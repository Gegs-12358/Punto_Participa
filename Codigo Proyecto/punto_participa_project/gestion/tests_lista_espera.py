"""
Lista de espera de talleres llenos: anotación desde la página del taller, aviso por correo a todos cuando se
libera un cupo por una cancelación, salida de la lista al inscribirse y panel en Participantes.
"""
from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from .cancelaciones import cancelar
from .lista_espera import avisar
from .models import Alumno, Inscripcion, ListaEspera, LogAuditoria
from .tests_integrales import BaseSistemaTestCase


class BaseListaEspera(BaseSistemaTestCase):
    def setUp(self):
        # Taller de 1 cupo, ocupado por Ana
        self.actividad.cupos_totales = 1
        self.actividad.cupos_disponibles = 1
        self.actividad.save(update_fields=['cupos_totales', 'cupos_disponibles'])
        self.post_inscripcion(self.alumno_pasaporte)
        self.ocupada = Inscripcion.objects.get(actividad=self.actividad, alumno=self.alumno_pasaporte)
        mail.outbox.clear()

    def url(self):
        return reverse('inscripcion_taller', args=[self.actividad.pk])

    def post_inscripcion(self, alumno):
        return self.client.post(self.url(), {'rut': alumno.rut, 'acepta_politica': 'on'})

    def anotar(self, alumno, **extra):
        datos = {'rut': alumno.rut, 'acepta_politica': 'on', 'accion': 'lista_espera'}
        datos.update(extra)
        return self.client.post(self.url(), datos)


class AnotacionTests(BaseListaEspera):
    def test_taller_lleno_ofrece_la_lista(self):
        respuesta = self.client.get(self.url())
        self.assertContains(respuesta, 'Sin cupos disponibles')
        self.assertContains(respuesta, 'Anotarme en la lista de espera')
        self.assertContains(respuesta, 'Anotarte no te inscribe')

    def test_anotarse(self):
        respuesta = self.anotar(self.alumno)
        self.assertContains(respuesta, 'Quedaste en la lista de espera (todavía no estás inscrito)')
        self.assertTrue(ListaEspera.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())
        self.assertNotContains(respuesta, self.alumno.correo)
        self.assertTrue(LogAuditoria.objects.filter(accion='Anotación en lista de espera').exists())

    def test_anotarse_dos_veces_no_duplica(self):
        self.anotar(self.alumno)
        respuesta = self.anotar(self.alumno)
        self.assertContains(respuesta, 'Ya estabas en la lista de espera')
        self.assertEqual(ListaEspera.objects.filter(actividad=self.actividad).count(), 1)

    def test_el_inscrito_no_se_anota(self):
        respuesta = self.anotar(self.alumno_pasaporte)
        self.assertContains(respuesta, 'Ya estás inscrito')
        self.assertFalse(ListaEspera.objects.exists())

    def test_sin_politica_no_se_anota(self):
        self.anotar(self.alumno, acepta_politica='')
        self.assertFalse(ListaEspera.objects.exists())

    def test_rut_inexistente(self):
        respuesta = self.client.post(self.url(), {'rut': '11111111-1', 'acepta_politica': 'on', 'accion': 'lista_espera'})
        self.assertContains(respuesta, 'No estás registrado')
        self.assertFalse(ListaEspera.objects.exists())

    def test_alumno_bloqueado_no_se_anota(self):
        Alumno.objects.filter(pk=self.alumno.pk).update(activo=False)
        self.anotar(self.alumno)
        self.assertFalse(ListaEspera.objects.exists())

    def test_con_el_taller_comenzado_no_se_ofrece(self):
        self.actividad.fecha_inicio = timezone.now() - timedelta(minutes=10)
        self.actividad.save(update_fields=['fecha_inicio'])
        respuesta = self.client.get(self.url())
        self.assertNotContains(respuesta, 'Anotarme en la lista de espera')
        self.anotar(self.alumno)
        self.assertFalse(ListaEspera.objects.exists())

    def test_con_cupos_la_accion_no_anota(self):
        cancelar(self.ocupada.pk, por=self.admin)
        mail.outbox.clear()
        self.anotar(self.alumno)
        self.assertFalse(ListaEspera.objects.exists())


class AvisoTests(BaseListaEspera):
    def setUp(self):
        super().setUp()
        self.tercero = Alumno.objects.create(rut='11111111-1', nombres='Pía', apellidos='Soto',
                                             correo='pia@example.com', carrera=self.carrera.nombre, jornada='Diurno')
        self.anotar(self.alumno)
        self.anotar(self.tercero)
        mail.outbox.clear()

    def test_cancelar_con_enlace_avisa_a_todos(self):
        self.client.post(reverse('cancelar_inscripcion', args=[self.ocupada.token]))
        destinatarios = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(destinatarios, sorted([self.alumno.correo, self.tercero.correo]))
        self.assertIn(self.url(), mail.outbox[0].body)
        self.assertEqual(ListaEspera.objects.filter(ultimo_aviso__isnull=False).count(), 2)
        self.assertTrue(LogAuditoria.objects.filter(accion='Aviso a lista de espera').exists())

    def test_cancelar_desde_participantes_avisa_y_lo_dice(self):
        self.login_as(self.creador)
        respuesta = self.client.post(reverse('cancelar_inscripcion_gestor', args=[self.actividad.pk, self.ocupada.pk]),
                                     follow=True)
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(respuesta, 'Se avisó por correo a 2 personas')

    def test_el_primero_que_se_inscribe_se_queda_con_el_cupo(self):
        cancelar(self.ocupada.pk, por=self.admin)
        self.post_inscripcion(self.tercero)
        respuesta = self.post_inscripcion(self.alumno)
        self.assertTrue(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.tercero).exists())
        self.assertFalse(Inscripcion.objects.filter(actividad=self.actividad, alumno=self.alumno).exists())
        self.assertContains(respuesta, 'Sin cupos disponibles')
        # Pía sale de la lista al inscribirse; Juan sigue esperando
        self.assertEqual(list(ListaEspera.objects.values_list('alumno_id', flat=True)), [self.alumno.pk])

    def test_sin_cupo_libre_no_se_avisa(self):
        self.assertEqual(avisar(self.actividad), (0, 0))
        self.assertEqual(len(mail.outbox), 0)

    def test_no_avisa_a_bloqueados(self):
        Alumno.objects.filter(pk=self.tercero.pk).update(activo=False)
        cancelar(self.ocupada.pk, por=self.admin)
        self.assertEqual(avisar(self.actividad), (1, 0))

    def test_participantes_muestra_la_lista(self):
        self.login_as(self.creador)
        respuesta = self.client.get(reverse('participantes_actividad', args=[self.actividad.pk]))
        self.assertContains(respuesta, 'Lista de espera')
        self.assertContains(respuesta, '2 personas esperan un cupo')
        self.assertContains(respuesta, 'Sin avisos')
