"""
Actividades con invitación, paso 2: enlace personal, respuesta con acompañantes y envío de
las invitaciones por correo.
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Acompanante, Actividad, Invitado, LogAuditoria, NotificacionCorreo
from .tests_invitados import BaseInvitadosTests, rut

ACOMP_1 = rut(18000001)
ACOMP_2 = rut(18000002)


class BaseRespuestaTests(BaseInvitadosTests):
    def setUp(self):
        self.act = self.actividad_invitacion(acompanantes_por_invitado=2)
        self.juan = Invitado.objects.create(actividad=self.act, alumno=self.alumno, rut='200015509',
                                            nombre='Juan Pérez', correo='juan@duocuc.cl')
        self.ana = Invitado.objects.create(actividad=self.act, rut='AB123456', nombre='Ana Gómez',
                                           correo='ana@duocuc.cl')
        self.url = reverse('responder_invitacion', args=[self.juan.token])

    def responder(self, asistira='si', acompanantes=(), politica=True, url=None):
        datos = {'asistira': asistira}
        for i, (doc, nombre) in enumerate(acompanantes, start=1):
            datos[f'acompanante_{i}_documento'] = doc
            datos[f'acompanante_{i}_nombre'] = nombre
        if politica:
            datos['acepta_politica'] = 'on'
        return self.client.post(url or self.url, datos)


class PaginaTests(BaseRespuestaTests):
    def test_muestra_la_invitacion_personal(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, 'Hola, Juan Pérez')
        self.assertContains(resp, 'puedes venir con hasta 2')
        self.assertContains(resp, 'name="acompanante_2_documento"')
        self.assertNotContains(resp, 'name="acompanante_3_documento"')
        self.assertContains(resp, 'noindex')

    def test_enlace_inexistente_da_404(self):
        self.assertEqual(self.client.get(reverse('responder_invitacion', args=['no-existe'])).status_code, 404)

    def test_sin_acompanantes_permitidos_no_los_pide(self):
        Actividad.objects.filter(pk=self.act.pk).update(acompanantes_por_invitado=0)
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'acompanante_1_documento')
        self.responder(acompanantes=[(ACOMP_1, 'Colado')])
        self.assertEqual(self.juan.acompanantes.count(), 0)


class RespuestaTests(BaseRespuestaTests):
    def test_confirma_con_acompanantes(self):
        resp = self.responder(acompanantes=[('18.000.001-' + ACOMP_1[-1], 'Marta Pérez'), (ACOMP_2, 'Luis Soto')])
        self.assertContains(resp, 'Respuesta guardada')
        self.juan.refresh_from_db()
        self.assertEqual(self.juan.estado, 'CONFIRMADO')
        self.assertIsNotNone(self.juan.fecha_respuesta)
        docs = sorted(self.juan.acompanantes.values_list('rut', flat=True))
        self.assertEqual(docs, sorted([ACOMP_1.replace('-', ''), ACOMP_2.replace('-', '')]))
        self.assertTrue(all(a.actividad_id == self.act.pk for a in self.juan.acompanantes.all()))
        log = LogAuditoria.objects.get(accion='Respuesta a invitación')
        self.assertIn('v2026-1', log.detalle)
        self.assertEqual(log.cambios_json['acompanantes'], 2)

    def test_filas_vacias_se_ignoran(self):
        self.responder(acompanantes=[('', ''), (ACOMP_2, 'Luis Soto')])
        self.assertEqual(self.juan.acompanantes.count(), 1)

    def test_no_asistira_borra_acompanantes(self):
        self.responder(acompanantes=[(ACOMP_1, 'Marta')])
        self.responder(asistira='no', acompanantes=[(ACOMP_2, 'Ignorado')])
        self.juan.refresh_from_db()
        self.assertEqual(self.juan.estado, 'RECHAZADO')
        self.assertEqual(self.juan.acompanantes.count(), 0)

    def test_cambiar_la_respuesta_reemplaza_los_acompanantes(self):
        self.responder(acompanantes=[(ACOMP_1, 'Marta')])
        self.responder(acompanantes=[(ACOMP_2, 'Luis')])
        self.assertEqual(list(self.juan.acompanantes.values_list('nombre', flat=True)), ['Luis'])

    def test_validaciones_no_guardan_nada(self):
        Acompanante.objects.create(invitado=self.ana, rut=ACOMP_2, nombre='De Ana')
        casos = [
            ([('11111111-2', 'RUT malo')], 'no es válido'),
            ([(ACOMP_1, '')], 'Falta el nombre'),
            ([('20.001.550-9', 'Yo mismo')], 'tu propio documento'),
            ([(ACOMP_1, 'Uno'), (ACOMP_1, 'Dos')], 'está repetido'),
            ([('AB123456', 'Ana otra vez')], 'ya está registrado en esta actividad'),
            ([(ACOMP_2, 'Acompañante de Ana')], 'ya está registrado en esta actividad'),
        ]
        for acompanantes, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                resp = self.responder(acompanantes=acompanantes)
                self.assertContains(resp, mensaje)
                self.assertContains(resp, 'No se guardó tu respuesta')
                self.juan.refresh_from_db()
                self.assertEqual(self.juan.estado, 'PENDIENTE')
                self.assertEqual(self.juan.acompanantes.count(), 0)

    def test_politica_obligatoria(self):
        resp = self.responder(politica=False)
        self.assertContains(resp, 'aceptar la Política de Privacidad')
        self.juan.refresh_from_db()
        self.assertEqual(self.juan.estado, 'PENDIENTE')

    def test_respuesta_invalida(self):
        resp = self.responder(asistira='quizas')
        self.assertContains(resp, 'Indica si vas a asistir')

    def test_despues_de_empezar_no_se_puede_cambiar(self):
        Actividad.objects.filter(pk=self.act.pk).update(fecha_inicio=timezone.now() - timedelta(minutes=5))
        resp = self.responder(acompanantes=[(ACOMP_1, 'Tarde')])
        self.assertContains(resp, 'Las respuestas están cerradas')
        self.assertContains(resp, 'igual puedes entrar mostrando tu documento')
        self.juan.refresh_from_db()
        self.assertEqual((self.juan.estado, self.juan.acompanantes.count()), ('PENDIENTE', 0))

    def test_actividad_cancelada(self):
        Actividad.objects.filter(pk=self.act.pk).update(estado='CANCELADA')
        self.assertContains(self.client.get(self.url), 'Actividad cancelada')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SITE_URL='https://punto.example.cl', MAX_INVITACIONES_POR_ENVIO=15)
class EnvioTests(BaseRespuestaTests):
    def setUp(self):
        super().setUp()
        self.login_as(self.creador)
        self.url_envio = reverse('enviar_invitaciones_lista', args=[self.act.pk])

    def test_envia_a_quienes_no_la_han_recibido_con_su_enlace(self):
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual(len(mail.outbox), 2)
        correo_juan = next(m for m in mail.outbox if m.to == ['juan@duocuc.cl'])
        self.assertIn(f'https://punto.example.cl/invitacion/{self.juan.token}/', correo_juan.alternatives[0][0])
        self.assertIn(self.juan.token, correo_juan.body)
        self.juan.refresh_from_db()
        self.assertIsNotNone(self.juan.invitacion_enviada)
        self.assertEqual(NotificacionCorreo.objects.filter(invitado=self.juan, estado_envio='EXITO').count(), 1)
        # Un segundo envío no repite
        mail.outbox.clear()
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual(len(mail.outbox), 0)

    def test_reenvio_solo_a_quienes_no_han_respondido(self):
        Invitado.objects.filter(pk=self.ana.pk).update(estado='CONFIRMADO')
        self.client.post(self.url_envio, {'modo': 'sin_responder'})
        self.assertEqual([m.to for m in mail.outbox], [['juan@duocuc.cl']])

    def test_no_se_envia_a_quien_dijo_que_no(self):
        Invitado.objects.filter(pk=self.ana.pk).update(estado='RECHAZADO')
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual([m.to for m in mail.outbox], [['juan@duocuc.cl']])

    @override_settings(MAX_INVITACIONES_POR_ENVIO=1)
    def test_respeta_el_maximo_por_envio(self):
        resp = self.client.post(self.url_envio, {'modo': 'pendientes'}, follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resp, 'Quedan 1')
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual(len(mail.outbox), 2)

    def test_fallo_de_correo_queda_registrado(self):
        with mock.patch('gestion.views_invitados.send_mail', side_effect=OSError('SMTP caído')):
            resp = self.client.post(self.url_envio, {'modo': 'pendientes'}, follow=True)
        self.assertContains(resp, '2 con error')
        self.assertEqual(NotificacionCorreo.objects.filter(actividad=self.act, estado_envio='FALLO').count(), 2)
        self.juan.refresh_from_db()
        self.assertIsNone(self.juan.invitacion_enviada)

    def test_no_se_envia_si_la_actividad_ya_empezo(self):
        Actividad.objects.filter(pk=self.act.pk).update(fecha_inicio=timezone.now() - timedelta(minutes=1))
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual(len(mail.outbox), 0)

    def test_permisos_y_solo_post(self):
        self.assertEqual(self.client.get(self.url_envio).status_code, 405)
        self.login_as(self.otro_creador)
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        self.assertEqual(len(mail.outbox), 0)

    def test_pantalla_muestra_estado_y_enlace_para_copiar(self):
        resp = self.client.get(reverse('invitados_actividad', args=[self.act.pk]))
        self.assertContains(resp, 'No enviada')
        self.assertContains(resp, f'data-copiar="https://punto.example.cl/invitacion/{self.juan.token}/"')
        self.assertContains(resp, 'Enviar a quienes no la han recibido')

    def test_notificaciones_muestran_al_invitado(self):
        self.client.post(self.url_envio, {'modo': 'pendientes'})
        resp = self.client.get(reverse('notificaciones_actividad', args=[self.act.pk]))
        self.assertContains(resp, 'Ana Gómez')
        self.assertContains(resp, 'ana@duocuc.cl')
