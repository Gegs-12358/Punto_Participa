# Punto Participa

Plataforma web para la gestión de actividades, talleres, inscripciones y control de asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

\---

## 1\. Descripción del proyecto

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

|Rol|Qué hace|
|-|-|
|**Administrador**|Gestiona usuarios, roles, actividades y reportes. Tiene acceso completo.|
|**Creador de Evento**|Crea y gestiona actividades y talleres, y envía invitaciones por correo.|
|**Encargado de Registrar**|Registra la asistencia presencial durante las actividades.|

Los **estudiantes no tienen cuenta**: consultan los talleres disponibles y se inscriben con su RUT desde el formulario público de inscripción.

\---

## 2\. Estado del proyecto

El proyecto está en desarrollo y funciona de punta a punta en un entorno local con Docker. Hoy se encuentra en etapa de pruebas internas y **todavía no está publicado en un servidor de producción**.

* Suite de pruebas automatizadas: 287 tests.
* Despliegue en la nube: **por definir**. Actualmente se ejecuta en local con Docker.

\---

## 3\. Tecnologías

|Tecnología|Uso|
|-|-|
|**HTML, CSS y JavaScript**|Interfaces web|
|**Python 3.12**|Backend|
|**Django 6.1**|Framework del backend|
|**PostgreSQL 16**|Base de datos|
|**Gunicorn**|Servidor de aplicación|
|**WhiteNoise**|Entrega de archivos estáticos|
|**Docker y Docker Compose**|Ejecución reproducible del sistema|
|**Git y GitHub**|Control de versiones y repositorio|

\---

## 4\. Cómo ejecutar el proyecto localmente

### Requisitos

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y en ejecución.
* Git.

No hace falta instalar Python ni PostgreSQL: todo corre dentro de contenedores.

### Pasos

1. **Clonar el repositorio y entrar a la carpeta del proyecto Django:**

```powershell
   git clone https://github.com/Gegs-12358/Punto\_Participa.git
   cd Punto\_Participa\\"Codigo Proyecto"\\punto\_participa\_project
   ```

2. **Crear el archivo `.env`** en esa carpeta (junto a `manage.py`) copiando la plantilla incluida en el repositorio:

```powershell
   Copy-Item env.example .env
   ```

   Luego abre `.env` y reemplaza los valores de ejemplo. El archivo `.env` nunca se sube al repositorio. Variables:

|Variable|Qué es|
|-|-|
|`SECRET\_KEY`|Clave secreta de Django (64 caracteres alfanuméricos aleatorios).|
|`DB\_NAME`, `DB\_USER`, `DB\_PASSWORD`|Nombre, usuario y clave de la base de datos. PostgreSQL los toma de aquí al crearse.|
|`DB\_HOST`, `DB\_PORT`|Los define `docker-compose.yml` dentro de Docker; en la plantilla quedan solo como referencia.|
|`EMAIL\_HOST\_USER`, `EMAIL\_HOST\_PASSWORD`|Cuenta de Gmail y su clave de aplicación para enviar correos.|
|`SITE\_URL`|Dirección base del sistema, usada en los enlaces de los correos.|
|`MAX\_INVITACIONES\_POR\_ENVIO`|Máximo de invitaciones por envío.|
|`DEBUG`, `ALLOWED\_HOSTS`|Modo de depuración y dominios permitidos.|

   Reglas para los valores:

   * Sin comillas, sin espacios (tampoco al final de la línea) y **sin el signo `$`**: Docker Compose lo interpreta como variable y rompe la clave.
   * Usa claves largas y aleatorias, distintas para cada integrante, y nunca las compartas por chat ni las subas a GitHub.
   * Hoy el envío real de correos está desactivado en la configuración (los correos salen por consola), así que en pruebas las claves de Gmail pueden quedar de ejemplo.
3. **Construir y levantar el sistema:**

```powershell
   docker compose up -d --build
   ```

   La primera vez demora, porque descarga las imágenes. Al arrancar, el contenedor espera a PostgreSQL, aplica las migraciones, crea la tabla de caché del límite de intentos, reúne los archivos estáticos e inicia Gunicorn.

4. **Abrir el sistema** en el navegador: [http://localhost:8000/login/](http://localhost:8000/login/)

### Comandos útiles

|Acción|Comando|
|-|-|
|Ver el estado de los servicios|`docker compose ps`|
|Ver los registros de la aplicación|`docker compose logs web --tail 25`|
|Correr todos los tests|`docker compose exec web python manage.py test --noinput`|
|Reiniciar tras editar archivos `.py` o `.html`|`docker compose restart web`|
|Aplicar un cambio en `.env`|`docker compose up -d --force-recreate web`|
|Reconstruir tras cambiar `Dockerfile`, `requirements.txt`, `entrypoint.sh` o `.dockerignore`|`docker compose up -d --build`|
|Detener el sistema (conserva los datos)|`docker compose down`|

### Advertencia sobre los datos

Los datos viven en volúmenes de Docker (`pgdata` para la base de datos y `media\_volume` para los archivos subidos). **Nunca ejecutes** `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`, porque borran esos volúmenes y se pierde toda la información.

\---

## 5\. Estructura del repositorio

```text
Codigo Proyecto/
├── puntopartida/              Frontend estático (prototipo de interfaz)
└── punto\_participa\_project/   Aplicación Django
    ├── gestion/               Lógica de la aplicación (vistas, modelos, permisos, tests)
    ├── punto\_participa/       Configuración del proyecto Django
    ├── Dockerfile
    ├── docker-compose.yml
    ├── entrypoint.sh          Script de arranque del contenedor
    └── requirements.txt
```

\---

## 6\. Seguridad

* Credenciales y claves fuera del código, en variables de entorno (`.env`).
* Rol obligatorio para cada usuario y permisos según el rol y la propiedad de cada actividad.
* Límite de intentos en el inicio de sesión y en la recuperación de contraseña (5 intentos por IP cada 15 minutos).
* Límite de escaneos por usuario en la pantalla de registro de asistencia (120 por minuto), con aviso en pantalla al superarlo.
* El escáner no repite en pantalla el texto leído del carnet y reconoce su QR con cualquier distribución de teclado (español o inglés).
* Recuperación de contraseña mediante token y cambio de clave obligatorio cuando corresponde.
* Validación de imágenes subidas, con eliminación de metadatos EXIF.
* Protección de las exportaciones CSV y Excel contra inyección de fórmulas.
* Tolerancia a caracteres especiales en los datos de entrada y escape en la salida.
* Registro de auditoría de las acciones del sistema.

\---

## 7\. Integrantes del equipo

|Integrante|Rol|Responsabilidades|
|-|-|-|
|**Gabriel González**|Jefe de Proyecto y Desarrollador Backend|Scrum Master, arquitectura y desarrollo backend, ciberseguridad|
|**Pablo Rebolledo**|Desarrollador Frontend|Diseño UX/UI, maquetación, desarrollo frontend, conexión frontend/backend|
|**Diverson Nonnombre**|Encargado de Base de Datos y QA|Modelamiento PostgreSQL, gestión de la base de datos, QA y testing, consultas para reportes|

\---

## 8\. Metodología de trabajo

El equipo trabaja con **Scrum**, y estima las funcionalidades mediante **Planning Poker**. El trabajo se divide en épicas y funcionalidades que se desarrollan por sprints:

* Registro de asistencia.
* Gestión de cupos e inscripciones.
* Invitaciones por correo.
* Usuarios y roles.
* Reportes y métricas.
* Gestión de actividades.
* Auditoría y trazabilidad.
* Respaldo y continuidad de datos.

\---

## 9\. Arquitectura de la solución

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

\---

## 10\. Código del proyecto

La carpeta `Codigo Proyecto` contiene el código del sistema Punto Participa. El historial de commits fue reconstruido el 05/10/2026 a partir de respaldos locales (archivos zip); la fecha de cada commit corresponde a la fecha del respaldo del que proviene.

