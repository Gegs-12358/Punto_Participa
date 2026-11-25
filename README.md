

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

* Suite de pruebas automatizadas: 778 tests (detalle en la sección 9).
* Despliegue en la nube: **por definir**. Actualmente se ejecuta en local con Docker.
* El historial detallado de cambios está en [`docs/CAMBIOS.md`](Codigo%20Proyecto/punto_participa_project/docs/CAMBIOS.md) y la guía de estilo de las pantallas en [`docs/GUIA_ESTILO.md`](Codigo%20Proyecto/punto_participa_project/docs/GUIA_ESTILO.md).

---

## 3. Pantallas

| Pantalla | Para qué sirve | Roles |
| --- | --- | --- |
| **Inicio** | Resumen del período: actividades en curso, talleres con cupos, inscritos, asistencias del día, invitaciones enviadas, alertas y gráficos. Cada gráfico explica en una línea qué muestra (sección 3.6). | Administrador, Creador |
| **Actividades** | Crear, editar y eliminar actividades y talleres, con buscador y filtros. El lugar se elige de una lista; si es una sala, se pide su número (por ejemplo, 1203). Desde aquí se envían las invitaciones por correo. Tipos: masiva, taller y con invitación (sección 3.2). Cualquiera puede tener varias sesiones, con un porcentaje mínimo de asistencia para cumplir (sección 3.7). | Administrador, Creador |
| **Detalle de actividad** | Datos de la actividad (con sus sesiones, si tiene varias) y el recorrido de la participación: invitados, inscritos, asistieron y no asistieron, con la lista de quienes se inscribieron y no fueron. En las actividades con invitación: invitados, confirmados, rechazados, sin responder, entraron y acompañantes. | Administrador, Creador |
| **Invitados** | Lista de una actividad con invitación: carga del Excel o CSV con vista previa, estado de cada invitado y sus acompañantes, enlace personal para copiar, envío de las invitaciones y quitar a quien aún no entra. | Administrador, Creador |
| **Reportes** | Gráficos y tablas por actividad o por escuela y carrera, con filtros por actividad, tipo, lugar, escuela, carrera, jornada y fechas. Menú **Exportar** con cuatro reportes en Excel o CSV (sección 3.1). | Administrador, Creador |
| **Usuarios** | Crear y editar cuentas, asignar el rol y bloquear el acceso, con buscador. **Importar usuarios** crea varias cuentas desde Excel o CSV (nombre, correo, rut, rol y usuario opcional), con vista previa; cada persona recibe un correo con un enlace para crear su contraseña. | Administrador |
| **Alumnos** | Directorio de la nómina con buscador; ficha de cada alumno con su historial de participación; bloqueo manual con motivo. Desde aquí se importa la nómina en Excel o CSV. | Administrador |
| **Catálogos** | Lugares, escuelas (con su color para los gráficos) y carreras: agregar, renombrar, bloquear y eliminar lo que no se usa. | Administrador |
| **Escáner** | Registro de asistencia por turnos, con contador en vivo (sección 6). | Los tres roles |
| **Auditoría** | Registro de todas las acciones del sistema, con filtros y exportación. | Administrador |
| **Páginas públicas** | Inscripción a talleres (con lista de espera cuando están llenos), cancelación de la inscripción (`/inscripcion/cancelar/<enlace>/`), página de las actividades masivas, respuesta a una invitación (`/invitacion/<enlace>/`) y Política de Privacidad. | Sin cuenta |

### 3.1 Exportaciones

Todas usan los filtros aplicados en Reportes, y cada descarga queda registrada en la auditoría. El Creador de Evento solo exporta sus propias actividades.

| Reporte | Contenido |
| --- | --- |
| **Resumen por actividad** | Una fila por actividad: tipo, estado, inicio y término, lugar, creador, cupos, invitados, inscritos, asistentes, no asistieron, porcentaje de asistencia y acompañantes. |
| **Participación por escuela y carrera** | Inscritos, asistentes y no asistieron por actividad, escuela, carrera y jornada. |
| **Listado de participantes** | Cada alumno con su inscripción y su asistencia (hora, método y quién la registró). En las actividades con invitación incluye a los acompañantes, y la columna **Participa como** dice si es invitado, agregado en la entrada o acompañante. Contiene datos personales. |
| **Asistencia por sesión** | Una fila por persona y actividad: sesiones de la actividad, sesiones a las que vino (por ejemplo "1, 2, 4"), porcentaje, mínimo exigido y **Cumple**. Filtrando "Cumple = Sí" queda la lista para los certificados de participación. Con una sola sesión, cumple quien asistió. Contiene datos personales. |
| **Todo en un Excel** | Los cuatro anteriores, cada uno en su hoja. |

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

### 3.3 Cancelación de inscripciones y lista de espera

* Al inscribirse en un taller, el estudiante recibe un correo de confirmación con un **enlace personal para cancelar**. Puede usarlo hasta 24 horas antes del inicio; después debe avisar al Punto Estudiantil.
* El Administrador y el creador del taller pueden cancelar una inscripción desde **Participantes** hasta que empiece el taller. No se cancela a quien ya tiene la asistencia registrada.
* Al cancelar, el cupo vuelve a quedar libre y la inscripción pasa a un historial de cancelaciones, que se ve en Participantes. El estudiante puede volver a inscribirse si hay cupo.
* Cuando un taller está lleno, su página ofrece anotarse en la **lista de espera** con el RUT. Anotarse no inscribe: cuando alguien cancela, se avisa por correo a todos los de la lista y el cupo es para el primero que se inscribe. Al inscribirse, el estudiante sale de la lista.
* Las cancelaciones, las anotaciones y los avisos quedan en la auditoría.

### 3.4 Retención de datos y anonimización

* La base principal guarda dos años. Las actividades que terminaron hace más tiempo (con sus inscripciones, asistencias, invitados, cancelaciones y correos) y los registros de auditoría de esa antigüedad, incluidas la IP y el navegador, se borran de ella. El histórico completo queda en los respaldos mensuales.
* **Nada se borra solo.** Cuando hay datos vencidos, el sistema avisa por correo a todos los Administradores y les da 10 días para verificar los respaldos. Los recordatorios salen a los 7 y a los 3 días. Si el plazo vence sin que nadie haya actuado, no se borra nada y el aviso se repite cada día.
* El borrado lo ejecuta un Administrador desde el Inicio, marcando que verificó los respaldos y presionando **"Ya verifiqué los respaldos: borrar ahora"**. Queda en la auditoría con su nombre y todos los Administradores reciben un correo que dice quién lo hizo.
* Desde la ficha de un alumno, el Administrador puede **anonimizarlo**: se reemplazan el nombre, el RUT y el correo (también en sus invitaciones, acompañantes y registros de auditoría) y se conservan la carrera, la escuela, la jornada y su participación, para que los reportes no cambien. Hay que escribir ANONIMIZAR para confirmar y no se puede deshacer.


### 3.5 Páginas públicas y correos

* Las páginas de inscripción, de actividad masiva, de invitación y de cancelación muestran arriba la **imagen de la actividad** con su tipo y su título. Sin imagen, una franja azul con la mascota.
* Los estados se ven en grande: "Sin cupos disponibles" en rojo y "Evento ya realizado" o "cancelado" en gris.
* Los correos de invitación, invitación especial, confirmación de inscripción y lista de espera llevan los logos, la imagen de la actividad y la fecha, el horario y el lugar. Las imágenes usan la dirección completa del sitio (`SITE_URL`), así que se ven en el correo cuando el sistema está publicado.

### 3.6 Gráficos

* Cada gráfico del Inicio y de Reportes tiene, bajo el título, una línea que explica qué cuenta y cómo leerlo. Al pasar el mouse aparece el detalle (total del mes, porcentaje de asistencia, escuela de la carrera).
* **Actividades terminadas, en curso y próximas** (Inicio): cuántas actividades empiezan cada mes, desde cinco meses atrás hasta el mes siguiente. Cada actividad se cuenta una vez y su estado sale de las fechas; las canceladas no se cuentan.
* **Talleres realizados** (Inicio): inscritos y asistentes de los 8 talleres más recientes que ya empezaron. Las actividades masivas no aparecen porque no tienen inscripción.
* En los gráficos de barras con muchas actividades, cada barra lleva un número y debajo hay una lista con el nombre completo y la cifra. En Reportes se muestran las 10 actividades con más asistentes; el resto está en la tabla.
* En las donas de carreras, las carreras de una misma escuela usan tonos del color de esa escuela (definido en Catálogos), y la leyenda muestra la cantidad y el porcentaje.
---

### 3.7 Actividades de varias sesiones

Cualquier actividad (masiva, taller o con invitación) puede tener varias sesiones. En el formulario, las fechas de siempre son la primera sesión y el bloque **Sesiones adicionales** agrega las demás, cada una con su día y horario. Con varias sesiones se define la **asistencia mínima para cumplir** (75 % por defecto).

- La inscripción a un taller vale para todas las sesiones y se puede hacer hasta que termina la primera.
- El escáner registra en la sesión del día y muestra cuál es ("sesión 2 de 3"); el operador puede cambiarla a mano. Cada persona se registra una vez por sesión.
- En **Participantes** hay una tabla con una columna por sesión, el porcentaje de cada persona y si cumple. El reporte **Asistencia por sesión** entrega la lista para los certificados de participación (el sistema no genera los certificados).
- Las páginas públicas y los correos listan las sesiones. Una sesión que ya tiene asistencias no se puede quitar.
- En los reportes y gráficos, "asistió" sigue significando que vino al menos a una sesión.

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

1. **Clonar el repositorio y entrar a la carpeta de Docker:**

   ```bash
   git clone https://github.com/Gegs-12358/Punto_Participa.git
   cd Punto_Participa/maquinasVirtuales
   ```

   Todos los comandos `docker compose` se ejecutan desde `maquinasVirtuales/`. El código de la aplicación está en `src/punto_participa_project/`.

2. **Crear el archivo `.env`** en `maquinasVirtuales/` (junto a `docker-compose.yml`) copiando la plantilla incluida en el repositorio:

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
| Reconstruir tras cambiar `Dockerfile`, `requirements.txt`, `entrypoint.sh` o `Dockerfile.dockerignore` | `docker compose up -d --build` |
| Achicar las imágenes de actividades subidas antes del 25/11/2026 y crear sus miniaturas e imágenes para correos (sin `--aplicar` solo muestra qué haría; respalda antes) | `docker compose exec web python manage.py optimizar_imagenes --aplicar` |
| Detener el sistema (conserva los datos) | `docker compose down` |

Tras editar un `.js` o `.css`, recarga el navegador con `Ctrl+Shift+R`. Si hay una migración nueva, córrela **antes** de reiniciar: al reiniciar, el contenedor también aplica las migraciones y las dos ejecuciones pueden chocar.

### 5.1 Respaldo de la base de datos

El servicio `respaldo` de `docker-compose.yml` respalda la base de datos y las imágenes subidas cada `RESPALDO_CADA_HORAS` horas, sin detener el sistema. Guarda los respaldos diarios durante `RESPALDO_DIAS` días y conserva para siempre el primero de cada mes, que forma el histórico completo.

| Acción | Comando |
| --- | --- |
| Respaldar ahora | `docker compose exec respaldo sh /scripts/respaldar.sh` |
| Prueba de recuperación (restaura en una base temporal y compara las tablas, sin tocar el sistema) | `docker compose exec respaldo sh /scripts/verificar.sh` |
| Ver lo que está haciendo | `docker compose logs respaldo --tail 20` |

La restauración, la ubicación de la carpeta y la solución de problemas están en [`maquinasVirtuales/respaldo/LEEME.md`](maquinasVirtuales/respaldo/LEEME.md). Los respaldos contienen datos personales: guárdalos en un lugar con acceso restringido y fuera del repositorio (`respaldos/` está en `.gitignore`).

### 5.2 Tareas programadas (retención de datos)

El servicio `tareas` revisa una vez al día (cada `TAREAS_CADA_HORAS` horas) si hay datos de más de `RETENCION_ANIOS` años y envía los avisos de la sección 3.4. Nunca borra: eso lo hace un Administrador desde el Inicio. Los días de aviso se configuran con `RETENCION_AVISOS_DIAS` (por defecto `10,7,3`).

| Acción | Comando |
| --- | --- |
| Ver qué haría hoy, sin enviar correos ni borrar | `docker compose exec web python manage.py retencion --simular` |
| Ver lo que está haciendo | `docker compose logs tareas --tail 20` |
| Aplicar cambios en `servicios/retencion.py` o en el `.env` | `docker compose up -d --force-recreate tareas` |

### Advertencia sobre los datos

Los datos viven en volúmenes de Docker (`pgdata` para la base de datos y `media_volume` para los archivos subidos). **Nunca ejecutes** `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`, porque borran esos volúmenes y se pierde toda la información.

---

## 6. Uso del escáner de asistencia

La pantalla del escáner (`/escaneo/`) registra la asistencia a una actividad por **turnos**:

1. El operador elige la actividad de una lista con buscador. Primero aparecen las que están en curso. Al elegirla empieza su turno. Los tres roles ven todas las actividades activas, también el Creador de Evento las de otros creadores.
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
Fase 3/                    Evidencias de la Fase 3 (grupales e individuales)
maquinasVirtuales/         Configuración de Docker (se ejecuta desde aquí)
├── docker-compose.yml         Servicios db, web, respaldo y tareas
├── Dockerfile                 Imagen de la aplicación
├── Dockerfile.dockerignore    Qué entra a la imagen
├── entrypoint.sh              Script de arranque del contenedor
├── env.example                Plantilla de variables de entorno (.env va aquí)
├── respaldo/                  Scripts y guía del respaldo automático
└── tareas/                    Ciclo diario del servicio tareas
src/                       Código fuente
├── puntopartida/              Versión estática del frontend (maqueta de referencia)
└── punto_participa_project/   Aplicación Django
    ├── gestion/               Lógica de la aplicación
    │   ├── models.py          Modelos de datos
    │   ├── urls.py            Direcciones, agrupadas igual que las vistas
    │   ├── views/             Pantallas, un archivo por tema:
    │   │   ├── comun.py           Lo que usan varias pantallas (auditoría, errores JSON, colores)
    │   │   ├── cuentas.py         Inicio de sesión y contraseñas
    │   │   ├── inicio.py          Inicio (dashboard) y botón de retención de datos
    │   │   ├── actividades.py     Listado, detalle, participantes, crear, editar y eliminar
    │   │   ├── inscripciones.py   Inscripción pública, lista de espera, cancelación y páginas públicas
    │   │   ├── invitaciones.py    Correo de invitación, lista de invitados y respuesta del alumno
    │   │   ├── escaner.py         Escáner de asistencia, turnos y contador en vivo
    │   │   ├── escaner_invitacion.py  Escáner en las actividades con invitación
    │   │   ├── reportes.py        Pantalla Reportes y filtros compartidos
    │   │   ├── exportaciones.py   Descargas en Excel y CSV de Reportes y Auditoría
    │   │   ├── usuarios.py        Usuarios y carga masiva
    │   │   ├── alumnos.py         Directorio, ficha, bloqueo, anonimización e importación de la nómina
    │   │   ├── catalogos.py       Lugares, escuelas y carreras
    │   │   └── auditoria.py       Pantalla Auditoría
    │   ├── servicios/         Lógica que no depende de una pantalla:
    │   │   ├── importador_alumnos.py  Lectura y validación de la nómina
    │   │   ├── usuarios_masivos.py    Lectura, validación y creación de usuarios desde Excel o CSV
    │   │   ├── invitados.py       Lectura y validación de la lista de invitados
    │   │   ├── cancelaciones.py   Cancelación de inscripciones y correo de confirmación
    │   │   ├── lista_espera.py    Lista de espera y aviso cuando se libera un cupo
    │   │   ├── retencion.py       Avisos de retención y borrado de los datos de más de dos años
    │   │   └── anonimizacion.py   Anonimización de un alumno
    │   ├── permissions.py, decorators.py, utils.py  Permisos por rol, decoradores y utilidades
    │   ├── management/commands/   seed_data, perf_seed, importar_alumnos y retencion
    │   ├── migrations/        Migraciones de la base de datos
    │   ├── static/            JavaScript, CSS, imágenes y Chart.js
    │   ├── templates/         Plantillas HTML (los correos, en templates/gestion/correos/)
    │   ├── templatetags/      Íconos, filtros y piezas comunes de interfaz
    │   └── tests/             Pruebas automatizadas, en una carpeta por tema
    ├── punto_participa/       Configuración del proyecto Django
    ├── docs/                  CAMBIOS.md (historial) y GUIA_ESTILO.md
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
* Cancelación de inscripciones con enlace personal aleatorio, sin indexar en buscadores y con límite de 30 envíos por minuto por IP. La lista de espera usa el mismo límite de intentos que la inscripción pública.
* Retención de dos años en la base principal, con borrado ejecutado por un Administrador después de verificar los respaldos, y anonimización de alumnos a pedido. La IP y el navegador de la auditoría se borran junto con el resto de los registros de más de dos años.
* Política de Privacidad pública (`/privacidad/`) y aceptación obligatoria al inscribirse, al anotarse en la lista de espera y al responder una invitación. La versión aceptada y la fecha quedan en el propio registro (y en la auditoría), y salen en el Listado de participantes. El texto es un borrador pendiente de revisión de Duoc UC.

### Pendientes antes de producción

* Envío de correos por SMTP con una cuenta institucional (hoy salen por consola o por una cuenta de prueba).
* Lectura de la IP real del visitante cuando el sistema quede detrás de un proxy, para que los límites de intentos cuenten por visitante y la auditoría guarde la IP correcta.
* Ubicación definitiva de la carpeta de respaldos en el servidor y plazo de conservación de los respaldos mensuales (la Política de Privacidad lo deja por confirmar).
* Revisión de la Política de Privacidad por parte de Duoc UC.
* Rotar las claves usadas en desarrollo y preparar la configuración de Docker para producción.

---

## 9. Pruebas automatizadas

La suite tiene **778 tests** y se ejecuta con:

```bash
docker compose exec web python manage.py test --parallel --noinput
```

En paralelo termina en unos dos minutos en un notebook del equipo. Sin `--parallel` corre en serie y demora bastante más.

Las pruebas usan una base de datos temporal con datos inventados, así que no tocan los datos del sistema. Están en `gestion/tests/`, en una carpeta por tema que sigue las mismas áreas de `views/` y `servicios/`. Para correr solo un tema o un archivo:

```bash
docker compose exec web python manage.py test gestion.tests.escaner --noinput
docker compose exec web python manage.py test gestion.tests.escaner.tests_turno --noinput
```

La cobertura es de **98 %** de las líneas del sistema (medida el 16/11/2026, sin contar migraciones, comandos de administración ni el admin de Django). Lo que queda sin probar son choques entre dos operadores en el mismo instante y errores inesperados genéricos.

Muchas pruebas recorren una tabla de casos (por ejemplo, todos los formatos de RUT o la matriz de permisos). Cada caso se revisa por separado con `subTest`, y si uno falla el informe dice cuál.

Los reportes y el dashboard cuentan como inscritos a quienes tienen una inscripción confirmada, sin exigir asistencia, y respetan los filtros de carrera, jornada y escuela según los datos que el alumno tenía al participar.

Qué se verifica, por carpeta:

| Carpeta | Qué se verifica | Archivos |
| --- | --- | --- |
| `cuentas_y_permisos` | Inicio y cierre de sesión, `next` solo hacia rutas internas, cambio y recuperación de contraseña. Matriz de permisos: qué responde cada una de las 27 pantallas a quien no inició sesión, al Administrador, al Creador y al Registrador. Cuentas inactivas o sin perfil, respuestas 401 y 403 en JSON, CSRF. Documento de identidad de los usuarios y carga masiva. | `tests_contrasenas`, `tests_roles`, `tests_usuarios`, `tests_usuarios_masivos` |
| `actividades` | Crear, editar y eliminar actividades; validación de fechas, cupos, lugar e imágenes; panel de participación del detalle. Sesiones adicionales: agregar, cambiar y quitar (no las que tienen asistencias), porcentaje mínimo, inscripción hasta el fin de la primera sesión y la hora correcta al editar. | `tests_formularios`, `tests_gestion`, `tests_embudo`, `tests_sesiones_form` |
| `inscripciones` | Inscripción pública y su límite de intentos, página pública de las masivas, portada con la imagen, Política de Privacidad y consentimiento guardado, cancelación por el alumno y por el gestor, lista de espera. | `tests_inscripcion_publica`, `tests_limite`, `tests_portada`, `tests_privacidad`, `tests_consentimiento`, `tests_cancelacion`, `tests_lista_espera` |
| `invitaciones` | Lista de invitados (columnas, dígito verificador, repetidos, nómina, bloqueados), respuesta con acompañantes, envío con enlace personal, correos de invitación según el tipo de actividad, fallo de SMTP y límite por envío. | `tests_lista`, `tests_respuesta`, `tests_correo` |
| `escaner` | Registro por RUT, QR y código de barras, dos etapas, duplicados, talleres sin inscripción, actividades inactivas, teclado en español e inglés, turnos y contador en vivo, invitados y acompañantes en la entrada. Actividades de varias sesiones: en qué sesión queda cada registro, una asistencia por sesión, cambio de sesión a mano y conversión de los datos que ya existían. | `tests_registro`, `tests_turno`, `tests_teclado`, `tests_invitacion`, `tests_sesiones` |
| `reportes` | Inscritos y asistentes con filtros, filtro por tipo y lugar, gráficos, datos académicos guardados al participar, reportes con invitados y exportaciones (fórmulas neutralizadas, BOM, separador `;`, permisos y auditoría). Cumplimiento del mínimo de sesiones y reporte Asistencia por sesión. | `tests_indicadores`, `tests_filtros`, `tests_graficos`, `tests_foto_academica`, `tests_invitacion`, `tests_exportaciones`, `tests_sesiones` |
| `alumnos` | Importación desde Excel y CSV, alumnos bloqueados, directorio con buscador, ficha y bloqueo manual. | `tests_importador`, `tests_importar_web`, `tests_bloqueados`, `tests_pantalla` |
| `catalogos` | Lugares (con número de sala), escuelas y carreras: agregar, renombrar con confirmación, bloquear, eliminar lo que no se usa, colores y migraciones. | `tests_lugares`, `tests_escuelas_carreras` |
| `datos` | Auditoría (pantalla, filtros, exportación y límites de los campos), retención de dos años y anonimización. | `tests_auditoria`, `tests_retencion` |
| `sistema` | Funciones de RUT y formato, entradas hostiles que no producen error 500 ni reflejan HTML, límite de intentos del login y del escáner, configuración desde `.env`, respaldo, interfaz, páginas de error propias y resistencia (carga, concurrencia en los cupos, reversión ante errores). | `tests_utilidades`, `tests_seguridad`, `tests_limites`, `tests_configuracion`, `tests_interfaz`, `tests_resistencia`, `tests_paginas_error` |

`gestion/tests/base.py` tiene los datos comunes (roles, usuarios, carreras, alumnos y actividades) que usan varias carpetas.

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

La carpeta `src` contiene el código del sistema Punto Participa y `maquinasVirtuales` su configuración de Docker, según la estructura de repositorio que pide la carrera (hasta el 25/11/2026 el código estaba en `Codigo Proyecto`). El historial de commits fue reconstruido el 05/10/2026 a partir de respaldos locales (archivos zip); la fecha de cada commit corresponde a la fecha del respaldo del que proviene.

---

## 14. Licencia

Punto Participa, plataforma de gestión de actividades y asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

Copyright (C) 2026 Gabriel Eduardo González Soto, Pablo Emilio Rebolledo Alvear y Diverson Nonnombre Nonnombre.

Este programa es software libre: puede redistribuirse y modificarse bajo los términos de la Licencia Pública General GNU (GPL) publicada por la Free Software Foundation, versión 3. Se distribuye con la esperanza de que sea útil, pero sin ninguna garantía. El texto completo está en el archivo [`LICENSE`](LICENSE).
