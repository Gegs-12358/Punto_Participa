"""
Correos de invitación: enlace según el tipo de actividad, fallo de SMTP y límite por envío.

Correr solo este archivo:
    python manage.py test gestion.tests.invitaciones.tests_correo --noinput
"""
from datetime import timedelta

from gestion.models import Actividad, Alumno, Rol, UsuarioSistema

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import override_settings, TestCase
from django.urls import reverse
from django.utils import timezone

from ...models import NotificacionCorreo
from ..base import CORREO_FALLIDO, BaseSistemaTestCase, SilenciarRegistros


def crear_actividad(tipo, creador=None):
    ahora = timezone.now()
    cupos = ({'cupos_totales': 10, 'cupos_disponibles': 10} if tipo == 'TALLER'
             else {'cupos_totales': None, 'cupos_disponibles': None})
    return Actividad.objects.create(
        titulo=f'Actividad {tipo}', descripcion='desc', tipo=tipo, lugar='Sala',
        fecha_inicio=ahora + timedelta(days=2), fecha_fin=ahora + timedelta(days=2, hours=2),
        estado='ACTIVA', creado_por=creador, **cupos)


def crear_alumno():
    return Alumno.objects.create(
        rut='11111111K', tipo_documento='RUT', nombres='Ana', apellidos='Uno',
        correo='ana@example.com', carrera='Informática', jornada='Diurna')


class CorreoInvitacionTests(TestCase):
    def setUp(self):
        self.alumno = crear_alumno()

    def _html(self, actividad):
        return render_to_string('gestion/correos/invitacion.html', {
            'actividad': actividad, 'alumno': self.alumno, 'site_url': 'http://sitio.test'})

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EnvioInvitacionMasivaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        rol, _ = Rol.objects.get_or_create(nombre='Administrador')
        admin = User.objects.create_user(username='admin_correo', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=rol, activo=True, must_change_password=False, rut='11111111K')
        self.actividad = crear_actividad('MASIVA', admin)
        crear_alumno()
        self.assertTrue(self.client.login(username='admin_correo', password='clave123'))

    def test_el_correo_de_una_masiva_no_apunta_a_una_pagina_inexistente(self):
        self.client.post(reverse('enviar_invitaciones'), {'actividad_id': self.actividad.pk})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn('/taller/', str(mail.outbox[0].message()))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitacionesYMetodosHttpTests(BaseSistemaTestCase):
    def test_invitaciones_envia_correo_y_registra_notificacion(self):
        self.actividad.carreras.set([self.carrera])
        self.actividad.jornadas.set([self.jornada])
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("enviar_invitaciones"),
            {"actividad_id": self.actividad.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertTrue(datos["success"])
        self.assertEqual(datos["enviados"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            NotificacionCorreo.objects.filter(
                actividad=self.actividad, estado_envio="EXITO"
            ).count(),
            1,
        )

    def test_invitaciones_rechaza_get(self):
        self.client.force_login(self.creador)
        response = self.client.get(reverse("enviar_invitaciones"))
        self.assertEqual(response.status_code, 405)

    def test_previsualizacion_rechaza_actividad_de_otro_creador(self):
        self.client.force_login(self.creador)
        response = self.client.get(
            reverse("previsualizar_invitacion", args=[self.actividad_otro.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_endpoint_de_usuario_rechaza_get(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("guardar_usuario"))
        self.assertEqual(response.status_code, 405)

    def test_endpoint_de_usuario_rechaza_datos_obligatorios_faltantes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("guardar_usuario"),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])


@override_settings(EMAIL_BACKEND=CORREO_FALLIDO)
class CorreosFallidosExtremosTests(SilenciarRegistros, BaseSistemaTestCase):
    def test_fallo_smtp_se_registra_como_notificacion_fallida(self):
        self.actividad.carreras.set([self.carrera])
        self.actividad.jornadas.set([self.jornada])
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("enviar_invitaciones"),
            {"actividad_id": self.actividad.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertFalse(datos["success"])
        self.assertEqual(datos["enviados"], 0)
        self.assertEqual(datos["fallidos"], 1)
        self.assertEqual(
            NotificacionCorreo.objects.filter(
                actividad=self.actividad, estado_envio="FALLO"
            ).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 0)


class LimitesDeInvitacionesTests(SilenciarRegistros, BaseSistemaTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        MAX_INVITACIONES_POR_ENVIO=1,
    )
    def test_se_respeta_el_limite_de_invitaciones_por_envio(self):
        self.actividad.carreras.set([self.carrera, self.carrera_2])
        self.actividad.jornadas.set([self.jornada, self.jornada_2])
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("enviar_invitaciones"),
            {"actividad_id": self.actividad.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["enviados"], 1)
        self.assertEqual(
            NotificacionCorreo.objects.filter(actividad=self.actividad).count(),
            1,
        )
