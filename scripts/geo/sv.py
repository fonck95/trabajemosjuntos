# Vistas de Street View hacia un edificio. Uso: sv.py lat lon salida_prefijo [radio_busqueda_m] [max_panos]
# Busca panoramas alrededor del punto, descarga cada uno y recorta una vista en perspectiva mirando al edificio.
import sys, math
from PIL import ImageDraw
from streetlevel import streetview
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from svlib import bearing, dist, persp
lat, lon, pref = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
rad = float(sys.argv[4]) if len(sys.argv) > 4 else 60
maxp = int(sys.argv[5]) if len(sys.argv) > 5 else 4
# Cobertura completa del casco urbano (sv_coverage.json, 2.100 panoramas): se eligen los más cercanos,
# separados al menos 12 m entre sí para ver el edificio desde ángulos distintos
import json, os
cov = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'geo', 'sv_coverage.json')))
cov = [c for c in cov if dist(c['lat'], c['lon'], lat, lon) <= rad]
cov.sort(key=lambda c: dist(c['lat'], c['lon'], lat, lon))
panos = []
for c in cov:
    if all(dist(c['lat'], c['lon'], q['lat'], q['lon']) >= 12 for q in panos): panos.append(c)
    if len(panos) >= maxp: break
if not panos: print('sin panoramas en', rad, 'm')
for i, c in enumerate(panos):
    full = streetview.find_panorama_by_id(c['id'])
    if not full: continue
    img = streetview.get_panorama(full, zoom=3)
    b = bearing(full.lat, full.lon, lat, lon); dd = dist(full.lat, full.lon, lat, lon)
    yaw = (b - math.degrees(full.heading)) % 360  # el centro del equirectangular apunta al heading del panorama
    for j, off in enumerate([0, -35, 35]):
        v = persp(img, yaw + off, pitch_deg=10 if dd > 25 else 18, fov=80)
        dr = ImageDraw.Draw(v); dr.text((10, 10), f'{full.id} {full.date} rumbo {(b+off)%360:.0f} dist {dd:.0f} m', fill='yellow')
        out = f'{pref}_p{i}_{j}.jpg'; v.save(out, quality=85); print(out, f'rumbo={(b+off)%360:.0f}', f'dist={dd:.0f}m', full.date)
