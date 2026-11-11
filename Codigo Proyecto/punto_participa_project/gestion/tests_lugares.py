"""
Pruebas del catálogo de lugares (sugerencia del Punto Estudiantil, noviembre 2026).

- La migración 0026 pasa al catálogo los lugares ya escritos y unifica variantes.
- El formulario de actividad solo ofrece lugares activos del catálogo.
- Al editar, un lugar ya bloqueado se mantiene válido para esa actividad.
- El filtro por lugar funciona en el listado de actividades, en reportes y en la exportación.
"""
import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ActividadForm
from .models import Actividad, Lugar
from .tests_integrales import BaseSistemaTestCase

migracion_lugar = importlib.import_module('gestion.migrations.0026_lugar')


class MigracionLugaresTests(BaseSistemaTestCase):
    def test_pasa_los_lugares_al_catalogo_y_unifica_variantes(self):
        Lugar.objects.all().delete()
        Actividad.objects.all().delete()
        ahora = timezone.now()
        for lugar in ('Auditorio', 'Auditorio', ' auditorio ', 'AUDITORIO  ', 'Sala   101', 'Sala 101'):
            Actividad.objects.create(
                titulo='x', descripcion='x', tipo='MASIVA', lugar=lugar,
                fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=1),
            )

        migracion_lugar.poblar_lugares(django_apps, None)

        self.assertEqual(sorted(Lugar.objects.values_list('nombre', flat=True)),
                         ['Auditorio', 'Sala 101'])
        self.assertEqual(Actividad.objects.filter(lugar='Auditorio').count(), 4)
        self.assertEqual(Actividad.objects.filter(lugar='Sala 101').count(), 2)

    def test_repetirla_no_duplica(self):
        migracion_lugar.poblar_lugares(django_apps, None)
        antes = Lugar.objects.count()
        migracion_lugar.poblar_lugares(django_apps, None)
        self.assertEqual(Lugar.objects.count(), antes)


class FormularioLugarTests(BaseSistemaTestCase):
    def _datos(self, lugar):
        inicio = timezone.localtime(timezone.now() + timedelta(days=3))
        fin = inicio + timedelta(hours=1)
        return {
            'titulo': 'Charla', 'descripcion': 'Descripción', 'tipo': 'MASIVA', 'lugar': lugar,
            'fecha_inicio_fecha': inicio.strftime('%Y-%m-%d'),
            'fecha_inicio_hora': inicio.strftime('%H:%M'),
            'fecha_fin_fecha': fin.strftime('%Y-%m-%d'),
            'fecha_fin_hora': fin.strftime('%H:%M'),
            'carreras': [self.carrera.pk], 'jornadas': [self.jornada.pk],
        }

    def test_solo_ofrece_lugares_activos(self):
        Lugar.objects.create(nombre='Sala cerrada', activo=False)
        opciones = list(ActividadForm().fields['lugar'].queryset.values_list('nombre', flat=True))
        self.assertIn('Sala 1', opciones)
        self.assertNotIn('Sala cerrada', opciones)

    def test_guarda_el_nombre_del_lugar(self):
        form = ActividadForm(data=self._datos('Sala 1'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().lugar, 'Sala 1')

    def test_rechaza_lugar_escrito_a_mano(self):
        form = ActividadForm(data=self._datos('Sala que no existe'))
        self.assertFalse(form.is_valid())
        self.assertIn('lugar', form.errors)

    def test_rechaza_lugar_bloqueado_en_actividad_nueva(self):
        Lugar.objects.create(nombre='Sala cerrada', activo=False)
        form = ActividadForm(data=self._datos('Sala cerrada'))
        self.assertFalse(form.is_valid())
        self.assertIn('lugar', form.errors)

    def test_al_editar_conserva_su_lugar_aunque_este_bloqueado(self):
        Lugar.objects.create(nombre='Sala cerrada', activo=False)
        self.actividad_masiva.lugar = 'Sala cerrada'
        self.actividad_masiva.save(update_fields=['lugar'])

        form = ActividadForm(instance=self.actividad_masiva)
        self.assertEqual(form.initial['lugar'], 'Sala cerrada')

        form = ActividadForm(data=self._datos('Sala cerrada'), instance=self.actividad_masiva)
        self.assertTrue(form.is_valid(), form.errors)

    def test_el_formulario_muestra_un_desplegable(self):
        self.login_as(self.admin)
        html = self.client.get(reverse('crear_actividad')).content.decode()
        self.assertIn('<select name="lugar"', html)
        self.assertIn('Selecciona un lugar', html)


class FiltroLugarTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.actividad_masiva.lugar = 'Auditorio'
        cls.actividad_masiva.save(update_fields=['lugar'])

    def test_listado_de_actividades_filtra_por_lugar(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('lista_actividades'), {'lugar': 'Auditorio'})
        titulos = [a.titulo for a in resp.context['actividades']]
        self.assertEqual(titulos, ['Actividad masiva'])
        self.assertIn('Auditorio', resp.context['lugares_opciones'])
        self.assertContains(resp, 'Lugar:')          # chip del filtro activo

    def test_reportes_filtra_por_lugar(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('reportes'), {'lugar': 'Auditorio'})
        titulos = [a.titulo for a in resp.context['actividades']]
        self.assertEqual(titulos, ['Actividad masiva'])

    def test_exportacion_respeta_el_filtro(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('exportar_reportes', args=['csv']), {'lugar': 'Auditorio'})
        contenido = resp.content.decode('utf-8-sig')
        self.assertIn('Actividad masiva', contenido)
        self.assertNotIn('Taller integral', contenido)

    def test_lugar_hostil_no_rompe_la_pagina(self):
        self.login_as(self.admin)
        for valor in ("<script>x</script>", "' OR 1=1 --", "\x00"):
            with self.subTest(valor=repr(valor)):
                resp = self.client.get(reverse('lista_actividades'), {'lugar': valor})
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, '<script>x</script>')


class LugarModeloTests(TestCase):
    def test_orden_y_texto(self):
        Lugar.objects.create(nombre='Sala B')
        Lugar.objects.create(nombre='Auditorio')
        self.assertEqual([str(l) for l in Lugar.objects.all()], ['Auditorio', 'Sala B'])