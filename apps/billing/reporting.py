from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceLine, ReportEmailSettings, ReportSendLog
from apps.clients.models import Client

REPORT_PERIOD_CHOICES = (1, 7, 21, 30)


def normalize_period_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = 7
    if days not in REPORT_PERIOD_CHOICES:
        return 7
    return days


def get_period_bounds(period_days: int):
    now = timezone.localtime()
    end = now
    start_date = now.date() - timedelta(days=period_days - 1)
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    return start, end, start_date, now.date()


def _fmt_ves(amount) -> str:
    if amount is None:
        return "Bs 0,00"
    value = Decimal(amount)
    text = f"{value:,.2f}"
    return "Bs " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def _invoice_client_label(invoice: Invoice) -> str:
    if invoice.client_nombre_snapshot:
        return invoice.client_nombre_snapshot.strip()
    if invoice.client_id:
        return f"Afiliado #{invoice.client_id}"
    return "—"


def build_report_context(period_days: int) -> dict:
    period_days = normalize_period_days(period_days)
    start, end, start_date, end_date = get_period_bounds(period_days)

    invoices = (
        Invoice.objects.filter(
            fecha_emision__gte=start, fecha_emision__lte=end, esta_anulada=False
        )
        .prefetch_related("lines")
        .order_by("-fecha_emision")
    )

    totals = {
        "invoice_count": 0,
        "total_ves": Decimal("0"),
        "membership_count": 0,
        "membership_ves": Decimal("0"),
        "product_count": 0,
        "product_ves": Decimal("0"),
        "late_fee_count": 0,
        "late_fee_ves": Decimal("0"),
    }
    invoice_rows = []

    for inv in invoices:
        totals["invoice_count"] += 1
        totals["total_ves"] += inv.monto_total
        invoice_rows.append(
            {
                "number": inv.nro_control,
                "date": timezone.localtime(inv.fecha_emision).strftime("%d/%m/%Y %H:%M"),
                "client": _invoice_client_label(inv),
                "total_ves": _fmt_ves(inv.monto_total),
            }
        )

        if inv.has_detail_lines():
            for line in inv.lines.all():
                qty = line.quantity or 1
                line_total = line.amount_ves or Decimal("0")
                if line.line_kind == InvoiceLine.LineKind.MEMBERSHIP:
                    totals["membership_count"] += qty
                    totals["membership_ves"] += line_total
                elif line.line_kind == InvoiceLine.LineKind.PRODUCT:
                    totals["product_count"] += qty
                    totals["product_ves"] += line_total
                elif line.line_kind == InvoiceLine.LineKind.LATE_FEE:
                    totals["late_fee_count"] += qty
                    totals["late_fee_ves"] += line_total
        else:
            membership_ves = inv.monto_cuota_ves or Decimal("0")
            late_fee_ves = inv.multa_ves or Decimal("0")
            if membership_ves:
                totals["membership_count"] += 1
                totals["membership_ves"] += membership_ves
            if late_fee_ves:
                totals["late_fee_count"] += 1
                totals["late_fee_ves"] += late_fee_ves
            if not membership_ves and not late_fee_ves:
                totals["product_count"] += 1
                totals["product_ves"] += inv.monto_total

    new_clients = Client.objects.filter(
        fecha_ingreso__gte=start_date,
        fecha_ingreso__lte=end_date,
    ).count()

    gym_name = getattr(settings, "GYM_NAME", "Perfect Line II")
    period_label = f"Últimos {period_days} día{'s' if period_days != 1 else ''}"
    date_range = (
        f"{start_date.strftime('%d/%m/%Y')} — {end_date.strftime('%d/%m/%Y')}"
    )

    return {
        "gym_name": gym_name,
        "period_days": period_days,
        "period_label": period_label,
        "date_range": date_range,
        "generated_at": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        "totals": {
            **totals,
            "total_ves_fmt": _fmt_ves(totals["total_ves"]),
            "membership_ves_fmt": _fmt_ves(totals["membership_ves"]),
            "product_ves_fmt": _fmt_ves(totals["product_ves"]),
            "late_fee_ves_fmt": _fmt_ves(totals["late_fee_ves"]),
        },
        "invoice_rows": invoice_rows[:50],
        "invoice_rows_truncated": len(invoice_rows) > 50,
        "new_clients": new_clients,
    }


def is_smtp_configured() -> bool:
    return bool(getattr(settings, "EMAIL_HOST_USER", "") and getattr(settings, "EMAIL_HOST_PASSWORD", ""))


def daily_send_count() -> int:
    today = timezone.localdate()
    return ReportSendLog.objects.filter(sent_at__date=today).count()


def can_send_report_today() -> tuple[bool, str]:
    cfg = ReportEmailSettings.get_settings()
    limit = cfg.daily_send_limit or 3
    count = daily_send_count()
    if count >= limit:
        return False, f"Límite diario alcanzado ({limit} envíos por día)."
    if not cfg.recipient_email:
        return False, "Configure el correo del destinatario en Configuración → Reportes."
    if not is_smtp_configured():
        return False, "El envío por correo no está disponible. Contacte al administrador."
    return True, ""


def _send_result(*, success: bool, items: list, daily_send_count_value: int | None = None) -> dict:
    payload = {
        "success": success,
        "items": items,
        "daily_send_count": daily_send_count_value if daily_send_count_value is not None else daily_send_count(),
    }
    return payload


def send_report_email(*, period_days: int, user) -> dict:
    period_days = normalize_period_days(period_days)
    cfg = ReportEmailSettings.get_settings()
    recipient = (cfg.recipient_email or "").strip()
    items: list[dict] = []

    if not recipient:
        items.append({"ok": False, "text": "Correo del destinatario configurado"})
        return _send_result(success=False, items=items)

    items.append({"ok": True, "text": "Correo del destinatario configurado"})

    limit = cfg.daily_send_limit or 3
    count = daily_send_count()
    if count >= limit:
        items.append({"ok": False, "text": f"Límite de envíos diarios ({limit})"})
        return _send_result(success=False, items=items, daily_send_count_value=count)

    items.append({"ok": True, "text": "Disponibilidad de envío"})

    if not is_smtp_configured():
        items.append({"ok": False, "text": "Servicio de correo disponible"})
        return _send_result(success=False, items=items, daily_send_count_value=count)

    items.append({"ok": True, "text": "Servicio de correo disponible"})

    context = build_report_context(period_days)
    html_body = render_to_string("billing/emails/report.html", context)
    subject = (
        f"{settings.REPORT_EMAIL_SUBJECT_PREFIX} — "
        f"Reporte {context['period_label']} ({context['date_range']})"
    )
    items.append({"ok": True, "text": f"Reporte generado ({context['period_label']})"})

    log = ReportSendLog(
        period_days=period_days,
        recipient_email=recipient,
        sent_by=user if getattr(user, "is_authenticated", False) else None,
        success=False,
    )

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Reporte HTML — abra este correo en un cliente compatible.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        log.success = True
        log.save()
        items.append({"ok": True, "text": f"Enviado a {recipient}"})
        return _send_result(success=True, items=items)
    except Exception as exc:
        log.error_message = str(exc)[:500]
        log.save()
        items.append({"ok": False, "text": f"No se pudo enviar: {exc}"})
        return _send_result(success=False, items=items)
