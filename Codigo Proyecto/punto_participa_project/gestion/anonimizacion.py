"""
Anonimización de un alumno (por ejemplo, cuando el titular pide la supresión de sus datos).

Se reemplazan el nombre, el RUT y el correo, y se conservan la carrera, la escuela, la jornada y la
participación (inscripciones, asistencias y cancelaciones), que alimentan las estadísticas. Es irreversible.

- Alumno: nombre "Alumno anonimizado", RUT ANON<id>, sin correo, bloqueado a mano para que la nómina no lo
  reactive. Si el estudiante vuelve a la nómina, entra como un registro nuevo.
- Invitados con su RUT o enlazados a él, y los acompañantes que registró: nombre, RUT y correo reemplazados.
- Lista de espera: se quita.
- Auditoría: se reemplazan su nombre y su RUT en los registros que los mencionan.
"""
import json

from django.db import transaction
from django.db.models import Q, TextField
from django.db.models.functions import Cast

from .models import Alumno, Invitado, ListaEspera, LogAuditoria
from .utils import formatear_rut

NOMBRE = 'Alumno'
APELLIDO = 'anonimizado'
MOTIVO = 'Datos personales anonimizados (supresión).'


def esta_anonimizado(alumno):
    return (alumno.rut or '').startswith('ANON')


def _textos_a_ocultar(alumno):
    textos = {f'{alumno.nombres} {alumno.apellidos}'.strip(), alumno.rut or ''}
    if alumno.rut:
        textos.add(formatear_rut(alumno.rut))
    if alumno.correo:
        textos.add(alumno.correo)
    return [t for t in textos if t and len(t) >= 4]


def anonimizar(alumno):
    """Anonimiza al alumno y lo que lo identifica. Devuelve el número de registros de auditoría corregidos."""
    if esta_anonimizado(alumno):
        return 0
    ocultar = _textos_a_ocultar(alumno)
    rut_original = alumno.rut
    with transaction.atomic():
        alumno = Alumno.objects.select_for_update().get(pk=alumno.pk)
        invitados = Invitado.objects.filter(Q(alumno=alumno) | Q(rut=rut_original))
        for inv in invitados:
            for acomp in inv.acompanantes.all():
                ocultar.extend(t for t in (acomp.nombre, acomp.rut) if t and len(t) >= 4)
                acomp.nombre = 'Acompañante anonimizado'
                acomp.rut = f'ANONA{acomp.pk}'
                acomp.save(update_fields=['nombre', 'rut'])
            ocultar.extend(t for t in (inv.nombre, inv.correo) if t and len(t) >= 4)
            inv.nombre = 'Invitado anonimizado'
            inv.rut = f'ANONI{inv.pk}'
            inv.correo = ''
            inv.save(update_fields=['nombre', 'rut', 'correo'])
        ListaEspera.objects.filter(alumno=alumno).delete()

        alumno.nombres = NOMBRE
        alumno.apellidos = f'{APELLIDO} {alumno.pk}'
        alumno.rut = f'ANON{alumno.pk}'
        alumno.correo = ''
        alumno.activo = False
        alumno.bloqueo_manual = True
        alumno.motivo_bloqueo = MOTIVO
        alumno.save()

        corregidos = 0
        filtro = Q(objeto_tipo='Alumno', objeto_id=alumno.pk)
        for t in set(ocultar):
            filtro |= Q(detalle__icontains=t) | Q(objeto_nombre__icontains=t) | Q(cambios_txt__icontains=t)
        logs = LogAuditoria.objects.annotate(cambios_txt=Cast('cambios_json', TextField())).filter(filtro)
        orden = sorted(set(ocultar), key=len, reverse=True)
        for log in logs:
            detalle, nombre = log.detalle or '', log.objeto_nombre or ''
            cambios = json.dumps(log.cambios_json, ensure_ascii=False) if log.cambios_json is not None else None
            for t in orden:
                detalle = _reemplazar(detalle, t)
                nombre = _reemplazar(nombre, t)
                if cambios is not None:
                    cambios = _reemplazar(cambios, t)
            if log.objeto_tipo == 'Alumno' and log.objeto_id == alumno.pk:
                nombre = 'Alumno anonimizado'
            nuevos_cambios = json.loads(cambios) if cambios is not None else None
            if (detalle, nombre, nuevos_cambios) != (log.detalle or '', log.objeto_nombre or '', log.cambios_json):
                log.detalle, log.objeto_nombre, log.cambios_json = detalle, nombre, nuevos_cambios
                log.save(update_fields=['detalle', 'objeto_nombre', 'cambios_json'])
                corregidos += 1
    return corregidos


def _reemplazar(texto, buscado):
    """Reemplaza sin distinguir mayúsculas."""
    if not texto or not buscado:
        return texto
    bajo, b = texto.lower(), buscado.lower()
    salida, i = [], 0
    while True:
        j = bajo.find(b, i)
        if j < 0:
            salida.append(texto[i:])
            return ''.join(salida)
        salida.append(texto[i:j] + '[anonimizado]')
        i = j + len(buscado)
