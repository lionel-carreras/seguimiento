# notifications/send.py
import base64, hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
    ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')  # https://<ns>.servicebus.windows.net
    kn  = parts['SharedAccessKeyName'].strip()
    kb  = base64.b64decode(parts['SharedAccessKey'].strip())  # bytes
    ent = parts.get('EntityPath', '').strip()
    return ep, kn, kb, ent

def _sas_for_hub(ep: str, hub: str, key_name: str, key_bytes: bytes, ttl: int = 600) -> str:
    # SR debe estar en minúsculas y URL-encoded con quote_plus
    resource = f"{ep}/{hub}"
    sr_lc_enc = urllib.parse.quote_plus(resource.lower())
    expiry = int(time.time()) + ttl
    to_sign = f"{sr_lc_enc}\n{expiry}".encode('utf-8')
    sig = base64.b64encode(hmac.new(key_bytes, to_sign, hashlib.sha256).digest()).decode()
    return (
        "SharedAccessSignature "
        f"sr={sr_lc_enc}&sig={urllib.parse.quote_plus(sig)}&se={expiry}&skn={urllib.parse.quote_plus(key_name)}"
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
    user_payload = data.get('payload') or {"title": "Actualización", "body": "Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    # --- SAS / NH ---
    ep, key_name, key_bytes, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath en connection string o NH_HUB en settings/env')

    # SAS firmado sobre el HUB (no sobre /messages)
    auth = _sas_for_hub(ep, hub, key_name, key_bytes)

    # URL de envío
    url = f"{ep}/{hub}/messages"
    params = {"api-version": "2015-01"}

    # CUERPO en formato webpush correcto
    body = {
        "notification": {
            "title": str(user_payload.get("title", "")),
            "body":  str(user_payload.get("body", "")),
        }
        # si querés, podés añadir "data": {...}
    }

    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",        # sin charset
        "ServiceBusNotification-Format": "webpush",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
        # "x-ms-version": "2015-01"  # opcional
    }

    try:
        r = requests.post(url, params=params, headers=headers,
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          timeout=15)
    except requests.RequestException as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)

    return JsonResponse({
        "status": r.status_code,
        "reason": r.reason,
        "text": r.text,
        "hub": hub,
        "resource_signed_over": f"{ep}/{hub}".lower(),
        "endpoint_called": f"{url}",
    }, status=r.status_code)
