from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


def role_required(*roles, json_response=False, redirect_name='dashboard' ):
    """
    Restringe una vista a los roles indicados.

    redirect_name:
        Ruta a la que se enviará al usuario si no tiene permisos.
    """

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from .views import tiene_rol

            if not request.user.is_authenticated:
                if json_response:
                    return JsonResponse(
                        {
                            'success': False,
                            'message': 'Debes iniciar sesión.'
                        },
                        status=401
                    )

                return redirect('login')

            if not tiene_rol(request.user, list(roles)):
                if json_response:
                    return JsonResponse(
                        {
                            'success': False,
                            'message': 'No autorizado.'
                        },
                        status=403
                    )

                messages.error(
                    request,
                    'No tienes permisos para acceder a esta sección.'
                )
                return redirect(redirect_name)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
