"""
Cancelación de inscripciones a talleres: correo de confirmación con enlace personal, cancelación
por el alumno hasta 24 horas antes, cancelación por el Administrador o el creador hasta que empiece,
historial de cancelaciones y devolución del cupo.
"""
from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from .cancelaciones import NoSePuedeCancelar, cancelar, ocultar_correo
from .models import Alumno, Asistencia, Inscripcion, InscripcionCancelada, LogAuditoria
from .tests_integrales import BaseSistemaTestCase


class BaseCancelacion(BaseSistemaTestCase):
    def inscribir(self, alumno=None):
        alumno = alumno or self.alumno
        return self.client.post(reverse('inscripcion_taller', args=[self.actividad.pk]),
                                {'rut': alumno.rut, 'acepta_politica': 'on'})

    def inscripcion(self, alumno=None):
        return Inscripcion.objects.get(actividad=self.actividad, alumno=alumno or self.alumno)

    def url_publica(self, insc):
        return reverse('cancelar_inscripcion', args=[insc.token])

    def mover_inicio(self, **delta):
        self.actividad.fecha_inicio = timezone.now() + timedelta(**delta)
        self.actividad.fecha_fin = self.actividad.fecha_inicio + timedelta(hours=2)
        self.actividad.save(update_fields=['fecha_inicio', 'fecha_fin'])


class ConfirmacionPorCorreoTests(BaseCancelacion):
    def test_al_inscribirse_llega_el_correo_con_el_enlace_para_cancelar(self):
        respuesta = self.inscribir()
        insc = self.inscripcion()
        self.assertTrue(insc.token)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.alumno.correo])
        self.assertIn(self.actividad.titulo, correo.subject)
        self.assertIn(self.url_publica(insc), correo.body)
        self.assertIn(self.url_publica(insc), correo.alternatives[0][0])
        self.assertContains(respuesta, ocultar_correo(self.alumno.correo))
        self.assertNotContains(respuesta, self.alumno.correo)

    def test_sin_correo_la_inscripcion_igual_queda(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(correo='')
        respuesta = self.inscribir()
        self.assertTrue(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(respuesta, 'No pudimos enviarte el correo')

    def test_a_menos_de_24_horas_el_correo_no_trae_el_enlace(self):
        self.mover_inicio(hours=10)
        self.inscribir()
        self.assertNotIn('/inscripcion/cancelar/', mail.outbox[0].body)
        self.assertIn('avisa al Punto Estudiantil', mail.outbox[0].alternatives[0][0])

    def test_cada_inscripcion_tiene_su_propio_enlace(self):
        self.inscribir()
        self.inscribir(self.alumno_pasaporte)
        tokens = set(Inscripcion.objects.filter(actividad=self.actividad).values_list('token', flat=True))
        self.assertEqual(len(tokens), 2)

    def test_ocultar_correo(self):
        self.assertEqual(ocultar_correo('juan.perez@duocuc.cl'), 'ju*****@duocuc.cl')
        self.assertEqual(ocultar_correo('ab@x.cl'), 'ab*****@x.cl')
        self.assertEqual(ocultar_correo(''), '')


class CancelacionPorElAlumnoTests(BaseCancelacion):
    def setUp(self):
        self.inscribir()
        self.insc = self.inscripcion()
        self.actividad.refresh_from_db()
        self.cupos_antes = self.actividad.cupos_disponibles

    def test_la_pagina_pide_confirmar(self):
        respuesta = self.client.get(self.url_publica(self.insc))
        self.assertContains(respuesta, 'Cancelar mi inscripción')
        self.assertContains(respuesta, 'noindex')
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_cancelar_libera_el_cupo_y_queda_en_el_historial(self):
        respuesta = self.client.post(self.url_publica(self.insc))
        self.assertContains(respuesta, 'quedó cancelada')
        self.assertFalse(Inscripcion.objects.filter(pk=self.insc.pk).exists())
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, self.cupos_antes + 1)
        c = InscripcionCancelada.objects.get(actividad=self.actividad, alumno=self.alumno)
        self.assertIsNone(c.cancelada_por)
        self.assertEqual(c.token, self.insc.token)
        self.assertEqual(c.carrera, self.insc.carrera)
        self.assertTrue(LogAuditoria.objects.filter(accion='Cancelación de inscripción',
                                                    detalle__contains='desde su enlace').exists())

    def test_el_enlace_usado_muestra_que_ya_se_cancelo(self):
        self.client.post(self.url_publica(self.insc))
        respuesta = self.client.get(self.url_publica(self.insc))
        self.assertContains(respuesta, 'ya fue cancelada')
        self.assertNotContains(respuesta, 'Cancelar mi inscripción')
        # Un segundo POST no devuelve otro cupo
        self.client.post(self.url_publica(self.insc))
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, self.cupos_antes + 1)

    def test_puede_volver_a_inscribirse(self):
        self.client.post(self.url_publica(self.insc))
        self.inscribir()
        nueva = self.inscripcion()
        self.assertNotEqual(nueva.token, self.insc.token)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, self.cupos_antes)

    def test_a_menos_de_24_horas_ya_no_se_puede(self):
        self.mover_inicio(hours=23)
        respuesta = self.client.get(self.url_publica(self.insc))
        self.assertContains(respuesta, 'Faltan menos de 24 horas')
        self.client.post(self.url_publica(self.insc))
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_con_el_taller_comenzado_no_se_puede(self):
        self.mover_inicio(hours=-1)
        respuesta = self.client.post(self.url_publica(self.insc))
        self.assertContains(respuesta, 'ya comenzó')
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_taller_cancelado(self):
        self.actividad.estado = 'CANCELADA'
        self.actividad.save(update_fields=['estado'])
        respuesta = self.client.post(self.url_publica(self.insc))
        self.assertContains(respuesta, 'Taller cancelado')
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_enlace_inventado_da_404(self):
        self.assertEqual(self.client.get(reverse('cancelar_inscripcion', args=['no-existe'])).status_code, 404)


class CancelacionPorElGestorTests(BaseCancelacion):
    def setUp(self):
        self.inscribir()
        self.insc = self.inscripcion()

    def url(self, insc=None):
        return reverse('cancelar_inscripcion_gestor', args=[self.actividad.pk, (insc or self.insc).pk])

    def test_el_creador_cancela_y_queda_registrado_quien(self):
        self.login_as(self.creador)
        respuesta = self.client.post(self.url())
        self.assertRedirects(respuesta, reverse('participantes_actividad', args=[self.actividad.pk]))
        c = InscripcionCancelada.objects.get(actividad=self.actividad, alumno=self.alumno)
        self.assertEqual(c.cancelada_por, self.creador)
        self.assertTrue(LogAuditoria.objects.filter(accion='Cancelación de inscripción',
                                                    detalle__contains='desde el sistema').exists())

    def test_el_gestor_puede_cancelar_dentro_de_las_24_horas(self):
        self.mover_inicio(hours=2)
        self.login_as(self.admin)
        self.client.post(self.url())
        self.assertFalse(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_con_el_taller_comenzado_nadie_cancela(self):
        self.mover_inicio(hours=-1)
        self.login_as(self.admin)
        self.client.post(self.url())
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_otro_creador_no_puede(self):
        self.login_as(self.otro_creador)
        self.client.post(self.url())
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_el_registrador_no_puede(self):
        self.login_as(self.registrador)
        self.client.post(self.url())
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_solo_por_post(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_no_se_cancela_a_quien_ya_tiene_asistencia(self):
        Asistencia.objects.create(actividad=self.actividad, alumno=self.alumno, metodo_ingreso='RUT')
        with self.assertRaises(NoSePuedeCancelar):
            cancelar(self.insc.pk, por=self.admin)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_el_cupo_no_supera_el_total(self):
        self.actividad.cupos_disponibles = self.actividad.cupos_totales
        self.actividad.save(update_fields=['cupos_disponibles'])
        cancelar(self.insc.pk, por=self.admin)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, self.actividad.cupos_totales)

    def test_participantes_muestra_el_boton_y_el_historial(self):
        self.login_as(self.creador)
        url = reverse('participantes_actividad', args=[self.actividad.pk])
        self.assertContains(self.client.get(url), self.url())
        self.client.post(self.url())
        respuesta = self.client.get(url)
        self.assertContains(respuesta, 'Inscripciones canceladas')
        self.assertContains(respuesta, self.creador.username)

    def test_participantes_sin_boton_cuando_comenzo(self):
        self.mover_inicio(hours=-1)
        self.login_as(self.creador)
        respuesta = self.client.get(reverse('participantes_actividad', args=[self.actividad.pk]))
        self.assertNotContains(respuesta, self.url())

    def test_la_cancelada_no_cuenta_como_inscrita(self):
        cancelar(self.insc.pk, por=self.admin)
        self.login_as(self.admin)
        respuesta = self.client.get(reverse('participantes_actividad', args=[self.actividad.pk]))
        self.assertEqual(respuesta.context['total_inscritos'], 0)
