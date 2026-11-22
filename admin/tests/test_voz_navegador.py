"""Las respuestas habladas del asistente en un navegador de verdad (Chromium con Playwright), contra el panel de verdad
(uvicorn, el panel en /panel) con las rutas /api/agente/* contestadas desde el navegador (`route.fulfill`): el estado
ofrece la voz clonada, el turno trae frases firmadas (inventadas) y POST /api/agente/voz responde el audio en NDJSON
(PCM de 16 bits a 24 kHz, una onda inventada). Nunca se llama a Mnemo.

* «Leer las respuestas en voz alta» aparece porque el estado lo ofrece (`voz.disponible` y `voz.respuestas`), con
  `aria-pressed`; su clic es el gesto que destraba el audio de la ventana (un AudioContext que corre) y la preferencia
  queda en la pestaña (`yj_agente`), no en localStorage.
* Con él encendido, el mensaje lleva `contexto.voz: true`; cada frase se pide por su referencia (`{conversacion, texto,
  firma}`, tal como llegó) y suena con Web Audio (fuentes agendadas, el mensaje marcado mientras suena); la frase que
  `frases_descartar` anuló no se dice y su versión nueva sí.
* Escape calla la respuesta que se está leyendo sin cerrar el panel; apagar el botón hace que el mensaje siguiente no
  pida la voz. Si la voz de la ventana se apaga (el botón «Voz» de la presentación), el botón se ve apagado y el mensaje
  tampoco la pide; un toque la vuelve a encender.
* Sin errores de consola, sin respuestas de error del servidor y sin violaciones de la CSP del panel (el audio no usa
  `<audio>` ni `blob:`).
* La respuesta inmediata (docs/agente.md, «La respuesta inmediata»), con el turno en flujo de verdad (un `fetch` que la
  prueba alimenta evento por evento): su recuadro aparece en el acto arriba de la respuesta, su voz va primero y la
  respuesta la espera, `vacio` no deja nada y el historial la trae arriba. Y con la presentación de verdad abierta (el
  sitio que arma build_site.py), su «Voz» encendida y sin voz clonada, la sala la oye con la voz del navegador (una
  síntesis falsa que anota qué dice y cuándo) y el plan que llega mientras suena empieza después de ella.
"""
import json

from test_agente_navegador import _correr, _revisar, panel_vivo, requiere_navegador  # noqa: F401 - la fixture
from test_agente_presentacion import panel_con_sitio  # noqa: F401 - la fixture
from test_pantalla_mcp import _Base, _hacer

FIRMA = {c: c * 43 for c in "abcd"}
FRASES = ["Hay tres puestos de votación en la zona rural.", "El más grande es la escuela de La Esperanza."]


@requiere_navegador
def test_las_respuestas_se_oyen_con_la_voz_clonada(panel_vivo, cfg, tmp_path):  # noqa: F811
    base, _, _ = panel_vivo
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "voz")
    (caso,) = res["casos"]
    _revisar(caso)
    d = caso["datos"]
    # El botón, ofrecido por el estado, y su preferencia en la pestaña
    assert d["boton"] == {"visible": True, "presionado": "false", "titulo": "Leer las respuestas en voz alta (con la voz "
                          "clonada de Mnemo «Voz de Ana Inventada», una voz sintética)"}, d["boton"]
    assert d["encendido"] == {"presionado": "true", "guardado": True, "local": None}, d["encendido"]
    # El turno pidió la voz; las frases se pidieron por su referencia, tal como llegaron (la anulada, a lo sumo
    # precargada, nunca dicha)
    m = d["mensajes"]
    assert m[0]["contexto"]["voz"] is True and "voz" not in m[2]["contexto"], m
    voz = d["voz"]
    assert voz[0] == {"conversacion": 61, "texto": FRASES[0], "firma": FIRMA["a"]}, voz
    assert {"conversacion": 61, "texto": FRASES[1], "firma": FIRMA["c"]} in voz, voz
    assert all(set(v) == {"conversacion", "texto", "firma"} for v in voz), voz
    # Sonó con Web Audio: el audio de la ventana corre y se agendaron fuentes; el mensaje se marcó mientras sonaba
    a = d["audio"]
    assert a["creados"] == 1 and a["estado"] == "running" and a["fuentes"] >= 2 and d["se_marco"] is True, a
    assert d["termino"] is True
    # Escape calla sin cerrar el panel
    assert d["escape"] == {"hablando": False, "abierto": True}, d["escape"]
    assert d["apagado"] == {"presionado": "false", "guardado": False}, d["apagado"]
    # Con la voz de la ventana apagada (el botón «Voz» de la presentación), leer se ve apagado aunque la persona lo dejó
    # encendido, y el mensaje no pide la voz; un toque la enciende y el siguiente sí
    assert d["voz_apagada"] == {"presionado": "false", "guardado": True, "voz": "0"}, d["voz_apagada"]
    assert "voz" not in m[3]["contexto"], m
    assert d["reencendida"] == {"presionado": "true", "guardado": True, "voz": "1"}, d["reencendida"]
    assert m[4]["contexto"]["voz"] is True, m


GUION = r"""// Las respuestas habladas en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> voz <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, , capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 20000 };
const F = (c) => c.repeat(43);
const FRASES = ['Hay tres puestos de votación en la zona rural.', 'El más grande es la escuela de La Esperanza.'];
const ESTADO = { disponible: true, motivo: null, configurado: true, proveedor: 'mnemo', es_admin: true, escritura: true,
  limite: { usados: 3, maximo: 300 }, mnemo: { activo: false, origen: null }, dictado: false, sugerencias: [],
  voz: { disponible: true, nombre: 'Voz de Ana Inventada', respuestas: true, automatica: true } };
const nd = (evs) => evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
// La primera respuesta: la frase 1 llega a medias, el texto final la cambia (`frases_descartar`) y llega la buena
const TURNOS = [
  [{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' },
    { tipo: 'texto', texto: FRASES[0] + ' ' }, { tipo: 'frase', n: 0, texto: FRASES[0], firma: F('a') },
    { tipo: 'texto', texto: 'El más grande es la escuela de La Esperanz' },
    { tipo: 'frase', n: 1, texto: 'El más grande es la escuela de La Esperanz', firma: F('b') },
    { tipo: 'frases_descartar', desde: 1 }, { tipo: 'texto_ronda', texto: FRASES.join(' ') },
    { tipo: 'frase', n: 1, texto: FRASES[1], firma: F('c') }, { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } }],
  [{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'texto', texto: 'Una respuesta larga que se va a callar con Escape.' },
    { tipo: 'frase', n: 0, texto: 'Una respuesta larga que se va a callar con Escape.', firma: F('d') },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 5, maximo: 300 } }],
  [{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'texto', texto: 'Esta ya no se lee.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 6, maximo: 300 } }],
  [{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'texto', texto: 'Con la voz apagada.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 7, maximo: 300 } }],
  [{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'texto', texto: 'Con la voz encendida otra vez.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 8, maximo: 300 } }],
];
const ultima = (t) => [...document.querySelectorAll('.agente-md')].pop()?.textContent === t
  && document.querySelector('#agente-panel').dataset.estado === 'listo';
// El audio de una frase: una onda de 220 Hz inventada, PCM de 16 bits a 24 kHz, en trozos de 200 ms (como Mnemo)
function audio(segundos) {
  const n = Math.round(24000 * segundos);
  const b = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(8000 * Math.sin(2 * Math.PI * 220 * i / 24000)), i * 2);
  const trozos = [];
  for (let i = 0; i < b.length; i += 9600) trozos.push(b.subarray(i, i + 9600).toString('base64'));
  return trozos;
}

(async () => {
  const nav = await chromium.launch();
  const caso = { nombre: 'voz', revisiones: {}, errores: [], csp: [], datos: { mensajes: [], voz: [] } };
  const d = caso.datos, v = caso.revisiones;
  try {
    const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.route((u) => u.origin !== origen, (r) => r.abort());
    await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
      const req = route.request();
      const ruta = new URL(req.url()).pathname.slice(pref.length);
      if (req.method() === 'GET' && ruta === '/api/agente/estado') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ESTADO) });
      if (req.method() === 'POST' && ruta === '/api/agente/mensajes') {
        const c = req.postDataJSON();
        d.mensajes.push({ contexto: c.contexto });
        return route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: nd(TURNOS[d.mensajes.length - 1]) });
      }
      if (req.method() === 'POST' && ruta === '/api/agente/voz') {
        const ref = req.postDataJSON();
        d.voz.push(ref);
        const trozos = audio(ref.firma === F('d') ? 6 : 1.2);
        return route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: nd([
          { tipo: 'inicio', formato: 'pcm_s16le', muestreo: 24000, canales: 1, cache: false, voz: 'Voz de Ana Inventada' },
          ...trozos.map((t) => ({ tipo: 'audio', datos: t })), { tipo: 'fin', ms_primer_audio: 320, ms_mnemo: 250, bytes: 1 }]) });
      }
      return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No existe' }) });
    });
    await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
    await ctx.addInitScript(() => {
      addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
      // Lo que hace el audio de la ventana: cuántos AudioContext, en qué estado y cuántas fuentes se agendan
      const AC = window.AudioContext;
      window.__audio = { creados: 0, fuentes: 0, ctx: null };
      window.AudioContext = class extends AC {
        constructor(...a) { super(...a); window.__audio.creados++; window.__audio.ctx = this; }
        createBufferSource() {
          const s = super.createBufferSource();
          const empezar = s.start.bind(s);
          s.start = (...a) => { if (s.buffer && s.buffer.length > 1) window.__audio.fuentes++; return empezar(...a); };
          return s;
        }
      };
      window.__marcado = false;
      new MutationObserver(() => { if (document.querySelector('.agente-msj.hablando')) window.__marcado = true; })
        .observe(document, { subtree: true, attributes: true, attributeFilter: ['class'] });
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => caso.errores.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
    page.on('response', (x) => { if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo'))) caso.errores.push(`${x.status()} ${x.url()}`); });

    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', usuario);
    await page.fill('#f-login [name=clave]', clave);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.waitForSelector('#agente-boton:not([hidden])', espera);
    await page.click('#agente-boton');
    await page.waitForSelector('#agente-hablar:not([hidden])', espera);
    d.boton = await page.evaluate(() => { const b = document.querySelector('#agente-hablar');
      return { visible: !b.hidden, presionado: b.getAttribute('aria-pressed'), titulo: b.title }; });
    await page.click('#agente-hablar');
    d.encendido = await page.evaluate(() => ({ presionado: document.querySelector('#agente-hablar').getAttribute('aria-pressed'),
      guardado: JSON.parse(sessionStorage.getItem('yj_agente') || '{}').hablar ?? null, local: localStorage.getItem('yj_agente') }));

    // 1. La respuesta se oye: sus dos frases, en orden, y el mensaje marcado mientras suena
    await page.fill('#agente-texto', '¿Cuántos puestos hay en la zona rural?');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction((t) => window.__audio.fuentes > 0, null, espera);
    await page.waitForFunction(() => !document.querySelector('.agente-msj.hablando') && window.__marcado, null, espera);
    await page.waitForFunction(() => !document.querySelector('#agente-hablar').hasAttribute('data-hablando'), null, espera);
    d.termino = true;
    d.audio = await page.evaluate(() => ({ creados: window.__audio.creados, estado: window.__audio.ctx?.state, fuentes: window.__audio.fuentes }));
    d.se_marco = await page.evaluate(() => window.__marcado);
    await page.screenshot({ path: `${capturas}/voz-respuesta.png` });

    // 2. Escape calla la que se está leyendo (sin cerrar el panel)
    await page.fill('#agente-texto', 'Cuéntame más.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForSelector('.agente-msj.hablando', espera);
    await page.waitForTimeout(300);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    d.escape = await page.evaluate(() => ({ hablando: !!document.querySelector('.agente-msj.hablando'), abierto: !document.querySelector('#agente-panel').hidden }));

    // 3. Apagado: el mensaje siguiente no pide la voz
    await page.click('#agente-hablar');
    d.apagado = await page.evaluate(() => ({ presionado: document.querySelector('#agente-hablar').getAttribute('aria-pressed'),
      guardado: JSON.parse(sessionStorage.getItem('yj_agente') || '{}').hablar ?? null }));
    await page.fill('#agente-texto', 'Gracias.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo'
      && [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Esta ya no se lee.', null, espera);

    // 4. Encendido otra vez, pero la voz de la ventana se apaga (lo que hace el botón «Voz» de la presentación: es la
    //    misma voz, la del módulo voz-panel.js de esta página): el botón se ve apagado y el mensaje no pide la voz. Un
    //    toque la vuelve a encender y el siguiente sí la pide
    await page.click('#agente-hablar');
    await page.evaluate(async () => {
      const url = performance.getEntriesByType('resource').map((e) => e.name).find((n) => /\/js\/voz-panel\.js/.test(n));
      const v = (await import(url)).tomarVoz('prueba');
      v.apagar();
      v.soltar();
    });
    await page.waitForFunction(() => document.querySelector('#agente-hablar').getAttribute('aria-pressed') === 'false', null, espera);
    d.voz_apagada = await page.evaluate(() => ({ presionado: document.querySelector('#agente-hablar').getAttribute('aria-pressed'),
      guardado: JSON.parse(sessionStorage.getItem('yj_agente') || '{}').hablar ?? null, voz: localStorage.getItem('yj_voz') }));
    await page.fill('#agente-texto', '¿Y en el casco urbano?');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(ultima, 'Con la voz apagada.', espera);
    await page.click('#agente-hablar');
    d.reencendida = await page.evaluate(() => ({ presionado: document.querySelector('#agente-hablar').getAttribute('aria-pressed'),
      guardado: JSON.parse(sessionStorage.getItem('yj_agente') || '{}').hablar ?? null, voz: localStorage.getItem('yj_voz') }));
    await page.fill('#agente-texto', 'Gracias otra vez.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(ultima, 'Con la voz encendida otra vez.', espera);
    await ctx.close();
  } catch (e) {
    v.sin_excepcion = String(e.stack || e).slice(0, 1500);
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos: [caso] }));
})().catch((e) => { console.error(e); process.exit(1); });
"""


# ───────────────────────────── La respuesta inmediata ─────────────────────────────

INMEDIATA = ["Buena pregunta: ", "en la zona rural hay varios puestos de votación."]
DICHA = "".join(INMEDIATA)
RESPUESTA = "Hay tres puestos en la zona rural."


@requiere_navegador
def test_la_respuesta_inmediata_se_ve_arriba_y_se_oye_primero(panel_vivo, cfg, tmp_path):  # noqa: F811
    """La respuesta inmediata (docs/agente.md, «La respuesta inmediata») en Chromium, con el turno en flujo de verdad (un
    `fetch` que la prueba alimenta evento por evento): el recuadro aparece en cuanto llega su primer trozo, arriba de la
    respuesta del turno, con «preparando el detalle…» mientras el turno sigue; su frase se pide a la voz clonada primero
    y la de la respuesta, que llega mientras tanto, espera a que termine; al terminar el turno la etiqueta queda en
    «Respuesta inmediata». Con `vacio` no queda nada, y al reabrir la conversación vuelve arriba de su respuesta."""
    base, _, _ = panel_vivo
    res = _correr(GUION_ADELANTO, tmp_path, base, cfg.usuario, cfg.clave, "adelanto")
    (caso,) = res["casos"]
    _revisar(caso)
    d = caso["datos"]
    # En cuanto llega: arriba del mensaje (después de «Asistente:»), como texto, y diciendo que el detalle se prepara
    assert d["vivo"] == {"primero": True, "texto": DICHA, "hijos": 0, "etiqueta": "Respuesta inmediata · preparando el detalle…",
                         "estado": "preparando", "trabajando": True}, d["vivo"]
    assert d["contexto"] is True
    # La frase de la respuesta llegó mientras sonaba la inmediata: no se pidió hasta que la inmediata terminó
    assert d["mientras"] == [DICHA], d["mientras"]
    assert d["orden"] == [DICHA, RESPUESTA], d["orden"]
    assert d["firmas"] == ["a" * 43, "b" * 43]
    assert d["final"] == {"primero": True, "etiqueta": "Respuesta inmediata", "estado": None, "respuesta": RESPUESTA}, d["final"]
    assert d["se_marco"] is True
    # `vacio`: nada queda; y en el historial vuelve arriba de su respuesta
    assert d["vacio"] == {"recuadros": 0, "respuesta": "De nada."}, d["vacio"]
    assert d["historial"] == {"primero": True, "etiqueta": "Respuesta inmediata", "estado": None, "texto": DICHA,
                              "respuesta": RESPUESTA}, d["historial"]
    # Con «Leer las respuestas» (no es para la sala), cerrar el chat calla también la inmediata
    assert d["cerrar_calla"] == ["Con gusto le cuento."], d["cerrar_calla"]
    # Sin leerla en voz alta, se anuncia en una región aparte en cuanto termina, aunque la conversación siga ocupada; lo
    # que dice que se prepara el detalle va escondido (al quitarlo no se vuelve a anunciar la etiqueta)
    assert d["lector_hablar"] is False
    assert d["lector_antes"] == {"texto": "", "fuera": True, "ocupada": "true"}, d["lector_antes"]
    assert d["lector"] == {"texto": "Respuesta inmediata: Con gusto, le cuento enseguida.", "fuera": True,
                           "ocupada": "true"}, d["lector"]
    assert d["lector_etiqueta"] == {"texto": "Respuesta inmediata · preparando el detalle…",
                                    "escondido": " · preparando el detalle…"}, d["lector_etiqueta"]
    assert d["lector_fin"]["ocupada"] is None
    # Otro turno la vacía, y con `vacio` no se anuncia nada
    assert d["lector_vacio"]["texto"] == "", d["lector_vacio"]


GUION_ADELANTO = r"""// La respuesta inmediata en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> adelanto <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, , capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 20000 };
const F = (c) => c.repeat(43);
const INMEDIATA = ['Buena pregunta: ', 'en la zona rural hay varios puestos de votación.'];
const DICHA = INMEDIATA.join('');
const RESPUESTA = 'Hay tres puestos en la zona rural.';
const ESTADO = { disponible: true, motivo: null, configurado: true, proveedor: 'mnemo', es_admin: true, escritura: true,
  limite: { usados: 3, maximo: 300 }, mnemo: { activo: false, origen: null }, dictado: false, sugerencias: [], adelanto: true,
  voz: { disponible: true, nombre: 'Voz de Ana Inventada', respuestas: true, automatica: true } };
// La conversación guardada: la respuesta inmediata va primera en las partes de la respuesta de su turno
const GUARDADA = { id: 61, titulo: 'Puestos', pendientes: [], mensajes: [{ rol: 'usuario', texto: '¿Cuántos puestos hay en la zona rural?' },
  { rol: 'asistente', partes: [{ tipo: 'adelanto', texto: DICHA }, { tipo: 'texto', texto: RESPUESTA }] }] };
const nd = (evs) => evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
function audio(segundos) {
  const n = Math.round(24000 * segundos);
  const b = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(8000 * Math.sin(2 * Math.PI * 220 * i / 24000)), i * 2);
  const trozos = [];
  for (let i = 0; i < b.length; i += 9600) trozos.push(b.subarray(i, i + 9600).toString('base64'));
  return trozos;
}
const hasta = async (page, f, ms = 20000) => { const fin = Date.now() + ms; while (!f() && Date.now() < fin) await page.waitForTimeout(50); if (!f()) throw new Error('No llegó a tiempo'); };
// Lo que ve la persona del último mensaje del asistente
const mirar = () => {
  const msj = [...document.querySelectorAll('.agente-msj.agente-respuesta')].pop();
  const b = msj?.querySelector('.agente-adelanto');
  return { primero: !!b && msj.children[0].classList.contains('sr') && msj.children[1] === b,
    etiqueta: b?.querySelector('.agente-adelanto-et').textContent ?? null, estado: b?.dataset.estado ?? null,
    texto: b?.querySelector('.agente-adelanto-texto').textContent ?? null, hijos: b?.querySelector('.agente-adelanto-texto').children.length ?? null,
    respuesta: msj?.querySelector('.agente-md')?.textContent ?? null, trabajando: !!msj?.classList.contains('trabajando'),
    recuadros: msj?.querySelectorAll('.agente-adelanto').length ?? 0 };
};

(async () => {
  const nav = await chromium.launch();
  const caso = { nombre: 'adelanto', revisiones: {}, errores: [], csp: [], datos: {} };
  const d = caso.datos, v = caso.revisiones;
  const voz = [];
  try {
    // (CAPTURAS_TEMA=oscuro: las capturas con el tema oscuro, para mirarlas a mano)
    const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: process.env.CAPTURAS_TEMA === 'oscuro' ? 'dark' : 'light' });
    await ctx.route((u) => u.origin !== origen, (r) => r.abort());
    await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
      const req = route.request();
      const ruta = new URL(req.url()).pathname.slice(pref.length);
      if (req.method() === 'GET' && ruta === '/api/agente/estado') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ESTADO) });
      if (req.method() === 'GET' && ruta === '/api/agente/conversaciones/61') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(GUARDADA) });
      if (req.method() === 'POST' && ruta === '/api/agente/voz') {
        const ref = req.postDataJSON();
        voz.push(ref);
        const trozos = audio(ref.texto === DICHA ? 2 : 1);
        return route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: nd([
          { tipo: 'inicio', formato: 'pcm_s16le', muestreo: 24000, canales: 1, cache: false, voz: 'Voz de Ana Inventada' },
          ...trozos.map((t) => ({ tipo: 'audio', datos: t })), { tipo: 'fin', ms_primer_audio: 320, ms_mnemo: 250, bytes: 1 }]) });
      }
      return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No existe' }) });
    });
    await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
    await ctx.addInitScript(() => {
      addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
      // El turno en flujo de verdad: POST /api/agente/mensajes responde un cuerpo que la prueba va llenando
      const original = window.fetch;
      const cod = new TextEncoder();
      window.__turnos = [];
      window.fetch = function (u, o) {
        if (/\/api\/agente\/mensajes$/.test(String(u))) {
          let c = null;
          const cuerpo = new ReadableStream({ start(x) { c = x; } });
          window.__turnos.push({ cuerpo: JSON.parse(o?.body || 'null'), c });
          return Promise.resolve(new Response(cuerpo, { status: 200, headers: { 'content-type': 'application/x-ndjson' } }));
        }
        return original.apply(this, arguments);
      };
      window.__empujar = (evs) => { const t = window.__turnos.at(-1); for (const e of evs) t.c.enqueue(cod.encode(JSON.stringify(e) + '\n')); };
      window.__cerrar = () => window.__turnos.at(-1).c.close();
      window.__marcado = false;
      new MutationObserver(() => { if (document.querySelector('.agente-msj.hablando')) window.__marcado = true; })
        .observe(document, { subtree: true, attributes: true, attributeFilter: ['class'] });
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => caso.errores.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
    page.on('response', (x) => { if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo'))) caso.errores.push(`${x.status()} ${x.url()}`); });
    const empujar = (evs) => page.evaluate((x) => window.__empujar(x), evs);

    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', usuario);
    await page.fill('#f-login [name=clave]', clave);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.waitForSelector('#agente-boton:not([hidden])', espera);
    await page.click('#agente-boton');
    await page.waitForSelector('#agente-hablar:not([hidden])', espera);
    await page.click('#agente-hablar');

    // 1. El primer trozo llega y el recuadro aparece en el acto, arriba, mientras el turno sigue
    await page.fill('#agente-texto', '¿Cuántos puestos hay en la zona rural?');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => window.__turnos.length === 1, null, espera);
    d.contexto = await page.evaluate(() => window.__turnos[0].cuerpo.contexto.voz === true);
    await empujar([{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'adelanto', texto: INMEDIATA[0] }]);
    await page.waitForSelector('.agente-adelanto', espera);
    await empujar([{ tipo: 'adelanto', texto: INMEDIATA[1] }]);
    await page.waitForFunction((t) => document.querySelector('.agente-adelanto-texto')?.textContent === t, DICHA, espera);
    const m = await page.evaluate(mirar);
    d.vivo = { primero: m.primero, texto: m.texto, hijos: m.hijos, etiqueta: m.etiqueta, estado: m.estado, trabajando: m.trabajando };
    await page.screenshot({ path: `${capturas}/adelanto-preparando.png` });

    // 2. Su frase se pide primero; la de la respuesta, que llega mientras tanto, espera
    await empujar([{ tipo: 'adelanto_frase', n: 0, texto: DICHA, firma: F('a') }]);
    await hasta(page, () => voz.length >= 1);
    await empujar([{ tipo: 'texto', texto: RESPUESTA }, { tipo: 'frase', n: 0, texto: RESPUESTA, firma: F('b') }]);
    await page.waitForTimeout(700);
    d.mientras = voz.map((x) => x.texto);

    // 3. La inmediata termina: la respuesta se pide y suena después; el turno termina
    await empujar([{ tipo: 'adelanto_fin' }]);
    await hasta(page, () => voz.length >= 2);
    await empujar([{ tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    await page.waitForFunction(() => window.__marcado && !document.querySelector('.agente-msj.hablando'), null, espera);
    d.orden = voz.map((x) => x.texto);
    d.firmas = voz.map((x) => x.firma);
    d.se_marco = await page.evaluate(() => window.__marcado);
    const f = await page.evaluate(mirar);
    d.final = { primero: f.primero, etiqueta: f.etiqueta, estado: f.estado, respuesta: f.respuesta };
    await page.screenshot({ path: `${capturas}/adelanto-final.png` });

    // 4. Con `vacio`, lo que llegó a pintarse se quita
    await page.fill('#agente-texto', 'Gracias.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => window.__turnos.length === 2, null, espera);
    await empujar([{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'adelanto', texto: 'Algo que no queda a la vista.' },
      { tipo: 'adelanto_fin', vacio: true }, { tipo: 'texto', texto: 'De nada.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 5, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo'
      && [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'De nada.', null, espera);
    const x = await page.evaluate(mirar);
    d.vacio = { recuadros: x.recuadros, respuesta: x.respuesta };

    // 5. El historial: al volver a abrir la conversación, la inmediata va arriba de su respuesta
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.agente-adelanto', espera);
    const h = await page.evaluate(mirar);
    d.historial = { primero: h.primero, etiqueta: h.etiqueta, estado: h.estado, texto: h.texto, respuesta: h.respuesta };
    await page.waitForTimeout(400);   // (el panel entra con una animación corta)
    await page.screenshot({ path: `${capturas}/adelanto-historial.png` });

    // 6. Con «Leer las respuestas» (no es para la sala), cerrar el chat calla también la inmediata: su frase siguiente
    // ya no se pide
    const n6 = voz.length;
    await page.fill('#agente-texto', '¿Y en el casco urbano?');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => window.__turnos.length === 1, null, espera);
    await empujar([{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'adelanto', texto: 'Con gusto le cuento. ' },
      { tipo: 'adelanto_frase', n: 0, texto: 'Con gusto le cuento.', firma: F('c') }]);
    await hasta(page, () => voz.length > n6);
    await page.click('#agente-cerrar');
    await empujar([{ tipo: 'adelanto', texto: 'Enseguida le doy el detalle.' },
      { tipo: 'adelanto_frase', n: 1, texto: 'Enseguida le doy el detalle.', firma: F('d') }, { tipo: 'adelanto_fin' },
      { tipo: 'texto', texto: 'Hay dos puestos.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 6, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForTimeout(1200);
    d.cerrar_calla = voz.slice(n6).map((x) => x.texto);

    // 7. Sin leerla en voz alta, la inmediata se anuncia a los lectores de pantalla en cuanto termina, aunque la
    // conversación siga ocupada (aria-busy) con el turno; con `vacio`, nada, y otro turno la vacía
    await page.click('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])', espera);
    await page.click('#agente-hablar');
    const vivo = () => page.evaluate(() => ({ texto: document.querySelector('#agente-adelanto-vivo')?.textContent ?? null,
      fuera: !document.querySelector('#agente-adelanto-vivo')?.closest('#agente-mensajes'),
      ocupada: document.querySelector('#agente-mensajes').getAttribute('aria-busy') }));
    await page.fill('#agente-texto', 'Gracias.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => window.__turnos.length === 2, null, espera);
    d.lector_hablar = await page.evaluate(() => window.__turnos[1].cuerpo.contexto.voz === true);
    await empujar([{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'adelanto', texto: 'Con gusto, le cuento enseguida.' }]);
    await page.waitForSelector('.agente-adelanto', espera);
    d.lector_antes = await vivo();
    await empujar([{ tipo: 'adelanto_fin' }]);
    await page.waitForFunction(() => !!document.querySelector('#agente-adelanto-vivo')?.textContent, null, { timeout: 5000 }).catch(() => {});
    d.lector = await vivo();
    d.lector_etiqueta = await page.evaluate(() => {
      const et = [...document.querySelectorAll('.agente-adelanto-et')].pop();
      return { texto: et.textContent, escondido: et.querySelector('[aria-hidden="true"]')?.textContent ?? null };
    });
    await empujar([{ tipo: 'texto', texto: 'De nada.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 7, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    d.lector_fin = await vivo();
    await page.fill('#agente-texto', 'Otra cosa.');
    await page.press('#agente-texto', 'Enter');
    await page.waitForFunction(() => window.__turnos.length === 3, null, espera);
    await empujar([{ tipo: 'inicio', conversacion: 61, titulo: 'Puestos' }, { tipo: 'adelanto', texto: 'Algo que no queda.' },
      { tipo: 'adelanto_fin', vacio: true }]);
    await page.waitForTimeout(300);
    d.lector_vacio = await vivo();
    await empujar([{ tipo: 'texto', texto: 'Listo.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 8, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    await ctx.close();
  } catch (e) {
    v.sin_excepcion = String(e.stack || e).slice(0, 1500);
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos: [caso] }));
})().catch((e) => { console.error(e); process.exit(1); });
"""


SALA = "Claro: son trescientas viviendas nuevas en un barrio de veinticinco bloques. Enseguida se lo muestro en la presentación."
CIERRE = ["Con gusto le cuento.", "Enseguida se lo muestro."]       # la sala la oye entera aunque se cierre el chat
# Un plan para la pantalla en off de otro equipo la calla (la primera, larga: el plan llega mientras suena)
REMOTA = ["Claro, con gusto le cuento lo esencial de la obra.", "Ya se lo muestro allá."]
PLAN = {"op": "recorrido", "titulo": "Las viviendas nuevas", "pasos": [
    {"capitulo": "vivienda", "paso": 3, "dice": "Estas son las viviendas nuevas del barrio."},
    {"paso": 4, "dice": "Y así es el apartamento tipo de cada bloque."}]}


@requiere_navegador
def test_la_sala_oye_la_inmediata_antes_del_plan(panel_con_sitio, cfg, tmp_path):  # noqa: F811
    """Con la presentación abierta en la pestaña, su «Voz» encendida y sin voz clonada, el turno pide la voz de la
    inmediata (`voz_adelanto`, no `voz`: la sala oye solo ella) y la respuesta inmediata se dice con la voz del
    navegador, sin pedirle nada a Mnemo. Cerrar el chat mientras suena no la calla (la sala la oye entera). Un plan para
    la pantalla en off de otro equipo (allá no la pueden esperar) la calla. El plan de esta pestaña que llega mientras
    suena espera a que termine (no la corta) y empieza después."""
    base, _ = panel_con_sitio
    # El plan, como lo arma el servidor (la acción `presentacion` con el recorrido absoluto y la de la tarjeta)
    acciones = _hacer(_Base(), 7, PLAN, por="asistente").acciones
    (tmp_path / "sala.cjs").write_text(GUION_SALA, encoding="utf-8")
    import os
    import subprocess
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)
    datos = json.dumps({"acciones": acciones, "sala": SALA, "cierre": CIERRE, "remota": REMOTA})
    r = subprocess.run(["node", str(tmp_path / "sala.cjs"), base, cfg.usuario, cfg.clave, datos, capturas],
                       capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s.get("excepcion") is None, s.get("excepcion")
    assert s["csp"] == [] and s["errores"] == [] and s["consola"] == [], (s["csp"], s["errores"], s["consola"])
    # Sin voz clonada no hay botón «Leer respuestas», pero la sala oye: el turno pidió la voz de la inmediata (solo
    # ella: no `voz`) y no se le pidió nada a Mnemo
    assert s["leer_visible"] is False and s["contexto_sala"] is True and s["voz_mnemo"] == []
    # Cerrar el chat (su X) mientras suena lo de la sala: la frase sigue y la siguiente también se dice
    assert s["cerrado"] is True
    assert [h["texto"] for h in s["cierre"]] == CIERRE and not any(h.get("cortada") for h in s["cierre"]), s["cierre"]
    # Un plan para la pantalla en off de otro equipo: la que sonaba se corta y la siguiente no se dice
    assert [h["texto"] for h in s["remota"]] == REMOTA[:1] and s["remota"][0].get("cortada") is True, s["remota"]
    habla = s["habla"]
    frase_plan = acciones[0]["recorrido"]["escenas"][0]["frases"][0]
    assert habla[0]["texto"] == SALA and not habla[0].get("cortada"), habla
    i = next(k for k, h in enumerate(habla) if h["texto"] == frase_plan)
    assert i == 1, habla
    # Sin la espera, el plan habría empezado antes de que terminara la inmediata (la previa es de 1,8 s) y la habría cortado
    assert habla[0]["fin"] - s["plan_en"] > 1800 + 1000, (s["plan_en"], habla)
    assert habla[1]["inicio"] >= habla[0]["fin"], habla
    assert s["recuadro"] == {"etiqueta": "Respuesta inmediata", "texto": SALA}, s["recuadro"]


GUION_SALA = r"""// La sala oye la respuesta inmediata antes del plan. Uso: node <guion> <base del panel> <usuario> <clave> <datos> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, datos, capturas] = process.argv.slice(2);
const D = JSON.parse(datos);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 90000 };
const F = (c) => c.repeat(43);
const ESTADO = { disponible: true, motivo: null, configurado: true, proveedor: 'mnemo', es_admin: true, escritura: true,
  limite: { usados: 3, maximo: 300 }, mnemo: { activo: false, origen: null }, dictado: false, sugerencias: [], adelanto: true,
  voz: { disponible: false } };
const salida = { csp: [], errores: [], consola: [], voz_mnemo: [] };

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  try {
    const ctx = await nav.newContext({ viewport: { width: 1400, height: 900 } });
    await ctx.route((u) => u.origin !== origen, (r) => r.abort());
    await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/') || u.pathname === pref + '/api/pantalla/progreso', async (route) => {
      const req = route.request();
      const ruta = new URL(req.url()).pathname.slice(pref.length);
      if (req.method() === 'GET' && ruta === '/api/agente/estado') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ESTADO) });
      // el plan de la prueba no está guardado en este servidor: su avance se acepta aquí (si no, un 409 lo detendría)
      if (req.method() === 'POST' && ruta === '/api/pantalla/progreso') return route.fulfill({ status: 204, body: '' });
      if (req.method() === 'POST' && ruta === '/api/agente/voz') salida.voz_mnemo.push(req.postDataJSON());
      return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No existe' }) });
    });
    await ctx.exposeBinding('__csp', (_, x) => salida.csp.push(x));
    await ctx.addInitScript(() => {
      addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective} ${e.blockedURI}`), true);
      if (window !== window.top) return;   // (el iframe de la presentación no habla ni conversa)
      // La voz del navegador, falsa: una voz en español que tarda 80 ms por carácter (la respuesta inmediata, unos 9 s: más
      // que la previa y que aplicar el primer paso) y anota qué dijo, cuándo y si se cortó
      window.__habla = [];
      class Locucion { constructor(t) { this.text = t; } }
      let actual = null, reloj = 0;
      const sintesis = {
        getVoices: () => [{ name: 'Voz falsa', lang: 'es-CO', localService: true }],
        addEventListener() {}, removeEventListener() {},
        cancel() {
          const a = actual; actual = null; clearTimeout(reloj);
          if (a) { a.r.fin = performance.now(); a.r.cortada = true; a.u.onerror?.({ error: 'interrupted' }); }
        },
        speak(u) {
          if (!u.text) return;   // la locución vacía con que se destraba
          const r = { texto: u.text, inicio: performance.now() };
          window.__habla.push(r);
          actual = { u, r };
          setTimeout(() => u.onstart?.(), 10);
          reloj = setTimeout(() => { if (actual?.u === u) { actual = null; r.fin = performance.now(); u.onend?.(); } }, 80 * u.text.length);
        },
      };
      Object.defineProperty(window, 'speechSynthesis', { value: sintesis, configurable: true });
      window.SpeechSynthesisUtterance = Locucion;
      // El turno en flujo de verdad (como en GUION_ADELANTO)
      const original = window.fetch;
      const cod = new TextEncoder();
      window.__turnos = [];
      window.fetch = function (u, o) {
        if (/\/api\/agente\/mensajes$/.test(String(u))) {
          let c = null;
          const cuerpo = new ReadableStream({ start(x) { c = x; } });
          window.__turnos.push({ cuerpo: JSON.parse(o?.body || 'null'), c });
          return Promise.resolve(new Response(cuerpo, { status: 200, headers: { 'content-type': 'application/x-ndjson' } }));
        }
        return original.apply(this, arguments);
      };
      window.__empujar = (evs) => { const t = window.__turnos.at(-1); for (const e of evs) t.c.enqueue(cod.encode(JSON.stringify(e) + '\n')); };
      window.__cerrar = () => window.__turnos.at(-1).c.close();
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => salida.errores.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) salida.consola.push(m.text().slice(0, 300)); });
    page.on('response', (x) => { if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo'))) salida.errores.push(`${x.status()} ${x.url()}`); });
    const empujar = (evs) => page.evaluate((x) => window.__empujar(x), evs);

    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', usuario);
    await page.fill('#f-login [name=clave]', clave);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.waitForSelector('#agente-boton:not([hidden])', espera);
    await page.goto(base + '/presentacion', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.evaluate(async () => { window.__P = await import(new URL('agente-presentacion.js', document.querySelector('script[type=module]').src).href); });
    await page.waitForFunction(() => window.__P.presentacionLista(), null, espera);
    await page.click('#agente-boton');
    salida.leer_visible = await page.evaluate(() => !document.querySelector('#agente-hablar').hidden);
    // Antes, la presentación va al paso donde empieza el plan (cargar el capítulo tarda: así su primer paso se aplica
    // enseguida y, sin la espera, cortaría la respuesta inmediata)
    // (la sala oye: la voz de la inmediata, `voz_adelanto`, y no la de la respuesta, `voz`)
    const pideSala = (i) => page.evaluate((k) => { const c = window.__turnos[k].cuerpo.contexto; return c.voz_adelanto === true && !('voz' in c); }, i);
    const preguntar = async (texto) => {
      const n = await page.evaluate(() => window.__turnos.length);
      await page.fill('#agente-texto', texto);
      await page.press('#agente-texto', 'Enter');
      await page.waitForFunction((k) => window.__turnos.length === k + 1, n, espera);
      salida.contexto_sala &&= await pideSala(n);
    };
    const dicha = (t, fin = false) => page.waitForFunction(([x, f]) => window.__habla.some((h) => h.texto === x && (!f || h.fin)), [t, fin], espera);
    const dichas = (ts) => page.evaluate((x) => window.__habla.filter((h) => x.includes(h.texto)).map((h) => ({ ...h })), ts);
    salida.contexto_sala = true;
    await preguntar('Abre las viviendas nuevas.');
    await empujar([{ tipo: 'inicio', conversacion: 71, titulo: 'Viviendas' },
      { tipo: 'accion', accion: { tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 3 } },
      { tipo: 'texto', texto: 'Listo.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    await page.waitForFunction(() => { const e = window.__P.estadoPresentacion(); return e?.capitulo === 'vivienda' && e.paso === 3; }, null, espera);
    await page.waitForTimeout(3000);

    // Cerrar el chat (su X) mientras suena lo de la sala no lo calla: la sala la oye entera
    await preguntar('¿Qué es la torre?');
    await empujar([{ tipo: 'inicio', conversacion: 71, titulo: 'Viviendas' }, { tipo: 'adelanto', texto: D.cierre[0] + ' ' },
      { tipo: 'adelanto_frase', n: 0, texto: D.cierre[0], firma: F('c') }]);
    await dicha(D.cierre[0]);
    await page.click('#agente-cerrar');
    salida.cerrado = await page.evaluate(() => document.querySelector('#agente-panel').hidden);
    await empujar([{ tipo: 'adelanto', texto: D.cierre[1] }, { tipo: 'adelanto_frase', n: 1, texto: D.cierre[1], firma: F('d') },
      { tipo: 'adelanto_fin' }, { tipo: 'texto', texto: 'Es la obra más grande.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 5, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await dicha(D.cierre[1], true).catch(() => {});
    salida.cierre = await dichas(D.cierre);
    await page.click('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])', espera);
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

    // Un plan para la pantalla en off de otro equipo (la tarjeta del chat; allá no la pueden esperar) la calla. (El
    // sondeo de esa tarjeta, aquí: no hay ningún plan en el servidor)
    await ctx.route((u) => u.pathname === pref + '/api/pantalla/recorrido' || u.pathname === pref + '/api/pantalla/recorrido/control',
      (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ recorrido: null, vigente: null, conectada: true }) }));
    await preguntar('¿Y el hospital?');
    await empujar([{ tipo: 'inicio', conversacion: 71, titulo: 'Viviendas' }, { tipo: 'adelanto', texto: D.remota[0] + ' ' },
      { tipo: 'adelanto_frase', n: 0, texto: D.remota[0], firma: F('e') }]);
    await dicha(D.remota[0]);
    await empujar([{ tipo: 'accion', accion: { ...D.acciones.at(-1), id: 'abcdef012345', destino: 'pantalla_off' } },
      { tipo: 'adelanto', texto: D.remota[1] }, { tipo: 'adelanto_frase', n: 1, texto: D.remota[1], firma: F('f') },
      { tipo: 'adelanto_fin' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 6, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    await page.waitForTimeout(80 * (D.remota[0].length + D.remota[1].length) + 500);
    salida.remota = await dichas(D.remota);
    await page.evaluate(() => { window.__habla = []; });

    // La pregunta: la sala oye (la presentación está abierta con su «Voz» encendida)
    await preguntar('¿Cómo son las viviendas nuevas?');
    await empujar([{ tipo: 'inicio', conversacion: 71, titulo: 'Viviendas' }, { tipo: 'adelanto', texto: D.sala },
      { tipo: 'adelanto_frase', n: 0, texto: D.sala, firma: F('a') }]);
    await page.waitForFunction(() => window.__habla.length >= 1, null, espera);
    // Mientras suena, el modelo arma el plan y llega: espera a que termine la inmediata
    await page.waitForTimeout(300);
    salida.plan_en = await page.evaluate((acciones) => {
      window.__empujar([{ tipo: 'texto', texto: 'Le preparo un plan de dos pasos.' },
        ...acciones.map((accion) => ({ tipo: 'accion', accion })), { tipo: 'adelanto_fin' }]);
      return performance.now();
    }, D.acciones);
    await empujar([{ tipo: 'fin', motivo: 'listo', limite: { usados: 7, maximo: 300 } }]);
    await page.evaluate(() => window.__cerrar());
    const frase = D.acciones[0].recorrido.escenas[0].frases[0];
    await page.waitForFunction((t) => window.__habla.some((h) => h.texto === t), frase, espera);
    await page.screenshot({ path: `${capturas}/sala-plan.png` });
    salida.habla = await page.evaluate(() => window.__habla.map((h) => ({ ...h })));
    salida.recuadro = await page.evaluate(() => {
      const b = [...document.querySelectorAll('.agente-adelanto')].pop();
      return b && { etiqueta: b.querySelector('.agente-adelanto-et').textContent, texto: b.querySelector('.agente-adelanto-texto').textContent };
    });
    await ctx.close();
  } catch (e) {
    salida.excepcion = String(e.stack || e).slice(0, 1500);
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""
