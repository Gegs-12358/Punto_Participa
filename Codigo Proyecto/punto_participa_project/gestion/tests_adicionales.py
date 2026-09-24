"""
Pruebas adicionales de seguridad y casos límite para Punto Participa.

Se ejecutan junto con la suite integral:
    python manage.py test gestion -v 2

Requiere que exista gestion/tests_integrales.py, porque reutiliza sus datos
comunes de prueba.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Asistencia, Inscripcion, LogAuditoria, NotificacionCorreo
from .tests_integrales import BaseSistemaTestCase


class EdicionYEliminacionTests(BaseSistemaTestCase):
    def datos_actividad(self, titulo="Actividad actualizada"):
        inicio = timezone.localtime(timezone.now() + timedelta(days=5))
        return {
            "titulo": titulo,
            "descripcion": "Descripción actualizada",
            "tipo": "TALLER",
            "lugar": "Sala nueva",
            "cupos_totales": 30,
            "fecha_inicio": inicio.strftime("%Y-%m-%dT%H:%M"),
            "fecha_fin": (inicio + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }

    def test_creador_puede_editar_su_actividad(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("editar_actividad", args=[self.actividad.pk]),
            self.datos_actividad(),
        )
        self.assertEqual(response.status_code, 302)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.titulo, "Actividad actualizada")
        self.assertTrue(
            LogAuditoria.objects.filter(accion="Edición de actividad").exists()
        )

    def test_creador_no_puede_editar_actividad_de_otro(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("editar_actividad", args=[self.actividad_otro.pk]),
            self.datos_actividad("Intento no autorizado"),
        )
        self.assertEqual(response.status_code, 302)
        self.actividad_otro.refresh_from_db()
        self.assertNotEqual(self.actividad_otro.titulo, "Intento no autorizado")

    def test_edicion_con_datos_asociados_pide_confirmacion_ajax(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.client.force_login(self.creador)
        response = self.client.get(
            reverse("editar_actividad", args=[self.actividad.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requiere_confirmacion"])

    def test_eliminar_actividad_con_inscripcion_es_rechazado(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("eliminar_ajax", args=[self.actividad.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertTrue(Actividad.objects.filter(pk=self.actividad.pk).exists())

    def test_eliminar_actividad_sin_registros_funciona(self):
        actividad_id = self.actividad.pk
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("eliminar_ajax", args=[actividad_id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(Actividad.objects.filter(pk=actividad_id).exists())
        self.assertTrue(
            LogAuditoria.objects.filter(
                accion="Eliminación rápida de actividad"
            ).exists()
        )


class EstadosYCuposTests(BaseSistemaTestCase):
    def test_no_se_puede_inscribir_en_actividad_finalizada(self):
        self.actividad.estado = "FINALIZADA"
        self.actividad.save(update_fields=["estado"])
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": self.alumno.rut},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "finalizado")
        self.assertFalse(Inscripcion.objects.filter(actividad=self.actividad).exists())

    def test_no_se_puede_inscribir_en_actividad_cancelada(self):
        self.actividad.estado = "CANCELADA"
        self.actividad.save(update_fields=["estado"])
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "finalizado")

    def test_no_se_puede_inscribir_sin_cupos(self):
        self.actividad.cupos_disponibles = 0
        self.actividad.save(update_fields=["cupos_disponibles"])
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin cupos")

    def test_no_se_registra_asistencia_en_actividad_inactiva(self):
        self.actividad_masiva.estado = "FINALIZADA"
        self.actividad_masiva.save(update_fields=["estado"])
        self.client.force_login(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()
        response = self.client.post(
            reverse("escaneo"), {"rut": self.alumno.rut}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Asistencia.objects.filter(actividad=self.actividad_masiva).exists())


class EscanerFormatosYSesionTests(BaseSistemaTestCase):
    def seleccionar_actividad(self, actividad=None):
        actividad = actividad or self.actividad_masiva
        self.client.force_login(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = actividad.pk
        session.save()

    def test_escaneo_por_qr_detecta_metodo_qr(self):
        self.seleccionar_actividad()
        qr = "https://portal.sidiv.registrocivil.cl/consulta?RUN=20001550-9"
        response = self.client.post(reverse("escaneo"), {"rut": qr})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["confirmar"])
        self.client.post(reverse("escaneo"), {"rut": qr, "confirmar": "true"})
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, "QR")

    def test_escaneo_por_codigo_detecta_metodo_codigo(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse("escaneo"), {"rut": "'20001550-9"}
        )
        self.assertEqual(response.status_code, 200)
        self.client.post(
            reverse("escaneo"),
            {"rut": "'20001550-9", "confirmar": "true"},
        )
        asistencia = Asistencia.objects.get(
            actividad=self.actividad_masiva, alumno=self.alumno
        )
        self.assertEqual(asistencia.metodo_ingreso, "CODIGO")

    def test_escaneo_sin_actividad_seleccionada_rechaza(self):
        self.client.force_login(self.registrador)
        response = self.client.post(
            reverse("escaneo"), {"rut": self.alumno.rut}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Primero selecciona", response.json()["message"])

    def test_finalizar_turno_limpia_la_actividad_de_la_sesion(self):
        self.seleccionar_actividad()
        response = self.client.post(
            reverse("escaneo"), {"finalizar_turno": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("actividad_escaneo_id", self.client.session)


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


class SeguridadCsrfYCuentaTests(BaseSistemaTestCase):
    def test_post_sin_csrf_es_rechazado_por_django(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.creador)
        response = cliente.post(
            reverse("crear_actividad"),
            {"titulo": "Sin CSRF"},
        )
        self.assertEqual(response.status_code, 403)

    def test_administrador_no_puede_bloquearse_a_si_mismo(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("guardar_usuario"),
            {
                "user_id": self.admin.usuariosistema.pk,
                "username": self.admin.username,
                "nombre": self.admin.first_name,
                "email": self.admin.email,
                "rol": self.rol_admin.pk,
                "rut": self.admin.usuariosistema.rut,
                # Sin estado: la vista interpreta la cuenta como inactiva.
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No puedes bloquear", response.json()["message"])

    def test_usuario_sin_rol_no_accede_a_endpoint_de_reportes(self):
        user = User.objects.create_user(
            username="sin_rol_adicional", password="ClaveSegura123!"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("reportes"))
        self.assertEqual(response.status_code, 302)


class FiltrosYParticipantesTests(BaseSistemaTestCase):
    def test_participantes_filtra_inscripciones_confirmadas(self):
        Inscripcion.objects.create(
            actividad=self.actividad, alumno=self.alumno, estado="CONFIRMADA"
        )
        Inscripcion.objects.create(
            actividad=self.actividad,
            alumno=self.alumno_pasaporte,
            estado="CANCELADA",
        )
        self.client.force_login(self.creador)
        response = self.client.get(
            reverse("participantes_actividad", args=[self.actividad.pk]),
            {"estado": "CONFIRMADA"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.alumno.nombres)
        self.assertNotContains(response, self.alumno_pasaporte.nombres)

    def test_notificaciones_filtra_por_estado(self):
        NotificacionCorreo.objects.create(
            actividad=self.actividad,
            alumno=self.alumno,
            estado_envio="EXITO",
        )
        NotificacionCorreo.objects.create(
            actividad=self.actividad,
            alumno=self.alumno_pasaporte,
            estado_envio="FALLO",
        )
        self.client.force_login(self.creador)
        response = self.client.get(
            reverse("notificaciones_actividad", args=[self.actividad.pk]),
            {"estado": "FALLO"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtro_estado"], "FALLO")
