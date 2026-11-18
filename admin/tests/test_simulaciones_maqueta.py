"""`simular` en la maqueta 3D: sin un modelo del atlas a la vista, el asistente y los agentes por MCP accionan la hora
del día, el día entero en 24 s, las luminarias y el partido en la Cancha de Sóftbol Casabe (la clave «maqueta» de
data/propuesta/simulaciones.json), con la misma forma y el mismo camino que los controles del atlas.

* Puro: en qué modelo acciona `simular` (app/recorrido.py `simulable_en`: el del atlas, la maqueta o, en un paso que no
  se sabe de un capítulo con modelos del atlas, ninguno) y cómo la herramienta resuelve un plan en la cancha (por id o
  por nombre, «de noche», «sí»), con avisos legibles para lo que es de otro capítulo o de un modelo del atlas cerrado.
* Node, con una escena falsa: web/js/propuesta/simulacion.js (la regla del valor del atlas, el día que se pausa y
  sigue, el partido que espera a que se arme su capítulo y que no se juega fuera del encuadre, las luces solo donde hay
  luminarias, todo vuelve a lo del paso con `reiniciar`).
* Chromium, con el sitio que arma build_site.py: una página del mismo origen enmarca propuesta.html?modo=tecnica&qa y le
  habla como el panel (postMessage): la noche (con el velo de los bordes teñido), las luces y el partido en la cancha, el
  día que corre con el reloj, que al cambiar de paso todo vuelve a lo del paso (y que un `ir` al mismo paso no la toca,
  como en la pantalla en off), lo que no vale (el partido en el mirador, fuera del encuadre en las canchas cubiertas o
  en salud) y la escena de un plan.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from app import pantalla, recorrido as rec
from app.agente import guion as guion_presentacion
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta
from test_agente_presentacion import requiere_navegador, requiere_node
from test_pantalla_mcp import _Base, _hacer
from test_plan_guiado import _node
from test_simulaciones_atlas import _Silencioso, _correr_node

G = guion_presentacion.cargar()
ADMIN = Path(__file__).resolve().parents[1]
RAIZ = ADMIN.parent
SIMULACIONES = RAIZ / "data" / "propuesta" / "simulaciones.json"
SIMULACION_JS = RAIZ / "web" / "js" / "propuesta" / "simulacion.js"
UID = 7

pytestmark = pytest.mark.skipif(G is None or not SIMULACIONES.is_file(), reason="Sin el guion o sin data/propuesta")


def _maqueta() -> list:
    return json.loads(SIMULACIONES.read_text(encoding="utf-8")).get("maqueta") or []


def _plan(*pasos, titulo="La cancha de noche"):
    return {"op": "recorrido", "titulo": titulo, "pasos": list(pasos), "cierre": ["La cancha también es de noche"]}


# ───────────────────────────── En qué modelo acciona simular ─────────────────────────────

def test_simular_acciona_en_el_atlas_o_en_la_maqueta():
    sim = rec.simulable_en
    assert sim("salud", 1, None, G) == rec.MAQUETA                      # un paso sin modelo del atlas: la maqueta
    assert sim("salud", 6, None, G) == "torre_sismo"                    # el paso del simulador sísmico
    assert sim("salud", 6, "maqueta", G) == rec.MAQUETA                 # cerrado el modelo del atlas
    assert sim("salud", 1, "torre_bim", G) == "torre_bim"               # el que se abre
    assert sim("vivienda", None, None, G) == rec.MAQUETA                # un capítulo sin modelos del atlas: cualquier paso
    assert sim("salud", None, None, G) is None                          # no se sabe el paso: puede ser el del atlas
    assert sim("salud", None, "maqueta", G) == rec.MAQUETA
    assert sim("marte", 1, None, G) is None and sim("salud", 99, None, G) is None and sim("salud", 1, None, None) is None
    esc = {"capitulo": "urbanismo", "paso": 3, "visual": {**rec.visual_inicial()}}
    assert rec.simulable_de(esc, G) == rec.MAQUETA and rec.simulable_de(None, G) is None
    # la herramienta ve lo mismo en cada paso: `controles` del atlas o `controles_maqueta`
    for c in G.capitulos:
        for pi in range(len(c["pasos"])):
            m = rec.simulable_en(c["id"], pi + 1, None, G)
            assert m == (rec.inmersion_en(c["id"], pi + 1, None, G) or rec.MAQUETA), (c["id"], pi + 1)


# ───────────────────────────── La herramienta: el plan y visual ─────────────────────────────

def test_el_plan_en_la_cancha_acciona_la_noche_las_luces_y_el_partido():
    db = _Base()
    pantalla.marcar_vista(db, UID)
    r = _hacer(db, UID, _plan(
        {"capitulo": "urbanismo", "paso": "softbol", "dice": "Esta es la Cancha de Sóftbol Casabe."},
        {"simular": [{"control": "Hora del día", "valor": "de noche"}, {"control": "luces", "valor": "sí"}, "partido"],
         "dice": "De noche, con sus torres LED, sigue el partido."},
        {"simular": [{"control": "reproducir_dia", "valor": True}], "sostener": 8, "dice": "Y así pasa un día entero."},
        {"capitulo": "salud", "paso": 1, "simular": ["partido", "luces", {"control": "hora", "valor": "amanecer"}],
         "dice": "En el hospital no hay partido."},
        {"simular": [{"control": "reproducir", "valor": True}], "dice": "Sin abrir el simulador no tiembla nada."},
        {"simular": [{"control": "hora", "valor": "atardecer"}, {"control": "calcular"}], "dice": "La hora sí."},
    ), por="mcp")
    sc = pantalla.recorrido_de(db.pantallas.find_one({"_id": UID}), G)["escenas"]
    assert sc[0]["simular"] is None
    assert sc[1]["simular"] == [{"control": "hora", "valor": "noche"}, {"control": "luces", "valor": True},
                                {"control": "partido", "valor": True}]
    assert sc[2]["simular"] == [{"control": "reproducir_dia", "valor": True}]
    assert sc[3]["simular"] is None and sc[4]["simular"] is None
    assert sc[5]["simular"] == [{"control": "hora", "valor": "atardecer"}]
    assert rec.validar({k: v for k, v in pantalla.recorrido_de(db.pantallas.find_one({"_id": UID}), G).items()
                        if k in ("id", "titulo", "escenas", "cierre")}, G) == []
    avisos = " | ".join(r.contenido["avisos"])
    for x in ("Paso 4: «La maqueta 3D» no tiene el control «partido» en Salud (está en: Urbanismo): se ignoró; "
              "controles: hora, reproducir_dia",
              # las luces, donde hay luminarias
              "Paso 4: «La maqueta 3D» no tiene el control «luces» en Salud (está en: Vivienda, Urbanismo): se ignoró",
              "Paso 4: simular «hora» no tiene la opción «amanecer»",
              # «reproducir» es el del simulador sísmico (no el día): el aviso de siempre y lo que tiene la maqueta
              "Paso 5: simular acciona los controles del modelo del atlas abierto y ahí no hay uno (ábralo con inmersion): "
              "no se accionó nada; la maqueta 3D tiene: hora, reproducir_dia",
              "Paso 6: «calcular» es del modelo del atlas «Simulador sísmico», que no está abierto (ábralo con inmersion): "
              "se ignoró"):
        assert x in avisos, (x, avisos)
    muestra = [p["muestra"] for p in r.contenido["pasos"]]
    assert "acciona: Hora del día: Noche; Luces de la maqueta: sí; Partido de sóftbol: sí" in muestra[1]
    assert "acciona: Reproducir el día: sí" in muestra[2] and "acciona" not in muestra[3]
    hace = [e["hace"] for a in _hacer(_Base(), UID, _plan(
        {"capitulo": "urbanismo", "paso": "softbol", "dice": "La cancha."},
        {"simular": [{"control": "hora", "valor": "noche"}], "dice": "De noche."}), por="asistente").acciones
        if a["tipo"] == "recorrido" for e in a["escenas"]]
    assert "simular" in hace[1] and "simular" not in hace[0]
    # lo que se sostiene: hay algo que mirar
    assert sc[1]["sostener_ms"] == rec.SOSTENER_MIRAR_MS


def test_visual_en_la_maqueta_avisa_lo_que_es_de_otro_lado():
    db = _Base()
    pantalla.marcar_vista(db, UID)
    _hacer(db, UID, {"op": "ir", "capitulo": "urbanismo", "paso": "softbol"})
    r = _hacer(db, UID, {"op": "visual", "simular": [{"control": "partido"}, {"control": "Hora del día", "valor": "Atardecer"}]})
    assert r.resumen == "La presentación muestra en «La maqueta 3D»: Partido de sóftbol: sí; Hora del día: Atardecer"
    assert r.contenido["simulacion"] == hi.SIMULACION_MAQUETA
    # todo de otro lado: un error con los controles que sí tiene la maqueta en ese capítulo
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 1})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "simular": [{"control": "partido"}]})
    assert "no tiene el control «partido» en Salud (está en: Urbanismo)" in str(e.value)
    assert [c["id"] for c in e.value.detalle["controles"]] == ["hora", "reproducir_dia"]
    # en el simulador sísmico abierto, la hora no es un control suyo
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "simular": [{"control": "hora", "valor": "noche"}]})
    assert "«Simulador sísmico» no tiene el control «hora»" in str(e.value)


def test_el_guion_dice_la_maqueta_y_no_la_mezcla_con_las_inmersiones():
    datos = json.loads((RAIZ / "web" / "data" / "propuesta.json").read_text(encoding="utf-8"))
    g = guion_presentacion.derivar(datos)
    assert g["maqueta"]["id"] == "maqueta" and g["maqueta"]["nombre"] == "La maqueta 3D"
    assert [c["id"] for c in g["maqueta"]["controles"]] == [c["id"] for c in _maqueta()]
    assert g["maqueta"]["controles"][-1]["capitulos"] == ["urbanismo"] and guion_presentacion.problemas(g) == []
    # sin catálogo, el guion sale sin la clave (y vale); con una forma que no sirve, problemas lo dice
    sin = json.loads(json.dumps(datos))
    sin["tecnica"].pop("simulaciones_maqueta")
    assert "maqueta" not in guion_presentacion.derivar(sin)
    malo = json.loads(json.dumps(g))
    malo["maqueta"]["controles"].append({"id": "hora", "tipo": "si_no"})
    malo["maqueta"]["controles"][0]["capitulos"] = "urbanismo"
    p = " | ".join(guion_presentacion.problemas(malo))
    assert "maqueta: control repetido: hora" in p and "maqueta: hora: capitulos es una lista" in p
    # un capítulo que no es del guion: el control quedaría fuera de todos sin que nadie lo note
    malo = json.loads(json.dumps(g))
    malo["maqueta"]["controles"][-1]["capitulos"] = ["urbanizmo"]
    assert guion_presentacion.problemas(malo) == ["maqueta: partido: el capítulo «urbanizmo» no existe"]
    malo = json.loads(json.dumps(g))
    malo["inmersiones"][0]["id"] = "maqueta"
    assert "una inmersión no puede llamarse «maqueta»" in " | ".join(guion_presentacion.problemas(malo))
    # un guion de antes (sin la maqueta) no tiene sus controles
    viejo = guion_presentacion.Guion(G.capitulos, G.inmersiones)
    assert viejo.controles("maqueta", "salud") == [] and viejo.nombre_modelo("maqueta") == "La maqueta 3D"


# ───────────────────────────── simulacion.js con una escena falsa (Node) ─────────────────────────────

NODE_SIMULACION = r"""// simulacion.js con una escena falsa. Uso: node <guion> <simulacion.js> <catálogo de la maqueta (JSON)>
import fs from 'node:fs';
const [modulo, catalogo] = process.argv.slice(2);
// escenario.js (la regla del valor) mira la dirección y el marco al cargarse: fuera de un marco no instala nada
globalThis.location = { search: '', href: 'http://localhost/propuesta.html' };
globalThis.window = globalThis;
const S = await import(modulo);
const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
const log = [];
const HORAS = ['manana', 'tarde', 'atardecer', 'noche'];
const amb = { h: 'tarde', enC: false, pausado: false, horas: HORAS,
  poner(v) { log.push(['poner', v]); if (v != null && !HORAS.includes(v)) return false; this.enC = false; this.pausado = false; this.h = v ?? 'tarde'; return true; },
  ciclo(o) { log.push(['ciclo', o]); this.enC = true; this.pausado = false; return Promise.resolve(true); },
  reanudar() { log.push(['reanudar']); if (!this.pausado) return null; this.enC = true; this.pausado = false; return Promise.resolve(true); },
  pausar() { log.push(['pausar']); if (this.enC) this.pausado = true; this.enC = false; },
  enCiclo() { return this.enC; }, hora() { return this.h; } };
let encendidas = null, falla = false;
const escena = { ambiente: amb, st: { invalidate() {} }, lucesEstado: () => ({ encendidas }),
  luces(v) { if (falla) throw new Error('sin luminarias'); log.push(['luces', v]); encendidas = v; } };
let activo = false;
const capa = { visible: true, parent: { visible: true, parent: null } };
const partido = { pieza: capa, jugar(v) { log.push(['jugar', v]); activo = v; }, activo: () => activo };
const ctx3d = {};
const datos = { tecnica: { simulaciones_maqueta: JSON.parse(fs.readFileSync(catalogo, 'utf8')) } };
const caps = [{ id: 'vivienda', nombre: 'Vivienda' }, { id: 'urbanismo', nombre: 'Urbanismo' }, { id: 'salud', nombre: 'Salud' }];
const estado = { ci: 0, pi: 0 };
// visual.js dice si la cancha queda en el encuadre en que queda la cámara
let encuadrada = true;
const sim = S.crearSimulacion({ escena, ctx3d, datos, caps, estado, enEncuadre: (p) => p === capa && encuadrada });
const r = { constantes: [S.DURACION_DIA, S.ESPERA_MAQUETA_MS] };
const ids = (l) => l.map((c) => c.id);
r.catalogo = { salud: ids(S.controlesMaqueta(datos, 'salud')), vivienda: ids(S.controlesMaqueta(datos, 'vivienda')),
  urbanismo: ids(S.controlesMaqueta(datos, 'urbanismo')),
  sin_capitulos: S.controlesMaqueta(datos, 'urbanismo').every((c) => !('capitulos' in c)), vacio: S.controlesMaqueta({}, 'salud'),
  copia: S.controlesMaqueta(datos, 'salud')[0] !== datos.tecnica.simulaciones_maqueta[0], controles: ids(sim.controles()) };
// en vivienda: lo que no es de la maqueta aquí, y la regla del valor del atlas
r.vivienda = { partido: sim.accionar('partido', true), noexiste: sim.accionar('explotar'), luces_texto: sim.accionar('luces', 'si'),
  luces_sin: sim.accionar('luces'), hora_mala: sim.accionar('hora', 'amanecer'), hora_tilde: sim.accionar('hora', 'Mañana'),
  hora: amb.hora() };
r.sin_tocar_antes = log.length;
log.length = 0;
r.noche = [sim.accionar('hora', 'noche'), sim.accionar('luces', true)];
r.estado_noche = sim.estado();
// el día: de la mañana a la noche; otra vez sí no lo reinicia; no lo pausa y sí sigue desde ahí
r.dia = [sim.accionar('reproducir_dia', true), sim.accionar('reproducir_dia', true), sim.accionar('reproducir_dia', false),
  sim.accionar('reproducir_dia', true)];
r.dia_log = log.filter((l) => ['ciclo', 'reanudar', 'pausar'].includes(l[0]));
r.estado_dia = sim.estado();
// todo vuelve a lo del paso (una vez: sin cambios, nada que devolver)
log.length = 0;
sim.reiniciar();
r.reinicio = log.slice();
log.length = 0;
sim.reiniciar();
r.reinicio_sin_cambios = log.slice();
r.estado_reiniciado = sim.estado();
// en urbanismo: el partido espera a que el capítulo se arme
estado.ci = 1;
const p1 = sim.accionar('partido', true);
r.partido_pendiente = typeof p1?.then === 'function';
setTimeout(() => { ctx3d.urbanismo = { simulaciones: { partido } }; }, 300);
r.partido = await p1;
r.partido_activo = sim.estado().partido;
r.partido_no = sim.accionar('partido', false);
r.partido_activo_tras_no = activo;
// el que espera se abandona si cambia de paso
delete ctx3d.urbanismo;
const p2 = sim.accionar('partido', true);
sim.reiniciar();
r.partido_abandonado = await p2;
// armada pero no a la vista (el mirador, comparar hoy, aislar): lo dice en el acto, sin esperar los 8 s
ctx3d.urbanismo = { simulaciones: { partido } };
capa.parent.visible = false;
r.partido_oculto = sim.accionar('partido', true);
capa.parent.visible = true;
r.partido_en_el_acto = sim.accionar('partido', true);
// a la vista pero fuera del encuadre en que queda la cámara (las canchas cubiertas junto al CIC): tampoco, en el acto
partido.jugar(false);
encuadrada = false;
r.partido_fuera = sim.accionar('partido', true);
r.partido_activo_fuera = activo;
encuadrada = true;
// y nunca lanza
falla = true;
r.lanza = sim.accionar('luces', false);
falla = false;
// en salud no hay luminarias que se vean: las luces no son un control de ahí
estado.ci = 2;
r.luces_salud = sim.accionar('luces', true);
console.log(JSON.stringify(r));
"""


@requiere_node
def test_simulacion_js_con_una_escena_falsa(tmp_path):
    cat = tmp_path / "maqueta.json"
    cat.write_text(json.dumps(_maqueta(), ensure_ascii=False), encoding="utf-8")
    r = _node(tmp_path, NODE_SIMULACION, SIMULACION_JS.as_uri(), str(cat))
    assert r["constantes"] == [24, 8000]
    assert r["catalogo"] == {"salud": ["hora", "reproducir_dia"], "vivienda": ["hora", "reproducir_dia", "luces"],
                             "urbanismo": ["hora", "reproducir_dia", "luces", "partido"], "sin_capitulos": True, "vacio": [],
                             "copia": True, "controles": ["hora", "reproducir_dia", "luces"]}
    s = r["vivienda"]
    assert s["partido"] == "«partido» no es un control de la maqueta en Vivienda; tiene: hora, reproducir_dia, luces"
    assert s["noexiste"].startswith("«explotar» no es un control de la maqueta en Vivienda")
    assert s["luces_texto"] == s["luces_sin"] == "«Luces de la maqueta» pide sí o no (true o false)"
    assert "no tiene la opción «amanecer»" in s["hora_mala"] and s["hora_tilde"] is True and s["hora"] == "manana"
    assert r["noche"] == [True, True]
    assert r["estado_noche"] == {"hora": "noche", "dia": False, "luces": True, "partido": False}
    assert r["dia"] == [True, True, True, True]
    # (sin un día pausado, reanudar no hace nada y empieza de la mañana)
    assert r["dia_log"] == [["reanudar"], ["ciclo", {"desde": "manana", "hasta": "noche", "duracion": 24}], ["pausar"],
                            ["reanudar"]], r["dia_log"]
    assert r["estado_dia"]["dia"] is True
    assert r["reinicio"] == [["poner", None], ["luces", None]] and r["reinicio_sin_cambios"] == []
    assert r["estado_reiniciado"] == {"hora": "tarde", "dia": False, "luces": None, "partido": False}
    assert r["partido_pendiente"] is True and r["partido"] is True and r["partido_activo"] is True
    assert r["partido_no"] is True and r["partido_activo_tras_no"] is False
    assert r["partido_abandonado"] == "se cambió de paso antes de accionarlo"
    assert "no está a la vista" in r["partido_oculto"] and r["partido_en_el_acto"] is True
    assert "no queda en el encuadre" in r["partido_fuera"] and r["partido_activo_fuera"] is False
    assert r["lanza"] == "sin luminarias"
    assert r["luces_salud"] == "«luces» no es un control de la maqueta en Salud; tiene: hora, reproducir_dia"


# ───────────────────────────── En Chromium: la presentación técnica, como la maneja el panel ─────────────────────────────

NODE_MAQUETA = r"""// La maqueta 3D manejada por la presentación técnica, como lo hace el panel (postMessage desde un marco del mismo
// origen). Uso: node <guion> <url de la página que enmarca propuesta.html?modo=tecnica&qa>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
const [url] = process.argv.slice(2);
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 760 }, deviceScaleFactor: 1 });
const errores = [];
page.on('pageerror', (e) => errores.push(String(e)));
await page.goto(url);
await page.waitForFunction(() => window.__msgs.some((m) => m.tipo === 'listo'), null, { timeout: 120000 });
const orden = (o, plazo = 30000) => page.evaluate(([o, plazo]) => window.__orden(o, plazo), [o, plazo]);
const pres = () => page.frames().find((f) => /\/propuesta\.html/.test(f.url()));
const qa = (expr) => pres().evaluate(new Function(`const Q = window.__qaPropuesta; return (${expr});`));
const corto = (x) => ({ tipo: x.tipo, error: x.error ?? null, aviso: x.aviso ?? null, descartadas: x.descartadas ?? null,
  paso: x.paso ?? null, simulacion: x.visual?.simulacion ?? null });
const V0 = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const r = {};
r.tema = await qa('Q.ambiente.hora()');
// 1. En la cancha: la noche, las luces y el partido
r.ir = corto(await orden({ orden: 'ir', capitulo: 'urbanismo', paso: 3 }));
r.noche = corto(await orden({ orden: 'visual', simular: [{ control: 'hora', valor: 'noche' }, { control: 'luces', valor: true },
  { control: 'partido', valor: true }] }));
// (si el capítulo de la cancha todavía se estaba armando, el partido arranca solo al terminar: se pregunta el estado)
for (let i = 0; i < 40 && !r.noche.simulacion?.partido; i++) { await page.waitForTimeout(250); r.noche.simulacion = corto(await orden({ orden: 'estado' })).simulacion; }
r.hora_noche = await qa('Q.ambiente.hora()');
r.fijada = await qa('Q.ambiente.fijada()');
// el velo de los bordes se tiñe de la noche (con el tema claro no quedan blancos)
const velo = () => pres().evaluate(() => getComputedStyle(document.getElementById('escena')).getPropertyValue('--velo-k').trim());
r.velo_noche = await velo();
// 2. El día: corre de la mañana a la noche (el sol se mueve); no lo pausa
r.dia = corto(await orden({ orden: 'visual', simular: [{ control: 'reproducir_dia', valor: true }] }));
const sol1 = await qa('Q.ambiente.datos().sol.join(",")');
await page.waitForTimeout(2500);
const sol2 = await qa('Q.ambiente.datos().sol.join(",")');
r.sol_se_mueve = sol1 !== sol2;
r.pausa = corto(await orden({ orden: 'visual', simular: [{ control: 'reproducir_dia', valor: false }] }));
const sol3 = await qa('Q.ambiente.datos().sol.join(",")');
await page.waitForTimeout(1200);
r.sol_quieto = sol3 === await qa('Q.ambiente.datos().sol.join(",")');
// el ciclo va con el reloj, no con los cuadros: un tramo de 2 s dura unos 2 s aunque se dibujen pocos cuadros por segundo
r.ciclo_s = await pres().evaluate(async () => { const t0 = performance.now(); await window.__qaPropuesta.ambiente.ciclo({ desde: 'manana', hasta: 'tarde', duracion: 2 }); return (performance.now() - t0) / 1000; });
// 3. Otro paso: todo vuelve a lo del paso (la hora del tema, las luces según la hora, el partido quieto)
r.otro_paso = corto(await orden({ orden: 'ir', capitulo: 'urbanismo', paso: 4 }));
r.hora_otro_paso = await qa('Q.ambiente.hora()');
r.velo_otro_paso = await velo();
// 4. El partido donde la cancha no está a la vista (el mirador), donde no queda en el encuadre (las canchas cubiertas
// junto al CIC) o donde no es un control (salud): un error que lo dice
await orden({ orden: 'ir', capitulo: 'urbanismo', paso: 6 });
r.instalaciones = corto(await orden({ orden: 'visual', simular: [{ control: 'partido', valor: true }] }));
await orden({ orden: 'ir', capitulo: 'urbanismo', paso: 7 });
r.mirador = corto(await orden({ orden: 'visual', simular: [{ control: 'partido', valor: true }] }));
r.mirador_parcial = corto(await orden({ orden: 'visual', simular: [{ control: 'hora', valor: 'atardecer' }, { control: 'partido', valor: true }] }));
await orden({ orden: 'ir', capitulo: 'salud', paso: 1 });
r.salud = corto(await orden({ orden: 'visual', simular: [{ control: 'partido', valor: true }] }));
// 5. Un `ir` al paso que ya está no la toca (la pantalla en off no se entera de ese `ir`: las dos muestran lo mismo)
r.salud_noche = corto(await orden({ orden: 'visual', simular: [{ control: 'hora', valor: 'noche' }] }));
r.mismo_paso = corto(await orden({ orden: 'ir', capitulo: 'salud', paso: 1 }));
// 6. Una escena de un plan en la cancha
r.escena = corto(await orden({ orden: 'escena', rid: 'abcdef123456', n: 1, de: 1, titulo: 'La cancha de noche', capitulo: 'urbanismo',
  paso: 3, panel: true, visual: V0, resaltar: null, mover: null, animar: false,
  simular: [{ control: 'hora', valor: 'atardecer' }, { control: 'partido', valor: true }], frases: ['Al atardecer sigue el partido.'],
  voz: false, ms: 3000 }));
r.hora_escena = await qa('Q.ambiente.hora()');
r.errores = errores;
console.log(JSON.stringify(r));
await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""

MARCO_PRESENTACION = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Marco</title></head>
<body style="margin:0"><iframe id="p" src="propuesta.html?modo=tecnica&qa#salud" style="border:0;width:100vw;height:100vh;display:block"></iframe>
<script>
// como admin/web/js/vistas/presentacion.js: solo su ventana y su origen; cada orden con su id y su respuesta
window.__msgs = [];
let nro = 0; const pend = new Map();
const f = document.getElementById('p');
addEventListener('message', (e) => {
  if (e.source !== f.contentWindow || e.origin !== location.origin) return;
  const m = e.data;
  if (!m || typeof m !== 'object' || m.canal !== 'yondo-presentacion' || m.v !== 1) return;
  window.__msgs.push(m);
  if (m.id != null && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
});
window.__orden = (o, plazo) => new Promise((ok) => {
  const id = ++nro;
  const reloj = setTimeout(() => { pend.delete(id); ok({ sinRespuesta: true }); }, plazo);
  pend.set(id, (m) => { clearTimeout(reloj); ok(m); });
  f.contentWindow.postMessage({ canal: 'yondo-presentacion', v: 1, id, ...o }, location.origin);
});
</script></body></html>"""


@pytest.fixture(scope="module")
def marco_presentacion(tmp_path_factory):
    """El sitio que arma build_site.py, servido en un puerto libre, con una página del mismo origen que enmarca la
    presentación técnica y le habla como el panel. Devuelve la dirección de esa página."""
    with pytest.MonkeyPatch.context() as mp:
        for v in ("SITE_URL", "RAILWAY_PUBLIC_DOMAIN", "PANEL_URL"):
            mp.delenv(v, raising=False)
        spec = importlib.util.spec_from_file_location("build_site", RAIZ / "scripts" / "build_site.py")
        build_site = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_site)
        sitio = tmp_path_factory.mktemp("presentacion") / "site"
        build_site.construir(RAIZ / "web", sitio)
    (sitio / "marco.html").write_text(MARCO_PRESENTACION, encoding="utf-8")
    servidor = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PUERTO_PRUEBA_MAQUETA") or 0)),
                                   partial(_Silencioso, directory=str(sitio)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}/marco.html"
    finally:
        servidor.shutdown()
        servidor.server_close()
        shutil.rmtree(sitio, ignore_errors=True)


@requiere_navegador
@pytest.mark.skipif(not (RAIZ / "web" / "data" / "propuesta.json").is_file(), reason="Sin los datos del sitio")
def test_la_maqueta_se_simula_desde_el_panel(tmp_path, marco_presentacion):
    r = _correr_node(tmp_path, NODE_MAQUETA, marco_presentacion, timeout=600)
    tema = r["tema"]
    assert tema in ("tarde", "atardecer")
    assert r["ir"]["tipo"] == "estado" and r["ir"]["paso"] == 3
    n = r["noche"]
    assert n["tipo"] == "estado" and n["aviso"] is None, n
    assert n["simulacion"] == {"hora": "noche", "dia": False, "luces": True, "partido": True}, n
    assert r["hora_noche"] == "noche" and r["fijada"] == "noche"
    assert r["velo_noche"] == "100%", r["velo_noche"]
    assert r["dia"]["simulacion"]["dia"] is True and r["dia"]["aviso"] is None and r["sol_se_mueve"], r["dia"]
    assert r["pausa"]["simulacion"]["dia"] is False and r["sol_quieto"]
    assert 1.5 < r["ciclo_s"] < 6, r["ciclo_s"]
    o = r["otro_paso"]
    assert o["paso"] == 4 and o["simulacion"] == {"hora": tema, "dia": False, "luces": None, "partido": False}, o
    assert r["hora_otro_paso"] == tema and r["velo_otro_paso"] == "", r["velo_otro_paso"]
    i = r["instalaciones"]
    assert i["tipo"] == "error" and "no queda en el encuadre" in i["error"], i
    assert r["mirador"]["tipo"] == "error" and "no está a la vista" in r["mirador"]["error"], r["mirador"]
    p = r["mirador_parcial"]
    assert p["tipo"] == "estado" and p["aviso"] == "parcial" and p["descartadas"][0]["clave"] == "simular.partido", p
    assert p["simulacion"]["hora"] == "atardecer"
    assert r["salud"]["tipo"] == "error" and "no es un control de la maqueta en Salud" in r["salud"]["error"], r["salud"]
    assert r["salud_noche"]["simulacion"]["hora"] == "noche"
    assert r["mismo_paso"]["simulacion"]["hora"] == "noche", r["mismo_paso"]
    e = r["escena"]
    assert e["tipo"] == "estado" and e["aviso"] is None and e["simulacion"]["partido"] is True, e
    assert e["simulacion"]["hora"] == "atardecer" and r["hora_escena"] == "atardecer"
    assert not r["errores"], r["errores"]
