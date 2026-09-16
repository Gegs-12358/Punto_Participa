# ==================== IMPORTS ESTÁNDAR DE PYTHON ====================
import re
import json
import csv
from collections import defaultdict

# ==================== IMPORTS DE TERCEROS ====================
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# ==================== IMPORTS DE DJANGO CORE ====================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

# ==================== IMPORTS LOCALES (TU APP) ====================
from .forms import ActividadForm
from .models import (
    Actividad, Asistencia, Alumno, LogAuditoria, Inscripcion,
    NotificacionCorreo, Carrera, Jornada, Rol, UsuarioSistema
)
from django_ratelimit.decorators import ratelimit


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
    if not user.is_authenticated:
        return False
    try:
        rol_usuario = user.usuariosistema.rol.nombre
        return rol_usuario in roles_permitidos
    except Exception:
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
        if not perfil.must_change_password:
            return redirect('dashboard')
    except UsuarioSistema.DoesNotExist:
        return redirect('dashboard')

    if request.method == 'POST':
        contrasena_actual = request.POST.get('contrasena_actual')
        nueva_contrasena = request.POST.get('nueva_contrasena')
        confirmar = request.POST.get('confirmar_contrasena')

        if not request.user.check_password(contrasena_actual):
            messages.error(request, 'La contraseña actual es incorrecta.')
            return render(request, 'gestion/cambiar_contrasena.html')

        if len(nueva_contrasena) < 8:
            messages.error(request, 'La nueva contraseña debe tener al menos 8 caracteres.')
            return render(request, 'gestion/cambiar_contrasena.html')

        if nueva_contrasena != confirmar:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'gestion/cambiar_contrasena.html')

        request.user.set_password(nueva_contrasena)
        request.user.save()
        update_session_auth_hash(request, request.user)
        perfil.must_change_password = False
        perfil.save()

        login(request, request.user)

        registrar_log(request, 'Seguridad', 'Cambio de contraseña',
                      f'Usuario "{request.user.username}" cambió su contraseña inicial',
                      'Usuario', request.user.id, request.user.username)

        messages.success(request, 'Contraseña actualizada correctamente. Ya puedes usar el sistema.')
        return redirect('dashboard')

    return render(request, 'gestion/cambiar_contrasena.html')


# ==================== AUTENTICACIÓN ====================

@ratelimit(key='ip', rate='5/15m', method='POST')
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            try:
                perfil = user.usuariosistema
                if not perfil.activo:
                    messages.error(request, 'Tu cuenta ha sido desactivada por un administrador.')
                    return render(request, 'gestion/login.html')
            except UsuarioSistema.DoesNotExist:
                pass

            login(request, user)

            try:
                perfil = user.usuariosistema
                if perfil.must_change_password:
                    return redirect('cambiar_contrasena')
            except UsuarioSistema.DoesNotExist:
                pass

            try:
                rol = user.usuariosistema.rol.nombre
                if rol == 'Encargado de Registrar':
                    return redirect('escaneo')
                return redirect('dashboard')
            except Exception:
                return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'gestion/login.html')


def logout_view(request):
    storage = get_messages(request)
    for _ in storage:
        pass
    logout(request)
    return redirect('login')


# ==================== DASHBOARD ====================

@login_required
def dashboard(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para ver el panel principal.')
        return redirect('login')

    es_admin = tiene_rol(request.user, ['Administrador'])
    es_creador = tiene_rol(request.user, ['Creador de Evento'])

    actividades_qs = Actividad.objects.all()
    asistencias_qs = Asistencia.objects.all()

    if es_creador and not es_admin:
        actividades_qs = actividades_qs.filter(creado_por=request.user)
        asistencias_qs = asistencias_qs.filter(actividad__creado_por=request.user)

    actividades_activas = actividades_qs.filter(estado='ACTIVA').count()
    talleres_proximos = actividades_qs.filter(
        tipo='TALLER',
        estado='ACTIVA',
        fecha_inicio__gte=timezone.now(),
        cupos_disponibles__gt=0
    ).count()
    asistencias_hoy = asistencias_qs.filter(fecha_ingreso__date=timezone.now().date()).count()
    ultimas_actividades = actividades_qs.order_by('-fecha_inicio')[:8]

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
        .order_by('-total')
    )
    labels_pastel = [item['alumno__carrera'] for item in asistencias_por_carrera]
    data_pastel = [item['total'] for item in asistencias_por_carrera]

    context = {
        'actividades_activas': actividades_activas,
        'talleres_proximos': talleres_proximos,
        'asistencias_hoy': asistencias_hoy,
        'actividades': ultimas_actividades,
        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
    }
    return render(request, 'gestion/dashboard.html', context)


# ==================== REPORTES ====================

@login_required
def reportes(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para consultar reportes.')
        return redirect('dashboard')

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
    if carrera:
        actividades_qs = actividades_qs.filter(carreras__nombre__icontains=carrera).distinct()
    if jornada:
        actividades_qs = actividades_qs.filter(jornadas__nombre__icontains=jornada).distinct()
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    actividades_qs = actividades_qs.annotate(
        total_asistentes_calc=Count('asistencias', distinct=True),
        total_inscritos_calc=Count('inscripciones', distinct=True),
    ).prefetch_related('carreras', 'jornadas')

    ids_actividades_filtradas = list(actividades_qs.values_list('id', flat=True))

    # ============================================================
    # Datos para el gráfico de barras (asistentes por actividad)
    # ============================================================
    labels_barras = [act.titulo for act in actividades_qs]
    data_barras = [act.total_asistentes_calc for act in actividades_qs]

    # ============================================================
    # Datos para el gráfico de pastel (asistentes por carrera)
    # ============================================================
    asistencias_por_carrera = (
        Asistencia.objects
        .filter(actividad_id__in=ids_actividades_filtradas)
        .values('alumno__carrera')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    labels_pastel = [item['alumno__carrera'] for item in asistencias_por_carrera]
    data_pastel = [item['total'] for item in asistencias_por_carrera]

    # ============================================================
    # Datos para el gráfico de barras por JORNADA (pestaña General)
    # ============================================================
    asistencias_por_jornada = (
        Asistencia.objects
        .filter(actividad_id__in=ids_actividades_filtradas)
        .values('alumno__jornada')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    labels_jornada = [item['alumno__jornada'] or 'Sin jornada' for item in asistencias_por_jornada]
    data_jornada = [item['total'] for item in asistencias_por_jornada]

    # ============================================================
    # Registros por actividad (para columna "Registrado por")
    # ============================================================
    registros_por_actividad = {}
    registros_qs = (
        Asistencia.objects
        .filter(actividad_id__in=ids_actividades_filtradas)
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

    # ============================================================
    # Datos detallados por escuela y carrera
    # ============================================================
    detalle_data = []
    detalle_escuelas = defaultdict(int)
    detalle_carreras = defaultdict(int)

    carreras_cache = {c.nombre.lower(): c for c in Carrera.objects.all()}

    asistencias_detalle = (
        Asistencia.objects
        .filter(actividad_id__in=ids_actividades_filtradas)
        .select_related('alumno', 'registrado_por', 'actividad')
    )

    agrupado_por_actividad = defaultdict(
        lambda: defaultdict(lambda: {'total': 0, 'registros': defaultdict(int)})
    )

    for a in asistencias_detalle:
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

    # ============================================================
    # Datos por JORNADA para el detallado
    # ============================================================
    labels_jornada_detalle = labels_jornada
    data_jornada_detalle = data_jornada

    # ============================================================
    # Opciones para filtros
    # ============================================================
    if es_creador and not es_admin:
        actividades_opciones = Actividad.objects.filter(creado_por=request.user).order_by('-fecha_inicio')
    else:
        actividades_opciones = Actividad.objects.all().order_by('-fecha_inicio')

    context = {
        'actividades': actividades_qs,
        'labels_barras': labels_barras,
        'data_barras': data_barras,
        'labels_pastel': labels_pastel,
        'data_pastel': data_pastel,
        'labels_jornada': labels_jornada,
        'data_jornada': data_jornada,
        'detalle_data': detalle_data,
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
    }
    return render(request, 'gestion/reportes.html', context)


@login_required
def exportar_reportes(request, formato):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

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
    if carrera:
        actividades_qs = actividades_qs.filter(carreras__nombre__icontains=carrera).distinct()
    if jornada:
        actividades_qs = actividades_qs.filter(jornadas__nombre__icontains=jornada).distinct()
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    datos = []
    for act in actividades_qs:
        carreras = ", ".join([c.nombre for c in act.carreras.all()])
        jornadas = ", ".join([j.nombre for j in act.jornadas.all()])
        creador = act.creado_por.username if act.creado_por else 'N/A'
        total_inscritos = Inscripcion.objects.filter(actividad=act).count()
        total_asistentes = Asistencia.objects.filter(actividad=act).count()

        asistencias_act = Asistencia.objects.filter(actividad=act)
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
def usuarios(request):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'No tienes permisos para gestionar usuarios.')
        return redirect('dashboard')

    usuarios = UsuarioSistema.objects.all().order_by('-id')
    logs_recientes = LogAuditoria.objects.all().order_by('-fecha_registro')[:10]
    roles = Rol.objects.all()

    context = {
        'usuarios': usuarios,
        'logs': logs_recientes,
        'roles': roles,
    }
    return render(request, 'gestion/usuarios.html', context)


@login_required
def guardar_usuario(request):
    if not tiene_rol(request.user, ['Administrador']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

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

        # ============================================================
        # PROTECCIÓN PRIMERO: No permitir bloquearse a sí mismo
        # (antes de cualquier otra validación)
        # ============================================================
        if usuario_sistema_id:
            usuario_sistema = UsuarioSistema.objects.get(pk=usuario_sistema_id)
            user = usuario_sistema.user

            if usuario_sistema.user == request.user and not estado:
                return JsonResponse({
                    'success': False,
                    'message': 'No puedes bloquear tu propia cuenta.'
                })
        # ============================================================

        # Validaciones básicas (después de la protección)
        if not username or not nombre or not email or not rol_id:
            return JsonResponse({'success': False, 'message': 'Faltan campos obligatorios'})

        if usuario_sistema_id:
            # Si cambia el username, verificar que no exista otro con ese nombre
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
            user.set_password('Duoc12345')

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

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


# ==================== CRUD ACTIVIDADES ====================

@login_required
def lista_actividades(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para ver actividades.')
        return redirect('dashboard')

    tipo = request.GET.get('tipo', '')
    fecha = request.GET.get('fecha', '')
    fecha_creacion = request.GET.get('fecha_creacion', '')
    estado = request.GET.get('estado', '')

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
    ).order_by('-fecha_inicio')

    if tiene_rol(request.user, ['Creador de Evento']) and not tiene_rol(request.user, ['Administrador']):
        actividades = actividades.filter(creado_por=request.user)

    if tipo:
        actividades = actividades.filter(tipo=tipo)
    if fecha:
        actividades = actividades.filter(fecha_inicio__date=fecha)
    if fecha_creacion:
        actividades = actividades.filter(fecha_creacion__date=fecha_creacion)
    if estado:
        actividades = actividades.filter(estado=estado)

    # Paginación: 20 actividades por página
    from django.core.paginator import Paginator
    paginator = Paginator(actividades, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    tipos = [('', 'Todos los tipos')] + list(Actividad.TIPO_CHOICES)
    estados = [('', 'Todos los estados')] + list(Actividad.ESTADO_CHOICES)

    return render(request, 'gestion/actividad_list.html', {
        'actividades': page_obj,
        'tipos': tipos,
        'estados': estados
    })


@login_required
def crear_actividad(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        messages.error(request, 'No tienes permisos para crear actividades.')
        return redirect('dashboard')

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
                return JsonResponse({ 'success': True, 'id': actividad.id, 'tipo': actividad.tipo,'es_nueva': True,})
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

    # ============================================================
    # Detectar si tiene datos asociados
    # ============================================================
    tiene_inscripciones = Inscripcion.objects.filter(actividad=actividad).exists()
    tiene_asistencias = Asistencia.objects.filter(actividad=actividad).exists()
    tiene_datos = tiene_inscripciones or tiene_asistencias

    # El frontend puede forzar la edición enviando este flag
    forzar_edicion = request.POST.get('forzar_edicion') == 'true' or request.GET.get('forzar_edicion') == 'true'

    # ============================================================
    # Si tiene datos y NO se ha forzado, pedir confirmación al usuario
    # ============================================================
    if tiene_datos and not forzar_edicion:
        # Construir mensaje contextual
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

        # Si es AJAX y no hay POST todavía, solo pedir confirmación
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' and not request.POST:
            return JsonResponse({
                'success': True,
                'requiere_confirmacion': True,
                'mensaje': mensaje,
                'total_inscritos': Inscripcion.objects.filter(actividad=actividad).count(),
                'total_asistentes': Asistencia.objects.filter(actividad=actividad).count(),
            })

    # ============================================================
    # Procesar POST (con o sin forzar_edicion)
    # ============================================================
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

            # Registrar en auditoría con detalle de si fue forzada
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
def enviar_invitaciones(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})

    try:
        actividad_id = request.POST.get('actividad_id')
        actividad = get_object_or_404(Actividad, pk=actividad_id)

        carreras_asociadas = [c.nombre for c in actividad.carreras.all()]
        jornadas_asociadas = [j.nombre for j in actividad.jornadas.all()]

        alumnos_qs = Alumno.objects.all()
        if carreras_asociadas:
            alumnos_qs = alumnos_qs.filter(carrera__in=carreras_asociadas)
        if jornadas_asociadas:
            alumnos_qs = alumnos_qs.filter(jornada__in=jornadas_asociadas)

        # LÍMITE DE 15 PARA PRUEBAS
        alumnos = alumnos_qs[:15]
        # Para envío masivo: descomentar la línea de abajo y comentar la de arriba
        # alumnos = alumnos_qs

        filtro_descripcion = "Todas las asociadas"
        if carreras_asociadas or jornadas_asociadas:
            filtro_descripcion = (
                f"Carreras: {', '.join(carreras_asociadas) or 'Todas'} | "
                f"Jornadas: {', '.join(jornadas_asociadas) or 'Todas'}"
            )

        enviados = 0
        fallidos = 0

        for alumno in alumnos:
            try:
                html_contenido = render_to_string('gestion/email_invitacion.html', {
                    'actividad': actividad,
                    'alumno': alumno,
                    'site_url': settings.SITE_URL,
                })
                send_mail(
                    subject=f'Invitación: {actividad.titulo}',
                    message=f'Hola {alumno.nombres}, te invitamos a participar en {actividad.titulo}.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[alumno.correo],
                    html_message=html_contenido,
                    fail_silently=True,
                )
                NotificacionCorreo.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    estado_envio='EXITO',
                    filtro_aplicado=filtro_descripcion
                )
                enviados += 1
            except Exception as e:
                NotificacionCorreo.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    estado_envio='FALLO',
                    filtro_aplicado=filtro_descripcion
                )
                fallidos += 1

        registrar_log(request, 'Actividades', 'Envío de invitaciones',
                      f'Actividad "{actividad.titulo}": {enviados} exitosos, {fallidos} fallidos. '
                      f'Filtro: {filtro_descripcion}',
                      'Actividad', actividad.id, actividad.titulo)

        return JsonResponse({
            'success': True,
            'message': f'{enviados} invitaciones enviadas exitosamente, {fallidos} fallidas.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al enviar: {str(e)}'})

@login_required
def previsualizar_invitacion(request, pk):
    """
    Devuelve el HTML renderizado del correo de invitación
    para previsualizarlo antes de enviarlo.
    """
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

    try:
        actividad = get_object_or_404(Actividad, pk=pk)

        # Tomar un alumno de ejemplo (el primero que coincida con los filtros)
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

        # Renderizar el HTML del correo
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

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})    


@login_required
def eliminar_ajax(request, pk):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'})

    try:
        actividad = get_object_or_404(Actividad, pk=pk)
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
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


# ==================== ESCÁNER ====================

@login_required
@ratelimit(key='ip', rate='30/1m', method='POST')
def escaneo(request):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento', 'Encargado de Registrar']):
        messages.error(request, 'No tienes permisos para registrar asistencia.')
        return redirect('dashboard')

    # 1. CAMBIAR ACTIVIDAD
    if request.method == 'POST' and 'cambiar_actividad' in request.POST:
        actividad_id = request.POST.get('actividad_id')
        if actividad_id:
            try:
                actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
                request.session['actividad_escaneo_id'] = actividad.id
                messages.success(request, f'Actividad seleccionada: {actividad.titulo}')
            except Actividad.DoesNotExist:
                messages.error(request, 'Actividad no válida o inactiva.')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'redirect_url': '/escaneo/'})
        return redirect('escaneo')

    # 2. FINALIZAR TURNO
    if request.method == 'POST' and 'finalizar_turno' in request.POST:
        if 'actividad_escaneo_id' in request.session:
            del request.session['actividad_escaneo_id']
        messages.info(request, 'Turno finalizado. Selecciona una nueva actividad.')
        return redirect('escaneo')

    # 3. REGISTRAR ASISTENCIA
    if request.method == 'POST' and 'rut' in request.POST:
        rut_original = request.POST.get('rut')
        confirmar = request.POST.get('confirmar', 'false') == 'true'

        if 'portal.sidiv.registrocivil.cl' in rut_original or 'RUN=' in rut_original:
            metodo_ingreso = 'QR'
            match = re.search(r'[?&]RUN=([0-9kK-]+)', rut_original)
            if match:
                rut_original = match.group(1)
        elif "'" in rut_original or "-" in rut_original:
            metodo_ingreso = 'CODIGO'
            rut_original = rut_original.replace("'", "").replace("-", "")
        else:
            metodo_ingreso = 'RUT'

        texto_limpio = re.sub(r'[^0-9kK]', '', str(rut_original)).upper()
        if len(texto_limpio) >= 9:
            rut = texto_limpio[:9]
        else:
            rut = texto_limpio

        actividad_id = request.session.get('actividad_escaneo_id')
        if not actividad_id:
            return JsonResponse({'success': False, 'message': 'Primero selecciona una actividad.'})
        if not rut:
            return JsonResponse({'success': False, 'message': 'Debes ingresar un RUT.'})

        try:
            alumno = Alumno.objects.get(rut=rut)
            actividad = Actividad.objects.get(pk=actividad_id)

            if confirmar is False:
                if Asistencia.objects.filter(actividad=actividad, alumno=alumno).exists():
                    registrar_log(request, 'Escáner', 'Intento de asistencia duplicada',
                                  f'Alumno {alumno.nombres} {alumno.apellidos} (RUT: {alumno.rut}) '
                                  f'intentó registrar asistencia en {actividad.titulo}',
                                  'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
                    return JsonResponse({'success': False, 'message': 'Ya registrado anteriormente'})
                if actividad.cupos_disponibles is not None and actividad.cupos_disponibles <= 0:
                    return JsonResponse({'success': False, 'message': 'No quedan cupos disponibles para esta actividad.'})
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

            elif confirmar is True:
                with transaction.atomic():
                    actividad = Actividad.objects.select_for_update().get(pk=actividad_id)
                    if Asistencia.objects.filter(actividad=actividad, alumno=alumno).exists():
                        registrar_log(request, 'Escáner', 'Intento de asistencia duplicada',
                                      f'Alumno {alumno.nombres} {alumno.apellidos} intentó registrar '
                                      f'asistencia en {actividad.titulo}',
                                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
                        return JsonResponse({'success': False, 'message': 'Ya registrado anteriormente'})
                    if actividad.cupos_disponibles is not None and actividad.cupos_disponibles <= 0:
                        return JsonResponse({'success': False, 'message': 'No quedan cupos disponibles para esta actividad.'})
                    if actividad.cupos_disponibles is not None:
                        actividad.cupos_disponibles -= 1
                        actividad.save()
                    Asistencia.objects.create(
                        actividad=actividad,
                        alumno=alumno,
                        metodo_ingreso=metodo_ingreso,
                        registrado_por=request.user
                    )
                    registrar_log(request, 'Escáner', 'Registro de asistencia',
                                  f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo}',
                                  'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')
                return JsonResponse({
                    'success': True,
                    'confirmar': False,
                    'message': f'Asistencia registrada para {alumno.nombres} {alumno.apellidos}'
                })

        except Alumno.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Estudiante no encontrado'})
        except Actividad.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Actividad no válida'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error inesperado: {str(e)}'})

    # 4. GET
    actividad_seleccionada_id = request.session.get('actividad_escaneo_id')
    actividad_seleccionada = None
    if actividad_seleccionada_id:
        try:
            actividad_seleccionada = Actividad.objects.get(pk=actividad_seleccionada_id)
        except Actividad.DoesNotExist:
            del request.session['actividad_escaneo_id']

    actividades_disponibles = Actividad.objects.filter(estado='ACTIVA').order_by('-fecha_inicio')
    ultimas_asistencias = []
    if actividad_seleccionada:
        ultimas_asistencias = (
            Asistencia.objects
            .filter(actividad=actividad_seleccionada)
            .order_by('-fecha_ingreso')[:10]
        )

    context = {
        'actividad_seleccionada': actividad_seleccionada,
        'actividades_disponibles': actividades_disponibles,
        'ultimas_asistencias': ultimas_asistencias
    }
    return render(request, 'gestion/escaneo.html', context)


# ==================== AUDITORÍA ====================

@login_required
def lista_auditoria(request):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'No tienes permisos para ver la auditoría.')
        return redirect('dashboard')

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

        # Paginación: 50 registros por página
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'gestion/auditoria_list.html', {
        'logs': page_obj,
        'acciones_disponibles': acciones_disponibles,
        'modulos_disponibles': modulos_disponibles,
    })


@login_required
def exportar_auditoria(request):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'No tienes permisos para exportar.')
        return redirect('dashboard')

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
    cupos = actividad.cupos_disponibles if actividad.cupos_disponibles is not None else 0

    if actividad.fecha_fin < timezone.now():
        return render(request, 'gestion/inscripcion_publica.html',
                      {'actividad': actividad, 'estado': 'finalizado'})
    if cupos <= 0:
        return render(request, 'gestion/inscripcion_publica.html',
                      {'actividad': actividad, 'estado': 'sin_cupos'})

    if request.method == 'POST':
        rut_original = request.POST.get('rut')
        rut = normalizar_rut(rut_original)
        if not rut:
            return render(request, 'gestion/inscripcion_publica.html',
                          {'actividad': actividad, 'estado': 'con_cupos',
                           'error': 'Debes ingresar tu RUT.'})
        try:
            alumno = Alumno.objects.get(rut=rut)
        except Alumno.DoesNotExist:
            return render(request, 'gestion/inscripcion_publica.html',
                          {'actividad': actividad, 'estado': 'con_cupos',
                           'error': 'No estás registrado en el sistema.'})

        if Inscripcion.objects.filter(actividad=actividad, alumno=alumno).exists():
            return render(request, 'gestion/inscripcion_publica.html',
                          {'actividad': actividad, 'estado': 'con_cupos',
                           'error': 'Ya estás inscrito en este taller.'})

        with transaction.atomic():
            actividad = Actividad.objects.select_for_update().get(pk=actividad_id)
            cupos_actuales = actividad.cupos_disponibles if actividad.cupos_disponibles is not None else 0
            if cupos_actuales <= 0:
                return render(request, 'gestion/inscripcion_publica.html',
                              {'actividad': actividad, 'estado': 'sin_cupos'})
            actividad.cupos_disponibles -= 1
            actividad.save()
            Inscripcion.objects.create(actividad=actividad, alumno=alumno, estado='CONFIRMADA')
            registrar_log(request, 'Inscripciones', 'Inscripción a taller',
                          f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo}',
                          'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

        actividad.cupos_disponibles = (actividad.cupos_disponibles if actividad.cupos_disponibles is not None else 0)
        return render(request, 'gestion/inscripcion_publica.html',
                      {'actividad': actividad, 'estado': 'con_cupos',
                       'exito': f'¡Inscripción exitosa! Cupos disponibles: {actividad.cupos_disponibles}'})

    return render(request, 'gestion/inscripcion_publica.html',
                  {'actividad': actividad, 'estado': 'con_cupos'})


# ==================== EXPORTAR REPORTE DETALLADO ====================

@login_required
def exportar_reportes_detalle(request, formato):
    if not tiene_rol(request.user, ['Administrador', 'Creador de Evento']):
        return JsonResponse({'success': False, 'message': 'No autorizado'})

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
    if carrera:
        actividades_qs = actividades_qs.filter(carreras__nombre__icontains=carrera).distinct()
    if jornada:
        actividades_qs = actividades_qs.filter(jornadas__nombre__icontains=jornada).distinct()
    if fecha_inicio:
        actividades_qs = actividades_qs.filter(fecha_inicio__date__gte=fecha_inicio)
    if fecha_fin:
        actividades_qs = actividades_qs.filter(fecha_fin__date__lte=fecha_fin)

    datos = []
    for act in actividades_qs:
        asistencias_act = Asistencia.objects.filter(actividad=act).select_related('alumno', 'registrado_por')

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