"""
Exportaciones de Reportes (P1): resumen por actividad, participación por escuela/carrera/
jornada, listado de participantes y libro completo.

Se comprueba el contenido (inscritos, asistentes, no asistieron, %), que se use la foto
académica, el formato del Excel (fechas reales, encabezado fijo, autofiltro, hoja
Información), los permisos (el creador solo lo suyo) y el registro en auditoría.
"""
import csv
import io
from datetime import datetime, timedelta
from io import BytesIO

from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from .models import Actividad, Alumno, Asistencia, Inscripcion, LogAuditoria, NotificacionCorreo
from .tests_integrales import BaseSistemaTestCase

INFORMATICA = 'Escuela de Informática y Telecomunicaciones'
DISENO = 'Escuela de Diseño'


def url(tipo, formato='csv'):
    return reverse('exportar_reporte', args=[tipo, formato])


class BaseExportTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Taller y masiva ya empezaron (los de la base parten en 2 días)
        ahora = timezone.now()
        Actividad.objects.filter(pk__in=[cls.actividad.pk, cls.actividad_masiva.pk]).update(
            fecha_inicio=ahora - timedelta(hours=2), fecha_fin=ahora + timedelta(hours=1))
        # Taller: Juan se inscribe y asiste; Ana se inscribe y no asiste
        Inscripcion.objects.create(actividad=cls.actividad, alumno=cls.alumno)
        Inscripcion.objects.create(actividad=cls.actividad, alumno=cls.alumno_pasaporte)
        Asistencia.objects.create(actividad=cls.actividad, alumno=cls.alumno, metodo_ingreso='QR',
                                  registrado_por=cls.registrador)
        # Masiva: Juan asiste (sin inscripción)
        Asistencia.objects.create(actividad=cls.actividad_masiva, alumno=cls.alumno, metodo_ingreso='RUT',
                                  registrado_por=cls.registrador)
        # Invitaciones del taller: 2 a Juan (cuenta una vez) y una fallida a Ana
        for estado, alumno in (('EXITO', cls.alumno), ('EXITO', cls.alumno), ('FALLO', cls.alumno_pasaporte)):
            NotificacionCorreo.objects.create(actividad=cls.actividad, alumno=alumno, estado_envio=estado)
        # Actividad de otro creador con un asistente
        Asistencia.objects.create(actividad=cls.actividad_otro, alumno=cls.alumno_pasaporte,
                                  metodo_ingreso='RUT')

    def setUp(self):
        self.login_as(self.admin)

    def csv_filas(self, reporte, **filtros):
        resp = self.client.get(url(reporte), filtros)
        self.assertEqual(resp.status_code, 200)
        texto = resp.content.decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(texto), delimiter=';'))

    def libro(self, reporte, **filtros):
        resp = self.client.get(url(reporte, 'excel'), filtros)
        self.assertEqual(resp.status_code, 200)
        return load_workbook(BytesIO(resp.content))


class ResumenTests(BaseExportTests):
    def _fila(self, titulo, **filtros):
        return next(f for f in self.csv_filas('resumen', **filtros) if f['Actividad'] == titulo)

    def test_taller_inscritos_asistentes_no_asistieron_y_porcentaje(self):
        fila = self._fila('Taller integral')
        self.assertEqual(fila['Tipo'], 'Taller')
        self.assertEqual(fila['Estado'], 'Activa')
        self.assertEqual(fila['Lugar'], 'Sede Alameda')
        self.assertEqual(fila['Creador'], 'creador_integral')
        self.assertEqual(fila['Invitados'], '1')
        self.assertEqual(fila['Inscritos'], '2')
        self.assertEqual(fila['Asistentes'], '1')
        self.assertEqual(fila['No asistieron'], '1')
        self.assertEqual(fila['% asistencia'], '50,0')

    def test_actividad_futura_sin_no_asistieron_ni_porcentaje(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(
            fecha_inicio=timezone.now() + timedelta(days=1), fecha_fin=timezone.now() + timedelta(days=1, hours=2))
        fila = self._fila('Taller integral')
        self.assertEqual((fila['Inscritos'], fila['No asistieron'], fila['% asistencia']), ('2', '', ''))
        part = [f for f in self.csv_filas('participacion') if f['Actividad'] == 'Taller integral']
        self.assertTrue(all(f['No asistieron'] == '' for f in part))
        ana = next(f for f in self.csv_filas('participantes')
                   if f['Actividad'] == 'Taller integral' and f['Apellidos'] == 'Gómez')
        self.assertEqual(ana['Asistió'], 'Pendiente')

    def test_masiva_sin_inscripcion(self):
        fila = self._fila('Actividad masiva')
        self.assertEqual(fila['Inscritos'], '')
        self.assertEqual(fila['No asistieron'], '')
        self.assertEqual(fila['Asistentes'], '1')

    def test_fechas_en_formato_chileno(self):
        fila = self._fila('Taller integral')
        datetime.strptime(fila['Inicio'], '%d/%m/%Y %H:%M')
        datetime.strptime(fila['Término'], '%d/%m/%Y %H:%M')

    def test_filtro_por_carrera_usa_la_foto(self):
        # Ana se cambia de carrera DESPUÉS de inscribirse: cuenta en su carrera antigua
        Alumno.objects.filter(pk=self.alumno_pasaporte.pk).update(carrera=self.carrera.nombre)
        fila = self._fila('Taller integral', carrera='Diseño Gráfico')
        self.assertEqual((fila['Inscritos'], fila['Asistentes'], fila['No asistieron']), ('1', '0', '1'))

    def test_excel_con_fechas_reales_encabezado_fijo_y_autofiltro(self):
        wb = self.libro('resumen')
        self.assertEqual(wb.sheetnames, ['Resumen por actividad', 'Información'])
        ws = wb['Resumen por actividad']
        self.assertEqual(ws['A1'].value, 'Actividad')
        self.assertEqual(ws.freeze_panes, 'A2')
        self.assertTrue(ws.auto_filter.ref.startswith('A1:N'))
        encabezados = [c.value for c in ws[1]]
        fila = next(r for r in ws.iter_rows(min_row=2) if r[0].value == 'Taller integral')
        inicio = fila[encabezados.index('Inicio')]
        self.assertIsInstance(inicio.value, datetime)
        self.assertEqual(inicio.number_format, 'dd/mm/yyyy hh:mm')
        pct = fila[encabezados.index('% asistencia')]
        self.assertAlmostEqual(pct.value, 0.5)
        self.assertEqual(pct.number_format, '0.0%')


class ParticipacionTests(BaseExportTests):
    def test_una_fila_por_escuela_carrera_y_jornada(self):
        filas = [f for f in self.csv_filas('participacion') if f['Actividad'] == 'Taller integral']
        por_carrera = {f['Carrera']: f for f in filas}
        self.assertEqual(set(por_carrera), {'Ingeniería en Informática', 'Diseño Gráfico'})
        juan = por_carrera['Ingeniería en Informática']
        self.assertEqual((juan['Escuela'], juan['Jornada']), (INFORMATICA, 'Diurno'))
        self.assertEqual((juan['Inscritos'], juan['Asistentes'], juan['No asistieron']), ('1', '1', '0'))
        ana = por_carrera['Diseño Gráfico']
        self.assertEqual((ana['Inscritos'], ana['Asistentes'], ana['No asistieron']), ('1', '0', '1'))

    def test_usa_la_carrera_que_tenia_al_participar(self):
        self.alumno.carrera = 'Diseño Gráfico'
        self.alumno.save()
        filas = [f for f in self.csv_filas('participacion') if f['Actividad'] == 'Actividad masiva']
        self.assertEqual([f['Carrera'] for f in filas], ['Ingeniería en Informática'])

    def test_direccion_anterior_sigue_funcionando(self):
        resp = self.client.get(reverse('exportar_reportes_detalle', args=['csv']))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('No asistieron', resp.content.decode('utf-8-sig').splitlines()[0])


class ParticipantesTests(BaseExportTests):
    def _filas(self, **filtros):
        return {(f['Actividad'], f['Apellidos']): f for f in self.csv_filas('participantes', **filtros)}

    def test_inscrito_que_no_asistio(self):
        ana = self._filas()[('Taller integral', 'Gómez')]
        self.assertEqual(ana['Documento'], 'AB123456')
        self.assertEqual(ana['Tipo de documento'], 'Pasaporte extranjero')
        self.assertEqual((ana['Inscrito'], ana['Estado inscripción'], ana['Asistió']), ('Sí', 'Confirmada', 'No'))
        self.assertEqual((ana['Ingreso'], ana['Método'], ana['Registrado por']), ('', '', ''))
        datetime.strptime(ana['Fecha inscripción'], '%d/%m/%Y %H:%M')

    def test_inscrito_que_asistio(self):
        juan = self._filas()[('Taller integral', 'Pérez')]
        self.assertEqual(juan['Documento'], '20.001.550-9')
        self.assertEqual((juan['Inscrito'], juan['Asistió'], juan['Método']), ('Sí', 'Sí', 'Código QR'))
        self.assertEqual(juan['Registrado por'], 'registrador_integral')
        self.assertEqual((juan['Escuela'], juan['Carrera'], juan['Jornada']),
                         (INFORMATICA, 'Ingeniería en Informática', 'Diurno'))
        datetime.strptime(juan['Ingreso'], '%d/%m/%Y %H:%M')

    def test_masiva_no_aplica_inscripcion(self):
        juan = self._filas()[('Actividad masiva', 'Pérez')]
        self.assertEqual((juan['Inscrito'], juan['Asistió']), ('No aplica', 'Sí'))

    def test_filtro_por_jornada(self):
        filas = self._filas(jornada='Vespertino')
        self.assertTrue(filas)
        self.assertTrue(all(f['Jornada'] == 'Vespertino' for f in filas.values()))

    def test_excel_con_aviso_de_datos_personales(self):
        wb = self.libro('participantes')
        self.assertEqual(wb.sheetnames, ['Participantes', 'Información'])
        textos = [c.value for fila in wb['Información'].iter_rows() for c in fila if c.value]
        self.assertTrue(any('datos personales' in str(t).lower() for t in textos))


class LibroYGeneralTests(BaseExportTests):
    def test_libro_completo_trae_las_tres_hojas_e_informacion(self):
        wb = self.libro('libro')
        self.assertEqual(wb.sheetnames, ['Resumen por actividad', 'Por escuela y carrera', 'Participantes',
                                         'Información'])

    def test_hoja_informacion_con_filtros_y_usuario(self):
        wb = self.libro('resumen', tipo='TALLER', actividad=self.actividad.pk)
        info = {fila[0].value: fila[1].value for fila in wb['Información'].iter_rows() if fila[0].value}
        self.assertEqual(info['Generado por'], 'admin_integral')
        self.assertIsInstance(info['Generado el'], datetime)
        self.assertEqual(info['Tipo'], 'Taller')
        self.assertEqual(info['Actividad'], 'Taller integral')

    def test_tipo_o_formato_invalido_da_404(self):
        for tipo, formato in (('libro', 'csv'), ('otro', 'csv'), ('resumen', 'pdf')):
            with self.subTest(tipo=tipo, formato=formato):
                self.assertEqual(self.client.get(url(tipo, formato)).status_code, 404)

    def test_nombre_de_archivo_con_fecha(self):
        resp = self.client.get(url('resumen'))
        self.assertRegex(resp['Content-Disposition'],
                         r'attachment; filename="punto_participa_resumen_\d{8}_\d{4}\.csv"')

    def test_neutraliza_formulas_en_textos(self):
        self.actividad.titulo = '=HYPERLINK("http://x")'
        self.actividad.save(update_fields=['titulo'])
        titulos = [f['Actividad'] for f in self.csv_filas('resumen')]
        self.assertIn('\'=HYPERLINK("http://x")', titulos)
        ws = self.libro('participantes')['Participantes']
        self.assertTrue(all(not str(c.value).startswith('=') for c in ws['A'] if c.value))


class PermisosYAuditoriaTests(BaseExportTests):
    def test_creador_solo_exporta_sus_actividades(self):
        self.login_as(self.creador)
        for tipo in ('resumen', 'participacion', 'participantes'):
            with self.subTest(tipo=tipo):
                titulos = {f['Actividad'] for f in self.csv_filas(tipo)}
                self.assertNotIn('Actividad de otro creador', titulos)
                self.assertIn('Taller integral', titulos)
        # Aunque pida la actividad ajena por id
        filas = self.csv_filas('participantes', actividad=self.actividad_otro.pk)
        self.assertEqual(filas, [])

    def test_registrador_no_puede_exportar(self):
        self.login_as(self.registrador)
        for tipo in ('resumen', 'participacion', 'participantes', 'libro'):
            with self.subTest(tipo=tipo):
                self.assertEqual(self.client.get(url(tipo, 'excel')).status_code, 403)

    def test_sin_sesion_no_puede_exportar(self):
        self.client.logout()
        self.assertIn(self.client.get(url('participantes')).status_code, (302, 401))

    def test_cada_descarga_queda_en_auditoria(self):
        self.csv_filas('participantes', tipo='TALLER')
        log = LogAuditoria.objects.filter(accion='Exportar reporte').latest('fecha_registro')
        self.assertEqual(log.modulo, 'Reportes')
        self.assertEqual(log.usuario_sistema, self.admin)
        self.assertIn('Listado de participantes (CSV)', log.detalle)
        self.assertIn('Tipo: Taller', log.detalle)
        self.assertEqual(log.cambios_json['reporte'], 'participantes')
        self.assertEqual(log.cambios_json['formato'], 'csv')
        self.assertEqual(log.cambios_json['filtros'], {'Tipo': 'Taller'})
        self.assertEqual(log.cambios_json['filas'], 3)

    def test_descarga_rechazada_no_queda_en_auditoria(self):
        self.login_as(self.registrador)
        self.client.get(url('participantes'))
        self.assertFalse(LogAuditoria.objects.filter(accion='Exportar reporte').exists())
