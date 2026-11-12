# Punto Participa: aplicación Django

Esta carpeta contiene la aplicación. La documentación completa (pantallas, instalación, escáner,
seguridad y pruebas) está en el [README del repositorio](../../README.md).

## Puesta en marcha rápida

Desde esta carpeta (la que tiene `manage.py` y `docker-compose.yml`):

```bash
cp env.example .env          # en Windows: Copy-Item env.example .env
# edita .env y reemplaza los valores de ejemplo
mkdir -p respaldos
docker compose up -d --build
```

Luego abre <http://localhost:8000/login/>.

## Comandos de uso diario

| Si… | Ejecuta |
| --- | --- |
| Editaste un `.py`, `.html`, `.css` o `.js` | `docker compose restart web` y recarga con `Ctrl+Shift+R` |
| Hay una migración nueva | `docker compose exec web python manage.py migrate` (antes de reiniciar) |
| Cambiaste `.env` | `docker compose up -d --force-recreate web` |
| Cambiaste `Dockerfile`, `requirements.txt` o `entrypoint.sh` | `docker compose up -d --build` |
| Quieres correr las pruebas | `docker compose exec web python manage.py test --parallel --noinput` |
| Quieres ver errores | `docker compose logs web --tail 50` |

## Más documentación

| Archivo | Contenido |
| --- | --- |
| [`docs/CAMBIOS.md`](docs/CAMBIOS.md) | Historial de cambios, decisiones y checklist antes de producción |
| [`docs/GUIA_ESTILO.md`](docs/GUIA_ESTILO.md) | Colores, botones, íconos y filtros que usan todas las pantallas |
| [`respaldo/LEEME.md`](respaldo/LEEME.md) | Respaldo automático, prueba de recuperación y restauración |
| `env.example` | Todas las variables de entorno, con su explicación |

## Cuidado con los datos

- Nunca ejecutes `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`:
  borran la base de datos y las imágenes.
- Nunca ejecutes `seed_data` ni `perf_seed` en producción: crean usuarios con contraseñas conocidas
  y `--flush` borra datos.
- El archivo `.env` y la carpeta `respaldos/` nunca se suben a GitHub.
