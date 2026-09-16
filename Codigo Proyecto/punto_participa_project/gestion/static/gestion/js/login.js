// ============================================================
// login.js - Lógica de la página de inicio de sesión
// ============================================================

document.addEventListener('DOMContentLoaded', function () {

    // ============================================================
    // Toggle para mostrar/ocultar contraseña
    // ============================================================
    const toggleBtn = document.getElementById('toggle-password');
    const passwordInput = document.getElementById('password');

    if (toggleBtn && passwordInput) {
        toggleBtn.addEventListener('click', function () {
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                this.textContent = '◉'; // Ojo cerrado (contraseña visible)
                this.setAttribute('aria-label', 'Ocultar contraseña');
            } else {
                passwordInput.type = 'password';
                this.textContent = '◎'; // Ojo abierto (contraseña oculta)
                this.setAttribute('aria-label', 'Mostrar contraseña');
            }
        });
    }

});