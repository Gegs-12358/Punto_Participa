"""
"Foto" académica en inscripciones y asistencias (P1).

Cada inscripción y asistencia guarda la carrera, la escuela y la jornada que el alumno
tenía en ese momento. Así el historial de participación no cambia cuando el alumno se
cambia de carrera o llega una nómina nueva.

- Se llena sola al crear (también desde la inscripción pública y el escáner).
- No cambia si después cambia el alumno ni al volver a guardar el registro.
- Renombrar una carrera o escuela en Catálogos es corregir: la foto se corrige igual.
  "Es otra carrera" (reemplazar) no la toca.
- La migración 0030 llena los registros que ya existían.
"""
import importlib

from django.apps import apps as django_apps
from django.urls import reverse

from .models import Alumno, Asistencia, Carrera, Escuela, Inscripcion, foto_academica
from .tests_integrales import BaseSistemaTestCase

INFORMATICA = 'Escuela de Informática y Telecomunicaciones'
DISENO = 'Escuela de Diseño'

migracion = importlib.import_module('gestion.migrations.0030_foto_academica')


class FotoAlCrearTests(BaseSistemaTestCase):
    def test_inscripcion_guarda_carrera_escuela_y_jornada(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        insc.refresh_from_db()
        self.assertEqual(insc.carrera, 'Ingeniería en Informática')
        self.assertEqual(insc.escuela, INFORMATICA)
        self.assertEqual(insc.jornada, 'Diurno')

    def test_asistencia_guarda_carrera_escuela_y_jornada(self):
        asis = Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno_pasaporte,
                                         metodo_ingreso='RUT')
        asis.refresh_from_db()
        self.assertEqual((asis.carrera, asis.escuela, asis.jornada),
                         ('Diseño Gráfico', DISENO, 'Vespertino'))

    def test_escuela_se_busca_sin_distinguir_mayusculas_ni_espacios(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(carrera='INGENIERÍA EN INFORMÁTICA')
        self.alumno.refresh_from_db()
        self.assertEqual(foto_academica(self.alumno)['escuela'], INFORMATICA)

    def test_carrera_fuera_del_catalogo_queda_sin_escuela(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(carrera='Carrera que no está')
        insc = Inscripcion.objects.create(actividad=self.actividad,
                                          alumno=Alumno.objects.get(pk=self.alumno.pk))
        self.assertEqual(insc.carrera, 'Carrera que no está')
        self.assertEqual(insc.escuela, '')

    def test_valores_dados_al_crear_se_respetan(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno,
                                          carrera='Otra', escuela='Escuela X', jornada='Online')
        insc.refresh_from_db()
        self.assertEqual((insc.carrera, insc.escuela, insc.jornada), ('Otra', 'Escuela X', 'Online'))


class FotoNoCambiaTests(BaseSistemaTestCase):
    def test_cambio_de_carrera_del_alumno_no_cambia_el_historial(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        asis = Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno,
                                         metodo_ingreso='RUT')
        self.alumno.carrera = self.carrera_2.nombre
        self.alumno.jornada = 'Vespertino'
        self.alumno.save()
        for registro in (insc, asis):
            registro.refresh_from_db()
            self.assertEqual(registro.carrera, 'Ingeniería en Informática')
            self.assertEqual(registro.escuela, INFORMATICA)
            self.assertEqual(registro.jornada, 'Diurno')
        # Un registro NUEVO sí toma los datos actuales
        nueva = Inscripcion.objects.create(actividad=self.actividad_otro, alumno=self.alumno)
        self.assertEqual((nueva.carrera, nueva.escuela), ('Diseño Gráfico', DISENO))

    def test_volver_a_guardar_no_refresca_la_foto(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Alumno.objects.filter(pk=self.alumno.pk).update(carrera=self.carrera_2.nombre)
        insc = Inscripcion.objects.get(pk=insc.pk)
        insc.estado = 'CANCELADA'
        insc.save()
        insc.refresh_from_db()
        self.assertEqual(insc.carrera, 'Ingeniería en Informática')


class FotoDesdeLasPantallasTests(BaseSistemaTestCase):
    def test_inscripcion_publica_guarda_la_foto(self):
        self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]),
                         {'rut': '20.001.550-9', 'acepta_politica': 'on'})
        insc = Inscripcion.objects.get(actividad=self.actividad, alumno=self.alumno)
        self.assertEqual((insc.carrera, insc.escuela, insc.jornada),
                         ('Ingeniería en Informática', INFORMATICA, 'Diurno'))

    def test_escaner_guarda_la_foto(self):
        self.seleccionar_actividad()
        url = reverse('escaneo')
        self.client.post(url, {'rut': '200015509'})
        resp = self.client.post(url, {'rut': '200015509', 'confirmar': 'true'})
        self.assertEqual(resp.status_code, 200)
        asis = Asistencia.objects.get(actividad=self.actividad_masiva, alumno=self.alumno)
        self.assertEqual((asis.carrera, asis.escuela, asis.jornada),
                         ('Ingeniería en Informática', INFORMATICA, 'Diurno'))


class FotoYCatalogosTests(BaseSistemaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.esc_informatica = Escuela.objects.create(nombre=INFORMATICA)
        Escuela.objects.create(nombre=DISENO)

    def setUp(self):
        self.login_as(self.admin)
        self.insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.asis = Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno,
                                              metodo_ingreso='RUT')

    def _fotos(self):
        self.insc.refresh_from_db()
        self.asis.refresh_from_db()
        return {(r.carrera, r.escuela) for r in (self.insc, self.asis)}

    def test_corregir_nombre_de_carrera_corrige_la_foto(self):
        self.client.post(reverse('catalogo_carreras'), {
            'accion': 'editar', 'carrera_id': self.carrera.pk,
            'nombre': 'Ingeniería Informática', 'escuela': INFORMATICA, 'confirmado': '1'})
        self.assertEqual(self._fotos(), {('Ingeniería Informática', INFORMATICA)})

    def test_cambiar_la_escuela_de_una_carrera_corrige_la_foto(self):
        self.client.post(reverse('catalogo_carreras'), {
            'accion': 'editar', 'carrera_id': self.carrera.pk,
            'nombre': self.carrera.nombre, 'escuela': DISENO})
        self.assertEqual(self._fotos(), {('Ingeniería en Informática', DISENO)})

    def test_otra_carrera_no_toca_la_foto(self):
        self.client.post(reverse('catalogo_carreras'), {
            'accion': 'reemplazar', 'carrera_id': self.carrera.pk,
            'nombre': 'Ingeniería en Informática 2027', 'escuela': INFORMATICA})
        self.assertEqual(self._fotos(), {('Ingeniería en Informática', INFORMATICA)})

    def test_renombrar_escuela_corrige_la_foto(self):
        self.client.post(reverse('catalogo_escuelas'), {
            'accion': 'renombrar', 'escuela_id': self.esc_informatica.pk,
            'nombre': 'Escuela de Informática'})
        self.assertEqual(self._fotos(), {('Ingeniería en Informática', 'Escuela de Informática')})

    def test_pide_confirmacion_si_hay_historial_aunque_no_queden_alumnos(self):
        # El alumno ya se cambió de carrera, pero su historial sigue con la antigua
        Alumno.objects.filter(pk=self.alumno.pk).update(carrera=self.carrera_2.nombre)
        resp = self.client.post(reverse('catalogo_carreras'), {
            'accion': 'editar', 'carrera_id': self.carrera.pk,
            'nombre': 'Ingeniería Informática', 'escuela': INFORMATICA})
        self.assertEqual(resp.status_code, 200)
        conf = resp.context['confirmacion']
        self.assertEqual((conf['alumnos'], conf['registros']), (0, 2))
        self.assertContains(resp, '2 registros de participación')
        self.carrera.refresh_from_db()
        self.assertEqual(self.carrera.nombre, 'Ingeniería en Informática')


class MigracionFotoTests(BaseSistemaTestCase):
    def test_llena_los_registros_que_ya_existian(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        asis = Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno_pasaporte,
                                         metodo_ingreso='RUT')
        sin_carrera = Alumno.objects.create(rut='11111111-1', nombres='Sin', apellidos='Catálogo',
                                            correo='sin@example.com', carrera='Carrera rara',
                                            jornada='Diurno')
        insc_rara = Inscripcion.objects.create(actividad=self.actividad_otro, alumno=sin_carrera)
        # Como estaban antes de la migración: sin foto
        Inscripcion.objects.update(carrera='', escuela='', jornada='')
        Asistencia.objects.update(carrera='', escuela='', jornada='')

        migracion.llenar_fotos(django_apps, None)

        insc.refresh_from_db()
        asis.refresh_from_db()
        insc_rara.refresh_from_db()
        self.assertEqual((insc.carrera, insc.escuela, insc.jornada),
                         ('Ingeniería en Informática', INFORMATICA, 'Diurno'))
        self.assertEqual((asis.carrera, asis.escuela, asis.jornada),
                         ('Diseño Gráfico', DISENO, 'Vespertino'))
        self.assertEqual((insc_rara.carrera, insc_rara.escuela), ('Carrera rara', ''))

    def test_escuela_sin_distinguir_mayusculas(self):
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Inscripcion.objects.update(carrera='', escuela='', jornada='')
        Alumno.objects.filter(pk=self.alumno.pk).update(carrera='  ingeniería en informática ')
        migracion.llenar_fotos(django_apps, None)
        insc.refresh_from_db()
        self.assertEqual(insc.escuela, INFORMATICA)

    def test_carrera_del_catalogo_sin_escuela(self):
        Carrera.objects.filter(pk=self.carrera.pk).update(escuela=None)
        insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Inscripcion.objects.update(carrera='', escuela='', jornada='')
        migracion.llenar_fotos(django_apps, None)
        insc.refresh_from_db()
        self.assertEqual((insc.carrera, insc.escuela), ('Ingeniería en Informática', ''))
