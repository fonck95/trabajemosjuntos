"""Empaqueta web/ como sitio estático autónomo en site/ (para GitHub Pages, el servidor de Railway o cualquier hosting).

web/index.html es el Home de la campaña y web/propuesta.html la presentación: los dos son documentos completos y se
copian tal cual. web/atlas.html se escribe sin <!doctype>/<head>/<body> porque también se publica como Artifact de
Claude, que añade ese esqueleto. Aquí se lo añadimos para que el sitio funcione solo.

three y GSAP: web/*.html los pide a cdnjs y jsdelivr, porque el Artifact solo admite scripts de esos dos CDN. En site/
esas URL (y la de la fuente que web/js/propuesta pide a jsdelivr) pasan a la copia verificada de web/vendor/ (vea
web/vendor/LEEME.md), con rutas relativas que sirven igual en GitHub Pages. En Railway el sitio comparte origen con el
panel (/panel/), así que ahí solo debe correr código del repositorio: el build falla si en site/ queda un <script src>
externo, una URL externa en un importmap, un destino del importmap que no existe, un módulo de three/addons sin copia
local, un import (estático o dinámico) de otro dominio o una URL de CDN en site/js, o código en atributos on* (la CSP
del sitio no lo deja correr).

Uso: python3 scripts/build_data.py && python3 scripts/build_site.py
     python3 scripts/build_site.py --three-desde <carpeta package del tgz de three>   (rehace web/vendor/three-0.160.0/)
"""
from html import escape
from html.parser import HTMLParser
import json
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

R = Path(__file__).resolve().parent.parent
VERSION_THREE = '0.160.0'
THREE = f'vendor/three-{VERSION_THREE}/'
ADDONS = 'three/addons/'
# URL exactas del CDN en web/*.html → copia local, relativa a la página. Las de three van en el importmap, que solo
# acepta rutas que empiecen con «./», «../» o «/» (sin eso las toma por un nombre de módulo y las ignora)
CDN = {
    'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js': 'vendor/gsap-3.12.5/gsap.min.js',
    f'https://cdn.jsdelivr.net/npm/three@{VERSION_THREE}/build/three.module.js': './' + THREE + 'build/three.module.js',
    f'https://cdn.jsdelivr.net/npm/three@{VERSION_THREE}/examples/jsm/': './' + THREE + 'examples/jsm/',
}
# Datos que web/js pide al CDN mientras corre (la fuente de las letras 3D de la propuesta) → copia local
CDN_JS = {
    f'https://cdn.jsdelivr.net/npm/three@{VERSION_THREE}/examples/fonts/helvetiker_bold.typeface.json':
        THREE + 'examples/fonts/helvetiker_bold.typeface.json',
}
# CDN de scripts y de módulos ES: cualquier literal con estas URL en site/js falla (también un import(variable))
RE_CDN = re.compile(r'https?://(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com|esm\.sh|esm\.run|cdn\.skypack\.dev'
                    r'|ga\.jspm\.io|jspm\.dev)/[^\s\'"`)]*')


def reescribir_cdn(html: str) -> str:
    for url, local in CDN.items():
        html = html.replace(url, local)
    return html


def reescribir_cdn_js(js: str, carpeta: str) -> str:
    """Cambia cada URL de CDN_JS entre comillas por su copia local, relativa al módulo (`carpeta`: la suya en site/)."""
    for url, local in CDN_JS.items():
        js = re.sub(rf"""(['"]){re.escape(url)}\1""", f"new URL('{posixpath.relpath(local, carpeta)}', import.meta.url).href", js)
    return js


class Scripts(HTMLParser):
    """Los <script> de una página, con sus atributos y el texto exacto entre las etiquetas, y el código en atributos."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self.en_atributos, self._abierto = [], [], None

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if re.fullmatch(r'on[a-z]+', k) or (v and re.match(r'\s*javascript:', v, re.I)):
                self.en_atributos.append(f'<{tag} {k}=…>')
        if tag == 'script':
            self._abierto = (dict(attrs), [])

    def handle_data(self, data):
        if self._abierto is not None:
            self._abierto[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._abierto is not None:
            self.scripts.append((self._abierto[0], ''.join(self._abierto[1])))
            self._abierto = None


def leer_scripts(pagina: Path) -> Scripts:
    p = Scripts()
    p.feed(pagina.read_text(encoding='utf-8'))
    p.close()
    return p


def es_externa(url: str) -> bool:
    """¿La URL sale del sitio (otro origen, protocolo relativo, data:…)? Como el navegador, ignora tabulaciones y saltos
    de línea y toma «\\» por «/»."""
    u = re.sub(r'[\t\n\r]|^[\x00-\x20]+|[\x00-\x20]+$', '', url).replace('\\', '/')
    return bool(re.match(r'[A-Za-z][A-Za-z0-9+.-]*:|//', u))


def existe_en(sitio: Path, pagina: Path, url: str) -> bool:
    """¿La URL local (relativa a la página o absoluta desde la raíz del sitio) apunta a algo que está en site/?"""
    ruta = unquote(re.split(r'[?#]', url, maxsplit=1)[0])
    f = ((sitio if ruta.startswith('/') else pagina.parent) / ruta.lstrip('/')).resolve()
    if not f.is_relative_to(sitio.resolve()):
        return False
    return f.is_dir() if ruta.endswith('/') else f.is_file()


# Un import estático empieza el renglón o sigue a «;» o «}» (los comentarios se quitan antes, en especificadores)
_IMPORT = re.compile(r"""(?:^|[;}])[ \t]*(?:import|export)\b[^'";]*?\bfrom\s*['"]([^'"\n]+)['"]"""  # import … from '…'
                     r"""|(?:^|[;}])[ \t]*import\s*['"]([^'"\n]+)['"]"""                          # import '…'
                     r"""|\bimport\s*\(\s*['"`]([^'"`\n]+)['"`]""", re.M)              # import('…') o import(`…`)


_COMENTARIOS = re.compile(r"/\*.*?\*/|(?<![:'\"`\\])//[^\n]*", re.S)


def especificadores(js: str) -> set:
    """Los especificadores de import y export de un módulo. Quita antes los comentarios (aproximado: un «//» después
    de «:» o de una comilla es parte de una URL o de un texto), para que «/* x */ import '…'» no se escape."""
    return {next(g for g in m if g) for m in _IMPORT.findall(_COMENTARIOS.sub(" ", js))}


def modulos_three(js: Path, jsm: Path):
    """Módulos de examples/jsm que necesita el sitio: los 'three/addons/…' que importa js/ y, dentro de jsm, lo que
    ellos importan con rutas relativas. Devuelve (los que hay en jsm, {el que falta: quién lo importa})."""
    pendientes = [(e[len(ADDONS):], f.relative_to(js).as_posix())
                  for f in sorted(js.rglob('*.js')) for e in sorted(especificadores(f.read_text(encoding='utf-8')))
                  if e.startswith(ADDONS)]
    hay, faltan = set(), {}
    while pendientes:
        mod, quien = pendientes.pop()
        if mod in hay or mod in faltan:
            continue
        if not (jsm / mod).is_file():
            faltan[mod] = quien
            continue
        hay.add(mod)
        pendientes += [(posixpath.normpath(posixpath.join(posixpath.dirname(mod), e)), f'{ADDONS}{mod}')
                       for e in especificadores((jsm / mod).read_text(encoding='utf-8')) if e.startswith('.')]
    return hay, faltan


def revisar(sitio: Path) -> list:
    """Lo que dejaría correr en site/ código que no es del repositorio o que la CSP bloquearía (vacío si nada)."""
    malos = []
    for pagina in sorted(sitio.rglob('*.html')):
        nombre, p = pagina.relative_to(sitio).as_posix(), leer_scripts(pagina)
        malos += [f'{nombre}: código en el atributo {a}' for a in p.en_atributos]
        for attrs, texto in p.scripts:
            if attrs.get('src') is not None:
                src = attrs['src'] or ''
                if es_externa(src):
                    malos.append(f'{nombre}: <script src="{src}"> externo')
                elif not existe_en(sitio, pagina, src):
                    malos.append(f'{nombre}: <script src="{src}"> no existe en site/')
            elif (attrs.get('type') or '').strip().lower() == 'importmap':
                try:
                    mapa = json.loads(texto)
                    destinos = list(mapa.get('imports', {}).values())
                    destinos += [d for alcance in mapa.get('scopes', {}).values() for d in alcance.values()]
                except (ValueError, AttributeError) as e:
                    malos.append(f'{nombre}: importmap que no se puede leer ({e})')
                    continue
                for d in destinos:
                    if not isinstance(d, str) or es_externa(d):
                        malos.append(f'{nombre}: URL externa en el importmap: {d}')
                    elif not d.startswith(('/', './', '../')):
                        malos.append(f'{nombre}: el navegador ignora el destino del importmap {d} (empiécelo con «./»)')
                    elif not existe_en(sitio, pagina, d):
                        malos.append(f'{nombre}: el destino del importmap {d} no existe en site/')
    if (sitio / 'js').is_dir():
        _, faltan = modulos_three(sitio / 'js', sitio / THREE / 'examples' / 'jsm')
        malos += [f'falta {THREE}examples/jsm/{m}, que importa {q} (vea web/vendor/LEEME.md)' for m, q in sorted(faltan.items())]
        for f in sorted((sitio / 'js').rglob('*.js')):
            nombre, js = f.relative_to(sitio).as_posix(), f.read_text(encoding='utf-8')
            malos += [f'{nombre}: importa {e} de otro dominio (la CSP del sitio lo bloquea)'
                      for e in sorted(especificadores(js)) if es_externa(e)]
            malos += [f'{nombre}: pide {u} (la CSP del sitio no deja salir a un CDN)' for u in sorted(set(RE_CDN.findall(js)))]
    return malos


def construir(src: Path = R / 'web', out: Path = R / 'site') -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    for pagina in sorted(src.glob('*.html')):
        html = body = pagina.read_text(encoding='utf-8')
        if body.lstrip()[:9].lower() != '<!doctype':
            head_end = body.index('</style>') + len('</style>')
            html = ('<!doctype html>\n<html lang="es">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                    + body[:head_end] + '\n</head>\n<body>\n' + body[head_end:] + '\n</body>\n</html>\n')
        html = reescribir_cdn(html)
        if html != body:
            (out / pagina.name).write_text(html, encoding='utf-8')
    usados = set()
    for f in sorted((out / 'js').rglob('*.js')):
        js = f.read_text(encoding='utf-8')
        nuevo = reescribir_cdn_js(js, f.parent.relative_to(out).as_posix())
        if nuevo != js:
            f.write_text(nuevo, encoding='utf-8')
            usados |= {local for url, local in CDN_JS.items() if url in js}
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
    malos = revisar(out) + [f'falta {local} (vea web/vendor/LEEME.md)' for local in sorted(usados) if not (out / local).is_file()]
    if malos:
        sys.exit('ERROR: en site/ quedaría código de fuera del repositorio o que la CSP del sitio bloquea:\n  '
                 + '\n  '.join(malos))
    print('site/ listo:', sum(1 for _ in out.rglob('*')), 'archivos')


def vendorizar_three(paquete: Path) -> None:
    """Rehace web/vendor/three-<versión>/ desde el paquete de npm ya verificado y extraído (web/vendor/LEEME.md):
    LICENSE, build/three.module.js, los módulos de examples/jsm que importa web/js y la fuente de CDN_JS con su licencia."""
    version = json.loads((paquete / 'package.json').read_text(encoding='utf-8')).get('version')
    if version != VERSION_THREE:
        sys.exit(f'ERROR: el paquete es three {version}; el sitio usa {VERSION_THREE}')
    hay, faltan = modulos_three(R / 'web' / 'js', paquete / 'examples' / 'jsm')
    if faltan:
        sys.exit('ERROR: el paquete no trae ' + ', '.join(f'{m} (lo importa {q})' for m, q in sorted(faltan.items())))
    destino = R / 'web' / THREE
    shutil.rmtree(destino, ignore_errors=True)
    datos = [local[len(THREE):] for local in CDN_JS.values()] + ['examples/fonts/LICENSE']
    for rel in ['LICENSE', 'build/three.module.js', *(f'examples/jsm/{m}' for m in sorted(hay)), *datos]:
        (destino / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paquete / rel, destino / rel)
    print(f'web/{THREE}: three.module.js, {len(hay)} módulos de examples/jsm y', ', '.join(datos))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--three-desde'] and len(sys.argv) == 3:
        vendorizar_three(Path(sys.argv[2]))
    elif len(sys.argv) > 1:
        sys.exit(__doc__)
    else:
        construir()
