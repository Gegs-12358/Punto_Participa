"""
Reportes: pantalla con gráficos y tablas. Aquí están también los filtros que comparten el Inicio y
las exportaciones (la "foto" académica de inscripciones y asistencias).
"""
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from ..decorators import role_required
from ..models import Acompanante, Actividad, Asistencia, Carrera, Inscripcion, Invitado, Jornada, Lugar
from ..permissions import tiene_rol
from ..utils import fecha_o_none, id_o_none

from .comun import _colores_por_carrera, _get_carreras_cache, color_para_escuela, colores_escuelas


def _q_foto(carrera=None, jornada=None, escuela=None, prefijo=''):
    q = Q()
    if escuela and escuela.strip():
        q &= Q(**{f'{prefijo}escuela__iexact': escuela.strip()})
    if carrera and carrera.strip():
        q &= Q(**{f'{prefijo}carrera__iexact': carrera.strip()})
    if jornada and jornada.strip():
        q &= Q(**{f'{prefijo}jornada__iexact': jornada.strip()})
    return q


def _filtrar_por_foto(qs, carrera=None, jornada=None, escuela=None, prefijo=''):
    """
    Filtra inscripciones o asistencias por la carrera, jornada o escuela que el alumno
    tenía en ese momento (la "foto" académica), sin distinguir mayúsculas ni espacios.
    Con prefijo (p. ej. 'asistencias__') sirve para armar un Q sobre actividades.
    """
    return qs.filter(_q_foto(carrera, jornada, escuela, prefijo))


def _construir_desglose_tipo(act_qs, asis_qs, carrera=None, jornada=None, escuela=None):
    """Calcula masivas/talleres para dashboard y reportes."""
    ids_talleres = list(act_qs.filter(tipo='TALLER').values_list('id', flat=True))
    ids_masivas = list(act_qs.filter(tipo='MASIVA').values_list('id', flat=True))

    insc = Inscripcion.objects.filter(actividad_id__in=ids_talleres)
    insc = _filtrar_por_foto(insc, carrera, jornada, escuela)

    t_insc = insc.count()
    t_asis = asis_qs.filter(actividad_id__in=ids_talleres).count()
    # La tasa se calcula con los talleres que ya empezaron: en los que vienen nadie puede haber asistido aún,
    # y contarlos bajaba la tasa
    empezados = list(act_qs.filter(tipo='TALLER', fecha_inicio__lte=timezone.now())
                     .exclude(estado='CANCELADA').values_list('id', flat=True))
    e_insc = insc.filter(actividad_id__in=empezados).count()
    e_asis = asis_qs.filter(actividad_id__in=empezados).count()
    m_asis = asis_qs.filter(actividad_id__in=ids_masivas).count()
    cupos_m = act_qs.filter(tipo='MASIVA', cupos_totales__isnull=False).aggregate(
        t=Sum('cupos_totales')).get('t') or 0

    return {
        'masivas_count': len(ids_masivas),
        'masivas_asistentes': m_asis,
        'cupos_masivas': cupos_m,
        'tasa_masivas': round(m_asis / cupos_m * 100, 1) if cupos_m else None,
        'talleres_count': len(ids_talleres),
        'talleres_inscritos': t_insc,
        'talleres_asistentes': t_asis,
        'tasa_talleres': round(e_asis / e_insc * 100, 1) if e_insc else None,
    }


# Filtros de reportes/export unificados
def _lugares_para_filtro():
    """Todos los lugares del catálogo (también los bloqueados: hay actividades antiguas en ellos)."""
    return list(Lugar.objects.order_by('nombre').values_list('nombre', flat=True))


def _aplicar_filtros_reporte(request, act_qs=None, asis_qs=None):
    """
    Aplica los filtros comunes de reportes/export a actividades y asistencias.
    Devuelve (act_qs, asis_qs).
    """
    # IDs y fechas inválidos se ignoran (no provocan error 500)
    actividad_id = id_o_none(request.GET.get('actividad'))
    escuela = request.GET.get('escuela', '')          
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    lugar = request.GET.get('lugar', '')
    tipo = request.GET.get('tipo', '')
    fecha_inicio = fecha_o_none(request.GET.get('fecha_inicio'))
    fecha_fin = fecha_o_none(request.GET.get('fecha_fin'))

    if act_qs is None:
        act_qs = Actividad.objects.all().order_by('-fecha_inicio')

    if tiene_rol(request.user, ['Creador de Evento']) and not tiene_rol(request.user, ['Administrador']):
        act_qs = act_qs.filter(creado_por=request.user)
    if actividad_id:
        act_qs = act_qs.filter(pk=actividad_id)
    if escuela:
        act_qs = act_qs.filter(carreras__escuela=escuela).distinct()
    if lugar:
        act_qs = act_qs.filter(lugar=lugar)
    if tipo in dict(Actividad.TIPO_CHOICES):          # historia 005; valores desconocidos se ignoran
        act_qs = act_qs.filter(tipo=tipo)
    if fecha_inicio:
        act_qs = act_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        act_qs = act_qs.filter(fecha_fin__date__lte=fecha_fin)

    ids = list(act_qs.values_list('id', flat=True))

    if asis_qs is None:
        asis_qs = Asistencia.objects.filter(actividad_id__in=ids) \
                                    .select_related('alumno', 'registrado_por', 'actividad')
    else:
        asis_qs = asis_qs.filter(actividad_id__in=ids)

    # Escuela, carrera y jornada: las que el alumno tenía al asistir (foto académica)
    asis_qs = _filtrar_por_foto(asis_qs, carrera, jornada, escuela)

    return act_qs, asis_qs


@login_required
@role_required('Administrador', 'Creador de Evento')
def reportes(request):
    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    escuela = request.GET.get('escuela', '') 
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    actividad_id = request.GET.get('actividad', '')

    # Filtros unificados
    act_qs, asis_qs = _aplicar_filtros_reporte(request)

    ids_act = list(act_qs.values_list('id', flat=True))

    filtro_asis = _q_foto(carrera, jornada, escuela, prefijo='asistencias__')
    filtro_insc = _q_foto(carrera, jornada, escuela, prefijo='inscripciones__')

    act_qs = act_qs.select_related('creado_por').annotate(
        total_asistentes_calc=Count('asistencias', filter=filtro_asis or None, distinct=True),
        total_inscritos_calc=Count('inscripciones', filter=filtro_insc or None, distinct=True),
    ).prefetch_related('carreras', 'jornadas')

    total_inscritos = _filtrar_por_foto(
        Inscripcion.objects.filter(actividad_id__in=ids_act),
        carrera, jornada, escuela,
    ).count()
    total_asistentes = asis_qs.count()

    # Uso del cache helper
    carreras_cache = _get_carreras_cache()

    # ---- Dona de Carreras (general) ----
    por_carrera = list(
        asis_qs.values('carrera')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t', 'carrera')
    )
    labels_pastel = [i['carrera'] or 'Sin carrera' for i in por_carrera]
    data_pastel = [i['t'] for i in por_carrera]
    # Uso del helper
    data_colores_pastel = _colores_por_carrera(por_carrera, carreras_cache)
    escuelas_pastel = []
    for i in por_carrera:
        c = carreras_cache.get((i['carrera'] or '').lower())
        escuelas_pastel.append(c.escuela if c and c.escuela else 'Sin escuela')

    # ---- Barras de Jornada (general) ----
    por_jornada = (
        asis_qs.values('jornada')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t', 'jornada')
    )
    labels_jornada = [i['jornada'] or 'Sin jornada' for i in por_jornada]
    data_jornada = [i['t'] for i in por_jornada]

    # ---- Registros por actividad ----
    regs_por_act = defaultdict(list)
    for item in asis_qs.values('actividad_id', 'registrado_por__username') \
                       .annotate(t=Count('id')).order_by('-t'):
        regs_por_act[item['actividad_id']].append(
            f"{item['registrado_por__username'] or 'Anónimo'} ({item['t']})"
        )
    # Con invitación: inscritos = confirmaron; asistentes = invitados y acompañantes que entraron
    ids_invitacion = [a.id for a in act_qs if a.tipo == 'INVITACION']
    lista_inv = {}
    if ids_invitacion:
        for i in (Invitado.objects.filter(actividad_id__in=ids_invitacion).order_by().values('actividad_id')
                  .annotate(conf=Count('id', filter=Q(estado='CONFIRMADO')),
                            entraron=Count('id', filter=Q(ingreso__isnull=False)))):
            lista_inv[i['actividad_id']] = [i['conf'], i['entraron']]
        for i in (Acompanante.objects.filter(actividad_id__in=ids_invitacion, ingreso__isnull=False)
                  .order_by().values('actividad_id').annotate(t=Count('id'))):
            lista_inv.setdefault(i['actividad_id'], [0, 0])[1] += i['t']
    for a in act_qs:
        a.total_asistentes = a.total_asistentes_calc
        a.total_inscritos = a.total_inscritos_calc
        if a.tipo == 'INVITACION':
            a.total_inscritos, a.total_asistentes = lista_inv.get(a.id, [0, 0])
        a.creador = a.creado_por.username if a.creado_por else 'N/A'
        a.registrado_por_detalle = ", ".join(regs_por_act.get(a.id, [])) or "Sin registros"

    # ---- Detalle por escuela/carrera/jornada ----
        # ---- Detalle por escuela/carrera/jornada ----
    detalle_data = []
    det_escuelas, det_carreras = defaultdict(int), defaultdict(int)
    agrupado = defaultdict(lambda: defaultdict(lambda: {'t': 0, 'regs': defaultdict(int)}))

    escuela_de_carrera = {}
    for i in (asis_qs.order_by()
              .values('actividad_id', 'escuela', 'carrera', 'jornada', 'registrado_por__username')
              .annotate(t=Count('id'))):
        escuela_item = i['escuela'] or 'Sin asignar'
        clave = (escuela_item, i['carrera'], i['jornada'])
        escuela_de_carrera.setdefault(i['carrera'], i['escuela'])
        agrupado[i['actividad_id']][clave]['t'] += i['t']
        agrupado[i['actividad_id']][clave]['regs'][i['registrado_por__username'] or 'Anónimo'] += i['t']

    for a in act_qs:
        for (escuela_item, carrera_n, jornada_n), vals in agrupado.get(a.id, {}).items():
            detalle_data.append({
                'actividad': a.titulo, 'tipo': a.get_tipo_display(),
                'fecha': timezone.localtime(a.fecha_inicio).strftime("%d/%m/%Y"),
                'escuela': escuela_item, 'carrera': carrera_n, 'jornada': jornada_n,
                'asistentes': vals['t'],
                'registrado_por': ", ".join(f"{u} ({c})" for u, c in vals['regs'].items()),
            })
            det_escuelas[escuela_item] += vals['t']
            det_carreras[carrera_n] += vals['t']

    # ---- Detalle ordenado: escuelas de mayor a menor; carreras agrupadas por escuela (en el orden de las
    # escuelas) y dentro de cada escuela de mayor a menor ----
    mapa = colores_escuelas()
    det_escuelas = dict(sorted(det_escuelas.items(), key=lambda x: (-x[1], x[0])))
    orden_escuela = {e: k for k, e in enumerate(det_escuelas)}
    det_carreras = dict(sorted(
        det_carreras.items(),
        key=lambda x: (orden_escuela.get(escuela_de_carrera.get(x[0]) or 'Sin asignar', 99), -x[1], x[0] or '')))
    data_colores_barras_detalle = [color_para_escuela(e, mapa) for e in det_escuelas.keys()]
    data_colores_pastel_detalle = []
    escuelas_pastel_detalle = []
    for carrera_n in det_carreras.keys():
        data_colores_pastel_detalle.append(color_para_escuela(escuela_de_carrera.get(carrera_n), mapa))
        escuelas_pastel_detalle.append(escuela_de_carrera.get(carrera_n) or 'Sin escuela')

    actividades_opciones = (
        Actividad.objects.filter(creado_por=request.user) if (es_creador and not es_admin)
        else Actividad.objects.all()
    ).order_by('-fecha_inicio')

    # ---- Barras general: solo actividades con al menos 1 asistente ----
    acts_con_datos = [a for a in act_qs if a.total_asistentes_calc > 0]
    total_acts_con_datos = len(acts_con_datos)
    # El gráfico muestra las 10 con más asistentes; el resto está en la tabla
    top_acts = sorted(acts_con_datos, key=lambda a: (-a.total_asistentes_calc, a.titulo))[:10]
    labels_barras = [a.titulo for a in top_acts]
    data_barras = [a.total_asistentes_calc for a in top_acts]

    from ..utils import paginar
    context = {
        'actividades': paginar(request, act_qs, param='page_act'),
        'detalle_data': paginar(request, detalle_data, param='page_det'),
        'total_acts_con_datos': total_acts_con_datos,

        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
        'data_colores_pastel': data_colores_pastel,
        'labels_jornada': labels_jornada,
        'data_jornada': data_jornada,

        'labels_barras_detalle': list(det_escuelas.keys()),
        'data_barras_detalle': list(det_escuelas.values()),
        'labels_pastel_detalle': [c or 'Sin carrera' for c in det_carreras.keys()],
        'escuelas_pastel_detalle': escuelas_pastel_detalle,
        'escuelas_pastel': escuelas_pastel,
        'data_pastel_detalle': list(det_carreras.values()),
        'data_colores_barras_detalle': data_colores_barras_detalle,
        'data_colores_pastel_detalle': data_colores_pastel_detalle,
        'labels_jornada_detalle': labels_jornada,
        'data_jornada_detalle': data_jornada,

        'actividades_opciones': actividades_opciones,
        'escuelas_opciones': Carrera.objects.exclude(escuela__isnull=True)   # <-- nuevo
            .exclude(escuela='')
            .values_list('escuela', flat=True).distinct().order_by('escuela'),
        'escuela_seleccionada': escuela,                                     # <-- nuevo
        'carreras_opciones': Carrera.objects.all(),
        'jornadas_opciones': Jornada.objects.all(),
        'lugares_opciones': _lugares_para_filtro(),
        'tipos_opciones': Actividad.TIPO_CHOICES,
        # Para que el chip del filtro Actividad muestre el nombre y no el número
        'valores_chips': {'actividad': {str(a.id): a.titulo for a in actividades_opciones}},
        'actividad_seleccionada': actividad_id,
        'total_inscritos_filtrado': total_inscritos,
        'total_asistentes_filtrado': total_asistentes,
        **_construir_desglose_tipo(act_qs, asis_qs, carrera, jornada, escuela),
    }
    return render(request, 'gestion/reportes.html', context)
