"""
Formulario de actividades: fechas, cupos, carreras y jornadas, imagen subida y textos hostiles.

Correr solo este archivo:
    python manage.py test gestion.tests.actividades.tests_formularios --noinput
"""
from datetime import timedelta
import io
from unittest import mock

from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Carrera, Inscripcion, Jornada, Lugar
from ..base import BaseSistemaTestCase


class ActividadFormReglasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(
            nombre="Ingeniería en Informática",
            escuela="Escuela de Informática y Telecomunicaciones",
        )
        cls.jornada = Jornada.objects.create(nombre="Diurno")
        Lugar.objects.create(nombre="Sala 2")

    def _datos(self, **cambios):
        inicio = timezone.localtime(timezone.now() + timedelta(days=3))
        fin = inicio + timedelta(hours=1)
        datos = {
            "titulo": "Actividad de prueba",
            "descripcion": "Descripción",
            "tipo": "MASIVA",
            "lugar": "Sala 2",
            "fecha_inicio_fecha": inicio.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": inicio.strftime("%H:%M"),
            "fecha_fin_fecha": fin.strftime("%Y-%m-%d"),
            "fecha_fin_hora": fin.strftime("%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        datos.update(cambios)
        return datos

    def test_datos_base_son_validos(self):
        form = ActividadForm(data=self._datos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_fecha_de_termino_igual_al_inicio_es_error(self):
        base = self._datos()
        form = ActividadForm(data=self._datos(
            fecha_fin_fecha=base["fecha_inicio_fecha"],
            fecha_fin_hora=base["fecha_inicio_hora"],
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_fin_fecha", form.errors)

    def test_fecha_de_termino_anterior_al_inicio_es_error(self):
        anterior = timezone.localtime(timezone.now() + timedelta(days=2))
        form = ActividadForm(data=self._datos(
            fecha_fin_fecha=anterior.strftime("%Y-%m-%d"),
            fecha_fin_hora=anterior.strftime("%H:%M"),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_fin_fecha", form.errors)

    def test_taller_con_cupo_cero_es_error(self):
        form = ActividadForm(data=self._datos(tipo="TALLER", cupos_totales=0))
        self.assertFalse(form.is_valid())
        self.assertIn("cupos_totales", form.errors)

    def test_taller_sin_cupo_es_error(self):
        form = ActividadForm(data=self._datos(tipo="TALLER"))
        self.assertFalse(form.is_valid())
        self.assertIn("cupos_totales", form.errors)

    def test_fecha_de_inicio_en_el_pasado_es_error(self):
        pasado = timezone.localtime(timezone.now() - timedelta(days=1))
        fin = pasado + timedelta(hours=1)
        form = ActividadForm(data=self._datos(
            fecha_inicio_fecha=pasado.strftime("%Y-%m-%d"),
            fecha_inicio_hora=pasado.strftime("%H:%M"),
            fecha_fin_fecha=fin.strftime("%Y-%m-%d"),
            fecha_fin_hora=fin.strftime("%H:%M"),
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_inicio_fecha", form.errors)


def _bytes_imagen(formato, **opciones):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buffer, format=formato, **opciones)
    return buffer.getvalue()


def _archivo(formato, nombre, **opciones):
    return SimpleUploadedFile(nombre, _bytes_imagen(formato, **opciones))


def _limpiar(valor):
    form = ActividadForm()
    form.cleaned_data = {"imagen": valor}
    return form.clean_imagen()


class CleanImagenTests(TestCase):
    def test_valor_que_no_es_archivo_nuevo_se_devuelve_igual(self):
        self.assertIsNone(_limpiar(None))
        self.assertEqual(_limpiar("imagenes/vieja.png"), "imagenes/vieja.png")

    def test_rechaza_imagen_demasiado_grande(self):
        archivo = _archivo("PNG", "grande.png")
        archivo.size = ActividadForm.TAMANO_MAXIMO_IMAGEN + 1
        with self.assertRaisesMessage(ValidationError, "no puede superar"):
            _limpiar(archivo)

    def test_rechaza_contenido_que_no_es_imagen(self):
        archivo = SimpleUploadedFile("falsa.png", b"esto no es una imagen")
        with self.assertRaisesMessage(ValidationError, "no es una imagen"):
            _limpiar(archivo)

    def test_rechaza_formato_valido_pero_no_permitido(self):
        archivo = _archivo("BMP", "mapa.bmp")
        with self.assertRaisesMessage(ValidationError, "Formato de imagen no permitido"):
            _limpiar(archivo)

    def test_gif_se_devuelve_sin_reprocesar(self):
        archivo = _archivo("GIF", "animado.gif")
        self.assertIs(_limpiar(archivo), archivo)

    def test_png_se_reconstruye_y_sigue_siendo_png(self):
        resultado = _limpiar(_archivo("PNG", "foto.png"))
        self.assertIsInstance(resultado, ContentFile)
        resultado.seek(0)
        imagen = Image.open(io.BytesIO(resultado.read()))
        self.assertEqual(imagen.format, "PNG")
        self.assertEqual(imagen.size, (8, 8))

    def test_jpeg_pierde_los_metadatos_exif(self):
        exif = Image.Exif()
        exif[0x010F] = "CamaraSecreta"
        datos = _bytes_imagen("JPEG", exif=exif)
        self.assertTrue(Image.open(io.BytesIO(datos)).getexif())
        resultado = _limpiar(SimpleUploadedFile("foto.jpg", datos))
        resultado.seek(0)
        limpia = Image.open(io.BytesIO(resultado.read()))
        self.assertEqual(limpia.format, "JPEG")
        self.assertEqual(len(limpia.getexif()), 0)

    def test_si_falla_la_limpieza_se_usa_la_imagen_original(self):
        archivo = _archivo("PNG", "foto.png")
        with mock.patch("gestion.servicios.imagenes.Image.new", side_effect=OSError("falla")):
            resultado = _limpiar(archivo)
        self.assertIs(resultado, archivo)


class ModeloYFormularioIntegralTests(BaseSistemaTestCase):
    def test_propiedades_y_recalculo_de_cupos_del_taller(self):
        self.assertTrue(self.actividad.esta_activa)
        self.assertTrue(self.actividad.es_taller)
        self.assertFalse(self.actividad.esta_lleno)

        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.actividad.recalcular_cupos()
        self.assertEqual(self.actividad.cupos_disponibles, 1)

        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno_pasaporte)
        self.actividad.recalcular_cupos()
        self.assertEqual(self.actividad.cupos_disponibles, 0)
        self.assertTrue(self.actividad.esta_lleno)

    def test_actividad_masiva_no_mantiene_cupos(self):
        self.actividad_masiva.cupos_totales = 100
        self.actividad_masiva.cupos_disponibles = 100
        self.actividad_masiva.recalcular_cupos()
        self.assertIsNone(self.actividad_masiva.cupos_totales)
        self.assertIsNone(self.actividad_masiva.cupos_disponibles)

    def test_formulario_taller_requiere_cupo_carrera_jornada_y_fechas_validas(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        datos = {
            "titulo": "Nuevo taller",
            "descripcion": "Descripción suficientemente clara",
            "tipo": "TALLER",
            "lugar": "Sala 1",
            "cupos_totales": 20,
            "fecha_inicio_fecha": futuro.strftime("%Y-%m-%d"),
            "fecha_inicio_hora": futuro.strftime("%H:%M"),
            "fecha_fin_fecha": (futuro + timedelta(hours=2)).strftime("%Y-%m-%d"),
            "fecha_fin_hora": (futuro + timedelta(hours=2)).strftime("%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        actividad = form.save(commit=False)
        actividad.creado_por = self.creador
        actividad.save()
        form.save_m2m()
        self.assertEqual(actividad.cupos_disponibles, 20)

# Entradas hostiles reutilizadas por las pruebas de caracteres especiales
ENTRADAS_HOSTILES = [
    "Bernardo O`higgins",
    "Bernardo O'Higgins",
    'María "La Pepa" Pérez',
    "Ñancupil Müller-Åström",
    "Nguyễn Văn Ánh",
    "Jose\u0301 (NFD)",
    "Robert'); DROP TABLE alumno;--",
    "<script>alert(1)</script>",
    '=HYPERLINK("http://x.com")',
    "+56912345678",
    "-Pedro",
    "@usuario",
    "Nombre\x00Con\x00Nul",
    "Línea1\nLínea2",
    "\u202eoediv",
    "😀 Emoji",
    "  espacios   múltiples  ",
    "100% & más #1",
]


class ActividadFormCaracteresTestCase(TestCase):
    """El formulario de actividad limpia texto y nunca lanza excepciones."""

    def test_entradas_hostiles_no_lanzan_excepcion(self):
        for texto in ENTRADAS_HOSTILES:
            with self.subTest(texto=repr(texto)):
                f = ActividadForm(data={
                    "titulo": texto, "lugar": texto, "descripcion": texto,
                })
                f.is_valid()  # será inválido por otros campos; no debe lanzar
                for campo in ("titulo", "lugar", "descripcion"):
                    valor = f.cleaned_data.get(campo)
                    if valor is not None:
                        self.assertNotIn("\x00", valor)
                        self.assertNotIn("\u202e", valor)

    def test_titulo_y_descripcion_se_limpian(self):
        f = ActividadForm(data={
            "titulo": "  Feria\x00 de   O`higgins \n", "lugar": "x",
            "descripcion": "línea1\nlínea2",
        })
        f.is_valid()
        self.assertEqual(f.cleaned_data.get("titulo"), "Feria de O`higgins")
        self.assertEqual(f.cleaned_data.get("descripcion"), "línea1\nlínea2")
