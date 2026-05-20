from django.shortcuts import render, get_object_or_404
from django.views.generic import DetailView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from .models import Client
from apps.billing.models import Plan, ExchangeRate

class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Client.objects.select_related('membership').all().order_by('-fecha_ingreso', '-id')
        q = self.request.GET.get('q', '')
        if q:
            queryset = queryset.filter(
                Q(cedula__icontains=q) |
                Q(codigo_afiliado__icontains=q) |
                Q(nombre__icontains=q)
            )
        return queryset

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
        context['access_logs'] = self.object.access_logs.all()[:20]
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
            if Client.objects.filter(cedula=cedula).exclude(pk=client.pk).exists():
                messages.error(request, "Ya existe otro afiliado con esa cédula.")
            else:
                client.nombre = nombre
                client.cedula = cedula
                client.telefono = telefono
                client.save()
                messages.success(request, "Datos actualizados correctamente.")
        else:
            messages.error(request, "El nombre y la cédula son obligatorios.")
            
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('clients:profile', codigo_afiliado=codigo_afiliado)
