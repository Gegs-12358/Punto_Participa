"""
Actividades de varias sesiones: las sesiones de cada actividad, la conversión de los datos que ya
existían y el registro de asistencia por sesión en el escáner (alumnos, invitados y acompañantes).

Correr solo este archivo:
    python manage.py test gestion.tests.escaner.tests_sesiones --noinput
"""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...models import (Acompanante, Actividad, Alumno, Asistencia, AsistenciaSesion, Inscripcion, Invitado,
                       LogAuditoria, Sesion)
from ..base import BaseSistemaTestCase
from ..invitaciones.tests_lista import BaseInvitadosTests, rut

URL = reverse('escaneo')


def con_sesiones(actividad, tramos):
    """Deja la actividad con estas sesiones [(inicio, fin), ...]; empieza con la primera y termina con la última."""
    actividad.sesiones.all().delete()
    for n, (inicio, fin) in enumerate(tramos, start=1):
        Sesion.objects.create(actividad=actividad, numero=n, fecha_inicio=inicio, fecha_fin=fin)
    Actividad.objects.filter(pk=actividad.pk).update(fecha_inicio=tramos[0][0], fecha_fin=tramos[-1][1])
    actividad.refresh_from_db()
    return list(actividad.sesiones.all())


def a_las(dias, hora):
    """Hoy (+/- días) a una hora dada, en hora de Chile."""
    base = timezone.localtime(timezone.now()).replace(hour=hora, minute=0, second=0, microsecond=0)
    return base + timedelta(days=dias)


class SesionesDeLaActividadTests(BaseSistemaTestCase):
    def test_toda_actividad_nueva_tiene_su_sesion_1_con_las_mismas_fechas(self):
        sesiones = list(self.actividad.sesiones.all())
        self.assertEqual(len(sesiones), 1)
        self.assertEqual((sesiones[0].numero, sesiones[0].fecha_inicio, sesiones[0].fecha_fin),
                         (1, self.actividad.fecha_inicio, self.actividad.fecha_fin))
        self.assertFalse(self.actividad.varias_sesiones)

    def test_al_cambiar_la_fecha_de_una_actividad_de_una_sesion_cambia_su_sesion(self):
        nueva = self.actividad.fecha_inicio + timedelta(days=7)
        self.actividad.fecha_inicio, self.actividad.fecha_fin = nueva, nueva + timedelta(hours=2)
        self.actividad.save()
        unica = self.actividad.sesiones.get()
        self.assertEqual((unica.fecha_inicio, unica.fecha_fin), (nueva, nueva + timedelta(hours=2)))

    def test_con_varias_sesiones_guardar_la_actividad_no_las_toca(self):
        tramos = [(a_las(1, 10), a_las(1, 12)), (a_las(8, 10), a_las(8, 12))]
        con_sesiones(self.actividad, tramos)
        self.actividad.titulo = 'Otro título'
        self.actividad.save()
        self.assertEqual([(s.fecha_inicio, s.fecha_fin) for s in self.actividad.sesiones.all()], tramos)
        self.assertTrue(self.actividad.varias_sesiones)

    def test_actividad_creada_sin_pasar_por_save_recibe_su_sesion_al_usarla(self):
        # perf_seed crea actividades con bulk_create, que no pasa por las señales
        ahora = timezone.now()
        [act] = Actividad.objects.bulk_create([Actividad(
            titulo='Masiva en lote', descripcion='d', tipo='MASIVA', lugar='Patio',
            fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=1))])
        self.assertEqual(act.sesiones.count(), 0)
        self.assertEqual(len(act.lista_sesiones()), 1)
        self.assertEqual(act.sesiones.get().fecha_inicio, ahora)


class SesionParaTests(BaseSistemaTestCase):
    """En qué sesión queda un registro según la hora en que se hace."""

    def setUp(self):
        self.s1, self.s2, self.s3, self.s4 = con_sesiones(self.actividad_masiva, [
            (a_las(-7, 10), a_las(-7, 12)),
            (a_las(0, 9), a_las(0, 11)),       # hoy en la mañana
            (a_las(0, 15), a_las(0, 17)),      # hoy en la tarde
            (a_las(7, 10), a_las(7, 12)),
        ])

    def test_reglas(self):
        casos = [
            ('hoy durante la sesión de la mañana', a_las(0, 10), self.s2),
            ('hoy durante la sesión de la tarde', a_las(0, 16), self.s3),
            ('hoy entre las dos, más cerca de la tarde', a_las(0, 14), self.s3),
            ('hoy antes de la primera del día', a_las(0, 7), self.s2),
            ('un día sin sesión: la última que ya empezó', a_las(3, 10), self.s3),
            ('antes de la primera sesión', a_las(-10, 10), self.s1),
            ('después de la última', a_las(10, 10), self.s4),
        ]
        for caso, momento, esperada in casos:
            with self.subTest(caso=caso):
                self.assertEqual(self.actividad_masiva.sesion_para(momento), esperada)
        # "En curso" solo durante una sesión, no entre dos
        self.assertTrue(self.actividad_masiva.sesion_en_curso(a_las(0, 10)))
        self.assertFalse(self.actividad_masiva.sesion_en_curso(a_las(0, 13)))

class RegistrosCreadosPorOtroCaminoTests(BaseSistemaTestCase):
    """Datos de prueba y admin: toda asistencia o ingreso queda también en su sesión."""

    def test_asistencia_creada_directamente_queda_en_la_sesion_de_su_hora(self):
        s1, s2 = con_sesiones(self.actividad_masiva, [(a_las(-7, 10), a_las(-7, 12)), (a_las(0, 9), a_las(0, 23))])
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno, metodo_ingreso='QR',
                                  registrado_por=self.registrador)
        registro = AsistenciaSesion.objects.get(alumno=self.alumno)
        self.assertEqual((registro.sesion, registro.metodo_ingreso, registro.registrado_por),
                         (s2, 'QR', self.registrador))

    def test_ingreso_de_invitado_y_acompanante_queda_en_su_sesion(self):
        ahora = timezone.now()
        act = Actividad.objects.create(titulo='Cena', descripcion='d', tipo='INVITACION', lugar='Salón',
                                       fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=3))
        inv = Invitado.objects.create(actividad=act, alumno=self.alumno, rut='200015509', nombre='Juan',
                                      correo='j@duocuc.cl', ingreso=ahora, metodo_ingreso='RUT')
        ac = Acompanante.objects.create(invitado=inv, rut=rut(18000001), nombre='Marta', ingreso=ahora)
        # La asistencia del alumno en una actividad con invitación no duplica: cuenta la del invitado
        Asistencia.objects.create(actividad=act, alumno=self.alumno, metodo_ingreso='RUT')
        self.assertEqual(AsistenciaSesion.objects.filter(sesion__actividad=act, invitado=inv).count(), 1)
        self.assertEqual(AsistenciaSesion.objects.filter(sesion__actividad=act, acompanante=ac).count(), 1)
        self.assertFalse(AsistenciaSesion.objects.filter(sesion__actividad=act, alumno__isnull=False).exists())
        inv.save()   # volver a guardar no crea otro registro
        self.assertEqual(AsistenciaSesion.objects.filter(invitado=inv).count(), 1)


class ConversionDeDatosExistentesTests(TestCase):
    """La migración 0039 deja cada actividad que ya existía con una sesión y le pasa sus asistencias."""

    def test_convierte_actividades_asistencias_e_ingresos(self):
        ahora = timezone.now()
        [act] = Actividad.objects.bulk_create([Actividad(
            titulo='Antigua', descripcion='d', tipo='MASIVA', lugar='Patio',
            fecha_inicio=ahora - timedelta(days=30), fecha_fin=ahora - timedelta(days=30) + timedelta(hours=2))])
        alumno = Alumno.objects.create(rut='200015509', nombres='Ana', apellidos='Uno', correo='a@duocuc.cl',
                                       carrera='Informática', jornada='Diurno')
        hora = ahora - timedelta(days=30, minutes=-15)
        Asistencia.objects.bulk_create([Asistencia(actividad=act, alumno=alumno, metodo_ingreso='QR')])
        Asistencia.objects.filter(actividad=act).update(fecha_ingreso=hora)
        [inv] = Invitado.objects.bulk_create([Invitado(actividad=act, rut='XK1', nombre='Rosa', correo='r@x.cl',
                                                       ingreso=hora, metodo_ingreso='RUT')])
        Acompanante.objects.bulk_create([Acompanante(actividad=act, invitado=inv, rut='XK2', nombre='Pía',
                                                     ingreso=hora, metodo_ingreso='CODIGO')])
        Acompanante.objects.bulk_create([Acompanante(actividad=act, invitado=inv, rut='XK3', nombre='Sin ingreso')])

        migracion = import_module('gestion.migrations.0039_sesiones')
        migracion.convertir_a_una_sesion(apps, None)

        sesion = act.sesiones.get()
        self.assertEqual((sesion.numero, sesion.fecha_inicio, sesion.fecha_fin), (1, act.fecha_inicio, act.fecha_fin))
        registros = AsistenciaSesion.objects.filter(sesion=sesion)
        self.assertEqual(registros.count(), 3)   # alumno, invitado y un acompañante (el otro no entró)
        alumno_reg = registros.get(alumno=alumno)
        self.assertEqual((alumno_reg.fecha_ingreso, alumno_reg.metodo_ingreso), (hora, 'QR'))
        self.assertEqual(registros.get(invitado=inv).metodo_ingreso, 'RUT')


class EscanerVariasSesionesTests(BaseSistemaTestCase):
    def setUp(self):
        self.s1, self.s2, self.s3 = con_sesiones(self.actividad_masiva, [
            (a_las(-7, 10), a_las(-7, 12)),
            (timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),   # en curso
            (a_las(7, 10), a_las(7, 12)),
        ])
        self.client.force_login(self.registrador)
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_masiva.pk})

    def escanear(self, confirmar=True):
        datos = {'rut': self.alumno.rut}
        if confirmar:
            datos['confirmar'] = 'true'
        return self.client.post(URL, datos)

    def test_registra_en_la_sesion_de_hoy_y_cuenta_una_asistencia_a_la_actividad(self):
        r = self.escanear()
        self.assertEqual(r.status_code, 200)
        self.assertIn('sesión 2 de 3', r.json()['message'])
        self.assertEqual(AsistenciaSesion.objects.get(alumno=self.alumno).sesion, self.s2)
        self.assertEqual(Asistencia.objects.filter(actividad=self.actividad_masiva, alumno=self.alumno).count(), 1)
        self.assertEqual(r.json()['contador']['sesion'], 'Sesión 2 de 3')

    def test_la_misma_sesion_no_se_registra_dos_veces_pero_otra_si(self):
        self.escanear()
        for confirmar in (False, True):
            with self.subTest(etapa='confirmación' if confirmar else 'primera'):
                r = self.escanear(confirmar)
                self.assertEqual(r.status_code, 409)
                self.assertIn('sesión 2 ya fue registrada', r.json()['message'])
        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s1.pk})
        r = self.escanear()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(a.sesion.numero for a in AsistenciaSesion.objects.filter(alumno=self.alumno)), [1, 2])
        self.assertEqual(Asistencia.objects.filter(actividad=self.actividad_masiva, alumno=self.alumno).count(), 1)
        self.assertTrue(LogAuditoria.objects.filter(accion='Cambiar sesión').exists())

    def test_el_contador_es_de_la_sesion_elegida(self):
        self.escanear()
        self.assertEqual(self.client.get(reverse('escaneo_contador')).json()['total'], 1)
        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s3.pk})
        datos = self.client.get(reverse('escaneo_contador')).json()
        self.assertEqual((datos['total'], datos['sesion']), (0, 'Sesión 3 de 3'))

    def test_la_pantalla_muestra_la_sesion_y_permite_cambiarla(self):
        r = self.client.get(URL)
        self.assertContains(r, 'sesión 2 de 3')
        self.assertContains(r, 'name="cambiar_sesion"')
        self.assertContains(r, 'TOTAL EN ESTA SESIÓN')
        self.assertEqual(r.context['sesion_escaneo'], self.s2)

    def test_no_acepta_una_sesion_de_otra_actividad(self):
        otra = self.actividad.sesiones.get()
        r = self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': otra.pk}, follow=True)
        self.assertContains(r, 'Esa sesión no es de la actividad del turno')
        self.assertEqual(self.client.get(URL).context['sesion_escaneo'], self.s2)

    def test_cambiar_de_actividad_olvida_la_sesion_elegida(self):
        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s1.pk})
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad.pk})
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_masiva.pk})
        self.assertEqual(self.client.get(URL).context['sesion_escaneo'], self.s2)

    def test_el_resumen_del_turno_suma_todas_las_sesiones(self):
        self.escanear()
        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s1.pk})
        self.escanear()
        r = self.client.post(URL, {'finalizar_turno': '1'}, follow=True)
        self.assertContains(r, 'registraste 2 asistencias')

    def test_en_un_taller_cada_sesion_exige_la_inscripcion(self):
        con_sesiones(self.actividad, [(a_las(-7, 10), a_las(-7, 12)),
                                      (timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1))])
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad.pk})
        self.assertEqual(self.escanear(confirmar=False).status_code, 403)
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.assertEqual(self.escanear().status_code, 200)

    def test_una_actividad_de_una_sesion_se_ve_y_funciona_como_siempre(self):
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad.pk})
        r = self.client.get(URL)
        self.assertNotContains(r, 'name="cambiar_sesion"')
        self.assertContains(r, 'TOTAL EN LA ACTIVIDAD')
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.assertEqual(self.escanear().json()['message'], f'Asistencia registrada para {self.alumno.nombres} '
                                                             f'{self.alumno.apellidos}.')
        self.assertEqual(self.escanear().json()['message'], 'La asistencia ya fue registrada anteriormente.')


class EscanerInvitacionVariasSesionesTests(BaseInvitadosTests):
    def setUp(self):
        self.act = self.actividad_invitacion(acompanantes_por_invitado=1)
        self.s1, self.s2 = con_sesiones(self.act, [
            (a_las(-7, 10), a_las(-7, 12)),
            (timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ])
        self.juan = Invitado.objects.create(actividad=self.act, alumno=self.alumno, rut='200015509',
                                            nombre='Juan Pérez', correo='juan@duocuc.cl', estado='CONFIRMADO')
        self.acomp = Acompanante.objects.create(invitado=self.juan, rut=rut(18000001), nombre='Marta Pérez')
        self.client.force_login(self.registrador)
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.act.pk})

    def escanear(self, doc):
        return self.client.post(URL, {'rut': doc, 'confirmar': 'true'})

    def test_invitado_y_acompanante_entran_una_vez_por_sesion(self):
        for doc, campo in (('200015509', 'invitado'), (self.acomp.rut, 'acompanante')):
            with self.subTest(persona=campo):
                self.assertEqual(self.escanear(doc).status_code, 200)
                r = self.escanear(doc)
                self.assertEqual(r.status_code, 409)
                self.assertIn('ya ingresó a la sesión 2', r.json()['message'])
        primer_ingreso = Invitado.objects.get(pk=self.juan.pk).ingreso

        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s1.pk})
        self.assertEqual(self.escanear('200015509').status_code, 200)
        self.assertEqual(AsistenciaSesion.objects.filter(invitado=self.juan).count(), 2)
        # El primer ingreso a la actividad no cambia al entrar a otra sesión
        self.assertEqual(Invitado.objects.get(pk=self.juan.pk).ingreso, primer_ingreso)
        self.assertEqual(Asistencia.objects.filter(actividad=self.act, alumno=self.alumno).count(), 1)

    def test_el_contador_cuenta_los_ingresos_de_la_sesion(self):
        datos = self.escanear('200015509').json()
        self.assertEqual((datos['contador']['total'], datos['contador']['sesion']), (1, 'Sesión 2 de 2'))
        self.client.post(URL, {'cambiar_sesion': '1', 'sesion_id': self.s1.pk})
        self.assertEqual(self.client.get(reverse('escaneo_contador')).json()['total'], 0)
