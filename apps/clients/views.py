from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import DetailView, ListView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from datetime import date
from .models import Client
from apps.billing.models import Plan, ExchangeRate, Invoice

class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Client.objects.prefetch_related('memberships').all().order_by('-fecha_ingreso', '-id')
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
        
        today = date.today()
        
        active_mems = self.object.active_memberships
        queued_mems = self.object.memberships.filter(fecha_inicio__gt=today).order_by('fecha_inicio')
        historical_mems = self.object.memberships.filter(fecha_fin__lt=today).order_by('-fecha_fin')
        
        if active_mems.exists():
            context['membership'] = active_mems.order_by('-fecha_fin').first()
            context['active_memberships'] = active_mems
        else:
            context['membership'] = None
            context['active_memberships'] = []
            
        context['queued_memberships'] = queued_mems
        context['historical_memberships'] = historical_mems
            
        context['invoices'] = Invoice.objects.filter(client=self.object).order_by('-fecha_emision')[:10]
            
        context['planes'] = Plan.objects.filter(is_active=True)
        context['latest_rate'] = ExchangeRate.get_latest()
        context['access_logs'] = self.object.access_logs.all()[:20]
        return context

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
