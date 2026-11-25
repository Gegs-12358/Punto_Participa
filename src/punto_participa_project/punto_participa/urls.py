"""
URL Configuration for punto_participa project.
 
Rutas principales del proyecto:
- /admin/       → Panel de administración de Django
- /favicon.ico  → Redirige al logo (evita el 404 del navegador)
- /media/       → Imágenes subidas (actividades)
- /             → Todas las rutas de la app 'gestion'
"""
 
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.templatetags.static import static as static_url
from django.urls import include, path, re_path
from django.views.static import serve
 
 
def favicon(request):
    """
    Redirección TEMPORAL al logo. Es temporal (302) a propósito: con
    ManifestStaticFilesStorage el nombre del archivo lleva un hash que cambia
    cuando el logo cambia, y una redirección permanente quedaría cacheada.
    """
    return HttpResponseRedirect(static_url('gestion/img/logo_duoc.png'))
 
 
urlpatterns = [
    # Panel de administración de Django
    path('admin/', admin.site.urls),
 
    # Favicon
    path('favicon.ico', favicon),
 
    # Archivos media (imágenes subidas).
    # Con DEBUG=False, Django no los sirve solo ni WhiteNoise tampoco.
    # Solución válida para un sistema chico; para más tráfico, lo correcto
    # es que los sirva Nginx delante de la aplicación.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
 
    # Rutas de la aplicación 'gestion'
    path('', include('gestion.urls')),
]