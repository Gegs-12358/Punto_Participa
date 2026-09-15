// ============================================================
// dashboard.js - Gráficos del Dashboard con Chart.js
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

    // Obtener datos desde json_script
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

    // ============================================================
    // Gráfico de Barras
    // ============================================================
    const ctxBarras = document.getElementById('graficoBarras');
    if (ctxBarras) {
        const labelsBarras = obtenerDatos('labels_barras');
        const dataBarras = obtenerDatos('data_barras');

        if (labelsBarras.length === 0) {
            mostrarSinDatos(ctxBarras);
        } else {
            new Chart(ctxBarras, {
                type: 'bar',
                data: {
                    labels: labelsBarras,
                    datasets: [{
                        label: 'Asistencias',
                        data: dataBarras,
                        backgroundColor: 'rgba(0, 51, 102, 0.7)',
                        borderColor: 'rgba(0, 51, 102, 1)',
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
                            ticks: {
                                stepSize: 1,
                                callback: function (v) { return formatoNumero.format(v); }
                            }
                        },
                        x: { ticks: { maxRotation: 45, minRotation: 0 } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    return 'Asistentes: ' + formatoNumero.format(ctx.parsed.y);
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    // ============================================================
    // Gráfico de Pastel
    // ============================================================
    const ctxPastel = document.getElementById('graficoPastel');
    if (ctxPastel) {
        const labelsPastel = obtenerDatos('labels_pastel');
        const dataPastel = obtenerDatos('data_pastel');

        if (labelsPastel.length === 0) {
            mostrarSinDatos(ctxPastel);
        } else {
            const colores = labelsPastel.map(function (_, i) {
                return COLORES_INSTITUCIONALES[i % COLORES_INSTITUCIONALES.length];
            });

            new Chart(ctxPastel, {
                type: 'pie',
                data: {
                    labels: labelsPastel,
                    datasets: [{
                        data: dataPastel,
                        backgroundColor: colores,
                        borderWidth: 1,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { boxWidth: 12, padding: 10, font: { size: 11 } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    const total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                                    const porcentaje = ((ctx.parsed / total) * 100).toFixed(1);
                                    return ctx.label + ': ' + formatoNumero.format(ctx.parsed) + ' (' + porcentaje + '%)';
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    // ============================================================
    // Funciones auxiliares
    // ============================================================
    function mostrarSinDatos(canvas) {
        if (canvas && canvas.parentElement) {
            canvas.parentElement.innerHTML =
                '<p class="text-muted text-center py-5">No hay datos disponibles.</p>';
        }
    }

    function mostrarErrorGraficos() {
        document.querySelectorAll('canvas').forEach(function (canvas) {
            if (canvas && canvas.parentElement) {
                canvas.parentElement.innerHTML =
                    '<p class="text-danger text-center py-5">Error al cargar los gráficos.</p>';
            }
        });
    }
});