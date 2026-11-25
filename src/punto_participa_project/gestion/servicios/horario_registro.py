"""
Horario en que el escáner acepta registros de asistencia.

Cada sesión se puede registrar desde MARGEN antes de que empiece hasta MARGEN después de que termine (los que llegan
temprano y los que quedan en la fila). Fuera de ese rango solo corrigen el Administrador o el creador de la
actividad, y cada registro queda en la auditoría como corrección.

La lista para elegir actividad en el escáner muestra las que tienen el registro abierto y las que lo abren en las
próximas PROXIMAS (para preparar el turno). A quien puede corregir se le muestran además las demás actividades
activas que gestiona, aparte, como "Fuera de horario".
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ..permissions import puede_gestionar_actividad

PROXIMAS = timedelta(hours=24)


def margen():
    return timedelta(minutes=getattr(settings, 'REGISTRO_MARGEN_MINUTOS', 60))


def desde(sesion):
    return sesion.fecha_inicio - margen()


def hasta(sesion):
    return sesion.fecha_fin + margen()


def abierta(sesion, ahora=None):
    ahora = ahora or timezone.now()
    return desde(sesion) <= ahora <= hasta(sesion)


def actividad_abierta(actividad, ahora=None):
    """True si alguna sesión de la actividad tiene el registro abierto ahora."""
    ahora = ahora or timezone.now()
    return any(abierta(s, ahora) for s in actividad.lista_sesiones())


def proxima_apertura(actividad, ahora=None):
    """Cuándo abre el registro de la próxima sesión que aún no lo abre (o None)."""
    ahora = ahora or timezone.now()
    futuras = [desde(s) for s in actividad.lista_sesiones() if desde(s) > ahora]
    return min(futuras) if futuras else None


def puede_corregir(user, actividad):
    """Administrador, o el creador de la actividad: pueden registrar fuera de horario."""
    return puede_gestionar_actividad(user, actividad)


def mensaje_cerrado(sesion, ahora=None):
    ahora = ahora or timezone.now()
    d, h = timezone.localtime(desde(sesion)), timezone.localtime(hasta(sesion))
    if ahora < desde(sesion):
        return (f'El registro todavía no abre: empieza el {d:%d/%m} a las {d:%H:%M} '
                f'(una hora antes de la actividad).')
    return (f'El registro de esta actividad ya cerró: era hasta el {h:%d/%m} a las {h:%H:%M} '
            f'(una hora después de terminar). Solo el Administrador o quien creó la actividad pueden corregirlo.')


def estado(user, actividad, sesion, ahora=None):
    """Lo que el escáner muestra del horario de la sesión elegida."""
    ahora = ahora or timezone.now()
    esta_abierta = abierta(sesion, ahora)
    return {
        'abierto': esta_abierta,
        'desde': timezone.localtime(desde(sesion)),
        'hasta': timezone.localtime(hasta(sesion)),
        'antes': ahora < desde(sesion),
        'corrige': not esta_abierta and puede_corregir(user, actividad),
    }
