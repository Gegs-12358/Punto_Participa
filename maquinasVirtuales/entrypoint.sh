#!/bin/sh
set -e

# Arranque del contenedor web: espera a PostgreSQL, aplica migraciones, crea la tabla
# de caché del límite de intentos, reúne los archivos estáticos e inicia Gunicorn.
# DB_HOST y DB_PORT los fija docker-compose.yml; el resto viene de .env.

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

python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput

echo "Iniciando Gunicorn..."
exec gunicorn punto_participa.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -