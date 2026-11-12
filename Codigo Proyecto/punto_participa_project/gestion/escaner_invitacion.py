"""
Escáner en actividades con invitación (paso 3a).

Entran, cada uno con su propio documento:
- los invitados de la lista (estén o no en la nómina);
- los acompañantes que registró cada invitado.

Si llega alguien que no está en la lista, el operador puede agregarlo en la entrada:
- un alumno de la nómina (activo) queda como invitado "agregado en la entrada";
- otra persona queda como acompañante de un invitado que todavía tenga cupo de acompañante.

La asistencia se guarda en Invitado/Acompanante (ingreso, método, quién registró). A los
invitados que están en la nómina se les crea además su Asistencia, para que aparezca en la
ficha del alumno y en los gráficos de Reportes.

Respuestas JSON (las mismas claves que el escáner normal):
- {confirmar: true, alumno: {...}}: pedir confirmación al operador.
- {success: true, contador: {...}}: ingreso registrado.
- {success: false, agregar: 'alumno' | 'acompanante', ...}: no está en la lista; se ofrece agregarlo.
- error con status 4xx: no se registra.
"""
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone

from .models import Acompanante, Alumno, Asistencia, Invitado, foto_academica
from .utils import buscar_alumno_por_documento, formatear_rut, limpiar_texto, normalizar_documento
from .views import _contador_escaneo, _error_json, registrar_log

METODOS = {'RUT': 'RUT', 'QR': 'Código QR', 'CODIGO': 'Código de barras'}
MAX_NOMBRE = Acompanante._meta.get_field('nombre').max_length


def _persona_invitado(invitado):
    n = invitado.acompanantes.count()
    detalle = 'Invitado'
    if invitado.agregado_en_entrada:
        detalle += ' (agregado en la entrada)'
    if invitado.carrera:
        detalle += f', {invitado.carrera}'
    if n:
        detalle += f'. Registró {n} acompañante{"s" if n != 1 else ""}'
    return {'nombre': invitado.nombre, 'rut': formatear_rut(invitado.rut), 'carrera': invitado.carrera,
            'jornada': invitado.jornada, 'detalle': detalle + '.'}


def _persona_acompanante(acompanante):
    return {'nombre': acompanante.nombre, 'rut': formatear_rut(acompanante.rut), 'carrera': '', 'jornada': '',
            'detalle': f'Acompañante de {acompanante.invitado.nombre}.'}


def _ya_ingreso(request, actividad, persona, hora):
    registrar_log(request, 'Escáner', 'Intento de asistencia duplicada',
                  f'{persona} en "{actividad.titulo}" (ya había ingresado a las {hora})',
                  'Actividad', actividad.id, actividad.titulo)
    return _error_json(f'{persona} ya ingresó a las {hora}.', 409)


def _exito(request, actividad, persona, metodo, mensaje):
    return JsonResponse({'success': True, 'confirmar': False, 'message': mensaje, 'metodo': metodo,
                         'alumno': persona, 'contador': _contador_escaneo(request, actividad)})


def _marcar_ingreso(registro, request, metodo):
    registro.ingreso = timezone.now()
    registro.metodo_ingreso = metodo
    registro.registrado_por = request.user
    registro.save(update_fields=['ingreso', 'metodo_ingreso', 'registrado_por'])


def _asistencia_de_alumno(actividad, invitado, request, metodo):
    """Asistencia normal para los invitados de la nómina (ficha del alumno y gráficos)."""
    alumno = invitado.alumno
    if alumno is None or not alumno.activo:
        return
    try:
        with transaction.atomic():
            Asistencia.objects.create(actividad=actividad, alumno=alumno, metodo_ingreso=metodo,
                                      registrado_por=request.user)
    except IntegrityError:
        pass   # ya tenía su asistencia: el ingreso del invitado igual queda registrado


def _opciones_acompanante(actividad):
    """Invitados (que no dijeron que no) con cupo de acompañante; primero los que ya entraron."""
    maximo = actividad.acompanantes_por_invitado
    if not maximo:
        return []
    opciones = []
    for inv in actividad.invitados.exclude(estado='RECHAZADO').prefetch_related('acompanantes'):
        quedan = maximo - len(inv.acompanantes.all())
        if quedan > 0:
            opciones.append({'id': inv.id, 'nombre': inv.nombre, 'quedan': quedan,
                             'entro': bool(inv.ingreso)})
    opciones.sort(key=lambda o: (not o['entro'], o['nombre'].lower()))
    return opciones


def procesar(request, actividad, metodo, documento, confirmar):
    doc = normalizar_documento(documento) or ''
    agregar = request.POST.get('agregar', '')

    with transaction.atomic():
        invitado = actividad.invitados.select_for_update().filter(rut=doc).first() if doc else None
        acompanante = (None if invitado or not doc else
                       actividad.acompanantes.select_for_update().select_related('invitado').filter(rut=doc).first())

        # ---- Invitado de la lista ----
        if invitado:
            persona = _persona_invitado(invitado)
            if invitado.ingreso:
                return _ya_ingreso(request, actividad, invitado.nombre,
                                   timezone.localtime(invitado.ingreso).strftime('%H:%M'))
            if not confirmar:
                return JsonResponse({'success': True, 'confirmar': True, 'alumno': persona})
            _marcar_ingreso(invitado, request, metodo)
            _asistencia_de_alumno(actividad, invitado, request, metodo)
            registrar_log(request, 'Escáner', 'Ingreso de invitado', f'{invitado.nombre} - {actividad.titulo}',
                          'Actividad', actividad.id, actividad.titulo)
            return _exito(request, actividad, persona, metodo, f'Ingreso registrado: {invitado.nombre}.')

        # ---- Acompañante registrado ----
        if acompanante:
            persona = _persona_acompanante(acompanante)
            if acompanante.ingreso:
                return _ya_ingreso(request, actividad, acompanante.nombre,
                                   timezone.localtime(acompanante.ingreso).strftime('%H:%M'))
            if not confirmar:
                return JsonResponse({'success': True, 'confirmar': True, 'alumno': persona})
            _marcar_ingreso(acompanante, request, metodo)
            registrar_log(request, 'Escáner', 'Ingreso de acompañante',
                          f'{acompanante.nombre} (acompaña a {acompanante.invitado.nombre}) - {actividad.titulo}',
                          'Actividad', actividad.id, actividad.titulo)
            return _exito(request, actividad, persona, metodo,
                          f'Ingreso registrado: {acompanante.nombre}, acompañante de {acompanante.invitado.nombre}.')

    # ---- No está en la lista ----
    alumno = buscar_alumno_por_documento(documento)
    if alumno is None and doc:
        # buscar_alumno_por_documento solo devuelve activos: un bloqueado no se puede agregar
        bloqueado = Alumno.objects.filter(rut=doc, activo=False).first()
        if bloqueado:
            return _error_json(f'{bloqueado.nombres} {bloqueado.apellidos} está bloqueado: no puede ingresar.', 403)

    if alumno is not None:
        persona = {'nombre': f'{alumno.nombres} {alumno.apellidos}', 'rut': formatear_rut(alumno.rut),
                   'carrera': alumno.carrera, 'jornada': alumno.jornada,
                   'detalle': f'Alumno de {alumno.carrera}. No está en la lista de invitados.'}
        if agregar != 'alumno' or not confirmar:
            return JsonResponse({'success': False, 'agregar': 'alumno', 'alumno': persona,
                                 'message': f'{persona["nombre"]} no está en la lista de invitados. '
                                            '¿Lo agregas y registras su ingreso?'})
        return _agregar_alumno(request, actividad, alumno, metodo, persona)

    opciones = _opciones_acompanante(actividad)
    if agregar == 'acompanante' and confirmar:
        return _agregar_acompanante(request, actividad, doc, metodo, opciones)
    if not opciones:
        registrar_log(request, 'Escáner', 'Intento de ingreso sin invitación',
                      f'Documento que no está en la lista de "{actividad.titulo}"',
                      'Actividad', actividad.id, actividad.titulo)
        return _error_json('Este documento no está en la lista de invitados ni entre los acompañantes, '
                           'y ningún invitado tiene cupo para un acompañante más.', 403)
    return JsonResponse({
        'success': False, 'agregar': 'acompanante', 'invitados': opciones,
        'documento': formatear_rut(doc),
        'message': 'Este documento no está en la lista. Si es acompañante de un invitado, '
                   'elige de quién y escribe su nombre.',
    })


def _agregar_alumno(request, actividad, alumno, metodo, persona):
    foto = foto_academica(alumno)
    try:
        with transaction.atomic():
            invitado = Invitado.objects.create(
                actividad=actividad, alumno=alumno, rut=alumno.rut,
                nombre=f'{alumno.nombres} {alumno.apellidos}', correo=alumno.correo,
                carrera=foto['carrera'], escuela=foto['escuela'], jornada=foto['jornada'],
                estado='CONFIRMADO', fecha_respuesta=timezone.now(), agregado_en_entrada=True)
            _marcar_ingreso(invitado, request, metodo)
    except IntegrityError:
        return _error_json('Otro operador acaba de registrar a esta persona.', 409)
    _asistencia_de_alumno(actividad, invitado, request, metodo)
    registrar_log(request, 'Escáner', 'Agregar invitado en la entrada',
                  f'{invitado.nombre} no estaba en la lista de "{actividad.titulo}": se agregó y entró.',
                  'Actividad', actividad.id, actividad.titulo)
    persona['detalle'] = 'Invitado (agregado en la entrada).'
    return _exito(request, actividad, persona, metodo, f'{invitado.nombre} agregado e ingreso registrado.')


def _agregar_acompanante(request, actividad, doc, metodo, opciones):
    nombre = limpiar_texto(request.POST.get('nombre') or '')
    try:
        invitado_id = int(request.POST.get('invitado_id') or 0)
    except (TypeError, ValueError):
        invitado_id = 0
    if not doc:
        return _error_json('Falta el documento del acompañante.')
    if not nombre or len(nombre) > MAX_NOMBRE:
        return _error_json('Escribe el nombre completo del acompañante.')
    if invitado_id not in {o['id'] for o in opciones}:
        return _error_json('Elige un invitado que todavía tenga cupo de acompañante.')
    try:
        with transaction.atomic():
            invitado = Invitado.objects.select_for_update().get(pk=invitado_id, actividad=actividad)
            if invitado.acompanantes.count() >= actividad.acompanantes_por_invitado:
                return _error_json(f'{invitado.nombre} ya no tiene cupo para otro acompañante.', 409)
            acompanante = Acompanante.objects.create(actividad=actividad, invitado=invitado, rut=doc,
                                                     nombre=nombre, agregado_en_entrada=True)
            _marcar_ingreso(acompanante, request, metodo)
    except IntegrityError:
        return _error_json('Otro operador acaba de registrar este documento.', 409)
    registrar_log(request, 'Escáner', 'Agregar acompañante en la entrada',
                  f'{nombre} entró como acompañante de {invitado.nombre} en "{actividad.titulo}".',
                  'Actividad', actividad.id, actividad.titulo)
    return _exito(request, actividad, _persona_acompanante(acompanante), metodo,
                  f'{nombre} agregado como acompañante de {invitado.nombre}.')


def registros(actividad):
    """Ingresos de invitados y acompañantes, para el contador del escáner."""
    filas = []
    for inv in actividad.invitados.filter(ingreso__isnull=False).select_related('registrado_por'):
        filas.append((inv, inv.nombre))
    for ac in actividad.acompanantes.filter(ingreso__isnull=False).select_related('registrado_por'):
        filas.append((ac, ac.nombre))
    return [{'nombre': nombre, 'metodo': METODOS.get(r.metodo_ingreso, r.metodo_ingreso),
             'registrado_por_id': r.registrado_por_id,
             'operador_nombre': (r.registrado_por.first_name or r.registrado_por.username) if r.registrado_por else '',
             'fecha': r.ingreso} for r, nombre in filas]
