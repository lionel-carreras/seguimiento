from django.urls import path
from . import views


app_name = 'tracking'

urlpatterns = [
path('', views.envios, name='home')
#path('<int:envio_id>/', views.detail, name='detail'),
]
