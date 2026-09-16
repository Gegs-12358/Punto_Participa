// ============================================================
// cambiar_contrasena.js - Validación y toggle de contraseña
// Sin Bootstrap: usa estilos propios
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('formCambiarContrasena');
    const inputActual = document.getElementById('contrasena_actual');
    const inputNueva = document.getElementById('nueva_contrasena');
    const inputConfirmar = document.getElementById('confirmar_contrasena');
    const fortalezaBarra = document.getElementById('fortalezaBarra');
    const fortalezaTexto = document.getElementById('fortalezaTexto');
    const mensajeCoincidencia = document.getElementById('mensajeCoincidencia');

    // ============================================================
    // TOGGLE DE CONTRASEÑA (mostrar/ocultar)
    // ============================================================
    document.querySelectorAll('.toggle-password').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const targetId = this.dataset.target;
            const input = document.getElementById(targetId);

            if (!input) return;

            if (input.type === 'password') {
                input.type = 'text';
                this.textContent = '◉'; // Ojo cerrado (contraseña visible)
                this.setAttribute('aria-label', 'Ocultar contraseña');
            } else {
                input.type = 'password';
                this.textContent = '◎'; // Ojo abierto (contraseña oculta)
                this.setAttribute('aria-label', 'Mostrar contraseña');
            }
        });
    });

    // ============================================================
    // INDICADOR DE FORTALEZA DE CONTRASEÑA
    // ============================================================
    function calcularFortaleza(password) {
        let puntos = 0;
        if (password.length >= 8) puntos++;
        if (password.length >= 12) puntos++;
        if (/[a-z]/.test(password)) puntos++;
        if (/[A-Z]/.test(password)) puntos++;
        if (/[0-9]/.test(password)) puntos++;
        if (/[^A-Za-z0-9]/.test(password)) puntos++;

        if (puntos <= 2) {
            return { nivel: 'Débil', color: '#b42318', porcentaje: 25 };
        } else if (puntos <= 4) {
            return { nivel: 'Media', color: '#fbb800', porcentaje: 60 };
        } else if (puntos === 5) {
            return { nivel: 'Fuerte', color: '#158149', porcentaje: 80 };
        } else {
            return { nivel: 'Muy fuerte', color: '#158149', porcentaje: 100 };
        }
    }

    if (inputNueva && fortalezaBarra && fortalezaTexto) {
        inputNueva.addEventListener('input', function () {
            const valor = inputNueva.value;

            if (valor.length === 0) {
                fortalezaBarra.style.width = '0%';
                fortalezaBarra.style.background = '#b42318';
                fortalezaBarra.setAttribute('aria-valuenow', '0');
                fortalezaTexto.textContent = '';
                return;
            }

            const fortaleza = calcularFortaleza(valor);
            fortalezaBarra.style.width = fortaleza.porcentaje + '%';
            fortalezaBarra.style.background = fortaleza.color;
            fortalezaBarra.setAttribute('aria-valuenow', fortaleza.porcentaje);
            fortalezaTexto.textContent = 'Fortaleza: ' + fortaleza.nivel;
            fortalezaTexto.className = 'input-help';
        });
    }

    // ============================================================
    // VALIDAR QUE LAS CONTRASEÑAS COINCIDAN
    // ============================================================
    function verificarCoincidencia() {
        if (!inputNueva || !inputConfirmar || !mensajeCoincidencia) return;

        const nueva = inputNueva.value;
        const confirmar = inputConfirmar.value;

        if (confirmar.length === 0) {
            mensajeCoincidencia.textContent = '';
            mensajeCoincidencia.className = 'input-help';
            return;
        }

        if (nueva === confirmar) {
            mensajeCoincidencia.textContent = '✓ Las contraseñas coinciden.';
            mensajeCoincidencia.className = 'input-help text-success';
        } else {
            mensajeCoincidencia.textContent = '✗ Las contraseñas no coinciden.';
            mensajeCoincidencia.className = 'input-help text-danger';
        }
    }

    if (inputConfirmar) {
        inputConfirmar.addEventListener('input', verificarCoincidencia);
    }
    if (inputNueva) {
        inputNueva.addEventListener('input', verificarCoincidencia);
    }

    // ============================================================
    // VALIDAR ANTES DE ENVIAR
    // ============================================================
    if (form) {
        form.addEventListener('submit', function (e) {
            let valido = true;

            if (!inputActual.value.trim()) {
                mostrarMensaje('Debes ingresar tu contraseña actual.', 'danger');
                valido = false;
            }

            if (inputNueva.value.length < 8) {
                mostrarMensaje('La nueva contraseña debe tener al menos 8 caracteres.', 'danger');
                valido = false;
            }

            if (inputNueva.value !== inputConfirmar.value) {
                mostrarMensaje('Las contraseñas no coinciden.', 'danger');
                valido = false;
            }

            if (inputNueva.value && inputNueva.value === inputActual.value) {
                mostrarMensaje('La nueva contraseña no puede ser igual a la actual.', 'danger');
                valido = false;
            }

            if (!valido) {
                e.preventDefault();
                return;
            }
        });
    }
});