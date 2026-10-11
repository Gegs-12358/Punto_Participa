from django import template

from gestion.utils import formatear_rut

register = template.Library()


@register.filter(name='rut_fmt')
def rut_fmt(valor):
    """Muestra un RUT con formato de pantalla (12.345.678-5).

    Solo para mostrar: lo guardado en la base no cambia. Un pasaporte
    se devuelve tal cual, y un valor vacío da texto vacío.
    """
    if not valor:
        return ''
    return formatear_rut(valor)