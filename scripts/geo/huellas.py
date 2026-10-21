# Huellas de edificaciones del casco urbano para dar contexto a la escena 3D (las casas alrededor de las sedes).
# Fuente: Microsoft Global ML Building Footprints (ODbL), teselas por quadkey de nivel 9.
# Salida: data/geo/huellas.json con polígonos en metros respecto al origen de data/geo/calles.json.
# Uso: python3 scripts/geo/huellas.py   (descarga la tesela 032230330 si no está en data/geo/img/)
import gzip, json, math, os, urllib.request

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
LINKS = 'https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv'
QK = '032230330'
LAT0, LON0, RADIO = 7.0065, -73.9115, 1300
K, C = 111320, math.cos(math.radians(LAT0))
cache = os.path.join(R, 'data/geo/img', f'ms_buildings_{QK}.csv.gz')
if not os.path.exists(cache):
    url = next(l.split(',')[2] for l in urllib.request.urlopen(LINKS).read().decode().splitlines() if l.startswith('Colombia,') and f',{QK},' in l)
    urllib.request.urlretrieve(url, cache)

out = []
with gzip.open(cache, 'rt') as f:
    for line in f:
        g = json.loads(line)['geometry']
        if g['type'] != 'Polygon': continue
        ring = g['coordinates'][0][:-1]
        pts = [((lon - LON0) * K * C, (lat - LAT0) * K) for lon, lat in ring]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if math.hypot(cx, cy) > RADIO: continue
        area = abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2
        if area < 12: continue
        out.append([round(v, 1) for p in pts for v in p])
json.dump({'fuente': 'Microsoft Global ML Building Footprints (ODbL), tesela ' + QK, 'origen': {'lat': LAT0, 'lon': LON0}, 'poligonos': out},
          open(os.path.join(R, 'data/geo/huellas.json'), 'w'), separators=(',', ':'))
print(len(out), 'edificaciones ·', os.path.getsize(os.path.join(R, 'data/geo/huellas.json')) // 1024, 'KB')
