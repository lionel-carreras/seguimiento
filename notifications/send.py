# notifications/send.py
import base64, hashlib, hmac, time, urllib.parse, json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    try:
        parts = dict(p.split('=', 1) for p in cs.split(';') if p and '=' in p)
        ep  = parts['Endpoint'].strip().replace('sb://', 'https://').rstrip('/')
        kn  = parts['SharedAccessKeyName'].strip()
        key = base64.b64decode(parts['SharedAccessKey'].strip())
        ent = parts.get('EntityPath', '').strip()
        return ep, kn, key, ent
    except Exception:
        # No reventar el arranque si algo falta; la vista devolverá 500 coherente.
        return '', '', b'', ''


def _sas_for_hub(ep: str, hub: str, key_name: str, key_bytes: bytes, ttl: int = 600):
    # 1) Recurso base del HUB (sin /messages) en minúsculas
    resource = f"{ep}/{hub}".lower()

    # 2) URL-encode y LUEGO forzar minúsculas en el encoded (para que %2F -> %2f)
    sr_enc = urllib.parse.quote_plus(resource).lower()

    # 3) Firmar "<sr-enc>\n<expiry>"
    expiry = int(time.time()) + ttl
    to_sign = f"{sr_enc}\n{expiry}".encode("utf-8")
    sig = base64.b64encode(hmac.new(key_bytes, to_sign, hashlib.sha256).digest()).decode()

    # 4) Token
    token = (
        f"SharedAccessSignature sr={sr_enc}"
        f"&sig={urllib.parse.quote_plus(sig)}"
        f"&se={expiry}"
        f"&skn={urllib.parse.quote_plus(key_name)}"
    )
    return token, resource  # devolvemos el resource “humano” solo para debug


@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    try:
        body = request.body.decode('utf-8') if request.body else '{}'
        data = json.loads(body)
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    envio_id = str(data.get('envio_id') or '').strip()
    payload = data.get('payload') or {"title": "Actualización", "body": "Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest('envio_id requerido')

    cs = getattr(settings, 'NH_CONNECTION_STRING', '')
    ep, key_name, key_bytes, entity = _parse_cs(cs)
    hub = (entity or getattr(settings, 'NH_HUB', '')).strip()

    if not (ep and key_name and key_bytes and hub):
        return JsonResponse(
            {"status": 500, "reason": "Misconfiguration",
             "text": "NH_CONNECTION_STRING o NH_HUB incompletos"},
            status=500
        )

    # sr = <ep>/<hub>  (lo firmado); resource = <ep>/<hub>/messages (la URL de envío)
    sas, signed_sr = _sas_for_hub(ep, hub, key_name, key_bytes)
    resource = f"{ep}/{hub}/messages"

    headers = {
        "Authorization": sas,
        "Content-Type": "application/json; charset=utf-8",
        "ServiceBusNotification-Format": "webpush",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
        "Accept": "application/json",
    }

    try:
        import requests  # import aquí evita fallar en el import del módulo si requests no está
        r = requests.post(
            resource,
            params={"api-version": "2015-01"},     # La query NO entra en el sr firmado
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=10,
        )
        return JsonResponse({
            "status": r.status_code,
            "reason": r.reason,
            "text": r.text,
            "hub": hub,
            "resource": resource,
            "signed_sr": signed_sr,
            "skn": key_name,
        }, status=r.status_code)
    except Exception as e:
        return JsonResponse({"status": 502, "reason": "Bad Gateway", "error": repr(e)}, status=502)
