from django.urls import path
from .views import (
    BulkDeleteInactiveClientsView,
    ClientProfileView,
    ClientDeleteView,
    EditClientView,
    ClientListView,
    InactiveClientsPreviewView,
    ReEnrollClientView,
)

app_name = 'clients'

urlpatterns = [
    path('', ClientListView.as_view(), name='client_list'),
    path('inactivos/vista-previa/', InactiveClientsPreviewView.as_view(), name='inactive_clients_preview'),
    path('inactivos/eliminar/', BulkDeleteInactiveClientsView.as_view(), name='inactive_clients_bulk_delete'),
    path('<str:codigo_afiliado>/', ClientProfileView.as_view(), name='profile'),
    path('<str:codigo_afiliado>/editar/', EditClientView.as_view(), name='edit_client'),
    path('<str:codigo_afiliado>/re-enrolar/', ReEnrollClientView.as_view(), name='re_enroll'),
    path('<str:codigo_afiliado>/eliminar/', ClientDeleteView.as_view(), name='delete_client'),
]
