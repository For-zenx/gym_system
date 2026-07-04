from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Count, Q, OuterRef, Subquery, Case, When, Value, CharField
from django.db.models.functions import ExtractHour, ExtractWeekDay
from django.utils import timezone

from apps.access.models import AccessLog
from apps.clients.models import Client, PersonCategory
from apps.billing.models import Membership


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
    today = timezone.localdate()

    # 1. Entradas por hora con desglose de planes
    # Subquery para encontrar el plan que el cliente tenía activo en el momento del log
    active_plan_subquery = Membership.objects.filter(
        client=OuterRef("client"),
        fecha_inicio__lte=OuterRef("timestamp__date"),
        fecha_fin__gte=OuterRef("timestamp__date"),
    ).values("plan__nombre")[:1]

    rows = (
        AccessLog.objects.filter(
            resultado=True,
            timestamp__gte=start,
            client__person_category=PersonCategory.MEMBER,
        )
        .annotate(
            hour=ExtractHour("timestamp", tzinfo=tzinfo),
            plan_name=Subquery(active_plan_subquery),
        )
        .values("hour", "plan_name")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    counts_by_hour = {}
    plan_breakdown_by_hour = {hour: {} for hour in range(24)}

    for row in rows:
        hour = row["hour"]
        if hour is None:
            continue
        count = row["count"]
        plan_name = row["plan_name"] or "Sin plan"

        counts_by_hour[hour] = counts_by_hour.get(hour, 0) + count
        plan_breakdown_by_hour[hour][plan_name] = count

    counts = [counts_by_hour.get(hour, 0) for hour in range(24)]
    plan_breakdown = [plan_breakdown_by_hour[hour] for hour in range(24)]
    labels = [_format_hour_label(hour) for hour in range(24)]
    total_entries = sum(counts)

    peak_hour = None
    peak_count = 0
    if total_entries:
        peak_hour = max(range(24), key=lambda hour: counts[hour])
        peak_count = counts[peak_hour]

    # 2. Distribución de Planes (Afiliados activos hoy)
    plan_dist_rows = (
        Membership.objects.filter(fecha_inicio__lte=today, fecha_fin__gte=today)
        .values("plan__nombre")
        .annotate(total=Count("client", distinct=True))
        .order_by("-total")
    )
    plan_distribution = {
        "labels": [row["plan__nombre"] for row in plan_dist_rows],
        "counts": [row["total"] for row in plan_dist_rows],
    }

    # 3. Distribución por Género (Afiliados activos hoy)
    gender_map = {"M": "Masculino", "F": "Femenino", "": "Sin especificar"}
    gender_dist_rows = (
        Client.objects.filter(
            person_category=PersonCategory.MEMBER,
            memberships__fecha_inicio__lte=today,
            memberships__fecha_fin__gte=today,
        )
        .values("sexo")
        .annotate(total=Count("id", distinct=True))
    )
    gender_distribution = {
        "labels": [gender_map.get(row["sexo"], "Otro") for row in gender_dist_rows],
        "counts": [row["total"] for row in gender_dist_rows],
    }

    # 4. Entradas por día de la semana
    weekday_rows = (
        AccessLog.objects.filter(
            resultado=True,
            timestamp__gte=start,
            client__person_category=PersonCategory.MEMBER,
        )
        .annotate(weekday_num=ExtractWeekDay("timestamp"))
        .values("weekday_num")
        .annotate(total=Count("id"))
        .order_by("weekday_num")
    )

    # Django ExtractWeekDay: 1=Sunday, 2=Monday, ..., 7=Saturday
    # Queremos Lunes a Domingo
    weekday_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    # Mapeo de ExtractWeekDay a nuestro índice (0=Lunes)
    # 2->0, 3->1, 4->2, 5->3, 6->4, 7->5, 1->6
    weekday_map = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 1: 6}
    weekday_counts = [0] * 7
    for row in weekday_rows:
        idx = weekday_map.get(row["weekday_num"])
        if idx is not None:
            weekday_counts[idx] = row["total"]

    weekday_stats = {
        "labels": weekday_names,
        "counts": weekday_counts,
    }

    return {
        "period_days": period_days,
        "period_label": STATS_PERIOD_LONG_LABELS[period_days],
        "period_short_label": STATS_PERIOD_SHORT_LABELS[period_days],
        "date_range": _format_date_range(start_date, end_date),
        "labels": labels,
        "counts": counts,
        "plan_breakdown": plan_breakdown,
        "total_entries": total_entries,
        "peak_hour": peak_hour,
        "peak_hour_label": _format_hour_label(peak_hour) if peak_hour is not None else None,
        "peak_count": peak_count,
        "plan_distribution": plan_distribution,
        "gender_distribution": gender_distribution,
        "weekday_stats": weekday_stats,
    }
