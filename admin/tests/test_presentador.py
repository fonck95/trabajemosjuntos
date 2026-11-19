"""El presentador (web/js/presentador/): la caricatura en 3D que explica lo que narra el asistente, con Node.

* El personaje se arma sin DOM ni WebGL (three en Node, desde web/vendor): mide lo que dice, con los pies en el piso, y
  trae los huesos y las manos que mueve el animador.
* El animador: cada gesto entra y sale (o se sostiene hasta otro), ninguno deja un ángulo que no sea un número, hablar
  abre la boca y callar la cierra, señalar a la izquierda o a la derecha usa el brazo de ese lado, y entrar y salir
  lo muestran y lo ocultan. Detrás del subtítulo: entra agachado sin pasarse (y saluda antes de terminar de subir), se
  agacha y sale sin subir antes (con el «gracias» de la despedida, un poco más), se asoma desde donde esté, camina con
  la velocidad y el rumbo que le piden; con movimiento reducido, todo eso en el acto y el cuerpo gira en el acto.
* Los gestos de mostrar y de explicar: ninguno pasa por la T ni mete un dedo en el cuerpo, y la mano que lo hace queda
  arriba del corte; señalar apunta justo, el saludo va y viene cada vez menos, explicar es asimétrico, destacar va
  adelante, comparar sube la mano del proyecto sin cruzar, crecer sube, el puño de construir toca la palma, el dedo
  nuevo de enumerar aparece enseguida, presentar barre con `hasta` y mostrar_panel señala.
* Los gestos de reaccionar, el lema, el cierre y la pausa: tampoco pasan por la T ni meten un dedo en el cuerpo; la mano
  va a la barbilla al pensar, la de preguntar adelante, asentir decrece, el índice de negar se menea sin ceño con los
  dientes, las palmas de calmar e invitar se ven, el pulgar queda a la altura del pecho, celebrar se agacha antes de
  saltar (con movimiento reducido no), las palmas se tocan al aplaudir, las manos del lema se entrelazan delante de la
  polo, la mano se apoya en el pecho, las manos se toman al escuchar y la despedida sigue saludando mientras se agacha;
  los sostenidos siguen vivos y aflojan, pensar termina con su «¡ya está!», el dedo de contar aparece enseguida y en el
  rótulo los gestos son con la cara.
* Lo que no se tiene que leer: ningún brazo estirado en alto con la mano plana (ni la mano abierta hacia lo que está muy
  arriba), ningún puño en alto al saludar, ningún antebrazo dentro del torso, el índice nunca en la muñeca del reloj, el
  brazo que apunta sin saltos, callado la sonrisa con los dientes de la foto, las manos del plano medio sobre el corte y
  la cabeza que no se alza de más.
* El diseño y la luz: las medidas siguen en su rango; la boca con los labios (cerrada, a medias o con cualquier valor)
  y el nivel de la cara (de 0 con la cabeza grande a 1 con la chica, y de vuelta a las tiras de siempre) no dejan nada sin
  número; lo que no recibe luz empieza sin teñir. Las luces siguen a la de la maqueta (`lucesDe`): sin aviso, las de
  siempre; de tarde, desde el lado del sol; al atardecer, el relleno tibio; de noche, más bajas y con el contraluz frío,
  sin saltos entre una hora y otra.
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
  subtítulo, que no lo pasa); los tiempos del resumen. Y lo que corrigió la revisión: no se mueve por poco; señalando
  lo que el dedo no alcanza se para lo más cerca que se puede del panel, y desde lejos se va aunque ya haya cambiado;
  no tapa los títulos de la maqueta si hay un lugar que llegue sin taparlos; si desde ningún lugar que deje leer los
  rótulos (el título y la caja entera) llega el dedo, señala desde lejos con la mano abierta hacia el borde del panel,
  sin taparlos; el rótulo de una seguidilla no cambia con cada panel y de lado no pisa la ficha; a mitad de la escena,
  lo que se ve («Solo 3D», el atlas, la ficha) manda.
* El vidrio del subtítulo que se quitó espera al presentador mientras se agacha detrás (propuesta.html y presentador.js).
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


NODE_DISENO = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { lucesDe } = await import(pathToFileURL(`${dir}/presentador.js`).href);
const r = { errores: [] };
const p = crearPersonaje({ documento: null });
r.medidas = p.medidas;
r.tinte = p.tinte?.value?.getHexString?.() ?? null;
// las tiras de la cara (la suma pesada de sus vértices): sin nivel, con el nivel chico y de vuelta al de cerca
const firmas = () => { const f = []; p.craneo.traverse((m) => { if (m.isMesh && m.renderOrder >= 3) { const a = m.geometry.attributes.position.array; let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * ((i % 7) + 1); f.push(s.toFixed(5)); } }); return f.join(','); };
const finito = () => { let ok = true; p.grupo.traverse((m) => { if (m.isMesh) for (const v of m.geometry.attributes.position.array) if (!Number.isFinite(v)) ok = false; }); return ok; };
const antes = firmas();
try {
  r.nivel = [150, 120, 110, 100, 76, 0, 1e6, undefined, NaN, null, 'x'].map((x) => p.cara.nivel(x));
  p.cara.nivel(60);
  r.cambia = firmas() !== antes;
  p.cara.nivel(150);
  r.vuelve = firmas() === antes;
  // la boca con los labios: cerrada, a medias, fuera de rango o sin número
  for (const labios of [0, 0.3, 1, 2, -1, NaN, undefined, 'x']) for (const abrir of [0, 0.5, 1]) for (const sonrisa of [0, 1]) {
    p.cara.boca.poner({ abrir, ancho: 0.9, sonrisa, labios });
  }
  p.cara.nivel(60);
  p.cara.boca.poner({ abrir: 0.2, labios: 1 });
} catch (e) { r.errores.push(String(e.stack || e).slice(0, 400)); }
r.finito = finito();
p.liberar();
// la luz de la maqueta (visual.js luz()) y las del presentador
const ver = (e) => ({ luz: e.luz.getHexString(), luzI: +e.luzI.toFixed(3), lado: +e.lado.toFixed(3), cielo: e.cielo.getHexString(),
  suelo: e.suelo.getHexString(), hemiI: +e.hemiI.toFixed(3), relleno: e.relleno.getHexString(), rellenoI: +e.rellenoI.toFixed(3),
  contraI: +e.contraI.toFixed(3) });
const tarde = { hora: 'tarde', luz: '#ffe8c6', intensidad: 2.7, cielo: '#cfe0ff', piso: '#7a7458', hemi: 0.42, oscuridad: 0,
  sol: [-0.2, 0.1, 0.9], solFin: [0.571, 0.128, 0.811] };
const atardecer = { ...tarde, hora: 'atardecer', luz: '#ffbd88', intensidad: 2.5, cielo: '#8d9fd0', piso: '#4a3f33', oscuridad: 0.5 };
const noche = { hora: 'noche', luz: '#a9bce6', intensidad: 0.62, cielo: '#5a6ea8', piso: '#26262c', hemi: 0.55, oscuridad: 1,
  sol: [-0.582, 0.748, 0.32] };
r.luces = { nada: ver(lucesDe(null)), vacio: ver(lucesDe({})), tarde: ver(lucesDe(tarde)), atardecer: ver(lucesDe(atardecer)),
  noche: ver(lucesDe(noche)), medio: ver(lucesDe({ ...noche, oscuridad: 0.75 })), porHora: ver(lucesDe({ ...noche, oscuridad: undefined })),
  malo: ver(lucesDe({ luz: 'rojo', cielo: 3, intensidad: NaN, oscuridad: 'x', sol: [NaN, 1, 2], solFin: 'x' })) };
console.log(JSON.stringify(r));
"""


@requiere_node
def test_el_diseno_del_personaje_y_la_luz(tmp_path):
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_DISENO, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=120, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    # las medidas siguen en su rango (las manos ×1.3 no cambian el alto ni el hombro) y nada quedó sin número
    m = r["medidas"]
    assert 2.1 < m["alto"] < 2.4 and abs(m["piso"]) < 0.03 and 1.2 < m["hombro"] < 1.45, m
    assert r["errores"] == [] and r["finito"], r
    # lo que no recibe luz empieza sin teñir (como siempre)
    assert r["tinte"] == "ffffff"
    # el nivel de la cara: 0 con la cabeza grande (o sin número), 1 con la chica, una mezcla en el medio; las tiras cambian
    # con el nivel chico y vuelven a ser las de siempre con el de cerca
    assert r["nivel"] == [0, 0, 0.5, 1, 1, 1, 0, 0, 0, 0, 0], r["nivel"]
    assert r["cambia"] and r["vuelve"], r
    L = r["luces"]
    # sin aviso de la maqueta (el taller, una capa vieja) o con uno que no se entiende: las luces de siempre
    hoy = {"luz": "ffffff", "luzI": 1.9, "lado": -1, "cielo": "ffffff", "suelo": "8a7a70", "hemiI": 1.15, "relleno": "fff1e6",
           "rellenoI": 0.7, "contraI": 0}
    assert L["nada"] == hoy and L["vacio"] == hoy and L["malo"] == hoy, L
    # de tarde: la principal desde el lado del sol donde termina el viaje (a la derecha), tibia, y sin contraluz
    assert L["tarde"]["lado"] == 1 and L["tarde"]["luzI"] == 1.9 and L["tarde"]["contraI"] == 0 and L["tarde"]["luz"] != "ffffff", L["tarde"]
    # al atardecer (el tema oscuro): el relleno tibio y algo menos de luz
    assert L["atardecer"]["relleno"] == "ffd9b0" and L["atardecer"]["luzI"] < 1.9 and L["atardecer"]["contraI"] == 0, L["atardecer"]
    # de noche: desde el lado de la luna, la principal y la hemisférica bajan (al 54 % del piso), el relleno tibio sube a
    # 0.85 y entra un contraluz frío suave (la piel sigue siendo piel: no gris malva); sin `oscuridad`, la hora la dice; a
    # medio camino, a medio camino (sin saltos)
    n = L["noche"]
    assert n["lado"] == -1 and abs(n["luzI"] - 1.9 * 0.55 * 0.54) < 0.01 and abs(n["hemiI"] - 1.15 * 0.55 * 0.54) < 0.01, n
    assert n["relleno"] == "ffd9b0" and n["rellenoI"] == 0.85 and n["contraI"] == 0.25, n
    assert L["porHora"] == n
    assert n["luzI"] < L["medio"]["luzI"] < 1.9 * 0.55 and L["medio"]["contraI"] == 0.125, L["medio"]


NODE_GESTOS = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
const THREE = await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { crearAnimador, MANOS } = await import(pathToFileURL(`${dir}/animador.js`).href);
const p = crearPersonaje({ documento: null });
const A = p.medidas.alto, CORTE = 0.37 * A;
const H = p.huesos;
const mallas = (o) => o.children.filter((c) => c.isMesh && c.geometry?.attributes?.position?.count > 200);
const cuerpo = [...mallas(H.columna), ...mallas(H.cadera), ...mallas(H.musloI), ...mallas(H.musloD)];
p.craneo.traverse((o) => { if (o.isMesh && o.geometry?.attributes?.position?.count > 400) cuerpo.push(o); });
for (const m of cuerpo) { m.material = m.material.clone(); m.material.side = THREE.DoubleSide; }
const rc = new THREE.Raycaster();
const DIRS = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]].map((d) => new THREE.Vector3(...d));
const dentro = (v) => DIRS.filter((d) => { rc.set(v, d); return rc.intersectObjects(cuerpo, false).length % 2 === 1; }).length >= 3;
const palma = { I: p.manos.I.grupo.children.find((c) => c.isMesh), D: p.manos.D.grupo.children.find((c) => c.isMesh) };
const PUNTA = new THREE.Vector3(0, -0.03, 0);
const inv = new THREE.Matrix4();
const en = (o, ofs = null) => (ofs ? o.localToWorld(ofs.clone()) : o.getWorldPosition(new THREE.Vector3())).applyMatrix4(inv);
// un gesto (o una lista de [t, nombre, opciones]) cuadro a cuadro: lo de las manos en el espacio del personaje
function correr(lista, { rumbo = 0, T = 4 } = {}) {
  let k = 7;
  const a = crearAnimador(p, { azar: () => ((k = (k * 16807) % 2147483647) / 2147483647) });
  a.camara = { position: new THREE.Vector3(0, 0.86 * A, 8) };
  p.grupo.position.set(0, 0, 0); p.grupo.rotation.set(0, 0, 0);
  a.girar(rumbo, { ya: true });
  for (let i = 0; i < 36; i++) a.actualizar(1 / 60);
  const serie = [], pen = new Set(), estados = [];
  let enT = 0, j = 0;
  for (let f = 0; f < T * 60; f++) {
    while (j < lista.length && lista[j][0] <= f / 60 + 1e-9) { const [, g, o] = lista[j++]; estados.push(a.gesto(g, o)); }
    a.actualizar(1 / 60);
    p.grupo.updateMatrixWorld(true);
    inv.copy(p.grupo.matrixWorld).invert();
    const s = { t: f / 60, dedos: p.manos.I.dedos.map(([b]) => -b.rotation.z / 1.5) };
    for (const l of ['I', 'D']) {
      s[`m${l}`] = en(H[`muneca${l}`]); s[`p${l}`] = en(palma[l]); s[`i${l}`] = en(p.manos[l].dedos[0][1], PUNTA); s[`s${l}`] = en(H[`hombro${l}`]);
      if (f % 2 === 0) for (const v of [palma[l].getWorldPosition(new THREE.Vector3()), ...p.manos[l].dedos.map(([, q]) => q.localToWorld(PUNTA.clone()))]) if (dentro(v)) pen.add(l);
    }
    // en T: las dos muñecas a la altura del hombro, afuera y sin adelanto
    if (['I', 'D'].every((l) => Math.abs(s[`m${l}`].y - s[`s${l}`].y) <= 0.08 && Math.abs(s[`m${l}`].x - s[`s${l}`].x) >= 0.45 && s[`m${l}`].z - s[`s${l}`].z < 0.2)) enT++;
    serie.push(s);
  }
  return { serie, pen: [...pen], enT, estado: a.estado(), estados, a };
}
const media = (xs) => xs.reduce((x, y) => x + y, 0) / xs.length;
const tramo = (serie, t0, t1) => serie.filter((s) => s.t >= t0 && s.t < t1);
const r3 = (x) => Math.round(x * 1000) / 1000;
const r = { manos: ['ok', 'ele', 'entrelazada', 'canto', 'llama'].every((m) => Array.isArray(MANOS[m]) && MANOS[m].length === 5), gestos: {} };
const PUNTO = new THREE.Vector3(-1.6, 1.45, 0.6);
const LISTA = ['saludar', 'senalar', 'presentar', 'indicar', 'mirar_maqueta', 'explicar', 'destacar', 'comparar', 'enumerar', 'crecer', 'grande', 'detalle', 'construir'];
for (const g of LISTA) {
  const apunta = ['senalar', 'presentar', 'indicar', 'mirar_maqueta'].includes(g);
  for (const variante of [0, 1]) {
    const x = correr([[0, g, { punto: apunta ? PUNTO : undefined, variante }]], { rumbo: apunta ? -0.35 : 0 });
    // lo más bajo de la mano que hace el gesto mientras está entero (las manos atrás de mirar la maqueta, aparte)
    const enGesto = tramo(x.serie, 0.9, 1.8);
    r.gestos[`${g}#${variante}`] = { T: x.enT, pen: x.pen, bajo: r3(Math.min(...enGesto.map((s) => Math.max(s.pI.y, s.pD.y))) - CORTE) };
  }
}
// señalar: la recta del hombro a la punta del índice cae en el punto
{
  const x = correr([[0, 'senalar', { punto: PUNTO }]], { rumbo: -0.35, T: 2 });
  p.grupo.updateMatrixWorld(true);
  const s = x.serie[x.serie.length - 1], P = PUNTO.clone().applyMatrix4(inv.copy(p.grupo.matrixWorld).invert());
  r.senalar = r3((Math.acos(s.iD.clone().sub(s.sD).normalize().dot(P.sub(s.sD).normalize())) * 180) / Math.PI);
}
// saludar: el antebrazo va y viene (los extremos del codo, cada vez menos)
{
  const x = correr([[0, 'saludar', {}]], { T: 2.6 });
  const cod = x.serie.map((s) => s.mD.x).slice(33);
  const ex = [];
  for (let i = 1; i < cod.length - 1; i++) if ((cod[i] - cod[i - 1]) * (cod[i + 1] - cod[i]) < 0) ex.push(cod[i]);
  const amp = ex.slice(1).map((v, i) => Math.abs(v - ex[i]));
  r.saludar = { semiciclos: amp.length, primero: r3(amp[0]), ultimo: r3(amp[Math.min(amp.length - 1, 4)]), arriba: r3(Math.max(...x.serie.map((s) => s.pD.y))) };
}
// explicar: las muñecas a alturas distintas
{ const x = correr([[0, 'explicar', { variante: 0 }]]); const h = tramo(x.serie, 0.8, 2.8); r.explicar = r3(Math.abs(media(h.map((s) => s.mI.y)) - media(h.map((s) => s.mD.y)))); }
// destacar: el índice delante del hombro
{ const x = correr([[0, 'destacar', { variante: 0 }]]); r.destacar = r3(Math.max(...tramo(x.serie, 0.6, 1.8).map((s) => s.iD.z - s.sD.z))); }
// comparar: «con el proyecto» más alta que «hoy» y las manos nunca se cruzan
{
  const x = correr([[0, 'comparar', {}]]);
  r.comparar = { masAlta: r3(media(tramo(x.serie, 2.4, 3.0).map((s) => s.mD.y)) - media(tramo(x.serie, 0.9, 1.4).map((s) => s.mI.y))),
    cruzan: x.serie.filter((s) => s.pD.x > s.pI.x - 0.02).length };
}
// crecer: la que sube termina más alta que la otra
{ const x = correr([[0, 'crecer', { variante: 0 }]]); const h = tramo(x.serie, 2.0, 2.4); r.crecer = r3(media(h.map((s) => s.mD.y)) - media(h.map((s) => s.mI.y))); }
// construir: el puño toca la palma en cada golpe (los mínimos de su distancia)
{
  const x = correr([[0, 'construir', {}]], { T: 2.4 });
  const d = x.serie.map((s) => s.pI.distanceTo(s.pD));
  const min = [];
  for (let i = 1; i < d.length - 1; i++) if (d[i] < d[i - 1] && d[i] <= d[i + 1] && d[i] < 0.12) min.push(r3(d[i]));
  r.construir = min;
}
// enumerar: el dedo nuevo aparece enseguida (cuando se pasa a la mitad de estirado) y la otra mano la acompaña sin
// tocarla: el índice derecho nunca va a la muñeca izquierda, la del reloj («se acabó el tiempo»)
{
  const x = correr([[0, 'enumerar', { n: 1, sostener: true }], [2, 'enumerar', { n: 2, seguir: true }], [3.5, 'enumerar', { n: 3, seguir: true }]], { T: 4.5 });
  const aparece = [2, 3.5].map((t0, k) => { const i = x.serie.findIndex((s) => s.t >= t0 && s.dedos[k + 1] < 0.5); return r3(x.serie[i].t - t0); });
  const reloj = Math.min(...x.serie.slice(20).map((s) => s.iD.distanceTo(s.mI)));
  r.enumerar = { aparece, reloj: r3(reloj), sigue: x.estado.gesto };
}
// presentar con `hasta`: barre la palma de un punto al otro (más largo); mostrar_panel señala
{
  // (de un punto lejano sobre el hombro, la fila de los años, a uno a la altura del hombro: el cronograma)
  const desde = new THREE.Vector3(-2.7, 2.2, 0.3), hasta = new THREE.Vector3(-1.2, 1.8, 1.2);
  const x = correr([[0, 'presentar', { punto: desde, hasta, variante: 0 }]], { rumbo: -0.35, T: 2.5 });
  p.grupo.updateMatrixWorld(true);
  inv.copy(p.grupo.matrixWorld).invert();
  const ang = (s, q) => (Math.acos(s.pD.clone().sub(s.sD).normalize().dot(q.clone().applyMatrix4(inv).sub(s.sD).normalize())) * 180) / Math.PI;
  const s1 = x.serie[Math.round(0.8 * 60)], s2 = x.serie[x.serie.length - 1];
  r.barrido = { dur: x.estados[0], antes: [r3(ang(s1, desde)), r3(ang(s1, hasta))], despues: [r3(ang(s2, desde)), r3(ang(s2, hasta))] };
  const m = correr([[0, 'mostrar_panel', { punto: PUNTO }]], { rumbo: -0.35, T: 0.5 });
  r.mostrarPanel = m.estado.gesto;
}
p.liberar();
console.log(JSON.stringify(r));
"""


@requiere_node
def test_los_gestos_de_mostrar_y_explicar(tmp_path):
    """Los gestos de mostrar y de explicar (etapa 7a): ninguno pasa por la T ni mete un dedo en el cuerpo; cada uno
    cumple lo suyo (señalar apunta justo, el saludo decrece, explicar es asimétrico, destacar va adelante, comparar sube
    la mano del proyecto sin cruzar, crecer sube, el puño de construir toca la palma, el dedo de enumerar aparece
    enseguida, presentar barre con `hasta`, mostrar_panel señala)."""
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_GESTOS, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=180, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["manos"]
    for g, x in r["gestos"].items():
        assert x["T"] == 0 and x["pen"] == [], (g, x)
        # la mano del gesto, arriba del corte del americano (las manos tomadas atrás de mirar la maqueta van detrás del
        # cuerpo)
        if not g.startswith("mirar_maqueta#0"):
            assert x["bajo"] > 0, (g, x)
    assert r["senalar"] < 1.5, r["senalar"]
    s = r["saludar"]
    assert s["semiciclos"] >= 4 and s["primero"] > s["ultimo"] and s["arriba"] > 1.8, s
    assert r["explicar"] >= 0.06, r["explicar"]
    assert r["destacar"] >= 0.25, r["destacar"]
    assert r["comparar"]["masAlta"] >= 0.15 and r["comparar"]["cruzan"] == 0, r["comparar"]
    assert r["crecer"] >= 0.35, r["crecer"]
    assert len(r["construir"]) >= 3 and all(d < 0.09 for d in r["construir"][:3]), r["construir"]
    e = r["enumerar"]
    assert all(t <= 0.12 for t in e["aparece"]) and e["reloj"] >= 0.15 and e["sigue"] == "enumerar", e
    b = r["barrido"]
    # (al llegar la palma está en el primero; al terminar de barrer, mucho más cerca del segundo)
    assert b["dur"] >= 3.4 and b["antes"][0] < b["antes"][1] and b["despues"][1] < b["antes"][1] - 8, b
    assert r["mostrarPanel"] == "senalar"


NODE_LECTURAS = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
const THREE = await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { crearAnimador, GESTOS_AGENTE, VARIANTES } = await import(pathToFileURL(`${dir}/animador.js`).href);
const p = crearPersonaje({ documento: null });
const A = p.medidas.alto, H = p.huesos;
const mallas = (o) => o.children.filter((c) => c.isMesh && c.geometry?.attributes?.position?.count > 200);
const torso = [...mallas(H.columna), ...mallas(H.cadera)];
for (const m of torso) { m.material = m.material.clone(); m.material.side = THREE.DoubleSide; }
const rc = new THREE.Raycaster();
const DIRS = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]].map((d) => new THREE.Vector3(...d));
const dentro = (v) => DIRS.filter((d) => { rc.set(v, d); return rc.intersectObjects(torso, false).length % 2 === 1; }).length >= 3;
const W = (o) => new THREE.Vector3().setFromMatrixPosition(o.matrixWorld);
const palma = { I: p.manos.I.grupo.children.find((c) => c.isMesh), D: p.manos.D.grupo.children.find((c) => c.isMesh) };
const dedosDe = (l) => p.manos[l].dedos.map(([b]) => -b.rotation.z / 1.5).reduce((x, y) => x + y, 0) / 4;
const r3 = (x) => Math.round(x * 1000) / 1000;
// (cada animador nuevo parte del personaje como se armó: la cadera y el cuerpo en su lugar)
const cadera0 = H.cadera.position.clone(), cuerpo0 = p.cuerpo.position.clone();
function nuevo(rumbo = 0, plano = null) {
  H.cadera.position.copy(cadera0); p.cuerpo.position.copy(cuerpo0);
  let k = 7;
  const a = crearAnimador(p, { azar: () => ((k = (k * 16807) % 2147483647) / 2147483647) });
  a.camara = { position: new THREE.Vector3(0, 0.86 * A, 8) };
  p.grupo.position.set(0, 0, 0); p.grupo.rotation.set(0, 0, 0);
  if (plano) a.plano = plano;
  a.girar(rumbo, { ya: true });
  for (let i = 0; i < 36; i++) a.actualizar(1 / 60);
  return a;
}
// cada cuadro de un brazo: la muñeca sobre el hombro, lo que dobla el codo (°), su elevación (°) y los dedos
function brazo(l) {
  const s = W(H[`hombro${l}`]), c = W(H[`codo${l}`]), m = W(H[`muneca${l}`]);
  const flex = (Math.acos(Math.min(1, c.clone().sub(s).normalize().dot(m.clone().sub(c).normalize()))) * 180) / Math.PI;
  const elev = (Math.asin(Math.max(-1, Math.min(1, m.clone().sub(s).normalize().y))) * 180) / Math.PI;
  return { sobre: m.y - s.y, flex, elev, dedos: dedosDe(l), s, c, m };
}
const enAlto = (b) => b.sobre > 0.15 && b.flex < 50 && b.dedos < 0.15;
const r = { alto: {}, antebrazo: {}, reloj: {}, puno: {} };
const PUNTO = new THREE.Vector3(-1.6, 1.45, 0.6);
for (const g of GESTOS_AGENTE) for (const rumbo of [0, -0.5]) for (let v = 0; v < (VARIANTES[g] || 1); v++) {
  const a = nuevo(rumbo);
  const apunta = ['senalar', 'presentar', 'mostrar_panel', 'mirar_maqueta'].includes(g);
  const d = a.gesto(g, { punto: apunta ? PUNTO : undefined, variante: v, n: 3 });
  const T = Math.min(4, Number.isFinite(d) ? d + 0.3 : 4), clave = `${g}#${v}@${rumbo}`;
  let alto = 0, ante = 0, reloj = 9, puno = 0;
  for (let f = 0; f < T * 60; f++) {
    a.actualizar(1 / 60);
    p.grupo.updateMatrixWorld(true);
    for (const l of ['I', 'D']) {
      const b = brazo(l);
      if (enAlto(b)) alto++;
      if (['saludar', 'despedirse'].includes(g) && palma[l].getWorldPosition(new THREE.Vector3()).y > b.s.y - 0.1 && b.dedos > 0.15) puno++;
      if (f % 6 === 0 && f > 20) { let n = 0; for (let i = 0; i <= 10; i++) if (dentro(b.c.clone().lerp(b.m, i / 10))) n++; ante = Math.max(ante, n); }
    }
    // (el índice derecho estirado nunca va a la muñeca izquierda, la del reloj)
    const punta = p.manos.D.dedos[0][1].localToWorld(new THREE.Vector3(0, -0.044, 0));
    if (f > 20 && -p.manos.D.dedos[0][0].rotation.z / 1.5 < 0.3) reloj = Math.min(reloj, punta.distanceTo(W(H.munecaI)));
  }
  r.alto[clave] = alto; r.antebrazo[clave] = ante; r.reloj[clave] = r3(reloj); if (puno) r.puno[clave] = puno;
}
// pensar: el brazo que sostiene el codo va por delante del vientre (el húmero, a lo sumo como en reposo)
{
  const a = nuevo();
  a.gesto('pensar', { sostener: true });
  let hum = 0;
  for (let f = 0; f < 8 * 60; f++) {
    a.actualizar(1 / 60);
    if (f % 30) continue;
    p.grupo.updateMatrixWorld(true);
    const b = brazo('I');
    let n = 0; for (let i = 0; i <= 10; i++) if (dentro(b.s.clone().lerp(b.c, i / 10))) n++;
    hum = Math.max(hum, n);
  }
  r.pensarHumero = hum;
}
// la mano abierta hacia lo que está muy arriba (indicar, presentar): nunca el brazo en alto
r.arriba = {};
for (const g of ['indicar', 'presentar']) for (const [rumbo, pt] of [[0.35, [1.8, 2.3, 0.6]], [0.35, [2.5, 3.4, 0.6]], [-0.35, [-0.9, 2.8, 0.6]]]) {
  const a = nuevo(rumbo);
  a.gesto(g, { punto: new THREE.Vector3(...pt), sostener: true });
  let peor = -9, alto = 0;
  for (let f = 0; f < 3 * 60; f++) {
    a.actualizar(1 / 60);
    if (f < 60) continue;
    p.grupo.updateMatrixWorld(true);
    for (const l of ['I', 'D']) { const b = brazo(l); peor = Math.max(peor, b.sobre); if (enAlto(b)) alto++; }
  }
  r.arriba[`${g}@${pt}`] = { sobre: r3(peor), alto };
}
// apuntar sostenido, hablando (la mirada mueve el pecho): la elevación del brazo cambia de a poco (nunca 30° de golpe)
r.salto = {};
for (const [g, rumbo, pt] of [['indicar', 0, [-3, 1.6, 1]], ['senalar', 0, [-2.5, 1.0, 0]], ['presentar', 0, [-3.5, 3.0, 0]], ['indicar', 0.35, [-2.5, 2.2, 0]]]) {
  const a = nuevo(rumbo);
  const P = new THREE.Vector3(...pt);
  a.gesto(g, { punto: P, sostener: true });
  a.hablar(5, { texto: 'Aquí ven el puesto de salud. Atiende a toda la vereda. Tiene consultorio y farmacia' });
  p.grupo.updateMatrixWorld(true);
  const l = (() => { const v = P.clone(); p.grupo.worldToLocal(v); return v.x >= 0 ? 'I' : 'D'; })();
  let antes = null, peor = 0;
  for (let f = 0; f < 5 * 60; f++) {
    a.actualizar(1 / 60);
    if (f < 60) continue;
    p.grupo.updateMatrixWorld(true);
    const e = brazo(l).elev;
    if (antes !== null) peor = Math.max(peor, Math.abs(e - antes));
    antes = e;
  }
  r.salto[`${g}@${pt}`] = r3(peor);
}
// callado en reposo, la sonrisa de la foto con los dientes de arriba (los labios entreabiertos); pensando, cerrada
{
  const a = nuevo();
  a.hablar(1, { texto: 'Hola a todos.' });
  for (let i = 0; i < 180; i++) a.actualizar(1 / 60);
  r.labiosReposo = a.estado().boca.labios;
  a.gesto('pensar', { sostener: true });
  for (let i = 0; i < 90; i++) a.actualizar(1 / 60);
  r.labiosPensar = a.estado().boca.labios;
}
// el plano medio (cerca, el busto): las manos de la casa, de invitar, de escuchar y de calmar quedan sobre el corte
{
  const CORTE_MEDIO = 0.4 * A;
  r.medio = {};
  for (const g of [null, 'invitar', 'escuchar', 'calmar']) {
    const a = nuevo(0, 'medio');
    if (g) a.gesto(g, { sostener: g !== 'calmar' });
    for (let i = 0; i < 90; i++) a.actualizar(1 / 60);
    p.grupo.updateMatrixWorld(true);
    // lo más bajo de las dos manos (la palma y la punta de los dedos), sobre el corte, en fracciones del alto
    const bajo = Math.min(...['I', 'D'].flatMap((l) => [palma[l].getWorldPosition(new THREE.Vector3()).y,
      ...p.manos[l].dedos.map(([, q]) => q.localToWorld(new THREE.Vector3(0, -0.03, 0)).y)]));
    r.medio[g || 'casa'] = r3((bajo - CORTE_MEDIO) / A);
  }
}
// mirando algo de arriba, la cabeza se alza poco (lo demás, los ojos)
{
  const a = nuevo(0.3);
  a.mirarA(new THREE.Vector3(-1, 4.5, 0.6));
  for (let i = 0; i < 90; i++) a.actualizar(1 / 60);
  p.grupo.updateMatrixWorld(true);
  const fwd = new THREE.Vector3(0, 0, 1).transformDirection(H.cabeza.matrixWorld);
  r.cabezaArriba = r3(Math.asin(fwd.y));
}
// en el celular (el busto, chico: contar por lugares), cada número con la palma frente al pecho, dentro del ancho de los
// hombros (el lienzo del busto va pegado al borde de la pantalla: abierta hacia afuera, la mano del 3 se salía) y hacia
// la sala; la otra mano, quieta abajo aunque hable (las dos palmas a los lados del pecho no dejaban leer el número)
{
  const a = nuevo(0, 'medio');
  a.tamano(200, { celular: true });
  a.hablar(9, { texto: 'En resumen. Uno: la torre. Dos: el agua para todos. Tres: vivienda nueva y mejorada.' });
  for (let i = 0; i < 30; i++) a.actualizar(1 / 60);
  r.chico = [];
  for (const n of [1, 2, 3]) {
    a.gesto('contar', n === 1 ? { n, sostener: true } : { n, seguir: true });
    const l = n === 3 ? 'I' : 'D', o = n === 3 ? 'D' : 'I', yOtra = [];
    for (let i = 0; i < 90; i++) {
      a.actualizar(1 / 60);
      p.grupo.updateMatrixWorld(true);
      if (i >= 45) yOtra.push(palma[o].getWorldPosition(new THREE.Vector3()).y);
    }
    const pm = palma[l].getWorldPosition(new THREE.Vector3());
    const normal = new THREE.Vector3(0, 0, 1).transformDirection(palma[l].matrixWorld);
    r.chico.push({ n, lado: l, x: r3(pm.x / A), y: r3(pm.y / A), otra: r3(Math.max(...yOtra) / A),
      mueve: r3((Math.max(...yOtra) - Math.min(...yOtra)) / A), chico: a.estado().chico });
  }
}
p.liberar();
console.log(JSON.stringify(r));
"""


@requiere_node
def test_los_gestos_no_se_leen_mal(tmp_path):
    """Lo que no se tiene que leer (los jueces de animación y de diseño): ningún gesto deja el brazo estirado en alto con
    la mano plana (se leería como un saludo de brazo en alto; el saludo y la despedida van con la palma a la sala y la mano
    ya abierta al subir: nunca un puño en alto), la mano abierta hacia lo que está muy arriba no sube más de ~11°, ningún
    antebrazo queda dentro del torso (pensar sostiene el codo por delante del vientre), el índice derecho nunca va a la
    muñeca del reloj (contar no dice «se acabó el tiempo»), el brazo que apunta no salta de una solución a otra, callado
    sonríe con los dientes de arriba como en la foto, en el plano medio las manos quedan sobre el corte y la cabeza no se
    alza de más para mirar arriba."""
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_LECTURAS, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=300, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    # el brazo en alto (la muñeca 0.15 sobre el hombro, el codo casi recto y la mano plana): ninguno, salvo el saludo y la
    # despedida, que son eso con la palma a la sala; y esos dos nunca suben la mano cerrada
    altos = {k: v for k, v in r["alto"].items() if v and not k.startswith(("saludar", "despedirse"))}
    assert altos == {}, altos
    assert r["puno"] == {}, r["puno"]
    for k, x in r["arriba"].items():
        assert x["alto"] == 0 and x["sobre"] < 0.1, (k, x)
    # ningún antebrazo dentro del torso; pensar, el brazo de abajo por delante (el húmero, como en reposo)
    assert all(v <= 3 for v in r["antebrazo"].values()), {k: v for k, v in r["antebrazo"].items() if v > 3}
    assert r["pensarHumero"] <= 7, r["pensarHumero"]
    assert all(v >= 0.15 for v in r["reloj"].values()), {k: v for k, v in r["reloj"].items() if v < 0.15}
    assert all(v < 3 for v in r["salto"].values()), r["salto"]
    assert 0.25 <= r["labiosReposo"] <= 0.5 and r["labiosPensar"] > 0.9, (r["labiosReposo"], r["labiosPensar"])
    assert r["medio"]["casa"] >= 0.04 and r["medio"]["invitar"] >= 0.1 and min(r["medio"].values()) > 0.02, r["medio"]
    assert r["cabezaArriba"] < 0.25, r["cabezaArriba"]
    # contar en el celular: el 1 a la izquierda de la pantalla, el 2 al centro y el 3 a la derecha, todos dentro de los
    # hombros (±0.2 del alto; antes ±0.26, y en el cierre del celular la mano del 3 salía del lienzo); la otra mano,
    # quieta abajo mientras habla
    ch = r["chico"]
    assert all(c["chico"] for c in ch) and [c["lado"] for c in ch] == ["D", "D", "I"], ch
    assert ch[0]["x"] < ch[1]["x"] < ch[2]["x"] and all(abs(c["x"]) <= 0.2 for c in ch) and abs(ch[1]["x"]) <= 0.06, ch
    assert all(c["otra"] <= 0.53 and c["mueve"] <= 0.01 for c in ch), ch


NODE_REACCIONES = r"""import { register } from 'node:module';
import { pathToFileURL } from 'node:url';
const [cargador, dir] = process.argv.slice(2);
register(pathToFileURL(cargador).href);
const THREE = await import('three');
const { crearPersonaje } = await import(pathToFileURL(`${dir}/personaje.js`).href);
const { crearAnimador, ARTICULACIONES, CARAS } = await import(pathToFileURL(`${dir}/animador.js`).href);
const p = crearPersonaje({ documento: null });
const A = p.medidas.alto, CORTE = 0.37 * A;
const H = p.huesos;
const mallas = (o) => o.children.filter((c) => c.isMesh && c.geometry?.attributes?.position?.count > 200);
const torso = mallas(H.columna);
const cuerpo = [...torso, ...mallas(H.cadera), ...mallas(H.musloI), ...mallas(H.musloD)];
p.craneo.traverse((o) => { if (o.isMesh && o.geometry?.attributes?.position?.count > 400) cuerpo.push(o); });
for (const m of cuerpo) { m.material = m.material.clone(); m.material.side = THREE.DoubleSide; }
const rc = new THREE.Raycaster();
const DIRS = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]].map((d) => new THREE.Vector3(...d));
const dentro = (v) => DIRS.filter((d) => { rc.set(v, d); return rc.intersectObjects(cuerpo, false).length % 2 === 1; }).length >= 3;
const palma = { I: p.manos.I.grupo.children.find((c) => c.isMesh), D: p.manos.D.grupo.children.find((c) => c.isMesh) };
const PUNTA = new THREE.Vector3(0, -0.03, 0);
const inv = new THREE.Matrix4();
const en = (o, ofs = null) => (ofs ? o.localToWorld(ofs.clone()) : o.getWorldPosition(new THREE.Vector3())).applyMatrix4(inv);
// la barbilla (en el espacio de la cabeza, medida de pie) y lo que separa una palma de la polo (hacia el centro del pecho)
p.grupo.updateMatrixWorld(true);
const cj = new THREE.Box3().setFromObject(p.craneo);
const barbilla = new THREE.Vector3((cj.min.x + cj.max.x) / 2, cj.min.y + 0.03, cj.max.z - 0.08).applyMatrix4(H.cabeza.matrixWorld.clone().invert());
const aPolo = (pa) => { const c = H.pecho.getWorldPosition(new THREE.Vector3()); c.y = pa.y; c.z = Math.min(c.z, pa.z - 0.001); rc.set(pa, c.sub(pa).normalize()); const h = rc.intersectObjects(torso, false); return h.length ? h[0].distance : 9; };
const nuevo = (o = {}) => {
  let k = 7;
  const a = crearAnimador(p, { azar: () => ((k = (k * 16807) % 2147483647) / 2147483647), ...o });
  a.camara = { position: new THREE.Vector3(0, 0.86 * A, 8) };
  p.grupo.position.set(0, 0, 0); p.grupo.rotation.set(0, 0, 0);
  for (let i = 0; i < 36; i++) a.actualizar(1 / 60);
  return a;
};
// un gesto (o una lista de [t, nombre, opciones]) cuadro a cuadro: las manos en el espacio del personaje, la cara y el cuerpo
function correr(lista, { T = 3.4, a = nuevo(), salir = null } = {}) {
  const serie = [], pen = new Set(), cara = [];
  const poner = p.cara.boca.poner, ceja = p.cara.cejas[0].poner;
  let labios = 1;
  p.cara.boca.poner = (o) => { labios = o.labios ?? 0; poner(o); };
  p.cara.cejas[0].poner = (o) => { cara.push([o.ceno || 0, labios]); ceja(o); };
  let enT = 0, j = 0;
  for (let f = 0; f < T * 60; f++) {
    while (j < lista.length && lista[j][0] <= f / 60 + 1e-9) { const [, g, o] = lista[j++]; if (g === 'salir') a.salir(null, o); else a.gesto(g, o); }
    a.actualizar(1 / 60);
    p.grupo.updateMatrixWorld(true);
    inv.copy(p.grupo.matrixWorld).invert();
    const s = { t: f / 60, dedos: p.manos.I.dedos.map(([b]) => -b.rotation.z / 1.5), y: p.cuerpo.position.y,
      rodillas: Math.min(H.rodillaI.rotation.x, H.rodillaD.rotation.x),
      cabX: new THREE.Euler().setFromQuaternion(H.cabeza.quaternion, 'YXZ').x + new THREE.Euler().setFromQuaternion(H.cuello.quaternion, 'YXZ').x,
      barb: en(H.cabeza, barbilla) };
    for (const l of ['I', 'D']) {
      s[`m${l}`] = en(H[`muneca${l}`]); s[`p${l}`] = en(palma[l]); s[`i${l}`] = en(p.manos[l].dedos[0][1], PUNTA); s[`s${l}`] = en(H[`hombro${l}`]);
      s[`c${l}`] = en(H[`codo${l}`]);
      const q = p.manos[l].grupo.getWorldQuaternion(new THREE.Quaternion());
      s[`n${l}`] = new THREE.Vector3(l === 'D' ? 1 : -1, 0, 0).applyQuaternion(q);
      if (f % 3 === 0) for (const v of [palma[l].getWorldPosition(new THREE.Vector3()), ...p.manos[l].dedos.map(([, q2]) => q2.localToWorld(PUNTA.clone()))]) if (dentro(v)) pen.add(l);
    }
    s.poloD = aPolo(palma.D.getWorldPosition(new THREE.Vector3()));
    s.pechoD = H.pecho.worldToLocal(palma.D.getWorldPosition(new THREE.Vector3()));
    if (['I', 'D'].every((l) => Math.abs(s[`m${l}`].y - s[`s${l}`].y) <= 0.08 && Math.abs(s[`m${l}`].x - s[`s${l}`].x) >= 0.45 && s[`m${l}`].z - s[`s${l}`].z < 0.2)) enT++;
    serie.push(s);
  }
  p.cara.boca.poner = poner; p.cara.cejas[0].poner = ceja;
  return { serie, pen: [...pen], enT, cara, a };
}
const media = (xs) => xs.reduce((x, y) => x + y, 0) / xs.length;
const tramo = (serie, t0, t1) => serie.filter((s) => s.t >= t0 && s.t < t1);
const r3 = (x) => Math.round(x * 1000) / 1000;
const r = { gestos: {} };
// ninguno pasa por la T ni mete un dedo en el cuerpo; la mano que lo hace queda arriba del corte
for (const g of ['pensar', 'preguntar', 'asentir', 'negar', 'calmar', 'aprobar', 'celebrar', 'aplaudir', 'juntos', 'corazon', 'invitar', 'despedirse', 'escuchar', 'contar']) {
  for (const variante of [0, 1]) {
    const x = correr([[0, g, { variante, n: 2 }]], { T: 3.2 });
    const h = tramo(x.serie, 0.9, 1.8);
    r.gestos[`${g}#${variante}`] = { T: x.enT, pen: x.pen, bajo: r3(Math.min(...h.map((s) => Math.max(s.pI.y, s.pD.y))) - CORTE) };
  }
}
// pensar: la mano a la barbilla (la palma y el índice) y el otro brazo bajo el codo; preguntar: la mano adelante
{
  const x = correr([[0, 'pensar', { sostener: true }]], { T: 3 });
  const h = tramo(x.serie, 1, 3);
  r.pensar = { palma: r3(Math.max(...h.map((s) => s.pD.distanceTo(s.barb)))), indice: r3(Math.max(...h.map((s) => s.iD.distanceTo(s.barb)))),
    codo: r3(Math.max(...h.map((s) => s.pI.distanceTo(s.cD)))) };
  const y = correr([[0, 'preguntar', {}]], { T: 2 });
  r.preguntar = r3(Math.max(...tramo(y.serie, 0.6, 2).map((s) => s.pD.z - s.sD.z)));
}
// asentir: cada vez menos, baja más rápido de lo que sube; negar: el índice se menea de lado y nunca el ceño con los dientes
{
  const x = correr([[0, 'asentir', { variante: 0 }]], { T: 1.4 });
  const c = x.serie.map((s) => s.cabX), ex = [];
  for (let i = 1; i < c.length - 1; i++) if ((c[i] - c[i - 1]) * (c[i + 1] - c[i]) < 0 && Math.abs(c[i] - (ex.at(-1)?.[1] ?? 1e9)) > 0.01) ex.push([i, c[i]]);
  const picos = [];
  for (let k = 1; k < ex.length - 1; k++) if (ex[k][1] > ex[k - 1][1]) picos.push({ amp: r3(ex[k][1] - ex[k - 1][1]), baja: (ex[k][0] - ex[k - 1][0]) / 60, sube: (ex[k + 1][0] - ex[k][0]) / 60 });
  r.asentir = picos;
  const y = correr([[0, 'negar', { variante: 0 }]], { T: 2.4 });
  const xs = tramo(y.serie, 0.45, 1.5).map((s) => s.iD.x);
  r.negar = { meneo: r3(Math.max(...xs) - Math.min(...xs)), cenoConDientes: y.cara.some(([cn, lb]) => cn > 0.45 && lb < 0.5) };
}
// calmar e invitar: las palmas a la vista desde la sala; aprobar: el pulgar a la altura del pecho
{
  const zs = (x) => r3(Math.min(...tramo(x.serie, 0.9, 1.8).flatMap((s) => [s.nI.z, s.nD.z])));
  r.calmar = zs(correr([[0, 'calmar', {}]], { T: 2 }));
  r.invitar = zs(correr([[0, 'invitar', {}]], { T: 2 }));
  r.aprobar = r3(Math.min(...tramo(correr([[0, 'aprobar', {}]], { T: 1.5 }).serie, 0.5, 1.5).map((s) => s.pD.y)));
}
// celebrar: se agacha antes de saltar (y con movimiento reducido, ni se agacha ni salta)
{
  const x = correr([[0, 'celebrar', {}]], { T: 1.2 });
  const y = correr([[0, 'celebrar', {}]], { T: 1.2, a: nuevo({ reducido: true }) });
  r.celebrar = { rodillas: r3(Math.max(...tramo(x.serie, 0.1, 0.38).map((s) => s.rodillas))), salto: r3(Math.max(...x.serie.map((s) => s.y))),
    reducido: r3(Math.max(...y.serie.map((s) => s.y))) };
}
// aplaudir: las palmas se tocan en cada golpe; juntos: las manos entrelazadas a 1 s, delante de la polo; corazón: la palma
// apoyada en el pectoral izquierdo; escuchar: las manos tomadas
{
  const minimos = (serie) => { const d = serie.map((s) => s.pI.distanceTo(s.pD)), m = []; for (let i = 1; i < d.length - 1; i++) if (d[i] < d[i - 1] && d[i] <= d[i + 1]) m.push(r3(d[i])); return m; };
  r.aplaudir = minimos(correr([[0, 'aplaudir', {}]], { T: 2.2 }).serie);
  const j = correr([[0, 'juntos', {}]], { T: 2.2 });
  r.juntos = { a1s: r3(j.serie[60].pI.distanceTo(j.serie[60].pD)), delante: r3(Math.min(...tramo(j.serie, 1.2, 2.2).map((s) => Math.min(s.pI.z, s.pD.z) - 0.165))) };
  const c = tramo(correr([[0, 'corazon', {}]], { T: 2.2 }).serie, 0.9, 2.2);
  r.corazon = { polo: r3(Math.max(...c.map((s) => s.poloD))), x: r3(Math.min(...c.map((s) => s.pechoD.x))) };
  r.escuchar = r3(Math.max(...tramo(correr([[0, 'escuchar', {}]], { T: 3 }).serie, 1, 3).map((s) => s.pI.distanceTo(s.pD))));
}
// despedirse con la salida: la mano sigue arriba mientras él se agacha
{
  const a = nuevo();
  const x = correr([[0, 'despedirse', { dur: 1.1, entra: 0.2, saliendo: true }], [0, 'salir', { hondo: 1.57, gracias: true }]], { T: 1, a });
  const rel = x.serie.map((s) => s.pD.y - s.y);
  const empieza = x.serie.find((s) => s.y < -0.01).t;
  r.despedirse = { arriba: r3(Math.max(...rel)), empieza: r3(empieza), bajaAntes: rel.some((v, i) => x.serie[i].t <= empieza + 0.3 && i > 0 && v < rel[i - 1] - 0.02) };
}
// los sostenidos siguen vivos y a los 8 s aflojan; al soltar pensar, «¡ya está!» (y no queda más de 1 s)
{
  r.sostenidos = {};
  for (const g of ['pensar', 'escuchar', 'invitar']) {
    const a = nuevo();
    a.gesto(g, { sostener: true });
    const foto = () => ARTICULACIONES.map((j) => H[j].quaternion.clone());
    const correrS = (s) => { for (let i = 0; i < Math.round(s * 60); i++) a.actualizar(1 / 60); };
    correrS(2); const f2 = foto(); correrS(2); const f4 = foto(); correrS(4);
    const dif = Math.max(...f2.map((q, i) => 2 * Math.acos(Math.min(1, Math.abs(q.dot(f4[i]))))));
    const rel = a.estado().relajada;
    a.detenerGesto();
    const soltando = a.estado().soltando;
    correrS(1);
    r.sostenidos[g] = { dif: r3(dif), relajada: rel, soltando, despues: a.estado().gesto };
  }
}
// contar: el dedo nuevo aparece enseguida; el rótulo: con la cara, sin mover los brazos (señalar no hace nada)
{
  const x = correr([[0, 'contar', { n: 1, sostener: true }], [1.5, 'contar', { n: 2, seguir: true }], [2.8, 'contar', { n: 3, seguir: true }]], { T: 3.4 });
  r.contar = [1.5, 2.8].map((t0, k) => r3(x.serie.find((s) => s.t >= t0 && s.dedos[k + 1] < 0.5).t - t0));
  const a = nuevo();
  r.rotulo = {};
  for (const g of ['aprobar', 'negar', 'pensar', 'saludar', 'senalar']) {
    const antes = ['hombroI', 'hombroD', 'codoI', 'codoD'].map((j) => H[j].quaternion.clone());
    const d = a.gesto(g, { soloCara: true });
    let brazo = 0;
    for (let i = 0; i < 60; i++) { a.actualizar(1 / 60); ['hombroI', 'hombroD', 'codoI', 'codoD'].forEach((j, k) => { brazo = Math.max(brazo, 2 * Math.acos(Math.min(1, Math.abs(antes[k].dot(H[j].quaternion))))); }); }
    r.rotulo[g] = { dur: d, gesto: a.estado().gesto, brazo: r3(brazo) };
    a.detenerGesto();
    for (let i = 0; i < 70; i++) a.actualizar(1 / 60);
  }
  r.caras = Object.keys(CARAS).length;
}
p.liberar();
console.log(JSON.stringify(r));
"""


@requiere_node
def test_los_gestos_de_reaccionar_el_lema_y_el_cierre(tmp_path):
    """Los gestos de reaccionar, el lema, el cierre y la pausa (etapa 7b): ninguno pasa por la T ni mete un dedo en el
    cuerpo, y la mano que lo hace queda arriba del corte; cada uno cumple lo suyo (la mano a la barbilla al pensar, la de
    preguntar adelante, asentir decrece y baja más rápido de lo que sube, el índice de negar se menea sin ceño con los
    dientes, las palmas de calmar e invitar a la vista, el pulgar a la altura del pecho, celebrar se agacha antes de
    saltar, las palmas se tocan al aplaudir, las manos entrelazadas del lema delante de la polo, la mano en el pecho, las
    manos tomadas al escuchar, la despedida que sigue saludando mientras se agacha); los sostenidos siguen vivos y aflojan,
    pensar termina con su «¡ya está!»; el dedo nuevo de contar aparece enseguida y en el rótulo los gestos son con la
    cara (los brazos quietos)."""
    (tmp_path / "cargador.mjs").write_text(CARGADOR, encoding="utf-8")
    (tmp_path / "prueba.mjs").write_text(NODE_REACCIONES, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), str(tmp_path / "cargador.mjs"), str(PRESENTADOR)],
                       capture_output=True, text=True, timeout=240, cwd=ADMIN,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin", "VENDOR_THREE": str(VENDOR_THREE)})
    assert p.returncode == 0, p.stderr
    import json
    r = json.loads(p.stdout.strip().splitlines()[-1])
    for g, x in r["gestos"].items():
        assert x["T"] == 0 and x["pen"] == [] and x["bajo"] > 0, (g, x)
    # (con la mano ×1.3 la palma no se acerca más sin tapar la boca: el índice en el mentón, la palma bajo la barbilla)
    assert r["pensar"]["palma"] < 0.16 and r["pensar"]["indice"] < 0.16 and r["pensar"]["codo"] < 0.15, r["pensar"]
    assert r["preguntar"] >= 0.35, r["preguntar"]
    a = r["asentir"]
    assert len(a) >= 2 and all(x["amp"] > y["amp"] for x, y in zip(a, a[1:])) and all(x["baja"] < x["sube"] for x in a), a
    assert r["negar"]["meneo"] >= 0.06 and not r["negar"]["cenoConDientes"], r["negar"]
    assert r["calmar"] > 0.3 and r["invitar"] > 0.3 and r["aprobar"] >= 1.15, (r["calmar"], r["invitar"], r["aprobar"])
    c = r["celebrar"]
    assert c["rodillas"] >= 0.3 and c["salto"] > 0.05 and c["reducido"] < 0.005, c
    # (las palmas se tocan: sus centros a menos de lo que miden de grueso las dos, 0.075, más 1 cm)
    assert sum(d <= 0.085 for d in r["aplaudir"]) >= 4, r["aplaudir"]
    assert r["juntos"]["a1s"] < 0.08 and r["juntos"]["delante"] >= 0.15, r["juntos"]
    assert r["corazon"]["polo"] < 0.035 and r["corazon"]["x"] > 0, r["corazon"]
    assert r["escuchar"] < 0.09, r["escuchar"]
    d = r["despedirse"]
    assert d["arriba"] > 1.7 and not d["bajaAntes"], d
    for g, x in r["sostenidos"].items():
        assert x["dif"] >= 0.02 and x["relajada"] == 1 and x["despues"] is None, (g, x)
    assert r["sostenidos"]["pensar"]["soltando"] and r["sostenidos"]["escuchar"]["soltando"]
    assert all(t <= 0.25 for t in r["contar"]), r["contar"]
    for g in ("aprobar", "negar", "pensar", "saludar"):
        assert r["rotulo"][g]["gesto"] == g and r["rotulo"][g]["brazo"] < 0.06, (g, r["rotulo"][g])
    assert r["rotulo"]["senalar"]["dur"] == 0 and r["caras"] >= 15


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


def test_el_vidrio_espera_al_presentador_que_baja():
    # el subtítulo que se quitó no se apaga mientras él se agacha detrás (si no, quedaba el corte en el aire, un casquete
    # de pelo sin el vidrio): presentador.js pone .presentador-sale en #pres al agacharse y la quita al terminar de bajar
    # (o si vuelve a subir); con la hoja grande del celular, nada (la hoja lo tapa)
    css = (WEB / "propuesta.html").read_text(encoding="utf-8")
    assert ".pres.presentador-sale:not(.panel-grande) .subtitulo:not(.visible) { visibility: visible; opacity: 1;" in css
    js = (PRESENTADOR / "presentador.js").read_text(encoding="utf-8")
    cuerpo = lambda nombre: js[js.index(f"function {nombre}("):js.index("\n  }\n", js.index(f"function {nombre}("))]
    assert "esperarVidrio(true)" in cuerpo("agachar")
    assert "esperarVidrio(false)" in cuerpo("esconder") and "esperarVidrio(false)" in cuerpo("subir")
    # mientras baja, el corte sigue al vidrio que lo espera (el subtítulo cambia de alto al quitarse la cabecera)
    assert "(saliendo ? vidrioQueEspera() : null)" in cuerpo("colocar")


def test_desde_lejos_la_mano_abierta_hacia_el_panel():
    # lo que el dedo no alcanza (la punta del índice a más de LEJOS_PX: Telesalud a 1440, el panel a 1920) no se señala con
    # el índice en alto (un dedo levantado) ni sobre la maqueta («esto del mapa»): la palma se abre hacia el borde del
    # panel a la altura del hombro (presentar y después indicar) y la cara mira el dato (`mira`) y vuelve a la sala; lo
    # señalado al alcance pero muy arriba del hombro sigue con el índice (la cifra de la portada)
    js = (PRESENTADOR / "presentador.js").read_text(encoding="utf-8")
    cuerpo = lambda nombre: js[js.index(f"function {nombre}("):js.index("\n  }\n", js.index(f"function {nombre}("))]
    entrada, sosten = cuerpo("gestoDeEntrada"), cuerpo("sostener")
    assert "comoSenalaDe(punto, c)" in entrada and "como === 'lejos'" in entrada and "g = 'presentar'" in entrada, entrada
    assert "opciones.mira = alMundo(punto.x, punto.y)" in entrada and "if (g === 'presentar' && como === 'alto') g = 'senalar'" in entrada
    assert "anim.gesto('indicar', { punto: alMundo(ab.x, ab.y), sostener: true })" in sosten
    assert "como === 'alto'" in sosten and "anim.gesto('senalar'" in sosten
    anim = (PRESENTADOR / "animador.js").read_text(encoding="utf-8")
    assert "if (o.mira && nuevo.mirar) nuevo.mirar = " in anim



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
// (lejos: peor y a más de un cuarto de su alto; poco: peor pero a menos de un cuarto, sin tapar mucho más)
const lejos = V.lugares(anf, ma, ctx, cajas).find((l) => l.costo > 1.25 * mejor.costo + 0.05 && Math.abs(l.x - mejor.x) >= 0.25 * ma.p);
const poco = V.lugares(anf, ma, ctx, cajas).find((l) => l.costo > 1.25 * mejor.costo + 0.05 && Math.abs(l.x - mejor.x) < 0.25 * ma.p && l.costo <= mejor.costo + 0.5);
r.histeresis = {
  mejor: mejor.x,
  queda: V.elegirLugar(anf, ma, ctx, cajas, { x: cerca.x }).razon,
  poco: poco ? V.elegirLugar(anf, ma, ctx, cajas, { x: poco.x }).razon : null,
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
// en una seguidilla de escenas con el atlas el círculo no cambia con cada panel: bajo el panel conserva su tamaño mientras
// quepa; acoplado sigue acoplado. De lado, con la ficha que el subtítulo monta, no la pisa (baja y se achica)
r.rotuloSigue = {
  conserva: V.rotuloDe(ESC, { sub: subR, panel: panelCorto, antes: { modo: 'panel', lado: 94 } }),
  achica: V.rotuloDe(ESC, { sub: subR, panel: { ...panelCorto, y1: 716 }, antes: { modo: 'panel', lado: 113 } }),
  acoplado: V.rotuloDe(ESC, { sub: subR, panel: panelCorto, antes: { modo: 'acoplado', lado: 84 } }),
  techo: V.posRotulo(lado, { x0: 397, y0: 280, x1: 834, y1: 376 }, null, { techo: 314 }),
};
// lo que se ve manda (ctx.domManda: «Solo 3D», el atlas o la ficha que se abren a mitad de la escena); sin él, la escena
const conPanel = E({ paso: 3, tipo: 'componente', resaltar: { tipo: 'especificacion', n: 2, en: 'panel' } });
r.domManda = {
  sinPanel: V.elegirVista(conPanel, { ...ESC, domManda: true, dom: { ...ESC.dom, sinPanel: true } }).vista,
  atlas: V.elegirVista(E({ paso: 3, tipo: 'componente' }), { ...ESC, domManda: true, dom: { ...ESC.dom, conInmersion: true } }).vista,
  ficha: V.elegirVista(E({ paso: 3, tipo: 'componente' }), { ...CEL, domManda: true, dom: { ...CEL.dom, conDetalle: true } }).regla,
  atlasCerrado: V.elegirVista(E({ paso: 6, tipo: 'inmersion', atlas: 'torre_sismo' }), { ...ESC, domManda: true }).vista,
  sinDom: V.elegirVista(conPanel, { ...ESC, dom: { ...ESC.dom, sinPanel: true } }).vista,
};
// señalando lo que el dedo no alcanza (la cifra de la portada, 190 px arriba del hombro): lo más cerca que se puede del
// panel (a no más de 30 px de lo mejor); desde lejos se va aunque ya haya cambiado. Los títulos de la maqueta: no se
// tapan si hay un lugar que llegue sin taparlos (Telesalud: San Francisco y La Soledad)
const cifra = { sub, panel, foco: { x0: 334, y0: 345, x1: 527, y1: 463 }, obra: { x0: 597, y0: 151, x1: 1411, y1: 626 },
  rotulos: [{ x0: 720, y0: 473, x1: 796, y1: 507 }, { x0: 957, y0: 164, x1: 1050, y1: 198 }] };
const eC = V.elegirVista(E({ capitulo: 'portada', paso: 1, tipo: 'portada', resaltar: { tipo: 'cifra', n: 2 } }), ESC);
const pC = V.objetivoDe(eC.objetivo, eC.lado, cifra, { yHombro: V.yHombro(sub.y0, m), VW: 1440, VH: 900 });
const todosC = V.lugares(eC, m, ctx, cifra, { punto: pC, todos: true });
const lC = V.elegirLugar(eC, m, ctx, cifra, {}, { punto: pC });
const subT = { x0: 568, y0: 721, x1: 1132, y1: 814 };
const tele = { sub: subT, panel, foco: { x0: 131, y0: 418, x1: 527, y1: 502 }, obra: { x0: 743, y0: 110, x1: 1265, y1: 667 },
  rotulos: [{ x0: 800, y0: 75, x1: 905, y1: 87 }, { x0: 1178, y0: 634, x1: 1261, y1: 646 }, { x0: 664, y0: 494, x1: 735, y1: 506 }, { x0: 647, y0: 616, x1: 703, y1: 628 }] };
const eT = V.elegirVista(E({ resaltar: { tipo: 'componente', id: 'telesalud' } }), ESC);
const pT = V.objetivoDe(eT.objetivo, eT.lado, tele, { yHombro: V.yHombro(subT.y0, m), VW: 1440, VH: 900 });
const lT = V.elegirLugar(eT, m, ctx, tele, {}, { punto: pT });
r.lejos = {
  dp: V.distPunta(lC.x, pC, { p: m.p, subTop: sub.y0, rumbo: V.rumboDe('senala', pC.x - lC.x) }),
  minDp: Math.min(...todosC.filter((l) => !l.razon.some((x) => x !== 'lejos')).map((l) => l.dp)),
  hayLejos: todosC.some((l) => l.razon.includes('lejos')),
  desdeLejos: V.elegirLugar(eC, m, ctx, cifra, { x: 1100, ms: 9000, cambios: 1 }, { punto: pC }).razon,
  titulo: V.lugares(eT, m, ctx, tele, { punto: pT, todos: true }).find((l) => l.x === lT.x)?.titulo,
  // (la cifra de la portada, al alcance pero 190 px arriba del hombro: el índice)
  como: V.comoSenala(lC.x, pC, { p: m.p, subTop: sub.y0, yc: m.yc, rumbo: V.rumboDe('senala', pC.x - lC.x) }),
};
// desde lejos: Telesalud con las cajas enteras de sus rótulos (las de la página: «La Soledad · a 27,6 km → · sede
// satélite (…)» a la altura del pecho en casi todo el subtítulo). Desde ningún lugar que deje leerlos llega el dedo: no
// hay por qué taparlos (ni el título ni la caja); la mano abierta hacia el borde del panel, a la altura del hombro
const teleE = { ...tele, cajasRotulos: [{ x0: 790, y0: 72, x1: 1042, y1: 105 }, { x0: 1168, y0: 631, x1: 1269, y1: 664 },
  { x0: 654, y0: 491, x1: 834, y1: 524 }, { x0: 637, y0: 613, x1: 1003, y1: 646 }] };
const lTE = V.elegirLugar(eT, m, ctx, teleE, {}, { punto: pT });
const todosTE = V.lugares(eT, m, ctx, teleE, { punto: pT, todos: true });
const xTE = todosTE.find((l) => l.x === lTE.x);
const oTE = { p: m.p, subTop: subT.y0, yc: m.yc, rumbo: V.rumboDe('senala', pT.x - lTE.x) };
const abTE = V.abierta('panel', teleE, lTE.x, V.yHombro(subT.y0, m));
const manoTE = V.manoAbierta(lTE.x, abTE, oTE);
r.desdeLejos = { lejos: lTE.lejos, como: V.comoSenala(lTE.x, pT, oTE), titulo: xTE.titulo, caja: xTE.caja, razon: xTE.razon,
  // (el lugar de antes, x 833: el dedo a 200 px y la caja de La Soledad tapada en un 37 %)
  antes: todosTE.find((l) => Math.abs(l.x - 833) <= 4)?.razon,
  ab: abTE, mano: manoTE.punta, hombro: manoTE.hombro, borde: panel.x1,
  seVa: V.elegirLugar(eT, m, ctx, teleE, { x: 833, cambios: 1, ms: 9000 }, { punto: pT }).razon };
// 1920x1080 (aguas/2, el punto 3): lo señalado 300 px arriba del hombro y el dedo no llega desde ningún lado: junto al
// panel (hasta el extremo del subtítulo que deja la cadera sobre él), con la mano abierta
const ctx19 = { ...ESC, VW: 1920, VH: 1080 };
const m19 = V.medidas('senala', ctx19);
const c19 = { sub: { x0: 668, y0: 893, x1: 1512, y1: 994 }, panel: { x0: 100, y0: 76, x1: 552, y1: 729 },
  foco: { x0: 149, y0: 441, x1: 527, y1: 509 }, obra: { x0: 746, y0: 138, x1: 1784, y1: 820 } };
const p19 = V.objetivoDe('foco', 'panel', c19, { yHombro: V.yHombro(c19.sub.y0, m19), VW: 1920, VH: 1080 });
const l19 = V.elegirLugar(eT, m19, ctx19, c19, {}, { punto: p19 });
r.lejos1920 = { x: l19.x, lejos: l19.lejos, sub: c19.sub.x0, cadera: 0.12 * m19.p, margen: 0.2 * m19.p,
  como: V.comoSenala(l19.x, p19, { p: m19.p, subTop: c19.sub.y0, yc: m19.yc, rumbo: -0.35 }) };
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
    # (moverse menos de un cuarto de su alto no vale la pena si desde ahí no tapa mucho más)
    assert h["poco"] == "se_queda", h
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
    # el rótulo de una seguidilla no cambia con cada panel; de lado no pisa la ficha
    rs = r["rotuloSigue"]
    assert rs["conserva"] == {"modo": "panel", "lado": 94, "borde": "izq"}, rs
    assert rs["achica"]["modo"] == "panel" and 88 <= rs["achica"]["lado"] < 113, rs
    assert rs["acoplado"]["modo"] == "acoplado", rs
    assert rs["techo"]["y0"] >= 314 + 4 and rs["techo"]["y0"] + rs["techo"]["L"] <= 376, rs
    # lo que se ve manda a mitad de la escena: sin el panel, el general; con el atlas, el rótulo; con la ficha en el
    # celular, el rótulo; el atlas que se cerró ya no es rótulo. Sin domManda, manda la escena
    assert r["domManda"] == {"sinPanel": "general", "atlas": "rotulo", "ficha": "R3", "atlasCerrado": "presenta", "sinDom": "senala"}, r["domManda"]
    # señalando lo que el dedo no alcanza: lo más cerca que se puede (a no más de 30 px) y desde lejos se va aunque ya
    # haya cambiado; Telesalud sin tapar los títulos de la maqueta
    lj = r["lejos"]
    assert lj["hayLejos"] and lj["dp"] <= lj["minDp"] + 30 and lj["desdeLejos"] == "no_sirve", lj
    assert lj["titulo"] is not None and lj["titulo"] <= 0.3, lj
    assert lj["como"] == "alto", lj
    # desde lejos (Telesalud, con la caja entera de La Soledad): el dedo no llega desde ningún lugar que deje leer los
    # rótulos, así que no tapa ni el título (≤ 30 %) ni la caja (≤ 10 %); el lugar de antes los tapaba y se va de ahí
    # aunque ya haya cambiado. La mano abierta, hacia el borde del panel a la altura del hombro, fuera del vidrio
    dl = r["desdeLejos"]
    assert dl["lejos"] and dl["como"] == "lejos" and not dl["razon"], dl
    assert dl["titulo"] <= 0.3 and dl["caja"] <= 0.1, dl
    assert "rotulo" in dl["antes"] and dl["seVa"] == "no_sirve", dl
    assert dl["ab"]["x"] == dl["borde"] and dl["mano"]["x"] >= dl["borde"] + 6, dl
    assert dl["hombro"]["y"] - dl["mano"]["y"] <= 0.21 * (dl["hombro"]["x"] - dl["mano"]["x"]) + 1, dl
    # en 1920x1080, junto al panel: más cerca que el margen de siempre, la cadera todavía sobre el subtítulo
    l19 = r["lejos1920"]
    assert l19["lejos"] and l19["como"] == "lejos", l19
    assert l19["sub"] + 8 + l19["cadera"] <= l19["x"] < l19["sub"] + l19["margen"], l19


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
