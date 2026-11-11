"""El asistente maneja el Mapa 3D: el puente `web/js/agente-mapa.js` y el control que registra `web/js/vistas/mapa.js`.

* `test_puente_*` (solo Node, sin navegador): la cola con plazo, el orden estricto entre llamadas, la navegación a /mapa
  una sola vez con los filtros sencillos de la primera acción `filtros` en la URL (nunca `area_id` ni `poligono`, que
  en la URL abren una zona), el rechazo en el acto si la persona abre otra vista mientras el mapa carga y que
  `estadoMapa()` nunca lanza.
* `test_el_asistente_maneja_el_mapa_en_chromium` (Playwright): el panel de verdad (uvicorn, en /panel como en Railway)
  con personas inventadas en Yondó y los mapas base falsos (estilos, teselas, fuentes, relieve y satélite se contestan
  desde el navegador: este entorno y el CI no salen a internet). Desde la página se importa `agente-mapa.js` y se
  aplican las acciones del §6 de docs/agente.md: volar (con polígono y sin él), filtros (la URL y la cifra cambian;
  el aviso «Filtros del asistente · Quitar» aparece con un filtro sin select y lo quita), capas, resaltar (la fuente
  `agente` tiene los puntos; las etiquetas no son HTML), base satélite (las capas `agente-*` sobreviven a setStyle),
  hexágono, recorrido, giro y luego volar (el vuelo llega), limpiar, zona, tipos raros y entradas inválidas. También
  desde otra vista (/personas): navega a /mapa con los filtros en la URL (una sola carga de puntos) y aplica al
  terminar de cargar sin que la presentación inicial pise la cámara. En el celular: el aviso de filtros se ve y se
  quita con el dedo. En todo: sin errores de página, sin promesas rechazadas sin atender y sin violaciones de CSP.

Se salta si no hay Node (o Node con Playwright), salvo en el CI, donde falla en vez de pasar en silencio.
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
import zlib
from pathlib import Path

import pymongo
import pytest
import uvicorn

from conftest import CASCO, MONGO, URI, insertar_personas

WEB_JS = Path(__file__).resolve().parents[1] / "web" / "js"
PUENTE = WEB_JS / "agente-mapa.js"


def _hay_node() -> bool:
    return bool(shutil.which("node"))


def _hay_playwright() -> bool:
    return _hay_node() and subprocess.run(
        ["node", "-e", "require(process.env.PLAYWRIGHT_MODULE || 'playwright')"], capture_output=True).returncode == 0


requiere_node = pytest.mark.skipif(not _hay_node() and not os.environ.get("CI"), reason="Sin Node")
requiere_navegador = pytest.mark.skipif(not _hay_playwright() and not os.environ.get("CI"),
                                        reason="Sin Node con Playwright (PLAYWRIGHT_MODULE o NODE_PATH)")


# ───────────────────────────── El puente, en Node ─────────────────────────────

GUION_PUENTE = r"""// El puente del mapa sin navegador: document, location y window mínimos. Uso: node <guion> <url del módulo>
const [modulo] = process.argv.slice(2);
const oyentes = [];
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/personas' };
globalThis.window = { addEventListener: (tipo, f) => { if (tipo === 'vista') oyentes.push(f); } };
const vista = (detail) => oyentes.forEach((f) => f({ detail }));
const P = await import(modulo);
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const navegadas = [];
const navegar = (ruta) => { navegadas.push(ruta); location.pathname = ruta.split('?')[0]; };
const mensaje = (p) => p.then(() => 'resolvió', (e) => e.message);
const r = { exports: Object.keys(P).sort() };

// 1. Sin mapa: encola y navega una vez, con los filtros sencillos de la primera acción «filtros»
const p1 = P.accionesMapa([{ tipo: 'volar', lat: 7, lon: -73.9 },
  { tipo: 'filtros', valores: { zona: 'rural', con_cedula: true, edad_min: 18, sexo: null, fuente: '' } }], { navegar });
const p2 = P.accionesMapa({ tipo: 'limpiar' }, { navegar }); // ya en /mapa (cargando): solo espera
r.navegadas = navegadas.slice();
r.en_cola = P.accionesEnCola();
r.listo_antes = P.mapaListo();
r.estado_sin_mapa = P.estadoMapa();

// 2. Al registrarse aplica la cola en orden y después lo que llega directo
const aplicadas = [];
let estadoLanza = false;
const control = {
  aplicar: async (l) => { aplicadas.push(l.map((a) => a.tipo)); await dormir(5); return l.map((a) => ({ tipo: a.tipo, ok: true })); },
  estado: () => { if (estadoLanza) throw new Error('roto'); return { zoom: 12 }; },
};
r.registro_invalido = typeof P.registrarMapa({ aplicar: 1 });
r.listo_tras_invalido = P.mapaListo();
let quitar = P.registrarMapa(control);
const p3 = P.accionesMapa([{ tipo: 'giro', activo: false }]);
r.resultados = await Promise.all([p1, p2, p3]);
r.aplicadas = aplicadas.slice();
r.en_cola_despues = P.accionesEnCola();
r.listo = P.mapaListo();
r.estado = P.estadoMapa();
estadoLanza = true;
r.estado_que_lanza = P.estadoMapa();

// 3. Si la vista se quita antes de aplicar, la llamada pendiente falla con un motivo claro
const p4 = P.accionesMapa([{ tipo: 'limpiar' }]);
quitar();
r.cerrada = await mensaje(p4);
r.listo_tras_quitar = P.mapaListo();

// 4. Sin navegar y sin mapa, el plazo vence
location.pathname = '/panel/personas';
r.vencida = await mensaje(P.accionesMapa([{ tipo: 'limpiar' }], { espera: 30 }));
r.en_cola_vencida = P.accionesEnCola();

// 5. Otra vista mientras el mapa carga: se rechaza en el acto (el anuncio del propio mapa no rechaza)
navegadas.length = 0;
const p5 = P.accionesMapa([{ tipo: 'filtros', valores: { zona: 'urbana', area_id: 3 } }], { navegar });
vista({ ruta: '/mapa', ok: true });
r.en_cola_tras_mapa = P.accionesEnCola();
location.pathname = '/panel/reuniones';
vista({ ruta: '/reuniones', ok: true });
r.otra_vista = await mensaje(p5);
r.navegadas_zona = navegadas.slice();

// 6. El mapa no se pudo abrir
navegadas.length = 0;
const p6 = P.accionesMapa([{ tipo: 'filtros', valores: { zona: 'rural', poligono: 'abc' } }], { navegar });
vista({ ruta: '/mapa', ok: false });
r.no_abrio = await mensaje(p6);
location.pathname = '/panel/personas';
const p7 = P.accionesMapa([{ tipo: 'filtros', valores: { q: { $ne: 1 }, zona: 'rural' } }], { navegar, espera: 20 });
location.pathname = '/panel/personas';
const p8 = P.accionesMapa([{ tipo: 'filtros', valores: ['zona', 'rural'] }], { navegar: (ruta) => navegadas.push(`otra ${ruta}`), espera: 20 });
await Promise.allSettled([p7, p8]);
r.navegadas_raras = navegadas.slice();

// 7. Con el mapa listo otra vez, lo directo no navega
quitar = P.registrarMapa(control);
navegadas.length = 0;
location.pathname = '/panel/mapa';
r.directo = await P.accionesMapa([{ tipo: 'base', base: 'auto' }], { navegar });
r.navegadas_directo = navegadas.slice();
console.log(JSON.stringify(r));
"""


@requiere_node
def test_puente_cola_orden_y_navegacion(tmp_path):
    (tmp_path / "puente.mjs").write_text(GUION_PUENTE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "puente.mjs"), PUENTE.as_uri()], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    # El contrato que usan el asistente (agente.js) y la vista: los mismos cinco nombres
    assert r["exports"] == ["accionesEnCola", "accionesMapa", "estadoMapa", "mapaListo", "registrarMapa"]
    # Una sola navegación, con los filtros de la primera acción «filtros» (sin los vacíos; sí y no como 1 y 0)
    assert r["navegadas"] == ["/mapa?zona=rural&con_cedula=1&edad_min=18"]
    assert r["en_cola"] == 2 and r["listo_antes"] is False and r["estado_sin_mapa"] is None
    assert r["registro_invalido"] == "function" and r["listo_tras_invalido"] is False
    # La cola sale en orden y antes que lo directo; cada llamada recibe sus resultados
    assert r["aplicadas"] == [["volar", "filtros"], ["limpiar"], ["giro"]]
    assert r["resultados"] == [[{"tipo": "volar", "ok": True}, {"tipo": "filtros", "ok": True}],
                               [{"tipo": "limpiar", "ok": True}], [{"tipo": "giro", "ok": True}]]
    assert r["en_cola_despues"] == 0 and r["listo"] is True and r["estado"] == {"zoom": 12}
    assert r["estado_que_lanza"] is None  # va en el contexto de cada mensaje: nunca lanza
    assert r["cerrada"] == "El mapa se cerró antes de aplicar las acciones" and r["listo_tras_quitar"] is False
    assert r["vencida"] == "El mapa no terminó de cargar" and r["en_cola_vencida"] == 0
    assert r["en_cola_tras_mapa"] == 1
    assert r["otra_vista"] == "Se abrió otra vista antes de que el mapa terminara de cargar"
    # `area_id` y `poligono` abren una zona si van en la URL del mapa: con ellos no viaja ningún filtro
    assert r["navegadas_zona"] == ["/mapa"]
    assert r["no_abrio"] == "El mapa no se pudo abrir"
    # Un valor que no es sencillo (objeto) o `valores` que no es un objeto: tampoco viaja nada en la URL
    assert r["navegadas_raras"] == ["/mapa", "/mapa", "otra /mapa"]
    assert r["directo"] == [{"tipo": "base", "ok": True}] and r["navegadas_directo"] == []


def test_mapa_registra_y_quita_el_control():
    """La vista se registra al terminar `load` y se quita en su limpieza (si no, el asistente aplicaría sobre un mapa
    destruido); las capas del asistente se rehacen en `agregarCapas` (sobreviven a setStyle)."""
    t = (WEB_JS / "vistas" / "mapa.js").read_text(encoding="utf-8")
    assert "import { registrarMapa } from '../agente-mapa.js';" in t
    assert t.count("registrarMapa({ aplicar: aplicarAcciones, estado: instantanea })") == 1
    limpieza = t[t.rindex("return () => {"):]
    assert "quitarControl?.()" in limpieza and "clearTimeout(tIntro)" in limpieza
    agregar = t[t.index("function agregarCapas()"):t.index("function aplicarVisibilidad()")]
    for capa in ("agente-relleno", "agente-borde", "agente-puntos", "agente-etiquetas"):
        assert f"id: '{capa}'" in agregar, capa
    # Las acciones se buscan en un Map: «constructor» o «__proto__» no encuentran nada
    assert "const ACCIONES = new Map(" in t


# ───────────────────────────── En Chromium ─────────────────────────────

def _png_plano(r: int = 128, g: int = 0, b: int = 0, lado: int = 256) -> bytes:
    """PNG de un solo color: con (128, 0, 0) es relieve plano en codificación terrarium (altura 0); también sirve de
    tesela satelital."""
    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    crudo = (b"\x00" + bytes([r, g, b]) * lado) * lado
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(crudo, 9)) + trozo(b"IEND", b""))


def _caja(geom: dict) -> list[list[float]]:
    xs, ys = [], []

    def rec(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                rec(x)
    rec(geom["coordinates"])
    return [[min(xs), min(ys)], [max(xs), max(ys)]]


def _sembrar(db) -> dict:
    """Personas inventadas: 24 en el casco (12 mujeres), 10 rurales ubicadas (4 mujeres) y 4 rurales sin ubicación. Y
    los lugares de las pruebas: una vereda con polígono y un barrio con punto (del nomenclátor sembrado)."""
    personas = []
    for i in range(24):
        personas.append({"nombre": f"PERSONA URBANA {i} INVENTADA", "sexo": "F" if i % 2 else "M", "zona": "urbana",
                         "lat": round(CASCO[1] + (i % 6 - 3) * 0.0012, 6), "lon": round(CASCO[0] + (i // 6 - 2) * 0.0012, 6),
                         "geo_precision": "direccion"})
    for i in range(10):
        personas.append({"nombre": f"PERSONA RURAL {i} INVENTADA", "sexo": "F" if i < 4 else "M", "zona": "rural",
                         "lat": round(7.09 + i * 0.002, 6), "lon": round(-73.95 + i * 0.002, 6), "geo_precision": "direccion"})
    for i in range(4):
        personas.append({"nombre": f"PERSONA SIN PUNTO {i} INVENTADA", "sexo": "M", "zona": "rural"})
    ids = insertar_personas(db, personas)
    # La vereda de San Miguel del Tigre: su polígono simplificado no cruza lados (abrirla como zona no da avisos)
    vereda = (db.lugares.find_one({"tipo": "vereda", "nombre": "SAN MIGUEL DEL TIGRE", "geom": {"$ne": None}})
              or db.lugares.find_one({"tipo": "vereda", "geom": {"$ne": None}, "lat": {"$ne": None}}, sort=[("_id", 1)]))
    barrio = db.lugares.find_one({"tipo": "barrio", "lat": {"$ne": None}}, sort=[("_id", 1)])
    assert vereda and barrio, "el nomenclátor sembrado trae veredas con polígono y barrios con punto"
    return {
        "png": base64.b64encode(_png_plano()).decode(),
        "vereda": {"id": vereda["_id"], "nombre": vereda["nombre"], "tipo": "vereda", "lat": vereda["lat"],
                   "lon": vereda["lon"], "caja": _caja(vereda["geom"])},
        "barrio": {"id": barrio["_id"], "nombre": barrio["nombre"], "tipo": "barrio", "lat": barrio["lat"],
                   "lon": barrio["lon"]},
        # Doce personas del casco para resaltar (con su id: el globo del punto abre su ficha)
        "resaltar": [{"id": ids[i], "lat": personas[i]["lat"], "lon": personas[i]["lon"],
                      "etiqueta": f"Persona inventada {i}"} for i in range(12)],
        "casco": list(CASCO),
        "cuentas": {"todas": 34, "rural_total": 14, "rural": 10, "urbana": 24, "rural_mujeres": 4},
    }


@pytest.fixture
def panel_mapa(cfg, tmp_path):
    """El servidor único de verdad (uvicorn h11, el panel en /panel, como en Railway) en un puerto libre, con las
    personas inventadas de `_sembrar`. Devuelve (base del panel, datos para el guion)."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    sitio = tmp_path / "site"
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
        yield f"http://127.0.0.1:{sock.getsockname()[1]}/panel", datos
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


GUION = r"""// El asistente maneja el Mapa 3D en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> <datos.json> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const [base, usuario, clave, rutaDatos, capturas] = process.argv.slice(2);
const D = JSON.parse(fs.readFileSync(rutaDatos, 'utf8'));
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const PNG = Buffer.from(D.png, 'base64');
const ESTILO = JSON.stringify({ version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf', sources: {},
  layers: [{ id: 'fondo', type: 'background', paint: { 'background-color': '#d9d9d4' } }] });
const TILEJSON = JSON.stringify({ tilejson: '2.2.0', tiles: ['https://tiles.openfreemap.org/planet/x/{z}/{x}/{y}.pbf'], minzoom: 0, maxzoom: 14 });
const XSS = '<img src=x onerror="window.__xss=1">';
// Con un cambio de dirección del texto (U+202E), un carácter de control y más de 80 letras
const LARGA = '\u202eNombre\u0007 con   espacios ' + 'x'.repeat(100);

// Los mapas base son externos (openfreemap, ESRI, el relieve en S3) y aquí no hay internet: se contestan desde el
// navegador con un estilo mínimo, TileJSON, teselas y fuentes vacías y un PNG plano. Lo demás de fuera se corta.
async function preparar(ctx, salida) {
  const cors = { 'Access-Control-Allow-Origin': '*' };
  await ctx.route((u) => u.origin !== origen, (r) => {
    const u = r.request().url();
    if (/^https:\/\/tiles\.openfreemap\.org\/styles\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: ESTILO });
    if (/^https:\/\/tiles\.openfreemap\.org\/planet$/.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: TILEJSON });
    if (/^https:\/\/tiles\.openfreemap\.org\/(planet|fonts)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/x-protobuf', body: Buffer.alloc(0) });
    if (/^https:\/\/(s3\.amazonaws\.com\/elevation-tiles-prod|server\.arcgisonline\.com)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'image/png', body: PNG });
    if (/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(u)) return r.abort(); // las letras del panel (index.html)
    salida.cortadas.push(u.slice(0, 120));
    return r.abort();
  });
  await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
    window.__rechazos = [];
    addEventListener('unhandledrejection', (e) => window.__rechazos.push(String(e.reason?.message || e.reason)));
    window.__avisos = [];
    new MutationObserver((cambios) => { for (const c of cambios) for (const n of c.addedNodes) {
      if (n.nodeType === 1 && n.classList.contains('aviso')) window.__avisos.push(`${n.className}: ${n.textContent}`);
    } }).observe(document, { childList: true, subtree: true });
  });
}

function vigilar(page, salida) {
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) salida.consola.push(m.text().slice(0, 300)); });
  page.on('response', (r) => {
    const u = new URL(r.url());
    if (u.origin === origen && r.status() >= 400 && !(r.status() === 401 && u.pathname.endsWith('/api/yo'))) salida.http.push(`${r.status()} ${u.pathname}${u.search}`);
  });
}

async function entrar(page, ruta = '/') {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app');
  if (ruta !== '/') { await page.goto(base + ruta, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('#app'); }
  await page.evaluate(async () => { window.__P = await import(new URL('agente-mapa.js', document.querySelector('script[type=module]').src).href); window.__A = await import(new URL('app.js', document.querySelector('script[type=module]').src).href); });
}

const listo = (page) => page.waitForFunction(() => window.__P.mapaListo(), null, { timeout: 90000, polling: 200 });
const acc = (page, acciones) => page.evaluate((a) => window.__P.accionesMapa(a), acciones);
const est = (page) => page.evaluate(() => window.__P.estadoMapa());
const fuente = (page) => page.evaluate(async () => {
  const s = window.__mapa?.getSource('agente');
  return s ? (await s.getData()).features.map((f) => f.geometry.type) : null;
});
const pantalla = (page) => page.evaluate(() => {
  const chip = document.querySelector('#filtros-asistente');
  const b = chip?.querySelector('[data-quitar-asistente]')?.getBoundingClientRect();
  return { search: location.search, ruta: location.pathname, cifra: document.querySelector('#cifra')?.textContent,
    chip: chip && !chip.hidden ? chip.textContent.replace(/\s+/g, ' ').trim() : null,
    chip_dentro: b ? b.left >= 0 && b.right <= innerWidth && b.top >= 0 && b.bottom <= innerHeight : null,
    desborde: document.scrollingElement.scrollWidth > innerWidth,
    zona_select: document.querySelector('[data-f="zona"]')?.value };
});
const T0 = Date.now();
const marcas = [];
const marca = (nombre) => marcas.push([nombre, Date.now() - T0]);
// Hasta que el mapa queda quieto y con todo dibujado (el GeoJSON nuevo pasa por el worker antes de verse)
const quietoYDibujado = (page) => page.evaluate(() => new Promise((ok) => {
  const m = window.__mapa;
  setTimeout(ok, 15000);
  if (m.loaded() && !m.isMoving()) setTimeout(ok, 300); else m.once('idle', ok);
}));
const dibujados = (page, capa) => page.evaluate((c) => window.__mapa.queryRenderedFeatures({ layers: [c] })
  .map((f) => f.properties.color || null), capa);
const foto = (page, nombre) => (capturas ? page.screenshot({ path: `${capturas}/${nombre}.png` }).catch(() => {}) : null);
const quieto = (page) => page.waitForFunction(() => !window.__mapa.isMoving(), null, { timeout: 15000, polling: 100 });

async function escritorio(nav, salida) {
  const S = salida.escritorio = {};
  // Con movimiento reducido los vuelos son saltos: cada cuadro con relieve cuesta mucho en SwiftShader. La presentación
  // inicial es `essential` y anima igual, así que comprobar que no pisa la cámara sigue teniendo sentido. El giro se
  // prueba aparte, con animaciones (es lo que cancela los vuelos)
  const ctx = await nav.newContext({ viewport: { width: 1024, height: 700 }, reducedMotion: 'reduce' });
  await preparar(ctx, salida);
  const page = await ctx.newPage();
  vigilar(page, salida);
  const puntos = [];
  page.on('request', (q) => { if (q.url().includes('/api/mapa/puntos')) puntos.push(new URL(q.url()).search); });
  await entrar(page);
  let t0 = Date.now();
  await page.click('#nav a[data-nav="mapa"]');
  await listo(page);
  S.carga_ms = Date.now() - t0;
  marca('carga');
  const V = D.vereda, B = D.barrio;
  // Sin relieve ni edificios mientras tanto: cada cuadro con relieve cuesta segundos en SwiftShader (se vuelve a
  // encender para el mapa satelital y al final)
  S.sin_relieve = await acc(page, [{ tipo: 'capas', valores: { relieve: false, edificios: false } }]);
  S.sin_relieve_terreno = await page.evaluate(() => !!window.__mapa.getTerrain());

  // Volar a una vereda (encuadra su polígono y lo marca) y, 1,5 s después, la presentación no la pisó
  S.volar_poligono = { r: await acc(page, [{ tipo: 'volar', lugar: { ...V, caja: undefined, poligono: true } }]) };
  S.volar_poligono.fuente = await fuente(page);
  await page.waitForTimeout(1500);
  S.volar_poligono.despues = await est(page);
  marca('volar_poligono');
  // A un barrio (su punto, zoom 16,5) y a coordenadas
  S.volar_punto = { r: await acc(page, [{ tipo: 'volar', lugar: { ...B, poligono: false } }]), fuente: await fuente(page) };
  S.volar_coordenadas = await acc(page, [{ tipo: 'volar', lat: D.casco[1], lon: D.casco[0], zoom: 15.5, pitch: 30, bearing: 10 }]);
  S.volar_malos = await acc(page, [{ tipo: 'volar', lat: 4.6, lon: -74.08 }, { tipo: 'volar', lat: '7', lon: -73.9 }, { tipo: 'volar' },
    { tipo: 'volar', lugar: { id: 'x' } }, { tipo: 'volar', lat: 7, lon: -73.9, zoom: 40 }, { tipo: 'volar', lugar: { id: 999999, poligono: true } }]);

  marca('volar');
  // Filtros: la URL y la cifra cambian; uno sin select muestra el aviso y «Quitar» lo quita
  S.filtros_rural = { r: await acc(page, [{ tipo: 'filtros', valores: { zona: 'rural' }, reemplazar: true }]), p: await pantalla(page) };
  S.filtros_sexo = { r: await acc(page, [{ tipo: 'filtros', valores: { sexo: 'F' }, reemplazar: false }]), p: await pantalla(page) };
  await foto(page, 'mapa-filtros-asistente');
  await page.click('[data-quitar-asistente]');
  await page.waitForFunction(() => !location.search.includes('sexo') && document.querySelector('#filtros-asistente').hidden);
  await page.waitForFunction((n) => document.querySelector('#cifra').textContent === n, String(D.cuentas.rural));
  S.quitar = await pantalla(page);
  // Como llegan del flujo (JSON.parse): «__proto__» es una clave propia, no el prototipo
  S.filtros_malos = { r: await page.evaluate(() => window.__P.accionesMapa(JSON.parse(`[
    {"tipo": "filtros", "valores": {"situacion": "xx"}}, {"tipo": "filtros", "valores": {"poligono": "abc"}},
    {"tipo": "filtros", "valores": {"zona": {"$ne": 1}}}, {"tipo": "filtros", "valores": "zona=rural"},
    {"tipo": "filtros", "valores": {"__proto__": {"zona": "urbana"}}}]`))), p: await pantalla(page) };
  S.filtros_todos = { r: await acc(page, [{ tipo: 'filtros', valores: {}, reemplazar: true }]), p: await pantalla(page) };

  marca('filtros');
  // Capas
  S.capas = { r: await acc(page, [{ tipo: 'capas', valores: { calor: false, columnas: true } }, { tipo: 'capas', valores: { inventada: true } },
    { tipo: 'capas', valores: { calor: 'no' } }, { tipo: 'capas', calor: true }]) };
  S.capas.calor = await page.evaluate(() => [window.__mapa.getLayoutProperty('calor', 'visibility'), document.querySelector('[data-capa="calor"]').checked]);

  // Resaltar: la fuente `agente` tiene los puntos; las etiquetas (una con HTML) se dibujan en WebGL
  const puntosR = D.resaltar.map((p, i) => (i === 3 ? { ...p, etiqueta: XSS + ' Persona inventada' } : i === 4 ? { ...p, etiqueta: LARGA } : p));
  S.resaltar = { r: await acc(page, [{ tipo: 'resaltar', puntos: [...puntosR, { lat: 4.6, lon: -74.08, etiqueta: 'Fuera' }], color: '#1baf7a' }]) };
  S.resaltar.fuente = await fuente(page);
  S.resaltar.etiquetas = await page.evaluate(async () => (await window.__mapa.getSource('agente').getData()).features
    .map((f) => f.properties.etiqueta ?? null));
  S.resaltar.xss = await page.evaluate(() => [window.__xss ?? null, document.querySelectorAll('img[src="x"]').length]);
  await quietoYDibujado(page);
  S.resaltar.dibujados = await dibujados(page, 'agente-puntos');
  await foto(page, 'mapa-resaltar');
  S.resaltar_malos = await acc(page, [{ tipo: 'resaltar', puntos: Array.from({ length: 501 }, () => ({ lat: 7, lon: -73.9 })) },
    { tipo: 'resaltar', puntos: [{ lat: 7, lon: -73.9 }], color: 'red' }, { tipo: 'resaltar', puntos: [{ lat: 4.6, lon: -74 }] },
    { tipo: 'resaltar', puntos: [] }, { tipo: 'resaltar', puntos: [{ lat: 7, lon: -73.9 }], sumar: 'si' }]);
  S.resaltar_sumar = { r: await acc(page, [{ tipo: 'resaltar', puntos: D.resaltar.slice(0, 2), sumar: true, encuadrar: false }]), fuente: await fuente(page) };

  marca('resaltar');
  // Mapa satelital: setStyle lo borra todo y agregarCapas lo rehace desde `estado` (también el relieve)
  S.base = { r: await acc(page, [{ tipo: 'capas', valores: { relieve: true } }, { tipo: 'base', base: 'satelite' }]) };
  S.base.despues = await page.evaluate(async () => {
    const m = window.__mapa;
    return { capas: ['agente-relleno', 'agente-borde', 'agente-puntos', 'agente-etiquetas', 'hex-3d', 'puntos', 'veredas-relleno'].filter((c) => !!m.getLayer(c)),
      satelite: !!m.getSource('sat'), calor: m.getLayoutProperty('calor', 'visibility'), terreno: !!m.getTerrain(),
      pulsado: document.querySelector('[data-base="satelite"]').getAttribute('aria-pressed') };
  });
  S.base.fuente = await fuente(page);
  S.base_repetida = await acc(page, [{ tipo: 'base', base: 'satelite' }, { tipo: 'base', base: 'auto' }, { tipo: 'base', base: 'mapa' }]);
  await acc(page, [{ tipo: 'capas', valores: { relieve: false } }]);

  marca('base');
  // Hexágono y recorrido
  S.hexagono = { r: await acc(page, [{ tipo: 'hexagono', tamano: '400' }, { tipo: 'hexagono', tamano: 77 }, { tipo: 'hexagono', tamano: 'constructor' }]) };
  S.hexagono.pulsado = await page.evaluate(() => document.querySelector('[data-radio="400"]').getAttribute('aria-pressed'));
  S.hexagono.estado = (await est(page)).radio_m;
  S.recorrido = await acc(page, [{ tipo: 'recorrido', nombre: 'casco' }, { tipo: 'recorrido', nombre: 'luna' }]);

  marca('hex_recorrido');
  // Giro y luego volar: el giro (rotateTo en cada cuadro) cancelaría el vuelo; volar lo detiene antes. Con animaciones
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.evaluate(() => window.__mapa.jumpTo({ center: [-73.95, 7.09], zoom: 12 }));
  S.giro_volar = { r: await acc(page, [{ tipo: 'giro', activo: true }, { tipo: 'volar', lat: D.casco[1], lon: D.casco[0], zoom: 16 }]) };
  S.giro_volar.estado = await est(page);
  // Lo mismo con los botones: «Girar» y luego «Casco urbano» llega al casco
  await page.evaluate(() => window.__mapa.jumpTo({ center: [-73.95, 7.09], zoom: 12 }));
  await page.click('[data-vista="girar"]');
  await page.waitForTimeout(300);
  await page.click('[data-vista="casco"]');
  await page.waitForTimeout(400);
  await quieto(page);
  S.giro_botones = await est(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  S.con_relieve = await acc(page, [{ tipo: 'capas', valores: { relieve: true, edificios: true } }]);
  S.con_relieve_terreno = await page.evaluate(() => !!window.__mapa.getTerrain());

  marca('giro');
  // Zona de una vereda y cerrarla
  S.zona = { r: await acc(page, [{ tipo: 'zona', lugar_id: V.id }]) };
  S.zona.estado = (await est(page)).zona;
  S.zona.cerrar = await acc(page, [{ tipo: 'zona', cerrar: true }, { tipo: 'zona', area_id: 1, lugar_id: V.id }]);
  S.zona.despues = (await est(page)).zona;

  // Limpiar, tipos raros y demasiadas acciones
  S.limpiar = { r: await acc(page, [{ tipo: 'limpiar' }]), fuente: await fuente(page), resaltados: (await est(page)).resaltados };
  S.raros = await acc(page, [{ tipo: 'constructor' }, { tipo: '__proto__' }, null, 'volar', { tipo: 'nada' }, { tipo: 'toString' }, []]);
  S.muchas = (await acc(page, Array.from({ length: 21 }, () => ({ tipo: 'hexagono', tamano: 'auto' })))).map((x) => x.ok);

  marca('zona_limpiar');
  // Desde otra vista: navega con los filtros en la URL (una sola carga de puntos) y aplica al terminar de cargar
  await page.evaluate(() => window.__A.ir('/personas'));
  await page.waitForFunction(() => document.querySelector('#nav a[aria-current="page"]')?.dataset.nav === 'personas' && !window.__P.mapaListo());
  await page.waitForTimeout(300);
  puntos.length = 0;
  t0 = Date.now();
  S.otra_vista = { r: await page.evaluate((a) => window.__P.accionesMapa(a, { navegar: window.__A.ir }), [
    { tipo: 'filtros', valores: { zona: 'urbana' }, reemplazar: true }, { tipo: 'recorrido', nombre: 'casco' },
    { tipo: 'resaltar', puntos: D.resaltar.slice(0, 3), encuadrar: false }]) };
  S.otra_vista.ms = Date.now() - t0;
  S.otra_vista.p = await pantalla(page);
  S.otra_vista.puntos = puntos.slice();
  S.otra_vista.fuente = await fuente(page);
  await page.waitForTimeout(2000); // la presentación habría salido a los 0,9 s
  S.otra_vista.despues = await est(page);
  S.otra_vista.cola = await page.evaluate(() => window.__P.accionesEnCola());

  marca('otra_vista');
  // La persona se va a otra vista mientras el mapa carga: la acción se rechaza en el acto
  await page.evaluate(() => window.__A.ir('/personas'));
  await page.waitForFunction(() => !window.__P.mapaListo());
  S.se_fue = await page.evaluate(async () => {
    const p = window.__P.accionesMapa([{ tipo: 'recorrido', nombre: 'casco' }], { navegar: window.__A.ir });
    await new Promise((ok) => setTimeout(ok, 150));
    window.__A.ir('/reuniones');
    const t = performance.now();
    const motivo = await p.then(() => 'resolvió', (e) => e.message);
    return { motivo, ms: Math.round(performance.now() - t), cola: window.__P.accionesEnCola() };
  });
  S.rechazos = await page.evaluate(() => window.__rechazos);
  S.avisos = await page.evaluate(() => window.__avisos);
  await ctx.close();
}

async function celular(nav, salida) {
  const S = salida.celular = {};
  const ctx = await nav.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
  await preparar(ctx, salida);
  const page = await ctx.newPage();
  vigilar(page, salida);
  await entrar(page, '/mapa?sexo=F&zona=rural');
  await listo(page);
  marca('celular_carga');
  S.inicio = await pantalla(page);
  await foto(page, 'mapa-celular-filtros');
  // Con movimiento reducido el encuadre es un salto: la acción termina sin esperar un moveend que no llega
  S.resaltar = { r: await acc(page, [{ tipo: 'resaltar', puntos: D.resaltar.slice(0, 2) }]), fuente: await fuente(page) };
  await page.tap('[data-quitar-asistente]');
  await page.waitForFunction(() => !location.search.includes('sexo') && document.querySelector('#filtros-asistente').hidden);
  await page.waitForFunction((n) => document.querySelector('#cifra').textContent === n, String(D.cuentas.rural));
  S.quitar = await pantalla(page);
  S.rechazos = await page.evaluate(() => window.__rechazos);
  S.avisos = await page.evaluate(() => window.__avisos);
  await foto(page, 'mapa-celular');
  await ctx.close();
}

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const salida = { errores: [], consola: [], csp: [], http: [], cortadas: [] };
  try {
    await escritorio(nav, salida);
    await celular(nav, salida);
  } finally { await nav.close(); }
  salida.marcas = marcas;
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _cerca(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _ok(resultados: list) -> bool:
    return all(r.get("ok") is True for r in resultados)


@requiere_navegador
def test_el_asistente_maneja_el_mapa_en_chromium(panel_mapa, cfg, tmp_path):
    base, datos = panel_mapa
    (tmp_path / "mapa.cjs").write_text(GUION, encoding="utf-8")
    (tmp_path / "datos.json").write_text(json.dumps(datos), encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_MAPA", "")  # para mirarlas a mano
    p = subprocess.run(["node", str(tmp_path / "mapa.cjs"), base, cfg.usuario, cfg.clave, str(tmp_path / "datos.json"),
                        capturas], capture_output=True, text=True, timeout=420)
    assert p.returncode == 0, (p.stdout[-3000:], p.stderr[-3000:])
    salida = json.loads(p.stdout.strip().splitlines()[-1])
    if capturas:
        (Path(capturas) / "resultado-mapa.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                                           encoding="utf-8")
    e, cuentas, casco = salida["escritorio"], datos["cuentas"], datos["casco"]

    # Volar a la vereda: encuadra su polígono (el centro queda en su caja) y lo marca en la fuente del asistente; la
    # presentación inicial (que sale a los 0,9 s de cargar) no lo pisó
    (r,) = e["volar_poligono"]["r"]
    (oeste, sur), (este, norte) = datos["vereda"]["caja"]
    holgura = max(este - oeste, norte - sur) * 0.3
    assert r["ok"] and r["encuadre"] == "poligono" and r["lugar"]["id"] == datos["vereda"]["id"], r
    assert oeste - holgura <= r["centro"][0] <= este + holgura and sur - holgura <= r["centro"][1] <= norte + holgura, r
    assert r["zoom"] <= 15.5
    assert e["volar_poligono"]["fuente"] in (["Polygon"], ["MultiPolygon"])
    despues = e["volar_poligono"]["despues"]
    assert despues["centro"] == r["centro"] and despues["zoom"] == r["zoom"] and despues["foco"] is True, despues
    # Al barrio: su punto, zoom 16,5; la marca de la vereda se va
    (r,) = e["volar_punto"]["r"]
    assert r["ok"] and r["encuadre"] == "punto" and _cerca(r["zoom"], 16.5, 0.01), r
    assert _cerca(r["centro"][0], datos["barrio"]["lon"], 1e-4) and _cerca(r["centro"][1], datos["barrio"]["lat"], 1e-4), r
    assert e["volar_punto"]["fuente"] == []
    (r,) = e["volar_coordenadas"]
    assert r["ok"] and _cerca(r["zoom"], 15.5, 0.01) and r["pitch"] == 30 and r["bearing"] == 10, r
    assert _cerca(r["centro"][0], casco[0], 1e-4) and _cerca(r["centro"][1], casco[1], 1e-4), r
    malos = e["volar_malos"]
    assert [x["ok"] for x in malos] == [False] * 6, malos
    assert malos[0]["error"] == "Ese punto queda fuera de Yondó"
    assert "zoom" in malos[4]["error"] and "no tiene punto ni polígono" in malos[5]["error"]

    # Filtros: la URL, la cifra y el select cambian; el filtro sin select muestra el aviso; «Quitar» lo quita
    f = e["filtros_rural"]
    assert f["r"] == [{"filtros": {"zona": "rural"}, "total": cuentas["rural_total"], "ubicadas": cuentas["rural"],
                       "tipo": "filtros", "ok": True}], f
    assert f["p"]["search"] == "?zona=rural" and f["p"]["cifra"] == str(cuentas["rural"]) and f["p"]["zona_select"] == "rural"
    assert f["p"]["chip"] is None
    f = e["filtros_sexo"]
    assert f["r"][0]["ok"] and f["r"][0]["filtros"] == {"zona": "rural", "sexo": "F"}, f
    assert f["r"][0]["ubicadas"] == cuentas["rural_mujeres"] and f["p"]["cifra"] == str(cuentas["rural_mujeres"])
    assert "sexo=F" in f["p"]["search"] and "zona=rural" in f["p"]["search"]
    assert f["p"]["chip"].startswith("Filtros del asistente · Quitar") and "Sexo" in f["p"]["chip"], f["p"]
    q = e["quitar"]
    assert q["search"] == "?zona=rural" and q["chip"] is None and q["cifra"] == str(cuentas["rural"]), q
    f = e["filtros_malos"]
    assert [x["ok"] for x in f["r"]] == [False] * 5, f["r"]
    assert f["r"][1]["error"] == "Filtro no disponible en el mapa: poligono"
    # El 422 de la API devuelve los filtros de antes (la URL y la cifra no cambian)
    assert f["p"]["search"] == "?zona=rural" and f["p"]["cifra"] == str(cuentas["rural"]), f["p"]
    f = e["filtros_todos"]
    assert f["r"][0]["ok"] and f["r"][0]["filtros"] == {} and f["p"]["cifra"] == str(cuentas["todas"]), f

    # Capas
    assert [x["ok"] for x in e["capas"]["r"]] == [True, False, False, False], e["capas"]["r"]
    assert e["capas"]["r"][0]["capas"]["calor"] is False and e["capas"]["calor"] == ["none", False]

    # Resaltar: 12 puntos en la fuente (el de fuera de Yondó se cuenta), las etiquetas no se vuelven HTML
    (r,) = e["resaltar"]["r"]
    assert r["ok"] and r["resaltados"] == 12 and r["nuevos"] == 12 and r["fuera_de_yondo"] == 1, r
    assert e["resaltar"]["fuente"] == ["Point"] * 12
    assert e["resaltar"]["xss"] == [None, 0]
    # Las etiquetas son texto del mapa: el HTML queda como texto; sin controles ni cambios de dirección y ≤ 80 letras
    etiquetas = e["resaltar"]["etiquetas"]
    assert etiquetas[3] == '<img src=x onerror="window.__xss=1"> Persona inventada' and etiquetas[0] == "Persona inventada 0"
    assert etiquetas[4] == "Nombre con espacios " + "x" * 59 + "…" and len(etiquetas[4]) == 80, etiquetas[4]
    # Y se dibujan (no solo están en la fuente), con el color pedido
    assert len(e["resaltar"]["dibujados"]) >= 12 and set(e["resaltar"]["dibujados"]) == {"#1baf7a"}, e["resaltar"]["dibujados"]
    assert [x["ok"] for x in e["resaltar_malos"]] == [False] * 5, e["resaltar_malos"]
    assert e["resaltar_malos"][1]["error"] == "El color va como #rrggbb"
    assert e["resaltar_sumar"]["r"][0]["resaltados"] == 14 and e["resaltar_sumar"]["fuente"] == ["Point"] * 14

    # Satélite: las capas del asistente (y las demás) se rehacen, con sus datos y la visibilidad elegida
    assert e["base"]["r"][1] == {"base": "satelite", "recargado": True, "tipo": "base", "ok": True}, e["base"]
    assert e["base"]["r"][0]["ok"] and e["base"]["r"][0]["capas"]["relieve"] is True
    d = e["base"]["despues"]
    assert d["capas"] == ["agente-relleno", "agente-borde", "agente-puntos", "agente-etiquetas", "hex-3d", "puntos",
                          "veredas-relleno"], d
    assert d["satelite"] and d["calor"] == "none" and d["terreno"] and d["pulsado"] == "true", d
    assert e["base"]["fuente"] == ["Point"] * 14
    rep = e["base_repetida"]
    assert [x["ok"] for x in rep] == [True, True, False] and rep[0]["recargado"] is False and rep[1]["recargado"] is True

    # Hexágono y recorrido
    h = e["hexagono"]
    assert [x["ok"] for x in h["r"]] == [True, False, False] and h["r"][0]["radio_m"] == 400, h
    assert h["pulsado"] == "true" and h["estado"] == 400
    r, malo = e["recorrido"]
    assert r["ok"] and _cerca(r["centro"][0], casco[0], 1e-3) and _cerca(r["centro"][1], casco[1], 1e-3), r
    assert _cerca(r["zoom"], 14.6, 0.05) and malo["ok"] is False

    # Giro y luego volar: el vuelo llega y el giro quedó detenido (también con los botones)
    giro, vuelo = e["giro_volar"]["r"]
    assert giro["ok"] and giro["giro"] is True, giro
    assert vuelo["ok"] and _cerca(vuelo["zoom"], 16, 0.01), vuelo
    assert _cerca(vuelo["centro"][0], casco[0], 1e-4) and _cerca(vuelo["centro"][1], casco[1], 1e-4), vuelo
    assert e["giro_volar"]["estado"]["giro"] is False
    assert _ok(e["sin_relieve"]) and e["sin_relieve_terreno"] is False
    assert _ok(e["con_relieve"]) and e["con_relieve_terreno"] is True
    b = e["giro_botones"]
    assert _cerca(b["centro"][0], casco[0], 1e-3) and _cerca(b["centro"][1], casco[1], 1e-3) and _cerca(b["zoom"], 14.6, 0.05), b
    assert b["giro"] is False

    # Zona de una vereda (con su distribución) y cerrarla
    (r,) = e["zona"]["r"]
    assert r["ok"] and r["fase"] == "edicion" and r["puntos"] >= 3 and r["area_m2"] > 0, r
    assert e["zona"]["estado"]["fase"] == "edicion"
    assert e["zona"]["cerrar"][0] == {"zona": None, "tipo": "zona", "ok": True}
    assert e["zona"]["cerrar"][1]["ok"] is False and e["zona"]["despues"] is None

    # Limpiar, tipos raros (también los del prototipo de Object) y el tope de acciones por vez
    assert e["limpiar"]["r"][0]["ok"] and e["limpiar"]["fuente"] == [] and e["limpiar"]["resaltados"] == 0
    raros = e["raros"]
    assert [x["ok"] for x in raros] == [False] * 7, raros
    assert raros[0] == {"tipo": "constructor", "ok": False, "error": "Acción desconocida: constructor"}
    assert raros[2] == {"tipo": None, "ok": False, "error": "Acción no válida"}
    assert e["muchas"] == [True] * 20 + [False]

    # Desde Habitantes: navega a /mapa?zona=urbana, una sola carga de puntos (ya filtrada) y la cámara del recorrido
    # no la pisa la presentación
    o = e["otra_vista"]
    assert _ok(o["r"]) and [x["tipo"] for x in o["r"]] == ["filtros", "recorrido", "resaltar"], o["r"]
    assert o["r"][0]["total"] == cuentas["urbana"] and o["r"][2]["resaltados"] == 3
    assert o["p"]["ruta"] == "/panel/mapa" and o["p"]["search"] == "?zona=urbana", o["p"]
    assert o["puntos"] == ["?zona=urbana"], o["puntos"]
    assert o["fuente"] == ["Point"] * 3 and o["cola"] == 0
    assert _cerca(o["despues"]["centro"][0], casco[0], 1e-3) and _cerca(o["despues"]["centro"][1], casco[1], 1e-3), o
    assert _cerca(o["despues"]["zoom"], 14.6, 0.05), o["despues"]
    s = e["se_fue"]
    assert s["motivo"] == "Se abrió otra vista antes de que el mapa terminara de cargar" and s["ms"] < 5000 and s["cola"] == 0, s

    # Celular: el aviso de filtros se ve dentro de la pantalla y se quita con el dedo; con movimiento reducido el
    # encuadre es un salto y la acción termina igual
    c = salida["celular"]
    assert c["inicio"]["chip"].startswith("Filtros del asistente · Quitar") and c["inicio"]["chip_dentro"], c["inicio"]
    assert c["inicio"]["cifra"] == str(cuentas["rural_mujeres"]) and not c["inicio"]["desborde"], c["inicio"]
    assert _ok(c["resaltar"]["r"]) and c["resaltar"]["fuente"] == ["Point"] * 2, c["resaltar"]
    assert c["quitar"]["search"] == "?zona=rural" and c["quitar"]["chip"] is None and not c["quitar"]["desborde"]

    # En todo: sin errores de página ni de consola, sin promesas sin atender, sin avisos de error inesperados, sin
    # violaciones de CSP y sin pedir nada de fuera que no sea de los mapas base
    assert salida["errores"] == [] and salida["consola"] == [], (salida["errores"], salida["consola"])
    assert e["rechazos"] == [] and c["rechazos"] == [], (e["rechazos"], c["rechazos"])
    assert not [a for a in e["avisos"] + c["avisos"] if "error" in a.split(":")[0]], (e["avisos"], c["avisos"])
    assert salida["csp"] == [] and salida["cortadas"] == [], (salida["csp"], salida["cortadas"])
    # La única respuesta de error de la API fue el 422 de la situación inventada
    assert salida["http"] == ["422 /panel/api/mapa/puntos?zona=rural&situacion=xx"], salida["http"]
