import io
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from .forms import ActividadForm


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
        with mock.patch("gestion.forms.Image.new", side_effect=OSError("falla")):
            resultado = _limpiar(archivo)
        self.assertIs(resultado, archivo)
