"""
Registro de asistencia en el escáner: lectura del RUT, dos etapas y rechazos.

Correr solo este archivo:
    python manage.py test gestion.tests.escaner.tests_registro --noinput
"""
from django.test import TestCase
from django.urls import reverse

from ...models import Asistencia, Inscripcion
from ...views.escaner import _parse_rut_escaneo
from ..base import BaseSistemaTestCase, SilenciarRegistros


class ParseRutEscaneoTests(SilenciarRegistros, TestCase):
    """Prueba _parse_rut_escaneo."""

    def test_reconoce_como_llego_el_rut(self):
        qr_sin_run = 'https://portal.sidiv.registrocivil.cl/consulta?OTRO=123'
        casos = [
            ('20001550-9', ('CODIGO', '20001550-9')),
            ("'20001550-9", ('CODIGO', '20001550-9')),   # comilla que agrega el lector
            ('200015509', ('RUT', '200015509')),         # digitado a mano
            ('https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9', ('QR', '20001550-9')),
            (qr_sin_run, ('QR', qr_sin_run)),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(tuple(_parse_rut_escaneo(texto)), esperado)


class ProcesarEscaneoTests(SilenciarRegistros, BaseSistemaTestCase):
    """Prueba _procesar_escaneo a través de la vista escaneo."""

    def seleccionar_actividad(self, actividad=None):
        actividad = actividad or self.actividad_masiva
        self.client.force_login(self.registrador)
        session = self.client.session
        session['actividad_escaneo_id'] = actividad.pk
        session.save()

    def test_sin_rut_rechaza(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': ''})
        self.assertEqual(response.status_code, 400)

    def test_alumno_inexistente_devuelve_404(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': '99999999-9'})
        self.assertEqual(response.status_code, 404)

    def test_primera_etapa_pide_confirmacion(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['confirmar'])

    def test_actividad_finalizada_entre_etapas_rechaza_confirmacion(self):
        self.seleccionar_actividad()
        primera = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(primera.status_code, 200)
        self.assertTrue(primera.json()['confirmar'])

        self.actividad_masiva.estado = 'FINALIZADA'
        self.actividad_masiva.save(update_fields=['estado'])
        segunda = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut, 'confirmar': 'true'})

        self.assertEqual(segunda.status_code, 404)
        self.assertFalse(Asistencia.objects.filter(actividad=self.actividad_masiva, alumno=self.alumno).exists())

    def test_segunda_etapa_crea_asistencia(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse('escaneo'),
            {'rut': self.alumno.rut, 'confirmar': 'true'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(
            Asistencia.objects.filter(
                actividad=self.actividad_masiva, alumno=self.alumno
            ).exists()
        )

    def test_taller_con_inscripcion_acepta(self):
        Inscripcion.objects.create(
            actividad=self.actividad, alumno=self.alumno, estado='CONFIRMADA'
        )
        self.seleccionar_actividad(self.actividad)
        response = self.client.post(
            reverse('escaneo'),
            {'rut': self.alumno.rut, 'confirmar': 'true'},
        )
        self.assertEqual(response.status_code, 200)

    def test_escaneo_con_qr_detecta_metodo(self):
        self.seleccionar_actividad()
        qr = 'https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9'
        self.client.post(reverse('escaneo'), {'rut': qr, 'confirmar': 'true'})
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, 'QR')


class EscanerFormatosYSesionTests(BaseSistemaTestCase):
   
    def test_escaneo_por_qr_detecta_metodo_qr(self):
        self.seleccionar_actividad()
        qr = "https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9"
        response = self.client.post(reverse("escaneo"), {"rut": qr})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["confirmar"])
        self.client.post(reverse("escaneo"), {"rut": qr, "confirmar": "true"})
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, "QR")

    def test_escaneo_por_codigo_detecta_metodo_codigo(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse("escaneo"), {"rut": "'20001550-9"}
        )
        self.assertEqual(response.status_code, 200)
        self.client.post(
            reverse("escaneo"),
            {"rut": "'20001550-9", "confirmar": "true"},
        )
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, "CODIGO")

    def test_escaneo_sin_actividad_seleccionada_rechaza(self):
        self.client.force_login(self.registrador)
        response = self.client.post(
            reverse("escaneo"), {"rut": self.alumno.rut}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Primero selecciona", response.json()["message"])

    def test_finalizar_turno_limpia_la_actividad_de_la_sesion(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse("escaneo"), {"finalizar_turno": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("actividad_escaneo_id", self.client.session)
