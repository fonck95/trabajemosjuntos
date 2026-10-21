# Superpone la especificación de un edificio (data/edificios/<id>.json) sobre la imagen satelital
# para verificar huella, orientación y ubicación. Uso: trace.py data/edificios/<id>.json salida.png [zoom=19] [radio_m]
# Dibuja: volúmenes (rojo, con id), elementos (amarillo), adecuaciones FV (cian), BESS (magenta), ancla (cruz blanca).
import sys, json, math, io, urllib.request
from PIL import Image, ImageDraw
spec = json.load(open(sys.argv[1])); out = sys.argv[2]
z = int(sys.argv[3]) if len(sys.argv) > 3 else 19
lat0, lon0 = spec['lat'], spec['lon']
def rect_pts(v):
    cx, cy = v['centro']; L, A = v['largo'], v['ancho']; r = math.radians(v.get('rumbo_eje', 0))
    ux, uy = math.sin(r), math.cos(r)           # eje largo (rumbo desde el norte)
    vx, vy = math.cos(r), -math.sin(r)          # eje corto (perpendicular, a la derecha)
    return [(cx + sx*L/2*ux + sy*A/2*vx, cy + sx*L/2*uy + sy*A/2*vy) for sx, sy in ((-1,-1), (1,-1), (1,1), (-1,1))]
def pts_of(o):
    if 'poligono' in o: return [tuple(p) for p in o['poligono']]
    if 'centro' in o and 'largo' in o: return rect_pts(o)
    return None
shapes = [(v.get('id', '?'), pts_of(v), (255, 40, 40)) for v in spec.get('volumenes', [])]
shapes += [(e.get('tipo', '?'), pts_of(e), (255, 220, 0)) for e in spec.get('elementos', []) if pts_of(e)]
ad = spec.get('adecuaciones', {})
shapes += [('FV', pts_of(f), (0, 230, 255)) for f in ad.get('fv', []) if pts_of(f)]
if ad.get('bess') and pts_of(ad['bess']): shapes.append(('BESS', pts_of(ad['bess']), (255, 0, 255)))
allp = [p for _, ps, _ in shapes if ps for p in ps] or [(0, 0)]
r = float(sys.argv[4]) if len(sys.argv) > 4 else max(25, 1.25 * max(max(abs(x), abs(y)) for x, y in allp))
def px(la, lo):
    n = 256 * 2**z
    return (lo + 180) / 360 * n, (1 - math.log(math.tan(math.radians(la)) + 1/math.cos(math.radians(la))) / math.pi) / 2 * n
mpp = 156543.03392 * math.cos(math.radians(lat0)) / 2**z
cx, cy = px(lat0, lon0); h = r / mpp; x0, y0 = cx - h, cy - h
img = Image.new('RGB', (int(2*h), int(2*h)))
for tx in range(int(x0//256), int((x0+2*h)//256) + 1):
    for ty in range(int(y0//256), int((y0+2*h)//256) + 1):
        url = f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}'
        try: t = Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'yondo-research/1.0'}), timeout=30).read())).convert('RGB')
        except Exception: continue
        img.paste(t, (int(tx*256 - x0), int(ty*256 - y0)))
d = ImageDraw.Draw(img)
toimg = lambda p: (h + p[0]/mpp, h - p[1]/mpp)
for label, ps, col in shapes:
    if not ps: continue
    q = [toimg(p) for p in ps]
    d.line(q + [q[0]], fill=col, width=2)
    mx, my = sum(a for a, _ in q)/len(q), sum(b for _, b in q)/len(q); d.text((mx-8, my-6), str(label), fill=col)
d.line([(h-6, h), (h+6, h)], fill='white', width=2); d.line([(h, h-6), (h, h+6)], fill='white', width=2)
w = 10 / mpp; d.rectangle([10, img.height-20, 10+w, img.height-14], fill='white'); d.text((12, img.height-34), '10 m', fill='white')
d.text((img.width-20, 8), 'N', fill='yellow')
img.save(out); print(out, img.size, f'{mpp:.3f} m/px', f'radio {r:.0f} m')
