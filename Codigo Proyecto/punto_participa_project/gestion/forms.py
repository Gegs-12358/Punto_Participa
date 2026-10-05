from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, time, date
from .models import Actividad
from .utils import limpiar_texto
import io
from PIL import Image
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile


class LimpiarTextoMixin:
    """Limpia automáticamente todos los CharField (incluye EmailField).

    - Excluye campos de contraseña y los listados en `campos_sin_limpiar`.
    - Los Textarea conservan los saltos de línea; el resto se limpia a una línea.
    - Se ejecuta en to_python, o sea ANTES de max_length y de los validadores.
    """
    campos_sin_limpiar = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if not isinstance(campo, forms.CharField):
                continue
            if nombre in self.campos_sin_limpiar:
                continue
            if isinstance(campo.widget, forms.PasswordInput):
                continue
            una_linea = not isinstance(campo.widget, forms.Textarea)
            self._envolver(campo, una_linea)

    @staticmethod
    def _envolver(campo, una_linea):
        original = campo.to_python

        def to_python(valor):
            if isinstance(valor, str):
                valor = limpiar_texto(valor, una_linea=una_linea)
            return original(valor)

        campo.to_python = to_python


class ActividadForm(LimpiarTextoMixin, forms.ModelForm):
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
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={
            'type': 'date',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_inicio_hora = forms.TimeField(
        label='Hora de inicio',
        input_formats=['%H:%M'],
        widget=forms.TimeInput(format='%H:%M', attrs={
            'type': 'time',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_fin_fecha = forms.DateField(
        label='Fecha de término',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={
            'type': 'date',
            'class': 'form-control',
            'required': True,
        }),
    )
    fecha_fin_hora = forms.TimeField(
        label='Hora de término',
        input_formats=['%H:%M'],
        widget=forms.TimeInput(format='%H:%M', attrs={
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
            # Si estamos editando y la fecha no cambió (hasta el minuto), no validar contra "ahora"
            fecha_sin_cambios = (
                self.instance and self.instance.pk and self.instance.fecha_inicio
                and self.instance.fecha_inicio.replace(second=0, microsecond=0)
                    == fecha_inicio.replace(second=0, microsecond=0)
            )
            if not fecha_sin_cambios:
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
        # Si es TALLER, validar cupos
        if tipo == 'TALLER':
            if cupos_totales is None:
                self.add_error('cupos_totales', 'Debes indicar el cupo máximo del taller.')
            elif cupos_totales < 1:
                self.add_error('cupos_totales', 'El cupo debe ser al menos 1.')

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

    # Tamaño máximo permitido para la imagen subida (5 MB)
    TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024

    # Formatos de imagen que el sistema acepta de verdad (validados por contenido,
    # no por la extensión del nombre de archivo)
    FORMATOS_IMAGEN_PERMITIDOS = {'JPEG', 'PNG', 'GIF', 'WEBP'}

    def clean_imagen(self):
        """
        Valida y limpia la imagen subida:
        1. Rechaza archivos demasiado grandes.
        2. Verifica que el CONTENIDO sea realmente una imagen válida en un
           formato permitido (no solo que el nombre termine en .jpg).
        3. Si es una imagen nueva, la reconstruye sin metadatos EXIF
           (ubicación GPS, fecha, modelo de cámara, etc.).
        No reemplaza un antivirus. ClamAV queda como mejora futura (ver backlog).
        """
        imagen = self.cleaned_data.get('imagen')

        # Si no es un archivo nuevo (se mantiene la imagen ya guardada), no tocar nada
        if not imagen or not isinstance(imagen, UploadedFile):
            return imagen

        # 1. Tamaño máximo
        if imagen.size > self.TAMANO_MAXIMO_IMAGEN:
            raise ValidationError(
                f'La imagen no puede superar los '
                f'{self.TAMANO_MAXIMO_IMAGEN // (1024 * 1024)} MB.'
            )

        # 2. Verificar que el contenido sea realmente una imagen válida
        try:
            img = Image.open(imagen)
            img.verify()  # valida la estructura sin cargarlo completo
        except Exception:
            raise ValidationError(
                'El archivo no es una imagen válida o está dañado.'
            )

        # Reabrir: img.verify() deja el objeto inutilizable para seguir operando
        imagen.seek(0)
        img = Image.open(imagen)
        formato = img.format or ''

        if formato not in self.FORMATOS_IMAGEN_PERMITIDOS:
            raise ValidationError(
                f'Formato de imagen no permitido ({formato or "desconocido"}). '
                f'Usa JPEG, PNG, GIF o WEBP.'
            )

        # GIF (animado o no) no se reprocesa: perdería la animación
        if formato == 'GIF':
            imagen.seek(0)
            return imagen

        # 3. Reconstruir la imagen sin metadatos EXIF
        try:
            datos_pixeles = list(img.getdata())
            imagen_limpia = Image.new(img.mode, img.size)
            imagen_limpia.putdata(datos_pixeles)

            buffer = io.BytesIO()
            opciones_guardado = {}
            if formato in ('JPEG', 'WEBP'):
                opciones_guardado['quality'] = 90
            imagen_limpia.save(buffer, format=formato, **opciones_guardado)
            buffer.seek(0)

            imagen = ContentFile(buffer.read(), name=imagen.name)
        except Exception:
            # Si falla la limpieza de metadatos, usar la imagen original
            # ya validada en los pasos 1 y 2 (no bloquear por esto)
            imagen.seek(0)

        return imagen

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