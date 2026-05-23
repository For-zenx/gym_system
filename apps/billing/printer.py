import os
import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from escpos.printer import Serial
from apps.core.models import PrinterConfig

logger = logging.getLogger(__name__)

MAX_LINE_WIDTH = 42
PREVIEW_LINE_WIDTH = 42

FISCAL_HEADER_LINES = [
    "SENIAT",
    "RIF J-403298858",
    "PERFECT LINE II, C.A",
    "CALLE PRINCIPAL DE JUAN GRIEGO CASA",
    "NRO 5 URB NUEVO JUAN GRIEGO JUAN GRIEGO",
    "NUEVA ESPARTA ZONA POSTAL 6309",
    "CONTRIBUYENTE FORMAL",
]

# Placeholders de solo previsualización: la Dascom imprime número, fecha y hora fiscales.
PREVIEW_FISCAL_NUMBER = "00000000"
PREVIEW_FISCAL_DATE = "xx-xx-xxxx"
PREVIEW_FISCAL_TIME = "--:--"


def _truncate(text, max_width):
    return text[:max_width] if len(text) > max_width else text


def _right_align(label, value, width=MAX_LINE_WIDTH):
    """Alinea el valor a la derecha de la línea: 'LABEL         VALUE'."""
    space = width - len(label) - len(value)
    if space < 1:
        space = 1
    return label + (" " * space) + value


def _center(text, width=MAX_LINE_WIDTH):
    return text[:width].center(width)


def _preview_blank(width=PREVIEW_LINE_WIDTH):
    return " " * width


def _preview_separator(width=PREVIEW_LINE_WIDTH):
    return "-" * width


def _format_currency_ves(amount):
    normalized = f"{amount:,.2f}"
    return "Bs " + normalized.replace(",", "X").replace(".", ",").replace("X", ".")


def _build_ticket_lines(invoice):
    nombre, cedula, codigo = invoice.get_receptor_for_ticket()
    monto_str = _format_currency_ves(invoice.monto_total)

    if invoice.membership:
        fecha_inicio = invoice.membership.fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin = invoice.membership.fecha_fin.strftime('%d/%m/%Y')
        cuota_line = f"|CUOTA {fecha_inicio} AL {fecha_fin}|"
    else:
        # Fallback en caso de que la membresía haya sido removida físicamente
        emision = invoice.fecha_emision.strftime('%d/%m/%Y')
        cuota_line = f"|CUOTA REF EMISION: {emision}|"

    lines = [
        # Datos del cliente (lo que el sistema envía, el encabezado lo genera la máquina)
        ("text", f"RIF/C.I.: {cedula}"),
        ("text", _truncate(f"RAZON SOCIAL: {nombre}", MAX_LINE_WIDTH)),
        ("text", f"Cod. Afil.: {codigo}"),
        ("separator", None),
        # Descripción de la transacción
        ("text", cuota_line),
        ("text", _right_align(_truncate(nombre, 28) + " (E)", monto_str)),
        ("separator", None),
        # Totales
        ("text", _right_align("EXENTO", monto_str)),
        ("separator", None),
        ("text", _right_align("TOTAL", monto_str)),
        ("text", _right_align("EFECTIVO 1", monto_str)),
    ]
    return lines


def build_invoice_preview_lines(invoice):
    issued_at = timezone.localtime(invoice.fecha_emision)
    amount = _format_currency_ves(invoice.monto_total)

    if invoice.membership:
        fecha_inicio = invoice.membership.fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin = invoice.membership.fecha_fin.strftime('%d/%m/%Y')
        quota_line = f"|CUOTA {fecha_inicio} AL {fecha_fin}|"
    else:
        quota_line = f"|CUOTA REF EMISION: {issued_at.strftime('%d/%m/%Y')}|"

    client_name, client_id, client_code = invoice.get_receptor_for_ticket()

    lines = [_preview_blank()]
    lines.extend(_center(line, PREVIEW_LINE_WIDTH) for line in FISCAL_HEADER_LINES)
    lines.extend([
        _preview_blank(),
        f"RIF/C.I.: {client_id}",
        _truncate(f"RAZON SOCIAL: {client_name}", PREVIEW_LINE_WIDTH),
        f"Cod. Afil.: {client_code}",
        _center("FACTURA", PREVIEW_LINE_WIDTH),
        _right_align("FACTURA:", PREVIEW_FISCAL_NUMBER, PREVIEW_LINE_WIDTH),
        _right_align(f"FECHA: {PREVIEW_FISCAL_DATE}", f"HORA: {PREVIEW_FISCAL_TIME}", PREVIEW_LINE_WIDTH),
        _preview_separator(),
        _truncate(quota_line, PREVIEW_LINE_WIDTH),
        _right_align(_truncate(client_name, 20) + " (E)", amount, PREVIEW_LINE_WIDTH),
        _preview_separator(),
        _right_align("EXENTO", amount, PREVIEW_LINE_WIDTH),
        _preview_separator(),
        _right_align("TOTAL", amount, PREVIEW_LINE_WIDTH),
        _right_align("EFECTIVO 1", amount, PREVIEW_LINE_WIDTH),
    ])
    return lines


def _render_lines(lines):
    """Convierte las líneas del tique a texto plano legible."""
    output = []
    for kind, content in lines:
        if kind == "separator":
            output.append("-" * MAX_LINE_WIDTH)
        else:
            output.append(content)
    return "\n".join(output)


def _print_to_file(invoice, lines):
    """Modo DEBUG: guarda el tique como archivo .txt en media/printer_debug/."""
    debug_dir = os.path.join(settings.MEDIA_ROOT, 'printer_debug')
    os.makedirs(debug_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"ticket_{invoice.nro_control}_{timestamp}.txt"
    filepath = os.path.join(debug_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(_render_lines(lines))
        f.write("\n[CORTE]\n")

    logger.info(f"[DEBUG] Tique guardado en: {filepath}")
    return filepath


def print_invoice(invoice):
    try:
        lines = _build_ticket_lines(invoice)

        if settings.DEBUG:
            _print_to_file(invoice, lines)
        else:
            config = PrinterConfig.get_active()
            if not config:
                raise RuntimeError("No hay una configuración de impresora activa en el sistema.")

            printer = Serial(devfile=config.port, baudrate=config.baudrate, profile="TM-T88IV")
            for kind, content in lines:
                if kind == "separator":
                    printer.text("-" * MAX_LINE_WIDTH + "\n")
                else:
                    printer.text(f"{content}\n")
            printer.cut()

        invoice.esta_impresa = True
        invoice.save()

        logger.info(f"Factura {invoice.nro_control} procesada correctamente.")
        return True

    except Exception as e:
        logger.error(f"Error al imprimir factura {invoice.nro_control}: {e}", exc_info=True)
        raise
