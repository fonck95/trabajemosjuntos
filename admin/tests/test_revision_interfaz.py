"""Regresiones de la revisión de la interfaz del asistente (hallazgos 36 a 48): web/js/agente.js, app.js, vistas/mapa.js
y css/agente.css, en Chromium contra el panel de verdad (uvicorn, en /panel como en Railway) con personas inventadas.

Las rutas /api/agente/* se contestan desde el navegador (`route.fulfill`), como en test_agente_navegador.py, salvo
POST /api/agente/confirmaciones en el caso 37, que va al servidor de verdad (su 422). Lo demás (la ficha, Habitantes,
Ajustes, el mapa) es el panel real; los mapas base se contestan con un estilo y teselas falsas (aquí no hay internet).
El guion corre una vez por módulo (cada caso en su propio contexto del navegador) y cada prueba revisa el suyo.

* 36: con la ficha editada sin guardar, `navegar`, `mapa` y `presentacion` no cambian de vista (`recargar` ya no lo
  hacía): queda una nota con «Abrir de todos modos», que sí la abre.
* 37: el bucle no deja más escrituras pendientes de las que POST /confirmaciones acepta decidir juntas, y un 422 de
  /confirmaciones no se explica como un problema del texto del mensaje.
* 38: lo escrito mientras se trae una conversación del historial no se borra ni se pierde: se envía después.
* 39: con el asistente abierto sobre el mapa en un escritorio angosto, lo que muestra (`volar`, `resaltar`, un
  recorrido) queda a la vista, no debajo de su panel ni del panel izquierdo del mapa.
* 40: al terminar de cargar una vista, el foco no se va del cuadro del asistente si la persona está escribiendo ahí
  (y sigue yendo a la vista si no).
* 41: en el celular, el panel que se abre mientras carga una vista no se cierra al terminar de cargarla.
* 42: «Nueva conversación» trae escrito el mensaje tras `larga`, antes del flujo (409) o a mitad del turno (el servidor
  ya no lo termina con `fin pasos` sino con el error `larga`): no se ofrece «Continuar», que no podría funcionar.
* 43: «Detener» antes de que lleguen los rechazos de lo pendiente deja las tarjetas decidibles otra vez.
* 44: el botón flotante no tapa «Guardar cambios» de la ficha, la paginación de Habitantes ni los controles del mapa.
* 45: tras guardar el asistente en Ajustes, el widget lo sabe sin recargar (ya corregido: se deja la regresión).
* 46: con el teclado, tras aprobar, usar una sugerencia o «Continuar», el foco sigue en el panel y Escape lo cierra.
* 47: un aviso que llega antes de la primera ronda (Mnemo no respondió) no se borra si esa ronda se repite.
* 48: `***texto***` es negrita y cursiva, sin asteriscos sueltos.

Se salta si no hay Node con Playwright, salvo en el CI (allí falla en vez de pasar en silencio).
"""
import json
import os
import socket
import subprocess
import threading
import time
import uuid

import pymongo
import pytest
import uvicorn

from conftest import MONGO, URI
from test_agente_mapa import _sembrar, requiere_navegador


def _tope_decisiones() -> int:
    """Cuántas decisiones acepta POST /api/agente/confirmaciones en una sola petición (`ConfirmacionIn`)."""
    from app.api.agente import ConfirmacionIn
    return next(m.max_length for m in ConfirmacionIn.model_fields["decisiones"].metadata if hasattr(m, "max_length"))


def test_37_el_bucle_no_deja_mas_pendientes_de_las_que_se_pueden_decidir():
    """El widget manda juntas las decisiones de todo lo pendiente (el servidor rechaza lo que quede sin decidir): una
    ronda no puede dejar más escrituras pendientes de las que /confirmaciones acepta en una petición. Cada `tool_use`
    de escritura es una tarjeta y una ronda corre como mucho `MAX_HERRAMIENTAS_RONDA` herramientas."""
    from app.agente import bucle
    assert bucle.MAX_HERRAMIENTAS_RONDA <= _tope_decisiones()


@pytest.fixture(scope="module")
def resultados(tmp_path_factory):
    """El panel de verdad en un puerto libre y el guion de Chromium con todos los casos: {caso: resultado}."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    from app.config import Config
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=URI,
                 mongodb_db=f"prueba_{uuid.uuid4().hex[:10]}", horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    tmp = tmp_path_factory.mktemp("revision_interfaz")
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
        datos["persona"] = datos["resaltar"][1]["id"]
        datos["max_decisiones"] = _tope_decisiones()
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
    assert not caso.get("fallo"), (nombre, caso["fallo"])
    malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
    assert caso["revisiones"] and not malas, (nombre, malas, caso.get("datos"))
    assert caso["errores"] == [], (nombre, caso["errores"])
    assert caso["csp"] == [], (nombre, caso["csp"])
    return caso


@requiere_navegador
def test_36_navegar_y_mapa_no_pierden_los_cambios_sin_guardar(resultados):
    _revisar(resultados, "36")


@requiere_navegador
def test_37_un_422_de_las_confirmaciones_no_culpa_al_mensaje(resultados):
    _revisar(resultados, "37")


@requiere_navegador
def test_38_lo_escrito_mientras_carga_una_conversacion_no_se_pierde(resultados):
    _revisar(resultados, "38")


@requiere_navegador
def test_39_lo_que_muestra_en_el_mapa_no_queda_debajo_de_los_paneles(resultados):
    _revisar(resultados, "39")


@requiere_navegador
def test_40_render_no_le_quita_el_foco_al_asistente(resultados):
    _revisar(resultados, "40")


@requiere_navegador
def test_41_en_el_celular_el_panel_abierto_mientras_carga_no_se_cierra(resultados):
    _revisar(resultados, "41")


@requiere_navegador
def test_42_larga_trae_el_mensaje_y_no_ofrece_continuar(resultados):
    _revisar(resultados, "42")


@requiere_navegador
def test_43_detener_deja_las_tarjetas_decidibles(resultados):
    _revisar(resultados, "43")


@requiere_navegador
def test_44_el_boton_no_tapa_los_controles_de_las_vistas(resultados):
    _revisar(resultados, "44")


@requiere_navegador
def test_45_el_widget_se_entera_al_guardar_el_asistente_en_ajustes(resultados):
    _revisar(resultados, "45")


@requiere_navegador
def test_46_con_el_teclado_el_foco_sigue_en_el_panel(resultados):
    _revisar(resultados, "46")


@requiere_navegador
def test_47_un_aviso_previo_a_la_ronda_sobrevive_a_descartar(resultados):
    _revisar(resultados, "47")


@requiere_navegador
def test_48_markdown_negrita_y_cursiva_juntas(resultados):
    _revisar(resultados, "48")


GUION = r"""// Regresiones de la revisión de la interfaz del asistente, en Chromium. Uso: node <guion> <base del panel> <usuario>
// <clave> <datos.json> <capturas>
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
  mnemo: { activo: false, origen: null }, sugerencias: ['¿Cómo va la base?', 'Muéstrame el mapa.'] };
const espera = { timeout: 20000 };
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const nd = (evs) => evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
const json = (d, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(d) });
const inicio = (conversacion = 41) => ({ tipo: 'inicio', conversacion, titulo: 'Prueba' });
const fin = (motivo = 'listo') => ({ tipo: 'fin', motivo, limite: { usados: 4, maximo: 300 } });
const herr = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: 'agregar_nota', etiqueta: 'Agregando la nota', estado,
  ...(resumen ? { resumen } : {}) });
// Una escritura que espera aprobación: su chip pendiente y su tarjeta
const tarjeta = (id, titulo = 'Agregar una nota') => [herr(id, 'inicio'), herr(id, 'pendiente'),
  { tipo: 'confirmar', id, nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo, detalle: [['Nota', 'Llamar el lunes']], aviso: null }];

// ── Contexto, «servidor» del asistente y ayudas ──
// `caso` ({nombre, revisiones, datos, errores, csp}) lo crea quien corre los casos: si uno lanza, queda lo que alcanzó
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
    window.__vistas = [];
    addEventListener('vista', (e) => window.__vistas.push(e.detail.ruta));
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => caso.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text().slice(0, 300)); });
  return { ctx, page, caso, v: caso.revisiones, d: caso.datos };
}

// Contesta /api/agente/*: el estado vigente (`reg.estado`) y lo que devuelva `h(ruta, metodo, route, reg)`: {flujo},
// {json, status}, con {espera} antes, 'hecho' si ya contestó, o null (404)
async function servirAgente(ctx, h, estado = ESTADO) {
  const reg = { estado, lecturas: 0, mensajes: [], confirmaciones: [] };
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
    const req = route.request();
    const ruta = new URL(req.url()).pathname.slice(pref.length);
    const metodo = req.method();
    try {
      if (metodo === 'GET' && ruta === '/api/agente/estado') { reg.lecturas++; return await route.fulfill(json(reg.estado)); }
      if (metodo === 'POST' && ruta === '/api/agente/mensajes') reg.mensajes.push(req.postDataJSON());
      if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') reg.confirmaciones.push(req.postDataJSON());
      const r = await h(ruta, metodo, route, reg);
      if (r === 'hecho') return;
      if (!r) return await route.fulfill(json({ detail: { codigo: 'no_existe', mensaje: 'No existe.' } }, 404));
      if (r.espera) await dormir(r.espera);
      if (r.flujo) return await route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: nd(r.flujo) });
      return await route.fulfill(json(r.json, r.status || 200));
    } catch { /* la página cortó la petición («Detener») o se cerró */ }
  });
  return reg;
}

async function ingresar(page, ruta = null) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  if (ruta) await ir(page, ruta);
}

// Abre una vista con el enrutador del panel y espera a que termine de pintarse
async function ir(page, ruta) {
  const n = await page.evaluate(() => window.__vistas.length);
  await page.evaluate(async ([p, r]) => (await import(`${p}/static/js/app.js`)).ir(r), [pref, ruta]);
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
}

async function enviar(page, texto) {
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
}
const listo = (page) => page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
const ultimaRespuesta = (page) => page.evaluate(() => {
  const m = [...document.querySelectorAll('.agente-msj.agente-respuesta')].pop();
  return { textos: [...(m?.querySelectorAll('.agente-md') || [])].map((x) => x.textContent),
    notas: [...(m?.querySelectorAll('.agente-nota') || [])].map((x) => x.textContent),
    error: m?.querySelector('.agente-error')?.textContent || null,
    botones: [...(m?.querySelectorAll('button') || [])].filter((b) => !b.closest('[hidden]')).map((b) => b.textContent) };
});
// Dónde está el foco: dentro del panel del asistente, en <body> o en otra parte
const foco = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return { id: a?.id || null, tag: a?.tagName || null, texto: (a?.textContent || '').trim().slice(0, 40),
    enPanel: !!a && document.querySelector('#agente-panel').contains(a) && !a.closest('[hidden]') && !a.disabled };
});

// ── 36: cambios sin guardar en la ficha ──
async function c36(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const pedidas = [{ tipo: 'recargar' }, { tipo: 'navegar', ruta: '/reuniones' },
    { tipo: 'mapa', acciones: [{ tipo: 'volar', lat: D.casco[1], lon: D.casco[0], zoom: 15 }] },
    { tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 2 }];
  await servirAgente(ctx, (ruta, metodo, route, reg) => {
    if (metodo !== 'POST' || ruta !== '/api/agente/mensajes') return null;
    const n = reg.mensajes.length;
    const h = (estado) => ({ tipo: 'herramienta', id: `toolu_v${n}`, nombre: 'abrir_vista', etiqueta: 'Abriendo la vista', estado });
    return { flujo: [inicio(36), h('inicio'), { ...h('ok'), resumen: 'Listo' }, { tipo: 'accion', accion: pedidas[n - 1] },
      { tipo: 'texto', texto: 'Hecho.' }, fin()] };
  });
  await ingresar(page, `/personas/${D.persona}`);
  await page.waitForSelector('#f-datos', espera);
  const campo = await page.evaluate(() => [...document.querySelectorAll('#f-datos input')]
    .find((i) => !i.disabled && i.name && (i.type === 'text' || !i.getAttribute('type')))?.name);
  const ESCRITO = 'VALOR ESCRITO SIN GUARDAR';
  await page.fill(`#f-datos [name="${campo}"]`, ESCRITO);
  await page.waitForFunction(() => document.querySelector('#estado-form')?.textContent === 'Cambios sin guardar', null, espera);
  await page.click('#agente-boton');
  const ficha = `${pref}/personas/${D.persona}`;
  for (const a of pedidas) {
    const vistas = await page.evaluate(() => window.__vistas.length);
    await enviar(page, `Prueba: ${a.tipo}`);
    await listo(page);
    await dormir(1500); // lo que tardaría en cambiar la vista (o en empezar a cargar el mapa)
    const r = { ...await ultimaRespuesta(page), ...await page.evaluate((c) => ({ ruta: location.pathname, vistas: window.__vistas.length,
      valor: document.querySelector(`#f-datos [name="${c}"]`)?.value ?? null }), campo) };
    d[a.tipo] = r;
    v[`${a.tipo}_no_pierde_lo_escrito`] = r.ruta === ficha && r.valor === ESCRITO && r.vistas === vistas;
    v[`${a.tipo}_lo_explica`] = r.notas.some((n) => n.includes('cambios sin guardar'));
    if (a.tipo !== 'recargar') v[`${a.tipo}_ofrece_abrir`] = r.botones.includes('Abrir de todos modos');
  }
  // «Abrir de todos modos» (el de `navegar`) abre la vista pedida
  const n = await page.evaluate(() => window.__vistas.length);
  await page.locator('.agente-nota button', { hasText: 'Abrir de todos modos' }).first().click();
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  v.abrir_de_todos_modos = await page.evaluate(() => location.pathname) === `${pref}/reuniones`;
  await ctx.close();
}

// ── 37: un 422 de /confirmaciones (más decisiones de las que acepta) ──
async function c37(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const n = D.max_decisiones + 1;
  const estados = [];
  await servirAgente(ctx, async (ruta, metodo, route) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      const evs = [inicio(41), { tipo: 'texto', texto: `Voy a agregar ${n} notas.` }];
      for (let i = 0; i < n; i++) evs.push(...tarjeta(`toolu_${i}`, `Nota ${i + 1}`));
      return { flujo: [...evs, fin('confirmacion')] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') {
      const r = await route.fetch(); // al servidor de verdad: valida el cuerpo
      estados.push(r.status());
      await route.fulfill({ response: r });
      return 'hecho';
    }
    return null;
  });
  await ingresar(page);
  await page.click('#agente-boton');
  await enviar(page, 'Agrega la nota a todos');
  await page.waitForFunction((k) => document.querySelectorAll('.agente-tarjeta').length === k, n, espera);
  await listo(page);
  for (let i = 0; i < n; i++) await page.evaluate((j) => document.querySelectorAll('.agente-tarjeta .btn.primario')[j].click(), i);
  await page.waitForSelector('.agente-error', espera);
  await listo(page);
  d.estados = estados;
  d.error = await page.evaluate(() => document.querySelector('.agente-error')?.textContent || '');
  v.el_servidor_lo_rechaza = estados.length === 1 && estados[0] === 422;
  v.no_culpa_al_mensaje = !d.error.includes('mensaje no es válido');
  v.habla_de_las_decisiones = d.error.includes('decisiones');
  await ctx.close();
}

// ── 38: escribir mientras se trae una conversación ──
async function c38(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const CONV = { id: 41, titulo: 'Reunión del jueves', pendientes: [], mensajes: [{ rol: 'usuario', texto: 'Hola' },
    { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'Hola. ¿En qué le ayudo?' }] }] };
  const reg = await servirAgente(ctx, (ruta, metodo) => {
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') {
      return { json: { conversaciones: [{ id: 41, titulo: CONV.titulo, actualizada: '2026-11-07T15:00:00+00:00', pendiente: false }] } };
    }
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones/41') return { espera: 2500, json: CONV };
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') return { flujo: [inicio(41), { tipo: 'texto', texto: 'Respondo.' }, fin()] };
    return null;
  });
  await ingresar(page);
  await page.click('#agente-boton');
  await page.click('#agente-ver-historial');
  await page.click('.agente-item .agente-abrir');
  await page.waitForSelector('#agente-mensajes .agente-cargando', espera);
  const TEXTO = 'Mi pregunta larga, escrita mientras cargaba la conversación';
  await page.fill('#agente-texto', TEXTO);
  await page.press('#agente-texto', 'Enter');
  d.mientras = await page.evaluate(() => document.querySelector('#agente-texto').value);
  v.no_lo_borra_mientras_carga = d.mientras === TEXTO && reg.mensajes.length === 0;
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Hola. ¿En qué le ayudo?'), null, espera);
  d.tras_cargar = await page.evaluate(() => document.querySelector('#agente-texto').value);
  v.sigue_al_cargar = d.tras_cargar === TEXTO && reg.mensajes.length === 0;
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Respondo.'), null, espera);
  await listo(page);
  d.mensajes = reg.mensajes;
  v.se_envia_despues = reg.mensajes.length === 1 && reg.mensajes[0].texto === TEXTO && reg.mensajes[0].conversacion === 41;
  await ctx.close();
}

// ── 39: lo que el asistente muestra en el mapa, con su panel abierto en un escritorio angosto ──
async function c39(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso, { viewport: { width: 1400, height: 760 }, reducedMotion: 'reduce' });
  await servirAgente(ctx, () => null);
  await ingresar(page, '/mapa');
  await page.evaluate(async (p) => { window.__P = await import(`${p}/static/js/agente-mapa.js`); }, pref);
  await page.waitForFunction(() => window.__P.mapaListo(), null, { timeout: 120000, polling: 200 });
  await page.evaluate(() => window.__P.accionesMapa([{ tipo: 'capas', valores: { relieve: false, edificios: false } }]));
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])');
  // Qué hay en el punto de pantalla donde quedó [lon, lat]: el mapa (se ve), el panel del asistente o uno del mapa
  const medir = (lon, lat) => page.evaluate(([lon, lat]) => {
    const m = window.__mapa;
    const c = m.getContainer().getBoundingClientRect();
    const p = m.project([lon, lat]);
    const x = c.left + p.x, y = c.top + p.y;
    const en = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight ? document.elementFromPoint(x, y) : null;
    const tapa = !en ? 'fuera' : en.closest('#agente-panel') ? 'asistente' : en.closest('.panel-mapa') ? en.closest('.panel-mapa').id || 'panel'
      : en.closest('.maplibregl-canvas-container, canvas') ? 'visible' : en.tagName;
    return { x: Math.round(x), y: Math.round(y), tapa };
  }, [lon, lat]);
  const ok = (r) => Array.isArray(r) && r.every((x) => x.ok);
  for (const ancho of [1400, 1100, 1024]) {
    await page.setViewportSize({ width: ancho, height: 760 });
    await dormir(400);
    const B = D.barrio;
    const r1 = await page.evaluate((b) => window.__P.accionesMapa([{ tipo: 'volar', lugar: { ...b, poligono: false } }]), B);
    const volar = await medir(B.lon, B.lat);
    const p0 = D.resaltar[0];
    const r2 = await page.evaluate((pts) => window.__P.accionesMapa([{ tipo: 'resaltar', puntos: pts }]), [p0]);
    const resaltar = await medir(p0.lon, p0.lat);
    const r3 = await page.evaluate(() => window.__P.accionesMapa([{ tipo: 'recorrido', nombre: 'casco' }]));
    const casco = await medir(D.casco[0], D.casco[1]);
    d[ancho] = { volar, resaltar, casco, ok: [ok(r1), ok(r2), ok(r3)] };
    v[`acciones_ok_${ancho}`] = ok(r1) && ok(r2) && ok(r3);
    v[`volar_se_ve_${ancho}`] = volar.tapa === 'visible';
    v[`resaltar_se_ve_${ancho}`] = resaltar.tapa === 'visible';
    v[`recorrido_se_ve_${ancho}`] = casco.tapa === 'visible';
    await page.screenshot({ path: `${capturas}/revision-39-${ancho}.png` });
  }
  await ctx.close();
}

// ── 40: escribir en el asistente mientras carga otra vista (escritorio) ──
async function c40(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await servirAgente(ctx, () => null);
  let lento = false;
  await ctx.route((u) => u.pathname === pref + '/api/personas', async (route) => { if (lento) await dormir(1500); await route.fallback(); });
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])');
  lento = true;
  let n = await page.evaluate(() => window.__vistas.length);
  await page.click('#nav a[data-nav="personas"]');
  await page.click('#agente-texto');
  const FRASE = '¿Cuántas personas faltan por ubicar en el casco?';
  for (const ch of FRASE) { await page.keyboard.type(ch); await dormir(60); }
  d.vistas = await page.evaluate(() => window.__vistas.slice());
  v.la_vista_termino_mientras_escribia = d.vistas.length > n && d.vistas[d.vistas.length - 1] === '/personas';
  d.texto = await page.evaluate(() => document.querySelector('#agente-texto').value);
  d.foco = await foco(page);
  v.texto_completo = d.texto === FRASE;
  v.foco_en_el_cuadro = d.foco.id === 'agente-texto';
  // Sin escribir en el asistente, la vista nueva recibe el foco como siempre
  lento = false;
  n = await page.evaluate(() => window.__vistas.length);
  await page.click('#nav a[data-nav="reuniones"]');
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  d.foco_reuniones = await page.evaluate(() => ({ en_vista: document.querySelector('#vista').contains(document.activeElement), id: document.activeElement?.id }));
  v.foco_a_la_vista_si_no_escribe = d.foco_reuniones.en_vista;
  await ctx.close();
}

// ── 41: en el celular, abrir el asistente mientras carga otra vista ──
async function c41(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await servirAgente(ctx, () => null);
  let lento = false;
  await ctx.route((u) => u.pathname === pref + '/api/personas', async (route) => { if (lento) await dormir(2500); await route.fallback(); });
  await ingresar(page);
  const menu = async (nav) => {
    await page.tap('#abrir-menu');
    await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
    await dormir(400); // la transición del menú
    await page.tap(`#nav a[data-nav="${nav}"]`);
  };
  lento = true;
  let n = await page.evaluate(() => window.__vistas.length);
  await menu('personas');
  await dormir(300);
  await page.tap('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])');
  await page.type('#agente-texto', '¿Cuántas personas hay en el casco?');
  v.abierto_mientras_carga = await page.evaluate(() => !document.querySelector('#agente-panel').hidden);
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  await dormir(300);
  d.tras_cargar = await page.evaluate(() => ({ abierto: !document.querySelector('#agente-panel').hidden, vista: window.__vistas.slice(-1)[0],
    texto: document.querySelector('#agente-texto').value }));
  v.sigue_abierto_al_cargar = d.tras_cargar.abierto && d.tras_cargar.vista === '/personas';
  // Con el panel abierto, elegir otra vista en el menú lo pliega, como siempre
  lento = false;
  n = await page.evaluate(() => window.__vistas.length);
  await menu('reuniones');
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  await dormir(300);
  v.otra_vista_lo_pliega = await page.evaluate(() => document.querySelector('#agente-panel').hidden);
  await ctx.close();
}

// ── 42: la conversación larga ──
async function c42(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const LARGA = { codigo: 'larga', mensaje: 'La conversación es demasiado larga: empiece una nueva.' };
  const respuestas = [
    { status: 409, json: { detail: LARGA } },                                   // antes del flujo
    { flujo: [inicio(43), { tipo: 'texto', texto: 'Respondo en la nueva.' }, fin()] },
    { flujo: [inicio(43), { tipo: 'texto', texto: 'Un mom' },                   // a mitad del turno
      { tipo: 'error', codigo: 'larga', mensaje: 'La conversación ya es muy larga: empiece una nueva para seguir.' }, fin('error')] },
    { flujo: [inicio(44), { tipo: 'texto', texto: 'Sigo.' }, fin('pasos')] }, // el tope de pasos sí ofrece «Continuar»
  ];
  const reg = await servirAgente(ctx, (ruta, metodo, route, reg) => (metodo === 'POST' && ruta === '/api/agente/mensajes'
    ? respuestas[reg.mensajes.length - 1] : null));
  await ingresar(page);
  await page.click('#agente-boton');
  await enviar(page, 'Primera pregunta');
  await page.waitForSelector('.agente-error', espera);
  await listo(page);
  d.antes = await ultimaRespuesta(page);
  v.antes_ofrece_solo_nueva = JSON.stringify(d.antes.botones) === '["Nueva conversación"]';
  await page.click('.agente-error button');
  v.antes_trae_el_mensaje = await page.evaluate(() => document.querySelector('#agente-texto').value) === 'Primera pregunta';
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Respondo en la nueva.'), null, espera);
  await listo(page);
  await enviar(page, 'Segunda pregunta');
  await page.waitForSelector('.agente-error', espera);
  await listo(page);
  d.mitad = await ultimaRespuesta(page);
  v.mitad_ofrece_solo_nueva = JSON.stringify(d.mitad.botones) === '["Nueva conversación"]';
  await page.click('.agente-error button');
  d.mitad_texto = await page.evaluate(() => document.querySelector('#agente-texto').value);
  v.mitad_trae_el_mensaje = d.mitad_texto === 'Segunda pregunta';
  await enviar(page, 'Tercera');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Sigo.'), null, espera);
  await listo(page);
  d.pasos = await ultimaRespuesta(page);
  v.pasos_ofrece_continuar = d.pasos.botones.includes('Continuar');
  d.mensajes = reg.mensajes.map((m) => [m.conversacion, m.texto]);
  await ctx.close();
}

// ── 43: «Detener» con una tarjeta pendiente, antes de que lleguen sus rechazos ──
async function c43(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirAgente(ctx, (ruta, metodo, route, reg) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      if (reg.mensajes.length === 1) return { flujo: [inicio(41), { tipo: 'texto', texto: 'Propongo esto:' }, ...tarjeta('toolu_1'), fin('confirmacion')] };
      return { espera: 4000, flujo: [inicio(41), herr('toolu_1', 'rechazada', 'No aprobada'), { tipo: 'texto', texto: 'Tarde.' }, fin()] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') {
      return { flujo: [inicio(41), herr('toolu_1', 'aprobada'), herr('toolu_1', 'ok', 'Nota guardada'), { tipo: 'texto', texto: 'Listo.' }, fin()] };
    }
    return null;
  });
  await ingresar(page);
  await page.click('#agente-boton');
  await enviar(page, 'Agrega una nota');
  await page.waitForSelector('.agente-tarjeta', espera);
  await listo(page);
  const tarjetaEstado = () => page.evaluate(() => ({ aprobar: !document.querySelector('.agente-tarjeta .btn.primario').disabled,
    linea: document.querySelector('.agente-tarjeta-estado').textContent, estado: document.querySelector('.agente-tarjeta').dataset.estado,
    nota: !document.querySelector('#agente-nota-pendiente').hidden }));
  // a) Detenido antes de que el servidor responda: no llegó nada
  await enviar(page, 'Mejor otra cosa');
  await dormir(200);
  await page.click('#agente-detener');
  await listo(page);
  d.antes = await tarjetaEstado();
  v.antes_decidible = d.antes.aprobar && d.antes.estado === 'pendiente' && d.antes.nota;
  // b) Detenido con el turno ya empezado (llegó `inicio`) y sin los rechazos: puede que ya no esté pendiente
  await page.evaluate(() => {
    const original = window.fetch;
    window.fetch = (u, o = {}) => {
      if (!String(u).endsWith('/api/agente/mensajes')) return original(u, o);
      window.fetch = original;
      const t = new TextEncoder();
      return Promise.resolve(new Response(new ReadableStream({ start(c) {
        c.enqueue(t.encode(JSON.stringify({ tipo: 'inicio', conversacion: 41, titulo: 'Prueba colgada' }) + '\n'));
        o.signal?.addEventListener('abort', () => c.error(new DOMException('Detenido', 'AbortError')));
      } }), { status: 200, headers: { 'content-type': 'application/x-ndjson' } }));
    };
  });
  await enviar(page, 'Y otra más');
  await page.waitForFunction(() => document.querySelector('#agente-sub').textContent === 'Prueba colgada', null, espera);
  await dormir(200);
  await page.click('#agente-detener');
  await listo(page);
  d.despues = await tarjetaEstado();
  v.despues_decidible = d.despues.aprobar && d.despues.estado === 'pendiente' && d.despues.nota;
  v.despues_avisa_la_duda = d.despues.linea.includes('Puede que ya no esté pendiente');
  // Y se puede aprobar
  await page.click('.agente-tarjeta .btn.primario');
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok', null, espera);
  await listo(page);
  v.se_aprueba = reg.confirmaciones.length === 1 && reg.confirmaciones[0].decisiones[0].id === 'toolu_1';
  await ctx.close();
}

// ── 44: el botón flotante y lo que hay al final de cada vista ──
async function c44(nav, caso) {
  const TAMANOS = [
    { nombre: 'w1024', op: { viewport: { width: 1024, height: 700 } } },
    { nombre: 'w960', op: { viewport: { width: 960, height: 700 } } },
    { nombre: 'w1400', op: { viewport: { width: 1400, height: 900 } } },
    { nombre: 'movil', op: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
  ];
  // Los controles visibles de la vista (y los del mapa) que el botón tapa
  const tapados = (page) => page.evaluate(() => {
    const b = document.querySelector('#agente-boton');
    if (!b || b.hidden) return null;
    const r = b.getBoundingClientRect();
    const out = [];
    const sel = '#vista button, #vista a, #vista input, #vista select, #vista textarea, .maplibregl-ctrl button, .maplibregl-ctrl-attrib';
    for (const e of document.querySelectorAll(sel)) {
      const q = e.getBoundingClientRect();
      if (!q.width || !q.height || getComputedStyle(e).visibility === 'hidden' || e.closest('[hidden]')) continue;
      if (q.left < r.right && r.left < q.right && q.top < r.bottom && r.top < q.bottom) out.push(`${e.tagName.toLowerCase()} «${(e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 40)}»`);
    }
    return out;
  });
  for (const t of TAMANOS) {
    const { ctx, page } = await abrir(nav, caso, t.op);
    await servirAgente(ctx, () => null);
    await ingresar(page);
    const movil = !!t.op.isMobile;
    for (const ruta of [`/personas/${D.persona}`, '/personas', ...(movil ? [] : ['/mapa'])]) {
      await ir(page, ruta);
      if (ruta === '/mapa') {
        await page.evaluate(async (p) => { window.__P = await import(`${p}/static/js/agente-mapa.js`); }, pref);
        await page.waitForFunction(() => window.__P.mapaListo(), null, { timeout: 120000, polling: 200 });
        // La atribución desplegada (como al abrir el mapa)
        await page.evaluate(() => document.querySelector('.maplibregl-ctrl-attrib')?.classList.add('maplibregl-compact-show'));
      }
      await dormir(400);
      const clave = `${t.nombre}${ruta.startsWith('/personas/') ? '_ficha' : ruta.replace('/', '_')}`;
      // La barra «Guardar cambios» de la ficha va pegada abajo: no se tapa ni arriba ni al final
      const barra = async () => page.evaluate(() => [...document.querySelectorAll('#vista .guardar-ficha button')].some((e) => {
        const r = document.querySelector('#agente-boton').getBoundingClientRect(), q = e.getBoundingClientRect();
        return q.width && q.left < r.right && r.left < q.right && q.top < r.bottom && r.top < q.bottom;
      }));
      const barraArriba = ruta.startsWith('/personas/') ? await barra() : false;
      await page.evaluate(() => { const s = document.scrollingElement; s.scrollTop = s.scrollHeight; });
      await dormir(300);
      const abajo = await tapados(page);
      const barraAbajo = ruta.startsWith('/personas/') ? await barra() : false;
      caso.datos[clave] = { abajo, barraArriba, barraAbajo };
      caso.revisiones[`nada_tapado_${clave}`] = Array.isArray(abajo) && abajo.length === 0 && !barraArriba && !barraAbajo;
      await page.screenshot({ path: `${capturas}/revision-44-${clave}.png` });
    }
    await ctx.close();
  }
}

// ── 45: encender el asistente para su rol en Ajustes ──
async function c45(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirAgente(ctx, () => null, { ...ESTADO, disponible: false, motivo: 'rol' });
  // Al guardar los ajustes de verdad (PUT /api/ajustes), el estado pasa a encendido
  await ctx.route((u) => u.pathname === pref + '/api/ajustes', async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback();
    const r = await route.fetch();
    if (r.ok()) reg.estado = ESTADO;
    return route.fulfill({ response: r });
  });
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('.agente-explicacion', espera);
  v.explica_que_esta_apagado = (await page.textContent('.agente-explicacion')).includes('apagado para su rol');
  // El enlace de la explicación lleva a Ajustes; ahí se guarda la sección del asistente
  await page.click('.agente-explicacion a[data-ruta]');
  await page.waitForSelector('#f-agente button.primario', espera);
  const lecturas = reg.lecturas;
  await page.click('#f-agente button.primario');
  await page.waitForFunction(() => document.querySelector('#avisos')?.textContent.includes('Asistente guardado'), null, espera);
  await ir(page, '/personas');
  if (await page.evaluate(() => document.querySelector('#agente-panel').hidden)) await page.click('#agente-boton');
  await page.waitForSelector('.agente-bienvenida', espera);
  d.lecturas = [lecturas, reg.lecturas];
  v.relee_el_estado = reg.lecturas > lecturas;
  v.ya_se_puede_escribir = await page.evaluate(() => !document.querySelector('#agente-form').hidden && !document.querySelector('.agente-explicacion'));
  await ctx.close();
}

// ── 46: solo con el teclado ──
async function c46(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await servirAgente(ctx, (ruta, metodo, route, reg) => {
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      const n = reg.mensajes.length;
      if (n === 1) return { flujo: [inicio(41), { tipo: 'texto', texto: 'Propongo esto:' }, ...tarjeta('toolu_1'), fin('confirmacion')] };
      if (n === 2) return { flujo: [inicio(41), { tipo: 'texto', texto: 'Voy por partes.' }, fin('pasos')] };
      return { flujo: [inicio(41), { tipo: 'texto', texto: 'Sigo donde quedé.' }, fin()] };
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') {
      return { espera: 300, flujo: [inicio(41), herr('toolu_1', 'aprobada'), herr('toolu_1', 'ok', 'Nota guardada'), { tipo: 'texto', texto: 'Listo.' }, fin()] };
    }
    return null;
  });
  await ingresar(page);
  const abrirConTeclado = async () => {
    if (await page.evaluate(() => !document.querySelector('#agente-panel').hidden)) await page.click('#agente-cerrar');
    await page.focus('#agente-boton');
    await page.keyboard.press('Enter');
    await page.waitForSelector('#agente-panel:not([hidden])');
  };
  const escapeCierra = async () => {
    await page.keyboard.press('Escape');
    return page.evaluate(() => document.querySelector('#agente-panel').hidden);
  };
  await abrirConTeclado();
  // Una sugerencia, con Enter
  await page.focus('.agente-sugerencia');
  await page.keyboard.press('Enter');
  await page.waitForSelector('.agente-tarjeta', espera);
  await listo(page);
  d.tras_sugerencia = await foco(page);
  v.foco_tras_sugerencia = d.tras_sugerencia.enPanel;
  // Aprobar con Enter
  await page.focus('.agente-tarjeta .btn.primario');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok', null, espera);
  await listo(page);
  await dormir(200);
  d.tras_aprobar = await foco(page);
  v.foco_tras_aprobar = d.tras_aprobar.enPanel;
  v.escape_tras_aprobar = await escapeCierra();
  // «Continuar», con Enter
  await abrirConTeclado();
  await page.keyboard.type('Haz todo');
  await page.keyboard.press('Enter');
  await page.waitForSelector('.agente-nota button', espera);
  await listo(page);
  await page.focus('.agente-nota button');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Sigo donde quedé.'), null, espera);
  await listo(page);
  d.tras_continuar = await foco(page);
  v.foco_tras_continuar = d.tras_continuar.enPanel;
  v.escape_tras_continuar = await escapeCierra();
  await ctx.close();
}

// ── 47: un aviso de antes de la primera ronda y `descartar` ──
async function c47(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const MNEMO = 'Mnemo no respondió: esta conversación sigue sin sus herramientas.';
  const RESPALDO = 'El modelo pasó a uno de respaldo.';
  await servirAgente(ctx, (ruta, metodo, route, reg) => {
    if (metodo !== 'POST' || ruta !== '/api/agente/mensajes') return null;
    if (reg.mensajes.length === 1) {
      return { flujo: [inicio(47), { tipo: 'aviso', nivel: 'alerta', texto: MNEMO }, { tipo: 'texto', texto: 'Esto se repite' }, { tipo: 'descartar' },
        { tipo: 'texto', texto: 'Respuesta completa.' }, fin()] };
    }
    // Un aviso de dentro de la ronda (el modelo de respaldo) sí se va con ella: la ronda repetida lo vuelve a mandar
    return { flujo: [inicio(47), { tipo: 'texto', texto: 'Parte' }, { tipo: 'aviso', nivel: 'info', texto: RESPALDO }, { tipo: 'descartar' },
      { tipo: 'aviso', nivel: 'info', texto: RESPALDO }, { tipo: 'texto', texto: 'Otra completa.' }, fin()] };
  });
  await ingresar(page);
  await page.click('#agente-boton');
  await enviar(page, 'Hola');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Respuesta completa.'), null, espera);
  await listo(page);
  d.primera = await ultimaRespuesta(page);
  v.aviso_previo_sigue = d.primera.notas.includes(MNEMO);
  v.lo_descartado_se_va = JSON.stringify(d.primera.textos) === '["Respuesta completa."]';
  await enviar(page, 'Otra');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].some((x) => x.textContent === 'Otra completa.'), null, espera);
  await listo(page);
  d.segunda = await ultimaRespuesta(page);
  v.aviso_de_la_ronda_una_vez = d.segunda.notas.filter((n) => n === RESPALDO).length === 1
    && JSON.stringify(d.segunda.textos) === '["Otra completa."]';
  await ctx.close();
}

// ── 48: Markdown con tres marcas ──
async function c48(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await servirAgente(ctx, (ruta, metodo) => (metodo === 'POST' && ruta === '/api/agente/mensajes' ? { flujo: [inicio(48),
    { tipo: 'texto', texto: 'Esto es ***muy importante*** para hoy. Y ___esto también___.\n\nNormal **negrita**, *cursiva* y ~~tachado~~.' }, fin()] } : null));
  await ingresar(page);
  await page.click('#agente-boton');
  await enviar(page, 'Hola');
  await page.waitForSelector('.agente-md p', espera);
  await listo(page);
  d.html = await page.evaluate(() => [...document.querySelectorAll('.agente-md p')].map((p) => p.innerHTML));
  v.tres_marcas = d.html[0] === 'Esto es <em><strong>muy importante</strong></em> para hoy. Y <em><strong>esto también</strong></em>.';
  v.lo_demas_igual = d.html[1] === 'Normal <strong>negrita</strong>, <em>cursiva</em> y <s>tachado</s>.';
  await ctx.close();
}

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const casos = [];
  try {
    for (const f of [c36, c37, c38, c39, c40, c41, c42, c43, c44, c45, c46, c47, c48]) {
      const caso = { nombre: f.name.slice(1), revisiones: {}, datos: {}, errores: [], csp: [] };
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
