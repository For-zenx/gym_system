from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.billing.models import ExchangeRate, Invoice, InvoiceLine, ReportEmailSettings, ReportSendLog
from apps.clients.models import Client

REPORT_PERIOD_CHOICES = (1, 7, 21, 30)

PAYMENT_ROW_ORDER = (
    (Invoice.PaymentMethod.CASH_VES, "Efectivo Bs", "ves"),
    (Invoice.PaymentMethod.MOBILE, "Pago móvil", "ves"),
    (Invoice.PaymentMethod.DEBIT, "Débito", "ves"),
    (Invoice.PaymentMethod.CASHEA, "Cashea", "ves"),
    (Invoice.PaymentMethod.CASH_USD, "Efectivo $", "usd"),
    (Invoice.PaymentMethod.ZELLE, "Zelle", "usd"),
)
UNKNOWN_PAYMENT_KEY = "unknown"
UNKNOWN_PAYMENT_LABEL = "Sin registrar"

USD_COLLECTED_METHODS = frozenset(
    {
        Invoice.PaymentMethod.CASH_USD,
        Invoice.PaymentMethod.ZELLE,
    }
)


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


def _fmt_usd(amount) -> str:
    if amount is None:
        return "$ 0,00"
    value = Decimal(amount)
    text = f"{value:,.2f}"
    return "$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def _invoice_usd_collected(invoice: Invoice) -> Decimal:
    if invoice.payment_method == Invoice.PaymentMethod.MIXED:
        total = Decimal("0")
        for entry in invoice.payment_splits or []:
            if entry.get("method") in USD_COLLECTED_METHODS:
                total += Decimal(str(entry.get("amount_usd", 0) or 0))
        return total

    if invoice.payment_method not in USD_COLLECTED_METHODS:
        return Decimal("0")

    if invoice.has_detail_lines():
        line_total = Decimal("0")
        for line in invoice.lines.all():
            qty = line.quantity or 1
            line_total += (line.unit_price_usd or Decimal("0")) * qty
        return line_total + (invoice.multa_usd or Decimal("0"))

    emission_date = timezone.localtime(invoice.fecha_emision).date()
    rate = (
        ExchangeRate.objects.filter(fecha__lte=emission_date)
        .order_by("-fecha", "-id")
        .first()
    )
    if rate and rate.tasa_ves:
        ves_without_multa = invoice.monto_total - (invoice.multa_ves or Decimal("0"))
        usd_part = (ves_without_multa / rate.tasa_ves).quantize(Decimal("0.01"))
        return usd_part + (invoice.multa_usd or Decimal("0"))
    return invoice.multa_usd or Decimal("0")


def _aggregate_payment_totals(invoices):
    buckets = {
        Invoice.PaymentMethod.CASH_VES: {"amount": Decimal("0"), "count": 0},
        Invoice.PaymentMethod.MOBILE: {"amount": Decimal("0"), "count": 0},
        Invoice.PaymentMethod.DEBIT: {"amount": Decimal("0"), "count": 0},
        Invoice.PaymentMethod.CASHEA: {"amount": Decimal("0"), "count": 0},
        Invoice.PaymentMethod.CASH_USD: {"amount": Decimal("0"), "count": 0},
        Invoice.PaymentMethod.ZELLE: {"amount": Decimal("0"), "count": 0},
        UNKNOWN_PAYMENT_KEY: {"amount": Decimal("0"), "count": 0},
    }
    total_ves = Decimal("0")
    total_usd = Decimal("0")

    for inv in invoices:
        total_ves += inv.monto_total or Decimal("0")

        if inv.payment_method == Invoice.PaymentMethod.MIXED:
            methods_in_invoice = set()
            for entry in inv.payment_splits or []:
                method = entry.get("method")
                if method in USD_COLLECTED_METHODS:
                    usd_amount = Decimal(str(entry.get("amount_usd", 0) or 0))
                    if usd_amount > 0:
                        buckets[method]["amount"] += usd_amount
                        total_usd += usd_amount
                        methods_in_invoice.add(method)
                elif method in buckets and method != UNKNOWN_PAYMENT_KEY:
                    ves_amount = Decimal(str(entry.get("amount_ves", 0) or 0))
                    if ves_amount > 0:
                        buckets[method]["amount"] += ves_amount
                        methods_in_invoice.add(method)
            for method in methods_in_invoice:
                buckets[method]["count"] += 1
            continue

        if not inv.payment_method:
            buckets[UNKNOWN_PAYMENT_KEY]["amount"] += inv.monto_total or Decimal("0")
            buckets[UNKNOWN_PAYMENT_KEY]["count"] += 1
            continue

        if inv.payment_method in USD_COLLECTED_METHODS:
            usd_amount = _invoice_usd_collected(inv)
            buckets[inv.payment_method]["amount"] += usd_amount
            buckets[inv.payment_method]["count"] += 1
            total_usd += usd_amount
            continue

        buckets[inv.payment_method]["amount"] += inv.monto_total or Decimal("0")
        buckets[inv.payment_method]["count"] += 1

    payment_rows = []
    for method, label, currency in PAYMENT_ROW_ORDER:
        data = buckets[method]
        if data["amount"] <= 0:
            continue
        amount_fmt = _fmt_usd(data["amount"]) if currency == "usd" else _fmt_ves(data["amount"])
        payment_rows.append(
            {
                "label": label,
                "amount_fmt": amount_fmt,
                "count": data["count"],
            }
        )

    unknown = buckets[UNKNOWN_PAYMENT_KEY]
    if unknown["amount"] > 0:
        payment_rows.append(
            {
                "label": UNKNOWN_PAYMENT_LABEL,
                "amount_fmt": _fmt_ves(unknown["amount"]),
                "count": unknown["count"],
            }
        )

    return payment_rows, total_ves, total_usd


def _invoice_client_label(invoice: Invoice) -> str:
    if invoice.client_nombre_snapshot:
        return invoice.client_nombre_snapshot.strip()
    if invoice.client_id:
        return f"Afiliado #{invoice.client_id}"
    return "—"


def _location_suffix(location: str) -> str:
    location = (location or "").strip()
    if not location:
        return ""
    return " — {}".format(location)


def _report_email_branding(meta: dict, gym_location: str) -> dict:
    location = (gym_location or "").strip()
    suffix = _location_suffix(location)
    return {
        "gym_location": location,
        "email_title": "{} — Reporte {} ({}){}".format(
            meta["gym_name"],
            meta["period_label"],
            meta["date_range"],
            suffix,
        ),
        "report_subtitle": "Reporte — {} ({}){}".format(
            meta["period_label"],
            meta["date_range"],
            suffix,
        ),
        "footer_brand": "{}{}".format(meta["gym_name"], suffix),
        "subject_line": "{} — Reporte {} ({}){}".format(
            meta["gym_name"],
            meta["period_label"],
            meta["date_range"],
            suffix,
        ),
    }


def _report_meta(period_days: int, start_date, end_date):
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
    }


def _period_invoices(period_days: int):
    period_days = normalize_period_days(period_days)
    start, end, start_date, end_date = get_period_bounds(period_days)
    invoices = (
        Invoice.objects.filter(
            fecha_emision__gte=start, fecha_emision__lte=end, esta_anulada=False
        )
        .prefetch_related("lines")
        .order_by("-fecha_emision")
    )
    return period_days, start_date, end_date, invoices


def _aggregate_report_totals_and_rows(invoices):
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
                "pk": inv.pk,
                "number": inv.nro_control,
                "date": timezone.localtime(inv.fecha_emision).strftime("%d/%m/%Y %H:%M"),
                "client": _invoice_client_label(inv),
                "client_code": inv.receptor_codigo,
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

    return totals, invoice_rows


def build_report_context(period_days: int) -> dict:
    period_days, start_date, end_date, invoices = _period_invoices(period_days)
    totals, invoice_rows = _aggregate_report_totals_and_rows(invoices)

    new_clients = Client.objects.filter(
        fecha_ingreso__gte=start_date,
        fecha_ingreso__lte=end_date,
    ).count()

    return {
        **_report_meta(period_days, start_date, end_date),
        "new_clients": new_clients,
        "totals": {
            **totals,
            "total_ves_fmt": _fmt_ves(totals["total_ves"]),
            "membership_ves_fmt": _fmt_ves(totals["membership_ves"]),
            "product_ves_fmt": _fmt_ves(totals["product_ves"]),
            "late_fee_ves_fmt": _fmt_ves(totals["late_fee_ves"]),
        },
        "invoice_rows": invoice_rows[:50],
        "invoice_rows_truncated": len(invoice_rows) > 50,
    }


def _date_bounds(target_date):
    start = timezone.make_aware(datetime.combine(target_date, time.min))
    end = timezone.make_aware(datetime.combine(target_date, time.max))
    return start, end


def _report_meta_for_date(target_date):
    gym_name = getattr(settings, "GYM_NAME", "Perfect Line II")
    day_label = target_date.strftime("%d/%m/%Y")
    return {
        "gym_name": gym_name,
        "period_days": 1,
        "period_label": day_label,
        "date_range": day_label,
        "generated_at": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
    }


def build_report_context_for_date(target_date) -> dict:
    start, end = _date_bounds(target_date)
    invoices = (
        Invoice.objects.filter(
            fecha_emision__gte=start, fecha_emision__lte=end, esta_anulada=False
        )
        .prefetch_related("lines")
        .order_by("-fecha_emision")
    )
    totals, invoice_rows = _aggregate_report_totals_and_rows(invoices)
    new_clients = Client.objects.filter(fecha_ingreso=target_date).count()

    return {
        **_report_meta_for_date(target_date),
        "new_clients": new_clients,
        "totals": {
            **totals,
            "total_ves_fmt": _fmt_ves(totals["total_ves"]),
            "membership_ves_fmt": _fmt_ves(totals["membership_ves"]),
            "product_ves_fmt": _fmt_ves(totals["product_ves"]),
            "late_fee_ves_fmt": _fmt_ves(totals["late_fee_ves"]),
        },
        "invoice_rows": invoice_rows[:50],
        "invoice_rows_truncated": len(invoice_rows) > 50,
    }


def _build_email_context(meta: dict, invoices, start_date, end_date) -> dict:
    payment_rows, total_ves, total_usd = _aggregate_payment_totals(invoices)
    new_clients = Client.objects.filter(
        fecha_ingreso__gte=start_date,
        fecha_ingreso__lte=end_date,
    ).count()
    cfg = ReportEmailSettings.get_settings()

    return {
        **meta,
        **_report_email_branding(meta, cfg.gym_location),
        "invoice_count": invoices.count(),
        "new_clients": new_clients,
        "payment_rows": payment_rows,
        "totals": {
            "total_ves": total_ves,
            "total_usd": total_usd,
            "total_ves_fmt": _fmt_ves(total_ves),
            "total_usd_fmt": _fmt_usd(total_usd),
        },
    }


def build_report_email_context(period_days: int) -> dict:
    period_days, start_date, end_date, invoices = _period_invoices(period_days)
    return _build_email_context(_report_meta(period_days, start_date, end_date), invoices, start_date, end_date)


def build_report_email_context_for_date(target_date) -> dict:
    start, end = _date_bounds(target_date)
    invoices = (
        Invoice.objects.filter(
            fecha_emision__gte=start, fecha_emision__lte=end, esta_anulada=False
        )
        .prefetch_related("lines")
        .order_by("-fecha_emision")
    )
    return _build_email_context(_report_meta_for_date(target_date), invoices, target_date, target_date)


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
    if not cfg.recipient_emails_list:
        return False, "Configure al menos un destinatario en Configuración → Reportes."
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


def send_report_email(*, user, period_days: int | None = None, target_date=None) -> dict:
    cfg = ReportEmailSettings.get_settings()
    recipients = cfg.recipient_emails_list
    items: list[dict] = []

    if target_date is not None:
        context = build_report_email_context_for_date(target_date)
    else:
        period_days = normalize_period_days(period_days if period_days is not None else 7)
        context = build_report_email_context(period_days)

    if not recipients:
        items.append({"ok": False, "text": "Destinatarios configurados"})
        return _send_result(success=False, items=items)

    items.append(
        {
            "ok": True,
            "text": "Destinatarios configurados ({})".format(len(recipients)),
        }
    )

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

    html_body = render_to_string("billing/emails/report.html", context)
    subject = context["subject_line"]
    items.append({"ok": True, "text": f"Reporte generado ({context['period_label']})"})

    recipients_display = ", ".join(recipients)
    log = ReportSendLog(
        period_days=context["period_days"],
        recipient_email=recipients_display,
        sent_by=user if getattr(user, "is_authenticated", False) else None,
        success=False,
    )

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Reporte HTML — abra este correo en un cliente compatible.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        log.success = True
        log.save()
        items.append({"ok": True, "text": "Enviado a {} destinatario(s): {}".format(len(recipients), recipients_display)})
        return _send_result(success=True, items=items)
    except Exception as exc:
        log.error_message = str(exc)[:500]
        log.save()
        items.append({"ok": False, "text": f"No se pudo enviar: {exc}"})
        return _send_result(success=False, items=items)
