"""
Utilidades para el proyecto Punto Participa.

Contiene funciones auxiliares para:
- Normalización y validación de RUT chileno.
- Soporte para documentos de identidad de extranjeros (pasaportes,
  RUN provisorios, cédulas de extranjero).
- Extracción de RUT desde códigos QR de cédula de identidad.
- Búsqueda inteligente de alumnos por documento en BBDD.
- Paginación estándar.
"""

import re

from django.core.paginator import Paginator

import re
import unicodedata
from datetime import datetime

# NUL, caracteres de control (excepto \t y \n), DEL, ancho cero,
# marcas de dirección bidi y BOM.
_CONTROL = re.compile(
    r'[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]'
)


def limpiar_texto(valor, una_linea=True):
    """Normaliza a NFC y quita NUL, control, bidi y ancho cero.

    Conserva apóstrofes, tildes invertidas, comillas, tildes, ñ, emojis, etc.
    - una_linea=True: saltos de línea y tabs se convierten en un espacio
      y se colapsan espacios repetidos.
    - una_linea=False: conserva los saltos de línea (para textareas).
    La longitud NO se valida aquí: lo hacen max_length y los validadores.
    """
    if valor is None:
        return valor
    valor = unicodedata.normalize('NFC', str(valor))
    valor = _CONTROL.sub('', valor)
    if una_linea:
        valor = re.sub(r'\s+', ' ', valor)
    else:
        valor = valor.replace('\r', '')
    return valor.strip()

def limpiar_documento(valor, max_len=40):
    """Limpia un RUT/pasaporte/código recibido por POST o GET y limita su largo.
    Devuelve '' si el valor es None. No valida formato: eso lo hace
    buscar_alumno_por_documento."""
    valor = limpiar_texto(valor) or ''
    return valor[:max_len]


__all__ = [
    # Documentos de identidad
    'rut_limpio',
    'rut_formateado',
    'normalizar_rut',        # alias de rut_limpio (compatibilidad)
    'normalizar_documento',
    'validar_rut',
    'validar_rut_extranjero',
    'validar_documento',
    'formatear_rut',
    'extraer_rut_de_carnet',
    'buscar_alumno_por_documento',
    'TIPO_DOCUMENTO_CHOICES',
    # Paginación
    'paginar',
    'ITEMS_POR_PAGINA',
]


# ============================================================
# TIPOS DE DOCUMENTO ACEPTADOS
# ============================================================

TIPO_DOCUMENTO_CHOICES = [
    ('RUT', 'RUT chileno'),
    ('PASAPORTE', 'Pasaporte extranjero'),
    ('RUN_PROVISORIO', 'RUN provisorio'),
    ('CEDULA_EXTRANJERO', 'Cédula de identidad de extranjero'),
]


# ============================================================
# NORMALIZACIÓN
# ============================================================

def rut_limpio(rut):
    """
    Elimina puntos, guiones y espacios del RUT.
    Convierte la 'k' a 'K' mayúscula.
    Acepta letras (para pasaportes) y números.

    ⚠️ NO usar para buscar en BBDD: la BBDD guarda con guion.
    Para buscar, usar `buscar_alumno_por_documento()`.

    Ejemplo:
        >>> rut_limpio('12.345.678-9')
        '123456789'
        >>> rut_limpio('AB-123456')
        'AB123456'
    """
    if not rut:
        return ""
    return re.sub(r'[^0-9a-zA-Z]', '', str(rut)).upper()


# [REFACTOR] Alias de compatibilidad: admin.py y otros módulos usan
# `normalizar_rut`, pero ahora hay UNA SOLA implementación.
normalizar_rut = rut_limpio


def rut_formateado(rut):
    """
    Devuelve el RUT en formato BBDD: '<cuerpo>-<DV>' (ej: '20001550-9').

    A diferencia de `formatear_rut()`, esta función NO agrega puntos.
    Se usa para guardar y buscar en la BBDD, que guarda sin puntos.

    Si el RUT no tiene un cuerpo numérico (ej: pasaporte), lo devuelve
    tal cual estaba (limpio, sin puntos ni espacios).

    Ejemplo:
        >>> rut_formateado('200015509')
        '20001550-9'
        >>> rut_formateado('20.001.550-9')
        '20001550-9'
        >>> rut_formateado('AB123456')
        'AB123456'
    """
    limpio = rut_limpio(rut)
    if len(limpio) < 2:
        return limpio

    cuerpo = limpio[:-1]
    dv = limpio[-1]

    # Si el cuerpo no es numérico, es un pasaporte → devolver tal cual
    if not cuerpo.isdigit():
        return limpio

    return f"{cuerpo}-{dv}"


def normalizar_documento(documento):
    """
    Normaliza cualquier tipo de documento de identidad.
    Conserva letras y números (para pasaportes).
    """
    if not documento:
        return ""
    return re.sub(r'[^0-9a-zA-Z]', '', str(documento)).upper()


# ============================================================
# VALIDACIÓN DE RUT CHILENO (MÓDULO 11)
# ============================================================

def validar_rut(rut):
    """
    Valida un RUT chileno usando el algoritmo del módulo 11.

    Devuelve True si el RUT es válido, False en caso contrario.

    ⚠️ OJO: Esta función rechaza RUTs que no cumplen el módulo 11,
    incluyendo algunos RUN provisorios de extranjeros.
    Para validación flexible, usar `validar_documento()`.

    Ejemplo:
        >>> validar_rut('12.345.678-9')
        True
        >>> validar_rut('12.345.678-0')
        False
    """
    rut = rut_limpio(rut)

    if len(rut) < 8 or len(rut) > 9:
        return False

    cuerpo = rut[:-1]
    dv = rut[-1]

    if not cuerpo.isdigit():
        return False

    # Algoritmo módulo 11
    suma = 0
    multiplo = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1

    resto = suma % 11
    dv_esperado = 11 - resto

    if dv_esperado == 11:
        dv_esperado = '0'
    elif dv_esperado == 10:
        dv_esperado = 'K'
    else:
        dv_esperado = str(dv_esperado)

    return dv == dv_esperado


# ============================================================
# VALIDACIÓN FLEXIBLE (para extranjeros y casos especiales)
# ============================================================

def validar_rut_extranjero(rut):
    """
    Valida un RUT de extranjero de forma flexible.

    Acepta RUTs que:
    - Tienen entre 8 y 9 dígitos (cuerpo + DV).
    - Pueden tener DV numérico o K.
    - NO requieren pasar el algoritmo del módulo 11.

    Esto es útil para RUN provisorios o documentos de extranjeros
    que no siguen el formato chileno tradicional.
    """
    rut = rut_limpio(rut)

    if len(rut) < 8 or len(rut) > 9:
        return False

    cuerpo = rut[:-1]
    dv = rut[-1]

    if not cuerpo.isdigit():
        return False

    if not (dv.isdigit() or dv == 'K'):
        return False

    return True


def validar_documento(documento, tipo='RUT'):
    """
    Valida un documento de identidad según su tipo.

    Args:
        documento (str): El número de documento.
        tipo (str): Tipo de documento ('RUT', 'PASAPORTE',
                    'RUN_PROVISORIO', 'CEDULA_EXTRANJERO').

    Returns:
        bool: True si el documento es válido para su tipo.

    Ejemplo:
        >>> validar_documento('12.345.678-9', 'RUT')
        True
        >>> validar_documento('12.345.678-9', 'RUN_PROVISORIO')
        True
        >>> validar_documento('AB123456', 'PASAPORTE')
        True
    """
    if not documento:
        return False

    if tipo == 'RUT':
        return validar_rut(documento)

    elif tipo in ('RUN_PROVISORIO', 'CEDULA_EXTRANJERO'):
        return validar_rut_extranjero(documento)

    elif tipo == 'PASAPORTE':
        doc_limpio = normalizar_documento(documento)
        return len(doc_limpio) >= 6

    else:
        return validar_rut_extranjero(documento)


# ============================================================
# FORMATEO
# ============================================================

def formatear_rut(rut):
    """
    Da formato chileno al RUT: '12.345.678-9' (CON puntos).

    Útil para mostrar en pantalla o exportar a Excel.
    Para guardar/buscar en BBDD usar `rut_formateado()` (sin puntos).

    Si el RUT no tiene el formato chileno tradicional,
    lo devuelve tal cual fue ingresado (limpio).

    Ejemplo:
        >>> formatear_rut('123456789')
        '12.345.678-9'
        >>> formatear_rut('AB123456')
        'AB123456'
    """
    rut = rut_limpio(rut)

    if len(rut) < 2:
        return rut

    cuerpo = rut[:-1]
    if not cuerpo.isdigit():
        return rut

    dv = rut[-1]
    cuerpo_con_puntos = re.sub(r'\B(?=(\d{3})+(?!\d))', '.', cuerpo)

    return f"{cuerpo_con_puntos}-{dv}"


# ============================================================
# EXTRACCIÓN DESDE QR DE CÉDULA
# ============================================================

def extraer_rut_de_carnet(texto):
    """
    Extrae el RUT desde el texto de un código QR de cédula de identidad.

    El QR de la cédula chilena contiene una URL con el parámetro RUN.
    Esta función extrae ese parámetro y devuelve el RUT limpio.

    Ejemplo:
        >>> extraer_rut_de_carnet('https://portal.sidiv.registrocivil.cl/...?RUN=12345678-9')
        '123456789'
        >>> extraer_rut_de_carnet('12345678-9')
        '123456789'
    """
    if not texto:
        return ""

    if 'RUN=' in texto:
        match = re.search(r'[?&]RUN=([0-9kK-]+)', texto)
        if match:
            return rut_limpio(match.group(1))

    rut_l = rut_limpio(texto)

    if len(rut_l) > 9:
        rut_l = rut_l[:9]

    return rut_l


# ============================================================
# BÚSQUEDA INTELIGENTE DE ALUMNOS
# ============================================================

def buscar_alumno_por_documento(valor):
    """
    Busca un alumno probando múltiples formatos con UNA SOLA query.

    Acepta:
    - RUT chileno:   20.001.550-9 / 20001550-9 / 200015509
    - Pasaporte:     AB123456
    - RUN provisorio: 200015509
    - Cédula extranjero: E12345678

    Devuelve el objeto Alumno o None si no lo encuentra.

    ⚠️ Import diferido de `Alumno` para evitar circular import con models.

    Ejemplo de uso:
        >>> alumno = buscar_alumno_por_documento('20001550-9')
        >>> alumno = buscar_alumno_por_documento('20.001.550-9')
        >>> alumno = buscar_alumno_por_documento('200015509')
    """
    # Import diferido para evitar circular import
    from .models import Alumno

    if not valor:
        return None

    valor = str(valor).strip()
    if not valor:
        return None

    valor_upper = valor.upper()
    rut_norm = re.sub(r'[^0-9kK]', '', valor_upper)

    # Construir todas las variantes posibles
    variantes = {valor, valor_upper}

    if rut_norm and len(rut_norm) >= 7:
        variantes.add(rut_norm)                          # 200015509
        variantes.add(f"{rut_norm[:-1]}-{rut_norm[-1]}") # 20001550-9
        try:
            cuerpo = rut_norm[:-1]
            dv = rut_norm[-1]
            if cuerpo.isdigit():
                cuerpo_puntos = f"{int(cuerpo):,}".replace(',', '.')
                variantes.add(f"{cuerpo_puntos}-{dv}")   # 20.001.550-9
        except (ValueError, IndexError):
            pass

    # Variantes para pasaportes (letras + números)
    tiene_letras_pasaporte = bool(re.search(r'[A-PR-Za-pr-z]', valor_upper))
    if tiene_letras_pasaporte:
        variantes.add(valor_upper.replace(' ', ''))
        variantes.add(valor_upper.replace('-', ''))
        variantes.add(valor_upper.replace(' ', '').replace('-', '').replace('.', ''))

    # Construir un único Q con todas las variantes
    from django.db.models import Q
    q = Q()
    for v in variantes:
        if v:
            q |= Q(rut__iexact=v)

    # Fallback: búsqueda parcial (último recurso)
    if len(valor_upper) >= 6:
        q |= Q(rut__icontains=valor_upper)

    return Alumno.objects.filter(q).first()


# ============================================================
# PAGINACIÓN ESTÁNDAR
# ============================================================

# Cantidad de filas por página en todas las tablas del sistema
ITEMS_POR_PAGINA = 15


def paginar(request, queryset, param='page', por_pagina=None):
    """
    Pagina un queryset de forma estándar.

    Args:
        request: HttpRequest, para leer el número de página actual.
        queryset: QuerySet o lista a paginar.
        param: nombre del parámetro GET que contiene la página.
            Por defecto 'page'. Usar 'page_insc', 'page_asis', etc.,
            cuando hay varias tablas en la misma vista.
        por_pagina: cantidad de filas por página. Si no se indica,
            usa ITEMS_POR_PAGINA (15).

    Returns:
        Un objeto Page listo para usar en el template.

    Ejemplo:
        page_obj = paginar(request, actividades_qs)
        page_obj = paginar(request, inscripciones, param='page_insc')
    """
    if por_pagina is None:
        por_pagina = ITEMS_POR_PAGINA

    paginator = Paginator(queryset, por_pagina)
    page_number = request.GET.get(param)

    return paginator.get_page(page_number)

def fecha_o_none(valor):
    """Devuelve un objeto date si el texto es una fecha AAAA-MM-DD real; si no, None.
    Sirve para usar parámetros de la URL en filtros sin provocar un error 500."""
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor).strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def id_o_none(valor):
    """Devuelve el entero si el texto es un ID positivo razonable; si no, None."""
    if not valor:
        return None
    valor = str(valor).strip()
    if valor.isascii() and valor.isdecimal() and len(valor) <= 9:
        return int(valor)
    return None

