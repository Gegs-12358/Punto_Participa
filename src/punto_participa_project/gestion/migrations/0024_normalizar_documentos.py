import re

from django.db import migrations


def _normalizar(valor):
    """Solo letras y numeros, en mayusculas. Vacio -> None."""
    if not valor:
        return None
    limpio = re.sub(r'[^0-9A-Za-z]', '', str(valor)).upper()
    return limpio or None


def normalizar_documentos(apps, schema_editor):
    for nombre_modelo in ('Alumno', 'UsuarioSistema'):
        Modelo = apps.get_model('gestion', nombre_modelo)

        # 1) Calcular todo antes de escribir nada, y abortar si hay choques.
        cambios = {}
        vistos = {}
        for pk, rut in Modelo.objects.exclude(rut__isnull=True).values_list('pk', 'rut'):
            nuevo = _normalizar(rut)
            if nuevo is not None:
                if nuevo in vistos:
                    raise RuntimeError(
                        f'{nombre_modelo}: dos filas (ids {vistos[nuevo]} y {pk}) '
                        'quedarian con el mismo documento al normalizar. '
                        'No se cambio nada.'
                    )
                vistos[nuevo] = pk
            if nuevo != rut:
                cambios[pk] = nuevo

        # 2) Aplicar. update() evita el save() y no depende de codigo de la app.
        for pk, nuevo in cambios.items():
            Modelo.objects.filter(pk=pk).update(rut=nuevo)


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0023_alter_alumno_rut'),
    ]

    operations = [
        # Sin marcha atras real: el guion original no se puede reconstruir.
        # Para volver atras se restaura el respaldo.
        migrations.RunPython(normalizar_documentos, migrations.RunPython.noop),
    ]