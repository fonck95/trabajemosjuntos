# Mosaico satelital (Esri World Imagery) centrado en lat/lon. Uso: sat.py lat lon radio_m zoom salida.png
import sys, math, io, urllib.request
from PIL import Image, ImageDraw
lat, lon, r, z, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
def px(lat, lon, z):
    n = 256 * 2**z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1/math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y
mpp = 156543.03392 * math.cos(math.radians(lat)) / 2**z
cx, cy = px(lat, lon, z); h = r / mpp
x0, y0, x1, y1 = cx-h, cy-h, cx+h, cy+h
img = Image.new('RGB', (int(x1-x0), int(y1-y0)))
for tx in range(int(x0//256), int(x1//256)+1):
    for ty in range(int(y0//256), int(y1//256)+1):
        url = f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}'
        req = urllib.request.Request(url, headers={'User-Agent': 'yondo-research/1.0'})
        try: t = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert('RGB')
        except Exception as e: print('fallo', url, e); continue
        img.paste(t, (int(tx*256 - x0), int(ty*256 - y0)))
d = ImageDraw.Draw(img)
# escala de 10 m y norte
w = 10 / mpp; d.rectangle([10, img.height-20, 10+w, img.height-14], fill='white', outline='black'); d.text((12, img.height-34), '10 m', fill='white')
d.text((img.width-20, 8), 'N', fill='yellow')
img.save(out); print(out, img.size, f'{mpp:.3f} m/px')
