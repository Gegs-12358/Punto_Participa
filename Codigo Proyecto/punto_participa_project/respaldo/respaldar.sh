#!/bin/sh
# ============================================================
# Respaldo de Punto Participa (historia 008)
#
# Guarda la base de datos (pg_dump, formato custom) y las imágenes subidas (media)
# en la carpeta de respaldos. Dentro de ella:
#   diarios/    un respaldo por corrida; se borran los que tienen más de RESPALDO_DIAS días
#   mensuales/  el primer respaldo de cada mes; NUNCA se borran (histórico completo)
#   registro.log  una línea por corrida
#
# No detiene el sistema: pg_dump lee una foto consistente de la base mientras se sigue
# registrando asistencia.
#
# Uso (dentro del servicio "respaldo"):  sh /scripts/respaldar.sh
# ============================================================
set -eu

DIR="${RESPALDO_DESTINO:-/respaldos}"
MEDIA="${MEDIA_ORIGEN:-/media}"
DIAS="${RESPALDO_DIAS:-30}"
FECHA=$(date +%Y-%m-%d_%H%M%S)
MES=$(date +%Y-%m)

registrar() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$DIR/registro.log"; }

if ! mkdir -p "$DIR/diarios" "$DIR/mensuales" 2>/dev/null || ! touch "$DIR/.prueba_escritura" 2>/dev/null; then
    echo "ERROR: no se puede escribir en la carpeta de respaldos ($DIR)." >&2
    echo "Revisa que exista en el computador y que tu usuario sea su dueño (RESPALDO_DIR en .env)." >&2
    exit 1
fi
rm -f "$DIR/.prueba_escritura"

BD="$DIR/diarios/bd_$FECHA.dump"
CONTEOS="$DIR/diarios/bd_$FECHA.conteos"
MED="$DIR/diarios/media_$FECHA.tar.gz"

# 1) Cuántas filas tiene cada tabla justo antes del respaldo (lo usa verificar.sh)
psql -X -A -t -c "
    SELECT format('SELECT %L, count(*) FROM %I;', table_name, table_name)
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
      AND (table_name LIKE 'gestion\_%' OR table_name = 'auth_user')
    ORDER BY table_name" | psql -X -A -t -F ' ' > "$CONTEOS.tmp"

# 2) Base de datos. Se escribe con otro nombre y se renombra al final, así nunca queda
#    un respaldo a medias con nombre válido.
pg_dump -Fc --no-owner -f "$BD.tmp"
pg_restore --list "$BD.tmp" > /dev/null          # el archivo se puede leer
mv "$BD.tmp" "$BD"
mv "$CONTEOS.tmp" "$CONTEOS"

# 3) Imágenes subidas
if [ -d "$MEDIA" ]; then
    tar -czf "$MED.tmp" -C "$MEDIA" .
    mv "$MED.tmp" "$MED"
fi

# 4) Copia mensual: la primera del mes se guarda para siempre
if ! ls "$DIR/mensuales/bd_$MES"*.dump > /dev/null 2>&1; then
    cp "$BD" "$DIR/mensuales/bd_${MES}.dump"
    cp "$CONTEOS" "$DIR/mensuales/bd_${MES}.conteos"
    [ -f "$MED" ] && cp "$MED" "$DIR/mensuales/media_${MES}.tar.gz"
    registrar "Copia mensual guardada: bd_${MES}.dump"
fi

# 5) Retención de los diarios
find "$DIR/diarios" -type f \( -name 'bd_*' -o -name 'media_*' \) -mtime +"$DIAS" -exec rm -f {} \;
find "$DIR/diarios" -type f -name '*.tmp' -mmin +120 -exec rm -f {} \;

TAM=$(du -h "$BD" | cut -f1)
registrar "OK respaldo bd_$FECHA.dump ($TAM)$( [ -f "$MED" ] && echo ' + imágenes')"
