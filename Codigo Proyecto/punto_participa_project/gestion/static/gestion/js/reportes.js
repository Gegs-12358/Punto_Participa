// =============================================================
// reportes.js - Manejo de gráficos con pestañas (General y Detallado)
// =============================================================

// Variables para almacenar las instancias de los gráficos
let chartGeneralBar = null;
let chartGeneralPie = null;
let chartDetalleBar = null;
let chartDetallePie = null;

/**
 * Función auxiliar para crear un gráfico Chart.js
 */
function crearGrafico(canvasId, tipo, labels, data, label, opcionesExtra) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    // Si ya existe un gráfico en este canvas (por si se llama varias veces), lo destruimos
    // (pero usaremos variables globales para controlar mejor)
    const existingChart = Chart.getChart(canvasId);
    if (existingChart) {
        existingChart.destroy();
    }

    const labelsData = JSON.parse(labels);
    const dataData = JSON.parse(data);

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
 * Inicializar gráficos de la pestaña GENERAL
 */
function initGeneralCharts() {
    const barCanvas = document.getElementById('graficoBarrasReportes');
    const pieCanvas = document.getElementById('graficoPastelReportes');

    if (barCanvas && !chartGeneralBar) {
        chartGeneralBar = crearGrafico(
            'graficoBarrasReportes',
            'bar',
            barCanvas.dataset.labels,
            barCanvas.dataset.data,
            'Asistentes'
        );
    }

    if (pieCanvas && !chartGeneralPie) {
        chartGeneralPie = crearGrafico(
            'graficoPastelReportes',
            'pie',
            pieCanvas.dataset.labels,
            pieCanvas.dataset.data,
            'Distribución por Carrera'
        );
    }
}

/**
 * Inicializar gráficos de la pestaña DETALLADO
 */
function initDetalleCharts() {
    const barCanvas = document.getElementById('graficoBarrasDetalle');
    const pieCanvas = document.getElementById('graficoPastelDetalle');

    if (barCanvas && !chartDetalleBar) {
        chartDetalleBar = crearGrafico(
            'graficoBarrasDetalle',
            'bar',
            barCanvas.dataset.labels,
            barCanvas.dataset.data,
            'Asistentes por Escuela'
        );
    }

    if (pieCanvas && !chartDetallePie) {
        chartDetallePie = crearGrafico(
            'graficoPastelDetalle',
            'pie',
            pieCanvas.dataset.labels,
            pieCanvas.dataset.data,
            'Distribución por Carrera'
        );
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

document.addEventListener('DOMContentLoaded', function() {
    // Inicializar gráficos generales (visibles por defecto)
    initGeneralCharts();

    // Escuchar el cambio de pestaña para inicializar los gráficos detallados
    const detalleTab = document.getElementById('detallado-tab');
    if (detalleTab) {
        detalleTab.addEventListener('shown.bs.tab', function (e) {
            // Esperar un poco para que el contenedor se renderice
            setTimeout(() => {
                initDetalleCharts();
            }, 200);
        });
    }

    // Si la pestaña detallado ya está activa al cargar (por si se guarda estado),
    // también la inicializamos.
    if (document.getElementById('detallado') && document.getElementById('detallado').classList.contains('active')) {
        setTimeout(initDetalleCharts, 300);
    }
});