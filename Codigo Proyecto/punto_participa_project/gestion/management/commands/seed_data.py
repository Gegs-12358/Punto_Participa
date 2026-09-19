# gestion/management/commands/seed_data.py

"""
Management command para poblar la base de datos con datos de prueba.

Uso:
    python manage.py seed_data                # puebla sin borrar
    python manage.py seed_data --flush        # borra todo y puebla
    python manage.py seed_data --flush --alumnos-por-carrera 10 --actividades 30

IMPORTANTE:
- Los correos usan @example.com (nunca llegan a ningún lado).
- Las fechas son relativas a NOW(): 90 días atrás -> 30 días adelante.
- Es idempotente: si lo corres dos veces sin --flush, no duplica datos.
"""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from gestion.models import (
    Actividad,
    Alumno,
    Asistencia,
    Carrera,
    Inscripcion,
    Jornada,
    LogAuditoria,
    NotificacionCorreo,
    Rol,
    UsuarioSistema,
)


# ============================================================
# CONSTANTES
# ============================================================

CARRERAS_POR_ESCUELA = {
    'Escuela de Construcción': [
        'Técnico Modelador Proyectista',
        'Conservación y Restauración del Patrimonio',
        'Ingeniería en Construcción',
        'Ingeniería en Prevención de Riesgos',
        'Técnico en Construcción',
        'Técnico Topógrafo Geomático',
    ],
    'Escuela de Informática y Telecomunicaciones': [
        'Ingeniería en Informática',
    ],
    'Escuela de Administración y Negocios': [
        'Ingeniería en Marketing Digital',
        'Auditoría',
        'Ingeniería en Gestión Logística',
        'Ingeniería en Comercio Exterior',
        'Ingeniería en Administración Mención Gestión de Personas',
        'Ingeniería en Administración Mención Finanzas',
    ],
}

JORNADAS = ['Diurna', 'Vespertina']

ROLES = ['Administrador', 'Creador de Evento', 'Encargado de Registrar']

PROBABILIDAD_DIURNA = 0.6

NOMBRES_M = [
    'Juan', 'José', 'Luis', 'Carlos', 'Pedro', 'Diego', 'Felipe', 'Matías',
    'Sebastián', 'Cristóbal', 'Ignacio', 'Vicente', 'Benjamín', 'Tomás',
    'Joaquín', 'Andrés', 'Gabriel', 'Daniel', 'Alejandro', 'Rodrigo',
    'Fabián', 'Marcelo', 'Pablo', 'Álvaro', 'Esteban',
]

NOMBRES_F = [
    'María', 'Camila', 'Javiera', 'Constanza', 'Valentina', 'Antonia',
    'Catalina', 'Fernanda', 'Isidora', 'Josefa', 'Florencia', 'Amanda',
    'Martina', 'Sofía', 'Emilia', 'Trinidad', 'Rocío', 'Daniela',
    'Carolina', 'Francisca', 'Andrea', 'Paulina', 'Verónica', 'Claudia',
    'Bárbara',
]

APELLIDOS = [
    'González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Contreras',
    'Silva', 'Martínez', 'Sepúlveda', 'Morales', 'Rodríguez', 'López',
    'Fuentes', 'Hernández', 'Torres', 'Araya', 'Flores', 'Espinoza',
    'Valenzuela', 'Castillo', 'Tapia', 'Reyes', 'Gutiérrez', 'Castro',
    'Pizarro', 'Álvarez', 'Vásquez', 'Sánchez', 'Fernández', 'Ramírez',
    'Carrasco', 'Núñez', 'Jara', 'Vergara', 'Riquelme', 'Salazar',
    'Godoy', 'Bravo', 'Herrera', 'Medina', 'Vega', 'Miranda', 'Campos',
]


# ============================================================
# HELPERS
# ============================================================

def calcular_dv(cuerpo):
    """Calcula el dígito verificador de un RUT chileno."""
    suma = 0
    multiplicador = 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * multiplicador
        multiplicador += 1
        if multiplicador > 7:
            multiplicador = 2
    resto = suma % 11
    dv = 11 - resto
    if dv == 11:
        return '0'
    if dv == 10:
        return 'K'
    return str(dv)


def generar_rut(cuerpo):
    """Devuelve un RUT con formato 12345678-9."""
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


def normalizar_para_correo(texto):
    """Convierte 'José' -> 'jose', 'Muñoz' -> 'munoz'."""
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
    }
    for orig, dest in reemplazos.items():
        texto = texto.replace(orig, dest)
    return texto.lower().replace(' ', '')


def elegir_jornada():
    """60% Diurna, 40% Vespertina."""
    return 'Diurna' if random.random() < PROBABILIDAD_DIURNA else 'Vespertina'


# ============================================================
# MANAGEMENT COMMAND
# ============================================================

class Command(BaseCommand):
    help = 'Puebla la base de datos con datos de prueba realistas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Borra todos los datos del seed antes de poblar.',
        )
        parser.add_argument(
            '--alumnos-por-carrera',
            type=int,
            default=5,
            help='Cantidad de alumnos por carrera (default: 5).',
        )
        parser.add_argument(
            '--actividades',
            type=int,
            default=20,
            help='Cantidad de actividades a crear (default: 20).',
        )

    def handle(self, *args, **options):
        self.alumnos_por_carrera = options['alumnos_por_carrera']
        self.total_actividades = options['actividades']
        self.flush = options['flush']

        random.seed(42)

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING(
            '  SEED DATA - Punto Participa'
        ))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))

        if self.flush:
            self.stdout.write(self.style.WARNING(
                '\n[1/9] Borrando datos existentes...'
            ))
            self._flush_datos()
        else:
            self.stdout.write(self.style.NOTICE(
                '\n[1/9] Sin --flush. Se respetarán datos existentes.'
            ))

        with transaction.atomic():
            self.stdout.write('\n[2/9] Creando roles...')
            self.roles = self._crear_roles()

            self.stdout.write('[3/9] Creando usuarios del sistema...')
            self.usuarios_sistema = self._crear_usuarios()

            self.stdout.write('[4/9] Creando carreras y jornadas...')
            self.carreras = self._crear_carreras()
            self.jornadas = self._crear_jornadas()

            self.stdout.write('[5/9] Creando alumnos...')
            self.alumnos = self._crear_alumnos()

            self.stdout.write('[6/9] Creando actividades...')
            self.actividades = self._crear_actividades()

            self.stdout.write('[7/9] Creando inscripciones y asistencias...')
            self._crear_inscripciones_y_asistencias()

            self.stdout.write('[8/9] Creando notificaciones de correo...')
            self._crear_notificaciones()

            self.stdout.write('[9/9] Creando logs de auditoría...')
            self._crear_logs()

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('  SEED COMPLETADO EXITOSAMENTE'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self._imprimir_resumen()

    # ============================================================
    # FLUSH
    # ============================================================

    def _flush_datos(self):
        usernames_seed = ['admin', 'creador1', 'creador2',
                          'registrador1', 'registrador2']

        LogAuditoria.objects.all().delete()
        NotificacionCorreo.objects.all().delete()
        Asistencia.objects.all().delete()
        Inscripcion.objects.all().delete()
        Actividad.objects.all().delete()
        Alumno.objects.all().delete()

        UsuarioSistema.objects.filter(
            user__username__in=usernames_seed
        ).delete()
        User.objects.filter(username__in=usernames_seed).delete()

        Carrera.objects.all().delete()
        Jornada.objects.all().delete()

        self.stdout.write(self.style.WARNING(
            '       Datos del seed eliminados.'
        ))

    # ============================================================
    # ROLES
    # ============================================================

    def _crear_roles(self):
        roles = {}
        for nombre in ROLES:
            rol, created = Rol.objects.get_or_create(nombre=nombre)
            roles[nombre] = rol
            if created:
                self.stdout.write(f'       + Rol: {nombre}')
        return roles

    # ============================================================
    # USUARIOS DEL SISTEMA
    # ============================================================

    def _crear_usuarios(self):
        definiciones = [
            {
                'username': 'admin',
                'first_name': 'Administrador',
                'last_name': 'del Sistema',
                'email': 'admin@example.com',
                'password': 'admin12345',
                'rol': 'Administrador',
                'rut': '11111111-1',
                'is_superuser': True,
                'is_staff': True,
            },
            {
                'username': 'creador1',
                'first_name': 'Patricia',
                'last_name': 'Fuentes Rojas',
                'email': 'creador1@example.com',
                'password': 'creador12345',
                'rol': 'Creador de Evento',
                'rut': '12222222-2',
                'is_superuser': False,
                'is_staff': False,
            },
            {
                'username': 'creador2',
                'first_name': 'Rodrigo',
                'last_name': 'Salinas Vega',
                'email': 'creador2@example.com',
                'password': 'creador12345',
                'rol': 'Creador de Evento',
                'rut': '13333333-3',
                'is_superuser': False,
                'is_staff': False,
            },
            {
                'username': 'registrador1',
                'first_name': 'Camila',
                'last_name': 'Herrera Soto',
                'email': 'registrador1@example.com',
                'password': 'reg12345',
                'rol': 'Encargado de Registrar',
                'rut': '14444444-4',
                'is_superuser': False,
                'is_staff': False,
            },
            {
                'username': 'registrador2',
                'first_name': 'Matías',
                'last_name': 'Contreras Díaz',
                'email': 'registrador2@example.com',
                'password': 'reg12345',
                'rol': 'Encargado de Registrar',
                'rut': '15555555-5',
                'is_superuser': False,
                'is_staff': False,
            },
        ]

        usuarios = {}
        for datos in definiciones:
            user, created = User.objects.get_or_create(
                username=datos['username'],
                defaults={
                    'first_name': datos['first_name'],
                    'last_name': datos['last_name'],
                    'email': datos['email'],
                    'is_superuser': datos['is_superuser'],
                    'is_staff': datos['is_staff'],
                    'is_active': True,
                }
            )

            if created:
                user.set_password(datos['password'])
                user.save()

            perfil, _ = UsuarioSistema.objects.get_or_create(
                user=user,
                defaults={
                    'rut': datos['rut'],
                    'rol': self.roles[datos['rol']],
                    'activo': True,
                    'must_change_password': False,
                }
            )
            if perfil.must_change_password:
                perfil.must_change_password = False
                perfil.save(update_fields=['must_change_password'])

            usuarios[datos['username']] = user
            if created:
                self.stdout.write(
                    f'       + Usuario: {datos["username"]} ({datos["rol"]})'
                )

        return usuarios

    # ============================================================
    # CARRERAS Y JORNADAS
    # ============================================================

    def _crear_carreras(self):
        carreras = []
        for escuela, nombres in CARRERAS_POR_ESCUELA.items():
            for nombre in nombres:
                carrera, created = Carrera.objects.get_or_create(
                    nombre=nombre,
                    defaults={'escuela': escuela}
                )
                carreras.append(carrera)
                if created:
                    self.stdout.write(f'       + Carrera: {nombre}')
        return carreras

    def _crear_jornadas(self):
        jornadas = []
        for nombre in JORNADAS:
            jornada, created = Jornada.objects.get_or_create(nombre=nombre)
            jornadas.append(jornada)
            if created:
                self.stdout.write(f'       + Jornada: {nombre}')
        return jornadas

    # ============================================================
    # ALUMNOS
    # ============================================================

    def _crear_alumnos(self):
        alumnos = []
        rut_actual = 20000000

        for carrera in self.carreras:
            for i in range(self.alumnos_por_carrera):
                if random.random() < 0.5:
                    nombres_pool = NOMBRES_M
                else:
                    nombres_pool = NOMBRES_F

                nombre = random.choice(nombres_pool)
                apellido1 = random.choice(APELLIDOS)
                apellido2 = random.choice(APELLIDOS)

                rut_actual += random.randint(1, 50)
                rut = generar_rut(rut_actual)

                correo_base = (
                    f'{normalizar_para_correo(nombre)}.'
                    f'{normalizar_para_correo(apellido1)}'
                    f'{rut_actual}'
                )
                correo = f'{correo_base}@example.com'

                jornada = elegir_jornada()

                alumno, created = Alumno.objects.get_or_create(
                    rut=rut,
                    defaults={
                        'tipo_documento': 'RUT',
                        'nombres': nombre,
                        'apellidos': f'{apellido1} {apellido2}',
                        'correo': correo,
                        'carrera': carrera.nombre,
                        'jornada': jornada,
                    }
                )
                alumnos.append(alumno)

            self.stdout.write(
                f'       + {self.alumnos_por_carrera} alumnos en '
                f'{carrera.nombre[:40]}'
            )

        self.stdout.write(
            self.style.SUCCESS(f'       Total alumnos: {len(alumnos)}')
        )
        return alumnos

    # ============================================================
    # ACTIVIDADES
    # ============================================================

    def _crear_actividades(self):
        ahora = timezone.now()
        actividades = []

        plantillas = [
            ('Taller de Liderazgo y Trabajo en Equipo', 'TALLER',
             'Sala 201 - Edificio A', None),
            ('Charla de Emprendimiento e Innovación', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Comunicación Efectiva', 'TALLER',
             'Sala 105 - Edificio B', None),
            ('Feria de Salud Estudiantil', 'MASIVA',
             'Patio Central', None),
            ('Charla de Inserción Laboral', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Construcción Sustentable', 'TALLER',
             'Laboratorio de Construcción',
             ['Escuela de Construcción']),
            ('Charla de Ciberseguridad', 'MASIVA',
             'Auditorio de Informática',
             ['Escuela de Informática y Telecomunicaciones']),
            ('Taller de Marketing Digital Aplicado', 'TALLER',
             'Sala 301 - Edificio C',
             ['Escuela de Administración y Negocios']),
            ('Charla de Finanzas Personales', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Prevención de Riesgos Laborales', 'TALLER',
             'Laboratorio de Seguridad',
             ['Escuela de Construcción']),
            ('Charla de Innovación Tecnológica', 'MASIVA',
             'Auditorio de Informática',
             ['Escuela de Informática y Telecomunicaciones']),
            ('Feria de Emprendimiento Estudiantil', 'MASIVA',
             'Patio Central', None),
            ('Taller de Oratoria y Presentaciones', 'TALLER',
             'Sala 202 - Edificio A', None),
            ('Charla de Diversidad e Inclusión', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Gestión de Proyectos', 'TALLER',
             'Sala 401 - Edificio C',
             ['Escuela de Administración y Negocios']),
            ('Charla de Sostenibilidad Ambiental', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Topografía con Drones', 'TALLER',
             'Laboratorio de Topografía',
             ['Escuela de Construcción']),
            ('Charla de Transformación Digital', 'MASIVA',
             'Auditorio de Informática',
             ['Escuela de Informática y Telecomunicaciones']),
            ('Taller de Atención al Cliente', 'TALLER',
             'Sala 302 - Edificio C',
             ['Escuela de Administración y Negocios']),
            ('Charla de Salud Mental Estudiantil', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Análisis de Datos', 'TALLER',
             'Laboratorio de Computación', None),
            ('Charla de Ética Profesional', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Metodologías Ágiles', 'TALLER',
             'Sala 203 - Edificio A', None),
            ('Charla de Ciudadanía Digital', 'MASIVA',
             'Auditorio Principal', None),
            ('Taller de Primeros Auxilios', 'TALLER',
             'Laboratorio de Salud', None),
        ]

        total = min(self.total_actividades, len(plantillas))

        for i in range(total):
            titulo, tipo, lugar, escuelas_destino = plantillas[i]

            dias_offset = random.randint(-90, 30)
            fecha_inicio = ahora + timedelta(days=dias_offset)
            fecha_inicio = fecha_inicio.replace(
                hour=random.randint(9, 18),
                minute=random.choice([0, 15, 30, 45]),
                second=0,
                microsecond=0,
            )

            duracion_horas = random.choice([2, 3, 4, 6, 8])
            fecha_fin = fecha_inicio + timedelta(hours=duracion_horas)

            if fecha_fin < ahora:
                estado = 'FINALIZADA'
            else:
                estado = 'ACTIVA'

            if i == total - 1 and estado == 'FINALIZADA':
                estado = 'CANCELADA'

            if tipo == 'TALLER':
                cupos_totales = random.choice([15, 20, 25, 30, 40])
                cupos_disponibles = cupos_totales
            else:
                cupos_totales = None
                cupos_disponibles = None

            fecha_creacion = fecha_inicio - timedelta(
                days=random.randint(5, 15),
                hours=random.randint(0, 8),
            )

            creador = random.choice(
                [self.usuarios_sistema['creador1'],
                 self.usuarios_sistema['creador2']]
            )

            descripcion = (
                f'{titulo}. Actividad organizada por la institución '
                f'para complementar la formación de los estudiantes. '
                f'Cupos limitados según disponibilidad.'
            )

            actividad = Actividad.objects.create(
                titulo=titulo,
                descripcion=descripcion,
                tipo=tipo,
                lugar=lugar,
                cupos_totales=cupos_totales,
                cupos_disponibles=cupos_disponibles,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                estado=estado,
                creado_por=creador,
            )

            Actividad.objects.filter(pk=actividad.pk).update(
                fecha_creacion=fecha_creacion
            )

            if escuelas_destino:
                carreras_filtradas = [
                    c for c in self.carreras
                    if c.escuela in escuelas_destino
                ]
                actividad.carreras.set(carreras_filtradas)
            else:
                actividad.carreras.set(self.carreras)

            if i % 7 == 0:
                jornadas_act = [
                    j for j in self.jornadas if j.nombre == 'Diurna'
                ]
            elif i % 7 == 3:
                jornadas_act = [
                    j for j in self.jornadas if j.nombre == 'Vespertina'
                ]
            else:
                jornadas_act = self.jornadas
            actividad.jornadas.set(jornadas_act)

            actividades.append(actividad)

        talleres = sum(1 for a in actividades if a.tipo == 'TALLER')
        masivas = sum(1 for a in actividades if a.tipo == 'MASIVA')
        self.stdout.write(
            self.style.SUCCESS(
                f'       Total actividades: {len(actividades)} '
                f'({talleres} talleres, {masivas} masivas)'
            )
        )
        return actividades

    # ============================================================
    # INSCRIPCIONES Y ASISTENCIAS
    # ============================================================

    def _crear_inscripciones_y_asistencias(self):
        ahora = timezone.now()
        registradores = [
            self.usuarios_sistema['registrador1'],
            self.usuarios_sistema['registrador2'],
            self.usuarios_sistema['admin'],
        ]

        talleres = [a for a in self.actividades if a.tipo == 'TALLER']
        masivas = [a for a in self.actividades if a.tipo == 'MASIVA']

        total_inscripciones = 0
        total_asistencias = 0

        for idx, actividad in enumerate(talleres):
            if idx == len(talleres) - 1:
                self.stdout.write(
                    f'       [caso borde] Taller sin inscritos: '
                    f'{actividad.titulo[:40]}'
                )
                continue

            elegibles = self._alumnos_elegibles(actividad)
            if not elegibles:
                continue

            cupo_max = actividad.cupos_totales or 25
            n_inscritos = min(
                random.randint(5, 25),
                len(elegibles),
                cupo_max,
            )
            inscritos = random.sample(elegibles, n_inscritos)

            for alumno in inscritos:
                fecha_insc = actividad.fecha_inicio - timedelta(
                    days=random.randint(1, 30),
                    hours=random.randint(0, 12),
                )
                if fecha_insc > ahora:
                    fecha_insc = ahora - timedelta(hours=1)

                inscripcion = Inscripcion.objects.create(
                    actividad=actividad,
                    alumno=alumno,
                    estado='CONFIRMADA',
                )
                Inscripcion.objects.filter(pk=inscripcion.pk).update(
                    fecha_inscripcion=fecha_insc
                )
                total_inscripciones += 1

            actividad.cupos_disponibles = max(0, cupo_max - n_inscritos)
            actividad.save(update_fields=['cupos_disponibles'])

            if actividad.fecha_inicio > ahora:
                continue

            tasa = random.uniform(0.70, 0.90)
            n_asistentes = int(n_inscritos * tasa)
            asistentes = random.sample(inscritos, n_asistentes)

            for alumno in asistentes:
                self._crear_asistencia(
                    actividad, alumno, registradores, ahora
                )
                total_asistencias += 1

        for idx, actividad in enumerate(masivas):
            if idx == len(masivas) - 1:
                self.stdout.write(
                    f'       [caso borde] Masiva sin asistentes: '
                    f'{actividad.titulo[:40]}'
                )
                continue

            if actividad.fecha_inicio > ahora:
                continue

            elegibles = self._alumnos_elegibles(actividad)
            if not elegibles:
                continue

            n_asistentes = min(random.randint(10, 40), len(elegibles))
            asistentes = random.sample(elegibles, n_asistentes)

            for alumno in asistentes:
                self._crear_asistencia(
                    actividad, alumno, registradores, ahora
                )
                total_asistencias += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'       Total inscripciones: {total_inscripciones}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'       Total asistencias: {total_asistencias}'
            )
        )

    def _alumnos_elegibles(self, actividad):
        carreras_nombres = list(
            actividad.carreras.values_list('nombre', flat=True)
        )
        jornadas_nombres = list(
            actividad.jornadas.values_list('nombre', flat=True)
        )

        qs = Alumno.objects.all()
        if carreras_nombres:
            qs = qs.filter(carrera__in=carreras_nombres)
        if jornadas_nombres:
            qs = qs.filter(jornada__in=jornadas_nombres)

        return list(qs)

    def _crear_asistencia(self, actividad, alumno, registradores, ahora):
        duracion = actividad.fecha_fin - actividad.fecha_inicio
        if duracion.total_seconds() > 0:
            offset = timedelta(
                seconds=random.randint(0, int(duracion.total_seconds()))
            )
            fecha_ingreso = actividad.fecha_inicio + offset
        else:
            fecha_ingreso = actividad.fecha_inicio

        if fecha_ingreso > ahora:
            fecha_ingreso = ahora - timedelta(minutes=random.randint(1, 60))

        metodo = random.choice(['RUT', 'QR', 'CODIGO'])
        registrador = random.choice(registradores)

        asistencia = Asistencia.objects.create(
            actividad=actividad,
            alumno=alumno,
            metodo_ingreso=metodo,
            registrado_por=registrador,
        )
        Asistencia.objects.filter(pk=asistencia.pk).update(
            fecha_ingreso=fecha_ingreso
        )

    # ============================================================
    # NOTIFICACIONES DE CORREO
    # ============================================================

    def _crear_notificaciones(self):
        ahora = timezone.now()
        talleres = [a for a in self.actividades if a.tipo == 'TALLER']

        if not talleres:
            return

        cantidad = random.randint(5, 10)
        notificaciones_creadas = 0

        for _ in range(cantidad):
            actividad = random.choice(talleres)

            elegibles = self._alumnos_elegibles(actividad)
            if not elegibles:
                continue

            alumno = random.choice(elegibles)

            carreras_txt = ', '.join(
                actividad.carreras.values_list('nombre', flat=True)[:3]
            )
            jornadas_txt = ', '.join(
                actividad.jornadas.values_list('nombre', flat=True)
            )
            filtro_aplicado = (
                f'Carreras: {carreras_txt or "Todas"} | '
                f'Jornadas: {jornadas_txt or "Todas"}'
            )

            estado = 'EXITO' if random.random() < 0.8 else 'FALLO'

            fecha_envio = actividad.fecha_inicio - timedelta(
                days=random.randint(1, 20),
                hours=random.randint(0, 12),
            )
            if fecha_envio > ahora:
                fecha_envio = ahora - timedelta(hours=random.randint(1, 48))

            notif = NotificacionCorreo.objects.create(
                actividad=actividad,
                alumno=alumno,
                filtro_aplicado=filtro_aplicado,
                estado_envio=estado,
            )
            NotificacionCorreo.objects.filter(pk=notif.pk).update(
                fecha_envio=fecha_envio
            )
            notificaciones_creadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'       Total notificaciones: {notificaciones_creadas}'
            )
        )

    # ============================================================
    # LOGS DE AUDITORÍA
    # ============================================================

    def _crear_logs(self):
        ahora = timezone.now()
        usuarios = list(self.usuarios_sistema.values())

        acciones = [
            ('Actividades', 'Crear Actividad',
             'Actividad "{titulo}" creada', 'Actividad'),
            ('Actividades', 'Edición de actividad',
             'Actividad "{titulo}" editada', 'Actividad'),
            ('Actividades', 'Envío de invitaciones',
             'Actividad "{titulo}": 15 exitosos, 2 fallidos', 'Actividad'),
            ('Inscripciones', 'Inscripción a taller',
             '{alumno} se inscribió en "{titulo}"', 'Alumno'),
            ('Escáner', 'Registro de asistencia',
             '{alumno} - {titulo}', 'Alumno'),
            ('Usuarios', 'Guardar usuario',
             'Usuario creado o actualizado', 'Usuario'),
            ('Seguridad', 'Cambio de contraseña',
             'Usuario cambió su contraseña', 'Usuario'),
        ]

        total_logs = 250
        logs_creados = 0

        for i in range(total_logs):
            modulo, accion, plantilla, obj_tipo = random.choice(acciones)
            usuario = random.choice(usuarios)

            actividad = random.choice(self.actividades)
            alumno = random.choice(self.alumnos)

            detalle = plantilla.format(
                titulo=actividad.titulo,
                alumno=f'{alumno.nombres} {alumno.apellidos}',
            )

            fecha = ahora - timedelta(
                days=random.randint(0, 90),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            log = LogAuditoria.objects.create(
                usuario_sistema=usuario,
                modulo=modulo,
                accion=accion,
                detalle=detalle,
                objeto_tipo=obj_tipo,
                objeto_id=(
                    actividad.id if obj_tipo == 'Actividad'
                    else alumno.id
                ),
                objeto_nombre=(
                    actividad.titulo if obj_tipo == 'Actividad'
                    else f'{alumno.nombres} {alumno.apellidos}'
                ),
                ip_address='127.0.0.1',
                user_agent='Seed/1.0',
            )
            LogAuditoria.objects.filter(pk=log.pk).update(
                fecha_registro=fecha
            )
            logs_creados += 1

        self.stdout.write(
            self.style.SUCCESS(f'       Total logs: {logs_creados}')
        )

    # ============================================================
    # RESUMEN FINAL
    # ============================================================

    def _imprimir_resumen(self):
        self.stdout.write('\n' + self.style.MIGRATE_HEADING('RESUMEN'))
        self.stdout.write(f'  Roles:              {Rol.objects.count()}')
        self.stdout.write(f'  Usuarios sistema:   {UsuarioSistema.objects.count()}')
        self.stdout.write(f'  Carreras:           {Carrera.objects.count()}')
        self.stdout.write(f'  Jornadas:           {Jornada.objects.count()}')
        self.stdout.write(f'  Alumnos:            {Alumno.objects.count()}')
        self.stdout.write(f'  Actividades:        {Actividad.objects.count()}')
        self.stdout.write(f'  Inscripciones:      {Inscripcion.objects.count()}')
        self.stdout.write(f'  Asistencias:        {Asistencia.objects.count()}')
        self.stdout.write(f'  Notificaciones:     {NotificacionCorreo.objects.count()}')
        self.stdout.write(f'  Logs auditoría:     {LogAuditoria.objects.count()}')

        self.stdout.write('\n' + self.style.MIGRATE_HEADING('CREDENCIALES'))
        self.stdout.write('  admin        / admin12345     (Administrador)')
        self.stdout.write('  creador1     / creador12345   (Creador de Evento)')
        self.stdout.write('  creador2     / creador12345   (Creador de Evento)')
        self.stdout.write('  registrador1 / reg12345       (Encargado de Registrar)')
        self.stdout.write('  registrador2 / reg12345       (Encargado de Registrar)')

        self.stdout.write('\n' + self.style.WARNING(
            '  AVISO: Correos @example.com NUNCA llegan a destino.'
        ))
        self.stdout.write('')