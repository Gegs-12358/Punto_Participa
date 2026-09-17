'use strict';

// ============================================================
// login.js - Lógica de la página de inicio de sesión
// ============================================================

document.addEventListener(
    'DOMContentLoaded',
    inicializarLogin
);


// ============================================================
// Inicialización general
// ============================================================

function inicializarLogin() {
    inicializarTogglePassword();
}


// ============================================================
// Mostrar u ocultar contraseña
// ============================================================

function inicializarTogglePassword() {
    const toggleButton = document.getElementById(
        'toggle-password'
    );

    const passwordInput = document.getElementById(
        'password'
    );

    if (!toggleButton || !passwordInput) {
        return;
    }

    toggleButton.addEventListener(
        'click',
        function () {
            const passwordVisible =
                passwordInput.type === 'text';

            if (passwordVisible) {
                passwordInput.type = 'password';

                actualizarEstadoToggle(
                    toggleButton,
                    false
                );
            } else {
                passwordInput.type = 'text';

                actualizarEstadoToggle(
                    toggleButton,
                    true
                );
            }
        }
    );
}


// ============================================================
// Actualizar estado visual y accesible del botón
// ============================================================

function actualizarEstadoToggle(
    toggleButton,
    passwordVisible
) {
    const icon = toggleButton.querySelector(
        '[aria-hidden="true"]'
    );

    if (passwordVisible) {
        if (icon) {
            icon.textContent = '◉';
        }

        toggleButton.setAttribute(
            'aria-label',
            'Ocultar contraseña'
        );

        toggleButton.setAttribute(
            'aria-pressed',
            'true'
        );
    } else {
        if (icon) {
            icon.textContent = '◎';
        }

        toggleButton.setAttribute(
            'aria-label',
            'Mostrar contraseña'
        );

        toggleButton.setAttribute(
            'aria-pressed',
            'false'
        );
    }
}
