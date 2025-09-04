# notifications/push.py
import base64, hashlib, hmac, time, urllib.parse, json, requests, os
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _parse_cs(cs):
    parts = dict(s.split('=',1) for s in cs.split(';') if '=' in s)
    ep = parts['Endpoint'].replace('sb://','https://').rstrip('/')  # https://<ns>.servicebus.windows.net
    return ep, parts['SharedAccessKeyName'], parts['SharedAccessKey']

def _sas(uri, key_name, key, ttl=3600):
    expiry = int(time.time()) + ttl
    to_sign = f"{urllib.parse.quote_plus(uri)}\n{expiry}".encode()
    sig = base64.b64encode(hmac.new(key.encode(), to_sign, hashlib.sha256).digest()).decode()
    return f"SharedAccessSignature sr={urllib.parse.quote_plus(uri)}&sig={urllib.parse.quote_plus(sig)}&se={expiry}&skn={key_name}"

def vapid_public(_):
    return JsonResponse(settings.VAPID_PUBLIC_KEY, safe=False)

@csrf_exempt
def subscribe(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    body = json.loads(request.body or '{}')
    sub = body.get('subscription') or {}
    tags = body.get('tags') or []

    # Construir Installation (platform browser)
    push = {
        "endpoint": sub.get("endpoint"),
        "p256dh": sub.get("keys",{}).get("p256dh"),
        "auth": sub.get("keys",{}).get("auth"),
    }
    if not all(push.values()):
        return HttpResponseBadRequest("Suscripción incompleta")

    installation_id = request.user.is_authenticated and f"user:{request.user.id}" or push["endpoint"][-32:]
    ep, key_name, key = _parse_cs(settings.NH_CONNECTION_STRING)
    hub = settings.NH_HUB
    uri = f"{ep}/{hub}/installations/{installation_id}"

    payload = {
        "installationId": installation_id,
        "platform": "browser",
        "pushChannel": push,
        "tags": tags
    }
    headers = {
        "Authorization": _sas(uri, key_name, key),
        "Content-Type": "application/json",
        "x-ms-version": "2015-01"
    }
    r = requests.put(f"{uri}?api-version=2015-01", headers=headers, json=payload, timeout=10)
    return JsonResponse({"status": r.status_code, "text": r.text})
