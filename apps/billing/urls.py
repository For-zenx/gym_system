from django.urls import path
from .views import RenewPlanView, PlanListView, PlanCreateView, PlanUpdateView, PlanDeleteView, MembershipDeleteView, ExchangeRateUpdateView, InvoiceListView, InvoiceDetailView, PrintInvoiceActionView

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
    path('facturas/<int:pk>/', InvoiceDetailView.as_view(), name='invoice_detail'),
    path('facturas/<int:pk>/imprimir/', PrintInvoiceActionView.as_view(), name='print_invoice'),
]
