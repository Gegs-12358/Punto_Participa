# gestion/migrations/XXXX_actualizar_escuelas_carreras_v2.py

from django.db import migrations

def actualizar_escuelas(apps, schema_editor):
    # Obtenemos el modelo Carrera en su estado histórico (seguro para migraciones)
    Carrera = apps.get_model('gestion', 'Carrera')

    # Mapeo exacto según las 13 carreras de la Sede Alameda (el mismo que funcionó en el shell)
    escuelas_por_carrera = {
        # Escuela de Construcción
        'Ingeniería en Construcción': 'Construcción',
        'Ingeniería en Prevención de Riesgos': 'Construcción',
        'Técnico en Construcción': 'Construcción',
        'Técnico Topógrafo Geomático': 'Construcción',
        'Técnico en Instalaciones y Proyectos Eléctricos': 'Construcción',
        'Dibujo y Modelamiento Arquitectónico y Estructural': 'Construcción',
        'Restauración de Bienes Patrimoniales': 'Construcción',
        # Escuela de Administración y Negocios
        'Ingeniería en Administración Financiera': 'Administración y Negocios',
        'Ingeniería en Administración de Recursos Humanos': 'Administración y Negocios',
        'Ingeniería en Gestión Logística': 'Administración y Negocios',
        'Ingeniería en Comercio Exterior': 'Administración y Negocios',
        'Auditoría': 'Administración y Negocios',
        # Escuela de Informática y Telecomunicaciones
        'Ingeniería en Informática': 'Informática y Telecomunicaciones',
    }

    # Recorremos y actualizamos
    for nombre, escuela in escuelas_por_carrera.items():
        # Usamos update() para eficiencia
        updated = Carrera.objects.filter(nombre=nombre).update(escuela=escuela)
        if updated:
            print(f"✅ Actualizada: '{nombre}' -> '{escuela}'")
        else:
            print(f"⚠️ No encontrada: '{nombre}' (no se actualizó)")

def reverse_actualizar_escuelas(apps, schema_editor):
    # Revertir: poner escuela=NULL para las carreras que actualizamos
    Carrera = apps.get_model('gestion', 'Carrera')
    nombres_actualizados = [
        'Ingeniería en Construcción', 'Ingeniería en Prevención de Riesgos',
        'Técnico en Construcción', 'Técnico Topógrafo Geomático',
        'Técnico en Instalaciones y Proyectos Eléctricos',
        'Dibujo y Modelamiento Arquitectónico y Estructural',
        'Restauración de Bienes Patrimoniales', 'Ingeniería en Administración Financiera',
        'Ingeniería en Administración de Recursos Humanos', 'Ingeniería en Gestión Logística',
        'Ingeniería en Comercio Exterior', 'Auditoría', 'Ingeniería en Informática'
    ]
    Carrera.objects.filter(nombre__in=nombres_actualizados).update(escuela=None)
    print("🔄 Migración revertida: escuelas puestas en NULL")

class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0015_merge_20260902_2140'),  # <-- IMPORTANTE: este es el número de la última migración que tienes (según tu showmigrations)
    ]

    operations = [
        migrations.RunPython(actualizar_escuelas, reverse_actualizar_escuelas),
    ]