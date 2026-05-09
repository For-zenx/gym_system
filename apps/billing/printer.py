import os
import logging
from datetime import datetime
from django.conf import settings
from escpos.printer import Serial
from apps.core.models import PrinterConfig

logger = logging.getLogger(__name__)

MAX_LINE_WIDTH = 42


def _truncate(text, max_width):
    return text[:max_width] if len(text) > max_width else text


def _right_align(label, value, width=MAX_LINE_WIDTH):
    """Alinea el valor a la derecha de la línea: 'LABEL         VALUE'."""
    space = width - len(label) - len(value)
    if space < 1:
        space = 1
    return label + (" " * space) + value


def _build_ticket_lines(invoice):
    membership = invoice.membership
    client = membership.client

    fecha_inicio = membership.fecha_inicio.strftime('%d/%m/%Y')
    fecha_fin = membership.fecha_fin.strftime('%d/%m/%Y')
    monto_str = f"Bs {invoice.monto_total:,.2f}"

    lines = [
        # Datos del cliente (lo que el sistema envía, el encabezado lo genera la máquina)
        ("text", f"RIF/C.I.: {client.cedula}"),
        ("text", _truncate(f"RAZON SOCIAL: {client.nombre}", MAX_LINE_WIDTH)),
        ("text", f"Cod. Afil.: {client.codigo_afiliado}"),
        ("separator", None),
        # Descripción de la transacción
        ("text", f"|CUOTA {fecha_inicio} AL {fecha_fin}|"),
        ("text", _right_align(_truncate(client.nombre, 28) + " (E)", monto_str)),
        ("separator", None),
        # Totales
        ("text", _right_align("EXENTO", monto_str)),
        ("separator", None),
        ("text", _right_align("TOTAL", monto_str)),
        ("text", "EFECTIVO 1"),
    ]
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
