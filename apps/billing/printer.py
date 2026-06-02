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

PREVIEW_FISCAL_NUMBER = "00000000"
PREVIEW_FISCAL_DATE = "xx-xx-xxxx"
PREVIEW_FISCAL_TIME = "--:--"


def _truncate(text, max_width):
    return text[:max_width] if len(text) > max_width else text


def _right_align(label, value, width=MAX_LINE_WIDTH):
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


def _legacy_ticket_amount_lines(invoice):
    cuota_ves = invoice.monto_cuota_ves
    lines = []
    if invoice.membership:
        fecha_inicio = invoice.membership.fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin = invoice.membership.fecha_fin.strftime('%d/%m/%Y')
        cuota_line = f"|CUOTA {fecha_inicio} AL {fecha_fin}|"
    else:
        emision = invoice.fecha_emision.strftime('%d/%m/%Y')
        cuota_line = f"|CUOTA REF EMISION: {emision}|"

    nombre, _, _ = invoice.get_receptor_for_ticket()
    cuota_str = _format_currency_ves(cuota_ves)
    lines.append(("text", cuota_line))
    lines.append(("text", _right_align(_truncate(nombre, 28) + " (E)", cuota_str)))

    if invoice.multa_ves and invoice.multa_ves > 0:
        multa_str = _format_currency_ves(invoice.multa_ves)
        lines.append(("text", _right_align("MULTA POR MOROSIDAD", multa_str)))

    return lines


def _detail_ticket_amount_lines(invoice, preview=False):
    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    lines = []
    nombre, _, _ = invoice.get_receptor_for_ticket()

    for line in invoice.lines.all().order_by("id"):
        label = _truncate(line.description, 28 if not preview else 20)
        amount_str = _format_currency_ves(line.amount_ves)
        text = _right_align(label, amount_str, width)
        if preview:
            lines.append(text)
        else:
            lines.append(("text", text))

    return lines


def _ticket_footer_lines(invoice, preview=False):
    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    total_str = _format_currency_ves(invoice.monto_total)
    exento_base = invoice.monto_cuota_ves
    exento_str = _format_currency_ves(exento_base)

    if preview:
        return [
            _preview_separator(width),
            _right_align("EXENTO", exento_str, width),
            _preview_separator(width),
            _right_align("TOTAL", total_str, width),
            _right_align("EFECTIVO 1", total_str, width),
        ]

    return [
        ("separator", None),
        ("text", _right_align("EXENTO", exento_str)),
        ("separator", None),
        ("text", _right_align("TOTAL", total_str)),
        ("text", _right_align("EFECTIVO 1", total_str)),
    ]


def _build_ticket_lines(invoice):
    nombre, cedula, codigo = invoice.get_receptor_for_ticket()
    lines = [
        ("text", f"RIF/C.I.: {cedula}"),
        ("text", _truncate(f"RAZON SOCIAL: {nombre}", MAX_LINE_WIDTH)),
        ("text", f"Cod. Afil.: {codigo}"),
        ("separator", None),
    ]

    if invoice.has_detail_lines():
        lines.extend(_detail_ticket_amount_lines(invoice, preview=False))
    else:
        lines.extend(_legacy_ticket_amount_lines(invoice))

    lines.extend(_ticket_footer_lines(invoice, preview=False))
    return lines


def build_invoice_preview_lines(invoice):
    issued_at = timezone.localtime(invoice.fecha_emision)
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
    ])

    if invoice.has_detail_lines():
        lines.extend(_detail_ticket_amount_lines(invoice, preview=True))
    else:
        cuota_str = _format_currency_ves(invoice.monto_cuota_ves)
        if invoice.membership:
            fecha_inicio = invoice.membership.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin = invoice.membership.fecha_fin.strftime('%d/%m/%Y')
            quota_line = f"|CUOTA {fecha_inicio} AL {fecha_fin}|"
        else:
            quota_line = f"|CUOTA REF EMISION: {issued_at.strftime('%d/%m/%Y')}|"
        lines.append(_truncate(quota_line, PREVIEW_LINE_WIDTH))
        lines.append(_right_align(_truncate(client_name, 20) + " (E)", cuota_str, PREVIEW_LINE_WIDTH))
        if invoice.multa_ves and invoice.multa_ves > 0:
            multa_str = _format_currency_ves(invoice.multa_ves)
            lines.append(_right_align("MULTA POR MOROSIDAD", multa_str, PREVIEW_LINE_WIDTH))

    lines.extend(_ticket_footer_lines(invoice, preview=True))
    return lines


def _render_lines(lines):
    output = []
    for kind, content in lines:
        if kind == "separator":
            output.append("-" * MAX_LINE_WIDTH)
        else:
            output.append(content)
    return "\n".join(output)


def _print_to_file(invoice, lines):
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
