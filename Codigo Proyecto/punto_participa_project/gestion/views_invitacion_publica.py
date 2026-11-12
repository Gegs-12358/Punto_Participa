"""
Respuesta a una invitación especial: /invitacion/<token>/ (público, sin cuenta).

Cada invitado tiene su propio enlace (Invitado.token, 32 caracteres aleatorios), que llega por
correo o se lo comparte el Punto. En la página:

- Confirma si asistirá o no.
- Si asiste, registra a sus acompañantes (documento y nombre), hasta el máximo de la actividad.
  Cada acompañante entra escaneando su propio documento.
- Acepta la Política de Privacidad (queda en la auditoría).
- Puede cambiar su respuesta hasta que empiece la actividad; después la página solo la muestra.

El documento de un acompañante no puede ser el del invitado ni estar ya registrado en la
actividad (como invitado o como acompañante de otro). El mensaje no dice de quién es.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from .invitados import documento_valido
from .models import Acompanante, Invitado
from .utils import formatear_rut, limpiar_texto, normalizar_documento
from .views import registrar_log

MAX_NOMBRE = Acompanante._meta.get_field('nombre').max_length
VERSION_POLITICA = 'v2026-1'


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
        elif len(nombre) > MAX_NOMBRE:
            errores[fila] = f'El nombre supera {MAX_NOMBRE} caracteres.'
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
                invitado.save(update_fields=['estado', 'fecha_respuesta'])
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
