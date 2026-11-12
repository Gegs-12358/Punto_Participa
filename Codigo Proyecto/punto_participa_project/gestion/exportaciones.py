"""
Exportaciones de Reportes (P1, historia 005).

Tres reportes, cada uno en Excel o CSV, con los mismos filtros de la pantalla:

  resumen        Una fila por actividad: lugar, horario, estado, cupos, invitados,
                 inscritos, asistentes, no asistieron y % de asistencia.
  participacion  Una fila por actividad, escuela, carrera y jornada: inscritos,
                 asistentes y no asistieron.
  participantes  Listado nominal: una fila por alumno y actividad, con su inscripción
                 y su asistencia (hora, método y quién lo registró).
  libro          Los tres anteriores en un solo Excel (una hoja cada uno).

Reglas:
  - Solo Administrador y Creador de Evento. El creador ve solo sus actividades
    (lo aplica _aplicar_filtros_reporte).
  - Escuela, carrera y jornada son las que el alumno tenía al inscribirse o asistir
    (la "foto" académica), no las de hoy.
  - Cada Excel trae una hoja "Información" con la fecha, quién lo descargó, los filtros
    usados y qué significa cada columna. Las fechas son fechas reales (se pueden ordenar
    y filtrar), con encabezado fijo y autofiltro.
  - Cada descarga queda registrada en la auditoría.
"""
import csv
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, OuterRef, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .decorators import role_required
from .models import Actividad, Alumno, Asistencia, Carrera, Inscripcion, NotificacionCorreo
from .utils import fecha_o_none, formatear_rut, id_o_none, limpiar_texto
from .views import _aplicar_filtros_reporte, _filtrar_por_foto, _sanitizar_celda, registrar_log

# Tipo de cada columna: cómo se escribe en Excel y en CSV
TEXTO, ENTERO, FECHA, PORCENTAJE = 'texto', 'entero', 'fecha', 'porcentaje'

FORMATO_FECHA_EXCEL = 'dd/mm/yyyy hh:mm'
FORMATO_FECHA_CSV = '%d/%m/%Y %H:%M'
COLOR_ENCABEZADO = '002F5F'   # --navy de la guía de estilo

SI, NO, NO_APLICA, PENDIENTE = 'Sí', 'No', 'No aplica', 'Pendiente'


class Reporte:
    """Un reporte listo para escribir: nombre, columnas (título, tipo) y filas."""

    def __init__(self, clave, titulo, hoja, columnas, filas, definiciones):
        self.clave = clave
        self.titulo = titulo
        self.hoja = hoja                  # nombre de la hoja de Excel (máx. 31 caracteres)
        self.columnas = columnas          # [(título, tipo), ...]
        self.filas = filas                # [[valor, ...], ...]
        self.definiciones = definiciones  # [(columna, explicación), ...]


# ============================================================
# DATOS
# ============================================================

def _filtros(request):
    """Filtros de la URL, ya limpios."""
    g = request.GET
    return {
        'actividad': id_o_none(g.get('actividad')),
        'escuela': limpiar_texto(g.get('escuela', ''))[:100],
        'carrera': limpiar_texto(g.get('carrera', ''))[:100],
        'jornada': limpiar_texto(g.get('jornada', ''))[:20],
        'lugar': limpiar_texto(g.get('lugar', ''))[:200],
        'tipo': g.get('tipo', '') if g.get('tipo', '') in dict(Actividad.TIPO_CHOICES) else '',
        'fecha_inicio': fecha_o_none(g.get('fecha_inicio')),
        'fecha_fin': fecha_o_none(g.get('fecha_fin')),
    }


def _local(dt):
    """Fecha y hora local sin zona horaria (Excel no acepta zona horaria)."""
    return timezone.localtime(dt).replace(tzinfo=None, microsecond=0) if dt else None


def _ya_empezo(act):
    """Antes de que empiece la actividad, "no asistió" todavía no se sabe."""
    return act.fecha_inicio <= timezone.now()


def _base(request):
    """Actividades visibles para el usuario con los filtros aplicados, y sus inscripciones y asistencias."""
    f = _filtros(request)
    act_qs, asis_qs = _aplicar_filtros_reporte(request)
    actividades = list(act_qs.select_related('creado_por').order_by('-fecha_inicio', 'titulo'))
    ids = [a.id for a in actividades]

    asistio = Asistencia.objects.filter(actividad_id=OuterRef('actividad_id'), alumno_id=OuterRef('alumno_id'))
    insc_qs = _filtrar_por_foto(
        Inscripcion.objects.filter(actividad_id__in=ids), f['carrera'], f['jornada'], f['escuela']
    ).annotate(asistio=Exists(asistio))
    return f, actividades, insc_qs, asis_qs


def _invitados_por_actividad(ids, f):
    """
    Alumnos distintos a los que se les envió la invitación con éxito.
    Las invitaciones no guardan foto académica: se filtra con los datos actuales del alumno.
    """
    qs = NotificacionCorreo.objects.filter(actividad_id__in=ids, estado_envio='EXITO', alumno__isnull=False)
    if f['carrera']:
        qs = qs.filter(alumno__carrera__iexact=f['carrera'])
    if f['jornada']:
        qs = qs.filter(alumno__jornada__iexact=f['jornada'])
    if f['escuela']:
        carreras = Carrera.objects.filter(escuela__iexact=f['escuela']).values_list('nombre', flat=True)
        qs = qs.filter(alumno__carrera__in=list(carreras))
    return {i['actividad_id']: i['t'] for i in
            qs.order_by().values('actividad_id').annotate(t=Count('alumno_id', distinct=True))}


def reporte_resumen(request, datos=None):
    f, actividades, insc_qs, asis_qs = datos or _base(request)
    ids = [a.id for a in actividades]

    confirmadas = insc_qs.filter(estado='CONFIRMADA').order_by()
    inscritos = {i['actividad_id']: (i['t'], i['a']) for i in confirmadas.values('actividad_id').annotate(
        t=Count('id'), a=Count('id', filter=Q(asistio=True)))}
    asistentes = {i['actividad_id']: i['t'] for i in
                  asis_qs.order_by().values('actividad_id').annotate(t=Count('id'))}
    invitados = _invitados_por_actividad(ids, f)

    filas = []
    for act in actividades:
        n_insc, n_asistieron = inscritos.get(act.id, (0, 0))
        n_asis = asistentes.get(act.id, 0)
        if not _ya_empezo(act):
            no_asistieron = pct = None
        elif act.tipo == 'TALLER':
            no_asistieron = n_insc - n_asistieron
            pct = (n_asistieron / n_insc) if n_insc else None
        else:
            no_asistieron = None
            pct = (n_asis / act.cupos_totales) if act.cupos_totales else None
        filas.append([
            act.titulo, act.get_tipo_display(), act.get_estado_display(),
            _local(act.fecha_inicio), _local(act.fecha_fin), act.lugar_completo,
            act.creado_por.username if act.creado_por else '',
            act.cupos_totales, invitados.get(act.id, 0),
            n_insc if act.tipo == 'TALLER' else None, n_asis, no_asistieron, pct,
        ])

    return Reporte(
        'resumen', 'Resumen por actividad', 'Resumen por actividad',
        [('Actividad', TEXTO), ('Tipo', TEXTO), ('Estado', TEXTO), ('Inicio', FECHA), ('Término', FECHA),
         ('Lugar', TEXTO), ('Creador', TEXTO), ('Cupos', ENTERO), ('Invitados', ENTERO),
         ('Inscritos', ENTERO), ('Asistentes', ENTERO), ('No asistieron', ENTERO), ('% asistencia', PORCENTAJE)],
        filas,
        [('Invitados', 'Alumnos distintos a los que les llegó la invitación por correo.'),
         ('Inscritos', 'Solo talleres: inscripciones confirmadas.'),
         ('Asistentes', 'Asistencias registradas en el escáner.'),
         ('No asistieron', 'Solo talleres: inscritos que no registraron asistencia. '
                           'Vacío si la actividad todavía no empieza.'),
         ('% asistencia', 'Talleres: inscritos que asistieron ÷ inscritos. '
                          'Masivas: asistentes ÷ cupos (vacío si no tiene cupos). '
                          'Vacío si la actividad todavía no empieza.')],
    )


def reporte_participacion(request, datos=None):
    f, actividades, insc_qs, asis_qs = datos or _base(request)
    por_id = {a.id: a for a in actividades}
    grupos = defaultdict(lambda: {'insc': 0, 'asis': 0, 'no': 0})

    for i in (insc_qs.filter(estado='CONFIRMADA').order_by()
              .values('actividad_id', 'escuela', 'carrera', 'jornada')
              .annotate(t=Count('id'), no=Count('id', filter=Q(asistio=False)))):
        g = grupos[(i['actividad_id'], i['escuela'], i['carrera'], i['jornada'])]
        g['insc'] += i['t']
        g['no'] += i['no']
    for i in (asis_qs.order_by().values('actividad_id', 'escuela', 'carrera', 'jornada')
              .annotate(t=Count('id'))):
        grupos[(i['actividad_id'], i['escuela'], i['carrera'], i['jornada'])]['asis'] += i['t']

    orden = {a.id: n for n, a in enumerate(actividades)}
    filas = []
    for (act_id, escuela, carrera, jornada), g in sorted(
            grupos.items(), key=lambda kv: (orden[kv[0][0]], kv[0][1] or '~', kv[0][2], kv[0][3])):
        act = por_id[act_id]
        es_taller = act.tipo == 'TALLER'
        filas.append([
            act.titulo, act.get_tipo_display(), _local(act.fecha_inicio),
            escuela or 'Sin escuela', carrera or 'Sin carrera', jornada or 'Sin jornada',
            g['insc'] if es_taller else None, g['asis'],
            g['no'] if es_taller and _ya_empezo(act) else None,
        ])

    return Reporte(
        'participacion', 'Participación por escuela, carrera y jornada', 'Por escuela y carrera',
        [('Actividad', TEXTO), ('Tipo', TEXTO), ('Inicio', FECHA), ('Escuela', TEXTO), ('Carrera', TEXTO),
         ('Jornada', TEXTO), ('Inscritos', ENTERO), ('Asistentes', ENTERO), ('No asistieron', ENTERO)],
        filas,
        [('Escuela, Carrera, Jornada', 'Las que tenía el alumno al inscribirse o asistir.'),
         ('Inscritos y No asistieron', 'Solo talleres (las masivas no tienen inscripción). '
                                       'No asistieron queda vacío si la actividad todavía no empieza.')],
    )


def reporte_participantes(request, datos=None):
    f, actividades, insc_qs, asis_qs = datos or _base(request)
    por_id = {a.id: a for a in actividades}
    alumno = ['alumno__rut', 'alumno__tipo_documento', 'alumno__nombres', 'alumno__apellidos', 'alumno__correo']
    personas = {}

    for i in insc_qs.order_by().values('actividad_id', 'alumno_id', 'escuela', 'carrera', 'jornada',
                                       'estado', 'fecha_inscripcion', *alumno):
        personas[(i['actividad_id'], i['alumno_id'])] = {'insc': i, 'datos': i, 'asis': None}
    for i in asis_qs.order_by().values('actividad_id', 'alumno_id', 'escuela', 'carrera', 'jornada',
                                       'fecha_ingreso', 'metodo_ingreso', 'registrado_por__username', *alumno):
        p = personas.setdefault((i['actividad_id'], i['alumno_id']), {'insc': None, 'datos': i, 'asis': None})
        p['asis'] = i
        p['datos'] = i      # al asistir, la foto de la asistencia es la más reciente

    estados = dict(Inscripcion.ESTADO_CHOICES)
    tipos_doc = dict(Alumno.TIPO_DOCUMENTO_CHOICES)
    metodos = dict(Asistencia.METODO_CHOICES)
    orden = {a.id: n for n, a in enumerate(actividades)}

    filas = []
    for (act_id, _), p in sorted(personas.items(), key=lambda kv: (
            orden[kv[0][0]], (kv[1]['datos']['alumno__apellidos'] or '').lower(),
            (kv[1]['datos']['alumno__nombres'] or '').lower())):
        act, d, insc, asis = por_id[act_id], p['datos'], p['insc'], p['asis']
        documento = d['alumno__rut'] or ''
        if d['alumno__tipo_documento'] == 'RUT':
            documento = formatear_rut(documento)
        if act.tipo != 'TALLER' and insc is None:
            inscrito, estado, fecha_insc = NO_APLICA, '', None
        else:
            inscrito = SI if insc and insc['estado'] == 'CONFIRMADA' else NO
            estado = estados.get(insc['estado'], insc['estado']) if insc else ''
            fecha_insc = _local(insc['fecha_inscripcion']) if insc else None
        filas.append([
            act.titulo, _local(act.fecha_inicio), documento,
            tipos_doc.get(d['alumno__tipo_documento'], d['alumno__tipo_documento']),
            d['alumno__apellidos'], d['alumno__nombres'], d['alumno__correo'],
            d['escuela'] or 'Sin escuela', d['carrera'], d['jornada'],
            inscrito, estado, fecha_insc,
            SI if asis else (NO if _ya_empezo(act) else PENDIENTE),
            _local(asis['fecha_ingreso']) if asis else None,
            metodos.get(asis['metodo_ingreso'], asis['metodo_ingreso']) if asis else '',
            (asis['registrado_por__username'] or '') if asis else '',
        ])

    return Reporte(
        'participantes', 'Listado de participantes', 'Participantes',
        [('Actividad', TEXTO), ('Inicio actividad', FECHA), ('Documento', TEXTO), ('Tipo de documento', TEXTO),
         ('Apellidos', TEXTO), ('Nombres', TEXTO), ('Correo', TEXTO), ('Escuela', TEXTO), ('Carrera', TEXTO),
         ('Jornada', TEXTO), ('Inscrito', TEXTO), ('Estado inscripción', TEXTO), ('Fecha inscripción', FECHA),
         ('Asistió', TEXTO), ('Ingreso', FECHA), ('Método', TEXTO), ('Registrado por', TEXTO)],
        filas,
        [('Listado', 'Una fila por alumno y actividad: quienes se inscribieron, quienes asistieron, o ambos.'),
         ('Inscrito', '"No aplica" en actividades masivas, que no tienen inscripción.'),
         ('Asistió', '"Pendiente" si la actividad todavía no empieza.'),
         ('Datos personales', 'Contiene datos personales de alumnos: no compartir fuera de la institución.')],
    )


REPORTES = {
    'resumen': reporte_resumen,
    'participacion': reporte_participacion,
    'participantes': reporte_participantes,
}


# ============================================================
# ESCRITURA
# ============================================================

def _texto_csv(valor, tipo):
    if valor is None:
        return ''
    if tipo == FECHA:
        return valor.strftime(FORMATO_FECHA_CSV)
    if tipo == PORCENTAJE:
        return f'{valor * 100:.1f}'.replace('.', ',')
    return _sanitizar_celda(valor)


def _escribir_hoja(ws, reporte):
    ws.title = reporte.hoja[:31]
    fuente, relleno = Font(bold=True, color='FFFFFF'), PatternFill('solid', start_color=COLOR_ENCABEZADO)
    anchos = []
    for col, (titulo, _) in enumerate(reporte.columnas, start=1):
        celda = ws.cell(row=1, column=col, value=titulo)
        celda.font, celda.fill = fuente, relleno
        celda.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        anchos.append(len(titulo))

    for r, fila in enumerate(reporte.filas, start=2):
        for col, ((_, tipo), valor) in enumerate(zip(reporte.columnas, fila), start=1):
            celda = ws.cell(row=r, column=col, value=_sanitizar_celda(valor))
            if tipo == FECHA and valor is not None:
                celda.number_format = FORMATO_FECHA_EXCEL
                largo = 17
            elif tipo == PORCENTAJE and valor is not None:
                celda.number_format = '0.0%'
                largo = 7
            else:
                largo = len(str(valor)) if valor is not None else 0
            anchos[col - 1] = max(anchos[col - 1], largo)

    for col, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(col)].width = min(ancho + 2, 50)
    ws.freeze_panes = 'A2'
    # Al imprimir: horizontal, todas las columnas en el ancho de la hoja y el encabezado en cada página
    ws.page_setup.orientation = 'landscape'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '1:1'
    if reporte.filas:
        ws.auto_filter.ref = f'A1:{get_column_letter(len(reporte.columnas))}{len(reporte.filas) + 1}'


def _escribir_informacion(ws, reportes, request, f, etiquetas):
    ws.title = 'Información'
    negrita = Font(bold=True)
    filas = [
        ('Punto Participa: exportación de reportes', None),
        (None, None),
        ('Contenido', ', '.join(r.titulo for r in reportes)),
        ('Generado el', _local(timezone.now())),
        ('Generado por', request.user.get_username()),
        (None, None),
        ('Filtros aplicados', None),
    ]
    filas += [(k, v) for k, v in etiquetas] or [('(ninguno)', 'Todas las actividades visibles para tu usuario')]
    filas += [(None, None), ('Qué significa cada columna', None)]
    for r in reportes:
        filas += [(f'{r.titulo}: {col}', texto) for col, texto in r.definiciones]

    for n, (a, b) in enumerate(filas, start=1):
        celda_a = ws.cell(row=n, column=1, value=_sanitizar_celda(a))
        celda_b = ws.cell(row=n, column=2, value=_sanitizar_celda(b))
        if b is None and a:
            celda_a.font = Font(bold=True, size=12 if n == 1 else 11, color=COLOR_ENCABEZADO)
        else:
            celda_a.font = negrita
        if hasattr(b, 'year'):
            celda_b.number_format = FORMATO_FECHA_EXCEL
            celda_b.alignment = Alignment(horizontal='left')
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 90


def _etiquetas_filtros(f):
    """Filtros usados, con nombres legibles, para la hoja Información y la auditoría."""
    etiquetas = []
    if f['actividad']:
        titulo = Actividad.objects.filter(pk=f['actividad']).values_list('titulo', flat=True).first()
        etiquetas.append(('Actividad', titulo or f'#{f["actividad"]}'))
    for clave, nombre in (('escuela', 'Escuela'), ('carrera', 'Carrera'), ('jornada', 'Jornada'),
                          ('lugar', 'Lugar')):
        if f[clave]:
            etiquetas.append((nombre, f[clave]))
    if f['tipo']:
        etiquetas.append(('Tipo', dict(Actividad.TIPO_CHOICES)[f['tipo']]))
    if f['fecha_inicio']:
        etiquetas.append(('Desde', f['fecha_inicio'].strftime('%d/%m/%Y')))
    if f['fecha_fin']:
        etiquetas.append(('Hasta', f['fecha_fin'].strftime('%d/%m/%Y')))
    return etiquetas


def _nombre_archivo(clave, extension):
    return f'punto_participa_{clave}_{timezone.localtime():%Y%m%d_%H%M}.{extension}'


def _respuesta_excel(reportes, request, f, etiquetas, clave):
    wb = Workbook()
    _escribir_hoja(wb.active, reportes[0])
    for r in reportes[1:]:
        _escribir_hoja(wb.create_sheet(), r)
    _escribir_informacion(wb.create_sheet(), reportes, request, f, etiquetas)
    respuesta = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition'] = f'attachment; filename="{_nombre_archivo(clave, "xlsx")}"'
    wb.save(respuesta)
    return respuesta


def _respuesta_csv(reporte):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{_nombre_archivo(reporte.clave, "csv")}"'
    respuesta.write('﻿')  # BOM: Excel reconoce UTF-8 (tildes y ñ)
    escritor = csv.writer(respuesta, delimiter=';')
    escritor.writerow([titulo for titulo, _ in reporte.columnas])
    tipos = [tipo for _, tipo in reporte.columnas]
    for fila in reporte.filas:
        escritor.writerow([_texto_csv(v, t) for v, t in zip(fila, tipos)])
    return respuesta


# ============================================================
# VISTAS
# ============================================================

FORMATOS = {'excel': 'excel', 'xlsx': 'excel', 'csv': 'csv'}


@login_required
@role_required('Administrador', 'Creador de Evento', json_response=True)
def exportar_reporte(request, tipo, formato):
    formato = FORMATOS.get(formato)
    if formato is None or (tipo not in REPORTES and tipo != 'libro') or (tipo == 'libro' and formato == 'csv'):
        raise Http404('Exportación no disponible.')

    datos = _base(request)
    f = datos[0]
    if tipo == 'libro':
        reportes = [construir(request, datos) for construir in REPORTES.values()]
    else:
        reportes = [REPORTES[tipo](request, datos)]

    etiquetas = _etiquetas_filtros(f)
    filas = sum(len(r.filas) for r in reportes)
    nombre = 'Libro completo' if tipo == 'libro' else reportes[0].titulo
    texto_filtros = '; '.join(f'{k}: {v}' for k, v in etiquetas) or 'sin filtros'
    registrar_log(
        request, 'Reportes', 'Exportar reporte',
        f'{nombre} ({"Excel" if formato == "excel" else "CSV"}), {filas} fila{"s" if filas != 1 else ""}. '
        f'Filtros: {texto_filtros}.',
        cambios_json={'reporte': tipo, 'formato': formato, 'filas': filas, 'filtros': dict(etiquetas)},
    )

    if formato == 'csv':
        return _respuesta_csv(reportes[0])
    return _respuesta_excel(reportes, request, f, etiquetas, tipo)


# Direcciones anteriores (enlaces guardados y pruebas): siguen funcionando.
def exportar_resumen(request, formato):
    return exportar_reporte(request, 'resumen', formato)


def exportar_participacion(request, formato):
    return exportar_reporte(request, 'participacion', formato)
