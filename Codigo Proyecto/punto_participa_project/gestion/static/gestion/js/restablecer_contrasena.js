'use strict';

// ============================================================
// restablecer_contrasena.js
// Mostrar/ocultar contraseña y validar coincidencia
// ============================================================

document.addEventListener(
    'DOMContentLoaded',
    inicializarRestablecimiento
);


// ============================================================
// Inicialización general
// ============================================================

function inicializarRestablecimiento() {
    inicializarBotonesPassword();
    inicializarCoincidencia();
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
            alternarVisibilidadPassword(boton);
        });
    });
}


function alternarVisibilidadPassword(boton) {
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

        return;
    }

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


// ============================================================
// Validar coincidencia de contraseñas
// ============================================================

function inicializarCoincidencia() {
    const nuevaContrasena = document.getElementById(
        'nueva_contrasena'
    );

    const confirmarContrasena = document.getElementById(
        'confirmar_contrasena'
    );

    const mensaje = document.getElementById(
        'mensajeCoincidencia'
    );

    const formulario = document.getElementById(
        'formRestablecerContrasena'
    );

    if (
        !nuevaContrasena ||
        !confirmarContrasena ||
        !mensaje ||
        !formulario
    ) {
        return;
    }

    function comprobarCoincidencia() {
        if (!confirmarContrasena.value) {
            mensaje.textContent = '';
            mensaje.style.color = '';
            confirmarContrasena.setCustomValidity('');
            return;
        }

        if (
            nuevaContrasena.value ===
            confirmarContrasena.value
        ) {
            mensaje.textContent =
                'Las contraseñas coinciden.';

            mensaje.style.color = '#158149';

            confirmarContrasena.setCustomValidity('');
        } else {
            mensaje.textContent =
                'Las contraseñas no coinciden.';

            mensaje.style.color = '#b42318';

            confirmarContrasena.setCustomValidity(
                'Las contraseñas no coinciden.'
            );
        }
    }

    nuevaContrasena.addEventListener(
        'input',
        comprobarCoincidencia
    );

    confirmarContrasena.addEventListener(
        'input',
        comprobarCoincidencia
    );

    formulario.addEventListener(
        'submit',
        function (evento) {
            comprobarCoincidencia();

            if (!formulario.checkValidity()) {
                evento.preventDefault();
            }
        }
    );
}
