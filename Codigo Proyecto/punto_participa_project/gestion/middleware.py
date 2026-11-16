from django.conf import settings
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import reverse

from .models import UsuarioSistema


class ForzarCambioContrasenaMiddleware:
    """
    Obliga a los usuarios con 'must_change_password=True' a cambiar su
    contraseña antes de acceder a cualquier otra parte del sistema.

    Sin este middleware, la obligación de cambiar la contraseña solo se
    verificaba una vez, justo después del login. Si el usuario ignoraba
    esa redirección (por ejemplo, escribiendo otra URL directamente, o
    usando un enlace guardado), podía usar el sistema completo con su
    contraseña temporal sin cambiarla nunca.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._rutas_exentas = None

    def _rutas_permitidas(self):
        if self._rutas_exentas is None:
            self._rutas_exentas = {
                reverse('cambiar_contrasena'),
                reverse('logout'),
            }
        return self._rutas_exentas

    def __call__(self, request):
        es_estatico = (
            request.path.startswith(settings.STATIC_URL)
            or request.path.startswith(settings.MEDIA_URL)
        )

        if request.user.is_authenticated and not es_estatico:
            try:
                perfil = request.user.usuariosistema
                if perfil.must_change_password and request.path not in self._rutas_permitidas():
                    return redirect('cambiar_contrasena')
            except UsuarioSistema.DoesNotExist:
                # Si el usuario no tiene UsuarioSistema asociado
                # (ej. un superusuario creado con createsuperuser),
                # no se le exige este cambio.
                pass

        return self.get_response(request)


class LimpiarNulMiddleware:
    """
    Quita el carácter NUL (\\x00) de todos los parámetros de la URL (GET) y de
    los formularios (POST) antes de que lleguen a cualquier vista.

    PostgreSQL no acepta NUL en texto: sin este filtro, un parámetro como
    ?carrera=%00 provoca un error 500 en cualquier vista que use ese valor
    en una consulta.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _tiene_nul(qd):
        for clave, valores in qd.lists():
            if '\x00' in clave or any('\x00' in v for v in valores):
                return True
        return False

    @staticmethod
    def _limpiar(qd):
        nuevo = qd.copy()  # copia mutable
        nuevo.clear()
        for clave, valores in qd.lists():
            nuevo.setlist(clave.replace('\x00', ''),
                          [v.replace('\x00', '') for v in valores])
        nuevo._mutable = False
        return nuevo

    def __call__(self, request):
        if self._tiene_nul(request.GET):
            request.GET = self._limpiar(request.GET)
        if request.method == 'POST' and self._tiene_nul(request.POST):
            request.POST = self._limpiar(request.POST)
        return self.get_response(request)

class PaginaMetodoNoPermitidoMiddleware:
    """
    Django no tiene una página propia para el error 405 (método no permitido): las vistas que solo
    aceptan POST responden con una página en blanco. Pasa si alguien recarga la pantalla después de
    apretar un botón o abre la dirección de una acción (enviar invitaciones, bloquear a un alumno...).

    Cuando una persona abre esa dirección desde el navegador, se muestra la página 405.html. Las
    respuestas JSON de los botones y los pedidos AJAX no se tocan.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 405 or response.content:
            return response
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'json' in request.headers.get('accept', ''):
            return response
        from django.template.loader import render_to_string
        pagina = HttpResponseNotAllowed(response.get('Allow', '').split(', '),
                                        render_to_string('405.html', request=request))
        return pagina
