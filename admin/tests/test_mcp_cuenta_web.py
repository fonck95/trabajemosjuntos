"""Mi cuenta → Agentes por MCP con la clave de datos (web/js/vistas/cuenta.js y web/css/app.css), en Chromium contra el
panel de verdad (uvicorn, en /panel como en Railway): el aviso de que los datos salen del panel, los permisos con el
motivo de los que no se tienen, la clave de datos que se muestra una vez y sin dirección, una propuesta que llega por
MCP (el guion la pide como lo haría un agente externo) y se abre con el enlace `aprobar_en` resaltada, con su tarjeta
entera (saltos de línea y espacios incluidos, y lo que parece HTML como texto), el motivo del agente y de qué clave y
desde qué IP llegó; Aprobar la ejecuta y queda en «Últimas decididas»; revocar la clave. En el celular, sin desborde
horizontal. Sin errores de consola ni violaciones de la CSP. Solo datos inventados.

Se salta si no hay Node con Playwright, salvo en el CI."""
import json
import socket
import subprocess
import threading
import time

import pymongo
import pytest
import uvicorn

from ayudas_g3 import autorizada, persona
from conftest import MONGO, URI
from test_agente_mapa import requiere_navegador

GUION = r"""const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, pid] = process.argv.slice(2);
const espera = { timeout: 20000 };
const TEXTO = 'Pidió que la llamen en la tarde.\n   Vive cerca del parque <b>grande</b>.';
const salida = { errores: [], csp: [] };

async function mcp(claveMcp, metodo, params) {
  const r = await fetch(base + '/api/mcp', { method: 'POST', headers: { 'content-type': 'application/json',
    authorization: 'Bearer ' + claveMcp }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: metodo, params }) });
  return { estado: r.status, json: await r.json() };
}

(async () => {
  const nav = await chromium.launch();
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/401|Failed to load resource/.test(m.text())) salida.errores.push(m.text()); });
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.goto(base + '/cuenta', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#mcp-datos #mcp-propuestas h3', espera);
  salida.bloque = await page.evaluate(() => ({
    aviso: document.querySelector('.mcp-aviso')?.textContent || '',
    casillas: [...document.querySelectorAll('input[name=alcance]')].map((x) => [x.value, x.disabled, x.checked]),
    pendientes: document.querySelector('#mcp-propuestas')?.textContent || '',
  }));
  // Crear la clave de datos con lectura y escritura
  await page.check('input[name=alcance][value=lectura]');
  await page.check('input[name=alcance][value=escritura]');
  await page.click('#mcp-crear-datos');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  salida.confirmacion = await page.textContent('dialog[open]');
  await page.click('dialog[open] [data-si]');
  await page.waitForSelector('#mcp-clave-datos', espera);
  const claveMcp = await page.inputValue('#mcp-clave-datos');
  salida.nueva = { prefijo: claveMcp.slice(0, 4),
    con_direccion: await page.evaluate(() => !!document.querySelector('#mcp-datos #mcp-con-clave')) };
  // El agente externo propone una nota (como Claude Desktop): queda pendiente
  const lista = await mcp(claveMcp, 'tools/list', {});
  salida.herramientas = lista.json.result.tools.map((h) => h.name);
  const r = await mcp(claveMcp, 'tools/call', { name: 'agregar_nota', arguments: { persona_id: Number(pid), texto: TEXTO,
    motivo_propuesta: 'Lo pidió en la reunión del barrio' } });
  const propuesta = JSON.parse(r.json.result.content[0].text);
  salida.propuesta = propuesta;
  // El enlace que da el agente: la propuesta resaltada, con la tarjeta entera
  await page.goto(propuesta.aprobar_en, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.mcp-propuesta.resaltada', espera);
  salida.tarjeta = await page.evaluate(() => {
    const t = document.querySelector('.mcp-propuesta.resaltada');
    const dd = [...t.querySelectorAll('dt')].find((x) => x.textContent === 'Nota')?.nextElementSibling;
    return { nota: dd?.textContent, html_inyectado: !!t.querySelector('dd b'), motivo: t.querySelector('.mcp-motivo')?.textContent,
      origen: t.querySelector('.mcp-origen')?.textContent, botones: [...t.querySelectorAll('button')].map((b) => b.textContent),
      pre: getComputedStyle(dd).whiteSpace, insignia: document.querySelector('#mcp-propuestas h3 .chip')?.textContent };
  });
  // En el celular: sin desborde horizontal
  await page.setViewportSize({ width: 390, height: 844 });
  salida.desborde = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  await page.setViewportSize({ width: 1280, height: 900 });
  // Aprobar
  await page.click('.mcp-propuesta.resaltada [data-aprobar]');
  await page.waitForFunction(() => !document.querySelector('.mcp-propuesta'), null, espera);
  salida.despues = await page.evaluate(() => ({
    vacio: document.querySelector('#mcp-propuestas')?.textContent || '',
    recientes: document.querySelector('.mcp-recientes')?.textContent || '' }));
  salida.estado = JSON.parse((await mcp(claveMcp, 'tools/call', { name: 'estado_propuesta',
    arguments: { propuesta: propuesta.propuesta } })).json.result.content[0].text).estado;
  // Revocar la clave de datos
  await page.click('#mcp-revocar-datos');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  await page.click('dialog[open] [data-si]');
  await page.waitForFunction(() => !document.querySelector('#mcp-revocar-datos'), null, espera);
  salida.revocada = (await mcp(claveMcp, 'ping', {})).estado;
  salida.csp = await page.evaluate(() => window.__csp);
  console.log(JSON.stringify(salida));
  await nav.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture
def panel_web(cfg, tmp_path):
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
        yield f"http://127.0.0.1:{sock.getsockname()[1]}/panel", app.state.panel
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


@requiere_navegador
def test_mi_cuenta_clave_de_datos_y_propuestas_en_chromium(panel_web, cfg, tmp_path):
    base, panel = panel_web
    db = panel.state.db
    pid = persona(db, nombre="CANDELARIA CUENTA INVENTADA")
    autorizada(db, pid)
    (tmp_path / "cuenta.cjs").write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "cuenta.cjs"), base, cfg.usuario, cfg.clave, str(pid)],
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])
    assert "salen del panel" in s["bloque"]["aviso"] and "Authorization: Bearer" in s["bloque"]["aviso"]
    assert s["bloque"]["casillas"] == [["lectura", False, False], ["analitica", False, False],
                                       ["escritura", False, False]]
    assert "No hay cambios esperando" in s["bloque"]["pendientes"]
    assert "sale del panel" in s["confirmacion"]
    assert s["nueva"]["prefijo"] == "ypd_" and s["nueva"]["con_direccion"] is False
    assert "buscar_personas" in s["herramientas"] and "estado_propuesta" in s["herramientas"]
    assert s["propuesta"]["estado"] == "pendiente" and "CANDELARIA" not in json.dumps(s["propuesta"])
    texto = "Pidió que la llamen en la tarde.\n   Vive cerca del parque <b>grande</b>."
    t = s["tarjeta"]
    assert t["nota"] == texto and t["html_inyectado"] is False and t["pre"] == "pre-wrap"
    assert "Lo pidió en la reunión del barrio" in t["motivo"] and "127.0.0.1" in t["origen"] and "…" in t["origen"]
    assert t["botones"] == ["Aprobar", "Rechazar"] and t["insignia"] == "1"
    assert s["desborde"] <= 0
    assert "No hay cambios esperando" in s["despues"]["vacio"] and "Hecha" in s["despues"]["recientes"]
    assert s["estado"] == "hecha" and s["revocada"] == 401
    assert [n["texto"] for n in db.personas.find_one({"_id": pid})["notas"]] == [texto]
