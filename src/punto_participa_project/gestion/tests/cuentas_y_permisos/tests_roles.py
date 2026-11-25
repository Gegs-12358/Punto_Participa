"""
Permisos por rol: qué pantallas abre cada uno y qué se le rechaza.

La matriz de abajo es la regla completa en una tabla. Para cada pantalla dice qué pasa con quien no
ha iniciado sesión, el Administrador, el Creador de Evento y el Encargado de Registrar:

  ok        la pantalla abre (200)
  login     vuelve al inicio de sesión, recordando a dónde quería ir
  inicio    vuelve a Inicio con un aviso (302 a /)
  lista     vuelve a la lista de actividades (actividad de otro creador)
  escaneo   el Registrador va directo al Escáner
  403       descarga rechazada

Cada combinación corre como un subTest: si una falla, el informe dice qué rol y qué pantalla.
"""
import json
from io import BytesIO

from openpyxl import load_workbook

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponse, JsonResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from ...decorators import ajax_required, method_required, role_required
from ...models import Asistencia, Inscripcion, LogAuditoria, Rol, UsuarioSistema
from ...permissions import tiene_rol
from ..base import BaseSistemaTestCase, HorarioAbierto

#   pantalla, argumentos                                 anónimo   admin  creador  registrador
MATRIZ = [
    ('dashboard', [],                                   'login', 'ok', 'ok', 'escaneo'),
    ('lista_actividades', [],                           'login', 'ok', 'ok', 'inicio'),
    ('crear_actividad', [],                             'login', 'ok', 'ok', 'inicio'),
    ('editar_actividad', ['propia'],                    'login', 'ok', 'ok', 'inicio'),
    ('editar_actividad', ['ajena'],                     'login', 'ok', 'lista', 'inicio'),
    ('actividad_detalle', ['propia'],                   'login', 'ok', 'ok', 'inicio'),
    ('actividad_detalle', ['ajena'],                    'login', 'ok', 'lista', 'inicio'),
    ('participantes_actividad', ['propia'],             'login', 'ok', 'ok', 'inicio'),
    ('participantes_actividad', ['ajena'],              'login', 'ok', 'lista', 'inicio'),
    ('notificaciones_actividad', ['propia'],            'login', 'ok', 'ok', 'inicio'),
    ('notificaciones_actividad', ['ajena'],             'login', 'ok', 'lista', 'inicio'),
    ('escaneo', [],                                     'login', 'ok', 'ok', 'ok'),
    ('reportes', [],                                    'login', 'ok', 'ok', 'inicio'),
    ('exportar_reportes', ['csv'],                      'login', 'ok', 'ok', '403'),
    ('exportar_reportes', ['excel'],                    'login', 'ok', 'ok', '403'),
    ('exportar_reportes_detalle', ['excel'],            'login', 'ok', 'ok', '403'),
    ('usuarios', [],                                    'login', 'ok', 'inicio', 'inicio'),
    ('importar_usuarios', [],                           'login', 'ok', 'inicio', 'inicio'),
    ('lista_alumnos', [],                               'login', 'ok', 'inicio', 'inicio'),
    ('alumno_detalle', ['alumno'],                      'login', 'ok', 'inicio', 'inicio'),
    ('importar_alumnos', [],                            'login', 'ok', 'inicio', 'inicio'),
    ('catalogo_lugares', [],                            'login', 'ok', 'inicio', 'inicio'),
    ('catalogo_escuelas', [],                           'login', 'ok', 'inicio', 'inicio'),
    ('catalogo_carreras', [],                           'login', 'ok', 'inicio', 'inicio'),
    ('auditoria', [],                                   'login', 'ok', 'inicio', 'inicio'),
    ('exportar_auditoria', [],                          'login', 'ok', '403', '403'),
    # Públicas: abren para todos
    ('inscripcion_taller', ['propia_id'],               'ok', 'ok', 'ok', 'ok'),
    ('privacidad', [],                                  'ok', 'ok', 'ok', 'ok'),
]
COLUMNA = {'anonimo': 2, 'admin': 3, 'creador': 4, 'registrador': 5}


class MatrizDePermisosTests(BaseSistemaTestCase):
    def _args(self, args):
        valores = {'propia': self.actividad.pk, 'propia_id': self.actividad.pk,
                   'ajena': self.actividad_otro.pk, 'alumno': self.alumno.pk}
        return [valores.get(a, a) for a in args]

    def _revisar(self, quien, usuario):
        if usuario:
            self.client.force_login(usuario)
        for fila in MATRIZ:
            nombre, args, esperado = fila[0], self._args(fila[1]), fila[COLUMNA[quien]]
            url = reverse(nombre, args=args)
            with self.subTest(rol=quien, pantalla=url):
                r = self.client.get(url)
                if esperado == 'ok':
                    self.assertEqual(r.status_code, 200)
                elif esperado == '403':
                    self.assertEqual(r.status_code, 403)
                else:
                    self.assertEqual(r.status_code, 302)
                    destino = {'inicio': reverse('dashboard'), 'lista': reverse('lista_actividades'),
                               'escaneo': reverse('escaneo')}
                    if esperado == 'login':
                        self.assertEqual(r.url, f"{reverse('login')}?next={url}")
                    else:
                        self.assertEqual(r.url, destino[esperado])

    def test_sin_sesion(self):
        self._revisar('anonimo', None)

    def test_administrador(self):
        self._revisar('admin', self.admin)

    def test_creador_de_evento(self):
        self._revisar('creador', self.creador)

    def test_encargado_de_registrar(self):
        self._revisar('registrador', self.registrador)

    def test_cuenta_inactiva_o_sin_perfil_no_entra(self):
        inactivo = User.objects.create_user(username='inactivo_matriz', password='x')
        UsuarioSistema.objects.create(user=inactivo, rol=self.rol_admin, activo=False,
                                      must_change_password=False)
        sin_perfil = User.objects.create_user(username='sin_perfil_matriz', password='x')
        for usuario in (inactivo, sin_perfil):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                for pantalla in ('usuarios', 'reportes'):
                    self.assertEqual(self.client.get(reverse(pantalla)).status_code, 302)


class FlujosPorRolTests(HorarioAbierto, BaseSistemaTestCase):
    """Acciones que cambian datos, hechas por el rol que corresponde."""

    def test_registrador_registra_asistencia_en_actividad_masiva(self):
        self.client.force_login(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()
        primera = self.client.post(reverse("escaneo"), {"rut": self.alumno.rut})
        self.assertEqual(primera.status_code, 200)
        self.assertTrue(primera.json()["confirmar"])
        segunda = self.client.post(reverse("escaneo"), {"rut": self.alumno.rut, "confirmar": "true"})
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()["success"])
        self.assertTrue(Asistencia.objects.filter(actividad=self.actividad_masiva, alumno=self.alumno).exists())

    def test_creador_puede_inscribir_alumno_en_su_taller(self):
        # La inscripción pública no exige sesión; con sesión de creador también debe funcionar.
        self.client.force_login(self.creador)
        response = self.client.post(reverse("inscripcion_taller", args=[self.actividad.pk]),
                                    {"rut": self.alumno.rut, "acepta_politica": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())

    def test_creador_solo_ve_sus_actividades_en_lista(self):
        self.login_as(self.creador)
        response = self.client.get(reverse("lista_actividades"))
        self.assertContains(response, self.actividad.titulo)
        self.assertNotContains(response, self.actividad_otro.titulo)


class TieneRolTests(TestCase):
    """tiene_rol() con usuario activo, inactivo, sin perfil y anónimo."""

    def test_tiene_rol(self):
        rol = Rol.objects.create(nombre='Administrador')
        Rol.objects.create(nombre='Encargado de Registrar')
        activo = User.objects.create_user(username='admin_test', password='x')
        UsuarioSistema.objects.create(user=activo, rol=rol, activo=True)
        inactivo = User.objects.create_user(username='inactivo_test', password='x')
        UsuarioSistema.objects.create(user=inactivo, rol=rol, activo=False)
        sin_perfil = User.objects.create_user(username='sin_perfil_test', password='x')
        casos = [
            (activo, ['Administrador'], True),
            (activo, ['Encargado de Registrar'], False),
            (inactivo, ['Administrador'], False),
            (sin_perfil, ['Administrador'], False),
            (AnonymousUser(), ['Administrador'], False),
        ]
        for usuario, roles, esperado in casos:
            with self.subTest(usuario=str(usuario), roles=roles):
                self.assertEqual(tiene_rol(usuario, roles), esperado)


def _vista_json(request):
    return JsonResponse({'ok': True})


class DecoradoresTests(TestCase):
    """ajax_required, method_required y las respuestas de role_required para pedidos JSON."""

    def setUp(self):
        self.f = RequestFactory()

    def test_ajax_required(self):
        vista = ajax_required(_vista_json)
        self.assertEqual(vista(self.f.get('/t/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')).status_code, 200)
        self.assertEqual(vista(self.f.get('/t/', HTTP_ACCEPT='application/json')).status_code, 200)
        rechazo = vista(self.f.get('/t/'))
        self.assertEqual(rechazo.status_code, 400)
        self.assertIn('solo acepta AJAX', rechazo.content.decode())

    def test_method_required(self):
        solo_post = method_required('POST')(_vista_json)
        self.assertEqual(solo_post(self.f.post('/t/')).status_code, 200)
        self.assertEqual(solo_post(self.f.get('/t/')).status_code, 405)
        varios = method_required('POST', 'PUT')(_vista_json)
        self.assertEqual(varios(self.f.post('/t/')).status_code, 200)
        self.assertEqual(varios(self.f.put('/t/')).status_code, 200)

    def test_role_required_sin_sesion(self):
        con_json = role_required('Administrador', json_response=True)(_vista_json)
        pedido = self.f.get('/test/')
        pedido.user = AnonymousUser()
        r = con_json(pedido)
        self.assertEqual(r.status_code, 401)
        data = json.loads(r.content)
        self.assertFalse(data['success'])
        self.assertIn('iniciar sesión', data['message'])

        sin_json = role_required('Administrador')(lambda request: HttpResponse('ok'))
        r = sin_json(pedido)
        self.assertEqual(r.status_code, 302)
        self.assertIn('next=/test/', r.url)

    def test_role_required_con_otro_rol_y_json_devuelve_403(self):
        Rol.objects.create(nombre='Administrador')
        usuario = User.objects.create_user(username='sin_rol', password='x')
        UsuarioSistema.objects.create(user=usuario, rol=Rol.objects.create(nombre='OtroRol'),
                                      activo=True, must_change_password=False)
        pedido = self.f.get('/test/')
        pedido.user = usuario
        self.assertEqual(role_required('Administrador', json_response=True)(_vista_json)(pedido).status_code, 403)


class SeguridadCsrfYCuentaTests(BaseSistemaTestCase):
    def test_post_sin_csrf_es_rechazado_por_django(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.creador)
        response = cliente.post(reverse("crear_actividad"), {"titulo": "Sin CSRF"})
        self.assertEqual(response.status_code, 403)

    def test_administrador_no_puede_bloquearse_a_si_mismo(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("guardar_usuario"),
            {
                "user_id": self.admin.usuariosistema.pk,
                "username": self.admin.username,
                "nombre": self.admin.first_name,
                "email": self.admin.email,
                "rol": self.rol_admin.pk,
                "rut": self.admin.usuariosistema.rut,
                # Sin estado: la vista interpreta la cuenta como inactiva.
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No puedes bloquear", response.json()["message"])


class ReportesYExportacionesPorRolTests(BaseSistemaTestCase):
    """Además de abrir, Inicio, Reportes y las descargas traen lo que deben."""

    def test_admin_ve_los_graficos_de_inicio_y_reportes(self):
        self.login_as(self.admin)
        self.assertContains(self.client.get(reverse("dashboard")), "graficoMeses")
        self.assertContains(self.client.get(reverse("reportes")), "graficoBarrasReportes")

    def test_exportacion_csv_contiene_encabezados_y_datos(self):
        self.login_as(self.creador)
        response = self.client.get(reverse("exportar_reportes", args=["csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        contenido = response.content.decode("utf-8")
        self.assertIn("Actividad", contenido)
        self.assertIn(self.actividad.titulo, contenido)

    def test_exportacion_excel_es_un_libro_valido(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("exportar_reportes", args=["excel"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        libro = load_workbook(filename=BytesIO(response.content), read_only=True)
        hoja = libro["Resumen por actividad"]
        self.assertEqual(hoja.cell(1, 1).value, "Actividad")
        self.assertTrue(any(fila[0] == self.actividad.titulo for fila in hoja.iter_rows(values_only=True)))

    def test_exportacion_detalle_y_auditoria_excel(self):
        LogAuditoria.objects.create(
            usuario_sistema=self.admin,
            modulo="Pruebas",
            accion="Acción de prueba",
            detalle="Detalle",
        )
        self.login_as(self.admin)
        detalle = self.client.get(
            reverse("exportar_reportes_detalle", args=["excel"])
        )
        auditoria = self.client.get(reverse("exportar_auditoria"))
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(auditoria.status_code, 200)
        self.assertGreater(len(detalle.content), 100)
        self.assertGreater(len(auditoria.content), 100)
