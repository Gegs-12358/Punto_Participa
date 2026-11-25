"""
Crea el catálogo de lugares y lo llena con los lugares ya escritos en las actividades.

Los lugares que solo difieren en mayúsculas o espacios ("Auditorio", " auditorio ",
"AUDITORIO") quedan como uno solo: se usa la forma más repetida y las actividades
se actualizan a esa forma. No se pierde ninguna actividad.
"""
from collections import Counter, defaultdict

from django.db import migrations, models


def _limpiar(texto):
    return ' '.join((texto or '').split())


def poblar_lugares(apps, schema_editor):
    Actividad = apps.get_model('gestion', 'Actividad')
    Lugar = apps.get_model('gestion', 'Lugar')

    grupos = defaultdict(Counter)          # clave sin mayúsculas -> {forma escrita: veces}
    for lugar in Actividad.objects.values_list('lugar', flat=True):
        limpio = _limpiar(lugar)
        if limpio:
            grupos[limpio.casefold()][limpio] += 1

    canonicos = {clave: formas.most_common(1)[0][0] for clave, formas in grupos.items()}
    for nombre in canonicos.values():
        Lugar.objects.get_or_create(nombre=nombre)

    for actividad in Actividad.objects.only('id', 'lugar').iterator():
        limpio = _limpiar(actividad.lugar)
        canonico = canonicos.get(limpio.casefold()) if limpio else None
        if canonico and actividad.lugar != canonico:
            actividad.lugar = canonico
            actividad.save(update_fields=['lugar'])


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0025_alumno_activo'),
    ]

    operations = [
        migrations.CreateModel(
            name='Lugar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200, unique=True)),
                ('activo', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'verbose_name': 'Lugar',
                'verbose_name_plural': 'Lugares',
                'ordering': ['nombre'],
            },
        ),
        migrations.RunPython(poblar_lugares, migrations.RunPython.noop),
    ]