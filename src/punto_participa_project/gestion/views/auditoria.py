"""
Auditoría: pantalla con filtros (texto, usuario, módulo, acción, sobre qué y fechas). Los mismos filtros
los usa la exportación (exportaciones.exportar_auditoria).
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render

from ..decorators import role_required
from ..models import LogAuditoria
from ..utils import fecha_o_none, limpiar_texto


SISTEMA = '__sistema__'   # valor del filtro Usuario para las acciones sin usuario (públicas o automáticas)


def filtros_auditoria(request):
    """Filtros de Auditoría, ya limpios. Los usa la pantalla y la exportación."""
    g = request.GET
    f = {
        'usuario': limpiar_texto(g.get('usuario', ''))[:150],
        'modulo': limpiar_texto(g.get('modulo', ''))[:50],
        'accion': limpiar_texto(g.get('accion', ''))[:200],
        'objeto': limpiar_texto(g.get('objeto', ''))[:50],
        'buscar': limpiar_texto(g.get('buscar', ''))[:100],
        'desde': fecha_o_none(g.get('desde')),
        'hasta': fecha_o_none(g.get('hasta')),
    }
    # "fecha" (un solo día) se mantiene para los enlaces guardados
    dia = fecha_o_none(g.get('fecha'))
    if dia and not (f['desde'] or f['hasta']):
        f['desde'] = f['hasta'] = dia
    return f


def _filtrar_auditoria(request, f=None):
    f = f or filtros_auditoria(request)
    qs = LogAuditoria.objects.select_related('usuario_sistema').order_by('-fecha_registro', '-id')
    if f['usuario'] == SISTEMA:
        qs = qs.filter(usuario_sistema__isnull=True)
    elif f['usuario']:
        qs = qs.filter(usuario_sistema__username__icontains=f['usuario'])
    if f['modulo']:
        qs = qs.filter(modulo__iexact=f['modulo'])
    if f['accion']:
        qs = qs.filter(accion__iexact=f['accion'])
    if f['objeto']:
        qs = qs.filter(objeto_tipo__iexact=f['objeto'])
    if f['buscar']:
        qs = qs.filter(Q(detalle__icontains=f['buscar']) | Q(objeto_nombre__icontains=f['buscar'])
                       | Q(accion__icontains=f['buscar']))
    if f['desde']:
        qs = qs.filter(fecha_registro__date__gte=f['desde'])
    if f['hasta']:
        qs = qs.filter(fecha_registro__date__lte=f['hasta'])
    return qs


def tono_accion(accion):
    """Color de la etiqueta de la acción: rojo si quita o bloquea, verde si crea o registra, azul si exporta."""
    a = (accion or '').lower()
    if any(p in a for p in ('elimin', 'borr', 'cancel', 'bloque', 'rechaz', 'fall', 'quitar', 'anonim',
                            'retención de datos ejecutada')):
        return 'inactive'
    if any(p in a for p in ('export', 'descarg', 'imprim')):
        return 'tono-info'
    if any(p in a for p in ('crear', 'guardar', 'agregar', 'inscrip', 'ingreso', 'asistencia', 'confirm',
                            'importar', 'iniciar', 'respuesta', 'anotación', 'envío', 'enviar')):
        return 'badge-success'
    return 'draft'


@login_required
@role_required('Administrador')
def lista_auditoria(request):
    from ..utils import paginar
    f = filtros_auditoria(request)
    logs = paginar(request, _filtrar_auditoria(request, f))
    for log in logs:
        log.tono = tono_accion(log.accion)

    # Acciones agrupadas por módulo (si hay un módulo elegido, solo las de ese módulo)
    pares = LogAuditoria.objects.order_by('modulo', 'accion').values_list('modulo', 'accion').distinct()
    acciones = {}
    for modulo, accion in pares:
        if f['modulo'] and (modulo or '').lower() != f['modulo'].lower():
            continue
        acciones.setdefault(modulo or 'Sin módulo', []).append(accion)

    usuarios = (User.objects.filter(logs_auditoria__isnull=False).distinct().order_by('username')
                .values_list('username', flat=True))
    return render(request, 'gestion/auditoria_list.html', {
        'retencion_anios': settings.RETENCION_ANIOS,
        'logs': logs,
        'filtros': f,
        'sistema': SISTEMA,
        'usuarios_disponibles': usuarios,
        'acciones_por_modulo': acciones,
        'modulos_disponibles': LogAuditoria.objects.exclude(modulo__isnull=True).exclude(modulo='')
            .values_list('modulo', flat=True).distinct().order_by('modulo'),
        'objetos_disponibles': LogAuditoria.objects.exclude(objeto_tipo__isnull=True).exclude(objeto_tipo='')
            .values_list('objeto_tipo', flat=True).distinct().order_by('objeto_tipo'),
        'chips_valores': {'usuario': {SISTEMA: 'Sistema'}},
    })
