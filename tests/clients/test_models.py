import pytest
from django.db import IntegrityError
from apps.clients.models import Client

@pytest.mark.django_db
class TestClientModel:
    def test_client_creation(self, sample_client):
        """Validar que un cliente se crea correctamente."""
        assert sample_client.nombre == "Juan Perez"
        assert str(sample_client) == "Juan Perez (M-00001-01)"

    def test_unique_cedula(self, sample_client):
        """No permitir duplicados de cédula."""
        with pytest.raises(IntegrityError):
            Client.objects.create(
                nombre="Otro Juan",
                cedula="V-12345678", # Misma cédula
                codigo_afiliado="M-00002-01"
            )

    def test_unique_codigo_afiliado(self, sample_client):
        """No permitir duplicados de código legacy."""
        with pytest.raises(IntegrityError):
            Client.objects.create(
                nombre="Otro Juan",
                cedula="V-87654321",
                codigo_afiliado="M-00001-01" # Mismo código
            )
