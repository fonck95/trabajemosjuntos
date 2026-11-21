"""El tipo de persona y el «Liderado por» del planillero (P) en el navegador: en la ficha de una persona de su zona ve
Líder · Votante · Concejal con los tipos ya marcados fijos (solo suma), el «Liderado por» sin ✕, sin enlace a la ficha
del líder y sin quién lo asignó, y busca al líder en el servidor (GET /api/lideres/candidatos, nunca la lista con los
conteos; una respuesta vieja que llega tarde se descarta); al guardar nunca manda un tipo en «no». En la de otra zona
(la ficha llega sin esas claves) no ve nada de eso. A conserva lo suyo (✕, enlaces y la tarjeta con los conteos). En
«Es esta» y en «Completar», un 403 `fuera_de_zona` o un 409 `lider_quitado` no hacen perder lo demás escrito, el aviso
dice qué líder no se asignó y «Guardar y siguiente» no lo tapa con la persona siguiente. «Nuevo votante» (Habitantes) y
«Registrar votante liderado» (la ficha de un líder) son también de P.

Sin MongoDB: el navegador abre las vistas del panel y la API se responde aquí. Solo personas inventadas."""
import json
import subprocess

from app import acceso
from test_agente_mapa import requiere_navegador
from test_formularios_datos import panel_sin_base  # noqa: F401 (fixture)

PERMISOS = {"planillero": sorted(acceso.PERMISOS["planillero"]), "admin": ["*"]}
FUERA_DE_ZONA = ("Esta persona no es de su zona: su tipo y su «Liderado por» los marcan el administrador, el "
                 "coordinador o quien la tiene asignada")
LIDER_QUITADO = ("El administrador o el coordinador le quitó ese líder a esta persona: pídales que lo vuelvan a "
                 "asignar")

FICHA = r"""// Uso: node <guion> <url del panel> <rol> <permisos en JSON> <caso: dentro|fuera>. La ficha 9 con la API simulada.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, rol, permisos, caso] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errores = [], parches = [], asignados = [], quitados = [], candidatos = [];
  let listaCompleta = 0;
  page.on('pageerror', (e) => errores.push(e.message));
  const json = (cuerpo, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(cuerpo) });
  const adm = rol === 'admin';
  // La ficha como la manda el servidor: con el tipo y el «Liderado por» (sin quién asignó, para P) solo si es de su zona.
  // Las `editables` de P traen también el Líder, que ya tiene: que salga fijo lo decide la interfaz (un tipo marcado no
  // se quita), no la lista
  const ficha = { id: 9, nombre: 'CARLOS INVENTADO LIDER', lugar_id: 1, lugar_nombre: 'EL PRADO', zona: 'urbana',
    consentimiento: 'si', faltan: [], votacion: null, no_disponible: {}, telefonos: [], etiquetas: [], acercamientos: [],
    reuniones: [], editables: adm ? undefined : ['nombre', 'correo', 'ocupacion', ...(caso === 'dentro' ? ['lider', 'concejal', 'votante'] : [])] };
  if (caso === 'dentro') {
    Object.assign(ficha, { lider: true, votante: false, concejal: false, lideres: [
      { id: 3, nombre: 'DORA INVENTADA LIDER', tipo: 'lider', marcado: true, asignado_en: '2026-11-01T12:00:00+00:00' },
      { id: 4, nombre: 'ELSA INVENTADA EXLIDER', tipo: null, marcado: false, asignado_en: '2026-11-02T12:00:00+00:00' }] });
    if (adm) {
      ficha.lideres = ficha.lideres.map((l) => ({ ...l, asignado_por: 'admin' }));
      ficha.traidas = { total: 2, compartidas: 0 };
    }
  }
  await page.route('**/api/personas/9', (r) => {
    if (r.request().method() === 'PATCH') {
      const c = r.request().postDataJSON();
      parches.push(c);
      // Con las mismas `editables`: el tipo recién marcado debe quedar fijo por la regla, no porque falte en la lista
      return r.fulfill(json({ ...ficha, ...Object.fromEntries(Object.entries(c).filter(([k]) => k !== 'base')) }));
    }
    return r.fulfill(json(ficha));
  });
  await page.route('**/api/personas/9/lideres', (r) => {
    asignados.push(r.request().postDataJSON());
    return r.fulfill(json({ ...ficha, lideres: [...ficha.lideres, { id: 7, nombre: 'BERTA INVENTADA CONCEJAL', tipo: 'concejal', marcado: true, asignado_en: '2026-11-21T12:00:00+00:00' }] }, 201));
  });
  await page.route('**/api/personas/9/lideres/*', (r) => { quitados.push(r.request().url()); return r.fulfill(json(ficha)); });
  await page.route('**/api/catalogos**', (r) => r.fulfill(json({ lugares: [{ id: 1, nombre: 'EL PRADO', tipo: 'barrio', zona: 'urbana' }], puestos: [], etiquetas: [], campos: [] })));
  await page.route('**/api/lideres', (r) => { listaCompleta += 1; return r.fulfill(json({ personas_con_varios: 0, lideres: [
    { id: 7, nombre: 'BERTA INVENTADA CONCEJAL', tipo: 'concejal', marcado: true, cedula: '1000000002', lugar: null, traidas: 3, votantes: 2, compartidas: 0 }] })); });
  await page.route('**/api/lideres/candidatos?**', async (r) => {
    const q = new URL(r.request().url()).searchParams.get('q');
    candidatos.push(q);
    // La consulta de «ber» llega tarde, después de la de «bert»: lo que se ve es siempre la última. La de «bert» trae
    // también a un líder que ya tiene (3) y a la persona misma (9): no se ofrecen. La cédula, ya enmascarada, como la
    // manda el servidor
    await new Promise((s) => setTimeout(s, q === 'ber' ? 1200 : 10));
    if (q === 'ber') return r.fulfill(json({ lideres: [{ id: 8, nombre: 'RESPUESTA VIEJA INVENTADA', tipo: 'concejal', lugar: 'EL PRADO', cedula_ult3: '···008' }] }));
    return r.fulfill(json({ lideres: [
      { id: 3, nombre: 'DORA INVENTADA LIDER', tipo: 'lider', lugar: 'EL PRADO', cedula_ult3: '···003' },
      { id: 9, nombre: 'CARLOS INVENTADO LIDER', tipo: 'lider', lugar: 'EL PRADO', cedula_ult3: '···009' },
      { id: 7, nombre: 'BERTA INVENTADA CONCEJAL', tipo: 'concejal', lugar: 'EL PRADO', cedula_ult3: '···002' }] }));
  });
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const src = await page.evaluate(() => document.querySelector('script[type=module]').src);
  await page.evaluate(async ([rol, permisos, src]) => {
    const a = await import(new URL('api.js', src).href);
    a.sesion.rol = rol;
    a.sesion.permisos = JSON.parse(permisos);
    const m = await import(new URL('vistas/ficha.js', src).href);
    const el = document.createElement('div');
    el.id = 'prueba-ficha';
    document.body.append(el);
    await m.vistaFicha(el, { params: ['9'], ir() {} });
  }, [rol, permisos, src]);
  await page.waitForSelector('#prueba-ficha #f-datos');
  const v = { rol, caso };
  const texto = (sel) => page.$eval(sel, (x) => x.textContent.replace(/\s+/g, ' ').trim()).catch(() => null);
  v.tipos = await page.$$eval('#prueba-ficha #f-datos [name=lider], #prueba-ficha #f-datos [name=votante], #prueba-ficha #f-datos [name=concejal]',
    (xs) => Object.fromEntries(xs.map((x) => [x.name, { marcado: x.checked, fijo: x.disabled }])));
  v.notas = await page.$$eval('#prueba-ficha #f-datos .grupo-campo .nota', (xs) => xs.map((x) => x.textContent.trim()));
  v.liderado = await texto('#prueba-ficha .liderado-por');
  v.enlaces_lider = await page.$$eval('#prueba-ficha .liderado-por a', (xs) => xs.length);
  v.quitar = await page.$$eval('#prueba-ficha [data-quitar-lider]', (xs) => xs.length);
  v.buscador = await page.$$eval('#prueba-ficha #buscador-lider-ficha [data-buscar-lider]', (xs) => xs.length);
  v.chips = await texto('#prueba-ficha .cabecera .chips');
  v.tarjeta_conteos = await page.$$eval('#prueba-ficha .lideres-ficha', (xs) => xs.length);
  v.tarjeta_atajo = await texto('#prueba-ficha .atajo-liderado');
  if (!adm && Object.keys(v.tipos).length) {
    // Marca «Votante» y guarda: va en true, sin `base` del tipo y sin el «Líder» (fijo)
    await page.click('#prueba-ficha #f-datos label:has([name=votante])');
    await page.click('#prueba-ficha #f-datos [type=submit]');
    await page.waitForFunction(() => document.querySelector('#prueba-ficha #f-datos [name=votante]')?.disabled, null, { timeout: 5000 });
    v.parche = parches[0];
    v.tipos_despues = await page.$$eval('#prueba-ficha #f-datos [name=lider], #prueba-ficha #f-datos [name=votante], #prueba-ficha #f-datos [name=concejal]',
      (xs) => Object.fromEntries(xs.map((x) => [x.name, { marcado: x.checked, fijo: x.disabled }])));
  }
  if (!adm && v.buscador) {
    const caja = '#prueba-ficha #buscador-lider-ficha';
    // Con menos de 3 letras, la ayuda y ninguna consulta
    await page.fill(`${caja} [data-buscar-lider]`, 'be');
    await page.waitForSelector(`${caja} [data-res-lider] .sec`, { timeout: 5000 });
    v.ayuda = await texto(`${caja} [data-res-lider]`);
    v.candidatos_con_be = candidatos.length;
    // «ber» y enseguida «bert»: la respuesta de «ber» llega después y no pisa la de «bert»
    await page.fill(`${caja} [data-buscar-lider]`, 'ber');
    await new Promise((s) => setTimeout(s, 450));
    await page.fill(`${caja} [data-buscar-lider]`, 'bert');
    await page.waitForSelector(`${caja} [data-lider="7"]`, { timeout: 5000 });
    await new Promise((s) => setTimeout(s, 1500));
    v.resultados = await page.$$eval(`${caja} [data-res-lider] .resultado`, (xs) => xs.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    v.ofrecidos = await page.$$eval(`${caja} [data-lider]`, (xs) => xs.map((x) => x.dataset.lider));
    v.detalles = await page.$$eval(`${caja} [data-res-lider] .resultado small`, (xs) => xs.map((x) => x.textContent.trim()));
    await page.press(`${caja} [data-buscar-lider]`, 'Enter');
    await page.waitForFunction(() => document.querySelectorAll('#prueba-ficha .lider-asignado').length === 3, null, { timeout: 5000 });
  }
  if (await page.$('#prueba-ficha [data-nuevo-liderado]')) {
    await page.click('#prueba-ficha [data-nuevo-liderado]');
    await page.waitForSelector('#f-nueva');
    v.liderado_alta = {
      titulo: await texto('dialog[open] .cab h2'),
      votante: await page.$eval('#f-nueva [name=tipo_votante]', (x) => x.checked).catch(() => null),
      elegidos: await page.$$eval('#f-nueva #lideres-elegidos [data-quitar-elegido]', (xs) => xs.map((x) => x.dataset.quitarElegido)),
      texto: await texto('#f-nueva #lideres-elegidos'),
    };
    await page.click('dialog[open] [data-cerrar]');
  }
  v.parches = parches;
  v.asignados = asignados;
  v.quitados = quitados;
  v.candidatos = candidatos;
  v.lista_completa = listaCompleta;
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""

RESPALDOS = r"""// Uso: node <guion> <url del panel> <permisos en JSON>. «Es esta» fuera de su zona y «Completar» con un líder quitado
// y con una ficha sin el tipo (la API se responde aquí).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, permisos] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errores = [], esEsta = [], asignadosEsEsta = [], parches = [], asignados = [], asignadosDeSuZona = [];
  page.on('pageerror', (e) => errores.push(e.message));
  const json = (cuerpo, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(cuerpo) });
  await page.route('**/api/lideres/candidatos?**', (r) => r.fulfill(json({ lideres: [
    { id: 6, nombre: 'AMELIA INVENTADA LIDER', tipo: 'lider', lugar: null, cedula_ult3: '···006' },
    { id: 7, nombre: 'BERTA INVENTADA CONCEJAL', tipo: 'concejal', lugar: null, cedula_ult3: '···002' },
    { id: 8, nombre: 'BERNARDO INVENTADO LIDER', tipo: 'lider', lugar: null, cedula_ult3: '···003' }] })));
  // Por la cédula: 1000000001 es una ficha de otra zona (1); 1000000005, una de su zona (2)
  await page.route('**/api/parecidas?**', (r) => {
    const suya = new URL(r.request().url()).searchParams.get('cedula') === '1000000005';
    return r.fulfill(json([{ id: suya ? 2 : 1, nombre: suya ? 'INES INVENTADA DE SU ZONA' : 'ANA INVENTADA DE OTRA ZONA',
      cedula_ult3: suya ? '···005' : '···001', tiene_cedula: true, lugar: 'EL PRADO', cedula_distinta: false, coincide_cedula: 'exacta' }]));
  });
  // «Es esta» sobre una ficha de otra zona: el tipo da 403 `fuera_de_zona`; lo demás se guarda
  await page.route('**/api/personas/1?modo=completar', (r) => {
    const c = r.request().postDataJSON();
    esEsta.push(c);
    if ('votante' in c) return r.fulfill(json({ detail: { codigo: 'fuera_de_zona', campo: 'votante', mensaje: process.env.FUERA } }, 403));
    return r.fulfill(json({ id: 1, nombre: 'ANA INVENTADA DE OTRA ZONA' }));
  });
  await page.route('**/api/personas/1/lideres', (r) => { asignadosEsEsta.push(r.request().postDataJSON()); return r.fulfill(json({ id: 1 }, 201)); });
  // «Es esta» sobre una de su zona: el coordinador le quitó los líderes 6 y 8 (409 `lider_quitado`); el 7 se asigna
  await page.route('**/api/personas/2?modo=completar', (r) => r.fulfill(json({ id: 2, nombre: 'INES INVENTADA DE SU ZONA' })));
  await page.route('**/api/personas/2/lideres', (r) => {
    const c = r.request().postDataJSON();
    asignadosDeSuZona.push(c);
    if (c.lider_id !== 7) return r.fulfill(json({ detail: { codigo: 'lider_quitado', campo: 'lider_id', mensaje: process.env.QUITADO } }, 409));
    return r.fulfill(json({ id: 2 }, 201));
  });
  await page.route('**/api/personas/10?modo=completar', (r) => r.fulfill(json({ id: 10, nombre: 'DIANA INVENTADA DE OTRA ZONA' })));
  // «Completar»: el líder 8 se lo quitó el coordinador (409 `lider_quitado`); el 7 se asigna
  await page.route('**/api/personas/9?modo=completar', (r) => { parches.push(r.request().postDataJSON()); return r.fulfill(json({ id: 9, nombre: 'CARLOS INVENTADO' })); });
  await page.route('**/api/personas/9/lideres', (r) => {
    const c = r.request().postDataJSON();
    asignados.push(c);
    if (c.lider_id === 8) return r.fulfill(json({ detail: { codigo: 'lider_quitado', campo: 'lider_id', mensaje: process.env.QUITADO } }, 409));
    return r.fulfill(json({ id: 9, nombre: 'CARLOS INVENTADO', lideres: [{ id: 7 }] }, 201));
  });
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const src = await page.evaluate(() => document.querySelector('script[type=module]').src);
  await page.evaluate(async ([permisos, src]) => {
    const a = await import(new URL('api.js', src).href);
    a.sesion.rol = 'planillero';
    a.sesion.permisos = JSON.parse(permisos);
  }, [permisos, src]);
  const cat = { lugares: [{ id: 1, nombre: 'EL PRADO', tipo: 'barrio', zona: 'urbana' }], puestos: [], etiquetas: [] };
  const v = {};
  const avisos = () => page.$$eval('.aviso', (xs) => xs.map((x) => x.textContent.trim()));

  // «Es esta»: votante marcado y un líder elegido, sobre una ficha de otra zona
  await page.evaluate(async ([cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    window.__creada = null;
    m.formularioNuevaPersona({ cat, prellenado: { tipo: 'votante' }, alCrear(x) { window.__creada = x; } });
  }, [cat, src]);
  await page.waitForSelector('#f-nueva');
  await page.fill('#f-nueva [data-buscar-lider]', 'berta');
  await page.waitForSelector('#f-nueva [data-lider="7"]', { timeout: 5000 });
  await page.click('#f-nueva [data-lider="7"]');
  await page.fill('#f-nueva [name=correo]', 'ana.otra@ejemplo.org');
  await page.fill('#f-nueva [name=cedula]', '1000000001');
  await page.waitForSelector('#parecidas [data-elegir="1"]', { timeout: 5000 });
  await page.click('#parecidas [data-elegir="1"]');
  await page.waitForFunction(() => !document.querySelector('#f-nueva'), null, { timeout: 10000 });
  v.es_esta = esEsta;
  v.asignados_es_esta = asignadosEsEsta;
  v.creada = await page.evaluate(() => window.__creada);
  v.avisos_es_esta = await avisos();

  // «Es esta» sobre una de su zona con tres líderes elegidos: los quitados se dicen por su nombre y el otro se asigna
  await page.evaluate(async ([cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    m.formularioNuevaPersona({ cat, prellenado: { tipo: 'votante' }, alCrear() {} });
  }, [cat, src]);
  await page.waitForSelector('#f-nueva');
  for (const id of ['6', '7', '8']) {
    await page.fill('#f-nueva [data-buscar-lider]', 'inventad');
    await page.waitForSelector(`#f-nueva [data-lider="${id}"]`, { timeout: 5000 });
    await page.click(`#f-nueva [data-lider="${id}"]`);
  }
  await page.fill('#f-nueva [name=cedula]', '1000000005');
  await page.waitForSelector('#parecidas [data-elegir="2"]', { timeout: 5000 });
  await page.click('#parecidas [data-elegir="2"]');
  await page.waitForFunction(() => !document.querySelector('#f-nueva'), null, { timeout: 10000 });
  v.asignados_de_su_zona = asignadosDeSuZona;
  v.avisos_de_su_zona = await avisos();

  // «Completar» con dos líderes elegidos: el quitado se salta con su aviso y el otro se asigna
  const ficha = { id: 9, nombre: 'CARLOS INVENTADO', lugar_id: 1, lugar_nombre: 'EL PRADO', zona: 'urbana', consentimiento: 'si',
    faltan: ['ocupacion'], votacion: null, lider: true, votante: false, concejal: false, lideres: [], no_disponible: {} };
  await page.evaluate(async ([ficha, cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    window.__completar = m.dialogoCompletar(ficha, cat, { siguiente: true });
  }, [ficha, cat, src]);
  await page.waitForSelector('#f-completar');
  v.completar_tipos = await page.$$eval('#f-completar [name=tipo_lider], #f-completar [name=tipo_votante], #f-completar [name=tipo_concejal]',
    (xs) => Object.fromEntries(xs.map((x) => [x.name, { marcado: x.checked, fijo: x.disabled }])));
  v.completar_nota = await page.$$eval('#f-completar .grupo-campo .nota', (xs) => xs.map((x) => x.textContent.trim()));
  await page.check('#f-completar [name=tipo_votante]', { force: true });
  for (const id of ['8', '7']) {
    await page.fill('#f-completar [data-buscar-lider]', 'bern');
    await page.waitForSelector(`#f-completar [data-lider="${id}"]`, { timeout: 5000 });
    // El ya elegido (8) no se vuelve a ofrecer
    if (id === '7') v.ofrecidos_despues = await page.$$eval('#f-completar [data-lider]', (xs) => xs.map((x) => x.dataset.lider));
    await page.click(`#f-completar [data-lider="${id}"]`);
  }
  await page.fill('#f-completar [name=ocupacion]', 'Pescador');
  // «Guardar y siguiente»: con un líder que no se asignó, no sigue (el aviso quedaría debajo del diálogo siguiente)
  await page.click('[data-guardar="siguiente"]');
  await page.waitForFunction(() => !document.querySelector('#f-completar'), null, { timeout: 10000 });
  v.completar_cuerpo = parches[0];
  v.asignados = asignados;
  v.avisos_completar = await avisos();
  v.completar_siguiente = await page.evaluate(async () => (await window.__completar)?.siguiente);

  // «Completar» una ficha de otra zona (sin las claves): nada político
  const otra = { id: 10, nombre: 'DIANA INVENTADA DE OTRA ZONA', lugar_id: 1, lugar_nombre: 'EL PRADO', zona: 'urbana', consentimiento: 'si',
    faltan: ['ocupacion'], votacion: null, no_disponible: {} };
  await page.evaluate(async ([otra, cat, src]) => {
    const m = await import(new URL('vistas/comunes.js', src).href);
    window.__otra = m.dialogoCompletar(otra, cat, { siguiente: true });
  }, [otra, cat, src]);
  await page.waitForSelector('#f-completar');
  v.otra_politico = await page.$$eval('#f-completar [name^=tipo_], #f-completar [data-buscar-lider], #f-completar #lideres-completar', (xs) => xs.length);
  // Sin líderes omitidos, «Guardar y siguiente» sigue
  await page.fill('#f-completar [name=ocupacion]', 'Docente');
  await page.click('[data-guardar="siguiente"]');
  await page.waitForFunction(() => !document.querySelector('#f-completar'), null, { timeout: 10000 });
  v.otra_siguiente = await page.evaluate(async () => (await window.__otra)?.siguiente);
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""

HABITANTES = r"""// Uso: node <guion> <url del panel> <rol> <permisos en JSON>. Habitantes con la API simulada: el botón «Nuevo
// votante» y el alta que abre.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, rol, permisos] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errores = [];
  page.on('pageerror', (e) => errores.push(e.message));
  const json = (cuerpo) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(cuerpo) });
  await page.route('**/api/catalogos**', (r) => r.fulfill(json({ lugares: [{ id: 1, nombre: 'EL PRADO', tipo: 'barrio', zona: 'urbana' }], puestos: [], etiquetas: [], campos: [] })));
  await page.route('**/api/personas?**', (r) => r.fulfill(json({ total: 0, pagina: 1, por_pagina: 50, filas: [] })));
  await page.route('**/api/lideres', (r) => r.fulfill(json({ personas_con_varios: 0, lideres: [] })));
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const src = await page.evaluate(() => document.querySelector('script[type=module]').src);
  await page.evaluate(async ([rol, permisos, src]) => {
    const a = await import(new URL('api.js', src).href);
    a.sesion.rol = rol;
    a.sesion.permisos = JSON.parse(permisos);
    const m = await import(new URL('vistas/personas.js', src).href);
    const el = document.createElement('div');
    el.id = 'prueba-habitantes';
    document.body.append(el);
    await m.vistaPersonas(el, { q: new URLSearchParams(), ir() {} });
  }, [rol, permisos, src]);
  await page.waitForSelector('#prueba-habitantes #filas');
  const v = { boton: !!(await page.$('#prueba-habitantes #nuevo-votante')), nueva: !!(await page.$('#prueba-habitantes #nueva')) };
  if (v.boton) {
    await page.click('#prueba-habitantes #nuevo-votante');
    await page.waitForSelector('#f-nueva');
    v.titulo = await page.$eval('dialog[open] .cab h2', (x) => x.textContent.trim());
    v.votante = await page.$eval('#f-nueva [name=tipo_votante]', (x) => x.checked);
    v.liderado = !!(await page.$('#f-nueva #bloque-liderado [data-buscar-lider]'));
  }
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _correr(tmp_path, nombre, guion, *args, env=None):
    import os
    (tmp_path / nombre).write_text(guion, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / nombre), *args], capture_output=True, text=True, timeout=120,
                       env={**os.environ, **(env or {})})
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def _ficha(panel, tmp_path, rol, caso):
    return _correr(tmp_path, "ficha.cjs", FICHA, panel, rol, json.dumps(PERMISOS[rol]), caso)


@requiere_navegador
def test_ficha_del_planillero_en_su_zona(panel_sin_base, tmp_path):  # noqa: F811
    v = _ficha(panel_sin_base, tmp_path, "planillero", "dentro")
    assert v["errores"] == []
    # El tipo: el marcado, fijo (aunque venga en `editables`: un tipo marcado no se quita); los que faltan, para marcar;
    # y la nota de que solo A o K lo quitan
    assert v["tipos"] == {"lider": {"marcado": True, "fijo": True}, "votante": {"marcado": False, "fijo": False},
                          "concejal": {"marcado": False, "fijo": False}}
    assert "Un tipo marcado solo lo quita el administrador o el coordinador." in v["notas"]
    # «Liderado por»: los nombres como texto, sin ✕ ni enlace, sin «por …»; «ya no marcado» solo para el que lo dejó
    assert "DORA INVENTADA LIDER" in v["liderado"] and "ELSA INVENTADA EXLIDER" in v["liderado"]
    assert v["liderado"].count("ya no marcado como líder ni concejal") == 1 and "por admin" not in v["liderado"]
    assert v["enlaces_lider"] == 0 and v["quitar"] == 0 and v["buscador"] == 1
    assert "Líder" in v["chips"] and "2 líderes" in v["chips"]
    # La tarjeta con los conteos es de A y K; P, en la ficha de un líder, solo el atajo para registrar a su votante
    assert v["tarjeta_conteos"] == 0 and "Registrar votante liderado" in v["tarjeta_atajo"]
    # Guardar: solo el tipo que marcó, en true, sin `base` del tipo ni el Líder (fijo); después, también fijo, aunque la
    # respuesta lo siga trayendo en `editables`
    assert v["parche"] == {"votante": True}
    assert v["tipos_despues"] == {"lider": {"marcado": True, "fijo": True}, "votante": {"marcado": True, "fijo": True},
                                  "concejal": {"marcado": False, "fijo": False}}
    # El líder se busca en el servidor: con menos de 3 letras, la ayuda; la respuesta vieja no pisa la nueva; Enter
    # elige el primero
    assert v["candidatos_con_be"] == 0 and "3 letras" in v["ayuda"]
    assert v["candidatos"] == ["ber", "bert"]
    assert len(v["resultados"]) == 1 and "BERTA INVENTADA CONCEJAL" in v["resultados"][0]
    assert "RESPUESTA VIEJA" not in json.dumps(v["resultados"], ensure_ascii=False)
    # Ni la persona misma ni un líder que ya tiene; la cédula tal como la enmascara el servidor, sin conteos
    assert v["ofrecidos"] == ["7"]
    assert v["detalles"] == ["Concejal · cédula ···002 · El Prado"]
    assert v["asignados"] == [{"lider_id": 7}] and v["quitados"] == [] and v["lista_completa"] == 0
    assert all("lider" not in c and "concejal" not in c for c in v["parches"])
    # «Registrar votante liderado»: el alta de un votante con esta persona ya elegida en «Liderado por»
    alta = v["liderado_alta"]
    assert (alta["titulo"], alta["votante"], alta["elegidos"]) == ("Nuevo votante", True, ["9"])
    assert "CARLOS INVENTADO LIDER" in alta["texto"]


@requiere_navegador
def test_ficha_del_planillero_fuera_de_su_zona(panel_sin_base, tmp_path):  # noqa: F811
    v = _ficha(panel_sin_base, tmp_path, "planillero", "fuera")
    assert v["errores"] == []
    assert v["tipos"] == {} and v["liderado"] is None and v["buscador"] == 0
    assert v["tarjeta_conteos"] == 0 and v["tarjeta_atajo"] is None
    assert not any(t in (v["chips"] or "") for t in ("Líder", "Votante", "Concejal"))
    assert v["candidatos"] == [] and v["lista_completa"] == 0 and v["asignados"] == []
    assert "liderado_alta" not in v


@requiere_navegador
def test_ficha_del_administrador_sin_cambios(panel_sin_base, tmp_path):  # noqa: F811
    v = _ficha(panel_sin_base, tmp_path, "admin", "dentro")
    assert v["errores"] == []
    # A marca y quita cualquier tipo, quita líderes, abre su ficha y ve la tarjeta con los conteos
    assert v["tipos"] == {"lider": {"marcado": True, "fijo": False}, "votante": {"marcado": False, "fijo": False},
                          "concejal": {"marcado": False, "fijo": False}}
    assert "Un tipo marcado solo lo quita el administrador o el coordinador." not in v["notas"]
    assert v["quitar"] == 2 and v["enlaces_lider"] == 2 and "por admin" in v["liderado"]
    assert v["tarjeta_conteos"] == 1 and v["tarjeta_atajo"] is None and v["buscador"] == 1
    alta = v["liderado_alta"]
    assert (alta["titulo"], alta["votante"], alta["elegidos"]) == ("Nuevo votante", True, ["9"])


@requiere_navegador
def test_es_esta_y_completar_no_pierden_lo_escrito(panel_sin_base, tmp_path):  # noqa: F811
    v = _correr(tmp_path, "respaldos.cjs", RESPALDOS, panel_sin_base, json.dumps(PERMISOS["planillero"]),
                env={"FUERA": FUERA_DE_ZONA, "QUITADO": LIDER_QUITADO})
    assert v["errores"] == []
    # «Es esta» fuera de su zona: el 403 del tipo, y se repite sin él; no se asignan líderes; un aviso lo dice
    primero, segundo = v["es_esta"]
    assert primero["votante"] is True and primero["correo"] == "ana.otra@ejemplo.org"
    assert "votante" not in segundo and segundo["correo"] == "ana.otra@ejemplo.org"
    assert v["asignados_es_esta"] == [] and v["creada"] == {"id": 1, "existente": True}
    assert any(a.startswith("Se completó la ficha, pero esta persona no es de su zona") for a in v["avisos_es_esta"])
    # «Es esta» en una de su zona: los líderes quitados se saltan y el aviso dice cuáles; el otro se asigna
    assert v["asignados_de_su_zona"] == [{"lider_id": 6}, {"lider_id": 7}, {"lider_id": 8}]
    quitado = "el administrador o el coordinador le quitó ese líder a esta persona: pídales que lo vuelvan a asignar"
    assert (f"Se completó la ficha, pero no se asignó a Amelia Inventada Lider: {quitado}; no se asignó a Bernardo "
            f"Inventado Lider: {quitado}.") in v["avisos_de_su_zona"]
    # «Completar»: el tipo ya marcado, fijo y con su nota; el nuevo, en true; el líder quitado se salta con su aviso
    assert v["completar_tipos"]["tipo_lider"] == {"marcado": True, "fijo": True}
    assert "Completar solo suma: un tipo marcado lo quita el administrador o el coordinador." in v["completar_nota"]
    c = v["completar_cuerpo"]
    assert c["votante"] is True and c["ocupacion"] == "Pescador" and "lider" not in c and "concejal" not in c
    assert v["asignados"] == [{"lider_id": 8}, {"lider_id": 7}]
    assert "8" not in v["ofrecidos_despues"] and "7" in v["ofrecidos_despues"]  # el ya elegido no se ofrece otra vez
    assert (f"Se guardaron los datos, pero no se asignó a Bernardo Inventado Lider: el administrador o el coordinador "
            f"le quitó ese líder a esta persona: pídales que lo vuelvan a asignar.") in v["avisos_completar"]
    # Con un líder omitido, «Guardar y siguiente» no abre a la siguiente persona: su diálogo taparía el aviso
    assert v["completar_siguiente"] is False
    # Una ficha de otra zona (sin el tipo ni los líderes): nada político; sin omitidos, «Guardar y siguiente» sigue
    assert v["otra_politico"] == 0 and v["otra_siguiente"] is True


@requiere_navegador
def test_nuevo_votante_en_habitantes_para_quien_marca_el_tipo(panel_sin_base, tmp_path):  # noqa: F811
    """«Nuevo votante» (el alta con Votante marcado y la barra «Liderado por») es de quien marca el tipo y registra: A,
    K y P. Un planillero sin `personas.tipo` solo ve «Nueva persona»; el consultor, ninguno de los dos."""
    casos = {"planillero": acceso.PERMISOS["planillero"], "admin": {"*"},
             "sin_tipo": acceso.PERMISOS["planillero"] - {"personas.tipo"}, "consultor": acceso.PERMISOS["consultor"]}
    vistas = {}
    for caso, permisos in casos.items():
        rol = "planillero" if caso == "sin_tipo" else caso
        vistas[caso] = _correr(tmp_path, "habitantes.cjs", HABITANTES, panel_sin_base, rol, json.dumps(sorted(permisos)))
        assert vistas[caso]["errores"] == [], (caso, vistas[caso]["errores"])
    for caso in ("planillero", "admin"):
        v = vistas[caso]
        assert v["boton"] and v["nueva"], caso
        assert (v["titulo"], v["votante"], v["liderado"]) == ("Nuevo votante", True, True), (caso, v)
    assert not vistas["sin_tipo"]["boton"] and vistas["sin_tipo"]["nueva"]
    assert not vistas["consultor"]["boton"] and not vistas["consultor"]["nueva"]
