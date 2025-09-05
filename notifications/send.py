# notifications/send.py
import hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
    kn  = parts['SharedAccessKeyName'].strip()
    # IMPORTANTE: usar la clave cruda (sin base64.decode)
    key_raw = parts['SharedAccessKey'].strip().encode('utf-8')
    ent = (parts.get('EntityPath') or '').strip()
    return ep, kn, key_raw, ent

def _sas_for_messages(ep: str, hub: str, key_name: str, key_raw: bytes, ttl: int = 600) -> str:
    resource = f"{ep}/{hub}/messages"
    sr_enc = urllib.parse.quote_plus(resource)
    expiry = int(time.time()) + ttl
    to_sign = f"{sr_enc}\n{expiry}".encode('utf-8')
    import base64
    sig_b64 = base64.b64encode(hmac.new(key_raw, to_sign, hashlib.sha256).digest()).decode()
    sig_enc = urllib.parse.quote_plus(sig_b64)
    return f"SharedAccessSignature sr={sr_enc}&sig={sig_enc}&se={expiry}&skn={urllib.parse.quote_plus(key_name)}"

def _try_send(ep, hub, sas, envio_id, user_payload, fmt):
    """fmt: 'browser' o 'webpush'."""
    url = f"{ep}/{hub}/messages"
    # 1) payload estilo Web Push (Notification API)
    body = {
        "notification": {
            "title": str(user_payload.get("title", "")),
            "body":  str(user_payload.get("body", "")),
        }
    }
    headers = {
        "Authorization": sas,
        "Content-Type": "application/json",   # sin charset
        "ServiceBusNotification-Format": fmt,
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
    }
    r = requests.post(
        url, params={"api-version": "2015-01"},
        headers=headers,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        timeout=15
    )
    return r

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        data = json.loads(request.body.decode('utf-8') if request.body else '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    envio_id = (str(data.get('envio_id') or '').strip())
    user_payload = data.get('payload') or {"title":"Actualización","body":"Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    ep, key_name, key_raw, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath o NH_HUB')

    sas = _sas_for_messages(ep, hub, key_name, key_raw)

    # 1º intento: 'browser'
    r1 = _try_send(ep, hub, sas, envio_id, user_payload, fmt='browser')
    if r1.status_code == 201:
        return JsonResponse({"status": r1.status_code, "reason": r1.reason, "format": "browser"}, status=r1.status_code)
    # 2º intento: 'webpush'
    r2 = _try_send(ep, hub, sas, envio_id, user_payload, fmt='webpush')
    # devolvemos el más “prometedor”
    best = r1 if r1.status_code != 401 else r2  # si r1 fuera 401 (no va a pasar ya), devolvemos r2
    return JsonResponse({
        "status": best.status_code,
        "reason": best.reason,
        "text": (best.text or "")[:500],
        "format_tried": {"first":"browser","second":"webpush"},
        "called": f"{ep}/{hub}/messages"
    }, status=best.status_code)
