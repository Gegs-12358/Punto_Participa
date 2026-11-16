"""
Retención de datos (avisos a todos los Administradores 10, 7 y 3 días antes, aviso diario al vencer el plazo y
borrado solo cuando un Administrador lo ejecuta) y anonimización de alumnos.
"""
from datetime import date, timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ..anonimizacion import anonimizar, esta_anonimizado
from ..models import (Acompanante, Actividad, Alumno, Asistencia, AvisoRetencion, Inscripcion, Invitado,
                     ListaEspera, LogAuditoria)
from ..retencion import ciclo, fecha_corte
from .tests_integrales import BaseSistemaTestCase


@override_settings(RETENCION_ANIOS=2, RETENCION_AVISOS_DIAS=[10, 7, 3])
class RetencionTests(BaseSistemaTestCase):
    def setUp(self):
        self.hoy = date(2026, 11, 15)
        hace_3 = timezone.now() - timedelta(days=3 * 365)
        self.vieja = self._crear_actividad('Taller antiguo', 'TALLER', self.creador, 5)
        Actividad.objects.filter(pk=self.vieja.pk).update(fecha_inicio=hace_3, fecha_fin=hace_3 + timedelta(hours=2))
        Inscripcion.objects.create(actividad=self.vieja, alumno=self.alumno)
        Asistencia.objects.create(actividad=self.vieja, alumno=self.alumno, metodo_ingreso='RUT')
        self.log_viejo = LogAuditoria.objects.create(accion='Algo antiguo', detalle='x', ip_address='10.0.0.1')
        LogAuditoria.objects.filter(pk=self.log_viejo.pk).update(fecha_registro=hace_3)
        self.log_nuevo = LogAuditoria.objects.create(accion='Algo reciente', detalle='y')
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.admin2 = self._crear_usuario('admin_dos', 'Administrador', self.rol_admin)
        mail.outbox.clear()

    def dia(self, n):
        return ciclo(self.hoy + timedelta(days=n))[0]

    def test_fecha_de_corte(self):
        self.assertEqual(fecha_corte(date(2026, 11, 15)), date(2024, 11, 15))
        self.assertEqual(fecha_corte(date(2028, 2, 29)), date(2026, 2, 28))

    def test_sin_datos_vencidos_no_hace_nada(self):
        Actividad.objects.filter(pk=self.vieja.pk).delete()
        LogAuditoria.objects.filter(pk=self.log_viejo.pk).delete()
        self.assertEqual(self.dia(0), 'sin_datos')
        self.assertFalse(AvisoRetencion.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def borrar(self, user, verificado=True):
        self.login_as(user)
        aviso = AvisoRetencion.objects.get()
        datos = {'verificado': 'on'} if verificado else {}
        return self.client.post(reverse('retencion_ejecutar', args=[aviso.pk]), datos, follow=True)

    def test_avisa_a_todos_10_7_y_3_dias_antes_y_no_borra_solo(self):
        self.assertEqual(self.dia(0), 'avisado')
        aviso = AvisoRetencion.objects.get()
        self.assertEqual(aviso.fecha_programada, self.hoy + timedelta(days=10))
        self.assertEqual(aviso.resumen['actividades'], 1)
        self.assertEqual(aviso.resumen['auditoria'], 1)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), sorted([self.admin.email, self.admin2.email]))
        self.assertIn('10 días', mail.outbox[0].subject)
        self.assertIn('verificar.sh', mail.outbox[0].alternatives[0][0])

        self.assertEqual(self.dia(1), 'esperando')
        self.assertEqual(self.dia(3), 'avisado')        # faltan 7
        self.assertIn('7 días', mail.outbox[-1].subject)
        self.assertEqual(self.dia(5), 'esperando')
        self.assertEqual(self.dia(7), 'avisado')        # faltan 3
        self.assertEqual(len(mail.outbox), 6)           # 3 avisos x 2 administradores
        self.assertTrue(Actividad.objects.filter(pk=self.vieja.pk).exists())

    def test_vencido_el_plazo_no_borra_y_avisa_cada_dia(self):
        self.dia(0)
        mail.outbox.clear()
        self.assertEqual(self.dia(10), 'vencido')
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('nadie lo ha ejecutado', mail.outbox[0].subject)
        self.assertEqual(self.dia(10), 'esperando')     # una vez por día
        self.assertEqual(self.dia(11), 'vencido')
        self.assertEqual(self.dia(25), 'vencido')
        self.assertEqual(len(mail.outbox), 6)
        self.assertTrue(Actividad.objects.filter(pk=self.vieja.pk).exists())
        self.assertTrue(LogAuditoria.objects.filter(pk=self.log_viejo.pk).exists())

    def test_si_un_dia_no_corre_el_recordatorio_sale_igual(self):
        self.dia(0)
        self.assertEqual(self.dia(8), 'avisado')   # faltan 2: se saltó el de 7 y el de 3
        self.assertEqual(AvisoRetencion.objects.get().avisos_enviados, [10, 7, 3])
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(self.dia(9), 'esperando')

    def test_un_administrador_ejecuta_y_se_avisa_a_todos_quien_fue(self):
        self.dia(0)
        mail.outbox.clear()
        respuesta = self.borrar(self.admin2)
        self.assertContains(respuesta, 'Se avisó a los demás Administradores')
        self.assertFalse(Actividad.objects.filter(pk=self.vieja.pk).exists())
        self.assertFalse(Asistencia.objects.filter(actividad_id=self.vieja.pk).exists())
        self.assertFalse(LogAuditoria.objects.filter(pk=self.log_viejo.pk).exists())
        # Lo reciente y el alumno se conservan
        self.assertTrue(Actividad.objects.filter(pk=self.actividad.pk).exists())
        self.assertTrue(LogAuditoria.objects.filter(pk=self.log_nuevo.pk).exists())
        self.assertTrue(Alumno.objects.filter(pk=self.alumno.pk).exists())

        aviso = AvisoRetencion.objects.get()
        self.assertEqual(aviso.ejecutado_por, self.admin2)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), sorted([self.admin.email, self.admin2.email]))
        self.assertIn('admin_dos borró', mail.outbox[0].subject)
        log = LogAuditoria.objects.get(accion='Retención de datos ejecutada')
        self.assertEqual(log.usuario_sistema, self.admin2)
        self.assertIn('admin_dos', log.detalle)
        # Cerrado el proceso, no hay más avisos ni aviso en el Inicio
        self.assertEqual(self.dia(12), 'sin_datos')
        self.assertNotContains(self.client.get(reverse('dashboard')), 'borrar ahora')

    def test_sin_la_casilla_no_borra(self):
        self.dia(0)
        respuesta = self.borrar(self.admin, verificado=False)
        self.assertContains(respuesta, 'Marca la casilla')
        self.assertTrue(Actividad.objects.filter(pk=self.vieja.pk).exists())

    def test_si_otro_ya_borro_se_informa(self):
        self.dia(0)
        self.borrar(self.admin2)
        respuesta = self.borrar(self.admin)
        self.assertContains(respuesta, 'admin_dos ya había ejecutado')
        self.assertEqual(LogAuditoria.objects.filter(accion='Retención de datos ejecutada').count(), 1)

    def test_solo_el_administrador_puede_borrar(self):
        self.dia(0)
        self.login_as(self.creador)
        aviso = AvisoRetencion.objects.get()
        respuesta = self.client.post(reverse('retencion_ejecutar', args=[aviso.pk]), {'verificado': 'on'})
        self.assertNotEqual(respuesta.status_code, 200)
        self.assertTrue(Actividad.objects.filter(pk=self.vieja.pk).exists())

    def test_borra_solo_lo_anunciado(self):
        self.dia(0)
        # Algo que vence después del aviso espera al próximo proceso
        casi = self._crear_actividad('Casi vencida', 'MASIVA', self.creador, None)
        limite = timezone.make_aware(timezone.datetime(2024, 11, 20, 12, 0))
        Actividad.objects.filter(pk=casi.pk).update(fecha_inicio=limite, fecha_fin=limite)
        self.borrar(self.admin)
        self.assertTrue(Actividad.objects.filter(pk=casi.pk).exists())

    def test_aviso_en_el_inicio_solo_para_el_administrador(self):
        ciclo(timezone.localdate())
        self.login_as(self.admin)
        respuesta = self.client.get(reverse('dashboard'))
        self.assertContains(respuesta, 'Retención de datos: quedan 10 días')
        self.assertContains(respuesta, 'Ya verifiqué los respaldos: borrar ahora')
        self.login_as(self.creador)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Retención de datos')

    def test_comando(self):
        salida = StringIO()
        call_command('retencion', '--simular', stdout=salida)
        self.assertIn('actividades: 1', salida.getvalue())
        self.assertFalse(AvisoRetencion.objects.exists())
        call_command('retencion', stdout=salida)
        self.assertIn('Aviso enviado', salida.getvalue())


class AnonimizacionTests(BaseSistemaTestCase):
    def setUp(self):
        self.insc = Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        Asistencia.objects.create(actividad=self.actividad, alumno=self.alumno, metodo_ingreso='RUT')
        LogAuditoria.objects.create(accion='Inscripción a taller', detalle='Juan Pérez - Taller integral',
                                    objeto_tipo='Alumno', objeto_id=self.alumno.pk, objeto_nombre='Juan Pérez')
        LogAuditoria.objects.create(accion='Respuesta a invitación', detalle='Juan Pérez confirmó',
                                    objeto_tipo='Actividad', cambios_json={'invitado': 'Juan Pérez'})
        especial = self._crear_actividad('Ceremonia', 'MASIVA', self.creador, None)
        self.inv = Invitado.objects.create(actividad=especial, alumno=self.alumno, rut=self.alumno.rut,
                                           nombre='Juan Pérez', correo=self.alumno.correo, carrera='X')
        self.acomp = Acompanante.objects.create(actividad=especial, invitado=self.inv, rut='11111111-1',
                                                nombre='Rosa Pérez')
        ListaEspera.objects.create(actividad=self.actividad_otro, alumno=self.alumno)

    def test_anonimiza_y_conserva_la_participacion(self):
        carrera = self.insc.carrera
        anonimizar(self.alumno)
        a = Alumno.objects.get(pk=self.alumno.pk)
        self.assertTrue(esta_anonimizado(a))
        self.assertNotIn('Juan', a.nombres + a.apellidos)
        self.assertEqual(a.correo, '')
        self.assertFalse(a.activo)
        self.assertTrue(a.bloqueo_manual)
        self.assertEqual(Inscripcion.objects.get(pk=self.insc.pk).carrera, carrera)
        self.assertTrue(Asistencia.objects.filter(alumno=a).exists())
        self.assertFalse(ListaEspera.objects.filter(alumno=a).exists())
        inv = Invitado.objects.get(pk=self.inv.pk)
        self.assertEqual((inv.nombre, inv.correo), ('Invitado anonimizado', ''))
        self.assertEqual(Acompanante.objects.get(pk=self.acomp.pk).nombre, 'Acompañante anonimizado')
        for log in LogAuditoria.objects.all():
            texto = f'{log.detalle} {log.objeto_nombre} {log.cambios_json}'
            self.assertNotIn('Juan Pérez', texto)
            self.assertNotIn('Rosa Pérez', texto)

    def test_pantalla_pide_escribir_anonimizar(self):
        self.login_as(self.admin)
        url = reverse('alumno_anonimizar', args=[self.alumno.pk])
        self.client.post(url, {'confirmacion': 'si'})
        self.assertFalse(esta_anonimizado(Alumno.objects.get(pk=self.alumno.pk)))
        self.client.post(url, {'confirmacion': 'anonimizar'})
        self.assertTrue(esta_anonimizado(Alumno.objects.get(pk=self.alumno.pk)))
        self.assertTrue(LogAuditoria.objects.filter(accion='Anonimización de alumno').exists())
        ficha = self.client.get(reverse('alumno_detalle', args=[self.alumno.pk]))
        self.assertContains(ficha, 'Los datos personales de este alumno fueron anonimizados')
        self.assertNotContains(ficha, 'Desbloquear')

    def test_no_se_puede_desbloquear_un_anonimizado(self):
        anonimizar(self.alumno)
        self.login_as(self.admin)
        self.client.post(reverse('alumno_bloqueo', args=[self.alumno.pk]), {'accion': 'desbloquear', 'volver': 'detalle'})
        self.assertFalse(Alumno.objects.get(pk=self.alumno.pk).activo)

    def test_solo_el_administrador(self):
        self.login_as(self.creador)
        self.client.post(reverse('alumno_anonimizar', args=[self.alumno.pk]), {'confirmacion': 'ANONIMIZAR'})
        self.assertFalse(esta_anonimizado(Alumno.objects.get(pk=self.alumno.pk)))
