from django.urls import path

from .views import (
    ConfigHomeView,
    RoleCreateView,
    RoleDeleteView,
    RoleListView,
    RoleUpdateView,
    StaffUserCreateView,
    StaffUserListView,
    StaffUserUpdateView,
)

app_name = "users"

urlpatterns = [
    path("", ConfigHomeView.as_view(), name="config_home"),
    path("plantillas/", RoleListView.as_view(), name="role_list"),
    path("plantillas/nueva/", RoleCreateView.as_view(), name="role_create"),
    path("plantillas/<int:pk>/editar/", RoleUpdateView.as_view(), name="role_update"),
    path("plantillas/<int:pk>/eliminar/", RoleDeleteView.as_view(), name="role_delete"),
    path("usuarios/", StaffUserListView.as_view(), name="staff_user_list"),
    path("usuarios/nuevo/", StaffUserCreateView.as_view(), name="staff_user_create"),
    path("usuarios/<int:pk>/editar/", StaffUserUpdateView.as_view(), name="staff_user_update"),
]
