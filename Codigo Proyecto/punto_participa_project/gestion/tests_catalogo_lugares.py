"""
Pruebas de la pantalla de catálogo de lugares (/catalogos/lugares/).

Solo el Administrador entra. Se puede agregar, renombrar (las actividades se actualizan),
bloquear, desbloquear y eliminar (solo si ninguna actividad usa el lugar).
"""
from django.urls import reverse

from .models import Actividad, LogAuditoria, Lugar
from .tests_integrales import BaseSistemaTestCase

URL = reverse('catalogo_lugares')


class AccesoCatalogoLugaresTests(BaseSistemaTestCase):
    def test_anonimo_va_al_login(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp['Location'])

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