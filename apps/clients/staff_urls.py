from django.urls import path

from .views import (
    ReEnrollClientView,
    StaffPersonDeleteView,
    StaffPersonListView,
    StaffPersonProfileView,
)

app_name = "staff_persons"

urlpatterns = [
    path("", StaffPersonListView.as_view(), name="staff_list"),
    path("<str:codigo_afiliado>/", StaffPersonProfileView.as_view(), name="profile"),
    path("<str:codigo_afiliado>/re-enrolar/", ReEnrollClientView.as_view(), name="re_enroll"),
    path("<str:codigo_afiliado>/eliminar/", StaffPersonDeleteView.as_view(), name="delete"),
]
