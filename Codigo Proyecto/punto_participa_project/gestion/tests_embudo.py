"""
Reporte del taller en el detalle de la actividad (P1): de la invitación a la asistencia.

Invitados (alumnos distintos con invitación enviada) -> inscritos (confirmados) ->
asistieron -> no asistieron, con la lista de quienes se inscribieron y no fueron.
Antes de que empiece la actividad, "no asistieron" y la tasa no se muestran.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Alumno, Asistencia, Inscripcion, NotificacionCorreo
from .tests_integrales import BaseSistemaTestCase
from .views import _embudo_actividad


class EmbudoTallerTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)
        ahora = timezone.now()
        Actividad.objects.filter(pk=self.actividad.pk).update(
            fecha_inicio=ahora - timedelta(hours=1), fecha_fin=ahora + timedelta(hours=1),
            cupos_totales=5)
        self.actividad.refresh_from_db()
        self.tercero = Alumno.objects.create(rut='11111111-1', nombres='Pía', apellidos='Soto',
                                             correo='pia@example.com', carrera=self.carrera.nombre,
                                             jornada='Diurno')
        for alumno in (self.alumno, self.alumno_pasaporte, self.tercero):
            Inscripcion.objects.create(actividad=self.actividad, alumno=alumno)
        Inscripcion.objects.filter(alumno=self.tercero).update(estado='CANCELADA')
        Asistencia.objects.create(actividad=self.actividad, alumno=self.alumno, metodo_ingreso='RUT')
        # Juan invitado 2 veces (cuenta 1), Ana con envío fallido (no cuenta)
        for estado, alumno in (('EXITO', self.alumno), ('EXITO', self.alumno), ('FALLO', self.alumno_pasaporte)):
            NotificacionCorreo.objects.create(actividad=self.actividad, alumno=alumno, estado_envio=estado)

    def test_cuenta_cada_paso(self):
        e = _embudo_actividad(self.actividad)
        self.assertEqual((e['invitados'], e['inscritos'], e['asistieron'], e['no_asistieron']), (1, 2, 1, 1))
        self.assertEqual(e['tasa'], 50.0)
        self.assertEqual(e['sin_invitacion'], 1)
        self.assertEqual([i.alumno for i in e['faltantes']], [self.alumno_pasaporte])
        self.assertEqual([p['etiqueta'] for p in e['pasos']],
                         ['Invitados', 'Inscritos', 'Asistieron', 'No asistieron'])
        self.assertEqual(max(p['ancho'] for p in e['pasos']), 100)

    def test_antes_de_empezar_no_hay_no_asistieron(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_inicio=timezone.now() + timedelta(days=1))
        self.actividad.refresh_from_db()
        e = _embudo_actividad(self.actividad)
        self.assertIsNone(e['no_asistieron'])
        self.assertIsNone(e['tasa'])
        self.assertEqual(e['faltantes'], [])
        self.assertNotIn('No asistieron', [p['etiqueta'] for p in e['pasos']])

    def test_pantalla_muestra_el_recorrido_y_quien_falto(self):
        resp = self.client.get(reverse('actividad_detalle', args=[self.actividad.pk]))
        self.assertContains(resp, 'De la invitación a la asistencia')
        self.assertContains(resp, 'Ver quiénes se inscribieron y no asistieron (1)')
        self.assertContains(resp, 'Ana Gómez')
        self.assertContains(resp, reverse('exportar_reporte', args=['participantes', 'excel'])
                            + f'?actividad={self.actividad.pk}')
        self.assertNotContains(resp, '✓')
        self.assertNotContains(resp, '✗')

    def test_lista_de_faltantes_usa_la_carrera_de_la_inscripcion(self):
        Alumno.objects.filter(pk=self.alumno_pasaporte.pk).update(carrera='Carrera nueva')
        resp = self.client.get(reverse('actividad_detalle', args=[self.actividad.pk]))
        self.assertContains(resp, 'Diseño Gráfico')
        self.assertNotContains(resp, 'Carrera nueva')

    def test_creador_ajeno_no_ve_el_detalle(self):
        self.login_as(self.otro_creador)
        resp = self.client.get(reverse('actividad_detalle', args=[self.actividad.pk]))
        self.assertEqual(resp.status_code, 302)


class EmbudoMasivaTests(BaseSistemaTestCase):
    def test_masiva_sin_inscritos(self):
        act = self.actividad_masiva
        Actividad.objects.filter(pk=act.pk).update(fecha_inicio=timezone.now() - timedelta(hours=1),
                                                   cupos_totales=4)
        act.refresh_from_db()
        Asistencia.objects.create(actividad=act, alumno=self.alumno, metodo_ingreso='RUT')
        e = _embudo_actividad(act)
        self.assertIsNone(e['inscritos'])
        self.assertEqual(e['asistieron'], 1)
        self.assertEqual(e['tasa'], 25.0)
        self.assertEqual([p['etiqueta'] for p in e['pasos']], ['Invitados', 'Asistieron'])
        self.login_as(self.admin)
        resp = self.client.get(reverse('actividad_detalle', args=[act.pk]))
        self.assertContains(resp, 'Actividad masiva: no tiene inscripción')
        self.assertContains(resp, 'Aún no se han enviado invitaciones')
