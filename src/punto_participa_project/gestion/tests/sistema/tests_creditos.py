"""
Créditos del equipo: página Acerca de y línea del pie de página (con nombres solo con sesión iniciada).

Correr solo este archivo:
    python manage.py test gestion.tests.sistema.tests_creditos --noinput
"""
from django.urls import reverse

from ..base import BaseSistemaTestCase


class CreditosTests(BaseSistemaTestCase):
    def test_acerca_de_es_publica_con_equipo_licencia_y_codigo(self):
        r = self.client.get(reverse('acerca'))
        self.assertEqual(r.status_code, 200)
        for nombre in ('Gabriel Eduardo González Soto', 'Pablo Emilio Rebolledo Alvear',
                       'Diverson Nonnombre Nonnombre'):
            self.assertContains(r, nombre)
        self.assertContains(r, 'Jefe de Proyecto y Desarrollador Backend')
        self.assertContains(r, 'GPL), versión 3')
        self.assertContains(r, 'github.com/Gegs-12358/Punto_Participa')

    def test_pie_con_sesion_lleva_los_nombres(self):
        self.login_as(self.admin)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Desarrollado por Gabriel González, Pablo Rebolledo y Diverson Nonnombre')
        self.assertContains(r, reverse('acerca'))

    def test_pie_publico_sin_nombres(self):
        r = self.client.get(reverse('privacidad'))
        self.assertContains(r, 'Desarrollado por\n            estudiantes de Ingeniería en Informática')
        self.assertNotContains(r, 'Pablo Rebolledo y Diverson')
        self.assertContains(r, reverse('acerca'))
