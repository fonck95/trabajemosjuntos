"""Genera web/data/propuesta.json para la presentación de la propuesta integral 2028–2031 (web/propuesta.html).

Entradas (data/propuesta/):
  general.json        portada, catálogo de fuentes de financiación, hoja de ruta, pedidos y el orden de los módulos
  modulos/<id>.json   un archivo por módulo: diagnóstico, componentes con costo, financiación, gestión, metas y pasos
  geo.json            sitios y trazados de cada propuesta en metros del modelo (x al oriente, y al norte)
  territorio.json     río Magdalena, vías y puente (lo genera scripts/geo/territorio_propuesta.py)
Revisa que las sumas cuadren (componentes y fuentes contra la inversión de cada módulo) y que cada fuente, componente y
proyecto tipo citado exista, y que el Home (web/index.html) siga repitiendo el nombre y el lema de cada área, con su
enlace y su imagen; avisa lo que no cuadra sin detener la construcción.
Uso: python3 scripts/build_propuesta.py   (también lo llama scripts/build_data.py)
     python3 scripts/build_propuesta.py --estricto   (la CI: termina con error si hay avisos)
"""
import json
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data/propuesta'
avisos = []
aviso = lambda m: avisos.append(m)
load = lambda p: json.loads((D / p).read_text(encoding='utf-8'))

if not (D / 'general.json').exists():
    print('propuesta: falta data/propuesta/general.json; no se genera web/data/propuesta.json')
    raise SystemExit(0)

g = load('general.json')
fuentes = {f['id']: f for f in g.get('financiacion', {}).get('fuentes', [])}
modulos = []
for mid in g.get('orden_modulos', []):
    ruta = D / 'modulos' / f'{mid}.json'
    if not ruta.exists():
        aviso(f'falta el módulo {mid} (data/propuesta/modulos/{mid}.json)')
        continue
    m = json.loads(ruta.read_text(encoding='utf-8'))
    m.setdefault('id', mid)
    comps = m.get('componentes', [])
    suma = sum((c.get('costo') or {}).get('central') or 0 for c in comps)
    inv = m.get('inversion') or {}
    if not inv.get('central'):
        inv = m['inversion'] = {'min': sum((c.get('costo') or {}).get('min') or 0 for c in comps), 'central': suma,
                                'max': sum((c.get('costo') or {}).get('max') or 0 for c in comps)}
    elif suma and abs(suma - inv['central']) > 0.01 * inv['central']:
        aviso(f'{mid}: los componentes suman {suma:,.0f} M y la inversión dice {inv["central"]:,.0f} M')
    fin = sum(f.get('monto') or 0 for f in m.get('financiacion', []))
    if fin and abs(fin - inv['central']) > 0.01 * inv['central']:
        aviso(f'{mid}: las fuentes suman {fin:,.0f} M y la inversión es {inv["central"]:,.0f} M')
    for f in m.get('financiacion', []):
        if f.get('fuente') not in fuentes:
            aviso(f'{mid}: la fuente «{f.get("fuente")}» no está en el catálogo de general.json')
    for c in comps:
        for f in c.get('fuentes', []):
            if f not in fuentes:
                aviso(f'{mid}/{c.get("id")}: la fuente «{f}» no está en el catálogo de general.json')
        cc = c.get('costo') or {}
        if cc and not (cc.get('min', 0) <= cc.get('central', 0) <= cc.get('max', cc.get('central', 0))):
            aviso(f'{mid}/{c.get("id")}: el rango de costo no está en orden (mín ≤ central ≤ máx)')
    ids = {c.get('id') for c in comps}
    for p in m.get('pasos', []):
        if p.get('tipo') == 'componente' and p.get('componente') not in ids:
            aviso(f'{mid}: el paso «{p.get("id")}» cita el componente «{p.get("componente")}», que no existe')
    modulos.append(m)

geo = load('geo.json') if (D / 'geo.json').exists() else {}
terr = load('territorio.json') if (D / 'territorio.json').exists() else {}
if not terr:
    aviso('falta data/propuesta/territorio.json (python3 scripts/geo/territorio_propuesta.py)')

out = {
    'meta': g.get('meta', {}),
    'portada': g.get('portada', {}),
    'modulos': modulos,
    'financiacion': g.get('financiacion', {}),
    'ruta': g.get('ruta', {}),
    'pedidos': g.get('pedidos', {}),
    'zonas_intervencion': geo.get('zonas_intervencion', []),
    'geo': {k: v for k, v in geo.items() if k != 'zonas_intervencion'},
    'territorio': terr,
}
# espacios que no se cortan entre número y unidad («69 %», «10 × 22 m», «Lote 2», «1.ª etapa»): así una cifra no queda
# partida entre dos líneas del panel. Solo en los textos de la presentación (no en geo ni territorio) y nunca en URL.
NBSP = '\u00a0'
UNIDAD = re.compile(r'(\d)[ \t](%|m²|m³|km²?\b|ha\b|m\b|L/s|L/día|kWp|MWp|kWh|MWh|kW\b|MW\b|kV\b|t/día|t/mes|t/h|t\b|horas?\b|días?\b|años?\b|meses\b|M\b|millones\b|billones\b)')
POR = re.compile(r'(\d)[ \t]×[ \t](\d)')
ROTULO = re.compile(r'\b(Lote|lote|Fase|fase|Sector|sector|Bloque|bloque|Etapa|etapa|Tramo|tramo|Calle|Carrera|manzana)[ \t](\d)')
ORDINAL = re.compile(r'(\d\.[ªº])[ \t]')
# y un rango con raya entre cifras («2028–2031», «$5–8 M») no se parte después de la raya (unión de palabras U+2060)
RANGO = re.compile(r'(\d)–(?=\$?\d)')
UNION = '\u2060'
cambios = 0
def sin_cortes(v, clave=''):
    global cambios
    if isinstance(v, dict):
        return {k: sin_cortes(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [sin_cortes(x, clave) for x in v]
    if isinstance(v, str) and clave != 'url' and not v.startswith('http'):
        n = POR.sub(f'\\1{NBSP}×{NBSP}\\2', v)
        n = UNIDAD.sub(f'\\1{NBSP}\\2', n)
        n = ROTULO.sub(f'\\1{NBSP}\\2', n)
        n = ORDINAL.sub(f'\\1{NBSP}', n)
        n = RANGO.sub(f'\\1–{UNION}', n)
        cambios += n != v
        return n
    return v
for k in ('meta', 'portada', 'modulos', 'financiacion', 'ruta', 'pedidos'):
    out[k] = sin_cortes(out[k])

# El Home repite en cada tarjeta el nombre y el lema del área, enlaza a su capítulo y muestra su imagen: si el módulo cambia,
# el Home se queda atrás sin que nadie lo note. Se revisa tarjeta por tarjeta, no el archivo entero (los ids del área
# también salen en las variables CSS y en los nombres de archivo). También se revisa que la lista de vistas del atlas que
# el Home manda a atlas.html sea la de las pestañas del atlas.
home = R / 'web/index.html'
if home.exists():
    h = home.read_text(encoding='utf-8')
    plano = lambda t: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t).replace('&nbsp;', ' ').replace('\u00a0', ' ').replace('\u2060', '')).strip().lower()
    tarjetas = {m.group(1): m.group(2) for m in re.finditer(r'<a class="area[^"]*"[^>]*href="propuesta\.html#([\w-]+)"[^>]*>(.*?)</a>', h, re.S)}
    for m in modulos:
        t = tarjetas.pop(m['id'], None)
        if t is None:
            aviso(f'el Home no tiene la tarjeta del área {m["id"]} (web/index.html)')
            continue
        nombre, nombres = re.search(r'<b>(.*?)</b>', t, re.S), list(dict.fromkeys(x for x in (m.get('corto'), m.get('nombre')) if x))
        if not nombre or plano(nombre.group(1)) not in {plano(x) for x in nombres}:
            aviso(f'la tarjeta de {m["id"]} en el Home no lleva su nombre ({" o ".join(f"«{x}»" for x in nombres)}) (web/index.html)')
        frase = re.search(r'<span class="frase">(.*?)</span>', t, re.S)
        if m.get('lema') and (not frase or plano(frase.group(1)) != plano(m['lema'])):
            aviso(f'el lema de {m["id"]} cambió y el Home sigue con otro: «{m["lema"]}» (web/index.html)')
        img = re.search(r'src="(img/home/[^"]+)"', t)
        if not img or img.group(1) != f'img/home/area-{m["id"]}.webp':
            aviso(f'la tarjeta de {m["id"]} en el Home no muestra img/home/area-{m["id"]}.webp (web/index.html)')
        if not (R / f'web/img/home/area-{m["id"]}.webp').exists():
            aviso(f'falta la imagen del Home para {m["id"]} (web/img/home/area-{m["id"]}.webp)')
    for sobra in tarjetas:
        aviso(f'el Home tiene una tarjeta de un área que no está en la propuesta: {sobra} (web/index.html)')
    for ref in sorted(set(re.findall(r'(?:src="|url\(|href="|content=")(img/home/[^")]+)', h))):
        if not (R / 'web' / ref).exists():
            aviso(f'el Home cita una imagen que no existe: web/{ref}')
    atlas = R / 'web/atlas.html'
    vistas = re.search(r'VISTAS_ATLAS = \[([^\]]*)\]', h)
    if atlas.exists() and vistas:
        enlaces = re.findall(r"'([\w-]+)'", vistas.group(1))
        pestanas = re.findall(r'<a href="#([\w-]+)" data-view="\1"', atlas.read_text(encoding='utf-8'))
        if sorted(enlaces) != sorted(pestanas):
            aviso(f'las vistas del atlas que el Home redirige ({", ".join(enlaces)}) no son las pestañas del atlas ({", ".join(pestanas)}) (web/index.html)')

dest = R / 'web/data/propuesta.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
total = sum((m.get('inversion') or {}).get('central') or 0 for m in modulos)
print(f'propuesta.json {dest.stat().st_size / 1024:.0f} KB: {len(modulos)} módulos, inversión central {total:,.0f} M'.replace(',', '.'))
print(f'Textos con cifras unidas a su unidad: {cambios}')
print(f'Avisos de la propuesta: {len(avisos)}')
for a in avisos:
    print('  -', a)
if avisos and '--estricto' in sys.argv:
    raise SystemExit(1)
