// Piezas comunes de interfaz (P-UI).
// Menús desplegables (<details class="menu-desplegable">): se cierran al hacer clic
// afuera, al elegir una opción o con la tecla Escape.
(function () {
    function cerrarMenus(excepto) {
        document.querySelectorAll('details.menu-desplegable[open]').forEach(function (menu) {
            if (menu !== excepto) menu.removeAttribute('open');
        });
    }
    document.addEventListener('click', function (evento) {
        var menu = evento.target.closest('details.menu-desplegable');
        cerrarMenus(menu);
        if (menu && evento.target.closest('.menu-desplegable__panel a, .menu-desplegable__panel button')) {
            menu.removeAttribute('open');
        }
    });
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') {
            var abierto = document.querySelector('details.menu-desplegable[open]');
            if (abierto) {
                abierto.removeAttribute('open');
                abierto.querySelector('summary').focus();
            }
        }
    });
})();

// Botones con data-copiar="texto": copian el texto al portapapeles y avisan.
(function () {
    function avisar(texto, tipo) {
        if (typeof mostrarMensaje === 'function') mostrarMensaje(texto, tipo);
    }
    document.addEventListener('click', function (evento) {
        var boton = evento.target.closest('[data-copiar]');
        if (!boton) return;
        var texto = boton.getAttribute('data-copiar');
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(texto).then(function () {
                avisar('Enlace copiado.', 'success');
            }, function () {
                window.prompt('Copia el enlace:', texto);
            });
        } else {
            // Sin HTTPS el navegador no deja escribir en el portapapeles: se muestra para copiarlo a mano
            window.prompt('Copia el enlace:', texto);
        }
    });
})();
