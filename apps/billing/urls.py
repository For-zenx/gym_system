from django.urls import path
from .views import RenewPlanView

app_name = 'billing'

urlpatterns = [
    path('renovar/<str:codigo_afiliado>/', RenewPlanView.as_view(), name='renew_plan'),
]
