"""
Pruebas de los scripts de respaldo (historia 008).

Los scripts corren en el servicio "respaldo" (imagen postgres:16-alpine), no en Django.
Aquí solo se revisa que estén, que no tengan errores de sintaxis y que el servicio esté
declarado. La prueba de verdad es verificar.sh, que restaura un respaldo en una base
temporal y deja un informe como evidencia (ver respaldo/LEEME.md).
"""
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

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
