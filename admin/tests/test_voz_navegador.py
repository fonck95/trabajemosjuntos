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
"""
from test_agente_navegador import _correr, _revisar, panel_vivo, requiere_navegador  # noqa: F401 - la fixture

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
