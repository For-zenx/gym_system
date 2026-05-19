from django.urls import path
from .views import ClientProfileView, EditClientView, ClientListView

app_name = 'clients'

urlpatterns = [
    path('', ClientListView.as_view(), name='client_list'),
    path('<str:codigo_afiliado>/', ClientProfileView.as_view(), name='profile'),
    path('<str:codigo_afiliado>/editar/', EditClientView.as_view(), name='edit_client'),
]
