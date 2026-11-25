"""
Crea el catálogo de escuelas y agrega "activo" a las carreras.

Las escuelas se llenan con las que ya tienen las carreras. Las que solo difieren en
mayúsculas o espacios quedan como una sola: se usa la forma más repetida y las carreras
se actualizan a esa forma. Todas las carreras existentes quedan activas.
"""
from collections import Counter, defaultdict

from django.db import migrations, models


def _limpiar(texto):
    return ' '.join((texto or '').split())


def poblar_escuelas(apps, schema_editor):
    Carrera = apps.get_model('gestion', 'Carrera')
    Escuela = apps.get_model('gestion', 'Escuela')

    grupos = defaultdict(Counter)          # clave sin mayúsculas -> {forma escrita: veces}
    for escuela in Carrera.objects.values_list('escuela', flat=True):
        limpio = _limpiar(escuela)
        if limpio:
            grupos[limpio.casefold()][limpio] += 1

    canonicos = {clave: formas.most_common(1)[0][0] for clave, formas in grupos.items()}
    for nombre in canonicos.values():
        Escuela.objects.get_or_create(nombre=nombre)

    for carrera in Carrera.objects.only('id', 'escuela').iterator():
        limpio = _limpiar(carrera.escuela)
        canonico = canonicos.get(limpio.casefold()) if limpio else None
        if canonico and carrera.escuela != canonico:
            carrera.escuela = canonico
            carrera.save(update_fields=['escuela'])


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0027_lugar_numero'),
    ]

    operations = [
        migrations.CreateModel(
            name='Escuela',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('activo', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'verbose_name': 'Escuela',
                'verbose_name_plural': 'Escuelas',
                'ordering': ['nombre'],
            },
        ),
        migrations.AddField(
            model_name='carrera',
            name='activo',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(poblar_escuelas, migrations.RunPython.noop),
    ]