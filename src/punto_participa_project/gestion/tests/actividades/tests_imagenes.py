"""
Imágenes de las actividades: tamaño máximo al subirlas, miniatura y comando para las ya guardadas.

Correr solo este archivo:
    python manage.py test gestion.tests.actividades.tests_imagenes --noinput
"""
import io
import os
import shutil
import tempfile
from datetime import date, timedelta
from io import StringIO

from PIL import Image

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ...forms import ActividadForm
from ...models import Actividad, AvisoRetencion
from ...servicios import imagenes
from ...servicios.retencion import ciclo
from ..base import BaseSistemaTestCase, HorarioAbierto


class ConMediaPropia(BaseSistemaTestCase):
    """Cada clase usa su propia carpeta de archivos: las pruebas corren en paralelo y unas borran archivos."""
    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp()
        cls._ajuste = override_settings(MEDIA_ROOT=cls._media)
        cls._ajuste.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._ajuste.disable()
        shutil.rmtree(cls._media, ignore_errors=True)


def _bytes(formato='JPEG', tamano=(3000, 2000), modo='RGB', color=(0, 80, 160), **opciones):
    salida = io.BytesIO()
    Image.new(modo, tamano, color).save(salida, format=formato, **opciones)
    return salida.getvalue()


def _limpiar(archivo):
    form = ActividadForm()
    form.cleaned_data = {'imagen': archivo}
    return form.clean_imagen()


def _abrir(archivo):
    archivo.seek(0)
    return Image.open(io.BytesIO(archivo.read()))


class ImagenAlSubirTests(ConMediaPropia):
    def test_una_foto_grande_queda_en_1600_px_por_su_lado_mayor(self):
        resultado = _abrir(_limpiar(SimpleUploadedFile('foto.jpg', _bytes(tamano=(4000, 3000)))))
        self.assertEqual(resultado.size, (1600, 1200))
        self.assertEqual(resultado.format, 'JPEG')

    def test_una_imagen_chica_no_se_agranda(self):
        resultado = _abrir(_limpiar(SimpleUploadedFile('chica.png', _bytes('PNG', (300, 200)))))
        self.assertEqual(resultado.size, (300, 200))

    def test_una_foto_de_celular_vertical_queda_derecha(self):
        exif = Image.Exif()
        exif[0x0112] = 6   # orientación: girada 90°, como la guardan muchos celulares
        datos = _bytes(tamano=(400, 100), exif=exif)
        resultado = _abrir(_limpiar(SimpleUploadedFile('vertical.jpg', datos)))
        self.assertEqual(resultado.size, (100, 400))
        self.assertEqual(len(resultado.getexif()), 0)

    def test_un_png_transparente_sigue_siendo_png_con_transparencia(self):
        datos = _bytes('PNG', (2400, 1200), 'RGBA', (0, 0, 0, 0))
        resultado = _abrir(_limpiar(SimpleUploadedFile('logo.png', datos)))
        self.assertEqual((resultado.format, resultado.mode, resultado.size), ('PNG', 'RGBA', (1600, 800)))

    def test_un_png_de_paleta_conserva_la_transparencia(self):
        img = Image.new('P', (50, 50))
        img.info['transparency'] = 0
        salida = io.BytesIO()
        img.save(salida, 'PNG', transparency=0)
        resultado = _abrir(_limpiar(SimpleUploadedFile('icono.png', salida.getvalue())))
        self.assertEqual(resultado.mode, 'RGBA')
        self.assertEqual(resultado.getpixel((0, 0))[3], 0)


class MiniaturaTests(HorarioAbierto, ConMediaPropia):
    def con_imagen(self, datos, nombre='portada.jpg', actividad=None):
        actividad = actividad or self.actividad_masiva
        actividad.imagen = ContentFile(datos, name=nombre)
        actividad.save()
        actividad.refresh_from_db()
        return actividad

    def test_al_guardar_una_imagen_se_crea_su_miniatura(self):
        a = self.con_imagen(_bytes(tamano=(1200, 600)))
        self.assertTrue(a.imagen_miniatura.name.startswith('actividades/miniaturas/'))
        with a.imagen_miniatura.open('rb') as f, Image.open(f) as mini:
            self.assertEqual((mini.format, mini.size), ('JPEG', (160, 80)))
        self.assertLess(a.imagen_miniatura.size, 15 * 1024)

    def test_guardar_de_nuevo_sin_cambiar_la_imagen_no_la_rehace(self):
        a = self.con_imagen(_bytes(tamano=(300, 300)))
        antes = a.imagen_miniatura.name
        a.titulo = 'Otro título'
        a.save()
        a.refresh_from_db()
        self.assertEqual(a.imagen_miniatura.name, antes)

    def test_al_cambiar_la_imagen_cambia_la_miniatura_y_se_borra_la_anterior(self):
        a = self.con_imagen(_bytes(tamano=(300, 300)), 'primera.jpg')
        vieja = a.imagen_miniatura.name
        a = self.con_imagen(_bytes(tamano=(300, 300), color=(200, 0, 0)), 'segunda.jpg', a)
        self.assertIn('segunda', a.imagen_miniatura.name)
        self.assertFalse(default_storage.exists(vieja))

    def test_sin_imagen_no_hay_miniatura_y_quitarla_la_borra(self):
        self.assertFalse(self.actividad_masiva.imagen_miniatura)
        a = self.con_imagen(_bytes(tamano=(300, 300)))
        mini = a.imagen_miniatura.name
        a.imagen = None
        a.save()
        a.refresh_from_db()
        self.assertFalse(a.imagen_miniatura)
        self.assertFalse(default_storage.exists(mini))

    def test_un_gif_animado_tiene_miniatura_del_primer_cuadro(self):
        cuadros = [Image.new('RGB', (200, 100), c) for c in ((255, 0, 0), (0, 255, 0))]
        salida = io.BytesIO()
        cuadros[0].save(salida, 'GIF', save_all=True, append_images=cuadros[1:])
        a = self.con_imagen(salida.getvalue(), 'animado.gif')
        with a.imagen.open('rb') as f, Image.open(f) as gif:
            self.assertEqual(gif.n_frames, 2)
        self.assertTrue(a.imagen_miniatura)

    def test_si_la_imagen_no_se_puede_leer_no_se_cae_al_guardar(self):
        a = self.con_imagen(b'no es una imagen', 'rota.jpg')
        self.assertFalse(a.imagen_miniatura)

    def test_el_escaner_muestra_las_miniaturas_al_elegir_actividad(self):
        self.con_imagen(_bytes(tamano=(300, 300)))
        self.login_as(self.registrador)
        resp = self.client.get(reverse('escaneo'))
        self.assertContains(resp, 'class="elegir-actividad__mini"')
        self.assertContains(resp, 'loading="lazy"')
        self.assertContains(resp, 'genericas/taller_mini')   # el taller no tiene imagen: va la genérica

    @override_settings(RETENCION_ANIOS=2, RETENCION_AVISOS_DIAS=[10, 7, 3])
    def test_la_retencion_borra_la_imagen_y_la_miniatura(self):
        a = self.con_imagen(_bytes(tamano=(300, 300)))
        archivos = [a.imagen.name, a.imagen_miniatura.name]
        hace_3 = timezone.now() - timedelta(days=3 * 365)
        Actividad.objects.filter(pk=a.pk).update(fecha_inicio=hace_3, fecha_fin=hace_3 + timedelta(hours=2))
        ciclo(date(2026, 11, 15))
        self.login_as(self.admin)
        aviso = AvisoRetencion.objects.get()
        self.client.post(reverse('retencion_ejecutar', args=[aviso.pk]), {'verificado': 'on'})
        self.assertFalse(Actividad.objects.filter(pk=a.pk).exists())
        for nombre in archivos:
            self.assertFalse(default_storage.exists(nombre), nombre)


class ComandoOptimizarImagenesTests(ConMediaPropia):
    def setUp(self):
        # Imagen grande guardada antes de este cambio: sin pasar por el formulario y sin miniatura
        self.actividad_masiva.imagen = ContentFile(_bytes(tamano=(3200, 1600)), name='antigua.jpg')
        self.actividad_masiva.save()
        Actividad.objects.filter(pk=self.actividad_masiva.pk).update(imagen_miniatura='')
        self.actividad_masiva.refresh_from_db()

    def correr(self, *args):
        salida = StringIO()
        call_command('optimizar_imagenes', *args, stdout=salida)
        self.actividad_masiva.refresh_from_db()
        return salida.getvalue()

    def tamano(self):
        with self.actividad_masiva.imagen.open('rb') as f, Image.open(f) as img:
            return img.size

    def test_sin_aplicar_solo_muestra_lo_que_haria(self):
        salida = self.correr()
        self.assertIn('Se achicarían 1 imágenes', salida)
        self.assertIn('imagen para correos por crear: 1', salida)
        self.assertIn('--aplicar', salida)
        self.assertEqual(self.tamano(), (3200, 1600))
        self.assertFalse(self.actividad_masiva.imagen_miniatura)

    def test_con_aplicar_achica_y_crea_la_miniatura(self):
        salida = self.correr('--aplicar')
        self.assertIn('Se achicaron 1 imágenes', salida)
        self.assertEqual(self.tamano(), (1600, 800))
        self.assertTrue(self.actividad_masiva.imagen_miniatura)
        self.assertIn('Se achicaron 0 imágenes', self.correr('--aplicar'))   # la segunda vez no hay nada que hacer

    def test_avisa_si_falta_el_archivo(self):
        os.remove(self.actividad_masiva.imagen.path)
        self.assertIn('Imágenes cuyo archivo no está: 1', self.correr())
