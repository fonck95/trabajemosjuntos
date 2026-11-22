"""Editar la ficha de un habitante sin que se pierda lo elegido ni se trabe el guardado (A, K y P), en el computador y
en el celular con las listas como chips:

* Lo cambiado y no guardado en las listas (Sexo, Estado civil, Estrato…) sobrevive a las acciones que vuelven a pintar
  la ficha («No la dio», registrar una visita, asignar un líder…) y se envía al guardar. Antes, una <select> se saltaba
  al devolver lo escrito (`x.length` son sus opciones) y el guardado decía «No hay cambios para guardar».
* En el celular, el bloque que la persona abrió («Más datos») sigue abierto tras volver a pintar.
* Una fecha guardada que hoy no pasaría la revisión (1899-12-30, la fecha cero de Excel) no se borra solo por tocar el
  campo ni frena el guardado de toda la ficha.
* Un 403 por el CSRF de una sesión vieja (otra pestaña ingresó de nuevo) se recupera solo: se toma el de la sesión
  vigente y se reintenta una vez.

Sin MongoDB: el navegador abre la ficha del panel y la API se responde aquí. Solo personas inventadas."""
import json
import subprocess

import pytest

from app import acceso, proyeccion
from test_agente_mapa import requiere_navegador
from test_formularios_datos import panel_sin_base  # noqa: F401 (fixture)

GUION = r"""// Uso: node <guion> <url del panel> <rol> <permisos en JSON> <editables en JSON> <movil: 0|1>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, rol, permisos, editables, movil] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage(movil === '1'
    ? { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }
    : { viewport: { width: 1280, height: 900 } });
  const errores = [], parches = [], tokens = [];
  page.on('pageerror', (e) => errores.push(e.message));
  const json = (cuerpo, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(cuerpo) });
  const ficha = { id: 9, nombre: 'CARLOS INVENTADO EDITA', lugar_id: 1, lugar_nombre: 'EL PRADO', zona: 'urbana',
    consentimiento: 'si', faltan: [], votacion: null, no_disponible: {}, telefonos: [], etiquetas: [], acercamientos: [],
    reuniones: [], sexo: null, estado_civil: null, estrato: null, fecha_nacimiento: '1899-12-30',
    editables: JSON.parse(editables) };
  let primera = true;
  await page.route('**/api/personas/9', (r) => {
    if (r.request().method() === 'PATCH') {
      tokens.push(r.request().headers()['x-csrf-token']);
      // La primera escritura llega con el CSRF de una sesión vieja: el servidor la rechaza antes de la ruta
      if (primera) { primera = false; return r.fulfill(json({ detail: { mensaje: 'Token CSRF inválido; recargue la página', codigo: 'csrf' } }, 403)); }
      const c = r.request().postDataJSON();
      parches.push(c);
      return r.fulfill(json({ ...ficha, ...Object.fromEntries(Object.entries(c).filter(([k]) => k !== 'base')) }));
    }
    return r.fulfill(json(ficha));
  });
  // «No la dio»: la ficha vuelve del servidor y se pinta de nuevo, con lo escrito y no guardado
  await page.route('**/api/personas/9/no-disponible', (r) => r.fulfill(json({ ...ficha, no_disponible: { cedula: { motivo: 'no_la_dio' } } })));
  await page.route('**/api/catalogos**', (r) => r.fulfill(json({ lugares: [{ id: 1, nombre: 'EL PRADO', tipo: 'barrio', zona: 'urbana' }], puestos: [], etiquetas: [], campos: [] })));
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  // La sesión vigente (la de la cookie), con otro CSRF: después de cargar, para que el panel no arranque con ella
  await page.route('**/api/yo', (r) => r.fulfill(json({ uid: 5, usuario: 'usuario5', nombre: 'Usuario de prueba', rol,
    permisos: JSON.parse(permisos), excepto: [], csrf: 'csrf-de-la-sesion-vigente', debe_cambiar_clave: false, compromiso_pendiente: false })));
  const src = await page.evaluate(() => document.querySelector('script[type=module]').src);
  await page.evaluate(async ([rol, permisos, src]) => {
    const a = await import(new URL('api.js', src).href);
    a.configurar({ token: 'csrf-de-una-sesion-vieja', usuario: 'usuario5', uid: 5, rol, permisos: JSON.parse(permisos), excepto: [] });
    const m = await import(new URL('vistas/ficha.js', src).href);
    const el = document.createElement('div');
    el.id = 'prueba-ficha';
    document.body.append(el);
    await m.vistaFicha(el, { params: ['9'], ir() {} });
  }, [rol, permisos, src]);
  await page.waitForSelector('#prueba-ficha #f-datos');
  const f = '#prueba-ficha #f-datos';
  const v = { chips: await page.evaluate(() => document.documentElement.classList.contains('modo-chips')) };
  // Elegir en una lista como lo haría la persona: la lista en el computador, el chip en el celular
  const elegir = async (campo, valor) => {
    if (v.chips) await page.click(`${f} [data-campo="${campo}"] button[data-opcion="${valor}"]`);
    else await page.selectOption(`${f} select[name="${campo}"]`, valor);
  };
  await elegir('sexo', 'F');
  await elegir('estado_civil', 'Casado(a)');
  await page.fill(`${f} [name=ocupacion]`, 'Pescadora');
  if (v.chips) await page.click(`${f} details[data-bloque="mas"] > summary`);
  await elegir('estrato', '3');
  // Tocar la fecha guardada y salir: sigue igual y no frena nada
  await page.click(`${f} [data-campo="fecha_nacimiento"] .campo-escrito > input:first-child`);
  await page.keyboard.press('Tab');
  v.fecha_tras_tocarla = await page.$eval(`${f} [name=fecha_nacimiento]`, (x) => x.value);
  // Una acción que vuelve a pintar la ficha
  await page.click(`${f} [data-nd="cedula"]`);
  await page.waitForSelector(`${f} [data-nd-quitar="cedula"]`);
  v.tras_repintar = await page.$eval(f, (x) => ({ sexo: x.sexo.value, estado_civil: x.estado_civil.value, estrato: x.estrato.value,
    ocupacion: x.ocupacion.value, fecha: x.fecha_nacimiento.value }));
  v.chips_elegidos = await page.$$eval(`${f} .opciones-lista [aria-checked="true"], ${f} .opciones-lista [aria-pressed="true"]`,
    (xs) => xs.map((x) => x.dataset.opcion));
  v.mas_abierto = await page.$eval(`${f} details[data-bloque="mas"]`, (x) => x.open);
  v.votacion_abierto = await page.$eval(`${f} details[data-bloque="votacion"]`, (x) => x.open);
  v.estado_form = await page.$eval('#prueba-ficha #estado-form', (x) => x.textContent.trim());
  await page.$eval(f, (x) => x.requestSubmit());
  await page.waitForFunction(() => document.querySelector('#prueba-ficha #estado-form')?.textContent.trim() === '', null, { timeout: 5000 });
  v.parches = parches;
  v.tokens = tokens;
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""

CASOS = [
    ("planillero", sorted(acceso.PERMISOS["planillero"]), list(proyeccion.EDITABLES_P)),
    ("coordinador", ["*"], list(proyeccion.EDITABLES_A)),
    ("admin", ["*"], list(proyeccion.EDITABLES_A)),
]


@requiere_navegador
@pytest.mark.parametrize("movil", ["0", "1"], ids=["computador", "celular"])
@pytest.mark.parametrize("rol,permisos,editables", CASOS, ids=[c[0] for c in CASOS])
def test_lo_elegido_sobrevive_al_repintado_y_se_guarda(panel_sin_base, tmp_path, rol, permisos, editables, movil):
    guion = tmp_path / "ficha.cjs"
    guion.write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(guion), panel_sin_base, rol, json.dumps(permisos), json.dumps(editables), movil],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    v = json.loads(r.stdout.strip().splitlines()[-1])
    assert v["errores"] == []
    assert v["chips"] is (movil == "1")
    # La fecha guardada (1899-12-30) no se borra al tocarla
    assert v["fecha_tras_tocarla"] == "1899-12-30"
    # Tras «No la dio», lo elegido y lo escrito siguen ahí, también en los chips
    assert v["tras_repintar"] == {"sexo": "F", "estado_civil": "Casado(a)", "estrato": "3", "ocupacion": "Pescadora",
                                  "fecha": "1899-12-30"}
    assert v["estado_form"] == "Cambios sin guardar"
    if movil == "1":
        assert {"F", "Casado(a)", "3"} <= set(v["chips_elegidos"])
        assert v["mas_abierto"] is True and v["votacion_abierto"] is False  # el que abrió sigue abierto; los demás no
    # Se guarda todo lo cambiado, sin tocar la fecha; el 403 del CSRF viejo se reintenta solo con el vigente
    assert len(v["parches"]) == 1
    c = v["parches"][0]
    assert (c["sexo"], c["estado_civil"], c["estrato"], c["ocupacion"]) == ("F", "Casado(a)", 3, "Pescadora")
    assert "fecha_nacimiento" not in c
    assert v["tokens"] == ["csrf-de-una-sesion-vieja", "csrf-de-la-sesion-vigente"]
