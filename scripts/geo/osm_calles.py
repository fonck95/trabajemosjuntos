# Convierte OpenStreetMap (data/geo/osm_amplio.xml, © colaboradores de OpenStreetMap, ODbL) en una base liviana
# para la escena urbana: calles con ancho por jerarquía, cuerpos de agua y caños, en metros respecto al origen.
# Salida: data/geo/calles.json   Uso: python3 scripts/geo/osm_calles.py
import json, math, os
import xml.etree.ElementTree as ET

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
LAT0, LON0 = 7.0065, -73.9115          # origen de la escena (centro del casco urbano)
RADIO = 1300                           # metros alrededor del origen
K, C = 111320, math.cos(math.radians(LAT0))
ANCHO = {'secondary': 9, 'secondary_link': 7, 'tertiary': 8, 'residential': 6.5, 'unclassified': 6, 'service': 4, 'pedestrian': 5, 'footway': 2, 'path': 1.5}

t = ET.parse(os.path.join(R, 'data/geo/osm_amplio.xml')).getroot()
nodes = {n.get('id'): (float(n.get('lat')), float(n.get('lon'))) for n in t.iter('node')}
xy = lambda ll: [round((ll[1] - LON0) * K * C, 1), round((ll[0] - LAT0) * K, 1)]
ways = {w.get('id'): w for w in t.iter('way')}
tags = lambda e: {x.get('k'): x.get('v') for x in e.findall('tag')}
dentro = lambda p: math.hypot(*p) <= RADIO

def pts(w):
    return [xy(nodes[nd.get('ref')]) for nd in w.findall('nd') if nd.get('ref') in nodes]

calles, agua, canos = [], [], []
for w in ways.values():
    tg = tags(w); p = pts(w)
    if len(p) < 2 or not any(dentro(q) for q in p): continue
    if tg.get('highway') in ANCHO:
        calles.append({'tipo': tg['highway'], 'nombre': tg.get('name'), 'ancho': ANCHO[tg['highway']], 'puente': tg.get('bridge') == 'yes', 'p': p})
    elif tg.get('natural') == 'water' and p[0] == p[-1]:
        agua.append({'nombre': tg.get('name'), 'p': p})
    elif tg.get('waterway') in ('canal', 'stream', 'river', 'ditch', 'drain'):
        canos.append({'tipo': tg['waterway'], 'nombre': tg.get('name'), 'ancho': {'river': 30, 'canal': 4}.get(tg['waterway'], 2.5), 'p': p})

# multipolígonos de agua (río Magdalena, ciénagas): se ensamblan los anillos exteriores completos
def anillos(rel):
    segs = []
    for m in rel.findall('member'):
        if m.get('type') == 'way' and m.get('role') in ('outer', '') and m.get('ref') in ways:
            refs = [nd.get('ref') for nd in ways[m.get('ref')].findall('nd')]
            if all(r in nodes for r in refs): segs.append(refs)
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]: ring += s[1:]
                elif s[-1] == ring[-1]: ring += s[::-1][1:]
                elif s[-1] == ring[0]: ring = s[:-1] + ring
                elif s[0] == ring[0]: ring = s[::-1][:-1] + ring
                else: continue
                segs.pop(i); changed = True; break
        if ring[0] == ring[-1] and len(ring) > 3: rings.append([xy(nodes[r]) for r in ring])
    return rings
for rel in t.iter('relation'):
    tg = tags(rel)
    if tg.get('natural') == 'water' or tg.get('water'):
        for ring in anillos(rel):
            if any(dentro(q) for q in ring) or any(math.hypot(*q) < 4000 for q in ring):
                agua.append({'nombre': tg.get('name') or ('Río Magdalena' if tg.get('water') == 'river' else None), 'p': ring})

out = {'origen': {'lat': LAT0, 'lon': LON0}, 'radio_m': RADIO, 'fuente': '© colaboradores de OpenStreetMap (ODbL), descarga de la API 0.6',
       'calles': calles, 'agua': agua, 'canos': canos}
json.dump(out, open(os.path.join(R, 'data/geo/calles.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"calles {len(calles)} · agua {len(agua)} ({sum(len(a['p']) for a in agua)} vértices) · caños {len(canos)} · {os.path.getsize(os.path.join(R, 'data/geo/calles.json')) // 1024} KB")
