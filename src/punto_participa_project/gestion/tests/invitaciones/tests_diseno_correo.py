"""
Diseño de la invitación: lo que se previsualiza es lo que llega, la versión de texto dice lo mismo que la HTML,
las fechas, los cupos, la lista de espera, los enlaces al calendario y la imagen para correos.

Correr solo este archivo:
    python manage.py test gestion.tests.invitaciones.tests_diseno_correo --noinput
"""
import io
from datetime import timedelta, timezone as zona

from PIL import Image

from django.core import mail
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ...models import Actividad, Sesion
from ...servicios import calendario, correos, imagenes
from ..actividades.tests_imagenes import ConMediaPropia
from ..base import BaseSistemaTestCase

SITIO = 'https://participa.ejemplo.cl'


def _contexto(actividad, alumno):
    return {'actividad': actividad, 'alumno': alumno, 'site_url': SITIO}


def _dos_sesiones(actividad):
    inicio = timezone.now() + timedelta(days=3)
    Sesion.objects.filter(actividad=actividad).delete()
    Sesion.objects.create(actividad=actividad, numero=1, fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=2))
    Sesion.objects.create(actividad=actividad, numero=2, fecha_inicio=inicio + timedelta(days=7),
                          fecha_fin=inicio + timedelta(days=7, hours=2))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_URL=SITIO)
class PrevisualizacionIgualAlEnvioTests(BaseSistemaTestCase):
    def test_la_previsualizacion_es_exactamente_el_correo_enviado(self):
        self.actividad.carreras.set([self.carrera])
        self.actividad.jornadas.set([self.jornada])
        self.client.force_login(self.creador)
        vista = self.client.get(reverse('previsualizar_invitacion', args=[self.actividad.pk])).json()
        self.client.post(reverse('enviar_invitaciones'), {'actividad_id': self.actividad.pk},
                         HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].alternatives[0][0], vista['html'])

    def test_el_texto_simple_trae_fechas_lugar_y_enlaces(self):
        self.actividad.carreras.set([self.carrera])
        self.client.force_login(self.creador)
        self.client.post(reverse('enviar_invitaciones'), {'actividad_id': self.actividad.pk},
                         HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        texto = mail.outbox[0].body
        enlace = SITIO + reverse('inscripcion_taller' if self.actividad.tipo == 'TALLER' else 'actividad_publica',
                                 args=[self.actividad.pk])
        self.assertIn(enlace, texto)
        self.assertIn(SITIO + reverse('calendario_actividad', args=[self.actividad.pk]), texto)
        self.assertIn(self.actividad.lugar_completo, texto)
        self.assertIn(timezone.localtime(self.actividad.fecha_inicio).strftime('%H:%M'), texto)
        self.assertNotIn('<', texto)


class ContenidoInvitacionTests(BaseSistemaTestCase):
    def setUp(self):
        super().setUp()
        self.taller = Actividad.objects.create(
            titulo='Taller de prueba', descripcion='Algo útil', tipo='TALLER', lugar='Sala', lugar_numero='102',
            cupos_totales=10, cupos_disponibles=3, estado='ACTIVA', creado_por=self.creador,
            fecha_inicio=timezone.now() + timedelta(days=3), fecha_fin=timezone.now() + timedelta(days=3, hours=2))

    def test_muestra_los_cupos_que_quedan(self):
        texto, html = correos.armar('invitacion', _contexto(self.taller, self.alumno))
        self.assertIn('Quedan 3 de 10 cupos', html)
        self.assertIn('Quedan 3 de 10 cupos', texto)
        self.assertIn('width="70%"', html)   # barra: 7 de 10 ocupados
        self.assertIn('Inscribirme', html)

    def test_taller_lleno_invita_a_la_lista_de_espera(self):
        self.taller.cupos_disponibles = 0
        self.taller.save()
        texto, html = correos.armar('invitacion', _contexto(self.taller, self.alumno))
        self.assertIn('Anotarme en la lista de espera', html)
        self.assertNotIn('Inscribirme', html)
        self.assertIn('lista de espera', texto)

    def test_varias_sesiones_una_hoja_de_calendario_por_sesion(self):
        _dos_sesiones(self.taller)
        texto, html = correos.armar('invitacion', _contexto(self.taller, self.alumno))
        self.assertIn('sesión 1 de 2', html)
        self.assertIn('sesión 2 de 2', html)
        self.assertEqual(html.count('Agregar a Google Calendar'), 2)
        self.assertIn('todas las sesiones', html)
        self.assertIn('Sesiones:', texto)

    def test_linea_de_vista_previa_de_la_bandeja(self):
        _, html = correos.armar('invitacion', _contexto(self.taller, self.alumno))
        self.assertIn('display: none; max-height: 0', html)
        self.assertIn('Inscríbete para asegurar tu cupo.', html)

    def test_sin_imagen_no_hay_banner(self):
        _, html = correos.armar('invitacion', _contexto(self.taller, self.alumno))
        self.assertNotIn('/media/', html)


class CalendarioTests(BaseSistemaTestCase):
    def setUp(self):
        super().setUp()
        self.act = Actividad.objects.create(
            titulo='Charla; con, signos', descripcion='d', tipo='MASIVA', lugar='Auditorio', estado='ACTIVA',
            creado_por=self.creador, fecha_inicio=timezone.now() + timedelta(days=3),
            fecha_fin=timezone.now() + timedelta(days=3, hours=2))

    def test_ics_con_una_entrada_por_sesion(self):
        _dos_sesiones(self.act)
        r = self.client.get(reverse('calendario_actividad', args=[self.act.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('text/calendar'))
        self.assertIn('attachment', r['Content-Disposition'])
        contenido = r.content.decode()
        self.assertEqual(contenido.count('BEGIN:VEVENT'), 2)
        self.assertIn('(sesión 2 de 2)', contenido)

    def test_ics_escapa_y_pliega_las_lineas(self):
        contenido = calendario.ics(self.act)
        self.assertIn('SUMMARY:Charla\\; con\\, signos', contenido)
        for linea in contenido.split('\r\n'):
            self.assertLessEqual(len(linea.encode('utf-8')), 75)

    def test_ics_no_disponible_para_invitacion_ni_cancelada(self):
        self.act.tipo = 'INVITACION'
        self.act.save()
        self.assertEqual(self.client.get(reverse('calendario_actividad', args=[self.act.pk])).status_code, 404)
        self.act.tipo, self.act.estado = 'MASIVA', 'CANCELADA'
        self.act.save()
        self.assertEqual(self.client.get(reverse('calendario_actividad', args=[self.act.pk])).status_code, 404)

    def test_enlace_de_google_en_hora_utc(self):
        sesion = self.act.lista_sesiones()[0]
        enlace = calendario.enlace_google(self.act, sesion)
        self.assertTrue(enlace.startswith('https://calendar.google.com/calendar/render?action=TEMPLATE'))
        inicio = sesion.fecha_inicio.astimezone(zona.utc)
        self.assertIn(inicio.strftime('%Y%m%dT%H%M%SZ'), enlace)


def _imagen(tamano):
    salida = io.BytesIO()
    Image.new('RGB', tamano, (200, 30, 30)).save(salida, format='PNG')
    return ContentFile(salida.getvalue())


class ImagenParaCorreosTests(ConMediaPropia):
    def _correo(self, tamano, nombre):
        self.actividad.imagen.save(nombre, _imagen(tamano))
        self.actividad.refresh_from_db()
        self.assertTrue(self.actividad.imagen_correo)
        with self.actividad.imagen_correo.open('rb') as f, Image.open(f) as img:
            img.load()
            return img

    def test_siempre_1200x600_en_jpeg(self):
        for tamano in ((1600, 800), (900, 1400), (1000, 1000)):
            img = self._correo(tamano, f'img_{tamano[0]}.png')
            self.assertEqual(img.size, imagenes.IMAGEN_CORREO)
            self.assertEqual(img.format, 'JPEG')

    def test_afiche_vertical_va_entero_sin_recortar(self):
        img = self._correo((600, 1200), 'afiche.png')
        # El afiche (rojo) ocupa el centro con todo el alto; los bordes son el fondo difuminado y oscurecido
        centro = img.getpixel((600, 10))
        borde = img.getpixel((5, 300))
        self.assertGreater(centro[0], 170)
        self.assertLess(borde[0], centro[0] - 40)

    def test_la_invitacion_usa_la_imagen_para_correos_con_su_alto(self):
        self._correo((1600, 800), 'banner.png')
        _, html = correos.armar('invitacion', _contexto(self.actividad, self.alumno))
        self.assertIn(self.actividad.imagen_correo.url, html)
        self.assertIn('width="600" height="300"', html)
        self.assertIn(f'alt="{self.actividad.titulo}"', html)

    def test_quitar_la_imagen_quita_la_version_para_correos(self):
        self._correo((1600, 800), 'quitar.png')
        nombre = self.actividad.imagen_correo.name
        self.actividad.imagen = None
        self.actividad.save()
        self.actividad.refresh_from_db()
        self.assertFalse(self.actividad.imagen_correo)
        self.assertFalse(self.actividad.imagen_correo.storage.exists(nombre))


class TodosLosCorreosTests(BaseSistemaTestCase):
    """Los 7 correos usan el mismo diseño y su versión de texto trae el enlace de la versión HTML."""
    def test_mismo_diseno_y_mismo_enlace_en_texto_y_html(self):
        from types import SimpleNamespace
        from ...models import Invitado
        enlace = 'https://participa.ejemplo.cl/enlace-personal/abc123/'
        invitado = Invitado(actividad=self.actividad, rut='12345678-5', nombre='Ana Pérez', correo='a@b.cl')
        aviso = SimpleNamespace(fecha_corte=timezone.now(), fecha_programada=timezone.now(), ejecutado=timezone.now())
        resumen = {k: 1 for k in ('actividades', 'inscripciones', 'asistencias', 'cancelaciones', 'lista_espera',
                                  'invitados', 'acompanantes', 'correos', 'turnos', 'auditoria')}
        casos = {
            'invitacion': _contexto(self.actividad, self.alumno),
            'invitacion_especial': {'actividad': self.actividad, 'invitado': invitado, 'enlace': enlace},
            'confirmacion_inscripcion': {'actividad': self.actividad, 'alumno': self.alumno, 'enlace': enlace,
                                         'limite': timezone.now() + timedelta(days=1), 'puede_cancelar': True},
            'lista_espera': {'actividad': self.actividad, 'alumno': self.alumno, 'enlace': enlace},
            'bienvenida_usuario': {'user': self.creador, 'rol': 'Encargado', 'enlace': enlace, 'dias': 3},
            'recuperacion': {'user': self.creador, 'enlace': enlace, 'dias': 3},
            'retencion': {'aviso': aviso, 'tipo': 'aviso', 'dias': 5, 'anios': 5, 'resumen': resumen,
                          'quien': 'Ana', 'sitio': SITIO, 'nombre': 'Ana'},
        }
        for nombre, contexto in casos.items():
            with self.subTest(correo=nombre):
                texto, html = correos.armar(nombre, contexto)
                self.assertIn('pp-tarjeta', html)
                self.assertIn('puntoestu@duoc.cl', texto)
                self.assertNotIn('<', texto.replace('<!--', ''))
                if nombre not in ('invitacion', 'retencion'):
                    self.assertIn(enlace, html)
                    self.assertIn(enlace, texto)
