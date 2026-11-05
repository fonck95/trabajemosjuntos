// Ficha de un habitante (7.4): cabecera con chips, barra de acciones por rol, teléfonos con su estado, formulario por
// bloques (los campos que el rol no puede editar quedan deshabilitados), autorización, historial con los
// acercamientos, origen y cambios (A y K). El consultor ve una ficha reducida (`pintarConsultor`).
import { api, ErrorApi, nuevaClave, puede, registrarPendiente, sesion } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { marcarLlamada } from '../llamadas.js';
import { BASES, baseSegunTema, cargarMapLibre } from '../mapa3d.js';
import {
  CANALES, ESTADOS_AUTORIZACION, ESTADOS_CIVILES, ESTADOS_TELEFONO, ESTADOS_VOTACION, ETIQUETAS_CAMPOS,
  MEDIOS_AUTORIZACION, MOTIVOS_ACTUALIZACION, MOTIVOS_NO_DISPONIBLE, NIVELES, REGIMENES_SALUD, SENSIBLES, SEXOS, SITUACIONES,
  SITUACIONES_LABORALES, TENENCIAS, TIPOS_DOCUMENTO, TIPOS_TELEFONO, autorizacionDe, enlaceWhatsapp, esCelular, esUsable,
  etiquetaResultado, marcable, telefonosUsables,
} from '../modelo.js';
import {
  $, $$, FUENTES, aviso, avisoError, chipAbordaje, chipAutorizacion, chipPrecision, confirmar, dialogo, esMovil, fecha, html,
  icono, iniciales, montar, num, titulo,
} from '../ui.js';
import { dialogoAcercamiento, mensajeNoContactable } from './acercamiento.js';
import {
  administra, camposAutorizacion, camposVotacion, chipsFaltan, cuerpoVotacion, dialogoCambiada, dialogoCompletar, elegirPunto,
  enlazarAutorizacion, enlazarVotacion, faltanDe, formularioNuevaPersona, leerAutorizacion, opcionesLugares, textoCedula,
  ubicarConGps,
} from './comunes.js';

const TIPOS_SOLICITUD = { consulta: 'Consultar sus datos', correccion: 'Corregir sus datos', supresion: 'Borrar sus datos', revocatoria: 'Revocar la autorización', otro: 'Otra' };
// Campos numéricos y de sí o no del formulario (el resto va como texto, vacío = null)
const NUMEROS = ['edad', 'personas_hogar', 'estrato', 'lugar_id'];
const AUXILIARES = ['cedula_confirmacion', 'motivo_cambio_cedula', 'puesto', 'puesto_texto', 'municipio', 'mesa', 'votacion_verificada'];

// Menú ⋯ de cada número: [clave, texto, cuerpo del PATCH o acción, roles]
const ACCIONES_TEL = [
  ['confirmado', 'Confirmado', { estado: 'confirmado' }],
  ['no_usa', 'Ya no lo usa', { estado: 'no_usa' }],
  ['equivocado', 'Equivocado', { estado: 'equivocado' }],
  ['inexistente', 'No existe', { estado: 'inexistente' }],
  ['whatsapp', 'Tiene WhatsApp', { whatsapp: true }],
  ['no_contactar', 'No contactar', { no_contactar: true }],
  ['contactar', 'Quitar «No contactar»', { no_contactar: false }],
  ['principal', 'Hacer principal', 'principal'],
  ['retirar', 'Retirar', 'retirar'],
];

const fuentesTel = (t) => (t.fuentes || []).map((f) => FUENTES[f] || f).join(', ');

export async function vistaFicha(el, { params, ir }) {
  const id = Number(params[0]);
  let p, cat;
  try {
    [p, cat] = await Promise.all([api.get(`/api/personas/${id}`), api.catalogos()]);
  } catch (e) {
    if (e instanceof ErrorApi && e.estado === 409 && e.detalle?.id) { ir(`/personas/${e.detalle.id}`, { reemplazar: true }); return; }
    if (e instanceof ErrorApi && e.codigo === 'no_contactable') throw new ErrorApi(409, mensajeNoContactable(e));
    throw e;
  }
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const rol = sesion.rol;
  const adm = administra();
  const esC = rol === 'consultor';
  const esP = rol === 'planillero';
  let pestana = 'datos';
  let formInicial = null; // valores del formulario tal como se pintaron
  let sucio = false;
  const quitarPendiente = registrarPendiente(() => sucio);

  // ───────── Minimapa: se crea una vez (a pedido en el celular) y sobrevive a los repintados ─────────
  let mini = null, marca = null, miniCont = null, miniCoords = null, turnoMini = 0, verMapa = !esMovil();
  async function pintarMini() {
    const hueco = $('#minimapa', el);
    if (!hueco) return;
    if (p.lat == null || p.lon == null) { if (mini) { mini.remove(); mini = null; marca = null; miniCont = null; miniCoords = null; } return; }
    if (!verMapa) return;
    if (miniCont) {
      hueco.replaceWith(miniCont);
      // Mismo punto: el mapa sigue tal cual; si cambió, se mueve el marcador (no se crea otro mapa)
      if (mini && (miniCoords?.[0] !== p.lon || miniCoords?.[1] !== p.lat)) {
        marca?.setLngLat([p.lon, p.lat]);
        mini.jumpTo({ center: [p.lon, p.lat] });
        miniCoords = [p.lon, p.lat];
      }
      mini?.resize();
      return;
    }
    const turno = ++turnoMini;
    const maplibregl = await cargarMapLibre();
    if (turno !== turnoMini || !el.isConnected) return;
    const actual = $('#minimapa', el);
    if (!actual) return;
    actual.replaceChildren();
    miniCont = actual;
    miniCoords = [p.lon, p.lat];
    mini = new maplibregl.Map({ container: actual, style: BASES[baseSegunTema()], center: miniCoords,
      zoom: p.geo_precision === 'vereda' ? 13 : 16.2, pitch: 45, attributionControl: { compact: true }, cooperativeGestures: true });
    marca = new maplibregl.Marker({ color: '#e3141b' }).setLngLat(miniCoords).addTo(mini);
  }

  // ───────── Valores del formulario ─────────
  function leerForm() {
    const f = $('#f-datos', el);
    if (!f) return null;
    const v = {};
    for (const x of f.elements) if (x.name && !x.name.startsWith('aut_')) v[x.name] = x.type === 'checkbox' ? x.checked : x.value;
    for (const b of $$('[data-et]', f)) v['et:' + b.dataset.et] = b.getAttribute('aria-pressed');
    return v;
  }
  const ed = (k) => !Array.isArray(p.editables) || p.editables.includes(k);
  const alternosDe = (k) => {
    const lista = (p.alternos || []).filter((a) => a.campo === k && a.valor != null && String(a.valor) !== String(p[k] ?? '')).slice(-2);
    if (!lista.length || !ed(k)) return '';
    return html`${lista.map((a) => html`<small class="alterno">Otra fuente dice: <b>${String(a.valor)}</b>${a.fuente ? ` (${FUENTES[a.fuente] || a.fuente})` : ''}
      <button type="button" class="btn fantasma chico" data-usar-alterno="${k}" data-valor="${String(a.valor)}">Usar este</button></small>`)}`;
  };
  const entrada = (k, t, { tipo = 'text', min = null, max = null, modo = null, ancho = false, valor = p[k], ayuda = '', largo = null } = {}) => html`<label class="campo${ancho ? ' ancho' : ''}" data-campo="${k}"><span>${t}</span>
    <input name="${k}" type="${tipo}" value="${valor ?? ''}" ${min != null ? html`min="${min}"` : ''} ${max != null ? html`max="${max}"` : ''} ${modo ? html`inputmode="${modo}"` : ''} ${largo ? html`maxlength="${largo}"` : ''} ${ed(k) ? '' : 'disabled'}>
    ${ayuda ? html`<small class="nota">${ayuda}</small>` : ''}${alternosDe(k)}</label>`;
  const selector = (k, t, opciones, { valor = p[k], nombre = k, editable = ed(k) } = {}) => {
    const v = valor == null ? '' : String(valor);
    const conocido = v === '' || opciones.some(([o]) => String(o) === v);
    return html`<label class="campo" data-campo="${k}"><span>${t}</span><select name="${nombre}" data-guardado="${conocido ? '' : v}" ${editable ? '' : 'disabled'}>
      ${opciones.map(([o, tx]) => html`<option value="${o}" ${String(o) === v ? 'selected' : ''}>${tx}</option>`)}</select>${alternosDe(k)}</label>`;
  };
  const lista = (arr) => [['', '—'], ...arr.map((x) => [x, x])];

  // ───────── Pintado ─────────
  function pintar({ conservar = true } = {}) {
    if (esC) { pintarConsultor(); return; }
    // Lo cambiado y no guardado sobrevive a las acciones que vuelven a pintar la ficha (nota, ubicación, teléfonos)
    const ahora = conservar ? leerForm() : null;
    const pendientes = ahora && formInicial ? Object.entries(ahora).filter(([k, v]) => formInicial[k] !== v) : [];
    // Persona que no autorizó: P solo ve lo mínimo y solo puede registrar una autorización nueva o una solicitud
    if (p.consentimiento === 'no' && !adm) { pintarNoAutorizo(); return; }
    const campos = (cat.campos || []).filter((c) => c.activo);
    const grupos = { necesidad: 'Necesidades', interes: 'Grupo poblacional e intereses', rol: 'Rol en la comunidad' };
    const tiene = new Set((p.etiquetas || []).map((e) => e.id));
    const aut = autorizacionDe(p);
    const v = p.votacion || (p.puesto_votacion || p.mesa ? { puesto_texto: p.puesto_votacion, mesa: p.mesa } : {});
    const eventos = eventosHistorial();
    const nTab = (n) => (n ? ` (${n})` : '');

    montar(el, html`
      <div class="miga"><a href="/personas" data-ruta>Habitantes</a> › Ficha ${p.id}</div>
      <div class="cabecera">
        <div class="perfil">
          <div class="avatar">${iniciales(p.nombre)}</div>
          <div><h1 class="nombre-ficha">${p.nombre}</h1>${chipsCabecera()}</div>
        </div>
        <div class="acciones">
          <div class="anillo" style="--p:${Number(p.completitud) || 0}" title="Completitud del perfil"><span>${Number(p.completitud) || 0}%</span></div>
          ${adm ? html`<button class="btn" id="unir">Unir con otra ficha</button><button class="btn peligro" id="suprimir">Suprimir datos</button>` : ''}
        </div>
      </div>
      ${bloqueSeguimiento()}
      ${(p.coincidencias || []).length && adm ? html`<div class="aviso-legal" style="margin-bottom:16px">Posible misma persona que ${p.coincidencias.map((c) => html`<a href="/personas/${c.otro_id}" data-ruta>${c.otro_nombre}</a> (${Math.round(c.puntaje * 100)} %) `)} — <a href="/calidad" data-ruta>revisar</a></div>` : ''}
      ${barraAcciones()}
      <div class="ficha">
        <div class="tarjeta principal-ficha">
          <div class="pestanas" role="tablist">
            ${[['datos', 'Datos'], ['historial', `Historial${nTab(eventos.length)}`], ...(adm ? [['origen', 'Origen'], ['cambios', 'Cambios']] : [])]
              .map(([k, t]) => html`<button role="tab" data-tab="${k}" aria-selected="${pestana === k}">${t}</button>`)}
          </div>
          <div data-panel="datos" ${pestana === 'datos' ? '' : 'hidden'}>
            <form id="f-datos" novalidate>
              <details class="bloque" open><summary>Identificación</summary><div class="form">
                ${entrada('nombre', 'Nombre completo', { ancho: true, largo: 160 })}
                ${selector('tipo_documento', 'Tipo de documento', [['', '—'], ...Object.entries(TIPOS_DOCUMENTO)])}
                ${entrada('cedula', 'Número de documento', { modo: 'numeric', largo: 15, ayuda: p.cedula ? '' : 'Al escribirla se pide repetirla.' })}
                <label class="campo" data-confirmacion hidden><span>Repita el número</span><input name="cedula_confirmacion" inputmode="numeric" autocomplete="off" maxlength="15"></label>
                ${adm && p.cedula ? html`<label class="campo" data-motivo-cedula hidden><span>Motivo del cambio de cédula *</span><input name="motivo_cambio_cedula" maxlength="200"></label>` : ''}
                <label class="casilla"><input type="checkbox" name="cedula_verificada" ${p.cedula_verificada ? 'checked' : ''} ${ed('cedula_verificada') ? '' : 'disabled'}> Vi el documento</label>
                ${noDisponible('cedula', 'No la dio')}
                ${adm && (p.cedulas_anteriores || []).length ? html`<p class="sec ancho">Cédulas anteriores: ${p.cedulas_anteriores.join(', ')}</p>` : ''}
              </div></details>
              <details class="bloque" ${esMovil() ? '' : 'open'}><summary>Votación ${v.estado ? html`<span class="chip ${v.estado === 'verificado' ? 'verde' : v.estado === 'por_confirmar' ? 'ambar' : 'borde'}">${ESTADOS_VOTACION[v.estado] || v.estado}</span>` : ''}</summary><div class="form">
                ${camposVotacion(cat, v)}
                ${noDisponible('puesto', 'No sabe')}
                ${cat.enlace_consulta_puesto ? html`<a class="btn chico" href="${cat.enlace_consulta_puesto}" target="_blank" rel="noopener noreferrer">Consultar en la Registraduría ↗</a>` : ''}
                <label class="casilla ancho"><input type="checkbox" name="votacion_verificada" ${v.estado === 'verificado' && v.fuente === 'titular' ? 'checked' : ''} ${ed('votacion_verificada') ? '' : 'disabled'}> Verificado en la Registraduría con el titular</label>
              </div></details>
              <details class="bloque" ${esMovil() ? '' : 'open'}><summary>Datos personales</summary><div class="form">
                ${selector('sexo', 'Sexo', [['', '—'], ...Object.entries(SEXOS)])}
                ${entrada('fecha_nacimiento', 'Fecha de nacimiento', { tipo: 'date' })}
                ${entrada('edad', 'Edad', { tipo: 'number', min: 0, max: 120, modo: 'numeric', ayuda: p.edad != null && p.edad_ref ? `Según fuente, declarada el ${fecha(p.edad_ref)}` : p.edad_efectiva != null ? `Edad calculada: ${p.edad_efectiva}` : '' })}
                ${selector('estado_civil', 'Estado civil', lista(ESTADOS_CIVILES))}
                ${selector('nivel_educativo', 'Nivel educativo', lista(NIVELES))}
                ${selector('situacion_laboral', 'Situación laboral', lista(SITUACIONES_LABORALES))}
                ${entrada('ocupacion', 'Ocupación', { largo: 120 })}
                ${entrada('personas_hogar', 'Personas en el hogar', { tipo: 'number', min: 0, max: 40, modo: 'numeric' })}
                ${selector('jefe_hogar', 'Jefe de hogar', [['', '—'], ['si', 'Sí'], ['no', 'No']], { valor: p.jefe_hogar == null ? '' : p.jefe_hogar ? 'si' : 'no' })}
                ${selector('tenencia_vivienda', 'Tenencia de la vivienda', lista(TENENCIAS))}
                ${selector('estrato', 'Estrato', [['', '—'], ...['0', '1', '2', '3', '4', '5', '6'].map((x) => [x, x])])}
                ${selector('regimen_salud', 'Régimen de salud', lista(REGIMENES_SALUD))}
              </div></details>
              <details class="bloque" ${esMovil() ? '' : 'open'}><summary>Contacto y ubicación</summary><div class="form">
                ${entrada('correo', 'Correo', { modo: 'email', largo: 120 })}
                ${entrada('direccion', 'Dirección', { ancho: true, largo: 240 })}
                <label class="campo" data-campo="lugar_id"><span>Barrio o vereda</span><select name="lugar_id" ${ed('lugar_id') ? '' : 'disabled'}>${opcionesLugares(cat, p.lugar_id)}</select></label>
                <div class="fila-botones ancho"><button type="button" class="btn chico" data-gps>${icono('gps')} Estoy en su casa</button><button type="button" class="btn chico" data-ver-mapa>${icono('mapa')} Ver en el mapa</button></div>
              </div></details>
              <details class="bloque" ${esMovil() ? '' : 'open'} id="bloque-autorizacion"><summary>Autorización ${chipAutorizacion(p, { conCanales: false })}</summary>
                <div class="datos">
                  <div><span>Estado</span><b>${ESTADOS_AUTORIZACION[aut.estado] || aut.estado}</b></div>
                  <div><span>Medio</span><b>${MEDIOS_AUTORIZACION[aut.medio] || aut.medio || '—'}</b></div>
                  <div><span>Canales</span><b>${(aut.canales || []).map((c) => CANALES[c] || c).join(', ') || (aut.estado === 'si' ? 'Ninguno' : '—')}</b></div>
                  <div><span>Habilita el contacto</span><b>${aut.habilitado == null ? '—' : aut.habilitado ? 'Sí' : 'No (falta confirmarla)'}</b></div>
                  ${adm ? html`<div><span>Fecha</span><b>${fecha(aut.fecha)}</b></div>` : ''}
                </div>
                ${adm ? html`<div class="form" style="margin-top:12px">${entrada('consentimiento_fecha', 'Fecha de la autorización', { tipo: 'date', valor: p.consentimiento_fecha })}</div>
                  <button type="button" class="btn chico fantasma" data-ver-autorizaciones>Ver historial de autorizaciones</button><div id="historial-aut"></div>` : ''}
                <div class="registrar-autorizacion">${camposAutorizacion(cat, { obligatoria: false, estados: adm ? ['si', 'no', 'revocada', 'pendiente'] : ['si', 'no', 'revocada'] })}
                  <button type="button" class="btn oscuro" data-registrar-autorizacion>Registrar autorización</button></div>
              </details>
              ${cat.sensibles_activos ? bloqueSensibles() : ''}
              <details class="bloque" ${esMovil() ? '' : 'open'}><summary>Necesidades, intereses y roles</summary>
                ${Object.entries(grupos).map(([g, t]) => {
                  const ets = (cat.etiquetas || []).filter((e) => e.grupo === g);
                  return ets.length ? html`<div class="campo" style="margin-top:12px"><span>${t}</span><div class="chips">
                    ${ets.map((e) => html`<button type="button" class="chip" data-et="${e.id}" aria-pressed="${tiene.has(e.id)}" ${ed('etiquetas') ? '' : 'disabled'}>${e.nombre}</button>`)}</div></div>` : '';
                })}
                <div class="form" style="margin-top:12px">
                  ${campos.map((c) => campoPropio(c))}
                  ${adm ? html`<label class="interruptor" style="align-self:end"><span>Líder comunitario</span><input type="checkbox" name="lider" ${p.lider ? 'checked' : ''}></label>` : ''}
                  <label class="campo ancho"><span>Observaciones</span><textarea name="observaciones" maxlength="4000" ${ed('observaciones') ? '' : 'disabled'}>${p.observaciones ?? ''}</textarea></label>
                </div>
              </details>
              <div class="guardar-ficha">
                <span class="sec" id="estado-form"></span>
                <button class="btn primario" type="submit">Guardar cambios</button>
              </div>
            </form>
          </div>
          <div data-panel="historial" ${pestana === 'historial' ? '' : 'hidden'}>
            <div class="fila-botones" style="margin-bottom:14px">
              ${puede('acercamientos.registrar') ? html`<button class="btn primario" data-registrar>${icono('acercamiento')} Registrar acercamiento</button>` : ''}
              ${puede('personas.notas') ? html`<button class="btn" data-abrir-nota>Nota interna</button>` : ''}
            </div>
            <form id="f-nota" class="nota-interna" hidden><input class="entrada" name="texto" placeholder="Nota interna (la ve el equipo, no el titular)…" required maxlength="4000"><button class="btn oscuro">Anotar</button></form>
            ${lineaTiempo(eventos)}
          </div>
          ${adm ? html`<div data-panel="origen" ${pestana === 'origen' ? '' : 'hidden'}>${panelOrigen()}</div>
            <div data-panel="cambios" ${pestana === 'cambios' ? '' : 'hidden'}>${panelCambios()}</div>` : ''}
        </div>
        <div class="lateral-ficha">
          <section class="tarjeta contacto-ficha">
            <header><h2>Teléfonos</h2>${p.abordaje !== undefined ? chipAbordaje(p.abordaje) : ''}</header>
            ${listaTelefonos()}
            <div class="datos" style="margin-top:12px;grid-template-columns:1fr 1fr">
              <div><span>Correo</span><b>${p.correo || '—'}</b></div>
              <div><span>Último contacto</span><b>${fecha(p.ultimo_contacto)}</b></div>
              ${p.edad_efectiva != null || p.rango_edad ? html`<div><span>Edad</span><b>${p.edad_efectiva ?? p.rango_edad}${p.sexo ? ' · ' + (SEXOS[p.sexo] || p.sexo) : ''}</b></div>` : ''}
              <div><span>Reuniones</span><b>${num((p.reuniones || []).length)}</b></div>
            </div>
          </section>
          <section class="tarjeta">
            <header><h2>Ubicación</h2>${chipPrecision(p.geo_precision)}</header>
            ${p.lat != null && verMapa ? html`<div class="minimapa" id="minimapa"></div>`
              : p.lat != null ? html`<button class="btn chico" data-ver-mapa>${icono('mapa')} Ver en el mapa</button>` : html`<div class="minimapa vacio-mapa" id="minimapa"><div class="vacio">Sin coordenada</div></div>`}
            <div class="datos" style="margin-top:12px;grid-template-columns:1fr">
              ${p.direccion_norm ? html`<div><span>Dirección normalizada</span><b>${p.direccion_norm}</b></div>` : ''}
              <div><span>Lugar</span><b>${p.lugar_nombre ? titulo(p.lugar_nombre) + (p.lugar_tipo ? ' · ' + p.lugar_tipo.replace('_', ' ') : '') : (p.lugar_texto ? titulo(p.lugar_texto) + ' (no reconocido)' : '—')}</b></div>
              ${p.geo_fuente === 'gps' ? html`<div><span>Ubicada con GPS</span><b>±${num(p.precision_m)} m</b></div>` : ''}
            </div>
            <div class="fila-botones" style="margin-top:12px">
              ${puede('personas.ubicar') ? html`<button class="btn chico" data-gps>${icono('gps')} Estoy en su casa</button><button class="btn chico" id="ubicar">Ajustar en el mapa</button>` : ''}
              ${p.geo_manual && puede('personas.ubicar') ? html`<button class="btn chico fantasma" id="automatica">Volver a la automática</button>` : ''}
            </div>
          </section>
        </div>
      </div>`);
    formInicial = leerForm();
    sucio = false;
    // Un dato guardado que su campo no puede mostrar (una fecha que no existe, como 1985-02-30, o una opción que ya no
    // está en la lista) se ve vacío: se dice cuál es. Al guardar otros cambios no se borra, porque solo se envía lo cambiado
    for (const x of $$('#f-datos input', el)) {
      const guardado = x.getAttribute('value');
      if (!guardado || x.value || x.type === 'checkbox') continue;
      notaGuardado(x, guardado, 'que no es válido');
    }
    for (const s of $$('#f-datos select[data-guardado]', el)) {
      if (s.dataset.guardado) notaGuardado(s, s.dataset.guardado, 'que no está en la lista');
    }
    if (!formInicial) return;
    if (pendientes.length) {
      const f = $('#f-datos', el);
      for (const [k, val] of pendientes) {
        if (k.startsWith('et:')) { $(`[data-et="${k.slice(3)}"]`, f)?.setAttribute('aria-pressed', val); continue; }
        const x = f.elements.namedItem(k);
        if (x && !x.length) x[x.type === 'checkbox' ? 'checked' : 'value'] = val;
      }
      marcarSucio();
    }
    pintarMini();
  }

  function notaGuardado(x, guardado, porque) {
    const n = document.createElement('small');
    n.className = 'nota';
    n.textContent = `Valor guardado: ${guardado}, ${porque}. Se conserva mientras no cambie este campo.`;
    x.after(n);
  }
  function marcarSucio() {
    sucio = true;
    const e = $('#estado-form', el);
    if (e) e.textContent = 'Cambios sin guardar';
  }

  function chipsCabecera() {
    const ced = textoCedula(p.cedula ? { cedula_ult3: String(p.cedula).slice(-3), tipo_documento: p.tipo_documento } : p);
    const sit = p.situacion?.estado && p.situacion.estado !== 'activa' ? p.situacion : null;
    return html`<div class="chips" style="margin-top:8px">
      ${ced ? html`<span class="chip">${ced}${p.cedula_verificada ? ' ✓' : ''}</span>` : html`<span class="chip ambar">Sin cédula</span>`}
      ${p.abordaje !== undefined ? chipAbordaje(p.abordaje) : ''}
      ${chipAutorizacion(p)}
      ${p.menor ? html`<span class="chip rojo">Menor de edad</span>` : ''}
      ${p.requiere_actualizacion ? html`<span class="chip ambar">Pendiente de actualizar</span>` : ''}
      ${sit ? html`<span class="chip rojo">${SITUACIONES[sit.estado] || sit.estado}${sit.confirmada ? '' : ' (sin confirmar)'}</span>` : ''}
      ${adm ? html`${(p.fuentes || []).map((f) => html`<span class="chip borde">${FUENTES[f] || f}</span>`)}${p.lider ? html`<span class="chip rojo">Líder</span>` : ''}${(p.listas || []).map((l) => html`<span class="chip azul">${l}</span>`)}` : ''}
    </div>`;
  }

  // Pendiente de actualizar (con la nota del consultor arriba), avisos del servidor y lo que falta
  function bloqueSeguimiento() {
    const ra = p.requiere_actualizacion;
    const avisos = (p.avisos || []).map((a) => (typeof a === 'string' ? a : a?.mensaje)).filter(Boolean);
    const faltan = faltanDe(p);
    return html`${ra ? html`<div class="aviso-legal pendiente-actualizar"><b>Pendiente de actualizar · ${MOTIVOS_ACTUALIZACION[ra.motivo] || ra.motivo || ''}</b>
        ${ra.nota ? html`<p class="nota-consultor">«${ra.nota}»</p>` : ''}<small class="sec">${ra.usuario ? `Pedido por ${ra.usuario}` : ''}${ra.ts ? ` · ${fecha(ra.ts, true)}` : ''}</small>
        ${puede('personas.editar') ? html`<div><button class="btn chico oscuro" data-atendido>Marcar como atendido</button></div>` : ''}</div>` : ''}
      ${avisos.length ? html`<div class="aviso-legal avisos-ficha">${avisos.map((a) => html`<div>${a}</div>`)}</div>` : ''}
      ${faltan.length ? html`<div class="faltan-ficha"><span class="sec">Faltan:</span> ${chipsFaltan(faltan)}</div>` : ''}`;
  }

  // Barra de acciones por rol, fija abajo en el celular: P visita y completa; C llama y registra; A y K, todo
  function barraAcciones() {
    const usables = telefonosUsables(p);
    const t0 = usables[0];
    const llamar = (adm || esC) && t0;
    const b = [];
    if (llamar) {
      b.push(html`<a class="btn" href="tel:${marcable(t0.numero)}" data-llamar="0" data-canal="llamada">${icono('telefono')}<span>Llamar</span></a>`);
      const cel = usables.findIndex((t) => esCelular(t.numero));
      if (cel >= 0) b.push(html`<a class="btn" href="${enlaceWhatsapp(usables[cel].numero)}" target="_blank" rel="noopener noreferrer" data-llamar="${cel}" data-canal="whatsapp">${icono('whatsapp')}<span>WhatsApp</span></a>`);
    }
    if (puede('acercamientos.registrar')) b.push(html`<button class="btn primario" data-registrar>${icono('acercamiento')}<span>${esP ? 'Registrar visita' : 'Registrar'}</span></button>`);
    if (puede('personas.editar')) b.push(html`<button class="btn" data-completar>${icono('completar')}<span>Completar</span></button>`);
    if (puede('personas.crear')) b.push(html`<button class="btn" data-hogar>${icono('hogar')}<span>Nueva en este hogar</span></button>`);
    if (puede('personas.ubicar')) b.push(html`<button class="btn" data-gps>${icono('gps')}<span>Estoy en su casa</span></button>`);
    return b.length ? html`<nav class="barra-acciones" aria-label="Acciones">${b}</nav>` : '';
  }

  function noDisponible(campo, texto) {
    if (!puede('personas.no_disponible')) return '';
    const nd = p.no_disponible?.[campo];
    if (nd) return html`<span class="chip borde no-disponible">${MOTIVOS_NO_DISPONIBLE[nd.motivo] || nd.motivo || texto} <button type="button" class="btn fantasma chico" data-nd-quitar="${campo}" aria-label="Quitar">✕</button></span>`;
    const vacio = campo === 'cedula' ? !p.cedula : !(p.votacion?.puesto_id || p.votacion?.puesto_texto || p.votacion?.donde);
    return vacio ? html`<button type="button" class="btn chico fantasma" data-nd="${campo}" data-motivo="${campo === 'cedula' ? 'no_la_dio' : 'no_sabe'}">${texto}</button>` : '';
  }

  function campoPropio(c) {
    const val = p.extra?.[c.clave] ?? '';
    const nombre = `extra.${c.clave}`;
    const dis = ed('extra') ? '' : 'disabled';
    if (c.tipo === 'opcion') return html`<label class="campo"><span>${c.etiqueta}</span><select name="${nombre}" ${dis}><option value="">—</option>${(c.opciones || []).map((o) => html`<option ${o === val ? 'selected' : ''}>${o}</option>`)}</select></label>`;
    if (c.tipo === 'si_no') return html`<label class="campo"><span>${c.etiqueta}</span><select name="${nombre}" ${dis}><option value="">—</option><option ${val === 'Sí' ? 'selected' : ''}>Sí</option><option ${val === 'No' ? 'selected' : ''}>No</option></select></label>`;
    // step="any": los números propios pueden tener decimales (hectáreas, metros)
    if (c.tipo === 'numero') return html`<label class="campo"><span>${c.etiqueta}</span><input name="${nombre}" value="${val}" type="number" step="any" inputmode="decimal" ${dis}></label>`;
    return html`<label class="campo"><span>${c.etiqueta}</span><input name="${nombre}" value="${val}" type="${c.tipo === 'fecha' ? 'date' : 'text'}" ${dis}></label>`;
  }

  // Datos sensibles: solo con el ajuste activo y la autorización de esa categoría; los valores no vienen en la ficha
  function bloqueSensibles() {
    const autorizadas = p.sensibles_autorizados || [];
    const registrados = p.sensibles_registrados || [];
    return html`<details class="bloque"><summary>Datos sensibles</summary>
      <p class="sec">Solo con autorización expresa del titular para cada categoría. Los valores no se muestran en la ficha.</p>
      <div class="form">${Object.entries(SENSIBLES).map(([k, s]) => html`<label class="campo"><span>${s.etiqueta}${registrados.includes(k) ? ' · registrado' : ''}</span>
        <select name="sens_${k}" ${autorizadas.includes(k) && ed('sensibles') ? '' : 'disabled'}><option value="">${autorizadas.includes(k) ? 'Sin cambio' : 'Sin autorización'}</option>${s.valores.map((x) => html`<option>${x}</option>`)}</select></label>`)}</div>
      ${adm && registrados.length ? html`<button type="button" class="btn chico" data-ver-sensibles>Ver valores (queda registrado)</button><div id="valores-sensibles"></div>` : ''}
    </details>`;
  }

  function eventosHistorial() {
    return [
      ...(p.acercamientos || []).map((a) => ({ f: a.ts || a.fecha, tipo: 'acercamiento', a,
        t: `${CANALES[a.canal] || a.canal} · ${etiquetaResultado(a.resultado, a.canal)}`,
        m: [a.usuario, a.telefono ? '···' + String(a.telefono).slice(-4) : null, a.proximo ? `volver el ${fecha(a.proximo)}` : null, a.nota].filter(Boolean).join(' · ') })),
      ...(p.reuniones || []).map((r) => ({ f: r.fecha, tipo: 'reunion', t: `Asistió a «${r.titulo}»`, m: [r.lugar_texto, r.rol, r.nota].filter(Boolean).join(' · '), href: `/reuniones/${r.id}` })),
      ...(p.notas || []).map((n) => ({ f: n.creado_en, tipo: 'nota', t: n.texto, m: `${n.autor || ''}${n.reunion ? ' · en ' + n.reunion : ''}`, nota: n.id, autor: n.autor_uid })),
      ...(p.tramites || []).map((t) => ({ f: t.fecha, tipo: 'tramite', t: titulo(t.tipo || 'Trámite'), m: [t.ficha && 'Ficha ' + t.ficha, t.direccion].filter(Boolean).join(' · ') })),
    ].sort((a, b) => String(b.f || '').localeCompare(String(a.f || '')));
  }

  function lineaTiempo(eventos) {
    const propio = (e) => adm || (e.autor != null && e.autor === sesion.uid);
    const anulable = (a) => !a.anulado && !a.auto && (adm || (a.uid === sesion.uid && Date.now() - new Date(a.ts).getTime() < 24 * 3600 * 1000));
    return eventos.length ? html`<div class="linea-tiempo">${eventos.map((e) => html`<div class="ev ${e.a?.anulado ? 'anulado' : ''}"><span class="punto ${e.tipo}"></span><div>
      <div class="t">${e.href ? html`<a href="${e.href}" data-ruta>${e.t}</a>` : e.t}${e.a?.anulado ? html` <span class="chip">Anulado</span>` : ''}</div>
      <div class="m">${fecha(e.f, e.tipo === 'nota' || e.tipo === 'acercamiento')}${e.m ? ' · ' + e.m : ''}
        ${e.nota && propio(e) ? html`<button class="btn fantasma chico" data-borrar-nota="${e.nota}">Borrar</button>` : ''}
        ${e.a && anulable(e.a) ? html`<button class="btn fantasma chico" data-anular="${e.a.id}">Anular</button>` : ''}</div></div></div>`)}</div>`
      : html`<div class="vacio"><b>Sin historial</b>Registre un acercamiento, su asistencia a una reunión o una nota.</div>`;
  }

  function panelOrigen() {
    const alt = p.alternos || [];
    const proc = Object.entries(p.procedencia || {});
    return html`
      ${alt.length ? html`<h3 class="sub-origen">Otros valores (${alt.length})</h3><div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Dato</th><th>Valor</th><th>Fuente</th><th>Fecha</th></tr></thead>
        <tbody>${alt.slice().reverse().map((a) => html`<tr style="cursor:default"><td>${ETIQUETAS_CAMPOS[a.campo] || a.campo}</td><td>${typeof a.valor === 'object' ? JSON.stringify(a.valor) : String(a.valor)}</td><td>${FUENTES[a.fuente] || a.fuente || '—'}</td><td>${fecha(a.ts)}</td></tr>`)}</tbody></table></div>` : ''}
      ${proc.length ? html`<h3 class="sub-origen">Procedencia de cada dato</h3><div class="datos">${proc.map(([k, x]) => html`<div><span>${ETIQUETAS_CAMPOS[k] || k.replace(/_/g, ' ')}</span><b>${FUENTES[x?.fuente] || x?.fuente || '—'} · ${fecha(x?.ts)}</b></div>`)}</div>` : ''}
      ${(p.origen || []).map((o) => html`<h3 class="sub-origen">${FUENTES[o.fuente] || o.fuente}</h3><div class="datos">
        ${Object.entries(o.datos || {}).filter(([k]) => k !== 'extra').map(([k, val]) => html`<div><span>${k.replace(/_/g, ' ')}</span><b>${Array.isArray(val) ? val.join(', ') : String(val ?? '')}</b></div>`)}</div>`)}
      <h3 class="sub-origen">Trámites (${(p.tramites || []).length})</h3>
      ${(p.tramites || []).length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th>Trámite</th><th>Ficha</th><th>Dirección</th><th>Teléfono</th></tr></thead>
        <tbody>${p.tramites.map((t) => html`<tr style="cursor:default"><td>${fecha(t.fecha)}</td><td>${titulo(t.tipo || '')}</td><td class="sec">${t.ficha}</td><td>${t.direccion}</td><td>${(t.telefono || '').replace(/;/g, ', ')}</td></tr>`)}</tbody></table></div>`
        : html`<p class="sec">No aparece en la base de trámites.</p>`}`;
  }

  function panelCambios() {
    const h = p.historial || [];
    return h.length ? html`<div class="linea-tiempo">${h.map((x) => html`<div class="ev"><span class="punto"></span><div>
      <div class="t">${x.usuario || 'sistema'} · ${String(x.accion || '').replace(/_/g, ' ')}</div><div class="m">${fecha(x.ts, true)}</div>
      ${x.detalle ? html`<pre class="detalle-cambio">${resumenDetalle(x.detalle)}</pre>` : ''}</div></div>`)}</div>`
      : html`<p class="sec">Sin cambios registrados.</p>`;
  }

  // ───────── Teléfonos ─────────
  function listaTelefonos() {
    const tels = Array.isArray(p.telefonos) ? p.telefonos : telefonosUsables(p);
    const usables = telefonosUsables(p);
    const llama = adm || esC;
    return html`<div class="telefonos">${tels.length ? tels.map((t) => {
      const i = usables.findIndex((u) => u.numero === t.numero);
      const usable = esUsable(t);
      return html`<div class="tel ${usable ? '' : 'no-usable'}" data-numero="${t.numero}">
        <div class="tel-num"><b>${t.numero}</b>
          <span class="chip borde">${TIPOS_TELEFONO[t.tipo] || (esCelular(t.numero) ? 'Celular' : 'Fijo')}</span>
          <span class="chip tel-estado estado-${t.estado || 'sin_verificar'}">${ESTADOS_TELEFONO[t.estado || 'sin_verificar']}</span>
          ${t.whatsapp ? html`<span class="chip verde">WhatsApp</span>` : ''}${t.no_contactar ? html`<span class="chip rojo">No contactar</span>` : ''}
          ${t.fuentes?.length ? html`<small class="sec">${fuentesTel(t)}</small>` : ''}</div>
        <div class="tel-acciones">
          ${llama && usable && i >= 0 ? html`<a class="btn chico" href="tel:${marcable(t.numero)}" data-llamar="${i}" data-canal="llamada" aria-label="Llamar al ${t.numero}">${icono('telefono')}</a>` : ''}
          ${llama && usable && i >= 0 && esCelular(t.numero) ? html`<a class="btn chico" href="${enlaceWhatsapp(t.numero)}" target="_blank" rel="noopener noreferrer" data-llamar="${i}" data-canal="whatsapp" aria-label="WhatsApp al ${t.numero}">${icono('whatsapp')}</a>` : ''}
          ${puede('personas.telefonos') && Array.isArray(p.telefonos) ? html`<button class="btn chico fantasma" data-menu-tel="${t.numero}" aria-label="Más acciones del ${t.numero}">${icono('puntos')}</button>` : ''}
        </div></div>`;
    }) : html`<p class="sec">Sin teléfono.</p>`}</div>
    ${puede('personas.telefonos') ? html`<button class="btn chico" data-agregar-tel>${icono('mas')} Agregar número</button>` : ''}`;
  }

  async function menuTelefono(numero) {
    const t = (p.telefonos || []).find((x) => x.numero === numero);
    if (!t) return;
    const visibles = ACCIONES_TEL.filter(([k]) => {
      if (k === 'principal') return puede('personas.editar') && !esC;
      if (k === 'retirar') return adm && t.estado !== 'retirado';
      if (k === 'whatsapp') return esCelular(numero) && !t.whatsapp;
      if (k === 'no_contactar') return !t.no_contactar;
      if (k === 'contactar') return t.no_contactar && !esC;
      return t.estado !== k;
    });
    const { el: d, cerrar } = dialogo({
      titulo: `Número ${numero}`,
      cuerpo: html`<div class="lista-acciones-tel">${visibles.map(([k, tx]) => html`<button class="btn ${k === 'retirar' ? 'peligro' : ''}" data-accion-tel="${k}">${tx}</button>`)}</div>
        <label class="campo" style="margin-top:12px"><span>Nota (opcional)</span><input name="nota" maxlength="300" placeholder="Por ejemplo: contestó la hermana"></label>`,
    });
    d.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-accion-tel]');
      if (!b) return;
      const [, , accion] = ACCIONES_TEL.find(([k]) => k === b.dataset.accionTel);
      const nota = $('[name="nota"]', d).value.trim() || undefined;
      const n = encodeURIComponent(numero);
      b.disabled = true;
      try {
        if (accion === 'principal') p = await api.post(`/api/personas/${id}/telefonos/${n}/principal`, {});
        else if (accion === 'retirar') {
          if (!await confirmar(`¿Retirar el ${numero}? No se borra: queda en la ficha como retirado.`, { si: 'Retirar', peligro: true })) { b.disabled = false; return; }
          p = await api.del(`/api/personas/${id}/telefonos/${n}`);
        } else p = await api.patch(`/api/personas/${id}/telefonos/${n}`, { ...accion, nota });
        cerrar();
        aviso('Número actualizado');
        pintar();
      } catch (err) { avisoError(err); b.disabled = false; }
    });
  }

  function agregarTelefono() {
    let clave = nuevaClave();
    const { el: d, cerrar } = dialogo({
      titulo: 'Agregar número',
      cuerpo: html`<form class="form una-columna" id="f-tel">
        <label class="campo"><span>Número *</span><input name="numero" inputmode="tel" required maxlength="40" autocomplete="off" placeholder="300 111 2233"></label>
        <label class="casilla"><input type="checkbox" name="whatsapp"> Tiene WhatsApp</label>
        <label class="casilla"><input type="checkbox" name="confirmado"> El titular confirmó que es suyo</label>
        <label class="casilla"><input type="checkbox" name="principal"> Usarlo primero (principal)</label>
        ${telefonosUsables(p).length ? html`<label class="casilla"><input type="checkbox" name="anterior_no_usa"> El número anterior ya no lo usa</label>` : ''}
        <label class="campo"><span>Nota</span><input name="nota" maxlength="300"></label>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g-tel">Agregar</button>`,
    });
    const f = $('#f-tel', d);
    const enviar = async () => {
      if (!f.reportValidity()) return;
      const b = $('#g-tel', d);
      b.disabled = true;
      const cuerpo = { numero: f.numero.value.trim(), whatsapp: f.whatsapp.checked || undefined, confirmado: f.confirmado.checked || undefined,
        principal: f.principal.checked || undefined, anterior_no_usa: f.anterior_no_usa?.checked || undefined, nota: f.nota.value.trim() || undefined };
      try {
        p = await api.post(`/api/personas/${id}/telefonos`, cuerpo, { clave });
        cerrar(); aviso('Número agregado'); pintar();
      } catch (err) {
        if (err instanceof ErrorApi && err.estado < 500) clave = nuevaClave();
        avisoError(err); b.disabled = false;
      }
    };
    $('#g-tel', d).addEventListener('click', enviar);
    f.addEventListener('submit', (e) => { e.preventDefault(); enviar(); });
  }

  // ───────── Vistas reducidas ─────────

  // Persona que no autorizó (P): lo mínimo, para no duplicarla; solo una autorización nueva con evidencia o una solicitud
  function pintarNoAutorizo() {
    montar(el, html`<div class="miga"><a href="/personas" data-ruta>Habitantes</a> › Ficha ${p.id}</div>
      <div class="cabecera"><div class="perfil"><div class="avatar">${iniciales(p.nombre)}</div><div><h1 class="nombre-ficha">${p.nombre}</h1>
        <div class="chips" style="margin-top:8px">${p.cedula_ult3 ? html`<span class="chip">CC ···${p.cedula_ult3}</span>` : ''}${chipAutorizacion(p)}${p.lugar ? html`<span class="chip borde">${titulo(p.lugar)}</span>` : ''}</div></div></div></div>
      <div class="tarjeta">
        <p><b>Esta persona no autorizó el tratamiento de sus datos.</b> No se le contacta ni se editan sus datos. Si el titular cambió de opinión, registre su autorización con la evidencia.</p>
        <form id="f-aut-no">${camposAutorizacion(cat, { obligatoria: true, estados: ['si'] })}</form>
        <div class="fila-botones"><button class="btn oscuro" data-registrar-autorizacion>Registrar autorización</button><button class="btn" data-solicitud>Solicitud del titular</button></div>
      </div>`);
    enlazarAutorizacion($('#f-aut-no', el));
  }

  // Ficha del consultor: encabezado, teléfonos usables, abordaje, autorización, puesto, lo que falta y sus acercamientos
  function pintarConsultor() {
    const usables = telefonosUsables(p);
    const faltan = faltanDe(p);
    const puesto = p.votacion?.puesto_nombre ?? p.puesto_nombre ?? p.puesto_votacion ?? null;
    montar(el, html`<div class="miga"><a href="/trabajo" data-ruta>Mi trabajo</a> › ${titulo(p.nombre || '')}</div>
      <div class="cabecera"><div class="perfil"><div class="avatar">${iniciales(p.nombre)}</div><div><h1 class="nombre-ficha">${p.nombre}</h1>
        <div class="sub">${[p.rango_edad && `${p.rango_edad} años`, SEXOS[p.sexo], titulo(p.lugar_nombre || p.lugar || ''), p.zona === 'rural' ? 'Rural' : p.zona === 'urbana' ? 'Casco urbano' : ''].filter(Boolean).join(' · ')}</div>
        <div class="chips" style="margin-top:8px">${p.cedula_ult3 ? html`<span class="chip">CC ···${p.cedula_ult3}</span>` : html`<span class="chip ambar">Sin cédula</span>`}
          ${chipAbordaje(p.abordaje)}${chipAutorizacion(p)}${p.requiere_actualizacion ? html`<span class="chip ambar">Pendiente de actualizar</span>` : ''}
          ${p.situacion?.estado && p.situacion.estado !== 'activa' ? html`<span class="chip rojo">${SITUACIONES[p.situacion.estado] || p.situacion.estado}</span>` : ''}</div></div></div></div>
      ${barraAcciones()}
      <div class="rejilla r-12">
        <section class="tarjeta c-6 contacto-ficha"><header><h2>Teléfonos</h2></header>${listaTelefonos()}</section>
        <section class="tarjeta c-6"><h2>Datos</h2><div class="datos">
          <div><span>Puesto de votación</span><b>${puesto ? titulo(puesto) : '—'}</b></div>
          <div><span>Faltan</span><b>${faltan.length ? chipsFaltan(faltan) : 'Nada'}</b></div>
          ${p.en_curso?.hasta ? html`<div><span>A su cargo hasta</span><b>${fecha(p.en_curso.hasta, true)}</b></div>` : ''}</div>
          <div class="fila-botones" style="margin-top:14px">
            <button class="btn primario" data-registrar>${icono('acercamiento')} Registrar</button>
            <button class="btn" data-pedir-actualizacion>Pedir actualización de datos</button>
            <button class="btn" data-solicitud>Solicitud del titular</button>
          </div></section>
        <section class="tarjeta c-12"><h2>Acercamientos</h2>${lineaTiempo(eventosHistorial())}</section>
      </div>`);
  }

  async function recargar() {
    p = await api.get(`/api/personas/${id}`);
    pintar({ conservar: false });
  }

  // ───────── Acciones ─────────
  async function registrar(op = {}) {
    const r = await dialogoAcercamiento(p, { ...op, alDeshacer: (f) => { if (f) { p = f; pintar(); } else recargar().catch(avisoError); } });
    if (r && r.id) { p = r; pintar(); refrescarInsignias(); }
  }

  function solicitud() {
    const { el: d, cerrar } = dialogo({
      titulo: 'Solicitud del titular',
      cuerpo: html`<form class="form una-columna" id="f-sol">
        <p class="sec">Lo que el titular pide sobre sus datos: queda con su plazo legal para que el administrador responda.</p>
        <label class="campo"><span>¿Qué pide?</span><select name="tipo">${Object.entries(TIPOS_SOLICITUD).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>
        <label class="campo"><span>Canal</span><select name="canal">${['llamada', 'whatsapp', 'sms', 'visita', 'correo', 'otro'].map((c) => html`<option value="${c}" ${c === (esC ? 'llamada' : 'visita') ? 'selected' : ''}>${CANALES[c] || c}</option>`)}</select></label>
        <label class="campo"><span>Descripción *</span><textarea name="descripcion" required maxlength="2000"></textarea><small class="nota-sensibles">No anote salud, política, religión ni otros datos sensibles.</small></label>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g-sol">Registrar solicitud</button>`,
    });
    const f = $('#f-sol', d);
    let clave = nuevaClave();
    $('#g-sol', d).addEventListener('click', async (e) => {
      if (!f.reportValidity()) return;
      e.currentTarget.disabled = true;
      try {
        const r = await api.post('/api/solicitudes', { persona_id: id, tipo: f.tipo.value, canal: f.canal.value, descripcion: f.descripcion.value.trim() }, { clave });
        cerrar();
        aviso(`Solicitud registrada${r?.vence ? `: vence el ${fecha(r.vence)}` : ''}`, 'ok', 6000);
      } catch (err) { if (err instanceof ErrorApi && err.estado < 500) clave = nuevaClave(); avisoError(err); e.currentTarget.disabled = false; }
    });
  }

  async function marcarAtendido() {
    const { el: d, cerrar, listo } = dialogo({
      titulo: 'Marcar como atendido',
      cuerpo: html`<label class="campo"><span>¿Qué se actualizó?</span><textarea name="nota" maxlength="1000" placeholder="Se confirmó la dirección y el celular nuevo"></textarea></label>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" data-ok>Marcar como atendido</button>`,
    });
    d.querySelector('[data-ok]').addEventListener('click', () => cerrar($('[name="nota"]', d).value.trim()));
    const nota = await listo;
    if (nota === null || nota === undefined) return;
    try { p = await api.post(`/api/personas/${id}/actualizacion`, { nota }); aviso('Marcada como atendida'); pintar(); refrescarInsignias(); } catch (err) { avisoError(err); }
  }

  async function registrarAutorizacion(boton) {
    const caja = boton.closest('form') || boton.closest('.tarjeta') || el;
    const { aut, error } = leerAutorizacion(caja);
    if (!aut) { aviso('Elija qué respondió el titular', 'error'); return; }
    if (error) { aviso(error, 'error'); return; }
    boton.disabled = true;
    try {
      p = await api.post(`/api/personas/${id}/autorizacion`, aut, { clave: nuevaClave() });
      aviso('Autorización registrada');
      pintar();
    } catch (err) { avisoError(err); boton.disabled = false; }
  }

  async function ponerNoDisponible(campo, motivo, quitar = false) {
    try {
      p = await api.post(`/api/personas/${id}/no-disponible`, quitar ? { campo, quitar: true } : { campo, motivo });
      pintar();
    } catch (err) { avisoError(err); }
  }

  el.addEventListener('click', async (e) => {
    const tab = e.target.closest('[data-tab]');
    if (tab) {
      // Cambiar de pestaña no vuelve a pintar: lo escrito y no guardado sigue en el formulario
      pestana = tab.dataset.tab;
      for (const b of $$('[data-tab]', el)) b.setAttribute('aria-selected', b === tab);
      for (const panel of $$('[data-panel]', el)) panel.hidden = panel.dataset.panel !== pestana;
      tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      return;
    }
    const et = e.target.closest('[data-et]');
    if (et && !et.disabled) { et.setAttribute('aria-pressed', et.getAttribute('aria-pressed') !== 'true'); marcarSucio(); return; }
    const ll = e.target.closest('[data-llamar]');
    if (ll) {
      // Llamar o escribir: se anota la llamada (sin número ni nombre) para la franja «Llamada sin registrar»
      marcarLlamada({ pid: id, indice: Number(ll.dataset.llamar), canal: ll.dataset.canal });
      if (esC) api.post(`/api/trabajo/tomar/${id}`).catch(() => {});
      return; // el enlace sigue su curso (tel: o WhatsApp)
    }
    if (e.target.closest('[data-registrar]')) return registrar(esP ? { canal: 'visita' } : {});
    if (e.target.closest('[data-pedir-actualizacion]')) return registrar({ resultado: 'actualizo_datos', pedirActualizacion: true });
    if (e.target.closest('[data-solicitud]')) return solicitud();
    if (e.target.closest('[data-completar]')) {
      const r = await dialogoCompletar(p, cat);
      if (r?.ficha?.id) { p = r.ficha; pintar(); }
      return;
    }
    if (e.target.closest('[data-hogar]')) {
      formularioNuevaPersona({ cat, hogar: { nombre: p.nombre, direccion: p.direccion, lugar_id: p.lugar_id, ficha: p.ficha ?? p.tramites?.[0]?.ficha ?? null, lat: p.lat, lon: p.lon },
        alCrear: (n) => ir(`/personas/${n.id}`) });
      return;
    }
    if (e.target.closest('[data-gps]')) {
      const r = await ubicarConGps(id);
      if (r?.id) { p = r; pintar(); }
      return;
    }
    if (e.target.closest('[data-ver-mapa]')) {
      verMapa = true;
      if (p.lat == null) { aviso('Esta persona todavía no tiene ubicación', 'error'); return; }
      pintar();
      $('#minimapa', el)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      return;
    }
    if (e.target.closest('[data-atendido]')) return marcarAtendido();
    const rab = e.target.closest('[data-registrar-autorizacion]');
    if (rab) return registrarAutorizacion(rab);
    const nd = e.target.closest('[data-nd]');
    if (nd) return ponerNoDisponible(nd.dataset.nd, nd.dataset.motivo);
    const ndq = e.target.closest('[data-nd-quitar]');
    if (ndq) return ponerNoDisponible(ndq.dataset.ndQuitar, null, true);
    const mt = e.target.closest('[data-menu-tel]');
    if (mt) return menuTelefono(mt.dataset.menuTel);
    if (e.target.closest('[data-agregar-tel]')) return agregarTelefono();
    if (e.target.closest('[data-abrir-nota]')) { const f = $('#f-nota', el); f.hidden = !f.hidden; if (!f.hidden) f.texto.focus(); return; }
    const alt = e.target.closest('[data-usar-alterno]');
    if (alt) {
      const k = alt.dataset.usarAlterno;
      return guardarCambios({ [k]: NUMEROS.includes(k) ? Number(alt.dataset.valor) : alt.dataset.valor, base: { [k]: p[k] ?? null } });
    }
    const an = e.target.closest('[data-anular]');
    if (an) {
      if (!await confirmar('¿Anular este registro? No se borra: queda anulado en el historial.', { si: 'Anular', peligro: true })) return;
      try { const r = await api.post(`/api/acercamientos/${an.dataset.anular}/anular`, { motivo: 'Anulado desde la ficha' }); if (r?.id) p = r; else p = await api.get(`/api/personas/${id}`); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('[data-ver-autorizaciones]')) {
      try {
        const evs = await api.get(`/api/personas/${id}/autorizaciones`);
        const lista = Array.isArray(evs) ? evs : evs?.filas || [];
        montar($('#historial-aut', el), lista.length ? html`<div class="linea-tiempo">${lista.map((a) => html`<div class="ev"><span class="punto"></span><div>
          <div class="t">${ESTADOS_AUTORIZACION[a.estado] || a.estado} · ${MEDIOS_AUTORIZACION[a.medio] || a.medio || ''}</div>
          <div class="m">${fecha(a.ts, true)} · ${a.usuario || ''}${a.evidencia ? ' · ' + a.evidencia : ''}${(a.canales || []).length ? ' · ' + a.canales.map((c) => CANALES[c] || c).join(', ') : ''}</div></div></div>`)}</div>`
          : html`<p class="sec">Sin eventos registrados.</p>`);
      } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('[data-ver-sensibles]')) {
      try {
        const s = await api.get(`/api/personas/${id}/sensibles`);
        montar($('#valores-sensibles', el), html`<div class="datos">${Object.entries(s || {}).map(([k, val]) => html`<div><span>${SENSIBLES[k]?.etiqueta || k}</span><b>${String(val ?? '—')}</b></div>`)}</div>`);
      } catch (err) { avisoError(err); }
      return;
    }
    const bn = e.target.closest('[data-borrar-nota]');
    if (bn && await confirmar('¿Borrar esta nota?', { si: 'Borrar', peligro: true })) {
      try { p = await api.del(`/api/personas/${id}/notas/${bn.dataset.borrarNota}`); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#ubicar')) {
      const punto = await elegirPunto({ inicial: p.lat != null ? [p.lon, p.lat] : null, titulo: `Ubicar a ${titulo(p.nombre)}` });
      if (!punto) return;
      try { p = await api.put(`/api/personas/${id}/ubicacion`, { lon: punto[0], lat: punto[1] }); aviso('Ubicación guardada'); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#automatica')) {
      try { p = await api.del(`/api/personas/${id}/ubicacion`); pintar(); } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.closest('#suprimir')) {
      if (await confirmar(`Se borrarán todos los datos personales de ${p.nombre} (derecho de supresión, Ley 1581), también de las fichas que se unieron con ella y del detalle de su auditoría. Las próximas importaciones la omitirán: queda solo una huella cifrada para reconocerla. ¿Continuar?`, { si: 'Suprimir', peligro: true })) {
        try { await api.del(`/api/personas/${id}`); aviso('Datos suprimidos'); sucio = false; ir('/personas'); } catch (err) { avisoError(err); }
      }
      return;
    }
    if (e.target.closest('#unir')) unir();
  });

  el.addEventListener('input', (e) => {
    if (!e.target.closest('#f-datos') || e.target.name?.startsWith('aut_')) return;
    marcarSucio();
    // Documento nuevo: se pide repetirlo; cambiar uno existente (A y K) pide el motivo
    if (e.target.name === 'cedula') {
      const nuevo = e.target.value.trim() !== String(p.cedula ?? '');
      const conf = $('[data-confirmacion]', el);
      if (conf) conf.hidden = !nuevo;
      const mot = $('[data-motivo-cedula]', el);
      if (mot) mot.hidden = !nuevo;
    }
  });
  enlazarVotacion(el, cat);
  enlazarAutorizacion(el);

  // Lo que cambió frente a lo que se pintó (`formInicial`), no frente a `p`: si el navegador vació un valor que no puede
  // mostrar (fecha imposible, número con letras, opción que ya no existe) y nadie lo tocó, no se borra
  function cambios() {
    const f = $('#f-datos', el);
    const ahora = leerForm();
    const tocado = (k) => ahora[k] !== formInicial[k];
    const cuerpo = {}, base = {};
    const extra = {};
    for (const [k, val] of Object.entries(ahora)) {
      if (k.startsWith('et:') || AUXILIARES.includes(k) || !tocado(k)) continue;
      if (k.startsWith('extra.')) { extra[k.slice(6)] = val === '' ? null : val; continue; }
      if (k.startsWith('sens_')) { if (val) (cuerpo.sensibles ||= {})[k.slice(5)] = val; continue; }
      let v = val;
      if (typeof v === 'string') v = v.trim() === '' ? null : v.trim();
      if (NUMEROS.includes(k) && v != null) v = Number(v);
      if (k === 'jefe_hogar') v = v == null ? null : v === 'si';
      cuerpo[k] = v;
      base[k] = p[k] ?? null;
    }
    if (Object.keys(extra).length) cuerpo.extra = extra;
    // Puesto y mesa: si cambió cualquiera de sus campos, van los cuatro como los muestra el formulario
    if (['puesto', 'puesto_texto', 'municipio', 'mesa'].some(tocado)) {
      Object.assign(cuerpo, cuerpoVotacion(f.puesto.value, { texto: f.puesto_texto?.value.trim(), municipio: f.municipio?.value.trim(), mesa: f.mesa?.value }));
      if (!f.puesto.value) cuerpo.puesto_id = null;
      if (f.mesa && f.mesa.value === '' && formInicial.mesa !== '') cuerpo.mesa = null;
    }
    if (tocado('votacion_verificada')) cuerpo.votacion_verificada = !!ahora.votacion_verificada;
    if ('cedula' in cuerpo && cuerpo.cedula) {
      if (!p.cedula && ahora.cedula_confirmacion?.trim() !== cuerpo.cedula) return { error: 'Los dos números del documento no coinciden' };
      if (p.cedula) {
        const motivo = ahora.motivo_cambio_cedula?.trim();
        if (!motivo) return { error: 'Escriba el motivo del cambio de cédula' };
        cuerpo.motivo_cambio_cedula = motivo;
      }
    }
    const etAhora = $$('[data-et][aria-pressed="true"]', f).map((b) => Number(b.dataset.et));
    const etAntes = Object.entries(formInicial).filter(([k, val]) => k.startsWith('et:') && val === 'true').map(([k]) => Number(k.slice(3)));
    if (etAhora.length !== etAntes.length || etAhora.some((x) => !etAntes.includes(x))) {
      cuerpo.etiquetas = etAhora;
      cuerpo.etiquetas_base = etAntes;
    }
    if (Object.keys(base).length) cuerpo.base = base;
    return { cuerpo };
  }

  async function guardarCambios(cuerpo) {
    try {
      p = await api.patch(`/api/personas/${id}`, cuerpo);
      aviso('Ficha actualizada');
      for (const a of p.avisos || []) aviso(typeof a === 'string' ? a : a.mensaje || '', 'ok', 7000);
      pintar({ conservar: false });
      return true;
    } catch (err) {
      if (err instanceof ErrorApi && err.codigo === 'cambiada') {
        const base = await dialogoCambiada(err, cuerpo);
        if (base) return guardarCambios({ ...cuerpo, base });
        await recargar();
        aviso('Se conservaron los datos actuales');
        return false;
      }
      if (err instanceof ErrorApi && err.codigo === 'cedula_ocupada' && err.detalle?.id) aviso(`${err.message} (ficha ${err.detalle.id}${err.detalle.nombre ? ', ' + err.detalle.nombre : ''})`, 'error', 8000);
      else if (err instanceof ErrorApi && err.codigo === 'no_contactable') aviso(mensajeNoContactable(err), 'error', 8000);
      else if (err instanceof ErrorApi && err.detalle?.id) aviso(`${err.message} (ficha ${err.detalle.id})`, 'error', 6000);
      else avisoError(err);
      return false;
    }
  }

  el.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (e.target.id === 'f-nota') {
      try {
        p = await api.post(`/api/personas/${id}/notas`, { texto: e.target.texto.value }, { clave: nuevaClave() });
        aviso('Nota guardada'); pintar();
      } catch (err) { avisoError(err); }
      return;
    }
    if (e.target.id !== 'f-datos') return;
    const boton = e.target.querySelector('[type="submit"]');
    const { cuerpo, error } = cambios();
    if (error) { aviso(error, 'error'); return; }
    if (!Object.keys(cuerpo).length) { aviso('No hay cambios para guardar'); return; }
    boton.disabled = true;
    try { await guardarCambios(cuerpo); } finally { boton.disabled = false; }
  });

  async function unir() {
    const { el: d, cerrar } = dialogo({
      titulo: 'Unir con otra ficha', ancho: true,
      cuerpo: html`<p class="sec" style="margin-top:0">Busque la otra ficha de esta misma persona. Esta ficha conserva sus datos y recibe lo que le falte, más los trámites, reuniones y notas de la otra.</p>
        <input class="entrada" id="buscar-unir" placeholder="Nombre, cédula o teléfono">
        <div class="resultados" id="res-unir"></div>`,
    });
    const pintarRes = (filas) => montar($('#res-unir', d), html`${(Array.isArray(filas) ? filas : filas?.filas || []).filter((x) => x.id !== id).map((x) => html`<div class="resultado"><div class="q"><b>${x.nombre}</b>
      <small>${textoCedula(x) || 'sin cédula'} · ${x.telefono || 'sin teléfono'} · ${titulo(x.lugar || '')}${x.parecido ? ` · parecido ${x.parecido} %` : ''}</small></div>
      <button class="btn chico oscuro" data-con="${x.id}">Unir</button></div>`)}`);
    try { pintarRes(await api.get(`/api/personas/${id}/parecidas`)); } catch (err) { avisoError(err); }
    $('#buscar-unir', d).addEventListener('input', async (ev) => { if (ev.target.value.length >= 2) { try { pintarRes(await api.get('/api/buscar', { q: ev.target.value })); } catch { /* sigue escribiendo */ } } });
    $('#res-unir', d).addEventListener('click', async (ev) => {
      const b = ev.target.closest('[data-con]');
      if (!b) return;
      try {
        p = await api.post(`/api/personas/${id}/fusionar`, { con_id: Number(b.dataset.con) });
        cerrar(); aviso('Fichas unidas'); pintar(); refrescarInsignias();
      } catch (err) { avisoError(err); }
    });
  }

  pintar();
  return () => { turnoMini++; quitarPendiente(); mini?.remove(); mini = null; };
}

function resumenDetalle(txt) {
  try {
    const d = JSON.parse(txt);
    return Object.entries(d).map(([k, v]) => `${k}: ${v && typeof v === 'object' && 'antes' in v ? `${v.antes ?? '—'} → ${v.despues ?? '—'}` : JSON.stringify(v)}`).join('\n');
  } catch { return txt; }
}
