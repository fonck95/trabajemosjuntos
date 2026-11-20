"""La pantalla completa de la vista Presentación en la pestaña del chat (web/js/vistas/presentacion.js y
css/presentacion.css), con el asistente a la vista.

Antes, «Pantalla completa» le pedía al navegador la pantalla completa solo para el marco de la presentación: el
asistente (su botón, su panel, el dictado) quedaba fuera y no se veía. Y la orden `pantalla_completa` del asistente
llenaba la ventana con su botón arriba a la derecha, encima de «Atlas» de la presentación. Ahora:

* «Pantalla completa» de la barra llena la ventana (html[data-pres-llena]: sin el menú ni las barras del panel) y le
  pide al navegador la pantalla completa con la página entera; si no la da (el iPhone, un permiso), queda llena igual.
* El botón del asistente flota abajo a la izquierda (como en el proyector) y «Salir de pantalla completa» a su lado; en
  el celular, los dos en la barra de arriba de la presentación, entre su marca y sus herramientas. Se atenúan con el
  ratón quieto. Abierto el asistente en escritorio, es una columna a la derecha sobre negro, con «Salir» encima.
* Se sale con ese botón, saliendo de la del navegador, con la orden del asistente (`activar: false`) o con Escape: con la
  del navegador, Escape es suyo y sale de una vez (la página no lo ve: Playwright no lo puede probar, sus teclas llegan
  directo a la página); sin ella, el primero con el chat abierto es del chat, también con el foco en la presentación.
  El botón de pantalla completa de la propia presentación y su tecla F hacen lo mismo (con su documento del mismo
  origen); si el navegador no la dio, salen en vez de pedirla otra vez, y la F no hace nada con sus fichas abiertas.
* Con el celular de lado la barra de la vista no se ve: «Pantalla completa» va en la barra del panel, junto al botón
  del asistente.
* La franja «Llamada sin registrar» no tapa la presentación llena.

Por texto (el código y el CSS) y en Chromium con el panel y la presentación de verdad (el servidor único y el sitio que
arma build_site.py), en escritorio y en el celular. Solo datos inventados: la presentación es pública."""
import json
import os
import re
import subprocess
from pathlib import Path

from test_agente_presentacion import _codigo, panel_con_sitio, requiere_navegador  # noqa: F401  (el fixture)

ADMIN = Path(__file__).resolve().parents[1]
WEB = ADMIN / "web"
VISTA_JS = WEB / "js" / "vistas" / "presentacion.js"
CSS = WEB / "css" / "presentacion.css"


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _bloque(texto: str, desde: str, hasta: str) -> str:
    i = texto.index(desde)
    return texto[i:texto.index(hasta, i)]


# ───────────────────────────── La vista, por texto ─────────────────────────────

def test_la_pestana_pide_la_pantalla_completa_con_la_pagina_entera_y_llena_la_ventana():
    vista = VISTA_JS.read_text(encoding="utf-8")
    codigo = _codigo(vista)
    # ya no se pide para el marco (el asistente quedaba fuera)
    assert "marco).requestFullscreen" not in codigo and "marco.requestFullscreen" not in codigo
    assert "const pestana = !proyector && !off;" in codigo
    # el botón de la barra, solo en la pestaña y siempre (sin la API del navegador, igual llena la ventana)
    assert "${pestana ? html`<button type=\"button\" class=\"btn\" id=\"pres-pantalla\"" in vista
    assert "${conPantalla ? html`<button type=\"button\" class=\"btn\" id=\"pres-pantalla\"" not in vista
    # entrar: llena la ventana y pide la del navegador con la página entera; si la rechaza, queda llena
    poner = _bloque(codigo, "function pedirCompleta() {", "\n  }\n")
    assert "if (!conCompleta() || document.fullscreenElement) return;" in poner
    assert "completaPropia = true;" in poner
    assert "raiz.requestFullscreen({ navigationUI: 'hide' })?.catch?.(rechazada);" in poner
    assert "function ponerCompleta() { llenar(true); pedirCompleta(); }" in codigo
    assert ("const conCompleta = () => pestana && !!document.fullscreenEnabled && typeof raiz.requestFullscreen === "
            "'function';") in codigo
    # salir: la ventana vuelve y, en la pestaña, la del navegador también
    salir = _bloque(codigo, "function salirDeLlena() {", "\n  }\n")
    assert "llenar(false);" in salir
    assert "if (pestana && document.fullscreenElement === raiz) document.exitFullscreen?.()?.catch?.(() => {});" in salir
    # Escape (el que no usó el asistente) sale de las dos
    assert ("const alTecla = (e) => { if (e.key === 'Escape' && !e.defaultPrevented && 'presLlena' in raiz.dataset) "
            "salirDeLlena(); };") in codigo
    # el navegador sale de la suya (su Escape, su aviso): la ventana vuelve, si la pidió esta vista
    cambio = _bloque(codigo, "const alCambiarCompleta = () => {", "\n    };\n")
    assert "if (document.fullscreenElement || !completaPropia) return;" in cambio and "llenar(false);" in cambio
    # (y si la persona salió mientras el navegador se la estaba dando, se suelta: no queda el panel a pantalla completa)
    assert ("if (document.fullscreenElement === raiz && completaPropia && !('presLlena' in raiz.dataset)) {\n"
            "        document.exitFullscreen?.()?.catch?.(() => {});") in cambio
    assert "document.addEventListener('fullscreenchange', alCambiarCompleta);" in codigo
    assert "document.removeEventListener('fullscreenchange', alCambiarCompleta);" in codigo
    # y la vista que se va (el asistente abrió otra) suelta la que pidió
    assert "if (completaPropia && document.fullscreenElement === raiz) document.exitFullscreen?.()?.catch?.(() => {});" in codigo
    # el botón: entra y el teclado va a la presentación
    boton = _bloque(codigo, "$('#pres-pantalla', el).addEventListener('click', () => {", "\n    });")
    assert "ponerCompleta();" in boton and "if (lista) iframe.focus({ preventScroll: true });" in boton
    # el proyector sigue con la ventana entera (su botón flotante), sin llenar nada
    pantalla = _bloque(codigo, "const pantalla = () => {", "\n  };\n")
    assert "else document.documentElement.requestFullscreen?.().catch(() => {});" in pantalla


def test_salir_de_pantalla_completa_flota_en_la_pestana_y_devuelve_el_foco():
    vista = VISTA_JS.read_text(encoding="utf-8")
    codigo = _codigo(vista)
    i = vista.index('id="pres-salir"')
    boton = vista[vista.rindex("${pestana ? html`<button", 0, i):vista.index("</button>", i)]
    # solo en la pestaña (el proyector y la pantalla en off tienen lo suyo), con nombre y su atajo en el título
    assert 'class="pres-salir"' in boton and 'title="Salir de pantalla completa (Escape)"' in boton
    assert '<span class="sr">Salir de pantalla completa</span>' in boton and 'aria-hidden="true"' in boton
    salir = _bloque(codigo, "$('#pres-salir', el).addEventListener('click', () => {", "\n    });")
    assert salir.index("salirDeLlena();") < salir.index("$('#pres-pantalla', el).focus({ preventScroll: true });")


def test_la_orden_del_asistente_pide_la_del_navegador_solo_con_un_gesto_reciente():
    codigo = _codigo(VISTA_JS.read_text(encoding="utf-8"))
    orden = _bloque(codigo, "if (p.op === 'pantalla_completa') {", "continue;")
    assert "if (!p.activar) salirDeLlena();" in orden
    assert "else if (globalThis.navigator?.userActivation?.isActive) ponerCompleta();" in orden
    assert "else llenar(true);" in orden and "res.push({ op: p.op, ok: true });" in orden
    # en el proyector `llenar` no llena y `conCompleta` es falso: no cambia nada allá
    assert "const llenar = (v) => { if (v && !proyector) raiz.dataset.presLlena = ''; else delete raiz.dataset.presLlena; };" in codigo


def test_el_boton_y_la_tecla_f_de_la_presentacion_hacen_lo_mismo_que_el_de_la_barra():
    codigo = _codigo(VISTA_JS.read_text(encoding="utf-8"))
    t = _bloque(codigo, "let engancharCompleta = () => {};\n  if (pestana) {", "\n  }\n\n")
    # su botón (mando.js no lo reenvía: main.js pedía la pantalla completa para su documento, el marco)
    assert "if (!e.target?.closest?.('[data-accion=\"pantalla\"]')) return;" in t
    clic = _bloque(t, "const alClicDentro = (e) => {", "};")
    assert clic.index("e.stopImmediatePropagation();") < clic.index("alternarCompleta();")
    # la tecla F (no repetida, sin modificadores, fuera de un campo), y Escape cuando la presentación no lo usa
    tecla = _bloque(t, "const alTeclaDentro = (e) => {", "\n    };")
    assert "if (e.defaultPrevented || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;" in tecla
    assert "if (e.key === 'f' || e.key === 'F') {" in tecla and "if (!e.repeat) alternarCompleta();" in tecla
    # (con sus fichas abiertas la presentación no usa la F: aquí tampoco se toma)
    f = _bloque(tecla, "if (e.key === 'f' || e.key === 'F') {", "} else if")
    assert f.index("if (doc?.querySelector('.fichas:not([hidden])')) return;") < f.index("e.stopImmediatePropagation();")
    # Escape: su índice o sus fichas los cierra ella; con el chat abierto es del chat (su cadena: lo que oye, lo que lee,
    # cerrarse), aunque el foco esté en la presentación; si no, sale
    esc = tecla[tecla.index("} else if (e.key === 'Escape' && 'presLlena' in raiz.dataset) {"):]
    assert esc.index("if (doc?.querySelector('.indice:not([hidden]), .fichas:not([hidden])')) return;") < esc.index(
        "const chat = document.getElementById('agente-panel');") < esc.index("salirDeLlena();")
    assert ("if (chat && !chat.hidden) {\n          e.preventDefault();\n          chat.dispatchEvent(new KeyboardEvent("
            "'keydown', { key: 'Escape', bubbles: true, cancelable: true }));\n          return;\n        }") in esc
    # en captura sobre su ventana (antes que main.js), una vez por documento, y se quitan al irse
    assert "for (const [t, f] of dentro) { try { w?.addEventListener(t, f, true); } catch { return; } }" in t
    assert "ventanaCompleta?.removeEventListener(t, f, true);" in t
    assert "escuchar(ventanaIframe, true);\n      engancharCompleta(ventanaIframe);" in codigo
    # alternar: con la del navegador (o ya llena sin poder pedirla: sin la API o porque la rechazó) sale; si no, entra
    alternar = _bloque(codigo, "const alternarCompleta = () => {", "\n  };")
    assert ("if (document.fullscreenElement === raiz || ('presLlena' in raiz.dataset && (!conCompleta() || "
            "completaRechazada))) {\n      salirDeLlena();\n    } else ponerCompleta();") in alternar
    # el rechazo se recuerda hasta salir o pedirla otra vez
    poner = _bloque(codigo, "function pedirCompleta() {", "\n  }\n")
    assert "completaRechazada = false;" in poner
    assert "const rechazada = () => { completaPropia = false; completaRechazada = true; };" in poner
    assert "raiz.requestFullscreen({ navigationUI: 'hide' })?.catch?.(rechazada);" in poner and "} catch { rechazada(); }" in poner
    assert "completaRechazada = false;" in _bloque(codigo, "function salirDeLlena() {", "\n  }\n")


def test_los_botones_flotantes_se_atenuan_tambien_en_la_pestana():
    codigo = _codigo(VISTA_JS.read_text(encoding="utf-8"))
    # el reloj del ratón quieto ya no es solo del proyector y de la pantalla en off
    assert "if (proyector || off) {\n    let ultima = 0" not in codigo
    q = codigo[codigo.index("  {\n    let ultima = 0"):]
    assert "raiz.dataset.presQuieto = '';" in q[:600]


# ───────────────────────────── El CSS ─────────────────────────────

def test_el_css_de_la_pestana_a_pantalla_completa():
    css = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    boton = "html[data-pres-llena]:not([data-pres-off]) body:has(#vista .presentacion) #agente #agente-boton"
    # el botón del asistente abajo a la izquierda (arriba a la derecha tapaba «Atlas» de la presentación) y «Salir» a su
    # lado; sin el botón del asistente, en su lugar
    assert f"{boton} {{\n  top: auto; right: auto; left: 14px; bottom: 14px; width: 42px; height: 42px; }}" in css
    assert ".pres-salir { display: none; }" in css
    assert re.search(r"html\[data-pres-llena\] \.pres-salir \{ position: fixed; z-index: 6; left: 64px; bottom: 14px; "
                     r"display: grid;", css)
    assert "html[data-pres-llena] body:not(:has(#agente-boton:not([hidden]))) .pres-salir { left: 14px; }" in css
    # en el celular, en la barra de la presentación, entre su marca (51 px desde el borde) y sus herramientas
    celular = _bloque(css, "@media (max-width: 640px), (max-width: 1080px) and (orientation: landscape) and "
                           "(max-height: 560px) {\n  html[data-pres-llena]", "\n}\n")
    assert "top: calc(7px + env(safe-area-inset-top, 0px)); bottom: auto;" in celular
    assert "left: calc(max(16px, env(safe-area-inset-left, 0px)) + 60px); }" in celular
    assert "html[data-pres-llena] .pres-salir { left: calc(max(16px, env(safe-area-inset-left, 0px)) + 108px); }" in celular
    # atenuados con el ratón quieto, salvo con el ratón encima o el foco del teclado
    assert (f"html[data-pres-llena]:not([data-pres-off])[data-pres-quieto] body:has(#vista .presentacion) #agente "
            f"#agente-boton:not(:hover):not(:focus-visible),\nhtml[data-pres-llena][data-pres-quieto] "
            f".pres-salir:not(:hover):not(:focus-visible) {{ opacity: .18; }}") in css
    # abierto en escritorio: una columna sobre el negro de la presentación, con «Salir» encima y con su nombre
    escritorio = _bloque(css, "@media (min-width: 901px) {\n  html[data-pres-llena]:not([data-pres-off]) .presentacion",
                         "\n}\n")
    assert "html[data-pres-llena]:not([data-pres-off]) .presentacion { background: #000; }" in escritorio
    assert "html[data-pres-llena]:not([data-pres-off]) #agente #agente-panel { top: 78px; height: auto; }" in escritorio
    assert "left: auto; bottom: auto; top: 24px; right: 24px;" in escritorio and "opacity: 1; }" in escritorio
    assert "position: static; width: auto; height: auto; overflow: visible; clip: auto; }" in escritorio
    # la franja «Llamada sin registrar» no tapa la barra de la presentación; el panel del celular, desde el borde
    assert "html[data-pres-llena] #franja-llamada { display: none; }" in css
    assert "html[data-pres-llena] #agente #agente-panel { top: 0; }" in css
    # la presentación entra desde el negro, sin animación con movimiento reducido
    assert "html[data-pres-llena]:not([data-pres-off]) .pres-marco iframe { animation: pres-llena .35s ease-out; }" in css
    reducido = css[css.index("@keyframes pres-llena"):]
    reducido = reducido[reducido.index("@media (prefers-reduced-motion: reduce) {"):]
    assert "animation: none; transition: none; }" in reducido[:400]
    # el marco ya no va solo a pantalla completa
    assert ".pres-marco:fullscreen" not in css
    # el celular de lado: la barra de la vista no se ve, salvo «Pantalla completa» de la pestaña, que pasa a la barra del
    # panel a la izquierda del botón del asistente (sin él, en su lugar), y no en la pantalla llena ni en las otras dos
    lado = _bloque(css, "@media (max-width: 900px) and (orientation: landscape) and (max-height: 560px) {\n  "
                        ".presentacion:not(.proyector) .pres-barra { display: none; }", "\n}\n")
    assert ("html:not([data-pres-llena]) .presentacion:not(.proyector):not(.en-off) .pres-barra:has(#pres-pantalla),\n"
            "  html:not([data-pres-llena]) .presentacion:not(.proyector):not(.en-off) .pres-barra .pres-botones "
            "{ display: contents; }") in lado
    assert ".presentacion:not(.proyector) .pres-barra .pres-botones > :not(#pres-pantalla) { display: none; }" in lado
    assert "top: calc(10px + env(safe-area-inset-top, 0px)); right: 60px;" in lado and "width: 40px;" in lado
    assert ("body:not(:has(#agente-boton:not([hidden]))) .presentacion:not(.proyector) .pres-barra #pres-pantalla "
            "{ right: 12px; }") in lado
    # el proyector y la pantalla en off quedan como estaban
    assert "html[data-proyector] #agente #agente-boton { top: auto; right: auto; left: 14px; bottom: 14px;" in css
    assert ("body:has(#vista .presentacion:not(.proyector)):has(#agente) .agente-boton { top: 9px; bottom: auto; "
            "right: 16px;") in css


# ───────────────────────────── En Chromium ─────────────────────────────

GUION = r"""// La pestaña del chat a pantalla completa, con el asistente. Uso: node <guion> <base del panel> <usuario> <clave>
// <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const espera = { timeout: 90000 };
const salida = { csp: [], errores: [] };

async function contexto(nav, opciones) {
  const ctx = await nav.newContext(opciones);
  await ctx.route((u) => u.origin !== origen, (r) => r.abort());   // sin internet
  await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective} ${e.blockedURI}`), true);
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.goto(base + '/presentacion', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  await page.evaluate(async () => { window.__P = await import(new URL('agente-presentacion.js', document.querySelector('script[type=module]').src).href); });
  await page.waitForFunction(() => window.__P.presentacionLista(), null, espera);
  return { ctx, page };
}

// Un toque de verdad en el centro de lo que se ve (con el ratón o el dedo): el navegador lo cuenta como gesto
async function tocar(page, sel, { marco = null, dedo = false } = {}) {
  const b = await (marco || page).locator(sel).boundingBox();
  if (!b) throw new Error(`no se ve ${sel}`);
  if (dedo) await page.touchscreen.tap(b.x + b.width / 2, b.y + b.height / 2);
  else await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
}
const marcoDe = (page) => page.frames().find((f) => /\/propuesta(\?[^#]*)?(#|$)/.test(f.url()));
// Lo que se ve: el estado, lo que está a pantalla completa, el foco y las cajas (las de la presentación, en la página)
const mirar = (page) => page.evaluate(() => {
  const caja = (e, dx = 0, dy = 0) => {
    if (!e) return null;
    const s = getComputedStyle(e);
    const b = e.getBoundingClientRect();
    if (!b.width || !b.height || s.display === 'none' || s.visibility === 'hidden') return null;
    return { l: Math.round(b.left + dx), t: Math.round(b.top + dy), r: Math.round(b.right + dx), b: Math.round(b.bottom + dy) };
  };
  const f = document.getElementById('pres-iframe');
  const o = f.getBoundingClientRect();
  const d = f.contentDocument;
  const dentro = (s) => caja(d?.querySelector(s), o.left, o.top);
  const fe = document.fullscreenElement;
  return {
    llena: 'presLlena' in document.documentElement.dataset,
    completa: fe ? (fe.id || fe.tagName) : null,
    foco: document.activeElement?.id || document.activeElement?.tagName || null,
    w: innerWidth, h: innerHeight,
    lateral: caja(document.querySelector('.lateral')), barraMovil: caja(document.querySelector('.barra-movil')),
    barra: caja(document.querySelector('.pres-barra')), iframe: caja(f),
    boton: caja(document.getElementById('agente-boton')), salir: caja(document.getElementById('pres-salir')),
    panel: caja(document.getElementById('agente-panel')),
    salirNombre: document.getElementById('pres-salir')?.textContent.trim() || null,
    salirOpacidad: getComputedStyle(document.getElementById('pres-salir')).opacity,
    botonOpacidad: getComputedStyle(document.getElementById('agente-boton')).opacity,
    fondo: getComputedStyle(document.querySelector('.presentacion')).backgroundColor,
    herr: dentro('.barra .herr'), marca: dentro('.barra .marca'), control: dentro('.control'), hoja: dentro('.panel'),
  };
});
const hasta = (page, f, arg) => page.waitForFunction(f, arg, { timeout: 30000 }).then(() => true, () => false);
const llena = (page, v) => hasta(page, (v) => ('presLlena' in document.documentElement.dataset) === v, v);
const completa = (page, v) => hasta(page, (v) => (document.fullscreenElement === document.documentElement) === v, v);
const capturar = (page, nombre) => page.screenshot({ path: `${capturas}/pantalla-completa-${nombre}.png`, timeout: 30000 }).catch(() => {});

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  try {
    // ── Escritorio ──
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 1440, height: 900 } });
      const e = salida.escritorio = {};
      e.antes = await mirar(page);
      // «Pantalla completa»: la ventana llena y la pantalla completa del navegador con la página entera
      await tocar(page, '#pres-pantalla');
      e.entra = [await llena(page, true), await completa(page, true)];
      e.lleno = await mirar(page);
      await capturar(page, 'escritorio');
      // con el ratón quieto los dos botones se atenúan, y vuelven al moverlo
      e.seAtenua = await hasta(page, () => 'presQuieto' in document.documentElement.dataset
        && parseFloat(getComputedStyle(document.getElementById('pres-salir')).opacity) < 0.25
        && parseFloat(getComputedStyle(document.getElementById('agente-boton')).opacity) < 0.25);
      await page.mouse.move(700, 400, { steps: 3 });
      e.vuelve = await hasta(page, () => parseFloat(getComputedStyle(document.getElementById('pres-salir')).opacity) > 0.9);
      // el asistente se abre al lado, sin salir de la pantalla completa
      await tocar(page, '#agente-boton');
      await page.waitForSelector('#agente-panel:not([hidden])', espera);
      await page.waitForTimeout(1200);
      e.chat = await mirar(page);
      await capturar(page, 'escritorio-chat');
      // (con la del navegador, Escape es del navegador y sale de una vez: las teclas de Playwright llegan directo a la
      // página y no lo pueden probar. El chat se cierra con su X; la pantalla completa sigue)
      await tocar(page, '#agente-cerrar');
      e.xCierraElChat = await hasta(page, () => document.getElementById('agente-panel').hidden);
      e.trasX = await mirar(page);
      // «Salir de pantalla completa»: vuelve todo y el foco queda en el botón que la abre
      await page.mouse.move(80, 860, { steps: 2 });
      await tocar(page, '#pres-salir');
      e.sale = [await llena(page, false), await completa(page, false)];
      e.fuera = await mirar(page);
      // otra vez, y el navegador sale de la suya (su Escape, su aviso): la ventana vuelve
      await tocar(page, '#pres-pantalla');
      e.otraVez = [await llena(page, true), await completa(page, true)];
      await page.evaluate(() => document.exitFullscreen());
      e.navegadorSale = await llena(page, false);
      // el botón de la presentación (su pantalla completa era la del marco) hace lo mismo que el de la barra; su F sale
      const m = marcoDe(page);
      await tocar(page, '.herr [data-accion="pantalla"]', { marco: m });
      e.suBoton = [await llena(page, true), await completa(page, true)];
      e.suBotonEs = (await mirar(page)).completa;
      await page.evaluate(() => document.getElementById('pres-iframe').focus());
      await page.keyboard.press('f');
      e.suTeclaF = [await llena(page, false), await completa(page, false)];
      // el navegador no la da (el iPhone, un permiso): queda llena; Escape en la presentación la devuelve
      await page.evaluate(() => {
        window.__rf = Element.prototype.requestFullscreen;
        Element.prototype.requestFullscreen = function () { return Promise.reject(new TypeError('sin permiso')); };
      });
      await tocar(page, '#pres-pantalla');
      e.rechazada = await llena(page, true);
      await page.waitForTimeout(1500);
      e.rechazadaMira = await mirar(page);
      e.rechazadaFoco = await page.evaluate(() => document.activeElement?.id);
      // su F alterna: llena y rechazada, sale (no la vuelve a pedir); otra vez, entra
      await page.keyboard.press('f');
      e.rechazadaFSale = await llena(page, false);
      await page.evaluate(() => document.getElementById('pres-iframe').focus());
      await page.keyboard.press('f');
      e.rechazadaFEntra = await llena(page, true);
      // con el chat abierto, el primer Escape es del chat (con el foco en él, o en la presentación) y la ventana sigue
      // llena; el siguiente sale
      await tocar(page, '#agente-boton');
      await page.waitForSelector('#agente-panel:not([hidden])', espera);
      await page.focus('#agente-texto');
      await page.keyboard.press('Escape');
      e.escapeEnElChat = await hasta(page, () => document.getElementById('agente-panel').hidden);
      e.trasEscapeEnElChat = (await mirar(page)).llena;
      await tocar(page, '#agente-boton');
      await page.waitForSelector('#agente-panel:not([hidden])', espera);
      await page.evaluate(() => document.getElementById('pres-iframe').focus());
      e.focoEnLaPresentacion = await page.evaluate(() => document.activeElement?.id);
      await page.keyboard.press('Escape');
      e.escapeEnLaPresentacion = await hasta(page, () => document.getElementById('agente-panel').hidden);
      e.trasEscapeEnLaPresentacion = (await mirar(page)).llena;
      await capturar(page, 'escape-chat');
      await page.keyboard.press('Escape');
      e.rechazadaEscape = await llena(page, false);
      // con sus fichas abiertas, su F no hace nada (como en la presentación sola)
      await tocar(page, '.herr [data-accion="fichas"]', { marco: marcoDe(page) });
      e.fichas = await hasta(page, () => !!document.getElementById('pres-iframe').contentDocument.querySelector('.fichas:not([hidden])'));
      await page.evaluate(() => document.getElementById('pres-iframe').focus());
      await page.keyboard.press('f');
      await page.waitForTimeout(600);
      e.fConFichas = await page.evaluate(() => ({ llena: 'presLlena' in document.documentElement.dataset,
        fichas: !!document.getElementById('pres-iframe').contentDocument.querySelector('.fichas:not([hidden])') }));
      await page.keyboard.press('Escape');
      await hasta(page, () => !document.getElementById('pres-iframe').contentDocument.querySelector('.fichas:not([hidden])'));
      await page.evaluate(() => { Element.prototype.requestFullscreen = window.__rf; });
      // la orden del asistente: llena (y, con un gesto reciente, la del navegador); `activar: false` sale de las dos
      await page.evaluate(() => window.__P.accionesPresentacion([{ tipo: 'presentacion', op: 'pantalla_completa', activar: true }]));
      e.orden = await llena(page, true);
      await page.evaluate(() => window.__P.accionesPresentacion([{ tipo: 'presentacion', op: 'pantalla_completa', activar: false }]));
      e.ordenSale = [await llena(page, false), await completa(page, false)];
      await ctx.close();
    }
    // ── Celular ──
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      const c = salida.celular = {};
      await tocar(page, '#pres-pantalla', { dedo: true });
      c.entra = await llena(page, true);
      await page.waitForTimeout(1500);
      c.lleno = await mirar(page);
      await capturar(page, 'celular');
      await tocar(page, '#agente-boton', { dedo: true });
      await page.waitForSelector('#agente-panel:not([hidden])', espera);
      await page.waitForTimeout(1200);
      c.chat = await mirar(page);
      await capturar(page, 'celular-chat');
      await tocar(page, '#agente-cerrar', { dedo: true });
      await page.waitForSelector('#agente-panel', { state: 'hidden' });
      c.trasCerrar = (await mirar(page)).llena;
      await tocar(page, '#pres-salir', { dedo: true });
      c.sale = await llena(page, false);
      c.fuera = await mirar(page);
      await ctx.close();
    }
    // ── El celular de lado: la barra de la vista no se ve; «Pantalla completa» va en la barra del panel ──
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
      const l = salida.lado = {};
      await page.waitForTimeout(800);
      l.antes = await mirar(page);
      l.antes.pantalla = await page.evaluate(() => {
        const e = document.getElementById('pres-pantalla');
        const b = e.getBoundingClientRect();
        const s = getComputedStyle(e);
        return s.display === 'none' || !b.width ? null : { l: Math.round(b.left), t: Math.round(b.top), r: Math.round(b.right), b: Math.round(b.bottom) };
      });
      l.antes.menu = await page.evaluate(() => {
        const b = document.querySelector('.barra-movil button')?.getBoundingClientRect();
        return b ? { l: Math.round(b.left), t: Math.round(b.top), r: Math.round(b.right), b: Math.round(b.bottom) } : null;
      });
      await capturar(page, 'lado');
      await tocar(page, '#pres-pantalla', { dedo: true });
      l.entra = await llena(page, true);
      await page.waitForTimeout(1500);
      l.lleno = await mirar(page);
      await capturar(page, 'lado-lleno');
      await tocar(page, '#pres-salir', { dedo: true });
      l.sale = await llena(page, false);
      await ctx.close();
    }
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _choca(a: dict | None, b: dict | None) -> bool:
    return bool(a and b) and a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


def _en_pantalla(a: dict | None, m: dict) -> bool:
    return bool(a) and a["l"] >= 0 and a["t"] >= 0 and a["r"] <= m["w"] and a["b"] <= m["h"]


@requiere_navegador
def test_la_pestana_a_pantalla_completa_con_el_asistente_en_chromium(panel_con_sitio, cfg, tmp_path):
    base, _ = panel_con_sitio
    (tmp_path / "completa.cjs").write_text(GUION, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)
    r = subprocess.run(["node", str(tmp_path / "completa.cjs"), base, cfg.usuario, cfg.clave, capturas],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["csp"] == [] and s["errores"] == [], (s["csp"], s["errores"])

    e = s["escritorio"]
    # antes: el menú y la barra de la vista; «Salir» no se ve
    assert e["antes"]["lateral"] and e["antes"]["barra"] and e["antes"]["salir"] is None, e["antes"]
    # «Pantalla completa»: la página entera (no el marco) y la ventana llena, sin menú ni barras
    assert e["entra"] == [True, True], e
    m = e["lleno"]
    assert m["completa"] == "HTML" and m["lateral"] is None and m["barra"] is None, m
    assert m["iframe"] == {"l": 0, "t": 0, "r": m["w"], "b": m["h"]}, m
    # el teclado va a la presentación
    assert m["foco"] == "pres-iframe", m
    # el botón del asistente y «Salir» a la vista, con nombre, abajo a la izquierda: sin tapar las herramientas de la
    # presentación (arriba a la derecha: antes tapaba «Atlas»), su marca ni su control
    assert m["boton"] and m["salir"] and m["salirNombre"] == "Salir de pantalla completa", m
    assert m["boton"]["l"] == 14 and m["boton"]["b"] == m["h"] - 14 and m["salir"]["l"] > m["boton"]["r"], m
    for nuestro in ("boton", "salir"):
        assert _en_pantalla(m[nuestro], m), (nuestro, m)
        for suyo in ("herr", "marca", "control"):
            assert m[suyo] and not _choca(m[nuestro], m[suyo]), (nuestro, suyo, m)
    # con el ratón quieto se atenúan y vuelven al moverlo
    assert e["seAtenua"] is True and e["vuelve"] is True, e
    # abierto, el asistente es una columna a la derecha: la presentación le deja su ancho y sigue a la vista; «Salir»
    # va encima de la columna, con su nombre a la vista, sin atenuarse; el fondo, negro
    c = e["chat"]
    assert c["llena"] is True and c["completa"] == "HTML" and c["panel"] and c["boton"] is None, c
    assert c["iframe"]["l"] == 0 and c["iframe"]["r"] <= c["panel"]["l"] and c["iframe"]["r"] - c["iframe"]["l"] > 900, c
    assert c["panel"]["t"] >= 70 and c["panel"]["b"] >= c["h"] - 30, c
    assert c["salir"] and c["salir"]["b"] <= c["panel"]["t"] and c["salir"]["r"] <= c["w"], c
    assert c["salir"]["r"] - c["salir"]["l"] > 120 and float(c["salirOpacidad"]) == 1, c
    assert c["fondo"] == "rgb(0, 0, 0)", c
    # su X lo cierra y la pantalla completa sigue
    assert e["xCierraElChat"] is True and e["trasX"]["llena"] is True and e["trasX"]["completa"] == "HTML", e["trasX"]
    # «Salir»: vuelven el menú y la barra, sale de la del navegador y el foco queda en «Pantalla completa»
    assert e["sale"] == [True, True], e
    f = e["fuera"]
    assert f["lateral"] and f["barra"] and f["salir"] is None and f["completa"] is None, f
    assert f["foco"] == "pres-pantalla", f
    # el navegador sale de la suya: la ventana vuelve
    assert e["otraVez"] == [True, True] and e["navegadorSale"] is True, e
    # el botón de la presentación pone la página entera (no su marco) y su F sale
    assert e["suBoton"] == [True, True] and e["suBotonEs"] == "HTML", e
    assert e["suTeclaF"] == [True, True], e
    # sin la del navegador queda llena igual, y Escape en la presentación la devuelve
    assert e["rechazada"] is True and e["rechazadaMira"]["completa"] is None and e["rechazadaMira"]["llena"] is True, e
    assert e["rechazadaMira"]["lateral"] is None and e["rechazadaMira"]["salir"], e["rechazadaMira"]
    assert e["rechazadaFoco"] == "pres-iframe", e
    # su F: llena y rechazada, sale (no la vuelve a pedir); otra vez, entra
    assert e["rechazadaFSale"] is True and e["rechazadaFEntra"] is True, e
    # con el chat abierto, el primer Escape es del chat, con el foco en él o en la presentación; la ventana sigue llena
    assert e["escapeEnElChat"] is True and e["trasEscapeEnElChat"] is True, e
    assert e["focoEnLaPresentacion"] == "pres-iframe", e
    assert e["escapeEnLaPresentacion"] is True and e["trasEscapeEnLaPresentacion"] is True, e
    # y el siguiente sale
    assert e["rechazadaEscape"] is True, e
    # con sus fichas abiertas, su F no hace nada
    assert e["fichas"] is True and e["fConFichas"] == {"llena": False, "fichas": True}, e["fConFichas"]
    # la orden del asistente llena y `activar: false` sale de las dos
    assert e["orden"] is True and e["ordenSale"] == [True, True], e

    k = s["celular"]
    assert k["entra"] is True, k
    m = k["lleno"]
    assert m["lateral"] is None and m["barraMovil"] is None and m["barra"] is None, m
    assert m["iframe"] == {"l": 0, "t": 0, "r": m["w"], "b": m["h"]}, m
    # en la barra de la presentación, entre su marca y sus herramientas: sin tapar su hoja ni su control
    assert m["boton"] and m["salir"] and m["boton"]["t"] < 60 and m["salir"]["t"] < 60, m
    assert m["marca"]["r"] <= m["boton"]["l"] and m["boton"]["r"] <= m["salir"]["l"] and m["salir"]["r"] <= m["herr"]["l"], m
    for nuestro in ("boton", "salir"):
        assert _en_pantalla(m[nuestro], m), (nuestro, m)
        for suyo in ("herr", "marca", "control", "hoja"):
            assert m[suyo] and not _choca(m[nuestro], m[suyo]), (nuestro, suyo, m)
    # abierto, el asistente ocupa la pantalla desde el borde de arriba (sin la barra del panel)
    c = k["chat"]
    assert c["llena"] is True and c["panel"] and c["panel"]["t"] == 0 and c["panel"]["l"] == 0, c
    assert k["trasCerrar"] is True and k["sale"] is True, k
    assert k["fuera"]["barraMovil"] and k["fuera"]["barra"] and k["fuera"]["salir"] is None, k["fuera"]

    # El celular de lado: la barra de la vista no se ve, pero «Pantalla completa» sí, en la barra del panel, a la
    # izquierda del botón del asistente, sin tapar el menú; un toque la llena sin la barra del panel
    lado = s["lado"]
    a = lado["antes"]
    assert a["barra"] is None and a["barraMovil"] and a["boton"] and a["pantalla"], a
    assert _en_pantalla(a["pantalla"], a) and a["pantalla"]["b"] <= a["barraMovil"]["b"], a
    assert a["pantalla"]["r"] <= a["boton"]["l"] and not _choca(a["pantalla"], a["menu"]), a
    assert lado["entra"] is True, lado
    m = lado["lleno"]
    assert m["barraMovil"] is None and m["lateral"] is None and m["iframe"] == {"l": 0, "t": 0, "r": 844, "b": 390}, m
    assert m["salir"] and _en_pantalla(m["salir"], m) and lado["sale"] is True, lado
