# ==================== IMPORTS ESTÁNDAR DE PYTHON ====================

import csv
import json
import logging
import re
from collections import defaultdict
from datetime import timedelta


# ==================== IMPORTS DE TERCEROS ====================

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


# ==================== IMPORTS DE DJANGO ====================

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)


# ==================== IMPORTS LOCALES ====================

from django_ratelimit.decorators import ratelimit

from .decorators import role_required
from .forms import ActividadForm
from .models import (
    Actividad,
    Alumno,
    Asistencia,
    Carrera,
    Inscripcion,
    Jornada,
    LogAuditoria,
    NotificacionCorreo,
    Rol,
    UsuarioSistema,
)


logger = logging.getLogger(__name__)


# ==================== FUNCIONES AUXILIARES ====================

def normalizar_rut(rut):
    if not rut:
        return ""
    return re.sub(r'[^0-9kK]', '', str(rut)).upper()


def extraer_rut_de_carnet(texto):
    if not texto:
        return ""
    texto_limpio = re.sub(r'[^0-9kK]', '', str(texto))
    if len(texto_limpio) >= 9:
        rut_candidato = texto_limpio[:9]
        if rut_candidato[:8].isdigit() and (rut_candidato[-1].isdigit() or rut_candidato[-1] == 'K'):
            return rut_candidato
    return texto_limpio


def tiene_rol(user, roles_permitidos):
    """Comprueba si el usuario autenticado tiene uno de los roles indicados."""
    if not user.is_authenticated:
        return False

    try:
        perfil = user.usuariosistema
        if not perfil.activo or perfil.rol is None:
            return False
        return perfil.rol.nombre in roles_permitidos
    except UsuarioSistema.DoesNotExist:
        return False


def puede_gestionar_actividad(user, actividad):
    """
    Determina si el usuario puede editar/eliminar/gestionar una actividad específica.
    - Administrador: puede gestionar cualquier actividad.
    - Creador de Evento: solo puede gestionar las que él mismo creó.
    """
    if tiene_rol(user, ['Administrador']):
        return True
    if tiene_rol(user, ['Creador de Evento']):
        return actividad.creado_por_id == user.id
    return False


def registrar_log(request, modulo, accion, detalle, objeto_tipo=None, objeto_id=None,
                  objeto_nombre=None, cambios_json=None):
    """Registra una acción en el log de auditoría."""
    LogAuditoria.objects.create(
        usuario_sistema=request.user if request.user.is_authenticated else None,
        modulo=modulo,
        accion=accion,
        detalle=detalle,
        objeto_tipo=objeto_tipo,
        objeto_id=objeto_id,
        objeto_nombre=objeto_nombre,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT'),
        cambios_json=cambios_json
    )


# ==================== CAMBIO DE CONTRASEÑA ====================

@login_required
def cambiar_contrasena(request):
    try:
        perfil = request.user.usuariosistema
    except UsuarioSistema.DoesNotExist:
        messages.error(
            request,
            'Tu cuenta no tiene un perfil válido en el sistema.'
        )
        return redirect('login')

    if not perfil.activo:
        messages.error(request, 'Tu cuenta está desactivada.')
        return redirect('login')

    if perfil.rol is None:
        messages.error(request, 'Tu cuenta no tiene un rol asignado.')
        return redirect('login')

    if request.method == 'POST':
        contrasena_actual = request.POST.get('contrasena_actual', '')
        nueva_contrasena = request.POST.get('nueva_contrasena', '')
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '')

        if not request.user.check_password(contrasena_actual):
            messages.error(request, 'La contraseña actual es incorrecta.')
            return render(request, 'gestion/cambiar_contrasena.html')

        if not nueva_contrasena:
            messages.error(request, 'Debes ingresar una nueva contraseña.')
            return render(request, 'gestion/cambiar_contrasena.html')

        if request.user.check_password(nueva_contrasena):
            messages.error(
                request,
                'La nueva contraseña debe ser diferente de la actual.'
            )
            return render(request, 'gestion/cambiar_contrasena.html')

        if nueva_contrasena != confirmar_contrasena:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'gestion/cambiar_contrasena.html')

        try:
            validate_password(nueva_contrasena, user=request.user)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
            return render(request, 'gestion/cambiar_contrasena.html')

        request.user.set_password(nueva_contrasena)
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)

        perfil.must_change_password = False
        perfil.save(update_fields=['must_change_password'])

        registrar_log(
            request,
            'Seguridad',
            'Cambio de contraseña',
            f'Usuario "{request.user.username}" cambió su contraseña',
            'Usuario',
            request.user.id,
            request.user.username,
        )

        messages.success(request, 'Contraseña actualizada correctamente.')

        if perfil.rol.nombre == 'Encargado de Registrar':
            return redirect('escaneo')

        return redirect('dashboard')

    return render(request, 'gestion/cambiar_contrasena.html')


# ==================== AUTENTICACIÓN ====================

@ratelimit(key='ip', rate='5/15m', method='POST', block=True)
def login_view(request):
    if request.method != 'POST':
        return render(request, 'gestion/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    if not username or not password:
        messages.error(request, 'Debes ingresar usuario y contraseña.')
        return render(request, 'gestion/login.html')

    user = authenticate(request, username=username, password=password)

    if user is None:
        messages.error(request, 'Usuario o contraseña incorrectos.')
        return render(request, 'gestion/login.html')

    if not user.is_active:
        messages.error(request, 'Usuario o contraseña incorrectos.')
        return render(request, 'gestion/login.html')

    try:
        perfil = user.usuariosistema
    except UsuarioSistema.DoesNotExist:
        messages.error(
            request,
            'La cuenta no tiene un perfil válido en el sistema.'
        )
        return render(request, 'gestion/login.html')

    if not perfil.activo:
        messages.error(request, 'Usuario o contraseña incorrectos.')
        return render(request, 'gestion/login.html')

    if perfil.rol is None:
        messages.error(request, 'La cuenta no tiene un rol asignado.')
        return render(request, 'gestion/login.html')

    rol = perfil.rol.nombre

    roles_validos = {
        'Administrador',
        'Creador de Evento',
        'Encargado de Registrar',
    }

    if rol not in roles_validos:
        messages.error(request, 'La cuenta tiene un rol no válido.')
        return render(request, 'gestion/login.html')

    login(request, user)

    if perfil.must_change_password:
        return redirect('cambiar_contrasena')

    if rol == 'Encargado de Registrar':
        return redirect('escaneo')

    return redirect('dashboard')


@login_required
def logout_view(request):
    if request.method != 'POST':
        return redirect('dashboard')

    logout(request)
    return redirect('login')


# ==================== RECUPERACIÓN DE CONTRASEÑA ====================

@ratelimit(key='ip', rate='5/15m', method='POST', block=True)
def solicitar_recuperacion(request):
    """
    Solicita un enlace de recuperación de contraseña.

    El mensaje final es siempre genérico para no revelar
    si un usuario o correo existe en el sistema.
    """
    if request.method != 'POST':
        return render(request, 'gestion/recuperar_contrasena.html')

    identificador = request.POST.get('identificador', '').strip()

    if not identificador:
        messages.error(request, 'Ingresa tu usuario o correo electrónico.')
        return render(request, 'gestion/recuperar_contrasena.html')

    usuario = User.objects.filter(username=identificador).first()

    if usuario is None:
        usuario = User.objects.filter(email__iexact=identificador).first()

    tiene_correo = bool(
        usuario is not None
        and usuario.email
        and usuario.email.strip()
    )

    if usuario is not None and usuario.is_active and tiene_correo:
        try:
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = PasswordResetTokenGenerator().make_token(usuario)

            enlace = (
                f'{settings.SITE_URL.rstrip("/")}'
                f'/restablecer-contrasena/{uid}/{token}/'
            )

            html_contenido = render_to_string(
                'gestion/email_recuperacion.html',
                {
                    'user': usuario,
                    'enlace': enlace,
                }
            )

            mensaje_plano = (
                'Para restablecer tu contraseña, visita el siguiente '
                'enlace:\n\n'
                f'{enlace}\n\n'
                'Si no solicitaste este cambio, puedes ignorar este mensaje.'
            )

            cantidad_enviada = send_mail(
                subject='Recuperación de contraseña - Punto Participa',
                message=mensaje_plano,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[usuario.email.strip()],
                html_message=html_contenido,
                fail_silently=False,
            )

            if cantidad_enviada != 1:
                raise RuntimeError(
                    'El servidor de correo no aceptó el mensaje.'
                )

            registrar_log(
                request,
                'Seguridad',
                'Solicitud de recuperación de contraseña',
                (
                    'Se envió un enlace de recuperación para el '
                    f'usuario "{usuario.username}".'
                ),
                'Usuario',
                usuario.id,
                usuario.username
            )

        except Exception:
            logger.exception(
                'Error enviando correo de recuperación '
                'para el usuario ID %s',
                usuario.id
            )

    messages.success(
        request,
        (
            'Si el usuario existe y tiene un correo registrado, '
            'recibirá instrucciones para restablecer su contraseña.'
        )
    )

    return redirect('login')


def restablecer_contrasena(request, uidb64, token):
    """
    Valida un enlace de recuperación y permite establecer
    una nueva contraseña.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        usuario = User.objects.get(pk=uid, is_active=True)

    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeDecodeError,
        User.DoesNotExist
    ):
        usuario = None

    token_generator = PasswordResetTokenGenerator()

    token_valido = (
        usuario is not None
        and token_generator.check_token(usuario, token)
    )

    if not token_valido:
        return render(
            request,
            'gestion/restablecer_contrasena.html',
            {'token_valido': False}
        )

    if request.method == 'POST':
        nueva_contrasena = request.POST.get('nueva_contrasena', '')
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '')

        contexto = {'token_valido': True}

        if not nueva_contrasena:
            messages.error(request, 'Debes ingresar una nueva contraseña.')
            return render(
                request,
                'gestion/restablecer_contrasena.html',
                contexto
            )

        if nueva_contrasena != confirmar_contrasena:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(
                request,
                'gestion/restablecer_contrasena.html',
                contexto
            )

        if usuario.check_password(nueva_contrasena):
            messages.error(
                request,
                'La nueva contraseña debe ser diferente de la anterior.'
            )
            return render(
                request,
                'gestion/restablecer_contrasena.html',
                contexto
            )

        try:
            validate_password(nueva_contrasena, user=usuario)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
            return render(
                request,
                'gestion/restablecer_contrasena.html',
                contexto
            )

        usuario.set_password(nueva_contrasena)
        usuario.save(update_fields=['password'])

        try:
            perfil = usuario.usuariosistema
            perfil.must_change_password = False
            perfil.save(update_fields=['must_change_password'])
        except UsuarioSistema.DoesNotExist:
            pass

        registrar_log(
            request,
            'Seguridad',
            'Restablecimiento de contraseña',
            (
                f'Usuario "{usuario.username}" restableció '
                'su contraseña mediante enlace de recuperación.'
            ),
            'Usuario',
            usuario.id,
            usuario.username
        )

        messages.success(
            request,
            (
                'Tu contraseña fue restablecida correctamente. '
                'Ya puedes iniciar sesión.'
            )
        )

        return redirect('login')

    return render(
        request,
        'gestion/restablecer_contrasena.html',
        {'token_valido': True}
    )


# ==================== DASHBOARD ====================

@login_required
@role_required('Administrador', 'Creador de Evento', redirect_name='escaneo')
def dashboard(request):
    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    actividades_qs = Actividad.objects.all()
    asistencias_qs = Asistencia.objects.all()
    inscripciones_qs = Inscripcion.objects.all()
    notificaciones_qs = NotificacionCorreo.objects.all()

    if es_creador and not es_admin:
        actividades_qs = actividades_qs.filter(creado_por=request.user)
        asistencias_qs = asistencias_qs.filter(actividad__creado_por=request.user)
        inscripciones_qs = inscripciones_qs.filter(actividad__creado_por=request.user)
        notificaciones_qs = notificaciones_qs.filter(actividad__creado_por=request.user)

    ahora = timezone.now()
    hoy = ahora.date()

    rango = request.GET.get('rango', '')
    tipo_filtro = request.GET.get('tipo', '')
    carrera_filtro = request.GET.get('carrera', '')
    jornada_filtro = request.GET.get('jornada', '')

    if rango == 'hoy':
        actividades_qs = actividades_qs.filter(fecha_inicio__date=hoy)
        asistencias_qs = asistencias_qs.filter(fecha_ingreso__date=hoy)
    elif rango == '7dias':
        desde = ahora - timedelta(days=7)
        actividades_qs = actividades_qs.filter(fecha_inicio__gte=desde)
        asistencias_qs = asistencias_qs.filter(fecha_ingreso__gte=desde)
    elif rango == 'mes':
        actividades_qs = actividades_qs.filter(
            fecha_inicio__year=ahora.year,
            fecha_inicio__month=ahora.month
        )
        asistencias_qs = asistencias_qs.filter(
            fecha_ingreso__year=ahora.year,
            fecha_ingreso__month=ahora.month
        )

    if tipo_filtro in ['MASIVA', 'TALLER']:
        actividades_qs = actividades_qs.filter(tipo=tipo_filtro)
        asistencias_qs = asistencias_qs.filter(actividad__tipo=tipo_filtro)

    if carrera_filtro:
        actividades_qs = actividades_qs.filter(carreras__nombre=carrera_filtro)
        asistencias_qs = asistencias_qs.filter(alumno__carrera=carrera_filtro)

    if jornada_filtro:
        actividades_qs = actividades_qs.filter(jornadas__nombre=jornada_filtro)
        asistencias_qs = asistencias_qs.filter(alumno__jornada=jornada_filtro)

    actividades_qs = actividades_qs.distinct()
    asistencias_qs = asistencias_qs.distinct()

    actividades_activas = actividades_qs.filter(estado='ACTIVA').count()

    talleres_proximos = actividades_qs.filter(
        tipo='TALLER',
        estado='ACTIVA',
        fecha_inicio__gte=ahora,
        cupos_disponibles__gt=0
    ).count()

    total_inscritos = inscripciones_qs.filter(actividad__in=actividades_qs).count()

    asistencias_hoy = asistencias_qs.filter(fecha_ingreso__date=hoy).count()

    invitaciones_enviadas = notificaciones_qs.filter(
        actividad__in=actividades_qs,
        estado_envio='EXITO'
    ).count()

    actividades_finalizadas = actividades_qs.filter(estado='FINALIZADA').count()

    total_asistencias_filtradas = asistencias_qs.count()
    promedio_asistentes = (
        round(total_asistencias_filtradas / actividades_qs.count(), 1)
        if actividades_qs.count() > 0 else 0
    )

    cupos_disponibles_totales = (
        actividades_qs.filter(tipo='TALLER', estado='ACTIVA')
        .aggregate(total=Sum('cupos_disponibles'))
        .get('total') or 0
    )

    total_inscritos_para_tasa = inscripciones_qs.filter(actividad__in=actividades_qs).count()
    tasa_asistencia = (
        round((total_asistencias_filtradas / total_inscritos_para_tasa) * 100, 1)
        if total_inscritos_para_tasa > 0 else 0
    )

        # ============================================================
    # DESGLOSE POR TIPO (MASIVAS / TALLERES)
    # ============================================================
    ids_talleres = list(
        actividades_qs.filter(tipo='TALLER').values_list('id', flat=True)
    )
    ids_masivas = list(
        actividades_qs.filter(tipo='MASIVA').values_list('id', flat=True)
    )

    # ---- TALLERES ----
    talleres_count = len(ids_talleres)

    inscripciones_talleres_qs = Inscripcion.objects.filter(
        actividad_id__in=ids_talleres
    )

    if carrera_filtro:
        inscripciones_talleres_qs = inscripciones_talleres_qs.filter(
            alumno__carrera=carrera_filtro
        )
    if jornada_filtro:
        inscripciones_talleres_qs = inscripciones_talleres_qs.filter(
            alumno__jornada=jornada_filtro
        )

    talleres_inscritos = inscripciones_talleres_qs.count()

    talleres_asistentes = asistencias_qs.filter(
        actividad_id__in=ids_talleres
    ).count()

    if talleres_inscritos > 0:
        tasa_talleres = round(
            (talleres_asistentes / talleres_inscritos) * 100, 1
        )
    else:
        tasa_talleres = None

    # ---- MASIVAS ----
    masivas_count = len(ids_masivas)

    masivas_asistentes = asistencias_qs.filter(
        actividad_id__in=ids_masivas
    ).count()

    cupos_masivas = (
        actividades_qs
        .filter(tipo='MASIVA', cupos_totales__isnull=False)
        .aggregate(total=Sum('cupos_totales'))
        .get('total') or 0
    )

    if cupos_masivas > 0:
        tasa_masivas = round(
            (masivas_asistentes / cupos_masivas) * 100, 1
        )
    else:
        tasa_masivas = None

    top_actividades = (
        actividades_qs
        .annotate(total_asist=Count('asistencias'))
        .order_by('-total_asist')[:5]
    )
    labels_barras = [
        act.titulo[:15] + '...' if len(act.titulo) > 15 else act.titulo
        for act in top_actividades
    ]
    data_barras = [act.total_asist for act in top_actividades]

    asistencias_por_carrera = (
        asistencias_qs
        .values('alumno__carrera')
        .annotate(total=Count('id'))
        .order_by('-total')[:6]
    )
    labels_pastel = [item['alumno__carrera'] or 'Sin carrera' for item in asistencias_por_carrera]
    data_pastel = [item['total'] for item in asistencias_por_carrera]

    meses_labels = []
    data_programadas = []
    data_en_curso = []
    data_finalizadas = []

    for i in range(5, -1, -1):
        fecha_ref = ahora - timedelta(days=30 * i)
        meses_labels.append(fecha_ref.strftime('%b').capitalize())

        programadas = actividades_qs.filter(
            fecha_inicio__year=fecha_ref.year,
            fecha_inicio__month=fecha_ref.month
        ).count()
        finalizadas = actividades_qs.filter(
            fecha_fin__year=fecha_ref.year,
            fecha_fin__month=fecha_ref.month,
            estado='FINALIZADA'
        ).count()
        en_curso = actividades_qs.filter(
            fecha_inicio__year=fecha_ref.year,
            fecha_inicio__month=fecha_ref.month,
            estado='ACTIVA'
        ).count()

        data_programadas.append(programadas)
        data_en_curso.append(en_curso)
        data_finalizadas.append(finalizadas)

    actividades_comp = (
        actividades_qs
        .annotate(
            total_inscritos_calc=Count('inscripciones', distinct=True),
            total_asistentes_calc=Count('asistencias', distinct=True),
        )
        .order_by('-fecha_inicio')[:6]
    )
    labels_comp = [
        act.titulo[:12] + '...' if len(act.titulo) > 12 else act.titulo
        for act in actividades_comp
    ]
    data_comp_inscritos = [act.total_inscritos_calc for act in actividades_comp]
    data_comp_asistentes = [act.total_asistentes_calc for act in actividades_comp]

    actividades_proximas = (
        actividades_qs
        .filter(estado='ACTIVA', fecha_inicio__gte=ahora)
        .order_by('fecha_inicio')[:4]
    )

    alertas = {
        'talleres_sin_cupos': actividades_qs.filter(
            tipo='TALLER', estado='ACTIVA', cupos_disponibles=0
        ).count(),
        'comienzan_hoy': actividades_qs.filter(
            estado='ACTIVA', fecha_inicio__date=hoy
        ).count(),
        'sin_inscritos': actividades_qs.filter(
            estado='ACTIVA', inscripciones__isnull=True
        ).count(),
        'correos_fallidos': notificaciones_qs.filter(
            actividad__in=actividades_qs, estado_envio='FALLO'
        ).count(),
    }

    ultimas_asistencias = (
        asistencias_qs
        .select_related('alumno', 'actividad')
        .order_by('-fecha_ingreso')[:5]
    )

    ultimas_actividades_creadas = actividades_qs.order_by('-fecha_creacion')[:5]

    ultimos_logs = LogAuditoria.objects.all().order_by('-fecha_registro')[:5]
    if es_creador and not es_admin:
        ultimos_logs = ultimos_logs.filter(usuario_sistema=request.user)

    carreras_cache = {c.nombre.lower(): c for c in Carrera.objects.all()}
    asistencias_escuela = defaultdict(int)

    for a in asistencias_qs.select_related('alumno'):
        carrera_obj = carreras_cache.get(a.alumno.carrera.lower())
        escuela = carrera_obj.escuela if carrera_obj and carrera_obj.escuela else 'Sin asignar'
        asistencias_escuela[escuela] += 1

    labels_escuela = list(asistencias_escuela.keys())[:6]
    data_escuela = [asistencias_escuela[k] for k in labels_escuela]

    ultimas_actividades_tabla = (
        actividades_qs
        .annotate(
            total_inscritos=Count('inscripciones', distinct=True),
            total_asistentes=Count('asistencias', distinct=True),
        )
        .order_by('-fecha_inicio')[:8]
    )

    carreras_opciones = Carrera.objects.all().order_by('nombre')
    jornadas_opciones = Jornada.objects.all().order_by('nombre')

    context = {
        'nombre_usuario': request.user.first_name or request.user.username,
        'actividades_activas': actividades_activas,
        'talleres_proximos': talleres_proximos,
        'total_inscritos': total_inscritos,
        'asistencias_hoy': asistencias_hoy,
        'invitaciones_enviadas': invitaciones_enviadas,
        'actividades_finalizadas': actividades_finalizadas,
        'promedio_asistentes': promedio_asistentes,
        'cupos_disponibles_totales': cupos_disponibles_totales,
        'tasa_asistencia': tasa_asistencia,
        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
        'labels_linea': meses_labels,
        'data_programadas': data_programadas,
        'data_en_curso': data_en_curso,
        'data_finalizadas': data_finalizadas,
        'labels_comp': labels_comp,
        'data_comp_inscritos': data_comp_inscritos,
        'data_comp_asistentes': data_comp_asistentes,
        'labels_escuela': labels_escuela,
        'data_escuela': data_escuela,
        'actividades_proximas': actividades_proximas,
        'alertas': alertas,
        'ultimas_asistencias': ultimas_asistencias,
        'ultimas_actividades_creadas': ultimas_actividades_creadas,
        'ultimos_logs': ultimos_logs,
        'actividades': ultimas_actividades_tabla,
        'carreras_opciones': carreras_opciones,
        'jornadas_opciones': jornadas_opciones,
        'rango_actual': rango,
        'tipo_actual': tipo_filtro,
        'carrera_actual': carrera_filtro,
        'jornada_actual': jornada_filtro,
                # Desglose por tipo
        'masivas_count': masivas_count,
        'masivas_asistentes': masivas_asistentes,
        'cupos_masivas': cupos_masivas,
        'tasa_masivas': tasa_masivas,
        'talleres_count': talleres_count,
        'talleres_inscritos': talleres_inscritos,
        'talleres_asistentes': talleres_asistentes,
        'tasa_talleres': tasa_talleres,
    }
    return render(request, 'gestion/dashboard.html', context)


# ==================== REPORTES ====================

@login_required
@role_required('Administrador', 'Creador de Evento')
def reportes(request):
    actividad_seleccionada = request.GET.get('actividad', '')
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')

    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    actividades_qs = Actividad.objects.all().order_by('-fecha_inicio')

    if es_creador and not es_admin:
        actividades_qs = actividades_qs.filter(creado_por=request.user)

    if actividad_seleccionada:
        actividades_qs = actividades_qs.filter(pk=actividad_seleccionada)
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    ids_actividades_filtradas = list(actividades_qs.values_list('id', flat=True))

    asistencias_qs = Asistencia.objects.filter(
        actividad_id__in=ids_actividades_filtradas
    ).select_related('alumno', 'registrado_por', 'actividad')

    if carrera:
        asistencias_qs = asistencias_qs.filter(alumno__carrera=carrera)
    if jornada:
        asistencias_qs = asistencias_qs.filter(alumno__jornada=jornada)

    alumnos_filtrados_ids = asistencias_qs.values('alumno')

    actividades_qs = actividades_qs.annotate(
        total_asistentes_calc=Count(
            'asistencias',
            filter=Q(asistencias__alumno__in=alumnos_filtrados_ids),
            distinct=True,
        ),
        total_inscritos_calc=Count(
            'inscripciones',
            filter=Q(inscripciones__alumno__in=alumnos_filtrados_ids),
            distinct=True,
        ),
    ).prefetch_related('carreras', 'jornadas')

    total_inscritos_filtrado = (
        Inscripcion.objects
        .filter(actividad_id__in=ids_actividades_filtradas)
        .filter(alumno__in=alumnos_filtrados_ids)
        .count()
    )
    total_asistentes_filtrado = asistencias_qs.count()

    # ============================================================
    # DESGLOSE POR TIPO (MASIVAS / TALLERES)
    # ============================================================
    ids_talleres = list(
        actividades_qs.filter(tipo='TALLER').values_list('id', flat=True)
    )
    ids_masivas = list(
        actividades_qs.filter(tipo='MASIVA').values_list('id', flat=True)
    )

    # ---- TALLERES ----
    talleres_count = len(ids_talleres)

    inscripciones_talleres_qs = Inscripcion.objects.filter(
        actividad_id__in=ids_talleres
    )

    if carrera:
        inscripciones_talleres_qs = inscripciones_talleres_qs.filter(
            alumno__carrera=carrera
        )
    if jornada:
        inscripciones_talleres_qs = inscripciones_talleres_qs.filter(
            alumno__jornada=jornada
        )

    talleres_inscritos = inscripciones_talleres_qs.count()

    talleres_asistentes = asistencias_qs.filter(
        actividad_id__in=ids_talleres
    ).count()

    if talleres_inscritos > 0:
        tasa_talleres = round(
            (talleres_asistentes / talleres_inscritos) * 100, 1
        )
    else:
        tasa_talleres = None

    # ---- MASIVAS ----
    masivas_count = len(ids_masivas)

    masivas_asistentes = asistencias_qs.filter(
        actividad_id__in=ids_masivas
    ).count()

    cupos_masivas = (
        actividades_qs
        .filter(tipo='MASIVA', cupos_totales__isnull=False)
        .aggregate(total=Sum('cupos_totales'))
        .get('total') or 0
    )

    if cupos_masivas > 0:
        tasa_masivas = round(
            (masivas_asistentes / cupos_masivas) * 100, 1
        )
    else:
        tasa_masivas = None

    # ============================================================
    # GRÁFICOS Y TABLAS
    # ============================================================
    labels_barras = [act.titulo for act in actividades_qs]
    data_barras = [act.total_asistentes_calc for act in actividades_qs]

    asistencias_por_carrera = (
        asistencias_qs
        .values('alumno__carrera')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    labels_pastel = [item['alumno__carrera'] or 'Sin carrera' for item in asistencias_por_carrera]
    data_pastel = [item['total'] for item in asistencias_por_carrera]

    asistencias_por_jornada = (
        asistencias_qs
        .values('alumno__jornada')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    labels_jornada = [item['alumno__jornada'] or 'Sin jornada' for item in asistencias_por_jornada]
    data_jornada = [item['total'] for item in asistencias_por_jornada]

    registros_por_actividad = {}
    registros_qs = (
        asistencias_qs
        .values('actividad_id', 'registrado_por__username')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    for item in registros_qs:
        act_id = item['actividad_id']
        nombre = item['registrado_por__username'] or 'Anónimo'
        total = item['total']
        registros_por_actividad.setdefault(act_id, []).append(f"{nombre} ({total})")

    for act in actividades_qs:
        act.total_asistentes = act.total_asistentes_calc
        act.total_inscritos = act.total_inscritos_calc
        act.creador = act.creado_por.username if act.creado_por else 'N/A'
        act.registrado_por_detalle = ", ".join(registros_por_actividad.get(act.id, [])) or "Sin registros"

    detalle_data = []
    detalle_escuelas = defaultdict(int)
    detalle_carreras = defaultdict(int)

    carreras_cache = {c.nombre.lower(): c for c in Carrera.objects.all()}

    agrupado_por_actividad = defaultdict(
        lambda: defaultdict(lambda: {'total': 0, 'registros': defaultdict(int)})
    )

    for a in asistencias_qs:
        alumno = a.alumno
        carrera_obj = carreras_cache.get(alumno.carrera.lower())
        escuela = carrera_obj.escuela if carrera_obj and carrera_obj.escuela else 'Sin asignar'

        clave = (escuela, alumno.carrera, alumno.jornada)
        agrupado_por_actividad[a.actividad_id][clave]['total'] += 1

        registrado_por = a.registrado_por.username if a.registrado_por else 'Anónimo'
        agrupado_por_actividad[a.actividad_id][clave]['registros'][registrado_por] += 1

    for act in actividades_qs:
        if act.id not in agrupado_por_actividad:
            continue

        for (escuela, carrera_nombre, jornada_nombre), vals in agrupado_por_actividad[act.id].items():
            detalle_data.append({
                'actividad': act.titulo,
                'tipo': act.get_tipo_display(),
                'fecha': act.fecha_inicio.strftime("%d/%m/%Y"),
                'escuela': escuela,
                'carrera': carrera_nombre,
                'jornada': jornada_nombre,
                'asistentes': vals['total'],
                'registrado_por': ", ".join([f"{u} ({c})" for u, c in vals['registros'].items()])
            })
            detalle_escuelas[escuela] += vals['total']
            detalle_carreras[carrera_nombre] += vals['total']

    labels_barras_detalle = list(detalle_escuelas.keys())
    data_barras_detalle = list(detalle_escuelas.values())

    labels_pastel_detalle = list(detalle_carreras.keys())
    data_pastel_detalle = list(detalle_carreras.values())

    labels_jornada_detalle = labels_jornada
    data_jornada_detalle = data_jornada

    if es_creador and not es_admin:
        actividades_opciones = Actividad.objects.filter(creado_por=request.user).order_by('-fecha_inicio')
    else:
        actividades_opciones = Actividad.objects.all().order_by('-fecha_inicio')

    # ============================================================
    # PAGINACIÓN
    # ============================================================
    from .utils import paginar

    actividades_page = paginar(request, actividades_qs, param='page_act')
    detalle_page = paginar(request, detalle_data, param='page_det')

    context = {
        'actividades': actividades_page,
        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
        'labels_jornada': labels_jornada,
        'data_jornada': data_jornada,
        'detalle_data': detalle_page,
        'labels_barras_detalle': labels_barras_detalle,
        'data_barras_detalle': data_barras_detalle,
        'labels_pastel_detalle': labels_pastel_detalle,
        'data_pastel_detalle': data_pastel_detalle,
        'labels_jornada_detalle': labels_jornada_detalle,
        'data_jornada_detalle': data_jornada_detalle,
        'actividades_opciones': actividades_opciones,
        'carreras_opciones': Carrera.objects.all(),
        'jornadas_opciones': Jornada.objects.all(),
        'actividad_seleccionada': actividad_seleccionada,
        'total_inscritos_filtrado': total_inscritos_filtrado,
        'total_asistentes_filtrado': total_asistentes_filtrado,
        # Desglose por tipo
        'masivas_count': masivas_count,
        'masivas_asistentes': masivas_asistentes,
        'cupos_masivas': cupos_masivas,
        'tasa_masivas': tasa_masivas,
        'talleres_count': talleres_count,
        'talleres_inscritos': talleres_inscritos,
        'talleres_asistentes': talleres_asistentes,
        'tasa_talleres': tasa_talleres,
    }
    return render(request, 'gestion/reportes.html', context)

@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def exportar_reportes(request, formato):
    actividad_id = request.GET.get('actividad', '')
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')

    actividades_qs = Actividad.objects.all().order_by('-fecha_inicio')

    if tiene_rol(request.user, ['Creador de Evento']) and not tiene_rol(request.user, ['Administrador']):
        actividades_qs = actividades_qs.filter(creado_por=request.user)

    if actividad_id:
        actividades_qs = actividades_qs.filter(pk=actividad_id)
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    ids_actividades_filtradas = list(actividades_qs.values_list('id', flat=True))

    asistencias_qs = Asistencia.objects.filter(
        actividad_id__in=ids_actividades_filtradas
    )

    if carrera:
        asistencias_qs = asistencias_qs.filter(alumno__carrera=carrera)
    if jornada:
        asistencias_qs = asistencias_qs.filter(alumno__jornada=jornada)

    alumnos_filtrados_ids = asistencias_qs.values('alumno')

    datos = []

    for act in actividades_qs:
        carreras = ", ".join([c.nombre for c in act.carreras.all()])
        jornadas = ", ".join([j.nombre for j in act.jornadas.all()])
        creador = act.creado_por.username if act.creado_por else 'N/A'

        total_inscritos = (
            Inscripcion.objects
            .filter(actividad=act)
            .filter(alumno__in=alumnos_filtrados_ids)
            .count()
        )
        total_asistentes = asistencias_qs.filter(actividad=act).count()

        asistencias_act = asistencias_qs.filter(actividad=act)
        registros_por_usuario = (
            asistencias_act
            .values('registrado_por__username')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

        if registros_por_usuario:
            detalle_registros = ", ".join([
                f"{item['registrado_por__username'] or 'Anónimo'} ({item['total']})"
                for item in registros_por_usuario
            ])
        else:
            detalle_registros = "Sin registros"

        datos.append([
            act.titulo,
            act.get_tipo_display(),
            creador,
            detalle_registros,
            act.fecha_inicio.strftime("%d/%m/%Y"),
            carreras,
            jornadas,
            total_inscritos,
            total_asistentes
        ])

    if formato == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="reporte_actividades.csv"'
        writer = csv.writer(response)
        writer.writerow(['Actividad', 'Tipo', 'Creador', 'Registrado por (cantidad)', 'Fecha',
                         'Carrera', 'Jornada', 'Inscritos', 'Asistentes'])
        for fila in datos:
            writer.writerow(fila)
        return response

    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte de Actividades"
    headers = ['Actividad', 'Tipo', 'Creador', 'Registrado por (cantidad)', 'Fecha',
               'Carrera', 'Jornada', 'Inscritos', 'Asistentes']
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for row_idx, fila in enumerate(datos, start=2):
        for col_idx, valor in enumerate(fila, start=1):
            ws.cell(row=row_idx, column=col_idx, value=valor)
    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = (max_length + 2)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_actividades.xlsx"'
    wb.save(response)
    return response

# ==================== USUARIOS ====================

@login_required
@role_required('Administrador')
def usuarios(request):
    usuarios_qs = UsuarioSistema.objects.all().order_by('-id')

    from .utils import paginar
    page_obj = paginar(request, usuarios_qs)
    logs_recientes = LogAuditoria.objects.all().order_by('-fecha_registro')[:10]
    roles = Rol.objects.all()

    context = {
        'usuarios': page_obj,
        'logs': logs_recientes,
        'roles': roles,
    }

    return render(request, 'gestion/usuarios.html', context)


@login_required
@role_required('Administrador', json_response=True)
def guardar_usuario(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})

    try:
        usuario_sistema_id = request.POST.get('user_id')
        username = request.POST.get('username', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        email = request.POST.get('email', '').strip()
        rol_id = request.POST.get('rol')
        estado = request.POST.get('estado') == 'on'
        rut = request.POST.get('rut', '').strip()

        usuario_sistema = None
        rol_anterior = None
        estado_anterior = None

        if usuario_sistema_id:
            usuario_sistema = UsuarioSistema.objects.get(pk=usuario_sistema_id)
            user = usuario_sistema.user

            if usuario_sistema.user == request.user and not estado:
                return JsonResponse({
                    'success': False,
                    'message': 'No puedes bloquear tu propia cuenta.'
                })

        if not username or not nombre or not email or not rol_id:
            return JsonResponse({'success': False, 'message': 'Faltan campos obligatorios'})

        if usuario_sistema_id:
            if user.username != username and User.objects.filter(username=username).exclude(pk=user.pk).exists():
                return JsonResponse({'success': False, 'message': 'Ese nombre de usuario ya está en uso'})

            user.username = username

            if usuario_sistema.rol:
                rol_anterior = usuario_sistema.rol.nombre
            estado_anterior = usuario_sistema.activo
        else:
            if User.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'message': 'Ese nombre de usuario ya está en uso'})
            user = User(username=username)
            password_temporal = get_random_string(
                length=12,
                allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
            )
            user.set_password(password_temporal)

        user.email = email
        user.first_name = nombre
        user.is_active = estado
        user.save()

        if not rut:
            rut = f'99999999-{user.id}'

        if usuario_sistema:
            usuario_sistema.rol = Rol.objects.get(pk=rol_id)
            usuario_sistema.activo = estado
            usuario_sistema.rut = rut
            usuario_sistema.save()
        else:
            usuario_sistema = UsuarioSistema(user=user)
            usuario_sistema.rol = Rol.objects.get(pk=rol_id)
            usuario_sistema.activo = estado
            usuario_sistema.rut = rut
            usuario_sistema.save()

        if rol_anterior is None or rol_anterior != usuario_sistema.rol.nombre:
            registrar_log(request, 'Usuarios', 'Cambio de rol',
                          f'Usuario "{user.username}" cambió de rol de "{rol_anterior}" a "{usuario_sistema.rol.nombre}"',
                          'Usuario', user.id, user.username)

        if estado_anterior is not None and estado_anterior != estado:
            estado_texto = 'Activo' if estado else 'Inactivo'
            estado_anterior_texto = 'Activo' if estado_anterior else 'Inactivo'
            registrar_log(request, 'Usuarios', 'Cambio de estado',
                          f'Usuario "{user.username}" cambió de estado de "{estado_anterior_texto}" a "{estado_texto}"',
                          'Usuario', user.id, user.username)

        registrar_log(request, 'Usuarios', 'Guardar usuario',
                      f'Usuario: {nombre} ({username})', 'Usuario', user.id, nombre)

        respuesta = {'success': True}
        if not usuario_sistema_id:
            respuesta['password_temporal'] = password_temporal
        return JsonResponse(respuesta)

    except Exception:
        logger.exception('Error en guardar_usuario')
        return JsonResponse({
            'success': False,
            'message': 'Ocurrió un error inesperado.'
        }, status=500)


# ==================== CRUD ACTIVIDADES ====================

@login_required
@role_required('Administrador', 'Creador de Evento')
def lista_actividades(request):
    tipo = request.GET.get('tipo', '')
    fecha = request.GET.get('fecha', '')
    fecha_creacion = request.GET.get('fecha_creacion', '')
    estado = request.GET.get('estado', '')
    orden = request.GET.get('orden', '-fecha_inicio')

    # Whitelist de campos ordenables
    campos_validos = {
        'titulo': 'titulo',
        '-titulo': '-titulo',
        'tipo': 'tipo',
        '-tipo': '-tipo',
        'fecha_inicio': 'fecha_inicio',
        '-fecha_inicio': '-fecha_inicio',
        'fecha_creacion': 'fecha_creacion',
        '-fecha_creacion': '-fecha_creacion',
        'estado': 'estado',
        '-estado': '-estado',
        'cupos_disponibles': 'cupos_disponibles',
        '-cupos_disponibles': '-cupos_disponibles',
        'total_inscritos': 'total_inscritos',
        '-total_inscritos': '-total_inscritos',
        'total_asistentes': 'total_asistentes',
        '-total_asistentes': '-total_asistentes',
    }

    orden_seguro = campos_validos.get(orden, '-fecha_inicio')

    es_admin = tiene_rol(request.user, ['Administrador'])

    actividades = Actividad.objects.annotate(
        total_inscritos=Count('inscripciones', distinct=True),
        total_asistentes=Count('asistencias', distinct=True),
        total_invitaciones_exito=Count(
            'notificaciones',
            filter=Q(notificaciones__estado_envio='EXITO'),
            distinct=True
        ),
        total_invitaciones_fallo=Count(
            'notificaciones',
            filter=Q(notificaciones__estado_envio='FALLO'),
            distinct=True
        )
    ).order_by(orden_seguro)

    if tiene_rol(request.user, ['Creador de Evento']) and not es_admin:
        actividades = actividades.filter(creado_por=request.user)

    if tipo:
        actividades = actividades.filter(tipo=tipo)
    if fecha:
        actividades = actividades.filter(fecha_inicio__date=fecha)
    if fecha_creacion:
        actividades = actividades.filter(fecha_creacion__date=fecha_creacion)
    if estado:
        actividades = actividades.filter(estado=estado)

    # Totales para la fila al pie (antes de paginar)
    totales = {
        'actividades': actividades.count(),
        'talleres': actividades.filter(tipo='TALLER').count(),
        'masivas': actividades.filter(tipo='MASIVA').count(),
        'inscritos': Inscripcion.objects.filter(actividad__in=actividades).count(),
        'asistentes': Asistencia.objects.filter(actividad__in=actividades).count(),
    }

    from .utils import paginar
    page_obj = paginar(request, actividades)

    tipos = [('', 'Todos los tipos')] + list(Actividad.TIPO_CHOICES)
    estados = [('', 'Todos los estados')] + list(Actividad.ESTADO_CHOICES)

    return render(request, 'gestion/actividad_list.html', {
        'actividades': page_obj,
        'tipos': tipos,
        'estados': estados,
        'es_admin': es_admin,
        'orden_actual': orden_seguro,
        'totales': totales,
    })

# ==================== DETALLE DE ACTIVIDAD ====================

@login_required
@role_required('Administrador', 'Creador de Evento')
def actividad_detalle(request, pk):
    """Muestra el detalle completo de una actividad."""
    actividad = get_object_or_404(Actividad, pk=pk)

    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    # Métricas
    total_inscritos = Inscripcion.objects.filter(actividad=actividad).count()
    total_inscritos_confirmados = Inscripcion.objects.filter(
        actividad=actividad,
        estado='CONFIRMADA'
    ).count()
    total_asistentes = Asistencia.objects.filter(actividad=actividad).count()

    if total_inscritos_confirmados > 0:
        tasa_asistencia = round(
            (total_asistentes / total_inscritos_confirmados) * 100, 1
        )
    else:
        tasa_asistencia = None

    # Notificaciones
    total_notificaciones_exito = NotificacionCorreo.objects.filter(
        actividad=actividad,
        estado_envio='EXITO'
    ).count()
    total_notificaciones_fallo = NotificacionCorreo.objects.filter(
        actividad=actividad,
        estado_envio='FALLO'
    ).count()

    # Últimas asistencias
    ultimas_asistencias = (
        Asistencia.objects
        .filter(actividad=actividad)
        .select_related('alumno', 'registrado_por')
        .order_by('-fecha_ingreso')[:10]
    )

    context = {
        'actividad': actividad,
        'total_inscritos': total_inscritos,
        'total_inscritos_confirmados': total_inscritos_confirmados,
        'total_asistentes': total_asistentes,
        'tasa_asistencia': tasa_asistencia,
        'total_notificaciones_exito': total_notificaciones_exito,
        'total_notificaciones_fallo': total_notificaciones_fallo,
        'ultimas_asistencias': ultimas_asistencias,
    }

    return render(request, 'gestion/actividad_detalle.html', context)


@login_required
@role_required('Administrador', 'Creador de Evento')
def notificaciones_actividad(request, pk):
    """Lista las notificaciones de correo enviadas para una actividad."""
    actividad = get_object_or_404(Actividad, pk=pk)

    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    filtro_estado = request.GET.get('estado', '')

    notificaciones = (
        NotificacionCorreo.objects
        .filter(actividad=actividad)
        .select_related('alumno')
        .order_by('-fecha_envio')
    )

    if filtro_estado in ['EXITO', 'FALLO']:
        notificaciones = notificaciones.filter(estado_envio=filtro_estado)

    total_exito = NotificacionCorreo.objects.filter(
        actividad=actividad,
        estado_envio='EXITO'
    ).count()
    total_fallo = NotificacionCorreo.objects.filter(
        actividad=actividad,
        estado_envio='FALLO'
    ).count()

    from .utils import paginar
    notificaciones = paginar(request, notificaciones)

    context = {
        'actividad': actividad,
        'notificaciones': notificaciones,
        'total_exito': total_exito,
        'total_fallo': total_fallo,
        'filtro_estado': filtro_estado,
    }

    return render(request, 'gestion/actividad_notificaciones.html', context)


@login_required
@role_required('Administrador', 'Creador de Evento')
def participantes_actividad(request, pk):
    """Lista los inscritos y asistentes de una actividad."""
    actividad = get_object_or_404(Actividad, pk=pk)

    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para ver esta actividad.')
        return redirect('lista_actividades')

    filtro_estado = request.GET.get('estado', '')

    inscripciones = (
        Inscripcion.objects
        .filter(actividad=actividad)
        .select_related('alumno')
        .order_by('alumno__apellidos', 'alumno__nombres')
    )

    if filtro_estado in ['CONFIRMADA', 'CANCELADA', 'LISTA_ESPERA']:
        inscripciones = inscripciones.filter(estado=filtro_estado)

    asistencias = (
        Asistencia.objects
        .filter(actividad=actividad)
        .select_related('alumno', 'registrado_por')
        .order_by('alumno__apellidos', 'alumno__nombres')
    )

    from .utils import paginar
    page_insc = paginar(request, inscripciones, param='page_insc')
    page_asis = paginar(request, asistencias, param='page_asis')

    context = {
        'actividad': actividad,
        'inscripciones': page_insc,
        'asistencias': page_asis,
        'filtro_estado': filtro_estado,
        'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
        'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
    }

    return render(request, 'gestion/actividad_participantes.html', context)


@login_required
@role_required('Administrador', 'Creador de Evento')
def crear_actividad(request):
    if request.method == 'POST':
        request.POST = request.POST.copy()
        if 'fecha_inicio' in request.POST and 'T' in request.POST['fecha_inicio']:
            request.POST['fecha_inicio'] = request.POST['fecha_inicio'].replace('T', ' ')
        if 'fecha_fin' in request.POST and 'T' in request.POST['fecha_fin']:
            request.POST['fecha_fin'] = request.POST['fecha_fin'].replace('T', ' ')

        form = ActividadForm(request.POST, request.FILES)
        if form.is_valid():
            actividad = form.save(commit=False)
            actividad.creado_por = request.user

            if actividad.fecha_fin <= actividad.fecha_inicio:
                form.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la fecha de inicio.')
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    html = render_to_string('gestion/actividad_form_partial.html',
                                            {'form': form, 'titulo': 'Crear Actividad'}, request=request)
                    return JsonResponse({'success': False, 'html': html})
                return render(request, 'gestion/actividad_form.html',
                              {'form': form, 'titulo': 'Crear Actividad'})

            if actividad.tipo == 'TALLER':
                actividad.cupos_disponibles = actividad.cupos_totales
            else:
                actividad.cupos_totales = None
                actividad.cupos_disponibles = None

            actividad.save()
            form.save_m2m()

            registrar_log(request, 'Actividades', 'Crear Actividad',
                          f'Actividad "{actividad.titulo}" (ID: {actividad.id}) creada',
                          'Actividad', actividad.id, actividad.titulo)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'id': actividad.id, 'tipo': actividad.tipo, 'es_nueva': True})
            messages.success(request, 'Actividad creada exitosamente.')
            return redirect('lista_actividades')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors.as_json()})
    else:
        form = ActividadForm()

    if request.GET.get('partial'):
        return render(request, 'gestion/actividad_form_partial.html',
                      {'form': form, 'titulo': 'Crear Actividad'})
    return render(request, 'gestion/actividad_form.html',
                  {'form': form, 'titulo': 'Crear Actividad'})


@login_required
def editar_actividad(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para editar actividades.')
        return redirect('dashboard')

    actividad = get_object_or_404(Actividad, pk=pk)

    if not puede_gestionar_actividad(request.user, actividad):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'No tienes permisos sobre esta actividad.'})
        messages.error(request, 'No tienes permisos para editar esta actividad.')
        return redirect('lista_actividades')

    tiene_inscripciones = Inscripcion.objects.filter(actividad=actividad).exists()
    tiene_asistencias = Asistencia.objects.filter(actividad=actividad).exists()
    tiene_datos = tiene_inscripciones or tiene_asistencias

    forzar_edicion = request.POST.get('forzar_edicion') == 'true' or request.GET.get('forzar_edicion') == 'true'

    if tiene_datos and not forzar_edicion:
        partes = []
        if tiene_inscripciones:
            count_insc = Inscripcion.objects.filter(actividad=actividad).count()
            partes.append(f'{count_insc} inscrito{"s" if count_insc != 1 else ""}')
        if tiene_asistencias:
            count_asis = Asistencia.objects.filter(actividad=actividad).count()
            partes.append(f'{count_asis} asistente{"s" if count_asis != 1 else ""}')

        detalle = ' y '.join(partes)

        mensaje = (
            f'Esta actividad ya tiene {detalle} registrado{"s" if len(partes) > 1 else ""}. '
            f'Si la editas, podrías crear inconsistencias en los datos históricos. '
            f'¿Estás seguro de que quieres editarla de todos modos?'
        )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' and not request.POST:
            return JsonResponse({
                'success': True,
                'requiere_confirmacion': True,
                'mensaje': mensaje,
                'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
                'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
            })

    if request.method == 'POST':
        form = ActividadForm(request.POST, request.FILES, instance=actividad)
        if form.is_valid():
            actividad = form.save(commit=False)

            if actividad.fecha_fin <= actividad.fecha_inicio:
                form.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la fecha de inicio.')
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    html = render_to_string('gestion/actividad_form_partial.html',
                                            {'form': form, 'titulo': 'Editar Actividad'}, request=request)
                    return JsonResponse({'success': False, 'html': html})
                return render(request, 'gestion/actividad_form.html',
                              {'form': form, 'titulo': 'Editar Actividad'})

            if actividad.tipo == 'TALLER':
                inscritos = Inscripcion.objects.filter(actividad=actividad).count()
                actividad.cupos_disponibles = max(0, actividad.cupos_totales - inscritos)
            else:
                actividad.cupos_totales = None
                actividad.cupos_disponibles = None

            actividad.save()
            form.save_m2m()

            if forzar_edicion and tiene_datos:
                detalle_log = (
                    f'Actividad "{actividad.titulo}" (ID: {actividad.id}) editada FORZADAMENTE '
                    f'a pesar de tener {Inscripcion.objects.filter(actividad=actividad).count()} inscritos '
                    f'y {Asistencia.objects.filter(actividad=actividad).count()} asistentes.'
                )
            else:
                detalle_log = f'Actividad "{actividad.titulo}" (ID: {actividad.id}) editada'

            registrar_log(request, 'Actividades', 'Edición de actividad',
                          detalle_log,
                          'Actividad', actividad.id, actividad.titulo)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'id': actividad.id,
                    'tipo': actividad.tipo,
                    'es_nueva': False,
                })
            messages.success(request, 'Actividad actualizada exitosamente.')
            return redirect('lista_actividades')
    else:
        form = ActividadForm(instance=actividad)

    if request.GET.get('partial'):
        return render(request, 'gestion/actividad_form_partial.html',
                      {'form': form, 'titulo': 'Editar Actividad'})
    return render(request, 'gestion/actividad_form.html',
                  {'form': form, 'titulo': 'Editar Actividad'})


@login_required
def eliminar_actividad(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para eliminar actividades.')
        return redirect('dashboard')

    actividad = get_object_or_404(Actividad, pk=pk)

    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos para eliminar esta actividad.')
        return redirect('lista_actividades')

    if Inscripcion.objects.filter(actividad=actividad).exists() or Asistencia.objects.filter(actividad=actividad).exists():
        messages.error(request, 'No puedes eliminar esta actividad porque tiene inscritos o asistentes registrados.')
        return redirect('lista_actividades')

    if request.method == 'POST':
        nombre = actividad.titulo
        id_act = actividad.id
        actividad.delete()
        registrar_log(request, 'Actividades', 'Eliminar Actividad',
                      f'Actividad "{nombre}" (ID: {id_act}) eliminada',
                      'Actividad', id_act, nombre)
        messages.success(request, 'Actividad eliminada.')
        return redirect('lista_actividades')

    return render(request, 'gestion/actividad_confirm_delete.html', {'actividad': actividad})


# ==================== INVITACIONES Y ELIMINACIÓN RÁPIDA ====================

@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def enviar_invitaciones(request):
    if request.method != 'POST':
        return JsonResponse(
            {
                'success': False,
                'message': 'Método no permitido.'
            },
            status=405
        )

    try:
        actividad_id = request.POST.get('actividad_id')

        if not actividad_id:
            return JsonResponse(
                {
                    'success': False,
                    'message': 'No se recibió la actividad.'
                },
                status=400
            )

        actividad = get_object_or_404(Actividad, pk=actividad_id)

        if not puede_gestionar_actividad(request.user, actividad):
            return JsonResponse(
                {
                    'success': False,
                    'message': 'No tienes permisos sobre esta actividad.'
                },
                status=403
            )

        carreras_asociadas = list(actividad.carreras.values_list('nombre', flat=True))
        jornadas_asociadas = list(actividad.jornadas.values_list('nombre', flat=True))

        alumnos_qs = Alumno.objects.all()

        if carreras_asociadas:
            alumnos_qs = alumnos_qs.filter(carrera__in=carreras_asociadas)

        if jornadas_asociadas:
            alumnos_qs = alumnos_qs.filter(jornada__in=jornadas_asociadas)

        limite = settings.MAX_INVITACIONES_POR_ENVIO

        if limite > 0:
            alumnos_qs = alumnos_qs[:limite]

        filtro_descripcion = 'Todas las asociadas'

        if carreras_asociadas or jornadas_asociadas:
            filtro_descripcion = (
                f"Carreras: {', '.join(carreras_asociadas) or 'Todas'} | "
                f"Jornadas: {', '.join(jornadas_asociadas) or 'Todas'}"
            )

        enviados = 0
        fallidos = 0

        for alumno in alumnos_qs:
            try:
                html_contenido = render_to_string(
                    'gestion/email_invitacion.html',
                    {
                        'actividad': actividad,
                        'alumno': alumno,
                        'site_url': settings.SITE_URL,
                    }
                )

                cantidad_enviada = send_mail(
                    subject=f'Invitación: {actividad.titulo}',
                    message=(
                        f'Hola {alumno.nombres}, te invitamos a participar '
                        f'en {actividad.titulo}.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[alumno.correo],
                    html_message=html_contenido,
                    fail_silently=False,
                )

                if cantidad_enviada != 1:
                    raise RuntimeError('El servidor de correo no aceptó el mensaje.')

                NotificacionCorreo.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    estado_envio='EXITO',
                    filtro_aplicado=filtro_descripcion
                )

                enviados += 1

            except Exception:
                NotificacionCorreo.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    estado_envio='FALLO',
                    filtro_aplicado=filtro_descripcion
                )

                fallidos += 1

        registrar_log(
            request,
            'Actividades',
            'Envío de invitaciones',
            (
                f'Actividad "{actividad.titulo}": '
                f'{enviados} exitosos, {fallidos} fallidos. '
                f'Filtro: {filtro_descripcion}'
            ),
            'Actividad',
            actividad.id,
            actividad.titulo
        )

        return JsonResponse({
            'success': fallidos == 0,
            'enviados': enviados,
            'fallidos': fallidos,
            'message': (
                f'{enviados} invitaciones enviadas exitosamente, '
                f'{fallidos} fallidas.'
            )
        })

    except Exception:
        logger.exception('Error en enviar_invitaciones')
        return JsonResponse(
            {
                'success': False,
                'message': 'Ocurrió un error al procesar las invitaciones.'
            },
            status=500
        )


@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def previsualizar_invitacion(request, pk):
    """
    Devuelve el HTML renderizado del correo de invitación
    para previsualizarlo antes de enviarlo.
    """
    try:
        actividad = get_object_or_404(Actividad, pk=pk)

        if not puede_gestionar_actividad(request.user, actividad):
            return JsonResponse({
                'success': False,
                'message': 'No tienes permisos sobre esta actividad.'
            }, status=403)

        carreras_asociadas = [c.nombre for c in actividad.carreras.all()]
        jornadas_asociadas = [j.nombre for j in actividad.jornadas.all()]

        alumnos_qs = Alumno.objects.all()
        if carreras_asociadas:
            alumnos_qs = alumnos_qs.filter(carrera__in=carreras_asociadas)
        if jornadas_asociadas:
            alumnos_qs = alumnos_qs.filter(jornada__in=jornadas_asociadas)

        alumno = alumnos_qs.first()

        if not alumno:
            return JsonResponse({
                'success': False,
                'message': 'No hay alumnos que coincidan con los filtros de esta actividad.'
            })

        html = render_to_string('gestion/email_invitacion.html', {
            'actividad': actividad,
            'alumno': alumno,
            'site_url': settings.SITE_URL,
        })

        return JsonResponse({
            'success': True,
            'html': html,
            'alumno_ejemplo': f'{alumno.nombres} {alumno.apellidos}',
            'total_destinatarios': alumnos_qs.count(),
        })

    except Exception:
        logger.exception('Error en previsualizar_invitacion')
        return JsonResponse({
            'success': False,
            'message': 'Ocurrió un error inesperado.'
        }, status=500)


@login_required
def eliminar_ajax(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})

    try:
        actividad = get_object_or_404(Actividad, pk=pk)

        if not puede_gestionar_actividad(request.user, actividad):
            return JsonResponse({
                'success': False,
                'message': 'No tienes permisos sobre esta actividad.'
            }, status=403)

        if Inscripcion.objects.filter(actividad=actividad).exists() or Asistencia.objects.filter(actividad=actividad).exists():
            return JsonResponse({
                'success': False,
                'message': 'No puedes eliminar esta actividad porque tiene registros asociados.'
            })

        nombre = actividad.titulo
        id_act = actividad.id
        actividad.delete()
        registrar_log(request, 'Actividades', 'Eliminación rápida de actividad',
                      f'Actividad "{nombre}" eliminada por cancelación de creación.',
                      'Actividad', id_act, nombre)
        return JsonResponse({'success': True})

    except Exception:
        logger.exception('Error en eliminar_ajax')
        return JsonResponse({
            'success': False,
            'message': 'Ocurrió un error inesperado.'
        }, status=500)


# ==================== ESCÁNER ====================

@login_required
@role_required('Administrador', 'Creador de Evento', 'Encargado de Registrar')
@ratelimit(key='ip', rate='30/1m', method='POST')
def escaneo(request):

    if request.method == 'POST' and 'cambiar_actividad' in request.POST:
        actividad_id = request.POST.get('actividad_id')

        if not actividad_id:
            mensaje = 'Debes seleccionar una actividad.'

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': mensaje
                }, status=400)

            messages.error(request, mensaje)
            return redirect('escaneo')

        try:
            actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')

            request.session['actividad_escaneo_id'] = actividad.id

            messages.success(request, f'Actividad seleccionada: {actividad.titulo}')

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'redirect_url': '/escaneo/'
                })

            return redirect('escaneo')

        except Actividad.DoesNotExist:
            mensaje = 'Actividad no válida o inactiva.'

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': mensaje
                }, status=404)

            messages.error(request, mensaje)
            return redirect('escaneo')

    if request.method == 'POST' and 'finalizar_turno' in request.POST:
        request.session.pop('actividad_escaneo_id', None)

        messages.info(request, 'Turno finalizado. Selecciona una nueva actividad.')

        return redirect('escaneo')

    if request.method == 'POST' and 'rut' in request.POST:
        rut_original = request.POST.get('rut', '').strip()

        if not rut_original:
            return JsonResponse({
                'success': False,
                'message': 'Debes ingresar un RUT.'
            }, status=400)

        confirmar = request.POST.get('confirmar', 'false').lower() == 'true'

        if 'portal.sidiv.registrocivil.cl' in rut_original or 'RUN=' in rut_original.upper():
            metodo_ingreso = 'QR'

            match = re.search(r'[?&]RUN=([0-9kK-]+)', rut_original, re.IGNORECASE)

            if match:
                rut_original = match.group(1)

        elif "'" in rut_original or '-' in rut_original:
            metodo_ingreso = 'CODIGO'
            rut_original = rut_original.replace("'", "").replace("-", "")

        else:
            metodo_ingreso = 'RUT'

        rut = normalizar_rut(rut_original)

        if not rut:
            return JsonResponse({
                'success': False,
                'message': 'Debes ingresar un RUT válido.'
            }, status=400)

        actividad_id = request.session.get('actividad_escaneo_id')

        if not actividad_id:
            return JsonResponse({
                'success': False,
                'message': 'Primero selecciona una actividad.'
            }, status=400)

        try:
            alumno = Alumno.objects.get(rut=rut)
        except Alumno.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Estudiante no encontrado.'
            }, status=404)

        try:
            actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
        except Actividad.DoesNotExist:
            request.session.pop('actividad_escaneo_id', None)

            return JsonResponse({
                'success': False,
                'message': 'La actividad no existe o ya no está activa.'
            }, status=404)

        # ============================================================
        # PRIMERA ETAPA: MOSTRAR DATOS Y PEDIR CONFIRMACIÓN
        # ============================================================
        if not confirmar:
            asistencia_existente = Asistencia.objects.filter(
                actividad=actividad,
                alumno=alumno
            ).exists()

            if asistencia_existente:
                registrar_log(
                    request,
                    'Escáner',
                    'Intento de asistencia duplicada',
                    (
                        f'Alumno {alumno.nombres} {alumno.apellidos} '
                        f'(RUT: {alumno.rut}) intentó registrar asistencia '
                        f'en {actividad.titulo}'
                    ),
                    'Alumno',
                    alumno.id,
                    f'{alumno.nombres} {alumno.apellidos}'
                )

                return JsonResponse({
                    'success': False,
                    'message': 'La asistencia ya fue registrada anteriormente.'
                }, status=409)

            # Validar inscripción si es taller
            if actividad.tipo == 'TALLER':
                inscrito = Inscripcion.objects.filter(
                    actividad=actividad,
                    alumno=alumno,
                    estado='CONFIRMADA'
                ).exists()

                if not inscrito:
                    registrar_log(
                        request,
                        'Escáner',
                        'Intento de asistencia sin inscripción',
                        (
                            f'Alumno {alumno.nombres} {alumno.apellidos} '
                            f'(RUT: {alumno.rut}) intentó registrar asistencia '
                            f'en el taller "{actividad.titulo}" sin estar inscrito.'
                        ),
                        'Alumno',
                        alumno.id,
                        f'{alumno.nombres} {alumno.apellidos}'
                    )

                    return JsonResponse({
                        'success': False,
                        'message': (
                            f'{alumno.nombres} {alumno.apellidos} '
                            f'no está inscrito en este taller.'
                        )
                    }, status=403)

            return JsonResponse({
                'success': True,
                'confirmar': True,
                'alumno': {
                    'nombre': f'{alumno.nombres} {alumno.apellidos}',
                    'rut': alumno.rut,
                    'carrera': alumno.carrera,
                    'jornada': alumno.jornada
                }
            })

        # ============================================================
        # SEGUNDA ETAPA: CONFIRMAR Y CREAR LA ASISTENCIA
        # ============================================================
        try:
            with transaction.atomic():
                actividad = (
                    Actividad.objects
                    .select_for_update()
                    .get(pk=actividad_id, estado='ACTIVA')
                )

                asistencia_existente = Asistencia.objects.filter(
                    actividad=actividad,
                    alumno=alumno
                ).exists()

                if asistencia_existente:
                    registrar_log(
                        request,
                        'Escáner',
                        'Intento de asistencia duplicada',
                        (
                            f'Alumno {alumno.nombres} '
                            f'{alumno.apellidos} intentó registrar '
                            f'asistencia en {actividad.titulo}'
                        ),
                        'Alumno',
                        alumno.id,
                        f'{alumno.nombres} {alumno.apellidos}'
                    )

                    return JsonResponse({
                        'success': False,
                        'message': 'La asistencia ya fue registrada anteriormente.'
                    }, status=409)

                # Validar inscripción si es taller (dentro de la transacción)
                if actividad.tipo == 'TALLER':
                    inscrito = Inscripcion.objects.filter(
                        actividad=actividad,
                        alumno=alumno,
                        estado='CONFIRMADA'
                    ).exists()

                    if not inscrito:
                        registrar_log(
                            request,
                            'Escáner',
                            'Intento de asistencia sin inscripción',
                            (
                                f'Alumno {alumno.nombres} {alumno.apellidos} '
                                f'(RUT: {alumno.rut}) intentó registrar asistencia '
                                f'en el taller "{actividad.titulo}" sin estar inscrito.'
                            ),
                            'Alumno',
                            alumno.id,
                            f'{alumno.nombres} {alumno.apellidos}'
                        )

                        return JsonResponse({
                            'success': False,
                            'message': (
                                f'{alumno.nombres} {alumno.apellidos} '
                                f'no está inscrito en este taller.'
                            )
                        }, status=403)

                Asistencia.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    metodo_ingreso=metodo_ingreso,
                    registrado_por=request.user
                )

                registrar_log(
                    request,
                    'Escáner',
                    'Registro de asistencia',
                    f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo}',
                    'Alumno',
                    alumno.id,
                    f'{alumno.nombres} {alumno.apellidos}'
                )

        except Actividad.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'La actividad no existe o ya no está activa.'
            }, status=404)

        except IntegrityError:
            return JsonResponse({
                'success': False,
                'message': 'La asistencia ya fue registrada por otro operador.'
            }, status=409)

        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Ocurrió un error al registrar la asistencia.'
            }, status=500)

        return JsonResponse({
            'success': True,
            'confirmar': False,
            'message': f'Asistencia registrada para {alumno.nombres} {alumno.apellidos}.'
        })

    actividad_seleccionada_id = request.session.get('actividad_escaneo_id')
    actividad_seleccionada = None

    if actividad_seleccionada_id:
        try:
            actividad_seleccionada = Actividad.objects.get(
                pk=actividad_seleccionada_id,
                estado='ACTIVA'
            )
        except Actividad.DoesNotExist:
            request.session.pop('actividad_escaneo_id', None)

    actividades_disponibles = (
        Actividad.objects
        .filter(estado='ACTIVA')
        .order_by('-fecha_inicio')
    )

    ultimas_asistencias = []

    if actividad_seleccionada:
        ultimas_asistencias = (
            Asistencia.objects
            .filter(actividad=actividad_seleccionada)
            .select_related('alumno', 'registrado_por')
            .order_by('-fecha_ingreso')[:10]
        )

    context = {
        'actividad_seleccionada': actividad_seleccionada,
        'actividades_disponibles': actividades_disponibles,
        'ultimas_asistencias': ultimas_asistencias,
    }

    return render(request, 'gestion/escaneo.html', context)


# ==================== AUDITORÍA ====================

@login_required
@role_required('Administrador')
def lista_auditoria(request):
    filtro_usuario = request.GET.get('usuario', '')
    filtro_accion = request.GET.get('accion', '')
    filtro_fecha = request.GET.get('fecha', '')
    filtro_modulo = request.GET.get('modulo', '')

    logs = LogAuditoria.objects.all().order_by('-fecha_registro')

    if filtro_usuario:
        logs = logs.filter(usuario_sistema__username__icontains=filtro_usuario)
    if filtro_accion:
        logs = logs.filter(accion__icontains=filtro_accion)
    if filtro_fecha:
        logs = logs.filter(fecha_registro__date=filtro_fecha)
    if filtro_modulo:
        logs = logs.filter(modulo__icontains=filtro_modulo)

    acciones_disponibles = LogAuditoria.objects.values_list('accion', flat=True).distinct().order_by('accion')
    modulos_disponibles = LogAuditoria.objects.values_list('modulo', flat=True).distinct().order_by('modulo')

    from .utils import paginar
    page_obj = paginar(request, logs)

    return render(request, 'gestion/auditoria_list.html', {
        'logs': page_obj,
        'acciones_disponibles': acciones_disponibles,
        'modulos_disponibles': modulos_disponibles,
    })


@login_required
@role_required('Administrador', json_response=True)
def exportar_auditoria(request):
    filtro_usuario = request.GET.get('usuario', '')
    filtro_accion = request.GET.get('accion', '')
    filtro_fecha = request.GET.get('fecha', '')
    filtro_modulo = request.GET.get('modulo', '')

    logs = LogAuditoria.objects.all().order_by('-fecha_registro')
    if filtro_usuario:
        logs = logs.filter(usuario_sistema__username__icontains=filtro_usuario)
    if filtro_accion:
        logs = logs.filter(accion__icontains=filtro_accion)
    if filtro_fecha:
        logs = logs.filter(fecha_registro__date=filtro_fecha)
    if filtro_modulo:
        logs = logs.filter(modulo__icontains=filtro_modulo)

    wb = Workbook()
    ws = wb.active
    ws.title = "Auditoría Filtrada"
    headers = ['Usuario', 'Módulo', 'Objeto', 'ID Objeto', 'Acción', 'Fecha y Hora', 'IP', 'Detalle']
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for row_idx, log in enumerate(logs, start=2):
        usuario = log.usuario_sistema.username if log.usuario_sistema else "Sistema/Anónimo"
        ws.cell(row=row_idx, column=1, value=usuario)
        ws.cell(row=row_idx, column=2, value=log.modulo or "N/A")
        ws.cell(row=row_idx, column=3, value=log.objeto_tipo or "N/A")
        ws.cell(row=row_idx, column=4, value=log.objeto_id or "N/A")
        ws.cell(row=row_idx, column=5, value=log.accion)
        ws.cell(row=row_idx, column=6, value=log.fecha_registro.strftime("%d/%m/%Y %H:%M"))
        ws.cell(row=row_idx, column=7, value=log.ip_address or "N/A")
        ws.cell(row=row_idx, column=8, value=log.detalle)
    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = (max_length + 2)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="auditoria_filtrada.xlsx"'
    wb.save(response)
    return response


# ==================== INSCRIPCIÓN A TALLERES (Pública) ====================

def inscripcion_taller(request, actividad_id):
    actividad = get_object_or_404(Actividad, pk=actividad_id, tipo='TALLER')

    ahora = timezone.now()

    if actividad.estado != 'ACTIVA' or actividad.fecha_fin <= ahora:
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'finalizado'
            }
        )

    cupos = actividad.cupos_disponibles or 0

    if cupos <= 0:
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'sin_cupos'
            }
        )

    if request.method != 'POST':
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'con_cupos'
            }
        )

    rut_original = request.POST.get('rut', '')
    rut = normalizar_rut(rut_original)

    if not rut:
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'con_cupos',
                'error': 'Debes ingresar tu RUT.'
            }
        )

    try:
        alumno = Alumno.objects.get(rut=rut)
    except Alumno.DoesNotExist:
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'con_cupos',
                'error': 'No estás registrado en el sistema.'
            }
        )

    try:
        with transaction.atomic():
            actividad_bloqueada = (
                Actividad.objects
                .select_for_update()
                .get(pk=actividad_id)
            )

            ahora = timezone.now()

            if actividad_bloqueada.tipo != 'TALLER':
                return render(
                    request,
                    'gestion/inscripcion_publica.html',
                    {
                        'actividad': actividad_bloqueada,
                        'estado': 'finalizado',
                        'error': 'Esta actividad no corresponde a un taller.'
                    }
                )

            if (
                actividad_bloqueada.estado != 'ACTIVA'
                or actividad_bloqueada.fecha_fin <= ahora
            ):
                return render(
                    request,
                    'gestion/inscripcion_publica.html',
                    {
                        'actividad': actividad_bloqueada,
                        'estado': 'finalizado'
                    }
                )

            inscripcion_existente = Inscripcion.objects.filter(
                actividad=actividad_bloqueada,
                alumno=alumno
            ).first()

            if inscripcion_existente:
                return render(
                    request,
                    'gestion/inscripcion_publica.html',
                    {
                        'actividad': actividad_bloqueada,
                        'estado': 'con_cupos',
                        'error': 'Ya estás inscrito en este taller.'
                    }
                )

            cupos_actuales = actividad_bloqueada.cupos_disponibles or 0

            if cupos_actuales <= 0:
                return render(
                    request,
                    'gestion/inscripcion_publica.html',
                    {
                        'actividad': actividad_bloqueada,
                        'estado': 'sin_cupos'
                    }
                )

            actividad_bloqueada.cupos_disponibles = cupos_actuales - 1
            actividad_bloqueada.save(update_fields=['cupos_disponibles'])

            Inscripcion.objects.create(
                actividad=actividad_bloqueada,
                alumno=alumno,
                estado='CONFIRMADA'
            )

            registrar_log(
                request,
                'Inscripciones',
                'Inscripción a taller',
                f'{alumno.nombres} {alumno.apellidos} - {actividad_bloqueada.titulo}',
                'Alumno',
                alumno.id,
                f'{alumno.nombres} {alumno.apellidos}'
            )

            cupos_restantes = actividad_bloqueada.cupos_disponibles

    except IntegrityError:
        return render(
            request,
            'gestion/inscripcion_publica.html',
            {
                'actividad': actividad,
                'estado': 'con_cupos',
                'error': 'Ya estás inscrito en este taller.'
            }
        )

    actividad.cupos_disponibles = cupos_restantes

    return render(
        request,
        'gestion/inscripcion_publica.html',
        {
            'actividad': actividad,
            'estado': 'con_cupos',
            'exito': f'¡Inscripción exitosa! Cupos disponibles: {cupos_restantes}'
        }
    )


# ==================== EXPORTAR REPORTE DETALLADO ====================

@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def exportar_reportes_detalle(request, formato):
    actividad_id = request.GET.get('actividad', '')
    carrera = request.GET.get('carrera', '')
    jornada = request.GET.get('jornada', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin = request.GET.get('fecha_fin', '')

    actividades_qs = Actividad.objects.all().order_by('-fecha_inicio')

    if tiene_rol(request.user, ['Creador de Evento']) and not tiene_rol(request.user, ['Administrador']):
        actividades_qs = actividades_qs.filter(creado_por=request.user)

    if actividad_id:
        actividades_qs = actividades_qs.filter(pk=actividad_id)
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    ids_actividades_filtradas = list(actividades_qs.values_list('id', flat=True))

    asistencias_qs = Asistencia.objects.filter(
        actividad_id__in=ids_actividades_filtradas
    ).select_related('alumno', 'registrado_por')

    if carrera:
        asistencias_qs = asistencias_qs.filter(alumno__carrera=carrera)
    if jornada:
        asistencias_qs = asistencias_qs.filter(alumno__jornada=jornada)

    datos = []

    for act in actividades_qs:
        asistencias_act = asistencias_qs.filter(actividad=act)

        agrupado = defaultdict(lambda: {'total': 0, 'registros_por_usuario': defaultdict(int)})

        for a in asistencias_act:
            alumno = a.alumno
            escuela = 'Sin asignar'
            carrera_obj = Carrera.objects.filter(nombre=alumno.carrera).first()
            if carrera_obj and carrera_obj.escuela:
                escuela = carrera_obj.escuela

            clave = (escuela, alumno.carrera, alumno.jornada)
            agrupado[clave]['total'] += 1
            registrado_por = a.registrado_por.username if a.registrado_por else 'Anónimo'
            agrupado[clave]['registros_por_usuario'][registrado_por] += 1

        for (escuela, carrera_nombre, jornada_nombre), valores in agrupado.items():
            total = valores['total']
            partes = [f"{user} ({cant})" for user, cant in valores['registros_por_usuario'].items()]
            detalle_registros = ", ".join(partes) if partes else "Sin registros"

            carreras_act = ", ".join([c.nombre for c in act.carreras.all()])
            jornadas_act = ", ".join([j.nombre for j in act.jornadas.all()])

            datos.append([
                act.titulo,
                act.get_tipo_display(),
                act.fecha_inicio.strftime("%d/%m/%Y"),
                escuela,
                carrera_nombre,
                jornada_nombre,
                total,
                detalle_registros,
                act.creado_por.username if act.creado_por else 'N/A',
                carreras_act,
                jornadas_act,
            ])

    if formato == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="reporte_detalle_participacion.csv"'
        writer = csv.writer(response)
        writer.writerow(['Actividad', 'Tipo', 'Fecha', 'Escuela', 'Carrera', 'Jornada',
                         'Asistentes', 'Registrado por (cantidad)', 'Creador Actividad',
                         'Carreras Asociadas', 'Jornadas Asociadas'])
        for fila in datos:
            writer.writerow(fila)
        return response

    wb = Workbook()
    ws = wb.active
    ws.title = "Detalle Participación"
    headers = ['Actividad', 'Tipo', 'Fecha', 'Escuela', 'Carrera', 'Jornada',
               'Asistentes', 'Registrado por (cantidad)', 'Creador Actividad',
               'Carreras Asociadas', 'Jornadas Asociadas']
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, fila in enumerate(datos, start=2):
        for col_idx, valor in enumerate(fila, start=1):
            ws.cell(row=row_idx, column=col_idx, value=valor)

    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_detalle_participacion.xlsx"'
    wb.save(response)
    return response