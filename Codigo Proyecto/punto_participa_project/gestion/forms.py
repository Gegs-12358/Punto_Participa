from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime
import re

from django.db.models import Q

from .models import Actividad, Carrera, Escuela, Lugar
from .utils import limpiar_texto
import io
from PIL import Image
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile


# Número de sala: letras, números y guion ("102", "1203", "A-201"), hasta 10 caracteres
PATRON_NUMERO_SALA = re.compile(r'^[A-Z0-9]+(-[A-Z0-9]+)*$')


class SelectLugar(forms.Select):
    """Desplegable de lugares que marca con data-pide-numero los que piden número de sala."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        lugar = getattr(value, 'instance', None)
        if lugar is not None and lugar.pide_numero:
            opcion['attrs']['data-pide-numero'] = '1'
        return opcion


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
    # Solo actividades con invitación: lista de alumnos (.xlsx o .csv). Obligatoria al crear.
    lista_invitados = forms.FileField(
        label='Lista de invitados', required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx,.csv', 'class': 'form-control'}),
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
            'lugar_numero', 'cupos_totales', 'cronograma',
            'carreras', 'jornadas', 'acompanantes_por_invitado',
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
            'cupos_totales': forms.NumberInput(attrs={
                'class': 'floating-input',
                'placeholder': ' ',
                'min': '1',
                'step': '1',
            }),
            'acompanantes_por_invitado': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': str(Actividad.MAX_ACOMPANANTES),
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

        # Acompañantes: solo se usa en las actividades con invitación; vacío = 0
        self.fields['acompanantes_por_invitado'].required = False

        # Lugar: desplegable con los lugares activos del catálogo. Si se edita una
        # actividad cuyo lugar ya está bloqueado, ese lugar se sigue ofreciendo
        # para no obligar a cambiarlo.
        actual = self.instance.lugar if self.instance and self.instance.pk else None
        filtro = Q(activo=True)
        if actual:
            filtro |= Q(nombre=actual)
        self.fields['lugar'] = forms.ModelChoiceField(
            queryset=Lugar.objects.filter(filtro).order_by('nombre'),
            to_field_name='nombre',
            empty_label='Selecciona un lugar',
            label='Lugar',
            error_messages={
                'required': 'Debes seleccionar un lugar.',
                'invalid_choice': 'Selecciona un lugar de la lista.',
            },
            widget=SelectLugar(attrs={'class': 'form-select', 'required': True}),
        )
        if actual:
            self.initial['lugar'] = actual

        # Número de sala: se muestra solo si el lugar elegido lo pide (lo controla
        # gestion/js/lugar_numero.js); la validación real está en clean().
        self.fields['lugar_numero'].label = 'Número de sala'
        self.fields['lugar_numero'].widget = forms.TextInput(attrs={
            'class': 'form-control', 'maxlength': '10', 'autocomplete': 'off',
            'placeholder': 'Ej.: 1203', 'data-lugar-numero': '1',
        })
        lugar_inicial = self.data.get(self.add_prefix('lugar')) if self.is_bound else actual
        lugar_inicial = limpiar_texto(str(lugar_inicial or ''))[:200]   # sin \x00 ni controles
        self.lugar_pide_numero = bool(lugar_inicial) and Lugar.objects.filter(
            nombre=lugar_inicial, pide_numero=True).exists()

        # Carreras: solo las activas de escuelas activas (o sin escuela). Al editar se
        # mantienen las que la actividad ya tenía, aunque después se hayan bloqueado.
        escuelas_bloqueadas = Escuela.objects.filter(activo=False).values_list('nombre', flat=True)
        filtro_carreras = Q(activo=True) & ~Q(escuela__in=list(escuelas_bloqueadas))
        if self.instance and self.instance.pk:
            filtro_carreras |= Q(pk__in=self.instance.carreras.values_list('pk', flat=True))
        self.fields['carreras'].queryset = (
            Carrera.objects.filter(filtro_carreras).order_by('escuela', 'nombre')
        )

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

        # Si es MASIVA o con invitación, limpiar cupos (en la con invitación manda la lista)
        if tipo in ('MASIVA', 'INVITACION'):
            cleaned_data['cupos_totales'] = None

        # Carreras y jornadas: obligatorias salvo en las actividades con invitación
        if tipo != 'INVITACION':
            if not cleaned_data.get('carreras'):
                self.add_error('carreras', 'Debes seleccionar al menos una carrera.')
            if not cleaned_data.get('jornadas'):
                self.add_error('jornadas', 'Debes seleccionar al menos una jornada.')
            cleaned_data['acompanantes_por_invitado'] = 0
        elif cleaned_data.get('acompanantes_por_invitado') is None:
            cleaned_data['acompanantes_por_invitado'] = 0
        self._validar_cambio_de_tipo(tipo)
        self._leer_lista_invitados(tipo)

        # Si es TALLER, asegurar que hay cupos
        # Si es TALLER, validar cupos
        if tipo == 'TALLER':
            if cupos_totales is None:
                self.add_error('cupos_totales', 'Debes indicar el cupo máximo del taller.')
            elif cupos_totales < 1:
                self.add_error('cupos_totales', 'El cupo debe ser al menos 1.')

        # Número de sala: obligatorio solo si el lugar lo pide; si no, se descarta
        lugar_obj = getattr(self, '_lugar_obj', None)
        numero = (cleaned_data.get('lugar_numero') or '').replace(' ', '').upper()
        if lugar_obj and lugar_obj.pide_numero:
            if not numero:
                self.add_error('lugar_numero', f'Indica el número de {lugar_obj.nombre.lower()}.')
            elif not PATRON_NUMERO_SALA.match(numero):
                self.add_error('lugar_numero', 'Usa solo letras, números y guion (ej.: 1203 o A-201).')
        else:
            numero = ''
        cleaned_data['lugar_numero'] = numero

        return cleaned_data

    def clean_lugar(self):
        # El modelo guarda el nombre del lugar (texto), no el objeto
        lugar = self.cleaned_data.get('lugar')
        self._lugar_obj = lugar
        return lugar.nombre if lugar else ''

    def _validar_cambio_de_tipo(self, tipo):
        """Una actividad con invitados no puede dejar de ser "con invitación", y una con
        inscripciones o asistencias no puede pasar a serlo (se mezclarían los registros)."""
        actividad = self.instance
        if not (actividad and actividad.pk) or not tipo or tipo == actividad.tipo:
            return
        if actividad.tipo == 'INVITACION' and actividad.invitados.exists():
            self.add_error('tipo', 'Esta actividad ya tiene invitados: no puede cambiar de tipo.')
        elif tipo == 'INVITACION' and (actividad.inscripciones.exists() or actividad.asistencias.exists()):
            self.add_error('tipo', 'Esta actividad ya tiene inscripciones o asistencias: '
                                   'no puede pasar a ser con invitación.')

    def _leer_lista_invitados(self, tipo):
        """Lee el archivo de invitados (solo si es con invitación). Las filas quedan en
        self.filas_invitados; la vista las revisa y las carga después de guardar."""
        from .invitados import ArchivoInvalido, leer
        self.filas_invitados = None
        archivo = self.cleaned_data.get('lista_invitados')
        if tipo != 'INVITACION':
            return
        if not archivo:
            if not (self.instance and self.instance.pk):
                self.add_error('lista_invitados', 'Sube la lista de invitados (.xlsx o .csv).')
            return
        try:
            self.filas_invitados = leer(archivo, archivo.name)
        except ArchivoInvalido as e:
            self.add_error('lista_invitados', str(e))

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