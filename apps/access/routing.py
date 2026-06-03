from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/tablet/acceso/$", consumers.AccessTabletConsumer.as_asgi()),
    re_path(r"^ws/tablet/enrolamiento/$", consumers.EnrollmentTabletConsumer.as_asgi()),
    re_path(r"^ws/dashboard/$", consumers.DashboardConsumer.as_asgi()),
]
