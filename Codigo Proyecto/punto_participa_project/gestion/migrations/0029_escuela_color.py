"""
Color de cada escuela en el catálogo (antes estaba fijo en el código, por nombre).

A las escuelas existentes se les pone su color oficial web de Duoc UC si se conoce;
las demás quedan sin color y los gráficos las muestran en gris hasta que se elija uno
en Catálogos > Escuelas.
"""
import django.core.validators
from django.db import migrations, models

# Copia de views.COLOR_POR_ESCUELA al momento de esta migración (no se importa desde
# views para que la migración no cambie si esa lista cambia después).
COLORES_OFICIALES = {
    'Escuela de Administración y Negocios': '#AC4FC6',
    'Escuela de Administración y Finanzas': '#AC4FC6',
    'Escuela de Comunicación': '#D50032',
    'Escuela de Comunicaciones': '#D50032',
    'Escuela de Construcción': '#E87722',
    'Escuela de Diseño': '#C4D600',
    'Escuela de Gastronomía': '#FF585D',
    'Escuela de Informática y Telecomunicaciones': '#307FE2',
    'Escuela de Ingeniería': '#43B02A',
    'Escuela de Recursos Naturales': '#43B02A',
    'Escuela de Salud': '#5BC2E7',
    'Escuela de Turismo': '#00A499',
}


def poner_colores(apps, schema_editor):
    Escuela = apps.get_model('gestion', 'Escuela')
    for escuela in Escuela.objects.filter(color=''):
        color = COLORES_OFICIALES.get(escuela.nombre.strip())
        if color:
            escuela.color = color
            escuela.save(update_fields=['color'])


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0028_escuela_carrera_activo'),
    ]

    operations = [
        migrations.AddField(
            model_name='escuela',
            name='color',
            field=models.CharField(
                blank=True, default='', max_length=7,
                validators=[django.core.validators.RegexValidator(
                    '^#[0-9A-Fa-f]{6}$', 'Usa un color como #307FE2.')],
            ),
        ),
        migrations.RunPython(poner_colores, migrations.RunPython.noop),
    ]
