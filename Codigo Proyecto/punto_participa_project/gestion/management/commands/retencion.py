"""
Retención de datos (ver gestion/retencion.py).

    python manage.py retencion            # un paso del ciclo: avisa o espera (nunca borra)
    python manage.py retencion --simular  # solo muestra qué se borraría hoy y el proceso abierto

El servicio "tareas" de docker-compose lo corre una vez al día.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from gestion import retencion


class Command(BaseCommand):
    help = ('Retención de datos: avisa a los Administradores que hay datos de más de RETENCION_ANIOS años. '
            'El borrado lo ejecuta un Administrador desde el Inicio.')

    def add_arguments(self, parser):
        parser.add_argument('--simular', action='store_true', help='No envía ni borra nada.')

    def handle(self, *args, **opciones):
        hoy = timezone.localdate()
        if opciones['simular']:
            corte = retencion.fecha_corte(hoy)
            self.stdout.write(f'Fecha de corte hoy: {corte:%d/%m/%Y}')
            for clave, valor in retencion.calcular(corte).items():
                self.stdout.write(f'  {clave}: {valor}')
            abierto = retencion.proceso_abierto()
            if abierto:
                self.stdout.write(f'Proceso abierto: corte {abierto.fecha_corte:%d/%m/%Y}, plazo '
                                  f'{abierto.fecha_programada:%d/%m/%Y}, avisos enviados {abierto.avisos_enviados}')
            return
        estado, aviso = retencion.ciclo(hoy)
        textos = {
            'sin_datos': 'No hay datos de más de dos años.',
            'avisado': 'Aviso enviado a los Administradores.',
            'vencido': 'Plazo cumplido sin borrado: aviso diario enviado a los Administradores.',
            'esperando': 'Proceso abierto; hoy no corresponde avisar.',
        }
        detalle = f' (plazo: {aviso.fecha_programada:%d/%m/%Y})' if aviso else ''
        self.stdout.write(f'{timezone.localtime():%d/%m/%Y %H:%M} {textos[estado]}{detalle}')
