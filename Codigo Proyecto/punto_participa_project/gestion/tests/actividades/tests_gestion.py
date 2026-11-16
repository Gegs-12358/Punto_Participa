"""
Crear, editar y eliminar actividades, con confirmación cuando ya tienen inscritos o asistencias.

Correr solo este archivo:
    python manage.py test gestion.tests.actividades.tests_gestion --noinput
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Actividad, Asistencia, Inscripcion, LogAuditoria, NotificacionCorreo
from ..base import BaseSistemaTestCase, SilenciarRegistros


class EdicionYEliminacionTests(BaseSistemaTestCase):
    def datos_actividad(self, titulo="Actividad actualizada"):
        inicio = timezone.localtime(timezone.now() + timedelta(days=5))
        return {
            "titulo": titulo,
            "descripcion": "Descripción actualizada",
            "tipo": "TALLER",
            "lugar": "Sala nueva",
            "cupos_totales": 30,
            "fecha_inicio_fecha": inicio.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": inicio.strftime("%H:%M"),
            "fecha_fin_fecha": (inicio + timedelta(hours=2)).strftime("%Y-%m-%d"),
            "fecha_fin_hora": (inicio + timedelta(hours=2)).strftime("%H:%M"),
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


class EliminarActividadTests(SilenciarRegistros, BaseSistemaTestCase):
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

    def test_creador_no_puede_eliminar_actividad_de_otro(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse('eliminar_ajax', args=[self.actividad_otro.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)


class RestriccionesDeDatosExtremasTests(SilenciarRegistros, BaseSistemaTestCase):
    def test_inscripcion_duplicada_es_rechazada_por_la_base(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)

    def test_asistencia_duplicada_es_rechazada_por_la_base(self):
        Asistencia.objects.create(
            actividad=self.actividad_masiva,
            alumno=self.alumno,
            metodo_ingreso="RUT",
            registrado_por=self.registrador,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Asistencia.objects.create(
                    actividad=self.actividad_masiva,
                    alumno=self.alumno,
                    metodo_ingreso="QR",
                    registrado_por=self.registrador,
                )

    def test_eliminar_actividad_cascadea_inscripciones_y_asistencias(self):
        inscripcion = Inscripcion.objects.create(
            actividad=self.actividad, alumno=self.alumno
        )
        asistencia = Asistencia.objects.create(
            actividad=self.actividad,
            alumno=self.alumno,
            metodo_ingreso="RUT",
            registrado_por=self.registrador,
        )
        actividad_id = self.actividad.pk
        self.actividad.delete()
        self.assertFalse(Actividad.objects.filter(pk=actividad_id).exists())
        self.assertFalse(Inscripcion.objects.filter(pk=inscripcion.pk).exists())
        self.assertFalse(Asistencia.objects.filter(pk=asistencia.pk).exists())

    def test_recalculo_de_cupos_nunca_queda_negativo(self):
        self.actividad.cupos_totales = 1
        self.actividad.recalcular_cupos(inscritos_override=99)
        self.assertEqual(self.actividad.cupos_disponibles, 0)
        self.assertTrue(self.actividad.esta_lleno)

    def test_formulario_limpia_cupos_de_actividad_masiva(self):
        inicio = timezone.localtime(timezone.now() + timedelta(days=4))
        form = ActividadForm(
            data={
                "titulo": "Masiva sin cupos",
                "descripcion": "Actividad general",
                "tipo": "MASIVA",
                "lugar": "Auditorio",
                "cupos_totales": 500,
                "fecha_inicio_fecha": inicio.strftime("%Y-%m-%d"),
                "fecha_inicio_hora": inicio.strftime("%H:%M"),
                "fecha_fin_fecha": (inicio + timedelta(hours=2)).strftime("%Y-%m-%d"),
                "fecha_fin_hora": (inicio + timedelta(hours=2)).strftime("%H:%M"),
                "carreras": [self.carrera.pk],
                "jornadas": [self.jornada.pk],
            }
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        actividad = form.save(commit=False)
        self.assertIsNone(actividad.cupos_totales)
        self.assertIsNone(actividad.cupos_disponibles)


class VistasAjaxYValidacionesExtremasTests(SilenciarRegistros, BaseSistemaTestCase):
    def datos_creacion(self, titulo="Actividad AJAX válida"):
        inicio = timezone.localtime(timezone.now() + timedelta(days=6))
        return {
            "titulo": titulo,
            "descripcion": "Descripción de una actividad nueva",
            "tipo": "TALLER",
            "lugar": "Sala AJAX",
            "cupos_totales": 10,
            "fecha_inicio_fecha": inicio.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": inicio.strftime("%H:%M"),
            "fecha_fin_fecha": (inicio + timedelta(hours=2)).strftime("%Y-%m-%d"),
            "fecha_fin_hora": (inicio + timedelta(hours=2)).strftime("%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }

    def test_crear_actividad_ajax_valida_devuelve_id(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("crear_actividad"),
            self.datos_creacion(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertTrue(datos["success"])
        self.assertTrue(Actividad.objects.filter(pk=datos["id"]).exists())

    def test_crear_actividad_ajax_invalida_devuelve_errores(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("crear_actividad"),
            {"titulo": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])
        self.assertIn("formActividad", response.json()["html"])

    def test_crear_actividad_get_partial_devuelve_fragmento(self):
        self.client.force_login(self.creador)
        response = self.client.get(reverse("crear_actividad") + "?partial=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="formActividad"')

    def test_exportacion_de_formato_no_permitido_no_rompe_la_respuesta(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("exportar_reportes", args=["pdf"]))
        self.assertIn(response.status_code, (200, 400, 404))
