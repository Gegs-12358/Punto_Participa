"""
Pruebas del número de sala (sugerencia del Punto Estudiantil, noviembre 2026).

En vez de una opción por sala en el desplegable, el lugar "Sala" del catálogo pide el
número ("1203") al crear la actividad. Se muestra junto: "Sala 1203".
"""
import io
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ActividadForm
from .models import Actividad, Lugar
from .tests_integrales import BaseSistemaTestCase


class FormularioNumeroSalaTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Lugar.objects.create(nombre='Sala', pide_numero=True)

    def _datos(self, lugar, numero=''):
        inicio = timezone.localtime(timezone.now() + timedelta(days=3))
        fin = inicio + timedelta(hours=1)
        return {
            'titulo': 'Charla', 'descripcion': 'Descripción', 'tipo': 'MASIVA',
            'lugar': lugar, 'lugar_numero': numero,
            'fecha_inicio_fecha': inicio.strftime('%Y-%m-%d'),
            'fecha_inicio_hora': inicio.strftime('%H:%M'),
            'fecha_fin_fecha': fin.strftime('%Y-%m-%d'),
            'fecha_fin_hora': fin.strftime('%H:%M'),
            'carreras': [self.carrera.pk], 'jornadas': [self.jornada.pk],
        }

    def test_sala_con_numero_se_guarda_aparte(self):
        form = ActividadForm(data=self._datos('Sala', '1203'))
        self.assertTrue(form.is_valid(), form.errors)
        actividad = form.save()
        self.assertEqual((actividad.lugar, actividad.lugar_numero), ('Sala', '1203'))
        self.assertEqual(actividad.lugar_completo, 'Sala 1203')

    def test_sala_sin_numero_es_rechazada(self):
        form = ActividadForm(data=self._datos('Sala', ''))
        self.assertFalse(form.is_valid())
        self.assertIn('lugar_numero', form.errors)

    def test_numero_se_normaliza(self):
        for escrito, guardado in (('a-201', 'A-201'), (' 12 03 ', '1203'), ('2203', '2203')):
            with self.subTest(escrito=escrito):
                form = ActividadForm(data=self._datos('Sala', escrito))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['lugar_numero'], guardado)

    def test_numero_con_simbolos_es_rechazado(self):
        for escrito in ('12/3', '<b>1', '-12', '12-', "1'2"):
            with self.subTest(escrito=escrito):
                form = ActividadForm(data=self._datos('Sala', escrito))
                self.assertFalse(form.is_valid())
                self.assertIn('lugar_numero', form.errors)

    def test_numero_demasiado_largo_es_rechazado(self):
        form = ActividadForm(data=self._datos('Sala', '12345678901'))
        self.assertFalse(form.is_valid())
        self.assertIn('lugar_numero', form.errors)

    def test_lugar_que_no_pide_numero_lo_descarta(self):
        form = ActividadForm(data=self._datos('Auditorio', '999'))
        self.assertTrue(form.is_valid(), form.errors)
        actividad = form.save()
        self.assertEqual(actividad.lugar_numero, '')
        self.assertEqual(actividad.lugar_completo, 'Auditorio')

    def test_desplegable_marca_los_lugares_que_piden_numero(self):
        html = str(ActividadForm()['lugar'])
        self.assertIn('value="Sala" data-pide-numero="1"', html)
        self.assertNotIn('value="Auditorio" data-pide-numero', html)

    def test_campo_oculto_salvo_que_el_lugar_pida_numero(self):
        self.assertFalse(ActividadForm().lugar_pide_numero)
        self.assertTrue(ActividadForm(data=self._datos('Sala', '')).lugar_pide_numero)
        self.actividad_masiva.lugar, self.actividad_masiva.lugar_numero = 'Sala', '1203'
        self.actividad_masiva.save(update_fields=['lugar', 'lugar_numero'])
        form = ActividadForm(instance=self.actividad_masiva)
        self.assertTrue(form.lugar_pide_numero)
        self.assertEqual(form['lugar_numero'].value(), '1203')

    def test_crear_desde_la_vista(self):
        self.login_as(self.admin)
        resp = self.client.post(reverse('crear_actividad'), self._datos('Sala', '2203'))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Actividad.objects.filter(lugar='Sala', lugar_numero='2203').exists())

    def test_filtro_por_lugar_agrupa_todas_las_salas(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(lugar='Sala', lugar_numero='1203')
        Actividad.objects.filter(pk=self.actividad_masiva.pk).update(lugar='Sala', lugar_numero='2203')
        self.login_as(self.admin)
        resp = self.client.get(reverse('lista_actividades'), {'lugar': 'Sala'})
        self.assertEqual({a.titulo for a in resp.context['actividades']},
                         {'Taller integral', 'Actividad masiva'})


class MostrarNumeroSalaTests(BaseSistemaTestCase):
    def setUp(self):
        Actividad.objects.filter(pk=self.actividad_masiva.pk).update(lugar='Sala', lugar_numero='1203')
        self.actividad_masiva.refresh_from_db()

    def test_pagina_publica_muestra_sala_y_numero(self):
        resp = self.client.get(reverse('actividad_publica', args=[self.actividad_masiva.pk]))
        self.assertContains(resp, 'Sala 1203')

    def test_detalle_muestra_sala_y_numero(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('actividad_detalle', args=[self.actividad_masiva.pk]))
        self.assertContains(resp, 'Sala 1203')


class CatalogoNumeroSalaTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)

    def test_agregar_lugar_que_pide_numero(self):
        self.client.post(reverse('catalogo_lugares'), {'accion': 'crear', 'nombre': 'Sala', 'pide_numero': 'on'})
        self.assertTrue(Lugar.objects.get(nombre='Sala').pide_numero)
        self.client.post(reverse('catalogo_lugares'), {'accion': 'crear', 'nombre': 'Patio'})
        self.assertFalse(Lugar.objects.get(nombre='Patio').pide_numero)

    def test_activar_y_quitar_pide_numero(self):
        lugar = Lugar.objects.get(nombre='Sala 1')
        url = reverse('catalogo_lugares')
        self.client.post(url, {'accion': 'pide_numero', 'lugar_id': lugar.pk, 'valor': 'si'})
        lugar.refresh_from_db()
        self.assertTrue(lugar.pide_numero)
        self.client.post(url, {'accion': 'pide_numero', 'lugar_id': lugar.pk, 'valor': 'no'})
        lugar.refresh_from_db()
        self.assertFalse(lugar.pide_numero)

    def test_la_pantalla_muestra_la_columna(self):
        resp = self.client.get(reverse('catalogo_lugares'))
        self.assertContains(resp, 'Número de sala')
        self.assertContains(resp, 'name="pide_numero"')


class SeedNumeroSalaTests(TestCase):
    def test_seed_crea_sala_con_numero(self):
        call_command('seed_data', '--alumnos-por-carrera', '1', '--actividades', '5', stdout=io.StringIO())
        self.assertTrue(Lugar.objects.get(nombre='Sala').pide_numero)
        sala = Actividad.objects.filter(lugar='Sala').first()
        self.assertTrue(sala.lugar_numero.isdigit())
        self.assertFalse(Lugar.objects.filter(nombre__startswith='Sala 2').exists())