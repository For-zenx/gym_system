from django.urls import path

from .views import (
    ClassAttendanceView,
    ClassCheckoutView,
    ClassMemberSearchView,
    ClassRegistrationAddView,
    ClassRegistrationCancelView,
    ClassSessionCancelView,
    ClassSessionCreateView,
    ClassSessionDetailView,
    ClassSessionListView,
    ClassSessionUpdateView,
)

app_name = "classes"

urlpatterns = [
    path("", ClassSessionListView.as_view(), name="session_list"),
    path("nueva/", ClassSessionCreateView.as_view(), name="session_create"),
    path("<int:pk>/", ClassSessionDetailView.as_view(), name="session_detail"),
    path("<int:pk>/editar/", ClassSessionUpdateView.as_view(), name="session_update"),
    path("<int:pk>/cancelar/", ClassSessionCancelView.as_view(), name="session_cancel"),
    path("<int:pk>/asistencia/", ClassAttendanceView.as_view(), name="session_attendance"),
    path(
        "<int:pk>/inscripciones/agregar/",
        ClassRegistrationAddView.as_view(),
        name="registration_add",
    ),
    path(
        "inscripciones/<int:pk>/cancelar/",
        ClassRegistrationCancelView.as_view(),
        name="registration_cancel",
    ),
    path("buscar-afiliados/", ClassMemberSearchView.as_view(), name="member_search"),
    path(
        "cobro/<int:registration_id>/",
        ClassCheckoutView.as_view(),
        name="class_checkout",
    ),
]
