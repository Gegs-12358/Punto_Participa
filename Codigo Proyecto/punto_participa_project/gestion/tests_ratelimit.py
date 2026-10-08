from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class LimiteIntentosLoginTests(TestCase):
       def setUp(self):
           cache.clear()
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