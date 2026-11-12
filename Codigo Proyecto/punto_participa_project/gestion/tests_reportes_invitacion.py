"""
Actividades con invitación, paso 3b: reportes.

- Detalle: recorrido de la lista a la entrada (invitados, confirmaron, asistieron, no
  asistieron, acompañantes), agregados en la entrada y quiénes no asistieron.
- Exportaciones: los números salen de la lista; la Asistencia que el escáner crea a los
  invitados de la nómina no se cuenta dos veces.
- Reportes (pantalla): la tabla por actividad muestra confirmados y quienes entraron.
"""
import csv
import io
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Acompanante, Actividad, Asistencia, Invitado
from .tests_invitados import BaseInvitadosTests, rut
from .views import _embudo_actividad


class BaseReportesInvitacionTests(BaseInvitadosTests):
    def setUp(self):
        ahora = timezone.now()
        self.act = self.actividad_invitacion(acompanantes_por_invitado=2, titulo='Gala de egreso',
                                             fecha_inicio=ahora - timedelta(hours=1),
                                             fecha_fin=ahora + timedelta(hours=2))
        def inv(**k):
            return Invitado.objects.create(actividad=self.act, correo='x@duocuc.cl', **k)
        # Juan (nómina): confirmó y entró, con un acompañante que entró
        self.juan = inv(alumno=self.alumno, rut='200015509', nombre='Juan Pérez', estado='CONFIRMADO',
                        carrera='Ingeniería en Informática', escuela='Escuela de Informática y Telecomunicaciones',
                        jornada='Diurno', ingreso=ahora, metodo_ingreso='QR', registrado_por=self.registrador)
        Asistencia.objects.create(actividad=self.act, alumno=self.alumno, metodo_ingreso='QR',
                                  registrado_por=self.registrador)
        self.marta = Acompanante.objects.create(invitado=self.juan, rut=rut(18000001), nombre='Marta Pérez',
                                                ingreso=ahora, metodo_ingreso='RUT')
        Acompanante.objects.create(invitado=self.juan, rut=rut(18000002), nombre='Luis No Vino')
        # Rosa (fuera de la nómina): confirmó y no vino
        self.rosa = inv(rut='XK1234567', nombre='Rosa Fuera', estado='CONFIRMADO', carrera='Diseño Gráfico',
                        escuela='Escuela de Diseño', jornada='Vespertino')
        # Pedro: no respondió y no vino. Ana: dijo que no.
        inv(rut=rut(17000011), nombre='Pedro Sin Respuesta', carrera='Diseño Gráfico', escuela='Escuela de Diseño')
        inv(rut='AB123456', nombre='Ana Gómez', estado='RECHAZADO', carrera='Diseño Gráfico',
            escuela='Escuela de Diseño')
        # Agregado en la entrada
        inv(rut=rut(17000012), nombre='Llegó Sin Lista', estado='CONFIRMADO', carrera='Diseño Gráfico',
            escuela='Escuela de Diseño', agregado_en_entrada=True, ingreso=ahora, metodo_ingreso='RUT')
        self.login_as(self.admin)

    def csv_filas(self, reporte, **filtros):
        resp = self.client.get(reverse('exportar_reporte', args=[reporte, 'csv']), filtros)
        self.assertEqual(resp.status_code, 200)
        return list(csv.DictReader(io.StringIO(resp.content.decode('utf-8-sig')), delimiter=';'))


class DetalleTests(BaseReportesInvitacionTests):
    def test_recorrido(self):
        e = _embudo_actividad(self.act)
        self.assertEqual((e['invitados'], e['confirmados'], e['asistieron'], e['no_asistieron']), (5, 3, 2, 2))
        self.assertEqual((e['acompanantes_registrados'], e['acompanantes_entraron'], e['agregados']), (2, 1, 1))
        self.assertEqual(e['tasa'], 50.0)    # 2 entraron de 4 que no dijeron que no
        self.assertEqual([i.nombre for i in e['faltantes']], ['Pedro Sin Respuesta', 'Rosa Fuera'])
        self.assertEqual([p['etiqueta'] for p in e['pasos']],
                         ['Invitados', 'Confirmaron', 'Asistieron', 'No asistieron', 'Acompañantes'])

    def test_antes_de_empezar(self):
        Actividad.objects.filter(pk=self.act.pk).update(fecha_inicio=timezone.now() + timedelta(days=1))
        self.act.refresh_from_db()
        e = _embudo_actividad(self.act)
        self.assertIsNone(e['no_asistieron'])
        self.assertEqual(e['faltantes'], [])

    def test_pantalla_de_detalle(self):
        resp = self.client.get(reverse('actividad_detalle', args=[self.act.pk]))
        self.assertContains(resp, 'De la lista a la entrada')
        self.assertContains(resp, 'CONFIRMARON')
        self.assertContains(resp, 'Ver quiénes no asistieron (2)')
        self.assertContains(resp, 'se agregó en la entrada')


class ExportacionesTests(BaseReportesInvitacionTests):
    def test_resumen(self):
        fila = next(f for f in self.csv_filas('resumen') if f['Actividad'] == 'Gala de egreso')
        self.assertEqual(fila['Tipo'], 'Con invitación')
        self.assertEqual((fila['Invitados'], fila['Inscritos'], fila['Asistentes'], fila['No asistieron']),
                         ('5', '3', '2', '2'))
        self.assertEqual(fila['% asistencia'], '50,0')
        self.assertEqual(fila['Acompañantes'], '1')
        otra = next(f for f in self.csv_filas('resumen') if f['Actividad'] == 'Taller integral')
        self.assertEqual(otra['Acompañantes'], '')

    def test_participacion_por_carrera_desde_la_lista(self):
        suma = {}
        for f in self.csv_filas('participacion'):
            if f['Actividad'] != 'Gala de egreso':
                continue
            t = suma.setdefault(f['Carrera'], [0, 0, 0])
            for n, col in enumerate(('Inscritos', 'Asistentes', 'No asistieron')):
                t[n] += int(f[col] or 0)
        self.assertEqual(set(suma), {'Ingeniería en Informática', 'Diseño Gráfico'})
        # La Asistencia que el escáner le creó a Juan no se cuenta dos veces
        self.assertEqual(suma['Ingeniería en Informática'], [1, 1, 0])
        # Rosa y el agregado confirmaron; entró el agregado; no vinieron Rosa y Pedro (Ana dijo que no)
        self.assertEqual(suma['Diseño Gráfico'], [2, 1, 2])

    def test_listado_con_invitados_y_acompanantes(self):
        filas = [f for f in self.csv_filas('participantes') if f['Actividad'] == 'Gala de egreso']
        por_nombre = {f['Nombres']: f for f in filas}
        self.assertEqual(len(filas), 7)              # 5 invitados + 2 acompañantes, Juan una sola vez
        juan = por_nombre['Juan']
        self.assertEqual((juan['Apellidos'], juan['Participa como'], juan['Asistió'], juan['Método']),
                         ('Pérez', 'Invitado', 'Sí', 'Código QR'))
        self.assertEqual((juan['Inscrito'], juan['Estado inscripción']), ('Sí', 'Confirmó'))
        marta = por_nombre['Marta Pérez']
        self.assertEqual((marta['Participa como'], marta['Asistió']), ('Acompañante de Juan Pérez', 'Sí'))
        self.assertEqual(por_nombre['Luis No Vino']['Asistió'], 'No')
        self.assertEqual(por_nombre['Rosa Fuera']['Documento'], 'XK1234567')
        self.assertEqual(por_nombre['Ana Gómez']['Estado inscripción'], 'No asistirá')
        self.assertEqual(por_nombre['Llegó Sin Lista']['Participa como'], 'Invitado (agregado en la entrada)')
        # Los acompañantes van justo después de su invitado
        orden = [f['Nombres'] for f in filas]
        self.assertEqual(orden[orden.index('Juan') + 1:orden.index('Juan') + 3], ['Luis No Vino', 'Marta Pérez'])
        otros = [f for f in self.csv_filas('participantes') if f['Actividad'] == 'Taller integral']
        self.assertTrue(all(f['Participa como'] == 'Alumno' for f in otros))

    def test_filtro_por_carrera(self):
        filas = [f for f in self.csv_filas('participantes', carrera='Ingeniería en Informática')
                 if f['Actividad'] == 'Gala de egreso']
        self.assertEqual(sorted(f['Nombres'] for f in filas), ['Juan', 'Luis No Vino', 'Marta Pérez'])


class PantallaReportesTests(BaseReportesInvitacionTests):
    def test_tabla_por_actividad(self):
        resp = self.client.get(reverse('reportes'))
        act = next(a for a in resp.context['actividades'] if a.pk == self.act.pk)
        self.assertEqual((act.total_inscritos, act.total_asistentes), (3, 3))   # 2 invitados + 1 acompañante
