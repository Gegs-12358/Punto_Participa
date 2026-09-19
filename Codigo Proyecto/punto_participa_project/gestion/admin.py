from django.contrib import admin
from .models import (
    Rol, UsuarioSistema, Alumno, Actividad, Carrera, Jornada,
    Inscripcion, Asistencia, NotificacionCorreo, LogAuditoria
)
from .utils import normalizar_rut


# ============================================================
# PERSONALIZACIÓN DEL ADMIN
# ============================================================

admin.site.site_header = 'Punto Participa'
admin.site.site_title = 'Punto Participa'
admin.site.index_title = 'Panel de Administración'


# ============================================================
# ADMIN: ROL
# ============================================================

@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)
    ordering = ('nombre',)


# ============================================================
# ADMIN: USUARIO SISTEMA
# ============================================================

@admin.register(UsuarioSistema)
class UsuarioSistemaAdmin(admin.ModelAdmin):
    list_display = ('user', 'rut', 'rol', 'activo', 'must_change_password')
    list_filter = ('rol', 'activo', 'must_change_password')
    search_fields = ('user__username', 'user__first_name', 'user__email', 'rut')
    list_select_related = ('user', 'rol')
    ordering = ('user__username',)

    fieldsets = (
        ('Credenciales', {
            'fields': ('user', 'rut')
        }),
        ('Permisos', {
            'fields': ('rol', 'activo', 'must_change_password')
        }),
    )


# ============================================================
# ADMIN: ALUMNO
# ============================================================
@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    list_display = ('rut', 'tipo_documento', 'nombres', 'apellidos', 'carrera', 'jornada')
    list_filter = ('tipo_documento', 'carrera', 'jornada')
    search_fields = ('rut', 'nombres', 'apellidos', 'correo')
    ordering = ('apellidos', 'nombres')

    def save_model(self, request, obj, form, change):
        """Normaliza el RUT antes de guardar."""
        obj.rut = normalizar_rut(obj.rut)
        super().save_model(request, obj, form, change)


# ============================================================
# ADMIN: CARRERA
# ============================================================

@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'escuela')
    list_filter = ('escuela',)
    search_fields = ('nombre', 'escuela')
    ordering = ('escuela', 'nombre')


# ============================================================
# ADMIN: JORNADA
# ============================================================

@admin.register(Jornada)
class JornadaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)
    ordering = ('nombre',)


# ============================================================
# ADMIN: ACTIVIDAD
# ============================================================

@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titulo', 'tipo', 'estado',
        'fecha_inicio', 'fecha_fin', 'cupos_totales', 'cupos_disponibles'
    )
    list_filter = ('tipo', 'estado', 'carreras', 'jornadas')
    search_fields = ('titulo', 'descripcion', 'lugar')
    list_select_related = ('creado_por',)
    filter_horizontal = ('carreras', 'jornadas')
    ordering = ('-fecha_inicio',)
    date_hierarchy = 'fecha_inicio'

    
    def save_model(self, request, obj, form, change):
        """
        Recalcula cupos_disponibles según las inscripciones actuales,
        igual que hace la vista normal de la app (crear/editar actividad).
        - Nueva actividad (change=False): 0 inscritos.
        - Edición (change=True): cuenta las inscripciones reales en BBDD.
        """
        if not change:
            obj.recalcular_cupos(inscritos_override=0)
        else:
            obj.recalcular_cupos()
        super().save_model(request, obj, form, change)

    fieldsets = (
        ('Información básica', {
            'fields': ('titulo', 'descripcion', 'imagen')
        }),
        ('Configuración del evento', {
            'fields': ('tipo', 'estado', 'lugar')
        }),
        ('Fechas', {
            'fields': ('fecha_inicio', 'fecha_fin', 'cronograma')
        }),
        ('Cupos (solo Taller)', {
            'fields': ('cupos_totales', 'cupos_disponibles')
        }),
        ('Público objetivo', {
            'fields': ('carreras', 'jornadas')
        }),
        ('Auditoría', {
            'fields': ('creado_por',),
            'classes': ('collapse',)
        }),
    )


# ============================================================
# ADMIN: INSCRIPCIÓN
# ============================================================

@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('id', 'actividad', 'alumno', 'fecha_inscripcion', 'estado')
    list_filter = ('estado', 'fecha_inscripcion')
    search_fields = ('alumno__rut', 'alumno__nombres', 'alumno__apellidos', 'actividad__titulo')
    list_select_related = ('actividad', 'alumno')
    ordering = ('-fecha_inscripcion',)
    date_hierarchy = 'fecha_inscripcion'


# ============================================================
# ADMIN: ASISTENCIA
# ============================================================

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ('id', 'actividad', 'alumno', 'metodo_ingreso', 'fecha_ingreso', 'registrado_por')
    list_filter = ('metodo_ingreso', 'fecha_ingreso')
    search_fields = ('alumno__rut', 'alumno__nombres', 'alumno__apellidos', 'actividad__titulo')
    list_select_related = ('actividad', 'alumno', 'registrado_por')
    ordering = ('-fecha_ingreso',)
    date_hierarchy = 'fecha_ingreso'
    readonly_fields = ('fecha_ingreso',)


# ============================================================
# ADMIN: NOTIFICACIÓN CORREO
# ============================================================

@admin.register(NotificacionCorreo)
class NotificacionCorreoAdmin(admin.ModelAdmin):
    list_display = ('id', 'actividad', 'alumno', 'estado_envio', 'fecha_envio')
    list_filter = ('estado_envio', 'fecha_envio')
    search_fields = ('alumno__rut', 'alumno__nombres', 'actividad__titulo')
    list_select_related = ('actividad', 'alumno')
    ordering = ('-fecha_envio',)
    date_hierarchy = 'fecha_envio'
    readonly_fields = ('fecha_envio',)


# ============================================================
# ADMIN: LOG AUDITORÍA (solo lectura)
# ============================================================

@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'fecha_registro', 'usuario_sistema',
        'modulo', 'accion', 'objeto_nombre', 'ip_address'
    )
    list_filter = ('modulo', 'accion', 'fecha_registro')
    search_fields = ('accion', 'detalle', 'objeto_nombre', 'usuario_sistema__username')
    list_select_related = ('usuario_sistema',)
    ordering = ('-fecha_registro',)
    date_hierarchy = 'fecha_registro'

    # Solo lectura
    readonly_fields = (
        'usuario_sistema', 'modulo', 'accion', 'detalle',
        'objeto_tipo', 'objeto_id', 'objeto_nombre',
        'ip_address', 'user_agent', 'cambios_json', 'fecha_registro'
    )

    def has_add_permission(self, request):
        """No se puede crear desde el admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """No se puede editar."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No se puede eliminar."""
        return False