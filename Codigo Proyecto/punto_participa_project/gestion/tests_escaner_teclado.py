from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from gestion.models import Actividad, Alumno, Rol, UsuarioSistema

# Textos como los envia el navegador (en mayusculas). Los RUN son inventados.
# Los simbolos raros imitan lo observado con el lector en teclado espanol:
# ':' -> Ñ, '/' -> '-', '?' -> '_' o '-', '=' -> ¡, '-' -> "'", '&' -> '/'.
QR_CASOS = [
    ('ingles',
     "HTTPS://PORTAL.SIDIV.REGISTROCIVIL.CL/DOCSTATUS?RUN=20001550-9&TYPE=CEDULA&SERIAL=A123456789",
     '20.001.550-9'),
    ('ingles_dv_k',
     "HTTPS://PORTAL.SIDIV.REGISTROCIVIL.CL/DOCSTATUS?RUN=12345678-K&TYPE=CEDULA&SERIAL=A123456789",
     '12.345.678-K'),
    ('espanol_a',
     "HTTPSÑ--PORTAL.SIDIV.REGISTROCIVIL.CL-DOCSTATUS_RUN¡20001550'9/TYPE¡CEDULA/SERIAL¡A123456789",
     '20.001.550-9'),
    ('espanol_b',
     "HTTPSÑ--PORTAL.SIDIV.REGISTROCIVIL:CL-DOCSTATUS-RUN¡20001550'9/TYPE¡CEDULA/SERIAL¡A123456789",
     '20.001.550-9'),
    ('espanol_dv_k',
     "HTTPSÑ--PORTAL.SIDIV.REGISTROCIVIL.CL-DOCSTATUS_RUN¡12345678'K/TYPE¡CEDULA/SERIAL¡A123456789",
     '12.345.678-K'),
]


class EscanerEnCualquierTecladoTests(TestCase):
    def setUp(self):
        cache.clear()
        rol = Rol.objects.create(nombre='Administrador')
        admin = User.objects.create_user(username='admin_teclado', password='clave123')
        UsuarioSistema.objects.create(
            user=admin, rol=rol, activo=True,
            must_change_password=False, rut='11111111K',
        )
        ahora = timezone.now()
        act = Actividad.objects.create(
            titulo='Masiva teclado', descripcion='desc', tipo='MASIVA',
            lugar='Patio', fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=2),
            estado='ACTIVA', cupos_totales=None, cupos_disponibles=None,
            creado_por=admin,
        )
        Alumno.objects.create(
            rut='20.001.550-9', nombres='Ana', apellidos='Uno',
            correo='ana@duocuc.cl', carrera='Informática', jornada='Diurno',
        )
        Alumno.objects.create(
            rut='12345678-K', nombres='Beto', apellidos='Dos',
            correo='beto@duocuc.cl', carrera='Informática', jornada='Diurno',
        )
        self.assertTrue(self.client.login(username='admin_teclado', password='clave123'))
        sesion = self.client.session
        sesion['actividad_escaneo_id'] = act.pk
        sesion.save()

    def _escanear(self, texto):
        # Solo la primera etapa (pide confirmacion): no registra asistencias.
        return self.client.post('/escaneo/', {'rut': texto})

    def test_qr_se_reconoce_con_teclado_en_ingles_o_espanol(self):
        for nombre, texto, esperado in QR_CASOS:
            with self.subTest(caso=nombre):
                r = self._escanear(texto)
                self.assertEqual(r.status_code, 200)
                datos = r.json()
                self.assertTrue(datos['confirmar'])
                self.assertEqual(datos['alumno']['rut'], esperado)

    def test_codigo_de_barras_con_teclado_en_ingles(self):
        r = self._escanear("20001550-9")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['alumno']['rut'], '20.001.550-9')

    def test_codigo_de_barras_con_teclado_en_espanol(self):
        r = self._escanear("20001550'9")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['alumno']['rut'], '20.001.550-9')

    def test_qr_sin_run_responde_no_encontrado_sin_error(self):
        r = self._escanear("HTTPSÑ--PORTAL.SIDIV.REGISTROCIVIL.CL-DOCSTATUS")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()['success'])