"""
Retención de datos personales.

Regla: lo que tenga más de RETENCION_ANIOS años (2 por defecto) se borra de la base principal; el histórico
completo queda en los respaldos mensuales (servicio respaldo, ver respaldo/LEEME.md).

Qué se borra:
- Las actividades que terminaron antes de la fecha de corte, con todo lo asociado: inscripciones, asistencias,
  cancelaciones, lista de espera, invitados, acompañantes, correos enviados, turnos del escáner e imagen.
- Los registros de auditoría anteriores a la fecha de corte (con su IP y navegador).
No se borran las fichas de los alumnos: para eso está la anonimización (anonimizacion.py).

Nada se borra solo: el borrado lo ejecuta un Administrador desde el Inicio, después de verificar los respaldos.

Ciclo diario (servicio "tareas", `python manage.py retencion`):
1. Si no hay un proceso abierto y hay datos vencidos, se abre uno: fija la fecha de corte y un plazo de
   RETENCION_AVISOS_DIAS[0] días (10), y avisa por correo a todos los Administradores.
2. Recordatorios a todos los Administradores a los 7 y 3 días del plazo. Si un día no corrió, el recordatorio
   pendiente sale al siguiente.
3. Cumplido el plazo sin que nadie haya borrado, no se borra: se envía un aviso diario a todos hasta que un
   Administrador ejecute el borrado.
Cuando un Administrador ejecuta el borrado (ejecutar), se borra lo anterior a la fecha de corte anunciada, queda
en la auditoría con su nombre y se avisa a todos los Administradores quién lo hizo.
"""
import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (Acompanante, Actividad, Asistencia, AvisoRetencion, Inscripcion, InscripcionCancelada,
                     Invitado, ListaEspera, LogAuditoria, NotificacionCorreo, TurnoEscaneo, UsuarioSistema)


logger = logging.getLogger(__name__)


def fecha_corte(hoy):
    """Mismo día de hace RETENCION_ANIOS años (el 29 de febrero pasa al 28)."""
    anio = hoy.year - settings.RETENCION_ANIOS
    try:
        return hoy.replace(year=anio)
    except ValueError:
        return hoy.replace(year=anio, day=28)


def _limite(corte):
    return timezone.make_aware(datetime.combine(corte, time.min))


def calcular(corte):
    """Cuántos registros se borrarían con esa fecha de corte."""
    limite = _limite(corte)
    acts = Actividad.objects.filter(fecha_fin__lt=limite)
    resumen = {
        'actividades': acts.count(),
        'inscripciones': Inscripcion.objects.filter(actividad__in=acts).count(),
        'asistencias': Asistencia.objects.filter(actividad__in=acts).count(),
        'cancelaciones': InscripcionCancelada.objects.filter(actividad__in=acts).count(),
        'lista_espera': ListaEspera.objects.filter(actividad__in=acts).count(),
        'invitados': Invitado.objects.filter(actividad__in=acts).count(),
        'acompanantes': Acompanante.objects.filter(actividad__in=acts).count(),
        'correos': NotificacionCorreo.objects.filter(actividad__in=acts).count(),
        'turnos': TurnoEscaneo.objects.filter(actividad__in=acts).count(),
        'auditoria': LogAuditoria.objects.filter(fecha_registro__lt=limite).count(),
    }
    return resumen


def total(resumen):
    return sum(resumen.values())


def administradores():
    return list(UsuarioSistema.objects.filter(rol__nombre='Administrador', activo=True, user__is_active=True)
                .exclude(user__email='').select_related('user'))


def nombre_usuario(user):
    if user is None:
        return 'un Administrador'
    return (user.first_name or user.get_full_name() or user.username).strip()


def _enviar(aviso, tipo, dias=None):
    """tipo: 'aviso' (antes del plazo), 'vencido' (plazo cumplido, aviso diario) o 'listo' (después de borrar).
    Se envía a todos los Administradores. Devuelve cuántos correos salieron."""
    anios = settings.RETENCION_ANIOS
    contexto = {'aviso': aviso, 'tipo': tipo, 'dias': dias, 'anios': anios,
                'resumen': aviso.resumen_ejecutado if tipo == 'listo' else aviso.resumen,
                'quien': nombre_usuario(aviso.ejecutado_por), 'sitio': settings.SITE_URL.rstrip('/')}
    if tipo == 'listo':
        asunto = f'Retención de datos: {contexto["quien"]} borró los datos de más de {anios} años'
    elif tipo == 'vencido':
        asunto = (f'Pendiente: el borrado de los datos de más de {anios} años venció el '
                  f'{aviso.fecha_programada:%d/%m/%Y} y nadie lo ha ejecutado')
    else:
        asunto = (f'Aviso: quedan {dias} día{"s" if dias != 1 else ""} para borrar los datos de más de '
                  f'{anios} años. Verifica los respaldos')
    enviados = 0
    for perfil in administradores():
        try:
            html = render_to_string('gestion/email_retencion.html', {**contexto, 'nombre': perfil.user.first_name})
            texto = (f'{asunto}. Fecha de corte: {aviso.fecha_corte:%d/%m/%Y}. Plazo: {aviso.fecha_programada:%d/%m/%Y}. '
                     f'Revisa el detalle en el correo HTML o en el Inicio del sistema.')
            enviados += send_mail(asunto, texto, settings.DEFAULT_FROM_EMAIL, [perfil.user.email],
                                  html_message=html, fail_silently=False)
        except Exception:
            logger.exception('No se pudo enviar el aviso de retención al usuario %s', perfil.user_id)
    return enviados


def _auditar(accion, detalle, aviso, cambios, usuario=None):
    LogAuditoria.objects.create(usuario_sistema=usuario, modulo='Datos', accion=accion, detalle=detalle,
                                objeto_tipo='Retención', objeto_id=aviso.pk,
                                objeto_nombre=f'Corte {aviso.fecha_corte:%d/%m/%Y}', cambios_json=cambios)


class YaEjecutado(Exception):
    """Otro Administrador ejecutó el borrado antes."""


def ejecutar(aviso, usuario):
    """Un Administrador ejecuta el borrado: borra lo anterior a la fecha de corte del aviso, lo registra con su
    nombre y avisa a todos los Administradores. Devuelve el resumen de lo borrado."""
    with transaction.atomic():
        aviso = AvisoRetencion.objects.select_for_update().get(pk=aviso.pk)
        if aviso.ejecutado:
            raise YaEjecutado(aviso)
        limite = _limite(aviso.fecha_corte)
        resumen = calcular(aviso.fecha_corte)
        acts = Actividad.objects.filter(fecha_fin__lt=limite)
        imagenes = [a.imagen.name for a in acts.exclude(imagen='').exclude(imagen__isnull=True)]
        acts.delete()
        LogAuditoria.objects.filter(fecha_registro__lt=limite).delete()
        aviso.ejecutado = timezone.now()
        aviso.ejecutado_por = usuario
        aviso.resumen_ejecutado = resumen
        aviso.save(update_fields=['ejecutado', 'ejecutado_por', 'resumen_ejecutado'])
    from django.core.files.storage import default_storage
    for nombre in imagenes:
        try:
            default_storage.delete(nombre)
        except Exception:
            logger.exception('No se pudo borrar la imagen %s', nombre)
    _auditar('Retención de datos ejecutada',
             f'{nombre_usuario(usuario)} verificó los respaldos y borró los datos anteriores al '
             f'{aviso.fecha_corte:%d/%m/%Y}: {resumen["actividades"]} actividades, {resumen["inscripciones"]} '
             f'inscripciones, {resumen["asistencias"]} asistencias y {resumen["auditoria"]} registros de auditoría, '
             f'entre otros. El histórico queda en los respaldos mensuales.',
             aviso, resumen, usuario=usuario)
    _enviar(aviso, 'listo')
    return resumen


def proceso_abierto():
    return AvisoRetencion.objects.filter(ejecutado__isnull=True).order_by('creado').first()


def ciclo(hoy=None):
    """Un paso diario; nunca borra. Devuelve (estado, aviso): 'sin_datos', 'avisado', 'vencido' o 'esperando'."""
    hoy = hoy or timezone.localdate()
    dias_aviso = settings.RETENCION_AVISOS_DIAS
    aviso = proceso_abierto()
    if aviso is None:
        corte = fecha_corte(hoy)
        resumen = calcular(corte)
        if not total(resumen):
            return 'sin_datos', None
        aviso = AvisoRetencion.objects.create(fecha_corte=corte, fecha_programada=hoy + timedelta(days=dias_aviso[0]),
                                              resumen=resumen)
        _auditar('Retención de datos programada',
                 f'Hay datos anteriores al {corte:%d/%m/%Y}. Plazo para que un Administrador verifique los respaldos y '
                 f'ejecute el borrado: {aviso.fecha_programada:%d/%m/%Y}.', aviso, resumen)

    faltan = (aviso.fecha_programada - hoy).days
    if faltan <= 0:
        if aviso.ultimo_aviso == hoy:
            return 'esperando', aviso
        aviso.resumen = calcular(aviso.fecha_corte)
        aviso.ultimo_aviso = hoy
        aviso.save(update_fields=['resumen', 'ultimo_aviso'])
        _enviar(aviso, 'vencido', -faltan)
        return 'vencido', aviso

    pendientes = [d for d in dias_aviso if faltan <= d and d not in aviso.avisos_enviados]
    if pendientes:
        aviso.resumen = calcular(aviso.fecha_corte)
        aviso.avisos_enviados = sorted(set(aviso.avisos_enviados) | set(pendientes), reverse=True)
        aviso.ultimo_aviso = hoy
        aviso.save(update_fields=['resumen', 'avisos_enviados', 'ultimo_aviso'])
        _enviar(aviso, 'aviso', faltan)
        return 'avisado', aviso
    return 'esperando', aviso
