from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from gestion.models import (
    Actividad, Alumno, Asistencia, Carrera, Inscripcion, Rol, UsuarioSistema,
)


class BaseKpiTests(TestCase):
    def setUp(self):
        rol = Rol.objects.create(nombre='Administrador')
        admin = User.objects.create_user('admin_kpi', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=rol, activo=True,
            must_change_password=False, rut='11111111K',
        )
        self.client.force_login(admin)
        self.admin = admin

        Carrera.objects.create(nombre='Informática', escuela='Escuela A')
        Carrera.objects.create(nombre='Construcción', escuela='Escuela B')

        ahora = timezone.now()
        self.taller = Actividad.objects.create(
            titulo='Taller KPI', descripcion='x', tipo='TALLER', lugar='Sala',
            cupos_totales=50, cupos_disponibles=50,
            fecha_inicio=ahora - timedelta(hours=2),
            fecha_fin=ahora + timedelta(hours=2),
            estado='ACTIVA', creado_por=admin,
        )
        self.a1 = self._alumno('10000001', 'Informática')
        self.a2 = self._alumno('10000002', 'Informática')
        self.a3 = self._alumno('10000003', 'Construcción')
        for a in (self.a1, self.a2, self.a3):
            Inscripcion.objects.create(actividad=self.taller, alumno=a, estado='CONFIRMADA')
        # Solo a1 asiste.
        Asistencia.objects.create(actividad=self.taller, alumno=self.a1, metodo_ingreso='RUT')
        self.taller.carreras.add(*Carrera.objects.all())

    def _alumno(self, rut, carrera):
        return Alumno.objects.create(
            rut=rut, nombres='Al', apellidos=rut, correo=f'{rut}@duocuc.cl',
            carrera=carrera, jornada='Diurno',
        )


class KpiReportesTests(BaseKpiTests):
    def test_reportes_cuenta_inscritos_que_no_asistieron(self):
        r = self.client.get(reverse('reportes'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_inscritos_filtrado'], 3)
        self.assertEqual(r.context['talleres_inscritos'], 3)

    def test_reportes_filtro_carrera_cuenta_solo_esa_carrera(self):
        r = self.client.get(reverse('reportes'), {'carrera': 'Informática'})
        self.assertEqual(r.context['total_inscritos_filtrado'], 2)
        self.assertEqual(r.context['talleres_inscritos'], 2)

    def test_reportes_filtro_escuela_cuenta_solo_esa_escuela(self):
        r = self.client.get(reverse('reportes'), {'escuela': 'Escuela B'})
        self.assertEqual(r.context['total_inscritos_filtrado'], 1)
        self.assertEqual(r.context['talleres_inscritos'], 1)

    def test_reportes_tasa_de_talleres_no_se_infla(self):
        # 1 asistente de 3 inscritos = 33.3 %, no 100 %.
        r = self.client.get(reverse('reportes'))
        self.assertEqual(r.context['tasa_talleres'], 33.3)

    def test_reportes_inscritos_por_actividad_incluye_a_quienes_no_asistieron(self):
        r = self.client.get(reverse('reportes'))
        act = [a for a in r.context['actividades'] if a.pk == self.taller.pk][0]
        self.assertEqual(act.total_inscritos_calc, 3)

class KpiDashboardTests(BaseKpiTests):
    def test_dashboard_sin_filtros_cuenta_todos_los_inscritos(self):
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_inscritos'], 3)

    def test_dashboard_filtro_carrera_cuenta_solo_esa_carrera(self):
        r = self.client.get(reverse('dashboard'), {'carrera': 'Informática'})
        self.assertEqual(r.context['total_inscritos'], 2)
        # 1 asistente de 2 inscritos informáticos = 50 %.
        self.assertEqual(r.context['tasa_asistencia'], 50.0)

class KpiExportacionTests(BaseKpiTests):
    def test_exportacion_cuenta_inscritos_que_no_asistieron(self):
        r = self.client.get(reverse('exportar_reportes', args=['csv']))
        self.assertEqual(r.status_code, 200)
        filas = r.content.decode('utf-8-sig').splitlines()
        cabecera = filas[0].split(';')
        self.assertIn('Inscritos', cabecera)
        fila = filas[1].split(';')
        self.assertEqual(fila[cabecera.index('Inscritos')], '3')
        self.assertEqual(fila[cabecera.index('Asistentes')], '1')

    def test_exportacion_filtro_carrera_cuenta_solo_esa_carrera(self):
        r = self.client.get(reverse('exportar_reportes', args=['csv']),
                            {'carrera': 'Informática'})
        filas = r.content.decode('utf-8-sig').splitlines()
        cabecera = filas[0].split(';')
        fila = filas[1].split(';')
        self.assertEqual(fila[cabecera.index('Inscritos')], '2')

    def test_csv_usa_punto_y_coma_como_separador(self):
        r = self.client.get(reverse('exportar_reportes', args=['csv']))
        cabecera = r.content.decode('utf-8-sig').splitlines()[0]
        self.assertIn(';', cabecera)
