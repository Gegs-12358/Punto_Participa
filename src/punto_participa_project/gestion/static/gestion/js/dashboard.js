// ============================================================
// dashboard.js - Gráficos del Inicio con Chart.js
// Cada gráfico lleva una línea de ayuda en la plantilla que explica qué cuenta.
// ============================================================

(function () {

    const AZUL = '#002F5F';
    const AMARILLO = '#FBB800';
    const VERDE = '#2B9141';
    const GRIS = '#A0A7B4';
    const AZUL_CLARO = '#3D7BD9';
    const COLORES_RESPALDO = ['#132CAA', '#F1B634', '#2B9141', '#BF0249', '#F78B30', '#3CB8C1'];

    const formatoNumero = new Intl.NumberFormat('es-CL');

    document.addEventListener('DOMContentLoaded', function () {

        if (typeof Chart === 'undefined') {
            console.error('Chart.js no está cargado.');
            document.querySelectorAll('canvas').forEach(function (c) {
                c.parentElement.innerHTML =
                    '<p class="text-danger text-center" style="padding:40px;">Error al cargar los gráficos.</p>';
            });
            return;
        }

        // ------------------------------------------------------------
        // Utilidades
        // ------------------------------------------------------------
        function obtenerDatos(id) {
            const el = document.getElementById(id);
            if (!el) return [];
            try { return JSON.parse(el.textContent); }
            catch (e) { console.error('Error al leer ' + id + ':', e); return []; }
        }

        function mostrarSinDatos(canvas, texto) {
            if (canvas && canvas.parentElement) {
                canvas.parentElement.innerHTML =
                    '<p class="grafico-vacio">' + (texto || 'Todavía no hay datos para mostrar.') + '</p>';
            }
        }

        function recortar(texto, max) {
            return texto.length > max ? texto.slice(0, max - 1) + '…' : texto;
        }

        function porcentaje(parte, total) {
            return total > 0 ? Math.round(parte / total * 100) + '%' : '0%';
        }

        // Leyenda con una muestra de color por ítem: [{color, texto}]
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

        const ejeEntero = {
            beginAtZero: true,
            ticks: { precision: 0, callback: v => formatoNumero.format(v) },
            grid: { color: '#EEF1F5' }
        };

        Chart.defaults.font.family = "'Lato', 'Roboto', system-ui, sans-serif";
        Chart.defaults.font.size = 12;
        Chart.defaults.color = '#4a5568';

        // Lista numerada bajo un gráfico: [{texto, detalle, color}]
        function lista(containerId, items) {
            const ol = document.getElementById(containerId);
            if (!ol) return;
            ol.innerHTML = '';
            items.forEach(function (it) {
                const li = document.createElement('li');
                if (it.color) {
                    li.className = 'con-muestra';
                    li.style.setProperty('--muestra', it.color);
                }
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

        // Aclara un color hacia el blanco (0 = igual, 1 = blanco)
        function aclarar(hex, cuanto) {
            const n = parseInt(hex.replace('#', ''), 16);
            const mezcla = c => Math.round(c + (255 - c) * cuanto);
            const r = mezcla(n >> 16), g = mezcla((n >> 8) & 255), b = mezcla(n & 255);
            return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
        }

        // ------------------------------------------------------------
        // 1. Actividades por mes: una línea por estado, calculado con las fechas
        // ------------------------------------------------------------
        const ctxMeses = document.getElementById('graficoMeses');
        if (ctxMeses) {
            const labels = obtenerDatos('labels_meses');
            const fin = obtenerDatos('data_meses_finalizadas');
            const curso = obtenerDatos('data_meses_en_curso');
            const prox = obtenerDatos('data_meses_proximas');
            const actual = obtenerDatos('mes_actual');
            const total = fin.concat(curso, prox).reduce((a, b) => a + b, 0);

            if (!labels.length || total === 0) {
                mostrarSinDatos(ctxMeses, 'No hay actividades en estos meses.');
            } else {
                const etiquetas = labels.map((l, i) => i === actual ? [l, '(este mes)'] : l);
                const linea = (label, data, color) => ({
                    label: label, data: data, borderColor: color, backgroundColor: color,
                    borderWidth: 2.5, tension: 0, fill: false, pointRadius: 4, pointHoverRadius: 6
                });
                new Chart(ctxMeses, {
                    type: 'line',
                    data: {
                        labels: etiquetas,
                        datasets: [
                            linea('Terminadas', fin, GRIS),
                            linea('En curso', curso, VERDE),
                            linea('Próximas', prox, AZUL_CLARO)
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 500 },
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { grid: { display: false },
                                 ticks: { font: ctx => ({ weight: ctx.index === actual ? '800' : '400' }) } },
                            y: Object.assign({ title: { display: true, text: 'Actividades' } }, ejeEntero)
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    title: items => labels[items[0].dataIndex],
                                    label: ctx => ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y),
                                    footer: items => 'Total del mes: ' + formatoNumero.format(
                                        items.reduce((a, it) => a + it.parsed.y, 0))
                                }
                            }
                        }
                    }
                });
                leyenda('legendMeses', [
                    { color: GRIS, texto: 'Terminadas' },
                    { color: VERDE, texto: 'En curso ahora' },
                    { color: AZUL_CLARO, texto: 'Próximas' }
                ]);
            }
        }

        // ------------------------------------------------------------
        // 2. Talleres realizados: inscritos y asistentes (barras verticales numeradas + lista)
        // ------------------------------------------------------------
        const ctxComp = document.getElementById('graficoComparativo');
        if (ctxComp) {
            const labels = obtenerDatos('labels_comp');
            const insc = obtenerDatos('data_comp_inscritos');
            const asis = obtenerDatos('data_comp_asistentes');

            if (!labels.length) {
                mostrarSinDatos(ctxComp, 'Todavía no hay talleres realizados con inscritos.');
            } else {
                new Chart(ctxComp, {
                    type: 'bar',
                    data: {
                        labels: labels.map((_, i) => String(i + 1)),
                        datasets: [
                            { label: 'Inscritos', data: insc, backgroundColor: AZUL, borderRadius: 3,
                              maxBarThickness: 34, categoryPercentage: 0.7 },
                            { label: 'Asistentes', data: asis, backgroundColor: AMARILLO, borderRadius: 3,
                              maxBarThickness: 34, categoryPercentage: 0.7 }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 500 },
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { grid: { display: false }, ticks: { font: { weight: '700' } } },
                            y: ejeEntero
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    title: items => labels[items[0].dataIndex],
                                    label: ctx => ctx.dataset.label + ': ' + formatoNumero.format(ctx.parsed.y),
                                    footer: items => {
                                        const i = items[0].dataIndex;
                                        return 'Asistió el ' + porcentaje(asis[i], insc[i]) + ' de los inscritos';
                                    }
                                }
                            }
                        }
                    }
                });
                leyenda('legendComparativo', [
                    { color: AZUL, texto: 'Inscritos' },
                    { color: AMARILLO, texto: 'Asistentes' }
                ]);
                lista('listaComparativo', labels.map((l, i) => ({
                    texto: l,
                    detalle: formatoNumero.format(asis[i]) + ' de ' + formatoNumero.format(insc[i]) +
                        ' (' + porcentaje(asis[i], insc[i]) + ')'
                })));
            }
        }

        // ------------------------------------------------------------
        // 3. Actividades con más asistentes (barras verticales numeradas + lista)
        // ------------------------------------------------------------
        const ctxBarras = document.getElementById('graficoBarras');
        if (ctxBarras) {
            const labels = obtenerDatos('labels_barras');
            const data = obtenerDatos('data_barras');
            const tipos = obtenerDatos('tipos_barras');

            if (!labels.length) {
                mostrarSinDatos(ctxBarras, 'Todavía no hay asistencias registradas.');
            } else {
                const colores = labels.map((_, i) => COLORES_RESPALDO[i % COLORES_RESPALDO.length]);
                new Chart(ctxBarras, {
                    type: 'bar',
                    data: {
                        labels: labels.map((_, i) => String(i + 1)),
                        datasets: [{ label: 'Asistentes', data: data, backgroundColor: colores, borderRadius: 4,
                                     maxBarThickness: 48 }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 500 },
                        scales: {
                            x: { grid: { display: false }, ticks: { font: { weight: '700' } } },
                            y: ejeEntero
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    title: items => labels[items[0].dataIndex],
                                    label: ctx => 'Asistentes: ' + formatoNumero.format(ctx.parsed.y),
                                    footer: items => tipos[items[0].dataIndex] ? 'Tipo: ' + tipos[items[0].dataIndex] : ''
                                }
                            }
                        }
                    }
                });
                lista('listaBarras', labels.map((l, i) => ({
                    texto: l, color: colores[i], detalle: formatoNumero.format(data[i])
                })));
            }
        }

        // ------------------------------------------------------------
        // 4. Carreras con más asistentes (dona; tonos del color de su escuela)
        // ------------------------------------------------------------
        const ctxPastel = document.getElementById('graficoPastel');
        if (ctxPastel) {
            const labels = obtenerDatos('labels_pastel');
            const data = obtenerDatos('data_pastel');
            const coloresEscuela = obtenerDatos('data_colores_pastel');
            const escuelas = obtenerDatos('escuelas_pastel');
            const total = obtenerDatos('total_carreras');

            if (!labels.length) {
                mostrarSinDatos(ctxPastel, 'Todavía no hay asistencias registradas.');
            } else {
                // Dos carreras de la misma escuela no quedan con el mismo color: la segunda va más clara
                const repetidos = {};
                const colores = labels.map(function (_, i) {
                    const base = coloresEscuela[i] || COLORES_RESPALDO[i % COLORES_RESPALDO.length];
                    const vez = repetidos[base] || 0;
                    repetidos[base] = vez + 1;
                    return aclarar(base, Math.min(vez * 0.28, 0.7));
                });
                new Chart(ctxPastel, {
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
                                        ' (' + porcentaje(ctx.parsed, total) + ' del total)',
                                    footer: items => escuelas[items[0].dataIndex] || ''
                                }
                            }
                        }
                    }
                });
                leyenda('legendPastel', labels.map((l, i) => ({
                    color: colores[i],
                    texto: l + ': ' + formatoNumero.format(data[i]) +
                        ' (' + porcentaje(data[i], total) + ')'
                })));
            }
        }

        // ------------------------------------------------------------
        // 5. Asistentes por escuela (dona con número y porcentaje en la leyenda)
        // ------------------------------------------------------------
        const ctxEscuela = document.getElementById('graficoEscuela');
        if (ctxEscuela) {
            const labels = obtenerDatos('labels_escuela');
            const data = obtenerDatos('data_escuela');
            const colores = obtenerDatos('data_colores_escuela');

            if (!labels.length) {
                mostrarSinDatos(ctxEscuela, 'Todavía no hay asistencias registradas.');
            } else {
                const total = data.reduce((a, b) => a + b, 0);
                const color = i => colores[i] || COLORES_RESPALDO[i % COLORES_RESPALDO.length];
                new Chart(ctxEscuela, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{ data: data, backgroundColor: labels.map((_, i) => color(i)),
                                     borderWidth: 2, borderColor: '#fff' }]
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
                                        ' (' + porcentaje(ctx.parsed, total) + ')'
                                }
                            }
                        }
                    }
                });
                leyenda('legendEscuela', labels.map((l, i) => ({
                    color: color(i),
                    texto: l.replace(/^Escuela de /, '') + ': ' + formatoNumero.format(data[i]) +
                        ' (' + porcentaje(data[i], total) + ')'
                })));
            }
        }
    });

})();
