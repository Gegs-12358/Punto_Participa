"""
URL Configuration for punto_participa project.

Rutas principales del proyecto:
- /admin/ → Panel de administración de Django
- /       → Todas las rutas de la app 'gestion'
"""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # Panel de administración de Django
    path('admin/', admin.site.urls),

    # Rutas de la aplicación 'gestion'
    path('', include('gestion.urls')),
]


# ============================================================
# CONFIGURACIÓN PARA DESARROLLO
# ============================================================
# Servir archivos media (imágenes subidas) durante el desarrollo.
# En producción, estos archivos los sirve el servidor web (Nginx/Apache).

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)