from django.shortcuts import render, get_object_or_404
from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Client
from apps.billing.models import Plan, ExchangeRate

class ClientProfileView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'clients/client_profile.html'
    context_object_name = 'client'
    slug_field = 'codigo_afiliado'
    slug_url_kwarg = 'codigo_afiliado'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.object, 'membership'):
            context['membership'] = self.object.membership
            context['invoices'] = self.object.membership.invoices.all().order_by('-fecha_emision')[:10]
        else:
            context['membership'] = None
            context['invoices'] = []
            
        context['planes'] = Plan.objects.all()
        context['latest_rate'] = ExchangeRate.get_latest()
        return context

from django.views import View
from django.shortcuts import redirect
from django.contrib import messages

class EditClientView(LoginRequiredMixin, View):
    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        
        nombre = request.POST.get('nombre')
        cedula = request.POST.get('cedula')
        telefono = request.POST.get('telefono')
        
        if nombre and cedula:
            # Comprobar si la cédula ya existe en otro cliente
            if Client.objects.filter(cedula=cedula).exclude(pk=client.pk).exists():
                messages.error(request, "Ya existe otro afiliado con esa cédula.")
            else:
                client.nombre = nombre
                client.cedula = cedula
                client.telefono = telefono
                client.save()
                messages.success(request, "Datos personales actualizados correctamente.")
        else:
            messages.error(request, "El nombre y la cédula son obligatorios.")
            
        return redirect('clients:profile', codigo_afiliado=codigo_afiliado)
