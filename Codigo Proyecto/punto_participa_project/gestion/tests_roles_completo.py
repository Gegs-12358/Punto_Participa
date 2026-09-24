"""
Matriz legible de permisos por rol para Punto Participa.

Este archivo complementa tests.py, tests_integrales.py y tests_adicionales.py.
Prueba qué puede abrir cada rol y qué debe ser rechazado.

Ejecución recomendada:
    python manage.py test gestion.tests_roles_completo -v 2

Ejecución de todo el sistema:
    python manage.py test gestion -v 2

Con -v 2 Django muestra cada caso como:
    test_admin_dashboard: OK
    test_registrador_reportes: OK

Al final muestra el resumen oficial:
    Ran N tests
    OK

Si existe un fallo, Django muestra la clase, el método y el traceback.
"""

from django.test import TestCase
from django.urls import reverse

from .models import Asistencia, Inscripcion
from .tests_integrales import BaseSistemaTestCase


class MatrizAdministradorTests(BaseSistemaTestCase):
    """El administrador puede acceder a las áreas administrativas y operativas."""

    def login_admin(self):
        self.client.force_login(self.admin)

    def test_admin_dashboard(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_admin_reportes(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("reportes")).status_code, 200)

    def test_admin_gestion_usuarios(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("usuarios")).status_code, 200)

    def test_admin_lista_actividades(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("lista_actividades")).status_code, 200)

    def test_admin_detalle_participantes_y_notificaciones(self):
        self.login_admin()
        self.assertEqual(
            self.client.get(reverse("actividad_detalle", args=[self.actividad.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("participantes_actividad", args=[self.actividad.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("notificaciones_actividad", args=[self.actividad.pk])).status_code,
            200,
        )

    def test_admin_escaneo(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("escaneo")).status_code, 200)

    def test_admin_auditoria(self):
        self.login_admin()
        self.assertEqual(self.client.get(reverse("auditoria")).status_code, 200)

    def test_admin_exportaciones(self):
        self.login_admin()
        self.assertEqual(
            self.client.get(reverse("exportar_reportes", args=["excel"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("exportar_reportes_detalle", args=["excel"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("exportar_auditoria")).status_code,
            200,
        )


class MatrizCreadorDeEventoTests(BaseSistemaTestCase):
    """El creador gestiona actividades y no entra en administración/auditoría."""

    def login_creador(self):
        self.client.force_login(self.creador)

    def test_creador_dashboard(self):
        self.login_creador()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_creador_reportes(self):
        self.login_creador()
        self.assertEqual(self.client.get(reverse("reportes")).status_code, 200)

    def test_creador_lista_y_detalle_de_su_actividad(self):
        self.login_creador()
        self.assertEqual(self.client.get(reverse("lista_actividades")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("actividad_detalle", args=[self.actividad.pk])).status_code,
            200,
        )

    def test_creador_participantes_y_notificaciones(self):
        self.login_creador()
        self.assertEqual(
            self.client.get(reverse("participantes_actividad", args=[self.actividad.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("notificaciones_actividad", args=[self.actividad.pk])).status_code,
            200,
        )

    def test_creador_escaneo(self):
        self.login_creador()
        self.assertEqual(self.client.get(reverse("escaneo")).status_code, 200)

    def test_creador_no_entra_a_usuarios_ni_auditoria(self):
        self.login_creador()
        self.assertEqual(self.client.get(reverse("usuarios")).status_code, 302)
        self.assertEqual(self.client.get(reverse("auditoria")).status_code, 302)

    def test_creador_exporta_reportes_pero_no_auditoria(self):
        self.login_creador()
        self.assertEqual(
            self.client.get(reverse("exportar_reportes", args=["csv"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("exportar_reportes_detalle", args=["excel"])).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse("exportar_auditoria")).status_code, 403)

    def test_creador_no_ve_actividad_de_otro_creador(self):
        self.login_creador()
        response = self.client.get(
            reverse("actividad_detalle", args=[self.actividad_otro.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("lista_actividades"))


class MatrizEncargadoRegistrarTests(BaseSistemaTestCase):
    """El registrador trabaja en escaneo y no accede a gestión administrativa."""

    def login_registrador(self):
        self.client.force_login(self.registrador)

    def test_registrador_es_redirigido_del_dashboard_al_escaneo(self):
        self.login_registrador()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("escaneo"))

    def test_registrador_puede_abrir_escaneo(self):
        self.login_registrador()
        self.assertEqual(self.client.get(reverse("escaneo")).status_code, 200)

    def test_registrador_no_accede_a_reportes(self):
        self.login_registrador()
        self.assertEqual(self.client.get(reverse("reportes")).status_code, 302)

    def test_registrador_no_accede_a_usuarios_ni_auditoria(self):
        self.login_registrador()
        self.assertEqual(self.client.get(reverse("usuarios")).status_code, 302)
        self.assertEqual(self.client.get(reverse("auditoria")).status_code, 302)

    def test_registrador_no_exporta_reportes_ni_auditoria(self):
        self.login_registrador()
        self.assertEqual(
            self.client.get(reverse("exportar_reportes", args=["csv"])).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("exportar_auditoria")).status_code, 403)

    def test_registrador_registra_asistencia_en_actividad_masiva(self):
        self.login_registrador()
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()

        primera = self.client.post(
            reverse("escaneo"), {"rut": self.alumno.rut}
        )
        self.assertEqual(primera.status_code, 200)
        self.assertTrue(primera.json()["confirmar"])

        segunda = self.client.post(
            reverse("escaneo"),
            {"rut": self.alumno.rut, "confirmar": "true"},
        )
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()["success"])
        self.assertTrue(
            Asistencia.objects.filter(
                actividad=self.actividad_masiva, alumno=self.alumno
            ).exists()
        )


class MatrizAccesoAnonimoTests(BaseSistemaTestCase):
    """Las vistas privadas redirigen o rechazan a usuarios no autenticados."""

    def test_anonimo_dashboard_redirige_a_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_anonimo_reportes_redirige_a_login(self):
        response = self.client.get(reverse("reportes"))
        self.assertEqual(response.status_code, 302)

    def test_anonimo_usuarios_redirige_a_login(self):
        response = self.client.get(reverse("usuarios"))
        self.assertEqual(response.status_code, 302)

    def test_anonimo_escaneo_redirige_a_login(self):
        response = self.client.get(reverse("escaneo"))
        self.assertEqual(response.status_code, 302)

    def test_inscripcion_publica_sigue_disponible(self):
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)


class FlujoRolCompletoTests(BaseSistemaTestCase):
    """Pruebas adicionales de funciones que cambian datos por rol."""

    def test_admin_puede_ver_actividad_de_otro_creador(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("actividad_detalle", args=[self.actividad_otro.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_creador_puede_inscribir_alumno_en_su_taller(self):
        self.client.force_login(self.creador)
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": self.alumno.rut},
        )
        # La inscripción pública no exige autenticación; el creador también debe
        # poder abrir el flujo y dejar registrada la inscripción.
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Inscripcion.objects.filter(
                actividad=self.actividad, alumno=self.alumno
            ).exists()
        )

    def test_registrador_no_puede_ver_detalle_de_actividad(self):
        self.client.force_login(self.registrador)
        response = self.client.get(
            reverse("actividad_detalle", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 302)
