import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.billing.services import register_membership_renewal
from apps.billing.models import Membership, Invoice
from datetime import timedelta

@pytest.mark.django_db
class TestBillingServices:
    
    def test_register_renewal_with_auto_rate(self, sample_client, monthly_plan, current_rate):
        """Validar cálculo automático: 30 USD * 50 VES = 1500 VES."""
        membership, invoice = register_membership_renewal(
            sample_client, monthly_plan, "CTRL-001"
        )
        assert float(invoice.monto_total) == 1500.00
        # localdate() es el estándar de Django para obtener la fecha "hoy" según el TIME_ZONE
        hoy = timezone.localdate()
        assert membership.fecha_fin == hoy + timedelta(days=30)

    def test_register_renewal_manual_override(self, sample_client, monthly_plan, current_rate):
        """Validar que el dueño puede sobreescribir el monto antes de imprimir."""
        membership, invoice = register_membership_renewal(
            sample_client, monthly_plan, "CTRL-002", monto_ves=1400.00
        )
        assert float(invoice.monto_total) == 1400.00
        assert invoice.esta_impresa is False

    def test_register_renewal_no_rate_error(self, sample_client, monthly_plan):
        """Validar que falla si no hay tasa cargada."""
        with pytest.raises(ValidationError) as excinfo:
            register_membership_renewal(sample_client, monthly_plan, "CTRL-999")
        assert "No hay una tasa de cambio" in str(excinfo.value)
