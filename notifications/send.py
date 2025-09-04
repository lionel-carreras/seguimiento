# notifications/send.py
import base64, hashlib, hmac, time, urllib.parse, json, requests
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs: str):
    parts = dict(p.split("=", 1) for p in cs.split(";") if p)
    ep = (parts.get("Endpoint", "") or "").strip()
    if ep.startswith("sb://"):
        ep = "https://" + ep[len("sb://"):]
    ep = ep.rstrip("/")
    key_name = (parts.get("SharedAccessKeyName","") or "").strip()
    key_b64  = (parts.get("SharedAccessKey","") or "").strip()
    entity   = (parts.get("EntityPath","") or "").strip()   # por si tu CS trae EntityPath
    return ep, key_name, key_b64, entity

def _sas(uri: str, key_name: str, key_b64: str, ttl_seconds: int = 600) -> str:
    expiry = int(time.time()) + ttl_seconds
    resource = uri  # ⬅️ SIN lower()
    sr = urllib.parse.quote(resource, safe="")  # sr exacto, URL-encoded
    to_sign = f"{sr}\n{expiry}".encode("utf-8")

    key_bytes = base64.b64decode(key_b64)
    sig_bytes = hmac.new(key_bytes, to_sign, hashlib.sha256).digest()
    sig_b64   = base64.b64encode(sig_bytes).decode("utf-8")
    sig       = urllib.parse.quote(sig_b64, safe="")

    return f"SharedAccessSignature sr={sr}&sig={sig}&se={expiry}&skn={urllib.parse.quote(key_name, safe='')}"

@csrf_exempt
def send_to_envio(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    raw = request.body or b'{}'
    try:
        data = json.loads(raw)
    except UnicodeDecodeError:
        data = json.loads(raw.decode('latin-1'))

    envio_id = str(data.get('envio_id') or "").strip()
    payload = data.get('payload') or {"title":"Actualización", "body":"Tu envío cambió de estado"}
    if not envio_id:
        return HttpResponseBadRequest("envio_id requerido")

    ep, key_name, key_b64, entity = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = entity or settings.NH_HUB  # si la CS trae EntityPath, úsalo
    uri = f"{ep}/{hub}/messages"
    uri_with_ver = f"{uri}?api-version=2015-01"

    if getattr(settings, "DEBUG", False):
        print("NH DEBUG → ep:", ep)
        print("NH DEBUG → hub:", hub)
        print("NH DEBUG → key_name:", key_name)
        print("NH DEBUG → resource (sr):", uri)  # ahora EXACTO

    headers = {
        "Authorization": _sas(uri, key_name, key_b64, ttl_seconds=300),
        "Content-Type": "application/json; charset=utf-8",
        "ServiceBusNotification-Format": "browser",
        "ServiceBusNotification-Tags": f"envio:{envio_id}",
        "Accept": "application/json",
    }

    resp = requests.post(uri_with_ver, headers=headers, data=json.dumps(payload))
    ok = 200 <= resp.status_code < 300
    return JsonResponse(
        {"status": resp.status_code, "reason": resp.reason, "text": (resp.text or "")[:2000], "sent_to": f"envio:{envio_id}"},
        status=200 if ok else 502,
    )
