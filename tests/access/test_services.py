import pytest
from apps.access.services import check_access_integrity
from apps.access.models import AccessLog
from apps.billing.models import Membership
from datetime import date, timedelta

@pytest.mark.django_db
class TestAccessServices:
    
    def test_check_access_no_membership(self, sample_client):
        """Validar denegación para clientes sin membresía."""
        allowed, reason = check_access_integrity(sample_client)
        assert allowed is False
        assert reason == "Sin membresía"
        assert AccessLog.objects.filter(client=sample_client, resultado=False).exists()

    def test_check_access_expired(self, sample_client, monthly_plan):
        """Validar denegación para clientes vencidos."""
        Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=date.today() - timedelta(days=40),
            fecha_fin=date.today() - timedelta(days=10)
        )
        allowed, reason = check_access_integrity(sample_client)
        assert allowed is False
        assert "vencid" in reason.lower()

    def test_check_access_success(self, sample_client, monthly_plan):
        """Validar éxito para clientes vigentes."""
        Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=30)
        )
        allowed, reason = check_access_integrity(sample_client)
        assert allowed is True
        assert reason == "OK"
        assert AccessLog.objects.filter(client=sample_client, resultado=True).exists()
