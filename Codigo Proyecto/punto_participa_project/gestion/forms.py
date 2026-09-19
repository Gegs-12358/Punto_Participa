from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Actividad


class ActividadForm(forms.ModelForm):
    """
    Formulario para crear y editar actividades.

    - Si es TALLER: cupos_totales es obligatorio.
    - Si es MASIVA: cupos_totales se ignora.
    - El estado se gestiona desde el admin, no desde el CRUD.
    - Las fechas se formatean como ISO 8601 para que el input datetime-local
      las acepte correctamente.
    """

    class Meta:
        model = Actividad
        fields = [
            'titulo', 'descripcion', 'tipo', 'lugar', 'imagen',
            'cupos_totales', 'fecha_inicio', 'fecha_fin',
            'carreras', 'jornadas',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '200',
                'required': True,
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'maxlength': '2000',
                'required': True,
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-select',
                'required': True,
            }),
            'lugar': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '200',
                'required': True,
            }),
            'cupos_totales': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1',
            }),
            'fecha_inicio': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'required': True,
                },
                format='%Y-%m-%dT%H:%M',
            ),
            'fecha_fin': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'required': True,
                },
                format='%Y-%m-%dT%H:%M',
            ),
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'carreras': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input',
            }),
            'jornadas': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input',
            }),
        }

    # ============================================================
    # INICIALIZACIÓN
    # ============================================================

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forzar formato ISO 8601 para datetime-local en entrada y salida.
        self.fields['fecha_inicio'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['fecha_fin'].input_formats = ['%Y-%m-%dT%H:%M']

    # ============================================================
    # VALIDACIONES POR CAMPO
    # ============================================================

    def clean_fecha_inicio(self):
        """Valida que la fecha de inicio no sea en el pasado.
        [REFACTOR] En edición se permite mantener la fecha original
        aunque ya haya pasado (evita romper ediciones de actividades antiguas).
        """
        fecha_inicio = self.cleaned_data.get('fecha_inicio')
        if not fecha_inicio:
            return fecha_inicio

        # Si estamos editando y la fecha no cambió, no validar contra "ahora"
        if self.instance and self.instance.pk and self.instance.fecha_inicio == fecha_inicio:
            return fecha_inicio

        if fecha_inicio < timezone.now():
            raise ValidationError('La fecha de inicio no puede ser en el pasado.')
        return fecha_inicio

    def clean_fecha_fin(self):
        """Valida que la fecha de fin sea posterior a la de inicio."""
        fecha_fin = self.cleaned_data.get('fecha_fin')
        fecha_inicio = self.cleaned_data.get('fecha_inicio')
        if fecha_fin and fecha_inicio and fecha_fin <= fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')
        return fecha_fin

    def clean_cupos_totales(self):
        """Valida que los cupos sean un número positivo si es TALLER."""
        cupos = self.cleaned_data.get('cupos_totales')
        tipo = self.cleaned_data.get('tipo')
        if tipo == 'TALLER':
            if not cupos or cupos <= 0:
                raise ValidationError('Si es un TALLER, debes indicar un cupo máximo mayor a 0.')
        return cupos

    def clean_carreras(self):
        """Valida que haya al menos una carrera seleccionada."""
        carreras = self.cleaned_data.get('carreras')
        if not carreras or carreras.count() == 0:
            raise ValidationError('Debes seleccionar al menos una carrera.')
        return carreras

    def clean_jornadas(self):
        """Valida que haya al menos una jornada seleccionada."""
        jornadas = self.cleaned_data.get('jornadas')
        if not jornadas or jornadas.count() == 0:
            raise ValidationError('Debes seleccionar al menos una jornada.')
        return jornadas

    # ============================================================
    # VALIDACIONES CRUZADAS
    # ============================================================

    def clean(self):
        """
        Validaciones cruzadas entre campos.
        [REFACTOR] La validación de fecha_fin > fecha_inicio ya está en
        clean_fecha_fin(), acá solo nos preocupamos de cupos vs tipo.
        """
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        cupos_totales = cleaned_data.get('cupos_totales')

        # Si es MASIVA, limpiar cupos
        if tipo == 'MASIVA':
            cleaned_data['cupos_totales'] = None

        # Si es TALLER, asegurar que hay cupos
        if tipo == 'TALLER' and not cupos_totales:
            self.add_error('cupos_totales', 'Debes indicar el cupo máximo del taller.')

        return cleaned_data

    # ============================================================
    # GUARDADO
    # ============================================================

    def save(self, commit=True):
        """
        [REFACTOR] Delega el cálculo de cupos al modelo Actividad.recalcular_cupos().
        - Al crear un TALLER: cupos_disponibles = cupos_totales (inscritos = 0).
        - Al editar un TALLER: respeta las inscripciones existentes.
        - MASIVA: cupos = None.
        """
        actividad = super().save(commit=False)

        es_nueva = not self.instance.pk
        if es_nueva:
            actividad.recalcular_cupos(inscritos_override=0)
        else:
            # Al editar, si ya está en BBDD, contar inscripciones reales
            actividad.recalcular_cupos()

        if commit:
            actividad.save()
            self.save_m2m()

        return actividad