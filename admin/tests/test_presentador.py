"""El presentador (web/js/presentador/): la caricatura en 3D que explica lo que narra el asistente, con Node.

* El personaje se arma sin DOM ni WebGL (three en Node, desde web/vendor): mide lo que dice, con los pies en el piso, y
  trae los huesos y las manos que mueve el animador.
* El animador: cada gesto entra y sale (o se sostiene hasta otro), ninguno deja un ángulo que no sea un número, hablar
  abre la boca y callar la cierra, señalar a la izquierda o a la derecha usa el brazo de ese lado, y entrar y salir
  lo muestran y lo ocultan. Detrás del subtítulo: entra agachado sin pasarse (y saluda antes de terminar de subir), se
  agacha y sale sin subir antes (con el «gracias» de la despedida, un poco más), se asoma desde donde esté, camina con
  la velocidad y el rumbo que le piden; con movimiento reducido, todo eso en el acto y el cuerpo gira en el acto.
* La carga perezosa (perezoso.js): un «quitar», un «mostrar» o un aviso de la escena (encuadre, atlas, simulación,
  ambiente) no cargan el módulo; el primer aviso que lo necesita sí, y lo que llegó mientras cargaba se le pasa en orden
  (de cada aviso de la escena, el último); con el presentador apagado no se carga; si no se pudo crear, lo que llega se
  ignora; `alturaMano()` es null hasta que está listo.
* El mando de la presentación (mando.js) le avisa cada cosa: la escena (con o sin resaltado, con o sin obra, y lo que
  se explica: el paso, su tipo, el resaltado, lo visual, la inmersión, `mover`, `simular`, las frases y el cambio de
  capítulo o de paso), la frase (con la voz o sin ella), `habla`, la pausa, el cierre, la píldora de «prepara», la
  explicación suelta, quitarla y la preferencia del panel (`vista {presentador}`); y, si la capa visual lo sabe, dónde
  queda la obra (`encuadre`, después de aplicar), el modelo del atlas que cargó (`atlas`), lo que se accionó
  (`simulacion`) y la luz de la maqueta (`ambiente`). Una escena que cambia de paso no lo despide en el camino, y un
  presentador (o una capa visual) que falla no rompe nada de la presentación.
* Las vistas (vistas.js, con Node): qué vista, lado y regla toma cada caso de la especificación (lo resaltado, la obra
  pedida, el tipo de paso, la pantalla chica, el atlas, el cierre); el movimiento suave del recorrido no cuenta como obra
  (y sus giros son los de app/recorrido.py); el lugar deja la punta del dedo fuera del panel y de la ficha, con
  histéresis, un cambio por escena y ninguno en una escena corta; las transiciones (girar, acercarse, caminar, saltar, el
  rótulo y, con movimiento reducido, solo fundirse o girar); el rótulo (bajo el panel si cabe, si no acoplado al
  subtítulo, que no lo pasa); los tiempos del resumen.
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
                                "asentir", "aprobar", "escuchar", "despedirse", "destacar", "comparar", "enumerar", "crecer",
                                "grande", "detalle", "construir", "preguntar", "negar", "calmar", "aplaudir", "juntos",
                                "corazon", "mirar_maqueta"}
    assert r["habla"]["hablando"] and r["habla"]["abrirMax"] > 0.3, r["habla"]
    assert r["calla"] == {"hablando": False, "abrir": 0.0} or (not r["calla"]["hablando"] and r["calla"]["abrir"] < 0.01), r["calla"]
    # a la izquierda de la pantalla (−x) señala con el brazo derecho del personaje, y al revés
    assert r["senalar"]["izquierda"]["D"] > 1 > r["senalar"]["izquierda"]["I"], r["senalar"]
    assert r["senalar"]["derecha"]["I"] > 1 > r["senalar"]["derecha"]["D"], r["senalar"]
    assert r["camina"] == 1.0
    assert r["salio"] is False and r["entro"] == {"visible": True, "y": 0.0} and r["numeros"], r


NODE_AGACHARSE = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
const THREE = await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { crearAnimador } = await import(pathToFileURL(`${dir}/animador.js`).href);
const azar = () => { let k = 7; return () => ((k = (k * 16807) % 2147483647) / 2147483647); };
const r = {};
const nuevo = (o = {}) => {
  const p = crearPersonaje({ documento: null });
  const a = crearAnimador(p, { azar: azar(), ...o });
  a.camara = new THREE.PerspectiveCamera(17, 1, 0.1, 50);
  a.camara.position.set(0, 1.2, 8);
  return { p, a };
};
const r3 = (v) => Math.round(v * 1000) / 1000;
// corre a 60 cuadros por segundo: las alturas del cuerpo y cuándo llamó cada aviso
const correr = (x, s) => { const ys = []; for (let i = 0; i < Math.round(s * 60); i++) { x.a.actualizar(1 / 60); x.t += 1 / 60; ys.push(x.p.cuerpo.position.y); } return ys; };
{
  const x = nuevo();
  x.t = 0;
  correr(x, 0.5);
  let t0 = x.t, tFin = null, tCasi = null;
  x.a.entrar(() => { tFin = x.t - t0; }, { hondo: 1.57, casi: [0.3, () => { tCasi = x.t - t0; }] });
  let ys = correr(x, 1.5);
  r.entrar = { desde: r3(ys[0]), max: r3(Math.max(...ys)), fin: r3(ys.at(-1)), tFin: r3(tFin), tCasi: r3(tCasi), sube: ys.every((y, i) => i === 0 || y >= ys[i - 1] - 1e-9) };
  t0 = x.t; tFin = null;
  x.a.agacharse(() => { tFin = x.t - t0; }, { hondo: 1.57 });
  ys = correr(x, 1);
  r.agacharse = { max: r3(Math.max(...ys)), fin: r3(ys.at(-1)), tFin: r3(tFin), visible: x.p.grupo.visible, agachado: x.a.estado().agachado };
  // a medio agacharse vuelve a asomarse: desde donde está, sin bajar antes
  x.a.asomarse();
  correr(x, 0.5);
  x.a.agacharse();
  correr(x, 0.1);
  const desde = x.p.cuerpo.position.y;
  t0 = x.t; tFin = null;
  x.a.asomarse(() => { tFin = x.t - t0; });
  ys = correr(x, 1);
  r.asomarse = { desde: r3(desde), min: r3(Math.min(...ys)), fin: r3(ys.at(-1)), tFin: r3(tFin) };
  t0 = x.t; tFin = null;
  x.a.salir(() => { tFin = x.t - t0; });
  ys = correr(x, 1.2);
  r.salir = { max: r3(Math.max(...ys)), visible: x.p.grupo.visible, tFin: r3(tFin) };
  x.a.entrar(null, { instante: true });
  correr(x, 0.3);
  t0 = x.t; tFin = null;
  x.a.salir(() => { tFin = x.t - t0; }, { gracias: true });
  ys = correr(x, 1.2);
  r.gracias = { max: r3(Math.max(...ys)), visible: x.p.grupo.visible, tFin: r3(tFin) };
  // caminar detrás del subtítulo: la velocidad que le piden y en 3/4 (rumbo 0.6), no de perfil
  x.a.entrar(null, { instante: true });
  correr(x, 0.2);
  x.a.reubicar(0);
  x.a.caminarA(1.6, { velocidad: 1.64, rumbo: 0.6, zancada: 0.65 });
  let rumbo = 0, tLlega = null;
  t0 = x.t;
  for (let i = 0; i < 180; i++) { x.a.actualizar(1 / 60); x.t += 1 / 60; rumbo = Math.max(rumbo, Math.abs(x.a.estado().rumbo)); if (tLlega === null && !x.a.estado().caminando) tLlega = x.t - t0; }
  r.caminar = { x: r3(x.a.estado().x), tLlega: r3(tLlega), rumbo: r3(rumbo) };
  x.a.girar(0.35, { ya: true });
  r.girarYa = x.a.estado().rumbo;
  x.p.liberar();
}
{
  // movimiento reducido: entrar, salir, agacharse y asomarse en el acto; el cuerpo gira en el acto
  const x = nuevo({ reducido: true });
  x.t = 0;
  correr(x, 0.3);
  const marcas = [];
  x.a.agacharse(() => marcas.push('agacha'), { hondo: 1.4 });
  marcas.push(r3(x.p.cuerpo.position.y));
  x.a.asomarse(() => marcas.push('asoma'));
  marcas.push(r3(x.p.cuerpo.position.y));
  x.a.salir(() => marcas.push('sale'));
  marcas.push(x.p.grupo.visible);
  x.a.entrar(() => marcas.push('entra'));
  marcas.push(r3(x.p.cuerpo.position.y), x.p.grupo.visible);
  x.a.girar(0.35);
  x.a.actualizar(1 / 60);
  r.reducido = { marcas, rumbo: x.a.estado().rumbo };
  x.p.liberar();
}
console.log(JSON.stringify(r));
"""


@requiere_node
def test_detras_del_subtitulo_se_agacha_se_asoma_y_camina(tmp_path):
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_AGACHARSE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=120, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    # entra agachado desde abajo, sube sin pasarse (nunca sobre 0) en 0.8 s y el saludo empieza 0.3 s antes del final
    e = r["entrar"]
    assert e["desde"] < -1.4 and e["max"] <= 0 and e["fin"] == 0 and e["sube"], e
    assert 0.7 <= e["tFin"] <= 0.85 and abs(e["tFin"] - e["tCasi"] - 0.3) < 0.05, e
    # se agacha sin subir antes (0.3 s) y se queda agachado, a la vista
    a = r["agacharse"]
    assert a["max"] <= 0 and a["fin"] == -1.57 and a["tFin"] <= 0.35 and a["visible"] and a["agachado"] == 1, a
    # a medio camino se asoma desde donde está (sin bajar antes) y tarda menos que desde abajo
    s = r["asomarse"]
    assert -1.5 < s["desde"] < -0.1 and s["min"] >= s["desde"] - 1e-6 and s["fin"] == 0 and s["tFin"] < 0.45, s
    # sale sin subir antes: oculto en 0.45 s; con el «gracias» de la despedida, en 0.6 s
    assert r["salir"]["max"] <= 0 and r["salir"]["visible"] is False and r["salir"]["tFin"] <= 0.5, r["salir"]
    assert r["gracias"]["max"] <= 0 and r["gracias"]["visible"] is False and 0.5 < r["gracias"]["tFin"] <= 0.65, r["gracias"]
    # camina a la velocidad pedida, en 3/4 (rumbo 0.6, no de perfil), y gira en el acto si se lo piden
    c = r["caminar"]
    assert abs(c["x"] - 1.6) < 0.02 and c["tLlega"] <= 1.2 and 0.55 <= c["rumbo"] <= 0.61, c
    assert r["girarYa"] == 0.35
    # movimiento reducido: todo en el acto, en orden, y el cuerpo gira sin muelle
    assert r["reducido"] == {"marcas": ["agacha", -1.4, "asoma", 0, "sale", False, "entra", 0, True], "rumbo": 0.35}, r["reducido"]


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
{
  // los avisos de la escena: sin cargar no lo despiertan (ni hay mano que preguntar); mientras carga, de cada uno el último
  const x = armar();
  x.p.encuadre({ n: 1 }); x.p.atlas({ listo: true }); x.p.simulacion({ controles: ['hora'] }); x.p.ambiente({ hora: 'tarde' });
  await dormir(20);
  r.avisos_no_despiertan = { cargas: x.cargas, estado: x.p.estado(), mano: x.p.alturaMano() };
  x.p.narrar({ n: 2 }); x.p.ambiente({ hora: 'tarde' }); x.p.encuadre({ n: 2 }); x.p.ambiente({ hora: 'noche' });
  await dormir(20);
  r.avisos_en_cola = { cargas: x.cargas, llamadas: x.llamadas };
}
{
  // la altura de la mano: la del de verdad cuando está listo; null antes, o si el de verdad falla
  const p = presentadorPerezoso(async () => ({ alturaMano: () => ({ lado: 'panel', y: 671 }) }));
  const antes = p.alturaMano();
  p.narrar({ n: 1 });
  await dormir(20);
  const roto = presentadorPerezoso(async () => ({ alturaMano: () => { throw new Error('roto'); } }));
  roto.narrar({ n: 1 });
  await dormir(20);
  r.mano = [antes, p.alturaMano(), roto.alturaMano()];
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
    assert r["avisos_no_despiertan"] == {"cargas": 0, "estado": "sin_cargar", "mano": None}, r["avisos_no_despiertan"]
    assert r["avisos_en_cola"] == {"cargas": 1, "llamadas": [
        ["narrar", {"n": 2}], ["encuadre", {"n": 2}], ["ambiente", {"hora": "noche"}]]}, r["avisos_en_cola"]
    assert r["mano"] == [None, {"lado": "panel", "y": 671}, None], r["mano"]


def _guion_mando(escenarios: str) -> str:
    base = NODE_MANDO.split("const r = {};")[0]
    viejo = "    restaurarEncuadre: () => { log.push(['restaurar']); } });"
    assert base.count(viejo) == 1
    base = base.replace(viejo, "    restaurarEncuadre: () => { log.push(['restaurar']); }, presentador: globalThis.PRESENTADOR });")
    # la capa visual de mentira, con lo que el guion le sume (globalThis.VISUAL_EXTRA(log): cajaObra, luz, modoDe, simular)
    capa = "ventana, documento, visual,"
    assert base.count(capa) == 1
    return base.replace(capa, "ventana, documento, visual: Object.assign(visual, globalThis.VISUAL_EXTRA?.(log) ?? {}),") + escenarios


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
  // el gesto que pidió el asistente llega al presentador; uno que no existe se descarta (aviso parcial) y elige solo
  const g1 = await a.pedir('escena', { id: 18, ...E({ paso: 2, n: 3, gesto: 'comparar' }) });
  const g2 = await a.pedir('escena', { id: 19, ...E({ paso: 2, n: 3, gesto: 'volar' }) });
  r.gestos = [tomar(), g1?.aviso ?? null, g2?.aviso ?? null, (g2?.descartadas || []).map((x) => x.clave)];
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
// el paso de inmersión (el 4: torre_sismo) y un `mover` que llega tal cual; sin cajaObra ni luz en la capa no van
// `encuadre` ni `ambiente`; el aviso del atlas, cuando el modelo terminó de cargar (o venció la espera)
{
  const a = armar();
  a.mandar('escena', { id: 1, ...E({ paso: 4, n: 2, mover: { giro: 12 } }) });
  await dormir(15);
  r.inmersion = tomar();
  a.asientos.shift()?.(false);
  await dormir(15);
  r.inmersion_lista = [tomar(), a.respuesta(1)?.aviso ?? null];
}
// una capa que sabe de la escena (cajaObra, luz, modoDe y simular): el encuadre después de aplicar, la luz después de
// aplicar, de simular y con cada frase, lo que se accionó (sin lo que el modelo rechazó) y el modo de la inmersión
const CAJA = { obra: { x0: 600, y0: 200, x1: 900, y1: 500 }, rotulos: [{ x0: 700, y0: 170, x1: 790, y1: 196 }] };
const LUZ = { hora: 'atardecer', luz: '#ffbd88', intensidad: 2.5, cielo: '#8d9fd0', piso: '#4a3f33', hemi: 0.58, oscuridad: 0.5, sol: [0.4, 0.3, -0.87], solFin: [0.4, 0.3, -0.87] };
{
  globalThis.VISUAL_EXTRA = (log) => ({
    cajaObra: () => { log.push(['cajaObra']); return structuredClone(CAJA); },
    luz: () => structuredClone(LUZ),
    modoDe: (id) => ({ torre_sismo: 'sismo', torre_bim: 'bim' })[id] ?? null,
    simular: async (lista) => lista.filter((x) => x.control === 'malo').map((x) => ({ clave: `simular.${x.control}`, motivo: 'no está' })),
  });
  const a = armar();
  globalThis.VISUAL_EXTRA = null;
  await a.pedir('escena', { id: 1, ...E({ paso: 2, visual: { ...structuredClone(V0), enfoque: 'torre' },
    simular: [{ control: 'hora', valor: 'noche' }, { control: 'malo' }] }) });
  r.capa = { llamadas: tomar(), nombres: a.nombres() };
  await a.pedir('narracion', { id: 2, frase: 1 });
  r.capa_frase = tomar();
  await a.pedir('visual', { id: 3, tema: 'oscuro' });
  r.capa_visual = tomar();
  const s = await a.pedir('visual', { id: 4, simular: [{ control: 'malo' }] });
  r.capa_simular_malo = [tomar(), s?.tipo];
  a.mandar('escena', { id: 5, ...E({ paso: 4, n: 2 }) });
  await dormir(15);
  const narrar = tomar();
  a.asientos.shift()?.(true);
  await dormir(15);
  r.capa_inmersion = [narrar, tomar()];
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
// y una capa visual cuyo saber de la escena falla (cajaObra, luz y modoDe lanzan): tampoco
{
  globalThis.VISUAL_EXTRA = () => ({ cajaObra: () => { throw new Error('roto'); }, luz: () => { throw new Error('roto'); },
    modoDe: () => { throw new Error('roto'); } });
  const a = armar();
  globalThis.VISUAL_EXTRA = null;
  const e = await a.pedir('escena', { id: 1, ...E({ paso: 2 }) });
  const f = await a.pedir('narracion', { id: 2, frase: 1 });
  const v = await a.pedir('visual', { id: 3, tema: 'claro' });
  r.capa_rota = [e?.tipo, e?.aviso ?? null, f?.tipo, v?.tipo];
}
console.log(JSON.stringify(r));
"""

# Lo de siempre de `narrar` (el taller y los presentadores de antes leen solo esto)
VIEJAS = ("n", "de", "senal", "gesto", "frases", "obra")


def _narrar(llamadas, **esperado):
    """La llamada `narrar` de `llamadas` (debe ser la única) con lo de siempre y, aparte, las claves de `esperado`."""
    assert len(llamadas) == 1 and llamadas[0][0] == "narrar", llamadas
    d = llamadas[0][1]
    for k, v in esperado.items():
        assert d.get(k, "falta") == v, (k, d.get(k, "falta"), v)
    return {k: d[k] for k in VIEJAS}


@requiere_node
def test_el_mando_le_avisa_al_presentador(tmp_path):
    r = _node(tmp_path, _guion_mando(NODE_MANDO_PRESENTADOR), MANDO_JS.as_uri())
    # la escena: lo de siempre (con los valores de antes) y lo nuevo, aparte (E() de la prueba: salud/1, donde ya está)
    v0 = {"enfoque": None, "camara": "paso", "rumbo": None, "elevacion": None, "zoom": None, "mirar": None, "girar": False,
          "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": [], "ocultar": [], "aislar": None, "sin": []}
    assert _narrar(r["escena1"], rid="abcdef123456", ms=7400, capitulo="salud", paso=1, tipo=None, lista=0, cambio=None,
                   panel=True, resaltar=None, visual=v0, atlas=None, modo=None, animar=False, simular=None, mover=None,
                   textos=["Frase uno.", "Frase dos."]) \
        == {"n": 1, "de": 3, "senal": False, "gesto": None, "frases": 2, "obra": False}
    assert len(r["escena1"][0][1]) == 22, sorted(r["escena1"][0][1])
    assert r["frase"] == [["frase", 1, {"voz": True, "texto": "Frase dos."}]], r["frase"]
    assert r["habla"] == [["habla", True], ["habla", False]]
    assert r["habla_mala"] == "error"
    assert r["pausa"] == [["pausa", True], ["pausa", False]]
    assert _narrar(r["escena2"], cambio="paso", resaltar={"tipo": "cifra", "n": 1}, paso=2, visual={**v0, "mirar": "torre"}) \
        == {"n": 2, "de": 3, "senal": True, "gesto": None, "frases": 2, "obra": True}
    assert [_narrar([x], cambio=None) for x in r["gestos"][0]] == [
        {"n": 3, "de": 3, "senal": False, "gesto": "comparar", "frases": 2, "obra": False},
        {"n": 3, "de": 3, "senal": False, "gesto": None, "frases": 2, "obra": False}], r["gestos"]
    assert r["gestos"][1:] == [None, "parcial", ["gesto"]], r["gestos"]
    assert r["cierre"] == [["cierre", ["Uno", "Dos"], {"voz": False}], ["cierre", None, {"voz": False}]], r["cierre"]
    assert r["quitar"] == [["quitar"]]
    assert r["explicar"] == [["explicar", "La torre tiene cuatro pisos."]]
    assert r["preparando"] == [["preparando", True], ["preparando", False]], r["preparando"]
    assert r["vista"] == [["mostrar", False]] and r["vista_mala"] == "error"
    # el paso de inmersión: la inmersión del paso y su `mover` tal cual; sin la capa que sabe, ni encuadre ni ambiente; el
    # aviso del atlas cuando la espera termina
    assert _narrar(r["inmersion"], tipo="inmersion", atlas="torre_sismo", modo=None, cambio="paso", mover={"giro": 12},
                   simular=None) == {"n": 2, "de": 3, "senal": False, "gesto": None, "frases": 2, "obra": True}
    assert r["inmersion_lista"] == [[["atlas", {"rid": "abcdef123456", "n": 2, "listo": False}]], "asiento"], r["inmersion_lista"]
    # con la capa que sabe: encuadre (después de aplicar) y ambiente; lo accionado, sin lo que el modelo rechazó
    caja = {"obra": {"x0": 600, "y0": 200, "x1": 900, "y1": 500}, "rotulos": [{"x0": 700, "y0": 170, "x1": 790, "y1": 196}]}
    luz = {"hora": "atardecer", "luz": "#ffbd88", "intensidad": 2.5, "cielo": "#8d9fd0", "piso": "#4a3f33", "hemi": 0.58,
           "oscuridad": 0.5, "sol": [0.4, 0.3, -0.87], "solFin": [0.4, 0.3, -0.87]}
    llamadas = r["capa"]["llamadas"]
    assert [x[0] for x in llamadas] == ["narrar", "encuadre", "ambiente", "simulacion", "ambiente"], llamadas
    assert _narrar(llamadas[:1], cambio="paso", simular={"modelo": "maqueta", "controles": ["hora", "malo"]},
                   visual={**v0, "enfoque": "torre"})["obra"] is True
    assert llamadas[1:] == [["encuadre", {"rid": "abcdef123456", "n": 1, "caja": caja}], ["ambiente", luz],
                            ["simulacion", {"rid": "abcdef123456", "n": 1, "modelo": "maqueta", "controles": ["hora"]}],
                            ["ambiente", luz]], llamadas
    nombres = r["capa"]["nombres"]
    assert nombres.index("aplicar") < nombres.index("cajaObra"), nombres
    assert r["capa_frase"] == [["frase", 1, {"voz": False, "texto": "Frase dos."}], ["ambiente", luz]], r["capa_frase"]
    assert r["capa_visual"] == [["encuadre", {"rid": "abcdef123456", "n": 1, "caja": caja}], ["ambiente", luz]], r["capa_visual"]
    assert r["capa_simular_malo"] == [[["ambiente", luz]], "error"], r["capa_simular_malo"]
    narrar, despues = r["capa_inmersion"]
    assert [x[0] for x in narrar] == ["narrar", "encuadre", "ambiente"], narrar
    assert _narrar(narrar[:1], atlas="torre_sismo", modo="sismo", tipo="inmersion")["obra"] is True
    assert despues == [["atlas", {"rid": "abcdef123456", "n": 2, "listo": True}]], despues
    # un presentador que falla, o una capa cuyo saber de la escena falla, no rompen nada
    assert r["roto"] == ["estado", "estado", "estado", False], r["roto"]
    assert r["capa_rota"] == ["estado", None, "estado", "estado"], r["capa_rota"]


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



# ───────────────────────────── Las vistas (vistas.js): qué plano, dónde y hacia dónde ─────────────────────────────

NODE_VISTAS = r"""import { pathToFileURL } from 'node:url';
const [dir] = process.argv.slice(2);
const V = await import(pathToFileURL(`${dir}/vistas.js`).href);
const V0 = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false,
  comparar: 'proyecto', detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
// una escena como la manda mando.js (salud/2 por omisión)
const E = (o = {}) => ({ evento: 'narrar', n: 2, de: 4, capitulo: 'salud', paso: 2, tipo: 'componentes', lista: 0, cambio: null,
  panel: true, resaltar: null, atlas: null, modo: null, animar: false, simular: null, mover: null, gesto: null,
  textos: ['Una frase.'], ...o, visual: { ...V0, ...(o.visual || {}) } });
const ESC = { chica: false, VW: 1440, VH: 900, horizontal: false, nuevo: false, reducido: false,
  dom: { conInmersion: false, conDetalle: false, sinPanel: false }, anterior: null };
const CEL = { ...ESC, chica: true, VW: 390, VH: 844 };
const casos = {
  bienvenida: [E({ capitulo: 'portada', paso: 1, n: 1, tipo: 'portada' }), { ...ESC, nuevo: true }],
  cifra: [E({ capitulo: 'portada', paso: 1, tipo: 'portada', resaltar: { tipo: 'cifra', n: 2 } }), ESC],
  cifra_celular: [E({ capitulo: 'portada', paso: 1, tipo: 'portada', resaltar: { tipo: 'cifra', n: 2 } }), CEL],
  portadilla_capitulo: [E({ capitulo: 'vivienda', paso: 1, n: 1, tipo: 'portadilla', cambio: 'capitulo' }), ESC],
  portadilla_pregunta: [E({ capitulo: 'tic', paso: 1, n: 1, tipo: 'portadilla', cambio: 'capitulo', textos: ['¿Por qué una granja solar?'] }), ESC],
  portadilla_sigue: [E({ capitulo: 'vivienda', paso: 1, n: 2, tipo: 'portadilla' }), ESC],
  lista: [E({ capitulo: 'aguas', tipo: 'texto', lista: 5 }), ESC],
  punto: [E({ capitulo: 'aguas', tipo: 'texto', lista: 5, resaltar: { tipo: 'punto', n: 3 } }), ESC],
  metas: [E({ capitulo: 'vivienda', paso: 6, tipo: 'metas' }), ESC],
  metas_crecen: [E({ capitulo: 'vivienda', paso: 6, tipo: 'metas', textos: ['Pasamos de 120 a 300 viviendas.'] }), ESC],
  telesalud: [E({ resaltar: { tipo: 'componente', id: 'telesalud' } }), ESC],
  automatica: [E({ paso: 3, tipo: 'componente', mover: { giro: 12, zoom: 1.06 }, animar: true }), ESC],
  metas_suave: [E({ paso: 10, tipo: 'metas', mover: { giro: -10 } }), ESC],
  metas_pedido: [E({ paso: 10, tipo: 'metas', mover: { giro: 40, elevacion: 60 } }), ESC],
  animar_solo: [E({ capitulo: 'tic', paso: 6, tipo: 'texto', animar: true }), ESC],
  ficha_dato: [E({ paso: 3, tipo: 'componente', visual: { detalle: 'torre' }, resaltar: { tipo: 'especificacion', n: 3, en: 'ficha' } }), ESC],
  ficha: [E({ paso: 3, tipo: 'componente', visual: { detalle: 'torre' } }), ESC],
  ficha_celular: [E({ paso: 3, tipo: 'componente', visual: { detalle: 'torre' } }), CEL],
  espec_panel: [E({ paso: 3, tipo: 'componente', resaltar: { tipo: 'especificacion', n: 2, en: 'panel' } }), ESC],
  leyenda: [E({ capitulo: 'aguas', paso: 3, tipo: 'comparacion', resaltar: { tipo: 'leyenda', n: 2 } }), ESC],
  leyenda_celular: [E({ capitulo: 'aguas', paso: 3, tipo: 'comparacion', resaltar: { tipo: 'leyenda', n: 2 } }), CEL],
  comparacion: [E({ capitulo: 'aguas', paso: 3, tipo: 'comparacion' }), ESC],
  hoy: [E({ capitulo: 'urbanismo', paso: 3, tipo: 'componente', visual: { comparar: 'hoy' } }),
    { ...ESC, anterior: { capitulo: 'urbanismo', paso: 3, visual: { ...V0 }, vista: 'presenta', lado: 'obra' } }],
  proyecto_otro_paso: [E({ capitulo: 'aguas', paso: 2, tipo: 'texto', lista: 5, visual: { comparar: 'proyecto' } }), ESC],
  enfoque: [E({ paso: 3, tipo: 'componente', visual: { enfoque: 'torre', camara: 'cerca' } }), ESC],
  aislar: [E({ paso: 3, tipo: 'componente', visual: { aislar: 'torre', sin: ['torre.cubierta'] } }), ESC],
  solo3d: [E({ paso: 3, tipo: 'componente', panel: false }), ESC],
  solo3d_leyenda: [E({ capitulo: 'aguas', paso: 3, tipo: 'comparacion', panel: false, resaltar: { tipo: 'leyenda', n: 1 } }), ESC],
  inmersion: [E({ paso: 6, tipo: 'inmersion', atlas: 'torre_sismo', modo: 'sismo' }), ESC],
  inmersion_maqueta: [E({ paso: 6, tipo: 'inmersion', visual: { inmersion: 'maqueta' } }), ESC],
  noche: [E({ capitulo: 'urbanismo', paso: 3, tipo: 'componente', simular: { modelo: 'maqueta', controles: ['hora'] } }), ESC],
  cronograma: [E({ capitulo: 'ruta', paso: 1, tipo: 'cronograma' }), ESC],
  senalar: [E({ capitulo: 'aguas', paso: 2, tipo: 'texto', gesto: 'senalar' }), ESC],
  senalar_enfoque: [E({ paso: 3, tipo: 'componente', gesto: 'senalar', visual: { enfoque: 'torre' } }), ESC],
  horizontal: [E({ paso: 3, tipo: 'componente' }), { ...ESC, chica: true, horizontal: true, VW: 844, VH: 390 }],
  texto: [E({ capitulo: 'tic', paso: 6, tipo: 'texto', lista: 0 }), ESC],
  cierre: [{ evento: 'cierre' }, ESC],
  cierre_celular: [{ evento: 'cierre' }, CEL],
  preguntas: [{ evento: 'preguntas' }, ESC],
  preparando: [{ evento: 'preparando' }, ESC],
  preparando_atlas: [{ evento: 'preparando' }, { ...ESC, dom: { ...ESC.dom, conInmersion: true } }],
  explicar: [{ evento: 'explicar' }, ESC],
  saludar_al_subir: [E({ capitulo: 'portada', paso: 1, n: 1, tipo: 'portada', gesto: 'saludar' }), { ...ESC, nuevo: true }],
  dato_al_subir: [E({ capitulo: 'portada', paso: 1, n: 1, tipo: 'portada', resaltar: { tipo: 'cifra', n: 1 } }), { ...ESC, nuevo: true }],
};
const r = { vistas: {} };
for (const [k, [d, ctx]] of Object.entries(casos)) {
  const e = V.elegirVista(d, ctx);
  r.vistas[k] = { vista: e.vista, lado: e.lado, regla: e.regla, gesto: e.gesto, frente: e.frente, objetivo: e.objetivo,
    saludo: e.saludoPrimero, corto: e.saludoCorto, capitulo: e.transicionCapitulo };
}
r.suaves = [{ giro: 12, zoom: 1.06 }, { giro: -10 }, { giro: 14, zoom: 1.7 }, { giro: 40 }, { giro: 12, elevacion: 60 }, { zoom: 1.3 }, null].map(V.esSuave);
// el lugar, con las cajas de 1440x900 (el subtítulo a la derecha del panel)
const ctx = { ...ESC };
const sub = { x0: 627, y0: 721, x1: 1365, y1: 814 }, panel = { x0: 100, y0: 76, x1: 552, y1: 818 };
const senala = { vista: 'senala', lado: 'panel', objetivo: 'foco' };
const m = V.medidas('senala', ctx);
r.medidas = { p: m.p, Wc: m.Wc, Hc: m.Hc, bajo: m.bajo, plano: m.plano };
const punto = { x: 528, y: V.yHombro(sub.y0, m) };
const al = V.elegirLugar(senala, m, ctx, { sub, panel }, {}, { punto });
const punta = V.alcance(al.x, punto, { p: m.p, subTop: sub.y0, rumbo: V.rumboDe('senala', punto.x - al.x) }).punta;
// el más cerca que deja el alcance: 40 px más a la izquierda la punta entraría al panel
const masCerca = V.lugares(senala, m, ctx, { sub, panel }, { punto, todos: true }).filter((l) => l.x < al.x - 20 && l.x > al.x - 60);
r.panel = { x: al.x, punta: punta.x, borde: panel.x1, masCerca: masCerca.map((l) => l.razon) };
// la ficha a la derecha: la punta no entra en ella
const subF = { x0: 568, y0: 696, x1: 1010, y1: 814 }, ficha = { x0: 1024, y0: 76, x1: 1424, y1: 814 };
const puntoF = { x: ficha.x0 + 6, y: V.yHombro(subF.y0, m) };
const alF = V.elegirLugar({ vista: 'senala', lado: 'ficha', objetivo: 'foco' }, m, ctx, { sub: subF, panel, ficha }, {}, { punto: puntoF });
r.ficha = { x: alF.x, punta: V.alcance(alF.x, puntoF, { p: m.p, subTop: subF.y0, rumbo: 0.35 }).punta.x, borde: ficha.x0 };
// histéresis: el anfitrión con la obra a la derecha y un rótulo en el centro
const anf = { vista: 'anfitrion', lado: 'sala', objetivo: 'sala' };
const ma = V.medidas('anfitrion', ctx);
const cajas = { sub, panel, obra: { x0: 900, y0: 200, x1: 1400, y1: 640 }, rotulos: [{ x0: 960, y0: 560, x1: 1040, y1: 600 }] };
const mejor = V.lugares(anf, ma, ctx, cajas)[0];
const cerca = V.lugares(anf, ma, ctx, cajas).find((l) => l.x !== mejor.x && l.costo <= 1.25 * mejor.costo + 0.02);
const lejos = V.lugares(anf, ma, ctx, cajas).find((l) => l.costo > 1.25 * mejor.costo + 0.05);
r.histeresis = {
  mejor: mejor.x,
  queda: V.elegirLugar(anf, ma, ctx, cajas, { x: cerca.x }).razon,
  cambia: V.elegirLugar(anf, ma, ctx, cajas, { x: lejos.x }),
  ya_cambio: V.elegirLugar(anf, ma, ctx, cajas, { x: lejos.x, cambios: 1 }).razon,
  corta: V.elegirLugar(anf, ma, ctx, cajas, { x: lejos.x, ms: 3000 }).razon,
  // la cadera en el aire (más allá del subtítulo): se va aunque ya haya cambiado
  no_sirve: V.elegirLugar(anf, ma, ctx, cajas, { x: sub.x1 - 10, cambios: 1 }).razon,
  lejos: lejos.x,
};
// las transiciones
const A = { vista: 'anfitrion', plano: 'americano', p: 324, x: 996 };
r.transiciones = [
  V.transicion(A, { ...A, vista: 'senala' }),
  V.transicion(A, { vista: 'cerca', plano: 'medio', p: 450, x: 996 }),
  V.transicion(A, { ...A, vista: 'senala', x: 800 }),
  V.transicion(A, { ...A, vista: 'presenta', x: 680 }),
  V.transicion(A, { vista: 'rotulo', plano: 'medio', p: 180, x: 700 }),
  V.transicion(A, { ...A, x: 800 }, { reducido: true }),
  V.transicion(A, { vista: 'cerca', plano: 'medio', p: 450, x: 996 }, { reducido: true }),
  V.transicion(A, { ...A, vista: 'senala' }, { reducido: true }),
];
// más: el plano nuevo a menos de 0.2·pxAlto se acerca (y se corre); lejos, salta; de un rótulo a otro, se funde; con
// movimiento reducido nunca camina, salta, se acerca ni cambia al rótulo con escala
const R = { vista: 'rotulo', plano: 'primer', p: 207, x: 492, modo: 'panel' };
r.transiciones2 = {
  acercar_corre: V.transicion(A, { vista: 'cerca', plano: 'medio', p: 450, x: 1040 }),
  saltar_plano: V.transicion(A, { vista: 'cerca', plano: 'medio', p: 450, x: 760 }),
  rotulo_figura: V.transicion(R, A),
  rotulo_rotulo: V.transicion(R, { ...R, p: 135, modo: 'acoplado', x: 680 }),
  reducido: [V.transicion(A, { ...A, x: 800 }, { reducido: true }), V.transicion(A, { ...A, x: 500 }, { reducido: true }),
    V.transicion(A, R, { reducido: true }), V.transicion(R, A, { reducido: true }),
    V.transicion(A, { vista: 'cerca', plano: 'medio', p: 450, x: 1040 }, { reducido: true })],
};
// el rótulo: bajo el panel si entre el panel y el pie del subtítulo cabe el círculo (si no entero, hasta 88 px);
// si no, acoplado al subtítulo (84; 64 en la pantalla chica; de lado, del alto del subtítulo)
const subR = { x0: 627, y0: 721, x1: 1365, y1: 814 };
const panelCorto = { x0: 100, y0: 76, x1: 552, y1: 693 }, panelLargo = { x0: 100, y0: 76, x1: 552, y1: 818 };
const bajo = V.rotuloDe(ESC, { sub: subR, panel: panelCorto });
const aco = V.rotuloDe(ESC, { sub: subR, panel: panelLargo });
const cel = V.rotuloDe(CEL, { sub: { x0: 10, y0: 335, x1: 380, y1: 439 }, panel: { x0: 10, y0: 447, x1: 380, y1: 768 } });
const lado = V.rotuloDe({ ...ESC, chica: true, horizontal: true, VW: 844, VH: 390 }, { sub: { x0: 397, y0: 280, x1: 834, y1: 376 } });
const mR = V.medidas('rotulo', ESC, { rotulo: bajo });
r.rotulo = {
  bajo, aco, cel, lado,
  medidas: { plano: mR.plano, Wc: mR.Wc, Hc: mR.Hc, bajo: mR.bajo, modo: mR.modo },
  // dónde va el círculo: bajo el panel, a 4 px de su borde derecho y al pie del subtítulo; acoplado, a 10 px del
  // extremo, centrado en su alto; con un subtítulo bajo, más chico (no lo pasa)
  posBajo: V.posRotulo(bajo, subR, panelCorto.x1),
  posAco: V.posRotulo(aco, subR),
  posBajito: V.posRotulo(aco, { ...subR, y0: 746 }),
  posCel: V.posRotulo(cel, { x0: 10, y0: 335, x1: 380, y1: 439 }),
};
// el cierre: un dedo al empezar cada punto
const tc = V.tiemposCierre(['Uno: la torre del hospital.', 'Dos: el agua.', 'Tres: vivienda nueva y mejorada para todos.']);
r.cierre = { crece: tc.inicios.every((t, i) => i === 0 || t > tc.inicios[i - 1]), primero: tc.inicios[0], total: tc.total, n: tc.inicios.length };
console.log(JSON.stringify(r));
"""

# la vista esperada de cada caso: [vista, lado, regla] y, si importa, el gesto
VISTAS_ESPERADAS = {
    "bienvenida": ["anfitrion", "sala", "R10"], "cifra": ["senala", "panel", "R5"],
    "cifra_celular": ["busto", "hoja", "R5c", "destacar"], "portadilla_capitulo": ["anfitrion", "sala", "R10", "explicar"],
    "portadilla_pregunta": ["anfitrion", "sala", "R10", "pensar"], "portadilla_sigue": ["presenta", "obra", "R10", "mirar_maqueta"],
    "lista": ["senala", "panel", "R10", "enumerar"], "punto": ["senala", "panel", "R5"],
    "metas": ["senala", "panel", "R10", "mostrar_panel"], "metas_crecen": ["senala", "panel", "R10", "crecer"],
    "telesalud": ["senala", "panel", "R5"], "automatica": ["presenta", "obra", "R10", "presentar"],
    "metas_suave": ["senala", "panel", "R10"], "metas_pedido": ["presenta", "obra", "R8"],
    "animar_solo": ["anfitrion", "sala", "R10", "explicar"], "ficha_dato": ["senala", "ficha", "R4"],
    "ficha": ["senala", "ficha", "R6", "presentar"], "ficha_celular": ["rotulo", "ficha", "R3"],
    "espec_panel": ["senala", "panel", "R5"], "leyenda": ["senala", "leyenda", "R4"],
    "leyenda_celular": ["busto", "arriba", "R4c", "senalar"], "comparacion": ["senala", "panel", "R10", "comparar"],
    "hoy": ["presenta", "obra", "R8", "comparar"], "proyecto_otro_paso": ["senala", "panel", "R10"],
    "enfoque": ["presenta", "obra", "R8", "presentar"], "aislar": ["presenta", "obra", "R8", "detalle"],
    "solo3d": ["general", "obra", "R7"], "solo3d_leyenda": ["senala", "leyenda", "R4"], "inmersion": ["rotulo", "marco", "R2"],
    "inmersion_maqueta": ["presenta", "obra", "R10"], "noche": ["presenta", "obra", "R8"],
    "cronograma": ["senala", "panel", "R10", "presentar"], "senalar": ["senala", "panel", "R9", "senalar"],
    "senalar_enfoque": ["presenta", "obra", "R8", "senalar"], "horizontal": ["rotulo", "sala", "R1"],
    "texto": ["anfitrion", "sala", "R10", "explicar"], "cierre": ["cerca", "sala", "cierre", "contar"],
    "cierre_celular": ["busto", "sala", "cierre", "contar"], "preguntas": ["cerca", "sala", "cierre", "invitar"],
    "preparando": ["anfitrion", "sala", "preparando", "pensar"], "preparando_atlas": ["rotulo", "marco", "R2"],
    "explicar": ["anfitrion", "sala", "explicar", "explicar"], "saludar_al_subir": ["anfitrion", "sala", "R10"],
    "dato_al_subir": ["senala", "panel", "R5"],
}


@requiere_node
def test_elegir_vista(tmp_path):
    r = _node(tmp_path, NODE_VISTAS, str(PRESENTADOR))
    v = r["vistas"]
    assert set(v) == set(VISTAS_ESPERADAS), set(v) ^ set(VISTAS_ESPERADAS)
    for k, esperado in VISTAS_ESPERADAS.items():
        x = v[k]
        assert [x["vista"], x["lado"], x["regla"]] == esperado[:3], (k, x)
        if len(esperado) > 3:
            assert x["gesto"] == esperado[3], (k, x)
    # la bienvenida: saluda al subir (y es el mismo saludo si lo pidió el asistente); con un dato que señalar, corto
    assert v["bienvenida"]["saludo"] and not v["bienvenida"]["corto"] and v["bienvenida"]["objetivo"] == "obra"
    assert v["saludar_al_subir"]["saludo"] and v["saludar_al_subir"]["gesto"] is None
    assert v["dato_al_subir"]["saludo"] and v["dato_al_subir"]["corto"]
    assert not v["cifra"]["saludo"] and not v["inmersion"]["saludo"]
    # el cambio de capítulo mira el panel antes del gesto; el gesto de cara a la sala gira de frente
    assert v["portadilla_capitulo"]["capitulo"] and not v["portadilla_sigue"]["capitulo"]
    assert v["portadilla_capitulo"]["frente"] and v["metas_crecen"]["frente"] and not v["cifra"]["frente"]
    # lo resaltado se señala (el .foco); el panel sin resaltado, el bloque; la ficha sin dato, su centro
    assert v["cifra"]["objetivo"] == v["leyenda"]["objetivo"] == v["ficha_dato"]["objetivo"] == "foco"
    assert v["metas"]["objetivo"] == "bloque" and v["ficha"]["objetivo"] == "ficha" and v["enfoque"]["objetivo"] == "obra"
    # el movimiento suave del recorrido no es «obra pedida»
    assert r["suaves"] == [True, True, True, False, False, False, False], r["suaves"]
    # el americano a 1440x900: la cabeza crece sin que el lienzo pase de 1.45 veces el de antes (257 × 270)
    assert r["medidas"]["plano"] == "americano" and r["medidas"]["p"] == 324 and r["medidas"]["Wc"] * r["medidas"]["Hc"] <= 1.45 * 257 * 270
    # señalando el panel: la punta del índice queda fuera de su vidrio (6 px) y no más lejos de lo que hace falta
    assert r["panel"]["punta"] >= r["panel"]["borde"] + 6, r["panel"]
    assert r["panel"]["masCerca"] and all("alcance" in x for x in r["panel"]["masCerca"]), r["panel"]
    # y la ficha, del otro lado: la punta 12 px antes de su borde
    assert r["ficha"]["punta"] <= r["ficha"]["borde"] - 12, r["ficha"]
    # la histéresis: se queda si no es más de un 25 % peor; si lo es, cambia (una vez por escena; en una escena corta
    # solo gira); si deja de servir, se va igual
    h = r["histeresis"]
    assert h["queda"] == "se_queda", h
    assert h["cambia"]["cambia"] and h["cambia"]["x"] == h["mejor"], h
    assert h["ya_cambio"] == "ya_cambio" and h["corta"] == "corta" and h["no_sirve"] == "no_sirve", h
    assert r["transiciones"] == ["giro", "acercar", "caminar", "saltar", "rotulo", "fundido", "fundido", "giro"], r["transiciones"]
    t2 = r["transiciones2"]
    assert (t2["acercar_corre"], t2["saltar_plano"], t2["rotulo_figura"], t2["rotulo_rotulo"]) == ("acercar", "saltar", "rotulo", "fundido"), t2
    # con movimiento reducido solo se funde (o gira): nunca camina, salta ni se acerca
    assert set(t2["reducido"]) == {"fundido"}, t2
    # el rótulo: bajo el panel (113 a 900 de alto) si cabe; si no, acoplado (84); en el celular 64; de lado, del subtítulo
    ro = r["rotulo"]
    assert ro["bajo"] == {"modo": "panel", "lado": 113, "borde": "izq"} and ro["aco"] == {"modo": "acoplado", "lado": 84, "borde": "izq"}, ro
    assert ro["cel"] == {"modo": "acoplado", "lado": 64, "borde": "der"} and ro["lado"] == {"modo": "acoplado", "lado": 64, "borde": "der"}, ro
    assert ro["medidas"] == {"plano": "primer", "Wc": 113, "Hc": 113, "bajo": 0, "modo": "panel"}, ro
    assert ro["posBajo"] == {"x0": 552 - 4 - 113, "y0": 814 - 113, "L": 113}, ro
    a, b = ro["posAco"], ro["posBajito"]
    assert a["x0"] == 637 and a["L"] == 84 and a["y0"] >= 721 and a["y0"] + a["L"] <= 814, ro
    assert b["L"] < 84 and b["y0"] >= 746 and b["y0"] + b["L"] <= 814, ro
    c = ro["posCel"]
    assert c["x0"] + c["L"] == 380 - 8 and c["y0"] >= 335 and c["y0"] + c["L"] <= 439, ro
    assert r["cierre"]["crece"] and r["cierre"]["n"] == 3 and 0.5 < r["cierre"]["primero"] < 1 and r["cierre"]["total"] <= 16, r["cierre"]


def test_los_giros_suaves_son_los_mismos():
    from app import recorrido as rec
    js = (PRESENTADOR / "vistas.js").read_text(encoding="utf-8")
    m = re.search(r"export const GIROS_SUAVES = \[([^\]]+)\];", js)
    assert m and tuple(int(x) for x in m.group(1).split(",")) == tuple(rec.GIROS_SUAVES)

# ───────────────────────────── La serie de gestos que pide el asistente ─────────────────────────────

def _lista_js(js: str, nombre: str) -> list[str]:
    m = re.search(rf"export const {nombre} = \[(.+?)\];", js, re.S)
    assert m, nombre
    return re.findall(r"'([a-z_]+)'", m.group(1))


def test_los_gestos_son_los_mismos_en_el_servidor_el_puente_el_mando_y_el_animador():
    from app import recorrido as rec
    puente = (ADMIN / "web" / "js" / "agente-presentacion.js").read_text(encoding="utf-8")
    animador = (PRESENTADOR / "animador.js").read_text(encoding="utf-8")
    mando = MANDO_JS.read_text(encoding="utf-8")
    nombres = list(rec.GESTOS)
    assert len(nombres) >= 24 and all(re.fullmatch(r"[a-z_]{3,20}", n) for n in nombres)
    assert _lista_js(puente, "GESTOS") == _lista_js(mando, "GESTOS") == _lista_js(animador, "GESTOS_AGENTE") == nombres
    # cada uno lo sabe hacer el animador (mostrar_panel es señalar hacia el panel) y dice para qué sirve
    hechos = set(re.findall(r"^  (\w+): \(o\) =>", animador, re.M))
    assert set(nombres) - hechos == {"mostrar_panel"}, set(nombres) - hechos
    assert all(5 <= len(rec.GESTOS[n]) <= 80 for n in nombres)


def test_el_asistente_pide_el_gesto_de_cada_paso():
    from app import recorrido as rec
    from app.agente.herramientas import interfaz as hi
    from test_recorrido import G, _armar
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Con el presentador", "pasos": [
        {"capitulo": "salud", "paso": "torre", "gesto": "Saludar", "dice": "Uno."},
        {"gesto": "señalar", "dice": "Dos."},
        {"gesto": "pulgar", "dice": "Tres."},
        {"gesto": "volar", "dice": "Cuatro."},
        {"gesto": "Mostrar panel", "dice": "Cinco."},
        {"dice": "Seis."}]})
    absoluto = r.acciones[0]["recorrido"]
    assert rec.validar(absoluto, G) == []
    # el nombre, con tildes o en otras palabras; el que no existe se descarta con un aviso y el plan corre igual
    assert [e.get("gesto") for e in absoluto["escenas"]] == ["saludar", "senalar", "aprobar", None, "mostrar_panel", None]
    avisos = r.contenido["avisos"]
    assert any(a.startswith("Paso 4: ") and "«volar»" in a and "saludar, senalar" in a for a in avisos), avisos
    assert not any(a.startswith(("Paso 1:", "Paso 2:", "Paso 3:", "Paso 5:")) for a in avisos), avisos
    # la tarjeta del chat lo muestra y al modelo se le dice
    t = r.acciones[1]
    assert ["gesto" in x["hace"] for x in t["escenas"]] == [True, True, True, False, True, False]
    assert hi.HACE["gesto"] == "el presentador hace un gesto"
    assert "el presentador: senalar" in r.contenido["pasos"][1]["muestra"]
    # un gesto que no está en la lista no pasa la validación (lo guardado en la base se vuelve a validar)
    malo = {**absoluto, "escenas": [{**absoluto["escenas"][0], "gesto": "volar"}]}
    assert any("ese gesto" in x for x in rec.validar(malo, G))


def test_el_guion_le_da_al_modelo_la_lista_de_gestos():
    from app import recorrido as rec
    from app.agente.herramientas import interfaz as hi
    from test_recorrido import _armar
    _, r = _armar(entrada={"op": "guion", "capitulo": "salud"})
    assert r.contenido["gestos"] == rec.GESTOS and "gesto del presentador" in hi.NOTA_GUION
    assert "gesto" in hi.D_PRESENTACION and len(hi.D_PRESENTACION) < 1500


NODE_PUENTE_GESTO = r"""globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const [puente, tarjeta, datos] = process.argv.slice(2);
const P = await import(puente), T = await import(tarjeta);
const fs = await import('node:fs');
const d = JSON.parse(fs.readFileSync(datos, 'utf8'));
const r = d.recorrido;
const malo = { ...r, escenas: r.escenas.map((e, i) => (i === 0 ? { ...e, gesto: 'volar' } : e)) };
console.log(JSON.stringify({
  valido: P.recorridoValido(r)?.escenas.map((e) => e.gesto ?? null) ?? null,
  malo: P.recorridoValido(malo),
  tarjeta: !!T.tarjetaValida(d.tarjeta),
}));
"""


@requiere_node
def test_el_puente_y_la_tarjeta_aceptan_el_gesto(tmp_path):
    import json
    from test_recorrido import PUENTE_JS, TARJETA_JS, _armar
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Gestos", "pasos": [
        {"capitulo": "salud", "paso": "torre", "gesto": "saludar", "dice": "Uno."}, {"gesto": "enumerar", "dice": "Dos."},
        {"dice": "Tres."}]})
    (tmp_path / "datos.json").write_text(json.dumps({"recorrido": r.acciones[0]["recorrido"], "tarjeta": r.acciones[1]},
                                                    ensure_ascii=False), encoding="utf-8")
    (tmp_path / "puente.mjs").write_text(NODE_PUENTE_GESTO, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "puente.mjs"), PUENTE_JS.as_uri(), TARJETA_JS.as_uri(), str(tmp_path / "datos.json")],
                       capture_output=True, text=True, timeout=60, cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o == {"valido": ["saludar", "enumerar", None], "malo": None, "tarjeta": True}, o
