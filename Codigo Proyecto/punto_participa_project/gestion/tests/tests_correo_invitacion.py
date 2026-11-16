# El correo de invitacion solo ofrece inscripcion en los talleres: las masivas no tienen
# pagina /taller/<n>/ (da 404), asi que su correo no debe apuntar alli.
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gestion.models import Actividad, Alumno, Rol, UsuarioSistema


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
        return render_to_string('gestion/email_invitacion.html', {
            'actividad': actividad, 'alumno': self.alumno, 'site_url': 'http://sitio.test'})

    def test_un_taller_lleva_el_enlace_de_inscripcion(self):
        actividad = crear_actividad('TALLER')
        html = self._html(actividad)
        self.assertIn(f'http://sitio.test/taller/{actividad.pk}/', html)
        self.assertIn('Inscribirme', html)

    def test_una_masiva_no_lleva_enlace_de_inscripcion(self):
        html = self._html(crear_actividad('MASIVA'))
        self.assertNotIn('/taller/', html)
        self.assertNotIn('Inscribirme', html)
        self.assertIn('no requiere inscripción', html)


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
