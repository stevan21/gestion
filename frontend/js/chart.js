// ===========================
// GRAPHIQUES
// ===========================

let charts = {};

//: Bleu pour l'attendu et le prevu, orange pour ce qui est acquis : les deux
//: series se distinguent sans recourir a une couleur hors palette.
const CHART_COLORS = {
    target: '#bfdbfe',
    achieved: '#1d4ed8',
    done: '#f97316',
    total: '#3b82f6'
};

/** Applique les couleurs de texte du thème courant aux axes. */
function chartTheme() {
    const dark = document.body.classList.contains('dark-mode');
    return {
        text: dark ? '#d1d5db' : '#4b5563',
        grid: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
    };
}

/** Détruit un graphique existant avant de le redessiner. */
function resetChart(key) {
    if (charts[key]) {
        charts[key].destroy();
        delete charts[key];
    }
}

/**
 * Convertit une clé de mois AAAA-MM en libellé court « janv. 26 ».
 */
function monthLabel(key) {
    const [year, month] = key.split('-').map(Number);
    const formatted = new Date(year, month - 1, 1)
        .toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
    return formatted.replace('.', '');
}

/**
 * Chiffre d'affaires attendu contre réalisé, mois par mois.
 */
async function drawRevenueChart(months = 6) {
    const canvas = document.getElementById('revenueChart');
    if (!canvas) return;

    try {
        const rows = await objectiveAPI.history(months);
        const theme = chartTheme();
        resetChart('revenue');

        charts.revenue = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: rows.map(r => monthLabel(r.month)),
                datasets: [
                    {
                        label: 'CA attendu',
                        data: rows.map(r => r.revenue_target),
                        backgroundColor: CHART_COLORS.target,
                        borderRadius: 4
                    },
                    {
                        label: 'CA réalisé',
                        data: rows.map(r => r.revenue_achieved),
                        backgroundColor: CHART_COLORS.achieved,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: theme.text, usePointStyle: true } },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label} : ${formatMoney(ctx.parsed.y)}`
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: theme.text }, grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: theme.text,
                            // Un axe en francs CFA compte sept chiffres :
                            // abrege, il reste lisible.
                            callback: (value) => formatMoneyCompact(value)
                        },
                        grid: { color: theme.grid }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Graphique du chiffre d\'affaires:', error);
    }
}

/**
 * Tâches créées et terminées sur les derniers jours.
 */
async function drawActivityChart(days = 14) {
    const canvas = document.getElementById('activityChart');
    if (!canvas) return;

    try {
        const rows = await dashboardAPI.activity(days);
        const theme = chartTheme();
        resetChart('activity');

        charts.activity = new Chart(canvas, {
            type: 'line',
            data: {
                labels: rows.map(r => formatDateShort(r.date)),
                datasets: [
                    {
                        label: 'Tâches prévues',
                        data: rows.map(r => r.total),
                        borderColor: CHART_COLORS.total,
                        backgroundColor: hexToRgba(CHART_COLORS.total, 0.12),
                        fill: true,
                        tension: 0.3
                    },
                    {
                        label: 'Terminées',
                        data: rows.map(r => r.done),
                        borderColor: CHART_COLORS.done,
                        backgroundColor: hexToRgba(CHART_COLORS.done, 0.12),
                        fill: true,
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: theme.text, usePointStyle: true } }
                },
                scales: {
                    x: { ticks: { color: theme.text }, grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        // Un compte de tâches est entier : pas de demi-graduation.
                        ticks: { color: theme.text, precision: 0 },
                        grid: { color: theme.grid }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Graphique d\'activité:', error);
    }
}

/** Convertit une couleur hexadécimale en rgba. */
function hexToRgba(hex, alpha = 0.1) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Dessine les graphiques du tableau de bord. */
async function initCharts() {
    // Les deux séries viennent d'endpoints distincts : les enchaîner ajoutait
    // un aller-retour d'attente pour rien.
    await Promise.all([drawRevenueChart(), drawActivityChart()]);
}

/** Redessine les graphiques après un changement de thème. */
async function refreshCharts() {
    await Promise.all([
        charts.revenue ? drawRevenueChart() : null,
        charts.activity ? drawActivityChart() : null
    ]);
}
