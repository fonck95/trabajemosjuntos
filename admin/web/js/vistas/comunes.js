// Piezas compartidas entre vistas: alta de personas con búsqueda en vivo (7.6), «Completar» (7.3), autorización,
// puesto y mesa, «Estoy en su casa» (GPS), el 409 `cambiada` y el selector de ubicación en el mapa.
import { api, ErrorApi, nuevaClave, registrarPendiente, sesion } from '../api.js';
import { BASES, CASCO, baseSegunTema, cargarMapLibre, dentroDeYondo } from '../mapa3d.js';
import {
  CAMPOS_FALTAN, CAMPOS_NO_DISPONIBLE, CANALES_AUTORIZACION, ETIQUETAS_CAMPOS, MAS_DATOS, MEDIOS_AUTORIZACION,
  MEDIOS_POR_ROL, MOTIVOS_NO_DISPONIBLE, SEXOS, TIPOS_DOCUMENTO,
} from '../modelo.js';
import { $, $$, aviso, avisoError, datosForm, debounce, dialogo, hoy, html, titulo } from '../ui.js';

/** ¿Administrador o coordinador? Lo que la especificación reserva a «A» en el manejo de datos (adenda 1). */
export const administra = () => sesion.rol === 'admin' || sesion.rol === 'coordinador';

export function opcionesLugares(cat, valor) {
  const grupos = { barrio: 'Barrios del casco', sector: 'Sectores', centro_poblado: 'Centros poblados', corregimiento: 'Corregimientos', caserio: 'Caseríos', vereda: 'Veredas' };
  return html`<option value="">Sin definir</option>${Object.entries(grupos).map(([t, g]) => {
    const ls = (cat.lugares || []).filter((l) => l.tipo === t);
    return ls.length ? html`<optgroup label="${g}">${ls.map((l) => html`<option value="${l.id}" ${String(valor) === String(l.id) ? 'selected' : ''}>${titulo(l.nombre)}</option>`)}</optgroup>` : '';
  })}`;
}

// ───────── Puesto y mesa (1.4) ─────────

/** Valor del selector de puesto para una `votacion`: el id del catálogo, «otro», «otro_municipio» o «no_inscrito». */
export function valorPuesto(v) {
  if (!v) return '';
  if (v.donde === 'otro_municipio') return 'otro_municipio';
  if (v.donde === 'no_inscrito') return 'no_inscrito';
  if (v.puesto_id != null) return String(v.puesto_id);
  return v.puesto_texto ? 'otro' : '';
}

/** Opciones del puesto: catálogo vigente agrupado en cabecera y rural, más «Otro», «Otro municipio» y «No inscrito». */
export function opcionesPuesto(cat, valor) {
  const puestos = cat.puestos || [];
  const grupo = (area, t) => {
    const ps = puestos.filter((x) => (area === 'rural' ? x.area === 'rural' : x.area !== 'rural'));
    return ps.length ? html`<optgroup label="${t}">${ps.map((x) => html`<option value="${x.id}" ${String(valor) === String(x.id) ? 'selected' : ''}>${x.codigo ? x.codigo + ' · ' : ''}${titulo(x.nombre)}</option>`)}</optgroup>` : '';
  };
  const extra = [['otro', 'Otro (sin verificar)'], ['otro_municipio', 'Vota en otro municipio'], ['no_inscrito', 'No está inscrito']];
  return html`<option value="">—</option>${grupo('cabecera', 'Cabecera')}${grupo('rural', 'Rural')}
    <optgroup label="Otros">${extra.map(([v, t]) => html`<option value="${v}" ${valor === v ? 'selected' : ''}>${t}</option>`)}</optgroup>`;
}

/** Campos de puesto y mesa a partir del selector: {puesto_id | puesto_texto | donde, municipio, mesa}. */
export function cuerpoVotacion(valor, { texto = '', municipio = '', mesa = '' } = {}) {
  const c = {};
  if (valor === 'otro') { c.puesto_texto = texto || null; c.donde = 'yondo'; } else if (valor === 'otro_municipio') { c.donde = 'otro_municipio'; c.municipio = municipio || null; } else if (valor === 'no_inscrito') c.donde = 'no_inscrito';
  else if (valor) { c.puesto_id = Number(valor); c.donde = 'yondo'; }
  if (mesa !== '' && mesa != null && valor !== 'no_inscrito' && valor !== 'otro_municipio') c.mesa = String(mesa);
  return c;
}

/** Tope de mesa del puesto elegido (99 si no se sabe). */
export const mesaMax = (cat, valor) => (cat.puestos || []).find((x) => String(x.id) === String(valor))?.mesas || 99;

/** Campos de puesto y mesa para un formulario: muestran el texto o el municipio según la opción. */
export function camposVotacion(cat, v = {}, { prefijo = '' } = {}) {
  const val = valorPuesto(v);
  return html`<label class="campo"><span>Puesto de votación</span><select name="${prefijo}puesto" data-puesto>${opcionesPuesto(cat, val)}</select></label>
    <label class="campo" data-solo="otro" ${val === 'otro' ? '' : 'hidden'}><span>¿Cuál puesto?</span><input name="${prefijo}puesto_texto" maxlength="120" value="${v?.puesto_texto ?? ''}"></label>
    <label class="campo" data-solo="otro_municipio" ${val === 'otro_municipio' ? '' : 'hidden'}><span>Municipio</span><input name="${prefijo}municipio" maxlength="80" value="${v?.municipio ?? ''}"></label>
    <label class="campo" data-mesa ${val === 'otro_municipio' || val === 'no_inscrito' ? 'hidden' : ''}><span>Mesa</span><input name="${prefijo}mesa" type="number" min="1" max="${mesaMax(cat, val)}" inputmode="numeric" value="${v?.mesa ?? ''}"></label>`;
}

/** Enlaza un selector de puesto: muestra u oculta el texto, el municipio y la mesa, y ajusta el tope de la mesa. */
export function enlazarVotacion(raiz, cat) {
  raiz.addEventListener('change', (e) => {
    const s = e.target.closest('[data-puesto]');
    if (!s) return;
    const cont = s.closest('form') || raiz;
    for (const x of $$('[data-solo]', cont)) x.hidden = x.dataset.solo !== s.value;
    const mesa = $('[data-mesa]', cont);
    if (mesa) {
      mesa.hidden = s.value === 'otro_municipio' || s.value === 'no_inscrito';
      $('input', mesa).max = mesaMax(cat, s.value);
    }
  });
}

// ───────── Autorización (1.6) ─────────

/** Medios que puede usar el rol: P escrito, verbal presencial o formulario; C por teléfono o mensaje; A y K todos. */
export const mediosDelRol = () => (administra()
  ? Object.keys(MEDIOS_AUTORIZACION).filter((m) => !['migrado', 'declarado_planilla', 'fusion'].includes(m))
  : MEDIOS_POR_ROL[sesion.rol] || []);

/**
 * Bloque de autorización obligatoria y sin valor por defecto: «Sí» pide medio, canales, evidencia y mayor de 18; el
 * aviso de privacidad va en un recuadro. `name` de los campos con el prefijo `aut_`.
 */
export function camposAutorizacion(cat, { obligatoria = true, estados = ['si', 'no', 'pendiente'] } = {}) {
  const t = { si: 'Sí autoriza', no: 'No autoriza', pendiente: 'Todavía no responde', revocada: 'Revocó' };
  const avisoTexto = cat.aviso_privacidad?.texto;
  return html`<fieldset class="bloque-autorizacion-ficha ancho">
    <legend>Autorización de tratamiento de datos${obligatoria ? ' *' : ''}</legend>
    ${avisoTexto ? html`<div class="recuadro-aviso"><b>Aviso de privacidad${cat.aviso_privacidad?.version ? ` (${cat.aviso_privacidad.version})` : ''}</b><p>${avisoTexto}</p>
      ${cat.aviso_privacidad?.responsable ? html`<small>Responsable: ${cat.aviso_privacidad.responsable}${cat.aviso_privacidad?.contacto ? ' · ' + cat.aviso_privacidad.contacto : ''}</small>` : ''}</div>`
      : html`<div class="recuadro-aviso"><b>Aviso de privacidad</b><p>Lea al titular el aviso de privacidad vigente antes de pedir su autorización.</p></div>`}
    <div class="opciones-radio" role="radiogroup">${estados.map((e) => html`<label class="chip opcion"><input type="radio" name="aut_estado" value="${e}" ${obligatoria ? 'required' : ''}> ${t[e]}</label>`)}</div>
    <div class="form" data-aut-si hidden>
      <label class="campo"><span>Medio</span><select name="aut_medio">${mediosDelRol().map((m) => html`<option value="${m}">${MEDIOS_AUTORIZACION[m] || m}</option>`)}</select></label>
      <div class="campo ancho"><span>Canales autorizados</span><div class="chips">${Object.entries(CANALES_AUTORIZACION).map(([k, tx]) => html`<label class="chip opcion"><input type="checkbox" name="aut_canal" value="${k}"> ${tx}</label>`)}</div></div>
      <label class="campo ancho"><span>Evidencia</span><input name="aut_evidencia" maxlength="300" placeholder="Formato firmado, planilla 14, folio 3"></label>
      <label class="casilla ancho"><input type="checkbox" name="aut_mayor"> Declara ser mayor de 18 años</label>
    </div>
  </fieldset>`;
}

/** Enlaza el bloque: «Sí» despliega los datos del evento. */
export function enlazarAutorizacion(raiz) {
  raiz.addEventListener('change', (e) => {
    if (e.target.name !== 'aut_estado') return;
    const f = e.target.closest('form') || raiz;
    for (const x of $$('[data-aut-si]', f)) x.hidden = e.target.value !== 'si';
  });
}

/** Lee el bloque; devuelve {estado, medio, canales, evidencia, mayor_declarado} o null, y el error si falta algo. */
export function leerAutorizacion(form) {
  const est = form.querySelector('[name="aut_estado"]:checked')?.value;
  if (!est) return { aut: null };
  const aut = { estado: est };
  if (est === 'si') {
    const campo = (n) => form.querySelector(`[name="${n}"]`);
    aut.medio = campo('aut_medio')?.value || null;
    aut.canales = $$('[name="aut_canal"]:checked', form).map((x) => x.value);
    aut.evidencia = campo('aut_evidencia')?.value.trim() || null;
    aut.mayor_declarado = !!campo('aut_mayor')?.checked;
    if (!administra()) {
      if (!aut.canales.length) return { aut, error: 'Marque al menos un canal autorizado' };
      if (!aut.evidencia) return { aut, error: 'Escriba la evidencia de la autorización' };
      if (!aut.mayor_declarado) return { aut, error: 'La autorización exige que declare ser mayor de 18 años' };
    }
  }
  return { aut };
}

// ───────── Filas de personas (con la proyección del rol) ─────────

/** Cédula de una fila o ficha: completa para A y K, «···123» para P, o «Sin cédula». */
export const textoCedula = (f) => (f?.cedula ? `${f.tipo_documento || 'CC'} ${f.cedula}`
  : f?.cedula_ult3 ? `${f.tipo_documento || 'CC'} ···${f.cedula_ult3}` : null);
/** Teléfono de una fila: el número para A y K, «···2233» para P. */
export const textoTelefono = (f) => f?.telefono || f?.telefono_mascara || null;

/** Lo que falta de una ficha: `faltan` del servidor o, si no viene, lo que se ve vacío. */
export function faltanDe(p) {
  if (Array.isArray(p?.faltan)) return p.faltan;
  const nd = p?.no_disponible || {};
  const vacio = {
    cedula: !p?.cedula && !p?.cedula_ult3 && !p?.tiene_cedula, telefono: !p?.telefono && !(p?.telefonos || []).length && !p?.telefono_mascara,
    sexo: !p?.sexo, edad: p?.edad == null && !p?.fecha_nacimiento && !p?.rango_edad, lugar: !p?.lugar_id && !p?.lugar,
    puesto: !p?.votacion?.puesto_id && !p?.votacion?.puesto_texto && !p?.votacion?.donde && !p?.puesto_votacion && !p?.puesto,
    mesa: !p?.votacion?.mesa && !p?.mesa, direccion: !p?.direccion, autorizacion: (p?.consentimiento || 'pendiente') === 'pendiente',
  };
  return CAMPOS_FALTAN.filter((c) => vacio[c] && !nd[c]);
}

export const chipsFaltan = (faltan) => (faltan?.length
  ? html`<span class="faltan" title="Datos que faltan">${faltan.map((c) => html`<span class="chip borde">${ETIQUETAS_CAMPOS[c] || c}</span>`)}</span>` : '');

// ───────── «No lo tiene / No sabe» ─────────

const noSabe = (campo) => (CAMPOS_NO_DISPONIBLE.includes(campo)
  ? html`<label class="no-sabe"><select name="nd_${campo}" aria-label="Si no lo tiene o no lo sabe"><option value="">Lo tiene</option>${Object.entries(MOTIVOS_NO_DISPONIBLE).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>` : '');

async function marcarNoDisponibles(pid, form) {
  let ficha = null;
  for (const x of $$('select[name^="nd_"]', form)) {
    if (!x.value || x.disabled) continue;
    ficha = await api.post(`/api/personas/${pid}/no-disponible`, { campo: x.name.slice(3), motivo: x.value });
  }
  return ficha;
}

// ───────── Completar (7.3) ─────────

/**
 * «Completar» desde Habitantes o una reunión: paso 1 con solo lo que falta (cada campo con «No lo tiene / No sabe»)
 * y el paso opcional «Más datos» con chips de un toque. Guarda con `PATCH ?modo=completar` e Idempotency-Key.
 * Resuelve con {ficha, siguiente} («Guardar y siguiente») o null.
 */
export async function dialogoCompletar(p, cat, { siguiente = false } = {}) {
  const faltan = faltanDe(p);
  const hay = (c) => faltan.includes(c);
  const v = p.votacion || {};
  let clave = nuevaClave();
  const { el, cerrar, listo } = dialogo({
    titulo: `Completar · ${titulo(p.nombre || '')}`,
    cuerpo: html`<form class="form una-columna" id="f-completar" novalidate>
      ${faltan.length ? '' : html`<p class="sec ancho">No le falta ningún dato básico. Puede agregar «Más datos».</p>`}
      ${hay('cedula') ? html`<div class="grupo-campo ancho"><span class="titulo-campo">Documento</span>
        <div class="fila-campos"><select name="tipo_documento" aria-label="Tipo de documento">${Object.entries(TIPOS_DOCUMENTO).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select>
        <input name="cedula" inputmode="numeric" autocomplete="off" placeholder="Número" aria-label="Número de documento" maxlength="15">
        <input name="cedula_confirmacion" inputmode="numeric" autocomplete="off" placeholder="Repita el número" aria-label="Repita el número" maxlength="15"></div>
        <label class="casilla"><input type="checkbox" name="cedula_verificada"> Vi el documento</label>${noSabe('cedula')}</div>` : ''}
      ${hay('telefono') ? html`<div class="grupo-campo ancho"><span class="titulo-campo">Teléfono</span>
        <div class="fila-campos"><input name="telefono" inputmode="tel" placeholder="Celular" aria-label="Celular" maxlength="30"><input name="telefono2" inputmode="tel" placeholder="Otro teléfono" aria-label="Otro teléfono" maxlength="30"></div>${noSabe('telefono')}</div>` : ''}
      ${hay('sexo') ? html`<div class="grupo-campo ancho"><span class="titulo-campo">Sexo</span><div class="opciones-radio">${Object.entries(SEXOS).map(([k, t]) => html`<label class="chip opcion"><input type="radio" name="sexo" value="${k}"> ${t}</label>`)}</div>${noSabe('sexo')}</div>` : ''}
      ${hay('edad') ? html`<div class="grupo-campo ancho"><span class="titulo-campo">Fecha de nacimiento o edad</span>
        <div class="fila-campos"><input type="date" name="fecha_nacimiento" max="${hoy()}" aria-label="Fecha de nacimiento"><input type="number" name="edad" min="0" max="120" inputmode="numeric" placeholder="Edad" aria-label="Edad"></div>${noSabe('edad')}</div>` : ''}
      ${hay('lugar') ? html`<label class="campo ancho"><span>Barrio o vereda</span><select name="lugar_id">${opcionesLugares(cat)}</select></label>` : ''}
      ${hay('direccion') ? html`<label class="campo ancho"><span>Dirección</span><input name="direccion" maxlength="240" placeholder="CL 49 # 45-12"></label>` : ''}
      ${hay('puesto') || hay('mesa') ? html`<div class="grupo-campo ancho"><span class="titulo-campo">Puesto y mesa</span><div class="form">${camposVotacion(cat, v)}</div>${noSabe(hay('puesto') ? 'puesto' : 'mesa')}</div>` : ''}
      ${hay('autorizacion') ? camposAutorizacion(cat, { obligatoria: false, estados: ['si', 'no'] }) : ''}
      <details class="mas-datos ancho" ${faltan.length ? '' : 'open'}><summary>Más datos</summary>
        ${MAS_DATOS.map(([k, t, ops]) => html`<div class="grupo-campo"><span class="titulo-campo">${t}</span><div class="chips" data-chips="${k}">
          ${ops.map((o) => html`<button type="button" class="chip" data-valor="${o}" aria-pressed="${valorMas(p, k) === o}">${o}</button>`)}</div></div>`)}
      </details>
    </form>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button>${siguiente ? html`<button class="btn oscuro" data-guardar="siguiente">Guardar y siguiente</button>` : ''}<button class="btn primario" data-guardar="uno">Guardar</button>`,
    // Tocar el fondo o Escape con algo escrito pregunta antes de perderlo (los chips de «Más datos» también cuentan);
    // mientras se guarda no hacen nada: lo escrito ya va al servidor y al terminar se cierra solo
    sucio: () => tocado,
    ocupado: () => enCurso,
  });
  const form = $('#f-completar', el);
  enlazarVotacion(form, cat);
  enlazarAutorizacion(form);
  let tocado = false, enCurso = false, resultado = null;
  const quitarPendiente = registrarPendiente(() => tocado);
  form.addEventListener('input', () => { tocado = true; });
  form.addEventListener('click', (e) => {
    const c = e.target.closest('[data-chips] [data-valor]');
    if (!c) return;
    const presionado = c.getAttribute('aria-pressed') === 'true';
    for (const b of c.parentElement.children) b.setAttribute('aria-pressed', 'false');
    c.setAttribute('aria-pressed', String(!presionado));
    tocado = true;
  });

  function cuerpo() {
    const d = datosForm(form);
    const c = {};
    for (const k of ['tipo_documento', 'cedula', 'cedula_verificada', 'telefono', 'telefono2', 'fecha_nacimiento', 'edad', 'direccion']) {
      if (d[k] != null && d[k] !== '' && d[k] !== false) c[k] = d[k];
    }
    if (!c.cedula) { delete c.tipo_documento; delete c.cedula_verificada; }
    const sexo = form.querySelector('[name="sexo"]:checked')?.value;
    if (sexo) c.sexo = sexo;
    if (d.lugar_id) c.lugar_id = Number(d.lugar_id);
    if (form.puesto) Object.assign(c, cuerpoVotacion(form.puesto.value, { texto: d.puesto_texto, municipio: d.municipio, mesa: d.mesa }));
    for (const [k] of MAS_DATOS) {
      const b = form.querySelector(`[data-chips="${k}"] [aria-pressed="true"]`);
      const antes = valorMas(p, k);
      const val = b?.dataset.valor ?? null;
      if (val === antes || val == null) continue;
      if (k === 'jefe_hogar') c[k] = val === 'Sí';
      else if (k === 'estrato' || k === 'personas_hogar') c[k] = Number(val);
      else c[k] = val;
    }
    return { c, d };
  }

  async function guardar(seguir) {
    if (enCurso) return;
    const { c, d } = cuerpo();
    if (c.cedula && c.cedula !== d.cedula_confirmacion) { aviso('Los dos números del documento no coinciden', 'error'); return; }
    const { aut, error } = form.querySelector('[name="aut_estado"]') ? leerAutorizacion(form) : { aut: null };
    if (error) { aviso(error, 'error'); return; }
    enCurso = true;
    for (const b of $$('[data-guardar]', el)) b.disabled = true;
    try {
      let ficha = null;
      if (Object.keys(c).length) ficha = await api.patch(`/api/personas/${p.id}?modo=completar`, c, { clave });
      clave = nuevaClave();
      ficha = (await marcarNoDisponibles(p.id, form)) || ficha;
      if (aut) ficha = await api.post(`/api/personas/${p.id}/autorizacion`, aut, { clave: nuevaClave() });
      for (const a of ficha?.avisos || []) aviso(typeof a === 'string' ? a : a.mensaje || '', 'ok', 7000);
      resultado = { ficha: ficha || p, siguiente: seguir };
      tocado = false;
      cerrar(resultado);
      aviso(`${titulo(p.nombre || '')}: datos guardados`);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado >= 400 && e.estado < 500 && e.codigo !== 'en_proceso') clave = nuevaClave();
      if (e instanceof ErrorApi && e.codigo === 'cedula_ocupada') aviso(`${e.message}${e.detalle?.nombre ? ` (${e.detalle.nombre})` : ''}`, 'error', 8000);
      else avisoError(e);
    } finally {
      enCurso = false;
      for (const b of $$('[data-guardar]', el)) b.disabled = false;
    }
  }
  for (const b of $$('[data-guardar]', el)) b.addEventListener('click', () => guardar(b.dataset.guardar === 'siguiente'));
  form.addEventListener('submit', (e) => { e.preventDefault(); guardar(false); });
  const r = await listo;
  quitarPendiente();
  return r || resultado;
}

function valorMas(p, k) {
  const v = p?.[k];
  if (v == null || v === '') return null;
  if (k === 'jefe_hogar') return v ? 'Sí' : 'No';
  return String(v);
}

// ───────── Nueva persona (7.6) ─────────

/**
 * Alta de una persona con búsqueda en vivo de parecidas. `prellenado` trae lo buscado ({nombre|cedula|telefono});
 * `hogar` copia dirección, lugar, ficha y ubicación («Nueva persona en este hogar»). `reunionId` la registra además
 * como asistente. `alCrear(p)` recibe la ficha nueva o {id, existente: true} si era una que ya estaba.
 */
export function formularioNuevaPersona({ cat, reunionId = null, nombreInicial = '', prellenado = {}, hogar = null, alCrear }) {
  const necesidades = (cat.etiquetas || []).filter((e) => e.grupo === 'necesidad');
  const ini = { nombre: nombreInicial, ...prellenado };
  let clave = nuevaClave();
  const { el, cerrar, listo } = dialogo({
    titulo: reunionId ? 'Registrar asistente nuevo' : hogar ? 'Nueva persona en este hogar' : 'Nueva persona',
    cuerpo: html`<form class="form una-columna" id="f-nueva" novalidate>
      ${hogar ? html`<p class="aviso-legal ancho">Se copian la dirección, el barrio${hogar.ficha ? ', la ficha del hogar' : ''}${hogar.lat != null ? ' y la ubicación' : ''} de ${titulo(hogar.nombre || 'la otra persona')}.</p>` : ''}
      <label class="campo ancho"><span>Nombre completo *</span><input name="nombre" required minlength="3" maxlength="160" autocomplete="off" value="${ini.nombre || ''}"></label>
      <div class="grupo-campo ancho"><span class="titulo-campo">Documento</span>
        <div class="fila-campos"><select name="tipo_documento" aria-label="Tipo de documento">${Object.entries(TIPOS_DOCUMENTO).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select>
        <input name="cedula" inputmode="numeric" autocomplete="off" placeholder="Número" aria-label="Número de documento" maxlength="15" value="${ini.cedula || ''}">
        <input name="cedula_confirmacion" inputmode="numeric" autocomplete="off" placeholder="Repita el número" aria-label="Repita el número" maxlength="15"></div>
        <label class="casilla"><input type="checkbox" name="cedula_verificada"> Vi el documento</label></div>
      <div class="grupo-campo ancho"><span class="titulo-campo">Teléfonos</span>
        <div class="fila-campos"><input name="telefono" inputmode="tel" placeholder="Celular" aria-label="Celular" maxlength="30" value="${ini.telefono || ''}"><input name="telefono2" inputmode="tel" placeholder="Otro teléfono" aria-label="Otro teléfono" maxlength="30"></div></div>
      <div class="ancho" id="parecidas" aria-live="polite"></div>
      <div class="grupo-campo ancho"><span class="titulo-campo">Sexo</span><div class="opciones-radio">${Object.entries(SEXOS).map(([k, t]) => html`<label class="chip opcion"><input type="radio" name="sexo" value="${k}"> ${t}</label>`)}</div></div>
      <div class="grupo-campo ancho"><span class="titulo-campo">Fecha de nacimiento o edad</span>
        <div class="fila-campos"><input type="date" name="fecha_nacimiento" max="${hoy()}" aria-label="Fecha de nacimiento"><input name="edad" type="number" min="0" max="120" inputmode="numeric" placeholder="Edad" aria-label="Edad"></div></div>
      <label class="campo ancho"><span>Barrio o vereda</span><select name="lugar_id">${opcionesLugares(cat, hogar?.lugar_id)}</select></label>
      <label class="campo ancho"><span>Dirección</span><input name="direccion" maxlength="240" placeholder="CL 49 # 45-12" value="${hogar?.direccion || ''}"></label>
      <div class="grupo-campo ancho"><span class="titulo-campo">Puesto y mesa</span><div class="form">${camposVotacion(cat, {})}</div></div>
      ${necesidades.length ? html`<div class="campo ancho"><span>Necesidades</span><div class="chips">${necesidades.map((e) => html`<button type="button" class="chip" data-et="${e.id}" aria-pressed="false">${e.nombre}</button>`)}</div></div>` : ''}
      ${camposAutorizacion(cat)}
      <div class="ancho" id="conflicto" aria-live="polite"></div>
    </form>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="guardar">Guardar</button>`,
    sucio: () => tocado,
    ocupado: () => enCurso,
  });
  const form = $('#f-nueva', el);
  enlazarVotacion(form, cat);
  enlazarAutorizacion(form);
  let tocado = !!(ini.nombre || ini.cedula || ini.telefono);
  // Pendiente hasta que el diálogo termina de verdad (`listo`, más abajo): no se mira si sigue en la página, porque el
  // navegador puede cerrarlo solo y `dialogo` lo vuelve a abrir con lo escrito
  let terminado = false;
  const quitarPendiente = registrarPendiente(() => tocado && !terminado);
  form.addEventListener('click', (e) => { const c = e.target.closest('[data-et]'); if (c) { c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') !== 'true'); tocado = true; } });

  // Búsqueda en vivo (400 ms, 3 caracteres o más en nombre, documento o celular): «¿Es alguna de estas?» antes de seguir
  let turno = 0;
  const filasDe = (r) => (Array.isArray(r) ? r : r?.filas || r?.parecidas || []);
  const pintarParecidas = (lista, { titulo: t = '¿Es alguna de estas?', ayuda = 'Si es una de ellas, elíjala para no duplicarla.' } = {}) => {
    const cont = $('#parecidas', el);
    if (!lista.length) { cont.replaceChildren(); return; }
    cont.innerHTML = String(html`<div class="aviso-legal parecidas"><b>${t}</b> ${ayuda}
      <div class="resultados">${lista.map((x) => html`<div class="resultado"><div class="q"><b>${x.nombre}</b><small>${[textoCedula(x) || 'sin cédula', textoTelefono(x) || 'sin teléfono', titulo(x.lugar || '')].filter(Boolean).join(' · ')}</small>
        ${x.cedula_distinta ? html`<small class="chip ambar">Otra cédula: es otra persona</small>` : ''}</div>
        ${x.cedula_distinta ? '' : html`<button type="button" class="btn chico" data-elegir="${x.id}">Es esta</button>`}</div>`)}</div></div>`);
  };
  const buscarParecidas = debounce(async () => {
    const nombre = form.nombre.value.trim(), cedula = form.cedula.value.replace(/\D/g, ''), telefono = form.telefono.value.replace(/\D/g, '');
    if (nombre.length < 3 && cedula.length < 3 && telefono.length < 3) { pintarParecidas([]); return; }
    const mio = ++turno;
    try {
      const r = await api.get('/api/parecidas', { nombre: nombre.length >= 3 ? nombre : null, cedula: cedula.length >= 3 ? cedula : null, telefono: telefono.length >= 3 ? telefono : null });
      if (mio === turno && el.isConnected) pintarParecidas(filasDe(r));
    } catch { /* la búsqueda en vivo es una ayuda: el servidor revisa de nuevo al guardar */ }
  }, 400);
  form.addEventListener('input', (e) => {
    tocado = true;
    if (['nombre', 'cedula', 'telefono'].includes(e.target.name)) buscarParecidas();
  });
  // Deja de contar como pendiente (y se cancela la búsqueda por salir) cuando el diálogo termina de verdad (`listo`): si
  // el navegador lo cierra solo, `dialogo` lo vuelve a abrir con lo escrito y un 401 debe seguir sin recargar
  listo.then(() => { terminado = true; quitarPendiente(); buscarParecidas.cancel(); });
  if (ini.nombre || ini.cedula || ini.telefono) buscarParecidas();

  let forzar = false, enCurso = false;
  const boton = $('#guardar', el);

  function cuerpo() {
    const d = datosForm(form);
    const c = { nombre: d.nombre };
    for (const k of ['tipo_documento', 'cedula', 'telefono', 'telefono2', 'fecha_nacimiento', 'edad', 'direccion']) if (d[k] != null) c[k] = d[k];
    if (!c.cedula) delete c.tipo_documento;
    else c.cedula_verificada = !!d.cedula_verificada;
    const sexo = form.querySelector('[name="sexo"]:checked')?.value;
    if (sexo) c.sexo = sexo;
    c.lugar_id = d.lugar_id ? Number(d.lugar_id) : null;
    Object.assign(c, cuerpoVotacion(form.puesto.value, { texto: d.puesto_texto, municipio: d.municipio, mesa: d.mesa }));
    c.etiquetas = $$('[data-et][aria-pressed="true"]', form).map((b) => Number(b.dataset.et));
    if (hogar?.ficha) c.ficha = hogar.ficha;
    return { c, d };
  }

  // «Es esta» (y «Completar esa ficha con lo que escribí»): se completa esa ficha con lo que se escribió (solo lo que le
  // falte) y se abre. Es la otra forma de guardar este formulario y cuenta igual que «Guardar» como operación en curso
  // (`enCurso`, el `ocupado` del diálogo): mientras el PATCH va al servidor, Escape y el fondo no preguntan
  // «¿Descartar lo escrito?» (sería falso: se guarda igual y la página se va a esa ficha), y no se cruza con un «Guardar»
  // ni con otro «Es esta». Al terminar, `cerrar` cierra sin preguntar
  async function esEsta(id, origen) {
    if (enCurso) return;
    const { c } = cuerpo();
    delete c.nombre; delete c.etiquetas; delete c.ficha;
    for (const k of Object.keys(c)) if (c[k] == null) delete c[k];
    enCurso = true;
    boton.disabled = true;
    if (origen) origen.disabled = true;
    try {
      if (Object.keys(c).length) await api.patch(`/api/personas/${id}?modo=completar`, c, { clave: nuevaClave() });
      tocado = false;
      cerrar();
      alCrear?.({ id, existente: true });
    } catch (e) { avisoError(e); } finally {
      enCurso = false;
      boton.disabled = false;
      if (origen) origen.disabled = false;
    }
  }

  function mostrarConflicto(e) {
    const caja = $('#conflicto', el);
    const det = e.detalle || {};
    if (e.codigo === 'cedula_ocupada') {
      caja.innerHTML = String(html`<div class="aviso-legal"><b>${e.message || 'Esa cédula ya está registrada'}</b>${det.nombre ? html` en la ficha de ${det.nombre}${det.lugar ? ' · ' + titulo(det.lugar) : ''}` : ''}.
        <div class="fila-botones"><a class="btn chico" href="/personas/${det.id}" data-ruta>Abrir esa ficha</a>
        <button type="button" class="btn chico oscuro" data-completar-otra="${det.id}">Completar esa ficha con lo que escribí</button></div></div>`);
    } else if (e.codigo === 'suprimida') {
      caja.innerHTML = String(html`<div class="aviso-legal"><b>Esta persona pidió que se borraran sus datos.</b> No se puede volver a registrar sin una nueva autorización del titular. ${administra() ? 'El administrador puede registrarla de nuevo con su autorización escrita.' : 'Si el titular lo pide, avise al administrador.'}</div>`);
    } else if (e.codigo === 'parecidas' || det.parecidas) {
      forzar = true;
      pintarParecidas(det.parecidas || [], { titulo: '¿Es alguna de estas personas?', ayuda: 'Si es otra persona, pulse Guardar de nuevo.' });
      $('#parecidas', el).scrollIntoView({ block: 'nearest' });
    } else return false;
    return true;
  }

  el.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-elegir]');
    if (b) { esEsta(Number(b.dataset.elegir), b); return; }
    const o = ev.target.closest('[data-completar-otra]');
    if (o) { esEsta(Number(o.dataset.completarOtra), o); return; }
    // «Abrir esa ficha» navega: el diálogo se cierra (el enlace lo atiende app.js)
    if (ev.target.closest('#conflicto a[data-ruta]')) { tocado = false; cerrar(); }
  });

  async function guardar() {
    // Un doble clic (o Enter y clic) no debe crear dos fichas: una sola petición a la vez
    if (enCurso || !form.reportValidity()) return;
    const { c, d } = cuerpo();
    if (c.cedula && c.cedula !== d.cedula_confirmacion) { aviso('Los dos números del documento no coinciden', 'error'); form.cedula_confirmacion.focus(); return; }
    const { aut, error } = leerAutorizacion(form);
    if (!aut) { aviso('Indique si la persona autoriza el tratamiento de sus datos', 'error'); return; }
    if (error) { aviso(error, 'error'); return; }
    enCurso = true;
    boton.disabled = true;
    try {
      let p = await api.post('/api/personas', { ...c, autorizacion: aut, forzar, reunion_id: reunionId }, { clave });
      // La ubicación del hogar: si el alta no la trajo, se copia
      if (hogar?.lat != null && p?.id && p.lat == null) {
        try { p = await api.put(`/api/personas/${p.id}/ubicacion`, { lat: hogar.lat, lon: hogar.lon }); } catch { /* la ficha ya existe */ }
      }
      tocado = false;
      cerrar();
      aviso(`${p.nombre} quedó registrada`);
      for (const a of p?.avisos || []) aviso(typeof a === 'string' ? a : a.mensaje || '', 'ok', 7000);
      alCrear?.(p);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado >= 400 && e.estado < 500 && e.codigo !== 'en_proceso') clave = nuevaClave();
      if (!(e instanceof ErrorApi && e.estado === 409 && mostrarConflicto(e))) avisoError(e);
    } finally {
      enCurso = false;
      boton.disabled = false;
    }
  }
  boton.addEventListener('click', guardar);
  form.addEventListener('submit', (e) => { e.preventDefault(); guardar(); });
}

// ───────── «Estoy en su casa» (GPS) ─────────

/** Ubica a la persona con el GPS del celular: precisión de 50 m o mejor y dentro de Yondó. Resuelve con la ficha o null. */
export function ubicarConGps(pid) {
  if (!navigator.geolocation) { aviso('Este navegador no da la ubicación', 'error'); return Promise.resolve(null); }
  aviso('Buscando su ubicación…', 'ok', 4000);
  return new Promise((resolver) => {
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const { latitude: lat, longitude: lon, accuracy } = pos.coords;
      if (accuracy > 50) { aviso(`La señal del GPS es débil (±${Math.round(accuracy)} m). Salga a un lugar abierto e intente de nuevo.`, 'error', 7000); resolver(null); return; }
      if (!dentroDeYondo(lon, lat)) { aviso('Su ubicación queda fuera de Yondó', 'error'); resolver(null); return; }
      try {
        const p = await api.put(`/api/personas/${pid}/ubicacion`, { lat, lon, fuente: 'gps', precision_m: Math.round(accuracy) });
        aviso(`Ubicación guardada (±${Math.round(accuracy)} m)`);
        resolver(p);
      } catch (e) { avisoError(e); resolver(null); }
    }, (err) => {
      aviso(err.code === 1 ? 'Sin permiso para usar la ubicación: actívelo en el navegador' : 'No se pudo obtener la ubicación. Intente de nuevo.', 'error', 7000);
      resolver(null);
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });
}

// ───────── 409 `cambiada` (2.4) ─────────

/**
 * Otro guardó antes un campo que este formulario cambió. Muestra lo que hay ahora y ofrece «Usar el mío» (resuelve
 * con la `base` nueva para reenviar) o «Conservar el actual» (resuelve con null: se vuelve a cargar la ficha).
 */
export function dialogoCambiada(err, cuerpo) {
  const det = err.detalle || {};
  const actuales = det.valores_actuales || {};
  const campos = det.campos || Object.keys(actuales);
  const muestra = (v) => (v == null || v === '' ? '(vacío)' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  const { el, cerrar, listo } = dialogo({
    titulo: 'Alguien más cambió esta ficha',
    cuerpo: html`<p>Mientras usted editaba, otra persona guardó estos datos:</p>
      <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Dato</th><th>Ahora</th><th>Lo suyo</th></tr></thead><tbody>
      ${campos.map((k) => html`<tr style="cursor:default"><td>${ETIQUETAS_CAMPOS[k] || k.replace(/_/g, ' ')}</td><td>${muestra(actuales[k])}</td><td><b>${muestra(cuerpo?.[k])}</b></td></tr>`)}</tbody></table></div>`,
    pie: html`<button class="btn" data-conservar>Conservar el actual</button><button class="btn primario" data-mio>Usar el mío</button>`,
  });
  el.querySelector('[data-conservar]').addEventListener('click', () => cerrar({ conservar: true }));
  el.querySelector('[data-mio]').addEventListener('click', () => cerrar({ base: { ...(cuerpo?.base || {}), ...actuales } }));
  return listo.then((v) => (v?.base ? v.base : null));
}

/** Diálogo con un mapa para elegir un punto. Resuelve [lon, lat] o null. */
export async function elegirPunto({ titulo: t = 'Ubicar en el mapa', inicial = null, ayuda = '' } = {}) {
  const maplibregl = await cargarMapLibre();
  const { el, cerrar, listo } = dialogo({
    titulo: t, ancho: true,
    cuerpo: html`<p class="sec" style="margin-top:0">${ayuda || 'Haga clic en el mapa o arrastre el marcador hasta el lugar exacto.'}</p>
      <div class="minimapa" style="height:min(60vh,520px)" id="elegir-mapa"></div>`,
    pie: html`<span class="sec" id="coord" style="margin-right:auto"></span><button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="usar">Usar este punto</button>`,
  });
  const map = new maplibregl.Map({ container: $('#elegir-mapa', el), style: BASES[baseSegunTema()],
    center: inicial || CASCO.center, zoom: inicial ? 16 : 14, attributionControl: { compact: true }, cooperativeGestures: true });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  const marca = new maplibregl.Marker({ color: '#e3141b', draggable: true }).setLngLat(inicial || CASCO.center).addTo(map);
  // El servidor solo acepta puntos en Yondó y sus alrededores: fuera de ese rango no se deja elegir
  const mostrar = () => {
    const p = marca.getLngLat();
    const ok = dentroDeYondo(p.lng, p.lat);
    $('#coord', el).textContent = ok ? `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}` : 'Ese punto queda fuera de Yondó';
    $('#usar', el).disabled = !ok;
  };
  mostrar();
  marca.on('dragend', mostrar);
  map.on('click', (e) => { marca.setLngLat(e.lngLat); mostrar(); });
  let elegido = null;
  $('#usar', el).addEventListener('click', () => {
    const p = marca.getLngLat();
    if (!dentroDeYondo(p.lng, p.lat)) return;
    elegido = [p.lng, p.lat]; cerrar(elegido);
  });
  return listo.then(() => { map.remove(); return elegido; });
}

