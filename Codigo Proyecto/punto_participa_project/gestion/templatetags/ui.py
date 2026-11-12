"""
Piezas de interfaz comunes (P-UI: unificación visual). Uso en una plantilla:

    {% load ui %}
    {% icono "editar" %}                                  -> ícono SVG
    {% acciones_filtro url_limpiar %}                     -> botones Filtrar y Limpiar (solo íconos, con aviso)
    {% chips_filtros "tipo=Tipo,estado=Estado" url %}     -> chips de "Filtros activos"

Reglas de la guía de estilo (docs/GUIA_ESTILO.md):
  - Barras de filtro y acciones de fila: solo ícono, con aviso (data-tooltip) y aria-label.
  - Acción principal de la pantalla: ícono y texto.
"""
from urllib.parse import urlencode

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..models import Actividad, Inscripcion, NotificacionCorreo

register = template.Library()

# Trazos de 24x24 (línea, sin relleno). Texto fijo del código: seguro de marcar como safe.
_TRAZOS = {
    'filtrar': '<path d="M3 4h18l-7 8.5V19l-4 2v-8.5z"/>',
    'limpiar': '<path d="M18 6 6 18M6 6l12 12"/>',
    'buscar': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    'ver': '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    'editar': '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m14 6 4 4"/>',
    'eliminar': '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    'bloquear': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    'desbloquear': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
    'participantes': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
                     '<path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
    'correo': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    'exportar': '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    'agregar': '<path d="M12 5v14M5 12h14"/>',
    'guardar': '<path d="m5 12 5 5L20 7"/>',
    'imprimir': '<path d="M7 9V3h10v6M7 17H4v-7h16v7h-3"/><rect x="7" y="14" width="10" height="7"/>',
    'cambiar': '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
    'finalizar': '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
    'actividad': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    'escuela': '<path d="M3 21h18M5 21V10M19 21V10M9 21v-6h6v6M2 10l10-6 10 6"/>',
}


@register.simple_tag
def icono(nombre, clase=''):
    """SVG del ícono `nombre`; hereda el color del texto (currentColor)."""
    trazo = _TRAZOS.get(nombre)
    if trazo is None:
        return ''
    return format_html(
        '<svg class="icono {}" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        'focusable="false">{}</svg>', clase, mark_safe(trazo))


@register.inclusion_tag('gestion/includes/acciones_filtro.html')
def acciones_filtro(url_limpiar):
    """Botones Filtrar (envía el formulario) y Limpiar (vuelve a la página sin filtros)."""
    return {'url_limpiar': url_limpiar}


# Valores que se muestran con su nombre legible en los chips
_LEGIBLES = {
    'tipo': dict(Actividad.TIPO_CHOICES),
    'estado': {**dict(Actividad.ESTADO_CHOICES), **dict(Inscripcion.ESTADO_CHOICES),
               **dict(NotificacionCorreo.ESTADO_CHOICES), 'activo': 'Activo', 'bloqueado': 'Bloqueado'},
}
_PAGINACION = {'page', 'page_act', 'page_det', 'orden'}


@register.inclusion_tag('gestion/includes/chips_filtros.html', takes_context=True)
def chips_filtros(context, etiquetas, url_limpiar, valores=None):
    """
    Chips de los filtros que están activos en la URL.

    etiquetas: "param=Etiqueta,param2=Etiqueta 2" (solo esos parámetros se muestran).
    valores: opcional, {param: {valor: texto}} para mostrar un nombre en vez de un id.
    Cada chip quita su filtro y deja los demás (y vuelve a la primera página).
    """
    request = context.get('request')
    if request is None:
        return {'chips': []}
    nombres = {}
    for par in etiquetas.split(','):
        if '=' in par:
            clave, etiqueta = par.split('=', 1)
            nombres[clave.strip()] = etiqueta.strip()

    chips = []
    for clave, etiqueta in nombres.items():
        valor = request.GET.get(clave, '')
        if not valor:
            continue
        resto = [(k, v) for k, v in request.GET.items() if k != clave and k not in _PAGINACION and v]
        chips.append({
            'etiqueta': etiqueta,
            'valor': ((valores or {}).get(clave) or _LEGIBLES.get(clave, {})).get(valor, valor),
            'url': '?' + urlencode(resto) if resto else url_limpiar,
        })
    return {'chips': chips, 'url_limpiar': url_limpiar}
