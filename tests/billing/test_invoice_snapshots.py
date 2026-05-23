import pytest
from apps.billing.models import Invoice
from apps.billing.services import register_membership_renewal


@pytest.mark.django_db
class TestInvoiceClientSnapshots:

    def test_new_invoice_stores_client_snapshots(self, sample_client, monthly_plan, current_rate):
        _, invoice = register_membership_renewal(sample_client, monthly_plan, "CTRL-SNAP")
        assert invoice.client_nombre_snapshot == sample_client.nombre
        assert invoice.client_cedula_snapshot == sample_client.cedula
        assert invoice.client_codigo_snapshot == sample_client.codigo_afiliado

    def test_invoice_survives_client_delete_without_relinking(self, sample_client, monthly_plan, current_rate):
        _, invoice = register_membership_renewal(sample_client, monthly_plan, "CTRL-DEL")
        invoice_id = invoice.pk
        snapshot_nombre = sample_client.nombre
        snapshot_cedula = sample_client.cedula
        client_id = sample_client.pk

        sample_client.delete()

        invoice = Invoice.objects.get(pk=invoice_id)
        assert invoice.client_id is None
        assert invoice.client_nombre_snapshot == snapshot_nombre
        assert invoice.client_cedula_snapshot == snapshot_cedula
        assert invoice.receptor_nombre == snapshot_nombre
        assert Invoice.objects.filter(client_id=client_id).count() == 0

    def test_recreated_client_does_not_inherit_old_invoices(self, sample_client, monthly_plan, current_rate, db):
        from apps.clients.models import Client

        _, old_invoice = register_membership_renewal(sample_client, monthly_plan, "CTRL-OLD")
        old_invoice_id = old_invoice.pk
        cedula = sample_client.cedula
        nombre = sample_client.nombre
        sample_client.delete()

        new_client = Client.objects.create(
            cedula=cedula,
            nombre=nombre,
            codigo_afiliado="M-99999-99",
        )
        _, new_invoice = register_membership_renewal(new_client, monthly_plan, "CTRL-NEW")

        assert new_invoice.client_id == new_client.pk
        assert Invoice.objects.filter(client=new_client).count() == 1
        assert Invoice.objects.get(pk=old_invoice_id).client_id is None
