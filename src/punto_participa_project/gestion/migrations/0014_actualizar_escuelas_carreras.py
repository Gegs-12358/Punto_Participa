# gestion/migrations/0014_actualizar_escuelas_carreras.py

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def actualizar_escuelas(apps, schema_editor):
    # Obtenemos el modelo Carrera en su estado histórico (seguro para migraciones)
    Carrera = apps.get_model('gestion', 'Carrera')

    # BD recién creada (tests, CI, entornos vacíos): no hay carreras que actualizar.
    if not Carrera.objects.exists():
        return

    # Mapeo exacto según las 13 carreras de la Sede Alameda
    escuelas_por_carrera = {
        # Escuela de Construcción (7 carreras)
        'Ingeniería en Construcción': 'Construcción',
        'Ingeniería en Prevención de Riesgos': 'Construcción',
        'Técnico en Construcción': 'Construcción',
        'Técnico Topógrafo Geomático': 'Construcción',
        'Técnico en Instalaciones y Proyectos Eléctricos': 'Construcción',
        'Dibujo y Modelamiento Arquitectónico y Estructural': 'Construcción',
        'Restauración de Bienes Patrimoniales': 'Construcción',

        # Escuela de Administración y Negocios (5 carreras)
        'Ingeniería en Administración Financiera': 'Administración y Negocios',
        'Ingeniería en Administración de Recursos Humanos': 'Administración y Negocios',
        'Ingeniería en Gestión Logística': 'Administración y Negocios',
        'Ingeniería en Comercio Exterior': 'Administración y Negocios',
        'Auditoría': 'Administración y Negocios',

        # Escuela de Informática y Telecomunicaciones (1 carrera)
        'Ingeniería en Informática': 'Informática y Telecomunicaciones',
    }

    # Recorremos el diccionario y actualizamos
    for nombre, escuela in escuelas_por_carrera.items():
        # Usamos update() directamente para ser eficientes y evitar múltiples saves
        # Filtramos por nombre exacto (que es unique)
        updated = Carrera.objects.filter(nombre=nombre).update(escuela=escuela)
        if updated:
            logger.info("Actualizada: '%s' -> '%s'", nombre, escuela)
        else:
            logger.debug("No encontrada: '%s' (no se actualizó)", nombre)


def reverse_actualizar_escuelas(apps, schema_editor):
    # Función para deshacer la migración (opcional)
    # Ponemos el campo escuela en NULL para las carreras que actualizamos
    Carrera = apps.get_model('gestion', 'Carrera')

    if not Carrera.objects.exists():
        return

    nombres_actualizados = [
        'Ingeniería en Construcción', 'Ingeniería en Prevención de Riesgos',
        'Técnico en Construcción', 'Técnico Topógrafo Geomático',
        'Técnico en Instalaciones y Proyectos Eléctricos',
        'Dibujo y Modelamiento Arquitectónico y Estructural',
        'Restauración de Bienes Patrimoniales', 'Ingeniería en Administración Financiera',
        'Ingeniería en Administración de Recursos Humanos', 'Ingeniería en Gestión Logística',
        'Ingeniería en Comercio Exterior', 'Auditoría', 'Ingeniería en Informática',
    ]
    Carrera.objects.filter(nombre__in=nombres_actualizados).update(escuela=None)
    logger.debug("Migración revertida: escuelas puestas en NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0012_alter_alumno_rut_alter_usuariosistema_rut'),
    ]

    operations = [
        migrations.RunPython(actualizar_escuelas, reverse_actualizar_escuelas),
    ]