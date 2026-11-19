"""El presentador (web/js/presentador/): la caricatura en 3D que explica lo que narra el asistente, con Node.

* El personaje se arma sin DOM ni WebGL (three en Node, desde web/vendor): mide lo que dice, con los pies en el piso, y
  trae los huesos y las manos que mueve el animador.
* El animador: cada gesto entra y sale (o se sostiene hasta otro), ninguno deja un ángulo que no sea un número, hablar
  abre la boca y callar la cierra, señalar a la izquierda o a la derecha usa el brazo de ese lado, y entrar y salir
  lo muestran y lo ocultan.
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
