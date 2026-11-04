"""Empaqueta web/ como sitio estático autónomo en site/ (para GitHub Pages o cualquier hosting).

web/index.html es el Home de la campaña y web/propuesta.html la presentación: los dos son documentos completos y se
copian tal cual. web/atlas.html se escribe sin <!doctype>/<head>/<body> porque también se publica como Artifact de
Claude, que añade ese esqueleto. Aquí se lo añadimos para que el sitio funcione solo.
Uso: python3 scripts/build_data.py && python3 scripts/build_site.py
"""
from html import escape
import os
import re
import shutil
from pathlib import Path

R = Path(__file__).resolve().parent.parent
src, out = R / 'web', R / 'site'
if out.exists():
    shutil.rmtree(out)
shutil.copytree(src, out)
for pagina in sorted(src.glob('*.html')):
    body = pagina.read_text(encoding='utf-8')
    if body.lstrip()[:9].lower() == '<!doctype':
        continue
    head_end = body.index('</style>') + len('</style>')
    html = ('<!doctype html>\n<html lang="es">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + body[:head_end] + '\n</head>\n<body>\n' + body[head_end:] + '\n</body>\n</html>\n')
    (out / pagina.name).write_text(html, encoding='utf-8')
# WhatsApp y Facebook solo leen la imagen para compartir con la dirección completa: si el despliegue conoce la suya
# (SITE_URL en GitHub Pages, RAILWAY_PUBLIC_DOMAIN en Railway), se completa en el Home
base = os.environ.get('SITE_URL') or (f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}" if os.environ.get('RAILWAY_PUBLIC_DOMAIN') else '')
if base:
    base = base.rstrip('/')
    home = out / 'index.html'
    h = home.read_text(encoding='utf-8')
    og = '<meta property="og:image" content="img/home/compartir.jpg">'
    if og in h:
        h = h.replace(og, f'<meta property="og:image" content="{base}/img/home/compartir.jpg">\n<meta property="og:url" content="{base}/">')
        home.write_text(h, encoding='utf-8')
        print('imagen para compartir:', f'{base}/img/home/compartir.jpg')
    else:
        print('aviso: el Home no trae la etiqueta og:image esperada; no se completó la dirección')
# Enlace discreto al panel de administración. En Railway el mismo servicio sirve el panel en /panel/ y railpack.json
# construye con PANEL_URL=/panel/; si el panel vive en otro servicio, PANEL_URL es su dirección https:// (variable del
# servicio del sitio, o de repositorio en GitHub Pages). Sin PANEL_URL el enlace no aparece (GitHub Pages no tiene
# panel).
home = out / 'index.html'
h = home.read_text(encoding='utf-8')
marca = '<!-- ingreso-equipo -->'
panel = (os.environ.get('PANEL_URL') or '').strip().rstrip('/')
if marca in h:
    enlace = ''
    if panel and (re.fullmatch(r'https://[A-Za-z0-9.-]+(:\d+)?(/[^\s"<>]*)?', panel)
                  or re.fullmatch(r'(/(?!\.\.?(?:/|$))[A-Za-z0-9._~-]+)+', panel)):  # o una ruta del mismo dominio, como /panel
        enlace = f'<a class="ingreso" href="{escape(panel)}/" rel="nofollow noopener">Ingreso del equipo</a>'
        print('ingreso del equipo:', panel)
    elif panel:
        print('aviso: PANEL_URL debe ser una dirección https://… o una ruta como /panel/; no se agregó el enlace')
    home.write_text(h.replace(marca, enlace), encoding='utf-8')
print('site/ listo:', sum(1 for _ in out.rglob('*')), 'archivos')
