"""
Invitados de una actividad con invitación: carga de la lista, listado y envío de invitaciones.

- La lista se sube al crear la actividad (formulario) o después, desde esta pantalla.
- Cada carga muestra cuántos se agregaron o actualizaron, y los errores y avisos por fila.
- Se puede quitar a un invitado mientras no haya entrado.
- Invitaciones por correo, cada una con el enlace personal del invitado (/invitacion/<token>/):
  "a quienes no la han recibido" o "reenviar a quienes no han respondido". Respeta
  MAX_INVITACIONES_POR_ENVIO (los demás quedan para el siguiente envío). El enlace también se
  puede copiar para enviarlo por otro medio.
- Lo ve el Administrador y el creador de la actividad.
"""
import csv
import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .invitados import ArchivoInvalido, analizar, aplicar, leer
from .models import Actividad, Invitado, NotificacionCorreo
from .permissions import puede_gestionar_actividad
from .utils import limpiar_texto, normalizar_documento, paginar
from .views import registrar_log


logger = logging.getLogger(__name__)


def enlace_invitacion(invitado):
    """Dirección completa del enlace personal (para el correo o para copiarlo)."""
    return settings.SITE_URL.rstrip('/') + reverse('responder_invitacion', args=[invitado.token])


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
        sin_invitacion=Count('id', filter=Q(invitacion_enviada__isnull=True)),
    )
    totales['acompanantes'] = actividad.acompanantes.count()

    pagina = paginar(request, qs.order_by('nombre'))
    for inv in pagina:
        inv.enlace = enlace_invitacion(inv)
    return render(request, 'gestion/actividad_invitados.html', {
        'actividad': actividad,
        'invitados': pagina,
        'max_por_envio': settings.MAX_INVITACIONES_POR_ENVIO,
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


@login_required
@role_required('Administrador', 'Creador de Evento')
@require_POST
def enviar_invitaciones_lista(request, pk):
    """Envía la invitación con el enlace personal. modo=pendientes: a quienes nunca la
    recibieron; modo=sin_responder: también reenvía a quienes no han respondido."""
    actividad, salida = _actividad_con_permiso(request, pk)
    if salida:
        return salida
    if actividad.estado != 'ACTIVA' or actividad.fecha_inicio <= timezone.now():
        messages.error(request, 'La actividad ya comenzó o no está activa: no se envían invitaciones.')
        return redirect('invitados_actividad', pk=actividad.pk)

    modo = request.POST.get('modo')
    destinatarios = actividad.invitados.exclude(estado='RECHAZADO')
    if modo == 'sin_responder':
        destinatarios = destinatarios.filter(estado='PENDIENTE')
        filtro = 'Lista de invitados: reenvío a quienes no han respondido'
    else:
        destinatarios = destinatarios.filter(invitacion_enviada__isnull=True)
        filtro = 'Lista de invitados: quienes no la han recibido'
    total = destinatarios.count()
    destinatarios = destinatarios.order_by('nombre')
    if settings.MAX_INVITACIONES_POR_ENVIO > 0:
        destinatarios = destinatarios[:settings.MAX_INVITACIONES_POR_ENVIO]

    enviados = fallidos = 0
    for invitado in destinatarios:
        enlace = enlace_invitacion(invitado)
        try:
            html = render_to_string('gestion/email_invitacion_especial.html',
                                    {'actividad': actividad, 'invitado': invitado, 'enlace': enlace})
            n = send_mail(
                subject=f'Invitación: {actividad.titulo}',
                message=(f'Hola {invitado.nombre}, estás invitado a {actividad.titulo}. '
                         f'Confirma tu asistencia en {enlace}'),
                from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[invitado.correo],
                html_message=html, fail_silently=False,
            )
            if n != 1:
                raise RuntimeError('Correo no aceptado.')
            invitado.invitacion_enviada = timezone.now()
            invitado.save(update_fields=['invitacion_enviada'])
            estado = 'EXITO'
            enviados += 1
        except Exception:
            logger.exception('No se pudo enviar la invitación a un invitado')
            estado = 'FALLO'
            fallidos += 1
        NotificacionCorreo.objects.create(actividad=actividad, alumno=invitado.alumno, invitado=invitado,
                                          estado_envio=estado, filtro_aplicado=filtro)

    quedan = max(0, total - enviados - fallidos)
    registrar_log(request, 'Actividades', 'Envío de invitaciones',
                  f'"{actividad.titulo}" ({filtro.split(": ", 1)[1]}): {enviados} enviadas, {fallidos} fallidas'
                  + (f', {quedan} quedan para el próximo envío' if quedan else '') + '.',
                  'Actividad', actividad.id, actividad.titulo,
                  cambios_json={'enviadas': enviados, 'fallidas': fallidos, 'quedan': quedan, 'modo': modo})
    if not total:
        messages.info(request, 'No había invitados a quienes enviar en esa opción.')
    else:
        texto = f'{enviados} invitación{"es" if enviados != 1 else ""} enviada{"s" if enviados != 1 else ""}'
        if fallidos:
            texto += f', {fallidos} con error (revisa los correos en Notificaciones)'
        if quedan:
            texto += f'. Quedan {quedan}: vuelve a presionar el botón para seguir'
        (messages.warning if fallidos else messages.success)(request, texto + '.')
    return redirect('invitados_actividad', pk=actividad.pk)
