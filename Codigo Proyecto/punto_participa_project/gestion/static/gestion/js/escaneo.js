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
    // CONTADOR EN VIVO (turno, total de la actividad y por operador)
    // ============================================================
    const contador = document.getElementById('contadorEscaneo');
    const listaOperadores = document.querySelector('[data-contador="operadores"]');

    function ponerNumero(clave, valor) {
        const el = contador && contador.querySelector('[data-contador="' + clave + '"]');
        if (!el || el.textContent === String(valor)) return;
        el.textContent = valor;
        el.classList.remove('actualizado');
        void el.offsetWidth;            // reinicia la animación
        el.classList.add('actualizado');
    }

    // Reconstruye "Últimos registros" con lo que manda el servidor (incluye a los demás operadores)
    function pintarUltimos(ultimos) {
        const lista = document.querySelector('.lista-ultimos-registros');
        if (!lista || !Array.isArray(ultimos)) return;
        lista.textContent = '';
        if (!ultimos.length) {
            const vacio = document.createElement('p');
            vacio.className = 'session__vacio';
            vacio.textContent = 'Sin registros aún';
            lista.appendChild(vacio);
            return;
        }
        ultimos.forEach(function (u) {
            const partes = u.nombre.split(' ');
            const item = document.createElement('div');
            item.className = 'person';
            const avatar = document.createElement('span');
            avatar.className = 'avatar';
            avatar.textContent = ((partes[0] || ' ')[0] + (partes[1] || ' ')[0]).trim().toUpperCase();
            const info = document.createElement('p');
            const nombre = document.createElement('strong');
            nombre.textContent = u.nombre;
            const detalle = document.createElement('small');
            detalle.textContent = u.metodo + (u.operador ? ', ' + u.operador : '');
            info.appendChild(nombre);
            info.appendChild(detalle);
            const hora = document.createElement('time');
            hora.textContent = u.hora;
            item.appendChild(avatar);
            item.appendChild(info);
            item.appendChild(hora);
            lista.appendChild(item);
        });
    }

    function actualizarContador(c) {
        if (!c || !contador) return;
        pintarUltimos(c.ultimos);
        ponerNumero('mi_turno', c.mi_turno);
        ponerNumero('total', c.total);
        ponerNumero('en_turno', c.en_turno);
        const meta = contador.querySelector('[data-contador="meta"]');
        if (meta) {
            meta.textContent = c.meta ? 'de ' + c.meta + ' ' + c.meta_texto : 'todos los operadores';
        }
        if (listaOperadores) {
            listaOperadores.textContent = '';
            if (!c.operadores.length) {
                const li = document.createElement('li');
                li.className = 'operadores__vacio';
                li.textContent = 'Nadie está en turno ni ha registrado todavía.';
                listaOperadores.appendChild(li);
            }
            c.operadores.forEach(function (op) {
                const li = document.createElement('li');
                if (op.yo) li.className = 'operadores__yo';
                const nombre = document.createElement('span');
                nombre.textContent = op.nombre + (op.yo ? ' (tú)' : '');
                if (op.en_turno) {
                    const estado = document.createElement('small');
                    estado.className = 'operadores__estado';
                    estado.textContent = ' en turno';
                    nombre.appendChild(estado);
                }
                const total = document.createElement('strong');
                total.textContent = op.total;
                li.appendChild(nombre);
                li.appendChild(total);
                listaOperadores.appendChild(li);
            });
        }
    }

    // Otros operadores registran en paralelo: se consulta cada 15 s mientras la pestaña está visible.
    if (contador && contador.dataset.url) {
        setInterval(function () {
            if (document.hidden) return;
            fetch(contador.dataset.url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) { if (data && data.success) actualizarContador(data); })
                .catch(function () { /* sin conexión: se reintenta en la próxima vuelta */ });
        }, 15000);
    }

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
        rutPendiente = '';   // no dejar el texto del carnet en memoria
        inputRut.focus();
    }

    function mostrarAviso(mensaje) {
        if (!modalAviso || !modalAvisoBody) return;
        const p = document.createElement('p');
        p.className = 'mb-0';
        p.textContent = mensaje;   // textContent no interpreta HTML
        modalAvisoBody.textContent = '';
        modalAvisoBody.appendChild(p);
        openModal(modalAviso);
    }

    /**
     * Inserta el alumno en la lista de "Últimos registros" sin recargar.
     */
    function agregarRegistroALaLista(alumno, metodo, hora) {
        if (!listaRegistros) return;

        // Quitar el mensaje "Sin registros aún" si existe (solo ese: los registros también tienen <p>)
        const vacio = listaRegistros.querySelector('.session__vacio');
        if (vacio) vacio.remove();

        // Iniciales del nombre
        const partes = alumno.nombre.split(' ');
        const iniciales = (
            (partes[0] ? partes[0][0] : '') +
            (partes[1] ? partes[1][0] : '')
        ).toUpperCase();

        let metodoTexto = 'RUT';
        if (metodo === 'QR') metodoTexto = 'Código QR';
        else if (metodo === 'CODIGO') metodoTexto = 'Código de barras';
        metodoTexto += ', tú';

        const item = document.createElement('div');
        item.className = 'person';
        item.style.animation = 'fadeIn 0.3s ease';

        const spanAvatar = document.createElement('span');
        spanAvatar.className = 'avatar';
        spanAvatar.textContent = iniciales;

        const elNombre = document.createElement('strong');
        elNombre.textContent = alumno.nombre;
        const elMetodo = document.createElement('small');
        elMetodo.textContent = metodoTexto;
        const elInfo = document.createElement('p');
        elInfo.appendChild(elNombre);
        elInfo.appendChild(elMetodo);

        const elHora = document.createElement('time');
        elHora.textContent = hora;

        item.appendChild(spanAvatar);
        item.appendChild(elInfo);
        item.appendChild(elHora);

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
                    inputRut.value = '';   // el texto del carnet no debe quedar a la vista
                    ultimoAlumno = data.alumno;
                    ultimoMetodo = 'RUT';

                    if (infoAlumno) {
                        infoAlumno.textContent = '';
                        const elNom = document.createElement('strong');
                        elNom.textContent = data.alumno.nombre;
                        infoAlumno.appendChild(elNom);
                        infoAlumno.appendChild(document.createElement('br'));
                        infoAlumno.appendChild(document.createTextNode('RUT: ' + data.alumno.rut));
                        infoAlumno.appendChild(document.createElement('br'));
                        infoAlumno.appendChild(document.createTextNode(
                            'Carrera: ' + data.alumno.carrera + ', ' + data.alumno.jornada
                        ));
                    }
                    openModal(modalConfirmar);
                } else if (!data.success) {
                    inputRut.value = '';
                    mostrarAviso(data.message);
                } else {
                    // Registro exitoso directo
                    mostrarMensaje(data.message, 'success');
                    if (data.alumno) {
                        ultimoAlumno = data.alumno;
                    }
                    if (data.metodo) ultimoMetodo = data.metodo;
                    actualizarContador(data.contador);
                    if (ultimoAlumno && !data.contador) {   // con contador, la lista ya llega del servidor
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
                        if (data.metodo) ultimoMetodo = data.metodo;
                        actualizarContador(data.contador);
                        if (ultimoAlumno && !data.contador) {   // con contador, la lista ya llega del servidor
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