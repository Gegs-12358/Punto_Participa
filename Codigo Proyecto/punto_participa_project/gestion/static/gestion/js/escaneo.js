// ============================================================
// escaneo.js - Lógica del módulo de escáner
// Compatible con pistola Well 9322 (modo Keyboard Wedge)
// Soporta RUT, Pasaporte, RUN provisorio y Cédula de extranjero
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

    const btnCambiarActividad = document.getElementById('btnCambiarActividad');
    const listaRegistros = document.querySelector('.lista-ultimos-registros');

    let rutPendiente = '';
    let ultimoAlumno = null;
    let ultimoMetodo = 'RUT';

    // ============================================================
    // LISTENERS DE MODALES (siempre, aunque no haya formulario)
    // ============================================================
    if (btnCambiarActividad) {
        btnCambiarActividad.addEventListener('click', function (e) {
            e.preventDefault();
            openModal(document.getElementById('cambiarActividadModal'));
        });
    }

    if (btnAceptarAviso) {
        btnAceptarAviso.addEventListener('click', function () {
            closeModal(modalAviso);
            enfocarInput();
        });
    }

    [btnCerrarModal, btnCancelar].forEach(function (btn) {
        if (btn) {
            btn.addEventListener('click', function () {
                enfocarInput();
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

    /**
     * NO eliminamos caracteres. El backend decide el formato.
     * Solo limpiamos espacios y pasamos a mayúsculas.
     * Esto permite RUT, pasaportes, RUN provisorio, etc.
     */
    function limpiarDocumento(valor) {
        return valor.trim().toUpperCase();
    }

    function enfocarInput() {
        inputRut.value = '';
        inputRut.focus();
    }

    function mostrarAviso(mensaje) {
        if (!modalAviso || !modalAvisoBody) return;
        modalAvisoBody.innerHTML = '<p class="mb-0">' + mensaje + '</p>';
        openModal(modalAviso);
    }

    /**
     * Inserta el alumno en la lista de "Últimos registros" sin recargar.
     */
    function agregarRegistroALaLista(alumno, metodo, hora) {
        if (!listaRegistros) return;

        // Quitar el mensaje "Sin registros aún" si existe
        const vacio = listaRegistros.querySelector('p');
        if (vacio) vacio.remove();

        // Iniciales del nombre
        const partes = alumno.nombre.split(' ');
        const iniciales = (
            (partes[0] ? partes[0][0] : '') +
            (partes[1] ? partes[1][0] : '')
        ).toUpperCase();

        // Ícono del método
        let metodoTexto = '⌨ RUT';
        if (metodo === 'QR') metodoTexto = '▢ QR';
        else if (metodo === 'CODIGO') metodoTexto = '▥ Código';

        const item = document.createElement('div');
        item.className = 'person';
        item.style.animation = 'fadeIn 0.3s ease';
        item.innerHTML =
            '<span class="avatar">' + iniciales + '</span>' +
            '<p>' +
                '<strong>' + alumno.nombre + '</strong>' +
                '<small>' + metodoTexto + '</small>' +
            '</p>' +
            '<time>' + hora + '</time>';

        listaRegistros.insertBefore(item, listaRegistros.firstChild);

        // Mantener máximo 10 items
        const items = listaRegistros.querySelectorAll('.person');
        if (items.length > 10) {
            items[items.length - 1].remove();
        }
    }

    function horaActual() {
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        return hh + ':' + mm;
    }

    // ============================================================
    // PROCESAR ENVÍO (manual o pistola)
    // ============================================================
    function procesarEnvio() {
        let valorLimpio = limpiarDocumento(inputRut.value);
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
                    // El backend pide confirmación → mostrar modal
                    rutPendiente = inputRut.value;
                    ultimoAlumno = data.alumno;
                    ultimoMetodo = 'RUT';

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
                    // Registro exitoso directo
                    mostrarMensaje(data.message, 'success');
                    if (data.alumno) {
                        ultimoAlumno = data.alumno;
                    }
                    if (ultimoAlumno) {
                        agregarRegistroALaLista(ultimoAlumno, ultimoMetodo, horaActual());
                    }
                    enfocarInput();
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
                        if (data.alumno) {
                            ultimoAlumno = data.alumno;
                        }
                        if (ultimoAlumno) {
                            agregarRegistroALaLista(ultimoAlumno, ultimoMetodo, horaActual());
                        }
                        enfocarInput();
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