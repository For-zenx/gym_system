from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView
from django.views import View
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from .models import Client
from .services import (
    ALLOWED_INACTIVITY_YEARS,
    BulkDeleteCountMismatchError,
    bulk_delete_inactive_clients,
    build_inactive_clients_preview,
    delete_client,
    replace_client_front_photo,
)
from .validation import validate_client_data, client_form_context, apply_client_fields
from apps.billing.models import Plan, ExchangeRate, Invoice, ClientBillingEvent
from apps.billing.services import (
    CUT_DATE_CHANGE_REASONS,
    get_chargeable_plans,
    get_display_service_periods_for_client,
    get_recent_service_periods_for_client,
    get_profile_subscription_summary,
)
from apps.lockers.services import (
    get_display_locker_rentals_for_client,
    get_recent_rentals_for_client,
)
from apps.users.mixins import PermissionRequiredMixin
from apps.users.permissions import has_permission


class ClientListView(PermissionRequiredMixin, ListView):
    required_permission = "clients.view_list"
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


class ClientProfileView(PermissionRequiredMixin, DetailView):
    required_permission = "clients.view_profile"
    model = Client
    template_name = 'clients/client_profile.html'
    context_object_name = 'client'
    slug_field = 'codigo_afiliado'
    slug_url_kwarg = 'codigo_afiliado'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['invoices'] = Invoice.objects.filter(client=self.object).order_by('-fecha_emision')[:10]

        active_plans = Plan.objects.filter(is_active=True)
        context['latest_rate'] = ExchangeRate.get_latest()
        context['access_logs'] = self.object.access_logs.all()[:20]
        context['billing_events'] = self.object.billing_events.select_related('created_by')[:15]
        context['subscription_summary'] = get_profile_subscription_summary(self.object)
        context['display_locker_rentals'] = get_display_locker_rentals_for_client(self.object)
        context['locker_rentals'] = get_recent_rentals_for_client(self.object)
        context['display_service_periods'] = get_display_service_periods_for_client(self.object)
        context['service_periods'] = get_recent_service_periods_for_client(self.object)
        context['has_profile_history'] = bool(
            context['subscription_summary'].get('fixed_groups_detail')
            or context['service_periods']
            or context['locker_rentals']
        )
        context['has_chargeable_plans'] = bool(
            get_chargeable_plans(self.object, active_plans)
        )
        context['cut_date_change_reasons'] = CUT_DATE_CHANGE_REASONS
        can_view_phone = has_permission(self.request.user, "clients.view_phone")
        context.update(
            client_form_context(client=self.object, can_view_phone=can_view_phone)
        )
        return context


class EditClientView(PermissionRequiredMixin, View):
    required_permission = "clients.edit"
    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)

        errors, cleaned = validate_client_data(
            request.POST.get('nombre'),
            request.POST.get('cedula_prefix'),
            request.POST.get('cedula_numero'),
            request.POST.get('telefono'),
            request.POST.get('fecha_nacimiento'),
            request.POST.get('sexo'),
        )

        if errors:
            for message in errors.values():
                messages.error(request, message)
        elif Client.objects.filter(cedula=cleaned['cedula']).exclude(pk=client.pk).exists():
            messages.error(request, 'Ya existe otro afiliado con esa cédula/RIF.')
        else:
            preserve_phone = (
                not has_permission(request.user, "clients.view_phone")
                and not cleaned["telefono"]
            )
            apply_client_fields(client, cleaned, preserve_phone_if_blank=preserve_phone)
            client.save()
            messages.success(request, 'Datos actualizados correctamente.')

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('clients:profile', codigo_afiliado=codigo_afiliado)


class InactiveClientsPreviewView(PermissionRequiredMixin, View):
    required_permission = "clients.delete"

    def get(self, request):
        years_raw = request.GET.get("years", "")
        try:
            inactivity_years = int(years_raw)
        except (TypeError, ValueError):
            return JsonResponse(
                {"status": "error", "message": "Seleccione un período válido."},
                status=400,
            )

        if inactivity_years not in ALLOWED_INACTIVITY_YEARS:
            return JsonResponse(
                {"status": "error", "message": "Seleccione 1 o 2 años de inactividad."},
                status=400,
            )

        preview = build_inactive_clients_preview(inactivity_years)
        preview["status"] = "success"
        return JsonResponse(preview)


class BulkDeleteInactiveClientsView(PermissionRequiredMixin, View):
    required_permission = "clients.delete"

    def post(self, request):
        if request.POST.get("confirm_bulk_delete") != "1":
            messages.error(request, "Debes confirmar la eliminación masiva.")
            return redirect("clients:client_list")

        if request.POST.get("bulk_delete_ack") != "on":
            messages.error(
                request,
                "Debes confirmar que entiendes que la acción no es reversible.",
            )
            return redirect("clients:client_list")

        try:
            inactivity_years = int(request.POST.get("inactivity_years", ""))
        except (TypeError, ValueError):
            messages.error(request, "Período de inactividad no válido.")
            return redirect("clients:client_list")

        if inactivity_years not in ALLOWED_INACTIVITY_YEARS:
            messages.error(request, "Período de inactividad no válido.")
            return redirect("clients:client_list")

        try:
            confirm_count = int(request.POST.get("confirm_count", ""))
        except (TypeError, ValueError):
            messages.error(
                request,
                "Debes escribir la cantidad exacta de afiliados a eliminar.",
            )
            return redirect("clients:client_list")

        try:
            deleted_codes = bulk_delete_inactive_clients(inactivity_years, confirm_count)
        except BulkDeleteCountMismatchError:
            messages.error(
                request,
                "La cantidad de afiliados cambió desde la vista previa. "
                "Vuelva a consultar antes de eliminar.",
            )
            return redirect("clients:client_list")

        if not deleted_codes:
            messages.warning(request, "No había afiliados inactivos que eliminar.")
        else:
            messages.success(
                request,
                f"Se eliminaron {len(deleted_codes)} afiliados inactivos. "
                "Las facturas emitidas permanecen en el historial.",
            )
        return redirect("clients:client_list")


class ClientDeleteView(PermissionRequiredMixin, View):
    required_permission = "clients.delete"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)

        if request.POST.get("confirm_delete") != "1":
            messages.error(request, "Debes confirmar la eliminación del afiliado.")
            return redirect("clients:profile", codigo_afiliado=codigo_afiliado)

        typed_code = (request.POST.get("confirm_codigo") or "").strip()
        if typed_code != client.codigo_afiliado:
            messages.error(request, "El código de afiliado no coincide. No se eliminó el registro.")
            return redirect("clients:profile", codigo_afiliado=codigo_afiliado)

        nombre = client.nombre
        delete_client(client)
        messages.success(
            request,
            f"Afiliado {nombre} eliminado. Las facturas emitidas permanecen en el historial con datos históricos.",
        )
        return redirect("clients:client_list")


class ReEnrollClientView(PermissionRequiredMixin, View):
    required_permission = "clients.edit"

    def get(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        return render(request, "clients/re_enrollment.html", {"client": client})

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        foto_frente_b64 = request.POST.get("foto_frente_base64")
        wants_json = request.headers.get("X-Reenroll-Submit") == "1"
        profile_url = reverse("clients:profile", kwargs={"codigo_afiliado": client.codigo_afiliado})

        if not foto_frente_b64:
            message = "Debe capturar la nueva foto del afiliado en la tablet de enrolamiento."
            if wants_json:
                return JsonResponse({"status": "error", "message": message}, status=400)
            messages.error(request, message)
            return redirect("clients:re_enroll", codigo_afiliado=codigo_afiliado)

        try:
            replace_client_front_photo(client, foto_frente_b64)
        except Exception as exc:
            message = f"No se pudo actualizar la foto facial: {exc}"
            if wants_json:
                return JsonResponse({"status": "error", "message": message}, status=400)
            messages.error(request, message)
            return redirect("clients:re_enroll", codigo_afiliado=codigo_afiliado)

        success_message = f"Foto y datos biométricos de {client.nombre} actualizados correctamente."
        if wants_json:
            return JsonResponse({"status": "success", "redirect_url": profile_url})
        messages.success(request, success_message)
        return redirect("clients:profile", codigo_afiliado=codigo_afiliado)
