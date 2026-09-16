// =============================================================
// reportes.js - Manejo de gráficos con pestañas (General y Detallado)
// Sin Bootstrap: tabs propias con data-tab
// =============================================================

// Variables para almacenar las instancias de los gráficos
let chartGeneralBar = null;
let chartGeneralPie = null;
let chartGeneralJornada = null;
let chartDetalleBar = null;
let chartDetallePie = null;
let chartDetalleJornada = null;

/**
 * Obtiene datos serializados de forma segura desde un <script type="application/json">
 */
function obtenerDatosJson(id) {
    const elemento = document.getElementById(id);
    if (!elemento) return [];
    try {
        return JSON.parse(elemento.textContent);
    } catch (error) {
        console.error(`Error al parsear datos de "${id}":`, error);
        return [];
    }
}

/**
 * Función auxiliar para crear un gráfico Chart.js
 */
function crearGrafico(canvasId, tipo, labelsData, dataData, label, opcionesExtra) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    if (!labelsData || labelsData.length === 0) {
        mostrarSinDatos(canvas);
        return null;
    }

    const existingChart = Chart.getChart(canvasId);
    if (existingChart) {
        existingChart.destroy();
    }

    const coloresBase = [
        '#003366', '#FFC107', '#28a745', '#dc3545',
        '#6c757d', '#17a2b8', '#fd7e14', '#6f42c1',
        '#20c997', '#e83e8c', '#6610f2', '#007bff'
    ];

    const backgroundColor = tipo === 'bar'
        ? 'rgba(0, 51, 102, 0.7)'
        : coloresBase.slice(0, dataData.length);

    const borderColor = tipo === 'bar'
        ? 'rgba(0, 51, 102, 1)'
        : coloresBase.slice(0, dataData.length);

    const config = {
        type: tipo,
        data: {
            labels: labelsData,
            datasets: [{
                label: label || (tipo === 'bar' ? 'Datos' : 'Distribución'),
                data: dataData,
                backgroundColor: backgroundColor,
                borderColor: borderColor,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: tipo === 'bar' ? 'top' : 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 10,
                        font: { size: 11 }
                    }
                }
            },
            scales: tipo === 'bar' ? {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1 }
                }
            } : undefined
        }
    };

    if (opcionesExtra) {
        config.options = { ...config.options, ...opcionesExtra };
    }

    return new Chart(canvas, config);
}

/**
 * Muestra un mensaje cuando no hay datos para un gráfico.
 */
function mostrarSinDatos(canvas) {
    if (canvas && canvas.parentElement) {
        canvas.parentElement.innerHTML =
            '<p class="text-muted text-center py-5">No hay datos disponibles.</p>';
    }
}

/**
 * Inicializar gráficos de la pestaña GENERAL
 */
function initGeneralCharts() {
    if (!chartGeneralBar) {
        const labels = obtenerDatosJson('labels_barras');
        const data = obtenerDatosJson('data_barras');
        chartGeneralBar = crearGrafico('graficoBarrasReportes', 'bar', labels, data, 'Asistentes');
    }

    if (!chartGeneralPie) {
        const labels = obtenerDatosJson('labels_pastel');
        const data = obtenerDatosJson('data_pastel');
        chartGeneralPie = crearGrafico('graficoPastelReportes', 'pie', labels, data, 'Distribución por Carrera');
    }

    if (!chartGeneralJornada) {
        const labels = obtenerDatosJson('labels_jornada');
        const data = obtenerDatosJson('data_jornada');
        chartGeneralJornada = crearGrafico('graficoJornadaReportes', 'bar', labels, data, 'Asistentes por Jornada');
    }
}

/**
 * Inicializar gráficos de la pestaña DETALLADO
 */
function initDetalleCharts() {
    if (!chartDetalleBar) {
        const labels = obtenerDatosJson('labels_barras_detalle');
        const data = obtenerDatosJson('data_barras_detalle');
        chartDetalleBar = crearGrafico('graficoBarrasDetalle', 'bar', labels, data, 'Asistentes por Escuela');
    }

    if (!chartDetallePie) {
        const labels = obtenerDatosJson('labels_pastel_detalle');
        const data = obtenerDatosJson('data_pastel_detalle');
        chartDetallePie = crearGrafico('graficoPastelDetalle', 'pie', labels, data, 'Distribución por Carrera');
    }

    if (!chartDetalleJornada) {
        const labels = obtenerDatosJson('labels_jornada_detalle');
        const data = obtenerDatosJson('data_jornada_detalle');
        chartDetalleJornada = crearGrafico('graficoJornadaDetalle', 'bar', labels, data, 'Asistentes por Jornada');
    }
}

/**
 * Destruir todos los gráficos (opcional, para limpiar)
 */
function destroyAllCharts() {
    if (chartGeneralBar) { chartGeneralBar.destroy(); chartGeneralBar = null; }
    if (chartGeneralPie) { chartGeneralPie.destroy(); chartGeneralPie = null; }
    if (chartGeneralJornada) { chartGeneralJornada.destroy(); chartGeneralJornada = null; }
    if (chartDetalleBar) { chartDetalleBar.destroy(); chartDetalleBar = null; }
    if (chartDetallePie) { chartDetallePie.destroy(); chartDetallePie = null; }
    if (chartDetalleJornada) { chartDetalleJornada.destroy(); chartDetalleJornada = null; }
}

// =============================================================
// EVENTOS
// =============================================================

document.addEventListener('DOMContentLoaded', function () {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js no está cargado.');
        return;
    }

    initGeneralCharts();

    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const targetId = this.dataset.tab;

            tabButtons.forEach(function (b) {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            tabContents.forEach(function (c) {
                c.classList.remove('active');
                c.hidden = true;
            });

            this.classList.add('active');
            this.setAttribute('aria-selected', 'true');

            const targetContent = document.getElementById(targetId);
            if (targetContent) {
                targetContent.classList.add('active');
                targetContent.hidden = false;
            }

            if (targetId === 'detallado-tab') {
                setTimeout(function () {
                    initDetalleCharts();
                }, 100);
            }
        });
    });
});