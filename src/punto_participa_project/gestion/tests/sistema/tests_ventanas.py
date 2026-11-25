"""
Ventanas emergentes: las que tienen un formulario no se cierran con un clic afuera ni con Esc.

Las pruebas de Django no ejecutan JavaScript: revisan que cada ventana tenga las marcas que lee scripts.js
(data-modal-persistent y data-modal-confirmar-cierre) y que el código que las interpreta siga ahí. El
comportamiento en el navegador se revisó a mano (ver CAMBIOS.md).

Correr solo este archivo:
    python manage.py test gestion.tests.sistema.tests_ventanas --noinput
"""
import re
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from ..base import BaseSistemaTestCase


# Ventanas que se completan o deciden algo: solo se cierran con la X o con "Cancelar"
PERSISTENTES = {
    'actividadModal': True,                # crear y editar actividad (con aviso de cambios sin guardar)
    'modalConfirmarInvitaciones': False,   # enviar invitaciones u "Ahora no" (obligatorio en talleres)
    'modalUsuario': True,                  # crear y editar usuario (con aviso)
    'modalAgregar': True,                  # agregar a alguien en la entrada (con aviso)
}
# Ventanas que solo informan o eligen: se pueden cerrar con un clic afuera o con Esc
SE_CIERRAN_AFUERA = {'globalMessageModal', 'cambiarActividadModal', 'modalConfirmarAsistencia', 'modalAviso'}

ETIQUETA = re.compile(r'<div class="modal-backdrop"[^>]*>')
CAMPO = re.compile(r'<(textarea|select)\b|<input\b(?![^>]*type="(hidden|search)")')


def _ventanas(html):
    """{id: (etiqueta de apertura, contenido hasta la siguiente ventana)}"""
    trozos = {}
    marcas = list(ETIQUETA.finditer(html))
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(html)
        ident = re.search(r'id="([^"]+)"', m.group(0)).group(1)
        trozos[ident] = (m.group(0), html[m.start():fin])
    return trozos


class VentanasTests(BaseSistemaTestCase):
    def paginas(self):
        self.login_as(self.admin)
        self.client.post(reverse('escaneo'), {'cambiar_actividad': '1', 'actividad_id': self.actividad.pk})
        for nombre in ('dashboard', 'lista_actividades', 'usuarios', 'escaneo'):
            yield nombre, self.client.get(reverse(nombre)).content.decode()

    def test_cada_ventana_tiene_su_marca(self):
        vistas = {}
        for _, html in self.paginas():
            vistas.update(_ventanas(html))
        self.assertTrue(set(PERSISTENTES) | SE_CIERRAN_AFUERA <= set(vistas), set(vistas))
        for ident, confirma in PERSISTENTES.items():
            with self.subTest(ventana=ident):
                etiqueta = vistas[ident][0]
                self.assertIn('data-modal-persistent', etiqueta)
                self.assertEqual('data-modal-confirmar-cierre' in etiqueta, confirma)
        for ident in SE_CIERRAN_AFUERA:
            with self.subTest(ventana=ident):
                self.assertNotIn('data-modal-persistent', vistas[ident][0])

    def test_una_ventana_nueva_con_campos_debe_ser_persistente(self):
        # Resguardo: si alguien agrega una ventana con campos para llenar, tiene que decidir cómo se cierra
        for pagina, html in self.paginas():
            for ident, (etiqueta, contenido) in _ventanas(html).items():
                # El buscador de "Elegir actividad" (type="search") no cuenta: no es un dato que se pierda
                if CAMPO.search(contenido):
                    with self.subTest(pagina=pagina, ventana=ident):
                        self.assertIn('data-modal-persistent', etiqueta)

    def test_la_x_de_invitaciones_hace_lo_mismo_que_ahora_no(self):
        self.login_as(self.admin)
        html = self.client.get(reverse('lista_actividades')).content.decode()
        _, contenido = _ventanas(html)['modalConfirmarInvitaciones']
        x = re.search(r'<button[^>]*class="close-button"[^>]*>', contenido).group(0)
        self.assertIn('id="btnCerrarInvitaciones"', x)
        self.assertNotIn('data-modal-close', x)

    def test_el_codigo_que_lee_las_marcas_sigue_en_scripts_js(self):
        js = (Path(settings.BASE_DIR) / 'gestion' / 'static' / 'gestion' / 'js' / 'scripts.js').read_text(encoding='utf-8')
        self.assertIn("hasAttribute('data-modal-persistent')", js)
        self.assertIn("hasAttribute('data-modal-confirmar-cierre')", js)
        self.assertIn('#btnCancelarEnvio, #btnCerrarInvitaciones', js)
        escaneo = (Path(settings.BASE_DIR) / 'gestion' / 'static' / 'gestion' / 'js' / 'escaneo.js').read_text(encoding='utf-8')
        self.assertIn("'modalConfirmarAsistencia', 'modalAviso', 'modalAgregar'", escaneo)
