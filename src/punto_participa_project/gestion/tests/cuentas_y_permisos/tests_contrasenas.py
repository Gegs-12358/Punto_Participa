"""
Inicio y cierre de sesión, cambio obligatorio y recuperación de contraseña.

Correr solo este archivo:
    python manage.py test gestion.tests.cuentas_y_permisos.tests_contrasenas --noinput
"""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from ...models import Inscripcion, LogAuditoria, Rol, UsuarioSistema
from ..base import CORREO_FALLIDO, BaseSistemaTestCase, SilenciarRegistros


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SolicitarRecuperacionTests(SilenciarRegistros, BaseSistemaTestCase):
    """Prueba solicitar_recuperacion."""

    def test_get_muestra_formulario(self):
        response = self.client.get(reverse('recuperar_contrasena'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'formRecuperarContrasena')

    def test_post_sin_identificador_muestra_error(self):
        response = self.client.post(reverse('recuperar_contrasena'), {'identificador': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ingresa tu usuario o correo')

    def test_post_con_usuario_valido_envia_correo(self):
        # El admin del BaseSistemaTestCase tiene email
        response = self.client.post(
            reverse('recuperar_contrasena'),
            {'identificador': self.admin.username},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Recuperación de contraseña', mail.outbox[0].subject)
        self.assertTrue(
            LogAuditoria.objects.filter(
                accion='Solicitud de recuperación de contraseña'
            ).exists()
        )

    def test_post_con_email_valido_envia_correo(self):
        response = self.client.post(
            reverse('recuperar_contrasena'),
            {'identificador': self.admin.email},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_usuario_inexistente_o_inactivo_no_recibe_correo(self):
        # La respuesta es la misma en ambos casos, para no revelar qué cuentas existen.
        for identificador in ('no.existe@example.com', self.admin.username):
            with self.subTest(identificador=identificador):
                if identificador == self.admin.username:
                    self.admin.is_active = False
                    self.admin.save(update_fields=['is_active'])
                response = self.client.post(reverse('recuperar_contrasena'), {'identificador': identificador})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND=CORREO_FALLIDO)
    def test_post_con_error_smtp_no_rompe_la_vista(self):
        response = self.client.post(
            reverse('recuperar_contrasena'),
            {'identificador': self.admin.username},
        )
        self.assertEqual(response.status_code, 302)


class RestablecerContrasenaTests(SilenciarRegistros, BaseSistemaTestCase):
    """Prueba restablecer_contrasena."""

    def _generar_enlace(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        return uid, token

    def test_token_invalido_muestra_mensaje(self):
        response = self.client.get(
            reverse('restablecer_contrasena', args=['abc', 'def'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enlace inválido')

    def test_token_valido_muestra_formulario(self):
        uid, token = self._generar_enlace(self.admin)
        response = self.client.get(
            reverse('restablecer_contrasena', args=[uid, token])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nueva contraseña')

    def test_usuario_inactivo_no_puede_restablecer_contrasena(self):
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        uid, token = self._generar_enlace(self.admin)

        response = self.client.get(reverse('restablecer_contrasena', args=[uid, token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enlace inv')
        self.assertFalse(response.context['token_valido'])

    def test_post_con_contrasenas_distintas_muestra_error(self):
        uid, token = self._generar_enlace(self.admin)
        response = self.client.post(
            reverse('restablecer_contrasena', args=[uid, token]),
            {
                'nueva_contrasena': 'NuevaClave123!',
                'confirmar_contrasena': 'OtraClave123!',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.admin.check_password('ClaveSegura123!'))

    def test_post_valido_cambia_contrasena(self):
        uid, token = self._generar_enlace(self.admin)
        response = self.client.post(
            reverse('restablecer_contrasena', args=[uid, token]),
            {
                'nueva_contrasena': 'NuevaClave123!',
                'confirmar_contrasena': 'NuevaClave123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('NuevaClave123!'))
        self.assertTrue(
            LogAuditoria.objects.filter(
                accion='Restablecimiento de contraseña'
            ).exists()
        )

    def test_post_con_contrasena_debil_muestra_error(self):
        uid, token = self._generar_enlace(self.admin)
        response = self.client.post(
            reverse('restablecer_contrasena', args=[uid, token]),
            {
                'nueva_contrasena': '123',
                'confirmar_contrasena': '123',
            },
        )
        self.assertEqual(response.status_code, 200)


class ContraseñasYAutenticacionExtremaTests(SilenciarRegistros, BaseSistemaTestCase):
    def test_usuario_con_contrasena_temporal_es_redirigido_al_cambio(self):
        self.admin.usuariosistema.must_change_password = True
        self.admin.usuariosistema.save(update_fields=["must_change_password"])
        self.client.force_login(self.admin)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("cambiar_contrasena"))

    def test_cambio_contrasena_incorrecta_no_modifica_la_cuenta(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("cambiar_contrasena"),
            {
                "contrasena_actual": "incorrecta",
                "nueva_contrasena": "NuevaClave123!",
                "confirmar_contrasena": "NuevaClave123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(authenticate(username=self.admin.username, password="ClaveSegura123!"))
        self.assertFalse(authenticate(username=self.admin.username, password="NuevaClave123!"))

    def test_cambio_contrasena_con_confirmacion_distinta_no_modifica(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("cambiar_contrasena"),
            {
                "contrasena_actual": "ClaveSegura123!",
                "nueva_contrasena": "NuevaClave123!",
                "confirmar_contrasena": "OtraClave123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(authenticate(username=self.admin.username, password="ClaveSegura123!"))

    def test_cambio_contrasena_valido_actualiza_password_y_perfil(self):
        self.admin.usuariosistema.must_change_password = True
        self.admin.usuariosistema.save(update_fields=["must_change_password"])
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("cambiar_contrasena"),
            {
                "contrasena_actual": "ClaveSegura123!",
                "nueva_contrasena": "NuevaClave123!",
                "confirmar_contrasena": "NuevaClave123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.admin.refresh_from_db()
        self.admin.usuariosistema.refresh_from_db()
        self.assertTrue(self.admin.check_password("NuevaClave123!"))
        self.assertFalse(self.admin.usuariosistema.must_change_password)
        self.assertTrue(LogAuditoria.objects.filter(accion="Cambio de contraseña").exists())

    def test_login_con_usuario_inactivo_no_autentica(self):
        self.admin.usuariosistema.activo = False
        self.admin.usuariosistema.save(update_fields=["activo"])
        response = self.client.post(
            reverse("login"),
            {"username": self.admin.username, "password": "ClaveSegura123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_respeta_next_interno(self):
        response = self.client.post(
            reverse("login") + "?next=/escaneo/",
            {
                "username": self.admin.username,
                "password": "ClaveSegura123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/escaneo/")

    def test_login_ignora_next_externo(self):
        response = self.client.post(
            reverse("login") + "?next=https://sitio-malicioso.example/",
            {
                "username": self.admin.username,
                "password": "ClaveSegura123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_logout_cierra_la_sesion(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        protegida = self.client.get(reverse("reportes"))
        self.assertEqual(protegida.status_code, 302)


class AutenticacionYCorreoIntegralTests(BaseSistemaTestCase):
    def test_login_con_credenciales_validas(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.admin.username, "password": "ClaveSegura123!"},
        )
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_con_credenciales_invalidas_no_autentica(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.admin.username, "password": "incorrecta"},
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.status_code, 200)

    def test_previsualizacion_de_invitacion_devuelve_html(self):
        self.login_as(self.creador)
        response = self.client.get(
            reverse("previsualizar_invitacion", args=[self.actividad.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIn("html", response.json())

    def test_inscripcion_exitosa_envia_solo_la_confirmacion(self):
        """Desde la cancelación de inscripciones, se envía un correo: la confirmación al alumno."""
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "AB123456", "acepta_politica": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Inscripcion.objects.filter(
                actividad=self.actividad, alumno=self.alumno_pasaporte
            ).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alumno_pasaporte.correo])
        self.assertIn("Inscripción confirmada", mail.outbox[0].subject)


class InicioDeSesionRechazosTests(BaseSistemaTestCase):
    """Casos del inicio de sesión y del cambio de contraseña que no dejan entrar ni cambiar nada."""
    CLAVE = 'ClaveSegura123!'

    def setUp(self):
        cache.clear()   # el inicio de sesión tiene límite de intentos por IP

    def entrar(self, username, password=CLAVE):
        return self.client.post(reverse('login'), {'username': username, 'password': password})

    def test_usuario_o_clave_vacios(self):
        r = self.entrar('', '')
        self.assertContains(r, 'Debes ingresar usuario y contraseña.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cuenta_con_un_rol_que_no_es_del_sistema_no_entra(self):
        user = User.objects.create_user('rol_raro', password=self.CLAVE)
        UsuarioSistema.objects.create(user=user, rol=Rol.objects.create(nombre='Visitante'), activo=True,
                                      must_change_password=False, rut='123456785')
        self.assertContains(self.entrar('rol_raro'), 'La cuenta tiene un rol no válido.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_con_clave_temporal_va_directo_a_cambiarla(self):
        UsuarioSistema.objects.filter(user=self.creador).update(must_change_password=True)
        self.assertRedirects(self.entrar(self.creador.username), reverse('cambiar_contrasena'),
                             fetch_redirect_response=False)

    def test_cambiar_clave_sin_perfil_o_con_la_cuenta_desactivada(self):
        sin_perfil = User.objects.create_user('sin_perfil_clave', password=self.CLAVE)
        UsuarioSistema.objects.filter(user=self.registrador).update(activo=False)
        for usuario, mensaje in ((sin_perfil, 'no tiene un perfil válido'), (self.registrador, 'está desactivada')):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                r = self.client.get(reverse('cambiar_contrasena'), follow=True)
                self.assertRedirects(r, reverse('login'))
                self.assertContains(r, mensaje)

    def test_nueva_clave_vacia_o_igual_a_la_actual(self):
        self.client.force_login(self.creador)
        for nueva, mensaje in (('', 'Debes ingresar una nueva contraseña.'),
                               (self.CLAVE, 'debe ser diferente de la actual')):
            with self.subTest(nueva=nueva or 'vacía'):
                r = self.client.post(reverse('cambiar_contrasena'), {
                    'contrasena_actual': self.CLAVE, 'nueva_contrasena': nueva, 'confirmar_contrasena': nueva})
                self.assertContains(r, mensaje)
        self.creador.refresh_from_db()
        self.assertTrue(self.creador.check_password(self.CLAVE))

