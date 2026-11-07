"""El asistente del panel en un navegador de verdad (Chromium con Playwright): escritorio (1400 × 900), celular
(390 × 844, táctil) y celular chico (320 × 568). Datos inventados; nunca se llama a Anthropic ni a Mnemo.

* `test_widget_sigue_el_protocolo`: las rutas /api/agente/* se contestan desde el navegador (`route.fulfill`) con un
  turno que trae cada tipo de evento (inicio, progreso, texto con Markdown, enlaces permitidos y no permitidos, un
  `<img onerror>`, herramienta, descartar, latido, una línea rota, un evento desconocido, navegar a una ruta del panel
  y a otra que no es, confirmar y fin). Se revisa lo pintado, la aprobación (POST /confirmaciones con la decisión),
  recargar e insignias, el contexto que se manda, el historial (abrir y borrar), Escape y el foco, Mayús+Enter,
  «Reintentar» tras un 503 (reusa la burbuja), la sesión vencida (el diálogo de ingreso del panel y el reintento solo),
  lo guardado en la pestaña (y que vuelve al recargar) y que cerrar sesión lo borra. En el celular: que se pliega al
  navegar, que el botón no tapa la barra de la ficha ni el título de la barra y que «Cerrar sesión» se alcanza con el
  menú abierto. El administrador sin ANTHROPIC_API_KEY ve qué variable falta. En todos: sin XSS, sin errores de
  consola, sin violaciones de CSP, sin desborde horizontal y el panel dentro de la ventana.
* `test_flujo_real_por_partes_y_detener`: contra el núcleo de verdad (uvicorn, el panel en /panel y la Messages API
  simulada con pausas): el texto llega y se pinta por partes (el primer párrafo conserva su nodo mientras llega el
  resto), «Detener» corta el turno y el siguiente mensaje funciona (el servidor soltó el candado).

Corre con uvicorn de verdad (el TestClient junta toda la respuesta) y un guion de Node, como test_servidor.py. Se
salta si no hay Node con Playwright, salvo en el CI (allí falla en vez de pasar en silencio).
"""
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pymongo
import pytest
import uvicorn

from conftest import MONGO, URI, insertar_personas, personas_inventadas


def _hay_playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(
        ["node", "-e", "require(process.env.PLAYWRIGHT_MODULE || 'playwright')"], capture_output=True).returncode == 0


requiere_navegador = pytest.mark.skipif(not _hay_playwright() and not os.environ.get("CI"),
                                        reason="Sin Node con Playwright (PLAYWRIGHT_MODULE o NODE_PATH)")


@pytest.fixture
def panel_vivo(cfg, tmp_path):
    """El servidor único de verdad (uvicorn h11, el panel en /panel, como en Railway) en un puerto libre, con tres
    personas inventadas. Devuelve (base del panel, app del panel, ids de las personas)."""
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
        while time.time() < fin and not (srv.started and app.state.panel is not None and app.state.panel.state.listo):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        ids = insertar_personas(app.state.panel.state.db, personas_inventadas(3, semilla=41))
        yield f"http://127.0.0.1:{sock.getsockname()[1]}/panel", app.state.panel, ids
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def _correr(guion: str, tmp_path, *args: str) -> dict:
    (tmp_path / "agente.cjs").write_text(guion, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)  # para mirarlas a mano
    r = subprocess.run(["node", str(tmp_path / "agente.cjs"), *args, capturas], capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    if os.environ.get("CAPTURAS_AGENTE"):
        (Path(capturas) / f"resultado-{args[3]}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                                   encoding="utf-8")
    return res


def _revisar(caso: dict) -> None:
    malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
    assert not malas, (caso["nombre"], malas, caso.get("datos"))
    assert caso["errores"] == [], (caso["nombre"], caso["errores"])
    assert caso["csp"] == [], (caso["nombre"], caso["csp"])


@requiere_navegador
def test_widget_sigue_el_protocolo(panel_vivo, cfg, tmp_path):
    base, _, ids = panel_vivo
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "protocolo", str(ids[1]))
    assert [c["nombre"] for c in res["casos"]] == ["escritorio", "movil", "chico", "sin_clave"]
    for caso in res["casos"]:
        _revisar(caso)
        if caso["nombre"] == "sin_clave":
            continue
        # Lo que el navegador le mandó al servidor
        primero, segundo = caso["mensajes"][:2]
        assert len(caso["mensajes"]) == (6 if caso["nombre"] == "escritorio" else 2)  # + reintento y reingreso
        assert primero["cuerpo"]["conversacion"] is None and primero["cuerpo"]["texto"] == TEXTO_XSS
        assert primero["cuerpo"]["contexto"]["ruta"] == "/" and primero["cuerpo"]["contexto"]["vista"] == "panel"
        assert primero["csrf"], "el flujo manda el token CSRF"
        assert segundo["cuerpo"]["conversacion"] == 41
        ctx = segundo["cuerpo"]["contexto"]
        assert ctx["ruta"] == "/personas" and ctx["vista"] == "personas" and ctx["filtros"]["zona"] == "rural", ctx
        assert caso["confirmaciones"] == [{"conversacion": 41, "decisiones": [{"id": "toolu_2", "aprobar": True}]}]


@requiere_navegador
def test_flujo_real_por_partes_y_detener(panel_vivo, cfg, tmp_path, monkeypatch):
    from ayudas_agente import T, con_herramientas, encender_lento, herramientas_falsas, sse
    base, panel, ids = panel_vivo
    con_herramientas(monkeypatch, herramientas_falsas()[0])
    encender_lento(panel,
                   sse(T("Primer párrafo de la respuesta."), T("\n\nSegundo párrafo, que llega después."),
                       T(" Y un final.")),
                   sse(*[T(f"Parte {i}. ") for i in range(30)]),
                   sse(T("De nada.")), pausa=0.15)
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "real", str(ids[1]))
    (caso,) = res["casos"]
    _revisar(caso)
    d = caso["datos"]
    assert d["respuesta"] == "Primer párrafo de la respuesta.\n\nSegundo párrafo, que llega después. Y un final."
    # Por partes: el primer texto se ve mucho antes del final, y el primer párrafo no se rehízo al llegar el resto
    assert d["primero_ms"] < d["total_ms"] - 600, d


TEXTO_XSS = '<img src=x onerror="window.__xss=1"> ¿Quiénes viven en Tres de Octubre?'

GUION = r"""// El asistente del panel en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> <modo> <persona> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, modo, persona, capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const TEXTO_XSS = '<img src=x onerror="window.__xss=1"> ¿Quiénes viven en Tres de Octubre?';
const CASOS = {
  protocolo: [
    { nombre: 'escritorio', viewport: { width: 1400, height: 900 } },
    { nombre: 'movil', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    { nombre: 'chico', viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    // El administrador sin ANTHROPIC_API_KEY ve el botón, y adentro qué variable falta
    { nombre: 'sin_clave', viewport: { width: 1280, height: 800 }, estado: { disponible: false, motivo: 'sin_configurar', configurado: false,
      es_admin: true, escritura: true, limite: { usados: 0, maximo: 300 }, mnemo: { activo: false, origen: null }, sugerencias: [] } },
  ],
  real: [{ nombre: 'real', viewport: { width: 1280, height: 800 } }],
}[modo];

// ── Lo que contesta el «servidor» en el modo protocolo ──
const ESTADO = {
  disponible: true, motivo: null, configurado: true, es_admin: true, escritura: true, limite: { usados: 3, maximo: 300 },
  mnemo: { activo: true, origen: 'https://mnemo.example.org' },
  sugerencias: ['¿Cómo va la base? Dame los indicadores principales.', 'Muéstrame en el mapa a las personas que faltan por ubicar.'],
};
const H = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: id === 'toolu_1' ? 'buscar_personas' : 'agregar_nota',
  etiqueta: id === 'toolu_1' ? 'Buscando habitantes' : 'Agregando la nota', estado, ...(resumen ? { resumen } : {}) });
const TURNO_1 = [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  { tipo: 'progreso', texto: 'Lo que pinta una ronda ' }, { tipo: 'texto', texto: 'Esto se descarta.' }, { tipo: 'descartar' },
  { tipo: 'progreso', texto: 'Busco a las personas ' }, { tipo: 'progreso', texto: 'del barrio.' },
  H('toolu_1', 'inicio'), { tipo: 'latido' }, H('toolu_1', 'ok', '2 personas'),
  { tipo: 'accion', accion: { tipo: 'navegar', ruta: '/personas?zona=rural' } },
  { tipo: 'accion', accion: { tipo: 'navegar', ruta: 'https://malo.example/robar' } },
  'esto no es JSON', { tipo: 'futuro', dato: 1 },
  { tipo: 'texto', texto: 'Encontré **dos personas impor' },
  { tipo: 'texto', texto: 'tantes** en Tres de Octubre:\n\n- [Ana Inventada](/personas/1)\n- Beto <img src=x onerror="window.__xss=1"> Inventado\n\n' },
  { tipo: 'texto', texto: '| Barrio | Personas |\n|---|---:|\n| Tres de Octubre | 1.234 |\n\n' },
  { tipo: 'texto', texto: 'Más en [aquí](https://malo.example/robar), [esto](javascript:alert(1)) o [Aprobar en Mnemo](https://mnemo.example.org/aprobar/abc). Use `buscar_personas`.' },
  H('toolu_2', 'inicio'), H('toolu_2', 'pendiente'),
  { tipo: 'confirmar', id: 'toolu_2', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar una nota',
    detalle: [['Persona', 'Ana Inventada (#1)'], ['Nota', 'Llamar el lunes <b>sin falta</b>']], aviso: 'Queda en la ficha y la ve el equipo.' },
  { tipo: 'fin', motivo: 'confirmacion', limite: { usados: 4, maximo: 300 } },
];
const TURNO_CONFIRMAR = [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  H('toolu_2', 'aprobada'), H('toolu_2', 'ok', 'Nota guardada'),
  { tipo: 'accion', accion: { tipo: 'recargar' } }, { tipo: 'accion', accion: { tipo: 'insignias' } },
  { tipo: 'texto', texto: 'Listo: la nota quedó en la ficha.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } },
];
const corto = (texto, usados) => [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  { tipo: 'texto', texto }, { tipo: 'fin', motivo: 'listo', limite: { usados, maximo: 300 } },
];
// Lo que contesta POST /mensajes, en orden: un error antes del flujo es {estado, detail}
const MENSAJES = [
  TURNO_1, corto('Claro que sí.', 5),
  { estado: 503, detail: { codigo: 'saturado', mensaje: 'El asistente está atendiendo muchas conversaciones a la vez. Intente de nuevo en unos segundos.' } },
  corto('Ahora sí.', 6),
  { estado: 401, detail: 'Inicie sesión' },
  corto('Sesión renovada.', 7),
];
const LISTA = { conversaciones: [
  { id: 41, titulo: '¿Quiénes viven en Tres de Octubre?', actualizada: '2026-11-07T15:00:00+00:00', pendiente: false },
  { id: 7, titulo: 'Reunión <b>inventada</b>', actualizada: '2026-11-01T10:00:00+00:00', pendiente: true },
] };
const CONV = {
  41: { id: 41, titulo: '¿Quiénes viven en Tres de Octubre?', pendientes: [], mensajes: [
    { rol: 'usuario', texto: '¿Quiénes viven en Tres de Octubre?' },
    { rol: 'asistente', partes: [{ tipo: 'progreso', texto: 'Busco.' }, H('toolu_1', 'ok', '2 personas'), { tipo: 'texto', texto: 'Encontré **dos**.' }] },
  ] },
  7: { id: 7, titulo: 'Reunión <b>inventada</b>', mensajes: [
    { rol: 'usuario', texto: 'Prepara la reunión' },
    { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'La reunión tiene *12* asistentes.' }, { tipo: 'aviso', texto: 'Mnemo no respondió.', nivel: 'alerta' }] },
  ], pendientes: [{ id: 'toolu_9', nombre: 'crear_reunion', etiqueta: 'Creando la reunión', titulo: 'Crear la reunión', detalle: [['Fecha', '2026-11-20']], aviso: null }] },
};
const nd = (evs) => evs.map((e) => (typeof e === 'string' ? e : JSON.stringify(e))).join('\n') + '\n';

async function servirAgente(ctx, reg, estado = ESTADO) {
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
    const req = route.request();
    const ruta = new URL(req.url()).pathname.slice(pref.length);
    const metodo = req.method();
    const json = (d, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(d) });
    const flujo = (evs) => route.fulfill({ status: 200, contentType: 'application/x-ndjson', headers: { 'cache-control': 'no-store' }, body: nd(evs) });
    if (metodo === 'GET' && ruta === '/api/agente/estado') return json(estado);
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') return json(LISTA);
    const c = /^\/api\/agente\/conversaciones\/(\d+)$/.exec(ruta);
    if (c && metodo === 'GET') return json(CONV[c[1]] || { detail: { codigo: 'no_existe', mensaje: 'No existe esa conversación.' } }, CONV[c[1]] ? 200 : 404);
    if (c && metodo === 'DELETE') { reg.borradas.push(+c[1]); return json({ ok: true }); }
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      reg.mensajes.push({ cuerpo: req.postDataJSON(), csrf: req.headers()['x-csrf-token'] || '' });
      const r = MENSAJES[reg.mensajes.length - 1];
      // Los errores a propósito llevan una marca para no contarlos como errores de la página
      if (!Array.isArray(r)) return route.fulfill({ status: r.estado, contentType: 'application/json', headers: { 'x-prueba': 'esperado' }, body: JSON.stringify({ detail: r.detail }) });
      return flujo(r);
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') { reg.confirmaciones.push(req.postDataJSON()); return flujo(TURNO_CONFIRMAR); }
    return json({ detail: 'No existe' }, 404);
  });
}

// ── Ayudas ──
const espera = { timeout: 15000 };
async function geometria(page, caso, cuando) {
  // Se mide sin la animación de entrada del panel (se desliza unos píxeles al abrirse)
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect?.getComputedTiming().iterations === Infinity));
  const g = await page.evaluate(() => {
    const caja = (s) => { const e = document.querySelector(s); if (!e || e.hidden || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, d: r.right, a: r.bottom }; };
    const dentro = (r) => !!r && r.x >= -0.5 && r.y >= -0.5 && r.d <= innerWidth + 0.5 && r.a <= innerHeight + 0.5;
    const log = document.querySelector('#agente-mensajes');
    return { boton: caja('#agente-boton'), panel: caja('#agente-panel'), panelDentro: dentro(caja('#agente-panel')),
      botonDentro: dentro(caja('#agente-boton')), desborde: document.documentElement.scrollWidth > innerWidth,
      desbordeLog: !!log && log.scrollWidth > log.clientWidth + 1, ventana: [innerWidth, innerHeight],
      ancho: document.documentElement.scrollWidth, anchos: [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 0.5 && getComputedStyle(e).position !== 'fixed').slice(0, 5).map((e) => `${e.tagName}.${e.className}#${e.id} ${Math.round(e.getBoundingClientRect().right)}`) };
  });
  // En el celular un contenido más ancho que la pantalla no da barra de desplazamiento: el navegador agranda la ventana
  // de diseño (innerWidth) para que quepa. Se compara con el ancho pedido
  g.desborde ||= g.ventana[0] !== page.viewportSize().width;
  caso.geo = caso.geo || {};
  caso.geo[cuando] = g;
  return g;
}
const cruzan = (a, b) => !!a && !!b && a.x < b.d && b.x < a.d && a.y < b.a && b.y < a.a;

async function salirAlcanzable(page, tocar) {
  await tocar('#abrir-menu');
  await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
  await page.waitForTimeout(400); // la transición del menú (.25 s)
  await page.locator('#salir').scrollIntoViewIfNeeded(); // en una pantalla baja el menú se desplaza solo él
  const ok = await page.evaluate(() => {
    const s = document.querySelector('#salir');
    const r = s.getBoundingClientRect();
    const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return r.top >= 0 && r.bottom <= innerHeight && r.right <= innerWidth && !!e && s.contains(e);
  });
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#app').classList.contains('menu-abierto'));
  return ok;
}

async function ingresar(page) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
}

async function enviar(page, texto) {
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
}

const listo = (page) => page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

async function protocolo(page, op, caso) {
  const v = caso.revisiones;
  const movil = !!op.isMobile;
  const tocar = (s) => (op.hasTouch ? page.tap(s) : page.click(s));
  await ingresar(page);
  let g = await geometria(page, caso, 'inicio');
  v.boton_visible = g.botonDentro;
  // En el mapa (render() pone #vista.lleno): en el celular el botón va a la barra de arriba, a la derecha y sin tapar
  // el título; en escritorio, a la izquierda de los controles de MapLibre (abajo a la derecha, 39 px de ancho)
  const enMapa = await page.evaluate(() => {
    const vista = document.querySelector('#vista');
    vista.classList.add('lleno');
    const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top, d: b.right, a: b.bottom }; };
    const out = { boton: r('#agente-boton'), titulo: r('.barra-movil b'), ancho: innerWidth, alto: innerHeight };
    vista.classList.remove('lleno');
    return out;
  });
  caso.geo.mapa = enMapa;
  v.boton_en_el_mapa = movil ? enMapa.boton.a <= 60 && enMapa.boton.d <= enMapa.ancho && enMapa.ancho - enMapa.boton.d < 20 && !cruzan(enMapa.boton, enMapa.titulo)
    : enMapa.boton.d <= enMapa.ancho - 60 && enMapa.boton.a > enMapa.alto - 100;
  if (movil) v.salir_con_el_menu = await salirAlcanzable(page, tocar);

  await tocar('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])');
  v.boton_oculto_con_el_panel = await page.evaluate(() => document.querySelector('#agente-boton').hidden
    && document.querySelector('#agente-boton').getAttribute('aria-expanded') === 'true');
  if (!movil) v.foco_en_el_cuadro = await page.evaluate(() => document.activeElement?.id === 'agente-texto');
  await page.waitForSelector('.agente-sugerencia');
  v.bienvenida = await page.evaluate(() => document.querySelectorAll('.agente-sugerencia').length === 2
    && document.querySelector('#agente-restantes').textContent === 'Le quedan 297 mensajes hoy'
    && document.querySelector('#agente-mensajes').getAttribute('role') === 'log'
    && document.querySelector('#agente-mensajes').getAttribute('aria-live') === 'polite');
  g = await geometria(page, caso, 'abierto');
  v.panel_dentro = g.panelDentro && !g.desborde;
  if (movil) v.salir_con_el_panel_abierto = await salirAlcanzable(page, tocar);
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-bienvenida.png` });

  // ── El turno con todos los eventos ──
  await enviar(page, TEXTO_XSS);
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta') && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  await page.waitForFunction(() => (window.__vistas || []).includes('/personas'), null, espera);
  await page.waitForTimeout(150);
  const d = await page.evaluate(() => {
    const msjs = [...document.querySelectorAll('.agente-msj.agente-respuesta')];
    const a = msjs[msjs.length - 1];
    const enlaces = [...a.querySelectorAll('a')].map((x) => ({ texto: x.textContent, href: x.getAttribute('href'), ruta: x.hasAttribute('data-ruta'), target: x.target, rel: x.rel }));
    const chip = (id) => [...document.querySelectorAll('.agente-herr')].find((c) => c.textContent.includes(id === 1 ? 'Buscando' : 'Agregando'));
    const t = document.querySelector('.agente-tarjeta');
    return {
      usuario: document.querySelector('.agente-msj.agente-persona p').textContent,
      texto: a.querySelector('.agente-md').textContent, html: a.querySelector('.agente-md').innerHTML,
      negrita: [...a.querySelectorAll('strong')].map((x) => x.textContent), items: a.querySelectorAll('.agente-md li').length,
      tabla: [...a.querySelectorAll('.md-tabla th, .md-tabla td')].map((x) => x.textContent), der: !!a.querySelector('.md-tabla td.der'),
      codigo: [...a.querySelectorAll('.agente-md code')].map((x) => x.textContent), enlaces,
      progreso: a.querySelector('.agente-progreso')?.textContent, progresos: [...document.querySelectorAll('.agente-progreso')].map((x) => x.textContent), notas: [...a.querySelectorAll('.agente-nota')].map((x) => x.textContent),
      chip1: chip(1)?.dataset.estado + '|' + chip(1)?.textContent, chip2: chip(2)?.dataset.estado,
      tarjeta: t && { titulo: t.querySelector('h3').textContent, dt: [...t.querySelectorAll('dt')].map((x) => x.textContent), dd: [...t.querySelectorAll('dd')].map((x) => x.textContent), aviso: t.querySelector('.agente-tarjeta-aviso')?.textContent, botones: [...t.querySelectorAll('button')].map((x) => x.textContent) },
      imgs: document.querySelectorAll('#agente-panel img, #agente-panel [onerror]').length, xss: window.__xss === undefined,
      ruta: location.pathname + location.search, restantes: document.querySelector('#agente-restantes').textContent,
      guardado: sessionStorage.getItem('yj_agente'), local: Object.keys(localStorage), abierto: !document.querySelector('#agente-panel').hidden,
      senal: document.querySelector('#agente-boton').dataset.senal, foco: document.activeElement?.id, sub: document.querySelector('#agente-sub').textContent,
      notaPendiente: !document.querySelector('#agente-nota-pendiente').hidden,
    };
  });
  caso.datos = d;
  v.texto_del_usuario_como_texto = d.usuario === TEXTO_XSS;
  v.sin_xss = d.imgs === 0 && d.xss && !d.html.includes('<img') && d.texto.includes('<img src=x onerror="window.__xss=1">');
  v.descartado = !d.texto.includes('Esto se descarta') && !d.progresos.some((p) => p.includes('Lo que pinta'));
  v.markdown = d.negrita.includes('dos personas importantes') && d.items === 2 && d.der && d.codigo.includes('buscar_personas')
    && JSON.stringify(d.tabla) === JSON.stringify(['Barrio', 'Personas', 'Tres de Octubre', '1.234']);
  v.enlace_interno = d.enlaces.some((e) => e.texto === 'Ana Inventada' && e.href === pref + '/personas/1' && e.ruta && !e.target);
  v.enlace_mnemo = d.enlaces.some((e) => e.texto === 'Aprobar en Mnemo' && e.href === 'https://mnemo.example.org/aprobar/abc' && e.target === '_blank' && e.rel === 'noopener noreferrer');
  v.enlaces_no_permitidos_como_texto = d.enlaces.length === 2 && d.texto.includes('Más en aquí, esto o') && !d.html.includes('malo.example') && !d.html.includes('javascript');
  v.progreso = d.progreso === 'Busco a las personas del barrio.';
  v.chips = d.chip1.startsWith('ok|') && d.chip1.includes('Buscando habitantes · 2 personas') && d.chip2 === 'pendiente';
  v.tarjeta = !!d.tarjeta && d.tarjeta.titulo === 'Agregar una nota' && JSON.stringify(d.tarjeta.dt) === '["Persona","Nota"]'
    && d.tarjeta.dd[1] === 'Llamar el lunes <b>sin falta</b>' && d.tarjeta.aviso === 'Queda en la ficha y la ve el equipo.'
    && JSON.stringify(d.tarjeta.botones) === '["Aprobar","Rechazar"]' && d.notaPendiente;
  v.navego = d.ruta.startsWith(pref + '/personas?zona=rural'); // la vista agrega su orden a la URL
  v.navegar_fuera_rechazado = d.notas.some((n) => n.includes('no es una vista del panel'));
  v.restantes = d.restantes === 'Le quedan 296 mensajes hoy';
  v.titulo = d.sub === '¿Quiénes viven en Tres de Octubre?';
  v.guardado_en_la_pestana = JSON.parse(d.guardado || '{}').conversacion === 41 && d.local.every((k) => k === 'tema');
  if (movil) {
    // En el celular se plegó al navegar: el botón avisa que hay algo esperando su aprobación
    v.plegado_al_navegar = !d.abierto && d.senal === 'pendiente';
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-plegado.png` });
    await tocar('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])');
  } else {
    v.foco_vuelve_tras_navegar = d.abierto && d.foco === 'agente-texto';
  }
  g = await geometria(page, caso, 'respuesta');
  v.sin_desborde_con_la_respuesta = !g.desborde && !g.desbordeLog && g.panelDentro;
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-respuesta.png` });

  // ── Aprobar ──
  const vistas = await page.evaluate(() => window.__vistas.length);
  const insignias = caso.insignias;
  await page.locator('.agente-tarjeta .btn.primario').scrollIntoViewIfNeeded();
  await tocar('.agente-tarjeta .btn.primario');
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  await page.waitForFunction((n) => window.__vistas.length > n, vistas, espera);
  await page.waitForTimeout(150);
  const c = await page.evaluate(() => ({ estado: document.querySelector('.agente-tarjeta-estado').textContent,
    botones: document.querySelector('.agente-tarjeta-botones').hidden, chip: [...document.querySelectorAll('.agente-herr')].find((x) => x.textContent.includes('Agregando'))?.dataset.estado,
    final: [...document.querySelectorAll('.agente-msj.agente-respuesta .agente-md')].pop().textContent, abierto: !document.querySelector('#agente-panel').hidden,
    ruta: location.pathname + location.search, notaPendiente: !document.querySelector('#agente-nota-pendiente').hidden }));
  v.aprobada = c.estado === 'Hecho · Nota guardada' && c.botones && c.chip === 'ok' && c.final === 'Listo: la nota quedó en la ficha.' && !c.notaPendiente;
  v.recargo_sin_plegarse = c.abierto && c.ruta.startsWith(pref + '/personas?zona=rural');
  v.insignias = caso.insignias > insignias;

  // ── Otro mensaje en la misma conversación ──
  await enviar(page, '¿Y cuántas faltan por ubicar?');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Claro que sí.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

  if (!movil) {
    // Mayús+Enter es otra línea (no envía)
    await page.fill('#agente-texto', 'uno');
    await page.press('#agente-texto', 'Shift+Enter');
    await page.type('#agente-texto', 'dos');
    v.mayus_enter = await page.evaluate(() => document.querySelector('#agente-texto').value === 'uno\ndos') && caso.mensajes.length === 2;
    // Un error antes del flujo (503): la burbuja queda «No se envió» y «Reintentar» la reusa
    await enviar(page, 'Tercero');
    await page.waitForSelector('.agente-error .agente-reintentar', espera);
    const fallo = await page.evaluate(() => ({ error: document.querySelector('.agente-error').textContent,
      sinEnviar: [...document.querySelectorAll('.agente-msj.agente-persona')].pop().textContent }));
    await page.click('.agente-error .agente-reintentar');
    await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Ahora sí.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    v.reintentar = fallo.error.includes('atendiendo muchas conversaciones') && fallo.sinEnviar.includes('No se envió')
      && await page.evaluate(() => !document.querySelector('.agente-error') && !document.querySelector('.sin-enviar')
        && [...document.querySelectorAll('.agente-msj.agente-persona p')].filter((p) => p.textContent === 'Tercero').length === 1);
    // La sesión venció: se abre el ingreso del panel en un diálogo y el mensaje se reintenta solo
    await enviar(page, 'Cuarto');
    await page.waitForSelector('dialog[open] #f-reingreso', espera);
    await page.fill('dialog[open] [name=clave]', clave);
    await page.click('dialog[open] button[type=submit]');
    await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Sesión renovada.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    v.reingreso = caso.mensajes.length === 6 && !await page.$('dialog[open]') && caso.mensajes[5].csrf && caso.mensajes[5].csrf !== caso.mensajes[4].csrf;
    // Escape cierra el panel (el foco está dentro) y el foco vuelve al botón
    await page.focus('#agente-texto');
    await page.keyboard.press('Escape');
    v.escape_cierra = await page.evaluate(() => document.querySelector('#agente-panel').hidden && document.activeElement?.id === 'agente-boton');
    // Al recargar la página vuelve abierto con la conversación guardada (pedida de nuevo al servidor)
    await page.click('#agente-boton');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#agente-panel:not([hidden]) .agente-md', espera);
    v.restaura_la_conversacion = await page.evaluate(() => document.querySelector('.agente-md').textContent === 'Encontré dos.'
      && document.querySelector('.agente-herr').dataset.estado === 'ok' && document.querySelector('#agente-sub').textContent.startsWith('¿Quiénes'));
    // Tema oscuro, para mirar
    await page.click('#cambiar-tema');
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-oscuro.png` });
    await page.click('#cambiar-tema');
  }

  // ── Historial: abrir una conversación con algo pendiente y borrarla ──
  await tocar('#agente-ver-historial');
  await page.waitForSelector('.agente-item .agente-abrir', espera);
  const lista = await page.evaluate(() => [...document.querySelectorAll('.agente-item b')].map((x) => x.textContent));
  v.historial = JSON.stringify(lista) === JSON.stringify(['¿Quiénes viven en Tres de Octubre?', 'Reunión <b>inventada</b>'])
    && await page.evaluate(() => document.querySelector('#agente-ver-historial').getAttribute('aria-expanded') === 'true' && document.querySelector('#agente-cuerpo').hidden);
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-historial.png` });
  await tocar('.agente-item:nth-child(2) .agente-abrir');
  await page.waitForSelector('.agente-tarjeta', espera);
  v.abre_del_historial = await page.evaluate(() => document.querySelector('.agente-md em')?.textContent === '12'
    && document.querySelector('.agente-tarjeta h3').textContent === 'Crear la reunión' && !document.querySelector('.agente-tarjeta .btn.primario').disabled
    && document.querySelector('.agente-nota.alerta')?.textContent === 'Mnemo no respondió.' && document.querySelector('#agente-sub').textContent === 'Reunión <b>inventada</b>');
  await tocar('#agente-ver-historial');
  await page.waitForSelector('.agente-item:nth-child(2) .agente-borrar', espera);
  await tocar('.agente-item:nth-child(2) .agente-borrar');
  await page.waitForSelector('dialog[open] [data-si]');
  await tocar('dialog[open] [data-si]');
  await page.waitForFunction(() => document.querySelectorAll('.agente-item').length === 1, null, espera);
  v.borra = caso.borradas.length === 1 && caso.borradas[0] === 7;
  await tocar('#agente-volver');
  v.vuelve_a_la_bienvenida = await page.evaluate(() => !!document.querySelector('.agente-bienvenida') && document.querySelector('#agente-sub').textContent === 'Nueva conversación');

  if (movil) {
    // En la ficha, abajo está su barra de acciones: el botón va arriba y no la tapa
    await tocar('#agente-cerrar');
    await page.evaluate((r) => { history.pushState({}, '', r); dispatchEvent(new PopStateEvent('popstate')); }, `${pref}/personas/${persona}`);
    await page.waitForSelector('#vista .barra-acciones', espera);
    await page.waitForTimeout(150);
    const f = await page.evaluate(() => {
      const r = (s) => { const e = document.querySelector(s); const b = e?.getBoundingClientRect(); return b && { x: b.left, y: b.top, d: b.right, a: b.bottom }; };
      return { boton: r('#agente-boton'), barra: r('#vista .barra-acciones'), guardar: r('#vista .guardar-ficha'), titulo: r('.barra-movil b') };
    });
    caso.geo.ficha_boton = f;
    v.boton_no_tapa_la_ficha = !!f.boton && f.boton.a <= 60 && !cruzan(f.boton, f.barra) && !cruzan(f.boton, f.guardar) && !cruzan(f.boton, f.titulo);
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-ficha.png` });
    await tocar('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])');
    g = await geometria(page, caso, 'ficha');
    v.panel_en_la_ficha = g.panelDentro && !g.desborde && await page.evaluate(() => getComputedStyle(document.querySelector('#vista .barra-acciones')).display === 'none');
    v.salir_en_la_ficha = await salirAlcanzable(page, tocar);
  }

  // Cerrar sesión borra lo guardado del asistente en la pestaña
  if (!movil) {
    await tocar('#agente-cerrar');
    await page.click('#salir');
    await page.waitForSelector('#f-login', espera);
    v.cerrar_sesion_olvida = await page.evaluate(() => sessionStorage.getItem('yj_agente') === null);
  }
}

async function sinClave(page, caso) {
  const v = caso.revisiones;
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-explicacion', espera);
  v.explica_la_variable = await page.evaluate(() => document.querySelector('.agente-explicacion').textContent.includes('ANTHROPIC_API_KEY')
    && document.querySelector('#agente-form').hidden && document.querySelector('#agente-nueva').hidden
    && document.querySelector('#agente-ver-historial').hidden && document.activeElement?.id === 'agente-cerrar');
  await page.waitForFunction(() => document.querySelector('#agente-panel').getAnimations().length === 0);
  await page.screenshot({ path: `${capturas}/agente-sin-clave.png` });
  await page.keyboard.press('Escape');
  v.cierra = await page.evaluate(() => document.querySelector('#agente-panel').hidden && !document.querySelector('#agente-boton').hidden);
  v.no_pidio_mensajes = caso.mensajes.length === 0;
}

async function real(page, caso) {
  const v = caso.revisiones;
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-sugerencia', espera);
  const t0 = Date.now();
  await enviar(page, 'Hola');
  await page.waitForFunction(() => document.querySelector('.agente-md p'), null, espera);
  const primero = Date.now() - t0;
  // Cuando ya hay un segundo párrafo, el primero está completo: se marca su nodo
  await page.waitForFunction(() => { const ps = document.querySelectorAll('.agente-md p'); if (ps.length < 2) return false; window.__p1 = ps[0]; return true; }, null, espera);
  await listo(page);
  const total = Date.now() - t0;
  const d = await page.evaluate(() => ({ respuesta: [...document.querySelectorAll('.agente-md p')].map((p) => p.textContent).join('\n\n'),
    mismo: document.querySelector('.agente-md p') === window.__p1, sub: document.querySelector('#agente-sub').textContent,
    restantes: document.querySelector('#agente-restantes').textContent }));
  caso.datos = { ...d, primero_ms: primero, total_ms: total };
  v.primer_parrafo_no_se_rehace = d.mismo;
  v.titulo = d.sub === 'Hola';
  v.restantes = /^Le quedan \d+ mensajes hoy$/.test(d.restantes);
  // «Detener» corta el turno y el siguiente mensaje funciona
  await enviar(page, 'Cuéntame más');
  await page.waitForFunction(() => document.querySelectorAll('.agente-md').length === 2, null, espera);
  await page.click('#agente-detener');
  await listo(page);
  const det = await page.evaluate(() => ({ notas: [...document.querySelectorAll('.agente-nota')].map((n) => n.textContent),
    parcial: [...document.querySelectorAll('.agente-md')][1]?.textContent || '' }));
  caso.datos.detenido = det;
  // Lo que alcanzó a llegar se queda (empieza por «Part…») y no llegó todo
  v.detenido = det.notas.includes('Detuvo la respuesta.') && det.parcial.startsWith('Part') && !det.parcial.includes('Parte 29');
  await enviar(page, 'Gracias');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'De nada.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, { timeout: 30000 });
  v.siguiente_mensaje = await page.evaluate(() => !document.querySelector('.agente-error'));
  await page.screenshot({ path: `${capturas}/agente-real.png` });
}

(async () => {
  const nav = await chromium.launch();
  const res = { casos: [] };
  try {
    for (const { nombre, estado, ...op } of CASOS) {
      const ctx = await nav.newContext(op);
      const caso = { nombre, revisiones: {}, errores: [], csp: [], mensajes: [], confirmaciones: [], borradas: [], insignias: 0 };
      await ctx.route((u) => u.origin !== origen, (r) => r.abort()); // sin red: fuentes de Google, teselas
      if (modo === 'protocolo') await servirAgente(ctx, caso, estado);
      await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
      await ctx.addInitScript(() => {
        addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
        window.__vistas = [];
        addEventListener('vista', (e) => window.__vistas.push(e.detail.ruta));
      });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => caso.errores.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
      // El 401 de GET /api/yo antes de ingresar es la pregunta del arranque («¿hay sesión?»): no es un error
      page.on('response', (x) => {
        if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo')) && x.headers()['x-prueba'] !== 'esperado') caso.errores.push(`${x.status()} ${x.url()}`);
      });
      page.on('request', (x) => { if (new URL(x.url()).pathname === pref + '/api/insignias') caso.insignias++; });
      try {
        if (nombre === 'sin_clave') await sinClave(page, caso);
        else if (modo === 'protocolo') await protocolo(page, op, caso);
        else await real(page, caso);
      } catch (e) {
        caso.revisiones.sin_excepcion = String(e.stack || e).slice(0, 1500);
        try { await page.screenshot({ path: `${capturas}/agente-${nombre}-fallo.png` }); } catch { /* nada */ }
      }
      res.casos.push(caso);
      await ctx.close();
    }
  } finally { await nav.close(); }
  console.log(JSON.stringify(res));
})().catch((e) => { console.error(e); process.exit(1); });
"""
