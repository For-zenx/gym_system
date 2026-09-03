# Data migration: backfill Membership status / corte snapshot for existing rows.

from django.db import migrations
from django.utils import timezone


def forwards_backfill_membership_history(apps, schema_editor):
    Membership = apps.get_model("billing", "Membership")
    today = timezone.localdate()
    for mem in Membership.objects.select_related("client").iterator():
        if mem.fecha_inicio and mem.fecha_fin:
            if mem.fecha_inicio <= today <= mem.fecha_fin:
                status = "ACTIVE"
            elif mem.fecha_inicio > today:
                status = "QUEUED"
            else:
                status = "EXPIRED"
        else:
            status = "EXPIRED"
        cut = None
        if mem.client_id and getattr(mem.client, "fecha_corte_dia", None):
            cut = mem.client.fecha_corte_dia
        Membership.objects.filter(pk=mem.pk).update(
            status=status,
            fecha_corte_dia=cut,
            origen="UNKNOWN",
        )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0029_membership_history_status"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_membership_history, backwards_noop),
    ]
