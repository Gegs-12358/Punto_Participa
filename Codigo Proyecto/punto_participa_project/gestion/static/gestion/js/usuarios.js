// ============================================================
// Usuarios - Gestión de Usuarios (Separado del HTML)
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    const btnNuevo = document.getElementById('btnNuevoUsuario');
    const modalElement = document.getElementById('modalUsuario');
    const form = document.getElementById('formUsuario');

    // Función para obtener CSRF
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    // Abrir modal para NUEVO usuario
    if (btnNuevo) {
        btnNuevo.addEventListener('click', function() {
            document.getElementById('modalUsuarioLabel').textContent = 'Crear Usuario';
            form.reset();
            document.getElementById('user_id').value = '';
            new bootstrap.Modal(modalElement).show();
        });
    }

    // Abrir modal para EDITAR usuario (Ahora incluye RUT y Username)
    document.querySelectorAll('.btn-editar-usuario').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.getElementById('modalUsuarioLabel').textContent = 'Editar Usuario';
            document.getElementById('user_id').value = this.dataset.id;
            document.getElementById('username').value = this.dataset.username;
            document.getElementById('nombre').value = this.dataset.nombre;
            document.getElementById('email').value = this.dataset.email;
            document.getElementById('rol').value = this.dataset.rol;
            document.getElementById('rut').value = this.dataset.rut;
            new bootstrap.Modal(modalElement).show();
        });
    });

    // Enviar formulario para guardar
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            fetch('/usuarios/guardar/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': csrftoken }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.reload(); // Recargar para actualizar la tabla
                } else {
                    alert('Error al guardar el usuario.');
                }
            })
            .catch(error => console.error('Error:', error));
        });
    }
});