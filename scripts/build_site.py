"""Empaqueta web/ como sitio estático autónomo en site/ (para GitHub Pages o cualquier hosting).

web/index.html es el Home de la campaña y web/propuesta.html la presentación: los dos son documentos completos y se
copian tal cual. web/atlas.html se escribe sin <!doctype>/<head>/<body> porque también se publica como Artifact de
Claude, que añade ese esqueleto. Aquí se lo añadimos para que el sitio funcione solo.
Uso: python3 scripts/build_data.py && python3 scripts/build_site.py
"""
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
print('site/ listo:', sum(1 for _ in out.rglob('*')), 'archivos')
