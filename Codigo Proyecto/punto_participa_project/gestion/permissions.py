# gestion/permissions.py
"""
Helpers de permisos centralizados.

Este módulo NO debe importar de views.py ni decorators.py.
Es la fuente única de verdad sobre roles y permisos.
"""

from .models import UsuarioSistema


# ============================================================
# CONSTANTES DE ROLES
# ============================================================

ROLES_VALIDOS = {'Administrador', 'Creador de Evento', 'Encargado de Registrar'}
ROLES_DASHBOARD = {'Administrador', 'Creador de Evento'}
ROLES_ADMIN_ONLY = {'Administrador'}


# ============================================================
# HELPERS
# ============================================================

def get_perfil(user):
    """
    Devuelve el UsuarioSistema del user o None si no tiene perfil.
    """
    if not user or not user.is_authenticated:
        return None
    try:
        return user.usuariosistema
    except UsuarioSistema.DoesNotExist:
        return None


def tiene_rol(user, roles):
    """
    Verifica si un usuario tiene alguno de los roles indicados.

    Devuelve False si:
        - no está autenticado
        - no tiene perfil
        - el perfil está inactivo
        - no tiene rol asignado
        - el rol no está en la lista
    """
    perfil = get_perfil(user)
    if not perfil or not perfil.activo or not perfil.rol:
        return False
    return perfil.rol.nombre in roles


def puede_gestionar_actividad(user, actividad):
    """
    True si el user puede ver/editar/eliminar la actividad.
    - Administrador: siempre
    - Creador de Evento: solo si la creó él
    """
    if tiene_rol(user, ROLES_ADMIN_ONLY):
        return True
    return (
        tiene_rol(user, ['Creador de Evento'])
        and actividad.creado_por_id == user.id
    )