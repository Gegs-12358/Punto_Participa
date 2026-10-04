"""
Pruebas de integración: entradas hostiles por los puntos de entrada reales.

Se guarda como gestion/tests_caracteres.py (Django lo descubre solo).
Verifica que ninguna entrada produce un 500 y que los nombres legítimos
con apóstrofes se guardan tal cual.
"""

import itertools
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import views
from .models import Actividad, Alumno, Inscripcion, Rol, UsuarioSistema
from .tests import ENTRADAS_HOSTILES

EXTRAS = [
    "a" * 500,
    "9" * 40,
    "\x00",
    "' OR '1'='1",
    "RUN=\x00",
    "https://portal.sidiv.registrocivil.cl/docstatus?RUN=\x00&type=CEDULA",
]
ENTRADAS = ENTRADAS_HOSTILES + EXTRAS

# Ruta vista en los logs ("Internal Server Error: /escaneo/")
ESCANEO_URL = '/escaneo/'


_contador_rut = itertools.count(1)


def _rut_unico():
    """RUT distinto en cada llamada (evita choques de unique entre subtests)."""
    return f'9{next(_contador_rut):07d}-1'


def _usuario_con_rol(username, nombre_rol):
    rol = Rol.objects.create(nombre=nombre_rol)
    user = User.objects.create_user(username=username, password='clave123')
    UsuarioSistema.objects.create(
        user=user, rol=rol, activo=True, must_change_password=False,
    )
    return user, rol


# ============================================================
# guardar_usuario
# ============================================================

class GuardarUsuarioHostilTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin, cls.rol = _usuario_con_rol('admin_h', 'Administrador')

    def setUp(self):
        self.client.login(username='admin_h', password='clave123')
        self.url = reverse(views.guardar_usuario)

    def _assert_controlada(self, r):
        """Respuesta JSON, sin 5xx y sin redirección/permiso denegado."""
        self.assertLess(r.status_code, 500)
        self.assertNotIn(r.status_code, (301, 302, 403))
        self.assertEqual(r['Content-Type'], 'application/json')

    def test_ningun_campo_hostil_devuelve_500(self):
        for i, texto in enumerate(ENTRADAS):
            for campo in ('username', 'nombre', 'email', 'rut'):
                with self.subTest(campo=campo, texto=repr(texto)[:50]):
                    datos = {
                        'username': f'u{campo}{i}',
                        'nombre': 'Nombre Valido',
                        'email': f'{campo}{i}@duocuc.cl',
                        'rol': self.rol.pk,
                        'estado': 'on',
                        'rut': _rut_unico(),
                    }
                    datos[campo] = texto
                    r = self.client.post(self.url, datos)
                    self._assert_controlada(r)

    def test_ids_no_numericos_no_devuelven_500(self):
        for malo in ('abc', '1; DROP TABLE x', '\x00', '9' * 30, '²'):
            with self.subTest(malo=repr(malo)):
                r = self.client.post(self.url, {
                    'user_id': malo, 'username': 'x', 'nombre': 'X',
                    'email': 'x@duocuc.cl', 'rol': self.rol.pk, 'estado': 'on',
                })
                self._assert_controlada(r)
                r = self.client.post(self.url, {
                    'username': 'y', 'nombre': 'Y',
                    'email': 'y@duocuc.cl', 'rol': malo, 'estado': 'on',
                })
                self._assert_controlada(r)

    def test_nombre_con_apostrofe_se_guarda_tal_cual(self):
        r = self.client.post(self.url, {
            'username': 'bohiggins', 'nombre': 'Bernardo O`higgins',
            'email': 'bohiggins@duocuc.cl', 'rol': self.rol.pk, 'estado': 'on',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.get(username='bohiggins').first_name,
                         'Bernardo O`higgins')

    def test_rut_duplicado_no_deja_usuario_huerfano(self):
        datos = {'nombre': 'A', 'rol': self.rol.pk, 'estado': 'on',
                 'rut': '12345678-5'}
        r1 = self.client.post(self.url, {**datos, 'username': 'dup1',
                                         'email': 'dup1@duocuc.cl'})
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(self.url, {**datos, 'username': 'dup2',
                                         'email': 'dup2@duocuc.cl'})
        self.assertEqual(r2.status_code, 409)
        self.assertFalse(User.objects.filter(username='dup2').exists())


# ============================================================
# inscripcion_taller (vista pública)
# ============================================================

class InscripcionPublicaHostilTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.creador = User.objects.create_user(username='creador_h', password='x')
        ahora = timezone.now()
        # Si Actividad exige otros campos, usa el helper que ya tengas
        # en tests_extremos.py en lugar de este create().
        cls.taller = Actividad.objects.create(
            titulo='Taller de prueba', descripcion='desc', tipo='TALLER',
            lugar='Sala 1',
            fecha_inicio=ahora + timedelta(days=1),
            fecha_fin=ahora + timedelta(days=1, hours=2),
            estado='ACTIVA', cupos_totales=10, cupos_disponibles=10,
            creado_por=cls.creador,
        )

    def setUp(self):
        self.url = reverse(views.inscripcion_taller, args=[self.taller.pk])

    def test_rut_hostil_no_devuelve_500_ni_refleja_html(self):
        for texto in ENTRADAS:
            with self.subTest(texto=repr(texto)[:50]):
                cache.clear()  # por si la vista tiene límite de intentos
                r = self.client.post(self.url, {'rut': texto})
                self.assertEqual(r.status_code, 200)
                self.assertNotIn('<script>alert(1)</script>', r.content.decode())

    def test_alumno_con_apostrofe_se_inscribe(self):
        Alumno.objects.create(
            rut='20001550-9', nombres='Bernardo', apellidos='O`higgins',
            correo='b@duocuc.cl', carrera='Informática', jornada='Diurno',
        )
        r = self.client.post(self.url, {'rut': '20.001.550-9'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Inscripcion.objects.filter(actividad=self.taller).exists())


# ============================================================
# Escáner
# ============================================================

class EscanerHostilTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user, _ = _usuario_con_rol('reg_h', 'Encargado de Registrar')

    def setUp(self):
        self.client.login(username='reg_h', password='clave123')
        sesion = self.client.session
        sesion['actividad_escaneo_id'] = 999999  # llega hasta la búsqueda del alumno
        sesion.save()

    def test_documento_hostil_devuelve_json_sin_500(self):
        for texto in ENTRADAS:
            with self.subTest(texto=repr(texto)[:50]):
                cache.clear()
                r = self.client.post(ESCANEO_URL, {'rut': texto})
                self.assertLess(r.status_code, 500)
                self.assertNotIn(r.status_code, (301, 302, 403))
                self.assertEqual(r['Content-Type'], 'application/json')