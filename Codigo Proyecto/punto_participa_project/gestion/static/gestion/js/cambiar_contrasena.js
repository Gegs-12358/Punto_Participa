// ============================================================
// cambiar_contrasena.js - Validación y toggle de contraseña
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
            const icon = this.querySelector('i');

            if (!input) return;

            if (input.type === 'password') {
                input.type = 'text';
                if (icon) icon.classList.replace('fa-eye', 'fa-eye-slash');
                this.setAttribute('aria-label', 'Ocultar contraseña');
            } else {
                input.type = 'password';
                if (icon) icon.classList.replace('fa-eye-slash', 'fa-eye');
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
            return { nivel: 'Débil', color: 'bg-danger', porcentaje: 25 };
        } else if (puntos <= 4) {
            return { nivel: 'Media', color: 'bg-warning', porcentaje: 60 };
        } else if (puntos === 5) {
            return { nivel: 'Fuerte', color: 'bg-success', porcentaje: 80 };
        } else {
            return { nivel: 'Muy fuerte', color: 'bg-success', porcentaje: 100 };
        }
    }

    if (inputNueva && fortalezaBarra && fortalezaTexto) {
        inputNueva.addEventListener('input', function () {
            const valor = inputNueva.value;

            if (valor.length === 0) {
                fortalezaBarra.style.width = '0%';
                fortalezaBarra.className = 'progress-bar';
                fortalezaBarra.setAttribute('aria-valuenow', '0');
                fortalezaTexto.textContent = '';
                return;
            }

            const fortaleza = calcularFortaleza(valor);
            fortalezaBarra.style.width = fortaleza.porcentaje + '%';
            fortalezaBarra.className = 'progress-bar ' + fortaleza.color;
            fortalezaBarra.setAttribute('aria-valuenow', fortaleza.porcentaje);
            fortalezaTexto.textContent = 'Fortaleza: ' + fortaleza.nivel;
            fortalezaTexto.className = 'text-muted small';
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
            mensajeCoincidencia.className = 'd-block mt-1';
            return;
        }

        if (nueva === confirmar) {
            mensajeCoincidencia.textContent = '✓ Las contraseñas coinciden.';
            mensajeCoincidencia.className = 'd-block mt-1 text-success small';
        } else {
            mensajeCoincidencia.textContent = '✗ Las contraseñas no coinciden.';
            mensajeCoincidencia.className = 'd-block mt-1 text-danger small';
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

            // 1. Contraseña actual no vacía
            if (!inputActual.value.trim()) {
                mostrarMensaje('Debes ingresar tu contraseña actual.', 'danger');
                valido = false;
            }

            // 2. Nueva contraseña mínimo 8 caracteres
            if (inputNueva.value.length < 8) {
                mostrarMensaje('La nueva contraseña debe tener al menos 8 caracteres.', 'danger');
                valido = false;
            }

            // 3. Contraseñas coinciden
            if (inputNueva.value !== inputConfirmar.value) {
                mostrarMensaje('Las contraseñas no coinciden.', 'danger');
                valido = false;
            }

            // 4. La nueva no puede ser igual a la actual
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