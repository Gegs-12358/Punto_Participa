"""
Escáner con turno y contador en vivo (P2, pedido del Punto Estudiantil).

- El turno empieza al elegir la actividad y termina con "Finalizar turno" o al cambiar
  de actividad. Ambos quedan en la auditoría; al finalizar se muestra el resumen.
- Elegir la actividad no abre un aviso emergente (taparía el campo de la pistola).
- Contador: lo registrado por el operador en su turno, el total de la actividad (todos
  los operadores) y cuántos lleva cada operador. Se actualiza con cada registro y con
  /escaneo/contador/.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Asistencia, Inscripcion, LogAuditoria, TurnoEscaneo
from .tests_integrales import BaseSistemaTestCase

URL = reverse('escaneo')
URL_CONTADOR = reverse('escaneo_contador')


class BaseTurnoTests(BaseSistemaTestCase):
    def elegir(self, actividad, usuario=None):
        self.client.force_login(usuario or self.registrador)
        return self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': actividad.pk}, follow=True)

    def registrar(self, rut):
        self.client.post(URL, {'rut': rut})
        return self.client.post(URL, {'rut': rut, 'confirmar': 'true'})


class InicioYFinDeTurnoTests(BaseTurnoTests):
    def test_elegir_actividad_inicia_turno_sin_aviso_emergente(self):
        resp = self.elegir(self.actividad_masiva)
        self.assertEqual(self.client.session['actividad_escaneo_id'], self.actividad_masiva.pk)
        self.assertIn('turno_inicio', self.client.session)
        self.assertEqual([str(m) for m in resp.context['messages']], [])
        self.assertTrue(LogAuditoria.objects.filter(accion='Iniciar turno', objeto_id=self.actividad_masiva.pk).exists())
        self.assertContains(resp, 'TU TURNO DESDE LAS')

    def test_finalizar_muestra_resumen_y_queda_en_auditoria(self):
        self.elegir(self.actividad_masiva)
        self.registrar('200015509')
        resp = self.client.post(URL, {'finalizar_turno': '1'}, follow=True)
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('registraste 1 asistencia en' in m for m in mensajes), mensajes)
        self.assertNotIn('actividad_escaneo_id', self.client.session)
        self.assertNotIn('turno_inicio', self.client.session)
        log = LogAuditoria.objects.get(accion='Finalizar turno')
        self.assertEqual(log.cambios_json['registradas'], 1)
        self.assertEqual(log.usuario_sistema, self.registrador)

    def test_cambiar_de_actividad_cierra_el_turno_anterior(self):
        self.elegir(self.actividad_masiva)
        self.elegir(self.actividad)
        self.assertEqual(self.client.session['actividad_escaneo_id'], self.actividad.pk)
        log = LogAuditoria.objects.get(accion='Finalizar turno')
        self.assertEqual(log.objeto_id, self.actividad_masiva.pk)
        self.assertEqual(LogAuditoria.objects.filter(accion='Iniciar turno').count(), 2)

    def test_volver_a_elegir_la_misma_actividad_no_reinicia_el_turno(self):
        self.elegir(self.actividad_masiva)
        inicio = self.client.session['turno_inicio']
        self.elegir(self.actividad_masiva)
        self.assertEqual(self.client.session['turno_inicio'], inicio)
        self.assertEqual(LogAuditoria.objects.filter(accion='Iniciar turno').count(), 1)

    def test_sesion_antigua_sin_hora_de_turno(self):
        self.seleccionar_actividad()   # deja la actividad en la sesión, sin turno_inicio
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('turno_inicio', self.client.session)

    def test_hora_de_turno_corrupta_no_rompe(self):
        self.elegir(self.actividad_masiva)
        sesion = self.client.session
        sesion['turno_inicio'] = 'no-es-fecha'
        sesion.save()
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.get(URL_CONTADOR).status_code, 200)
        self.assertEqual(self.client.post(URL, {'finalizar_turno': '1'}).status_code, 302)


class ContadorTests(BaseTurnoTests):
    def test_registro_devuelve_contador_y_metodo(self):
        self.elegir(self.actividad_masiva)
        data = self.registrar('200015509').json()
        self.assertEqual(data['metodo'], 'RUT')
        c = data['contador']
        self.assertEqual((c['mi_turno'], c['total']), (1, 1))
        nombre = self.registrador.first_name or self.registrador.username
        self.assertEqual(c['operadores'], [{'nombre': nombre, 'total': 1, 'yo': True, 'en_turno': True}])
        self.assertEqual(c['en_turno'], 1)

    def test_otros_operadores_suman_al_total_pero_no_a_mi_turno(self):
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno_pasaporte,
                                  metodo_ingreso='RUT', registrado_por=self.admin)
        self.elegir(self.actividad_masiva)
        self.registrar('200015509')
        c = self.client.get(URL_CONTADOR).json()
        self.assertEqual((c['mi_turno'], c['total']), (1, 2))
        self.assertEqual(sorted((o['total'], o['yo']) for o in c['operadores']), [(1, False), (1, True)])

    def test_lo_registrado_antes_del_turno_no_cuenta_en_el_turno(self):
        anterior = Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno_pasaporte,
                                             metodo_ingreso='RUT', registrado_por=self.registrador)
        Asistencia.objects.filter(pk=anterior.pk).update(fecha_ingreso=timezone.now() - timedelta(hours=2))
        self.elegir(self.actividad_masiva)
        c = self.client.get(URL_CONTADOR).json()
        self.assertEqual((c['mi_turno'], c['total']), (0, 1))

    def test_en_talleres_la_meta_son_los_inscritos(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno_pasaporte)
        self.elegir(self.actividad)
        c = self.client.get(URL_CONTADOR).json()
        self.assertEqual((c['meta'], c['meta_texto']), (2, 'inscritos'))

    def test_pantalla_muestra_el_contador(self):
        self.elegir(self.actividad_masiva)
        self.registrar('200015509')
        resp = self.client.get(URL)
        self.assertContains(resp, 'REGISTRADOS EN TU TURNO')
        self.assertContains(resp, 'OPERADORES EN TURNO')
        self.assertContains(resp, 'Por operador')
        self.assertContains(resp, f'data-url="{URL_CONTADOR}"')
        html = resp.content.decode()
        contenido = html[html.index('<main'):html.index('</main>')]   # el menú tiene sus propios íconos
        for simbolo in ('▦', '◎', '⚠', '▢', 'ⓘ', '◉', '●', '⌨'):
            self.assertNotIn(simbolo, contenido)

    def test_contador_sin_actividad_y_permisos(self):
        self.client.force_login(self.registrador)
        self.assertEqual(self.client.get(URL_CONTADOR).status_code, 404)
        self.elegir(self.actividad_masiva)
        self.assertEqual(self.client.post(URL_CONTADOR).status_code, 405)
        self.client.logout()
        self.assertIn(self.client.get(URL_CONTADOR).status_code, (302, 401))


class OperadoresEnTurnoTests(BaseTurnoTests):
    """Lo que se vio en la prueba con dos navegadores: un operador recién conectado, con 0
    registros (o con un intento duplicado), igual debe verse en turno."""

    def test_operador_en_turno_con_cero_registros_aparece(self):
        # El admin registra a Juan en su turno
        self.elegir(self.actividad_masiva, usuario=self.admin)
        self.registrar('200015509')
        # Otro operador entra (otro navegador) e intenta registrar a Juan de nuevo: duplicado
        otro = self.client_class()
        otro.force_login(self.registrador)
        otro.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_masiva.pk})
        self.assertEqual(otro.post(URL, {'rut': '200015509'}).status_code, 409)

        c = otro.get(URL_CONTADOR).json()
        self.assertEqual((c['mi_turno'], c['total'], c['en_turno']), (0, 1, 2))
        por_nombre = {o['nombre']: o for o in c['operadores']}
        registrador = por_nombre[self.registrador.first_name or self.registrador.username]
        self.assertEqual((registrador['total'], registrador['en_turno'], registrador['yo']), (0, True, True))
        # El admin también lo ve
        c_admin = self.client.get(URL_CONTADOR).json()
        self.assertEqual(c_admin['en_turno'], 2)

    def test_finalizar_lo_saca_de_en_turno_pero_conserva_sus_registros(self):
        self.elegir(self.actividad_masiva)
        self.registrar('200015509')
        self.client.post(URL, {'finalizar_turno': '1'})
        turno = TurnoEscaneo.objects.get(usuario=self.registrador)
        self.assertIsNotNone(turno.fin)
        self.elegir(self.actividad_masiva, usuario=self.admin)
        c = self.client.get(URL_CONTADOR).json()
        self.assertEqual(c['en_turno'], 1)
        nombre = self.registrador.first_name or self.registrador.username
        self.assertIn({'nombre': nombre, 'total': 1, 'yo': False, 'en_turno': False}, c['operadores'])

    def test_turno_olvidado_deja_de_contar_a_las_12_horas(self):
        self.elegir(self.actividad_masiva)
        TurnoEscaneo.objects.update(inicio=timezone.now() - timedelta(hours=13))
        self.assertEqual(TurnoEscaneo.abiertos(self.actividad_masiva).count(), 0)

    def test_cambiar_de_actividad_cierra_el_turno_guardado(self):
        self.elegir(self.actividad_masiva)
        self.elegir(self.actividad)
        self.assertEqual(TurnoEscaneo.objects.filter(fin__isnull=True).count(), 1)
        self.assertEqual(TurnoEscaneo.objects.get(fin__isnull=True).actividad, self.actividad)

    def test_contador_trae_los_ultimos_registros_de_todos(self):
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno_pasaporte,
                                  metodo_ingreso='QR', registrado_por=self.admin)
        self.elegir(self.actividad_masiva)
        self.registrar('200015509')
        ultimos = self.client.get(URL_CONTADOR).json()['ultimos']
        self.assertEqual([u['nombre'] for u in ultimos], ['Juan Pérez', 'Ana Gómez'])
        self.assertEqual(ultimos[0]['operador'], 'tú')
        self.assertEqual(ultimos[1]['operador'], self.admin.first_name or self.admin.username)
        self.assertEqual(ultimos[1]['metodo'], 'Código QR')
