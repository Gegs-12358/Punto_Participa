"""
Horario de registro del escáner (servicios/horario_registro.py): desde una hora antes hasta una hora después de
cada sesión. Fuera de ese rango solo corrigen el Administrador o el creador de la actividad, y queda en la
auditoría.

Correr solo este archivo:
    python manage.py test gestion.tests.escaner.tests_horario --noinput
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ...models import Actividad, Asistencia, LogAuditoria, Sesion
from ...servicios import horario_registro
from ..base import BaseSistemaTestCase

URL = reverse('escaneo')


def mover(actividad, inicio, horas=2):
    """Deja la actividad (y su única sesión) empezando `inicio` desde ahora y durando `horas`."""
    ahora = timezone.now()
    desde, hasta = ahora + inicio, ahora + inicio + timedelta(hours=horas)
    Actividad.objects.filter(pk=actividad.pk).update(fecha_inicio=desde, fecha_fin=hasta)
    Sesion.objects.filter(actividad=actividad).delete()
    Sesion.objects.create(actividad=actividad, numero=1, fecha_inicio=desde, fecha_fin=hasta)
    actividad.refresh_from_db()
    return actividad


class ServicioTests(BaseSistemaTestCase):
    def test_una_hora_antes_y_una_hora_despues(self):
        act = mover(self.actividad_masiva, timedelta(hours=1))
        sesion = act.lista_sesiones()[0]
        ahora = timezone.now()
        self.assertTrue(horario_registro.abierta(sesion, ahora + timedelta(minutes=1)))
        self.assertFalse(horario_registro.abierta(sesion, ahora - timedelta(minutes=2)))
        fin = sesion.fecha_fin
        self.assertTrue(horario_registro.abierta(sesion, fin + timedelta(minutes=59)))
        self.assertFalse(horario_registro.abierta(sesion, fin + timedelta(minutes=61)))

    def test_varias_sesiones_abre_la_que_corresponde(self):
        act = mover(self.actividad_masiva, -timedelta(days=7))
        ahora = timezone.now()
        Sesion.objects.create(actividad=act, numero=2, fecha_inicio=ahora - timedelta(minutes=30),
                              fecha_fin=ahora + timedelta(hours=1))
        self.assertTrue(horario_registro.actividad_abierta(act))


class ListaParaElegirTests(BaseSistemaTestCase):
    def setUp(self):
        self.en_curso = mover(self.actividad_masiva, -timedelta(minutes=30))
        self.terminada = mover(self.actividad, -timedelta(hours=5))          # terminó hace 3 horas (creador)
        self.de_otro = mover(self.actividad_otro, -timedelta(days=2))        # terminó hace 2 días (otro creador)

    def listas(self, usuario):
        self.client.force_login(usuario)
        r = self.client.get(URL)
        return ([a.pk for a in r.context['actividades_disponibles']],
                [a.pk for a in r.context['actividades_fuera_de_horario']])

    def test_el_encargado_solo_ve_las_abiertas_y_las_proximas(self):
        mover(self.actividad_otro, timedelta(hours=10))
        disponibles, fuera = self.listas(self.registrador)
        self.assertEqual(disponibles, [self.en_curso.pk, self.actividad_otro.pk])
        self.assertEqual(fuera, [])

    def test_las_que_abren_en_mas_de_24_horas_no_aparecen(self):
        mover(self.actividad_otro, timedelta(days=3))
        disponibles, _ = self.listas(self.registrador)
        self.assertNotIn(self.actividad_otro.pk, disponibles)

    def test_el_administrador_ve_aparte_todas_las_fuera_de_horario(self):
        disponibles, fuera = self.listas(self.admin)
        self.assertEqual(disponibles, [self.en_curso.pk])
        self.assertEqual(fuera, [self.terminada.pk, self.de_otro.pk])   # la más reciente primero

    def test_el_creador_ve_aparte_solo_las_suyas(self):
        _, fuera = self.listas(self.creador)
        self.assertEqual(fuera, [self.terminada.pk])

    def test_el_encargado_no_puede_elegir_una_terminada(self):
        self.client.force_login(self.registrador)
        r = self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': self.terminada.pk},
                             HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('actividad_escaneo_id', self.client.session)


class RegistroFueraDeHorarioTests(BaseSistemaTestCase):
    def escanear(self, usuario, actividad):
        self.client.force_login(usuario)
        self.client.post(URL, {'cambiar_actividad': '1', 'actividad_id': actividad.pk})
        session = self.client.session
        session['actividad_escaneo_id'] = actividad.pk   # el encargado no la puede elegir: se fuerza
        session.save()
        primera = self.client.post(URL, {'rut': self.alumno.rut})
        if primera.status_code != 200:
            return primera
        return self.client.post(URL, {'rut': self.alumno.rut, 'confirmar': 'true'})

    def test_terminada_el_encargado_no_registra(self):
        act = mover(self.actividad_masiva, -timedelta(hours=5))
        r = self.escanear(self.registrador, act)
        self.assertEqual(r.status_code, 403)
        self.assertIn('ya cerró', r.json()['message'])
        self.assertFalse(Asistencia.objects.filter(actividad=act).exists())

    def test_antes_de_tiempo_el_encargado_no_registra(self):
        act = mover(self.actividad_masiva, timedelta(hours=3))
        r = self.escanear(self.registrador, act)
        self.assertEqual(r.status_code, 403)
        self.assertIn('todavía no abre', r.json()['message'])

    def test_dentro_del_margen_registra_normal(self):
        act = mover(self.actividad_masiva, -timedelta(hours=2, minutes=30))   # terminó hace 30 minutos
        r = self.escanear(self.registrador, act)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Asistencia.objects.filter(actividad=act, alumno=self.alumno).exists())
        self.assertFalse(LogAuditoria.objects.filter(accion='Registro fuera de horario').exists())

    def test_el_administrador_corrige_y_queda_en_la_auditoria(self):
        act = mover(self.actividad_masiva, -timedelta(days=1))
        r = self.escanear(self.admin, act)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Asistencia.objects.filter(actividad=act, alumno=self.alumno).exists())
        log = LogAuditoria.objects.get(accion='Registro fuera de horario')
        self.assertEqual(log.usuario_sistema, self.admin)
        self.assertIn('Corrección', log.detalle)

    def test_el_creador_corrige_la_suya_pero_no_la_de_otro(self):
        suya = mover(self.actividad_masiva, -timedelta(days=1))
        self.assertEqual(self.escanear(self.creador, suya).status_code, 200)
        otra = mover(self.actividad_otro, -timedelta(days=1))
        Actividad.objects.filter(pk=otra.pk).update(tipo='MASIVA')
        self.assertEqual(self.escanear(self.creador, otra).status_code, 403)

    def test_la_pantalla_avisa_del_horario(self):
        act = mover(self.actividad_masiva, -timedelta(hours=5))
        self.escanear(self.registrador, act)
        r = self.client.get(URL)
        self.assertContains(r, 'Registro cerrado')
        self.assertContains(r, 'ya cerró')
        self.escanear(self.admin, act)
        r = self.client.get(URL)
        self.assertContains(r, 'Fuera de horario: corrección')
        self.assertContains(r, 'Como Administrador puedes corregir')
