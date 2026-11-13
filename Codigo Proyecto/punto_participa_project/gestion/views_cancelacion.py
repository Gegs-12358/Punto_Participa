"""
Cancelación de inscripciones (la lógica está en cancelaciones.py).

- cancelar_inscripcion: página pública del enlace personal. Pide confirmar antes de cancelar.
  Límite de 30 envíos por minuto por IP; no se indexa en buscadores.
- cancelar_inscripcion_gestor: botón en Participantes, para el Administrador y el creador.
Las dos dejan registro en la auditoría.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .cancelaciones import (NoSePuedeCancelar, alumno_puede_cancelar, cancelar,
                            limite_cancelacion)
from .decorators import role_required
from .models import Actividad, Inscripcion, InscripcionCancelada
from .permissions import puede_gestionar_actividad
from .views import registrar_log


def _estado_pagina(actividad, ahora):
    if actividad.estado == 'CANCELADA':
        return 'taller_cancelado'
    if actividad.estado != 'ACTIVA' or ahora >= actividad.fecha_inicio:
        return 'comenzo'
    if not alumno_puede_cancelar(actividad, ahora):
        return 'fuera_de_plazo'
    return 'abierta'


def _puede_volver(actividad):
    return actividad.estado == 'ACTIVA' and timezone.now() < actividad.fecha_fin


def _auditar(request, cancelacion, por_gestor):
    alumno = cancelacion.alumno
    nombre = f'{alumno.nombres} {alumno.apellidos}'
    quien = 'desde el sistema' if por_gestor else 'desde su enlace'
    registrar_log(request, 'Inscripciones', 'Cancelación de inscripción',
                  f'{nombre} - {cancelacion.actividad.titulo} (cancelada {quien}). Cupo liberado.',
                  'Alumno', alumno.id, nombre,
                  cambios_json={'actividad': cancelacion.actividad_id, 'por_gestor': por_gestor})


@ratelimit(key='ip', rate='30/m', method='POST', block=False)
def cancelar_inscripcion(request, token):
    inscripcion = (Inscripcion.objects.select_related('actividad', 'alumno')
                   .filter(token=token, actividad__tipo='TALLER').first())
    if inscripcion is None:
        anterior = (InscripcionCancelada.objects.select_related('actividad', 'alumno')
                    .filter(token=token).exclude(token='').first())
        if anterior is None:
            raise Http404('Enlace no válido.')
        return render(request, 'gestion/cancelacion_publica.html', {
            'actividad': anterior.actividad, 'alumno': anterior.alumno, 'estado_pagina': 'ya_cancelada',
            'cancelacion': anterior, 'puede_volver': _puede_volver(anterior.actividad)})

    actividad = inscripcion.actividad
    ahora = timezone.now()
    contexto = {'actividad': actividad, 'alumno': inscripcion.alumno, 'inscripcion': inscripcion,
                'estado_pagina': _estado_pagina(actividad, ahora), 'limite': limite_cancelacion(actividad)}

    if request.method == 'POST' and contexto['estado_pagina'] == 'abierta':
        if getattr(request, 'limited', False):
            contexto['error'] = 'Demasiados intentos seguidos. Espera un minuto y vuelve a intentarlo.'
            return render(request, 'gestion/cancelacion_publica.html', contexto, status=429)
        try:
            cancelacion = cancelar(inscripcion.pk, por=None, desde_enlace=True)
        except NoSePuedeCancelar as e:
            contexto['error'] = str(e)
        else:
            _auditar(request, cancelacion, por_gestor=False)
            contexto.update(estado_pagina='ya_cancelada', cancelacion=cancelacion,
                            puede_volver=_puede_volver(actividad),
                            exito='Tu inscripción quedó cancelada y el cupo quedó libre para otro estudiante.')
    return render(request, 'gestion/cancelacion_publica.html', contexto)


@login_required
@role_required('Administrador', 'Creador de Evento')
@require_POST
def cancelar_inscripcion_gestor(request, pk, inscripcion_id):
    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para gestionar esta actividad.')
        return redirect('lista_actividades')
    inscripcion = Inscripcion.objects.select_related('alumno').filter(pk=inscripcion_id, actividad=actividad).first()
    if inscripcion is None:
        messages.info(request, 'Esa inscripción ya estaba cancelada.')
        return redirect('participantes_actividad', pk=actividad.pk)
    nombre = f'{inscripcion.alumno.nombres} {inscripcion.alumno.apellidos}'
    try:
        cancelacion = cancelar(inscripcion.pk, por=request.user)
    except NoSePuedeCancelar as e:
        messages.error(request, f'No se canceló la inscripción de {nombre}: {e}')
    else:
        _auditar(request, cancelacion, por_gestor=True)
        messages.success(request, f'Inscripción de {nombre} cancelada. El cupo quedó disponible.')
    return redirect('participantes_actividad', pk=actividad.pk)
