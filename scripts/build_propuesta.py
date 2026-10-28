"""Genera web/data/propuesta.json para la presentación de la propuesta integral 2028–2031 (web/propuesta.html).

Entradas (data/propuesta/):
  general.json        portada, catálogo de fuentes de financiación, hoja de ruta, pedidos y el orden de los módulos
  modulos/<id>.json   un archivo por módulo: diagnóstico, componentes con costo, financiación, gestión, metas y pasos
  geo.json            sitios y trazados de cada propuesta en metros del modelo (x al oriente, y al norte)
  territorio.json     río Magdalena, vías y puente (lo genera scripts/geo/territorio_propuesta.py)
Revisa que las sumas cuadren (componentes y fuentes contra la inversión de cada módulo) y que cada fuente, componente y
proyecto tipo citado exista; avisa lo que no cuadra sin detener la construcción.
Uso: python3 scripts/build_propuesta.py   (también lo llama scripts/build_data.py)
"""
import json
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
dest = R / 'web/data/propuesta.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
total = sum((m.get('inversion') or {}).get('central') or 0 for m in modulos)
print(f'propuesta.json {dest.stat().st_size / 1024:.0f} KB: {len(modulos)} módulos, inversión central {total:,.0f} M'.replace(',', '.'))
print(f'Avisos de la propuesta: {len(avisos)}')
for a in avisos:
    print('  -', a)
