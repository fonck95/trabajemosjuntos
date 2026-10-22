# Distancias por las vías entre las sedes de la microrred y red propuesta de mínima longitud.
# Entradas: data/geo/osm_vias.xml (© colaboradores de OpenStreetMap, ODbL; API 0.6), data/edificios/*.json y, si existe,
# data/red/subestacion.json (raíz de la red: subestación de EPM). Salidas: data/red/distancias.json y data/red/distancias.csv
# Uso: python3 scripts/geo/red_distancias.py
#
# Método: grafo de las vías (sin senderos peatonales); cada sede se conecta al punto más cercano de la vía más cercana
# (acometida en línea recta); distancias por Dijkstra; la red propuesta es el árbol de mínima longitud entre las sedes con
# las distancias por la vía, y su longitud "única" cuenta una sola vez las calles que comparten varios tramos.
import csv, heapq, json, math, os, glob
import xml.etree.ElementTree as ET

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
LAT0, LON0 = 7.0065, -73.9115
K, C = 111320, math.cos(math.radians(LAT0))
xy = lambda lat, lon: ((lon - LON0) * K * C, (lat - LAT0) * K)
VIAS = {'secondary', 'secondary_link', 'tertiary', 'tertiary_link', 'residential', 'unclassified', 'service', 'track', 'living_street', 'primary', 'road'}

t = ET.parse(os.path.join(R, 'data/geo/osm_vias.xml')).getroot()
nodes = {n.get('id'): xy(float(n.get('lat')), float(n.get('lon'))) for n in t.iter('node')}
adj = {}
def edge(a, b, w):
    adj.setdefault(a, []).append((b, w)); adj.setdefault(b, []).append((a, w))
segs = []
for w in t.iter('way'):
    tg = {x.get('k'): x.get('v') for x in w.findall('tag')}
    if tg.get('highway') not in VIAS: continue
    refs = [nd.get('ref') for nd in w.findall('nd') if nd.get('ref') in nodes]
    for a, b in zip(refs, refs[1:]):
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        L = math.hypot(x2 - x1, y2 - y1)
        if L > 0: edge(a, b, L); segs.append((a, b))

# puntos: sedes (y la subestación si se conoce)
pts = []
for f in sorted(glob.glob(os.path.join(R, 'data/edificios/*.json'))):
    s = json.load(open(f))
    if not s.get('id') or s.get('lat') is None or s.get('reemplazado_por'): continue
    pts.append({'id': s['id'], 'nombre': s.get('nombre', s['id']), 'lat': s['lat'], 'lon': s['lon']})
sub_path = os.path.join(R, 'data/red/subestacion.json')
if os.path.exists(sub_path):
    sb = json.load(open(sub_path))
    if sb.get('lat') is not None: pts.insert(0, {'id': 'subestacion', 'nombre': sb.get('nombre', 'Subestación Yondó (EPM)'), 'lat': sb['lat'], 'lon': sb['lon']})

def snap(p):
    px, py = xy(p['lat'], p['lon']); best = None
    for a, b in segs:
        (x1, y1), (x2, y2) = nodes[a], nodes[b]; dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
        u = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2)); qx, qy = x1 + u * dx, y1 + u * dy
        d = math.hypot(px - qx, py - qy)
        if best is None or d < best[0]: best = (d, a, b, u, qx, qy)
    return best
for i, p in enumerate(pts):
    d, a, b, u, qx, qy = snap(p)
    vid = f'v{i}'; nodes[vid] = (qx, qy)
    L = math.hypot(nodes[b][0] - nodes[a][0], nodes[b][1] - nodes[a][1])
    edge(vid, a, u * L); edge(vid, b, (1 - u) * L)
    p['nodo'] = vid; p['acometida_m'] = round(d, 1); p['xy'] = [round(c, 1) for c in xy(p['lat'], p['lon'])]

def dijkstra(src):
    dist, prev, q = {src: 0.0}, {}, [(0.0, src)]
    while q:
        d, u = heapq.heappop(q)
        if d > dist.get(u, 1e18): continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; heapq.heappush(q, (nd, v))
    return dist, prev
n = len(pts); D = [[0.0] * n for _ in range(n)]; PREV = []
for i, p in enumerate(pts):
    dist, prev = dijkstra(p['nodo']); PREV.append(prev)
    for j, q in enumerate(pts): D[i][j] = dist.get(q['nodo'], float('inf')) + p['acometida_m'] + q['acometida_m'] if i != j else 0.0
recta = [[math.dist(xy(p['lat'], p['lon']), xy(q['lat'], q['lon'])) for q in pts] for p in pts]

def ruta(i, j):
    prev, cur, out = PREV[i], pts[j]['nodo'], []
    while cur != pts[i]['nodo']: out.append(cur); cur = prev[cur]
    out.append(cur); return out[::-1]

# árbol de mínima longitud (Prim) desde la raíz (subestación, o alcaldía si no se conoce)
raiz = 0 if pts[0]['id'] == 'subestacion' else next((i for i, p in enumerate(pts) if p['id'] == 'alcaldia'), 0)
dentro, tramos, usados = {raiz}, [], set()
while len(dentro) < n:
    i, j = min(((i, j) for i in dentro for j in range(n) if j not in dentro), key=lambda e: D[e[0]][e[1]])
    r = ruta(i, j); nuevo = 0.0
    for a, b in zip(r, r[1:]):
        k = tuple(sorted((a, b)))
        if k not in usados: usados.add(k); nuevo += math.dist(nodes[a], nodes[b])
    poly = [pts[i]['xy']] + [[round(c, 1) for c in nodes[v]] for v in r] + [pts[j]['xy']]
    tramos.append({'de': pts[i]['id'], 'a': pts[j]['id'], 'km_via': round(D[i][j] / 1000, 3), 'km_recta': round(recta[i][j] / 1000, 3),
                   'km_red_nueva': round((nuevo + pts[j]['acometida_m']) / 1000, 3), 'acometida_m': pts[j]['acometida_m'], 'ruta': poly})
    dentro.add(j)
total_unico = sum(t['km_red_nueva'] for t in tramos)

out = {'fuente': '© colaboradores de OpenStreetMap (ODbL), API 0.6; cálculo propio', 'origen': {'lat': LAT0, 'lon': LON0},
       'metodo': 'Distancia por la vía más corta (Dijkstra) sobre el grafo de vías de OSM, más la acometida en línea recta de cada sede a la vía; red propuesta = árbol de mínima longitud (Prim) con esas distancias; km_red_nueva cuenta una sola vez las calles compartidas.',
       'raiz': pts[raiz]['id'], 'puntos': [{k: p[k] for k in ('id', 'nombre', 'lat', 'lon', 'xy', 'acometida_m')} for p in pts],
       'matriz_via_km': [[round(v / 1000, 3) for v in row] for row in D], 'matriz_recta_km': [[round(v / 1000, 3) for v in row] for row in recta],
       'arbol': {'tramos': tramos, 'km_total_red': round(total_unico, 3), 'km_suma_tramos': round(sum(t['km_via'] for t in tramos), 3)}}
os.makedirs(os.path.join(R, 'data/red'), exist_ok=True)
json.dump(out, open(os.path.join(R, 'data/red/distancias.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(R, 'data/red/distancias.csv'), 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh); w.writerow(['km por la vía'] + [p['id'] for p in pts])
    for p, row in zip(pts, out['matriz_via_km']): w.writerow([p['id']] + row)
print(f"{n} puntos · raíz {pts[raiz]['id']} · red propuesta {total_unico:.2f} km (suma de tramos {out['arbol']['km_suma_tramos']:.2f} km)")
for p in pts:
    if p['acometida_m'] > 80: print(f"  aviso: {p['id']} queda a {p['acometida_m']:.0f} m de la vía más cercana")
for t in tramos: print(f"  {t['de']:>16} → {t['a']:<18} {t['km_via']:6.3f} km por la vía · {t['km_recta']:6.3f} en línea recta · red nueva {t['km_red_nueva']:6.3f}")
