import json, os
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def vapid_public(request):
    return JsonResponse({"vapid_public": settings.VAPID_PUBLIC_KEY or ""})

@csrf_exempt
def subscribe(request):
    # Placeholder (no llama a NH). Devuelve 204 para que el cliente siga.
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    return JsonResponse({"ok": True}, status=204)

        "Content-Type": "application/json",
        "x-ms-version": "2015-01"
    }
    r = requests.put(f"{uri}?api-version=2015-01", headers=headers, json=payload, timeout=10)
    return JsonResponse({"status": r.status_code, "text": r.text})
