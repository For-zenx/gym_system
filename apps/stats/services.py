from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Count
from django.db.models.functions import ExtractHour
from django.utils import timezone

from apps.access.models import AccessLog

STATS_PERIOD_CHOICES = (7, 21, 30, 90, 365)

STATS_PERIOD_SHORT_LABELS = {
    7: "7D",
    21: "21D",
    30: "1M",
    90: "3M",
    365: "1Y",
}

STATS_PERIOD_LONG_LABELS = {
    7: "Últimos 7 días",
    21: "Últimos 21 días",
    30: "Último mes",
    90: "Últimos 3 meses",
    365: "Último año",
}


def normalize_period_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = 7
    if days not in STATS_PERIOD_CHOICES:
        return 7
    return days


def get_period_bounds(period_days: int):
    now = timezone.localtime()
    end = now
    start_date = now.date() - timedelta(days=period_days - 1)
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    return start, end, start_date, now.date()


def _format_hour_label(hour: int) -> str:
    return f"{hour:02d}:00"


def _format_date_range(start_date, end_date) -> str:
    return f"{start_date.strftime('%d/%m/%Y')} — {end_date.strftime('%d/%m/%Y')}"


def build_entry_hour_stats(period_days: int) -> dict:
    period_days = normalize_period_days(period_days)
    start, _end, start_date, end_date = get_period_bounds(period_days)
    tzinfo = timezone.get_current_timezone()

    rows = (
        AccessLog.objects.filter(resultado=True, timestamp__gte=start)
        .annotate(hour=ExtractHour("timestamp", tzinfo=tzinfo))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    counts_by_hour = {row["hour"]: row["count"] for row in rows if row["hour"] is not None}
    counts = [counts_by_hour.get(hour, 0) for hour in range(24)]
    labels = [_format_hour_label(hour) for hour in range(24)]
    total_entries = sum(counts)

    peak_hour = None
    peak_count = 0
    if total_entries:
        peak_hour = max(range(24), key=lambda hour: counts[hour])
        peak_count = counts[peak_hour]

    return {
        "period_days": period_days,
        "period_label": STATS_PERIOD_LONG_LABELS[period_days],
        "period_short_label": STATS_PERIOD_SHORT_LABELS[period_days],
        "date_range": _format_date_range(start_date, end_date),
        "labels": labels,
        "counts": counts,
        "total_entries": total_entries,
        "peak_hour": peak_hour,
        "peak_hour_label": _format_hour_label(peak_hour) if peak_hour is not None else None,
        "peak_count": peak_count,
    }
