(function () {
    const config = window.ENTRY_HOURS_STATS || {};
    const dataScript = document.getElementById('entry-hours-stats-data');
    const canvas = document.getElementById('entry-hours-chart');
    const emptyState = document.getElementById('stats-empty-state');
    const chartWrap = document.getElementById('stats-chart-wrap');
    const periodButtons = document.querySelectorAll('.stats-period-btn');

    const totalEl = document.getElementById('stats-total-entries');
    const peakHourEl = document.getElementById('stats-peak-hour');
    const peakCountEl = document.getElementById('stats-peak-count');
    const periodLabelEl = document.getElementById('stats-period-label');
    const dateRangeEl = document.getElementById('stats-date-range');

    let chart = null;
    let activePeriod = config.initialPeriod || 7;

    function parseInitialStats() {
        if (!dataScript) {
            return null;
        }
        try {
            return JSON.parse(dataScript.textContent);
        } catch (err) {
            console.error('[Stats] Datos iniciales inválidos:', err);
            return null;
        }
    }

    function formatPeakHour(stats) {
        if (!stats.total_entries || stats.peak_hour_label == null) {
            return '—';
        }
        return stats.peak_hour_label;
    }

    function formatPeakCount(stats) {
        if (!stats.total_entries) {
            return '—';
        }
        return String(stats.peak_count);
    }

    function updateKpis(stats) {
        if (totalEl) {
            totalEl.textContent = String(stats.total_entries);
        }
        if (peakHourEl) {
            peakHourEl.textContent = formatPeakHour(stats);
        }
        if (peakCountEl) {
            peakCountEl.textContent = formatPeakCount(stats);
        }
        if (periodLabelEl) {
            periodLabelEl.textContent = stats.period_label;
        }
        if (dateRangeEl) {
            dateRangeEl.textContent = stats.date_range;
        }
    }

    function toggleEmptyState(stats) {
        const hasData = stats.total_entries > 0;
        if (emptyState) {
            emptyState.classList.toggle('hidden', hasData);
        }
        if (chartWrap) {
            chartWrap.classList.toggle('hidden', !hasData);
        }
    }

    function buildChartOptions() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const value = context.parsed.y || 0;
                            return value === 1 ? '1 entrada' : value + ' entradas';
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(148, 163, 184, 0.12)' },
                    ticks: {
                        color: '#94a3b8',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12,
                    },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(148, 163, 184, 0.12)' },
                    ticks: {
                        color: '#94a3b8',
                        precision: 0,
                    },
                    title: {
                        display: true,
                        text: 'Entradas',
                        color: '#94a3b8',
                    },
                },
            },
        };
    }

    function renderChart(stats) {
        if (!canvas || typeof Chart === 'undefined') {
            return;
        }

        const dataset = {
            label: 'Entradas',
            data: stats.counts,
            backgroundColor: 'rgba(16, 185, 129, 0.75)',
            borderColor: '#10b981',
            borderWidth: 1,
            borderRadius: 4,
        };

        if (!chart) {
            chart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: stats.labels,
                    datasets: [dataset],
                },
                options: buildChartOptions(),
            });
            return;
        }

        chart.data.labels = stats.labels;
        chart.data.datasets[0].data = stats.counts;
        chart.update();
    }

    function setActivePeriodButton(periodDays) {
        periodButtons.forEach(function (button) {
            const isActive = Number(button.dataset.period) === Number(periodDays);
            button.classList.toggle('is-active', isActive);
            button.disabled = isActive;
        });
    }

    function applyStats(stats) {
        activePeriod = stats.period_days;
        updateKpis(stats);
        toggleEmptyState(stats);
        if (stats.total_entries > 0) {
            renderChart(stats);
        }
        setActivePeriodButton(activePeriod);
    }

    function fetchStats(periodDays) {
        if (!config.dataUrl) {
            return;
        }

        periodButtons.forEach(function (button) {
            button.disabled = true;
        });

        const url = config.dataUrl + '?period=' + encodeURIComponent(periodDays);
        fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (stats) {
                applyStats(stats);
            })
            .catch(function (err) {
                console.error('[Stats] Error al cargar datos:', err);
                setActivePeriodButton(activePeriod);
            });
    }

    periodButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            const periodDays = Number(button.dataset.period);
            if (!periodDays || periodDays === activePeriod) {
                return;
            }
            fetchStats(periodDays);
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const initialStats = parseInitialStats();
        if (initialStats) {
            applyStats(initialStats);
        }
    });
})();
