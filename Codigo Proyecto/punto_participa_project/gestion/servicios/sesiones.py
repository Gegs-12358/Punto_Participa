"""
Sesiones de las actividades y asistencia por sesión.

Toda actividad tiene al menos una sesión. Las de una sola sesión funcionan como siempre: la sesión 1
tiene las mismas fechas de la actividad y se mantiene igual cuando la actividad cambia de fecha.

Regla que se cumple en todo el sistema: quien tiene Asistencia (alumno) o un ingreso (invitado o
acompañante) tiene al menos un registro de AsistenciaSesion. El escáner crea primero el de la sesión y
después la Asistencia; las señales de abajo cubren lo que se crea por otro camino (datos de prueba,
admin de Django), y lo dejan en la sesión que corresponde a la hora del registro.
"""
from collections import defaultdict

from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import Acompanante, Actividad, Alumno, Asistencia, AsistenciaSesion, Inscripcion, Invitado, Sesion


def registrar(sesion, *, metodo='', usuario=None, momento=None, **persona):
    """
    Deja la asistencia de una persona (alumno=, invitado= o acompanante=) en la sesión.
    Devuelve True si se registró y False si ya estaba registrada en esa sesión.
    """
    datos = {'sesion': sesion, 'metodo_ingreso': metodo, 'registrado_por': usuario, **persona}
    if momento is not None:
        datos['fecha_ingreso'] = momento
    try:
        with transaction.atomic():
            AsistenciaSesion.objects.create(**datos)
    except IntegrityError:
        return False
    return True


def registro_en_sesion(sesion, **persona):
    """El registro de la persona en esa sesión, o None."""
    return AsistenciaSesion.objects.filter(sesion=sesion, **persona).first()


def _asegurar_registro(actividad, momento, metodo, usuario, **persona):
    """Si la persona no tiene ningún registro en las sesiones de la actividad, lo crea en la que
    corresponde a `momento`."""
    if not AsistenciaSesion.objects.filter(sesion__actividad=actividad, **persona).exists():
        registrar(actividad.sesion_para(momento), metodo=metodo, usuario=usuario, momento=momento, **persona)


def guardar_sesiones(actividad, tramos):
    """
    Deja la actividad con estas sesiones: tramos = [(id o None, inicio, fin), ...] en orden. Las que
    traen id se cambian, las sin id se crean y las que ya no están se quitan (el formulario ya revisó
    que no tengan asistencias). Se numeran por orden de fecha, y la actividad queda empezando con la
    primera y terminando con la última.
    """
    with transaction.atomic():
        actuales = {s.id: s for s in actividad.sesiones.select_for_update()}
        conservar = {i for i, _, _ in tramos if i}
        Sesion.objects.filter(pk__in=[i for i in actuales if i not in conservar]).delete()
        # Números provisorios, para no chocar con la regla "un número por actividad" al renumerar
        for s in actuales.values():
            if s.id in conservar:
                Sesion.objects.filter(pk=s.id).update(numero=s.numero + 1000)
        for numero, (i, inicio, fin) in enumerate(tramos, start=1):
            if i:
                Sesion.objects.filter(pk=i, actividad=actividad).update(numero=numero, fecha_inicio=inicio,
                                                                        fecha_fin=fin)
            else:
                Sesion.objects.create(actividad=actividad, numero=numero, fecha_inicio=inicio, fecha_fin=fin)
        Actividad.objects.filter(pk=actividad.pk).update(fecha_inicio=tramos[0][1], fecha_fin=tramos[-1][2])
        actividad.fecha_inicio, actividad.fecha_fin = tramos[0][1], tramos[-1][2]


# ============================================================
# Cumplimiento de la asistencia (certificados de participación)
# ============================================================

def cumple(asistidas, total, minima):
    """Cumple quien asistió al menos al `minima` % de las sesiones (con una sola sesión: quien asistió)."""
    return asistidas > 0 and asistidas * 100 >= minima * total


def cumplimiento(actividad):
    """
    Una fila por persona de la actividad, con las sesiones a las que vino, el porcentaje y si cumple
    el mínimo. Personas: en talleres, los inscritos (confirmados) y quien asistió; en masivas, quien
    asistió; en las con invitación, los invitados que no dijeron que no, los acompañantes y quien
    ingresó. Ordenadas por apellidos y nombres.
    """
    sesiones = actividad.lista_sesiones()
    total = len(sesiones)
    numero = {s.id: s.numero for s in sesiones}
    asistio = defaultdict(set)
    for r in AsistenciaSesion.objects.filter(sesion__actividad=actividad).values(
            'sesion_id', 'alumno_id', 'invitado_id', 'acompanante_id'):
        clave = (('alumno', r['alumno_id']) if r['alumno_id'] else
                 ('invitado', r['invitado_id']) if r['invitado_id'] else ('acompanante', r['acompanante_id']))
        asistio[clave].add(numero[r['sesion_id']])

    personas = []
    if actividad.tipo == 'INVITACION':
        for inv in actividad.invitados.all():
            if inv.estado != 'RECHAZADO' or ('invitado', inv.id) in asistio:
                personas.append({'clave': ('invitado', inv.id), 'apellidos': '', 'nombres': inv.nombre,
                                 'documento': inv.rut, 'tipo_documento': '', 'correo': inv.correo,
                                 'escuela': inv.escuela, 'carrera': inv.carrera, 'jornada': inv.jornada,
                                 'participa_como': 'Invitado'})
        for ac in actividad.acompanantes.select_related('invitado'):
            personas.append({'clave': ('acompanante', ac.id), 'apellidos': '', 'nombres': ac.nombre,
                             'documento': ac.rut, 'tipo_documento': '', 'correo': '',
                             'escuela': '', 'carrera': '', 'jornada': '',
                             'participa_como': f'Acompañante de {ac.invitado.nombre}'})
    else:
        ids = {i for tipo, i in asistio if tipo == 'alumno'}
        fotos = {}
        if actividad.tipo == 'TALLER':
            for i in Inscripcion.objects.filter(actividad=actividad, estado='CONFIRMADA').values(
                    'alumno_id', 'escuela', 'carrera', 'jornada'):
                ids.add(i['alumno_id'])
                fotos[i['alumno_id']] = i
        # La foto de la asistencia (más reciente) manda sobre la de la inscripción
        for a in Asistencia.objects.filter(actividad=actividad).values('alumno_id', 'escuela', 'carrera', 'jornada'):
            fotos[a['alumno_id']] = a
        for al in Alumno.objects.filter(pk__in=ids):
            foto = fotos.get(al.id, {})
            personas.append({'clave': ('alumno', al.id), 'apellidos': al.apellidos, 'nombres': al.nombres,
                             'documento': al.rut or '', 'tipo_documento': al.tipo_documento, 'correo': al.correo,
                             'escuela': foto.get('escuela') or '', 'carrera': foto.get('carrera') or al.carrera,
                             'jornada': foto.get('jornada') or al.jornada, 'participa_como': 'Alumno'})

    for p in personas:
        numeros = sorted(asistio.get(p['clave'], ()))
        p['sesiones_asistidas'] = numeros
        p['asistidas'] = len(numeros)
        p['total'] = total
        p['porcentaje'] = round(100 * len(numeros) / total) if total else 0
        p['cumple'] = cumple(len(numeros), total, actividad.asistencia_minima)
        p['marcas'] = [s.numero in numeros for s in sesiones]
    personas.sort(key=lambda p: (f"{p['apellidos']} {p['nombres']}".lower(), p['documento']))
    return personas


# ============================================================
# Señales
# ============================================================

@receiver(post_save, sender=Actividad)
def sincronizar_sesion_unica(sender, instance, raw=False, **kwargs):
    """Una actividad de una sola sesión: la sesión 1 tiene siempre las fechas de la actividad."""
    if raw:
        return
    sesiones = list(instance.sesiones.all()[:2])
    if not sesiones:
        Sesion.objects.create(actividad=instance, numero=1, fecha_inicio=instance.fecha_inicio,
                              fecha_fin=instance.fecha_fin)
    elif len(sesiones) == 1:
        unica = sesiones[0]
        if (unica.fecha_inicio, unica.fecha_fin) != (instance.fecha_inicio, instance.fecha_fin):
            Sesion.objects.filter(pk=unica.pk).update(fecha_inicio=instance.fecha_inicio,
                                                      fecha_fin=instance.fecha_fin)


@receiver(post_save, sender=Asistencia)
def asistencia_con_sesion(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    if instance.actividad.tipo == 'INVITACION':
        return   # ahí la asistencia por sesión es la del invitado (señal de abajo)
    _asegurar_registro(instance.actividad, instance.fecha_ingreso, instance.metodo_ingreso,
                       instance.registrado_por, alumno=instance.alumno)


@receiver(post_save, sender=Invitado)
def ingreso_invitado_con_sesion(sender, instance, raw=False, **kwargs):
    if raw or not instance.ingreso:
        return
    _asegurar_registro(instance.actividad, instance.ingreso, instance.metodo_ingreso,
                       instance.registrado_por, invitado=instance)


@receiver(post_save, sender=Acompanante)
def ingreso_acompanante_con_sesion(sender, instance, raw=False, **kwargs):
    if raw or not instance.ingreso:
        return
    _asegurar_registro(instance.actividad, instance.ingreso, instance.metodo_ingreso,
                       instance.registrado_por, acompanante=instance)
