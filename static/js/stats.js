(function () {
    const config = window.GYM_STATS_CONFIG || {};
    const dataScript = document.getElementById('stats-data');
    const periodButtons = document.querySelectorAll('.stats-period-btn');

    // KPIs
    const totalEl = document.getElementById('stats-total-entries');
    const peakHourEl = document.getElementById('stats-peak-hour');
    const peakCountEl = document.getElementById('stats-peak-count');
    const periodLabelEl = document.getElementById('stats-period-label');
    const dateRangeEl = document.getElementById('stats-date-range');

    // Charts
    let hoursChart = null;
    let daysChart = null;
    let plansChart = null;
    let genderChart = null;

    let activePeriod = config.initialPeriod || 7;

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

    function renderHoursChart(stats) {
        const canvas = document.getElementById('entry-hours-chart');
        if (!canvas) return;

        const hasData = stats.total_entries > 0;
        toggleEmptyState('hours', hasData);
        if (!hasData) return;

        const data = {
            labels: stats.labels,
            datasets: [{
                label: 'Entradas',
                data: stats.counts,
                backgroundColor: CHART_COLORS.primaryAlpha,
                borderColor: CHART_COLORS.primary,
                borderWidth: 1,
                borderRadius: 4,
            }]
        };

        const options = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const hourIdx = context.dataIndex;
                            const total = context.parsed.y || 0;
                            const breakdown = stats.plan_breakdown[hourIdx] || {};
                            
                            let lines = [total === 1 ? '1 entrada' : total + ' entradas'];
                            
                            const plans = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
                            if (plans.length > 0) {
                                lines.push(''); // Espacio
                                plans.forEach(([name, count]) => {
                                    lines.push(`• ${name}: ${count}`);
                                });
                            }
                            return lines;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: CHART_COLORS.grid },
                    ticks: { color: CHART_COLORS.text, maxTicksLimit: 12 }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: CHART_COLORS.grid },
                    ticks: { color: CHART_COLORS.text, precision: 0 }
                }
            }
        };

        if (hoursChart) {
            hoursChart.data = data;
            hoursChart.update();
        } else {
            hoursChart = new Chart(canvas, { type: 'bar', data, options });
        }
    }

    function renderDaysChart(stats) {
        const canvas = document.getElementById('entry-days-chart');
        if (!canvas) return;

        const hasData = stats.total_entries > 0;
        toggleEmptyState('days', hasData);
        if (!hasData) return;

        const data = {
            labels: stats.weekday_stats.labels,
            datasets: [{
                label: 'Entradas',
                data: stats.weekday_stats.counts,
                backgroundColor: CHART_COLORS.secondaryAlpha,
                borderColor: CHART_COLORS.secondary,
                borderWidth: 1,
                borderRadius: 4,
            }]
        };

        const options = {
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
                    ticks: { color: CHART_COLORS.text, precision: 0 }
                }
            }
        };

        if (daysChart) {
            daysChart.data = data;
            daysChart.update();
        } else {
            daysChart = new Chart(canvas, { type: 'bar', data, options });
        }
    }

    function renderPlansChart(stats) {
        const canvas = document.getElementById('plan-dist-chart');
        if (!canvas) return;

        const hasData = stats.plan_distribution.counts.length > 0;
        toggleEmptyState('plans', hasData);
        if (!hasData) return;

        const data = {
            labels: stats.plan_distribution.labels,
            datasets: [{
                data: stats.plan_distribution.counts,
                backgroundColor: CHART_COLORS.palette,
                borderWidth: 2,
                borderColor: 'transparent',
            }]
        };

        const options = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: CHART_COLORS.text, padding: 15, usePointStyle: true }
                }
            },
            cutout: '65%'
        };

        if (plansChart) {
            plansChart.data = data;
            plansChart.update();
        } else {
            plansChart = new Chart(canvas, { type: 'doughnut', data, options });
        }
    }

    function renderGenderChart(stats) {
        const canvas = document.getElementById('gender-dist-chart');
        if (!canvas) return;

        const hasData = stats.gender_distribution.counts.length > 0;
        toggleEmptyState('gender', hasData);
        if (!hasData) return;

        const data = {
            labels: stats.gender_distribution.labels,
            datasets: [{
                data: stats.gender_distribution.counts,
                backgroundColor: ['#3b82f6', '#ec4899', '#94a3b8'],
                borderWidth: 2,
                borderColor: 'transparent',
            }]
        };

        const options = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: CHART_COLORS.text, padding: 15, usePointStyle: true }
                }
            },
            cutout: '65%'
        };

        if (genderChart) {
            genderChart.data = data;
            genderChart.update();
        } else {
            genderChart = new Chart(canvas, { type: 'doughnut', data, options });
        }
    }

    function applyStats(stats) {
        activePeriod = stats.period_days;
        updateKpis(stats);
        renderHoursChart(stats);
        renderDaysChart(stats);
        renderPlansChart(stats);
        renderGenderChart(stats);
        
        periodButtons.forEach(btn => {
            const isActive = Number(btn.dataset.period) === activePeriod;
            btn.classList.toggle('is-active', isActive);
            btn.disabled = isActive;
        });
    }

    function fetchStats(periodDays) {
        if (!config.dataUrl) return;
        periodButtons.forEach(btn => btn.disabled = true);

        fetch(config.dataUrl + '?period=' + periodDays, { credentials: 'same-origin' })
            .then(res => res.json())
            .then(applyStats)
            .catch(err => {
                console.error('[Stats] Error:', err);
                applyStats({ period_days: activePeriod }); // Reset buttons
            });
    }

    periodButtons.forEach(btn => {
        btn.addEventListener('click', () => fetchStats(Number(btn.dataset.period)));
    });

    document.addEventListener('DOMContentLoaded', () => {
        const initial = parseInitialStats();
        if (initial) applyStats(initial);
    });
})();
