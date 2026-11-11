"""
Catálogos que administra el Administrador: por ahora, lugares.

Pantalla /catalogos/lugares/ para agregar, renombrar, bloquear, desbloquear y eliminar
lugares. Reglas:
  - Los nombres se guardan sin espacios repetidos y no se aceptan duplicados, aunque
    difieran solo en mayúsculas ("Auditorio" y "AUDITORIO" son el mismo lugar).
  - Renombrar un lugar actualiza también las actividades que lo usan, para que los
    filtros y reportes sigan juntándolas.
  - Bloquear lo saca del desplegable de actividades nuevas, pero las actividades que ya
    lo usan lo conservan. Es la opción para un lugar que dejó de usarse.
  - Solo se puede eliminar un lugar que ninguna actividad usa.
Cada cambio queda en la auditoría.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render

from .models import Actividad, Lugar
from .utils import limpiar_texto
from .views import registrar_log, role_required

MAX_NOMBRE = Lugar._meta.get_field('nombre').max_length


def _limpiar_nombre(valor):
    """Quita caracteres de control y deja un solo espacio entre palabras."""
    return ' '.join(limpiar_texto(valor or '').split())


def _validar_nombre(nombre, excluir_pk=None):
    """Devuelve un mensaje de error, o None si el nombre sirve."""
    if not nombre:
        return 'Escribe el nombre del lugar.'
    if len(nombre) > MAX_NOMBRE:
        return f'El nombre no puede superar los {MAX_NOMBRE} caracteres.'
    duplicado = Lugar.objects.filter(nombre__iexact=nombre)
    if excluir_pk:
        duplicado = duplicado.exclude(pk=excluir_pk)
    if duplicado.exists():
        return f'Ya existe un lugar llamado "{duplicado.first().nombre}".'
    return None


def _lugar_o_none(valor):
    try:
        return Lugar.objects.get(pk=int(valor))
    except (TypeError, ValueError, Lugar.DoesNotExist):
        return None


def _lugares_con_uso():
    usos = (Actividad.objects.filter(lugar=OuterRef('nombre'))
            .values('lugar').annotate(n=Count('id')).values('n'))
    return Lugar.objects.annotate(
        total_actividades=Coalesce(Subquery(usos, output_field=IntegerField()), Value(0)),
    ).order_by('-activo', 'nombre')


@login_required
@role_required('Administrador')
def catalogo_lugares(request):
    if request.method == 'POST':
        _procesar(request)
        return redirect('catalogo_lugares')

    editar_id = request.GET.get('editar')
    return render(request, 'gestion/catalogo_lugares.html', {
        'lugares': _lugares_con_uso(),
        'editar_id': int(editar_id) if (editar_id or '').isdigit() else None,
        'max_nombre': MAX_NOMBRE,
    })


def _procesar(request):
    accion = request.POST.get('accion')

    if accion == 'crear':
        nombre = _limpiar_nombre(request.POST.get('nombre'))
        error = _validar_nombre(nombre)
        if error:
            messages.error(request, error)
            return
        lugar = Lugar.objects.create(nombre=nombre)
        registrar_log(request, 'Catálogos', 'Crear lugar', f'Lugar "{nombre}" agregado.',
                      'Lugar', lugar.id, nombre)
        messages.success(request, f'Lugar "{nombre}" agregado.')
        return

    lugar = _lugar_o_none(request.POST.get('lugar_id'))
    if not lugar:
        messages.error(request, 'El lugar no existe.')
        return

    if accion == 'renombrar':
        nuevo = _limpiar_nombre(request.POST.get('nombre'))
        if nuevo == lugar.nombre:
            return
        error = _validar_nombre(nuevo, excluir_pk=lugar.pk)
        if error:
            messages.error(request, error)
            return
        anterior = lugar.nombre
        with transaction.atomic():
            actualizadas = Actividad.objects.filter(lugar=anterior).update(lugar=nuevo)
            lugar.nombre = nuevo
            lugar.save(update_fields=['nombre'])
        registrar_log(request, 'Catálogos', 'Renombrar lugar',
                      f'"{anterior}" ahora se llama "{nuevo}" ({actualizadas} actividades actualizadas).',
                      'Lugar', lugar.id, nuevo,
                      cambios_json={'nombre': {'antes': anterior, 'despues': nuevo}})
        messages.success(request, f'"{anterior}" ahora se llama "{nuevo}". '
                                  f'Se actualizaron {actualizadas} actividades.')

    elif accion in ('bloquear', 'desbloquear'):
        activo = accion == 'desbloquear'
        if lugar.activo != activo:
            lugar.activo = activo
            lugar.save(update_fields=['activo'])
            registrar_log(request, 'Catálogos',
                          'Desbloquear lugar' if activo else 'Bloquear lugar',
                          f'Lugar "{lugar.nombre}" {"desbloqueado" if activo else "bloqueado"}.',
                          'Lugar', lugar.id, lugar.nombre)
        messages.success(request, f'Lugar "{lugar.nombre}" '
                                  f'{"desbloqueado" if activo else "bloqueado"}.')

    elif accion == 'eliminar':
        en_uso = Actividad.objects.filter(lugar=lugar.nombre).count()
        if en_uso:
            messages.error(request, f'No se puede eliminar "{lugar.nombre}": lo usan {en_uso} '
                                    f'actividades. Puedes bloquearlo para que no se ofrezca más.')
            return
        nombre, pk = lugar.nombre, lugar.pk
        lugar.delete()
        registrar_log(request, 'Catálogos', 'Eliminar lugar', f'Lugar "{nombre}" eliminado.',
                      'Lugar', pk, nombre)
        messages.success(request, f'Lugar "{nombre}" eliminado.')

    else:
        messages.error(request, 'Acción no válida.')