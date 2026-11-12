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
RATELIMIT_ENABLE = True

SILENCED_SYSTEM_CHECKS = [
    'django_ratelimit.E003',
    'django_ratelimit.W001',
]

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
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'gestion.middleware.LimpiarNulMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'gestion.middleware.ForzarCambioContrasenaMiddleware',
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
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==================== DETECCIÓN DE TESTS ====================
import sys

TESTING = 'test' in sys.argv

if TESTING:
    # En modo test, usar StaticFilesStorage (sin manifest)
    # porque collectstatic no se ejecuta en los tests.
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# ==================== CONFIGURACIÓN DE CORREO ====================
# Por defecto los correos se imprimen en la consola. Para enviarlos de verdad:
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend en .env
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
# Remitente de los correos. Con Gmail debe ser la misma cuenta de EMAIL_HOST_USER.
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=f'Punto Participa <{EMAIL_HOST_USER}>')
# URL del sitio (para correos y enlaces absolutos)
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')

# ==================== AUTENTICACIÓN ====================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ==================== CONFIGURACIÓN GENERAL ====================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



# Límite de destinatarios por envío de invitaciones (0 = sin límite)
MAX_INVITACIONES_POR_ENVIO = config('MAX_INVITACIONES_POR_ENVIO', default=15, cast=int)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================
# MODO DE EJECUCIÓN Y SEGURIDAD (todo se lee desde .env)
# =============================================================
# Los valores por defecto sirven para trabajar en local con Docker. Para producción
# (con dominio y HTTPS) se activan en .env; ver la sección "Solo para produccion"
# de env.example.
def _lista(valor):
    """'a, b,,c' -> ['a', 'b', 'c']"""
    return [v.strip() for v in valor.split(',') if v.strip()]


DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = _lista(config('ALLOWED_HOSTS', default='localhost,127.0.0.1'))
# Con HTTPS y dominio propio, Django exige declarar el origen para aceptar formularios:
# CSRF_TRUSTED_ORIGINS=https://participa.ejemplo.cl
CSRF_TRUSTED_ORIGINS = _lista(config('CSRF_TRUSTED_ORIGINS', default=''))

SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)
# Detrás de un proxy (Nginx) que termina el HTTPS, para que Django sepa que la conexión es segura
if config('USAR_PROXY_HTTPS', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
