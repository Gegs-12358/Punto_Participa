"""
Imagen y datos de la actividad en las páginas públicas y en los correos.

Correr solo este archivo:
    python manage.py test gestion.tests.inscripciones.tests_portada --noinput
"""
import io
import shutil
import tempfile

from PIL import Image

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse

from ...models import Invitado
from ..base import BaseSistemaTestCase


MEDIA = tempfile.mkdtemp()


def _imagen():
    salida = io.BytesIO()
    Image.new('RGB', (40, 20), (0, 80, 160)).save(salida, 'JPEG')
    return SimpleUploadedFile('portada.jpg', salida.getvalue(), content_type='image/jpeg')


@override_settings(MEDIA_ROOT=MEDIA, SITE_URL='https://participa.ejemplo.cl')
class PortadaPublicaTests(BaseSistemaTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def con_imagen(self, actividad):
        actividad.imagen = _imagen()
        actividad.save()
        return actividad

    def test_taller_con_imagen_la_muestra_con_el_titulo_una_vez(self):
        self.con_imagen(self.actividad)
        r = self.client.get(reverse('inscripcion_taller', args=[self.actividad.pk]))
        self.assertContains(r, 'event-portada--imagen')
        self.assertContains(r, self.actividad.imagen.url)
        self.assertContains(r, f'<h1>{self.actividad.titulo}</h1>', count=1, html=True)
        self.assertNotContains(r, 'event-portada__mascota')

    def test_sin_imagen_muestra_la_mascota(self):
        r = self.client.get(reverse('inscripcion_taller', args=[self.actividad.pk]))
        self.assertContains(r, 'event-portada__mascota')
        self.assertNotContains(r, 'event-portada--imagen')

    def test_masiva_e_invitacion_usan_la_misma_portada(self):
        self.con_imagen(self.actividad_masiva)
        r = self.client.get(reverse('actividad_publica', args=[self.actividad_masiva.pk]))
        self.assertContains(r, 'event-portada--imagen')
        especial = self.con_imagen(self._crear_actividad('Ceremonia', 'INVITACION', self.creador, None))
        inv = Invitado.objects.create(actividad=especial, rut='12345678-5', nombre='Ana Pérez', correo='a@b.cl')
        r = self.client.get(reverse('responder_invitacion', args=[inv.token]))
        self.assertContains(r, 'event-portada--imagen')
        self.assertContains(r, 'INVITACIÓN')

    def test_casilla_de_privacidad_con_su_estilo(self):
        r = self.client.get(reverse('inscripcion_taller', args=[self.actividad.pk]))
        self.assertContains(r, 'class="casilla"')

    def test_correo_de_invitacion_con_imagen_y_logos_en_direccion_completa(self):
        self.con_imagen(self.actividad)
        html = render_to_string('gestion/correos/invitacion.html',
                                {'actividad': self.actividad, 'alumno': self.alumno, 'site_url': 'https://participa.ejemplo.cl'})
        # Va la versión para correos (1200x600, JPEG), no la imagen original
        self.actividad.refresh_from_db()
        self.assertTrue(self.actividad.imagen_correo)
        self.assertIn(f'src="https://participa.ejemplo.cl{self.actividad.imagen_correo.url}"', html)
        self.assertIn('src="https://participa.ejemplo.cl/static/', html)
        self.assertNotIn('Súmate al', html)
        self.assertNotIn('cronograma', html)

    def test_confirmacion_de_inscripcion_con_imagen(self):
        self.con_imagen(self.actividad)
        self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]),
                         {'rut': self.alumno.rut, 'acepta_politica': 'on'})
        html = mail.outbox[-1].alternatives[0][0]
        self.actividad.refresh_from_db()
        self.assertIn(f'https://participa.ejemplo.cl{self.actividad.imagen_correo.url}', html)
        self.assertIn('Quedaste inscrito', html)
