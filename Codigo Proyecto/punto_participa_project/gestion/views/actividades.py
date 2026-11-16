"""
Actividades: listado, detalle con el recorrido de la participación, participantes, correos enviados,
crear, editar y eliminar.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ..decorators import role_required
from ..forms import ActividadForm
from ..models import Actividad, Asistencia, Inscripcion, NotificacionCorreo
from ..permissions import puede_gestionar_actividad, tiene_rol
from ..utils import fecha_o_none, limpiar_texto

from .comun import _error_json, _es_ajax, registrar_log
from .reportes import _lugares_para_filtro

logger = logging.getLogger(__name__)


@login_required
@role_required('Administrador', 'Creador de Evento')
def lista_actividades(request):
    tipo = request.GET.get('tipo', '')
    fecha = fecha_o_none(request.GET.get('fecha'))
    fecha_creacion = fecha_o_none(request.GET.get('fecha_creacion'))
    estado = request.GET.get('estado', '')
    lugar = request.GET.get('lugar', '')
    buscar = limpiar_texto(request.GET.get('q', ''))[:100]
    orden = request.GET.get('orden', '-fecha_inicio')

    validos = {
        'titulo', '-titulo', 'tipo', '-tipo', 'fecha_inicio', '-fecha_inicio',
        'fecha_creacion', '-fecha_creacion', 'estado', '-estado',
        'cupos_disponibles', '-cupos_disponibles',
        'total_inscritos', '-total_inscritos', 'total_asistentes', '-total_asistentes',
    }
    orden_seguro = orden if orden in validos else '-fecha_inicio'
    es_admin = tiene_rol(request.user, ['Administrador'])

    qs = Actividad.objects.annotate(
        total_inscritos=Count('inscripciones', distinct=True),
        total_asistentes=Count('asistencias', distinct=True),
        total_invitaciones_exito=Count(
            'notificaciones', filter=Q(notificaciones__estado_envio='EXITO'), distinct=True
        ),
        total_invitaciones_fallo=Count(
            'notificaciones', filter=Q(notificaciones__estado_envio='FALLO'), distinct=True
        ),
    ).order_by(orden_seguro)

    if tiene_rol(request.user, ['Creador de Evento']) and not es_admin:
        qs = qs.filter(creado_por=request.user)
    for campo, val in [('tipo', tipo), ('estado', estado), ('lugar', lugar)]:
        if val:
            qs = qs.filter(**{campo: val})
    if buscar:
        qs = qs.filter(Q(titulo__icontains=buscar) | Q(descripcion__icontains=buscar)
                       | Q(lugar__icontains=buscar))
    if fecha:
        qs = qs.filter(fecha_inicio__date=fecha)
    if fecha_creacion:
        qs = qs.filter(fecha_creacion__date=fecha_creacion)

    totales = {
        'actividades': qs.count(),
        'talleres': qs.filter(tipo='TALLER').count(),
        'masivas': qs.filter(tipo='MASIVA').count(),
        'inscritos': Inscripcion.objects.filter(actividad__in=qs).count(),
        'asistentes': Asistencia.objects.filter(actividad__in=qs).count(),
    }

    from ..utils import paginar
    return render(request, 'gestion/actividad_list.html', {
        'actividades': paginar(request, qs),
        'tipos': [('', 'Todos los tipos')] + list(Actividad.TIPO_CHOICES),
        'estados': [('', 'Todos los estados')] + list(Actividad.ESTADO_CHOICES),
        'lugares_opciones': _lugares_para_filtro(),
        'es_admin': es_admin, 'orden_actual': orden_seguro, 'totales': totales,
    })


@login_required
@role_required('Administrador', 'Creador de Evento')
def actividad_detalle(request, pk):
    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    total_inscritos = Inscripcion.objects.filter(actividad=actividad).count()
    confirmados = Inscripcion.objects.filter(actividad=actividad, estado='CONFIRMADA').count()
    total_asistentes = Asistencia.objects.filter(actividad=actividad).count()
    embudo = _embudo_actividad(actividad)

    return render(request, 'gestion/actividad_detalle.html', {
        'actividad': actividad,
        'total_inscritos': total_inscritos,
        'total_inscritos_confirmados': confirmados,
        'total_asistentes': total_asistentes,
        'tasa_asistencia': embudo['tasa'],
        'embudo': embudo,
        'total_notificaciones_exito': NotificacionCorreo.objects.filter(
            actividad=actividad, estado_envio='EXITO').count(),
        'total_notificaciones_fallo': NotificacionCorreo.objects.filter(
            actividad=actividad, estado_envio='FALLO').count(),
        'ultimas_asistencias': Asistencia.objects.filter(actividad=actividad)
            .select_related('alumno', 'registrado_por').order_by('-fecha_ingreso')[:10],
    })


def _pasos_embudo(pasos):
    """Barras proporcionales: cada valor como % del mayor."""
    mayor = max([v for _, v, _ in pasos] + [1])
    return [{'etiqueta': e, 'valor': v, 'clase': c, 'ancho': round(v / mayor * 100)} for e, v, c in pasos]


def _embudo_invitacion(actividad, max_lista=15):
    """
    Recorrido en una actividad con invitación: invitados -> confirmaron -> asistieron ->
    no asistieron, más los acompañantes (registrados y que entraron) y los agregados en la entrada.

    - no_asistieron: invitados que no dijeron que no y no entraron (solo cuando ya empezó).
    - tasa: invitados que entraron ÷ invitados que no dijeron que no.
    """
    ya_empezo = actividad.fecha_inicio <= timezone.now()
    invitados = actividad.invitados.all()
    c = invitados.aggregate(
        total=Count('id'),
        confirmados=Count('id', filter=Q(estado='CONFIRMADO')),
        rechazados=Count('id', filter=Q(estado='RECHAZADO')),
        entraron=Count('id', filter=Q(ingreso__isnull=False)),
        agregados=Count('id', filter=Q(agregado_en_entrada=True)),
    )
    acomp = actividad.acompanantes.aggregate(
        registrados=Count('id', filter=Q(agregado_en_entrada=False)),
        entraron=Count('id', filter=Q(ingreso__isnull=False)),
        agregados=Count('id', filter=Q(agregado_en_entrada=True)),
    )
    esperados = c['total'] - c['rechazados']
    datos = {
        'es_invitacion': True, 'es_taller': False, 'ya_empezo': ya_empezo,
        'invitados': c['total'], 'confirmados': c['confirmados'], 'rechazados': c['rechazados'],
        'asistieron': c['entraron'], 'agregados': c['agregados'] + acomp['agregados'],
        'acompanantes_registrados': acomp['registrados'], 'acompanantes_entraron': acomp['entraron'],
        'no_asistieron': None, 'faltantes': [], 'tasa': None, 'sin_invitacion': None,
    }
    if ya_empezo:
        faltan = invitados.exclude(estado='RECHAZADO').filter(ingreso__isnull=True)
        datos['no_asistieron'] = faltan.count()
        datos['faltantes'] = list(faltan.order_by('nombre')[:max_lista])
        datos['tasa'] = round(c['entraron'] / esperados * 100, 1) if esperados else None

    pasos = [('Invitados', c['total'], 'invitados'), ('Confirmaron', c['confirmados'], 'inscritos'),
             ('Asistieron', c['entraron'], 'asistieron')]
    if datos['no_asistieron'] is not None:
        pasos.append(('No asistieron', datos['no_asistieron'], 'no-asistieron'))
    pasos.append(('Acompañantes', acomp['entraron'], 'acompanantes'))
    datos['pasos'] = _pasos_embudo(pasos)
    return datos


def _embudo_actividad(actividad, max_lista=15):
    """
    Recorrido de la participación en una actividad (P1, reporte del taller):
    invitados -> inscritos -> asistieron -> no asistieron.

    - invitados: alumnos distintos a los que les llegó la invitación (envío con éxito).
    - inscritos: inscripciones confirmadas (solo talleres).
    - asistieron: talleres, inscritos que registraron asistencia; masivas, todos los asistentes.
    - no_asistieron: inscritos sin asistencia. Antes de que empiece la actividad es None
      (todavía no se sabe) y la tasa también.
    - sin_invitacion: inscritos (o asistentes, en masivas) que no tenían invitación.
    """
    if actividad.tipo == 'INVITACION':
        return _embudo_invitacion(actividad, max_lista)
    es_taller = actividad.tipo == 'TALLER'
    ya_empezo = actividad.fecha_inicio <= timezone.now()
    invitados_ids = set(NotificacionCorreo.objects.filter(
        actividad=actividad, estado_envio='EXITO', alumno__isnull=False).values_list('alumno_id', flat=True))
    asistentes_ids = set(Asistencia.objects.filter(actividad=actividad).values_list('alumno_id', flat=True))

    datos = {'es_taller': es_taller, 'ya_empezo': ya_empezo, 'invitados': len(invitados_ids),
             'inscritos': None, 'no_asistieron': None, 'faltantes': [], 'tasa': None}
    if es_taller:
        inscritos_ids = set(Inscripcion.objects.filter(
            actividad=actividad, estado='CONFIRMADA').values_list('alumno_id', flat=True))
        asistieron = len(inscritos_ids & asistentes_ids)
        datos.update(inscritos=len(inscritos_ids), asistieron=asistieron,
                     sin_invitacion=len(inscritos_ids - invitados_ids) if invitados_ids else None)
        if ya_empezo:
            faltan = Inscripcion.objects.filter(
                actividad=actividad, estado='CONFIRMADA').exclude(alumno_id__in=asistentes_ids)
            datos['no_asistieron'] = len(inscritos_ids) - asistieron
            datos['faltantes'] = list(faltan.select_related('alumno')
                                      .order_by('alumno__apellidos', 'alumno__nombres')[:max_lista])
            datos['tasa'] = round(asistieron / len(inscritos_ids) * 100, 1) if inscritos_ids else None
    else:
        datos.update(asistieron=len(asistentes_ids),
                     sin_invitacion=len(asistentes_ids - invitados_ids) if invitados_ids else None)
        if ya_empezo and actividad.cupos_totales:
            datos['tasa'] = round(len(asistentes_ids) / actividad.cupos_totales * 100, 1)

    # Barras: cada valor como % del mayor, para dibujarlas proporcionales
    pasos = [('Invitados', datos['invitados'], 'invitados')]
    if es_taller:
        pasos.append(('Inscritos', datos['inscritos'], 'inscritos'))
    pasos.append(('Asistieron', datos['asistieron'], 'asistieron'))
    if datos['no_asistieron'] is not None:
        pasos.append(('No asistieron', datos['no_asistieron'], 'no-asistieron'))
    datos['pasos'] = _pasos_embudo(pasos)
    return datos


@login_required
@role_required('Administrador', 'Creador de Evento')
def notificaciones_actividad(request, pk):
    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    filtro = request.GET.get('estado', '')
    notif = NotificacionCorreo.objects.filter(actividad=actividad) \
                                     .select_related('alumno', 'invitado').order_by('-fecha_envio')
    if filtro in ['EXITO', 'FALLO']:
        notif = notif.filter(estado_envio=filtro)

    from ..utils import paginar
    return render(request, 'gestion/actividad_notificaciones.html', {
        'actividad': actividad, 'notificaciones': paginar(request, notif),
        'total_exito': NotificacionCorreo.objects.filter(actividad=actividad, estado_envio='EXITO').count(),
        'total_fallo': NotificacionCorreo.objects.filter(actividad=actividad, estado_envio='FALLO').count(),
        'filtro_estado': filtro,
    })


@login_required
@role_required('Administrador', 'Creador de Evento')
def participantes_actividad(request, pk):
    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    filtro = request.GET.get('estado', '')
    insc = Inscripcion.objects.filter(actividad=actividad).select_related('alumno') \
                             .order_by('alumno__apellidos', 'alumno__nombres')
    if filtro in ['CONFIRMADA', 'CANCELADA', 'LISTA_ESPERA']:
        insc = insc.filter(estado=filtro)

    asis = Asistencia.objects.filter(actividad=actividad) \
                             .select_related('alumno', 'registrado_por') \
                             .order_by('alumno__apellidos', 'alumno__nombres')

    from ..utils import paginar
    return render(request, 'gestion/actividad_participantes.html', {
        'actividad': actividad,
        'inscripciones': paginar(request, insc, param='page_insc'),
        'asistencias': paginar(request, asis, param='page_asis'),
        'filtro_estado': filtro,
        'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
        'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
        'lista_espera': actividad.lista_espera.select_related('alumno')[:200],
        'total_lista_espera': actividad.lista_espera.count(),
        'cancelaciones': actividad.cancelaciones.select_related('alumno', 'cancelada_por')[:100],
        'total_cancelaciones': actividad.cancelaciones.count(),
        'puede_cancelar': actividad.tipo == 'TALLER' and actividad.estado == 'ACTIVA'
                          and timezone.now() < actividad.fecha_inicio,
    })


def _procesar_form_actividad(request, form, es_nueva):
    """Guarda el form de actividad validando fechas y cupos."""
    if not form.is_valid():
        if _es_ajax(request):
            titulo = 'Crear Actividad' if es_nueva else 'Editar Actividad'
            html = render_to_string('gestion/actividad_form_partial.html',
                                    {'form': form, 'titulo': titulo}, request=request)
            return None, JsonResponse({'success': False, 'html': html})
        return None, None

    actividad = form.save(commit=False)
    if actividad.fecha_fin <= actividad.fecha_inicio:
        form.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la fecha de inicio.')
        if _es_ajax(request):
            titulo = 'Crear Actividad' if es_nueva else 'Editar Actividad'
            html = render_to_string('gestion/actividad_form_partial.html',
                                    {'form': form, 'titulo': titulo}, request=request)
            return None, JsonResponse({'success': False, 'html': html})
        return None, None

    if es_nueva:
        actividad.creado_por = request.user

    # Delegado al modelo (si implementás Actividad.recalcular_cupos)
    if hasattr(actividad, 'recalcular_cupos'):
        if es_nueva:
            actividad.recalcular_cupos(inscritos_override=0)
        else:
            actividad.recalcular_cupos()
    else:
        # Fallback: comportamiento original
        if actividad.tipo == 'TALLER':
            if es_nueva:
                actividad.cupos_disponibles = actividad.cupos_totales
            else:
                inscritos = Inscripcion.objects.filter(actividad=actividad).count()
                actividad.cupos_disponibles = max(0, actividad.cupos_totales - inscritos)
        else:
            actividad.cupos_totales = None
            actividad.cupos_disponibles = None

    actividad.save()
    form.save_m2m()
    form.guardar_sesiones(actividad)
    if actividad.tipo == 'INVITACION' and getattr(form, 'filas_invitados', None):
        from .invitaciones import cargar_lista
        cargar_lista(request, actividad, form.filas_invitados)
    return actividad, None


@login_required
@role_required('Administrador', 'Creador de Evento')
def crear_actividad(request):
    if request.method == 'POST':
        request.POST = request.POST.copy()
        for f in ('fecha_inicio', 'fecha_fin'):
            if f in request.POST and 'T' in request.POST[f]:
                request.POST[f] = request.POST[f].replace('T', ' ')

        form = ActividadForm(request.POST, request.FILES)
        actividad, error = _procesar_form_actividad(request, form, es_nueva=True)

        if error:
            return error
        if actividad:
            registrar_log(request, 'Actividades', 'Crear Actividad',
                          f'Actividad "{actividad.titulo}" (ID: {actividad.id}) creada',
                          'Actividad', actividad.id, actividad.titulo)
            if actividad.tipo == 'INVITACION':
                # Sigue en la lista de invitados (resultado de la carga), no en el envío por carrera
                url = reverse('invitados_actividad', args=[actividad.pk])
                if _es_ajax(request):
                    return JsonResponse({'success': True, 'id': actividad.id, 'tipo': actividad.tipo,
                                         'es_nueva': True, 'redirect_url': url})
                return redirect(url)
            if _es_ajax(request):
                return JsonResponse({'success': True, 'id': actividad.id,
                                     'tipo': actividad.tipo, 'es_nueva': True})
            messages.success(request, 'Actividad creada exitosamente.')
            return redirect('lista_actividades')

        if _es_ajax(request) and form.errors:
            return JsonResponse({'success': False, 'errors': form.errors.as_json()})
    else:
        form = ActividadForm()

    titulo = 'Crear Actividad'
    if request.GET.get('partial'):
        return render(request, 'gestion/actividad_form_partial.html', {'form': form, 'titulo': titulo})
    return render(request, 'gestion/actividad_form.html', {'form': form, 'titulo': titulo})


@login_required
def editar_actividad(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para editar actividades.')
        return redirect('dashboard')

    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        if _es_ajax(request):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        messages.error(request, 'No tienes permisos para editar esta actividad.')
        return redirect('lista_actividades')

    tiene_insc = Inscripcion.objects.filter(actividad=actividad).exists()
    tiene_asis = Asistencia.objects.filter(actividad=actividad).exists()
    tiene_datos = tiene_insc or tiene_asis
    forzar = (request.POST.get('forzar_edicion') == 'true' or
              request.GET.get('forzar_edicion') == 'true')

    if tiene_datos and not forzar and _es_ajax(request) and not request.POST:
        partes = []
        if tiene_insc:
            n = Inscripcion.objects.filter(actividad=actividad).count()
            partes.append(f'{n} inscrito{"s" if n != 1 else ""}')
        if tiene_asis:
            n = Asistencia.objects.filter(actividad=actividad).count()
            partes.append(f'{n} asistente{"s" if n != 1 else ""}')
        return JsonResponse({
            'success': True, 'requiere_confirmacion': True,
            'mensaje': (f'Esta actividad ya tiene {" y ".join(partes)} registrado'
                        f'{"s" if len(partes) > 1 else ""}. '
                        'Si la editas, podrías crear inconsistencias en los datos históricos. '
                        '¿Estás seguro de que quieres editarla de todos modos?'),
            'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
            'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
        })

    if request.method == 'POST':
        form = ActividadForm(request.POST, request.FILES, instance=actividad)
        actividad, error = _procesar_form_actividad(request, form, es_nueva=False)

        if error:
            return error
        if actividad:
            detalle = f'Actividad "{actividad.titulo}" (ID: {actividad.id}) editada'
            if forzar and tiene_datos:
                detalle += ' FORZADAMENTE a pesar de tener datos asociados.'
            registrar_log(request, 'Actividades', 'Edición de actividad', detalle,
                          'Actividad', actividad.id, actividad.titulo)
            if actividad.tipo == 'INVITACION':
                url = reverse('invitados_actividad', args=[actividad.pk])
                if _es_ajax(request):
                    return JsonResponse({'success': True, 'id': actividad.id, 'tipo': actividad.tipo,
                                         'es_nueva': False, 'redirect_url': url})
                return redirect(url)
            if _es_ajax(request):
                return JsonResponse({'success': True, 'id': actividad.id,
                                     'tipo': actividad.tipo, 'es_nueva': False})
            messages.success(request, 'Actividad actualizada exitosamente.')
            return redirect('lista_actividades')
    else:
        form = ActividadForm(instance=actividad)

    titulo = 'Editar Actividad'
    if request.GET.get('partial'):
        return render(request, 'gestion/actividad_form_partial.html', {'form': form, 'titulo': titulo})
    return render(request, 'gestion/actividad_form.html', {'form': form, 'titulo': titulo})


@login_required
def eliminar_ajax(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return _error_json('No autorizado', 403)
    if request.method != 'POST':
        return _error_json('Método no permitido', 405)

    try:
        actividad = get_object_or_404(Actividad, pk=pk)
        if not puede_gestionar_actividad(request.user, actividad):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        if Inscripcion.objects.filter(actividad=actividad).exists() or \
           Asistencia.objects.filter(actividad=actividad).exists():
            return _error_json('No puedes eliminar esta actividad porque tiene registros asociados.')

        nombre, id_act = actividad.titulo, actividad.id
        actividad.delete()
        registrar_log(request, 'Actividades', 'Eliminación rápida de actividad',
                      f'Actividad "{nombre}" eliminada por cancelación de creación.',
                      'Actividad', id_act, nombre)
        return JsonResponse({'success': True})
    except Http404:
        return _error_json('La actividad ya no existe. Recarga la página.', 404)
    except Exception:
        logger.exception('Error en eliminar_ajax')
        return _error_json('Ocurrió un error inesperado.', 500)
