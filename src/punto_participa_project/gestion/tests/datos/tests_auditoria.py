"""
Auditoría: pantalla, filtros, exportación y límites de los campos guardados.

Correr solo este archivo:
    python manage.py test gestion.tests.datos.tests_auditoria --noinput
"""
from datetime import datetime, timedelta
import io

from gestion.views.comun import registrar_log
from openpyxl import load_workbook

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from ...models import LogAuditoria
from ...views.auditoria import SISTEMA, tono_accion
from ..base import BaseSistemaTestCase


class AuditoriaPantallaTests(BaseSistemaTestCase):
    def setUp(self):
        LogAuditoria.objects.all().delete()
        self.a = LogAuditoria.objects.create(usuario_sistema=self.admin, modulo='Actividades',
                                             accion='Crear actividad', detalle='Taller de Oratoria creado',
                                             objeto_tipo='Actividad', objeto_id=5, objeto_nombre='Taller de Oratoria',
                                             ip_address='10.0.0.7')
        self.b = LogAuditoria.objects.create(modulo='Inscripciones', accion='Inscripción a taller',
                                             detalle='Juan Pérez se inscribió', objeto_tipo='Alumno',
                                             objeto_nombre='Juan Pérez')
        self.c = LogAuditoria.objects.create(usuario_sistema=self.creador, modulo='Actividades',
                                             accion='Eliminar actividad', detalle='Charla vieja')
        hace_10 = timezone.make_aware(datetime.now() - timedelta(days=10))
        LogAuditoria.objects.filter(pk=self.c.pk).update(fecha_registro=hace_10)
        self.login_as(self.admin)

    def ids(self, **params):
        return {log.pk for log in self.client.get(reverse('auditoria'), params).context['logs']}

    def test_filtros(self):
        self.assertEqual(self.ids(buscar='juan'), {self.b.pk})
        self.assertEqual(self.ids(buscar='oratoria'), {self.a.pk})
        self.assertEqual(self.ids(usuario=SISTEMA), {self.b.pk})
        self.assertEqual(self.ids(usuario='admin_integral'), {self.a.pk})
        self.assertEqual(self.ids(objeto='Alumno'), {self.b.pk})
        self.assertEqual(self.ids(modulo='actividades'), {self.a.pk, self.c.pk})
        hoy = timezone.localdate()
        self.assertEqual(self.ids(desde=hoy.isoformat()), {self.a.pk, self.b.pk})
        self.assertEqual(self.ids(hasta=(hoy - timedelta(days=5)).isoformat()), {self.c.pk})
        # El filtro antiguo de un solo día sigue funcionando
        self.assertEqual(self.ids(fecha=hoy.isoformat()), {self.a.pk, self.b.pk})

    def test_acciones_agrupadas_por_modulo_y_detalle_completo(self):
        r = self.client.get(reverse('auditoria'), {'modulo': 'Actividades'})
        self.assertEqual(list(r.context['acciones_por_modulo']), ['Actividades'])
        self.assertContains(r, '<optgroup label="Actividades">')
        r = self.client.get(reverse('auditoria'))
        self.assertContains(r, 'Ver todo')
        self.assertContains(r, '10.0.0.7')

    def test_colores_de_las_acciones(self):
        self.assertEqual(tono_accion('Eliminar actividad'), 'inactive')
        self.assertEqual(tono_accion('Crear actividad'), 'badge-success')
        self.assertEqual(tono_accion('Exportar reporte'), 'tono-info')
        self.assertEqual(tono_accion('Finalizar turno'), 'draft')

    def test_excel_con_formato_de_reportes(self):
        r = self.client.get(reverse('exportar_auditoria'), {'modulo': 'Actividades', 'formato': 'excel'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('punto_participa_auditoria_', r['Content-Disposition'])
        wb = load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ['Auditoría', 'Información'])
        ws = wb['Auditoría']
        self.assertEqual(ws['A1'].value, 'Fecha y hora')
        self.assertEqual(ws.max_row, 3)
        self.assertIsInstance(ws['A2'].value, datetime)
        self.assertEqual(ws.freeze_panes, 'A2')
        self.assertTrue(ws['H2'].alignment.wrap_text)
        info = [c.value for c in wb['Información']['B']]
        self.assertIn('Actividades', info)
        # La descarga queda en la auditoría
        log = LogAuditoria.objects.get(accion='Exportar auditoría')
        self.assertIn('2 filas', log.detalle)

    def test_csv(self):
        r = self.client.get(reverse('exportar_auditoria'), {'formato': 'csv', 'usuario': SISTEMA})
        self.assertEqual(r.status_code, 200)
        texto = r.content.decode('utf-8-sig')
        self.assertTrue(texto.startswith('Fecha y hora;Usuario;'))
        self.assertIn('Juan Pérez se inscribió', texto)
        self.assertNotIn('Taller de Oratoria creado', texto)

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
