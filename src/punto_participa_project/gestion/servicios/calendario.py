"""
Agregar una actividad al calendario del alumno, desde los correos.

- enlace_google(actividad, sesion): abre Google Calendar con el evento listo para guardar (una sesión).
- ics(actividad): archivo .ics con todas las sesiones, que abren Outlook, el calendario de Apple y el de Android.
  Lo entrega la página pública /actividad/<id>/calendario.ics.
"""
from datetime import timezone as zona
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

SEDE = 'Duoc UC Sede Alameda'


def _utc(momento):
    return timezone.localtime(momento, zona.utc).strftime('%Y%m%dT%H%M%SZ')


def _lugar(actividad):
    return f'{actividad.lugar_completo}, {SEDE}'


def enlace_publico(actividad):
    nombre = 'inscripcion_taller' if actividad.tipo == 'TALLER' else 'actividad_publica'
    return settings.SITE_URL.rstrip('/') + reverse(nombre, args=[actividad.pk])


def _titulo(actividad, sesion, total):
    return f'{actividad.titulo} (sesión {sesion.numero} de {total})' if total > 1 else actividad.titulo


def enlace_google(actividad, sesion):
    total = len(actividad.lista_sesiones())
    datos = {
        'action': 'TEMPLATE',
        'text': _titulo(actividad, sesion, total),
        'dates': f'{_utc(sesion.fecha_inicio)}/{_utc(sesion.fecha_fin)}',
        'location': _lugar(actividad),
        'details': f'Punto Estudiantil, {SEDE}.\n{enlace_publico(actividad)}',
    }
    return 'https://calendar.google.com/calendar/render?' + urlencode(datos)


def _texto(valor):
    """Escapa un valor para el formato iCalendar (RFC 5545)."""
    return (str(valor).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _plegar(linea):
    """Las líneas de un .ics no deben pasar de 75 bytes: las largas siguen en la siguiente con un espacio."""
    partes, actual = [], ''
    for caracter in linea:
        if len((actual + caracter).encode('utf-8')) > 74:
            partes.append(actual)
            actual = ' '
        actual += caracter
    partes.append(actual)
    return '\r\n'.join(partes)


def ics(actividad):
    sesiones = actividad.lista_sesiones()
    ahora = _utc(timezone.now())
    host = settings.SITE_URL.split('//')[-1].split('/')[0].split(':')[0] or 'puntoparticipa'
    lineas = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Punto Participa//Duoc UC//ES',
              'CALSCALE:GREGORIAN', 'METHOD:PUBLISH']
    for sesion in sesiones:
        lineas += [
            'BEGIN:VEVENT',
            f'UID:actividad-{actividad.pk}-sesion-{sesion.numero}@{host}',
            f'DTSTAMP:{ahora}',
            f'DTSTART:{_utc(sesion.fecha_inicio)}',
            f'DTEND:{_utc(sesion.fecha_fin)}',
            f'SUMMARY:{_texto(_titulo(actividad, sesion, len(sesiones)))}',
            f'LOCATION:{_texto(_lugar(actividad))}',
            f'DESCRIPTION:{_texto(f"Punto Estudiantil, {SEDE}. " + enlace_publico(actividad))}',
            f'URL:{enlace_publico(actividad)}',
            'END:VEVENT',
        ]
    lineas.append('END:VCALENDAR')
    return '\r\n'.join(_plegar(linea) for linea in lineas) + '\r\n'
