import pytest
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.billing.models import Membership, Plan, Invoice
from apps.access.models import AccessLog
from datetime import timedelta

@pytest.mark.django_db
class TestBillingIntegrity:
    
    def test_plan_protection(self, monthly_plan, sample_client):
        Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=timezone.localdate()
        )
        with pytest.raises(models.ProtectedError):
            monthly_plan.delete()

    def test_invoice_immutable_if_printed(self, sample_client, monthly_plan, current_rate):
        """Validar que una factura impresa queda bloqueada para edición."""
        invoice, created = Invoice.objects.get_or_create(
            membership=Membership.objects.create(client=sample_client, plan=monthly_plan),
            defaults={'monto_total': 1500.00, 'nro_control': 'FISCAL-001', 'esta_impresa': True}
        )
        
        invoice.monto_total = 2000.00
        with pytest.raises(ValidationError) as excinfo:
            invoice.full_clean()
        assert "No se puede editar una factura que ya ha sido impresa" in str(excinfo.value)
