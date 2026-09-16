// ============================================================
// escaneo.js - Lógica del módulo de escáner
// Compatible con pistola Well 9322 (modo Keyboard Wedge)
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    const formEscaneo = document.getElementById('formEscaneo');
    const inputRut = document.getElementById('rutInput');

    const modalConfirmar = document.getElementById('modalConfirmarAsistencia');
    const infoAlumno = document.getElementById('info-alumno');
    const btnAceptar = document.getElementById('btnAceptarConfirmacion');
    const btnCancelar = document.getElementById('btnCancelarConfirmacion');
    const btnCerrarModal = document.getElementById('btnCerrarModalAsistencia');

    const modalAviso = document.getElementById('modalAviso');
    const modalAvisoBody = document.getElementById('modalAvisoBody');
    const btnAceptarAviso = document.getElementById('btnAceptarAviso');

    // Botón "Cambiar actividad"
    const btnCambiarActividad = document.getElementById('btnCambiarActividad');

    let rutPendiente = '';

    // ============================================================
    // LISTENERS DE MODALES (siempre, aunque no haya formulario)
    // ============================================================

    // Botón "Cambiar" → abre el modal de cambiar actividad
    if (btnCambiarActividad) {
        btnCambiarActividad.addEventListener('click', function (e) {
            e.preventDefault();
            openModal(document.getElementById('cambiarActividadModal'));
        });
    }

    // Botón "Aceptar" del modal de aviso
    if (btnAceptarAviso) {
        btnAceptarAviso.addEventListener('click', function () {
            closeModal(modalAviso);
            if (inputRut) {
                inputRut.value = '';
                inputRut.focus();
            }
        });
    }

    // Botones "Cerrar" y "Cancelar" del modal de confirmación
    [btnCerrarModal, btnCancelar].forEach(function (btn) {
        if (btn) {
            btn.addEventListener('click', function () {
                if (inputRut) {
                    inputRut.value = '';
                    inputRut.focus();
                }
            });
        }
    });

    // ============================================================
    // SI NO HAY FORMULARIO, NO HACEMOS NADA MÁS
    // ============================================================
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
        openModal(modalAviso);
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
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.confirmar) {
                    rutPendiente = inputRut.value;
                    if (infoAlumno) {
                        infoAlumno.innerHTML =
                            '<strong>' + data.alumno.nombre + '</strong><br>' +
                            'RUT: ' + data.alumno.rut + '<br>' +
                            'Carrera: ' + data.alumno.carrera + ' — ' + data.alumno.jornada;
                    }
                    openModal(modalConfirmar);
                } else if (!data.success) {
                    mostrarAviso(data.message);
                } else {
                    mostrarMensaje(data.message, 'success');
                    inputRut.value = '';
                    inputRut.focus();
                    setTimeout(function () { window.location.reload(); }, 1000);
                }
            })
            .catch(function (error) {
                console.error('Error al registrar asistencia:', error);
                mostrarAviso('Error al conectar con el servidor.');
            });
    }

    // ============================================================
    // LISTENERS DEL FORMULARIO
    // ============================================================
    inputRut.focus();

    // Pistola Well 9322: detecta el "Enter" que envía la pistola
    inputRut.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            procesarEnvio();
        }
    });

    // Submit del formulario
    formEscaneo.addEventListener('submit', function (e) {
        e.preventDefault();
        procesarEnvio();
    });

    // ============================================================
    // CONFIRMAR ASISTENCIA
    // ============================================================
    if (btnAceptar) {
        btnAceptar.addEventListener('click', function () {
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
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    closeModal(modalConfirmar);

                    if (data.success) {
                        mostrarMensaje(data.message, 'success');
                        inputRut.value = '';
                        inputRut.focus();
                        setTimeout(function () { window.location.reload(); }, 1000);
                    } else {
                        mostrarAviso(data.message);
                    }
                })
                .catch(function (error) {
                    console.error('Error al confirmar:', error);
                    mostrarAviso('Error al conectar con el servidor.');
                });
        });
    }
});