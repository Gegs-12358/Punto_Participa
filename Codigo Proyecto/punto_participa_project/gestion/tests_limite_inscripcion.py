from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Alumno, Inscripcion
from .views import LIMITE_FALLOS_INSCRIPCION


class LimiteFallosInscripcionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        cls.actividad = Actividad.objects.create(
            titulo="Taller de prueba",
            descripcion="Descripción",
            tipo="TALLER",
            lugar="Sala 1",
            cupos_totales=5,
            cupos_disponibles=5,
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

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _fallar(self, **extra):
        return self.client.post(
            self.url, {"rut": "99999999-9", "acepta_politica": "on"}, **extra
        )

    def test_pasado_el_tope_se_bloquea_incluso_un_documento_valido(self):
        for n in range(1, LIMITE_FALLOS_INSCRIPCION + 1):
            r = self._fallar()
            self.assertContains(r, "No estás registrado", msg_prefix=f"intento {n}")
        r = self._fallar()
        self.assertContains(r, "Demasiados intentos fallidos")
        r = self.client.post(
            self.url, {"rut": self.alumno.rut, "acepta_politica": "on"}
        )
        self.assertContains(r, "Demasiados intentos fallidos")
        self.assertEqual(Inscripcion.objects.count(), 0)

    def test_las_inscripciones_y_repetidas_no_consumen_el_tope(self):
        datos = {"rut": self.alumno.rut, "acepta_politica": "on"}
        for _ in range(LIMITE_FALLOS_INSCRIPCION + 5):
            r = self.client.post(self.url, datos)
            self.assertNotContains(r, "Demasiados intentos fallidos")
        self.assertEqual(Inscripcion.objects.count(), 1)

    def test_los_envios_sin_casilla_no_cuentan(self):
        for _ in range(LIMITE_FALLOS_INSCRIPCION + 5):
            self.client.post(self.url, {"rut": "99999999-9"})
        r = self._fallar()
        self.assertContains(r, "No estás registrado")
        self.assertNotContains(r, "Demasiados intentos fallidos")

    def test_otra_ip_no_queda_bloqueada(self):
        for _ in range(LIMITE_FALLOS_INSCRIPCION + 1):
            self._fallar()
        r = self.client.post(
            self.url,
            {"rut": self.alumno.rut, "acepta_politica": "on"},
            REMOTE_ADDR="10.0.0.9",
        )
        self.assertNotContains(r, "Demasiados intentos fallidos")
        self.assertEqual(Inscripcion.objects.count(), 1)
