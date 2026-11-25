// Catálogos: pide confirmación antes de enviar los formularios marcados con data-confirmar.
document.addEventListener('submit', function (evento) {
    var form = evento.target;
    var mensaje = form.getAttribute && form.getAttribute('data-confirmar');
    if (mensaje && !confirm(mensaje)) {
        evento.preventDefault();
    }
});
