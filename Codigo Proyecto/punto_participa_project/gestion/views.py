# ==================== IMPORTS ====================
import csv
import logging
from django.core.cache import cache as cache_django
logger = logging.getLogger(__name__)
import re

from collections import defaultdict
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .utils import limpiar_texto, limpiar_documento, fecha_o_none, id_o_none

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from django_ratelimit.decorators import ratelimit
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET
 
from .decorators import role_required
from .forms import ActividadForm
from .models import (
    Actividad, Alumno, Asistencia, Carrera, Escuela, Inscripcion, Jornada, Lugar,
    LogAuditoria, NotificacionCorreo, Rol, TurnoEscaneo, UsuarioSistema,
)
# [REFACTOR Opción B] Permisos centralizados
from .permissions import ( ROLES_VALIDOS, get_perfil, puede_gestionar_actividad,tiene_rol,)
from .utils import buscar_alumno_por_documento, formatear_rut, normalizar_documento


# ==================== COLORES DE LAS ESCUELAS ====================
# El color de cada escuela se elige en Catálogos > Escuelas. Esta lista de colores
# oficiales web de Duoc UC se usa para llenar el catálogo la primera vez y como respaldo
# para escuelas sin color.
COLOR_POR_ESCUELA = {
    'Escuela de Administración y Negocios': '#AC4FC6',
    'Escuela de Administración y Finanzas': '#AC4FC6',
    'Escuela de Comunicación': '#D50032',
    'Escuela de Comunicaciones': '#D50032',
    'Escuela de Construcción': '#E87722',
    'Escuela de Diseño': '#C4D600',
    'Escuela de Gastronomía': '#FF585D',
    'Escuela de Informática y Telecomunicaciones': '#307FE2',
    'Escuela de Ingeniería': '#43B02A',
    'Escuela de Recursos Naturales': '#43B02A',
    'Escuela de Salud': '#5BC2E7',
    'Escuela de Turismo': '#00A499',
}

COLORES_FALLBACK = [
    '#307FE2', '#FFB800', '#43B02A', '#D50032',
    '#E87722', '#5BC2E7', '#AC4FC6', '#00A499',
    '#C4D600', '#666666',
]


COLOR_SIN_ESCUELA = '#666666'


def colores_escuelas():
    """{nombre de escuela: color} según el catálogo (una sola consulta)."""
    return dict(Escuela.objects.exclude(color='').values_list('nombre', 'color'))


def color_para_escuela(escuela, colores=None):
    """Color de la escuela: el del catálogo, el oficial conocido o gris.

    En ciclos, pasa `colores=colores_escuelas()` para no consultar la BBDD cada vez.
    """
    if not escuela:
        return COLOR_SIN_ESCUELA
    nombre = escuela.strip()
    if colores is None:
        colores = colores_escuelas()
    return colores.get(nombre) or COLOR_POR_ESCUELA.get(nombre, COLOR_SIN_ESCUELA)


# ============================================================
# HELPERS GENERALES
# ============================================================

def registrar_log(request, modulo, accion, detalle, objeto_tipo=None, objeto_id=None,
                  objeto_nombre=None, cambios_json=None):
    def _cortar(valor, largo):
        return valor[:largo] if isinstance(valor, str) else valor

    LogAuditoria.objects.create(
        usuario_sistema=request.user if request.user.is_authenticated else None,
        modulo=_cortar(modulo, 50),
        accion=_cortar(accion, 200),
        detalle=detalle,
        objeto_tipo=_cortar(objeto_tipo, 50),
        objeto_id=objeto_id,
        objeto_nombre=_cortar(objeto_nombre, 200),
        ip_address=request.META.get('REMOTE_ADDR') or None,
        user_agent=request.META.get('HTTP_USER_AGENT'),
        cambios_json=cambios_json,
    )


_get_perfil_o_none = get_perfil


def _error_json(msg, status=400):
    return JsonResponse({'success': False, 'message': msg}, status=status)


def _es_ajax(request):
    # [REFACTOR] Más robusto: acepta x-requested-with, Accept: application/json, o fetch
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.headers.get('x-requested-with') == 'fetch'
    )


def _validar_password_nueva(user, nueva, confirma, vieja=None):
    """Valida todos los casos de cambio/restablecimiento de contraseña."""
    if not nueva:
        return 'Debes ingresar una nueva contraseña.'
    if nueva != confirma:
        return 'Las contraseñas no coinciden.'
    if vieja is not None and not user.check_password(vieja):
        return 'La contraseña actual es incorrecta.'
    if user.check_password(nueva):
        return 'La nueva contraseña debe ser diferente de la actual.' if vieja else \
               'La nueva contraseña debe ser diferente de la anterior.'
    try:
        validate_password(nueva, user=user)
    except ValidationError as e:
        return ' · '.join(e.messages)
    return None


# ============================================================
# [REFACTOR] HELPERS COMPARTIDOS DE DASHBOARD / REPORTES
# ============================================================

def _get_carreras_cache():
    """Cache único de carreras para evitar 3 queries en distintas vistas."""
    return {c.nombre.lower(): c for c in Carrera.objects.all()}


def _colores_por_carrera(items, carreras_cache):
    """
    Devuelve la lista de colores para una lista de dicts con clave 'carrera'
    (o 'alumno__carrera'). Uso: gráficos de dona por carrera.
    """
    colores = []
    mapa = colores_escuelas()
    for i in items:
        nombre = (i.get('carrera', i.get('alumno__carrera')) or '').lower()
        c = carreras_cache.get(nombre)
        colores.append(color_para_escuela(c.escuela if c else None, mapa))
    return colores

def _filtrar_por_foto(qs, carrera=None, jornada=None, escuela=None, prefijo=''):
    """
    Filtra inscripciones o asistencias por la carrera, jornada o escuela que el alumno
    tenía en ese momento (la "foto" académica), sin distinguir mayúsculas ni espacios.
    Con prefijo (p. ej. 'asistencias__') sirve para armar un Q sobre actividades.
    """
    return qs.filter(_q_foto(carrera, jornada, escuela, prefijo))


def _q_foto(carrera=None, jornada=None, escuela=None, prefijo=''):
    q = Q()
    if escuela and escuela.strip():
        q &= Q(**{f'{prefijo}escuela__iexact': escuela.strip()})
    if carrera and carrera.strip():
        q &= Q(**{f'{prefijo}carrera__iexact': carrera.strip()})
    if jornada and jornada.strip():
        q &= Q(**{f'{prefijo}jornada__iexact': jornada.strip()})
    return q


def _filtrar_inscripciones(insc, carrera=None, jornada=None, escuela=None):
    """Filtra inscripciones con el mismo criterio que las asistencias (la foto académica)."""
    return _filtrar_por_foto(insc, carrera, jornada, escuela)

def _construir_desglose_tipo(act_qs, asis_qs, carrera=None, jornada=None, escuela=None):
    """Calcula masivas/talleres para dashboard y reportes."""
    ids_talleres = list(act_qs.filter(tipo='TALLER').values_list('id', flat=True))
    ids_masivas = list(act_qs.filter(tipo='MASIVA').values_list('id', flat=True))

    insc = Inscripcion.objects.filter(actividad_id__in=ids_talleres)
    insc = _filtrar_inscripciones(insc, carrera, jornada, escuela)

    t_insc = insc.count()
    t_asis = asis_qs.filter(actividad_id__in=ids_talleres).count()
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
        'tasa_talleres': round(t_asis / t_insc * 100, 1) if t_insc else None,
    }


def _construir_graficos_dashboard(asis_qs, act_qs, carreras_cache, ahora):
    """Construye labels/data/colores de los 5 gráficos del dashboard,
    excluyendo elementos sin datos."""

    # ---- Top 5 barras (solo actividades con asistencias > 0) ----
    top = (
        act_qs
        .annotate(t=Count('asistencias'))
        .filter(t__gt=0)
        .order_by('-t')[:5]
    )
    labels_barras = [(a.titulo[:15] + '...') if len(a.titulo) > 15 else a.titulo for a in top]
    data_barras = [a.t for a in top]

    # ---- Dona de carreras (solo carreras con asistentes > 0) ----
    por_carrera = (
        asis_qs
        .values('carrera')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t')[:6]
    )
    labels_pastel = [i['carrera'] or 'Sin carrera' for i in por_carrera]
    data_pastel = [i['t'] for i in por_carrera]
    # [REFACTOR] Uso del helper
    data_colores_pastel = _colores_por_carrera(por_carrera, carreras_cache)

    # ---- Línea mensual ----
    fecha_min = (ahora - timedelta(days=30 * 5)).replace(day=1)

    def agrupar(qs, campo):
        return {
            i['mes'].strftime('%Y-%m'): i['t']
            for i in qs.annotate(mes=TruncMonth(campo))
                    .values('mes').annotate(t=Count('id'))
            if i['mes']
        }

    d_prog = agrupar(act_qs.filter(fecha_inicio__gte=fecha_min), 'fecha_inicio')
    d_curso = agrupar(
        act_qs.filter(fecha_inicio__gte=fecha_min, estado='ACTIVA'),
        'fecha_inicio'
    )
    d_fin = agrupar(
        act_qs.filter(fecha_fin__gte=fecha_min, estado='FINALIZADA'),
        'fecha_fin'
    )

    labels_linea, data_prog, data_curso, data_fin = [], [], [], []
    for i in range(5, -1, -1):
        ref = ahora - timedelta(days=30 * i)
        labels_linea.append(ref.strftime('%b').capitalize())
        data_prog.append(d_prog.get(ref.strftime('%Y-%m'), 0))
        data_curso.append(d_curso.get(ref.strftime('%Y-%m'), 0))
        data_fin.append(d_fin.get(ref.strftime('%Y-%m'), 0))

    # ---- Comparativo: TODAS las actividades con datos reales ----
    comp = (
        act_qs
        .annotate(
            ti=Count('inscripciones', distinct=True),
            ta=Count('asistencias', distinct=True),
        )
        .filter(Q(ti__gt=0) | Q(ta__gt=0))
        .order_by('-ti', '-ta')[:10]
    )
    labels_comp = [(a.titulo[:12] + '...') if len(a.titulo) > 12 else a.titulo for a in comp]
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
        'labels_linea': labels_linea,
        'data_programadas': data_prog,
        'data_en_curso': data_curso,
        'data_finalizadas': data_fin,
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


# [REFACTOR] Filtros de reportes/export unificados
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

# ============================================================
# CAMBIO / RECUPERACIÓN DE CONTRASEÑA
# ============================================================

@login_required
@sensitive_post_parameters('contrasena_actual', 'nueva_contrasena', 'confirmar_contrasena')
def cambiar_contrasena(request):
    perfil = _get_perfil_o_none(request.user)
    if not perfil:
        messages.error(request, 'Tu cuenta no tiene un perfil válido en el sistema.')
        return redirect('login')
    if not perfil.activo:
        messages.error(request, 'Tu cuenta está desactivada.')
        return redirect('login')
    if not perfil.rol:
        messages.error(request, 'Tu cuenta no tiene un rol asignado.')
        return redirect('login')

    if request.method == 'POST':
        actual = request.POST.get('contrasena_actual', '')
        nueva = request.POST.get('nueva_contrasena', '')
        confirma = request.POST.get('confirmar_contrasena', '')

        error = _validar_password_nueva(request.user, nueva, confirma, vieja=actual)
        if error:
            messages.error(request, error)
            return render(request, 'gestion/cambiar_contrasena.html')

        request.user.set_password(nueva)
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)
        perfil.must_change_password = False
        perfil.save(update_fields=['must_change_password'])

        registrar_log(request, 'Seguridad', 'Cambio de contraseña',
                      f'Usuario "{request.user.username}" cambió su contraseña',
                      'Usuario', request.user.id, request.user.username)
        messages.success(request, 'Contraseña actualizada correctamente.')
        return redirect('escaneo' if perfil.rol.nombre == 'Encargado de Registrar' else 'dashboard')

    return render(request, 'gestion/cambiar_contrasena.html')


@sensitive_post_parameters('password')
@ratelimit(key='ip', rate='5/15m', method='POST', block=True)
def login_view(request):
    if request.method != 'POST':
        return render(request, 'gestion/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    def _fail():
        messages.error(request, 'Usuario o contraseña incorrectos.')
        return render(request, 'gestion/login.html')

    if not username or not password:
        messages.error(request, 'Debes ingresar usuario y contraseña.')
        return render(request, 'gestion/login.html')

    user = authenticate(request, username=username, password=password)
    if not user or not user.is_active:
        return _fail()

    perfil = _get_perfil_o_none(user)
    if not perfil or not perfil.activo or not perfil.rol:
        return _fail()

        
    rol = perfil.rol.nombre
    if rol not in ROLES_VALIDOS:
        messages.error(request, 'La cuenta tiene un rol no válido.')
        return render(request, 'gestion/login.html')

    login(request, user)

    if perfil.must_change_password:
        return redirect('cambiar_contrasena')

    # [REFACTOR Opción B] Respetar ?next= si existe (solo rutas relativas)
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)

    return redirect('escaneo' if rol == 'Encargado de Registrar' else 'dashboard')


@login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('login')


@ratelimit(key='ip', rate='5/15m', method='POST', block=True)
def solicitar_recuperacion(request):
    if request.method != 'POST':
        return render(request, 'gestion/recuperar_contrasena.html')

    identificador = request.POST.get('identificador', '').strip()
    if not identificador:
        messages.error(request, 'Ingresa tu usuario o correo electrónico.')
        return render(request, 'gestion/recuperar_contrasena.html')

    usuario = (User.objects.filter(username=identificador).first() or
               User.objects.filter(email__iexact=identificador).first())

    if usuario and usuario.is_active and usuario.email and usuario.email.strip():
        try:
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = PasswordResetTokenGenerator().make_token(usuario)
            enlace = f'{settings.SITE_URL.rstrip("/")}/restablecer-contrasena/{uid}/{token}/'
            html = render_to_string('gestion/email_recuperacion.html',
                                    {'user': usuario, 'enlace': enlace})
            send_mail(
                subject='Recuperación de contraseña - Punto Participa',
                message=f'Restablece tu contraseña aquí:\n\n{enlace}\n',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[usuario.email.strip()],
                html_message=html, fail_silently=False,
            )
            registrar_log(request, 'Seguridad', 'Solicitud de recuperación de contraseña',
                          f'Enlace enviado a "{usuario.username}".',
                          'Usuario', usuario.id, usuario.username)
        except Exception:
            logger.exception('Error enviando correo de recuperación (user %s)', usuario.id)

    messages.success(request, 'Si el usuario existe y tiene un correo registrado, '
                              'recibirá instrucciones para restablecer su contraseña.')
    return redirect('login')


@sensitive_post_parameters('nueva_contrasena', 'confirmar_contrasena')
def restablecer_contrasena(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        usuario = User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        usuario = None

    if not (usuario and PasswordResetTokenGenerator().check_token(usuario, token)):
        return render(request, 'gestion/restablecer_contrasena.html', {'token_valido': False})

    if request.method == 'POST':
        nueva = request.POST.get('nueva_contrasena', '')
        confirma = request.POST.get('confirmar_contrasena', '')

        error = _validar_password_nueva(usuario, nueva, confirma)
        if error:
            messages.error(request, error)
            return render(request, 'gestion/restablecer_contrasena.html', {'token_valido': True})

        usuario.set_password(nueva)
        usuario.save(update_fields=['password'])
        perfil = _get_perfil_o_none(usuario)
        if perfil:
            perfil.must_change_password = False
            perfil.save(update_fields=['must_change_password'])

        registrar_log(request, 'Seguridad', 'Restablecimiento de contraseña',
                      f'Usuario "{usuario.username}" restableció su contraseña.',
                      'Usuario', usuario.id, usuario.username)
        messages.success(request, 'Tu contraseña fue restablecida correctamente.')
        return redirect('login')

    return render(request, 'gestion/restablecer_contrasena.html', {'token_valido': True})


# ============================================================
# DASHBOARD
# ============================================================

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

    ahora, hoy = timezone.now(), timezone.now().date()
    rango = request.GET.get('rango', '')
    tipo = request.GET.get('tipo', '')
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')

    act_qs, asis_qs = _aplicar_filtros_dashboard(
        act_qs, asis_qs, rango, tipo, carrera, jornada, ahora, hoy
    )

    agg = act_qs.aggregate(
        activas=Count('id', filter=Q(estado='ACTIVA')),
        finalizadas=Count('id', filter=Q(estado='FINALIZADA')),
        total=Count('id'),
    )
    total_asis = asis_qs.count()
    total_inscritos = _filtrar_inscripciones(
        insc_qs.filter(actividad__in=act_qs), carrera, jornada
    ).count()

    # [REFACTOR] Uso del cache helper
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
        'promedio_asistentes': round(total_asis / agg['total'], 1) if agg['total'] else 0,
        'cupos_disponibles_totales': act_qs.filter(tipo='TALLER', estado='ACTIVA')
            .aggregate(t=Sum('cupos_disponibles')).get('t') or 0,
        'tasa_asistencia': round(total_asis / total_inscritos * 100, 1) if total_inscritos else 0,
        'actividades_proximas': act_qs.filter(estado='ACTIVA', fecha_inicio__gte=ahora)
            .order_by('fecha_inicio')[:4],
        'alertas': {
            'talleres_sin_cupos': act_qs.filter(tipo='TALLER', estado='ACTIVA', cupos_disponibles=0).count(),
            'comienzan_hoy': act_qs.filter(estado='ACTIVA', fecha_inicio__date=hoy).count(),
            'sin_inscritos': act_qs.filter(estado='ACTIVA', inscripciones__isnull=True).count(),
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

    # [REFACTOR] Debug temporal eliminado.
    return render(request, 'gestion/dashboard.html', context)


# ============================================================
# REPORTES
# ============================================================

@login_required
@role_required('Administrador', 'Creador de Evento')
def reportes(request):
    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    escuela = request.GET.get('escuela', '') 
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    actividad_id = request.GET.get('actividad', '')

    # [REFACTOR] Filtros unificados
    act_qs, asis_qs = _aplicar_filtros_reporte(request)

    ids_act = list(act_qs.values_list('id', flat=True))

    filtro_asis = _q_foto(carrera, jornada, escuela, prefijo='asistencias__')
    filtro_insc = _q_foto(carrera, jornada, escuela, prefijo='inscripciones__')

    act_qs = act_qs.select_related('creado_por').annotate(
        total_asistentes_calc=Count('asistencias', filter=filtro_asis or None, distinct=True),
        total_inscritos_calc=Count('inscripciones', filter=filtro_insc or None, distinct=True),
    ).prefetch_related('carreras', 'jornadas')

    total_inscritos = _filtrar_inscripciones(
        Inscripcion.objects.filter(actividad_id__in=ids_act),
        carrera, jornada, escuela,
    ).count()
    total_asistentes = asis_qs.count()

    # [REFACTOR] Uso del cache helper
    carreras_cache = _get_carreras_cache()

    # ---- Dona de Carreras (general) ----
    por_carrera = (
        asis_qs.values('carrera')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t')
    )
    labels_pastel = [i['carrera'] or 'Sin carrera' for i in por_carrera]
    data_pastel = [i['t'] for i in por_carrera]
    # [REFACTOR] Uso del helper
    data_colores_pastel = _colores_por_carrera(por_carrera, carreras_cache)

    # ---- Barras de Jornada (general) ----
    por_jornada = (
        asis_qs.values('jornada')
        .annotate(t=Count('id'))
        .filter(t__gt=0)
        .order_by('-t')
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
    for a in act_qs:
        a.total_asistentes = a.total_asistentes_calc
        a.total_inscritos = a.total_inscritos_calc
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
                'fecha': a.fecha_inicio.strftime("%d/%m/%Y"),
                'escuela': escuela_item, 'carrera': carrera_n, 'jornada': jornada_n,
                'asistentes': vals['t'],
                'registrado_por': ", ".join(f"{u} ({c})" for u, c in vals['regs'].items()),
            })
            det_escuelas[escuela_item] += vals['t']
            det_carreras[carrera_n] += vals['t']

    # ---- Colores del detalle ----
    mapa = colores_escuelas()
    data_colores_barras_detalle = [color_para_escuela(e, mapa) for e in det_escuelas.keys()]
    data_colores_pastel_detalle = []
    for carrera_n in det_carreras.keys():
        data_colores_pastel_detalle.append(color_para_escuela(escuela_de_carrera.get(carrera_n), mapa))

    actividades_opciones = (
        Actividad.objects.filter(creado_por=request.user) if (es_creador and not es_admin)
        else Actividad.objects.all()
    ).order_by('-fecha_inicio')

    # ---- Barras general: solo actividades con al menos 1 asistente ----
    acts_con_datos = [a for a in act_qs if a.total_asistentes_calc > 0]
    labels_barras = [a.titulo for a in acts_con_datos]
    data_barras = [a.total_asistentes_calc for a in acts_con_datos]
    total_acts_con_datos = len(acts_con_datos)

    from .utils import paginar
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
        'labels_pastel_detalle': list(det_carreras.keys()),
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


# ============================================================
# EXPORTAR REPORTES
# ============================================================

# Caracteres con los que Excel/LibreOffice interpretan una celda como fórmula
_PREFIJOS_FORMULA = ('=', '+', '-', '@', '\t', '\r')


def _sanitizar_celda(valor):
    """
    Neutraliza la inyección de fórmulas en exportaciones CSV/Excel.
    Si un texto empieza con un carácter de fórmula, se le antepone un
    apóstrofe para que la planilla lo trate como texto literal.
    También quita caracteres de control (NUL, etc.) que harían fallar
    la exportación a Excel. Los valores que no son texto (números,
    fechas) pasan sin cambios.
    """
    if isinstance(valor, str):
        valor = ILLEGAL_CHARACTERS_RE.sub('', valor)
    if isinstance(valor, str) and valor.startswith(_PREFIJOS_FORMULA):
        return "'" + valor
    return valor


def _exportar_excel(datos, headers, filename, sheet_name='Reporte'):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    h_font = Font(bold=True, color="FFFFFF")
    h_fill = PatternFill(start_color="132CAA", end_color="132CAA", fill_type="solid")

    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = h_font
        c.fill = h_fill
        c.alignment = Alignment(horizontal="center")

    for r, fila in enumerate(datos, start=2):
        for col, val in enumerate(fila, start=1):
            ws.cell(row=r, column=col, value=_sanitizar_celda(val))

    for col in ws.columns:
        max_len = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    wb.save(response)
    return response


def _exportar_csv(datos, headers, filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    response.write('\ufeff')  # BOM: hace que Excel reconozca UTF-8 y muestre bien tildes y ñ
    writer = csv.writer(response, delimiter=';')
    writer.writerow(headers)
    writer.writerows([[_sanitizar_celda(v) for v in fila] for fila in datos])
    return response


# ============================================================
# USUARIOS
# ============================================================

@login_required
@role_required('Administrador')
def usuarios(request):
    from .utils import paginar
    qs = UsuarioSistema.objects.select_related('user', 'rol').order_by('-id')
    buscar = limpiar_texto(request.GET.get('q', ''))[:100]
    if buscar:
        qs = qs.filter(Q(user__username__icontains=buscar) | Q(user__first_name__icontains=buscar)
                       | Q(user__email__icontains=buscar)
                       | Q(rut__icontains=normalizar_documento(buscar) or buscar))
    if request.GET.get('rol'):
        qs = qs.filter(rol__nombre=request.GET['rol'])
    if request.GET.get('estado') in ('activo', 'bloqueado'):
        qs = qs.filter(activo=request.GET['estado'] == 'activo')
    return render(request, 'gestion/usuarios.html', {
        'usuarios': paginar(request, qs),
        'logs': LogAuditoria.objects.all().order_by('-fecha_registro')[:10],
        'roles': Rol.objects.all(),
    })

_validador_username = UnicodeUsernameValidator()
_MSG_USERNAME = ('El nombre de usuario solo puede contener letras, números y '
                 'los símbolos @ . + - _ (máximo 150 caracteres).')
 
 
def _username_valido(username):
    if not username or len(username) > 150:
        return False
    try:
        _validador_username(username)
    except ValidationError:
        return False
    return True
 
 
def _id_valido(valor):
    """True si es un entero positivo corto (evita ValueError y desbordes en pk)."""
    return bool(valor) and valor.isascii() and valor.isdecimal() and len(valor) <= 9

@login_required
@role_required('Administrador', json_response=True)
@sensitive_post_parameters('password')
def guardar_usuario(request):
    if request.method != 'POST':
        return _error_json('Método no permitido', 405)

    try:
        usuario_id = limpiar_documento(request.POST.get('user_id'), 20)
        username = limpiar_texto(request.POST.get('username') or '')
        nombre = limpiar_texto(request.POST.get('nombre') or '')
        email = limpiar_texto(request.POST.get('email') or '')
        rol_id = limpiar_documento(request.POST.get('rol'), 20)
        estado = request.POST.get('estado') == 'on'

        # --- RUT / documento: obligatorio, normalizado, sin validar módulo 11 ---
        rut = normalizar_documento(limpiar_texto(request.POST.get('rut') or ''))
        confirmar_rut = request.POST.get('confirmar_rut', '').lower() == 'true'
        rut_max = UsuarioSistema._meta.get_field('rut').max_length

        if not (username and nombre and email and rol_id):
            return _error_json('Faltan campos obligatorios')
        if not rut:
            return _error_json('El RUT o documento es obligatorio.')
        if len(rut) > rut_max:
            return _error_json(f'El RUT no puede superar los {rut_max} caracteres.')

        # --- Validación de formato y largo (evita errores de BD) ---
        if (usuario_id and not _id_valido(usuario_id)) or not _id_valido(rol_id):
            return _error_json('Datos inválidos.')
        if len(nombre) > 150:
            return _error_json('El nombre no puede superar los 150 caracteres.')
        try:
            if len(email) > 254:
                raise ValidationError('largo')
            validate_email(email)
        except ValidationError:
            return _error_json('El correo electrónico no es válido.')

        usuario_sistema = None
        rol_anterior = estado_anterior = None
        password_temporal = None

        if usuario_id:
            usuario_sistema = UsuarioSistema.objects.get(pk=usuario_id)
            user = usuario_sistema.user
            if user == request.user and not estado:
                return _error_json('No puedes bloquear tu propia cuenta.')
            # Solo se valida el formato si el username cambió
            # (no rompe usuarios antiguos con formato distinto).
            if user.username != username:
                if not _username_valido(username):
                    return _error_json(_MSG_USERNAME)
                if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                    return _error_json('Ese nombre de usuario ya está en uso')
            user.username = username
            rol_anterior = usuario_sistema.rol.nombre if usuario_sistema.rol else None
            estado_anterior = usuario_sistema.activo
        else:
            if not _username_valido(username):
                return _error_json(_MSG_USERNAME)
            if User.objects.filter(username=username).exists():
                return _error_json('Ese nombre de usuario ya está en uso')
            user = User(username=username)
            password_temporal = get_random_string(
                length=12,
                allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
            )
            user.set_password(password_temporal)

        # --- RUT duplicado en otro usuario ---
        duplicado = UsuarioSistema.objects.filter(rut=rut)
        if usuario_sistema:
            duplicado = duplicado.exclude(pk=usuario_sistema.pk)
        if duplicado.exists():
            return _error_json('Ese RUT o documento ya está asignado a otro usuario.')

        # --- Cambio de RUT: el servidor exige confirmación ---
        rut_anterior = normalizar_documento(usuario_sistema.rut) if usuario_sistema else ''
        rut_cambia = bool(rut_anterior) and rut_anterior != rut
        if rut_cambia and not confirmar_rut:
            return JsonResponse({
                'success': False,
                'confirmar_rut': True,
                'message': 'Vas a cambiar el RUT o documento de este usuario. ¿Confirmas el cambio?',
            })

        rol = Rol.objects.get(pk=rol_id)  # antes de escribir nada

        # Atómico: si falla UsuarioSistema (p. ej. RUT duplicado) no queda un User huérfano
        with transaction.atomic():
            user.email, user.first_name, user.is_active = email, nombre, estado
            user.save()

            if usuario_sistema is None:
                usuario_sistema = UsuarioSistema(user=user)
            usuario_sistema.rol = rol
            usuario_sistema.activo = estado
            usuario_sistema.rut = rut
            usuario_sistema.save()

        if rol_anterior != usuario_sistema.rol.nombre:
            registrar_log(request, 'Usuarios', 'Cambio de rol',
                          f'"{user.username}": de "{rol_anterior}" a "{usuario_sistema.rol.nombre}"',
                          'Usuario', user.id, user.username)

        if estado_anterior is not None and estado_anterior != estado:
            registrar_log(request, 'Usuarios', 'Cambio de estado',
                          f'"{user.username}": de "{"Activo" if estado_anterior else "Inactivo"}" '
                          f'a "{"Activo" if estado else "Inactivo"}"',
                          'Usuario', user.id, user.username)

        if rut_cambia:
            registrar_log(request, 'Usuarios', 'Cambio de RUT',
                          f'"{user.username}": se modificó el documento de identidad',
                          'Usuario', user.id, user.username)

        registrar_log(request, 'Usuarios', 'Guardar usuario',
                      f'Usuario: {nombre} ({username})', 'Usuario', user.id, nombre)

        resp = {'success': True}
        if password_temporal:
            resp['password_temporal'] = password_temporal
        return JsonResponse(resp)

    except (UsuarioSistema.DoesNotExist, Rol.DoesNotExist):
        return _error_json('Usuario o rol no encontrado.', 404)
    except IntegrityError:
        return _error_json('Ya existe un usuario con ese nombre de usuario o RUT.', 409)
    except Exception:
        logger.exception('Error en guardar_usuario')
        return _error_json('Ocurrió un error inesperado.', 500)


# ============================================================
# CRUD ACTIVIDADES
# ============================================================

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

    from .utils import paginar
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
    mayor = max([v for _, v, _ in pasos] + [1])
    datos['pasos'] = [{'etiqueta': e, 'valor': v, 'clase': c, 'ancho': round(v / mayor * 100)}
                      for e, v, c in pasos]
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

    from .utils import paginar
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

    from .utils import paginar
    return render(request, 'gestion/actividad_participantes.html', {
        'actividad': actividad,
        'inscripciones': paginar(request, insc, param='page_insc'),
        'asistencias': paginar(request, asis, param='page_asis'),
        'filtro_estado': filtro,
        'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
        'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
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

    # [REFACTOR] Delegado al modelo (si implementás Actividad.recalcular_cupos)
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
    if actividad.tipo == 'INVITACION' and getattr(form, 'filas_invitados', None):
        from .views_invitados import cargar_lista
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


# ============================================================
# INVITACIONES
# ============================================================

@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def enviar_invitaciones(request):
    if request.method != 'POST':
        return _error_json('Método no permitido.', 405)

    try:
        actividad_id = id_o_none(request.POST.get('actividad_id'))
        if not actividad_id:
            return _error_json('No se recibió la actividad.')

        actividad = get_object_or_404(Actividad, pk=actividad_id)
        if not puede_gestionar_actividad(request.user, actividad):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        if actividad.tipo == 'INVITACION':
            # Sin este corte, una actividad sin carreras le escribiría a toda la nómina
            return _error_json('Las invitaciones de esta actividad se envían a su lista de invitados.', 400)

        carreras = list(actividad.carreras.values_list('nombre', flat=True))
        jornadas = list(actividad.jornadas.values_list('nombre', flat=True))

        alumnos = Alumno.objects.filter(activo=True)
        if carreras:
            alumnos = alumnos.filter(carrera__in=carreras)
        if jornadas:
            alumnos = alumnos.filter(jornada__in=jornadas)
        if settings.MAX_INVITACIONES_POR_ENVIO > 0:
            alumnos = alumnos[:settings.MAX_INVITACIONES_POR_ENVIO]

        filtro = 'Todas las asociadas'
        if carreras or jornadas:
            filtro = (f"Carreras: {', '.join(carreras) or 'Todas'} | "
                      f"Jornadas: {', '.join(jornadas) or 'Todas'}")

        enviados = fallidos = 0
        for alumno in alumnos:
            try:
                html = render_to_string('gestion/email_invitacion.html', {
                    'actividad': actividad, 'alumno': alumno, 'site_url': settings.SITE_URL,
                })
                n = send_mail(
                    subject=f'Invitación: {actividad.titulo}',
                    message=f'Hola {alumno.nombres}, te invitamos a participar en {actividad.titulo}.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[alumno.correo], html_message=html, fail_silently=False,
                )
                if n != 1:
                    raise RuntimeError('Correo no aceptado.')
                NotificacionCorreo.objects.create(actividad=actividad, alumno=alumno,
                                                  estado_envio='EXITO', filtro_aplicado=filtro)
                enviados += 1
            except Exception:
                NotificacionCorreo.objects.create(actividad=actividad, alumno=alumno,
                                                  estado_envio='FALLO', filtro_aplicado=filtro)
                fallidos += 1

        registrar_log(request, 'Actividades', 'Envío de invitaciones',
                      f'Actividad "{actividad.titulo}": {enviados} OK, {fallidos} fallidos.',
                      'Actividad', actividad.id, actividad.titulo)
        return JsonResponse({
            'success': fallidos == 0, 'enviados': enviados, 'fallidos': fallidos,
            'message': f'{enviados} invitaciones enviadas, {fallidos} fallidas.'
        })
    except Exception:
        logger.exception('Error en enviar_invitaciones')
        return _error_json('Ocurrió un error al procesar las invitaciones.', 500)


@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def previsualizar_invitacion(request, pk):
    try:
        actividad = get_object_or_404(Actividad, pk=pk)
        if not puede_gestionar_actividad(request.user, actividad):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        if actividad.tipo == 'INVITACION':
            return _error_json('Las invitaciones de esta actividad se envían a su lista de invitados.', 400)

        carreras = [c.nombre for c in actividad.carreras.all()]
        jornadas = [j.nombre for j in actividad.jornadas.all()]
        alumnos = Alumno.objects.filter(activo=True)
        if carreras:
            alumnos = alumnos.filter(carrera__in=carreras)
        if jornadas:
            alumnos = alumnos.filter(jornada__in=jornadas)

        alumno = alumnos.first()
        if not alumno:
            return _error_json('No hay alumnos que coincidan con los filtros.')

        html = render_to_string('gestion/email_invitacion.html', {
            'actividad': actividad, 'alumno': alumno, 'site_url': settings.SITE_URL,
        })
        return JsonResponse({
            'success': True, 'html': html,
            'alumno_ejemplo': f'{alumno.nombres} {alumno.apellidos}',
            'total_destinatarios': alumnos.count(),
        })
    except Exception:
        logger.exception('Error en previsualizar_invitacion')
        return _error_json('Ocurrió un error inesperado.', 500)


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
    except Exception:
        logger.exception('Error en eliminar_ajax')
        return _error_json('Ocurrió un error inesperado.', 500)


# ============================================================
# ESCÁNER
# ============================================================

# RUN del QR del carnet, tolerante a la puntuacion que cambia segun el teclado:
# 'RUN' + 1 a 3 simbolos + cuerpo + 0 a 2 simbolos + digito verificador.
_RE_RUN_QR = re.compile(r'RUN[^0-9A-Z]{1,3}(\d{1,9})[^0-9A-Z]{0,2}([0-9K])', re.IGNORECASE)


def _parse_rut_escaneo(rut_original):
    """Detecta el método (QR/CODIGO/RUT) y devuelve el documento normalizado."""
    mayus = rut_original.upper()
    if 'SIDIV' in mayus or 'REGISTROCIVIL' in mayus or 'RUN=' in mayus:
        m = _RE_RUN_QR.search(rut_original)
        if m:
            return 'QR', f'{m.group(1)}-{m.group(2).upper()}'
        return 'QR', rut_original
    if "'" in rut_original or '-' in rut_original:
        return 'CODIGO', rut_original.replace("'", "")
    return 'RUT', rut_original

_RE_DOC_CORTO = re.compile(r"^[A-Za-z0-9.\-']{1,20}$")


def _mensaje_no_encontrado(metodo, documento):
    """No repite en pantalla el texto leido de un carnet (QR) ni textos largos o raros.
    Un documento digitado a mano y corto se muestra para detectar errores de tipeo."""
    if metodo != 'QR' and _RE_DOC_CORTO.match(documento or ''):
        return f'Estudiante no encontrado con el documento: {documento}'
    return 'Estudiante no encontrado.'

# ------------------------------------------------------------
# Turno del escáner (P2)
# ------------------------------------------------------------
# El turno empieza al elegir la actividad y termina con "Finalizar turno" (o al cambiar de
# actividad). Se guarda en TurnoEscaneo para que todos vean quién está en turno, y en la
# sesión (id y hora de inicio) para contar lo que registró este operador.

def _turno_inicio(request):
    """Hora de inicio del turno (con zona horaria) o None."""
    valor = request.session.get('turno_inicio')
    try:
        inicio = datetime.fromisoformat(valor) if valor else None
    except (TypeError, ValueError):
        return None
    return inicio if inicio and timezone.is_aware(inicio) else None


def _iniciar_turno(request, actividad):
    turno = TurnoEscaneo.objects.create(usuario=request.user, actividad=actividad)
    request.session['actividad_escaneo_id'] = actividad.id
    request.session['turno_id'] = turno.id
    request.session['turno_inicio'] = turno.inicio.isoformat()
    registrar_log(request, 'Escáner', 'Iniciar turno', f'Turno de escaneo en "{actividad.titulo}".',
                  'Actividad', actividad.id, actividad.titulo)


def _terminar_turno(request):
    """Cierra el turno en curso, lo deja en la auditoría y devuelve un resumen (o None)."""
    act_id = request.session.pop('actividad_escaneo_id', None)
    inicio = _turno_inicio(request)
    request.session.pop('turno_inicio', None)
    turno_id = request.session.pop('turno_id', None)
    if turno_id:
        TurnoEscaneo.objects.filter(pk=turno_id, usuario=request.user, fin__isnull=True).update(
            fin=timezone.now())
    actividad = Actividad.objects.filter(pk=act_id).first() if act_id else None
    if actividad is None:
        return None
    registradas = (Asistencia.objects.filter(actividad=actividad, registrado_por=request.user,
                                             fecha_ingreso__gte=inicio).count() if inicio else 0)
    minutos = int((timezone.now() - inicio).total_seconds() // 60) if inicio else None
    duracion = f' en {minutos} min' if minutos is not None else ''
    registrar_log(request, 'Escáner', 'Finalizar turno',
                  f'Turno en "{actividad.titulo}": {registradas} asistencia{"s" if registradas != 1 else ""}'
                  f' registrada{"s" if registradas != 1 else ""}{duracion}.',
                  'Actividad', actividad.id, actividad.titulo,
                  cambios_json={'registradas': registradas, 'minutos': minutos})
    return {'actividad': actividad, 'registradas': registradas, 'minutos': minutos}


def _contador_escaneo(request, actividad):
    """
    Contador en vivo del escáner: lo que registró este operador en su turno, el total
    de la actividad (todos los operadores) y cuántas lleva cada operador.
    """
    asis = Asistencia.objects.filter(actividad=actividad)
    inicio = _turno_inicio(request)
    if actividad.tipo == 'TALLER':
        meta = Inscripcion.objects.filter(actividad=actividad, estado='CONFIRMADA').count()
        meta_texto = 'inscritos'
    else:
        meta, meta_texto = actividad.cupos_totales, 'cupos'
    # Operadores: quienes ya registraron en la actividad y quienes están en turno ahora (aunque lleven 0)
    en_turno = set(TurnoEscaneo.abiertos(actividad).values_list('usuario_id', flat=True))
    totales = {i['registrado_por_id']: i['t'] for i in
               asis.order_by().values('registrado_por_id').annotate(t=Count('id'))}
    nombres = {u.id: (u.first_name or u.username) for u in User.objects.filter(pk__in=set(totales) | en_turno)}
    operadores = sorted(
        ({'nombre': nombres.get(uid, 'Sin operador'), 'total': t, 'yo': uid == request.user.id,
          'en_turno': uid in en_turno}
         for uid, t in ({**{u: 0 for u in en_turno}, **totales}).items()),
        key=lambda o: (-o['total'], o['nombre'].lower()))
    ultimos = [{
        'nombre': f'{a.alumno.nombres} {a.alumno.apellidos}',
        'metodo': a.get_metodo_ingreso_display(),
        'operador': ('tú' if a.registrado_por_id == request.user.id
                     else (a.registrado_por.first_name or a.registrado_por.username) if a.registrado_por else ''),
        'hora': timezone.localtime(a.fecha_ingreso).strftime('%H:%M'),
    } for a in asis.select_related('alumno', 'registrado_por').order_by('-fecha_ingreso')[:10]]
    return {
        'total': asis.count(),
        'meta': meta,
        'meta_texto': meta_texto,
        'en_turno': len(en_turno),
        'ultimos': ultimos,
        'mi_turno': asis.filter(registrado_por=request.user, fecha_ingreso__gte=inicio).count() if inicio else 0,
        'turno_desde': timezone.localtime(inicio).strftime('%H:%M') if inicio else None,
        'operadores': operadores,
    }


def _procesar_escaneo(request):
    """
    Procesa la solicitud POST del escáner.
    Soporta 4 tipos de documento:
    - RUT chileno (con o sin guion, con o sin puntos, con K mayúscula o minúscula)
    - Pasaporte extranjero (letras + números)
    - RUN provisorio (solo números)
    - Cédula de extranjero (números o alfanumérico)
    """
    rut_original = limpiar_documento(request.POST.get('rut'), 300)
    if not rut_original:
        return _error_json('Debes ingresar un RUT o Pasaporte.')

    confirmar = request.POST.get('confirmar', 'false').lower() == 'true'

    # ============================================================
    # DETECTAR MÉTODO DE INGRESO (QR / CÓDIGO / RUT)
    # ============================================================
    metodo, rut_procesado = _parse_rut_escaneo(rut_original)

    if not rut_procesado:
        return _error_json('Debes ingresar un RUT o Pasaporte válido.')

    # ============================================================
    # VALIDAR ACTIVIDAD EN SESIÓN
    # ============================================================
    actividad_id = request.session.get('actividad_escaneo_id')
    if not actividad_id:
        return _error_json('Primero selecciona una actividad.')

    # ============================================================
    # BUSCAR ALUMNO — [REFACTOR] Usando helper global
    # ============================================================
    alumno = buscar_alumno_por_documento(rut_procesado)
    if not alumno:
        return _error_json(_mensaje_no_encontrado(metodo, rut_procesado), 404)

    # ============================================================
    # VALIDAR ACTIVIDAD
    # ============================================================
    try:
        actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
    except Actividad.DoesNotExist:
        request.session.pop('actividad_escaneo_id', None)
        return _error_json('La actividad no existe o ya no está activa.', 404)

    # ============================================================
    # HELPERS DE LOG
    # ============================================================
    def _log_duplicado():
        registrar_log(request, 'Escáner', 'Intento de asistencia duplicada',
                      f'{alumno.nombres} {alumno.apellidos} en {actividad.titulo}',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    def _log_sin_inscripcion():
        registrar_log(request, 'Escáner', 'Intento de asistencia sin inscripción',
                      f'{alumno.nombres} {alumno.apellidos} en "{actividad.titulo}"',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    # Con invitación: solo entran los de la lista
    if actividad.tipo == 'INVITACION' and not actividad.invitados.filter(rut=alumno.rut).exists():
        registrar_log(request, 'Escáner', 'Intento de ingreso sin invitación',
                      f'{alumno.nombres} {alumno.apellidos} en "{actividad.titulo}"',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
        return _error_json(f'{alumno.nombres} {alumno.apellidos} no está en la lista de invitados.', 403)

    # ============================================================
    # PRIMERA ETAPA: PEDIR CONFIRMACIÓN
    # ============================================================
    if not confirmar:
        if Asistencia.objects.filter(actividad=actividad, alumno=alumno).exists():
            _log_duplicado()
            return _error_json('La asistencia ya fue registrada anteriormente.', 409)

        if actividad.tipo == 'TALLER' and not Inscripcion.objects.filter(
            actividad=actividad, alumno=alumno, estado='CONFIRMADA'
        ).exists():
            _log_sin_inscripcion()
            return _error_json(
                f'{alumno.nombres} {alumno.apellidos} no está inscrito en este taller.',
                403
            )

        return JsonResponse({
            'success': True,
            'confirmar': True,
            'alumno': {
                'nombre': f'{alumno.nombres} {alumno.apellidos}',
                'rut': formatear_rut(alumno.rut),
                'carrera': alumno.carrera,
                'jornada': alumno.jornada,
            }
        })

    # ============================================================
    # SEGUNDA ETAPA: CONFIRMAR Y CREAR ASISTENCIA
    # ============================================================
    try:
        with transaction.atomic():
            actividad = Actividad.objects.select_for_update().get(
                pk=actividad_id, estado='ACTIVA'
            )

            if Asistencia.objects.filter(actividad=actividad, alumno=alumno).exists():
                _log_duplicado()
                return _error_json('La asistencia ya fue registrada anteriormente.', 409)

            if actividad.tipo == 'TALLER' and not Inscripcion.objects.filter(
                actividad=actividad, alumno=alumno, estado='CONFIRMADA'
            ).exists():
                _log_sin_inscripcion()
                return _error_json(
                    f'{alumno.nombres} {alumno.apellidos} no está inscrito en este taller.',
                    403
                )

            Asistencia.objects.create(
                actividad=actividad,
                alumno=alumno,
                metodo_ingreso=metodo,
                registrado_por=request.user
            )
            registrar_log(request, 'Escáner', 'Registro de asistencia',
                          f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo}',
                          'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    except Actividad.DoesNotExist:
        return _error_json('La actividad no existe o ya no está activa.', 404)
    except IntegrityError:
        return _error_json('La asistencia ya fue registrada por otro operador.', 409)
    except Exception:
        logger.exception('Error al registrar asistencia')
        return _error_json('Ocurrió un error al registrar la asistencia.', 500)

    return JsonResponse({
        'success': True,
        'confirmar': False,
        'message': f'Asistencia registrada para {alumno.nombres} {alumno.apellidos}.',
        'metodo': metodo,
        'alumno': {
            'nombre': f'{alumno.nombres} {alumno.apellidos}',
            'rut': formatear_rut(alumno.rut),
            'carrera': alumno.carrera,
            'jornada': alumno.jornada,
        },
        'contador': _contador_escaneo(request, actividad),
    })


@login_required
@role_required('Administrador', 'Creador de Evento', 'Encargado de Registrar')
@ratelimit(key='user', rate='120/1m', method='POST', block=False)
def escaneo(request):
    if request.method == 'POST':
        if 'cambiar_actividad' in request.POST:
            actividad_id = id_o_none(request.POST.get('actividad_id'))
            if not actividad_id:
                if _es_ajax(request):
                    return _error_json('Debes seleccionar una actividad.')
                messages.error(request, 'Debes seleccionar una actividad.')
                return redirect('escaneo')
            try:
                actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
                # Sin aviso emergente: taparía el campo y la pistola escribiría en ninguna parte.
                # La pantalla ya muestra la actividad y la hora de inicio del turno.
                if (request.session.get('actividad_escaneo_id') != actividad.id
                        or not request.session.get('turno_id')):
                    _terminar_turno(request)
                    _iniciar_turno(request, actividad)
                if _es_ajax(request):
                    return JsonResponse({'success': True, 'redirect_url': '/escaneo/'})
                return redirect('escaneo')
            except Actividad.DoesNotExist:
                if _es_ajax(request):
                    return _error_json('Actividad no válida o inactiva.', 404)
                messages.error(request, 'Actividad no válida o inactiva.')
                return redirect('escaneo')

        if 'finalizar_turno' in request.POST:
            resumen = _terminar_turno(request)
            if resumen:
                n, minutos = resumen['registradas'], resumen['minutos']
                messages.info(request, f'Turno finalizado en "{resumen["actividad"].titulo}": registraste {n} '
                                       f'asistencia{"s" if n != 1 else ""}'
                                       + (f' en {minutos} min.' if minutos is not None else '.'))
            else:
                messages.info(request, 'Turno finalizado.')
            return redirect('escaneo')

        if 'rut' in request.POST:
               if getattr(request, 'limited', False):
                   return _error_json(
                       'Demasiados escaneos seguidos. Espera unos segundos e intenta de nuevo.',
                       429,
                   )
               return _procesar_escaneo(request)

    act_id = request.session.get('actividad_escaneo_id')
    actividad = None
    if act_id:
        try:
            actividad = Actividad.objects.get(pk=act_id, estado='ACTIVA')
        except Actividad.DoesNotExist:
            request.session.pop('actividad_escaneo_id', None)
            request.session.pop('turno_inicio', None)
    if actividad and not request.session.get('turno_id'):
        # Sesiones anteriores a los turnos guardados: el turno empieza ahora
        _iniciar_turno(request, actividad)

    return render(request, 'gestion/escaneo.html', {
        'actividad_seleccionada': actividad,
        'contador': _contador_escaneo(request, actividad) if actividad else None,
        'actividades_disponibles': _actividades_para_escanear(),
        'ultimas_asistencias': (
            Asistencia.objects.filter(actividad=actividad)
            .select_related('alumno', 'registrado_por').order_by('-fecha_ingreso')[:10]
            if actividad else []
        ),
    })


def _actividades_para_escanear():
    """Actividades activas: primero las que están en curso, luego las próximas (la más cercana
    primero) y al final las que ya terminaron pero siguen activas."""
    ahora = timezone.now()
    actividades = list(Actividad.objects.filter(estado='ACTIVA'))
    for a in actividades:
        a.en_curso = a.fecha_inicio <= ahora <= a.fecha_fin
    def orden(a):
        if a.en_curso:
            return (0, a.fecha_inicio.timestamp())
        if a.fecha_inicio > ahora:
            return (1, a.fecha_inicio.timestamp())
        return (2, -a.fecha_fin.timestamp())
    return sorted(actividades, key=orden)


@login_required
@role_required('Administrador', 'Creador de Evento', 'Encargado de Registrar', json_response=True)
@require_GET
def escaneo_contador(request):
    """Contador en vivo del escáner (la pantalla lo consulta cada pocos segundos)."""
    act_id = request.session.get('actividad_escaneo_id')
    actividad = Actividad.objects.filter(pk=act_id, estado='ACTIVA').first() if act_id else None
    if actividad is None:
        return _error_json('No hay una actividad seleccionada.', 404)
    return JsonResponse({'success': True, **_contador_escaneo(request, actividad)})


# ============================================================
# AUDITORÍA
# ============================================================

def _filtrar_auditoria(request):
    qs = LogAuditoria.objects.all().order_by('-fecha_registro')
    for campo, param in [
        ('usuario_sistema__username__icontains', 'usuario'),
        ('accion__icontains', 'accion'),
        ('modulo__icontains', 'modulo'),
    ]:
        if request.GET.get(param):
            qs = qs.filter(**{campo: request.GET[param]})
    fecha = fecha_o_none(request.GET.get('fecha'))
    if fecha:
        qs = qs.filter(fecha_registro__date=fecha)
    return qs


@login_required
@role_required('Administrador')
def lista_auditoria(request):
    from .utils import paginar
    return render(request, 'gestion/auditoria_list.html', {
        'logs': paginar(request, _filtrar_auditoria(request)),
        'acciones_disponibles': LogAuditoria.objects.values_list('accion', flat=True)
            .distinct().order_by('accion'),
        'modulos_disponibles': LogAuditoria.objects.values_list('modulo', flat=True)
            .distinct().order_by('modulo'),
    })


@login_required
@role_required('Administrador', json_response=True)
def exportar_auditoria(request):
    datos = [[
        log.usuario_sistema.username if log.usuario_sistema else "Sistema/Anónimo",
        log.modulo or "N/A", log.objeto_tipo or "N/A", log.objeto_id or "N/A",
        log.accion, log.fecha_registro.strftime("%d/%m/%Y %H:%M"),
        log.ip_address or "N/A", log.detalle,
    ] for log in _filtrar_auditoria(request)]

    headers = ['Usuario', 'Módulo', 'Objeto', 'ID Objeto', 'Acción',
               'Fecha y Hora', 'IP', 'Detalle']
    return _exportar_excel(datos, headers, 'auditoria_filtrada', 'Auditoría Filtrada')


# ============================================================
# INSCRIPCIÓN PÚBLICA
# ============================================================

def _render_inscripcion(request, actividad, estado='con_cupos', error=None, exito=None):
    ctx = {'actividad': actividad, 'estado': estado}
    if error:
        ctx['error'] = error
    if exito:
        ctx['exito'] = exito
    return render(request, 'gestion/inscripcion_publica.html', ctx)


def inscripcion_taller(request, actividad_id):
    """
    Vista pública de inscripción a talleres.
    [REFACTOR] Ahora usa buscar_alumno_por_documento() para aceptar
    RUT con/sin guion, con/sin puntos, pasaportes, etc.
    """
    actividad = get_object_or_404(Actividad, pk=actividad_id, tipo='TALLER')
    ahora = timezone.now()

    if actividad.estado != 'ACTIVA' or actividad.fecha_fin <= ahora:
        return _render_inscripcion(request, actividad, 'finalizado')
    if (actividad.cupos_disponibles or 0) <= 0:
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

    # [REFACTOR] Búsqueda inteligente: acepta múltiples formatos
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
            if act_lock.estado != 'ACTIVA' or act_lock.fecha_fin <= timezone.now():
                return _render_inscripcion(request, act_lock, 'finalizado')
            if Inscripcion.objects.filter(actividad=act_lock, alumno=alumno).exists():
                return _render_inscripcion(request, act_lock, 'con_cupos',
                                           'Ya estás inscrito en este taller.')

            cupos = act_lock.cupos_disponibles or 0
            if cupos <= 0:
                return _render_inscripcion(request, act_lock, 'sin_cupos')

            act_lock.cupos_disponibles = cupos - 1
            act_lock.save(update_fields=['cupos_disponibles'])

            Inscripcion.objects.create(actividad=act_lock, alumno=alumno, estado='CONFIRMADA')
            cupos_restantes = act_lock.cupos_disponibles
    except IntegrityError:
        return _render_inscripcion(request, actividad, 'con_cupos', 'Ya estás inscrito en este taller.')
    try:
        registrar_log(request, 'Inscripciones', 'Inscripción a taller',
                      f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo} - Política de Privacidad v2026-1 aceptada',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
    except Exception:
        logger.exception(
            'No se pudo registrar la auditoría de la inscripción (alumno %s, actividad %s)',
            alumno.id, actividad_id,
        )

    actividad.cupos_disponibles = cupos_restantes
    return _render_inscripcion(request, actividad, 'con_cupos', exito=
                               f'¡Inscripción exitosa! Cupos disponibles: {cupos_restantes}')

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


def politica_privacidad(request):
    """Página pública con la Política de Privacidad."""
    return render(request, 'gestion/politica_privacidad.html')
