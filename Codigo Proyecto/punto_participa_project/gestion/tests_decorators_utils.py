"""
Tests específicos para decorators.py y utils.py.

Estos tests suben la cobertura de:
- gestion/decorators.py
- gestion/utils.py

Ejecutar con:
    python manage.py test gestion.tests_decorators_utils -v 2
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .decorators import ajax_required, method_required, role_required
from .models import Alumno, Carrera, Jornada, Rol, UsuarioSistema
from .utils import (
    buscar_alumno_por_documento,
    extraer_rut_de_carnet,
    formatear_rut,
    normalizar_documento,
    normalizar_rut,
    paginar,
    rut_formateado,
    rut_limpio,
    validar_documento,
    validar_rut,
    validar_rut_extranjero,
)


# ============================================================
# 1. DECORADORES
# ============================================================

class AjaxRequiredDecoratorTests(TestCase):
    """Prueba el decorador @ajax_required."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_acepta_peticion_ajax_por_header(self):
        @ajax_required
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get(
            '/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        response = vista(request)
        self.assertEqual(response.status_code, 200)

    def test_acepta_peticion_con_accept_json(self):
        @ajax_required
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get('/test/', HTTP_ACCEPT='application/json')
        response = vista(request)
        self.assertEqual(response.status_code, 200)

    def test_rechaza_peticion_no_ajax(self):
        @ajax_required
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get('/test/')
        response = vista(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('solo acepta AJAX', response.content.decode())


class MethodRequiredDecoratorTests(TestCase):
    """Prueba el decorador @method_required."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_acepta_metodo_permitido(self):
        @method_required('POST')
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.post('/test/')
        response = vista(request)
        self.assertEqual(response.status_code, 200)

    def test_rechaza_metodo_no_permitido(self):
        @method_required('POST')
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get('/test/')
        response = vista(request)
        self.assertEqual(response.status_code, 405)

    def test_acepta_multiples_metodos(self):
        @method_required('POST', 'PUT')
        def vista(request):
            return JsonResponse({'ok': True})

        request_post = self.factory.post('/test/')
        request_put = self.factory.put('/test/')
        self.assertEqual(vista(request_post).status_code, 200)
        self.assertEqual(vista(request_put).status_code, 200)


class RoleRequiredDecoratorAvanzadoTests(TestCase):
    """Prueba las ramas del decorador @role_required que faltaban."""

    def setUp(self):
        self.factory = RequestFactory()
        self.rol = Rol.objects.create(nombre='Administrador')
        self.user = User.objects.create_user(
            username='test_role', password='x'
        )
        UsuarioSistema.objects.create(
            user=self.user, rol=self.rol, activo=True,
            must_change_password=False,
        )

    def test_anonimo_con_json_response_devuelve_401(self):
        @role_required('Administrador', json_response=True)
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get('/test/')
        request.user = AnonymousUser()
        response = vista(request)
        self.assertEqual(response.status_code, 401)

        # Parsear el JSON en lugar de comparar el string crudo
        import json
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('iniciar sesión', data['message'])

    def test_anonimo_sin_json_redirige_a_login_con_next(self):
        @role_required('Administrador')
        def vista(request):
            return HttpResponse('ok')

        request = self.factory.get('/test/')
        request.user = AnonymousUser()
        response = vista(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=/test/', response.url)

    def test_usuario_sin_rol_con_json_devuelve_403(self):
        user_sin_rol = User.objects.create_user(username='sin_rol', password='x')
        UsuarioSistema.objects.create(
            user=user_sin_rol,
            rol=Rol.objects.create(nombre='OtroRol'),
            activo=True,
            must_change_password=False,
        )

        @role_required('Administrador', json_response=True)
        def vista(request):
            return JsonResponse({'ok': True})

        request = self.factory.get('/test/')
        request.user = user_sin_rol
        response = vista(request)
        self.assertEqual(response.status_code, 403)

    def test_usuario_sin_rol_sin_json_redirige(self):
        """Usa Client en lugar de RequestFactory para tener middleware."""
        from django.test import Client

        user_sin_rol = User.objects.create_user(username='sin_rol2', password='x')
        UsuarioSistema.objects.create(
            user=user_sin_rol,
            rol=Rol.objects.create(nombre='OtroRol2'),
            activo=True,
            must_change_password=False,
        )

        # Usamos una vista REAL con el decorador para que el middleware
        # de mensajes esté disponible.
        client = Client()
        client.force_login(user_sin_rol)

        # La vista 'usuarios' está protegida con @role_required('Administrador')
        response = client.get(reverse('usuarios'))
        self.assertEqual(response.status_code, 302)


# ============================================================
# 2. UTILS: NORMALIZACIÓN
# ============================================================

class NormalizacionTests(TestCase):
    """Prueba rut_limpio, normalizar_rut y normalizar_documento."""

    def test_rut_limpio_con_puntos(self):
        self.assertEqual(rut_limpio('12.345.678-9'), '123456789')

    def test_rut_limpio_con_espacios(self):
        self.assertEqual(rut_limpio('  12.345.678-9  '), '123456789')

    def test_rut_limpio_con_k_minuscula(self):
        self.assertEqual(rut_limpio('12.345.678-k'), '12345678K')

    def test_rut_limpio_con_pasaporte(self):
        self.assertEqual(rut_limpio('AB-123456'), 'AB123456')

    def test_normalizar_rut_es_alias_de_rut_limpio(self):
        self.assertEqual(normalizar_rut('12.345.678-9'), rut_limpio('12.345.678-9'))

    def test_normalizar_documento_con_letras(self):
        self.assertEqual(normalizar_documento('ab-123.456'), 'AB123456')

    def test_normalizar_documento_vacio(self):
        self.assertEqual(normalizar_documento(''), '')
        self.assertEqual(normalizar_documento(None), '')


# ============================================================
# 3. UTILS: VALIDACIÓN DE RUT
# ============================================================

class ValidarRutTests(TestCase):
    """Prueba validar_rut, validar_rut_extranjero y validar_documento."""

    def test_rut_valido_sin_puntos(self):
        self.assertTrue(validar_rut('200015509'))

    def test_rut_valido_con_puntos(self):
        self.assertTrue(validar_rut('20.001.550-9'))

    def test_rut_invalido_dv_incorrecto(self):
        self.assertFalse(validar_rut('12345678-0'))

    def test_rut_muy_corto(self):
        self.assertFalse(validar_rut('123-4'))

    def test_rut_muy_largo(self):
        self.assertFalse(validar_rut('1234567890-1'))

    def test_rut_con_cuerpo_no_numerico(self):
        self.assertFalse(validar_rut('AB123456'))

    def test_rut_vacio(self):
        self.assertFalse(validar_rut(''))

    def test_rut_extranjero_valido(self):
        self.assertTrue(validar_rut_extranjero('20001550-9'))

    def test_rut_extranjero_con_k(self):
        self.assertTrue(validar_rut_extranjero('12345678-K'))

    def test_rut_extranjero_con_cuerpo_no_numerico(self):
        self.assertFalse(validar_rut_extranjero('AB123456'))

    def test_rut_extranjero_corto(self):
        self.assertFalse(validar_rut_extranjero('123-4'))

    def test_validar_documento_rut(self):
        self.assertTrue(validar_documento('20.001.550-9', 'RUT'))
        self.assertFalse(validar_documento('12345678-0', 'RUT'))

    def test_validar_documento_run_provisorio(self):
        self.assertTrue(validar_documento('20001550-9', 'RUN_PROVISORIO'))

    def test_validar_documento_cedula_extranjero(self):
        self.assertTrue(validar_documento('20001550-9', 'CEDULA_EXTRANJERO'))

    def test_validar_documento_pasaporte_valido(self):
        self.assertTrue(validar_documento('AB123456', 'PASAPORTE'))

    def test_validar_documento_pasaporte_corto(self):
        self.assertFalse(validar_documento('AB1', 'PASAPORTE'))

    def test_validar_documento_tipo_desconocido(self):
        self.assertTrue(validar_documento('20001550-9', 'OTRO'))

    def test_validar_documento_vacio(self):
        self.assertFalse(validar_documento('', 'RUT'))


# ============================================================
# 4. UTILS: FORMATEO
# ============================================================

class FormatearRutTests(TestCase):
    """Prueba rut_formateado y formatear_rut."""

    def test_rut_formateado_sin_puntos(self):
        self.assertEqual(rut_formateado('200015509'), '20001550-9')

    def test_rut_formateado_con_puntos(self):
        self.assertEqual(rut_formateado('20.001.550-9'), '20001550-9')

    def test_rut_formateado_pasaporte(self):
        self.assertEqual(rut_formateado('AB123456'), 'AB123456')

    def test_rut_formateado_muy_corto(self):
        self.assertEqual(rut_formateado('A'), 'A')

    def test_formatear_rut_con_puntos(self):
        self.assertEqual(formatear_rut('123456789'), '12.345.678-9')

    def test_formatear_rut_pasaporte(self):
        self.assertEqual(formatear_rut('AB123456'), 'AB123456')

    def test_formatear_rut_muy_corto(self):
        self.assertEqual(formatear_rut('A'), 'A')

    def test_formatear_rut_con_k(self):
        self.assertEqual(formatear_rut('12345678K'), '12.345.678-K')


# ============================================================
# 5. UTILS: EXTRACCIÓN DE QR
# ============================================================

class ExtraerRutDeCarnetTests(TestCase):
    """Prueba extraer_rut_de_carnet con URLs de QR."""

    def test_extrae_rut_de_url_qr(self):
        url = 'https://portal.sidiv.registrocivil.cl/consulta?RUN=12345678-9'
        self.assertEqual(extraer_rut_de_carnet(url), '123456789')

    def test_extrae_rut_de_url_qr_con_k(self):
        url = 'https://portal.sidiv.registrocivil.cl/consulta?RUN=12345678-K'
        self.assertEqual(extraer_rut_de_carnet(url), '12345678K')

    def test_extrae_rut_de_texto_plano(self):
        self.assertEqual(extraer_rut_de_carnet('12345678-9'), '123456789')

    def test_extrae_rut_con_parametro_run_y_ampersand(self):
        url = 'https://x.cl?foo=bar&RUN=12345678-9&baz=qux'
        self.assertEqual(extraer_rut_de_carnet(url), '123456789')

    def test_valor_vacio(self):
        self.assertEqual(extraer_rut_de_carnet(''), '')
        self.assertEqual(extraer_rut_de_carnet(None), '')

    def test_rut_muy_largo_se_trunca(self):
        self.assertEqual(extraer_rut_de_carnet('123456789012345'), '123456789')


# ============================================================
# 6. UTILS: BÚSQUEDA DE ALUMNOS
# ============================================================

class BuscarAlumnoPorDocumentoTests(TestCase):
    """Prueba buscar_alumno_por_documento con distintas variantes."""

    @classmethod
    def setUpTestData(cls):
        cls.alumno = Alumno.objects.create(
            rut='20001550-9',
            tipo_documento='RUT',
            nombres='Juan',
            apellidos='Pérez',
            correo='juan@example.com',
            carrera='Ingeniería',
            jornada='Diurna',
        )
        cls.alumno_pasaporte = Alumno.objects.create(
            rut='AB123456',
            tipo_documento='PASAPORTE',
            nombres='Ana',
            apellidos='Gómez',
            correo='ana@example.com',
            carrera='Diseño',
            jornada='Vespertina',
        )

    def test_busca_con_formato_bbdd(self):
        self.assertEqual(
            buscar_alumno_por_documento('20001550-9'),
            self.alumno
        )

    def test_busca_sin_guion(self):
        self.assertEqual(
            buscar_alumno_por_documento('200015509'),
            self.alumno
        )

    def test_busca_con_puntos(self):
        self.assertEqual(
            buscar_alumno_por_documento('20.001.550-9'),
            self.alumno
        )

    def test_busca_con_espacios(self):
        self.assertEqual(
            buscar_alumno_por_documento('  20001550-9  '),
            self.alumno
        )

    def test_busca_pasaporte(self):
        self.assertEqual(
            buscar_alumno_por_documento('AB123456'),
            self.alumno_pasaporte
        )

    def test_busca_pasaporte_con_guion(self):
        self.assertEqual(
            buscar_alumno_por_documento('AB-123456'),
            self.alumno_pasaporte
        )

    def test_no_encuentra_rut_inexistente(self):
        self.assertIsNone(buscar_alumno_por_documento('99999999-9'))

    def test_valor_vacio_devuelve_none(self):
        self.assertIsNone(buscar_alumno_por_documento(''))
        self.assertIsNone(buscar_alumno_por_documento(None))
        self.assertIsNone(buscar_alumno_por_documento('   '))

    def test_rut_numerico_sin_guion(self):
        self.assertEqual(
            buscar_alumno_por_documento('200015509'),
            self.alumno
        )


# ============================================================
# 7. UTILS: PAGINACIÓN
# ============================================================

class PaginarTests(TestCase):
    """Prueba la función paginar."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_pagina_por_defecto(self):
        from django.core.paginator import Paginator
        from django.http import QueryDict

        items = list(range(50))
        request = self.factory.get('/test/')
        page = paginar(request, items)
        self.assertEqual(page.number, 1)
        self.assertEqual(len(page.object_list), 15)

    def test_pagina_especifica(self):
        items = list(range(50))
        request = self.factory.get('/test/?page=2')
        page = paginar(request, items)
        self.assertEqual(page.number, 2)

    def test_param_personalizado(self):
        items = list(range(50))
        request = self.factory.get('/test/?page_insc=3')
        page = paginar(request, items, param='page_insc')
        self.assertEqual(page.number, 3)

    def test_por_pagina_personalizado(self):
        items = list(range(50))
        request = self.factory.get('/test/')
        page = paginar(request, items, por_pagina=5)
        self.assertEqual(len(page.object_list), 5)

    def test_pagina_fuera_de_rango_devuelve_ultima(self):
        items = list(range(50))
        request = self.factory.get('/test/?page=999')
        page = paginar(request, items)
        self.assertEqual(page.number, page.paginator.num_pages)