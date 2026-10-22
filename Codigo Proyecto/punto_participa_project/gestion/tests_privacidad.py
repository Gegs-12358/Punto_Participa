from django.test import TestCase
from django.urls import reverse


class PoliticaPrivacidadTests(TestCase):
    def test_es_publica_y_muestra_la_politica(self):
        response = self.client.get(reverse("privacidad"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Política de Privacidad")
        self.assertContains(response, "puntoestu@duoc.cl")
