"""
Catálogos que administra el Administrador: lugares, escuelas y carreras.

Reglas comunes:
  - Los nombres se guardan sin espacios repetidos y no se aceptan duplicados, aunque
    difieran solo en mayúsculas ("Auditorio" y "AUDITORIO" son lo mismo).
  - Bloquear saca el elemento de lo que se ofrece al crear actividades, pero lo que ya
    lo usa lo conserva. Es la opción para algo que dejó de usarse.
  - Solo se puede eliminar lo que nada usa.
  - Cada cambio queda en la auditoría.

Lugares (/catalogos/lugares/):
  - Renombrar actualiza también las actividades que lo usan.
  - "Pide número" (por ejemplo, en "Sala") hace que el formulario de actividad pida el
    número de la sala ("1203"), así el desplegable no necesita una opción por sala.

Escuelas (/catalogos/escuelas/):
  - Renombrar actualiza también sus carreras (Carrera.escuela guarda el nombre) y la
    escuela guardada en inscripciones y asistencias (renombrar = corregir).
  - Cada escuela tiene un color, que es el que usan los gráficos del dashboard y reportes.
  - Bloquear una escuela deja de ofrecer sus carreras al crear actividades.

Carreras (/catalogos/carreras/):
  - Renombrar es para CORREGIR el nombre de la misma carrera: actualiza también a los
    alumnos y la carrera guardada en inscripciones y asistencias. Si hay alumnos o
    historial, pide confirmación antes de hacerlo.
  - Si es una carrera DISTINTA (cambio de malla, fusión), se usa "crear nueva y bloquear
    la antigua": alumnos y actividades antiguas conservan su carrera y el historial
    no cambia.
  - Las actividades guardan un enlace a la carrera, así que siguen el cambio de nombre solas.
"""
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render

from .models import Actividad, Alumno, Asistencia, Carrera, Escuela, Inscripcion, Lugar
from .utils import limpiar_texto
from .views import COLORES_FALLBACK, COLOR_SIN_ESCUELA, registrar_log, role_required

MAX_NOMBRE = Lugar._meta.get_field('nombre').max_length


# ============================================================
# AYUDAS COMUNES
# ============================================================

def _limpiar_nombre(valor):
    """Quita caracteres de control y deja un solo espacio entre palabras."""
    return ' '.join(limpiar_texto(valor or '').split())


def _validar_nombre(modelo, nombre, un_elemento, excluir_pk=None):
    """Devuelve un mensaje de error, o None si el nombre sirve.

    un_elemento: "un lugar", "una escuela", "una carrera" (para los mensajes).
    """
    llamado = 'llamada' if un_elemento.startswith('una ') else 'llamado'
    maximo = modelo._meta.get_field('nombre').max_length
    if not nombre:
        return 'Escribe el nombre.'
    if len(nombre) > maximo:
        return f'El nombre no puede superar los {maximo} caracteres.'
    duplicado = modelo.objects.filter(nombre__iexact=nombre)
    if excluir_pk:
        duplicado = duplicado.exclude(pk=excluir_pk)
    if duplicado.exists():
        return f'Ya existe {un_elemento} {llamado} "{duplicado.first().nombre}".'
    return None


def _obj_o_none(modelo, valor):
    try:
        return modelo.objects.get(pk=int(valor))
    except (TypeError, ValueError, modelo.DoesNotExist):
        return None


PATRON_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _color_o_none(valor):
    """'#307fe2' -> '#307FE2'; cualquier otra cosa -> None."""
    valor = (valor or '').strip()
    return valor.upper() if PATRON_COLOR.match(valor) else None


def _id_o_none(valor):
    return int(valor) if (valor or '').isdigit() else None


def _cambiar_activo(request, obj, activo, tipo, terminacion):
    """Bloquea o desbloquea. tipo: "lugar"/"escuela"/"carrera"; terminacion: "o"/"a"."""
    estado = f'desbloquead{terminacion}' if activo else f'bloquead{terminacion}'
    if obj.activo != activo:
        obj.activo = activo
        obj.save(update_fields=['activo'])
        registrar_log(request, 'Catálogos',
                      f'{"Desbloquear" if activo else "Bloquear"} {tipo}',
                      f'{tipo.capitalize()} "{obj.nombre}" {estado}.',
                      tipo.capitalize(), obj.id, obj.nombre)
    messages.success(request, f'{tipo.capitalize()} "{obj.nombre}" {estado}.')


def _subconsulta_conteo(modelo, campo):
    """Cuenta filas de `modelo` cuyo `campo` (texto) es igual al nombre del elemento."""
    conteo = (modelo.objects.filter(**{campo: OuterRef('nombre')})
              .values(campo).annotate(n=Count('id')).values('n'))
    return Coalesce(Subquery(conteo, output_field=IntegerField()), Value(0))


# ============================================================
# LUGARES
# ============================================================

def _lugares_con_uso():
    return Lugar.objects.annotate(
        total_actividades=_subconsulta_conteo(Actividad, 'lugar'),
    ).order_by('-activo', 'nombre')


@login_required
@role_required('Administrador')
def catalogo_lugares(request):
    if request.method == 'POST':
        _procesar_lugar(request)
        return redirect('catalogo_lugares')

    return render(request, 'gestion/catalogo_lugares.html', {
        'lugares': _lugares_con_uso(),
        'editar_id': _id_o_none(request.GET.get('editar')),
        'max_nombre': MAX_NOMBRE,
        'pestana': 'lugares',
    })


def _procesar_lugar(request):
    accion = request.POST.get('accion')

    if accion == 'crear':
        nombre = _limpiar_nombre(request.POST.get('nombre'))
        error = _validar_nombre(Lugar, nombre, 'un lugar')
        if error:
            messages.error(request, error)
            return
        pide_numero = request.POST.get('pide_numero') == 'on'
        lugar = Lugar.objects.create(nombre=nombre, pide_numero=pide_numero)
        registrar_log(request, 'Catálogos', 'Crear lugar',
                      f'Lugar "{nombre}" agregado{" (pide número de sala)" if pide_numero else ""}.',
                      'Lugar', lugar.id, nombre)
        messages.success(request, f'Lugar "{nombre}" agregado.')
        return

    lugar = _obj_o_none(Lugar, request.POST.get('lugar_id'))
    if not lugar:
        messages.error(request, 'El lugar no existe.')
        return

    if accion == 'renombrar':
        nuevo = _limpiar_nombre(request.POST.get('nombre'))
        if nuevo == lugar.nombre:
            return
        error = _validar_nombre(Lugar, nuevo, 'un lugar', excluir_pk=lugar.pk)
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
        _cambiar_activo(request, lugar, accion == 'desbloquear', 'lugar', 'o')

    elif accion == 'pide_numero':
        pide = request.POST.get('valor') == 'si'
        if lugar.pide_numero != pide:
            lugar.pide_numero = pide
            lugar.save(update_fields=['pide_numero'])
            registrar_log(request, 'Catálogos', 'Cambiar número de sala del lugar',
                          f'Lugar "{lugar.nombre}": {"ahora pide" if pide else "ya no pide"} número de sala.',
                          'Lugar', lugar.id, lugar.nombre)
        messages.success(request, f'"{lugar.nombre}" {"ahora pide" if pide else "ya no pide"} '
                                  f'número de sala.')

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


# ============================================================
# ESCUELAS
# ============================================================

@login_required
@role_required('Administrador')
def catalogo_escuelas(request):
    if request.method == 'POST':
        _procesar_escuela(request)
        return redirect('catalogo_escuelas')

    escuelas = Escuela.objects.annotate(
        total_carreras=_subconsulta_conteo(Carrera, 'escuela'),
    ).order_by('-activo', 'nombre')
    usados = {e.color for e in escuelas}
    sugerido = next((c for c in COLORES_FALLBACK if c not in usados and c != COLOR_SIN_ESCUELA),
                    COLORES_FALLBACK[0])
    return render(request, 'gestion/catalogo_escuelas.html', {
        'escuelas': escuelas,
        'color_sugerido': sugerido,
        'color_sin_escuela': COLOR_SIN_ESCUELA,
        'editar_id': _id_o_none(request.GET.get('editar')),
        'max_nombre': Escuela._meta.get_field('nombre').max_length,
        'pestana': 'escuelas',
    })


def _procesar_escuela(request):
    accion = request.POST.get('accion')

    if accion == 'crear':
        nombre = _limpiar_nombre(request.POST.get('nombre'))
        error = _validar_nombre(Escuela, nombre, 'una escuela')
        if error:
            messages.error(request, error)
            return
        escuela = Escuela.objects.create(nombre=nombre, color=_color_o_none(request.POST.get('color')) or '')
        registrar_log(request, 'Catálogos', 'Crear escuela', f'Escuela "{nombre}" agregada.',
                      'Escuela', escuela.id, nombre)
        messages.success(request, f'Escuela "{nombre}" agregada.')
        return

    escuela = _obj_o_none(Escuela, request.POST.get('escuela_id'))
    if not escuela:
        messages.error(request, 'La escuela no existe.')
        return

    if accion == 'renombrar':           # editar nombre y/o color
        nuevo = _limpiar_nombre(request.POST.get('nombre'))
        color = _color_o_none(request.POST.get('color'))
        cambia_nombre = nuevo != escuela.nombre
        cambia_color = color is not None and color != escuela.color
        if not (cambia_nombre or cambia_color):
            return
        if cambia_nombre:
            error = _validar_nombre(Escuela, nuevo, 'una escuela', excluir_pk=escuela.pk)
            if error:
                messages.error(request, error)
                return
        anterior, color_anterior = escuela.nombre, escuela.color
        actualizadas = 0
        with transaction.atomic():
            if cambia_nombre:
                actualizadas = Carrera.objects.filter(escuela=anterior).update(escuela=nuevo)
                # Renombrar es corregir: el historial de participación también se corrige.
                for Modelo in (Inscripcion, Asistencia):
                    Modelo.objects.filter(escuela=anterior).update(escuela=nuevo)
                escuela.nombre = nuevo
            if cambia_color:
                escuela.color = color
            escuela.save(update_fields=['nombre', 'color'])

        cambios = {}
        partes = []
        if cambia_nombre:
            cambios['nombre'] = {'antes': anterior, 'despues': nuevo}
            partes.append(f'"{anterior}" ahora se llama "{nuevo}" ({actualizadas} carreras actualizadas)')
        if cambia_color:
            cambios['color'] = {'antes': color_anterior, 'despues': color}
            partes.append(f'color {color}')
        registrar_log(request, 'Catálogos', 'Renombrar escuela' if cambia_nombre else 'Cambiar color de escuela',
                      '; '.join(partes) + '.', 'Escuela', escuela.id, escuela.nombre, cambios_json=cambios)
        messages.success(request, f'Escuela "{escuela.nombre}" actualizada.' if not cambia_nombre else
                         f'"{anterior}" ahora se llama "{nuevo}". Se actualizaron {actualizadas} carreras.')

    elif accion in ('bloquear', 'desbloquear'):
        _cambiar_activo(request, escuela, accion == 'desbloquear', 'escuela', 'a')

    elif accion == 'eliminar':
        carreras = Carrera.objects.filter(escuela=escuela.nombre).count()
        if carreras:
            messages.error(request, f'No se puede eliminar "{escuela.nombre}": tiene {carreras} '
                                    f'carreras. Puedes bloquearla para que no se ofrezca más.')
            return
        nombre, pk = escuela.nombre, escuela.pk
        escuela.delete()
        registrar_log(request, 'Catálogos', 'Eliminar escuela', f'Escuela "{nombre}" eliminada.',
                      'Escuela', pk, nombre)
        messages.success(request, f'Escuela "{nombre}" eliminada.')

    else:
        messages.error(request, 'Acción no válida.')


# ============================================================
# CARRERAS
# ============================================================

def _carreras_con_uso(escuela=None):
    carreras = Carrera.objects.annotate(
        total_alumnos=_subconsulta_conteo(Alumno, 'carrera'),
        total_actividades=Count('actividades', distinct=True),
    )
    if escuela:
        carreras = carreras.filter(escuela=escuela)
    return carreras.order_by('-activo', 'escuela', 'nombre')


def _contexto_carreras(request, **extra):
    escuela_filtro = request.GET.get('escuela', '')
    return {
        'carreras': _carreras_con_uso(escuela_filtro),
        'escuelas_activas': Escuela.objects.filter(activo=True).order_by('nombre'),
        'escuelas_todas': Escuela.objects.order_by('nombre'),
        'escuela_filtro': escuela_filtro,
        'editar_id': _id_o_none(request.GET.get('editar')),
        'max_nombre': Carrera._meta.get_field('nombre').max_length,
        'pestana': 'carreras',
        **extra,
    }


@login_required
@role_required('Administrador')
def catalogo_carreras(request):
    if request.method == 'POST':
        confirmacion = _procesar_carrera(request)
        if confirmacion:
            # Renombrar con alumnos: antes de hacerlo se muestra qué se va a cambiar
            return render(request, 'gestion/catalogo_carreras.html',
                          _contexto_carreras(request, confirmacion=confirmacion))
        return redirect('catalogo_carreras')

    return render(request, 'gestion/catalogo_carreras.html', _contexto_carreras(request))


def _escuela_valida(nombre, actual=None):
    """La escuela elegida debe existir y estar activa (o ser la que la carrera ya tenía)."""
    if not nombre:
        return None
    escuela = Escuela.objects.filter(nombre=nombre).first()
    if escuela and (escuela.activo or nombre == actual):
        return escuela.nombre
    return None


def _procesar_carrera(request):
    """Aplica la acción. Devuelve un dict si hay que pedir confirmación antes de renombrar."""
    accion = request.POST.get('accion')

    if accion == 'crear':
        nombre = _limpiar_nombre(request.POST.get('nombre'))
        escuela = _escuela_valida(request.POST.get('escuela'))
        error = _validar_nombre(Carrera, nombre, 'una carrera')
        if error:
            messages.error(request, error)
            return None
        if not escuela:
            messages.error(request, 'Elige una escuela activa para la carrera.')
            return None
        carrera = Carrera.objects.create(nombre=nombre, escuela=escuela)
        registrar_log(request, 'Catálogos', 'Crear carrera',
                      f'Carrera "{nombre}" agregada en "{escuela}".', 'Carrera', carrera.id, nombre)
        messages.success(request, f'Carrera "{nombre}" agregada.')
        return None

    carrera = _obj_o_none(Carrera, request.POST.get('carrera_id'))
    if not carrera:
        messages.error(request, 'La carrera no existe.')
        return None

    if accion in ('editar', 'reemplazar'):
        nuevo = _limpiar_nombre(request.POST.get('nombre'))
        escuela = _escuela_valida(request.POST.get('escuela'),
                                  actual=carrera.escuela if accion == 'editar' else None)
        if not escuela:
            messages.error(request, 'Elige una escuela activa para la carrera.')
            return None
        if accion == 'reemplazar':
            return _reemplazar_carrera(request, carrera, nuevo, escuela)
        return _editar_carrera(request, carrera, nuevo, escuela)

    if accion in ('bloquear', 'desbloquear'):
        _cambiar_activo(request, carrera, accion == 'desbloquear', 'carrera', 'a')

    elif accion == 'eliminar':
        alumnos = Alumno.objects.filter(carrera=carrera.nombre).count()
        actividades = carrera.actividades.count()
        if alumnos or actividades:
            messages.error(request, f'No se puede eliminar "{carrera.nombre}": la usan {alumnos} '
                                    f'alumnos y {actividades} actividades. '
                                    f'Puedes bloquearla para que no se ofrezca más.')
            return None
        nombre, pk = carrera.nombre, carrera.pk
        carrera.delete()
        registrar_log(request, 'Catálogos', 'Eliminar carrera', f'Carrera "{nombre}" eliminada.',
                      'Carrera', pk, nombre)
        messages.success(request, f'Carrera "{nombre}" eliminada.')

    else:
        messages.error(request, 'Acción no válida.')
    return None


def _editar_carrera(request, carrera, nuevo, escuela):
    cambia_nombre = nuevo != carrera.nombre
    cambia_escuela = escuela != (carrera.escuela or '')
    if not (cambia_nombre or cambia_escuela):
        return None
    if cambia_nombre:
        error = _validar_nombre(Carrera, nuevo, 'una carrera', excluir_pk=carrera.pk)
        if error:
            messages.error(request, error)
            return None

    alumnos = registros = 0
    if cambia_nombre:
        alumnos = Alumno.objects.filter(carrera=carrera.nombre).count()
        registros = _registros_historial(carrera.nombre)
    if (alumnos or registros) and request.POST.get('confirmado') != '1':
        return {
            'carrera': carrera, 'nuevo_nombre': nuevo, 'nueva_escuela': escuela,
            'alumnos': alumnos, 'registros': registros, 'actividades': carrera.actividades.count(),
        }

    anterior_nombre, anterior_escuela = carrera.nombre, carrera.escuela
    with transaction.atomic():
        if cambia_nombre:
            Alumno.objects.filter(carrera=anterior_nombre).update(carrera=nuevo)
        # Editar es corregir: la "foto" guardada en inscripciones y asistencias se
        # corrige igual, para que los reportes no muestren la carrera con dos nombres.
        for Modelo in (Inscripcion, Asistencia):
            Modelo.objects.filter(carrera=anterior_nombre).update(carrera=nuevo, escuela=escuela)
        carrera.nombre, carrera.escuela = nuevo, escuela
        carrera.save(update_fields=['nombre', 'escuela'])

    cambios = {}
    if cambia_nombre:
        cambios['nombre'] = {'antes': anterior_nombre, 'despues': nuevo}
    if cambia_escuela:
        cambios['escuela'] = {'antes': anterior_escuela, 'despues': escuela}
    detalle = [f'"{anterior_nombre}" ahora se llama "{nuevo}" ({alumnos} alumnos actualizados)'
               if cambia_nombre else f'Carrera "{nuevo}"']
    if cambia_escuela:
        detalle.append(f'pasa de "{anterior_escuela or "sin escuela"}" a "{escuela}"')
    registrar_log(request, 'Catálogos', 'Editar carrera', ', '.join(detalle) + '.',
                  'Carrera', carrera.id, nuevo, cambios_json=cambios)

    mensaje = ', '.join(detalle) + '.'
    if cambia_nombre:
        mensaje += ' Las actividades siguen el cambio solas.'
    messages.success(request, mensaje)
    return None


def _registros_historial(nombre_carrera):
    """Inscripciones y asistencias guardadas con esta carrera (la "foto" del momento)."""
    return (Inscripcion.objects.filter(carrera=nombre_carrera).count()
            + Asistencia.objects.filter(carrera=nombre_carrera).count())


def _reemplazar_carrera(request, carrera, nuevo, escuela):
    """Carrera distinta: crea la nueva y bloquea la antigua, sin tocar alumnos ni actividades."""
    error = _validar_nombre(Carrera, nuevo, 'una carrera')
    if error:
        messages.error(request, error)
        return None
    with transaction.atomic():
        nueva = Carrera.objects.create(nombre=nuevo, escuela=escuela)
        carrera.activo = False
        carrera.save(update_fields=['activo'])
    registrar_log(request, 'Catálogos', 'Reemplazar carrera',
                  f'Se creó "{nuevo}" y se bloqueó "{carrera.nombre}". '
                  f'Alumnos y actividades de "{carrera.nombre}" no cambian.',
                  'Carrera', nueva.id, nuevo,
                  cambios_json={'reemplaza_a': carrera.nombre, 'nueva': nuevo})
    messages.success(request, f'Se creó "{nuevo}" y se bloqueó "{carrera.nombre}". Los alumnos y '
                              f'actividades de "{carrera.nombre}" la conservan; el historial no cambia.')
    return None
