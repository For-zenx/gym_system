(function () {
    const config = window.GYM_STATS_CONFIG || {};
    const dataScript = document.getElementById('stats-data');
    const periodButtons = document.querySelectorAll('.stats-period-btn');

    const totalEl = document.getElementById('stats-total-entries');
    const peakHourEl = document.getElementById('stats-peak-hour');
    const peakCountEl = document.getElementById('stats-peak-count');
    const periodLabelEl = document.getElementById('stats-period-label');
    const dateRangeEl = document.getElementById('stats-date-range');

    let hoursChart = null;
    let daysChart = null;
    let plansChart = null;
    let genderChart = null;

    let activePeriod = config.initialPeriod || 7;
    let latestHourlyStats = null;

    const CHART_COLORS = {
        primary: '#10b981',
        primaryAlpha: 'rgba(16, 185, 129, 0.75)',
        secondary: '#3b82f6',
        secondaryAlpha: 'rgba(59, 130, 246, 0.75)',
        text: '#94a3b8',
        grid: 'rgba(148, 163, 184, 0.12)',
        palette: [
            '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
            '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1'
        ]
    };

    const barValueLabelsPlugin = {
        id: 'barValueLabels',
        afterDatasetsDraw(chart) {
            const ctx = chart.ctx;
            chart.data.datasets.forEach(function (dataset, datasetIndex) {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (!meta.visible) {
                    return;
                }
                meta.data.forEach(function (bar, index) {
                    const value = dataset.data[index];
                    if (!value || value <= 0) {
                        return;
                    }
                    ctx.save();
                    ctx.fillStyle = CHART_COLORS.text;
                    ctx.font = '11px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'bottom';
                    ctx.fillText(String(value), bar.x, bar.y - 4);
                    ctx.restore();
                });
            });
        },
    };

    function parseInitialStats() {
        if (!dataScript) return null;
        try {
            return JSON.parse(dataScript.textContent);
        } catch (err) {
            console.error('[Stats] Datos iniciales inválidos:', err);
            return null;
        }
    }

    function updateKpis(stats) {
        if (totalEl) totalEl.textContent = String(stats.total_entries);
        if (peakHourEl) peakHourEl.textContent = stats.peak_hour_label || '—';
        if (peakCountEl) peakCountEl.textContent = stats.total_entries ? String(stats.peak_count) : '—';
        if (periodLabelEl) periodLabelEl.textContent = stats.period_label;
        if (dateRangeEl) dateRangeEl.textContent = stats.date_range;
    }

    function toggleEmptyState(id, hasData) {
        const empty = document.getElementById('stats-empty-state-' + id);
        const wrap = document.getElementById('stats-chart-wrap-' + id);
        if (empty) empty.classList.toggle('hidden', hasData);
        if (wrap) wrap.classList.toggle('hidden', !hasData);
    }

    function destroyChart(chartRef) {
        if (chartRef) {
            chartRef.destroy();
        }
        return null;
    }

    function doughnutLabelsWithCounts(labels, counts) {
        return labels.map(function (label, index) {
            const count = counts[index] || 0;
            return label + ' (' + count + ')';
        });
    }

    function renderHoursChart(stats) {
        const canvas = document.getElementById('entry-hours-chart');
        if (!canvas) return;

        latestHourlyStats = stats;
        const hasData = stats.total_entries > 0;
        toggleEmptyState('hours', hasData);
        hoursChart = destroyChart(hoursChart);
        if (!hasData) return;

        hoursChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: stats.labels,
                datasets: [{
                    label: 'Entradas',
                    data: stats.counts,
                    backgroundColor: CHART_COLORS.primaryAlpha,
                    borderColor: CHART_COLORS.primary,
                    borderWidth: 1,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const hourIdx = context.dataIndex;
                                const total = context.parsed.y || 0;
                                const breakdown = (latestHourlyStats && latestHourlyStats.plan_breakdown)
                                    ? latestHourlyStats.plan_breakdown[hourIdx] || {}
                                    : {};

                                const lines = [total === 1 ? '1 entrada' : total + ' entradas'];
                                const plans = Object.entries(breakdown).sort(function (a, b) {
                                    return b[1] - a[1];
                                });
                                if (plans.length > 0) {
                                    lines.push('');
                                    plans.forEach(function (entry) {
                                        lines.push('• ' + entry[0] + ': ' + entry[1]);
                                    });
                                }
                                return lines;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { color: CHART_COLORS.grid },
                        ticks: { color: CHART_COLORS.text, maxTicksLimit: 12 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: CHART_COLORS.grid },
                        ticks: { color: CHART_COLORS.text, precision: 0 },
                    },
                },
            },
            plugins: [barValueLabelsPlugin],
        });
    }

    function renderDaysChart(stats) {
        const canvas = document.getElementById('entry-days-chart');
        if (!canvas) return;

        const hasData = stats.total_entries > 0;
        toggleEmptyState('days', hasData);
        daysChart = destroyChart(daysChart);
        if (!hasData) return;

        daysChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: stats.weekday_stats.labels,
                datasets: [{
                    label: 'Entradas',
                    data: stats.weekday_stats.counts,
                    backgroundColor: CHART_COLORS.secondaryAlpha,
                    borderColor: CHART_COLORS.secondary,
                    borderWidth: 1,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } },
                    y: {
                        beginAtZero: true,
                        grid: { color: CHART_COLORS.grid },
                        ticks: { color: CHART_COLORS.text, precision: 0 },
                    },
                },
            },
            plugins: [barValueLabelsPlugin],
        });
    }

    function renderPlansChart(stats) {
        const canvas = document.getElementById('plan-dist-chart');
        if (!canvas) return;

        const hasData = stats.plan_distribution.counts.length > 0;
        toggleEmptyState('plans', hasData);
        plansChart = destroyChart(plansChart);
        if (!hasData) return;

        plansChart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: doughnutLabelsWithCounts(
                    stats.plan_distribution.labels,
                    stats.plan_distribution.counts
                ),
                datasets: [{
                    data: stats.plan_distribution.counts,
                    backgroundColor: CHART_COLORS.palette,
                    borderWidth: 2,
                    borderColor: 'transparent',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: CHART_COLORS.text, padding: 15, usePointStyle: true },
                    },
                },
                cutout: '65%',
            },
        });
    }

    function renderGenderChart(stats) {
        const canvas = document.getElementById('gender-dist-chart');
        if (!canvas) return;

        const hasData = stats.gender_distribution.counts.length > 0;
        toggleEmptyState('gender', hasData);
        genderChart = destroyChart(genderChart);
        if (!hasData) return;

        genderChart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: doughnutLabelsWithCounts(
                    stats.gender_distribution.labels,
                    stats.gender_distribution.counts
                ),
                datasets: [{
                    data: stats.gender_distribution.counts,
                    backgroundColor: ['#3b82f6', '#ec4899', '#94a3b8'],
                    borderWidth: 2,
                    borderColor: 'transparent',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: CHART_COLORS.text, padding: 15, usePointStyle: true },
                    },
                },
                cutout: '65%',
            },
        });
    }

    function applyStats(stats) {
        if (!stats || typeof stats.total_entries === 'undefined') {
            periodButtons.forEach(function (btn) {
                btn.disabled = Number(btn.dataset.period) === activePeriod;
            });
            return;
        }

        activePeriod = stats.period_days;
        updateKpis(stats);
        renderHoursChart(stats);
        renderDaysChart(stats);
        renderPlansChart(stats);
        renderGenderChart(stats);

        periodButtons.forEach(function (btn) {
            const isActive = Number(btn.dataset.period) === activePeriod;
            btn.classList.toggle('is-active', isActive);
            btn.disabled = isActive;
        });
    }

    function fetchStats(periodDays) {
        if (!config.dataUrl) return;
        periodButtons.forEach(function (btn) {
            btn.disabled = true;
        });

        fetch(config.dataUrl + '?period=' + periodDays, { credentials: 'same-origin' })
            .then(function (res) {
                return res.json();
            })
            .then(applyStats)
            .catch(function (err) {
                console.error('[Stats] Error:', err);
                periodButtons.forEach(function (btn) {
                    btn.disabled = Number(btn.dataset.period) === activePeriod;
                });
            });
    }

    periodButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            fetchStats(Number(btn.dataset.period));
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const initial = parseInitialStats();
        if (initial) applyStats(initial);
    });
})();
