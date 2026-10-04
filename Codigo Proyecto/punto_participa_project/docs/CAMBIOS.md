# Punto Participa — Registro de cambios

Plataforma web del Punto Estudiantil (Duoc UC, Sede Alameda) para gestionar actividades, inscripciones y asistencia.
Stack: Django 6.1 · PostgreSQL · Gunicorn · WhiteNoise · Docker.

> Ubicación sugerida: `docs/CAMBIOS.md`. La guía de instalación y uso de Docker está en `LEEME.md`.

**Marcas de estado usadas en este documento**

| Marca | Significado |
|---|---|
| `[CONFIRMADO]` | Aplicado y verificado funcionando |
| `[ENTREGADO – CONFIRMAR]` | El código se entregó, pero no hay confirmación de que se aplicó o se probó |
| `[PENDIENTE]` | Todavía no hecho |

---

## 0. Resumen ejecutivo

**Estado actual: listo para piloto interno. No está listo para producción abierta** (ver sección 11).

Funciona hoy: login con roles, dashboard, reportes con filtros y exportación, CRUD de actividades, inscripción pública a talleres, escáner de asistencia (RUT, QR, pasaporte), auditoría, gestión de usuarios, recuperación de contraseña y envío de invitaciones por correo. Todo corre en contenedores (Django + Gunicorn + PostgreSQL 16) con los datos reales ya migrados.

**Roles**

| Rol | Alcance |
|---|---|
| Administrador | Todo el sistema |
| Creador de Evento | Solo sus propias actividades y reportes |
| Encargado de Registrar | Solo el escáner de asistencia |

**Entregado en la última tanda pero sin confirmación de aplicación**

- Aviso de cambios sin guardar (`scripts.js`) — sección 7.3
- Sanitización de CSV/Excel — sección 7.5
- Envoltura IIFE de `dashboard.js` y `reportes.js` — sección 7.6
- `urls.py` corregido con favicon y `/media/` — sección 7.7
- `LOGGING` y flags de Gunicorn para ver errores — sección 9, problema 6
- `LEEME.md` actualizado

---

## 1. Cronología

| Fecha | Hito |
|---|---|
| 13/09/2026 | Frontend inicial y wireframes |
| 15/09/2026 | Proyecto Django base |
| 16/09/2026 | Recuperación de contraseña, carpeta `media` |
| 17/09/2026 | Middleware, templates de detalle, paginación |
| 19/09/2026 | Management commands, `permissions.py` |
| 23/09/2026 | Pruebas de performance |
| Previo a Docker | Refactor de permisos, 12 bugs corregidos, limpieza de código muerto, revisión de tests, incidente de datos sintéticos (sección 3) |
| 25/09/2026 | Dockerización y migración de datos (según los logs de Docker; el ZIP es del 27/09) |
| 27/09/2026 | ZIP "después del Docker" |
| 28/09/2026 | Ajustes posteriores a Docker (sección 7), refactor del formulario de actividad, suite de 228 tests y cobertura |

---

## 2. Fases iniciales (ZIPs)

### Fase 1 — Frontend inicial (13/09)
`puntopartida front.zip`: `index.html`, `css/styles.css`, `js/app.js` y 10 wireframes. Solo frontend estático, sin backend.

### Fase 2 — Proyecto Django base (15/09)
`punto_participa_project.zip`: proyecto `punto_participa`, app `gestion`, 19 migraciones.
Modelos: `Rol`, `UsuarioSistema`, `Alumno`, `Carrera`, `Jornada`, `Actividad`, `Inscripcion`, `Asistencia`, `NotificacionCorreo`, `LogAuditoria`.
Templates: `base`, `login`, `dashboard`, `actividad_list`, `escaneo`, `reportes`, `usuarios`. `tests.py` inicial.

### Fase 3 — Iteraciones intermedias (15–16/09)

| ZIP | Cambios |
|---|---|
| (2) | Migración 0020 (`filtro_aplicado`), `cambiar_contrasena.js` |
| (3) | Carpeta `punto_participa/` (settings, urls, wsgi, asgi), `manage.py`, `media/actividades/`, CSS consolidado en `styles.css` |
| (4) | Migración 0021 (`rol`), templates de recuperación de contraseña (`email_recuperacion`, `recuperar_contrasena`, `restablecer_contrasena`), `requirements.txt` |
| backup | Copia idéntica al ZIP (4) |
| (5) | Migración 0022 (unicidad de asistencia), `decorators.py`, `restablecer_contrasena.js` |

Impacto: flujo completo de recuperación de contraseña, permisos en decoradores e integridad de asistencias.

### Fase 4 — Refinamiento (17/09)

| ZIP | Cambios |
|---|---|
| (6) | `middleware.py` (`ForzarCambioContrasenaMiddleware`): obliga a cambiar la contraseña temporal |
| (7) | Templates `actividad_detalle`, `actividad_notificaciones`, `actividad_participantes`, `includes/paginacion`; `estructura.txt` |
| "antes de llenado de bbdd" | Copia idéntica al ZIP (7); punto de restauración antes de cargar datos |

### Fase 5 — Carga de datos (19/09)
ZIP (8): migración 0023 (`rut`), comando `seed_data`, `permissions.py`, `includes/orden_link.html`, `_nav_links.html`.

### Fase 6 — Performance (23/09)
`perf_seed.py` (seed masivo), resultados de carga (`dash_*.html`), archivos de cookies de las pruebas y un `.bak`. Resultados en la sección 3.4.

---

## 3. Sesión de refactor y correcciones (previa a Docker)

### 3.1 Refactor de permisos (Opción B)
- `gestion/permissions.py` (nuevo): centraliza `get_perfil()`, `tiene_rol()`, `puede_gestionar_actividad()` y las constantes de roles.
- `gestion/decorators.py`: reescrito para importar desde `permissions.py`, lo que eliminó el import circular con `views.py`. Suma soporte de `?next=` (volver a la página pedida tras el login) y protección anti-loop de redirecciones.
- `gestion/views.py`: sin funciones duplicadas, imports ordenados; `login_view()` respeta `next=` solo para rutas internas.
- `gestion/context_processors.py`: usa `get_perfil()` en vez de duplicar la lógica.
- Verificado con los 20 tests originales pasando en cada paso.

### 3.2 Bugs funcionales corregidos

| # | Bug | Corrección |
|---|---|---|
| 1 | `rut_limpio()` borraba las letras de los pasaportes (la regex solo conservaba dígitos y "K") | Conserva todas las letras |
| 2 | Columnas "Invit. OK" e "Invit. fallidas" vacías | Faltaba el `annotate()` en `lista_actividades()` |
| 3 | Botón "Eliminar" sin funcionalidad | Conectado a `eliminar_ajax` con confirmación y aviso |
| 4 | `ActividadAdmin` no recalculaba cupos | `save_model()` usa `recalcular_cupos()` |
| 5 | `_procesar_form_actividad()` solo manejaba errores de fecha vía AJAX; el navegador recibía HTML en vez de JSON | Maneja cualquier error de formulario |
| 6 | Horario roto en el correo de invitación | Un salto de línea dentro de un `{% if %}` dejaba `{{ ...|date:"H:i" }}` literal |

### 3.3 Bugs de CSS y diseño corregidos
1. `cambiar_contrasena.html` sin centrar (`.password-page` y `.password-card` sin CSS).
2. Modal de crear/editar actividad angosto (regla de ancho duplicada).
3. Columnas del formulario apiladas (faltaba `.form-2col` en la regla de grid).
4. Selector de carreras y jornadas sin contención: ahora con scroll interno.
5. Logos del login gigantes y apilados (`.brand-header` sin CSS), lo que también arregló recuperar y restablecer contraseña.
6. `actividad_form.html` con Bootstrap obsoleto: reescrito con las clases propias del sistema y el toggle de campos según tipo.

### 3.4 Datos sintéticos e incidente de rendimiento

**Incidente:** el dashboard quedaba cargando y aparecían errores de CSRF. Causa: una sesión con otra herramienta había generado 5.000 alumnos, 53.000 inscripciones y 100.000 asistencias **directamente en la base real** (unas 800 veces el volumen normal). Se limpió por el prefijo único `LOAD_ALAMEDA_` sin tocar datos legítimos.

**Lección:** ningún generador de datos de prueba debería poder correr contra la base real sin una confirmación explícita. `[PENDIENTE]` agregarlo a `perf_seed`.

**Mediciones** (con `perf_seed.py`, reversible):

| Escenario | Resultado |
|---|---|
| Línea base (66 alumnos) | ~0,12 s |
| 5.000 alumnos | ~0,4 s |
| 5.000 alumnos + 20 usuarios (runserver) | 0,27–2,65 s, sin errores |
| 5.000 alumnos + 50 usuarios (Waitress) | 0,69–4,11 s, 0% de errores |

La medición anterior de la otra herramienta (70% de errores) estaba contaminada por el volumen desproporcionado y por usar `runserver`.

> **Importante:** las mediciones se hicieron con **Waitress**. El contenedor usa **Gunicorn con 3 workers sync**. Esa combinación nunca se midió. `[PENDIENTE]` repetir la prueba contra el contenedor antes de producción.

### 3.5 Limpieza de código muerto
- Eliminados `eliminar_actividad()` (vista), su ruta y `actividad_confirm_delete.html`; el flujo AJAX ya cubría el caso.
- Eliminado el botón `#btnEnviarInvitaciones` sin funcionalidad.
- `scripts.js` cargado dos veces en algunos templates (causaba `SyntaxError` por variable ya declarada).
- Import sin usar en `admin.py`.

### 3.6 Mejoras funcionales
- Campo `cronograma` en el formulario de actividades (existía en el modelo pero no se editaba).
- Correo de invitación personalizado ("Hola Juan," en vez de "Estimada comunidad").
- Texto de ayuda de la inscripción pública: menciona que acepta RUT y pasaporte.

### 3.7 Revisión general
Revisados 21 templates, los archivos JavaScript, `settings.py`, `admin.py` y `requirements.txt` (Django 6.1 confirmado como versión estable real).

---

## 4. Tests

- **130 tests** iniciales: `tests.py` original más 5 archivos generados por otra herramienta (`tests_adicionales`, `tests_extremos`, `tests_integrales`, `tests_resistencia`, `tests_roles_completo`). Se revisaron a fondo: buena calidad, sin bugs, y cubren casos nuevos (concurrencia real con `ThreadPoolExecutor`, rollback transaccional, CSRF, límites de invitaciones, auto-bloqueo del administrador).
- **228 tests** actuales (+98): `tests_decorators_utils.py` (63) y `tests_views_criticas.py` (35).
- Modo test: `TESTING = 'test' in sys.argv` en `settings.py` para usar `StaticFilesStorage` en vez del storage con manifest.

| Archivo | Cobertura |
|---|---|
| context_processors.py | 100% |
| decorators.py | 98% |
| forms.py | 96% |
| middleware.py | 100% |
| models.py | 99% |
| permissions.py | 100% |
| urls.py | 100% |
| utils.py | 96% |
| views.py | 83% |
| **TOTAL** | **87%** |

Archivos: `.coveragerc`, `docs/coverage_report.txt`, `docs/htmlcov/`.

`[PENDIENTE]` volver a correr la suite completa tras los cambios de la sección 7 y agregar tests para `/favicon.ico`, `/media/`, el filtro de Escuela y `_sanitizar_celda`. Verificar además que el modo test sobrescriba `STORAGES["staticfiles"]` (Django 6.1 ignora `STATICFILES_STORAGE`).

---

## 5. Dockerización `[CONFIRMADO]`

### 5.1 Arquitectura

| Componente | Detalle |
|---|---|
| Imagen `web` | `python:3.12-slim`, dependencias del sistema (`build-essential`, `libpq-dev`, `gettext`), `pip install -r requirements.txt` |
| Servidor de aplicación | **Gunicorn**, 3 workers sync, `--timeout 60`, puerto 8000 (elegido por ser el estándar en Linux/Docker) |
| Base de datos | `postgres:16-alpine` con healthcheck (`pg_isready`) |
| Estáticos | WhiteNoise con `CompressedManifestStaticFilesStorage` |
| Volúmenes | `pgdata`, `static_volume`, `media_volume`, y el código montado en vivo (`.:/app`) |
| Puertos publicados | 8000 (web) y 5432 (Postgres, pensado para DBeaver o pgAdmin) |

Archivos: `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.dockerignore`.

`entrypoint.sh`: espera a Postgres, corre `migrate --noinput` y `collectstatic --noinput`, y arranca `gunicorn punto_participa.wsgi:application`. Corrige saltos de línea de Windows (`sed 's/\r$//'`) al construir la imagen.

**Variables de entorno (`.env`):** `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `SITE_URL`, `MAX_INVITACIONES_POR_ENVIO`.

`settings.py` lee `DEBUG` y `ALLOWED_HOSTS` con `config()` (antes estaban fijos como `DEBUG = True` y `ALLOWED_HOSTS = []`).

### 5.2 `requirements.txt` sincronizado
Se regeneró con `pip freeze` desde el venv y el `Dockerfile` ahora instala todo desde ese archivo (sin la línea aparte de `gunicorn` y `psycopg2-binary`).

`asgiref 3.12.1` · `certifi 2026.7.22` · `charset-normalizer 3.5.1` · `Django 6.1` · `django-ratelimit 4.1.0` · `et_xmlfile 2.0.0` · `gunicorn 26.2.0` · `idna 3.20` · `openpyxl 3.1.5` · `pillow 12.3.0` · `psycopg2-binary 2.9.12` · `python-decouple 3.8` · `requests 2.34.2` · `sqlparse 0.6.0` · `tzdata 2026.3` · `urllib3 2.8.0` · `waitress 3.0.2` · `whitenoise 6.12.0`

### 5.3 Migración de datos (PostgreSQL local → contenedor)
- Base: `punto_participa_db`, usuario `punto_user`. Postgres local **17.0** contra **16** del contenedor.
- `pg_dump -F c` falló al restaurar (`unsupported version (1.16)`). Se usó **formato SQL plano** (`-F p`) y `psql`.
- Los `ERROR: already exists` y `duplicate key` en tablas de Django son esperados (las migraciones ya las habían creado).
- Dos tablas de relación quedaron en cero por el orden del dump (`gestion_actividad_carreras` y `gestion_actividad_jornadas`, con foreign keys hacia tablas aún vacías). Se extrajeron sus bloques `COPY` a `fix_relaciones.sql` y se cargaron al final: 182 y 36 filas.
- Verificado: 11 usuarios cargados, login real funcionando, carreras (13) y jornadas (2) presentes.
- El procedimiento completo está en `LEEME.md`.

---

## 6. Detalle de la sesión de Docker: decisiones y correcciones

- Placeholder `nombre_proyecto` en `entrypoint.sh` reemplazado por `punto_participa` (Gunicorn no arrancaba).
- Se detectó que `settings.py` tenía las líneas de producción dentro de un bloque `"""..."""`. Las líneas `DEBUG` y `ALLOWED_HOSTS` quedaron activas fuera del bloque; el resto sigue como texto muerto (ver sección 11).
- WhiteNoise agregado en `MIDDLEWARE` (después de `SecurityMiddleware`) para servir los estáticos con `DEBUG=False`.

---

## 7. Ajustes posteriores a Docker

### 7.1 Reportes: filtro por Escuela `[CONFIRMADO]`
- Filtros en el orden pedido: Actividad · Escuela · Carrera · Jornada · Desde · Hasta. Botones Filtrar y Limpiar como íconos SVG (sin librerías externas) y distribuidos en una fila con `flex-wrap`.
- `_aplicar_filtros_reporte()` recibe `escuela`. Para actividades filtra por `carreras__escuela` (relación real); para asistencias filtra los alumnos cuya `carrera` (texto libre) pertenece a esa escuela. Las exportaciones Excel y CSV heredan el filtro porque usan el mismo helper.
- Contexto nuevo: `escuelas_opciones` y `escuela_seleccionada`.
- Los `<select>` llevan `autocomplete="off"` para que el navegador no restaure valores viejos.
- **Bug encontrado:** dentro de `reportes()`, un `for` reutilizaba el nombre `escuela` y pisaba el filtro, por lo que el select mostraba siempre la última escuela procesada. Renombrado a `escuela_item`.

### 7.2 Títulos de gráficos más explícitos `[CONFIRMADO]`
Dashboard: "Top 5 actividades con más asistentes", "Asistentes por carrera (top 6)", "Asistentes por escuela (top 6)", "Actividades programadas, en curso y finalizadas", "Inscritos vs. asistentes (top 10 actividades)".
Reportes: los gráficos por carrera y por jornada se distinguen entre pestañas con "(agregado)" y "(cruzado con escuela)" / "(detalle por actividad)".

### 7.3 Aviso de cambios sin guardar `[ENTREGADO – CONFIRMAR]`
`scripts.js`: `beforeunload` cuando el formulario de actividad (`#formActividad`) tiene cambios. La marca se limpia al guardar con éxito, al cargar otro formulario y al cerrar el modal.

### 7.4 Aviso de pérdida de conexión `[CONFIRMADO]`
Toast dedicado `#toast-conexion` (en `base.html`) con la clase `.toast-conexion`, para no pisarse con los mensajes normales. Se activa con los eventos `offline` y `online`, y también si la página carga sin conexión. Probado con DevTools en modo Offline.

### 7.5 Seguridad
- `sensitive_post_parameters` en `login_view`, `cambiar_contrasena`, `restablecer_contrasena` y `guardar_usuario`: oculta contraseñas en los reportes de error de Django `[CONFIRMADO]`.
- Sanitización de inyección de fórmulas en exportaciones (`_sanitizar_celda()`, aplicada en `_exportar_excel` y `_exportar_csv`): antepone un apóstrofe a textos que empiezan con `=`, `+`, `-`, `@` `[ENTREGADO – CONFIRMAR]`.
- Revisión de SQL crudo: sin `raw()`, `extra()` ni `cursor.execute()` en `views.py`, `models.py`, `forms.py`, `admin.py` y `utils.py`. Todo usa el ORM `[CONFIRMADO]`.
- Revisión de logs: no se encontraron contraseñas ni tokens en `logger` ni en `registrar_log()`.

### 7.6 JavaScript
`dashboard.js` y `reportes.js` declaraban las mismas constantes globales (`COLORES_FALLBACK`, `formatoNumero`). Envueltos en IIFE para que no choquen si algún día se cargan juntos `[ENTREGADO – CONFIRMAR]`.

### 7.7 Estáticos, media y favicon
- **Chart.js vendorizado** en `gestion/static/gestion/js/vendor/chart.umd.js` y cargado con `{% static %}` en `dashboard.html` y `reportes.html`. Ya no hay dependencia de jsDelivr `[CONFIRMADO]`. Versión: anotar con `Get-Content ... -TotalCount 3`, porque se actualiza a mano.
- **`STORAGES`** en `settings.py` con `CompressedManifestStaticFilesStorage`. Django 6.1 ignora `STATICFILES_STORAGE`, por lo que el manifest nunca había estado activo. Ahora los estáticos salen con hash y comprimidos `[CONFIRMADO]`.
- Se quitó el comentario `sourceMappingURL` de `chart.umd.js` porque apuntaba a un `.map` inexistente y hacía fallar `collectstatic`.
- **`/media/`**: con `DEBUG=False` nadie servía las imágenes de actividades (404). Se agregó una ruta con `django.views.static.serve` `[CONFIRMADO]`. Es aceptable para el piloto; para producción debería servirla Nginx.
- **`/favicon.ico`**: redirección temporal (302) al logo `[ENTREGADO – CONFIRMAR]`. Regla al editar `urls.py`: definir `favicon` **antes** de usarla y no importar dos cosas llamadas `static` (se usa el alias `static_url`).

### 7.8 Refactor del formulario de actividades (28/09, según el registro del proyecto)
1. Fecha y hora separadas: `fecha_inicio_fecha`, `fecha_inicio_hora`, `fecha_fin_fecha`, `fecha_fin_hora` (se combinan en `clean()` y `save()` con `timezone.make_aware()`; corrige el error `can't compare offset-naive and offset-aware datetimes`). Archivos: `forms.py`, `actividad_form.html`, `actividad_form_partial.html`, `scripts.js` (`combinarFechaHora()`), `styles.css` (sección 42, `.form-row-4`).
2. Label flotante en formularios (login, inscripción, escáner, cambiar y restablecer contraseña, usuarios, auditoría y actividad).
3. Select de tipo con "— Selecciona un tipo —".
4. Asterisco de obligatorio junto al label (sección 43 de `styles.css`).
5. Banner "Los campos marcados con * son obligatorios."

---

## 8. Incidente del dashboard con error 500 (28/09) `[CONFIRMADO]`

Causa: `dashboard.html` tenía **3 tags de Django partidos en dos líneas** (`{%` en una línea y `endif %}` en otra), en las tasas de masivas y talleres y en los cupos de la tabla, además de comparaciones sin espacios (`rango_actual=='hoy'`). Un tag de Django no puede partirse entre líneas, así que quedaba un `{% if %}` sin cerrar (`TemplateSyntaxError`).

Se sospecha que el causante es el formateador automático del editor. Es el mismo tipo de error del bug 6 de la sección 3.2. Se entregó el `dashboard.html` corregido.

Aclaración de URL: el dashboard vive en `http://localhost:8000/`, no en `/dashboard/`.

---

## 9. Problemas conocidos y cómo se resolvieron

| # | Problema | Solución |
|---|---|---|
| 1 | Un `$` en la `SECRET_KEY` del `.env` hace que Docker Compose lo tome como variable y la trunque (aviso `The "zy6" variable is not set`) | Escribir cada `$` como `$$` en el `.env`. Solo aplica a Docker Compose |
| 2 | El formateador del editor parte tags de Django y quita espacios de los `==` | Desactivar "Format on Save" para HTML o usar el modo "Django HTML" |
| 3 | `STATICFILES_STORAGE` no hace nada en Django 5.1 en adelante | Usar el diccionario `STORAGES` |
| 4 | `collectstatic` falla si un `.js` referencia un `.map` que no existe | Quitar el comentario `sourceMappingURL` del archivo vendorizado |
| 5 | Un `for` pisa una variable de la vista con el mismo nombre (`escuela`) | Nombres distintos para variables de bucle |
| 6 | Con `DEBUG=False` no se ven ni los requests de Gunicorn ni los tracebacks de un 500 en `docker compose logs`. `[PENDIENTE]` aplicar | Agregar `LOGGING` (handler de consola para `django.request`) en `settings.py` y `--access-logfile - --error-logfile -` en `entrypoint.sh` |
| 7 | Con `DEBUG=False` nadie sirve `/media/` | Ruta con `serve` en `urls.py` (Nginx en producción) |
| 8 | `pg_restore` no lee dumps de un Postgres más nuevo | Formato SQL plano con `psql` |
| 9 | El navegador restaura el valor previo de un `<select>` e ignora el `selected` del servidor | `autocomplete="off"` |
| 10 | El contenedor `web` a veces falla al arrancar con `the database system is starting up` (aparece en los logs de reinicios) y se recupera solo. El chequeo del `entrypoint.sh` solo verifica que el puerto esté abierto, no que Postgres acepte conexiones | `[PENDIENTE]` reemplazar por un reintento de `migrate` o una conexión real |
| 11 | `docker compose restart` **no relee el `.env`** | Usar `docker compose up -d --force-recreate` o `down` y `up` |

---

## 10. Seguridad y privacidad

### 10.1 Análisis de una lista externa de recomendaciones
- **Token de recuperación ligado al usuario, con vencimiento y de un solo uso:** ya resuelto. `PasswordResetTokenGenerator` de Django ata el token al usuario, expira y se invalida al cambiar la contraseña.
- Aviso de cambios sin guardar y detección de desconexión: implementados (7.3 y 7.4).
- Drag & drop de imágenes, limpieza de EXIF y auditoría de logs: ver backlog y 7.5.

### 10.2 Riesgos por tipo de archivo (para el importador)
Imágenes: extensión o tipo MIME falsos, "decompression bomb", archivos políglotas, EXIF malicioso. Excel y CSV: inyección de fórmulas, `.xlsx` como zip bomb, archivos con millones de filas. Mitigaciones: validar el contenido real y no la extensión, limitar el tamaño, procesar por streaming, sanitizar fórmulas y **no guardar los archivos importados en `media/`** (esa carpeta se sirve sin login).

### 10.3 Inventario de terceros

| Tercero | Datos que recibe | Finalidad | Observación |
|---|---|---|---|
| Google (Gmail SMTP) | Correo y nombre del alumno, datos de la actividad; usuario, correo y enlace de recuperación de los funcionarios | Invitaciones y recuperación de contraseña | El remitente es una cuenta Gmail **personal**, sin contrato de tratamiento de datos. Migrar a una cuenta institucional |
| jsDelivr | — | Ya no se usa (Chart.js local) | Eliminado |
| Hosting de producción | Potencialmente toda la base | Alojar la aplicación | A definir; será "encargado del tratamiento" |
| Docker Hub / PyPI | Nada de usuarios | Build | No aplica |

No hay Analytics, fuentes externas ni otras APIs. Las únicas cookies son las de sesión y CSRF (esenciales, sin banner de consentimiento).

### 10.4 Marco legal (a verificar)
Rige la Ley 19.628. La Ley 21.719 tenía vigencia prevista para el 1/12/2026, pero el 1/09/2026 el Gobierno ingresó un proyecto para postergarla a diciembre de 2027. **Verificar el estado actual antes de decidir plazos.** Para producción con datos reales, conviene revisión del área legal de Duoc.

---

## 11. Checklist antes de producción

**Secretos**
- [ ] Rotar `SECRET_KEY`, contraseña de la base de datos y credenciales de correo (quedaron expuestas en conversaciones).
- [ ] `.env` fuera del repositorio y de la imagen.

**Seguridad de Django**
- [ ] `DEBUG=False` y `ALLOWED_HOSTS` reales (el valor por defecto es `midominio.com`).
- [ ] Activar HTTPS: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS y `CSRF_TRUSTED_ORIGINS`. Hoy están dentro del bloque de texto muerto de `settings.py`.
- [ ] Reactivar el rate limiting (`RATELIMIT_ENABLE = False` hoy, con sus checks silenciados). Detrás de un proxy, la clave `ip` debe usar la IP real del cliente. Verificar `createcachetable`.
- [ ] Limpiar el bloque `"""..."""` sobrante al final de `settings.py`.
- [ ] Confirmar `EMAIL_BACKEND`: en el `settings.py` revisado estaba en modo consola (no envía correos).
- [ ] Cuenta de correo institucional.

**Docker y despliegue**
- [ ] Compose de producción: sin el volumen `.:/app`, sin publicar el puerto 5432.
- [ ] Ejecutar el contenedor como usuario no root (hoy corre como root; pip lo advierte).
- [ ] Reintento robusto de conexión a la base al arrancar (problema 10).
- [ ] Usar la misma versión de PostgreSQL en desarrollo y producción (hoy 17 local contra 16 del contenedor).
- [ ] Nginx (o equivalente) delante, sirviendo `/static/` y `/media/`.
- [ ] Repetir la prueba de carga contra Gunicorn (sección 3.4).

**Datos**
- [ ] Respaldos programados de la base **y** del volumen `media_volume`. `docker compose down -v` borra ambos.
- [ ] Excluir de ZIPs, imagen y repositorio: `*.sql`, `*.dump`, `cookies*.txt`, `dash_*.html`, `*.bak`, `.coverage`, `docs/htmlcov/` (los dumps contienen RUT, nombres y correos reales).
- [ ] Política de Privacidad y consentimiento en la inscripción pública.
- [ ] Definir el borrado o anonimización de datos.

**Calidad**
- [ ] Suite completa de tests en verde y cobertura recalculada.
- [ ] Usar Git (los ZIPs numerados, los `.bak` y las copias duplicadas indican que hoy el versionado es manual).

---

## 12. Observaciones a verificar

1. **"Inscritos" en Reportes.** En `reportes()`, el total de inscritos se calcula con `Inscripcion.filter(alumno__in=alumnos_ids)`, donde `alumnos_ids` son los alumnos **que asistieron**. Sin filtros, eso cuenta solo inscripciones de quienes asistieron y subestima la cifra. Revisar si es lo deseado.
2. **Desglose por tipo y filtro de Escuela.** `_construir_desglose_tipo()` recibe `carrera` y `jornada`, pero no `escuela`. Con el filtro de Escuela activo, los inscritos a talleres podrían no reflejarlo.
3. **Chips de filtros activos.** La condición del bloque de chips en `reportes.html` no incluye `escuela`, así que ese filtro no genera chip.
4. **CSS duplicado.** `.filters-bar`, `.filter-group` y `.filter-actions` están definidas dos veces en `styles.css` (secciones 2 y 8). La segunda pisa parte de la primera. Funciona, pero conviene unificarlas.
5. **`waitress`** sigue en `requirements.txt` aunque el contenedor usa Gunicorn (útil solo para correr local en Windows).

---

## 13. Backlog (de menor a mayor complejidad)

**Baja**
1. Confirmar y aplicar los ítems `[ENTREGADO – CONFIRMAR]` y el `LOGGING`.
2. Chip de filtro activo para Escuela y resto de observaciones (sección 12).
3. Tabla de minimización de datos. Candidato claro: `ip_address` y `user_agent` de `LogAuditoria`.

**Media**
4. Drag & drop de imágenes (ya existe `#drop-area`, que hoy solo abre el selector).
5. Eliminar metadatos EXIF de `Actividad.imagen` con Pillow.
6. Política de Privacidad y checkbox de consentimiento; luego Términos y Condiciones. El banner de cookies no aplica mientras solo haya cookies esenciales.

**Alta (requieren diseño previo)**
7. Derecho al olvido: anonimizar en vez de borrar en cascada, para conservar el historial de inscripciones y asistencias que alimenta los reportes.
8. Importador de alumnos desde Excel/CSV. Nueve decisiones abiertas: estado o bloqueo, separación de nombre y apellido, mapeo de jornada, matching de carrera, formato de RUT, comparación de cambios, filas inválidas, y el impacto de alumnos bloqueados en el resto del sistema.

**Muy alta (arquitectura)**
9. Soporte multi-sede, cola de tareas para correos masivos (hoy se envían dentro del request) y escala nacional (~112.000 estudiantes).

---

## 14. Comandos de uso diario

| Si cambiaste… | Ejecutá |
|---|---|
| `.py` o template `.html` | `docker compose restart web` |
| `.js` o `.css` | `docker compose restart web` (regenera el hash de los estáticos) |
| `requirements.txt`, `Dockerfile` o `entrypoint.sh` | `docker compose down`, `build`, `up` |
| `.env` | `docker compose up -d --force-recreate` |

Ver errores y logs: `docker compose logs -f web`. Crear superusuario: `docker compose exec web python manage.py createsuperuser`.

---

## 15. Estructura de referencia

```
manage.py
Dockerfile · docker-compose.yml · entrypoint.sh · .dockerignore · .env
requirements.txt · LEEME.md · .coveragerc
punto_participa/        settings.py · urls.py · wsgi.py · asgi.py
gestion/
  models.py · views.py · forms.py · admin.py · urls.py
  utils.py · permissions.py · decorators.py · middleware.py · context_processors.py
  tests*.py
  management/commands/  seed_data.py · perf_seed.py
  templates/gestion/    (base, login, dashboard, reportes, actividad_*, escaneo, usuarios, ...)
  static/gestion/       css/styles.css · js/*.js · js/vendor/chart.umd.js · img/
media/actividades/      (volumen Docker)
docs/                   CAMBIOS.md · coverage_report.txt · htmlcov/
```
16. Sesión posterior (01/10/2026) — bugs del formulario de actividad, observabilidad y limpieza
16.1 Cadena de bugs en el formulario de Crear/Editar Actividad [CONFIRMADO]

Reportado como "no guarda imágenes nuevas al editar". La investigación encontró 4 causas encadenadas, no una sola:

Fechas no se prellenaban al editar. forms.py declaraba los 4 campos (fecha_inicio_fecha, fecha_inicio_hora, fecha_fin_fecha, fecha_fin_hora) sin fijar input_formats/format. Con LANGUAGE_CODE='es-es', Django formateaba la fecha como 28/09/2026, que el <input type="date"> del navegador no reconoce (exige AAAA-MM-DD) y descarta en silencio. Corregido fijando input_formats=['%Y-%m-%d'] / format='%Y-%m-%d' (y %H:%M para hora) en los 4 campos, sin depender del idioma configurado.
Checkboxes de Carreras/Jornadas se veían vacíos tras un reintento fallido. El template comparaba carrera.id in form.carreras.value: la primera carga compara enteros contra enteros (funciona), pero tras un POST inválido form.carreras.value vuelve como lista de strings — 24 in ["24", "15"] da False aunque sean "la misma" carrera. Visualmente parecía que el formulario "perdía" todo lo marcado. Corregido en actividad_form_partial.html comparando ambos lados con stringformat:"s" dentro de un {% with %} que captura form.carreras.value/form.jornadas.value una sola vez.
Imagen actual no se mostraba al editar. El #preview-container siempre estaba vacío al abrir el formulario de edición, sin forma de saber si la actividad ya tenía imagen. Corregido agregando una miniatura condicional ({% if form.instance.imagen %}) con la imagen guardada y una nota de que solo hace falta subir una nueva si se quiere reemplazar.
Causa raíz real de "no guarda nada, imagen incluida". La validación "la fecha de inicio no puede ser en el pasado" comparaba self.instance.fecha_inicio == fecha_inicio con precisión de microsegundos. Como fecha_inicio se reconstruye desde los campos separados (siempre en :00.000000) y el valor guardado en BBDD podía diferir en segundos/microsegundos, la comparación de "¿la fecha no cambió?" casi nunca era True — así que cualquier edición de una actividad con fecha ya pasada (algo común en un sistema con meses de datos reales) disparaba el error y Django rechazaba todo el formulario, incluida la imagen. Corregido comparando ambos datetimes truncados a minuto (.replace(second=0, microsecond=0)).

Las cuatro correcciones se verificaron en conjunto sobre la actividad de prueba id=98: fechas, horas, carreras, jornadas e imagen ya se conservan correctamente al editar.

16.2 Botón "+ Crear la primera" (estado vacío) sin reacción [CONFIRMADO]

El botón del estado vacío (cuando un Creador de Evento nuevo no tiene actividades propias) tenía id="btnNuevaActividadVacio", distinto al id="btnNuevaActividad" que escuchaba scripts.js. El click no disparaba nada, sin generar ningún error en consola ni petición de red — diagnosticado inspeccionando el HTML real del botón, ya que el comportamiento era indistinguible de un error silencioso de permisos. Corregido uniendo ambos ids en la misma condición del listener.

Nota para diagnóstico futuro: "sin red, sin consola, sin reacción" ante un click casi siempre significa que el selector del listener no coincide con el elemento real — revisar el id/clase exacto antes de sospechar de lógica de permisos o backend.

16.3 Cierre de modal sin aviso de cambios sin guardar [CONFIRMADO]

El botón X del modal de actividad ([data-modal-close]) cerraba siempre sin preguntar, aunque hubiera cambios sin guardar. Causa: listener duplicado — el bloque de cierre existía dos veces en scripts.js (uno en la sección de modales, sin aviso; otro agregado después en la sección de mensajes, con el confirm(...)). Ambos escuchaban el mismo evento; el primero cerraba el modal antes de que el segundo llegara a preguntar. Corregido eliminando el bloque duplicado y dejando solo el que incluye el confirm() condicionado a modal.id === 'actividadModal' && formActividadModificado.

16.4 Avisos de campo obligatorio en rojo [CONFIRMADO]

Los mensajes de validación de carreras/jornadas/cupos (tipo 'warning') se mostraban con el color por defecto del toast en vez de rojo. Corregido en mostrarMensaje(): la condición de clase .error ahora incluye tipo === 'warning' además de 'danger'/'error'.

16.5 LOGGING y flags de Gunicorn [CONFIRMADO]

Pendiente desde que un 500 en dashboard.html (sesión previa) no dejó ningún rastro en docker compose logs por tener DEBUG=False. Resuelto con dos cambios:

settings.py: bloque LOGGING con handler de consola para el logger django.request (nivel ERROR), que ahora vuelca el traceback completo de cualquier excepción no manejada a los logs del contenedor sin necesitar DEBUG=True.
entrypoint.sh: agregados --access-logfile - y --error-logfile - al comando de Gunicorn, para que registre cada request (método, ruta, código de respuesta, referer, user-agent) en stdout.

Verificado en vivo: docker compose logs -f web ya muestra una línea de acceso por cada navegación.

16.6 Dockerfile: resiliencia ante redes que bloquean HTTP [CONFIRMADO]

Durante la migración a un segundo computador (ver sección 10), una red con restricciones bloqueaba el puerto 80 hacia los repositorios de Debian (403 Forbidden en apt-get update). En esa ocasión el problema se sorteó cambiando a datos móviles, sin aplicar el fix. Se decidió dejarlo aplicado de forma preventiva:

dockerfile
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gettext \
    && rm -rf /var/lib/apt/lists/*

Reescribe las URLs de los repositorios a HTTPS (puerto 443) antes de instalar paquetes, ya que ese puerto suele estar permitido incluso en redes restrictivas. Verificado con docker compose build --no-cache: el log de apt-get muestra explícitamente Hit:1 https://deb.debian.org/..., confirmando que la reescritura se aplica.

Detalle operativo: tras editar el Dockerfile, si un primer intento de rebuild muestra el mismo tamaño de archivo (992B) en vez del esperado tras el cambio, el archivo no llegó a guardarse antes del build — verificar con Get-Content Dockerfile y, si hace falta forzar que Docker ignore cualquier capa cacheada de un build previo, usar docker compose build --no-cache.

16.7 Chip de filtro activo para "Escuela" en Reportes [CONFIRMADO]

La fila de "Filtros activos" no se mostraba cuando el único filtro aplicado era Escuela, porque la condición {% if request.GET.actividad or ... %} no incluía ese parámetro. Corregido: agregado request.GET.escuela a la condición, y agregado el chip individual correspondiente (mismo patrón que los demás: muestra el valor y permite quitarlo sin afectar el resto de los filtros activos).

16.8 CSS duplicado de filtros [CONFIRMADO]

.filters-bar, .filter-group y .filter-actions estaban definidos dos veces en styles.css (sección 2, cerca del header, y sección 8, "FILTROS"). Por orden de cascada, la sección 8 era la que realmente se aplicaba; la sección 2 era código muerto. Eliminado el bloque duplicado de la sección 2, dejando una sola fuente de verdad. Verificado visualmente: sin cambios en la apariencia de los filtros (confirma que la sección 8 ya mandaba).

16.9 Revisión de minimización de datos (models.py)

Análisis campo por campo de Alumno, UsuarioSistema, LogAuditoria y NotificacionCorreo:

Alumno.rut: confirmado que debe permanecer en texto plano, no hashearse — el sistema necesita mostrarlo en pantalla y buscarlo con múltiples formatos (con/sin puntos, con/sin guion), algo que un hash no permite.
LogAuditoria.user_agent: candidato a eliminar o reducir a una categoría simple (móvil/escritorio) — hoy guarda el string completo del navegador sin que se le vea uso real en el sistema.
LogAuditoria.ip_address: mantener, pero definir una política de retención (purga tras 6–12 meses) en vez de conservarlo indefinidamente.
LogAuditoria.cambios_json: campo declarado pero nunca poblado por ningún registrar_log() actual — decidir si se implementa su uso o se elimina.
UsuarioSistema.rut: ya es opcional en el modelo (null=True, blank=True) con fallback automático; revisar si aporta algo más allá de "parecerse" al alumno.
Resto de campos de Alumno (nombres, apellidos, correo, carrera, jornada) y de NotificacionCorreo: confirmados como obligatorios, con uso funcional directo y verificable en el código (escáner, invitaciones, reportes).

[PENDIENTE] decidir e implementar las acciones sobre user_agent, ip_address y cambios_json; documentar la política de retención resultante en la Política de Privacidad.

17. Backlog actualizado (tras la sesión del 01/10/2026)

Media complejidad

Drag & drop real de imágenes en el formulario de actividad (hoy #drop-area solo abre el selector de archivos al hacer click, sin manejar el evento drop)
Limpiar metadatos EXIF de Actividad.imagen con Pillow
Política de Privacidad + checkbox de consentimiento en inscripción pública (incorporar los hallazgos de minimización de datos, sección 16.9)
Migrar el envío de correos de la cuenta Gmail personal a una institucional

Alta complejidad

Derecho al olvido / borrado de datos (conecta con la política de retención de ip_address de logs)
Importador de alumnos desde Excel/CSV (9 decisiones de diseño sin resolver)

Muy alta complejidad

Evolución arquitectónica: multi-sede, cola de tareas para correos masivos, escala nacional

En curso

Pruebas vista por vista: completadas Dashboard, Reportes y el formulario de Actividad (con los bugs de la sección 16.1–16.4 ya resueltos). Pendientes: lista de actividades, detalle de actividad, participantes, notificaciones, escáner, usuarios, auditoría.

Observaciones sin verificar, siguen abiertas

El KPI "Inscritos" en Reportes podría estar subcontando (solo cuenta inscripciones de alumnos que también asistieron)
El desglose por tipo (masivas/talleres) no aplica el filtro de Escuela
