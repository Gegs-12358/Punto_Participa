# Guía de estilo de Punto Participa (P-UI)

Reglas para que todas las pantallas se vean y se usen igual. Las piezas comunes están en
`gestion/templatetags/ui.py` (se cargan con `{% load ui %}`) y sus estilos al final de
`static/gestion/css/styles.css` (bloque "P-UI").

## Colores (variables de `styles.css`)

| Variable | Uso |
| --- | --- |
| `--navy` `#002f5f` | Títulos, texto de botones, íconos |
| `--gold` `#fbb800` | Acción principal (botón amarillo) |
| `--red` `#b42318` | Acciones que borran o bloquean |
| `--muted` `#68798a` | Textos secundarios |
| `--line` `#dbe3e9` | Bordes |

No se escriben colores sueltos en las plantillas; se usan estas variables.

## Encabezado de cada pantalla

```html
<div class="page-title">
    <div>
        <span class="eyebrow">SECCIÓN</span>
        <h1>Título</h1>
        <p>Una frase que diga qué se hace aquí.</p>
    </div>
    <div class="page-title__acciones">
        <img class="page-title__ilustracion" src="{% static 'gestion/img/encabezado/actividad.webp' %}" alt="" width="92" height="92">
        <p class="globo-mascota">Mensaje corto de la mascota</p>
        <button class="btn">{% icono "agregar" %} Acción principal</button>
    </div>
</div>
```

- Orden a la derecha: mascota, su globo (opcional) y la acción principal.
- El mensaje del globo es texto real, no parte de la imagen, para que se lea y lo lean los
  lectores de pantalla. Mascota y globo se ocultan en pantallas angostas.
- Ilustraciones disponibles (livianas, ~10 KB): `actividad`, `alumnos`, `auditoria`, `inscripcion`,
  `registro`, `reportes`, `usuarios`, en `img/encabezado/*.webp`.

## Botones

| Tipo | Cómo se ve | Cuándo |
| --- | --- | --- |
| Acción principal | `<button class="btn">{% icono "agregar" %} Texto</button>` (amarillo, ícono y texto) | Lo que el usuario vino a hacer: crear, guardar, agregar, exportar |
| Secundario | `class="btn secondary"` | Alternativas de la acción principal |
| Solo ícono | `class="btn-icon"` + `data-tooltip` + `aria-label` | Barras de filtro y acciones de cada fila |
| Peligro | `class="btn-icon btn-icon--danger"` | Eliminar, bloquear; siempre con confirmación |

Un botón de solo ícono **siempre** lleva `data-tooltip="Nombre"` (aviso al pasar el mouse o al
llegar con Tab) y `aria-label` (para lectores de pantalla).

## Íconos

`{% icono "nombre" %}`: `filtrar`, `limpiar`, `buscar`, `ver`, `editar`, `eliminar`, `bloquear`,
`desbloquear`, `participantes`, `correo`, `exportar`, `agregar`, `guardar`, `imprimir`, `cambiar`,
`finalizar`.
No se usan emojis ni símbolos sueltos (👁, ✎, ✕, ▽) como íconos.

## Barra de filtros

```html
<form method="get" class="filters-bar" role="search">
    <div class="filter-group filter-group--buscar">   <!-- buscador, si la pantalla lo tiene -->
        <label for="filtro-buscar">Buscar</label>
        <input type="search" id="filtro-buscar" name="q" value="{{ request.GET.q }}">
    </div>
    <div class="filter-group">...</div>              <!-- un filtro por grupo, con su label -->
    {% url 'mi_vista' as url_limpiar %}{% acciones_filtro url_limpiar %}
</form>
{% chips_filtros "q=Búsqueda,tipo=Tipo,estado=Estado" url_limpiar %}
```

- Siempre los mismos dos botones al final: **Filtrar** (amarillo) y **Limpiar filtros** (×).
- Debajo, los chips de "Filtros activos": cada uno quita su filtro y "Limpiar todos" los quita todos.

## Menú desplegable (varias acciones del mismo tipo)

Cuando hay varias opciones parecidas (por ejemplo, los formatos de exportación), van en un solo
botón con menú, y cada opción dice qué contiene. Funciona sin JavaScript y se cierra con Escape o
al hacer clic afuera (`js/ui.js`).

```html
<details class="menu-desplegable">
    <summary class="btn secondary">{% icono "exportar" %} Exportar <span aria-hidden="true">▾</span></summary>
    <div class="menu-desplegable__panel" role="menu">
        <a role="menuitem" href="..."><strong>Qué es · Formato</strong><span>Qué trae, en una frase.</span></a>
    </div>
</details>
```

## Pestañas de vista (dos formas de ver los mismos datos)

Cuando una pantalla muestra los mismos datos de dos maneras (Reportes: por actividad
o por escuela y carrera), cada pestaña es una tarjeta con ícono, **título que dice qué
agrupa** y una línea que explica qué trae. La activa va en azul institucional con borde
dorado. Clases: `tabs tabs--vistas` y `tab-button tab-vista`, con `role="tab"`.
La pestaña elegida queda en la URL (`?vista=detalle`), así se mantiene al recargar,
filtrar o paginar. Las pestañas de navegación simple (Catálogos) siguen con `tab-button`.

## Acciones de cada fila

```html
<div class="acciones-fila">
    <a class="btn-icon btn-icon--sm" href="..." data-tooltip="Ver detalle" aria-label="Ver detalle de X">{% icono "ver" %}</a>
    <button type="button" class="btn-icon btn-icon--sm btn-icon--danger" data-tooltip="Eliminar" aria-label="Eliminar X">{% icono "eliminar" %}</button>
</div>
```

Orden fijo: ver, acciones propias de la pantalla, editar, bloquear/eliminar (al final).

## Textos

- Botones con verbo y en minúscula salvo la primera letra: "Nueva actividad", "Guardar cambios".
- Lista vacía: qué pasa y qué hacer ("No hay actividades que coincidan con los filtros").
