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


def _period_covered(period_start, period_end, memberships):
    for membership in memberships:
        if membership.fecha_inicio <= period_start and membership.fecha_fin >= period_end:
            return True
    return False


def unpaid_fixed_periods(client, today=None):
    if not client.fecha_corte_dia:
        return []
    if today is None:
        today = date.today()

    from apps.billing.models import Plan

    cut_day = client.fecha_corte_dia
    fixed_memberships = list(
        client.memberships.filter(plan__billing_type=Plan.BillingType.FIXED).order_by("fecha_inicio")
    )
    if not fixed_memberships:
        return []

    unpaid = []
    period_start = fixed_memberships[0].fecha_inicio

    while period_start <= today:
        period_end = subscription_period_bounds(cut_day, period_start)[1]
        if not _period_covered(period_start, period_end, fixed_memberships):
            unpaid.append((period_start, period_end))
        period_start = period_end + timedelta(days=1)

    return unpaid


def days_since_last_unpaid_cut(client, today=None):
    unpaid = unpaid_fixed_periods(client, today)
    if not unpaid:
        return None
    if today is None:
        today = date.today()
    return (today - unpaid[0][0]).days


def next_cut_date(client, today=None):
    if not client.fecha_corte_dia:
        return None
    if today is None:
        today = date.today()
    cut_day = client.fecha_corte_dia
    cut_this_month = resolve_cut_date(today.year, today.month, cut_day)
    if today <= cut_this_month:
        return cut_this_month
    return advance_cut_date(cut_this_month, cut_day)


def days_until_next_cut_date(client, today=None):
    next_cut = next_cut_date(client, today)
    if not next_cut:
        return None
    if today is None:
        today = date.today()
    return (next_cut - today).days


def get_fixed_grace_days():
    from apps.billing.models import BillingSettings

    return BillingSettings.get_settings().fixed_grace_days


def get_latest_fixed_membership_end(client):
    from apps.billing.models import Plan

    latest = (
        client.memberships.filter(plan__billing_type=Plan.BillingType.FIXED)
        .order_by("-fecha_fin")
        .first()
    )
    return latest.fecha_fin if latest else None


def fixed_grace_deadline(client, today=None):
    if not client.fecha_corte_dia:
        return None
    grace_days = get_fixed_grace_days()
    if grace_days <= 0:
        return None
    last_end = get_latest_fixed_membership_end(client)
    if last_end is None:
        return None
    if today is None:
        today = date.today()
    if not is_subscription_suspended(client, today):
        return None
    return last_end + timedelta(days=grace_days)


def is_in_fixed_grace_period(client, today=None):
    if today is None:
        today = date.today()
    deadline = fixed_grace_deadline(client, today)
    if deadline is None:
        return False
    return today <= deadline


def fixed_grace_days_remaining(client, today=None):
    if today is None:
        today = date.today()
    deadline = fixed_grace_deadline(client, today)
    if deadline is None or today > deadline:
        return 0
    return (deadline - today).days
