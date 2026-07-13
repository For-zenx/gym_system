"""Conexión COM e impresión fiscal TFHKA."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional

from django.conf import settings

from apps.billing.fiscal.driver import NAK, PAYMENT_CMD_EFECTIVO, TfhkaClient
from apps.billing.fiscal.services import FiscalCommandStep
from apps.core.models import PrinterConfig

logger = logging.getLogger(__name__)

MSG_NOT_CONFIGURED = (
    "La impresora fiscal no está configurada. "
    "Vaya a Configuración del sistema → Impresoras y seleccione el puerto COM."
)
MSG_PORT_NOT_FOUND = (
    "No se encontró el puerto COM configurado. Verifique que la impresora esté "
    "conectada por USB."
)
MSG_PORT_BUSY = (
    "El puerto COM está en uso por otra aplicación (por ejemplo GymPOS). "
    "Cierre la otra aplicación e intente de nuevo."
)
MSG_NO_PING = (
    "La impresora fiscal no responde. Verifique que esté encendida y conectada."
)
MSG_COMM_ERROR = "Error de comunicación con la impresora fiscal."
MSG_DEBUG_OK = (
    "Simulación (modo desarrollo): secuencia fiscal guardada en archivo. "
    "No se abrió el puerto COM y la factura no se marcó como impresa."
)


@dataclass
class FiscalPrintStepResult:
    label: str
    cmd: str
    ok: bool
    response_hex: Optional[str] = None
    detail: str = ""


@dataclass
class FiscalPrintResult:
    success: bool
    message: str
    error_code: Optional[str] = None
    steps: List[FiscalPrintStepResult] = field(default_factory=list)
    debug_log_path: Optional[str] = None
    simulated: bool = False

    def to_dict(self):
        payload = asdict(self)
        payload["steps"] = [asdict(step) for step in self.steps]
        return payload


def resolve_fiscal_port() -> str:
    config = PrinterConfig.get_active()
    if config and config.port:
        return config.port.strip()
    return ""


def resolve_fiscal_baudrate() -> int:
    config = PrinterConfig.get_active()
    if config and config.baudrate:
        return int(config.baudrate)
    return int(getattr(settings, "FISCAL_BAUDRATE", 9600))


def _friendly_serial_error(exc: Exception) -> tuple[str, str]:
    text = str(exc).lower()
    if "filenotfounderror" in text or "could not open port" in text:
        return "PORT_NOT_FOUND", MSG_PORT_NOT_FOUND
    if "access is denied" in text or "permission" in text:
        return "PORT_BUSY", MSG_PORT_BUSY
    return "COMM_ERROR", MSG_COMM_ERROR


def _step_failure_code(result: FiscalPrintStepResult) -> str:
    if result.response_hex and result.response_hex.startswith(f"{NAK:02x}"):
        return "NAK"
    return "TIMEOUT"


def _step_failure_message(result: FiscalPrintStepResult) -> str:
    code = _step_failure_code(result)
    if code == "NAK":
        return "La impresora rechazó el paso «{label}».".format(label=result.label)
    return "Sin respuesta de la impresora en el paso «{label}».".format(label=result.label)


def execute_fiscal_print(
    steps: List[FiscalCommandStep],
    *,
    dry_run: bool = False,
    debug_log_path: Optional[str] = None,
) -> FiscalPrintResult:
    port = resolve_fiscal_port()
    if not port and not dry_run:
        return FiscalPrintResult(False, MSG_NOT_CONFIGURED, "NOT_CONFIGURED")

    baudrate = resolve_fiscal_baudrate()
    wait_before_close = float(getattr(settings, "FISCAL_WAIT_BEFORE_CLOSE", 5.0))
    close_read_timeout = float(getattr(settings, "FISCAL_CLOSE_READ_TIMEOUT", 10.0))

    client = TfhkaClient(
        port=port or "COM0",
        baudrate=baudrate,
        dry_run=dry_run,
        log_path=debug_log_path,
    )

    step_results: List[FiscalPrintStepResult] = []

    try:
        client.connect()
        client.reset()
        time.sleep(0.3)

        ping = client.ping()
        ping_result = FiscalPrintStepResult(
            label="Conexión con impresora",
            cmd="ENQ",
            ok=ping.ok,
            response_hex=ping.response_hex,
        )
        step_results.append(ping_result)
        if not ping.ok:
            return FiscalPrintResult(
                False,
                MSG_NO_PING,
                "NO_PING",
                step_results,
                debug_log_path,
            )

        for step in steps:
            is_close = step.cmd == PAYMENT_CMD_EFECTIVO
            if is_close:
                time.sleep(wait_before_close)
                cmd_result = client.send_cmd(
                    step.cmd,
                    post_write_sleep=0.8,
                    read_timeout=close_read_timeout,
                )
            else:
                cmd_result = client.send_cmd(step.cmd)

            step_result = FiscalPrintStepResult(
                label=step.label,
                cmd=step.cmd,
                ok=cmd_result.ok,
                response_hex=cmd_result.response_hex,
                detail="" if cmd_result.ok else _step_failure_message(
                    FiscalPrintStepResult(step.label, step.cmd, False, cmd_result.response_hex)
                ),
            )
            step_results.append(step_result)

            if not cmd_result.ok:
                failed = step_results[-1]
                return FiscalPrintResult(
                    False,
                    _step_failure_message(failed),
                    _step_failure_code(failed),
                    step_results,
                    debug_log_path,
                )

        message = MSG_DEBUG_OK if dry_run else "Factura impresa correctamente."
        return FiscalPrintResult(
            True, message, None, step_results, debug_log_path, simulated=dry_run
        )

    except Exception as exc:
        logger.exception("Error al imprimir factura fiscal por %s", port)
        code, message = _friendly_serial_error(exc)
        return FiscalPrintResult(False, message, code, step_results, debug_log_path)
    finally:
        client.close()


def write_fiscal_debug_file(invoice, steps: List[FiscalCommandStep]) -> str:
    debug_dir = os.path.join(settings.MEDIA_ROOT, "printer_debug")
    os.makedirs(debug_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "fiscal_{nro}_{ts}.txt".format(nro=invoice.nro_control, ts=timestamp)
    filepath = os.path.join(debug_dir, filename)

    lines = [
        "=== MODO DEBUG — secuencia TFHKA (DT-230) ===",
        "Factura: {0}".format(invoice.nro_control),
        "Puerto configurado: {0}".format(resolve_fiscal_port() or "(vacío)"),
        "",
    ]
    for index, step in enumerate(steps, start=1):
        lines.append("{0}. [{1}]".format(index, step.label))
        lines.append("   CMD: {0!r}".format(step.cmd))
    lines.append("")
    lines.append("Simulación: todos los pasos ACK (no se abrió COM).")

    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")

    return filepath
