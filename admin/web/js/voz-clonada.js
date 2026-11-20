// La voz clonada del asistente (docs/agente.md, «La voz clonada de Mnemo»): la voz que el administrador clonó en Mnemo
// narra el plan guiado (reproductor.js) y lee las respuestas del asistente (locutor.js), con la voz del navegador
// (voz.js) como respaldo de cada frase. Devuelve EXACTAMENTE la forma de `crearVoz` de voz.js (`estado`, `encender`,
// `apagar`, `activar`, `gesto`, `soltar`, `decir`, `callar`, `alCambiar`) y además `preparar(items)` (precarga),
// `motor()` ('clonada' o 'navegador') y `nivel()` (cuánto suena ahora, de 0 a 1): quien la usa no sabe cuál de las
// dos habla.
//
// * El audio lo pide `pedir(ref, {signal, alEvento})` (la vista lo arma con `flujo('/api/agente/voz', ref, …)` de
//   api.js, en voz-panel.js): POST /api/agente/voz responde en flujo NDJSON con `inicio` (el formato), `audio` (un
//   trozo en base64, unos 200 ms de PCM de 16 bits a 24 kHz, mono, mientras Mnemo lo genera) y `fin` (con lo que tardó
//   el primer audio) o `error` (`{codigo, mensaje}`). Lo que impide hablar llega antes del flujo: `pedir` lanza un
//   error con `codigo` (el `ErrorApi` de api.js). El navegador nunca manda un texto: pide por referencia (`ref`), y el
//   servidor saca el texto de lo que él mismo generó: `{rid, n, frase}` o `{rid, cierre: true}` (la narración del plan
//   guardado), `{conversacion, texto, firma}` (una frase de una respuesta, con la firma que le puso el servidor) o
//   `{prueba: true}` (la frase fija de Ajustes). Sin `ref` (o con una de otra forma), habla la voz del navegador.
// * El PCM se agenda con Web Audio a medida que llega: cada trozo es un `AudioBufferSourceNode` que empieza donde
//   termina el anterior, con un colchón de BUFER_S antes del primero (y otra vez si se quedó sin audio a mitad). No hace
//   falta tocar la CSP del panel (sin `<audio>` ni `blob:`) y el `AnalyserNode` de la salida da el nivel para la boca
//   del presentador. Si Mnemo no pudo dar PCM (`formato` mp3 o wav), se junta la frase entera y se decodifica de una
//   vez (`decodeAudioData`).
// * `decir(texto, {alEmpezar, ref, alFin})` resuelve 'dicha' (sonó entera), 'cortada' (`callar`, otra frase) o 'fallo'
//   y nunca lanza, como voz.js. `alEmpezar` corre cuando el primer trozo suena de verdad (no cuando llega). Si en
//   PRIMER_AUDIO_MS no hay audio sonando (la prueba de Ajustes espera PRIMER_AUDIO_PRUEBA_MS y nunca va con la voz del
//   navegador: mide la voz clonada), o la petición falla antes de sonar, la frase se dice con `respaldo.decir` y
//   resuelve lo que ese resuelva: el reproductor no se entera (la sala nunca queda muda por Mnemo). La petición de una
//   narración que llegó tarde sigue llegando y queda guardada: si la frase se repite (una pausa, «Repetir»), suena ya.
//   Un flujo que ya sonó y se queda ESTANCADO_MS sin traer nada se da por cortado: suena lo que llegó y resuelve
//   'fallo' (el reproductor espera lo que le falte a la lectura). `alFin` recibe, al terminar el intento con la voz
//   clonada, `{ms_primer_audio, ms_mnemo, cache, bytes}` o `{error: {codigo, mensaje}}` (Ajustes lo muestra al probar).
// * 409 `sin_voz` o 403 `voz_rol` (el panel no tiene voz clonada para esta persona: sin voz elegida, sin permiso, otra
//   cuenta, Mnemo no puede) pasan la voz al navegador para el resto de la sesión (`motor()` dice 'navegador', avisa con
//   `alCambiar` y llama `alCaer(codigo)`); cualquier otro error (`plan_vencido`, `frecuencia`, `mnemo_red`…) solo cambia
//   esa frase.
// * `preparar([{texto, ref}])` precarga lo que viene (la frase siguiente, la primera del paso siguiente o el resumen):
//   cuando le toque, empieza ya. A la vez se piden como mucho A_LA_VEZ frases (las del servidor: la que suena y la
//   siguiente); la que se va a decir ahora pasa delante y, si hace falta, suelta la precarga que ya no se quiere (se
//   saltó a otra parte). `callar` no tira lo de la narración (una pausa repite la frase al instante, sin volver a
//   pedirla); lo de una respuesta y la prueba sí (no se repiten). Se guardan como mucho MAX_GUARDADAS frases y
//   MAX_BYTES, y sale primero lo que se usó hace más. Nada se guarda fuera de la memoria de esta página.
// * `activar()` y `gesto()` destraban el audio en el gesto de la persona (un clic, una tecla): `resume()` del
//   AudioContext, un búfer mudo de una muestra (iOS no suelta el audio sin algo que suene en el gesto) y
//   `respaldo.activar()`. El AudioContext se crea recién cuando hay voz clonada que usar: una ventana sin ella no abre
//   audio. Safari puede negarse a reanudarlo con el gesto dado en la presentación (un iframe de otro origen): entonces
//   la voz del navegador sigue hablando (`estado()` es 'activa' si cualquiera de las dos puede sonar).
// * La preferencia (encendida o apagada) es la de voz.js (`yj_voz`): `encender` y `apagar` cambian las dos.
// Sin dependencias del panel ni del DOM: la ventana (`AudioContext`, `atob`, los oyentes del gesto), `pedir`,
// `respaldo`, `almacen`, `reloj` y `disponible()` (¿el panel ofrece la voz clonada ahora?, `voz.disponible` de GET
// /api/agente/estado) llegan por parámetro (admin/tests/test_voz_clonada.py la prueba con Node, un AudioContext y un
// reloj falsos).

export const CLAVE = 'yj_voz';                 // la preferencia de voz.js (una prueba compara las dos)
export const PRIMER_AUDIO_MS = 4000;           // sin audio sonando en esto, la frase va con la voz del navegador
export const PRIMER_AUDIO_PRUEBA_MS = 20000;   // la prueba de Ajustes espera más: mide lo que tarde, aunque tarde
export const BUFER_S = 0.15;                   // el colchón antes del primer trozo (y tras quedarse sin audio)
export const ESTANCADO_MS = 8000;              // un flujo que ya sonó y no trae nada en esto se da por cortado
export const A_LA_VEZ = 2;                     // frases pedidas a la vez (`A_LA_VEZ_PERSONA` de app/agente/voz.py)
export const MAX_GUARDADAS = 8;                // frases en memoria (precargadas o ya dichas)
export const MAX_BYTES = 24 * 1024 * 1024;     // lo que ocupan
export const MAX_FRASE = 10 * 1024 * 1024;     // el audio de una frase (`MAX_AUDIO` del servidor)
export const MUESTREO = 24000;                 // el PCM que se le pide a Mnemo
export const SIN_VOZ = ['sin_voz', 'voz_rol']; // con estos, el resto de la sesión con la voz del navegador
const ESPERA_AUDIO_MS = 300;                   // lo que se espera a que el audio de la ventana arranque (resume)
const VIGILA_MS = 1000;
const MARGEN_FIN_MS = 60;
const MAX_ESCENAS = 12;                        // los rangos de `VozIn` (app/api/agente.py): una referencia de otra
const MAX_FRASES = 3;                          // forma no se pide (sería un 422)
const MAX_TEXTO = 400;
const ID_MAX = 10 ** 12;
const RID = /^[0-9a-f]{12}$/;
const FIRMA = /^[A-Za-z0-9_-]{43}$/;
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;
const CANCELADA = { codigo: 'cancelada', mensaje: 'Se canceló.' };

const relojDelNavegador = {
  ahora: () => (globalThis.performance?.now ? globalThis.performance.now() : Date.now()),
  programar: (f, ms) => setTimeout(f, ms),
  cancelar: (h) => clearTimeout(h),
};
// Sin respaldo (la prueba de Ajustes, una ventana sin síntesis): no habla y no rompe nada
const SIN_RESPALDO = { estado: () => 'sin_voces', decir: async () => 'fallo', callar() {}, activar() {}, gesto() {},
  encender() {}, apagar() {}, soltar() {}, alCambiar: () => () => {} };

const entero = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;

/** La referencia de lo que se dice, copiada con la forma exacta que acepta POST /api/agente/voz, o null. */
export function refValida(ref) {
  if (!ref || typeof ref !== 'object' || Array.isArray(ref)) return null;
  const claves = Object.keys(ref).sort().join(',');
  const rid = typeof ref.rid === 'string' && RID.test(ref.rid);
  if (claves === 'frase,n,rid' && rid && entero(ref.n, 1, MAX_ESCENAS) && entero(ref.frase, 0, MAX_FRASES - 1)) {
    return { rid: ref.rid, n: ref.n, frase: ref.frase };
  }
  if (claves === 'cierre,rid' && rid && ref.cierre === true) return { rid: ref.rid, cierre: true };
  if (claves === 'conversacion,firma,texto' && entero(ref.conversacion, 1, ID_MAX) && typeof ref.texto === 'string'
    && ref.texto.trim() && [...ref.texto].length <= MAX_TEXTO && typeof ref.firma === 'string' && FIRMA.test(ref.firma)) {
    return { conversacion: ref.conversacion, texto: ref.texto, firma: ref.firma };
  }
  if (claves === 'prueba' && ref.prueba === true) return { prueba: true };
  return null;
}

/** 'narracion', 'respuesta' o 'prueba' (de una referencia ya válida). */
export const tipoDe = (r) => (r.prueba ? 'prueba' : r.conversacion ? 'respuesta' : 'narracion');
const claveDe = (r) => JSON.stringify(r.prueba ? ['p'] : r.conversacion ? ['r', r.conversacion, r.firma, r.texto]
  : r.cierre ? ['c', r.rid] : ['n', r.rid, r.n, r.frase]);
const textoDe = (v, max) => (typeof v === 'string' ? v.slice(0, max) : '');

/** El error de `pedir` (un ErrorApi de api.js, o cualquier cosa) como {codigo, mensaje}. */
function errorDe(e) {
  const codigo = textoDe(e?.codigo, 40) || (Number.isInteger(e?.estado) && e.estado ? `http_${e.estado}` : 'red');
  return { codigo, mensaje: textoDe(e?.message, 300) || 'La voz clonada no respondió.' };
}

export function crearVozClonada({ ventana = globalThis, pedir = null, respaldo = null, almacen = null,
  reloj = relojDelNavegador, disponible = () => true, alCaer = () => {} } = {}) {
  let AC = null;
  try { AC = ventana?.AudioContext || ventana?.webkitAudioContext || null; } catch { AC = null; }
  const hayAudio = typeof AC === 'function' && typeof pedir === 'function';
  const otra = respaldo || SIN_RESPALDO;
  const Control = ventana?.AbortController || globalThis.AbortController;
  const atob = typeof ventana?.atob === 'function' ? (s) => ventana.atob(s) : (s) => globalThis.atob(s);
  try { almacen ??= ventana?.localStorage ?? null; } catch { almacen = null; }
  let guardado = null;
  try { guardado = almacen?.getItem(CLAVE) ?? null; } catch { guardado = null; }
  let preferida = guardado !== '0';   // encendida por omisión, como voz.js
  let caida = null;        // el código con que el panel dijo que esta sesión no tiene voz clonada (SIN_VOZ)
  let soltada = false;
  let ctx = null, salida = null, analizador = null, muestras = null;
  let ficha = 0;
  let actual = null;       // la frase en curso: {ficha, resolver, sonido}
  let enUso = null;        // la entrada de la frase en curso (no se suelta para hacer lugar)
  let orden = 0;
  const entradas = new Map();   // clave → entrada; la usada va al final (sale primero la del comienzo)
  const queridas = { narracion: [], respuesta: [], prueba: [] };   // lo último que se precargó, por tipo
  const oyentes = new Set();

  const avisar = () => { const e = estado(); for (const f of oyentes) { try { f(e); } catch { /* el oyente se fue */ } } };
  const corriendo = () => !!ctx && ctx.state === 'running';

  /** 'clonada' si el panel ofrece la voz clonada ahora y este navegador la puede sonar; si no, 'navegador'. */
  function motor() {
    if (!hayAudio || caida || soltada) return 'navegador';
    let d = false;
    try { d = disponible() === true; } catch { d = false; }
    return d ? 'clonada' : 'navegador';
  }

  /** 'activa' | 'apagada' | 'sin_activar' | 'sin_voces', como voz.js. Con la voz clonada no hay 'sin_voces': está
   * activa si el audio de la ventana corre o si la voz del navegador puede hablar (el respaldo de cada frase). */
  function estado() {
    if (motor() !== 'clonada') return otra.estado();
    if (!preferida) return 'apagada';
    return corriendo() || otra.estado() === 'activa' ? 'activa' : 'sin_activar';
  }

  function guardar(v) {
    preferida = v;
    try { almacen?.setItem(CLAVE, v ? '1' : '0'); } catch { /* sin almacenamiento: dura lo que la página */ }
  }

  // El audio de la ventana: la salida (ganancia → medidor → parlantes), creada la primera vez que hace falta
  function asegurarAudio() {
    if (ctx && ctx.state !== 'closed') return ctx;
    if (!hayAudio || soltada) return null;
    try {
      ctx = new AC();
      salida = ctx.createGain();
      analizador = typeof ctx.createAnalyser === 'function' ? ctx.createAnalyser() : null;
      if (analizador) {
        analizador.fftSize = 1024;
        muestras = new Uint8Array(analizador.fftSize);
        salida.connect(analizador);
        analizador.connect(ctx.destination);
      } else salida.connect(ctx.destination);
      try { ctx.addEventListener?.('statechange', avisar); } catch { /* sin el evento */ }
    } catch {
      ctx = salida = analizador = muestras = null;
    }
    return ctx;
  }

  /** En el gesto de la persona: reanuda el audio de la ventana y suena un búfer mudo (iOS lo pide). */
  function despertarAudio() {
    const c = asegurarAudio();
    if (!c) return null;
    let p = null;
    try { p = c.resume?.(); } catch { p = null; }
    try {
      const b = c.createBuffer(1, 1, c.sampleRate || MUESTREO);
      const s = c.createBufferSource();
      s.buffer = b;
      s.connect(c.destination);
      s.start(0);
    } catch { /* nada */ }
    return Promise.resolve(p).then(() => avisar(), () => avisar());
  }

  /** Destraba las dos voces: hay que llamarla desde un gesto de la persona (un clic, una tecla). */
  function activar() {
    try { otra.activar?.(); } catch { /* nada */ }
    if (motor() === 'clonada') despertarAudio();
    avisar();
  }

  function encender() {
    guardar(true);
    try { otra.encender?.(); } catch { /* nada */ }
    activar();
  }

  function apagar() {
    guardar(false);
    try { otra.apagar?.(); } catch { /* nada */ }
    callar();
    avisar();
  }

  /** Un gesto de la persona (aquí o en la presentación, que la vista reenvía): con la preferencia encendida, activa lo
   * que falte. */
  function gesto() {
    if (!preferida || soltada) return;
    try { otra.gesto?.(); } catch { /* nada */ }
    if (motor() === 'clonada' && !corriendo()) { despertarAudio(); avisar(); }
  }

  // ── Las frases pedidas (precargadas o en curso) ──
  function nuevaEntrada(r) {
    return { clave: claveDe(r), ref: r, tipo: tipoDe(r), estado: 'esperando', control: null, formato: null,
      muestreo: MUESTREO, canales: 1, cache: false, trozos: [], bytes: 0, ultimo: 0, error: null, medida: null,
      audio: null, orden: ++orden, oyentes: new Set() };
  }
  const avisarEntrada = (x) => { for (const f of [...x.oyentes]) { try { f(); } catch { /* nada */ } } };
  const esQuerida = (x) => queridas[x.tipo].includes(x.clave);

  function caer(codigo) {
    if (caida) return;
    caida = codigo;
    // lo que se estaba pidiendo va a responder lo mismo: se suelta (la prueba de Ajustes, no)
    for (const x of [...entradas.values()]) if (x !== enUso && x.tipo !== 'prueba') quitar(x);
    try { alCaer(codigo); } catch { /* nada */ }
    avisar();
  }

  function fallar(x, error) {
    if (x.estado === 'fallo') return;
    x.estado = 'fallo';
    x.error = error;
    const c = x.control;
    x.control = null;
    try { c?.abort(); } catch { /* nada */ }
    if (entradas.get(x.clave) === x) entradas.delete(x.clave);   // la próxima vez se pide de nuevo
    if (SIN_VOZ.includes(error.codigo) && x.tipo !== 'prueba') caer(error.codigo);
    avisarEntrada(x);
  }

  /** Saca una entrada de la memoria (y corta su petición si sigue en camino). */
  function quitar(x) {
    if (entradas.get(x.clave) === x) entradas.delete(x.clave);
    if (x.estado === 'esperando' || x.estado === 'pidiendo') fallar(x, { ...CANCELADA });
    if (x !== enUso) { x.trozos = []; x.audio = null; x.bytes = 0; }
  }

  function deBase64(s) {
    if (typeof s !== 'string' || !s || s.length % 4 || !BASE64.test(s)) return null;
    try {
      const b = atob(s);
      const u = new Uint8Array(b.length);
      for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
      return u;
    } catch { return null; }
  }

  function recibir(x, ev) {
    if (x.estado !== 'pidiendo' || !ev || typeof ev !== 'object') return;
    if (ev.tipo === 'inicio') {
      x.formato = ev.formato === 'pcm_s16le' ? 'pcm' : textoDe(ev.formato, 20) || 'desconocido';
      x.muestreo = entero(ev.muestreo, 8000, 192000) ? ev.muestreo : MUESTREO;
      x.canales = ev.canales === 2 ? 2 : 1;
      x.cache = ev.cache === true;
    } else if (ev.tipo === 'audio') {
      const b = deBase64(ev.datos);
      if (!b?.length) return;
      if (x.formato === null) x.formato = 'pcm';
      if (x.bytes + b.length > MAX_FRASE) { fallar(x, { codigo: 'grande', mensaje: 'El audio de la frase es demasiado largo.' }); return; }
      x.trozos.push(b);
      x.bytes += b.length;
      x.ultimo = reloj.ahora();
    } else if (ev.tipo === 'fin') {
      if (!x.trozos.length) { fallar(x, { codigo: 'sin_audio', mensaje: 'La voz clonada no mandó audio.' }); return; }
      x.estado = 'lista';
      x.control = null;
      x.medida = { ms_primer_audio: entero(ev.ms_primer_audio, 0, 600000) ? ev.ms_primer_audio : null,
        ms_mnemo: entero(ev.ms_mnemo, 0, 600000) ? ev.ms_mnemo : null, cache: x.cache, bytes: x.bytes };
      recortar();
    } else if (ev.tipo === 'error') {
      fallar(x, { codigo: textoDe(ev.codigo, 40) || 'mnemo', mensaje: textoDe(ev.mensaje, 300) || 'La voz clonada falló.' });
      return;
    } else return;   // `latido` y lo que todavía no se conoce
    avisarEntrada(x);
  }

  function pedirEntrada(x) {
    x.estado = 'pidiendo';
    const control = typeof Control === 'function' ? new Control() : null;
    x.control = control;
    let p;
    try { p = Promise.resolve(pedir(x.ref, { signal: control?.signal ?? null, alEvento: (ev) => recibir(x, ev) })); } catch (e) { p = Promise.reject(e); }
    p.then((cerro) => {
      if (x.estado === 'pidiendo') {
        fallar(x, cerro === false ? { ...CANCELADA } : { codigo: 'cortado', mensaje: 'Se cortó la voz clonada antes de terminar la frase.' });
      }
    }, (e) => { if (x.estado === 'pidiendo') fallar(x, errorDe(e)); }).then(bombear, bombear);
  }

  /** Empieza lo que espera, hasta A_LA_VEZ: primero la frase en curso, después lo precargado en orden. */
  function bombear() {
    if (soltada) return;
    const todas = [...entradas.values()];
    let pidiendo = todas.filter((x) => x.estado === 'pidiendo').length;
    const esperan = todas.filter((x) => x.estado === 'esperando')
      .sort((a, b) => Number(b === enUso) - Number(a === enUso) || a.orden - b.orden);
    for (const x of esperan) {
      if (pidiendo >= A_LA_VEZ) break;
      pedirEntrada(x);
      pidiendo++;
    }
  }

  /** La frase en curso necesita un lugar: suelta una precarga en camino (la que ya no se quiere, si no la última). */
  function hacerLugar() {
    const otras = [...entradas.values()].filter((x) => x.estado === 'pidiendo' && x !== enUso);
    if (otras.length < A_LA_VEZ) return;
    const sobra = otras.sort((a, b) => Number(esQuerida(a)) - Number(esQuerida(b)) || b.orden - a.orden)[0];
    if (sobra) quitar(sobra);
  }

  /** Lo que no entra en memoria sale: lo usado hace más primero, nunca la frase en curso ni una precarga en camino. */
  function recortar() {
    let total = 0;
    for (const x of entradas.values()) total += x.bytes;
    for (const x of [...entradas.values()]) {
      if (entradas.size <= MAX_GUARDADAS && total <= MAX_BYTES) break;
      if (x === enUso || (x.estado === 'pidiendo' && esQuerida(x))) continue;
      total -= x.bytes;
      quitar(x);
    }
  }

  /** La entrada de `r` (la que hay, que pasa al final, o una nueva). Una que falló se vuelve a pedir. */
  function entrada(r) {
    const k = claveDe(r);
    let x = entradas.get(k);
    if (x) { entradas.delete(k); entradas.set(k, x); } else { x = nuevaEntrada(r); entradas.set(k, x); }
    return x;
  }

  /** Precarga lo que viene ([{texto, ref}]): cuando le toque, empieza ya. Lo del mismo tipo que se estaba pidiendo y
   * ya no viene (se saltó a otra parte) deja el lugar. Solo con la voz clonada encendida y su audio andando: si no,
   * la frase la diría la voz del navegador y lo pedido se gastaría en nada. */
  function preparar(items) {
    if (soltada || motor() !== 'clonada' || estado() !== 'activa' || !corriendo()) return;
    const refs = (Array.isArray(items) ? items : [items]).map((it) => refValida(it?.ref))
      .filter((r) => r && !r.prueba).slice(0, A_LA_VEZ);
    const porTipo = new Map();
    for (const r of refs) porTipo.set(tipoDe(r), [...(porTipo.get(tipoDe(r)) || []), claveDe(r)]);
    for (const [t, claves] of porTipo) {
      queridas[t] = claves;
      for (const x of [...entradas.values()]) {
        if (x.tipo === t && x !== enUso && x.estado === 'pidiendo' && !claves.includes(x.clave)) quitar(x);
      }
    }
    for (const r of refs) { const x = entrada(r); if (x.estado === 'esperando') x.orden = ++orden; }
    bombear();
    recortar();
  }

  // ── Lo que suena ──
  function pararSonido(s) {
    if (!s || s.cerrado) return;
    s.cerrado = true;
    for (const h of s.relojes) reloj.cancelar(h);
    s.relojes.clear();
    s.e.oyentes.delete(s.mirar);
    for (const f of s.fuentes) {
      f.onended = null;
      try { f.stop(); } catch { /* ya terminó */ }
      try { f.disconnect(); } catch { /* nada */ }
    }
    s.fuentes.clear();
  }

  /** Reproduce la entrada `e` para la frase `a`. op: {alEmpezar, alFin, fin(res), respaldar(error)}. */
  function sonar(e, a, op) {
    const s = { e, cerrado: false, fuentes: new Set(), relojes: new Set(), i: 0, resto: null, agendado: false,
      empezo: false, inicio: 0, cursor: 0, final: false, decodificando: false, mirar: null };
    a.sonido = s;
    const vigente = () => actual === a && a.sonido === s && !s.cerrado;
    const programar = (f, ms) => {
      const h = reloj.programar(() => { s.relojes.delete(h); f(); }, Math.max(0, ms));
      h?.unref?.();
      s.relojes.add(h);
    };
    const avisarFin = (d) => { try { op.alFin?.(d); } catch { /* nada */ } };
    // No llegó a sonar: la frase va con la voz del navegador. La narración que sigue llegando queda guardada (si se
    // repite, suena ya); lo de una respuesta o la prueba, no
    const antes = (error) => {
      if (!vigente()) return;
      pararSonido(s);
      if (e.tipo !== 'narracion') quitar(e);
      avisarFin({ error });
      op.respaldar(error);
    };

    function agendar(buf, duracion) {
      const ahora = ctx.currentTime;
      if (!s.agendado) { s.inicio = ahora + BUFER_S; s.cursor = s.inicio; }
      else if (s.cursor < ahora + 0.02) s.cursor = ahora + BUFER_S;   // se quedó sin audio: otro colchón
      const f = ctx.createBufferSource();
      f.buffer = buf;
      f.connect(salida);
      f.onended = () => { s.fuentes.delete(f); try { f.disconnect(); } catch { /* nada */ } };
      f.start(s.cursor);
      s.fuentes.add(f);
      s.cursor += duracion;
      if (s.agendado) return;
      s.agendado = true;
      // `alEmpezar` cuando suena de verdad: al terminar el colchón
      programar(() => {
        if (!vigente()) return;
        s.empezo = true;
        try { op.alEmpezar?.(); } catch { /* nada */ }
      }, (s.inicio - ahora) * 1000);
      vigilar();
    }

    // Un trozo de PCM de 16 bits, little endian (un byte suelto pasa al trozo siguiente)
    function agendarPcm(bytes) {
      let b = bytes;
      if (s.resto) { const u = new Uint8Array(s.resto.length + b.length); u.set(s.resto); u.set(b, s.resto.length); b = u; s.resto = null; }
      const canales = e.canales === 2 ? 2 : 1;
      const paso = 2 * canales;
      const marcos = Math.floor(b.length / paso);
      if (b.length > marcos * paso) s.resto = b.slice(marcos * paso);
      if (!marcos) return;
      const buf = ctx.createBuffer(canales, marcos, e.muestreo);
      for (let c = 0; c < canales; c++) {
        const datos = buf.getChannelData(c);
        for (let i = 0; i < marcos; i++) {
          const j = (i * canales + c) * 2;
          let v = b[j] | (b[j + 1] << 8);
          if (v >= 0x8000) v -= 0x10000;
          datos[i] = v / 32768;
        }
      }
      agendar(buf, marcos / e.muestreo);
    }

    // MP3, WAV (Mnemo no pudo dar PCM): la frase entera, decodificada una vez (queda en la entrada para repetirla)
    function agendarEntera() {
      if (e.audio) { agendar(e.audio, e.audio.duration); terminarAlFinal(); return; }
      if (s.decodificando) return;
      s.decodificando = true;
      const todo = new Uint8Array(e.bytes);
      let k = 0;
      for (const t of e.trozos) { todo.set(t, k); k += t.length; }
      new Promise((ok, mal) => {
        const p = ctx.decodeAudioData(todo.buffer, ok, mal);
        if (p && typeof p.then === 'function') p.then(ok, mal);
      }).then((buf) => {
        e.audio = buf;
        if (!vigente()) return;
        agendar(buf, buf.duration);
        terminarAlFinal();
      }, () => antes({ codigo: 'audio', mensaje: 'Este navegador no pudo leer el audio de la voz clonada.' }));
    }

    function terminarAlFinal(resultado = 'dicha') {
      if (s.final) return;
      s.final = true;
      avisarFin(resultado === 'dicha' ? { ...e.medida } : { error: e.error });
      programar(() => op.fin(resultado), (s.cursor - ctx.currentTime) * 1000 + MARGEN_FIN_MS);
    }

    // Un flujo que ya sonó y se quedó sin traer nada: se corta (suena lo que llegó)
    function vigilar() {
      programar(() => {
        if (!vigente() || e.estado !== 'pidiendo') return;
        if (reloj.ahora() - e.ultimo >= ESTANCADO_MS) fallar(e, { codigo: 'callado', mensaje: 'La voz clonada dejó de llegar.' });
        else vigilar();
      }, VIGILA_MS);
    }

    s.mirar = () => {
      if (!vigente()) return;
      if (e.formato && e.formato !== 'pcm') {
        if (e.estado === 'lista') agendarEntera();
        else if (e.estado === 'fallo') antes(e.error);
        return;
      }
      while (s.i < e.trozos.length) agendarPcm(e.trozos[s.i++]);
      if (e.estado === 'fallo') {
        if (!s.agendado) antes(e.error);
        else terminarAlFinal('fallo');   // sonó una parte: termina eso y resuelve 'fallo'
      } else if (e.estado === 'lista' && s.agendado) terminarAlFinal();
      else if (e.estado === 'lista') antes({ codigo: 'sin_audio', mensaje: 'La voz clonada no mandó audio.' });
    };
    e.oyentes.add(s.mirar);
    programar(() => { if (vigente() && !s.agendado) antes({ codigo: 'plazo', mensaje: 'La voz clonada tardó demasiado.' }); },
      e.tipo === 'prueba' ? PRIMER_AUDIO_PRUEBA_MS : PRIMER_AUDIO_MS);
    s.mirar();
    return s;
  }

  // ── decir y callar ──
  function parar() {
    ficha++;
    const a = actual;
    actual = null;
    enUso = null;
    if (a) { pararSonido(a.sonido); a.resolver('cortada'); }
    try { otra.callar?.(); } catch { /* nada */ }
  }

  /** Calla en el acto. Lo precargado de la narración se queda (una pausa repite la frase al instante); lo de una
   * respuesta o de la prueba, no. */
  function callar() {
    parar();
    for (const x of [...entradas.values()]) if (x.tipo !== 'narracion') quitar(x);
    queridas.respuesta = [];
    queridas.prueba = [];
  }

  /** Dice `texto` (una frase). Con `ref` y la voz clonada, con ella; si no llega, con la del navegador. `alEmpezar`
   * corre cuando empieza a sonar de verdad. La prueba de Ajustes (`ref: {prueba: true}`) suena con la voz clonada
   * aunque la persona no la use (es el administrador probándola) y nunca con la del navegador. */
  function decir(texto, { alEmpezar, ref, alFin } = {}) {
    const r = refValida(ref);
    const prueba = r?.prueba === true;
    if (soltada || (!prueba && estado() !== 'activa')) return Promise.resolve('fallo');
    parar();
    const mia = ++ficha;
    return new Promise((resolver) => {
      const a = { ficha: mia, resolver, sonido: null };
      actual = a;
      const vigente = () => actual === a;
      const fin = (res) => {
        if (!vigente()) return;
        pararSonido(a.sonido);
        actual = null;
        // lo de una respuesta o de la prueba ya se dijo: no se repite
        if (enUso && enUso.tipo !== 'narracion') quitar(enUso);
        enUso = null;
        resolver(res);
      };
      const respaldar = () => {
        if (!vigente()) return;
        a.sonido = null;
        if (prueba) { fin('fallo'); return; }
        let p;
        try { p = otra.decir(texto, { alEmpezar }); } catch { fin('fallo'); return; }
        Promise.resolve(p).then((x) => fin(x === 'dicha' || x === 'cortada' ? x : 'fallo'), () => fin('fallo'));
      };
      if (!r || !hayAudio || !(prueba || motor() === 'clonada')) {
        if (prueba) { try { alFin?.({ error: { codigo: 'sin_audio', mensaje: 'Este navegador no puede reproducir la voz clonada.' } }); } catch { /* nada */ } }
        respaldar();
        return;
      }
      // La petición sale ya (también mientras el audio de la ventana arranca). Una que falló ya no está: se pide otra
      const x = entrada(r);
      enUso = x;
      if (x.estado === 'esperando') hacerLugar();
      bombear();
      recortar();
      const empezar = () => {
        if (!vigente()) return;
        if (!corriendo()) {
          if (x.tipo !== 'narracion') quitar(x);
          try { alFin?.({ error: { codigo: 'sin_activar', mensaje: 'El audio de esta ventana no está activado: tóquela y vuelva a intentar.' } }); } catch { /* nada */ }
          respaldar();
          return;
        }
        sonar(x, a, { alEmpezar, alFin, fin, respaldar });
      };
      if (corriendo()) { empezar(); return; }
      // Sin el audio de la ventana andando (todavía no hubo gesto con la voz clonada; la prueba, en su clic): se
      // intenta ahora, un momento
      const listo = despertarAudio() || Promise.resolve();
      let hecho = false;
      const una = () => { if (!hecho) { hecho = true; empezar(); } };
      listo.then(una, una);
      const h = reloj.programar(una, ESPERA_AUDIO_MS);
      h?.unref?.();
    });
  }

  /** Cuánto suena ahora la voz clonada (de 0 a 1, del medidor de la salida): la boca del presentador. 0 con la voz del
   * navegador (no da su audio). */
  function nivel() {
    if (!analizador || !muestras || !corriendo() || !actual?.sonido?.empezo) return 0;
    try { analizador.getByteTimeDomainData(muestras); } catch { return 0; }
    let s = 0;
    for (let i = 0; i < muestras.length; i++) { const x = (muestras[i] - 128) / 128; s += x * x; }
    return Math.min(1, Math.sqrt(Math.sqrt(s / muestras.length) / 0.3));
  }

  // Lo que cambia en la voz del navegador (cargó sus voces, se activó) cambia el estado de esta
  let quitarRespaldo = null;
  try { quitarRespaldo = otra.alCambiar?.(() => avisar()) || null; } catch { quitarRespaldo = null; }
  // El primer toque o tecla en esta ventana; y si ya la tocaron antes de crearla, el navegador lo dice
  if (hayAudio) {
    try {
      ventana.addEventListener?.('pointerdown', gesto, true);
      ventana.addEventListener?.('keydown', gesto, true);
    } catch { /* nada */ }
    let tocada = false;
    try { tocada = ventana.navigator?.userActivation?.hasBeenActive === true; } catch { tocada = false; }
    if (tocada) gesto();
  }

  /** Se deja de usar: sin oyentes de la ventana, callada, sin nada en memoria y con el audio de la ventana cerrado. */
  function soltar() {
    if (soltada) return;
    callar();
    soltada = true;
    try {
      ventana?.removeEventListener?.('pointerdown', gesto, true);
      ventana?.removeEventListener?.('keydown', gesto, true);
    } catch { /* nada */ }
    for (const x of [...entradas.values()]) quitar(x);
    entradas.clear();
    try { quitarRespaldo?.(); } catch { /* nada */ }
    try { otra.soltar?.(); } catch { /* nada */ }
    try { ctx?.removeEventListener?.('statechange', avisar); } catch { /* nada */ }
    try { Promise.resolve(ctx?.close?.()).catch(() => {}); } catch { /* nada */ }
    ctx = salida = analizador = muestras = null;
  }

  return {
    estado, encender, apagar, activar, gesto, soltar, decir, callar,
    alCambiar(f) { oyentes.add(f); return () => oyentes.delete(f); },
    preparar, motor, nivel,
  };
}
