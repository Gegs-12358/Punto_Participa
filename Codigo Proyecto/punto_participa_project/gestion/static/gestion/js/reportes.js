// ============================================================
// reportes.js - Gráficos de la vista de Reportes
// Pestaña General + Pestaña Detallado
// ============================================================

const COLORES_INSTITUCIONALES = [
    '#003366', '#FFC107', '#28a745', '#dc3545',
    '#6c757d', '#17a2b8', '#fd7e14', '#6f42c1',
    '#20c997', '#e83e8c', '#6610f2', '#007bff'
];

const formatoNumero = new Intl.NumberFormat('es-CL');

document.addEventListener('DOMContentLoaded', function () {

    // Verificar que Chart.js esté cargado
    if (typeof Chart === 'undefined') {
        console.error('Chart.js no está cargado.');
        mostrarErrorGraficos();
        return;
    }

    // ============================================================
    // Configuración global de Chart.js
    // ============================================================
    Chart.defaults.font.family = "'Lato', 'Roboto', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#4a5568';

    // ============================================================
    // Utilidades
    // ============================================================
    function obtenerDatos(id) {
        const elemento = document.getElementById(id);
        if (!elemento) return [];
        try {
            return JSON.parse(elemento.textContent);
        } catch (error) {
            console.error(`Error al parsear ${id}:`, error);
            return [];
        }
    }

    function calcularTotal(datos) {
        return datos.reduce(function (a, b) { return a + b; }, 0);
    }

    function mostrarSinDatos(canvas) {
        if (canvas && canvas.parentElement) {
            canvas.parentElement.innerHTML =
                '<p class="text-muted text-center" style="padding: 40px;">No hay datos disponibles.</p>';
        }
    }

    function mostrarErrorGraficos() {
        document.querySelectorAll('canvas').forEach(function (canvas) {
            if (canvas && canvas.parentElement) {
                canvas.parentElement.innerHTML =
                    '<p class="text-danger text-center" style="padding: 40px;">Error al cargar los gráficos.</p>';
            }
        });
    }

    // ============================================================
    // Configuración común para gráficos de barras
    // ============================================================
    function opcionesBarras(tituloSerie) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600 },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        callback: function (v) { return formatoNumero.format(v); }
                    }
                },
                x: {
                    ticks: { maxRotation: 45, minRotation: 0 }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            return tituloSerie + ': ' + formatoNumero.format(ctx.parsed.y);
                        }
                    }
                }
            }
        };
    }

    // ============================================================
    // Configuración común para gráficos de pastel / donut
    // ============================================================
    function opcionesDonut() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600 },
            cutout: '60%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 10,
                        font: { size: 11 },
                        generateLabels: function (chart) {
                            const data = chart.data;
                            if (!data.labels.length || !data.datasets.length) {
                                return [];
                            }
                            const dataset = data.datasets[0];
                            const total = calcularTotal(dataset.data);

                            return data.labels.map(function (label, i) {
                                const valor = dataset.data[i];
                                const porcentaje = total > 0
                                    ? ((valor / total) * 100).toFixed(1)
                                    : '0.0';
                                const color = dataset.backgroundColor[i];

                                return {
                                    text: `${label} — ${porcentaje}%`,
                                    fillStyle: color,
                                    strokeStyle: color,
                                    lineWidth: 0,
                                    hidden: isNaN(valor) || chart.getDatasetMeta(0).data[i].hidden,
                                    index: i
                                };
                            });
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            const total = calcularTotal(ctx.dataset.data);
                            const valor = ctx.parsed;
                            const porcentaje = total > 0
                                ? ((valor / total) * 100).toFixed(1)
                                : '0.0';
                            return (
                                ctx.label +
                                ': ' +
                                formatoNumero.format(valor) +
                                ' (' + porcentaje + '%)'
                            );
                        }
                    }
                }
            }
        };
    }

    // ============================================================
    // Función reutilizable: crear gráfico de barras
    // ============================================================
    function crearGraficoBarras(canvasId, labelsId, dataId, tituloSerie) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const labels = obtenerDatos(labelsId);
        const data = obtenerDatos(dataId);

        if (labels.length === 0 || data.length === 0) {
            mostrarSinDatos(canvas);
            return;
        }

        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: tituloSerie,
                    data: data,
                    backgroundColor: 'rgba(0, 51, 102, 0.75)',
                    borderColor: 'rgba(0, 51, 102, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: opcionesBarras(tituloSerie)
        });
    }

    // ============================================================
    // Función reutilizable: crear gráfico de donut
    // ============================================================
    function crearGraficoDonut(canvasId, labelsId, dataId) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        const labels = obtenerDatos(labelsId);
        const data = obtenerDatos(dataId);

        if (labels.length === 0 || data.length === 0) {
            mostrarSinDatos(canvas);
            return;
        }

        const colores = labels.map(function (_, i) {
            return COLORES_INSTITUCIONALES[i % COLORES_INSTITUCIONALES.length];
        });

        new Chart(canvas, {
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
            options: opcionesDonut()
        });
    }

    // ============================================================
    // PESTAÑA GENERAL
    // ============================================================
    crearGraficoBarras(
        'graficoBarrasReportes',
        'labels_barras',
        'data_barras',
        'Asistentes'
    );

    crearGraficoDonut(
        'graficoPastelReportes',
        'labels_pastel',
        'data_pastel'
    );

    crearGraficoBarras(
        'graficoJornadaReportes',
        'labels_jornada',
        'data_jornada',
        'Asistentes'
    );

    // ============================================================
    // PESTAÑA DETALLADO
    // ============================================================
    crearGraficoBarras(
        'graficoBarrasDetalle',
        'labels_barras_detalle',
        'data_barras_detalle',
        'Asistentes'
    );

    crearGraficoDonut(
        'graficoPastelDetalle',
        'labels_pastel_detalle',
        'data_pastel_detalle'
    );

    crearGraficoBarras(
        'graficoJornadaDetalle',
        'labels_jornada_detalle',
        'data_jornada_detalle',
        'Asistentes'
    );

    // ============================================================
    // TABS — Mostrar y ocultar pestañas
    // ============================================================
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            const targetId = button.getAttribute('data-tab');

            tabButtons.forEach(function (b) {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });

            tabContents.forEach(function (c) {
                c.classList.remove('active');
                c.setAttribute('hidden', 'hidden');
            });

            button.classList.add('active');
            button.setAttribute('aria-selected', 'true');

            const target = document.getElementById(targetId);
            if (target) {
                target.classList.add('active');
                target.removeAttribute('hidden');
            }
        });
    });
});