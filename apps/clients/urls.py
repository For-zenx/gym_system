from django.urls import path
from .views import ClientProfileView, EditClientView

app_name = 'clients'

urlpatterns = [
    path('<str:codigo_afiliado>/', ClientProfileView.as_view(), name='profile'),
    path('<str:codigo_afiliado>/editar/', EditClientView.as_view(), name='edit_client'),
]
