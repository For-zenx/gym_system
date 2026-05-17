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
        membership, created = Membership.objects.get_or_create(
            client=client,
            defaults={'plan': plan, 'fecha_inicio': timezone.localdate()}
        )

        hoy = timezone.localdate()
        
        if not created:
            membership.plan = plan
            if membership.es_valida:
                membership.fecha_fin = membership.fecha_fin + timedelta(days=plan.dias_duracion)
            else:
                membership.fecha_inicio = hoy
                membership.fecha_fin = hoy + timedelta(days=plan.dias_duracion)
        
        membership.save()

        invoice = Invoice.objects.create(
            membership=membership,
            monto_total=monto_ves,
            nro_control=nro_control or "PENDING"
        )
        
        if not nro_control:
            invoice.nro_control = f"F-{timezone.now().strftime('%Y%m%d')}-{invoice.pk:05d}"
            invoice.save(update_fields=['nro_control'])

        return membership, invoice
