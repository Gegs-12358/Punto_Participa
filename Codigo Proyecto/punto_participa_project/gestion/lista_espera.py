"""
Lista de espera de los talleres llenos.

- El estudiante se anota desde la página del taller cuando no quedan cupos (RUT y Política de Privacidad).
- Cuando se libera un cupo por una cancelación, se avisa por correo a todos los de la lista con el enlace al
  taller. No se reserva el cupo: el primero que se inscribe lo obtiene (lo decide la transacción de la inscripción).
- Al inscribirse, el estudiante sale de la lista.
- Solo se aceptan anotaciones y se envían avisos mientras el taller esté activo y no haya empezado.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Inscripcion, ListaEspera


logger = logging.getLogger(__name__)


def acepta_anotaciones(actividad, ahora=None):
    ahora = ahora or timezone.now()
    return actividad.tipo == 'TALLER' and actividad.estado == 'ACTIVA' and ahora < actividad.fecha_inicio


def anotar(actividad, alumno):
    """Anota al alumno. Devuelve 'anotado', 'ya_estaba' o 'inscrito'."""
    if Inscripcion.objects.filter(actividad=actividad, alumno=alumno).exists():
        return 'inscrito'
    _, creado = ListaEspera.objects.get_or_create(actividad=actividad, alumno=alumno)
    return 'anotado' if creado else 'ya_estaba'


def quitar(actividad, alumno):
    ListaEspera.objects.filter(actividad=actividad, alumno=alumno).delete()


def avisar(actividad):
    """
    Avisa por correo a todos los de la lista que se liberó un cupo. Devuelve (enviados, fallidos).
    No hace nada si el taller ya no acepta inscripciones o si no quedan cupos libres.
    """
    actividad.refresh_from_db()
    if not acepta_anotaciones(actividad) or (actividad.cupos_disponibles or 0) <= 0:
        return 0, 0
    enlace = settings.SITE_URL.rstrip('/') + reverse('inscripcion_taller', args=[actividad.pk])
    inscritos = Inscripcion.objects.filter(actividad=actividad).values_list('alumno_id', flat=True)
    pendientes = (ListaEspera.objects.filter(actividad=actividad, alumno__activo=True)
                  .exclude(alumno_id__in=inscritos).exclude(alumno__correo='').select_related('alumno'))
    enviados = fallidos = 0
    for registro in pendientes:
        alumno = registro.alumno
        try:
            html = render_to_string('gestion/email_lista_espera.html',
                                    {'actividad': actividad, 'alumno': alumno, 'enlace': enlace})
            n = send_mail(subject=f'Se liberó un cupo: {actividad.titulo}',
                          message=(f'Hola {alumno.nombres}, se liberó un cupo en {actividad.titulo}. Los cupos se '
                                   f'asignan por orden de inscripción: si te interesa, inscríbete en {enlace}'),
                          from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[alumno.correo],
                          html_message=html, fail_silently=False)
            if n != 1:
                raise RuntimeError('Correo no aceptado.')
            registro.ultimo_aviso = timezone.now()
            registro.save(update_fields=['ultimo_aviso'])
            enviados += 1
        except Exception:
            logger.exception('No se pudo avisar a la lista de espera (registro %s)', registro.pk)
            fallidos += 1
    return enviados, fallidos
