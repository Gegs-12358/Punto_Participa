// ============================================================
// Punto Participa - Scripts personalizados (globales)
// ============================================================
//
// IMPORTANTE:
// - Este archivo NO debe contener lógica del escáner.
//   La lógica del escáner vive únicamente en escaneo.js.
// - Sistema de modales propio (sin Bootstrap).
// ============================================================

// ============================================================
// UTILIDADES GLOBALES
// ============================================================

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

function escapeHtml(texto) {
    const div = document.createElement('div');
    div.textContent = texto;
    return div.innerHTML;
}

// ============================================================
// SISTEMA DE MODALES (sin Bootstrap)
// ============================================================

let _ultimoFocoAntesDeModal = null;

function openModal(modalOrSelector) {
    const modal = typeof modalOrSelector === 'string'
        ? document.querySelector(modalOrSelector)
        : modalOrSelector;

    if (!modal) {
        console.warn('openModal: modal no encontrado', modalOrSelector);
        return;
    }

    _ultimoFocoAntesDeModal = document.activeElement;
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';

    const focusable = modal.querySelector('input, select, textarea, button, a[href]');
    if (focusable) {
        focusable.focus();
    }
}

function closeModal(modalOrSelector) {
    const modal = typeof modalOrSelector === 'string'
        ? document.querySelector(modalOrSelector)
        : modalOrSelector;

    if (!modal) return;

    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';

    if (_ultimoFocoAntesDeModal && document.body.contains(_ultimoFocoAntesDeModal)) {
        _ultimoFocoAntesDeModal.focus();
    }
    _ultimoFocoAntesDeModal = null;

    modal.dispatchEvent(new Event('modal:hidden'));
}

function closeAllModals() {
    document.querySelectorAll('.modal-backdrop').forEach(function (modal) {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
    });
    document.body.style.overflow = '';
}

document.addEventListener('click', function (e) {
    if (e.target.closest('[data-modal-close]')) {
        const modal = e.target.closest('.modal-backdrop');
        if (modal) closeModal(modal);
        return;
    }

    if (e.target.classList.contains('modal-backdrop')) {
        if (e.target.hasAttribute('data-modal-persistent')) return;
        closeModal(e.target);
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        const abierto = document.querySelector('.modal-backdrop:not([hidden])');
        if (abierto && !abierto.hasAttribute('data-modal-persistent')) {
            closeModal(abierto);
        }
    }
});

// ============================================================
// AVISO DE CAMBIOS SIN GUARDAR (formulario de Actividad)
// ============================================================

let formActividadModificado = false;

function marcarFormularioSinGuardar() {
    formActividadModificado = true;
}

function marcarFormularioGuardado() {
    formActividadModificado = false;
}

document.addEventListener('input', function (e) {
    if (e.target.closest('#formActividad')) {
        marcarFormularioSinGuardar();
    }
});

document.addEventListener('change', function (e) {
    if (e.target.closest('#formActividad')) {
        marcarFormularioSinGuardar();
    }
});

window.addEventListener('beforeunload', function (e) {
    if (!formActividadModificado) return;
    e.preventDefault();
    e.returnValue = '';
    return '';
});

document.addEventListener('DOMContentLoaded', function () {
    const actividadModal = document.getElementById('actividadModal');
    if (actividadModal) {
        actividadModal.addEventListener('modal:hidden', function () {
            marcarFormularioGuardado();
        });
    }
});

// ============================================================
// AVISO DE PÉRDIDA DE CONEXIÓN A INTERNET
// ============================================================

function mostrarAvisoSinConexion() {
    const toast = document.getElementById('toast-conexion');
    if (!toast) return;

    toast.textContent = '⚠ Sin conexión a internet. Los cambios podrían no guardarse.';
    toast.hidden = false;
}

function ocultarAvisoSinConexion() {
    const toast = document.getElementById('toast-conexion');
    if (!toast || toast.hidden) return;

    toast.hidden = true;
    mostrarMensaje('✓ Conexión restablecida.', 'success');
}

window.addEventListener('offline', mostrarAvisoSinConexion);
window.addEventListener('online', ocultarAvisoSinConexion);

document.addEventListener('DOMContentLoaded', function () {
    if (!navigator.onLine) {
        mostrarAvisoSinConexion();
    }
});

// ============================================================
// MOSTRAR MENSAJES (alertas y modal global)
// ============================================================

document.addEventListener('click', function (e) {
    if (e.target.closest('.hint-close')) {
        const banner = e.target.closest('.hint-banner');
        if (banner) {
            banner.style.display = 'none';
            try {
                localStorage.setItem('hint-dismissed', '1');
            } catch (err) {}
        }
    }
});

document.addEventListener('DOMContentLoaded', function () {
    try {
        if (localStorage.getItem('hint-dismissed') === '1') {
            document.querySelectorAll('.hint-banner').forEach(b => b.style.display = 'none');
        }
    } catch (err) {}
});

function abrirModalGlobal(titulo, mensaje, tipo) {
    tipo = tipo || 'danger';
    const modalGlobal = document.getElementById('globalMessageModal');
    if (!modalGlobal) {
        mostrarMensaje(mensaje, tipo);
        return;
    }

    let headerClass = '';
    let tituloDefault = 'Aviso del Sistema';
    if (tipo === 'danger') {
        headerClass = 'bg-danger';
        tituloDefault = 'Error';
    } else if (tipo === 'success') {
        headerClass = 'bg-success';
        tituloDefault = 'Éxito';
    } else if (tipo === 'warning') {
        headerClass = 'bg-warning';
        tituloDefault = 'Advertencia';
    }

    const modalTitle = document.getElementById('globalMessageTitle');
    const modalBody = document.getElementById('globalMessageBody');

    if (modalTitle) modalTitle.textContent = titulo || tituloDefault;
    if (modalBody) modalBody.innerHTML = mensaje;

    openModal(modalGlobal);
}

function mostrarMensaje(mensaje, tipo) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
        document.body.appendChild(toast);
    }

    toast.textContent = mensaje;
    toast.className = 'toast';
    if (tipo === 'danger' || tipo === 'error') {
        toast.classList.add('error');
    }
    toast.hidden = false;

    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(function () {
        toast.hidden = true;
    }, 4000);
}

// ============================================================
// LÓGICA DEL FORMULARIO DE ACTIVIDAD (cupos y fechas)
// ============================================================

function toggleCamposCupos() {
    const tipoSelect = document.getElementById('id_tipo');
    const camposCupos = document.getElementById('campos-cupos');
    if (!tipoSelect || !camposCupos) return;
    if (tipoSelect.value === 'MASIVA') {
        camposCupos.style.display = 'none';
        const cuposTotales = document.getElementById('id_cupos_totales');
        if (cuposTotales) cuposTotales.value = '';
    } else {
        camposCupos.style.display = 'block';
    }
}

// ============================================================
// VALIDACIÓN DE FECHAS Y HORAS (nuevos campos separados)
// ============================================================

/**
 * Combina fecha + hora de un par de inputs en un objeto Date.
 * Retorna null si falta alguno de los dos.
 */
function combinarFechaHora(idFecha, idHora) {
    const fechaEl = document.getElementById(idFecha);
    const horaEl = document.getElementById(idHora);
    if (!fechaEl || !horaEl || !fechaEl.value || !horaEl.value) return null;

    // Construye "YYYY-MM-DDTHH:MM:00"
    return new Date(fechaEl.value + 'T' + horaEl.value + ':00');
}

function validarFechas() {
    const inicio = combinarFechaHora('id_fecha_inicio_fecha', 'id_fecha_inicio_hora');
    const fin = combinarFechaHora('id_fecha_fin_fecha', 'id_fecha_fin_hora');

    if (inicio && fin && fin <= inicio) {
        mostrarMensaje('La fecha y hora de término debe ser posterior a la de inicio.', 'danger');

        // Limpiar solo los campos de fin
        const fechaFinEl = document.getElementById('id_fecha_fin_fecha');
        const horaFinEl = document.getElementById('id_fecha_fin_hora');
        if (fechaFinEl) fechaFinEl.value = '';
        if (horaFinEl) horaFinEl.value = '';

        if (fechaFinEl) fechaFinEl.focus();
        return false;
    }
    return true;
}

function actualizarMinFechaFin() {
    // Cuando cambia la fecha de inicio, actualizar el "min" de la fecha de fin
    const fechaInicioEl = document.getElementById('id_fecha_inicio_fecha');
    const fechaFinEl = document.getElementById('id_fecha_fin_fecha');
    if (fechaInicioEl && fechaFinEl && fechaInicioEl.value) {
        fechaFinEl.min = fechaInicioEl.value;

        // Si la fecha de fin ya no es válida, limpiarla
        if (fechaFinEl.value && fechaFinEl.value < fechaInicioEl.value) {
            fechaFinEl.value = '';
            const horaFinEl = document.getElementById('id_fecha_fin_hora');
            if (horaFinEl) horaFinEl.value = '';
        }
    }
}

function inicializarFormularioActividad() {
    toggleCamposCupos();
    actualizarMinFechaFin();
}

// ============================================================
// EVENTOS GLOBALES: change
// ============================================================

document.addEventListener('change', function (e) {
    if (e.target && e.target.id === 'id_tipo') toggleCamposCupos();

    // Cuando cambia la fecha de inicio, actualizar el min de fecha fin
    if (e.target && e.target.id === 'id_fecha_inicio_fecha') {
        actualizarMinFechaFin();
    }

    // Validar cuando cambia la hora de inicio (por si ya hay fecha/hora fin)
    if (e.target && e.target.id === 'id_fecha_inicio_hora') {
        const inicio = combinarFechaHora('id_fecha_inicio_fecha', 'id_fecha_inicio_hora');
        const fin = combinarFechaHora('id_fecha_fin_fecha', 'id_fecha_fin_hora');
        if (inicio && fin && fin <= inicio) {
            const fechaFinEl = document.getElementById('id_fecha_fin_fecha');
            const horaFinEl = document.getElementById('id_fecha_fin_hora');
            if (fechaFinEl) fechaFinEl.value = '';
            if (horaFinEl) horaFinEl.value = '';
        }
    }

    if (e.target && e.target.id === 'id_imagen') {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function (event) {
                let previewContainer = document.getElementById('preview-container');
                if (!previewContainer) {
                    previewContainer = document.createElement('div');
                    previewContainer.id = 'preview-container';
                    previewContainer.className = 'mt-2 text-center';
                    e.target.closest('.mb-3')?.appendChild(previewContainer);
                }
                previewContainer.innerHTML =
                    '<img src="' + event.target.result + '" class="img-preview-actividad" alt="Vista previa de la imagen">';
            };
            reader.readAsDataURL(file);
        }
    }
});

// ============================================================
// EVENTOS GLOBALES: click
// ============================================================

document.addEventListener('click', function (e) {

    // Seleccionar todas las carreras de una escuela
    if (e.target.closest('.btn-select-all')) {
        const btn = e.target.closest('.btn-select-all');
        const group = btn.getAttribute('data-group');
        const checkboxes = document.querySelectorAll('.carrera-checkbox[data-group="' + group + '"]');
        let allChecked = true;
        checkboxes.forEach(function (cb) { if (!cb.checked) allChecked = false; });
        checkboxes.forEach(function (cb) { cb.checked = !allChecked; });
    }

    // Checkbox "todas las jornadas"
    if (e.target && e.target.id === 'check_all_jornadas') {
        const checkAll = e.target.checked;
        document.querySelectorAll('.jornada-checkbox').forEach(function (checkbox) {
            checkbox.checked = checkAll;
        });
    }

    // Drop area de imagen
    if (e.target.closest('#drop-area')) {
        const input = document.getElementById('id_imagen');
        if (input) input.click();
    }

    // Botón "Nueva Actividad"
    if (e.target.closest('#btnNuevaActividad')) {
        e.preventDefault();
        cargarFormulario('/actividades/nueva/', 'Crear Actividad');
    }

    // Botón "Editar"
    if (e.target.closest('.btn-editar')) {
        e.preventDefault();
        const btn = e.target.closest('.btn-editar');
        const url = btn.getAttribute('data-url');
        cargarFormulario(url, 'Editar Actividad');
    }

    // Botón "Eliminar" (tabla de actividades)
    if (e.target.closest('.btn-eliminar')) {
        e.preventDefault();
        const btn = e.target.closest('.btn-eliminar');
        const url = btn.getAttribute('data-url');
        const nombre = btn.getAttribute('data-nombre') || 'esta actividad';

        if (!confirm('¿Estás seguro de eliminar "' + nombre + '"? Esta acción no se puede deshacer.')) {
            return;
        }

        btn.disabled = true;

        fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken },
            credentials: 'same-origin'
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success) {
                    mostrarMensaje('Actividad eliminada correctamente.', 'success');
                    setTimeout(function () { window.location.reload(); }, 1000);
                } else {
                    btn.disabled = false;
                    mostrarMensaje(data.message || 'No se pudo eliminar la actividad.', 'danger');
                }
            })
            .catch(function (error) {
                console.error('Error al eliminar actividad:', error);
                btn.disabled = false;
                mostrarMensaje('Error al conectar con el servidor.', 'danger');
            });
    }

    // Botón "Ahora no" en modal de invitaciones
    if (e.target.closest('#btnCancelarEnvio')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const tipo = modalInv.dataset.tipo;
        const esNueva = modalInv.dataset.esNueva === '1';
        const msg = document.getElementById('invitacion-message');
        const btnEliminar = document.getElementById('btnEliminarActividad');

        if (!esNueva) {
            closeModal(modalInv);
            setTimeout(function () { window.location.reload(); }, 300);
            return;
        }

        if (tipo === 'TALLER') {
            msg.className = 'alert alert-danger';
            msg.innerHTML = '<strong>Es obligatorio enviar invitaciones para talleres.</strong><br>Si no deseas enviarlas, debes eliminar la actividad recién creada.';
            btnEliminar.classList.remove('d-none');
            document.getElementById('btnCancelarEnvio').classList.add('d-none');
        } else {
            window.location.reload();
        }
    }

    // Botón "Eliminar actividad" en modal de invitaciones
    if (e.target.closest('#btnEliminarActividad')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const actividadId = modalInv.dataset.actividadId;
        if (confirm('¿Estás seguro de eliminar esta actividad? Esta acción no se puede deshacer.')) {
            fetch('/actividades/eliminar-ajax/' + actividadId + '/', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrftoken },
                credentials: 'same-origin'
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        closeModal(modalInv);
                        mostrarMensaje('Actividad eliminada correctamente.', 'success');
                        setTimeout(function () { window.location.reload(); }, 1500);
                    } else {
                        mostrarMensaje(data.message || 'Error al eliminar la actividad.', 'danger');
                    }
                })
                .catch(function (error) {
                    console.error('Error al eliminar actividad:', error);
                    mostrarMensaje('Error al conectar con el servidor.', 'danger');
                });
        }
    }

    // Botón "Enviar" en modal de invitaciones
    if (e.target.closest('#btnConfirmarEnvio')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const actividadId = modalInv.dataset.actividadId;
        const btnEnviar = document.getElementById('btnConfirmarEnvio');
        btnEnviar.disabled = true;
        btnEnviar.innerHTML = '◌ Enviando...';
        enviarInvitaciones(actividadId);
    }

    // Previsualizar / ocultar invitación
    if (e.target.closest('#btnVerPrevisualizacion')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const actividadId = modalInv.dataset.actividadId;
        const btn = e.target.closest('#btnVerPrevisualizacion');
        const container = document.getElementById('invitacion-preview-container');
        const iframe = document.getElementById('invitacion-preview-iframe');
        const ejemplo = document.getElementById('invitacion-ejemplo');
        const info = document.getElementById('invitacion-info-destinatarios');
        const total = document.getElementById('invitacion-total');

        if (!container.classList.contains('d-none')) {
            container.classList.add('d-none');
            iframe.srcdoc = '';
            btn.innerHTML = '◎ Ver cómo se verá el correo';
            return;
        }

        if (!actividadId) return;

        btn.disabled = true;
        btn.innerHTML = '◌ Cargando...';

        fetch('/actividades/previsualizar-invitacion/' + actividadId + '/', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                btn.disabled = false;

                if (data.success) {
                    iframe.srcdoc = data.html;
                    container.classList.remove('d-none');

                    if (data.total_destinatarios && data.total_destinatarios > 0) {
                        total.textContent = data.total_destinatarios;
                        info.classList.remove('d-none');
                    }

                    if (data.alumno_ejemplo) {
                        ejemplo.textContent = '(ejemplo con: ' + data.alumno_ejemplo + ')';
                    }

                    btn.innerHTML = '◉ Ocultar previsualización';
                } else {
                    btn.innerHTML = '◎ Ver cómo se verá el correo';
                    mostrarMensaje(data.message || 'No se pudo previsualizar.', 'danger');
                }
            })
            .catch(function (error) {
                console.error('Error al previsualizar:', error);
                btn.disabled = false;
                btn.innerHTML = '◎ Ver cómo se verá el correo';
                mostrarMensaje('Error al conectar con el servidor.', 'danger');
            });
    }
});

// ============================================================
// ENVÍO DEL FORMULARIO DE ACTIVIDAD (modal) + INVITACIONES
// ============================================================

document.addEventListener('submit', function (e) {
    const form = e.target;
    if (form.closest('#actividadModal') && form.id !== 'formEscaneo') {
        if (!validarFechas()) {
            e.preventDefault();
            return;
        }
        e.preventDefault();

        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success) {
                    closeModal(document.getElementById('actividadModal'));
                    marcarFormularioGuardado();

                    const modalInv = document.getElementById('modalConfirmarInvitaciones');
                    modalInv.dataset.actividadId = data.id;
                    modalInv.dataset.tipo = data.tipo;
                    modalInv.dataset.esNueva = data.es_nueva ? '1' : '0';

                    if (data.es_nueva) {
                        document.getElementById('invitacion-texto').innerHTML =
                            '¿Deseas enviar invitaciones por correo a los participantes?';
                    } else {
                        document.getElementById('invitacion-texto').innerHTML =
                            'Actividad actualizada correctamente. ¿Deseas reenviar las invitaciones por correo?';
                    }

                    document.getElementById('invitacion-resultado').innerHTML = '';
                    document.getElementById('btnEliminarActividad').classList.add('d-none');
                    document.getElementById('btnCancelarEnvio').classList.remove('d-none');
                    document.getElementById('btnConfirmarEnvio').classList.remove('d-none');
                    document.getElementById('btnConfirmarEnvio').disabled = false;
                    document.getElementById('btnConfirmarEnvio').innerHTML = '➤ Enviar';
                    document.getElementById('invitacion-message').className = 'alert alert-info';

                    const previewContainer = document.getElementById('invitacion-preview-container');
                    const previewIframe = document.getElementById('invitacion-preview-iframe');
                    const previewBtn = document.getElementById('btnVerPrevisualizacion');
                    if (previewContainer) previewContainer.classList.add('d-none');
                    if (previewIframe) previewIframe.srcdoc = '';
                    if (previewBtn) previewBtn.innerHTML = '◎ Ver cómo se verá el correo';
                    const infoDest = document.getElementById('invitacion-info-destinatarios');
                    if (infoDest) infoDest.classList.add('d-none');

                    openModal(modalInv);
                } else {
                    if (data.errors) {
                        const errores = JSON.parse(data.errors);
                        let mensaje = '<ul class="mb-0">';
                        const nombresCampos = {
                            titulo: 'Nombre', descripcion: 'Descripción', tipo: 'Tipo',
                            lugar: 'Lugar',
                            fecha_inicio_fecha: 'Fecha Inicio',
                            fecha_inicio_hora: 'Hora Inicio',
                            fecha_fin_fecha: 'Fecha Término',
                            fecha_fin_hora: 'Hora Término',
                            cupos_totales: 'Cupo Máximo',
                            carreras: 'Carreras', jornadas: 'Jornadas'
                        };
                        for (const campo in errores) {
                            const nombreCampo = nombresCampos[campo] || campo;
                            mensaje += '<li><strong>' + escapeHtml(nombreCampo) + ':</strong> ' +
                                escapeHtml(errores[campo][0].message) + '</li>';
                        }
                        mensaje += '</ul>';
                        abrirModalGlobal('Error de validación', mensaje, 'danger');
                    } else {
                        const modalBody = document.querySelector('#actividadModal .modal-body');
                        if (modalBody) modalBody.innerHTML = data.html;
                        inicializarFormularioActividad();
                    }
                }
            })
            .catch(function (error) {
                console.error('Error al guardar actividad:', error);
                mostrarMensaje('Error al conectar con el servidor.', 'danger');
            });
    }
});

function enviarInvitaciones(actividadId) {
    const formData = new FormData();
    formData.append('actividad_id', actividadId);

    fetch('/actividades/enviar-invitaciones/', {
        method: 'POST',
        body: formData,
        headers: { 'X-CSRFToken': csrftoken },
        credentials: 'same-origin'
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            const resultado = document.getElementById('invitacion-resultado');
            if (data.success) {
                resultado.innerHTML = '<div class="alert alert-success">' + escapeHtml(data.message) + '</div>';
                closeModal(document.getElementById('modalConfirmarInvitaciones'));
                setTimeout(function () { window.location.reload(); }, 2000);
            } else {
                resultado.innerHTML = '<div class="alert alert-danger">' + escapeHtml(data.message) + '</div>';
            }
        })
        .catch(function (error) {
            console.error('Error al enviar invitaciones:', error);
            const resultado = document.getElementById('invitacion-resultado');
            if (resultado) {
                resultado.innerHTML = '<div class="alert alert-danger">Error al conectar con el servidor.</div>';
            }
        });
}

// ============================================================
// CARGAR FORMULARIO DE ACTIVIDAD EN MODAL
// ============================================================

function cargarFormulario(url, titulo) {
    const separator = url.includes('?') ? '&' : '?';
    const urlConPartial = url + separator + 'partial=1';

    const label = document.getElementById('modalLabel');
    const body = document.getElementById('modalBody');
    if (!label || !body) {
        console.error('Modal no encontrado');
        return;
    }

    label.textContent = titulo;

    fetch(urlConPartial, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then(function (response) { return response.text(); })
        .then(function (html) {
            if (html.trim().startsWith('{')) {
                let data;
                try {
                    data = JSON.parse(html);
                } catch (error) {
                    console.error('Error al parsear respuesta JSON:', error);
                    mostrarMensaje('Error al cargar el formulario.', 'danger');
                    return;
                }

                if (data.requiere_confirmacion) {
                    if (confirm(data.mensaje)) {
                        const urlForzada = urlConPartial + '&forzar_edicion=true';
                        fetch(urlForzada, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                            .then(function (resp) { return resp.text(); })
                            .then(function (htmlForzado) {
                                body.innerHTML = htmlForzado;
                                inicializarFormularioActividad();
                                marcarFormularioGuardado();
                                openModal(document.getElementById('actividadModal'));

                                const form = document.getElementById('formActividad');
                                if (form) {
                                    const hidden = document.createElement('input');
                                    hidden.type = 'hidden';
                                    hidden.name = 'forzar_edicion';
                                    hidden.value = 'true';
                                    form.appendChild(hidden);
                                }
                            })
                            .catch(function (error) {
                                console.error('Error al cargar formulario forzado:', error);
                                mostrarMensaje('Error al cargar el formulario.', 'danger');
                            });
                    }
                    return;
                }

                if (data.success === false) {
                    abrirModalGlobal('Error', data.message, 'danger');
                    return;
                }
            }

            body.innerHTML = html;
            inicializarFormularioActividad();
            marcarFormularioGuardado();
            openModal(document.getElementById('actividadModal'));
        })
        .catch(function (error) {
            console.error('Error al cargar formulario:', error);
            mostrarMensaje('Error al cargar el formulario.', 'danger');
        });
}

// ============================================================
// VALIDACIÓN DINÁMICA DEL FORMULARIO DE ACTIVIDAD
// ============================================================

document.addEventListener('submit', function (e) {
    const form = e.target;
    if (form.id === 'formActividad') {
        const carrerasMarcadas = document.querySelectorAll('input[name="carreras"]:checked').length;
        const jornadasMarcadas = document.querySelectorAll('input[name="jornadas"]:checked').length;

        if (carrerasMarcadas === 0) {
            e.preventDefault();
            mostrarMensaje('Debes seleccionar al menos una Carrera.', 'warning');
            return;
        }
        if (jornadasMarcadas === 0) {
            e.preventDefault();
            mostrarMensaje('Debes seleccionar al menos una Jornada.', 'warning');
            return;
        }

        const tipoEl = document.getElementById('id_tipo');
        const cupo = document.getElementById('id_cupos_totales');
        if (tipoEl && tipoEl.value === 'TALLER' && cupo && (!cupo.value || cupo.value <= 0)) {
            e.preventDefault();
            mostrarMensaje('Si es un TALLER, debes indicar el Cupo Máximo.', 'warning');
            return;
        }
        if (tipoEl && tipoEl.value === 'MASIVA' && cupo) cupo.value = '';
    }
});

// ============================================================
// MODAL GLOBAL PARA MENSAJES DE DJANGO
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    const messageContainer = document.getElementById('django-messages-data');

    if (messageContainer && messageContainer.children.length > 0) {
        const firstMessage = messageContainer.querySelector('.msg');
        const messageText = firstMessage.textContent.trim();
        const messageType = firstMessage.getAttribute('data-type');

        if (messageType === 'error') {
            abrirModalGlobal('Error', messageText, 'danger');
        } else if (messageType === 'success') {
            abrirModalGlobal('Éxito', messageText, 'success');
        } else if (messageType === 'warning') {
            abrirModalGlobal('Advertencia', messageText, 'warning');
        } else {
            abrirModalGlobal('Aviso', messageText, 'primary');
        }
    }
});