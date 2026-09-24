"""
Suite de pruebas integrales para Punto Participa.

Ejecutar con:
    python manage.py test gestion.tests_integrales -v 2

Esta suite complementa tests.py y cubre los flujos principales:
- modelos y cupos;
- validaciones de ActividadForm;
- inscripción pública a talleres;
- registro de asistencia por escáner;
- permisos y propiedad de actividades;
- dashboard y reportes;
- exportaciones Excel y CSV;
- auditoría y creación de usuarios;
- middleware de cambio obligatorio de contraseña.
"""

from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from openpyxl import load_workbook

from .forms import ActividadForm
from .models import (
    Actividad,
    Alumno,
    Asistencia,
    Carrera,
    Inscripcion,
    Jornada,
    LogAuditoria,
    Rol,
    UsuarioSistema,
)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BaseSistemaTestCase(TestCase):
    """Datos comunes para los escenarios integrales."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(nombre="Administrador")
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


class ModeloYFormularioIntegralTests(BaseSistemaTestCase):
    def test_propiedades_y_recalculo_de_cupos_del_taller(self):
        self.assertTrue(self.actividad.esta_activa)
        self.assertTrue(self.actividad.es_taller)
        self.assertFalse(self.actividad.esta_lleno)

        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno)
        self.actividad.recalcular_cupos()
        self.assertEqual(self.actividad.cupos_disponibles, 1)

        Inscripcion.objects.create(actividad=self.actividad, alumno=self.alumno_pasaporte)
        self.actividad.recalcular_cupos()
        self.assertEqual(self.actividad.cupos_disponibles, 0)
        self.assertTrue(self.actividad.esta_lleno)

    def test_actividad_masiva_no_mantiene_cupos(self):
        self.actividad_masiva.cupos_totales = 100
        self.actividad_masiva.cupos_disponibles = 100
        self.actividad_masiva.recalcular_cupos()
        self.assertIsNone(self.actividad_masiva.cupos_totales)
        self.assertIsNone(self.actividad_masiva.cupos_disponibles)

    def test_formulario_taller_requiere_cupo_carrera_jornada_y_fechas_validas(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        datos = {
            "titulo": "Nuevo taller",
            "descripcion": "Descripción suficientemente clara",
            "tipo": "TALLER",
            "lugar": "Sala 1",
            "cupos_totales": 20,
            "fecha_inicio": futuro.strftime("%Y-%m-%dT%H:%M"),
            "fecha_fin": (futuro + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        actividad = form.save(commit=False)
        actividad.creado_por = self.creador
        actividad.save()
        form.save_m2m()
        self.assertEqual(actividad.cupos_disponibles, 20)

    def test_formulario_rechaza_fecha_fin_anterior(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        datos = {
            "titulo": "Fechas inválidas",
            "descripcion": "Descripción",
            "tipo": "MASIVA",
            "lugar": "Sala 1",
            "fecha_inicio": futuro.strftime("%Y-%m-%dT%H:%M"),
            "fecha_fin": (futuro - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_fin", form.errors)

    def test_formulario_rechaza_taller_sin_cupos(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        datos = {
            "titulo": "Taller sin cupos",
            "descripcion": "Descripción",
            "tipo": "TALLER",
            "lugar": "Sala 1",
            "cupos_totales": "",
            "fecha_inicio": futuro.strftime("%Y-%m-%dT%H:%M"),
            "fecha_fin": (futuro + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("cupos_totales", form.errors)


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
            {"rut": "20.001.550-9"},
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
            {"rut": "200015509"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya estás inscrito")

    def test_inscripcion_publica_rechaza_alumno_inexistente(self):
        response = self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "99999999-9"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No estás registrado")

    def test_escaneo_confirma_y_registra_asistencia(self):
        self.login_as(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()

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
        self.login_as(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad_masiva.pk
        session.save()

        response = self.client.post(
            reverse("escaneo"), {"rut": "200015509"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("ya fue registrada", response.json()["message"])

    def test_escaneo_rechaza_taller_sin_inscripcion(self):
        self.login_as(self.registrador)
        session = self.client.session
        session["actividad_escaneo_id"] = self.actividad.pk
        session.save()

        response = self.client.post(
            reverse("escaneo"), {"rut": "200015509"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("no está inscrito", response.json()["message"])


class VistasPermisosYReportesIntegralTests(BaseSistemaTestCase):
    def test_dashboard_y_reportes_requieren_login(self):
        self.assertEqual(
            self.client.get(reverse("dashboard")).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("reportes")).status_code, 302
        )

    def test_creador_solo_ve_sus_actividades_en_lista(self):
        self.login_as(self.creador)
        response = self.client.get(reverse("lista_actividades"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.actividad.titulo)
        self.assertNotContains(response, self.actividad_otro.titulo)

    def test_admin_ve_dashboard_y_reportes(self):
        self.login_as(self.admin)
        dashboard = self.client.get(reverse("dashboard"))
        reportes = self.client.get(reverse("reportes"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(reportes.status_code, 200)
        self.assertContains(dashboard, "graficoLinea")
        self.assertContains(reportes, "graficoBarrasReportes")

    def test_creador_no_puede_ver_actividad_de_otro_creador(self):
        self.login_as(self.creador)
        response = self.client.get(
            reverse("actividad_detalle", args=[self.actividad_otro.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("lista_actividades"))

    def test_exportacion_csv_contiene_encabezados_y_datos(self):
        self.login_as(self.creador)
        response = self.client.get(reverse("exportar_reportes", args=["csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        contenido = response.content.decode("utf-8")
        self.assertIn("Actividad", contenido)
        self.assertIn(self.actividad.titulo, contenido)

    def test_exportacion_excel_es_un_libro_valido(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("exportar_reportes", args=["excel"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        libro = load_workbook(filename=BytesIO(response.content), read_only=True)
        hoja = libro["Reporte de Actividades"]
        self.assertEqual(hoja.cell(1, 1).value, "Actividad")
        self.assertTrue(any(fila[0] == self.actividad.titulo for fila in hoja.iter_rows(values_only=True)))

    def test_exportacion_detalle_y_auditoria_excel(self):
        LogAuditoria.objects.create(
            usuario_sistema=self.admin,
            modulo="Pruebas",
            accion="Acción de prueba",
            detalle="Detalle",
        )
        self.login_as(self.admin)
        detalle = self.client.get(
            reverse("exportar_reportes_detalle", args=["excel"])
        )
        auditoria = self.client.get(reverse("exportar_auditoria"))
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(auditoria.status_code, 200)
        self.assertGreater(len(detalle.content), 100)
        self.assertGreater(len(auditoria.content), 100)


class UsuariosAuditoriaYMiddlewareIntegralTests(BaseSistemaTestCase):
    def test_administrador_puede_crear_usuario_y_se_genera_log(self):
        self.login_as(self.admin)
        response = self.client.post(
            reverse("guardar_usuario"),
            {
                "username": "nuevo_integral",
                "nombre": "Nuevo Usuario",
                "email": "nuevo@example.com",
                "rol": self.rol_registrador.pk,
                "estado": "on",
                "rut": "12345678-5",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        usuario = User.objects.get(username="nuevo_integral")
        self.assertTrue(UsuarioSistema.objects.filter(user=usuario, rol=self.rol_registrador).exists())
        self.assertTrue(LogAuditoria.objects.filter(accion="Guardar usuario").exists())

    def test_exportacion_de_auditoria_solo_es_para_administrador(self):
        self.login_as(self.registrador)
        response = self.client.get(reverse("exportar_auditoria"))
        self.assertEqual(response.status_code, 403)

    def test_middleware_obliga_cambio_de_contrasena(self):
        self.admin.usuariosistema.must_change_password = True
        self.admin.usuariosistema.save(update_fields=["must_change_password"])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("cambiar_contrasena"))

    def test_archivo_de_imagen_se_puede_recibir_en_el_formulario(self):
        futuro = timezone.localtime(timezone.now() + timedelta(days=3))
        imagen = SimpleUploadedFile(
            "banner.txt", b"contenido-de-prueba", content_type="text/plain"
        )
        datos = {
            "titulo": "Actividad con archivo",
            "descripcion": "Descripción",
            "tipo": "MASIVA",
            "lugar": "Sala 2",
            "fecha_inicio": futuro.strftime("%Y-%m-%dT%H:%M"),
            "fecha_fin": (futuro + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "carreras": [self.carrera.pk],
            "jornadas": [self.jornada.pk],
        }
        form = ActividadForm(data=datos, files={"imagen": imagen})
        self.assertFalse(form.is_valid())
        self.assertIn("imagen", form.errors)


class AutenticacionYCorreoIntegralTests(BaseSistemaTestCase):
    def test_login_con_credenciales_validas(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.admin.username, "password": "ClaveSegura123!"},
        )
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_con_credenciales_invalidas_no_autentica(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.admin.username, "password": "incorrecta"},
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.status_code, 200)

    def test_previsualizacion_de_invitacion_devuelve_html(self):
        self.login_as(self.creador)
        response = self.client.get(
            reverse("previsualizar_invitacion", args=[self.actividad.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIn("html", response.json())

    def test_inscripcion_no_envia_correo_externo_en_modo_local(self):
        self.client.post(
            reverse("inscripcion_taller", args=[self.actividad.pk]),
            {"rut": "AB123456"},
        )
        self.assertEqual(len(mail.outbox), 0)
