// ============================================================
// dashboard.js - Gráficos del Dashboard con Chart.js
// ============================================================

// Paleta de respaldo (solo se usa si el backend no envía colores)
const COLORES_FALLBACK = [
    '#132CAA', '#F1B634', '#2B9141', '#BF0249',
    '#F78B30', '#3CB8C1', '#9521B2', '#37A7C6',
    '#BDC601', '#939393'
];

const formatoNumero = new Intl.NumberFormat('es-CL');

document.addEventListener('DOMContentLoaded', function () {

    if (typeof Chart === 'undefined') {
        console.error('Chart.js no está cargado.');
        mostrarErrorGraficos();
        return;
    }

    // ------------------------------------------------------------
    // Utilidades
    // ------------------------------------------------------------
    function obtenerDatos(id) {
        const el = document.getElementById(id);
        if (!el) return [];
        try { return JSON.parse(el.textContent); }
        catch (e) { console.error('Error al parsear ' + id + ':', e); return []; }
    }

    function mostrarSinDatos(canvas) {
        if (canvas && canvas.parentElement) {
            canvas.parentElement.innerHTML =
                '<p class="text-muted text-center" style="padding:40px;">No hay datos disponibles.</p>';
        }
    }

    function mostrarErrorGraficos() {
        document.querySelectorAll('canvas').forEach(function (c) {
            if (c && c.parentElement) {
                c.parentElement.innerHTML =
                    '<p class="text-danger text-center" style="padding:40px;">Error al cargar los gráficos.</p>';
            }
        });
    }

    // Devuelve colores del backend o fallback
    function obtenerColores(colorsId, total) {
        const colores = colorsId ? obtenerDatos(colorsId) : [];
        return Array.from({ length: total }, (_, i) =>
            (colores && colores[i]) || COLORES_FALLBACK[i % COLORES_FALLBACK.length]
        );
    }

    // Leyenda HTML con texto coloreado (1 color por label)
    function renderLegendColored(chart, containerId) {
        const container = document.getElementById(containerId);
        if (!container || !chart) return;
        container.innerHTML = '';
        chart.data.labels.forEach(function (label, i) {
            const bg = chart.data.datasets[0].backgroundColor;
            const color = Array.isArray(bg) ? bg[i] : bg;
            const item = document.createElement('span');
            item.className = 'chart-legend-item';
            item.style.color = color;
            item.textContent = label;
            container.appendChild(item);
        });
    }

    // Leyenda HTML para múltiples datasets (línea, comparativo)
    function renderLegendDatasets(chart, containerId, key) {
        const container = document.getElementById(containerId);
        if (!container || !chart) return;
        container.innerHTML = '';
        chart.data.datasets.forEach(function (dataset) {
            const color = dataset[key] || dataset.borderColor || dataset.backgroundColor;
            const item = document.createElement('span');
            item.className = 'chart-legend-item';
            item.style.color = Array.isArray(color) ? color[0] : color;
            item.textContent = dataset.label;
            container.appendChild(item);
        });
    }

    // ------------------------------------------------------------
    // Configuración global
    // ------------------------------------------------------------
    Chart.defaults.font.family = "'Lato', 'Roboto', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#4a5568';

    // ------------------------------------------------------------
    // 1. Barras - Asistencia por Actividad (Top 5)
    //    Colores del backend (por escuela si aplica) o fallback
    // ------------------------------------------------------------
    const ctxBarras = document.getElementById('graficoBarras');
    if (ctxBarras) {
        const labels = obtenerDatos('labels_barras');
        const data = obtenerDatos('data_barras');

        if (!labels.length) {
            mostrarSinDatos(ctxBarras);
        } else {
            const colores = obtenerColores(null, labels.length);

            const chartBarras = new Chart(ctxBarras, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Asistencias',
                        data: data,
                        backgroundColor: colores,
                        borderColor: colores,
                        borderWidth: 1,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    scales: {
                        y: { beginAtZero: true, ticks: { stepSize: 1, callback: v => formatoNumero.format(v) } },
                        x: { ticks: { display: false }, grid: { display: false } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                title: ctx => ctx[0].label,
                                label: ctx => 'Asistentes: ' + formatoNumero.format(ctx.parsed.y)
                            }
                        }
                    }
                }
            });

            renderLegendColored(chartBarras, 'legendBarras');
        }
    }

    // ------------------------------------------------------------
    // 2. Dona - Distribución por Carrera
    //    Colores según escuela de cada carrera (backend)
    // ------------------------------------------------------------
    const ctxPastel = document.getElementById('graficoPastel');
    if (ctxPastel) {
        const labels = obtenerDatos('labels_pastel');
        const data = obtenerDatos('data_pastel');

        if (!labels.length) {
            mostrarSinDatos(ctxPastel);
        } else {
            const colores = obtenerColores('data_colores_pastel', labels.length);

            const chartPastel = new Chart(ctxPastel, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: colores,
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    cutout: '60%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                    return ctx.label + ': ' + formatoNumero.format(ctx.parsed) + ' (' + pct + '%)';
                                }
                            }
                        }
                    }
                }
            });

            renderLegendColored(chartPastel, 'legendPastel');
        }
    }

    // ------------------------------------------------------------
    // 3. Línea - Resumen de Actividades por Mes
    // ------------------------------------------------------------
    const ctxLinea = document.getElementById('graficoLinea');
    if (ctxLinea) {
        const labels = obtenerDatos('labels_linea');
        const dProg = obtenerDatos('data_programadas');
        const dCurso = obtenerDatos('data_en_curso');
        const dFin = obtenerDatos('data_finalizadas');

        if (!labels.length) {
            mostrarSinDatos(ctxLinea);
        } else {
            const chartLinea = new Chart(ctxLinea, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Programadas',
                            data: dProg,
                            borderColor: '#132CAA',
                            backgroundColor: 'rgba(19, 44, 170, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#132CAA'
                        },
                        {
                            label: 'En curso',
                            data: dCurso,
                            borderColor: '#2B9141',
                            backgroundColor: 'rgba(43, 145, 65, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#2B9141'
                        },
                        {
                            label: 'Finalizadas',
                            data: dFin,
                            borderColor: '#939393',
                            backgroundColor: 'rgba(147, 147, 147, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#939393'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { beginAtZero: true, ticks: { stepSize: 1, callback: v => formatoNumero.format(v) } },
                        x: { grid: { display: false } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y)
                            }
                        }
                    }
                }
            });

            renderLegendDatasets(chartLinea, 'legendLinea', 'borderColor');
        }
    }

    // ------------------------------------------------------------
// 4. Comparativo - Inscritos vs Asistentes
// ------------------------------------------------------------
const ctxComp = document.getElementById('graficoComparativo');
if (ctxComp) {
    const labels = obtenerDatos('labels_comp');
    const dInscritos = obtenerDatos('data_comp_inscritos');
    const dAsistentes = obtenerDatos('data_comp_asistentes');

    if (!labels.length) {
        mostrarSinDatos(ctxComp);
    } else {
        const chartComp = new Chart(ctxComp, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Inscritos',
                        data: dInscritos,
                        backgroundColor: 'rgba(0, 47, 95, 0.85)',
                        borderColor: '#002f5f',
                        borderWidth: 1,
                        borderRadius: 4,
                        barPercentage: 0.8,
                        categoryPercentage: 0.7
                    },
                    {
                        label: 'Asistentes',
                        data: dAsistentes,
                        backgroundColor: 'rgba(251, 184, 0, 0.85)',
                        borderColor: '#fbb800',
                        borderWidth: 1,
                        borderRadius: 4,
                        barPercentage: 0.8,
                        categoryPercentage: 0.7
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 600 },
                // FORZAR que las barras NO se apilen y siempre se vean ambas
                scales: {
                    x: {
                        stacked: false,
                        ticks: { display: false },
                        grid: { display: false }
                    },
                    y: {
                        stacked: false,
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1,
                            callback: v => formatoNumero.format(v)
                        }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: ctx => ctx[0].label,
                            label: ctx => ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y)
                        }
                    }
                }
            }
        });

        renderLegendDatasets(chartComp, 'legendComparativo', 'borderColor');
    }
}

    // ------------------------------------------------------------
    // 5. Dona - Participación por Escuela
    //    Colores oficiales del manual Duoc UC (desde el backend)
    // ------------------------------------------------------------
    const ctxEscuela = document.getElementById('graficoEscuela');
    if (ctxEscuela) {
        const labels = obtenerDatos('labels_escuela');
        const data = obtenerDatos('data_escuela');

        if (!labels.length) {
            mostrarSinDatos(ctxEscuela);
        } else {
            const colores = obtenerColores('data_colores_escuela', labels.length);

            const chartEscuela = new Chart(ctxEscuela, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: colores,
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    cutout: '60%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                    return ctx.label + ': ' + formatoNumero.format(ctx.parsed) + ' (' + pct + '%)';
                                }
                            }
                        }
                    }
                }
            });

            renderLegendColored(chartEscuela, 'legendEscuela');
        }
    }
});