from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Alumno, Inscripcion, LogAuditoria


class PoliticaPrivacidadTests(TestCase):
    def test_es_publica_y_muestra_la_politica(self):
        response = self.client.get(reverse("privacidad"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Política de Privacidad")
        self.assertContains(response, "puntoestu@duoc.cl")


class ConsentimientoInscripcionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        cls.actividad = Actividad.objects.create(
            titulo="Taller de prueba",
            descripcion="Descripción",
            tipo="TALLER",
            lugar="Sala 1",
            cupos_totales=2,
            cupos_disponibles=2,
            fecha_inicio=ahora + timedelta(days=1),
            fecha_fin=ahora + timedelta(days=1, hours=1),
            estado="ACTIVA",
        )
        cls.alumno = Alumno.objects.create(
            rut="20001550-9",
            tipo_documento="RUT",
            nombres="Juan",
            apellidos="Pérez",
            correo="juan.perez@example.com",
            carrera="Informática",
            jornada="Diurno",
        )
        cls.url = reverse("inscripcion_taller", args=[cls.actividad.pk])

    def test_formulario_muestra_la_casilla_y_el_enlace(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="acepta_politica"')
        self.assertContains(response, reverse("privacidad"))

    def test_sin_casilla_no_inscribe(self):
        response = self.client.post(self.url, {"rut": self.alumno.rut})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes aceptar la Política de Privacidad")
        self.assertEqual(Inscripcion.objects.count(), 0)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, 2)

    def test_sin_casilla_no_revela_si_el_documento_existe(self):
        response = self.client.post(self.url, {"rut": "99999999-9"})
        self.assertContains(response, "Debes aceptar la Política de Privacidad")
        self.assertNotContains(response, "No estás registrado")

    def test_con_casilla_inscribe_y_descuenta_cupo(self):
        response = self.client.post(
            self.url, {"rut": self.alumno.rut, "acepta_politica": "on"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Inscripcion.objects.filter(
                actividad=self.actividad, alumno=self.alumno
            ).count(),
            1,
        )
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, 1)

    def test_la_aceptacion_queda_en_la_auditoria(self):
        self.client.post(
            self.url, {"rut": self.alumno.rut, "acepta_politica": "on"}
        )
        self.assertTrue(
            LogAuditoria.objects.filter(detalle__contains="v2026-1").exists()
        )
