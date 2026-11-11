// Usuarios (7.8, administrador y coordinador): coordinadores, planilleros y consultores, sus indicadores, alertas,
// acciones y asignación; el avance por zona y el detalle de cada usuario. El coordinador ve a todos, pero solo crea y
// gestiona planilleros y consultores, y no cambia roles: esas acciones no se le muestran (y el servidor las rechaza).
// `pintarIndicadores` lo usan también «Mi cuenta» y «Mi trabajo».
import { api, ErrorApi, nombreRol, puede } from '../api.js';
import { url } from '../base.js';
import { CANALES, ETIQUETAS_CAMPOS, RESULTADOS } from '../modelo.js';
import { $, aviso, avisoError, confirmar, dialogo, fecha, hayEscrito, html, montar, num, titulo } from '../ui.js';

const ROLES = { coordinador: 'Coordinador', planillero: 'Planillero', consultor: 'Consultor' };
const DE_CAMPO = ['planillero', 'consultor'];
// Los coordinadores solo los crea y gestiona el administrador (como en el servidor: cualquier otro rol, también)
const gestionable = (u) => DE_CAMPO.includes(u.rol) || puede('usuarios.coordinadores');
const rolesQueCrea = () => Object.entries(ROLES).filter(([k]) => DE_CAMPO.includes(k) || puede('usuarios.coordinadores'));
const rolHtml = (rol) => html`<span class="chip rol rol-${rol}">${nombreRol(rol)}</span>`;
const ALERTAS = {
  bloqueo: ['Bloqueo', 'ambar', 'Tiene 5 o más ingresos fallidos en los últimos 15 minutos: su red puede estar bloqueada. «Desbloquear» los borra.'],
  volumen: ['Volumen', 'rojo', 'Hoy llegó al tope de personas consultadas.'],
  ingresos: ['Ingresos', 'rojo', 'Más de 20 ingresos fallidos con su usuario en 24 horas.'],
  clave_vencida: ['Clave vencida', 'ambar', 'La clave temporal venció sin usarse: restablézcala.'],
};
// Qué cuenta cada columna (va en `title`)
const EXPLICA = {
  creadas: 'Fichas nuevas que creó o que se cargaron de sus planillas. Entre paréntesis, las netas: sin las que después se unieron por estar duplicadas.',
  actualizadas: 'Personas distintas a las que les cambió algún dato. No cuenta las asistencias a reuniones.',
  con_datos_nuevos: 'Personas distintas a las que les completó un dato que la ficha nunca había tenido.',
  cedulas: 'Cédulas completadas por primera vez.',
  puesto_mesa: 'Puestos y mesas de votación completados por primera vez.',
  acercamientos: 'Llamadas, mensajes y visitas registrados, sin los anulados.',
  contactadas: 'Personas distintas con al menos un contacto efectivo.',
  calidad: 'Números que agregó y hoy están equivocados o no existen · cédulas en conflicto · fichas que creó y se unieron por duplicadas.',
  ultimo_ingreso: 'Último ingreso correcto al panel.',
};

const hoyLocal = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const restarDias = (iso, n) => new Date(new Date(iso + 'T12:00:00').getTime() - n * 86400000).toISOString().slice(0, 10);

/** Selector de periodo (desde, hasta); por defecto, los últimos 30 días. */
function periodoHtml(desde, hasta) {
  const h = hasta || hoyLocal();
  const d = desde || restarDias(h, 29);
  return html`<form class="periodo" id="f-periodo">
    <label class="campo"><span>Desde</span><input type="date" name="desde" value="${d}" max="${hoyLocal()}"></label>
    <label class="campo"><span>Hasta</span><input type="date" name="hasta" value="${h}" max="${hoyLocal()}"></label>
    <div class="segmentado" role="group" aria-label="Periodos rápidos">${[7, 30, 90].map((n) => html`<button type="button" data-dias="${n}">${n} días</button>`)}</div>
  </form>`;
}

function enlazarPeriodo(el, alCambiar) {
  const f = $('#f-periodo', el);
  if (!f) return;
  f.addEventListener('change', () => alCambiar(f.desde.value, f.hasta.value));
  f.addEventListener('click', (e) => {
    const b = e.target.closest('[data-dias]');
    if (!b) return;
    const h = hoyLocal();
    alCambiar(restarDias(h, Number(b.dataset.dias) - 1), h);
  });
}

const kpi = (t, v, d = '', explica = '') => html`<div class="kpi" title="${explica}"><div class="t">${t}</div><div class="v">${v}</div>${d ? html`<div class="d">${d}</div>` : ''}</div>`;

function alertasHtml(u) {
  return html`${(u.alertas || []).map((a) => { const [t, c, ex] = ALERTAS[a] || [a, '', '']; return html`<span class="chip ${c}" title="${ex}">${t}</span>`; })}`;
}

function estadoHtml(u) {
  if (!u.activo) return html`<span class="chip">Inactivo</span>`;
  if (u.debe_cambiar_clave) return html`<span class="chip ambar" title="Todavía no cambió la clave temporal">Clave temporal</span>`;
  return html`<span class="chip verde">Activo</span>`;
}

/** Indicadores de 5.1 de un usuario (o los propios): bloques según el rol y la serie del periodo. */
export function pintarIndicadores(c, ind, { rol = ind.rol } = {}) {
  const p = ind.planillero || {};
  const k = ind.consultor || {};
  const comp = Object.entries(p.completados || {}).filter(([, n]) => n);
  const adm = ind.administracion || {};
  const conPlanillero = rol !== 'consultor';
  const conConsultor = rol === 'consultor' || (k.acercamientos || 0) > 0;
  const conAdministracion = rol === 'coordinador' || rol === 'admin' || Object.values(adm).some((n) => n > 0);
  const barras = (obj, etiquetas) => {
    const filas = Object.entries(obj || {}).filter(([, n]) => n).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...filas.map(([, n]) => n));
    return filas.length ? html`<div class="lista-barras">${filas.map(([clave, n]) => html`<div class="f"><span>${etiquetas(clave)}</span><span><span class="b" style="width:${Math.round((n / max) * 100)}%"></span></span><span class="n">${num(n)}</span></div>`)}</div>`
      : html`<p class="sec">Sin datos en el periodo.</p>`;
  };
  const serie = ind.serie || [];
  montar(c, html`
    <p class="sec">Del ${fecha(ind.desde)} al ${fecha(ind.hasta)}.</p>
    ${conAdministracion ? html`<div class="kpis kpis-administracion">
      ${kpi('Importaciones', num(adm.importaciones), '', 'Importaciones de Excel que hizo.')}
      ${kpi('Exportaciones', num(adm.exportaciones), '', 'Exportaciones de la base y de listas de asistentes.')}
      ${kpi('Uniones', num(adm.uniones), '', 'Fichas duplicadas que unió.')}
      ${kpi('Supresiones', num(adm.supresiones), '', 'Personas que suprimió a pedido del titular.')}
      ${kpi('Usuarios creados', num(adm.usuarios_creados), '', 'Planilleros, consultores o coordinadores que creó.')}
    </div>` : ''}
    ${conPlanillero ? html`<div class="kpis">
      ${kpi('Creadas', num(p.creadas), `${num(p.creadas_netas)} netas · ${num(p.creadas_por_planilla)} de planillas`, EXPLICA.creadas)}
      ${kpi('Actualizadas', num(p.actualizadas), `${num(p.correcciones)} correcciones`, EXPLICA.actualizadas)}
      ${kpi('Con datos nuevos', num(p.con_datos_nuevos), '', EXPLICA.con_datos_nuevos)}
      ${kpi('Teléfonos agregados', num(p.telefonos_agregados), '', 'Números agregados a fichas.')}
      ${kpi('Autorizaciones', num((p.autorizaciones || {}).si || 0), `${num((p.autorizaciones || {}).no || 0)} no autorizan`, 'Autorizaciones registradas: sí y no.')}
      ${kpi('Asistencias', num(p.asistencias), `${num(p.ubicadas)} ubicadas`, 'Asistentes registrados en reuniones · personas ubicadas en el mapa.')}
      ${kpi('Fichas vistas', num(p.fichas_vistas), `${num(p.personas_vistas)} personas consultadas`, 'Fichas abiertas y personas servidas en listas, por día.')}
    </div>
    <div class="rejilla r-12">
      <section class="tarjeta c-6"><h2 title="La primera vez que cada dato llegó a la ficha">Datos completados</h2>${barras(Object.fromEntries(comp), (cl) => ETIQUETAS_CAMPOS[cl] || titulo(cl.replace(/_/g, ' ')))}</section>
      <section class="tarjeta c-6"><h2 title="${EXPLICA.calidad}">Calidad</h2><div class="datos">
        <div><span>Números luego equivocados</span><b>${num((p.calidad || {}).telefonos_luego_equivocados)}</b></div>
        <div><span>Cédulas en conflicto</span><b>${num((p.calidad || {}).cedulas_en_conflicto)}</b></div>
        <div><span>Duplicados unidos</span><b>${num((p.calidad || {}).duplicados_unidos)}</b></div></div></section>
    </div>` : ''}
    ${conConsultor ? html`<div class="kpis">
      ${kpi('Acercamientos', num(k.acercamientos), `${num(k.personas)} personas`, EXPLICA.acercamientos)}
      ${kpi('Contactadas', num(k.contactadas), `${num(k.no_contactar)} pidieron no ser contactadas`, EXPLICA.contactadas)}
      ${kpi('Autorizaciones', num(k.autorizaciones_obtenidas), `${num(k.cedulas_dictadas)} cédulas dictadas`, 'Autorizaciones obtenidas en acercamientos · cédulas que dictó el titular.')}
      ${kpi('Fuera de horario', num(k.fuera_de_horario), '', 'Acercamientos fuera del horario de contacto.')}
    </div>
    <div class="rejilla r-12">
      <section class="tarjeta c-6"><h2>Por canal</h2>${barras(k.por_canal, (cl) => CANALES[cl] || cl)}</section>
      <section class="tarjeta c-6"><h2>Por resultado</h2>${barras(k.por_resultado, (cl) => RESULTADOS[cl]?.etiqueta || cl)}</section>
    </div>` : ''}
    <section class="tarjeta serie">
      <header><h2>Por ${ind.agrupar === 'semana' ? 'semana' : ind.agrupar === 'mes' ? 'mes' : 'día'}</h2><span class="nota" title="Cada periodo cuenta personas distintas: una persona actualizada dos días cuenta en los dos">No suma al total</span></header>
      ${serie.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th class="num">Creadas</th><th class="num">Actualizadas</th><th class="num">Acercamientos</th></tr></thead>
        <tbody>${serie.map((s) => html`<tr style="cursor:default"><td>${/^\d{4}-\d{2}-\d{2}$/.test(s.fecha) ? fecha(s.fecha) : s.fecha}</td><td class="num">${num(s.creadas)}</td><td class="num">${num(s.actualizadas)}</td><td class="num">${num(s.acercamientos)}</td></tr>`)}</tbody></table></div>`
        : html`<p class="sec">Sin actividad en el periodo.</p>`}
    </section>`);
}

// ───────── Alta, edición y acciones ─────────

async function areasDisponibles() {
  try {
    const r = await api.get('/api/areas');
    return Array.isArray(r) ? r : r?.filas || r?.areas || [];
  } catch {
    return []; // sin zonas guardadas (o el servidor todavía no las tiene)
  }
}

function asignacionHtml(cat, areas, asignacion = {}) {
  const lugares = new Set((asignacion.lugares || []).map(String));
  const elegidas = new Set((asignacion.areas || []).map(String));
  const grupos = { barrio: 'Barrios', sector: 'Sectores', centro_poblado: 'Centros poblados', corregimiento: 'Corregimientos', caserio: 'Caseríos', vereda: 'Veredas' };
  return html`<fieldset class="asignacion ancho"><legend>Asignación</legend>
    <p class="sec">Sus listas y colas se limitan a estos barrios, veredas y áreas. Sin asignación, trabaja sobre toda la base.</p>
    <input class="entrada" type="search" placeholder="Filtrar barrios y veredas" data-filtrar-lugares>
    <div class="opciones-asignacion" data-lugares>${Object.entries(grupos).map(([t, g]) => {
      const ls = cat.lugares.filter((l) => l.tipo === t);
      return ls.length ? html`<div class="grupo"><b>${g}</b>${ls.map((l) => html`<label data-nombre="${l.nombre.toLowerCase()}"><input type="checkbox" name="lugares" value="${l.id}" ${lugares.has(String(l.id)) ? 'checked' : ''}> ${titulo(l.nombre)}</label>`)}</div>` : '';
    })}</div>
    ${areas.length ? html`<b class="sub-asignacion">Áreas dibujadas en el mapa</b><div class="opciones-asignacion corto">${areas.map((a) => html`<label><input type="checkbox" name="areas" value="${a.id ?? a._id}" ${elegidas.has(String(a.id ?? a._id)) ? 'checked' : ''}> ${a.nombre}</label>`)}</div>` : ''}
  </fieldset>`;
}

const marcados = (f, nombre) => [...f.querySelectorAll(`input[name="${nombre}"]:checked`)].map((x) => Number(x.value));

function enlazarFiltroLugares(raiz) {
  const filtro = raiz.querySelector('[data-filtrar-lugares]');
  filtro?.addEventListener('input', () => {
    const t = filtro.value.trim().toLowerCase();
    for (const l of raiz.querySelectorAll('[data-lugares] label')) l.hidden = !!t && !l.dataset.nombre.includes(t);
  });
}

function mostrarClaveTemporal(usuario, r) {
  const { el } = dialogo({
    titulo: 'Clave temporal',
    cuerpo: html`<p>Entregue esta clave a <b>${usuario}</b> en persona o por un medio seguro. <b>No se vuelve a mostrar.</b></p>
      <div class="clave-temporal"><code id="clave-temporal">${r.clave_temporal}</code><button class="btn" id="copiar">Copiar</button></div>
      <p class="sec">Vence el ${fecha(r.vence, true)} (72 horas). Al ingresar, el sistema le pedirá cambiarla y aceptar el compromiso de confidencialidad.</p>`,
    pie: html`<button class="btn primario" data-cerrar>Listo</button>`,
  });
  el.querySelector('#copiar').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(r.clave_temporal); aviso('Clave copiada'); } catch {
      const s = getSelection(); s.selectAllChildren(el.querySelector('#clave-temporal')); aviso('Seleccionada: cópiela con el teclado');
    }
  });
}

/** Alta (sin `u`) o edición de un usuario. Resuelve con true si guardó. */
async function dialogoUsuario(u = null) {
  const [cat, areas] = await Promise.all([api.catalogos(), areasDisponibles()]);
  return new Promise((resolver) => {
    const { el, cerrar, listo } = dialogo({
      titulo: u ? `Editar a ${u.usuario}` : 'Nuevo usuario',
      ancho: true,
      cuerpo: html`<form class="form" id="f-usuario" novalidate>
        ${u ? '' : html`<label class="campo"><span>Usuario *</span><input name="usuario" required minlength="3" maxlength="40" autocapitalize="none" spellcheck="false" placeholder="ana.perez"></label>`}
        <label class="campo"><span>Nombre completo *</span><input name="nombre" required minlength="3" maxlength="80" value="${u?.nombre || ''}"></label>
        ${u ? '' : html`<label class="campo"><span>Rol *</span><select name="rol">${rolesQueCrea().map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>`}
        <label class="campo"><span>Teléfono de contacto</span><input name="telefono" maxlength="30" inputmode="tel" value="${u?.telefono || ''}"></label>
        ${asignacionHtml(cat, areas, u?.asignacion)}
        <p class="sec ancho" data-sin-asignacion hidden>Los coordinadores no tienen asignación: trabajan sobre toda la base, como el administrador.</p>
        <div class="error ancho" role="alert"></div>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" type="submit" form="f-usuario">${u ? 'Guardar' : 'Crear usuario'}</button>`,
      sucio: (x) => hayEscrito(x.querySelector('#f-usuario')),
    });
    enlazarFiltroLugares(el);
    listo.then((v) => resolver(!!v));
    const f = el.querySelector('#f-usuario');
    // Un coordinador no lleva asignación: se oculta y no se envía
    const coordinador = () => (u ? u.rol : f.rol.value) === 'coordinador';
    const verAsignacion = () => {
      f.querySelector('.asignacion').hidden = coordinador();
      f.querySelector('[data-sin-asignacion]').hidden = !coordinador();
    };
    f.rol?.addEventListener('change', verAsignacion);
    verAsignacion();
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const boton = el.querySelector('button[type=submit]');
      const error = f.querySelector('.error');
      error.textContent = '';
      const asignacion = coordinador() ? { lugares: [], areas: [] } : { lugares: marcados(f, 'lugares'), areas: marcados(f, 'areas') };
      const cuerpo = { nombre: f.nombre.value.trim(), telefono: f.telefono.value.trim() || null, asignacion };
      boton.disabled = true;
      try {
        if (u) {
          await api.patch(`/api/usuarios/${u.id}`, cuerpo);
          aviso('Usuario guardado');
          cerrar(true);
        } else {
          const r = await api.post('/api/usuarios', { ...cuerpo, usuario: f.usuario.value.trim().toLowerCase(), rol: f.rol.value });
          cerrar(true);
          mostrarClaveTemporal(r.usuario, r);
        }
      } catch (err) {
        if (err?.estado === 401) return;
        error.textContent = err.message;
      } finally {
        boton.disabled = false;
      }
    });
  });
}

/** Acciones sobre un usuario; resuelve con true si cambió algo. */
async function accion(nombre, u) {
  try {
    if (nombre === 'editar') return await dialogoUsuario(u);
    if (nombre === 'activar' || nombre === 'desactivar') {
      const activar = nombre === 'activar';
      if (!await confirmar(activar ? `¿Activar a ${u.usuario}? Podrá volver a ingresar.` : `¿Desactivar a ${u.usuario}? Sus sesiones se cierran en la siguiente acción que haga. No se borra nada.`,
        { si: activar ? 'Activar' : 'Desactivar', peligro: !activar })) return false;
      await api.patch(`/api/usuarios/${u.id}`, { activo: activar });
      aviso(activar ? 'Usuario activado' : 'Usuario desactivado');
      return true;
    }
    if (nombre === 'rol') {
      const nuevo = await elegirRol(u);
      if (!nuevo) return false;
      await api.patch(`/api/usuarios/${u.id}`, { rol: nuevo });
      aviso('Rol cambiado');
      return true;
    }
    if (nombre === 'clave') {
      if (!await confirmar(`¿Restablecer la clave de ${u.usuario}? Recibirá una clave temporal y sus sesiones se cierran.`, { si: 'Restablecer' })) return false;
      mostrarClaveTemporal(u.usuario, await api.post(`/api/usuarios/${u.id}/clave`));
      return true;
    }
    if (nombre === 'sesiones') {
      if (!await confirmar(`¿Cerrar las sesiones abiertas de ${u.usuario}?`, { si: 'Cerrar sesiones' })) return false;
      const r = await api.del(`/api/usuarios/${u.id}/sesiones`);
      aviso(r.cerradas === 1 ? '1 sesión cerrada' : `${num(r.cerradas)} sesiones cerradas`);
      return true;
    }
    if (nombre === 'desbloquear') {
      await api.del(`/api/usuarios/${u.id}/bloqueo`);
      aviso('Ingresos fallidos borrados');
      return true;
    }
  } catch (err) { avisoError(err); }
  return false;
}

/** Cambio de rol (solo el administrador): elige el rol nuevo y avisa que sus sesiones se cierran. */
function elegirRol(u) {
  const otros = Object.entries(ROLES).filter(([k]) => k !== u.rol);
  const { el, cerrar, listo } = dialogo({
    titulo: `Cambiar el rol de ${u.usuario}`,
    cuerpo: html`<form class="form" id="f-rol"><label class="campo ancho"><span>Rol nuevo</span><select name="rol">${otros.map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>
      <p class="sec ancho">Sus sesiones se cierran. Un coordinador tiene todos los permisos del administrador salvo gestionar coordinadores, cambiar roles y los ajustes de permisos; al pasar a coordinador deja su asignación.</p></form>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn oscuro" type="submit" form="f-rol">Cambiar rol</button>`,
  });
  el.querySelector('#f-rol').addEventListener('submit', (e) => { e.preventDefault(); cerrar(e.target.rol.value); });
  return listo;
}

function botonesAccion(u) {
  if (!gestionable(u)) return html`<p class="sec">Solo el administrador gestiona a los coordinadores.</p>`;
  return html`<div class="acciones-usuario">
    <button class="btn chico" data-accion="editar" data-id="${u.id}">Editar</button>
    <button class="btn chico" data-accion="${u.activo ? 'desactivar' : 'activar'}" data-id="${u.id}">${u.activo ? 'Desactivar' : 'Activar'}</button>
    <button class="btn chico" data-accion="clave" data-id="${u.id}">Restablecer clave</button>
    ${puede('usuarios.roles') ? html`<button class="btn chico" data-accion="rol" data-id="${u.id}">Cambiar rol</button>` : ''}
    <button class="btn chico" data-accion="sesiones" data-id="${u.id}">Cerrar sesiones</button>
    ${u.bloqueado ? html`<button class="btn chico" data-accion="desbloquear" data-id="${u.id}">Desbloquear</button>` : ''}
  </div>`;
}

/** Las acciones de una fila en un diálogo (la tabla queda angosta); resuelve con el nombre de la acción elegida. */
function elegirAccion(u) {
  const { el, cerrar, listo } = dialogo({ titulo: `Acciones · ${u.usuario}`, cuerpo: html`<div class="lista-acciones">${botonesAccion(u)}</div>` });
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-accion]');
    if (b) cerrar(b.dataset.accion);
  });
  return listo;
}

const plural = (n, uno, varios) => `${num(n)} ${n === 1 ? uno : varios}`;

// ───────── Vista de la lista ─────────

export async function vistaUsuarios(el, { q }) {
  let desde = q.get('desde') || '';
  let hasta = q.get('hasta') || '';
  let por = q.get('por') === 'area' ? 'area' : 'lugar';
  let filas = [];

  async function pintar() {
    const params = { desde, hasta };
    const [lista, ind] = await Promise.all([api.get('/api/usuarios', params), api.get('/api/usuarios/indicadores', params)]);
    if (!el.isConnected) return;
    filas = lista;
    const t = ind.totales;
    montar(el, html`
      <div class="cabecera"><div><h1>Usuarios</h1><div class="sub">Coordinadores, planilleros y consultores: su trabajo, sus alertas y su asignación. Los usuarios no se borran: se desactivan.</div></div>
        <div class="acciones"><button class="btn primario" id="nuevo">Nuevo usuario</button></div></div>
      ${periodoHtml(ind.desde, ind.hasta)}
      <div class="kpis">
        ${kpi('Activos', num((t.coordinadores_activos || 0) + t.planilleros_activos + t.consultores_activos), `${t.coordinadores_activos ? `${plural(t.coordinadores_activos, 'coordinador', 'coordinadores')} · ` : ''}${plural(t.planilleros_activos, 'planillero', 'planilleros')} · ${plural(t.consultores_activos, 'consultor', 'consultores')}`)}
        ${kpi('Creadas', num(t.creadas), `${num(t.creadas_netas)} netas`, EXPLICA.creadas)}
        ${kpi('Actualizadas', num(t.actualizadas), '', EXPLICA.actualizadas)}
        ${kpi('Cédulas agregadas', num(t.cedulas), '', EXPLICA.cedulas)}
        ${kpi('Puestos y mesas', `${num(t.puestos)} · ${num(t.mesas)}`, '', EXPLICA.puesto_mesa)}
        ${kpi('Acercamientos', num(t.acercamientos), `${num(t.contactadas)} contactadas`, EXPLICA.acercamientos)}
        ${kpi('Esperan autorización', num(t.pendientes_autorizacion), 'con número usable', 'Personas vigentes con número usable que todavía no autorizan: la cola del consultor no las llama.')}
      </div>
      ${filas.length ? html`<div class="envoltura-tabla"><table class="tabla tabla-usuarios"><thead><tr>
          <th>Usuario</th><th>Rol</th><th>Estado</th>
          <th class="num" title="${EXPLICA.creadas}">Creadas</th><th class="num" title="${EXPLICA.actualizadas}">Actualizadas</th>
          <th class="num" title="${EXPLICA.con_datos_nuevos}">Datos nuevos</th><th class="num" title="${EXPLICA.cedulas}">Cédulas</th>
          <th class="num" title="${EXPLICA.puesto_mesa}">Puesto · mesa</th><th class="num" title="${EXPLICA.acercamientos}">Acercamientos</th>
          <th class="num" title="${EXPLICA.contactadas}">Contactadas</th><th class="num" title="${EXPLICA.calidad}">Calidad</th>
          <th title="${EXPLICA.ultimo_ingreso}">Último ingreso</th><th>Alertas</th><th></th></tr></thead>
        <tbody>${filas.map((u) => {
          const p = u.indicadores?.planillero || {};
          const k = u.indicadores?.consultor || {};
          const cal = p.calidad || {};
          const comp = p.completados || {};
          return html`<tr data-fila="${u.id}" class="${u.activo ? '' : 'inactivo'}">
            <td data-titulo="Usuario"><a class="nombre" href="/usuarios/${u.id}" data-ruta>${u.usuario}</a><div class="sec">${u.nombre}</div></td>
            <td data-titulo="Rol">${rolHtml(u.rol)}</td><td data-titulo="Estado">${estadoHtml(u)}</td>
            <td class="num" data-titulo="Creadas"><span>${num(p.creadas)} <span class="sec">(${num(p.creadas_netas)})</span></span></td>
            <td class="num" data-titulo="Actualizadas">${num(p.actualizadas)}</td><td class="num" data-titulo="Datos nuevos">${num(p.con_datos_nuevos)}</td>
            <td class="num" data-titulo="Cédulas">${num(comp.cedula || 0)}</td><td class="num" data-titulo="Puesto · mesa">${num(comp.puesto || 0)} · ${num(comp.mesa || 0)}</td>
            <td class="num" data-titulo="Acercamientos">${num(k.acercamientos)}</td><td class="num" data-titulo="Contactadas">${num(k.contactadas)}</td>
            <td class="num" data-titulo="Calidad">${num(cal.telefonos_luego_equivocados)} · ${num(cal.cedulas_en_conflicto)} · ${num(cal.duplicados_unidos)}</td>
            <td data-titulo="Último ingreso">${fecha(u.ultimo_ingreso, true)}</td><td data-titulo="Alertas"><div class="chips">${alertasHtml(u)}</div></td>
            <td class="celda-acciones">${gestionable(u) ? html`<button class="btn chico" data-acciones="${u.id}" aria-haspopup="dialog">Acciones</button>` : ''}</td></tr>`;
        })}</tbody></table></div>`
        : html`<div class="tarjeta vacio"><b>Todavía no hay usuarios</b>Cree planilleros para el trabajo de campo y consultores para llamar.</div>`}
      <section class="tarjeta avance">
        <header><h2>Avance por zona</h2>
          <div class="segmentado" role="group" aria-label="Agrupar por"><button data-por="lugar" aria-pressed="${por === 'lugar'}">Barrios y veredas</button><button data-por="area" aria-pressed="${por === 'area'}">Áreas</button></div></header>
        <div id="avance"><div class="cargando"><div class="giro"></div></div></div>
      </section>`);
    enlazarPeriodo(el, (d, h) => { desde = d; hasta = h; recordar(); pintar(); });
    pintarAvance();
  }

  function recordar() {
    const p = new URLSearchParams();
    if (desde) p.set('desde', desde);
    if (hasta) p.set('hasta', hasta);
    if (por === 'area') p.set('por', 'area');
    const s = p.toString();
    history.replaceState({}, '', url('/usuarios' + (s ? `?${s}` : '')));
  }

  async function pintarAvance() {
    const c = $('#avance', el);
    try {
      const a = await api.get('/api/usuarios/avance', { por });
      if (!c?.isConnected) return;
      montar(c, a.filas.length ? html`<div class="envoltura-tabla"><table class="tabla tabla-avance"><thead><tr><th>Zona</th><th>Responsables</th>
          <th class="num" title="Personas vigentes (sin fallecidas ni quienes ya no viven en Yondó)">Personas</th><th class="num">Con cédula</th>
          <th class="num">Puesto y mesa</th><th class="num" title="Con al menos un número usable">Teléfono</th><th class="num">Contactadas</th></tr></thead>
        <tbody>${a.filas.map((z) => html`<tr style="cursor:default"><td data-titulo="Zona"><b>${titulo(z.nombre || '') || `#${z.id}`}</b></td>
          <td data-titulo="Responsables">${z.responsables.map((r) => r.usuario).join(', ')}</td><td class="num" data-titulo="Personas">${num(z.personas)}</td>
          <td class="num" data-titulo="Con cédula">${z.pct_cedula} %</td><td class="num" data-titulo="Puesto y mesa">${z.pct_puesto_mesa} %</td>
          <td class="num" data-titulo="Teléfono">${z.pct_telefono} %</td><td class="num" data-titulo="Contactadas">${z.pct_contactadas} %</td></tr>`)}</tbody></table></div>`
        : html`<p class="sec">Ningún usuario activo tiene ${por === 'area' ? 'áreas' : 'barrios o veredas'} asignados.</p>`);
    } catch (e) {
      if (c?.isConnected) montar(c, html`<p class="sec">${e.message}</p>`);
    }
  }

  el.addEventListener('click', async (e) => {
    if (e.target.closest('#nuevo')) { if (await dialogoUsuario()) pintar(); return; }
    const b = e.target.closest('[data-acciones]');
    if (b) {
      const u = filas.find((x) => String(x.id) === b.dataset.acciones);
      const elegida = u && await elegirAccion(u);
      if (elegida && await accion(elegida, u)) pintar();
      return;
    }
    const p = e.target.closest('[data-por]');
    if (p) {
      por = p.dataset.por;
      for (const x of el.querySelectorAll('[data-por]')) x.setAttribute('aria-pressed', x.dataset.por === por);
      recordar();
      pintarAvance();
    }
  });
  await pintar();
}

// ───────── Detalle de un usuario ─────────

/** Detalle de un usuario (/usuarios/:id): indicadores con su serie, sesiones, actividad reciente y asignación. */
export async function vistaUsuario(el, { params, q }) {
  const id = params[0];
  let desde = q.get('desde') || '';
  let hasta = q.get('hasta') || '';
  let agrupar = ['semana', 'mes'].includes(q.get('agrupar')) ? q.get('agrupar') : 'dia';
  let u = null;

  async function pintar() {
    let ind, aud, cat, areas;
    try {
      [u, ind, aud, cat, areas] = await Promise.all([api.get(`/api/usuarios/${id}`),
        api.get(`/api/usuarios/${id}/indicadores`, { desde, hasta, agrupar }), api.get('/api/auditoria', { uid: id }),
        api.catalogos(), areasDisponibles()]);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 404) { montar(el, html`<div class="vacio"><b>No existe ese usuario</b><a href="/usuarios" data-ruta>Volver a Usuarios</a></div>`); return; }
      throw e;
    }
    if (!el.isConnected) return;
    const lugares = new Map(cat.lugares.map((l) => [l.id, l.nombre]));
    const nombresAreas = new Map(areas.map((a) => [a.id ?? a._id, a.nombre]));
    montar(el, html`
      <div class="miga"><a href="/usuarios" data-ruta>Usuarios</a> › ${u.usuario}</div>
      <div class="cabecera"><div><h1>${u.nombre || u.usuario}</h1><div class="sub">${u.usuario} · ${rolHtml(u.rol)} · ${estadoHtml(u)} ${alertasHtml(u)}</div></div>
        <div class="acciones">${botonesAccion(u)}</div></div>
      ${periodoHtml(ind.desde, ind.hasta)}
      <div class="segmentado agrupar" role="group" aria-label="Agrupar la serie">${[['dia', 'Por día'], ['semana', 'Por semana'], ['mes', 'Por mes']].map(([k, t]) => html`<button data-agrupar="${k}" aria-pressed="${k === agrupar}">${t}</button>`)}</div>
      <div id="indicadores"></div>
      <div class="rejilla r-12">
        <section class="tarjeta c-6"><h2>Asignación</h2>
          ${u.rol === 'coordinador' ? html`<p class="sec">Coordinador: trabaja sobre toda la base, sin asignación.</p>`
            : (u.asignacion.lugares.length || u.asignacion.areas.length) ? html`<div class="chips">
            ${u.asignacion.lugares.map((l) => html`<span class="chip borde">${titulo(lugares.get(l) || `Lugar ${l}`)}</span>`)}
            ${u.asignacion.areas.map((a) => html`<span class="chip azul">${nombresAreas.get(a) || `Área ${a}`}</span>`)}</div>`
            : html`<p class="sec">Sin asignación: trabaja sobre toda la base.</p>`}
          <dl class="ficha-usuario"><dt>Teléfono</dt><dd>${u.telefono || '—'}</dd><dt>Creado</dt><dd>${fecha(u.creado_en, true)}</dd>
            <dt>Último ingreso</dt><dd>${fecha(u.ultimo_ingreso, true)}</dd>
            ${u.debe_cambiar_clave ? html`<dt>Clave temporal</dt><dd>${u.clave_vencida ? 'vencida' : `vence el ${fecha(u.clave_temporal_vence, true)}`}</dd>` : ''}
            ${u.desactivado_en ? html`<dt>Desactivado</dt><dd>${fecha(u.desactivado_en, true)}</dd>` : ''}</dl>
        </section>
        <section class="tarjeta c-6"><h2>Sesiones activas</h2>
          ${u.sesiones.length ? html`<ul class="lista-simple">${u.sesiones.map((s) => html`<li><b>${fecha(s.ultima_actividad || s.creada, true)}</b> <span class="sec">desde ${s.ip || '—'} · ${s.agente || ''}</span></li>`)}</ul>`
            : html`<p class="sec">Ninguna.</p>`}
          ${u.intentos_recientes.length ? html`<h3 class="sub-asignacion">Ingresos fallidos recientes</h3><ul class="lista-simple">${u.intentos_recientes.map((x) => html`<li>${fecha(x.ts, true)} <span class="sec">desde ${x.ip || '—'}</span></li>`)}</ul>` : ''}
        </section>
        <section class="tarjeta c-12"><header><h2>Actividad reciente</h2><span class="nota">${num(aud.total)} acciones registradas (últimas 100)</span></header>
          ${aud.filas.length ? html`<div class="envoltura-tabla" style="max-height:420px;overflow:auto"><table class="tabla"><thead><tr><th>Cuándo</th><th>Acción</th><th>Sobre</th></tr></thead>
            <tbody>${aud.filas.map((a) => html`<tr style="cursor:default"><td>${fecha(a.ts, true)}</td><td>${(a.accion || '').replace(/_/g, ' ')}</td>
              <td>${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>persona ${a.entidad_id}</a>` : a.entidad ? `${a.entidad} ${a.entidad_id ?? ''}` : ''}</td></tr>`)}</tbody></table></div>`
            : html`<p class="sec">Sin acciones registradas.</p>`}
        </section>
      </div>`);
    pintarIndicadores($('#indicadores', el), ind, { rol: u.rol });
    enlazarPeriodo(el, (d, h) => { desde = d; hasta = h; recordar(); pintar(); });
  }

  function recordar() {
    const p = new URLSearchParams();
    if (desde) p.set('desde', desde);
    if (hasta) p.set('hasta', hasta);
    if (agrupar !== 'dia') p.set('agrupar', agrupar);
    const s = p.toString();
    history.replaceState({}, '', url(`/usuarios/${id}` + (s ? `?${s}` : '')));
  }

  el.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-accion]');
    if (b && u) { if (await accion(b.dataset.accion, u)) pintar(); return; }
    const g = e.target.closest('[data-agrupar]');
    if (g) { agrupar = g.dataset.agrupar; recordar(); pintar(); }
  });
  await pintar();
}
