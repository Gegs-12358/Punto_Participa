# Cambios Realizados - Punto Participa

## Sprint Final - Refactor de Formulario de Actividades

### 1. Separación de campos de fecha y hora

**Antes:** Un solo campo `datetime-local` con fecha y hora juntas.
**Después:** 4 campos separados: `fecha_inicio_fecha`, `fecha_inicio_hora`, `fecha_fin_fecha`, `fecha_fin_hora`.

**Archivos modificados:**
- `gestion/forms.py`: Se agregaron 4 campos `DateField`/`TimeField` y se combinan en `clean()` y `save()`.
- `gestion/templates/gestion/actividad_form.html`: Se muestran los 4 campos en una fila (`form-row-4`).
- `gestion/templates/gestion/actividad_form_partial.html`: Igual, para el modal.
- `gestion/static/gestion/js/scripts.js`: Se actualizó la validación de fechas con `combinarFechaHora()`.
- `gestion/static/gestion/css/styles.css`: Se agregó la sección 42 (`.form-row-4`).

**Bug corregido:** Se usó `timezone.make_aware()` para evitar el error `can't compare offset-naive and offset-aware datetimes`.

### 2. Label flotante en formularios

**Antes:** Los labels estaban arriba del input.
**Después:** Los labels flotan dentro del input y suben al hacer clic.

**Archivos modificados:**
- `gestion/static/gestion/css/styles.css`: Sección 38 y "FORZAR LABEL FLOTANTE".
- `gestion/templates/gestion/login.html`, `inscripcion_taller.html`, `escaneo.html`, `cambiar_contrasena.html`, `recuperar_contrasena.html`, `restablecer_contrasena.html`, `usuarios.html`, `auditoria.html`, `actividad_form.html`, `actividad_form_partial.html`.
- `gestion/forms.py`: Se agregó `class="floating-input"` a los widgets.

### 3. Select de tipo en español

**Antes:** El select mostraba "Select an option".
**Después:** Muestra "— Selecciona un tipo —".

**Archivos modificados:**
- `gestion/templates/gestion/actividad_form.html` y `actividad_form_partial.html`: Select manual con opciones en español.

### 4. Asterisco de campo obligatorio al lado del label

**Antes:** El asterisco quedaba debajo del texto.
**Después:** El asterisco queda al lado del texto en rojo.

**Archivos modificados:**
- `gestion/static/gestion/css/styles.css`: Sección 43.

### 5. Aviso de campos obligatorios

**Nuevo:** Se agregó un banner al inicio del formulario de actividades que dice "Los campos marcados con * son obligatorios."

**Archivos modificados:**
- `gestion/templates/gestion/actividad_form.html` y `actividad_form_partial.html`.

### 6. Configuración de tests

**Nuevo:** Se agregó detección de modo test en `settings.py` para usar `StaticFilesStorage` en lugar de `CompressedManifestStaticFilesStorage`.

**Archivos modificados:**
- `punto_participa/settings.py`: Se agregó `TESTING = 'test' in sys.argv`.

### 7. Suite de tests ampliada

**Antes:** 130 tests.
**Después:** 228 tests.

**Archivos nuevos:**
- `gestion/tests_decorators_utils.py`: 63 tests para `decorators.py` y `utils.py`.
- `gestion/tests_views_criticas.py`: 35 tests para las vistas críticas de `views.py`.

**Cobertura final:**

| Archivo | Cobertura |
|---------|-----------|
| context_processors.py | 100% |
| decorators.py | 98% |
| forms.py | 96% |
| middleware.py | 100% |
| models.py | 99% |
| permissions.py | 100% |
| urls.py | 100% |
| utils.py | 96% |
| views.py | 83% |
| **TOTAL** | **87%** |

### 8. Archivos nuevos

- `.coveragerc`: Configuración de coverage para excluir migraciones, tests, etc.
- `docs/coverage_report.txt`: Reporte de cobertura en texto.
- `docs/htmlcov/`: Reporte de cobertura HTML interactivo.
- `gestion/tests_decorators_utils.py`: Tests de decoradores y utils.
- `gestion/tests_views_criticas.py`: Tests de vistas críticas.