"""
Pruebas del importador de alumnos (gestion/importador_alumnos.py y el comando
importar_alumnos): crear, actualizar campo por campo, bloquear ausentes sin
borrar datos, reactivar, filas con error, resguardo de bloqueo masivo y
validación del archivo.
"""
import io
import os
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from gestion.importador_alumnos import (
    ArchivoInvalido, Resultado, analizar, aplicar, bloqueo_masivo, leer_filas,
)
from gestion.management.commands.seed_data import calcular_dv
from gestion.models import (
    Actividad, Alumno, Asistencia, Carrera, Inscripcion, Jornada, LogAuditoria,
)
from gestion.utils import buscar_alumno_por_documento

COLS = ['rut', 'tipo_documento', 'nombres', 'apellidos', 'correo', 'carrera', 'jornada']


def rut_valido(cuerpo):
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


def doc_norm(cuerpo):
    return f'{cuerpo}{calcular_dv(cuerpo)}'


class ImportadorBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(nombre='Ingeniería en Informática', escuela='Informática')
        Jornada.objects.create(nombre='Diurna')
        Jornada.objects.create(nombre='Vespertina')

    def fila(self, cuerpo=20000001, **kw):
        d = dict(rut=rut_valido(cuerpo), tipo_documento='', nombres='Ana', apellidos='Pérez',
                 correo=f'a{cuerpo}@example.com', carrera='Ingeniería en Informática',
                 jornada='Diurna')
        d.update(kw)
        return d

    def leer(self, filas, nombre='n.csv'):
        texto = ';'.join(COLS) + '\n' + '\n'.join(
            ';'.join(f.get(c, '') for c in COLS) for f in filas)
        return leer_filas(io.BytesIO(texto.encode('utf-8')), nombre)

    def analizar(self, filas):
        return analizar(self.leer(filas))

    def crear_alumno(self, cuerpo=20000001, **kw):
        datos = dict(rut=doc_norm(cuerpo), tipo_documento='RUT', nombres='Ana', apellidos='Pérez',
                     correo=f'a{cuerpo}@example.com', carrera='Ingeniería en Informática',
                     jornada='Diurna')
        datos.update(kw)
        return Alumno.objects.create(**datos)


class AltasYCambiosTests(ImportadorBase):
    def test_crea_alumno_nuevo_con_documento_normalizado(self):
        res = self.analizar([self.fila(20000001)])
        self.assertEqual(len(res.nuevos), 1)
        creados, actualizados, bloqueados = aplicar(res)
        self.assertEqual((creados, actualizados, bloqueados), (1, 0, 0))
        a = Alumno.objects.get(rut=doc_norm(20000001))
        self.assertTrue(a.activo)
        self.assertEqual(a.tipo_documento, 'RUT')
        self.assertEqual(a.apellidos, 'Pérez')

    def test_actualiza_solo_el_campo_que_cambio(self):
        self.crear_alumno(20000001, correo='viejo@example.com')
        res = self.analizar([self.fila(20000001, correo='nuevo@example.com')])
        self.assertEqual(len(res.actualizados), 1)
        _, _, cambios = res.actualizados[0]
        self.assertEqual(cambios, [('correo', 'viejo@example.com', 'nuevo@example.com')])
        aplicar(res)
        a = Alumno.objects.get(rut=doc_norm(20000001))
        self.assertEqual(a.correo, 'nuevo@example.com')
        self.assertEqual(a.nombres, 'Ana')

    def test_actualiza_varios_campos(self):
        self.crear_alumno(20000001)
        res = self.analizar([self.fila(20000001, nombres='María', jornada='Vespertina')])
        campos = {c for c, _, _ in res.actualizados[0][2]}
        self.assertEqual(campos, {'nombres', 'jornada'})

    def test_sin_cambios_no_se_reporta_como_actualizado(self):
        self.crear_alumno(20000001)
        res = self.analizar([self.fila(20000001)])
        self.assertEqual(res.sin_cambios, 1)
        self.assertEqual(res.actualizados, [])
        self.assertEqual(res.nuevos, [])

    def test_carrera_y_jornada_no_distinguen_mayusculas(self):
        res = self.analizar([self.fila(carrera='INGENIERÍA EN INFORMÁTICA', jornada='diurna')])
        self.assertEqual(res.errores, [])
        datos = res.nuevos[0][1]
        self.assertEqual(datos['carrera'], 'Ingeniería en Informática')
        self.assertEqual(datos['jornada'], 'Diurna')

    def test_acepta_documento_con_puntos_guion_y_minusculas(self):
        self.crear_alumno(20000001)
        con_formato = f'20.000.001-{calcular_dv(20000001)}'
        res = self.analizar([self.fila(rut=con_formato)])
        self.assertEqual(res.sin_cambios, 1)


class BloqueoTests(ImportadorBase):
    def test_bloquea_ausentes_sin_borrar_nada(self):
        presente = self.crear_alumno(20000001)
        ausente = self.crear_alumno(20000002)
        user = User.objects.create_user('u', password='x')
        ahora = timezone.now()
        act = Actividad.objects.create(
            titulo='Charla', descripcion='d', tipo='MASIVA', lugar='L',
            fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=1), creado_por=user)
        Asistencia.objects.create(actividad=act, alumno=ausente, metodo_ingreso='RUT')
        Inscripcion.objects.create(actividad=act, alumno=ausente)

        res = self.analizar([self.fila(20000001)])
        self.assertEqual([d for d, _ in res.bloqueados], [ausente.rut])
        creados, actualizados, bloqueados = aplicar(res)
        self.assertEqual(bloqueados, 1)

        ausente.refresh_from_db()
        presente.refresh_from_db()
        self.assertFalse(ausente.activo)
        self.assertTrue(presente.activo)
        self.assertEqual(Alumno.objects.count(), 2)                       # nada se borra
        self.assertEqual(Asistencia.objects.filter(alumno=ausente).count(), 1)
        self.assertEqual(Inscripcion.objects.filter(alumno=ausente).count(), 1)

    def test_bloqueado_vuelve_al_archivo_y_se_reactiva(self):
        a = self.crear_alumno(20000001, activo=False)
        res = self.analizar([self.fila(20000001)])
        self.assertEqual(len(res.actualizados), 1)
        self.assertIn(('activo', False, True), res.actualizados[0][2])
        aplicar(res)
        a.refresh_from_db()
        self.assertTrue(a.activo)

    def test_alumno_ya_bloqueado_ausente_no_se_vuelve_a_bloquear(self):
        self.crear_alumno(20000001)
        self.crear_alumno(20000002, activo=False)
        res = self.analizar([self.fila(20000001)])
        self.assertEqual(res.bloqueados, [])

    def test_fila_con_error_no_bloquea_al_alumno(self):
        c = self.crear_alumno(20000003)
        res = self.analizar([self.fila(20000003, correo='no-es-correo')])
        self.assertEqual(len(res.errores), 1)
        self.assertEqual(res.bloqueados, [])
        aplicar(res)
        c.refresh_from_db()
        self.assertTrue(c.activo)

    def test_alumno_sin_documento_no_se_bloquea(self):
        sin_doc = Alumno.objects.create(
            rut=None, tipo_documento='RUT', nombres='S', apellidos='D',
            correo='s@example.com', carrera='Ingeniería en Informática', jornada='Diurna')
        self.crear_alumno(20000001)
        res = self.analizar([self.fila(20000001)])
        self.assertEqual(res.bloqueados, [])
        sin_doc.refresh_from_db()
        self.assertTrue(sin_doc.activo)

    def test_bloqueado_no_se_encuentra_por_documento(self):
        a = self.crear_alumno(20000001)
        self.assertEqual(buscar_alumno_por_documento(a.rut), a)
        Alumno.objects.filter(pk=a.pk).update(activo=False)
        self.assertIsNone(buscar_alumno_por_documento(a.rut))
        Alumno.objects.filter(pk=a.pk).update(activo=True)
        self.assertEqual(buscar_alumno_por_documento(a.rut), a)

    def test_resguardo_de_bloqueo_masivo(self):
        for i in range(10):
            self.crear_alumno(20000001 + i)
        res_uno = self.analizar([self.fila(20000001)])           # bloquearía 9 de 10
        self.assertTrue(bloqueo_masivo(res_uno))
        nueve = [self.fila(20000001 + i) for i in range(9)]
        res_nueve = self.analizar(nueve)                           # bloquearía 1 de 10
        self.assertFalse(bloqueo_masivo(res_nueve))

    def test_aplicar_es_todo_o_nada(self):
        datos = dict(rut=doc_norm(20000009), tipo_documento='RUT', nombres='A', apellidos='B',
                     correo='a@example.com', carrera='Ingeniería en Informática',
                     jornada='Diurna', activo=True)
        res = Resultado(nuevos=[(2, dict(datos)), (3, dict(datos))])   # mismo documento dos veces
        with self.assertRaises(IntegrityError):
            aplicar(res)
        self.assertEqual(Alumno.objects.count(), 0)


class ValidacionPorFilaTests(ImportadorBase):
    def test_errores_por_fila_y_nada_se_escribe(self):
        malo_dv = f'20000009-{"0" if calcular_dv(20000009) != "0" else "1"}'
        filas = [
            self.fila(20000001, correo='no-es-correo'),                 # fila 2
            self.fila(20000002, carrera='Carrera Inexistente'),         # fila 3
            self.fila(20000003, jornada='Nocturna'),                    # fila 4
            self.fila(20000004, tipo_documento='LICENCIA'),             # fila 5
            self.fila(rut=malo_dv, tipo_documento='RUT'),               # fila 6
            self.fila(20000006, rut=''),                                # fila 7
            self.fila(20000007, nombres=''),                            # fila 8
            self.fila(20000008),                                        # fila 9 (valida)
            self.fila(20000008),                                        # fila 10 (repetida)
        ]
        res = self.analizar(filas)
        err = dict(res.errores)
        self.assertIn('Correo no válido', err[2])
        self.assertIn('Carrera desconocida', err[3])
        self.assertIn('Jornada desconocida', err[4])
        self.assertIn('Tipo de documento desconocido', err[5])
        self.assertIn('no válido', err[6])
        self.assertIn('Falta el documento', err[7])
        self.assertIn('Falta el nombre', err[8])
        self.assertIn('repetido', err[10])
        self.assertEqual(len(res.nuevos), 1)                           # solo la fila 9
        aplicar(res)
        self.assertEqual(Alumno.objects.count(), 1)

    def test_infiere_tipo_de_documento_y_avisa(self):
        res = self.analizar([
            self.fila(20000001),                                        # RUT válido
            self.fila(rut='AB123456'),                                  # pasaporte
        ])
        tipos = {d['rut']: d['tipo_documento'] for _, d in res.nuevos}
        self.assertEqual(tipos[doc_norm(20000001)], 'RUT')
        self.assertEqual(tipos['AB123456'], 'PASAPORTE')
        self.assertEqual(len(res.avisos), 2)

    def test_fila_rechazada_no_genera_avisos(self):
        res = self.analizar([self.fila(20000001, correo='mal')])
        self.assertEqual(len(res.errores), 1)
        self.assertEqual(res.avisos, [])

    def test_rut_con_dv_incorrecto_declarado_como_provisorio_es_valido(self):
        malo_dv = f'20000009-{"0" if calcular_dv(20000009) != "0" else "1"}'
        res = self.analizar([self.fila(rut=malo_dv, tipo_documento='RUN provisorio')])
        self.assertEqual(res.errores, [])
        self.assertEqual(res.nuevos[0][1]['tipo_documento'], 'RUN_PROVISORIO')


class LecturaDeArchivoTests(ImportadorBase):
    def test_extension_no_permitida(self):
        with self.assertRaises(ArchivoInvalido):
            leer_filas(io.BytesIO(b'x'), 'datos.txt')

    def test_xlsx_con_contenido_falso(self):
        with self.assertRaises(ArchivoInvalido):
            leer_filas(io.BytesIO(b'hola'), 'datos.xlsx')
        with self.assertRaises(ArchivoInvalido):
            leer_filas(io.BytesIO(b'PK\x03\x04basura'), 'datos.xlsx')

    def test_csv_con_bytes_nulos(self):
        with self.assertRaises(ArchivoInvalido):
            leer_filas(io.BytesIO(b'rut;nombres\x00\n1;2'), 'datos.csv')

    def test_archivo_vacio(self):
        with self.assertRaises(ArchivoInvalido):
            leer_filas(io.BytesIO(b''), 'datos.csv')

    def test_faltan_columnas(self):
        with self.assertRaises(ArchivoInvalido) as ctx:
            leer_filas(io.BytesIO(b'rut;nombres\n1;2'), 'datos.csv')
        self.assertIn('Faltan columnas', str(ctx.exception))

    def test_limite_de_tamano_y_de_filas(self):
        texto = (';'.join(COLS) + '\n' + ';'.join(['x'] * 7) + '\n').encode()
        with mock.patch('gestion.importador_alumnos.MAX_BYTES', 10):
            with self.assertRaises(ArchivoInvalido):
                leer_filas(io.BytesIO(texto), 'datos.csv')
        texto3 = (';'.join(COLS) + '\n' + (';'.join(['x'] * 7) + '\n') * 3).encode()
        with mock.patch('gestion.importador_alumnos.MAX_FILAS', 2):
            with self.assertRaises(ArchivoInvalido):
                leer_filas(io.BytesIO(texto3), 'datos.csv')

    def test_alias_de_encabezados_y_bom(self):
        texto = ('\ufeffRUN;Nombre;Apellido;Email;Carrera;Jornada\n'
                 f'{rut_valido(20000001)};Ana;Pérez;a@example.com;'
                 'Ingeniería en Informática;Diurna\n').encode('utf-8')
        res = analizar(leer_filas(io.BytesIO(texto), 'datos.csv'))
        self.assertEqual(res.errores, [])
        self.assertEqual(len(res.nuevos), 1)

    def test_csv_separado_por_comas_y_latin1(self):
        texto = (','.join(COLS) + '\n'
                 f'{rut_valido(20000001)},,Ana,Muñoz,a@example.com,'
                 'Ingeniería en Informática,Diurna\n').encode('latin-1')
        res = analizar(leer_filas(io.BytesIO(texto), 'datos.csv'))
        self.assertEqual(res.errores, [])
        self.assertEqual(res.nuevos[0][1]['apellidos'], 'Muñoz')

    def test_lee_xlsx_con_documento_numerico(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(COLS)
        ws.append([987654321, 'RUN provisorio', 'Luis', 'Soto', 'l@example.com',
                   'Ingeniería en Informática', 'Vespertina'])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        res = analizar(leer_filas(buf, 'nomina.xlsx'))
        self.assertEqual(res.errores, [])
        self.assertEqual(res.nuevos[0][1]['rut'], '987654321')
        self.assertEqual(res.nuevos[0][1]['tipo_documento'], 'RUN_PROVISORIO')


class ComandoImportarAlumnosTests(ImportadorBase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def archivo(self, filas):
        ruta = os.path.join(self.dir.name, 'nomina.csv')
        with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(';'.join(COLS) + '\n')
            for fila in filas:
                f.write(';'.join(fila.get(c, '') for c in COLS) + '\n')
        return ruta

    def correr(self, ruta, *args):
        out = io.StringIO()
        call_command('importar_alumnos', ruta, *args, stdout=out)
        return out.getvalue()

    def test_simular_no_guarda_nada(self):
        self.crear_alumno(20000001)
        ruta = self.archivo([self.fila(20000001, correo='otro@example.com'),
                             self.fila(20000002)])
        salida = self.correr(ruta, '--simular')
        self.assertIn('Simulacion', salida)
        self.assertEqual(Alumno.objects.count(), 1)
        self.assertEqual(Alumno.objects.get().correo, 'a20000001@example.com')
        self.assertEqual(LogAuditoria.objects.count(), 0)

    def test_importacion_real_guarda_y_audita(self):
        self.crear_alumno(20000001)
        ruta = self.archivo([self.fila(20000001, correo='otro@example.com'),
                             self.fila(20000002)])
        self.correr(ruta)
        self.assertEqual(Alumno.objects.count(), 2)
        self.assertEqual(Alumno.objects.get(rut=doc_norm(20000001)).correo, 'otro@example.com')
        log = LogAuditoria.objects.get(accion='Importacion de alumnos')
        self.assertIn('1 creados', log.detalle)
        self.assertIn('1 actualizados', log.detalle)

    def test_bloqueo_masivo_se_rechaza_sin_confirmacion(self):
        for i in range(10):
            self.crear_alumno(20000001 + i)
        ruta = self.archivo([self.fila(20000001)])
        with self.assertRaises(CommandError):
            self.correr(ruta)
        self.assertEqual(Alumno.objects.filter(activo=True).count(), 10)
        self.assertEqual(LogAuditoria.objects.count(), 0)

    def test_bloqueo_masivo_con_confirmacion_explicita(self):
        for i in range(10):
            self.crear_alumno(20000001 + i)
        ruta = self.archivo([self.fila(20000001)])
        self.correr(ruta, '--confirmar-bloqueo-masivo')
        self.assertEqual(Alumno.objects.filter(activo=True).count(), 1)
        self.assertEqual(Alumno.objects.count(), 10)                   # nada se borró

    def test_archivo_inexistente(self):
        with self.assertRaises(CommandError):
            self.correr(os.path.join(self.dir.name, 'no_existe.csv'))
