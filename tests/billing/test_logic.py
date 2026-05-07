import pytest
from django.db import models
from django.core.exceptions import ValidationError
from apps.billing.models import Membership, Plan, Invoice
from apps.access.models import AccessLog
from datetime import date, timedelta

@pytest.mark.django_db
class TestBillingIntegrity:
    
    def test_plan_protection(self, monthly_plan, sample_client):
        """Validar que un plan no se puede borrar si tiene una membresía asociada (PROTECT)."""
        Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=date.today()
        )
        
        # Al intentar borrar el plan, debe lanzar ProtectedError
        with pytest.raises(models.ProtectedError):
            monthly_plan.delete()

    def test_membership_date_validation(self, sample_client, monthly_plan):
        """Validar que el método clean bloquea fechas inválidas."""
        if hasattr(sample_client, 'membership'):
            sample_client.membership.delete()
            
        membership = Membership(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=date.today(),
            fecha_fin=date.today() - timedelta(days=1)
        )
        
        with pytest.raises(ValidationError):
            membership.clean()
            membership.save()

    def test_access_log_creation(self, sample_client):
        """Validar registro de acceso."""
        log = AccessLog.objects.create(
            client=sample_client,
            resultado=False,
            motivo="Prueba de denegación"
        )
        assert log.id is not None
        assert "DENEGADO" in str(log)

    def test_invoice_creation(self, sample_client, monthly_plan):
        """Validar creación de factura vinculada a membresía."""
        if hasattr(sample_client, 'membership'):
            sample_client.membership.delete()
            
        m = Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=date.today()
        )
        
        invoice = Invoice.objects.create(
            membership=m,
            monto_total=monthly_plan.precio,
            nro_control="FISCAL-001"
        )
        assert invoice.id is not None
        assert invoice.monto_total == monthly_plan.precio
