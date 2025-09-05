# notifications/send.py  (cambios MÍNIMOS)
import base64, hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
    kn  = parts['SharedAccessKeyName'].strip()
    key = base64.b64decode(parts['SharedAccessKey'].strip())
    ent = parts.get('EntityPath', '').strip()
    return ep, kn, key, ent

def _sas(resource_base: str, key_name: str, key_bytes: bytes, ttl: int = 600) -> str:
    # 👉 el sr debe ser el HUB BASE, lowercased y URL-encoded (sin /messages)
    sr_raw_lower = resource_base.lower()
    sr_enc = urllib.parse.quote(sr_raw_lower, safe='')
    expiry = int(time.time()) + ttl
    sig = base64.b64encode(hmac.new(key_bytes, f"{sr_enc}\n{expiry}".encode(), hashlib.sha256).digest()).decode()
    return f"SharedAccessSignature sr={sr_enc}&sig={urllib.parse.quote(sig)}&se={expiry}&skn={urllib.parse.quote(key_name)}"

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        data = json.loads(request.body.decode('utf-8') if request.body else '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    envio_id = str(data.get('envio_id') or '').strip()
    payload = data.get('payload') or {"title": "Actualización", "body": "Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    cs = settings.NH_CONNECTION_STRING
    ep, key_name, key_bytes, entity = _parse_cs(cs)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath en connection string o NH_HUB en settings/env')

    # 👉 base del hub (para firmar) y URL de envío (para hacer POST)
    resource_base = f"{ep}/{hub}"               # para el SR del token
    resource_post = f"{resource_base}/messages" # endpoint real del POST

    sas = _sas(resource_base, key_name, key_bytes)

    headers = {
        "Authorization": sas,
        "Content-Type": "application/json; charset=utf-8",
        "ServiceBusNotification-Format": "webpush",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
        "x-ms-version": "2015-01",
        "Accept": "application/json",
    }

    try:
        r = requests.post(
            resource_post,
            params={"api-version": "2015-01"},  # la query NO va en el sr
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=10,
        )
    except requests.RequestException as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)

    return JsonResponse({
        "status": r.status_code,
        "reason": r.reason,
        "text": r.text,
        "hub": hub,
        "resource": resource_post,
    }, status=r.status_code)

