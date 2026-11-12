"""
Actividades con invitación, paso 1: tipo nuevo, carga de la lista de invitados y pantalla
de invitados.

- La lista (rut, nombre, carrera, correo; jornada opcional) se sube al crear la actividad
  o después. Los datos de la lista mandan; si el alumno está en la nómina se enlaza.
- Errores por fila no detienen el resto; avisos si no coincide con la nómina o el catálogo.
- Estas actividades no usan carreras ni jornadas, no tienen página pública, no se pueden
  invitar "por carrera" (le escribiría a toda la nómina) y en el escáner solo entra la lista.
"""
import json
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ActividadForm
from .invitados import analizar, aplicar, leer
from .management.commands.seed_data import calcular_dv
from .models import Actividad, Alumno, Asistencia, Invitado, LogAuditoria, NotificacionCorreo
from .tests_integrales import BaseSistemaTestCase


def rut(cuerpo):
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


def csv_archivo(filas, nombre='invitados.csv', encabezado='rut;nombre;carrera;correo'):
    texto = encabezado + '\n' + '\n'.join(';'.join(f) for f in filas) + '\n'
    return SimpleUploadedFile(nombre, texto.encode('utf-8'), content_type='text/csv')


class BaseInvitadosTests(BaseSistemaTestCase):
    def datos_formulario(self, **cambios):
        futuro = timezone.localtime(timezone.now() + timedelta(days=5))
        datos = {
            'titulo': 'Ceremonia de premiación', 'descripcion': 'Solo invitados', 'tipo': 'INVITACION',
            'lugar': 'Auditorio', 'acompanantes_por_invitado': '2',
            'fecha_inicio_fecha': futuro.strftime('%Y-%m-%d'), 'fecha_inicio_hora': futuro.strftime('%H:%M'),
            'fecha_fin_fecha': (futuro + timedelta(hours=2)).strftime('%Y-%m-%d'),
            'fecha_fin_hora': (futuro + timedelta(hours=2)).strftime('%H:%M'),
        }
        datos.update(cambios)
        return datos

    def lista_basica(self):
        return csv_archivo([
            ['20.001.550-9', 'Juan Pérez', 'Ingeniería en Informática', 'juan@duocuc.cl'],
            [rut(17000001), 'Externa Nómina', 'Diseño Gráfico', 'otra@duocuc.cl'],
        ])

    def crear_por_formulario(self, archivo=None, **cambios):
        self.login_as(self.creador)
        datos = self.datos_formulario(**cambios)
        if archivo is not None:
            datos['lista_invitados'] = archivo
        return self.client.post(reverse('crear_actividad'), datos, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def actividad_invitacion(self, **campos):
        ahora = timezone.now()
        datos = dict(titulo='Cena de egresados', descripcion='x', tipo='INVITACION', lugar='Auditorio',
                     fecha_inicio=ahora + timedelta(days=2), fecha_fin=ahora + timedelta(days=2, hours=3),
                     creado_por=self.creador, acompanantes_por_invitado=1)
        datos.update(campos)
        return Actividad.objects.create(**datos)


class FormularioTests(BaseInvitadosTests):
    def test_crear_con_lista_carga_invitados_y_lleva_a_la_lista(self):
        resp = self.crear_por_formulario(self.lista_basica())
        data = resp.json()
        self.assertTrue(data['success'], data)
        act = Actividad.objects.get(titulo='Ceremonia de premiación')
        self.assertEqual(data['redirect_url'], reverse('invitados_actividad', args=[act.pk]))
        self.assertEqual((act.tipo, act.acompanantes_por_invitado, act.cupos_totales), ('INVITACION', 2, None))
        self.assertEqual(act.invitados.count(), 2)
        self.assertEqual(act.carreras.count(), 0)
        log = LogAuditoria.objects.get(accion='Cargar lista de invitados')
        self.assertEqual(log.cambios_json['nuevos'], 2)
        # La pantalla muestra el resultado una sola vez
        pantalla = self.client.get(data['redirect_url'])
        self.assertContains(pantalla, '2 agregados')
        self.assertNotContains(self.client.get(data['redirect_url']), 'LISTA CARGADA')

    def test_al_crear_la_lista_es_obligatoria(self):
        form = ActividadForm(data=self.datos_formulario())
        self.assertFalse(form.is_valid())
        self.assertIn('lista_invitados', form.errors)

    def test_no_pide_carreras_ni_jornadas_pero_las_otras_si(self):
        form = ActividadForm(data=self.datos_formulario(), files={'lista_invitados': self.lista_basica()})
        self.assertTrue(form.is_valid(), form.errors)
        masiva = ActividadForm(data=self.datos_formulario(tipo='MASIVA'))
        self.assertFalse(masiva.is_valid())
        self.assertIn('carreras', masiva.errors)
        self.assertIn('jornadas', masiva.errors)

    def test_archivo_sin_columnas_dice_cuales_faltan(self):
        malo = csv_archivo([['1', 'x']], encabezado='rut;correo')
        form = ActividadForm(data=self.datos_formulario(), files={'lista_invitados': malo})
        self.assertFalse(form.is_valid())
        self.assertIn('Faltan columnas: nombre, carrera', form.errors['lista_invitados'][0])

    def test_maximo_de_acompanantes(self):
        form = ActividadForm(data=self.datos_formulario(acompanantes_por_invitado='11'),
                             files={'lista_invitados': self.lista_basica()})
        self.assertIn('acompanantes_por_invitado', form.errors)

    def test_en_otros_tipos_los_acompanantes_quedan_en_cero(self):
        form = ActividadForm(data=self.datos_formulario(tipo='TALLER', cupos_totales='10',
                                                        carreras=[self.carrera.pk], jornadas=[self.jornada.pk]))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['acompanantes_por_invitado'], 0)

    def test_no_cambia_de_tipo_si_ya_tiene_invitados_o_inscripciones(self):
        act = self.actividad_invitacion()
        Invitado.objects.create(actividad=act, rut='200015509', nombre='Juan', correo='j@x.cl')
        form = ActividadForm(data=self.datos_formulario(tipo='MASIVA', carreras=[self.carrera.pk],
                                                        jornadas=[self.jornada.pk]), instance=act)
        self.assertIn('tipo', form.errors)
        Asistencia.objects.create(actividad=self.actividad_masiva, alumno=self.alumno, metodo_ingreso='RUT')
        form = ActividadForm(data=self.datos_formulario(), instance=self.actividad_masiva,
                             files={'lista_invitados': self.lista_basica()})
        self.assertIn('tipo', form.errors)

    def test_editar_sin_lista_conserva_invitados(self):
        act = self.actividad_invitacion()
        Invitado.objects.create(actividad=act, rut='200015509', nombre='Juan', correo='j@x.cl')
        self.login_as(self.creador)
        datos = self.datos_formulario(titulo='Cena renombrada', acompanantes_por_invitado='3')
        resp = self.client.post(reverse('editar_actividad', args=[act.pk]), datos,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.json()['redirect_url'], reverse('invitados_actividad', args=[act.pk]))
        act.refresh_from_db()
        self.assertEqual((act.titulo, act.acompanantes_por_invitado, act.invitados.count()),
                         ('Cena renombrada', 3, 1))


class AnalisisListaTests(BaseInvitadosTests):
    def _analizar(self, filas, actividad=None, encabezado='rut;nombre;carrera;correo'):
        return analizar(leer(csv_archivo(filas, encabezado=encabezado), 'x.csv'),
                        actividad or self.actividad_invitacion())

    def test_alumno_de_la_nomina_se_enlaza_con_los_datos_de_la_lista(self):
        res = self._analizar([['200015509', 'Juan Pérez', 'Ingeniería en Informática', 'juan.otro@gmail.com']])
        self.assertEqual(res.errores, [])
        datos = res.nuevos[0][1]
        self.assertEqual(datos['alumno_id'], self.alumno.pk)
        self.assertEqual(datos['correo'], 'juan.otro@gmail.com')        # manda la lista
        self.assertEqual(datos['escuela'], 'Escuela de Informática y Telecomunicaciones')
        self.assertEqual(datos['jornada'], 'Diurno')                     # de la nómina, si la lista no la trae
        self.assertEqual(res.avisos, [])

    def test_avisa_si_no_coincide_con_la_nomina_o_el_catalogo(self):
        res = self._analizar([['200015509', 'Juanito P.', 'Carrera Nueva', 'j@x.cl']])
        avisos = ' '.join(m for _, m in res.avisos)
        self.assertIn('En la nómina se llama "Juan Pérez"', avisos)
        self.assertIn('En la nómina su carrera es "Ingeniería en Informática"', avisos)
        self.assertIn('no está en el catálogo', avisos)
        self.assertEqual(len(res.nuevos), 1)

    def test_fuera_de_la_nomina_se_carga_con_aviso(self):
        res = self._analizar([[rut(17000001), 'Nuevo Alumno', 'Diseño Gráfico', 'n@x.cl']])
        self.assertIsNone(res.nuevos[0][1]['alumno_id'])
        self.assertIn('No está en la nómina', res.avisos[0][1])

    def test_errores_por_fila_no_detienen_el_resto(self):
        Alumno.objects.filter(pk=self.alumno_pasaporte.pk).update(activo=False)
        res = self._analizar([
            ['11111111-2', 'RUT malo', 'Diseño Gráfico', 'a@x.cl'],
            [rut(17000002), 'Correo malo', 'Diseño Gráfico', 'no-es-correo'],
            [rut(17000003), '', 'Diseño Gráfico', 'b@x.cl'],
            [rut(17000004), 'Sin carrera', '', 'c@x.cl'],
            ['AB123456', 'Ana Gómez', 'Diseño Gráfico', 'ana@x.cl'],
            [rut(17000005), 'Válido', 'Diseño Gráfico', 'd@x.cl'],
            [rut(17000005), 'Repetido', 'Diseño Gráfico', 'e@x.cl'],
        ])
        mensajes = {fila: m for fila, m in res.errores}
        self.assertIn('RUT o documento no válido', mensajes[2])
        self.assertIn('Correo no válido', mensajes[3])
        self.assertIn('Falta el nombre', mensajes[4])
        self.assertIn('Falta la carrera', mensajes[5])
        self.assertIn('bloqueado en la nómina', mensajes[6])
        self.assertIn('repetido en el archivo (ver fila 7)', mensajes[8])
        self.assertEqual([d['nombre'] for _, d in res.nuevos], ['Válido'])

    def test_acepta_run_provisorio_y_pasaporte(self):
        res = self._analizar([['100.123.456-1', 'Run Provisorio', 'Diseño Gráfico', 'r@x.cl'],
                              ['XK9988776', 'Con Pasaporte', 'Diseño Gráfico', 'p@x.cl']])
        self.assertEqual(res.errores, [])
        self.assertEqual(len(res.nuevos), 2)

    def test_junta_nombre_y_apellidos_y_acepta_alias(self):
        res = self._analizar([[rut(17000006), 'María José', 'Soto Díaz', 'Diseño Gráfico', 'm@x.cl', 'Vespertino']],
                             encabezado='RUN;Nombres;Apellidos;Carrera;Email;Jornada')
        self.assertEqual(res.errores, [])
        self.assertEqual(res.nuevos[0][1]['nombre'], 'María José Soto Díaz')
        self.assertEqual(res.nuevos[0][1]['jornada'], 'Vespertino')

    def test_recargar_actualiza_datos_sin_tocar_respuestas(self):
        act = self.actividad_invitacion()
        aplicar(self._analizar([[rut(17000007), 'Primera', 'Diseño Gráfico', 'p@x.cl']], act), act)
        Invitado.objects.filter(actividad=act).update(estado='CONFIRMADO')
        res = self._analizar([[rut(17000007), 'Primera Corregida', 'Diseño Gráfico', 'p@x.cl'],
                              [rut(17000008), 'Segunda', 'Diseño Gráfico', 's@x.cl']], act)
        self.assertEqual((len(res.nuevos), len(res.actualizados)), (1, 1))
        aplicar(res, act)
        primera = act.invitados.get(rut=rut(17000007).replace('-', ''))
        self.assertEqual((primera.nombre, primera.estado), ('Primera Corregida', 'CONFIRMADO'))
        self.assertEqual(act.invitados.count(), 2)
        self.assertEqual(self._analizar([[rut(17000008), 'Segunda', 'Diseño Gráfico', 's@x.cl']], act).sin_cambios, 1)

    def test_cada_invitado_tiene_un_enlace_unico(self):
        act = self.actividad_invitacion()
        a = Invitado.objects.create(actividad=act, rut='200015509', nombre='A', correo='a@x.cl')
        b = Invitado.objects.create(actividad=act, rut='AB123456', nombre='B', correo='b@x.cl')
        self.assertNotEqual(a.token, b.token)
        self.assertGreaterEqual(len(a.token), 30)


class PantallaInvitadosTests(BaseInvitadosTests):
    def setUp(self):
        self.act = self.actividad_invitacion()
        self.url = reverse('invitados_actividad', args=[self.act.pk])

    def test_cargar_mas_desde_la_pantalla(self):
        self.login_as(self.creador)
        resp = self.client.post(self.url, {'archivo': self.lista_basica()}, follow=True)
        self.assertContains(resp, '2 agregados')
        self.assertContains(resp, 'Fuera de la nómina')
        self.assertContains(resp, 'Juan Pérez')

    def test_archivo_ilegible_avisa(self):
        self.login_as(self.creador)
        malo = SimpleUploadedFile('lista.pdf', b'%PDF', content_type='application/pdf')
        resp = self.client.post(self.url, {'archivo': malo}, follow=True)
        self.assertContains(resp, 'No se pudo leer la lista')

    def test_permisos(self):
        for usuario in (self.otro_creador, self.registrador):
            with self.subTest(usuario=usuario.username):
                self.login_as(usuario)
                self.assertEqual(self.client.get(self.url).status_code, 302)
        self.login_as(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_actividad_que_no_es_con_invitacion_vuelve_al_detalle(self):
        self.login_as(self.admin)
        resp = self.client.get(reverse('invitados_actividad', args=[self.actividad.pk]))
        self.assertRedirects(resp, reverse('actividad_detalle', args=[self.actividad.pk]))

    def test_quitar_invitado_y_no_si_ya_entro(self):
        self.login_as(self.creador)
        inv = Invitado.objects.create(actividad=self.act, rut='200015509', nombre='Juan', correo='j@x.cl')
        entro = Invitado.objects.create(actividad=self.act, rut='AB123456', nombre='Ana', correo='a@x.cl',
                                        ingreso=timezone.now())
        self.client.post(reverse('quitar_invitado', args=[self.act.pk, inv.pk]))
        self.client.post(reverse('quitar_invitado', args=[self.act.pk, entro.pk]))
        self.assertEqual(list(self.act.invitados.values_list('nombre', flat=True)), ['Ana'])
        self.assertTrue(LogAuditoria.objects.filter(accion='Quitar invitado').exists())

    def test_detalle_muestra_boton_invitados(self):
        self.login_as(self.creador)
        resp = self.client.get(reverse('actividad_detalle', args=[self.act.pk]))
        self.assertContains(resp, self.url)
        self.assertContains(resp, 'Con invitación')

    def test_plantilla(self):
        self.login_as(self.creador)
        resp = self.client.get(reverse('plantilla_invitados'))
        self.assertEqual(resp.content.decode('utf-8-sig').splitlines()[0], 'rut;nombre;apellidos;carrera;jornada;correo')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SeguridadTests(BaseInvitadosTests):
    def setUp(self):
        self.act = self.actividad_invitacion()

    def test_no_se_puede_invitar_por_carrera(self):
        """Sin carreras, el envío por carrera le habría escrito a toda la nómina."""
        self.login_as(self.creador)
        resp = self.client.post(reverse('enviar_invitaciones'), {'actividad_id': self.act.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(NotificacionCorreo.objects.filter(actividad=self.act).exists())
        prev = self.client.get(reverse('previsualizar_invitacion', args=[self.act.pk]))
        self.assertEqual(prev.status_code, 400)

    def test_no_tiene_pagina_publica_ni_inscripcion(self):
        self.assertEqual(self.client.get(reverse('actividad_publica', args=[self.act.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('inscripcion_taller', args=[self.act.pk])).status_code, 404)

    def test_escaner_no_deja_entrar_directo_a_quien_no_esta_en_la_lista(self):
        self.seleccionar_actividad(self.act)
        resp = self.client.post(reverse('escaneo'), {'rut': '200015509', 'confirmar': 'true'})
        datos = resp.json()
        self.assertFalse(datos['success'])
        self.assertEqual(datos['agregar'], 'alumno')          # se ofrece agregarlo, no entra solo
        self.assertIn('no está en la lista de invitados', datos['message'])
        self.assertFalse(Asistencia.objects.filter(actividad=self.act).exists())
        Invitado.objects.create(actividad=self.act, rut='200015509', nombre='Juan', correo='j@x.cl')
        resp = self.client.post(reverse('escaneo'), {'rut': '200015509'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['confirmar'])

    def test_etiqueta_del_tipo_en_listados(self):
        self.login_as(self.admin)
        for url in (reverse('lista_actividades'), reverse('reportes')):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'Con invitación')
