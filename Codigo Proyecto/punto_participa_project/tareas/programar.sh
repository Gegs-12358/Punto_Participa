#!/bin/sh
# Servicio "tareas" (docker-compose.yml): corre una vez al día las tareas programadas del sistema.
# Hoy: retención de datos (python manage.py retencion). Espera a que el servicio web haya aplicado
# las migraciones antes de empezar.
set -u
CADA_HORAS="${TAREAS_CADA_HORAS:-24}"

echo "Tareas: esperando la base de datos y las migraciones..."
until python manage.py migrate --check >/dev/null 2>&1; do
  sleep 15
done
echo "Tareas: listo. Se ejecutan cada ${CADA_HORAS} horas."

while true; do
  python manage.py retencion || echo "Tareas: la retención terminó con error (se reintenta en el próximo ciclo)."
  sleep $((CADA_HORAS * 3600))
done
