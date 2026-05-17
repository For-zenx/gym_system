from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.clients.models import Client
from .models import Plan
from .services import register_membership_renewal

class RenewPlanView(LoginRequiredMixin, View):
    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        plan_id = request.POST.get('plan_id')
        
        if not plan_id:
            messages.error(request, "Debe seleccionar un plan válido.")
            return redirect('clients:profile', codigo_afiliado=codigo_afiliado)
            
        plan = get_object_or_404(Plan, id=plan_id)
        
        try:
            membership, invoice = register_membership_renewal(client, plan)
            messages.success(request, f"Plan '{plan.nombre}' asignado correctamente. Factura generada: {invoice.nro_control}")
        except Exception as e:
            messages.error(request, f"Error al asignar plan: {str(e)}")
            
        return redirect('clients:profile', codigo_afiliado=codigo_afiliado)
