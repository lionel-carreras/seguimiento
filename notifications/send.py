# notifications/send.py
import hashlib, hmac, time, urllib.parse, json, requests, base64
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
    kn  = parts['SharedAccessKeyName'].strip()
    key_raw = parts['SharedAccessKey'].strip().encode('utf-8')  # CLAVE CRUDA
    hub = (parts.get('EntityPath') or getattr(settings, 'NH_HUB', '')).strip()
    return ep, hub, kn, key_raw

def _sas_for_messages(ep: str, hub: str, key_name: str, key_raw: bytes, ttl: int = 600) -> str:
    resource = f"{ep}/{hub}/messages"
    sr_enc = urllib.parse.quote_plus(resource)
    expiry = int(time.time()) + ttl
    sig_b64 = base64.b64encode(hmac.new(key_raw, f"{sr_enc}\n{expiry}".encode(), hashlib.sha256).digest()).decode()
    return f"SharedAccessSignature sr={sr_enc}&sig={urllib.parse.quote_plus(sig_b64)}&se={expiry}&skn={urllib.parse.quote_plus(key_name)}"

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        data = json.loads(request.body.decode('utf-8') if request.body else '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    envio_id = (str(data.get('envio_id') or '').strip())
    user_payload = data.get('payload') or {"title": "Actualización", "body": "Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    ep, hub, key_name, key_raw = _parse_cs(settings.NH_CONNECTION_STRING)
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath o NH_HUB')

    sas = _sas_for_messages(ep, hub, key_name, key_raw)
    url = f"{ep}/{hub}/messages"

    body = {"notification": {"title": str(user_payload.get("title","")), "body": str(user_payload.get("body",""))}}
    headers = {
        "Authorization": sas,
        "Content-Type": "application/json",
        "ServiceBusNotification-Format": "browser",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
    }

    r = requests.post(url, params={"api-version": "2015-01"},
                      headers=headers, data=json.dumps(body).encode('utf-8'), timeout=15)

    return JsonResponse({
        "status": r.status_code, "reason": r.reason,
        "text": (r.text or "")[:500],
        "called": url
    }, status=r.status_code)
