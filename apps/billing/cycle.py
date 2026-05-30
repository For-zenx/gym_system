import calendar
from datetime import date, timedelta


def resolve_cut_date(year, month, cut_day):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(cut_day, last_day))


def advance_cut_date(cut_anchor, cut_day):
    month = cut_anchor.month + 1
    year = cut_anchor.year
    if month > 12:
        month = 1
        year += 1
    return resolve_cut_date(year, month, cut_day)


def subscription_period_bounds(cut_day, period_start):
    next_cut = advance_cut_date(period_start, cut_day)
    return period_start, next_cut - timedelta(days=1)


def billing_period_start(cut_day, payment_date):
    cut_this_month = resolve_cut_date(payment_date.year, payment_date.month, cut_day)
    if payment_date >= cut_this_month:
        return cut_this_month
    prev_month = payment_date.month - 1
    prev_year = payment_date.year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    return resolve_cut_date(prev_year, prev_month, cut_day)


def is_subscription_suspended(client, today=None):
    if not client.fecha_corte_dia:
        return False
    if today is None:
        today = date.today()
    from apps.billing.models import Plan

    return not client.memberships.filter(
        plan__billing_type=Plan.BillingType.FIXED,
        fecha_inicio__lte=today,
        fecha_fin__gte=today,
    ).exists()
