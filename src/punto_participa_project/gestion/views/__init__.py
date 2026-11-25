"""
Vistas de la aplicación, separadas por tema. Cada archivo agrupa lo que hace algo parecido:

  comun.py               Lo que usan varias pantallas: registro en la auditoría, errores JSON,
                         detección de AJAX y colores de las escuelas.
  cuentas.py             Inicio y cierre de sesión, cambio y recuperación de contraseña.
  inicio.py              Inicio (dashboard) y botón de retención de datos.
  actividades.py         Listado, detalle, participantes, crear, editar y eliminar actividades.
  inscripciones.py       Inscripción pública a talleres, lista de espera, cancelación,
                         página de actividades masivas y Política de Privacidad.
  invitaciones.py        Correo de invitación, lista de invitados y respuesta desde el enlace.
  escaner.py             Escáner de asistencia, turnos y contador en vivo.
  escaner_invitacion.py  Escáner en las actividades con invitación.
  reportes.py            Pantalla Reportes y filtros que comparten el Inicio y las exportaciones.
  exportaciones.py       Descargas en Excel y CSV de Reportes y Auditoría.
  usuarios.py            Usuarios del sistema y carga masiva.
  alumnos.py             Directorio, ficha, bloqueo, anonimización e importación de la nómina.
  catalogos.py           Lugares, escuelas y carreras.
  auditoria.py           Pantalla Auditoría y sus filtros.

Las URL están en gestion/urls.py. La lógica que no depende de una pantalla (retención, cancelaciones,
lista de espera, importadores, invitados) está en gestion/servicios/. Los correos están en
templates/gestion/correos/.
"""
