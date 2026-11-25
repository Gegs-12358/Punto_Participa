"""
Usuarios del sistema: documento de identidad obligatorio y normalizado, edición, auditoría y admin de Django.

Correr solo este archivo:
    python manage.py test gestion.tests.cuentas_y_permisos.tests_usuarios --noinput
"""
from datetime import timedelta

from gestion.models import Alumno, LogAuditoria, Rol, UsuarioSistema
from gestion.utils import buscar_alumno_por_documento

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ..base import BaseSistemaTestCase


URL = '/usuarios/guardar/'


_n = 0


def _alumno(rut):
    global _n
    _n += 1
    return Alumno.objects.create(
        rut=rut, nombres='Prueba', apellidos=f'Alumno{_n}',
        correo=f'alumno{_n}@duocuc.cl', carrera='Informática', jornada='Diurno',
    )


class NormalizacionDeDocumentosTests(TestCase):
    ENTRADAS = [
        ('20.001.550-9', '200015509'),
        ('12.345.678-k', '12345678K'),
        (' ab-123.456 ', 'AB123456'),
    ]

    def test_alumno_se_guarda_sin_puntos_ni_guion_y_en_mayusculas(self):
        for entrada, esperado in self.ENTRADAS:
            with self.subTest(entrada=entrada):
                a = _alumno(entrada)
                a.refresh_from_db()
                self.assertEqual(a.rut, esperado)

    def test_usuario_sistema_se_guarda_normalizado(self):
        rol = Rol.objects.create(nombre='Creador de Evento')
        for i, (entrada, esperado) in enumerate(self.ENTRADAS):
            with self.subTest(entrada=entrada):
                u = User.objects.create_user(username=f'norm{i}', password='clave123')
                us = UsuarioSistema.objects.create(
                    user=u, rol=rol, activo=True,
                    must_change_password=False, rut=entrada,
                )
                us.refresh_from_db()
                self.assertEqual(us.rut, esperado)

    def test_mismo_documento_en_otro_formato_es_duplicado(self):
        _alumno('20.001.550-9')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _alumno('200015509')

    def test_la_busqueda_sigue_encontrando_al_alumno(self):
        # Guardia: debe pasar antes y despues del cambio.
        a = _alumno('20.001.550-9')
        k = _alumno('12.345.678-k')
        p = _alumno('AB123456')
        for consulta in ['20.001.550-9', '20001550-9', '200015509', ' 20.001.550-9 ']:
            with self.subTest(consulta=consulta):
                self.assertEqual(buscar_alumno_por_documento(consulta).pk, a.pk)
        self.assertEqual(buscar_alumno_por_documento('12.345.678-k').pk, k.pk)
        self.assertEqual(buscar_alumno_por_documento('ab123456').pk, p.pk)


class BaseGuardarUsuario(TestCase):
    """Un Administrador con sesión iniciada y ayudas para llamar a Guardar usuario."""

    def setUp(self):
        cache.clear()
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_creador = Rol.objects.create(nombre='Creador de Evento')
        admin = User.objects.create_user(username='admin_rut', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=self.rol_admin, activo=True,
            must_change_password=False, rut='11111111K',
        )
        self.assertTrue(self.client.login(username='admin_rut', password='clave123'))

    def _usuario(self, username, rut):
        u = User.objects.create_user(username=username, password='clave123')
        return UsuarioSistema.objects.create(
            user=u, rol=self.rol_creador, activo=True,
            must_change_password=False, rut=rut,
        )

    def _post(self, us=None, username='nuevo', rut='', estado='on', **extra):
        datos = {
            'username': us.user.username if us else username,
            'nombre': 'Nombre Prueba',
            'email': 'prueba@duocuc.cl',
            'rol': self.rol_creador.pk,
            'estado': estado,
            'rut': rut,
        }
        if us:
            datos['user_id'] = us.pk
        datos.update(extra)
        return self.client.post(URL, datos)

class RutUsuarioTests(BaseGuardarUsuario):
    def test_crear_sin_rut_se_rechaza(self):
        r = self._post(username='nuevo1', rut='')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['success'])
        self.assertIn('obligatorio', r.json()['message'].lower())
        self.assertFalse(User.objects.filter(username='nuevo1').exists())
        self.assertFalse(UsuarioSistema.objects.filter(rut__startswith='99999999-').exists())

    def test_crear_con_rut_lo_guarda_normalizado(self):
        r = self._post(username='nuevo2', rut='12.345.678-k')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            UsuarioSistema.objects.get(user__username='nuevo2').rut, '12345678K')

    def test_editar_sin_rut_se_rechaza_y_conserva_el_existente(self):
        us = self._usuario('objetivo', '123456785')
        r = self._post(us, rut='')
        self.assertEqual(r.status_code, 400)
        us.refresh_from_db()
        self.assertEqual(us.rut, '123456785')

    def test_editar_con_el_mismo_rut_en_otro_formato_no_pregunta(self):
        us = self._usuario('objetivo', '123456785')
        r = self._post(us, rut='12.345.678-5')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        self.assertNotIn('confirmar_rut', r.json())
        us.refresh_from_db()
        self.assertEqual(us.rut, '123456785')

    def test_cambiar_el_rut_sin_confirmar_pide_confirmacion(self):
        us = self._usuario('objetivo', '123456785')
        r = self._post(us, rut='98765432K')
        self.assertFalse(r.json()['success'])
        self.assertTrue(r.json().get('confirmar_rut'))
        us.refresh_from_db()
        self.assertEqual(us.rut, '123456785')

    def test_cambiar_el_rut_confirmado_lo_cambia_y_deja_auditoria(self):
        us = self._usuario('objetivo', '123456785')
        r = self._post(us, rut='98.765.432-k', confirmar_rut='true')
        self.assertEqual(r.status_code, 200)
        us.refresh_from_db()
        self.assertEqual(us.rut, '98765432K')
        self.assertTrue(LogAuditoria.objects.filter(accion='Cambio de RUT').exists())

    def test_editar_con_rut_de_otro_usuario_da_mensaje_claro(self):
        self._usuario('primero', '123456785')
        segundo = self._usuario('segundo', '98765432K')
        r = self._post(segundo, rut='12.345.678-5', confirmar_rut='true')
        self.assertEqual(r.status_code, 400)
        self.assertIn('asignado', r.json()['message'].lower())

    def test_crear_con_rut_de_otro_usuario_da_mensaje_claro(self):
        self._usuario('primero', '123456785')
        r = self._post(username='nuevo3', rut='12.345.678-5')
        self.assertEqual(r.status_code, 400)
        self.assertIn('asignado', r.json()['message'].lower())

    def test_bloquear_reenviando_el_rut_guardado_sigue_funcionando(self):
        # Guardia: es lo que hace el boton de bloquear de usuarios.js.
        us = self._usuario('objetivo', '123456785')
        r = self._post(us, rut='123456785', estado='off')
        self.assertEqual(r.status_code, 200)
        us.refresh_from_db()
        self.assertFalse(us.activo)


class PantallaUsuariosTests(TestCase):
       def test_la_lista_de_usuarios_carga(self):
           rol = Rol.objects.create(nombre='Administrador')
           admin = User.objects.create_user(username='admin_pantalla', password='clave123')
           UsuarioSistema.objects.create(
               user=admin, rol=rol, activo=True,
               must_change_password=False, rut='11111111K',
           )
           self.assertTrue(self.client.login(username='admin_pantalla', password='clave123'))
           r = self.client.get('/usuarios/')
           self.assertEqual(r.status_code, 200)
           self.assertContains(r, 'admin_pantalla')


class AdminUsuarioSistemaTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Creador de Evento')
        User.objects.create_superuser('super_admin', 's@duocuc.cl', 'clave123')
        self.assertTrue(self.client.login(username='super_admin', password='clave123'))
        self.url = '/admin/gestion/usuariosistema/add/'

    def _post(self, username, rut):
        u = User.objects.create_user(username=username, password='clave123')
        return u, self.client.post(self.url, {
            'user': u.pk, 'rut': rut, 'rol': self.rol.pk, 'activo': 'on',
        })

    def test_admin_guarda_el_documento_normalizado(self):
        casos = [
            ('conrut', '12.345.678-5', '123456785'),
            ('pasaporte', 'ab-123.456', 'AB123456'),        # pasaporte con guion
            ('provisorio', '100.000.000-3', '1000000003'),  # RUN provisorio, sin módulo 11
        ]
        for username, escrito, guardado in casos:
            with self.subTest(documento=escrito):
                u, r = self._post(username, escrito)
                self.assertEqual(r.status_code, 302)
                self.assertEqual(UsuarioSistema.objects.get(user=u).rut, guardado)

    def test_admin_rechaza_documento_vacio_corto_o_de_otro_usuario(self):
        UsuarioSistema.objects.create(
            user=User.objects.create_user('primero', password='x'),
            rol=self.rol, rut='123456785')
        for username, escrito in (('sinrut', ''), ('corto', '123'), ('segundo', '12.345.678-5')):
            with self.subTest(documento=escrito):
                u, r = self._post(username, escrito)
                self.assertEqual(r.status_code, 200)  # vuelve al formulario con el error
                self.assertFalse(UsuarioSistema.objects.filter(user=u).exists())
                if not escrito:
                    self.assertContains(r, 'obligatorio')


class UsuariosAuditoriaYMiddlewareIntegralTests(BaseSistemaTestCase):
    def test_administrador_puede_crear_usuario_y_se_genera_log(self):
        self.login_as(self.admin)
        response = self.client.post(
            reverse("guardar_usuario"),
            {
                "username": "nuevo_integral",
                "nombre": "Nuevo Usuario",
                "email": "nuevo@example.com",
                "rol": self.rol_registrador.pk,
                "estado": "on",
                "rut": "12345678-5",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        usuario = User.objects.get(username="nuevo_integral")
        self.assertTrue(UsuarioSistema.objects.filter(user=usuario, rol=self.rol_registrador).exists())
        self.assertTrue(LogAuditoria.objects.filter(accion="Guardar usuario").exists())

    def test_middleware_obliga_cambio_de_contrasena(self):
        self.admin.usuariosistema.must_change_password = True
        self.admin.usuariosistema.save(update_fields=["must_change_password"])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("cambiar_contrasena"))

    def test_formulario_rechaza_archivo_que_no_es_imagen(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        imagen = SimpleUploadedFile(
            "banner.txt", b"contenido-de-prueba", content_type="text/plain"
        )
        datos = {
            "titulo": "Actividad con archivo",
            "descripcion": "Descripción",
            "tipo": "MASIVA",
            "lugar": "Sala 2",
            "fecha_inicio_fecha": futuro.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": futuro.strftime("%H:%M"),
            "fecha_fin_fecha": (futuro + timedelta(hours=1)).strftime("%Y-%m-%d"),
            "fecha_fin_hora": (futuro + timedelta(hours=1)).strftime("%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos, files={"imagen": imagen})
        self.assertFalse(form.is_valid())
        self.assertIn("imagen", form.errors)


class GuardarUsuarioRechazosTests(BaseGuardarUsuario):
    """Datos que Guardar usuario rechaza sin crear ni cambiar nada."""

    def _editar(self, us, **cambios):
        datos = {'user_id': us.pk, 'username': us.user.username, 'nombre': 'Nombre Prueba',
                 'email': 'prueba@duocuc.cl', 'rol': self.rol_creador.pk, 'estado': 'on', 'rut': us.rut}
        datos.update(cambios)
        return self.client.post(URL, datos)

    def test_identificadores_que_no_son_numeros(self):
        for campo, valor in (('user_id', 'abc'), ('rol', 'x')):
            with self.subTest(campo=campo):
                r = self._post(username='nuevo_ids', rut='12.345.678-5', **{campo: valor})
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json()['message'], 'Datos inválidos.')
        self.assertFalse(User.objects.filter(username='nuevo_ids').exists())

    def test_usuario_o_rol_que_no_existen(self):
        for extra in ({'user_id': 99999}, {'rol': 99999}):
            with self.subTest(**extra):
                r = self._post(username='nuevo_404', rut='12.345.678-5', **extra)
                self.assertEqual(r.status_code, 404)
                self.assertIn('no encontrado', r.json()['message'])
        self.assertFalse(User.objects.filter(username='nuevo_404').exists())

    def test_nombre_de_usuario_repetido_al_crear_y_al_editar(self):
        self._usuario('ocupado', '123456785')
        r = self._post(username='ocupado', rut='20.001.550-9')
        self.assertEqual((r.status_code, r.json()['message']), (400, 'Ese nombre de usuario ya está en uso'))
        otro = self._usuario('otro', '200015509')
        r = self._editar(otro, username='ocupado')
        self.assertEqual((r.status_code, r.json()['message']), (400, 'Ese nombre de usuario ya está en uso'))
        otro.user.refresh_from_db()
        self.assertEqual(otro.user.username, 'otro')

    def test_nombre_de_usuario_con_caracteres_no_permitidos_al_editar(self):
        us = self._usuario('valido', '123456785')
        r = self._editar(us, username='con espacio')
        self.assertEqual(r.status_code, 400)
        self.assertIn('solo puede contener', r.json()['message'])
        us.user.refresh_from_db()
        self.assertEqual(us.user.username, 'valido')

