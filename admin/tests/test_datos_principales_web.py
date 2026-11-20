"""Los datos principales de la ficha en el navegador: el alta y «Completar» van en el orden de los 17 (nombre, cédula,
sexo, edad, teléfono, fecha de nacimiento, correo, dirección, barrio o vereda, zona, líder y votante —con concejal—,
liderado por, perfil profesional, ocupación, estado civil y jefe de hogar), con el puesto y la mesa plegados después;
la sugerencia «¿Es alguna de estas?» sale también con la cédula sola; y P nunca ve ni manda el tipo ni los líderes.

Sin MongoDB: el navegador abre los formularios del panel y la API se responde aquí. Solo personas inventadas."""
import json
import subprocess

from test_agente_mapa import requiere_navegador
from test_formularios_datos import panel_sin_base  # noqa: F401 (fixture)

PRINCIPALES_A = ["Cédula", "Sexo", "Edad", "Teléfono", "Fecha de nacimiento", "Correo electrónico", "Dirección",
                 "Barrio o vereda", "Zona urbana o rural", "Líder · Votante · Concejal", "Liderado por",
                 "Perfil profesional", "Ocupación", "Estado civil", "Jefe de hogar"]
PRINCIPALES_P = [t for t in PRINCIPALES_A if t not in ("Líder · Votante · Concejal", "Liderado por")]

GUION = r"""// Uso: node <guion> <url del panel> <rol>. Abre el alta y «Completar» con el rol dado (la API se responde aquí).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, rol] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errores = [], altas = [], parches = [], asignados = [], parecidas = [];
  page.on('pageerror', (e) => errores.push(e.message));
  const json = (cuerpo) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(cuerpo) });
  await page.route('**/api/lideres', (r) => r.fulfill(json({ personas_con_varios: 0, lideres: [
    { id: 7, nombre: 'BERTA INVENTADA CONCEJAL', tipo: 'concejal', marcado: true, cedula: '1000000002', lugar: null, traidas: 3, votantes: 2, compartidas: 0 }] })));
  await page.route('**/api/parecidas?**', (r) => {
    const u = new URL(r.request().url());
    parecidas.push({ nombre: u.searchParams.get('nombre'), cedula: u.searchParams.get('cedula') });
    return r.fulfill(json(u.searchParams.get('cedula') === '1000000001'
      ? [{ id: 1, nombre: 'ANA INVENTADA DE PRUEBA', cedula_ult3: '001', tiene_cedula: true, lugar: 'EL PRADO', coincide_cedula: 'exacta', cedula_distinta: false }] : []));
  });
  await page.route('**/api/personas', async (r) => {
    if (r.request().method() !== 'POST') return r.continue();
    altas.push(r.request().postDataJSON());
    return r.fulfill({ ...json({ id: 50 + altas.length }), status: 201 });
  });
  await page.route('**/api/personas/9?modo=completar', (r) => { parches.push(r.request().postDataJSON()); return r.fulfill(json({ id: 9, nombre: 'CARLOS INVENTADO' })); });
  await page.route('**/api/personas/9/lideres', (r) => { asignados.push(r.request().postDataJSON()); return r.fulfill({ ...json({ id: 9, nombre: 'CARLOS INVENTADO', lideres: [{ id: 7 }] }), status: 201 }); });
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const src = () => document.querySelector('script[type=module]').src;
  await page.evaluate(async ([rol, src]) => { (await import(new URL('api.js', src).href)).sesion.rol = rol; }, [rol, await page.evaluate(src)]);
  const cat = { lugares: [{ id: 1, nombre: 'EL PRADO', tipo: 'barrio', zona: 'urbana' }], puestos: [], etiquetas: [] };
  const titulos = (sel) => page.$$eval(`${sel} > .campo > span, ${sel} > .grupo-campo > .titulo-campo, ${sel} > details > summary`, (xs) => xs.map((x) => x.textContent.trim()));
  const v = { rol };

  // Alta
  await page.evaluate(async ([cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    m.formularioNuevaPersona({ cat, prellenado: { tipo: 'votante' }, alCrear() {} });
  }, [cat, await page.evaluate(src)]);
  await page.waitForSelector('#f-nueva');
  v.alta = await titulos('#f-nueva');
  v.alta_puesto_plegado = await page.$eval('#alta-votacion', (d) => !d.open && !!d.querySelector('[name=puesto]'));
  v.alta_politico = await page.$$eval('#f-nueva [name=tipo_lider], #f-nueva [name=tipo_votante], #f-nueva [name=tipo_concejal], #f-nueva #bloque-liderado, #f-nueva [data-buscar-lider]', (xs) => xs.length);
  // Solo la cédula (sin nombre): la sugerencia sale igual
  await page.fill('#f-nueva [name=cedula]', '1000000001');
  await page.waitForSelector('#parecidas [data-elegir="1"]', { timeout: 5000 }).catch(() => {});
  v.sugerencia = await page.$$eval('#parecidas .resultado', (xs) => xs.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
  v.parecidas = parecidas.slice();
  await page.fill('#f-nueva [name=cedula]', '');
  if (rol !== 'planillero') {
    // «Liderado por»: buscar por cédula y elegir
    await page.fill('#f-nueva [data-buscar-lider]', '100000000');
    await page.waitForSelector('#f-nueva [data-lider="7"]', { timeout: 5000 });
    await page.click('#f-nueva [data-lider="7"]');
  }
  await page.fill('#f-nueva [name=nombre]', 'CARLA INVENTADA VOTANTE');
  await page.fill('#f-nueva [name=correo]', 'carla.inventada@ejemplo.org');
  await page.fill('#f-nueva [name=perfil_profesional]', 'Contadora');
  await page.selectOption('#f-nueva [name=jefe_hogar]', 'si');
  await page.check('#f-nueva [name=aut_estado][value=no]', { force: true });
  await page.click('#guardar');
  await page.waitForFunction(() => !document.querySelector('#f-nueva'), null, { timeout: 10000 });
  v.alta_cuerpo = altas[0];

  // Completar una ficha con nombre y barrio
  const ficha = { id: 9, nombre: 'CARLOS INVENTADO', lugar_id: 1, lugar_nombre: 'EL PRADO', zona: 'urbana', consentimiento: 'si',
    faltan: ['cedula', 'telefono', 'sexo', 'edad', 'direccion', 'puesto', 'mesa'], votacion: null, lideres: [], no_disponible: {} };
  await page.evaluate(async ([ficha, cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    window.__completar = m.dialogoCompletar(ficha, cat);
  }, [ficha, cat, await page.evaluate(src)]);
  await page.waitForSelector('#f-completar');
  v.completar = await titulos('#f-completar');
  v.completar_cedula_visible = await page.isVisible('#f-completar [name=cedula]');
  v.completar_puesto_plegado = await page.$eval('#completar-votacion', (d) => !d.open && !!d.querySelector('[name=puesto]'));
  v.completar_politico = await page.$$eval('#f-completar [name=tipo_lider], #f-completar [name=tipo_votante], #f-completar [name=tipo_concejal], #f-completar [data-buscar-lider]', (xs) => xs.length);
  await page.fill('#f-completar [name=correo]', 'carlos.inventado@ejemplo.org');
  await page.fill('#f-completar [name=ocupacion]', 'Pescador');
  await page.selectOption('#f-completar [name=estado_civil]', 'Unión libre');
  if (rol !== 'planillero') {
    await page.check('#f-completar [name=tipo_votante]', { force: true });
    await page.fill('#f-completar [data-buscar-lider]', 'berta');
    await page.waitForSelector('#f-completar [data-lider="7"]', { timeout: 5000 });
    await page.click('#f-completar [data-lider="7"]');
  }
  await page.click('[data-guardar="uno"]');
  await page.waitForFunction(() => !document.querySelector('#f-completar'), null, { timeout: 10000 });
  v.completar_cuerpo = parches[0];
  v.asignados = asignados;
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _correr(panel, tmp_path, rol):
    (tmp_path / "principales.cjs").write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "principales.cjs"), panel, rol], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


@requiere_navegador
def test_alta_y_completar_del_administrador(panel_sin_base, tmp_path):  # noqa: F811
    v = _correr(panel_sin_base, tmp_path, "admin")
    assert v["errores"] == []
    # El alta: los 17 en su orden y, después, plegados, el puesto y la mesa (y las necesidades si hay)
    assert v["alta"] == ["Nombre completo *", *PRINCIPALES_A, "Puesto y mesa de votación (opcional)"]
    assert v["alta_puesto_plegado"] is True and v["alta_politico"] == 5 and v["completar_politico"] == 4
    # Con la cédula sola (sin nombre) se piden y se muestran las parecidas, con «Misma cédula»
    assert {"nombre": None, "cedula": "1000000001"} in v["parecidas"]
    assert v["sugerencia"] and "Misma cédula" in v["sugerencia"][0]
    c = v["alta_cuerpo"]
    assert c["votante"] is True and c["lideres"] == [7] and "lider" not in c and "concejal" not in c
    assert (c["correo"], c["perfil_profesional"], c["jefe_hogar"]) == ("carla.inventada@ejemplo.org", "Contadora", True)
    # Completar: los 17 primero (lo que ya tiene, fijo), después el puesto y la mesa plegados y «Más datos»
    assert v["completar"] == ["Nombre", *PRINCIPALES_A, "Puesto y mesa de votación", "Más datos"]
    assert v["completar_cedula_visible"] is True and v["completar_puesto_plegado"] is True
    p = v["completar_cuerpo"]
    assert (p["correo"], p["ocupacion"], p["estado_civil"], p["votante"]) == (
        "carlos.inventado@ejemplo.org", "Pescador", "Unión libre", True)
    assert "lider" not in p and "concejal" not in p and "lideres" not in p and "lugar_id" not in p
    assert v["asignados"] == [{"lider_id": 7}]  # el líder se asigna después de guardar lo demás


@requiere_navegador
def test_alta_y_completar_del_planillero(panel_sin_base, tmp_path):  # noqa: F811
    v = _correr(panel_sin_base, tmp_path, "planillero")
    assert v["errores"] == []
    assert v["alta"] == ["Nombre completo *", *PRINCIPALES_P, "Puesto y mesa de votación (opcional)"]
    assert v["alta_politico"] == 0 and v["completar_politico"] == 0
    assert v["completar"] == ["Nombre", *PRINCIPALES_P, "Puesto y mesa de votación", "Más datos"]
    # P nunca manda el tipo ni los líderes (el servidor le respondería 403)
    for cuerpo in (v["alta_cuerpo"], v["completar_cuerpo"]):
        assert not {"lider", "votante", "concejal", "lideres"} & set(cuerpo), cuerpo
    assert v["asignados"] == []
    assert {"nombre": None, "cedula": "1000000001"} in v["parecidas"]
