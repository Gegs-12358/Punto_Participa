// Formulario de actividad: sesiones adicionales (includes/sesiones_form.html).
// "Agregar sesión" copia la fila de la plantilla; "Quitar" la saca. El porcentaje mínimo
// de asistencia solo se muestra cuando hay sesiones adicionales. Escucha en todo el
// documento para funcionar también en el modal, que se carga después.
(function () {
    function actualizar(bloque) {
        var hay = bloque.querySelectorAll('[data-sesiones-filas] [data-fila-sesion]').length > 0;
        var minima = bloque.querySelector('[data-asistencia-minima]');
        if (minima) {
            minima.hidden = !hay;
        }
    }

    document.addEventListener('click', function (evento) {
        var agregar = evento.target.closest && evento.target.closest('[data-agregar-sesion]');
        if (agregar) {
            var bloque = agregar.closest('[data-sesiones]');
            var plantilla = bloque.querySelector('template[data-sesion-plantilla]');
            var filas = bloque.querySelector('[data-sesiones-filas]');
            var nueva = plantilla.content.firstElementChild.cloneNode(true);
            filas.appendChild(nueva);
            actualizar(bloque);
            var fecha = nueva.querySelector('input[name="sesion_fecha"]');
            if (fecha) {
                fecha.focus();
            }
            return;
        }
        var quitar = evento.target.closest && evento.target.closest('[data-quitar-sesion]');
        if (quitar) {
            var bloqueQuitar = quitar.closest('[data-sesiones]');
            quitar.closest('[data-fila-sesion]').remove();
            actualizar(bloqueQuitar);
        }
    });
})();
