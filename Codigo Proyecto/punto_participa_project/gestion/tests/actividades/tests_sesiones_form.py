"""
Actividades de varias sesiones en el formulario: agregar, cambiar y quitar sesiones, porcentaje mínimo,
inscripción hasta el fin de la primera sesión y cómo se muestran las sesiones. Incluye el arreglo de la
hora al editar (se mostraba en UTC, 3 horas corrida).

Correr solo este archivo:
    python manage.py test gestion.tests.actividades.tests_sesiones_form --noinput
"""
from datetime import timedelta

from django.core import mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Actividad, AsistenciaSesion, Inscripcion, Sesion
from ..base import BaseSistemaTestCase

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


def dia(dias, hora=10, minuto=0):
    base = timezone.localtime(timezone.now()).replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return base + timedelta(days=dias)


class BaseSesionesForm(BaseSistemaTestCase):
    def datos(self, inicio=None, fin=None, sesiones=(), **cambios):
        """Datos del formulario; sesiones = [(id o '', fecha, hora_inicio, hora_fin), ...]."""
        inicio = inicio or dia(5, 10)
        fin = fin or inicio + timedelta(hours=2)
        datos = {
            'titulo': 'Taller de oratoria', 'descripcion': 'Tres sesiones', 'tipo': 'TALLER',
            'lugar': 'Sala 1', 'cupos_totales': 20,
            'fecha_inicio_fecha': inicio.strftime('%Y-%m-%d'), 'fecha_inicio_hora': inicio.strftime('%H:%M'),
            'fecha_fin_fecha': fin.strftime('%Y-%m-%d'), 'fecha_fin_hora': fin.strftime('%H:%M'),
            'carreras': [self.carrera.pk], 'jornadas': [self.jornada.pk],
            'sesion_id': [s[0] for s in sesiones], 'sesion_fecha': [s[1] for s in sesiones],
            'sesion_inicio': [s[2] for s in sesiones], 'sesion_fin': [s[3] for s in sesiones],
        }
        datos.update(cambios)
        return datos

    def fila(self, dias, desde='10:00', hasta='12:00', id_=''):
        return (str(id_), dia(dias).strftime('%Y-%m-%d'), desde, hasta)

    def crear(self, **kw):
        self.login_as(self.creador)
        return self.client.post(reverse('crear_actividad'), self.datos(**kw), **AJAX)

    def editar(self, actividad, **kw):
        self.login_as(self.creador)
        return self.client.post(reverse('editar_actividad', args=[actividad.pk]),
                                {**self.datos(**kw), 'forzar_edicion': 'true'}, **AJAX)


class HoraAlEditarTests(BaseSesionesForm):
    def test_el_formulario_muestra_la_hora_de_chile_y_guardar_no_mueve_la_actividad(self):
        # 22:30 en Chile es otro día en UTC: con el error se mostraba 01:30 del día siguiente
        inicio = dia(6, 22, 30)
        self.actividad.fecha_inicio, self.actividad.fecha_fin = inicio, inicio + timedelta(hours=1)
        self.actividad.save()
        form = ActividadForm(instance=self.actividad)
        self.assertEqual(form.fields['fecha_inicio_fecha'].initial, inicio.date())
        self.assertEqual(form.fields['fecha_inicio_hora'].initial.strftime('%H:%M'), '22:30')

        r = self.editar(self.actividad, inicio=inicio, fin=inicio + timedelta(hours=1))
        self.assertTrue(r.json()['success'], r.json())
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.fecha_inicio, inicio)


class CrearConSesionesTests(BaseSesionesForm):
    def test_crea_las_sesiones_en_orden_y_la_actividad_termina_con_la_ultima(self):
        # Una fila vacía (se agregó y no se llenó) se ignora
        r = self.crear(sesiones=[self.fila(19, '15:00', '17:00'), ('', '', '', ''), self.fila(12)],
                       asistencia_minima='80')
        self.assertTrue(r.json()['success'], r.json())
        act = Actividad.objects.get(titulo='Taller de oratoria')
        sesiones = list(act.sesiones.all())
        self.assertEqual([s.numero for s in sesiones], [1, 2, 3])
        self.assertEqual([timezone.localtime(s.fecha_inicio).date() for s in sesiones],
                         [dia(5).date(), dia(12).date(), dia(19).date()])
        self.assertEqual((act.fecha_inicio, act.fecha_fin), (sesiones[0].fecha_inicio, sesiones[2].fecha_fin))
        self.assertEqual(act.asistencia_minima, 80)

    def test_sin_sesiones_adicionales_queda_de_una_sesion_con_75_por_ciento(self):
        r = self.crear()
        self.assertTrue(r.json()['success'], r.json())
        act = Actividad.objects.get(titulo='Taller de oratoria')
        self.assertEqual(act.sesiones.count(), 1)
        self.assertEqual(act.asistencia_minima, 75)

    def test_sesiones_invalidas_se_rechazan_con_un_mensaje_claro(self):
        casos = [
            ('incompleta', [('', dia(12).strftime('%Y-%m-%d'), '10:00', '')], 'Completa la fecha'),
            ('termina antes de empezar', [self.fila(12, '12:00', '10:00')], 'debe terminar después de empezar'),
            ('antes de que termine la primera', [self.fila(5, '11:00', '13:00')], 'van después de la primera'),
            ('dos que se cruzan', [self.fila(12, '10:00', '12:00'), self.fila(12, '11:00', '13:00')],
             'no pueden cruzarse'),
            ('en el pasado', [self.fila(-3)], 'no puede ser en el pasado'),
            ('demasiadas', [self.fila(10 + i) for i in range(30)], 'hasta 30 sesiones'),
            ('de otra actividad', [self.fila(12, id_=self.actividad_otro.sesiones.get().pk)],
             'no es de esta actividad'),
        ]
        for caso, sesiones, mensaje in casos:
            with self.subTest(caso=caso):
                r = self.crear(sesiones=sesiones)
                datos = r.json()
                self.assertFalse(datos['success'])
                self.assertIn(mensaje, datos['html'])
        self.assertFalse(Actividad.objects.filter(titulo='Taller de oratoria').exists())

    def test_porcentaje_fuera_de_rango_se_rechaza(self):
        for valor in ('0', '101'):
            with self.subTest(valor=valor):
                self.assertFalse(self.crear(sesiones=[self.fila(12)], asistencia_minima=valor).json()['success'])


class EditarSesionesTests(BaseSesionesForm):
    def setUp(self):
        self.crear(sesiones=[self.fila(12), self.fila(19)])
        self.act = Actividad.objects.get(titulo='Taller de oratoria')
        self.s1, self.s2, self.s3 = self.act.sesiones.all()

    def test_el_formulario_trae_las_sesiones_guardadas(self):
        form = ActividadForm(instance=self.act)
        self.assertEqual([f['id'] for f in form.filas_sesiones], [str(self.s2.pk), str(self.s3.pk)])
        # Los campos de fecha de arriba son la primera sesión, no la actividad completa
        self.assertEqual(form.fields['fecha_fin_fecha'].initial, timezone.localtime(self.s1.fecha_fin).date())
        html = render_to_string('gestion/actividad_form_partial.html', {'form': form, 'titulo': 'Editar'})
        self.assertIn('data-agregar-sesion', html)
        self.assertNotIn('data-asistencia-minima hidden', html)

    def test_agregar_una_sesion_entre_medio_renumera_sin_perder_asistencias(self):
        AsistenciaSesion.objects.create(sesion=self.s3, alumno=self.alumno)
        r = self.editar(self.act, sesiones=[self.fila(12, id_=self.s2.pk), self.fila(15), self.fila(19, id_=self.s3.pk)])
        self.assertTrue(r.json()['success'], r.json())
        sesiones = list(self.act.sesiones.all())
        self.assertEqual([s.numero for s in sesiones], [1, 2, 3, 4])
        self.assertEqual(Sesion.objects.get(pk=self.s3.pk).numero, 4)
        self.assertEqual(AsistenciaSesion.objects.get(alumno=self.alumno).sesion_id, self.s3.pk)

    def test_quitar_sesiones_sin_asistencias(self):
        r = self.editar(self.act, sesiones=[self.fila(12, id_=self.s2.pk)])
        self.assertTrue(r.json()['success'], r.json())
        self.assertFalse(Sesion.objects.filter(pk=self.s3.pk).exists())
        self.act.refresh_from_db()
        self.assertEqual(self.act.fecha_fin, Sesion.objects.get(pk=self.s2.pk).fecha_fin)
        # Y quitando todas las adicionales queda de una sesión
        self.assertTrue(self.editar(self.act).json()['success'])
        self.assertEqual(list(self.act.sesiones.values_list('pk', flat=True)), [self.s1.pk])

    def test_no_se_quita_una_sesion_con_asistencias(self):
        AsistenciaSesion.objects.create(sesion=self.s3, alumno=self.alumno)
        r = self.editar(self.act, sesiones=[self.fila(12, id_=self.s2.pk)])
        self.assertFalse(r.json()['success'])
        self.assertIn('ya tiene asistencias registradas', r.json()['html'])
        self.assertTrue(Sesion.objects.filter(pk=self.s3.pk).exists())

    def test_sesiones_ya_realizadas_que_no_cambian_no_se_rechazan(self):
        # Un taller a mitad de camino: las dos primeras sesiones ya pasaron y se edita otra cosa
        tramos = [(dia(-14), dia(-14, 12)), (dia(-7), dia(-7, 12)), (dia(7), dia(7, 12))]
        Sesion.objects.filter(actividad=self.act).delete()
        for n, (a, b) in enumerate(tramos, start=1):
            Sesion.objects.create(actividad=self.act, numero=n, fecha_inicio=a, fecha_fin=b)
        Actividad.objects.filter(pk=self.act.pk).update(fecha_inicio=tramos[0][0], fecha_fin=tramos[-1][1])
        self.act.refresh_from_db()
        filas = ActividadForm(instance=self.act).filas_sesiones
        datos = self.datos(inicio=tramos[0][0], fin=tramos[0][1], titulo='Nombre corregido',
                           sesiones=[(f['id'], f['fecha'], f['inicio'], f['fin']) for f in filas])
        form = ActividadForm(data=datos, instance=self.act)
        self.assertTrue(form.is_valid(), form.errors)
        # Pero mover una sesión al pasado sí se rechaza
        datos['sesion_fecha'][0] = dia(-3).strftime('%Y-%m-%d')
        form = ActividadForm(data=datos, instance=self.act)
        self.assertFalse(form.is_valid())
        self.assertIn('no puede ser en el pasado', ' '.join(form.errores_sesiones))


class InscripcionHastaLaPrimeraSesionTests(BaseSesionesForm):
    def test_el_taller_cierra_la_inscripcion_al_terminar_la_primera_sesion(self):
        ahora = timezone.now()
        Sesion.objects.filter(actividad=self.actividad).delete()
        Sesion.objects.create(actividad=self.actividad, numero=1, fecha_inicio=ahora - timedelta(hours=3),
                              fecha_fin=ahora - timedelta(hours=1))
        Sesion.objects.create(actividad=self.actividad, numero=2, fecha_inicio=ahora + timedelta(days=7),
                              fecha_fin=ahora + timedelta(days=7, hours=2))
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_inicio=ahora - timedelta(hours=3),
                                                             fecha_fin=ahora + timedelta(days=7, hours=2))
        url = reverse('inscripcion_taller', args=[self.actividad.pk])
        r = self.client.post(url, {'rut': self.alumno.rut, 'acepta_politica': 'on'})
        self.assertFalse(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())
        self.assertEqual(r.context['estado'], 'finalizado')

    def test_durante_la_primera_sesion_todavia_se_puede_inscribir(self):
        ahora = timezone.now()
        Sesion.objects.filter(actividad=self.actividad).delete()
        Sesion.objects.create(actividad=self.actividad, numero=1, fecha_inicio=ahora - timedelta(minutes=30),
                              fecha_fin=ahora + timedelta(minutes=30))
        Sesion.objects.create(actividad=self.actividad, numero=2, fecha_inicio=ahora + timedelta(days=7),
                              fecha_fin=ahora + timedelta(days=7, hours=2))
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_inicio=ahora - timedelta(minutes=30),
                                                             fecha_fin=ahora + timedelta(days=7, hours=2))
        self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]),
                         {'rut': self.alumno.rut, 'acepta_politica': 'on'})
        self.assertTrue(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())


class MostrarSesionesTests(BaseSesionesForm):
    def setUp(self):
        self.crear(sesiones=[self.fila(12, '15:00', '17:30')], tipo='MASIVA')
        self.act = Actividad.objects.get(titulo='Taller de oratoria')

    def test_pagina_publica_detalle_y_correo_listan_las_sesiones_solo_si_hay_varias(self):
        publica = self.client.get(reverse('actividad_publica', args=[self.act.pk]))
        self.assertContains(publica, '2 sesiones:')
        self.assertContains(publica, '15:00 a 17:30')

        self.login_as(self.creador)
        detalle = self.client.get(reverse('actividad_detalle', args=[self.act.pk]))
        self.assertContains(detalle, 'Sesiones (2)')
        self.assertContains(detalle, '75 % de las sesiones')

        html = render_to_string('gestion/correos/_datos_actividad.html', {'actividad': self.act})
        self.assertIn('2 sesiones:', html)
        self.assertIn('2. ', html)
        self.assertEqual(len(mail.outbox), 0)

        # Una actividad de una sola sesión se muestra como siempre
        una = self.client.get(reverse('actividad_publica', args=[self.actividad_masiva.pk]))
        self.assertNotContains(una, 'sesiones:')
        self.assertContains(una, 'Fecha:')

