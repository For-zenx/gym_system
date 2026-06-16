from django.urls import path

from .views import LockerCreateView, LockerListView, LockerReleaseView, LockerUpdateView

app_name = "lockers"

urlpatterns = [
    path("", LockerListView.as_view(), name="locker_list"),
    path("nuevo/", LockerCreateView.as_view(), name="locker_create"),
    path("<int:pk>/editar/", LockerUpdateView.as_view(), name="locker_update"),
    path("<int:pk>/liberar/", LockerReleaseView.as_view(), name="locker_release"),
]
