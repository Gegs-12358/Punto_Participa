"""
Pantalla Alumnos (P1): directorio, ficha con historial y bloqueo manual.

- Solo el Administrador entra.
- Buscar por RUT (con o sin puntos), nombre y apellido juntos, o correo; filtrar por
  carrera, jornada y estado.
- La ficha muestra el historial con la carrera que tenía en cada actividad y marca
  "No asistió" solo en talleres ya realizados.
- Bloquear a mano pide un motivo, queda en auditoría y la nómina lo respeta.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .importador_alumnos import analizar, aplicar
from .models import Actividad, Alumno, Asistencia, Inscripcion, LogAuditoria
from .tests_integrales import BaseSistemaTestCase

URL = reverse('lista_alumnos')


class BaseAlumnosTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)

    def _ids(self, **filtros):
        resp = self.client.get(URL, filtros)
        self.assertEqual(resp.status_code, 200)
        return {a.pk for a in resp.context['alumnos']}

    def _bloquear(self, alumno, motivo='Solicitud del alumno', **extra):
        return self.client.post(reverse('alumno_bloqueo', args=[alumno.pk]),
                                {'accion': 'bloquear', 'motivo': motivo, **extra}, follow=True)


class AccesoTests(BaseAlumnosTests):
    def test_solo_administrador(self):
        for usuario in (self.creador, self.registrador):
            with self.subTest(usuario=usuario.username):
                self.login_as(usuario)
                self.assertEqual(self.client.get(URL).status_code, 302)
                self.assertEqual(self.client.get(reverse('alumno_detalle', args=[self.alumno.pk])).status_code, 302)
                self.client.post(reverse('alumno_bloqueo', args=[self.alumno.pk]),
                                 {'accion': 'bloquear', 'motivo': 'x'})
                self.alumno.refresh_from_db()
                self.assertTrue(self.alumno.activo)

    def test_bloqueo_solo_por_post(self):
        resp = self.client.get(reverse('alumno_bloqueo', args=[self.alumno.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_menu_lleva_a_alumnos(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'Importar nómina')
        self.assertContains(resp, f'href="{reverse("importar_alumnos")}"')
        self.assertContains(self.client.get(reverse('dashboard')), f'href="{URL}"')


class DirectorioTests(BaseAlumnosTests):
    def test_busca_por_rut_con_o_sin_puntos(self):
        for texto in ('20.001.550-9', '200015509', '20001550'):
            with self.subTest(texto=texto):
                self.assertEqual(self._ids(q=texto), {self.alumno.pk})

    def test_busca_por_nombre_y_apellido_juntos(self):
        self.assertEqual(self._ids(q='juan pérez'), {self.alumno.pk})
        self.assertEqual(self._ids(q='Gómez'), {self.alumno_pasaporte.pk})
        self.assertEqual(self._ids(q='juan gómez'), set())

    def test_busca_por_correo_y_pasaporte(self):
        self.assertEqual(self._ids(q='ana.gomez@'), {self.alumno_pasaporte.pk})
        self.assertEqual(self._ids(q='ab123456'), {self.alumno_pasaporte.pk})

    def test_filtra_por_carrera_jornada_y_estado(self):
        self.assertEqual(self._ids(carrera='Diseño Gráfico'), {self.alumno_pasaporte.pk})
        self.assertEqual(self._ids(jornada='diurno'), {self.alumno.pk})
        Alumno.objects.filter(pk=self.alumno.pk).update(activo=False)
        Alumno.objects.filter(pk=self.alumno_pasaporte.pk).update(activo=False, bloqueo_manual=True)
        self.assertEqual(self._ids(estado='nomina'), {self.alumno.pk})
        self.assertEqual(self._ids(estado='manual'), {self.alumno_pasaporte.pk})
        self.assertEqual(self._ids(estado='activo'), set())

    def test_cuenta_inscripciones_y_asistencias(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Asistencia.objects.create(actividad=self.actividad, alumno=self.alumno, metodo_ingreso='RUT')
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno, metodo_ingreso='RUT')
        resp = self.client.get(URL)
        juan = next(a for a in resp.context['alumnos'] if a.pk == self.alumno.pk)
        self.assertEqual((juan.total_inscripciones, juan.total_asistencias), (1, 2))
        self.assertEqual(resp.context['totales']['activos'], 2)

    def test_busqueda_hostil_no_rompe(self):
        for texto in ("' OR 1=1 --", '<script>x</script>', 'a' * 500, '\x00'):
            with self.subTest(texto=texto[:20]):
                resp = self.client.get(URL, {'q': texto, 'estado': 'raro', 'page': 'x'})
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, '<script>x</script>')


class FichaTests(BaseAlumnosTests):
    def setUp(self):
        super().setUp()
        ahora = timezone.now()
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_inicio=ahora - timedelta(days=1))
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)        # fue al pasado y faltó
        Inscripcion.objects.create(actividad=self.actividad_otro, alumno=self.alumno)   # futuro: pendiente
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno, metodo_ingreso='QR')

    def test_historial_y_resumen(self):
        resp = self.client.get(reverse('alumno_detalle', args=[self.alumno.pk]))
        self.assertEqual(resp.status_code, 200)
        r = resp.context['resumen']
        self.assertEqual((r['actividades'], r['inscripciones'], r['asistencias'], r['faltas']), (3, 2, 1, 1))
        estados = {f['actividad'].titulo: (f['falto'], f['pendiente']) for f in resp.context['historial']}
        self.assertEqual(estados['Taller integral'], (True, False))
        self.assertEqual(estados['Actividad de otro creador'], (False, True))
        self.assertContains(resp, 'No asistió')
        self.assertContains(resp, 'Pendiente')
        self.assertContains(resp, 'Código QR')

    def test_historial_usa_la_carrera_de_ese_momento(self):
        self.alumno.carrera = 'Diseño Gráfico'
        self.alumno.save()
        resp = self.client.get(reverse('alumno_detalle', args=[self.alumno.pk]))
        carreras = {f['carrera'] for f in resp.context['historial']}
        self.assertEqual(carreras, {'Ingeniería en Informática'})

    def test_alumno_inexistente_da_404(self):
        self.assertEqual(self.client.get(reverse('alumno_detalle', args=[999999])).status_code, 404)


class BloqueoTests(BaseAlumnosTests):
    def test_bloquear_pide_motivo(self):
        resp = self._bloquear(self.alumno, motivo='   ')
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.activo)
        self.assertContains(resp, 'Escribe el motivo del bloqueo')

    def test_bloquear_y_desbloquear_quedan_en_auditoria(self):
        self._bloquear(self.alumno, motivo='Retiro de la institución', volver='detalle')
        self.alumno.refresh_from_db()
        self.assertEqual((self.alumno.activo, self.alumno.bloqueo_manual, self.alumno.estado),
                         (False, True, 'manual'))
        self.assertEqual(self.alumno.motivo_bloqueo, 'Retiro de la institución')
        log = LogAuditoria.objects.get(accion='Bloquear alumno')
        self.assertEqual((log.modulo, log.objeto_id), ('Alumnos', self.alumno.pk))
        self.assertEqual(log.cambios_json['motivo'], 'Retiro de la institución')

        resp = self.client.post(reverse('alumno_bloqueo', args=[self.alumno.pk]),
                                {'accion': 'desbloquear', 'volver': 'detalle'})
        self.assertRedirects(resp, reverse('alumno_detalle', args=[self.alumno.pk]))
        self.alumno.refresh_from_db()
        self.assertEqual((self.alumno.activo, self.alumno.bloqueo_manual, self.alumno.motivo_bloqueo),
                         (True, False, ''))
        self.assertTrue(LogAuditoria.objects.filter(accion='Desbloquear alumno').exists())

    def test_bloqueado_no_puede_inscribirse(self):
        self._bloquear(self.alumno)
        self.client.logout()
        self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]),
                         {'rut': '20.001.550-9', 'acepta_politica': 'on'})
        self.assertFalse(Inscripcion.objects.filter(alumno=self.alumno).exists())

    def test_desbloquear_bloqueado_por_nomina_avisa(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(activo=False)
        resp = self.client.post(reverse('alumno_bloqueo', args=[self.alumno.pk]),
                                {'accion': 'desbloquear'}, follow=True)
        self.assertContains(resp, 'no venía en la última nómina')

    def test_accion_desconocida(self):
        resp = self.client.post(reverse('alumno_bloqueo', args=[self.alumno.pk]), {'accion': 'borrar'},
                                follow=True)
        self.assertContains(resp, 'Acción no válida')
        self.assertTrue(Alumno.objects.filter(pk=self.alumno.pk, activo=True).exists())


class NominaRespetaBloqueoManualTests(BaseAlumnosTests):
    def _fila(self, alumno, **cambios):
        datos = {'rut': alumno.rut, 'tipo_documento': alumno.tipo_documento, 'nombres': alumno.nombres,
                 'apellidos': alumno.apellidos, 'correo': alumno.correo, 'carrera': alumno.carrera,
                 'jornada': alumno.jornada}
        datos.update(cambios)
        return datos

    def test_nomina_no_desbloquea_al_bloqueado_a_mano(self):
        self._bloquear(self.alumno)
        res = analizar([(2, self._fila(self.alumno, correo='nuevo@example.com')),
                        (3, self._fila(self.alumno_pasaporte))])
        self.assertTrue(any('bloqueado a mano' in texto for _, texto in res.avisos))
        aplicar(res)
        self.alumno.refresh_from_db()
        self.assertFalse(self.alumno.activo)
        self.assertTrue(self.alumno.bloqueo_manual)
        self.assertEqual(self.alumno.correo, 'nuevo@example.com')   # los datos sí se actualizan

    def test_nomina_si_reactiva_al_bloqueado_por_nomina(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(activo=False)
        aplicar(analizar([(2, self._fila(self.alumno)), (3, self._fila(self.alumno_pasaporte))]))
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.activo)
