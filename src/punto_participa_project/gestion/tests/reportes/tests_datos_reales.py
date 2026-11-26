"""
Los números y textos que se muestran corresponden a los datos reales: promedios y tasas sin contar actividades que
aún no ocurren, plazos que salen de la configuración y fechas en hora de Chile.

Correr solo este archivo:
    python manage.py test gestion.tests.reportes.tests_datos_reales --noinput
"""
from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ...models import Actividad, Asistencia, Inscripcion
from ...views.reportes import _construir_desglose_tipo
from ..base import BaseSistemaTestCase


class IndicadoresTests(BaseSistemaTestCase):
    def setUp(self):
        ahora = timezone.now()
        # Un taller que ya pasó: 2 inscritos, 1 asistió (tasa real: 50 %)
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_inicio=ahora - timedelta(days=2),
                                                              fecha_fin=ahora - timedelta(days=2, hours=-2))
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno_pasaporte)
        Asistencia.objects.create(actividad=self.actividad, alumno=self.alumno)
        # Un taller que viene, con un inscrito: todavía nadie puede haber asistido
        Inscripcion.objects.create(actividad=self.actividad_otro, alumno=self.alumno)

    def test_la_tasa_de_talleres_no_cuenta_los_que_no_han_empezado(self):
        datos = _construir_desglose_tipo(Actividad.objects.all(), Asistencia.objects.all())
        self.assertEqual(datos['talleres_inscritos'], 3)      # el total se sigue mostrando
        self.assertEqual(datos['tasa_talleres'], 50.0)        # antes daba 33,3 % (1 de 3)

    def test_el_promedio_de_asistentes_solo_cuenta_las_realizadas(self):
        self.login_as(self.admin)
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['promedio_asistentes'], 1.0)   # 1 asistente en la única realizada

    def test_la_etiqueta_dice_lo_que_cuenta(self):
        self.login_as(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'ACTIVIDADES PRÓXIMAS O EN CURSO')


class PlazosDeLaConfiguracionTests(BaseSistemaTestCase):
    @override_settings(RETENCION_ANIOS=3)
    def test_auditoria_y_politica_dicen_el_plazo_configurado(self):
        self.login_as(self.admin)
        self.assertContains(self.client.get(reverse('auditoria')), 'se guardan 3 años')
        self.assertContains(self.client.get(reverse('privacidad')), '3 años')


class FechasEnHoraDeChileTests(BaseSistemaTestCase):
    def test_el_detalle_de_reportes_usa_la_fecha_local(self):
        # 22:30 en Chile ya es el día siguiente en UTC
        local = timezone.localtime(timezone.now()).replace(hour=22, minute=30, second=0, microsecond=0)
        local = local - timedelta(days=1)
        Actividad.objects.filter(pk=self.actividad_masiva.pk).update(fecha_inicio=local,
                                                                     fecha_fin=local + timedelta(hours=1))
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno)
        self.login_as(self.admin)
        r = self.client.get(reverse('reportes'))
        fechas = {d['fecha'] for d in r.context['detalle_data'] if d['actividad'] == self.actividad_masiva.titulo}
        self.assertEqual(fechas, {local.strftime('%d/%m/%Y')})
