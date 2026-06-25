from django.urls import path

from .views import (
    GuestDeleteView,
    GuestIssuePassView,
    GuestListRedirectView,
    GuestProfileView,
    GuestRegisterRedirectView,
    GuestRevokePassView,
)

app_name = "guests"

urlpatterns = [
    path("", GuestListRedirectView.as_view(), name="guest_list"),
    path("registro/", GuestRegisterRedirectView.as_view(), name="register"),
    path("<str:codigo_afiliado>/", GuestProfileView.as_view(), name="profile"),
    path("<str:codigo_afiliado>/nuevo-pase/", GuestIssuePassView.as_view(), name="issue_pass"),
    path("<str:codigo_afiliado>/revocar-pase/", GuestRevokePassView.as_view(), name="revoke_pass"),
    path("<str:codigo_afiliado>/eliminar/", GuestDeleteView.as_view(), name="delete"),
]
