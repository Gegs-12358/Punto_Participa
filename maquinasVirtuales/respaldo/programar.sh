#!/bin/sh
# Servicio "respaldo": espera a la base de datos, respalda y repite cada RESPALDO_CADA_HORAS.
HORAS="${RESPALDO_CADA_HORAS:-24}"
echo "Servicio de respaldo: cada $HORAS horas, en ${RESPALDO_DESTINO:-/respaldos}"
until pg_isready -q; do sleep 2; done
while true; do
    sh /scripts/respaldar.sh || echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: el respaldo falló (ver arriba)"
    sleep $((HORAS * 3600))
done
