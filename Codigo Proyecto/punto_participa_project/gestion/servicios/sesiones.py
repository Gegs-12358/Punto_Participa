"""
Sesiones de las actividades y asistencia por sesión.

Toda actividad tiene al menos una sesión. Las de una sola sesión funcionan como siempre: la sesión 1
tiene las mismas fechas de la actividad y se mantiene igual cuando la actividad cambia de fecha.

Regla que se cumple en todo el sistema: quien tiene Asistencia (alumno) o un ingreso (invitado o
acompañante) tiene al menos un registro de AsistenciaSesion. El escáner crea primero el de la sesión y
después la Asistencia; las señales de abajo cubren lo que se crea por otro camino (datos de prueba,
admin de Django), y lo dejan en la sesión que corresponde a la hora del registro.
"""
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import Acompanante, Actividad, Asistencia, AsistenciaSesion, Invitado, Sesion


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
