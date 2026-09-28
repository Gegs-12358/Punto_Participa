"""
Tests para las vistas críticas de views.py.

Cubre los flujos de seguridad y operación:
- Recuperación de contraseña
- Restablecer contraseña
- Parseo de RUT en escáner
- Registro de asistencia (POST)
- Eliminar actividad
- Colores de escuela

Ejecutar con:
    python manage.py test gestion.tests_views_criticas -v 2
"""

import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Actividad, Alumno, Asistencia, Carrera, Inscripcion, Jornada, LogAuditoria, Rol, UsuarioSistema
from .tests_integrales import BaseSistemaTestCase
from .views import color_para_escuela, _parse_rut_escaneo


# ============================================================
# 1. RECUPERACIÓN DE CONTRASEÑA
# ============================================================

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SolicitarRecuperacionTests(BaseSistemaTestCase):
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

    def test_post_con_usuario_inexistente_no_envia_correo(self):
        response = self.client.post(
            reverse('recuperar_contrasena'),
            {'identificador': 'no.existe@example.com'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="gestion.tests_extremos.BackendCorreoFallido")
    def test_post_con_error_smtp_no_rompe_la_vista(self):
        response = self.client.post(
            reverse('recuperar_contrasena'),
            {'identificador': self.admin.username},
        )
        self.assertEqual(response.status_code, 302)


# ============================================================
# 2. RESTABLECER CONTRASEÑA
# ============================================================

class RestablecerContrasenaTests(BaseSistemaTestCase):
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


# ============================================================
# 3. PARSEO DE RUT EN ESCÁNER
# ============================================================

class ParseRutEscaneoTests(TestCase):
    """Prueba _parse_rut_escaneo."""

    def test_rut_normal(self):
        metodo, rut = _parse_rut_escaneo('20001550-9')
        self.assertEqual(metodo, 'CODIGO')
        self.assertEqual(rut, '20001550-9')

    def test_rut_con_qr_url(self):
        url = 'https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9'
        metodo, rut = _parse_rut_escaneo(url)
        self.assertEqual(metodo, 'QR')
        self.assertEqual(rut, '20001550-9')

    def test_rut_con_comilla(self):
        metodo, rut = _parse_rut_escaneo("'20001550-9")
        self.assertEqual(metodo, 'CODIGO')
        self.assertEqual(rut, '20001550-9')

    def test_rut_solo_numeros(self):
        metodo, rut = _parse_rut_escaneo('200015509')
        self.assertEqual(metodo, 'RUT')
        self.assertEqual(rut, '200015509')

    def test_rut_con_qr_sin_run(self):
        url = 'https://portal.sidiv.registrocivil.cl/consulta?OTRO=123'
        metodo, rut = _parse_rut_escaneo(url)
        self.assertEqual(metodo, 'QR')
        self.assertEqual(rut, url)


# ============================================================
# 4. PROCESAR ESCANEO (POST)
# ============================================================

class ProcesarEscaneoTests(BaseSistemaTestCase):
    """Prueba _procesar_escaneo a través de la vista escaneo."""

    def seleccionar_actividad(self, actividad=None):
        actividad = actividad or self.actividad_masiva
        self.client.force_login(self.registrador)
        session = self.client.session
        session['actividad_escaneo_id'] = actividad.pk
        session.save()

    def test_sin_actividad_seleccionada_rechaza(self):
        self.client.force_login(self.registrador)
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 400)

    def test_sin_rut_rechaza(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': ''})
        self.assertEqual(response.status_code, 400)

    def test_alumno_inexistente_devuelve_404(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': '99999999-9'})
        self.assertEqual(response.status_code, 404)

    def test_primera_etapa_pide_confirmacion(self):
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['confirmar'])

    def test_segunda_etapa_crea_asistencia(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse('escaneo'),
            {'rut': self.alumno.rut, 'confirmar': 'true'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(
            Asistencia.objects.filter(
                actividad=self.actividad_masiva, alumno=self.alumno
            ).exists()
        )

    def test_asistencia_duplicada_rechaza(self):
        Asistencia.objects.create(
            actividad=self.actividad_masiva, alumno=self.alumno,
            metodo_ingreso='RUT', registrado_por=self.registrador,
        )
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 409)

    def test_taller_sin_inscripcion_rechaza(self):
        self.seleccionar_actividad(self.actividad)  # actividad es TALLER
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 403)

    def test_taller_con_inscripcion_acepta(self):
        Inscripcion.objects.create(
            actividad=self.actividad, alumno=self.alumno, estado='CONFIRMADA'
        )
        self.seleccionar_actividad(self.actividad)
        response = self.client.post(
            reverse('escaneo'),
            {'rut': self.alumno.rut, 'confirmar': 'true'},
        )
        self.assertEqual(response.status_code, 200)

    def test_actividad_inactiva_rechaza(self):
        self.actividad_masiva.estado = 'FINALIZADA'
        self.actividad_masiva.save(update_fields=['estado'])
        self.seleccionar_actividad()
        response = self.client.post(reverse('escaneo'), {'rut': self.alumno.rut})
        self.assertEqual(response.status_code, 404)

    def test_escaneo_con_qr_detecta_metodo(self):
        self.seleccionar_actividad()
        qr = 'https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9'
        self.client.post(reverse('escaneo'), {'rut': qr, 'confirmar': 'true'})
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, 'QR')


# ============================================================
# 5. ELIMINAR ACTIVIDAD
# ============================================================

class EliminarActividadTests(BaseSistemaTestCase):
    """Prueba eliminar_ajax."""

    def test_sin_permisos_rechaza(self):
        self.client.force_login(self.registrador)
        response = self.client.post(
            reverse('eliminar_ajax', args=[self.actividad.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)

    def test_metodo_get_rechaza(self):
        self.client.force_login(self.creador)
        response = self.client.get(
            reverse('eliminar_ajax', args=[self.actividad.pk]),
        )
        self.assertEqual(response.status_code, 405)

    def test_con_inscripciones_rechaza(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse('eliminar_ajax', args=[self.actividad.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_sin_registros_elimina(self):
        actividad_id = self.actividad.pk
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse('eliminar_ajax', args=[actividad_id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(Actividad.objects.filter(pk=actividad_id).exists())

    def test_creador_no_puede_eliminar_actividad_de_otro(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse('eliminar_ajax', args=[self.actividad_otro.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)


# ============================================================
# 6. COLOR DE ESCUELA
# ============================================================

class ColorParaEscuelaTests(TestCase):
    """Prueba color_para_escuela."""

    def test_escuela_mapeada_devuelve_color(self):
        color = color_para_escuela('Escuela de Informática y Telecomunicaciones')
        self.assertEqual(color, '#307FE2')

    def test_escuela_no_mapeada_devuelve_gris(self):
        color = color_para_escuela('Escuela Inexistente')
        self.assertEqual(color, '#666666')

    def test_escuela_vacia_devuelve_gris(self):
        self.assertEqual(color_para_escuela(''), '#666666')
        self.assertEqual(color_para_escuela(None), '#666666')

    def test_escuela_con_espacios_extra(self):
        color = color_para_escuela('  Escuela de Construcción  ')
        self.assertEqual(color, '#E87722')