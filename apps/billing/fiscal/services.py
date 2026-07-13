"""Mapeo Invoice → comandos TFHKA (secuencia validada iter. 4 gym)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.billing.fiscal.driver import PAYMENT_CMD_EFECTIVO, format_item_exento
from apps.billing.models import InvoiceLine


@dataclass
class FiscalCommandStep:
    label: str
    cmd: str


def _get_membership_quota_line(invoice, line):
    from apps.billing.printer import _membership_quota_line

    return _membership_quota_line(invoice, line)


def _quota_body_message(quota_line: str) -> str:
    q = quota_line.strip()
    if q.startswith("|") and q.endswith("|"):
        return q[1:-1]
    return q


def _membership_item_description(invoice) -> str:
    nombre, _, _ = invoice.get_receptor_for_ticket()
    return nombre[:37]


def build_fiscal_command_steps(invoice) -> list[FiscalCommandStep]:
    nombre, cedula, codigo = invoice.get_receptor_for_ticket()
    steps: list[FiscalCommandStep] = [
        FiscalCommandStep("RIF / C.I. del cliente", f"iR*{cedula}"),
        FiscalCommandStep("Razón social", f"iS*{nombre}"),
        FiscalCommandStep("Código de afiliado", f"i01Cod. Afil.: {codigo}"),
    ]

    if invoice.has_detail_lines():
        for line in invoice.lines.all().order_by("id"):
            steps.extend(_steps_for_invoice_line(invoice, line))
    else:
        steps.extend(_steps_for_legacy_invoice(invoice))

    steps.append(FiscalCommandStep("Cierre — efectivo", PAYMENT_CMD_EFECTIVO))
    return steps


def _steps_for_invoice_line(invoice, line: InvoiceLine) -> list[FiscalCommandStep]:
    amount = line.amount_ves
    qty = Decimal(line.quantity)

    if line.line_kind == InvoiceLine.LineKind.MEMBERSHIP:
        quota_line = _get_membership_quota_line(invoice, line)
        return [
            FiscalCommandStep(
                "Línea de cuota",
                f"@{_quota_body_message(quota_line)}",
            ),
            FiscalCommandStep(
                "Ítem membresía (exento)",
                format_item_exento(amount, _membership_item_description(invoice), qty),
            ),
        ]

    if line.line_kind == InvoiceLine.LineKind.LATE_FEE:
        desc = "MULTA POR MOROSIDAD"
    else:
        desc = (line.description or "Producto")[:37]

    return [
        FiscalCommandStep(
            f"Ítem {line.get_line_kind_display().lower()} (exento)",
            format_item_exento(amount, desc, qty),
        ),
    ]


def _steps_for_legacy_invoice(invoice) -> list[FiscalCommandStep]:
    nombre, _, _ = invoice.get_receptor_for_ticket()
    steps: list[FiscalCommandStep] = []

    quota_line = _get_membership_quota_line(invoice, None)
    steps.append(
        FiscalCommandStep(
            "Línea de cuota",
            f"@{_quota_body_message(quota_line)}",
        )
    )
    steps.append(
        FiscalCommandStep(
            "Ítem membresía (exento)",
            format_item_exento(invoice.monto_cuota_ves, nombre[:37]),
        )
    )

    multa = invoice.multa_ves or Decimal("0.00")
    if multa > 0:
        steps.append(
            FiscalCommandStep(
                "Ítem multa (exento)",
                format_item_exento(multa, "MULTA POR MOROSIDAD"),
            )
        )

    return steps
