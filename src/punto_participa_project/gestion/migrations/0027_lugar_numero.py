"""
Número de sala: el catálogo de lugares indica qué lugares piden número ("Sala") y la
actividad guarda ese número aparte. Los datos existentes no cambian.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0026_lugar'),
    ]

    operations = [
        migrations.AddField(
            model_name='lugar',
            name='pide_numero',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='actividad',
            name='lugar_numero',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
    ]