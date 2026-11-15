"""Las preguntas por voz del asistente (docs/agente.md, «Preguntas por voz»). Solo datos inventados; nunca se llama a
Mnemo ni se usa un micrófono de verdad.

* `web/js/dictado.js`, con Node, un reloj falso y medios falsos (un `MediaRecorder`, un `AudioContext` con su
  `AnalyserNode`, cuyo nivel maneja la prueba, y un `SpeechRecognition`): la vía 1 corta sola a los 1,6 s de silencio
  después de haber oído voz (no antes de oírla, no en una pausa corta, y el ruido parejo del lugar o el toque en el
  botón no cuentan como voz), tiene un tope de 60 s, descarta lo muy corto y lo que nunca tuvo voz (sin transcribir
  nada), suelta el micrófono antes de transcribir, se cancela (oyendo o transcribiendo) y dice por qué no pudo (el
  permiso negado, sin micrófono, un error del panel con su mensaje). La vía 2 usa `es-CO` con resultados parciales, y
  se llega a ella si el panel dice que no transcribe, si no hay `MediaRecorder` o tras un 409 `sin_transcriptor` (la
  pregunta se repite, y la próxima vez va directo). Sin medidor de nivel no hay corte solo.
* `app/agente/dictado.py` y `POST /api/agente/transcribir`, con un Mnemo falso (el MCP falso de ayudas_mcp.py con la
  herramienta `mnemo_transcribe`, detrás de un `ClienteMnemo` de verdad): la respuesta, lo que se le manda a Mnemo, y
  409 `sin_transcriptor` (sin conexión, sin el alcance, sin la herramienta, `no_transcriber`), 413, 415, 422, 402, 429 y
  502. La ruta se monta en una aplicación mínima con su `requiere("agente.usar")` sustituido y la conexión con Mnemo
  simulada (`dictado._preparar`): la sesión y la conexión de verdad necesitan MongoDB (las cubren test_agente_api.py
  y test_agente_conexion.py). Aquí sí se comprueba que la ruta declara ese permiso.
* `mnemo_transcribe` no se le ofrece al modelo (`NUNCA` de herramientas/mnemo.py), ni con `*` ni nombrada.
* El panel: el micrófono del cuadro de escribir, lo que hace con el texto y la franja de la presentación automática
  (lo estático de agente.js y agente-recorrido.js, y la franja con un DOM mínimo).
* Lo que la voz necesita del resto del panel y no es de estos archivos (`app/seguridad.py`): que la política de
  permisos deje usar el micrófono a la propia página y que la guardia deje pasar un audio de hasta 2 MB. Mientras no
  esté, esas dos pruebas quedan marcadas como fallo esperado.
"""
import asyncio
import base64
import json
import logging
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from ayudas_mcp import LECTURA, TOKEN, MnemoFalso, correcto, fallo, herramienta
from test_agente_presentacion import requiere_node

from app import acceso
from app.agente import dictado, politica, proveedores
from app.agente import mnemo_cliente as mc
from app.agente.herramientas import mnemo
from app.agente.herramientas.base import ErrorHerramienta
from app.api import agente as agente_api

ADMIN = Path(__file__).resolve().parents[1]
JS = ADMIN / "web" / "js"
DICTADO_JS = JS / "dictado.js"
URL = "https://mnemo.example.org/mcp"
PREGUNTA = "¿Cuántas personas hay en el barrio Tres de Octubre?"
AUDIO = b"\x1aE\xdf\xa3" + bytes(range(256)) * 8   # no es un audio de verdad: nadie lo decodifica aquí


# ───────────────────────────── dictado.js con Node ─────────────────────────────

NODE = r"""
const { crearDictado, soporteDeDictado, textoDeEstado, limpiar, SILENCIO_MS, TOPE_MS, MINIMO_MS, SIN_VOZ_MS, SIN_ARRANQUE_MS, TICK_MS,
  IDIOMA, MAX_TEXTO } = await import(process.argv[2]);
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
// Una ventana con medios falsos. `nivel(t)` es lo que suena en el micrófono en el instante t del reloj (RMS, de 0 a 1)
function ventana(reloj, { nivel = () => 0, permiso = 'ok', grabar = true, reconocer = true, audio = 'running', politica = null, segura, srMudo = false } = {}) {
  const reg = { pedidos: 0, pistasParadas: 0, grabadoras: [], contextos: 0, cerrados: 0, sr: [] };
  const flujo = () => ({ getTracks: () => [{ stop() { reg.pistasParadas++; } }] });
  class MediaRecorder {
    static isTypeSupported(t) { return t === 'audio/webm;codecs=opus'; }
    constructor(f, op) { this.op = op || {}; this.mimeType = this.op.mimeType || ''; this.state = 'inactive'; reg.grabadoras.push(this); }
    start(ms) { this.state = 'recording'; this.inicio = reloj.ahora(); this.trozo = ms; }
    // como el navegador: el último trozo y después `stop`, en otra vuelta. 3 bytes por milisegundo: 24 kbps
    stop() { if (this.state === 'inactive') throw new Error('inactiva'); this.state = 'inactive';
      const ms = reloj.ahora() - this.inicio;
      setImmediate(() => { this.ondataavailable?.({ data: new Blob([new Uint8Array(Math.round(ms * 3))]) }); this.onstop?.(); }); }
  }
  class AudioContext {
    constructor() { this.state = audio; reg.contextos++; }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 0, getByteTimeDomainData(buf) { const a = nivel(reloj.ahora());
      for (let i = 0; i < buf.length; i++) buf[i] = 128 + Math.round((i % 2 ? 1 : -1) * a * 127); } }; }
    resume() { return Promise.resolve(); }
    close() { reg.cerrados++; return Promise.resolve(); }
  }
  class SpeechRecognition {
    constructor() { reg.sr.push(this); this.paradas = 0; this.abortos = 0; }
    start() { this.iniciado = true; if (!srMudo) setImmediate(() => this.onstart?.()); }
    stop() { this.paradas++; setImmediate(() => this.onend?.()); }
    abort() { this.abortos++; }
    // lo que maneja la prueba: [[texto, ¿final?], …], un error y el final
    resultado(lista) { this.onresult?.({ results: lista.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f })) }); }
    error(e) { this.onerror?.({ error: e }); this.onend?.(); }
    fin() { this.onend?.(); }
  }
  const medios = { getUserMedia(c) { reg.pedidos++; reg.restricciones = c;
    if (permiso === 'ok') return Promise.resolve(flujo());
    return Promise.reject(Object.assign(new Error('no'), { name: permiso })); } };
  const v = { navigator: { mediaDevices: medios }, Blob, ...(audio ? { AudioContext } : {}), ...(grabar ? { MediaRecorder } : {}),
    ...(reconocer ? { webkitSpeechRecognition: SpeechRecognition } : {}),
    ...(politica ? { document: { featurePolicy: { allowsFeature: (f) => politica(f) } } } : {}),
    ...(segura === undefined ? {} : { isSecureContext: segura }) };
  return { v, reg };
}
// Un dictado armado: los estados resumidos («escuchando», «error:vacio»…), los textos y lo que se mandó a transcribir
function armar(op = {}, { transcribir, servidor } = {}) {
  const reloj = relojFalso();
  const { v, reg } = ventana(reloj, op);
  const estados = [], textos = [], enviados = [], niveles = [], crudos = [];
  const d = crearDictado({ ventana: v, reloj, ...(servidor === undefined ? {} : { servidor }),
    transcribir: transcribir === null ? null : async (blob, extra) => {
      enviados.push({ tipo: blob.type, bytes: blob.size, ms: extra.duracion_ms, en: reloj.ahora(), pistas: reg.pistasParadas, cerrados: reg.cerrados });
      return transcribir ? transcribir(blob, extra, reloj) : '  ¿Cuántas personas\n hay en   Tres de Octubre?  ';
    },
    alEstado: (e) => { crudos.push(e); if (e.estado === 'escuchando') niveles.push([reloj.ahora(), e.nivel]);
      const s = e.estado + (e.motivo ? ':' + e.motivo : ''); if (estados.at(-1) !== s) estados.push(s); },
    alTexto: (t, x) => { textos.push([t, x.via, d.estado().estado]); estados.push('texto'); } });
  return { reloj, reg, d, estados, textos, enviados, niveles, crudos };
}
const voz = (...tramos) => (t) => (tramos.some(([a, b]) => t >= a && t < b) ? 0.2 : 0.002);
const out = { tiempos: { SILENCIO_MS, TOPE_MS, MINIMO_MS, SIN_VOZ_MS, TICK_MS }, idioma: IDIOMA };

// 1. Corta sola: un segundo callada, dos hablando y silencio. El silencio de antes de hablar no la corta
{
  const x = armar({ nivel: voz([1000, 3000]) });
  const arranco = x.d.empezar();
  await x.reloj.avanzar(4400);
  const antes = { estado: x.d.estado().estado, enviados: x.enviados.length, pistas: x.reg.pistasParadas };
  await x.reloj.avanzar(600);
  const fuerte = Math.min(...x.niveles.filter(([t]) => t >= 1100 && t <= 2900).map(([, n]) => n));
  const callado = Math.max(...x.niveles.filter(([t]) => t < 1000 || t > 3100).map(([, n]) => n));
  out.corte = { arranco, antes, estados: x.estados, textos: x.textos, enviados: x.enviados, fuerte, callado,
    restricciones: x.reg.restricciones, grabadora: x.reg.grabadoras[0].op, trozo: x.reg.grabadoras[0].trozo, contextos: x.reg.contextos,
    final: x.d.estado(), enRango: x.niveles.every(([, n]) => n >= 0 && n <= 1) };
}
// 2. Una pausa corta al hablar (1,2 s) no la corta: termina 1,6 s después de la última voz
{
  const x = armar({ nivel: voz([500, 1500], [2700, 3500]) });
  x.d.empezar();
  await x.reloj.avanzar(3300);
  const enLaPausa = x.d.estado().estado;
  await x.reloj.avanzar(3000);
  out.pausa = { enLaPausa, enviados: x.enviados, textos: x.textos.length };
}
// 3. El ruido parejo del lugar no es voz: con ruido antes y después, corta 1,6 s después de la voz
{
  const x = armar({ nivel: (t) => (t >= 2000 && t < 4000 ? 0.2 : 0.03) });
  x.d.empezar();
  await x.reloj.avanzar(7000);
  out.ruido = { enviados: x.enviados, estados: x.estados };
}
// 4. El tope: quien no deja de hablar llega a 60 s y ahí se transcribe
{
  const x = armar({ nivel: () => 0.2 });
  x.d.empezar();
  await x.reloj.avanzar(59900);
  const antes = [x.d.estado().estado, x.enviados.length];
  await x.reloj.avanzar(300);
  out.tope = { antes, enviados: x.enviados, textos: x.textos.length };
}
// 5. Nadie habla: a los 10 s termina sin transcribir nada (ni el toque en el botón, que suena al empezar, cuenta)
{
  const x = armar({ nivel: (t) => (t < 250 ? 0.5 : 0.002) });
  x.d.empezar();
  await x.reloj.avanzar(9800);
  const antes = x.d.estado().estado;
  await x.reloj.avanzar(400);
  out.sin_voz = { antes, estados: x.estados, enviados: x.enviados.length, final: x.d.estado(), pistas: x.reg.pistasParadas, cerrados: x.reg.cerrados,
    texto: textoDeEstado(x.d.estado()) };
}
// 6. Muy corto (un toque doble): se descarta. Y terminar a mano con voz: se transcribe lo oído
{
  const x = armar({ nivel: () => 0.2 });
  x.d.empezar();
  await x.reloj.avanzar(300);
  x.d.terminar();
  await x.reloj.avanzar(100);
  const y = armar({ nivel: voz([300, 5000]) });
  y.d.empezar();
  await y.reloj.avanzar(1500);
  y.d.terminar();
  await y.reloj.avanzar(100);
  // sin haber oído voz, pero la persona terminó a mano: se transcribe igual (el medidor puede no oír a quien habla bajo)
  const z = armar({ nivel: () => 0.002 });
  z.d.empezar();
  await z.reloj.avanzar(2000);
  z.d.terminar();
  await z.reloj.avanzar(100);
  out.manual = { corto: [x.estados, x.enviados.length, x.d.estado()], aMano: [y.estados, y.enviados], sinVoz: z.enviados.length };
}
// 7. Cancelar oyendo: nada se transcribe y el micrófono queda libre. Cancelar transcribiendo: el texto ya no llega
{
  const x = armar({ nivel: voz([300, 5000]) });
  x.d.empezar();
  await x.reloj.avanzar(1000);
  x.d.cancelar();
  const enElActo = [x.d.estado().estado, x.reg.pistasParadas, x.reg.cerrados];
  await x.reloj.avanzar(5000);
  let soltar, senal;
  const y = armar({ nivel: voz([300, 1000]) }, { transcribir: (b, extra) => { senal = extra.signal; return new Promise((ok) => { soltar = ok; }); } });
  y.d.empezar();
  await y.reloj.avanzar(3000);
  const transcribiendo = y.d.estado().estado;
  y.d.terminar();   // transcribiendo, «terminar» no hace nada
  y.d.cancelar();
  const abortada = senal.aborted;
  soltar('texto que llega tarde');
  await y.reloj.avanzar(100);
  // cancelar mientras el navegador pregunta por el permiso: el micrófono que llega después se suelta sin grabar
  const z = armar();
  z.d.empezar();
  z.d.cancelar();
  await z.reloj.avanzar(500);
  out.cancelar = { oyendo: { enElActo, estados: x.estados, enviados: x.enviados.length, textos: x.textos.length },
    transcribiendo: { transcribiendo, abortada, estados: y.estados, textos: y.textos.length, final: y.d.estado().estado },
    pidiendo: { estados: z.estados, pistas: z.reg.pistasParadas, grabadoras: z.reg.grabadoras.length } };
}
// 8. El permiso negado, sin micrófono, y que desde el error se puede volver a empezar
{
  const x = armar({ permiso: 'NotAllowedError' });
  x.d.empezar();
  await x.reloj.avanzar(100);
  const y = armar({ permiso: 'NotFoundError' });
  y.d.empezar();
  await y.reloj.avanzar(100);
  const negado = [x.estados.slice(), x.d.estado(), textoDeEstado(x.d.estado())];
  out.permiso = { negado, sin: y.d.estado(), otraVez: x.d.empezar() };
}
// 9. La vía 2: el panel dice que no transcribe (o no hay MediaRecorder). es-CO, parciales, y el texto final
{
  const x = armar({}, { servidor: () => false });
  x.d.empezar();
  await x.reloj.avanzar(10);
  const r = x.reg.sr[0];
  const config = { lang: r.lang, parciales: r.interimResults, continuo: r.continuous };
  const alEmpezar = x.d.estado();
  r.resultado([['cuántas personas', false]]);
  const parcial = x.d.estado();
  r.resultado([['¿Cuántas personas hay', true], [' en Tres de Octubre', false]]);
  const medio = x.d.estado().parcial;
  r.resultado([['¿Cuántas personas hay', true], [' en Tres de Octubre?', true]]);
  r.fin();
  const y = armar({ grabar: false });
  y.d.empezar();
  await y.reloj.avanzar(10);
  out.via2 = { config, alEmpezar, parcial, medio, estados: x.estados, textos: x.textos, pedidos: x.reg.pedidos, enviados: x.enviados.length,
    aviso: textoDeEstado(alEmpezar), sinGrabadora: [y.d.estado().via, y.reg.sr.length, y.reg.pedidos] };
}
// 10. La vía 2: terminar a mano entrega lo que iba, el tope la para, cancelar la aborta, y sus errores
{
  const x = armar({}, { servidor: false });
  x.d.empezar();
  await x.reloj.avanzar(10);
  x.reg.sr[0].resultado([['solo un parcial', false]]);
  x.d.terminar();
  await x.reloj.avanzar(10);
  const y = armar({}, { servidor: false });
  y.d.empezar();
  await y.reloj.avanzar(TOPE_MS - 100);
  const antes = y.reg.sr[0].paradas;
  await y.reloj.avanzar(200);
  const z = armar({}, { servidor: false });
  z.d.empezar();
  await z.reloj.avanzar(10);
  z.reg.sr[0].resultado([['algo', false]]);
  z.d.cancelar();
  z.reg.sr[0].fin?.();
  const errores = {};
  for (const e of ['not-allowed', 'service-not-allowed', 'audio-capture', 'no-speech', 'network']) {
    const w = armar({}, { servidor: false });
    w.d.empezar();
    await w.reloj.avanzar(10);
    w.reg.sr[0].error(e);
    errores[e] = w.d.estado().motivo;
  }
  const callada = armar({}, { servidor: false });
  callada.d.empezar();
  await callada.reloj.avanzar(10);
  callada.reg.sr[0].fin();
  // un navegador que anuncia el reconocimiento y no lo tiene: ni empieza ni da un error
  const muda = armar({ srMudo: true }, { servidor: false });
  muda.d.empezar();
  await muda.reloj.avanzar(SIN_ARRANQUE_MS - 100);
  const esperando = muda.d.estado().estado;
  await muda.reloj.avanzar(200);
  out.muda = { esperando, final: muda.d.estado(), abortos: muda.reg.sr[0].abortos, espera: SIN_ARRANQUE_MS };
  out.via2b = { aMano: [x.reg.sr[0].paradas, x.textos], tope: [antes, y.reg.sr[0].paradas, y.d.estado()],
    cancelada: [z.reg.sr[0].abortos, z.textos.length, z.d.estado().estado], errores, callada: callada.d.estado() };
}
// 11. El 409: el panel no puede transcribir. Se pasa a la vía 2 pidiendo repetir, y la próxima vez va directo
{
  const sin = () => Promise.reject(Object.assign(new Error('x'), { codigo: 'sin_transcriptor', estado: 409, mensaje: 'El panel no puede transcribir la voz: Mnemo no está conectado.' }));
  const x = armar({ nivel: voz([300, 1500]) }, { transcribir: sin });
  x.d.empezar();
  await x.reloj.avanzar(4000);
  const tras = x.d.estado();
  x.reg.sr[0].resultado([['la pregunta repetida', true]]);
  x.reg.sr[0].fin();
  x.d.empezar();
  await x.reloj.avanzar(10);
  const y = armar({ nivel: voz([300, 1500]), reconocer: false }, { transcribir: sin });
  y.d.empezar();
  await y.reloj.avanzar(4000);
  const sinReconocer = [y.estados.at(-1), y.d.estado(), textoDeEstado(y.d.estado()), y.d.empezar(), y.reg.pedidos];
  out.paso = { tras, aviso: textoDeEstado(tras), estados: x.estados, textos: x.textos, enviados: x.enviados.length, pedidos: x.reg.pedidos, sr: x.reg.sr.length,
    despues: x.d.estado().via, sinReconocer };
}
// 12. Otro error del panel (sin créditos): queda en «fallo» con su mensaje; y una transcripción vacía, en «vacío»
{
  const x = armar({ nivel: voz([300, 1500]) }, { transcribir: () => Promise.reject(Object.assign(new Error('x'),
    { codigo: 'mnemo_creditos', estado: 402, mensaje: 'Se acabaron los créditos de Mnemo.' })) });
  x.d.empezar();
  await x.reloj.avanzar(4000);
  const y = armar({ nivel: voz([300, 1500]) }, { transcribir: () => ({ texto: '   ' }) });
  y.d.empezar();
  await y.reloj.avanzar(4000);
  const z = armar({ nivel: voz([300, 1500]) }, { transcribir: () => { throw new Error('se rompió'); } });
  z.d.empezar();
  await z.reloj.avanzar(4000);
  out.errores = { creditos: [x.d.estado(), textoDeEstado(x.d.estado()), x.reg.sr.length], vacia: y.d.estado(), rota: [z.d.estado(), textoDeEstado(z.d.estado())] };
}
// 13. Sin medidor (el audio del navegador suspendido, o sin AudioContext): no corta sola ni a los 10 s; sí a los 60
for (const [clave, audio] of [['suspendido', 'suspended'], ['sin_contexto', null]]) {
  const x = armar({ audio, nivel: () => 0.002 });
  x.d.empezar();
  await x.reloj.avanzar(15000);
  const a15 = x.d.estado();
  await x.reloj.avanzar(46000);
  out[clave] = { a15, texto: textoDeEstado(a15), enviados: x.enviados.map((e) => e.ms), textos: x.textos.length };
}
// 14. Lo que puede este navegador, y sin nada: no arranca
{
  const reloj = relojFalso();
  const nada = armar({ grabar: false, reconocer: false });
  const arranco = nada.d.empezar();
  // con MediaRecorder pero sin reconocimiento, y el panel diciendo que no transcribe: se intenta grabar igual
  const soloGrabar = armar({ reconocer: false, nivel: voz([300, 1500]) }, { servidor: false });
  soloGrabar.d.empezar();
  await soloGrabar.reloj.avanzar(4000);
  // sin `transcribir`, solo queda el reconocimiento
  const sinTranscribir = armar({}, { transcribir: null });
  sinTranscribir.d.empezar();
  await sinTranscribir.reloj.avanzar(10);
  out.soporte = { todo: soporteDeDictado(ventana(reloj).v), sinGrabar: soporteDeDictado(ventana(reloj, { grabar: false }).v),
    sinNada: soporteDeDictado(ventana(reloj, { grabar: false, reconocer: false }).v),
    politica: soporteDeDictado(ventana(reloj, { politica: (f) => f !== 'microphone' }).v),
    politicaSi: soporteDeDictado(ventana(reloj, { politica: () => true }).v),
    insegura: soporteDeDictado(ventana(reloj, { segura: false }).v), vacia: soporteDeDictado({}),
    nada: [arranco, nada.d.estado(), textoDeEstado(nada.d.estado())], soloGrabar: soloGrabar.textos, sinTranscribir: sinTranscribir.d.estado().via };
}
// 15. Los textos y la limpieza
out.textos = { inactivo: textoDeEstado({ estado: 'inactivo' }), pidiendo: textoDeEstado({ estado: 'pidiendo' }),
  servidor: textoDeEstado({ estado: 'escuchando', via: 'servidor', nivel: 0.2 }), transcribiendo: textoDeEstado({ estado: 'transcribiendo' }),
  navegador: textoDeEstado({ estado: 'escuchando', via: 'navegador' }), raro: textoDeEstado(null) };
out.limpiar = [limpiar('  hola\u0000\n\tmundo  '), limpiar(null), limpiar('a'.repeat(MAX_TEXTO + 50)).length, limpiar('<b>hola</b>')];
// 16. soltar: cancela y deja de avisar
{
  const x = armar({ nivel: voz([300, 5000]) });
  x.d.empezar();
  await x.reloj.avanzar(1000);
  const n = x.crudos.length;
  x.d.soltar();
  await x.reloj.avanzar(3000);
  out.soltar = { avisos: x.crudos.slice(n).map((e) => e.estado), pistas: x.reg.pistasParadas, empieza: x.d.empezar(), estado: x.d.estado().estado };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def node(tmp_path_factory):
    """El guion de Node corre una vez: cada prueba mira su parte."""
    if requiere_node.args[0]:   # la misma condición de `requiere_node` (en el CI no se salta: falla)
        pytest.skip("Sin Node")
    d = tmp_path_factory.mktemp("dictado")
    (d / "prueba.mjs").write_text(NODE, encoding="utf-8")
    p = subprocess.run(["node", str(d / "prueba.mjs"), DICTADO_JS.as_uri()], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_los_tiempos_del_contrato(node):
    assert node["tiempos"] == {"SILENCIO_MS": 1600, "TOPE_MS": 60000, "MINIMO_MS": 400, "SIN_VOZ_MS": 10000,
                               "TICK_MS": 100}
    assert node["idioma"] == "es-CO"


def test_corta_sola_tras_el_silencio_despues_de_oir_voz(node):
    r = node["corte"]
    assert r["arranco"] is True
    # A los 4,4 s (1,4 s después de la última voz) sigue oyendo, con el micrófono tomado
    assert r["antes"] == {"estado": "escuchando", "enviados": 0, "pistas": 0}
    # El texto llega antes de volver a «inactivo», limpio y por la vía del servidor
    assert r["estados"] == ["pidiendo", "escuchando", "transcribiendo", "texto", "inactivo"]
    assert r["textos"] == [["¿Cuántas personas hay en Tres de Octubre?", "servidor", "transcribiendo"]]
    assert r["final"] == {"estado": "inactivo"}
    (e,) = r["enviados"]
    # La última medida con voz fue a los 2,9 s: corta 1,6 s después (a los 4,5 s), ni antes ni mucho después
    assert e["en"] == e["ms"] == 4500
    assert e["tipo"] == "audio/webm;codecs=opus" and e["bytes"] == 4500 * 3
    # El micrófono y el medidor ya estaban sueltos cuando se mandó a transcribir
    assert e["pistas"] == 1 and e["cerrados"] == 1 and r["contextos"] == 1
    # El nivel se ve: alto mientras habla y bajo en silencio, siempre de 0 a 1
    assert r["fuerte"] > 0.6 and r["callado"] < 0.15 and r["enRango"] is True
    # Lo que se le pide al navegador: un canal, con cancelación de eco y de ruido; y la grabadora, en opus a 24 kbps
    assert r["restricciones"] == {"audio": {"channelCount": 1, "echoCancellation": True, "noiseSuppression": True,
                                            "autoGainControl": True}}
    assert r["grabadora"] == {"mimeType": "audio/webm;codecs=opus", "audioBitsPerSecond": 24000} and r["trozo"] == 250


def test_una_pausa_corta_o_el_ruido_del_lugar_no_la_cortan(node):
    # Una pausa de 1,2 s al hablar: sigue oyendo, y corta 1,6 s después de la última voz (3,4 s → 5,0 s)
    assert node["pausa"]["enLaPausa"] == "escuchando"
    assert [e["ms"] for e in node["pausa"]["enviados"]] == [5000] and node["pausa"]["textos"] == 1
    # Ruido parejo antes y después de hablar (de 2 a 4 s): no es voz, y corta 1,6 s después de la última (3,9 s → 5,5 s)
    assert [e["ms"] for e in node["ruido"]["enviados"]] == [5500]
    assert node["ruido"]["estados"] == ["pidiendo", "escuchando", "transcribiendo", "texto", "inactivo"]


def test_el_tope_de_un_minuto(node):
    r = node["tope"]
    assert r["antes"] == ["escuchando", 0]
    assert [e["ms"] for e in r["enviados"]] == [60000] and r["textos"] == 1
    # Un minuto en opus a 24 kbps: 180 kB, lejos del tope de 2 MB de la ruta
    assert r["enviados"][0]["bytes"] == 180_000


def test_sin_voz_no_se_transcribe_nada(node):
    r = node["sin_voz"]
    assert r["antes"] == "escuchando"
    assert r["estados"] == ["pidiendo", "escuchando", "error:vacio"] and r["enviados"] == 0
    assert r["final"] == {"estado": "error", "motivo": "vacio", "via": "servidor"}
    assert r["pistas"] == 1 and r["cerrados"] == 1
    assert r["texto"] == "No oí nada. Toque el micrófono y hable."


def test_lo_muy_corto_se_descarta_y_terminar_a_mano_transcribe(node):
    estados, enviados, final = node["manual"]["corto"]
    assert estados == ["pidiendo", "escuchando", "error:vacio"] and enviados == 0 and final["motivo"] == "vacio"
    estados, enviados = node["manual"]["aMano"]
    assert estados == ["pidiendo", "escuchando", "transcribiendo", "texto", "inactivo"]
    assert [e["ms"] for e in enviados] == [1500]
    assert node["manual"]["sinVoz"] == 1


def test_cancelar(node):
    r = node["cancelar"]
    # Oyendo: vuelve a «inactivo» en el acto, con el micrófono y el medidor sueltos, y nada se transcribe después
    assert r["oyendo"] == {"enElActo": ["inactivo", 1, 1], "estados": ["pidiendo", "escuchando", "inactivo"],
                           "enviados": 0, "textos": 0}
    # Transcribiendo: la petición se corta y el texto que llegue tarde no se entrega
    assert r["transcribiendo"] == {"transcribiendo": "transcribiendo", "abortada": True, "textos": 0, "final": "inactivo",
                                   "estados": ["pidiendo", "escuchando", "transcribiendo", "inactivo"]}
    # Mientras el navegador pregunta por el permiso: el micrófono que llega después se suelta sin grabar nada
    assert r["pidiendo"] == {"estados": ["pidiendo", "inactivo"], "pistas": 1, "grabadoras": 0}


def test_el_permiso_negado_y_sin_microfono(node):
    estados, final, texto = node["permiso"]["negado"]
    assert estados == ["pidiendo", "error:permiso"] and final == {"estado": "error", "motivo": "permiso", "via": "servidor"}
    assert "permiso para usar el micrófono" in texto
    assert node["permiso"]["sin"] == {"estado": "error", "motivo": "sin_microfono", "via": "servidor"}
    assert node["permiso"]["otraVez"] is True   # desde el error se vuelve a empezar


def test_la_via_del_navegador_con_parciales_en_es_co(node):
    r = node["via2"]
    assert r["config"] == {"lang": "es-CO", "parciales": True, "continuo": False}
    assert r["alEmpezar"] == {"estado": "escuchando", "via": "navegador", "nivel": 0.15, "parcial": ""}
    assert r["parcial"]["parcial"] == "cuántas personas" and r["parcial"]["nivel"] == 0.7
    assert r["medio"] == "¿Cuántas personas hay en Tres de Octubre"
    assert r["estados"] == ["pidiendo", "escuchando", "texto", "inactivo"]
    assert r["textos"] == [["¿Cuántas personas hay en Tres de Octubre?", "navegador", "escuchando"]]
    # No se graba ni se manda nada al panel
    assert r["pedidos"] == 0 and r["enviados"] == 0
    # El aviso dice quién transcribe
    assert "servicio de voz de su navegador" in r["aviso"]
    # Sin MediaRecorder también se llega a esta vía
    assert r["sinGrabadora"] == ["navegador", 1, 0]


def test_la_via_del_navegador_terminar_tope_cancelar_y_errores(node):
    r = node["via2b"]
    assert r["aMano"] == [1, [["solo un parcial", "navegador", "escuchando"]]]   # lo último que oyó cuenta
    antes, despues, final = r["tope"]
    assert antes == 0 and despues == 1 and final == {"estado": "error", "motivo": "vacio", "via": "navegador"}
    assert r["cancelada"] == [1, 0, "inactivo"]
    assert r["errores"] == {"not-allowed": "permiso", "service-not-allowed": "permiso", "audio-capture": "sin_microfono",
                            "no-speech": "vacio", "network": "fallo"}
    assert r["callada"] == {"estado": "error", "motivo": "vacio", "via": "navegador"}
    # Un reconocimiento que nunca arranca (un Chromium sin el servicio de voz): a los 15 s se da por no disponible
    assert node["muda"] == {"esperando": "pidiendo", "abortos": 1, "espera": 15000,
                            "final": {"estado": "error", "motivo": "sin_soporte", "via": "navegador"}}


def test_un_409_pasa_a_la_via_del_navegador(node):
    r = node["paso"]
    # La grabación ya no sirve: se pide repetir la pregunta, ahora con el reconocimiento del navegador
    assert r["tras"] == {"estado": "escuchando", "via": "navegador", "nivel": 0.15, "parcial": "", "repetir": True}
    assert "Repita su pregunta" in r["aviso"] and "servicio de voz de su navegador" in r["aviso"]
    assert r["estados"] == ["pidiendo", "escuchando", "transcribiendo", "pidiendo", "escuchando", "texto", "inactivo",
                            "pidiendo", "escuchando"]
    assert r["textos"] == [["la pregunta repetida", "navegador", "escuchando"]]
    # La vez siguiente va directo al navegador: una sola grabación y una sola petición al panel
    assert r["enviados"] == 1 and r["pedidos"] == 1 and r["sr"] == 2 and r["despues"] == "navegador"
    # Sin reconocimiento en el navegador: no hay cómo, y lo dice con el mensaje del panel
    ultimo, final, texto, otra, pedidos = r["sinReconocer"]
    assert ultimo == "error:sin_soporte" and final["motivo"] == "sin_soporte"
    assert texto == "El panel no puede transcribir la voz: Mnemo no está conectado."
    assert otra is False and pedidos == 1   # y no se vuelve a grabar para nada


def test_los_errores_del_panel_y_la_transcripcion_vacia(node):
    final, texto, reconocimientos = node["errores"]["creditos"]
    assert final == {"estado": "error", "motivo": "fallo", "via": "servidor", "mensaje": "Se acabaron los créditos de Mnemo."}
    assert texto == "Se acabaron los créditos de Mnemo." and reconocimientos == 0   # no se pasa al navegador por esto
    assert node["errores"]["vacia"] == {"estado": "error", "motivo": "vacio", "via": "servidor"}
    final, texto = node["errores"]["rota"]
    assert final == {"estado": "error", "motivo": "fallo", "via": "servidor"} and texto.startswith("No se pudo transcribir")


@pytest.mark.parametrize("caso", ["suspendido", "sin_contexto"])
def test_sin_medidor_no_corta_sola(node, caso):
    r = node[caso]
    # A los 15 s sigue oyendo (sin medidor no se sabe si hubo voz) y dice cómo terminar
    assert r["a15"] == {"estado": "escuchando", "via": "servidor", "nivel": 0, "medidor": False}
    assert r["texto"] == "Escuchando… Toque el micrófono para terminar."
    assert r["enviados"] == [60000] and r["textos"] == 1


def test_lo_que_puede_el_navegador(node):
    r = node["soporte"]
    assert r["todo"] == {"grabar": True, "reconocer": True}
    assert r["sinGrabar"] == {"grabar": False, "reconocer": True}
    assert r["sinNada"] == r["vacia"] == {"grabar": False, "reconocer": False}
    # La política de permisos de la página le quita el micrófono, o la página no es segura: nada
    assert r["politica"] == r["insegura"] == {"grabar": False, "reconocer": False}
    assert r["politicaSi"] == {"grabar": True, "reconocer": True}
    arranco, final, texto = r["nada"]
    assert arranco is False and final == {"estado": "error", "motivo": "sin_soporte"} and "Escriba su pregunta" in texto
    # Con grabadora y sin reconocimiento, se graba aunque el panel haya dicho que no transcribe (es solo una pista)
    assert r["soloGrabar"] == [["¿Cuántas personas hay en Tres de Octubre?", "servidor", "transcribiendo"]]
    assert r["sinTranscribir"] == "navegador"


def test_los_textos_y_la_limpieza(node):
    t = node["textos"]
    assert t["inactivo"] == t["raro"] == ""
    assert t["pidiendo"].startswith("Permita el micrófono")
    assert t["servidor"] == "Escuchando… Termina sola cuando deje de hablar."
    assert t["transcribiendo"] == "Transcribiendo…"
    assert t["navegador"] == "Escuchando… Aquí la transcribe el servicio de voz de su navegador."
    assert node["limpiar"] == ["hola mundo", "", 4000, "<b>hola</b>"]   # el texto se queda texto: lo pinta textContent
    # soltar: avisa que quedó inactivo, suelta el micrófono y ya no avisa ni arranca más
    assert node["soltar"] == {"avisos": ["inactivo"], "pistas": 1, "empieza": False, "estado": "inactivo"}


def test_dictado_js_no_depende_del_panel():
    js = DICTADO_JS.read_text(encoding="utf-8")
    assert not re.search(r"^\s*import\b", js, re.M), "dictado.js no importa nada"
    for prohibido in ("innerHTML", "document.querySelector", "getElementById", "localStorage", "sessionStorage", "fetch("):
        assert prohibido not in js, prohibido
    assert re.search(r"^export function crearDictado\(\{ ventana = globalThis, transcribir = null, alEstado", js, re.M)


# ───────────────────────────── dictado.py: funciones puras ─────────────────────────────

def test_el_tipo_del_audio():
    assert dictado.tipo_de("audio/webm;codecs=opus") == "audio/webm"
    assert dictado.tipo_de("AUDIO/OGG; codecs=opus") == "audio/ogg"
    assert dictado.tipo_de("audio/mp4") == "audio/mp4" and dictado.tipo_de("audio/mpeg") == "audio/mpeg"
    assert dictado.tipo_de("audio/wav") == dictado.tipo_de("audio/x-wav") == dictado.tipo_de("audio/wave") == "audio/wav"
    assert dictado.tipo_de("audio/mp3") == "audio/mpeg" and dictado.tipo_de("audio/x-m4a") == "audio/mp4"
    for malo in ("application/json", "video/webm", "audio/flac", "text/plain", "", None, 7, "audio/"):
        assert dictado.tipo_de(malo) is None, malo
    assert set(dictado.TIPOS) == {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
    assert set(dictado.ALIAS.values()) <= set(dictado.TIPOS)


@pytest.fixture
def sin_ventanas():
    dictado._ventanas.clear()
    yield
    dictado._ventanas.clear()


def test_el_tope_de_frecuencia(sin_ventanas, monkeypatch):
    ahora = [1000.0]
    monkeypatch.setattr(dictado.time, "monotonic", lambda: ahora[0])
    for _ in range(20):
        dictado.frecuencia("base", 7)
    with pytest.raises(dictado.ErrorDictado) as e:
        dictado.frecuencia("base", 7)
    assert e.value.status_code == 429 and e.value.detail["codigo"] == "frecuencia"
    assert e.value.headers == {"Retry-After": "60"}
    dictado.frecuencia("base", 8)      # otra persona no se entera
    dictado.frecuencia("otra", 7)      # ni la misma en otra base
    ahora[0] += 61
    dictado.frecuencia("base", 7)      # pasado el minuto, vuelve a poder
    assert (dictado.FRECUENCIA_MAX, dictado.FRECUENCIA_S) == (20, 60)


def test_el_texto_de_la_respuesta():
    assert dictado.texto_de(correcto({"text": "  ¿Cuántas\n personas\x00 hay?  ", "language": "es"})) == "¿Cuántas personas hay?"
    assert dictado.texto_de(correcto({"text": ""})) == ""
    assert len(dictado.texto_de(correcto({"text": "a" * 9000}))) == 4000
    for malo in ({}, {"content": []}, {"structuredContent": {"text": 7}}, {"structuredContent": "x"}, None):
        with pytest.raises(dictado.ErrorDictado) as e:
            dictado.texto_de(malo)
        assert e.value.status_code == 502


def _error_mnemo(codigo, detalles=None, **kw):
    return ErrorHerramienta("Mnemo dice algo", mc.COD_MNEMO, detalle={"code": codigo, **({"details": detalles}
                                                                                         if detalles else {})}, **kw)


@pytest.mark.parametrize("error, estado, codigo, recordar", [
    (_error_mnemo("NO_TRANSCRIBER"), 409, "sin_transcriptor", True),
    (_error_mnemo("no_transcriber"), 409, "sin_transcriptor", True),
    (_error_mnemo("UNAVAILABLE", {"reason": "no_transcriber"}), 409, "sin_transcriptor", True),
    (_error_mnemo("FAILED", {"code": "NO_TRANSCRIBER"}), 409, "sin_transcriptor", True),
    (_error_mnemo("NO_TRANSCRIBER", {"reason": "no_transcriber", "cause": "pinned_unavailable"}), 409, "sin_transcriptor", True),
    (_error_mnemo("PLAN_REQUIRED", {"feature": "chat"}), 409, "sin_transcriptor", True),
    (_error_mnemo("UNAVAILABLE", {"reason": "transcriber"}), 409, "sin_transcriptor", True),
    (ErrorHerramienta("ya no", mc.COD_NO_DISPONIBLE, estado=200), 409, "sin_transcriptor", True),
    (ErrorHerramienta("venció", mc.COD_TOKEN, estado=401), 409, "sin_transcriptor", False),
    (ErrorHerramienta("alcance", mc.COD_TOKEN, estado=403), 409, "sin_transcriptor", False),
    (ErrorHerramienta("cambió", mc.COD_TOKEN, detalle={"conexion": "cambio"}), 502, "mnemo_red", False),
    (_error_mnemo("CREDITS_EXHAUSTED"), 402, "mnemo_creditos", False),
    (_error_mnemo("RATE_LIMITED", {"reason": "provider"}), 429, "frecuencia", False),
    (ErrorHerramienta("muchas", mc.COD_MNEMO, estado=429), 429, "frecuencia", False),
    (_error_mnemo("INVALID_ARGUMENT"), 422, "audio", False),
    (_error_mnemo("INVALID_ARGUMENT", {"reason": "undecodable"}), 422, "audio", False),
    (_error_mnemo("INVALID_ARGUMENT", {"reason": "too_long"}), 422, "audio", False),
    (ErrorHerramienta("grande", mc.COD_MNEMO, estado=413), 413, "grande", False),
    (ErrorHerramienta("red", mc.COD_RED), 502, "mnemo_red", False),
    (ErrorHerramienta("plazo", mc.COD_PLAZO), 502, "mnemo_red", False),
    (_error_mnemo("UNAVAILABLE"), 502, "mnemo", False),
    (_error_mnemo("TIMEOUT"), 502, "mnemo", False),
    (_error_mnemo("INTERNAL"), 502, "mnemo", False),
    (ErrorHerramienta("500", mc.COD_MNEMO, estado=500), 502, "mnemo", False),
])
def test_cada_fallo_de_mnemo_tiene_su_respuesta(error, estado, codigo, recordar):
    e, r = dictado.traducir(error)
    assert (e.status_code, e.detail["codigo"], r) == (estado, codigo, recordar)
    # El mensaje es propio: nunca el texto que vino de Mnemo
    assert e.detail["mensaje"] and "Mnemo dice" not in e.detail["mensaje"]
    assert set(e.detail) == {"codigo", "mensaje"}


def test_cuando_se_puede_transcribir_por_mnemo(monkeypatch):
    app = SimpleNamespace(state=SimpleNamespace())
    con = {"estado": "conectada", "modelo": True, "desde": "2026-11-01T10:00:00+00:00"}
    assert dictado.puede(app, con) is True
    assert dictado.puede(app, {**con, "modelo": False}) is False            # sin `mnemo:model`
    assert dictado.puede(app, {**con, "estado": "caida"}) is False
    assert dictado.puede(app, {"estado": "sin_conectar", "modelo": False, "desde": None}) is False
    assert dictado.puede(app, None) is False
    # Mnemo dijo que no transcribe: se recuerda una hora, para esta conexión
    ahora = [500.0]
    monkeypatch.setattr(dictado.time, "monotonic", lambda: ahora[0])
    dictado._recordar(app, con, True)
    assert dictado.puede(app, con) is False
    assert dictado.puede(app, {**con, "desde": "2026-11-02T08:00:00+00:00"}) is True   # se volvió a conectar
    ahora[0] += dictado.OLVIDO_S + 1
    assert dictado.puede(app, con) is True
    dictado._recordar(app, con, True)
    dictado._recordar(app, con, False)   # una transcripción que sí salió lo borra
    assert dictado.puede(app, con) is True


# ───────────────────────────── La ruta, con un Mnemo falso ─────────────────────────────

def _mnemo_que_transcribe(manejador=None) -> MnemoFalso:
    """El MCP falso con `mnemo_transcribe`, como la lista Mnemo (la entrada de la sección 4 del contrato)."""
    falso = MnemoFalso()
    falso.herramientas.append(herramienta("mnemo_transcribe", "Transcribe audio", {
        "audio": {"type": "string", "maxLength": 3_000_000}, "mime": {"type": "string", "enum": list(dictado.TIPOS)},
        "language": {"type": "string"}, "prompt": {"type": "string", "maxLength": 500}}, ["audio", "mime"], LECTURA))

    async def transcribe(args):
        return correcto({"text": f"  {PREGUNTA}\n", "language": "es", "duration_s": 3.2,
                         "model": {"provider": "openai", "model": "whisper-1"}})
    falso.manejadores["mnemo_transcribe"] = manejador or transcribe
    return falso


CONECTADA = {"estado": "conectada", "motivo": None, "url": URL, "cuenta": None, "alcances": ["mnemo:read", "mnemo:model"],
             "modelo": True, "ofrece_modelo": True, "desde": "2026-11-01T10:00:00+00:00"}


class Banco:
    """La ruta de verdad en una aplicación mínima: `requiere("agente.usar")` sustituido por una persona fija, los
    ajustes del asistente fijos y la conexión con Mnemo simulada (`dictado._preparar`)."""

    def __init__(self, monkeypatch, falso: MnemoFalso | None, *, conexion: dict = CONECTADA, rol: str = "admin",
                 roles: tuple = ("admin", "coordinador"), proveedor: str | None = "mnemo"):
        self.falso = falso
        self.app = FastAPI()
        self.app.include_router(agente_api.r)
        self.app.state.db = SimpleNamespace(name="prueba_dictado")
        self.app.state.cfg = SimpleNamespace()
        self.cliente_mnemo = mc.ClienteMnemo(URL, TOKEN, transporte=falso.transporte()) if falso is not None else None
        ruta = next(r for r in self.app.routes if isinstance(r, APIRoute) and r.path == "/api/agente/transcribir")
        (dep,) = [d.call for d in ruta.dependant.dependencies if hasattr(d.call, "permisos")]
        self.permisos = dep.permisos
        quien = acceso.Quien(uid=0 if rol == "admin" else 9, usuario="prueba", rol=rol, permisos=acceso.PERMISOS[rol])
        self.app.dependency_overrides[dep] = lambda: quien
        monkeypatch.setattr(politica, "leer", lambda db: ({}, {"roles": list(roles), "escritura": True}))
        monkeypatch.setattr(proveedores, "clave_para_nueva", lambda cfg, db=None: proveedor)
        monkeypatch.setattr(dictado, "_preparar", lambda app: (dict(conexion), self.cliente_mnemo))
        self.http = TestClient(self.app)

    def transcribir(self, audio: bytes = AUDIO, tipo: str | None = "audio/webm;codecs=opus", **kw):
        return self.http.post("/api/agente/transcribir", content=audio,
                              headers={"Content-Type": tipo} if tipo else {}, **kw)

    def llamadas(self) -> list[dict]:
        return [a for n, a in self.falso.llamadas if n == "mnemo_transcribe"]


@pytest.fixture
def banco(monkeypatch, sin_ventanas):
    def crear(falso="por_defecto", **kw):
        return Banco(monkeypatch, _mnemo_que_transcribe() if falso == "por_defecto" else falso, **kw)
    return crear


def test_la_ruta_transcribe_con_mnemo(banco, caplog):
    b = banco()
    assert b.permisos == frozenset({"agente.usar"})
    with caplog.at_level(logging.DEBUG, logger="panel"):
        r = b.transcribir()
    assert r.status_code == 200, r.text
    assert r.json() == {"texto": PREGUNTA, "via": "mnemo"}
    # Lo que recibe Mnemo: el audio en base64, su tipo sin parámetros y el idioma. Nada más
    # el audio, el idioma y el vocabulario de la propuesta (nombres propios y siglas, sin datos de personas)
    assert b.llamadas() == [{"audio": base64.b64encode(AUDIO).decode(), "mime": "audio/webm", "language": "es",
                             "prompt": dictado.VOCABULARIO}]
    assert "Yondó" in dictado.VOCABULARIO and len(dictado.VOCABULARIO) <= 500
    # Ni el audio ni el texto van al registro
    registro = "\n".join(m.getMessage() for m in caplog.records)
    assert PREGUNTA not in registro and "Tres de Octubre" not in registro
    assert base64.b64encode(AUDIO).decode()[:40] not in registro
    # Los demás tipos, con su nombre de Mnemo
    for tipo, mime in (("audio/ogg; codecs=opus", "audio/ogg"), ("audio/mp4", "audio/mp4"), ("audio/x-wav", "audio/wav"),
                       ("audio/mp3", "audio/mpeg")):
        assert b.transcribir(tipo=tipo).status_code == 200
        assert b.llamadas()[-1]["mime"] == mime
    # Una grabación sin nada que oír: texto vacío (el panel dice «No oí nada»)
    async def callado(args):
        return correcto({"text": "  ", "model": {"provider": "openai", "model": "whisper-1"}})
    b.falso.manejadores["mnemo_transcribe"] = callado
    assert b.transcribir().json() == {"texto": "", "via": "mnemo"}


def test_sin_conexion_o_sin_el_alcance_es_409_sin_llamar_a_mnemo(banco):
    b = banco(falso=None, conexion={**CONECTADA, "estado": "sin_conectar", "modelo": False, "alcances": []})
    r = b.transcribir()
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_transcriptor"
    assert "Mnemo no está conectado" in r.json()["detail"]["mensaje"]
    b = banco(conexion={**CONECTADA, "estado": "caida", "motivo": "revocada", "modelo": False})
    assert b.transcribir().status_code == 409 and b.llamadas() == []
    # Conectada, pero sin `mnemo:model`: el audio ni sale del panel
    b = banco(conexion={**CONECTADA, "modelo": False, "alcances": ["mnemo:read"]})
    r = b.transcribir()
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_transcriptor" and b.llamadas() == []
    assert "permiso para usar sus modelos" in r.json()["detail"]["mensaje"]


@pytest.mark.parametrize("codigo, detalles", [
    ("NO_TRANSCRIBER", {"reason": "no_transcriber", "cause": "none_configured"}),   # como lo manda Mnemo
    ("NO_TRANSCRIBER", None), ("UNAVAILABLE", {"reason": "no_transcriber"})])
def test_mnemo_sin_un_modelo_que_transcriba_es_409_y_se_recuerda(banco, codigo, detalles):
    async def sin_modelo(args):
        return fallo(codigo, "No transcription model is configured. Choose one in Settings → Models.", detalles)
    b = banco(_mnemo_que_transcribe(sin_modelo))
    assert dictado.puede(b.app, CONECTADA) is True
    r = b.transcribir()
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_transcriptor"
    # El mensaje es del panel: no cita el de Mnemo
    assert "no tiene un modelo que transcriba" in r.json()["detail"]["mensaje"] and "Settings" not in r.text
    # `GET /api/agente/estado` ya dice `dictado: false` (el panel va directo al navegador), hasta que una sí salga
    assert dictado.puede(b.app, CONECTADA) is False and agente_api._dictado(b.app, CONECTADA) is False
    b.falso.manejadores["mnemo_transcribe"] = _mnemo_que_transcribe().manejadores["mnemo_transcribe"]
    assert b.transcribir().status_code == 200
    assert dictado.puede(b.app, CONECTADA) is True


def test_un_mnemo_que_no_ofrece_la_herramienta_es_409(banco):
    b = banco(MnemoFalso())   # el catálogo de siempre, sin `mnemo_transcribe`
    r = b.transcribir()
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_transcriptor"
    assert "todavía no transcribe" in r.json()["detail"]["mensaje"]
    assert dictado.puede(b.app, CONECTADA) is False


def test_413_415_y_422(banco):
    b = banco()
    # 415: un tipo que no es audio de los que se transcriben, o ninguno
    for tipo in ("application/json", "audio/flac", "video/webm", None):
        r = b.transcribir(tipo=tipo)
        assert r.status_code == 415 and r.json()["detail"]["codigo"] == "tipo", tipo
    # 422: sin cuerpo
    r = b.transcribir(audio=b"")
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "vacio"
    # 413: más de 2 MB (por su Content-Length y, sin él, contando lo que llega)
    r = b.transcribir(audio=b"\0" * (dictado.MAX_AUDIO + 1))
    assert r.status_code == 413 and r.json()["detail"]["codigo"] == "grande"

    def por_partes():
        for _ in range(9):
            yield b"\0" * (256 * 1024)
    r = b.http.post("/api/agente/transcribir", content=por_partes(), headers={"Content-Type": "audio/webm"})
    assert r.status_code == 413 and r.json()["detail"]["codigo"] == "grande"
    # Justo 2 MB sí pasa. Nada de lo rechazado llegó a Mnemo
    assert b.transcribir(audio=b"\1" * dictado.MAX_AUDIO).status_code == 200
    assert len(b.llamadas()) == 1
    assert dictado.MAX_AUDIO == 2 * 1024 * 1024
    # 422: Mnemo no pudo leer la grabación
    async def ilegible(args):
        return fallo("INVALID_ARGUMENT", "The audio could not be decoded.", {"reason": "undecodable"})
    b.falso.manejadores["mnemo_transcribe"] = ilegible
    r = b.transcribir()
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "audio" and "decoded" not in r.text
    # Una grabación que no suena no es un error: el texto vacío (el panel dice «No oí nada»)
    async def muda(args):
        return fallo("INVALID_ARGUMENT", "The audio has no sound.", {"reason": "empty"})
    b.falso.manejadores["mnemo_transcribe"] = muda
    r = b.transcribir()
    assert r.status_code == 200 and r.json() == {"texto": "", "via": "mnemo"}


def test_402_sin_creditos_y_502_si_mnemo_falla(banco):
    async def sin_creditos(args):
        return fallo("CREDITS_EXHAUSTED", "Weekly credits exhausted.", {"resets_at": "2026-11-16"})
    b = banco(_mnemo_que_transcribe(sin_creditos))
    r = b.transcribir()
    assert r.status_code == 402 and r.json()["detail"]["codigo"] == "mnemo_creditos"
    assert "créditos" in r.json()["detail"]["mensaje"] and "Weekly" not in r.text
    assert dictado.puede(b.app, CONECTADA) is True   # no es que no transcriba: no se recuerda

    async def roto(args):
        return fallo("INTERNAL", "boom")
    b.falso.manejadores["mnemo_transcribe"] = roto
    r = b.transcribir()
    assert r.status_code == 502 and r.json()["detail"]["codigo"] == "mnemo" and "boom" not in r.text

    async def sin_texto(args):
        return correcto({"language": "es"})
    b.falso.manejadores["mnemo_transcribe"] = sin_texto
    assert b.transcribir().status_code == 502
    # Mnemo caído (un 503 de su servidor)
    b.falso.forzar["tools/call"] = (503, {"error": "down"}, {})
    r = b.transcribir()
    assert r.status_code == 502 and r.json()["detail"]["codigo"] == "mnemo"


def test_429_a_la_vez_veintiuna(banco):
    b = banco()
    for _ in range(20):
        assert b.transcribir().status_code == 200
    r = b.transcribir()
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "frecuencia"
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    assert len(b.llamadas()) == 20
    # El de Mnemo también es un 429
    dictado._ventanas.clear()

    async def limitado(args):
        return fallo("RATE_LIMITED", "Too many requests.", {"reason": "provider"})
    b.falso.manejadores["mnemo_transcribe"] = limitado
    r = b.transcribir()
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "frecuencia" and r.headers["Retry-After"] == "30"


def test_con_el_permiso_del_asistente(banco):
    # El rol apagado para el asistente: 403, sin leer el audio ni contarlo
    b = banco(rol="coordinador", roles=("admin",))
    r = b.transcribir()
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "agente_apagado" and b.llamadas() == []
    # Sin proveedor del modelo no hay asistente: 503
    b = banco(proveedor=None)
    r = b.transcribir()
    assert r.status_code == 503 and r.json()["detail"]["codigo"] == "sin_configurar" and b.llamadas() == []
    # El coordinador con el asistente encendido sí
    assert banco(rol="coordinador").transcribir().status_code == 200
    # La ruta declara el permiso del asistente (la sesión y el CSRF los pone `requiere`, como en las demás)
    ruta = next(r for r in agente_api.r.routes if isinstance(r, APIRoute) and r.path == "/api/agente/transcribir")
    assert ruta.methods == {"POST"}
    assert [d.call.permisos for d in ruta.dependant.dependencies if hasattr(d.call, "permisos")] == [frozenset({"agente.usar"})]


# ───────────────────────────── `mnemo_transcribe` no es una herramienta para el modelo ─────────────────────────────

def test_mnemo_transcribe_no_se_ofrece_al_modelo():
    assert mnemo.NUNCA == {"mnemo_model_complete", "mnemo_transcribe"}
    assert dictado.HERRAMIENTA == "mnemo_transcribe"
    falso = _mnemo_que_transcribe()

    async def nombres(filtro):
        return [d["name"] for d in await mnemo.definiciones(mc.ClienteMnemo(URL, TOKEN, transporte=falso.transporte()), filtro)]
    todas = asyncio.run(nombres("*"))
    assert "search" in todas and "mnemo_transcribe" not in todas
    assert asyncio.run(nombres("mnemo_transcribe,search")) == ["search"]
    assert "mnemo_transcribe" not in asyncio.run(nombres(""))
    assert "mnemo_transcribe" not in mnemo.POR_DEFECTO


# ───────────────────────────── El panel: el micrófono y la franja ─────────────────────────────

AGENTE_JS = (JS / "agente.js").read_text(encoding="utf-8")
RECORRIDO_JS = (JS / "agente-recorrido.js").read_text(encoding="utf-8")
CSS = (ADMIN / "web" / "css" / "agente.css").read_text(encoding="utf-8")


def _funcion(texto: str, nombre: str) -> str:
    """El cuerpo de `function nombre(` de agente.js (hasta la siguiente función o sección del mismo nivel)."""
    i = texto.index(f"function {nombre}(")
    fin = re.search(r"\n  (?:async function|function|// ──|const|let|\w+\.addEventListener)", texto[i + 10:])
    return texto[i:i + 10 + (fin.start() if fin else len(texto))]


def test_el_microfono_del_cuadro_de_escribir():
    # El botón: junto a «Enviar», con nombre, marcado mientras oye y oculto hasta saber que se puede
    assert ('<button type="button" class="btn agente-voz" id="agente-voz" aria-label="Preguntar por voz" '
            'title="Preguntar por voz" aria-pressed="false" hidden>${icono(\'microfono\')}</button>') in AGENTE_JS
    assert re.search(r"^\s*microfono:\s*'<path ", (JS / "ui.js").read_text(encoding="utf-8"), re.M)
    # El estado se anuncia con discreción: una región `status` aparte, que no cambia en cada medida del nivel
    assert '<span class="sr" id="agente-voz-vivo" role="status" aria-live="polite"></span>' in AGENTE_JS
    pintar = _funcion(AGENTE_JS, "pintarVoz")
    assert "vozBtn.setAttribute('aria-pressed', oyendo ? 'true' : 'false')" in pintar
    assert "if (dicho !== vozDicho) vozDicho = vozVivo.textContent = dicho;" in pintar
    assert "form.style.setProperty('--voz-nivel'" in pintar and "textoDeEstado(e)" in pintar
    # Nada de lo transcrito (ni lo parcial) entra como HTML: al cuadro por `value`, a la línea por textContent
    assert "vozParcial.textContent = parcial" in pintar and "innerHTML" not in pintar
    # Se crea con la ventana, la pista del servidor (`dictado` del estado) y la ruta de transcribir
    assert ("crearDictado({ ventana: window, servidor: () => info?.dictado === true, transcribir: transcribirVoz,"
            in AGENTE_JS)
    assert "dictado: o.dictado === true," in AGENTE_JS
    subir = _funcion(AGENTE_JS, "transcribirVoz")
    assert "api.subir('/api/agente/transcribir', blob, { cabeceras: { 'Content-Type': tipo }, timeout: ESPERA_VOZ_MS })" in subir
    assert "e.estado === 409 && e.codigo === 'sin_transcriptor' && info) info.dictado = false" in subir


def test_el_texto_dictado_se_envia_solo_si_el_cuadro_estaba_vacio():
    f = _funcion(AGENTE_JS, "textoDeVoz")
    assert "const habia = entrada.value.trim();" in f
    assert "entrada.value = (habia ? `${entrada.value.replace(/\\s+$/, '')} ${t}` : t).slice(0, MAX_TEXTO);" in f
    assert "vozEnviada = !habia && !turno && !cargando && !!info?.disponible;" in f
    assert "try { enviarDelCompositor(); } finally { vozEntregando = false; }" in f
    assert "innerHTML" not in f
    # Y un mensaje enviado a mano mientras se oía descarta lo que se dictaba (no llega después como otra pregunta)
    assert "if (!vozEntregando && vozActiva()) dictado.cancelar();" in _funcion(AGENTE_JS, "enviar")


def test_un_toque_empieza_otro_termina_y_escape_cancela():
    clic = AGENTE_JS[AGENTE_JS.index("vozBtn.addEventListener('click'"):]
    clic = clic[:clic.index("});") + 3]
    assert "if (e === 'pidiendo' || e === 'escuchando') { dictado.terminar(); return; }" in clic
    # Al empezar a oír se pausa lo que suena (para que la narración no entre al micrófono), y al dejar de oír sigue
    assert "if (dictado.empezar()) seguirPlan = pausaPorVoz();" in clic
    assert "seguir?.(vozEnviada)" in _funcion(AGENTE_JS, "pintarVoz")
    # Escape cancela primero lo que se oye (y no cierra el panel); cerrar el panel suelta el micrófono
    teclas = AGENTE_JS[AGENTE_JS.index("panel.addEventListener('keydown'"):]
    assert teclas.index("if (vozActiva()) { dictado.cancelar(); return; }") < teclas.index("cerrar({ foco: true })")
    assert "if (vozOyendo()) dictado.cancelar();" in _funcion(AGENTE_JS, "cerrar")
    # La pausa: el plan del chat, en el acto (no al terminar la frase); sin tarjeta, el que suene en la pantalla en off
    pausa = RECORRIDO_JS[RECORRIDO_JS.index("export function pausaPorVoz()"):RECORRIDO_JS.index("// ── La presentación automática")]
    assert "t.controlar('pausar', { nota: 'En pausa mientras usted pregunta.' });" in pausa and "suave" not in pausa
    assert "if (!enviada) pausa.then(() => { if (t.sonando()) t.controlar('continuar'); });" in pausa
    assert "api.get('/api/pantalla/recorrido')" in pausa
    assert "api.post('/api/pantalla/recorrido/control', { rid: r.id, accion: 'pausar' })" in pausa
    assert "api.post('/api/pantalla/recorrido/control', { rid, accion: 'continuar' })" in pausa


def test_los_estilos_del_microfono():
    assert re.search(r"\.btn\.agente-voz \{[^}]*width: 44px; height: 44px", CSS)
    assert ".btn.agente-voz[aria-pressed=\"true\"]::before" in CSS and "var(--voz-nivel, 0)" in CSS
    reducido = CSS[CSS.index("@media (prefers-reduced-motion: reduce)"):]
    assert ".btn.agente-voz::before, .agente-voz-onda i { transition: none; animation: none; }" in reducido


NODE_FRANJA = r"""
// Un DOM mínimo: lo que usan `el`, la franja y su botón
class Nodo {
  constructor(tag) { this.tag = tag; this.hijos = []; this.dataset = {}; this.attrs = {}; this.oyentes = {}; this.hidden = false; this.textContent = ''; this.padre = null; }
  append(...xs) { for (const x of xs) { x.padre = this; this.hijos.push(x); } }
  remove() { if (this.padre) this.padre.hijos = this.padre.hijos.filter((h) => h !== this); this.padre = null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(t, f) { this.oyentes[t] = f; }
  contains(x) { return x === this || this.hijos.some((h) => h.contains(x)); }
  focus() { globalThis.document.activeElement = this; }
  texto() { return this.textContent + this.hijos.map((h) => h.texto()).join(''); }
  buscar(clase) { return (this.className || '').split(' ').includes(clase) ? this : this.hijos.map((h) => h.buscar(clase)).find(Boolean) || null; }
}
globalThis.document = { querySelector: () => null, documentElement: {}, activeElement: null };
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const el = (tag, clase, texto) => { const n = new Nodo(tag); if (clase) n.className = clase; if (texto != null) n.textContent = texto; return n; };
const ico = (nombre) => el('svg', `ico-${nombre}`);
const llamadas = [];
let responder = () => ({ auto: { activa: false } });
globalThis.fetch = async (u, o = {}) => {
  llamadas.push(`${o.method || 'GET'} ${new URL(u, 'http://x').pathname} ${o.body || ''}`);
  const r = await responder();
  return { ok: r.estado === undefined, status: r.estado ?? 200, headers: { get: () => 'application/json' }, json: async () => r.cuerpo ?? r };
};
const { automaticaValida, crearFranjaAutomatica } = await import(process.argv[2]);
const out = {};
const A = { tipo: 'automatica', activa: true, capitulo: 'salud', nombre: 'Salud', paso: 1, de: 10 };
out.validas = [automaticaValida(A), automaticaValida({ ...A, activa: false, paso: 3, vueltas: 2 })];
out.invalidas = [null, [], { ...A, tipo: 'recorrido' }, { ...A, activa: 'si' }, { ...A, capitulo: 'Salud<b>' }, { ...A, nombre: '' },
  { ...A, nombre: 'x'.repeat(81) }, { ...A, paso: 0 }, { ...A, paso: 11 }, { ...A, de: 61 }, { ...A, paso: 1.5 }].map(automaticaValida);
// Encendida: la franja con «Detener», que la apaga en el servidor
const f1 = crearFranjaAutomatica(automaticaValida(A), { el, ico }).el;
const boton = f1.buscar('agente-auto-detener');
out.encendida = { texto: f1.buscar('agente-auto-texto').textContent, activa: f1.dataset.activa, boton: boton.texto(), nombre: boton.attrs['aria-label'] };
// Falla: lo dice y el botón sigue
responder = () => ({ estado: 500, cuerpo: { detail: 'La base no responde' } });
await boton.oyentes.click();
out.fallo = { error: f1.buscar('agente-auto-error').textContent, oculto: f1.buscar('agente-auto-error').hidden, sigue: !!f1.buscar('agente-auto-detener') };
// Ahora sí: se apaga, el botón se va y el foco (que estaba en él) pasa a la franja
responder = () => ({ auto: { activa: false, capitulo: 'salud', nombre: 'Salud', paso: 1, de: 10 } });
document.activeElement = boton;
await boton.oyentes.click();
out.detenida = { texto: f1.buscar('agente-auto-texto').textContent, activa: f1.dataset.activa, boton: !!f1.buscar('agente-auto-detener'),
  foco: document.activeElement === f1, llamadas: llamadas.slice() };
// A mitad de un capítulo, y apagada
out.sigue = crearFranjaAutomatica(automaticaValida({ ...A, capitulo: 'vias', nombre: 'Vías', paso: 3, de: 8 }), { el, ico }).el.buscar('agente-auto-texto').textContent;
const vieja = crearFranjaAutomatica(automaticaValida(A), { el, ico }).el;
const apagada = crearFranjaAutomatica(automaticaValida({ ...A, activa: false }), { el, ico }).el;
out.apagada = { texto: apagada.buscar('agente-auto-texto').textContent, boton: !!apagada.buscar('agente-auto-detener'), activa: apagada.dataset.activa,
  laViejaYaNoDetiene: !vieja.buscar('agente-auto-detener') };
// Un nombre con marcas se queda texto
out.marcas = crearFranjaAutomatica(automaticaValida({ ...A, nombre: '<img src=x onerror=alert(1)>' }), { el, ico }).el.buscar('agente-auto-texto').textContent;
console.log(JSON.stringify(out));
"""


@requiere_node
def test_la_franja_de_la_presentacion_automatica(tmp_path):
    (tmp_path / "prueba.mjs").write_text(NODE_FRANJA, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), (JS / "agente-recorrido.js").as_uri()],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["validas"] == [{"activa": True, "capitulo": "salud", "nombre": "Salud", "paso": 1, "de": 10},
                            {"activa": False, "capitulo": "salud", "nombre": "Salud", "paso": 3, "de": 10}]
    assert r["invalidas"] == [None] * 11
    assert r["encendida"] == {"texto": "Presentación automática encendida · empieza en Salud", "activa": "si",
                              "boton": "Detener", "nombre": "Detener la presentación automática"}
    assert r["fallo"] == {"error": "No se pudo detener: La base no responde", "oculto": False, "sigue": True}
    assert r["detenida"]["texto"] == "Presentación automática apagada" and r["detenida"]["activa"] == "no"
    assert r["detenida"]["boton"] is False and r["detenida"]["foco"] is True
    assert r["detenida"]["llamadas"] == ['POST /api/pantalla/auto {"accion":"detener"}'] * 2
    assert r["sigue"] == "Presentación automática encendida · sigue en Vías, paso 3 de 8"
    assert r["apagada"] == {"texto": "Presentación automática apagada", "boton": False, "activa": "no",
                            "laViejaYaNoDetiene": True}
    assert r["marcas"] == "Presentación automática encendida · empieza en <img src=x onerror=alert(1)>"


def test_la_accion_automatica_llega_a_su_franja():
    accion = _funcion(AGENTE_JS, "accion")
    assert "else if (a.tipo === 'automatica') franjaAutomatica(a);" in accion
    f = _funcion(AGENTE_JS, "franjaAutomatica")
    assert "const v = automaticaValida(a);" in f and "crearFranjaAutomatica(v, { el, ico }).el" in f
    franja = RECORRIDO_JS[RECORRIDO_JS.index("export function crearFranjaAutomatica("):]
    assert "await api.post('/api/pantalla/auto', { accion: 'detener' });" in franja
    assert "innerHTML" not in franja


# ───────────────────────────── Lo que la voz necesita de app/seguridad.py ─────────────────────────────

def test_la_politica_de_permisos_deja_usar_el_microfono_a_la_propia_pagina():
    """`Permissions-Policy: microphone=()` le quita el micrófono a todas las páginas del panel: ni `getUserMedia` ni el
    reconocimiento del navegador funcionan. Tiene que ser `microphone=(self)` (o no nombrarlo)."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app import seguridad
    app = Starlette(routes=[Route("/", lambda request: PlainTextResponse("ok"))])
    app.add_middleware(seguridad.CabecerasSeguras)
    app.state.cfg = SimpleNamespace(origen_sitio="", cookie_segura=False)
    cabecera = TestClient(app).get("/").headers["permissions-policy"]
    microfono = re.search(r"microphone=\(([^)]*)\)", cabecera)
    assert microfono is None or "self" in microfono.group(1), cabecera
    assert "camera=()" in cabecera   # la cámara sigue cerrada


def test_la_guardia_deja_pasar_un_audio_de_dos_megas():
    """`GuardiaApi` corta por `Content-Length` todo lo que no es /api/importar a los 256 kB (`LIMITE_JSON`), antes de
    llegar a la ruta: la de transcribir necesita su tope de 2 MB."""
    from app import seguridad
    estados = []

    async def enviar(m):
        if m["type"] == "http.response.start":
            estados.append(m["status"])

    async def recibir():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def adentro(scope, receive, send):   # la guardia dejó pasar la petición
        estados.append(200)
    # Sin la base lista, la guardia responde 503 después de mirar el tamaño: lo que no puede ser es un 413
    app = SimpleNamespace(state=SimpleNamespace(cfg=SimpleNamespace(max_subida_mb=5), listo=False))
    scope = {"type": "http", "method": "POST", "path": "/api/agente/transcribir", "root_path": "", "app": app,
             "query_string": b"", "headers": [(b"content-type", b"audio/webm"),
                                              (b"content-length", str(dictado.MAX_AUDIO).encode())]}
    asyncio.run(seguridad.GuardiaApi(adentro)(scope, recibir, enviar))
    assert estados and estados[0] != 413, estados
