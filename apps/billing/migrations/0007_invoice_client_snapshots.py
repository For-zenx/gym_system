from django.db import migrations, models
import django.db.models.deletion


def backfill_client_snapshots(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    for invoice in Invoice.objects.select_related('client', 'membership__client').iterator():
        if invoice.client_nombre_snapshot:
            continue
        source = invoice.client
        if not source and invoice.membership_id:
            membership = invoice.membership
            if membership:
                source = membership.client
        if not source:
            continue
        invoice.client_nombre_snapshot = source.nombre
        invoice.client_cedula_snapshot = source.cedula
        invoice.client_codigo_snapshot = source.codigo_afiliado
        invoice.save(update_fields=[
            'client_nombre_snapshot',
            'client_cedula_snapshot',
            'client_codigo_snapshot',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_invoice_client_invoice_plan_snapshot_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='client_nombre_snapshot',
            field=models.CharField(blank=True, max_length=255, verbose_name='Nombre del Receptor'),
        ),
        migrations.AddField(
            model_name='invoice',
            name='client_cedula_snapshot',
            field=models.CharField(blank=True, max_length=20, verbose_name='Cédula del Receptor'),
        ),
        migrations.AddField(
            model_name='invoice',
            name='client_codigo_snapshot',
            field=models.CharField(blank=True, max_length=20, verbose_name='Cód. Afiliado (snapshot)'),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='client',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoices',
                to='clients.client',
                verbose_name='Afiliado',
            ),
        ),
        migrations.RunPython(backfill_client_snapshots, migrations.RunPython.noop),
    ]
