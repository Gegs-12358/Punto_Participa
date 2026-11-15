"""
Pantalla de carga masiva de usuarios (solo Administrador). Mismo flujo que la importación de la nómina:
  1) "previsualizar": se lee y valida el archivo; las filas quedan en la sesión y no se crea nada.
  2) "confirmar": se vuelve a analizar contra la base (pudo cambiar entre medio), se crean las cuentas y se
     envían los correos con el enlace para crear la contraseña.
La lógica está en usuarios_masivos.py.
"""
import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from .decorators import role_required
from .importador_alumnos import MAX_BYTES
from .models import Rol
from .usuarios_masivos import ArchivoInvalido, aplicar, analizar, leer
from .views import registrar_log

PLANTILLA = 'gestion/usuarios_importar.html'
CLAVE_SESION = 'carga_usuarios'
MAX_LISTADO = 100


def _contexto(res, nombre):
    return {
        'vista_previa': True, 'nombre_archivo': nombre,
        'resumen': {'total': res.total, 'nuevos': len(res.nuevos), 'omitidas': len(res.omitidas),
                    'errores': len(res.errores)},
        'nuevos': [d for _, d in res.nuevos[:MAX_LISTADO]],
        'nuevos_extra': max(0, len(res.nuevos) - MAX_LISTADO),
        'omitidas': res.omitidas[:MAX_LISTADO], 'omitidas_extra': max(0, len(res.omitidas) - MAX_LISTADO),
        'errores': res.errores[:MAX_LISTADO], 'errores_extra': max(0, len(res.errores) - MAX_LISTADO),
    }


def _base():
    return {'roles': Rol.objects.order_by('nombre').values_list('nombre', flat=True)}


@login_required
@role_required('Administrador')
def importar_usuarios(request):
    ctx = _base()
    if request.method != 'POST':
        return render(request, PLANTILLA, ctx)
    accion = request.POST.get('accion')

    if accion == 'previsualizar':
        archivo = request.FILES.get('archivo')
        if not archivo:
            ctx['error'] = 'Selecciona un archivo .xlsx o .csv.'
            return render(request, PLANTILLA, ctx)
        if archivo.size > MAX_BYTES:
            ctx['error'] = f'El archivo supera {MAX_BYTES // (1024 * 1024)} MB.'
            return render(request, PLANTILLA, ctx)
        try:
            filas = leer(archivo, archivo.name)
        except ArchivoInvalido as e:
            request.session.pop(CLAVE_SESION, None)
            ctx['error'] = str(e)
            return render(request, PLANTILLA, ctx)
        nombre = archivo.name[:100]
        request.session[CLAVE_SESION] = {'nombre': nombre, 'filas': [[n, d] for n, d in filas]}
        ctx.update(_contexto(analizar(filas), nombre))
        return render(request, PLANTILLA, ctx)

    if accion == 'confirmar':
        guardado = request.session.get(CLAVE_SESION)
        if not guardado:
            ctx['error'] = 'No hay una vista previa pendiente. Sube el archivo de nuevo.'
            return render(request, PLANTILLA, ctx)
        res = analizar([(n, d) for n, d in guardado['filas']])
        request.session.pop(CLAVE_SESION, None)
        if not res.nuevos:
            ctx['error'] = 'No hay usuarios nuevos que crear.'
            return render(request, PLANTILLA, ctx)
        creados, fallidos = aplicar(res)
        registrar_log(request, 'Usuarios', 'Carga masiva de usuarios',
                      f'Archivo {guardado["nombre"]}: {len(creados)} usuarios creados, {len(res.omitidas)} omitidos '
                      f'por existir, {len(res.errores)} filas con error, {len(fallidos)} correos sin enviar.',
                      'Usuario', cambios_json={'creados': creados, 'correos_fallidos': fallidos})
        ctx['resultado'] = {'nombre': guardado['nombre'], 'creados': creados, 'fallidos': fallidos,
                            'omitidas': len(res.omitidas), 'errores': len(res.errores)}
        return render(request, PLANTILLA, ctx)

    ctx['error'] = 'Acción no válida.'
    return render(request, PLANTILLA, ctx)


@login_required
@role_required('Administrador')
def plantilla_usuarios(request):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="plantilla_usuarios.csv"'
    respuesta.write('﻿')
    w = csv.writer(respuesta, delimiter=';')
    w.writerow(['nombre', 'correo', 'rut', 'rol', 'usuario'])
    w.writerow(['Juan Pérez Soto', 'juan.perez@duoc.cl', '12.345.678-5', 'Encargado de Registrar', ''])
    w.writerow(['María González Rojas', 'maria.gonzalez@duoc.cl', '9.876.543-3', 'Creador de Evento', 'mgonzalez'])
    return respuesta
