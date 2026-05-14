import logging

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import render

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

