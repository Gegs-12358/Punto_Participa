"""
Catálogo de lugares, número de sala, el lugar en el formulario y los filtros por lugar.

Correr solo este archivo:
    python manage.py test gestion.tests.catalogos.tests_lugares --noinput
"""
from datetime import timedelta
import io

import importlib

from django.apps import apps as django_apps
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Actividad, LogAuditoria, Lugar
from ..base import BaseSistemaTestCase


URL = reverse('catalogo_lugares')


class AccesoCatalogoLugaresTests(BaseSistemaTestCase):
    def test_solo_el_administrador_entra(self):
        for usuario in (self.creador, self.registrador):
            with self.subTest(usuario=usuario.username):
                self.login_as(usuario)
                self.assertEqual(self.client.get(URL).status_code, 302)
                self.client.post(URL, {'accion': 'crear', 'nombre': 'Sala intrusa'})
                self.assertFalse(Lugar.objects.filter(nombre='Sala intrusa').exists())

    def test_administrador_ve_los_lugares_y_su_uso(self):
        self.login_as(self.admin)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Sala 1')
        usos = {l.nombre: l.total_actividades for l in resp.context['lugares']}
        self.assertEqual(usos['Sala 1'], 0)

    def test_el_menu_muestra_catalogos_solo_al_administrador(self):
        self.login_as(self.admin)
        self.assertContains(self.client.get(reverse('reportes')), URL)
        self.login_as(self.creador)
        self.assertNotContains(self.client.get(reverse('reportes')), URL)


class AccionesCatalogoLugaresTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)

    def _post(self, **datos):
        return self.client.post(URL, datos, follow=True)

    def _mensajes(self, resp):
        return [str(m) for m in resp.context['messages']]

    # ---------- crear ----------
    def test_agregar_lugar_limpia_espacios_y_audita(self):
        self._post(accion='crear', nombre='  Sala   204  -  Edificio A ')
        self.assertTrue(Lugar.objects.filter(nombre='Sala 204 - Edificio A', activo=True).exists())
        self.assertTrue(LogAuditoria.objects.filter(accion='Crear lugar').exists())

    def test_no_acepta_duplicados_aunque_cambien_mayusculas(self):
        resp = self._post(accion='crear', nombre='SALA 1')
        self.assertEqual(Lugar.objects.filter(nombre__iexact='sala 1').count(), 1)
        self.assertTrue(any('Ya existe' in m for m in self._mensajes(resp)))

    def test_no_acepta_nombre_vacio_ni_demasiado_largo(self):
        antes = Lugar.objects.count()
        self._post(accion='crear', nombre='   ')
        self._post(accion='crear', nombre='x' * 201)
        self.assertEqual(Lugar.objects.count(), antes)

    def test_nombre_hostil_se_guarda_limpio_y_se_muestra_escapado(self):
        self._post(accion='crear', nombre='<script>alert(1)</script>\x00')
        self.assertTrue(Lugar.objects.filter(nombre='<script>alert(1)</script>').exists())
        resp = self.client.get(URL)
        self.assertNotContains(resp, '<script>alert(1)</script>')
        self.assertContains(resp, '&lt;script&gt;')

    # ---------- renombrar ----------
    def test_renombrar_actualiza_las_actividades(self):
        lugar = Lugar.objects.get(nombre='Auditorio')
        Actividad.objects.filter(pk=self.actividad.pk).update(lugar='Auditorio')
        resp = self._post(accion='renombrar', lugar_id=lugar.pk, nombre='Auditorio Principal')
        lugar.refresh_from_db()
        self.actividad.refresh_from_db()
        self.assertEqual(lugar.nombre, 'Auditorio Principal')
        self.assertEqual(self.actividad.lugar, 'Auditorio Principal')
        self.assertFalse(Actividad.objects.filter(lugar='Auditorio').exists())
        self.assertTrue(any('1 actividades' in m for m in self._mensajes(resp)))
        log = LogAuditoria.objects.get(accion='Renombrar lugar')
        self.assertEqual(log.cambios_json['nombre'], {'antes': 'Auditorio', 'despues': 'Auditorio Principal'})

    def test_renombrar_a_un_nombre_existente_no_hace_nada(self):
        lugar = Lugar.objects.get(nombre='Auditorio')
        self._post(accion='renombrar', lugar_id=lugar.pk, nombre='sala 1')
        lugar.refresh_from_db()
        self.assertEqual(lugar.nombre, 'Auditorio')

    def test_renombrar_solo_cambiando_mayusculas_esta_permitido(self):
        lugar = Lugar.objects.get(nombre='Auditorio')
        self._post(accion='renombrar', lugar_id=lugar.pk, nombre='AUDITORIO')
        lugar.refresh_from_db()
        self.assertEqual(lugar.nombre, 'AUDITORIO')

    def test_la_pantalla_de_renombrar_muestra_el_formulario(self):
        lugar = Lugar.objects.get(nombre='Auditorio')
        resp = self.client.get(URL, {'editar': lugar.pk})
        self.assertContains(resp, f'id="renombrar-{lugar.pk}"')
        self.assertEqual(self.client.get(URL, {'editar': 'abc'}).status_code, 200)

    # ---------- bloquear / desbloquear ----------
    def test_bloquear_y_desbloquear(self):
        lugar = Lugar.objects.get(nombre='Sala 1')
        self._post(accion='bloquear', lugar_id=lugar.pk)
        lugar.refresh_from_db()
        self.assertFalse(lugar.activo)
        self._post(accion='desbloquear', lugar_id=lugar.pk)
        lugar.refresh_from_db()
        self.assertTrue(lugar.activo)
        self.assertEqual(LogAuditoria.objects.filter(accion__in=['Bloquear lugar', 'Desbloquear lugar']).count(), 2)

    # ---------- eliminar ----------
    def test_eliminar_lugar_sin_actividades(self):
        lugar = Lugar.objects.get(nombre='Sala 1')
        self._post(accion='eliminar', lugar_id=lugar.pk)
        self.assertFalse(Lugar.objects.filter(pk=lugar.pk).exists())
        self.assertTrue(LogAuditoria.objects.filter(accion='Eliminar lugar').exists())

    def test_no_elimina_lugar_en_uso(self):
        lugar = Lugar.objects.get(nombre='Auditorio')
        Actividad.objects.filter(pk=self.actividad.pk).update(lugar='Auditorio')
        resp = self._post(accion='eliminar', lugar_id=lugar.pk)
        self.assertTrue(Lugar.objects.filter(pk=lugar.pk).exists())
        self.assertTrue(any('No se puede eliminar' in m for m in self._mensajes(resp)))

    # ---------- entradas inválidas ----------
    def test_ids_y_acciones_invalidas_no_rompen(self):
        for datos in ({'accion': 'bloquear', 'lugar_id': 'abc'},
                      {'accion': 'bloquear', 'lugar_id': '999999'},
                      {'accion': 'otra', 'lugar_id': Lugar.objects.first().pk},
                      {}):
            with self.subTest(datos=datos):
                self.assertEqual(self._post(**datos).status_code, 200)


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

    def test_numero_vacio_invalido_o_largo_es_rechazado(self):
        for escrito in ('', '12/3', '<b>1', '-12', '12-', "1'2", '12345678901'):
            with self.subTest(escrito=escrito):
                form = ActividadForm(data=self._datos('Sala', escrito))
                self.assertFalse(form.is_valid())
                self.assertIn('lugar_numero', form.errors)

    def test_numero_se_normaliza(self):
        for escrito, guardado in (('a-201', 'A-201'), (' 12 03 ', '1203'), ('2203', '2203')):
            with self.subTest(escrito=escrito):
                form = ActividadForm(data=self._datos('Sala', escrito))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['lugar_numero'], guardado)

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
