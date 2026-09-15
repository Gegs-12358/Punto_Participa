from .models import UsuarioSistema


def rol_usuario(request):
    """
    Context processor que añade información del rol del usuario
    a todos los templates.

    Devuelve:
        - rol_usuario: nombre del rol ('Administrador', 'Creador de Evento', etc.)
        - perfil_usuario: objeto UsuarioSistema del usuario autenticado
    """
    contexto = {
        'rol_usuario': None,
        'perfil_usuario': None,
    }

    if not request.user.is_authenticated:
        return contexto

    try:
        perfil = request.user.usuariosistema
        contexto['perfil_usuario'] = perfil
        if perfil.rol:
            contexto['rol_usuario'] = perfil.rol.nombre
    except UsuarioSistema.DoesNotExist:
        # El usuario no tiene perfil asociado (ej: superusuario creado con createsuperuser)
        pass
    except AttributeError:
        # Por si 'usuariosistema' no existe como atributo
        pass

    return contexto