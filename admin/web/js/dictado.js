// Preguntas por voz al asistente (docs/agente.md, «Preguntas por voz»): la persona toca el micrófono, habla, y lo dicho
// llega como texto al cuadro de escribir (agente.js lo envía si el cuadro estaba vacío). Dos vías:
//
// 1. «servidor»: se graba con `getUserMedia` + `MediaRecorder` (opus a BITS: un minuto pesa menos de 200 kB) y, al
//    terminar, `transcribir(blob)` lo manda al panel (POST /api/agente/transcribir, que se lo pide a Mnemo). Un medidor
//    de nivel (`AnalyserNode`) dice cuánto suena y corta solo: a los SILENCIO_MS de silencio después de haber oído voz
//    y a los TOPE_MS como mucho. Si en SIN_VOZ_MS no oyó voz, termina sin mandar nada («vacío»: no se gasta una
//    transcripción en silencio), y descarta lo que dure menos de MINIMO_MS (un toque doble sin querer). Qué es voz: un
//    nivel por encima del ruido del lugar (el mínimo de los últimos segundos) durante dos medidas seguidas; el toque en
//    el botón, que suena en el micrófono, no cuenta. Sin medidor (un navegador sin AudioContext, o con el audio
//    suspendido) no hay corte solo: termina con otro toque o a los TOPE_MS.
// 2. «navegador»: el reconocimiento de voz del navegador (`SpeechRecognition`, en `es-CO`, con resultados parciales).
//    Se usa si el servidor no puede transcribir (`servidor` lo dice, o la transcripción respondió 409
//    `sin_transcriptor`) o si no hay `MediaRecorder`. Con ella el audio lo transcribe el servicio de voz del fabricante
//    del navegador: el texto de `textoDeEstado` lo dice. Corta sola (el servicio detecta el final de la frase) y a los
//    TOPE_MS. Hay navegadores que lo anuncian y no lo tienen (un Chromium sin el servicio de voz): si en SIN_ARRANQUE_MS
//    no empezó a oír ni dio un error, se da por no disponible (`sin_soporte`). Un 409 llega con la pregunta ya grabada, que el navegador no puede transcribir después: se pasa a esta
//    vía en el acto y se pide repetirla (`repetir`).
//
// Estados (`estado()` y `alEstado`): `inactivo`, `pidiendo` (el permiso), `escuchando` (con `nivel` de 0 a 1 y, en la
// vía 2, `parcial`), `transcribiendo` y `error` (con `motivo`: `permiso`, `sin_microfono`, `sin_soporte`, `vacio` o
// `fallo`, y a veces `mensaje`, el del panel). Todos llevan `via` cuando ya se eligió. `empezar()` arranca desde
// `inactivo` o `error`; `terminar()` cierra lo que se está oyendo y lo transcribe; `cancelar()` lo descarta todo (también
// una transcripción en camino, cuyo resultado ya no se entrega); `soltar()` cancela (avisa que quedó `inactivo`) y de
// ahí en adelante ni avisa ni arranca. El texto llega por `alTexto` justo antes de que el estado vuelva a `inactivo`.
//
// Nada del audio ni del texto se guarda aquí. El micrófono se suelta en cuanto se deja de oír (la marca de «grabando»
// del navegador se apaga). Sin dependencias del DOM del panel: la ventana, el reloj y `transcribir` llegan por
// parámetro (admin/tests lo prueba con Node y un MediaRecorder, un AnalyserNode y un SpeechRecognition falsos).

export const SILENCIO_MS = 1600;   // de silencio, después de haber oído voz: terminó de hablar
export const TOPE_MS = 60000;      // lo más que dura una pregunta
export const MINIMO_MS = 400;      // menos que esto no es una pregunta
export const SIN_VOZ_MS = 10000;   // sin haber oído voz en esto: nadie habló
export const SIN_ARRANQUE_MS = 15000; // el reconocimiento del navegador que no arranca en esto no va a arrancar
export const TICK_MS = 100;        // cada cuánto se mide el nivel
export const IDIOMA = 'es-CO';     // el del reconocimiento del navegador
export const MAX_TEXTO = 4000;     // el tope de un mensaje al asistente
const ARRANQUE_MS = 300;           // el toque en el botón suena en el micrófono: todavía no cuenta como voz
const VENTANA_PISO = 30;           // medidas (3 s) de las que sale el ruido del lugar
const SOBRE_PISO = 2.5;            // voz: tantas veces el ruido del lugar…
const UMBRAL_MIN = 0.012;          // …pero nunca menos que esto (un cuarto en silencio)
const UMBRAL_MAX = 0.08;           // …ni más que esto (quien habla sin pausas no se queda sin voz)
const SEGUIDAS = 2;                // medidas seguidas por encima del umbral (un golpe suelto no es voz)
const BITS = 24000;                // opus a 24 kbps: de sobra para transcribir, y un minuto cabe en 200 kB
const TROZO_MS = 250;
// Los contenedores que sabe leer el panel (`TIPOS` de app/agente/dictado.py), del mejor al último recurso
const TIPOS = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/ogg'];
// Los errores del reconocimiento del navegador (`SpeechRecognitionErrorEvent.error`)
const MOTIVO_RECONOCER = { 'not-allowed': 'permiso', 'service-not-allowed': 'permiso', 'audio-capture': 'sin_microfono',
  'no-speech': 'vacio' };

const relojDelNavegador = {
  ahora: () => (globalThis.performance?.now ? globalThis.performance.now() : Date.now()),
  programar: (f, ms) => setTimeout(f, ms),
  cancelar: (h) => clearTimeout(h),
};

/** Lo que este navegador puede hacer: `grabar` (la vía 1) y `reconocer` (la vía 2). Ninguna de las dos si la página
 * no es segura (http) o si su política de permisos le quita el micrófono. */
export function soporteDeDictado(ventana = globalThis) {
  const v = ventana || {};
  let permitido = true;
  try {
    const politica = v.document?.permissionsPolicy || v.document?.featurePolicy;
    if (politica && typeof politica.allowsFeature === 'function') permitido = politica.allowsFeature('microphone') !== false;
  } catch { /* sin política que consultar */ }
  if (!permitido || v.isSecureContext === false) return { grabar: false, reconocer: false };
  return {
    grabar: typeof v.navigator?.mediaDevices?.getUserMedia === 'function' && typeof v.MediaRecorder === 'function',
    reconocer: typeof (v.SpeechRecognition || v.webkitSpeechRecognition) === 'function',
  };
}

/** El texto transcrito, limpio: sin caracteres de control, con los espacios juntos y con el tope de un mensaje. */
export function limpiar(t) {
  if (typeof t !== 'string') return '';
  return [...t.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim()].slice(0, MAX_TEXTO).join('').trim();
}

const ERRORES = {
  permiso: 'El navegador no tiene permiso para usar el micrófono. Permítalo (en el candado de la barra de direcciones) '
    + 'y toque de nuevo el micrófono.',
  sin_microfono: 'No encontré un micrófono en este equipo.',
  sin_soporte: 'Este navegador no puede transcribir la voz aquí. Escriba su pregunta.',
  vacio: 'No oí nada. Toque el micrófono y hable.',
  fallo: 'No se pudo transcribir. Intente de nuevo o escriba su pregunta.',
};

/** Lo que se le dice a la persona en cada estado (una línea). En la vía 2 dice que transcribe el servicio del navegador. */
export function textoDeEstado(e) {
  switch (e?.estado) {
    case 'pidiendo': return 'Permita el micrófono para preguntar por voz…';
    case 'escuchando':
      if (e.via === 'navegador') {
        return `${e.repetir ? 'El panel no pudo transcribir esa grabación. Repita su pregunta: ahora' : 'Escuchando… Aquí'} `
          + 'la transcribe el servicio de voz de su navegador.';
      }
      return e.medidor === false ? 'Escuchando… Toque el micrófono para terminar.'
        : 'Escuchando… Termina sola cuando deje de hablar.';
    case 'transcribiendo': return 'Transcribiendo…';
    case 'error': return (typeof e.mensaje === 'string' && e.mensaje.trim()) || ERRORES[e.motivo] || ERRORES.fallo;
    default: return '';
  }
}

/**
 * El dictado de una pregunta.
 * `transcribir(blob, {signal, duracion_ms})` → el texto (o `{texto}`); si lanza un error con `codigo`
 * 'sin_transcriptor' (o `estado` 409), se pasa a la vía 2; cualquier otro queda en `error` con `motivo` «fallo» (y su
 * `mensaje`, si trae uno para la persona). `servidor`: ¿el panel puede transcribir? (un booleano o una función; es una
 * pista: sin reconocimiento en el navegador se intenta igual). `alEstado(estado)` en cada cambio (y en cada medida del
 * nivel); `alTexto(texto, {via})` con lo transcrito.
 */
export function crearDictado({ ventana = globalThis, transcribir = null, alEstado = () => {}, alTexto = () => {},
  servidor = true, reloj = relojDelNavegador } = {}) {
  let actual = { estado: 'inactivo' };
  let gen = 0;               // cambia con cada intento y con cada cancelación: lo que llegue tarde no cuenta
  let vivo = true;
  let sinServidor = false;   // el panel ya respondió que no puede transcribir: de aquí en adelante, la vía 2
  let cortar = null;         // lo que suelta el intento en curso (el micrófono, el medidor, el reconocimiento)
  let parar = null;          // lo que termina de oír en el intento en curso

  function poner(e) {
    actual = e;
    if (!vivo) return;
    try { alEstado({ ...e }); } catch (x) { console.error(x); }
  }
  const fallar = (motivo, extra = {}) => poner({ estado: 'error', motivo, ...extra });
  // El texto llega antes de volver a `inactivo`: quien escucha el estado ya sabe, al verlo, qué se hizo con el texto
  function entregar(texto, via) {
    if (vivo) { try { alTexto(texto, { via }); } catch (x) { console.error(x); } }
    poner({ estado: 'inactivo' });
  }
  // Lo que el panel le dice a la persona en un error de `transcribir` (su `mensaje`), si trae algo
  const mensajeDe = (e) => {
    const m = typeof e?.mensaje === 'string' ? limpiar(e.mensaje).slice(0, 300) : '';
    return m ? { mensaje: m } : {};
  };
  const puedeServidor = () => {
    if (sinServidor || typeof transcribir !== 'function') return false;
    try { return (typeof servidor === 'function' ? servidor() : servidor) !== false; } catch { return true; }
  };

  // ── Vía 1: grabar y transcribir en el servidor ──
  function medidorDe(flujo) {
    const AC = ventana.AudioContext || ventana.webkitAudioContext;
    if (typeof AC !== 'function') return null;
    try {
      const ctx = new AC();
      const fuente = ctx.createMediaStreamSource(flujo);
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      fuente.connect(an);
      try { Promise.resolve(ctx.resume?.()).catch(() => {}); } catch { /* ya corre */ }
      const muestras = new Uint8Array(an.fftSize);
      return {
        /** El nivel (RMS, de 0 a 1) de lo que suena ahora, o null si el audio del navegador no está corriendo. */
        rms() {
          if (typeof ctx.state === 'string' && ctx.state !== 'running') return null;
          an.getByteTimeDomainData(muestras);
          let s = 0;
          for (let i = 0; i < muestras.length; i++) { const x = (muestras[i] - 128) / 128; s += x * x; }
          return Math.sqrt(s / muestras.length);
        },
        soltar() {
          try { fuente.disconnect(); } catch { /* ya suelto */ }
          try { Promise.resolve(ctx.close?.()).catch(() => {}); } catch { /* ya cerrado */ }
        },
      };
    } catch { return null; }
  }

  const motivoDeMedios = (e) => {
    const n = e?.name || '';
    if (n === 'NotAllowedError' || n === 'SecurityError' || n === 'PermissionDeniedError') return 'permiso';
    if (n === 'NotFoundError' || n === 'DevicesNotFoundError' || n === 'OverconstrainedError') return 'sin_microfono';
    if (n === 'NotReadableError' || n === 'TrackStartError' || n === 'AbortError') return 'sin_microfono';
    return 'fallo';
  };

  async function grabar() {
    const g = ++gen;
    const via = 'servidor';
    poner({ estado: 'pidiendo', via });
    let flujo = null, medidor = null, grabadora = null, reloj1 = null, fase = 'pidiendo';
    const soltarMedios = () => {
      if (reloj1 !== null) { reloj.cancelar(reloj1); reloj1 = null; }
      medidor?.soltar();
      medidor = null;
      try { for (const p of flujo?.getTracks?.() || []) p.stop(); } catch { /* ya suelto */ }
      flujo = null;
    };
    cortar = () => {
      fase = 'cortado';
      if (grabadora) {
        grabadora.ondataavailable = grabadora.onstop = grabadora.onerror = null;
        try { if (grabadora.state !== 'inactive') grabadora.stop(); } catch { /* ya parada */ }
      }
      soltarMedios();
    };
    parar = () => { if (fase === 'pidiendo') cancelar(); };   // todavía no hay nada grabado
    try {
      flujo = await ventana.navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      if (g === gen) { cortar = parar = null; fallar(motivoDeMedios(e), { via }); }
      return;
    }
    if (g !== gen) {   // se canceló mientras el navegador preguntaba: el micrófono se suelta sin oír nada
      try { for (const p of flujo?.getTracks?.() || []) p.stop(); } catch { /* ya suelto */ }
      return;
    }
    const MR = ventana.MediaRecorder;
    const tipo = TIPOS.find((t) => { try { return MR.isTypeSupported?.(t) === true; } catch { return false; } }) || '';
    try {
      grabadora = new MR(flujo, { ...(tipo ? { mimeType: tipo } : {}), audioBitsPerSecond: BITS });
    } catch {
      try { grabadora = new MR(flujo); } catch { grabadora = null; }
    }
    if (!grabadora) {   // este navegador no graba: queda su reconocimiento, si lo tiene
      soltarMedios();
      cortar = parar = null;
      if (soporteDeDictado(ventana).reconocer) reconocer();
      else fallar('sin_soporte', { via });
      return;
    }
    const trozos = [];
    let inicio = reloj.ahora(), duracion = 0, porque = null;
    let oyoVoz = false, ultimaVoz = 0, seguidas = 0, midio = false;
    const piso = [];
    grabadora.ondataavailable = (ev) => { if (ev?.data && ev.data.size > 0) trozos.push(ev.data); };
    grabadora.onerror = () => {
      if (g !== gen) return;
      cortar?.();
      cortar = parar = null;
      fallar('fallo', { via });
    };
    grabadora.onstop = () => { if (g === gen) alParar(); };

    function detener(motivo) {
      if (fase !== 'escuchando') return;
      fase = 'parando';
      porque = motivo;
      duracion = reloj.ahora() - inicio;
      if (reloj1 !== null) { reloj.cancelar(reloj1); reloj1 = null; }
      try { grabadora.stop(); } catch { alParar(); }
    }
    parar = () => { if (fase === 'pidiendo') cancelar(); else detener('manual'); };

    async function alParar() {
      if (fase === 'cortado' || fase === 'listo') return;
      if (porque === null) {   // la grabadora paró sola (el micrófono se desconectó): vale lo que alcanzó a oír
        porque = 'grabadora';
        duracion = reloj.ahora() - inicio;
      }
      fase = 'listo';
      const tipoFinal = (typeof grabadora.mimeType === 'string' && grabadora.mimeType) || tipo || 'audio/webm';
      soltarMedios();   // el micrófono queda libre antes de transcribir
      cortar = parar = null;
      if (porque === 'sin_voz' || duracion < MINIMO_MS) { fallar('vacio', { via }); return; }
      const B = ventana.Blob || globalThis.Blob;
      const blob = new B(trozos, { type: tipoFinal });
      if (!blob.size) { fallar('vacio', { via }); return; }
      const control = typeof AbortController === 'function' ? new AbortController() : null;
      cortar = () => { try { control?.abort(); } catch { /* nada */ } };
      poner({ estado: 'transcribiendo', via });
      let res;
      try {
        res = await transcribir(blob, { signal: control?.signal ?? null, duracion_ms: Math.round(duracion) });
      } catch (e) {
        if (g !== gen) return;
        cortar = null;
        if (e?.codigo === 'sin_transcriptor' || e?.estado === 409) {
          // El panel no puede transcribir (Mnemo sin conectar, sin el permiso o sin un modelo que transcriba): la
          // grabación ya no sirve, y la pregunta se repite con el reconocimiento del navegador
          sinServidor = true;
          if (soporteDeDictado(ventana).reconocer) reconocer({ repetir: true });
          else fallar('sin_soporte', { via, ...mensajeDe(e) });
          return;
        }
        fallar('fallo', { via, ...mensajeDe(e) });
        return;
      }
      if (g !== gen) return;
      cortar = null;
      const texto = limpiar(typeof res === 'string' ? res : res?.texto);
      if (!texto) { fallar('vacio', { via }); return; }
      entregar(texto, via);
    }

    function medir() {
      reloj1 = null;
      if (g !== gen || fase !== 'escuchando') return;
      const ahora = reloj.ahora(), lleva = ahora - inicio;
      const r = medidor ? medidor.rms() : null;
      let nivel = 0;
      if (r !== null && Number.isFinite(r)) {
        midio = true;
        piso.push(r);
        if (piso.length > VENTANA_PISO) piso.shift();
        const umbral = Math.min(UMBRAL_MAX, Math.max(UMBRAL_MIN, Math.min(...piso) * SOBRE_PISO));
        seguidas = lleva >= ARRANQUE_MS && r >= umbral ? seguidas + 1 : 0;
        if (seguidas >= SEGUIDAS) { oyoVoz = true; ultimaVoz = ahora; }
        nivel = Math.min(1, Math.sqrt(r / 0.3));
        if (oyoVoz && ahora - ultimaVoz >= SILENCIO_MS) { detener('silencio'); return; }
        if (!oyoVoz && lleva >= SIN_VOZ_MS) { detener('sin_voz'); return; }
      }
      if (lleva >= TOPE_MS) { detener('tope'); return; }
      poner({ estado: 'escuchando', via, nivel, ...(midio ? {} : { medidor: false }) });
      reloj1 = reloj.programar(medir, TICK_MS);
    }

    try {
      grabadora.start(TROZO_MS);
    } catch {
      cortar?.();
      cortar = parar = null;
      fallar('fallo', { via });
      return;
    }
    medidor = medidorDe(flujo);
    inicio = reloj.ahora();
    fase = 'escuchando';
    poner({ estado: 'escuchando', via, nivel: 0, ...(medidor ? {} : { medidor: false }) });
    reloj1 = reloj.programar(medir, TICK_MS);
  }

  // ── Vía 2: el reconocimiento del navegador ──
  function reconocer({ repetir = false } = {}) {
    const g = ++gen;
    const via = 'navegador';
    const SR = ventana.SpeechRecognition || ventana.webkitSpeechRecognition;
    let r;
    try { r = new SR(); } catch { fallar('sin_soporte', { via }); return; }
    r.lang = IDIOMA;
    r.interimResults = true;
    r.continuous = false;     // el servicio corta solo al terminar la frase
    r.maxAlternatives = 1;
    let finales = '', parcial = '', error = null, hablando = false, tope = null, oyendo = false;
    const emitir = () => poner({ estado: 'escuchando', via, nivel: hablando ? 0.7 : 0.15,
      parcial: limpiar(`${finales} ${parcial}`), ...(repetir ? { repetir: true } : {}) });
    const quitarTope = () => { if (tope !== null) { reloj.cancelar(tope); tope = null; } };
    const alTope = (f, ms) => { quitarTope(); tope = reloj.programar(() => { tope = null; f(); }, ms); };
    r.onstart = () => {
      if (g !== gen) return;
      oyendo = true;
      emitir();
      alTope(() => { try { r.stop(); } catch { /* ya paró */ } }, TOPE_MS);
    };
    r.onspeechstart = () => { if (g === gen && oyendo) { hablando = true; emitir(); } };
    r.onspeechend = () => { if (g === gen && oyendo) { hablando = false; emitir(); } };
    r.onresult = (ev) => {
      if (g !== gen) return;
      let f = '', p = '';
      const lista = ev?.results || [];
      for (let i = 0; i < lista.length; i++) {
        const t = typeof lista[i]?.[0]?.transcript === 'string' ? lista[i][0].transcript : '';
        if (lista[i]?.isFinal) f += `${t} `; else p += `${t} `;
      }
      finales = f;
      parcial = p;
      hablando = true;
      oyendo = true;
      emitir();
    };
    r.onerror = (ev) => { error = typeof ev?.error === 'string' ? ev.error : 'fallo'; };
    r.onend = () => {
      if (g !== gen) return;
      quitarTope();
      cortar = parar = null;
      // Lo último que se oyó cuenta aunque el servicio no lo haya dado por final (un «terminar» a mitad de frase)
      const texto = limpiar(`${finales} ${parcial}`);
      if (texto) { entregar(texto, via); return; }
      fallar(error ? MOTIVO_RECONOCER[error] || 'fallo' : 'vacio', { via });
    };
    cortar = () => {
      quitarTope();
      r.onstart = r.onresult = r.onerror = r.onend = r.onspeechstart = r.onspeechend = null;
      try { r.abort(); } catch { /* ya paró */ }
    };
    parar = () => { try { r.stop(); } catch { /* ya paró */ } };
    poner({ estado: 'pidiendo', via, ...(repetir ? { repetir: true } : {}) });
    // Si ni empieza a oír ni da un error, este navegador anuncia el reconocimiento pero no lo tiene
    alTope(() => {
      if (g !== gen || oyendo) return;
      cortar?.();
      cortar = parar = null;
      fallar('sin_soporte', { via });
    }, SIN_ARRANQUE_MS);
    try {
      r.start();
    } catch {
      cortar();
      cortar = parar = null;
      fallar('fallo', { via });
    }
  }

  // ── Lo que usa la vista ──
  /** Empieza a oír (desde `inactivo` o `error`). true si arrancó. */
  function empezar() {
    if (!vivo || (actual.estado !== 'inactivo' && actual.estado !== 'error')) return false;
    const s = soporteDeDictado(ventana);
    const puedeGrabar = s.grabar && typeof transcribir === 'function' && !sinServidor;
    if (puedeGrabar && (puedeServidor() || !s.reconocer)) grabar();
    else if (s.reconocer) reconocer();
    else { fallar('sin_soporte'); return false; }
    return true;
  }

  /** Deja de oír y transcribe lo oído. */
  function terminar() {
    if (actual.estado === 'escuchando' || actual.estado === 'pidiendo') parar?.();
  }

  /** Lo descarta todo y vuelve a `inactivo`: lo que se oía, y una transcripción en camino (su texto ya no llega). */
  function cancelar() {
    gen++;
    const c = cortar;
    cortar = parar = null;
    try { c?.(); } catch (x) { console.error(x); }
    if (actual.estado !== 'inactivo') poner({ estado: 'inactivo' });
  }

  function soltar() {
    cancelar();
    vivo = false;
  }

  return { estado: () => ({ ...actual }), empezar, terminar, cancelar, soltar };
}
