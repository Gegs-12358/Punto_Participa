from django.db import models
from django.contrib.auth.models import User
from .utils import limpiar_texto


# ==================== MODELOS BASE ====================

class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class UsuarioSistema(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='usuariosistema')
    rut = models.CharField(max_length=12, unique=True, null=True, blank=True, db_index=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='usuarios')
    activo = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Usuario del sistema'
        verbose_name_plural = 'Usuarios del sistema'
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} ({self.rol.nombre if self.rol else 'Sin rol'})"


# Reemplaza la clase Alumno en tu models.py por esta.
# Agrega arriba del models.py:  from .utils import limpiar_texto

class Alumno(models.Model):
    TIPO_DOCUMENTO_CHOICES = [
        ('RUT', 'RUT chileno'),
        ('PASAPORTE', 'Pasaporte extranjero'),
        ('RUN_PROVISORIO', 'RUN provisorio'),
        ('CEDULA_EXTRANJERO', 'Cédula de identidad de extranjero'),
    ]

    rut = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='RUT/Pasaporte'
    )
    tipo_documento = models.CharField(
        max_length=20,
        choices=TIPO_DOCUMENTO_CHOICES,
        default='RUT',
        verbose_name='Tipo de documento'
    )
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    correo = models.EmailField()
    carrera = models.CharField(max_length=100)
    jornada = models.CharField(max_length=20)

    class Meta:
        verbose_name = 'Alumno'
        verbose_name_plural = 'Alumnos'
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"

    def save(self, *args, **kwargs):
        # Red de seguridad: cubre admin, importador y objects.create().
        # OJO: .update() y bulk_create() NO pasan por aquí; limpiar antes.
        self.nombres = limpiar_texto(self.nombres)
        self.apellidos = limpiar_texto(self.apellidos)
        self.carrera = limpiar_texto(self.carrera)
        self.jornada = limpiar_texto(self.jornada)
        self.correo = limpiar_texto(self.correo)
        self.rut = limpiar_texto(self.rut) or None  # '' -> None (evita choque de unique)
        super().save(*args, **kwargs)


class Carrera(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    escuela = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Carrera'
        verbose_name_plural = 'Carreras'
        ordering = ['escuela', 'nombre']

    def __str__(self):
        return self.nombre


class Jornada(models.Model):
    nombre = models.CharField(max_length=20, unique=True)

    class Meta:
        verbose_name = 'Jornada'
        verbose_name_plural = 'Jornadas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Actividad(models.Model):
    TIPO_CHOICES = [('MASIVA', 'Masiva'), ('TALLER', 'Taller')]
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada')
    ] 

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    lugar = models.CharField(max_length=200)
    imagen = models.ImageField(upload_to='actividades/', null=True, blank=True)
    cupos_totales = models.IntegerField(null=True, blank=True)
    cupos_disponibles = models.IntegerField(null=True, blank=True)
    fecha_inicio = models.DateTimeField(db_index=True)
    fecha_fin = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ACTIVA', db_index=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='actividades_creadas')
    carreras = models.ManyToManyField(Carrera, blank=True, related_name='actividades')
    jornadas = models.ManyToManyField(Jornada, blank=True, related_name='actividades')
    cronograma = models.TextField(blank=True, null=True, verbose_name="Cronograma de fechas")
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Actividad'
        verbose_name_plural = 'Actividades'
        ordering = ['-fecha_inicio']
        indexes = [
            models.Index(fields=['-fecha_inicio', 'estado']),
        ]

    def __str__(self):
        return self.titulo

    # ============================================================
    # [REFACTOR] Propiedades y métodos de negocio
    # ============================================================

    @property
    def esta_activa(self):
        return self.estado == 'ACTIVA'

    @property
    def es_taller(self):
        return self.tipo == 'TALLER'

    @property
    def esta_lleno(self):
        """[REFACTOR] Útil para templates y validaciones rápidas."""
        if self.tipo != 'TALLER':
            return False
        return (self.cupos_disponibles or 0) <= 0

    def recalcular_cupos(self, inscritos_override=None):
        """
        [REFACTOR] Recalcula cupos_disponibles según las inscripciones actuales.

        - TALLER: cupos_disponibles = max(0, cupos_totales - inscritos)
        - MASIVA: cupos_totales y cupos_disponibles = None

        Parámetros:
            inscritos_override (int | None): si se pasa, usa ese número en vez
                de contar en BBDD. Útil al crear una actividad nueva (0).
        NO guarda en BBDD: el llamador debe hacer actividad.save().
        """
        if self.tipo == 'TALLER':
            if inscritos_override is not None:
                inscritos = inscritos_override
            elif self.pk:
                inscritos = self.inscripciones.count()
            else:
                inscritos = 0
            self.cupos_disponibles = max(0, (self.cupos_totales or 0) - inscritos)
        else:
            self.cupos_totales = None
            self.cupos_disponibles = None


# ==================== MODELOS TRANSACCIONALES ====================

class Inscripcion(models.Model):
    ESTADO_CHOICES = [
        ('CONFIRMADA', 'Confirmada'),
        ('CANCELADA', 'Cancelada'),
        ('LISTA_ESPERA', 'Lista de espera'),
    ]

    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='inscripciones')
    alumno = models.ForeignKey('Alumno', on_delete=models.CASCADE, related_name='inscripciones')
    fecha_inscripcion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='CONFIRMADA')

    class Meta:
        verbose_name = 'Inscripción'
        verbose_name_plural = 'Inscripciones'
        unique_together = ('actividad', 'alumno')
        ordering = ['-fecha_inscripcion']

    def __str__(self):
        return f"{self.alumno} - {self.actividad}"


class Asistencia(models.Model):
    METODO_CHOICES = [('RUT', 'RUT'), ('QR', 'Código QR'), ('CODIGO', 'Código de barras')]

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='asistencias'
    )

    alumno = models.ForeignKey(
        'Alumno',
        on_delete=models.CASCADE,
        related_name='asistencias'
    )

    fecha_ingreso = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    metodo_ingreso = models.CharField(
        max_length=10,
        choices=METODO_CHOICES
    )

    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asistencias_registradas'
    )

    class Meta:
        verbose_name = 'Asistencia'
        verbose_name_plural = 'Asistencias'
        ordering = ['-fecha_ingreso']
        constraints = [
            models.UniqueConstraint(
                fields=['actividad', 'alumno'],
                name='unique_asistencia_actividad_alumno'
            )
        ]

    def __str__(self):
        return f'{self.alumno} - {self.actividad}'


class NotificacionCorreo(models.Model):
    ESTADO_CHOICES = [('EXITO', 'Éxito'), ('FALLO', 'Fallo')]

    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name='notificaciones'
    )

    alumno = models.ForeignKey(
        'Alumno',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notificaciones'
    )

    filtro_aplicado = models.CharField(
        max_length=2000,
        blank=True
    )

    fecha_envio = models.DateTimeField(auto_now_add=True)

    estado_envio = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES
    )

    class Meta:
        verbose_name = 'Notificación de correo'
        verbose_name_plural = 'Notificaciones de correo'
        ordering = ['-fecha_envio']

    def __str__(self):
        return f'{self.actividad} - {self.estado_envio}'


class LogAuditoria(models.Model):
    usuario_sistema = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='logs_auditoria')
    accion = models.CharField(max_length=200)
    detalle = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    modulo = models.CharField(max_length=50, blank=True, null=True)
    objeto_tipo = models.CharField(max_length=50, blank=True, null=True)
    objeto_id = models.IntegerField(null=True, blank=True)
    objeto_nombre = models.CharField(max_length=200, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    cambios_json = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Log de auditoría'
        verbose_name_plural = 'Logs de auditoría'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.usuario_sistema} - {self.accion}"