# gestion/decorators.py
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .permissions import tiene_rol

# DECORADORES DE ROL
def role_required(*roles, json_response=False, redirect_name='dashboard'):
    """ Restringe una vista a los roles indicados.
    Uso:
        @role_required('Administrador')
        def vista(request): ...
        @role_required('Administrador', 'Creador de Evento', json_response=True)
        def vista_ajax(request): ...
    Parámetros:
        *roles: nombres de roles permitidos.
        json_response: si True, devuelve JSON en vez de redirigir (para AJAX).
        redirect_name: nombre de URL a la que redirigir si no tiene permisos.
    """
    def decorator(view_func):

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # 1. Usuario NO autenticado → login (con next)
            if not request.user.is_authenticated:
                if json_response:
                    return JsonResponse(
                        {'success': False, 'message': 'Debes iniciar sesión.'},
                        status=401,
                    )
                login_url = reverse('login')
                return redirect(f'{login_url}?next={request.get_full_path()}')
            # 2. Usuario autenticado pero sin el rol requerido
            if not tiene_rol(request.user, list(roles)):
                if json_response:
                    return JsonResponse(
                        {'success': False, 'message': 'No autorizado.'},
                        status=403,
                    )

                messages.error(
                    request,
                    'No tienes permisos para acceder a esta sección.'
                )
                # Evitar loop: si el redirect es al dashboard y ya estamos en él
                if (redirect_name == 'dashboard'
                        and request.resolver_match
                        and request.resolver_match.url_name == 'dashboard'):
                    return redirect('login')

                return redirect(redirect_name)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# DECORADORES AUXILIARES (opcionales, pero útiles)
# ============================================================

def ajax_required(view_func):
    """
    Fuerza que la petición sea AJAX (para endpoints que devuelven JSON).
    Si no lo es, devuelve 400.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if (request.headers.get('x-requested-with') != 'XMLHttpRequest'
                and 'application/json' not in request.headers.get('accept', '')):
            return JsonResponse(
                {'success': False, 'message': 'Esta ruta solo acepta AJAX.'},
                status=400,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def method_required(*methods):
    """
    Restringe los métodos HTTP permitidos.
    Uso: @method_required('POST', 'PUT')
    """
    methods_upper = {m.upper() for m in methods}

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method.upper() not in methods_upper:
                return JsonResponse(
                    {'success': False,
                     'message': f'Método {request.method} no permitido.'},
                    status=405,
                )
            return view_func(request, *args, **kwargs)
        return wrapper

    return decorator
