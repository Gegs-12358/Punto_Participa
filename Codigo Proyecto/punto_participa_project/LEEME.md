# Cómo integrar esto en Punto Participa

## 1. Copiar archivos
Copiá estos 4 archivos a la raíz del proyecto (donde está `manage.py`):
- `Dockerfile`
- `docker-compose.yml`
- `entrypoint.sh`
- `.dockerignore`

## 2. Ajustar 2 placeholders en `entrypoint.sh`
Buscá `nombre_proyecto` y reemplazalo por el nombre real de la carpeta
que contiene `settings.py` y `wsgi.py` (la que usás en `DJANGO_SETTINGS_MODULE`).

## 3. Revisar nombres de variables en tu `.env`
El `docker-compose.yml` espera estas variables en tu `.env`:
```
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
```
Si tu `.env` usa otros nombres (ej. `POSTGRES_DB` en vez de `DB_NAME`), avisame
y ajusto el compose para que coincida exactamente, sin que tengas que renombrar nada.

## 4. Revisar `settings.py`
Confirmá que la configuración de base de datos lea de variables de entorno, algo así:
```python
import os

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
```
Si hoy tenés esto hardcodeado, decime y te ayudo a migrarlo.

## 5. Actualizar requirements.txt
Como me dijiste que puede estar desactualizado, generalo de nuevo con tu entorno activado:
```
pip freeze > requirements.txt
```
`gunicorn` y `psycopg2-binary` NO hace falta agregarlos a mano: el `Dockerfile`
ya los instala aparte. Pero si preferís tenerlos explícitos en requirements.txt, mejor,
así el archivo queda como fuente de verdad completa.

## 6. Arrancar Docker Desktop
Abrí Docker Desktop (el ícono de la ballena) y esperá a que diga "Engine running".

## 7. Levantar todo
Desde la raíz del proyecto:
```bash
docker compose build
docker compose up
```
La primera vez va a: levantar PostgreSQL, esperar a que esté sano, correr migraciones,
colectar estáticos, y levantar Gunicorn en el puerto 8000.

Entrá a: http://localhost:8000

## 8. Crear superusuario (primera vez)
En otra terminal, con los contenedores corriendo:
```bash
docker compose exec web python manage.py createsuperuser
```

## Notas
- El volumen `.:/app` en `docker-compose.yml` monta tu código en vivo — cómodo para
  desarrollo, pero para producción real conviene sacarlo y reconstruir la imagen en cada deploy.
- Ya validaste rendimiento con Waitress (5.000 alumnos, 50 usuarios concurrentes) — si preferís
  no arriesgar ese resultado y mantener Waitress dentro del contenedor, decime y cambio
  una línea del Dockerfile/entrypoint sin tocar el resto.
