"""El asistente en la misma ventana de la presentación: la pantalla en off (/presentacion?off=1) y la ventana del
proyector (/presentacion?pantalla=1) ya no lo esconden; se abre al lado, con todo lo que tiene en el panel.

* El puente (admin/web/js/agente-presentacion.js), con Node: `pedirPantalla()` dispara `pantalla:pedir` en window y
  nunca lanza; `registrarVozLocal(fn)` registra la voz de la pantalla en off de esta ventana y `alternarVozRecorrido()`
  la usa solo si no hay una presentación registrada aquí ni un proyector que mande; en la propia ventana del proyector
  las acciones, los controles y la voz van a su vista (allí `elegido()` es null).
* La vista (vistas/presentacion.js), por texto (necesita la presentación cargada en un iframe): en off escucha
  `pantalla:pedir` y adelanta su sondeo, registra su voz; el botón flotante se atenúa con el ratón quieto; un Escape que
  ya usó el asistente no devuelve la pantalla completa; el proyector va a pantalla completa con la ventana entera. Y las
  dos correcciones de la automática: el plan llega al reproductor con `auto` (sin el «¿Preguntas?» de 12 s; se prueba
  con el reproductor de verdad) y la vista que se va no le avisa al servidor el «detenido» del plan automático.
* El CSS (css/presentacion.css): ya no esconde #agente en esas ventanas; abierto en escritorio, la presentación le deja
  su ancho también en el proyector (sin menú: --side-w 0); el botón y su atenuación.
* En Chromium (si hay Playwright y el sitio construido en site/), el panel de verdad (index.html, app.js y el asistente)
  contra una API simulada (en los puertos PUERTOS): en la pantalla en off el botón va en su barra, abierto le deja su
  ancho y un plan que pide el chat de esa ventana mientras la presentación carga suena ahí (y en el celular el panel se
  pliega); en el proyector la presentación que termina de cargar no le quita el foco al chat, el teclado sigue siendo
  de la presentación después de cerrar el chat, el botón no tapa el control de la presentación, se atenúa y vuelve, y
  un plan del chat de esa ventana suena ahí y la pestaña del panel lo ve por el canal.
* Las correcciones de la verificación («ventana #1» a «#6»), cada una con su prueba: el teclado del proyector, el
  latido de la pantalla en off mientras carga, el foco al cargar, el panel plegado en el celular, el botón encima del
  control de la presentación y la voz de la pantalla en off con un proyector abierto.
"""
import json
import re
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from test_agente_presentacion import requiere_navegador, requiere_node

ADMIN = Path(__file__).resolve().parents[1]
RAIZ = ADMIN.parent
WEB = ADMIN / "web"
JS = WEB / "js"
PUENTE_JS = JS / "agente-presentacion.js"
VISTA_JS = JS / "vistas" / "presentacion.js"
REPRODUCTOR_JS = JS / "reproductor.js"
CSS = WEB / "css" / "presentacion.css"
SITIO = RAIZ / "site"
PUERTOS = range(18960, 18970)   # el banco de las pruebas en Chromium


def _node(tmp_path: Path, guion: str, *args: str, timeout: int = 90) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=timeout,
                       cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ───────────────────────────── El puente ─────────────────────────────

NODE_PUENTE = r"""// El puente con la pantalla en off y el proyector en la ventana del chat. Uso: node <guion> <agente-presentacion.js>
const [modulo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
let canal = null;
globalThis.BroadcastChannel = class { constructor() { canal = this; } postMessage() {} close() {} };
const P = await import(modulo);
const r = {};

// pedirPantalla: sin window (Node sin dispatchEvent) no lanza; con ella, dispara `pantalla:pedir` (sin detalle)
r.sin_ventana = (() => { try { return P.pedirPantalla() === undefined; } catch { return false; } })();
const eventos = [];
globalThis.dispatchEvent = (e) => { eventos.push([e.type, e instanceof Event, e.detail ?? null]); return true; };
P.pedirPantalla(); P.pedirPantalla();
r.eventos = eventos;
globalThis.dispatchEvent = () => { throw new Error('x'); };
r.si_falla = (() => { try { P.pedirPantalla(); return true; } catch { return false; } })();
delete globalThis.dispatchEvent;

// La voz: nada registrado → null; la de la pantalla en off de esta ventana (registrarVozLocal)
const voz = [];
voz.push(P.alternarVozRecorrido());
let estadoLocal = 'apagada', toquesLocal = 0;
const local = () => { toquesLocal++; estadoLocal = estadoLocal === 'activa' ? 'apagada' : 'activa'; return estadoLocal; };
r.registro_invalido = typeof P.registrarVozLocal('no es una función');
voz.push(P.alternarVozRecorrido());   // lo inválido no registra nada
const quitarLocal = P.registrarVozLocal(local);
voz.push(P.alternarVozRecorrido(), P.alternarVozRecorrido());
// con una presentación registrada aquí (la pestaña del chat o el proyector), manda la suya
let toquesVista = 0;
const control = { aplicar: async (l) => l.map((a) => ({ op: a.op, ok: true })), estado: () => ({ capitulo: 'salud', paso: 1, total: 4 }),
  alternarVoz: () => { toquesVista++; return 'sin_activar'; } };
const quitarVista = P.registrarPresentacion(control);
voz.push(P.alternarVozRecorrido());
// una vista registrada que no maneja voz: null (no la de la pantalla en off)
const sinVoz = { aplicar: async () => [], estado: () => null };
const quitarSinVoz = P.registrarPresentacion(sinVoz);
voz.push(P.alternarVozRecorrido());
quitarSinVoz();
quitarVista();   // (ya no es la registrada: no cambia nada)
P.registrarPresentacion({ aplicar: async () => [], estado: () => null })();   // se va: queda sin presentación
voz.push(P.alternarVozRecorrido());   // otra vez la local
// con un proyector que manda (otra ventana), la pantalla en off de aquí sigue narrando su plan: su voz se alterna igual
// (antes daba null y la tarjeta decía que se encendía «allá», que era esta misma ventana)
canal.onmessage({ data: { canal: 'yondo-presentacion', v: 1, tipo: 'proyector', id: 'abcdefgh12345678', desde: Date.now(), listo: true,
  estado: { capitulo: 'salud', paso: 1, total: 4 } } });
await new Promise((ok) => setTimeout(ok, 20));
const antes = toquesLocal;
voz.push(P.proyectorVivo(), P.alternarVozRecorrido(), toquesLocal === antes + 1);
// pero una presentación registrada aquí (la pestaña del chat) con ese proyector: su voz es la de allá, null
const vistaAntes = toquesVista;
const quitarConProyector = P.registrarPresentacion(control);
voz.push(P.alternarVozRecorrido(), toquesVista === vistaAntes);
quitarConProyector();
canal.onmessage({ data: { canal: 'yondo-presentacion', v: 1, tipo: 'adios', id: 'abcdefgh12345678' } });
await new Promise((ok) => setTimeout(ok, 20));
// lo que no es un estado y lo que lanza: null
const quitarRara = P.registrarVozLocal(() => 'encendidísima');
voz.push(P.alternarVozRecorrido());
const quitarMala = P.registrarVozLocal(() => { throw new Error('x'); });
voz.push(P.alternarVozRecorrido());
// quitar una que ya no es la registrada no quita la vigente
quitarRara();
voz.push(P.alternarVozRecorrido());
quitarMala();
voz.push(P.alternarVozRecorrido());
quitarLocal();
r.voz = voz;
r.toques = { local: toquesLocal, vista: toquesVista };

// La ventana del proyector: su propio chat aplica en su vista (no hay otro proyector que elegir), también los controles
// del plan y su voz
const aplicadas = [];
const proyector = { proyector: true, aplicar: async (l) => { aplicadas.push(...l.map((a) => a.op)); return l.map((a) => ({ op: a.op, ok: true })); },
  estado: () => ({ capitulo: 'salud', paso: 1, total: 4 }), alternarVoz: () => 'activa' };
const quitarProyector = P.registrarPresentacion(proyector);
r.en_el_proyector = {
  vivo: P.proyectorVivo(),
  ir: await P.accionesPresentacion([{ tipo: 'presentacion', op: 'ir', capitulo: 'salud', paso: 2 }]),
  control: await P.controlRecorrido('abcdef123456', 'pausar'),
  voz: P.alternarVozRecorrido(),
};
P.avisarRecorrido({ rid: 'abcdef123456', n: 1, de: 3, fase: 'narrando', voz: 'activa' });
r.en_el_proyector.en_curso = P.recorridoEnCurso()?.donde ?? null;
r.en_el_proyector.aplicadas = aplicadas;
quitarProyector();
console.log(JSON.stringify(r));
process.exit(0);
"""


@requiere_node
def test_el_puente_pide_la_pantalla_y_maneja_la_voz_de_la_ventana(tmp_path):
    r = _node(tmp_path, NODE_PUENTE, PUENTE_JS.as_uri())
    # pedirPantalla: nunca lanza; dispara `pantalla:pedir` cada vez, sin datos
    assert r["sin_ventana"] is True and r["si_falla"] is True
    assert r["eventos"] == [["pantalla:pedir", True, None], ["pantalla:pedir", True, None]]
    assert r["registro_invalido"] == "function"
    # sin nada: null; la local alterna; manda la vista registrada (y una sin voz da null, no la local); sin ella, otra
    # vez la local; con un proyector que manda en otra ventana, la local igual (ventana #6: el plan de la pantalla en off
    # lo narra esta ventana), pero la de una vista registrada aquí no (suena allá); lo que no es un estado o lanza, null
    # (la nueva reemplaza a la anterior); quitar una vieja no quita la vigente; quitada, null
    assert r["voz"] == [None, None, "activa", "apagada", "sin_activar", None, "activa", True, "apagada", True, None, True,
                        None, None, None, None], r["voz"]
    assert r["toques"] == {"local": 4, "vista": 1}, r["toques"]
    # en la ventana del proyector, todo va a su vista
    p = r["en_el_proyector"]
    assert p["vivo"] is False and p["ir"] == [{"op": "ir", "ok": True}] and p["control"] == {"op": "control_recorrido", "ok": True}
    assert p["voz"] == "activa" and p["en_curso"] == "aqui" and p["aplicadas"] == ["ir", "control_recorrido"]


def test_el_evento_de_pedir_es_el_mismo_en_el_puente_y_en_la_vista():
    puente = PUENTE_JS.read_text(encoding="utf-8")
    vista = VISTA_JS.read_text(encoding="utf-8")
    assert "const EVENTO_PEDIR = 'pantalla:pedir';" in puente
    assert "const PEDIR_PANTALLA = 'pantalla:pedir';" in vista
    assert "globalThis.dispatchEvent?.(new CustomEvent(EVENTO_PEDIR))" in puente


# ───────────────────────────── La vista, por texto ─────────────────────────────

def test_la_vista_en_off_pide_ya_registra_su_voz_y_no_se_pisa_con_el_asistente():
    vista = VISTA_JS.read_text(encoding="utf-8")
    assert "registrarPresentacion, registrarVozLocal } from '../agente-presentacion.js';" in vista
    # su voz, para el interruptor de la tarjeta del chat abierto al lado (solo en off: las demás se registran enteras)
    assert "if (off) limpiezas.push(registrarVozLocal(alternarVoz));" in vista
    # `pantalla:pedir`: una vuelta del sondeo ya (adelantarSondeo: una a la vez), solo en off y con su limpieza
    pedir = vista[vista.index("const alPedir = "):]
    pedir = pedir[:pedir.index("}\n") + 2]
    assert "adelantarSondeo?.()" in pedir
    bloque = vista[vista.index("const alPedir = ") - 200:vista.index("const alPedir = ") + 400]
    assert "if (off) {" in bloque and "window.addEventListener(PEDIR_PANTALLA, alPedir);" in bloque
    assert "limpiezas.push(() => window.removeEventListener(PEDIR_PANTALLA, alPedir));" in bloque
    adelantar = vista[vista.index("adelantarSondeo = () => {"):]
    assert "if (enVuelta) pronto = true;" in adelantar[:300]
    # el avance del reproductor de esta vista sigue yendo al puente (la tarjeta lo pinta en el acto)
    assert re.search(r"avisar: \(pr\) => \{\n\s+avisarRecorrido\(pr\);", vista)
    # un Escape que ya usó el asistente (cerrarse, cancelar la grabación) no devuelve la pantalla completa (ni la de la
    # ventana ni, en la pestaña, la del navegador: `salirDeLlena`)
    assert "if (e.key === 'Escape' && !e.defaultPrevented && 'presLlena' in raiz.dataset) salirDeLlena();" in vista
    # los enlaces que abren esas ventanas dicen que ahí también está el asistente
    for i in ('id="pres-otra"', 'id="pres-off"'):
        enlace = vista[vista.index(i):]
        enlace = enlace[:enlace.index(">")]
        assert re.search(r'title="[^"]*también se abre el asistente[^"]*"', enlace), enlace
    assert "innerHTML" not in vista


def test_el_boton_flotante_se_atenua_con_la_ventana_quieta():
    vista = VISTA_JS.read_text(encoding="utf-8")
    assert "const QUIETO_MS = 3000;" in vista
    # (en las tres ventanas: en la pestaña, el css solo los atenúa a pantalla completa)
    q = vista[vista.index("  {\n    let ultima = 0"):]
    q = q[:q.index("\n  }\n") + 4]
    assert "raiz.dataset.presQuieto = '';" in q and "delete raiz.dataset.presQuieto;" in q
    assert "const tipos = [['pointermove', alRaton], ['pointerdown', () => actividad()], ['keydown', () => actividad()], ['wheel', () => actividad()]];" in q
    # el ratón cuenta si se movió de verdad (el navegador repite el último movimiento con el ratón quieto cuando cambia
    # lo que hay debajo: los rótulos de la maqueta se mueven con la cámara)
    assert "if (e.screenX === ratonX && e.screenY === ratonY) return;" in q
    # también lo que pasa sobre la presentación: su ventana si es del mismo origen (cada vez que carga)
    assert "iframe.addEventListener('load', alCargar);" in q and "ventanaIframe = iframe.contentWindow;" in q
    # (desde su primer mensaje: su `listo` llega antes que el `load` del iframe; una vez por documento)
    assert "if (!doc || doc === docIframe) return;" in q
    assert "if (e.source !== iframe.contentWindow || e.origin !== d.origen) return;\n    enganchar();" in vista
    # y se limpia todo
    limpieza = q[q.index("limpiezas.push(() => {"):]
    for x in ("escuchar(window, false);", "escuchar(ventanaIframe, false);", "clearTimeout(tQuieto);",
              "delete raiz.dataset.presQuieto;", "enganchar = () => {};"):
        assert x in limpieza, x
    # el gesto y las teclas de la presentación (en el proyector el iframe ocupa la ventana) despiertan el botón
    assert "if (m.tipo === 'gesto') { voz.gesto(); actividad(); return; }" in vista
    assert "if (m.tipo === 'tecla') {\n      actividad();" in vista
    # el proyector a pantalla completa con la ventana entera: el asistente sigue a mano (y la pestaña también, con la
    # página entera: ya ninguna pide la pantalla completa solo para el marco)
    assert "else document.documentElement.requestFullscreen?.().catch(() => {});" in vista
    assert "raiz.requestFullscreen({ navigationUI: 'hide' })" in vista
    assert "marco).requestFullscreen" not in vista and "marco.requestFullscreen" not in vista


def _bloque(texto: str, desde: str, hasta: str) -> str:
    i = texto.index(desde)
    return texto[i:texto.index(hasta, i)]


def test_el_teclado_del_proyector_es_de_la_presentacion():
    """ventana #1: al cerrarse, el asistente deja el foco en su botón; las flechas y AvPág no le llegaban a la
    presentación y el espacio volvía a abrir el chat delante de la sala. ventana #3: el foco del primer `listo` no se lo
    quita al chat donde la persona ya escribe (en Chromium, más abajo, con la presentación de verdad)."""
    vista = VISTA_JS.read_text(encoding="utf-8")
    t = _bloque(vista, "if (proyector) {\n    const TECLA_FUERA", "\n  }\n")
    assert ("const TECLA_FUERA = { ArrowRight: 'siguiente', PageDown: 'siguiente', ' ': 'siguiente', ArrowLeft: 'anterior',\n"
            "      PageUp: 'anterior', Backspace: 'anterior' };") in t
    # solo con la presentación lista, sin modificadores ni lo que ya usó otro; lo que se escribe no se toca, ni el
    # espacio sobre los otros botones de la ventana (sí sobre el del asistente: ese foco lo dejó el chat al cerrarse)
    assert "if (!op || !lista || e.defaultPrevented || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;" in t
    assert "t?.closest?.('#agente-panel, input, textarea, select, [contenteditable], dialog')" in t
    assert "if (e.key === ' ' && t?.closest?.('button:not(#agente-boton), a')) return;" in t
    # la mueve como sus botones (con un plan sonando, de paso del plan) y el foco vuelve a ella; y se limpia
    assert t.index("e.preventDefault();") < t.index("iframe.focus({ preventScroll: true });") < t.index("mover(op);")
    assert "document.addEventListener('keydown', alTeclaFuera);" in t
    assert "limpiezas.push(() => document.removeEventListener('keydown', alTeclaFuera));" in t
    # (después de `mover` y de `lista`)
    assert vista.index("const mover = (op) =>") < vista.index("const TECLA_FUERA") and vista.index("let lista = false;") < vista.index("const TECLA_FUERA")
    # ventana #3: al cargar, el foco va a la presentación salvo que la persona ya esté en el chat
    assert "if (proyector && !document.activeElement?.closest?.('#agente-panel')) iframe.focus({ preventScroll: true });" in vista
    # (la otra: el toque de la persona en «Pantalla completa» de la pestaña, que deja el teclado en la presentación)
    assert vista.count("iframe.focus(") == 3
    assert "ponerCompleta();\n      if (lista) iframe.focus({ preventScroll: true });" in vista
    # y el asistente que se cierra en el proyector (Escape, su X) le devuelve el foco a la presentación, no a su botón
    # (con el foco a la vista, además, el botón no se atenuaba)
    agente = (JS / "agente.js").read_text(encoding="utf-8")
    cerrar = _bloque(agente, "function cerrar({ foco = false, plegado = false } = {}) {", "\n  }\n")
    assert "const pres = 'proyector' in document.documentElement.dataset ? document.getElementById('pres-iframe') : null;" in cerrar
    assert "(pres?.isConnected ? pres : boton).focus({ preventScroll: true });" in cerrar
    assert 'id="pres-iframe"' in vista


def test_la_pantalla_en_off_cuenta_como_abierta_mientras_carga():
    """ventana #2: la vista en off solo le preguntaba al servidor después del `listo` de la presentación y el chat de esa
    ventana se usa antes: un plan pedido en ese hueco salía para la pestaña (`destino: vista`) y aquí no lo narraba
    nadie. Ahora avisa desde que se monta, con un latido, hasta que empieza el sondeo (en Chromium, más abajo)."""
    vista = VISTA_JS.read_text(encoding="utf-8")
    # declarado antes de la primera salida temprana (sin sitio: `sinPresentacion`, que lo para)
    assert vista.index("let latidoPrevio = 0;") < vista.index("const d = await direccion();")
    sin = _bloque(vista, "function sinPresentacion(titulo, detalle) {", "\n  }\n")
    assert "clearInterval(latidoPrevio);" in sin
    latido = _bloque(vista, "if (off) {\n    const latir = ", "\n  }\n")
    assert "api.get('/api/pantalla?v=-1&latido=1').catch(() => {});" in latido
    assert "latir();\n    latidoPrevio = setInterval(latir, LATIDO_MS);" in latido
    assert "limpiezas.push(() => clearInterval(latidoPrevio));" in latido
    # empieza en cuanto el iframe existe (antes del `listo`) y lo releva el sondeo: después de la orden `vista` (que
    # puede tardar) y justo antes de la primera vuelta
    assert vista.index("montar(marco, html`<iframe id=\"pres-iframe\"") < vista.index("const latir = ")
    seguir = _bloque(vista, "async function seguirAlServidor() {", "\n  }\n")
    assert seguir.index("await orden({ orden: 'vista', controles: false });") < seguir.index("clearInterval(latidoPrevio);")
    assert seguir.rstrip().endswith("clearInterval(latidoPrevio);   // desde aquí avisa el sondeo (y sus latidos en las esperas largas)\n    vuelta();")
    # los latidos de las esperas largas también se marcan: su respuesta no es lo que la vista aplicó
    assert "api.get(`/api/pantalla?v=${versionVista}&latido=1`)" in vista


def test_en_el_celular_la_pantalla_en_off_se_ve_cuando_su_plan_empieza():
    """ventana #4: un plan con destino pantalla_off no pasa por `aplicarPresentacion` (que pliega el panel en el
    celular), así que en la pantalla en off el plan sonaba detrás del panel, que la tapaba entera."""
    agente = (JS / "agente.js").read_text(encoding="utf-8")
    t = _bloque(agente, "function tarjetaRecorrido(a) {", "\n  }\n")
    assert "if (v.destino === 'pantalla_off' && 'presOff' in document.documentElement.dataset) plegar();" in t
    assert t.index("enAsistente().append(t.el);") < t.index("plegar();")
    # plegar() solo cierra en el celular (sin cortar la respuesta inmediata que suena: el plan la espera); y
    # tarjetaRecorrido solo corre con acciones en vivo (no al repintar el historial)
    assert "function plegar() {\n    if (abierto && esMovil()) cerrar({ plegado: true });" in agente
    assert agente.count("tarjetaRecorrido(") == 2 and "else if (a.tipo === 'recorrido') tarjetaRecorrido(a);" in agente


NODE_AUTO = r"""// El plan automático que la vista en off le da al reproductor. Uso: node <guion> <puente> <reproductor> <vista (texto)>
import { readFileSync } from 'node:fs';
const [puente, reproductor, vistaRuta] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
globalThis.BroadcastChannel = class { postMessage() {} close() {} };
const P = await import(puente);
const { crearReproductor, lecturaMs } = await import(reproductor);
// la línea de la vista que arma el plan para el reproductor (`recorridoDeLaPantalla`), tal cual
const vista = readFileSync(vistaRuta, 'utf8');
const linea = vista.match(/const \{ edad_s: _edad[^}]*\} = x;/)[0];
const comoLaVista = new Function('x', `${linea} return r;`);
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const escena = (paso) => ({ capitulo: 'salud', paso, panel: true, visual: { ...V }, resaltar: null, mover: null, animar: false,
  frases: [`Salud, paso ${paso}.`], sostener_ms: 600 });
const plan = { id: 'abcdef123456', titulo: 'Salud', escenas: [escena(1), escena(2)], cierre: null };
const base = { v: 7, capitulo: 'salud', paso: 2, explicacion: null, panel: true, indice: false, fichas: false, completa: false, orden_completa: 0 };
const out = { linea };
for (const auto of [true, false]) {
  const e = P.estadoDePantalla({ ...base, recorrido: { ...plan, edad_s: 1, ...(auto ? { auto: true } : {}) } });
  const r = comoLaVista(e.recorrido);
  const reloj = relojFalso(), ordenes = [], avances = [];
  const rep = crearReproductor({ reloj, orden: async (o) => { ordenes.push(o.orden + (o.puntos === null ? ':preguntas' : '')); return { ok: true }; },
    avisar: (p) => avances.push([reloj.ahora(), p.fase]) });
  rep.iniciar(r);
  await reloj.avanzar(60000);
  const cierre = avances.find((x) => x[1] === 'cierre')?.[0], fin = avances.find((x) => x[1] === 'fin')?.[0];
  out[auto ? 'automatico' : 'sin_auto'] = { auto: r.auto ?? null, edad: 'edad_s' in r, cierre_a_fin_ms: fin - cierre,
    preguntas: ordenes.includes('cierre:preguntas') };
}
console.log(JSON.stringify(out));
process.exit(0);
"""


@requiere_node
def test_el_plan_automatico_llega_al_reproductor_con_auto_y_no_espera_preguntas(tmp_path):
    """automatica #1: la vista le quitaba `auto` al plan antes de dárselo al reproductor, y el plan automático esperaba
    el «¿Preguntas?» de 12 s al final de cada capítulo. Con la línea de la vista tal cual y el reproductor de verdad."""
    r = _node(tmp_path, NODE_AUTO, PUENTE_JS.as_uri(), REPRODUCTOR_JS.as_uri(), str(VISTA_JS))
    assert r["linea"] == "const { edad_s: _edad, ...r } = x;"
    a, s = r["automatico"], r["sin_auto"]
    assert a["auto"] is True and a["edad"] is False and a["preguntas"] is False and a["cierre_a_fin_ms"] < 100, a
    # el del asistente sin cierre (la misma forma, sin `auto`) sí espera las preguntas
    assert s["auto"] is None and s["preguntas"] is True and s["cierre_a_fin_ms"] >= 10000, s
    vista = VISTA_JS.read_text(encoding="utf-8")
    rec = vista[vista.index("async function recorridoDeLaPantalla(e)"):vista.index("const enSuEscena")]
    i = rec.index("const { edad_s: _edad, ...r } = x;")
    assert rec.index("recorrido: r, desde }", i) > i and "auto: _auto" not in vista
    assert "rep.iniciar(p.recorrido, {" in vista


def test_la_vista_que_se_va_no_apaga_la_automatica():
    """automatica #2 (la parte de la vista): al desmontarse, el «detenido» del plan automático no va al servidor (lo
    cerraba y apagaba la automática para todos, y cortaba otra pantalla en off que la narrara)."""
    vista = VISTA_JS.read_text(encoding="utf-8")
    assert "let seFue = false;" in vista
    avisar = vista[vista.index("avisar: (pr) => {"):]
    avisar = avisar[:avisar.index("\n    },")]
    assert "if (!(seFue && pr.rid === ridAuto)) enviarAvance(pr);" in avisar
    # el puente y la barra lo siguen sabiendo
    assert avisar.index("avisarRecorrido(pr);") < avisar.index("enviarAvance(pr)")
    # la limpieza la pone antes de detener
    assert "limpiezas.push(() => { seFue = true; rep.detener('otra_orden'); voz.callar(); });" in vista
    # (el 409 de un avance que el servidor ya no tiene por vigente sigue deteniendo lo que suena)
    assert "rep.activo() && rep.recorrido()?.id === x.rid" in vista


# ───────────────────────────── El CSS ─────────────────────────────

def test_el_css_deja_ver_el_asistente_y_le_da_su_ancho():
    css = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    reglas = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    # ya no se esconde en el proyector ni en la pantalla en off
    for sel, cuerpo in reglas:
        if "display: none" in cuerpo or "display:none" in cuerpo:
            assert not re.search(r"html\[data-(proyector|pres-off)\][^,]*#agente(\s*[,{]|\s*$)", sel.strip() + " "), sel
    assert "html[data-proyector] .lateral, html[data-proyector] .barra-movil { display: none; }" in css
    # abierto en escritorio: la presentación le deja su ancho en las tres (sin :not(.proyector))
    assert "body:has(#vista .presentacion) { --pres-agente-w: min(420px, max(300px, 100vw - var(--side-w) - 408px)); }" in css
    assert "body:has(#agente-panel:not([hidden])) #vista .presentacion { padding-right: calc(var(--pres-agente-w) + 36px); }" in css
    assert "body:has(#vista .presentacion) .agente-panel { width: var(--pres-agente-w); }" in css
    # sin menú, el ancho no lo descuenta
    assert "html[data-proyector], html[data-pres-llena] { --side-w: 0px; }" in css
    # el botón en el proyector: abajo a la izquierda, con los botones de la ventana corridos a su derecha
    assert re.search(r"html\[data-proyector\] #agente #agente-boton \{ top: auto; right: auto; left: 14px; bottom: 14px;", css)
    assert "html[data-proyector] body:has(#agente-boton:not([hidden])) .pres-flotantes { left: 64px; }" in css
    # se atenúa quieto (no con el ratón encima ni con el foco del teclado), en el proyector y en off a pantalla completa
    assert re.search(r"html\[data-proyector\]\[data-pres-quieto\] #agente #agente-boton:not\(:hover\):not\(:focus-visible\),\s*"
                     r"html\[data-pres-off\]\[data-pres-llena\]\[data-pres-quieto\] #agente #agente-boton:not\(:hover\):not\(:focus-visible\) "
                     r"\{ opacity: \.18; \}", css)
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{\s*html\[data-proyector\] #agente #agente-boton", css)
    # el proyector en pantalla completa es la ventana entera: sus botones de abajo no se ven, como antes
    assert "html[data-proyector]:fullscreen .pres-flotantes { display: none; }" in css
    # ventana #5: en el celular (de pie y acostado, las condiciones de web/propuesta.html) el botón y los de la ventana
    # van encima del control de la presentación (52 px desde 14), no sobre «anterior»
    assert re.search(r"@media \(max-width: 640px\), \(max-width: 1080px\) and \(orientation: landscape\) and \(max-height: 560px\) \{\s*"
                     r"html\[data-proyector\] #agente #agente-boton, html\[data-proyector\] \.pres-flotantes \{\s*"
                     r"bottom: calc\(76px \+ env\(safe-area-inset-bottom, 0px\)\); \}", css)
    propuesta = (RAIZ / "web" / "propuesta.html").read_text(encoding="utf-8")
    assert "@media (max-width: 640px) {" in propuesta
    assert "@media (max-width: 1080px) and (orientation: landscape) and (max-height: 560px) {" in propuesta
    assert re.search(r"\.control \{ position: fixed;[^}]*bottom: max\(14px, env\(safe-area-inset-bottom, 0px\)\);[^}]*height: 52px;", propuesta)
    # y hasta 1200 px, solo los íconos de «Pantalla completa» y «Voz» (con el botón del asistente delante, su texto
    # llegaba al control centrado: en 1024 × 768 tapaba «anterior»); «Pantalla completa» lleva su title
    assert re.search(r"@media \(max-width: 1200px\) \{\s*html\[data-proyector\] body:has\(#agente-boton:not\(\[hidden\]\)\) "
                     r"\.pres-flotantes \.btn span \{", css)
    assert 'id="pres-completa" title="Pantalla completa"' in VISTA_JS.read_text(encoding="utf-8")


# ───────────────────────────── En Chromium ─────────────────────────────

V = {"enfoque": None, "camara": "paso", "rumbo": None, "elevacion": None, "zoom": None, "mirar": None, "girar": False,
     "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": [], "ocultar": [], "aislar": None, "sin": []}


def _plan(rid: str) -> tuple[dict, dict]:
    escenas = [{"capitulo": "salud", "paso": p, "panel": True, "visual": dict(V), "resaltar": None, "mover": None,
                "animar": False, "frases": [f"Salud, paso {p}: una frase corta para la prueba."], "sostener_ms": 1300}
               for p in (1, 2, 3)]
    plan = {"id": rid, "titulo": "La torre del hospital", "escenas": escenas, "cierre": None}
    tarjeta = {"tipo": "recorrido", "id": rid, "titulo": plan["titulo"], "destino": "vista", "duracion_ms": 15000,
               "cierre": None, "sugerencias": [], "escenas": [{"narracion": e["frases"][0], "donde": f"Salud · paso {e['paso']}",
                                                              "hace": ["paso"]} for e in escenas]}
    return plan, tarjeta


class _Banco:
    """La API simulada: la sesión, el asistente (un chat que responde con un plan: a la pantalla en off si hay una
    abierta, si no a la vista de la ventana del chat), la pantalla en off (su estado y el avance) y la tarjeta."""

    def __init__(self):
        self.lock = threading.RLock()
        self.visto = 0.0
        self.p = {"v": 1, "capitulo": "portada", "paso": 1, "explicacion": None, "panel": True, "indice": False,
                  "fichas": False, "completa": False, "orden_completa": 0, **V, "tema": None, "mover": None, "animar": False}
        self.recorrido = None
        self.progreso = None
        self.llamadas = []
        self.n = 0

    def pantalla(self) -> dict:
        out = {**self.p, "recorrido": None, "control_recorrido": None, "progreso": None, "auto": None}
        r = self.recorrido
        if r and not r["cerrado"]:
            out["recorrido"] = {k: r[k] for k in ("id", "titulo", "escenas", "cierre")} | {"edad_s": int(time.time() - r["creado"])}
            pr = self.progreso
            if pr and pr["rid"] == r["id"]:
                out["progreso"] = {k: pr[k] for k in ("rid", "n", "de", "fase")} | {"hace_s": int(time.time() - pr["en"])}
        return out

    def chat(self) -> list:
        self.n += 1
        rid = f"{self.n:012x}"
        plan, tarjeta = _plan(rid)
        abierta = time.time() - self.visto < 10
        self.recorrido = {**plan, "cerrado": False, "creado": time.time()}
        self.progreso = None
        self.p["v"] += 1
        acciones = [{**tarjeta, "destino": "pantalla_off"}] if abierta else [
            {"tipo": "presentacion", "op": "recorrido", "recorrido": plan}, tarjeta]
        self.llamadas.append(["chat", time.time(), "pantalla_off" if abierta else "vista"])
        return ([{"tipo": "inicio", "conversacion": 7, "titulo": "La torre"},
                 {"tipo": "herramienta", "id": "t1", "nombre": "presentacion", "etiqueta": "Armando el plan", "estado": "inicio"},
                 {"tipo": "herramienta", "id": "t1", "nombre": "presentacion", "etiqueta": "Armando el plan", "estado": "ok",
                  "resumen": "Plan «La torre del hospital» · 3 pasos"}]
                + [{"tipo": "accion", "accion": a} for a in acciones]
                + [{"tipo": "texto", "texto": "Le muestro la torre."}, {"tipo": "fin", "motivo": "fin"}])


def _servidor(banco: _Banco):
    pagina = (WEB / "index.html").read_text(encoding="utf-8").replace('"/static/', '"/panel/static/').replace(
        '<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="panel-base" content="/panel">')
    estado_agente = {"disponible": True, "motivo": None, "configurado": True, "proveedor": "mnemo", "es_admin": True,
                     "escritura": True, "limite": {"usados": 3, "maximo": 200}, "mnemo": {"activo": True, "origen": None},
                     "dictado": False, "sugerencias": []}

    class M(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def translate_path(self, path):
            p = path.split("?")[0]
            if p == "/propuesta":
                return str(SITIO / "propuesta.html")
            if p.startswith("/panel/static/"):
                return str(WEB / p[len("/panel/static/"):])
            return str(SITIO / p.lstrip("/"))

        def _json(self, code, obj=None, tipo="application/json"):
            b = b"" if obj is None else (obj if isinstance(obj, bytes) else json.dumps(obj).encode())
            self.send_response(code)
            if obj is not None:
                self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            p = self.path.split("?")[0]
            with banco.lock:
                if p == "/panel/api/pantalla":
                    banco.visto = time.time()
                    v = int(self.path.split("v=")[1].split("&")[0])
                    banco.llamadas.append(["get", time.time(), v != banco.p["v"]])
                    return self._json(204) if v == banco.p["v"] else self._json(200, banco.pantalla())
                if p == "/panel/api/pantalla/recorrido":
                    r, pr = banco.recorrido, banco.progreso
                    x = None if not r else {"id": r["id"], "titulo": r["titulo"], "destino": "pantalla_off", "cerrado": r["cerrado"],
                                            "escena": pr["n"] if pr else 1, "de": len(r["escenas"]),
                                            "fase": pr["fase"] if pr else "sin_avance", "motivo": None, "voz": None,
                                            "hace_s": int(time.time() - pr["en"]) if pr else None}
                    return self._json(200, {"recorrido": x, "frase": 0, "avisos": [], "auto": None,
                                            "conectada": time.time() - banco.visto < 10,
                                            "vigente": x and {"id": x["id"], "cerrado": x["cerrado"]}})
                if p == "/panel/api/yo":
                    return self._json(200, {"csrf": "x", "usuario": "admin", "uid": 1, "rol": "admin", "permisos": ["*"],
                                            "excepto": [], "nombre": "Ana Prueba"})
                if p == "/panel/api/insignias":
                    return self._json(200, {})
                if p == "/panel/api/agente/estado":
                    return self._json(200, estado_agente)
                if p.startswith("/panel/api/"):
                    return self._json(404, {"detail": "no"})
                if p.startswith("/panel") and not p.startswith("/panel/static/"):
                    return self._json(200, pagina.encode(), "text/html; charset=utf-8")
            return super().do_GET()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            x = json.loads(self.rfile.read(n) or b"{}") if n else {}
            p = self.path.split("?")[0]
            with banco.lock:
                if p == "/panel/api/agente/mensajes":
                    b = "".join(json.dumps(e) + "\n" for e in banco.chat()).encode()
                    return self._json(200, b, "application/x-ndjson")
                if p == "/panel/api/pantalla/progreso":
                    r = banco.recorrido
                    banco.llamadas.append(["progreso", time.time(), x.get("fase"), x.get("motivo")])
                    if not r or r["id"] != x.get("rid") or r["cerrado"]:
                        return self._json(409, {"detail": "Ese recorrido ya no es el vigente"})
                    banco.progreso = {**x, "en": time.time()}
                    if x.get("fase") in ("fin", "detenido", "error"):
                        r["cerrado"] = True
                        banco.p["v"] += 1
                    return self._json(204)
                if p == "/panel/api/pantalla/recorrido/control":
                    return self._json(200, {"id": x.get("rid"), "cerrado": False})
            return self._json(404, {"detail": "no"})

    srv = None
    for puerto in [*PUERTOS, 0]:   # los de esta prueba y, si están todos ocupados, uno libre cualquiera
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", puerto), M)
            break
        except OSError:
            continue
    puerto = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{puerto}"


GUION_NAVEGADOR = r"""// El asistente en la pantalla en off y en el proyector. Uso: node <guion> <base> <ancho> <alto> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [B, ancho, alto, D] = process.argv.slice(2);
const W = Number(ancho), H = Number(alto);
const espera = { timeout: 120000 };
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const caja = (p, s) => p.evaluate((s) => { const e = document.querySelector(s); if (!e || e.hidden) return null;
  const r = e.getBoundingClientRect(); return r.width ? [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] : null; }, s);
const dentro = (a, b) => !!a && !!b && a[0] >= b[0] - 1 && a[1] >= b[1] - 1 && a[2] <= b[2] + 1 && a[3] <= b[3] + 1;
const cargando = (p) => p.evaluate(() => /Cargando/.test(document.querySelector('#pres-off-paso, #pres-paso')?.textContent || ''));
const cargada = (p) => p.waitForFunction(() => { const s = document.querySelector('#pres-off-paso, #pres-paso'); return s && !/Cargando/.test(s.textContent); }, null, espera);
// (las capturas son para mirarlas a mano: con la maqueta en la CPU y otro Chromium a la vez pueden no salir a tiempo)
const capturar = (p, nombre) => p.screenshot({ path: `${D}/${nombre}-${W}.png`, timeout: 20000 }).catch(() => {});
// La presentación tarda en llegar (una red lenta, un televisor) y el chat ya se usa antes: la que se pida mientras esto
// esté puesto llega cuando la prueba la suelta (o a los 30 s)
const esLenta = (u) => u.pathname === '/propuesta';
function retener() {
  let soltar = () => {};
  const puerta = new Promise((ok) => { soltar = ok; });
  return { soltar, lento: async (r) => { await Promise.race([puerta, dormir(30000)]); await r.continue().catch(() => {}); } };
}
async function abrir(ctx, ruta, errores, { esperar = true } = {}) {
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errores.push(e.message));
  // (sin esperar el `load`: con la presentación retenida, el de la página puede esperar al del iframe)
  await p.goto(`${B}${ruta}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('#agente-boton:not([hidden])', espera);
  await p.evaluate(async () => {
    const P = await import('/panel/static/js/agente-presentacion.js');   // el mismo módulo que usa la app
    window.__P = P; window.__av = [];
    P.escucharRecorrido((x, d) => window.__av.push(`${x.n}/${x.fase}@${d}`));
  });
  if (esperar) await cargada(p);
  return p;
}
async function preguntar(p) {
  if (await p.locator('#agente-panel').isHidden()) await p.click('#agente-boton');
  await p.fill('#agente-texto', 'Muéstrame la torre del hospital');
  await p.press('#agente-texto', 'Enter');
  await p.waitForSelector('.agente-recorrido', { ...espera, state: 'attached' });
  await p.waitForFunction(() => window.__av.some((x) => x.includes('/narrando@aqui')), null, espera);
}
// ¿Qué botones de la ventana (el del asistente y los flotantes) caen sobre el control propio de la presentación?
const sobreElControl = (p) => p.evaluate(() => {
  const f = document.getElementById('pres-iframe'), r = f.getBoundingClientRect();
  const c = f.contentDocument?.querySelector('.control')?.getBoundingClientRect();
  if (!c?.width) return null;
  return [...document.querySelectorAll('#agente-boton, .pres-flotantes .btn')].filter((b) => {
    const q = b.getBoundingClientRect();
    return !b.hidden && q.width && q.left < c.right + r.left && c.left + r.left < q.right && q.top < c.bottom + r.top && c.top + r.top < q.bottom;
  }).map((b) => b.id || b.className);
});
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, hasTouch: W < 600, isMobile: W < 600 });
  await ctx.route((u) => !u.href.startsWith(B), (r) => r.abort());
  const errores = [];
  const out = {};
  // La pantalla en off, con la presentación lenta: el chat de esa ventana se usa mientras carga
  const r1 = retener();
  await ctx.route(esLenta, r1.lento);
  const O = await abrir(ctx, '/panel/presentacion?off=1', errores, { esperar: false });
  out.off = { boton: await caja(O, '#agente-boton'), barra: await caja(O, W >= 901 ? '.pres-barra:not([hidden])' : '.barra-movil'),
    cerrado: await O.evaluate(() => document.querySelector('#agente-panel').hidden) };
  out.off.botonEnLaBarra = dentro(out.off.boton, out.off.barra);
  await O.click('#agente-boton');
  await O.waitForSelector('#agente-panel:not([hidden])');
  await O.waitForTimeout(800);
  const panel = await caja(O, '#agente-panel'), iframe = await caja(O, '#pres-iframe');
  out.off.libre = W >= 901 ? iframe[2] <= panel[0] : true;
  // se pregunta antes de que la presentación cargue: la pantalla ya cuenta como abierta (ventana #2)
  await O.fill('#agente-texto', 'Muéstrame la torre del hospital');
  out.off.cargandoAlPreguntar = await cargando(O);
  await O.press('#agente-texto', 'Enter');
  await O.waitForSelector('.agente-recorrido', { ...espera, state: 'attached' });
  out.off.destino = await O.evaluate(() => document.querySelector('.agente-recorrido')?.dataset.destino);
  // en el celular el panel tapa la pantalla: se pliega cuando llega el plan (ventana #4); en escritorio sigue al lado
  out.off.panelConPlan = await O.evaluate(() => !document.querySelector('#agente-panel').hidden);
  r1.soltar();
  await cargada(O);
  await ctx.unroute(esLenta, r1.lento);
  await O.waitForFunction(() => window.__av.some((x) => x.includes('/narrando@aqui')), null, espera);
  out.off.avances = await O.evaluate(() => window.__av.slice(0, 4));
  out.off.voz = await O.evaluate(() => window.__P.alternarVozRecorrido());
  await capturar(O, 'off');
  await O.close();
  await dormir(10500);   // la pantalla en off ya no cuenta como abierta
  // El proyector, con la pestaña del panel abierta también
  const T = await abrir(ctx, '/panel/presentacion', errores);
  const r2 = retener();
  await ctx.route(esLenta, r2.lento);
  const Pj = await abrir(ctx, '/panel/presentacion?pantalla=1', errores, { esperar: false });
  out.proyector = {};
  // La persona abre el chat y escribe mientras la presentación carga: el foco del primer `listo` no se lo quita (ventana
  // #3). Letra por letra hasta que cargó, y unas cuantas más
  await Pj.click('#agente-boton');
  await Pj.waitForSelector('#agente-panel:not([hidden])');
  let escrito = '', despues = -1;
  for (const letra of 'hola, quiero ver el indice de salud y la ficha de la torre '.repeat(5)) {
    if (escrito.length === 6) r2.soltar();   // la presentación llega con la frase empezada
    if (despues < 0 && !(await cargando(Pj))) despues = 0;
    if (despues >= 0 && ++despues > 14) break;
    await Pj.keyboard.type(letra);
    escrito += letra;
    await Pj.waitForTimeout(110);
  }
  await cargada(Pj);
  await ctx.unroute(esLenta, r2.lento);
  await Pj.waitForTimeout(800);
  const paso = () => Pj.evaluate(() => window.__P.estadoPresentacion()?.paso ?? null);
  const foco = () => Pj.evaluate(() => document.activeElement?.id || document.activeElement?.tagName);
  out.proyector.escribiendo = { cargoAMitad: despues > 0, entero: await Pj.evaluate(() => document.querySelector('#agente-texto').value) === escrito,
    foco: await foco(), capitulo: await Pj.evaluate(() => window.__P.estadoPresentacion()?.capitulo ?? null), paso: await paso() };
  // El teclado sigue siendo de la presentación (ventana #1): Escape cierra el chat y el foco vuelve a ella, no al botón
  // (las flechas no le llegaban); con el foco en el botón igual, sus teclas la mueven y el foco vuelve a ella, y el
  // espacio no reabre el chat delante de la sala; Enter sí lo abre
  await Pj.keyboard.press('Escape');
  await Pj.waitForSelector('#agente-panel', { state: 'hidden' });
  const donde = () => Pj.evaluate(() => { const e = window.__P.estadoPresentacion(); return e ? `${e.capitulo}/${e.paso}` : null; });
  const otroPaso = (d0) => Pj.waitForFunction((d0) => { const e = window.__P.estadoPresentacion();
    return e && `${e.capitulo}/${e.paso}` !== d0; }, d0, { timeout: 15000 }).catch(() => {});
  const teclado = out.proyector.teclado = { focoAlCerrar: await foco(), antes: await donde() };
  await Pj.keyboard.press('ArrowRight');
  await otroPaso(teclado.antes);
  teclado.trasFlecha = [await donde(), await foco()];
  await Pj.focus('#agente-boton');
  await Pj.keyboard.press('ArrowLeft');
  await otroPaso(teclado.trasFlecha[0]);
  teclado.desdeElBoton = [await donde(), await foco()];
  await Pj.focus('#agente-boton');
  await Pj.keyboard.press(' ');
  await otroPaso(teclado.desdeElBoton[0]);
  teclado.trasEspacio = [await donde(), await Pj.evaluate(() => document.querySelector('#agente-panel').hidden)];
  await Pj.focus('#agente-boton');
  await Pj.keyboard.press('Enter');
  teclado.enterAbre = await Pj.waitForSelector('#agente-panel:not([hidden])', { timeout: 5000 }).then(() => true, () => false);
  await Pj.click('#agente-cerrar');
  await Pj.waitForSelector('#agente-panel', { state: 'hidden' });
  teclado.focoTrasLaX = await foco();
  // el botón y los de la ventana no caen sobre el control de la presentación (ventana #5: en el celular, «anterior»)
  out.proyector.sobreElControl = await sobreElControl(Pj);
  const tMov = Date.now();
  await Pj.mouse.move(W / 2, H / 2, { steps: 3 });
  // (con la maqueta en la CPU el movimiento puede atenderse después del reloj que la daba por quieta)
  await Pj.waitForFunction(() => !('presQuieto' in document.documentElement.dataset), null, { timeout: 3000 }).catch(() => {});
  const o = () => Pj.evaluate(() => [getComputedStyle(document.querySelector('#agente-boton')).opacity, 'presQuieto' in document.documentElement.dataset]);
  Object.assign(out.proyector, { boton: await caja(Pj, '#agente-boton'), despierto: await o() });
  // quieto: se atenúa a los 3 s (con la maqueta 3D armándose en la CPU, los relojes de la página pueden llegar tarde)
  await Pj.waitForFunction(() => 'presQuieto' in document.documentElement.dataset, null, { timeout: 15000 });
  out.proyector.quietoTrasMs = Date.now() - tMov;
  // (la transición avanza con los cuadros, que con la maqueta en la CPU llegan espaciados)
  await Pj.waitForFunction(() => parseFloat(getComputedStyle(document.querySelector('#agente-boton')).opacity) < 0.25, null, { timeout: 10000 }).catch(() => {});
  out.proyector.quieto = await o();
  await Pj.mouse.move(W / 2 + 30, H / 2 + 30, { steps: 3 });
  await Pj.waitForFunction(() => parseFloat(getComputedStyle(document.querySelector('#agente-boton')).opacity) > 0.9, null, { timeout: 10000 }).catch(() => {});
  out.proyector.otraVez = await o();
  await preguntar(Pj);
  await Pj.waitForTimeout(1500);
  out.proyector.destino = await Pj.evaluate(() => document.querySelector('.agente-recorrido')?.dataset.destino);
  out.proyector.avances = await Pj.evaluate(() => window.__av.slice(0, 4));
  out.proyector.enElPanel = await T.evaluate(() => window.__av.slice(0, 4));
  await capturar(Pj, 'proyector');
  out.errores = errores;
  console.log(JSON.stringify(out));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
@pytest.mark.skipif(not (SITIO / "propuesta.html").is_file(), reason="Sin el sitio construido en site/ (scripts/build_site.py)")
@pytest.mark.parametrize("ancho,alto", [(1600, 900), (390, 844)])
def test_el_asistente_en_la_pantalla_en_off_y_en_el_proyector_en_chromium(tmp_path, ancho, alto):
    banco = _Banco()
    srv, base = _servidor(banco)
    try:
        (tmp_path / "ventana.cjs").write_text(GUION_NAVEGADOR, encoding="utf-8")
        p = subprocess.run(["node", str(tmp_path / "ventana.cjs"), base, str(ancho), str(alto), str(tmp_path)],
                           capture_output=True, text=True, timeout=500, cwd=ADMIN)
    finally:
        srv.shutdown()
    assert p.returncode == 0, p.stderr[-3000:]
    r = json.loads(p.stdout.strip().splitlines()[-1])
    o = r["off"]
    # cerrado por omisión, el botón en su barra (en el celular, la de arriba); abierto, la presentación le deja su ancho
    assert o["cerrado"] is True and o["botonEnLaBarra"] is True and o["libre"] is True, o
    # el plan del chat de esa ventana va a la pantalla en off y suena ahí mismo, aunque se pidiera mientras la
    # presentación cargaba (ventana #2: ya contaba como abierta); la voz, la de ahí
    assert o["cargandoAlPreguntar"] is True, o
    assert o["destino"] == "pantalla_off" and any(a.endswith("/narrando@aqui") for a in o["avances"]), o
    assert o["voz"] in ("activa", "apagada", "sin_activar", "sin_voces"), o
    # en el celular el panel se pliega cuando llega el plan (ventana #4); en escritorio sigue al lado
    assert o["panelConPlan"] is (ancho >= 901), o
    pj = r["proyector"]
    # ventana #3: la presentación cargó mientras la persona escribía en el chat y no le quitó el foco ni una letra
    e = pj["escribiendo"]
    assert e == {"cargoAMitad": True, "entero": True, "foco": "agente-texto", "capitulo": "portada", "paso": 1}, e
    # ventana #1: cerrado el chat (con Escape o con su X), el foco vuelve a la presentación y la flecha la mueve; con el
    # foco en el botón, sus teclas la mueven igual y el foco vuelve a ella, y el espacio no reabre el chat; Enter sí
    t = pj["teclado"]
    assert t["focoAlCerrar"] == "pres-iframe" and t["focoTrasLaX"] == "pres-iframe" and t["antes"] == "portada/1", t
    assert t["trasFlecha"] == ["portada/2", "pres-iframe"] and t["desdeElBoton"] == ["portada/1", "pres-iframe"], t
    assert t["trasEspacio"] == ["portada/2", True] and t["enterAbre"] is True, t
    # ventana #5: ni el botón ni los de la ventana caen sobre el control de la presentación
    assert pj["sobreElControl"] == [], pj
    # el botón: a la vista al mover el ratón, atenuado quieto (3 s), de vuelta al moverlo sobre la presentación
    assert pj["despierto"][1] is False and pj["otraVez"][1] is False and float(pj["otraVez"][0]) > 0.9, pj
    assert pj["quieto"][1] is True and float(pj["quieto"][0]) < 0.25 and pj["quietoTrasMs"] >= 2900, pj
    # el plan del chat de esa ventana suena ahí (la vista de esa ventana) y la pestaña del panel lo ve por el canal
    assert pj["destino"] == "vista" and any(a.endswith("/narrando@aqui") for a in pj["avances"]), pj
    assert any(a.endswith("@proyector") for a in pj["enElPanel"]), pj
    assert r["errores"] == []
