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

    // ============================================================
    // Utilidad: leer datos desde json_script
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

    // ============================================================
    // Configuración global de Chart.js
    // ============================================================
    Chart.defaults.font.family = "'Lato', 'Roboto', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#4a5568';

    // ============================================================
    // 1. Gráfico de Barras - Asistencia por Actividad (Top 5)
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
                        backgroundColor: 'rgba(0, 51, 102, 0.75)',
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
    // 2. Gráfico Donut - Distribución por Carrera
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
                type: 'doughnut',
                data: {
                    labels: labelsPastel,
                    datasets: [{
                        data: dataPastel,
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
                        legend: {
                            position: 'bottom',
                            labels: { boxWidth: 12, padding: 10, font: { size: 11 } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    const total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                                    const porcentaje = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
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
    // 3. Gráfico de Línea - Resumen de Actividades por Mes
    // ============================================================
    const ctxLinea = document.getElementById('graficoLinea');
    if (ctxLinea) {
        const labelsLinea = obtenerDatos('labels_linea');
        const dataProgramadas = obtenerDatos('data_programadas');
        const dataEnCurso = obtenerDatos('data_en_curso');
        const dataFinalizadas = obtenerDatos('data_finalizadas');

        if (labelsLinea.length === 0) {
            mostrarSinDatos(ctxLinea);
        } else {
            new Chart(ctxLinea, {
                type: 'line',
                data: {
                    labels: labelsLinea,
                    datasets: [
                        {
                            label: 'Programadas',
                            data: dataProgramadas,
                            borderColor: '#003366',
                            backgroundColor: 'rgba(0, 51, 102, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#003366'
                        },
                        {
                            label: 'En curso',
                            data: dataEnCurso,
                            borderColor: '#28a745',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#28a745'
                        },
                        {
                            label: 'Finalizadas',
                            data: dataFinalizadas,
                            borderColor: '#6c757d',
                            backgroundColor: 'rgba(108, 117, 125, 0.1)',
                            borderWidth: 2,
                            tension: 0.35,
                            fill: true,
                            pointRadius: 4,
                            pointBackgroundColor: '#6c757d'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1,
                                callback: function (v) { return formatoNumero.format(v); }
                            }
                        },
                        x: { grid: { display: false } }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            align: 'start',
                            labels: { boxWidth: 12, padding: 12, usePointStyle: true }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    return ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y);
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    // ============================================================
    // 4. Gráfico Comparativo - Inscritos vs Asistentes
    // ============================================================
    const ctxComp = document.getElementById('graficoComparativo');
    if (ctxComp) {
        const labelsComp = obtenerDatos('labels_comp');
        const dataInscritos = obtenerDatos('data_comp_inscritos');
        const dataAsistentes = obtenerDatos('data_comp_asistentes');

        if (labelsComp.length === 0) {
            mostrarSinDatos(ctxComp);
        } else {
            new Chart(ctxComp, {
                type: 'bar',
                data: {
                    labels: labelsComp,
                    datasets: [
                        {
                            label: 'Inscritos',
                            data: dataInscritos,
                            backgroundColor: 'rgba(0, 80, 158, 0.75)',
                            borderColor: 'rgba(0, 80, 158, 1)',
                            borderWidth: 1,
                            borderRadius: 4
                        },
                        {
                            label: 'Asistentes',
                            data: dataAsistentes,
                            backgroundColor: 'rgba(255, 193, 7, 0.75)',
                            borderColor: 'rgba(255, 193, 7, 1)',
                            borderWidth: 1,
                            borderRadius: 4
                        }
                    ]
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
                        legend: {
                            position: 'top',
                            align: 'end',
                            labels: { boxWidth: 12, padding: 12 }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    return ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y);
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    // ============================================================
    // 5. Gráfico Donut - Participación por Escuela
    // ============================================================
    const ctxEscuela = document.getElementById('graficoEscuela');
    if (ctxEscuela) {
        const labelsEscuela = obtenerDatos('labels_escuela');
        const dataEscuela = obtenerDatos('data_escuela');

        if (labelsEscuela.length === 0) {
            mostrarSinDatos(ctxEscuela);
        } else {
            const coloresEscuela = labelsEscuela.map(function (_, i) {
                return COLORES_INSTITUCIONALES[i % COLORES_INSTITUCIONALES.length];
            });

            new Chart(ctxEscuela, {
                type: 'doughnut',
                data: {
                    labels: labelsEscuela,
                    datasets: [{
                        data: dataEscuela,
                        backgroundColor: coloresEscuela,
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
                        legend: {
                            position: 'bottom',
                            labels: { boxWidth: 12, padding: 10, font: { size: 11 } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    const total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                                    const porcentaje = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
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
});