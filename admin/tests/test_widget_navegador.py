"""Las fotos de planillas y los gráficos del asistente en un navegador de verdad (Chromium con Playwright), contra el
panel de verdad (uvicorn, en /panel como en Railway). Las rutas del asistente y de la bandeja de planillas se
contestan desde el navegador (`route.fulfill`): la subida está simulada y nunca se llama a un modelo. Las fotos son
imágenes inventadas que la prueba genera con Pillow (renglones y cuadrícula, ruido, una oscura, una con EXIF girado).

* `escritorio`: la cámara aparece solo con `adjuntos` en el estado; la bandeja con el aviso fijo; «Elegir de la
  galería» abre un selector múltiple y entran como mucho 4; cada foto se prepara de a una (nunca hay dos imágenes
  abiertas a la vez), se reduce a `lado_max`, se vuelve a codificar como JPEG sin EXIF (derecha según su EXIF) y por
  debajo de `max_bytes` (bajando la calidad y, si no alcanza, el tamaño), y se sube cruda; los avisos (pequeña, oscura)
  y el error de lo que no es una imagen. Con una foto que falló no se envía; quitarla, girar (sube la girada y borra la
  anterior) y quitar una subida (la borra de la bandeja). El mensaje lleva los ids en `adjuntos`; la burbuja, el chip.
  El turno trae gráficos: se dibujan debajo de su herramienta, uno que no cumple el contrato no, y nada entra como HTML.
  «Tomar foto» abre el selector de la cámara; enviar con la foto subiendo la manda sola al terminar (un mensaje solo de
  fotos); «Reintentar» y «Nueva conversación» la conservan. Una subida que falla se reintenta desde la memoria. Al
  repintar una conversación guardada: el chip de fotos y el gráfico de la herramienta.
* `movil` (390 × 844, táctil) y `chico` (320 × 568): cuatro fotos en la bandeja sin desborde, el panel y el cuadro de
  escribir dentro de la pantalla, y la indicación del cuadro en un renglón.
En todos: sin errores de página ni de consola, sin violaciones de CSP. Se salta si no hay Node con Playwright, salvo en
el CI (allí falla).
"""
import json
import os
import random
import subprocess
from pathlib import Path

import pytest

from test_agente_navegador import _servir, requiere_navegador

AVISO = ("Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o políticas. Borre la "
         "foto del teléfono.")


def _imagenes(dir_: Path) -> dict[str, str]:
    """Las fotos inventadas, en `dir_`: {nombre: ruta}."""
    from PIL import Image, ImageDraw, ImageFilter

    azar = random.Random(41)

    def planilla(ancho, alto, tinta=30, fondo=232):
        im = Image.new("L", (ancho, alto), fondo)
        d = ImageDraw.Draw(im)
        paso = max(12, alto // 40)
        for y in range(0, alto, paso * 3):
            d.line([(0, y), (ancho, y)], fill=tinta, width=2)
        for x in range(0, ancho, ancho // 12):
            d.line([(x, 0), (x, alto)], fill=tinta, width=2)
        for y in range(paso, alto - paso, paso * 3):   # «letra»: trazos cortos de 1–3 px
            for _ in range(ancho // 18):
                x = azar.randrange(0, ancho - 20)
                d.line([(x, y), (x + azar.randrange(4, 16), y + azar.randrange(-6, 7))], fill=tinta,
                       width=azar.randrange(1, 4))
        return im.convert("RGB")

    out = {}
    planilla(3000, 2250).save(dir_ / "nitida.jpg", quality=92)
    out["nitida"] = str(dir_ / "nitida.jpg")
    planilla(1000, 700).save(dir_ / "pequena.png")
    out["pequena"] = str(dir_ / "pequena.png")
    planilla(2000, 1500, tinta=5, fondo=40).save(dir_ / "oscura.jpg", quality=90)
    out["oscura"] = str(dir_ / "oscura.jpg")
    # Guardada acostada (2400 × 1800) con EXIF Orientation = 6: se ve parada (1800 × 2400)
    exif = Image.Exif()
    exif[0x0112] = 6
    planilla(2400, 1800).save(dir_ / "exif.jpg", quality=90, exif=exif)
    out["exif"] = str(dir_ / "exif.jpg")
    # Ruido: pesa mucho como JPEG (obliga a bajar la calidad y después el tamaño)
    Image.effect_noise((2400, 1800), 90).convert("RGB").filter(ImageFilter.SMOOTH).save(dir_ / "ruido.jpg", quality=95)
    out["ruido"] = str(dir_ / "ruido.jpg")
    (dir_ / "no_es_imagen.jpg").write_bytes(b"Esto no es una imagen, aunque diga .jpg\n" * 50)
    out["no_es_imagen"] = str(dir_ / "no_es_imagen.jpg")
    planilla(150, 100).save(dir_ / "diminuta.png")
    out["diminuta"] = str(dir_ / "diminuta.png")
    return out


def _correr(tmp_path, *args: str) -> dict:
    guion = tmp_path / "fotos.cjs"
    guion.write_text(GUION, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)
    r = subprocess.run(["node", str(guion), *args, capturas], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    if os.environ.get("CAPTURAS_AGENTE"):  # para mirarlo a mano
        (Path(capturas) / "resultado-fotos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    return res


@requiere_navegador
def test_fotos_y_graficos_en_chromium(cfg, tmp_path):
    imagenes = _imagenes(tmp_path)
    with _servir(cfg, tmp_path) as (base, _, _ids, _):
        res = _correr(tmp_path, base, cfg.usuario, cfg.clave, json.dumps(imagenes))
    assert [c["nombre"] for c in res["casos"]] == ["escritorio", "movil", "chico"]
    for caso in res["casos"]:
        malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
        assert not malas, (caso["nombre"], malas, caso.get("datos"))
        assert caso["errores"] == [], (caso["nombre"], caso["errores"])
        assert caso["csp"] == [], (caso["nombre"], caso["csp"])
    esc = res["casos"][0]
    subidas = esc["subidas"]
    # Las subidas: JPEG enteros (SOI y EOI), sin EXIF, con el lado mayor ≤ 2000 y ≤ 600 000 bytes, de a una
    assert len(subidas) == 8, subidas
    for s in subidas:
        assert s["tipo"] == "image/jpeg" and s["soi"] and s["eoi"] and not s["exif"], s
        assert max(s["ancho"], s["alto"]) <= 2000 and s["bytes"] <= 600000, s
        assert s["csrf"], "la subida lleva el token CSRF"
    assert [(s["ancho"], s["alto"]) for s in subidas[:3]] == [(2000, 1500), (1000, 700), (2000, 1500)]
    # Girada: los lados cambiados
    assert (subidas[3]["ancho"], subidas[3]["alto"]) == (1500, 2000)
    # La del EXIF: derecha (parada)
    assert (subidas[4]["ancho"], subidas[4]["alto"]) == (1500, 2000)
    # La de ruido: más chica que 2000 (con la calidad más baja no cabía) y bajo el tope
    assert max(subidas[6]["ancho"], subidas[6]["alto"]) < 2000 and subidas[5]["estado"] == 503
    # Una a la vez: cada subida empieza después de que terminó la anterior
    for a, b in zip(subidas, subidas[1:]):
        assert b["inicio"] >= a["fin"] - 5, (a, b)
    # Lo que se borró de la bandeja: la anterior a girar, la que se quitó, y la del reintento al girarla y al quitarla
    # (ninguna llegó en un mensaje). La que llegó en un mensaje (f5) no
    assert esc["borradas"] == ["f1", "f3", "f7", "f8"], esc["borradas"]
    m = [x["cuerpo"] for x in esc["mensajes"]]
    assert len(m) == 4, m
    assert m[0]["texto"] == "Revisa estas planillas" and m[0]["adjuntos"] == ["f4", "f2"]
    assert m[0]["conversacion"] is None
    # Solo fotos (sin texto), enviado al terminar de subir; «Reintentar» repite lo mismo; «Nueva conversación» lo trae
    assert m[1] == {**m[1], "texto": "", "adjuntos": ["f5"], "conversacion": 61}
    assert m[2]["adjuntos"] == ["f5"] and m[2]["texto"] == "" and m[2]["conversacion"] == 61
    assert m[3]["adjuntos"] == ["f5"] and m[3]["texto"] == "" and m[3]["conversacion"] is None
    assert esc["mensajes"][1]["t"] >= subidas[4]["fin"]


GUION = r"""// Uso: node <guion> <base del panel> <usuario> <clave> <imágenes (JSON)> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, imagenesJson, capturas] = process.argv.slice(2);
const IMG = JSON.parse(imagenesJson);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const AVISO = 'Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o políticas. Borre la foto del teléfono.';
const ADJUNTOS = { max_por_mensaje: 4, lado_max: 2000, calidad: 0.8, max_bytes: 600000 };
const ESTADO = { disponible: true, motivo: null, configurado: true, es_admin: true, escritura: true, limite: { usados: 3, maximo: 300 },
  mnemo: { activo: false, origen: null }, sugerencias: [], adjuntos: ADJUNTOS };
const H = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: 'analizar', etiqueta: 'Analizando la base', estado, ...(resumen ? { resumen } : {}) });
const G_BARRAS = { tipo: 'grafico', clase: 'barras', titulo: 'Personas por zona', unidad: 'personas',
  items: [{ etiqueta: 'Rural', valor: 120 }, { etiqueta: 'Urbana', valor: 80 }], nota: 'Sin quienes no autorizaron.' };
const G_SERIE = { tipo: 'grafico', clase: 'serie', titulo: 'Altas por mes', unidad: 'altas',
  items: [{ etiqueta: '2026-08', valor: 10 }, { etiqueta: '2026-09', valor: 25 }, { etiqueta: '2026-10', valor: 40 }] };
const G_MALO = { tipo: 'grafico', clase: 'pastel', titulo: 'No se dibuja', items: [{ etiqueta: 'a', valor: 1 }] };
const XSS = '<img src=x onerror="window.__xss=1">';
const G_XSS = { tipo: 'grafico', clase: 'columnas', titulo: XSS, items: [{ etiqueta: XSS, valor: 3, color: 'red;background:url(https://malo.example/x)' }] };
const G_APILADA = { tipo: 'grafico', clase: 'apilada', titulo: 'Autorizaciones', unidad: 'personas',
  items: [{ etiqueta: 'Sí', valor: 70 }, { etiqueta: 'Pendiente', valor: 25 }, { etiqueta: 'Por confirmar', valor: 5 }] };
const TURNO_FOTOS = [
  { tipo: 'inicio', conversacion: 61, titulo: 'Planillas' },
  H('toolu_g', 'inicio'), H('toolu_g', 'ok', '2 zonas'), { tipo: 'accion', accion: G_BARRAS },
  H('toolu_h', 'inicio'), H('toolu_h', 'ok', '3 meses'), { tipo: 'accion', accion: G_SERIE }, { tipo: 'accion', accion: G_MALO },
  { tipo: 'accion', accion: G_XSS },
  { tipo: 'texto', texto: 'Leí las dos planillas.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } },
];
const CORTO = [{ tipo: 'inicio', conversacion: 62, titulo: 'Fotos' }, { tipo: 'texto', texto: 'Recibí la foto.' },
  { tipo: 'fin', motivo: 'listo', limite: { usados: 5, maximo: 300 } }];
const RESPUESTAS = [
  TURNO_FOTOS,
  { estado: 503, detail: { codigo: 'saturado', mensaje: 'El asistente está atendiendo muchas conversaciones a la vez. Intente de nuevo en unos segundos.' } },
  { estado: 409, detail: { codigo: 'proveedor', mensaje: 'Esta conversación se empezó con un modelo que ya no está disponible: empiece una nueva.' } },
  CORTO,
];
const LISTA = { conversaciones: [{ id: 41, titulo: 'Planillas de ayer', actualizada: '2026-11-20T15:00:00+00:00', pendiente: false }] };
const CONV = { 41: { id: 41, titulo: 'Planillas de ayer', pendientes: [], mensajes: [
  { rol: 'usuario', texto: '', adjuntos: [{ id: 'aa1', ancho: 1500, alto: 2000 }, { id: 'aa2' }, { id: 'aa3' }] },
  { rol: 'asistente', partes: [{ ...H('toolu_r', 'ok', 'listo'), grafico: G_APILADA }, { tipo: 'texto', texto: 'Así quedaron.' }] },
  { rol: 'usuario', texto: 'Y esta otra', adjuntos: [{ id: 'aa4' }] },
  { rol: 'usuario', texto: '', adjuntos: 'no es una lista' },
] } };
// Lo que hace cada subida, por número (1 en adelante): una demora antes de responder o un error
const PLAN = { 5: { demora: 2500 }, 6: { estado: 503 } };
const nd = (evs) => evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
const ahora = () => Date.now();

/** Lo que hay en un JPEG: SOI, EOI, si trae EXIF (APP1) y su tamaño (SOF). */
function jpeg(b) {
  const r = { soi: b[0] === 0xff && b[1] === 0xd8, eoi: b[b.length - 2] === 0xff && b[b.length - 1] === 0xd9, exif: false, ancho: null, alto: null };
  let i = 2;
  while (i + 4 < b.length && b[i] === 0xff) {
    const marca = b[i + 1];
    if (marca === 0xd9 || marca === 0xda) break;
    const largo = b.readUInt16BE(i + 2);
    if (marca === 0xe1 && b.slice(i + 4, i + 8).toString('latin1') === 'Exif') r.exif = true;
    if (marca >= 0xc0 && marca <= 0xc3) { r.alto = b.readUInt16BE(i + 5); r.ancho = b.readUInt16BE(i + 7); }
    i += 2 + largo;
  }
  return r;
}

async function servir(ctx, reg) {
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/') || u.pathname.startsWith(pref + '/api/planillas'), async (route) => {
    const req = route.request();
    const ruta = new URL(req.url()).pathname.slice(pref.length);
    const metodo = req.method();
    const json = (d, status = 200, extra = {}) => route.fulfill({ status, contentType: 'application/json', headers: extra, body: JSON.stringify(d) });
    if (metodo === 'GET' && ruta === '/api/agente/estado') return json(reg.estado);
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') return json(LISTA);
    const c = /^\/api\/agente\/conversaciones\/(\d+)$/.exec(ruta);
    if (c && metodo === 'GET') return json(CONV[c[1]] || { detail: 'No existe' }, CONV[c[1]] ? 200 : 404);
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      reg.mensajes.push({ cuerpo: req.postDataJSON(), t: ahora() });
      const r = RESPUESTAS[reg.mensajes.length - 1];
      if (!Array.isArray(r)) return json({ detail: r.detail }, r.estado, { 'x-prueba': 'esperado' });
      return route.fulfill({ status: 200, contentType: 'application/x-ndjson', headers: { 'cache-control': 'no-store' }, body: nd(r) });
    }
    if (metodo === 'POST' && ruta === '/api/planillas/fotos') {
      const n = reg.subidas.length + 1;
      const cuerpo = req.postDataBuffer() || Buffer.alloc(0);
      const s = { n, inicio: ahora(), tipo: req.headers()['content-type'], csrf: !!req.headers()['x-csrf-token'], bytes: cuerpo.length, ...jpeg(cuerpo) };
      reg.subidas.push(s);
      const plan = PLAN[n] || {};
      if (plan.demora) await new Promise((ok) => setTimeout(ok, plan.demora));
      s.fin = ahora();
      if (plan.estado) {
        s.estado = plan.estado;
        return json({ detail: { codigo: 'saturado', mensaje: 'El panel está ocupado: intente de nuevo en un momento.' } }, plan.estado, { 'x-prueba': 'esperado' });
      }
      s.estado = 201;
      return json({ id: `f${n}`, estado: 'leyendo', bytes: cuerpo.length, ancho: s.ancho, alto: s.alto, expira: '2026-11-24T12:00:00+00:00' }, 201);
    }
    const b = /^\/api\/planillas\/([A-Za-z0-9_-]+)$/.exec(ruta);
    if (b && metodo === 'DELETE') { reg.borradas.push(b[1]); return json({ ok: true }); }
    return json({ detail: 'No existe' }, 404);
  });
}

const espera = { timeout: 20000 };
async function ingresar(page) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
}
const terminadas = (page) => page.waitForFunction(() => [...document.querySelectorAll('#agente-fotos-lista .agente-foto')]
  .every((li) => !['preparando', 'subiendo'].includes(li.dataset.estado)), null, espera);
const fotosEnBandeja = (page) => page.evaluate(() => [...document.querySelectorAll('#agente-fotos-lista .agente-foto')].map((li) => ({
  estado: li.dataset.estado, titulo: li.querySelector('b').textContent, linea: li.querySelector('.agente-foto-estado').textContent,
  avisos: li.querySelector('.agente-foto-avisos').hidden ? '' : li.querySelector('.agente-foto-avisos').textContent,
  reintentar: !li.querySelector('.agente-foto-reintentar').hidden, girar: !li.querySelector('.agente-foto-girar').disabled,
  pintada: (() => { const c = li.querySelector('canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    for (let i = 3; i < d.length; i += 4) if (d[i]) return true; return false; })() })));
const listo = (page) => page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
async function elegir(page, boton, archivos) {
  const [ch] = await Promise.all([page.waitForEvent('filechooser', espera), page.click(boton)]);
  const multiple = ch.isMultiple();
  await ch.setFiles(archivos);
  return multiple;
}

async function escritorio(page, caso, reg) {
  const v = caso.revisiones, d = caso.datos;
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-adjuntar:not([hidden])', espera);
  v.bandeja_cerrada_al_principio = await page.evaluate(() => document.querySelector('#agente-fotos').hidden);
  await page.click('#agente-adjuntar');
  v.bandeja_con_el_aviso = await page.evaluate((aviso) => !document.querySelector('#agente-fotos').hidden
    && document.querySelector('#agente-fotos-aviso').textContent.trim() === aviso
    && document.querySelector('#agente-adjuntar').getAttribute('aria-expanded') === 'true', AVISO);
  v.selectores = await page.evaluate(() => {
    const c = document.querySelector('#agente-foto-camara-in'), g = document.querySelector('#agente-foto-galeria-in');
    return c.getAttribute('capture') === 'environment' && !c.multiple && g.multiple && !g.hasAttribute('capture');
  });
  // La galería: cinco archivos, entran cuatro (el quinto no)
  v.galeria_multiple = await elegir(page, '#agente-foto-galeria',
    [IMG.nitida, IMG.pequena, IMG.oscura, IMG.no_es_imagen, IMG.diminuta]);
  await terminadas(page);
  let fotos = await fotosEnBandeja(page);
  d.primeras = fotos;
  v.entran_cuatro = fotos.length === 4 && (await page.textContent('#agente-fotos-estado')).includes('como mucho van 4 fotos');
  v.subidas_leyendo = fotos.slice(0, 3).every((f) => f.estado === 'lista' && f.linea === 'Subida · el panel la está leyendo…' && f.pintada);
  v.avisos = fotos[0].avisos === '' && fotos[1].avisos.startsWith('Foto pequeña') && fotos[2].avisos.startsWith('Foto oscura');
  v.no_es_imagen = fotos[3].estado === 'error' && fotos[3].linea.startsWith('No se pudo abrir esa imagen') && !fotos[3].reintentar && !fotos[3].girar;
  v.llena = await page.evaluate(() => document.querySelector('#agente-foto-camara').disabled && document.querySelector('#agente-foto-galeria').disabled
    && document.querySelector('.agente-adjuntar-n').textContent === '4');
  v.de_a_una = await page.evaluate(() => window.__bmp.max === 1 && window.__bmp.abiertos === 0);
  // Con una foto que falló no se envía
  await page.fill('#agente-texto', 'Revisa estas planillas');
  await page.press('#agente-texto', 'Enter');
  await page.waitForTimeout(300);
  v.no_envia_con_error = reg.mensajes.length === 0 && (await page.textContent('#agente-fotos-estado')).startsWith('Una foto no subió')
    && (await page.inputValue('#agente-texto')) === 'Revisa estas planillas';
  // Quitar la que falló (no se había subido: nada que borrar), girar la primera y quitar la oscura
  await page.click('#agente-fotos-lista .agente-foto:nth-child(4) .agente-foto-quitar');
  await page.click('#agente-fotos-lista .agente-foto:nth-child(1) .agente-foto-girar');
  await terminadas(page);
  await page.click('#agente-fotos-lista .agente-foto:nth-child(3) .agente-foto-quitar');
  await page.waitForFunction(() => document.querySelectorAll('#agente-fotos-lista .agente-foto').length === 2, null, espera);
  await page.waitForTimeout(200);
  fotos = await fotosEnBandeja(page);
  v.quedan_dos = fotos.length === 2 && fotos.every((f) => f.estado === 'lista') && fotos.map((f) => f.titulo).join() === 'Foto 1,Foto 2';
  v.girada_y_borrada = reg.borradas.join() === 'f1,f3' && reg.subidas.length === 4;
  // Enviar: los ids en `adjuntos`, la burbuja con el chip y el texto, y el turno con sus gráficos
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => document.querySelectorAll('.agente-grafico').length === 3, null, espera);
  await listo(page);
  d.burbuja = await page.evaluate(() => { const m = document.querySelector('.agente-msj.agente-persona');
    return { chip: m.querySelector('.agente-fotos-chip')?.textContent, minis: m.querySelectorAll('.agente-fotos-chip canvas').length,
      texto: m.querySelector('p')?.textContent }; });
  v.burbuja = d.burbuja.chip === '2 fotos adjuntas' && d.burbuja.minis === 2 && d.burbuja.texto === 'Revisa estas planillas';
  v.bandeja_vacia_tras_enviar = await page.evaluate(() => document.querySelector('#agente-fotos').hidden
    && document.querySelector('.agente-adjuntar-n').hidden && !document.querySelector('#agente-fotos-lista').children.length);
  d.orden = await page.evaluate(() => [...document.querySelector('.agente-msj.agente-respuesta').children].map((e) => e.className.split(' ')[0]
    + (e.classList.contains('agente-grafico') ? `:${e.dataset.clase}` : '') + (e.title ? `:${e.title}` : '')));
  v.graficos_bajo_su_herramienta = JSON.stringify(d.orden.filter((x) => x !== 'sr')) === JSON.stringify([
    'agente-herr:analizar', 'agente-grafico:barras', 'agente-herr:analizar', 'agente-grafico:serie', 'agente-grafico:columnas', 'agente-md']);
  d.graficos = await page.evaluate(() => [...document.querySelectorAll('.agente-grafico')].map((f) => ({
    titulo: f.querySelector('figcaption b').textContent, filas: f.querySelectorAll('.lista-barras .f').length,
    svg: !!f.querySelector('svg'), nota: f.querySelector('.agente-grafico-nota')?.textContent || null,
    img: f.querySelectorAll('img').length })));
  v.graficos = d.graficos[0].titulo === 'Personas por zona' && d.graficos[0].filas === 2 && d.graficos[0].nota === 'Sin quienes no autorizaron.'
    && d.graficos[1].titulo === 'Altas por mes' && d.graficos[1].svg && d.graficos[2].titulo === '<img src=x onerror="window.__xss=1">'
    && d.graficos.every((g) => g.img === 0);
  // «Tomar foto»: el selector de la cámara (una sola); enviar mientras sube la manda sola al terminar
  await page.click('#agente-adjuntar');
  v.camara_una = (await elegir(page, '#agente-foto-camara', [IMG.exif])) === false;
  await page.waitForFunction(() => document.querySelector('#agente-fotos-lista .agente-foto')?.dataset.estado === 'subiendo', null, espera);
  await page.press('#agente-texto', 'Enter');
  v.espera_la_subida = reg.mensajes.length === 1 && (await page.textContent('#agente-fotos-estado')) === 'Se envía cuando terminen de subir las fotos…';
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-reintentar')].some((b) => b.textContent === 'Reintentar'), null, espera);
  v.sale_sola = reg.mensajes.length === 2;
  d.solo_fotos = await page.evaluate(() => { const m = [...document.querySelectorAll('.agente-msj.agente-persona')].pop();
    return { chip: m.querySelector('.agente-fotos-chip')?.textContent, p: !!m.querySelector('p'), sinEnviar: m.classList.contains('sin-enviar') }; });
  v.solo_fotos = d.solo_fotos.chip === '1 foto adjunta' && !d.solo_fotos.p && d.solo_fotos.sinEnviar;
  // «Reintentar» la repite (409 proveedor) y «Nueva conversación» la trae de vuelta a la bandeja
  await page.click('.agente-reintentar:text-is("Reintentar")');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-reintentar')].some((b) => b.textContent === 'Nueva conversación'), null, espera);
  await page.click('.agente-reintentar:text-is("Nueva conversación")');
  await page.waitForSelector('.agente-bienvenida', espera);
  fotos = await fotosEnBandeja(page);
  v.nueva_trae_la_foto = fotos.length === 1 && fotos[0].estado === 'lista' && fotos[0].pintada
    && !(await page.evaluate(() => document.querySelector('#agente-fotos').hidden));
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => document.querySelector('.agente-msj.agente-respuesta .agente-md')?.textContent.includes('Recibí la foto.'), null, espera);
  await listo(page);
  // Una subida que falla: «Reintentar» la sube otra vez desde la memoria; quitarla después la borra de la bandeja
  await page.click('#agente-adjuntar');
  await elegir(page, '#agente-foto-galeria', [IMG.ruido]);
  await page.waitForFunction(() => document.querySelector('#agente-fotos-lista .agente-foto')?.dataset.estado === 'error', null, espera);
  fotos = await fotosEnBandeja(page);
  v.error_de_subida = fotos[0].linea === 'El panel está ocupado: intente de nuevo en un momento.' && fotos[0].reintentar && fotos[0].girar;
  await page.click('#agente-fotos-lista .agente-foto-reintentar');
  await terminadas(page);
  fotos = await fotosEnBandeja(page);
  v.reintento_sube = fotos[0].estado === 'lista' && reg.subidas.length === 7;
  // (y girar la que no llegó en un mensaje: la anterior se borra)
  await page.click('#agente-fotos-lista .agente-foto-girar');
  await terminadas(page);
  await page.click('#agente-fotos-lista .agente-foto-quitar');
  await page.waitForFunction(() => !document.querySelector('#agente-fotos-lista').children.length, null, espera);
  await page.waitForTimeout(200);
  d.borradas = reg.borradas.slice();
  v.quitar_borra = reg.borradas.join() === 'f1,f3,f7,f8';
  // Al repintar una conversación guardada: el chip de las fotos y el gráfico debajo de su herramienta
  await page.click('#agente-ver-historial');
  await page.waitForSelector('.agente-abrir', espera);
  await page.click('.agente-abrir');
  await page.waitForFunction(() => document.querySelector('.agente-grafico[data-clase="apilada"]'), null, espera);
  d.repintada = await page.evaluate(() => ({
    personas: [...document.querySelectorAll('.agente-msj.agente-persona')].map((m) => [m.querySelector('.agente-fotos-chip')?.textContent || null,
      m.querySelector('p')?.textContent || null, m.querySelectorAll('canvas').length]),
    orden: [...document.querySelector('.agente-msj.agente-respuesta').children].map((e) => e.className.split(' ')[0]).filter((x) => x !== 'sr'),
  }));
  v.repintada = JSON.stringify(d.repintada.personas) === JSON.stringify([['3 fotos adjuntas', null, 0], ['1 foto adjunta', 'Y esta otra', 0]])
    && JSON.stringify(d.repintada.orden) === JSON.stringify(['agente-herr', 'agente-grafico', 'agente-md']);
  v.sin_xss = await page.evaluate(() => window.__xss === undefined);
}

async function movil(page, caso) {
  const v = caso.revisiones, d = caso.datos;
  await ingresar(page);
  await page.tap('#agente-boton');
  await page.waitForSelector('#agente-adjuntar:not([hidden])', espera);
  await page.tap('#agente-adjuntar');
  await elegir(page, '#agente-foto-galeria', [IMG.nitida, IMG.pequena, IMG.oscura, IMG.exif]);
  await terminadas(page);
  await page.waitForTimeout(300);
  d.geo = await page.evaluate(() => {
    const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top, d: b.right, a: b.bottom }; };
    const bandeja = document.querySelector('#agente-fotos');
    const fila = ['#agente-adjuntar', '#agente-texto', '#agente-enviar'].map(r);
    return { panel: r('#agente-panel'), bandeja: r('#agente-fotos'), fila, ancho: innerWidth, alto: innerHeight,
      desbordeBandeja: bandeja.scrollWidth > bandeja.clientWidth + 1, desbordePagina: document.documentElement.scrollWidth > innerWidth,
      items: [...document.querySelectorAll('.agente-foto')].map((e) => e.getBoundingClientRect().right <= bandeja.getBoundingClientRect().right + 0.5) };
  });
  const g = d.geo;
  v.panel_dentro = g.panel.x >= -0.5 && g.panel.d <= g.ancho + 0.5 && g.panel.y >= -0.5 && g.panel.a <= g.alto + 0.5;
  v.sin_desborde = !g.desbordeBandeja && !g.desbordePagina && g.items.length === 4 && g.items.every(Boolean);
  v.fila_dentro = g.fila.every((b) => b.x >= g.panel.x - 0.5 && b.d <= g.panel.d + 0.5);
  // La indicación del cuadro de escribir, en un renglón (no se parte debajo de la cámara y el micrófono)
  v.indicacion_en_un_renglon = await page.evaluate(() => getComputedStyle(document.querySelector('#agente-texto'), '::placeholder').whiteSpace === 'nowrap');
  try { await page.screenshot({ path: `${capturas}/fotos-${caso.nombre}.png` }); } catch { /* nada */ }
}

(async () => {
  const nav = await chromium.launch();
  const res = { casos: [] };
  try {
    for (const [nombre, op] of [['escritorio', { viewport: { width: 1400, height: 900 } }],
      ['movil', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }],
      ['chico', { viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }]]) {
      const ctx = await nav.newContext(op);
      const reg = { estado: ESTADO, mensajes: [], subidas: [], borradas: [] };
      const caso = { nombre, revisiones: {}, datos: {}, errores: [], csp: [] };
      await ctx.route((u) => u.origin !== origen, (r) => r.abort());
      await servir(ctx, reg);
      await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
      await ctx.addInitScript(() => {
        addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
        // Cuántas imágenes abiertas hay a la vez (createImageBitmap sin su close())
        window.__bmp = { abiertos: 0, max: 0 };
        const original = window.createImageBitmap;
        window.createImageBitmap = async (...a) => {
          const b = await original.apply(window, a);
          window.__bmp.abiertos++;
          window.__bmp.max = Math.max(window.__bmp.max, window.__bmp.abiertos);
          const cerrar = b.close.bind(b);
          let cerrada = false;
          b.close = () => { if (!cerrada) { cerrada = true; window.__bmp.abiertos--; } cerrar(); };
          return b;
        };
      });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => caso.errores.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
      page.on('response', (x) => {
        if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo')) && x.headers()['x-prueba'] !== 'esperado') caso.errores.push(`${x.status()} ${x.url()}`);
      });
      try {
        if (nombre === 'escritorio') await escritorio(page, caso, reg);
        else await movil(page, caso);
      } catch (e) {
        caso.revisiones.sin_excepcion = String(e.stack || e).slice(0, 1500);
        try { await page.screenshot({ path: `${capturas}/fotos-${nombre}-fallo.png` }); } catch { /* nada */ }
      }
      caso.subidas = reg.subidas;
      caso.borradas = reg.borradas;
      caso.mensajes = reg.mensajes;
      res.casos.push(caso);
      await ctx.close();
    }
  } finally { await nav.close(); }
  console.log(JSON.stringify(res));
})().catch((e) => { console.error(e); process.exit(1); });
"""
