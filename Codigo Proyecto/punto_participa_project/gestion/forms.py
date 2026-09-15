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
            'tipo': forms.Select(attrs={'class': 'form-select', 'required': True}),
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
            'fecha_inicio': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
                'required': True,
            }),
            'fecha_fin': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
                'required': True,
            }),
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'carreras': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
            'jornadas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }

    # ============================================================
    # VALIDACIONES
    # ============================================================

    def clean_fecha_inicio(self):
        """Valida que la fecha de inicio no sea en el pasado."""
        fecha_inicio = self.cleaned_data.get('fecha_inicio')
        if fecha_inicio and fecha_inicio < timezone.now():
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

    def clean(self):
        """Validaciones cruzadas entre campos."""
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

    def save(self, commit=True):
        """
        Sobrescribe el save para asignar cupos_disponibles automáticamente.
        - Si es TALLER: cupos_disponibles = cupos_totales (al crear).
        - Si es MASIVA: cupos_disponibles = None.
        """
        actividad = super().save(commit=False)

        if actividad.tipo == 'TALLER':
            if not self.instance.pk:  # Si es nueva
                actividad.cupos_disponibles = actividad.cupos_totales
        else:
            actividad.cupos_totales = None
            actividad.cupos_disponibles = None

        if commit:
            actividad.save()
            self.save_m2m()

        return actividad