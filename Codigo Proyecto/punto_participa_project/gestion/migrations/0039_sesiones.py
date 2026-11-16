"""
Actividades de varias sesiones (16/11/2026).

Cada actividad que ya existe queda con una sesión (la 1, con sus mismas fechas). Las asistencias de
alumnos y los ingresos de invitados y acompañantes que ya existen pasan a esa sesión, con su hora,
método y operador. No se borra ni cambia nada de lo que había.
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def convertir_a_una_sesion(apps, schema_editor):
    Actividad = apps.get_model('gestion', 'Actividad')
    Sesion = apps.get_model('gestion', 'Sesion')
    AsistenciaSesion = apps.get_model('gestion', 'AsistenciaSesion')
    Asistencia = apps.get_model('gestion', 'Asistencia')
    Invitado = apps.get_model('gestion', 'Invitado')
    Acompanante = apps.get_model('gestion', 'Acompanante')

    sesion_de = {}
    for a in Actividad.objects.all().only('id', 'fecha_inicio', 'fecha_fin').iterator():
        sesion_de[a.id] = Sesion.objects.create(actividad_id=a.id, numero=1,
                                                fecha_inicio=a.fecha_inicio, fecha_fin=a.fecha_fin).id

    def copiar(registros, campo):
        AsistenciaSesion.objects.bulk_create([
            AsistenciaSesion(sesion_id=sesion_de[r.actividad_id], fecha_ingreso=fecha,
                             metodo_ingreso=r.metodo_ingreso or '', registrado_por_id=r.registrado_por_id,
                             **{campo: r.id if campo != 'alumno_id' else r.alumno_id})
            for r, fecha in registros
        ], batch_size=1000)

    copiar(((a, a.fecha_ingreso) for a in Asistencia.objects.all().iterator()), 'alumno_id')
    copiar(((i, i.ingreso) for i in Invitado.objects.filter(ingreso__isnull=False).iterator()), 'invitado_id')
    copiar(((c, c.ingreso) for c in Acompanante.objects.filter(ingreso__isnull=False).iterator()), 'acompanante_id')


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0038_consentimiento_privacidad"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="actividad",
            name="asistencia_minima",
            field=models.PositiveSmallIntegerField(
                default=75,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Asistencia mínima (%)",
            ),
        ),
        migrations.CreateModel(
            name="Sesion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("numero", models.PositiveSmallIntegerField()),
                ("fecha_inicio", models.DateTimeField()),
                ("fecha_fin", models.DateTimeField()),
                (
                    "actividad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sesiones",
                        to="gestion.actividad",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sesión",
                "verbose_name_plural": "Sesiones",
                "ordering": ["actividad", "numero"],
            },
        ),
        migrations.CreateModel(
            name="AsistenciaSesion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "fecha_ingreso",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                (
                    "metodo_ingreso",
                    models.CharField(blank=True, default="", max_length=10),
                ),
                (
                    "acompanante",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asistencias_sesion",
                        to="gestion.acompanante",
                    ),
                ),
                (
                    "alumno",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asistencias_sesion",
                        to="gestion.alumno",
                    ),
                ),
                (
                    "invitado",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asistencias_sesion",
                        to="gestion.invitado",
                    ),
                ),
                (
                    "registrado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sesion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asistencias",
                        to="gestion.sesion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Asistencia por sesión",
                "verbose_name_plural": "Asistencias por sesión",
                "ordering": ["-fecha_ingreso"],
            },
        ),
        migrations.AddConstraint(
            model_name="sesion",
            constraint=models.UniqueConstraint(
                fields=("actividad", "numero"), name="unica_sesion_por_numero"
            ),
        ),
        migrations.AddConstraint(
            model_name="asistenciasesion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("alumno__isnull", False)),
                fields=("sesion", "alumno"),
                name="una_asistencia_por_sesion_alumno",
            ),
        ),
        migrations.AddConstraint(
            model_name="asistenciasesion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("invitado__isnull", False)),
                fields=("sesion", "invitado"),
                name="una_asistencia_por_sesion_invitado",
            ),
        ),
        migrations.AddConstraint(
            model_name="asistenciasesion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("acompanante__isnull", False)),
                fields=("sesion", "acompanante"),
                name="una_asistencia_por_sesion_acompanante",
            ),
        ),
        migrations.AddConstraint(
            model_name="asistenciasesion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("acompanante__isnull", True),
                        ("alumno__isnull", False),
                        ("invitado__isnull", True),
                    ),
                    models.Q(
                        ("acompanante__isnull", True),
                        ("alumno__isnull", True),
                        ("invitado__isnull", False),
                    ),
                    models.Q(
                        ("acompanante__isnull", False),
                        ("alumno__isnull", True),
                        ("invitado__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="asistencia_sesion_de_una_sola_persona",
            ),
        ),
        migrations.RunPython(convertir_a_una_sesion, migrations.RunPython.noop),
    ]
