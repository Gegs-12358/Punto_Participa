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


class PantallasUnificadasTests(BaseSistemaTestCase):
    """P-UI parte 2: Reportes, Usuarios, Auditoría, Catálogos, Inicio y Detalle."""

    def setUp(self):
        self.login_as(self.admin)

    def test_buscador_y_filtros_de_usuarios(self):
        url = reverse('usuarios')
        nombres = lambda **f: {u.user.username for u in self.client.get(url, f).context['usuarios']}
        self.assertEqual(nombres(q='registrador'), {'registrador_integral'})
        self.assertEqual(nombres(rol='Creador de Evento'), {'creador_integral', 'creador_otro'})
        self.assertNotIn('admin_integral', nombres(estado='bloqueado'))
        resp = self.client.get(url, {'q': "<script>x</script>' OR 1=1"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '<script>x</script>')

    def test_menu_exportar_explica_cada_archivo(self):
        resp = self.client.get(reverse('reportes'), {'tipo': 'TALLER'})
        self.assertContains(resp, 'Resumen por actividad')
        self.assertContains(resp, 'Participación por escuela y carrera')
        self.assertContains(resp, 'Listado de participantes')
        self.assertContains(resp, 'Todo en un Excel')
        self.assertContains(resp, 'Todas las descargas usan los filtros aplicados')
        self.assertContains(resp, reverse('exportar_reporte', args=['participacion', 'csv']) + '?tipo=TALLER')

    def test_ninguna_pantalla_usa_emojis_ni_simbolos_como_iconos(self):
        paginas = [reverse(n) for n in ('dashboard', 'lista_actividades', 'reportes', 'usuarios',
                                        'auditoria', 'catalogo_lugares', 'catalogo_escuelas',
                                        'catalogo_carreras', 'escaneo')]
        paginas += [reverse('actividad_detalle', args=[self.actividad.pk]),
                    reverse('participantes_actividad', args=[self.actividad.pk])]
        for url in paginas:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for simbolo in ('👁', '👥', '✎', '🗑', '⇩', '⎙', '▽ Filtrar', '× Limpiar</a>'):
                    self.assertNotIn(simbolo, html)

    def test_filtros_de_auditoria_con_chips(self):
        resp = self.client.get(reverse('auditoria'), {'usuario': 'admin'})
        self.assertContains(resp, 'Usuario: admin')
        self.assertContains(resp, 'data-tooltip="Filtrar"')


class SinSimbolosAntiguosTests(BaseSistemaTestCase):
    """Los símbolos de texto (▦ ◎ ⌖ ...) se reemplazaron por los íconos SVG de la guía de estilo."""
    SIMBOLOS = '⌂▦▥◎▤⚙▢☰⎋◈◉✓✉⌖◷▣ⓘ⚠●✔✗✕➤◌'

    def _sin_simbolos(self, resp):
        texto = resp.content.decode()
        encontrados = sorted({c for c in texto if c in self.SIMBOLOS})
        self.assertEqual(encontrados, [], resp.request['PATH_INFO'])

    def test_pantallas_del_administrador(self):
        self.login_as(self.admin)
        for nombre, args in (('dashboard', []), ('lista_actividades', []), ('reportes', []),
                             ('usuarios', []), ('lista_alumnos', []), ('catalogo_lugares', []),
                             ('catalogo_escuelas', []), ('catalogo_carreras', []), ('escaneo', []),
                             ('auditoria', []), ('actividad_detalle', [self.actividad.pk]),
                             ('participantes_actividad', [self.actividad.pk]),
                             ('notificaciones_actividad', [self.actividad.pk]), ('cambiar_contrasena', []),
                             ('crear_actividad', [])):
            with self.subTest(pantalla=nombre):
                resp = self.client.get(reverse(nombre, args=args))
                self.assertEqual(resp.status_code, 200)
                self._sin_simbolos(resp)

    def test_paginas_publicas(self):
        for url in (reverse('login'), reverse('inscripcion_taller', args=[self.actividad.pk]),
                    reverse('actividad_publica', args=[self.actividad_masiva.pk])):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self._sin_simbolos(resp)

    def test_menu_con_iconos_y_pagina_actual_marcada(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('reportes'))
        self.assertContains(resp, 'aria-current="page"', count=2)   # menú de escritorio y de celular
        self.assertContains(resp, '</svg> Reportes')
