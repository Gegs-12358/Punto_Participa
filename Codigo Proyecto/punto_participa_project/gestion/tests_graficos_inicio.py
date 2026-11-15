"""
Gráficos del Inicio y de Reportes: actividades por mes según sus fechas, talleres realizados, orden y carreras con su escuela.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Asistencia, Inscripcion
from .tests_integrales import BaseSistemaTestCase


class GraficosInicioTests(BaseSistemaTestCase):
    def setUp(self):
        Actividad.objects.all().delete()
        self.ahora = timezone.now()

    def crear(self, titulo, inicio, horas=2, tipo='TALLER', estado='ACTIVA'):
        act = self._crear_actividad(titulo, tipo, self.creador, 10)
        Actividad.objects.filter(pk=act.pk).update(fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=horas),
                                                   estado=estado)
        act.refresh_from_db()
        return act

    def contexto(self):
        self.login_as(self.admin)
        return self.client.get(reverse('dashboard')).context

    def test_meses_en_espanol_con_el_actual_y_el_siguiente(self):
        ctx = self.contexto()
        self.assertEqual(len(ctx['labels_meses']), 7)
        self.assertEqual(ctx['mes_actual'], 5)
        meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        self.assertTrue(ctx['labels_meses'][5].startswith(meses[timezone.localtime(self.ahora).month - 1]))

    def test_cada_actividad_una_vez_segun_sus_fechas(self):
        self.crear('Terminada', self.ahora - timedelta(hours=5))
        self.crear('En curso', self.ahora - timedelta(hours=1))
        self.crear('Próxima', self.ahora + timedelta(minutes=30))
        self.crear('Cancelada', self.ahora + timedelta(minutes=40), estado='CANCELADA')
        ctx = self.contexto()
        # Si el mes recién empezó, la terminada puede caer en el mes anterior: se suma todo
        self.assertEqual(sum(ctx['data_meses_finalizadas']), 1)
        self.assertEqual(sum(ctx['data_meses_en_curso']), 1)
        self.assertEqual(sum(ctx['data_meses_proximas']), 1)

    def test_talleres_solo_los_ya_realizados(self):
        hecho = self.crear('Taller hecho', self.ahora - timedelta(days=2))
        futuro = self.crear('Taller futuro', self.ahora + timedelta(days=2))
        masiva = self.crear('Charla masiva', self.ahora - timedelta(days=2), tipo='MASIVA')
        for act in (hecho, futuro):
            Inscripcion.objects.create(actividad=act, alumno=self.alumno)
        Asistencia.objects.create(actividad=hecho, alumno=self.alumno, metodo_ingreso='RUT')
        Asistencia.objects.create(actividad=masiva, alumno=self.alumno_pasaporte, metodo_ingreso='RUT')
        ctx = self.contexto()
        self.assertEqual(ctx['labels_comp'], ['Taller hecho'])
        self.assertEqual(ctx['data_comp_inscritos'], [1])
        self.assertEqual(ctx['data_comp_asistentes'], [1])
        # El top de asistentes sí incluye la masiva, con su tipo
        self.assertIn('Charla masiva', ctx['labels_barras'])
        self.assertIn('Masiva', ctx['tipos_barras'])

    def test_carreras_con_su_escuela(self):
        act = self.crear('Taller hecho', self.ahora - timedelta(days=2))
        Asistencia.objects.create(actividad=act, alumno=self.alumno, metodo_ingreso='RUT')
        ctx = self.contexto()
        self.assertEqual(ctx['labels_pastel'], [self.carrera.nombre])
        self.assertEqual(ctx['escuelas_pastel'], [self.carrera.escuela])
        self.assertEqual(ctx['total_carreras'], 1)

    def test_cada_grafico_explica_que_muestra(self):
        self.login_as(self.admin)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'grafico-ayuda', count=5)
        self.assertContains(r, 'graficoMeses')


class GraficosReportesTests(BaseSistemaTestCase):
    def setUp(self):
        Actividad.objects.all().delete()
        self.login_as(self.admin)

    def test_actividades_ordenadas_y_maximo_diez(self):
        ahora = timezone.now() - timedelta(days=1)
        alumnos = [self.alumno, self.alumno_pasaporte]
        for n in range(12):
            act = self._crear_actividad(f'Charla {n:02d}', 'MASIVA', self.creador, None)
            Actividad.objects.filter(pk=act.pk).update(fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=1))
            for alumno in alumnos[:1 + (n % 2)]:
                Asistencia.objects.create(actividad=act, alumno=alumno, metodo_ingreso='RUT')
        ctx = self.client.get(reverse('reportes')).context
        self.assertEqual(len(ctx['labels_barras']), 10)
        self.assertEqual(ctx['data_barras'], sorted(ctx['data_barras'], reverse=True))
        self.assertEqual(ctx['total_acts_con_datos'], 12)

    def test_carreras_del_detalle_agrupadas_por_escuela(self):
        act = self._crear_actividad('Charla', 'MASIVA', self.creador, None)
        Asistencia.objects.create(actividad=act, alumno=self.alumno, metodo_ingreso='RUT')
        Asistencia.objects.create(actividad=act, alumno=self.alumno_pasaporte, metodo_ingreso='RUT')
        ctx = self.client.get(reverse('reportes')).context
        escuelas = ctx['escuelas_pastel_detalle']
        orden = list(ctx['labels_barras_detalle'])
        self.assertEqual(escuelas, sorted(escuelas, key=orden.index))
        self.assertEqual(len(ctx['escuelas_pastel']), len(ctx['labels_pastel']))
