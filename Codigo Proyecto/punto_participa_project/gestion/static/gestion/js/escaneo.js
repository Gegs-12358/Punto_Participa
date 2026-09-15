// ============================================================
// escaneo.js - Lógica del módulo de escáner
// Compatible con pistola Well 9322 (modo Keyboard Wedge)
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    const formEscaneo = document.getElementById('formEscaneo');
    const inputRut = document.getElementById('rutInput');
    const metodoInput = document.getElementById('metodo_ingreso');

    const modalConfirmar = document.getElementById('modalConfirmarAsistencia');
    const infoAlumno = document.getElementById('info-alumno');
    const btnAceptar = document.getElementById('btnAceptarConfirmacion');
    const btnCancelar = document.getElementById('btnCancelarConfirmacion');
    const btnCerrarModal = document.getElementById('btnCerrarModalAsistencia');

    const modalAviso = document.getElementById('modalAviso');
    const modalAvisoBody = document.getElementById('modalAvisoBody');
    const btnAceptarAviso = document.getElementById('btnAceptarAviso');

    let rutPendiente = '';

    // Si no existe el formulario, no hacemos nada
    if (!formEscaneo || !inputRut) return;

    // ============================================================
    // FUNCIONES AUXILIARES
    // ============================================================
    function limpiarRUT(valor) {
        return valor.replace(/[^0-9kK]/g, '').toUpperCase();
    }

    function mostrarAviso(mensaje) {
        if (!modalAviso || !modalAvisoBody) return;
        modalAvisoBody.innerHTML = '<p class="mb-0">' + mensaje + '</p>';
        new bootstrap.Modal(modalAviso).show();
    }

    // ============================================================
    // PROCESAR ENVÍO (manual o pistola)
    // ============================================================
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
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCookie('csrftoken')
            },
            credentials: 'same-origin'
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.confirmar) {
                rutPendiente = inputRut.value;
                if (infoAlumno) {
                    infoAlumno.innerHTML =
                        '<strong>' + data.alumno.nombre + '</strong><br>' +
                        '<span class="text-muted">RUT: ' + data.alumno.rut + '</span><br>' +
                        '<span class="text-muted">Carrera: ' + data.alumno.carrera + ' - ' + data.alumno.jornada + '</span>';
                }
                new bootstrap.Modal(modalConfirmar).show();
            } else if (!data.success) {
                mostrarAviso(data.message);
            } else {
                mostrarMensaje(data.message, 'success');
                inputRut.value = '';
                inputRut.focus();
                setTimeout(function() { window.location.reload(); }, 1000);
            }
        })
        .catch(function(error) {
            console.error('Error al registrar asistencia:', error);
            mostrarAviso('Error al conectar con el servidor.');
        });
    }

    // ============================================================
    // LISTENERS
    // ============================================================
    inputRut.focus();

    // Pistola Well 9322: detecta el "Enter" que envía la pistola
    // También funciona con Enter manual
    inputRut.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            procesarEnvio();
        }
    });

    // Submit del formulario (por si el usuario presiona el botón)
    formEscaneo.addEventListener('submit', function(e) {
        e.preventDefault();
        procesarEnvio();
    });

    // ============================================================
    // CONFIRMAR ASISTENCIA
    // ============================================================
    if (btnAceptar) {
        btnAceptar.addEventListener('click', function() {
            if (!rutPendiente) return;

            const formData = new FormData(formEscaneo);
            formData.append('rut', rutPendiente);
            formData.append('confirmar', 'true');

            fetch('/escaneo/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                credentials: 'same-origin'
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                const modal = bootstrap.Modal.getInstance(modalConfirmar);
                if (modal) modal.hide();

                if (data.success) {
                    mostrarMensaje(data.message, 'success');
                    inputRut.value = '';
                    inputRut.focus();
                    setTimeout(function() { window.location.reload(); }, 1000);
                } else {
                    mostrarAviso(data.message);
                }
            })
            .catch(function(error) {
                console.error('Error al confirmar:', error);
                mostrarAviso('Error al conectar con el servidor.');
            });
        });
    }

    // ============================================================
    // CIERRE DE MODALES Y LIMPIEZA
    // ============================================================
    [btnCerrarModal, btnCancelar].forEach(function(btn) {
        if (btn) {
            btn.addEventListener('click', function() {
                inputRut.value = '';
                inputRut.focus();
            });
        }
    });

    if (modalAviso) {
        modalAviso.addEventListener('hidden.bs.modal', function() {
            inputRut.value = '';
            inputRut.focus();
        });
    }

    if (btnAceptarAviso) {
        btnAceptarAviso.addEventListener('click', function() {
            const modal = bootstrap.Modal.getInstance(modalAviso);
            if (modal) modal.hide();
        });
    }
});