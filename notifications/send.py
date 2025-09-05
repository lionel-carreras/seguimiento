# notifications/send.py
import base64, hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
    kn  = parts['SharedAccessKeyName'].strip()
    key_b64 = parts['SharedAccessKey'].strip()
    ent = parts.get('EntityPath', '').strip()
    return ep, kn, key_b64, ent

def _sas_for_hub(resource_hub: str, key_name: str, key_b64: str, ttl: int = 600) -> str:
    exp = int(time.time()) + ttl
    sr_enc = urllib.parse.quote(resource_hub, safe='')  # SR = <ep>/<hub> (SIN /messages)
    key = base64.b64decode(key_b64)
    sig = base64.b64encode(hmac.new(key, f"{sr_enc}\n{exp}".encode(), hashlib.sha256).digest()).decode()
    return (
        f"SharedAccessSignature sr={sr_enc}"
        f"&sig={urllib.parse.quote(sig)}"
        f"&se={exp}"
        f"&skn={urllib.parse.quote(key_name)}"
    )

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

    ep, key_name, key_b64, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath en connection string o NH_HUB en settings/env')

    resource_hub = f"{ep}/{hub}"                # SR que se FIRMA
    resource_msg = f"{resource_hub}/messages"   # Endpoint al que SE ENVÍA
    sas = _sas_for_hub(resource_hub, key_name, key_b64)

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
            resource_msg,
            params={"api-version": "2015-01"},
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=15,
        )
    except requests.RequestException as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)

    return JsonResponse({
        "status": r.status_code,
        "reason": r.reason,
        "text": r.text,
        "hub": hub,
        "resource": resource_msg,
    }, status=r.status_code)

