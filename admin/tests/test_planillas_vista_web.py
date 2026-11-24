"""Importar y exportar → Planillas por foto (web/js/vistas/importar.js y web/css/planillas.css), en Chromium contra el
panel de verdad (uvicorn, en /panel como en Railway), con la bandeja y su lectura de fondo reales y un proveedor del
modelo falso que responde una lectura inventada (sin red).

El administrador sube una foto generada (con el selector de la galería): la bandeja la muestra «leyendo» y, al
terminar, «Por revisar» (se consulta sola). La abre: la foto en un canvas al lado de la grilla con los valores
completos, lo dudoso marcado; corrige una celda (PATCH) y la fila queda corregida y elegida; coteja (la vista previa del
importador por fila: nueva, completa una ficha, nueva sin autorización); desmarca una fila y carga las demás con el
folio y el planillero; el resultado enlaza a la confirmación de las autorizaciones «declaradas en planilla», que se
confirman con el papel; luego carga la fila que faltaba y la planilla queda cargada, sin foto. En el celular, sin
desborde horizontal. La insignia de «Mi cuenta» cuenta las propuestas MCP pendientes. Un planillero no ve las
planillas por foto (son solo del administrador y los coordinadores): la vista no le muestra la sección ni le pide la
bandeja. Sin errores de consola ni violaciones de la CSP. Solo datos inventados; las imágenes se generan en la prueba.

Se salta si no hay Node con Playwright, salvo en el CI."""
import json
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import uvicorn

from ayudas_g3 import persona
from ayudas_planillas import ProveedorFalso, encender, fila, jpeg, lectura_json
from conftest import CLAVE_USUARIO, MONGO, URI, crear_usuario
from test_agente_mapa import requiere_navegador

ANA = dict(cedula="90000101", cedula_repetida="90000101", tipo_documento="CC", nombre="ANA INVENTADA RUIZ",
           celular="3101234501", sexo="F", fecha_nacimiento="14/03/1979", direccion="CALLE 50 # 48-21",
           barrio="TRES DE OCTUBRE", autorizacion="si", medio="escrito", canales="llamada, whatsapp", mayor_18="si",
           fecha="02/11/2026", observaciones="Vive con su hija")
BERTA = dict(cedula="90000202", tipo_documento="CC", nombre="BERTA INVENTADA SOLANO", celular="31012345O2",
             barrio="TRES DE OCTUBRE", autorizacion="si", medio="escrito", canales="llamada", mayor_18="si",
             fecha="02/11/2026")
CARMEN = dict(cedula="90000303", tipo_documento="CC", nombre="CARMEN INVENTADA LOPEZ", celular="3101234503",
              barrio="TRES DE OCTUBRE", mayor_18="si", fecha="02/11/2026")
CENOBIA = dict(cedula="90000131", nombre="CENOBIA INVENTADA PACHECO", celular="3101234541",
               direccion="CALLE 49 # 47-03", barrio="TRES DE OCTUBRE", autorizacion="no",
               observaciones="No quiere que la llamen")
DORA = dict(cedula="90000404", cedula_repetida="90000404", tipo_documento="CC", nombre="DORA INVENTADA MEJIA",
            celular="3101234504", barrio="TRES DE OCTUBRE", autorizacion="si", medio="verbal", mayor_18="si")

GUION = r"""const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, foto, fotoP, usuarioP, claveP, planillero] = process.argv.slice(2);
const espera = { timeout: 25000 };
const presente = { state: 'attached', timeout: 25000 };
const salida = { errores: [], csp: [] };

async function contexto(nav, ancho = 1360) {
  const ctx = await nav.newContext({ viewport: { width: ancho, height: 900 } });
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
  });
  // Las letras del panel son externas y aquí no hay internet
  await ctx.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort());
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/401|Failed to load resource|fonts\.g/.test(m.text())) salida.errores.push(m.text()); });
  return { ctx, page };
}

async function ingresar(page, u, c) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', u);
  await page.fill('#f-login [name=clave]', c);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
}

// Con CAPTURAS=<carpeta> en el entorno, guarda capturas de la vista (para mirarla a ojo; la prueba no las necesita)
const capturar = async (pg, nombre) => { if (process.env.CAPTURAS) await pg.screenshot({ path: `${process.env.CAPTURAS}/${nombre}.png`, fullPage: true }); };
const filaSel = (n) => `.pf-tabla tr[data-n="${n}"]`;

(async () => {
  const nav = await chromium.launch();
  // ── El administrador ──
  const { ctx, page } = await contexto(nav);
  await ingresar(page, usuario, clave);
  await page.waitForFunction(() => document.querySelector('#insignia-cuenta')?.textContent === '1', null, espera);
  salida.insignia = await page.evaluate(() => {
    const b = document.querySelector('#insignia-cuenta');
    return { texto: b.textContent, oculta: b.classList.contains('oculto'), titulo: b.title };
  });
  // Lo que se calcula sin el navegador, desde el módulo de la vista
  salida.puras = await page.evaluate(async () => {
    const m = await import(new URL('vistas/importar.js', document.querySelector('script[type=module]').src).href);
    const filas = [{ n: 1, estado: 'pendiente', dudosos: [] }, { n: 2, estado: 'pendiente', dudosos: ['celular'] },
      { n: 3, estado: 'no_autoriza' }, { n: 4, estado: 'cargada' }, { n: 5, estado: 'pendiente', ilegibles: ['cedula'] },
      { n: 6, estado: 'descartada' }, { n: 7, estado: 'no_se_carga' }];
    return {
      sinModelo: m.limitesSubida({ configurado: false, proveedor: null }),
      directo: m.limitesSubida({ configurado: true, proveedor: 'anthropic', adjuntos: null }),
      mnemo: m.limitesSubida({ configurado: true, proveedor: 'mnemo' }),
      delEstado: m.limitesSubida({ proveedor: 'anthropic', adjuntos: { max_por_mensaje: 4, lado_max: 2000, calidad: 0.7, max_bytes: 900000 } }),
      malos: m.limitesSubida({ proveedor: 'anthropic', adjuntos: { lado_max: 99999, calidad: 0.8, max_bytes: 1500000 } }),
      sinEstado: m.limitesSubida(null),
      medidas: [m.medidasFoto(4000, 3000, 2000), m.medidasFoto(800, 600, 2000)],
      pasos: m.pasosCalidad(0.8),
      avisos: [m.avisosFoto({ ladoOriginal: 1200, brillo: 40 }), m.avisosFoto({ ladoOriginal: 3000, brillo: 200 })],
      porDefecto: [...m.filasPorDefecto(filas)].sort(),
      seleccionables: filas.filter(m.seleccionable).map((f) => f.n),
      filtros: ['todas', 'revisar', 'leyendo', 'error', 'cargada'].map((k) => m.filtrarBandeja(
        [{ estado: 'leyendo' }, { estado: 'leida' }, { estado: 'fallida' }, { estado: 'rechazada' }, { estado: 'cargada' }], k).length),
      estados: [m.estadoPlanilla({ estado: 'leyendo', progreso: 7 }).texto, m.estadoPlanilla({ estado: 'leida', pendientes: 3 }).texto,
        m.estadoPlanilla({ estado: 'leida', pendientes: 2, cargadas: 1 }).texto, m.estadoPlanilla({ estado: 'leida', pendientes: 0 }).texto,
        m.estadoPlanilla({ estado: 'cargada', importacion_id: 9 }).texto],
    };
  });

  await page.goto(base + '/importar', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#planillas-foto #pf-galeria-in', presente);
  await page.waitForSelector('#pf-bandeja .pf-vacia', espera); // la bandeja ya llegó (vacía)
  salida.seccion = await page.evaluate(() => ({
    camara: document.querySelector('#pf-camara-in')?.getAttribute('capture'),
    galeriaMultiple: document.querySelector('#pf-galeria-in')?.multiple,
    aviso: document.querySelector('.pf-aviso')?.textContent || '',
    privacidad: document.querySelector('.pf-privacidad')?.textContent || '',
    vacia: document.querySelector('#pf-bandeja')?.textContent || '',
    historial: !!document.querySelector('#historial'),
  }));
  // Subir la foto con el selector de la galería
  const subida = page.waitForResponse((r) => r.url().includes('/api/planillas/fotos') && r.request().method() === 'POST', espera);
  await page.fill('#pf-nota', 'Vereda inventada, reunión del 2/11');
  await page.setInputFiles('#pf-galeria-in', foto);
  const resp = await subida;
  salida.subida = { estado: resp.status(), tipo: resp.request().headers()['content-type'], cuerpo: await resp.json() };
  await page.waitForFunction(() => /en la bandeja/.test(document.querySelector('#pf-subidas')?.textContent || ''), null, espera);
  salida.subidas = await page.textContent('#pf-subidas');
  // La bandeja se consulta sola hasta que termina la lectura
  await page.waitForFunction(() => /Por revisar/.test(document.querySelector('#pf-bandeja .pf-item')?.textContent || ''), null, espera);
  salida.bandeja = await page.evaluate(() => {
    const it = document.querySelector('#pf-bandeja .pf-item');
    return { texto: it.textContent.replace(/\s+/g, ' '), boton: it.querySelector('[data-abrir]').textContent };
  });

  // Abrir: la foto y la grilla
  await page.click('#pf-bandeja [data-abrir]');
  await page.waitForSelector('#planilla-abierta .pf-tabla', espera);
  await page.waitForFunction(() => (document.querySelector('#pf-lienzo')?.width || 0) > 0, null, espera);
  salida.abierta = await page.evaluate(() => {
    const c = document.querySelector('#pf-lienzo');
    const px = c.getContext('2d').getImageData(Math.floor(c.width / 2), 40, 1, 1).data;
    const fila = (n) => document.querySelector(`.pf-tabla tr[data-n="${n}"]`);
    const valor = (n, k) => fila(n)?.querySelector(`.pf-entrada[data-campo="${k}"]`)?.value;
    return {
      url: location.search,
      lienzo: [c.width, c.height, px[0] < 100], // la línea oscura de la «planilla» inventada
      filas: [...document.querySelectorAll('.pf-tabla tbody tr')].map((t) => [Number(t.dataset.n), t.dataset.estado]),
      ana: [valor(1, 'cedula'), valor(1, 'celular'), valor(1, 'observaciones')],
      dudoso: fila(2).querySelector('td[data-campo="celular"]').dataset.marca,
      etiqueta: fila(2).querySelector('.pf-entrada[data-campo="celular"]').getAttribute('aria-label'),
      no: [valor(4, 'nombre'), valor(4, 'celular'), valor(4, 'autorizacion')],
      elegidas: [...document.querySelectorAll('[data-elegir]')].filter((x) => x.checked).map((x) => Number(x.dataset.elegir)),
      cargar: document.querySelector('#pf-cargar').textContent,
      guardar: document.querySelector('#pf-guardar').disabled,
      sinCrudo: !document.querySelector('.pf-tabla b, .pf-tabla script'),
    };
  });
  // Zoom y giro de la foto (solo la vista)
  await page.click('[data-zoom="1"]');
  await page.click('#pf-girar');
  salida.zoom = await page.evaluate(() => ({ valor: document.querySelector('#pf-zoom-valor').textContent,
    lienzo: [document.querySelector('#pf-lienzo').width, document.querySelector('#pf-lienzo').height] }));
  await page.click('[data-zoom="0"]');

  // Corregir la celda dudosa
  await page.fill(`${filaSel(2)} .pf-entrada[data-campo="celular"]`, '3101234502');
  salida.antesDeGuardar = await page.textContent('#pf-guardar');
  const parche = page.waitForResponse((r) => /\/api\/planillas\/[0-9a-f]{32}$/.test(r.url()) && r.request().method() === 'PATCH', espera);
  await page.click('#pf-guardar');
  salida.parche = { estado: (await parche).status(), cuerpo: (await parche).request().postDataJSON() };
  await page.waitForFunction(() => document.querySelector('.pf-tabla tr[data-n="2"] td[data-campo="celular"]')?.dataset.marca === 'corregido', null, espera);
  salida.corregida = await page.evaluate(() => ({
    valor: document.querySelector('.pf-tabla tr[data-n="2"] .pf-entrada[data-campo="celular"]').value,
    elegida: document.querySelector('[data-elegir="2"]').checked,
    guardar: document.querySelector('#pf-guardar').disabled,
  }));

  // Cotejar
  await page.click('#pf-cotejar');
  await page.waitForSelector('#pf-cotejo-resumen .chips', espera);
  salida.cotejo = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('.pf-tabla tbody tr')].map((t) => [t.dataset.n,
    [...t.querySelectorAll('.pf-estado-celda .chip')].map((c) => c.textContent.replace(/[▾▴]/g, '').trim())])));
  if (process.env.CAPTURAS) await page.evaluate(() => { document.querySelector('.pf-tabla-env').scrollLeft = 0; });
  await capturar(page, '1-cotejo-escritorio');
  salida.cotejoDetalle = await page.evaluate(() => document.querySelector('.pf-tabla tr[data-n="3"] .pf-cotejo')?.textContent || '');

  // Cargar todas menos la de CARMEN, con folio y planillero
  await page.uncheck('[data-elegir="3"]');
  await page.fill('#pf-folio', 'Carpeta 3, hoja 12');
  await page.selectOption('#pf-capturado', planillero);
  await page.click('#pf-cargar');
  await page.waitForSelector('dialog[open] #pf-si-cargar', espera);
  salida.dialogo = (await page.textContent('dialog[open]')).replace(/\s+/g, ' ');
  const carga = page.waitForResponse((r) => r.url().endsWith('/cargar') && r.request().method() === 'POST', espera);
  await page.click('dialog[open] #pf-si-cargar');
  const rc = await carga;
  salida.carga = { estado: rc.status(), cuerpo: rc.request().postDataJSON(), clave: !!rc.request().headers()['idempotency-key'] };
  await page.waitForSelector('.pf-resultado-caja', espera);
  await page.waitForFunction(() => document.querySelector('.pf-tabla tr[data-n="1"]')?.dataset.estado === 'cargada', null, espera);
  salida.resultado = await page.evaluate(() => ({
    texto: document.querySelector('.pf-resultado-caja').textContent.replace(/\s+/g, ' '),
    confirmar: document.querySelector('[data-confirmar-carga]')?.textContent,
    filas: [...document.querySelectorAll('.pf-tabla tbody tr')].map((t) => [Number(t.dataset.n), t.dataset.estado]),
    enlace: document.querySelector('.pf-tabla tr[data-n="1"] a')?.getAttribute('href'),
    historial: document.querySelector('#historial')?.textContent.includes('Foto de planilla física'),
    dialogo: !!document.querySelector('dialog[open]'),
  }));
  // En el celular: sin desborde horizontal de la página
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  await capturar(page, '2-resultado-celular');
  salida.desborde = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  // Si se desborda, qué lo desborda (para el mensaje de la prueba)
  salida.anchos = await page.evaluate(() => [...document.querySelectorAll('#vista *')]
    .filter((x) => x.getBoundingClientRect().right > innerWidth + 1 && !x.closest('.envoltura-tabla, .pf-foto-marco'))
    .slice(0, 8).map((x) => `${x.tagName}.${x.className}#${x.id} ${Math.round(x.getBoundingClientRect().right)}`));
  await page.setViewportSize({ width: 1360, height: 900 });

  // Confirmar las autorizaciones declaradas, con el papel
  await page.click('[data-confirmar-carga]');
  await page.waitForSelector('dialog[open] #evidencia', espera);
  await page.fill('dialog[open] #evidencia', 'Planilla física, carpeta 3, hoja 12, archivada en la sede');
  const conf = page.waitForResponse((r) => r.url().endsWith('/confirmar-autorizaciones'), espera);
  await page.click('dialog[open] #g');
  salida.confirmadas = await (await conf).json();

  // La fila que faltaba: la planilla queda cargada y sin foto
  await page.check('[data-elegir="3"]');
  await page.click('#pf-cargar');
  await page.waitForSelector('dialog[open] #pf-si-cargar', espera);
  await page.click('dialog[open] #pf-si-cargar');
  await page.waitForFunction(() => /Cargada/.test(document.querySelector('.pf-abierta-cab .chip')?.textContent || ''), null, espera);
  salida.final = await page.evaluate(() => ({
    chip: document.querySelector('.pf-abierta-cab .chip').textContent,
    sinFoto: !!document.querySelector('.pf-revision.sin-foto') && !document.querySelector('#pf-lienzo'),
    filas: [...document.querySelectorAll('.pf-tabla tbody tr')].map((t) => [Number(t.dataset.n), t.dataset.estado]),
    acciones: !!document.querySelector('#pf-cargar'),
  }));
  // Cerrar la planilla
  await page.click('#pf-cerrar');
  salida.cerrada = await page.evaluate(() => ({ oculta: document.querySelector('#planilla-abierta').hidden, url: location.search }));
  salida.csp.push(...await page.evaluate(() => window.__csp));
  await ctx.close();

  // ── El planillero: no ve las planillas por foto (solo A y K) ──
  const p = await contexto(nav, 390);
  await ingresar(p.page, usuarioP, claveP);
  const pedidasP = [];
  p.page.on('request', (r) => { if (r.url().includes('/api/planillas')) pedidasP.push(r.url()); });
  salida.p = await p.page.evaluate(async () => {
    const m = await import(new URL('vistas/importar.js', document.querySelector('script[type=module]').src).href);
    const div = document.createElement('div');
    div.className = 'vista';
    div.id = 'prueba-p';
    document.querySelector('#vista').replaceChildren(div);
    const limpiar = await m.vistaImportar(div, { q: new URLSearchParams() });
    limpiar?.();
    return { secciones: [...div.querySelectorAll('section')].map((s) => s.id || s.querySelector('h2')?.textContent),
      galeria: !!div.querySelector('#pf-galeria-in'), aviso: !!div.querySelector('.pf-aviso'),
      desborde: document.documentElement.scrollWidth - innerWidth };
  });
  salida.p.pedidas = pedidasP;
  await capturar(p.page, '3-planillero-celular');
  salida.csp.push(...await p.page.evaluate(() => window.__csp));
  await p.ctx.close();
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
def test_planillas_por_foto_en_chromium(panel_web, cfg, tmp_path, monkeypatch):
    base, panel = panel_web
    db = panel.state.db
    proveedor = ProveedorFalso(
        lectura_json([fila(1, firma="presente", **ANA), fila(2, firma="presente", dudosos=["celular"], **BERTA),
                      fila(3, **CARMEN), fila(4, **CENOBIA)],
                     encabezado={"planillero": None, "fecha": "02/11/2026", "lugar": "TRES DE OCTUBRE"}),
        lectura_json([fila(1, **DORA)]))
    encender(monkeypatch, panel, proveedor, de_fondo=True)
    carmen = persona(db, nombre="CARMEN INVENTADA LOPEZ", cedula="90000303", tipo_documento="CC")
    pl = crear_usuario(db, "planillero", usuario="pedro.campo", nombre="PEDRO PLANILLERO INVENTADO")
    pp = crear_usuario(db, "planillero", usuario="rosa.campo", nombre="ROSA PLANILLERA INVENTADA")
    db.mcp_propuestas.insert_one({"_id": "a" * 32, "uid": 0, "estado": "pendiente",
                                  "vence": datetime.now(timezone.utc) + timedelta(hours=2)})
    foto, foto_p = tmp_path / "hoja.jpg", tmp_path / "hoja-p.jpg"
    foto.write_bytes(jpeg(1200, 900))
    foto_p.write_bytes(jpeg(1300, 1000))
    (tmp_path / "planillas.cjs").write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "planillas.cjs"), base, cfg.usuario, cfg.clave, str(foto), str(foto_p),
                        pp["usuario"], CLAVE_USUARIO, str(pl["_id"])], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])

    # La insignia de «Mi cuenta»: las propuestas MCP que esperan
    assert s["insignia"] == {"texto": "1", "oculta": False,
                             "titulo": "Cambios propuestos por un agente MCP que esperan su aprobación"}

    # Lo puro de la vista
    u = s["puras"]
    assert u["sinModelo"] is None and u["sinEstado"] == {"ladoMax": 2000, "calidad": 0.8, "maxBytes": 1500000}
    assert u["directo"]["ladoMax"] == 2576 and u["mnemo"]["ladoMax"] == 2000
    assert u["delEstado"] == {"ladoMax": 2000, "calidad": 0.7, "maxBytes": 900000}
    assert u["malos"]["ladoMax"] == 2576  # unos topes que no cuadran no se usan
    assert u["medidas"] == [{"ancho": 2000, "alto": 1500}, {"ancho": 800, "alto": 600}]
    assert u["pasos"] == [0.8, 0.7, 0.6, 0.5]
    assert u["avisos"] == [["pequena", "oscura"], []]
    assert u["porDefecto"] == [1, 3] and u["seleccionables"] == [1, 2, 3, 5]
    assert u["filtros"] == [5, 1, 1, 2, 1]
    assert u["estados"] == ["Leyendo… 7 filas", "Por revisar", "Carga parcial", "Sin filas por cargar",
                            "Cargada · importación #9"]

    # La sección: cámara trasera, galería con varias, el aviso fijo y la privacidad
    sec = s["seccion"]
    assert sec["camara"] == "environment" and sec["galeriaMultiple"] is True and sec["historial"] is True
    assert "No fotografíe cédulas" in sec["aviso"] and "Borre la foto del teléfono" in sec["aviso"]
    assert "a las 24 horas" in sec["privacidad"] and "declaradas en planilla" in sec["privacidad"]
    assert "Aún no hay fotos" in sec["vacia"]

    # La subida: JPEG crudo, reducida y sin metadatos; aviso de foto pequeña (1200 px)
    assert s["subida"]["estado"] == 201 and s["subida"]["tipo"] == "image/jpeg"
    assert s["subida"]["cuerpo"]["estado"] == "leyendo" and s["subida"]["cuerpo"]["ancho"] == 1200
    assert "Foto pequeña" in s["subidas"]
    pid = s["subida"]["cuerpo"]["id"]
    assert "Por revisar" in s["bandeja"]["texto"] and "4 filas" in s["bandeja"]["texto"]
    assert "Vereda inventada" in s["bandeja"]["texto"] and s["bandeja"]["boton"] == "Revisar"

    # Abierta: la foto (en canvas) y los valores completos; lo dudoso marcado y sin elegir; la fila «No autoriza» solo
    # con nombre, cédula y barrio
    a = s["abierta"]
    assert a["url"] == f"?planilla={pid}" and a["lienzo"] == [1200, 900, True]
    assert a["filas"] == [[1, "pendiente"], [2, "pendiente"], [3, "pendiente"], [4, "no_autoriza"]]
    assert a["ana"] == ["90000101", "3101234501", "Vive con su hija"]
    assert a["dudoso"] == "dudoso" and a["etiqueta"] == "Fila 2, Celular (dudoso)"
    assert a["no"] == ["CENOBIA INVENTADA PACHECO", "", "no"]
    assert a["elegidas"] == [1, 3, 4] and a["cargar"] == "Cargar 3 filas" and a["guardar"] is True and a["sinCrudo"]
    assert s["zoom"] == {"valor": "×1,5", "lienzo": [900, 1200]}

    # La corrección: una sola celda por PATCH; la fila queda corregida, limpia y elegida
    assert s["antesDeGuardar"] == "Guardar correcciones (1)"
    assert s["parche"] == {"estado": 200, "cuerpo": {"filas": [{"n": 2, "campo": "celular", "valor": "3101234502"}]}}
    assert s["corregida"] == {"valor": "3101234502", "elegida": True, "guardar": True}

    # El cotejo por fila
    c = s["cotejo"]
    assert "Ficha nueva" in c["1"] and "Ficha nueva" in c["2"] and "Completa una ficha" in c["3"]
    assert "Ficha nueva sin autorización" in c["4"] and "No autoriza" in c["4"]
    assert "llenaría" in s["cotejoDetalle"] and "Teléfono" in s["cotejoDetalle"]

    # La carga: el diálogo lo dice todo antes; la petición lleva las filas, el folio, el planillero y la clave
    d = s["dialogo"]
    assert "Cargar 3 filas" in d and "Carpeta 3, hoja 12" in d and "PEDRO PLANILLERO INVENTADO" in d
    assert "declaradas en planilla" in d and "se anota su «no»" in d
    assert s["carga"]["estado"] == 200 and s["carga"]["clave"] is True
    assert s["carga"]["cuerpo"] == {"filas": [1, 2, 4], "folio": "Carpeta 3, hoja 12", "capturado_por": pl["_id"]}
    res = s["resultado"]
    assert "importación #1" in res["texto"] and "Fila 1: Ficha nueva" in res["texto"]
    assert "Fila 4: Ficha nueva sin autorización" in res["texto"] and res["dialogo"] is False
    assert res["confirmar"] == "Confirmar 2 con el papel" and res["historial"] is True
    assert res["filas"] == [[1, "cargada"], [2, "cargada"], [3, "pendiente"], [4, "cargada"]]
    assert res["enlace"].startswith("/panel/personas/")
    assert s["desborde"] <= 0, s["anchos"]
    assert s["confirmadas"] == {"confirmadas": 2}
    assert "Cargada · importación #2" in s["final"]["chip"] and s["final"]["sinFoto"] is True
    assert s["final"]["filas"] == [[1, "cargada"], [2, "cargada"], [3, "cargada"], [4, "cargada"]]
    assert s["final"]["acciones"] is False
    assert s["cerrada"] == {"oculta": True, "url": ""}

    # En la base: dos importaciones de la foto con su folio, el planillero y la huella; los «sí» declarados y luego
    # confirmados; el «no» sin más datos; la corrección guardada; la planilla cargada y sin foto ni lectura
    imps = list(db.importaciones.find().sort("_id", 1))
    doc = db.planillas.find_one({"_id": pid})
    assert [i["archivo"] for i in imps] == ["Foto de planilla física"] * 2
    assert all(i["folio"] == "Carpeta 3, hoja 12" and i["fotos_sha256"] == [doc["sha256"]] for i in imps)
    assert imps[0]["capturado_por"] == pl["_id"]
    assert doc["estado"] == "cargada" and doc["foto"] is None and doc["lectura"] is None
    ana = db.personas.find_one({"cedula": "90000101"})
    berta = db.personas.find_one({"cedula": "90000202"})
    cenobia = db.personas.find_one({"cedula": "90000131"})
    assert ana["consentimiento"] == "si" and ana["contacto_habilitado"] is True  # confirmada con el papel
    assert [t["numero"] for t in berta["telefonos"]] == ["3101234502"]
    eventos = list(db.autorizaciones.find({"persona_id": ana["_id"]}).sort("_id", 1))
    assert eventos[0]["medio"] == "declarado_planilla" and eventos[-1]["confirmada_por"] == 0
    assert cenobia["consentimiento"] == "no" and not cenobia.get("telefonos") and not cenobia.get("direccion")
    assert any(t["numero"] == "3101234503" for t in db.personas.find_one({"_id": carmen})["telefonos"])

    # El planillero: ni la sección, ni la cámara, ni el aviso, ni una petición a la bandeja; sin desborde
    p = s["p"]
    assert p["secciones"] == [] and p["galeria"] is False and p["aviso"] is False and p["pedidas"] == []
    assert p["desborde"] <= 0
    assert db.planillas.count_documents({"uid": pp["_id"]}) == 0


GUION_CASOS = r"""const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, foto1, foto2, rutaSenal] = process.argv.slice(2);
const fs = require('fs');
const espera = { timeout: 25000 };
const presente = { state: 'attached', timeout: 25000 };
const salida = { errores: [], csp: [] };
const textoDe = (pg, sel) => pg.evaluate((s) => (document.querySelector(s)?.textContent || '').replace(/\s+/g, ' ').trim(), sel);
const item = (n) => `#pf-bandeja .pf-item:nth-child(${n})`;

(async () => {
  const nav = await chromium.launch();
  const ctx = await nav.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
  });
  await ctx.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort());
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/401|403|Failed to load resource|fonts\.g/.test(m.text())) salida.errores.push(m.text()); });
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.goto(base + '/importar', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#pf-bandeja .pf-vacia', espera);

  // 1. La lectura falla: «Falló la lectura» con su motivo y «Volver a leer», que la lee de nuevo
  await page.setInputFiles('#pf-galeria-in', foto1);
  await page.waitForFunction(() => /Falló la lectura/.test(document.querySelector('#pf-bandeja .pf-item')?.textContent || ''), null, espera);
  salida.fallida = await textoDe(page, '#pf-bandeja .pf-item');
  await page.click('#pf-bandeja [data-releer]');
  await page.waitForFunction(() => /Por revisar/.test(document.querySelector('#pf-bandeja .pf-item')?.textContent || ''), null, espera);
  salida.releida = await textoDe(page, '#pf-bandeja .pf-item');

  // 2. Otra foto con la lectura cortada: «Leer desde la fila 3» lee el resto y conserva lo de antes
  await page.setInputFiles('#pf-galeria-in', foto2);
  await page.waitForFunction(() => /lectura incompleta/.test(document.querySelector('#pf-bandeja .pf-item')?.textContent || ''), null, espera);
  await page.click(`${item(1)} [data-abrir]`);
  await page.waitForSelector('[data-releer-desde]', espera);
  salida.incompleta = { aviso: await textoDe(page, '#planilla-abierta .aviso-legal'),
    filas: await page.$$eval('.pf-tabla tbody tr', (t) => t.map((x) => Number(x.dataset.n))) };
  await page.click('[data-releer-desde]');
  await page.waitForFunction(() => document.querySelectorAll('.pf-tabla tbody tr').length === 4, null, espera);
  salida.completa = { filas: await page.$$eval('.pf-tabla tbody tr', (t) => t.map((x) => Number(x.dataset.n))),
    sinBoton: await page.evaluate(() => !document.querySelector('[data-releer-desde]')),
    releer: await page.evaluate(() => !!document.querySelector('#pf-releer')) };

  // 3. Descartar una fila (sale de lo elegido) y recuperarla (no se elige sola: fue una decisión)
  salida.antes = await textoDe(page, '#pf-cargar');
  await page.click('.pf-tabla tr[data-n="1"] [data-descartar]');
  await page.waitForFunction(() => document.querySelector('.pf-tabla tr[data-n="1"]')?.dataset.estado === 'descartada', null, espera);
  salida.descartada = { cargar: await textoDe(page, '#pf-cargar'),
    casilla: await page.evaluate(() => !!document.querySelector('[data-elegir="1"]')),
    entradas: await page.evaluate(() => [...document.querySelectorAll('.pf-tabla tr[data-n="1"] .pf-entrada')].every((x) => x.disabled)) };
  await page.click('.pf-tabla tr[data-n="1"] [data-restaurar]');
  await page.waitForFunction(() => document.querySelector('.pf-tabla tr[data-n="1"]')?.dataset.estado === 'pendiente', null, espera);
  salida.recuperada = { cargar: await textoDe(page, '#pf-cargar'),
    elegida: await page.evaluate(() => document.querySelector('[data-elegir="1"]').checked) };
  // «Elegir: todas» y «ninguna»
  await page.click('[data-elegir-grupo="ninguna"]');
  salida.ninguna = { cargar: await textoDe(page, '#pf-cargar'), deshabilitado: await page.evaluate(() => document.querySelector('#pf-cargar').disabled) };
  await page.click('[data-elegir-grupo="todas"]');
  salida.todas = await textoDe(page, '#pf-cargar');
  // Una corrección sin guardar: al cargar sin folio, no se manda nada y se pide el folio
  await page.fill('.pf-tabla tr[data-n="3"] .pf-entrada[data-campo="barrio"]', 'BARRIO CORREGIDO');
  await page.click('#pf-cargar');
  salida.sinFolio = { dialogo: await page.evaluate(() => !!document.querySelector('dialog[open]')),
    foco: await page.evaluate(() => document.activeElement?.id), guardar: await textoDe(page, '#pf-guardar') };
  // Escape devuelve la celda a lo leído
  await page.focus('.pf-tabla tr[data-n="3"] .pf-entrada[data-campo="barrio"]');
  await page.keyboard.press('Escape');
  salida.escape = { valor: await page.inputValue('.pf-tabla tr[data-n="3"] .pf-entrada[data-campo="barrio"]'), guardar: await textoDe(page, '#pf-guardar') };

  // 4. Borrar la primera foto desde la bandeja (con confirmación)
  await page.click('#pf-bandeja .pf-item:nth-child(2) [data-borrar]');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  salida.borrarTexto = await textoDe(page, 'dialog[open]');
  await page.click('dialog[open] [data-si]');
  await page.waitForFunction(() => document.querySelectorAll('#pf-bandeja .pf-item').length === 1, null, espera);

  // 5. El rol deja de subir fotos (Ajustes): la subida se oculta y lo dice; la bandeja sigue
  fs.writeFileSync(rutaSenal, 'rol');
  for (let i = 0; i < 100 && fs.existsSync(rutaSenal); i++) await page.waitForTimeout(100);
  await page.goto(base + '/importar', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#pf-bandeja .pf-item', espera);
  salida.sinRol = await page.evaluate(() => ({ subir: document.querySelector('#pf-subir').hidden,
    aviso: document.querySelector('#pf-sin-subida').hidden ? '' : document.querySelector('#pf-sin-subida').textContent,
    bandeja: document.querySelectorAll('#pf-bandeja .pf-item').length }));
  salida.csp = await page.evaluate(() => window.__csp);
  console.log(JSON.stringify(salida));
  await nav.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
def test_planillas_por_foto_casos_en_chromium(panel_web, cfg, tmp_path, monkeypatch):
    base, panel = panel_web
    db = panel.state.db
    filas = [fila(1, **ANA), fila(2, **BERTA), fila(3, **CARMEN), fila(4, **DORA)]
    proveedor = ProveedorFalso(
        RuntimeError("caída inventada"),                         # foto 1: falla
        lectura_json([fila(1, **ANA)]),                          # foto 1, releída
        (lectura_json(filas[:2], visibles=4), "max_tokens"),     # foto 2: se corta en la fila 2 de 4
        lectura_json(filas[2:], visibles=4))                     # foto 2, desde la fila 3
    encender(monkeypatch, panel, proveedor, de_fondo=True)
    foto1, foto2, senal = tmp_path / "uno.jpg", tmp_path / "dos.jpg", tmp_path / "senal"
    foto1.write_bytes(jpeg(1700, 1200))
    foto2.write_bytes(jpeg(1800, 1300))
    (tmp_path / "casos.cjs").write_text(GUION_CASOS, encoding="utf-8")
    proceso = subprocess.Popen(["node", str(tmp_path / "casos.cjs"), base, cfg.usuario, cfg.clave, str(foto1),
                                str(foto2), str(senal)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Cuando el guion lo pide, el administrador saca su rol de los que suben fotos (como en Ajustes)
    fin = time.time() + 240
    while proceso.poll() is None and time.time() < fin:
        if senal.exists():
            db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas.roles": ["coordinador"]}})
            senal.unlink()
        time.sleep(0.1)
    salida, errores = proceso.communicate(timeout=60)
    assert proceso.returncode == 0, (salida[-3000:], errores[-3000:])
    s = json.loads(salida.strip().splitlines()[-1])
    assert s["errores"] == [] and s["csp"] == [], (s["errores"], s["csp"])
    assert "Falló la lectura" in s["fallida"] and "Falló el modelo falso" in s["fallida"]
    assert "Volver a leer" in s["fallida"]
    assert "Por revisar" in s["releida"] and "1 fila" in s["releida"] and "Volver a leer" not in s["releida"]
    assert "La lectura quedó incompleta: llegó hasta la fila 2 de 4" in s["incompleta"]["aviso"]
    assert s["incompleta"]["filas"] == [1, 2]
    assert s["completa"]["filas"] == [1, 2, 3, 4] and s["completa"]["sinBoton"] is True
    assert s["completa"]["releer"] is False  # ya se leyó 2 veces
    assert s["antes"] == "Cargar 4 filas"
    assert s["descartada"] == {"cargar": "Cargar 3 filas", "casilla": False, "entradas": True}
    assert s["recuperada"] == {"cargar": "Cargar 3 filas", "elegida": False}
    assert s["ninguna"] == {"cargar": "Cargar filas", "deshabilitado": True} and s["todas"] == "Cargar 4 filas"
    assert s["sinFolio"] == {"dialogo": False, "foco": "pf-folio", "guardar": "Guardar correcciones (1)"}
    assert s["escape"] == {"valor": "TRES DE OCTUBRE", "guardar": "Guardar correcciones"}
    assert "¿Borrar esta planilla?" in s["borrarTexto"]
    assert s["sinRol"]["subir"] is True and "Su rol no sube fotos de planillas" in s["sinRol"]["aviso"]
    assert s["sinRol"]["bandeja"] == 1
    # Lo corregido sin guardar nunca llegó al servidor; la primera foto ya no está
    assert db.planillas.count_documents({}) == 1 and len(proveedor.llamadas) == 4
    assert not db.importaciones.find_one()
