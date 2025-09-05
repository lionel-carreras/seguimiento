# notifications/send.py
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

def _sas(resource: str, key_name: str, key_bytes: bytes, ttl: int = 600) -> str:
    # resource = https://<ns>.servicebus.windows.net/<Hub>   (sin /messages)
    se = int(time.time()) + ttl
    sr_enc = urllib.parse.quote_plus(resource)
    sig = base64.b64encode(hmac.new(key_bytes, f"{sr_enc}\n{se}".encode(), hashlib.sha256).digest()).decode()
    return f"SharedAccessSignature sr={sr_enc}&sig={urllib.parse.quote_plus(sig)}&se={se}&skn={urllib.parse.quote_plus(key_name)}"

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        data = json.loads(request.body.decode('utf-8') if request.body else '{}')
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    envio_id = str(data.get('envio_id') or '').strip()
    payload  = data.get('payload') or {}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    # --- SAS / NH ---
    ep, key_name, key_bytes, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or (getattr(settings, 'NH_HUB', '') or '').strip()
    if not hub:
        return HttpResponseBadRequest('Falta EntityPath o NH_HUB')

    sr_hub   = f"{ep}/{hub}"                 # lo que se firma
    url_post = f"{sr_hub}/messages"          # endpoint real para POST

    sas = _sas(sr_hub, key_name, key_bytes)

    # Forma que Notification Hubs espera para Browser
    body = {
        "notification": {
            "title": payload.get("title") or "Actualización",
            "body":  payload.get("body")  or "Tu envío cambió de estado"
        }
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode('utf-8')

    headers = {
        "Authorization": sas,
        "Content-Type": "application/json",         # <- sin charset
        "ServiceBusNotification-Format": "browser", # <- browser
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
        "x-ms-version": "2015-01",
        "Accept": "application/json",
        "Content-Length": str(len(body_bytes)),     # explícito por si acaso
    }

    try:
        r = requests.post(
            url_post,
            params={"api-version": "2015-01"},
            headers=headers,
            data=body_bytes,
            timeout=15,
        )
    except requests.RequestException as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)

    return JsonResponse({
        "status": r.status_code,
        "reason": r.reason,
        "text": r.text,
        "hub": hub,
        "resource": url_post,
        "tracking": {k:v for k,v in r.headers.items() if k.lower().startswith('x-ms') or 'tracking' in k.lower()}
    }, status=r.status_code)
