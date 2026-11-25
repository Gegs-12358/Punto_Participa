// Formulario de actividad: muestra el campo "Número de sala" solo cuando el lugar
// elegido lo pide (opción con data-pide-numero). Funciona también en el modal, que se
// carga después, porque escucha el evento en todo el documento.
document.addEventListener('change', function (evento) {
    var select = evento.target;
    if (!select.matches || !select.matches('select[name="lugar"]')) {
        return;
    }
    var form = select.closest('form') || document;
    var contenedor = form.querySelector('[data-lugar-numero-wrap]');
    if (!contenedor) {
        return;
    }
    var opcion = select.options[select.selectedIndex];
    var pideNumero = !!(opcion && opcion.hasAttribute('data-pide-numero'));
    contenedor.style.display = pideNumero ? '' : 'none';
    var campo = contenedor.querySelector('input');
    if (campo) {
        campo.required = pideNumero;
        if (!pideNumero) {
            campo.value = '';
        } else {
            campo.focus();
        }
    }
});
