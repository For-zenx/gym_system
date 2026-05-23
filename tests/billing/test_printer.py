import os
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import date
from django.core.exceptions import ValidationError
from apps.billing.printer import (
    print_invoice,
    _build_ticket_lines,
    build_invoice_preview_lines,
    MAX_LINE_WIDTH,
    PREVIEW_FISCAL_NUMBER,
    PREVIEW_FISCAL_DATE,
    PREVIEW_FISCAL_TIME,
)
from apps.billing.models import Invoice, Membership
from apps.core.models import PrinterConfig


@pytest.mark.django_db
class TestPrinterService:

    def _create_invoice(self, client, monthly_plan, nro_control="TEST-001"):
        if hasattr(client, 'membership'):
            client.membership.delete()
        membership = Membership.objects.create(
            client=client,
            plan=monthly_plan,
            fecha_inicio=date.today()
        )
        return Invoice.objects.create(
            membership=membership,
            monto_total=monthly_plan.precio_usd,
            nro_control=nro_control
        )

    # --- Tests Originales ---

    def test_ticket_description_format(self, sample_client, monthly_plan):
        """Validar el formato exacto del tique replicando la factura real."""
        invoice = self._create_invoice(sample_client, monthly_plan)
        invoice.monto_total = Decimal("1000.00")
        invoice.save(update_fields=['monto_total'])
        lines = _build_ticket_lines(invoice)

        fecha_inicio = invoice.membership.fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin = invoice.membership.fecha_fin.strftime('%d/%m/%Y')
        amount = "Bs 1.000,00"

        text_lines = [content for kind, content in lines if kind == "text"]

        # Validar datos del cliente
        assert any("RIF/C.I.:" in l for l in text_lines)
        assert any("RAZON SOCIAL:" in l for l in text_lines)
        assert any("Cod. Afil.:" in l for l in text_lines)
        # Validar descripción con pipes
        assert any(f"|CUOTA {fecha_inicio} AL {fecha_fin}|" in l for l in text_lines)
        # Validar que (E) aparece junto al nombre
        assert any("(E)" in l for l in text_lines)
        # Validar secciones de total
        assert any("EXENTO" in l for l in text_lines)
        assert any("TOTAL" in l for l in text_lines)
        assert any("EFECTIVO 1" in l for l in text_lines)
        assert any(amount in l for l in text_lines)
        assert any(l.startswith("EFECTIVO 1") and amount in l for l in text_lines)

    def test_invoice_preview_matches_fiscal_ticket_shape(self, sample_client, monthly_plan):
        invoice = self._create_invoice(sample_client, monthly_plan, nro_control="00008042")
        invoice.client = sample_client
        invoice.monto_total = Decimal("1000.00")
        invoice.save(update_fields=['client', 'monto_total'])

        lines = build_invoice_preview_lines(invoice)

        assert lines[0] == " " * 42
        assert not any(line == "=" * 42 for line in lines)
        assert not any("- " in line and line.strip().endswith("-") for line in lines)
        assert any("SENIAT" in line for line in lines)
        assert any("RIF J-403298858" in line for line in lines)
        assert any("PERFECT LINE II, C.A" in line for line in lines)
        assert any(line.strip() == "FACTURA" for line in lines)
        assert any(line.startswith("FACTURA:") and line.endswith(PREVIEW_FISCAL_NUMBER) for line in lines)
        assert any(f"FECHA: {PREVIEW_FISCAL_DATE}" in line and f"HORA: {PREVIEW_FISCAL_TIME}" in line for line in lines)
        assert not any("00008042" in line for line in lines)
        assert any(line.startswith("TOTAL") and line.endswith("Bs 1.000,00") for line in lines)
        assert any(line.startswith("EFECTIVO 1") and line.endswith("Bs 1.000,00") for line in lines)

    def test_print_marks_invoice_as_printed(self, sample_client, monthly_plan, settings):
        """Validar que tras imprimir, esta_impresa se actualiza a True."""
        settings.DEBUG = True
        invoice = self._create_invoice(sample_client, monthly_plan)
        result = print_invoice(invoice)
        invoice.refresh_from_db()
        assert result is True
        assert invoice.esta_impresa is True

    def test_print_fails_without_config_in_production(self, sample_client, monthly_plan, settings):
        """En modo producción, sin PrinterConfig activo debe lanzar RuntimeError."""
        settings.DEBUG = False
        invoice = self._create_invoice(sample_client, monthly_plan)
        with pytest.raises(RuntimeError, match="No hay una configuración de impresora activa"):
            print_invoice(invoice)

    def test_singleton_printer_config(self):
        """No puede haber dos PrinterConfig activas simultáneamente."""
        PrinterConfig.objects.create(port="COM3", baudrate=38400, is_active=True)
        with pytest.raises(ValidationError):
            PrinterConfig.objects.create(port="COM4", baudrate=38400, is_active=True)

    # --- Tests de Estrés / Casos Borde ---

    def test_long_name_truncation(self, monthly_plan, db):
        """Nombres largos no deben superar los 42 caracteres por línea."""
        from apps.clients.models import Client
        client_largo = Client.objects.create(
            cedula="V-99999999",
            nombre="Fabricio Constantino de la Santísima Trinidad",
            codigo_afiliado="M-99999-99"
        )
        invoice = self._create_invoice(client_largo, monthly_plan)
        lines = _build_ticket_lines(invoice)

        for kind, content in lines:
            if kind == "text":
                assert len(content) <= MAX_LINE_WIDTH, (
                    f"Línea excede {MAX_LINE_WIDTH} chars: '{content}' ({len(content)} chars)"
                )

    def test_special_characters_in_name(self, monthly_plan, db):
        """Nombres con Ñ y tildes deben procesarse sin excepciones."""
        from apps.clients.models import Client
        client_especial = Client.objects.create(
            cedula="V-88888888",
            nombre="Nuñez García Mañé Ángel",
            codigo_afiliado="M-88888-88"
        )
        invoice = self._create_invoice(client_especial, monthly_plan)

        try:
            lines = _build_ticket_lines(invoice)
            text_lines = [c for k, c in lines if k == "text"]
            assert any("Nuñez" in line or "Nú" in line for line in text_lines)
        except Exception as e:
            pytest.fail(f"Excepción inesperada con caracteres especiales: {e}")

    def test_debug_mode_writes_to_file(self, sample_client, monthly_plan, settings, tmp_path):
        """En modo DEBUG, el tique se guarda como .txt en media/printer_debug/."""
        settings.DEBUG = True
        settings.MEDIA_ROOT = str(tmp_path)
        invoice = self._create_invoice(sample_client, monthly_plan)

        print_invoice(invoice)

        debug_dir = tmp_path / 'printer_debug'
        assert debug_dir.exists(), "La carpeta printer_debug no fue creada."
        files = list(debug_dir.iterdir())
        assert len(files) == 1, "Se esperaba exactamente 1 archivo de tique."
        content = files[0].read_text(encoding='utf-8')
        assert "RAZON SOCIAL:" in content
        assert sample_client.nombre in content
        assert "(E)" in content
        assert "EXENTO" in content

    def test_connection_error_does_not_lose_payment(self, sample_client, monthly_plan, settings):
        """Si el puerto COM falla, el pago (Invoice) NO debe borrarse de la BD."""
        settings.DEBUG = False
        PrinterConfig.objects.create(port="COM99", baudrate=38400, is_active=True)
        invoice = self._create_invoice(sample_client, monthly_plan)

        with patch("apps.billing.printer.Serial", side_effect=Exception("Puerto COM99 no encontrado")):
            with pytest.raises(Exception, match="Puerto COM99 no encontrado"):
                print_invoice(invoice)

        invoice.refresh_from_db()
        assert invoice.id is not None, "La factura fue borrada de la BD tras un error de hardware."
        assert invoice.esta_impresa is False, "esta_impresa no debe cambiar si falló la impresión."
