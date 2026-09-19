"""
Tests para el proyecto Punto Participa.

Cobertura actual (post-refactor Opción B):
- utils.py: rut_limpio, rut_formateado, buscar_alumno_por_documento
- permissions.py: tiene_rol
- decorators.py: role_required (a través de una vista protegida real)
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Alumno, Rol, UsuarioSistema
from .permissions import tiene_rol
from .utils import buscar_alumno_por_documento, rut_formateado, rut_limpio


# ============================================================
# 1. HELPERS DE RUT (utils.py)
# ============================================================

class RutHelpersTestCase(TestCase):
    """Prueba rut_limpio() y rut_formateado() con distintos formatos."""

    def test_rut_limpio_con_puntos_y_guion(self):
        self.assertEqual(rut_limpio('20.001.550-9'), '200015509')

    def test_rut_limpio_sin_nada(self):
        self.assertEqual(rut_limpio('200015509'), '200015509')

    def test_rut_limpio_con_k_minuscula(self):
        self.assertEqual(rut_limpio('11.111.111-k'), '11111111K')

    def test_rut_limpio_vacio(self):
        self.assertEqual(rut_limpio(''), '')
        self.assertEqual(rut_limpio(None), '')

    def test_rut_formateado_desde_numero_plano(self):
        self.assertEqual(rut_formateado('200015509'), '20001550-9')

    def test_rut_formateado_desde_formato_con_puntos(self):
        self.assertEqual(rut_formateado('20.001.550-9'), '20001550-9')

    def test_rut_formateado_pasaporte_no_se_rompe(self):
        # Un pasaporte no tiene cuerpo numérico -> se devuelve limpio, sin guion forzado
        # ⚠️ PENDIENTE: este test falla actualmente porque rut_limpio() elimina
        # las letras del pasaporte (solo conserva dígitos y 'K'). Ver conversación
        # aparte antes de decidir si se corrige utils.py o se ajusta este test.
        resultado = rut_formateado('AB123456')
        self.assertEqual(resultado, 'AB123456')


# ============================================================
# 2. BÚSQUEDA DE ALUMNO POR DOCUMENTO (utils.py)
# ============================================================

class BuscarAlumnoPorDocumentoTestCase(TestCase):
    """Prueba que buscar_alumno_por_documento() encuentra al alumno
    sin importar el formato del RUT ingresado."""

    @classmethod
    def setUpTestData(cls):
        cls.alumno = Alumno.objects.create(
            rut='20001550-9',
            tipo_documento='RUT',
            nombres='Juan',
            apellidos='Pérez',
            correo='juan.perez@duocuc.cl',
            carrera='Ingeniería en Informática',
            jornada='Diurno',
        )

    def test_busca_con_formato_bbdd_exacto(self):
        alumno = buscar_alumno_por_documento('20001550-9')
        self.assertEqual(alumno, self.alumno)

    def test_busca_sin_guion(self):
        alumno = buscar_alumno_por_documento('200015509')
        self.assertEqual(alumno, self.alumno)

    def test_busca_con_puntos(self):
        alumno = buscar_alumno_por_documento('20.001.550-9')
        self.assertEqual(alumno, self.alumno)

    def test_no_encuentra_rut_inexistente(self):
        alumno = buscar_alumno_por_documento('99999999-9')
        self.assertIsNone(alumno)

    def test_valor_vacio_devuelve_none(self):
        self.assertIsNone(buscar_alumno_por_documento(''))
        self.assertIsNone(buscar_alumno_por_documento(None))


# ============================================================
# 3. PERMISOS (permissions.py)
# ============================================================

class PermissionsTestCase(TestCase):
    """Prueba tiene_rol() en distintos escenarios de usuario/perfil."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(nombre='Administrador')
        cls.rol_registrador = Rol.objects.create(nombre='Encargado de Registrar')

        cls.user_admin = User.objects.create_user(username='admin_test', password='x')
        UsuarioSistema.objects.create(
            user=cls.user_admin, rol=cls.rol_admin, activo=True
        )

        cls.user_inactivo = User.objects.create_user(username='inactivo_test', password='x')
        UsuarioSistema.objects.create(
            user=cls.user_inactivo, rol=cls.rol_admin, activo=False
        )

        cls.user_sin_perfil = User.objects.create_user(username='sin_perfil_test', password='x')

    def test_usuario_con_rol_correcto(self):
        self.assertTrue(tiene_rol(self.user_admin, ['Administrador']))

    def test_usuario_con_rol_incorrecto(self):
        self.assertFalse(tiene_rol(self.user_admin, ['Encargado de Registrar']))

    def test_usuario_inactivo_no_tiene_rol(self):
        self.assertFalse(tiene_rol(self.user_inactivo, ['Administrador']))

    def test_usuario_sin_perfil_no_tiene_rol(self):
        self.assertFalse(tiene_rol(self.user_sin_perfil, ['Administrador']))

    def test_usuario_anonimo_no_tiene_rol(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(tiene_rol(AnonymousUser(), ['Administrador']))


# ============================================================
# 4. DECORADOR role_required (a través de vistas reales)
# ============================================================

class RoleRequiredDecoratorTestCase(TestCase):
    """Prueba el decorador role_required usando la vista real 'usuarios'."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(nombre='Administrador')
        cls.rol_registrador = Rol.objects.create(nombre='Encargado de Registrar')

        cls.admin = User.objects.create_user(username='admin2_test', password='clave123')
        UsuarioSistema.objects.create(
            user=cls.admin, rol=cls.rol_admin, activo=True,
            must_change_password=False,
        )

        cls.registrador = User.objects.create_user(username='reg2_test', password='clave123')
        UsuarioSistema.objects.create(
            user=cls.registrador, rol=cls.rol_registrador, activo=True,
            must_change_password=False,
        )

    def test_sin_login_redirige_a_login_con_next(self):
        url = reverse('usuarios')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.assertIn('next=', response.url)

    def test_con_rol_correcto_accede(self):
        self.client.login(username='admin2_test', password='clave123')
        response = self.client.get(reverse('usuarios'))
        self.assertEqual(response.status_code, 200)

    def test_con_rol_incorrecto_no_accede(self):
        self.client.login(username='reg2_test', password='clave123')
        response = self.client.get(reverse('usuarios'))
        # No tiene permiso -> redirige (302), no 200 ni 500
        self.assertEqual(response.status_code, 302)