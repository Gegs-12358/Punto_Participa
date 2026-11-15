"""
Carga masiva de usuarios desde Excel o CSV (solo Administrador).

- Columnas: nombre, correo, rut y rol; usuario es opcional (si no viene, se usa lo que está antes de la @
  del correo). Las reglas son las mismas que al crear un usuario uno por uno.
- Las filas cuyo usuario, RUT o correo ya existen se omiten, con el motivo: la carga nunca modifica cuentas.
- Cada cuenta nueva queda activa y sin contraseña utilizable. La persona recibe un correo con un enlace
  personal, que vence, para crear su contraseña (el mismo mecanismo de "recuperar contraseña").
"""
import logging
import unicodedata
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .importador_alumnos import ArchivoInvalido, leer_filas  # noqa: F401  (ArchivoInvalido se reexporta)
from .models import Rol, UsuarioSistema
from .utils import limpiar_texto, normalizar_documento


logger = logging.getLogger(__name__)

COLUMNAS = ['nombres', 'correo', 'rut', 'rol']
MAX_USUARIOS = 300


def leer(archivo, nombre):
    filas = leer_filas(archivo, nombre, obligatorias=COLUMNAS)
    if len(filas) > MAX_USUARIOS:
        raise ArchivoInvalido(f'Demasiadas filas: el máximo es {MAX_USUARIOS} usuarios por archivo.')
    return filas


def _sin_tildes(texto):
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower().strip()


@dataclass
class Resultado:
    total: int = 0
    nuevos: list = field(default_factory=list)      # [(fila, datos)]
    omitidas: list = field(default_factory=list)    # [(fila, usuario, motivo)]
    errores: list = field(default_factory=list)     # [(fila, mensaje)]


def analizar(filas):
    """Valida las filas sin escribir nada. Devuelve un Resultado."""
    from .views import _username_valido
    res = Resultado(total=len(filas))
    roles = {_sin_tildes(r.nombre): r for r in Rol.objects.all()}
    nombres_roles = ', '.join(sorted(r.nombre for r in roles.values()))
    rut_max = UsuarioSistema._meta.get_field('rut').max_length
    vistos = {'usuario': {}, 'rut': {}, 'correo': {}}

    for n, d in filas:
        nombre = limpiar_texto(d.get('nombres') or '')
        correo = (limpiar_texto(d.get('correo') or '') or '').strip()
        rut = normalizar_documento(limpiar_texto(d.get('rut') or '') or '')
        usuario = (limpiar_texto(d.get('usuario') or d.get('username') or '') or '').strip()
        rol_txt = limpiar_texto(d.get('rol') or '') or ''

        errores = []
        if not nombre:
            errores.append('Falta el nombre.')
        elif len(nombre) > 150:
            errores.append('El nombre supera 150 caracteres.')
        try:
            if not correo or len(correo) > 254:
                raise ValidationError('correo')
            validate_email(correo)
        except ValidationError:
            errores.append('Correo no válido.')
        if not rut:
            errores.append('Falta el RUT o documento.')
        elif len(rut) > rut_max:
            errores.append(f'El RUT supera {rut_max} caracteres.')
        if not usuario and '@' in correo:
            usuario = correo.split('@', 1)[0]
        if not _username_valido(usuario):
            errores.append('Usuario no válido: solo letras, números y @ . + - _ (máximo 150).')
        rol = roles.get(_sin_tildes(rol_txt))
        if rol is None:
            errores.append(f'Rol "{rol_txt}" no existe. Usa: {nombres_roles}.')

        for clave, valor in (('usuario', usuario.lower()), ('rut', rut), ('correo', correo.lower())):
            if valor and valor in vistos[clave]:
                errores.append(f'{clave.capitalize()} repetido en el archivo (ver fila {vistos[clave][valor]}).')
            elif valor:
                vistos[clave][valor] = n

        if errores:
            res.errores.append((n, ' '.join(errores)))
            continue

        motivo = None
        if User.objects.filter(username__iexact=usuario).exists():
            motivo = 'El usuario ya existe.'
        elif UsuarioSistema.objects.filter(rut=rut).exists():
            motivo = 'El RUT ya está asignado a otra cuenta.'
        elif User.objects.filter(email__iexact=correo).exists():
            motivo = 'El correo ya está asignado a otra cuenta.'
        if motivo:
            res.omitidas.append((n, usuario, motivo))
            continue
        res.nuevos.append((n, {'nombre': nombre, 'correo': correo, 'rut': rut, 'usuario': usuario,
                               'rol_id': rol.pk, 'rol': rol.nombre}))
    return res


def enlace_crear_clave(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = PasswordResetTokenGenerator().make_token(user)
    return f'{settings.SITE_URL.rstrip("/")}/restablecer-contrasena/{uid}/{token}/'


def enviar_bienvenida(user, rol):
    """Correo con el enlace para crear la contraseña. Devuelve True si se envió."""
    enlace = enlace_crear_clave(user)
    dias = max(1, round(settings.PASSWORD_RESET_TIMEOUT / 86400))
    try:
        html = render_to_string('gestion/email_bienvenida_usuario.html',
                                {'user': user, 'rol': rol, 'enlace': enlace, 'dias': dias})
        n = send_mail(subject='Tu cuenta en Punto Participa',
                      message=(f'Hola {user.first_name}, se creó tu cuenta en Punto Participa con el rol {rol}. '
                               f'Tu usuario es {user.username}. Crea tu contraseña en {enlace} '
                               f'(el enlace vence en {dias} día{"s" if dias != 1 else ""}).'),
                      from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email],
                      html_message=html, fail_silently=False)
        return n == 1
    except Exception:
        logger.exception('No se pudo enviar el correo de bienvenida (usuario %s)', user.pk)
        return False


def aplicar(res):
    """Crea las cuentas nuevas y envía los correos. Devuelve (creados, correos_fallidos), cada uno una lista
    de (usuario, rol). Si una fila choca con otra cuenta creada recién, se omite sin afectar a las demás."""
    creados, fallidos = [], []
    for _, d in res.nuevos:
        try:
            with transaction.atomic():
                user = User(username=d['usuario'], email=d['correo'], first_name=d['nombre'], is_active=True)
                user.set_unusable_password()
                user.save()
                UsuarioSistema.objects.create(user=user, rol_id=d['rol_id'], rut=d['rut'], activo=True,
                                              must_change_password=True)
        except Exception:
            logger.exception('No se pudo crear el usuario %s en la carga masiva', d['usuario'])
            continue
        creados.append((user.username, d['rol']))
        if not enviar_bienvenida(user, d['rol']):
            fallidos.append((user.username, d['rol']))
    return creados, fallidos
