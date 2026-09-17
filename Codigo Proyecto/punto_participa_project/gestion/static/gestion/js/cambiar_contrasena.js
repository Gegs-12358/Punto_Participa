'use strict';

// ============================================================
// cambiar_contrasena.js
// Validación y mostrar/ocultar campos de contraseña
// ============================================================

document.addEventListener(
    'DOMContentLoaded',
    inicializarCambioContrasena
);


// ============================================================
// Inicialización general
// ============================================================

function inicializarCambioContrasena() {
    inicializarBotonesPassword();
    inicializarIndicadorFortaleza();
    inicializarCoincidencia();
    inicializarValidacionFormulario();
}


// ============================================================
// Mostrar u ocultar contraseñas
// ============================================================

function inicializarBotonesPassword() {
    const botones = document.querySelectorAll(
        '.toggle-password'
    );

    botones.forEach(function (boton) {
        boton.addEventListener('click', function () {
            alternarPassword(boton);
        });
    });
}


function alternarPassword(boton) {
    const idObjetivo = boton.dataset.target;
    const campo = document.getElementById(idObjetivo);

    if (!campo) {
        return;
    }

    const icono = boton.querySelector(
        '[aria-hidden="true"]'
    );

    const estaVisible = campo.type === 'text';

    if (estaVisible) {
        campo.type = 'password';

        boton.setAttribute(
            'aria-label',
            'Mostrar contraseña'
        );

        boton.setAttribute(
            'aria-pressed',
            'false'
        );

        if (icono) {
            icono.textContent = '◎';
        }
    } else {
        campo.type = 'text';

        boton.setAttribute(
            'aria-label',
            'Ocultar contraseña'
        );

        boton.setAttribute(
            'aria-pressed',
            'true'
        );

        if (icono) {
            icono.textContent = '◉';
        }
    }
}


// ============================================================
// Indicador visual de fortaleza
// ============================================================

function calcularFortaleza(contrasena) {
    let puntos = 0;

    if (contrasena.length >= 8) {
        puntos++;
    }

    if (contrasena.length >= 12) {
        puntos++;
    }

    if (/[a-z]/.test(contrasena)) {
        puntos++;
    }

    if (/[A-Z]/.test(contrasena)) {
        puntos++;
    }

    if (/[0-9]/.test(contrasena)) {
        puntos++;
    }

    if (/[^A-Za-z0-9]/.test(contrasena)) {
        puntos++;
    }

    if (puntos <= 2) {
        return {
            nivel: 'Débil',
            color: '#b42318',
            porcentaje: 25
        };
    }

    if (puntos <= 4) {
        return {
            nivel: 'Media',
            color: '#fbb800',
            porcentaje: 60
        };
    }

    if (puntos === 5) {
        return {
            nivel: 'Fuerte',
            color: '#158149',
            porcentaje: 80
        };
    }

    return {
        nivel: 'Muy fuerte',
        color: '#158149',
        porcentaje: 100
    };
}


function inicializarIndicadorFortaleza() {
    const campo = document.getElementById(
        'nueva_contrasena'
    );

    const barra = document.getElementById(
        'fortalezaBarra'
    );

    const texto = document.getElementById(
        'fortalezaTexto'
    );

    if (!campo || !barra || !texto) {
        return;
    }

    campo.addEventListener('input', function () {
        const valor = campo.value;

        if (!valor) {
            barra.style.width = '0%';
            barra.style.backgroundColor = '';
            barra.setAttribute('aria-valuenow', '0');
            texto.textContent = '';
            return;
        }

        const fortaleza = calcularFortaleza(valor);

        barra.style.width = `${fortaleza.porcentaje}%`;
        barra.style.backgroundColor = fortaleza.color;
        barra.setAttribute(
            'aria-valuenow',
            String(fortaleza.porcentaje)
        );

        texto.textContent = `Fortaleza: ${fortaleza.nivel}`;
    });
}


// ============================================================
// Validar coincidencia de contraseñas
// ============================================================

function inicializarCoincidencia() {
    const nueva = document.getElementById(
        'nueva_contrasena'
    );

    const confirmacion = document.getElementById(
        'confirmar_contrasena'
    );

    const mensaje = document.getElementById(
        'mensajeCoincidencia'
    );

    if (!nueva || !confirmacion || !mensaje) {
        return;
    }

    function comprobar() {
        if (!confirmacion.value) {
            mensaje.textContent = '';
            confirmacion.setCustomValidity('');
            return;
        }

        if (nueva.value === confirmacion.value) {
            mensaje.textContent =
                '✓ Las contraseñas coinciden.';

            mensaje.className =
                'input-help text-success';

            confirmacion.setCustomValidity('');
        } else {
            mensaje.textContent =
                '✗ Las contraseñas no coinciden.';

            mensaje.className =
                'input-help text-danger';

            confirmacion.setCustomValidity(
                'Las contraseñas no coinciden.'
            );
        }
    }

    nueva.addEventListener('input', comprobar);
    confirmacion.addEventListener('input', comprobar);
}


// ============================================================
// Validación previa del formulario
// ============================================================

function inicializarValidacionFormulario() {
    const formulario = document.getElementById(
        'formCambiarContrasena'
    );

    const actual = document.getElementById(
        'contrasena_actual'
    );

    const nueva = document.getElementById(
        'nueva_contrasena'
    );

    const confirmacion = document.getElementById(
        'confirmar_contrasena'
    );

    if (!formulario || !actual || !nueva || !confirmacion) {
        return;
    }

    formulario.addEventListener('submit', function (evento) {
        let valido = true;
        let mensaje = '';

        if (!actual.value.trim()) {
            mensaje = 'Debes ingresar tu contraseña actual.';
            valido = false;
        } else if (nueva.value.length < 8) {
            mensaje =
                'La nueva contraseña debe tener al menos 8 caracteres.';
            valido = false;
        } else if (nueva.value !== confirmacion.value) {
            mensaje = 'Las contraseñas no coinciden.';
            valido = false;
        } else if (nueva.value === actual.value) {
            mensaje =
                'La nueva contraseña no puede ser igual a la actual.';
            valido = false;
        }

        if (!valido) {
            evento.preventDefault();
            mostrarErrorLocal(mensaje);
        }
    });
}


// ============================================================
// Mostrar mensaje de validación local
// ============================================================

function mostrarErrorLocal(mensaje) {
    let alerta = document.getElementById(
        'error-validacion-contrasena'
    );

    if (!alerta) {
        alerta = document.createElement('div');
        alerta.id = 'error-validacion-contrasena';
        alerta.className = 'alert alert-danger';
        alerta.setAttribute('role', 'alert');
        alerta.setAttribute('aria-live', 'assertive');

        const formulario = document.getElementById(
            'formCambiarContrasena'
        );

        if (formulario) {
            formulario.insertBefore(
                alerta,
                formulario.firstChild
            );
        }
    }

    alerta.textContent = mensaje;
}
