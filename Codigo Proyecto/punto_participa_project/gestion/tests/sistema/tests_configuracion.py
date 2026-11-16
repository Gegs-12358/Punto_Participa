"""
Configuración desde .env, datos de prueba repetibles y scripts del respaldo.

Correr solo este archivo:
    python manage.py test gestion.tests.sistema.tests_configuracion --noinput
"""
import io
from pathlib import Path

from gestion.models import Actividad, Alumno, Asistencia, Carrera, Inscripcion, Jornada, NotificacionCorreo, UsuarioSistema
from punto_participa.settings import _lista
import subprocess

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ...models import LogAuditoria


class ConfiguracionTests(SimpleTestCase):
    def test_lista_separada_por_comas(self):
        self.assertEqual(_lista(' a.cl, b.cl ,,'), ['a.cl', 'b.cl'])
        self.assertEqual(_lista(''), [])

    def test_valores_por_defecto_seguros_para_desarrollo(self):
        self.assertIn('Punto Participa', settings.DEFAULT_FROM_EMAIL)
        self.assertNotIn('casicasi', settings.DEFAULT_FROM_EMAIL)
        self.assertTrue(settings.EMAIL_BACKEND)
        self.assertIsInstance(settings.SECURE_HSTS_SECONDS, int)

    def test_el_bloque_de_produccion_ya_no_esta_comentado(self):
        texto = (Path(settings.BASE_DIR) / 'punto_participa' / 'settings.py').read_text(encoding='utf-8')
        self.assertNotIn('DESCOMENTAR PARA PRODUCCIÓN', texto)
        self.assertIn("config('SECURE_SSL_REDIRECT'", texto)


class ArchivosDelProyectoTests(SimpleTestCase):
    def test_requirements_en_utf8(self):
        datos = (Path(settings.BASE_DIR) / 'requirements.txt').read_bytes()
        self.assertFalse(datos.startswith((b'\xff\xfe', b'\xfe\xff')), 'requirements.txt sigue en UTF-16')
        self.assertIn('Django==', datos.decode('utf-8'))

    def test_entrypoint_sin_comentarios_de_plantilla(self):
        texto = (Path(settings.BASE_DIR) / 'entrypoint.sh').read_text(encoding='utf-8')
        self.assertNotIn('AJUSTAR', texto)
        self.assertNotIn('\r\n', texto)


CARPETA = Path(settings.BASE_DIR) / 'respaldo'


SCRIPTS = ('respaldar.sh', 'verificar.sh', 'restaurar.sh', 'programar.sh')


class ScriptsRespaldoTests(SimpleTestCase):
    def test_los_scripts_existen_y_no_tienen_errores_de_sintaxis(self):
        for nombre in SCRIPTS:
            with self.subTest(script=nombre):
                ruta = CARPETA / nombre
                self.assertTrue(ruta.exists(), f'falta {ruta}')
                resultado = subprocess.run(['sh', '-n', str(ruta)], capture_output=True, text=True)
                self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_los_scripts_usan_saltos_de_linea_de_linux(self):
        # Con CRLF (guardados en Windows) sh falla en el contenedor
        for nombre in SCRIPTS:
            with self.subTest(script=nombre):
                self.assertNotIn(b'\r\n', (CARPETA / nombre).read_bytes())

    def test_restaurar_exige_confirmacion(self):
        resultado = subprocess.run(['sh', str(CARPETA / 'restaurar.sh'), 'x.dump'],
                                   capture_output=True, text=True)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('--confirmo', resultado.stderr)

    def test_el_servicio_esta_en_docker_compose(self):
        compose = (Path(settings.BASE_DIR) / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('respaldo:', compose)
        self.assertIn('/scripts/programar.sh', compose)
        self.assertIn('media_volume:/media:ro', compose)

    def test_respaldos_fuera_de_la_imagen(self):
        ignorados = (Path(settings.BASE_DIR) / '.dockerignore').read_text(encoding='utf-8')
        self.assertIn('respaldos/', ignorados)


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


class ServidoresDeCorreoDeLasPruebasTests(SimpleTestCase):
    """Cada EMAIL_BACKEND que nombran las pruebas tiene que existir. Si no existe, Django falla al importarlo
    y una prueba de "correo caído" pasaría por la razón equivocada (pasó al reorganizar las carpetas)."""

    def test_cada_backend_nombrado_se_puede_importar(self):
        import re
        from pathlib import Path
        from django.utils.module_loading import import_string
        carpeta = Path(__file__).resolve().parent.parent
        nombres = set()
        for archivo in carpeta.rglob('*.py'):
            nombres |= set(re.findall(r"EMAIL_BACKEND\s*=\s*['\"]([\w.]+)['\"]", archivo.read_text(encoding='utf-8')))
            nombres |= set(re.findall(r"^CORREO_FALLIDO\s*=\s*'([\w.]+)'", archivo.read_text(encoding='utf-8'), re.M))
        self.assertIn('gestion.tests.base.BackendCorreoFallido', nombres)
        for nombre in sorted(nombres):
            with self.subTest(backend=nombre):
                import_string(nombre)

