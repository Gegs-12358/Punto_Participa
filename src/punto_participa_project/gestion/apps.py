from django.apps import AppConfig


class GestionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gestion'
    verbose_name = 'Gestión Punto Participa'

    def ready(self):
        # Señales que mantienen las sesiones y la asistencia por sesión (servicios/sesiones.py)
        from .servicios import sesiones  # noqa: F401
