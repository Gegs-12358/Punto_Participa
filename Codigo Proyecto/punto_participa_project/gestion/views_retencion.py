"""
Botón del Inicio "Ya verifiqué los respaldos: borrar ahora" (solo Administrador). Ejecuta el borrado del proceso
de retención abierto, lo deja en la auditoría con el nombre de quien lo hizo y avisa a todos los Administradores.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .decorators import role_required
from .models import AvisoRetencion
from .retencion import YaEjecutado, ejecutar, nombre_usuario


@login_required
@role_required('Administrador')
@require_POST
def retencion_ejecutar(request, pk):
    aviso = get_object_or_404(AvisoRetencion, pk=pk)
    if request.POST.get('verificado') != 'on':
        messages.error(request, 'Marca la casilla para confirmar que verificaste los respaldos antes de borrar.')
        return redirect('dashboard')
    try:
        resumen = ejecutar(aviso, request.user)
    except YaEjecutado as e:
        previo = e.args[0]
        messages.info(request, f'{nombre_usuario(previo.ejecutado_por)} ya había ejecutado este borrado el '
                               f'{previo.ejecutado:%d/%m/%Y}.')
        return redirect('dashboard')
    messages.success(request, f'Listo: se borraron {resumen["actividades"]} actividades y {resumen["auditoria"]} '
                              f'registros de auditoría anteriores al {aviso.fecha_corte:%d/%m/%Y}. Se avisó a los '
                              f'demás Administradores.')
    return redirect('dashboard')
