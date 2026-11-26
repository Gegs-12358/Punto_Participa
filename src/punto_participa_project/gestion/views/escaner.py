"""
Escáner de asistencia: lectura por RUT, QR o código de barras, turnos de cada operador y contador en vivo.
Las actividades con invitación se resuelven en escaner_invitacion.py.
"""
from collections import defaultdict
from datetime import datetime
import json
import logging
import re

from django_ratelimit.decorators import ratelimit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from ..decorators import role_required
from ..models import Actividad, Asistencia, AsistenciaSesion, Inscripcion, TurnoEscaneo
from ..permissions import tiene_rol
from ..servicios import horario_registro
from ..servicios import sesiones as servicio_sesiones
from ..utils import buscar_alumno_por_documento, formatear_rut, id_o_none, limpiar_documento

from .comun import _error_json, _es_ajax, registrar_log

logger = logging.getLogger(__name__)


# RUN del QR del carnet, tolerante a la puntuacion que cambia segun el teclado:
# 'RUN' + 1 a 3 simbolos + cuerpo + 0 a 2 simbolos + digito verificador.
_RE_RUN_QR = re.compile(r'RUN[^0-9A-Z]{1,3}(\d{1,9})[^0-9A-Z]{0,2}([0-9K])', re.IGNORECASE)


def _parse_rut_escaneo(rut_original):
    """Detecta el método (QR/CODIGO/RUT) y devuelve el documento normalizado."""
    mayus = rut_original.upper()
    if 'SIDIV' in mayus or 'REGISTROCIVIL' in mayus or 'RUN=' in mayus:
        m = _RE_RUN_QR.search(rut_original)
        if m:
            return 'QR', f'{m.group(1)}-{m.group(2).upper()}'
        return 'QR', rut_original
    if "'" in rut_original or '-' in rut_original:
        return 'CODIGO', rut_original.replace("'", "")
    return 'RUT', rut_original


_RE_DOC_CORTO = re.compile(r"^[A-Za-z0-9.\-']{1,20}$")


def _mensaje_no_encontrado(metodo, documento):
    """No repite en pantalla el texto leido de un carnet (QR) ni textos largos o raros.
    Un documento digitado a mano y corto se muestra para detectar errores de tipeo."""
    if metodo != 'QR' and _RE_DOC_CORTO.match(documento or ''):
        return f'Estudiante no encontrado con el documento: {documento}'
    return 'Estudiante no encontrado.'


def _turno_inicio(request):
    """Hora de inicio del turno (con zona horaria) o None."""
    valor = request.session.get('turno_inicio')
    try:
        inicio = datetime.fromisoformat(valor) if valor else None
    except (TypeError, ValueError):
        return None
    return inicio if inicio and timezone.is_aware(inicio) else None


METODOS = {'RUT': 'RUT', 'QR': 'Código QR', 'CODIGO': 'Código de barras'}


def _sesion_escaneo(request, actividad):
    """
    Sesión en la que se registra. Por defecto, la que corresponde a ahora (Actividad.sesion_para);
    el operador puede elegir otra de la misma actividad, y queda guardada en su sesión de usuario.
    """
    sesiones = actividad.lista_sesiones()
    elegida = request.session.get('sesion_escaneo_id')
    for s in sesiones:
        if s.id == elegida:
            return s
    return actividad.sesion_para(timezone.now())


def _texto_sesion(actividad, sesion):
    """"Sesión 2 de 3" en las actividades de varias sesiones; vacío en las de una."""
    total = len(actividad.lista_sesiones())
    return f'Sesión {sesion.numero} de {total}' if total > 1 else ''


def _iniciar_turno(request, actividad):
    turno = TurnoEscaneo.objects.create(usuario=request.user, actividad=actividad)
    request.session['actividad_escaneo_id'] = actividad.id
    request.session['turno_id'] = turno.id
    request.session['turno_inicio'] = turno.inicio.isoformat()
    registrar_log(request, 'Escáner', 'Iniciar turno', f'Turno de escaneo en "{actividad.titulo}".',
                  'Actividad', actividad.id, actividad.titulo)


def _terminar_turno(request):
    """Cierra el turno en curso, lo deja en la auditoría y devuelve un resumen (o None)."""
    act_id = request.session.pop('actividad_escaneo_id', None)
    request.session.pop('sesion_escaneo_id', None)
    inicio = _turno_inicio(request)
    request.session.pop('turno_inicio', None)
    turno_id = request.session.pop('turno_id', None)
    if turno_id:
        TurnoEscaneo.objects.filter(pk=turno_id, usuario=request.user, fin__isnull=True).update(
            fin=timezone.now())
    actividad = Actividad.objects.filter(pk=act_id).first() if act_id else None
    if actividad is None:
        return None
    # Alumnos, invitados y acompañantes, en cualquiera de las sesiones
    registradas = (AsistenciaSesion.objects.filter(sesion__actividad=actividad, registrado_por=request.user,
                                                   fecha_ingreso__gte=inicio).count() if inicio else 0)
    minutos = int((timezone.now() - inicio).total_seconds() // 60) if inicio else None
    duracion = f' en {minutos} min' if minutos is not None else ''
    registrar_log(request, 'Escáner', 'Finalizar turno',
                  f'Turno en "{actividad.titulo}": {registradas} asistencia{"s" if registradas != 1 else ""}'
                  f' registrada{"s" if registradas != 1 else ""}{duracion}.',
                  'Actividad', actividad.id, actividad.titulo,
                  cambios_json={'registradas': registradas, 'minutos': minutos})
    return {'actividad': actividad, 'registradas': registradas, 'minutos': minutos}


def _contador_escaneo(request, actividad):
    """
    Contador en vivo del escáner: lo que registró este operador en su turno, el total
    de la actividad (todos los operadores) y cuántas lleva cada operador.
    """
    inicio = _turno_inicio(request)
    sesion = _sesion_escaneo(request, actividad)
    if actividad.tipo == 'INVITACION':
        return _contador_invitacion(request, actividad, sesion, inicio)
    # En las actividades de varias sesiones, se cuenta la sesión en la que se está registrando
    asis = AsistenciaSesion.objects.filter(sesion=sesion, alumno__isnull=False)
    if actividad.tipo == 'TALLER':
        meta = Inscripcion.objects.filter(actividad=actividad, estado='CONFIRMADA').count()
        meta_texto = 'inscritos'
    else:
        meta, meta_texto = actividad.cupos_totales, 'cupos'
    # Operadores: quienes ya registraron en la actividad y quienes están en turno ahora (aunque lleven 0)
    en_turno = set(TurnoEscaneo.abiertos(actividad).values_list('usuario_id', flat=True))
    totales = {i['registrado_por_id']: i['t'] for i in
               asis.order_by().values('registrado_por_id').annotate(t=Count('id'))}
    nombres = {u.id: (u.first_name or u.username) for u in User.objects.filter(pk__in=set(totales) | en_turno)}
    operadores = sorted(
        ({'nombre': nombres.get(uid, 'Sin operador'), 'total': t, 'yo': uid == request.user.id,
          'en_turno': uid in en_turno}
         for uid, t in ({**{u: 0 for u in en_turno}, **totales}).items()),
        key=lambda o: (-o['total'], o['nombre'].lower()))
    ultimos = [{
        'nombre': f'{a.alumno.nombres} {a.alumno.apellidos}',
        'iniciales': _iniciales(f'{a.alumno.nombres} {a.alumno.apellidos}'),
        'metodo': METODOS.get(a.metodo_ingreso, a.metodo_ingreso),
        'operador': ('tú' if a.registrado_por_id == request.user.id
                     else (a.registrado_por.first_name or a.registrado_por.username) if a.registrado_por else ''),
        'hora': timezone.localtime(a.fecha_ingreso).strftime('%H:%M'),
    } for a in asis.select_related('alumno', 'registrado_por').order_by('-fecha_ingreso')[:10]]
    return {
        'sesion': _texto_sesion(actividad, sesion),
        'total': asis.count(),
        'meta': meta,
        'meta_texto': meta_texto,
        'en_turno': len(en_turno),
        'ultimos': ultimos,
        'mi_turno': asis.filter(registrado_por=request.user, fecha_ingreso__gte=inicio).count() if inicio else 0,
        'turno_desde': timezone.localtime(inicio).strftime('%H:%M') if inicio else None,
        'operadores': operadores,
    }


def _iniciales(nombre):
    return ''.join(p[0] for p in nombre.split()[:2]).upper()


def _contador_invitacion(request, actividad, sesion, inicio):
    """Contador del escáner en una actividad con invitación: cuenta invitados y acompañantes."""
    from .escaner_invitacion import registros
    filas = registros(sesion)
    en_turno = set(TurnoEscaneo.abiertos(actividad).values_list('usuario_id', flat=True))
    totales = defaultdict(int)
    for f in filas:
        totales[f['registrado_por_id']] += 1
    nombres = {u.id: (u.first_name or u.username) for u in User.objects.filter(pk__in=set(totales) | en_turno)}
    operadores = sorted(
        ({'nombre': nombres.get(uid, 'Sin operador'), 'total': t, 'yo': uid == request.user.id,
          'en_turno': uid in en_turno}
         for uid, t in ({**{u: 0 for u in en_turno}, **totales}).items()),
        key=lambda o: (-o['total'], o['nombre'].lower()))
    esperados = (actividad.invitados.exclude(estado='RECHAZADO').count()
                 + actividad.acompanantes.count())
    filas.sort(key=lambda f: f['fecha'], reverse=True)
    return {
        'sesion': _texto_sesion(actividad, sesion),
        'total': len(filas),
        'meta': esperados,
        'meta_texto': 'esperados (invitados y acompañantes)',
        'en_turno': len(en_turno),
        'ultimos': [{'nombre': f['nombre'], 'iniciales': _iniciales(f['nombre']), 'metodo': f['metodo'],
                     'operador': 'tú' if f['registrado_por_id'] == request.user.id else f['operador_nombre'],
                     'hora': timezone.localtime(f['fecha']).strftime('%H:%M')} for f in filas[:10]],
        'mi_turno': sum(1 for f in filas if f['registrado_por_id'] == request.user.id
                        and inicio and f['fecha'] >= inicio),
        'turno_desde': timezone.localtime(inicio).strftime('%H:%M') if inicio else None,
        'operadores': operadores,
    }


def _procesar_escaneo(request):
    """
    Procesa la solicitud POST del escáner.
    Soporta 4 tipos de documento:
    - RUT chileno (con o sin guion, con o sin puntos, con K mayúscula o minúscula)
    - Pasaporte extranjero (letras + números)
    - RUN provisorio (solo números)
    - Cédula de extranjero (números o alfanumérico)
    """
    rut_original = limpiar_documento(request.POST.get('rut'), 300)
    if not rut_original:
        return _error_json('Debes ingresar un RUT o Pasaporte.')

    confirmar = request.POST.get('confirmar', 'false').lower() == 'true'

    # ============================================================
    # DETECTAR MÉTODO DE INGRESO (QR / CÓDIGO / RUT)
    # ============================================================
    metodo, rut_procesado = _parse_rut_escaneo(rut_original)

    if not rut_procesado:
        return _error_json('Debes ingresar un RUT o Pasaporte válido.')

    # ============================================================
    # VALIDAR ACTIVIDAD EN SESIÓN
    # ============================================================
    actividad_id = request.session.get('actividad_escaneo_id')
    if not actividad_id:
        return _error_json('Primero selecciona una actividad.')

    try:
        actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
    except Actividad.DoesNotExist:
        _terminar_turno(request)
        return _error_json('La actividad no existe o ya no está activa.', 404)

    # ============================================================
    # HORARIO: una hora antes hasta una hora después de la sesión (servicios/horario_registro.py)
    # ============================================================
    sesion_horario = _sesion_escaneo(request, actividad)
    correccion = False
    if not horario_registro.abierta(sesion_horario):
        if not horario_registro.puede_corregir(request.user, actividad):
            return _error_json(horario_registro.mensaje_cerrado(sesion_horario), 403)
        correccion = True
    # Aviso en la ventana de confirmar (antes de aceptar) y motivo para la auditoría
    aviso_correccion = horario_registro.mensaje_correccion(sesion_horario, request.user) if correccion else ''
    motivo = f' (fuera de horario: {horario_registro.motivo_fuera(sesion_horario)})' if correccion else ''

    # Con invitación: entran invitados y acompañantes de la lista (pueden no estar en la nómina)
    if actividad.tipo == 'INVITACION':
        from . import escaner_invitacion
        respuesta = escaner_invitacion.procesar(request, actividad, metodo, rut_procesado, confirmar)
        if correccion and respuesta.status_code == 200:
            if confirmar:
                registrar_log(request, 'Escáner', 'Registro fuera de horario',
                              f'Corrección en "{actividad.titulo}": registro de {rut_procesado}{motivo}.',
                              'Actividad', actividad.id, actividad.titulo)
            else:
                datos = json.loads(respuesta.content)
                if datos.get('confirmar') or datos.get('agregar'):
                    datos['correccion'] = aviso_correccion
                    return JsonResponse(datos, status=respuesta.status_code)
        return respuesta

    # ============================================================
    # BUSCAR ALUMNO — Usando helper global
    # ============================================================
    alumno = buscar_alumno_por_documento(rut_procesado)
    if not alumno:
        return _error_json(_mensaje_no_encontrado(metodo, rut_procesado), 404)

    # ============================================================
    # HELPERS DE LOG
    # ============================================================
    def _log_duplicado():
        registrar_log(request, 'Escáner', 'Intento de asistencia duplicada',
                      f'{alumno.nombres} {alumno.apellidos} en {actividad.titulo}',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    def _log_sin_inscripcion():
        registrar_log(request, 'Escáner', 'Intento de asistencia sin inscripción',
                      f'{alumno.nombres} {alumno.apellidos} en "{actividad.titulo}"',
                      'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    # ============================================================
    # PRIMERA ETAPA: PEDIR CONFIRMACIÓN
    # ============================================================
    sesion = _sesion_escaneo(request, actividad)
    texto_sesion = _texto_sesion(actividad, sesion)
    duplicado = (f'La asistencia de la sesión {sesion.numero} ya fue registrada.'
                 if texto_sesion else 'La asistencia ya fue registrada anteriormente.')

    if not confirmar:
        if servicio_sesiones.registro_en_sesion(sesion, alumno=alumno):
            _log_duplicado()
            return _error_json(duplicado, 409)

        if actividad.tipo == 'TALLER' and not Inscripcion.objects.filter(
            actividad=actividad, alumno=alumno, estado='CONFIRMADA'
        ).exists():
            _log_sin_inscripcion()
            return _error_json(
                f'{alumno.nombres} {alumno.apellidos} no está inscrito en este taller.',
                403
            )

        return JsonResponse({
            'success': True,
            'confirmar': True,
            'correccion': aviso_correccion,
            'alumno': {
                'nombre': f'{alumno.nombres} {alumno.apellidos}',
                'rut': formatear_rut(alumno.rut),
                'carrera': alumno.carrera,
                'jornada': alumno.jornada,
            }
        })

    # ============================================================
    # SEGUNDA ETAPA: CONFIRMAR Y CREAR ASISTENCIA
    # ============================================================
    try:
        with transaction.atomic():
            actividad = Actividad.objects.select_for_update().get(
                pk=actividad_id, estado='ACTIVA'
            )

            if servicio_sesiones.registro_en_sesion(sesion, alumno=alumno):
                _log_duplicado()
                return _error_json(duplicado, 409)

            if actividad.tipo == 'TALLER' and not Inscripcion.objects.filter(
                actividad=actividad, alumno=alumno, estado='CONFIRMADA'
            ).exists():
                _log_sin_inscripcion()
                return _error_json(
                    f'{alumno.nombres} {alumno.apellidos} no está inscrito en este taller.',
                    403
                )

            if not servicio_sesiones.registrar(sesion, alumno=alumno, metodo=metodo, usuario=request.user):
                raise IntegrityError('otro operador registró esta sesión')
            # Asistencia a la actividad (al menos una sesión): la primera vez que viene
            if not Asistencia.objects.filter(actividad=actividad, alumno=alumno).exists():
                Asistencia.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    metodo_ingreso=metodo,
                    registrado_por=request.user
                )
            registrar_log(request, 'Escáner',
                          'Registro fuera de horario' if correccion else 'Registro de asistencia',
                          ('Corrección: ' if correccion else '')
                          + f'{alumno.nombres} {alumno.apellidos} - {actividad.titulo}'
                          + (f' ({texto_sesion.lower()})' if texto_sesion else '') + motivo,
                          'Alumno', alumno.id, f'{alumno.nombres} {alumno.apellidos}')

    except Actividad.DoesNotExist:
        return _error_json('La actividad no existe o ya no está activa.', 404)
    except IntegrityError:
        return _error_json('La asistencia ya fue registrada por otro operador.', 409)
    except Exception:
        logger.exception('Error al registrar asistencia')
        return _error_json('Ocurrió un error al registrar la asistencia.', 500)

    return JsonResponse({
        'success': True,
        'confirmar': False,
        'message': f'Asistencia registrada para {alumno.nombres} {alumno.apellidos}'
                   + (f' ({texto_sesion.lower()}).' if texto_sesion else '.'),
        'metodo': metodo,
        'alumno': {
            'nombre': f'{alumno.nombres} {alumno.apellidos}',
            'rut': formatear_rut(alumno.rut),
            'carrera': alumno.carrera,
            'jornada': alumno.jornada,
        },
        'contador': _contador_escaneo(request, actividad),
    })


def _actividades_para_escanear(user):
    """
    Actividades para elegir en el escáner (servicios/horario_registro.py): las que tienen el registro abierto
    (primero las en curso) y las que lo abren en las próximas 24 horas. El Creador de Evento también ve las de
    otros: el equipo del Punto se reparte el registro. Devuelve (disponibles, fuera_de_horario); la segunda lista
    son las demás actividades activas que el usuario puede corregir (Administrador: todas; Creador: las suyas),
    la más reciente primero.
    """
    ahora = timezone.now()
    actividades = list(Actividad.objects.filter(estado='ACTIVA').select_related('creado_por')
                       .prefetch_related('sesiones'))
    disponibles, fuera = [], []
    for a in actividades:
        # En las de varias sesiones, "en curso" es que una de sus sesiones está en curso ahora
        a.en_curso = a.sesion_en_curso(ahora)
        a.registro_abierto = horario_registro.actividad_abierta(a, ahora)
        a.abre = None if a.registro_abierto else horario_registro.proxima_apertura(a, ahora)
        if a.registro_abierto or (a.abre and a.abre - ahora <= horario_registro.PROXIMAS):
            disponibles.append(a)
        elif horario_registro.puede_corregir(user, a):
            fuera.append(a)

    def orden(a):
        if a.en_curso:
            return (0, a.fecha_inicio.timestamp())
        if a.registro_abierto:
            return (1, a.fecha_inicio.timestamp())
        return (2, a.abre.timestamp())
    fuera.sort(key=lambda a: -a.fecha_fin.timestamp())
    return sorted(disponibles, key=orden), fuera


@login_required
@role_required('Administrador', 'Creador de Evento', 'Encargado de Registrar')
@ratelimit(key='user', rate='120/1m', method='POST', block=False)
def escaneo(request):
    if request.method == 'POST':
        if 'cambiar_actividad' in request.POST:
            actividad_id = id_o_none(request.POST.get('actividad_id'))
            if not actividad_id:
                if _es_ajax(request):
                    return _error_json('Debes seleccionar una actividad.')
                messages.error(request, 'Debes seleccionar una actividad.')
                return redirect('escaneo')
            try:
                actividad = Actividad.objects.get(pk=actividad_id, estado='ACTIVA')
                disponibles, fuera = _actividades_para_escanear(request.user)
                if not any(a.pk == actividad.pk for a in disponibles + fuera):
                    raise Actividad.DoesNotExist
                # Sin aviso emergente: taparía el campo y la pistola escribiría en ninguna parte.
                # La pantalla ya muestra la actividad y la hora de inicio del turno.
                if (request.session.get('actividad_escaneo_id') != actividad.id
                        or not request.session.get('turno_id')):
                    _terminar_turno(request)
                    _iniciar_turno(request, actividad)
                    request.session.pop('sesion_escaneo_id', None)
                if _es_ajax(request):
                    return JsonResponse({'success': True, 'redirect_url': '/escaneo/'})
                return redirect('escaneo')
            except Actividad.DoesNotExist:
                if _es_ajax(request):
                    return _error_json('Actividad no válida o inactiva.', 404)
                messages.error(request, 'Actividad no válida o inactiva.')
                return redirect('escaneo')

        if 'cambiar_sesion' in request.POST:
            actividad = Actividad.objects.filter(pk=request.session.get('actividad_escaneo_id'),
                                                 estado='ACTIVA').first()
            sesion_id = id_o_none(request.POST.get('sesion_id'))
            if actividad and any(s.id == sesion_id for s in actividad.lista_sesiones()):
                request.session['sesion_escaneo_id'] = sesion_id
                registrar_log(request, 'Escáner', 'Cambiar sesión',
                              f'Registro en "{actividad.titulo}": se eligió otra sesión a mano.',
                              'Actividad', actividad.id, actividad.titulo)
            else:
                messages.error(request, 'Esa sesión no es de la actividad del turno.')
            return redirect('escaneo')

        if 'finalizar_turno' in request.POST:
            resumen = _terminar_turno(request)
            if resumen:
                n, minutos = resumen['registradas'], resumen['minutos']
                messages.info(request, f'Turno finalizado en "{resumen["actividad"].titulo}": registraste {n} '
                                       f'asistencia{"s" if n != 1 else ""}'
                                       + (f' en {minutos} min.' if minutos is not None else '.'))
            else:
                messages.info(request, 'Turno finalizado.')
            return redirect('escaneo')

        if 'rut' in request.POST:
               if getattr(request, 'limited', False):
                   return _error_json(
                       'Demasiados escaneos seguidos. Espera unos segundos e intenta de nuevo.',
                       429,
                   )
               return _procesar_escaneo(request)

    act_id = request.session.get('actividad_escaneo_id')
    actividad = None
    if act_id:
        try:
            actividad = Actividad.objects.get(pk=act_id, estado='ACTIVA')
        except Actividad.DoesNotExist:
            _terminar_turno(request)
    if actividad and not request.session.get('turno_id'):
        # Sesiones anteriores a los turnos guardados: el turno empieza ahora
        _iniciar_turno(request, actividad)

    sesion = _sesion_escaneo(request, actividad) if actividad else None
    disponibles, fuera = _actividades_para_escanear(request.user)
    return render(request, 'gestion/escaneo.html', {
        'actividad_seleccionada': actividad,
        'sesion_escaneo': sesion,
        'sesiones': actividad.lista_sesiones() if actividad else [],
        'contador': _contador_escaneo(request, actividad) if actividad else None,
        'horario': horario_registro.estado(request.user, actividad, sesion) if actividad else None,
        'actividades_disponibles': disponibles,
        'actividades_fuera_de_horario': fuera,
        'user_es_admin': tiene_rol(request.user, ['Administrador']),
        'ahora': timezone.now(),
    })


@login_required
@role_required('Administrador', 'Creador de Evento', 'Encargado de Registrar', json_response=True)
@require_GET
def escaneo_contador(request):
    """Contador en vivo del escáner (la pantalla lo consulta cada pocos segundos)."""
    act_id = request.session.get('actividad_escaneo_id')
    actividad = Actividad.objects.filter(pk=act_id, estado='ACTIVA').first() if act_id else None
    if actividad is None:
        return _error_json('No hay una actividad seleccionada.', 404)
    return JsonResponse({'success': True, **_contador_escaneo(request, actividad)})
