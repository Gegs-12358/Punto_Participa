# Punto Participa

Sistema de gestión de actividades y asistencia del **Punto Estudiantil** de Duoc UC Sede Alameda.

## Descripción

Punto Participa es una plataforma web que centraliza la gestión de actividades, inscripciones, control de cupos y registro de asistencia del Punto Estudiantil. Reemplaza el uso de planillas Excel y formularios externos por un sistema centralizado, seguro y con trazabilidad completa.

## Características Principales

- **Gestión de actividades**: CRUD completo de talleres y actividades masivas.
- **Inscripción pública**: Los estudiantes se inscriben a talleres mediante enlace directo recibido por correo.
- **Control de cupos**: Validación transaccional para evitar sobreventa.
- **Registro de asistencia**: Escáner que soporta QR, código de barras y RUT manual.
- **Invitaciones por correo**: Envío segmentado por carrera y jornada.
- **Reportes**: Exportación a Excel/CSV con filtros por actividad, carrera, jornada y fecha.
- **Auditoría**: Registro completo de acciones de usuarios.
- **Roles**: Administrador, Creador de Evento, Encargado de Registrar.

## Perfiles de Usuario

| Rol | Permisos |
|-----|----------|
| **Administrador** | Acceso completo: usuarios, roles, actividades, reportes, auditoría. |
| **Creador de Evento** | Gestión de sus propias actividades y reportes de las mismas. |
| **Encargado de Registrar** | Solo módulo escáner para registrar asistencia presencial. |
| **Estudiante** | Sin login: accede por enlace directo para inscribirse a talleres. |

## Tecnologías

| Capa | Tecnología |
|------|------------|
| **Frontend** | HTML5, CSS3, JavaScript, Chart.js |
| **Backend** | Python 3.12 + Django 5.x |
| **Base de Datos** | PostgreSQL 15 |
| **Servidor WSGI** | Gunicorn |
| **Estáticos** | WhiteNoise |
| **Contenedores** | Docker + Docker Compose |
| **Tests** | Django TestCase, coverage.py |
| **Control de versiones** | Git + GitHub |

## Requisitos Previos

- **Docker Desktop** instalado y corriendo.
- **Git** instalado (opcional, para clonar el repositorio).
- **4 GB de RAM** disponibles mínimo.

## Instalación con Docker (recomendado)

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/punto-participa.git
cd punto-participa