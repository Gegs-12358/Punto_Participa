"""
Estado que se muestra de una actividad (Actividad.estado_mostrado): una activa que ya terminó se muestra como
Finalizada en todas las vistas, sin cambiar el estado guardado.

Correr solo este archivo:
    python manage.py test gestion.tests.actividades.tests_estado_mostrado --noinput
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ...models import Actividad
from ..base import BaseSistemaTestCase


def fechas(actividad, inicio, horas=2):
    ahora = timezone.now()
    Actividad.objects.filter(pk=actividad.pk).update(fecha_inicio=ahora + inicio,
                                                     fecha_fin=ahora + inicio + timedelta(hours=horas))
    actividad.refresh_from_db()
    return actividad


class EstadoMostradoTests(BaseSistemaTestCase):
    def test_proxima_en_curso_finalizada_y_cancelada(self):
        self.assertEqual(fechas(self.actividad, timedelta(days=1)).etiqueta_estado, 'Próxima')
        self.assertEqual(fechas(self.actividad, -timedelta(hours=1)).etiqueta_estado, 'En curso')
        terminada = fechas(self.actividad, -timedelta(days=1))
        self.assertEqual(terminada.etiqueta_estado, 'Finalizada')
        self.assertEqual(terminada.estado, 'ACTIVA')   # no se cambia lo guardado
        Actividad.objects.filter(pk=terminada.pk).update(estado='CANCELADA')
        terminada.refresh_from_db()
        self.assertEqual(terminada.etiqueta_estado, 'Cancelada')

    def test_filtro_del_listado_por_estado_mostrado(self):
        fechas(self.actividad, -timedelta(days=1))          # terminada
        self.login_as(self.admin)
        url = reverse('lista_actividades')
        activas = [a.pk for a in self.client.get(url, {'estado': 'ACTIVA'}).context['actividades']]
        finalizadas = [a.pk for a in self.client.get(url, {'estado': 'FINALIZADA'}).context['actividades']]
        self.assertNotIn(self.actividad.pk, activas)
        self.assertIn(self.actividad.pk, finalizadas)
        self.assertIn(self.actividad_masiva.pk, activas)

    def test_inicio_y_listado_muestran_finalizada(self):
        fechas(self.actividad, -timedelta(days=1))
        self.login_as(self.admin)
        for url in (reverse('dashboard'), reverse('lista_actividades'),
                    reverse('actividad_detalle', args=[self.actividad.pk])):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'Finalizada')

    def test_el_inicio_no_cuenta_como_activas_las_terminadas(self):
        self.login_as(self.admin)
        antes = self.client.get(reverse('dashboard')).context['actividades_activas']
        fechas(self.actividad, -timedelta(days=1))
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['actividades_activas'], antes - 1)
