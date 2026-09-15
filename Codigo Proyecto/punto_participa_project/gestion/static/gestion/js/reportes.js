// =============================================================
// reportes.js - Manejo de gráficos con pestañas (General y Detallado)
// =============================================================

// Variables para almacenar las instancias de los gráficos
let chartGeneralBar = null;
let chartGeneralPie = null;
let chartDetalleBar = null;
let chartDetallePie = null;

/**
 * Obtiene datos serializados de forma segura desde un <script type="application/json">
 * generado con el filtro {% json_script %} de Django.
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

    // Si ya existe un gráfico en este canvas, lo destruimos antes de crear uno nuevo
    const existingChart = Chart.getChart(canvasId);
    if (existingChart) {
        existingChart.destroy();
    }

    // Definir colores base
    const coloresBase = [
        '#003366', '#FFC107', '#28a745', '#dc3545',
        '#6c757d', '#17a2b8', '#fd7e14', '#6f42c1',
        '#20c997', '#e83e8c', '#6610f2', '#007bff'
    ];

    // Para gráficos de barras, usamos un solo color con opacidad
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

    // Mezclar opciones extra si se proporcionan
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
}

/**
 * Destruir todos los gráficos (opcional, para limpiar)
 */
function destroyAllCharts() {
    if (chartGeneralBar) { chartGeneralBar.destroy(); chartGeneralBar = null; }
    if (chartGeneralPie) { chartGeneralPie.destroy(); chartGeneralPie = null; }
    if (chartDetalleBar) { chartDetalleBar.destroy(); chartDetalleBar = null; }
    if (chartDetallePie) { chartDetallePie.destroy(); chartDetallePie = null; }
}

// =============================================================
// EVENTOS
// =============================================================

document.addEventListener('DOMContentLoaded', function () {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js no está cargado.');
        return;
    }

    // Inicializar gráficos generales (visibles por defecto)
    initGeneralCharts();

    // Escuchar el cambio de pestaña para inicializar los gráficos detallados
    const detalleTab = document.getElementById('detallado-tab');
    if (detalleTab) {
        detalleTab.addEventListener('shown.bs.tab', function () {
            setTimeout(function () {
                initDetalleCharts();
            }, 200);
        });
    }

    // Si la pestaña detallado ya está activa al cargar (por si se guarda estado)
    const tabDetallado = document.getElementById('detallado');
    if (tabDetallado && tabDetallado.classList.contains('active')) {
        setTimeout(initDetalleCharts, 300);
    }
});