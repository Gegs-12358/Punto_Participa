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
            catch (e) { console.error('Error al leer ' + id + ':', e); return []; }
        }

        function mostrarSinDatos(canvas) {
            if (canvas && canvas.parentElement) {
                canvas.parentElement.innerHTML =
                    '<p class="grafico-vacio">No hay asistentes con estos filtros.</p>';
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

        function porcentaje(parte, total) {
            return total > 0 ? Math.round(parte / total * 100) + '%' : '0%';
        }

        function colorDe(colores, i) {
            return (colores && colores[i]) || COLORES_FALLBACK[i % COLORES_FALLBACK.length];
        }

        // Aclara un color hacia el blanco (0 = igual, 1 = blanco)
        function aclarar(hex, cuanto) {
            const n = parseInt(hex.replace('#', ''), 16);
            const mezcla = c => Math.round(c + (255 - c) * cuanto);
            const r = mezcla(n >> 16), g = mezcla((n >> 8) & 255), b = mezcla(n & 255);
            return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
        }

        // Varias carreras de una escuela: tonos cada vez más claros del color de la escuela
        function tonosPorEscuela(coloresBase, total) {
            const vistos = {};
            return Array.from({ length: total }, function (_, i) {
                const base = colorDe(coloresBase, i);
                const vez = vistos[base] || 0;
                vistos[base] = vez + 1;
                return aclarar(base, Math.min(vez * 0.14, 0.75));
            });
        }

        // Leyenda con muestra de color: [{color, texto}]
        function leyenda(containerId, items) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '';
            items.forEach(function (it) {
                const item = document.createElement('span');
                item.className = 'chart-legend-item chart-legend-item--muestra';
                item.style.setProperty('--muestra', it.color);
                item.textContent = it.texto;
                container.appendChild(item);
            });
        }

        // Lista numerada (el número coincide con el de la barra): [{color, texto, detalle}]
        function lista(containerId, items) {
            const ol = document.getElementById(containerId);
            if (!ol) return;
            ol.innerHTML = '';
            items.forEach(function (it) {
                const li = document.createElement('li');
                li.className = 'con-muestra';
                li.style.setProperty('--muestra', it.color);
                const nombre = document.createElement('span');
                nombre.className = 'grafico-lista__nombre';
                nombre.textContent = it.texto;
                const dato = document.createElement('strong');
                dato.textContent = it.detalle;
                li.appendChild(nombre);
                li.appendChild(dato);
                ol.appendChild(li);
            });
        }

        const ejeEntero = {
            beginAtZero: true,
            ticks: { precision: 0, callback: v => formatoNumero.format(v) },
            grid: { color: '#EEF1F5' }
        };

        // ------------------------------------------------------------
        // Barras verticales. numerar: el eje muestra 1, 2, 3... y los nombres van en una lista;
        // si no, el eje muestra el nombre y la leyenda la cantidad y el porcentaje.
        // ------------------------------------------------------------
        function crearBarras(canvasId, labelsId, dataId, colorsId, opciones) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const labels = obtenerDatos(labelsId);
            const data = obtenerDatos(dataId);
            if (!labels.length) { mostrarSinDatos(canvas); return; }

            const coloresBackend = colorsId ? obtenerDatos(colorsId) : [];
            const colores = labels.map((_, i) => colorDe(coloresBackend, i));
            const total = data.reduce((a, b) => a + b, 0);
            const numerar = opciones && opciones.listaId;

            new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: numerar ? labels.map((_, i) => String(i + 1)) : labels,
                    datasets: [{ label: 'Asistentes', data: data, backgroundColor: colores, borderRadius: 4,
                                 maxBarThickness: 56 }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 500 },
                    scales: {
                        y: ejeEntero,
                        x: { grid: { display: false },
                             ticks: numerar ? { font: { weight: '700' } }
                                          : { display: labels.every(l => l.length <= 14), maxRotation: 0 } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                title: items => labels[items[0].dataIndex],
                                label: ctx => 'Asistentes: ' + formatoNumero.format(ctx.parsed.y) +
                                    ' (' + porcentaje(ctx.parsed.y, total) + ')'
                            }
                        }
                    }
                }
            });

            if (numerar) {
                lista(opciones.listaId, labels.map((l, i) => ({
                    color: colores[i], texto: l, detalle: formatoNumero.format(data[i])
                })));
            } else if (opciones && opciones.legendId) {
                leyenda(opciones.legendId, labels.map((l, i) => ({
                    color: colores[i],
                    texto: l + ': ' + formatoNumero.format(data[i]) + ' (' + porcentaje(data[i], total) + ')'
                })));
            }
        }

        // ------------------------------------------------------------
        // Dona de carreras: tonos del color de la escuela, leyenda con cantidad y porcentaje
        // ------------------------------------------------------------
        function crearDonaCarreras(canvasId, labelsId, dataId, colorsId, escuelasId, legendId) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const labels = obtenerDatos(labelsId);
            const data = obtenerDatos(dataId);
            if (!labels.length) { mostrarSinDatos(canvas); return; }

            const colores = tonosPorEscuela(obtenerDatos(colorsId), labels.length);
            const escuelas = obtenerDatos(escuelasId);
            const total = data.reduce((a, b) => a + b, 0);

            new Chart(canvas, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{ data: data, backgroundColor: colores, borderWidth: 2, borderColor: '#fff' }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 500 },
                    cutout: '58%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => ctx.label + ': ' + formatoNumero.format(ctx.parsed) +
                                    ' (' + porcentaje(ctx.parsed, total) + ')',
                                footer: items => escuelas[items[0].dataIndex] || ''
                            }
                        }
                    }
                }
            });

            leyenda(legendId, labels.map((l, i) => ({
                color: colores[i],
                texto: l + ': ' + formatoNumero.format(data[i]) + ' (' + porcentaje(data[i], total) + ')'
            })));
        }

        // ------------------------------------------------------------
        // PESTAÑA GENERAL
        // ------------------------------------------------------------
        crearBarras('graficoBarrasReportes', 'labels_barras', 'data_barras', null,
                    { listaId: 'listaBarrasReportes' });
        crearDonaCarreras('graficoPastelReportes', 'labels_pastel', 'data_pastel', 'data_colores_pastel',
                          'escuelas_pastel', 'legendPastelReportes');
        crearBarras('graficoJornadaReportes', 'labels_jornada', 'data_jornada', null,
                    { legendId: 'legendJornadaReportes' });

        // ------------------------------------------------------------
        // PESTAÑA DETALLADO
        // ------------------------------------------------------------
        crearBarras('graficoBarrasDetalle', 'labels_barras_detalle', 'data_barras_detalle',
                    'data_colores_barras_detalle', { legendId: 'legendBarrasDetalle' });
        crearDonaCarreras('graficoPastelDetalle', 'labels_pastel_detalle', 'data_pastel_detalle',
                          'data_colores_pastel_detalle', 'escuelas_pastel_detalle', 'legendPastelDetalle');
        crearBarras('graficoJornadaDetalle', 'labels_jornada_detalle', 'data_jornada_detalle', null,
                    { legendId: 'legendJornadaDetalle' });

        // ------------------------------------------------------------
        // TABS
        // ------------------------------------------------------------
        function activarPestana(btn) {
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
        }

        const pestanas = document.querySelectorAll('.tab-button[data-tab]');
        pestanas.forEach(function (btn) {
            btn.addEventListener('click', function () {
                activarPestana(btn);
                // Recordar la vista en la URL (sin recargar) para que un F5 vuelva a ella.
                const url = new URL(window.location.href);
                if (btn.getAttribute('data-tab') === 'detallado-tab') {
                    url.searchParams.set('vista', 'detalle');
                } else {
                    url.searchParams.delete('vista');
                }
                window.history.replaceState(null, '', url);
            });
        });

        // Al filtrar, mantener la pestaña que se estaba mirando.
        const formFiltros = document.querySelector('form.filters-bar');
        if (formFiltros) {
            formFiltros.addEventListener('submit', function () {
                const activa = document.querySelector('.tab-button.active[data-tab="detallado-tab"]');
                if (activa && !formFiltros.querySelector('input[name="vista"]')) {
                    const oculto = document.createElement('input');
                    oculto.type = 'hidden';
                    oculto.name = 'vista';
                    oculto.value = 'detalle';
                    formFiltros.appendChild(oculto);
                }
            });
        }

        // Al paginar la tabla detallada (page_det) o volver con ?vista=detalle, abrir esa pestaña.
        const params = new URLSearchParams(window.location.search);
        if (params.get('vista') === 'detalle' || params.has('page_det')) {
            const btnDet = document.querySelector('.tab-button[data-tab="detallado-tab"]');
            if (btnDet) activarPestana(btnDet);
        }
    });

})();
