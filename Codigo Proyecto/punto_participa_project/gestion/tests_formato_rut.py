from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone

from gestion.models import Actividad, Alumno, Rol, UsuarioSistema


def _mostrar(valor):
    """Renderiza el filtro tal como lo usarian las plantillas."""
    return Template('{% load formato %}{{ v|rut_fmt }}').render(Context({'v': valor}))


class FiltroRutFmtTests(TestCase):
    CASOS = [
        ('123456785', '12.345.678-5'),
        ('12345678K', '12.345.678-K'),
        ('12.345.678-k', '12.345.678-K'),   # fila antigua, sin normalizar
        ('20.001.550-9', '20.001.550-9'),   # fila antigua, ya formateada
        ('AB123456', 'AB123456'),           # pasaporte: se muestra tal cual
        ('', ''),
        (None, ''),
    ]

    def test_formato_de_pantalla(self):
        for entrada, esperado in self.CASOS:
            with self.subTest(entrada=entrada):
                self.assertEqual(_mostrar(entrada), esperado)


class RutFormateadoEnPantallasTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rol = Rol.objects.create(nombre='Administrador')
        self.admin = User.objects.create_user(username='admin_fmt', password='clave123')
        UsuarioSistema.objects.create(
            user=self.admin, rol=self.rol, activo=True,
            must_change_password=False, rut='11111111K',
        )
        self.assertTrue(self.client.login(username='admin_fmt', password='clave123'))

    def test_lista_de_usuarios_muestra_el_rut_con_formato(self):
        r = self.client.get('/usuarios/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '11.111.111-K')

    def test_el_boton_editar_conserva_el_rut_guardado(self):
        # Guardia: debe pasar antes y despues del cambio. El boton
        # reenvia este valor al servidor, asi que NO puede llevar formato.
        r = self.client.get('/usuarios/')
        self.assertContains(r, 'data-rut="11111111K"')

    def test_el_escaner_devuelve_el_rut_con_formato(self):
        ahora = timezone.now()
        act = Actividad.objects.create(
            titulo='Masiva de prueba', descripcion='desc', tipo='MASIVA',
            lugar='Patio', fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=2),
            estado='ACTIVA', cupos_totales=None, cupos_disponibles=None,
            creado_por=self.admin,
        )
        Alumno.objects.create(
            rut='20.001.550-9', nombres='Ana', apellidos='Prueba',
            correo='ana@duocuc.cl', carrera='Informática', jornada='Diurno',
        )
        sesion = self.client.session
        sesion['actividad_escaneo_id'] = act.pk
        sesion.save()

        # Etapa 1: pide confirmacion y devuelve los datos del alumno
        r = self.client.post('/escaneo/', {'rut': '20.001.550-9'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['alumno']['rut'], '20.001.550-9')

        # Etapa 2: registra la asistencia
        r = self.client.post('/escaneo/', {'rut': '20.001.550-9', 'confirmar': 'true'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['alumno']['rut'], '20.001.550-9')