"""
Pruebas del paquete P0 (arreglos técnicos):
- Color de cada escuela en el catálogo (antes fijo en el código por nombre).
- Configuración leída desde .env (remitente, modo de envío y seguridad).
- requirements.txt y entrypoint.sh legibles en cualquier sistema.
"""
import importlib
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from punto_participa.settings import _lista

from .models import Escuela, LogAuditoria
from .tests_integrales import BaseSistemaTestCase
from .views import COLOR_POR_ESCUELA, _colores_por_carrera, color_para_escuela, colores_escuelas

INFORMATICA = 'Escuela de Informática y Telecomunicaciones'
URL_ESCUELAS = reverse('catalogo_escuelas')
migracion_color = importlib.import_module('gestion.migrations.0029_escuela_color')


# ============================================================
# COLOR DE LA ESCUELA
# ============================================================

class ColorEscuelaTests(TestCase):
    def test_usa_el_color_del_catalogo_antes_que_el_oficial(self):
        Escuela.objects.create(nombre=INFORMATICA, color='#123456')
        self.assertEqual(color_para_escuela(INFORMATICA), '#123456')

    def test_sin_color_en_catalogo_usa_el_oficial_y_si_no_gris(self):
        Escuela.objects.create(nombre=INFORMATICA)
        self.assertEqual(color_para_escuela(INFORMATICA), COLOR_POR_ESCUELA[INFORMATICA])
        Escuela.objects.create(nombre='Escuela Nueva')
        self.assertEqual(color_para_escuela('Escuela Nueva'), '#666666')
        self.assertEqual(color_para_escuela(None), '#666666')

    def test_mapa_precalculado_evita_consultas_en_ciclos(self):
        Escuela.objects.create(nombre='Escuela A', color='#AAAAAA')
        mapa = colores_escuelas()
        with self.assertNumQueries(0):
            self.assertEqual(color_para_escuela('Escuela A', mapa), '#AAAAAA')

    def test_colores_por_carrera_hace_una_sola_consulta(self):
        Escuela.objects.create(nombre='Escuela A', color='#AAAAAA')

        class C:
            escuela = 'Escuela A'
        cache = {'carrera a': C(), 'carrera b': C()}
        items = [{'alumno__carrera': 'Carrera A'}, {'alumno__carrera': 'Carrera B'},
                 {'alumno__carrera': None}]
        with self.assertNumQueries(1):
            self.assertEqual(_colores_por_carrera(items, cache), ['#AAAAAA', '#AAAAAA', '#666666'])

    def test_el_color_solo_acepta_formato_hexadecimal(self):
        for malo in ('red', '#12345', '#GGGGGG', 'red;}x'):
            with self.subTest(color=malo):
                with self.assertRaises(ValidationError):
                    Escuela(nombre='X', color=malo).full_clean()
        Escuela(nombre='X', color='#a1B2c3').full_clean()

    def test_la_migracion_pone_los_colores_oficiales(self):
        Escuela.objects.create(nombre=INFORMATICA)
        Escuela.objects.create(nombre='Escuela desconocida')
        Escuela.objects.create(nombre='Escuela de Diseño', color='#000000')   # ya elegido: no se toca
        migracion_color.poner_colores(django_apps, None)
        colores = dict(Escuela.objects.values_list('nombre', 'color'))
        self.assertEqual(colores[INFORMATICA], '#307FE2')
        self.assertEqual(colores['Escuela desconocida'], '')
        self.assertEqual(colores['Escuela de Diseño'], '#000000')


class CatalogoColorEscuelaTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)
        self.escuela = Escuela.objects.create(nombre=INFORMATICA, color='#307FE2')

    def test_agregar_con_color(self):
        self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'Escuela de Salud', 'color': '#5bc2e7'})
        self.assertEqual(Escuela.objects.get(nombre='Escuela de Salud').color, '#5BC2E7')

    def test_color_invalido_se_ignora(self):
        self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'Escuela de Salud', 'color': 'javascript:x'})
        self.assertEqual(Escuela.objects.get(nombre='Escuela de Salud').color, '')

    def test_cambiar_solo_el_color(self):
        self.client.post(URL_ESCUELAS, {'accion': 'renombrar', 'escuela_id': self.escuela.pk,
                                        'nombre': INFORMATICA, 'color': '#000000'})
        self.escuela.refresh_from_db()
        self.assertEqual(self.escuela.color, '#000000')
        log = LogAuditoria.objects.get(accion='Cambiar color de escuela')
        self.assertEqual(log.cambios_json['color'], {'antes': '#307FE2', 'despues': '#000000'})

    def test_renombrar_y_cambiar_color_a_la_vez(self):
        self.client.post(URL_ESCUELAS, {'accion': 'renombrar', 'escuela_id': self.escuela.pk,
                                        'nombre': 'Escuela de Informática', 'color': '#111111'})
        self.escuela.refresh_from_db()
        self.carrera.refresh_from_db()
        self.assertEqual((self.escuela.nombre, self.escuela.color), ('Escuela de Informática', '#111111'))
        self.assertEqual(self.carrera.escuela, 'Escuela de Informática')
        # El color sigue a la escuela aunque cambie el nombre
        self.assertEqual(color_para_escuela('Escuela de Informática'), '#111111')

    def test_la_pantalla_muestra_el_color_y_sugiere_uno_libre(self):
        resp = self.client.get(URL_ESCUELAS)
        self.assertContains(resp, 'background: #307FE2')
        self.assertNotEqual(resp.context['color_sugerido'], '#307FE2')


# ============================================================
# CONFIGURACIÓN DESDE .env
# ============================================================

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
