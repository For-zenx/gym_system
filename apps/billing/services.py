from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import Membership, Invoice, ExchangeRate

def register_membership_renewal(client, plan, nro_control=None, monto_ves=None):
    """
    Registra administrativamente la renovación.
    Si monto_ves es None, lo calcula usando la tasa más reciente.
    """
    if monto_ves is None:
        tasa = ExchangeRate.get_latest()
        if not tasa:
            raise ValidationError("No hay una tasa de cambio registrada en el sistema.")
        monto_ves = plan.precio_usd * tasa.tasa_ves

    with transaction.atomic():
        hoy = timezone.localdate()
        fecha_inicio_nueva = hoy
        
        latest_membership = client.memberships.order_by('-fecha_fin').first()
        if latest_membership and latest_membership.fecha_fin >= hoy:
            fecha_inicio_nueva = latest_membership.fecha_fin + timedelta(days=1)
            
        membership = Membership.objects.create(
            client=client,
            plan=plan,
            fecha_inicio=fecha_inicio_nueva
        )

        invoice = Invoice(
            client=client,
            membership=membership,
            plan_snapshot=f"{plan.nombre} ({plan.dias_duracion} días)",
            monto_total=monto_ves,
            nro_control=nro_control or "PENDING",
        )
        invoice.set_client_snapshots(client)
        invoice.save()
        
        if not nro_control:
            invoice.nro_control = f"F-{timezone.now().strftime('%Y%m%d')}-{invoice.pk:05d}"
            invoice.save(update_fields=['nro_control'])

        return membership, invoice
