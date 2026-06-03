import logging

from django.db.models import Q
from django.shortcuts import render
from django.views.generic import ListView

from apps.users.mixins import PermissionRequiredMixin

from .models import AccessLog

logger = logging.getLogger(__name__)


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


# DEPRECATED: TASK-045 — reemplazado por tablet_access_view (una sola tablet dual-mode).
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
