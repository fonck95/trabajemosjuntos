// El reproductor del recorrido narrado: lleva el reloj de la explicación (docs/agente.md, «Recorridos narrados»).
//
// El asistente arma en una sola llamada un recorrido de escenas (app/recorrido.py lo valida y lo deja absoluto: cada
// escena trae su paso, lo visual, lo que se resalta y la narración en frases). Este módulo lo reproduce en la página
// que enmarca la presentación (la pestaña del chat, la ventana del proyector o la pantalla en off), con órdenes a
// mando.js: la escena (atómica: responde cuando la imagen se asentó), la frase que suena, la pausa y el cierre. Así la
// sala ve primero lo que se nombra y después lo oye o lo lee, frase por frase, al ritmo de la voz si está encendida o
// de un tiempo de lectura si no.
//
// * Ciclo de una escena: «preparando» (la orden `escena`, hasta ESPERA_ESCENA_MS) → RESPIRO_MS → «narrando» (cada
//   frase se ilumina cuando empieza a sonar; sin voz, cuando aparece, y se queda su tiempo de lectura) → «sosteniendo»
//   (sostener_ms: la sala mira) → la siguiente. Al final, el cierre: «En resumen» con los puntos, «¿Preguntas?» y la
//   narración se quita; la imagen queda donde terminó.
// * Las esperas se pueden pausar y guardan lo que les falta. Miden con `reloj.ahora()` y dan ticks de TICK_MS como
//   mucho: una pestaña oculta, cuyos relojes el navegador espacia, no adelanta ni atrasa el ritmo.
// * Pausa dura (un botón, la tecla p, la persona movió la maqueta): calla en el acto. Al seguir, la frase en curso se
//   repite desde el comienzo (no hay pause() de la síntesis: en Android y Safari corta); si la persona había movido la
//   imagen, la escena vuelve a aplicarse, también si la movió con la pausa ya puesta. Pausa suave (la persona escribe en
//   el chat): entra al terminar la frase. El resumen del cierre es una frase más: la pausa suave lo deja terminar y una
//   pausa en medio lo repite.
// * Siguiente, anterior, repetir y detener cortan lo que suena y saltan. Cada salto sube la generación: las
//   continuaciones viejas se descartan solas. Un recorrido nuevo reemplaza al que suena, y el viejo termina para los
//   suyos (la tarjeta del chat, la barra, el servidor) con «detenido» por «reemplazo»: si no, su tarjeta seguiría
//   sonando y los controles y la pausa al escribir irían a un rid muerto.
// * Una escena que falla se salta (aviso); dos seguidas, o una presentación que no responde, detienen con «error».
// * `avisar(progreso)` corre en cada cambio de fase y de frase: la vista lo manda al puente (la tarjeta del chat), a su
//   barra y al servidor (POST /api/pantalla/progreso: el asistente y los agentes por MCP lo leen en `estado`).
// Lógica pura: `orden`, `voz`, `reloj` y `avisar` llegan por parámetro (admin/tests lo prueba con Node y un reloj falso).

export const RESPIRO_MS = 350;
export const ENTRE_FRASES_MS = 250;
export const CIERRE_SOSTENER_MS = 4000;
export const PREGUNTAS_MS = 12000;
export const ESPERA_ESCENA_MS = 25000;
export const MAX_FALLAS = 2;
export const TICK_MS = 250;
export const DETENER_ESPERA_MS = 1000;
export const FASES = ['preparando', 'narrando', 'sosteniendo', 'cierre', 'pausa', 'fin', 'detenido', 'error'];
export const TERMINALES = ['fin', 'detenido', 'error'];
export const CONTROLES = ['pausar', 'continuar', 'siguiente', 'anterior', 'repetir', 'detener'];

/** Lo que tarda en leerse un texto (`recorrido.lectura_ms` del servidor: la duración estimada sale de lo mismo). */
export const lecturaMs = (t) => Math.min(16000, Math.max(3200, 1500 + 62 * [...String(t)].length));

const relojDelNavegador = {
  ahora: () => (globalThis.performance?.now ? performance.now() : Date.now()),
  programar: (f, ms) => setTimeout(f, ms),
  cancelar: (h) => clearTimeout(h),
};
const sinVoz = { estado: () => 'sin_voces', decir: async () => 'fallo', callar: () => {} };

/**
 * orden(o, {plazo}) → Promise<{ok, error?, aviso?, sinRespuesta?}>: manda una orden a mando.js.
 * voz: {estado(), decir(texto, {alEmpezar}) → 'dicha'|'cortada'|'fallo', callar()} (voz.js).
 * avisar(progreso): {rid, n, de, fase, frase, voz, motivo?, aviso?, t_ms}.
 */
export function crearReproductor({ orden, voz = sinVoz, reloj = relojDelNavegador, avisar = () => {} } = {}) {
  let r = null;            // el recorrido que suena
  let n = 0;               // la escena (1..de; de + 1 es el cierre)
  let fase = null;
  let frase = 0;
  let gen = 0;             // sube con cada salto, detención o reemplazo
  let pausado = false;
  let suave = false;       // pausa pedida al terminar la frase
  let enFrase = false;     // una frase suena (o se está leyendo): la pausa suave espera a que termine
  let motivoPausa = null;
  let faseAntes = null;    // la fase que la pausa interrumpió
  let fallas = 0;
  let t0 = 0;
  let enVuelo = null;      // la orden en curso (detener la espera, hasta DETENER_ESPERA_MS)
  let narrando = false;    // hay una narración en pantalla (a la que se le puede mandar pausa o frase)
  let mandoEscena = false; // ya salió una orden `escena`: al terminar hay que dejarla atrás aunque no haya respondido
  let alPrimera = null;    // resuelve la promesa de `iniciar` cuando la primera escena está a la vista (o falló)
  const despiertos = new Set();   // las esperas en curso: se despiertan al seguir o saltar
  const despertar = () => { for (const f of [...despiertos]) f(); };
  const oyentes = new Set();

  const de = () => r?.escenas.length || 0;
  const vigente = (g) => g === gen && !!r;

  function emitir(extra = {}) {
    if (!r) return;
    const p = { rid: r.id, n: Math.min(Math.max(n, 1), de()), de: de(), fase, frase, voz: voz.estado(),
      t_ms: Math.min(600000, Math.max(0, Math.round(reloj.ahora() - t0))), ...extra };
    try { avisar(p); } catch { /* el oyente se fue */ }
    for (const f of oyentes) { try { f(p); } catch { /* nada */ } }
  }

  async function mandar(o, opciones) {
    const p = Promise.resolve().then(() => orden(o, opciones)).catch((e) => ({ ok: false, error: String(e?.message || e) }));
    enVuelo = p;
    const res = await p;
    if (enVuelo === p) enVuelo = null;
    return res || { ok: false };
  }

  // Una espera que se puede pausar: `ms` de reloj corrido mientras no hay pausa. false si la generación cambió
  function esperar(ms, g, { pausable = true } = {}) {
    return new Promise((listo) => {
      let falta = ms;
      let antes = reloj.ahora();
      let h = null;
      const salir = (v) => { despiertos.delete(despierta); listo(v); };
      const mirar = () => {
        h = null;
        if (!vigente(g)) { salir(false); return; }
        const ahora = reloj.ahora();
        if (!(pausable && pausado)) falta -= ahora - antes;
        antes = ahora;
        // una pausa suave pedida fuera de una frase entra en el acto
        if (pausable && suave && !pausado && !enFrase) entrarEnPausa(motivoPausa || 'mensaje');
        if (falta <= 0) { salir(true); return; }
        h = reloj.programar(mirar, Math.min(TICK_MS, Math.max(1, falta)));
      };
      const despierta = () => { if (h !== null) { reloj.cancelar(h); mirar(); } };
      despiertos.add(despierta);
      mirar();
    });
  }

  // Espera hasta que no haya pausa (la generación puede cambiar mientras tanto)
  async function hastaSeguir(g) {
    while (vigente(g) && pausado) await esperar(TICK_MS, g, { pausable: false });
    return vigente(g);
  }

  function entrarEnPausa(motivo) {
    if (!r || pausado || TERMINALES.includes(fase)) return;
    pausado = true;
    suave = false;
    motivoPausa = motivo;
    faseAntes = fase;
    voz.callar();
    if (narrando) mandar({ orden: 'narracion', pausa: true });
    fase = 'pausa';
    emitir({ motivo });
  }

  // true si terminó; false si ya no era el vigente, o si mientras se quitaba la narración llegó otro recorrido o un
  // salto (lo nuevo manda: este no pisa su fase ni su primera escena)
  async function terminar(g, f, motivo, { quitar = true } = {}) {
    if (!vigente(g)) return false;
    const mia = ++gen;
    voz.callar();
    pausado = false;
    suave = false;
    // también con la primera escena en vuelo: si no, al asentarse narraría y dejaría tomado el teclado de la presentación
    if (quitar && (narrando || mandoEscena)) await mandar({ orden: 'quitar_explicacion' });
    if (mia !== gen) return false;
    narrando = false;
    mandoEscena = false;
    fase = f;
    emitir(motivo ? { motivo } : {});
    despertar();
    alPrimera?.(false);
    alPrimera = null;
    return true;
  }

  // Una frase (de una escena o el resumen del cierre): con voz, `mostrar` corre cuando empieza a sonar; sin voz (o si la
  // voz no arrancó), corre antes y la frase se queda su tiempo de lectura. Una pausa en medio la repite desde el
  // comienzo; la pausa suave espera a que termine (`enFrase`). `alIntentar` corre al comienzo de cada intento
  async function decirFrase(g, texto, { alIntentar = () => {}, mostrar = async () => {} } = {}) {
    enFrase = true;
    try { return await decirFraseYa(g, texto, alIntentar, mostrar); } finally { enFrase = false; }
  }
  async function decirFraseYa(g, texto, alIntentar, mostrar) {
    for (;;) {
      if (!await hastaSeguir(g)) return false;
      alIntentar();
      if (voz.estado() !== 'activa') {
        await mostrar();
        if (!vigente(g)) return false;
        return esperar(lecturaMs(texto), g);
      }
      let empezo = null;   // cuándo empezó a sonar (reloj.ahora())
      const res = await voz.decir(texto, { alEmpezar: () => {
        if (!vigente(g)) return;
        empezo = reloj.ahora();
        mostrar();
        emitir();
      } });
      if (!vigente(g)) return false;
      if (pausado) continue;
      if (res === 'dicha') return true;
      let falta = lecturaMs(texto);
      if (empezo === null) {
        // no llegó a sonar: la voz no pudo (el aviso, para el asistente) y la frase se lee
        if (res === 'fallo') emitir({ aviso: 'voz' });
        await mostrar();
        emitir();
      } else {
        // sonó y no terminó (el vigía venció: Chrome perdió el fin o cortó una locución larga; o un error a mitad): ya
        // estuvo a la vista desde que empezó, así que solo lo que le falte de su lectura. No es un aviso de voz: habló
        falta = Math.max(0, falta - (reloj.ahora() - empezo));
      }
      const ok = await esperar(falta, g);
      if (!vigente(g)) return false;
      if (ok) return true;
    }
  }

  async function aplicarEscena(g, k) {
    const esc = r.escenas[k - 1];
    // con la pausa ya puesta (pedida mientras arrancaba), sigue en pausa: «preparando» es a donde vuelve al continuar
    if (pausado) faseAntes = 'preparando'; else fase = 'preparando';
    frase = 0;
    emitir();
    mandoEscena = true;
    const res = await mandar({ orden: 'escena', capitulo: esc.capitulo, paso: esc.paso, panel: esc.panel,
      visual: esc.visual, resaltar: esc.resaltar, frases: esc.frases, titulo: r.titulo, n: k, de: de(),
      voz: voz.estado() === 'activa', rid: r.id }, { plazo: ESPERA_ESCENA_MS });
    if (!vigente(g)) return null;
    return res;
  }

  async function jugar(g, desde) {
    for (n = desde; n <= de(); n++) {
      if (!await hastaSeguir(g)) return;
      const esc = r.escenas[n - 1];
      const res = await aplicarEscena(g, n);
      // una escena de una generación vieja no resuelve la primera: con un reemplazo, `alPrimera` ya es la del nuevo
      if (!vigente(g)) return;
      alPrimera?.(!!res?.ok);
      alPrimera = null;
      if (!res?.ok) {
        fallas++;
        if (res?.sinRespuesta || fallas >= MAX_FALLAS) {
          await terminar(g, 'error', res?.sinRespuesta ? 'sin_respuesta' : 'escena_fallida', { quitar: narrando });
          return;
        }
        emitir({ motivo: 'escena_fallida' });
        continue;
      }
      fallas = 0;
      narrando = true;
      // la pausa llegó mientras la imagen cambiaba: la narración nueva también se ve en pausa
      if (pausado) mandar({ orden: 'narracion', pausa: true });
      if (res.aviso) emitir({ aviso: res.aviso });
      if (!await esperar(RESPIRO_MS, g)) return;
      for (let k = 0; k < esc.frases.length; k++) {
        const alIntentar = () => { fase = 'narrando'; frase = k; emitir(); };
        const mostrar = () => mandar({ orden: 'narracion', frase: k });
        if (!await decirFrase(g, esc.frases[k], { alIntentar, mostrar })) return;
        if (suave) entrarEnPausa(motivoPausa || 'mensaje');
        if (k < esc.frases.length - 1 && !await esperar(ENTRE_FRASES_MS, g)) return;
      }
      if (!await hastaSeguir(g)) return;
      fase = 'sosteniendo';
      emitir();
      if (!await esperar(esc.sostener_ms, g)) return;
    }
    await cerrar(g);
  }

  async function cerrar(g) {
    n = de() + 1;
    if (!await hastaSeguir(g)) return;
    fase = 'cierre';
    frase = 0;
    emitir();
    if (r.cierre) {
      await mandar({ orden: 'cierre', puntos: r.cierre.puntos, rid: r.id });
      if (!vigente(g)) return;
      // el resumen se dice como una frase (los puntos ya están a la vista): la persona que escribe en el chat lo deja
      // terminar, y una pausa en medio lo repite al seguir
      if (!await decirFrase(g, `En resumen. ${r.cierre.puntos.join('. ')}`)) return;
      if (suave) entrarEnPausa(motivoPausa || 'mensaje');
      if (!await esperar(CIERRE_SOSTENER_MS, g)) return;
    }
    await mandar({ orden: 'cierre', puntos: null, rid: r.id });
    if (!vigente(g)) return;
    if (!await esperar(PREGUNTAS_MS, g)) return;
    await terminar(g, 'fin');
  }

  function saltar(k) {
    if (!r) return;
    gen++;
    voz.callar();
    pausado = false;
    suave = false;
    fallas = 0;
    despertar();
    const g = gen;
    if (k > de()) cerrar(g).catch(() => {});
    else jugar(g, Math.max(1, k)).catch(() => {});
  }

  const activo = () => !!r && !!fase && !TERMINALES.includes(fase);

  return {
    /** Arranca `rec` (ya validado) desde la escena `desde`; un recorrido que suena se reemplaza. Resuelve cuando la
     * primera escena está a la vista (true) o no se pudo (false). */
    iniciar(rec, { desde = 1 } = {}) {
      if (activo()) {
        // lo que sonaba se corta aquí (no en el salto): así sus continuaciones ya no pueden emitir con el recorrido nuevo
        gen++;
        voz.callar();
        pausado = false;
        suave = false;
        despertar();
        // otro recorrido: el viejo termina para su tarjeta, la barra y el servidor. El mismo (otra vez, desde una
        // escena) sigue en la misma tarjeta: no hay nada que cerrar
        if (rec?.id !== r.id) { fase = 'detenido'; emitir({ motivo: 'reemplazo' }); }
      }
      alPrimera?.(false);
      const primera = new Promise((ok) => { alPrimera = ok; });
      r = rec;
      n = 0;
      fase = 'preparando';
      t0 = reloj.ahora();
      narrando = false;
      mandoEscena = false;
      motivoPausa = null;
      saltar(Math.min(Math.max(1, desde | 0), de()));
      return primera;
    },
    /** `suave`: entra al terminar la frase en curso (la persona escribe en el chat). */
    pausar(motivo = 'boton', { suave: s = false } = {}) {
      if (!activo() || pausado) return false;
      if (s && enFrase) { suave = true; motivoPausa = motivo; return true; }
      entrarEnPausa(motivo);
      return true;
    },
    continuar() {
      if (!activo() || (!pausado && !suave)) return false;
      suave = false;
      if (!pausado) return true;
      // la persona había movido la imagen: la escena vuelve a aplicarse y se narra desde el comienzo
      if (motivoPausa === 'persona' && n <= de()) { saltar(n); return true; }
      pausado = false;
      if (narrando) mandar({ orden: 'narracion', pausa: false });
      fase = faseAntes || 'narrando';
      emitir();
      despertar();
      return true;
    },
    alternar(motivo = 'boton') { return pausado || suave ? this.continuar() : this.pausar(motivo); },
    siguiente() { if (!activo()) return false; if (n > de()) { terminar(gen, 'fin'); return true; } saltar(n + 1); return true; },
    anterior() { if (!activo()) return false; saltar(Math.max(1, Math.min(n, de() + 1) - 1)); return true; },
    repetir() { if (!activo()) return false; saltar(Math.min(n, de())); return true; },
    /** Detiene y quita la narración; espera la orden en vuelo hasta DETENER_ESPERA_MS. */
    async detener(motivo = 'boton') {
      if (!activo()) return false;
      const g = ++gen;   // lo que estaba en curso se descarta
      voz.callar();
      despertar();
      const vuelo = enVuelo;
      if (vuelo) {
        await Promise.race([vuelo, new Promise((ok) => { const h = reloj.programar(ok, DETENER_ESPERA_MS); h?.unref?.(); })]);
      }
      if (g !== gen) return false;   // mientras tanto llegó otro recorrido o un salto
      return terminar(g, 'detenido', motivo);
    },
    /** Un control por nombre (CONTROLES). La pausa suave solo la pide el chat cuando la persona escribe: su motivo es
     * 'mensaje' (la tarjeta lo dice y el asistente sabe que, al responder, sigue). */
    control(accion, { suave: s = false } = {}) {
      if (accion === 'pausar') return this.pausar(s ? 'mensaje' : 'boton', { suave: s });
      if (accion === 'continuar') return this.continuar();
      if (accion === 'siguiente') return this.siguiente();
      if (accion === 'anterior') return this.anterior();
      if (accion === 'repetir') return this.repetir();
      if (accion === 'detener') { this.detener('boton'); return true; }
      return false;
    },
    /** La persona movió la imagen (un paso, la cámara): pausa dura; al seguir, la escena vuelve. Con la pausa ya puesta
     * (un botón, una tecla, el chat), su motivo pasa a 'persona': si no, al seguir se narraría sobre otra imagen. */
    alPersona() {
      if (!activo()) return false;
      if (!pausado) return this.pausar('persona');
      if (motivoPausa !== 'persona') { motivoPausa = 'persona'; emitir({ motivo: 'persona' }); }
      return true;
    },
    activo,
    pausado: () => pausado,
    recorrido: () => r,
    /** {rid, n, de, fase, frase, pausado} o null */
    estado: () => (r ? { rid: r.id, n: Math.min(Math.max(n, 1), de()), de: de(), fase, frase, pausado } : null),
    alProgreso(f) { oyentes.add(f); return () => oyentes.delete(f); },
  };
}
