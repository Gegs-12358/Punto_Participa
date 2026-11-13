"""
Cancelación de inscripciones a talleres.

- El alumno cancela con el enlace personal que le llega en el correo de confirmación
  (/inscripcion/cancelar/<token>/), hasta 24 horas antes del inicio (PLAZO_CANCELACION).
- El Administrador y el creador del taller pueden cancelar desde Participantes hasta que empiece.
- Al cancelar, la fila sale de Inscripcion y queda en InscripcionCancelada (historial), y el cupo
  vuelve a quedar disponible. No se cancela a quien ya tiene la asistencia registrada.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Actividad, Asistencia, Inscripcion, InscripcionCancelada


logger = logging.getLogger(__name__)

PLAZO_CANCELACION = timedelta(hours=24)


class NoSePuedeCancelar(Exception):
    """La inscripción no se puede cancelar; el mensaje explica por qué."""


def limite_cancelacion(actividad):
    """Hasta cuándo puede cancelar el alumno con su enlace."""
    return actividad.fecha_inicio - PLAZO_CANCELACION


def alumno_puede_cancelar(actividad, ahora=None):
    ahora = ahora or timezone.now()
    return actividad.estado == 'ACTIVA' and ahora < limite_cancelacion(actividad)


def gestor_puede_cancelar(actividad, ahora=None):
    ahora = ahora or timezone.now()
    return actividad.estado == 'ACTIVA' and ahora < actividad.fecha_inicio


def enlace_cancelacion(inscripcion):
    """Dirección completa del enlace personal para cancelar."""
    return settings.SITE_URL.rstrip('/') + reverse('cancelar_inscripcion', args=[inscripcion.token])


def ocultar_correo(correo):
    """juan.perez@duocuc.cl -> ju*****@duocuc.cl (para mostrarlo en la página pública).
    Siempre cinco asteriscos, para no revelar el largo del correo."""
    usuario, _, dominio = (correo or '').partition('@')
    if not dominio:
        return ''
    return usuario[:2] + '*****' + '@' + dominio


def cancelar(inscripcion_id, por=None, desde_enlace=False):
    """
    Cancela la inscripción: la pasa al historial y devuelve el cupo.
    por: usuario que cancela (None si es el alumno con su enlace).
    Devuelve la InscripcionCancelada. Lanza NoSePuedeCancelar si no corresponde.
    """
    ahora = timezone.now()
    with transaction.atomic():
        insc = (Inscripcion.objects.select_related('alumno')
                .filter(pk=inscripcion_id).first())
        if insc is None:
            raise NoSePuedeCancelar('Esta inscripción ya fue cancelada.')
        actividad = Actividad.objects.select_for_update().get(pk=insc.actividad_id)
        # Volver a leer con el bloqueo puesto: otro proceso pudo cancelarla recién
        insc = Inscripcion.objects.select_for_update().filter(pk=inscripcion_id).first()
        if insc is None:
            raise NoSePuedeCancelar('Esta inscripción ya fue cancelada.')

        permitido = alumno_puede_cancelar if desde_enlace else gestor_puede_cancelar
        if not permitido(actividad, ahora):
            if actividad.estado != 'ACTIVA':
                raise NoSePuedeCancelar('El taller no está activo.')
            if desde_enlace and ahora < actividad.fecha_inicio:
                raise NoSePuedeCancelar('Faltan menos de 24 horas para el taller: ya no se puede '
                                        'cancelar desde el enlace. Avisa al Punto Estudiantil.')
            raise NoSePuedeCancelar('El taller ya comenzó.')
        if Asistencia.objects.filter(actividad=actividad, alumno_id=insc.alumno_id).exists():
            raise NoSePuedeCancelar('El alumno ya tiene la asistencia registrada.')

        cancelacion = InscripcionCancelada.objects.create(
            actividad=actividad, alumno_id=insc.alumno_id, token=insc.token or '',
            fecha_inscripcion=insc.fecha_inscripcion, cancelada_por=por,
            carrera=insc.carrera, escuela=insc.escuela, jornada=insc.jornada,
        )
        insc.delete()
        if actividad.tipo == 'TALLER':
            disponibles = (actividad.cupos_disponibles or 0) + 1
            if actividad.cupos_totales is not None:
                disponibles = min(disponibles, actividad.cupos_totales)
            actividad.cupos_disponibles = disponibles
            actividad.save(update_fields=['cupos_disponibles'])
    return cancelacion


def enviar_confirmacion(inscripcion):
    """
    Correo de confirmación de la inscripción, con el enlace para cancelar.
    Devuelve True si se envió. Un fallo no deshace la inscripción.
    """
    alumno = inscripcion.alumno
    if not alumno.correo:
        return False
    actividad = inscripcion.actividad
    enlace = enlace_cancelacion(inscripcion)
    limite = limite_cancelacion(actividad)
    contexto = {'actividad': actividad, 'alumno': alumno, 'enlace': enlace, 'limite': limite,
                'puede_cancelar': timezone.now() < limite}
    try:
        html = render_to_string('gestion/email_confirmacion_inscripcion.html', contexto)
        texto = (f'Hola {alumno.nombres}, quedaste inscrito en {actividad.titulo}. '
                 + (f'Si no puedes asistir, cancela en {enlace} para liberar tu cupo.'
                    if contexto['puede_cancelar'] else ''))
        n = send_mail(subject=f'Inscripción confirmada: {actividad.titulo}', message=texto,
                      from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[alumno.correo],
                      html_message=html, fail_silently=False)
        return n == 1
    except Exception:
        logger.exception('No se pudo enviar la confirmación de inscripción (inscripción %s)', inscripcion.pk)
        return False
