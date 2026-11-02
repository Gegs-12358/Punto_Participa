"""
Importación de alumnos desde la web (solo Administrador).

Flujo en dos pasos, sin guardar el archivo en disco (ver 10.2 de CAMBIOS.md):
  1) "previsualizar": se lee y valida el archivo, se muestra el resumen y las filas ya
     validadas quedan en la sesión del usuario. No se escribe nada en Alumno.
  2) "confirmar": se vuelve a analizar contra la BBDD (pudo cambiar entre medio) y se aplica.

Toda la lógica vive en importador_alumnos.py, la misma que usa el comando importar_alumnos.
"""
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import render

from .importador_alumnos import (
    MAX_BYTES, ArchivoInvalido, analizar, aplicar, bloqueo_masivo, leer_filas,
)
from .views import registrar_log, role_required

PLANTILLA = 'gestion/alumnos_importar.html'
CLAVE_SESION = 'importacion_alumnos'
MAX_LISTADO = 50          # filas que se muestran por tabla; los totales siempre son completos


def _contexto_vista_previa(res, nombre):
    return {
        'vista_previa': True,
        'nombre_archivo': nombre,
        'resumen': {
            'total': res.total,
            'nuevos': len(res.nuevos),
            'actualizados': len(res.actualizados),
            'sin_cambios': res.sin_cambios,
            'errores': len(res.errores),
            'bloqueos': len(res.bloqueados),
            'activos': res.total_activos,
        },
        'errores': res.errores[:MAX_LISTADO],
        'errores_extra': max(0, len(res.errores) - MAX_LISTADO),
        'cambios': [(fila, datos['rut'], lista)
                    for fila, datos, lista in res.actualizados[:MAX_LISTADO]],
        'cambios_extra': max(0, len(res.actualizados) - MAX_LISTADO),
        'bloqueos': res.bloqueados[:MAX_LISTADO],
        'bloqueos_extra': max(0, len(res.bloqueados) - MAX_LISTADO),
        'avisos': res.avisos[:20],
        'avisos_extra': max(0, len(res.avisos) - 20),
        'bloqueo_masivo': bloqueo_masivo(res),
        'hay_algo': bool(res.nuevos or res.actualizados or res.bloqueados),
    }


def _previsualizar(request):
    archivo = request.FILES.get('archivo')
    if not archivo:
        return render(request, PLANTILLA, {'error': 'Selecciona un archivo .xlsx o .csv.'})
    if archivo.size > MAX_BYTES:
        return render(request, PLANTILLA, {
            'error': f'El archivo supera {MAX_BYTES // (1024 * 1024)} MB.'})
    try:
        filas = leer_filas(archivo, archivo.name)
    except ArchivoInvalido as e:
        request.session.pop(CLAVE_SESION, None)
        return render(request, PLANTILLA, {'error': str(e)})

    nombre = archivo.name[:100]
    request.session[CLAVE_SESION] = {'nombre': nombre, 'filas': [[n, d] for n, d in filas]}
    return render(request, PLANTILLA, _contexto_vista_previa(analizar(filas), nombre))


def _confirmar(request):
    guardado = request.session.get(CLAVE_SESION)
    if not guardado:
        return render(request, PLANTILLA, {
            'error': 'No hay una vista previa pendiente. Sube el archivo de nuevo.'})

    nombre = guardado['nombre']
    res = analizar([(n, d) for n, d in guardado['filas']])

    if bloqueo_masivo(res) and request.POST.get('confirmar_bloqueo_masivo') != 'on':
        ctx = _contexto_vista_previa(res, nombre)
        ctx['error'] = ('Se bloquearía a más del 20 % de los alumnos activos. Revisa que el '
                        'archivo sea la nómina completa y marca la casilla para continuar.')
        return render(request, PLANTILLA, ctx)

    if not (res.nuevos or res.actualizados or res.bloqueados):
        request.session.pop(CLAVE_SESION, None)
        return render(request, PLANTILLA, {'error': 'No hay nada que guardar.'})

    try:
        creados, actualizados, bloqueados = aplicar(res)
    except IntegrityError:
        return render(request, PLANTILLA, {
            'error': 'No se pudo guardar (conflicto con datos existentes). No se cambió nada.'})

    registrar_log(
        request, 'Alumnos', 'Importación de alumnos',
        f'Archivo {nombre}: {creados} creados, {actualizados} actualizados, '
        f'{bloqueados} bloqueados, {len(res.errores)} con error',
        'Alumno')
    request.session.pop(CLAVE_SESION, None)
    return render(request, PLANTILLA, {'resultado': {
        'nombre': nombre, 'creados': creados, 'actualizados': actualizados,
        'bloqueados': bloqueados, 'errores': len(res.errores)}})


@login_required
@role_required('Administrador')
def importar_alumnos_web(request):
    if request.method != 'POST':
        return render(request, PLANTILLA, {})
    accion = request.POST.get('accion')
    if accion == 'previsualizar':
        return _previsualizar(request)
    if accion == 'confirmar':
        return _confirmar(request)
    return render(request, PLANTILLA, {'error': 'Acción no válida.'})
