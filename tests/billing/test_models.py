import pytest
from django.utils import timezone
from apps.billing.models import Plan, Membership
from datetime import timedelta

@pytest.mark.django_db
class TestBillingModels:
    def test_plan_creation(self, monthly_plan):
        assert monthly_plan.nombre == "Mensual"
        assert float(monthly_plan.precio_usd) == 30.00

    def test_membership_creation(self, sample_client, monthly_plan):
        membership = Membership.objects.create(
            client=sample_client,
            plan=monthly_plan
        )
        hoy = timezone.localdate()
        assert membership.fecha_fin == hoy + timedelta(days=30)
