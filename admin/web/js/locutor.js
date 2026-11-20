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
// `alHablar(true | false)`: empezó o terminó de hablar (agente.js marca el mensaje que se oye). Sin DOM ni red: la voz,
// `ocupada` y el reloj llegan por parámetro (admin/tests/test_voz_clonada.py lo prueba con Node, una voz y un reloj
// falsos).

export const MAX_TEXTO = 400;   // una frase (`VozIn.texto` de app/api/agente.py)
export const ESPERA_NARRACION_MS = 20000;   // lo que una frase espera a que el plan que suena se pause o termine
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

export function crearLocutor({ voz, ocupada = () => false, alHablar = () => {}, reloj = relojDelNavegador } = {}) {
  let turno = 0;          // sube con cada turno y cada callar: lo que resuelva tarde ya no cuenta
  let mudo = true;        // sin turno que leer (o callado)
  let conversacion = null;
  let siguiente = 0;      // la próxima frase que toca decir
  let diciendo = null;    // {n, turno}: la que suena
  const cola = new Map(); // n → {texto, ref}
  let hablaba = false;
  let tEspera = null;     // la próxima mirada mientras suena un plan
  let esperaDesde = null;

  const ocupadaYa = () => { try { return ocupada() === true; } catch { return false; } };
  const avisar = (v) => { if (v === hablaba) return; hablaba = v; try { alHablar(v); } catch { /* nada */ } };
  const precargar = (n) => { const x = cola.get(n); if (x) { try { voz.preparar?.([x]); } catch { /* nada */ } } };

  function hablar() {
    if (mudo || diciendo) return;
    const x = cola.get(siguiente);
    if (!x) { avisar(false); return; }
    if (ocupadaYa()) {
      // suena un plan: se espera a que se pause o termine (sin cola de relojes: una mirada a la vez)
      esperaDesde ??= reloj.ahora();
      if (reloj.ahora() - esperaDesde >= ESPERA_NARRACION_MS) { callar(); return; }
      if (tEspera === null) tEspera = reloj.programar(() => { tEspera = null; hablar(); }, MIRAR_MS);
      return;
    }
    esperaDesde = null;
    cola.delete(siguiente);
    const n = siguiente;
    const t = turno;
    diciendo = { n, turno: t };
    avisar(true);
    let p;
    try { p = Promise.resolve(voz.decir(x.texto, { ref: x.ref })); } catch { p = Promise.resolve('fallo'); }
    precargar(n + 1);
    p.then((r) => r, () => 'fallo').then((r) => {
      if (t !== turno || diciendo?.n !== n) return;   // se calló o se descartó mientras tanto
      diciendo = null;
      // la voz la tomó otro (la narración de un plan): el resto del turno ya no se dice
      if (r === 'cortada') { callar(); return; }
      siguiente = n + 1;
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

  /** Un evento `frase`: a la cola, y se dice cuando le toque. */
  function frase(ev) {
    const f = fraseValida(ev);
    if (!f || mudo || !conversacion || f.n < siguiente || (diciendo && f.n === diciendo.n)) return false;
    cola.set(f.n, { texto: f.texto, ref: { conversacion, texto: f.texto, firma: f.firma } });
    if (diciendo && f.n === diciendo.n + 1) precargar(f.n);
    hablar();
    return true;
  }

  /** `frases_descartar`: las frases desde `desde` ya no valen. */
  function descartar(desde) {
    if (!Number.isInteger(desde) || desde < 0 || mudo) return;
    for (const n of [...cola.keys()]) if (n >= desde) cola.delete(n);
    if (diciendo && diciendo.n >= desde) {
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
    if (!Number.isInteger(desde) || desde < 0 || mudo || diciendo) return;
    if (siguiente > desde) siguiente = desde;
    hablar();
  }

  /** Calla en el acto: lo que queda del turno ya no se dice. */
  function callar() {
    const habia = !mudo || !!diciendo || cola.size > 0;
    turno++;
    mudo = true;
    cola.clear();
    siguiente = 0;
    if (tEspera !== null) { reloj.cancelar(tEspera); tEspera = null; }
    esperaDesde = null;
    const d = diciendo;
    diciendo = null;
    if (habia || d) { try { voz.callar(); } catch { /* nada */ } }
    avisar(false);
  }

  return {
    empezar, fijarConversacion, frase, descartar, ronda, callar,
    /** ¿Está diciendo una frase ahora? */
    hablando: () => !!diciendo,
    /** ¿Lee este turno (aunque ahora espere la frase siguiente)? */
    activo: () => !mudo,
  };
}
