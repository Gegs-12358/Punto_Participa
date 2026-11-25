"""
Piezas que usan varias pantallas: registro en la auditoría, respuestas JSON de error,
detección de peticiones AJAX y colores de las escuelas para los gráficos.
"""
from django.http import JsonResponse

from ..models import Carrera, Escuela, LogAuditoria


# El color de cada escuela se elige en Catálogos > Escuelas. Esta lista de colores oficiales web de
# Duoc UC se usa para llenar el catálogo la primera vez y como respaldo para escuelas sin color.
COLOR_POR_ESCUELA = {
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


COLORES_FALLBACK = [
    '#307FE2', '#FFB800', '#43B02A', '#D50032',
    '#E87722', '#5BC2E7', '#AC4FC6', '#00A499',
    '#C4D600', '#666666',
]


COLOR_SIN_ESCUELA = '#666666'


def colores_escuelas():
    """{nombre de escuela: color} según el catálogo (una sola consulta)."""
    return dict(Escuela.objects.exclude(color='').values_list('nombre', 'color'))


def color_para_escuela(escuela, colores=None):
    """Color de la escuela: el del catálogo, el oficial conocido o gris.

    En ciclos, pasa `colores=colores_escuelas()` para no consultar la BBDD cada vez.
    """
    if not escuela:
        return COLOR_SIN_ESCUELA
    nombre = escuela.strip()
    if colores is None:
        colores = colores_escuelas()
    return colores.get(nombre) or COLOR_POR_ESCUELA.get(nombre, COLOR_SIN_ESCUELA)


def _get_carreras_cache():
    """Cache único de carreras para evitar 3 queries en distintas vistas."""
    return {c.nombre.lower(): c for c in Carrera.objects.all()}


def _colores_por_carrera(items, carreras_cache):
    """
    Devuelve la lista de colores para una lista de dicts con clave 'carrera'
    (o 'alumno__carrera'). Uso: gráficos de dona por carrera.
    """
    colores = []
    mapa = colores_escuelas()
    for i in items:
        nombre = (i.get('carrera', i.get('alumno__carrera')) or '').lower()
        c = carreras_cache.get(nombre)
        colores.append(color_para_escuela(c.escuela if c else None, mapa))
    return colores


def registrar_log(request, modulo, accion, detalle, objeto_tipo=None, objeto_id=None,
                  objeto_nombre=None, cambios_json=None):
    def _cortar(valor, largo):
        return valor[:largo] if isinstance(valor, str) else valor

    LogAuditoria.objects.create(
        usuario_sistema=request.user if request.user.is_authenticated else None,
        modulo=_cortar(modulo, 50),
        accion=_cortar(accion, 200),
        detalle=detalle,
        objeto_tipo=_cortar(objeto_tipo, 50),
        objeto_id=objeto_id,
        objeto_nombre=_cortar(objeto_nombre, 200),
        ip_address=request.META.get('REMOTE_ADDR') or None,
        user_agent=request.META.get('HTTP_USER_AGENT'),
        cambios_json=cambios_json,
    )


def _error_json(msg, status=400):
    return JsonResponse({'success': False, 'message': msg}, status=status)


def _es_ajax(request):
    # Más robusto: acepta x-requested-with, Accept: application/json, o fetch
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.headers.get('x-requested-with') == 'fetch'
    )
