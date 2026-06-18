from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from apps.users.mixins import PermissionRequiredMixin

from .services import (
    STATS_PERIOD_CHOICES,
    STATS_PERIOD_SHORT_LABELS,
    build_entry_hour_stats,
    normalize_period_days,
)


class EntryHoursStatsView(PermissionRequiredMixin, View):
    required_permission = "stats.view"

    def get(self, request):
        period_days = normalize_period_days(request.GET.get("period", 7))
        stats = build_entry_hour_stats(period_days)
        return render(
            request,
            "stats/entry_hours.html",
            {
                "stats": stats,
                "period_choices": STATS_PERIOD_CHOICES,
                "period_options": [
                    (days, STATS_PERIOD_SHORT_LABELS[days]) for days in STATS_PERIOD_CHOICES
                ],
                "period_days": period_days,
            },
        )


class EntryHoursStatsDataView(PermissionRequiredMixin, View):
    required_permission = "stats.view"

    def get(self, request):
        period_days = normalize_period_days(request.GET.get("period", 7))
        stats = build_entry_hour_stats(period_days)
        return JsonResponse(stats)
