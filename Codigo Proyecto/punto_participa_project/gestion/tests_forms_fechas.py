from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .forms import ActividadForm
from .models import Carrera, Jornada


class ActividadFormReglasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(
            nombre="Ingeniería en Informática",
            escuela="Escuela de Informática y Telecomunicaciones",
        )
        cls.jornada = Jornada.objects.create(nombre="Diurno")

    def _datos(self, **cambios):
        inicio = timezone.localtime(timezone.now() + timedelta(days=3))
        fin = inicio + timedelta(hours=1)
        datos = {
            "titulo": "Actividad de prueba",
            "descripcion": "Descripción",
            "tipo": "MASIVA",
            "lugar": "Sala 2",
            "fecha_inicio_fecha": inicio.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": inicio.strftime("%H:%M"),
            "fecha_fin_fecha": fin.strftime("%Y-%m-%d"),
            "fecha_fin_hora": fin.strftime("%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        datos.update(cambios)
        return datos

    def test_datos_base_son_validos(self):
        form = ActividadForm(data=self._datos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_fecha_de_termino_igual_al_inicio_es_error(self):
        base = self._datos()
        form = ActividadForm(data=self._datos(
            fecha_fin_fecha=base["fecha_inicio_fecha"],
            fecha_fin_hora=base["fecha_inicio_hora"],
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_fin_fecha", form.errors)

    def test_fecha_de_termino_anterior_al_inicio_es_error(self):
        anterior = timezone.localtime(timezone.now() + timedelta(days=2))
        form = ActividadForm(data=self._datos(
            fecha_fin_fecha=anterior.strftime("%Y-%m-%d"),
            fecha_fin_hora=anterior.strftime("%H:%M"),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_fin_fecha", form.errors)

    def test_taller_con_cupo_cero_es_error(self):
        form = ActividadForm(data=self._datos(tipo="TALLER", cupos_totales=0))
        self.assertFalse(form.is_valid())
        self.assertIn("cupos_totales", form.errors)

    def test_taller_sin_cupo_es_error(self):
        form = ActividadForm(data=self._datos(tipo="TALLER"))
        self.assertFalse(form.is_valid())
        self.assertIn("cupos_totales", form.errors)

    def test_fecha_de_inicio_en_el_pasado_es_error(self):
        pasado = timezone.localtime(timezone.now() - timedelta(days=1))
        fin = pasado + timedelta(hours=1)
        form = ActividadForm(data=self._datos(
            fecha_inicio_fecha=pasado.strftime("%Y-%m-%d"),
            fecha_inicio_hora=pasado.strftime("%H:%M"),
            fecha_fin_fecha=fin.strftime("%Y-%m-%d"),
            fecha_fin_hora=fin.strftime("%H:%M"),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_inicio_fecha", form.errors)
