from .permissions import get_perfil


def rol_usuario(request):
    """
    Context processor que añade información del rol del usuario
    a todos los templates.

    Devuelve:
        - rol_usuario: nombre del rol ('Administrador', 'Creador de Evento', etc.)
        - perfil_usuario: objeto UsuarioSistema del usuario autenticado
    """
    perfil = get_perfil(request.user)

    return {
        'rol_usuario': perfil.rol.nombre if perfil and perfil.rol else None,
        'perfil_usuario': perfil,
    }