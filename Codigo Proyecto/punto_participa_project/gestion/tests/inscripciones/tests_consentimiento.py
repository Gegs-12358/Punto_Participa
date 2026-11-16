"""
La aceptación de la Política de Privacidad queda guardada con versión y fecha.

Correr solo este archivo:
    python manage.py test gestion.tests.inscripciones.tests_consentimiento --noinput
"""
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from django.urls import reverse
from django.utils import timezone

from ...models import Inscripcion, InscripcionCancelada, Invitado, ListaEspera, VERSION_POLITICA
from ...servicios.cancelaciones import cancelar
from ..base import BaseSistemaTestCase


class ConsentimientoTests(BaseSistemaTestCase):
    def inscribir(self, alumno=None, **extra):
        datos = {'rut': (alumno or self.alumno).rut, 'acepta_politica': 'on'}
        datos.update(extra)
        return self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]), datos)

    def assertConsentimiento(self, registro):
        self.assertEqual(registro.politica_version, VERSION_POLITICA)
        self.assertIsNotNone(registro.politica_aceptada)
        self.assertLess(abs((timezone.now() - registro.politica_aceptada).total_seconds()), 60)

    def test_la_inscripcion_guarda_version_y_fecha(self):
        self.inscribir()
        self.assertConsentimiento(Inscripcion.objects.get(actividad=self.actividad, alumno=self.alumno))

    def test_sin_aceptar_no_hay_inscripcion(self):
        datos = {'rut': self.alumno.rut}
        self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]), datos)
        self.assertFalse(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())

    def test_si_falla_la_auditoria_la_evidencia_queda_en_la_inscripcion(self):
        with patch('gestion.views.inscripciones.registrar_log', side_effect=RuntimeError('auditoría caída')):
            self.inscribir()
        self.assertConsentimiento(Inscripcion.objects.get(actividad=self.actividad, alumno=self.alumno))

    def test_la_lista_de_espera_guarda_version_y_fecha(self):
        self.actividad.cupos_totales = self.actividad.cupos_disponibles = 1
        self.actividad.save(update_fields=['cupos_totales', 'cupos_disponibles'])
        self.inscribir(self.alumno_pasaporte)
        self.inscribir(accion='lista_espera')
        self.assertConsentimiento(ListaEspera.objects.get(actividad=self.actividad, alumno=self.alumno))

    def test_al_cancelar_la_evidencia_pasa_al_historial(self):
        self.inscribir()
        insc = Inscripcion.objects.get(actividad=self.actividad, alumno=self.alumno)
        cancelar(insc.pk, por=self.admin)
        historial = InscripcionCancelada.objects.get(actividad=self.actividad, alumno=self.alumno)
        self.assertEqual((historial.politica_version, historial.politica_aceptada),
                         (insc.politica_version, insc.politica_aceptada))

    def test_la_respuesta_a_la_invitacion_guarda_version_y_fecha(self):
        especial = self._crear_actividad('Ceremonia', 'INVITACION', self.creador, None)
        inv = Invitado.objects.create(actividad=especial, rut='12345678-5', nombre='Ana Pérez', correo='a@b.cl')
        self.assertEqual(inv.politica_version, '')
        self.client.post(reverse('responder_invitacion', args=[inv.token]),
                         {'asistira': 'no', 'acepta_politica': 'on'})
        inv.refresh_from_db()
        self.assertEqual(inv.estado, 'RECHAZADO')
        self.assertConsentimiento(inv)

    def test_el_listado_de_participantes_muestra_la_politica_aceptada(self):
        self.inscribir()
        self.login_as(self.admin)
        resp = self.client.get(reverse('exportar_reporte', args=['participantes', 'excel']),
                               {'actividad': self.actividad.pk})
        ws = load_workbook(BytesIO(resp.content))['Participantes']
        encabezados = [c.value for c in ws[1]]
        self.assertIn('Política aceptada', encabezados)
        fila = [c.value for c in ws[2]]
        self.assertEqual(fila[encabezados.index('Política aceptada')], VERSION_POLITICA)
        self.assertIsNotNone(fila[encabezados.index('Aceptó el')])

    def test_la_pagina_de_la_politica_muestra_la_version_vigente(self):
        self.assertContains(self.client.get(reverse('privacidad')), f'Versión {VERSION_POLITICA}')
