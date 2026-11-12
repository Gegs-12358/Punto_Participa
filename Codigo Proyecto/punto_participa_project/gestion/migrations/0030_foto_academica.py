"""
"Foto" de carrera, escuela y jornada en cada inscripción y asistencia.

Los registros que ya existen se llenan con los datos que el alumno tiene HOY
(es lo mejor que hay: antes de esta migración no se guardaba). Desde aquí en
adelante, cada registro nuevo guarda los datos del momento en que se crea.

Se hace con UPDATE ... = (subconsulta) en la base, sin traer filas a Python,
para que sea rápido aunque haya muchas asistencias.
"""
from django.db import migrations, models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce, Lower, Trim


def llenar_fotos(apps, schema_editor):
    Alumno = apps.get_model('gestion', 'Alumno')
    Carrera = apps.get_model('gestion', 'Carrera')
    for nombre in ('Inscripcion', 'Asistencia'):
        Modelo = apps.get_model('gestion', nombre)
        alumno = Alumno.objects.filter(pk=OuterRef('alumno_id'))
        Modelo.objects.update(
            carrera=Coalesce(Subquery(alumno.values('carrera')[:1]), Value('')),
            jornada=Coalesce(Subquery(alumno.values('jornada')[:1]), Value('')),
        )
        escuela = (Carrera.objects
                   .annotate(_n=Lower(Trim('nombre')))
                   .filter(_n=Lower(Trim(OuterRef('carrera'))))
                   .exclude(escuela__isnull=True)
                   .values('escuela')[:1])
        Modelo.objects.exclude(carrera='').update(
            escuela=Coalesce(Subquery(escuela), Value('')))


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0029_escuela_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="asistencia",
            name="carrera",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Carrera (en ese momento)",
            ),
        ),
        migrations.AddField(
            model_name="asistencia",
            name="escuela",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Escuela (en ese momento)",
            ),
        ),
        migrations.AddField(
            model_name="asistencia",
            name="jornada",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="Jornada (en ese momento)",
            ),
        ),
        migrations.AddField(
            model_name="inscripcion",
            name="carrera",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Carrera (en ese momento)",
            ),
        ),
        migrations.AddField(
            model_name="inscripcion",
            name="escuela",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Escuela (en ese momento)",
            ),
        ),
        migrations.AddField(
            model_name="inscripcion",
            name="jornada",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="Jornada (en ese momento)",
            ),
        ),
        migrations.RunPython(llenar_fotos, migrations.RunPython.noop),
    ]
