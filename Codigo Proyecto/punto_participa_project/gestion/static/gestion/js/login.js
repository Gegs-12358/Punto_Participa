// ============================================================
// login.js - Lógica de la página de inicio de sesión
// ============================================================

document.addEventListener('DOMContentLoaded', function() {

    // ============================================================
    // Toggle para mostrar/ocultar contraseña
    // ============================================================
    const toggleBtn = document.getElementById('toggle-password');
    const passwordInput = document.getElementById('password');

    if (toggleBtn && passwordInput) {
        toggleBtn.addEventListener('click', function() {
            const icon = this.querySelector('i');

            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                if (icon) {
                    icon.classList.replace('fa-eye', 'fa-eye-slash');
                }
                this.setAttribute('aria-label', 'Ocultar contraseña');
            } else {
                passwordInput.type = 'password';
                if (icon) {
                    icon.classList.replace('fa-eye-slash', 'fa-eye');
                }
                this.setAttribute('aria-label', 'Mostrar contraseña');
            }
        });
    }

});