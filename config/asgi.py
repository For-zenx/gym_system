"""
ASGI config for gym_system project.

Enruta el tráfico HTTP normal hacia Django y el tráfico WebSocket
(ws://) hacia los consumidores de Django Channels.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# En produccion la licencia es obligatoria; en desarrollo local no.
from config.licencia import verify_license_if_required
verify_license_if_required()

django_asgi_app = get_asgi_application()

# Importar rutas WS despues de inicializar Django evita AppRegistryNotReady.
import apps.access.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,

    "websocket": AllowedHostsOriginValidator(
        URLRouter(
            apps.access.routing.websocket_urlpatterns
        )
    ),
})
