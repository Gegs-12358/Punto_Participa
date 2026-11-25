"""
Achica las imágenes de actividades ya guardadas y crea las miniaturas que falten (servicios/imagenes.py).

Las imágenes subidas desde ahora ya quedan así; este comando es para las anteriores. Sin --aplicar solo muestra
qué haría. Con --aplicar reemplaza los archivos grandes por su versión achicada: haz un respaldo antes.

    python manage.py optimizar_imagenes            # ver qué haría
    python manage.py optimizar_imagenes --aplicar  # hacerlo
"""
from PIL import Image

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from ...models import Actividad
from ...servicios import imagenes


def _kb(n):
    return f'{n / 1024:,.0f} KB'.replace(',', '.')


class Command(BaseCommand):
    help = 'Achica las imágenes grandes de las actividades y crea las miniaturas que falten.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Hacer los cambios (sin esto solo los muestra).')

    def handle(self, *args, aplicar=False, **opciones):
        antes = despues = achicadas = miniaturas = faltan = 0
        for actividad in Actividad.objects.exclude(imagen='').exclude(imagen__isnull=True).order_by('pk'):
            storage, nombre = actividad.imagen.storage, actividad.imagen.name
            if not storage.exists(nombre):
                faltan += 1
                self.stdout.write(f'  {actividad.pk}: falta el archivo {nombre}')
                continue
            tamano = storage.size(nombre)
            antes += tamano
            try:
                with storage.open(nombre, 'rb') as archivo, Image.open(archivo) as img:
                    formato = img.format
                    grande = max(img.size) > imagenes.LADO_MAXIMO
                    datos = imagenes.preparar(img, formato) if grande and formato != 'GIF' else None
            except Exception as e:
                self.stdout.write(f'  {actividad.pk}: no se pudo leer {nombre} ({e})')
                despues += tamano
                continue
            if datos is not None and len(datos) < tamano:
                achicadas += 1
                self.stdout.write(f'  {actividad.pk}: {nombre} {_kb(tamano)} -> {_kb(len(datos))}')
                despues += len(datos)
                if aplicar:
                    storage.delete(nombre)
                    guardado = storage.save(nombre, ContentFile(datos))
                    if guardado != nombre:
                        Actividad.objects.filter(pk=actividad.pk).update(imagen=guardado)
                        actividad.imagen.name = guardado
                    imagenes.actualizar_miniatura(actividad, forzar=True)
            else:
                despues += tamano
            if not imagenes._corresponde(actividad):
                miniaturas += 1
                if aplicar:
                    imagenes.actualizar_miniatura(actividad)

        verbo = 'Se achicaron' if aplicar else 'Se achicarían'
        self.stdout.write(f'{verbo} {achicadas} imágenes: de {_kb(antes)} a {_kb(despues)} en total.')
        self.stdout.write(f'Miniaturas {"creadas" if aplicar else "por crear"}: {miniaturas}.')
        if faltan:
            self.stdout.write(f'Imágenes cuyo archivo no está: {faltan}.')
        if not aplicar and (achicadas or miniaturas):
            self.stdout.write('Para hacerlo, respalda primero y corre: python manage.py optimizar_imagenes --aplicar')
