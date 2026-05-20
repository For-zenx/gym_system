from django.urls import path
from .views import AccessLogListView

app_name = 'access'

urlpatterns = [
    path('', AccessLogListView.as_view(), name='access_log_list'),
]
