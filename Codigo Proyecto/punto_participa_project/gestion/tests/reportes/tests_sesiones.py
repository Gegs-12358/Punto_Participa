"""
Asistencia por sesión y cumplimiento del mínimo (certificados de participación): el cálculo, el reporte
"Asistencia por sesión" y la tabla de Participantes.

Correr solo este archivo:
    python manage.py test gestion.tests.reportes.tests_sesiones --noinput
"""
import csv
import io
from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook

from django.urls import reverse
from django.utils import timezone

from ...models import (Acompanante, Actividad, Alumno, Asistencia, AsistenciaSesion, Inscripcion, Invitado,
                       LogAuditoria, Sesion)
from ...servicios.sesiones import cumple, cumplimiento
from ..base import BaseSistemaTestCase


def con_sesiones(actividad, n):
    """Deja la actividad con n sesiones semanales (las primeras ya realizadas)."""
    base = timezone.now() - timedelta(days=7 * (n - 1))
    actividad.sesiones.all().delete()
    sesiones = [Sesion.objects.create(actividad=actividad, numero=i + 1, fecha_inicio=base + timedelta(days=7 * i),
                                      fecha_fin=base + timedelta(days=7 * i, hours=2)) for i in range(n)]
    Actividad.objects.filter(pk=actividad.pk).update(fecha_inicio=sesiones[0].fecha_inicio,
                                                     fecha_fin=sesiones[-1].fecha_fin)
    actividad.refresh_from_db()
    return sesiones


class ReglaCumpleTests(BaseSistemaTestCase):
    def test_cumple_con_el_minimo_exacto_y_no_por_debajo(self):
        casos = [
            ((3, 4, 75), True),     # 75 % justo
            ((2, 4, 75), False),
            ((2, 3, 75), False),    # 66 %
            ((4, 4, 100), True),
            ((1, 1, 75), True),     # una sola sesión: cumple quien asistió
            ((0, 1, 75), False),
            ((0, 4, 1), False),     # sin asistencia nunca cumple
        ]
        for (asistidas, total, minima), esperado in casos:
            with self.subTest(asistidas=asistidas, total=total, minima=minima):
                self.assertEqual(cumple(asistidas, total, minima), esperado)


class BaseCumplimientoTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ana = Alumno.objects.create(rut='111111111', nombres='Beatriz', apellidos='Arce', correo='beatriz@duocuc.cl',
                                        carrera='Ilustración', jornada='Vespertino')
        cls.sesiones = con_sesiones(cls.actividad, 4)
        Actividad.objects.filter(pk=cls.actividad.pk).update(asistencia_minima=75)
        cls.actividad.refresh_from_db()
        # Juan: 3 de 4 (cumple). Beatriz: 2 de 4 (no cumple). Alumno con pasaporte: inscrito, nunca vino.
        for alumno in (cls.alumno, cls.ana, cls.alumno_pasaporte):
            Inscripcion.objects.create(actividad=cls.actividad, alumno=alumno)
        for s in cls.sesiones[:3]:
            AsistenciaSesion.objects.create(sesion=s, alumno=cls.alumno, metodo_ingreso='QR')
        for s in (cls.sesiones[0], cls.sesiones[3]):
            AsistenciaSesion.objects.create(sesion=s, alumno=cls.ana, metodo_ingreso='RUT')


class CumplimientoTests(BaseCumplimientoTests):
    def test_taller_inscritos_sesiones_porcentaje_y_cumple(self):
        filas = {p['nombres']: p for p in cumplimiento(self.actividad)}
        self.assertEqual(set(filas), {'Juan', 'Beatriz', self.alumno_pasaporte.nombres})
        juan, ana, sin = filas['Juan'], filas['Beatriz'], filas[self.alumno_pasaporte.nombres]
        self.assertEqual((juan['sesiones_asistidas'], juan['porcentaje'], juan['cumple']), ([1, 2, 3], 75, True))
        self.assertEqual((ana['sesiones_asistidas'], ana['porcentaje'], ana['cumple']), ([1, 4], 50, False))
        self.assertEqual((sin['asistidas'], sin['cumple']), (0, False))
        self.assertEqual(juan['marcas'], [True, True, True, False])

    def test_subir_el_minimo_cambia_quien_cumple(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(asistencia_minima=100)
        self.actividad.refresh_from_db()
        self.assertFalse(any(p['cumple'] for p in cumplimiento(self.actividad)))

    def test_masiva_solo_quien_asistio(self):
        sesiones = con_sesiones(self.actividad_masiva, 2)
        AsistenciaSesion.objects.create(sesion=sesiones[1], alumno=self.ana)
        filas = cumplimiento(self.actividad_masiva)
        self.assertEqual([(p['nombres'], p['asistidas'], p['cumple']) for p in filas], [('Beatriz', 1, False)])

    def test_una_sesion_cumple_quien_asistio(self):
        Asistencia.objects.create(actividad=self.actividad_otro, alumno=self.ana, metodo_ingreso='RUT')
        [fila] = cumplimiento(self.actividad_otro)
        self.assertEqual((fila['total'], fila['porcentaje'], fila['cumple']), (1, 100, True))

    def test_con_invitacion_invitados_y_acompanantes(self):
        ahora = timezone.now()
        act = Actividad.objects.create(titulo='Ciclo de charlas', descripcion='d', tipo='INVITACION', lugar='Aula',
                                       fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=2),
                                       acompanantes_por_invitado=1)
        s1, s2 = con_sesiones(act, 2)
        va = Invitado.objects.create(actividad=act, rut='XK1', nombre='Rosa Vino', correo='r@x.cl', estado='CONFIRMADO')
        Invitado.objects.create(actividad=act, rut='XK2', nombre='Pedro No', correo='p@x.cl', estado='RECHAZADO')
        Invitado.objects.create(actividad=act, rut='XK3', nombre='Luis Pendiente', correo='l@x.cl')
        ac = Acompanante.objects.create(invitado=va, rut='XK4', nombre='Marta Acompaña')
        for s in (s1, s2):
            AsistenciaSesion.objects.create(sesion=s, invitado=va)
        AsistenciaSesion.objects.create(sesion=s2, acompanante=ac)
        filas = {p['nombres']: p for p in cumplimiento(act)}
        self.assertEqual(set(filas), {'Rosa Vino', 'Luis Pendiente', 'Marta Acompaña'})   # sin el que dijo que no
        self.assertTrue(filas['Rosa Vino']['cumple'])
        self.assertEqual(filas['Marta Acompaña']['participa_como'], 'Acompañante de Rosa Vino')
        self.assertFalse(filas['Marta Acompaña']['cumple'])


class ReporteSesionesTests(BaseCumplimientoTests):
    def filas_csv(self, **filtros):
        r = self.client.get(reverse('exportar_reporte', args=['sesiones', 'csv']), filtros)
        self.assertEqual(r.status_code, 200)
        return list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig')), delimiter=';'))

    def test_una_fila_por_persona_con_sesiones_porcentaje_y_cumple(self):
        self.login_as(self.admin)
        filas = {f['Nombres']: f for f in self.filas_csv(actividad=self.actividad.pk)}
        juan = filas['Juan']
        self.assertEqual((juan['Sesiones de la actividad'], juan['Sesiones asistidas'], juan['Asistió a las sesiones'],
                          juan['% asistencia'], juan['Mínimo para cumplir'], juan['Cumple']),
                         ('4', '3', '1, 2, 3', '75,0', '75,0', 'Sí'))
        self.assertEqual(filas['Beatriz']['Cumple'], 'No')
        self.assertEqual(juan['Documento'], '20.001.550-9')

    def test_excel_con_su_hoja_y_explicacion(self):
        self.login_as(self.admin)
        r = self.client.get(reverse('exportar_reporte', args=['sesiones', 'excel']), {'actividad': self.actividad.pk})
        wb = load_workbook(BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ['Asistencia por sesión', 'Información'])
        hoja = wb['Asistencia por sesión']
        self.assertEqual(hoja.cell(1, 17).value, 'Cumple')
        info = ' '.join(str(c.value) for fila in wb['Información'].iter_rows() for c in fila if c.value)
        self.assertIn('certificados de participación', info)

    def test_filtro_por_carrera(self):
        self.login_as(self.admin)
        filas = self.filas_csv(actividad=self.actividad.pk, carrera='Ilustración')
        self.assertEqual([f['Nombres'] for f in filas], ['Beatriz'])

    def test_permisos_y_auditoria(self):
        self.login_as(self.registrador)
        self.assertEqual(self.client.get(reverse('exportar_reporte', args=['sesiones', 'excel'])).status_code, 403)
        # El otro creador no ve las personas de este taller
        self.login_as(self.otro_creador)
        self.assertEqual([f['Actividad'] for f in self.filas_csv() if f['Actividad'] == self.actividad.titulo], [])
        self.login_as(self.creador)
        self.assertTrue(self.filas_csv(actividad=self.actividad.pk))
        log = LogAuditoria.objects.filter(accion='Exportar reporte').latest('fecha_registro')
        self.assertIn('Asistencia por sesión', log.detalle)


class PantallaParticipantesTests(BaseCumplimientoTests):
    def test_tabla_por_sesion_en_una_actividad_de_varias_sesiones(self):
        self.login_as(self.creador)
        r = self.client.get(reverse('participantes_actividad', args=[self.actividad.pk]))
        self.assertContains(r, 'Asistencia por sesión')
        self.assertContains(r, '1 de 3 cumple el mínimo de 75 %')
        self.assertContains(r, '3 de 4 (75 %)')
        self.assertContains(r, 'S4')

    def test_detalle_ofrece_la_descarga(self):
        self.login_as(self.creador)
        r = self.client.get(reverse('actividad_detalle', args=[self.actividad.pk]))
        self.assertContains(r, f"{reverse('exportar_reporte', args=['sesiones', 'excel'])}?actividad={self.actividad.pk}")

    def test_una_actividad_de_una_sesion_no_muestra_la_tabla(self):
        self.login_as(self.creador)
        for nombre in ('participantes_actividad', 'actividad_detalle'):
            with self.subTest(pantalla=nombre):
                r = self.client.get(reverse(nombre, args=[self.actividad_masiva.pk]))
                self.assertNotContains(r, 'Asistencia por sesión')
