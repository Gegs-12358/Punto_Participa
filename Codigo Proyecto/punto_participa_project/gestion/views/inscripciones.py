"""
Inscripción a talleres y todo lo que la rodea:
  - Página pública de inscripción (con límite de intentos fallidos) y lista de espera cuando no hay cupos.
  - Cancelación: desde el enlace personal del alumno y desde Participantes (Administrador y creador).
    Al cancelar se avisa a la lista de espera. La lógica está en cancelaciones.py y lista_espera.py.
  - Página pública de las actividades masivas y Política de Privacidad.
"""
import logging

from django_ratelimit.decorators import ratelimit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache as cache_django
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..servicios.cancelaciones import alumno_puede_cancelar, cancelar, limite_cancelacion, NoSePuedeCancelar
from ..decorators import role_required
from ..servicios.lista_espera import avisar as avisar_lista_espera
from ..models import Actividad, consentimiento, Inscripcion, InscripcionCancelada, VERSION_POLITICA
from ..permissions import puede_gestionar_actividad
from ..utils import buscar_alumno_por_documento, limpiar_documento

from .comun import registrar_log

logger = logging.getLogger(__name__)


LIMITE_FALLOS_INSCRIPCION = 15


VENTANA_FALLOS_INSCRIPCION = 15 * 60  # segundos


def _clave_fallos_inscripcion(request):
    return 'insc_fallos:' + (request.META.get('REMOTE_ADDR') or 'desconocida')


def _inscripcion_bloqueada(request):
    """True si esta IP acumuló demasiados documentos inexistentes."""
    return cache_django.get(_clave_fallos_inscripcion(request), 0) >= LIMITE_FALLOS_INSCRIPCION


def _registrar_fallo_inscripcion(request):
    clave = _clave_fallos_inscripcion(request)
    if cache_django.add(clave, 1, VENTANA_FALLOS_INSCRIPCION):
        return
    try:
        cache_django.incr(clave)
    except ValueError:  # la clave venció justo ahora
        cache_django.set(clave, 1, VENTANA_FALLOS_INSCRIPCION)


def _render_inscripcion(request, actividad, estado='con_cupos', error=None, exito=None):
    from ..servicios.lista_espera import acepta_anotaciones
    ctx = {'actividad': actividad, 'estado': estado,
           'acepta_espera': estado == 'sin_cupos' and acepta_anotaciones(actividad)}
    if error:
        ctx['error'] = error
    if exito:
        ctx['exito'] = exito
    return render(request, 'gestion/inscripcion_publica.html', ctx)


def _estado_cerrado(actividad):
    """Estado de la página cuando el taller ya no recibe inscripciones."""
    return 'cancelado' if actividad.estado == 'CANCELADA' else 'finalizado'


def inscripcion_taller(request, actividad_id):
    """
    Vista pública de inscripción a talleres.
    Ahora usa buscar_alumno_por_documento() para aceptar
    RUT con/sin guion, con/sin puntos, pasaportes, etc.
    """
    actividad = get_object_or_404(Actividad, pk=actividad_id)
    if actividad.tipo == 'MASIVA':
        # Una masiva no tiene inscripción: se muestra su página pública
        return redirect('actividad_publica', actividad_id=actividad.pk)
    if actividad.tipo != 'TALLER':
        raise Http404('Actividad sin inscripción pública.')
    ahora = timezone.now()

    if actividad.estado != 'ACTIVA' or actividad.cierre_inscripcion <= ahora:
        return _render_inscripcion(request, actividad, _estado_cerrado(actividad))
    if (actividad.cupos_disponibles or 0) <= 0:
        if request.method == 'POST' and request.POST.get('accion') == 'lista_espera':
            return _anotar_lista_espera(request, actividad)
        return _render_inscripcion(request, actividad, 'sin_cupos')
    if request.method != 'POST':
        return _render_inscripcion(request, actividad, 'con_cupos')

    if not request.POST.get('acepta_politica'):
        return _render_inscripcion(
            request, actividad, 'con_cupos',
            'Debes aceptar la Política de Privacidad para inscribirte.'
        )

    if _inscripcion_bloqueada(request):
        return _render_inscripcion(
            request, actividad, 'con_cupos',
            'Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.'
        )

    rut_original = limpiar_documento(request.POST.get('rut'), 40)
    if not rut_original:
        return _render_inscripcion(request, actividad, 'con_cupos', 'Debes ingresar tu RUT.')

    # Búsqueda inteligente: acepta múltiples formatos
    alumno = buscar_alumno_por_documento(rut_original)
    if not alumno:
        _registrar_fallo_inscripcion(request)
        return _render_inscripcion(
            request, actividad, 'con_cupos',
            'No estás registrado en el sistema. Verifica tu RUT o contacta a Punto Estudiantil.'
        )

    try:
        with transaction.atomic():
            act_lock = Actividad.objects.select_for_update().get(pk=actividad_id)

            if act_lock.tipo != 'TALLER':
                return _render_inscripcion(request, act_lock, 'finalizado',
                                           'Esta actividad no corresponde a un taller.')
            if act_lock.estado != 'ACTIVA' or act_lock.cierre_inscripcion <= timezone.now():
                return _render_inscripcion(request, act_lock, _estado_cerrado(act_lock))
            if Inscripcion.objects.filter(actividad=act_lock, alumno=alumno).exists():
                return _render_inscripcion(request, act_lock, 'con_cupos',
                                           'Ya estás inscrito en este taller.')

            cupos = act_lock.cupos_disponibles or 0
            if cupos <= 0:
                return _render_inscripcion(request, act_lock, 'sin_cupos')

            act_lock.cupos_disponibles = cupos - 1
            act_lock.save(update_fields=['cupos_disponibles'])

            inscripcion = Inscripcion.objects.create(actividad=act_lock, alumno=alumno, estado='CONFIRMADA',
                                                     **consentimiento())
            cupos_restantes = act_lock.cupos_disponibles
            from ..servicios.lista_espera import quitar as quitar_de_lista_espera
            quitar_de_lista_espera(act_lock, alumno)
    except IntegrityError:
        return _render_inscripcion(request, actividad, 'con_cupos', 'Ya estás inscrito en este taller.')
    try:
        registrar_log(request, 'Inscripciones', 'Inscripción a taller',
                      f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo} - Política de Privacidad '
                      f'{VERSION_POLITICA} aceptada',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
    except Exception:
        logger.exception(
            'No se pudo registrar la auditoría de la inscripción (alumno %s, actividad %s)',
            alumno.id, actividad_id,
        )

    actividad.cupos_disponibles = cupos_restantes
    from ..servicios.cancelaciones import enviar_confirmacion, ocultar_correo
    if enviar_confirmacion(inscripcion):
        aviso = (f' Te enviamos la confirmación a {ocultar_correo(alumno.correo)}, '
                 'con el enlace para cancelar si no puedes asistir.')
    else:
        aviso = ' No pudimos enviarte el correo de confirmación; tu inscripción igual quedó registrada.'
    return _render_inscripcion(request, actividad, 'con_cupos', exito=
                               f'Cupos disponibles: {cupos_restantes}.{aviso}')


def _anotar_lista_espera(request, actividad):
    """Anota al estudiante en la lista de espera de un taller sin cupos."""
    from ..servicios.cancelaciones import ocultar_correo
    from ..servicios.lista_espera import acepta_anotaciones, anotar

    def error(texto):
        return _render_inscripcion(request, actividad, 'sin_cupos', texto)

    if not acepta_anotaciones(actividad):
        return error('El taller ya comenzó: no se reciben anotaciones en la lista de espera.')
    if not request.POST.get('acepta_politica'):
        return error('Debes aceptar la Política de Privacidad para anotarte en la lista de espera.')
    if _inscripcion_bloqueada(request):
        return error('Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.')
    documento = limpiar_documento(request.POST.get('rut'), 40)
    if not documento:
        return error('Debes ingresar tu RUT.')
    alumno = buscar_alumno_por_documento(documento)
    if not alumno:
        _registrar_fallo_inscripcion(request)
        return error('No estás registrado en el sistema. Verifica tu RUT o contacta a Punto Estudiantil.')
    resultado = anotar(actividad, alumno, consentimiento())
    if resultado == 'inscrito':
        return error('Ya estás inscrito en este taller.')
    correo = ocultar_correo(alumno.correo)
    destino = f' a {correo}' if correo else ''
    if resultado == 'ya_estaba':
        return _render_inscripcion(request, actividad, 'sin_cupos', exito=
                                   f'Ya estabas en la lista de espera (todavía no estás inscrito). Te avisaremos{destino} '
                                   'si se libera un cupo.')
    registrar_log(request, 'Inscripciones', 'Anotación en lista de espera',
                  f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo} - Política de Privacidad '
                  f'{VERSION_POLITICA} aceptada',
                  'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
    return _render_inscripcion(request, actividad, 'sin_cupos', exito=
                               f'Quedaste en la lista de espera (todavía no estás inscrito). Si se libera un cupo te '
                               f'avisaremos{destino}, y el cupo será para el primero que se inscriba.')


def _estado_pagina(actividad, ahora):
    if actividad.estado == 'CANCELADA':
        return 'taller_cancelado'
    if actividad.estado != 'ACTIVA' or ahora >= actividad.fecha_inicio:
        return 'comenzo'
    if not alumno_puede_cancelar(actividad, ahora):
        return 'fuera_de_plazo'
    return 'abierta'


def _puede_volver(actividad):
    return actividad.estado == 'ACTIVA' and timezone.now() < actividad.cierre_inscripcion


def _auditar(request, cancelacion, por_gestor):
    alumno = cancelacion.alumno
    nombre = f'{alumno.nombres} {alumno.apellidos}'
    quien = 'desde el sistema' if por_gestor else 'desde su enlace'
    registrar_log(request, 'Inscripciones', 'Cancelación de inscripción',
                  f'{nombre} - {cancelacion.actividad.titulo} (cancelada {quien}). Cupo liberado.',
                  'Alumno', alumno.id, nombre,
                  cambios_json={'actividad': cancelacion.actividad_id, 'por_gestor': por_gestor})


def _avisar_lista(request, actividad):
    """Avisa a la lista de espera que se liberó un cupo y lo deja en la auditoría. Devuelve los avisos enviados."""
    enviados, fallidos = avisar_lista_espera(actividad)
    if enviados or fallidos:
        registrar_log(request, 'Inscripciones', 'Aviso a lista de espera',
                      f'"{actividad.titulo}": se liberó un cupo. {enviados} aviso{"s" if enviados != 1 else ""} '
                      f'enviado{"s" if enviados != 1 else ""}' + (f', {fallidos} con error' if fallidos else '') + '.',
                      'Actividad', actividad.id, actividad.titulo,
                      cambios_json={'enviados': enviados, 'fallidos': fallidos})
    return enviados


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
            _avisar_lista(request, actividad)
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
        avisados = _avisar_lista(request, actividad)
        texto = f'Inscripción de {nombre} cancelada. El cupo quedó disponible.'
        if avisados:
            texto += (f' Se avisó por correo a {avisados} persona{"s" if avisados != 1 else ""} '
                      f'de la lista de espera.')
        messages.success(request, texto)
    return redirect('participantes_actividad', pk=actividad.pk)


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


def politica_privacidad(request):
    """Página pública con la Política de Privacidad."""
    return render(request, 'gestion/politica_privacidad.html', {'version_politica': VERSION_POLITICA})
