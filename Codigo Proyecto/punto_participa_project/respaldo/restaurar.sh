#!/bin/sh
# ============================================================
# Restaurar un respaldo EN LA BASE DEL SISTEMA (historia 008)
#
# ATENCIÓN: reemplaza todos los datos actuales por los del respaldo. Antes de hacerlo
# guarda un respaldo de seguridad del estado actual (diarios/antes_de_restaurar_*.dump).
# Detén la aplicación primero para que nadie escriba mientras tanto:
#
#   docker compose stop web
#   docker compose exec respaldo sh /scripts/restaurar.sh bd_2026-11-12_030000.dump --confirmo
#   docker compose start web
#
# Para probar un respaldo SIN tocar el sistema, usa verificar.sh.
# ============================================================
set -eu

DIR="${RESPALDO_DESTINO:-/respaldos}"
MEDIA="${MEDIA_ORIGEN:-/media}"

if [ $# -lt 2 ] || [ "$2" != "--confirmo" ]; then
    echo "Uso: sh /scripts/restaurar.sh <archivo.dump> --confirmo" >&2
    echo "Reemplaza TODOS los datos actuales. Para solo probar un respaldo usa verificar.sh." >&2
    exit 1
fi
BD=$(ls "$DIR"/diarios/"$1" "$DIR"/mensuales/"$1" 2>/dev/null | head -n 1 || true)
if [ -z "$BD" ]; then
    echo "ERROR: no encontré $1 en diarios/ ni en mensuales/." >&2
    exit 1
fi
pg_restore --list "$BD" > /dev/null

SEGURIDAD="$DIR/diarios/antes_de_restaurar_$(date +%Y-%m-%d_%H%M%S).dump"
echo "1/3 Guardando el estado actual en $SEGURIDAD"
pg_dump -Fc --no-owner -f "$SEGURIDAD"

echo "2/3 Restaurando $BD"
pg_restore --clean --if-exists --no-owner --single-transaction -d "$PGDATABASE" "$BD"

MED=$(echo "$BD" | sed 's#/bd_\([^/]*\)\.dump$#/media_\1.tar.gz#')
if [ -f "$MED" ] && [ -w "$MEDIA" ]; then
    echo "3/3 Restaurando imágenes desde $MED"
    tar -xzf "$MED" -C "$MEDIA"
else
    echo "3/3 Imágenes: sin cambios (no hay archivo de imágenes o la carpeta es de solo lectura)."
fi
echo "$(date '+%Y-%m-%d %H:%M:%S') RESTAURADO $BD (seguridad: $SEGURIDAD)" >> "$DIR/registro.log"
echo "Listo. Vuelve a iniciar la aplicación: docker compose start web"
