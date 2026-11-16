"""
Páginas de error propias (400, 403, formulario vencido, 405 y 500) y respuestas de "ya no existe" en los botones.
La 404 se prueba junto a las páginas públicas, en inscripciones/tests_inscripcion_publica.

Correr solo este archivo:
    python manage.py test gestion.tests.sistema.tests_paginas_error --noinput
"""
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from ..base import BaseSistemaTestCase


class PaginaMetodoNoPermitidoTests(BaseSistemaTestCase):
    """Abrir desde el navegador una dirección que solo funciona con un botón."""

    def test_muestra_la_pagina_del_sistema_en_vez_de_una_en_blanco(self):
        self.login_as(self.admin)
        urls = [
            reverse('alumno_bloqueo', args=[self.alumno.pk]),
            reverse('alumno_anonimizar', args=[self.alumno.pk]),
            reverse('enviar_invitaciones_lista', args=[self.actividad.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 405)
                self.assertIn('POST', r['Allow'])
                self.assertContains(r, 'Esta dirección se usa desde un botón', status_code=405)

    def test_los_pedidos_de_los_botones_no_cambian(self):
        self.login_as(self.admin)
        url = reverse('alumno_bloqueo', args=[self.alumno.pk])
        r = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 405)
        self.assertNotContains(r, 'Esta dirección se usa desde un botón', status_code=405)


class ActividadQueYaNoExisteTests(BaseSistemaTestCase):
    """Si la actividad se borró mientras la pantalla estaba abierta, el botón avisa en vez de dar error 500."""

    def test_los_botones_responden_que_ya_no_existe(self):
        self.login_as(self.admin)
        ajax = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        respuestas = {
            'eliminar': self.client.post(reverse('eliminar_ajax', args=[99999]), **ajax),
            'previsualizar': self.client.get(reverse('previsualizar_invitacion', args=[99999]), **ajax),
            'enviar': self.client.post(reverse('enviar_invitaciones'), {'actividad_id': 99999}, **ajax),
        }
        for boton, r in respuestas.items():
            with self.subTest(boton=boton):
                self.assertEqual(r.status_code, 404)
                self.assertIn('ya no existe', r.json()['message'])


class OtrasPaginasDeErrorTests(BaseSistemaTestCase):
    def test_formulario_vencido_muestra_la_pagina_del_sistema(self):
        cliente = Client(enforce_csrf_checks=True)
        r = cliente.post(reverse('login'), {'username': 'x', 'password': 'y'})
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, 'El formulario venció', status_code=403)

    def test_las_paginas_se_dibujan_sin_detalles_internos(self):
        casos = {
            '400.html': 'No pudimos procesar la solicitud',
            '403.html': 'No tienes acceso a esta página',
            '403_csrf.html': 'El formulario venció',
            '405.html': 'Esta dirección se usa desde un botón',
            '500.html': 'Algo salió mal',
        }
        for plantilla, mensaje in casos.items():
            with self.subTest(plantilla=plantilla):
                html = render_to_string(plantilla)
                self.assertIn(mensaje, html)
                self.assertIn('puntoestu@duoc.cl', html)
                self.assertNotIn('Traceback', html)
