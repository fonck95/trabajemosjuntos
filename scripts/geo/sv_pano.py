# Vista libre desde un panorama de Street View. Uso: sv_pano.py PANO_ID rumbo pitch fov salida.jpg [zoom]
# rumbo: grados desde el norte (0 = N, 90 = E); pitch: + mira hacia arriba; fov: campo visual horizontal.
import sys, math
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from streetlevel import streetview
from svlib import persp
pid, rumbo, pitch, fov, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
zoom = int(sys.argv[6]) if len(sys.argv) > 6 else 4
p = streetview.find_panorama_by_id(pid)
img = streetview.get_panorama(p, zoom=zoom)
v = persp(img, (rumbo - math.degrees(p.heading)) % 360, pitch_deg=pitch, fov=fov, W=1400, H=900)
from PIL import ImageDraw
ImageDraw.Draw(v).text((10, 10), f'{pid} {p.date} lat {p.lat:.6f} lon {p.lon:.6f} rumbo {rumbo:.0f} pitch {pitch:.0f} fov {fov:.0f}', fill='yellow')
v.save(out, quality=88); print(out, p.date, f'{p.lat:.6f},{p.lon:.6f}', 'altura_camara≈2.5m')
