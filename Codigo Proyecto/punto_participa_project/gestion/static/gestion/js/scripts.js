// ============================================================
// Punto Participa - Scripts personalizados
// ============================================================
console.log('Scripts cargados correctamente.');

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

// ============================================================
// LÓGICA DE CUPOS Y FECHAS
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

function validarFechas() {
    const fechaInicio = document.getElementById('id_fecha_inicio');
    const fechaFin = document.getElementById('id_fecha_fin');
    if (fechaInicio && fechaFin && fechaInicio.value && fechaFin.value) {
        if (fechaFin.value <= fechaInicio.value) {
            alert('La fecha de fin debe ser posterior a la fecha de inicio.');
            fechaFin.value = '';
            fechaFin.focus();
            return false;
        }
    }
    return true;
}

function inicializarFormularioActividad() {
    toggleCamposCupos();
    const fechaInicio = document.getElementById('id_fecha_inicio');
    const fechaFin = document.getElementById('id_fecha_fin');
    if (fechaInicio && fechaFin && fechaInicio.value) {
        fechaFin.min = fechaInicio.value;
    }
}

// ============================================================
// LIMPIAR FONDO OSCURO AL CERRAR CUALQUIER MODAL
// ============================================================
document.addEventListener('hidden.bs.modal', function(event) {
    // Elimina cualquier backdrop residual que Bootstrap no haya quitado
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.classList.remove('show');
        backdrop.remove();
    });
    // Quita la clase 'modal-open' del body (evita que quede bloqueado)
    document.body.classList.remove('modal-open');
});

// ============================================================
// FUNCIÓN PARA ABRIR MODAL GLOBAL (Corregido)
// ============================================================
function abrirModalGlobal(titulo, mensaje, tipo = 'danger') {
    const modalGlobal = document.getElementById('globalMessageModal');
    if (!modalGlobal) {
        // Si no existe el modal, mostrar alerta flotante
        mostrarMensaje(mensaje, tipo);
        return;
    }

    // Configurar colores y textos
    let headerClass = 'bg-primary text-white';
    let tituloDefault = 'Aviso del Sistema';
    if (tipo === 'danger') {
        headerClass = 'bg-danger text-white';
        tituloDefault = 'Error';
    } else if (tipo === 'success') {
        headerClass = 'bg-success text-white';
        tituloDefault = 'Éxito';
    } else if (tipo === 'warning') {
        headerClass = 'bg-warning text-dark';
        tituloDefault = 'Advertencia';
    }

    const modalHeader = document.getElementById('globalMessageHeader');
    const modalTitle = document.getElementById('globalMessageTitle');
    const modalBody = document.getElementById('globalMessageBody');

    if (modalHeader) modalHeader.className = `modal-header ${headerClass}`;
    if (modalTitle) modalTitle.textContent = titulo || tituloDefault;
    if (modalBody) modalBody.innerHTML = mensaje;

    // Usar getOrCreateInstance para no crear instancias duplicadas
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalGlobal);
    modalInstance.show();
}

// ============================================================
// EVENTOS GLOBALES (Cambio de inputs, clics)
// ============================================================
document.addEventListener('change', function(e) {
    if (e.target && e.target.id === 'id_tipo') toggleCamposCupos();
    if (e.target && e.target.id === 'id_fecha_inicio') {
        const fechaInicio = e.target.value;
        const fechaFin = document.getElementById('id_fecha_fin');
        if (fechaInicio) {
            fechaFin.min = fechaInicio;
            if (fechaFin.value && fechaFin.value < fechaInicio) fechaFin.value = '';
        }
    }
    if (e.target && e.target.id === 'id_imagen') {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(event) {
                let previewContainer = document.getElementById('preview-container');
                if (!previewContainer) {
                    previewContainer = document.createElement('div');
                    previewContainer.id = 'preview-container';
                    previewContainer.className = 'mt-2 text-center';
                    e.target.closest('.mb-3').appendChild(previewContainer);
                }
                previewContainer.innerHTML = `<img src="${event.target.result}" style="max-width: 100%; max-height: 150px; border-radius: 5px;">`;
            };
            reader.readAsDataURL(file);
        }
    }
});

document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-select-all')) {
        const btn = e.target.closest('.btn-select-all');
        const group = btn.getAttribute('data-group');
        const checkboxes = document.querySelectorAll(`.carrera-checkbox[data-group="${group}"]`);
        let allChecked = true;
        checkboxes.forEach(cb => { if (!cb.checked) allChecked = false; });
        checkboxes.forEach(cb => { cb.checked = !allChecked; });
    }
    if (e.target && e.target.id === 'check_all_jornadas') {
        const checkAll = e.target.checked;
        document.querySelectorAll('.jornada-checkbox').forEach(checkbox => { checkbox.checked = checkAll; });
    }
    if (e.target.closest('#drop-area')) {
        const input = document.getElementById('id_imagen');
        if (input) input.click();
    }
    if (e.target.closest('#btnNuevaActividad')) {
        e.preventDefault();
        cargarFormulario('/actividades/nueva/', 'Crear Actividad');
    }
    if (e.target.closest('.btn-editar')) {
        e.preventDefault();
        const btn = e.target.closest('.btn-editar');
        const url = btn.getAttribute('data-url');
        cargarFormulario(url, 'Editar Actividad');
    }
    if (e.target.closest('#btnCancelarEnvio')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const tipo = modalInv.dataset.tipo;
        const msg = document.getElementById('invitacion-message');
        const btnEliminar = document.getElementById('btnEliminarActividad');
        if (tipo === 'TALLER') {
            msg.className = 'alert alert-danger';
            msg.innerHTML = `<strong>Es obligatorio enviar invitaciones para talleres.</strong><br>Si no deseas enviarlas, debes eliminar la actividad recién creada.`;
            btnEliminar.style.display = 'inline-block';
            document.getElementById('btnCancelarEnvio').style.display = 'none';
        } else {
            window.location.reload();
        }
    }
    if (e.target.closest('#btnEliminarActividad')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const actividadId = modalInv.dataset.actividadId;
        if (confirm('¿Estás seguro de eliminar esta actividad? Esta acción no se puede deshacer.')) {
            fetch(`/actividades/eliminar-ajax/${actividadId}/`, {
                method: 'POST', headers: { 'X-CSRFToken': csrftoken }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const modalConfirm = bootstrap.Modal.getInstance(modalInv);
                    if (modalConfirm) modalConfirm.hide();
                    mostrarMensaje('Actividad eliminada correctamente.', 'success');
                    setTimeout(() => { window.location.reload(); }, 1500);
                } else {
                    mostrarMensaje('Error al eliminar la actividad.', 'danger');
                }
            });
        }
    }
    if (e.target.closest('#btnConfirmarEnvio')) {
        const modalInv = document.getElementById('modalConfirmarInvitaciones');
        const actividadId = modalInv.dataset.actividadId;
        const btnEnviar = document.getElementById('btnConfirmarEnvio');
        btnEnviar.disabled = true;
        btnEnviar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
        enviarInvitaciones(actividadId);
    }
});

// ============================================================
// ENVÍO DEL FORMULARIO (ACTIVIDADES) - CON MODAL DE INVITACIONES
// ============================================================
document.addEventListener('submit', function(e) {
    const form = e.target;
    if (form.closest('#actividadModal') && form.id !== 'formEscaneo') {
        if (!validarFechas()) { e.preventDefault(); return; }
        e.preventDefault();
        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 1. Cerrar el modal de crear/editar
                const modal = bootstrap.Modal.getInstance(document.getElementById('actividadModal'));
                if (modal) modal.hide();
                
                // 2. Si la actividad fue guardada correctamente
                if (data.id) {
                    // Configurar el modal de invitaciones
                    const modalInv = document.getElementById('modalConfirmarInvitaciones');
                    modalInv.dataset.actividadId = data.id;
                    modalInv.dataset.tipo = data.tipo;
                    
                    // Resetear el modal de invitaciones
                    document.getElementById('invitacion-texto').innerHTML = '¿Deseas enviar invitaciones por correo a los participantes?';
                    document.getElementById('invitacion-resultado').innerHTML = '';
                    document.getElementById('btnEliminarActividad').style.display = 'none';
                    document.getElementById('btnCancelarEnvio').style.display = 'inline-block';
                    document.getElementById('btnConfirmarEnvio').style.display = 'inline-block';
                    document.getElementById('btnConfirmarEnvio').disabled = false;
                    document.getElementById('btnConfirmarEnvio').innerHTML = '<i class="fas fa-paper-plane"></i> Enviar';
                    document.getElementById('invitacion-message').className = 'alert alert-info';
                    
                    // Abrir el modal de invitaciones
                    const modalConfirm = new bootstrap.Modal(modalInv);
                    modalConfirm.show();
                } else {
                    // Si no hay ID, recargar la página
                    setTimeout(() => { window.location.reload(); }, 1500);
                }
            } else {
                // Manejo de errores de validación
                if (data.errors) {
                    let errores = JSON.parse(data.errors);
                    let mensaje = '<ul>';
                    const nombresCampos = {
                        'titulo': 'Nombre', 'descripcion': 'Descripción', 'tipo': 'Tipo',
                        'lugar': 'Lugar', 'estado': 'Estado', 'fecha_inicio': 'Fecha Inicio',
                        'fecha_fin': 'Fecha Término', 'cupos_totales': 'Cupo Máximo',
                        'cupos_disponibles': 'Cupos Disponibles', 'carreras': 'Carreras',
                        'jornadas': 'Jornadas'
                    };
                    for (let campo in errores) {
                        let nombreCampo = nombresCampos[campo] || campo;
                        mensaje += '<li><strong>' + nombreCampo + ':</strong> ' + errores[campo][0].message + '</li>';
                    }
                    mensaje += '</ul>';
                    abrirModalGlobal('Error de validación', mensaje, 'danger');
                } else {
                    const modalBody = document.querySelector('#actividadModal .modal-body');
                    if (modalBody) modalBody.innerHTML = data.html;
                    inicializarFormularioActividad();
                }
            }
        });
    }
});

function enviarInvitaciones(actividadId) {
    const formData = new FormData();
    formData.append('actividad_id', actividadId);

    fetch('/actividades/enviar-invitaciones/', {
        method: 'POST', body: formData, headers: { 'X-CSRFToken': csrftoken }
    })
    .then(response => response.json())
    .then(data => {
        const resultado = document.getElementById('invitacion-resultado');
        if (data.success) {
            resultado.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
            const modal = document.getElementById('modalConfirmarInvitaciones');
            bootstrap.Modal.getInstance(modal).hide();
            setTimeout(() => window.location.reload(), 2000);
        } else {
            resultado.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
        }
    });
}

function mostrarMensaje(mensaje, tipo) {
    const alerta = document.createElement('div');
    alerta.className = `alert alert-${tipo} alert-dismissible fade show`;
    alerta.innerHTML = `${mensaje}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    const container = document.querySelector('main') || document.body;
    if (container) {
        container.prepend(alerta);
        setTimeout(() => { alerta.remove(); }, 4000);
    }
}

// ============================================================
// CARGAR FORMULARIO EN MODAL (CORREGIDO para usar abrirModalGlobal)
// ============================================================
function cargarFormulario(url, titulo) {
    const separator = url.includes('?') ? '&' : '?';
    const urlConPartial = url + separator + 'partial=1';
    
    const label = document.getElementById('modalLabel');
    const body = document.getElementById('modalBody');
    if (!label || !body) { console.error("Modal no encontrado"); return; }

    label.textContent = titulo;
    fetch(urlConPartial, {
        // ¡CLAVE! Este encabezado permite que Django devuelva JSON en vez de redirigir
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.text())
    .then(html => {
        // 1. Verificar si el servidor devolvió un JSON de error (bloqueo por registros)
        if (html.trim().startsWith('{')) {
            let data = JSON.parse(html);
            if (data.success === false) {
                // Mostrar el mensaje usando la nueva función (evita el bug de pantalla oscura)
                abrirModalGlobal('Error', data.message, 'danger');
                return; // Detener el proceso, no abrir el modal de edición
            }
        }

        // 2. Si es HTML normal, procedemos a abrir el modal de edición
        body.innerHTML = html;
        inicializarFormularioActividad();
        const modal = new bootstrap.Modal(document.getElementById('actividadModal'));
        modal.show();
    });
}

// ============================================================
// ESCÁNER (Validación + Confirmación con Modal + Avisos en Modal)
// ============================================================
function limpiarRUT(valor) { return valor.replace(/[^0-9kK]/g, '').toUpperCase(); }

document.addEventListener('DOMContentLoaded', function() {
    const formEscaneo = document.getElementById('formEscaneo');
    const inputRut = document.getElementById('rutInput');
    
    // Elementos del Modal de Confirmación
    const modalConfirmar = document.getElementById('modalConfirmarAsistencia');
    const infoAlumno = document.getElementById('info-alumno');
    const btnAceptar = document.getElementById('btnAceptarConfirmacion');
    const btnCancelar = document.getElementById('btnCancelarConfirmacion');
    const btnCerrarModal = document.getElementById('btnCerrarModalAsistencia');
    
    // Elementos del Modal de Aviso
    const modalAviso = document.getElementById('modalAviso');
    const modalAvisoBody = document.getElementById('modalAvisoBody');
    const btnAceptarAviso = document.getElementById('btnAceptarAviso');
    
    let rutPendiente = '';

    // Función para procesar el envío
    function procesarEnvio() {
        let valorLimpio = limpiarRUT(inputRut.value);
        if (valorLimpio.length >= 9) valorLimpio = valorLimpio.slice(0, 9);
        inputRut.value = valorLimpio;
        
        if (!inputRut.value) { 
            inputRut.focus();
            return; 
        }

        const formData = new FormData(formEscaneo);
        formData.append('rut', inputRut.value);

        fetch('/escaneo/', {
            method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.confirmar) {
                rutPendiente = inputRut.value;
                infoAlumno.innerHTML = `
                    <strong>${data.alumno.nombre}</strong><br>
                    <span class="text-muted">RUT: ${data.alumno.rut}</span><br>
                    <span class="text-muted">Carrera: ${data.alumno.carrera} - ${data.alumno.jornada}</span>
                `;
                const modal = new bootstrap.Modal(modalConfirmar);
                modal.show();
            } else if (!data.success) {
                mostrarAviso(data.message);
            } else {
                mostrarMensaje(data.message, 'success');
                inputRut.value = '';
                inputRut.focus();
                setTimeout(() => window.location.reload(), 1500);
            }
        });
    }

    // Enfocar el campo al cargar
    if (inputRut) inputRut.focus();

    // Listener GLOBAL para el escáner físico
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Tab' || e.key === 'Enter') {
            if (document.activeElement === inputRut) {
                e.preventDefault();
                procesarEnvio();
            } else {
                e.preventDefault();
                inputRut.focus();
                procesarEnvio();
            }
        }
    });

    // Submit del formulario
    if (formEscaneo && inputRut) {
        formEscaneo.addEventListener('submit', function(e) {
            e.preventDefault();
            procesarEnvio();
        });

        btnAceptar.addEventListener('click', function() {
            if (!rutPendiente) return;
            const formData = new FormData(formEscaneo);
            formData.append('rut', rutPendiente);
            formData.append('confirmar', 'true');

            fetch('/escaneo/', {
                method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(response => response.json())
            .then(data => {
                const modal = bootstrap.Modal.getInstance(modalConfirmar);
                modal.hide();
                if (data.success) {
                    mostrarMensaje(data.message, 'success');
                    inputRut.value = '';
                    inputRut.focus();
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    mostrarAviso(data.message);
                }
            });
        });

        btnAceptarAviso.addEventListener('click', function() {
            const modal = bootstrap.Modal.getInstance(modalAviso);
            modal.hide();
            inputRut.value = '';
            inputRut.focus();
        });

        btnCerrarModal.addEventListener('click', function() {
            inputRut.value = '';
            inputRut.focus();
        });

        btnCancelar.addEventListener('click', function() {
            inputRut.value = '';
            inputRut.focus();
        });

        modalAviso.addEventListener('hidden.bs.modal', function() {
            inputRut.value = '';
            inputRut.focus();
        });
    }

    function mostrarAviso(mensaje) {
        modalAvisoBody.innerHTML = `<p class="mb-0">${mensaje}</p>`;
        const modal = new bootstrap.Modal(modalAviso);
        modal.show();
    }
});

// ============================================================
// Validación dinámica del formulario de actividad
// ============================================================
document.addEventListener('submit', function(e) {
    const form = e.target;
    if (form.id === 'formActividad') {
        const carrerasMarcadas = document.querySelectorAll('input[name="carreras"]:checked').length;
        const jornadasMarcadas = document.querySelectorAll('input[name="jornadas"]:checked').length;
        if (carrerasMarcadas === 0) {
            e.preventDefault();
            alert('Debes seleccionar al menos una Carrera.');
            return;
        }
        if (jornadasMarcadas === 0) {
            e.preventDefault();
            alert('Debes seleccionar al menos una Jornada.');
            return;
        }
        const tipo = document.getElementById('id_tipo').value;
        const cupo = document.getElementById('id_cupos_totales');
        if (tipo === 'TALLER' && (!cupo.value || cupo.value <= 0)) {
            e.preventDefault();
            alert('Si es un TALLER, debes indicar el Cupo Máximo.');
            return;
        }
        if (tipo === 'MASIVA') cupo.value = '';
    }
});

// ============================================================
// MODAL GLOBAL PARA MENSAJES DE DJANGO (CORREGIDO)
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const messageContainer = document.getElementById('django-messages-data');
    
    if (messageContainer && messageContainer.children.length > 0) {
        const firstMessage = messageContainer.querySelector('.msg');
        const messageText = firstMessage.textContent.trim();
        const messageType = firstMessage.getAttribute('data-type');
        
        // Usa la función abrirModalGlobal para abrir el modal sin dejar pantalla oscura
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