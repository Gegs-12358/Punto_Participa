# Pruebas del comando seed_data: repetirlo no debe fallar ni duplicar datos.
import io

from django.core.management import call_command
from django.test import TestCase

from gestion.models import (
    Actividad, Alumno, Asistencia, Carrera, Inscripcion, Jornada, LogAuditoria,
    NotificacionCorreo, UsuarioSistema,
)


class SeedDataTests(TestCase):
    def _correr(self, *args):
        salida = io.StringIO()
        call_command('seed_data', '--alumnos-por-carrera', '1', '--actividades', '5',
                     *args, stdout=salida)
        return salida.getvalue()

    def _conteos(self):
        modelos = (Alumno, Carrera, Jornada, Actividad, Inscripcion, Asistencia,
                   NotificacionCorreo, LogAuditoria, UsuarioSistema)
        return {m.__name__: m.objects.count() for m in modelos}

    def test_repetirlo_sin_flush_no_falla_ni_duplica_datos(self):
        self._correr()
        antes = self._conteos()
        self.assertGreater(antes['Alumno'], 0)
        self.assertGreater(antes['Actividad'], 0)
        salida = self._correr()
        self.assertEqual(self._conteos(), antes)
        self.assertIn('Ya hay actividades', salida)

    def test_los_alumnos_quedan_con_el_documento_normalizado(self):
        self._correr()
        self.assertFalse(Alumno.objects.filter(rut__contains='-').exists())

    def test_con_flush_regenera_los_datos(self):
        self._correr()
        antes = self._conteos()
        self._correr('--flush')
        despues = self._conteos()
        self.assertEqual(despues['Alumno'], antes['Alumno'])
        self.assertEqual(despues['Actividad'], antes['Actividad'])
