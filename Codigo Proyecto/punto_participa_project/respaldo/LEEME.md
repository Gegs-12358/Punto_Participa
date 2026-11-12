# Respaldo y recuperación (historia 008)

El servicio `respaldo` de `docker-compose.yml` respalda automáticamente la base de datos y las
imágenes subidas. No detiene el sistema: `pg_dump` lee una foto consistente de la base mientras
se sigue registrando asistencia.

## Qué se respalda

| Archivo | Contenido |
| --- | --- |
| `bd_AAAA-MM-DD_HHMMSS.dump` | Toda la base: usuarios y roles, alumnos, actividades, inscripciones, asistencias, notificaciones, auditoría y catálogos |
| `bd_….conteos` | Cuántas filas tenía cada tabla al respaldar (lo usa la prueba de recuperación) |
| `media_….tar.gz` | Las imágenes de las actividades (volumen `media_volume`) |

## Frecuencia, retención y ubicación

Se configuran en `.env` (ver `env.example`):

| Variable | Por defecto | Qué hace |
| --- | --- | --- |
| `RESPALDO_DIR` | `./respaldos` | Carpeta del computador donde se guardan |
| `RESPALDO_CADA_HORAS` | `24` | Cada cuántas horas se respalda (además, uno al iniciar el servicio) |
| `RESPALDO_DIAS` | `30` | Días que se guardan los respaldos de `diarios/` |
| `RESPALDO_UID`, `RESPALDO_GID` | `1000` | Tu usuario del computador (`id -u`, `id -g`), para que los archivos sean tuyos |

Dentro de la carpeta:

- `diarios/`: un respaldo por corrida; se borran los que tienen más de `RESPALDO_DIAS` días.
- `mensuales/`: el primer respaldo de cada mes. **No se borran nunca**: es el histórico completo
  desde el inicio.
- `verificaciones/`: los informes de las pruebas de recuperación (evidencia).
- `registro.log`: una línea por cada respaldo o restauración.

**Copia fuera del equipo principal.** `RESPALDO_DIR` puede apuntar a un disco externo, a una carpeta
sincronizada con Google Drive u OneDrive, o a una carpeta de red del servidor de la sede. La ubicación
definitiva queda pendiente de lo que defina el Punto Estudiantil; mientras tanto, la carpeta por
defecto está dentro del proyecto y fuera de git.

> Los respaldos contienen datos personales. Guárdalos en un lugar con acceso restringido y nunca
> los subas a GitHub (`respaldos/` está en `.gitignore`).

## Comandos

Desde la carpeta del proyecto (donde está `docker-compose.yml`):

| Acción | Comando |
| --- | --- |
| Iniciar el servicio (la primera vez) | `mkdir -p respaldos && docker compose up -d respaldo` |
| Ver qué está haciendo | `docker compose logs respaldo --tail 20` |
| Respaldar ahora | `docker compose exec respaldo sh /scripts/respaldar.sh` |
| **Prueba de recuperación** (no toca el sistema) | `docker compose exec respaldo sh /scripts/verificar.sh` |
| Probar un respaldo específico | `docker compose exec respaldo sh /scripts/verificar.sh bd_2026-11.dump` |

## Prueba de recuperación

`verificar.sh` restaura el respaldo en una base **temporal**, compara las filas de cada tabla con
las que había al respaldar, revisa que el archivo de imágenes se pueda leer, guarda un informe en
`verificaciones/` y borra la base temporal. El resultado esperado es:

```
RESULTADO: RESPALDO RECUPERABLE (todas las tablas coinciden)
```

Conviene hacerla una vez al mes y cada vez que cambie algo en el servidor. El informe sirve de
evidencia para el proyecto.

## Restaurar el sistema desde un respaldo

**Reemplaza todos los datos actuales.** Antes de hacerlo, el script guarda el estado actual en
`diarios/antes_de_restaurar_….dump`, por si hay que volver atrás.

```bash
docker compose stop web
docker compose exec respaldo sh /scripts/restaurar.sh bd_2026-11-12_030000.dump --confirmo
docker compose start web
```

Las imágenes no se restauran desde el servicio de respaldo (lo monta en solo lectura para protegerlas).
Si también hay que recuperarlas:

```bash
docker compose exec -T web tar -xzf - -C /app/media < respaldos/diarios/media_2026-11-12_030000.tar.gz
```

## Si algo falla

- *"no se puede escribir en la carpeta de respaldos"*: la carpeta de `RESPALDO_DIR` no existe o no
  es de tu usuario. Créala con `mkdir -p` (sin `sudo`) o revisa `RESPALDO_UID` / `RESPALDO_GID`.
- *"no encontré el respaldo"*: todavía no hay respaldos; corre primero `respaldar.sh`.
- El servicio se reinicia solo (`restart: unless-stopped`), también después de reiniciar el
  computador, mientras Docker esté corriendo.
