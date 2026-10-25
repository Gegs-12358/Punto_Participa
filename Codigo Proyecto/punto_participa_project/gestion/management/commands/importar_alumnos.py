"""
Importa alumnos desde un .xlsx o .csv.

Uso:
    python manage.py importar_alumnos nomina.csv --simular   # no guarda nada
    python manage.py importar_alumnos nomina.xlsx            # guarda

Sincroniza: crea los nuevos, actualiza los que cambiaron y BLOQUEA (no borra)
a los alumnos activos que no vienen en el archivo.

Columnas: rut ; tipo_documento (opcional) ; nombres ; apellidos ; correo ; carrera ; jornada
"""

import os

from django.core.management.base import BaseCommand, CommandError

from gestion.importador_alumnos import (
    ArchivoInvalido, analizar, aplicar, bloqueo_masivo, leer_filas,
)
from gestion.models import LogAuditoria


class Command(BaseCommand):
    help = 'Importa alumnos desde un archivo .xlsx o .csv (crea o actualiza por documento).'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str)
        parser.add_argument('--simular', action='store_true',
                            help='Muestra el resumen sin guardar nada.')
        parser.add_argument('--confirmar-bloqueo-masivo', action='store_true',
                            help='Permite bloquear a mas del 20%% de los alumnos activos.')
        parser.add_argument('--max-errores', type=int, default=30,
                            help='Cantidad de errores a listar (default: 30).')

    def handle(self, *args, **options):
        ruta = options['archivo']
        if not os.path.isfile(ruta):
            raise CommandError(f'No existe el archivo: {ruta}')

        try:
            with open(ruta, 'rb') as f:
                filas = leer_filas(f, os.path.basename(ruta))
        except ArchivoInvalido as e:
            raise CommandError(str(e))

        res = analizar(filas)

        self.stdout.write(f'Filas leidas:   {res.total}')
        self.stdout.write(self.style.SUCCESS(f'Nuevos:         {len(res.nuevos)}'))
        self.stdout.write(self.style.SUCCESS(f'Actualizados:   {len(res.actualizados)}'))
        self.stdout.write(f'Sin cambios:    {res.sin_cambios}')
        self.stdout.write(self.style.WARNING(
            f'A bloquear:     {len(res.bloqueados)} (de {res.total_activos} activos)'))
        self.stdout.write((self.style.ERROR if res.errores else self.style.SUCCESS)(
            f'Con error:      {len(res.errores)}'))

        for fila, msg in res.errores[:options['max_errores']]:
            self.stdout.write(self.style.ERROR(f'  Fila {fila}: {msg}'))
        if len(res.errores) > options['max_errores']:
            self.stdout.write(f'  ... y {len(res.errores) - options["max_errores"]} mas.')
        for fila, datos, cambios in res.actualizados[:10]:
            detalle = '; '.join(f'{c}: {a!r} -> {d!r}' for c, a, d in cambios)
            self.stdout.write(f'  Fila {fila} cambia: {detalle}')
        for doc, nombre in res.bloqueados[:10]:
            self.stdout.write(self.style.WARNING(f'  Se bloquea: {doc} ({nombre})'))
        for fila, msg in res.avisos[:10]:
            self.stdout.write(self.style.WARNING(f'  Fila {fila}: {msg}'))

        if options['simular']:
            self.stdout.write(self.style.NOTICE('\nSimulacion: no se guardo nada.'))
            return

        if bloqueo_masivo(res) and not options['confirmar_bloqueo_masivo']:
            raise CommandError(
                f'Se bloquearian {len(res.bloqueados)} de {res.total_activos} alumnos activos. '
                'Revisa que el archivo sea la nomina completa. '
                'Si es correcto, repite con --confirmar-bloqueo-masivo.')

        if not (res.nuevos or res.actualizados or res.bloqueados):
            self.stdout.write('Nada que guardar.')
            return

        creados, actualizados, bloqueados = aplicar(res)
        LogAuditoria.objects.create(
            usuario_sistema=None, modulo='Alumnos', accion='Importacion de alumnos',
            detalle=(f'Archivo {os.path.basename(ruta)}: {creados} creados, '
                     f'{actualizados} actualizados, {bloqueados} bloqueados, '
                     f'{len(res.errores)} con error'),
        )
        self.stdout.write(self.style.SUCCESS(
            f'\nGuardado: {creados} creados, {actualizados} actualizados, '
            f'{bloqueados} bloqueados. Las filas con error no se importaron.'))
