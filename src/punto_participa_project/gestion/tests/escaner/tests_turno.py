"""
Turnos del escáner, contador en vivo con varios operadores y lista para elegir la actividad.

Correr solo este archivo:
    python manage.py test gestion.tests.escaner.tests_turno --noinput
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ...models import Actividad, Asistencia, Inscripcion, LogAuditoria, TurnoEscaneo
from ..base import BaseSistemaTestCase


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


class ElegirActividadTests(BaseTurnoTests):
    """La actividad se elige en una lista (no en un <select>, que se cerraba solo en Linux)."""

    def test_lista_en_curso_primero_y_sin_select(self):
        from ...models import Actividad
        ahora = timezone.now()
        Actividad.objects.filter(pk=self.actividad_otro.pk).update(
            fecha_inicio=ahora - timedelta(hours=1), fecha_fin=ahora + timedelta(hours=1))
        Actividad.objects.filter(pk=self.actividad.pk).update(
            fecha_inicio=ahora + timedelta(days=5), fecha_fin=ahora + timedelta(days=5, hours=2))
        self.client.force_login(self.registrador)
        resp = self.client.get(URL)
        titulos = [a.titulo for a in resp.context['actividades_disponibles']]
        self.assertEqual(titulos, ['Actividad de otro creador', 'Actividad masiva', 'Taller integral'])
        self.assertTrue(resp.context['actividades_disponibles'][0].en_curso)
        self.assertNotContains(resp, 'id="actividadSelect"')
        self.assertContains(resp, 'class="elegir-actividad__opcion')
        self.assertContains(resp, 'En curso')

    def test_cada_opcion_envia_su_actividad(self):
        self.client.force_login(self.registrador)
        resp = self.client.get(URL)
        self.assertContains(resp, '<input type="hidden" name="cambiar_actividad" value="1">', html=True)
        self.assertContains(resp, f'name="actividad_id" value="{self.actividad.pk}"')
        self.assertNotContains(resp, 'name="actividad_id" value="" ')

    # Los tres roles escanean cualquier actividad activa: el Creador de Evento también las de otros
    # (decisión del equipo, 16/11/2026: en el Punto se reparten el registro).
    def test_creador_ve_todas_las_actividades_en_lista(self):
        self.client.force_login(self.creador)
        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, 200)
        titulos = {a.titulo for a in resp.context['actividades_disponibles']}
        self.assertEqual(titulos, {self.actividad.titulo, self.actividad_masiva.titulo, self.actividad_otro.titulo})

    def test_creador_puede_elegir_una_actividad_de_otro_creador(self):
        self.client.force_login(self.creador)
        resp = self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_otro.pk})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session['actividad_escaneo_id'], self.actividad_otro.pk)
        self.assertTrue(LogAuditoria.objects.filter(accion='Iniciar turno',
                                                    objeto_id=self.actividad_otro.pk).exists())

    def test_creador_consulta_el_contador_y_registra_en_actividad_de_otro_creador(self):
        Inscripcion.objects.create(actividad=self.actividad_otro, alumno=self.alumno)
        self.client.force_login(self.creador)
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_otro.pk})

        self.assertEqual(self.client.get(URL_CONTADOR).status_code, 200)
        registro = self.client.post(URL, {'rut': self.alumno.rut, 'confirmar': 'true'})

        self.assertEqual(registro.status_code, 200)
        self.assertTrue(Asistencia.objects.filter(actividad=self.actividad_otro, alumno=self.alumno).exists())

    def test_administrador_ve_todas_las_actividades_en_el_escaner(self):
        self.client.force_login(self.admin)
        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, 200)
        titulos = {a.titulo for a in resp.context['actividades_disponibles']}
        self.assertEqual(titulos, {self.actividad.titulo, self.actividad_masiva.titulo, self.actividad_otro.titulo})


class EscanerCasosBordeTests(BaseTurnoTests):
    """Elegir actividad con datos malos, terminar un turno que no existe y lecturas vacías."""
    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def setUp(self):
        self.client.force_login(self.registrador)

    def test_elegir_actividad_por_ajax_sin_id_inexistente_y_valida(self):
        r = self.client.post(URL, {'cambiar_actividad': '1'}, **self.AJAX)
        self.assertEqual((r.status_code, r.json()['message']), (400, 'Debes seleccionar una actividad.'))
        r = self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': 999999}, **self.AJAX)
        self.assertEqual(r.status_code, 404)
        r = self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.actividad_masiva.pk}, **self.AJAX)
        self.assertEqual(r.json(), {'success': True, 'redirect_url': '/escaneo/'})

    def test_elegir_una_actividad_inexistente_desde_la_pantalla(self):
        r = self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': 999999}, follow=True)
        self.assertIn('Actividad no válida o inactiva.', [str(m) for m in r.context['messages']])

    def test_finalizar_sin_turno_y_actividad_que_dejo_de_estar_activa(self):
        r = self.client.post(URL, {'finalizar_turno': '1'}, follow=True)
        self.assertIn('Turno finalizado.', [str(m) for m in r.context['messages']])
        self.elegir(self.actividad_masiva)
        Actividad.objects.filter(pk=self.actividad_masiva.pk).update(estado='FINALIZADA')
        r = self.client.get(URL)
        self.assertIsNone(r.context['actividad_seleccionada'])
        self.assertNotIn('actividad_escaneo_id', self.client.session)

    def test_lectura_que_queda_vacia(self):
        self.elegir(self.actividad_masiva)
        r = self.client.post(URL, {'rut': "'"})
        self.assertEqual((r.status_code, r.json()['message']), (400, 'Debes ingresar un RUT o Pasaporte válido.'))

    def test_las_que_ya_terminaron_pero_siguen_activas_van_al_final(self):
        ahora = timezone.now()
        Actividad.objects.filter(pk=self.actividad_otro.pk).update(
            fecha_inicio=ahora - timedelta(days=3), fecha_fin=ahora - timedelta(days=3, hours=-2))
        lista = self.client.get(URL).context['actividades_disponibles']
        self.assertEqual(lista[-1].pk, self.actividad_otro.pk)

