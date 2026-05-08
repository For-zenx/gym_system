import pytest
from decimal import Decimal
from apps.clients.models import Client
from apps.billing.models import Plan, ExchangeRate

@pytest.fixture
def sample_client(db):
    return Client.objects.create(
        nombre="Juan Perez",
        cedula="V-12345678",
        codigo_afiliado="M-00001-01",
        telefono="0412-0000000"
    )

@pytest.fixture
def monthly_plan(db):
    return Plan.objects.create(
        nombre="Mensual",
        dias_duracion=30,
        precio_usd=Decimal("30.00")
    )

@pytest.fixture
def daily_plan(db):
    return Plan.objects.create(
        nombre="Diario",
        dias_duracion=1,
        precio_usd=Decimal("2.00")
    )

@pytest.fixture
def current_rate(db):
    """Tasa de cambio de prueba: 1 USD = 50 VES."""
    return ExchangeRate.objects.create(
        tasa_ves=Decimal("50.0000")
    )
