from django.urls import path
from .views import RenewPlanView, PlanListView, PlanCreateView, PlanUpdateView, PlanDeleteView, MembershipDeleteView, ExchangeRateUpdateView, InvoiceListView

app_name = 'billing'

urlpatterns = [
    path('renovar/<str:codigo_afiliado>/', RenewPlanView.as_view(), name='renew_plan'),
    path('planes/', PlanListView.as_view(), name='plan_list'),
    path('planes/nuevo/', PlanCreateView.as_view(), name='plan_create'),
    path('planes/editar/<int:pk>/', PlanUpdateView.as_view(), name='plan_update'),
    path('planes/borrar/<int:pk>/', PlanDeleteView.as_view(), name='plan_delete'),
    path('membresia/eliminar/<int:pk>/', MembershipDeleteView.as_view(), name='membership_delete'),
    path('tasa/actualizar/', ExchangeRateUpdateView.as_view(), name='update_rate'),
    path('facturas/', InvoiceListView.as_view(), name='invoice_list'),
]
