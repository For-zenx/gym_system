from urllib.parse import urlencode

from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView
from django.views.generic.base import RedirectView
from django.core.exceptions import PermissionDenied
from django.views import View
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Exists, OuterRef, Q
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date
from .models import Client, GuestPass, PersonCategory, STAFF_PERSON_CATEGORIES
from .services import (
    ALLOWED_INACTIVITY_YEARS,
    BulkDeleteCountMismatchError,
    PROFILE_NOTE_MAX_LENGTH,
    bulk_delete_inactive_clients,
    build_inactive_clients_preview,
    delete_client,
    get_active_guest_pass,
    get_person_profile_url_name,
    issue_guest_pass,
    replace_client_front_photo,
    revoke_guest_pass,
    update_profile_note,
)
from .validation import (
    apply_client_fields,
    build_cedula,
    client_form_context,
    validate_client_data,
    validate_guest_pass_dates,
    guest_pass_custom_mode_enabled,
)
from apps.billing.models import Plan, ExchangeRate, Invoice, ClientBillingEvent
from apps.billing.services import (
    get_chargeable_plans,
    get_display_service_periods_for_client,
    get_recent_service_periods_for_client,
    get_profile_subscription_summary,
    grant_admin_access,
)
from apps.lockers.services import (
    get_display_locker_rentals_for_client,
    get_recent_rentals_for_client,
)
from apps.users.mixins import PermissionRequiredMixin
from apps.users.permissions import has_permission


STAFF_LIST_TYPES = {
    "empleado": PersonCategory.EMPLOYEE,
    "entrenador": PersonCategory.TRAINER,
    "socio": PersonCategory.PARTNER,
}


def _edit_permission_for_client(client):
    if client.is_member:
        return "clients.edit"
    return "staff_persons.edit"


def _profile_note_edit_permission(client):
    if client.is_member:
        return "clients.edit"
    if client.is_guest:
        return "guests.register"
    return None


def _view_permission_for_client(client):
    if client.is_member:
        return "clients.view_profile"
    return "staff_persons.view_profile"


def _delete_permission_for_client(client):
    if client.is_member:
        return "clients.delete"
    return "staff_persons.delete"


class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (
            has_permission(request.user, "clients.view_list")
            or has_permission(request.user, "guests.view_list")
        ):
            raise PermissionDenied("No tienes permiso para ver esta lista.")
        tipo = self._resolve_list_tipo(request)
        if tipo == "invitados" and not has_permission(request.user, "guests.view_list"):
            return redirect(reverse("clients:client_list"))
        if tipo == "afiliados" and not has_permission(request.user, "clients.view_list"):
            return redirect("{}?tipo=invitados".format(reverse("clients:client_list")))
        return super().dispatch(request, *args, **kwargs)

    def _resolve_list_tipo(self, request):
        tipo = (request.GET.get("tipo") or "afiliados").strip().lower()
        if tipo not in ("afiliados", "invitados"):
            return "afiliados"
        return tipo

    def get_queryset(self):
        tipo = self._resolve_list_tipo(self.request)
        q = self.request.GET.get('q', '')

        if tipo == "invitados":
            today = date.today()
            active_pass = GuestPass.objects.filter(
                guest=OuterRef("pk"),
                revoked_at__isnull=True,
                valid_from__lte=today,
                valid_until__gte=today,
            )
            queryset = (
                Client.objects.filter(person_category=PersonCategory.GUEST)
                .annotate(has_active_pass=Exists(active_pass))
                .order_by("-fecha_ingreso", "-id")
            )
            if q:
                queryset = queryset.filter(
                    Q(codigo_afiliado__icontains=q)
                    | Q(nombre__icontains=q)
                    | Q(cedula__icontains=q)
                )
            return queryset

        queryset = (
            Client.objects.filter(person_category=PersonCategory.MEMBER)
            .prefetch_related("memberships")
            .order_by("-fecha_ingreso", "-id")
        )
        if q:
            queryset = queryset.filter(
                Q(cedula__icontains=q)
                | Q(codigo_afiliado__icontains=q)
                | Q(nombre__icontains=q)
            )

        sexo = (self.request.GET.get("sexo") or "").strip().upper()
        if sexo == "M" or sexo == "F":
            queryset = queryset.filter(sexo=sexo)
        elif sexo == "_blank":
            queryset = queryset.filter(Q(sexo="") | Q(sexo__isnull=True))

        cedula_tipo = (self.request.GET.get("cedula_tipo") or "").strip().upper()
        if cedula_tipo in ("V", "J", "E"):
            queryset = queryset.filter(cedula__startswith="{}-".format(cedula_tipo))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tipo = self._resolve_list_tipo(self.request)
        query = self.request.GET.get('q', '').strip()
        sexo = (self.request.GET.get("sexo") or "").strip()
        cedula_tipo = (self.request.GET.get("cedula_tipo") or "").strip().upper()
        if cedula_tipo not in ("V", "J", "E"):
            cedula_tipo = ""

        context['search_query'] = query
        context['filter_sexo'] = sexo
        context['filter_cedula_tipo'] = cedula_tipo
        context['list_tipo'] = tipo
        context['can_view_members'] = has_permission(self.request.user, "clients.view_list")
        context['can_view_guests'] = has_permission(self.request.user, "guests.view_list")

        filter_params = {}
        if tipo == "invitados":
            filter_params["tipo"] = "invitados"
        if query:
            filter_params["q"] = query
        if tipo == "afiliados":
            if sexo:
                filter_params["sexo"] = sexo
            if cedula_tipo:
                filter_params["cedula_tipo"] = cedula_tipo
        context["filter_query"] = urlencode(filter_params)
        context["has_member_filters"] = bool(
            query or (tipo == "afiliados" and (sexo or cedula_tipo))
        )

        if tipo == "invitados":
            guest_ids = [g.pk for g in context["clients"]]
            active_passes = {
                p.guest_id: p
                for p in GuestPass.objects.filter(
                    guest_id__in=guest_ids,
                    revoked_at__isnull=True,
                    valid_from__lte=date.today(),
                    valid_until__gte=date.today(),
                ).select_related("sponsor")
            }
            context["active_pass_by_guest_id"] = active_passes
            for guest in context["clients"]:
                guest.active_pass = active_passes.get(guest.pk)
        return context


class ClientProfileView(PermissionRequiredMixin, DetailView):
    required_permission = "clients.view_profile"
    model = Client
    template_name = 'clients/client_profile.html'
    context_object_name = 'client'
    slug_field = 'codigo_afiliado'
    slug_url_kwarg = 'codigo_afiliado'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_guest:
            return redirect(
                reverse(
                    "guests:profile",
                    kwargs={"codigo_afiliado": self.object.codigo_afiliado},
                )
            )
        if not self.object.is_member:
            return redirect(
                reverse(
                    "staff_persons:profile",
                    kwargs={"codigo_afiliado": self.object.codigo_afiliado},
                )
            )
        return super().get(request, *args, **kwargs)

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
        context['all_memberships'] = self.object.memberships.select_related('plan').order_by('-fecha_inicio')
        context['has_chargeable_plans'] = bool(
            get_chargeable_plans(self.object, active_plans)
        )
        context['admin_access_fixed_plans'] = Plan.objects.filter(
            is_active=True,
            billing_type=Plan.BillingType.FIXED,
        ).order_by("nombre")
        context['can_grant_admin_access'] = has_permission(
            self.request.user, "clients.grant_admin_access"
        )
        context['can_edit_profile_note'] = has_permission(
            self.request.user, "clients.edit"
        )
        context['profile_note_max_length'] = PROFILE_NOTE_MAX_LENGTH
        context['profile_note_form_url'] = reverse(
            "clients:update_profile_note",
            kwargs={"codigo_afiliado": self.object.codigo_afiliado},
        )
        if has_permission(self.request.user, "classes.view"):
            from apps.classes.services import get_client_class_registrations

            context["class_registrations"] = get_client_class_registrations(self.object)
        
        from apps.billing.corporate_services import get_group_for_client
        corp_group = get_group_for_client(self.object)
        if corp_group:
            context['corp_group'] = corp_group
            context['is_corp_owner'] = corp_group.subscriber_id == self.object.pk
            
        can_view_phone = has_permission(self.request.user, "clients.view_phone")
        context['today'] = date.today()
        context.update(
            client_form_context(client=self.object, can_view_phone=can_view_phone)
        )
        return context


class EditClientView(PermissionRequiredMixin, View):
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        client = get_object_or_404(Client, codigo_afiliado=kwargs["codigo_afiliado"])
        required = _edit_permission_for_client(client)
        if not has_permission(request.user, required):
            raise PermissionDenied(self.permission_denied_message)
        return View.dispatch(self, request, *args, **kwargs)

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
        return redirect(
            reverse(
                get_person_profile_url_name(client),
                kwargs={"codigo_afiliado": codigo_afiliado},
            )
        )


class UpdateProfileNoteView(PermissionRequiredMixin, View):
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        client = get_object_or_404(Client, codigo_afiliado=kwargs["codigo_afiliado"])
        required = _profile_note_edit_permission(client)
        if not required or not has_permission(request.user, required):
            raise PermissionDenied(self.permission_denied_message)
        return View.dispatch(self, request, *args, **kwargs)

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        profile_url = reverse(
            get_person_profile_url_name(client),
            kwargs={"codigo_afiliado": codigo_afiliado},
        )

        if not (client.is_member or client.is_guest):
            messages.error(request, "Solo se puede guardar nota en afiliados o invitados.")
            return redirect(profile_url)

        try:
            update_profile_note(client, request.POST.get("profile_note"))
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            messages.error(request, message)
            return redirect(profile_url)

        if client.profile_note:
            messages.success(request, "Nota de perfil actualizada.")
        else:
            messages.success(request, "Nota de perfil eliminada.")
        return redirect(profile_url)


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
        if not client.is_member:
            return redirect(
                reverse(
                    "staff_persons:profile",
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

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


class ToggleBlockClientView(PermissionRequiredMixin, View):
    required_permission = "clients.block"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if client.is_blocked:
            client.is_blocked = False
            client.blocking_reason = ""
            messages.success(request, f"Acceso desbloqueado para {client.nombre}.")
        else:
            client.is_blocked = True
            client.blocking_reason = request.POST.get("blocking_reason", "").strip()
            messages.warning(request, f"Acceso bloqueado para {client.nombre}.")
        
        client.save(update_fields=["is_blocked", "blocking_reason"])
        return redirect("clients:profile", codigo_afiliado=codigo_afiliado)


class ClientGrantAdminAccessView(PermissionRequiredMixin, View):
    required_permission = "clients.grant_admin_access"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        profile_url = reverse(
            "clients:profile",
            kwargs={"codigo_afiliado": codigo_afiliado},
        )

        if not client.is_member:
            messages.error(request, "Solo se puede asignar acceso administrativo a afiliados.")
            return redirect(
                reverse(
                    get_person_profile_url_name(client),
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

        if request.POST.get("confirm_admin_access") != "1":
            messages.error(
                request,
                "Debes confirmar que entiendes que se eliminarán membresías anteriores y no se generará cobro.",
            )
            return redirect(profile_url)

        plan_id = (request.POST.get("plan_id") or "").strip()
        plan = Plan.objects.filter(
            pk=plan_id,
            is_active=True,
            billing_type=Plan.BillingType.FIXED,
        ).first()
        if not plan:
            messages.error(request, "Seleccione un plan fijo activo.")
            return redirect(profile_url)

        valid_until = parse_date((request.POST.get("valid_until") or "").strip())
        if not valid_until:
            messages.error(request, "Indique la fecha de vigencia.")
            return redirect(profile_url)

        try:
            membership = grant_admin_access(client, plan, valid_until, request.user)
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            messages.error(request, message)
            return redirect(profile_url)

        cut_day = membership.client.fecha_corte_dia
        messages.success(
            request,
            "Acceso administrativo asignado con plan {} hasta el {} (sin cobro). "
            "Fecha de corte realineada al día {}.".format(
                plan.nombre,
                membership.fecha_fin.strftime("%d/%m/%Y"),
                cut_day,
            ),
        )
        return redirect(profile_url)


class ReEnrollClientView(PermissionRequiredMixin, View):
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        client = get_object_or_404(Client, codigo_afiliado=kwargs["codigo_afiliado"])
        required = _edit_permission_for_client(client)
        if not has_permission(request.user, required):
            raise PermissionDenied(self.permission_denied_message)
        return View.dispatch(self, request, *args, **kwargs)

    def get(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        return render(request, "clients/re_enrollment.html", {"client": client})

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        foto_frente_b64 = request.POST.get("foto_frente_base64")
        wants_json = request.headers.get("X-Reenroll-Submit") == "1"
        profile_url = reverse(
            get_person_profile_url_name(client),
            kwargs={"codigo_afiliado": client.codigo_afiliado},
        )

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
        return redirect(profile_url)


class StaffPersonListView(PermissionRequiredMixin, ListView):
    required_permission = "staff_persons.view_list"
    model = Client
    template_name = "clients/staff_person_list.html"
    context_object_name = "staff_persons"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Client.objects.filter(person_category__in=STAFF_PERSON_CATEGORIES)
            .order_by("-fecha_ingreso", "-id")
        )
        tipo = self.request.GET.get("tipo", "")
        if tipo in STAFF_LIST_TYPES:
            queryset = queryset.filter(person_category=STAFF_LIST_TYPES[tipo])
        q = self.request.GET.get("q", "")
        if q:
            queryset = queryset.filter(
                Q(cedula__icontains=q)
                | Q(codigo_afiliado__icontains=q)
                | Q(nombre__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["active_tipo"] = self.request.GET.get("tipo", "")
        return context


class StaffPersonProfileView(PermissionRequiredMixin, DetailView):
    required_permission = "staff_persons.view_profile"
    model = Client
    template_name = "clients/staff_person_profile.html"
    context_object_name = "client"
    slug_field = "codigo_afiliado"
    slug_url_kwarg = "codigo_afiliado"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_member:
            return redirect(
                reverse(
                    "clients:profile",
                    kwargs={"codigo_afiliado": self.object.codigo_afiliado},
                )
            )
        if self.object.is_guest:
            return redirect(
                reverse(
                    "guests:profile",
                    kwargs={"codigo_afiliado": self.object.codigo_afiliado},
                )
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoices"] = Invoice.objects.filter(client=self.object).order_by("-fecha_emision")[:10]
        context["access_logs"] = self.object.access_logs.all()[:20]
        can_view_phone = has_permission(self.request.user, "clients.view_phone")
        context.update(
            client_form_context(client=self.object, can_view_phone=can_view_phone)
        )
        return context


class StaffPersonDeleteView(PermissionRequiredMixin, View):
    required_permission = "staff_persons.delete"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if client.is_member:
            return redirect(
                reverse("clients:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )
        if client.is_guest:
            return redirect(
                reverse("guests:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )

        if request.POST.get("confirm_delete") != "1":
            messages.error(request, "Debes confirmar la eliminación.")
            return redirect(
                reverse("staff_persons:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )

        typed_code = (request.POST.get("confirm_codigo") or "").strip()
        if typed_code != client.codigo_afiliado:
            messages.error(request, "El código no coincide. No se eliminó el registro.")
            return redirect(
                reverse("staff_persons:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )

        nombre = client.nombre
        delete_client(client)
        messages.success(request, "Registro de {} eliminado.".format(nombre))
        return redirect("staff_persons:staff_list")


class GuestListRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        params = {"tipo": "invitados"}
        q = self.request.GET.get("q")
        if q:
            params["q"] = q
        return "{}?{}".format(reverse("clients:client_list"), urlencode(params))


class GuestRegisterRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return "{}?tipo=invitado".format(reverse("enrollment"))


class GuestProfileView(PermissionRequiredMixin, DetailView):
    required_permission = "guests.view_profile"
    model = Client
    template_name = "clients/guest_profile.html"
    context_object_name = "client"
    slug_field = "codigo_afiliado"
    slug_url_kwarg = "codigo_afiliado"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_guest:
            return redirect(
                reverse(
                    get_person_profile_url_name(self.object),
                    kwargs={"codigo_afiliado": self.object.codigo_afiliado},
                )
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_pass"] = get_active_guest_pass(self.object)
        context["guest_passes"] = (
            self.object.guest_passes.select_related("registered_by")
            .order_by("-created_at")
        )
        context["access_logs"] = self.object.access_logs.all()[:20]
        can_view_phone = has_permission(self.request.user, "clients.view_phone")
        context.update(
            client_form_context(client=self.object, can_view_phone=can_view_phone)
        )
        today = date.today()
        context["default_valid_from"] = today.isoformat()
        context["default_valid_until"] = (today + timedelta(days=1)).isoformat()
        context["today"] = today
        context["can_set_custom_pass_expiry"] = has_permission(
            self.request.user, "guests.set_custom_pass_expiry"
        )
        context["can_edit_profile_note"] = has_permission(
            self.request.user, "guests.register"
        )
        context["profile_note_max_length"] = PROFILE_NOTE_MAX_LENGTH
        context["profile_note_form_url"] = reverse(
            "guests:update_profile_note",
            kwargs={"codigo_afiliado": self.object.codigo_afiliado},
        )
        return context


class GuestIssuePassView(PermissionRequiredMixin, View):
    required_permission = "guests.register"

    def post(self, request, codigo_afiliado):
        guest = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if not guest.is_guest:
            return redirect(
                reverse(
                    get_person_profile_url_name(guest),
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

        if get_active_guest_pass(guest):
            messages.error(
                request,
                "Este invitado ya tiene un pase activo. Revóquelo o espere a que venza antes de emitir otro.",
            )
            return redirect("guests:profile", codigo_afiliado=codigo_afiliado)

        pass_errors, pass_cleaned = validate_guest_pass_dates(
            request.POST.get("valid_from"),
            request.POST.get("valid_until"),
            allow_custom_expiry=has_permission(
                request.user, "guests.set_custom_pass_expiry"
            ),
            custom_mode=guest_pass_custom_mode_enabled(request.POST.get("guest_pass_custom")),
        )
        sponsor_id = (request.POST.get("sponsor_id") or "").strip()
        sponsor = None
        if sponsor_id:
            sponsor = Client.objects.filter(
                pk=sponsor_id,
                person_category=PersonCategory.MEMBER,
            ).first()
        if sponsor is None:
            active = get_active_guest_pass(guest)
            sponsor = active.sponsor if active and active.sponsor_id else None

        if pass_errors:
            messages.error(request, next(iter(pass_errors.values())))
            return redirect("guests:profile", codigo_afiliado=codigo_afiliado)

        notes = (request.POST.get("notes") or "").strip()
        issue_guest_pass(
            guest,
            sponsor,
            pass_cleaned["valid_from"],
            pass_cleaned["valid_until"],
            registered_by=request.user,
            notes=notes,
        )
        messages.success(request, "Nuevo pase de invitado registrado.")
        return redirect("guests:profile", codigo_afiliado=codigo_afiliado)


class GuestRevokePassView(PermissionRequiredMixin, View):
    required_permission = "guests.revoke_pass"

    def post(self, request, codigo_afiliado):
        guest = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if not guest.is_guest:
            return redirect(
                reverse(
                    get_person_profile_url_name(guest),
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

        pass_id = request.POST.get("pass_id")
        guest_pass = get_object_or_404(GuestPass, pk=pass_id, guest=guest)
        revoke_guest_pass(guest_pass)
        messages.success(request, "Pase de invitado revocado.")
        return redirect("guests:profile", codigo_afiliado=codigo_afiliado)


class GuestDeleteView(PermissionRequiredMixin, View):
    required_permission = "guests.delete"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if not client.is_guest:
            return redirect(
                reverse(
                    get_person_profile_url_name(client),
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

        if request.POST.get("confirm_delete") != "1":
            messages.error(request, "Debes confirmar la eliminación.")
            return redirect("guests:profile", codigo_afiliado=codigo_afiliado)

        typed_code = (request.POST.get("confirm_codigo") or "").strip()
        if typed_code != client.codigo_afiliado:
            messages.error(request, "El código no coincide. No se eliminó el registro.")
            return redirect("guests:profile", codigo_afiliado=codigo_afiliado)

        nombre = client.nombre
        delete_client(client)
        messages.success(request, "Registro de {} eliminado.".format(nombre))
        return redirect("{}?tipo=invitados".format(reverse("clients:client_list")))
