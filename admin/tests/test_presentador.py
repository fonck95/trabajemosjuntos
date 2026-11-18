"""El presentador (web/js/presentador/): la caricatura en 3D que explica lo que narra el asistente, con Node.

* El personaje se arma sin DOM ni WebGL (three en Node, desde web/vendor): mide lo que dice, con los pies en el piso, y
  trae los huesos y las manos que mueve el animador.
* El animador: cada gesto entra y sale (o se sostiene hasta otro), ninguno deja un ángulo que no sea un número, hablar
  abre la boca y callar la cierra, señalar a la izquierda o a la derecha usa el brazo de ese lado, y entrar y salir
  lo muestran y lo ocultan.
* La carga perezosa (perezoso.js): un «quitar» o un «mostrar» no cargan el módulo; el primer aviso que lo necesita sí,
  y lo que llegó mientras cargaba se le pasa en orden; con el presentador apagado no se carga; si no se pudo crear, lo
  que llega se ignora.
* El mando de la presentación (mando.js) le avisa cada cosa: la escena (con o sin resaltado, con o sin obra), la frase
  (con la voz o sin ella), `habla`, la pausa, el cierre, la píldora de «prepara», la explicación suelta, quitarla y la
  preferencia del panel (`vista {presentador}`). Una escena que cambia de paso no lo despide en el camino, y un
  presentador que falla no rompe nada de la presentación.
"""
import re
import subprocess
from pathlib import Path

from test_agente_presentacion import requiere_node
from test_plan_guiado import MANDO_JS, NODE_MANDO, _node

ADMIN = Path(__file__).resolve().parents[1]
WEB = ADMIN.parent / "web"
PRESENTADOR = WEB / "js" / "presentador"
VENDOR_THREE = WEB / "vendor" / "three-0.160.0"
VISTA_JS = ADMIN / "web" / "js" / "vistas" / "presentacion.js"

CARGADOR = r"""// three en Node: los mismos nombres del importmap de la página, resueltos a web/vendor
import { pathToFileURL } from 'node:url';
const VENDOR = process.env.VENDOR_THREE;
export async function resolve(esp, ctx, next) {
  if (esp === 'three') return { url: pathToFileURL(`${VENDOR}/build/three.module.js`).href, shortCircuit: true };
  if (esp.startsWith('three/addons/')) return { url: pathToFileURL(`${VENDOR}/examples/jsm/${esp.slice(13)}`).href, shortCircuit: true };
  return next(esp, ctx);
}
"""

NODE_PERSONAJE = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
const THREE = await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { crearAnimador, NOMBRES_GESTOS, ARTICULACIONES } = await import(pathToFileURL(`${dir}/animador.js`).href);
const azar = () => { let k = 11; return () => ((k = (k * 16807) % 2147483647) / 2147483647); };
const r = {};
const p = crearPersonaje({ documento: null });
r.medidas = p.medidas;
r.huesos = ARTICULACIONES.filter((j) => !p.huesos[j]);
r.manos = ['I', 'D'].map((l) => p.manos[l].dedos.length);
r.ojos = p.cara.ojos.length;
r.cejas = p.cara.cejas.length;
// la boca: lo que se le pide en cada cuadro
let abrir = 0, abrirMax = 0;
const poner = p.cara.boca.poner;
p.cara.boca.poner = (o) => { abrir = o.abrir; abrirMax = Math.max(abrirMax, o.abrir); poner(o); };
const camara = new THREE.PerspectiveCamera(17, 0.95, 0.1, 50);
camara.position.set(0, 1.2, 8);
const a = crearAnimador(p, { azar: azar() });
a.camara = camara;
const correr = (s) => { for (let i = 0; i < Math.round(s * 60); i++) a.actualizar(1 / 60); };
const numeros = () => ARTICULACIONES.every((j) => p.huesos[j].quaternion.toArray().every(Number.isFinite))
  && Object.values(p.manos).every((m) => m.dedos.flat().every((d) => Number.isFinite(d.rotation.z)));
correr(1);
r.reposo = { gesto: a.estado().gesto, numeros: numeros(), abrir };
// cada gesto: entra (a la mitad está), no deja NaN y sale (o se sostiene hasta detenerlo)
r.gestos = {};
for (const g of NOMBRES_GESTOS) {
  const dur = a.gesto(g, { n: 2, punto: new THREE.Vector3(-3, 2.2, 1) });
  correr(Math.min(dur, 6) / 2);
  const mitad = a.estado().gesto;
  correr(Math.min(dur, 6) / 2 + 0.6);
  const sigue = a.estado().gesto;
  a.detenerGesto();
  correr(1);
  r.gestos[g] = { dur: Number.isFinite(dur) ? Math.round(dur * 10) / 10 : 'sostenido', mitad, sigue, despues: a.estado().gesto, numeros: numeros() };
}
// hablar abre la boca; callar la cierra
abrirMax = 0;
a.hablar(1.5);
correr(1);
r.habla = { abrirMax: Math.round(abrirMax * 100) / 100, hablando: a.estado().hablando };
correr(1);
const tras = a.estado().hablando;
correr(0.5);
r.calla = { hablando: tras, abrir: Math.round(abrir * 1000) / 1000 };
// señalar: el brazo del lado del punto (el derecho del personaje está en −x)
const giro = (j) => 2 * Math.acos(Math.min(1, Math.abs(p.huesos[j].quaternion.w)));
const lado = (x) => {
  a.gesto('senalar', { punto: new THREE.Vector3(x, 2.4, 1) });
  correr(1.2);
  const out = { I: Math.round(giro('hombroI') * 100) / 100, D: Math.round(giro('hombroD') * 100) / 100 };
  a.detenerGesto();
  correr(1);
  return out;
};
r.senalar = { izquierda: lado(-3), derecha: lado(3) };
// caminar y volver
a.caminarA(1);
correr(3);
r.camina = Math.round(a.estado().x * 100) / 100;
// salir y entrar
a.salir();
correr(1.2);
r.salio = p.grupo.visible;
a.entrar();
correr(1.2);
r.entro = { visible: p.grupo.visible, y: Math.round(p.cuerpo.position.y * 100) / 100 };
r.numeros = numeros();
p.liberar();
console.log(JSON.stringify(r));
"""


@requiere_node
def test_el_personaje_y_el_animador_con_node(tmp_path):
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_PERSONAJE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=120, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    m = r["medidas"]
    assert 2.1 < m["alto"] < 2.4 and abs(m["piso"]) < 0.03 and 1.2 < m["hombro"] < 1.45, m
    assert r["huesos"] == [] and r["manos"] == [4, 4] and r["ojos"] == 2 and r["cejas"] == 2
    assert r["reposo"] == {"gesto": None, "numeros": True, "abrir": 0}, r["reposo"]
    sostenidos = {"escuchar"}
    for g, x in r["gestos"].items():
        assert x["mitad"] == g and x["numeros"], (g, x)
        assert x["despues"] is None, (g, x)
        if g in sostenidos:
            assert x["dur"] == "sostenido" and x["sigue"] == g, (g, x)
        else:
            assert isinstance(x["dur"], (int, float)) and 1 <= x["dur"] <= 6 and x["sigue"] is None, (g, x)
    assert set(r["gestos"]) >= {"saludar", "senalar", "presentar", "explicar", "contar", "pensar", "celebrar", "invitar",
                                "asentir", "pulgar", "escuchar", "despedirse"}
    assert r["habla"]["hablando"] and r["habla"]["abrirMax"] > 0.3, r["habla"]
    assert r["calla"] == {"hablando": False, "abrir": 0.0} or (not r["calla"]["hablando"] and r["calla"]["abrir"] < 0.01), r["calla"]
    # a la izquierda de la pantalla (−x) señala con el brazo derecho del personaje, y al revés
    assert r["senalar"]["izquierda"]["D"] > 1 > r["senalar"]["izquierda"]["I"], r["senalar"]
    assert r["senalar"]["derecha"]["I"] > 1 > r["senalar"]["derecha"]["D"], r["senalar"]
    assert r["camina"] == 1.0
    assert r["salio"] is False and r["entro"] == {"visible": True, "y": 0.0} and r["numeros"], r


NODE_PEREZOSO = r"""import { pathToFileURL } from 'node:url';
const [dir] = process.argv.slice(2);
const { presentadorPerezoso } = await import(pathToFileURL(`${dir}/perezoso.js`).href);
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const r = {};
// uno que carga: lleva la cuenta de las cargas y de lo que le llega
const armar = (crear = true) => {
  const x = { cargas: 0, llamadas: [] };
  // (sin `then`: si no, la promesa de la carga lo tomaría por otra promesa)
  const real = new Proxy({}, { get: (_, k) => (k === 'then' ? undefined : (...a) => x.llamadas.push([k, ...a])) });
  x.p = presentadorPerezoso(async () => { x.cargas++; await dormir(5); return crear ? real : null; });
  return x;
};
{
  const x = armar();
  x.p.quitar(); x.p.mostrar(true);
  await dormir(20);
  r.no_despiertan = { cargas: x.cargas, estado: x.p.estado() };
  x.p.narrar({ n: 1 }); x.p.frase(0, { voz: true }); x.p.habla(false);
  r.cargando = x.p.estado();
  await dormir(20);
  x.p.cierre(null);
  r.en_orden = { cargas: x.cargas, estado: x.p.estado(), llamadas: x.llamadas };
}
{
  const x = armar();
  x.p.mostrar(false);
  x.p.narrar({ n: 1 });
  await dormir(20);
  r.apagado = { cargas: x.cargas, estado: x.p.estado() };
}
{
  const x = armar(false);
  x.p.narrar({ n: 1 });
  await dormir(20);
  x.p.frase(0);
  await dormir(20);
  r.sin_webgl = { cargas: x.cargas, estado: x.p.estado() };
}
console.log(JSON.stringify(r));
"""


@requiere_node
def test_la_carga_perezosa(tmp_path):
    r = _node(tmp_path, NODE_PEREZOSO, str(PRESENTADOR))
    assert r["no_despiertan"] == {"cargas": 0, "estado": "sin_cargar"}
    assert r["cargando"] == "cargando"
    assert r["en_orden"] == {"cargas": 1, "estado": "listo", "llamadas": [
        ["narrar", {"n": 1}], ["frase", 0, {"voz": True}], ["habla", False], ["cierre", None]]}, r["en_orden"]
    assert r["apagado"] == {"cargas": 0, "estado": "sin_cargar"}
    assert r["sin_webgl"] == {"cargas": 1, "estado": "fallo"}


def _guion_mando(escenarios: str) -> str:
    base = NODE_MANDO.split("const r = {};")[0]
    viejo = "    restaurarEncuadre: () => { log.push(['restaurar']); } });"
    assert base.count(viejo) == 1
    return base.replace(viejo, "    restaurarEncuadre: () => { log.push(['restaurar']); }, presentador: globalThis.PRESENTADOR });") + escenarios


NODE_MANDO_PRESENTADOR = r"""
const r = {};
const llamadas = [];
globalThis.PRESENTADOR = new Proxy({}, { get: (_, k) => (...a) => { llamadas.push([k, ...a]); } });
const tomar = () => llamadas.splice(0).map((l) => JSON.parse(JSON.stringify(l)));
{
  const a = armar();
  await a.pedir('escena', { id: 1, ...E({ voz: true }) });
  r.escena1 = tomar();
  await a.pedir('narracion', { id: 2, frase: 1 });
  r.frase = tomar();
  await a.pedir('narracion', { id: 3, habla: true });
  await a.pedir('narracion', { id: 4, habla: false });
  r.habla = tomar();
  r.habla_mala = (await a.pedir('narracion', { id: 5, habla: 'sí' }))?.tipo;
  await a.pedir('narracion', { id: 6, pausa: true });
  await a.pedir('narracion', { id: 7, pausa: false });
  r.pausa = tomar();
  // otra escena en otro paso, con resaltado y la cámara a una obra: el subtítulo que se quita en el camino no lo despide
  await a.pedir('escena', { id: 8, ...E({ paso: 2, n: 2, resaltar: { tipo: 'cifra', n: 1 }, visual: { ...structuredClone(V0), mirar: 'torre' } }) });
  r.escena2 = tomar();
  await a.pedir('cierre', { id: 9, puntos: ['Uno', 'Dos'], rid: 'abcdef123456' });
  await a.pedir('cierre', { id: 10, puntos: null, rid: 'abcdef123456' });
  r.cierre = tomar();
  await a.pedir('quitar_explicacion', { id: 11 });
  r.quitar = tomar();
  await a.pedir('explicar', { id: 12, explicacion: 'La torre tiene cuatro pisos.' });
  r.explicar = tomar();
  await a.pedir('quitar_explicacion', { id: 13 });
  tomar();
  await a.pedir('narracion', { id: 14, preparando: true });
  await a.pedir('narracion', { id: 15, preparando: false });
  r.preparando = tomar();
  await a.pedir('vista', { id: 16, presentador: false });
  r.vista = tomar();
  r.vista_mala = (await a.pedir('vista', { id: 17, presentador: 1 }))?.tipo;
}
// un presentador que falla en todo: la presentación responde igual
{
  globalThis.PRESENTADOR = new Proxy({}, { get: () => () => { throw new Error('roto'); } });
  const a = armar();
  const e = await a.pedir('escena', { id: 1, ...E() });
  const f = await a.pedir('narracion', { id: 2, frase: 0 });
  const q = await a.pedir('quitar_explicacion', { id: 3 });
  r.roto = [e?.tipo, f?.tipo, q?.tipo, a.sub.classList.contains('visible')];
}
console.log(JSON.stringify(r));
"""


@requiere_node
def test_el_mando_le_avisa_al_presentador(tmp_path):
    r = _node(tmp_path, _guion_mando(NODE_MANDO_PRESENTADOR), MANDO_JS.as_uri())
    assert r["escena1"] == [["narrar", {"n": 1, "de": 3, "senal": False, "obra": False}]], r["escena1"]
    assert r["frase"] == [["frase", 1, {"voz": True, "texto": "Frase dos."}]], r["frase"]
    assert r["habla"] == [["habla", True], ["habla", False]]
    assert r["habla_mala"] == "error"
    assert r["pausa"] == [["pausa", True], ["pausa", False]]
    assert r["escena2"] == [["narrar", {"n": 2, "de": 3, "senal": True, "obra": True}]], r["escena2"]
    assert r["cierre"] == [["cierre", ["Uno", "Dos"], {"voz": False}], ["cierre", None, {"voz": False}]], r["cierre"]
    assert r["quitar"] == [["quitar"]]
    assert r["explicar"] == [["explicar", "La torre tiene cuatro pisos."]]
    assert r["preparando"] == [["preparando", True], ["preparando", False]], r["preparando"]
    assert r["vista"] == [["mostrar", False]] and r["vista_mala"] == "error"
    assert r["roto"] == ["estado", "estado", "estado", False], r["roto"]


def test_la_vista_del_panel_le_da_la_boca_y_el_boton():
    vista = VISTA_JS.read_text(encoding="utf-8")
    # la voz del recorrido avisa cuándo empieza y termina de decir algo (la boca del presentador)
    assert "orden({ orden: 'narracion', habla: v }, { plazo: 3000 })" in vista
    assert "orden, voz: vozConBoca," in vista
    # el botón «Presentador» en las tres ventanas (la pestaña, la pantalla en off y el proyector) y su preferencia
    assert vista.count("pres-presentador\" aria-pressed=\"true\"") == 3
    assert "const CLAVE_PRESENTADOR = 'yj_presentador';" in vista
    assert "if (m.tipo === 'listo' && !conPresentador) orden({ orden: 'vista', presentador: false });" in vista
    mando = MANDO_JS.read_text(encoding="utf-8")
    assert "['vista', ['panel', 'indice', 'fichas', 'controles', 'presentador']]" in mando
    assert "['narracion', ['frase', 'pausa', 'voz', 'preparando', 'habla']]" in mando


def test_el_presentador_solo_usa_lo_que_el_sitio_publica():
    # los módulos de three que importa están en la copia de web/vendor (build_site.py falla si falta uno)
    for js in PRESENTADOR.glob("*.js"):
        for m in re.findall(r"from 'three/addons/([^']+)'", js.read_text(encoding="utf-8")):
            assert (VENDOR_THREE / "examples" / "jsm" / m).is_file(), (js.name, m)
    # sin texturas, modelos ni scripts de afuera: el personaje se arma con geometrías
    for js in PRESENTADOR.glob("*.js"):
        texto = js.read_text(encoding="utf-8")
        assert not re.search(r"https?://", texto.split("\n", 30)[-1]), js.name
    # la página del taller no se indexa y el lienzo de la presentación no toma toques
    assert '<meta name="robots" content="noindex">' in (WEB / "presentador.html").read_text(encoding="utf-8")
    assert ".presentador { position: fixed; z-index: 8; left: 0; top: 0; pointer-events: none; }" in \
        (WEB / "propuesta.html").read_text(encoding="utf-8")
