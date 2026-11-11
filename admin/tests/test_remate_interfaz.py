"""Regresiones del remate de la interfaz del asistente (web/js/agente.js y css/agente.css): lo que las revisiones de los
arreglos dejaron abierto en el widget.

* 2 y 23 (alta): la tarjeta de aprobación muestra entero lo que se va a escribir. El servidor manda los valores enteros
  (hasta `bucle.TARJETA_VALOR` = 4.000 caracteres) y hasta `bucle.TARJETA_FILAS` = 40 filas, y no ofrece lo que no
  cabe; el widget los cortaba en silencio a 500 caracteres y a 30 filas, y se aprobaba sin ver el final. Ahora los
  muestra todos; un dato largo se desplaza dentro de su recuadro, con una sombra mientras queda texto y un aviso de que
  hay que desplazarlo; y si llegara más de lo que se puede mostrar, la tarjeta no deja aprobar y lo dice. Por los dos
  caminos: el evento `confirmar` en vivo y lo pendiente al volver a abrir la conversación.
* Un 409 `sin_pendientes` al decidir (otra pestaña ya lo atendió o llegó otra propuesta), antes del flujo o como `error`
  dentro de él, vuelve a traer la conversación: se ve lo que espera aprobación ahora y por qué cambió.
* El contexto de cada mensaje lleva solo lo que el servidor deja llegar al modelo: las claves de `sistema.CLAVES_FILTRO`
  y, del mapa, el zoom y el centro solo de lejos y redondeado (`sistema._mapa`).

Las pruebas con navegador corren en Chromium contra el panel de verdad (uvicorn, en /panel como en Railway) y contestan
/api/agente/* desde el navegador (`route.fulfill`), como test_revision_interfaz.py. El guion corre una vez por módulo
(cada caso en su propio contexto del navegador) y cada prueba revisa el suyo. Se saltan sin Node con Playwright, salvo
en el CI (allí fallan en vez de pasar en silencio).
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

from conftest import MONGO, URI
from test_agente_mapa import _png_plano, requiere_navegador, requiere_node

RAIZ = Path(__file__).resolve().parents[1]
AGENTE = (RAIZ / "web" / "js" / "agente.js").read_text(encoding="utf-8")
CSS = (RAIZ / "web" / "css" / "agente.css").read_text(encoding="utf-8")

# Carga agente.js en Node (sin navegador) y aplica a cada entrada (JSON por la entrada estándar: son largas) la función
# exportada que se pide
NODE = r"""
import { readFileSync } from 'node:fs';
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
const m = await import('./web/js/agente.js');
const entradas = JSON.parse(readFileSync(0, 'utf8'));
console.log(JSON.stringify(entradas.map((e) => m[process.argv[1]](e))));
"""


def _node(funcion: str, entradas: list) -> list:
    r = subprocess.run(["node", "--input-type=module", "-e", NODE, funcion], input=json.dumps(entradas), cwd=RAIZ,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _constante(nombre: str) -> int:
    m = re.search(rf"^const {nombre} = (\d+);", AGENTE, re.M)
    assert m, nombre
    return int(m.group(1))


# ───────────────────────────── La tarjeta: lo que acepta el widget es lo que ofrece el servidor ─────────────────────


def test_los_topes_de_la_tarjeta_son_los_del_servidor():
    """El widget no deja aprobar lo que pasa de los topes del servidor: tienen que ser los mismos, o una tarjeta que el
    servidor ofrece quedaría sin «Aprobar» (o una que no cabe se mostraría)."""
    from app.agente import bucle
    assert _constante("TARJETA_VALOR") == bucle.TARJETA_VALOR
    assert _constante("TARJETA_FILAS") == bucle.TARJETA_FILAS
    # Las etiquetas tampoco se recortan: una más larga que lo que admite el widget no se ofrece (en Mnemo son los
    # nombres de los argumentos que se mandan; test_remate_cierre.py)
    from app.agente.herramientas.base import Confirmacion, ErrorHerramienta
    assert _constante("TARJETA_ETIQUETA") == bucle.TARJETA_ETIQUETA
    t = bucle._tarjeta(Confirmacion("Prueba", [("e" * bucle.TARJETA_ETIQUETA, "v")]))
    assert t["detalle"][0][0] == "e" * bucle.TARJETA_ETIQUETA
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(Confirmacion("Prueba", [("e" * (bucle.TARJETA_ETIQUETA + 1), "v")]))
    assert e.value.codigo == "no_cabe"


@requiere_node
def test_la_tarjeta_muestra_entero_lo_que_el_servidor_ofrece():
    """filasTarjeta() devuelve todas las filas, enteras, de la tarjeta más grande que arma el servidor (40 filas y un
    valor de 4.000 caracteres, también contados como el servidor: un emoji es uno); lo que pasa de ahí, o una fila que
    no es un par de textos, da null (la tarjeta queda sin «Aprobar»). Antes: 30 filas y 500 caracteres, sin avisar."""
    from app.agente import bucle
    from app.agente.herramientas.base import Confirmacion
    fin = "FINAL QUE SOLO SE VE DESPLAZANDO"
    nota = ("Visita sin novedad. " * 300)[:bucle.TARJETA_VALOR - len(fin)] + fin
    filas = [("Persona", "ROSA INVENTADA"), ("Nota", nota)]
    filas += [(f"Dato {i}", f"Valor {i}") for i in range(3, bucle.TARJETA_FILAS)] + [("Último dato", "ÚLTIMA FILA")]
    grande = bucle._tarjeta(Confirmacion("Agregar una nota", filas))["detalle"]
    emojis = bucle._tarjeta(Confirmacion("Emojis", [("Nota", "🙂" * bucle.TARJETA_VALOR)]))["detalle"]
    assert len(grande) == bucle.TARJETA_FILAS and grande[1][1] == nota  # el servidor la ofrece entera
    entradas = [
        grande, emojis, [], None,
        grande + [["Una más", "x"]],                       # 41 filas
        [["Nota", nota + "x"]],                            # 4.001 caracteres
        [["Nota", "🙂" * (bucle.TARJETA_VALOR + 1)]],
        [["e" * 81, "x"]],                                 # una etiqueta más larga que las del servidor
        [["Nota"]], [["Nota", "x", "otro"]], [["Nota", {"texto": "x"}]], [["Nota", None]], [[3, "x"]], "Nota",
    ]
    a, b, c, d, *malas = _node("filasTarjeta", entradas)
    assert a == grande and a[1][1] == nota and a[-1] == ["Último dato", "ÚLTIMA FILA"]
    assert b == emojis
    assert c == [] and d == []
    assert malas == [None] * len(malas), malas


# ───────────────────────────── El contexto: solo lo que el servidor deja llegar al modelo ─────────────────────────────


@requiere_node
def test_el_contexto_lleva_las_claves_que_acepta_el_servidor():
    """Las claves de la dirección que manda el widget son las de `sistema.CLAVES_FILTRO`: ni la lista de origen, el
    liderazgo o el régimen de salud, ni la selección o el dibujo del mapa (el servidor ya los descartaba)."""
    from app.agente.sistema import CLAVES_FILTRO
    from app.api.filtros import Filtros
    candidatas = sorted(set(Filtros.model_fields) | set(CLAVES_FILTRO) | {"code", "state", "iss", "otra"})
    salida = _node("filtrosDe", [f"?{k}=1" for k in candidatas])
    pasan = {k for k, f in zip(candidatas, salida) if f}
    assert pasan == set(CLAVES_FILTRO), pasan ^ set(CLAVES_FILTRO)
    assert not {"lista", "lider", "regimen_salud", "ids", "poligono"} & pasan


@requiere_node
def test_el_encuadre_del_mapa_va_como_lo_deja_el_servidor():
    """encuadreMapa(): el zoom con un decimal y el centro solo de lejos (zoom de 14 o menos), con 2 decimales; sin zoom
    válido, nada (el centro podría ser de cerca). Lo que manda es lo que el servidor deja pasar al modelo."""
    from app.agente import sistema
    punto = [-73.912345, 6.987654]
    entradas = [
        {"centro": punto, "zoom": 16.5},                     # de cerca: al resaltar a una persona, su punto
        {"centro": punto, "zoom": 12.34},
        {"centro": punto, "zoom": 14},
        {"centro": {"lat": 6.987654, "lng": -73.912345}, "zoom": 9.06},
        {"center": punto, "zoom": 3},
        {"centro": punto}, {"centro": punto, "zoom": "12"}, {"centro": punto, "zoom": 99},
        {"centro": [200, 6.98], "zoom": 10}, {"centro": [-73.9], "zoom": 10}, None, "mapa",
    ]
    salida = _node("encuadreMapa", entradas)
    assert salida == [
        {"zoom": 16.5}, {"centro": [-73.91, 6.99], "zoom": 12.3}, {"centro": [-73.91, 6.99], "zoom": 14},
        {"centro": [-73.91, 6.99], "zoom": 9.1}, {"centro": [-73.91, 6.99], "zoom": 3},
        None, None, None, {"zoom": 10}, {"zoom": 10}, None, None,
    ], salida
    # Lo que el modelo recibe de lo que manda el widget es lo mismo que de la cámara entera (el servidor ya lo dejaba
    # así); sin zoom válido el widget no manda el centro, que el servidor sí dejaría pasar
    for antes, despues in zip(entradas, salida):
        if despues is not None:
            assert sistema._mapa(despues) == sistema._mapa(antes), (antes, despues)
    # camara() pasa por encuadreMapa() (antes mandaba el centro con 6 decimales también de cerca)
    cuerpo = AGENTE[AGENTE.index("  function camara() {"):AGENTE.index("  function contexto() {")]
    assert "return encuadreMapa(c);" in cuerpo and "r(lon, 6)" not in cuerpo


def test_el_recuadro_de_cada_dato_se_desplaza_y_avisa_que_sigue():
    """En agente.css, el dato de la tarjeta tiene altura máxima y se desplaza, con las sombras que dicen que sigue, y el
    aviso de los datos largos solo se ve en una tarjeta pendiente con alguno que no cabe."""
    regla = re.search(r"\.agente-tarjeta dd \{([^}]*)\}", CSS).group(1)
    assert "max-height:" in regla and "overflow-y: auto" in regla and "pre-wrap" in regla
    # Las sombras, solo en el que no se ve entero: en uno corto asomarían como rayas
    sombras = re.search(r"\.agente-tarjeta dd\[data-mas\] \{([^}]*)\}", CSS).group(1)
    assert sombras.count("local") == 2 and sombras.count("scroll") == 2 and "background" not in regla
    assert re.search(r"\.agente-tarjeta-largo \{[^}]*display: none", CSS)
    assert '.agente-tarjeta[data-estado="pendiente"]:has(dd[data-mas]) .agente-tarjeta-largo { display: block; }' in CSS


# ───────────────────────────── En Chromium ─────────────────────────────


@pytest.fixture(scope="module")
def resultados(tmp_path_factory):
    """El panel de verdad en un puerto libre y el guion de Chromium con todos los casos: {caso: resultado}."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    from app.agente import bucle
    from app.config import Config
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=URI,
                 mongodb_db=f"prueba_{uuid.uuid4().hex[:10]}", horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    tmp = tmp_path_factory.mktemp("remate_interfaz")
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
        datos = {"png": base64.b64encode(_png_plano()).decode(), "valor": bucle.TARJETA_VALOR,
                 "filas": bucle.TARJETA_FILAS}
        (tmp / "datos.json").write_text(json.dumps(datos), encoding="utf-8")
        (tmp / "guion.cjs").write_text(GUION, encoding="utf-8")
        capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp)  # para mirarlas a mano
        base = f"http://127.0.0.1:{sock.getsockname()[1]}/panel"
        r = subprocess.run(["node", str(tmp / "guion.cjs"), base, cfg.usuario, cfg.clave, str(tmp / "datos.json"),
                            capturas], capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
        yield {c["nombre"]: c for c in json.loads(r.stdout.strip().splitlines()[-1])["casos"]}
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def _revisar(resultados: dict, nombre: str) -> dict:
    caso = resultados[nombre]
    assert not caso.get("fallo"), (nombre, caso["fallo"], caso.get("datos"))
    malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
    assert caso["revisiones"] and not malas, (nombre, malas, caso.get("datos"))
    assert caso["errores"] == [], (nombre, caso["errores"])
    assert caso["csp"] == [], (nombre, caso["csp"])
    return caso


@requiere_navegador
def test_la_tarjeta_en_vivo_se_ve_entera_y_se_aprueba(resultados):
    """El evento `confirmar` con 40 filas y un valor de 4.000 caracteres: se ven todas, el valor entero (su final, al
    desplazar su recuadro) y la última fila, la tarjeta avisa que hay que desplazar y «Aprobar» manda la decisión."""
    _revisar(resultados, "vivo")


@requiere_navegador
def test_la_tarjeta_pendiente_al_reabrir_se_ve_entera_y_se_aprueba(resultados):
    """Lo mismo con lo pendiente de una conversación abierta desde «Conversaciones», en un celular de 360 px."""
    _revisar(resultados, "reabrir")


@requiere_navegador
def test_lo_que_no_cabe_no_se_puede_aprobar(resultados):
    """Más filas o un valor más largo que lo que ofrece el servidor (en vivo y al reabrir): la tarjeta lo dice y solo se
    puede rechazar; las demás tarjetas del mismo lote se deciden y se mandan juntas, como siempre."""
    _revisar(resultados, "no_cabe")


@requiere_navegador
def test_sin_pendientes_vuelve_a_traer_la_conversacion(resultados):
    """Un 409 `sin_pendientes` (antes del flujo) y el mismo código en un `error` del flujo: el widget vuelve a traer la
    conversación, muestra lo que espera aprobación ahora (y se aprueba) y dice por qué cambió."""
    _revisar(resultados, "sin_pendientes")


@requiere_navegador
def test_el_contexto_que_manda_el_widget(resultados):
    """Con filtros sensibles en la dirección y el mapa de cerca o de lejos: el cuerpo de POST /mensajes lleva solo las
    claves que acepta el servidor y el encuadre minimizado."""
    _revisar(resultados, "contexto")


GUION = r"""// Remate de la interfaz del asistente, en Chromium. Uso: node <guion> <base del panel> <usuario> <clave>
// <datos.json> <capturas>
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
const ESTADO = { disponible: true, motivo: null, configurado: true, es_admin: true, escritura: true, limite: { usados: 3, maximo: 300 },
  mnemo: { activo: false, origen: null }, sugerencias: ['¿Cómo va la base?'] };
const espera = { timeout: 20000 };
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const nd = (evs) => evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
const json = (d, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(d) });
const inicio = (conversacion) => ({ tipo: 'inicio', conversacion, titulo: 'Prueba' });
const fin = (motivo = 'listo') => ({ tipo: 'fin', motivo, limite: { usados: 4, maximo: 300 } });
const herr = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: 'agregar_nota', etiqueta: 'Agregando la nota', estado,
  ...(resumen ? { resumen } : {}) });
// Una escritura que espera aprobación: su chip pendiente y su tarjeta
const tarjeta = (id, titulo, detalle) => [herr(id, 'inicio'), herr(id, 'pendiente'),
  { tipo: 'confirmar', id, nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo, detalle, aviso: null }];
const aprobada = (conv, id) => ({ flujo: [inicio(conv), herr(id, 'aprobada'), herr(id, 'ok', 'Nota guardada'),
  { tipo: 'texto', texto: 'Listo.' }, fin()] });

// Lo más grande que ofrece el servidor (bucle.TARJETA_VALOR y TARJETA_FILAS): una nota cuyo final solo se ve
// desplazando su recuadro, y la última fila con su propia marca
const FINAL = 'FINAL QUE SOLO SE VE DESPLAZANDO';
const NOTA = 'Visita sin novedad. '.repeat(400).slice(0, D.valor - FINAL.length) + FINAL;
const GRANDE = [['Persona', 'ROSA INVENTADA'], ['Nota', NOTA],
  ...Array.from({ length: D.filas - 3 }, (_, i) => [`Dato ${i + 3}`, `Valor ${i + 3}`]), ['Último dato', 'ÚLTIMA FILA']];

// ── Contexto, «servidor» del asistente y ayudas ──
async function abrir(nav, caso, op = {}) {
  const ctx = await nav.newContext({ viewport: { width: 1400, height: 900 }, ...op });
  // Los mapas base son externos y aquí no hay internet: estilo mínimo, TileJSON, teselas y fuentes vacías y un PNG plano
  const cors = { 'Access-Control-Allow-Origin': '*' };
  await ctx.route((u) => u.origin !== origen, (r) => {
    const u = r.request().url();
    if (/^https:\/\/tiles\.openfreemap\.org\/styles\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: ESTILO });
    if (/^https:\/\/tiles\.openfreemap\.org\/planet$/.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: TILEJSON });
    if (/^https:\/\/tiles\.openfreemap\.org\/(planet|fonts)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'application/x-protobuf', body: Buffer.alloc(0) });
    if (/^https:\/\/(s3\.amazonaws\.com\/elevation-tiles-prod|server\.arcgisonline\.com)\//.test(u)) return r.fulfill({ status: 200, headers: cors, contentType: 'image/png', body: PNG });
    return r.abort();
  });
  await ctx.exposeBinding('__csp', (_, v) => caso.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => caso.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text().slice(0, 300)); });
  return { ctx, page, v: caso.revisiones, d: caso.datos };
}

// Contesta /api/agente/*: el estado y lo que devuelva `h(ruta, metodo, reg)`: {flujo} o {json, status}; null es un 404.
// `reg` lleva lo que llegó: los cuerpos de los mensajes y las decisiones y cuántas veces se pidió cada conversación
async function servirAgente(ctx, h) {
  const reg = { mensajes: [], confirmaciones: [], lecturas: {} };
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
    const req = route.request();
    const ruta = new URL(req.url()).pathname.slice(pref.length);
    const metodo = req.method();
    try {
      if (metodo === 'GET' && ruta === '/api/agente/estado') return await route.fulfill(json(ESTADO));
      if (metodo === 'POST' && ruta === '/api/agente/mensajes') reg.mensajes.push(req.postDataJSON());
      if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') reg.confirmaciones.push(req.postDataJSON());
      if (metodo === 'GET') reg.lecturas[ruta] = (reg.lecturas[ruta] || 0) + 1;
      const r = await h(ruta, metodo, reg);
      if (!r) return await route.fulfill(json({ detail: { codigo: 'no_existe', mensaje: 'No existe.' } }, 404));
      if (r.flujo) return await route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: nd(r.flujo) });
      return await route.fulfill(json(r.json, r.status || 200));
    } catch { /* la página cortó la petición o se cerró */ }
  });
  return reg;
}

async function ingresar(page) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])', espera);
}

async function enviar(page, texto) {
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
}
const listo = (page) => page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

// Abre la conversación `titulo` desde «Conversaciones»
async function reabrir(page, titulo) {
  await page.click('#agente-ver-historial');
  await page.locator('.agente-abrir', { hasText: titulo }).click();
  await page.waitForSelector('#agente-historial[hidden]', { state: 'attached', ...espera });
  await page.waitForFunction(() => !document.querySelector('#agente-mensajes .agente-cargando'), null, espera);
}

// Lo que muestra la tarjeta `i`: título, filas, si se puede aprobar o rechazar y sus avisos
const leerTarjeta = (page, i = 0) => page.evaluate((i) => {
  const t = document.querySelectorAll('.agente-tarjeta')[i];
  const visible = (b) => !!b && !b.hidden && !b.disabled && b.offsetParent !== null;
  const largo = t.querySelector('.agente-tarjeta-largo');
  return { titulo: t.querySelector('h3').textContent, estado: t.dataset.estado,
    filas: [...t.querySelectorAll('dl > div')].map((f) => [f.querySelector('dt').textContent, f.querySelector('dd').textContent]),
    aprobar: visible(t.querySelector('.agente-tarjeta-botones .btn.primario')),
    rechazar: visible(t.querySelector('.agente-tarjeta-botones .btn:not(.primario)')),
    no_cabe: t.querySelector('.agente-tarjeta-no-cabe')?.textContent || null,
    aviso_largos: !!largo && getComputedStyle(largo).display !== 'none', linea: t.querySelector('.agente-tarjeta-estado').textContent };
}, i);

// ¿Se ve en pantalla el último carácter del dato `j` de la tarjeta `i`? Lleva el recuadro a la vista (y, con
// `desplazar`, hasta su final) y mira qué elemento está de verdad en ese punto: ni tapado ni fuera de lo que se ve
const verFinal = (page, i, j, desplazar) => page.evaluate(([i, j, desplazar]) => {
  const dd = document.querySelectorAll('.agente-tarjeta')[i].querySelectorAll('dd')[j];
  if (!dd) return { se_ve: false, falta: true };
  dd.scrollTop = 0;
  dd.scrollIntoView({ block: 'center' });
  if (desplazar) dd.scrollTop = dd.scrollHeight;
  const nodo = dd.firstChild;
  const r = document.createRange();
  r.setStart(nodo, nodo.length - 1);
  r.setEnd(nodo, nodo.length);
  const c = r.getBoundingClientRect();
  const caja = dd.getBoundingClientRect();
  const y = c.top + c.height / 2;
  const s = getComputedStyle(dd);
  return { se_ve: y > caja.top && y < caja.bottom && document.elementFromPoint(c.left + c.width / 2, y) === dd,
    alto: dd.clientHeight, contenido: dd.scrollHeight, max: s.maxHeight, desborde: s.overflowY, sombras: s.backgroundAttachment,
    fondo: s.backgroundImage,
    marcado: dd.hasAttribute('data-mas'), teclado: dd.tabIndex === 0, ancho_ok: dd.scrollWidth <= dd.clientWidth };
}, [i, j, desplazar]);

// Las revisiones de una tarjeta con GRANDE: todas las filas enteras, el final del valor largo solo desplazando, la
// última fila a la vista, el aviso de los datos largos y «Aprobar» a mano
async function revisarGrande(page, v, d, i = 0) {
  d.tarjeta = await leerTarjeta(page, i);
  v.todas_las_filas = d.tarjeta.filas.length === D.filas;
  v.valores_enteros = JSON.stringify(d.tarjeta.filas) === JSON.stringify(GRANDE);
  v.se_puede_aprobar = d.tarjeta.aprobar && d.tarjeta.rechazar && !d.tarjeta.no_cabe;
  // La marca del dato largo llega en el cuadro siguiente al que se ve su recuadro
  const marcado = await page.waitForFunction((i) => document.querySelectorAll('.agente-tarjeta')[i]?.querySelector('dd[data-mas]'), i,
    { timeout: 5000 }).then(() => true, () => false);
  v.avisa_que_hay_que_desplazar = marcado && (await leerTarjeta(page, i)).aviso_largos;
  d.antes = await verFinal(page, i, 1, false);
  d.despues = await verFinal(page, i, 1, true);
  v.recuadro_con_tope_y_desplazamiento = d.antes.max !== 'none' && d.antes.desborde === 'auto' && d.antes.contenido > d.antes.alto;
  v.sombras_de_que_sigue = d.antes.sombras.includes('local') && d.antes.sombras.includes('scroll');
  v.marcado_y_con_teclado = d.antes.marcado && d.antes.teclado;
  v.final_oculto_sin_desplazar = !d.antes.se_ve;
  v.final_visible_al_desplazar = d.despues.se_ve;
  v.sin_desborde_horizontal = d.despues.ancho_ok;
  d.ultima = await verFinal(page, i, D.filas - 1, false);
  v.ultima_fila_visible = d.ultima.se_ve;
  v.las_cortas_sin_sombras = d.ultima.fondo === 'none' && !d.ultima.marcado && !d.ultima.teclado;
}

// ── En vivo: el evento `confirmar` ──
async function cVivo(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirAgente(ctx, (ruta, metodo) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      return { flujo: [inicio(51), { tipo: 'texto', texto: 'Propongo esto:' }, ...tarjeta('toolu_1', 'Agregar una nota', GRANDE), fin('confirmacion')] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') return aprobada(51, 'toolu_1');
    return null;
  });
  await ingresar(page);
  await enviar(page, 'Agrega la nota de la visita');
  await page.waitForSelector('.agente-tarjeta', espera);
  await listo(page);
  await revisarGrande(page, v, d);
  await page.screenshot({ path: `${capturas}/remate-tarjeta-vivo.png` });
  await page.locator('.agente-tarjeta .btn.primario').click();
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok', null, espera);
  await listo(page);
  v.aprobada = JSON.stringify(reg.confirmaciones) === JSON.stringify([{ conversacion: 51, decisiones: [{ id: 'toolu_1', aprobar: true }] }]);
  v.decidida_sin_aviso = !(await leerTarjeta(page)).aviso_largos;
  await ctx.close();
}

// ── Al volver a abrir la conversación: lo pendiente (en un celular angosto) ──
async function cReabrir(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso, { viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });
  const conversacion = { id: 52, titulo: 'Nota larga pendiente', proveedor: 'anthropic',
    mensajes: [{ rol: 'usuario', texto: 'Agrega la nota de la visita' }, { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'Propongo esto:' },
      { tipo: 'herramienta', id: 'toolu_9', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', estado: 'pendiente', resumen: '' }] }],
    pendientes: [{ id: 'toolu_9', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar una nota', detalle: GRANDE, aviso: null }] };
  const reg = await servirAgente(ctx, (ruta, metodo) => {
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') {
      return { json: { conversaciones: [{ id: 52, titulo: conversacion.titulo, actualizada: '2026-11-09T15:00:00+00:00', pendiente: true }] } };
    }
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones/52') return { json: conversacion };
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') return aprobada(52, 'toolu_9');
    return null;
  });
  await ingresar(page);
  await reabrir(page, conversacion.titulo);
  await page.waitForSelector('.agente-tarjeta', espera);
  await revisarGrande(page, v, d);
  await page.screenshot({ path: `${capturas}/remate-tarjeta-reabrir.png` });
  await page.locator('.agente-tarjeta .btn.primario').click();
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok', null, espera);
  await listo(page);
  v.aprobada = JSON.stringify(reg.confirmaciones) === JSON.stringify([{ conversacion: 52, decisiones: [{ id: 'toolu_9', aprobar: true }] }]);
  await ctx.close();
}

// ── Lo que no cabe: más filas en vivo (junto a otra tarjeta del mismo lote) y un valor más largo al reabrir ──
async function cNoCabe(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const MAS_FILAS = [...GRANDE, ['Una más', 'x']];
  const conversacion = { id: 56, titulo: 'Nota que no cabe', proveedor: 'anthropic', mensajes: [{ rol: 'usuario', texto: 'Agrega la nota' }],
    pendientes: [{ id: 'toolu_c', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar una nota demasiado larga',
      detalle: [['Nota', 'x'.repeat(D.valor + 1)]], aviso: null }] };
  const reg = await servirAgente(ctx, (ruta, metodo, reg) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      return { flujo: [inicio(55), { tipo: 'texto', texto: 'Propongo esto:' }, ...tarjeta('toolu_a', 'Agregar una nota', [['Nota', 'Llamar el lunes']]),
        ...tarjeta('toolu_b', 'Agregar una nota con más datos', MAS_FILAS), fin('confirmacion')] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') {
      if (reg.confirmaciones.length === 1) {
        return { flujo: [inicio(55), herr('toolu_a', 'aprobada'), herr('toolu_a', 'ok', 'Nota guardada'), herr('toolu_b', 'rechazada', 'Rechazada'),
          { tipo: 'texto', texto: 'Listo.' }, fin()] };
      }
      return { flujo: [inicio(56), herr('toolu_c', 'rechazada', 'Rechazada'), { tipo: 'texto', texto: 'Entendido.' }, fin()] };
    }
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') {
      return { json: { conversaciones: [{ id: 56, titulo: conversacion.titulo, actualizada: '2026-11-09T15:00:00+00:00', pendiente: true }] } };
    }
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones/56') return { json: conversacion };
    return null;
  });
  await ingresar(page);
  await enviar(page, 'Agrega las notas');
  await page.waitForFunction(() => document.querySelectorAll('.agente-tarjeta').length === 2, null, espera);
  await listo(page);
  d.normal = await leerTarjeta(page, 0);
  d.mas_filas = await leerTarjeta(page, 1);
  v.la_normal_se_aprueba = d.normal.aprobar;
  v.mas_filas_sin_aprobar = !d.mas_filas.aprobar && d.mas_filas.rechazar;
  v.mas_filas_lo_dice = (d.mas_filas.no_cabe || '').includes('No se puede aprobar');
  v.mas_filas_no_muestra_a_medias = d.mas_filas.filas.length === 0;
  // Se aprueba la normal y se rechaza la que no cabe: van juntas
  await page.locator('.agente-tarjeta').nth(0).locator('.btn.primario').click();
  await dormir(300);
  v.espera_la_otra = reg.confirmaciones.length === 0 && (await leerTarjeta(page, 0)).linea.includes('Falta decidir');
  await page.locator('.agente-tarjeta').nth(1).locator('.btn:not(.primario)').click();
  await page.waitForFunction(() => document.querySelectorAll('.agente-tarjeta')[1].dataset.estado === 'rechazada', null, espera);
  await listo(page);
  v.lote = JSON.stringify(reg.confirmaciones[0]) === JSON.stringify({ conversacion: 55,
    decisiones: [{ id: 'toolu_a', aprobar: true }, { id: 'toolu_b', aprobar: false }] });
  // Al reabrir, un valor de más
  await reabrir(page, conversacion.titulo);
  await page.waitForSelector('.agente-tarjeta', espera);
  d.valor_largo = await leerTarjeta(page, 0);
  v.valor_largo_sin_aprobar = !d.valor_largo.aprobar && d.valor_largo.rechazar && (d.valor_largo.no_cabe || '').includes('No se puede aprobar');
  await page.screenshot({ path: `${capturas}/remate-tarjeta-no-cabe.png` });
  await page.locator('.agente-tarjeta .btn:not(.primario)').click();
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'rechazada', null, espera);
  await listo(page);
  v.se_rechaza = JSON.stringify(reg.confirmaciones[1]) === JSON.stringify({ conversacion: 56, decisiones: [{ id: 'toolu_c', aprobar: false }] });
  await ctx.close();
}

// ── 409 `sin_pendientes`: antes del flujo y como `error` dentro de él ──
async function cSinPendientes(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const RUTA = '/api/agente/conversaciones/53';
  const chip = (id, estado, resumen = '') => ({ tipo: 'herramienta', id, nombre: 'agregar_nota', etiqueta: 'Agregando la nota', estado, resumen });
  const usuario = { rol: 'usuario', texto: 'Agrega una nota' };
  // Cómo está la conversación en el servidor después de cada decisión que llegó tarde (la atendió otra pestaña)
  const vistas = [
    { id: 53, titulo: 'Notas', proveedor: 'anthropic', mensajes: [usuario, { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'Propongo esto:' },
      chip('toolu_1', 'ok', 'Nota guardada'), { tipo: 'texto', texto: 'Y esta otra:' }, chip('toolu_2', 'pendiente')] }],
    pendientes: [{ id: 'toolu_2', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar la segunda nota', detalle: [['Nota', 'Segunda']], aviso: null }] },
    { id: 53, titulo: 'Notas', proveedor: 'anthropic', mensajes: [usuario, { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'Propongo esto:' },
      chip('toolu_1', 'ok', 'Nota guardada'), chip('toolu_2', 'ok', 'Nota guardada'), { tipo: 'texto', texto: 'Falta una:' }, chip('toolu_3', 'pendiente')] }],
    pendientes: [{ id: 'toolu_3', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar la tercera nota', detalle: [['Nota', 'Tercera']], aviso: null }] },
  ];
  const TARDE = 'Lo que decidió ya no es lo que espera su aprobación (se atendió en otra pestaña o llegó otra propuesta). Vuelva a abrir la conversación para verlo.';
  const reg = await servirAgente(ctx, (ruta, metodo, reg) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      return { flujo: [inicio(53), { tipo: 'texto', texto: 'Propongo esto:' }, ...tarjeta('toolu_1', 'Agregar la primera nota', [['Nota', 'Primera']]), fin('confirmacion')] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') {
      const n = reg.confirmaciones.length;
      if (n === 1) return { status: 409, json: { detail: { codigo: 'sin_pendientes', mensaje: TARDE } } };
      if (n === 2) return { flujo: [inicio(53), { tipo: 'error', codigo: 'sin_pendientes', mensaje: 'Otro turno atendió lo pendiente de esta conversación.' }, fin('error')] };
      return aprobada(53, 'toolu_3');
    }
    if (metodo === 'GET' && ruta === RUTA) return { json: vistas[Math.min(reg.lecturas[RUTA], vistas.length) - 1] };
    return null;
  });
  const estado = () => page.evaluate(() => ({
    tarjetas: [...document.querySelectorAll('.agente-tarjeta')].map((t) => ({ titulo: t.querySelector('h3').textContent, estado: t.dataset.estado,
      aprobar: !t.querySelector('.btn.primario').disabled })),
    notas: [...document.querySelectorAll('#agente-mensajes .agente-nota')].map((n) => n.textContent),
    errores: [...document.querySelectorAll('#agente-mensajes .agente-error')].map((n) => n.textContent),
    pendiente: !document.querySelector('#agente-nota-pendiente').hidden, sub: document.querySelector('#agente-sub').textContent }));
  await ingresar(page);
  await enviar(page, 'Agrega una nota');
  await page.waitForSelector('.agente-tarjeta', espera);
  await listo(page);
  // Espera a que se vea la tarjeta `titulo` (la de lo que quedó pendiente en el servidor); false si no llega
  const trae = (titulo) => page.waitForFunction((t) => document.querySelector('.agente-tarjeta h3')?.textContent === t, titulo,
    { timeout: 8000 }).then(() => true, () => false);
  // a) 409 antes del flujo
  await page.locator('.agente-tarjeta .btn.primario').click();
  v.a_vuelve_a_traerla = await trae('Agregar la segunda nota') && reg.lecturas[RUTA] === 1;
  d.a = await estado();
  if (!v.a_vuelve_a_traerla) { await ctx.close(); return; }
  v.a_muestra_lo_pendiente_ahora = d.a.tarjetas.length === 1 && d.a.tarjetas[0].estado === 'pendiente' && d.a.tarjetas[0].aprobar && d.a.pendiente;
  v.a_dice_por_que = d.a.notas.some((n) => n.includes('ya no estaba esperando su aprobación')) && d.a.errores.length === 0;
  // b) el mismo código en un `error` del flujo
  await page.locator('.agente-tarjeta .btn.primario').click();
  v.b_vuelve_a_traerla = await trae('Agregar la tercera nota') && reg.lecturas[RUTA] === 2;
  d.b = await estado();
  if (!v.b_vuelve_a_traerla) { await ctx.close(); return; }
  v.b_muestra_lo_pendiente_ahora = d.b.tarjetas.length === 1 && d.b.tarjetas[0].aprobar && d.b.notas.some((n) => n.includes('ya no estaba esperando'));
  // Y lo que espera ahora se aprueba
  await page.locator('.agente-tarjeta .btn.primario').click();
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok', null, espera);
  await listo(page);
  v.se_aprueba_lo_nuevo = JSON.stringify(reg.confirmaciones.map((c) => c.decisiones)) === JSON.stringify([[{ id: 'toolu_1', aprobar: true }],
    [{ id: 'toolu_2', aprobar: true }], [{ id: 'toolu_3', aprobar: true }]]);
  await ctx.close();
}

// ── El contexto de cada mensaje ──
async function cContexto(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirAgente(ctx, (ruta, metodo) => (metodo === 'POST' && ruta === '/api/agente/mensajes'
    ? { flujo: [inicio(54), { tipo: 'texto', texto: 'Hola.' }, fin()] } : null));
  await ingresar(page);
  // Un mapa «abierto» (el puente del asistente con la cámara que se le diga) y filtros sensibles en la dirección
  await page.evaluate(async () => {
    const m = await import(new URL('agente-mapa.js', document.querySelector('script[type=module]').src).href);
    window.__camara = { centro: [-73.912345, 6.987654], zoom: 16.5, base: 'auto' };
    window.__quitarMapa = m.registrarMapa({ aplicar: async () => [], estado: () => window.__camara });
    history.replaceState(history.state, '', `${location.pathname}?zona=rural&lista=7&lider=1&regimen_salud=subsidiado&ids=1,2,3`
      + '&poligono=-73.9,7.0,-73.8,7.1,-73.8,7.0&q=Ana&fuente=planilla');
  });
  await enviar(page, 'Hola de cerca');
  await listo(page);
  await page.evaluate(() => { window.__camara = { centro: [-73.912345, 6.987654], zoom: 12.34 }; });
  await enviar(page, 'Hola de lejos');
  await listo(page);
  await page.evaluate(() => window.__quitarMapa());
  d.contextos = reg.mensajes.map((m) => m.contexto);
  const [cerca, lejos] = d.contextos;
  v.solo_claves_del_servidor = JSON.stringify(cerca.filtros) === JSON.stringify({ zona: 'rural', q: 'Ana', fuente: 'planilla' });
  v.de_cerca_sin_centro = JSON.stringify(cerca.mapa) === JSON.stringify({ zoom: 16.5 });
  v.de_lejos_redondeado = JSON.stringify(lejos.mapa) === JSON.stringify({ centro: [-73.91, 6.99], zoom: 12.3 });
  await ctx.close();
}

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const casos = [];
  try {
    for (const [nombre, f] of [['vivo', cVivo], ['reabrir', cReabrir], ['no_cabe', cNoCabe], ['sin_pendientes', cSinPendientes],
      ['contexto', cContexto]]) {
      const caso = { nombre, revisiones: {}, datos: {}, errores: [], csp: [] };
      casos.push(caso);
      try {
        await f(nav, caso);
      } catch (e) {
        caso.fallo = String(e && e.stack || e).slice(0, 2000);
      }
    }
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos }));
})().catch((e) => { console.error(e); process.exit(1); });
"""
