"""
Invitaciones:
  - Correo de invitación por carrera y jornada (actividades masivas y talleres), con vista previa.
  - Actividades con invitación: lista de invitados (carga, quitar, plantilla, envío con enlace personal).
  - Respuesta del alumno desde su enlace (página pública, con acompañantes).
La lógica de la lista está en invitados.py.
"""
import csv
import logging

from django_ratelimit.decorators import ratelimit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import role_required
from ..servicios.invitados import analizar, aplicar, ArchivoInvalido, documento_valido, leer, MAX_NOMBRE_ACOMPANANTE
from ..models import (Acompanante, Actividad, Alumno, consentimiento, Invitado, NotificacionCorreo,
                      VERSION_POLITICA)
from ..permissions import puede_gestionar_actividad
from ..utils import formatear_rut, id_o_none, limpiar_texto, normalizar_documento, paginar

from .comun import _error_json, registrar_log

logger = logging.getLogger(__name__)


@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def enviar_invitaciones(request):
    if request.method != 'POST':
        return _error_json('Método no permitido.', 405)

    try:
        actividad_id = id_o_none(request.POST.get('actividad_id'))
        if not actividad_id:
            return _error_json('No se recibió la actividad.')

        actividad = get_object_or_404(Actividad, pk=actividad_id)
        if not puede_gestionar_actividad(request.user, actividad):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        if actividad.tipo == 'INVITACION':
            # Sin este corte, una actividad sin carreras le escribiría a toda la nómina
            return _error_json('Las invitaciones de esta actividad se envían a su lista de invitados.', 400)

        carreras = list(actividad.carreras.values_list('nombre', flat=True))
        jornadas = list(actividad.jornadas.values_list('nombre', flat=True))

        alumnos = Alumno.objects.filter(activo=True)
        if carreras:
            alumnos = alumnos.filter(carrera__in=carreras)
        if jornadas:
            alumnos = alumnos.filter(jornada__in=jornadas)
        if settings.MAX_INVITACIONES_POR_ENVIO > 0:
            alumnos = alumnos[:settings.MAX_INVITACIONES_POR_ENVIO]

        filtro = 'Todas las asociadas'
        if carreras or jornadas:
            filtro = (f"Carreras: {', '.join(carreras) or 'Todas'} | "
                      f"Jornadas: {', '.join(jornadas) or 'Todas'}")

        enviados = fallidos = 0
        for alumno in alumnos:
            try:
                html = render_to_string('gestion/correos/invitacion.html', {
                    'actividad': actividad, 'alumno': alumno, 'site_url': settings.SITE_URL,
                })
                n = send_mail(
                    subject=f'Invitación: {actividad.titulo}',
                    message=f'Hola {alumno.nombres}, te invitamos a participar en {actividad.titulo}.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[alumno.correo], html_message=html, fail_silently=False,
                )
                if n != 1:
                    raise RuntimeError('Correo no aceptado.')
                NotificacionCorreo.objects.create(actividad=actividad, alumno=alumno,
                                                  estado_envio='EXITO', filtro_aplicado=filtro)
                enviados += 1
            except Exception:
                NotificacionCorreo.objects.create(actividad=actividad, alumno=alumno,
                                                  estado_envio='FALLO', filtro_aplicado=filtro)
                fallidos += 1

        registrar_log(request, 'Actividades', 'Envío de invitaciones',
                      f'Actividad "{actividad.titulo}": {enviados} OK, {fallidos} fallidos.',
                      'Actividad', actividad.id, actividad.titulo)
        return JsonResponse({
            'success': fallidos == 0, 'enviados': enviados, 'fallidos': fallidos,
            'message': f'{enviados} invitaciones enviadas, {fallidos} fallidas.'
        })
    except Http404:
        return _error_json('La actividad ya no existe. Recarga la página.', 404)
    except Exception:
        logger.exception('Error en enviar_invitaciones')
        return _error_json('Ocurrió un error al procesar las invitaciones.', 500)


@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def previsualizar_invitacion(request, pk):
    try:
        actividad = get_object_or_404(Actividad, pk=pk)
        if not puede_gestionar_actividad(request.user, actividad):
            return _error_json('No tienes permisos sobre esta actividad.', 403)
        if actividad.tipo == 'INVITACION':
            return _error_json('Las invitaciones de esta actividad se envían a su lista de invitados.', 400)

        carreras = [c.nombre for c in actividad.carreras.all()]
        jornadas = [j.nombre for j in actividad.jornadas.all()]
        alumnos = Alumno.objects.filter(activo=True)
        if carreras:
            alumnos = alumnos.filter(carrera__in=carreras)
        if jornadas:
            alumnos = alumnos.filter(jornada__in=jornadas)

        alumno = alumnos.first()
        if not alumno:
            return _error_json('No hay alumnos que coincidan con los filtros.')

        html = render_to_string('gestion/correos/invitacion.html', {
            'actividad': actividad, 'alumno': alumno, 'site_url': settings.SITE_URL,
        })
        return JsonResponse({
            'success': True, 'html': html,
            'alumno_ejemplo': f'{alumno.nombres} {alumno.apellidos}',
            'total_destinatarios': alumnos.count(),
        })
    except Http404:
        return _error_json('La actividad ya no existe. Recarga la página.', 404)
    except Exception:
        logger.exception('Error en previsualizar_invitacion')
        return _error_json('Ocurrió un error inesperado.', 500)


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
            html = render_to_string('gestion/correos/invitacion_especial.html',
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






def _estado_pagina(actividad):
    if actividad.estado == 'CANCELADA':
        return 'cancelada'
    if actividad.estado == 'FINALIZADA' or actividad.fecha_inicio <= timezone.now():
        return 'cerrada'
    return 'abierta'


def _leer_acompanantes(post, maximo):
    """[(fila, documento_normalizado, documento_escrito, nombre)] de las filas con algún dato."""
    filas = []
    for i in range(1, maximo + 1):
        escrito = limpiar_texto(post.get(f'acompanante_{i}_documento') or '')[:30]
        nombre = limpiar_texto(post.get(f'acompanante_{i}_nombre') or '')
        if escrito or nombre:
            filas.append((i, normalizar_documento(escrito) or '', escrito, nombre))
    return filas


def _validar_acompanantes(invitado, filas):
    """Devuelve {fila: mensaje} con los errores (vacío si todo está bien)."""
    actividad = invitado.actividad
    errores = {}
    vistos = set()
    otros_docs = set(actividad.invitados.values_list('rut', flat=True)) | set(
        actividad.acompanantes.exclude(invitado=invitado).values_list('rut', flat=True))
    for fila, doc, _, nombre in filas:
        if not doc or not documento_valido(doc):
            errores[fila] = 'El RUT o pasaporte no es válido.'
        elif not nombre:
            errores[fila] = 'Falta el nombre.'
        elif len(nombre) > MAX_NOMBRE_ACOMPANANTE:
            errores[fila] = f'El nombre supera {MAX_NOMBRE_ACOMPANANTE} caracteres.'
        elif doc == invitado.rut:
            errores[fila] = 'Ese es tu propio documento: tú ya estás invitado.'
        elif doc in vistos:
            errores[fila] = 'Ese documento está repetido.'
        elif doc in otros_docs:
            errores[fila] = 'Ese documento ya está registrado en esta actividad.'
        vistos.add(doc)
    return errores


@ratelimit(key='ip', rate='30/m', method='POST', block=False)
def responder_invitacion(request, token):
    invitado = get_object_or_404(Invitado.objects.select_related('actividad'), token=token,
                                 actividad__tipo='INVITACION')
    actividad = invitado.actividad
    maximo = actividad.acompanantes_por_invitado
    estado_pagina = _estado_pagina(actividad)
    contexto = {'invitado': invitado, 'actividad': actividad, 'estado_pagina': estado_pagina,
                'maximo': maximo}

    acompanantes = list(invitado.acompanantes.order_by('fecha_registro', 'pk'))
    valores = {i: {'documento': formatear_rut(a.rut), 'nombre': a.nombre}
               for i, a in enumerate(acompanantes, start=1)}

    if request.method == 'POST' and estado_pagina == 'abierta':
        if getattr(request, 'limited', False):
            contexto['error'] = 'Demasiados intentos seguidos. Espera un minuto y vuelve a intentarlo.'
            contexto.update(filas_form=[{'i': i, 'documento': '', 'nombre': '', 'error': ''}
                                        for i in range(1, maximo + 1)],
                            asistira='', acompanantes=acompanantes)
            return render(request, 'gestion/invitacion_publica.html', contexto, status=429)
        asistira = request.POST.get('asistira')
        filas = _leer_acompanantes(request.POST, maximo) if asistira == 'si' else []
        valores = {i: {'documento': escrito, 'nombre': nombre} for i, _, escrito, nombre in filas}
        errores = _validar_acompanantes(invitado, filas)
        if asistira not in ('si', 'no'):
            contexto['error'] = 'Indica si vas a asistir.'
        elif not request.POST.get('acepta_politica'):
            contexto['error'] = 'Para responder debes aceptar la Política de Privacidad.'
        elif errores:
            contexto['error'] = 'Revisa los datos de tus acompañantes.'
            contexto['errores_fila'] = errores
        else:
            with transaction.atomic():
                invitado.acompanantes.filter(ingreso__isnull=True).delete()
                for _, doc, _, nombre in filas:
                    Acompanante.objects.create(actividad=actividad, invitado=invitado, rut=doc, nombre=nombre)
                invitado.estado = 'CONFIRMADO' if asistira == 'si' else 'RECHAZADO'
                invitado.fecha_respuesta = timezone.now()
                for campo, valor in consentimiento().items():
                    setattr(invitado, campo, valor)
                invitado.save(update_fields=['estado', 'fecha_respuesta', 'politica_version', 'politica_aceptada'])
            detalle = (f'{invitado.nombre} confirmó su asistencia a "{actividad.titulo}" con '
                       f'{len(filas)} acompañante{"s" if len(filas) != 1 else ""}'
                       if asistira == 'si' else f'{invitado.nombre} no asistirá a "{actividad.titulo}"')
            registrar_log(request, 'Invitaciones', 'Respuesta a invitación',
                          f'{detalle}. Política de Privacidad {VERSION_POLITICA} aceptada.',
                          'Actividad', actividad.id, actividad.titulo,
                          cambios_json={'invitado': invitado.nombre, 'respuesta': invitado.estado,
                                        'acompanantes': len(filas)})
            contexto['exito'] = ('¡Listo! Te esperamos.' if asistira == 'si'
                                 else 'Gracias por avisar. Si cambias de opinión, vuelve a este enlace.')
            valores = {i: {'documento': formatear_rut(doc), 'nombre': nombre}
                       for i, (_, doc, _, nombre) in enumerate(filas, start=1)}

    errores = contexto.get('errores_fila', {})
    contexto['filas_form'] = [
        {'i': i, 'documento': valores.get(i, {}).get('documento', ''),
         'nombre': valores.get(i, {}).get('nombre', ''), 'error': errores.get(i, '')}
        for i in range(1, maximo + 1)
    ]
    contexto['asistira'] = (request.POST.get('asistira') if request.method == 'POST' and 'exito' not in contexto
                            else {'CONFIRMADO': 'si', 'RECHAZADO': 'no'}.get(invitado.estado, ''))
    contexto['acompanantes'] = list(invitado.acompanantes.order_by('fecha_registro', 'pk'))
    return render(request, 'gestion/invitacion_publica.html', contexto)
