import os
import logging
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from escpos.printer import Serial

from apps.billing.models import InvoiceLine
from apps.core.models import PrinterConfig

logger = logging.getLogger(__name__)

MAX_LINE_WIDTH = 42
PREVIEW_LINE_WIDTH = 42


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


def _normalize_overrides(amount_overrides):
    if not amount_overrides:
        return {}
    normalized = {}
    for key, value in amount_overrides.items():
        normalized[int(key)] = Decimal(str(value))
    return normalized


def _get_line_amount(line, amount_overrides):
    if amount_overrides and line.pk in amount_overrides:
        return amount_overrides[line.pk]
    return line.amount_ves


def compute_invoice_total(invoice, amount_overrides=None):
    overrides = _normalize_overrides(amount_overrides)
    if invoice.has_detail_lines():
        if overrides:
            total = Decimal("0.00")
            for line in invoice.lines.all():
                total += _get_line_amount(line, overrides)
            return total
        return sum((line.amount_ves for line in invoice.lines.all()), Decimal("0.00"))
    if overrides and "legacy_total" in overrides:
        return overrides["legacy_total"]
    return invoice.monto_total


def _membership_quota_line(invoice, line):
    membership = line.membership if line else None
    if membership is None:
        membership = invoice.membership
    if membership and membership.fecha_fin:
        fecha_inicio = membership.fecha_inicio.strftime("%d/%m/%Y")
        fecha_fin = membership.fecha_fin.strftime("%d/%m/%Y")
        return f"|CUOTA {fecha_inicio} AL {fecha_fin}|"
    issued = timezone.localtime(invoice.fecha_emision).strftime("%d/%m/%Y")
    return f"|CUOTA REF EMISION: {issued}|"


def _cabecera_block_preview():
    width = PREVIEW_LINE_WIDTH
    return [
        _preview_blank(width),
        _preview_blank(width),
        _preview_separator(width),
        _preview_blank(width),
        _center("CABECERA", width),
        _preview_blank(width),
        _preview_separator(width),
        _preview_blank(width),
    ]


def _cabecera_block_print():
    blank = " " * MAX_LINE_WIDTH
    return [
        ("text", blank),
        ("text", "-" * MAX_LINE_WIDTH),
        ("text", blank),
        ("text", _center("CABECERA")),
        ("text", blank),
        ("text", "-" * MAX_LINE_WIDTH),
        ("text", blank),
    ]


def _legacy_ticket_amount_lines(invoice, preview=False, amount_overrides=None):
    overrides = _normalize_overrides(amount_overrides)
    cuota_ves = overrides.get("legacy_cuota", invoice.monto_cuota_ves)
    if overrides.get("legacy_total") is not None:
        total_ves = overrides["legacy_total"]
        multa_ves = total_ves - cuota_ves
        if multa_ves < 0:
            multa_ves = Decimal("0.00")
    else:
        multa_ves = invoice.multa_ves or Decimal("0.00")

    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    nombre, _, _ = invoice.get_receptor_for_ticket()
    cuota_str = _format_currency_ves(cuota_ves)
    lines = []

    cuota_line = _membership_quota_line(invoice, None)
    if preview:
        lines.append(_truncate(cuota_line, width))
        lines.append(_right_align(_truncate(nombre, 28) + " (E)", cuota_str, width))
        if multa_ves > 0:
            multa_str = _format_currency_ves(multa_ves)
            lines.append(_right_align("MULTA POR MOROSIDAD", multa_str, width))
        return lines

    lines.append(("text", cuota_line))
    lines.append(("text", _right_align(_truncate(nombre, 28) + " (E)", cuota_str)))
    if multa_ves > 0:
        multa_str = _format_currency_ves(multa_ves)
        lines.append(("text", _right_align("MULTA POR MOROSIDAD", multa_str)))
    return lines


def _detail_ticket_amount_lines(invoice, preview=False, amount_overrides=None):
    overrides = _normalize_overrides(amount_overrides)
    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    nombre, _, _ = invoice.get_receptor_for_ticket()
    lines = []

    for line in invoice.lines.all().order_by("id"):
        amount = _get_line_amount(line, overrides)
        amount_str = _format_currency_ves(amount)

        if line.line_kind == InvoiceLine.LineKind.MEMBERSHIP:
            cuota_line = _membership_quota_line(invoice, line)
            if preview:
                lines.append(_truncate(cuota_line, width))
                lines.append(_right_align(_truncate(nombre, 28) + " (E)", amount_str, width))
            else:
                lines.append(("text", cuota_line))
                lines.append(("text", _right_align(_truncate(nombre, 28) + " (E)", amount_str)))
        elif line.line_kind == InvoiceLine.LineKind.LATE_FEE:
            text = _right_align("MULTA POR MOROSIDAD", amount_str, width)
            if preview:
                lines.append(text)
            else:
                lines.append(("text", text))
        else:
            label = _truncate(line.description, 28 if not preview else 20)
            text = _right_align(label, amount_str, width)
            if preview:
                lines.append(text)
            else:
                lines.append(("text", text))

    return lines


def _ticket_footer_lines(invoice, preview=False, amount_overrides=None):
    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    total = compute_invoice_total(invoice, amount_overrides)
    total_str = _format_currency_ves(total)
    exento_str = total_str

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


def _client_header_lines(invoice, preview=False):
    nombre, cedula, codigo = invoice.get_receptor_for_ticket()
    width = PREVIEW_LINE_WIDTH if preview else MAX_LINE_WIDTH
    if preview:
        return [
            f"RIF/C.I.: {cedula}",
            _truncate(f"RAZON SOCIAL: {nombre}", width),
            f"Cod. Afil.: {codigo}",
            _preview_separator(width),
        ]
    return [
        ("text", f"RIF/C.I.: {cedula}"),
        ("text", _truncate(f"RAZON SOCIAL: {nombre}", MAX_LINE_WIDTH)),
        ("text", f"Cod. Afil.: {codigo}"),
        ("separator", None),
    ]


def _build_ticket_lines(invoice):
    lines = []
    lines.extend(_cabecera_block_print())
    lines.extend(_client_header_lines(invoice, preview=False))

    if invoice.has_detail_lines():
        lines.extend(_detail_ticket_amount_lines(invoice, preview=False))
    else:
        lines.extend(_legacy_ticket_amount_lines(invoice, preview=False))

    lines.extend(_ticket_footer_lines(invoice, preview=False))
    return lines


def build_invoice_preview_lines(invoice, amount_overrides=None):
    lines = []
    lines.extend(_cabecera_block_preview())
    lines.extend(_client_header_lines(invoice, preview=True))

    if invoice.has_detail_lines():
        lines.extend(
            _detail_ticket_amount_lines(
                invoice, preview=True, amount_overrides=amount_overrides
            )
        )
    else:
        lines.extend(
            _legacy_ticket_amount_lines(
                invoice, preview=True, amount_overrides=amount_overrides
            )
        )

    lines.extend(_ticket_footer_lines(invoice, preview=True, amount_overrides=amount_overrides))
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
    debug_dir = os.path.join(settings.MEDIA_ROOT, "printer_debug")
    os.makedirs(debug_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ticket_{invoice.nro_control}_{timestamp}.txt"
    filepath = os.path.join(debug_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
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
