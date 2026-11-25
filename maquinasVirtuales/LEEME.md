# Configuración de Docker

Esta carpeta tiene todo lo necesario para levantar Punto Participa con Docker. El código de la
aplicación está en `../src/punto_participa_project`.

| Archivo o carpeta | Para qué sirve |
| --- | --- |
| `docker-compose.yml` | Los cuatro servicios: `db` (PostgreSQL 16), `web` (Django con Gunicorn), `respaldo` y `tareas` |
| `Dockerfile` | Imagen de la aplicación (Python 3.12). Se construye con la raíz del repositorio como contexto |
| `Dockerfile.dockerignore` | Qué entra a la imagen: solo el código de `src/punto_participa_project` y `entrypoint.sh` |
| `entrypoint.sh` | Arranque del contenedor web: espera a la base, migra, reúne los estáticos e inicia Gunicorn |
| `env.example` | Plantilla de variables de entorno. La copia con los valores reales se llama `.env` y nunca se sube a GitHub |
| `respaldo/` | Scripts del respaldo automático y de la prueba de recuperación ([guía](respaldo/LEEME.md)) |
| `tareas/` | Ciclo diario del servicio `tareas` (retención de datos) |

## Uso

Todos los comandos se ejecutan desde esta carpeta:

```bash
cp env.example .env          # en Windows: Copy-Item env.example .env
# edita .env y reemplaza los valores de ejemplo
mkdir -p respaldos           # en Windows: mkdir respaldos
docker compose up -d --build
```

Luego abre <http://localhost:8000/login/>. Los comandos de uso diario están en la sección 5 del
[README del repositorio](../README.md).

## Datos

- La base de datos y las imágenes viven en los volúmenes `punto_participa_project_pgdata` y
  `punto_participa_project_media_volume`. El nombre fijo (`name:` en `docker-compose.yml`) hace que
  se usen los mismos volúmenes aunque la configuración cambie de carpeta.
- Nunca ejecutes `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`:
  borran la base de datos y las imágenes.
- `.env` y `respaldos/` nunca se suben a GitHub.
