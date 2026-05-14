from django.urls import re_path

from . import consumers

# Patrones de URL para conexiones WebSocket entrantes.
# La tablet se conectará a: ws://<IP_SERVIDOR>:8000/ws/tablet/
websocket_urlpatterns = [
    re_path(r"^ws/tablet/$", consumers.TabletConsumer.as_asgi()),
    re_path(r"^ws/dashboard/$", consumers.DashboardConsumer.as_asgi()),
]
