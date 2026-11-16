"""Pruebas de la importación de alumnos desde la web (gestion/views_importar.py)."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from gestion.importador_alumnos import MAX_BYTES
from gestion.management.commands.seed_data import calcular_dv
from gestion.models import Alumno, Carrera, Jornada, LogAuditoria, Rol, UsuarioSistema

COLS = ['rut', 'tipo_documento', 'nombres', 'apellidos', 'correo', 'carrera', 'jornada']
CARRERA = 'Ingeniería en Informática'


def rut_valido(cuerpo):
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


def doc_norm(cuerpo):
    return f'{cuerpo}{calcular_dv(cuerpo)}'


def csv_subido(filas, nombre='nomina.csv'):
    texto = ';'.join(COLS) + '\n' + '\n'.join(';'.join(f.get(c, '') for c in COLS) for f in filas)
    return SimpleUploadedFile(nombre, texto.encode('utf-8'), content_type='text/csv')


class ImportarAlumnosWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Carrera.objects.create(nombre=CARRERA, escuela='Informática')
        Jornada.objects.create(nombre='Diurna')
        cls.url = reverse('importar_alumnos')

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _entrar(self, rol_nombre, username):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        user = User.objects.create_user(username=username, password='clave123')
        UsuarioSistema.objects.create(
            user=user, rol=rol, activo=True, must_change_password=False, rut='11111111K')
        self.assertTrue(self.client.login(username=username, password='clave123'))

    def _fila(self, cuerpo=20000001, **kw):
        d = dict(rut=rut_valido(cuerpo), tipo_documento='', nombres='Ana', apellidos='Pérez',
                 correo=f'a{cuerpo}@example.com', carrera=CARRERA, jornada='Diurna')
        d.update(kw)
        return d

    def _crear_alumno(self, cuerpo):
        return Alumno.objects.create(
            rut=doc_norm(cuerpo), tipo_documento='RUT', nombres='Ana', apellidos='Pérez',
            correo=f'a{cuerpo}@example.com', carrera=CARRERA, jornada='Diurna')

    def _previsualizar(self, filas, nombre='nomina.csv'):
        return self.client.post(self.url, {
            'accion': 'previsualizar', 'archivo': csv_subido(filas, nombre)})

    def _confirmar(self, **extra):
        return self.client.post(self.url, {'accion': 'confirmar', **extra})

    # ---------------- permisos ----------------
    def test_sin_sesion_redirige_al_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r['Location'])

    def test_un_rol_distinto_de_administrador_no_entra(self):
        self._entrar('Creador de Evento', 'creador_imp')
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self._previsualizar([self._fila()])
        self.assertEqual(Alumno.objects.count(), 0)

    def test_el_administrador_ve_el_formulario(self):
        self._entrar('Administrador', 'admin_imp')
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # ---------------- vista previa ----------------
    def test_la_vista_previa_no_guarda_nada(self):
        self._entrar('Administrador', 'admin_imp')
        r = self._previsualizar([self._fila(20000001), self._fila(20000002)])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['resumen']['nuevos'], 2)
        self.assertEqual(Alumno.objects.count(), 0)
        self.assertEqual(LogAuditoria.objects.filter(accion='Importación de alumnos').count(), 0)

    def test_la_vista_previa_informa_errores_y_cambios_y_bloqueos(self):
        self._entrar('Administrador', 'admin_imp')
        self._crear_alumno(20000001)     # cambia el correo
        self._crear_alumno(20000002)     # no viene: se bloquea
        for i in range(3, 12):
            self._crear_alumno(20000000 + i)
        filas = [self._fila(20000001, correo='otro@example.com')] + \
                [self._fila(20000000 + i) for i in range(3, 12)] + \
                [self._fila(20000099, correo='no-es-correo')]
        r = self._previsualizar(filas)
        resumen = r.context['resumen']
        self.assertEqual(resumen['actualizados'], 1)
        self.assertEqual(resumen['errores'], 1)
        self.assertEqual(resumen['bloqueos'], 1)
        self.assertEqual(Alumno.objects.filter(activo=True).count(), 11)

    def test_un_archivo_invalido_muestra_error_y_no_guarda(self):
        self._entrar('Administrador', 'admin_imp')
        archivo = SimpleUploadedFile('datos.txt', b'hola')
        r = self.client.post(self.url, {'accion': 'previsualizar', 'archivo': archivo})
        self.assertEqual(r.status_code, 200)
        self.assertIn('error', r.context)
        self.assertEqual(Alumno.objects.count(), 0)

    def test_sin_archivo_muestra_error(self):
        self._entrar('Administrador', 'admin_imp')
        r = self.client.post(self.url, {'accion': 'previsualizar'})
        self.assertIn('error', r.context)

    def test_un_archivo_demasiado_grande_se_rechaza(self):
        self._entrar('Administrador', 'admin_imp')
        grande = SimpleUploadedFile('nomina.csv', b'x' * (MAX_BYTES + 1))
        r = self.client.post(self.url, {'accion': 'previsualizar', 'archivo': grande})
        self.assertIn('error', r.context)
        self.assertEqual(Alumno.objects.count(), 0)

    # ---------------- confirmación ----------------
    def test_confirmar_guarda_y_audita(self):
        self._entrar('Administrador', 'admin_imp')
        self._previsualizar([self._fila(20000001), self._fila(20000002)])
        r = self._confirmar()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['resultado']['creados'], 2)
        self.assertEqual(Alumno.objects.count(), 2)
        log = LogAuditoria.objects.get(accion='Importación de alumnos')
        self.assertIn('2 creados', log.detalle)

    def test_confirmar_sin_vista_previa_no_hace_nada(self):
        self._entrar('Administrador', 'admin_imp')
        r = self._confirmar()
        self.assertIn('error', r.context)
        self.assertEqual(Alumno.objects.count(), 0)

    def test_no_se_puede_confirmar_dos_veces(self):
        self._entrar('Administrador', 'admin_imp')
        self._previsualizar([self._fila(20000001)])
        self._confirmar()
        r = self._confirmar()
        self.assertIn('error', r.context)
        self.assertEqual(LogAuditoria.objects.filter(accion='Importación de alumnos').count(), 1)

    def test_el_bloqueo_masivo_exige_la_casilla(self):
        self._entrar('Administrador', 'admin_imp')
        for i in range(10):
            self._crear_alumno(20000001 + i)
        self._previsualizar([self._fila(20000001)])           # bloquearía 9 de 10
        r = self._confirmar()
        self.assertIn('error', r.context)
        self.assertEqual(Alumno.objects.filter(activo=True).count(), 10)
        r = self._confirmar(confirmar_bloqueo_masivo='on')
        self.assertEqual(r.context['resultado']['bloqueados'], 9)
        self.assertEqual(Alumno.objects.filter(activo=True).count(), 1)
        self.assertEqual(Alumno.objects.count(), 10)          # nada se borra

    def test_se_reanaliza_al_confirmar(self):
        # Entre la vista previa y la confirmación alguien crea el mismo alumno.
        self._entrar('Administrador', 'admin_imp')
        self._previsualizar([self._fila(20000001)])
        self._crear_alumno(20000001)
        r = self._confirmar()
        self.assertEqual(Alumno.objects.count(), 1)           # no se duplica
        self.assertIn('error', r.context)                     # ya no hay nada que guardar
        self.assertEqual(LogAuditoria.objects.filter(accion='Importación de alumnos').count(), 0)


class EnlaceDelMenuTests(TestCase):
    def _entrar(self, rol_nombre, username):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        user = User.objects.create_user(username=username, password='clave123')
        UsuarioSistema.objects.create(
            user=user, rol=rol, activo=True, must_change_password=False, rut='11111111K')
        self.assertTrue(self.client.login(username=username, password='clave123'))

    # El menú lleva a Alumnos; desde ahí se entra a "Importar nómina".
    def test_el_administrador_ve_el_enlace_en_el_menu(self):
        self._entrar('Administrador', 'admin_menu')
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, f'href="{reverse("lista_alumnos")}"')
        self.assertContains(self.client.get(reverse('lista_alumnos')), reverse('importar_alumnos'))

    def test_un_creador_de_evento_no_ve_el_enlace(self):
        self._entrar('Creador de Evento', 'creador_menu')
        r = self.client.get(reverse('dashboard'))
        self.assertNotContains(r, f'href="{reverse("lista_alumnos")}"')
        self.assertNotContains(r, reverse('importar_alumnos'))
