"""
Inicio (dashboard): indicadores, gráficos y el botón de retención de datos.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import role_required
from ..models import (Actividad, Asistencia, AvisoRetencion, Carrera, Inscripcion, Jornada, LogAuditoria,
                      NotificacionCorreo)
from ..permissions import tiene_rol
from ..servicios.retencion import ejecutar, nombre_usuario, YaEjecutado

from .comun import _colores_por_carrera, _get_carreras_cache, color_para_escuela, colores_escuelas
from .reportes import _construir_desglose_tipo, _filtrar_por_foto


MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _construir_graficos_dashboard(asis_qs, act_qs, carreras_cache, ahora):
    """Construye labels/data/colores de los 5 gráficos del dashboard,
    excluyendo elementos sin datos."""

    # ---- Top 5: actividades con más asistentes ----
    top = (
        act_qs
        .annotate(t=Count('asistencias'))
        .filter(t__gt=0)
        .order_by('-t', 'titulo')[:5]
    )
    tipos = dict(Actividad.TIPO_CHOICES)
    labels_barras = [a.titulo for a in top]
    tipos_barras = [tipos.get(a.tipo, a.tipo) for a in top]
    data_barras = [a.t for a in top]

    # ---- Carreras con más asistentes (color = escuela de la carrera) ----
    por_carrera = list(
        asis_qs
        .values('carrera')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t', 'carrera')[:6]
    )
    labels_pastel = [i['carrera'] or 'Sin carrera' for i in por_carrera]
    data_pastel = [i['t'] for i in por_carrera]
    data_colores_pastel = _colores_por_carrera(por_carrera, carreras_cache)
    escuelas_pastel = []
    for i in por_carrera:
        c = carreras_cache.get((i['carrera'] or '').lower())
        escuelas_pastel.append(c.escuela if c and c.escuela else 'Sin escuela')
    total_carreras = asis_qs.count()

    # ---- Actividades por mes (cada una una vez, en el mes en que empieza) ----
    # Siete meses: los cinco anteriores, el actual y el siguiente. El estado sale de las fechas, no del campo
    # estado (que no cambia solo): ya terminó, está ocurriendo o todavía no empieza. Las canceladas no se cuentan.
    local = timezone.localtime(ahora)
    meses = []
    anio, mes = local.year, local.month
    for desplazamiento in range(-5, 2):
        m = mes + desplazamiento
        a = anio + (m - 1) // 12
        m = (m - 1) % 12 + 1
        meses.append((a, m))
    tz = timezone.get_current_timezone()
    desde = timezone.make_aware(datetime(meses[0][0], meses[0][1], 1), tz)
    a_fin, m_fin = meses[-1][0] + (meses[-1][1] // 12), meses[-1][1] % 12 + 1
    hasta = timezone.make_aware(datetime(a_fin, m_fin, 1), tz)
    indice = {am: k for k, am in enumerate(meses)}
    data_fin = [0] * len(meses)
    data_curso = [0] * len(meses)
    data_prox = [0] * len(meses)
    for ini, fin in (act_qs.exclude(estado='CANCELADA')
                     .filter(fecha_inicio__gte=desde, fecha_inicio__lt=hasta)
                     .values_list('fecha_inicio', 'fecha_fin')):
        k = indice.get((timezone.localtime(ini).year, timezone.localtime(ini).month))
        if k is None:
            continue
        if fin and fin <= ahora:
            data_fin[k] += 1
        elif ini <= ahora:
            data_curso[k] += 1
        else:
            data_prox[k] += 1
    labels_meses = [MESES_CORTOS[m - 1] + (f' {a}' if m == 1 or k == 0 else '') for k, (a, m) in enumerate(meses)]
    mes_actual = 5
    rango_meses = f'{MESES_CORTOS[meses[0][1] - 1]} {meses[0][0]} a {MESES_CORTOS[meses[-1][1] - 1].lower()} {meses[-1][0]}'

    # ---- Talleres ya realizados: inscritos y asistentes (las masivas no tienen inscripción; los que no han
    # empezado quedarían con 0 asistentes y parecería inasistencia) ----
    comp = (
        act_qs
        .filter(tipo='TALLER', fecha_inicio__lte=ahora)
        .exclude(estado='CANCELADA')
        .annotate(
            ti=Count('inscripciones', distinct=True),
            ta=Count('asistencias', distinct=True),
        )
        .filter(ti__gt=0)
        .order_by('-fecha_inicio', 'titulo')[:8]
    )
    labels_comp = [a.titulo for a in comp]
    data_comp_insc = [a.ti for a in comp]
    data_comp_asis = [a.ta for a in comp]

    # ---- Dona de escuelas (solo escuelas con asistentes > 0) ----
    escuela_count = defaultdict(int)
    for i in asis_qs.order_by().values('escuela').annotate(t=Count('id')):
        escuela_count[i['escuela'] or 'Sin asignar'] += i['t']

    escuelas_con_datos = [(e, t) for e, t in escuela_count.items() if t > 0]
    escuelas_con_datos.sort(key=lambda x: -x[1])
    escuelas_con_datos = escuelas_con_datos[:6]

    labels_escuela = [e for e, _ in escuelas_con_datos]
    data_escuela = [t for _, t in escuelas_con_datos]
    mapa = colores_escuelas()
    data_colores_escuela = [color_para_escuela(e, mapa) for e in labels_escuela]

    return {
        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
        'data_colores_pastel': data_colores_pastel,
        'labels_meses': labels_meses,
        'data_meses_finalizadas': data_fin,
        'data_meses_en_curso': data_curso,
        'data_meses_proximas': data_prox,
        'mes_actual': mes_actual,
        'rango_meses': rango_meses,
        'tipos_barras': tipos_barras,
        'escuelas_pastel': escuelas_pastel,
        'total_carreras': total_carreras,
        'labels_comp': labels_comp,
        'data_comp_inscritos': data_comp_insc,
        'data_comp_asistentes': data_comp_asis,
        'labels_escuela': labels_escuela,
        'data_escuela': data_escuela,
        'data_colores_escuela': data_colores_escuela,
    }


def _aplicar_filtros_dashboard(qs_act, qs_asis, rango, tipo, carrera, jornada, ahora, hoy):
    if rango == 'hoy':
        qs_act = qs_act.filter(fecha_inicio__date=hoy)
        qs_asis = qs_asis.filter(fecha_ingreso__date=hoy)
    elif rango == '7dias':
        desde = ahora - timedelta(days=7)
        qs_act = qs_act.filter(fecha_inicio__gte=desde)
        qs_asis = qs_asis.filter(fecha_ingreso__gte=desde)
    elif rango == 'mes':
        qs_act = qs_act.filter(fecha_inicio__year=ahora.year, fecha_inicio__month=ahora.month)
        qs_asis = qs_asis.filter(fecha_ingreso__year=ahora.year, fecha_ingreso__month=ahora.month)

    if tipo in ['MASIVA', 'TALLER']:
        qs_act = qs_act.filter(tipo=tipo)
        qs_asis = qs_asis.filter(actividad__tipo=tipo)
    if carrera:
        qs_act = qs_act.filter(carreras__nombre=carrera)
    if jornada:
        qs_act = qs_act.filter(jornadas__nombre=jornada)
    qs_asis = _filtrar_por_foto(qs_asis, carrera, jornada)
    return qs_act.distinct(), qs_asis.distinct()


@login_required
@role_required('Administrador', 'Creador de Evento', redirect_name='escaneo')
def dashboard(request):
    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    act_qs = Actividad.objects.all()
    asis_qs = Asistencia.objects.all()
    insc_qs = Inscripcion.objects.all()
    notif_qs = NotificacionCorreo.objects.all()

    if es_creador and not es_admin:
        act_qs = act_qs.filter(creado_por=request.user)
        asis_qs = asis_qs.filter(actividad__creado_por=request.user)
        insc_qs = insc_qs.filter(actividad__creado_por=request.user)
        notif_qs = notif_qs.filter(actividad__creado_por=request.user)

    # localdate: la fecha de hoy en Chile (now().date() es la de UTC y entre las 21:00 y las 24:00 ya es mañana)
    ahora, hoy = timezone.now(), timezone.localdate()
    rango = request.GET.get('rango', '')
    tipo = request.GET.get('tipo', '')
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')

    act_qs, asis_qs = _aplicar_filtros_dashboard(
        act_qs, asis_qs, rango, tipo, carrera, jornada, ahora, hoy
    )

    agg = act_qs.aggregate(
        activas=Count('id', filter=Actividad.vigente_q(ahora)),
        finalizadas=Count('id', filter=Actividad.finalizada_q(ahora)),
        total=Count('id'),
        # Para el promedio de asistentes: las que ya empezaron (las futuras aún no tienen asistentes)
        realizadas=Count('id', filter=Q(fecha_inicio__lte=ahora) & ~Q(estado='CANCELADA')),
    )
    total_asis = asis_qs.count()
    total_inscritos = _filtrar_por_foto(
        insc_qs.filter(actividad__in=act_qs), carrera, jornada
    ).count()

    # Uso del cache helper
    carreras_cache = _get_carreras_cache()
    graficos = _construir_graficos_dashboard(asis_qs, act_qs, carreras_cache, ahora)

    ultimos_logs = LogAuditoria.objects.all().order_by('-fecha_registro')
    if es_creador and not es_admin:
        ultimos_logs = ultimos_logs.filter(usuario_sistema=request.user)

    context = {
        'nombre_usuario': request.user.first_name or request.user.username,
        'actividades_activas': agg['activas'],
        'talleres_proximos': act_qs.filter(
            tipo='TALLER', estado='ACTIVA', fecha_inicio__gte=ahora, cupos_disponibles__gt=0
        ).count(),
        'total_inscritos': total_inscritos,
        'asistencias_hoy': asis_qs.filter(fecha_ingreso__date=hoy).count(),
        'invitaciones_enviadas': notif_qs.filter(actividad__in=act_qs, estado_envio='EXITO').count(),
        'actividades_finalizadas': agg['finalizadas'],
        'promedio_asistentes': (round(asis_qs.filter(actividad__fecha_inicio__lte=ahora)
                                      .exclude(actividad__estado='CANCELADA').count() / agg['realizadas'], 1)
                                if agg['realizadas'] else 0),
        'cupos_disponibles_totales': act_qs.filter(Actividad.vigente_q(ahora), tipo='TALLER')
            .aggregate(t=Sum('cupos_disponibles')).get('t') or 0,
        'tasa_asistencia': round(total_asis / total_inscritos * 100, 1) if total_inscritos else 0,
        'actividades_proximas': act_qs.filter(estado='ACTIVA', fecha_inicio__gte=ahora)
            .order_by('fecha_inicio')[:4],
        'alertas': {
            'talleres_sin_cupos': act_qs.filter(Actividad.vigente_q(ahora), tipo='TALLER',
                                                cupos_disponibles=0).count(),
            'comienzan_hoy': act_qs.filter(estado='ACTIVA', fecha_inicio__date=hoy).count(),
            'sin_inscritos': act_qs.filter(Actividad.vigente_q(ahora), inscripciones__isnull=True).count(),
            'correos_fallidos': notif_qs.filter(actividad__in=act_qs, estado_envio='FALLO').count(),
        },
        'ultimas_asistencias': asis_qs.select_related('alumno', 'actividad')
            .order_by('-fecha_ingreso')[:5],
        'ultimas_actividades_creadas': act_qs.order_by('-fecha_creacion')[:5],
        'ultimos_logs': ultimos_logs[:5],
        'actividades': act_qs.annotate(
            total_inscritos=Count('inscripciones', distinct=True),
            total_asistentes=Count('asistencias', distinct=True),
        ).order_by('-fecha_inicio')[:8],
        'carreras_opciones': Carrera.objects.all().order_by('nombre'),
        'jornadas_opciones': Jornada.objects.all().order_by('nombre'),
        'rango_actual': rango, 'tipo_actual': tipo,
        'carrera_actual': carrera, 'jornada_actual': jornada,
        **_construir_desglose_tipo(act_qs, asis_qs, carrera, jornada),
        **graficos,
    }

    if es_admin:
        from ..servicios.retencion import proceso_abierto
        aviso = proceso_abierto()
        if aviso:
            context['retencion'] = {'aviso': aviso, 'faltan': (aviso.fecha_programada - timezone.localdate()).days}

    return render(request, 'gestion/dashboard.html', context)


@login_required
@role_required('Administrador')
@require_POST
def retencion_ejecutar(request, pk):
    aviso = get_object_or_404(AvisoRetencion, pk=pk)
    if request.POST.get('verificado') != 'on':
        messages.error(request, 'Marca la casilla para confirmar que verificaste los respaldos antes de borrar.')
        return redirect('dashboard')
    try:
        resumen = ejecutar(aviso, request.user)
    except YaEjecutado as e:
        previo = e.args[0]
        messages.info(request, f'{nombre_usuario(previo.ejecutado_por)} ya había ejecutado este borrado el '
                               f'{timezone.localtime(previo.ejecutado):%d/%m/%Y}.')
        return redirect('dashboard')
    messages.success(request, f'Listo: se borraron {resumen["actividades"]} actividades y {resumen["auditoria"]} '
                              f'registros de auditoría anteriores al {aviso.fecha_corte:%d/%m/%Y}. Se avisó a los '
                              f'demás Administradores.')
    return redirect('dashboard')
