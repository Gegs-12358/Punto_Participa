"""
Catálogo de escuelas y carreras, colores de las escuelas y su migración.

Correr solo este archivo:
    python manage.py test gestion.tests.catalogos.tests_escuelas_carreras --noinput
"""
from datetime import timedelta

import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Carrera, Escuela, LogAuditoria
from ...views.comun import _colores_por_carrera, color_para_escuela, COLOR_POR_ESCUELA, colores_escuelas
from ..base import BaseSistemaTestCase, SilenciarRegistros


URL_ESCUELAS = reverse('catalogo_escuelas')


URL_CARRERAS = reverse('catalogo_carreras')


INFORMATICA = 'Escuela de Informática y Telecomunicaciones'


DISENO = 'Escuela de Diseño'


migracion_escuelas = importlib.import_module('gestion.migrations.0028_escuela_carrera_activo')


class BaseCatalogoTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Las carreras de BaseSistemaTestCase ya traen estas escuelas
        cls.esc_informatica = Escuela.objects.create(nombre=INFORMATICA)
        cls.esc_diseno = Escuela.objects.create(nombre=DISENO)

    def setUp(self):
        self.login_as(self.admin)

    def _mensajes(self, resp):
        return [str(m) for m in resp.context['messages']]


class AccesoCatalogosTests(BaseCatalogoTests):
    def test_solo_el_administrador_entra(self):
        for usuario in (self.creador, self.registrador):
            with self.subTest(usuario=usuario.username):
                self.login_as(usuario)
                for url in (URL_ESCUELAS, URL_CARRERAS):
                    self.assertEqual(self.client.get(url).status_code, 302)
                self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'Escuela intrusa'})
                self.assertFalse(Escuela.objects.filter(nombre='Escuela intrusa').exists())

    def test_las_tres_pestanas_se_muestran(self):
        resp = self.client.get(URL_CARRERAS)
        for url in (reverse('catalogo_lugares'), URL_ESCUELAS, URL_CARRERAS):
            self.assertContains(resp, f'href="{url}"')
        # Mismo estilo que las pestañas de Reportes, con la de Carreras marcada como actual
        self.assertContains(resp, 'tabs--vistas')
        self.assertContains(resp, f'href="{URL_CARRERAS}" class="tab-button tab-vista active" aria-current="page"')
        self.assertContains(resp, '<span class="tab-vista__titulo">Carreras</span>')


class EscuelasTests(BaseCatalogoTests):
    def test_lista_con_cantidad_de_carreras(self):
        resp = self.client.get(URL_ESCUELAS)
        conteo = {e.nombre: e.total_carreras for e in resp.context['escuelas']}
        self.assertEqual(conteo[INFORMATICA], 1)

    def test_agregar_y_no_duplicar(self):
        self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': '  Escuela   de Salud '})
        self.assertTrue(Escuela.objects.filter(nombre='Escuela de Salud').exists())
        resp = self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'ESCUELA DE SALUD'}, follow=True)
        self.assertEqual(Escuela.objects.filter(nombre__iexact='escuela de salud').count(), 1)
        self.assertTrue(any('Ya existe una escuela llamada' in m for m in self._mensajes(resp)))

    def test_renombrar_actualiza_sus_carreras(self):
        self.client.post(URL_ESCUELAS, {'accion': 'renombrar', 'escuela_id': self.esc_informatica.pk,
                                        'nombre': 'Escuela de Informática'})
        self.carrera.refresh_from_db()
        self.assertEqual(self.carrera.escuela, 'Escuela de Informática')
        self.assertTrue(LogAuditoria.objects.filter(accion='Renombrar escuela').exists())

    def test_bloquear_oculta_sus_carreras_en_el_formulario(self):
        self.client.post(URL_ESCUELAS, {'accion': 'bloquear', 'escuela_id': self.esc_diseno.pk})
        self.esc_diseno.refresh_from_db()
        self.assertFalse(self.esc_diseno.activo)
        ofrecidas = ActividadForm().fields['carreras'].queryset
        self.assertIn(self.carrera, ofrecidas)
        self.assertNotIn(self.carrera_2, ofrecidas)

    def test_no_elimina_escuela_con_carreras(self):
        resp = self.client.post(URL_ESCUELAS, {'accion': 'eliminar', 'escuela_id': self.esc_diseno.pk}, follow=True)
        self.assertTrue(Escuela.objects.filter(pk=self.esc_diseno.pk).exists())
        self.assertTrue(any('No se puede eliminar' in m for m in self._mensajes(resp)))

    def test_elimina_escuela_sin_carreras(self):
        vacia = Escuela.objects.create(nombre='Escuela vacía')
        self.client.post(URL_ESCUELAS, {'accion': 'eliminar', 'escuela_id': vacia.pk})
        self.assertFalse(Escuela.objects.filter(pk=vacia.pk).exists())


class CarrerasTests(BaseCatalogoTests):
    def test_lista_con_alumnos_y_actividades(self):
        resp = self.client.get(URL_CARRERAS)
        fila = {c.nombre: c for c in resp.context['carreras']}[self.carrera.nombre]
        self.assertEqual(fila.total_alumnos, 1)
        self.assertEqual(fila.total_actividades, 3)

    def test_filtrar_por_escuela(self):
        resp = self.client.get(URL_CARRERAS, {'escuela': DISENO})
        self.assertEqual([c.nombre for c in resp.context['carreras']], [self.carrera_2.nombre])

    def test_agregar_exige_escuela_activa(self):
        self.client.post(URL_CARRERAS, {'accion': 'crear', 'nombre': 'Analista Programador',
                                        'escuela': INFORMATICA})
        self.assertTrue(Carrera.objects.filter(nombre='Analista Programador', escuela=INFORMATICA).exists())

        for escuela in ('', 'Escuela inventada'):
            with self.subTest(escuela=escuela):
                self.client.post(URL_CARRERAS, {'accion': 'crear', 'nombre': 'Otra carrera', 'escuela': escuela})
                self.assertFalse(Carrera.objects.filter(nombre='Otra carrera').exists())

        self.esc_diseno.activo = False
        self.esc_diseno.save()
        self.client.post(URL_CARRERAS, {'accion': 'crear', 'nombre': 'Ilustración', 'escuela': DISENO})
        self.assertFalse(Carrera.objects.filter(nombre='Ilustración').exists())

    def test_cambiar_solo_la_escuela_no_pide_confirmacion(self):
        resp = self.client.post(URL_CARRERAS, {'accion': 'editar', 'carrera_id': self.carrera.pk,
                                               'nombre': self.carrera.nombre, 'escuela': DISENO})
        self.assertEqual(resp.status_code, 302)
        self.carrera.refresh_from_db()
        self.assertEqual(self.carrera.escuela, DISENO)

    def test_renombrar_sin_alumnos_no_pide_confirmacion(self):
        sin_alumnos = Carrera.objects.create(nombre='Carrera vacía', escuela=INFORMATICA)
        resp = self.client.post(URL_CARRERAS, {'accion': 'editar', 'carrera_id': sin_alumnos.pk,
                                               'nombre': 'Carrera corregida', 'escuela': INFORMATICA})
        self.assertEqual(resp.status_code, 302)
        sin_alumnos.refresh_from_db()
        self.assertEqual(sin_alumnos.nombre, 'Carrera corregida')

    def test_renombrar_con_alumnos_pide_confirmacion_y_no_cambia_nada(self):
        anterior = self.carrera.nombre
        resp = self.client.post(URL_CARRERAS, {'accion': 'editar', 'carrera_id': self.carrera.pk,
                                               'nombre': 'Ingeniería Informática', 'escuela': INFORMATICA})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['confirmacion']['alumnos'], 1)
        self.assertContains(resp, 'Es la misma: corregir el nombre en todas partes')
        self.assertContains(resp, 'Es distinta: crear')
        self.carrera.refresh_from_db()
        self.alumno.refresh_from_db()
        self.assertEqual(self.carrera.nombre, anterior)
        self.assertEqual(self.alumno.carrera, anterior)

    def test_confirmar_misma_carrera_corrige_alumnos_y_actividades(self):
        self.client.post(URL_CARRERAS, {'accion': 'editar', 'carrera_id': self.carrera.pk,
                                        'nombre': 'Ingeniería Informática', 'escuela': INFORMATICA,
                                        'confirmado': '1'})
        self.carrera.refresh_from_db()
        self.alumno.refresh_from_db()
        self.assertEqual(self.carrera.nombre, 'Ingeniería Informática')
        self.assertEqual(self.alumno.carrera, 'Ingeniería Informática')
        # Las actividades guardan el enlace a la carrera: siguen el cambio solas
        self.assertIn(self.carrera, self.actividad.carreras.all())
        log = LogAuditoria.objects.get(accion='Editar carrera')
        self.assertEqual(log.cambios_json['nombre']['despues'], 'Ingeniería Informática')

    def test_carrera_distinta_crea_nueva_y_bloquea_antigua_sin_tocar_historial(self):
        anterior = self.carrera.nombre
        resp = self.client.post(URL_CARRERAS, {'accion': 'reemplazar', 'carrera_id': self.carrera.pk,
                                               'nombre': 'Ingeniería en Informática 2027', 'escuela': INFORMATICA},
                                follow=True)
        nueva = Carrera.objects.get(nombre='Ingeniería en Informática 2027')
        self.carrera.refresh_from_db()
        self.alumno.refresh_from_db()
        self.assertTrue(nueva.activo)
        self.assertFalse(self.carrera.activo)
        self.assertEqual(self.carrera.nombre, anterior)
        self.assertEqual(self.alumno.carrera, anterior)
        self.assertIn(self.carrera, self.actividad.carreras.all())
        self.assertTrue(LogAuditoria.objects.filter(accion='Reemplazar carrera').exists())
        self.assertTrue(any('el historial no cambia' in m for m in self._mensajes(resp)))

    def test_no_renombra_a_un_nombre_existente(self):
        self.client.post(URL_CARRERAS, {'accion': 'editar', 'carrera_id': self.carrera.pk,
                                        'nombre': self.carrera_2.nombre.upper(), 'escuela': INFORMATICA,
                                        'confirmado': '1'})
        self.carrera.refresh_from_db()
        self.assertEqual(self.carrera.nombre, 'Ingeniería en Informática')

    def test_bloquear_la_saca_del_formulario_pero_la_actividad_la_conserva(self):
        self.client.post(URL_CARRERAS, {'accion': 'bloquear', 'carrera_id': self.carrera.pk})
        self.carrera.refresh_from_db()
        self.assertFalse(self.carrera.activo)
        self.assertNotIn(self.carrera, ActividadForm().fields['carreras'].queryset)
        self.assertIn(self.carrera, ActividadForm(instance=self.actividad).fields['carreras'].queryset)

    def test_no_elimina_carrera_en_uso(self):
        resp = self.client.post(URL_CARRERAS, {'accion': 'eliminar', 'carrera_id': self.carrera.pk}, follow=True)
        self.assertTrue(Carrera.objects.filter(pk=self.carrera.pk).exists())
        self.assertTrue(any('No se puede eliminar' in m for m in self._mensajes(resp)))

    def test_elimina_carrera_sin_uso(self):
        vacia = Carrera.objects.create(nombre='Carrera sin uso', escuela=INFORMATICA)
        self.client.post(URL_CARRERAS, {'accion': 'eliminar', 'carrera_id': vacia.pk})
        self.assertFalse(Carrera.objects.filter(pk=vacia.pk).exists())

    def test_entradas_invalidas_no_rompen(self):
        for url, datos in ((URL_CARRERAS, {'accion': 'editar', 'carrera_id': 'abc'}),
                           (URL_CARRERAS, {'accion': 'otra', 'carrera_id': self.carrera.pk}),
                           (URL_CARRERAS, {'accion': 'editar', 'carrera_id': self.carrera.pk,
                                           'nombre': '<script>x</script>', 'escuela': '\x00'}),
                           (URL_ESCUELAS, {'accion': 'bloquear', 'escuela_id': '999999'}),
                           (URL_ESCUELAS, {})):
            with self.subTest(datos=datos):
                self.assertIn(self.client.post(url, datos).status_code, (200, 302))
        self.carrera.refresh_from_db()
        self.assertEqual(self.carrera.nombre, 'Ingeniería en Informática')


class FormularioCarrerasActivasTests(BaseCatalogoTests):
    def test_actividad_nueva_no_acepta_carrera_bloqueada(self):
        self.carrera_2.activo = False
        self.carrera_2.save()
        inicio = timezone.localtime(timezone.now() + timedelta(days=3))
        form = ActividadForm(data={
            'titulo': 'Charla', 'descripcion': 'x', 'tipo': 'MASIVA', 'lugar': 'Sala 1',
            'fecha_inicio_fecha': inicio.strftime('%Y-%m-%d'), 'fecha_inicio_hora': inicio.strftime('%H:%M'),
            'fecha_fin_fecha': inicio.strftime('%Y-%m-%d'),
            'fecha_fin_hora': (inicio + timedelta(hours=1)).strftime('%H:%M'),
            'carreras': [self.carrera_2.pk], 'jornadas': [self.jornada.pk],
        })
        self.assertFalse(form.is_valid())
        self.assertIn('carreras', form.errors)


class MigracionEscuelasTests(BaseSistemaTestCase):
    def test_pasa_las_escuelas_al_catalogo_y_unifica_variantes(self):
        Escuela.objects.all().delete()
        Carrera.objects.create(nombre='Carrera A', escuela='  escuela de diseño ')
        Carrera.objects.create(nombre='Carrera B', escuela='Escuela   de Diseño')
        migracion_escuelas.poblar_escuelas(django_apps, None)
        self.assertEqual(sorted(Escuela.objects.values_list('nombre', flat=True)), [DISENO, INFORMATICA])
        self.assertEqual(Carrera.objects.filter(escuela=DISENO).count(), 3)
        migracion_escuelas.poblar_escuelas(django_apps, None)
        self.assertEqual(Escuela.objects.count(), 2)


migracion_color = importlib.import_module('gestion.migrations.0029_escuela_color')


class ColorEscuelaTests(TestCase):
    def test_usa_el_color_del_catalogo_antes_que_el_oficial(self):
        Escuela.objects.create(nombre=INFORMATICA, color='#123456')
        self.assertEqual(color_para_escuela(INFORMATICA), '#123456')

    def test_sin_color_en_catalogo_usa_el_oficial_y_si_no_gris(self):
        Escuela.objects.create(nombre=INFORMATICA)
        self.assertEqual(color_para_escuela(INFORMATICA), COLOR_POR_ESCUELA[INFORMATICA])
        Escuela.objects.create(nombre='Escuela Nueva')
        self.assertEqual(color_para_escuela('Escuela Nueva'), '#666666')
        self.assertEqual(color_para_escuela(None), '#666666')

    def test_mapa_precalculado_evita_consultas_en_ciclos(self):
        Escuela.objects.create(nombre='Escuela A', color='#AAAAAA')
        mapa = colores_escuelas()
        with self.assertNumQueries(0):
            self.assertEqual(color_para_escuela('Escuela A', mapa), '#AAAAAA')

    def test_colores_por_carrera_hace_una_sola_consulta(self):
        Escuela.objects.create(nombre='Escuela A', color='#AAAAAA')

        class C:
            escuela = 'Escuela A'
        cache = {'carrera a': C(), 'carrera b': C()}
        items = [{'alumno__carrera': 'Carrera A'}, {'alumno__carrera': 'Carrera B'},
                 {'alumno__carrera': None}]
        with self.assertNumQueries(1):
            self.assertEqual(_colores_por_carrera(items, cache), ['#AAAAAA', '#AAAAAA', '#666666'])

    def test_el_color_solo_acepta_formato_hexadecimal(self):
        for malo in ('red', '#12345', '#GGGGGG', 'red;}x'):
            with self.subTest(color=malo):
                with self.assertRaises(ValidationError):
                    Escuela(nombre='X', color=malo).full_clean()
        Escuela(nombre='X', color='#a1B2c3').full_clean()

    def test_la_migracion_pone_los_colores_oficiales(self):
        Escuela.objects.create(nombre=INFORMATICA)
        Escuela.objects.create(nombre='Escuela desconocida')
        Escuela.objects.create(nombre='Escuela de Diseño', color='#000000')   # ya elegido: no se toca
        migracion_color.poner_colores(django_apps, None)
        colores = dict(Escuela.objects.values_list('nombre', 'color'))
        self.assertEqual(colores[INFORMATICA], '#307FE2')
        self.assertEqual(colores['Escuela desconocida'], '')
        self.assertEqual(colores['Escuela de Diseño'], '#000000')


class CatalogoColorEscuelaTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)
        self.escuela = Escuela.objects.create(nombre=INFORMATICA, color='#307FE2')

    def test_agregar_con_color(self):
        self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'Escuela de Salud', 'color': '#5bc2e7'})
        self.assertEqual(Escuela.objects.get(nombre='Escuela de Salud').color, '#5BC2E7')

    def test_color_invalido_se_ignora(self):
        self.client.post(URL_ESCUELAS, {'accion': 'crear', 'nombre': 'Escuela de Salud', 'color': 'javascript:x'})
        self.assertEqual(Escuela.objects.get(nombre='Escuela de Salud').color, '')

    def test_cambiar_solo_el_color(self):
        self.client.post(URL_ESCUELAS, {'accion': 'renombrar', 'escuela_id': self.escuela.pk,
                                        'nombre': INFORMATICA, 'color': '#000000'})
        self.escuela.refresh_from_db()
        self.assertEqual(self.escuela.color, '#000000')
        log = LogAuditoria.objects.get(accion='Cambiar color de escuela')
        self.assertEqual(log.cambios_json['color'], {'antes': '#307FE2', 'despues': '#000000'})

    def test_renombrar_y_cambiar_color_a_la_vez(self):
        self.client.post(URL_ESCUELAS, {'accion': 'renombrar', 'escuela_id': self.escuela.pk,
                                        'nombre': 'Escuela de Informática', 'color': '#111111'})
        self.escuela.refresh_from_db()
        self.carrera.refresh_from_db()
        self.assertEqual((self.escuela.nombre, self.escuela.color), ('Escuela de Informática', '#111111'))
        self.assertEqual(self.carrera.escuela, 'Escuela de Informática')
        # El color sigue a la escuela aunque cambie el nombre
        self.assertEqual(color_para_escuela('Escuela de Informática'), '#111111')

    def test_la_pantalla_muestra_el_color_y_sugiere_uno_libre(self):
        resp = self.client.get(URL_ESCUELAS)
        self.assertContains(resp, 'background: #307FE2')
        self.assertNotEqual(resp.context['color_sugerido'], '#307FE2')


class ColorParaEscuelaTests(SilenciarRegistros, TestCase):
    """color_para_escuela sin catálogo: color oficial, o gris si la escuela no se conoce."""

    def test_color_oficial_o_gris(self):
        casos = [
            ('Escuela de Informática y Telecomunicaciones', '#307FE2'),
            ('  Escuela de Construcción  ', '#E87722'),   # espacios de más
            ('Escuela Inexistente', '#666666'),
            ('', '#666666'),
            (None, '#666666'),
        ]
        for escuela, color in casos:
            with self.subTest(escuela=escuela):
                self.assertEqual(color_para_escuela(escuela), color)


class CatalogosSinCambiosYRepetidosTests(BaseCatalogoTests):
    """Guardar sin cambiar nada no deja registro; un nombre repetido se rechaza; una acción desconocida avisa."""

    def post(self, url, **datos):
        return self.client.post(url, datos, follow=True)

    def test_sin_cambios_no_queda_nada_en_la_auditoria(self):
        from ...models import Lugar
        lugar = Lugar.objects.get(nombre='Sala 1')
        antes = LogAuditoria.objects.count()
        self.post(reverse('catalogo_lugares'), accion='renombrar', lugar_id=lugar.pk, nombre='Sala 1')
        self.post(URL_ESCUELAS, accion='renombrar', escuela_id=self.esc_diseno.pk, nombre=DISENO,
                  color=self.esc_diseno.color)
        carrera = self.carrera
        self.post(URL_CARRERAS, accion='editar', carrera_id=carrera.pk, nombre=carrera.nombre,
                  escuela=carrera.escuela)
        self.assertEqual(LogAuditoria.objects.count(), antes)

    def test_nombres_repetidos_se_rechazan(self):
        casos = [
            ('escuela renombrada como otra', URL_ESCUELAS,
             {'accion': 'renombrar', 'escuela_id': self.esc_diseno.pk, 'nombre': INFORMATICA}),
            ('carrera nueva con un nombre que ya existe', URL_CARRERAS,
             {'accion': 'crear', 'nombre': self.carrera.nombre, 'escuela': INFORMATICA}),
            ('carrera reemplazada por una que ya existe', URL_CARRERAS,
             {'accion': 'reemplazar', 'carrera_id': self.carrera.pk, 'nombre': self.carrera_2.nombre,
              'escuela': INFORMATICA}),
        ]
        for caso, url, datos in casos:
            with self.subTest(caso=caso):
                mensajes = self._mensajes(self.post(url, **datos))
                self.assertTrue(any('Ya existe' in m for m in mensajes), mensajes)
        self.assertEqual(Escuela.objects.get(pk=self.esc_diseno.pk).nombre, DISENO)
        self.assertTrue(Carrera.objects.get(pk=self.carrera.pk).activo)

    def test_accion_desconocida_en_escuelas(self):
        mensajes = self._mensajes(self.post(URL_ESCUELAS, accion='otra', escuela_id=self.esc_diseno.pk))
        self.assertIn('Acción no válida.', mensajes)

