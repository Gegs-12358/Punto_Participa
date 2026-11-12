"""
Invitados de una actividad con invitación (paso 1: carga de la lista y listado).

- La lista se sube al crear la actividad (formulario) o después, desde esta pantalla.
- Cada carga muestra cuántos se agregaron o actualizaron, y los errores y avisos por fila.
- Se puede quitar a un invitado mientras no haya entrado.
- Lo ve el Administrador y el creador de la actividad.
"""
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import role_required
from .invitados import ArchivoInvalido, analizar, aplicar, leer
from .models import Actividad, Invitado
from .permissions import puede_gestionar_actividad
from .utils import limpiar_texto, normalizar_documento, paginar
from .views import registrar_log


def _clave_resumen(actividad):
    return f'carga_invitados_{actividad.pk}'


def cargar_lista(request, actividad, filas):
    """Revisa y carga las filas leídas; deja el resumen en la sesión para mostrarlo."""
    res = analizar(filas, actividad)
    nuevos, actualizados = aplicar(res, actividad)
    resumen = res.resumen()
    request.session[_clave_resumen(actividad)] = resumen
    registrar_log(
        request, 'Actividades', 'Cargar lista de invitados',
        f'"{actividad.titulo}": {nuevos} agregados, {actualizados} actualizados, '
        f'{resumen["sin_cambios"]} sin cambios, {resumen["total_errores"]} con errores.',
        'Actividad', actividad.id, actividad.titulo,
        cambios_json={k: resumen[k] for k in ('nuevos', 'actualizados', 'sin_cambios', 'total_errores',
                                               'total_avisos')},
    )
    return resumen


def _actividad_con_permiso(request, pk):
    actividad = get_object_or_404(Actividad, pk=pk)
    if not puede_gestionar_actividad(request.user, actividad):
        messages.error(request, 'No tienes permisos sobre esta actividad.')
        return None, redirect('lista_actividades')
    if actividad.tipo != 'INVITACION':
        messages.info(request, 'Esta actividad no es con invitación.')
        return None, redirect('actividad_detalle', pk=actividad.pk)
    return actividad, None


@login_required
@role_required('Administrador', 'Creador de Evento')
def invitados_actividad(request, pk):
    actividad, salida = _actividad_con_permiso(request, pk)
    if salida:
        return salida

    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Elige el archivo con la lista (.xlsx o .csv).')
        else:
            try:
                cargar_lista(request, actividad, leer(archivo, archivo.name))
            except ArchivoInvalido as e:
                messages.error(request, f'No se pudo leer la lista: {e}')
        return redirect('invitados_actividad', pk=actividad.pk)

    qs = actividad.invitados.annotate(total_acompanantes=Count('acompanantes')).select_related('alumno')
    buscar = limpiar_texto(request.GET.get('q', ''))[:100]
    if buscar:
        doc = normalizar_documento(buscar)
        qs = qs.filter(Q(nombre__icontains=buscar) | Q(correo__icontains=buscar)
                       | Q(rut__icontains=doc or buscar) | Q(carrera__icontains=buscar))
    estado = request.GET.get('estado', '')
    if estado in dict(Invitado.ESTADO_CHOICES):
        qs = qs.filter(estado=estado)

    todos = actividad.invitados
    totales = todos.aggregate(
        total=Count('id'),
        confirmados=Count('id', filter=Q(estado='CONFIRMADO')),
        rechazados=Count('id', filter=Q(estado='RECHAZADO')),
        pendientes=Count('id', filter=Q(estado='PENDIENTE')),
        fuera_de_nomina=Count('id', filter=Q(alumno__isnull=True)),
    )
    totales['acompanantes'] = actividad.acompanantes.count()

    return render(request, 'gestion/actividad_invitados.html', {
        'actividad': actividad,
        'invitados': paginar(request, qs.order_by('nombre')),
        'totales': totales,
        'resumen': request.session.pop(_clave_resumen(actividad), None),
        'estados_opciones': Invitado.ESTADO_CHOICES,
    })


@login_required
@role_required('Administrador', 'Creador de Evento')
@require_POST
def quitar_invitado(request, pk, invitado_id):
    actividad, salida = _actividad_con_permiso(request, pk)
    if salida:
        return salida
    invitado = get_object_or_404(Invitado, pk=invitado_id, actividad=actividad)
    if invitado.ingreso or invitado.acompanantes.filter(ingreso__isnull=False).exists():
        messages.error(request, f'{invitado.nombre} ya entró a la actividad: no se puede quitar.')
        return redirect('invitados_actividad', pk=actividad.pk)
    nombre, rut, acompanantes = invitado.nombre, invitado.rut, invitado.acompanantes.count()
    invitado.delete()
    registrar_log(request, 'Actividades', 'Quitar invitado',
                  f'{nombre} quitado de "{actividad.titulo}"'
                  + (f' junto con {acompanantes} acompañante{"s" if acompanantes != 1 else ""}' if acompanantes else '')
                  + '.', 'Actividad', actividad.id, actividad.titulo,
                  cambios_json={'invitado': nombre, 'documento': rut, 'acompanantes': acompanantes})
    messages.success(request, f'{nombre} ya no está en la lista de invitados.')
    return redirect('invitados_actividad', pk=actividad.pk)


@login_required
@role_required('Administrador', 'Creador de Evento')
def plantilla_invitados(request):
    """CSV vacío con las columnas que espera la carga, listo para llenar en Excel."""
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="plantilla_invitados.csv"'
    respuesta.write('﻿')
    escritor = csv.writer(respuesta, delimiter=';')
    escritor.writerow(['rut', 'nombre', 'apellidos', 'carrera', 'jornada', 'correo'])
    escritor.writerow(['20.001.550-9', 'Juan', 'Pérez Soto', 'Ingeniería en Informática', 'Diurna',
                       'juan.perez@duocuc.cl'])
    return respuesta
