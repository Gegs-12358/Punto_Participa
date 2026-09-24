"""
Generador de datos sinteticos para pruebas de rendimiento.

Ejemplo:

    python manage.py perf_seed \
        --prefijo PRUEBA_ALAMEDA_20260922_ \
        --alumnos 1000 \
        --actividades 10 \
        --creator-username admin

Para limpiar:

    python manage.py perf_seed \
        --prefijo PRUEBA_ALAMEDA_20260922_ \
        --reset
"""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
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
)


class Command(BaseCommand):
    help = "Genera y limpia datos sinteticos con un prefijo controlado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefijo",
            type=str,
            default="PERF_",
            help="Prefijo unico para identificar los datos de prueba.",
        )
        parser.add_argument(
            "--alumnos",
            type=int,
            default=1000,
            help="Cantidad de alumnos sinteticos.",
        )
        parser.add_argument(
            "--actividades",
            type=int,
            default=10,
            help="Cantidad de actividades sinteticas.",
        )
        parser.add_argument(
            "--creator-username",
            type=str,
            default="admin",
            help="Usuario que quedara como creador y registrador.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina todos los datos asociados al prefijo y termina.",
        )

    def handle(self, *args, **options):
        prefijo = options["prefijo"].strip()
        cantidad_alumnos = options["alumnos"]
        cantidad_actividades = options["actividades"]
        username = options["creator_username"]

        if not prefijo:
            raise CommandError("El prefijo no puede estar vacio.")

        if cantidad_alumnos < 0:
            raise CommandError("La cantidad de alumnos no puede ser negativa.")

        if cantidad_actividades < 0:
            raise CommandError(
                "La cantidad de actividades no puede ser negativa."
            )

        if options["reset"]:
            self._reset(prefijo)
            return

        try:
            creador = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(
                f"No existe el usuario '{username}'."
            )

        with transaction.atomic():
            carrera, _ = Carrera.objects.get_or_create(
                nombre=f"{prefijo}Carrera Test",
                defaults={
                    "escuela": f"{prefijo}Escuela Test",
                },
            )

            jornada, _ = Jornada.objects.get_or_create(
                nombre=f"{prefijo}Jornada Test",
            )

            self.stdout.write(
                f"Generando {cantidad_alumnos} alumnos con prefijo "
                f"'{prefijo}'..."
            )

            existentes = Alumno.objects.filter(
                rut__startswith=prefijo
            ).count()

            alumnos = []

            for i in range(
                existentes,
                existentes + cantidad_alumnos,
            ):
                alumnos.append(
                    Alumno(
                        rut=f"{prefijo}{100000 + i}-0",
                        tipo_documento="RUT",
                        nombres=f"{prefijo}Alumno{i}",
                        apellidos="Sintetico",
                        correo=(
                            f"{prefijo.lower()}alumno{i}"
                            "@example.invalid"
                        ),
                        carrera=carrera.nombre,
                        jornada=jornada.nombre,
                    )
                )

            Alumno.objects.bulk_create(
                alumnos,
                batch_size=500,
                ignore_conflicts=True,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Alumnos nuevos creados: {len(alumnos)}"
                )
            )

            alumnos_creados = list(
                Alumno.objects.filter(rut__startswith=prefijo)
            )

            self.stdout.write(
                f"Generando {cantidad_actividades} actividades "
                f"con prefijo '{prefijo}'..."
            )

            ahora = timezone.now()
            actividades = []

            actividades_existentes = Actividad.objects.filter(
                titulo__startswith=prefijo
            ).count()

            for i in range(
                actividades_existentes,
                actividades_existentes + cantidad_actividades,
            ):
                actividades.append(
                    Actividad(
                        titulo=f"{prefijo}Actividad {i}",
                        descripcion=(
                            "Actividad sintetica para prueba de "
                            "rendimiento."
                        ),
                        tipo="MASIVA",
                        lugar="Sede Alameda - prueba controlada",
                        fecha_inicio=ahora - timedelta(days=i + 1),
                        fecha_fin=(
                            ahora
                            - timedelta(days=i + 1)
                            + timedelta(hours=2)
                        ),
                        estado="FINALIZADA",
                        creado_por=creador,
                    )
                )

            Actividad.objects.bulk_create(
                actividades,
                batch_size=500,
            )

            actividades_creadas = list(
                Actividad.objects.filter(titulo__startswith=prefijo)
            )

            for actividad in actividades_creadas:
                actividad.carreras.add(carrera)
                actividad.jornadas.add(jornada)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Actividades existentes o creadas: "
                    f"{len(actividades_creadas)}"
                )
            )

            if actividades_creadas and alumnos_creados:
                self.stdout.write(
                    "Generando asistencias sinteticas..."
                )

                asistencias = []

                for alumno in alumnos_creados:
                    actividad = random.choice(actividades_creadas)

                    asistencias.append(
                        Asistencia(
                            actividad=actividad,
                            alumno=alumno,
                            metodo_ingreso="RUT",
                            registrado_por=creador,
                        )
                    )

                Asistencia.objects.bulk_create(
                    asistencias,
                    batch_size=500,
                    ignore_conflicts=True,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Asistencias procesadas: {len(asistencias)}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Generacion terminada. Para limpiar, usa --reset "
                "con el mismo prefijo."
            )
        )

    def _reset(self, prefijo):
        self.stdout.write(
            f"Limpiando datos con prefijo '{prefijo}'..."
        )

        with transaction.atomic():
            alumnos = Alumno.objects.filter(
                rut__startswith=prefijo
            )

            actividades = Actividad.objects.filter(
                titulo__startswith=prefijo
            )

            ids_alumnos = alumnos.values_list("id", flat=True)
            ids_actividades = actividades.values_list("id", flat=True)

            auditorias = LogAuditoria.objects.filter(
                detalle__icontains=prefijo
            ) | LogAuditoria.objects.filter(
                objeto_nombre__icontains=prefijo
            )

            n_auditorias = auditorias.delete()
            n_asistencias = Asistencia.objects.filter(
                alumno_id__in=ids_alumnos
            ).delete()
            n_asistencias_actividad = Asistencia.objects.filter(
                actividad_id__in=ids_actividades
            ).delete()
            n_inscripciones = Inscripcion.objects.filter(
                alumno_id__in=ids_alumnos
            ).delete()
            n_alumnos = alumnos.delete()
            n_actividades = actividades.delete()
            n_carreras = Carrera.objects.filter(
                nombre__startswith=prefijo
            ).delete()
            n_jornadas = Jornada.objects.filter(
                nombre__startswith=prefijo
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Limpieza terminada:"
            )
        )
        self.stdout.write(f"  Auditorias: {n_auditorias}")
        self.stdout.write(
            f"  Asistencias por alumno: {n_asistencias}"
        )
        self.stdout.write(
            f"  Asistencias por actividad: "
            f"{n_asistencias_actividad}"
        )
        self.stdout.write(f"  Inscripciones: {n_inscripciones}")
        self.stdout.write(f"  Alumnos: {n_alumnos}")
        self.stdout.write(f"  Actividades: {n_actividades}")
        self.stdout.write(f"  Carreras: {n_carreras}")
        self.stdout.write(f"  Jornadas: {n_jornadas}")
