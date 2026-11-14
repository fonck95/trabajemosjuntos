// Vista Presentación: la propuesta Yondó 2028–2031 en su versión técnica (la presentación pública del sitio,
// web/propuesta.html?modo=tecnica: lo que se construye, sin costos, con los modelos 3D del atlas) dentro del panel, para
// mostrarla y explicarla, a mano o con el asistente (herramienta `presentacion`, docs/agente.md).
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
//   se haga en el iframe de aquí (su control, su índice) va allá. Con dos ventanas de proyector manda la última que se
//   abrió y la otra la sigue como el iframe de aquí (el puente).
//   Se abre con un enlace (`target="_blank"`), no con window.open: con COOP same-origin la ventana no se podría manejar
//   y no hace falta, porque el canal es por origen.
// * /presentacion?off=1 es la pantalla en off (app/pantalla.py): la abre la persona en el proyector o en un televisor,
//   desde cualquier navegador con su sesión, y no tiene controles. Sigue el estado que dejan en el servidor el asistente
//   del panel y un agente por MCP (`GET /api/pantalla?v=`, cada POLL_MS): solo cambia cuando se le pide algo concreto a
//   un agente. La presentación queda inerte (ni clics ni teclado) y sin sus botones (mando.js, vista {controles:
//   false}); no se anuncia al puente ni al proyector, y en esa ventana no está el asistente. Con `completa` llena la
//   ventana, sin el menú ni las barras del panel; Escape la devuelve hasta la próxima orden de pantalla completa.
// * En la pestaña del chat, `pantalla_completa` del asistente hace lo mismo con esta vista (el botón del asistente queda
//   a mano para seguir hablando); Escape la devuelve.
// * El recorrido narrado (reproductor.js, voz.js): la acción `recorrido` no se convierte en una orden; la reproduce
//   aquí el reproductor, que lleva el reloj de la explicación y le manda a la presentación escena, frase, pausa y
//   cierre. Suena en la página que mira la sala (la pestaña del chat, la ventana del proyector o la pantalla en off),
//   con la voz del navegador si la persona la encendió con el botón «Voz» de esa ventana; si ya la había encendido antes,
//   la activa el primer toque o tecla de la persona, también sobre la presentación (mando.js lo avisa con `gesto`: en el
//   proyector el iframe ocupa la ventana y los toques no llegan a esta). Las teclas y los botones de la presentación lo
//   manejan mientras suena (avanzan escenas, pausan, detienen), y si la persona mueve la imagen se pausa. Cualquier otra
//   acción lo detiene antes. El avance va al puente (la tarjeta del chat), a la barra y al servidor (POST
//   /api/pantalla/progreso), así el asistente y los agentes por MCP saben dónde va; si el servidor ya no lo tiene por
//   vigente (otra orden lo cerró, otro recorrido lo reemplazó), se detiene aquí también.
// * Los estilos (css/presentacion.css) los carga la vista, como agente.js los suyos.
import { ErrorApi, api } from '../api.js';
import { BASE, url } from '../base.js';
import { $, html, icono, montar } from '../ui.js';
import { AVISOS, CANAL, TERMINALES, VERSION, accionPresentacion, accionesPresentacion, avisarEstado, avisarRecorrido,
  controlRecorrido, estadoDePantalla, estadoPresentacion, estadoValido, ordenesHacia, presentacionNoDisponible,
  proyectorVivo, recorridoEnCurso, registrarPresentacion } from '../agente-presentacion.js';
import { crearReproductor } from '../reproductor.js';
import { crearVoz } from '../voz.js';

const ESPERA_LISTO_MS = 45000;   // la presentación carga sus datos y la maqueta 3D: si en esto no avisó, se dice
const ESPERA_ORDEN_MS = 12000;   // un cambio de capítulo con su telón y la maqueta del módulo tarda unos segundos
const POLL_MS = 1500;            // la pantalla en off pregunta por su estado (app/pantalla.py la da por cerrada a los 10 s)
const POLL_ERROR_MS = 4000;      // sin conexión con el panel, reintenta más espaciado
const LATIDO_MS = 4000;          // durante una espera larga, la pantalla en off sigue avisando que está abierta
const PRIMERA_ESCENA_MS = 10000; // al aceptar un recorrido se espera a que la primera escena esté a la vista (o esto)
const VIGENCIA_RECORRIDO_S = 90; // la pantalla en off narra un recorrido nuevo; uno viejo se aplica en silencio
const REANUDAR_S = 20;           // y reanuda uno a medias si su último avance es de hace menos que esto
const TEXTO_VOZ = { activa: 'Voz activa', apagada: 'Voz', sin_activar: 'Toque para activar la voz', sin_voces: 'Sin voces en español' };
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
  if (BASE) return { src: `${location.origin}/propuesta?modo=tecnica`, origen: location.origin };   // servicio único: el sitio en la raíz
  let sitio = null;
  try { sitio = (await api.get('/api/yo'))?.sitio_url; } catch { sitio = null; }
  if (typeof sitio !== 'string' || !SITIO.test(sitio)) return null;
  const u = new URL(`${sitio.replace(/\/+$/, '')}/propuesta?modo=tecnica`);
  return { src: u.href, origen: u.origin };
}

/** Dónde queda la pantalla al terminar o detener un recorrido en la escena `esc`: sus campos base (`estado_de_escena`
 * de app/recorrido.py), sobre lo último aplicado (el tema y la pantalla completa no cambian). */
function baseDeEscena(antes, esc) {
  return { ...(antes || {}), capitulo: esc.capitulo, paso: esc.paso, explicacion: null, panel: esc.panel, indice: false,
    fichas: false, ...esc.visual };
}

const dormir = (ms) => new Promise((ok) => { setTimeout(ok, ms); });

/** La orden para mando.js de una acción del puente (ya validada por `accionPresentacion`). */
function ordenDe(p) {
  if (p.op === 'visual') {
    const o = { orden: 'visual' };
    for (const [k, v] of Object.entries(p)) if (k !== 'tipo' && k !== 'op') o[k] = v;
    return o;
  }
  if (p.op === 'vista') {
    const o = { orden: 'vista' };
    for (const k of ['panel', 'indice', 'fichas']) if (typeof p[k] === 'boolean') o[k] = p[k];
    return o;
  }
  const o = p.op === 'ir' ? { orden: 'ir', capitulo: p.capitulo, ...(p.paso ? { paso: p.paso } : {}) }
    : p.op === 'siguiente' || p.op === 'anterior' ? { orden: 'avanzar', d: p.op === 'siguiente' ? 1 : -1 }
      : { orden: p.op };
  if (p.explicacion) o.explicacion = p.explicacion;
  return o;
}

export async function vistaPresentacion(el, { q } = {}) {
  await cargarEstilos();
  const proyector = q?.get?.('pantalla') === '1';
  const off = !proyector && q?.get?.('off') === '1';
  const raiz = document.documentElement;
  if (proyector) raiz.dataset.proyector = '';
  if (off) raiz.dataset.presOff = '';
  const conPantalla = !!document.fullscreenEnabled;
  montar(el, html`
    <section class="presentacion${proyector ? ' proyector' : ''}${off ? ' en-off' : ''}" aria-label="Presentación de la propuesta 2028–2031">
      ${off ? html`<div class="pres-barra" role="status" aria-label="Pantalla en off">
        <div class="pres-donde"><b id="pres-off-capitulo">Pantalla en off</b><small id="pres-off-paso">Cargando la presentación…</small></div>
        <div class="pres-botones">
          <span class="chip borde pres-off-chip">${icono('agente')}<span id="pres-off-estado">Esperando al asistente</span></span>
          <button type="button" class="btn pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta pantalla (la del navegador)">${icono('voz')}<span>Voz</span></button>
          <a class="btn" id="pres-salir-off" href="${url('/presentacion')}">${icono('cerrar')}<span>Salir del modo en off</span></a>
        </div>
      </div>
      <p class="pres-remoto pres-off-aviso" role="note">${icono('agente')}<span>Esta pantalla no tiene controles: solo cambia cuando le pide algo concreto al asistente del panel (desde otro equipo o el celular) o a un agente por MCP. Pídale «pantalla completa» para que llene la ventana; Escape la devuelve aquí.</span></p>` : ''}
      <div class="pres-barra" role="toolbar" aria-label="Presentación"${off ? ' hidden' : ''}>
        <div class="pres-donde"><b id="pres-capitulo">Presentación de la propuesta</b><small id="pres-paso">Cargando la presentación…</small></div>
        <div class="pres-botones">
          <button type="button" class="btn" id="pres-anterior" aria-label="Paso anterior" title="Paso anterior" disabled>${icono('anterior')}</button>
          <button type="button" class="btn primario" id="pres-siguiente" aria-label="Paso siguiente" title="Paso siguiente" disabled><span>Siguiente</span>${icono('siguiente')}</button>
          ${off ? '' : html`<button type="button" class="btn pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta pestaña (la del navegador)">${icono('voz')}<span>Voz</span></button>`}
          ${conPantalla ? html`<button type="button" class="btn" id="pres-pantalla" aria-label="Pantalla completa" title="Pantalla completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
          <a class="btn" id="pres-otra" href="${url('/presentacion?pantalla=1')}" target="_blank" rel="noopener" aria-label="Abrir en otra pantalla (proyector)" title="Abre la presentación en otra ventana para el proyector: el asistente la sigue manejando desde aquí">${icono('proyector')}<span>Abrir en otra pantalla</span></a>
          <a class="btn" id="pres-off" href="${url('/presentacion?off=1')}" target="_blank" rel="noopener" aria-label="Pantalla en off" title="Una pantalla sin controles para el proyector o un televisor, en este equipo o en otro: solo cambia cuando se le pide al asistente o a un agente por MCP">${icono('agente')}<span>Pantalla en off</span></a>
        </div>
      </div>
      <p class="pres-remoto" id="pres-remoto" role="status" hidden>${icono('proyector')}<span>La presentación se está mostrando en otra pantalla: el asistente, estos botones y la presentación de aquí la manejan allá.</span></p>
      <div class="pres-marco" id="pres-marco"></div>
      ${proyector ? html`<div class="pres-flotantes">
        ${conPantalla ? html`<button type="button" class="btn oscuro pres-completa" id="pres-completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
        <button type="button" class="btn oscuro pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta ventana (la del navegador)">${icono('voz')}<span>Voz</span></button>
      </div>` : ''}
    </section>`);
  const marco = $('#pres-marco', el);
  // En off la barra que se ve es la suya (la de los botones queda oculta, sin ids repetidos)
  const capituloEl = $(off ? '#pres-off-capitulo' : '#pres-capitulo', el), pasoEl = $(off ? '#pres-off-paso' : '#pres-paso', el);
  const anterior = $('#pres-anterior', el), siguiente = $('#pres-siguiente', el), remoto = $('#pres-remoto', el);
  const limpiezas = [() => { if (proyector) delete raiz.dataset.proyector; if (off) delete raiz.dataset.presOff; },
    () => { delete raiz.dataset.presLlena; }];
  const limpiar = () => { for (const f of limpiezas.splice(0)) { try { f(); } catch { /* nada */ } } };

  const d = await direccion();
  if (!d) {
    sinPresentacion('La presentación no está en este servidor',
      'El panel se sirve solo, sin el sitio público. Para verla aquí, el administrador configura SITIO_URL con la dirección del sitio (o se usa el servicio único, que sirve sitio y panel juntos).');
    return limpiar;
  }

  montar(marco, html`<iframe id="pres-iframe" src="${d.src}" title="Presentación de la propuesta Yondó 2028–2031" allow="fullscreen" allowfullscreen referrerpolicy="no-referrer"></iframe>`);
  const iframe = $('#pres-iframe', el);
  // En off nadie la toca: ni clics ni teclado (las flechas y la barra espaciadora la moverían por su cuenta). Y el foco
  // no se queda en ella: la presentación enfoca el índice al abrirlo, y entonces las teclas irían allá
  if (off) {
    iframe.inert = true;
    iframe.tabIndex = -1;
    const devolverFoco = () => setTimeout(() => { if (document.activeElement === iframe) iframe.blur(); }, 0);
    window.addEventListener('blur', devolverFoco);
    limpiezas.push(() => window.removeEventListener('blur', devolverFoco));
  }
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
    const e = (!proyector && !off && estadoPresentacion()) || estado;
    if (!e) return;
    capituloEl.textContent = e.nombre || e.capitulo;
    // con un recorrido sonando (aquí o en el proyector), la barra dice dónde va
    const aqui = rep.estado();
    const alla = !aqui || !rep.activo() ? recorridoEnCurso() : null;
    if (rep.activo() && aqui) {
      const donde = aqui.fase === 'cierre' ? 'en resumen' : `escena ${aqui.n} de ${aqui.de}`;
      pasoEl.textContent = `Recorrido · ${rep.recorrido().titulo} · ${donde}${aqui.pausado ? ' · en pausa' : ''}`;
    } else if (alla?.donde === 'proyector') {
      pasoEl.textContent = `Recorrido en el proyector · escena ${alla.n} de ${alla.de}${alla.fase === 'pausa' ? ' · en pausa' : ''}`;
    } else {
      pasoEl.textContent = `Paso ${e.paso} de ${e.total}${e.titulo ? ` · ${e.titulo}` : ''}`;
    }
    const sonando = rep.activo() || alla?.donde === 'proyector';
    for (const [b, que] of [[anterior, 'anterior'], [siguiente, 'siguiente']]) {
      const t = `${sonando ? 'Escena' : 'Paso'} ${que}`;
      b.title = t;
      b.setAttribute('aria-label', t);
    }
  }
  // Y en la pestaña del chat, el aviso de que se está mostrando en otra pantalla: en el acto cuando el puente avisa que
  // cambió algo del proyector (`cambio`) y cada poco, porque uno que se cerró sin avisar solo deja de contar al vencer
  // su latido (y entonces la barra vuelve a la de aquí)
  function mirar() {
    if (!proyector && !off) remoto.hidden = !proyectorVivo();
    pintarEstado();
  }

  function orden(o, { plazo = ESPERA_ORDEN_MS } = {}) {
    return new Promise((ok) => {
      const id = ++nro;
      const reloj = setTimeout(() => { pendientes.delete(id); ok({ ok: false, error: 'La presentación no respondió', sinRespuesta: true }); }, plazo);
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

  // Llenar la ventana: sin el menú ni las barras del panel (css/presentacion.css, html[data-pres-llena]). Escape la
  // devuelve; en la pantalla en off, hasta la próxima orden de pantalla completa
  const llenar = (v) => { if (v && !proyector) raiz.dataset.presLlena = ''; else delete raiz.dataset.presLlena; };
  const alTecla = (e) => { if (e.key === 'Escape' && 'presLlena' in raiz.dataset) llenar(false); };
  document.addEventListener('keydown', alTecla);
  limpiezas.push(() => document.removeEventListener('keydown', alTecla));

  // ── El recorrido narrado: el reproductor de esta página, su voz y el avance ──
  const voz = crearVoz();
  // El avance va al servidor de a uno: el más nuevo reemplaza al que esperaba y siempre sale (no se pierde la última fase)
  let avanceEnVuelo = false, avancePendiente = null;
  async function enviarAvance(p) {
    avancePendiente = p;
    if (avanceEnVuelo) return;
    avanceEnVuelo = true;
    while (avancePendiente) {
      const x = avancePendiente;
      avancePendiente = null;
      try {
        await api.post('/api/pantalla/progreso', x);
      } catch (err) {
        // El servidor ya no lo tiene por vigente: lo cerró otra orden (un agente por MCP, el asistente con la pantalla en
        // off abierta) o llegó otro recorrido. Si es el que suena aquí, se detiene: si no, seguiría hablando en la sala
        // sin que el asistente, la tarjeta ni la barra lo vean. Sin conexión, sigue. Con 'otra_orden', no 'reemplazo':
        // un proyector que se abre después no lo retoma (el puente le pasa al nuevo el que se soltó con 'reemplazo')
        if (err instanceof ErrorApi && err.estado === 409 && rep.activo() && rep.recorrido()?.id === x.rid) {
          rep.detener('otra_orden').catch(() => {});
        }
      }
    }
    avanceEnVuelo = false;
  }
  let alTerminarRecorrido = null;   // la pantalla en off deja `aplicado` en la escena donde quedó
  const rep = crearReproductor({
    orden, voz,
    avisar: (pr) => {
      avisarRecorrido(pr);
      pintarEstado();
      enviarAvance(pr);
      if (TERMINALES.includes(pr.fase)) { try { alTerminarRecorrido?.(pr); } catch { /* nada */ } }
    },
  });
  limpiezas.push(() => { rep.detener('otra_orden'); voz.callar(); });
  limpiezas.push(() => voz.soltar());   // sus oyentes de la ventana y de la síntesis: si no, cada montaje sumaría otros
  const botonesVoz = [...el.querySelectorAll('.pres-voz')];
  const pintarVoz = () => {
    const e = voz.estado();
    for (const b of botonesVoz) {
      b.setAttribute('aria-pressed', String(e === 'activa'));
      b.disabled = e === 'sin_voces';
      b.dataset.voz = e;
      const t = b.querySelector('span');
      if (t) t.textContent = TEXTO_VOZ[e];
      b.setAttribute('aria-label', TEXTO_VOZ[e]);
    }
  };
  for (const b of botonesVoz) b.addEventListener('click', () => { if (voz.estado() === 'activa') voz.apagar(); else voz.encender(); });
  limpiezas.push(voz.alCambiar(pintarVoz));
  pintarVoz();

  // `enPausa`: la pantalla en off que se recargó con el recorrido en pausa lo retoma en su escena y en pausa. La pausa
  // entra cuando la escena ya está a la vista (antes, el cambio de imagen la taparía con «preparando»)
  async function aplicarRecorrido(p, { enPausa = false } = {}) {
    const primera = rep.iniciar(p.recorrido, { desde: p.desde || 1 });
    if (enPausa) primera.then((ok) => { if (ok && rep.recorrido() === p.recorrido) rep.pausar('boton'); });
    await Promise.race([primera, dormir(PRIMERA_ESCENA_MS)]);
    return { op: p.op, ok: true };
  }
  function controlar(p) {
    const r = rep.recorrido();
    if (!r || r.id !== p.rid || !rep.activo()) return { op: p.op, ok: false, error: 'Ese recorrido ya no está sonando' };
    // el detener del servidor cuando el asistente mostró otra cosa: la tarjeta lo dice así, no como el botón Detener
    if (p.accion === 'detener' && p.motivo === 'otra_orden') rep.detener('otra_orden');
    else rep.control(p.accion, { suave: !!p.suave });
    return { op: p.op, ok: true };
  }

  // Lo que el asistente (o los botones) piden: una orden por acción, en orden, cada una con su resultado. Un recorrido
  // lo reproduce el reproductor; cualquier otra acción (salvo sus controles y la píldora) lo detiene antes
  async function aplicar(lista) {
    const res = [];
    for (const a of Array.isArray(lista) ? lista : []) {
      const p = accionPresentacion(a);
      if (!p) { res.push({ op: typeof a?.op === 'string' ? a.op.slice(0, 30) : null, ok: false, error: 'Acción no válida' }); continue; }
      if (p.op === 'recorrido') { res.push(await aplicarRecorrido(p)); continue; }
      if (p.op === 'control_recorrido') { res.push(controlar(p)); continue; }
      if (p.op === 'preparando') {
        if (!rep.activo()) await orden({ orden: 'narracion', preparando: p.activar });
        res.push({ op: p.op, ok: true });
        continue;
      }
      if (p.op === 'pantalla_completa') { llenar(p.activar); res.push({ op: p.op, ok: true }); continue; }
      if (rep.activo()) await rep.detener('otra_orden');
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
    // Un toque o una tecla de la persona sobre la presentación: enciende la voz que ya estaba elegida (en el proyector es
    // el único gesto que hay: el iframe ocupa la ventana). La activación del usuario dentro del iframe vale también aquí
    if (m.tipo === 'gesto') { voz.gesto(); return; }
    // La presentación sin controles (la pantalla en off) no atiende el teclado: Escape devuelve aquí la ventana. Con un
    // recorrido sonando, las teclas y los botones de la presentación lo manejan. Las que no son Escape también son un
    // gesto (Escape no le da al navegador la activación del usuario: con él la voz no podría hablar)
    if (m.tipo === 'tecla') {
      if (m.tecla !== 'Escape' && m.tecla !== 'detener') voz.gesto();
      if (m.tecla === 'Escape' && 'presLlena' in raiz.dataset) llenar(false);
      else if (rep.activo()) {
        if (m.tecla === 'siguiente') rep.siguiente();
        else if (m.tecla === 'anterior') rep.anterior();
        else if (m.tecla === 'pausa') rep.alternar('tecla');
        else if (m.tecla === 'detener') rep.detener('tecla');
      }
      return;
    }
    if (m.tipo !== 'listo' && m.tipo !== 'estado' && m.tipo !== 'error') return;
    const nuevo = estadoValido(m);
    if (nuevo) { estado = nuevo; pintarEstado(); }
    if (Number.isInteger(m.id) && pendientes.has(m.id)) {
      const resolver = pendientes.get(m.id);
      pendientes.delete(m.id);
      resolver({ ok: m.tipo === 'estado', ...(m.tipo === 'error' ? { error: typeof m.error === 'string' ? m.error.slice(0, 160) : 'No se pudo' } : {}),
        ...(m.tipo === 'estado' && AVISOS.includes(m.aviso) ? { aviso: m.aviso } : {}) });
    } else if (m.tipo === 'estado' && nuevo?.por === 'persona' && rep.activo()) {
      // la persona movió la imagen (un paso, la cámara): el recorrido se pausa; al seguir, la escena vuelve
      rep.alPersona();
    }
    // la presentación se recargó a mitad del recorrido: la escena en curso vuelve a empezar
    if (m.tipo === 'listo' && lista && rep.activo()) rep.repetir();
    if (!lista && (m.tipo === 'listo' || (m.tipo === 'estado' && nuevo))) {
      lista = true;
      clearTimeout(tListo);
      clearTimeout(tPedir);
      anterior.disabled = siguiente.disabled = false;
      if (off) seguirAlServidor();
      else {
        quitarRegistro ||= registrarPresentacion({ aplicar, estado: () => estado, cambio: mirar,
          recorrido: () => (rep.activo() ? { recorrido: rep.recorrido(), n: rep.estado().n } : null),
          soltarRecorrido: (motivo) => rep.detener(motivo),
          ...(proyector ? { proyector: true } : {}) });
        if (proyector) iframe.focus({ preventScroll: true });   // las flechas del teclado van a la presentación
      }
    }
    if (nuevo && !off) avisarEstado();
  }
  // La pantalla en off: pregunta cada POLL_MS por la versión del servidor y aplica solo lo que cambió, en orden (una
  // pregunta a la vez). Lo que tarda la presentación (el telón de un capítulo) no se pisa: la siguiente pregunta sale
  // cuando termina la anterior
  let tPoll = 0, versionVista = -1, aplicado = null, siguiendo = false;
  const offEstado = $('#pres-off-estado', el);
  // El recorrido en la pantalla en off: el que vio por última vez (id) y el último control que aplicó (n)
  let ridOff = null, controlOff = 0;
  if (off) {
    alTerminarRecorrido = (pr) => {
      const r = rep.recorrido();
      if (r && pr.rid === r.id) aplicado = baseDeEscena(aplicado, r.escenas[pr.n - 1]);
    };
  }
  // Un recorrido que esta pantalla ve por primera vez (se abrió o se recargó con él en el servidor). Si ya tuvo avance,
  // decide el avance: uno terminado no se vuelve a narrar; uno en pausa se retoma en su escena y en pausa (en pausa no
  // hay avances y su antigüedad no dice nada: antes se lo daba por viejo, la pantalla saltaba a la última escena y no
  // atendía el «continuar»); uno a medias con un avance reciente (la pantalla se recargó) sigue en su escena, y uno sin
  // noticias hace rato (la pantalla se cerró) no se narra. Sin avance, se narra si es nuevo: una pantalla que se abre
  // después no narra uno viejo. El que no se narra se queda en la escena de su último avance (`enSuEscena`)
  async function recorridoDeLaPantalla(e) {
    const x = e.recorrido;
    if (x && x.id !== ridOff) {
      ridOff = x.id;
      controlOff = e.control_recorrido?.n || 0;
      const pr = e.progreso;   // del mismo recorrido: `estadoDePantalla` descarta el de otro
      let desde = 0;
      if (pr) desde = !TERMINALES.includes(pr.fase) && (pr.fase === 'pausa' || pr.hace_s < REANUDAR_S) ? pr.n : 0;
      else if (x.edad_s < VIGENCIA_RECORRIDO_S) desde = 1;
      if (desde) {
        const { edad_s: _edad, ...r } = x;
        await aplicarRecorrido({ op: 'recorrido', recorrido: r, desde }, { enPausa: pr?.fase === 'pausa' });
      }
    } else if (!x && rep.activo()) {
      // el asistente pidió otra cosa o lo detuvo: el servidor lo cerró
      await rep.detener('otra_orden');
    } else if (x && rep.activo() && e.control_recorrido && e.control_recorrido.n > controlOff) {
      controlOff = e.control_recorrido.n;
      if (e.control_recorrido.accion !== 'reproducir') rep.control(e.control_recorrido.accion);
    }
  }
  // Mientras el servidor tiene abierto un recorrido, su base es la última escena (la que queda si termina): uno que esta
  // pantalla no narra, o que dejó de narrar sin que el servidor lo cierre, se queda en la escena de su último avance en
  // vez de saltar al final con la próxima versión (una pantalla completa, un control)
  const enSuEscena = (e) => {
    const esc = e.recorrido && e.progreso ? e.recorrido.escenas[e.progreso.n - 1] : null;
    return esc ? baseDeEscena(e, esc) : e;
  };
  async function seguirAlServidor() {
    if (siguiendo) return;
    siguiendo = true;
    await orden({ orden: 'vista', controles: false });
    const vuelta = async () => {
      if (!iframe.isConnected) return;
      let espera = POLL_MS;
      try {
        const r = await api.get(`/api/pantalla?v=${versionVista}`);
        const e = estadoDePantalla(r);
        if (e) {
          // Las esperas largas (la primera escena, hasta PRIMERA_ESCENA_MS; cada orden, hasta ESPERA_ORDEN_MS) no dejan de
          // avisar que la pantalla sigue abierta: si no, el servidor la daba por cerrada (VIVA_S) y un recorrido que el
          // asistente armaba en ese hueco salía para la pestaña. La respuesta no se usa: la próxima vuelta vuelve a leer
          const latido = setInterval(() => { api.get(`/api/pantalla?v=${versionVista}`).catch(() => {}); }, LATIDO_MS);
          let meta;
          try {
            await recorridoDeLaPantalla(e);
            // mientras suena un recorrido, lo que se ve lo pone él (solo la pantalla completa se aplica igual)
            meta = rep.activo() ? null : enSuEscena(e);
            for (const o of meta ? ordenesHacia(aplicado, meta) : []) {
              const res = await orden(o);
              if (!res.ok) console.warn('La pantalla en off no pudo aplicar', o.orden, res.error);
            }
          } finally { clearInterval(latido); }
          // Cada orden de pantalla completa se aplica, aunque no cambie el valor: así vuelve a llenar la ventana que
          // se devolvió con Escape
          if (!aplicado || aplicado.completa !== e.completa || aplicado.orden_completa !== e.orden_completa) llenar(e.completa);
          if (rep.activo()) aplicado = { ...(aplicado || e), completa: e.completa, orden_completa: e.orden_completa };
          else aplicado = meta;
          versionVista = e.v;
        }
        if (offEstado) offEstado.textContent = 'Conectada: la manejan el asistente y los agentes por MCP';
      } catch (err) {
        espera = POLL_ERROR_MS;
        if (offEstado) offEstado.textContent = err instanceof ErrorApi && err.estado === 0 ? 'Sin conexión: reintentando…' : 'No se pudo leer la pantalla: reintentando…';
      }
      if (iframe.isConnected) tPoll = setTimeout(vuelta, espera);
    };
    vuelta();
  }
  limpiezas.push(() => clearTimeout(tPoll));

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
  // Con un recorrido sonando (aquí o en el proyector), los botones pasan de escena
  const mover = (op) => {
    if (rep.activo()) { if (op === 'siguiente') rep.siguiente(); else rep.anterior(); return; }
    const alla = recorridoEnCurso();
    if (alla?.donde === 'proyector') { controlRecorrido(alla.rid, op).catch(() => {}); return; }
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
