"""
Pruebas de parámetros hostiles en la URL (GET) y en formularios simples (POST).

Se guarda como gestion/tests_parametros.py (Django lo descubre solo).
Verifica que ningún valor raro (texto donde va un número, fechas imposibles,
NUL, textos larguísimos, HTML, etc.) produce un error 500.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Rol, UsuarioSistema

VALORES = [
    'abc',                          # texto donde va un número o una fecha
    '\x00',                         # NUL: PostgreSQL lo rechaza
    'a\x00b',
    "' OR '1'='1",
    '2026-13-45',                   # fecha imposible
    '9' * 30,                       # número gigante
    '<script>alert(1)</script>',
    'Peña & Co #1 100%',
    'a' * 3000,
]

_FILTROS_REPORTE = ['actividad', 'escuela', 'carrera', 'jornada',
                    'fecha_inicio', 'fecha_fin']

# (nombre de la URL, argumentos, parámetros GET que lee la vista)
PAGINAS_GET = [
    ('dashboard', [], ['rango', 'tipo', 'carrera', 'jornada']),
    ('lista_actividades', [],
     ['tipo', 'fecha', 'fecha_creacion', 'estado', 'orden', 'page']),
    ('auditoria', [], ['usuario', 'accion', 'modulo', 'fecha', 'page']),
    ('reportes', [], _FILTROS_REPORTE + ['page_act', 'page_det']),
    ('exportar_reportes', ['csv'], _FILTROS_REPORTE),
    ('exportar_reportes', ['xlsx'], _FILTROS_REPORTE),
    ('exportar_reportes_detalle', ['csv'], _FILTROS_REPORTE),
    ('exportar_auditoria', [], ['usuario', 'accion', 'modulo', 'fecha']),
]


def _crear_admin():
    rol = Rol.objects.create(nombre='Administrador')
    user = User.objects.create_user(username='admin_p', password='clave123')
    UsuarioSistema.objects.create(
        user=user, rol=rol, activo=True, must_change_password=False,
    )


class ParametrosGetHostilesTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        _crear_admin()

    def setUp(self):
        self.client.login(username='admin_p', password='clave123')

    def test_parametros_hostiles_no_devuelven_500(self):
        for nombre, args, params in PAGINAS_GET:
            url = reverse(nombre, args=args)
            for param in params:
                for valor in VALORES:
                    with self.subTest(url=f'{nombre}{args}', param=param,
                                      valor=repr(valor)[:25]):
                        r = self.client.get(url, {param: valor})
                        self.assertEqual(r.status_code, 200)

    def test_filtros_validos_siguen_funcionando(self):
        validos = [
            ('lista_actividades', [],
             {'fecha': '2026-10-04', 'tipo': 'TALLER', 'estado': 'ACTIVA'}),
            ('auditoria', [], {'fecha': '2026-10-04', 'usuario': 'admin'}),
            ('reportes', [],
             {'actividad': '1', 'fecha_inicio': '2026-01-01',
              'fecha_fin': '2026-12-31'}),
            ('exportar_reportes', ['csv'],
             {'actividad': '1', 'fecha_inicio': '2026-01-01'}),
            ('exportar_auditoria', [], {'fecha': '2026-10-04'}),
        ]
        for nombre, args, params in validos:
            with self.subTest(url=nombre):
                r = self.client.get(reverse(nombre, args=args), params)
                self.assertEqual(r.status_code, 200)


class ParametrosPostHostilesTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        _crear_admin()

    def setUp(self):
        self.client.login(username='admin_p', password='clave123')

    def test_actividad_id_hostil_en_escaneo(self):
        url = reverse('escaneo')
        for valor in VALORES:
            with self.subTest(valor=repr(valor)[:25]):
                r = self.client.post(
                    url, {'cambiar_actividad': '1', 'actividad_id': valor})
                self.assertLess(r.status_code, 500)

    def test_actividad_id_hostil_en_enviar_invitaciones(self):
        url = reverse('enviar_invitaciones')
        for valor in VALORES:
            with self.subTest(valor=repr(valor)[:25]):
                r = self.client.post(url, {'actividad_id': valor})
                self.assertLess(r.status_code, 500)
