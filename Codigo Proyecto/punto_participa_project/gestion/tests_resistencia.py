"""
Pruebas de resistencia y consistencia de Punto Participa.

Estas pruebas utilizan únicamente la base de datos temporal de Django. No
modifican la base de datos de desarrollo ni la producción.

Ejecución:
    python manage.py test gestion.tests_resistencia -v 2

Ejecución completa:
    python manage.py test gestion -v 2

La prueba concurrente requiere PostgreSQL porque usa select_for_update().
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection, close_old_connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Alumno, Asistencia, Inscripcion, LogAuditoria
from .tests_integrales import BaseSistemaTestCase


class CargaControladaTests(BaseSistemaTestCase):
    def crear_alumnos(self, cantidad, prefijo="Carga"):
        alumnos = []
        for indice in range(cantidad):
            alumnos.append(
                Alumno(
                    rut=f"{30000000 + indice}-0",
                    tipo_documento="RUT",
                    nombres=f"{prefijo}{indice}",
                    apellidos="Prueba",
                    correo=f"{prefijo.lower()}{indice}@example.com",
                    carrera=self.carrera.nombre,
                    jornada=self.jornada.nombre,
                )
            )
        return Alumno.objects.bulk_create(alumnos)

    def test_carga_de_inscripciones_mantiene_cupos_consistentes(self):
        alumnos = self.crear_alumnos(40)
        self.actividad.cupos_totales = 15
        self.actividad.cupos_disponibles = 15
        self.actividad.save(update_fields=["cupos_totales", "cupos_disponibles"])

        inscritos = 0
        for alumno in alumnos:
            response = self.client.post(
                reverse("inscripcion_taller", args=[self.actividad.pk]),
                {"rut": alumno.rut},
            )
            self.assertEqual(response.status_code, 200)
            if Inscripcion.objects.filter(actividad=self.actividad, alumno=alumno).exists():
                inscritos += 1

        self.actividad.refresh_from_db()
        self.assertEqual(inscritos, 15)
        self.assertEqual(self.actividad.cupos_disponibles, 0)
        self.assertGreaterEqual(self.actividad.cupos_disponibles, 0)
        self.assertEqual(
            Inscripcion.objects.filter(actividad=self.actividad).count(), 15
        )

    def test_carga_de_asistencias_no_duplica_alumnos(self):
        alumnos = self.crear_alumnos(80, prefijo="Asistencia")
        Asistencia.objects.bulk_create(
            [
                Asistencia(
                    actividad=self.actividad_masiva,
                    alumno=alumno,
                    metodo_ingreso="RUT",
                    registrado_por=self.registrador,
                )
                for alumno in alumnos
            ]
        )
        self.assertEqual(
            Asistencia.objects.filter(actividad=self.actividad_masiva).count(),
            80,
        )
        self.assertEqual(
            Asistencia.objects.filter(actividad=self.actividad_masiva)
            .values("alumno_id")
            .distinct()
            .count(),
            80,
        )

    def test_reporte_con_muchas_actividades_responde(self):
        actividades = []
        ahora = timezone.now()
        for indice in range(60):
            actividades.append(
                Actividad(
                    titulo=f"Carga de reportes {indice}",
                    descripcion="Actividad generada para prueba de carga",
                    tipo="MASIVA",
                    lugar="Auditorio",
                    fecha_inicio=ahora + timedelta(days=indice + 3),
                    fecha_fin=ahora + timedelta(days=indice + 3, hours=2),
                    creado_por=self.admin,
                )
            )
        Actividad.objects.bulk_create(actividades)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reportes"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(Actividad.objects.count(), 63)

    def test_exportacion_csv_con_muchos_registros_no_queda_vacia(self):
        alumnos = self.crear_alumnos(25, prefijo="Export")
        Asistencia.objects.bulk_create(
            [
                Asistencia(
                    actividad=self.actividad_masiva,
                    alumno=alumno,
                    metodo_ingreso="RUT",
                    registrado_por=self.registrador,
                )
                for alumno in alumnos
            ]
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("exportar_reportes", args=["csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 100)
        self.assertIn(self.actividad_masiva.titulo.encode(), response.content)

    def test_auditoria_con_muchos_registros_se_puede_exportar(self):
        LogAuditoria.objects.bulk_create(
            [
                LogAuditoria(
                    usuario_sistema=self.admin,
                    modulo="Resistencia",
                    accion=f"Acción {indice}",
                    detalle="Registro de carga controlada",
                )
                for indice in range(100)
            ]
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("exportar_auditoria"))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 100)


class RollbackTransaccionalTests(BaseSistemaTestCase):
    def test_error_durante_inscripcion_revierte_cupo_y_registro(self):
        self.client.raise_request_exception = False
        cupos_iniciales = self.actividad.cupos_disponibles
        with patch(
            "gestion.views.registrar_log",
            side_effect=RuntimeError("fallo controlado de auditoría"),
        ):
            response = self.client.post(
                reverse("inscripcion_taller", args=[self.actividad.pk]),
                {"rut": self.alumno.rut},
            )
        self.assertEqual(response.status_code, 500)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, cupos_iniciales)
        self.assertFalse(
            Inscripcion.objects.filter(
                actividad=self.actividad, alumno=self.alumno
            ).exists()
        )

    def test_error_durante_asistencia_revierte_el_registro(self):
        self.client.force_login(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()
        self.client.raise_request_exception = False

        with patch(
            "gestion.views.registrar_log",
            side_effect=RuntimeError("fallo controlado de auditoría"),
        ):
            self.client.post(
                reverse("escaneo"),
                {"rut": self.alumno.rut},
            )
            response = self.client.post(
                reverse("escaneo"),
                {"rut": self.alumno.rut, "confirmar": "true"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(
            Asistencia.objects.filter(
                actividad=self.actividad_masiva, alumno=self.alumno
            ).exists()
        )


@skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL para probar select_for_update")
class ConcurrenciaDeCuposTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Reutiliza una preparación mínima compatible con TransactionTestCase.
        from .models import Carrera, Jornada, Rol, UsuarioSistema

        cls.rol = Rol.objects.create(nombre="Encargado de Registrar")
        cls.user = User.objects.create_user(
            username="registrador_concurrente",
            password="ClaveSegura123!",
        )
        UsuarioSistema.objects.create(
            user=cls.user,
            rol=cls.rol,
            activo=True,
            must_change_password=False,
            rut="88888888-8",
        )
        cls.carrera = Carrera.objects.create(
            nombre="Carrera Concurrente",
            escuela="Escuela de Pruebas",
        )
        cls.jornada = Jornada.objects.create(nombre="Jornada Concurrente")
        ahora = timezone.now()
        cls.actividad = Actividad.objects.create(
            titulo="Actividad concurrente",
            descripcion="Prueba de solicitudes simultáneas",
            tipo="TALLER",
            lugar="Laboratorio",
            cupos_totales=3,
            cupos_disponibles=3,
            fecha_inicio=ahora + timedelta(days=2),
            fecha_fin=ahora + timedelta(days=2, hours=2),
            creado_por=cls.user,
        )
        cls.actividad.carreras.add(cls.carrera)
        cls.actividad.jornadas.add(cls.jornada)
        cls.alumnos = []
        for indice in range(8):
            cls.alumnos.append(
                Alumno.objects.create(
                    rut=f"4000000{indice}-0",
                    tipo_documento="RUT",
                    nombres=f"Concurrente{indice}",
                    apellidos="Prueba",
                    correo=f"concurrente{indice}@example.com",
                    carrera=cls.carrera.nombre,
                    jornada=cls.jornada.nombre,
                )
            )

    @classmethod
    def tearDownClass(cls):
        close_old_connections()
        super().tearDownClass()

    def solicitar_inscripcion(self, alumno):
        close_old_connections()
        try:
            cliente = Client()
            response = cliente.post(
                reverse("inscripcion_taller", args=[self.actividad.pk]),
                {"rut": alumno.rut},
            )
            return response.status_code
        finally:
            close_old_connections()

    def test_inscripciones_simultaneas_no_superan_los_cupos(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            futuros = [
                executor.submit(self.solicitar_inscripcion, alumno)
                for alumno in self.alumnos
            ]
            estados = [futuro.result() for futuro in as_completed(futuros)]

        self.actividad.refresh_from_db()
        total = Inscripcion.objects.filter(actividad=self.actividad).count()
        self.assertEqual(total, 3)
        self.assertEqual(self.actividad.cupos_disponibles, 0)
        self.assertGreaterEqual(self.actividad.cupos_disponibles, 0)
        self.assertEqual(len(estados), 8)
