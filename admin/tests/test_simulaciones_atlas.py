"""Las simulaciones del atlas: los controles de adentro de cada modelo 3D que el asistente acciona (`simular`).

* El catálogo data/propuesta/simulaciones.json ({inmersión: [control…]}): la forma de cada control (id, nombre, tipo,
  rangos, opciones), que cada inmersión exista en `tecnica.inmersiones` y que los rangos sean coherentes. La clave
  reservada «maqueta» (las simulaciones de la maqueta 3D: la hora, el día, las luces, el partido) tiene la misma forma,
  con `capitulos` (solo ella), y la maqueta sabe accionar cada uno (ACCIONADORES de web/js/propuesta/simulacion.js).
* Que el catálogo diga lo mismo que la página: los rangos y los escenarios del simulador sísmico son los del estudio de
  amenaza (web/data/sismo_amenaza.json), las exageraciones y los campos de color los de web/js/scenes/torre/sismo.js.
* Que el atlas sepa accionar cada control (la tabla ACCIONADORES de web/js/escenario.js, por vista y modo) y que
  scripts/build_propuesta.py los haya copiado como `controles` a cada inmersión de web/data/propuesta.json.
* Lo proyectado nunca lleva costos: ningún control (ni una opción) habla de plata, con la misma regla con que avisa
  build_propuesta.py, y bim.js no escribe cifras en pesos en el escenario.
* En Chromium, con el sitio que arma build_site.py: una página del mismo origen enmarca atlas.html?escenario=1, abre la
  torre en modo sismo con __escenario.ir y acciona cada control del catálogo con __escenario.simular; se comprueba lo que
  la página muestra (el valor del deslizador, el sismo que se calcula, arranca y se detiene; el instante pedido mientras
  calcula, sobre el resultado nuevo) y que lo que no vale vuelve como texto, sin lanzar. Y el modelo BIM recién abierto
  (los controles esperan a que cargue) y, en cada modo con sus controles encendidos, que la sala no vea plata ni datos
  de personas.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from test_agente_presentacion import requiere_navegador

ADMIN = Path(__file__).resolve().parents[1]
RAIZ = ADMIN.parent
SIMULACIONES = RAIZ / "data" / "propuesta" / "simulaciones.json"
GENERAL = RAIZ / "data" / "propuesta" / "general.json"
PROPUESTA_JSON = RAIZ / "web" / "data" / "propuesta.json"
AMENAZA = RAIZ / "web" / "data" / "sismo_amenaza.json"
ESCENARIO_JS = RAIZ / "web" / "js" / "escenario.js"
SISMO_JS = RAIZ / "web" / "js" / "scenes" / "torre" / "sismo.js"
BIM_JS = RAIZ / "web" / "js" / "scenes" / "torre" / "bim.js"
BUILD_PROPUESTA = RAIZ / "scripts" / "build_propuesta.py"

pytestmark = pytest.mark.skipif(not SIMULACIONES.is_file() or not GENERAL.is_file(),
                                reason="Sin data/propuesta (el panel desplegado aparte)")

ID = re.compile(r"[a-z0-9_]{1,40}")
TIPOS = {"accion", "numero", "opcion", "si_no"}
CAMPOS = {"id", "nombre", "tipo", "min", "max", "paso", "unidad", "opciones", "ayuda"}
SIMULACION_JS = RAIZ / "web" / "js" / "propuesta" / "simulacion.js"
AMBIENTE_JS = RAIZ / "web" / "js" / "propuesta" / "ambiente.js"
URBANISMO_JS = RAIZ / "web" / "js" / "propuesta" / "modulos" / "urbanismo.js"


def _cargar(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _catalogo() -> dict:
    """Las simulaciones de los modelos del atlas (sin la clave reservada «maqueta»)."""
    return {k: v for k, v in _cargar(SIMULACIONES).items() if k != "maqueta"}


def _maqueta() -> list:
    """Las simulaciones de la maqueta 3D (la clave «maqueta» del catálogo)."""
    return _cargar(SIMULACIONES).get("maqueta") or []


def _capitulos_tecnica() -> set:
    """Los capítulos de la presentación técnica: la portada, los módulos y el cronograma."""
    return {"portada", "ruta"} | set(_cargar(GENERAL).get("orden_modulos") or [])


def _inmersiones() -> dict:
    return {i["id"]: i for i in _cargar(GENERAL)["tecnica"]["inmersiones"]}


def _es_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _accionadores() -> dict:
    """{'vista:modo': {ids}} de la tabla ACCIONADORES de escenario.js (como la lee build_propuesta.py)."""
    js = ESCENARIO_JS.read_text(encoding="utf-8")
    claves = lambda t: set(re.findall(r"^\s+([a-z0-9_]+): \{ como:", t, re.M))
    tabla = re.search(r"^const ACCIONADORES = \{\n(.*?)^\};", js, re.M | re.S)
    assert tabla, "escenario.js no tiene la tabla ACCIONADORES"
    hay = {}
    for m in re.finditer(r"^  '([a-z]+:[a-z0-9_]+)': (?:([A-Z_]+),|\{\n(.*?)^  \},)", tabla.group(1), re.M | re.S):
        if m.group(2):
            c = re.search(rf"^const {m.group(2)} = \{{\n(.*?)^\}};", js, re.M | re.S)
            assert c, f"escenario.js no define {m.group(2)}"
            hay[m.group(1)] = claves(c.group(1))
        else:
            hay[m.group(1)] = claves(m.group(3))
    return hay


# ───────────────────────────── El catálogo ─────────────────────────────

def test_catalogo_es_un_objeto_de_listas_por_inmersion_que_existe():
    cat, inm = _catalogo(), _inmersiones()
    assert isinstance(cat, dict) and cat
    for iid, lista in cat.items():
        assert iid in inm, f"{iid} no es una inmersión de tecnica.inmersiones"
        assert isinstance(lista, list) and lista, f"{iid}: sin controles (si no tiene, que no esté)"
    # empieza por el simulador sísmico; están todas las inmersiones de la torre que tienen controles en la página
    assert {"torre_sismo", "torre", "torre_pisos", "torre_recorrido", "torre_laboratorio", "torre_bim"} <= set(cat)


def test_cada_control_tiene_la_forma_comun():
    for iid, lista in [*_catalogo().items(), ("maqueta", _maqueta())]:
        ids, nombres = set(), set()
        for c in lista:
            donde = f"{iid}/{c.get('id')}"
            assert isinstance(c.get("id"), str) and ID.fullmatch(c["id"]), donde
            assert c["id"] not in ids, f"{donde}: id repetido"
            ids.add(c["id"])
            # (solo los de la maqueta dicen en qué capítulos valen)
            assert set(c) <= CAMPOS | ({"capitulos"} if iid == "maqueta" else set()), f"{donde}: campos de más {set(c) - CAMPOS}"
            if "capitulos" in c:
                assert isinstance(c["capitulos"], list) and c["capitulos"] and set(c["capitulos"]) <= _capitulos_tecnica(), donde
            assert c.get("tipo") in TIPOS, donde
            nombre = c.get("nombre")
            assert isinstance(nombre, str) and nombre.strip(), f"{donde}: sin nombre"
            assert nombre.strip().lower() not in nombres, f"{donde}: nombre repetido (se piden también por nombre)"
            nombres.add(nombre.strip().lower())
            if "ayuda" in c:
                assert isinstance(c["ayuda"], str) and 10 <= len(c["ayuda"]) <= 220, f"{donde}: ayuda de una frase"
            if c["tipo"] == "opcion":
                ops = c.get("opciones")
                assert isinstance(ops, list) and len(ops) >= 2, f"{donde}: una opción pide al menos dos"
                vistos = set()
                for o in ops:
                    assert set(o) == {"id", "nombre"}, f"{donde}: opción {o}"
                    assert ID.fullmatch(o["id"]) and o["id"] not in vistos, f"{donde}: opción {o['id']}"
                    assert isinstance(o["nombre"], str) and o["nombre"].strip(), f"{donde}: opción sin nombre"
                    vistos.add(o["id"])
            else:
                assert "opciones" not in c, donde
            if c["tipo"] != "numero":
                assert not {"min", "max", "paso", "unidad"} & set(c), f"{donde}: rangos solo en los números"


def test_rangos_coherentes():
    for iid, lista in [*_catalogo().items(), ("maqueta", _maqueta())]:
        for c in (x for x in lista if x["tipo"] == "numero"):
            donde = f"{iid}/{c['id']}"
            mn, mx, paso = c.get("min"), c.get("max"), c.get("paso")
            assert _es_num(mn) and _es_num(mx) and mn < mx, donde
            assert paso is None or (_es_num(paso) and 0 < paso <= mx - mn), donde
            if paso:
                n = (mx - mn) / paso
                assert abs(n - round(n)) < 1e-6, f"{donde}: el rango no es un número entero de pasos"
            assert c.get("unidad") is None or isinstance(c["unidad"], str), donde


def _regla_de_plata():
    """`habla_de_plata` de scripts/build_propuesta.py, tal cual (el guion arma el sitio al importarlo: se toma su código)."""
    js = BUILD_PROPUESTA.read_text(encoding="utf-8")
    codigo = re.search(r"^PLATA = .*?^    return bool\(.*?\n", js, re.M | re.S)
    assert codigo, "build_propuesta.py no tiene la regla PLATA / habla_de_plata"
    ns = {"re": re}
    exec(codigo.group(0), ns)
    return ns["habla_de_plata"], ns["PLATA_AYUDA"]


def test_lo_proyectado_no_lleva_plata():
    """Lo que el asistente acciona se ve en la sala, y lo proyectado nunca lleva costos: ni el coloreado por capítulo
    del presupuesto (5D) ni la pestaña de costos. build_propuesta.py avisa (y la CI falla) si un control o una opción
    habla de plata; bim.js, además, no escribe cifras en pesos en el escenario."""
    habla, ayuda = _regla_de_plata()
    for iid, lista in [*_catalogo().items(), ("maqueta", _maqueta())]:
        for c in lista:
            donde = f"{iid}/{c['id']}"
            assert not habla(c["id"]) and not habla(c["nombre"]) and not habla(c.get("ayuda"), ayuda), donde
            for o in c.get("opciones") or []:
                assert not habla(o["id"]) and not habla(o["nombre"]), f"{donde}.{o['id']}"
    # la regla reconoce lo que se quitó (y no confunde lo que no es plata)
    for t in ("colores_5d", "Colorear por capítulo del presupuesto (5D)", "5d", "5D: costo", "Valor del modelo", "precio_unitario",
              "Costos", "$ 3.000"):
        assert habla(t), t
    for t in ("magnitud", "Colorear por", "Construir la torre en el tiempo (4D)", "Escenario sísmico", "equipos", "valoracion",
              "Velocidad de reproducción", "Disciplina: Dotación"):
        assert not habla(t), t
    assert not habla("el valor de la magnitud", ayuda) and habla("el capítulo del presupuesto que lo paga", ayuda)
    bim = {c["id"]: c for c in _catalogo()["torre_bim"]}
    assert "colores_5d" not in bim and "5d" not in {o["id"] for o in bim["herramienta"]["opciones"]}
    esc = ESCENARIO_JS.read_text(encoding="utf-8")
    assert "colores_5d" not in esc and "pestana: '5d'" not in esc
    # bim.js: en el escenario, las cifras en pesos no se escriben y la leyenda del 5D nombra solo los capítulos
    js = BIM_JS.read_text(encoding="utf-8")
    assert "const SIN_PLATA = document.documentElement.hasAttribute('data-escenario');" in js
    for f in ("millones", "cop"):
        assert re.search(rf"^const {f} = \(v\) => \(!SIN_PLATA && ", js, re.M), f
    assert "${SIN_PLATA ? '' : `: ${millones(c.valor)}`}" in js and "costo && !SIN_PLATA" in js


def test_el_atlas_espera_lo_que_hace_falta():
    """Reproducir y el instante esperan a que termine el cálculo en curso (con el resultado anterior a la vista no dejarían
    nada del nuevo); los controles del BIM, a que cargue el modelo (antes sus botones están pero no hacen nada)."""
    js = ESCENARIO_JS.read_text(encoding="utf-8")
    for cid in ("reproducir", "instante"):
        assert re.search(rf"^      {cid}: \{{ como: [^\n]*libre: '\[data-s=\"cancelar\"\]'", js, re.M), cid
    assert "if (a.libre && usable(buscar(ac, a.libre))) return null;" in js
    bim = re.search(r"^  'torre:bim': \{\n(.*?)^    controles:", js, re.M | re.S).group(1)
    assert "listo: '[data-bim-listo]'," in bim and "if (ac.listo && !(await hasta(" in js
    assert "elPanel.dataset.bimListo = '';" in BIM_JS.read_text(encoding="utf-8")
    # en la sala, el panel del simulador no se ve: la línea del resumen no le pide pulsar «Calcular»
    sismo = SISMO_JS.read_text(encoding="utf-8")
    assert "'falta calcular'" in sismo and "pulsa «Calcular»" not in sismo


def test_sismo_coincide_con_la_pagina():
    """Los rangos del deslizador y los escenarios salen del estudio de amenaza; las exageraciones y los campos de color,
    del código del simulador: si cambian allá, el catálogo se queda atrás y el asistente pediría lo que no hay."""
    sismo = {c["id"]: c for c in _catalogo()["torre_sismo"]}
    for k in ("calcular", "reproducir", "magnitud", "instante", "cancelar"):
        assert k in sismo, k
    assert sismo["calcular"]["tipo"] == "accion" and sismo["reproducir"]["tipo"] == "si_no"
    if AMENAZA.is_file():
        a = _cargar(AMENAZA)
        ctl = a.get("controles") or {}
        for cid, k in (("magnitud", "Mw"), ("profundidad", "profundidad_km"), ("distancia", "distancia_epicentral_km"),
                       ("suelo", "vs30_m_s")):
            assert (sismo[cid]["min"], sismo[cid]["max"], sismo[cid]["paso"]) == (ctl[k]["min"], ctl[k]["max"], ctl[k]["paso"]), cid
        assert [o["id"] for o in sismo["escenario"]["opciones"]] == [e["id"] for e in a["escenarios"]]
    js = SISMO_JS.read_text(encoding="utf-8")
    exag = re.search(r"const EXAGERACIONES = \[([^\]]*)\]", js).group(1)
    assert [o["id"] for o in sismo["exageracion"]["opciones"]] == ["auto"] + re.findall(r"\d+", exag)
    campos = re.search(r"const CAMPOS = \{(.*?)\n\};", js, re.S).group(1)
    assert [o["id"] for o in sismo["colorear"]["opciones"]] == re.findall(r"^  (\w+): \[", campos, re.M)
    for cid, nombre in (("muros", "muros"), ("histeresis", "histeresis"), ("calidad", "calidad")):
        valores = re.findall(r"\['(\w+)', '", re.search(rf"radio\('{nombre}', '[^']*', \[(.*?)\]\)\}}", js).group(1))
        assert [o["id"] for o in sismo[cid]["opciones"]] == valores, cid


def test_el_atlas_sabe_accionar_cada_control():
    hay, inm = _accionadores(), _inmersiones()
    for iid, lista in _catalogo().items():
        clave = f"{inm[iid]['vista']}:{inm[iid]['modo']}"
        assert clave in hay, f"{iid}: escenario.js no tiene ACCIONADORES['{clave}']"
        faltan = {c["id"] for c in lista} - hay[clave]
        assert not faltan, f"{iid}: el atlas no sabe accionar {sorted(faltan)}"
    # el recorrido y el laboratorio son el mismo modo de la torre: los mismos controles
    cat = _catalogo()
    assert cat["torre_recorrido"] == cat["torre_laboratorio"]


def test_la_maqueta_sabe_accionar_cada_control():
    """La maqueta 3D acciona sus controles con la tabla ACCIONADORES de simulacion.js (como la lee build_propuesta.py);
    las horas son las de ambiente.js, en su orden; el partido vive en urbanismo.js (`simulaciones: { partido }`) y solo
    vale ahí; ninguna inmersión se llama «maqueta»."""
    maq = {c["id"]: c for c in _maqueta()}
    assert list(maq) == ["hora", "reproducir_dia", "luces", "partido"]
    js = SIMULACION_JS.read_text(encoding="utf-8")
    tabla = re.search(r"const ACCIONADORES = \{\n(.*?)\n  \};", js, re.S)
    assert tabla, "simulacion.js no tiene la tabla ACCIONADORES"
    claves = lambda t: set(re.findall(r"^ {4}([a-z0-9_]+): ", t.group(1), re.M))   # noqa: E731
    assert set(maq) <= claves(tabla)
    # la tabla se lee hasta su propio cierre (a 2 espacios), no hasta el primer `};` de una función de adentro: un
    # control escrito después del partido también cuenta
    otra = js.replace("\n  };\n  const controles = ", "\n    lluvia: (v) => true,\n  };\n  const controles = ", 1)
    assert otra != js and "lluvia" in claves(re.search(r"const ACCIONADORES = \{\n(.*?)\n  \};", otra, re.S))
    assert "import { validar } from '../escenario.js';" in js   # la misma regla del valor que el atlas
    horas = re.search(r"export const ORDEN_HORAS = \[([^\]]*)\]", AMBIENTE_JS.read_text(encoding="utf-8"))
    assert horas and [o["id"] for o in maq["hora"]["opciones"]] == re.findall(r"'([a-z0-9_]+)'", horas.group(1))
    assert maq["reproducir_dia"]["tipo"] == maq["luces"]["tipo"] == maq["partido"]["tipo"] == "si_no"
    assert re.search(r"export const DURACION_DIA = (\d+);", js).group(1) == "24" and "24 segundos" in maq["reproducir_dia"]["ayuda"]
    assert maq["partido"]["capitulos"] == ["urbanismo"] and "Solo con la cancha a la vista" in maq["partido"]["ayuda"]
    # las luces, solo donde hay luminarias que se vean (en los demás capítulos encenderlas no cambiaba nada)
    assert maq["luces"]["capitulos"] == ["vivienda", "urbanismo"]
    assert all("capitulos" not in c for k, c in maq.items() if k not in ("partido", "luces"))
    urb = URBANISMO_JS.read_text(encoding="utf-8")
    assert "simulaciones: {" in urb and re.search(r"^\s+partido: \{ pieza: ", urb, re.M)
    assert "maqueta" not in _inmersiones() and "export function validar(c, valor)" in ESCENARIO_JS.read_text(encoding="utf-8")


@pytest.mark.skipif(not PROPUESTA_JSON.is_file(), reason="Sin web/data/propuesta.json")
def test_propuesta_json_lleva_los_controles_en_cada_inmersion():
    """build_propuesta.py copia el catálogo tal cual (sin unir cifras y unidades) a cada inmersión; [] si no tiene."""
    cat = _catalogo()
    tec = _cargar(PROPUESTA_JSON)["tecnica"]
    inms = tec["inmersiones"]
    assert {i["id"] for i in inms} == set(_inmersiones())
    for i in inms:
        assert i.get("controles") == cat.get(i["id"], []), f"{i['id']}: corre python3 scripts/build_propuesta.py"
    # y los de la maqueta 3D, tal cual (con sus capítulos), aparte
    assert tec.get("simulaciones_maqueta") == _maqueta(), "corre python3 scripts/build_propuesta.py"


# ───────────────────────────── simular en Chromium ─────────────────────────────

NODE_SIMULAR = r"""// El simulador sísmico manejado desde un marco del mismo origen. Uso: node <guion> <url de la página que enmarca el atlas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
const [url] = process.argv.slice(2);
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1100, height: 700 }, deviceScaleFactor: 1 });
const errores = [];
page.on('pageerror', (e) => errores.push(String(e)));
await page.goto(url);
await page.waitForFunction(() => !!document.getElementById('m').contentWindow.__escenario, null, { timeout: 60000 });
const E = (expr, arg) => page.evaluate(new Function('arg', `const E = document.getElementById('m').contentWindow.__escenario, D = document.getElementById('m').contentWindow.document; return (async () => { ${expr} })();`), arg);
const sim = (c, v) => E('return E.simular(arg.c, arg.v);', { c, v });
const q = (sel, prop = 'value') => E(`const el = D.querySelector(arg.sel); return el ? (arg.prop === 'text' ? el.textContent : el[arg.prop] ?? el.getAttribute(arg.prop)) : null;`, { sel, prop });
const listo = () => page.waitForFunction(() => /^Listo/.test(document.getElementById('m').contentWindow.document.querySelector('[data-o="estado"]')?.textContent || ''), null, { timeout: 180000 });
const r = { errores_simular: {}, controles: {} };
await E("return E.ir({ vista: 'torre', modo: 'sismo' });");
// el control del modo se espera mientras carga: la primera orden llega antes de que exista el panel
r.primera = await sim('leyenda', true);
await listo();
r.lista = (await E('return E.controles();')).map((c) => c.id);
for (const [n, c, v] of [['no_existe', 'noexiste'], ['fuera_de_rango', 'magnitud', 99], ['no_es_numero', 'magnitud', 'x'], ['si_no_texto', 'reproducir', 'si'], ['accion_con_valor', 'calcular', 3], ['opcion_que_no_hay', 'escenario', 'marte'], ['cancelar_sin_calculo', 'cancelar']]) {
  const x = await sim(c, v);
  r.errores_simular[n] = typeof x === 'string' ? 'texto' : x;
}
// cada control del catálogo con un valor válido (las acciones y la reproducción, aparte)
for (const c of await E('return E.controles();')) {
  if (['calcular', 'cancelar', 'reproducir'].includes(c.id)) continue;
  const v = c.tipo === 'numero' ? c.min + Math.round((c.max - c.min) / c.paso / 3) * c.paso : c.tipo === 'opcion' ? c.opciones[Math.min(1, c.opciones.length - 1)].id : c.tipo === 'si_no' ? true : undefined;
  r.controles[c.id] = await sim(c.id, v);
}
r.calidad_baja = await q('input[name="sismo-calidad"][value="baja"]', 'checked');
r.magnitud = [await sim('magnitud', 7.04), await q('[data-c="Mw"]'), await q('[data-o="Mw"]', 'text')];
r.resumen_sin_calcular = await q('[data-o="resumen"]', 'text');
r.calcular = await sim('calcular');
r.cancelar_boton_visible = await q('[data-s="cancelar"]', 'hidden') === false;
r.calcular_mientras_calcula = await sim('calcular');
await listo();
r.g_estado = await q('[data-o="g-estado"]', 'text');
await page.waitForTimeout(500);
r.tiembla_al_terminar = await q('[data-s="play"]', 'aria-pressed');
r.reproducir_no = await sim('reproducir', false);
const t1 = await q('[data-c="t"]'); await page.waitForTimeout(600); const t2 = await q('[data-c="t"]');
r.quieto = [t1, t2];
r.instante_0 = [await sim('instante', 0), await q('[data-c="t"]')];
r.reproducir_si = await sim('reproducir', true);
await page.waitForTimeout(1200);
r.avanza = +(await q('[data-c="t"]'));
r.pausa_texto = await q('[data-s="play"]', 'text');
await sim('reproducir', false);
const max = +(await q('[data-c="t"]', 'max'));
r.instante_50 = [await sim('instante', 50), +(await q('[data-c="t"]')), Math.round(max / 2)];
// una tanda seguida, como la manda un paso del plan: el instante y la pausa esperan el resultado nuevo (con el anterior a
// la vista, accionarlos no dejaba nada: al llegar, el nuevo arrancaba solo desde el comienzo)
r.tanda = await E("return Promise.all([E.simular('magnitud', 6.5), E.simular('calcular'), E.simular('instante', 50), E.simular('reproducir', false)]);");
r.tanda_estado = await q('[data-o="estado"]', 'text');
r.tanda_g = await q('[data-o="g-estado"]', 'text');
const maxN = +(await q('[data-c="t"]', 'max'));
r.tanda_t = [+(await q('[data-c="t"]')), Math.round(maxN / 2), maxN !== max];
await page.waitForTimeout(2500);
r.tanda_quieto = [+(await q('[data-c="t"]')), await q('[data-s="play"]', 'aria-pressed')];
await E("return E.ir({ vista: 'torre', modo: 'torre' });");
r.fuera_del_modo = typeof (await sim('magnitud', 6)) === 'string';
r.controles_torre = (await E('return E.controles();')).map((c) => c.id);
r.errores = errores;
console.log(JSON.stringify(r));
await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def marco_atlas(tmp_path_factory):
    """El sitio que arma build_site.py (una vez para las pruebas en Chromium de este archivo), servido en un puerto libre,
    con una página del mismo origen que enmarca atlas.html?escenario=1. Devuelve la dirección de esa página."""
    with pytest.MonkeyPatch.context() as mp:
        for v in ("SITE_URL", "RAILWAY_PUBLIC_DOMAIN", "PANEL_URL"):
            mp.delenv(v, raising=False)
        spec = importlib.util.spec_from_file_location("build_site", RAIZ / "scripts" / "build_site.py")
        build_site = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_site)
        sitio = tmp_path_factory.mktemp("atlas") / "site"
        build_site.construir(RAIZ / "web", sitio)
    # el catálogo que lee el atlas es el de hoy (data/propuesta/simulaciones.json), aunque web/data no se haya reconstruido
    datos = _cargar(sitio / "data" / "propuesta.json")
    for i in datos["tecnica"]["inmersiones"]:
        i["controles"] = _catalogo().get(i["id"], [])
    (sitio / "data" / "propuesta.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    (sitio / "marco.html").write_text('<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Marco</title></head>'
                                      '<body style="margin:0"><iframe id="m" src="atlas.html?escenario=1#torre" '
                                      'style="border:0;width:100vw;height:100vh"></iframe></body></html>', encoding="utf-8")
    # (PUERTO_PRUEBA_ATLAS: un puerto fijo, para correrla junto a otros servidores con puertos asignados)
    servidor = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PUERTO_PRUEBA_ATLAS") or 0)),
                                   partial(_Silencioso, directory=str(sitio)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}/marco.html"
    finally:
        servidor.shutdown()
        servidor.server_close()
        shutil.rmtree(sitio, ignore_errors=True)


def _correr_node(tmp_path, guion: str, url: str, timeout: int = 420) -> dict:
    (tmp_path / "guion.cjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "guion.cjs"), url], capture_output=True, text=True, timeout=timeout, cwd=ADMIN)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


@requiere_navegador
@pytest.mark.skipif(not PROPUESTA_JSON.is_file() or not AMENAZA.is_file(), reason="Sin los datos del sitio")
def test_simular_el_sismo_desde_un_marco_del_mismo_origen(tmp_path, marco_atlas):
    r = _correr_node(tmp_path, NODE_SIMULAR, marco_atlas)
    assert r["primera"] is True
    assert r["lista"] == [c["id"] for c in _catalogo()["torre_sismo"]]
    assert set(r["errores_simular"].values()) == {"texto"}, r["errores_simular"]
    assert all(v is True for v in r["controles"].values()), r["controles"]
    assert r["calidad_baja"] is True
    assert r["magnitud"] == [True, "7", "7,0"]
    assert "Mw 7,0" in r["resumen_sin_calcular"] and r["resumen_sin_calcular"].endswith("falta calcular")
    assert r["calcular"] is True and r["cancelar_boton_visible"] and r["calcular_mientras_calcula"] is True
    assert "Mw 7,0" in r["g_estado"]
    assert r["tiembla_al_terminar"] == "true"
    assert r["reproducir_no"] is True and r["quieto"][0] == r["quieto"][1]
    assert r["instante_0"] == [True, "0"]
    assert r["reproducir_si"] is True and r["avanza"] > 0 and r["pausa_texto"] == "Pausa"
    assert r["instante_50"][0] is True and r["instante_50"][1] == r["instante_50"][2]
    assert r["tanda"] == [True, True, True, True] and r["tanda_estado"].startswith("Listo") and "Mw 6,5" in r["tanda_g"]
    assert r["tanda_t"][0] == r["tanda_t"][1] and r["tanda_quieto"] == [r["tanda_t"][0], "false"], (r["tanda_t"], r["tanda_quieto"])
    assert r["fuera_del_modo"] and r["controles_torre"] == ["proyecto_tipo"]
    assert not r["errores"], r["errores"]


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


NODE_BIM_Y_PLATA = r"""// El modelo BIM recién abierto y lo que la sala ve en cada modo. Uso: node <guion> <url de la página que enmarca el atlas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
const [url] = process.argv.slice(2);
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1400, height: 820 }, deviceScaleFactor: 1 });
const errores = [];
page.on('pageerror', (e) => errores.push(String(e)));
await page.goto(url);
await page.waitForFunction(() => !!document.getElementById('m').contentWindow.__escenario, null, { timeout: 60000 });
const E = (expr, arg) => page.evaluate(new Function('arg', `const E = document.getElementById('m').contentWindow.__escenario, W = document.getElementById('m').contentWindow, D = W.document; return (async () => { ${expr} })();`), arg);
const sim = (c, v) => E('return E.simular(arg.c, arg.v);', { c, v });
// lo que la sala ve: los textos a la vista dentro de la ventana del atlas que hablan de plata o de personas
const aLaVista = () => E(`const out = []; const w = D.createTreeWalker(D.body, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const el = n.parentElement; if (!el || !n.textContent.trim()) continue; const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < W.innerHeight && r.left < W.innerWidth && el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) out.push(n.textContent.trim()); }
  return out;`);
const PLATA = /\$\s?\d|millones|\bCOP\b|precio|costo|presupuesto|valor del modelo/i, PERSONAS = /@|\d{7,}/;
const mira = async () => { const t = await aLaVista(); return { plata: t.filter((x) => PLATA.test(x)).slice(0, 6), personas: t.filter((x) => PERSONAS.test(x)).slice(0, 6), textos: t.length }; };
const r = { modos: {} };
// 1. El BIM recién abierto: el panel aparece antes que el modelo; los controles esperan a que cargue (antes daban true
//    sin hacer nada)
await E("return E.ir({ vista: 'torre', modo: 'bim' });");
r.frio = await E("return Promise.all([E.simular('herramienta', 'cortes'), E.simular('corte', 'p2')]);");
r.corte = await E("const b = D.querySelector('[data-cn=\"P2\"]'); return [b?.getAttribute('aria-pressed') ?? null, !!D.querySelector('[data-b=\"sincorte\"]')];");
r.listo = await E("return !!D.querySelector('[data-bim-listo]');");
// 2. Lo de plata ya no está en el catálogo
r.colores_5d = await sim('colores_5d', true);
r.pestana_5d = await sim('herramienta', '5d');
// 3. La defensa de bim.js: aunque alguien pulse «Colorear por capítulo» (la pestaña 5D, oculta en el escenario), la
//    leyenda de la sala nombra los capítulos sin su valor
r.ley5d = await E(`D.querySelector('.bim-pestanas button[data-p="5d"]').click(); await new Promise((ok) => setTimeout(ok, 50));
  D.querySelector('[data-b="c5d"]').click(); await new Promise((ok) => setTimeout(ok, 300));
  const l = D.querySelector('[data-b="ley"]'); return [l && !l.hidden ? l.textContent : null, D.querySelector('[data-b="chip"]')?.textContent || ''];`);
r.vista_5d = await mira();
// 4. Cada modo con sus controles encendidos: la sala no ve plata ni datos de personas
const pasos = [
  ['torre', [['proyecto_tipo', true]], 5000],
  ['pisos', [['piso', '2']], 5000],
  ['recorrido', [['nivel', 'p2'], ['faltantes', true], ['cumplimiento', true], ['contraste', true], ['infraestructura', true], ['mapa', true], ['laboratorio']], 6000],
  ['sismo', [['equipos', '2'], ['leyenda', true], ['colorear', 'rotacion']], 9000],
  ['bim', [['herramienta', 'comportamiento'], ['colorear_sismo', 'dc'], ['leyenda', true], ['herramienta', 'interferencias'], ['herramienta', 'ifc'], ['herramienta', '4d'], ['fecha_obra', 60], ['espacios', true]], 3000],
];
for (const [modo, ctls, ms] of pasos) {
  await E('return E.ir({ vista: "torre", modo: arg });', modo);
  await page.waitForTimeout(ms);
  const res = {};
  for (const [c, v] of ctls) res[c] = await sim(c, v);
  await page.waitForTimeout(1500);
  r.modos[modo] = { controles: res, ...(await mira()) };
}
r.errores = errores;
console.log(JSON.stringify(r));
await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
@pytest.mark.skipif(not PROPUESTA_JSON.is_file() or not AMENAZA.is_file(), reason="Sin los datos del sitio")
def test_el_bim_recien_abierto_y_lo_que_la_sala_ve_en_cada_modo(tmp_path, marco_atlas):
    """Los controles del BIM pedidos antes de que cargue el modelo esperan (antes daban true sin hacer nada); lo de plata
    ya no se puede accionar, y aunque se pulse a mano, la leyenda proyectada no lleva cifras; y con los controles de cada
    modo encendidos, nada de lo que se ve habla de plata ni de personas."""
    r = _correr_node(tmp_path, NODE_BIM_Y_PLATA, marco_atlas, timeout=600)
    assert r["frio"] == [True, True] and r["corte"] == ["true", True] and r["listo"] is True, r
    assert isinstance(r["colores_5d"], str) and "no tiene el control «colores_5d»" in r["colores_5d"]
    assert isinstance(r["pestana_5d"], str) and "no tiene la opción «5d»" in r["pestana_5d"]
    ley, chip = r["ley5d"]
    assert ley and ley.startswith("LeyendaCapítulo de obra") and "$" not in ley and "millones" not in ley, ley
    assert chip == "Modelo coloreado por capítulo de obra"
    assert r["vista_5d"]["plata"] == [] and r["vista_5d"]["personas"] == [], r["vista_5d"]
    assert set(r["modos"]) == {"torre", "pisos", "recorrido", "sismo", "bim"}
    for modo, x in r["modos"].items():
        assert all(v is True for v in x["controles"].values()), (modo, x["controles"])
        assert x["textos"] > 0 and x["plata"] == [] and x["personas"] == [], (modo, x)
    assert not r["errores"], r["errores"]


NODE_SISMO_SIN_RESULTADO = r"""// El simulador sísmico sin un sismo calculado, en un proyector con «reducir movimiento», y la primera reproducción de
// un resultado. Uso: node <guion> <url de la página que enmarca el atlas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
const [url] = process.argv.slice(2);
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const r = { errores: [] };
async function abrir(opciones) {
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 700 }, deviceScaleFactor: 1, ...opciones });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => r.errores.push(String(e)));
  await page.goto(url);
  await page.waitForFunction(() => !!document.getElementById('m').contentWindow.__escenario, null, { timeout: 60000 });
  const E = (expr, arg) => page.evaluate(new Function('arg', `const E = document.getElementById('m').contentWindow.__escenario, D = document.getElementById('m').contentWindow.document; return (async () => { ${expr} })();`), arg);
  const sim = (c, v) => E('return E.simular(arg.c, arg.v);', { c, v });
  const q = (sel, prop = 'value') => E(`const el = D.querySelector(arg.sel); return el ? (arg.prop === 'text' ? el.textContent : el[arg.prop] ?? el.getAttribute(arg.prop)) : null;`, { sel, prop });
  const listo = () => page.waitForFunction(() => /^Listo/.test(document.getElementById('m').contentWindow.document.querySelector('[data-o="estado"]')?.textContent || ''), null, { timeout: 180000 });
  await E("return E.ir({ vista: 'torre', modo: 'sismo' });");
  return { ctx, page, sim, q, listo };
}
const medir = async (f) => { const t = Date.now(); const v = await f(); return [v, Date.now() - t]; };
// 1. Con «reducir movimiento»: el cálculo de entrada, cancelado apenas arranca; sin resultado ni cálculo en curso,
//    el instante dice enseguida que falta calcular, pausar no tiene nada que pausar y Reproducir calcula antes (antes
//    esperaba 25 s en silencio); el resultado se reproduce solo al llegar, aunque el proyector reduzca el movimiento
{
  const { ctx, page, sim, q, listo } = await abrir({ reducedMotion: 'reduce' });
  await page.waitForFunction(() => { const b = document.getElementById('m').contentWindow.document.querySelector('[data-s="cancelar"]'); return !!b && !b.hidden; }, null, { timeout: 120000 });
  r.cancelar = await sim('cancelar');
  r.sin_resultado = [await q('[data-s="play"]', 'disabled'), await q('[data-s="cancelar"]', 'hidden')];
  r.instante = await medir(() => sim('instante', 50));
  r.pausa = await medir(() => sim('reproducir', false));
  r.reproducir = await medir(() => sim('reproducir', true));
  r.calcula = (await q('[data-s="cancelar"]', 'hidden')) === false || /^Listo/.test(await q('[data-o="estado"]', 'text') || '');
  await listo();
  await page.waitForTimeout(600);
  r.tiembla = await q('[data-s="play"]', 'aria-pressed');
  await sim('reproducir', false);
  await ctx.close();
}
// 2. Sin «reducir movimiento»: el cálculo de entrada no se reproduce solo y queda en su pico; la primera vez que se
//    reproduce arranca desde el comienzo (antes, desde el pico: la sala no veía llegar el sismo)
{
  const { ctx, page, sim, q, listo } = await abrir({});
  await listo();
  await page.waitForTimeout(400);
  r.entrada = [await q('[data-s="play"]', 'aria-pressed'), +(await q('[data-c="t"]'))];
  r.reproducir_tras_entrada = await sim('reproducir', true);
  r.t_al_reproducir = +(await q('[data-c="t"]'));
  await sim('reproducir', false);
  await ctx.close();
}
console.log(JSON.stringify(r));
await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
@pytest.mark.skipif(not PROPUESTA_JSON.is_file() or not AMENAZA.is_file(), reason="Sin los datos del sitio")
def test_reproducir_sin_un_sismo_calculado_y_desde_el_comienzo(tmp_path, marco_atlas):
    """Lo que encontró la prueba de punta a punta del agente: Reproducir sin un sismo calculado ni un cálculo en curso
    esperaba 25 s en silencio (la presentación lo daba por hecho y la torre no se movía); con «reducir movimiento»,
    calcular no hacía temblar la torre; y la primera reproducción de un resultado arrancaba en el pico."""
    r = _correr_node(tmp_path, NODE_SISMO_SIN_RESULTADO, marco_atlas, timeout=600)
    assert r["cancelar"] is True and r["sin_resultado"] == [True, True], r
    instante, ms = r["instante"]
    assert isinstance(instante, str) and "necesita un cálculo terminado" in instante and "«Calcular el sismo»" in instante, instante
    assert ms < 2000, ms
    assert r["pausa"][0] is True and r["pausa"][1] < 2000, r["pausa"]
    assert r["reproducir"][0] is True and r["reproducir"][1] < 2000 and r["calcula"], (r["reproducir"], r["calcula"])
    assert r["tiembla"] == "true", r
    pressed, pico = r["entrada"]
    assert pressed == "false" and pico > 0, r["entrada"]
    assert r["reproducir_tras_entrada"] is True and r["t_al_reproducir"] < pico, (r["t_al_reproducir"], pico)
    assert not r["errores"], r["errores"]
