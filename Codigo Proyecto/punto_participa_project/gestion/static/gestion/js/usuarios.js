// ============================================================
// usuarios.js - Gestión de Usuarios
// ============================================================
document.addEventListener('DOMContentLoaded', function () {
    const btnNuevo = document.getElementById('btnNuevoUsuario');
    const modalElement = document.getElementById('modalUsuario');
    const form = document.getElementById('formUsuario');

    // ============================================================
    // Abrir modal para NUEVO usuario
    // ============================================================
    if (btnNuevo) {
        btnNuevo.addEventListener('click', function () {
            document.getElementById('modalUsuarioLabel').textContent = 'Crear Usuario';
            form.reset();
            document.getElementById('user_id').value = '';
            openModal(modalElement);
        });
    }

    // ============================================================
    // Abrir modal para EDITAR usuario
    // ============================================================
    document.querySelectorAll('.btn-editar-usuario').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.getElementById('modalUsuarioLabel').textContent = 'Editar Usuario';
            document.getElementById('user_id').value = this.dataset.id;
            document.getElementById('username').value = this.dataset.username || '';
            document.getElementById('nombre').value = this.dataset.nombre || '';
            document.getElementById('email').value = this.dataset.email || '';
            document.getElementById('rol').value = this.dataset.rol || '';
            document.getElementById('rut').value = this.dataset.rut || '';

            const checkboxEstado = document.getElementById('estado');
            if (checkboxEstado) {
                checkboxEstado.checked = this.dataset.activo === '1';
            }

            openModal(modalElement);
        });
    });

    // ============================================================
    // BLOQUEAR / DESBLOQUEAR USUARIO
    // ============================================================
    document.querySelectorAll('.btn-bloquear-usuario').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const usuarioId = this.dataset.id;
            const username = this.dataset.username;
            const accion = this.dataset.accion;

            const fila = this.closest('tr');
            const btnEditar = fila ? fila.querySelector('.btn-editar-usuario') : null;

            if (!btnEditar) {
                mostrarMensaje('Error: no se pudieron leer los datos del usuario.', 'danger');
                return;
            }

            const usernameActual = btnEditar.dataset.username || '';
            const nombreActual = btnEditar.dataset.nombre || '';
            const emailActual = btnEditar.dataset.email || '';
            const rolActual = btnEditar.dataset.rol || '';
            const rutActual = btnEditar.dataset.rut || '';
            const activoActual = btnEditar.dataset.activo === '1';

            let mensajeConfirm;
            if (accion === 'bloquear') {
                mensajeConfirm = '¿Bloquear a "' + usernameActual + '"?\n\n' +
                                 'El usuario no podrá iniciar sesión, pero su historial se conserva.';
            } else {
                mensajeConfirm = '¿Desbloquear a "' + usernameActual + '"?\n\n' +
                                 'El usuario podrá volver a iniciar sesión.';
            }

            if (!confirm(mensajeConfirm)) {
                return;
            }

            const formData = new FormData();
            formData.append('user_id', usuarioId);
            formData.append('username', usernameActual);
            formData.append('nombre', nombreActual);
            formData.append('email', emailActual);
            formData.append('rol', rolActual);
            formData.append('rut', rutActual);
            formData.append('estado', activoActual ? 'off' : 'on');

            const self = this;
            self.disabled = true;
            const iconOriginal = self.innerHTML;
            self.innerHTML = '◌';

            fetch('/usuarios/guardar/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                credentials: 'same-origin'
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        const accionExitosa = accion === 'bloquear' ? 'bloqueado' : 'desbloqueado';
                        mostrarMensaje('Usuario ' + accionExitosa + ' correctamente.', 'success');
                        setTimeout(function () { window.location.reload(); }, 1000);
                    } else {
                        self.disabled = false;
                        self.innerHTML = iconOriginal;
                        mostrarMensaje(data.message || 'Error al cambiar el estado del usuario.', 'danger');
                    }
                })
                .catch(function (error) {
                    console.error('Error al cambiar estado:', error);
                    self.disabled = false;
                    self.innerHTML = iconOriginal;
                    mostrarMensaje('Error al conectar con el servidor.', 'danger');
                });
        });
    });

        // ============================================================
    // Enviar formulario para guardar
    // ============================================================
    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = new FormData(this);
            const csrftoken = getCookie('csrftoken');

            fetch('/usuarios/guardar/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': csrftoken },
                credentials: 'same-origin'
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        if (data.password_temporal) {
                            mostrarPasswordTemporal(data.password_temporal);
                        } else {
                            window.location.reload();
                        }
                    } else {
                        mostrarMensaje(data.message || 'Error al guardar el usuario.', 'danger');
                    }
                })
                .catch(function (error) {
                    console.error('Error al guardar usuario:', error);
                    mostrarMensaje('Error al conectar con el servidor.', 'danger');
                });
        });
    }

    // ============================================================
    // Mostrar la contraseña temporal generada al crear un usuario
    // ============================================================
    function mostrarPasswordTemporal(password) {
        const mensaje =
            '<p>El usuario fue creado correctamente. Esta es su contraseña temporal:</p>' +
            '<div class="alert alert-warning text-center">' +
            '<strong style="font-size: 1.3rem; letter-spacing: 1px;">' + password + '</strong>' +
            '</div>' +
            '<p class="small text-muted mb-0">' +
            'Cópiala y entrégasela de forma segura a la persona. No podrás volver a verla después de cerrar este mensaje. ' +
            'Deberá cambiarla al iniciar sesión por primera vez.' +
            '</p>';

        abrirModalGlobal('Usuario creado', mensaje, 'success');

        // Recargar la tabla al cerrar el modal, para que se vea el usuario nuevo
        const modalGlobal = document.getElementById('globalMessageModal');
        if (modalGlobal) {
            modalGlobal.addEventListener('hidden.bs.modal', function handler() {
                modalGlobal.removeEventListener('hidden.bs.modal', handler);
                window.location.reload();
            });
        }
    }
});