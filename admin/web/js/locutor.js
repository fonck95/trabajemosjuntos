// Las respuestas habladas del asistente (docs/agente.md, «Respuestas habladas»): agente.js le pasa al locutor las
// frases que arma el servidor mientras el modelo escribe (el evento `frase` del turno: `{n, texto, firma}`, ya
// firmadas para esta persona y esta conversación) y el locutor las dice en orden con la voz de la ventana
// (voz-panel.js: la voz clonada de Mnemo, con la del navegador de respaldo de cada frase).
//
// * En orden de `n` (desde 0): una frase que llega antes de su turno espera a la anterior; mientras una suena, la que
//   sigue se precarga (`voz.preparar`). Cada una se pide por su referencia `{conversacion, texto, firma}`: el
//   navegador no puede pedirle a la voz otra cosa que lo que el servidor firmó.
// * `frases_descartar` (`descartar(desde)`): las frases desde `desde` ya no valen (el servidor repitió la ronda, o el
//   texto final no era el que se venía leyendo) y las que lleguen se numeran otra vez desde ahí. Se quitan de la cola;
//   la que suena, si es una de ellas, se corta y se dice su versión nueva. Lo que ya se dijo entero no se repite.
// * `frases_ronda` (`ronda(desde)`): la ronda rehecha terminó y la siguiente empieza en `desde`. Si la versión nueva
//   fue más corta que lo que ya se había dicho, lo que se saltaba por número es de la ronda siguiente, que nunca se
//   oyó: desde ahí se vuelve a decir.
// * Se calla (`callar`: el resto del turno ya no se dice) cuando la persona toca el micrófono, escribe, envía otro
//   mensaje, pulsa «Detener» o Escape, cierra el panel, cambia de conversación o apaga «Leer respuestas», y cuando el
//   turno pone un plan en la presentación. La narración manda: si la voz la toma un plan (`decir` resuelve 'cortada'
//   sin que se haya pedido), el resto del turno se calla; y mientras suena un plan (`ocupada()`: uno que no está en
//   pausa), la frase espera, hasta ESPERA_NARRACION_MS: la persona que escribe en medio de un plan lo pausa al terminar
//   la frase que suena (y quien pregunta por voz, en el acto), y entonces la respuesta se oye. Si el plan sigue sonando
//   pasado ese tiempo, el turno se calla.
// * Una frase que no se pudo decir ('fallo': ni la voz clonada ni la del navegador) se salta: sigue la siguiente.
// * La respuesta inmediata (docs/agente.md, «La respuesta inmediata»: el evento `adelanto` y sus frases
//   `adelanto_frase`, numeradas desde 0 aparte) tiene su propia cola, que va primero: la respuesta espera a que se
//   diga entera y a que termine (`adelanto_fin`; con `vacio`, no hubo nada que decir y la respuesta sigue en el acto).
//   El servidor manda ese `vacio` antes del primer texto de la respuesta cuando la inmediata no alcanzó a mostrar nada,
//   así que sin un `adelanto` antes la respuesta no espera nada. Si de la inmediata no se sabe nada en
//   ESPERA_ADELANTO_MS (no llega ni suena nada suyo), la respuesta deja de esperarla y lo que llegue tarde no se dice.
//   `callarRespuesta` calla la respuesta y deja terminar la inmediata (el turno puso un plan en la presentación de esta
//   ventana: su primer paso espera a que termine, reproductor.js); `callar` calla las dos. Cada frase de la inmediata
//   va a la voz con `adelanto: true` (voz-panel.js: un plan en su espera previa le cede el turno).
// `alHablar(true | false)`: empezó o terminó de hablar (agente.js marca el mensaje que se oye). `alAdelanto(true |
// false)`: la respuesta inmediata empezó a sonar (o está por sonar: empezó a llegar) o terminó (agente.js se lo dice a la
// voz de la ventana, y el plan nuevo la espera). `ocupada({adelanto})`: ¿suena un plan que esta frase debe esperar?
// Sin DOM ni red: la voz, `ocupada` y el reloj llegan por parámetro (admin/tests/test_voz_clonada.py lo prueba con
// Node, una voz y un reloj falsos).

export const MAX_TEXTO = 400;   // una frase (`VozIn.texto` de app/api/agente.py)
export const ESPERA_NARRACION_MS = 20000;   // lo que una frase espera a que el plan que suena se pause o termine
export const ESPERA_ADELANTO_MS = 8000;     // sin saber nada de la respuesta inmediata en esto, la respuesta ya no la espera
const MIRAR_MS = 300;
const FIRMA = /^[A-Za-z0-9_-]{43}$/;
const MAX_N = 10000;

const relojDelNavegador = {
  ahora: () => (globalThis.performance?.now ? globalThis.performance.now() : Date.now()),
  programar: (f, ms) => setTimeout(f, ms),
  cancelar: (h) => clearTimeout(h),
};

/** Un evento `frase` del turno ({n, texto, firma}) con la forma esperada, o null. */
export function fraseValida(ev) {
  if (!ev || typeof ev !== 'object') return null;
  const { n, texto, firma } = ev;
  if (!Number.isInteger(n) || n < 0 || n > MAX_N) return null;
  if (typeof texto !== 'string' || !texto.trim() || [...texto].length > MAX_TEXTO) return null;
  if (typeof firma !== 'string' || !FIRMA.test(firma)) return null;
  return { n, texto, firma };
}

export function crearLocutor({ voz, ocupada = () => false, alHablar = () => {}, alAdelanto = () => {},
  reloj = relojDelNavegador } = {}) {
  let turno = 0;          // sube con cada turno y cada callar: lo que resuelva tarde ya no cuenta
  let mudo = true;        // sin turno que leer (o callado)
  let conversacion = null;
  let diciendo = null;    // {n, turno, adelanto}: la que suena (de la respuesta inmediata o de la respuesta)
  let hablaba = false;
  let tEspera = null;     // la próxima mirada mientras suena un plan
  let esperaDesde = null;
  // La respuesta: sus frases (`frase`)
  let siguiente = 0;      // la próxima frase que toca decir
  const cola = new Map(); // n → {texto, ref}
  let respuestaMuda = false;   // `callarRespuesta`: lo que queda de la respuesta ya no se dice (la inmediata termina)
  // La respuesta inmediata: sus frases (`adelanto_frase`, numeradas aparte), que van antes
  let adelanto = 'no';    // 'no' (no empezó) | 'llegando' (empezó y no terminó) | 'fin' (terminó, o se dejó de esperar)
  let siguienteA = 0;
  const colaA = new Map();
  let noticiaA = 0;       // lo último que se supo de ella: llegó un trozo o una frase, o terminó de decirse una
  let tAdelanto = null;   // el plazo ESPERA_ADELANTO_MS
  let sonandoA = false;   // lo último que se avisó con `alAdelanto`

  const ocupadaYa = (deAdelanto) => { try { return ocupada({ adelanto: deAdelanto }) === true; } catch { return false; } };
  const avisar = (v) => { if (v === hablaba) return; hablaba = v; try { alHablar(v); } catch { /* nada */ } };
  /** ¿La respuesta inmediata suena o está por sonar? (empezó y no terminó, le quedan frases o dice una) */
  const vivaA = () => !mudo && (adelanto === 'llegando' || colaA.size > 0 || !!diciendo?.adelanto);
  function avisarAdelanto() {
    const v = vivaA();
    if (v === sonandoA) return;
    sonandoA = v;
    try { alAdelanto(v); } catch { /* nada */ }
  }

  /** Lo que se dice después de lo que suena: la frase siguiente de su cola o, terminada la respuesta inmediata, la
   * primera de la respuesta que espera. */
  function queSigue() {
    if (!diciendo) return null;
    if (!diciendo.adelanto) return cola.get(diciendo.n + 1) ?? null;
    return colaA.get(diciendo.n + 1) ?? (adelanto === 'fin' && !respuestaMuda ? cola.get(siguiente) ?? null : null);
  }
  const precargar = () => { const x = queSigue(); if (x) { try { voz.preparar?.([x]); } catch { /* nada */ } } };

  function hablar() {
    decirLoQueToca();
    avisarAdelanto();
  }

  function decirLoQueToca() {
    if (mudo || diciendo) return;
    // Primero la respuesta inmediata (una frase que no llegó, terminada ella, se salta)
    if (adelanto === 'fin' && colaA.size && !colaA.has(siguienteA)) siguienteA = Math.min(...colaA.keys());
    const a = colaA.get(siguienteA);
    if (a) { intentar(a, siguienteA, true); return; }
    if (adelanto === 'llegando') {
      // La respuesta espera a que termine la inmediata, mientras se sepa de ella
      const falta = ESPERA_ADELANTO_MS - (reloj.ahora() - noticiaA);
      if (falta > 0) {
        if (tAdelanto === null) tAdelanto = reloj.programar(() => { tAdelanto = null; hablar(); }, falta);
        avisar(false);
        return;
      }
      adelanto = 'fin';   // ya no se sabe de ella: no se la espera más (y lo que llegue tarde no se dice)
    }
    if (respuestaMuda) { callar(); return; }
    const x = cola.get(siguiente);
    if (!x) { avisar(false); return; }
    intentar(x, siguiente, false);
  }

  function intentar(x, n, deAdelanto) {
    if (ocupadaYa(deAdelanto)) {
      // suena un plan: se espera a que se pause o termine (sin cola de relojes: una mirada a la vez)
      esperaDesde ??= reloj.ahora();
      if (reloj.ahora() - esperaDesde >= ESPERA_NARRACION_MS) { callar(); return; }
      if (tEspera === null) tEspera = reloj.programar(() => { tEspera = null; hablar(); }, MIRAR_MS);
      return;
    }
    esperaDesde = null;
    (deAdelanto ? colaA : cola).delete(n);
    const t = turno;
    diciendo = { n, turno: t, adelanto: deAdelanto };
    avisar(true);
    let p;
    try { p = Promise.resolve(voz.decir(x.texto, { ref: x.ref, ...(deAdelanto ? { adelanto: true } : {}) })); } catch { p = Promise.resolve('fallo'); }
    precargar();
    p.then((r) => r, () => 'fallo').then((r) => {
      // se calló o se descartó mientras tanto
      if (t !== turno || diciendo?.n !== n || diciendo.adelanto !== deAdelanto) return;
      diciendo = null;
      // la voz la tomó otro (la narración de un plan): el resto del turno ya no se dice
      if (r === 'cortada') { callar(); return; }
      if (deAdelanto) { siguienteA = n + 1; noticiaA = reloj.ahora(); } else siguiente = n + 1;
      hablar();
    });
  }

  /** Un turno nuevo que se lee en voz alta, en la conversación `cid` (puede llegar después, con `conversacion`). */
  function empezar(cid = null) {
    callar();
    mudo = false;
    conversacion = Number.isInteger(cid) && cid > 0 ? cid : null;
  }

  /** La conversación del turno (el evento `inicio` la trae en una conversación nueva). */
  function fijarConversacion(cid) {
    if (Number.isInteger(cid) && cid > 0) conversacion = cid;
  }

  const item = (f) => ({ texto: f.texto, ref: { conversacion, texto: f.texto, firma: f.firma } });

  /** Un evento `frase`: a la cola, y se dice cuando le toque (después de la respuesta inmediata, si hay una). */
  function frase(ev) {
    const f = fraseValida(ev);
    if (!f || mudo || respuestaMuda || !conversacion || f.n < siguiente || (diciendo && !diciendo.adelanto && f.n === diciendo.n)) {
      return false;
    }
    const x = item(f);
    cola.set(f.n, x);
    if (diciendo && queSigue() === x) precargar();
    hablar();
    return true;
  }

  /** Un trozo de la respuesta inmediata (el evento `adelanto`): empezó, y la respuesta la espera. */
  function empiezaAdelanto() {
    if (mudo || adelanto === 'fin') return;
    adelanto = 'llegando';
    noticiaA = reloj.ahora();
    hablar();
  }

  /** Un evento `adelanto_frase`: a su cola, que va antes que la de la respuesta. */
  function fraseAdelanto(ev) {
    const f = fraseValida(ev);
    if (!f || mudo || !conversacion || adelanto === 'fin' || f.n < siguienteA || (diciendo?.adelanto && f.n === diciendo.n)) {
      return false;
    }
    adelanto = 'llegando';
    noticiaA = reloj.ahora();
    const x = item(f);
    colaA.set(f.n, x);
    if (diciendo && queSigue() === x) precargar();
    hablar();
    return true;
  }

  /** `adelanto_fin`: la respuesta inmediata terminó (con `vacio`, sin mostrar nada: no hay nada que decir). Lo que le
   * quede por decir se dice, y después la respuesta. */
  function terminaAdelanto(vacio = false) {
    if (mudo) return;
    adelanto = 'fin';
    if (tAdelanto !== null) { reloj.cancelar(tAdelanto); tAdelanto = null; }
    if (vacio === true) colaA.clear();
    if (diciendo?.adelanto) precargar();   // lo que sigue a la que suena puede ser ya la respuesta
    hablar();
  }

  /** `frases_descartar`: las frases de la respuesta desde `desde` ya no valen. */
  function descartar(desde) {
    if (!Number.isInteger(desde) || desde < 0 || mudo) return;
    for (const n of [...cola.keys()]) if (n >= desde) cola.delete(n);
    if (diciendo && !diciendo.adelanto && diciendo.n >= desde) {
      // la que suena ya no vale: se corta y se dice su versión nueva cuando llegue
      siguiente = diciendo.n;
      diciendo = null;
      turno++;
      try { voz.callar(); } catch { /* nada */ }
    }
    hablar();
  }

  /** `frases_ronda`: la ronda siguiente empieza en `desde`. Lo ya dicho de la ronda rehecha se saltaba por número; lo
   * que siga desde `desde` es nuevo y se dice. */
  function ronda(desde) {
    if (!Number.isInteger(desde) || desde < 0 || mudo || (diciendo && !diciendo.adelanto)) return;
    if (siguiente > desde) siguiente = desde;
    hablar();
  }

  /** Calla la respuesta (lo que queda de ella ya no se dice) y deja terminar la respuesta inmediata: un plan va a
   * narrar en esta ventana y su primer paso la espera (reproductor.js). Sin respuesta inmediata por terminar, es
   * `callar`. */
  function callarRespuesta() {
    if (mudo) return;
    if (!vivaA()) { callar(); return; }
    respuestaMuda = true;
    cola.clear();
    if (diciendo && !diciendo.adelanto) {
      turno++;
      diciendo = null;
      try { voz.callar(); } catch { /* nada */ }
    }
    hablar();
  }

  /** Calla en el acto las dos: lo que queda del turno ya no se dice. */
  function callar() {
    const habia = !mudo || !!diciendo || cola.size > 0 || colaA.size > 0;
    turno++;
    mudo = true;
    cola.clear();
    colaA.clear();
    siguiente = 0;
    siguienteA = 0;
    adelanto = 'no';
    respuestaMuda = false;
    if (tEspera !== null) { reloj.cancelar(tEspera); tEspera = null; }
    if (tAdelanto !== null) { reloj.cancelar(tAdelanto); tAdelanto = null; }
    esperaDesde = null;
    const d = diciendo;
    diciendo = null;
    if (habia || d) { try { voz.callar(); } catch { /* nada */ } }
    avisar(false);
    avisarAdelanto();
  }

  return {
    empezar, fijarConversacion, frase, descartar, ronda, callar, callarRespuesta,
    empiezaAdelanto, fraseAdelanto, terminaAdelanto,
    /** ¿Está diciendo una frase ahora? */
    hablando: () => !!diciendo,
    /** ¿Lee este turno (aunque ahora espere la frase siguiente)? */
    activo: () => !mudo,
    /** ¿La respuesta inmediata suena o está por sonar? (lo que avisa `alAdelanto`) */
    adelantoVivo: () => sonandoA,
  };
}
