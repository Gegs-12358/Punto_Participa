#!/bin/sh
# ============================================================
# Prueba de recuperación (historia 008)
#
# Restaura un respaldo en una base TEMPORAL (no toca la base del sistema), compara
# cuántas filas tiene cada tabla con las que había al momento del respaldo y revisa
# que el archivo de imágenes se pueda leer. Deja un informe en la carpeta de respaldos
# (verificaciones/) que sirve como evidencia, y borra la base temporal.
#
# Uso:  sh /scripts/verificar.sh                  (el respaldo más reciente)
#       sh /scripts/verificar.sh bd_2026-11-12_030000.dump
# ============================================================
set -eu

DIR="${RESPALDO_DESTINO:-/respaldos}"
TEMPORAL="verificacion_respaldo"

if [ $# -ge 1 ]; then
    BD=$(ls "$DIR"/diarios/"$1" "$DIR"/mensuales/"$1" 2>/dev/null | head -n 1 || true)
else
    BD=$(ls -t "$DIR"/diarios/bd_*.dump 2>/dev/null | head -n 1 || true)
fi
if [ -z "$BD" ] || [ ! -f "$BD" ]; then
    echo "ERROR: no encontré el respaldo. Corre primero: sh /scripts/respaldar.sh" >&2
    exit 1
fi

BASE=$(basename "$BD" .dump)
CONTEOS="${BD%.dump}.conteos"
MED=$(echo "$BD" | sed 's#/bd_\([^/]*\)\.dump$#/media_\1.tar.gz#')
mkdir -p "$DIR/verificaciones"
INFORME="$DIR/verificaciones/verificacion_$(date +%Y-%m-%d_%H%M%S).txt"

limpiar() { dropdb --if-exists "$TEMPORAL" 2>/dev/null || true; }
trap limpiar EXIT

{
    echo "PRUEBA DE RECUPERACIÓN - Punto Participa"
    echo "Fecha de la prueba : $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Respaldo probado   : $BD"
    echo "Tamaño             : $(du -h "$BD" | cut -f1)"
    echo
} > "$INFORME"

limpiar
createdb "$TEMPORAL"
INICIO=$(date +%s)
pg_restore --no-owner -d "$TEMPORAL" "$BD"
FIN=$(date +%s)
echo "Restauración en base temporal: OK ($((FIN - INICIO)) s)" >> "$INFORME"
echo >> "$INFORME"

FALLAS=0
printf '%-40s %12s %12s  %s\n' "TABLA" "RESPALDO" "RESTAURADO" "RESULTADO" >> "$INFORME"
if [ -f "$CONTEOS" ]; then
    while read -r TABLA ESPERADO; do
        [ -n "$TABLA" ] || continue
        OBTENIDO=$(psql -X -A -t -d "$TEMPORAL" -c "SELECT count(*) FROM \"$TABLA\"" 2>/dev/null || echo "FALTA")
        if [ "$OBTENIDO" = "$ESPERADO" ]; then R="OK"; else R="DIFERENTE"; FALLAS=$((FALLAS + 1)); fi
        printf '%-40s %12s %12s  %s\n' "$TABLA" "$ESPERADO" "$OBTENIDO" "$R" >> "$INFORME"
    done < "$CONTEOS"
else
    echo "(Este respaldo no tiene archivo de conteos; solo se probó que se restaura.)" >> "$INFORME"
fi
echo >> "$INFORME"

if [ -f "$MED" ]; then
    if tar -tzf "$MED" > /dev/null 2>&1; then
        N=$(tar -tzf "$MED" | grep -vc '/$' || true)
        echo "Imágenes: $MED se lee bien ($N archivos)." >> "$INFORME"
    else
        echo "Imágenes: $MED NO se puede leer." >> "$INFORME"; FALLAS=$((FALLAS + 1))
    fi
else
    echo "Imágenes: no hay archivo de imágenes para este respaldo." >> "$INFORME"
fi
echo >> "$INFORME"

if [ "$FALLAS" -eq 0 ]; then
    echo "RESULTADO: RESPALDO RECUPERABLE (todas las tablas coinciden)" >> "$INFORME"
else
    echo "RESULTADO: REVISAR ($FALLAS diferencias)" >> "$INFORME"
fi
cat "$INFORME"
echo
echo "Informe guardado en: $INFORME"
[ "$FALLAS" -eq 0 ]
