"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.http import FileResponse
from django.conf import settings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def service_worker_view(_):
    sw_path = BASE_DIR / 'service-worker.js'  
    resp = FileResponse(open(sw_path, 'rb'), content_type='application/javascript')
    # No cachear el SW para garantizar updates
    resp['Cache-Control'] = 'no-store'
    # Permitir scope raíz aunque el archivo se sirva por vista
    resp['Service-Worker-Allowed'] = '/'
    return resp

urlpatterns = [
path('admin/', admin.site.urls),
path('', TemplateView.as_view(template_name='home.html'), name='home'),
path('tracking/', include('tracking.urls')),
path('drivers/', include('drivers.urls')),
path('notifications/', include('notifications.urls')),
path('service-worker.js', service_worker_view, name='service_worker'),
path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),
]
