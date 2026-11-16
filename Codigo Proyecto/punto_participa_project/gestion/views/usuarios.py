"""
Usuarios del sistema: listado, crear y editar (con rol y documento), y la carga masiva desde Excel o CSV
(la lógica de la carga está en usuarios_masivos.py).
"""
import csv
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.crypto import get_random_string
from django.views.decorators.debug import sensitive_post_parameters

from ..decorators import role_required
from ..servicios.importador_alumnos import MAX_BYTES
from ..models import LogAuditoria, Rol, UsuarioSistema
from ..servicios.usuarios_masivos import analizar, aplicar, ArchivoInvalido, leer
from ..utils import id_o_none, limpiar_documento, limpiar_texto, normalizar_documento

from .comun import _error_json, registrar_log

logger = logging.getLogger(__name__)


@login_required
@role_required('Administrador')
def usuarios(request):
    from ..utils import paginar
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
        if (usuario_id and id_o_none(usuario_id) is None) or id_o_none(rol_id) is None:
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


PLANTILLA = 'gestion/usuarios_importar.html'


CLAVE_SESION = 'carga_usuarios'


MAX_LISTADO = 100


def _contexto(res, nombre):
    return {
        'vista_previa': True, 'nombre_archivo': nombre,
        'resumen': {'total': res.total, 'nuevos': len(res.nuevos), 'omitidas': len(res.omitidas),
                    'errores': len(res.errores)},
        'nuevos': [d for _, d in res.nuevos[:MAX_LISTADO]],
        'nuevos_extra': max(0, len(res.nuevos) - MAX_LISTADO),
        'omitidas': res.omitidas[:MAX_LISTADO], 'omitidas_extra': max(0, len(res.omitidas) - MAX_LISTADO),
        'errores': res.errores[:MAX_LISTADO], 'errores_extra': max(0, len(res.errores) - MAX_LISTADO),
    }


def _base():
    return {'roles': Rol.objects.order_by('nombre').values_list('nombre', flat=True)}


@login_required
@role_required('Administrador')
def importar_usuarios(request):
    ctx = _base()
    if request.method != 'POST':
        return render(request, PLANTILLA, ctx)
    accion = request.POST.get('accion')

    if accion == 'previsualizar':
        archivo = request.FILES.get('archivo')
        if not archivo:
            ctx['error'] = 'Selecciona un archivo .xlsx o .csv.'
            return render(request, PLANTILLA, ctx)
        if archivo.size > MAX_BYTES:
            ctx['error'] = f'El archivo supera {MAX_BYTES // (1024 * 1024)} MB.'
            return render(request, PLANTILLA, ctx)
        try:
            filas = leer(archivo, archivo.name)
        except ArchivoInvalido as e:
            request.session.pop(CLAVE_SESION, None)
            ctx['error'] = str(e)
            return render(request, PLANTILLA, ctx)
        nombre = archivo.name[:100]
        request.session[CLAVE_SESION] = {'nombre': nombre, 'filas': [[n, d] for n, d in filas]}
        ctx.update(_contexto(analizar(filas), nombre))
        return render(request, PLANTILLA, ctx)

    if accion == 'confirmar':
        guardado = request.session.get(CLAVE_SESION)
        if not guardado:
            ctx['error'] = 'No hay una vista previa pendiente. Sube el archivo de nuevo.'
            return render(request, PLANTILLA, ctx)
        res = analizar([(n, d) for n, d in guardado['filas']])
        request.session.pop(CLAVE_SESION, None)
        if not res.nuevos:
            ctx['error'] = 'No hay usuarios nuevos que crear.'
            return render(request, PLANTILLA, ctx)
        creados, fallidos = aplicar(res)
        registrar_log(request, 'Usuarios', 'Carga masiva de usuarios',
                      f'Archivo {guardado["nombre"]}: {len(creados)} usuarios creados, {len(res.omitidas)} omitidos '
                      f'por existir, {len(res.errores)} filas con error, {len(fallidos)} correos sin enviar.',
                      'Usuario', cambios_json={'creados': creados, 'correos_fallidos': fallidos})
        ctx['resultado'] = {'nombre': guardado['nombre'], 'creados': creados, 'fallidos': fallidos,
                            'omitidas': len(res.omitidas), 'errores': len(res.errores)}
        return render(request, PLANTILLA, ctx)

    ctx['error'] = 'Acción no válida.'
    return render(request, PLANTILLA, ctx)


@login_required
@role_required('Administrador')
def plantilla_usuarios(request):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="plantilla_usuarios.csv"'
    respuesta.write('﻿')
    w = csv.writer(respuesta, delimiter=';')
    w.writerow(['nombre', 'correo', 'rut', 'rol', 'usuario'])
    w.writerow(['Juan Pérez Soto', 'juan.perez@duoc.cl', '12.345.678-5', 'Encargado de Registrar', ''])
    w.writerow(['María González Rojas', 'maria.gonzalez@duoc.cl', '9.876.543-3', 'Creador de Evento', 'mgonzalez'])
    return respuesta
