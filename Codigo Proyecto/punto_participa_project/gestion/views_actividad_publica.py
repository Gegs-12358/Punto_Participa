"""
Página pública y de solo lectura de una actividad: /actividad/<n>/

Es el enlace que lleva el correo de invitación de las actividades masivas (que no tienen
inscripción). No pide ni muestra datos de ningún estudiante. Un taller se redirige a su
página de inscripción. Las actividades con invitación no tienen página pública (404).
"""
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Actividad


def actividad_publica(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    if actividad.tipo == 'INVITACION':
        # Es privada: cada invitado recibe su propio enlace
        raise Http404('Actividad con invitación.')
    if actividad.tipo == 'TALLER':
        return redirect('inscripcion_taller', actividad_id=actividad.pk)

    if actividad.estado == 'CANCELADA':
        estado = 'cancelada'
    elif actividad.estado == 'FINALIZADA' or actividad.fecha_fin <= timezone.now():
        estado = 'finalizada'
    else:
        estado = 'vigente'
    return render(request, 'gestion/actividad_publica.html',
                  {'actividad': actividad, 'estado': estado})
