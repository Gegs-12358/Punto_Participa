"""
Carga masiva de usuarios: vista previa, errores por fila y enlace para crear la contraseña.

Correr solo este archivo:
    python manage.py test gestion.tests.cuentas_y_permisos.tests_usuarios_masivos --noinput
"""
import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from ...models import LogAuditoria, UsuarioSistema

from ..base import CORREO_FALLIDO, BaseSistemaTestCase


def csv_archivo(filas, encabezado='nombre;correo;rut;rol;usuario'):
    texto = encabezado + '\n' + '\n'.join(filas) + '\n'
    return SimpleUploadedFile('usuarios.csv', texto.encode('utf-8'), content_type='text/csv')


class BaseCarga(BaseSistemaTestCase):
    def setUp(self):
        self.login_as(self.admin)
        self.url = reverse('importar_usuarios')

    def previsualizar(self, filas, **kw):
        return self.client.post(self.url, {'accion': 'previsualizar', 'archivo': csv_archivo(filas, **kw)})

    def confirmar(self):
        return self.client.post(self.url, {'accion': 'confirmar'})


class VistaPreviaTests(BaseCarga):
    def test_la_vista_previa_no_crea_nada(self):
        antes = User.objects.count()
        r = self.previsualizar(['Ana Rojas;ana.rojas@duoc.cl;12.345.678-5;Encargado de Registrar;'])
        self.assertContains(r, 'Cuentas que se crearán')
        self.assertContains(r, 'ana.rojas')
        self.assertEqual(User.objects.count(), antes)
        self.assertEqual(len(mail.outbox), 0)

    def test_errores_por_fila(self):
        r = self.previsualizar([
            'Sin Correo;no-es-correo;11111111-1;Encargado de Registrar;',
            'Rol Malo;rol.malo@duoc.cl;22222222-2;Superusuario;',
            'Uno;uno@duoc.cl;33333333-3;Creador de Evento;',
            'Dos;dos@duoc.cl;33333333-3;Creador de Evento;',
            ';sinnombre@duoc.cl;44444444-4;Creador de Evento;',
        ])
        self.assertContains(r, 'Correo no válido.')
        self.assertContains(r, 'Rol &quot;Superusuario&quot; no existe')
        self.assertContains(r, 'Rut repetido en el archivo (ver fila 4)')
        self.assertContains(r, 'Falta el nombre.')

    def test_faltan_columnas(self):
        r = self.previsualizar(['Ana;ana@duoc.cl;12.345.678-5'], encabezado='nombre;correo;rut')
        self.assertContains(r, 'Faltan columnas: rol')

    def test_rol_sin_importar_mayusculas_ni_tildes(self):
        r = self.previsualizar(['Ana;ana@duoc.cl;12.345.678-5;ENCARGADO DE REGISTRAR;'])
        self.assertContains(r, 'Crear 1 cuenta')

    def test_cuentas_existentes_se_omiten(self):
        perfil = UsuarioSistema.objects.get(user=self.creador)
        r = self.previsualizar([
            f'Ya Existe;nuevo1@duoc.cl;55555555-5;Creador de Evento;{self.creador.username}',
            f'Rut Usado;nuevo2@duoc.cl;{perfil.rut};Creador de Evento;',
            f'Correo Usado;{self.creador.email};66666666-6;Creador de Evento;correousado',
        ])
        self.assertContains(r, 'El usuario ya existe.')
        self.assertContains(r, 'El RUT ya está asignado a otra cuenta.')
        self.assertContains(r, 'El correo ya está asignado a otra cuenta.')
        self.assertContains(r, 'No hay cuentas nuevas que crear.')


class CreacionTests(BaseCarga):
    def test_crea_las_cuentas_y_envia_el_enlace(self):
        self.previsualizar(['Ana Rojas;ana.rojas@duoc.cl;12.345.678-5;Encargado de Registrar;',
                            'María González;maria@duoc.cl;9.876.543-3;Creador de Evento;mgonzalez'])
        r = self.confirmar()
        self.assertContains(r, 'Cuentas creadas: <strong>2</strong>', html=False)
        ana = User.objects.get(username='ana.rojas')
        self.assertFalse(ana.has_usable_password())
        self.assertTrue(ana.is_active)
        perfil = UsuarioSistema.objects.get(user=ana)
        self.assertEqual(perfil.rol.nombre, 'Encargado de Registrar')
        self.assertEqual(perfil.rut, '123456785')
        self.assertTrue(User.objects.filter(username='mgonzalez', email='maria@duoc.cl').exists())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['ana.rojas@duoc.cl', 'maria@duoc.cl'])
        self.assertTrue(LogAuditoria.objects.filter(accion='Carga masiva de usuarios').exists())

    def test_el_enlace_permite_crear_la_contrasena_y_entrar(self):
        self.previsualizar(['Ana Rojas;ana.rojas@duoc.cl;12.345.678-5;Encargado de Registrar;'])
        self.confirmar()
        enlace = re.search(r'https?://[^\s]+/restablecer-contrasena/[^\s]+/', mail.outbox[0].body).group(0)
        ruta = '/' + enlace.split('/', 3)[3]
        self.client.logout()
        self.assertContains(self.client.get(ruta), 'name="nueva_contrasena"')
        self.client.post(ruta, {'nueva_contrasena': 'ClaveNueva2026!x', 'confirmar_contrasena': 'ClaveNueva2026!x'})
        ana = User.objects.get(username='ana.rojas')
        self.assertTrue(ana.check_password('ClaveNueva2026!x'))
        self.assertFalse(UsuarioSistema.objects.get(user=ana).must_change_password)
        # El enlace no se puede usar dos veces
        self.assertNotContains(self.client.get(ruta), 'name="nueva_contrasena"')

    def test_confirmar_sin_vista_previa(self):
        r = self.confirmar()
        self.assertContains(r, 'No hay una vista previa pendiente')

    def test_si_la_cuenta_aparece_entre_la_vista_previa_y_la_confirmacion_se_omite(self):
        self.previsualizar(['Ana Rojas;ana.rojas@duoc.cl;12.345.678-5;Encargado de Registrar;'])
        User.objects.create_user('ana.rojas', 'otra@duoc.cl', 'x')
        r = self.confirmar()
        self.assertContains(r, 'No hay usuarios nuevos que crear.')
        self.assertEqual(len(mail.outbox), 0)


class PermisosTests(BaseCarga):
    def test_solo_el_administrador(self):
        for usuario in (self.creador, self.registrador):
            self.client.force_login(usuario)
            self.assertNotEqual(self.client.get(self.url).status_code, 200)
            self.previsualizar(['Ana;ana@duoc.cl;12.345.678-5;Creador de Evento;'])
            self.confirmar()
        self.assertFalse(User.objects.filter(email='ana@duoc.cl').exists())

    def test_plantilla(self):
        r = self.client.get(reverse('plantilla_usuarios'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('nombre;correo;rut;rol;usuario', r.content.decode('utf-8-sig'))

    def test_boton_en_usuarios(self):
        self.assertContains(self.client.get(reverse('usuarios')), self.url)


class ImportarUsuariosRechazosTests(BaseCarga):
    def test_sin_archivo_archivo_grande_y_accion_desconocida(self):
        from ...servicios.importador_alumnos import MAX_BYTES
        grande = SimpleUploadedFile('usuarios.csv', b'x' * (MAX_BYTES + 1), content_type='text/csv')
        casos = [
            ('sin archivo', {'accion': 'previsualizar'}, 'Selecciona un archivo'),
            ('archivo demasiado grande', {'accion': 'previsualizar', 'archivo': grande}, 'El archivo supera 5 MB'),
            ('acción desconocida', {'accion': 'otra'}, 'Acción no válida'),
        ]
        for caso, datos, mensaje in casos:
            with self.subTest(caso=caso):
                self.assertContains(self.client.post(self.url, datos), mensaje)
        self.assertFalse(User.objects.filter(email__endswith='@duoc.cl').exists())


class CargaMasivaFilasConErroresTests(BaseCarga):
    def test_errores_por_fila(self):
        casos = [
            ('N' * 151 + ';largo@duoc.cl;12.345.678-5;Creador de Evento;', 'El nombre supera 150 caracteres.'),
            ('Sin Rut;sinrut@duoc.cl;;Creador de Evento;', 'Falta el RUT o documento.'),
            ('Rut Largo;rutlargo@duoc.cl;1234567890123;Creador de Evento;', 'El RUT supera'),
        ]
        for fila, mensaje in casos:
            with self.subTest(mensaje=mensaje):
                self.assertContains(self.previsualizar([fila]), mensaje)

    def test_demasiadas_filas(self):
        from ...servicios.usuarios_masivos import MAX_USUARIOS
        filas = [f'Persona {i};p{i}@duoc.cl;{i}-1;Creador de Evento;' for i in range(MAX_USUARIOS + 1)]
        self.assertContains(self.previsualizar(filas), f'el máximo es {MAX_USUARIOS} usuarios')

    @override_settings(EMAIL_BACKEND=CORREO_FALLIDO)
    def test_si_el_correo_de_bienvenida_no_sale_la_cuenta_igual_se_crea(self):
        self.previsualizar(['Ana Nueva;ana.nueva@duoc.cl;12.345.678-5;Creador de Evento;'])
        r = self.confirmar()
        self.assertTrue(User.objects.filter(email='ana.nueva@duoc.cl').exists())
        log = LogAuditoria.objects.filter(accion='Carga masiva de usuarios').latest('fecha_registro')
        self.assertEqual(log.cambios_json['correos_fallidos'], [['ana.nueva', 'Creador de Evento']])
        self.assertEqual(r.status_code, 200)

