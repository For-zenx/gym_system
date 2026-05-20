import logging

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import AccessLog

logger = logging.getLogger(__name__)


def tablet_view(request):
    """
    Protegida por token de dispositivo — no requiere login de usuario.
    """
    token = request.GET.get("token", "")
    if token != settings.TABLET_TOKEN:
        logger.warning("Intento de acceso a /tablet/ con token inválido: '%s' desde %s", token, request.META.get("REMOTE_ADDR"))
        return HttpResponseForbidden("Acceso denegado.")

    ws_scheme = "wss" if request.is_secure() else "ws"
    ws_url = f"{ws_scheme}://{request.get_host()}/ws/tablet/"

    return render(request, "tablet.html", {"ws_url": ws_url})


class AccessLogListView(LoginRequiredMixin, ListView):
    model = AccessLog
    template_name = 'access/access_log_list.html'
    context_object_name = 'logs'
    paginate_by = 15

    def get_queryset(self):
        queryset = AccessLog.objects.select_related(
            'client', 'client__membership'
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
