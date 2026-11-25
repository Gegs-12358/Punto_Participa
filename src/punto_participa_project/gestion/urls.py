"""
URL de la aplicación, agrupadas igual que los archivos de gestion/views/.
Los nombres (name=...) son los que usan las plantillas; no cambian aunque una vista se mueva de archivo.
"""
from django.urls import path

from .views import (actividades, alumnos, auditoria, catalogos, cuentas, escaner, exportaciones, inicio,
                    inscripciones, invitaciones, reportes, usuarios)

urlpatterns = [
    # ============================================================
    # CUENTAS
    # ============================================================
    path('login/', cuentas.login_view, name='login'),
    path('logout/', cuentas.logout_view, name='logout'),
    path('cambiar-contrasena/', cuentas.cambiar_contrasena, name='cambiar_contrasena'),
    path('recuperar-contrasena/', cuentas.solicitar_recuperacion, name='recuperar_contrasena'),
    path('restablecer-contrasena/<uidb64>/<token>/', cuentas.restablecer_contrasena, name='restablecer_contrasena'),

    # ============================================================
    # INICIO
    # ============================================================
    path('', inicio.dashboard, name='dashboard'),
    path('retencion/<int:pk>/ejecutar/', inicio.retencion_ejecutar, name='retencion_ejecutar'),

    # ============================================================
    # ACTIVIDADES
    # ============================================================
    path('actividades/', actividades.lista_actividades, name='lista_actividades'),
    path('actividades/nueva/', actividades.crear_actividad, name='crear_actividad'),
    path('actividades/editar/<int:pk>/', actividades.editar_actividad, name='editar_actividad'),
    path('actividades/eliminar-ajax/<int:pk>/', actividades.eliminar_ajax, name='eliminar_ajax'),
    path('actividades/<int:pk>/', actividades.actividad_detalle, name='actividad_detalle'),
    path('actividades/<int:pk>/notificaciones/', actividades.notificaciones_actividad,
         name='notificaciones_actividad'),
    path('actividades/<int:pk>/participantes/', actividades.participantes_actividad,
         name='participantes_actividad'),

    # ============================================================
    # INVITACIONES (correo por carrera, lista de invitados y respuesta pública)
    # ============================================================
    path('actividades/enviar-invitaciones/', invitaciones.enviar_invitaciones, name='enviar_invitaciones'),
    path('actividades/previsualizar-invitacion/<int:pk>/', invitaciones.previsualizar_invitacion,
         name='previsualizar_invitacion'),
    path('actividades/<int:pk>/invitados/', invitaciones.invitados_actividad, name='invitados_actividad'),
    path('actividades/<int:pk>/invitados/<int:invitado_id>/quitar/', invitaciones.quitar_invitado,
         name='quitar_invitado'),
    path('actividades/invitados/plantilla.csv', invitaciones.plantilla_invitados, name='plantilla_invitados'),
    path('actividades/<int:pk>/invitados/enviar/', invitaciones.enviar_invitaciones_lista,
         name='enviar_invitaciones_lista'),
    path('invitacion/<str:token>/', invitaciones.responder_invitacion, name='responder_invitacion'),

    # ============================================================
    # INSCRIPCIONES (página pública, cancelación y lista de espera)
    # ============================================================
    path('taller/<int:actividad_id>/', inscripciones.inscripcion_taller, name='inscripcion_taller'),
    path('actividad/<int:actividad_id>/', inscripciones.actividad_publica, name='actividad_publica'),
    path('inscripcion/cancelar/<str:token>/', inscripciones.cancelar_inscripcion, name='cancelar_inscripcion'),
    path('actividades/<int:pk>/inscripciones/<int:inscripcion_id>/cancelar/',
         inscripciones.cancelar_inscripcion_gestor, name='cancelar_inscripcion_gestor'),
    path('privacidad/', inscripciones.politica_privacidad, name='privacidad'),

    # ============================================================
    # ESCÁNER
    # ============================================================
    path('escaneo/', escaner.escaneo, name='escaneo'),
    path('escaneo/contador/', escaner.escaneo_contador, name='escaneo_contador'),

    # ============================================================
    # REPORTES Y EXPORTACIONES
    # ============================================================
    path('reportes/', reportes.reportes, name='reportes'),
    path('reportes/descargar/<str:tipo>/<str:formato>/', exportaciones.exportar_reporte, name='exportar_reporte'),
    # Direcciones anteriores: resumen por actividad y participación por escuela/carrera/jornada
    path('reportes/exportar/<str:formato>/', exportaciones.exportar_resumen, name='exportar_reportes'),
    path('reportes/exportar-detalle/<str:formato>/', exportaciones.exportar_participacion,
         name='exportar_reportes_detalle'),

    # ============================================================
    # USUARIOS
    # ============================================================
    path('usuarios/', usuarios.usuarios, name='usuarios'),
    path('usuarios/guardar/', usuarios.guardar_usuario, name='guardar_usuario'),
    path('usuarios/importar/', usuarios.importar_usuarios, name='importar_usuarios'),
    path('usuarios/importar/plantilla.csv', usuarios.plantilla_usuarios, name='plantilla_usuarios'),

    # ============================================================
    # ALUMNOS
    # ============================================================
    path('alumnos/', alumnos.lista_alumnos, name='lista_alumnos'),
    path('alumnos/<int:pk>/', alumnos.alumno_detalle, name='alumno_detalle'),
    path('alumnos/<int:pk>/bloqueo/', alumnos.alumno_bloqueo, name='alumno_bloqueo'),
    path('alumnos/<int:pk>/anonimizar/', alumnos.alumno_anonimizar, name='alumno_anonimizar'),
    path('alumnos/importar/', alumnos.importar_alumnos_web, name='importar_alumnos'),

    # ============================================================
    # CATÁLOGOS
    # ============================================================
    path('catalogos/lugares/', catalogos.catalogo_lugares, name='catalogo_lugares'),
    path('catalogos/escuelas/', catalogos.catalogo_escuelas, name='catalogo_escuelas'),
    path('catalogos/carreras/', catalogos.catalogo_carreras, name='catalogo_carreras'),

    # ============================================================
    # AUDITORÍA
    # ============================================================
    path('auditoria/', auditoria.lista_auditoria, name='auditoria'),
    path('auditoria/exportar/', exportaciones.exportar_auditoria, name='exportar_auditoria'),
]
