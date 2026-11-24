"""Revisión adversarial de las planillas por foto en el navegador (web/js/agente.js y web/js/vistas/importar.js), en
Chromium contra el panel de verdad (uvicorn, en /panel como en Railway), con la bandeja real y un proveedor del modelo
falso (sin red). Solo datos inventados; las imágenes se generan en la prueba.

* El widget no borra de la bandeja una foto que no subió él. La bandeja reconoce una foto que la persona ya había
  subido (su huella) y responde la que ya estaba (`repetida`): la misma foto dos veces en un mensaje, o una que ya llegó
  en otro mensaje (o que se subió en Importar y exportar y quizá ya se corrigió o se cargó en parte). Quitarla o girarla
  en el cuadro de escribir borraba esa planilla de la bandeja: la otra copia del mensaje quedaba apuntando a nada (el
  envío daba 422 «fotos») y una cargada en parte ya no se podía volver a subir (409 `ya_cargada`). Ahora la repetida
  dentro del mismo mensaje sale sola («ya estaba adjunta») y una repetida de antes nunca se borra.
* La vista Importar y exportar → Planillas por foto no reusa la Idempotency-Key de una carga con otras filas. Tras una
  carga que se cortó (sin respuesta, aunque el servidor la hizo), la vista guardaba la clave para el reintento; si la
  persona elegía otras filas (u otro folio) y cargaba, el servidor devolvía la respuesta guardada de la primera: la
  vista decía «Importación terminada» y las filas nuevas no se cargaban. La clave ahora va atada al cuerpo.

Se salta si no hay Node con Playwright, salvo en el CI."""
import json
import shutil
import subprocess

from ayudas_planillas import ProveedorFalso, encender, fila, jpeg, lectura_json
from test_agente_mapa import requiere_navegador
from test_planillas_vista_web import ANA, CARMEN, DORA, panel_web  # noqa: F401 (fixture)

COMUN = r"""const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const espera = { timeout: 25000 };
const presente = { state: 'attached', timeout: 25000 };
const salida = { errores: [], csp: [] };

async function contexto(nav) {
  const ctx = await nav.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
  });
  await ctx.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort());
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/401|Failed to load resource|fonts\.g/.test(m.text())) salida.errores.push(m.text()); });
  return { ctx, page };
}

async function ingresar(page, base, u, c) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', u);
  await page.fill('#f-login [name=clave]', c);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
}
"""

GUION_WIDGET = COMUN + r"""
const [base, usuario, clave, fotoA, fotoA2, fotoB, fotoC] = process.argv.slice(2);
const terminadas = (page) => page.waitForFunction(() => [...document.querySelectorAll('#agente-fotos-lista .agente-foto')]
  .every((li) => !['preparando', 'subiendo'].includes(li.dataset.estado)), null, espera);
const cuantas = (page) => page.evaluate(() => document.querySelectorAll('#agente-fotos-lista .agente-foto').length);

async function abrirWidget(page) {
  // En el computador el panel del asistente puede quedar abierto de antes (su botón se oculta mientras tanto)
  await page.waitForFunction(() => { const b = document.querySelector('#agente-boton');
    return !!b && (!b.hidden || b.getAttribute('aria-expanded') === 'true'); }, null, espera);
  if (await page.evaluate(() => !document.querySelector('#agente-boton').hidden)) await page.click('#agente-boton');
  await page.waitForSelector('#agente-adjuntar:not([hidden])', espera);
  if (await page.evaluate(() => document.querySelector('#agente-fotos').hidden)) await page.click('#agente-adjuntar');
}
// Las respuestas de cada subida (se leen aparte: hay que esperar a que lleguen todas) y los DELETE de la bandeja
const subidas = [], borradas = [];
async function esperarSubidas(n) {
  for (let i = 0; i < 250 && subidas.length < n; i++) await new Promise((ok) => setTimeout(ok, 100));
  if (subidas.length < n) throw new Error(`se esperaban ${n} subidas y hubo ${subidas.length}`);
}
async function adjuntar(page, archivos) {
  const antes = subidas.length;
  const [ch] = await Promise.all([page.waitForEvent('filechooser', espera), page.click('#agente-foto-galeria')]);
  await ch.setFiles(archivos);
  await esperarSubidas(antes + archivos.length);
  await terminadas(page);
  await page.waitForTimeout(300);
}

(async () => {
  const nav = await chromium.launch();
  const { ctx, page } = await contexto(nav);
  page.on('response', async (r) => {
    const u = new URL(r.url());
    if (r.request().method() === 'POST' && u.pathname.endsWith('/api/planillas/fotos')) {
      try { const d = await r.json(); subidas.push({ estado: r.status(), id: d.id, repetida: !!d.repetida }); } catch { /* nada */ }
    }
  });
  page.on('request', (q) => {
    const m = /\/api\/planillas\/([0-9a-f]{32})$/.exec(new URL(q.url()).pathname);
    if (q.method() === 'DELETE' && m) borradas.push(m[1]);
  });
  await ingresar(page, base, usuario, clave);
  await abrirWidget(page);

  // 1. La misma foto dos veces en el mismo mensaje: la bandeja responde la misma planilla. Si quedan dos en el cuadro,
  //    la persona quita la que sobra
  await adjuntar(page, [fotoA, fotoA2]);
  salida.dosVeces = { enCuadro: await cuantas(page), subidas: subidas.slice(),
    estado: await page.evaluate(() => document.querySelector('#agente-fotos-estado')?.textContent || '') };
  if (salida.dosVeces.enCuadro === 2) {
    await page.click('#agente-fotos-lista .agente-foto:nth-child(2) .agente-foto-quitar');
    await page.waitForTimeout(500);
  }
  salida.dosVeces.quedan = await cuantas(page);
  salida.dosVeces.borradas = borradas.slice();

  // 2. Una foto que ya estaba en la bandeja (subida antes; la página se recargó): adjuntarla otra vez y quitarla
  await adjuntar(page, [fotoB]);
  const idB = subidas[subidas.length - 1].id;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  await abrirWidget(page);
  await adjuntar(page, [fotoB]);
  salida.deAntes = { idB, otra: subidas[subidas.length - 1] };
  await page.click('#agente-fotos-lista .agente-foto:nth-child(1) .agente-foto-quitar');
  await page.waitForTimeout(500);

  // 3. Lo mismo, girándola: se sube la girada (otra planilla) y la que ya estaba no se borra
  await adjuntar(page, [fotoC]);
  const idC = subidas[subidas.length - 1].id;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  await abrirWidget(page);
  await adjuntar(page, [fotoC]);
  salida.girada = { idC, otra: subidas[subidas.length - 1] };
  const antesDeGirar = subidas.length;
  await page.click('#agente-fotos-lista .agente-foto:nth-child(1) .agente-foto-girar');
  await esperarSubidas(antesDeGirar + 1);
  await terminadas(page);
  await page.waitForTimeout(300);
  salida.girada.ultima = subidas[subidas.length - 1];
  salida.borradas = borradas.slice();
  salida.csp.push(...await page.evaluate(() => window.__csp));
  await ctx.close();
  await nav.close();
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""

GUION_VISTA = COMUN + r"""
const [base, usuario, clave, foto] = process.argv.slice(2);
const filaSel = (n) => `.pf-tabla tr[data-n="${n}"]`;

(async () => {
  const nav = await chromium.launch();
  const { ctx, page } = await contexto(nav);
  const cargas = [];
  let cortar = true;
  // La primera carga llega al servidor (que la hace) pero su respuesta se pierde, como sin señal
  await page.route(/\/api\/planillas\/[0-9a-f]{32}\/cargar$/, async (route) => {
    const q = route.request();
    cargas.push({ clave: q.headers()['idempotency-key'] || null, cuerpo: q.postDataJSON() });
    if (cortar) {
      cortar = false;
      await route.fetch();
      return route.abort('failed');
    }
    return route.continue();
  });
  await ingresar(page, base, usuario, clave);
  await page.goto(base + '/importar', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#planillas-foto #pf-galeria-in', presente);
  await page.setInputFiles('#pf-galeria-in', foto);
  await page.waitForFunction(() => /Por revisar/.test(document.querySelector('#pf-bandeja .pf-item')?.textContent || ''), null, espera);
  await page.click('#pf-bandeja [data-abrir]');
  await page.waitForSelector('.pf-tabla tbody tr', espera);
  await page.fill('#pf-folio', 'CARPETA 7, HOJA 2');

  // Cargar la fila 1: se corta. El diálogo sigue abierto para reintentar; la persona lo cancela
  await page.click('[data-elegir-grupo="ninguna"]');
  await page.check('[data-elegir="1"]');
  await page.click('#pf-cargar');
  await page.waitForSelector('dialog[open] #pf-si-cargar', espera);
  await page.click('dialog[open] #pf-si-cargar');
  await page.waitForFunction(() => { const b = document.querySelector('dialog[open] #pf-si-cargar'); return b && !b.disabled; }, null, espera);
  await page.click('dialog[open] [data-cerrar]');
  await page.waitForFunction(() => !document.querySelector('dialog[open]'), null, espera);

  // Ahora elige otra fila y la carga
  await page.click('[data-elegir-grupo="ninguna"]');
  await page.check('[data-elegir="2"]');
  await page.click('#pf-cargar');
  await page.waitForSelector('dialog[open] #pf-si-cargar', espera);
  await page.click('dialog[open] #pf-si-cargar');
  await page.waitForSelector('#pf-resultado .pf-resultado-caja', espera);
  salida.resultado = await page.evaluate(() => document.querySelector('#pf-resultado .pf-resultado-filas').textContent.replace(/\s+/g, ' '));
  salida.cargas = cargas;
  salida.csp.push(...await page.evaluate(() => window.__csp));
  await ctx.close();
  await nav.close();
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _correr(tmp_path, nombre: str, guion: str, *args: str) -> dict:
    ruta = tmp_path / nombre
    ruta.write_text(guion, encoding="utf-8")
    r = subprocess.run(["node", str(ruta), *args], capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


@requiere_navegador
def test_el_widget_no_borra_de_la_bandeja_una_foto_que_no_subio_el(panel_web, cfg, tmp_path, monkeypatch):
    base, panel = panel_web
    db = panel.state.db
    encender(monkeypatch, panel, ProveedorFalso())  # sin lectura de fondo: las fotos quedan «leyendo»
    a, a2, b, c = (tmp_path / n for n in ("a.jpg", "a-copia.jpg", "b.jpg", "c.jpg"))
    a.write_bytes(jpeg(2000, 1500))
    shutil.copyfile(a, a2)                     # la misma foto, elegida dos veces
    b.write_bytes(jpeg(1900, 1400))
    c.write_bytes(jpeg(1800, 1350))
    s = _correr(tmp_path, "widget.cjs", GUION_WIDGET, base, cfg.usuario, cfg.clave, str(a), str(a2), str(b), str(c))
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])

    # 1. La segunda copia es la misma planilla de la bandeja; queda una sola en el cuadro y nada se borra
    d = s["dosVeces"]
    assert [x["repetida"] for x in d["subidas"]] == [False, True], d
    assert d["subidas"][0]["id"] == d["subidas"][1]["id"]
    assert d["quedan"] == 1 and d["borradas"] == [], d
    assert db.planillas.count_documents({"_id": d["subidas"][0]["id"]}) == 1

    # 2. La que ya estaba en la bandeja: adjuntarla de nuevo la reconoce (repetida) y quitarla no la borra
    assert s["deAntes"]["otra"]["repetida"] is True and s["deAntes"]["otra"]["id"] == s["deAntes"]["idB"]
    assert db.planillas.count_documents({"_id": s["deAntes"]["idB"]}) == 1

    # 3. Girarla sube la girada (otra planilla) y la de antes sigue
    g = s["girada"]
    assert g["otra"]["repetida"] is True and g["otra"]["id"] == g["idC"]
    assert g["ultima"]["repetida"] is False and g["ultima"]["id"] != g["idC"]
    assert db.planillas.count_documents({"_id": g["idC"]}) == 1
    assert s["borradas"] == [], s["borradas"]


@requiere_navegador
def test_otra_carga_de_la_misma_planilla_no_reusa_la_clave_de_idempotencia(panel_web, cfg, tmp_path, monkeypatch):
    base, panel = panel_web
    db = panel.state.db
    proveedor = ProveedorFalso(lectura_json([fila(1, **ANA), fila(2, **CARMEN), fila(3, **DORA)]))
    encender(monkeypatch, panel, proveedor, de_fondo=True)
    foto = tmp_path / "hoja.jpg"
    foto.write_bytes(jpeg(1700, 1250))
    s = _correr(tmp_path, "vista.cjs", GUION_VISTA, base, cfg.usuario, cfg.clave, str(foto))
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])

    primera, segunda = s["cargas"]
    assert primera["cuerpo"]["filas"] == [1] and segunda["cuerpo"]["filas"] == [2]
    # Las dos se cargaron: la 1 (la que se cortó, que el servidor sí hizo) y la 2 (la que se pidió después); con la
    # misma clave, el servidor devolvía la respuesta de la 1 y la 2 quedaba sin cargar
    doc = db.planillas.find_one()
    assert set(doc.get("cargadas") or {}) == {"1", "2"}, (doc.get("cargadas"), s["resultado"])
    assert "Fila 2:" in s["resultado"] and "Fila 1:" not in s["resultado"], s["resultado"]
    assert primera["clave"] and segunda["clave"] and primera["clave"] != segunda["clave"], s["cargas"]
    assert db.importaciones.count_documents({}) == 2
