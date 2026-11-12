

# Punto Participa

Plataforma web para la gestión de actividades, talleres, inscripciones y control de asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

---

## 1. Descripción del proyecto

Hoy el registro de participación se hace en planillas Excel con macros que se trasladan a mano, lo que dificulta centralizar la información, controlar el acceso, resguardar los datos y generar historial. Además, los talleres con cupos limitados usan formularios externos, y los estudiantes no pueden ver las vacantes en tiempo real.

**Punto Participa** reemplaza esos procesos por una plataforma única que permite gestionar:

* Actividades masivas.
* Talleres con cupos limitados.
* Actividades con invitación, con lista cargada en Excel o CSV y acompañantes.
* Inscripciones de estudiantes.
* Registro de asistencia, con turnos de operador y contador en vivo.
* Usuarios y roles.
* La nómina de alumnos y su historial de participación.
* Los catálogos de lugares, escuelas y carreras.
* Reportes de participación y exportaciones a Excel y CSV.
* Auditoría de acciones.
* Respaldo automático de la base de datos.

El registro de asistencia se puede hacer digitando el RUT, leyendo el código QR de la cédula de identidad o leyendo el código de barras que muestra la aplicación Vivo Duoc.

### Perfiles

El sistema tiene **tres roles con cuenta de usuario**:

| Rol | Qué puede hacer |
| --- | --- |
| **Administrador** | Acceso completo: usuarios y roles, alumnos, catálogos, actividades de todos los creadores, reportes, auditoría y registro de asistencia. |
| **Creador de Evento** | Crea y gestiona sus propias actividades y talleres, envía invitaciones por correo, consulta y exporta los reportes de sus actividades y registra asistencia. |
| **Encargado de Registrar** | Solo registra la asistencia presencial, desde la pantalla del escáner. |

El registro de asistencia en el escáner está disponible para los tres roles; el Encargado de Registrar solo tiene acceso a esa pantalla.

Los **estudiantes no tienen cuenta**: consultan los talleres disponibles y se inscriben con su RUT desde el formulario público de inscripción. En las actividades con invitación responden desde un enlace personal que les llega por correo.

---

## 2. Estado del proyecto

El proyecto está en desarrollo y funciona de punta a punta en un entorno local con Docker. Hoy se encuentra en etapa de pruebas internas y **todavía no está publicado en un servidor de producción**. La entrega está fijada para el 1 de diciembre de 2026.

* Suite de pruebas automatizadas: 666 tests (detalle en la sección 9).
* Despliegue en la nube: **por definir**. Actualmente se ejecuta en local con Docker.
* El historial detallado de cambios está en [`docs/CAMBIOS.md`](Codigo%20Proyecto/punto_participa_project/docs/CAMBIOS.md) y la guía de estilo de las pantallas en [`docs/GUIA_ESTILO.md`](Codigo%20Proyecto/punto_participa_project/docs/GUIA_ESTILO.md).

---

## 3. Pantallas

| Pantalla | Para qué sirve | Roles |
| --- | --- | --- |
| **Inicio** | Resumen del período: actividades en curso, talleres con cupos, inscritos, asistencias del día, invitaciones enviadas, alertas y gráficos. | Administrador, Creador |
| **Actividades** | Crear, editar y eliminar actividades y talleres, con buscador y filtros. El lugar se elige de una lista; si es una sala, se pide su número (por ejemplo, 1203). Desde aquí se envían las invitaciones por correo. Tipos: masiva, taller y con invitación (sección 3.2). | Administrador, Creador |
| **Detalle de actividad** | Datos de la actividad y el recorrido de la participación: invitados, inscritos, asistieron y no asistieron, con la lista de quienes se inscribieron y no fueron. En las actividades con invitación: invitados, confirmados, rechazados, sin responder, entraron y acompañantes. | Administrador, Creador |
| **Invitados** | Lista de una actividad con invitación: carga del Excel o CSV con vista previa, estado de cada invitado y sus acompañantes, enlace personal para copiar, envío de las invitaciones y quitar a quien aún no entra. | Administrador, Creador |
| **Reportes** | Gráficos y tablas por actividad o por escuela y carrera, con filtros por actividad, tipo, lugar, escuela, carrera, jornada y fechas. Menú **Exportar** con tres reportes en Excel o CSV (sección 3.1). | Administrador, Creador |
| **Usuarios** | Crear y editar cuentas, asignar el rol y bloquear el acceso, con buscador. | Administrador |
| **Alumnos** | Directorio de la nómina con buscador; ficha de cada alumno con su historial de participación; bloqueo manual con motivo. Desde aquí se importa la nómina en Excel o CSV. | Administrador |
| **Catálogos** | Lugares, escuelas (con su color para los gráficos) y carreras: agregar, renombrar, bloquear y eliminar lo que no se usa. | Administrador |
| **Escáner** | Registro de asistencia por turnos, con contador en vivo (sección 6). | Los tres roles |
| **Auditoría** | Registro de todas las acciones del sistema, con filtros y exportación. | Administrador |
| **Páginas públicas** | Inscripción a talleres, página de las actividades masivas, respuesta a una invitación (`/invitacion/<enlace>/`) y Política de Privacidad. | Sin cuenta |

### 3.1 Exportaciones

Todas usan los filtros aplicados en Reportes, y cada descarga queda registrada en la auditoría. El Creador de Evento solo exporta sus propias actividades.

| Reporte | Contenido |
| --- | --- |
| **Resumen por actividad** | Una fila por actividad: tipo, estado, inicio y término, lugar, creador, cupos, invitados, inscritos, asistentes, no asistieron, porcentaje de asistencia y acompañantes. |
| **Participación por escuela y carrera** | Inscritos, asistentes y no asistieron por actividad, escuela, carrera y jornada. |
| **Listado de participantes** | Cada alumno con su inscripción y su asistencia (hora, método y quién la registró). En las actividades con invitación incluye a los acompañantes, y la columna **Participa como** dice si es invitado, agregado en la entrada o acompañante. Contiene datos personales. |
| **Todo en un Excel** | Los tres anteriores, cada uno en su hoja. |

En Excel las fechas son fechas reales, el encabezado queda fijo, tiene autofiltro y trae una hoja **Información** con la fecha, el usuario, los filtros usados y qué significa cada columna. Los CSV usan `;` y coma decimal para abrirse directo en el Excel en español.

La escuela, la carrera y la jornada de cada inscripción y asistencia son las que el alumno tenía **en ese momento**: si después se cambia de carrera o llega una nómina nueva, el historial no cambia.

En las actividades con invitación, los reportes cuentan como **inscritos** a los invitados que confirmaron y como **asistentes** a los que entraron (invitados y agregados en la entrada). Los acompañantes van en su propia columna y no suman a la asistencia de alumnos.

### 3.2 Actividades con invitación

Son actividades cerradas, para una lista de alumnos que define quien las crea. No tienen página pública ni cupo total.

1. Al crear la actividad se elige el tipo **Con invitación** y cuántos acompañantes puede llevar cada invitado (de 0 a 10, el mismo número para todos).
2. En la pantalla **Invitados** se sube la lista en Excel o CSV con las columnas `rut`, `nombres`, `carrera` y `correo` (`jornada` es opcional). Hay una plantilla para descargar. Antes de guardar se muestra una vista previa con los avisos y errores por fila: RUT con dígito verificador incorrecto, RUT repetidos y alumnos bloqueados son errores; un alumno que no está en la nómina o con otra carrera se carga igual, con aviso.
3. Se envían las invitaciones por correo: a quienes todavía no la recibieron, o también a quienes no han respondido. Cada invitado recibe un **enlace personal**, que también se puede copiar desde la pantalla para mandarlo por otro medio.
4. El alumno abre el enlace, confirma o rechaza, y registra a sus acompañantes con RUT o pasaporte y nombre. Debe aceptar la Política de Privacidad. Puede cambiar su respuesta hasta que empiece la actividad; después el enlace queda solo para consulta.
5. En la entrada se usa el escáner de siempre (sección 6). Un acompañante se registra con su propio documento.

Si llega alguien que no está en la lista, el escáner ofrece agregarlo: un alumno de la nómina entra como invitado **agregado en la entrada**, y una persona externa entra como acompañante de un invitado que tenga cupo libre. Los datos de invitados y acompañantes se guardan el mismo tiempo que el resto de la información del sistema.

---

## 4. Tecnologías

| Tecnología | Uso |
| --- | --- |
| **HTML, CSS y JavaScript** | Interfaces web (Chart.js para los gráficos, incluido en el proyecto) |
| **Python 3.12** | Backend |
| **Django 6.1** | Framework del backend |
| **PostgreSQL 16** | Base de datos |
| **Gunicorn** | Servidor de aplicación |
| **WhiteNoise** | Entrega de archivos estáticos |
| **openpyxl** | Lectura de la nómina y exportaciones a Excel |
| **Docker y Docker Compose** | Ejecución reproducible del sistema |
| **Git y GitHub** | Control de versiones y repositorio |

---

## 5. Cómo ejecutar el proyecto localmente

### Requisitos

* Docker instalado y en ejecución ([Docker Desktop](https://www.docker.com/products/docker-desktop/) en Windows y macOS; Docker Engine con el plugin Compose en Linux).
* Git.

No hace falta instalar Python ni PostgreSQL: todo corre dentro de contenedores.

### Pasos

1. **Clonar el repositorio y entrar a la carpeta del proyecto Django:**

   ```bash
   git clone https://github.com/Gegs-12358/Punto_Participa.git
   cd Punto_Participa/"Codigo Proyecto"/punto_participa_project
   ```

2. **Crear el archivo `.env`** en esa carpeta (junto a `manage.py`) copiando la plantilla incluida en el repositorio:

   ```bash
   cp env.example .env              # Linux y macOS
   Copy-Item env.example .env       # Windows (PowerShell)
   ```

   Luego abre `.env` y reemplaza los valores de ejemplo. El archivo `.env` nunca se sube al repositorio. Variables principales:

   | Variable | Qué es |
   | --- | --- |
   | `SECRET_KEY` | Clave secreta de Django (64 caracteres alfanuméricos aleatorios). |
   | `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Nombre, usuario y clave de la base de datos. PostgreSQL los toma de aquí al crearse. |
   | `DB_HOST`, `DB_PORT` | Los define `docker-compose.yml` dentro de Docker; en la plantilla quedan solo como referencia. |
   | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Cuenta de correo y su clave de aplicación para enviar correos. |
   | `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | Por defecto los correos se imprimen en los registros (`docker compose logs web`). Para enviarlos de verdad se activa el SMTP (ver `env.example`). |
   | `SITE_URL` | Dirección base del sistema, usada en los enlaces de los correos. |
   | `MAX_INVITACIONES_POR_ENVIO` | Máximo de invitaciones por envío. |
   | `DEBUG`, `ALLOWED_HOSTS` | Modo de depuración y dominios permitidos. |
   | `RESPALDO_DIR`, `RESPALDO_CADA_HORAS`, `RESPALDO_DIAS`, `RESPALDO_UID`, `RESPALDO_GID` | Dónde, cada cuánto y por cuánto tiempo se guardan los respaldos (sección 5.1). |
   | `CSRF_TRUSTED_ORIGINS`, `SECURE_*`, `USAR_PROXY_HTTPS` | Solo para producción con dominio y HTTPS; vienen comentadas en la plantilla. |

   Reglas para los valores:

   * Sin comillas, sin espacios (tampoco al final de la línea) y **sin el signo `$`**: Docker Compose lo interpreta como variable y rompe la clave.
   * Usa claves largas y aleatorias, distintas para cada integrante, y nunca las compartas por chat ni las subas a GitHub.

3. **Construir y levantar el sistema:**

   ```bash
   mkdir -p respaldos               # carpeta de los respaldos (en Windows: mkdir respaldos)
   docker compose up -d --build
   ```

   La primera vez demora, porque descarga las imágenes. Al arrancar, el contenedor espera a PostgreSQL, aplica las migraciones, crea la tabla de caché del límite de intentos, reúne los archivos estáticos e inicia Gunicorn.

4. **Abrir el sistema** en el navegador: <http://localhost:8000/login/>

5. **Datos de prueba (opcional, solo en local):** `docker compose exec web python manage.py seed_data` crea usuarios, alumnos, catálogos y actividades inventadas. **Nunca lo ejecutes en producción**: crea usuarios con contraseñas conocidas.

### Comandos útiles

| Acción | Comando |
| --- | --- |
| Ver el estado de los servicios | `docker compose ps` |
| Ver los registros de la aplicación | `docker compose logs web --tail 25` |
| Correr todos los tests (en paralelo) | `docker compose exec web python manage.py test --parallel --noinput` |
| Aplicar migraciones nuevas | `docker compose exec web python manage.py migrate` |
| Reiniciar tras editar archivos `.py`, `.html`, `.css` o `.js` | `docker compose restart web` |
| Aplicar un cambio en `.env` | `docker compose up -d --force-recreate web` |
| Reconstruir tras cambiar `Dockerfile`, `requirements.txt`, `entrypoint.sh` o `.dockerignore` | `docker compose up -d --build` |
| Detener el sistema (conserva los datos) | `docker compose down` |

Tras editar un `.js` o `.css`, recarga el navegador con `Ctrl+Shift+R`. Si hay una migración nueva, córrela **antes** de reiniciar: al reiniciar, el contenedor también aplica las migraciones y las dos ejecuciones pueden chocar.

### 5.1 Respaldo de la base de datos

El servicio `respaldo` de `docker-compose.yml` respalda la base de datos y las imágenes subidas cada `RESPALDO_CADA_HORAS` horas, sin detener el sistema. Guarda los respaldos diarios durante `RESPALDO_DIAS` días y conserva para siempre el primero de cada mes, que forma el histórico completo.

| Acción | Comando |
| --- | --- |
| Respaldar ahora | `docker compose exec respaldo sh /scripts/respaldar.sh` |
| Prueba de recuperación (restaura en una base temporal y compara las tablas, sin tocar el sistema) | `docker compose exec respaldo sh /scripts/verificar.sh` |
| Ver lo que está haciendo | `docker compose logs respaldo --tail 20` |

La restauración, la ubicación de la carpeta y la solución de problemas están en [`respaldo/LEEME.md`](Codigo%20Proyecto/punto_participa_project/respaldo/LEEME.md). Los respaldos contienen datos personales: guárdalos en un lugar con acceso restringido y fuera del repositorio (`respaldos/` está en `.gitignore`).

### Advertencia sobre los datos

Los datos viven en volúmenes de Docker (`pgdata` para la base de datos y `media_volume` para los archivos subidos). **Nunca ejecutes** `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`, porque borran esos volúmenes y se pierde toda la información.

---

## 6. Uso del escáner de asistencia

La pantalla del escáner (`/escaneo/`) registra la asistencia a una actividad por **turnos**:

1. El operador elige la actividad de una lista con buscador. Primero aparecen las que están en curso. Al elegirla empieza su turno.
2. Lee o digita el documento y confirma en el cuadro que muestra el nombre y el RUT del alumno.
3. Al terminar, presiona **Finalizar turno** y ve cuántas asistencias registró y en cuánto tiempo. Si elige otra actividad, el turno anterior se cierra solo.

Mientras trabaja, la pantalla muestra un **contador en vivo**: lo registrado en su turno, el total de la actividad (todos los operadores, frente a los inscritos o los cupos) y cuántos operadores están en turno. También muestra la lista de los últimos registros y cuántos lleva cada operador. Se actualiza con cada registro y cada 15 segundos. El inicio y el fin de cada turno quedan en la auditoría. Un turno que nadie cerró deja de contar como abierto a las 12 horas.

Documentos que reconoce:

* RUT chileno, con o sin puntos y guion, y con la K en mayúscula o minúscula.
* RUN provisorio, pasaporte y cédula de extranjero.
* Código de barras de la aplicación Vivo Duoc.
* Código QR del carnet de identidad (probado con el carnet nuevo y con el anterior que trae QR).

El lector funciona como un teclado, y el sistema reconoce el QR con teclado en español o en inglés, porque busca el RUN en el texto sin depender de la puntuación. Se probó con un lector 2D inalámbrico Well 9322 en su configuración de fábrica.

Detalles de funcionamiento:

* Los documentos se guardan sin puntos ni guion y en mayúsculas, y en pantalla se muestran con formato (por ejemplo, `20.001.550-9`).
* El campo no muestra el texto leído del carnet mientras se confirma, y el aviso de "estudiante no encontrado" no lo repite.
* En los talleres solo se registra a quienes están inscritos. Los alumnos bloqueados no se pueden registrar.
* En las actividades con invitación entran los invitados y sus acompañantes. Si el documento no está en la lista, el escáner ofrece agregar a la persona (sección 3.2), y el contador compara a los que entraron con los esperados (invitados y acompañantes).
* Cada usuario puede hacer hasta 120 lecturas por minuto. El límite es por usuario y no por IP, porque en el Punto varios operadores comparten la misma red.

Limitación conocida: los carnets más antiguos, cuyo código no es un QR con la dirección del Registro Civil, todavía no se reconocen. En ese caso se digita el RUT.

---

## 7. Estructura del repositorio

```text
Fase 1/                    Evidencias de la Fase 1 (grupales e individuales)
Fase 2/                    Documentos de la Fase 2 (versión ágil)
Codigo Proyecto/
├── puntopartida/              Versión estática del frontend (maqueta de referencia)
└── punto_participa_project/   Aplicación Django
    ├── gestion/               Lógica de la aplicación
    │   ├── models.py          Modelos de datos
    │   ├── views.py           Pantallas principales (inicio, actividades, reportes, escáner, usuarios, auditoría)
    │   ├── views_alumnos.py   Directorio, ficha y bloqueo de alumnos
    │   ├── views_catalogos.py Lugares, escuelas y carreras
    │   ├── views_importar.py  Importación de la nómina desde la web
    │   ├── exportaciones.py   Exportaciones de Reportes (Excel y CSV)
    │   ├── importador_alumnos.py  Lectura y validación de la nómina
    │   ├── invitados.py       Lectura y validación de la lista de invitados
    │   ├── views_invitados.py Pantalla Invitados y envío de las invitaciones
    │   ├── views_invitacion_publica.py  Respuesta del alumno desde su enlace
    │   ├── escaner_invitacion.py  Escáner en las actividades con invitación
    │   ├── management/commands/   seed_data, perf_seed e importar_alumnos
    │   ├── migrations/        Migraciones de la base de datos
    │   ├── static/            JavaScript, CSS, imágenes y Chart.js
    │   ├── templates/         Plantillas HTML
    │   ├── templatetags/      Íconos, filtros y piezas comunes de interfaz
    │   └── tests_*.py         Pruebas automatizadas
    ├── punto_participa/       Configuración del proyecto Django
    ├── respaldo/              Scripts y guía del respaldo automático
    ├── docs/                  CAMBIOS.md (historial) y GUIA_ESTILO.md
    ├── Dockerfile
    ├── docker-compose.yml     Servicios db, web y respaldo
    ├── entrypoint.sh          Script de arranque del contenedor
    ├── env.example            Plantilla de variables de entorno
    └── requirements.txt
```

---

## 8. Seguridad

* Credenciales y claves fuera del código, en variables de entorno (`.env`). La configuración de HTTPS, cookies seguras, HSTS y correo también se toma de ahí.
* Rol obligatorio para cada usuario y permisos según el rol y la propiedad de cada actividad.
* Documento de identidad obligatorio para cada usuario; al cambiarlo, el servidor pide confirmación y deja registro en la auditoría.
* Límite de intentos en el inicio de sesión y en la recuperación de contraseña (5 intentos por IP cada 15 minutos).
* Límite de lecturas por usuario en la pantalla del escáner (120 por minuto), con aviso en pantalla al superarlo.
* Límite de intentos en la inscripción pública: 15 documentos inexistentes por IP cada 15 minutos (las inscripciones válidas no cuentan).
* Recuperación de contraseña mediante token y cambio de clave obligatorio cuando corresponde.
* Validación de imágenes subidas, con eliminación de metadatos EXIF.
* Protección de las exportaciones CSV y Excel contra inyección de fórmulas. El listado nominal de participantes solo lo descargan el Administrador y el creador de cada actividad, y cada descarga queda en la auditoría.
* Alumnos bloqueados (por no venir en la nómina o a mano, con motivo): no pueden inscribirse, registrar asistencia ni recibir invitaciones. La nómina respeta los bloqueos manuales.
* Actividades con invitación: el enlace personal es aleatorio y no se puede adivinar, la página no se indexa en buscadores, la respuesta tiene límite de 30 envíos por minuto por IP y queda en la auditoría. El envío de invitaciones por carrera está bloqueado en este tipo de actividad, para que el correo no le llegue a toda la nómina.
* Tolerancia a caracteres especiales en los datos de entrada y escape en la salida.
* Registro de auditoría de las acciones del sistema, incluidos los turnos del escáner y las exportaciones.
* Respaldo automático con prueba de recuperación y copias mensuales permanentes.
* Política de Privacidad pública (`/privacidad/`) y aceptación obligatoria al inscribirse, registrada en la auditoría. El texto es un borrador pendiente de revisión de Duoc UC.

### Pendientes antes de producción

* Envío de correos por SMTP con una cuenta institucional (hoy salen por consola o por una cuenta de prueba).
* Lectura de la IP real del visitante cuando el sistema quede detrás de un proxy, para que los límites de intentos cuenten por visitante y la auditoría guarde la IP correcta.
* Retención de datos: dos años en la base principal y el histórico completo en los respaldos mensuales.
* Derecho al olvido (anonimizar en vez de borrar en cascada) y decisión sobre la IP y el navegador que guarda la auditoría.
* Ubicación definitiva de la carpeta de respaldos en el servidor.
* Revisión de la Política de Privacidad por parte de Duoc UC.
* Rotar las claves usadas en desarrollo y preparar la configuración de Docker para producción.

---

## 9. Pruebas automatizadas

La suite tiene **666 tests** y se ejecuta con:

```bash
docker compose exec web python manage.py test --parallel --noinput
```

En paralelo termina en unos dos minutos y medio en un notebook del equipo. Sin `--parallel` corre en serie y demora bastante más.

Las pruebas usan una base de datos temporal con datos inventados, así que no tocan los datos del sistema. Para correr solo un área, indica su archivo, por ejemplo:

```bash
docker compose exec web python manage.py test gestion.tests_escaner_turno --noinput
```

Los reportes y el dashboard cuentan como inscritos a quienes tienen una inscripción confirmada, sin exigir asistencia, y respetan los filtros de carrera, jornada y escuela según los datos que el alumno tenía al participar.

Qué se verifica, por tema:

| Tema | Qué se verifica | Archivos |
| --- | --- | --- |
| Autenticación y contraseñas | Inicio de sesión con credenciales válidas e inválidas, usuario inactivo que no entra, cierre de sesión, redirección `next` permitida solo hacia rutas internas, cambio de contraseña, recuperación por token y cambio de clave obligatorio. | `tests_extremos`, `tests_integrales`, `tests_views_criticas` |
| Límite de intentos | El sexto intento de login se bloquea; el escáner responde un aviso en JSON al pasar el tope y el límite es por usuario; límite de la inscripción pública. | `tests_ratelimit`, `tests_limite_inscripcion` |
| Permisos por rol | Qué puede abrir cada rol y el usuario anónimo, que un creador no vea ni exporte actividades de otro, respuestas 401 y 403 en los endpoints JSON y rechazo de peticiones sin token CSRF. | `tests_roles_completo`, `tests`, `tests_decorators_utils`, `tests_adicionales` |
| Usuarios y documento de identidad | Documento obligatorio, guardado normalizado, rechazo de duplicados, confirmación al cambiarlo, registro en la auditoría y bloqueo de usuarios. | `tests_rut_usuarios`, `tests_caracteres` |
| RUT, RUN provisorio y pasaporte | Limpieza de puntos y guion, dígito verificador, documentos extranjeros, búsqueda del alumno en distintos formatos y formato de pantalla. | `tests`, `tests_decorators_utils`, `tests_formato_rut` |
| Escáner de asistencia | Registro por RUT, QR y código de barras, confirmación en dos etapas, duplicados, talleres sin inscripción, actividades inactivas, teclado en español e inglés, turnos guardados, contador en vivo con varios operadores y lista para elegir la actividad. | `tests_views_criticas`, `tests_escaner_teclado`, `tests_escaner_turno`, `tests_integrales`, `tests_adicionales` |
| Alumnos y nómina | Importación desde Excel y CSV (vista previa, errores por fila, bloqueo masivo), alumnos bloqueados que no se inscriben ni se registran, directorio con buscador, ficha con historial y bloqueo manual que la nómina respeta. | `tests_importador`, `tests_importar_web`, `tests_alumnos_bloqueados`, `tests_alumnos_pantalla` |
| Catálogos | Lugares, escuelas y carreras: agregar, renombrar con confirmación, crear una carrera nueva y bloquear la antigua, bloquear y eliminar lo que no se usa, número de sala y migraciones que unifican los datos existentes. | `tests_lugares`, `tests_catalogo_lugares`, `tests_lugar_numero`, `tests_catalogo_escuelas_carreras` |
| Datos al participar | La carrera, la escuela y la jornada se guardan al inscribirse y al asistir, no cambian si el alumno cambia de carrera y se corrigen al renombrar en Catálogos. | `tests_foto_academica` |
| Datos hostiles y caracteres especiales | Apóstrofes y tildes, caracteres nulos y de control, normalización Unicode, y que entradas o parámetros hostiles no generen error 500 ni reflejen HTML. | `tests`, `tests_caracteres`, `tests_parametros` |
| Exportaciones | Protección contra fórmulas, BOM y separador `;`, contenido de los tres reportes (inscritos, asistentes, no asistieron, porcentaje), fechas reales, hoja Información, permisos y registro en la auditoría. | `tests_exportaciones`, `tests_exportaciones_p1`, `tests_extremos`, `tests_integrales` |
| Actividades, inscripciones y cupos | Crear, editar y eliminar actividades, validación de fechas, cupos e imágenes, inscripción pública, página pública de las masivas, recálculo de cupos y panel de participación del detalle. | `tests_integrales`, `tests_adicionales`, `tests_extremos`, `tests_forms_fechas`, `tests_forms_imagen`, `tests_actividad_publica`, `tests_embudo` |
| Actividades con invitación | Lectura y validación de la lista (columnas, dígito verificador, repetidos, nómina y bloqueados), permisos de la pantalla Invitados, envío con enlace personal, respuesta con acompañantes y su validación, cambios hasta que empieza la actividad, escáner con invitados, acompañantes y agregados en la entrada, y reportes y exportaciones con invitados. | `tests_invitados`, `tests_invitacion_respuesta`, `tests_escaner_invitacion`, `tests_reportes_invitacion` |
| Invitaciones por correo | Envío y registro de la notificación, fallo de SMTP registrado como fallido, límite por envío, previsualización y enlace correcto según el tipo de actividad. | `tests_adicionales`, `tests_extremos`, `tests_integrales`, `tests_correo_invitacion` |
| Reportes y auditoría | Inscritos y asistentes con filtros, filtro por tipo y lugar, pestañas, cada creador ve solo lo suyo, la auditoría guarda los datos de la petición y su exportación es solo para el Administrador. | `tests_kpi_inscritos`, `tests_reportes_tipo`, `tests_auditoria_limites`, `tests_integrales`, `tests_roles_completo` |
| Interfaz | Botones con ícono y aviso, filtros activos, menú Exportar, pantallas sin símbolos de texto antiguos y menú con la página actual marcada. | `tests_ui` |
| Configuración, privacidad y respaldo | Configuración desde `.env`, colores de las escuelas, Política de Privacidad y consentimiento, datos de prueba repetibles y scripts del respaldo. | `tests_p0_tecnicos`, `tests_privacidad`, `tests_seed_data`, `tests_respaldo` |
| Resistencia y consistencia | Carga de muchas inscripciones y asistencias sin duplicados, inscripciones simultáneas que no superan los cupos y reversión de los cambios cuando ocurre un error. | `tests_resistencia` |

Lo que las pruebas automáticas no cubren: el JavaScript de las pantallas y el lector físico de códigos se verifican a mano. La prueba de usabilidad del escáner con operadores reales del Punto está pendiente.

---

## 10. Integrantes del equipo

| Integrante | Rol | Responsabilidades |
| --- | --- | --- |
| **Gabriel González** | Jefe de Proyecto y Desarrollador Backend | Scrum Master, arquitectura y desarrollo backend, ciberseguridad |
| **Pablo Rebolledo** | Desarrollador Frontend | Diseño UX/UI, maquetación, desarrollo frontend, conexión frontend/backend |
| **Diverson Nonnombre** | Encargado de Base de Datos y QA | Modelamiento PostgreSQL, gestión de la base de datos, QA y testing, consultas para reportes |

---

## 11. Metodología de trabajo

El equipo trabaja con **Scrum**, y estima las funcionalidades mediante **Planning Poker**. El trabajo se divide en épicas y funcionalidades que se desarrollan por sprints:

* Registro de asistencia.
* Gestión de cupos e inscripciones.
* Invitaciones por correo.
* Usuarios y roles.
* Reportes y métricas.
* Gestión de actividades.
* Auditoría y trazabilidad.
* Respaldo y continuidad de datos.

---

## 12. Arquitectura de la solución

La aplicación web tiene tres capas:

```text
┌──────────────────────────────────────────────┐
│                  USUARIOS                    │
│  Administrador · Creador de Evento ·         │
│  Encargado de Registrar · Estudiantes        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                  FRONTEND                    │
│              HTML / CSS / JS                 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                   BACKEND                    │
│      Python / Django (Gunicorn + WhiteNoise) │
│                                              │
│  • Usuarios y roles   • Inscripciones        │
│  • Actividades        • Asistencia y turnos  │
│  • Alumnos            • Catálogos            │
│  • Reportes           • Auditoría            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 PostgreSQL 16                │
│                                              │
│  • Usuarios           • Inscripciones        │
│  • Alumnos            • Asistencias          │
│  • Actividades        • Turnos del escáner   │
│  • Catálogos          • Registro de auditoría│
└──────────────────────────────────────────────┘
```

Todo el sistema se ejecuta con Docker Compose en tres servicios: `db` (PostgreSQL), `web` (Django con Gunicorn) y `respaldo` (copias automáticas de la base y de las imágenes).

---

## 13. Código del proyecto

La carpeta `Codigo Proyecto` contiene el código del sistema Punto Participa. El historial de commits fue reconstruido el 05/10/2026 a partir de respaldos locales (archivos zip); la fecha de cada commit corresponde a la fecha del respaldo del que proviene.
