/**
 * app.js - Punto Participa
 * ------------------------
 * Este es todo el frontend, hecho en JavaScript "vanilla" (sin React, sin
 * jQuery, nada instalado con npm). La idea era que la app funcionara completa
 * en el navegador aunque el backend en Django todavía no estuviera listo.
 * Fui comentando las partes que me costó entender o que tuve que investigar,
 * para que si alguien más del grupo (o yo en un mes más) lee esto, no tenga
 * que adivinar por qué está hecho así.
 */
(function () {
  "use strict";

  // Esto es solo para no escribir document.querySelector 300 veces.
  // $ busca un elemento, $$ busca varios (es lo mismo que hace jQuery con $,
  // pero sin instalar nada).
  const $ = (q, r = document) => r.querySelector(q);
  const $$ = (q, r = document) => [...r.querySelectorAll(q)];
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>'"]/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          "'": "&#39;",
          '"': "&quot;",
        })[c],
    );
  const uid = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;

  /**
   * OJO CON ESTO (limitación que sé que tiene el prototipo)
   * --------------------------------------------------------
   * Como todavía no está listo el backend en Django, estoy guardando todo en
   * localStorage. Sirve para mostrar que la app funciona de principio a fin
   * sin depender de un servidor, pero tiene sus letras chicas: los datos
   * quedan pegados en ESTE navegador nomás (si abro la app en otro compu no
   * va a ver lo mismo), no se comparten entre usuarios, y si alguien borra
   * los datos de navegación se pierde todo.
   *
   * Ya revisé el proyecto Django que armó el equipo de backend, así que dejo
   * anotado lo que hay que cambiar cuando toque conectar de verdad (esto no
   * es una suposición, lo saqué de leer su código):
   *
   *   - NO es una API REST tipo /api/actividades/. Es Django "normal", con
   *     vistas que devuelven templates (render) y unas pocas que devuelven
   *     JSON (JsonResponse) solo para las partes con AJAX (guardar
   *     actividad, guardar usuario, escaneo, eliminar).
   *   - Los nombres de URL reales son: login, dashboard, lista_actividades,
   *     crear_actividad, editar_actividad, eliminar_actividad,
   *     guardar_usuario, usuarios, escaneo, auditoria, reportes,
   *     exportar_reportes, inscripcion_taller. Los data-action de este
   *     archivo deberían apuntar a esos nombres, no a los que inventé yo.
   *   - Los formularios necesitan el token CSRF de Django en cada POST
   *     (esto no existe todavía en este prototipo).
   *   - Los nombres de campos en español no calzan 100% con los míos, ver el
   *     detalle en cada save* más abajo (ej. "titulo" en vez de "name").
   *   - Las respuestas AJAX vienen como { success: true/false, message } o
   *     { success: false, errors }, parecido a como uso toast() acá, así que
   *     esa parte no debería costar mucho adaptarla.
   *
   * Mientras tanto, todo esto sigue leyendo y escribiendo el objeto `data`
   * en memoria y persistiéndolo con save() en localStorage.
   */
  const STORE = "punto-participa-production-v1";
  let startupWarning = "";
  let persistenceFailed = false;

  // Puse todas las carreras en un solo lugar para no tener que escribirlas
  // de nuevo en cada formulario o filtro. Si Duoc agrega una carrera nueva,
  // se cambia solo acá y se actualiza en toda la app.
  const careers = {
    "Escuela de Informática y Telecomunicaciones": [
      "Ingeniería en Informática",
    ],
    "Escuela de Administración y Negocios": [
      "Auditoría",
      "Ingeniería en Administración Mención Finanzas",
      "Ingeniería en Administración Mención Gestión de Personas",
      "Ingeniería en Comercio Exterior",
      "Ingeniería en Gestión Logística",
      "Ingeniería en Marketing Digital",
    ],
    "Escuela de Construcción": [
      "Dibujo y Modelamiento Arquitectónico y Estructural",
      "Ingeniería en Construcción",
      "Ingeniería en Prevención de Riesgos",
      "Restauración de Bienes Patrimoniales",
      "Técnico en Construcción",
      "Técnico en Instalaciones y Proyectos Eléctricos",
      "Técnico Topógrafo Geomático",
    ],
  };
  // Este es el estado "de fábrica" de la app: todo parte vacío. Lo dejé así
  // a propósito para que en la entrega no aparezcan datos inventados de prueba.
  const emptyState = {
    activities: [],
    students: [],
    users: [
      {
        id: "admin",
        name: "Pablo Rebolledo",
        username: "pa.rebolledoa",
        rut: "",
        email: "pa.rebolledoa@duocuc.cl",
        role: "Administrador",
        active: true,
        // El admin inicial no necesita cambiar la clave al entrar (a
        // diferencia de las cuentas nuevas que crea el admin, ver saveUser).
        mustChangePassword: false,
      },
    ],
    attendance: [],
    enrollments: [],
    audit: [],
    session: { active: false, activityId: "" },
    currentUserId: null,
    role: "Administrador",
    view: "activities",
  };
  let data = load();
  // Guarda temporalmente al usuario que está en medio del flujo de "debes
  // cambiar tu contraseña" (ver Auth más arriba y completePasswordChange()
  // más abajo). Solo se usa mientras el modal de cambio de clave está abierto.
  let pendingPasswordUser = null;

  // Esta función carga lo que haya guardado en localStorage. Los "parches"
  // de aquí abajo son porque a mitad de camino cambié nombres de estados y
  // roles (ej. "Publicado" pasó a llamarse "ACTIVA") y no quería que la app
  // se rompiera si alguien tenía datos guardados de una versión anterior.
  function load() {
    try {
      const stored = {
        ...structuredClone(emptyState),
        ...JSON.parse(localStorage.getItem(STORE) || "{}"),
      };
      const admin = stored.users?.find((u) => u.id === "admin");
      if (admin) {
        admin.name = "Pablo Rebolledo";
        admin.username = "pa.rebolledoa";
        admin.email = "pa.rebolledoa@duocuc.cl";
        admin.role = "Administrador";
        admin.active = true;
        admin.mustChangePassword = false;
      }
      stored.users?.forEach((u) => {
        if (u.role === "Encargado de Registro")
          u.role = "Encargado de Registrar";
        // Estos dos campos son nuevos (username y mustChangePassword). Si
        // alguien tiene datos guardados de antes de que los agregara, les
        // invento un username a partir del correo para que no les falte, y
        // los dejo sin pedir cambio de clave (para no bloquear cuentas que
        // ya estaban usando antes de este cambio).
        if (!u.username) u.username = (u.email || "").split("@")[0] || u.id;
        if (u.mustChangePassword === undefined) u.mustChangePassword = false;
      });
      stored.activities?.forEach((a) => {
        if (a.type === "Taller") a.type = "TALLER";
        if (a.type === "Masiva") a.type = "MASIVA";
        if (a.status === "Publicado") a.status = "ACTIVA";
        if (a.status === "Borrador") a.status = "CANCELADA";
        a.endDate = a.endDate || a.date;
        a.schedules = a.schedules || [a.schedule || "Diurna"];
      });
      return stored;
    } catch (error) {
      console.error("No fue posible leer los datos locales:", error);
      startupWarning =
        "Los datos guardados estaban dañados o no se pudieron leer. Se inició una sesión limpia.";
      return structuredClone(emptyState);
    }
  }

  // Junté todo el guardado en esta única función. Así, si el navegador se
  // queda sin espacio (pasa harto en modo incógnito), puedo avisarle al
  // usuario desde un solo lugar en vez de repetir el try/catch en cada función.
  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify(data));
      persistenceFailed = false;
      return true;
    } catch (error) {
      persistenceFailed = true;
      console.error("No fue posible guardar los datos locales:", error);
      toast(
        "No se pudieron guardar los cambios. Revisa el espacio disponible del navegador.",
        true,
      );
      return false;
    }
  }
  /**
   * LOGIN / AUTH
   * ------------
   * Dejé toda la lógica de "quién puede entrar" metida en este objeto para no
   * tenerla desparramada por el código. Ya la actualicé para que pida
   * "username" en vez de correo, porque revisando el backend real confirmé
   * que Django no se loguea con correo: usa su sistema de auth normal, que
   * es `username` + `password` (esto no es una suposición mía, lo vi en
   * `views.py`: `username = request.POST.get('username')`).
   *
   * Lo que SIGUE faltando (esto sí es responsabilidad del equipo de backend,
   * no del frontend, pero lo dejo anotado para no perderlo de vista):
   *
   *   1. Comparar `password` de verdad. Hoy se recibe como parámetro pero no
   *      se usa para nada, porque no hay ninguna contraseña real guardada en
   *      este prototipo (sería absurdo "inventar" contraseñas acá).
   *   2. Cuando exista el backend, este login deja de ser una búsqueda local
   *      y pasa a ser un POST normal a la vista `login_view` (URL: /login/),
   *      con el token CSRF incluido (ver getCsrfToken() más abajo) y Django
   *      maneja la sesión con una cookie, no con un token que uno guarda a
   *      mano.
   *   3. El backend también hace rate limiting (5 intentos cada 15 minutos)
   *      antes de bloquear. Esto no se puede replicar bien en el frontend
   *      porque alguien podría limpiar el localStorage y resetearlo, así que
   *      lo debe hacer el servidor.
   *
   * El flujo de "cambiar contraseña obligatoria" (punto que sí alcancé a
   * agregar) está más abajo, se activa cuando `user.mustChangePassword`
   * es true, igual que en el backend real (`must_change_password`).
   */
  const Auth = {
    login(username, password) {
      const normalized = username.trim().toLowerCase();
      const user = data.users.find(
        (u) =>
          (u.username || "").toLowerCase() === normalized ||
          // Dejo el correo como respaldo por si a alguien le queda un dato
          // viejo sin username todavía (no debería pasar gracias a la
          // migración de load(), pero por si acaso).
          u.email.toLowerCase() === normalized,
      );
      if (!user)
        return {
          ok: false,
          message: "La cuenta no existe. Solicita su creación al administrador.",
        };
      if (!user.active)
        return { ok: false, message: "La cuenta está desactivada." };
      // Falta comparar `password` contra lo que devuelva el backend. Por
      // ahora lo recibo como parámetro nomás para no dejar el input suelto.
      void password;
      return { ok: true, user };
    },
  };

  // Placeholder para cuando exista el backend: Django exige mandar el token
  // CSRF en cada POST que modifique datos. Esta función ya está lista para
  // leerlo desde la meta que agregué en el <head> del index.html; por ahora
  // devuelve texto vacío porque no hay backend sirviendo esta página todavía.
  function getCsrfToken() {
    return $('meta[name="csrf-token"]')?.content || "";
  }

  function log(action, detail) {
    const actor =
      data.users.find((u) => u.id === data.currentUserId)?.name || "Sistema";
    data.audit.unshift({
      id: uid(),
      user: actor,
      action,
      detail,
      at: new Date().toISOString(),
    });
    save();
  }
  function toast(message, error = false) {
    // Ojo: si ya hubo un error guardando antes, no quiero que aparezca
    // después un toast de "éxito" que confunda al usuario haciéndole creer
    // que sí se guardó.
    if (!error && persistenceFailed) return;
    const t = $("#toast");
    t.textContent = `${error ? "!" : "✓"} ${message}`;
    t.classList.toggle("error", error);
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.hidden = true), 3000);
  }
  function formatDate(value) {
    if (!value) return "Sin fecha";
    return new Date(`${value}T00:00:00`).toLocaleDateString("es-CL", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  function normalizeRut(v) {
    return v.replace(/[^0-9kK]/g, "").toUpperCase();
  }
  function formatRut(value) {
    const rut = normalizeRut(value);
    if (rut.length < 2) return rut;
    const body = rut.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${body}-${rut.slice(-1)}`;
  }
  function validRut(value) {
    const rut = normalizeRut(value);
    if (rut.length < 8) return false;
    const body = rut.slice(0, -1),
      dv = rut.slice(-1);
    let sum = 0,
      m = 2;
    for (let i = body.length - 1; i >= 0; i--) {
      sum += Number(body[i]) * m;
      m = m === 7 ? 2 : m + 1;
    }
    const r = 11 - (sum % 11),
      expected = r === 11 ? "0" : r === 10 ? "K" : String(r);
    return dv === expected;
  }
  function rutField(name = "rut", label = "RUT", value = "") {
    return /* HTML */ `<label
      >${label}<input
        name="${name}"
        inputmode="numeric"
        autocomplete="off"
        maxlength="12"
        value="${esc(formatRut(value))}"
        placeholder="XX.XXX.XXX-X"
        required
      /><small class="input-help"
        >Escribe solamente los números; el formato se agrega
        automáticamente.</small
      ></label
    >`;
  }
  // Cada ítem del menú lleva la lista de roles que lo pueden ver. Así controlo
  // qué ve cada tipo de usuario sin tener que hacer un montón de "if" repetidos
  // por cada botón del menú.
  const navItems = [
    ["activities", "▦", "Actividades", ["Administrador", "Creador de Evento"]],
    ["scanner", "⌗", "Registro", ["Administrador", "Encargado de Registrar"]],
    ["reports", "▥", "Reportes", ["Administrador", "Creador de Evento"]],
    ["students", "♧", "Alumnos", ["Administrador"]],
    ["users", "♙", "Usuarios", ["Administrador"]],
    ["audit", "◫", "Auditoría", ["Administrador"]],
    ["enrollment", "↗", "Inscripción", ["Administrador", "Creador de Evento"]],
  ];
  function renderNav() {
    const items = navItems.filter((n) => n[3].includes(data.role));
    if (!items.some((n) => n[0] === data.view)) data.view = items[0][0];
    $("#main-nav").innerHTML = items
      .map(
        (n) =>
          /* HTML */ `<button
            data-view="${n[0]}"
            class="${data.view === n[0] ? "active" : ""}"
          >
            <span>${n[1]}</span>${n[2]}
          </button>`,
      )
      .join("");
    const user =
      data.users.find((u) => u.id === data.currentUserId) || data.users[0];
    $("#profile-role").textContent = user.role;
    $("#profile-name").textContent = user.name;
    $("#profile-initials").textContent = user.name
      .split(/\s+/)
      .slice(0, 2)
      .map((x) => x[0])
      .join("")
      .toUpperCase();
  }
  function render() {
    renderNav();
    const renderer = views[data.view];
    $("#main-content").innerHTML = renderer ? renderer() : "";
    bindView();
  }
  const empty = (title, text) =>
    /* HTML */ `<div class="empty-state">
      <span>○</span>
      <h3>${title}</h3>
      <p>${text}</p>
    </div>`;
  // Acá están las 7 pantallas de la app. Cada una es una función que devuelve
  // el HTML como texto (como un template). Todas leen del mismo objeto `data`,
  // que es como la "base de datos" en memoria mientras no hay backend.
  const views = {
    activities() {
      const published = data.activities.filter(
          (a) => a.status === "ACTIVA",
        ).length,
        talleres = data.activities.filter((a) => a.type === "TALLER").length;
      return /* HTML */ `<section class="hero">
          <div>
            <span class="eyebrow">GESTIÓN DE ACTIVIDADES</span>
            <h1>Conecta a la comunidad con nuevas experiencias</h1>
            <p>
              Crea talleres y actividades masivas, segmenta destinatarios y
              administra su publicación.
            </p>
          </div>
          <div class="hero-actions">
            <img
              class="activity-guide"
              src="imagenes/actividad.png"
              alt="Mascota de Punto Participa mostrando la creación de actividades"
            /><button class="btn" data-action="activity-new">
              ＋ Nueva actividad
            </button>
          </div>
        </section>
        <section class="stats">
          <article class="stat">
            <span>ACTIVIDADES ACTIVAS</span><strong>${published}</strong
            ><small>Publicadas actualmente</small>
          </article>
          <article class="stat">
            <span>TALLERES</span><strong>${talleres}</strong
            ><small>Con control de cupos</small>
          </article>
          <article class="stat">
            <span>ASISTENCIAS HOY</span><strong>${todayAttendance()}</strong
            ><small>Registros del día</small>
          </article>
        </section>
        <section class="panel">
          <div class="panel-head">
            <div>
              <span class="eyebrow">CATÁLOGO</span>
              <h2>Actividades</h2>
            </div>
            <div class="toolbar">
              <input
                id="activity-search"
                placeholder="Buscar actividad…"
              /><select id="activity-status">
                <option>Todos</option>
                <option value="ACTIVA">Activa</option>
                <option value="FINALIZADA">Finalizada</option>
                <option value="CANCELADA">Cancelada</option>
              </select>
            </div>
          </div>
          <div id="activity-list"></div>
        </section>`;
    },
    scanner() {
      const published = data.activities.filter((a) => a.status === "ACTIVA");
      return /* HTML */ `<div
          class="page-title illustrated-title registry-title"
        >
          <div>
            <span class="eyebrow">REGISTRO PRESENCIAL</span>
            <h1>Control de asistencia</h1>
            <p>
              Selecciona una actividad e inicia un turno antes de registrar
              estudiantes.
            </p>
          </div>
          <img
            class="section-illustration registry-illustration"
            src="imagenes/registro.png"
            alt="Mascota registrando una actividad"
          />
        </div>
        <section class="scanner-grid">
          <article class="card scan-card">
            <label
              >Actividad publicada<select id="scan-activity">
                <option value="">Seleccionar actividad</option>
                ${published
                  .map(
                    (a) =>
                      /* HTML */ `<option
                        value="${a.id}"
                        ${data.session.activityId === a.id ? "selected" : ""}
                      >
                        ${esc(a.name)}
                      </option>`,
                  )
                  .join("")}
              </select></label
            >
            <div class="session-controls">
              <button
                class="btn"
                data-action="session-start"
                ${!published.length ? "disabled" : ""}
              >
                Iniciar turno</button
              ><button
                class="btn secondary"
                data-action="session-end"
                ${!data.session.active ? "disabled" : ""}
              >
                Finalizar turno
              </button>
            </div>
            <hr />
            <span class="scan-symbol">⌗</span>
            <h2>Escanear o ingresar RUT</h2>
            <form id="attendance-form">
              <label
                >Método de ingreso<select name="method">
                  <option value="RUT">RUT</option>
                  <option value="QR">Código QR</option>
                  <option value="CODIGO">Código de barras</option>
                </select></label
              >${rutField()}<button
                class="btn"
                ${!data.session.active ? "disabled" : ""}
              >
                Registrar asistencia
              </button>
            </form>
            <div id="scan-result"></div>
          </article>
          <aside class="session">
            <span class="live"
              >●
              ${data.session.active ? "TURNO ACTIVO" : "TURNO INACTIVO"}</span
            ><strong>${sessionAttendance()}</strong
            ><small>registros en esta sesión</small>
            <hr />
            <h3>Últimos ingresos</h3>
            <div id="recent-attendance"></div>
          </aside>
        </section>`;
    },
    reports() {
      const total = data.attendance.length;
      return /* HTML */ `<div
          class="page-title illustrated-title reports-title"
        >
          <div>
            <span class="eyebrow">ANÁLISIS DE PARTICIPACIÓN</span>
            <h1>Reportes</h1>
            <p>Consulta información consolidada y expórtala en CSV.</p>
          </div>
          <img
            class="section-illustration report-illustration"
            src="imagenes/reportes.png"
            alt="Mascota presentando un reporte de actividades"
          /><button class="btn" data-action="export">⇩ Exportar CSV</button>
        </div>
        <section class="filters">
          <select id="report-activity">
            <option value="">Todas las actividades</option>
            ${data.activities
              .map(
                (a) =>
                  /* HTML */ `<option value="${a.id}">${esc(a.name)}</option>`,
              )
              .join("")}</select
          ><select id="report-type">
            <option value="">Todos los tipos</option>
            <option value="TALLER">Taller</option>
            <option value="MASIVA">Masiva</option></select
          ><select id="report-career">
            <option value="">Todas las carreras</option>
            ${Object.values(careers)
              .flat()
              .map((c) => /* HTML */ `<option>${c}</option>`)
              .join("")}</select
          ><button class="btn" data-action="report-filter">Filtrar</button>
        </section>
        <section class="stats">
          <article class="stat">
            <span>ASISTENCIAS</span><strong>${total}</strong
            ><small>Total histórico</small>
          </article>
          <article class="stat">
            <span>INSCRIPCIONES</span><strong>${data.enrollments.length}</strong
            ><small>Reservas confirmadas</small>
          </article>
          <article class="stat">
            <span>ACTIVIDADES</span><strong>${data.activities.length}</strong
            ><small>Registradas</small>
          </article>
        </section>
        <section class="panel">
          <h2>Detalle consolidado</h2>
          <div id="report-table"></div>
        </section>`;
    },
    students() {
      return /* HTML */ `<div
          class="page-title illustrated-title management-title"
        >
          <div>
            <span class="eyebrow">COMUNIDAD ESTUDIANTIL</span>
            <h1>Alumnos</h1>
            <p>
              Registro base utilizado por inscripciones, asistencia e
              invitaciones.
            </p>
          </div>
          <img
            class="section-illustration management-illustration"
            src="imagenes/alumnos.png"
            alt="Mascota presentando la gestión de alumnos"
          />
          <button class="btn" data-action="student-new">＋ Nuevo alumno</button>
        </div>
        <section class="stats">
          <article class="stat">
            <span>ALUMNOS</span><strong>${data.students.length}</strong
            ><small>Registros disponibles</small>
          </article>
          <article class="stat">
            <span>INSCRIPCIONES</span><strong>${data.enrollments.length}</strong
            ><small>Reservas confirmadas</small>
          </article>
          <article class="stat">
            <span>ASISTENCIAS</span><strong>${data.attendance.length}</strong
            ><small>Total histórico</small>
          </article>
        </section>
        <section class="panel">
          <div class="panel-head">
            <h2>Directorio de alumnos</h2>
            <input
              id="student-search"
              placeholder="Buscar por nombre, RUT o carrera…"
            />
          </div>
          <div id="student-list"></div>
        </section>`;
    },
    users() {
      return /* HTML */ `<div
          class="page-title illustrated-title management-title"
        >
          <div>
            <span class="eyebrow">ADMINISTRACIÓN</span>
            <h1>Usuarios y permisos</h1>
            <p>Cada cuenta posee un único rol.</p>
          </div>
          <img
            class="section-illustration management-illustration"
            src="imagenes/usuarios.png"
            alt="Mascota presentando la gestión de usuarios y permisos"
          />
          <button class="btn" data-action="user-new">＋ Nuevo usuario</button>
        </div>
        <section class="panel">
          <div class="panel-head">
            <h2>Usuarios del sistema</h2>
            <input id="user-search" placeholder="Buscar usuario…" />
          </div>
          <div id="user-list"></div>
        </section>`;
    },
    audit() {
      return /* HTML */ `<div class="page-title illustrated-title audit-title">
          <div>
            <span class="eyebrow">TRAZABILIDAD</span>
            <h1>Auditoría</h1>
            <p>Acciones relevantes registradas por usuario y fecha.</p>
          </div>
          <img
            class="section-illustration audit-illustration"
            src="imagenes/auditoria.png"
            alt="Mascota revisando el historial de auditoría"
          /><span class="restricted">Acceso administrador</span>
        </div>
        <section class="filters">
          <input
            id="audit-search"
            placeholder="Buscar acción o usuario…"
          /><select id="audit-action">
            <option value="">Todas las acciones</option>
            ${[...new Set(data.audit.map((x) => x.action))]
              .map((x) => /* HTML */ `<option>${x}</option>`)
              .join("")}
          </select>
        </section>
        <section class="panel timeline"><div id="audit-list"></div></section>`;
    },
    enrollment() {
      const workshops = data.activities.filter(
        (a) => a.type === "TALLER" && a.status === "ACTIVA",
      );
      return /* HTML */ `<div
          class="page-title illustrated-title enrollment-title"
        >
          <div>
            <span class="eyebrow">VISTA PÚBLICA</span>
            <h1>Inscripción a talleres</h1>
            <p>Revisa los talleres disponibles y completa tu inscripción.</p>
          </div>
          <img
            class="section-illustration enrollment-illustration"
            src="imagenes/inscripcion.png"
            alt="Mascota invitando a participar en actividades extraprogramáticas"
          />
        </div>
        <section class="enrollment-wrap">
          <label
            >Vista previa del taller<select id="enrollment-activity">
              <option value="">Seleccionar taller publicado</option>
              ${workshops
                .map(
                  (a) =>
                    /* HTML */ `<option value="${a.id}">
                      ${esc(a.name)}
                    </option>`,
                )
                .join("")}
            </select></label
          >
          <div id="enrollment-card">
            ${empty(
              "Sin taller seleccionado",
              "Publica un taller y selecciónalo para comprobar su inscripción.",
            )}
          </div>
        </section>`;
    },
  };
  function todayAttendance() {
    const today = new Date().toDateString();
    return data.attendance.filter(
      (x) => new Date(x.at).toDateString() === today,
    ).length;
  }
  function sessionAttendance() {
    return data.session.activityId
      ? data.attendance.filter((x) => x.activityId === data.session.activityId)
          .length
      : 0;
  }
  function activityRows(query = "", status = "Todos") {
    const rows = data.activities.filter(
      (a) =>
        a.name.toLowerCase().includes(query.toLowerCase()) &&
        (status === "Todos" || a.status === status),
    );
    const totalCareers = Object.values(careers).flat().length;
    $("#activity-list").innerHTML = !rows.length
      ? empty(
          "No existen actividades",
          "Crea la primera actividad para comenzar.",
        )
      : /* HTML */ `<div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Actividad</th>
                <th>Tipo</th>
                <th>Fecha y horario</th>
                <th>Cupos</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              ${rows
                .map(
                  (a) =>
                    /* HTML */ `<tr>
                      <td>
                        <b>${esc(a.name)}</b
                        ><small
                          >${a.careers.length === totalCareers
                            ? "Todas las carreras"
                            : `${a.careers.length} carrera(s)`}</small
                        >
                      </td>
                      <td>${a.type === "TALLER" ? "Taller" : "Masiva"}</td>
                      <td>
                        ${formatDate(a.date)}<small
                          >${a.startTime} a ${formatDate(a.endDate)}
                          ${a.endTime} · ${esc(a.place)}</small
                        >
                      </td>
                      <td>
                        ${a.type === "TALLER"
                          ? `${enrollmentCount(a.id)} / ${a.capacity}`
                          : "—"}
                      </td>
                      <td>
                        <span
                          class="badge ${a.status !== "ACTIVA" ? "draft" : ""}"
                          >${a.status}</span
                        >
                      </td>
                      <td>
                        <div class="action-group">
                          <button
                            class="link-button"
                            data-activity-edit="${a.id}"
                          >
                            Editar</button
                          ><button
                            class="link-button"
                            data-activity-publish="${a.id}"
                          >
                            ${a.status === "ACTIVA" ? "Cancelar" : "Activar"}</button
                          ><button
                            class="danger-button"
                            data-activity-delete="${a.id}"
                          >
                            Eliminar
                          </button>
                        </div>
                      </td>
                    </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>`;
  }
  function enrollmentCount(id) {
    return data.enrollments.filter((x) => x.activityId === id).length;
  }
  function careerFields(selected = []) {
    return /* HTML */ `<fieldset class="career-selector wide">
      <legend>Carreras convocadas</legend>
      <div class="career-actions">
        <span>Selección rápida</span>
        <div>
          <button type="button" class="career-action" data-career-select-all>
            Seleccionar todas</button
          ><button
            type="button"
            class="career-action secondary"
            data-career-clear
          >
            Limpiar selección
          </button>
        </div>
      </div>
      ${Object.entries(careers)
        .map(
          ([school, list]) =>
            /* HTML */ `<section>
              <h3>${school}</h3>
              ${list
                .map(
                  (c) =>
                    /* HTML */ `<label
                      ><input
                        type="checkbox"
                        name="career"
                        value="${c}"
                        data-career
                        ${selected.includes(c) ? "checked" : ""}
                      />
                      ${c}</label
                    >`,
                )
                .join("")}
            </section>`,
        )
        .join("")}<small id="career-error" class="field-error" hidden
        >Selecciona al menos una carrera.</small
      >
    </fieldset>`;
  }
  // Este es el formulario más largo de la app porque una actividad tiene
  // fecha, hora, tipo, carreras convocadas y jornada. Lo saqué como función
  // aparte porque se reutiliza tanto para crear como para editar.
  function activityFormAligned(a = {}) {
    const schedules = a.schedules || [];
    return /* HTML */ `<form
      id="activity-form"
      class="form-grid"
      data-id="${a.id || ""}"
    >
      <label class="wide"
        >Título<input
          name="name"
          value="${esc(a.name || "")}"
          maxlength="200"
          required /></label
      ><label
        >Tipo<select name="type" id="activity-type">
          <option value="TALLER" ${a.type === "TALLER" ? "selected" : ""}>
            Taller
          </option>
          <option value="MASIVA" ${a.type === "MASIVA" ? "selected" : ""}>
            Masiva
          </option>
        </select></label
      ><label
        >Estado<select name="status">
          <option value="ACTIVA" ${a.status === "ACTIVA" ? "selected" : ""}>
            Activa
          </option>
          <option
            value="FINALIZADA"
            ${a.status === "FINALIZADA" ? "selected" : ""}
          >
            Finalizada
          </option>
          <option
            value="CANCELADA"
            ${a.status === "CANCELADA" ? "selected" : ""}
          >
            Cancelada
          </option>
        </select></label
      ><label
        >Fecha de inicio<input
          name="date"
          type="date"
          value="${a.date || ""}"
          required /></label
      ><label
        >Hora de inicio<input
          name="startTime"
          type="time"
          value="${a.startTime || ""}"
          required /></label
      ><label
        >Fecha de término<input
          name="endDate"
          type="date"
          value="${a.endDate || a.date || ""}"
          required /></label
      ><label
        >Hora de término<input
          name="endTime"
          type="time"
          value="${a.endTime || ""}"
          required /></label
      ><label id="capacity-label"
        >Cupo máximo<input
          name="capacity"
          type="number"
          min="1"
          step="1"
          value="${a.capacity || ""}"
          ${a.type === "MASIVA" ? "" : "required"} /></label
      ><label
        >Imagen<input name="image" type="file" accept="image/*" /><small
          class="input-help"
          >Opcional. Puedes seleccionar una imagen para la actividad.</small
        ></label
      ><label class="wide"
        >Lugar<input
          name="place"
          value="${esc(a.place || "")}"
          maxlength="200"
          required /></label
      >${careerFields(a.careers || [])}
      <fieldset class="career-selector wide">
        <legend>Jornadas asociadas</legend>
        <div class="schedule-options">
          <label
            ><input
              type="checkbox"
              name="schedule"
              value="Diurna"
              ${schedules.includes("Diurna") ? "checked" : ""}
            />
            Diurna</label
          ><label
            ><input
              type="checkbox"
              name="schedule"
              value="Vespertina"
              ${schedules.includes("Vespertina") ? "checked" : ""}
            />
            Vespertina</label
          >
        </div>
        <small id="schedule-error" class="field-error" hidden
          >Selecciona al menos una jornada.</small
        >
      </fieldset>
      <label class="wide"
        >Descripción<textarea name="description" maxlength="2000" required>
${esc(a.description || "")}</textarea
        ></label
      ><label class="wide check-line"
        ><input name="notify" type="checkbox" ${a.notify ? "checked" : ""} />
        Enviar invitaciones después de guardar</label
      >
      <div class="modal-actions wide">
        <button type="button" class="btn secondary" data-action="modal-close">
          Cancelar</button
        ><button class="btn">
          ${a.id ? "Guardar cambios" : "Crear actividad"}
        </button>
      </div>
    </form>`;
  }
  function userForm(u = {}) {
    return /* HTML */ `<form
      id="user-form"
      class="form-grid"
      data-id="${u.id || ""}"
    >
      <label class="wide"
        >Nombre completo<input
          name="name"
          value="${esc(u.name || "")}"
          required /></label
      ><label
        >Usuario (username)<input
          name="username"
          value="${esc(u.username || "")}"
          placeholder="nombre.apellido"
          required /></label
      >${rutField("rut", "RUT", u.rut || "")}<label
        >Correo electrónico<input
          name="email"
          type="email"
          value="${esc(u.email || "")}"
          placeholder="nombre@dominio.cl"
          required /></label
      ><label
        >Rol<select name="role">
          <option ${u.role === "Administrador" ? "selected" : ""}>
            Administrador
          </option>
          <option ${u.role === "Creador de Evento" ? "selected" : ""}>
            Creador de Evento
          </option>
          <option ${u.role === "Encargado de Registrar" ? "selected" : ""}>
            Encargado de Registrar
          </option>
        </select></label
      >
      <div class="modal-actions wide">
        <button type="button" class="btn secondary" data-action="modal-close">
          Cancelar</button
        ><button class="btn">Guardar usuario</button>
      </div>
    </form>`;
  }
  // Estos campos son los mismos que va a tener el modelo Alumno en Django
  // (lo hablamos con el grupo), para que cuando se conecte el backend no
  // haya que andar traduciendo nombres de campos.
  function studentForm(s = {}) {
    const careerOptions = Object.entries(careers)
      .map(
        ([school, list]) =>
          /* HTML */ `<optgroup label="${esc(school)}">
            ${list
              .map(
                (c) =>
                  /* HTML */ `<option ${s.career === c ? "selected" : ""}>
                    ${esc(c)}
                  </option>`,
              )
              .join("")}
          </optgroup>`,
      )
      .join("");
    return /* HTML */ `<form
      id="student-form"
      class="form-grid"
      data-id="${s.id || ""}"
    >
      ${rutField("rut", "RUT", s.rut || "")}<label
        >Correo institucional o personal<input
          name="email"
          type="email"
          value="${esc(s.email || "")}"
          required /></label
      ><label
        >Nombres<input
          name="firstNames"
          value="${esc(s.firstNames || "")}"
          maxlength="100"
          required /></label
      ><label
        >Apellidos<input
          name="lastNames"
          value="${esc(s.lastNames || "")}"
          maxlength="100"
          required /></label
      ><label class="wide"
        >Carrera<select name="career" required>
          <option value="">Seleccionar carrera</option>
          ${careerOptions}
        </select></label
      ><label
        >Jornada<select name="schedule" required>
          <option value="">Seleccionar jornada</option>
          <option ${s.schedule === "Diurna" ? "selected" : ""}>Diurna</option>
          <option ${s.schedule === "Vespertina" ? "selected" : ""}>
            Vespertina
          </option>
        </select></label
      >
      <div class="modal-actions wide">
        <button type="button" class="btn secondary" data-action="modal-close">
          Cancelar</button
        ><button class="btn">Guardar alumno</button>
      </div>
    </form>`;
  }
  function modal(title, body) {
    $("#modal-title").textContent = title;
    $("#modal-content").innerHTML = body;
    $("#modal-backdrop").hidden = false;
    $("#modal-close").focus();
    bindType();
  }
  function closeModal() {
    $("#modal-backdrop").hidden = true;
    $("#modal-content").innerHTML = "";
  }
  function confirmModal(title, message, onConfirm) {
    modal(
      title,
      /* HTML */ `<div class="confirm-box">
        <p>${esc(message)}</p>
        <div class="modal-actions">
          <button class="btn secondary" data-action="modal-close">
            Cancelar</button
          ><button class="btn danger" id="confirm-action">Confirmar</button>
        </div>
      </div>`,
    );
    $("#confirm-action").onclick = () => {
      closeModal();
      onConfirm();
    };
  }
  function bindType() {
    const type = $("#activity-type");
    if (type)
      type.onchange = () => {
        const box = $("#capacity-label");
        box.hidden = type.value === "MASIVA";
        box.querySelector("input").required = type.value === "TALLER";
      };
    type?.dispatchEvent(new Event("change"));
  }
  // Como todo el HTML de la vista se vuelve a generar cada vez que cambio
  // de pantalla, los listeners que tenía puestos se pierden con él. Por eso
  // después de cada render() tengo que "reenganchar" los eventos acá.
  function bindView() {
    if (data.view === "activities") {
      activityRows();
      const f = () =>
        activityRows($("#activity-search").value, $("#activity-status").value);
      $("#activity-search").oninput = f;
      $("#activity-status").onchange = f;
    }
    if (data.view === "scanner") {
      renderRecent();
      $("#scan-activity").onchange = (e) => {
        data.session.activityId = e.target.value;
        data.session.active = false;
        save();
        render();
      };
    }
    if (data.view === "reports") {
      renderReport();
    }
    if (data.view === "students") {
      renderStudents();
      $("#student-search").oninput = (e) => renderStudents(e.target.value);
    }
    if (data.view === "users") {
      renderUsers();
      $("#user-search").oninput = (e) => renderUsers(e.target.value);
    }
    if (data.view === "audit") {
      renderAudit();
      $("#audit-search").oninput = renderAudit;
      $("#audit-action").onchange = renderAudit;
    }
    if (data.view === "enrollment")
      $("#enrollment-activity").onchange = (e) =>
        renderEnrollment(e.target.value);
  }
  function renderRecent() {
    const rows = data.attendance
      .filter((x) => x.activityId === data.session.activityId)
      .slice(-5)
      .reverse();
    $("#recent-attendance").innerHTML = !rows.length
      ? "<p>Todavía no existen registros.</p>"
      : rows
          .map(
            (x) =>
              /* HTML */ `<div class="person">
                <span class="avatar">${esc(x.rut.slice(0, 2))}</span>
                <p>
                  <b>${esc(formatRut(x.rut))}</b><small>Registro exitoso</small>
                </p>
                <time
                  >${new Date(x.at).toLocaleTimeString("es-CL", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}</time
                >
              </div>`,
          )
          .join("");
  }
  function reportRows() {
    const aid = $("#report-activity")?.value || "",
      type = $("#report-type")?.value || "",
      career = $("#report-career")?.value || "";
    return data.activities
      .filter(
        (a) =>
          (!aid || a.id === aid) &&
          (!type || a.type === type) &&
          (!career || a.careers.includes(career)),
      )
      .map((a) => ({
        ...a,
        attendees: data.attendance.filter((x) => x.activityId === a.id).length,
        enrolled: enrollmentCount(a.id),
      }));
  }
  function renderReport() {
    const rows = reportRows();
    $("#report-table").innerHTML = !rows.length
      ? empty(
          "Sin resultados",
          "No hay actividades que coincidan con los filtros.",
        )
      : /* HTML */ `<div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Actividad</th>
                <th>Tipo</th>
                <th>Inscritos</th>
                <th>Asistentes</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              ${rows
                .map(
                  (a) =>
                    /* HTML */ `<tr>
                      <td>${esc(a.name)}</td>
                      <td>${a.type}</td>
                      <td>${a.enrolled}</td>
                      <td>${a.attendees}</td>
                      <td>${formatDate(a.date)}</td>
                    </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>`;
  }
  function renderUsers(q = "") {
    const rows = data.users.filter((u) =>
      `${u.name} ${u.email} ${u.role}`.toLowerCase().includes(q.toLowerCase()),
    );
    $("#user-list").innerHTML = /* HTML */ `<div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Correo</th>
            <th>Rol</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (u) =>
                /* HTML */ `<tr>
                  <td>
                    <b>${esc(u.name)}</b
                    ><small
                      >${u.rut ? esc(formatRut(u.rut)) : "RUT pendiente"}</small
                    >
                  </td>
                  <td>${esc(u.email)}</td>
                  <td><span class="role">${u.role}</span></td>
                  <td>
                    <span class="badge ${u.active ? "" : "inactive"}"
                      >${u.active ? "Activo" : "Inactivo"}</span
                    >
                  </td>
                  <td>
                    <div class="action-group">
                      <button class="link-button" data-user-edit="${u.id}">
                        Editar</button
                      ><button
                        class="link-button"
                        data-user-toggle="${u.id}"
                        ${u.id === "admin"
                          ? 'disabled title="La cuenta principal no se puede desactivar"'
                          : ""}
                      >
                        ${u.active ? "Desactivar" : "Activar"}
                      </button>
                    </div>
                  </td>
                </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  }
  function renderStudents(q = "") {
    const query = q.toLowerCase(),
      rows = data.students.filter((s) =>
        `${s.firstNames} ${s.lastNames} ${s.rut} ${s.email} ${s.career} ${s.schedule}`
          .toLowerCase()
          .includes(query),
      );
    $("#student-list").innerHTML = !rows.length
      ? empty(
          "No existen alumnos",
          "Agrega alumnos para habilitar inscripciones, asistencia e invitaciones.",
        )
      : /* HTML */ `<div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Alumno</th>
                <th>RUT</th>
                <th>Correo</th>
                <th>Carrera</th>
                <th>Jornada</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              ${rows
                .map(
                  (s) =>
                    /* HTML */ `<tr>
                      <td><b>${esc(s.firstNames)} ${esc(s.lastNames)}</b></td>
                      <td>${esc(formatRut(s.rut))}</td>
                      <td>${esc(s.email)}</td>
                      <td>${esc(s.career)}</td>
                      <td><span class="role">${esc(s.schedule)}</span></td>
                      <td>
                        <div class="action-group">
                          <button
                            class="link-button"
                            data-student-edit="${s.id}"
                          >
                            Editar</button
                          ><button
                            class="danger-button"
                            data-student-delete="${s.id}"
                          >
                            Eliminar
                          </button>
                        </div>
                      </td>
                    </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>`;
  }
  function renderAudit() {
    const q = $("#audit-search")?.value.toLowerCase() || "",
      action = $("#audit-action")?.value || "";
    const rows = data.audit.filter(
      (x) =>
        (!action || x.action === action) &&
        `${x.user} ${x.detail}`.toLowerCase().includes(q),
    );
    $("#audit-list").innerHTML = !rows.length
      ? empty("Auditoría vacía", "Las acciones relevantes aparecerán aquí.")
      : rows
          .map(
            (x) =>
              /* HTML */ `<article>
                <span>•</span>
                <div>
                  <b>${esc(x.action)}: ${esc(x.detail)}</b
                  ><small>${esc(x.user)}</small>
                </div>
                <time>${new Date(x.at).toLocaleString("es-CL")}</time>
              </article>`,
          )
          .join("");
  }
  function workshopStatus(a) {
    const used = enrollmentCount(a.id),
      ended = new Date(`${a.endDate || a.date}T${a.endTime}`) < new Date();
    return ended ? "past" : used >= Number(a.capacity) ? "full" : "available";
  }
  function renderEnrollment(id) {
    const a = data.activities.find((x) => x.id === id),
      box = $("#enrollment-card");
    if (!a) {
      box.innerHTML = empty(
        "Sin taller seleccionado",
        "Selecciona un taller publicado.",
      );
      return;
    }
    const status = workshopStatus(a),
      available = Math.max(0, Number(a.capacity) - enrollmentCount(a.id));
    box.innerHTML = /* HTML */ `<article class="card event-card">
      <img class="event-logo" src="imagenes/logo.png" alt="Punto Participa" />
      <div class="event-banner">
        <div>
          <span>${a.type === "TALLER" ? "TALLER" : "ACTIVIDAD MASIVA"}</span>
          <h2>${esc(a.name)}</h2>
        </div>
      </div>
      <div class="event-body">
        <div class="date-tile">
          <strong>${new Date(a.date + "T00:00").getDate()}</strong
          ><span
            >${new Date(a.date + "T00:00")
              .toLocaleDateString("es-CL", { month: "short" })
              .toUpperCase()}</span
          >
        </div>
        <div class="event-copy">
          <h1>${esc(a.name)}</h1>
          <p>${esc(a.description)}</p>
          <ul>
            <li>◷ ${a.startTime} a ${a.endTime}</li>
            <li>⌖ ${esc(a.place)}</li>
          </ul>
        </div>
        <div class="enroll-box">
          ${status === "available"
            ? /* HTML */ `<div class="seat-note">
                  <b>${available} cupos disponibles</b
                  ><span>de ${a.capacity} totales</span>
                </div>
                <form id="enrollment-form" data-id="${a.id}">
                  ${rutField()}<button class="btn">Reservar mi cupo</button>
                </form>`
            : status === "full"
              ? '<div class="state-box error"><span class="state-icon">×</span><h3>Sin cupos disponibles</h3></div>'
              : '<div class="state-box neutral"><span class="state-icon">✓</span><h3>Evento ya realizado</h3></div>'}
        </div>
      </div>
    </article>`;
  }
  // Esto le agrega el punto y el guión al RUT automáticamente mientras el
  // usuario escribe, así la persona no tiene que preocuparse del formato.
  document.addEventListener("input", (e) => {
    if (e.target.matches('input[name="rut"]'))
      e.target.value = formatRut(e.target.value);
  });
  // En vez de poner un onclick en cada botón (que además se perdería cada
  // vez que se re-renderiza la vista), puse un solo listener de click en
  // document y reviso qué botón fue mirando su atributo data-action. Es el
  // patrón de "delegación de eventos" que vimos en clases.
  document.addEventListener("click", (e) => {
    const v = e.target.closest("[data-view]");
    if (v) {
      data.view = v.dataset.view;
      save();
      render();
      return;
    }
    const action = e.target.closest("[data-action]")?.dataset.action;
    if (action === "activity-new")
      modal("Nueva actividad", activityFormAligned());
    if (action === "user-new") modal("Nuevo usuario", userForm());
    if (action === "student-new") modal("Nuevo alumno", studentForm());
    if (action === "modal-close") closeModal();
    if (action === "session-start") {
      const id = $("#scan-activity").value;
      if (!id) return toast("Selecciona una actividad", true);
      data.session = { active: true, activityId: id };
      log("Turno", "Inició un turno de asistencia");
      render();
    }
    if (action === "session-end") {
      data.session.active = false;
      log("Turno", "Finalizó el turno de asistencia");
      render();
    }
    if (action === "report-filter") renderReport();
    if (action === "export") exportCsv();
    if (e.target.closest("[data-career-select-all]")) {
      $$("[data-career]").forEach((x) => (x.checked = true));
      $("#career-error").hidden = true;
    }
    if (e.target.closest("[data-career-clear]")) {
      $$("[data-career]").forEach((x) => (x.checked = false));
    }
    const edit = e.target.closest("[data-activity-edit]");
    if (edit) {
      const a = data.activities.find((x) => x.id === edit.dataset.activityEdit);
      modal("Editar actividad", activityFormAligned(a));
    }
    const publish = e.target.closest("[data-activity-publish]");
    if (publish) {
      const a = data.activities.find(
        (x) => x.id === publish.dataset.activityPublish,
      );
      a.status = a.status === "ACTIVA" ? "CANCELADA" : "ACTIVA";
      log("Actividad", `${a.status}: ${a.name}`);
      render();
    }
    const del = e.target.closest("[data-activity-delete]");
    if (del) {
      const a = data.activities.find(
        (x) => x.id === del.dataset.activityDelete,
      );
      if (
        data.attendance.some((x) => x.activityId === a.id) ||
        data.enrollments.some((x) => x.activityId === a.id)
      )
        return toast("No se puede eliminar: posee registros asociados", true);
      confirmModal("Eliminar actividad", `¿Eliminar “${a.name}”?`, () => {
        data.activities = data.activities.filter((x) => x.id !== a.id);
        log("Actividad", `Eliminó ${a.name}`);
        render();
      });
    }
    const se = e.target.closest("[data-student-edit]");
    if (se)
      modal(
        "Editar alumno",
        studentForm(data.students.find((x) => x.id === se.dataset.studentEdit)),
      );
    const sd = e.target.closest("[data-student-delete]");
    if (sd) {
      const student = data.students.find(
        (x) => x.id === sd.dataset.studentDelete,
      );
      const linked =
        data.attendance.some((x) => x.rut === student.rut) ||
        data.enrollments.some((x) => x.rut === student.rut);
      if (linked)
        return toast(
          "No se puede eliminar: el alumno posee registros asociados",
          true,
        );
      confirmModal(
        "Eliminar alumno",
        `¿Eliminar a ${student.firstNames} ${student.lastNames}?`,
        () => {
          data.students = data.students.filter((x) => x.id !== student.id);
          log("Alumno", `Eliminó a ${student.firstNames} ${student.lastNames}`);
          render();
        },
      );
    }
    const ue = e.target.closest("[data-user-edit]");
    if (ue)
      modal(
        "Editar usuario",
        userForm(data.users.find((x) => x.id === ue.dataset.userEdit)),
      );
    const ut = e.target.closest("[data-user-toggle]");
    if (ut && !ut.disabled) {
      const u = data.users.find((x) => x.id === ut.dataset.userToggle);
      u.active = !u.active;
      log("Usuario", `${u.active ? "Activó" : "Desactivó"} a ${u.name}`);
      render();
    }
  });
  // Mismo truco que con los clicks: un solo listener de submit para todos
  // los formularios de la app, y según el id del formulario decido a qué
  // función mandarlo.
  document.addEventListener("submit", (e) => {
    e.preventDefault();
    if (e.target.id === "activity-form") saveActivity(e.target);
    if (e.target.id === "user-form") saveUser(e.target);
    if (e.target.id === "student-form") saveStudent(e.target);
    if (e.target.id === "attendance-form") saveAttendance(e.target);
    if (e.target.id === "enrollment-form") saveEnrollment(e.target);
    if (e.target.id === "change-password-form")
      completePasswordChange(e.target);
  });
  // Esta función guarda una actividad, sea nueva o editada. Antes de guardar
  // valida 3 cosas: que haya al menos una carrera marcada, al menos una
  // jornada marcada, y que la fecha/hora de término sea después de la de inicio.
  //
  // Nota para cuando se conecte el backend: el modelo Actividad de Django usa
  // otros nombres de campo. Acá uso "name" y allá es "titulo", acá "date" y
  // "endDate" y allá son "fecha_inicio"/"fecha_fin", acá "place" y allá
  // "lugar". "status" sí calza con "estado" (mismos valores ACTIVA/
  // FINALIZADA/CANCELADA). El campo de imagen ya está en el formulario, pero
  // ojo que acá solo guardo el nombre del archivo (imageName): no hay dónde
  // subirlo todavía porque no hay servidor. Cuando exista el backend, ese
  // input type="file" hay que mandarlo de verdad en el FormData del POST.
  function saveActivity(form) {
    const fd = new FormData(form),
      selected = fd.getAll("career"),
      schedules = fd.getAll("schedule");
    if (!selected.length) {
      $("#career-error").hidden = false;
      return;
    }
    if (!schedules.length) {
      $("#schedule-error").hidden = false;
      return;
    }
    const startsAt = new Date(`${fd.get("date")}T${fd.get("startTime")}`),
      endsAt = new Date(`${fd.get("endDate")}T${fd.get("endTime")}`);
    if (endsAt <= startsAt) {
      form.elements.endTime.setCustomValidity(
        "El término debe ser posterior al inicio.",
      );
      form.elements.endTime.reportValidity();
      form.elements.endTime.oninput = () =>
        form.elements.endTime.setCustomValidity("");
      return;
    }
    const id = form.dataset.id,
      image = fd.get("image"),
      item = {
        id: id || uid(),
        name: fd.get("name").trim(),
        type: fd.get("type"),
        date: fd.get("date"),
        startTime: fd.get("startTime"),
        endDate: fd.get("endDate"),
        endTime: fd.get("endTime"),
        capacity:
          fd.get("type") === "TALLER" ? Number(fd.get("capacity")) : null,
        place: fd.get("place").trim(),
        careers: selected,
        schedules,
        description: fd.get("description").trim(),
        notify: fd.has("notify"),
        status: fd.get("status"),
        imageName:
          image?.name ||
          data.activities.find((x) => x.id === id)?.imageName ||
          "",
      };
    if (id)
      data.activities = data.activities.map((x) => (x.id === id ? item : x));
    else data.activities.unshift(item);
    log("Actividad", `${id ? "Actualizó" : "Creó"} ${item.name}`);
    closeModal();
    render();
    toast("Actividad guardada");
  }
  // Guarda un usuario nuevo o editado. Tiene un caso especial: no dejo que
  // se le cambie el rol a la cuenta admin principal, porque si no alguien
  // podría dejar el sistema sin ningún administrador por error.
  //
  // Agregué el campo "username" porque Django no loguea por correo, loguea
  // por username (ver el comentario grande de Auth más arriba). A las
  // cuentas nuevas les dejo mustChangePassword en true, para simular que el
  // admin les da una clave provisoria y el sistema les va a pedir cambiarla
  // la primera vez que entren (así funciona el backend real).
  function saveUser(form) {
    const fd = new FormData(form),
      rut = fd.get("rut");
    if (!validRut(rut)) {
      form.elements.rut.setCustomValidity("El RUT no es válido.");
      form.elements.rut.reportValidity();
      form.elements.rut.oninput = () => form.elements.rut.setCustomValidity("");
      return;
    }
    const email = fd.get("email").toLowerCase(),
      username = fd.get("username").trim().toLowerCase(),
      id = form.dataset.id;
    if (data.users.some((u) => u.email.toLowerCase() === email && u.id !== id))
      return toast("El correo ya está registrado", true);
    if (
      data.users.some((u) => (u.username || "").toLowerCase() === username && u.id !== id)
    )
      return toast("Ese usuario (username) ya está en uso", true);
    if (id === "admin" && fd.get("role") !== "Administrador")
      return toast(
        "La cuenta administradora principal debe conservar su rol",
        true,
      );
    const existing = id ? data.users.find((x) => x.id === id) : null;
    const user = {
      id: id || uid(),
      name: fd.get("name").trim(),
      username,
      rut,
      email,
      role: fd.get("role"),
      active: existing ? existing.active : true,
      // Si es un usuario nuevo, queda pendiente de cambiar la clave al
      // primer ingreso. Si estoy editando uno que ya existía, respeto lo
      // que tenía antes (no lo fuerzo a cambiarla de nuevo por editarlo).
      mustChangePassword: existing ? existing.mustChangePassword : true,
    };
    if (id) data.users = data.users.map((x) => (x.id === id ? user : x));
    else data.users.push(user);
    log("Usuario", `${id ? "Actualizó" : "Creó"} ${user.name}`);
    closeModal();
    render();
    toast("Usuario guardado");
  }
  // Guarda un alumno. Uso el RUT sin puntos ni guion como si fuera el "ID
  // único" para no terminar con el mismo alumno duplicado dos veces.
  //
  // Nota para el backend: el modelo Alumno de Django usa "nombres" y
  // "apellidos" (dos campos separados, como acá), pero llamados distinto:
  // acá tengo "firstNames"/"lastNames" y allá son "nombres"/"apellidos". El
  // resto de los campos (rut, correo, carrera, jornada) sí calzan en nombre.
  function saveStudent(form) {
    const fd = new FormData(form),
      rut = normalizeRut(fd.get("rut")),
      id = form.dataset.id;
    if (!validRut(rut)) {
      form.elements.rut.setCustomValidity("El RUT no es válido.");
      form.elements.rut.reportValidity();
      form.elements.rut.oninput = () => form.elements.rut.setCustomValidity("");
      return;
    }
    if (data.students.some((s) => s.rut === rut && s.id !== id))
      return toast("Ya existe un alumno con ese RUT", true);
    const student = {
      id: id || uid(),
      rut,
      firstNames: fd.get("firstNames").trim(),
      lastNames: fd.get("lastNames").trim(),
      email: fd.get("email").trim().toLowerCase(),
      career: fd.get("career"),
      schedule: fd.get("schedule"),
    };
    if (id)
      data.students = data.students.map((s) => (s.id === id ? student : s));
    else data.students.unshift(student);
    log(
      "Alumno",
      `${id ? "Actualizó" : "Creó"} ${student.firstNames} ${student.lastNames}`,
    );
    closeModal();
    render();
    toast("Alumno guardado");
  }
  // Esto es lo que se usa en la pantalla de "Registro" cuando alguien
  // ingresa su RUT para marcar asistencia. Revisa que no esté ya registrado
  // en esta misma actividad, para que nadie marque entrada dos veces.
  //
  // El selector de "método" (RUT/QR/Código) ya deja guardado con qué medio
  // entró el alumno, igual que lo espera el backend (campo metodo_ingreso).
  // Ojo que acá solo estoy leyendo el RUT escrito a mano en los tres casos;
  // conectar un lector de QR o de código de barras de verdad es aparte y no
  // alcancé a hacerlo, ver la lista de pendientes al final.
  function saveAttendance(form) {
    const rut = form.elements.rut.value;
    const method = form.elements.method?.value || "RUT";
    if (!validRut(rut)) {
      form.elements.rut.setCustomValidity("RUT inválido");
      form.elements.rut.reportValidity();
      form.elements.rut.oninput = () => form.elements.rut.setCustomValidity("");
      return;
    }
    const normalized = normalizeRut(rut),
      student = data.students.find((s) => s.rut === normalized);
    if (!student)
      return toast("El alumno no está registrado en el sistema", true);
    if (
      data.attendance.some(
        (x) => x.activityId === data.session.activityId && x.rut === normalized,
      )
    ) {
      log("Duplicado", `Intento duplicado de ${normalized}`);
      $("#scan-result").innerHTML =
        '<div class="alert error">! <div><b>Asistencia ya registrada</b><small>El estudiante ya ingresó a esta actividad.</small></div></div>';
      return;
    }
    data.attendance.push({
      id: uid(),
      activityId: data.session.activityId,
      studentId: student.id,
      rut: normalized,
      method,
      at: new Date().toISOString(),
    });
    log("Asistencia", `Registró a ${student.firstNames} ${student.lastNames}`);
    render();
    toast("Asistencia registrada");
  }
  // Inscribe a un alumno en un taller. Antes de guardar revisa 3 cosas:
  // que el alumno exista en el sistema, que no esté ya inscrito antes, y
  // que todavía queden cupos disponibles.
  function saveEnrollment(form) {
    const rut = form.elements.rut.value,
      a = data.activities.find((x) => x.id === form.dataset.id);
    if (!validRut(rut)) {
      form.elements.rut.setCustomValidity("RUT inválido");
      form.elements.rut.reportValidity();
      return;
    }
    const normalized = normalizeRut(rut),
      student = data.students.find((s) => s.rut === normalized);
    if (!student)
      return toast("El alumno no está registrado en el sistema", true);
    if (
      data.enrollments.some(
        (x) => x.activityId === a.id && x.rut === normalized,
      )
    )
      return toast("El estudiante ya está inscrito", true);
    if (workshopStatus(a) !== "available")
      return toast("El taller ya no tiene cupos", true);
    data.enrollments.push({
      id: uid(),
      activityId: a.id,
      studentId: student.id,
      rut: normalized,
      at: new Date().toISOString(),
    });
    log(
      "Inscripción",
      `${student.firstNames} ${student.lastNames} se inscribió en ${a.name}`,
    );
    renderEnrollment(a.id);
    toast("Cupo reservado");
  }
  // Arma el CSV a mano (uniendo con comas y comillas) y lo descarga creando
  // un link temporal. El finally es para asegurarme de liberar esa URL
  // aunque algo falle en el medio; si no se libera queda ocupando memoria
  // del navegador (esto lo aprendí revisando la documentación de
  // URL.createObjectURL, no lo sabía antes).
  function exportCsv() {
    let url = "";
    try {
      const rows = reportRows(),
        csv = [
          "Actividad,Tipo,Fecha,Inscritos,Asistentes",
          ...rows.map((a) =>
            [a.name, a.type, a.date, a.enrolled, a.attendees]
              .map((v) => `"${String(v).replaceAll('"', '""')}"`)
              .join(","),
          ),
        ].join("\n");
      url = URL.createObjectURL(
        new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "reporte-punto-participa.csv";
      link.click();
      toast("Reporte descargado");
    } catch (error) {
      console.error("No fue posible exportar el reporte:", error);
      toast("No se pudo generar el archivo CSV. Inténtalo nuevamente.", true);
    } finally {
      if (url) URL.revokeObjectURL(url);
    }
  }
  // Deja al usuario adentro de verdad: guarda quién es, decide qué vista le
  // toca según su rol, y muestra la app privada. La separé de onsubmit
  // porque se necesita llamar desde dos lugares: el login normal, y después
  // de que alguien termina el flujo de "cambiar contraseña obligatoria".
  function completeLogin(user) {
    data.currentUserId = user.id;
    data.role = user.role;
    data.view = navItems.find((n) => n[3].includes(user.role))[0];
    save();
    $("#login-view").hidden = true;
    $("#private-view").hidden = false;
    $("#login-form").reset();
    render();
  }
  // El formulario para pedir la contraseña nueva. Es chico a propósito,
  // reutiliza el mismo modal que ya se usa para actividades y usuarios en
  // vez de inventar un componente nuevo.
  function changePasswordForm() {
    return /* HTML */ `<form id="change-password-form" class="form-grid">
      <p class="wide">
        Es tu primer ingreso (o un administrador reseteó tu clave). Define
        una contraseña nueva antes de continuar.
      </p>
      <label class="wide"
        >Nueva contraseña<input
          name="newPassword"
          type="password"
          minlength="4"
          required /></label
      ><label class="wide"
        >Confirmar contraseña<input
          name="confirmPassword"
          type="password"
          minlength="4"
          required /></label
      >
      <div class="modal-actions wide">
        <button class="btn">Guardar y continuar</button>
      </div>
    </form>`;
  }
  // Recibe el formulario de arriba. Como esto es solo frontend, no hay
  // ninguna contraseña real que guardar: lo único que hago es sacarle a la
  // cuenta la marca de "debe cambiar contraseña" y dejarla entrar. Cuando
  // exista el backend, acá va el POST a `cambiar_contrasena` con el token
  // CSRF (ver getCsrfToken()).
  function completePasswordChange(form) {
    const fd = new FormData(form);
    if (fd.get("newPassword") !== fd.get("confirmPassword"))
      return toast("Las contraseñas no coinciden", true);
    if (!pendingPasswordUser) return;
    pendingPasswordUser.mustChangePassword = false;
    log(
      "Seguridad",
      `${pendingPasswordUser.name} definió una nueva contraseña`,
    );
    const user = pendingPasswordUser;
    pendingPasswordUser = null;
    closeModal();
    completeLogin(user);
    toast("Contraseña actualizada");
  }
  // Acá entra la lógica del login. Ya pide "username" (no correo) porque así
  // funciona el backend real. Si a la cuenta le toca cambiar la contraseña
  // (mustChangePassword), no la dejo pasar directo: le muestro el modal de
  // arriba primero y solo completa el login cuando termina ese paso.
  $("#login-form").onsubmit = (e) => {
    e.preventDefault();
    const username = $("#username").value.trim();
    const password = $("#password").value;
    const result = Auth.login(username, password);
    if (!result.ok) return toast(result.message, true);
    if (result.user.mustChangePassword) {
      pendingPasswordUser = result.user;
      modal("Cambiar contraseña", changePasswordForm());
      return;
    }
    completeLogin(result.user);
  };
  $("#logout-button").onclick = () => {
    data.currentUserId = null;
    save();
    $("#private-view").hidden = true;
    $("#login-view").hidden = false;
    $("#login-form").reset();
  };
  $("#modal-close").onclick = closeModal;
  $("#modal-backdrop").onclick = (e) => {
    if (e.target.id === "modal-backdrop") closeModal();
  };
  document.onkeydown = (e) => {
    if (e.key === "Escape" && !$("#modal-backdrop").hidden) closeModal();
  };

  // Puse este listener "atrapa-todo" por si algo se rompe durante una
  // demostración en clases, para que al menos salga un aviso en pantalla en
  // vez de que la app se quede pegada sin decir nada.
  window.addEventListener("error", (event) => {
    console.error("Error inesperado:", event.error || event.message);
    toast(
      "Ocurrió un error inesperado. Actualiza la página e inténtalo nuevamente.",
      true,
    );
  });
  window.addEventListener("unhandledrejection", (event) => {
    console.error("Operación no controlada:", event.reason);
    toast("Una operación no pudo completarse. Inténtalo nuevamente.", true);
  });

  // Si load() encontró datos corruptos en localStorage, este mensaje recién
  // se muestra acá al final, porque antes de este punto el toast todavía no
  // existe en el DOM.
  if (startupWarning) setTimeout(() => toast(startupWarning, true), 0);
})();
