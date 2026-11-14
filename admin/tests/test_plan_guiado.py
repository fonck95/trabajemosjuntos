"""El plan guiado (el recorrido narrado que muestra MIENTRAS explica), con Node: lo que cambia en el mando de la
presentación (web/js/propuesta/mando.js), en el puente del panel (admin/web/js/agente-presentacion.js), en el reproductor
(reproductor.js) y en la vista.

* La orden `escena` del mando, con una capa visual, un `ir` y un `asentada` de mentira: cambia de paso sin telón ni
  vuelo propio, pinta la narración antes de aplicar lo visual, le pasa a la capa lo visual completo con `ms`, `mover` y
  `animar`, y responde sin esperar a que la imagen se asiente. Lo opcional que no vale (una parte de lo visual, el
  resaltado, el movimiento, un dato de más) se descarta con el aviso `parcial` y lo demás se aplica; solo lo que se
  proyecta, el avance, el id, el paso y `panel` la hacen fallar entera. Una escena que otra orden dejó atrás responde
  `reemplazada`. Solo espera cuando deja un modelo del atlas a la vista. Y con una capa visual de antes (sin `depurar`,
  `guiado` ni `mover`) nada se rompe.
* La orden suelta `visual`: las partes nuevas, `mover` (con `ms`; por omisión, 6 s) y `animar`, con la misma tolerancia.
* El puente: las formas nuevas de lo visual, de `mover` y de `animar` en el recorrido, en la acción `visual` y en el
  estado de la pantalla en off (las válidas y las que no); doce pasos; el aviso `parcial`; `ordenesHacia` compara las
  listas por contenido; `alternarVozRecorrido` enciende o apaga la voz de la vista de esta pestaña.
* El reproductor: `ms`, `mover` y `animar` en la orden; `previa` (la espera antes del primer paso de un plan nuevo) se
  pausa y la cortan un salto, un detener u otro plan; `parcial` sigue como aviso.
"""
import json
import re
import subprocess
from pathlib import Path

from test_agente_presentacion import requiere_node

ADMIN = Path(__file__).resolve().parents[1]
JS = ADMIN / "web" / "js"
PUENTE_JS = JS / "agente-presentacion.js"
REPRODUCTOR_JS = JS / "reproductor.js"
VOZ_JS = JS / "voz.js"
VISTA_JS = JS / "vistas" / "presentacion.js"
MANDO_JS = ADMIN.parent / "web" / "js" / "propuesta" / "mando.js"


def _node(tmp_path: Path, guion: str, *args: str, timeout: int = 90) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=timeout,
                       cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


# ───────────────────────────── Los mismos topes y tiempos (sección 6 del contrato) ─────────────────────────────

def _const(js: str, nombre: str) -> str:
    m = re.search(rf"export const {nombre} = (.+?);\n", js, re.S)
    assert m, nombre
    return m.group(1)


def test_doce_pasos_el_aviso_parcial_y_los_tiempos_nuevos():
    puente, mando = PUENTE_JS.read_text(encoding="utf-8"), MANDO_JS.read_text(encoding="utf-8")
    repro = REPRODUCTOR_JS.read_text(encoding="utf-8")
    avisos = "['atlas', 'resaltar', 'asiento', 'voz', 'parcial']"
    for nombre, js in (("puente", puente), ("mando", mando), ("reproductor", repro)):
        assert _const(js, "MAX_ESCENAS") == "12", nombre
        assert _const(js, "AVISOS") == avisos, nombre
    tiempos = {"PREVIA_MS": 1800, "RESPIRO_MS": 350, "ENTRE_FRASES_MS": 250, "SOSTENER_MS": 1300,
               "SOSTENER_MIRAR_MS": 2700, "CIERRE_SOSTENER_MS": 4000, "PREGUNTAS_MS": 12000}
    for nombre, valor in tiempos.items():
        assert _const(repro, nombre) == str(valor), nombre
    # el mando estima la narración como el reproductor (si la orden no trae `ms`)
    assert "Math.min(16000, Math.max(3200, 1500 + 62 *" in repro and "Math.min(16000, Math.max(3200, 1500 + 62 *" in mando
    assert "const ENTRE_FRASES_MS = 250;" in mando


def test_la_vista_da_la_previa_solo_al_plan_nuevo_y_registra_la_voz():
    vista = VISTA_JS.read_text(encoding="utf-8")
    assert "import { PREVIA_MS, crearReproductor } from '../reproductor.js';" in vista
    # la espera solo va cuando la vista la pide; y la pide con un plan que no reprodujo y que llega sin `desde`
    assert "rep.iniciar(p.recorrido, { desde: p.desde || 1, ...(previa ? { previa: PREVIA_MS } : {}) })" in vista
    assert "aplicarRecorrido(p, { previa: nuevo && p.desde === undefined })" in vista
    # la pantalla en off: el que retoma (ya tuvo avance) no espera
    assert "previa: nuevo && !pr" in vista
    # la voz de esta vista queda a mano del puente (el interruptor de la tarjeta del chat)
    assert re.search(r"registrarPresentacion\(\{ aplicar,.*?\n\s+alternarVoz,.*?\n\s+\.\.\.\(proyector \? \{ proyector: true \} : \{\}\) \}\);", vista, re.S)
    assert "for (const b of botonesVoz) b.addEventListener('click', alternarVoz);" in vista
    assert "export function alternarVozRecorrido()" in PUENTE_JS.read_text(encoding="utf-8")
    # encendida por omisión: solo un '0' guardado la apaga
    assert "let preferida = guardado !== '0';" in VOZ_JS.read_text(encoding="utf-8")


# ───────────────────────────── La orden `escena` y la orden `visual` del mando ─────────────────────────────

NODE_MANDO = r"""// mando.js con ventana, documento, marco padre, capa visual, `ir` y `asentada` de mentira. Uso: node <guion> <mando.js>
const [modulo] = process.argv.slice(2);
const M = await import(modulo);
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const clases = () => { const s = new Set(); return { add: (...c) => c.forEach((x) => s.add(x)), remove: (...c) => c.forEach((x) => s.delete(x)),
  contains: (c) => s.has(c), toggle: (c, v) => ((v ?? !s.has(c)) ? s.add(c) : s.delete(c)), lista: () => [...s].sort() }; };
// Un DOM de lo justo para la narración (createElement, textContent, hijos, clases)
class Nodo {
  constructor(tag) { Object.assign(this, { tag, className: '', hijos: [], texto: '', atributos: {}, classList: clases(), offsetHeight: 40 }); }
  get textContent() { return this.hijos.length ? this.hijos.map((h) => h.textContent).join('|') : this.texto; }
  set textContent(v) { this.texto = String(v); this.hijos = []; }
  append(...xs) { this.hijos.push(...xs); }
  replaceChildren(...xs) { this.hijos = [...xs]; this.texto = ''; }
  insertBefore(n) { this.hijos.unshift(n); }
  setAttribute(k, v) { this.atributos[k] = String(v); }
  remove() {}
  todos() { return this.hijos.flatMap((h) => [h, ...h.todos()]); }
  querySelector(sel) { return this.todos().find((n) => n.className.split(' ').includes(sel.slice(1))) || null; }
  getBoundingClientRect() { return { height: 40, width: 100 }; }
}
const V0 = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const PIEZAS = ['torre', 'red', 'puestos'], PARTES = ['torre.cubierta', 'torre.solar'], INMERSIONES = ['torre_sismo', 'torre_bim'];
// `capa`: 'nueva' (depurar, guiado, mover) o 'vieja' (solo estado, aplicar, validar y cargando, como antes del plan guiado)
function armar({ capa = 'nueva' } = {}) {
  const oyentes = {}, enviados = [], log = [];
  const padre = { postMessage: (m) => enviados.push(structuredClone(m)) };
  const ventana = { location: { origin: 'https://sitio.example' }, addEventListener: (t, f) => { (oyentes[t] ||= []).push(f); },
    matchMedia: () => ({ matches: false }), innerWidth: 1400 };
  ventana.parent = padre;
  const p = new Nodo('p'), sub = new Nodo('div');
  sub.querySelector = (s) => (s === 'p' ? p : null);
  const pres = { classList: clases(), style: { setProperty() {}, removeProperty() {} } };
  const documento = { querySelector: (s) => ({ '#pres': pres, '.subtitulo': sub, '.leyenda3d': { childElementCount: 0 } })[s] ?? null,
    querySelectorAll: () => [], createElement: (t) => new Nodo(t), addEventListener() {} };
  const caps = [{ id: 'salud', nombre: 'Salud', pasos: [{ titulo: 'Uno' }, { titulo: 'Dos' }, { titulo: 'Tres' },
    { titulo: 'Por dentro', tipo: 'inmersion', inmersion: 'torre_sismo' }] }, { id: 'aguas', nombre: 'Aguas', pasos: [{ titulo: 'Uno' }] }];
  const estado = { ci: 0, pi: 0 };
  const x = { retener: false, retenidos: [], asientos: [], cargando: false, existe: () => true, log, enviados, sub, p, pres, estado };
  const narrando = () => sub.classList.contains('narracion') && !sub.classList.contains('cambiando');
  const frases = () => p.hijos.map((h) => [h.className, h.textContent]);
  x.narrando = narrando; x.frases = frases;
  const paso = () => (oyentes['propuesta:paso'] || []).forEach((f) => f({}));
  x.pasoAMano = (ci, pi) => { estado.ci = ci; estado.pi = pi; paso(); };
  // como `mostrar` de main.js: el paso cambia y se anuncia en el acto; lo que tarda es el panel
  const ir = (ci, pi, opts) => {
    log.push(['ir', caps[ci].id, pi + 1, opts ?? null]);
    estado.ci = ci; estado.pi = pi; paso();
    return x.retener ? new Promise((ok) => x.retenidos.push(ok)) : Promise.resolve();
  };
  let vis = structuredClone(V0);
  const visual = {
    estado: () => ({ ...structuredClone(vis), tema: null, abierta: null }),
    aplicar: async (c, o) => { log.push(['aplicar', structuredClone(c), o === undefined ? null : structuredClone(o), narrando() ? frases() : null]);
      if (x.errorAlAplicar) return x.errorAlAplicar; vis = { ...vis, ...structuredClone(c) }; return null; },
    cargando: () => x.cargando,
    validar: (v) => { for (const k of ['enfoque', 'detalle']) if (v[k] != null && !PIEZAS.includes(v[k])) return `El capítulo Salud no tiene el componente «${v[k]}»`;
      return v.inmersion != null && v.inmersion !== 'maqueta' && !INMERSIONES.includes(v.inmersion) ? 'La presentación no tiene esa inmersión' : null; },
  };
  if (capa === 'nueva') {
    visual.guiado = (v) => { log.push(['guiado', v]); };
    // como la de visual.js: devuelve si movió la cámara (no es un error)
    visual.mover = (m, ms) => { log.push(['mover', structuredClone(m), ms]); return true; };
    visual.depurar = (v, ci) => {
      log.push(['depurar', caps[ci].id]);
      const out = structuredClone(v), descartadas = [];
      const quitar = (clave, valor, motivo) => descartadas.push({ clave, valor, motivo });
      for (const [k, lista] of [['mostrar', PIEZAS], ['ocultar', PIEZAS], ['sin', PARTES]]) {
        if (!Array.isArray(v[k])) continue;
        out[k] = v[k].filter((id) => lista.includes(id));
        for (const id of v[k]) if (!lista.includes(id)) quitar(k, id, `«${id}» no está en ${caps[ci].nombre}`);
      }
      for (const k of ['enfoque', 'detalle', 'mirar', 'aislar']) if (v[k] != null && !PIEZAS.includes(v[k])) { quitar(k, v[k], `«${v[k]}» no está en ${caps[ci].nombre}`); out[k] = null; }
      if (v.inmersion != null && v.inmersion !== 'maqueta' && !INMERSIONES.includes(v.inmersion)) { quitar('inmersion', v.inmersion, 'La presentación no tiene esa inmersión'); out.inmersion = null; }
      return { visual: out, descartadas };
    };
  }
  M.montarMando({ caps, estado, ir, vecino: (ci, pi) => [ci, pi], ventana, documento, visual,
    verPanel: (v) => { log.push(['panel', v]); pres.classList.toggle('sin-panel', !v); },
    asentada: ({ tope } = {}) => { log.push(['asentada', tope ?? null]); return new Promise((ok) => x.asientos.push(ok)); },
    resaltar: (r) => { if (r) log.push(['resaltar', r]); return r ? x.existe(r) : true; },
    restaurarEncuadre: () => { log.push(['restaurar']); } });
  x.mandar = (orden, extra = {}) => { for (const f of oyentes.message || []) f({ data: { canal: 'yondo-presentacion', v: 1, orden, ...extra }, origin: 'https://sitio.example', source: padre }); };
  // la respuesta a una orden (la que lleva su id), o null si todavía no llegó
  x.respuesta = (id) => enviados.find((m) => m.id === id) || null;
  x.pedir = async (orden, extra, espera = 15) => { x.mandar(orden, extra); await dormir(espera); return x.respuesta(extra.id); };
  x.nombres = () => log.map((l) => l[0]);
  return x;
}
const E = (extra = {}) => ({ rid: 'abcdef123456', n: 1, de: 3, titulo: 'La torre', capitulo: 'salud', paso: 1, panel: true, visual: structuredClone(V0),
  resaltar: null, mover: null, animar: false, frases: ['Frase uno.', 'Frase dos.'], voz: false, ms: 7400, ...extra });
const r = {};

// A. Un paso del plan a otro paso: sin telón ni vuelo propio, la narración antes que lo visual, y la respuesta sin
// esperar a que la imagen se asiente (el `asentada` de mentira no resolvería nunca)
{
  const a = armar();
  const visual = { ...structuredClone(V0), rumbo: 150, elevacion: 30, zoom: 1.2, mirar: 'torre', mostrar: ['red'], ocultar: ['puestos'], sin: ['torre.cubierta'] };
  const t0 = Date.now();
  a.mandar('escena', { id: 1, ...E({ paso: 2, visual, resaltar: { tipo: 'cifra', n: 2 }, mover: { giro: 30, zoom: 1.4 }, animar: true, voz: true }) });
  await dormir(15);
  const res = a.respuesta(1);
  const aplicar = a.log.find((l) => l[0] === 'aplicar');
  r.rapida = { tipo: res?.tipo, asentada: res?.asentada, aviso: res?.aviso ?? null, descartadas: res?.descartadas ?? null, tardo: Date.now() - t0 < 500,
    ms_respuesta: typeof res?.ms === 'number' && res.ms < 500, nombres: a.nombres(), ir: a.log.find((l) => l[0] === 'ir'),
    visual: aplicar?.[1], opciones: aplicar?.[2], narrada_al_aplicar: aplicar?.[3], resaltar: a.log.find((l) => l[0] === 'resaltar')?.[1],
    donde: [res?.capitulo, res?.paso, res?.explicacion, res?.texto, res?.por], recorrido: res?.recorrido, estado_visual: res?.visual,
    clases: a.sub.classList.lista(), vivo: a.sub.atributos['aria-live'] };
  // B. El mismo paso, sin nada que cambie: igual se le pide a la capa (la cámara viaja), sin `ir`; `ms` es lo que dura
  // la narración según el reproductor
  a.log.length = 0;
  const b = await a.pedir('escena', { id: 2, ...E({ paso: 2, n: 2, ms: 9000 }) });
  r.mismo_paso = { tipo: b?.tipo, nombres: a.nombres(), opciones: a.log.find((l) => l[0] === 'aplicar')?.[2] };
  // sin `ms` (o con uno que no vale), la lectura de las frases: 3200 + 3200 + 250
  a.log.length = 0;
  const { ms: _ms, ...sinMs } = E({ paso: 2, n: 2 });
  await a.pedir('escena', { id: 3, ...sinMs });
  await a.pedir('escena', { id: 4, ...sinMs, ms: -5 });
  r.ms_estimado = a.log.filter((l) => l[0] === 'aplicar').map((l) => l[2].ms);
  // «Solo 3D»: el panel se quita cuando la escena lo pide
  a.log.length = 0;
  await a.pedir('escena', { id: 5, ...E({ paso: 2, n: 2, panel: false }) });
  r.solo_3d = a.log.filter((l) => l[0] === 'panel');
}

// C. Tolerante: lo opcional que no vale se descarta (con el aviso `parcial`) y lo demás se aplica
{
  const a = armar();
  const visual = { camara: 'dron', rumbo: 90, zoom: 1.256, mostrar: ['red', 'Mala!', 'fantasma', 'red'], sin: ['torre.cubierta', 'torre.x'], aislar: 'nada',
    comparar: 'hoy', otra: 1 };
  const res = await a.pedir('escena', { id: 1, ...E({ visual, resaltar: { tipo: 'cifra', n: 99 }, mover: { giro: 500, zoom: 1.5, elevacion: null, lado: 1 },
    animar: 'si', voz: 'x', ms: 7400, sorpresa: 1 }) });
  const aplicar = a.log.find((l) => l[0] === 'aplicar');
  r.tolerante = { tipo: res?.tipo, aviso: res?.aviso, descartadas: res?.descartadas, visual: aplicar?.[1], opciones: aplicar?.[2],
    narrada: a.narrando(), resaltados: a.log.filter((l) => l[0] === 'resaltar').length, clases: a.sub.classList.lista() };
  // sin `visual`, sin `resaltar`, sin `mover` ni `animar` (un reproductor de antes): lo del paso, sin aviso
  a.log.length = 0;
  const { visual: _v, resaltar: _r, mover: _m, animar: _a, ...minima } = E({ n: 2 });
  const min = await a.pedir('escena', { id: 2, ...minima });
  r.minima = { tipo: min?.tipo, aviso: min?.aviso ?? null, visual: a.log.find((l) => l[0] === 'aplicar')?.[1], opciones: a.log.find((l) => l[0] === 'aplicar')?.[2] };
  // lo visual de antes (siete partes): las demás, lo del paso
  a.log.length = 0;
  const vieja = await a.pedir('escena', { id: 3, ...E({ n: 3, visual: { enfoque: 'torre', camara: 'aerea', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null } }) });
  r.visual_de_antes = { aviso: vieja?.aviso ?? null, visual: a.log.find((l) => l[0] === 'aplicar')?.[1] };
  // lo que la capa no pudo aplicar también es `parcial`, y la escena igual narra
  a.log.length = 0;
  a.errorAlAplicar = 'La presentación todavía no muestra ningún paso';
  const err = await a.pedir('escena', { id: 4, ...E({ n: 3 }) });
  r.error_de_la_capa = { tipo: err?.tipo, aviso: err?.aviso, descartadas: err?.descartadas, narrada: a.narrando() };
}

// D. Lo único que la hace fallar entera: lo que se proyecta, el avance, el id, el capítulo, el paso y `panel`
{
  const a = armar();
  const malas = { titulo: { titulo: 'Cuesta $5.000' }, sin_frases: { frases: [] }, frase_con_arroba: { frases: ['ana@correo.co'] }, frase_larga: { frases: ['x'.repeat(221)] },
    cuatro_frases: { frases: ['a.', 'b.', 'c.', 'd.'] }, rid: { rid: 'ABC' }, n_cero: { n: 0 }, n_mayor: { n: 4, de: 3 }, de_trece: { n: 1, de: 13 },
    capitulo: { capitulo: 'marte' }, paso: { paso: 9 }, panel: { panel: 'si' } };
  r.fatales = {};
  let id = 10;
  for (const [k, extra] of Object.entries(malas)) {
    const res = await a.pedir('escena', { id: ++id, ...E(extra) });
    r.fatales[k] = [res?.tipo, typeof res?.error === 'string' && res.error.length > 0];
  }
  r.fatales_no_mueven = { log: a.nombres(), narrada: a.sub.classList.contains('narracion') };
  const doce = await a.pedir('escena', { id: 99, ...E({ n: 12, de: 12 }) });
  r.doce = [doce?.tipo, doce?.recorrido];
  // sin la capa visual (la presentación que no es la técnica) no hay escenas
  const oy = {}, env = [], padre = { postMessage: (m) => env.push(m) };
  const ventana = { location: { origin: 'https://sitio.example' }, addEventListener: (t, f) => { (oy[t] ||= []).push(f); }, matchMedia: () => ({ matches: false }), parent: padre };
  M.montarMando({ caps: [{ id: 'salud', nombre: 'Salud', pasos: [{}] }], estado: { ci: 0, pi: 0 }, ir: async () => {}, vecino: (c, p) => [c, p], ventana,
    documento: { querySelector: () => null, querySelectorAll: () => [] } });
  for (const f of oy.message) f({ data: { canal: 'yondo-presentacion', v: 1, orden: 'escena', id: 1, ...E() }, origin: 'https://sitio.example', source: padre });
  await dormir(10);
  r.sin_capa = env.filter((m) => m.id === 1).map((m) => [m.tipo, m.error]);
}

// E. Una escena que otra orden dejó atrás mientras cambiaba de paso: `reemplazada`, sin narrar ni aplicar nada
{
  const a = armar();
  a.retener = true;
  a.mandar('escena', { id: 1, ...E({ paso: 2 }) });
  await dormir(10);
  const enEspera = a.respuesta(1);
  a.mandar('quitar_explicacion', { id: 2 });
  await dormir(10);
  a.retenidos.splice(0).forEach((ok) => ok());
  await dormir(10);
  r.reemplazada_por_quitar = { en_espera: enEspera, respuesta: [a.respuesta(1)?.tipo, a.respuesta(1)?.reemplazada ?? null, a.respuesta(1)?.asentada ?? null],
    aplicar: a.nombres().includes('aplicar'), narrada: a.sub.classList.contains('narracion'), guiado: a.log.filter((l) => l[0] === 'guiado').map((l) => l[1]) };
  // otra escena (un salto): la primera sale sin tocar nada y la segunda narra lo suyo
  const b = armar();
  b.retener = true;
  b.mandar('escena', { id: 1, ...E({ paso: 2, frases: ['La que se queda atrás.'] }) });
  await dormir(10);
  b.mandar('escena', { id: 2, ...E({ paso: 3, n: 2, frases: ['La que vale.'] }) });
  await dormir(10);
  b.retenidos.splice(0).forEach((ok) => ok());
  await dormir(15);
  r.reemplazada_por_otra = { primera: [b.respuesta(1)?.tipo, b.respuesta(1)?.reemplazada ?? null], segunda: [b.respuesta(2)?.tipo, b.respuesta(2)?.reemplazada ?? null, b.respuesta(2)?.paso],
    aplicadas: b.log.filter((l) => l[0] === 'aplicar').length, texto: b.p.textContent, n: b.respuesta(2)?.recorrido?.n };
}

// F. Solo espera cuando la escena deja un modelo del atlas a la vista (el del paso de inmersión o el que pide)
{
  const a = armar();
  a.mandar('escena', { id: 1, ...E({ paso: 4 }) });
  await dormir(15);
  const f = { antes: a.respuesta(1), narrada_mientras: a.narrando(), tope: a.log.find((l) => l[0] === 'asentada')?.[1],
    orden: a.nombres().filter((n) => n === 'aplicar' || n === 'asentada') };
  a.asientos.splice(0).forEach((ok) => ok(true));
  await dormir(10);
  f.despues = [a.respuesta(1)?.tipo, a.respuesta(1)?.asentada, a.respuesta(1)?.aviso ?? null];
  // el que pide la escena, en un paso cualquiera; si no cargó a tiempo, el aviso dice cuál de las dos cosas pasó
  for (const [clave, cargando, id] of [['atlas', true, 2], ['asiento', false, 3]]) {
    a.mandar('escena', { id, ...E({ paso: 1, visual: { ...structuredClone(V0), inmersion: 'torre_bim' } }) });
    await dormir(10);
    a.cargando = cargando;
    a.asientos.splice(0).forEach((ok) => ok(false));
    await dormir(10);
    f[clave] = [a.respuesta(id)?.tipo, a.respuesta(id)?.asentada, a.respuesta(id)?.aviso ?? null];
  }
  a.cargando = false;
  // un paso de inmersión que pide la maqueta no deja ningún modelo a la vista: no espera
  a.log.length = 0;
  const maqueta = await a.pedir('escena', { id: 4, ...E({ paso: 4, visual: { ...structuredClone(V0), inmersion: 'maqueta' } }) });
  f.maqueta = [maqueta?.tipo, maqueta?.asentada, a.nombres().includes('asentada')];
  // y la que quedó atrás mientras el atlas cargaba también responde `reemplazada`
  a.mandar('escena', { id: 5, ...E({ paso: 4 }) });
  await dormir(10);
  a.mandar('quitar_explicacion', { id: 6 });
  await dormir(10);
  a.asientos.splice(0).forEach((ok) => ok(true));
  await dormir(10);
  f.reemplazada = a.respuesta(5)?.reemplazada ?? null;
  r.atlas = f;
}

// G. Lo que la narración señala: si todavía no está, se avisa y se vuelve a buscar mientras siga la escena
{
  const a = armar();
  let hay = false;
  a.existe = () => hay;
  const res = await a.pedir('escena', { id: 1, ...E({ resaltar: { tipo: 'especificacion', n: 2, en: 'ficha' } }) });
  const antes = a.log.filter((l) => l[0] === 'resaltar').length;
  hay = true;
  await dormir(260);
  const hallado = a.log.filter((l) => l[0] === 'resaltar').length;
  await dormir(1000);
  r.resaltar = { aviso: res?.aviso, antes, hallado, despues: a.log.filter((l) => l[0] === 'resaltar').length };
}

// H. `guiado`: mientras hay una narración, la capa lo sabe; se suelta con «¿Preguntas?», al quitar la explicación, con
// un paso pedido suelto y con un paso a mano
{
  const a = armar();
  const guiado = () => a.log.filter((l) => l[0] === 'guiado').map((l) => l[1]);
  const h = {};
  await a.pedir('escena', { id: 1, ...E() });
  h.escena = guiado().every((v) => v === true) && guiado().length >= 1;
  a.log.length = 0;
  await a.pedir('cierre', { id: 2, puntos: ['Uno', 'Dos'], rid: 'abcdef123456' });
  h.resumen = guiado();
  await a.pedir('cierre', { id: 3, puntos: null, rid: 'abcdef123456' });
  h.preguntas = guiado();
  a.log.length = 0;
  await a.pedir('escena', { id: 4, ...E() });
  a.log.length = 0;
  await a.pedir('quitar_explicacion', { id: 5 });
  h.quitar = guiado();
  await a.pedir('escena', { id: 6, ...E() });
  a.log.length = 0;
  await a.pedir('ir', { id: 7, capitulo: 'aguas' });
  h.ir = guiado();
  await a.pedir('escena', { id: 8, ...E() });
  a.log.length = 0;
  a.pasoAMano(0, 2);
  h.a_mano = guiado();
  h.a_mano_por = a.enviados.at(-1)?.por;
  r.guiado = h;
}

// I. La orden suelta `visual`: las partes nuevas, `mover` (con `ms`; por omisión 6000) y `animar`, con tolerancia
{
  const a = armar();
  const v = {};
  const pedir = async (id, extra) => { a.log.length = 0; const res = await a.pedir('visual', { id, ...extra }); return { tipo: res?.tipo, error: res?.error ?? null,
    aviso: res?.aviso ?? null, descartadas: res?.descartadas ?? null, log: a.log.filter((l) => l[0] === 'aplicar' || l[0] === 'mover').map((l) => l.slice(0, 3)), visual: res?.visual }; };
  v.nuevas = await pedir(1, { elevacion: 40, zoom: 1.5, mirar: 'torre', mostrar: ['red'], ocultar: [], aislar: 'torre', sin: ['torre.cubierta'] });
  v.solo_mover = await pedir(2, { mover: { giro: 90 } });
  v.mover_con_ms = await pedir(3, { mover: { giro: -45, zoom: 2, elevacion: 60 }, ms: 3000 });
  v.todo = await pedir(4, { camara: 'aerea', mover: { giro: 30 }, animar: true, ms: 8000 });
  v.solo_animar = await pedir(5, { animar: true });
  v.ms_sin_mover = await pedir(6, { rumbo: 200, ms: 4000 });
  v.parcial = await pedir(7, { camara: 'oblicua', rumbo: 400, mostrar: ['red', 'fantasma'], aislar: 'nada', mover: { giro: 20, zoom: 9 } });
  v.nada_vale = await pedir(8, { rumbo: 400, zoom: 'cerca' });
  v.nada_existe = await pedir(9, { aislar: 'nada' });
  v.vacia = await pedir(10, {});
  v.mover_nulo = await pedir(11, { mover: null, animar: false });
  v.solo_ms = await pedir(12, { ms: 3000 });
  v.clave_de_mas = await pedir(13, { camara: 'aerea', panel: true });
  r.visual = v;
  // con una capa de antes (sin `mover`), el movimiento va por `aplicar`
  const viejo = armar({ capa: 'vieja' });
  await viejo.pedir('visual', { id: 1, mover: { giro: 90 } });
  r.visual_capa_vieja = viejo.log.filter((l) => l[0] === 'aplicar').map((l) => l.slice(0, 3));
}

// J. Con una capa visual de antes (sin `depurar`, `guiado` ni `mover`) la escena no rompe: lo que su `validar` rechaza
// se descarta y lo demás se aplica
{
  const a = armar({ capa: 'vieja' });
  const res = await a.pedir('escena', { id: 1, ...E({ paso: 2, visual: { ...structuredClone(V0), enfoque: 'marte', detalle: 'torre', inmersion: 'otra', mostrar: ['red'] } }) });
  const aplicar = a.log.find((l) => l[0] === 'aplicar');
  r.capa_vieja = { tipo: res?.tipo, aviso: res?.aviso, descartadas: res?.descartadas, enfoque: aplicar?.[1].enfoque, detalle: aplicar?.[1].detalle,
    inmersion: aplicar?.[1].inmersion, mostrar: aplicar?.[1].mostrar, narrada: a.narrando() };
}

// K. La forma exacta de `mover`
r.mover_valido = [null, { giro: 30 }, { giro: -360, zoom: 0.3, elevacion: 85 }, { zoom: 3 }].map((m) => M.moverValido(m));
r.mover_malo = [undefined, {}, [], 'giro', { giro: 361 }, { giro: 1.5 }, { zoom: 0.2 }, { elevacion: 7 }, { lado: 1 }, { giro: null }, { giro: 30, lado: 1 }].map((m) => M.moverValido(m));
console.log(JSON.stringify(r));
process.exit(0);
"""


@requiere_node
def test_la_escena_muestra_mientras_narra_y_no_espera_el_asiento(tmp_path):
    r = _node(tmp_path, NODE_MANDO, MANDO_JS.as_uri())
    a = r["rapida"]
    # responde enseguida y sin llamar a `asentada` (que aquí no resolvería nunca)
    assert a["tipo"] == "estado" and a["asentada"] is True and a["tardo"] is True and a["ms_respuesta"] is True, a
    assert a["aviso"] is None and a["descartadas"] is None and "asentada" not in a["nombres"], a
    # el paso cambia sin telón ni vuelo propio (la cámara la lleva la capa), con la animación que pide la escena
    assert a["ir"] == ["ir", "salud", 2, {"dir": 1, "telon": False, "camara": False, "animar": True}], a
    # el orden: la capa sabe que hay un plan, el paso, la narración (ya está al aplicar), lo visual y lo que se señala
    orden = [n for n in a["nombres"] if n in ("guiado", "ir", "depurar", "aplicar", "resaltar", "restaurar")]
    assert orden.index("guiado") < orden.index("ir") < orden.index("aplicar") < orden.index("resaltar"), orden
    assert a["narrada_al_aplicar"] == [["frase activa", "Frase uno."], ["frase", "Frase dos."]], a
    # lo visual completo (catorce partes) y las opciones: lo que dura la narración, el movimiento y la animación
    assert a["visual"] == {"enfoque": None, "camara": "paso", "rumbo": 150, "elevacion": 30, "zoom": 1.2, "mirar": "torre",
                           "girar": False, "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": ["red"],
                           "ocultar": ["puestos"], "aislar": None, "sin": ["torre.cubierta"]}, a
    assert a["opciones"] == {"ms": 7400, "mover": {"giro": 30, "zoom": 1.4}, "animar": True}, a
    assert a["resaltar"] == {"tipo": "cifra", "n": 2}
    # el estado de la respuesta: el paso, la narración a la vista, el plan y lo visual con las partes nuevas
    assert a["donde"] == ["salud", 2, True, "Frase uno. Frase dos.", "orden"], a
    assert a["recorrido"] == {"rid": "abcdef123456", "n": 1, "de": 3}
    assert a["estado_visual"]["mostrar"] == ["red"] and a["estado_visual"]["elevacion"] == 30 and a["estado_visual"]["sin"] == ["torre.cubierta"]
    assert a["clases"] == ["con-voz", "narracion", "visible"] and a["vivo"] == "off", a
    # el mismo paso: sin `ir`, pero la capa igual recibe lo visual (la cámara viaja lo que dura la narración)
    b = r["mismo_paso"]
    assert b["tipo"] == "estado" and "ir" not in b["nombres"] and "aplicar" in b["nombres"], b
    assert b["opciones"] == {"ms": 9000, "mover": None, "animar": False}, b
    assert r["ms_estimado"] == [6650, 6650]
    assert r["solo_3d"] == [["panel", False]]


@requiere_node
def test_la_escena_descarta_lo_que_no_vale_y_solo_falla_por_lo_que_se_proyecta(tmp_path):
    r = _node(tmp_path, NODE_MANDO, MANDO_JS.as_uri())
    t = r["tolerante"]
    assert t["tipo"] == "estado" and t["aviso"] == "parcial" and t["narrada"] is True, t
    # lo que valía se aplicó: el rumbo, el zoom (con dos decimales), las piezas y las partes que existen, hoy/proyecto
    assert t["visual"] == {"enfoque": None, "camara": "paso", "rumbo": 90, "elevacion": None, "zoom": 1.26, "mirar": None,
                           "girar": False, "comparar": "hoy", "detalle": None, "inmersion": None, "mostrar": ["red"],
                           "ocultar": [], "aislar": None, "sin": ["torre.cubierta"]}, t
    assert t["opciones"] == {"ms": 7400, "mover": {"zoom": 1.5}, "animar": False}, t
    assert t["resaltados"] == 0 and "con-voz" not in t["clases"], t
    # las descartadas: hasta ocho, cada una con su clave y un motivo corto
    d = t["descartadas"]
    assert 1 <= len(d) <= 8 and all(set(x) == {"clave", "motivo"} and x["motivo"] and len(x["motivo"]) <= 120 for x in d), d
    claves = [x["clave"] for x in d]
    for clave in ("sorpresa", "otra", "camara", "mostrar", "aislar"):
        assert clave in claves, (clave, claves)
    # lo que falta es lo del paso, sin aviso (un reproductor o un recorrido de antes del plan guiado)
    m = r["minima"]
    assert m["tipo"] == "estado" and m["aviso"] is None and m["opciones"] == {"ms": 7400, "mover": None, "animar": False}, m
    assert m["visual"]["camara"] == "paso" and m["visual"]["mostrar"] == [] and len(m["visual"]) == 14, m
    v = r["visual_de_antes"]
    assert v["aviso"] is None and v["visual"]["enfoque"] == "torre" and v["visual"]["camara"] == "aerea" and v["visual"]["zoom"] is None, v
    e = r["error_de_la_capa"]
    assert e["tipo"] == "estado" and e["aviso"] == "parcial" and e["narrada"] is True, e
    assert e["descartadas"] == [{"clave": "visual", "motivo": "La presentación todavía no muestra ningún paso"}], e
    # lo que sí la tumba, sin mover nada
    for clave, x in r["fatales"].items():
        assert x == ["error", True], (clave, x)
    assert r["fatales_no_mueven"] == {"log": [], "narrada": False}, r["fatales_no_mueven"]
    assert r["doce"] == ["estado", {"rid": "abcdef123456", "n": 12, "de": 12}]
    assert r["sin_capa"] == [["error", "Esta presentación no tiene la capa visual: es la de la presentación técnica (?modo=tecnica)"]]
    # una capa visual de antes: su `validar` dice qué no existe, y lo demás se aplica
    c = r["capa_vieja"]
    assert c["tipo"] == "estado" and c["aviso"] == "parcial" and c["narrada"] is True, c
    assert (c["enfoque"], c["detalle"], c["inmersion"], c["mostrar"]) == (None, "torre", None, ["red"]), c
    assert [x["clave"] for x in c["descartadas"]] == ["enfoque", "inmersion"], c
    assert r["mover_valido"] == [True] * 4 and r["mover_malo"] == [False] * 11


@requiere_node
def test_la_escena_reemplazada_el_atlas_el_resaltado_y_el_guiado(tmp_path):
    r = _node(tmp_path, NODE_MANDO, MANDO_JS.as_uri())
    q = r["reemplazada_por_quitar"]
    assert q["en_espera"] is None and q["respuesta"] == ["estado", True, None], q
    assert q["aplicar"] is False and q["narrada"] is False and q["guiado"][-1] is False, q
    o = r["reemplazada_por_otra"]
    assert o["primera"] == ["estado", True] and o["segunda"] == ["estado", None, 3], o
    assert o["aplicadas"] == 1 and o["texto"] == "La que vale." and o["n"] == 2, o
    # el atlas: lo único que se espera (hasta 15 s), con la narración ya pintada y lo visual ya aplicado
    f = r["atlas"]
    assert f["antes"] is None and f["narrada_mientras"] is True and f["tope"] == 15000 and f["orden"] == ["aplicar", "asentada"], f
    assert f["despues"] == ["estado", True, None], f
    assert f["atlas"] == ["estado", False, "atlas"] and f["asiento"] == ["estado", False, "asiento"], f
    assert f["maqueta"] == ["estado", True, False] and f["reemplazada"] is True, f
    # lo que se señala: el aviso si no estaba, y se vuelve a buscar hasta encontrarlo (después, no más)
    s = r["resaltar"]
    assert s["aviso"] == "resaltar" and s["antes"] == 1 and s["hallado"] == 2 and s["despues"] == 2, s
    # la capa sabe cuándo hay un plan en pantalla
    g = r["guiado"]
    assert g["escena"] is True and g["resumen"] == [] and g["preguntas"] == [False], g
    assert g["quitar"] == [False] and g["ir"] == [False] and g["a_mano"] == [False] and g["a_mano_por"] == "persona", g


@requiere_node
def test_la_orden_visual_con_las_partes_nuevas_mover_y_animar(tmp_path):
    v = _node(tmp_path, NODE_MANDO, MANDO_JS.as_uri())["visual"]
    n = v["nuevas"]
    assert n["tipo"] == "estado" and n["aviso"] is None, n
    assert n["log"] == [["aplicar", {"elevacion": 40, "zoom": 1.5, "mirar": "torre", "mostrar": ["red"], "ocultar": [],
                                     "aislar": "torre", "sin": ["torre.cubierta"]}, {}]], n
    assert n["visual"]["aislar"] == "torre" and n["visual"]["mostrar"] == ["red"], n
    # solo el movimiento: desde donde está la cámara, 6 s si no dice cuánto. Lo que devuelve la capa al mover (`true`:
    # movió la cámara) no es un error: solo un texto lo es
    assert v["solo_mover"]["log"] == [["mover", {"giro": 90}, 6000]], v["solo_mover"]
    assert (v["solo_mover"]["tipo"], v["solo_mover"]["error"], v["solo_mover"]["aviso"]) == ("estado", None, None), v["solo_mover"]
    assert v["mover_con_ms"]["log"] == [["mover", {"giro": -45, "zoom": 2, "elevacion": 60}, 3000]], v["mover_con_ms"]
    assert v["mover_con_ms"]["tipo"] == "estado", v["mover_con_ms"]
    assert v["todo"]["log"] == [["aplicar", {"camara": "aerea"}, {"mover": {"giro": 30}, "ms": 8000, "animar": True}]], v["todo"]
    assert v["solo_animar"]["log"] == [["aplicar", {}, {"animar": True}]], v["solo_animar"]
    assert v["ms_sin_mover"]["log"] == [["aplicar", {"rumbo": 200}, {"ms": 4000}]], v["ms_sin_mover"]
    for clave in ("todo", "solo_animar", "ms_sin_mover"):
        assert v[clave]["tipo"] == "estado" and v[clave]["aviso"] is None, (clave, v[clave])
    # tolerante: lo que vale se aplica y la respuesta dice qué no
    p = v["parcial"]
    assert p["tipo"] == "estado" and p["aviso"] == "parcial", p
    assert p["log"] == [["aplicar", {"camara": "oblicua", "mostrar": ["red"]}, {"mover": {"giro": 20}, "ms": 6000}]], p
    assert sorted({x["clave"] for x in p["descartadas"]}) == ["aislar", "mostrar", "mover.zoom", "rumbo"], p
    # si no queda nada que aplicar, es un error con su porqué, y la capa no se toca
    assert v["nada_vale"]["tipo"] == "error" and v["nada_vale"]["log"] == [], v["nada_vale"]
    assert v["nada_vale"]["error"] == "Valor que la presentación no admite en: rumbo, zoom"
    assert v["nada_existe"]["tipo"] == "error" and v["nada_existe"]["error"] == "«nada» no está en Salud" and v["nada_existe"]["log"] == []
    for clave in ("vacia", "mover_nulo", "solo_ms"):
        assert (v[clave]["tipo"], v[clave]["error"], v[clave]["log"]) == ("error", "La orden visual no dice qué cambiar", []), (clave, v[clave])
    assert v["clave_de_mas"]["error"] == "La orden trae datos que la presentación no usa"


@requiere_node
def test_la_orden_visual_con_una_capa_de_antes(tmp_path):
    r = _node(tmp_path, NODE_MANDO, MANDO_JS.as_uri())
    assert r["visual_capa_vieja"] == [["aplicar", {}, {"mover": {"giro": 90}, "ms": 6000}]]


# ───────────────────────────── El puente: las formas nuevas ─────────────────────────────

NODE_PUENTE = r"""// El puente con las formas del plan guiado. Uso: node <guion> <agente-presentacion.js>
const [modulo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
// el canal del proyector, de mentira: la prueba le entrega los mensajes a mano
let canal = null;
globalThis.BroadcastChannel = class { constructor() { canal = this; } postMessage() {} close() {} };
const P = await import(modulo);
const r = {};
const copia = (x) => JSON.parse(JSON.stringify(x));
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const escena = (extra = {}) => ({ capitulo: 'salud', paso: 3, panel: true, visual: { ...copia(V), rumbo: 150, elevacion: 30, zoom: 1.2, mirar: 'torre',
  mostrar: ['telesalud'], sin: ['torre.cubierta'] }, resaltar: { tipo: 'cifra', n: 2 }, mover: { giro: 60, zoom: 1.5 }, animar: true,
  frases: ['La torre tiene cuatro pisos.'], sostener_ms: 1300, ...extra });
const rec = (escenas = [escena()]) => ({ id: 'abcdef123456', titulo: 'La torre', escenas, cierre: null });
const igual = (x) => JSON.stringify(P.recorridoValido(x)) === JSON.stringify(x);

// El recorrido: la forma nueva, copiada tal cual; doce pasos; el de antes del plan guiado también vale
r.nuevo = igual(rec());
r.copiado = (() => { const x = rec(), y = P.recorridoValido(x); return y !== x && y.escenas[0] !== x.escenas[0] && y.escenas[0].visual.mostrar !== x.escenas[0].visual.mostrar && y.escenas[0].mover !== x.escenas[0].mover; })();
r.doce = igual(rec(Array.from({ length: 12 }, () => escena())));
r.trece = P.recorridoValido(rec(Array.from({ length: 13 }, () => escena())));
const deAntes = { capitulo: 'salud', paso: 3, panel: true, visual: { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null },
  resaltar: null, frases: ['Como antes.'], sostener_ms: 1100 };
r.de_antes = igual(rec([deAntes]));
r.sin_mover = igual(rec([escena({ mover: null, animar: false })]));
const conVisual = (cambio) => { const e = escena(); Object.assign(e.visual, cambio); return !!P.recorridoValido(rec([e])); };
const conEscena = (cambio) => !!P.recorridoValido(rec([escena(cambio)]));
r.visual_validas = [{ elevacion: 8 }, { elevacion: 85 }, { zoom: 0.3 }, { zoom: 3 }, { zoom: 1.06 }, { mirar: 'torre_hospital' }, { mostrar: [] },
  { mostrar: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] }, { ocultar: ['red'] }, { aislar: 'torre' }, { sin: ['torre.cubierta', 'torre.solar'] }].map(conVisual);
r.visual_malas = [{ elevacion: 7 }, { elevacion: 86 }, { elevacion: 30.5 }, { elevacion: '30' }, { zoom: 0.29 }, { zoom: 3.01 }, { zoom: 1.234 }, { zoom: '1' },
  { mirar: 'Torre' }, { mirar: 7 }, { mostrar: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i'] }, { mostrar: ['a', 'a'] }, { mostrar: 'a' }, { mostrar: ['A b'] },
  { mostrar: null }, { ocultar: [3] }, { aislar: 3 }, { aislar: 'a.b' }, { sin: ['torre'] }, { sin: ['torre.Cubierta'] }, { sin: ['a.b', 'a.b'] }, { tema: 'oscuro' },
  { otra: 1 }].map(conVisual);
r.mover_validos = [{ giro: -360 }, { giro: 360 }, { zoom: 0.3, elevacion: 85 }, { giro: 12, zoom: 1.06 }, { giro: 10, zoom: null }, null].map((mover) => conEscena({ mover }));
r.mover_malos = [{}, { giro: 361 }, { giro: 1.5 }, { zoom: 4 }, { elevacion: 5 }, { lado: 1 }, [], 'x', { giro: null }, 7].map((mover) => conEscena({ mover }));
r.animar = [true, false, 'si', 1, null].map((animar) => conEscena({ animar }));
r.escena_mala = [{ otra: 1 }, { sostener_ms: 9000 }, { resaltar: { tipo: 'cifra', n: 99 } }].map(conEscena);
r.sin_base = (() => { const e = escena(); delete e.visual.camara; return P.recorridoValido(rec([e])); })();

// La acción `visual`: las partes nuevas, `mover`, `animar` y `ms`
const A = (x) => P.accionPresentacion({ tipo: 'presentacion', ...x });
r.accion_validas = [
  A({ op: 'visual', elevacion: 40, zoom: 1.5, mirar: 'torre', mostrar: ['red'], ocultar: [], aislar: null, sin: ['torre.cubierta'] }),
  A({ op: 'visual', mover: { giro: 90 } }), A({ op: 'visual', animar: true }),
  A({ op: 'visual', camara: 'aerea', mover: { giro: 30, zoom: 1.4, elevacion: 50 }, animar: false, ms: 8000 }),
  A({ op: 'visual', rumbo: 90, mover: null }),
];
r.accion_malas = [A({ op: 'visual', ms: 3000 }), A({ op: 'visual', mover: null }), A({ op: 'visual', animar: false }), A({ op: 'visual', mover: { giro: 400 } }),
  A({ op: 'visual', mover: {} }), A({ op: 'visual', camara: 'aerea', ms: -1 }), A({ op: 'visual', camara: 'aerea', ms: 120001 }), A({ op: 'visual', camara: 'aerea', animar: 'si' }),
  A({ op: 'visual', mostrar: ['a', 'a'] }), A({ op: 'visual', sin: ['torre'] }), A({ op: 'visual', zoom: 5 }), A({ op: 'visual', elevacion: 90 }),
  A({ op: 'ir', capitulo: 'salud', mover: { giro: 3 } }), A({ op: 'vista', panel: true, animar: true }), A({ op: 'explicar', explicacion: 'x', ms: 3000 }),
  A({ op: 'visual', constructor: 1 })];
// la copia no comparte las listas ni el movimiento con lo que llegó
r.accion_copiada = (() => { const x = { tipo: 'presentacion', op: 'visual', mostrar: ['red'], mover: { giro: 9 } }, y = P.accionPresentacion(x); return y.mostrar !== x.mostrar && y.mover !== x.mover; })();

// El estado de la pantalla en off: las partes nuevas (lo que falta es lo del paso) y las acciones
const base = { v: 3, capitulo: 'salud', paso: 2, explicacion: null, panel: true, indice: false, fichas: false, completa: false, orden_completa: 0 };
const e0 = P.estadoDePantalla(base);
r.pantalla_inicial = [e0.elevacion, e0.zoom, e0.mirar, e0.mostrar, e0.ocultar, e0.aislar, e0.sin, e0.mover, e0.animar];
const conPiezas = { ...base, elevacion: 40, zoom: 1.5, mirar: 'torre', mostrar: ['red', 'torre'], ocultar: ['puestos'], aislar: null, sin: ['torre.cubierta'] };
const e1 = P.estadoDePantalla(conPiezas);
r.pantalla_nueva = [e1.elevacion, e1.zoom, e1.mirar, e1.mostrar, e1.ocultar, e1.aislar, e1.sin];
r.pantalla_malas = [{ ...base, elevacion: 90 }, { ...base, zoom: 0 }, { ...base, mostrar: 'red' }, { ...base, sin: ['x'] }, { ...base, aislar: 'A' },
  { ...base, mover: { giro: 999 } }, { ...base, animar: 'si' }].map((e) => P.estadoDePantalla(e));
// las listas se comparan por contenido: el mismo estado leído dos veces no manda nada
r.sin_cambios = P.ordenesHacia(P.estadoDePantalla(conPiezas), P.estadoDePantalla(copia(conPiezas)));
r.desde_inicial = P.ordenesHacia(e0, e1);
r.cambia_una_lista = P.ordenesHacia(e1, P.estadoDePantalla({ ...conPiezas, mostrar: ['red'] }));
r.vuelve = P.ordenesHacia(e1, e0);
r.otro_paso = P.ordenesHacia(e1, P.estadoDePantalla({ ...conPiezas, paso: 3 }));
r.otro_paso_limpio = P.ordenesHacia(e1, P.estadoDePantalla({ ...base, paso: 3 }));
// las acciones no son estado: van una vez por cada versión nueva de la pantalla que las trae (la misma pedida otra vez
// se hace otra vez), no con la misma versión leída de nuevo, y nunca al abrir o recargar la pantalla
const conMover = P.estadoDePantalla({ ...conPiezas, v: 4, mover: { giro: 90 }, animar: true });
r.acciones = [P.ordenesHacia(e1, conMover), P.ordenesHacia(conMover, P.estadoDePantalla({ ...conPiezas, v: 4, mover: { giro: 90 }, animar: true })),
  P.ordenesHacia(conMover, P.estadoDePantalla({ ...conPiezas, v: 5, mover: { giro: 90 }, animar: true })),
  P.ordenesHacia(null, conMover).filter((o) => o.mover !== undefined || o.animar !== undefined)];

// El avance: doce pasos y el aviso `parcial`
const pr = { rid: 'abcdef123456', n: 12, de: 12, fase: 'narrando', frase: 0, voz: 'activa', t_ms: 10 };
r.progreso = [P.progresoValido({ ...pr, aviso: 'parcial' })?.aviso ?? null, P.progresoValido(pr)?.n ?? null, P.progresoValido({ ...pr, n: 13, de: 13 }),
  P.progresoValido({ ...pr, aviso: 'otro' })];
r.estado_doce = P.estadoValido({ capitulo: 'salud', paso: 2, total: 4, recorrido: { rid: 'abcdef123456', n: 12, de: 12 } })?.recorrido ?? null;
r.avisos = P.AVISOS;

// La voz de la vista de esta pestaña, por el puente (el interruptor de la tarjeta del chat)
const voz = [];
voz.push(P.alternarVozRecorrido());   // sin vista aquí
let estadoVoz = 'apagada', toques = 0;
const control = { aplicar: async (l) => l.map((a) => ({ op: a.op, ok: true })), estado: () => ({ capitulo: 'salud', paso: 1, total: 4 }),
  alternarVoz: () => { toques++; estadoVoz = estadoVoz === 'activa' ? 'apagada' : 'activa'; return estadoVoz; } };
const quitar = P.registrarPresentacion(control);
voz.push(P.alternarVozRecorrido(), P.alternarVozRecorrido());
control.alternarVoz = () => 'encendidísima';
voz.push(P.alternarVozRecorrido());   // un estado que no es de la lista
control.alternarVoz = () => { throw new Error('x'); };
voz.push(P.alternarVozRecorrido());   // nunca lanza
control.alternarVoz = () => { toques++; return 'sin_activar'; };
voz.push(P.alternarVozRecorrido());
// con una ventana de proyector viva, el plan suena allá: aquí no se enciende nada
canal.onmessage({ data: { canal: 'yondo-presentacion', v: 1, tipo: 'proyector', id: 'abcdefgh12345678', desde: Date.now(), listo: true,
  estado: { capitulo: 'salud', paso: 1, total: 4 } } });
await new Promise((ok) => setTimeout(ok, 20));
const antes = toques;
voz.push(P.proyectorVivo(), P.alternarVozRecorrido(), toques === antes);
canal.onmessage({ data: { canal: 'yondo-presentacion', v: 1, tipo: 'adios', id: 'abcdefgh12345678' } });
await new Promise((ok) => setTimeout(ok, 20));
voz.push(P.alternarVozRecorrido());
quitar();
voz.push(P.alternarVozRecorrido());   // la vista se cerró
P.registrarPresentacion({ aplicar: async () => [], estado: () => null });   // una vista que no registra su voz
voz.push(P.alternarVozRecorrido());
r.voz = voz;
console.log(JSON.stringify(r));
process.exit(0);
"""


@requiere_node
def test_el_puente_valida_las_formas_nuevas(tmp_path):
    r = _node(tmp_path, NODE_PUENTE, PUENTE_JS.as_uri())
    # el recorrido con la forma nueva vuelve copiado e idéntico; doce pasos sí, trece no; el de antes también vale
    assert r["nuevo"] is True and r["copiado"] is True and r["doce"] is True and r["trece"] is None, r
    assert r["de_antes"] is True and r["sin_mover"] is True, r
    assert r["visual_validas"] == [True] * 11, r["visual_validas"]
    assert r["visual_malas"] == [False] * 23, r["visual_malas"]
    assert r["mover_validos"] == [True] * 6, r["mover_validos"]
    assert r["mover_malos"] == [False] * 10, r["mover_malos"]
    assert r["animar"] == [True, True, False, False, False], r["animar"]
    assert r["escena_mala"] == [False] * 3 and r["sin_base"] is None, r
    # la acción `visual`
    assert r["accion_validas"] == [
        {"tipo": "presentacion", "op": "visual", "elevacion": 40, "zoom": 1.5, "mirar": "torre", "mostrar": ["red"],
         "ocultar": [], "aislar": None, "sin": ["torre.cubierta"]},
        {"tipo": "presentacion", "op": "visual", "mover": {"giro": 90}},
        {"tipo": "presentacion", "op": "visual", "animar": True},
        {"tipo": "presentacion", "op": "visual", "camara": "aerea", "mover": {"giro": 30, "zoom": 1.4, "elevacion": 50},
         "animar": False, "ms": 8000},
        {"tipo": "presentacion", "op": "visual", "rumbo": 90, "mover": None}], r["accion_validas"]
    assert r["accion_malas"] == [None] * 16, r["accion_malas"]
    assert r["accion_copiada"] is True


@requiere_node
def test_el_puente_en_la_pantalla_en_off_el_avance_y_la_voz(tmp_path):
    r = _node(tmp_path, NODE_PUENTE, PUENTE_JS.as_uri())
    assert r["pantalla_inicial"] == [None, None, None, [], [], None, [], None, False], r["pantalla_inicial"]
    assert r["pantalla_nueva"] == [40, 1.5, "torre", ["red", "torre"], ["puestos"], None, ["torre.cubierta"]]
    assert r["pantalla_malas"] == [None] * 7, r["pantalla_malas"]
    # las listas, por contenido
    assert r["sin_cambios"] == [], r["sin_cambios"]
    assert r["desde_inicial"] == [{"orden": "visual", "elevacion": 40, "zoom": 1.5, "mirar": "torre", "mostrar": ["red", "torre"],
                                   "ocultar": ["puestos"], "sin": ["torre.cubierta"]}], r["desde_inicial"]
    assert r["cambia_una_lista"] == [{"orden": "visual", "mostrar": ["red"]}], r["cambia_una_lista"]
    assert r["vuelve"] == [{"orden": "visual", "elevacion": None, "zoom": None, "mirar": None, "mostrar": [], "ocultar": [],
                            "sin": []}], r["vuelve"]
    # al cambiar de paso la presentación deja lo visual en lo del paso: va lo que difiere de eso
    assert r["otro_paso"] == [{"orden": "ir", "capitulo": "salud", "paso": 3},
                              {"orden": "visual", "elevacion": 40, "zoom": 1.5, "mirar": "torre", "mostrar": ["red", "torre"],
                               "ocultar": ["puestos"], "sin": ["torre.cubierta"]}], r["otro_paso"]
    assert r["otro_paso_limpio"] == [{"orden": "ir", "capitulo": "salud", "paso": 3}], r["otro_paso_limpio"]
    assert r["acciones"] == [[{"orden": "visual", "mover": {"giro": 90}, "animar": True}], [],
                             [{"orden": "visual", "mover": {"giro": 90}, "animar": True}], []], r["acciones"]
    assert r["progreso"] == ["parcial", 12, None, None] and r["estado_doce"] == {"rid": "abcdef123456", "n": 12, "de": 12}
    assert r["avisos"] == ["atlas", "resaltar", "asiento", "voz", "parcial"]
    # la voz: null sin vista; con ella, el estado en que quedó; null si no es un estado, si falla o si manda un proyector
    assert r["voz"] == [None, "activa", "apagada", None, None, "sin_activar", True, None, True, "sin_activar", None, None], r["voz"]


# ───────────────────────────── El reproductor: `ms`, `previa` y `parcial` ─────────────────────────────

NODE_REPRODUCTOR = r"""// El reproductor con un reloj de mentira. Uso: node <guion> <reproductor.js>
const R = await import(process.argv[2]);
const { crearReproductor, lecturaMs, narracionMs, PREVIA_MS, RESPIRO_MS, ENTRE_FRASES_MS } = R;
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
const V = { enfoque: null, camara: 'paso', rumbo: 150, elevacion: 30, zoom: 1.2, mirar: 'torre', girar: false, comparar: 'proyecto', detalle: null,
  inmersion: null, mostrar: ['red'], ocultar: [], aislar: null, sin: ['torre.cubierta'] };
const esc = (paso, frases, extra = {}) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, mover: null, animar: false, frases, sostener_ms: 1300, ...extra });
const rec = (id, escenas) => ({ id: id.repeat(12), titulo: 'Prueba', cierre: null,
  escenas: escenas || [esc(1, ['Frase uno.', 'Frase dos.'], { mover: { giro: 30, zoom: 1.4 }, animar: true }), esc(2, ['Frase tres.'])] });
const nombre = (o) => o.orden + (o.orden === 'escena' ? ':' + o.n : o.frase !== undefined ? ':f' + o.frase : o.pausa !== undefined ? ':p' + o.pausa : '');
function armar({ respuesta = () => ({ ok: true }) } = {}) {
  const reloj = relojFalso(), ordenes = [], enteras = [], avances = [];
  const rep = crearReproductor({ reloj, orden: async (o, opciones) => { ordenes.push(nombre(o)); enteras.push([o, opciones]); return respuesta(o, reloj); },
    avisar: (p) => avances.push(`${p.rid[0]}${p.n}/${p.fase}${p.frase ? ':' + p.frase : ''}${p.motivo ? '!' + p.motivo : ''}${p.aviso ? '?' + p.aviso : ''}`) });
  return { reloj, ordenes, enteras, avances, rep };
}
const out = { PREVIA_MS, narracion: [narracionMs(['Frase uno.']), narracionMs(['Frase uno.', 'Frase dos.']), narracionMs(['x'.repeat(100), 'y'.repeat(100), 'z'])],
  lectura: [lecturaMs('Frase uno.'), lecturaMs('x'.repeat(100))] };

// 1. La orden `escena`: lo que durará la narración (`ms`), el movimiento y la animación de la escena; y ya no hay espera
// de asiento: respondida la orden, a los RESPIRO_MS suena la primera frase
{
  const { reloj, ordenes, enteras, avances, rep } = armar();
  const primera = rep.iniciar(rec('a'));
  await reloj.avanzar(1);
  const [o, opciones] = enteras[0];
  out.orden = { claves: Object.keys(o).sort(), ms: o.ms, mover: o.mover, animar: o.animar, visual: o.visual, n: [o.n, o.de], plazo: opciones?.plazo, primera: await primera };
  out.antes_del_respiro = ordenes.slice();
  await reloj.avanzar(RESPIRO_MS);
  out.tras_el_respiro = ordenes.slice();
  out.fase = rep.estado().fase;
  // la segunda escena (sin movimiento propio) y una escena de antes del plan guiado (sin `mover` ni `animar`)
  rep.siguiente();
  await reloj.avanzar(1);
  out.segunda = { ms: enteras.at(-1)[0].ms, mover: enteras.at(-1)[0].mover, animar: enteras.at(-1)[0].animar };
  const b = armar();
  const { mover: _m, animar: _a, ...vieja } = esc(1, ['Como antes.']);
  b.rep.iniciar(rec('b', [vieja]));
  await b.reloj.avanzar(1);
  out.de_antes = { mover: b.enteras[0][0].mover, animar: b.enteras[0][0].animar, ms: b.enteras[0][0].ms };
}

// 2. `previa`: un plan nuevo espera antes de su primer paso, en «preparando»
{
  const { reloj, ordenes, avances, rep } = armar();
  let primera = null;
  rep.iniciar(rec('c'), { previa: PREVIA_MS }).then((x) => { primera = [x, reloj.ahora()]; });
  await reloj.avanzar(1);
  const p = { al_empezar: { ordenes: ordenes.slice(), avances: avances.slice(), estado: rep.estado() } };
  await reloj.avanzar(PREVIA_MS - 20);
  p.casi = ordenes.slice();
  await reloj.avanzar(30);
  p.despues = ordenes.slice();
  p.primera = primera;
  out.previa = p;
}
// se pausa (la espera no corre) y sigue con lo que le faltaba
{
  const { reloj, ordenes, avances, rep } = armar();
  rep.iniciar(rec('d'), { previa: PREVIA_MS });
  await reloj.avanzar(500);
  rep.pausar('boton');
  await reloj.avanzar(8000);
  const p = { en_pausa: { ordenes: ordenes.slice(), estado: rep.estado(), avance: avances.at(-1) } };
  rep.continuar();
  await reloj.avanzar(1);
  p.al_seguir = [rep.estado().fase, avances.at(-1)];
  await reloj.avanzar(PREVIA_MS - 500 - 100);
  p.casi = ordenes.slice();
  await reloj.avanzar(150);
  p.despues = ordenes.slice(0, 1);
  out.previa_pausa = p;
}
// la pausa suave del chat (la persona escribe) también entra en la espera
{
  const { reloj, ordenes, avances, rep } = armar();
  rep.iniciar(rec('e'), { previa: PREVIA_MS });
  await reloj.avanzar(300);
  rep.control('pausar', { suave: true });
  await reloj.avanzar(5000);
  out.previa_suave = { ordenes: ordenes.slice(), avance: avances.at(-1) };
}
// la cortan «siguiente» (empieza ya, por el primer paso), «repetir», un detener y otro plan
{
  const a = armar();
  a.rep.iniciar(rec('f'), { previa: PREVIA_MS });
  await a.reloj.avanzar(300);
  a.rep.siguiente();
  await a.reloj.avanzar(1);
  const tras = a.ordenes.slice();
  await a.reloj.avanzar(PREVIA_MS + 100);
  out.previa_siguiente = { tras, escenas: a.ordenes.filter((x) => x.startsWith('escena')) };
  const b = armar();
  b.rep.iniciar(rec('g'), { previa: PREVIA_MS });
  await b.reloj.avanzar(300);
  b.rep.repetir();
  await b.reloj.avanzar(1);
  out.previa_repetir = b.ordenes.slice();
  const c = armar();
  let primera = null;
  c.rep.iniciar(rec('h'), { previa: PREVIA_MS }).then((x) => { primera = x; });
  await c.reloj.avanzar(300);
  const detuvo = c.rep.detener('boton');
  await c.reloj.avanzar(PREVIA_MS + 2000);
  out.previa_detener = { detuvo: await detuvo, ordenes: c.ordenes.slice(), ultimo: c.avances.at(-1), primera, activo: c.rep.activo() };
  const d = armar();
  d.rep.iniciar(rec('i'), { previa: PREVIA_MS });
  await d.reloj.avanzar(300);
  d.rep.iniciar(rec('j'));
  await d.reloj.avanzar(PREVIA_MS + 100);
  out.previa_reemplazo = { escenas: d.enteras.filter(([o]) => o.orden === 'escena').map(([o]) => o.rid[0] + o.n), deI: d.avances.filter((x) => x[0] === 'i').at(-1) };
  // después de la espera, «siguiente» vuelve a ser el paso que sigue
  const e = armar();
  e.rep.iniciar(rec('k'), { previa: PREVIA_MS });
  await e.reloj.avanzar(PREVIA_MS + 50);
  e.rep.siguiente();
  await e.reloj.avanzar(1);
  out.siguiente_despues = e.ordenes.filter((x) => x.startsWith('escena'));
}
// sin `previa` (reanudar, volver a reproducir, un traspaso) no espera nada
{
  const { reloj, ordenes, rep } = armar();
  rep.iniciar(rec('l'), { desde: 2 });
  await reloj.avanzar(1);
  out.sin_previa = ordenes.slice();
}

// 3. Lo que la presentación avisa de la escena sigue como aviso: `parcial` sí; uno que no es de la lista, no
{
  const { reloj, avances, rep } = armar({ respuesta: (o) => (o.orden === 'escena' ? { ok: true, aviso: o.n === 1 ? 'parcial' : 'raro' } : { ok: true }) });
  rep.iniciar(rec('m'));
  await reloj.avanzar(1);
  rep.siguiente();
  await reloj.avanzar(1);
  out.avisos = avances.filter((x) => x.includes('?'));
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_reproductor_manda_ms_espera_la_previa_y_avisa_parcial(tmp_path):
    r = _node(tmp_path, NODE_REPRODUCTOR, REPRODUCTOR_JS.as_uri())
    assert r["PREVIA_MS"] == 1800 and r["lectura"] == [3200, 7700]
    # lo que dura la narración: la lectura de las frases y 250 ms entre ellas
    assert r["narracion"] == [3200, 6650, 7700 + 7700 + 3200 + 500]
    o = r["orden"]
    assert o["claves"] == ["animar", "capitulo", "de", "frases", "mover", "ms", "n", "orden", "panel", "paso", "resaltar",
                           "rid", "titulo", "visual", "voz"], o
    assert o["ms"] == 6650 and o["mover"] == {"giro": 30, "zoom": 1.4} and o["animar"] is True and o["n"] == [1, 2], o
    assert o["visual"]["mostrar"] == ["red"] and o["visual"]["elevacion"] == 30 and o["plazo"] == 25000 and o["primera"] is True, o
    # respondida la escena, el respiro y la primera frase: sin espera de asiento
    assert r["antes_del_respiro"] == ["escena:1"] and r["tras_el_respiro"] == ["escena:1", "narracion:f0"] and r["fase"] == "narrando", r
    assert r["segunda"] == {"ms": 3200, "mover": None, "animar": False}
    assert r["de_antes"] == {"mover": None, "animar": False, "ms": 3200}
    # la previa: «preparando» desde el comienzo, y la primera escena recién al cumplirse
    p = r["previa"]
    assert p["al_empezar"]["ordenes"] == [] and p["al_empezar"]["avances"] == ["c1/preparando"], p
    assert p["al_empezar"]["estado"]["fase"] == "preparando" and p["al_empezar"]["estado"]["n"] == 1, p
    assert p["casi"] == [] and p["despues"] == ["escena:1"] and p["primera"] == [True, 1800], p
    # pausable: en pausa no corre, y al seguir espera lo que le faltaba
    q = r["previa_pausa"]
    assert q["en_pausa"]["ordenes"] == [] and q["en_pausa"]["estado"]["fase"] == "pausa" and q["en_pausa"]["avance"] == "d1/pausa!boton", q
    assert q["al_seguir"] == ["preparando", "d1/preparando"] and q["casi"] == [] and q["despues"] == ["escena:1"], q
    assert r["previa_suave"] == {"ordenes": [], "avance": "e1/pausa!mensaje"}
    # cortable: «siguiente» empieza ya por el primer paso (no lo salta) y la espera no vuelve a disparar nada
    s = r["previa_siguiente"]
    assert s["tras"] == ["escena:1"] and s["escenas"] == ["escena:1"], s
    assert r["previa_repetir"] == ["escena:1"]
    d = r["previa_detener"]
    assert d == {"detuvo": True, "ordenes": [], "ultimo": "h1/detenido!boton", "primera": False, "activo": False}, d
    x = r["previa_reemplazo"]
    assert x["escenas"] == ["j1"] and x["deI"] == "i1/detenido!reemplazo", x
    assert r["siguiente_despues"] == ["escena:1", "escena:2"]
    assert r["sin_previa"] == ["escena:2"]
    assert r["avisos"] == ["m1/preparando?parcial"]
