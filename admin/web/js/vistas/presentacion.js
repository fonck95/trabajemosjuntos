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
// * /presentacion?pantalla=1 es el modo proyector: sin menú, la presentación ocupa toda la ventana y la ventana se
//   anuncia al resto de las pestañas (el puente): el asistente de la pestaña del chat la maneja desde ahí. El asistente
//   también se abre en esta ventana (su botón flota con los de la ventana y se atenúa con el ratón quieto:
//   data-pres-quieto), y lo que pide se aplica aquí mismo (en la ventana del proyector el puente no elige otro proyector).
//   El teclado y el control remoto son de la presentación: el asistente le devuelve el foco al cerrarse y, con el foco
//   fuera de ella (en el botón del asistente, en la página), sus teclas de avanzar y retroceder la mueven igual y el
//   foco vuelve a ella; al cargar no le quita el foco al chat donde la persona ya escribe.
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
//   false}); no se anuncia al puente ni al proyector. El asistente se puede abrir al lado, en la misma ventana (su botón
//   va en la barra; con `completa`, flotando como en el proyector): sus planes siguen yendo al servidor y los narra esta
//   vista; cuando el chat cambia algo, el puente lo avisa (`pantalla:pedir`) y se pregunta en el acto, sin esperar el
//   sondeo; el avance le llega a la tarjeta por el puente (`avisarRecorrido`) y su interruptor de voz maneja la de aquí
//   (`registrarVozLocal`). Cuenta como abierta desde que se monta (avisa con un latido mientras la presentación carga):
//   un plan pedido en el chat de aquí antes de eso iba a la pestaña y no lo narraba nadie. Con `completa` llena la
//   ventana, sin el menú ni las barras del panel; Escape la devuelve hasta la próxima orden de pantalla completa.
// * En la pestaña del chat, `pantalla_completa` del asistente hace lo mismo con esta vista (el botón del asistente queda
//   a mano para seguir hablando); Escape la devuelve.
// * El plan guiado (el recorrido narrado: reproductor.js, voz.js): la acción `recorrido` no se convierte en una orden;
//   la reproduce aquí el reproductor, que lleva el reloj de la explicación y le manda a la presentación cada paso del
//   plan (la escena: lo que se muestra ocurre mientras se dice), la frase que suena, la pausa y el cierre. Un plan
//   nuevo espera PREVIA_MS antes del primer paso (el chat lo muestra entero); uno que se reanuda, se vuelve a
//   reproducir, llega traspasado de otra ventana o la pantalla en off retoma, no. Suena en la página que mira la sala
//   (la pestaña del chat, la ventana del proyector o la pantalla en off), con la voz del navegador, que está encendida
//   mientras la persona no la apague (el botón «Voz» de esa ventana o el interruptor de la tarjeta del chat, que llega
//   por el puente: `alternarVoz`); la activa el primer toque o tecla de la persona en esa ventana, también sobre la
//   presentación (mando.js lo avisa con `gesto`: en el
//   proyector el iframe ocupa la ventana y los toques no llegan a esta). Las teclas y los botones de la presentación lo
//   manejan mientras suena (avanzan escenas, pausan, detienen), y si la persona mueve la imagen se pausa. Cualquier otra
//   acción lo detiene antes. El avance va al puente (la tarjeta del chat), a la barra y al servidor (POST
//   /api/pantalla/progreso), así el asistente y los agentes por MCP saben dónde va; si el servidor ya no lo tiene por
//   vigente (otra orden lo cerró, otro recorrido lo reemplazó), se detiene aquí también.
// * La presentación automática (app/automatica.py), solo en la pantalla en off: el botón «Presentación automática» de su
//   barra la enciende o la apaga (POST /api/pantalla/auto; también la enciende el asistente). Con ella encendida el
//   servidor arma, sin modelo, un plan por capítulo con un paso por cada paso de la presentación y una frase muy corta, y
//   esta pantalla se los pide uno tras otro (`crearAutomatica`: POST /api/pantalla/auto/siguiente cuando el reproductor
//   se queda sin plan). El plan llega por el sondeo con `auto: true` y se narra como cualquier otro, sin la espera de
//   «Plan listo»; el reproductor recibe esa clave y no espera el «¿Preguntas?» del final (sigue con el capítulo
//   siguiente). Un plan del asistente (la respuesta a una pregunta) lo reemplaza; al terminar, la automática sigue
//   donde iba (repite el paso que se estaba diciendo). Otra orden suelta la hace esperar más. La barra dice dónde va.
//   La vista que se va (otra vista del panel) suelta el plan automático sin avisar el «detenido» al servidor (`seFue`):
//   ese aviso lo cerraba y apagaba la automática para todos, también para otra pantalla en off que la narrara.
// * Los estilos (css/presentacion.css) los carga la vista, como agente.js los suyos.
import { ErrorApi, api } from '../api.js';
import { BASE, url } from '../base.js';
import { $, html, icono, montar } from '../ui.js';
import { AVISOS, CANAL, TERMINALES, VERSION, accionPresentacion, accionesPresentacion, avisarEstado, avisarRecorrido,
  controlRecorrido, estadoDePantalla, estadoPresentacion, estadoValido, ordenesHacia, presentacionNoDisponible,
  proyectorVivo, recorridoEnCurso, registrarPresentacion, registrarVozLocal } from '../agente-presentacion.js';
import { PREVIA_MS, crearReproductor } from '../reproductor.js';
import { crearVoz } from '../voz.js';

const ESPERA_LISTO_MS = 45000;   // la presentación carga sus datos y la maqueta 3D: si en esto no avisó, se dice
const ESPERA_ORDEN_MS = 12000;   // un cambio de capítulo con su telón y la maqueta del módulo tarda unos segundos
const POLL_MS = 1500;            // la pantalla en off pregunta por su estado (app/pantalla.py la da por cerrada a los 10 s)
const POLL_ERROR_MS = 4000;      // sin conexión con el panel, reintenta más espaciado
const LATIDO_MS = 4000;          // durante una espera larga, la pantalla en off sigue avisando que está abierta
const PRIMERA_ESCENA_MS = 10000; // al aceptar un recorrido se espera a que la primera escena esté a la vista (o esto)
const VIGENCIA_RECORRIDO_S = 90; // la pantalla en off narra un recorrido nuevo; uno viejo se aplica en silencio
const REANUDAR_S = 20;           // y reanuda uno a medias si su último avance es de hace menos que esto
// La presentación automática (la pantalla en off): cuánto se espera antes de pedirle al servidor el plan siguiente
export const ESPERA_AUTO_MS = 1500;          // desde que terminó un plan automático (el del capítulo siguiente)
export const ESPERA_TRAS_PLAN_MS = 5000;     // desde que terminó un plan del asistente (la pregunta que la interrumpió)
export const ESPERA_TRAS_ORDEN_MS = 45000;   // desde otra orden suelta: lo que se pidió ver se queda un rato a la vista
export const REINTENTO_AUTO_MS = 5000;       // el servidor no tenía nada que armar (204) o no respondió: se vuelve a pedir
const CLAVE_PRESENTADOR = 'yj_presentador';   // el botón «Presentador»: '0' oculto
const QUIETO_MS = 3000;          // el botón flotante del asistente se atenúa tras esto sin mover el ratón ni tocar
const PEDIR_PANTALLA = 'pantalla:pedir';   // el puente (`pedirPantalla`): la pantalla en off pregunta ya
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
 * de app/recorrido.py). De lo último aplicado solo quedan el tema y la pantalla completa, que la escena no cambia. Lo
 * visual es el de la escena y nada más: la parte que no trae (una escena de antes del plan guiado) es lo del paso
 * (`ordenesHacia` da por inicial lo que falta), no lo que hubiera antes. Su movimiento y su animación ya pasaron. */
function baseDeEscena(antes, esc) {
  const { tema = null, completa, orden_completa } = antes || {};
  return { tema, completa, orden_completa, capitulo: esc.capitulo, paso: esc.paso, explicacion: null, panel: esc.panel,
    indice: false, fichas: false, ...esc.visual, mover: null, animar: false };
}

// Los planes que esta página ya reprodujo (los últimos): su id y su contenido. «Volver a reproducir» llega del servidor
// con un id nuevo y el mismo contenido, y «Reanudar» con el mismo id: ninguno es un plan nuevo
const reproducidos = [];
/** ¿Es `r` un plan que esta página todavía no reprodujo? Queda anotado. */
function esNuevo(r) {
  const huella = JSON.stringify([r.titulo, r.escenas, r.cierre]);
  const visto = reproducidos.some((x) => x.id === r.id || x.huella === huella);
  if (!visto) { reproducidos.push({ id: r.id, huella }); while (reproducidos.length > 6) reproducidos.shift(); }
  return !visto;
}

const dormir = (ms) => new Promise((ok) => { setTimeout(ok, ms); });

const relojDelNavegador = {
  ahora: () => (globalThis.performance?.now ? performance.now() : Date.now()),
  programar: (f, ms) => setTimeout(f, ms),
  cancelar: (h) => clearTimeout(h),
};

/**
 * El reloj de la presentación automática: decide cuándo la pantalla en off le pide al servidor el plan siguiente.
 * pedir() → Promise<boolean>: POST /api/pantalla/auto/siguiente; true si el servidor armó un plan (llega por el sondeo).
 * ocupado() → ¿el reproductor tiene un plan? (sonando o en pausa: mientras tanto no se pide nada).
 * alArmar(): el servidor acaba de armar uno (la vista adelanta su sondeo para recibirlo ya).
 * Solo pide con la automática encendida y el reproductor sin plan, una petición a la vez: enseguida al encenderla; a los
 * ESPERA_AUTO_MS de terminar un plan automático; a los ESPERA_TRAS_PLAN_MS de terminar uno del asistente (o uno
 * automático que no llegó a su final: se cortó o falló); a los ESPERA_TRAS_ORDEN_MS de otra orden suelta. Manda lo último
 * que pasó. Si el servidor no arma nada (204), falla, o el plan que armó no llega, vuelve a pedir a los REINTENTO_AUTO_MS.
 * Sin DOM: el reloj llega por parámetro (admin/tests/test_automatica_panel.py lo prueba con uno de mentira).
 */
export function crearAutomatica({ pedir, ocupado, alArmar = () => {}, reloj = relojDelNavegador }) {
  let activa = false, pidiendo = false, suelta = false;
  let noAntes = 0;   // el siguiente no se pide antes de este momento
  let cita = null;   // el reloj pendiente
  const programar = () => {
    if (cita !== null) { reloj.cancelar(cita); cita = null; }
    if (!activa || pidiendo || suelta) return;
    cita = reloj.programar(tocar, Math.max(0, noAntes - reloj.ahora()));
  };
  const esperar = (ms) => { noAntes = reloj.ahora() + ms; programar(); };
  async function tocar() {
    cita = null;
    if (!activa || pidiendo || suelta) return;
    if (reloj.ahora() < noAntes) { programar(); return; }
    // con un plan en el reproductor no se pide: cuando termine, `alTerminar` pone la espera que toca (y por si ese aviso
    // no llegara, se vuelve a mirar)
    if (ocupado()) { esperar(REINTENTO_AUTO_MS); return; }
    pidiendo = true;
    let armo = false;
    try { armo = (await pedir()) === true; } catch { armo = false; }
    pidiendo = false;
    // lo que pasó mientras tanto (una orden suelta, un plan que terminó) ya dejó su espera: vale la más larga
    noAntes = Math.max(noAntes, reloj.ahora() + REINTENTO_AUTO_MS);
    programar();
    if (armo && activa && !suelta) { try { alArmar(); } catch { /* nada */ } }
  }
  return {
    /** Lo que dice el servidor (o el botón): encendida o apagada. Al encenderla pide enseguida. */
    fijar(v) {
      if ((v === true) === activa) return;
      activa = v === true;
      if (activa) esperar(0); else programar();
    },
    /** Terminó un plan en esta pantalla: `auto`, si era el de la automática; `fase`, cómo terminó (TERMINALES). */
    alTerminar({ auto = false, fase = 'fin' } = {}) { esperar(auto && fase === 'fin' ? ESPERA_AUTO_MS : ESPERA_TRAS_PLAN_MS); },
    /** Llegó otra orden suelta (algo concreto que no es un plan). */
    alOrden() { esperar(ESPERA_TRAS_ORDEN_MS); },
    activa: () => activa,
    /** {activa, pidiendo, en_ms}: `en_ms` es lo que falta para la próxima petición (null si no hay ninguna prevista). */
    estado: () => ({ activa, pidiendo, en_ms: cita === null ? null : Math.max(0, Math.round(noAntes - reloj.ahora())) }),
    soltar() { suelta = true; programar(); },
  };
}

/** Lo que responde POST /api/pantalla/auto ({activa, capitulo, nombre, paso, de}), solo con la forma esperada, o null.
 * `nombre` y `de` (el nombre del capítulo y cuántos pasos tiene) son para la barra: si no vienen bien, quedan en null. */
function autoRespondida(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || typeof a.activa !== 'boolean') return null;
  if (typeof a.capitulo !== 'string' || !/^[a-z_]{2,40}$/.test(a.capitulo) || !Number.isSafeInteger(a.paso) || a.paso < 1) return null;
  const nombre = typeof a.nombre === 'string' ? a.nombre.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 80) : '';
  return { activa: a.activa, capitulo: a.capitulo, paso: a.paso, nombre: nombre || null,
    de: Number.isInteger(a.de) && a.de >= a.paso && a.de <= 60 ? a.de : null };
}

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
          <span class="chip borde pres-off-chip" title="La manejan el asistente del panel y los agentes por MCP">${icono('agente')}<span id="pres-off-estado">Esperando al asistente</span></span>
          <button type="button" class="btn pres-auto" id="pres-auto" aria-pressed="false" aria-label="Presentación automática" title="Recorre sola toda la presentación, muy resumida. Una pregunta al asistente la interrumpe y, al terminar la respuesta, sigue donde iba" disabled>${icono('animar')}<span>Presentación automática</span></button>
          <button type="button" class="btn pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta pantalla (la del navegador)">${icono('voz')}<span>Voz</span></button>
          <button type="button" class="btn pres-presentador" aria-pressed="true" title="El presentador: la caricatura que explica lo que narra el asistente (se oculta y se vuelve a mostrar en esta pantalla)">${icono('presentador')}<span>Presentador</span></button>
          <a class="btn" id="pres-salir-off" href="${url('/presentacion')}">${icono('cerrar')}<span>Salir del modo en off</span></a>
        </div>
      </div>
      <p class="pres-remoto pres-off-aviso" role="note">${icono('agente')}<span>Esta pantalla no tiene controles: solo cambia cuando le pide algo concreto al asistente del panel (con su botón, aquí al lado, o desde otro equipo o el celular) o a un agente por MCP. Con «Presentación automática» recorre sola toda la presentación, muy resumida; una pregunta al asistente la interrumpe y después sigue. Pídale «pantalla completa» para que llene la ventana; Escape la devuelve aquí.</span></p>` : ''}
      <div class="pres-barra" role="toolbar" aria-label="Presentación"${off ? ' hidden' : ''}>
        <div class="pres-donde"><b id="pres-capitulo">Presentación de la propuesta</b><small id="pres-paso">Cargando la presentación…</small></div>
        <div class="pres-botones">
          <button type="button" class="btn" id="pres-anterior" aria-label="Paso anterior" title="Paso anterior" disabled>${icono('anterior')}</button>
          <button type="button" class="btn primario" id="pres-siguiente" aria-label="Paso siguiente" title="Paso siguiente" disabled><span>Siguiente</span>${icono('siguiente')}</button>
          ${off ? '' : html`<button type="button" class="btn pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta pestaña (la del navegador)">${icono('voz')}<span>Voz</span></button>
          <button type="button" class="btn pres-presentador" aria-pressed="true" title="El presentador: la caricatura que explica lo que narra el asistente (se oculta y se vuelve a mostrar en esta pestaña)">${icono('presentador')}<span>Presentador</span></button>`}
          ${conPantalla ? html`<button type="button" class="btn" id="pres-pantalla" aria-label="Pantalla completa" title="Pantalla completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
          <a class="btn" id="pres-otra" href="${url('/presentacion?pantalla=1')}" target="_blank" rel="noopener" aria-label="Abrir en otra pantalla (proyector)" title="Abre la presentación en otra ventana para el proyector: el asistente la sigue manejando desde aquí, y en esa ventana también se abre el asistente, al lado de la presentación">${icono('proyector')}<span>Abrir en otra pantalla</span></a>
          <a class="btn" id="pres-off" href="${url('/presentacion?off=1')}" target="_blank" rel="noopener" aria-label="Pantalla en off" title="Una pantalla sin controles para el proyector o un televisor, en este equipo o en otro: solo cambia cuando se le pide al asistente o a un agente por MCP. En esa ventana también se abre el asistente, al lado de la presentación">${icono('agente')}<span>Pantalla en off</span></a>
        </div>
      </div>
      <p class="pres-remoto" id="pres-remoto" role="status" hidden>${icono('proyector')}<span>La presentación se está mostrando en otra pantalla: el asistente, estos botones y la presentación de aquí la manejan allá.</span></p>
      <div class="pres-marco" id="pres-marco"></div>
      ${proyector ? html`<div class="pres-flotantes">
        ${conPantalla ? html`<button type="button" class="btn oscuro pres-completa" id="pres-completa" title="Pantalla completa">${icono('pantalla')}<span>Pantalla completa</span></button>` : ''}
        <button type="button" class="btn oscuro pres-voz" aria-pressed="false" title="La voz del recorrido narrado en esta ventana (la del navegador)">${icono('voz')}<span>Voz</span></button>
        <button type="button" class="btn oscuro pres-presentador" aria-pressed="true" title="El presentador: la caricatura que explica lo que narra el asistente (se oculta y se vuelve a mostrar en esta ventana)">${icono('presentador')}<span>Presentador</span></button>
      </div>` : ''}
    </section>`);
  const marco = $('#pres-marco', el);
  // En off la barra que se ve es la suya (la de los botones queda oculta, sin ids repetidos)
  const capituloEl = $(off ? '#pres-off-capitulo' : '#pres-capitulo', el), pasoEl = $(off ? '#pres-off-paso' : '#pres-paso', el);
  const anterior = $('#pres-anterior', el), siguiente = $('#pres-siguiente', el), remoto = $('#pres-remoto', el);
  const limpiezas = [() => { if (proyector) delete raiz.dataset.proyector; if (off) delete raiz.dataset.presOff; },
    () => { delete raiz.dataset.presLlena; }];
  const limpiar = () => { for (const f of limpiezas.splice(0)) { try { f(); } catch { /* nada */ } } };
  let actividad = () => {};   // el ratón, un toque o una tecla (el proyector y la pantalla en off: el botón flotante)
  let enganchar = () => {};   // y los oyentes de eso sobre la presentación (su ventana, si es del mismo origen)
  let latidoPrevio = 0;       // la pantalla en off avisa que está abierta mientras la presentación carga

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
  // La presentación automática (solo la pantalla en off): lo último que dijo el servidor ({activa, capitulo, paso} o
  // null), el plan suyo que esta pantalla recibió y lo que se sabe de cada capítulo para la barra (su nombre y cuántos
  // pasos tiene: lo dicen la presentación al pasar por él, el título del plan automático y la respuesta del botón)
  let auto = null, ridAuto = null;
  const capitulosVistos = new Map();
  const dondeAuto = (capitulo, paso, { sigue = false, fin = false } = {}) => {
    const c = capitulosVistos.get(capitulo);
    const nombre = c?.nombre || capitulo.replace(/_/g, ' ');
    if (fin) return `Presentación automática · ${nombre} · fin del capítulo`;
    return `Presentación automática · ${sigue ? 'sigue en ' : ''}${nombre} · paso ${paso}${c?.total >= paso ? ` de ${c.total}` : ''}`;
  };

  function sinPresentacion(titulo, detalle) {
    clearInterval(latidoPrevio);   // (sin presentación no hay quien narre aquí: no cuenta como abierta)
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
    capitulosVistos.set(e.capitulo, { nombre: e.nombre || capitulosVistos.get(e.capitulo)?.nombre || null, total: e.total });
    capituloEl.textContent = e.nombre || e.capitulo;
    // con un recorrido sonando (aquí o en el proyector), la barra dice dónde va
    const aqui = rep.estado();
    const alla = !aqui || !rep.activo() ? recorridoEnCurso() : null;
    // (hacia la persona es un «plan» con «pasos»; por dentro, un recorrido con escenas)
    if (rep.activo() && aqui && rep.recorrido().id === ridAuto) {
      // el plan de la presentación automática: el capítulo y el paso de la presentación que se está diciendo (y en su
      // cierre, que no espera preguntas y dura un instante, que el capítulo terminó)
      const esc = rep.recorrido().escenas[aqui.n - 1];
      pasoEl.textContent = `${dondeAuto(esc.capitulo, esc.paso, { fin: aqui.fase === 'cierre' })}${aqui.pausado ? ' · en pausa' : ''}`;
    } else if (rep.activo() && aqui) {
      const donde = aqui.fase === 'cierre' ? 'en resumen' : `paso ${aqui.n} de ${aqui.de}`;
      pasoEl.textContent = `Plan · ${rep.recorrido().titulo} · ${donde}${aqui.pausado ? ' · en pausa' : ''}${auto?.activa ? ' · después sigue la automática' : ''}`;
    } else if (alla?.donde === 'proyector') {
      pasoEl.textContent = `Plan en el proyector · paso ${alla.n} de ${alla.de}${alla.fase === 'pausa' ? ' · en pausa' : ''}`;
    } else if (auto?.activa) {
      // entre un plan y el siguiente (o mientras se ve lo que pidió otra orden): por dónde sigue
      pasoEl.textContent = dondeAuto(auto.capitulo, auto.paso, { sigue: true });
    } else {
      pasoEl.textContent = `Paso ${e.paso} de ${e.total}${e.titulo ? ` · ${e.titulo}` : ''}`;
    }
    const sonando = rep.activo() || alla?.donde === 'proyector';
    for (const [b, que] of [[anterior, 'anterior'], [siguiente, 'siguiente']]) {
      const t = sonando ? `Paso ${que} del plan` : `Paso ${que}`;
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
  // (un Escape que ya usó el asistente abierto al lado, para cerrarse o cancelar la grabación de voz, no la devuelve)
  const alTecla = (e) => { if (e.key === 'Escape' && !e.defaultPrevented && 'presLlena' in raiz.dataset) llenar(false); };
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
  // La vista se va (otra vista del panel, desde el menú): el plan de la presentación automática se suelta aquí
  // sin avisarle el «detenido» al servidor, que lo cerraba y la apagaba para todos (y cortaba otra pantalla en off que la
  // estuviera narrando). Así queda encendida, como al cerrar o recargar la pestaña: la retoma quien siga
  let seFue = false;
  // La boca del presentador (web/js/presentador/, en la presentación): cuándo la voz empieza y termina de decir algo
  // (una frase o el resumen). Sin narración en pantalla la presentación lo ignora
  const boca = (v) => { if (rep.activo()) orden({ orden: 'narracion', habla: v }, { plazo: 3000 }); };
  const vozConBoca = { ...voz, decir: (texto, o = {}) => voz.decir(texto, { ...o, alEmpezar: () => { boca(true); o.alEmpezar?.(); } })
    .then((r) => { boca(false); return r; }) };
  const rep = crearReproductor({
    orden, voz: vozConBoca,
    avisar: (pr) => {
      avisarRecorrido(pr);
      pintarEstado();
      if (!(seFue && pr.rid === ridAuto)) enviarAvance(pr);
      if (TERMINALES.includes(pr.fase)) { try { alTerminarRecorrido?.(pr); } catch { /* nada */ } }
    },
  });
  limpiezas.push(() => { seFue = true; rep.detener('otra_orden'); voz.callar(); });
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
  // El botón «Voz» y el interruptor de la tarjeta del chat (por el puente) hacen lo mismo: la encienden (el clic es el
  // gesto que la deja hablar) o la apagan. Devuelve cómo quedó
  const alternarVoz = () => {
    if (voz.estado() === 'activa') voz.apagar(); else voz.encender();
    return voz.estado();
  };
  for (const b of botonesVoz) b.addEventListener('click', alternarVoz);
  // La pantalla en off no se registra como presentación en el puente: su voz sí, para el interruptor de la tarjeta del
  // chat abierto en esta misma ventana
  if (off) limpiezas.push(registrarVozLocal(alternarVoz));
  // Con una narración en pantalla, la presentación también lo sabe (las barras de la voz, quién lee el subtítulo); sin
  // narración responde un error que no importa
  let hablaba = voz.estado() === 'activa';
  limpiezas.push(voz.alCambiar((e) => {
    pintarVoz();
    const habla = e === 'activa';
    if (habla !== hablaba && rep.activo()) orden({ orden: 'narracion', voz: habla });
    hablaba = habla;
  }));
  pintarVoz();
  // El botón «Presentador»: muestra u oculta la caricatura que explica lo que narra el asistente. La preferencia es de
  // este navegador (`yj_presentador`: '0' oculto; sin guardar, a la vista) y le llega a la presentación como
  // `vista {presentador}` al cambiarla y, si está oculto, cada vez que la presentación carga
  let conPresentador = true;
  try { conPresentador = localStorage.getItem(CLAVE_PRESENTADOR) !== '0'; } catch { conPresentador = true; }
  const botonesPresentador = [...el.querySelectorAll('.pres-presentador')];
  const pintarPresentador = () => { for (const b of botonesPresentador) b.setAttribute('aria-pressed', String(conPresentador)); };
  for (const b of botonesPresentador) {
    b.addEventListener('click', () => {
      conPresentador = !conPresentador;
      try { localStorage.setItem(CLAVE_PRESENTADOR, conPresentador ? '1' : '0'); } catch { /* dura lo que la página */ }
      pintarPresentador();
      if (lista) orden({ orden: 'vista', presentador: conPresentador });
    });
  }
  pintarPresentador();

  // `enPausa`: la pantalla en off que se recargó con el recorrido en pausa lo retoma en su escena y en pausa. La pausa
  // entra cuando la escena ya está a la vista (antes, el cambio de imagen la taparía con «preparando»). `previa`: un
  // plan nuevo desde el primer paso espera PREVIA_MS antes de empezar (el chat lo muestra entero)
  async function aplicarRecorrido(p, { enPausa = false, previa = false } = {}) {
    const primera = rep.iniciar(p.recorrido, { desde: p.desde || 1, ...(previa ? { previa: PREVIA_MS } : {}) });
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
      if (p.op === 'recorrido') {
        // un plan nuevo llega sin `desde`; el que se traspasa de otra ventana lo trae siempre, y el que se reanuda o se
        // vuelve a reproducir ya pasó por aquí
        const nuevo = esNuevo(p.recorrido);
        res.push(await aplicarRecorrido(p, { previa: nuevo && p.desde === undefined }));
        continue;
      }
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
  // La pantalla en off cuenta como abierta para el servidor desde que se monta, no desde que la presentación termina de
  // cargar (entonces empieza a seguirlo): el chat de esta misma ventana se usa antes, y un plan pedido en ese hueco
  // salía para la pestaña (`destino: vista`), que aquí no narraba nadie. Avisa cada LATIDO_MS hasta que el sondeo toma
  // la posta (o hasta saber que no hay presentación); la respuesta no se usa (`latido`: no es lo que la vista aplicó)
  if (off) {
    const latir = () => { api.get('/api/pantalla?v=-1&latido=1').catch(() => {}); };
    latir();
    latidoPrevio = setInterval(latir, LATIDO_MS);
    limpiezas.push(() => clearInterval(latidoPrevio));
  }
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
    enganchar();   // (su documento ya existe: su `listo` llega antes que el `load` del iframe)
    const m = e.data;
    if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
    // Un toque o una tecla de la persona sobre la presentación: enciende la voz que ya estaba elegida (en el proyector es
    // el único gesto que hay: el iframe ocupa la ventana). La activación del usuario dentro del iframe vale también aquí
    if (m.tipo === 'gesto') { voz.gesto(); actividad(); return; }
    // La presentación sin controles (la pantalla en off) no atiende el teclado: Escape devuelve aquí la ventana. Con un
    // recorrido sonando, las teclas y los botones de la presentación lo manejan. Las que no son Escape también son un
    // gesto (Escape no le da al navegador la activación del usuario: con él la voz no podría hablar)
    if (m.tipo === 'tecla') {
      actividad();
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
    if (m.tipo === 'listo' && !conPresentador) orden({ orden: 'vista', presentador: false });
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
          alternarVoz,   // el interruptor de voz de la tarjeta del chat (`alternarVozRecorrido` del puente)
          ...(proyector ? { proyector: true } : {}) });
        // las flechas del teclado van a la presentación (salvo que la persona ya esté en el chat de esta ventana: lo que
        // sigue escribiendo iría a la presentación, delante de la sala)
        if (proyector && !document.activeElement?.closest?.('#agente-panel')) iframe.focus({ preventScroll: true });
      }
    }
    if (nuevo && !off) avisarEstado();
  }
  // La pantalla en off: pregunta cada POLL_MS por la versión del servidor y aplica solo lo que cambió, en orden (una
  // pregunta a la vez). Lo que tarda la presentación (el telón de un capítulo) no se pisa: la siguiente pregunta sale
  // cuando termina la anterior
  let tPoll = 0, versionVista = -1, aplicado = null, siguiendo = false;
  let adelantarSondeo = null;   // la automática acaba de armar un plan: la próxima pregunta al servidor sale ya
  const offEstado = $('#pres-off-estado', el);
  // El recorrido en la pantalla en off: el que vio por última vez (id) y el último control que aplicó (n)
  let ridOff = null, controlOff = 0;
  // La presentación automática: su reloj (cuándo se le pide al servidor el plan siguiente) y su botón
  const automatica = off ? crearAutomatica({
    pedir: async () => { const r = await api.post('/api/pantalla/auto/siguiente'); return !!r && typeof r === 'object'; },
    ocupado: () => rep.activo(),
    alArmar: () => adelantarSondeo?.(),
  }) : null;
  limpiezas.push(() => automatica?.soltar());
  const botonAuto = $('#pres-auto', el);
  // Lo que dice la barra de la conexión; `avisoAuto`, lo que no se pudo con el botón (se ve unos segundos). Con la
  // automática encendida, corto: que está encendida lo dicen el botón y el paso, que necesita el ancho
  let conexion = null, avisoAuto = null, tAvisoAuto = 0;
  function pintarAuto() {
    const activa = !!auto?.activa;
    if (botonAuto) botonAuto.setAttribute('aria-pressed', String(activa));
    if (off) $('.presentacion', el)?.toggleAttribute('data-auto', activa);   // (css: el paso se lleva más ancho de la barra)
    if (offEstado && (conexion || avisoAuto)) {
      offEstado.textContent = avisoAuto || (conexion !== 'ok' ? conexion
        : activa ? 'Conectada' : 'Conectada: asistente y agentes por MCP');
    }
    pintarEstado();
  }
  /** La automática como la dice el servidor (en el estado de la pantalla o al responder el botón). */
  function alAuto(a) {
    auto = a;
    automatica?.fijar(!!a?.activa);
    pintarAuto();
  }
  if (off) {
    alTerminarRecorrido = (pr) => {
      const r = rep.recorrido();
      if (r && pr.rid === r.id) aplicado = baseDeEscena(aplicado, r.escenas[pr.n - 1]);
      // la automática sigue sola: el del capítulo siguiente, o donde iba si lo que terminó fue un plan del asistente
      automatica.alTerminar({ auto: pr.rid === ridAuto, fase: pr.fase });
    };
    let cambiandoAuto = false;
    botonAuto.addEventListener('click', async () => {
      voz.gesto();   // el clic es además el gesto que deja hablar a la voz en esta ventana
      if (cambiandoAuto) return;
      cambiandoAuto = true;
      botonAuto.setAttribute('aria-busy', 'true');
      const encender = !auto?.activa;
      clearTimeout(tAvisoAuto);
      avisoAuto = null;
      try {
        const r = await api.post('/api/pantalla/auto', { accion: encender ? 'iniciar' : 'detener' });
        const a = autoRespondida(r?.auto);
        if (a?.nombre) capitulosVistos.set(a.capitulo, { nombre: a.nombre, total: a.de ?? capitulosVistos.get(a.capitulo)?.total ?? null });
        // (sin la forma esperada, vale lo pedido: el estado de la pantalla trae enseguida lo que quedó)
        alAuto(a ? { activa: a.activa, capitulo: a.capitulo, paso: a.paso } : auto && { ...auto, activa: encender });
        // al apagarla, su plan se calla ya (el servidor lo cerró; si no, seguiría hasta la próxima pregunta al servidor)
        if (!auto?.activa && rep.activo() && rep.recorrido()?.id === ridAuto) rep.detener('otra_orden').catch(() => {});
        adelantarSondeo?.();   // al encenderla el servidor ya armó el primer plan: que llegue ya
      } catch (err) {
        avisoAuto = err instanceof ErrorApi && err.estado === 0 ? 'Sin conexión: no se pudo cambiar la presentación automática'
          : err instanceof ErrorApi && err.estado === 404 ? 'Este servidor no tiene la presentación automática'
            : `No se pudo ${encender ? 'encender' : 'apagar'} la presentación automática`;
        tAvisoAuto = setTimeout(() => { avisoAuto = null; pintarAuto(); }, 6000);
        pintarAuto();
      }
      botonAuto.removeAttribute('aria-busy');
      cambiandoAuto = false;
    });
    limpiezas.push(() => clearTimeout(tAvisoAuto));
  }
  // Un recorrido que esta pantalla ve por primera vez (se abrió o se recargó con él en el servidor). Si ya tuvo avance,
  // decide el avance: uno terminado no se vuelve a narrar; uno en pausa se retoma en su escena y en pausa (en pausa no
  // hay avances y su antigüedad no dice nada: antes se lo daba por viejo, la pantalla saltaba a la última escena y no
  // atendía el «continuar»); uno a medias con un avance reciente (la pantalla se recargó) sigue en su escena, y uno sin
  // noticias hace rato (la pantalla se cerró) no se narra. Sin avance, se narra si es nuevo: una pantalla que se abre
  // después no narra uno viejo. El que no se narra se queda en la escena de su último avance (`enSuEscena`).
  // Con la presentación automática encendida la pantalla no deja callado un plan que el servidor da por sonando (si no,
  // no armaría el siguiente y la automática se quedaría parada hasta que lo diera por perdido): el suyo (`auto`) se
  // retoma siempre, desde su último avance o desde el comienzo, por viejo que sea; el del asistente, si su último avance
  // es de hace menos de VIGENCIA_RECORRIDO_S (lo mismo que espera el servidor, `plan_sonando`; uno más viejo no se
  // narra: la automática sigue). El plan de la automática no espera la previa
  async function recorridoDeLaPantalla(e) {
    const x = e.recorrido;
    if (x && x.id !== ridOff) {
      ridOff = x.id;
      controlOff = e.control_recorrido?.n || 0;
      const esAuto = x.auto === true;
      if (esAuto) {
        ridAuto = x.id;
        // su título es el nombre del capítulo
        const c = x.escenas[0].capitulo;
        capitulosVistos.set(c, { nombre: x.titulo, total: capitulosVistos.get(c)?.total ?? null });
      }
      const pr = e.progreso;   // del mismo recorrido: `estadoDePantalla` descarta el de otro
      const sigue = !!auto?.activa;
      const reanudar = !sigue ? REANUDAR_S : esAuto ? Infinity : VIGENCIA_RECORRIDO_S;
      let desde = 0;
      if (pr) desde = !TERMINALES.includes(pr.fase) && (pr.fase === 'pausa' || pr.hace_s < reanudar) ? pr.n : 0;
      else if (x.edad_s < VIGENCIA_RECORRIDO_S || (sigue && esAuto)) desde = 1;
      if (desde) {
        // `auto` llega al reproductor: con ella el plan de la automática no espera el «¿Preguntas?» del final (sin ella
        // esperaba 12 s en cada capítulo). `esNuevo` no la mira, y en esta pantalla el plan no pasa por el puente
        const { edad_s: _edad, ...r } = x;
        // el que esta pantalla retoma (ya tuvo avance) o ya reprodujo no espera; el que le llega nuevo, sí (el de la
        // automática, nunca: nadie lo está leyendo en el chat)
        const nuevo = esNuevo(r);
        await aplicarRecorrido({ op: 'recorrido', recorrido: r, desde }, { enPausa: pr?.fase === 'pausa', previa: nuevo && !pr && !esAuto });
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
    if (botonAuto) botonAuto.disabled = false;
    let enVuelta = false, pronto = false;
    const vuelta = async () => {
      if (!iframe.isConnected) return;
      enVuelta = true;
      let espera = POLL_MS;
      try {
        const r = await api.get(`/api/pantalla?v=${versionVista}`);
        const e = estadoDePantalla(r);
        if (e) {
          // antes que el plan: `recorridoDeLaPantalla` mira si la automática está encendida
          alAuto(e.auto);
          // Las esperas largas (la primera escena, hasta PRIMERA_ESCENA_MS; cada orden, hasta ESPERA_ORDEN_MS) no dejan de
          // avisar que la pantalla sigue abierta: si no, el servidor la daba por cerrada (VIVA_S) y un recorrido que el
          // asistente armaba en ese hueco salía para la pestaña. La respuesta no se usa: la próxima vuelta vuelve a leer
          const latido = setInterval(() => { api.get(`/api/pantalla?v=${versionVista}&latido=1`).catch(() => {}); }, LATIDO_MS);
          let meta;
          try {
            await recorridoDeLaPantalla(e);
            // mientras suena un recorrido, lo que se ve lo pone él (solo la pantalla completa se aplica igual)
            meta = rep.activo() ? null : enSuEscena(e);
            const ordenes = meta ? ordenesHacia(aplicado, meta) : [];
            // Otra orden suelta (algo concreto que no es un plan cambió lo que se ve; no al abrir, que es ponerse al día):
            // la automática le deja su rato a la vista antes de seguir
            if (ordenes.length && aplicado) automatica.alOrden();
            for (const o of ordenes) {
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
        conexion = 'ok';
      } catch (err) {
        espera = POLL_ERROR_MS;
        conexion = err instanceof ErrorApi && err.estado === 0 ? 'Sin conexión: reintentando…' : 'No se pudo leer la pantalla: reintentando…';
      }
      pintarAuto();
      enVuelta = false;
      if (iframe.isConnected) tPoll = setTimeout(vuelta, pronto ? 0 : espera);
      pronto = false;
    };
    // (una pregunta a la vez: con una en curso, que pudo salir antes de lo nuevo, la que le sigue sale sin esperar)
    adelantarSondeo = () => {
      if (enVuelta) pronto = true;
      else if (iframe.isConnected) { clearTimeout(tPoll); vuelta(); }
    };
    clearInterval(latidoPrevio);   // desde aquí avisa el sondeo (y sus latidos en las esperas largas)
    vuelta();
  }
  limpiezas.push(() => clearTimeout(tPoll));
  // El chat abierto en esta misma ventana acaba de cambiar algo en el servidor (un plan, un control: `pedirPantalla` del
  // puente): se pregunta ya, sin esperar POLL_MS (una pregunta a la vez; antes de empezar a seguirlo, nada)
  if (off) {
    const alPedir = () => { adelantarSondeo?.(); };
    window.addEventListener(PEDIR_PANTALLA, alPedir);
    limpiezas.push(() => window.removeEventListener(PEDIR_PANTALLA, alPedir));
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
  // Con un recorrido sonando (aquí o en el proyector), los botones pasan de escena
  const mover = (op) => {
    if (rep.activo()) { if (op === 'siguiente') rep.siguiente(); else rep.anterior(); return; }
    const alla = recorridoEnCurso();
    if (alla?.donde === 'proyector') { controlRecorrido(alla.rid, op).catch(() => {}); return; }
    accionesPresentacion([{ tipo: 'presentacion', op }]).catch(() => {});
  };
  anterior.addEventListener('click', () => mover('anterior'));
  siguiente.addEventListener('click', () => mover('siguiente'));
  // En el proyector el teclado (y el control remoto: AvPág y RePág) es de la presentación, que ocupa la ventana. El
  // asistente, al cerrarse, le devuelve el foco (agente.js); pero con el foco fuera de ella (un clic en el botón del
  // asistente o en la ventana) las flechas no le llegaban y la barra espaciadora volvía a abrir el chat delante de la
  // sala: esas teclas la mueven igual (con un plan sonando, de paso del plan, como las suyas) y el foco vuelve a ella.
  // Lo que se escribe en el chat o en un campo no se toca, ni el espacio sobre los otros botones de la ventana («Voz»,
  // «Pantalla completa»), que los pulsa
  if (proyector) {
    const TECLA_FUERA = { ArrowRight: 'siguiente', PageDown: 'siguiente', ' ': 'siguiente', ArrowLeft: 'anterior',
      PageUp: 'anterior', Backspace: 'anterior' };
    const alTeclaFuera = (e) => {
      const op = TECLA_FUERA[e.key];
      if (!op || !lista || e.defaultPrevented || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;
      const t = e.target;
      if (t?.closest?.('#agente-panel, input, textarea, select, [contenteditable], dialog')) return;
      if (e.key === ' ' && t?.closest?.('button:not(#agente-boton), a')) return;
      e.preventDefault();
      iframe.focus({ preventScroll: true });
      mover(op);
    };
    document.addEventListener('keydown', alTeclaFuera);
    limpiezas.push(() => document.removeEventListener('keydown', alTeclaFuera));
  }
  // En el proyector, la ventana entera (es lo mismo: no tiene menú ni barra), así el asistente sigue a mano en pantalla
  // completa; con solo el marco, quedaba fuera. En la pestaña, el marco: el menú y la barra no van
  const pantalla = () => {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    else (proyector ? document.documentElement : marco).requestFullscreen?.().catch(() => {});
  };
  $('#pres-pantalla', el)?.addEventListener('click', pantalla);
  const completa = $('#pres-completa', el);
  if (completa) {
    completa.addEventListener('click', pantalla);
    const alCambiar = () => { completa.hidden = !!document.fullscreenElement; };
    document.addEventListener('fullscreenchange', alCambiar);
    limpiezas.push(() => document.removeEventListener('fullscreenchange', alCambiar));
  }

  // El botón del asistente flotando sobre la presentación (el proyector; la pantalla en off a pantalla completa): tras
  // QUIETO_MS sin mover el ratón ni tocar se atenúa (css/presentacion.css: html[data-pres-quieto]) para no distraer a
  // la sala, y vuelve al mover el ratón, tocar o con una tecla, también sobre la presentación: su `gesto` y su `tecla` y,
  // si es del mismo origen, su ratón (en el proyector el iframe ocupa la ventana y lo que pasa sobre él no llega aquí;
  // de otro origen, el botón vuelve igual al pasarle el ratón por encima: css)
  if (proyector || off) {
    let ultima = 0, tQuieto = 0, ventanaIframe = null, docIframe = null;
    const mirarQuieto = () => {
      const falta = ultima + QUIETO_MS - Date.now();
      if (falta > 0) { tQuieto = setTimeout(mirarQuieto, falta); return; }
      tQuieto = 0;
      raiz.dataset.presQuieto = '';
    };
    actividad = () => {
      ultima = Date.now();
      if ('presQuieto' in raiz.dataset) delete raiz.dataset.presQuieto;
      if (!tQuieto) tQuieto = setTimeout(mirarQuieto, QUIETO_MS);
    };
    // El ratón cuenta si se movió de verdad: el navegador repite el último movimiento cuando cambia lo que hay debajo
    // del ratón quieto (los rótulos de la maqueta se mueven con la cámara), y eso no es la persona
    let ratonX = null, ratonY = null;
    const alRaton = (e) => {
      if (e.screenX === ratonX && e.screenY === ratonY) return;
      ratonX = e.screenX;
      ratonY = e.screenY;
      actividad();
    };
    const tipos = [['pointermove', alRaton], ['pointerdown', () => actividad()], ['keydown', () => actividad()], ['wheel', () => actividad()]];
    const opciones = { capture: true, passive: true };
    const escuchar = (w, si) => {
      if (!w) return;
      for (const [t, f] of tipos) {
        try { if (si) w.addEventListener(t, f, opciones); else w.removeEventListener(t, f, opciones); } catch { return; }   // de otro origen
      }
    };
    // Sobre cada documento de la presentación, una vez: al llegar su primer mensaje (`listo` sale antes que el `load`
    // del iframe, que espera la maqueta y las imágenes) y en cada `load` (se recargó). De otro origen no hay documento
    enganchar = () => {
      let doc = null;
      try { doc = iframe.contentDocument; } catch { doc = null; }
      if (!doc || doc === docIframe) return;
      docIframe = doc;
      try { ventanaIframe = iframe.contentWindow; } catch { ventanaIframe = null; }
      escuchar(ventanaIframe, true);
    };
    const alCargar = () => enganchar();
    escuchar(window, true);
    iframe.addEventListener('load', alCargar);
    actividad();
    limpiezas.push(() => {
      escuchar(window, false);
      escuchar(ventanaIframe, false);
      iframe.removeEventListener('load', alCargar);
      clearTimeout(tQuieto);
      actividad = () => {};
      enganchar = () => {};
      delete raiz.dataset.presQuieto;
    });
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
