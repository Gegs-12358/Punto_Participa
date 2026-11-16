"""
Piezas comunes de las pruebas (este archivo no tiene pruebas propias):

  BaseSistemaTestCase  roles, usuarios (admin, creador, otro creador, registrador), carreras, jornadas,
                       alumnos (con RUT y con pasaporte) y tres actividades listas para usar.
  BackendCorreoFallido servidor de correo que siempre falla (CORREO_FALLIDO), para probar los avisos.
  SilenciarRegistros   apaga el registro de errores mientras corre la clase, para que la salida de las
                       pruebas que provocan fallas a propósito se lea limpia.
"""
import logging
import smtplib

from datetime import timedelta
from django.contrib.auth.models import User
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.utils import timezone
from ..models import Actividad, Alumno, Carrera, Jornada, Lugar, Rol, UsuarioSistema


class BackendCorreoFallido(BaseEmailBackend):
    """Servidor de correo que siempre falla, como un SMTP caído. Uso:
    @override_settings(EMAIL_BACKEND=CORREO_FALLIDO)"""

    def send_messages(self, email_messages):
        raise smtplib.SMTPException('Servidor de correo no disponible (prueba)')


CORREO_FALLIDO = 'gestion.tests.base.BackendCorreoFallido'


class SilenciarRegistros:
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        logging.disable(logging.NOTSET)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BaseSistemaTestCase(TestCase):
    """Datos comunes para los escenarios integrales."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(nombre="Administrador")
        # Lugares del catálogo que usan los formularios de estas pruebas
        for nombre in ("Sala 1", "Sala nueva", "Auditorio", "Sala AJAX", "Sala auditoría"):
            Lugar.objects.create(nombre=nombre)
        cls.rol_creador = Rol.objects.create(nombre="Creador de Evento")
        cls.rol_registrador = Rol.objects.create(nombre="Encargado de Registrar")

        cls.admin = cls._crear_usuario(
            "admin_integral", "Administrador", cls.rol_admin
        )
        cls.creador = cls._crear_usuario(
            "creador_integral", "Creador de Evento", cls.rol_creador
        )
        cls.otro_creador = cls._crear_usuario(
            "creador_otro", "Creador de Evento", cls.rol_creador
        )
        cls.registrador = cls._crear_usuario(
            "registrador_integral", "Encargado de Registrar", cls.rol_registrador
        )

        cls.carrera = Carrera.objects.create(
            nombre="Ingeniería en Informática",
            escuela="Escuela de Informática y Telecomunicaciones",
        )
        cls.carrera_2 = Carrera.objects.create(
            nombre="Diseño Gráfico",
            escuela="Escuela de Diseño",
        )
        cls.jornada = Jornada.objects.create(nombre="Diurno")
        cls.jornada_2 = Jornada.objects.create(nombre="Vespertino")

        cls.alumno = Alumno.objects.create(
            rut="20001550-9",
            tipo_documento="RUT",
            nombres="Juan",
            apellidos="Pérez",
            correo="juan.perez@example.com",
            carrera=cls.carrera.nombre,
            jornada=cls.jornada.nombre,
        )
        cls.alumno_pasaporte = Alumno.objects.create(
            rut="AB123456",
            tipo_documento="PASAPORTE",
            nombres="Ana",
            apellidos="Gómez",
            correo="ana.gomez@example.com",
            carrera=cls.carrera_2.nombre,
            jornada=cls.jornada_2.nombre,
        )

        cls.actividad = cls._crear_actividad(
            titulo="Taller integral",
            tipo="TALLER",
            creador=cls.creador,
            cupos=2,
        )
        cls.actividad_masiva = cls._crear_actividad(
            titulo="Actividad masiva",
            tipo="MASIVA",
            creador=cls.creador,
            cupos=None,
        )
        cls.actividad_otro = cls._crear_actividad(
            titulo="Actividad de otro creador",
            tipo="TALLER",
            creador=cls.otro_creador,
            cupos=5,
        )

    @staticmethod
    def _crear_usuario(username, rol_nombre, rol):
        user = User.objects.create_user(
            username=username,
            password="ClaveSegura123!",
            email=f"{username}@example.com",
            first_name=username,
        )
        UsuarioSistema.objects.create(
            user=user,
            rol=rol,
            activo=True,
            must_change_password=False,
            rut=f"9999999-{user.pk}",
        )
        return user

    @classmethod
    def _crear_actividad(cls, titulo, tipo, creador, cupos):
        ahora = timezone.now()
        actividad = Actividad.objects.create(
            titulo=titulo,
            descripcion="Descripción de prueba integral",
            tipo=tipo,
            lugar="Sede Alameda",
            cupos_totales=cupos,
            cupos_disponibles=cupos,
            fecha_inicio=ahora + timedelta(days=2),
            fecha_fin=ahora + timedelta(days=2, hours=2),
            creado_por=creador,
        )
        actividad.carreras.add(cls.carrera, cls.carrera_2)
        actividad.jornadas.add(cls.jornada, cls.jornada_2)
        actividad.recalcular_cupos(inscritos_override=0)
        actividad.save(update_fields=["cupos_totales", "cupos_disponibles"])
        return actividad

    def login_as(self, user):
        self.client.force_login(user)

    def seleccionar_actividad(self, actividad=None, usuario=None):
        """Inicia sesión como registrador y deja elegida la actividad del escáner."""
        self.client.force_login(usuario or self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = (actividad or self.actividad_masiva).pk
        session.save()
