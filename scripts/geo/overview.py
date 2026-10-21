# Mapa satelital con panoramas de Street View (puntos cian) y puntos de interés. Uso: overview.py lat lon radio_m zoom salida.png [lat,lon,etiqueta ...]
import sys, math, json, os, io, urllib.request
from PIL import Image, ImageDraw
lat, lon, r, z, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
marks = [a.split(',', 2) for a in sys.argv[6:]]
def px(la, lo):
    n = 256 * 2**z
    return (lo + 180) / 360 * n, (1 - math.log(math.tan(math.radians(la)) + 1/math.cos(math.radians(la))) / math.pi) / 2 * n
mpp = 156543.03392 * math.cos(math.radians(lat)) / 2**z
cx, cy = px(lat, lon); h = r / mpp; x0, y0 = cx-h, cy-h
img = Image.new('RGB', (int(2*h), int(2*h)))
for tx in range(int(x0//256), int((x0+2*h)//256)+1):
    for ty in range(int(y0//256), int((y0+2*h)//256)+1):
        url = f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}'
        try: t = Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'yondo-research/1.0'}), timeout=30).read())).convert('RGB')
        except Exception: continue
        img.paste(t, (int(tx*256-x0), int(ty*256-y0)))
d = ImageDraw.Draw(img)
cov = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'geo', 'sv_coverage.json')))
for c in cov:
    x, y = px(c['lat'], c['lon']); x -= x0; y -= y0
    if 0 <= x < img.width and 0 <= y < img.height: d.ellipse([x-2, y-2, x+2, y+2], fill=(0, 230, 255))
for m in marks:
    x, y = px(float(m[0]), float(m[1])); x -= x0; y -= y0
    d.ellipse([x-5, y-5, x+5, y+5], outline='red', width=3); d.text((x+7, y-6), m[2] if len(m) > 2 else '', fill='yellow')
w = 50 / mpp; d.rectangle([10, img.height-20, 10+w, img.height-14], fill='white'); d.text((12, img.height-34), '50 m', fill='white')
img.save(out); print(out, img.size, f'{mpp:.3f} m/px')
