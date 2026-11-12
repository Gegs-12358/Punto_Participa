"""
Reportes: filtro por tipo de actividad (historia 005: "filtrar por tipo de actividad")
y piezas comunes de P-UI (chips con el nombre de la actividad, botones de exportar).
"""
from django.urls import reverse

from .tests_integrales import BaseSistemaTestCase


class FiltroTipoReportesTests(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)

    def _titulos(self, **filtros):
        resp = self.client.get(reverse('reportes'), filtros)
        self.assertEqual(resp.status_code, 200)
        return {a.titulo for a in resp.context['actividades']}

    def test_filtra_talleres_y_masivas(self):
        self.assertEqual(self._titulos(tipo='TALLER'), {'Taller integral', 'Actividad de otro creador'})
        self.assertEqual(self._titulos(tipo='MASIVA'), {'Actividad masiva'})
        self.assertEqual(len(self._titulos()), 3)

    def test_tipo_desconocido_se_ignora(self):
        for valor in ('OTRO', '<script>x</script>', "' OR 1=1 --"):
            with self.subTest(valor=valor):
                self.assertEqual(len(self._titulos(tipo=valor)), 3)

    def test_la_exportacion_respeta_el_filtro(self):
        resp = self.client.get(reverse('exportar_reportes', args=['csv']), {'tipo': 'MASIVA'})
        contenido = resp.content.decode('utf-8-sig')
        self.assertIn('Actividad masiva', contenido)
        self.assertNotIn('Taller integral', contenido)

    def test_creador_solo_ve_lo_suyo_aunque_filtre(self):
        self.login_as(self.creador)
        self.assertEqual(self._titulos(tipo='TALLER'), {'Taller integral'})

    def test_chips_con_nombre_de_actividad_y_tipo_legible(self):
        resp = self.client.get(reverse('reportes'), {'tipo': 'TALLER', 'actividad': self.actividad.pk})
        self.assertContains(resp, 'id="filtro-tipo"')
        self.assertContains(resp, 'Tipo: Taller')
        self.assertContains(resp, 'Actividad: Taller integral')
        self.assertContains(resp, 'data-tooltip="Filtrar"')
        self.assertContains(resp, 'img/encabezado/reportes.webp')
