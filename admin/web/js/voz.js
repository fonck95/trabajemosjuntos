// La voz del recorrido narrado (reproductor.js): la síntesis del navegador (Web Speech), opcional y apagada por omisión.
// Lo que se ve no depende de ella: sin voz, cada frase se queda en pantalla su tiempo de lectura.
//
// * Suena solo donde mira la sala (la pestaña del chat, la ventana del proyector o la pantalla en off) y solo después de
//   un gesto de la persona en ESA ventana: el navegador no deja hablar a una página que nadie tocó. `encender` corre en
//   el clic del botón «Voz» (destraba la síntesis con una locución vacía); si la preferencia ya estaba encendida, el
//   primer toque o tecla en la ventana la activa. En el proyector esos toques y teclas caen en el iframe de la
//   presentación, que ocupa la ventana, y no llegan aquí: mando.js los avisa y la vista llama a `gesto()` (la activación
//   de la persona en el iframe vale también para la ventana que lo contiene).
// * `soltar()` al desmontar la vista: quita los oyentes de la ventana y de la síntesis y calla (si no, cada montaje
//   sumaría los suyos).
// * La preferencia se guarda en este navegador (`yj_voz`); un almacenamiento bloqueado no rompe nada.
// * La voz: la mejor en español de las que tenga el equipo (es-CO; después es-419, es-MX, es-US; después es-ES; después
//   cualquier es-*), las locales antes que las remotas. Una voz remota manda el texto a un servicio del fabricante del
//   navegador: solo se usa si no hay ninguna local en español (y el texto proyectado nunca trae datos de personas).
// * `decir` habla una frase y resuelve 'dicha', 'cortada' (callar, una pausa) o 'fallo' (sin voz, un error, el vigía
//   vencido); nunca lanza. Chrome corta las locuciones largas cerca de los 15 s: una frase de más de PARTIR caracteres
//   se dice en partes de PARTIR como mucho (contadas sobre lo que se oye, que con las siglas y las unidades dichas crece).
//   La locución en curso se guarda: si nadie la retiene, Chrome la recoge y pierde su `onend`, y la frase queda colgada
//   hasta el vigía. `paraDecir` solo cambia lo que se oye (las siglas, las unidades), no lo que se ve.
// Sin dependencias del DOM del panel: la ventana y el almacén llegan por parámetro (admin/tests, con una síntesis falsa).

export const CLAVE = 'yj_voz';
export const PARTIR = 160;
const ESPERA_VOCES_MS = 1500;
const ORDEN_IDIOMAS = [['es-co'], ['es-419', 'es-mx', 'es-us'], ['es-es']];

// Lo que se dice distinto de como se escribe (tabla fija: solo el audio)
const TABLA = [
  [/(\d)\s*m²/g, '$1 metros cuadrados'], [/(\d)\s*m³/g, '$1 metros cúbicos'],
  [/(\d)\s*km\b/g, '$1 kilómetros'], [/(\d)\s*ha\b/g, '$1 hectáreas'], [/(\d)\s*m\b(?![²³])/g, '$1 metros'],
  [/(\d)\s*h\b/g, '$1 horas'], [/\s*%/g, ' por ciento'],
  [/\bNSR-10\b/g, 'ene ese erre diez'], [/\bRes\./g, 'Resolución'], [/\bE\.S\.E\./g, 'e ese e'],
  [/\bREPS\b/g, 'reps'], [/\bTPR\b/g, 'te pe erre'], [/\bBIM\b/g, 'bim'], [/\bIFC4\b/g, 'i efe ce cuatro'],
  [/\b((?:19|20)\d\d)\s*[–—-]\s*((?:19|20)\d\d)\b/g, '$1 a $2'],
  [/≈\s*/g, 'unos '], [/\s*→\s*/g, ' a '],
];

/** El texto como se dice (la pantalla muestra el original). */
export function paraDecir(t) {
  let s = String(t ?? '');
  for (const [re, por] of TABLA) s = s.replace(re, por);
  return s.replace(/\s+/g, ' ').trim();
}

/** Las partes en que se dice una frase: una, o varias de PARTIR caracteres como mucho. Se corta por la «, » o «; » más
 * cercana a la mitad solo si las dos mitades caben; si no, por el espacio más cercano a la mitad, y cada mitad que
 * todavía no cabe se vuelve a partir (una «, » pegada a un extremo dejaría la otra parte tan larga como la frase). */
export function partes(t) {
  const s = String(t ?? '');
  if ([...s].length <= PARTIR) return [s];
  const mitad = s.length / 2;
  const cabe = (x) => [...x.trim()].length <= PARTIR;
  // el corte (la posición donde empieza la segunda mitad) más cercano a la mitad entre los que `sirve` acepta
  const corte = (re, sirve) => {
    let mejor = -1;
    for (const m of s.matchAll(re)) {
      const c = m.index + 1;
      if (sirve(c) && (mejor < 0 || Math.abs(c - mitad) < Math.abs(mejor - mitad))) mejor = c;
    }
    return mejor;
  };
  let c = corte(/[,;] /g, (i) => cabe(s.slice(0, i)) && cabe(s.slice(i)));
  if (c < 0) c = corte(/\s/g, (i) => !!s.slice(0, i).trim() && !!s.slice(i).trim());
  // una sola palabra más larga que el tope: por la mitad, sin partir un carácter
  if (c < 0) { const cp = [...s]; c = cp.slice(0, Math.ceil(cp.length / 2)).join('').length; }
  return [s.slice(0, c), s.slice(c)].map((x) => x.trim()).filter(Boolean).flatMap(partes);
}

/** Lo que se espera a una locución antes de darla por colgada. */
export const vigia = (t) => Math.max(4000, Math.round(1.8 * 70 * [...t].length + 1500));

/** La mejor voz en español de `voces` (o null). */
export function elegirVoz(voces) {
  const es = (voces || []).filter((v) => typeof v?.lang === 'string' && /^es([-_]|$)/i.test(v.lang));
  if (!es.length) return null;
  const idioma = (v) => {
    const l = v.lang.toLowerCase().replace('_', '-');
    const i = ORDEN_IDIOMAS.findIndex((g) => g.includes(l));
    return i < 0 ? ORDEN_IDIOMAS.length : i;
  };
  const buena = (v) => (/natural|neural|google/i.test(v.name || '') ? 0 : 1);
  const locales = es.filter((v) => v.localService !== false);
  const lista = locales.length ? locales : es;
  return [...lista].sort((a, b) => idioma(a) - idioma(b) || buena(a) - buena(b))[0];
}

export function crearVoz({ ventana = globalThis, almacen = null } = {}) {
  const sintesis = ventana?.speechSynthesis;
  const Locucion = ventana?.SpeechSynthesisUtterance;
  const hay = !!sintesis && typeof Locucion === 'function';
  let guardado = null;
  try { almacen ??= ventana?.localStorage ?? null; } catch { almacen = null; }
  try { guardado = almacen?.getItem(CLAVE) === '1'; } catch { guardado = false; }
  let preferida = !!guardado;
  let activada = false;
  let voz = null;
  let vocesListas = false;
  const oyentes = new Set();
  let actual = null;   // {ficha, resolver, reloj, u}: la locución en curso (`u` la retiene: ver la cabecera)
  let ficha = 0;
  let alCambiarVoces = null;   // el oyente de `voiceschanged` y el reloj de la espera de las voces (`soltar` los quita)
  let tVoces = null;

  const avisar = () => { for (const f of oyentes) { try { f(estado()); } catch { /* el oyente se fue */ } } };

  function cargarVoces() {
    if (!hay) return;
    const mirar = () => {
      let lista = [];
      try { lista = sintesis.getVoices() || []; } catch { lista = []; }
      if (lista.length) { voz = elegirVoz(lista); vocesListas = true; avisar(); }
      return lista.length > 0;
    };
    if (mirar()) return;
    alCambiarVoces = () => { mirar(); };
    try { sintesis.addEventListener?.('voiceschanged', alCambiarVoces); } catch { /* sin el evento */ }
    // sin el evento (o si no llega): se da por cargada al rato, con lo que haya
    tVoces = setTimeout(() => { tVoces = null; mirar(); vocesListas = true; avisar(); }, ESPERA_VOCES_MS);
    tVoces?.unref?.();
  }

  /** 'activa' | 'apagada' | 'sin_activar' | 'sin_voces' */
  function estado() {
    if (!hay || (vocesListas && !voz)) return 'sin_voces';
    if (!preferida) return 'apagada';
    if (!activada) return 'sin_activar';
    return 'activa';
  }

  function guardar(v) {
    preferida = v;
    try { almacen?.setItem(CLAVE, v ? '1' : '0'); } catch { /* sin almacenamiento: dura lo que la página */ }
  }

  /** Destraba la síntesis: hay que llamarla desde un gesto de la persona (un clic, una tecla). */
  function activar() {
    if (!hay || activada) return;
    try {
      const u = new Locucion('');
      u.volume = 0;
      sintesis.speak(u);
      activada = true;
    } catch { activada = false; }
    avisar();
  }

  function encender() { guardar(true); activar(); avisar(); }
  function apagar() { guardar(false); callar(); avisar(); }

  function callar() {
    ficha++;
    const a = actual;
    actual = null;
    if (a) { clearTimeout(a.reloj); a.resolver('cortada'); }
    try { if (hay) sintesis.cancel(); } catch { /* nada */ }
  }

  /** Dice `texto` (una frase). `alEmpezar` corre cuando empieza a sonar de verdad. */
  function decir(texto, { alEmpezar } = {}) {
    if (estado() !== 'activa') return Promise.resolve('fallo');
    callar();
    const mia = ++ficha;
    const trozos = partes(paraDecir(texto));
    return new Promise((resolver) => {
      let empezo = false;
      const fin = (r) => {
        if (actual?.ficha !== mia) return;
        clearTimeout(actual.reloj);
        actual = null;
        if (r === 'fallo') { try { sintesis.cancel(); } catch { /* nada */ } }
        resolver(r);
      };
      actual = { ficha: mia, resolver, reloj: 0 };
      const hablar = (i) => {
        if (actual?.ficha !== mia) return;
        if (i >= trozos.length) { fin('dicha'); return; }
        let u;
        try {
          u = new Locucion(trozos[i]);
          if (voz) { u.voice = voz; u.lang = voz.lang; } else u.lang = 'es-CO';
          u.rate = 1;
          u.pitch = 1;
        } catch { fin('fallo'); return; }
        u.onstart = () => {
          if (actual?.ficha !== mia || empezo) return;
          empezo = true;
          try { alEmpezar?.(); } catch { /* nada */ }
        };
        u.onend = () => hablar(i + 1);
        u.onerror = (e) => {
          const err = e?.error;
          if (err === 'interrupted' || err === 'canceled') { fin('cortada'); return; }
          if (err === 'not-allowed') { activada = false; avisar(); }
          fin('fallo');
        };
        clearTimeout(actual.reloj);
        actual.u = u;
        actual.reloj = setTimeout(() => fin('fallo'), vigia(trozos[i]));
        actual.reloj?.unref?.();
        try { sintesis.speak(u); } catch { fin('fallo'); }
      };
      hablar(0);
    });
  }

  /** Un gesto de la persona (aquí o en la presentación, que la vista reenvía): con la preferencia encendida, la activa. */
  function gesto() { if (preferida && !activada) activar(); }

  // El primer toque o tecla en esta ventana
  if (hay) {
    cargarVoces();
    try {
      ventana.addEventListener?.('pointerdown', gesto, true);
      ventana.addEventListener?.('keydown', gesto, true);
    } catch { /* nada */ }
  }

  /** La vista se desmonta: sin oyentes de la ventana ni de la síntesis, y callada. */
  function soltar() {
    try {
      ventana?.removeEventListener?.('pointerdown', gesto, true);
      ventana?.removeEventListener?.('keydown', gesto, true);
    } catch { /* nada */ }
    if (alCambiarVoces) { try { sintesis.removeEventListener?.('voiceschanged', alCambiarVoces); } catch { /* nada */ } }
    alCambiarVoces = null;
    clearTimeout(tVoces);
    tVoces = null;
    callar();
  }

  return {
    estado, encender, apagar, activar, gesto, soltar, decir, callar,
    alCambiar(f) { oyentes.add(f); return () => oyentes.delete(f); },
  };
}
