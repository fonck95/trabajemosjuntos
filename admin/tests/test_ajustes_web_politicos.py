"""Ajustes en Chromium, contra el panel de verdad (uvicorn, en /panel como en Railway): el bloque «Datos políticos en el
asistente y por MCP» (`agente_politicos`) y el aviso del compromiso en «Planillas físicas por foto».

Con el compromiso 2026-11-v1 vigente (prohíbe fotografiar), el administrador ve el aviso con el botón que pone la
versión 2026-11-v2 y las casillas de los datos políticos encendidas; el coordinador ve lo mismo en solo lectura (sin
botón ni guardar). El administrador apaga los datos políticos por MCP y guarda (PUT con los dos booleanos), cambia el
compromiso con el botón (confirmando) y el aviso desaparece. En el celular, sin desborde. Sin errores de consola ni
violaciones de la CSP. Solo datos inventados. Se salta si no hay Node con Playwright, salvo en el CI."""
import json
import subprocess

import pytest

from app import modelo
from conftest import CLAVE_USUARIO, crear_usuario
from test_agente_navegador import _servir, requiere_navegador

GUION = r"""const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, usuarioK, claveK] = process.argv.slice(2);
const espera = { timeout: 25000 };
const salida = { errores: [], csp: [], puts: [] };

(async () => {
  const nav = await chromium.launch();
  async function entrar(u, c, ancho) {
    const ctx = await nav.newContext({ viewport: { width: ancho, height: 900 } });
    await ctx.addInitScript(() => {
      window.__csp = [];
      document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
    });
    await ctx.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort());
    const page = await ctx.newPage();
    page.on('pageerror', (e) => salida.errores.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/401|403|Failed to load resource|fonts\.g/.test(m.text())) salida.errores.push(m.text()); });
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', u);
    await page.fill('#f-login [name=clave]', c);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.goto(base + '/ajustes', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#f-politicos', espera);
    return { ctx, page };
  }
  const leer = (pg) => pg.evaluate(() => ({
    politicos: [...document.querySelectorAll('#f-politicos input[type=checkbox]')].map((c) => [c.name, c.checked, c.disabled]),
    guardar: !!document.querySelector('#f-politicos button.primario'),
    aviso: document.querySelector('#pf-compromiso')?.textContent.replace(/\s+/g, ' ').trim() || null,
    boton: document.querySelector('#compromiso-fotos')?.textContent.trim() || null,
    roles: [...document.querySelectorAll('#f-planillas input[name^=planillas_rol_]')].map((c) => c.name),
    nota: document.querySelector('#f-politicos .aviso-legal')?.textContent.replace(/\s+/g, ' ').trim() || null,
  }));

  // ── El administrador y el coordinador, con el compromiso que prohíbe fotografiar ──
  const a = await entrar(usuario, clave, 1360);
  salida.a = await leer(a.page);
  const k = await entrar(usuarioK, claveK, 1360);
  salida.k = await leer(k.page);
  salida.csp.push(...await k.page.evaluate(() => window.__csp));
  await k.ctx.close();

  // ── Apaga los datos políticos por MCP y guarda ──
  a.page.on('request', (r) => { if (r.method() === 'PUT' && r.url().endsWith('/api/ajustes')) salida.puts.push(JSON.parse(r.postData())); });
  await a.page.$eval('#f-politicos [name=politicos_mcp]', (c) => { c.checked = false; });
  await Promise.all([
    a.page.waitForResponse((r) => r.url().endsWith('/api/ajustes') && r.request().method() === 'PUT', espera),
    a.page.click('#f-politicos button.primario'),
  ]);
  await a.page.waitForFunction(() => {
    const c = document.querySelector('#f-politicos [name=politicos_mcp]');
    return c && !c.checked;
  }, null, espera);
  salida.guardado = await leer(a.page);

  // ── Cambia el compromiso con el botón del aviso (confirmando) ──
  await a.page.click('#compromiso-fotos');
  await a.page.waitForSelector('dialog [data-si], .dialogo [data-si], [data-si]', espera);
  salida.confirmar = await a.page.evaluate(() => document.querySelector('[data-si]').closest('dialog, .dialogo, [role=dialog]')?.textContent.replace(/\s+/g, ' ').trim() || '');
  await Promise.all([
    a.page.waitForResponse((r) => r.url().endsWith('/api/ajustes') && r.request().method() === 'PUT', espera),
    a.page.click('[data-si]'),
  ]);
  await a.page.waitForFunction(() => !document.querySelector('#pf-compromiso') && document.querySelector('#f-politicos'), null, espera);
  salida.cambiado = await leer(a.page);
  // En el celular, sin desborde
  await a.page.setViewportSize({ width: 390, height: 900 });
  await a.page.waitForTimeout(200);
  salida.desborde = await a.page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  salida.csp.push(...await a.page.evaluate(() => window.__csp));
  await a.ctx.close();
  console.log(JSON.stringify(salida));
  await nav.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture
def panel(cfg, tmp_path):
    with _servir(cfg, tmp_path) as servido:
        yield servido


@requiere_navegador
def test_datos_politicos_y_compromiso_en_ajustes(panel, cfg, tmp_path):
    base, app, _, _ = panel
    db = app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"compromiso_version": "2026-11-v1"}}, upsert=True)
    k = crear_usuario(db, "planillero", usuario="coordinadora.inventada", nombre="COORDINADORA INVENTADA")
    db.usuarios.update_one({"_id": k["_id"]}, {"$set": {"rol": "coordinador"}})
    (tmp_path / "ajustes.cjs").write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "ajustes.cjs"), base, cfg.usuario, cfg.clave, k["usuario"],
                        CLAVE_USUARIO], capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])

    # El administrador: las dos casillas encendidas, el aviso del compromiso con su botón, roles solo A y K
    a = s["a"]
    assert a["politicos"] == [["politicos_asistente", True, False], ["politicos_mcp", True, False]]
    assert a["guardar"] is True and "art. 5" in a["nota"]
    assert "versión 2026-11-v1" in a["aviso"] and "nunca cédulas ni otros documentos" in a["aviso"]
    assert a["boton"] == "Usar el compromiso 2026-11-v2"
    assert a["roles"] == ["planillas_rol_admin", "planillas_rol_coordinador"]
    # El coordinador: lo mismo en solo lectura
    kk = s["k"]
    assert kk["politicos"] == [["politicos_asistente", True, True], ["politicos_mcp", True, True]]
    assert kk["guardar"] is False and kk["boton"] is None
    assert "Solo el administrador cambia la versión del compromiso." in kk["aviso"]

    # Lo guardado: los dos booleanos; luego el compromiso nuevo, confirmado
    assert s["puts"][0] == {"agente_politicos": {"asistente": True, "mcp": False}}
    assert s["guardado"]["politicos"] == [["politicos_asistente", True, False], ["politicos_mcp", False, False]]
    assert "2026-11-v2" in s["confirmar"] and "aceptarlo de nuevo" in s["confirmar"]
    assert s["puts"][1] == {"compromiso_version": "2026-11-v2"} and len(s["puts"]) == 2
    assert s["cambiado"]["aviso"] is None and s["desborde"] <= 0
    aj = modelo.leer_ajustes(db)
    assert aj["agente_politicos"] == {"asistente": True, "mcp": False} and aj["compromiso_version"] == "2026-11-v2"
