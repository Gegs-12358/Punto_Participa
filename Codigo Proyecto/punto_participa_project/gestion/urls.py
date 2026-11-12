from django.urls import path
from . import (exportaciones, views, views_actividad_publica, views_alumnos, views_catalogos,
               views_importar, views_invitados)

# Sin app_name para mantener compatibilidad con los templates existentes

urlpatterns = [
    # ============================================================
    # AUTENTICACIÓN
    # ============================================================
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('cambiar-contrasena/', views.cambiar_contrasena, name='cambiar_contrasena'),

    # ============================================================
    # REPORTES
    # ============================================================
    path('reportes/', views.reportes, name='reportes'),
    path('reportes/descargar/<str:tipo>/<str:formato>/', exportaciones.exportar_reporte, name='exportar_reporte'),
    # Direcciones anteriores: resumen por actividad y participación por escuela/carrera/jornada
    path('reportes/exportar/<str:formato>/', exportaciones.exportar_resumen, name='exportar_reportes'),
    path('reportes/exportar-detalle/<str:formato>/', exportaciones.exportar_participacion,
         name='exportar_reportes_detalle'),

    # ============================================================
    # USUARIOS
    # ============================================================
    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/guardar/', views.guardar_usuario, name='guardar_usuario'),

    # ============================================================
    # ALUMNOS (IMPORTACIÓN)
    # ============================================================
    path('alumnos/', views_alumnos.lista_alumnos, name='lista_alumnos'),
    path('alumnos/<int:pk>/', views_alumnos.alumno_detalle, name='alumno_detalle'),
    path('alumnos/<int:pk>/bloqueo/', views_alumnos.alumno_bloqueo, name='alumno_bloqueo'),
    path('alumnos/importar/', views_importar.importar_alumnos_web, name='importar_alumnos'),
    path('catalogos/lugares/', views_catalogos.catalogo_lugares, name='catalogo_lugares'),
    path('catalogos/escuelas/', views_catalogos.catalogo_escuelas, name='catalogo_escuelas'),
    path('catalogos/carreras/', views_catalogos.catalogo_carreras, name='catalogo_carreras'),

    path('recuperar-contrasena/', views.solicitar_recuperacion, name='recuperar_contrasena'),
    path('restablecer-contrasena/<uidb64>/<token>/', views.restablecer_contrasena, name='restablecer_contrasena'),

    # ============================================================
    # ACTIVIDADES
    # ============================================================
    path('actividades/', views.lista_actividades, name='lista_actividades'),
    path('actividades/nueva/', views.crear_actividad, name='crear_actividad'),
    path('actividades/editar/<int:pk>/', views.editar_actividad, name='editar_actividad'),
    path('actividades/enviar-invitaciones/', views.enviar_invitaciones, name='enviar_invitaciones'),
    path('actividades/previsualizar-invitacion/<int:pk>/', views.previsualizar_invitacion, name='previsualizar_invitacion'),
    path('actividades/eliminar-ajax/<int:pk>/', views.eliminar_ajax, name='eliminar_ajax'),
    # ============================================================
    # DETALLE DE ACTIVIDAD
    # ============================================================
    path( 'actividades/<int:pk>/', views.actividad_detalle, name='actividad_detalle'),
    path( 'actividades/<int:pk>/notificaciones/', views.notificaciones_actividad, name='notificaciones_actividad'),
    path( 'actividades/<int:pk>/participantes/', views.participantes_actividad, name='participantes_actividad'),
    path('actividades/<int:pk>/invitados/', views_invitados.invitados_actividad, name='invitados_actividad'),
    path('actividades/<int:pk>/invitados/<int:invitado_id>/quitar/', views_invitados.quitar_invitado,
         name='quitar_invitado'),
    path('actividades/invitados/plantilla.csv', views_invitados.plantilla_invitados, name='plantilla_invitados'),
    # ============================================================
    # ESCÁNER
    # ============================================================
    path('escaneo/', views.escaneo, name='escaneo'),
    path('escaneo/contador/', views.escaneo_contador, name='escaneo_contador'),

    # ============================================================
    # AUDITORÍA
    # ============================================================
    path('auditoria/', views.lista_auditoria, name='auditoria'),
    path('auditoria/exportar/', views.exportar_auditoria, name='exportar_auditoria'),

    # ============================================================
    # INSCRIPCIÓN PÚBLICA
    # ============================================================
    path('taller/<int:actividad_id>/', views.inscripcion_taller, name='inscripcion_taller'),
    path('actividad/<int:actividad_id>/', views_actividad_publica.actividad_publica, name='actividad_publica'),
    path('privacidad/', views.politica_privacidad, name='privacidad'),

]