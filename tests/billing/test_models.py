import pytest
from datetime import date, timedelta
from apps.billing.models import Membership

@pytest.mark.django_db
class TestBillingLogic:
    def test_membership_expiration_calculation_monthly(self, sample_client, monthly_plan):
        """Validar que un plan de 30 días calcula correctamente el vencimiento."""
        start_date = date.today()
        membership = Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=start_date
        )
        
        expected_end_date = start_date + timedelta(days=30)
        assert membership.fecha_fin == expected_end_date
        assert membership.es_valida is True

    def test_membership_expiration_calculation_daily(self, sample_client, daily_plan):
        """Validar que un plan de 1 día vence mañana."""
        start_date = date.today()
        # Borrar si existe para evitar conflictos de OneToOne
        if hasattr(sample_client, 'membership'):
            sample_client.membership.delete() 
        
        membership = Membership.objects.create(
            client=sample_client,
            plan=daily_plan,
            fecha_inicio=start_date
        )
        
        expected_end_date = start_date + timedelta(days=1)
        assert membership.fecha_fin == expected_end_date

    def test_es_valida_property(self, sample_client, monthly_plan):
        """Validar que la propiedad es_valida detecta vencimientos."""
        start_date = date.today() - timedelta(days=31) # Hace 31 días
        if hasattr(sample_client, 'membership'):
            sample_client.membership.delete()
        
        membership = Membership.objects.create(
            client=sample_client,
            plan=monthly_plan,
            fecha_inicio=start_date
        )
        # Forzar fecha_fin para simular pasado
        membership.fecha_fin = start_date + timedelta(days=30)
        membership.save()
        
        assert membership.es_valida is False
