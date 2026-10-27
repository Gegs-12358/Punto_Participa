"""
Un alumno bloqueado (Alumno.activo = False, por ejemplo tras una importacion en la que
ya no viene en la nomina) no debe poder inscribirse, registrar asistencia ni recibir
invitaciones.

Las pruebas miran el EFECTO (no se crea inscripcion/asistencia, el cupo no cambia, no se
revelan sus datos) y no el texto del mensaje, que se definira con el Punto Estudiantil.
Cada caso tiene un control con un alumno activo para que no pasen "en vacio".
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gestion.management.commands.seed_data import calcular_dv
from gestion.models import (
    Actividad, Alumno, Asistencia, Inscripcion, NotificacionCorreo, Rol, UsuarioSistema,
)


def rut_con_dv(cuerpo):
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


RUT_ACTIVO = rut_con_dv(30111222)
RUT_BLOQUEADO = rut_con_dv(30111223)


def crear_alumnos():
    activo = Alumno.objects.create(
        rut=RUT_ACTIVO, tipo_documento='RUT', nombres='Ana', apellidos='Activa',
        correo='ana@example.com', carrera='Informática', jornada='Diurna')
    bloqueado = Alumno.objects.create(
        rut=RUT_BLOQUEADO, tipo_documento='RUT', nombres='Carla', apellidos='Bloqueada',
        correo='carla@example.com', carrera='Informática', jornada='Diurna', activo=False)
    return activo, bloqueado


class InscripcionPublicaBloqueadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        cls.actividad = Actividad.objects.create(
            titulo='Taller de prueba', descripcion='Descripción', tipo='TALLER', lugar='Sala 1',
            cupos_totales=5, cupos_disponibles=5,
            fecha_inicio=ahora + timedelta(days=1),
            fecha_fin=ahora + timedelta(days=1, hours=1), estado='ACTIVA')
        cls.activo, cls.bloqueado = crear_alumnos()
        cls.url = reverse('inscripcion_taller', args=[cls.actividad.pk])

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _inscribir(self, rut):
        return self.client.post(self.url, {'rut': rut, 'acepta_politica': 'on'})

    def test_control_alumno_activo_se_inscribe(self):
        self._inscribir(RUT_ACTIVO)
        self.assertEqual(Inscripcion.objects.filter(alumno=self.activo).count(), 1)

    def test_alumno_bloqueado_no_se_inscribe(self):
        self._inscribir(RUT_BLOQUEADO)
        self.assertEqual(Inscripcion.objects.count(), 0)
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, 5)

    def test_alumno_bloqueado_no_se_inscribe_con_el_documento_sin_formato(self):
        for texto in (RUT_BLOQUEADO.replace('-', ''), RUT_BLOQUEADO.lower()):
            with self.subTest(texto=texto):
                self._inscribir(texto)
                self.assertEqual(Inscripcion.objects.count(), 0)

    def test_no_se_revelan_los_datos_del_bloqueado(self):
        r = self._inscribir(RUT_BLOQUEADO)
        contenido = r.content.decode('utf-8')
        self.assertNotIn('Carla', contenido)
        self.assertNotIn('Bloqueada', contenido)
        self.assertNotIn('carla@example.com', contenido)

    def test_al_reactivarlo_puede_inscribirse(self):
        self._inscribir(RUT_BLOQUEADO)
        self.assertEqual(Inscripcion.objects.count(), 0)
        Alumno.objects.filter(pk=self.bloqueado.pk).update(activo=True)
        self._inscribir(RUT_BLOQUEADO)
        self.assertEqual(Inscripcion.objects.filter(alumno=self.bloqueado).count(), 1)


class EscanerBloqueadoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        rol, _ = Rol.objects.get_or_create(nombre='Administrador')
        admin = User.objects.create_user(username='admin_bloqueados', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=rol, activo=True, must_change_password=False, rut='11111111K')
        ahora = timezone.now()
        self.actividad = Actividad.objects.create(
            titulo='Masiva bloqueados', descripcion='desc', tipo='MASIVA', lugar='Patio',
            fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=2), estado='ACTIVA',
            cupos_totales=None, cupos_disponibles=None, creado_por=admin)
        self.activo, self.bloqueado = crear_alumnos()
        self.assertTrue(self.client.login(username='admin_bloqueados', password='clave123'))
        sesion = self.client.session
        sesion['actividad_escaneo_id'] = self.actividad.pk
        sesion.save()

    def _escanear(self, texto):
        return self.client.post('/escaneo/', {'rut': texto})

    def test_control_alumno_activo_se_reconoce(self):
        r = self._escanear(RUT_ACTIVO)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['confirmar'])

    def test_alumno_bloqueado_no_se_reconoce_por_documento(self):
        r = self._escanear(RUT_BLOQUEADO)
        self.assertEqual(r.status_code, 404)
        datos = r.json()
        self.assertFalse(datos['success'])
        self.assertFalse(datos.get('confirmar'))
        self.assertNotIn('alumno', datos)
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_alumno_bloqueado_no_se_reconoce_por_qr(self):
        qr = ('HTTPS://PORTAL.SIDIV.REGISTROCIVIL.CL/DOCSTATUS'
              f'?RUN={RUT_BLOQUEADO}&TYPE=CEDULA&SERIAL=A123456789')
        r = self._escanear(qr)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_no_se_revelan_los_datos_del_bloqueado(self):
        r = self._escanear(RUT_BLOQUEADO)
        contenido = r.content.decode('utf-8')
        self.assertNotIn('Carla', contenido)
        self.assertNotIn('Bloqueada', contenido)

    def test_al_reactivarlo_se_reconoce(self):
        self.assertEqual(self._escanear(RUT_BLOQUEADO).status_code, 404)
        Alumno.objects.filter(pk=self.bloqueado.pk).update(activo=True)
        r = self._escanear(RUT_BLOQUEADO)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['confirmar'])

    def test_la_confirmacion_directa_tampoco_registra_asistencia_de_un_bloqueado(self):
        r = self.client.post('/escaneo/', {'rut': RUT_BLOQUEADO, 'confirmar': 'true'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_control_la_confirmacion_de_un_activo_registra_asistencia(self):
        self.client.post('/escaneo/', {'rut': RUT_ACTIVO, 'confirmar': 'true'})
        self.assertEqual(Asistencia.objects.filter(alumno=self.activo).count(), 1)

    def test_si_se_bloquea_despues_de_reconocerlo_ya_no_se_reconoce(self):
        self.assertEqual(self._escanear(RUT_ACTIVO).status_code, 200)
        Alumno.objects.filter(pk=self.activo.pk).update(activo=False)
        self.assertEqual(self._escanear(RUT_ACTIVO).status_code, 404)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitacionesBloqueadoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        rol, _ = Rol.objects.get_or_create(nombre='Administrador')
        admin = User.objects.create_user(username='admin_invitaciones', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=rol, activo=True, must_change_password=False, rut='11111111K')
        ahora = timezone.now()
        self.actividad = Actividad.objects.create(
            titulo='Charla invitaciones', descripcion='desc', tipo='MASIVA', lugar='Patio',
            fecha_inicio=ahora + timedelta(days=2), fecha_fin=ahora + timedelta(days=2, hours=2),
            estado='ACTIVA', cupos_totales=None, cupos_disponibles=None, creado_por=admin)
        self.activo, self.bloqueado = crear_alumnos()
        self.assertTrue(self.client.login(username='admin_invitaciones', password='clave123'))

    def _destinatarios(self):
        return [d for m in mail.outbox for d in (list(m.to) + list(m.bcc))]

    def _enviar(self):
        return self.client.post(
            reverse('enviar_invitaciones'), {'actividad_id': self.actividad.pk})

    def test_el_bloqueado_no_recibe_invitaciones_y_el_activo_si(self):
        self._enviar()
        destinatarios = self._destinatarios()
        self.assertIn('ana@example.com', destinatarios)          # control
        self.assertNotIn('carla@example.com', destinatarios)

    def test_el_bloqueado_no_queda_en_el_historial_de_notificaciones(self):
        self._enviar()
        self.assertEqual(NotificacionCorreo.objects.filter(alumno=self.bloqueado).count(), 0)
        self.assertEqual(NotificacionCorreo.objects.filter(alumno=self.activo).count(), 1)

    def test_al_reactivarlo_vuelve_a_recibir_invitaciones(self):
        Alumno.objects.filter(pk=self.bloqueado.pk).update(activo=True)
        self._enviar()
        self.assertIn('carla@example.com', self._destinatarios())

    def test_la_vista_previa_ignora_al_bloqueado(self):
        # Se crea un bloqueado que, por el orden alfabetico, seria el primero de la lista.
        Alumno.objects.create(
            rut=rut_con_dv(30111224), tipo_documento='RUT', nombres='Zoe',
            apellidos='AAA Primero', correo='zoe@example.com',
            carrera='Informática', jornada='Diurna', activo=False)
        r = self.client.get(reverse('previsualizar_invitacion', args=[self.actividad.pk]))
        datos = r.json()
        self.assertTrue(datos['success'])                        # control: hay un activo
        self.assertNotIn('AAA Primero', r.content.decode('utf-8'))

    def test_sin_alumnos_activos_no_hay_vista_previa(self):
        Alumno.objects.filter(pk=self.activo.pk).update(activo=False)
        r = self.client.get(reverse('previsualizar_invitacion', args=[self.actividad.pk]))
        self.assertFalse(r.json()['success'])