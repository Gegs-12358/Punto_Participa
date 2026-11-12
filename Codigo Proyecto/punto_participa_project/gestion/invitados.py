"""
Lista de invitados de una actividad con invitación (.xlsx o .csv).

Columnas obligatorias: rut, nombre, carrera y correo. Opcionales: apellidos (se juntan con
el nombre) y jornada. Se aceptan los mismos alias que en la nómina (documento, run, email,
mail, nombres...).

Reglas:
- Los datos de la lista mandan: la invitación se envía al correo de la planilla.
- Si el documento está en la nómina, el invitado se enlaza con el alumno. Si el nombre o la
  carrera no coinciden, se avisa sin bloquear. Si el alumno está bloqueado, la fila no se carga.
- Si el documento no está en la nómina, se carga igual (con aviso), sin crear al alumno.
- La carrera se busca en el catálogo; si no está, se guarda como viene y se avisa.
- Volver a cargar una lista agrega a los nuevos y actualiza los datos de los que ya estaban
  (no borra a nadie ni cambia sus respuestas).
- Errores por fila (no detienen el resto): documento inválido, correo inválido, nombre o
  carrera vacíos, documento repetido en el archivo.
"""
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from .importador_alumnos import ArchivoInvalido, inferir_tipo, leer_filas
from .models import Alumno, Carrera, Invitado, Jornada
from .utils import limpiar_texto, normalizar_documento, validar_documento, validar_rut

COLUMNAS_INVITADOS = ['rut', 'nombres', 'carrera', 'correo']
_NOMBRE_COLUMNA = {'rut': 'rut', 'nombres': 'nombre', 'carrera': 'carrera', 'correo': 'correo'}

MAX_NOMBRE = Invitado._meta.get_field('nombre').max_length
MAX_CARRERA = Invitado._meta.get_field('carrera').max_length
MAX_JORNADA = Invitado._meta.get_field('jornada').max_length


@dataclass
class ResultadoInvitados:
    nuevos: list = field(default_factory=list)        # [(fila, datos)]
    actualizados: list = field(default_factory=list)  # [(fila, datos)]
    sin_cambios: int = 0
    errores: list = field(default_factory=list)       # [(fila, mensaje)]
    avisos: list = field(default_factory=list)        # [(fila, mensaje)]

    def resumen(self):
        """Versión corta y serializable (para la sesión y la auditoría)."""
        return {
            'nuevos': len(self.nuevos), 'actualizados': len(self.actualizados),
            'sin_cambios': self.sin_cambios,
            'errores': [list(e) for e in self.errores[:200]], 'total_errores': len(self.errores),
            'avisos': [list(a) for a in self.avisos[:200]], 'total_avisos': len(self.avisos),
        }


def leer(archivo, nombre_archivo):
    """Lee el archivo y devuelve las filas. Lanza ArchivoInvalido con un mensaje para el usuario."""
    try:
        return leer_filas(archivo, nombre_archivo, obligatorias=COLUMNAS_INVITADOS)
    except ArchivoInvalido as e:
        texto = str(e)
        if texto.startswith('Faltan columnas: '):
            faltan = [_NOMBRE_COLUMNA.get(c.strip(), c.strip()) for c in texto.split(':', 1)[1].split(',')]
            texto = ('Faltan columnas: ' + ', '.join(faltan)
                     + '. La lista debe tener rut, nombre, carrera y correo.')
        raise ArchivoInvalido(texto)


_PARECE_RUT = re.compile(r'^\d{7,9}[\dK]$')


def _documento_valido(doc):
    """Más estricto que la nómina: lo que tiene forma de RUT debe tener el dígito verificador
    correcto (salvo los RUN provisorios, que parten en 100.000.000). Lo demás, como pasaporte."""
    if _PARECE_RUT.match(doc) and int(doc[:-1]) < 100_000_000:
        return validar_rut(doc)
    return validar_documento(doc, inferir_tipo(doc))


def _texto(datos, columna):
    """Celda limpia; vacía si la columna no viene (limpiar_texto(None) devuelve None)."""
    return limpiar_texto(datos.get(columna) or '') or ''


def _comparable(texto):
    return ' '.join(limpiar_texto(texto or '').casefold().split())


def analizar(filas, actividad):
    """Revisa las filas contra la nómina, el catálogo y los invitados que ya tiene la actividad.
    No escribe nada."""
    res = ResultadoInvitados()
    carreras = {c.nombre.casefold(): c for c in Carrera.objects.all()}
    jornadas = {j.nombre.casefold(): j.nombre for j in Jornada.objects.all()}
    docs = [normalizar_documento(d.get('rut')) for _, d in filas]
    nomina = {a.rut: a for a in Alumno.objects.filter(rut__in=[d for d in docs if d])}
    existentes = {i.rut: i for i in actividad.invitados.all()} if actividad and actividad.pk else {}
    vistos = {}

    for n, d in filas:
        doc = normalizar_documento(d.get('rut'))
        if not doc:
            res.errores.append((n, 'Falta el RUT.'))
            continue
        if doc in vistos:
            res.errores.append((n, f'RUT repetido en el archivo (ver fila {vistos[doc]}).'))
            continue
        vistos[doc] = n

        errores = []
        if not _documento_valido(doc):
            errores.append('RUT o documento no válido.')
        nombre = ' '.join(p for p in (_texto(d, 'nombres'), _texto(d, 'apellidos')) if p)
        if not nombre:
            errores.append('Falta el nombre.')
        elif len(nombre) > MAX_NOMBRE:
            errores.append(f'El nombre supera {MAX_NOMBRE} caracteres.')
        correo = _texto(d, 'correo')
        try:
            validate_email(correo)
        except ValidationError:
            errores.append('Correo no válido.')
        carrera_txt = _texto(d, 'carrera')
        if not carrera_txt:
            errores.append('Falta la carrera.')
        elif len(carrera_txt) > MAX_CARRERA:
            errores.append(f'La carrera supera {MAX_CARRERA} caracteres.')
        alumno = nomina.get(doc)
        if alumno is not None and not alumno.activo:
            errores.append('El alumno está bloqueado en la nómina.')
        if errores:
            res.errores.append((n, ' '.join(errores)))
            continue

        avisos = []
        carrera_obj = carreras.get(carrera_txt.casefold())
        if carrera_obj is None:
            avisos.append(f'La carrera "{carrera_txt}" no está en el catálogo.')
        carrera = carrera_obj.nombre if carrera_obj else carrera_txt
        jornada_txt = _texto(d, 'jornada')[:MAX_JORNADA]
        jornada = jornadas.get(jornada_txt.casefold(), jornada_txt) if jornada_txt else ''
        if alumno is None:
            avisos.append('No está en la nómina: se carga con los datos de la lista.')
        else:
            if _comparable(nombre) != _comparable(f'{alumno.nombres} {alumno.apellidos}'):
                avisos.append(f'En la nómina se llama "{alumno.nombres} {alumno.apellidos}".')
            if _comparable(carrera) != _comparable(alumno.carrera):
                avisos.append(f'En la nómina su carrera es "{alumno.carrera}".')
            if not jornada:
                jornada = alumno.jornada
        for aviso in avisos:
            res.avisos.append((n, aviso))

        datos = {
            'rut': doc, 'nombre': nombre, 'correo': correo, 'carrera': carrera,
            'escuela': (carrera_obj.escuela or '') if carrera_obj else '',
            'jornada': jornada, 'alumno_id': alumno.id if alumno else None,
        }
        actual = existentes.get(doc)
        if actual is None:
            res.nuevos.append((n, datos))
        elif any(getattr(actual, k) != v for k, v in datos.items()):
            res.actualizados.append((n, datos))
        else:
            res.sin_cambios += 1
    return res


@transaction.atomic
def aplicar(res, actividad):
    """Crea a los nuevos y actualiza los datos de los que ya estaban (no toca respuestas ni asistencia)."""
    for _, datos in res.nuevos:
        Invitado(actividad=actividad, **datos).save()
    for _, datos in res.actualizados:
        invitado = Invitado.objects.get(actividad=actividad, rut=datos['rut'])
        for campo, valor in datos.items():
            setattr(invitado, campo, valor)
        invitado.save()
    return len(res.nuevos), len(res.actualizados)
