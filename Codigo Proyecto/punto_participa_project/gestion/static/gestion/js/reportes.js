// ============================================================
// reportes.js - Gráficos de la vista de Reportes
// ============================================================

(function () {

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

        Chart.defaults.font.family = "'Lato', 'Roboto', system-ui, sans-serif";
        Chart.defaults.font.size = 12;
        Chart.defaults.color = '#4a5568';

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

        // ------------------------------------------------------------
        // Creador: Barras
        // ------------------------------------------------------------
        function crearBarras(canvasId, labelsId, dataId, colorsId, legendId) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;

            const labels = obtenerDatos(labelsId);
            const data = obtenerDatos(dataId);

            if (!labels.length) { mostrarSinDatos(canvas); return; }

            const colores = obtenerColores(colorsId, labels.length);

            const chart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Asistentes',
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
                        y: {
                            beginAtZero: true,
                            ticks: { stepSize: 1, callback: v => formatoNumero.format(v) }
                        },
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

            if (legendId) renderLegendColored(chart, legendId);
            return chart;
        }

        // ------------------------------------------------------------
        // Creador: Dona
        // ------------------------------------------------------------
        function crearDonut(canvasId, labelsId, dataId, colorsId, legendId) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;

            const labels = obtenerDatos(labelsId);
            const data = obtenerDatos(dataId);

            if (!labels.length) { mostrarSinDatos(canvas); return; }

            const colores = obtenerColores(colorsId, labels.length);

            const chart = new Chart(canvas, {
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

            if (legendId) renderLegendColored(chart, legendId);
            return chart;
        }

        // ------------------------------------------------------------
        // PESTAÑA GENERAL
        // ------------------------------------------------------------
        crearBarras('graficoBarrasReportes', 'labels_barras', 'data_barras', null, 'legendBarrasReportes');
        crearDonut('graficoPastelReportes', 'labels_pastel', 'data_pastel', 'data_colores_pastel', 'legendPastelReportes');
        crearBarras('graficoJornadaReportes', 'labels_jornada', 'data_jornada', null, 'legendJornadaReportes');

        // ------------------------------------------------------------
        // PESTAÑA DETALLADO
        // ------------------------------------------------------------
        crearBarras('graficoBarrasDetalle', 'labels_barras_detalle', 'data_barras_detalle', 'data_colores_barras_detalle', 'legendBarrasDetalle');
        crearDonut('graficoPastelDetalle', 'labels_pastel_detalle', 'data_pastel_detalle', 'data_colores_pastel_detalle', 'legendPastelDetalle');
        crearBarras('graficoJornadaDetalle', 'labels_jornada_detalle', 'data_jornada_detalle', null, 'legendJornadaDetalle');

        // ------------------------------------------------------------
        // TABS
        // ------------------------------------------------------------
        document.querySelectorAll('.tab-button').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const targetId = btn.getAttribute('data-tab');

                document.querySelectorAll('.tab-button').forEach(b => {
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                });
                document.querySelectorAll('.tab-content').forEach(c => {
                    c.classList.remove('active');
                    c.setAttribute('hidden', 'hidden');
                });

                btn.classList.add('active');
                btn.setAttribute('aria-selected', 'true');

                const target = document.getElementById(targetId);
                if (target) {
                    target.classList.add('active');
                    target.removeAttribute('hidden');
                }
            });
        });
    });

})();
