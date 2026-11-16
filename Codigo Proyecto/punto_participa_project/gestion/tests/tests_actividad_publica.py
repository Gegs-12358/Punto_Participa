# Pagina publica /actividad/<n>/ y el boton "Ver detalles" del correo de las masivas.
from datetime import timedelta

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from gestion.models import Actividad, Alumno


def crear_actividad(tipo='MASIVA', estado='ACTIVA', dias=2):
    ahora = timezone.now()
    cupos = ({'cupos_totales': 10, 'cupos_disponibles': 10} if tipo == 'TALLER'
             else {'cupos_totales': None, 'cupos_disponibles': None})
    return Actividad.objects.create(
        titulo=f'Premiacion {tipo}', descripcion='Una ceremonia importante', tipo=tipo,
        lugar='Sede Alameda', fecha_inicio=ahora + timedelta(days=dias),
        fecha_fin=ahora + timedelta(days=dias, hours=2), estado=estado, **cupos)


class ActividadPublicaTests(TestCase):
    def _get(self, actividad):
        return self.client.get(reverse('actividad_publica', args=[actividad.pk]))

    def test_cualquiera_ve_una_masiva_sin_iniciar_sesion(self):
        actividad = crear_actividad()
        r = self._get(actividad)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Premiacion MASIVA')
        self.assertContains(r, 'Sede Alameda')
        self.assertContains(r, 'no requiere inscripción')
        self.assertEqual(r.context['estado'], 'vigente')

    def test_la_pagina_no_pide_datos_ni_permite_inscribirse(self):
        r = self._get(crear_actividad())
        self.assertNotContains(r, '<form')
        self.assertNotContains(r, 'name="rut"')

    def test_un_taller_se_redirige_a_su_inscripcion(self):
        taller = crear_actividad('TALLER')
        r = self._get(taller)
        self.assertRedirects(
            r, reverse('inscripcion_taller', args=[taller.pk]), fetch_redirect_response=False)

    def test_una_actividad_inexistente_da_404(self):
        self.assertEqual(self.client.get('/actividad/99999/').status_code, 404)

    def test_finalizada_y_cancelada_se_muestran_con_su_estado(self):
        vencida = crear_actividad(dias=-3)
        self.assertEqual(self._get(vencida).context['estado'], 'finalizada')
        cancelada = crear_actividad(estado='CANCELADA')
        self.assertEqual(self._get(cancelada).context['estado'], 'cancelada')


class CorreoVerDetallesTests(TestCase):
    def setUp(self):
        self.alumno = Alumno.objects.create(
            rut='11111111K', tipo_documento='RUT', nombres='Ana', apellidos='Uno',
            correo='ana@example.com', carrera='Informática', jornada='Diurna')

    def _html(self, actividad):
        return render_to_string('gestion/email_invitacion.html', {
            'actividad': actividad, 'alumno': self.alumno, 'site_url': 'http://sitio.test'})

    def test_la_masiva_lleva_ver_detalles_y_ningun_enlace_de_inscripcion(self):
        actividad = crear_actividad()
        html = self._html(actividad)
        self.assertIn(f'http://sitio.test/actividad/{actividad.pk}/', html)
        self.assertIn('Ver detalles', html)
        self.assertNotIn('/taller/', html)
        self.assertNotIn('Inscribirme', html)

    def test_el_taller_no_cambia(self):
        taller = crear_actividad('TALLER')
        html = self._html(taller)
        self.assertIn(f'http://sitio.test/taller/{taller.pk}/', html)
        self.assertIn('Inscribirme', html)
        self.assertNotIn('/actividad/', html)
        self.assertNotIn('Ver detalles', html)
