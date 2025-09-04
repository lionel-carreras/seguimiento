# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.http import FileResponse, Http404
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def service_worker_view(_):
    sw_path = BASE_DIR / 'service-worker.js'
    if not sw_path.exists():
        raise Http404("service-worker.js no encontrado")
    resp = FileResponse(open(sw_path, 'rb'), content_type='application/javascript')
    resp['Cache-Control'] = 'no-store'
    resp['Service-Worker-Allowed'] = '/'
    return resp

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('tracking/', include('tracking.urls')),
    path('drivers/', include('drivers.urls')),

    # <<--- API de Web Push bajo /api/push/
    path('api/push/', include('notifications.urls')),

    path('service-worker.js', service_worker_view, name='service_worker'),
    path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),
]
