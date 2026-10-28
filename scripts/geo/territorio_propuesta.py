# Territorio de la presentación de la propuesta 2028–2031: el río Magdalena con sus islas, las vías que salen del casco
# hacia el puente Guillermo Gaviria Correa («Puente Yondó» en OpenStreetMap) y el puente mismo, en metros respecto al
# origen del atlas. Complementa data/geo/calles.json, que solo cubre 1,3 km alrededor del casco.
# Entradas: data/geo/osm_amplio.xml, osm_vias.xml y osm_corredor_puente.xml (© colaboradores de OpenStreetMap, ODbL;
# el corredor se descargó de la API 0.6 con bbox −73,93, 7,02, −73,88, 7,095).
# Salida: data/propuesta/territorio.json   Uso: python3 scripts/geo/territorio_propuesta.py
import json, math
import xml.etree.ElementTree as ET
from pathlib import Path

R = Path(__file__).resolve().parents[2]
LAT0, LON0 = 7.0065, -73.9115
K = 111320 * math.cos(math.radians(LAT0))
XML = ['data/geo/osm_amplio.xml', 'data/geo/osm_vias.xml', 'data/geo/osm_corredor_puente.xml']
RIO = '415081'                 # multipolígono del agua del Magdalena en este tramo
Y_SUR, Y_NORTE = -6200, 12500  # el río se recorta a este tramo (el resto no se ve)
# borde oriental del río entre las dos piezas que trae OpenStreetMap (frente a Barrancabermeja no está en los extractos):
# se cierra por fuera de las islas, solo para que el agua se dibuje completa
PUENTE_ORIENTE = [(4650, 4300), (5150, 2300), (5050, 300)]  # de norte a sur
ANCHO = {'secondary': 9, 'secondary_link': 7, 'tertiary': 8, 'unclassified': 6}
RADIO_CASCO = 1250             # dentro de este radio las vías ya están en calles.json

xy = lambda la, lo: (round((lo - LON0) * K, 1), round((la - LAT0) * 111320, 1))
nodos, vias, externos, internos = {}, {}, set(), set()
for f in XML:
    raiz = ET.parse(R / f).getroot()
    for n in raiz.iter('node'):
        nodos[n.get('id')] = xy(float(n.get('lat')), float(n.get('lon')))
    for w in raiz.iter('way'):
        vias[w.get('id')] = ({t.get('k'): t.get('v') for t in w.findall('tag')}, [nd.get('ref') for nd in w.findall('nd')])
    for rel in raiz.iter('relation'):
        if rel.get('id') == RIO:
            for m in rel.findall('member'):
                if m.get('type') == 'way':
                    (externos if m.get('role') == 'outer' else internos).add(m.get('ref'))

def douglas(p, tol):
    if len(p) < 3:
        return p
    a, b = p[0], p[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-9
    d = [abs(dy * (q[0] - a[0]) - dx * (q[1] - a[1])) / L for q in p[1:-1]]
    i = max(range(len(d)), key=d.__getitem__)
    if d[i] <= tol:
        return [a, b]
    return douglas(p[:i + 2], tol)[:-1] + douglas(p[i + 1:], tol)

def encadenar(ids):
    """Une las vías del borde del río por sus extremos: devuelve polilíneas de ids de nodos."""
    tramos, cadenas = [list(vias[w][1]) for w in ids if w in vias], []
    while tramos:
        c, seguir = tramos.pop(0), True
        while seguir:
            seguir = False
            for s in tramos:
                if s[0] == c[-1]: c += s[1:]
                elif s[-1] == c[0]: c = s + c[1:]
                elif s[-1] == c[-1]: c += s[::-1][1:]
                elif s[0] == c[0]: c = s[::-1] + c[1:]
                else: continue
                tramos.remove(s); seguir = True; break
        cadenas.append([nodos[i] for i in c if i in nodos])
    return cadenas

def recorta(p, y0, y1):
    """Parte de la polilínea entre y0 y y1 (con los puntos de corte interpolados)."""
    out = []
    for a, b in zip(p, p[1:]):
        if y0 <= a[1] <= y1:
            out.append(a)
        for yc in (y0, y1):
            if (a[1] - yc) * (b[1] - yc) < 0:
                u = (yc - a[1]) / (b[1] - a[1])
                out.append((round(a[0] + (b[0] - a[0]) * u, 1), yc))
    if p and y0 <= p[-1][1] <= y1:
        out.append(p[-1])
    return out

cadenas = sorted(encadenar(externos), key=len, reverse=True)
# la orilla occidental es la más larga (pasa frente al casco); la oriental norte arranca frente al puente y la oriental
# sur frente a Barrancabermeja hacia el sur
occ = max(cadenas, key=lambda c: sum(1 for p in c if -2000 < p[1] < 9000 and p[0] < 3000))
resto = [c for c in cadenas if c is not occ]
ori_n = max(resto, key=lambda c: max(p[1] for p in c))
ori_s = [c for c in resto if c is not ori_n][0]
occ = recorta(occ if occ[0][1] < occ[-1][1] else occ[::-1], Y_SUR, Y_NORTE)                  # de sur a norte
ori_n = recorta(ori_n if ori_n[0][1] > ori_n[-1][1] else ori_n[::-1], Y_SUR, Y_NORTE)        # de norte a sur
ori_s = recorta(ori_s if ori_s[0][1] > ori_s[-1][1] else ori_s[::-1], Y_SUR, Y_NORTE)        # de norte a sur
poligono = douglas(occ, 4) + douglas(ori_n, 4) + PUENTE_ORIENTE + douglas(ori_s, 4)

def dentro(pt, ring):
    x, y, d = pt[0], pt[1], False
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i], ring[i - 1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            d = not d
    return d

islas = []
for w in internos:
    if w not in vias:
        continue
    anillo = [nodos[i] for i in vias[w][1] if i in nodos]
    if len(anillo) < 4 or anillo[0] != anillo[-1]:
        continue
    anillo = douglas(anillo[:-1], 3)  # abierto: Douglas-Peucker con los dos extremos iguales lo reduciría a un punto
    if len(anillo) >= 3 and all(dentro(p, poligono) for p in anillo):
        islas.append(anillo)

# vías principales fuera del casco (las de adentro ya están en calles.json) y el puente
salida, puente = [], {}
for wid, (t, refs) in vias.items():
    p = [nodos[i] for i in refs if i in nodos]
    if t.get('man_made') == 'bridge' and t.get('name') == 'Puente Yondó':
        puente['contorno'] = douglas(p[:-1], 1)
        continue
    if t.get('highway') not in ANCHO or len(p) < 2:
        continue
    if t.get('bridge') in ('yes', 'viaduct') and t.get('name') == 'Vía Barrancabermeja - Yondó' and max(q[1] for q in p) > 7000:
        puente.setdefault('tramos', []).append(p)
        continue
    trozo, trozos = [], []
    for q in p:
        if math.hypot(*q) > RADIO_CASCO:
            trozo.append(q)
        elif trozo:
            trozos.append(trozo); trozo = []
    trozos.append(trozo)
    for tr in trozos:
        if len(tr) >= 2:
            salida.append({'tipo': t['highway'], 'nombre': t.get('name'), 'ancho': ANCHO[t['highway']], 'p': douglas(tr, 2)})
# el tablero del puente, del estribo de Yondó (occidental) al de Barrancabermeja
t = sorted(puente.get('tramos', []), key=lambda p: min(q[0] for q in p))
tablero = []
for p in t:
    p = p if p[0][0] < p[-1][0] else p[::-1]
    tablero += p if not tablero else p[1:]
puente = {'nombre': 'Puente Guillermo Gaviria Correa (Barrancabermeja–Yondó)', 'tablero': tablero, 'contorno': puente.get('contorno', []),
          'estribo_yondo': tablero[0] if tablero else None}

out = {
    'origen': {'lat': LAT0, 'lon': LON0},
    'fuente': '© colaboradores de OpenStreetMap (ODbL), API 0.6; cálculo propio (scripts/geo/territorio_propuesta.py)',
    'nota': 'El borde oriental del río frente a Barrancabermeja (entre y = −871 y y = 5.980) no viene en los extractos y se cierra a mano por fuera de las islas.',
    'rio': {'nombre': 'Río Magdalena', 'poligono': poligono, 'islas': islas},
    'vias': salida,
    'puente': puente,
}
dest = R / 'data/propuesta/territorio.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'{dest.relative_to(R)}: río de {len(poligono)} puntos y {len(islas)} islas, {len(salida)} vías, puente de {len(tablero)} puntos '
      f'(estribo de Yondó en {puente["estribo_yondo"]}); {dest.stat().st_size / 1024:.0f} KB')
