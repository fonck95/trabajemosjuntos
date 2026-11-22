// La tarjeta del plan guiado en el chat del asistente (agente.js) y la barra fija que lo sigue mientras suena. Hacia la
// persona es un «plan» con «pasos»; por dentro siguen el recorrido y sus escenas (la acción `recorrido`, el reproductor).
//
// La acción `recorrido` del servidor trae el plan entero y la tarjeta lo muestra ANTES de que empiece («Plan listo:
// empieza enseguida»): el título, cuántos pasos, la duración estimada, dónde suena y los pasos numerados (dónde está
// cada uno, lo que hace mientras se dice y su frase), el cierre y las sugerencias para seguir. Después lo sigue paso a
// paso: el paso en curso va marcado y abierto, con la frase que suena resaltada; los hechos, con su marca. Los demás
// van resumidos en un renglón («Ver todo» los abre). La lista de pasos tiene su propio desplazamiento y va sola al
// paso en curso mientras la persona no la haya movido para leer otra parte; el desplazamiento del chat no se toca.
// El avance llega en vivo:
// * si suena en esta pestaña o en el proyector, del puente (`escucharRecorrido`: el reproductor de la vista o el canal
//   del proyector);
// * si suena en la pantalla en off, de GET /api/pantalla/recorrido cada SONDEO_MS mientras no termine; y si esa pantalla
//   en off es ESTA ventana (el asistente abierto al lado de la presentación), además del puente, en el acto
//   (`escucharRecorrido`, desde 'aqui'): mientras lleguen esos avances, mandan ellos (el sondeo trae lo mismo con
//   retraso) y la tarjeta no lo da por «sin respuesta». Una
//   pantalla que deja de dar noticias sin estar en pausa (se apagó, perdió la red) lo deja «detenido» por falta de
//   respuesta: si no, la tarjeta y la barra quedaban sonando para siempre y cada mensaje mandaba una pausa que nadie
//   aplicaba. En pausa no hay avances: la tarjeta mira si la pantalla sigue abierta (`conectada`) y, si se cerró, también
//   lo da por detenido. Una pausa larga se sigue preguntando, más despacio (SONDEO_LENTO_MS), así se ve el «continuar»
//   que mande el asistente.
// Los controles van adonde suena (el puente o POST /api/pantalla/recorrido/control, en orden y con `keepalive`; después
// `pedirPantalla()` del puente, para que la pantalla en off de esta ventana, si la hay, lo aplique sin esperar su
// sondeo). El interruptor de voz dice cómo está la voz donde suena (`voz` del avance) y la enciende o la apaga si suena
// en esta pestaña o en la pantalla en off de esta ventana (`alternarVozRecorrido` del puente: el clic es el gesto que el
// navegador pide); si suena en otra ventana, dice dónde se enciende. Al terminar
// ofrece volver a reproducirlo y las sugerencias como botones (al tocar una, se envía como mensaje de la persona).
// Volver a reproducirlo pasa siempre por el servidor, que lo vuelve a armar con un id nuevo (también uno que otra orden
// cerró): así el asistente lo ve y lo controla, y su avance no rebota. Si el asistente armó otro después, ya no se
// puede (409).
//
// Seguridad: todo se valida con la forma exacta y se pinta con textContent (nada del modelo entra como HTML). La
// tarjeta no es aria-live: solo cambia aria-current del paso en curso.
import { ErrorApi, api } from './api.js';
import * as puente from './agente-presentacion.js';
import { MAX_CIERRE, MAX_ESCENAS, MAX_EXPLICACION, MAX_FRASES, MAX_PUNTO, MAX_TITULO, TERMINALES, VOCES, controlRecorrido,
  escucharRecorrido, proyectorVivo, recorridoEnCurso } from './agente-presentacion.js';

const SONDEO_MS = 1500;
const SONDEO_MAX_MS = 15 * 60 * 1000;   // sin ningún cambio en esto: sonando, lo da por detenido; en pausa, pregunta
const SONDEO_LENTO_MS = 10000;          // más despacio (cada SONDEO_LENTO_MS)
const VOLVER_ESPERA_MS = 20000;         // lo que «Volver a reproducir» espera el primer avance del id nuevo antes de
                                        // ofrecerse otra vez (la vista no llegó a reproducirlo)
const SIN_NOTICIAS_S = 60;              // sonando y sin un avance en esto, la pantalla en off dejó de responder (la
                                        // espera más larga sin avisar es el cierre: el resumen, lo que se sostiene y
                                        // «¿Preguntas?», unos 35 s)
const SIN_EMPEZAR_MS = 90000;           // y sin ningún avance en esto, no lo va a narrar (`VIGENCIA_RECORRIDO_S` de la vista)
const NOTA_PROPIA_MS = 7000;            // lo que dura una nota que pidió la persona (dónde se enciende la voz) aunque
                                        // llegue otro avance
const ORDEN_PROPIA_MS = 5000;           // lo que vale una pausa o un «continuar» propio que el avance todavía no refleja
                                        // (la pantalla en off lo aplica en su próximo sondeo, y avisa después)
const RID = /^[0-9a-f]{12}$/;
// Lo que hace cada paso (`HACE` de la herramienta): el nombre y el ícono de ui.js. `simular`: el paso acciona los
// controles de una simulación del modelo del atlas abierto (el sismo, los pisos, el BIM…)
export const HACE = {
  paso: ['Cambia de paso', 'siguiente'], camara: ['Mueve la cámara', 'gps'], enfoque: ['Enfoca una obra', 'buscar'],
  ficha: ['Abre una ficha', 'info'], hoy: ['Muestra hoy', 'reloj'], proyecto: ['Muestra el proyecto', 'presentacion'],
  modelo: ['Abre un modelo del atlas', 'zona'], resaltar: ['Resalta', 'pin'], solo3d: ['Solo 3D', 'pantalla'],
  girar: ['Gira', 'repetir'], capas: ['Muestra u oculta piezas', 'capas'], aislar: ['Aísla una obra', 'aislar'],
  partes: ['Quita partes', 'partes'], mover: ['Recorre con la cámara', 'recorrer'], mirar: ['Apunta la cámara', 'mirar'],
  animar: ['Anima la obra', 'animar'], simular: ['Maneja la simulación', 'ajustes'],
  gesto: ['El presentador hace un gesto', 'presentador'],
};
const FASE = { preparando: 'Preparando', narrando: 'Narrando', sosteniendo: 'Mirando', cierre: 'En resumen', pausa: 'En pausa',
  fin: 'Terminó', detenido: 'Detenido', error: 'Detenido por un error', sin_avance: 'Preparando' };
const LISTO = 'Plan listo: empieza enseguida';
const AVISO = { atlas: 'el modelo del atlas no cargó', resaltar: 'no encontró lo que resaltar', asiento: 'la imagen tardó en asentarse',
  voz: 'la voz no pudo hablar', parcial: 'parte de lo pedido no se pudo mostrar' };
const DONDE = { aqui: 'en esta pestaña', proyector: 'en el proyector', pantalla_off: 'en la pantalla en off' };
// El interruptor de voz: lo que dice, su nombre para quien no lo ve (contiene lo que dice) y la ayuda; y, si no se
// maneja desde aquí, dónde sí
const VOZ = {
  activa: { texto: 'Voz', nombre: 'Voz del plan', ayuda: 'La voz del plan está encendida' },
  apagada: { texto: 'Voz', nombre: 'Voz del plan', ayuda: 'La voz del plan está apagada' },
  sin_activar: { texto: 'Activar voz', nombre: 'Activar voz del plan', ayuda: 'La voz del plan espera un toque para sonar' },
  sin_voces: { texto: 'Sin voces', nombre: 'Sin voces en español para el plan', ayuda: 'El navegador donde suena no tiene voces en español' },
};
const VOZ_ALLA = {
  aqui: 'La voz se enciende en la presentación de esta pestaña, con su botón «Voz»: ábrala primero.',
  proyector: 'La voz suena en la ventana del proyector: se enciende o se apaga allá, con su botón «Voz» (abajo a la izquierda).',
  pantalla_off: 'La voz suena en la pantalla en off: se enciende o se apaga allá, con su botón «Voz».',
};

const cadena = (v, max) => typeof v === 'string' && v.trim() && [...v].length <= max && !/[\u0000-\u001f\u007f]/.test(v);

/** La acción `recorrido` con la forma exacta, copiada, o null. `abierto` (solo `true`): el plan en flujo que el panel
 * todavía escribe; la misma acción vuelve, con el mismo id, cada vez que crece (`crecer` de la tarjeta). */
export function tarjetaValida(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || a.tipo !== 'recorrido') return null;
  const claves = ['tipo', 'id', 'titulo', 'destino', 'duracion_ms', 'cierre', 'sugerencias', 'escenas', 'abierto'];
  if (Object.keys(a).some((k) => !claves.includes(k))) return null;
  if (a.abierto !== undefined && a.abierto !== true) return null;
  if (typeof a.id !== 'string' || !RID.test(a.id) || !cadena(a.titulo, MAX_TITULO)) return null;
  if (a.destino !== 'vista' && a.destino !== 'pantalla_off') return null;
  if (!Number.isInteger(a.duracion_ms) || a.duracion_ms < 0 || a.duracion_ms > 600000) return null;
  let cierre = null;
  if (a.cierre != null) {
    if (!Array.isArray(a.cierre) || !a.cierre.length || a.cierre.length > 3 || !a.cierre.every((x) => cadena(x, MAX_PUNTO))) return null;
    if (a.cierre.reduce((s, x) => s + [...x].length, 0) > MAX_CIERRE) return null;
    cierre = [...a.cierre];
  }
  const sug = a.sugerencias ?? [];
  if (!Array.isArray(sug) || sug.length > 3 || !sug.every((x) => cadena(x, 60))) return null;
  if (!Array.isArray(a.escenas) || !a.escenas.length || a.escenas.length > MAX_ESCENAS) return null;
  const escenas = [];
  const maxHace = Object.keys(HACE).length;
  for (const e of a.escenas) {
    if (!e || typeof e !== 'object' || Array.isArray(e) || Object.keys(e).some((k) => !['narracion', 'donde', 'hace'].includes(k))) return null;
    if (!cadena(e.narracion, MAX_EXPLICACION) || !cadena(e.donde, 300)) return null;
    if (!Array.isArray(e.hace) || e.hace.length > maxHace || !e.hace.every((h) => Object.prototype.hasOwnProperty.call(HACE, h))) return null;
    escenas.push({ narracion: e.narracion, donde: e.donde, hace: [...new Set(e.hace)] });
  }
  return { id: a.id, titulo: a.titulo, destino: a.destino, duracion_ms: a.duracion_ms, cierre, sugerencias: [...sug], escenas,
    abierto: a.abierto === true };
}

/** La tarjeta viva del plan `rid` en este chat (la del plan en flujo, que crece), o null. */
export function tarjetaDe(rid) {
  for (const t of tarjetasVivas) if (t.el.isConnected && t.id() === rid) return t;
  return null;
}

export function duracion(ms) {
  const s = Math.max(1, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

// Dónde termina una frase, como `partir_frases` de app/recorrido.py: un punto o un cierre de pregunta o de exclamación,
// un espacio y una mayúscula o un signo de apertura, salvo después de una sigla con puntos («la E.S.E. Hospital…»). Sin
// «lookbehind»: un Safari viejo no cargaría el módulo
const ABRE_FRASE = /[A-ZÁÉÍÓÚÑ¿¡«(]/;
const SIGLA = /(?:^|[^\p{L}\p{N}_])(?:[A-ZÁÉÍÓÚÑ]\.){2,}$|(?:^|[^\p{L}\p{N}_])(?:Res|art|Art|núm|No|Dr|Sr|Sra)\.$/u;

/** La narración de un paso en sus frases (de 1 a MAX_FRASES), partida como la parte el servidor: el avance dice cuál
 * suena por su número. La tarjeta recibe la narración entera; cuando el plan está en este navegador, sus frases ya
 * partidas mandan (`frases` de crearTarjetaRecorrido). */
export function partirFrases(texto) {
  const t = String(texto ?? '').split(/\s+/).filter(Boolean).join(' ');
  const partes = [];
  let desde = 0;
  for (let i = 1; i < t.length - 1; i++) {
    if (t[i] === ' ' && '.!?'.includes(t[i - 1]) && ABRE_FRASE.test(t[i + 1])) {
      partes.push(t.slice(desde, i));
      desde = i + 1;
    }
  }
  partes.push(t.slice(desde));
  const frases = [];
  for (const x of partes) {
    if (frases.length && SIGLA.test(frases[frases.length - 1])) frases[frases.length - 1] += ` ${x}`;
    else frases.push(x);
  }
  return frases.length > MAX_FRASES ? [...frases.slice(0, MAX_FRASES - 1), frases.slice(MAX_FRASES - 1).join(' ')] : frases;
}

// ── La barra fija: sigue a la tarjeta que suena (la más nueva) ──
const tarjetasVivas = new Set();
const oyentesBarra = new Set();
function avisarBarra() {
  const viva = recorridoDelChat();
  for (const f of oyentesBarra) { try { f(viva); } catch { /* nada */ } }
}

/** La tarjeta cuyo recorrido suena: la del que dice el puente que suena (aquí o en el proyector), si está; si no, la más
 * nueva que suena; o null. La del puente primero: después de «Volver a reproducir» uno anterior, la más nueva no es la
 * que suena, y la barra y la pausa al escribir irían a otra. */
export function recorridoDelChat() {
  const rid = recorridoEnCurso()?.rid;
  let viva = null, suya = null;
  for (const t of tarjetasVivas) {
    if (!t.el.isConnected && t.viejo()) tarjetasVivas.delete(t);   // la conversación se borró de la pantalla
    else if (t.sonando()) {
      viva = t;
      if (rid && t.id() === rid) suya = t;
    }
  }
  return suya || viva;
}

/** La persona escribe en el chat: el recorrido que suena se pausa al terminar la frase (en la pantalla en off, en el
 * acto: el servidor no tiene pausa suave). */
export function pausaPorMensaje() {
  const t = recorridoDelChat();
  if (t && !t.pausado()) t.controlar('pausar', { suave: true, nota: 'En pausa mientras responde el asistente.' });
}

/** La persona le va a hablar al micrófono (las preguntas por voz, dictado.js): lo que suena se pausa en el acto, sin
 * esperar el final de la frase, para que la narración no entre a la grabación. El plan del chat (el de la tarjeta que
 * suena), como al escribir; y si no hay ninguno, el que suene en la pantalla en off sin tarjeta en este chat (el de la
 * presentación automática): se le pregunta al servidor y se pausa allá. Devuelve `seguir(enviada)`, para cuando se
 * deja de oír: continúa lo que esta llamada pausó. El plan del chat, solo si la pregunta no se envió (se canceló, no
 * se oyó nada): si se envió, sigue en pausa mientras responde el asistente, como al escribir. El de la pantalla en
 * off, siempre: la sala no se queda en silencio mientras el asistente piensa, y el plan con que responda lo reemplaza. */
//
// Cada pregunta va detrás del «continuar» de la anterior (`ordenDeVoz`): si la persona vuelve a tocar el micrófono
// enseguida (tras «No oí nada», un fallo o un cancelar), la pausa nueva no se adelanta al «continuar» viejo. Y lo que
// dice si ya estaba en pausa tiene en cuenta ese «continuar» propio: la fase del servidor es la del último avance de la
// pantalla (no la del último control) y sigue diciendo `pausa` hasta que la pantalla lo aplica y avisa (`vozEnOff`; en
// la tarjeta, `pausado()`). Si no, se tomaba por una pausa a mano, no se pausaba y la sala narraba con el micrófono
// abierto. El «continuar» va con `keepalive`: si la página se va mientras se oye (agente.js cancela en `pagehide`), la
// sala no se queda en pausa para siempre.
let ordenDeVoz = Promise.resolve();
let vozEnOff = null;   // el último «continuar» de una pregunta a la pantalla en off sin tarjeta: {rid, en}
export function pausaPorVoz() {
  const antes = ordenDeVoz;
  const t = recorridoDelChat();
  if (t) {
    let mia = false;
    const pausa = antes.then(() => {
      if (t.pausado() || !t.sonando()) return null;   // una pausa a mano no la continúa una pregunta
      mia = true;
      return t.controlar('pausar', { nota: 'En pausa mientras usted pregunta.' });
    });
    ordenDeVoz = pausa;
    // «continuar» va detrás de la pausa (si se deja de oír enseguida, no la adelanta)
    return (enviada = false) => {
      ordenDeVoz = pausa.then(() => (mia && !enviada && t.sonando() ? t.controlar('continuar') : null));
    };
  }
  let rid = null;
  const pausa = (async () => {
    try {
      await antes;
      const d = await api.get('/api/pantalla/recorrido');
      const r = d?.recorrido;
      if (!r || typeof r !== 'object' || r.destino !== 'pantalla_off' || r.cerrado || d.conectada !== true) return;
      if (typeof r.id !== 'string' || !RID.test(r.id) || TERMINALES.includes(r.fase)) return;
      const nuestra = !!vozEnOff && vozEnOff.rid === r.id && Date.now() - vozEnOff.en < ORDEN_PROPIA_MS;
      if (r.fase === 'pausa' && !nuestra) return;   // en pausa a mano: no se toca
      await api.post('/api/pantalla/recorrido/control', { rid: r.id, accion: 'pausar' });
      rid = r.id;
      pedirPantalla();
    } catch { /* sin permiso para la presentación, o ya no suena: no hay nada que pausar */ }
  })();
  ordenDeVoz = pausa;
  return () => {
    ordenDeVoz = pausa.then(() => {
      if (!rid) return null;
      vozEnOff = { rid, en: Date.now() };
      return api.post('/api/pantalla/recorrido/control', { rid, accion: 'continuar' }, { keepalive: true })
        .then(pedirPantalla, () => {});
    });
  };
}

/** Que la pantalla en off de esta ventana (si la hay) pregunte ya por lo que cambió en el servidor, sin esperar su
 * sondeo (`pedirPantalla` del puente; nunca lanza). */
function pedirPantalla() {
  try { puente.pedirPantalla?.(); } catch { /* el puente sin esa función: la pantalla lo verá en su sondeo */ }
}

// ── La presentación automática: la franja de la acción `automatica` ──
const CAPITULO = /^[a-z0-9][a-z0-9_-]{0,39}$/;
let franjaAuto = null;   // la última franja: solo ella conserva su «Detener»

/** La acción `automatica` ({tipo, activa, capitulo, nombre, paso, de}) con lo que la franja usa, copiado, o null. */
export function automaticaValida(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || a.tipo !== 'automatica' || typeof a.activa !== 'boolean') return null;
  if (typeof a.capitulo !== 'string' || !CAPITULO.test(a.capitulo) || !cadena(a.nombre, 80)) return null;
  if (![a.paso, a.de].every((n) => Number.isInteger(n) && n >= 1 && n <= 60) || a.paso > a.de) return null;
  return { activa: a.activa, capitulo: a.capitulo, nombre: a.nombre.trim(), paso: a.paso, de: a.de };
}

/** La franja de la presentación automática `v` (ya validada con `automaticaValida`): «Presentación automática
 * encendida · empieza en Salud» con «Detener» (POST /api/pantalla/auto), o «Presentación automática apagada». Una
 * franja más nueva le quita el botón a la anterior. deps: {el, ico}. Devuelve {el}. */
export function crearFranjaAutomatica(v, { el, ico }) {
  const caja = el('div', 'agente-auto');
  caja.dataset.activa = v.activa ? 'si' : 'no';
  const texto = el('span', 'agente-auto-texto');
  const decir = (activa) => {
    const donde = v.paso > 1 ? `sigue en ${v.nombre}, paso ${v.paso} de ${v.de}` : `empieza en ${v.nombre}`;
    texto.textContent = activa ? `Presentación automática encendida · ${donde}` : 'Presentación automática apagada';
    caja.dataset.activa = activa ? 'si' : 'no';
  };
  decir(v.activa);
  caja.append(ico('presentacion'), texto);
  let boton = null, enviando = false;
  // Si el foco estaba en el botón, pasa a la franja: en <body>, Escape ya no cerraría el panel del asistente
  const quitarBoton = () => {
    if (!boton) return;
    const tenia = typeof boton.contains === 'function' && boton.contains(globalThis.document?.activeElement ?? null);
    boton.remove();
    boton = null;
    if (tenia) { caja.tabIndex = -1; caja.focus?.({ preventScroll: true }); }
  };
  if (v.activa) {
    boton = el('button', 'btn chico agente-auto-detener');
    boton.type = 'button';
    boton.append(ico('detener'), el('span', null, 'Detener'));
    boton.setAttribute('aria-label', 'Detener la presentación automática');
    const error = el('small', 'agente-auto-error');
    error.setAttribute('role', 'alert');
    error.hidden = true;
    boton.addEventListener('click', async () => {
      if (!boton || enviando) return;
      enviando = true;
      error.hidden = true;
      try {
        await api.post('/api/pantalla/auto', { accion: 'detener' });
        quitarBoton();
        decir(false);
        pedirPantalla();
      } catch (e) {
        enviando = false;
        const porque = e instanceof ErrorApi && e.message && e.message !== 'Error inesperado' ? e.message : 'intente de nuevo';
        error.textContent = `No se pudo detener: ${String(porque).slice(0, 140)}`;
        error.hidden = false;
      }
    });
    caja.append(boton, error);
  }
  franjaAuto?.caducar();
  franjaAuto = { caducar: quitarBoton };
  return { el: caja };
}

const sinMovimiento = () => {
  try { return !!globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
};

/**
 * La tarjeta del plan `a` (ya validado con `tarjetaValida`).
 * deps: {el, ico, alSugerencia(texto), reproducir(rid, desde, nuevo?) → bool (la vista o el proyector: el recorrido
 * guardado con el id `rid`, desde la escena `desde`; con `nuevo`, con ese id: el que le dio el servidor al volver a
 * armarlo), guardado?(rid) → bool (¿lo tiene este navegador?), frases?(rid) → [[frase, …], …] (las frases de cada
 * escena del recorrido que tiene este navegador; sin eso, la narración se parte aquí)}
 */
export function crearTarjetaRecorrido(a, { el, ico, alSugerencia, reproducir, guardado, frases }) {
  let rid = a.id;
  let donde = a.destino === 'pantalla_off' ? 'pantalla_off' : (proyectorVivo() ? 'proyector' : 'aqui');
  let ultimo = null;        // el último avance
  let terminado = false;
  let quitar = () => {};
  let escuchando = false;   // la pantalla en off: el sondeo sigue (en una pausa larga se detiene hasta el próximo control)
  let sondeos = 0;          // el sondeo vigente (uno que se reemplazó no toca `escuchando`)
  // Los plazos de la pantalla en off corren desde que existe este id, no desde cada sondeo: un control (la pausa que
  // sale con cada mensaje) vuelve a preguntar enseguida, pero no los reinicia
  let desdeRid = Date.now();
  let sinPantallaDesde = null;   // desde cuándo el servidor dice que la pantalla en off no está abierta
  let volviendo = false;         // «Volver a reproducir» ya pidió el id nuevo y espera su primer avance
  let empezo = false;            // ya salió del «Plan listo» (el primer paso empezó a decirse, o se reanudó más adelante)
  let viva = 'preparando';       // la fase del paso `nViva` antes de una pausa: dice qué frase queda resaltada
  let nViva = 0;
  let actual = null;             // el <li> del paso en curso (o el del cierre)
  let completo = false;          // «Ver todo»: todos los pasos abiertos y la lista sin su desplazamiento propio
  let vozSabida = null;          // cómo está la voz donde suena (del avance o del interruptor)
  let notaPropia = 0;            // hasta cuándo se queda la nota que pidió la persona
  let notaDeVoz = false;         // la nota que se ve habla de la voz
  // La pantalla en off de ESTA ventana lo narra: cuándo llegó su último avance por el puente, y cuándo cambió
  let localEn = 0;
  let localCambio = 0;
  let localClave = null;
  let ordenPropia = null;        // la pausa o el «continuar» de esta tarjeta que el avance todavía no refleja: {pausa, en}
  let colaControl = Promise.resolve();   // los controles a la pantalla en off, uno detrás de otro
  /** ¿La narra la pantalla en off de esta ventana? (sus avances llegan por el puente) */
  const local = () => a.destino === 'pantalla_off' && Date.now() - localEn < SIN_NOTICIAS_S * 1000;

  const art = el('article', 'agente-recorrido');
  art.dataset.destino = a.destino;
  const cab = el('header', 'rec-cab');
  const sello = el('span', 'rec-sello');
  sello.append(ico('presentacion'));
  const tit = el('div', 'rec-titulos');
  // «Plan · título»
  const h = el('h3');
  h.append(el('span', 'rec-tipo', 'Plan'), el('span', 'rec-sep', ' · '), el('span', 'rec-titulo', a.titulo));
  const meta = el('small', 'rec-meta');
  tit.append(h, meta);
  cab.append(sello, tit);
  const avance = el('div', 'rec-avance');
  const barra = el('i');
  avance.append(barra);
  avance.setAttribute('aria-hidden', 'true');
  // El estado, «Ver todo» y el interruptor de voz, en un renglón
  const fila = el('div', 'rec-fila');
  const estadoEl = el('p', 'rec-estado', LISTO);
  const bTodo = el('button', 'rec-todo', 'Ver todo');
  bTodo.type = 'button';
  bTodo.setAttribute('aria-expanded', 'false');
  bTodo.setAttribute('aria-label', 'Ver todo el plan');
  const bVoz = el('button', 'rec-voz');
  bVoz.type = 'button';
  bVoz.setAttribute('role', 'switch');
  bVoz.setAttribute('aria-checked', 'false');
  bVoz.setAttribute('aria-label', 'Voz del plan');
  const vozTexto = el('span', 'rec-voz-texto', 'Voz');
  const perilla = el('i', 'rec-voz-perilla');
  perilla.setAttribute('aria-hidden', 'true');
  bVoz.append(ico('voz'), vozTexto, perilla);
  bVoz.hidden = true;   // hasta saber cómo está (el primer avance)
  fila.append(estadoEl, bTodo, bVoz);

  // Las frases de cada paso: las del recorrido que tiene este navegador (si arman la misma narración) o partidas aquí
  let propias = null;
  try { propias = frases?.(a.id) ?? null; } catch { propias = null; }
  const frasesDe = (i) => {
    const f = Array.isArray(propias) ? propias[i] : null;
    return Array.isArray(f) && f.length && f.every((x) => typeof x === 'string') && f.join(' ') === a.escenas[i].narracion
      ? f : partirFrases(a.escenas[i].narracion);
  };
  const marcaDe = () => {
    const m = el('span', 'rec-marca');
    m.setAttribute('aria-hidden', 'true');
    return m;
  };
  const lista = el('ol', 'rec-escenas');
  lista.tabIndex = 0;   // se desplaza: con el teclado también
  lista.setAttribute('aria-label', 'Pasos del plan');
  const nuevoItem = (e, i) => {
    const li = el('li', 'rec-escena');
    const hecho = el('span', 'sr');   // «Hecho»: la marca, para quien no la ve
    const texto = el('p', 'rec-narracion');
    const spans = frasesDe(i).map((f) => el('span', 'rec-frase', f));
    spans.forEach((s, k) => { if (k) texto.append(' '); texto.append(s); });
    const chips = el('div', 'rec-chips');
    for (const k of e.hace) {
      const c = el('span', 'rec-chip');
      c.title = HACE[k][0];
      c.append(ico(HACE[k][1]), el('span', null, HACE[k][0]));
      chips.append(c);
    }
    li.append(marcaDe(), hecho, el('b', 'rec-donde', e.donde), texto, chips);
    // (detrás del último paso, antes del cierre si ya está: el plan en flujo crece)
    if (liCierre) lista.insertBefore(li, liCierre); else lista.append(li);
    return { li, hecho, frases: spans, avisos: new Set(), aviso: null };
  };
  let liCierre = null;
  let hechoCierre = null;
  const items = a.escenas.map(nuevoItem);
  const ponerCierre = () => {
    liCierre = el('li', 'rec-escena rec-cierre');
    hechoCierre = el('span', 'sr');
    const pts = el('ul', 'rec-puntos');
    for (const x of a.cierre) pts.append(el('li', null, x));
    liCierre.append(marcaDe(), hechoCierre, el('b', 'rec-donde', 'En resumen'), pts);
    lista.append(liCierre);
  };
  if (a.cierre) ponerCierre();
  const notaEl = el('p', 'rec-nota');
  notaEl.hidden = true;

  const boton = (accion, etiqueta, icono, clase = 'btn chico') => {
    const b = el('button', clase);
    b.type = 'button';
    b.dataset.accion = accion;
    b.title = etiqueta;
    b.setAttribute('aria-label', etiqueta);
    b.append(ico(icono), el('span', null, etiqueta));
    return b;
  };
  const controles = el('div', 'rec-controles');
  const bPausa = boton('pausar', 'Pausa', 'pausa');
  const bAnt = boton('anterior', 'Anterior', 'anterior');
  const bSig = boton('siguiente', 'Siguiente', 'siguiente');
  const bRep = boton('repetir', 'Repetir', 'repetir');
  const bDet = boton('detener', 'Detener', 'detener');
  controles.append(bPausa, bAnt, bSig, bRep, bDet);
  controles.setAttribute('role', 'group');
  controles.setAttribute('aria-label', 'Controles del plan');
  const final = el('div', 'rec-final');
  final.hidden = true;
  const bOtra = boton('reproducir', 'Volver a reproducir', 'reproducir', 'btn chico primario');
  const bReanudar = boton('reanudar', 'Reanudar', 'reproducir', 'btn chico primario');
  bReanudar.hidden = true;
  final.append(bOtra, bReanudar);
  const sugerencias = el('div', 'rec-sugerencias');
  const ponerSugerencias = () => {
    sugerencias.replaceChildren();
    for (const s of a.sugerencias) {
      const b = el('button', 'btn chico rec-sugerencia', s);
      b.type = 'button';
      b.addEventListener('click', () => alSugerencia?.(s));
      sugerencias.append(b);
    }
  };
  ponerSugerencias();
  sugerencias.hidden = true;
  art.append(cab, avance, fila, lista, notaEl, controles, final, sugerencias);
  art.dataset.etapa = 'listo';

  function pintarMeta() {
    const partes = [`${a.escenas.length} ${a.escenas.length === 1 ? 'paso' : 'pasos'}${a.abierto ? ' por ahora: el panel sigue escribiéndolo' : ''}`,
      `≈ ${duracion(a.duracion_ms)}`, DONDE[donde]];
    meta.textContent = partes.join(' · ');
  }
  pintarMeta();

  // ── El final de la tarjeta (los controles, las sugerencias) no se sale de la vista cuando la tarjeta crece ──
  let marcoChat = null;
  /** Lo que desplaza a la tarjeta: el registro del chat. */
  function marco() {
    if (marcoChat?.isConnected && marcoChat.contains(art)) return marcoChat;
    marcoChat = null;
    if (typeof art.getBoundingClientRect !== 'function' || typeof globalThis.getComputedStyle !== 'function') return null;
    for (let x = art.parentElement; x && !marcoChat; x = x.parentElement) {
      const o = getComputedStyle(x).overflowY;
      if (o === 'auto' || o === 'scroll') marcoChat = x;
    }
    return marcoChat;
  }
  /** Corre `f`, que cambia el alto de la tarjeta o del chat (una nota, los botones del final, la barra fija que
   * aparece): si el final de la tarjeta se veía, se sigue viendo (el chat baja lo justo). Si la persona estaba leyendo
   * otra parte y no se veía, el chat no se mueve. */
  function conElPieALaVista(f) {
    const m = marco();
    let hueco = null;
    if (m) {
      const r = art.getBoundingClientRect(), v = m.getBoundingClientRect();
      if (r.bottom <= v.bottom + 1 && r.bottom > v.top) hueco = v.bottom - r.bottom;
    }
    f();
    if (hueco === null) return;
    const d = art.getBoundingClientRect().bottom + hueco - m.getBoundingClientRect().bottom;
    if (d > 1) m.scrollTop += Math.ceil(d);
  }

  /** La nota de la tarjeta. `deVoz`: habla de la voz (el interruptor la quita cuando ya no hace falta). */
  function nota(t, deVoz = false) {
    notaDeVoz = !!t && deVoz;
    if (notaEl.textContent === (t || '') && notaEl.hidden === !t) return;
    conElPieALaVista(() => {
      notaEl.textContent = t || '';
      notaEl.hidden = !t;
    });
  }
  /** Una nota que pidió la persona (tocó el interruptor de voz): se queda un momento aunque llegue otro avance. */
  function notaDeLaPersona(t) {
    nota(t, true);
    notaPropia = t ? Date.now() + NOTA_PROPIA_MS : 0;
  }

  // ── La lista: cuál va abierto y hasta dónde se desplaza ──
  const sinLista = () => completo || typeof lista.scrollTo !== 'function';
  const aLaVista = (li) => sinLista() || !li
    || (li.offsetTop < lista.scrollTop + lista.clientHeight && li.offsetTop + li.offsetHeight > lista.scrollTop);
  /** Lleva la lista al paso `li`, con el anterior asomado arriba (lo que se acaba de decir). */
  function llevar(li, suave = true) {
    if (sinLista() || !li) return;
    const ref = li.previousElementSibling || li;
    lista.scrollTo({ top: Math.max(0, ref.offsetTop), behavior: suave && !sinMovimiento() ? 'smooth' : 'auto' });
  }
  function abrir() {
    for (const it of items) it.li.classList.toggle('abierta', completo || it.li === actual);
    liCierre?.classList.toggle('abierta', completo || liCierre === actual);
  }
  bTodo.addEventListener('click', () => {
    completo = !completo;
    art.classList.toggle('completo', completo);
    bTodo.setAttribute('aria-expanded', String(completo));
    bTodo.textContent = completo ? 'Resumir' : 'Ver todo';
    bTodo.setAttribute('aria-label', completo ? 'Resumir el plan' : 'Ver todo el plan');
    abrir();
    if (!completo) llevar(actual, false);
  });

  // ── La voz ──
  function pintarVoz(e) {
    if (!VOCES.includes(e)) return;
    vozSabida = e;
    bVoz.dataset.voz = e;
    bVoz.setAttribute('aria-checked', String(e === 'activa'));
    vozTexto.textContent = VOZ[e].texto;
    bVoz.setAttribute('aria-label', VOZ[e].nombre);
    bVoz.title = `${VOZ[e].ayuda} (${DONDE[donde]})`;
    bVoz.hidden = terminado;
  }
  bVoz.addEventListener('click', () => {
    // Solo si suena en esta pestaña o en la pantalla en off de esta ventana (el puente usa la voz que esa vista
    // registró): con el plan en otra pantalla en off, la vista de aquí (si está abierta) no es la que habla
    let e = null;
    if (donde === 'aqui' || local()) { try { e = puente.alternarVozRecorrido?.() ?? null; } catch { e = null; } }
    if (!VOCES.includes(e)) {
      notaDeLaPersona(VOZ_ALLA[donde === 'aqui' && proyectorVivo() ? 'proyector' : donde]);
      return;
    }
    pintarVoz(e);
    if (e === 'sin_voces') notaDeLaPersona('Este navegador no tiene voces en español: el plan se lee en pantalla.');
    else if (e === 'sin_activar') notaDeLaPersona('El navegador todavía no deja sonar la voz: toque otra vez «Activar voz».');
    else if (notaDeVoz) notaDeLaPersona('');
  });

  const pintar = (p) => conElPieALaVista(() => pintarYa(p));
  function pintarYa(p) {
    ultimo = p;
    if (volviendo) { volviendo = false; bOtra.disabled = false; }
    const de = a.escenas.length;
    const n = Math.min(Math.max(p.n || 1, 1), de);
    const fase = p.fase in FASE ? p.fase : 'preparando';
    const enCierre = fase === 'cierre' || (fase === 'pausa' && p.enCierre);
    const fin = fase === 'fin';
    terminado = TERMINALES.includes(fase);
    if (ordenPropia && (terminado || (fase === 'pausa') === ordenPropia.pausa)) ordenPropia = null;
    // «Plan listo»: llegó entero y todavía no empieza (la espera de antes del primer paso, o la pantalla en off que aún no avisa)
    if (fase !== 'preparando' || n > 1) empezo = true;
    const listo = !empezo;
    // La fase del paso antes de una pausa (la pausa no cambia lo que queda resaltado)
    if (fase !== 'pausa') { viva = fase; nViva = n; } else if (nViva !== n) { viva = p.frase > 0 ? 'narrando' : 'preparando'; nViva = n; }
    const nuevo = terminado || listo ? null : enCierre ? liCierre : items[n - 1].li;
    // ¿la lista seguía al paso en curso? (antes de abrir y cerrar pasos: cambian de alto)
    const seguia = aLaVista(actual);
    const cambio = nuevo !== actual;
    actual = nuevo;
    items.forEach((it, i) => {
      const k = i + 1;
      const hecha = fin || (!listo && (k < n || (enCierre && k <= n)));
      it.li.classList.toggle('hecha', hecha);
      it.hecho.textContent = hecha ? 'Hecho. ' : '';
      const cur = it.li === actual;
      if (cur) { it.li.setAttribute('aria-current', 'step'); it.li.dataset.fase = fase; } else { it.li.removeAttribute('aria-current'); delete it.li.dataset.fase; }
      // la frase que suena y las que ya se dijeron
      const suena = cur && viva === 'narrando' ? Math.min(p.frase || 0, it.frases.length - 1) : -1;
      const todas = cur && viva === 'sosteniendo';
      it.frases.forEach((s, j) => {
        s.classList.toggle('sonando', j === suena);
        s.classList.toggle('dicha', todas || j < suena);
      });
    });
    if (liCierre) {
      liCierre.classList.toggle('hecha', fin);
      hechoCierre.textContent = fin ? 'Hecho. ' : '';
      if (liCierre === actual) liCierre.setAttribute('aria-current', 'step'); else liCierre.removeAttribute('aria-current');
    }
    abrir();
    if (cambio && seguia) llevar(actual);
    if (p.aviso && AVISO[p.aviso]) marcarAviso(n, AVISO[p.aviso]);
    if (p.motivo === 'escena_fallida' && !TERMINALES.includes(fase)) marcarAviso(n, 'no se pudo mostrar');
    const total = de + 1;
    const hechas = fin ? total : enCierre ? de + 0.5 : listo ? 0
      : (n - 1) + (viva === 'sosteniendo' ? 0.85 : viva === 'narrando' ? 0.5 : 0.15);
    barra.style.width = `${Math.round((hechas / total) * 100)}%`;
    art.dataset.fase = fase;
    art.dataset.etapa = terminado ? 'final' : listo ? 'listo' : 'marcha';
    // lo que dice la línea de estado
    if (fin) estadoEl.textContent = `Terminó${p.t_ms ? ` · ${duracion(p.t_ms)}` : ''}`;
    else if (fase === 'detenido') estadoEl.textContent = p.motivo === 'reemplazo' ? 'Lo reemplazó otro plan' : `Detenido en el paso ${n}`;
    else if (fase === 'error') estadoEl.textContent = `Se detuvo por un error en el paso ${n}`;
    else if (enCierre) estadoEl.textContent = fase === 'pausa' ? 'En pausa · en el resumen' : 'En resumen';
    else if (listo) estadoEl.textContent = LISTO;
    else estadoEl.textContent = `Paso ${n} de ${de} · ${FASE[fase]}`;
    // la voz donde suena
    if (VOCES.includes(p.voz)) pintarVoz(p.voz);
    bVoz.hidden = terminado || !vozSabida;
    // los botones
    const pausado = fase === 'pausa';
    bPausa.dataset.accion = pausado ? 'continuar' : 'pausar';
    bPausa.replaceChildren(ico(pausado ? 'reproducir' : 'pausa'), el('span', null, pausado ? 'Continuar' : 'Pausa'));
    bPausa.title = pausado ? 'Continuar' : 'Pausa';
    bPausa.setAttribute('aria-label', bPausa.title);
    controles.hidden = terminado;
    final.hidden = !terminado;
    sugerencias.hidden = !terminado || !a.sugerencias.length;
    const cortado = fase === 'detenido' && p.motivo === 'proyector';
    bReanudar.hidden = !cortado;
    if (cortado) {
      bReanudar.querySelector('span').textContent = `Reanudar desde el paso ${n}`;
      bReanudar.dataset.desde = String(n);
    }
    // las notas
    if (cortado) nota('Se detuvo: se cerró el proyector.');
    else if (fase === 'detenido' && p.motivo === 'otra_orden') nota('Se detuvo: el asistente mostró otra cosa.');
    else if (fase === 'detenido' && p.motivo === 'sin_respuesta') nota('Se detuvo: la pantalla en off dejó de responder.');
    else if (pausado && p.motivo === 'mensaje') nota('En pausa mientras responde el asistente.');
    else if (pausado && p.motivo === 'persona') nota('En pausa: movieron la imagen. Al continuar, el paso vuelve.');
    else if (Date.now() < notaPropia && !terminado) { /* la que pidió la persona se queda un momento */ }
    else if (!terminado && donde === 'proyector' && p.voz === 'sin_activar') nota('Toque el botón «Voz» (abajo a la izquierda) en la ventana del proyector para activar la voz; tocar la maqueta pausa el plan.', true);
    else if (!terminado && donde === 'pantalla_off' && p.voz === 'sin_activar') nota(local() ? 'Toque «Activar voz» (o la presentación) para oír el plan.' : 'Toque la pantalla en off (o su botón «Voz») para activar la voz.', true);
    else if (!terminado && donde === 'aqui' && p.voz === 'sin_activar') nota('Toque «Activar voz» para oír el plan.', true);
    else if (!pausado) nota('');
    if (terminado) soltar();
    avisarBarra();
  }

  /** Un aviso del paso `n` (cada texto una vez; varios, en el mismo renglón). */
  function marcarAviso(n, t) {
    const it = items[n - 1];
    if (!it || it.avisos.has(t)) return;
    it.avisos.add(t);
    if (!it.aviso) { it.aviso = el('small', 'rec-aviso'); it.li.append(it.aviso); }
    it.aviso.textContent = [...it.avisos].join(' · ');
  }
  function quitarAvisos() {
    for (const it of items) {
      it.avisos.clear();
      it.aviso?.remove();
      it.aviso = null;
    }
  }

  // ── De dónde llega el avance ──
  const conCierre = (p) => ({ ...p, enCierre: p.fase === 'cierre' || (p.fase === 'pausa' && ultimo?.fase === 'cierre') || (p.fase === 'pausa' && !!ultimo?.enCierre) });
  const delPuente = (p, de) => {
    if (p.rid !== rid) return;
    // el reproductor de aquí lo soltó para pasárselo al proyector que se abrió: sigue allá (lo dirá el proyector)
    if (de === 'aqui' && p.fase === 'detenido' && p.motivo === 'proyector') return;
    if (de === 'proyector' || de === 'aqui') { const antes = donde; donde = de; if (antes !== donde) pintarMeta(); }
    pintar(conCierre(p));
  };
  // La pantalla en off de esta misma ventana avisa su avance en el acto: se pinta sin esperar al sondeo
  const delLocal = (p, de) => {
    if (de !== 'aqui' || p.rid !== rid || terminado) return;
    localEn = Date.now();
    const clave = `${p.n}/${p.fase}/${p.frase}`;
    if (clave !== localClave) { localClave = clave; localCambio = localEn; }
    pintar(conCierre(p));
  };
  function escuchar() {
    quitar();
    if (a.destino === 'vista') {
      quitar = escucharRecorrido(delPuente);
    } else {
      // El tope corre desde el último cambio (otra escena, otra fase u otra frase), no desde que se creó la tarjeta: una
      // pausa larga para preguntas no la congela. Al vencer en pausa sigue preguntando más despacio; sonando, o sin
      // noticias de la pantalla (no está en pausa y no avisa, o ya no pregunta por su estado), lo da por detenido
      let hasta = Date.now() + SONDEO_MAX_MS;
      let visto = null;
      let parar = false;
      let reloj = 0;
      const mio = ++sondeos;
      const fin = () => { if (sondeos === mio) escuchando = false; };
      const quitarLocal = escucharRecorrido(delLocal);
      const vuelta = async () => {
        if (parar || !art.isConnected) { fin(); return; }
        let espera = SONDEO_MS;
        if (local()) hasta = Math.max(hasta, localCambio + SONDEO_MAX_MS);   // cambia en esta ventana: no está quieto
        if (Date.now() > hasta) {
          if (terminado || ultimo?.fase !== 'pausa') {
            fin();
            if (!terminado) pintar({ ...(ultimo || { rid, n: 1, de: a.escenas.length }), fase: 'detenido', motivo: 'sin_respuesta' });
            return;
          }
          espera = SONDEO_LENTO_MS;
        }
        try {
          const r = await api.get('/api/pantalla/recorrido');
          if (parar) return;   // mientras tanto lo reemplazó otro sondeo (un control, volver a reproducir)
          const x = r?.recorrido;
          if (!x || x.id !== rid) {
            // otro recorrido lo reemplazó, o se cerró hace rato
            if (!terminado) pintar({ ...(ultimo || { n: 1 }), fase: 'detenido', motivo: x ? 'reemplazo' : ultimo?.motivo });
            fin();
            return;
          }
          const fase = x.fase === 'sin_avance' ? 'preparando' : x.fase;
          const p = { rid, n: x.escena, de: x.de, fase: x.cerrado && !TERMINALES.includes(fase) ? 'detenido' : fase,
            frase: Number.isInteger(r.frase) ? r.frase : 0, voz: x.voz, motivo: x.motivo ?? undefined,
            enCierre: fase === 'cierre' || (fase === 'pausa' && !!ultimo?.enCierre) };
          const clave = `${p.n}/${p.fase}/${p.frase}`;
          if (clave !== visto) { visto = clave; hasta = Date.now() + SONDEO_MAX_MS; }
          for (const av of Array.isArray(r.avisos) ? r.avisos : []) {
            if (av && Number.isInteger(av.n) && Object.prototype.hasOwnProperty.call(AVISO, av.tipo)) marcarAviso(av.n, AVISO[av.tipo]);
          }
          // Sin noticias: la pantalla se cerró (no pregunta por su estado hace SIN_NOTICIAS_S; también en pausa), no
          // empezó a tiempo (no lo va a narrar) o, sonando, no avisa hace rato (en pausa no hay avances: eso solo no dice
          // nada)
          if (r.conectada === false) sinPantallaDesde ??= Date.now();
          else if (r.conectada === true) sinPantallaDesde = null;
          const cerrada = sinPantallaDesde !== null && Date.now() - sinPantallaDesde > SIN_NOTICIAS_S * 1000;
          // Con la pantalla en off de esta ventana narrándolo, sus avances mandan: el sondeo trae lo mismo, con retraso
          // (pintado, haría retroceder la tarjeta), y no está mudo. Lo terminal sí se pinta
          const aqui = local();
          const mudo = !aqui && !TERMINALES.includes(p.fase) && (cerrada || (x.fase === 'sin_avance' ? Date.now() - desdeRid > SIN_EMPEZAR_MS
            : x.fase !== 'pausa' && Number.isInteger(x.hace_s) && x.hace_s > SIN_NOTICIAS_S));
          if (!aqui || TERMINALES.includes(p.fase)) pintar(mudo ? { ...p, fase: 'detenido', motivo: 'sin_respuesta' } : p);
          if (mudo || TERMINALES.includes(p.fase)) { fin(); return; }
        } catch { espera = Math.max(espera, SONDEO_MS * 3); }
        reloj = setTimeout(vuelta, espera);
      };
      quitar = () => { parar = true; clearTimeout(reloj); fin(); quitarLocal(); };
      escuchando = true;
      // la primera, en la vuelta siguiente: al crearse, la tarjeta todavía no está en el chat (`isConnected` daría falso
      // y el sondeo no arrancaba nunca)
      reloj = setTimeout(vuelta, 0);
    }
  }

  function soltar() {
    if (a.destino === 'pantalla_off') { quitar(); quitar = () => {}; }
  }

  async function controlar(accion, { suave = false, nota: t = null } = {}) {
    if (terminado) return;
    // Lo propio cuenta desde ya para `pausado()`: el avance que lo refleja llega después
    const propia = accion === 'pausar' || accion === 'continuar' ? { pausa: accion === 'pausar', en: Date.now() } : null;
    if (propia) ordenPropia = propia;
    try {
      if (a.destino === 'pantalla_off') {
        // En orden (una pausa no se adelanta al «continuar» anterior) y con `keepalive` (la página puede irse)
        const envio = colaControl.then(() => api.post('/api/pantalla/recorrido/control', { rid, accion }, { keepalive: true }));
        colaControl = envio.catch(() => {});
        const r = await envio;
        if (accion === 'reproducir' && r?.id && RID.test(r.id)) { rid = r.id; terminado = false; desdeRid = Date.now(); sinPantallaDesde = null; escuchar(); }
        else escuchar();   // vuelve a preguntar enseguida (en una pausa larga preguntaba despacio, o ya no preguntaba)
        pedirPantalla();   // la pantalla en off de esta ventana, si la hay, lo aplica ya
      } else {
        const r = await controlRecorrido(rid, accion, { suave });
        if (r && r.ok === false) throw new Error(r.error || 'No se pudo');
      }
      if (t) nota(t);
    } catch (e) {
      if (ordenPropia === propia) ordenPropia = null;
      nota(`No se pudo: ${String(e?.message || 'la presentación no está abierta').slice(0, 140)}.`);
    }
  }

  controles.addEventListener('click', (e) => {
    const b = e.target.closest?.('button[data-accion]');
    if (b) controlar(b.dataset.accion);
  });
  // Volver a reproducirlo: el servidor lo vuelve a armar con un id nuevo (también uno que otra orden cerró) y la tarjeta
  // sigue a ese. En la pestaña o el proyector se reproduce el guardado en este navegador con el id nuevo: antes se
  // reproducía con el viejo, sin pasar por el servidor, y su avance rebotaba (409), el asistente no lo veía y sus
  // controles iban a otro recorrido. Si el asistente armó otro después, este ya no se puede volver a reproducir
  bOtra.addEventListener('click', async () => {
    if (bOtra.disabled) return;
    const enVista = a.destino !== 'pantalla_off';
    if (enVista && guardado && !guardado(rid)) {
      nota('No se pudo volver a reproducir: el plan ya no está en este navegador.');
      return;
    }
    bOtra.disabled = true;
    let nuevo;
    try {
      const r = await api.post('/api/pantalla/recorrido/control', { rid, accion: 'reproducir' });
      if (!r?.id || !RID.test(r.id)) throw new Error('el servidor no lo volvió a armar');
      nuevo = r.id;
    } catch (e) {
      const otro = e instanceof ErrorApi && e.estado === 409;
      bOtra.disabled = otro;
      nota(otro ? 'Ya no se puede volver a reproducir: hay un plan más nuevo.'
        : `No se pudo: ${String(e?.message || 'sin conexión').slice(0, 140)}.`);
      return;
    }
    const viejo = rid;
    rid = nuevo;
    terminado = false;
    ultimo = null;
    desdeRid = Date.now();
    sinPantallaDesde = null;
    bOtra.disabled = false;
    quitarAvisos();
    if (!enVista) {
      pintar({ rid, n: 1, de: a.escenas.length, fase: 'preparando' });
      escuchar();
      pedirPantalla();
    } else {
      // En la pestaña o el proyector no pinta «preparando» todavía: lo pinta el primer avance del reproductor (si la
      // vista no llega a reproducirlo, por cambios sin guardar en otra vista, la tarjeta no queda «preparando» con la
      // barra puesta). Mientras tanto, ni otro «Volver a reproducir» (armaría otro id) ni «Reanudar» (iría encima)
      volviendo = true;
      bOtra.disabled = true;
      bReanudar.hidden = true;
      estadoEl.textContent = 'Volviendo a empezar…';
      if (!reproducir?.(viejo, 1, nuevo)) {
        volviendo = false;
        bOtra.disabled = false;
        pintar({ rid, n: 1, de: a.escenas.length, fase: 'detenido' });
        nota('No se pudo volver a reproducir: el plan ya no está en este navegador.');
      } else setTimeout(() => { if (volviendo) { volviendo = false; bOtra.disabled = false; } }, VOLVER_ESPERA_MS);
    }
  });
  // Reanudar (se cerró el proyector que lo reproducía): el mismo recorrido, con el mismo id, sigue en esta pestaña desde la
  // escena donde quedó; para el servidor nunca se cortó
  // Antes, que siga siendo el vigente: reanudar uno que el servidor cerró o reemplazó cortaría lo que suena y rebotaría en
  // su primer avance (409)
  bReanudar.addEventListener('click', async () => {
    const k = Number(bReanudar.dataset.desde) || 1;
    // el que suena es por fuerza más nuevo (el servidor solo acepta el último): este ya no se reanuda
    const otro = recorridoEnCurso();
    if (otro && otro.rid !== rid) { bReanudar.hidden = true; nota('Ya no se puede reanudar: hay un plan más nuevo.'); return; }
    // el vigente del servidor (`vigente`, no el resumen: ese deja de nombrar uno cerrado o terminado a los dos minutos)
    let resp = null;
    try { resp = await api.get('/api/pantalla/recorrido'); } catch { /* sin conexión: se intenta igual */ }
    const v = resp?.vigente;
    if (resp && (!v || v.id !== rid || v.cerrado)) {
      bReanudar.hidden = true;
      nota(v && v.id === rid ? 'Ya no se puede reanudar: se cerró. Use «Volver a reproducir».' : 'Ya no se puede reanudar: hay un plan más nuevo.');
      return;
    }
    if (!reproducir?.(rid, k)) nota('No se pudo reanudar: el plan ya no está en este navegador.');
  });

  const t = {
    el: art,
    id: () => rid,
    titulo: a.titulo,
    sonando: () => art.isConnected && !terminado && !!ultimo,
    viejo: () => { if (art.isConnected) return false; quitar(); return true; },
    // Con una pausa o un «continuar» propio reciente, ese manda: el avance que lo refleja todavía no llegó
    pausado: () => (ordenPropia && Date.now() - ordenPropia.en < ORDEN_PROPIA_MS ? ordenPropia.pausa : ultimo?.fase === 'pausa'),
    avance: () => ultimo,
    controlar,
    /** El plan en flujo creció (`v`, ya validada, con este id): se agregan sus pasos nuevos, el cierre, las sugerencias y
     * la duración; sin `abierto`, ya está entero. Los pasos que ya tenía no se tocan. */
    crecer(v) {
      if (!v || v.id !== a.id) return false;
      try { propias = frases?.(a.id) ?? propias; } catch { /* las de antes */ }
      for (let i = a.escenas.length; i < v.escenas.length; i++) {
        a.escenas.push(v.escenas[i]);
        items.push(nuevoItem(v.escenas[i], i));
      }
      if (v.cierre && !a.cierre) { a.cierre = v.cierre; ponerCierre(); }
      if (v.sugerencias.length) { a.sugerencias = v.sugerencias; ponerSugerencias(); }
      a.duracion_ms = v.duracion_ms;
      a.abierto = v.abierto;
      pintarMeta();
      if (ultimo) pintar(ultimo);
      return true;
    },
  };
  tarjetasVivas.add(t);
  escuchar();
  // El plan pudo empezar antes de que existiera su tarjeta (su primer avance ya pasó, y el siguiente llega con el primer
  // paso): lo que el puente sabe de él se pinta en cuanto la tarjeta está en el chat. Así la barra y la pausa al
  // escribir ya lo cuentan, y el interruptor de voz dice cómo está
  // (La pantalla en off de esta ventana también: el chat le pide que pregunte en cuanto llega el resultado de la
  // herramienta, antes que esta acción)
  setTimeout(() => {
    const ya = ultimo || !art.isConnected ? null : recorridoEnCurso();
    if (!ya || ya.rid !== rid) return;
    const { donde: de, ...p } = ya;
    if (a.destino === 'vista') delPuente(p, de);
    else delLocal(p, de);
  }, 0);
  return t;
}

/**
 * La barra fija arriba del registro del chat mientras un plan suena (aunque el turno haya terminado o la persona suba
 * en el historial): «● Plan · paso 3 de 8 · título · Pausa · Detener».
 */
export function montarBarraRecorrido(antesDe, { el, ico }) {
  const b = el('div', 'agente-rec-barra');
  b.hidden = true;
  const punto = el('span', 'rec-punto');
  punto.setAttribute('aria-hidden', 'true');
  const txt = el('span', 'rec-barra-texto');
  const pausa = el('button', 'btn fantasma chico');
  pausa.type = 'button';
  const det = el('button', 'btn fantasma chico');
  det.type = 'button';
  det.title = 'Detener el plan';
  det.setAttribute('aria-label', det.title);
  det.append(ico('detener'), el('span', null, 'Detener'));
  b.append(punto, txt, pausa, det);
  antesDe.before(b);
  let actual = null;
  const pintar = (t) => {
    actual = t;
    b.hidden = !t;
    if (!t) return;
    const p = t.avance();
    const enPausa = p?.fase === 'pausa';
    b.dataset.fase = p?.fase || '';
    const va = p?.fase === 'cierre' || (enPausa && p?.enCierre) ? 'en resumen' : `paso ${p?.n || 1} de ${p?.de || 1}`;
    txt.textContent = `Plan · ${va}${enPausa ? ' · en pausa' : ''} · ${t.titulo}`;
    pausa.replaceChildren(ico(enPausa ? 'reproducir' : 'pausa'), el('span', null, enPausa ? 'Continuar' : 'Pausa'));
    pausa.title = enPausa ? 'Continuar el plan' : 'Pausar el plan';
    pausa.setAttribute('aria-label', pausa.title);
  };
  oyentesBarra.add(pintar);
  pausa.addEventListener('click', () => { if (actual) actual.controlar(actual.pausado() ? 'continuar' : 'pausar'); });
  det.addEventListener('click', () => { if (actual) actual.controlar('detener'); });
  return () => { oyentesBarra.delete(pintar); b.remove(); };
}
