"""
Inscripción pública, página pública de las masivas, cupos y estados de la actividad.

Correr solo este archivo:
    python manage.py test gestion.tests.inscripciones.tests_inscripcion_publica --noinput
"""
from datetime import timedelta

from gestion.models import Actividad, Alumno

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...models import Asistencia, Inscripcion, LogAuditoria
from ..base import BaseSistemaTestCase


def crear_actividad(tipo='MASIVA', estado='ACTIVA', dias=2):
    ahora = timezone.now()
    cupos = ({'cupos_totales': 10, 'cupos_disponibles': 10} if tipo == 'TALLER'
             else {'cupos_totales': None, 'cupos_disponibles': None})
    return Actividad.objects.create(
        titulo=f'Premiacion {tipo}', descripcion='Una ceremonia importante', tipo=tipo,
        lugar='Sede Alameda', fecha_inicio=ahora + timedelta(days=dias),
        fecha_fin=ahora + timedelta(days=dias, hours=2), estado=estado, **cupos)


class ActividadPublicaTests(TestCase):
    def _get(self, actividad):
        return self.client.get(reverse('actividad_publica', args=[actividad.pk]))

    def test_cualquiera_ve_una_masiva_sin_iniciar_sesion(self):
        actividad = crear_actividad()
        r = self._get(actividad)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Premiacion MASIVA')
        self.assertContains(r, 'Sede Alameda')
        self.assertContains(r, 'no requiere inscripción')
        self.assertEqual(r.context['estado'], 'vigente')

    def test_la_pagina_no_pide_datos_ni_permite_inscribirse(self):
        r = self._get(crear_actividad())
        self.assertNotContains(r, '<form')
        self.assertNotContains(r, 'name="rut"')

    def test_un_taller_se_redirige_a_su_inscripcion(self):
        taller = crear_actividad('TALLER')
        r = self._get(taller)
        self.assertRedirects(
            r, reverse('inscripcion_taller', args=[taller.pk]), fetch_redirect_response=False)

    def test_la_direccion_de_taller_de_una_masiva_lleva_a_su_pagina(self):
        # Alguien escribe /taller/<id>/ para una masiva: va a la página pública, no a un error
        masiva = crear_actividad()
        r = self.client.get(reverse('inscripcion_taller', args=[masiva.pk]))
        self.assertRedirects(
            r, reverse('actividad_publica', args=[masiva.pk]), fetch_redirect_response=False)

    def test_una_con_invitacion_no_tiene_pagina_publica(self):
        privada = crear_actividad('INVITACION')
        for nombre in ('inscripcion_taller', 'actividad_publica'):
            with self.subTest(pagina=nombre):
                self.assertEqual(self.client.get(reverse(nombre, args=[privada.pk])).status_code, 404)

    def test_una_actividad_inexistente_da_404_con_la_pagina_del_sistema(self):
        for url in ('/actividad/99999/', '/taller/99999/', '/no-existe/'):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 404)
                self.assertContains(r, 'Esta página no existe', status_code=404)
                self.assertContains(r, 'puntoestu@duoc.cl', status_code=404)
                self.assertNotContains(r, 'Not Found', status_code=404)

    def test_finalizada_y_cancelada_se_muestran_con_su_estado(self):
        vencida = crear_actividad(dias=-3)
        self.assertEqual(self._get(vencida).context['estado'], 'finalizada')
        cancelada = crear_actividad(estado='CANCELADA')
        self.assertEqual(self._get(cancelada).context['estado'], 'cancelada')


class CorreoVerDetallesTests(TestCase):
    def setUp(self):
        self.alumno = Alumno.objects.create(
            rut='11111111K', tipo_documento='RUT', nombres='Ana', apellidos='Uno',
            correo='ana@example.com', carrera='Informática', jornada='Diurna')

    def _html(self, actividad):
        return render_to_string('gestion/correos/invitacion.html', {
            'actividad': actividad, 'alumno': self.alumno, 'site_url': 'http://sitio.test'})

    def test_la_masiva_lleva_ver_detalles_y_ningun_enlace_de_inscripcion(self):
        actividad = crear_actividad()
        html = self._html(actividad)
        self.assertIn(f'http://sitio.test/actividad/{actividad.pk}/', html)
        self.assertIn('Ver detalles', html)
        self.assertNotIn('/taller/', html)
        self.assertNotIn('Inscribirme', html)
        self.assertIn('no requiere inscripción', html)

    def test_el_taller_no_cambia(self):
        taller = crear_actividad('TALLER')
        html = self._html(taller)
        self.assertIn(f'http://sitio.test/taller/{taller.pk}/', html)
        self.assertIn('Inscribirme', html)
        self.assertNotIn('/actividad/', html)
        self.assertNotIn('Ver detalles', html)


class EstadosYCuposTests(BaseSistemaTestCase):
    def test_no_se_puede_inscribir_en_actividad_finalizada(self):
        self.actividad.estado = "FINALIZADA"
        self.actividad.save(update_fields=["estado"])
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": self.alumno.rut, "acepta_politica": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Evento ya realizado")
        self.assertFalse(Inscripcion.objects.filter(actividad=self.actividad).exists())

    def test_taller_con_fecha_pasada_dice_evento_ya_realizado(self):
        """H002: aunque siga ACTIVA, si ya terminó muestra "Evento ya realizado"."""
        self.actividad.fecha_inicio = timezone.now() - timedelta(days=2)
        self.actividad.fecha_fin = timezone.now() - timedelta(days=1)
        self.actividad.save(update_fields=["fecha_inicio", "fecha_fin"])
        response = self.client.get(reverse("inscripcion_taller", args=[self.actividad.pk]))
        self.assertContains(response, "Evento ya realizado")
        self.assertNotContains(response, "Inscribirme")

    def test_no_se_puede_inscribir_en_actividad_cancelada(self):
        self.actividad.estado = "CANCELADA"
        self.actividad.save(update_fields=["estado"])
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Taller cancelado")
        self.assertNotContains(response, "Evento ya realizado")

    def test_no_se_puede_inscribir_sin_cupos(self):
        self.actividad.cupos_disponibles = 0
        self.actividad.save(update_fields=["cupos_disponibles"])
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin cupos disponibles")

    def test_no_se_registra_asistencia_en_actividad_inactiva(self):
        self.actividad_masiva.estado = "FINALIZADA"
        self.actividad_masiva.save(update_fields=["estado"])
        self.seleccionar_actividad()
        response = self.client.post(
            reverse("escaneo"), {"rut": self.alumno.rut}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Asistencia.objects.filter(actividad=self.actividad_masiva).exists())


class InscripcionYAsistenciaIntegralTests(BaseSistemaTestCase):
    def test_inscripcion_publica_get_muestra_taller_disponible(self):
        response = self.client.get(
            reverse("inscripcion_taller", args=[self.actividad.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.actividad.titulo)

    def test_inscripcion_publica_crea_registro_y_recalcula_cupo(self):
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "20.001.550-9", "acepta_politica": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Inscripcion.objects.filter(
                actividad=self.actividad, alumno=self.alumno
            ).count(),
            1,
        )
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.cupos_disponibles, 1)

    def test_inscripcion_publica_rechaza_duplicado(self):
        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "200015509", "acepta_politica": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya estás inscrito")

    def test_inscripcion_publica_rechaza_alumno_inexistente(self):
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "99999999-9", "acepta_politica": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No estás registrado")

    def test_escaneo_confirma_y_registra_asistencia(self):
        self.seleccionar_actividad()

        url = reverse("escaneo")
        primera = self.client.post(url, {"rut": "200015509"})
        self.assertEqual(primera.status_code, 200)
        self.assertEqual(primera.json()["confirmar"], True)

        segunda = self.client.post(
            url, {"rut": "200015509", "confirmar": "true"}
        )
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()["success"])
        self.assertEqual(
            Asistencia.objects.filter(
                actividad=self.actividad_masiva, alumno=self.alumno
            ).count(),
            1,
        )
        self.assertTrue(
            LogAuditoria.objects.filter(accion="Registro de asistencia").exists()
        )

    def test_escaneo_rechaza_asistencia_duplicada(self):
        Asistencia.objects.create(
            actividad=self.actividad_masiva,
            alumno=self.alumno,
            metodo_ingreso="RUT",
            registrado_por=self.registrador,
        )
        self.seleccionar_actividad()

        response = self.client.post(
            reverse("escaneo"), {"rut": "200015509"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("ya fue registrada", response.json()["message"])

    def test_escaneo_rechaza_taller_sin_inscripcion(self):
        self.seleccionar_actividad(self.actividad)

        response = self.client.post(
            reverse("escaneo"), {"rut": "200015509"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("no está inscrito", response.json()["message"])
