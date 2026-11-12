"""
Pantalla Alumnos (P1): directorio, ficha con historial y bloqueo manual. Solo Administrador.

- Los alumnos NO se crean ni se borran aquí: llegan con la nómina (Importar nómina) y
  borrarlos eliminaría su historial.
- Estados:
    activo    puede inscribirse, registrar asistencia y recibir invitaciones.
    nomina    bloqueado porque no vino en la última nómina; la siguiente nómina lo
              reactiva si vuelve a venir.
    manual    bloqueado a mano por el Administrador, con un motivo. La nómina lo respeta:
              sigue bloqueado hasta que se desbloquee a mano.
- Bloquear y desbloquear quedan en la auditoría.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .models import Alumno, Asistencia, Carrera, Inscripcion, Jornada
from .utils import limpiar_texto, normalizar_documento, paginar
from .views import registrar_log

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
    return render(request, 'gestion/alumno_detalle.html', {
        'alumno': alumno,
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
