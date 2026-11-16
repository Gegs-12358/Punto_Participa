from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from gestion.models import Rol, UsuarioSistema


def congelar_reloj_del_limite(prueba):
       """Congela el reloj que usa django-ratelimit durante la prueba.

       El límite cuenta en ventanas fijas (15 min el login, 1 min el escáner). Si la prueba
       cruzaba el borde de una ventana, el contador volvía a cero y fallaba al azar
       (pasó en corridas con --parallel). Solo se congela el reloj de la librería.
       """
       parche = mock.patch('django_ratelimit.core.time')
       reloj = parche.start()
       reloj.time.return_value = 1_800_000_000
       prueba.addCleanup(parche.stop)


class LimiteIntentosLoginTests(TestCase):
       def setUp(self):
           cache.clear()
           congelar_reloj_del_limite(self)
           self.url = reverse('login')

       def tearDown(self):
           cache.clear()

       def _intento_fallido(self):
           return self.client.post(
               self.url,
               {'username': 'no_existe', 'password': 'clave_incorrecta'},
           )

       def test_cinco_intentos_pasan_y_el_sexto_se_bloquea(self):
           for n in range(1, 6):
               r = self._intento_fallido()
               self.assertEqual(r.status_code, 200, f'intento {n}')
           r = self._intento_fallido()
           self.assertEqual(r.status_code, 403)


def _registrador(username):
       rol, _ = Rol.objects.get_or_create(nombre='Encargado de Registrar')
       user = User.objects.create_user(username=username, password='clave123')
       UsuarioSistema.objects.create(
           user=user, rol=rol, activo=True, must_change_password=False,
       )
       return user


class LimiteEscaneoTests(TestCase):
       TOPE = 120  # escaneos por minuto y por usuario

       def setUp(self):
           cache.clear()
           congelar_reloj_del_limite(self)
           self.url = reverse('escaneo')

       def tearDown(self):
           cache.clear()

       def _cliente(self, username):
           _registrador(username)
           c = Client()
           self.assertTrue(c.login(username=username, password='clave123'))
           return c

       def _escanear(self, cliente):
           # Sin actividad en sesion la vista responde 400 rapido,
           # pero el limite igual cuenta la peticion.
           return cliente.post(self.url, {'rut': '12345678-5'})

       def test_pasado_el_tope_responde_429_en_json(self):
           c = self._cliente('reg_limite')
           for n in range(1, self.TOPE + 1):
               r = self._escanear(c)
               self.assertEqual(r.status_code, 400, f'escaneo {n}')
           r = self._escanear(c)
           self.assertEqual(r.status_code, 429)
           datos = r.json()
           self.assertFalse(datos['success'])
           self.assertTrue(datos['message'])

       def test_el_limite_es_por_usuario_no_compartido(self):
           c1 = self._cliente('reg_uno')
           c2 = self._cliente('reg_dos')
           for _ in range(self.TOPE):
               self._escanear(c1)
           self.assertEqual(self._escanear(c1).status_code, 429)
           self.assertNotEqual(self._escanear(c2).status_code, 429)