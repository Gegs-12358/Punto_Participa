from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase

from gestion.models import Alumno, LogAuditoria, Rol, UsuarioSistema
from gestion.utils import buscar_alumno_por_documento

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


class RutUsuarioTests(TestCase):
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