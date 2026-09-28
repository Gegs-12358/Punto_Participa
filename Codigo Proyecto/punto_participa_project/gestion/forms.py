from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, time, date
from .models import Actividad


class ActividadForm(forms.ModelForm):
    """
    Formulario para crear y editar actividades.

    - Si es TALLER: cupos_totales es obligatorio.
    - Si es MASIVA: cupos_totales se ignora.
    - El estado se gestiona desde el admin, no desde el CRUD.
    - Las fechas se separan en fecha + hora para mejor UX.
    """

    # Campos separados de fecha y hora
    fecha_inicio_fecha = forms.DateField(
        label='Fecha de inicio',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_inicio_hora = forms.TimeField(
        label='Hora de inicio',
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_fin_fecha = forms.DateField(
        label='Fecha de término',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_fin_hora = forms.TimeField(
        label='Hora de término',
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'form-control',
            'required': True,
        }),
    )

    class Meta:
        model = Actividad
        fields = [
            'titulo', 'descripcion', 'tipo', 'lugar', 'imagen',
            'cupos_totales', 'cronograma',
            'carreras', 'jornadas',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'maxlength': '200',
                'required': True,
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'rows': 4,
                'maxlength': '2000',
                'required': True,
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-select',
                'required': True,
            }),
            'lugar': forms.TextInput(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'maxlength': '200',
                'required': True,
            }),
            'cupos_totales': forms.NumberInput(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'min': '1',
                'step': '1',
            }),
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'cronograma': forms.Textarea(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'rows': 3,
            }),
            'carreras': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input',
            }),
            'jornadas': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Placeholder en español para el select de tipo
        self.fields['tipo'].empty_label = 'Selecciona un tipo'

        # Si estamos editando, prellenar los campos de fecha/hora
        if self.instance and self.instance.pk:
            if self.instance.fecha_inicio:
                self.fields['fecha_inicio_fecha'].initial = self.instance.fecha_inicio.date()
                self.fields['fecha_inicio_hora'].initial = self.instance.fecha_inicio.time()
            if self.instance.fecha_fin:
                self.fields['fecha_fin_fecha'].initial = self.instance.fecha_fin.date()
                self.fields['fecha_fin_hora'].initial = self.instance.fecha_fin.time()

    # ============================================================
    # VALIDACIONES
    # ============================================================

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        cupos_totales = cleaned_data.get('cupos_totales')

        # Combinar fecha + hora en datetime (con zona horaria)
        fi_fecha = cleaned_data.get('fecha_inicio_fecha')
        fi_hora = cleaned_data.get('fecha_inicio_hora')
        ff_fecha = cleaned_data.get('fecha_fin_fecha')
        ff_hora = cleaned_data.get('fecha_fin_hora')

        if fi_fecha and fi_hora:
            cleaned_data['fecha_inicio'] = timezone.make_aware(
                datetime.combine(fi_fecha, fi_hora),
                timezone.get_current_timezone()
            )
        if ff_fecha and ff_hora:
            cleaned_data['fecha_fin'] = timezone.make_aware(
                datetime.combine(ff_fecha, ff_hora),
                timezone.get_current_timezone()
            )

        # Validar que fecha_inicio no sea en el pasado
        fecha_inicio = cleaned_data.get('fecha_inicio')
        if fecha_inicio:
            # Si estamos editando y la fecha no cambió, no validar contra "ahora"
            if not (self.instance and self.instance.pk and self.instance.fecha_inicio == fecha_inicio):
                if fecha_inicio < timezone.now():
                    self.add_error('fecha_inicio_fecha', 'La fecha de inicio no puede ser en el pasado.')

        # Validar que fecha_fin > fecha_inicio
        fecha_fin = cleaned_data.get('fecha_fin')
        if fecha_fin and fecha_inicio and fecha_fin <= fecha_inicio:
            self.add_error('fecha_fin_fecha', 'La fecha de término debe ser posterior a la de inicio.')

        # Si es MASIVA, limpiar cupos
        if tipo == 'MASIVA':
            cleaned_data['cupos_totales'] = None

        # Si es TALLER, asegurar que hay cupos
        if tipo == 'TALLER' and not cupos_totales:
            self.add_error('cupos_totales', 'Debes indicar el cupo máximo del taller.')

        return cleaned_data

    def clean_carreras(self):
        carreras = self.cleaned_data.get('carreras')
        if not carreras or carreras.count() == 0:
            raise ValidationError('Debes seleccionar al menos una carrera.')
        return carreras

    def clean_jornadas(self):
        jornadas = self.cleaned_data.get('jornadas')
        if not jornadas or jornadas.count() == 0:
            raise ValidationError('Debes seleccionar al menos una jornada.')
        return jornadas

    # ============================================================
    # GUARDADO
    # ============================================================

    def save(self, commit=True):
        actividad = super().save(commit=False)

        # Asignar fecha_inicio y fecha_fin desde los campos combinados (con zona horaria)
        fi_fecha = self.cleaned_data.get('fecha_inicio_fecha')
        fi_hora = self.cleaned_data.get('fecha_inicio_hora')
        ff_fecha = self.cleaned_data.get('fecha_fin_fecha')
        ff_hora = self.cleaned_data.get('fecha_fin_hora')

        if fi_fecha and fi_hora:
            actividad.fecha_inicio = timezone.make_aware(
                datetime.combine(fi_fecha, fi_hora),
                timezone.get_current_timezone()
            )
        if ff_fecha and ff_hora:
            actividad.fecha_fin = timezone.make_aware(
                datetime.combine(ff_fecha, ff_hora),
                timezone.get_current_timezone()
            )

        es_nueva = not self.instance.pk
        if es_nueva:
            actividad.recalcular_cupos(inscritos_override=0)
        else:
            actividad.recalcular_cupos()

        if commit:
            actividad.save()
            self.save_m2m()

        return actividad