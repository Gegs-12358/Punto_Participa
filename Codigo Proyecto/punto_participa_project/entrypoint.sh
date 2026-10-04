#!/bin/sh
set -e

# --- Nombres de variables: deben coincidir con tu .env ---
# DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# Si tu .env usa otros nombres (ej. POSTGRES_HOST), ajustá acá abajo.

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

echo "Esperando PostgreSQL en $DB_HOST:$DB_PORT..."
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('$DB_HOST', $DB_PORT))
    s.close()
except OSError:
    sys.exit(1)
"; do
  sleep 1
done
echo "PostgreSQL disponible."

# ⚠️ AJUSTAR: reemplazar "nombre_proyecto" por el módulo real de settings
# (la carpeta donde está manage.py y settings.py)
python manage.py migrate --noinput
python manage.py collectstatic --noinput

echo "Iniciando Gunicorn..."
# ⚠️ AJUSTAR: reemplazar "nombre_proyecto.wsgi" por tu módulo WSGI real
exec gunicorn punto_participa.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -