from django.urls import path

from . import views

app_name = "stats"

urlpatterns = [
    path("", views.EntryHoursStatsView.as_view(), name="entry_hours"),
    path("entrada-por-hora/", views.EntryHoursStatsDataView.as_view(), name="entry_hours_data"),
]
