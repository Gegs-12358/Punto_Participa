"""
Utilidades para el proyecto Punto Participa.

Contiene funciones auxiliares para:
- Normalización y validación de RUT chileno.
- Soporte para documentos de identidad de extranjeros.
- Extracción de RUT desde códigos QR de cédula de identidad.
"""

import re


__all__ = [
    'normalizar_rut',
    'validar_rut',
    'validar_rut_extranjero',
    'validar_documento',
    'formatear_rut',
    'extraer_rut_de_carnet',
    'TIPO_DOCUMENTO_CHOICES',
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

def normalizar_rut(rut):
    """
    Elimina puntos, guiones y espacios del RUT.
    Convierte la 'k' a 'K' mayúscula.
    Acepta tanto letras como números (para pasaportes).

    Ejemplo:
        >>> normalizar_rut('12.345.678-9')
        '123456789'
        >>> normalizar_rut('AB-123456')
        'AB123456'
    """
    if not rut:
        return ""
    return re.sub(r'[^0-9kK]', '', str(rut)).upper()


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
    rut = normalizar_rut(rut)

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
    rut = normalizar_rut(rut)

    if len(rut) < 8 or len(rut) > 9:
        return False

    cuerpo = rut[:-1]
    dv = rut[-1]

    # El cuerpo debe ser numérico
    if not cuerpo.isdigit():
        return False

    # El DV puede ser número o K
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
        # RUT chileno: validación estricta con módulo 11
        return validar_rut(documento)

    elif tipo in ('RUN_PROVISORIO', 'CEDULA_EXTRANJERO'):
        # RUN provisorio o cédula de extranjero: validación flexible
        return validar_rut_extranjero(documento)

    elif tipo == 'PASAPORTE':
        # Pasaporte: solo requiere longitud mínima y caracteres válidos
        doc_limpio = normalizar_documento(documento)
        return len(doc_limpio) >= 6

    else:
        # Tipo desconocido: validación flexible como fallback
        return validar_rut_extranjero(documento)


# ============================================================
# FORMATEO
# ============================================================

def formatear_rut(rut):
    """
    Da formato chileno al RUT: '12.345.678-9'.

    Si el RUT no tiene el formato chileno tradicional,
    lo devuelve tal cual fue ingresado.

    Ejemplo:
        >>> formatear_rut('123456789')
        '12.345.678-9'
        >>> formatear_rut('AB123456')
        'AB123456'
    """
    rut = normalizar_rut(rut)

    if len(rut) < 2:
        return rut

    # Si contiene letras en el cuerpo, no es un RUT chileno
    cuerpo = rut[:-1]
    if not cuerpo.isdigit():
        return rut

    dv = rut[-1]

    # Agregar puntos cada 3 dígitos desde la derecha
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

    # Si es una URL con parámetro RUN
    if 'RUN=' in texto:
        match = re.search(r'[?&]RUN=([0-9kK-]+)', texto)
        if match:
            return normalizar_rut(match.group(1))

    # Si es texto plano (RUT con puntos/guiones)
    rut_limpio = normalizar_rut(texto)

    # Si tiene más de 9 caracteres, tomar los primeros 9
    if len(rut_limpio) > 9:
        rut_limpio = rut_limpio[:9]

    return rut_limpio

# ============================================================
# PAGINACIÓN ESTÁNDAR
# ============================================================

from django.core.paginator import Paginator


# Cantidad de filas por página en todas las tablas del sistema
ITEMS_POR_PAGINA = 3


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