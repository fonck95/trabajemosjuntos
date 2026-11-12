"""Diseño responsivo del panel (cualquier dispositivo), en Chromium contra el panel de verdad (uvicorn, en /panel como en
Railway) con personas, coincidencias y reuniones inventadas. Lo de la auditoría que una prueba de API no ve:

* Sin desborde horizontal en el panel, Habitantes, la ficha, Calidad y Reuniones en 320×568, 390×844 (celulares,
  táctiles), 820×1180 (tableta vertical, táctil), 1024×768, 1280×800 y 1400×900, en claro y en oscuro. La tabla de
  Habitantes no esconde columnas tras un desplazamiento sin aviso (P3) y en escritorio con ratón las pestañas se
  envuelven en vez de cortarse (P4).
* En pantalla táctil, todo lo que se toca mide 44 px o más (P7), medido ANTES de cualquier captura de página completa:
  en la emulación móvil, `screenshot({ fullPage: true })` hace que `(pointer: coarse)` deje de cumplirse en ese contexto
  y las medidas siguientes salen falsas. Ningún campo de texto o lista mide menos de 16 px a 900 px o menos (iOS
  amplía la página), tampoco los de «Completar» (P5).
* La ficha en el celular: el título a su tamaño, la barra de acciones sin botones fuera de la pantalla (las que no
  caben pasan a «Más», que las ofrece y las ejecuta), «Unir» y «Suprimir» en el menú ⋯, los avisos encima de la barra,
  y «Cerrar sesión» y el tema alcanzables con el menú abierto (P1, P6, P9).
* Un diálogo con algo escrito pide confirmar antes de descartarlo al tocar el fondo o con Escape; sin nada escrito se
  cierra sin preguntar; el botón de cerrar mide 44×44 (P5). Mientras «Completar» guarda (el PATCH retenido hasta que
  la prueba lo suelta, sin relojes), Escape, el fondo y dos Escape seguidos no preguntan ni cierran, y al terminar se
  cierra sin preguntar ni dejar una pregunta suelta. Igual en «Nueva persona» cuando guarda por «Es esta» (el nombre de
  una que ya está y otro teléfono, en escritorio) o por «Completar esa ficha con lo que escribí» (su cédula, en el
  celular): con el PATCH retenido no hay pregunta, y al soltarlo se abre esa ficha con lo escrito y sin diálogos.
  «Nueva persona» que el navegador cerró solo (Escape repetido) y `dialogo` volvió a abrir sigue contando como
  pendiente: un 401 abre el ingreso en un diálogo en vez de recargar.
* El menú lateral cerrado del celular es inerte (fuera del tabulador), al abrirse el foco entra en él y queda atrapado:
  lo que tapa el velo (la vista, la barra de arriba y el botón del asistente) queda inerte; Escape lo cierra y devuelve
  el foco; en escritorio nunca es inerte, tampoco al ensanchar la ventana (P8). Con agente.js retenido (red lenta) y el
  menú ya abierto, el asistente que se monta después también queda inerte y el tabulador no llega a su botón. Dentro
  del menú, solo en el celular, «Cerrar menú» (44 px, a la vista, sin montarse con la marca) está en el árbol de
  accesibilidad con el menú abierto (la barra de arriba no) y lo cierra devolviendo el foco a «Menú».
* El tema Sistema / Claro / Oscuro y la tarjeta destacada del panel visible en oscuro (P11).
* Sin violaciones de CSP ni errores de consola en ningún caso.

Más revisiones estáticas de app.css e index.html (`:hover` solo con ratón, movimiento reducido, `theme-color`).
Se salta si no hay Node con Playwright, salvo en el CI (allí falla en vez de pasar en silencio).
"""
import base64
import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pymongo
import pytest
import uvicorn

from conftest import MONGO, URI, insertar_personas, personas_inventadas
from test_agente_mapa import _png_plano, requiere_navegador

WEB = Path(__file__).resolve().parents[1] / "web"
CSS = (WEB / "css" / "app.css").read_text(encoding="utf-8")
TAMANOS = ("w320", "w390", "w820", "w1024", "w1280", "w1400")


def _sembrar(db) -> dict:
    """40 personas inventadas de dos bases (chips de fuente, abordaje y autorización en cada fila de Habitantes), una
    ficha completa para mirar (nombre largo, dos celulares, listas, líder, sin cédula para que «Completar» la pida),
    coincidencias pendientes de varios motivos y tres reuniones."""
    from app import db as bd
    tramites = personas_inventadas(24, semilla=57)
    cedulas = personas_inventadas(16, semilla=58)
    for i, p in enumerate(tramites):
        p["listas"] = ["LISTA INVENTADA A"] if i % 4 == 0 else []
    ids = insertar_personas(db, tramites, fuente="tramites") + insertar_personas(db, cedulas, fuente="cedulas")
    ficha = insertar_personas(db, [{
        "nombre": "MARIA DE LOS ANGELES ARRIETA BOHORQUEZ INVENTADA", "cedula": None, "telefono": "3159990001",
        "telefono2": "3159990002", "sexo": "F", "edad": 47, "direccion": "CALLE 49 # 45-12", "consentimiento": "si",
        "listas": ["LISTA INVENTADA A", "LISTA INVENTADA B"], "lider": True,
        "lat": 7.0062, "lon": -73.9112, "geo_precision": "direccion",
    }], fuente="tramites")[0]
    db.personas.update_one({"_id": ficha}, {"$set": {"fuentes": ["tramites", "cedulas"]}})
    otro = ids[30]
    # Dos fichas de trámites sin cédula y fuera de las coincidencias: «Completar» guarda una en cada tamaño
    sin_cedula = {"w390": ids[6], "w1400": ids[9]}
    assert all(tramites[i]["cedula"] is None for i in (6, 9))
    pares = [(ficha, otro, 0.91, "nombre_telefono"), (ids[1], ids[25], 0.86, "cruce_cedula"),
             (ids[2], ids[3], 0.74, "homonimo"), (ids[4], ids[5], 0.7, "variante")]
    db.coincidencias.insert_many([{"_id": i + 1, "persona_id": a, "candidato_id": b, "estado": "pendiente",
                                   "puntaje": s, "motivo": m, "detalle": {"palabras": 3}}
                                  for i, (a, b, s, m) in enumerate(pares)])
    ahora = bd.ahora()
    db.reuniones.insert_many([{
        "_id": i + 1, "titulo": t, "fecha": f, "hora": "18:00", "lugar_texto": "Caseta comunal inventada",
        "lugar_id": None, "lat": None, "lon": None, "tema": tema, "descripcion": None, "compromisos": None,
        "abierta_a_equipo": i == 0, "creado_por": "admin", "creado_por_uid": 0, "creado_en": ahora, "actualizado_en": ahora,
    } for i, (t, f, tema) in enumerate([("Reunión inventada con la junta de acción comunal del barrio", "2026-11-03", "Agua"),
                                        ("Reunión inventada de vivienda", "2026-10-21", "Vivienda"),
                                        ("Reunión inventada rural", "2026-09-30", None)])])
    # «Nueva persona» que guarda en una ficha que ya está: por «Es esta» (escritorio, el nombre y otro teléfono, como lo
    # reprodujo la revisión) o por «Completar esa ficha con lo que escribí» (celular, su cédula). Fuera de las
    # coincidencias y de «Completar», con nombre único y sin segundo teléfono: lo que se guarde se ve
    es_esta = {"w1400": {"id": ids[11], "nombre": tramites[11]["nombre"], "telefono2": "3001112233"},
               "w390": {"id": ids[13], "cedula": tramites[13]["cedula"], "telefono2": "3001112234"}}
    for i in (11, 13):
        assert sum(x["nombre"] == tramites[i]["nombre"] for x in tramites + cedulas) == 1 and not tramites[i].get("telefono2")
    assert tramites[13]["cedula"]
    return {"persona": ficha, "sin_cedula": sin_cedula, "es_esta": es_esta, "png": base64.b64encode(_png_plano()).decode()}


@pytest.fixture(scope="module")
def resultados(tmp_path_factory):
    """El panel de verdad en un puerto libre y el guion de Chromium con todos los casos: {caso: resultado}."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    from app.config import Config
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=URI,
                 mongodb_db=f"prueba_{uuid.uuid4().hex[:10]}", horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    tmp = tmp_path_factory.mktemp("responsivo")
    sitio = tmp / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 20
        while time.time() < fin and not (srv.started and app.state.panel is not None
                                         and getattr(app.state.panel.state, "listo", False)):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        datos = _sembrar(app.state.panel.state.db)
        (tmp / "datos.json").write_text(json.dumps(datos), encoding="utf-8")
        (tmp / "guion.cjs").write_text(GUION, encoding="utf-8")
        capturas = os.environ.get("CAPTURAS_RESPONSIVO") or str(tmp)  # para mirarlas a mano
        base = f"http://127.0.0.1:{sock.getsockname()[1]}/panel"
        r = subprocess.run(["node", str(tmp / "guion.cjs"), base, cfg.usuario, cfg.clave, str(tmp / "datos.json"),
                            capturas], capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
        casos = {c["nombre"]: c for c in json.loads(r.stdout.strip().splitlines()[-1])["casos"]}
        if os.environ.get("CAPTURAS_RESPONSIVO"):
            (Path(capturas) / "resultado-responsivo.json").write_text(json.dumps(casos, ensure_ascii=False, indent=1),
                                                                      encoding="utf-8")
        yield casos
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def _revisar(resultados: dict, nombre: str, prefijo: str = "") -> dict:
    caso = resultados[nombre]
    assert not caso.get("fallo"), (nombre, caso["fallo"])
    revisiones = {k: v for k, v in caso["revisiones"].items() if k.startswith(prefijo)}
    malas = {k: v for k, v in revisiones.items() if v is not True}
    assert revisiones and not malas, (nombre, malas, {k: v for k, v in caso.get("datos", {}).items() if k in malas})
    assert caso["errores"] == [], (nombre, caso["errores"])
    assert caso["csp"] == [], (nombre, caso["csp"])
    return caso


@requiere_navegador
@pytest.mark.parametrize("tamano", [*TAMANOS, "w390_oscuro", "w1400_oscuro"])
def test_sin_desborde_horizontal(resultados, tamano):
    """Ninguna vista es más ancha que la pantalla, la tabla de Habitantes cabe en su caja (tarjetas hasta 1100 px,
    columnas secundarias ocultas en anchos medios) y, con ratón, las pestañas no esconden ninguna."""
    _revisar(resultados, tamano, "sin_desborde")
    caso = resultados[tamano]
    for clave in ("tabla_cabe", "pestanas_enteras"):
        malas = {k: v for k, v in caso["revisiones"].items() if k.startswith(clave) and v is not True}
        assert not malas, (tamano, malas, {k: caso["datos"].get(k) for k in malas})


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w320", "w390", "w820", "w390_oscuro"])
def test_objetivos_tactiles_de_44_px(resultados, tamano):
    caso = _revisar(resultados, tamano, "tactil")
    assert any(k.startswith("tactil_vigente") for k in caso["revisiones"])


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w320", "w390", "w820"])
def test_campos_de_16_px_en_el_celular(resultados, tamano):
    _revisar(resultados, tamano, "campos_16")


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w320", "w390"])
def test_la_ficha_en_el_celular(resultados, tamano):
    """Título a su tamaño, barra sin botones ocultos (con «Más»), menú ⋯ de la cabecera, avisos encima de la barra y
    «Cerrar sesión» alcanzable con el menú abierto sobre la ficha."""
    _revisar(resultados, f"ficha_{tamano}")


@requiere_navegador
def test_la_barra_de_la_tableta_muestra_todas_las_acciones(resultados):
    _revisar(resultados, "ficha_w820")


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w390", "w1400"])
def test_dialogo_con_algo_escrito_pide_confirmar(resultados, tamano):
    _revisar(resultados, f"dialogo_{tamano}")


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w390", "w1400"])
def test_dialogo_guardando_no_pregunta_ni_cierra(resultados, tamano):
    """Lo escrito ya va al servidor: preguntar «¿Descartar?» sería falso y descartar dejaría la ficha sin lo guardado."""
    _revisar(resultados, f"guardando_{tamano}")


@requiere_navegador
@pytest.mark.parametrize("tamano", ["w1400", "w390"])
def test_nueva_persona_es_esta_guardando_no_pregunta(resultados, tamano):
    """«Es esta» (escritorio) y «Completar esa ficha con lo que escribí» (celular) también guardan: mientras el PATCH va
    al servidor, Escape y el fondo no preguntan «¿Descartar?» (la ficha se completa igual y la página se va a ella)."""
    _revisar(resultados, f"es_esta_{tamano}")


@requiere_navegador
def test_nueva_persona_reabierta_sigue_pendiente(resultados):
    caso = resultados["pendiente"]
    # Con lo que se vio (diálogos abiertos, cierres del navegador), un fallo dice en qué paso se perdió lo pendiente
    assert caso["revisiones"].get("sigue_pendiente") is True, caso.get("datos")
    _revisar(resultados, "pendiente")


@requiere_navegador
def test_menu_cerrado_inerte_y_foco(resultados):
    _revisar(resultados, "menu")


@requiere_navegador
def test_menu_abierto_antes_del_asistente(resultados):
    """El asistente llega tarde (agente.js retenido) con el menú abierto: también queda tapado e inerte."""
    _revisar(resultados, "menu_tarde")


@requiere_navegador
def test_menu_se_cierra_con_su_boton(resultados):
    """Con el menú abierto la barra de arriba es inerte: «Cerrar menú», dentro del menú, es el control con nombre que
    queda para cerrarlo sin teclado (lector de pantalla táctil)."""
    _revisar(resultados, "cerrar_menu")


@requiere_navegador
def test_tema_sistema_claro_oscuro(resultados):
    _revisar(resultados, "tema")


# ───────────────────────────── Revisiones estáticas ─────────────────────────────

def _fuera_de_hover(css: str) -> list[str]:
    """Selectores con `:hover` que no están dentro de un `@media (hover: hover)`: en una pantalla táctil el primer toque
    los deja pegados (la fila de la tabla, la tarjeta del panel, un botón) hasta tocar otra cosa."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    malos, pila, i, inicio = [], [], 0, 0
    while i < len(css):
        c = css[i]
        if c == "{":
            pila.append(css[inicio:i].strip())
            inicio = i + 1
        elif c == "}":
            if pila:
                pila.pop()
            inicio = i + 1
        elif c == ";" and not pila:
            inicio = i + 1
        i += 1
        if c == "{" and ":hover" in pila[-1] and not pila[-1].startswith("@"):
            if not any(re.match(r"@media[^{]*\(hover:\s*hover\)", p) for p in pila[:-1]):
                malos.append(pila[-1])
    return malos


def test_hover_solo_con_raton():
    assert _fuera_de_hover(CSS) == []
    # Autocomprobación de la revisión
    assert _fuera_de_hover(".a:hover { x: 1 } @media (hover: hover) { .b:hover { y: 2 } }") == [".a:hover"]
    assert _fuera_de_hover("@media (max-width: 9px) { .c:hover { z: 3 } }") == [".c:hover"]


def test_movimiento_reducido_y_capas():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    movimiento = CSS[CSS.index("@media (prefers-reduced-motion: reduce)"):]
    for selector in (".lateral", ".giro", ".esqueleto", ".aviso"):
        assert selector in movimiento.split("\n}\n")[0], selector
    # La barra de acciones de la ficha va debajo del asistente (28), del velo (29) y del menú (30): el menú abierto la
    # tapa y «Cerrar sesión» se alcanza (P1)
    barra = re.search(r"\.barra-acciones \{ position: fixed; z-index: (\d+)", CSS)
    assert barra and int(barra.group(1)) < 28


def test_index_declara_el_color_de_la_barra_del_navegador():
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<meta name="theme-color" content="#[0-9a-fA-F]{6}"', index)
    assert "viewport-fit=cover" in index


GUION = r"""
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const [base, usuario, clave, rutaDatos, capturas] = process.argv.slice(2);
const D = JSON.parse(fs.readFileSync(rutaDatos, 'utf8'));
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 20000 };
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const json = (d, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(d) });
// El asistente está, como en producción (su botón flotante es lo que más tapa), pero sin modelo: solo su estado
const ESTADO = { disponible: true, motivo: null, configurado: true, es_admin: true, escritura: true, limite: { usados: 3, maximo: 300 },
  mnemo: { activo: false, origen: null }, sugerencias: ['¿Cómo va la base?'] };
const FICHA = `/personas/${D.persona}`;
// Los mapas base son externos y aquí no hay internet: estilo mínimo, TileJSON, teselas y fuentes vacías y un PNG plano
// (el minimapa de la ficha en escritorio)
const PNG = Buffer.from(D.png, 'base64');
const ESTILO = JSON.stringify({ version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf', sources: {},
  layers: [{ id: 'fondo', type: 'background', paint: { 'background-color': '#d9d9d4' } }] });
const TILEJSON = JSON.stringify({ tilejson: '2.2.0', tiles: ['https://tiles.openfreemap.org/planet/x/{z}/{x}/{y}.pbf'], minzoom: 0, maxzoom: 14 });
const RUTAS = [['panel', '/'], ['personas', '/personas'], ['ficha', FICHA], ['calidad', '/calidad'], ['reuniones', '/reuniones']];
const MOVIL = { isMobile: true, hasTouch: true, deviceScaleFactor: 2 };
const TAMANOS = {
  w320: { viewport: { width: 320, height: 568 }, ...MOVIL },
  w390: { viewport: { width: 390, height: 844 }, ...MOVIL },
  w820: { viewport: { width: 820, height: 1180 }, ...MOVIL },
  w1024: { viewport: { width: 1024, height: 768 } },
  w1280: { viewport: { width: 1280, height: 800 } },
  w1400: { viewport: { width: 1400, height: 900 } },
  w390_oscuro: { viewport: { width: 390, height: 844 }, ...MOVIL, colorScheme: 'dark', reducedMotion: 'reduce' },
  w1400_oscuro: { viewport: { width: 1400, height: 900 }, colorScheme: 'dark' },
};

// ── Contexto y ayudas ──
async function abrir(nav, caso, op) {
  const ctx = await nav.newContext(op);
  // Sin internet: los mapas base se contestan aquí y las letras de Google no se piden
  const cors = { 'Access-Control-Allow-Origin': '*' };
  await ctx.route((u) => u.origin !== origen, (r) => {
    const u = r.request().url();
    if (/^https:\/\/tiles\.openfreemap\.org\/styles\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: ESTILO });
    if (/^https:\/\/tiles\.openfreemap\.org\/planet$/.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: TILEJSON });
    if (/^https:\/\/tiles\.openfreemap\.org\/(planet|fonts)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/x-protobuf', body: Buffer.alloc(0) });
    if (/^https:\/\/(s3\.amazonaws\.com\/elevation-tiles-prod|server\.arcgisonline\.com)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'image/png', body: PNG });
    return r.abort();
  });
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), (r) => {
    const ruta = new URL(r.request().url()).pathname.slice(pref.length);
    if (r.request().method() === 'GET' && ruta === '/api/agente/estado') return r.fulfill(json(ESTADO));
    return r.fulfill(json({ detail: { codigo: 'no_existe', mensaje: 'No existe.' } }, 404));
  });
  await ctx.exposeBinding('__csp', (_, v) => caso.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
    window.__vistas = [];
    addEventListener('vista', (e) => window.__vistas.push(e.detail.ruta));
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => caso.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text().slice(0, 300)); });
  return { ctx, page };
}

async function ingresar(page) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
}

// Abre una vista con el enrutador del panel y espera a que termine de pintarse y de cargar sus datos
async function ir(page, ruta) {
  const n = await page.evaluate(() => window.__vistas.length);
  await page.evaluate(async (r) => (await import(new URL('app.js', document.querySelector('script[type=module]').src).href)).ir(r), ruta);
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  await page.waitForFunction(() => !document.querySelector('#vista .cargando, #vista .esqueleto-fila, #vista .giro'), null, espera);
  await dormir(350);
}

const tocar = (page, sel, tactil) => (tactil ? page.tap(sel) : page.click(sel));
const caja = (r) => r && { x: Math.round(r.left), y: Math.round(r.top), d: Math.round(r.right), a: Math.round(r.bottom) };
const cruzan = (a, b) => !!a && !!b && a.x < b.d && b.x < a.d && a.y < b.a && b.y < a.a;
// Sin relojes: lo que dispara un gesto (una tecla, un toque) ya está hecho cuando pasan dos cuadros de la página
const quieto = (page) => page.evaluate(() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok))));
// El menú del celular, abierto o cerrado del todo: la clase puesta, sin transición en curso y en su sitio
const menuQuieto = (page, abierto) => page.waitForFunction((abierto) => {
  const m = document.querySelector('#menu-lateral'), r = m.getBoundingClientRect();
  return document.querySelector('#app').classList.contains('menu-abierto') === abierto && !m.getAnimations().length
    && (abierto ? Math.abs(r.left) < 0.5 : r.right <= 0.5);
}, abierto, espera);
// Los botones y enlaces vivos del árbol de accesibilidad de Chromium (lo que recorre un lector de pantalla con el dedo)
async function arbolAccesible(cdp) {
  const { nodes } = await cdp.send('Accessibility.getFullAXTree');
  return nodes.filter((n) => !n.ignored && ['button', 'link'].includes(n.role?.value)).map((n) => `${n.role.value}:${(n.name?.value || '').trim()}`);
}

// ¿Algo de la página es más ancho que la pantalla? En el celular un contenido más ancho no da barra: el navegador
// agranda la ventana de diseño (innerWidth), así que también se compara con el ancho pedido
async function desborde(page) {
  const g = await page.evaluate(() => ({
    ancho: document.documentElement.scrollWidth, ventana: innerWidth,
    culpables: [...document.querySelectorAll('#raiz *')].filter((e) => {
      const r = e.getBoundingClientRect();
      if (!r.width || r.right <= innerWidth + 0.5 || getComputedStyle(e).position === 'fixed' || e.closest('[inert], .lateral')) return false;
      // Lo que queda dentro de una caja que se desplaza o recorta no ensancha la página
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (s.overflowX !== 'visible' || s.position === 'fixed') return false;
      }
      return true;
    }).slice(0, 6).map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join('.')} ${Math.round(e.getBoundingClientRect().right)}`),
  }));
  g.malo = g.ancho > g.ventana + 0.5 || g.ventana !== page.viewportSize().width;
  return g;
}

// Lo que se toca y mide menos de 44 × 44 (visible, fuera del asistente, que tiene sus propias pruebas). Un enlace en
// medio de un texto no cuenta (el estándar lo exceptúa), salvo la miga de pan; una casilla dentro de su etiqueta
// tampoco: el blanco es la etiqueta entera
const OBJETIVOS = () => {
  const SEL = 'a[href], button, select, input:not([type=hidden]), textarea, summary, label.casilla, label.chip.opcion, .interruptor';
  const malos = [];
  for (const e of document.querySelectorAll(SEL)) {
    if (e.closest('[hidden], [inert], #agente, #agente-boton, #agente-panel, .sr, .esqueleto-fila')) continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || r.right <= 0 || r.left >= innerWidth) continue;
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.display === 'none') continue;
    if (e.matches('input[type=checkbox], input[type=radio]') && e.closest('label')) continue;
    if (e.matches('a') && s.display === 'inline' && !e.closest('.miga')) continue;
    if (r.height < 43.5 || r.width < 43.5) {
      malos.push(`${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${[...e.classList].join('.')} «${(e.textContent || e.getAttribute('aria-label') || e.name || '').trim().replace(/\s+/g, ' ').slice(0, 28)}» ${Math.round(r.width)}×${Math.round(r.height)}`);
    }
  }
  return malos;
};

// Campos de escribir o elegir con letra de menos de 16 px (también los que están plegados o en otra pestaña)
const CAMPOS = () => [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=range]):not([type=color]):not([type=file]), select, textarea')]
  .map((e) => [e, parseFloat(getComputedStyle(e).fontSize)]).filter(([, f]) => f < 15.95)
  .map(([e, f]) => `${e.tagName.toLowerCase()}[${e.name || e.id || e.className}] ${f}px`);

async function salirAlcanzable(page, tactil) {
  await tocar(page, '#abrir-menu', tactil);
  await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
  await dormir(400); // la transición del menú (.25 s)
  const res = {};
  for (const sel of ['#salir', '#cambiar-tema [data-tema="dark"]']) {
    await page.locator(sel).scrollIntoViewIfNeeded(); // en una pantalla baja el menú se desplaza solo él
    res[sel] = await page.evaluate((sel) => {
      const s = document.querySelector(sel);
      const r = s.getBoundingClientRect();
      const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return r.top >= 0 && r.bottom <= innerHeight && r.right <= innerWidth && !!e && s.contains(e) ? true : `tapado por ${e?.tagName}.${e?.className}`;
    }, sel);
  }
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#app').classList.contains('menu-abierto'));
  return res;
}

// ── Cada tamaño: las cinco vistas ──
async function tamano(nav, caso, op) {
  const v = caso.revisiones, d = caso.datos;
  const tactil = !!op.hasTouch;
  const ancho = op.viewport.width;
  const { ctx, page } = await abrir(nav, caso, op);
  await ingresar(page);
  for (const [nombre, ruta] of RUTAS) {
    await ir(page, ruta);
    // Primero las medidas (antes de cualquier captura de página completa)
    const g = await desborde(page);
    d[`sin_desborde_${nombre}`] = g;
    v[`sin_desborde_${nombre}`] = !g.malo;
    if (tactil) {
      v[`tactil_vigente_${nombre}`] = await page.evaluate(() => matchMedia('(pointer: coarse)').matches);
      const malos = await page.evaluate(OBJETIVOS);
      d[`tactil_${nombre}`] = malos;
      v[`tactil_${nombre}`] = malos.length === 0;
    }
    if (ancho <= 900) {
      const malos = await page.evaluate(CAMPOS);
      d[`campos_16_${nombre}`] = malos;
      v[`campos_16_${nombre}`] = malos.length === 0;
    }
    if (nombre === 'personas') {
      // La tabla cabe en su caja: nada de columnas escondidas tras un desplazamiento sin aviso
      const t = await page.evaluate(() => {
        const e = document.querySelector('#vista .envoltura-tabla');
        const nombre = document.querySelector('#filas tr[data-id] td:first-child');
        return { scroll: e.scrollWidth, caja: e.clientWidth, nombre: nombre && Math.round(nombre.getBoundingClientRect().width),
          tarjetas: getComputedStyle(document.querySelector('.tabla-personas thead')).display === 'none' };
      });
      d.tabla_cabe = t;
      v.tabla_cabe = t.scroll <= t.caja + 1 && (t.tarjetas || t.nombre >= 200);
    }
    if (!tactil && (nombre === 'calidad' || nombre === 'ficha')) {
      // Con ratón las pestañas se envuelven: ninguna queda cortada ni escondida
      const p = await page.evaluate(() => {
        const e = document.querySelector('#vista .pestanas');
        return e && { scroll: e.scrollWidth, caja: e.clientWidth, mascara: getComputedStyle(e).maskImage || getComputedStyle(e).webkitMaskImage };
      });
      d[`pestanas_enteras_${nombre}`] = p;
      v[`pestanas_enteras_${nombre}`] = !!p && p.scroll <= p.caja + 1 && (!p.mascara || p.mascara === 'none');
    }
    if (nombre === 'panel' && op.colorScheme === 'dark') {
      // La tarjeta destacada se distingue del fondo y de las otras tarjetas en oscuro
      const k = await page.evaluate(() => {
        const lum = (c) => { const [r, g, b] = c.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
        const contraste = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
        const fondo = getComputedStyle(document.body).backgroundColor;
        const acento = getComputedStyle(document.querySelector('.kpi.acento')).backgroundColor;
        const otra = getComputedStyle(document.querySelector('.kpi:not(.acento)')).backgroundColor;
        return { fondo, acento, otra, contra_fondo: contraste(acento, fondo), contra_otra: contraste(acento, otra), otra_fondo: contraste(otra, fondo) };
      });
      d.kpi_acento = k;
      v.sin_desborde_kpi_acento_visible = k.contra_fondo >= 1.3 && k.contra_otra >= 1.2;
    }
    if (op.reducedMotion === 'reduce' && nombre === 'panel') {
      v.sin_desborde_movimiento_reducido = await page.evaluate(() => {
        const s = getComputedStyle(document.querySelector('.lateral'));
        return parseFloat(s.transitionDuration) === 0;
      });
    }
    await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-${nombre}.png` });
  }
  // Las capturas de página completa al final: después de una, la emulación táctil deja de medir bien
  for (const [nombre, ruta] of RUTAS) {
    await ir(page, ruta);
    await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-${nombre}-entera.png`, fullPage: true });
  }
  await ctx.close();
}

// ── La ficha en el celular y la tableta ──
async function ficha(nav, caso, op) {
  const v = caso.revisiones, d = caso.datos;
  const ancho = op.viewport.width;
  const { ctx, page } = await abrir(nav, caso, op);
  await ingresar(page);
  await ir(page, FICHA);
  const f = await page.evaluate(() => {
    const nav = document.querySelector('#vista .barra-acciones');
    const hijos = [...nav.children];
    const visibles = hijos.filter((x) => !x.hidden && x.getClientRects().length);
    return {
      titulo: parseFloat(getComputedStyle(document.querySelector('.nombre-ficha')).fontSize),
      scroll: nav.scrollWidth, caja: nav.clientWidth,
      fuera: visibles.filter((x) => { const r = x.getBoundingClientRect(); return r.left < -0.5 || r.right > innerWidth + 0.5; }).map((x) => x.textContent.trim()),
      visibles: visibles.map((x) => x.textContent.trim()),
      ocultas: hijos.filter((x) => x.hidden && !x.matches('.mas-acciones')).map((x) => x.textContent.trim()),
      mas: !!document.querySelector('.barra-acciones .mas-acciones:not([hidden])'),
      cabecera: [...document.querySelectorAll('.cabecera .acciones .btn')].filter((x) => x.getClientRects().length && getComputedStyle(x).display !== 'none').map((x) => x.id),
    };
  });
  d.barra = f;
  v.titulo_a_su_tamano = ancho <= 640 ? f.titulo <= 24 : f.titulo <= 28;
  v.barra_sin_botones_fuera = f.fuera.length === 0 && f.scroll <= f.caja + 1;
  if (ancho > 640) {
    v.barra_todas_a_la_vista = f.ocultas.length === 0 && !f.mas && f.visibles.length === 6;
    v.cabecera_con_sus_botones = f.cabecera.includes('unir') && f.cabecera.includes('suprimir') && !f.cabecera.includes('mas-ficha');
    await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}.png` });
    await ctx.close();
    return;
  }
  v.barra_con_mas = f.mas && f.ocultas.length > 0 && f.visibles.length + f.ocultas.length === 7;
  // «Más» ofrece exactamente las que no cupieron y cada una hace lo mismo que en la barra
  await page.tap('.barra-acciones .mas-acciones');
  await page.waitForSelector('dialog[open] [data-otra-accion]', espera);
  const ofrecidas = await page.evaluate(() => [...document.querySelectorAll('dialog[open] [data-otra-accion]')].map((b) => b.textContent.trim()));
  d.ofrecidas = ofrecidas;
  v.mas_ofrece_las_ocultas = JSON.stringify(ofrecidas) === JSON.stringify(f.ocultas);
  await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-mas.png` });
  const hogar = await page.$('dialog[open] [data-otra-accion]:has-text("Nueva en este hogar")');
  if (hogar) {
    await hogar.tap();
    await page.waitForSelector('dialog[open] #f-nueva', espera);
    v.mas_ejecuta_la_accion = await page.evaluate(() => document.querySelectorAll('dialog[open]').length === 1);
    await page.tap('dialog[open] .pie [data-cerrar]');
    await page.waitForFunction(() => !document.querySelector('dialog[open]'));
  } else v.mas_ejecuta_la_accion = `«Nueva en este hogar» no está entre las ofrecidas: ${ofrecidas}`;
  // Cabecera: «Unir» y «Suprimir» en el menú ⋯
  v.cabecera_en_menu = JSON.stringify(f.cabecera) === '["mas-ficha"]';
  await page.tap('#mas-ficha');
  await page.waitForSelector('dialog[open] [data-ficha="unir"]', espera);
  await page.tap('dialog[open] [data-ficha="unir"]');
  await page.waitForSelector('dialog[open] #buscar-unir', espera);
  v.menu_ficha_abre_unir = true;
  await page.tap('dialog[open] [data-cerrar]');
  await page.waitForFunction(() => !document.querySelector('dialog[open]'));
  // Un aviso no tapa la barra de acciones
  await page.evaluate(async () => (await import(new URL('ui.js', document.querySelector('script[type=module]').src).href)).aviso('Aviso de prueba inventado', 'ok', 8000));
  await dormir(300);
  const av = await page.evaluate(() => ({ aviso: document.querySelector('#avisos .aviso').getBoundingClientRect().toJSON(),
    barra: document.querySelector('#vista .barra-acciones').getBoundingClientRect().toJSON() }));
  d.aviso = { aviso: caja(av.aviso), barra: caja(av.barra) };
  v.aviso_encima_de_la_barra = av.aviso.bottom <= av.barra.top + 0.5;
  await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-aviso.png` });
  // «Cerrar sesión» y el tema se alcanzan con el menú abierto sobre la ficha (la barra no los tapa)
  const s = await salirAlcanzable(page, true);
  d.salir = s;
  v.salir_alcanzable_en_la_ficha = s['#salir'];
  v.tema_alcanzable_en_la_ficha = s['#cambiar-tema [data-tema="dark"]'];
  await ctx.close();
}

// ── Diálogo con algo escrito ──
async function dialogo(nav, caso, op) {
  const v = caso.revisiones, d = caso.datos;
  const tactil = !!op.hasTouch;
  const { ctx, page } = await abrir(nav, caso, op);
  await ingresar(page);
  await ir(page, FICHA);
  const abrirCompletar = async () => {
    // En el celular «Completar» puede estar en «Más»: se toca la acción de la barra (la misma que ofrece «Más»)
    if (await page.isVisible('.barra-acciones [data-completar]')) await tocar(page, '.barra-acciones [data-completar]', tactil);
    else await page.evaluate(() => document.querySelector('.barra-acciones [data-completar]').click());
    await page.waitForSelector('dialog[open] #f-completar', espera);
    await dormir(200);
  };
  // Un punto del fondo, fuera de la hoja o del diálogo
  const fondo = async () => {
    const r = await page.evaluate(() => [...document.querySelectorAll('dialog[open]')].pop().getBoundingClientRect().toJSON());
    const [x, y] = r.top >= 6 ? [op.viewport.width / 2, r.top / 2] : [r.left / 2, r.top + r.height / 2];
    if (tactil) await page.touchscreen.tap(x, y); else await page.mouse.click(x, y);
    await dormir(250);
  };
  const abiertos = () => page.evaluate(() => [...document.querySelectorAll('dialog[open]')].map((x) => x.querySelector('h2').textContent));
  await abrirCompletar();
  const cerrar = await page.evaluate(() => { const b = document.querySelector('dialog[open] .cab [data-cerrar]').getBoundingClientRect(); return [b.width, b.height]; });
  d.boton_cerrar = cerrar;
  v.boton_cerrar_de_44 = cerrar[0] >= 44 && cerrar[1] >= 44;
  await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-completar.png` });
  // Sin nada escrito, el fondo cierra sin preguntar
  await fondo();
  d.sin_escribir = await abiertos();
  v.sin_escribir_cierra = d.sin_escribir.length === 0;
  // Con una cédula escrita, el fondo pregunta y «Seguir escribiendo» la conserva
  await abrirCompletar();
  await page.fill('dialog[open] [name=cedula]', '12345');
  await fondo();
  d.con_escrito = await abiertos();
  v.fondo_pregunta = d.con_escrito.length === 2 && d.con_escrito[1] === 'Confirmar'
    && (await page.textContent('dialog[open]:last-of-type')).includes('¿Descartar lo escrito?');
  await page.screenshot({ path: `${capturas}/responsivo-${caso.nombre}-descartar.png` });
  await tocar(page, 'dialog[open]:last-of-type [data-cerrar]:not(.cerrar-dialogo)', tactil);
  await dormir(200);
  v.seguir_conserva = JSON.stringify(await abiertos()) === JSON.stringify([d.con_escrito[0]])
    && await page.inputValue('dialog[open] [name=cedula]') === '12345';
  // Escape también pregunta; «Descartar» cierra los dos
  await page.focus('dialog[open] [name=cedula]');
  await page.keyboard.press('Escape');
  await dormir(250);
  d.escape = await abiertos();
  v.escape_pregunta = d.escape.length === 2 && d.escape[1] === 'Confirmar';
  await tocar(page, 'dialog[open]:last-of-type [data-si]', tactil);
  await dormir(250);
  v.descartar_cierra = (await abiertos()).length === 0;
  // La ficha no cambió (nada se guardó)
  v.nada_guardado = await page.evaluate(() => !document.querySelector('#avisos .aviso'));
  await ctx.close();
}

// ── Guardar con la red lenta: Escape y el fondo no preguntan ni cierran ──
async function guardando(nav, caso, op, id) {
  const v = caso.revisiones, d = caso.datos;
  const tactil = !!op.hasTouch;
  const { ctx, page } = await abrir(nav, caso, op);
  await ingresar(page);
  await ir(page, `/personas/${id}`);
  // El PATCH de «Completar» queda retenido hasta que la prueba lo suelta: «guardando» dura lo que haga falta
  let soltar, llego;
  const retenido = new Promise((ok) => { soltar = ok; });
  const enCamino = new Promise((ok) => { llego = ok; });
  await page.route((u) => u.pathname === `${pref}/api/personas/${id}` && u.searchParams.get('modo') === 'completar',
    async (r) => { llego(); await retenido; await r.continue(); });
  await page.evaluate(() => { window.__cierres = 0; document.addEventListener('close', () => { window.__cierres++; }, true); });
  if (await page.isVisible('.barra-acciones [data-completar]')) await tocar(page, '.barra-acciones [data-completar]', tactil);
  else await page.evaluate(() => document.querySelector('.barra-acciones [data-completar]').click());
  await page.waitForSelector('dialog[open] #f-completar', espera);
  const cedula = String(1098765400 + id);
  await page.fill('dialog[open] [name=cedula]', cedula);
  await page.fill('dialog[open] [name=cedula_confirmacion]', cedula);
  await tocar(page, 'dialog[open] [data-guardar="uno"]', tactil);
  await enCamino;
  const abiertos = () => page.evaluate(() => [...document.querySelectorAll('dialog[open]')].map((x) => x.querySelector('h2').textContent));
  const solo = (l) => l.length === 1 && l[0].startsWith('Completar');
  const fondo = async () => {
    const r = await page.evaluate(() => [...document.querySelectorAll('dialog[open]')].pop().getBoundingClientRect().toJSON());
    const [x, y] = r.top >= 6 ? [op.viewport.width / 2, r.top / 2] : [r.left / 2, r.top + r.height / 2];
    if (tactil) await page.touchscreen.tap(x, y); else await page.mouse.click(x, y);
    await dormir(250);
  };
  await page.keyboard.press('Escape');
  await dormir(250);
  d.escape = await abiertos();
  v.guardando_escape_no_pregunta = solo(d.escape);
  await fondo();
  d.fondo = await abiertos();
  v.guardando_fondo_no_pregunta = solo(d.fondo);
  // Dos Escape seguidos: Chromium ya no deja cancelar el segundo y cierra el diálogo, que `dialogo` vuelve a abrir
  for (let i = 0; i < 2; i++) { await page.keyboard.press('Escape'); await dormir(250); }
  d.escapes = await abiertos();
  d.cierres_del_navegador = await page.evaluate(() => window.__cierres);
  v.guardando_escapes_seguidos_no_cierran = solo(d.escapes);
  // El fondo otra vez, lo último antes de terminar: si preguntara, la pregunta quedaría suelta al cerrarse el formulario
  await fondo();
  d.fondo_al_final = await abiertos();
  v.guardando_fondo_al_final_no_pregunta = solo(d.fondo_al_final);
  // Al terminar de guardar se cierra sin preguntar: el aviso queda en la página (no en una pregunta que sobró) y la
  // ficha muestra lo guardado
  soltar();
  await page.waitForFunction(() => [...document.querySelectorAll('.aviso')].some((a) => a.textContent.includes('datos guardados')), null, espera);
  d.tras_guardar = await abiertos();
  v.al_guardar_cierra_sin_preguntar = d.tras_guardar.length === 0;
  d.cedula_en_la_ficha = await page.inputValue('#f-datos [name=cedula]');
  v.ficha_con_lo_guardado = d.cedula_en_la_ficha === cedula;
  await ctx.close();
}

// ── «Nueva persona» que guarda en una ficha que ya está («Es esta» o «Completar esa ficha con lo que escribí»), con
// la red lenta: Escape y el fondo no preguntan, y al terminar se abre esa ficha sin diálogos y con lo escrito ──
async function esEsta(nav, caso, op, { id, nombre, cedula, telefono2 }) {
  const v = caso.revisiones, d = caso.datos;
  const tactil = !!op.hasTouch;
  const { ctx, page } = await abrir(nav, caso, op);
  await ingresar(page);
  await ir(page, '/personas');
  // El PATCH ?modo=completar de esa ficha queda retenido hasta que la prueba lo suelta: «guardando» dura lo que haga falta
  let soltar, llego;
  const retenido = new Promise((ok) => { soltar = ok; });
  const enCamino = new Promise((ok) => { llego = ok; });
  await page.route((u) => u.pathname === `${pref}/api/personas/${id}` && u.searchParams.get('modo') === 'completar',
    async (r) => { if (r.request().method() !== 'PATCH') return r.continue(); llego(); await retenido; await r.continue(); });
  await page.evaluate(() => { window.__cierres = 0; document.addEventListener('close', () => { window.__cierres++; }, true); });
  await tocar(page, '#nueva', tactil);
  await page.waitForSelector('dialog[open] #f-nueva', espera);
  const abiertos = () => page.evaluate(() => [...document.querySelectorAll('dialog[open]')].map((x) => x.querySelector('h2').textContent));
  const solo = (l) => l.length === 1 && l[0] === 'Nueva persona';
  // Si apareció la pregunta, «Seguir escribiendo» la quita: cada gesto se prueba solo, con el formulario como estaba
  const quitarPregunta = async () => {
    if ((await abiertos()).length < 2) return;
    await tocar(page, 'dialog[open]:last-of-type [data-cerrar]:not(.cerrar-dialogo)', tactil);
    await page.waitForFunction(() => document.querySelectorAll('dialog[open]').length === 1, null, espera);
  };
  if (cedula) {
    // La cédula de esa ficha: «Guardar» responde 409 cedula_ocupada y ofrece «Completar esa ficha con lo que escribí»
    await page.fill('#f-nueva [name=nombre]', 'PERSONA INVENTADA CON CEDULA AJENA');
    await page.fill('#f-nueva [name=cedula]', cedula);
    await page.fill('#f-nueva [name=cedula_confirmacion]', cedula);
    await page.fill('#f-nueva [name=telefono2]', telefono2);
    await tocar(page, '#f-nueva label.chip.opcion:has(input[name=aut_estado][value=pendiente])', tactil);
    await tocar(page, 'dialog[open] #guardar', tactil);
    await page.waitForSelector(`dialog[open] [data-completar-otra="${id}"]`, espera);
    d.camino = 'Completar esa ficha con lo que escribí';
    await tocar(page, `dialog[open] [data-completar-otra="${id}"]`, tactil);
  } else {
    // Como lo reprodujo la revisión: el nombre de una que ya está y otro teléfono; «¿Es alguna de estas?» → «Es esta»
    await page.fill('#f-nueva [name=nombre]', nombre);
    await page.fill('#f-nueva [name=telefono2]', telefono2);
    await page.waitForSelector(`dialog[open] [data-elegir="${id}"]`, espera);
    d.camino = 'Es esta';
    await tocar(page, `dialog[open] [data-elegir="${id}"]`, tactil);
  }
  await enCamino;
  // Escape (en Android, también el gesto de volver): no pregunta
  await page.keyboard.press('Escape');
  await quieto(page);
  d.escape = await abiertos();
  v.es_esta_escape_no_pregunta = solo(d.escape);
  await quitarPregunta();
  // El fondo, en un punto fuera de la hoja o del diálogo cuando su caja ya no se mueve (dos cuadros iguales)
  const p = await page.evaluate(() => new Promise((ok) => {
    let antes = '';
    const mirar = () => {
      const dl = [...document.querySelectorAll('dialog[open]')].pop(), r = dl.getBoundingClientRect(), ahora = JSON.stringify(r);
      if (ahora !== antes) { antes = ahora; requestAnimationFrame(mirar); return; }
      const [x, y] = r.top >= 6 ? [innerWidth / 2, r.top / 2] : [r.left / 2, r.top + r.height / 2];
      ok({ x, y, fondo: document.elementFromPoint(x, y) === dl && (x < r.left || x > r.right || y < r.top || y > r.bottom) });
    };
    requestAnimationFrame(mirar);
  }));
  d.punto_del_fondo = p;
  v.es_esta_el_toque_cae_en_el_fondo = p.fondo;
  if (tactil) await page.touchscreen.tap(p.x, p.y); else await page.mouse.click(p.x, p.y);
  await quieto(page);
  d.fondo = await abiertos();
  v.es_esta_fondo_no_pregunta = solo(d.fondo);
  await quitarPregunta();
  // Dos Escape seguidos: Chromium ya no deja cancelar el segundo y cierra el diálogo, que `dialogo` vuelve a abrir al
  // atender su 'close' (sin preguntar, guardando). Se espera a que esté abierto otra vez, no a un reloj
  for (let i = 0; i < 2; i++) await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelector('#f-nueva')?.closest('dialog')?.open, null, espera);
  await quieto(page);
  d.escapes = await abiertos();
  d.cierres_del_navegador = await page.evaluate(() => window.__cierres);
  v.es_esta_escapes_seguidos_no_preguntan = solo(d.escapes);
  await quitarPregunta();
  // Al terminar se cierra sin preguntar y se abre esa ficha, con el teléfono escrito guardado
  soltar();
  await page.waitForFunction((id) => window.__vistas.includes(`/personas/${id}`), id, espera);
  await page.waitForFunction(() => !document.querySelector('#vista .cargando, #vista .esqueleto-fila, #vista .giro'), null, espera);
  await quieto(page);
  d.tras_guardar = await abiertos();
  v.es_esta_al_guardar_cierra_sin_preguntar = d.tras_guardar.length === 0;
  d.guardado = await page.evaluate(async (id) => {
    const p = await (await import(new URL('api.js', document.querySelector('script[type=module]').src).href)).api.get(`/api/personas/${id}`);
    return [p.telefono, p.telefono2, ...(p.telefonos || []).map((t) => t.numero)].filter(Boolean);
  }, id);
  v.es_esta_ficha_con_lo_escrito = d.guardado.includes(telefono2);
  await ctx.close();
}

// ── «Nueva persona» cerrada por el navegador y vuelta a abrir: sigue pendiente y un 401 no recarga ──
async function pendiente(nav, caso) {
  const v = caso.revisiones, d = caso.datos;
  const { ctx, page } = await abrir(nav, caso, TAMANOS.w1400);
  await ingresar(page);
  await ir(page, '/personas');
  const abiertos = () => page.evaluate(() => [...document.querySelectorAll('dialog[open]')].map((x) => x.querySelector('h2').textContent));
  await page.evaluate(() => { window.__cierres = 0; document.addEventListener('close', () => { window.__cierres++; }, true); });
  await page.click('#nueva');
  await page.waitForSelector('dialog[open] #f-nueva', espera);
  const nombre = 'PERSONA INVENTADA DE PRUEBA';
  await page.fill('#f-nueva [name=nombre]', nombre);
  // Tres Escape seguidos: el primero pregunta, el segundo cierra la pregunta y el tercero ya no se puede cancelar
  // (Chromium cierra el diálogo y `dialogo` lo vuelve a abrir preguntando); «Seguir escribiendo» lo conserva
  for (let i = 0; i < 3; i++) { await page.keyboard.press('Escape'); await dormir(300); }
  d.cierres_del_navegador = await page.evaluate(() => window.__cierres);
  if ((await abiertos()).length > 1) await page.click('dialog[open]:last-of-type [data-cerrar]:not(.cerrar-dialogo)');
  await dormir(200);
  d.abiertos = await abiertos();
  v.sigue_abierta_con_lo_escrito = JSON.stringify(d.abiertos) === '["Nueva persona"]' && await page.inputValue('#f-nueva [name=nombre]') === nombre;
  v.sigue_pendiente = await page.evaluate(async () => (await import(new URL('api.js', document.querySelector('script[type=module]').src).href)).hayCambiosSinGuardar());
  if (!v.sigue_pendiente) d.dialogos = await page.evaluate(() => [...document.querySelectorAll('dialog')].map((x) => ({ abierto: x.open, titulo: x.querySelector('h2')?.textContent, valor: x.querySelector('[name=nombre]')?.value })));
  // La sesión vence: la búsqueda en vivo de parecidas (un GET) recibe un 401 y se ingresa en un diálogo, sin recargar
  let recargo = false;
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) recargo = true; });
  await ctx.clearCookies();
  await page.fill('#f-nueva [name=nombre]', nombre + ' X');
  d.reingreso = await page.waitForSelector('dialog[open] #f-reingreso', { timeout: 8000 }).then(() => true, () => false);
  d.recargo = recargo;
  v.un_401_abre_el_ingreso = d.reingreso && !recargo;
  if (d.reingreso) {
    await page.fill('dialog[open] #f-reingreso [name=clave]', clave);
    await page.click('dialog[open] button[type=submit][form=f-reingreso]');
    await page.waitForSelector('#f-reingreso', { state: 'detached', ...espera });
    d.tras_ingresar = { valor: await page.inputValue('#f-nueva [name=nombre]'), abiertos: await abiertos() };
    v.conserva_lo_escrito = !recargo && d.tras_ingresar.valor === nombre + ' X';
  }
  await ctx.close();
}

// ── Menú lateral ──
async function menu(nav, caso) {
  const v = caso.revisiones, d = caso.datos;
  const { ctx, page } = await abrir(nav, caso, TAMANOS.w390);
  await ingresar(page);
  await ir(page, '/personas');
  // El botón del asistente, a la vista: es lo que el tabulador alcanzaba debajo del velo
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  const tapado = () => page.evaluate(() => ['#vista', '.barra-movil', '#agente'].map((s) => document.querySelector(s)?.inert ?? 'falta'));
  const estado = () => page.evaluate(() => ({ menu: document.querySelector('#menu-lateral').inert, vista: document.querySelector('#vista').inert,
    abierto: document.querySelector('#app').classList.contains('menu-abierto'), foco: document.activeElement?.closest('#menu-lateral') ? 'menu' : document.activeElement?.id || document.activeElement?.tagName }));
  d.cerrado = await estado();
  v.cerrado_inerte = d.cerrado.menu === true && d.cerrado.vista === false;
  // Con el tabulador, desde el botón del menú no se entra al menú cerrado
  await page.focus('#abrir-menu');
  const pasos = [];
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press('Tab');
    pasos.push(await page.evaluate(() => !!document.activeElement?.closest('#menu-lateral')));
  }
  d.tabulador = pasos;
  v.tabulador_no_entra = pasos.every((x) => !x);
  await page.tap('#abrir-menu');
  await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
  d.abierto = await estado();
  v.abierto_foco_y_vista_inerte = d.abierto.menu === false && d.abierto.vista === true && d.abierto.foco === 'menu'
    && await page.evaluate(() => document.activeElement?.getAttribute('aria-current') === 'page');
  await dormir(400);
  await page.screenshot({ path: `${capturas}/responsivo-menu-abierto.png` });
  // Abierto, el foco queda atrapado en el menú: lo que tapa el velo es inerte (también el asistente, que vive en
  // document.body), así que desde «Cerrar sesión» el tabulador solo recorre el menú (o sale de la página y vuelve)
  d.tapado_abierto = await tapado();
  v.lo_tapado_es_inerte = d.tapado_abierto.every((x) => x === true);
  await page.focus('#salir');
  const fuera = [];
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => { const a = document.activeElement; return !a || a === document.body || a.closest('#menu-lateral') ? null : a.id || a.tagName; });
    if (f) fuera.push(f);
  }
  d.tabulador_abierto = fuera;
  v.tabulador_atrapado_en_el_menu = fuera.length === 0;
  await page.keyboard.press('Escape');
  await dormir(100);
  d.escape = await estado();
  v.escape_cierra_y_devuelve_el_foco = d.escape.abierto === false && d.escape.menu === true && d.escape.foco === 'abrir-menu';
  d.tapado_cerrado = await tapado();
  v.cerrado_nada_tapado = d.tapado_cerrado.every((x) => x === false);
  // El velo también lo cierra
  await page.tap('#abrir-menu');
  await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
  await dormir(400);
  await page.touchscreen.tap(380, 400);
  await dormir(200);
  v.velo_cierra = (await estado()).menu === true;
  // Al ensanchar la ventana el menú fijo del escritorio no queda inerte (ni la vista)
  await page.setViewportSize({ width: 1280, height: 800 });
  await dormir(300);
  d.ancho = await estado();
  v.escritorio_no_inerte = d.ancho.menu === false && d.ancho.vista === false;
  await ctx.close();
  // En escritorio, de entrada
  const e = await abrir(nav, caso, TAMANOS.w1400);
  await ingresar(e.page);
  v.escritorio_de_entrada = await e.page.evaluate(() => !document.querySelector('#menu-lateral').inert && !document.querySelector('#vista').inert);
  await e.ctx.close();
}

// ── El menú abierto antes de que llegue el asistente (red lenta al cargar en el celular) ──
async function menuTarde(nav, caso) {
  const v = caso.revisiones, d = caso.datos;
  const { ctx, page } = await abrir(nav, caso, TAMANOS.w390);
  // agente.js (se importa después del primer render) queda retenido hasta que la prueba lo suelta
  let soltar, llego;
  const retenido = new Promise((ok) => { soltar = ok; });
  const enCamino = new Promise((ok) => { llego = ok; });
  await ctx.route((u) => u.pathname.endsWith('/js/agente.js'), async (r) => { llego(); await retenido; await r.continue(); });
  await ingresar(page);
  await enCamino;
  d.agente_al_abrir = await page.evaluate(() => !!document.getElementById('agente'));
  v.el_asistente_aun_no_esta = d.agente_al_abrir === false;
  await page.tap('#abrir-menu');
  await menuQuieto(page, true);
  // Llega el asistente con el menú abierto
  soltar();
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  await quieto(page);
  d.con_el_asistente = await page.evaluate(() => ({ abierto: document.querySelector('#app').classList.contains('menu-abierto'),
    tapado: ['#vista', '.barra-movil', '#agente'].map((s) => document.querySelector(s)?.inert ?? 'falta') }));
  v.sigue_abierto = d.con_el_asistente.abierto === true;
  v.el_asistente_tardio_es_inerte = d.con_el_asistente.tapado.every((x) => x === true);
  // Desde «Cerrar sesión» el tabulador solo recorre el menú (o sale de la página y vuelve): nunca el botón del asistente
  await page.focus('#salir');
  const fuera = [];
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => { const a = document.activeElement; return !a || a === document.body || a.closest('#menu-lateral') ? null : a.id || a.tagName; });
    if (f) fuera.push(f);
  }
  d.tabulador = fuera;
  v.tabulador_no_llega_al_asistente = fuera.length === 0;
  // Cerrado, nada queda tapado y el vigía se fue: lo que se agregue después a la página no vuelve inerte la vista
  await page.keyboard.press('Escape');
  await menuQuieto(page, false);
  await page.evaluate(() => document.body.append(Object.assign(document.createElement('div'), { id: 'prueba-agregado' })));
  await quieto(page);
  d.cerrado = await page.evaluate(() => ['#vista', '.barra-movil', '#agente'].map((s) => document.querySelector(s)?.inert ?? 'falta'));
  v.cerrado_nada_tapado = d.cerrado.every((x) => x === false);
  await ctx.close();
}

// ── «Cerrar menú»: el control con nombre que queda en el menú abierto del celular ──
async function cerrarMenu(nav, caso) {
  const v = caso.revisiones, d = caso.datos;
  const { ctx, page } = await abrir(nav, caso, TAMANOS.w390);
  await ingresar(page);
  await ir(page, '/personas');
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  const cdp = await ctx.newCDPSession(page);
  d.arbol_cerrado = await arbolAccesible(cdp);
  v.cerrado_no_esta_en_el_arbol = !d.arbol_cerrado.includes('button:Cerrar menú');
  await page.tap('#abrir-menu');
  await menuQuieto(page, true);
  // Abierto: «Cerrar menú» está en el árbol; la barra de arriba (con «Menú») sigue inerte, el foco no sale del menú
  d.arbol_abierto = await arbolAccesible(cdp);
  v.abierto_esta_en_el_arbol = d.arbol_abierto.includes('button:Cerrar menú');
  v.la_barra_sigue_inerte = !d.arbol_abierto.some((b) => b.startsWith('button:Menú'));
  const g = await page.evaluate(() => {
    const b = document.querySelector('#cerrar-menu'), r = b.getBoundingClientRect();
    const caja = (r) => ({ x: r.left, y: r.top, d: r.right, a: r.bottom });
    const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    // Lo que se lee de la marca (el sello y el texto), no la caja del enlace entero
    const marca = [...document.querySelectorAll('.marca > *')].map((x) => caja(x.getBoundingClientRect()));
    return { ancho: r.width, alto: r.height, caja: caja(r), a_la_vista: !!e && b.contains(e) && r.left >= 0 && r.right <= innerWidth && r.top >= 0,
      marca, menu: caja(document.querySelector('#menu-lateral').getBoundingClientRect()) };
  });
  d.boton = g;
  v.mide_44 = g.ancho >= 44 && g.alto >= 44;
  v.a_la_vista_dentro_del_menu = g.a_la_vista && g.caja.x >= g.menu.x && g.caja.d <= g.menu.d;
  v.no_se_monta_con_la_marca = g.marca.length > 0 && g.marca.every((m) => !cruzan(m, g.caja));
  await page.screenshot({ path: `${capturas}/responsivo-cerrar-menu.png` });
  // Lo cierra y devuelve el foco al botón «Menú»
  await page.tap('#cerrar-menu');
  await menuQuieto(page, false);
  d.tras = await page.evaluate(() => ({ menu: document.querySelector('#menu-lateral').inert, expandido: document.querySelector('#abrir-menu').getAttribute('aria-expanded'),
    foco: document.activeElement?.id || document.activeElement?.tagName, tapado: ['#vista', '.barra-movil', '#agente'].map((s) => document.querySelector(s)?.inert ?? 'falta') }));
  v.cierra_y_devuelve_el_foco = d.tras.menu === true && d.tras.expandido === 'false' && d.tras.foco === 'abrir-menu' && d.tras.tapado.every((x) => x === false);
  await ctx.close();
  // En escritorio el menú está siempre a la vista: no hay botón de cerrarlo
  const e = await abrir(nav, caso, TAMANOS.w1400);
  await ingresar(e.page);
  const cdpe = await e.ctx.newCDPSession(e.page);
  d.escritorio = { display: await e.page.evaluate(() => getComputedStyle(document.querySelector('#cerrar-menu')).display), arbol: (await arbolAccesible(cdpe)).filter((b) => b === 'button:Cerrar menú') };
  v.escritorio_sin_boton = d.escritorio.display === 'none' && d.escritorio.arbol.length === 0;
  await e.ctx.close();
}

// ── Tema ──
async function tema(nav, caso) {
  const v = caso.revisiones, d = caso.datos;
  const { ctx, page } = await abrir(nav, caso, TAMANOS.w1400_oscuro);
  await ingresar(page);
  const leer = () => page.evaluate(() => ({ tema: document.documentElement.dataset.theme || null, guardado: localStorage.getItem('tema'),
    fondo: getComputedStyle(document.body).backgroundColor,
    pulsado: [...document.querySelectorAll('#cambiar-tema [data-tema]')].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent) }));
  d.inicio = await leer();
  v.sigue_al_sistema = d.inicio.tema === null && d.inicio.fondo === 'rgb(13, 13, 13)' && JSON.stringify(d.inicio.pulsado) === '["Sistema"]';
  await page.click('#cambiar-tema [data-tema="light"]');
  d.claro = await leer();
  v.claro = d.claro.tema === 'light' && d.claro.guardado === 'light' && d.claro.fondo === 'rgb(242, 242, 239)' && JSON.stringify(d.claro.pulsado) === '["Claro"]';
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  d.recargado = await leer();
  v.se_recuerda = d.recargado.tema === 'light' && JSON.stringify(d.recargado.pulsado) === '["Claro"]';
  await page.click('#cambiar-tema [data-tema="dark"]');
  d.oscuro = await leer();
  v.oscuro = d.oscuro.tema === 'dark' && d.oscuro.guardado === 'dark' && JSON.stringify(d.oscuro.pulsado) === '["Oscuro"]';
  await page.click('#cambiar-tema [data-tema=""]');
  d.sistema = await leer();
  v.vuelve_al_sistema = d.sistema.tema === null && d.sistema.guardado === null && d.sistema.fondo === 'rgb(13, 13, 13)';
  await page.screenshot({ path: `${capturas}/responsivo-tema.png` });
  await ctx.close();
}

(async () => {
  const nav = await chromium.launch();
  const casos = [];
  const correr = async (nombre, f) => {
    const caso = { nombre, revisiones: {}, datos: {}, errores: [], csp: [] };
    casos.push(caso);
    try { await f(caso); } catch (e) { caso.fallo = String(e && e.stack || e).slice(0, 2000); }
  };
  try {
    for (const [nombre, op] of Object.entries(TAMANOS)) await correr(nombre, (c) => tamano(nav, c, op));
    for (const t of ['w320', 'w390', 'w820']) await correr(`ficha_${t}`, (c) => ficha(nav, c, TAMANOS[t]));
    for (const t of ['w390', 'w1400']) await correr(`dialogo_${t}`, (c) => dialogo(nav, c, TAMANOS[t]));
    for (const t of ['w390', 'w1400']) await correr(`guardando_${t}`, (c) => guardando(nav, c, TAMANOS[t], D.sin_cedula[t]));
    for (const t of ['w1400', 'w390']) await correr(`es_esta_${t}`, (c) => esEsta(nav, c, TAMANOS[t], D.es_esta[t]));
    await correr('pendiente', (c) => pendiente(nav, c));
    await correr('menu', (c) => menu(nav, c));
    await correr('menu_tarde', (c) => menuTarde(nav, c));
    await correr('cerrar_menu', (c) => cerrarMenu(nav, c));
    await correr('tema', (c) => tema(nav, c));
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos }));
})().catch((e) => { console.error(e); process.exit(1); });
"""
