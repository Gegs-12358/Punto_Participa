from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.contrib.auth.models import User
from .utils import limpiar_texto, normalizar_documento


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

    def save(self, *args, **kwargs):
        self.rut = normalizar_documento(self.rut) or None
        super().save(*args, **kwargs)


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
    activo = models.BooleanField(default=True, db_index=True, verbose_name='Activo')
    # Bloqueo hecho a mano por el Administrador (pantalla Alumnos). La nómina lo respeta:
    # aunque el alumno venga en el archivo, sigue bloqueado hasta que se desbloquee a mano.
    # Un alumno con activo=False y bloqueo_manual=False fue bloqueado por no venir en la nómina.
    bloqueo_manual = models.BooleanField(default=False, verbose_name='Bloqueado a mano')
    motivo_bloqueo = models.CharField(max_length=200, blank=True, default='',
                                      verbose_name='Motivo del bloqueo')

    class Meta:
        verbose_name = 'Alumno'
        verbose_name_plural = 'Alumnos'
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"

    @property
    def estado(self):
        """'activo', 'manual' (bloqueado a mano) o 'nomina' (no vino en la última nómina)."""
        if self.activo:
            return 'activo'
        return 'manual' if self.bloqueo_manual else 'nomina'

    def save(self, *args, **kwargs):
        # Red de seguridad: cubre admin, importador y objects.create().
        # OJO: .update() y bulk_create() NO pasan por aquí; limpiar antes.
        self.nombres = limpiar_texto(self.nombres)
        self.apellidos = limpiar_texto(self.apellidos)
        self.carrera = limpiar_texto(self.carrera)
        self.jornada = limpiar_texto(self.jornada) 
        self.correo = limpiar_texto(self.correo)
        self.rut = normalizar_documento(self.rut) or None  # '' -> None (evita choque de unique)
        super().save(*args, **kwargs)


class Escuela(models.Model):
    """
    Catálogo de escuelas. Carrera.escuela guarda el NOMBRE de la escuela (texto), que es
    lo que usan los reportes, los filtros y los colores; este catálogo solo controla qué
    escuelas existen y cuáles están activas.
    """
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True, db_index=True)
    # Color de la escuela en los gráficos ("#307FE2"). Vacío: se usa el color oficial
    # conocido por nombre (views.COLOR_POR_ESCUELA) o gris.
    color = models.CharField(
        max_length=7, blank=True, default='',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Usa un color como #307FE2.')],
    )

    class Meta:
        verbose_name = 'Escuela'
        verbose_name_plural = 'Escuelas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Carrera(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    escuela = models.CharField(max_length=100, blank=True, null=True)
    # Bloqueada: deja de ofrecerse al crear actividades, pero conserva su historial
    activo = models.BooleanField(default=True, db_index=True)

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


class Lugar(models.Model):
    """
    Catálogo de lugares donde se realizan las actividades.

    Actividad.lugar guarda el NOMBRE del lugar (texto), igual que Alumno.carrera
    guarda el nombre de la carrera. El formulario de actividad solo ofrece los
    lugares activos de este catálogo, así todas las actividades quedan escritas
    igual y el filtro por lugar funciona.
    """
    nombre = models.CharField(max_length=200, unique=True)
    activo = models.BooleanField(default=True, db_index=True)
    # Si está marcado (por ejemplo "Sala"), al crear la actividad se pide el número
    # de la sala, que se guarda aparte en Actividad.lugar_numero.
    pide_numero = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Lugar'
        verbose_name_plural = 'Lugares'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Actividad(models.Model):
    # INVITACION: solo entran los alumnos de una lista cargada desde Excel o CSV, cada uno
    # con hasta `acompanantes_por_invitado` acompañantes (ver Invitado y Acompanante).
    TIPO_CHOICES = [('MASIVA', 'Masiva'), ('TALLER', 'Taller'), ('INVITACION', 'Con invitación')]
    MAX_ACOMPANANTES = 10
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada')
    ] 

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    lugar = models.CharField(max_length=200)
    # Número de sala cuando el lugar lo pide ("102", "1203"). Vacío en los demás lugares.
    lugar_numero = models.CharField(max_length=10, blank=True, default='')
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
    # Solo actividades con invitación: cuántos acompañantes puede registrar cada invitado
    acompanantes_por_invitado = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(MAX_ACOMPANANTES)],
        verbose_name='Acompañantes por invitado')

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
    def lugar_completo(self):
        """Lugar tal como se muestra: "Sala 102", o solo "Auditorio Principal"."""
        return f'{self.lugar} {self.lugar_numero}'.strip()

    @property
    def esta_activa(self):
        return self.estado == 'ACTIVA'

    @property
    def es_taller(self):
        return self.tipo == 'TALLER'

    @property
    def es_con_invitacion(self):
        return self.tipo == 'INVITACION'

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

def foto_academica(alumno):
    """
    Carrera, escuela y jornada que tiene el alumno AHORA, como textos.
    La escuela se busca en el catálogo de carreras (sin distinguir mayúsculas);
    si la carrera no está en el catálogo, queda vacía.
    """
    carrera = limpiar_texto(alumno.carrera or '')[:100]
    jornada = limpiar_texto(alumno.jornada or '')[:20]
    escuela = ''
    if carrera:
        escuela = (Carrera.objects.filter(nombre__iexact=carrera)
                   .values_list('escuela', flat=True).first() or '')
    return {'carrera': carrera, 'escuela': escuela[:100], 'jornada': jornada}


class FotoAcademica(models.Model):
    """
    "Foto" de la carrera, escuela y jornada del alumno en el momento de inscribirse
    o de registrar su asistencia. Los reportes usan estos campos, así el historial no
    cambia si después el alumno se cambia de carrera, llega una nómina nueva o se
    renombra una carrera.

    Se llenan solos al crear el registro (objects.create pasa por save()).
    OJO: bulk_create() NO pasa por save(); quien lo use debe llenarlos con foto_academica().
    """
    carrera = models.CharField(max_length=100, blank=True, default='',
                               verbose_name='Carrera (en ese momento)')
    escuela = models.CharField(max_length=100, blank=True, default='',
                               verbose_name='Escuela (en ese momento)')
    jornada = models.CharField(max_length=20, blank=True, default='',
                               verbose_name='Jornada (en ese momento)')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self._state.adding and self.alumno_id and not (self.carrera or self.jornada):
            for campo, valor in foto_academica(self.alumno).items():
                setattr(self, campo, valor)
        super().save(*args, **kwargs)


class Inscripcion(FotoAcademica):
    ESTADO_CHOICES = [
        ('CONFIRMADA', 'Confirmada'),
        ('CANCELADA', 'Cancelada'),
        ('LISTA_ESPERA', 'Lista de espera'),
    ]

    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='inscripciones')
    alumno = models.ForeignKey('Alumno', on_delete=models.CASCADE, related_name='inscripciones')
    fecha_inscripcion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='CONFIRMADA')
    # Enlace personal para cancelar (/inscripcion/cancelar/<token>/), llega en el correo de confirmación
    token = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)

    class Meta:
        verbose_name = 'Inscripción'
        verbose_name_plural = 'Inscripciones'
        unique_together = ('actividad', 'alumno')
        ordering = ['-fecha_inscripcion']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = _token_invitacion()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alumno} - {self.actividad}"


class InscripcionCancelada(FotoAcademica):
    """
    Historial de inscripciones canceladas. Al cancelar, la fila sale de Inscripcion y queda aquí,
    así los conteos de inscritos, el escáner y los reportes no cambian, y el alumno puede volver a
    inscribirse si hay cupo. cancelada_por vacío = la canceló el alumno con su enlace.
    """
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='cancelaciones')
    alumno = models.ForeignKey('Alumno', on_delete=models.CASCADE, related_name='cancelaciones')
    token = models.CharField(max_length=40, blank=True, db_index=True)
    fecha_inscripcion = models.DateTimeField(null=True, blank=True)
    fecha_cancelacion = models.DateTimeField(auto_now_add=True)
    cancelada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='cancelaciones_registradas')

    class Meta:
        verbose_name = 'Inscripción cancelada'
        verbose_name_plural = 'Inscripciones canceladas'
        ordering = ['-fecha_cancelacion']

    def __str__(self):
        return f"{self.alumno} - {self.actividad} (cancelada)"


class Asistencia(FotoAcademica):
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

    # Solo en actividades con invitación: a qué invitado de la lista se le escribió
    invitado = models.ForeignKey(
        'Invitado',
        on_delete=models.SET_NULL,
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


def _token_invitacion():
    import secrets
    return secrets.token_urlsafe(24)


class Invitado(models.Model):
    """
    Alumno invitado a una actividad con invitación. Los datos (nombre, carrera, correo)
    vienen de la lista que cargó el Punto, no de la nómina: la invitación se envía a ESE
    correo. Si el documento está en la nómina, se enlaza con el alumno (historial y reportes).

    El enlace personal de respuesta usa `token`. La asistencia se guarda aquí (también para
    quien no está en la nómina); a los que sí están se les crea además su Asistencia.
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Sin responder'),
        ('CONFIRMADO', 'Confirmó'),
        ('RECHAZADO', 'No asistirá'),
    ]

    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='invitados')
    alumno = models.ForeignKey(Alumno, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='invitaciones')
    rut = models.CharField(max_length=30, verbose_name='Documento')     # normalizado
    nombre = models.CharField(max_length=200)
    correo = models.EmailField()
    carrera = models.CharField(max_length=100, blank=True, default='')
    escuela = models.CharField(max_length=100, blank=True, default='')
    jornada = models.CharField(max_length=20, blank=True, default='')
    token = models.CharField(max_length=64, unique=True, default=_token_invitacion, editable=False)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='PENDIENTE', db_index=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)
    agregado_en_entrada = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Último envío exitoso de la invitación por correo (vacío: nunca se le envió)
    invitacion_enviada = models.DateTimeField(null=True, blank=True)
    ingreso = models.DateTimeField(null=True, blank=True)
    metodo_ingreso = models.CharField(max_length=10, blank=True, default='')
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+')

    class Meta:
        verbose_name = 'Invitado'
        verbose_name_plural = 'Invitados'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['actividad', 'rut'], name='unico_invitado_por_actividad'),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.actividad})'

    def save(self, *args, **kwargs):
        self.rut = normalizar_documento(self.rut) or ''
        self.nombre = limpiar_texto(self.nombre)
        self.correo = limpiar_texto(self.correo)
        super().save(*args, **kwargs)


class Acompanante(models.Model):
    """Acompañante de un invitado: lo registra el alumno al responder (o se agrega en la
    entrada) y entra escaneando su propio documento."""
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='acompanantes')
    invitado = models.ForeignKey(Invitado, on_delete=models.CASCADE, related_name='acompanantes')
    rut = models.CharField(max_length=30, verbose_name='Documento')     # normalizado
    nombre = models.CharField(max_length=200)
    agregado_en_entrada = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    ingreso = models.DateTimeField(null=True, blank=True)
    metodo_ingreso = models.CharField(max_length=10, blank=True, default='')
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+')

    class Meta:
        verbose_name = 'Acompañante'
        verbose_name_plural = 'Acompañantes'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['actividad', 'rut'], name='unico_acompanante_por_actividad'),
        ]

    def __str__(self):
        return f'{self.nombre} (acompaña a {self.invitado.nombre})'

    def save(self, *args, **kwargs):
        self.rut = normalizar_documento(self.rut) or ''
        self.nombre = limpiar_texto(self.nombre)
        if not self.actividad_id and self.invitado_id:
            self.actividad_id = self.invitado.actividad_id
        super().save(*args, **kwargs)


class TurnoEscaneo(models.Model):
    """
    Turno de un operador en el escáner (P2): empieza al elegir la actividad y termina con
    "Finalizar turno" o al cambiar de actividad. Sirve para mostrar quién está registrando
    ahora en una actividad, aunque todavía no haya registrado a nadie.
    Un turno que nadie cerró (se cerró el navegador) deja de contar como abierto después de
    HORAS_MAXIMAS.
    """
    HORAS_MAXIMAS = 12

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='turnos_escaneo')
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='turnos_escaneo')
    inicio = models.DateTimeField(auto_now_add=True, db_index=True)
    fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Turno de escaneo'
        verbose_name_plural = 'Turnos de escaneo'
        ordering = ['-inicio']
        indexes = [models.Index(fields=['actividad', 'fin'])]

    def __str__(self):
        return f'{self.usuario} en {self.actividad} ({self.inicio:%d/%m/%Y %H:%M})'

    @classmethod
    def abiertos(cls, actividad):
        from datetime import timedelta
        from django.utils import timezone
        limite = timezone.now() - timedelta(hours=cls.HORAS_MAXIMAS)
        return cls.objects.filter(actividad=actividad, fin__isnull=True, inicio__gte=limite)


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