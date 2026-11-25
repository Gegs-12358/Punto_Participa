"""
Cuentas: inicio y cierre de sesión, cambio de contraseña y recuperación por correo.
"""
import logging

from django_ratelimit.decorators import ratelimit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.debug import sensitive_post_parameters

from ..servicios import correos
from ..permissions import get_perfil, ROLES_VALIDOS

from .comun import registrar_log

logger = logging.getLogger(__name__)


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

    perfil = get_perfil(user)
    if not perfil or not perfil.activo or not perfil.rol:
        return _fail()

        
    rol = perfil.rol.nombre
    if rol not in ROLES_VALIDOS:
        messages.error(request, 'La cuenta tiene un rol no válido.')
        return render(request, 'gestion/login.html')

    login(request, user)

    if perfil.must_change_password:
        return redirect('cambiar_contrasena')

    # Respetar ?next= si existe (solo rutas relativas)
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)

    return redirect('escaneo' if rol == 'Encargado de Registrar' else 'dashboard')


@login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
    return redirect('login')


@login_required
@sensitive_post_parameters('contrasena_actual', 'nueva_contrasena', 'confirmar_contrasena')
def cambiar_contrasena(request):
    perfil = get_perfil(request.user)
    if not perfil:
        messages.error(request, 'Tu cuenta no tiene un perfil válido en el sistema.')
        return redirect('login')
    if not perfil.activo:
        messages.error(request, 'Tu cuenta está desactivada.')
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
            dias = max(1, round(settings.PASSWORD_RESET_TIMEOUT / 86400))
            texto, html = correos.armar('recuperacion', {'user': usuario, 'enlace': enlace, 'dias': dias})
            send_mail(
                subject='Recuperación de contraseña - Punto Participa',
                message=texto,
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
        perfil = get_perfil(usuario)
        if perfil:
            perfil.must_change_password = False
            perfil.save(update_fields=['must_change_password'])

        registrar_log(request, 'Seguridad', 'Restablecimiento de contraseña',
                      f'Usuario "{usuario.username}" restableció su contraseña.',
                      'Usuario', usuario.id, usuario.username)
        messages.success(request, 'Tu contraseña fue restablecida correctamente.')
        return redirect('login')

    return render(request, 'gestion/restablecer_contrasena.html', {'token_valido': True})
