"""
Imágenes de las actividades: tamaño razonable y miniatura.

- Al subir una imagen (ActividadForm.clean_imagen) se gira según la orientación de la cámara, se le quitan los
  metadatos (ubicación GPS, modelo de cámara) y, si es más grande, se achica a LADO_MAXIMO px por su lado mayor.
  Una foto de celular de varios MB queda en unos cientos de KB, sin diferencia visible en pantalla.
- Cada actividad con imagen tiene una miniatura JPEG de LADO_MINIATURA px (unos 10 KB), que usan el escáner y la
  lista para elegir actividad. La crea la señal de este archivo al guardar la actividad, así que también se crea
  si la imagen llega por otro camino (admin, comando optimizar_imagenes).
- Los GIF se guardan tal cual (achicarlos perdería la animación); su miniatura sale del primer cuadro.
"""
import io
import logging
import os

from PIL import Image, ImageOps

from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

LADO_MAXIMO = 1600
LADO_MINIATURA = 160
CALIDAD = {'JPEG': 85, 'WEBP': 85}
CARPETA_MINIATURAS = 'actividades/miniaturas/'


def preparar(img, formato):
    """Imagen girada según su orientación, sin metadatos y con su lado mayor en LADO_MAXIMO px como máximo.
    Devuelve los bytes en el mismo formato."""
    img = ImageOps.exif_transpose(img)
    if img.mode == 'P':   # paleta (PNG de pocos colores): a RGBA para no perder la transparencia
        img = img.convert('RGBA')
    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
    limpia = Image.new(img.mode, img.size)
    limpia.paste(img)
    salida = io.BytesIO()
    limpia.save(salida, format=formato, optimize=True, **({'quality': CALIDAD[formato]} if formato in CALIDAD else {}))
    return salida.getvalue()


def _a_rgb(img):
    """Para guardar en JPEG: las transparencias quedan sobre fondo blanco."""
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        fondo = Image.new('RGB', img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert('RGB')


def miniatura(archivo):
    """Bytes JPEG de la miniatura de una imagen (archivo abierto o ruta)."""
    with Image.open(archivo) as img:
        img.seek(0)
        img = _a_rgb(ImageOps.exif_transpose(img))
        img.thumbnail((LADO_MINIATURA, LADO_MINIATURA), Image.LANCZOS)
        salida = io.BytesIO()
        img.save(salida, format='JPEG', quality=80, optimize=True)
        return salida.getvalue()


def nombre_miniatura(nombre_imagen):
    base = os.path.splitext(os.path.basename(nombre_imagen))[0]
    return f'{base}_mini.jpg'


def _corresponde(actividad):
    """True si la miniatura guardada es la de la imagen actual."""
    mini = actividad.imagen_miniatura.name or ''
    if not mini:
        return False
    esperado = os.path.splitext(nombre_miniatura(actividad.imagen.name))[0]
    return os.path.basename(mini).startswith(esperado)


def _borrar(storage, nombre):
    if nombre:
        try:
            storage.delete(nombre)
        except Exception:
            logger.exception('No se pudo borrar la miniatura %s', nombre)


def actualizar_miniatura(actividad, forzar=False):
    """Crea, cambia o quita la miniatura según la imagen actual. Devuelve True si cambió algo."""
    from ..models import Actividad
    campo = actividad.imagen_miniatura
    anterior = campo.name or ''
    if not actividad.imagen:
        if not anterior:
            return False
        _borrar(campo.storage, anterior)
        Actividad.objects.filter(pk=actividad.pk).update(imagen_miniatura='')
        actividad.imagen_miniatura = None
        return True
    if not forzar and _corresponde(actividad):
        return False
    try:
        with actividad.imagen.open('rb') as archivo:
            datos = miniatura(archivo)
    except Exception:
        logger.exception('No se pudo crear la miniatura de la actividad %s', actividad.pk)
        return False
    nuevo = campo.storage.save(CARPETA_MINIATURAS + nombre_miniatura(actividad.imagen.name), ContentFile(datos))
    if anterior and anterior != nuevo:
        _borrar(campo.storage, anterior)
    Actividad.objects.filter(pk=actividad.pk).update(imagen_miniatura=nuevo)
    actividad.imagen_miniatura = nuevo
    return True


@receiver(post_save, sender='gestion.Actividad', dispatch_uid='miniatura_actividad')
def miniatura_al_guardar(sender, instance, raw=False, **kwargs):
    if not raw:
        actualizar_miniatura(instance)
