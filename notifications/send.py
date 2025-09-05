import base64, hashlib, hmac, json, time, urllib.parse, urllib.request, urllib.error
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
    hub = (parts.get('EntityPath') or settings.NH_HUB).strip()
    kn  = parts['SharedAccessKeyName'].strip()
    key = parts['SharedAccessKey'].strip()
    return ep, hub, kn, key

def _sas_for_hub(endpoint_https: str, hub: str, key_name: str, key_b64: str, ttl=600):
    # Recurso base del hub SIN /messages y en minúsculas (evita 401 por case mismatch)
    base = f"{endpoint_https}/{hub}".lower()
    expiry = int(time.time()) + ttl
    sr = urllib.parse.quote(base, safe='')

    mac = hmac.new(
        base64.b64decode(key_b64),
        f"{sr}\n{expiry}".encode(),
        hashlib.sha256
    ).digest()

    sig = urllib.parse.quote(base64.b64encode(mac).decode())
    skn = urllib.parse.quote(key_name)
    token = f"SharedAccessSignature sr={sr}&sig={sig}&se={expiry}&skn={skn}"
    return base, token

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        data = json.loads(request.body or '{}')
    except Exception:
        data = {}

    envio_id = str(data.get('envio_id') or '')
    payload  = data.get('payload') or {"title":"Actualización","body":"Tu envío cambió de estado"}

    try:
        ep, hub, key_name, key_b64 = _parse_cs(settings.NH_CONNECTION_STRING)
        base_lc, token = _sas_for_hub(ep, hub, key_name, key_b64)
        url = f"{base_lc}/messages?api-version=2015-01"

        headers = {
            "Authorization": token,
            "Content-Type": "application/json; charset=utf-8",
            "x-ms-version": "2015-01",
            "ServiceBusNotification-Format": "webpush",
        }
        if envio_id:
            headers["ServiceBusNotification-Tags"] = f"envio:{envio_id}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            method='POST',
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = (resp.read() or b'')[:500].decode(errors='ignore')
                return JsonResponse({
                    "status": resp.status, "reason": "OK", "text": body,
                    "hub": hub, "resource": url
                }, status=201)
        except urllib.error.HTTPError as e:
            body = (e.read() or b'')[:500].decode(errors='ignore')
            return JsonResponse({
                "status": e.code, "reason": "HTTPError", "text": body,
                "hub": hub, "resource": url
            }, status=502)

    except Exception as e:
        return JsonResponse({"status": 500, "error": repr(e)}, status=500)

