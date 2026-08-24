# Punto Participa

## 📌 Descripción del proyecto

**Punto Participa** es una plataforma web orientada a la gestión de actividades, talleres, inscripciones y control de asistencia del Punto Estudiantil de Duoc UC Sede Alameda.

El proyecto busca centralizar y optimizar el proceso de gestión de participación estudiantil, reemplazando el uso de planillas Excel y formularios externos por una solución web organizada y centralizada.

La plataforma estará dirigida principalmente a:

* **Administradores del Punto Estudiantil**, encargados de gestionar actividades, usuarios, talleres y reportes.
* **Operadores**, encargados de registrar la asistencia durante las actividades.
* **Estudiantes**, quienes podrán consultar e inscribirse en talleres con cupos disponibles.

El sistema contempla dos tipos principales de actividades:

* **Actividades masivas:** permiten registrar la asistencia presencial mediante digitación del RUT, lectura de código QR de la cédula o lectura del código de barras mostrado en la aplicación Vivo Duoc.
* **Talleres con cupo:** permiten que los estudiantes consulten la disponibilidad de vacantes y realicen su inscripción mediante la plataforma.

El problema principal que busca resolver es la gestión manual y dispersa de la información de participación, facilitando la centralización de datos, el control de acceso, el registro de asistencia y la generación de reportes.

---

## 🛠️ Tecnologías utilizadas

El proyecto utilizará inicialmente las siguientes tecnologías:

| Tecnología     | Uso                                     |
| -------------- | --------------------------------------- |
| **HTML**       | Estructura de las interfaces web        |
| **CSS**        | Diseño y estilos de la aplicación       |
| **JavaScript** | Interactividad del frontend             |
| **Python**     | Lenguaje de programación del backend    |
| **Django**     | Framework para el desarrollo backend    |
| **PostgreSQL** | Base de datos                           |
| **Git**        | Control de versiones                    |
| **GitHub**     | Repositorio y gestión del código fuente |

Estas corresponden a la base tecnológica definida para el proyecto.

> **Estado actual:** el proyecto se encuentra en una etapa inicial y el repositorio contiene actualmente el esqueleto de desarrollo. Las tecnologías serán implementadas progresivamente durante el desarrollo.

---

## 🚀 Instrucciones para ejecutar el proyecto localmente

Actualmente **Punto Participa se encuentra en una etapa inicial de desarrollo**, por lo que todavía no existe una versión funcional que requiera un procedimiento completo de instalación y ejecución.

Una vez implementada la estructura de Django y sus dependencias, esta sección será actualizada con:

1. Clonación del repositorio.
2. Creación y activación del entorno virtual.
3. Instalación de dependencias.
4. Configuración de PostgreSQL.
5. Configuración de variables de entorno.
6. Ejecución de migraciones.
7. Inicio del servidor local.

### Repositorio

**GitHub:**
https://github.com/Gegs-12358/Punto_Participa

---

## 👥 Integrantes del equipo

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
* Desarrollo frontend.
* Conexión frontend/backend.

### Diverson Nonnombre

**Encargado de Base de Datos y QA**

Responsabilidades:

* Modelamiento de PostgreSQL.
* Gestión de base de datos.
* QA / Testing.
* Consultas para reportes.

Los roles se encuentran definidos en la propuesta del proyecto.

---

## 🔄 Metodología de trabajo

El equipo trabajará utilizando una metodología basada en **Scrum**.

Para la planificación y estimación del trabajo se utilizará **Planning Poker**, permitiendo dimensionar las distintas funcionalidades y distribuirlas dentro del periodo de desarrollo.

El proyecto se organizará mediante épicas y tareas, realizando un desarrollo progresivo de las funcionalidades.

La planificación contempla la distribución de las épicas durante las semanas de trabajo definidas para el proyecto.

---

## 🏗️ Arquitectura de la solución

Punto Participa será desarrollado como una **aplicación web**, utilizando una arquitectura separada en frontend, backend y base de datos.

### Diagrama de arquitectura

```text
                  ┌─────────────────────────┐
                  │         USUARIOS        │
                  │                         │
                  │ Administrador           │
                  │ Operador                │
                  │ Estudiante              │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │        FRONTEND         │
                  │                         │
                  │ HTML + CSS + JavaScript │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │         BACKEND         │
                  │                         │
                  │      Python + Django    │
                  │                         │
                  │ • Usuarios y roles      │
                  │ • Actividades           │
                  │ • Inscripciones         │
                  │ • Asistencia            │
                  │ • Reportes              │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │       BASE DE DATOS     │
                  │                         │
                  │        PostgreSQL       │
                  │                         │
                  │ • Usuarios              │
                  │ • Estudiantes           │
                  │ • Actividades           │
                  │ • Inscripciones         │
                  │ • Asistencias           │
                  │ • Reportes              │
                  └─────────────────────────┘
```

### Componentes

**Frontend**

Será responsable de la interfaz con la que interactuarán administradores, operadores y estudiantes.

Tecnologías:

* HTML
* CSS
* JavaScript

**Backend**

Será responsable de la lógica de negocio y procesamiento de las funcionalidades de la plataforma.

Tecnologías:

* Python
* Django

**Base de datos**

PostgreSQL será utilizada para almacenar y centralizar la información relacionada con usuarios, estudiantes, actividades, inscripciones y asistencias.

**Control de acceso**

La solución contempla un sistema de roles que permitirá restringir las funcionalidades disponibles según el tipo de usuario.

---

## 📍 Estado del proyecto

**Punto Participa se encuentra actualmente en fase inicial de desarrollo.**

En esta etapa se está trabajando principalmente en la definición, planificación y construcción del esqueleto inicial de la solución.

Las funcionalidades y componentes descritos en este README corresponden a la **propuesta actual del proyecto** y serán implementados progresivamente durante las siguientes etapas.

---

## 📄 Proyecto

**Proyecto APT / CAPSTONE**
**Duoc UC — Escuela de Informática y Telecomunicaciones**

**Punto Participa**
