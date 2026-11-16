from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from gestion.models import LogAuditoria
from gestion.views import registrar_log


class RegistrarLogLimitesTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.user = User.objects.create_user('auditor', password='clave123')

    def test_objeto_nombre_largo_se_corta_en_vez_de_fallar(self):
        registrar_log(self.request, 'Inscripciones', 'Prueba', 'detalle',
                      'Alumno', 1, 'N' * 300)
        log = LogAuditoria.objects.get(accion='Prueba')
        self.assertEqual(len(log.objeto_nombre), 200)

    def test_modulo_accion_y_tipo_largos_se_cortan(self):
        registrar_log(self.request, 'M' * 80, 'A' * 250, 'detalle', 'T' * 80, 1, 'x')
        log = LogAuditoria.objects.get(objeto_nombre='x')
        self.assertEqual(len(log.modulo), 50)
        self.assertEqual(len(log.accion), 200)
        self.assertEqual(len(log.objeto_tipo), 50)

    def test_ip_vacia_se_guarda_como_nula(self):
        self.request.META['REMOTE_ADDR'] = ''
        registrar_log(self.request, 'Modulo', 'SinIP', 'detalle')
        self.assertIsNone(LogAuditoria.objects.get(accion='SinIP').ip_address)