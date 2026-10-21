# Panoramas de Street View cerca de un punto. Uso: cobertura.py lat lon [radio_m=80] [n=15]
# Imprime id, distancia, rumbo DESDE el panorama HACIA el punto, y coordenadas.
import sys, json, math, os
lat, lon = float(sys.argv[1]), float(sys.argv[2])
rad = float(sys.argv[3]) if len(sys.argv) > 3 else 80; n = int(sys.argv[4]) if len(sys.argv) > 4 else 15
cov = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'geo', 'sv_coverage.json')))
k = 111320; c = math.cos(math.radians(lat))
rows = []
for p in cov:
    dx, dy = (lon - p['lon']) * k * c, (lat - p['lat']) * k
    d = math.hypot(dx, dy)
    if d <= rad: rows.append((d, (math.degrees(math.atan2(dx, dy)) + 360) % 360, p))
for d, b, p in sorted(rows, key=lambda r: r[0])[:n]:
    print(f"{p['id']}  dist={d:5.1f} m  rumbo_hacia_punto={b:5.1f}  {p['lat']:.6f},{p['lon']:.6f}")
