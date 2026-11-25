"""
Imágenes de las actividades: tamaño razonable y miniatura.

- Al subir una imagen (ActividadForm.clean_imagen) se gira según la orientación de la cámara, se le quitan los
  metadatos (ubicación GPS, modelo de cámara) y, si es más grande, se achica a LADO_MAXIMO px por su lado mayor.
  Una foto de celular de varios MB queda en unos cientos de KB, sin diferencia visible en pantalla.
- Cada actividad con imagen tiene una miniatura JPEG de LADO_MINIATURA px (unos 10 KB), que usan el escáner y la
  lista para elegir actividad. La crea la señal de este archivo al guardar la actividad, así que también se crea
  si la imagen llega por otro camino (admin, comando optimizar_imagenes).
- Cada actividad con imagen tiene además una versión para los correos (IMAGEN_CORREO, JPEG de 1200x600, unos
  100 KB): siempre del mismo alto, así el correo se ve parejo y, si el programa de correo bloquea las imágenes, el
  recuadro que ocupa su lugar tiene el tamaño justo. Si la imagen no tiene esa forma (un afiche vertical, por
  ejemplo) no se recorta: va entera al centro sobre un fondo hecho con la misma imagen difuminada. Es JPEG porque
  Outlook para Windows no muestra WebP.
- Los GIF se guardan tal cual (achicarlos perdería la animación); su miniatura sale del primer cuadro.
"""
import io
import logging
import os

from PIL import Image, ImageFilter, ImageOps

from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

LADO_MAXIMO = 1600
LADO_MINIATURA = 160
CALIDAD = {'JPEG': 85, 'WEBP': 85}
CARPETA_MINIATURAS = 'actividades/miniaturas/'
IMAGEN_CORREO = (1200, 600)
CARPETA_CORREO = 'actividades/correo/'
AZUL = (0, 47, 95)


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


def imagen_correo(archivo):
    """Bytes JPEG de la imagen para los correos: IMAGEN_CORREO px, sin cortar lo importante."""
    ancho, alto = IMAGEN_CORREO
    with Image.open(archivo) as img:
        img.seek(0)
        img = _a_rgb(ImageOps.exif_transpose(img))
        proporcion = img.width / img.height
        if 1.7 <= proporcion <= 2.4:
            # Casi de la misma forma: se recorta un poco por los bordes y llena todo el espacio
            lienzo = ImageOps.fit(img, IMAGEN_CORREO, Image.LANCZOS)
        else:
            # Afiche vertical o imagen cuadrada: entera al centro, sobre un fondo de ella misma difuminada
            fondo = ImageOps.fit(img, (ancho // 4, alto // 4), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
            fondo = Image.blend(fondo.resize(IMAGEN_CORREO, Image.LANCZOS), Image.new('RGB', IMAGEN_CORREO, AZUL), 0.45)
            frente = img.copy()
            frente.thumbnail(IMAGEN_CORREO, Image.LANCZOS)
            fondo.paste(frente, ((ancho - frente.width) // 2, (alto - frente.height) // 2))
            lienzo = fondo
        salida = io.BytesIO()
        lienzo.save(salida, format='JPEG', quality=80, optimize=True, progressive=True)
        return salida.getvalue()


# Versiones derivadas de la imagen: campo del modelo -> (carpeta, sufijo del nombre, función que la crea)
DERIVADAS = {
    'imagen_miniatura': (CARPETA_MINIATURAS, '_mini', miniatura),
    'imagen_correo': (CARPETA_CORREO, '_correo', imagen_correo),
}


def nombre_derivada(nombre_imagen, campo):
    base = os.path.splitext(os.path.basename(nombre_imagen))[0]
    return f'{base}{DERIVADAS[campo][1]}.jpg'


def nombre_miniatura(nombre_imagen):
    return nombre_derivada(nombre_imagen, 'imagen_miniatura')


def _corresponde(actividad, campo='imagen_miniatura'):
    """True si la versión guardada en `campo` es la de la imagen actual."""
    guardada = getattr(actividad, campo).name or ''
    if not guardada:
        return False
    esperado = os.path.splitext(nombre_derivada(actividad.imagen.name, campo))[0]
    return os.path.basename(guardada).startswith(esperado)


def _borrar(storage, nombre):
    if nombre:
        try:
            storage.delete(nombre)
        except Exception:
            logger.exception('No se pudo borrar la imagen %s', nombre)


def _actualizar(actividad, campo, forzar=False):
    """Crea, cambia o quita la versión `campo` según la imagen actual. Devuelve True si cambió algo."""
    from ..models import Actividad
    archivo_campo = getattr(actividad, campo)
    anterior = archivo_campo.name or ''
    if not actividad.imagen:
        if not anterior:
            return False
        _borrar(archivo_campo.storage, anterior)
        Actividad.objects.filter(pk=actividad.pk).update(**{campo: ''})
        setattr(actividad, campo, None)
        return True
    if not forzar and _corresponde(actividad, campo):
        return False
    carpeta, _, crear = DERIVADAS[campo]
    try:
        with actividad.imagen.open('rb') as archivo:
            datos = crear(archivo)
    except Exception:
        logger.exception('No se pudo crear %s de la actividad %s', campo, actividad.pk)
        return False
    nuevo = archivo_campo.storage.save(carpeta + nombre_derivada(actividad.imagen.name, campo), ContentFile(datos))
    if anterior and anterior != nuevo:
        _borrar(archivo_campo.storage, anterior)
    Actividad.objects.filter(pk=actividad.pk).update(**{campo: nuevo})
    setattr(actividad, campo, nuevo)
    return True


def actualizar_miniatura(actividad, forzar=False):
    return _actualizar(actividad, 'imagen_miniatura', forzar)


def actualizar_imagen_correo(actividad, forzar=False):
    return _actualizar(actividad, 'imagen_correo', forzar)


def actualizar_derivadas(actividad, forzar=False):
    """Miniatura e imagen para correos. Devuelve True si cambió alguna."""
    return any([_actualizar(actividad, campo, forzar) for campo in DERIVADAS])


@receiver(post_save, sender='gestion.Actividad', dispatch_uid='miniatura_actividad')
def miniatura_al_guardar(sender, instance, raw=False, **kwargs):
    if not raw:
        actualizar_derivadas(instance)
