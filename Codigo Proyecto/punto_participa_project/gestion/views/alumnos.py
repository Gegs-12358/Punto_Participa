"""
Alumnos: directorio con buscador, ficha con historial, bloqueo manual, anonimización e importación de la
nómina desde la web (la lógica de la importación está en importador_alumnos.py).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import role_required
from ..servicios.importador_alumnos import analizar, aplicar, ArchivoInvalido, bloqueo_masivo, leer_filas, MAX_BYTES
from ..models import Alumno, Asistencia, Carrera, Inscripcion, Jornada
from ..utils import limpiar_texto, normalizar_documento, paginar

from .comun import registrar_log


MAX_MOTIVO = Alumno._meta.get_field('motivo_bloqueo').max_length


ESTADOS = [
    ('activo', 'Activo'),
    ('nomina', 'Bloqueado: no vino en la nómina'),
    ('manual', 'Bloqueado a mano'),
]


def _conteo(modelo):
    sub = (modelo.objects.filter(alumno_id=OuterRef('pk')).order_by()
           .values('alumno_id').annotate(n=Count('id')).values('n'))
    return Coalesce(Subquery(sub, output_field=IntegerField()), Value(0))


def _buscar(qs, texto):
    """RUT o documento (con o sin puntos y guion), nombre, apellido o correo.
    Con varias palabras ("juan perez") cada palabra debe estar en el nombre o el apellido."""
    texto = limpiar_texto(texto)[:100]
    if not texto:
        return qs
    q = Q(correo__icontains=texto) | Q(rut__icontains=normalizar_documento(texto) or texto)
    palabras = Q()
    for palabra in texto.split()[:5]:
        palabras &= Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra)
    return qs.filter(q | palabras)


@login_required
@role_required('Administrador')
def lista_alumnos(request):
    g = request.GET
    qs = _buscar(Alumno.objects.all(), g.get('q', ''))
    if g.get('carrera'):
        qs = qs.filter(carrera__iexact=limpiar_texto(g['carrera'])[:100])
    if g.get('jornada'):
        qs = qs.filter(jornada__iexact=limpiar_texto(g['jornada'])[:20])
    estado = g.get('estado', '')
    if estado == 'activo':
        qs = qs.filter(activo=True)
    elif estado == 'nomina':
        qs = qs.filter(activo=False, bloqueo_manual=False)
    elif estado == 'manual':
        qs = qs.filter(activo=False, bloqueo_manual=True)

    qs = qs.annotate(total_inscripciones=_conteo(Inscripcion),
                     total_asistencias=_conteo(Asistencia)).order_by('apellidos', 'nombres', 'pk')

    totales = Alumno.objects.aggregate(
        activos=Count('id', filter=Q(activo=True)),
        nomina=Count('id', filter=Q(activo=False, bloqueo_manual=False)),
        manual=Count('id', filter=Q(activo=False, bloqueo_manual=True)),
    )
    return render(request, 'gestion/alumnos_lista.html', {
        'alumnos': paginar(request, qs),
        'carreras_opciones': Carrera.objects.order_by('nombre').values_list('nombre', flat=True),
        'jornadas_opciones': Jornada.objects.order_by('nombre').values_list('nombre', flat=True),
        'estados_opciones': ESTADOS,
        'totales': totales,
        'max_motivo': MAX_MOTIVO,
    })


def _historial(alumno):
    """Una fila por actividad en que el alumno se inscribió o asistió, de la más reciente a la más antigua."""
    filas = {}
    for i in alumno.inscripciones.select_related('actividad'):
        filas[i.actividad_id] = {'actividad': i.actividad, 'inscripcion': i, 'asistencia': None}
    for a in alumno.asistencias.select_related('actividad', 'registrado_por'):
        filas.setdefault(a.actividad_id, {'actividad': a.actividad, 'inscripcion': None, 'asistencia': None})
        filas[a.actividad_id]['asistencia'] = a
    ahora = timezone.now()
    for f in filas.values():
        foto = f['asistencia'] or f['inscripcion']
        f['carrera'], f['jornada'] = foto.carrera, foto.jornada
        f['pendiente'] = f['actividad'].fecha_inicio > ahora
        f['falto'] = (f['inscripcion'] is not None and f['inscripcion'].estado == 'CONFIRMADA'
                      and f['asistencia'] is None and not f['pendiente'])
    return sorted(filas.values(), key=lambda f: f['actividad'].fecha_inicio, reverse=True)


@login_required
@role_required('Administrador')
def alumno_detalle(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    historial = _historial(alumno)
    from ..servicios.anonimizacion import esta_anonimizado
    return render(request, 'gestion/alumno_detalle.html', {
        'alumno': alumno,
        'anonimizado': esta_anonimizado(alumno),
        'historial': historial,
        'resumen': {
            'actividades': len(historial),
            'inscripciones': sum(1 for f in historial if f['inscripcion']
                                 and f['inscripcion'].estado == 'CONFIRMADA'),
            'asistencias': sum(1 for f in historial if f['asistencia']),
            'faltas': sum(1 for f in historial if f['falto']),
        },
        'max_motivo': MAX_MOTIVO,
    })


@login_required
@role_required('Administrador')
@require_POST
def alumno_bloqueo(request, pk):
    alumno = get_object_or_404(Alumno, pk=pk)
    accion = request.POST.get('accion')
    volver = 'alumno_detalle' if request.POST.get('volver') == 'detalle' else 'lista_alumnos'
    destino = redirect(volver, pk=alumno.pk) if volver == 'alumno_detalle' else redirect(volver)
    nombre = f'{alumno.nombres} {alumno.apellidos}'
    from ..servicios.anonimizacion import esta_anonimizado
    if esta_anonimizado(alumno):
        messages.error(request, 'Este alumno fue anonimizado: no se puede bloquear ni desbloquear.')
        return destino

    if accion == 'bloquear':
        motivo = limpiar_texto(request.POST.get('motivo', ''))[:MAX_MOTIVO]
        if not motivo:
            messages.error(request, 'Escribe el motivo del bloqueo: queda en la ficha y en la auditoría.')
            return destino
        if alumno.bloqueo_manual and not alumno.activo:
            messages.info(request, f'{nombre} ya estaba bloqueado a mano.')
            return destino
        antes = alumno.estado
        Alumno.objects.filter(pk=alumno.pk).update(activo=False, bloqueo_manual=True, motivo_bloqueo=motivo)
        registrar_log(request, 'Alumnos', 'Bloquear alumno', f'{nombre} bloqueado a mano. Motivo: {motivo}',
                      'Alumno', alumno.id, nombre,
                      cambios_json={'estado': {'antes': antes, 'despues': 'manual'}, 'motivo': motivo})
        messages.success(request, f'{nombre} quedó bloqueado: no podrá inscribirse, registrar asistencia '
                                  f'ni recibir invitaciones. La nómina no lo desbloquea.')

    elif accion == 'desbloquear':
        if alumno.activo:
            messages.info(request, f'{nombre} ya estaba activo.')
            return destino
        antes, motivo_anterior = alumno.estado, alumno.motivo_bloqueo
        Alumno.objects.filter(pk=alumno.pk).update(activo=True, bloqueo_manual=False, motivo_bloqueo='')
        registrar_log(request, 'Alumnos', 'Desbloquear alumno',
                      f'{nombre} desbloqueado' + (f' (motivo anterior: {motivo_anterior})' if motivo_anterior else '')
                      + '.', 'Alumno', alumno.id, nombre,
                      cambios_json={'estado': {'antes': antes, 'despues': 'activo'}})
        aviso = (' Ojo: no venía en la última nómina; si tampoco viene en la próxima, se volverá a bloquear.'
                 if antes == 'nomina' else '')
        messages.success(request, f'{nombre} quedó activo.{aviso}')

    else:
        messages.error(request, 'Acción no válida.')
    return destino


@login_required
@role_required('Administrador')
@require_POST
def alumno_anonimizar(request, pk):
    """Anonimiza al alumno (irreversible). Hay que escribir ANONIMIZAR para confirmar."""
    from ..servicios.anonimizacion import anonimizar, esta_anonimizado
    alumno = get_object_or_404(Alumno, pk=pk)
    if esta_anonimizado(alumno):
        messages.info(request, 'Este alumno ya estaba anonimizado.')
        return redirect('alumno_detalle', pk=alumno.pk)
    if (request.POST.get('confirmacion') or '').strip().upper() != 'ANONIMIZAR':
        messages.error(request, 'Para anonimizar escribe ANONIMIZAR en el recuadro de confirmación.')
        return redirect('alumno_detalle', pk=alumno.pk)
    corregidos = anonimizar(alumno)
    registrar_log(request, 'Alumnos', 'Anonimización de alumno',
                  f'Alumno #{alumno.pk} anonimizado: se reemplazaron su nombre, documento y correo, y se conservaron '
                  f'su carrera, escuela, jornada y participación. Registros de auditoría corregidos: {corregidos}.',
                  'Alumno', alumno.pk, 'Alumno anonimizado')
    messages.success(request, 'Datos personales anonimizados. Se conservan la carrera, la escuela, la jornada y la '
                              'participación para las estadísticas.')
    return redirect('alumno_detalle', pk=alumno.pk)


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
