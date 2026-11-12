"""
Actividades con invitación, paso 3a: escáner.

- Entran los invitados de la lista (en la nómina o no) y los acompañantes registrados,
  cada uno con su documento. A los de la nómina se les crea además su Asistencia.
- Quien no está en la lista no entra solo: un alumno de la nómina se puede agregar en la
  entrada; otra persona, como acompañante de un invitado con cupo.
- El contador cuenta invitados y acompañantes.
"""
from django.urls import reverse

from .models import Acompanante, Alumno, Asistencia, Invitado, LogAuditoria
from .tests_invitados import BaseInvitadosTests, rut

URL = reverse('escaneo')
URL_CONTADOR = reverse('escaneo_contador')
ACOMP = rut(18000001)
DESCONOCIDO = rut(18000009)


class BaseEscanerInvitacionTests(BaseInvitadosTests):
    def setUp(self):
        self.act = self.actividad_invitacion(acompanantes_por_invitado=1)
        self.juan = Invitado.objects.create(actividad=self.act, alumno=self.alumno, rut='200015509',
                                            nombre='Juan Pérez', correo='juan@duocuc.cl',
                                            carrera='Ingeniería en Informática', estado='CONFIRMADO')
        self.externa = Invitado.objects.create(actividad=self.act, rut='XK1234567', nombre='Rosa Fuera',
                                               correo='rosa@duocuc.cl', carrera='Diseño Gráfico')
        self.acomp = Acompanante.objects.create(invitado=self.juan, rut=ACOMP, nombre='Marta Pérez')
        self.client.force_login(self.registrador)
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.act.pk})

    def escanear(self, doc, confirmar=False, **extra):
        datos = {'rut': doc, **extra}
        if confirmar:
            datos['confirmar'] = 'true'
        return self.client.post(URL, datos)


class IngresoTests(BaseEscanerInvitacionTests):
    def test_invitado_de_la_nomina_entra_y_suma_asistencia(self):
        primera = self.escanear('200015509').json()
        self.assertTrue(primera['confirmar'])
        self.assertIn('Invitado', primera['alumno']['detalle'])
        self.assertIn('Registró 1 acompañante', primera['alumno']['detalle'])
        datos = self.escanear('200015509', confirmar=True).json()
        self.assertTrue(datos['success'])
        self.juan.refresh_from_db()
        self.assertIsNotNone(self.juan.ingreso)
        self.assertEqual((self.juan.metodo_ingreso, self.juan.registrado_por), ('RUT', self.registrador))
        self.assertTrue(Asistencia.objects.filter(actividad=self.act, alumno=self.alumno).exists())
        self.assertEqual(datos['contador']['total'], 1)
        self.assertTrue(LogAuditoria.objects.filter(accion='Ingreso de invitado').exists())

    def test_invitado_fuera_de_la_nomina_entra_sin_asistencia_de_alumno(self):
        datos = self.escanear('XK1234567', confirmar=True).json()
        self.assertTrue(datos['success'])
        self.externa.refresh_from_db()
        self.assertIsNotNone(self.externa.ingreso)
        self.assertFalse(Asistencia.objects.filter(actividad=self.act).exists())

    def test_acompanante_entra_con_su_documento(self):
        primera = self.escanear(ACOMP).json()
        self.assertEqual(primera['alumno']['detalle'], 'Acompañante de Juan Pérez.')
        datos = self.escanear(ACOMP, confirmar=True).json()
        self.assertIn('acompañante de Juan Pérez', datos['message'])
        self.acomp.refresh_from_db()
        self.assertIsNotNone(self.acomp.ingreso)

    def test_no_entra_dos_veces(self):
        self.escanear('200015509', confirmar=True)
        resp = self.escanear('200015509')
        self.assertEqual(resp.status_code, 409)
        self.assertIn('ya ingresó a las', resp.json()['message'])
        self.escanear(ACOMP, confirmar=True)
        self.assertEqual(self.escanear(ACOMP, confirmar=True).status_code, 409)

    def test_documento_con_formato_distinto(self):
        datos = self.escanear('20.001.550-9', confirmar=True).json()
        self.assertTrue(datos['success'])


class AgregarEnLaEntradaTests(BaseEscanerInvitacionTests):
    def test_alumno_de_la_nomina_se_ofrece_y_se_agrega(self):
        oferta = self.escanear('AB123456', confirmar=True).json()
        self.assertEqual(oferta['agregar'], 'alumno')
        self.assertFalse(Invitado.objects.filter(actividad=self.act, rut='AB123456').exists())
        datos = self.escanear('AB123456', confirmar=True, agregar='alumno').json()
        self.assertTrue(datos['success'])
        nuevo = Invitado.objects.get(actividad=self.act, rut='AB123456')
        self.assertTrue(nuevo.agregado_en_entrada)
        self.assertEqual((nuevo.estado, nuevo.alumno, nuevo.carrera), ('CONFIRMADO', self.alumno_pasaporte,
                                                                       'Diseño Gráfico'))
        self.assertIsNotNone(nuevo.ingreso)
        self.assertTrue(Asistencia.objects.filter(actividad=self.act, alumno=self.alumno_pasaporte).exists())
        self.assertTrue(LogAuditoria.objects.filter(accion='Agregar invitado en la entrada').exists())

    def test_alumno_bloqueado_no_se_agrega(self):
        Alumno.objects.filter(pk=self.alumno_pasaporte.pk).update(activo=False)
        resp = self.escanear('AB123456', confirmar=True, agregar='alumno')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Invitado.objects.filter(actividad=self.act, rut='AB123456').exists())

    def test_desconocido_se_ofrece_como_acompanante_de_quien_tiene_cupo(self):
        oferta = self.escanear(DESCONOCIDO).json()
        self.assertEqual(oferta['agregar'], 'acompanante')
        # Juan ya tiene su único acompañante: solo Rosa tiene cupo
        self.assertEqual([o['nombre'] for o in oferta['invitados']], ['Rosa Fuera'])
        datos = self.escanear(DESCONOCIDO, confirmar=True, agregar='acompanante',
                              invitado_id=self.externa.pk, nombre='Pedro Soto').json()
        self.assertTrue(datos['success'], datos)
        nuevo = Acompanante.objects.get(actividad=self.act, rut=DESCONOCIDO.replace('-', ''))
        self.assertEqual((nuevo.invitado, nuevo.nombre, nuevo.agregado_en_entrada), (self.externa, 'Pedro Soto', True))
        self.assertIsNotNone(nuevo.ingreso)

    def test_agregar_acompanante_valida_invitado_y_nombre(self):
        sin_nombre = self.escanear(DESCONOCIDO, confirmar=True, agregar='acompanante', invitado_id=self.externa.pk)
        self.assertEqual(sin_nombre.status_code, 400)
        sin_cupo = self.escanear(DESCONOCIDO, confirmar=True, agregar='acompanante',
                                 invitado_id=self.juan.pk, nombre='Otro')
        self.assertEqual(sin_cupo.status_code, 400)
        self.assertFalse(Acompanante.objects.filter(rut=DESCONOCIDO.replace('-', '')).exists())

    def test_sin_cupo_para_nadie_se_rechaza(self):
        Invitado.objects.filter(pk=self.externa.pk).update(estado='RECHAZADO')
        resp = self.escanear(DESCONOCIDO)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(LogAuditoria.objects.filter(accion='Intento de ingreso sin invitación').exists())


class ContadorInvitacionTests(BaseEscanerInvitacionTests):
    def test_cuenta_invitados_y_acompanantes(self):
        self.escanear('200015509', confirmar=True)
        self.escanear(ACOMP, confirmar=True)
        c = self.client.get(URL_CONTADOR).json()
        self.assertEqual((c['total'], c['mi_turno']), (2, 2))
        self.assertEqual(c['meta'], 3)   # 2 invitados que no dijeron que no + 1 acompañante registrado
        self.assertEqual([u['nombre'] for u in c['ultimos']], ['Marta Pérez', 'Juan Pérez'])
        self.assertEqual(c['ultimos'][0]['iniciales'], 'MP')
        self.assertEqual(c['operadores'][0]['total'], 2)

    def test_pantalla_muestra_los_ultimos_ingresos(self):
        self.escanear('XK1234567', confirmar=True)
        resp = self.client.get(URL)
        self.assertContains(resp, 'Rosa Fuera')
        self.assertContains(resp, 'id="modalAgregar"')
