"""La voz clonada en el navegador (docs/agente.md, «La voz clonada de Mnemo» y «Respuestas habladas»), con Node. Solo
datos inventados; nunca se llama a Mnemo ni suena un parlante de verdad.

* `web/js/voz-clonada.js`, con un AudioContext, un reloj y un `pedir` falsos (cada petición la maneja la prueba): tiene
  la forma exacta de voz.js más `preparar`, `motor` y `nivel`; sin la voz clonada ofrecida habla la del navegador sin
  abrir audio ni pedir nada; con ella, el PCM de 16 bits se agenda trozo tras trozo (los valores, el byte suelto que
  pasa al trozo siguiente, el colchón de 150 ms y otro colchón si se quedó sin audio), `alEmpezar` corre cuando suena
  de verdad y 'dicha' cuando terminó; sin audio en 4 s (o con un error antes de sonar) la frase va con la voz del
  navegador y la narración que llega tarde queda guardada; `sin_voz` y `voz_rol` pasan al navegador para la sesión;
  `callar` deja lo de la narración (una pausa repite sin volver a pedir) y suelta lo de una respuesta; se piden como
  mucho 2 a la vez y la precarga que ya no se quiere deja el lugar; un flujo estancado se corta; MP3 se decodifica una
  vez; la prueba de Ajustes nunca va con la voz del navegador; `activar`/`gesto` destraban el audio; `soltar` cierra
  todo; `nivel` sale del medidor de la salida; y una referencia de otra forma no se pide.
* `web/js/locutor.js`, con una voz falsa: dice las frases de un turno en orden, precarga la siguiente, se resincroniza
  con `frases_descartar` sin repetir lo ya dicho, se calla y no sigue, cede ante la narración y salta lo que falló.
* `web/js/voz-panel.js`, con `fetch` y `AudioContext` falsos: una sola voz por ventana con conteo de referencias, la
  narración manda sobre las respuestas, el audio se pide a POST /api/agente/voz con `flujo` (CSRF, NDJSON), el estado
  de la voz llega del asistente o se pide si no hay asistente, y `sin_voz` avisa `agente:estado`.
* `web/js/reproductor.js` con una voz que precarga: cada frase lleva su referencia en el plan (y el resumen la suya) y
  se precarga la que sigue, también en la espera de un plan nuevo.
* Lo estático: los módulos puros no dependen del panel, y lo que usan agente.js, vistas/ajustes.js y
  vistas/presentacion.js de la voz (el botón «Leer las respuestas en voz alta», el bloque «Voz del asistente», la voz de
  la ventana). Y los topes del navegador son los del servidor.
"""
import json
import re
import subprocess
from pathlib import Path

from pytest import approx
from test_agente_presentacion import requiere_node

from app import recorrido as rec
from app.agente import voz as voz_srv

ADMIN = Path(__file__).resolve().parents[1]
JS = ADMIN / "web" / "js"
CLONADA_JS = JS / "voz-clonada.js"
LOCUTOR_JS = JS / "locutor.js"
PANEL_JS = JS / "voz-panel.js"
VOZ_JS = JS / "voz.js"
REPRODUCTOR_JS = JS / "reproductor.js"
AGENTE_JS = (JS / "agente.js").read_text(encoding="utf-8")
AJUSTES_JS = (JS / "vistas" / "ajustes.js").read_text(encoding="utf-8")
VISTA_JS = (JS / "vistas" / "presentacion.js").read_text(encoding="utf-8")
FIRMA = "f" * 43


def _node(tmp_path: Path, guion: str, *args: str) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=120,
                       cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


# Lo falso que comparten los guiones: el reloj (como el de test_reproductor_voz.py), el audio de la ventana, el servidor
# (cada petición queda a mano de la prueba) y la voz del navegador
FALSOS = r"""
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
function audioFalso(ahora) {
  const registro = { contextos: [], fuentes: [], decodificados: 0, decodificadoBytes: 0, nivel: 128, bloqueado: false };
  class AudioContextFalso {
    constructor() { this.state = 'suspended'; this.sampleRate = 48000; this.destination = { parlantes: true }; this.oyentes = {}; registro.contextos.push(this); }
    get currentTime() { return ahora() / 1000; }
    addEventListener(n, f) { this.oyentes[n] = f; }
    removeEventListener(n) { delete this.oyentes[n]; }
    resume() { if (registro.bloqueado) return Promise.reject(new Error('sin gesto')); this.state = 'running'; this.oyentes.statechange?.(); return Promise.resolve(); }
    close() { this.state = 'closed'; return Promise.resolve(); }
    createGain() { return { salida: true, connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 0, connect() {}, getByteTimeDomainData(a) { a.fill(registro.nivel); } }; }
    createBuffer(c, n, m) { const d = Array.from({ length: c }, () => new Float32Array(n)); return { numberOfChannels: c, length: n, sampleRate: m, duration: n / m, getChannelData: (i) => d[i] }; }
    createBufferSource() {
      const s = { buffer: null, en: null, parada: false, destino: null, connect(x) { s.destino = x; }, disconnect() {},
        start(t) { s.en = t; registro.fuentes.push(s); }, stop() { s.parada = true; } };
      return s;
    }
    decodeAudioData(buf) { registro.decodificados++; registro.decodificadoBytes = buf.byteLength; return Promise.resolve(this.createBuffer(1, 4800, 24000)); }
  }
  // lo que suena de verdad (no el búfer mudo del gesto, que va directo a los parlantes)
  registro.sonando = () => registro.fuentes.filter((f) => f.destino?.salida);
  return { AudioContextFalso, registro };
}
function servidorFalso() {
  const pedidos = [];
  let activos = 0, maximo = 0;
  const pedir = (ref, { signal, alEvento }) => new Promise((ok, mal) => {
    activos++; maximo = Math.max(maximo, activos);
    const fin = () => { if (!p.hecho) { p.hecho = true; activos--; } };
    const p = { ref, alEvento, abortada: false, hecho: false, ok: (v) => { fin(); ok(v); }, mal: (e) => { fin(); mal(e); } };
    pedidos.push(p);
    signal?.addEventListener('abort', () => { p.abortada = true; p.ok(false); });
  });
  return { pedidos, pedir, maximo: () => maximo, activos: () => activos };
}
const pcm = (ms) => Buffer.alloc(ms * 48).toString('base64');   // 24 kHz, 16 bits, mono: 48 bytes por ms
const b64 = (bytes) => Buffer.from(bytes).toString('base64');
const errorApi = (estado, codigo, mensaje) => Object.assign(new Error(mensaje), { estado, codigo, detalle: { codigo, mensaje } });
function respaldoFalso() {
  const r = { dichos: [], activado: 0, gestos: 0, encendido: 0, apagado: 0, callado: 0, suelto: false, resultado: 'dicha', e: 'activa',
    estado: () => r.e, decir: async (t) => { r.dichos.push(t); return r.resultado; }, callar() { r.callado++; },
    activar() { r.activado++; }, gesto() { r.gestos++; }, encender() { r.encendido++; }, apagar() { r.apagado++; },
    soltar() { r.suelto = true; }, alCambiar: () => () => {} };
  return r;
}
const almacenFalso = (inicial = {}) => { const d = { ...inicial }; return { d, getItem: (k) => d[k] ?? null, setItem: (k, v) => { d[k] = String(v); } }; };
"""

NODE_CLONADA = FALSOS + r"""
const V = await import(process.argv[2]);
const Vz = await import(process.argv[3]);
const RID = 'abcdef123456';
const REF = (n, frase) => ({ rid: RID, n, frase });
const RESP = (texto) => ({ conversacion: 7, texto, firma: 'f'.repeat(43) });
function armar({ disponible = true, guardado = {}, ventana = {} } = {}) {
  const reloj = relojFalso();
  const { AudioContextFalso, registro } = audioFalso(reloj.ahora);
  const srv = servidorFalso();
  const respaldo = respaldoFalso();
  const almacen = almacenFalso(guardado);
  const caidas = [], cambios = [], oyentes = {};
  const v = { AudioContext: AudioContextFalso, atob, AbortController, addEventListener: (n, f) => { oyentes[n] = f; },
    removeEventListener: (n) => { delete oyentes[n]; }, ...ventana };
  let disp = disponible;
  const voz = V.crearVozClonada({ ventana: v, pedir: srv.pedir, respaldo, almacen, reloj, disponible: () => disp, alCaer: (c) => caidas.push(c) });
  voz.alCambiar((e) => cambios.push(e));
  return { reloj, registro, srv, respaldo, almacen, caidas, cambios, oyentes, voz, fijar: (x) => { disp = x; } };
}
async function encendida(op) { const a = armar(op); a.voz.activar(); await a.reloj.avanzar(1); return a; }
const decir = (a, texto, ref, extra = {}) => {
  const d = { res: null, marcas: [] };
  d.p = a.voz.decir(texto, { ref, alEmpezar: () => d.marcas.push(['empezo', a.reloj.ahora()]), alFin: (x) => d.marcas.push(['fin', x]), ...extra });
  d.p.then((x) => { d.res = x; });
  return d;
};
const inicio = (q, extra = {}) => q.alEvento({ tipo: 'inicio', formato: 'pcm_s16le', muestreo: 24000, canales: 1, cache: false, voz: 'Ana Inventada', ...extra });
const out = {};

// La forma: la de voz.js más preparar, motor y nivel; las constantes que comparten
{
  const { voz } = armar();
  const nav = Vz.crearVoz({ ventana: {}, almacen: almacenFalso() });
  out.forma = { clonada: Object.keys(voz).sort(), navegador: Object.keys(nav).sort() };
  out.constantes = { CLAVE: V.CLAVE, CLAVE_VOZ: Vz.CLAVE, A_LA_VEZ: V.A_LA_VEZ, MAX_FRASE: V.MAX_FRASE, PRIMER: V.PRIMER_AUDIO_MS,
    PRIMER_PRUEBA: V.PRIMER_AUDIO_PRUEBA_MS, BUFER: V.BUFER_S, ESTANCADO: V.ESTANCADO_MS, SIN_VOZ: V.SIN_VOZ };
}

// Sin la voz clonada ofrecida: la del navegador, sin abrir audio ni pedir nada
{
  const a = armar({ disponible: false });
  a.voz.activar();
  a.voz.gesto();
  const r = await a.voz.decir('Una frase.', { ref: REF(1, 0) });
  a.voz.preparar([{ texto: 'Otra.', ref: REF(1, 1) }]);
  await a.reloj.avanzar(10);
  out.navegador = { motor: a.voz.motor(), r, dichos: a.respaldo.dichos, pedidos: a.srv.pedidos.length,
    contextos: a.registro.contextos.length, estado: a.voz.estado(), activado: a.respaldo.activado };
}

// La voz clonada: el PCM agendado trozo tras trozo, cuándo empieza y cuándo termina
{
  const a = await encendida();
  out.listo = { estado: a.voz.estado(), motor: a.voz.motor(), contextos: a.registro.contextos.length, corre: a.registro.contextos[0].state,
    mudo: a.registro.fuentes.filter((f) => f.destino?.parlantes).map((f) => [f.buffer.length, f.en]), activado: a.respaldo.activado };
  const d = decir(a, 'Hola.', REF(1, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  await a.reloj.avanzar(300);
  const llega = a.reloj.ahora();
  // 0x4000 → 0,5; 0xFFFF → -1/32768; y un byte suelto, que pasa al trozo siguiente (con él: 0x8000 → -1)
  q.alEvento({ tipo: 'audio', datos: b64([0x00, 0x40, 0xff, 0xff, 0x00]) });
  q.alEvento({ tipo: 'audio', datos: b64([0x80, 0x00, 0x00]) });
  q.alEvento({ tipo: 'latido' });
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  await a.reloj.avanzar(100);
  const antes = d.marcas.length;
  await a.reloj.avanzar(60);
  q.alEvento({ tipo: 'fin', ms_primer_audio: 300, ms_mnemo: 210, bytes: 9608 });
  q.ok(true);
  await a.reloj.avanzar(10);
  const sonando = a.registro.sonando();
  const fin = sonando.at(-1).en + sonando.at(-1).buffer.duration;
  const resAntes = d.res;
  await a.reloj.avanzar(Math.ceil(fin * 1000 + 60 - a.reloj.ahora()) + 1);
  out.pcm = { ref: q.ref, llega, antes, marcas: d.marcas, resAntes, res: d.res, fin,
    fuentes: sonando.map((f) => ({ en: f.en, n: f.buffer.length, datos: [...f.buffer.getChannelData(0).slice(0, 2)] })) };
  // La misma frase otra vez (una pausa, «Repetir»): de lo guardado, sin pedirla
  const d2 = decir(a, 'Hola.', REF(1, 0));
  const t0 = a.reloj.ahora();
  await a.reloj.avanzar(1000);
  out.repetida = { pedidos: a.srv.pedidos.length, res: d2.res, empezo: d2.marcas.find((m) => m[0] === 'empezo')?.[1] - t0 };
}

// Sin audio en 4 s: la voz del navegador; la narración que llega tarde queda guardada
{
  const a = await encendida();
  const d = decir(a, 'Una frase lenta.', REF(1, 1));
  await a.reloj.avanzar(3990);
  const antes = { dichos: [...a.respaldo.dichos], res: d.res };
  await a.reloj.avanzar(20);
  const q = a.srv.pedidos[0];
  out.plazo = { antes, dichos: a.respaldo.dichos, res: d.res, abortada: q.abortada, fin: d.marcas.find((m) => m[0] === 'fin')?.[1] };
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  q.alEvento({ tipo: 'fin', ms_primer_audio: 5000, ms_mnemo: 4800, bytes: 9600 });
  q.ok(true);
  await a.reloj.avanzar(5);
  const d2 = decir(a, 'Una frase lenta.', REF(1, 1));
  await a.reloj.avanzar(500);
  out.plazo.despues = { pedidos: a.srv.pedidos.length, res: d2.res, dichos: a.respaldo.dichos.length };
}

// Un error antes de sonar: esa frase con la voz del navegador, y la siguiente vez se vuelve a pedir
{
  const a = await encendida();
  const d = decir(a, 'Ya no vale.', REF(2, 0));
  await a.reloj.avanzar(5);
  a.srv.pedidos[0].mal(errorApi(409, 'plan_vencido', 'Ese plan ya no es el vigente: no se narra.'));
  await a.reloj.avanzar(5);
  const d2 = decir(a, 'Ya no vale.', REF(2, 0));
  await a.reloj.avanzar(5);
  out.error_antes = { res: d.res, dichos: a.respaldo.dichos, motor: a.voz.motor(), fin: d.marcas.find((m) => m[0] === 'fin')?.[1],
    pedidos: a.srv.pedidos.length, caidas: a.caidas };
  a.voz.callar();
  await a.reloj.avanzar(5);
  out.error_antes.cortada = d2.res;
}

// sin_voz y voz_rol: la voz del navegador para el resto de la sesión
for (const [codigo, estado] of [['sin_voz', 409], ['voz_rol', 403]]) {
  const a = await encendida();
  a.voz.preparar([{ texto: 'Después.', ref: REF(1, 1) }]);
  const d = decir(a, 'Primera.', REF(1, 0));
  await a.reloj.avanzar(5);
  const [pre, esta] = [a.srv.pedidos[0], a.srv.pedidos[1]];
  a.cambios.length = 0;
  esta.mal(errorApi(estado, codigo, 'El asistente usa la voz del navegador.'));
  await a.reloj.avanzar(5);
  const r2 = await a.voz.decir('Segunda.', { ref: REF(1, 1) });
  a.voz.preparar([{ texto: 'Tercera.', ref: REF(2, 0) }]);
  out[`caida_${codigo}`] = { res: d.res, r2, dichos: a.respaldo.dichos, motor: a.voz.motor(), caidas: a.caidas, pedidos: a.srv.pedidos.length,
    precarga_abortada: pre.abortada, avisado: a.cambios.length > 0 };
}

// callar: deja lo de la narración (una pausa repite sin pedir) y suelta lo de una respuesta
{
  const a = await encendida();
  const d = decir(a, 'Una frase que se pausa.', REF(3, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  await a.reloj.avanzar(250);
  a.voz.callar();
  await a.reloj.avanzar(1);
  const paradas = a.registro.sonando().every((f) => f.parada);
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  q.alEvento({ tipo: 'fin', ms_primer_audio: 5, ms_mnemo: 4, bytes: 19200 });
  q.ok(true);
  const antes = a.registro.sonando().length;
  const d2 = decir(a, 'Una frase que se pausa.', REF(3, 0));
  await a.reloj.avanzar(800);
  out.callar_narracion = { res: d.res, paradas, abortada: q.abortada, pedidos: a.srv.pedidos.length, res2: d2.res,
    agendadas: a.registro.sonando().length - antes };
  const r = decir(a, 'Hay doce puestos.', RESP('Hay doce puestos.'));
  await a.reloj.avanzar(5);
  const qr = a.srv.pedidos[1];
  inicio(qr);
  qr.alEvento({ tipo: 'audio', datos: pcm(200) });
  await a.reloj.avanzar(200);
  a.voz.callar();
  await a.reloj.avanzar(1);
  const r2 = decir(a, 'Hay doce puestos.', RESP('Hay doce puestos.'));
  await a.reloj.avanzar(5);
  out.callar_respuesta = { res: r.res, abortada: qr.abortada, pedidos: a.srv.pedidos.length, ref: a.srv.pedidos[2]?.ref };
  a.voz.callar();
}

// Como mucho dos a la vez; la precarga que ya no se quiere deja el lugar
{
  const a = await encendida();
  decir(a, 'A.', REF(1, 0));
  a.voz.preparar([{ texto: 'B.', ref: REF(1, 1) }]);
  await a.reloj.avanzar(5);
  const dos = a.srv.pedidos.map((p) => p.ref);
  a.voz.preparar([{ texto: 'C.', ref: REF(2, 0) }]);   // se saltó a otro paso: B ya no viene
  await a.reloj.avanzar(5);
  const tras = a.srv.pedidos.map((p) => [p.ref.n, p.ref.frase, p.abortada]);
  decir(a, 'D.', REF(3, 0));                            // otra frase ahora (sin precarga): A deja el lugar, C no
  await a.reloj.avanzar(5);
  out.lugares = { dos, tras, final: a.srv.pedidos.map((p) => [p.ref.n, p.ref.frase, p.abortada]), maximo: a.srv.maximo() };
  a.voz.callar();
  // tres para precargar: van dos
  const b = await encendida();
  b.voz.preparar([1, 2, 3].map((k) => ({ texto: `${k}.`, ref: REF(4, k - 1) })));
  await b.reloj.avanzar(5);
  out.lugares.precargadas = b.srv.pedidos.length;
}

// Un flujo que ya sonó y se queda sin traer nada: se corta, suena lo que llegó y resuelve 'fallo' (sin el navegador)
{
  const a = await encendida();
  const d = decir(a, 'Se estanca.', REF(5, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  await a.reloj.avanzar(7000);
  const antes = { abortada: q.abortada, res: d.res };
  await a.reloj.avanzar(2500);
  out.estancado = { antes, abortada: q.abortada, res: d.res, dichos: a.respaldo.dichos, motor: a.voz.motor(),
    fin: d.marcas.find((m) => m[0] === 'fin')?.[1] };
}

// Un error a mitad del flujo: suena lo que llegó y 'fallo'
{
  const a = await encendida();
  const d = decir(a, 'Falla a mitad.', REF(5, 1));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(100) });
  q.alEvento({ tipo: 'error', codigo: 'mnemo_red', mensaje: 'La voz clonada no respondió: Mnemo no está disponible.' });
  q.ok(true);
  await a.reloj.avanzar(400);
  out.a_mitad = { res: d.res, dichos: a.respaldo.dichos, motor: a.voz.motor(), empezo: d.marcas.some((m) => m[0] === 'empezo') };
}

// Se quedó sin audio a mitad: el trozo que llega tarde lleva otro colchón (no se agenda en el pasado)
{
  const a = await encendida();
  const d = decir(a, 'Llega a saltos.', REF(6, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(100) });
  await a.reloj.avanzar(600);
  const tarde = a.reloj.ahora();
  q.alEvento({ tipo: 'audio', datos: pcm(100) });
  q.alEvento({ tipo: 'fin', ms_primer_audio: 5, ms_mnemo: 4, bytes: 9600 });
  q.ok(true);
  await a.reloj.avanzar(500);
  out.sin_audio = { tarde, en: a.registro.sonando().map((f) => f.en), res: d.res };
}

// MP3 (Mnemo no pudo dar PCM): la frase entera, decodificada una vez
{
  const a = await encendida();
  const d = decir(a, 'En mp3.', REF(7, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q, { formato: 'mp3', muestreo: null, canales: null });
  q.alEvento({ tipo: 'audio', datos: b64([1, 2, 3, 4, 5, 6]) });
  q.alEvento({ tipo: 'audio', datos: b64([7, 8, 9]) });
  await a.reloj.avanzar(100);
  const antes = a.registro.decodificados;
  q.alEvento({ tipo: 'fin', ms_primer_audio: 900, ms_mnemo: 800, bytes: 9 });
  q.ok(true);
  await a.reloj.avanzar(600);
  const d2 = decir(a, 'En mp3.', REF(7, 0));
  await a.reloj.avanzar(600);
  out.mp3 = { antes, decodificados: a.registro.decodificados, bytes: a.registro.decodificadoBytes, res: d.res, res2: d2.res,
    fuentes: a.registro.sonando().length, pedidos: a.srv.pedidos.length };
}

// El gesto: crea el audio de la ventana (solo con voz clonada), lo reanuda y suena un búfer mudo
{
  const a = armar();
  const antes = a.registro.contextos.length;
  const oye = typeof a.oyentes.pointerdown === 'function' && typeof a.oyentes.keydown === 'function';
  a.oyentes.pointerdown();
  await a.reloj.avanzar(1);
  const b = armar({ ventana: { navigator: { userActivation: { hasBeenActive: true } } } });
  await b.reloj.avanzar(1);
  const c = armar({ disponible: false, ventana: { navigator: { userActivation: { hasBeenActive: true } } } });
  c.voz.gesto();
  out.gesto = { antes, oye, despues: a.registro.contextos.length, corre: a.registro.contextos[0]?.state,
    mudo: a.registro.fuentes.filter((f) => f.destino?.parlantes && f.buffer.length === 1).length, gestos: a.respaldo.gestos,
    tocada: b.registro.contextos.length && b.registro.contextos[0].state, sin_clonada: c.registro.contextos.length };
}

// El navegador no deja reanudar el audio (Safari, con el gesto en un iframe de otro origen): habla la del navegador
{
  const a = armar();
  a.registro.bloqueado = true;
  a.voz.activar();
  await a.reloj.avanzar(1);
  const estado = a.voz.estado();
  const d = decir(a, 'Sin audio de la ventana.', REF(8, 0));
  await a.reloj.avanzar(400);
  // Y las que siguen (la narración y una respuesta): ninguna se le pide a Mnemo, que la cobraría sin que se oyera
  const fines = [d.marcas.find((m) => m[0] === 'fin')?.[1]?.error?.codigo];
  const res = [d.res];
  for (const [t, ref] of [['Segunda frase.', REF(8, 1)], ['Tercera frase.', REF(8, 2)], ['Una respuesta.', RESP('Una respuesta.')]]) {
    const x = decir(a, t, ref);
    await a.reloj.avanzar(400);
    res.push(x.res);
    fines.push(x.marcas.find((m) => m[0] === 'fin')?.[1]?.error?.codigo);
  }
  out.sin_reanudar = { estado, res: d.res, dichos: a.respaldo.dichos, fin: fines[0], fines, todas: res,
    pedidos: a.srv.pedidos.length, sonando: a.registro.sonando().length };
}

// El estado de la voz del navegador sola (la vista lo usa con el plan automático sin la voz clonada): sin voces en
// español, 'sin_voces' aunque la clonada esté activa
{
  const a = await encendida();
  a.respaldo.e = 'sin_voces';
  out.estado_navegador = { estado: a.voz.estado(), navegador: a.voz.estadoNavegador(), motor: a.voz.motor() };
}

// La preferencia es la de voz.js (`yj_voz`)
{
  const a = armar({ guardado: { yj_voz: '0' } });
  const apagada = a.voz.estado();
  const r = await a.voz.decir('Nada.', { ref: REF(1, 0) });
  a.voz.preparar([{ texto: 'Nada.', ref: REF(1, 1) }]);
  a.voz.encender();
  await a.reloj.avanzar(1);
  const encendida = { estado: a.voz.estado(), guardado: a.almacen.d.yj_voz, respaldo: a.respaldo.encendido };
  a.voz.apagar();
  out.preferencia = { apagada, r, pedidos: a.srv.pedidos.length, encendida, apagada2: a.voz.estado(), guardado: a.almacen.d.yj_voz,
    respaldo: a.respaldo.apagado };
}

// La prueba de Ajustes: con la voz clonada aunque la persona no la use, nunca con la del navegador
{
  const a = armar({ disponible: false });
  const d = decir(a, '', { prueba: true });
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q, { cache: true });
  q.alEvento({ tipo: 'audio', datos: pcm(200) });
  q.alEvento({ tipo: 'fin', ms_primer_audio: 12, ms_mnemo: null, bytes: 9600 });
  q.ok(true);
  await a.reloj.avanzar(600);
  out.prueba = { ref: q.ref, res: d.res, fin: d.marcas.find((m) => m[0] === 'fin')?.[1], empezo: d.marcas.some((m) => m[0] === 'empezo'),
    contextos: a.registro.contextos.length };
  const d2 = decir(a, '', { prueba: true });
  await a.reloj.avanzar(5);
  out.prueba.otra_vez = a.srv.pedidos.length;   // no se guarda: cada prueba mide de nuevo
  a.srv.pedidos[1].mal(errorApi(409, 'sin_voz', 'La voz elegida ya no está disponible en Mnemo.'));
  await a.reloj.avanzar(5);
  out.prueba.fallo = { res: d2.res, fin: d2.marcas.find((m) => m[0] === 'fin')?.[1], dichos: a.respaldo.dichos, caidas: a.caidas };
  // espera más que una frase: a los 4 s todavía no se rinde
  const d3 = decir(a, '', { prueba: true });
  await a.reloj.avanzar(5000);
  const a_los_5 = d3.res;
  await a.reloj.avanzar(16000);
  out.prueba.plazo = { a_los_5, res: d3.res, codigo: d3.marcas.find((m) => m[0] === 'fin')?.[1]?.error?.codigo };
}

// nivel: del medidor de la salida, mientras suena la voz clonada
{
  const a = await encendida();
  const callado = a.voz.nivel();
  const d = decir(a, 'Suena.', REF(9, 0));
  await a.reloj.avanzar(5);
  const q = a.srv.pedidos[0];
  inicio(q);
  q.alEvento({ tipo: 'audio', datos: pcm(400) });
  await a.reloj.avanzar(200);
  a.registro.nivel = 128;
  const silencio = a.voz.nivel();
  a.registro.nivel = 200;
  const suena = a.voz.nivel();
  a.voz.callar();
  out.nivel = { callado, silencio, suena, tras_callar: a.voz.nivel() };
}

// soltar: callada, sin oyentes, sin peticiones en camino y con el audio cerrado
{
  const a = await encendida();
  const d = decir(a, 'Se suelta.', REF(10, 0));
  a.voz.preparar([{ texto: 'Otra.', ref: REF(10, 1) }]);
  await a.reloj.avanzar(5);
  a.voz.soltar();
  await a.reloj.avanzar(5);
  const r = await a.voz.decir('Ya no.', { ref: REF(10, 0) });
  out.soltar = { res: d.res, abortadas: a.srv.pedidos.map((p) => p.abortada), estado: a.registro.contextos[0].state,
    oyentes: Object.keys(a.oyentes), respaldo: a.respaldo.suelto, r, pedidos: a.srv.pedidos.length, motor: a.voz.motor() };
}

// Las referencias: solo las de la forma que acepta el servidor; las demás, con la voz del navegador
{
  const a = await encendida();
  const malas = [{ rid: 'XYZ', n: 1, frase: 0 }, { rid: RID, n: 1, frase: 3 }, { rid: RID, n: 13, frase: 0 }, { rid: RID, n: 0, frase: 0 },
    { rid: RID, n: 1, frase: 0, extra: 1 }, { rid: RID, cierre: false }, { rid: RID, n: 1.5, frase: 0 },
    { conversacion: 1, texto: 'x'.repeat(401), firma: 'f'.repeat(43) }, { conversacion: 1, texto: 'hola', firma: 'corta' },
    { conversacion: 0, texto: 'hola', firma: 'f'.repeat(43) }, { conversacion: 1, texto: '  ', firma: 'f'.repeat(43) },
    { prueba: 'si' }, null, 'abc', [1]];
  for (const m of malas) await a.voz.decir('Una frase.', { ref: m });
  out.referencias = { pedidos: a.srv.pedidos.length, dichos: a.respaldo.dichos.length,
    buenas: [REF(12, 2), { rid: RID, cierre: true }, RESP('é'.repeat(400)), { prueba: true }].map((r) => V.refValida(r)),
    malas: malas.map((m) => V.refValida(m)) };
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_la_voz_clonada_con_un_audio_falso(tmp_path):
    r = _node(tmp_path, NODE_CLONADA, CLONADA_JS.as_uri(), VOZ_JS.as_uri())
    # La forma exacta de voz.js, más lo suyo
    assert set(r["forma"]["clonada"]) == set(r["forma"]["navegador"]) | {"preparar", "motor", "nivel",
                                                                         "estadoNavegador"}
    c = r["constantes"]
    assert c["CLAVE"] == c["CLAVE_VOZ"] == "yj_voz"
    assert c["A_LA_VEZ"] == voz_srv.A_LA_VEZ_PERSONA and c["MAX_FRASE"] == voz_srv.MAX_AUDIO
    assert c["PRIMER"] == 4000 and c["BUFER"] == 0.15 and c["PRIMER_PRUEBA"] > c["PRIMER"]
    assert c["SIN_VOZ"] == ["sin_voz", "voz_rol"]

    # Sin la voz clonada ofrecida: la del navegador, sin audio de la ventana ni pedidos
    assert r["navegador"] == {"motor": "navegador", "r": "dicha", "dichos": ["Una frase."], "pedidos": 0, "contextos": 0,
                              "estado": "activa", "activado": 1}

    # El gesto destrabó el audio (un búfer mudo de una muestra) y la voz del navegador
    assert r["listo"] == {"estado": "activa", "motor": "clonada", "contextos": 1, "corre": "running", "mudo": [[1, 0]],
                          "activado": 1}
    p = r["pcm"]
    assert p["ref"] == {"rid": "abcdef123456", "n": 1, "frase": 0}
    # llegó y todavía no suena: el colchón de 150 ms; después, `alEmpezar`
    assert p["antes"] == 0 and p["marcas"][0][0] == "empezo" and p["marcas"][0][1] == approx(p["llega"] + 150)
    f = p["fuentes"]
    assert [x["n"] for x in f] == [2, 2, 4800]
    assert f[0]["en"] == approx((p["llega"] + 150) / 1000)
    assert f[1]["en"] == approx(f[0]["en"] + 2 / 24000) and f[2]["en"] == approx(f[1]["en"] + 2 / 24000)
    assert f[0]["datos"] == approx([0.5, -1 / 32768]) and f[1]["datos"] == approx([-1, 0])
    # terminó cuando terminó de sonar (no cuando llegó el `fin`), con lo que midió el servidor
    assert p["resAntes"] is None and p["res"] == "dicha"
    assert p["marcas"][1] == ["fin", {"ms_primer_audio": 300, "ms_mnemo": 210, "cache": False, "bytes": 9608}]
    assert r["repetida"]["pedidos"] == 1 and r["repetida"]["res"] == "dicha" and r["repetida"]["empezo"] == approx(150)

    # Sin audio a los 4 s: con la voz del navegador (y lo que dice esa); la narración sigue llegando y queda guardada
    pl = r["plazo"]
    assert pl["antes"] == {"dichos": [], "res": None}
    assert pl["dichos"] == ["Una frase lenta."] and pl["res"] == "dicha" and pl["abortada"] is False
    assert pl["fin"]["error"]["codigo"] == "plazo"
    assert pl["despues"] == {"pedidos": 1, "res": "dicha", "dichos": 1}

    # Un error antes de sonar: solo esa frase; se vuelve a pedir la próxima vez
    e = r["error_antes"]
    assert e["res"] == "dicha" and e["dichos"] == ["Ya no vale."] and e["motor"] == "clonada" and e["caidas"] == []
    assert e["fin"]["error"] == {"codigo": "plan_vencido", "mensaje": "Ese plan ya no es el vigente: no se narra."}
    assert e["pedidos"] == 2 and e["cortada"] == "cortada"

    # sin_voz y voz_rol: el resto de la sesión con la del navegador (y lo que se estaba pidiendo se suelta)
    for codigo in ("sin_voz", "voz_rol"):
        k = r[f"caida_{codigo}"]
        assert k["res"] == "dicha" and k["r2"] == "dicha" and k["dichos"] == ["Primera.", "Segunda."], k
        assert k["motor"] == "navegador" and k["caidas"] == [codigo] and k["pedidos"] == 2, k
        assert k["precarga_abortada"] is True and k["avisado"] is True, k

    # callar: la narración queda (la pausa la repite sin pedir: lo que siguió llegando también suena)
    cn = r["callar_narracion"]
    assert cn == {"res": "cortada", "paradas": True, "abortada": False, "pedidos": 1, "res2": "dicha", "agendadas": 2}
    # lo de una respuesta se suelta: se corta su petición y otra vez se pide
    cr = r["callar_respuesta"]
    assert cr["res"] == "cortada" and cr["abortada"] is True and cr["pedidos"] == 3
    assert cr["ref"] == {"conversacion": 7, "texto": "Hay doce puestos.", "firma": FIRMA}

    # Dos a la vez como mucho: la precarga que ya no viene (se saltó) se corta; la frase de ahora pasa delante
    lg = r["lugares"]
    assert [x["frase"] for x in lg["dos"]] == [0, 1]
    assert lg["tras"] == [[1, 0, False], [1, 1, True], [2, 0, False]]
    assert lg["final"] == [[1, 0, True], [1, 1, True], [2, 0, False], [3, 0, False]]
    assert lg["maximo"] == 2 and lg["precargadas"] == 2

    # Estancado: a los 8 s sin nada se corta; suena lo que llegó y 'fallo', sin la voz del navegador
    es = r["estancado"]
    assert es["antes"] == {"abortada": False, "res": None}
    assert es["abortada"] is True and es["res"] == "fallo" and es["dichos"] == [] and es["motor"] == "clonada"
    assert es["fin"]["error"]["codigo"] == "callado"
    assert r["a_mitad"] == {"res": "fallo", "dichos": [], "motor": "clonada", "empezo": True}
    sa = r["sin_audio"]
    assert sa["en"][1] == approx((sa["tarde"] + 150) / 1000) and sa["res"] == "dicha"

    # MP3: se junta entero y se decodifica una vez (la repetición usa lo decodificado)
    assert r["mp3"] == {"antes": 0, "decodificados": 1, "bytes": 9, "res": "dicha", "res2": "dicha", "fuentes": 2, "pedidos": 1}

    # El gesto: el audio se crea en el gesto (o al crearse, si la página ya tuvo uno), nunca sin voz clonada
    assert r["gesto"] == {"antes": 0, "oye": True, "despues": 1, "corre": "running", "mudo": 1, "gestos": 1,
                          "tocada": "running", "sin_clonada": 0}
    # Sin el audio de la ventana, ninguna frase se le pide a Mnemo (se pagaría sin oírse): todas van con la del navegador
    assert r["sin_reanudar"] == {"estado": "activa", "res": "dicha",
                                 "dichos": ["Sin audio de la ventana.", "Segunda frase.", "Tercera frase.",
                                            "Una respuesta."],
                                 "fin": "sin_activar", "fines": ["sin_activar"] * 4, "todas": ["dicha"] * 4,
                                 "pedidos": 0, "sonando": 0}
    assert r["estado_navegador"] == {"estado": "activa", "navegador": "sin_voces", "motor": "clonada"}

    # La preferencia de voz.js: apagada, ni se pide; encender y apagar cambian las dos voces
    pr = r["preferencia"]
    assert pr["apagada"] == "apagada" and pr["r"] == "fallo" and pr["pedidos"] == 0
    assert pr["encendida"] == {"estado": "activa", "guardado": "1", "respaldo": 1}
    assert pr["apagada2"] == "apagada" and pr["guardado"] == "0" and pr["respaldo"] == 1

    # La prueba de Ajustes
    pb = r["prueba"]
    assert pb["ref"] == {"prueba": True} and pb["res"] == "dicha" and pb["empezo"] and pb["contextos"] == 1
    assert pb["fin"] == {"ms_primer_audio": 12, "ms_mnemo": None, "cache": True, "bytes": 9600}
    assert pb["otra_vez"] == 2
    assert pb["fallo"]["res"] == "fallo" and pb["fallo"]["dichos"] == [] and pb["fallo"]["caidas"] == []
    assert pb["fallo"]["fin"]["error"]["codigo"] == "sin_voz"
    assert pb["plazo"] == {"a_los_5": None, "res": "fallo", "codigo": "plazo"}

    n = r["nivel"]
    assert n["callado"] == 0 and n["silencio"] == 0 and 0 < n["suena"] <= 1 and n["tras_callar"] == 0

    s = r["soltar"]
    assert s["res"] == "cortada" and s["abortadas"] == [True, True] and s["estado"] == "closed" and s["oyentes"] == []
    assert s["respaldo"] is True and s["r"] == "fallo" and s["pedidos"] == 2 and s["motor"] == "navegador"

    ref = r["referencias"]
    assert ref["pedidos"] == 0 and ref["dichos"] == len(ref["malas"]) and all(m is None for m in ref["malas"])
    assert ref["buenas"] == [{"rid": "abcdef123456", "n": 12, "frase": 2}, {"rid": "abcdef123456", "cierre": True},
                             {"conversacion": 7, "texto": "é" * 400, "firma": FIRMA}, {"prueba": True}]


def test_los_rangos_de_la_referencia_son_los_de_la_ruta():
    """Lo que el navegador pide (`refValida`) cabe en `VozIn` (app/api/agente.py): una referencia de otra forma sería un
    422 de la ruta. Los rangos vienen del recorrido."""
    js = CLONADA_JS.read_text(encoding="utf-8")
    assert f"const MAX_ESCENAS = {rec.MAX_ESCENAS};" in js and f"const MAX_FRASES = {rec.MAX_FRASES};" in js
    assert f"const MAX_TEXTO = {voz_srv.MAX_TEXTO};" in js
    assert "const RID = /^[0-9a-f]{12}$/;" in js and "const FIRMA = /^[A-Za-z0-9_-]{43}$/;" in js
    from app.api.agente import ID_MAX, VozIn
    assert "const ID_MAX = 10 ** 12;" in js and ID_MAX == 10**12
    assert VozIn.model_fields["texto"].metadata[1].max_length == voz_srv.MAX_TEXTO
    locutor = LOCUTOR_JS.read_text(encoding="utf-8")
    assert f"export const MAX_TEXTO = {voz_srv.MAX_TEXTO};" in locutor


NODE_LOCUTOR = FALSOS + r"""
const L = await import(process.argv[2]);
const espera = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
// Una voz que la prueba maneja: cada `decir` queda pendiente hasta `terminar(res)`; callar la corta
function vozFalsa() {
  const v = { dichos: [], preparados: [], callados: 0, pendiente: null,
    decir(t, o) { return new Promise((ok) => { v.dichos.push(o.ref.texto); v.refs = [...(v.refs || []), o.ref]; v.pendiente = { ok }; }); },
    async terminar(r = 'dicha') { const p = v.pendiente; v.pendiente = null; p?.ok(r); await espera(); },
    callar() { v.callados++; const p = v.pendiente; v.pendiente = null; p?.ok('cortada'); },
    preparar(items) { v.preparados.push(items.map((x) => x.ref.texto)); } };
  return v;
}
const F = (n, texto) => ({ tipo: 'frase', n, texto, firma: 'f'.repeat(43) });
const out = {};

// En orden, con la siguiente precargada; avisa cuándo habla
{
  const v = vozFalsa(); const avisos = [];
  const l = L.crearLocutor({ voz: v, alHablar: (x) => avisos.push(x) });
  l.empezar(5);
  l.frase(F(1, 'Y eso es todo por ahora.'));
  await espera();
  const antes = [...v.dichos];
  l.frase(F(0, 'Hay doce puestos en Yondó.'));
  await espera();
  const hablando = l.hablando();
  await v.terminar();
  await v.terminar();
  out.orden = { antes, dichos: v.dichos, refs: v.refs, preparados: v.preparados, avisos, hablando, despues: l.hablando(), activo: l.activo() };
}

// frases_descartar: la que suena se corta y se dice su versión nueva; lo ya dicho no se repite
{
  const v = vozFalsa();
  const l = L.crearLocutor({ voz: v });
  l.empezar(5);
  for (const [n, t] of [[0, 'Primera frase de la respuesta.'], [1, 'Segunda frase de la respuesta.'], [2, 'Tercera frase de la respuesta.']]) l.frase(F(n, t));
  await espera();
  await v.terminar();          // la 0, dicha; suena la 1
  l.descartar(1);              // la 1 y la 2 ya no valen
  await espera();
  const callados = v.callados;
  l.frase(F(1, 'Otra segunda frase.'));
  await espera();
  await v.terminar();
  l.frase(F(2, 'Otra tercera frase.'));
  await espera();
  await v.terminar();
  out.descartar = { dichos: v.dichos, callados };
  // lo que ya se dijo entero no vuelve: sonaba la 2 y se descarta desde la 1
  const w = vozFalsa();
  const m = L.crearLocutor({ voz: w });
  m.empezar(5);
  for (const n of [0, 1, 2]) m.frase(F(n, `Frase número ${n} de la respuesta.`));
  await espera();
  await w.terminar();
  await w.terminar();
  m.descartar(1);
  await espera();
  const vieja = m.frase(F(1, 'La uno nueva no se dice: ya se dijo.'));
  m.frase(F(2, 'La dos nueva sí.'));
  await espera();
  await w.terminar();
  // y sin nada sonando, descartar solo quita lo que esperaba
  m.frase(F(4, 'La cuatro llega antes que la tres.'));
  m.descartar(3);
  m.frase(F(3, 'La tres.'));
  await espera();
  await w.terminar();
  out.descartar_dicho = { dichos: w.dichos, vieja };
}

// frases_ronda: la ronda rehecha fue más corta que lo que ya se había dicho; lo de la ronda siguiente sí se dice
{
  const v = vozFalsa();
  const l = L.crearLocutor({ voz: v });
  l.empezar(5);
  for (const n of [0, 1, 2, 3]) l.frase(F(n, `Vieja ${n}.`));
  await espera();
  await v.terminar();
  await v.terminar();
  await v.terminar();          // la 0, la 1 y la 2, dichas; suena la 3
  l.descartar(0);              // la ronda se repite: la 3 se corta
  await espera();
  const nuevas = [l.frase(F(0, 'Nueva 0.')), l.frase(F(1, 'Nueva 1.'))];   // ya dichas por número: no se repiten
  await espera();
  l.ronda(2);                  // la ronda siguiente empieza en la 2
  for (const n of [2, 3, 4]) l.frase(F(n, `Después ${n}.`));
  await espera();
  await v.terminar();
  await v.terminar();
  await v.terminar();
  // una ronda que no hace falta ajustar (lo dicho no pasó de `desde`) no cambia nada, ni sonando una frase
  const w = vozFalsa();
  const m = L.crearLocutor({ voz: w });
  m.empezar(5);
  m.frase(F(0, 'La única de la ronda.'));
  await espera();
  m.ronda(0);
  m.ronda(1);
  await w.terminar();
  m.frase(F(1, 'La de la ronda siguiente.'));
  await espera();
  await w.terminar();
  m.ronda(-1);
  m.ronda('2');
  out.ronda = { dichos: v.dichos, nuevas, otra: w.dichos, activo: l.activo() };
}

// callar: el resto del turno ya no se dice, hasta un turno nuevo
{
  const v = vozFalsa();
  const l = L.crearLocutor({ voz: v });
  l.empezar(5);
  l.frase(F(0, 'Se va a cortar esta frase.'));
  l.frase(F(1, 'Y esta no se dice.'));
  await espera();
  l.callar();
  await espera();
  const tarde = l.frase(F(2, 'Ni esta, que llega tarde.'));
  const activo = l.activo();
  l.empezar(6);
  l.frase(F(0, 'Un turno nuevo sí se dice.'));
  await espera();
  out.callar = { dichos: v.dichos, callados: v.callados, tarde, activo, ref: v.refs.at(-1) };
}

// La narración toma la voz (decir resuelve 'cortada' sin que nadie la callara): se calla el turno
{
  const v = vozFalsa();
  const l = L.crearLocutor({ voz: v });
  l.empezar(5);
  l.frase(F(0, 'Empieza a sonar la respuesta.'));
  l.frase(F(1, 'Esta ya no suena.'));
  await espera();
  await v.terminar('cortada');
  l.frase(F(2, 'Ni esta.'));
  await espera();
  out.cedida = { dichos: v.dichos, activo: l.activo() };
}

// Con un plan sonando (ocupada), espera a que se pause; si sigue sonando pasado el plazo, el turno se calla
{
  const reloj = relojFalso();
  const v = vozFalsa();
  let plan = true;
  const l = L.crearLocutor({ voz: v, ocupada: () => plan, reloj });
  l.empezar(5);
  l.frase(F(0, 'Se dice cuando el plan se pausa.'));
  await reloj.avanzar(5000);
  const esperando = { dichos: [...v.dichos], activo: l.activo() };
  plan = false;   // la persona escribió: el plan se pausó al terminar su frase
  await reloj.avanzar(400);
  out.ocupada = { esperando, dichos: v.dichos };
  const w = vozFalsa();
  const m = L.crearLocutor({ voz: w, ocupada: () => true, reloj });
  m.empezar(5);
  m.frase(F(0, 'No llega a decirse: el plan nunca se pausa.'));
  await reloj.avanzar(L.ESPERA_NARRACION_MS + 500);
  out.ocupada.siempre = { dichos: w.dichos, activo: m.activo() };
}

// Una que falló se salta; sin conversación no se dice nada (llega con el `inicio`)
{
  const v = vozFalsa();
  const l = L.crearLocutor({ voz: v });
  l.empezar(null);
  const sin = l.frase(F(0, 'Todavía sin conversación.'));
  l.fijarConversacion(9);
  l.frase(F(0, 'Esta falla.'));
  l.frase(F(1, 'Esta sí se dice.'));
  await espera();
  await v.terminar('fallo');
  out.fallo = { sin, dichos: v.dichos, conversacion: v.refs.at(-1).conversacion };
}

out.validas = [F(0, 'Hola, buenos días.'), F(3, 'x'.repeat(400)), { n: 1, texto: 'Sí.', firma: 'A-_b'.repeat(10) + 'abc' }].map((f) => !!L.fraseValida(f));
out.invalidas = [{ n: -1, texto: 'Hola.', firma: 'f'.repeat(43) }, { n: 1.5, texto: 'Hola.', firma: 'f'.repeat(43) },
  { n: 1, texto: '', firma: 'f'.repeat(43) }, { n: 1, texto: '   ', firma: 'f'.repeat(43) }, { n: 1, texto: 'x'.repeat(401), firma: 'f'.repeat(43) },
  { n: 1, texto: 'Hola.', firma: 'corta' }, { n: 1, texto: 'Hola.', firma: '+'.repeat(43) }, { n: 1, texto: 'Hola.' }, null, 'frase']
  .map((f) => L.fraseValida(f));
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_locutor_de_las_respuestas(tmp_path):
    r = _node(tmp_path, NODE_LOCUTOR, LOCUTOR_JS.as_uri())
    o = r["orden"]
    assert o["antes"] == []   # la 1 espera a la 0
    assert o["dichos"] == ["Hay doce puestos en Yondó.", "Y eso es todo por ahora."]
    assert o["refs"][0] == {"conversacion": 5, "texto": "Hay doce puestos en Yondó.", "firma": FIRMA}
    assert o["preparados"] == [["Y eso es todo por ahora."]]
    assert o["avisos"] == [True, False] and o["hablando"] is True and o["despues"] is False and o["activo"] is True
    d = r["descartar"]
    assert d["dichos"] == ["Primera frase de la respuesta.", "Segunda frase de la respuesta.", "Otra segunda frase.",
                           "Otra tercera frase."]
    assert d["callados"] == 1
    dd = r["descartar_dicho"]
    assert dd["vieja"] is False
    assert dd["dichos"] == ["Frase número 0 de la respuesta.", "Frase número 1 de la respuesta.",
                            "Frase número 2 de la respuesta.", "La dos nueva sí.", "La tres."]
    # `frases_ronda`: tras una ronda rehecha más corta, la siguiente se dice entera (antes se saltaba «Después 2.»)
    ro = r["ronda"]
    assert ro["dichos"] == ["Vieja 0.", "Vieja 1.", "Vieja 2.", "Vieja 3.", "Después 2.", "Después 3.", "Después 4."]
    assert ro["nuevas"] == [False, False] and ro["activo"] is True
    assert ro["otra"] == ["La única de la ronda.", "La de la ronda siguiente."]
    c = r["callar"]
    assert c["dichos"] == ["Se va a cortar esta frase.", "Un turno nuevo sí se dice."] and c["callados"] >= 1
    assert c["tarde"] is False and c["activo"] is False and c["ref"]["conversacion"] == 6
    assert r["cedida"] == {"dichos": ["Empieza a sonar la respuesta."], "activo": False}
    assert r["ocupada"] == {"esperando": {"dichos": [], "activo": True}, "dichos": ["Se dice cuando el plan se pausa."],
                            "siempre": {"dichos": [], "activo": False}}
    assert r["fallo"] == {"sin": False, "dichos": ["Esta falla.", "Esta sí se dice."], "conversacion": 9}
    assert r["validas"] == [True, True, True] and r["invalidas"] == [None] * 10


NODE_PANEL = FALSOS + r"""
// El panel en /panel (servicio único), con un `fetch` que la prueba maneja y una ventana con eventos
const et = new EventTarget();
globalThis.window = globalThis;
globalThis.addEventListener = et.addEventListener.bind(et);
globalThis.removeEventListener = et.removeEventListener.bind(et);
globalThis.dispatchEvent = et.dispatchEvent.bind(et);
globalThis.document = { querySelector: (s) => (s === 'meta[name="panel-base"]' ? { content: '/panel' } : null), documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
const ahora = () => performance.now();
const { AudioContextFalso, registro } = audioFalso(ahora);
globalThis.AudioContext = AudioContextFalso;
const pedidos = [];
let estado = { voz: { disponible: true, nombre: 'Ana Inventada', respuestas: true, automatica: false } };
globalThis.fetch = async (u, o = {}) => {
  const ruta = String(u);
  const p = { ruta, metodo: o.method || 'GET', cuerpo: o.body ? JSON.parse(o.body) : null, cabeceras: o.headers || {} };
  pedidos.push(p);
  if (ruta === '/panel/api/agente/estado') return new Response(JSON.stringify(estado), { headers: { 'content-type': 'application/json' } });
  if (ruta === '/panel/api/agente/voz') {
    if (p.cuerpo?.rid === 'eeeeeeeeeeee') {
      return new Response(JSON.stringify({ detail: { codigo: 'sin_voz', mensaje: 'El asistente usa la voz del navegador.' } }), { status: 409, headers: { 'content-type': 'application/json' } });
    }
    const flujo = new ReadableStream({ start(c) { p.flujo = c; } });
    o.signal?.addEventListener('abort', () => { p.abortada = true; try { p.flujo.error(new Error('abort')); } catch {} });
    return new Response(flujo, { headers: { 'content-type': 'application/x-ndjson' } });
  }
  return new Response('{}', { status: 404, headers: { 'content-type': 'application/json' } });
};
const api = await import(process.argv[2]);
api.configurar({ token: 'tok-prueba', usuario: 'ana', uid: 3, rol: 'coordinador', permisos: ['*'] });
const P = await import(process.argv[3]);
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const linea = (p, ev) => p.flujo.enqueue(new TextEncoder().encode(JSON.stringify(ev) + '\n'));
const voces = (ruta) => pedidos.filter((p) => p.ruta === ruta);
const out = {};

// Sin el asistente (un rol que no lo usa): la voz de la ventana pide el estado ella misma, después de esperarlo un poco
{
  const v = P.tomarVoz('narracion');
  const enseguida = voces('/panel/api/agente/estado').length;
  await dormir(1500);
  out.sola = { enseguida, despues: voces('/panel/api/agente/estado').length, info: P.infoVoz(), motor: v.motor() };
  // Ajustes cambió algo: se vuelve a pedir
  estado = { voz: { disponible: false } };
  dispatchEvent(new Event('agente:estado'));
  await dormir(50);
  out.sola.releida = { pedidos: voces('/panel/api/agente/estado').length, info: P.infoVoz(), motor: v.motor() };
  v.soltar();
}

// Con el asistente, que trae el estado: no se pide aquí
{
  P.fijarInfoVoz({ disponible: true, nombre: '  Ana\u0007 Inventada  ', respuestas: true, automatica: 1 });
  const antes = voces('/panel/api/agente/estado').length;
  const n = P.tomarVoz('narracion');
  const r = P.tomarVoz('respuestas');
  await dormir(1500);
  dispatchEvent(new Event('agente:estado'));
  await dormir(50);
  out.compartida = { pedidos: voces('/panel/api/agente/estado').length - antes, info: P.infoVoz(), motor: n.motor() };
  n.activar();
  await dormir(10);
  r.activar();
  await dormir(10);
  out.compartida.contextos = registro.contextos.length;
  n.soltar();
  out.compartida.tras_uno = registro.contextos[0].state;
  r.soltar();
  out.compartida.tras_todos = registro.contextos[0].state;
  const otra = P.tomarVoz('narracion');
  otra.activar();
  await dormir(10);
  out.compartida.nueva = registro.contextos.length;
  otra.soltar();
}

// La narración manda; el audio se pide a /api/agente/voz con flujo (CSRF, NDJSON)
{
  let plan = true;
  const n = P.tomarVoz('narracion', { ocupada: () => plan });
  const r = P.tomarVoz('respuestas');
  n.activar();
  await dormir(10);
  const ref = { conversacion: 7, texto: 'Hay doce puestos.', firma: 'f'.repeat(43) };
  const conPlan = await r.decir('Hay doce puestos.', { ref });
  const sinPedir = voces('/panel/api/agente/voz').length;
  plan = false;
  const dicha = r.decir('Hay doce puestos.', { ref });
  await dormir(30);
  const pv = voces('/panel/api/agente/voz')[0];
  linea(pv, { tipo: 'inicio', formato: 'pcm_s16le', muestreo: 24000, canales: 1, cache: false, voz: 'Ana Inventada' });
  linea(pv, { tipo: 'audio', datos: pcm(400) });
  await dormir(300);
  const nivelRespuesta = (registro.nivel = 200, r.nivel());
  const nivelNarracion = n.nivel();
  // la vista que deja de narrar (o el reproductor entre pasos) no corta la respuesta
  n.callar();
  await dormir(20);
  let res = null;
  dicha.then((x) => { res = x; });
  await dormir(20);
  const sigue = res;
  // un plan que empieza (su primera precarga) sí
  n.preparar([{ texto: 'La primera del plan.', ref: { rid: 'abcdef123456', n: 1, frase: 0 } }]);
  await dormir(30);
  out.manda = { conPlan, sinPedir, sigue, res, nivelRespuesta: nivelRespuesta > 0, nivelNarracion,
    pedido: { metodo: pv.metodo, cuerpo: pv.cuerpo, csrf: pv.cabeceras['X-CSRF-Token'], acepta: pv.cabeceras.Accept },
    abortada: !!pv.abortada, precarga: voces('/panel/api/agente/voz').at(-1).cuerpo };
  n.callar();
  // sin_voz: la sesión sigue con la voz del navegador y se avisa `agente:estado`
  let avisado = 0;
  addEventListener('agente:estado', () => { avisado++; });
  const antes = voces('/panel/api/agente/estado').length;
  const cae = await n.decir('Un plan que ya no tiene voz clonada.', { ref: { rid: 'eeeeeeeeeeee', n: 1, frase: 0 } });
  await dormir(30);
  out.cae = { res: cae, motor: n.motor(), avisado, releyo: voces('/panel/api/agente/estado').length - antes };
  n.soltar();
  r.soltar();
}

// La narración (o la prueba) toma la voz con una respuesta sonando y su frase siguiente precargada: las dos peticiones
// de la respuesta se cortan (se pagaban sin oírse) y la precarga de la narración tiene su lugar
for (const quien of ['narracion', 'prueba']) {
  const n = P.tomarVoz('narracion');
  const r = P.tomarVoz('respuestas');
  const otra = quien === 'prueba' ? P.tomarVoz('prueba') : null;
  n.activar();
  await dormir(10);
  const antes = voces('/panel/api/agente/voz').length;
  let resUno = null;
  r.decir('Uno.', { ref: { conversacion: 7, texto: 'Uno.', firma: 'f'.repeat(43) } }).then((x) => { resUno = x; });
  await dormir(20);
  r.preparar([{ texto: 'Dos.', ref: { conversacion: 7, texto: 'Dos.', firma: 'f'.repeat(43) } }]);
  await dormir(20);
  if (otra) otra.decir('', { ref: { prueba: true } });
  else {
    n.decir('La frase del plan.', { ref: { rid: 'abcdef123456', n: 1, frase: 0 } });
    n.preparar([{ texto: 'La siguiente del plan.', ref: { rid: 'abcdef123456', n: 1, frase: 1 } }]);
  }
  await dormir(30);
  const ps = voces('/panel/api/agente/voz').slice(antes);
  out[`toma_${quien}`] = { cuerpos: ps.map((p) => p.cuerpo), abortadas: ps.map((p) => !!p.abortada), resUno };
  (otra || n).callar();
  for (const v of [n, r, otra]) v?.soltar();
  await dormir(10);
}

// Lo que llega en el estado se limpia; lo que no tiene la forma es «sin voz»
out.estados = [{ disponible: true, nombre: 'x'.repeat(80), respuestas: true, automatica: true }, { disponible: 'si' }, null, [1],
  { disponible: true, nombre: 7 }].map((v) => P.vozDelEstado(v));
let error = null;
try { P.tomarVoz('otra'); } catch (e) { error = e.message; }
out.quien = error;
console.log(JSON.stringify(out));
"""


@requiere_node
def test_una_sola_voz_por_ventana(tmp_path):
    r = _node(tmp_path, NODE_PANEL, (JS / "api.js").as_uri(), PANEL_JS.as_uri())
    voz = {"disponible": True, "nombre": "Ana Inventada", "respuestas": True, "automatica": False}
    s = r["sola"]
    assert s["enseguida"] == 0 and s["despues"] == 1 and s["info"] == voz and s["motor"] == "clonada"
    sin = {"disponible": False, "nombre": None, "respuestas": False, "automatica": False}
    assert s["releida"] == {"pedidos": 2, "info": sin, "motor": "navegador"}
    c = r["compartida"]
    # con el asistente: su estado (limpio), sin pedirlo aquí; una sola voz para las dos, que se suelta con la última
    assert c["pedidos"] == 0 and c["info"] == {"disponible": True, "nombre": "Ana Inventada", "respuestas": True,
                                               "automatica": False}
    assert c["motor"] == "clonada" and c["contextos"] == 1 and c["tras_uno"] == "running" and c["tras_todos"] == "closed"
    assert c["nueva"] == 2
    m = r["manda"]
    assert m["conPlan"] == "cortada" and m["sinPedir"] == 0
    assert m["pedido"] == {"metodo": "POST", "cuerpo": {"conversacion": 7, "texto": "Hay doce puestos.", "firma": FIRMA},
                           "csrf": "tok-prueba", "acepta": "application/x-ndjson"}
    assert m["sigue"] is None and m["res"] == "cortada" and m["abortada"] is True
    assert m["nivelRespuesta"] is True and m["nivelNarracion"] == 0
    assert m["precarga"] == {"rid": "abcdef123456", "n": 1, "frase": 0}
    assert r["cae"] == {"res": "fallo", "motor": "navegador", "avisado": 1, "releyo": 0}
    # La narración toma la voz: la frase de la respuesta y su precarga se cortan (las dos), y la narración pide la suya y
    # la siguiente; la prueba de Ajustes, igual
    uno = {"conversacion": 7, "texto": "Uno.", "firma": FIRMA}
    dos = {"conversacion": 7, "texto": "Dos.", "firma": FIRMA}
    assert r["toma_narracion"] == {"cuerpos": [uno, dos, {"rid": "abcdef123456", "n": 1, "frase": 0},
                                               {"rid": "abcdef123456", "n": 1, "frase": 1}],
                                   "abortadas": [True, True, False, False], "resUno": "cortada"}
    assert r["toma_prueba"] == {"cuerpos": [uno, dos, {"prueba": True}], "abortadas": [True, True, False],
                                "resUno": "cortada"}
    assert r["estados"][0] == {"disponible": True, "nombre": "x" * 60, "respuestas": True, "automatica": True}
    assert r["estados"][1:4] == [sin] * 3 and r["estados"][4]["nombre"] is None
    assert "narracion, respuestas, prueba" in r["quien"]


NODE_REPRODUCTOR = FALSOS + r"""
const { crearReproductor } = await import(process.argv[2]);
// Una voz que precarga: cada frase empieza a los 10 ms y termina a los 500
function vozPrecarga(reloj) {
  const v = { eventos: [], estado: () => 'activa',
    callar() { const p = v.p; v.p = null; p?.('cortada'); },
    decir(t, { alEmpezar, ref } = {}) {
      v.eventos.push(['decir', t, ref ?? null]);
      return new Promise((ok) => { v.p = ok; reloj.programar(() => alEmpezar?.(), 10); reloj.programar(() => { if (v.p === ok) { v.p = null; ok('dicha'); } }, 500); });
    },
    preparar(items) { v.eventos.push(['preparar', items.map((x) => [x.texto, x.ref])]); } };
  return v;
}
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const esc = (paso, frases) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, mover: null, animar: false, frases, sostener_ms: 1300 });
const out = {};
for (const [nombre, plan, previa] of [
  ['con_cierre', { id: 'abcdef123456', titulo: 'Prueba', cierre: { puntos: ['Uno', 'Dos'] }, escenas: [esc(1, ['Frase uno.', 'Frase dos.']), esc(2, ['Frase tres.'])] }, 1800],
  ['automatica', { id: 'bbbbbbbbbbbb', titulo: 'Salud', auto: true, cierre: null, escenas: [esc(1, ['Solo una.'])] }, 0],
]) {
  const reloj = relojFalso();
  const voz = vozPrecarga(reloj);
  const rep = crearReproductor({ reloj, voz, orden: async () => ({ ok: true }) });
  rep.iniciar(plan, { previa });
  await reloj.avanzar(60000);
  out[nombre] = { eventos: voz.eventos, activo: rep.activo() };
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_reproductor_da_la_referencia_y_precarga_lo_que_sigue(tmp_path):
    r = _node(tmp_path, NODE_REPRODUCTOR, REPRODUCTOR_JS.as_uri())
    rid = "abcdef123456"
    f = lambda n, k, t: [t, {"rid": rid, "n": n, "frase": k}]  # noqa: E731
    cierre = ["En resumen. Uno. Dos", {"rid": rid, "cierre": True}]
    assert r["con_cierre"]["eventos"] == [
        ["preparar", [f(1, 0, "Frase uno.")]],           # en la espera del plan nuevo
        ["preparar", [f(1, 0, "Frase uno.")]],           # al aplicar la escena
        ["decir", *f(1, 0, "Frase uno.")], ["preparar", [f(1, 1, "Frase dos.")]],
        ["decir", *f(1, 1, "Frase dos.")], ["preparar", [f(2, 0, "Frase tres.")]],
        ["preparar", [f(2, 0, "Frase tres.")]],
        ["decir", *f(2, 0, "Frase tres.")], ["preparar", [cierre]],
        ["decir", *cierre],
    ], r["con_cierre"]["eventos"]
    assert r["con_cierre"]["activo"] is False
    # el plan de la presentación automática no tiene resumen: después de su última frase no hay nada que precargar
    assert r["automatica"]["eventos"] == [["preparar", [["Solo una.", {"rid": "bbbbbbbbbbbb", "n": 1, "frase": 0}]]],
                                          ["decir", "Solo una.", {"rid": "bbbbbbbbbbbb", "n": 1, "frase": 0}]]


NODE_AUTO_SIN_CLONADA = FALSOS + r"""
// El plan de la presentación automática con `automatica` apagado en Ajustes (la vista le quita la referencia: va con la
// voz del navegador), en un navegador sin voces en español y con el audio de la ventana andando
const { crearReproductor } = await import(process.argv[2]);
const V = await import(process.argv[3]);
const VI = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const esc = (paso, frases) => ({ capitulo: 'salud', paso, panel: true, visual: VI, resaltar: null, mover: null, animar: false, frases, sostener_ms: 1300 });
const out = {};
for (const nombre of ['vista', 'sin_su_estado']) {
  const reloj = relojFalso();
  const { AudioContextFalso } = audioFalso(reloj.ahora);
  const srv = servidorFalso();
  const respaldo = respaldoFalso();
  respaldo.e = 'sin_voces';
  respaldo.resultado = 'fallo';
  const voz = V.crearVozClonada({ ventana: { AudioContext: AudioContextFalso, atob, AbortController, addEventListener() {},
    removeEventListener() {} }, pedir: srv.pedir, respaldo, almacen: almacenFalso(), reloj, disponible: () => true });
  voz.activar();
  await reloj.avanzar(1);
  let rep = null;
  const sinClonada = () => rep.recorrido()?.auto === true;
  // como `vozConBoca` de vistas/presentacion.js (y, para comparar, sin su `estado`)
  const conVista = { ...voz,
    ...(nombre === 'vista' ? { estado: () => (sinClonada() ? voz.estadoNavegador() : voz.estado()) } : {}),
    decir: (t, o = {}) => voz.decir(t, { ...o, ...(sinClonada() ? { ref: null } : {}) }),
    preparar: (items) => { if (!sinClonada()) voz.preparar(items); } };
  const progresos = [];
  rep = crearReproductor({ reloj, voz: conVista, orden: async () => ({ ok: true }), avisar: (p) => progresos.push(p) });
  rep.iniciar({ id: 'bbbbbbbbbbbb', titulo: 'Salud', auto: true, cierre: null, escenas: [esc(1, ['Solo una frase.', 'Y otra más.'])] },
    { previa: 0 });
  await reloj.avanzar(60000);
  out[nombre] = { avisos: progresos.filter((p) => p.aviso === 'voz').length, voces: [...new Set(progresos.map((p) => p.voz))],
    dichos: respaldo.dichos, pedidos: srv.pedidos.length, fin: progresos.at(-1)?.fase };
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_plan_automatico_sin_la_voz_clonada_usa_el_estado_del_navegador(tmp_path):
    r = _node(tmp_path, NODE_AUTO_SIN_CLONADA, REPRODUCTOR_JS.as_uri(), CLONADA_JS.as_uri())
    # Con el estado de la voz del navegador (sin voces): se lee en silencio, sin «la voz no pudo hablar» en cada frase,
    # y el avance dice 'sin_voces'
    assert r["vista"] == {"avisos": 0, "voces": ["sin_voces"], "dichos": [], "pedidos": 0, "fin": "fin"}
    # Con el de la voz clonada (lo de antes): 'activa', y un aviso por frase sin que suene nada
    assert r["sin_su_estado"]["avisos"] == 2 and r["sin_su_estado"]["voces"] == ["activa"]
    assert r["sin_su_estado"]["pedidos"] == 0


# ───────────────────────────── Lo estático ─────────────────────────────

def test_los_modulos_puros_no_dependen_del_panel():
    for f in (CLONADA_JS, LOCUTOR_JS):
        js = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*import\b", js, re.M), f"{f.name} no importa nada"
        for prohibido in ("innerHTML", "insertAdjacentHTML", "eval(", "document.", "sessionStorage", "fetch(",
                          "speechSynthesis", "console.log"):
            assert prohibido not in js, (f.name, prohibido)
        # el almacenamiento, solo el de la ventana que llega por parámetro (como voz.js): nunca el global
        assert not re.search(r"(?<![\w.])localStorage\b", js), f.name
    assert re.search(r"^export function crearVozClonada\(\{ ventana = globalThis, pedir = null, respaldo = null, almacen = null,",
                     CLONADA_JS.read_text(encoding="utf-8"), re.M)
    assert re.search(r"^export function crearLocutor\(\{ voz, ocupada = \(\) => false, alHablar = \(\) => \{\}, reloj = relojDelNavegador \} = \{\}\)",
                     LOCUTOR_JS.read_text(encoding="utf-8"), re.M)
    # La voz de la ventana pide el audio con `flujo` de api.js (CSRF, reingreso, NDJSON) y solo a esta ruta
    panel = PANEL_JS.read_text(encoding="utf-8")
    assert "export const RUTA_VOZ = '/api/agente/voz';" in panel
    assert "flujo(RUTA_VOZ, ref, { signal, alEvento, inactividad: INACTIVIDAD_MS })" in panel
    assert "const INACTIVIDAD_MS = 20000;" in panel and 20000 > voz_srv.LATIDO_S * 1000
    assert "localStorage" not in panel and "innerHTML" not in panel


def test_el_chat_lee_las_respuestas_en_voz_alta():
    codigo = _sin_comentarios(AGENTE_JS)
    # El botón, en el encabezado, con su estado para los lectores de pantalla; solo íconos de ui.js en la plantilla
    assert ('id="agente-hablar" aria-pressed="false" aria-label="Leer las respuestas en voz alta" '
            'title="Leer las respuestas en voz alta" hidden>${icono(\'voz\')}</button>') in AGENTE_JS
    assert "const puedeHablar = () => !!info?.disponible && info.voz.disponible && info.voz.respuestas;" in codigo
    # La preferencia va en la pestaña (yj_agente), nunca en localStorage
    assert "JSON.stringify({ abierto, conversacion: conv, uid: sesion.uid, hablar })" in codigo
    assert "hablar: g.hablar === true" in codigo and "localStorage" not in AGENTE_JS
    # El turno pide la voz con el botón encendido o si la pregunta llegó por voz; la confirmación también
    assert "const leer = puedeHablar() && (hablar || vozEntregando) && !vozApagada();" in codigo
    assert "const leer = puedeHablar() && hablar && !vozApagada();" in codigo
    # Con la voz de la ventana apagada (el botón «Voz» de la presentación) el botón se ve apagado y no se pide la
    # respuesta hablada; lo sigue (alCambiar), y un toque la vuelve a encender
    assert "const si = puede && hablar && !vozApagada();" in codigo
    assert "v.alCambiar(() => aplicarHablar());" in codigo and "return v.estado() === 'apagada';" in codigo
    assert "hablar = !hablar || apagada;" in codigo and "if (apagada) v.encender(); else v.activar();" in codigo
    assert "contexto: contexto({ voz: leer })" in codigo and "...(voz ? { voz: true } : {})," in codigo
    assert "...(leer ? { voz: true } : {})" in codigo
    # Las frases y su resincronización van al locutor; la voz es la de la ventana
    assert "case 'frase': if (t.hablar && turno === t) locutor.frase(ev); break;" in codigo
    assert "case 'frases_descartar': if (t.hablar && turno === t) locutor.descartar(ev.desde); break;" in codigo
    assert "case 'frases_ronda': if (t.hablar && turno === t) locutor.ronda(ev.desde); break;" in codigo
    assert "tomarVoz('respuestas')" in codigo and "fijarInfoVoz(info.voz);" in codigo
    assert "voz: vozDelEstado(o.voz)," in codigo
    # Se calla: el micrófono (antes del permiso), escribir, enviar, Detener, Escape, cerrar, otra conversación, un plan
    clic = codigo[codigo.index("vozBtn.addEventListener('click'"):]
    assert clic.index("locutor.callar();") < clic.index("dictado.empezar()")
    assert "if (oyendo) locutor.callar();" in codigo
    assert "entrada.addEventListener('input', () => locutor.callar());" in codigo
    enviar = codigo[codigo.index("async function enviar("):codigo.index("function marcarInterrumpidas()")]
    assert enviar.index("pausaPorMensaje();") < enviar.index("locutor.callar();") < enviar.index("await correr(")
    detener = codigo[codigo.index("detenerBtn.addEventListener('click'"):]
    assert detener.index("locutor.callar();") < detener.index("turno.control.abort();")
    teclas = codigo[codigo.index("panel.addEventListener('keydown'"):]
    assert teclas.index("if (vozActiva()) { dictado.cancelar(); return; }") < teclas.index(
        "if (locutor.hablando()) { locutor.callar(); return; }") < teclas.index("cerrar({ foco: true })")
    for funcion in ("function cerrar(", "function limpiarConversacion()", "function ocultar()"):
        cuerpo = codigo[codigo.index(funcion):]
        assert "locutor.callar();" in cuerpo[:cuerpo.index("\n  }\n")], funcion
    assert "if (t.hablar && ponePlan(ev.accion)) locutor.callar();" in codigo
    assert "window.addEventListener('pagehide', () => locutor.callar());" in codigo
    # Con un plan sonando aquí (o en el proyector), que no está en pausa, las respuestas esperan
    assert ("ocupada: () => { const r = recorridoEnCurso(); return !!r && r.fase !== 'pausa' && (r.donde === 'aqui' "
            "|| proyectorVivo()); },") in codigo


def test_ajustes_elige_la_voz_del_asistente():
    codigo = _sin_comentarios(AJUSTES_JS)
    assert "'mnemo:voice': 'Hablar con sus voces clonadas (narrar y leer respuestas)'" in codigo
    # Las voces se piden solo al administrador y con una conexión que las puede usar (si no, el servidor no le
    # pregunta nada a Mnemo y el coordinador recibiría un 403)
    assert ("const voces = puede('agente.conectar') && conexion?.estado === 'conectada' && conexion.voz === true\n"
            "      ? await api.get('/api/agente/voces').catch((error) => ({ error })) : null;") in codigo
    # Se guarda como `agente_voz` (con el nombre que dio Mnemo), y el coordinador lo ve en solo lectura
    assert "await guardar({ agente_voz: { motor, voz, ...(nombre ? { nombre } : {}), roles, respuestas: v.respuestas === true," in codigo
    assert "for (const id of ['#f-politica', '#f-limites', '#f-agente', '#f-voz']) {" in codigo
    # «Probar voz»: la frase fija, con la voz de la ventana, en el clic (sin esperas antes: es el gesto del audio)
    clic = codigo[codigo.index("el.addEventListener('click', async (e) => {"):]
    assert clic.index("if (pv) { probarVoz(pv); return; }") < clic.index("await ")
    probar = codigo[codigo.index("function probarVoz(boton) {"):codigo.index("function horario(f) {")]
    assert "vozPrueba ||= tomarVoz('prueba');" in probar and "ref: { prueba: true }," in probar
    assert "Primer audio en ${num(primer)} ms en este navegador (Mnemo: ${mnemo})." in probar
    assert "return () => { vozPrueba?.soltar(); vozPrueba = null; };" in codigo
    # Lo que se dice de la voz: sintética, biométrica, y qué va a Mnemo
    assert "Voz sintética</span>" in AJUSTES_JS and "dato biométrico de su dueño" in AJUSTES_JS
    assert "Hablar con las voces que clonaste en Mnemo…" in AJUSTES_JS


def test_la_presentacion_narra_con_la_voz_de_la_ventana():
    assert "import { infoVoz, tomarVoz } from '../voz-panel.js';" in VISTA_JS
    assert "const voz = tomarVoz('narracion', { ocupada: () => rep.activo() && !rep.pausado() });" in VISTA_JS
    # El plan de la presentación automática va con la voz del navegador si Ajustes no deja narrarla con la clonada
    assert "const sinClonada = () => rep.recorrido()?.auto === true && !infoVoz().automatica;" in VISTA_JS
    assert "...(sinClonada() ? { ref: null } : {})" in VISTA_JS
    assert "preparar: (items) => { if (!sinClonada()) voz.preparar(items); } };" in VISTA_JS
    # y su estado es el de la voz del navegador (sin voces, el reproductor lee en silencio), también en el botón «Voz»
    assert "estado: () => (sinClonada() ? voz.estadoNavegador() : voz.estado())," in VISTA_JS
    assert "const e = vozConBoca.estado();" in VISTA_JS
    assert "if (vozConBoca.estado() === 'activa') voz.apagar(); else voz.encender();" in VISTA_JS
    # La boca y el botón siguen como antes (test_presentador.py, test_plan_guiado.py)
    assert "orden, voz: vozConBoca," in VISTA_JS and "limpiezas.push(() => voz.soltar());" in VISTA_JS
