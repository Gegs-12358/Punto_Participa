"""
Django settings for punto_participa project.
"""

import os
from pathlib import Path
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# ==================== RATE LIMITING (DESARROLLO) ====================
RATELIMIT_ENABLE = False

SILENCED_SYSTEM_CHECKS = [
    'django_ratelimit.E003',
    'django_ratelimit.W001',
]

# ==================== DEBUG Y HOSTS ====================
DEBUG = True

ALLOWED_HOSTS = []

# ==================== APLICACIONES ====================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_ratelimit',
    'gestion',
]

# ==================== CACHÉ ====================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'ratelimit_cache_table',
    }
}

# ==================== MIDDLEWARE ====================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'punto_participa.urls'

# ==================== TEMPLATES ====================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'gestion.context_processors.rol_usuario',
            ],
        },
    },
]

WSGI_APPLICATION = 'punto_participa.wsgi.application'

# ==================== BASE DE DATOS ====================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# ==================== VALIDACIÓN DE CONTRASEÑAS ====================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'max_similarity': 0.7,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ==================== INTERNACIONALIZACIÓN ====================
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# ==================== ARCHIVOS ESTÁTICOS Y MEDIA ====================
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==================== CONFIGURACIÓN DE CORREO ====================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'Punto Participa <casicasi1723@gmail.com>'

# ==================== AUTENTICACIÓN ====================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ==================== CONFIGURACIÓN GENERAL ====================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# URL del sitio (para correos y enlaces absolutos)
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')

# Límite de destinatarios por envío de invitaciones (0 = sin límite)
MAX_INVITACIONES_POR_ENVIO = config('MAX_INVITACIONES_POR_ENVIO', default=15, cast=int)

# =============================================================
# CONFIGURACIÓN PARA PRODUCCIÓN (DESCOMENTAR AL DESPLEGAR)
# =============================================================
# ATENCIÓN: Antes de desplegar en un servidor real, debes:
#   1. Cambiar DEBUG = False (o leerlo desde .env)
#   2. Poner tu dominio real en ALLOWED_HOSTS
#   3. Tener un certificado SSL configurado (HTTPS)
#   4. Configurar las variables en el .env para producción
# Comentar las líneas DEBUG = True y ALLOWED_HOSTS = [] de la parte de arriba.
# =============================================================

"""
# === DESCOMENTAR PARA PRODUCCIÓN (Y COMENTAR LAS LÍNEAS DE ARRIBA) ===

# 1. Desactivar modo debug
# DEBUG = config('DEBUG', default=False, cast=bool)

# 2. Dominios permitidos (cambiar por el dominio real)
# ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='midominio.com,www.midominio.com').split(',')

# 3. Seguridad SSL (requiere certificado HTTPS)
# SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
# SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
# CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)

# 4. HSTS (HTTP Strict Transport Security)
# SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# 5. Archivos estáticos en producción
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# MEDIA_ROOT = os.path.join(BASE_DIR, 'mediafiles')

# === FIN CONFIGURACIÓN PRODUCCIÓN ===
"""