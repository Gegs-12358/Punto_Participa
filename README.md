

# Punto Participa

Plataforma web para la gestión de actividades, talleres, inscripciones y control de asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

---

## 1. Descripción del proyecto

Hoy el registro de participación se hace en planillas Excel con macros que se trasladan a mano, lo que dificulta centralizar la información, controlar el acceso, resguardar los datos y generar historial. Además, los talleres con cupos limitados usan formularios externos, y los estudiantes no pueden ver las vacantes en tiempo real.

**Punto Participa** reemplaza esos procesos por una plataforma única que permite gestionar:

* Actividades masivas.
* Talleres con cupos limitados.
* Inscripciones de estudiantes.
* Registro de asistencia.
* Usuarios y roles.
* Reportes de participación.
* Auditoría de acciones.

El registro de asistencia se puede hacer digitando el RUT, leyendo el código QR de la cédula de identidad o leyendo el código de barras que muestra la aplicación Vivo Duoc.

### Perfiles

El sistema tiene **tres roles con cuenta de usuario**:

| Rol | Qué puede hacer |
| --- | --- |
| **Administrador** | Acceso completo: usuarios y roles, actividades de todos los creadores, reportes, auditoría y registro de asistencia. |
| **Creador de Evento** | Crea y gestiona sus propias actividades y talleres, envía invitaciones por correo, consulta sus reportes y registra asistencia. |
| **Encargado de Registrar** | Solo registra la asistencia presencial, desde la pantalla del escáner. |

El registro de asistencia en el escáner está disponible para los tres roles; el Encargado de Registrar solo tiene acceso a esa pantalla.

Los **estudiantes no tienen cuenta**: consultan los talleres disponibles y se inscriben con su RUT desde el formulario público de inscripción.

---

## 2. Estado del proyecto

El proyecto está en desarrollo y funciona de punta a punta en un entorno local con Docker. Hoy se encuentra en etapa de pruebas internas y **todavía no está publicado en un servidor de producción**.

* Suite de pruebas automatizadas: 319 tests (detalle en la sección 8).
* Despliegue en la nube: **por definir**. Actualmente se ejecuta en local con Docker.

---

## 3. Tecnologías

| Tecnología | Uso |
| --- | --- |
| **HTML, CSS y JavaScript** | Interfaces web |
| **Python 3.12** | Backend |
| **Django 6.1** | Framework del backend |
| **PostgreSQL 16** | Base de datos |
| **Gunicorn** | Servidor de aplicación |
| **WhiteNoise** | Entrega de archivos estáticos |
| **Docker y Docker Compose** | Ejecución reproducible del sistema |
| **Git y GitHub** | Control de versiones y repositorio |

---

## 4. Cómo ejecutar el proyecto localmente

### Requisitos

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y en ejecución.
* Git.

No hace falta instalar Python ni PostgreSQL: todo corre dentro de contenedores.

### Pasos

1. **Clonar el repositorio y entrar a la carpeta del proyecto Django:**

   ```powershell
   git clone https://github.com/Gegs-12358/Punto_Participa.git
   cd Punto_Participa\"Codigo Proyecto"\punto_participa_project
   ```

2. **Crear el archivo `.env`** en esa carpeta (junto a `manage.py`) copiando la plantilla incluida en el repositorio:

   ```powershell
   Copy-Item env.example .env
   ```

   Luego abre `.env` y reemplaza los valores de ejemplo. El archivo `.env` nunca se sube al repositorio. Variables:

   | Variable | Qué es |
   | --- | --- |
   | `SECRET_KEY` | Clave secreta de Django (64 caracteres alfanuméricos aleatorios). |
   | `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Nombre, usuario y clave de la base de datos. PostgreSQL los toma de aquí al crearse. |
   | `DB_HOST`, `DB_PORT` | Los define `docker-compose.yml` dentro de Docker; en la plantilla quedan solo como referencia. |
   | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Cuenta de Gmail y su clave de aplicación para enviar correos. |
   | `SITE_URL` | Dirección base del sistema, usada en los enlaces de los correos. |
   | `MAX_INVITACIONES_POR_ENVIO` | Máximo de invitaciones por envío. |
   | `DEBUG`, `ALLOWED_HOSTS` | Modo de depuración y dominios permitidos. |

   Reglas para los valores:

   * Sin comillas, sin espacios (tampoco al final de la línea) y **sin el signo `$`**: Docker Compose lo interpreta como variable y rompe la clave.
   * Usa claves largas y aleatorias, distintas para cada integrante, y nunca las compartas por chat ni las subas a GitHub.
   * Hoy el envío real de correos está desactivado en la configuración (los correos salen por consola), así que en pruebas las claves de Gmail pueden quedar de ejemplo.

3. **Construir y levantar el sistema:**

   ```powershell
   docker compose up -d --build
   ```

   La primera vez demora, porque descarga las imágenes. Al arrancar, el contenedor espera a PostgreSQL, aplica las migraciones, crea la tabla de caché del límite de intentos, reúne los archivos estáticos e inicia Gunicorn.

4. **Abrir el sistema** en el navegador: <http://localhost:8000/login/>

### Comandos útiles

| Acción | Comando |
| --- | --- |
| Ver el estado de los servicios | `docker compose ps` |
| Ver los registros de la aplicación | `docker compose logs web --tail 25` |
| Correr todos los tests | `docker compose exec web python manage.py test --noinput` |
| Reiniciar tras editar archivos `.py` o `.html` | `docker compose restart web` |
| Aplicar un cambio en `.env` | `docker compose up -d --force-recreate web` |
| Reconstruir tras cambiar `Dockerfile`, `requirements.txt`, `entrypoint.sh` o `.dockerignore` | `docker compose up -d --build` |
| Detener el sistema (conserva los datos) | `docker compose down` |

Tras editar un `.js` o `.css`, recarga el navegador con `Ctrl+Shift+R`.

### Respaldo de la base de datos

Desde PowerShell, en la carpeta del proyecto. No uses el operador `>` para guardar el volcado: en PowerShell convierte el archivo a otra codificación y lo daña.

```powershell
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/respaldo.dump'
docker compose cp db:/tmp/respaldo.dump "..\respaldos\bd_AAAAMMDD.dump"
docker compose exec -T db rm /tmp/respaldo.dump
```

Los respaldos pueden contener datos personales: guárdalos fuera del repositorio y de cualquier carpeta compartida. Un respaldo no probado es solo una esperanza, así que conviene restaurarlo de vez en cuando en una base temporal y comparar los conteos.

### Advertencia sobre los datos

Los datos viven en volúmenes de Docker (`pgdata` para la base de datos y `media_volume` para los archivos subidos). **Nunca ejecutes** `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`, porque borran esos volúmenes y se pierde toda la información.

---

## 5. Uso del escáner de asistencia

La pantalla del escáner (`/escaneo/`) registra la asistencia a una actividad. El flujo es: elegir una actividad activa, leer o digitar el documento y confirmar en el cuadro que muestra el nombre y el RUT del alumno.

Documentos que reconoce:

* RUT chileno, con o sin puntos y guion, y con la K en mayúscula o minúscula.
* RUN provisorio, pasaporte y cédula de extranjero.
* Código de barras de la aplicación Vivo Duoc.
* Código QR del carnet de identidad (probado con el carnet nuevo y con el anterior que trae QR).

El lector funciona como un teclado, y el sistema reconoce el QR con teclado en español o en inglés, porque busca el RUN en el texto sin depender de la puntuación. Se probó con un lector 2D inalámbrico Well 9322 en su configuración de fábrica.

Detalles de funcionamiento:

* Los documentos se guardan sin puntos ni guion y en mayúsculas, y en pantalla se muestran con formato (por ejemplo, `20.001.550-9`).
* El campo no muestra el texto leído del carnet mientras se confirma, y el aviso de "estudiante no encontrado" no lo repite.
* Cada usuario puede hacer hasta 120 lecturas por minuto.

Limitación conocida: los carnets más antiguos, cuyo código no es un QR con la dirección del Registro Civil, todavía no se reconocen. En ese caso se digita el RUT.

---

## 6. Estructura del repositorio

```text
Fase 1/                    Evidencias de la Fase 1 (grupales e individuales)
Fase 2/                    Documentos de la Fase 2 (versión ágil)
Codigo Proyecto/
├── puntopartida/              Versión estática del frontend
└── punto_participa_project/   Aplicación Django
    ├── gestion/               Lógica de la aplicación
    │   ├── migrations/        Migraciones de la base de datos
    │   ├── static/            JavaScript y CSS
    │   ├── templates/         Plantillas HTML
    │   ├── templatetags/      Filtros de plantilla (formato del RUT)
    │   └── tests_*.py         Pruebas automatizadas
    ├── punto_participa/       Configuración del proyecto Django
    ├── Dockerfile
    ├── docker-compose.yml
    ├── entrypoint.sh          Script de arranque del contenedor
    ├── env.example            Plantilla de variables de entorno
    └── requirements.txt
```

---

## 7. Seguridad

* Credenciales y claves fuera del código, en variables de entorno (`.env`).
* Rol obligatorio para cada usuario y permisos según el rol y la propiedad de cada actividad.
* Documento de identidad obligatorio para cada usuario; al cambiarlo, el servidor pide confirmación y deja registro en la auditoría.
* Límite de intentos en el inicio de sesión y en la recuperación de contraseña (5 intentos por IP cada 15 minutos).
* Límite de lecturas por usuario en la pantalla del escáner (120 por minuto), con aviso en pantalla al superarlo.
* Recuperación de contraseña mediante token y cambio de clave obligatorio cuando corresponde.
* Validación de imágenes subidas, con eliminación de metadatos EXIF.
* Protección de las exportaciones CSV y Excel contra inyección de fórmulas.
* Tolerancia a caracteres especiales en los datos de entrada y escape en la salida.
* Registro de auditoría de las acciones del sistema.
* Política de Privacidad pública (`/privacidad/`) y aceptación obligatoria al inscribirse, registrada en la auditoría. El texto es un borrador pendiente de revisión de Duoc UC.

### Pendientes antes de producción

* Envío de correos por SMTP con una cuenta institucional (hoy salen por consola).
* Lectura de la IP real del visitante cuando el sistema quede detrás de un proxy, para que el límite de intentos cuente por visitante.
* Política de privacidad y casilla de consentimiento en la inscripción pública.
* Derecho al olvido (anonimizar en vez de borrar en cascada).

---

## 8. Pruebas automatizadas

La suite tiene **319 tests** y se ejecuta con:

```powershell
docker compose exec web python manage.py test --noinput
```

En paralelo termina en cerca de 70 segundos, frente a unos 290 en serie:

```powershell
docker compose exec web python manage.py test --parallel --noinput
```

Las pruebas usan una base de datos temporal con datos inventados, así que no tocan los datos del sistema. Para correr solo un área, indica su archivo, por ejemplo:

```powershell
docker compose exec web python manage.py test gestion.tests_ratelimit --noinput
```

Los reportes y el dashboard cuentan como inscritos a quienes tienen una inscripción confirmada, sin exigir asistencia, y respetan los filtros de carrera, jornada y escuela. Hoy todas las inscripciones están confirmadas, porque la cancelación y la lista de espera aún no están habilitadas.

Qué se verifica, por tema:

| Tema | Qué se verifica | Archivos |
| --- | --- | --- |
| Autenticación y contraseñas | Inicio de sesión con credenciales válidas e inválidas, usuario inactivo que no entra, cierre de sesión, redirección `next` permitida solo hacia rutas internas, cambio de contraseña (clave actual incorrecta, confirmación distinta), recuperación por token (token inválido, contraseña débil) y cambio de clave obligatorio. | `tests_extremos`, `tests_integrales`, `tests_views_criticas` |
| Límite de intentos | El sexto intento de login se bloquea; el escáner responde un aviso en JSON al pasar el tope y el límite es por usuario. | `tests_ratelimit` |
| Permisos por rol | Qué puede abrir cada rol (Administrador, Creador de Evento, Encargado de Registrar y usuario anónimo), que un creador no vea actividades de otro, que el Encargado no acceda a reportes, usuarios ni auditoría, respuestas 401 y 403 en los endpoints JSON y rechazo de peticiones sin token CSRF. | `tests_roles_completo`, `tests`, `tests_decorators_utils`, `tests_adicionales` |
| Usuarios y documento de identidad | Documento obligatorio, guardado normalizado, rechazo de duplicados con mensaje claro, confirmación al cambiarlo, registro en la auditoría y que bloquear a un usuario siga funcionando. | `tests_rut_usuarios`, `tests_caracteres` |
| RUT, RUN provisorio y pasaporte | Limpieza de puntos y guion, validación del dígito verificador, documentos extranjeros, búsqueda del alumno en distintos formatos y formato de pantalla (`20.001.550-9`). | `tests`, `tests_decorators_utils`, `tests_formato_rut` |
| Escáner de asistencia | Registro por RUT, QR y código de barras, confirmación en dos etapas, rechazo de asistencia duplicada, de talleres sin inscripción y de actividades inactivas, lectura con teclado en español e inglés y que el aviso no repita el texto del carnet. | `tests_views_criticas`, `tests_escaner_teclado`, `tests_integrales`, `tests_adicionales` |
| Datos hostiles y caracteres especiales | Apóstrofes y tildes en los nombres, caracteres nulos y de control, normalización Unicode, y que entradas o parámetros hostiles no generen error 500 ni reflejen HTML. | `tests`, `tests_caracteres`, `tests_parametros` |
| Exportaciones | Protección contra fórmulas en CSV y Excel, limpieza de caracteres de control, BOM y separador `;` para que los CSV se abran en columnas en el Excel chileno, y libros válidos. | `tests_exportaciones`, `tests_extremos`, `tests_integrales` |
| Actividades, inscripciones y cupos | Crear, editar y eliminar actividades, confirmación al editar una con datos, validación de fechas y cupos, inscripción pública (duplicados, alumno inexistente, sin cupos, actividad finalizada o cancelada) y recálculo de cupos. | `tests_integrales`, `tests_adicionales`, `tests_extremos` |
| Invitaciones por correo | Envío y registro de la notificación, fallo de SMTP registrado como fallido, límite por envío y previsualización. | `tests_adicionales`, `tests_extremos`, `tests_integrales` |
| Reportes y auditoría | Dashboard y reportes exigen inicio de sesión, cada creador ve solo lo suyo, la auditoría guarda datos de la petición y su exportación es solo para el Administrador. | `tests_integrales`, `tests_extremos`, `tests_roles_completo` |
| Resistencia y consistencia | Carga de muchas inscripciones y asistencias sin duplicados, inscripciones simultáneas que no superan los cupos, y reversión de los cambios cuando ocurre un error. | `tests_resistencia` |

Lo que las pruebas automáticas no cubren: el JavaScript de las pantallas y el lector físico de códigos se verifican a mano.

---

## 9. Integrantes del equipo

| Integrante | Rol | Responsabilidades |
| --- | --- | --- |
| **Gabriel González** | Jefe de Proyecto y Desarrollador Backend | Scrum Master, arquitectura y desarrollo backend, ciberseguridad |
| **Pablo Rebolledo** | Desarrollador Frontend | Diseño UX/UI, maquetación, desarrollo frontend, conexión frontend/backend |
| **Diverson Nonnombre** | Encargado de Base de Datos y QA | Modelamiento PostgreSQL, gestión de la base de datos, QA y testing, consultas para reportes |

---

## 10. Metodología de trabajo

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

## 11. Arquitectura de la solución

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
│  • Actividades        • Asistencia           │
│  • Reportes           • Auditoría            │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 PostgreSQL 16                │
│                                              │
│  • Usuarios           • Inscripciones        │
│  • Alumnos            • Asistencias          │
│  • Actividades        • Registro de auditoría│
└──────────────────────────────────────────────┘
```

Todo el sistema se ejecuta con Docker Compose en dos servicios: `db` (PostgreSQL) y `web` (Django con Gunicorn).

---

## 12. Código del proyecto

La carpeta `Codigo Proyecto` contiene el código del sistema Punto Participa. El historial de commits fue reconstruido el 05/10/2026 a partir de respaldos locales (archivos zip); la fecha de cada commit corresponde a la fecha del respaldo del que proviene.
