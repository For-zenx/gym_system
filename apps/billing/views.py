from urllib.parse import urlencode
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from apps.clients.models import Client
from django.db.models import Q
from .models import Plan, Membership, ExchangeRate, Invoice
from .services import register_membership_renewal
from .printer import build_invoice_preview_lines, print_invoice


def _get_safe_next_url(request, value):
    if url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}):
        return value
    return ''


class ExchangeRateUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            tasa_str = request.POST.get('tasa_ves')
            if not tasa_str:
                raise ValueError("La tasa no puede estar vacía.")
            
            tasa = float(tasa_str.replace(',', '.'))
            if tasa <= 0:
                raise ValueError("La tasa debe ser mayor a 0.")
                
            ExchangeRate.objects.create(tasa_ves=tasa)
            messages.success(request, f"Tasa VES/$ actualizada a {tasa:.2f}")
        except ValueError as e:
            messages.error(request, f"Valor de tasa inválido: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error al actualizar la tasa: {str(e)}")
            
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER', '/')
        return redirect(next_url)

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

class PlanListView(LoginRequiredMixin, ListView):
    model = Plan
    template_name = 'billing/plan_list.html'
    context_object_name = 'planes'
    
    def get_queryset(self):
        return Plan.objects.filter(is_active=True).order_by('-id')

class PlanCreateView(LoginRequiredMixin, CreateView):
    model = Plan
    template_name = 'billing/plan_form.html'
    fields = ['nombre', 'dias_duracion', 'precio_usd', 'hora_inicio', 'hora_fin']
    success_url = reverse_lazy('billing:plan_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Plan creado exitosamente.")
        return super().form_valid(form)

class PlanUpdateView(LoginRequiredMixin, UpdateView):
    model = Plan
    template_name = 'billing/plan_form.html'
    fields = ['nombre', 'dias_duracion', 'precio_usd', 'hora_inicio', 'hora_fin']
    success_url = reverse_lazy('billing:plan_list')

    def form_valid(self, form):
        old_plan = self.get_object()
        old_plan.is_active = False
        old_plan.save()
        
        Plan.objects.create(
            nombre=form.cleaned_data['nombre'],
            dias_duracion=form.cleaned_data['dias_duracion'],
            precio_usd=form.cleaned_data['precio_usd'],
            hora_inicio=form.cleaned_data['hora_inicio'],
            hora_fin=form.cleaned_data['hora_fin'],
            is_active=True
        )
        
        messages.success(self.request, "Plan actualizado exitosamente (Se conservó el historial de la versión anterior).")
        return redirect('billing:plan_list')

class PlanDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        plan.is_active = False
        plan.save()
        messages.success(request, "Plan eliminado exitosamente.")
        return redirect('billing:plan_list')

class MembershipDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        client_code = membership.client.codigo_afiliado
        
        # We only allow deleting if it hasn't started yet (queued)
        from datetime import date
        if membership.fecha_inicio > date.today():
            membership.delete()
            messages.success(request, "Membresía encolada cancelada exitosamente.")
        else:
            messages.error(request, "No se puede eliminar una membresía activa o pasada.")
            
        return redirect('clients:profile', codigo_afiliado=client_code)

class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        queryset = Invoice.objects.select_related('client', 'membership__plan').order_by('-fecha_emision', '-id')
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(nro_control__icontains=q) |
                Q(client__nombre__icontains=q) |
                Q(client__cedula__icontains=q) |
                Q(client__codigo_afiliado__icontains=q) |
                Q(client_nombre_snapshot__icontains=q) |
                Q(client_cedula_snapshot__icontains=q) |
                Q(client_codigo_snapshot__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'billing/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['latest_rate'] = ExchangeRate.get_latest()
        context['next_url'] = _get_safe_next_url(self.request, self.request.GET.get('next', ''))
        context['ticket_lines'] = build_invoice_preview_lines(self.object)
        return context


class PrintInvoiceActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        detail_url = reverse('billing:invoice_detail', kwargs={'pk': pk})
        next_url = _get_safe_next_url(request, request.POST.get('next', ''))
        if next_url:
            detail_url = f"{detail_url}?{urlencode({'next': next_url})}"
        
        if invoice.esta_impresa:
            messages.error(request, "Esta factura ya ha sido impresa y no se puede volver a imprimir.")
            return redirect(detail_url)

        try:
            print_invoice(invoice)
            messages.success(request, f"Factura {invoice.nro_control} enviada a la impresora con éxito.")
        except Exception as e:
            messages.error(request, f"Error al imprimir la factura: {str(e)}")

        return redirect(detail_url)
