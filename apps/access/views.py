from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.clients.models import Client
from apps.users.mixins import PermissionRequiredMixin

from .forms import TurnstileControlForm
from .hardware import open_turnstile
from .models import AccessLog, ManualTurnstileAccess
from .services import evaluate_access_integrity


def _tablet_ws_url(request, path):
    ws_scheme = "wss" if request.is_secure() else "ws"
    return f"{ws_scheme}://{request.get_host()}{path}"


def tablet_access_view(request):
    return render(request, "tablet_access.html", {
        "ws_url": _tablet_ws_url(request, "/ws/tablet/acceso/"),
    })


def tablet_enrollment_view(request):
    return render(request, "tablet_enrollment.html", {
        "ws_url": _tablet_ws_url(request, "/ws/tablet/enrolamiento/"),
    })


def tablet_enrolamiento_acceso_view(request):
    """Una sola tablet: acceso por defecto; enrolamiento al comando de la PC."""
    return render(request, "tablet_enrolamiento_acceso.html", {
        "ws_url": _tablet_ws_url(request, "/ws/tablet/enrolamiento_acceso/"),
    })


# DEPRECATED: TASK-045 — /tablet/ redirige a acceso; usar tablet_enrolamiento_acceso_view para 1 dispositivo.
def tablet_view(request):
    return tablet_access_view(request)


class AccessLogListView(PermissionRequiredMixin, ListView):
    required_permission = "access.view_logs"
    model = AccessLog
    template_name = 'access/access_log_list.html'
    context_object_name = 'logs'
    paginate_by = 15

    def get_queryset(self):
        queryset = AccessLog.objects.select_related(
            'client'
        ).all()

        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(client__nombre__icontains=q) |
                Q(client__cedula__icontains=q) |
                Q(client__codigo_afiliado__icontains=q)
            )

        resultado = self.request.GET.get('resultado', '')
        if resultado == 'concedido':
            queryset = queryset.filter(resultado=True)
        elif resultado == 'denegado':
            queryset = queryset.filter(resultado=False)

        fecha = self.request.GET.get('fecha', '').strip()
        if fecha:
            queryset = queryset.filter(timestamp__date=fecha)

        return queryset


class ManualTurnstileAccessListView(PermissionRequiredMixin, ListView):
    required_permission = "access.view_logs"
    model = ManualTurnstileAccess
    template_name = "access/manual_access_list.html"
    context_object_name = "accesses"
    paginate_by = 20

    def get_queryset(self):
        queryset = ManualTurnstileAccess.objects.select_related(
            "client", "opened_by", "opened_by__staff_profile"
        ).all()

        q = self.request.GET.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(person_name__icontains=q)
                | Q(client__nombre__icontains=q)
                | Q(client__cedula__icontains=q)
                | Q(client__codigo_afiliado__icontains=q)
                | Q(custom_reason__icontains=q)
            )

        fecha = self.request.GET.get("fecha", "").strip()
        if fecha:
            queryset = queryset.filter(timestamp__date=fecha)

        return queryset


class QuickTurnstileOpenView(PermissionRequiredMixin, View):
    required_permission = "access.open_turnstile"

    def post(self, request, *args, **kwargs):
        reason = request.POST.get("reason", ManualTurnstileAccess.Reason.UNSPECIFIED)
        custom_reason = request.POST.get("custom_reason", "").strip()
        person_name = (request.POST.get("person_name") or "").strip()
        client_id = (request.POST.get("client_id") or "").strip()
        allow_unidentified = reason == ManualTurnstileAccess.Reason.UNSPECIFIED

        client = None
        membership_warning = ""

        if client_id:
            try:
                client = Client.objects.get(pk=int(client_id))
            except (Client.DoesNotExist, ValueError, TypeError):
                return JsonResponse(
                    {"success": False, "error": "La persona seleccionada ya no existe."},
                    status=400,
                )
            person_name = client.nombre
            granted, detail = evaluate_access_integrity(client)
            if not granted:
                membership_warning = detail
        elif not person_name:
            if allow_unidentified:
                person_name = "Sin identificar"
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Seleccione una persona o indique el nombre.",
                    },
                    status=400,
                )

        if reason == ManualTurnstileAccess.Reason.OTHER and not custom_reason:
            return JsonResponse(
                {"success": False, "error": "Debe especificar el motivo."}, status=400
            )

        hardware_result = open_turnstile()

        ManualTurnstileAccess.objects.create(
            client=client,
            person_name=person_name,
            reason=reason,
            custom_reason=custom_reason,
            opened_by=request.user,
            hardware_success=hardware_result.success,
            hardware_error=hardware_result.message,
            membership_warning=membership_warning,
            port_used=hardware_result.port,
        )

        if hardware_result.success:
            return JsonResponse({"success": True, "message": "Torniquete abierto."})
        return JsonResponse(
            {"success": False, "error": hardware_result.message}, status=500
        )


class TurnstileClientSearchView(PermissionRequiredMixin, View):
    required_permission = "access.open_turnstile"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"results": []})

        clients = (
            Client.objects.filter(
                Q(cedula__icontains=query)
                | Q(codigo_afiliado__icontains=query)
                | Q(nombre__icontains=query)
            )
            .order_by("nombre")[:8]
        )

        results = []
        for client in clients:
            granted, detail = evaluate_access_integrity(client)
            results.append({
                "id": client.pk,
                "nombre": client.nombre,
                "cedula": client.cedula or "",
                "codigo_afiliado": client.codigo_afiliado,
                "photo_url": client.foto_frente.url if client.foto_frente else "",
                "access_warning": "" if granted else detail,
            })

        return JsonResponse({"results": results})


class TurnstileControlView(PermissionRequiredMixin, View):
    required_permission = "access.open_turnstile"
    template_name = "access/turnstile_control.html"

    def get(self, request, *args, **kwargs):
        return render(
            request,
            self.template_name,
            self._build_context(form=TurnstileControlForm()),
        )

    def post(self, request, *args, **kwargs):
        form = TurnstileControlForm(request.POST)

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._build_context(form=form, restore_form=True),
            )

        client = form.cleaned_data["client"]
        person_name = form.cleaned_data["person_name"]
        membership_warning = ""

        if client:
            granted, detail = evaluate_access_integrity(client)
            if not granted:
                membership_warning = detail

        hardware_result = open_turnstile()
        ManualTurnstileAccess.objects.create(
            client=client,
            person_name=person_name,
            reason=form.cleaned_data["reason"],
            custom_reason=form.cleaned_data["custom_reason"],
            opened_by=request.user,
            hardware_success=hardware_result.success,
            hardware_error=hardware_result.message,
            membership_warning=membership_warning,
            port_used=hardware_result.port,
        )

        if hardware_result.success:
            messages.success(request, "El torniquete se abrió correctamente.")
        else:
            messages.error(request, hardware_result.message)

        return redirect("access:turnstile_control")

    def _build_context(self, form, restore_form=False):
        selected_client = None
        client_access_warning = ""
        guest_mode = False

        if restore_form:
            client_pk = form["client_id"].value()
            if client_pk:
                selected_client = Client.objects.filter(pk=client_pk).first()
                if selected_client:
                    granted, detail = evaluate_access_integrity(selected_client)
                    if not granted:
                        client_access_warning = detail
            elif form["person_name"].value():
                guest_mode = True

        return {
            "form": form,
            "selected_client": selected_client,
            "guest_mode": guest_mode,
            "client_access_warning": client_access_warning,
            "restore_form": restore_form,
            "recent_accesses": ManualTurnstileAccess.objects.select_related(
                "client",
                "opened_by",
                "opened_by__staff_profile",
            )[:12],
            "turnstile_configured": bool((settings.TURNSTILE_COM_PORT or "").strip()),
            "search_url": reverse("access:turnstile_client_search"),
            "reason_other": ManualTurnstileAccess.Reason.OTHER,
        }
