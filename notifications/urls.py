# notifications/urls.py
from django.urls import path
from .push import vapid_public, subscribe
from .send import send_to_envio

app_name = 'notifications'

urlpatterns = [
    path('vapid-public', vapid_public, name='vapid_public'),
    path('subscribe', subscribe, name='push_subscribe'),
    path('send', send_to_envio, name='push_send'),
]

