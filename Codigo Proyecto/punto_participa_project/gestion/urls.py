from django.urls import path
from . import views

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
    path('reportes/exportar/<str:formato>/', views.exportar_reportes, name='exportar_reportes'),
    path('reportes/exportar-detalle/<str:formato>/', views.exportar_reportes_detalle, name='exportar_reportes_detalle'),

    # ============================================================
    # USUARIOS
    # ============================================================
    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/guardar/', views.guardar_usuario, name='guardar_usuario'),

    # ============================================================
    # ACTIVIDADES
    # ============================================================
    path('actividades/', views.lista_actividades, name='lista_actividades'),
    path('actividades/nueva/', views.crear_actividad, name='crear_actividad'),
    path('actividades/editar/<int:pk>/', views.editar_actividad, name='editar_actividad'),
    path('actividades/eliminar/<int:pk>/', views.eliminar_actividad, name='eliminar_actividad'),
    path('actividades/enviar-invitaciones/', views.enviar_invitaciones, name='enviar_invitaciones'),
    path('actividades/previsualizar-invitacion/<int:pk>/', views.previsualizar_invitacion, name='previsualizar_invitacion'),
    path('actividades/eliminar-ajax/<int:pk>/', views.eliminar_ajax, name='eliminar_ajax'),

    # ============================================================
    # ESCÁNER
    # ============================================================
    path('escaneo/', views.escaneo, name='escaneo'),

    # ============================================================
    # AUDITORÍA
    # ============================================================
    path('auditoria/', views.lista_auditoria, name='auditoria'),
    path('auditoria/exportar/', views.exportar_auditoria, name='exportar_auditoria'),

    # ============================================================
    # INSCRIPCIÓN PÚBLICA
    # ============================================================
    path('taller/<int:actividad_id>/', views.inscripcion_taller, name='inscripcion_taller'),

]