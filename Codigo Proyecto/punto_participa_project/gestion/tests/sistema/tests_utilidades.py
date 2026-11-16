"""
Funciones de apoyo de utils.py y decorators.py: RUT y documentos (limpiar, validar, formatear,
leer el QR del carnet, buscar al alumno), paginación, limpieza de texto y el filtro rut_fmt.

Cada prueba recorre una tabla de casos con subTest: si un caso falla, el informe dice cuál.
"""
from datetime import timedelta
import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.utils import timezone

from ...models import Actividad, Alumno, Rol, UsuarioSistema
from ...utils import buscar_alumno_por_documento, extraer_rut_de_carnet, formatear_rut, limpiar_texto, normalizar_documento, normalizar_rut, paginar, rut_formateado, rut_limpio, validar_documento, validar_rut, validar_rut_extranjero


def revisar(prueba, funcion, casos):
    """Compara funcion(entrada) con lo esperado para cada caso de la tabla."""
    for entrada, esperado in casos:
        with prueba.subTest(entrada=entrada):
            prueba.assertEqual(funcion(entrada), esperado)


class NormalizacionTests(TestCase):
    """rut_limpio, normalizar_rut y normalizar_documento dejan el documento sin puntos, guion ni espacios."""

    def test_rut_limpio(self):
        revisar(self, rut_limpio, [
            ('12.345.678-9', '123456789'),
            ('  12.345.678-9  ', '123456789'),
            ('20.001.550-9', '200015509'),
            ('200015509', '200015509'),
            ('12.345.678-k', '12345678K'),
            ('11.111.111-k', '11111111K'),
            ('AB-123456', 'AB123456'),
            ('', ''),
            (None, ''),
        ])

    def test_normalizar_rut_y_documento(self):
        self.assertEqual(normalizar_rut('12.345.678-9'), rut_limpio('12.345.678-9'))
        revisar(self, normalizar_documento, [('ab-123.456', 'AB123456'), ('', ''), (None, '')])


class ValidarRutTests(TestCase):
    """validar_rut, validar_rut_extranjero y validar_documento."""

    def test_validar_rut(self):
        revisar(self, validar_rut, [
            ('200015509', True),
            ('20.001.550-9', True),
            ('12345678-0', False),     # dígito verificador incorrecto
            ('123-4', False),          # muy corto
            ('1234567890-1', False),   # muy largo
            ('AB123456', False),       # cuerpo no numérico
            ('', False),
        ])

    def test_validar_rut_extranjero(self):
        revisar(self, validar_rut_extranjero, [
            ('20001550-9', True), ('12345678-K', True), ('AB123456', False), ('123-4', False),
        ])

    def test_validar_documento_segun_tipo(self):
        casos = [
            (('20.001.550-9', 'RUT'), True),
            (('12345678-0', 'RUT'), False),
            (('20001550-9', 'RUN_PROVISORIO'), True),
            (('20001550-9', 'CEDULA_EXTRANJERO'), True),
            (('AB123456', 'PASAPORTE'), True),
            (('AB1', 'PASAPORTE'), False),          # pasaporte muy corto
            (('20001550-9', 'OTRO'), True),         # tipo desconocido: no se bloquea
            (('', 'RUT'), False),
        ]
        revisar(self, lambda e: validar_documento(*e), casos)


class FormatearRutTests(TestCase):
    """rut_formateado (sin puntos, con guion) y formatear_rut (con puntos y guion)."""

    def test_rut_formateado(self):
        revisar(self, rut_formateado, [
            ('200015509', '20001550-9'),
            ('20.001.550-9', '20001550-9'),
            ('AB123456', 'AB123456'),   # pasaporte: se devuelve limpio, sin guion
            ('A', 'A'),
        ])

    def test_formatear_rut(self):
        revisar(self, formatear_rut, [
            ('123456789', '12.345.678-9'),
            ('12345678K', '12.345.678-K'),
            ('AB123456', 'AB123456'),
            ('A', 'A'),
        ])


class ExtraerRutDeCarnetTests(TestCase):
    """extraer_rut_de_carnet lee el RUT del QR del carnet o de un texto escrito a mano."""

    def test_extrae_el_rut(self):
        revisar(self, extraer_rut_de_carnet, [
            ('https://portal.sidiv.registrocivil.cl/consulta?RUN=12345678-9', '123456789'),
            ('https://portal.sidiv.registrocivil.cl/consulta?RUN=12345678-K', '12345678K'),
            ('https://x.cl?foo=bar&RUN=12345678-9&baz=qux', '123456789'),
            ('12345678-9', '123456789'),
            ('123456789012345', '123456789'),   # demasiado largo: se trunca
            ('', ''),
            (None, ''),
        ])


class BuscarAlumnoPorDocumentoTests(TestCase):
    """buscar_alumno_por_documento encuentra al alumno sin importar cómo se escriba el documento."""

    @classmethod
    def setUpTestData(cls):
        cls.alumno = Alumno.objects.create(
            rut='20001550-9', tipo_documento='RUT', nombres='Juan', apellidos='Pérez',
            correo='juan@example.com', carrera='Ingeniería', jornada='Diurna')
        cls.pasaporte = Alumno.objects.create(
            rut='AB123456', tipo_documento='PASAPORTE', nombres='Ana', apellidos='Gómez',
            correo='ana@example.com', carrera='Diseño', jornada='Vespertina')

    def test_encuentra_en_distintos_formatos(self):
        revisar(self, buscar_alumno_por_documento, [
            ('20001550-9', self.alumno),
            ('200015509', self.alumno),
            ('20.001.550-9', self.alumno),
            ('  20001550-9  ', self.alumno),
            ('AB123456', self.pasaporte),
            ('AB-123456', self.pasaporte),
        ])

    def test_sin_resultado_devuelve_none(self):
        revisar(self, buscar_alumno_por_documento, [
            ('99999999-9', None), ('', None), (None, None), ('   ', None),
        ])


class PaginarTests(TestCase):
    """paginar: página pedida, nombre del parámetro, tamaño de página y página fuera de rango."""

    def test_paginar(self):
        f = RequestFactory()
        items = list(range(50))
        pagina = paginar(f.get('/test/'), items)
        self.assertEqual((pagina.number, len(pagina.object_list)), (1, 15))
        self.assertEqual(paginar(f.get('/test/?page=2'), items).number, 2)
        self.assertEqual(paginar(f.get('/test/?page_insc=3'), items, param='page_insc').number, 3)
        self.assertEqual(len(paginar(f.get('/test/'), items, por_pagina=5).object_list), 5)
        fuera = paginar(f.get('/test/?page=999'), items)
        self.assertEqual(fuera.number, fuera.paginator.num_pages)


# Entradas hostiles reutilizadas por las pruebas de caracteres especiales
ENTRADAS_HOSTILES = [
    "Bernardo O`higgins",
    "Bernardo O'Higgins",
    'María "La Pepa" Pérez',
    "Ñancupil Müller-Åström",
    "Nguyễn Văn Ánh",
    "José (NFD)",
    "Robert'); DROP TABLE alumno;--",
    "<script>alert(1)</script>",
    '=HYPERLINK("http://x.com")',
    "+56912345678",
    "-Pedro",
    "@usuario",
    "Nombre\x00Con\x00Nul",
    "Línea1\nLínea2",
    "‮oediv",
    "😀 Emoji",
    "  espacios   múltiples  ",
    "100% & más #1",
]


class LimpiarTextoTestCase(TestCase):
    """limpiar_texto conserva lo legítimo (apóstrofes, tildes) y quita lo peligroso."""

    def test_limpiar_texto(self):
        revisar(self, limpiar_texto, [
            ("O`higgins", "O`higgins"),
            ("O'Higgins", "O'Higgins"),
            ("Peña Müller", "Peña Müller"),
            ("A\x00B", "AB"),               # carácter nulo
            ("‮ABC", "ABC"),           # control de dirección del texto
            ("a\nb", "a b"),                # una sola línea por defecto
            ("José", "José"),    # se normaliza a NFC
            (None, None),
        ])
        self.assertEqual(limpiar_texto("a\nb", una_linea=False), "a\nb")


class AlumnoCaracteresTestCase(TestCase):
    """Guardar y leer alumnos con entradas hostiles nunca debe fallar."""

    def test_entradas_hostiles_se_guardan_limpias(self):
        for i, texto in enumerate(ENTRADAS_HOSTILES):
            with self.subTest(texto=repr(texto)):
                a = Alumno.objects.create(
                    rut=f"T{i}", nombres=texto[:100], apellidos=texto[:100],
                    correo="a@b.cl", carrera=texto[:100], jornada="Diurno",
                )
                a.refresh_from_db()
                self.assertNotIn("\x00", a.nombres)
                self.assertNotIn("\n", a.nombres)
                self.assertNotIn("\u202e", a.nombres)

    def test_apostrofe_se_conserva_en_bbdd(self):
        a = Alumno.objects.create(
            rut="X1", nombres="Bernardo", apellidos="O`higgins",
            correo="a@b.cl", carrera="X", jornada="Y",
        )
        a.refresh_from_db()
        self.assertEqual(a.apellidos, "O`higgins")

    def test_nfc_en_modelo(self):
        a = Alumno.objects.create(
            rut="X2", nombres="Jose\u0301", apellidos="P",
            correo="a@b.cl", carrera="X", jornada="Y",
        )
        a.refresh_from_db()
        self.assertEqual(a.nombres, "Jos\u00e9")

    def test_rut_vacio_se_guarda_como_none(self):
        a = Alumno.objects.create(
            rut="", nombres="A", apellidos="B",
            correo="a@b.cl", carrera="X", jornada="Y",
        )
        b = Alumno.objects.create(
            rut="", nombres="C", apellidos="D",
            correo="c@d.cl", carrera="X", jornada="Y",
        )
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertIsNone(a.rut)
        self.assertIsNone(b.rut)  # sin la conversión, el segundo chocaría por unique


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

    def test_el_campo_del_escaner_acepta_el_texto_largo_de_un_qr(self):
        # El QR del carnet mide ~170 caracteres; con maxlength=30 se corta
        # y el sistema no encuentra al alumno.
        ahora = timezone.now()
        act = Actividad.objects.create(
            titulo='Masiva campo', descripcion='desc', tipo='MASIVA',
            lugar='Patio', fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=2),
            estado='ACTIVA', cupos_totales=None, cupos_disponibles=None,
            creado_por=self.admin,
        )
        sesion = self.client.session
        sesion['actividad_escaneo_id'] = act.pk
        sesion.save()

        r = self.client.get('/escaneo/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        m = re.search(r'<input\b(?:(?!>).)*?id="rutInput"(?:(?!>).)*>', html, re.DOTALL)
        self.assertIsNotNone(m, 'no aparece el campo rutInput')
        l = re.search(r'maxlength="(\d+)"', m.group(0))
        limite = int(l.group(1)) if l else 10**6
        self.assertGreaterEqual(limite, 300)
