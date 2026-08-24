# Punto Participa

## 1. Nombre del proyecto

**Punto Participa**

Plataforma web para la gestión de actividades, talleres, inscripciones y control de asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

---

## 2. Descripción del proyecto

**Punto Participa** es una plataforma web que busca centralizar y optimizar la gestión de actividades y participación estudiantil del Punto Estudiantil.

Actualmente, el registro de participación se realiza mediante planillas Excel con macros que son trasladadas manualmente, lo que dificulta la centralización de la información, el control de acceso, el resguardo de los datos y la generación de información histórica.

Además, para los talleres con cupos limitados se utilizan formularios externos, dificultando que los estudiantes puedan conocer la disponibilidad de vacantes en tiempo real.

La solución propuesta permitirá gestionar desde una plataforma centralizada:

* Actividades masivas.
* Talleres con cupos limitados.
* Inscripciones de estudiantes.
* Registro de asistencia.
* Usuarios y roles.
* Reportes de participación.

### ¿A quién está dirigido?

El sistema estará dirigido principalmente a:

* **Administradores del Punto Estudiantil:** responsables de gestionar actividades, talleres, usuarios y reportes.
* **Operadores:** encargados de registrar la asistencia durante las actividades presenciales.
* **Estudiantes:** usuarios que podrán consultar e inscribirse en talleres disponibles.

### ¿Qué problema resuelve?

Punto Participa busca reemplazar procesos manuales y dispersos por una solución web centralizada, permitiendo mejorar la gestión de la participación estudiantil, reducir registros duplicados, facilitar el control de asistencia y disponer de información consolidada para reportes y análisis.

La propuesta contempla el registro de asistencia mediante digitación del RUT, lectura del código QR de la cédula de identidad o lectura del código de barras mostrado en la aplicación Vivo Duoc.

---

## 3. Tecnologías utilizadas

La solución será desarrollada utilizando las siguientes tecnologías:

| Tecnología     | Uso                              |
| -------------- | -------------------------------- |
| **HTML**       | Estructura de las interfaces web |
| **CSS**        | Diseño y estilos                 |
| **JavaScript** | Interactividad del frontend      |
| **Python**     | Desarrollo del backend           |
| **Django**     | Framework del backend            |
| **PostgreSQL** | Base de datos                    |
| **Git**        | Control de versiones             |
| **GitHub**     | Repositorio del proyecto         |

Estas tecnologías corresponden a la base tecnológica definida para el proyecto.

### Cloud

**Por definir durante el desarrollo del proyecto.**

Actualmente no se ha definido una plataforma de despliegue en la nube.

---

## 4. Instrucciones para ejecutar el proyecto localmente

### Estado actual

El proyecto se encuentra actualmente en una **etapa inicial de definición** y el repositorio todavía no contiene la implementación de la aplicación.

Por este motivo, **actualmente no existe una versión funcional que pueda ejecutarse localmente**.

El repositorio será utilizado para incorporar progresivamente el código fuente, configuración, dependencias y documentación necesarias para ejecutar la aplicación.

### Repositorio

[GitHub — Punto Participa](https://github.com/Gegs-12358/Punto_Participa)

### Próximamente

Cuando se implemente el proyecto, esta sección será actualizada con las instrucciones para:

1. Clonar el repositorio.
2. Crear el entorno virtual de Python.
3. Instalar las dependencias.
4. Configurar PostgreSQL.
5. Configurar las variables de entorno.
6. Ejecutar las migraciones de Django.
7. Iniciar el servidor local.

---

## 5. Integrantes del equipo y roles

| Integrante             | Rol                                      |
| ---------------------- | ---------------------------------------- |
| **Gabriel González**   | Jefe de Proyecto y Desarrollador Backend |
| **Pablo Rebolledo**    | Desarrollador Frontend                   |
| **Diverson Nonnombre** | Encargado de Base de Datos y QA          |

### Gabriel González

**Jefe de Proyecto y Desarrollador Backend**

Responsabilidades:

* Scrum Master.
* Arquitectura Backend.
* Desarrollo Backend.
* Ciberseguridad.

### Pablo Rebolledo

**Desarrollador Frontend**

Responsabilidades:

* Diseño UX/UI.
* Maquetación web.
* Desarrollo Frontend.
* Conexión Frontend/Backend.

### Diverson Nonnombre

**Encargado de Base de Datos y QA**

Responsabilidades:

* Modelamiento PostgreSQL.
* Gestión de base de datos.
* QA / Testing.
* Consultas para reportes.

Los roles del equipo están definidos en la propuesta del proyecto.

---

## 6. Metodología de trabajo

El equipo utilizará una metodología de trabajo basada en **Scrum**.

La planificación y estimación de las funcionalidades se realizará mediante **Planning Poker**, permitiendo dimensionar el trabajo y organizar las actividades del equipo.

El proyecto será dividido en funcionalidades y épicas que serán desarrolladas progresivamente.

Entre las principales funcionalidades consideradas se encuentran:

* Registro de asistencia.
* Gestión de cupos e inscripciones.
* Invitaciones por correo.
* Usuarios y roles.
* Reportes y métricas.
* Gestión de actividades.
* Auditoría y trazabilidad.
* Respaldo y continuidad de datos.

La planificación del proyecto contempla la distribución de estas funcionalidades durante las semanas de desarrollo.

---

## 7. Arquitectura de la solución

La solución será desarrollada como una aplicación web utilizando una arquitectura basada en tres componentes principales:

### Frontend

Será la capa con la que interactuarán los usuarios del sistema.

**Tecnologías:**

* HTML
* CSS
* JavaScript

### Backend

Será responsable de procesar la lógica de negocio de la aplicación, incluyendo usuarios, actividades, inscripciones, asistencia y reportes.

**Tecnologías:**

* Python
* Django

### Base de datos

Será responsable de almacenar y centralizar la información del sistema.

**Tecnología:**

* PostgreSQL

### Diagrama de arquitectura propuesta

```text
                    ┌──────────────────────┐
                    │       USUARIOS       │
                    │                      │
                    │ Administrador        │
                    │ Operador             │
                    │ Estudiante           │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       FRONTEND       │
                    │                      │
                    │ HTML / CSS / JS      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       BACKEND        │
                    │                      │
                    │ Python / Django      │
                    │                      │
                    │ • Usuarios y roles   │
                    │ • Actividades        │
                    │ • Inscripciones      │
                    │ • Asistencia         │
                    │ • Reportes           │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      PostgreSQL      │
                    │                      │
                    │ • Usuarios           │
                    │ • Estudiantes        │
                    │ • Actividades        │
                    │ • Inscripciones      │
                    │ • Asistencias        │
                    └──────────────────────┘
```

> **Nota:** La arquitectura presentada corresponde a la propuesta inicial del proyecto y podrá ajustarse durante las etapas de diseño y desarrollo.

---

## Estado actual del proyecto

**Punto Participa se encuentra actualmente en etapa inicial.**

El repositorio será utilizado para incorporar progresivamente la implementación de la solución durante el desarrollo del Proyecto APT.

**Repositorio:**
https://github.com/Gegs-12358/Punto_Participa
