# notifications/send.py
import hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')  # https://<ns>.servicebus.windows.net
    kn  = parts['SharedAccessKeyName'].strip()
    # *** OJO: clave cruda, SIN base64.decode()
    key_raw = parts['SharedAccessKey'].strip().encode('utf-8')
    ent = (parts.get('EntityPath') or '').strip()
    return ep, kn, key_raw, ent

def _sas_for_messages(ep: str, hub: str, key_name: str, key_raw: bytes, ttl: int = 600) -> str:
    # Firmamos el recurso EXACTO que vamos a llamar: .../<Hub>/messages (sin querystring)
    resource = f"{ep}/{hub}/messages"
    # Codificación recomendada: quote_plus; sin forzar lower (no hizo falta en tus pruebas)
    sr_enc = urllib.parse.quote_plus(resource)
    expiry = int(time.time()) + ttl
    to_sign = f"{sr_enc}\n{expiry}".encode('utf-8')
    sig = hmac.new(key_raw, to_sign, hashlib.sha256).digest()
    sig_b64u = urllib.parse.quote_plus(__import__("base64").b64encode(sig).decode())
    return f"SharedAccessSignature sr={sr_enc}&sig={sig_b64u}&se={expiry}&skn={urllib.parse.quote_plus(key_name)}"

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

    ep, key_name, key_raw, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath o NH_HUB')

    url = f"{ep}/{hub}/messages"
    sas = _sas_for_messages(ep, hub, key_name, key_raw)

    # Cuerpo correcto para WebPush
    body = {
        "notification": {
            "title": str(user_payload.get("title", "")),
            "body":  str(user_payload.get("body", "")),
        }
        # puedes agregar "data": {...} si querés
    }

    headers = {
        "Authorization": sas,
        "Content-Type": "application/json",          # sin charset
        "ServiceBusNotification-Format": "webpush",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
    }

    try:
        r = requests.post(url, params={"api-version": "2015-01"},
                          headers=headers,
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          timeout=15)
    except requests.RequestException as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)

    return JsonResponse({
        "status": r.status_code,
        "reason": r.reason,
        "text": (r.text or "")[:500],
        "called": url,
        "signed_over": f"{url}",  # firmamos exactamente /messages
        "skn": key_name,
    }, status=r.status_code)
