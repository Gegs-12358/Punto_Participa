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
