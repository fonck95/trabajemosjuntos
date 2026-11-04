"""Servidor único de Railway: sitio público en la raíz, panel en /panel/ y el sitio en línea aunque el panel falle.

Solo datos inventados."""
import base64
import hashlib
import importlib.util
import json
import logging
import shutil
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from conftest import MONGO

import servidor

RAIZ = Path(__file__).resolve().parents[2]
JS_HOME = "\ndocument.documentElement.classList.add('js');\n"
MAPA = '\n{ "imports": { "three": "./js/three.js" } }\n'


@pytest.fixture
def sitio(tmp_path):
    d = tmp_path / "site"
    (d / "js").mkdir(parents=True)
    (d / "guia").mkdir()
    (d / "index.html").write_text(f"<!doctype html><title>Home</title><script>{JS_HOME}</script><p>HOME-PUBLICO</p>"
                                  + "x" * 3000, encoding="utf-8")
    (d / "atlas.html").write_text(f'<!doctype html><title>Atlas</title><script type="importmap">{MAPA}</script>'
                                  '<script type="module" src="js/a.js"></script>ATLAS-PUBLICO', encoding="utf-8")
    (d / "js" / "a.js").write_text("console.log(1)", encoding="utf-8")
    (d / "guia" / "index.html").write_text("<!doctype html>GUIA", encoding="utf-8")
    return d


def _esperar_panel(app, segundos=15):
    fin = time.time() + segundos
    while time.time() < fin and not getattr(app.state.panel.state, "listo", False):
        time.sleep(0.05)
    assert app.state.panel.state.listo


@pytest.fixture
def servido(cfg, sitio):
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas del servidor")
    app = servidor.crear_servidor(cfg, sitio)
    try:
        with TestClient(app) as c:
            _esperar_panel(app)
            yield c
    finally:
        import pymongo
        from conftest import URI
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


@pytest.fixture
def solo_sitio(sitio, monkeypatch):
    """El servidor sin la configuración del panel: el sitio no depende de MongoDB."""
    from app import config

    def sin_uri():
        raise RuntimeError("Falta la variable MONGODB_URI en el servicio del panel")
    monkeypatch.setattr(config, "cargar", sin_uri)
    with TestClient(servidor.crear_servidor(None, sitio)) as c:
        yield c


def _hash(texto):
    return "'sha256-" + base64.b64encode(hashlib.sha256(texto.encode("utf-8")).digest()).decode() + "'"


def _script_src(csp):
    return next(d for d in csp.split(";") if d.split()[:1] == ["script-src"]).split()[1:]


def test_sitio_publico_como_caddy(servido, sitio):
    c = servido
    r = c.get("/")
    assert r.status_code == 200 and "HOME-PUBLICO" in r.text
    assert r.headers["content-security-policy"] == servidor.politica_sitio(sitio)
    assert r.headers["x-content-type-options"] == "nosniff" and "server" not in r.headers
    assert c.get("/atlas").text.endswith("ATLAS-PUBLICO") and c.get("/atlas.html").status_code == 200
    assert c.get("/js/a.js").status_code == 200
    assert c.get("/no-existe").status_code == 404
    assert c.get("/", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip"
    assert c.get("/health").text == "ok"


def test_panel_bajo_el_prefijo(servido, cfg):
    from app.seguridad import CSP
    c = servido
    r = c.get("/panel", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/panel/"
    r = c.get("/panel/personas/12")  # rutas del navegador: devuelven la aplicación con el prefijo
    assert r.status_code == 200 and '<meta name="panel-base" content="/panel">' in r.text
    assert '"/panel/static/js/app.js"' in r.text and '"/static/' not in r.text
    assert r.headers["content-security-policy"] == CSP  # la del panel, no la del sitio
    assert c.get("/panel/static/js/base.js").status_code == 200
    assert c.get("/panel/api/yo").status_code == 401
    # Sin sesión, la API se corta antes de leer el cuerpo, también bajo el prefijo
    assert c.post("/panel/api/importar", content=b"x" * 2048, headers={"Content-Type": "application/octet-stream"}).status_code == 401
    r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
    assert r.status_code == 200
    assert "path=/panel/api/login" in r.headers["set-cookie"].lower().replace("; ", ";").replace(";", "; ")
    assert c.get("/panel/api/personas").headers["cache-control"] == "no-store"
    assert c.post("/panel/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-11-01"}).status_code == 403  # sin CSRF
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert c.post("/panel/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-11-01"}).status_code == 201


def test_sitio_en_linea_aunque_mongodb_no_responda(cfg, sitio):
    from dataclasses import replace
    caido = replace(cfg, mongodb_uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200&connectTimeoutMS=200")
    app = servidor.crear_servidor(caido, sitio)
    with TestClient(app) as c:
        assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
        r = c.get("/panel/api/yo")
        assert r.status_code == 503 and r.headers["retry-after"] == "5"
        assert c.get("/panel/").status_code == 200  # la página carga y muestra el aviso al intentar ingresar


def test_sitio_en_linea_aunque_falte_la_configuracion_del_panel(solo_sitio):
    c = solo_sitio
    assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
    r = c.get("/panel/")
    assert r.status_code == 503 and "MONGODB_URI" in r.text and "Volver al sitio" in r.text


# ───────────────────────────── Sitio público: CSP y atajos ─────────────────────────────

def test_csp_del_sitio_en_todas_sus_respuestas(solo_sitio):
    """El sitio comparte origen con el panel: solo corren sus propios scripts y sus <script> en línea, por su hash."""
    c = solo_sitio
    respuestas = {"/": c.get("/"), "/atlas": c.get("/atlas"), "js": c.get("/js/a.js"), "404": c.get("/no-existe"),
                  "405": c.post("/atlas.html"), "405 atajo": c.post("/atlas"), "308": c.get("/atlas/", follow_redirects=False),
                  "304": c.get("/js/a.js", headers={"If-None-Match": c.get("/js/a.js").headers["etag"]})}
    assert [r.status_code for r in respuestas.values()] == [200, 200, 200, 404, 405, 405, 308, 304]
    for nombre, r in respuestas.items():
        csp = r.headers.get("content-security-policy", "")
        fuentes = _script_src(csp)
        # El texto exacto entre las etiquetas, con sus saltos de línea; los dos importmap iguales dan un solo hash
        assert sorted(fuentes) == sorted(["'self'", "'wasm-unsafe-eval'", _hash(JS_HOME), _hash(MAPA)]), nombre
        # ni 'unsafe-inline' ni 'unsafe-eval' ni hosts (https:, //cdn…, *)
        assert not [f for f in fuentes if f in ("'unsafe-inline'", "'unsafe-eval'", "*") or ":" in f or "." in f], nombre
        for d in ("default-src 'self'", "object-src 'none'", "base-uri 'self'", "img-src 'self' data: blob:",
                  "worker-src 'self' blob:", "connect-src 'self' blob: data:"):
            assert d in csp, (nombre, d)
        assert len(r.headers.get_list("content-security-policy")) == 1, nombre
        assert r.headers["x-content-type-options"] == "nosniff" and "server" not in r.headers, nombre
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin", nombre


def test_hash_de_scripts_en_linea_como_el_navegador(tmp_path):
    """El navegador convierte CRLF en LF antes de leer el <script>; un <script src> no lleva hash."""
    d = tmp_path / "site"
    (d / "sub").mkdir(parents=True)
    (d / "index.html").write_bytes("<script>\r\nvar a = 'ñ';\r\n</script><SCRIPT src=x.js>no</SCRIPT>".encode())
    (d / "sub" / "p.html").write_text('<script type="importmap">{"imports":{}}</script><script></script>', encoding="utf-8")
    assert servidor.hashes_en_linea(d) == sorted({_hash("\nvar a = 'ñ';\n"), _hash('{"imports":{}}'), _hash("")})


def test_sitio_solo_get_y_head(solo_sitio):
    """Antes «POST /atlas» (y DELETE, OPTIONS, PROPFIND…) devolvía la página: el atajo no miraba el método."""
    c = solo_sitio
    for metodo in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "PROPFIND"):
        for ruta in ("/atlas", "/atlas.html", "/", "/js/a.js", "/guia/"):
            r = c.request(metodo, ruta, content=b"x" * 2048)
            assert r.status_code == 405 and r.headers["allow"] == "GET, HEAD", (metodo, ruta)
            assert "ATLAS-PUBLICO" not in r.text and "content-security-policy" in r.headers
    r = c.head("/atlas")
    assert r.status_code == 200 and r.content == b"" and int(r.headers["content-length"]) > 0


def test_sitio_ruta_con_caracter_nulo_es_404(solo_sitio, caplog):
    """«%00» en la ruta daba 500 con la traza en el registro (ValueError: embedded null character)."""
    c = solo_sitio
    with caplog.at_level(logging.WARNING):
        for ruta in ("/atlas%00", "/js/a.js%00", "/%00", "/guia%00/", "/atlas%00/", "/a%00b/c"):
            r = c.get(ruta, follow_redirects=False)
            assert r.status_code == 404 and "content-security-policy" in r.headers, ruta
        assert c.get("/" + "a" * 5000).status_code == 404  # nombre demasiado largo para el sistema de archivos
    assert not [x for x in caplog.records if x.levelno >= logging.ERROR]


def test_sitio_barra_final_lleva_a_la_pagina(solo_sitio, sitio):
    """«/atlas/» servía atlas.html con las rutas relativas bajo /atlas/ y la página se rompía."""
    c = solo_sitio
    r = c.get("/atlas/", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/atlas"
    assert c.get("/atlas/?vista=torre&n=1", follow_redirects=False).headers["location"] == "/atlas?vista=torre&n=1"
    assert c.get("http://testserver//atlas/", follow_redirects=False).headers["location"] == "/atlas"  # nunca «//atlas»
    assert c.get("http://testserver//evil.example/", follow_redirects=False).status_code == 404  # sin redirección abierta
    assert c.get("/atlas.html/", follow_redirects=False).headers["location"] == "/atlas.html"
    assert c.get("/atlas/").text.endswith("ATLAS-PUBLICO")
    assert c.get("/guia/").text == "<!doctype html>GUIA"  # una carpeta con index.html sigue igual
    assert c.get("/no-existe/", follow_redirects=False).status_code == 404
    # Una carpeta sin index.html junto a {ruta}.html: como el try_files de Caddy, manda la página
    assert c.get("/js/", follow_redirects=False).status_code == 404
    (sitio / "js.html").write_text("<!doctype html>JS-HTML", encoding="utf-8")
    assert c.get("/js").text == "<!doctype html>JS-HTML"
    assert c.get("/js/", follow_redirects=False).headers["location"] == "/js"


def test_sitio_error_inesperado_lleva_cabeceras_y_queda_en_el_registro(solo_sitio, monkeypatch, caplog):
    def falla(*a, **k):
        raise RuntimeError("disco ilegible")
    monkeypatch.setattr(servidor.Sitio, "file_response", falla)
    with caplog.at_level(logging.ERROR):
        r = solo_sitio.get("/js/a.js")
    assert r.status_code == 500 and "content-security-policy" in r.headers and "disco" not in r.text
    assert any(x.exc_info and "disco ilegible" in str(x.exc_info[1]) for x in caplog.records)


def test_sitio_conserva_gzip_etag_rangos_y_head(solo_sitio):
    c = solo_sitio
    r = c.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and "HOME-PUBLICO" in r.text
    assert "content-encoding" not in c.get("/js/a.js", headers={"Accept-Encoding": "gzip"}).headers  # menos de 1 KiB
    etag = c.get("/atlas").headers["etag"]
    assert c.get("/atlas", headers={"If-None-Match": etag}).status_code == 304
    r = c.get("/js/a.js", headers={"Range": "bytes=0-6"})
    assert r.status_code == 206 and r.text == "console"
    assert c.get("/guia", follow_redirects=False).status_code in (307, 308)


def test_sin_sitio_construido_responde_503_con_cabeceras(tmp_path, monkeypatch):
    from app import config

    def sin_uri():
        raise RuntimeError("Falta la variable MONGODB_URI en el servicio del panel")
    monkeypatch.setattr(config, "cargar", sin_uri)
    with TestClient(servidor.crear_servidor(None, tmp_path / "vacio")) as c:
        r = c.get("/")
        assert r.status_code == 503 and "content-security-policy" in r.headers and c.get("/health").text == "ok"


# ───────────────────────────── build_site.py ─────────────────────────────

CDN_GSAP = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"
CDN_THREE = "https://cdn.jsdelivr.net/npm/three@0.160.0/"
FUENTE = CDN_THREE + "examples/fonts/helvetiker_bold.typeface.json"


@pytest.fixture
def build_site(monkeypatch):
    for v in ("SITE_URL", "RAILWAY_PUBLIC_DOMAIN", "PANEL_URL"):
        monkeypatch.delenv(v, raising=False)
    spec = importlib.util.spec_from_file_location("build_site", RAIZ / "scripts" / "build_site.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def web(tmp_path):
    """web/ mínima como la del repositorio: páginas con las URL del CDN y copias locales inventadas en vendor/."""
    w = tmp_path / "web"
    archivos = {
        "index.html": "<!doctype html><html><head><script>var tema = 1;</script></head><body><!-- ingreso-equipo --></body></html>",
        "atlas.html": (f'<style>p{{}}</style>\n<p>ATLAS</p>\n<script src="{CDN_GSAP}"></script>\n<script type="importmap">\n'
                       f'{{ "imports": {{ "three": "{CDN_THREE}build/three.module.js", "three/addons/": "{CDN_THREE}examples/jsm/" }} }}\n'
                       '</script>\n<script type="module" src="js/main.js"></script>'),
        "js/main.js": "import * as THREE from 'three';\nimport { Orbita } from 'three/addons/controls/OrbitControls.js';\n",
        "js/propuesta/geo3d.js": f"const f = () => import('three/addons/loaders/FontLoader.js');\nconst u = '{FUENTE}';\n",
        "vendor/gsap-3.12.5/gsap.min.js": "/* gsap */",
        "vendor/three-0.160.0/build/three.module.js": "export const REVISION = '160';",
        "vendor/three-0.160.0/examples/jsm/controls/OrbitControls.js": "import {\n  Vector3\n} from 'three';\nimport { ayuda } from '../utils/Ayuda.js';\n",
        "vendor/three-0.160.0/examples/jsm/utils/Ayuda.js": "// will be loaded from 'https://ejemplo.invalid/x.js' (comentario, no un import)\nexport const ayuda = 1;\n",
        "vendor/three-0.160.0/examples/jsm/loaders/FontLoader.js": "export class FontLoader {}\n",
        "vendor/three-0.160.0/examples/fonts/helvetiker_bold.typeface.json": "{}",
    }
    for rel, texto in archivos.items():
        (w / rel).parent.mkdir(parents=True, exist_ok=True)
        (w / rel).write_text(texto, encoding="utf-8")
    return w


def test_build_site_cambia_el_cdn_por_la_copia_local(build_site, web, tmp_path):
    site = tmp_path / "site"
    build_site.construir(web, site)
    atlas = (site / "atlas.html").read_text(encoding="utf-8")
    assert atlas.startswith("<!doctype html>") and '<script src="vendor/gsap-3.12.5/gsap.min.js">' in atlas
    # En el importmap, con «./»: sin eso el navegador toma la ruta por un nombre de módulo y la ignora
    assert ('"three": "./vendor/three-0.160.0/build/three.module.js", "three/addons/": "./vendor/three-0.160.0/examples/jsm/"'
            in atlas)
    assert not [p for p in site.rglob("*.html") if "cdnjs" in p.read_text() or "jsdelivr" in p.read_text()]
    geo = (site / "js/propuesta/geo3d.js").read_text(encoding="utf-8")
    assert "new URL('../../vendor/three-0.160.0/examples/fonts/helvetiker_bold.typeface.json', import.meta.url).href" in geo
    assert CDN_GSAP in (web / "atlas.html").read_text() and FUENTE in (web / "js/propuesta/geo3d.js").read_text()  # web/ sigue igual
    assert build_site.revisar(site) == []
    hay, faltan = build_site.modulos_three(site / "js", site / "vendor/three-0.160.0/examples/jsm")
    assert hay == {"controls/OrbitControls.js", "utils/Ayuda.js", "loaders/FontLoader.js"} and faltan == {}


@pytest.mark.parametrize("rel, texto, motivo", [
    ("extra.html", '<script src="https://ejemplo.invalid/x.js"></script>', 'extra.html: <script src="https://ejemplo.invalid/x.js"> externo'),
    ("extra.html", '<script src=" //ejemplo.invalid/x.js"></script>', "externo"),
    ("extra.html", '<script src="/\\ejemplo.invalid/x.js"></script>', "externo"),
    ("extra.html", '<script src="ht\ttps://ejemplo.invalid/x.js"></script>', "externo"),
    ("extra.html", '<script src="js/no-existe.js"></script>', "no existe en site/"),
    ("extra.html", '<script type="importmap">{"imports": {"x": "https://ejemplo.invalid/x.js"}}</script>', "URL externa en el importmap"),
    ("extra.html", '<script type="importmap">{"scopes": {"/": {"x": "//ejemplo.invalid/x.js"}}}</script>', "URL externa en el importmap"),
    ("extra.html", '<script type="importmap">{"imports": {"x": "./vendor/no-existe.js"}}</script>', "destino del importmap ./vendor/no-existe.js no existe"),
    ("extra.html", '<script type="importmap">{"imports": {"x": "vendor/gsap-3.12.5/gsap.min.js"}}</script>', "el navegador ignora el destino del importmap vendor/gsap"),
    ("extra.html", '<script type="importmap">{"imports": </script>', "importmap que no se puede leer"),
    ("extra.html", '<button onclick="alert(1)">x</button>', "código en el atributo <button onclick"),
    ("extra.html", '<a href=" javascript:alert(1)">x</a>', "código en el atributo <a href"),
    ("js/otro.js", "import { Nuevo } from 'three/addons/loaders/Nuevo.js';\n", "falta vendor/three-0.160.0/examples/jsm/loaders/Nuevo.js, que importa otro.js"),
    ("js/otro.js", "fetch('https://unpkg.com/algo@1/x.json');\n", "js/otro.js: pide https://unpkg.com/algo@1/x.json"),
    # Un import de un dominio que no es CDN conocido: la CSP del sitio lo bloquea y el atlas queda sin vistas
    ("js/otro.js", "import 'https://esm.sh/x@1';\n", "js/otro.js: importa https://esm.sh/x@1 de otro dominio"),
    ("js/otro.js", "import confeti from 'https://ga.jspm.io/npm:x@1/x.mjs';\n", "importa https://ga.jspm.io/npm:x@1/x.mjs"),
    ("js/propuesta/otro.js", "export { y } from '//esm.sh/y@2';\n", "js/propuesta/otro.js: importa //esm.sh/y@2"),
    ("js/otro.js", "const x = () => import('https://cdn.skypack.dev/x');\n", "importa https://cdn.skypack.dev/x"),
    ("js/otro.js", "const x = () => import(`//cdn.skypack.dev/x`);\n", "importa //cdn.skypack.dev/x"),
    ("js/otro.js", "import 'data:text/javascript,alert(1)';\n", "importa data:text/javascript,alert(1)"),
    ("vendor/three-0.160.0/examples/jsm/utils/Ayuda.js", "import { m } from './Falta.js';\n", "falta vendor/three-0.160.0/examples/jsm/utils/Falta.js, que importa three/addons/utils/Ayuda.js"),
])
def test_build_site_falla_con_codigo_de_fuera(build_site, web, tmp_path, rel, texto, motivo):
    (web / rel).parent.mkdir(parents=True, exist_ok=True)
    (web / rel).write_text("<!doctype html>" + texto if rel.endswith(".html") else texto, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        build_site.construir(web, tmp_path / "site")
    assert isinstance(e.value.code, str) and e.value.code.startswith("ERROR")  # sys.exit(mensaje): código 1
    assert motivo in e.value.code


def test_build_site_falla_si_falta_la_copia_de_la_fuente(build_site, web, tmp_path):
    (web / "vendor/three-0.160.0/examples/fonts/helvetiker_bold.typeface.json").unlink()
    with pytest.raises(SystemExit) as e:
        build_site.construir(web, tmp_path / "site")
    assert "falta vendor/three-0.160.0/examples/fonts/helvetiker_bold.typeface.json" in e.value.code


def test_vendor_del_repositorio_cubre_lo_que_importa_web():
    """web/vendor/three-0.160.0 trae todo módulo de three/addons que importa web/js (sin red: solo archivos locales)."""
    spec = importlib.util.spec_from_file_location("build_site", RAIZ / "scripts" / "build_site.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    hay, faltan = m.modulos_three(RAIZ / "web" / "js", RAIZ / "web" / m.THREE / "examples" / "jsm")
    assert faltan == {} and len(hay) >= 20
    for local in [*m.CDN.values(), *m.CDN_JS.values()]:
        assert (RAIZ / "web" / local).exists(), local


# ───────────────────────────── Modelos 3D bajo la CSP del sitio ─────────────────────────────

GUION_MODELOS = r"""// Sube GLB propios a la vista Modelos 3D y dice cómo terminó cada uno. Uso: node <guion> <url del atlas> <glb>...
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [url, ...glbs] = process.argv.slice(2);
(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const salida = { csp: [], archivos: [] };
  try {
    const ctx = await nav.newContext();
    await ctx.route((u) => u.origin !== new URL(url).origin, (r) => r.abort());
    await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
    await ctx.addInitScript(() => addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true));
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: 'load' });
    await page.evaluate(() => document.querySelector('nav.tabs a[data-view="modelos"]').click());
    await page.waitForFunction(() => document.querySelector('[data-slot="modelos.caps"]')?.children.length, null, { timeout: 60000 });
    const estado = '[data-slot="modelos.estado"]';
    for (const g of glbs) {
      const t0 = Date.now();
      await page.setInputFiles('#md-file', g);
      const fin = await page.waitForFunction((s) => { const t = document.querySelector(s).textContent; return /cargado desde tu equipo|No se pudo leer/.test(t) && t; }, estado, { timeout: 30000 }).then((h) => h.jsonValue(), () => null);
      salida.archivos.push({ fin, ms: Date.now() - t0, estado: fin || await page.$eval(estado, (e) => e.textContent) });
    }
  } finally { await nav.close(); }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _hay_playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(
        ["node", "-e", "require(process.env.PLAYWRIGHT_MODULE || 'playwright')"], capture_output=True).returncode == 0


def _glb_con_ktx2() -> bytes:
    """GLB inventado: un triángulo con una textura KTX2 (UASTC de 4 × 4, un bloque) que exige KHR_texture_basisu."""
    ktx2 = bytearray(176)
    ktx2[:12] = bytes([0xAB, 0x4B, 0x54, 0x58, 0x20, 0x32, 0x30, 0xBB, 0x0D, 0x0A, 0x1A, 0x0A])
    struct.pack_into("<9I", ktx2, 12, 0, 1, 4, 4, 0, 0, 1, 1, 0)  # vkFormat … supercompresión
    struct.pack_into("<4I2Q", ktx2, 48, 104, 44, 0, 0, 0, 0)     # dfd, kvd, sgd
    struct.pack_into("<3Q", ktx2, 80, 160, 16, 16)               # nivel 0
    struct.pack_into("<2I2H", ktx2, 104, 44, 0, 2, 40)
    ktx2[116:132] = bytes([166, 1, 2, 0, 3, 3, 0, 0, 16, 0, 0, 0, 0, 0, 0, 0])
    struct.pack_into("<HBB3I", ktx2, 132, 0, 127, 0, 0, 0, 0xFFFFFFFF)
    binario = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0) + struct.pack("<6f", 0, 0, 1, 0, 0, 1) + bytes(ktx2)
    gltf = json.dumps({
        "asset": {"version": "2.0"}, "extensionsUsed": ["KHR_texture_basisu"], "extensionsRequired": ["KHR_texture_basisu"],
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"extensions": {"KHR_texture_basisu": {"source": 0}}}],
        "images": [{"bufferView": 2, "mimeType": "image/ktx2"}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]},
                      {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 24},
                        {"buffer": 0, "byteOffset": 60, "byteLength": len(ktx2)}],
        "buffers": [{"byteLength": len(binario)}],
    }).encode()
    gltf += b" " * (-len(gltf) % 4)
    binario += b"\0" * (-len(binario) % 4)
    return (struct.pack("<3I", 0x46546C67, 2, 28 + len(gltf) + len(binario)) + struct.pack("<2I", len(gltf), 0x4E4F534A)
            + gltf + struct.pack("<2I", len(binario), 0x004E4942) + binario)


@pytest.mark.skipif(not _hay_playwright(), reason="Sin Node con Playwright (PLAYWRIGHT_MODULE o NODE_PATH; vea scripts/qa/LEEME.md)")
def test_modelos_glb_con_ktx2_bajo_la_csp_del_sitio(build_site, tmp_path, monkeypatch):
    """Con la CSP del sitio el transcodificador Basis no arranca (necesita evaluar código) y un GLB propio con texturas
    KTX2 se quedaba en «Leyendo…» para siempre. Ahora termina en un aviso, Draco sigue cargando y la página no deja
    violaciones de CSP. Corre con uvicorn de verdad y el sitio que arma build_site.py."""
    from app import config

    def sin_panel():
        raise RuntimeError("Falta la variable MONGODB_URI en el servicio del panel")
    monkeypatch.setattr(config, "cargar", sin_panel)
    build_site.construir(RAIZ / "web", tmp_path / "site")
    (tmp_path / "ktx2.glb").write_bytes(_glb_con_ktx2())
    (tmp_path / "modelos.cjs").write_text(GUION_MODELOS, encoding="utf-8")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(servidor.crear_servidor(None, tmp_path / "site"), http="h11", log_level="warning"))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 15
        while not srv.started and time.time() < fin:
            time.sleep(0.05)
        r = subprocess.run(["node", str(tmp_path / "modelos.cjs"), f"http://127.0.0.1:{sock.getsockname()[1]}/atlas",
                            str(tmp_path / "ktx2.glb"), str(RAIZ / "web/models/hospital_lod1.glb")],
                           capture_output=True, text=True, timeout=240)
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    ktx2, draco = salida["archivos"]
    assert ktx2["fin"] and ktx2["estado"].startswith("No se pudo leer ktx2.glb: usa texturas KTX2"), ktx2
    assert draco["estado"] == "hospital_lod1.glb cargado desde tu equipo.", draco
    assert salida["csp"] == []
