"""
Pruebas de las piezas comunes de interfaz (P-UI): íconos, botones de filtro con aviso,
chips de filtros activos y el buscador de Actividades.
"""
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from .tests_integrales import BaseSistemaTestCase


def _render(texto, url='/x/', **contexto):
    request = RequestFactory().get(url)
    return Template('{% load ui %}' + texto).render(Context({'request': request, **contexto}))


class PiezasUITests(SimpleTestCase):
    def test_icono_conocido_y_desconocido(self):
        html = _render('{% icono "editar" %}')
        self.assertIn('<svg class="icono', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertEqual(_render('{% icono "no_existe" %}').strip(), '')

    def test_acciones_filtro_con_aviso_y_etiqueta_accesible(self):
        html = _render('{% acciones_filtro "/actividades/" %}')
        self.assertIn('data-tooltip="Filtrar"', html)
        self.assertIn('aria-label="Limpiar filtros"', html)
        self.assertIn('href="/actividades/"', html)

    def test_chips_solo_de_los_filtros_activos_y_con_nombre_legible(self):
        html = _render('{% chips_filtros "tipo=Tipo,estado=Estado,lugar=Lugar" "/a/" %}',
                       url='/a/?tipo=TALLER&lugar=Sala&page=3')
        self.assertIn('Tipo: Taller', html)
        self.assertIn('Lugar: Sala', html)
        self.assertNotIn('Estado:', html)
        # El chip de Tipo conserva Lugar y quita la página
        self.assertIn('href="?lugar=Sala"', html)
        self.assertIn('Limpiar todos', html)

    def test_sin_filtros_no_hay_chips(self):
        self.assertNotIn('filter-chips', _render('{% chips_filtros "tipo=Tipo" "/a/" %}', url='/a/?page=2'))

    def test_chip_con_valor_hostil_se_escapa(self):
        html = _render('{% chips_filtros "q=Búsqueda" "/a/" %}', url='/a/?q=<script>x</script>')
        self.assertNotIn('<script>x</script>', html)
        self.assertIn('&lt;script&gt;', html)


class ActividadesUnificadaTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)

    def test_buscador_por_nombre_descripcion_o_lugar(self):
        url = reverse('lista_actividades')
        titulos = lambda q: {a.titulo for a in self.client.get(url, {'q': q}).context['actividades']}
        self.assertEqual(titulos('masiva'), {'Actividad masiva'})
        self.assertEqual(len(titulos('Sede Alameda')), 3)          # busca también en el lugar
        self.assertEqual(titulos('no existe nada'), set())

    def test_buscador_hostil_no_rompe(self):
        for q in ("' OR 1=1 --", '<script>x</script>', '\x00', 'a' * 500):
            with self.subTest(q=q[:20]):
                resp = self.client.get(reverse('lista_actividades'), {'q': q})
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, '<script>x</script>')

    def test_acciones_de_fila_con_aviso_y_sin_emojis(self):
        resp = self.client.get(reverse('lista_actividades'))
        self.assertContains(resp, 'data-tooltip="Editar"')
        self.assertContains(resp, 'data-tooltip="Participantes"')
        self.assertContains(resp, 'btn-editar')          # el JavaScript del modal sigue funcionando
        self.assertNotContains(resp, '👁')
        self.assertContains(resp, 'img/encabezado/actividad.webp')
