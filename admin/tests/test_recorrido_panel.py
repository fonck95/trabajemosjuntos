"""Lo que el panel hace con el recorrido narrado (docs/agente.md, «Recorridos narrados»), con Node: los casos que la
revisión del recorrido encontró en el puente (agente-presentacion.js), en la tarjeta del chat (agente-recorrido.js) y en
las reglas de lo que se proyecta, y que test_recorrido.py no cubre.

* Las reglas: nada de lo que se le manda a la presentación técnica lleva costos (la explicación de `explicar` y de `ir`,
  la que dice el estado, el título y las frases del recorrido): ni «$», «💲», «COP», «pesos», «billones de» o «millones
  de pesos», en mayúsculas o minúsculas. Y una tirada de dígitos pegados con el apóstrofo (recto o tipográfico), la prima
  o un punto de viñeta cuenta entera: «C.C. 71'234.567» es una cédula. El puente y mando.js deciden igual, y el servidor
  (`texto_proyectable`) también.
* El puente con un proyector ocupado (armando su maqueta 3D): un recorrido que no acusa a tiempo se reproduce en la
  pestaña y el proyector no lo aplica al liberarse (caducó: sonaría en los dos); cuando vuelve a latir, la pestaña se lo
  pasa desde la escena en curso, sin detenerlo por «otra_orden». Una orden que no es un recorrido sí la aplica tarde:
  queda en el mismo paso que la pestaña. Y la persona que mueve la presentación de la pestaña mientras el recorrido suena
  en el proyector lo pausa allá (antes le llevaba su paso y lo detenía, y la tarjeta culpaba al asistente), y la pestaña
  vuelve a la escena del proyector.
* La tarjeta, con un DOM mínimo y la API simulada: «Volver a reproducir» pasa por el servidor y sigue al id nuevo (si ya
  hay uno más nuevo, 409: no se puede; si el recorrido no está en este navegador, ni lo pide); la barra y la pausa al
  escribir siguen a la tarjeta del recorrido que suena, no a la más nueva; en la pantalla en off, una pantalla que deja
  de avisar (o que nunca empezó) lo deja detenido por falta de respuesta, una pausa larga no, y un control vuelve a
  seguirlo.
"""
import json
import subprocess
from pathlib import Path

import pytest

from app.proyectable import texto_proyectable
from test_agente_presentacion import requiere_node

ADMIN = Path(__file__).resolve().parents[1]
JS = ADMIN / "web" / "js"
PUENTE_JS = JS / "agente-presentacion.js"
TARJETA_JS = JS / "agente-recorrido.js"
MANDO_JS = ADMIN.parent / "web" / "js" / "propuesta" / "mando.js"


def _node(tmp_path: Path, guion: str, *args: str, timeout: int = 90) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=timeout,
                       cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


# ───────────────────────────── Las reglas de lo que se proyecta ─────────────────────────────

# Costos como se escriben en Colombia, en mayúsculas o minúsculas (también el monto en pesos que antes pasaba)
CON_PLATA = ("La torre cuesta $106.271 M", "Cuesta 💲116.294 M", "Son ＄5.000 de más", "Inversión: COP 106.271 millones",
             "Inversión: cop 106.271 millones", "Cuesta 106.271 Millones de pesos", "MILLONES DE PESOS 116.294",
             "La obra vale 1,2 billones de pesos", "Vale 1,2 Billones de la plata", "Son 300 Pesos al mes",
             "Por habitante, $1.156.350")
# Cédulas y teléfonos con separadores pegados que no eran los de siempre
TIRADAS = ("Habla doña Ana, C.C. 71'234.567", "cédula 1'023'456.789", "cédula 1’023’456", "Llamen al 300‧123‧4567",
           "Tel 300•123•4567", "Tel 300∙123∙4567", "Tel 300・123・4567", "Tel 300･123･4567", "Tel 300′123′4567",
           "Tel ３００＇１２３＇４５６７")
# Lo que sí pasa (y se ve tal cual): palabras que solo se parecen, apóstrofos sin cifras, periodos y rangos
PASAN = ("Cuatro pisos y 15 camas", "La propuesta 2028–2031", "Rango 1.346–1.500 kWh", "En 2028, 300 viviendas",
         "Una copa de agua", "El peso de la estructura", "Los 22.429 habitantes de Yondó", "Dice 'sí' y 'no'",
         "Son 3 millones de visitas", "La torre, en 1'2 minutos")

NODE_REGLAS = r"""// Cada texto por el puente (explicar, ir, el estado, el recorrido) y por el mando. Uso: node <guion> <puente> <mando> <casos>
import { readFileSync } from 'node:fs';
const [puente, mando, archivo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const P = await import(puente), M = await import(mando);
const V = { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null };
const recorrido = (frase, titulo = 'La torre') => ({ id: 'abcdef123456', titulo, cierre: null,
  escenas: [{ capitulo: 'salud', paso: 3, panel: true, visual: V, resaltar: null, frases: [frase], sostener_ms: 1000 }] });
const a = (x) => P.accionPresentacion({ tipo: 'presentacion', ...x });
const casos = JSON.parse(readFileSync(archivo, 'utf-8'));
console.log(JSON.stringify(casos.map((t) => ({
  explicar: a({ op: 'explicar', explicacion: t })?.explicacion ?? null,
  ir: a({ op: 'ir', capitulo: 'salud', paso: 2, explicacion: t })?.explicacion ?? null,
  estado: P.estadoValido({ capitulo: 'salud', paso: 2, total: 4, explicacion: true, texto: t })?.texto ?? null,
  frase: !!P.recorridoValido(recorrido(t)),
  titulo: !!P.recorridoValido(recorrido('Cuatro pisos y 15 camas.', t)),
  cierre: !!P.recorridoValido({ ...recorrido('Cuatro pisos.'), cierre: { puntos: [t] } }),
  mando: M.textoVisible(t),
}))));
"""


def _reglas(tmp_path, casos):
    (tmp_path / "casos.json").write_text(json.dumps(casos, ensure_ascii=False), encoding="utf-8")
    return _node(tmp_path, NODE_REGLAS, PUENTE_JS.as_uri(), MANDO_JS.as_uri(), str(tmp_path / "casos.json"))


@requiere_node
def test_nada_de_lo_que_se_proyecta_lleva_costos_ni_tiradas_pegadas(tmp_path):
    """El puente frena la plata y las tiradas pegadas en la explicación de `explicar` y de `ir`, en la que dice el estado
    y en el título, las frases y el cierre del recorrido, igual que mando.js; lo que solo se les parece pasa tal cual."""
    malos = list(CON_PLATA + TIRADAS)
    salida = _reglas(tmp_path, malos + list(PASAN))
    for t, x in zip(malos, salida[:len(malos)], strict=True):
        assert x == {"explicar": None, "ir": None, "estado": None, "frase": False, "titulo": False, "cierre": False,
                     "mando": None}, (t, x)
    for t, x in zip(PASAN, salida[len(malos):], strict=True):
        assert x == {"explicar": t, "ir": t, "estado": t, "frase": True, "titulo": True, "cierre": True, "mando": t}, (t, x)


def test_el_servidor_decide_lo_mismo():
    """`texto_proyectable` (la herramienta y el recorrido) frena lo mismo y deja pasar lo mismo que el puente."""
    for t in CON_PLATA + TIRADAS:
        try:
            texto_proyectable(t)
        except ValueError:
            continue
        raise AssertionError(f"el servidor deja pasar {t!r}")
    assert [texto_proyectable(t) for t in PASAN] == list(PASAN)


# ───────────────────────────── El puente con un proyector ocupado ─────────────────────────────

GUION_PROYECTOR = r"""// El puente con un proyector ocupado o que reproduce un recorrido. Uso: node <guion> <url del módulo> <escenario>.
// Cada «pestaña» es una instancia del módulo; el canal entrega en otra vuelta del bucle, y a una pestaña ocupada
// (`ocupadaHasta`) le entrega lo suyo al liberarse, en orden
const [modulo, escenario] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
const canales = new Set();
let ultimo = null;
const vistos = [];
function entregar(x, c) {
  if (x.ocupadaHasta > Date.now() || x.fila.length) {
    x.fila.push(c);
    x.libre ||= setTimeout(() => { x.libre = 0; for (const m of x.fila.splice(0)) entregar(x, m); }, Math.max(1, x.ocupadaHasta - Date.now()));
    return;
  }
  x.onmessage?.({ data: structuredClone(c) });
}
globalThis.BroadcastChannel = class {
  constructor(n) { this.n = n; this.fila = []; this.ocupadaHasta = 0; canales.add(this); ultimo = this; }
  postMessage(d) {
    // una pestaña ocupada tampoco manda (su hilo está tomado): lo suyo sale al liberarse
    const c = structuredClone(d);
    const salir = () => { vistos.push(c); for (const x of canales) if (x !== this && x.n === this.n) setTimeout(() => entregar(x, c), 1); };
    if (this.ocupadaHasta > Date.now()) setTimeout(salir, this.ocupadaHasta - Date.now()); else salir();
  }
  close() { canales.delete(this); }
};
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const hasta = async (f, ms = 10000) => { const fin = Date.now() + ms; while (!f() && Date.now() < fin) await dormir(5); return f(); };
const canalDe = {};
const abrir = async (nombre) => { const M = await import(`${modulo}?pestana=${nombre}`); canalDe[nombre] = ultimo; return M; };
const caps = { portada: 1, vivienda: 6, salud: 4 };
const orden = Object.keys(caps);
const mover = (e, a) => {
  const antes = `${e.capitulo}/${e.paso}`;
  if (a.op === 'ir') { e.capitulo = a.capitulo; e.paso = a.paso || 1; }
  else if (a.op === 'siguiente' || a.op === 'anterior') {
    let ci = orden.indexOf(e.capitulo), p = e.paso + (a.op === 'siguiente' ? 1 : -1);
    if (p > caps[orden[ci]]) { if (ci < orden.length - 1) { ci++; p = 1; } else p = caps[orden[ci]]; }
    if (p < 1) { if (ci > 0) { ci--; p = caps[orden[ci]]; } else p = 1; }
    e.capitulo = orden[ci]; e.paso = p;
  }
  e.total = caps[e.capitulo];
  if (a.explicacion) { e.explicacion = true; e.texto = a.explicacion; }
  else if (a.op === 'quitar_explicacion' || `${e.capitulo}/${e.paso}` !== antes) { e.explicacion = false; e.texto = null; }
};
const nuevo = (capitulo = 'vivienda', paso = 3) => ({ capitulo, paso, total: caps[capitulo], nombre: 'N', titulo: 'T', explicacion: false, texto: null });
const donde = (e) => `${e.capitulo}/${e.paso}`;
const op = (o, extra = {}) => ({ tipo: 'presentacion', op: o, ...extra });
const V = { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null };
const escena = (paso) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, frases: [`La escena del paso ${paso}.`], sostener_ms: 1000 });
const REC = { id: 'abcdef123456', titulo: 'La torre', cierre: null, escenas: [escena(1), escena(2), escena(3)] };
// Una vista de mentira que reproduce recorridos como la de verdad: el recorrido la lleva al paso de su escena y avisa su
// avance al puente; otra orden lo detiene («otra_orden»); sus controles se aplican; el puente lo suelta al pasarlo
function vista(M, e) {
  let sonando = null;   // {recorrido, n, fase}
  const avisar = (fase, motivo) => M.avisarRecorrido({ rid: sonando.recorrido.id, n: sonando.n, de: sonando.recorrido.escenas.length,
    fase, frase: 0, voz: 'apagada', t_ms: 0, ...(motivo ? { motivo } : {}) });
  const parar = (motivo) => { avisar('detenido', motivo); v.detenidos.push(motivo); sonando = null; };
  const v = {
    registro: [], detenidos: [], controles: [],
    avanzar() { sonando.n++; const esc = sonando.recorrido.escenas[sonando.n - 1]; e.paso = esc.paso; avisar('narrando'); M.avisarEstado(); },
    estado: () => ({ ...e }), cambio: () => {},
    recorrido: () => (sonando ? { recorrido: sonando.recorrido, n: sonando.n } : null),
    soltarRecorrido: (motivo) => { if (sonando) parar(motivo); },
    aplicar: async (l) => {
      v.registro.push(l.map((a) => (a.op === 'recorrido' ? `recorrido@${a.desde || 1}` : a.op === 'control_recorrido' ? `control:${a.accion}`
        : `${a.op}:${a.capitulo || ''}${a.paso || ''}`)));
      await dormir(3);
      const res = [];
      for (const a of l) {
        if (a.op === 'recorrido') {
          if (sonando) parar(sonando.recorrido.id === a.recorrido.id ? 'otra_orden' : 'reemplazo');
          sonando = { recorrido: a.recorrido, n: a.desde || 1 };
          mover(e, op('ir', { capitulo: 'salud', paso: a.recorrido.escenas[sonando.n - 1].paso }));
          avisar('narrando');
        } else if (a.op === 'control_recorrido') {
          if (!sonando || sonando.recorrido.id !== a.rid) { res.push({ op: a.op, ok: false, error: 'Ese recorrido ya no está sonando' }); continue; }
          v.controles.push(a.accion);
          if (a.accion === 'pausar') avisar('pausa', 'boton');
        } else {
          if (sonando) parar('otra_orden');
          mover(e, a);
        }
        res.push({ op: a.op, ok: true });
      }
      M.avisarEstado();
      return res;
    } };
  return v;
}
const r = {};
// La pestaña del chat con la vista en Vivienda 3 y un proyector que ya tomó su paso
const A = await abrir('chat');
const eA = nuevo(), vA = vista(A, eA);
A.registrarPresentacion(vA);
const P = await abrir('p1');
const eP = nuevo('portada', 1), vP = vista(P, eP);
P.registrarPresentacion({ proyector: true, ...vP });
r.sincronizado = await hasta(() => donde(eP) === 'vivienda/3' && A.proyectorVivo() && A.estadoPresentacion()?.paso === 3) && donde(eP);
await dormir(300);
vP.registro.length = 0;

if (escenario === 'ocupado_recorrido') {
  // El proyector se ocupa 6 s justo cuando el asistente manda el recorrido: no acusa y suena en la pestaña del chat
  canalDe.p1.ocupadaHasta = Date.now() + 6000;
  const t0 = Date.now();
  r.aplicado = await A.accionesPresentacion([op('recorrido', { recorrido: REC })]);
  r.ms = Date.now() - t0;
  r.aqui = vA.registro.slice(-1);
  // mientras tanto pasa a la escena 2
  vA.avanzar();
  // Ya libre, el proyector no aplica la lista que caducó; con su latido, la pestaña se lo pasa desde la escena 2
  await hasta(() => vP.registro.some((l) => l.some((x) => x.startsWith('recorrido'))), 15000);
  await dormir(600);
  r.alla = vP.registro.filter((l) => l.some((x) => x.startsWith('recorrido')));
  r.detenidos_aqui = vA.detenidos;
  r.en_curso = A.recorridoEnCurso() && `${A.recorridoEnCurso().n}/${A.recorridoEnCurso().fase}@${A.recorridoEnCurso().donde}`;
} else if (escenario === 'ocupado_ir') {
  // Una orden que no es un recorrido: se aplica aquí y el proyector, al liberarse, también (quedan en el mismo paso)
  canalDe.p1.ocupadaHasta = Date.now() + 6000;
  const t0 = Date.now();
  r.aplicado = await A.accionesPresentacion([op('ir', { capitulo: 'salud', paso: 2 })]);
  r.ms = Date.now() - t0;
  r.aqui = donde(eA);
  await hasta(() => donde(eP) === 'salud/2', 15000);
  await dormir(2500);
  r.final = [donde(eP), donde(eA)];
} else if (escenario === 'llevar_pausa') {
  // El recorrido suena en el proyector y la vista de aquí lo sigue
  r.aplicado = await A.accionesPresentacion([op('recorrido', { recorrido: REC })]);
  await hasta(() => A.recorridoEnCurso()?.donde === 'proyector' && donde(eA) === donde(eP));
  r.antes = [donde(eP), donde(eA)];
  // La persona pasa de paso en la presentación de la pestaña del chat (su control, una flecha)
  mover(eA, op('siguiente'));
  A.avisarEstado();
  await hasta(() => vP.controles.length > 0 || vP.detenidos.length > 0, 5000);
  await hasta(() => donde(eA) === donde(eP), 5000);
  await dormir(50);
  r.controles = vP.controles;
  r.detenidos = vP.detenidos;
  r.despues = [donde(eP), donde(eA)];
  r.en_curso = A.recorridoEnCurso()?.fase;
  r.ir_al_proyector = vP.registro.filter((l) => l.some((x) => x.startsWith('ir:'))).length;
}
console.log(JSON.stringify(r));
process.exit(0);
"""


@requiere_node
def test_un_recorrido_que_el_proyector_ocupado_no_acusa_suena_en_un_solo_lado(tmp_path):
    r = _node(tmp_path, GUION_PROYECTOR, PUENTE_JS.as_uri(), "ocupado_recorrido")
    assert r["sincronizado"] == "vivienda/3", r
    assert r["aplicado"] == [{"op": "recorrido", "ok": True}] and 2400 <= r["ms"] < 5000, r
    assert r["aqui"] == [["recorrido@1"]], r
    # El proyector solo lo recibe una vez: el traspaso desde la escena en curso (la lista que caducó no se aplica)
    assert r["alla"] == [["recorrido@2"]], r
    # y aquí se soltó para pasárselo, no se detuvo como si el asistente hubiera pedido otra cosa
    assert r["detenidos_aqui"] == ["proyector"], r
    assert r["en_curso"] == "2/narrando@proyector", r


@requiere_node
def test_una_orden_que_no_es_un_recorrido_la_aplica_tarde_el_proyector(tmp_path):
    r = _node(tmp_path, GUION_PROYECTOR, PUENTE_JS.as_uri(), "ocupado_ir")
    assert r["aplicado"] == [{"op": "ir", "ok": True}] and r["aqui"] == "salud/2", r
    assert r["final"] == ["salud/2", "salud/2"], r


@requiere_node
def test_mover_la_pestana_con_el_recorrido_en_el_proyector_lo_pausa(tmp_path):
    r = _node(tmp_path, GUION_PROYECTOR, PUENTE_JS.as_uri(), "llevar_pausa")
    assert r["antes"] == ["salud/1", "salud/1"], r
    assert r["controles"] == ["pausar"] and r["detenidos"] == [] and r["ir_al_proyector"] == 0, r
    assert r["despues"] == ["salud/1", "salud/1"] and r["en_curso"] == "pausa", r


# ───────────────────────────── La tarjeta del chat ─────────────────────────────

NODE_TARJETA = r"""// La tarjeta con un DOM mínimo y la API simulada. Uso: node <guion> <url del puente> <url de la tarjeta>
const [puente, tarjetaJs] = process.argv.slice(2);
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
// Un DOM de lo justo: lo que usa la tarjeta (textContent, hijos, clases, atributos, clics que suben, selectores simples)
class Nodo {
  constructor(tag, clase) {
    Object.assign(this, { tag, className: clase || '', hijos: [], padre: null, dataset: {}, style: {}, atributos: {},
      hidden: false, disabled: false, title: '', type: '', oyentes: {}, _texto: '' });
    const yo = this;
    this.classList = { toggle(c, v) { const s = new Set(yo.className.split(' ').filter(Boolean)); if (v ?? !s.has(c)) s.add(c); else s.delete(c); yo.className = [...s].join(' '); } };
  }
  get textContent() { return this._texto + this.hijos.map((h) => h.textContent).join(''); }
  set textContent(v) { this._texto = String(v); this.hijos = []; }
  get isConnected() { let n = this; while (n.padre) n = n.padre; return n === CUERPO; }
  append(...xs) { for (const x of xs) { x.remove?.(); x.padre = this; this.hijos.push(x); } }
  replaceChildren(...xs) { this.hijos = []; this._texto = ''; this.append(...xs); }
  before() {}
  remove() { if (this.padre) this.padre.hijos = this.padre.hijos.filter((h) => h !== this); this.padre = null; }
  setAttribute(k, v) { this.atributos[k] = String(v); }
  removeAttribute(k) { delete this.atributos[k]; }
  addEventListener(t, f) { (this.oyentes[t] ||= []).push(f); }
  click() { const e = { target: this }; for (let n = this; n; n = n.padre) for (const f of n.oyentes.click || []) f(e); }
  todos() { return this.hijos.flatMap((h) => [h, ...h.todos()]); }
  coincide(sel) {
    if (sel.startsWith('.')) return this.className.split(' ').includes(sel.slice(1));
    const m = /^(\w+)(?:\[data-(\w+)\])?$/.exec(sel);
    return !!m && this.tag === m[1] && (!m[2] || m[2] in this.dataset);
  }
  querySelector(sel) { return this.todos().find((n) => n.coincide(sel)) || null; }
  querySelectorAll(sel) { return this.todos().filter((n) => n.coincide(sel)); }
  closest(sel) { for (let n = this; n; n = n.padre) if (n.coincide(sel)) return n; return null; }
}
const CUERPO = new Nodo('div', 'cuerpo');
const el = (t, c, x) => { const n = new Nodo(t, c); if (x != null) n.textContent = x; return n; };
const ico = () => el('svg', 'ico');
// La API: cada llamada queda anotada y `responder` decide qué vuelve
const llamadas = [];
let responder = () => ({ status: 404, body: { detail: 'no' } });
globalThis.fetch = async (u, o = {}) => {
  const metodo = o.method || 'GET', cuerpo = o.body ? JSON.parse(o.body) : null;
  llamadas.push(`${metodo} ${u}${cuerpo ? ` ${cuerpo.accion}:${cuerpo.rid}` : ''}`);
  const { status, body } = responder(metodo, String(u), cuerpo);
  return { status, ok: status >= 200 && status < 300, headers: { get: () => 'application/json' }, json: async () => body };
};
// El reloj de la tarjeta se puede adelantar (los plazos de 15 min y 90 s, sin esperarlos)
const ahora0 = Date.now.bind(Date);
let desfase = 0;
Date.now = () => ahora0() + desfase;
const P = await import(puente), T = await import(tarjetaJs);
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const tarjeta = (id, destino) => T.tarjetaValida({ tipo: 'recorrido', id, titulo: 'La torre', destino, duracion_ms: 30000, cierre: null,
  sugerencias: [], escenas: [{ narracion: 'Una.', donde: 'Salud', hace: ['paso'] }, { narracion: 'Dos.', donde: 'Salud', hace: ['camara'] }] });
function crear(id, destino, guardados = [id]) {
  const reproducidos = [];
  const t = T.crearTarjetaRecorrido(tarjeta(id, destino), { el, ico, alSugerencia: () => {}, guardado: (rid) => guardados.includes(rid),
    reproducir: (rid, desde, nuevo) => { reproducidos.push([rid, desde, nuevo ?? null]); return guardados.includes(rid); } });
  CUERPO.append(t.el);
  return Object.assign(t, { reproducidos });
}
const ver = (t) => ({ estado: t.el.querySelector('.rec-estado').textContent,
  nota: t.el.querySelector('.rec-nota').hidden ? '' : t.el.querySelector('.rec-nota').textContent, sonando: t.sonando() });
const boton = (t, accion) => t.el.querySelectorAll('button').find((b) => b.dataset.accion === accion);
const av = (rid, n, fase, extra = {}) => P.avisarRecorrido({ rid, n, de: 2, fase, frase: 0, voz: 'apagada', t_ms: 0, ...extra });
// Una presentación abierta en esta pestaña: recibe los controles que van adonde suena
const recibidas = [];
P.registrarPresentacion({ estado: () => ({ capitulo: 'salud', paso: 1, total: 4 }),
  aplicar: async (l) => { recibidas.push(...l.map((a) => `${a.accion}:${a.rid}${a.suave ? ':suave' : ''}`)); return l.map((a) => ({ op: a.op, ok: true })); } });
const r = {};

// 1. Volver a reproducir (pestaña o proyector): el servidor lo vuelve a armar con un id nuevo y la tarjeta sigue a ese
const A = crear('aaaaaaaaaaa1', 'vista');
av('aaaaaaaaaaa1', 1, 'narrando'); av('aaaaaaaaaaa1', 2, 'fin');
r.fin = ver(A);
responder = (m, u) => (m === 'POST' && u === '/api/pantalla/recorrido/control'
  ? { status: 200, body: { id: 'bbbbbbbbbbb2', titulo: 'La torre', escena: 2, de: 2, fase: 'sin_avance', cerrado: false } } : { status: 404, body: {} });
llamadas.length = 0;
boton(A, 'reproducir').click();
await dormir(30);
r.volver = { llamadas: llamadas.slice(), reproducidos: A.reproducidos, id: A.id(), ...ver(A) };
// otro clic antes del primer avance no arma otro id
boton(A, 'reproducir').click();
await dormir(30);
r.volver_otra_vez = { llamadas: llamadas.length, deshabilitado: boton(A, 'reproducir').disabled };
av('bbbbbbbbbbb2', 1, 'narrando');
r.sigue_al_nuevo = ver(A);
av('bbbbbbbbbbb2', 2, 'fin');

// 2. Con uno más nuevo en el servidor (409), no se puede; y uno que no está en este navegador ni se pide
const B = crear('ccccccccccc3', 'vista');
av('ccccccccccc3', 2, 'fin');
responder = () => ({ status: 409, body: { detail: 'No hay un recorrido sonando con ese id' } });
boton(B, 'reproducir').click();
await dormir(30);
r.mas_nuevo = { ...ver(B), deshabilitado: boton(B, 'reproducir').disabled, reproducidos: B.reproducidos.length };
const C = crear('ddddddddddd4', 'vista', []);
av('ddddddddddd4', 2, 'fin');
llamadas.length = 0;
boton(C, 'reproducir').click();
await dormir(30);
r.no_guardado = { ...ver(C), llamadas: llamadas.length };

// 3. La barra y la pausa al escribir: la tarjeta del que suena (el del puente), aunque haya una más nueva sonando
const D = crear('eeeeeeeeeee5', 'vista');
const E = crear('fffffffffff6', 'vista');
av('fffffffffff6', 1, 'narrando');
r.del_chat_e = T.recorridoDelChat()?.id();
av('eeeeeeeeeee5', 1, 'narrando');   // D suena otra vez (volver a reproducirlo reemplazó a E)
r.del_chat_d = T.recorridoDelChat()?.id();
T.pausaPorMensaje();
await dormir(30);
r.pausa_a = recibidas.slice();
av('eeeeeeeeeee5', 1, 'fin'); av('fffffffffff6', 1, 'detenido', { motivo: 'reemplazo' });

// 4. Pantalla en off que deja de avisar sonando: detenido por falta de respuesta (sin barra ni pausa al escribir)
const off = (id, fase, hace_s, escena = 2) => ({ recorrido: { id, titulo: 'La torre', destino: 'pantalla_off', cerrado: false, escena, de: 2,
  fase, motivo: null, voz: 'apagada', hace_s }, frase: 0, avisos: [] });
let get = off('aaaabbbbcccc', 'narrando', 3);
responder = (m, u, c) => (m === 'GET' ? { status: 200, body: get } : { status: 200, body: { id: c.rid, escena: 2, de: 2, fase: 'pausa', cerrado: false } });
const F = crear('aaaabbbbcccc', 'pantalla_off');
await dormir(100);
r.off_sonando = ver(F);
get = off('aaaabbbbcccc', 'narrando', 120);
await dormir(1700);
r.off_mudo = ver(F);
r.off_barra = T.recorridoDelChat()?.id() ?? null;

// 5. Una pausa larga no la da por muerta: al vencer el tope pregunta más despacio, y un control la vuelve a seguir
// enseguida
get = off('ddddeeeeffff', 'pausa', 5000);
const G = crear('ddddeeeeffff', 'pantalla_off');
await dormir(100);
r.pausa_larga = { ...ver(G), pausado: G.pausado() };
desfase += 16 * 60 * 1000;
await dormir(1700);
const antes = llamadas.filter((x) => x.startsWith('GET')).length;
await dormir(1700);
r.sin_preguntar = { ...ver(G), gets: llamadas.filter((x) => x.startsWith('GET')).length - antes };
get = off('ddddeeeeffff', 'narrando', 1);
boton(G, 'continuar')?.click();
await dormir(200);
r.tras_continuar = { ...ver(G), control: llamadas.filter((x) => x.startsWith('POST')).slice(-1)[0] };
// y sigue preguntando aunque nadie la toque: un «continuar» del asistente, pasado el tope, también se ve
get = off('ddddeeeeffff', 'pausa', 1);
await dormir(1700);
desfase += 16 * 60 * 1000;
await dormir(1700);
get = off('ddddeeeeffff', 'narrando', 1);
await dormir(10500);
r.continuo_el_asistente = ver(G);

// 5b. La pantalla se cerró con el recorrido en pausa: el servidor dice que ya no pregunta por su estado (`conectada`)
// y, pasado SIN_NOTICIAS_S, la tarjeta lo da por detenido (en pausa no hay avances que lo digan)
get = { ...off('444455556666', 'pausa', 30), conectada: false };
const G2 = crear('444455556666', 'pantalla_off');
await dormir(100);
r.cerrada_al_rato = ver(G2);
desfase += 61 * 1000;
await dormir(1700);
r.cerrada = ver(G2);

// 6. Una pantalla en off que nunca empezó (sin avance en 90 s): no lo va a narrar
get = off('111122223333', 'sin_avance', null);
const H = crear('111122223333', 'pantalla_off');
await dormir(100);
r.sin_empezar = ver(H);
// un control (la pausa que sale con cada mensaje) vuelve a preguntar, pero no reinicia ese plazo
boton(H, 'pausar')?.click();
await dormir(100);
desfase += 91 * 1000;
await dormir(1700);
r.nunca_empezo = ver(H);
console.log(JSON.stringify(r));
process.exit(0);
"""


@pytest.fixture(scope="module")
def tarjeta(tmp_path_factory):
    """Una sola corrida de NODE_TARJETA (unos 25 s) para las dos pruebas que siguen."""
    return _node(tmp_path_factory.mktemp("tarjeta"), NODE_TARJETA, PUENTE_JS.as_uri(), TARJETA_JS.as_uri())


@requiere_node
def test_la_tarjeta_vuelve_a_reproducir_por_el_servidor_y_sigue_al_que_suena(tarjeta):
    r = tarjeta
    assert r["fin"] == {"estado": "Terminó", "nota": "", "sonando": False}, r
    # Volver a reproducir: primero el servidor (id nuevo), después el guardado con ese id; la tarjeta sigue al nuevo
    assert r["volver"]["llamadas"] == ["POST /api/pantalla/recorrido/control reproducir:aaaaaaaaaaa1"], r
    assert r["volver"]["reproducidos"] == [["aaaaaaaaaaa1", 1, "bbbbbbbbbbb2"]] and r["volver"]["id"] == "bbbbbbbbbbb2", r
    # sin pintar «preparando» antes de que suene: lo pinta el primer avance (si la vista no llega a reproducirlo, la
    # tarjeta no queda «preparando» con la barra puesta)
    assert r["volver"]["estado"] == "Volviendo a empezar…" and r["volver"]["sonando"] is False, r
    assert r["volver_otra_vez"] == {"llamadas": 1, "deshabilitado": True}, r
    assert r["sigue_al_nuevo"]["estado"] == "Escena 1 de 2 · Narrando", r
    assert r["mas_nuevo"] == {"estado": "Terminó", "nota": "Ya no se puede volver a reproducir: hay un recorrido más nuevo.",
                              "sonando": False, "deshabilitado": True, "reproducidos": 0}, r
    assert r["no_guardado"]["llamadas"] == 0, r
    assert r["no_guardado"]["nota"] == "No se pudo volver a reproducir: el recorrido ya no está en este navegador.", r
    # La barra y la pausa al escribir van a la del que suena, no a la más nueva
    assert r["del_chat_e"] == "fffffffffff6" and r["del_chat_d"] == "eeeeeeeeeee5", r
    assert r["pausa_a"] == ["pausar:eeeeeeeeeee5:suave"], r


@requiere_node
def test_la_tarjeta_de_la_pantalla_en_off_no_queda_sonando_para_siempre(tarjeta):
    r = tarjeta
    assert r["off_sonando"]["estado"] == "Escena 2 de 2 · Narrando" and r["off_sonando"]["sonando"] is True, r
    assert r["off_mudo"] == {"estado": "Detenido en la escena 2", "nota": "Se detuvo: la pantalla en off dejó de responder.",
                             "sonando": False}, r
    assert r["off_barra"] is None, r
    assert r["pausa_larga"] == {"estado": "Escena 2 de 2 · En pausa", "nota": "", "sonando": True, "pausado": True}, r
    assert r["sin_preguntar"]["estado"] == "Escena 2 de 2 · En pausa" and r["sin_preguntar"]["gets"] == 0, r
    assert r["tras_continuar"]["estado"] == "Escena 2 de 2 · Narrando", r
    assert r["tras_continuar"]["control"] == "POST /api/pantalla/recorrido/control continuar:ddddeeeeffff", r
    assert r["continuo_el_asistente"]["estado"] == "Escena 2 de 2 · Narrando", r
    assert r["cerrada_al_rato"]["estado"] == "Escena 2 de 2 · En pausa" and r["cerrada_al_rato"]["sonando"] is True, r
    assert r["cerrada"] == {"estado": "Detenido en la escena 2", "nota": "Se detuvo: la pantalla en off dejó de responder.",
                            "sonando": False}, r
    assert r["sin_empezar"]["estado"] == "Escena 2 de 2 · Preparando", r
    assert r["nunca_empezo"]["estado"] == "Detenido en la escena 2" and r["nunca_empezo"]["sonando"] is False, r
