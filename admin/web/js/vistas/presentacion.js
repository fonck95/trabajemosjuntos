// Vista Presentación: la propuesta Yondó 2028–2031 (la presentación pública, web/propuesta.html del sitio) dentro del
// panel, para mostrarla y explicarla, a mano o con el asistente (herramienta `presentacion`, docs/agente.md).
//
// * La presentación va en un <iframe> sin `sandbox` (con él no cargaría sus módulos ni sus datos; el límite de verdad es
//   la CSP del sitio). En el servicio único el sitio está en la raíz del mismo origen (/propuesta); con el panel
//   desplegado aparte, en `SITIO_URL` (la dice /api/yo). Sin sitio, un aviso claro.
// * Se habla con ella por postMessage (web/js/propuesta/mando.js): solo con su ventana y su origen, nunca con '*', y lo
//   que responde se valida. La vista se registra en el puente del asistente (agente-presentacion.js) recién cuando la
//   presentación avisa que cargó (`listo`): lo que el asistente pidió antes espera en la cola del puente.
// * /presentacion?pantalla=1 es el modo proyector: sin menú ni asistente, la presentación ocupa toda la ventana y la
//   ventana se anuncia al resto de las pestañas (el puente): el asistente de la pestaña del chat la maneja desde ahí.
//   Mientras viva, manda ella: la barra de la pestaña del chat muestra su paso, sus botones le mandan la orden solo a
//   ella y el iframe de aquí la sigue (también cuando el paso cambia allá, con el teclado o el control remoto); lo que
//   se haga en el iframe de aquí (su control, su índice) va allá.
//   Se abre con un enlace (`target="_blank"`), no con window.open: con COOP same-origin la ventana no se podría manejar
//   y no hace falta, porque el canal es por origen.
// * Los estilos (css/presentacion.css) los carga la vista, como agente.js los suyos.
import { api } from '../api.js';
import { BASE, url } from '../base.js';
import { $, html, icono, montar } from '../ui.js';
import { CANAL, VERSION, accionPresentacion, accionesPresentacion, avisarEstado, estadoPresentacion, estadoValido,
  presentacionNoDisponible, proyectorVivo, registrarPresentacion } from '../agente-presentacion.js';

const ESPERA_LISTO_MS = 45000;   // la presentación carga sus datos y la maqueta 3D: si en esto no avisó, se dice
const ESPERA_ORDEN_MS = 12000;   // un cambio de capítulo con su telón y la maqueta del módulo tarda unos segundos
const SITIO = /^(https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?|http:\/\/(127\.0\.0\.1|localhost)(:\d{1,5})?)(\/[A-Za-z0-9._~%-]*)*$/;

let estilos = null;
function cargarEstilos() {
  estilos ||= new Promise((listo) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = new URL('../../css/presentacion.css', import.meta.url).href;
    l.dataset.presentacion = '';
    l.onload = l.onerror = () => listo();
    document.head.append(l);
  });
  return estilos;
}

/** Dónde está la presentación: {src, origen} o null si este servidor no tiene el sitio. */
async function direccion() {
  if (BASE) return { src: `${location.origin}/propuesta`, origen: location.origin };   // servicio único: el sitio en la raíz
  let sitio = null;
  try { sitio = (await api.get('/api/yo'))?.sitio_url; } catch { sitio = null; }
  if (typeof sitio !== 'string' || !SITIO.test(sitio)) return null;
  const u = new URL(`${sitio.replace(/\/+$/, '')}/propuesta`);
  return { src: u.href, origen: u.origin };
}

/** La orden para mando.js de una acción del puente (ya validada por `accionPresentacion`). */
function ordenDe(p) {
  const o = p.op === 'ir' ? { orden: 'ir', capitulo: p.capitulo, ...(p.paso ? { paso: p.paso } : {}) }
    : p.op === 'siguiente' || p.op === 'anterior' ? { orden: 'avanzar', d: p.op === 'siguiente' ? 1 : -1 }
      : { orden: p.op };
  if (p.explicacion) o.explicacion = p.explicacion;
  return o;
}

export async function vistaPresentacion(el, { q } = {}) {
  await cargarEstilos();
  const proyector = q?.get?.('pantalla') === '1';
  const raiz = document.documentElement;
  if (proyector) raiz.dataset.proyector = '';
  const conPantalla = !!document.fullscreenEnabled;
  montar(el, html`
    <section class="presentacion${proyector ? ' proyector' : ''}" aria-label="Presentación de la propuesta 2028–2031">
      <div class="pres-barra" role="toolbar" aria-label="Presentación">
        <div class="pres-donde"><b id="pres-capitulo">Presentación de la propuesta</b><small id="pres-paso">Cargando la presentación…</small></div>
        <div class="pres-botones">
          <button type="button" class="btn" id="pres-anterior" aria-label="Paso anterior" title="Paso anterior" disabled>${icono('anterior')}</button>
          <button type="button" class="btn primario" id="pres-siguiente" aria-label="Paso siguiente" title="Paso siguiente" disabled><span>Siguiente</span>${icono('siguiente')}</button>
          ${conPantalla ? html`<button type="button" class="btn" id="pres-pantalla" aria-label="Pantalla completa" title="Pantalla completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
          <a class="btn" id="pres-otra" href="${url('/presentacion?pantalla=1')}" target="_blank" rel="noopener" aria-label="Abrir en otra pantalla (proyector)" title="Abre la presentación en otra ventana para el proyector: el asistente la sigue manejando desde aquí">${icono('proyector')}<span>Abrir en otra pantalla</span></a>
        </div>
      </div>
      <p class="pres-remoto" id="pres-remoto" role="status" hidden>${icono('proyector')}<span>La presentación se está mostrando en otra pantalla: el asistente, estos botones y la presentación de aquí la manejan allá.</span></p>
      <div class="pres-marco" id="pres-marco"></div>
      ${proyector && conPantalla ? html`<button type="button" class="btn oscuro pres-completa" id="pres-completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
    </section>`);
  const marco = $('#pres-marco', el), capituloEl = $('#pres-capitulo', el), pasoEl = $('#pres-paso', el);
  const anterior = $('#pres-anterior', el), siguiente = $('#pres-siguiente', el), remoto = $('#pres-remoto', el);
  const limpiezas = [() => { if (proyector) delete raiz.dataset.proyector; }];
  const limpiar = () => { for (const f of limpiezas.splice(0)) { try { f(); } catch { /* nada */ } } };

  const d = await direccion();
  if (!d) {
    sinPresentacion('La presentación no está en este servidor',
      'El panel se sirve solo, sin el sitio público. Para verla aquí, el administrador configura SITIO_URL con la dirección del sitio (o se usa el servicio único, que sirve sitio y panel juntos).');
    return limpiar;
  }

  montar(marco, html`<iframe id="pres-iframe" src="${d.src}" title="Presentación de la propuesta Yondó 2028–2031" allow="fullscreen" allowfullscreen referrerpolicy="no-referrer"></iframe>`);
  const iframe = $('#pres-iframe', el);
  let estado = null;
  let quitarRegistro = null;
  let nro = 0;
  const pendientes = new Map();   // id de la orden → resolver

  function sinPresentacion(titulo, detalle) {
    montar(marco, html`<div class="vacio pres-sin"><b>${titulo}</b>${detalle}</div>`);
    pasoEl.textContent = titulo;
    anterior.disabled = siguiente.disabled = true;
    presentacionNoDisponible(titulo);
  }

  // Lo que ve la sala: con una ventana de proyector viva, su estado (el paso también cambia allá, con el control remoto
  // o el teclado, y el iframe de aquí lo sigue con un momento de retraso); si no, el de este iframe
  function pintarEstado() {
    const e = (!proyector && estadoPresentacion()) || estado;
    if (!e) return;
    capituloEl.textContent = e.nombre || e.capitulo;
    pasoEl.textContent = `Paso ${e.paso} de ${e.total}${e.titulo ? ` · ${e.titulo}` : ''}`;
  }
  // Y en la pestaña del chat, el aviso de que se está mostrando en otra pantalla: en el acto cuando el puente avisa que
  // cambió algo del proyector (`cambio`) y cada poco, porque uno que se cerró sin avisar solo deja de contar al vencer
  // su latido (y entonces la barra vuelve a la de aquí)
  function mirar() {
    if (!proyector) remoto.hidden = !proyectorVivo();
    pintarEstado();
  }

  function orden(o) {
    return new Promise((ok) => {
      const id = ++nro;
      const reloj = setTimeout(() => { pendientes.delete(id); ok({ ok: false, error: 'La presentación no respondió' }); }, ESPERA_ORDEN_MS);
      pendientes.set(id, (r) => { clearTimeout(reloj); ok(r); });
      try {
        iframe.contentWindow.postMessage({ canal: CANAL, v: VERSION, id, ...o }, d.origen);
      } catch {
        pendientes.delete(id);
        clearTimeout(reloj);
        ok({ ok: false, error: 'La presentación no está abierta' });
      }
    });
  }

  // Lo que el asistente (o los botones) piden: una orden por acción, en orden, cada una con su resultado
  async function aplicar(lista) {
    const res = [];
    for (const a of Array.isArray(lista) ? lista : []) {
      const p = accionPresentacion(a);
      if (!p) { res.push({ op: typeof a?.op === 'string' ? a.op.slice(0, 30) : null, ok: false, error: 'Acción no válida' }); continue; }
      const r = await orden(ordenDe(p));
      res.push({ op: p.op, ok: r.ok === true, ...(r.error ? { error: r.error } : {}) });
    }
    return res;
  }

  // Si tarda (un equipo lento arma la maqueta 3D con la CPU), se dice, pero el iframe se queda: su `listo` vale aunque
  // llegue tarde. Antes se quitaba y la presentación ya no se podía usar hasta recargar
  let lista = false;
  const tListo = setTimeout(() => {
    if (!lista) pasoEl.textContent = 'La presentación está tardando en cargar… (si no aparece, recargue la página)';
  }, ESPERA_LISTO_MS);
  limpiezas.push(() => clearTimeout(tListo));
  // Y se le pregunta en qué paso está al cargar y cada poco hasta que conteste: si su `listo` salió antes de que esta
  // vista escuchara (o se perdió), la respuesta a «estado» la da por lista igual
  let tPedir = 0;
  const pedirEstado = () => {
    if (lista || !iframe.isConnected) return;
    try { iframe.contentWindow?.postMessage({ canal: CANAL, v: VERSION, orden: 'estado' }, d.origen); } catch { /* aún no */ }
    tPedir = setTimeout(pedirEstado, 2000);
  };
  limpiezas.push(() => clearTimeout(tPedir));

  function alMensaje(e) {
    if (e.source !== iframe.contentWindow || e.origin !== d.origen) return;
    const m = e.data;
    if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
    if (m.tipo !== 'listo' && m.tipo !== 'estado' && m.tipo !== 'error') return;
    const nuevo = estadoValido(m);
    if (nuevo) { estado = nuevo; pintarEstado(); }
    if (Number.isInteger(m.id) && pendientes.has(m.id)) {
      const resolver = pendientes.get(m.id);
      pendientes.delete(m.id);
      resolver({ ok: m.tipo === 'estado', ...(m.tipo === 'error' ? { error: typeof m.error === 'string' ? m.error.slice(0, 160) : 'No se pudo' } : {}) });
    }
    if (!lista && (m.tipo === 'listo' || (m.tipo === 'estado' && nuevo))) {
      lista = true;
      clearTimeout(tListo);
      clearTimeout(tPedir);
      anterior.disabled = siguiente.disabled = false;
      quitarRegistro ||= registrarPresentacion({ aplicar, estado: () => estado, cambio: mirar,
        ...(proyector ? { proyector: true } : {}) });
      if (proyector) iframe.focus({ preventScroll: true });   // las flechas del teclado van a la presentación
    }
    if (nuevo) avisarEstado();
  }
  window.addEventListener('message', alMensaje);
  limpiezas.push(() => window.removeEventListener('message', alMensaje));
  limpiezas.push(() => { quitarRegistro?.(); quitarRegistro = null; });
  limpiezas.push(() => { for (const r of pendientes.values()) r({ ok: false, error: 'Se cerró la presentación' }); pendientes.clear(); });

  // Una página que no es la presentación (un 404, el sitio sin construir): en el mismo origen se ve al cargar; si no,
  // vence el plazo
  iframe.addEventListener('load', () => {
    try {
      const doc = iframe.contentDocument;
      if (doc && !doc.getElementById('pres')) { sinPresentacion('La presentación no está en este servidor', 'El sitio público no trae la presentación de la propuesta (propuesta.html).'); return; }
    } catch { /* de otro origen: no se puede mirar */ }
    pedirEstado();
  });

  // Con un proyector vivo, el paso lo da él (el puente le manda la orden solo a él y este iframe lo sigue): así los
  // botones llevan a las dos pantallas al mismo paso aunque el de allá haya cambiado sin pasar por aquí
  const mover = (op) => {
    accionesPresentacion([{ tipo: 'presentacion', op }]).catch(() => {});
  };
  anterior.addEventListener('click', () => mover('anterior'));
  siguiente.addEventListener('click', () => mover('siguiente'));
  const pantalla = () => {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    else marco.requestFullscreen?.().catch(() => {});
  };
  $('#pres-pantalla', el)?.addEventListener('click', pantalla);
  const completa = $('#pres-completa', el);
  if (completa) {
    completa.addEventListener('click', pantalla);
    const alCambiar = () => { completa.hidden = !!document.fullscreenElement; };
    document.addEventListener('fullscreenchange', alCambiar);
    limpiezas.push(() => document.removeEventListener('fullscreenchange', alCambiar));
  }

  // En la pestaña del chat: si hay una ventana de proyector viva, se dice (los botones y el asistente la manejan allá) y
  // la barra muestra su paso
  if (!proyector) {
    mirar();
    const t = setInterval(mirar, 1500);
    limpiezas.push(() => clearInterval(t));
  }
  return limpiar;
}
