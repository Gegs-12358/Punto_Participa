"""
Contenido de los correos. Cada correo tiene dos plantillas con el mismo nombre en templates/gestion/correos/: la
.html (la que ve casi todo el mundo) y la .txt (la que muestran los programas de solo texto y la que se lee en los
registros). Las dos reciben el mismo contexto, así que dicen lo mismo, con los mismos datos y enlaces.
La previsualización usa esta misma función: lo que se ve ahí es lo que se envía.
"""
from django.template.loader import render_to_string


def armar(nombre, contexto):
    """(texto, html) del correo `nombre` (por ejemplo 'invitacion')."""
    base = f'gestion/correos/{nombre}'
    return render_to_string(f'{base}.txt', contexto).strip() + '\n', render_to_string(f'{base}.html', contexto)
