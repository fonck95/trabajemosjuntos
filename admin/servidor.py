"""Servidor único del despliegue en Railway: el sitio público en la raíz y el panel en /panel/.

    uvicorn servidor:app --app-dir admin --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips=* \\
        --no-access-log --no-server-header

* `/` sirve `site/` (lo que arma `scripts/build_site.py`) como lo hacía Caddy: `{ruta}`, `{ruta}.html`,
  `{ruta}/index.html` y `404.html`, con las mismas cabeceras de seguridad y una Content-Security-Policy propia: el sitio
  comparte origen con el panel, así que solo corren los scripts de site/ (three y GSAP van incluidos) y sus <script> en
  línea por su hash.
* `/panel/` es el panel de administración (app/main.py) con su propia CSP, sesión y auditoría.
* `/health` responde siempre 200: el sitio público no depende de MongoDB ni del panel. Si faltan variables o MongoDB
  no responde, el sitio sigue en línea, el panel muestra un aviso y sigue intentando conectarse.
"""
from __future__ import annotations

import asyncio
import logging
import os
import stat
import sys
from html import escape
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from starlette.applications import Starlette
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PREFIJO = "/panel"
log = logging.getLogger("servidor")

if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))


# ───────────────────────────── Sitio público ─────────────────────────────

# Módulos que solo usa el sitio público
import base64
import errno
import hashlib
from html.parser import HTMLParser

from starlette.exceptions import HTTPException


class Sitio(StaticFiles):
    """Archivos de site/ con los atajos del Caddyfile anterior: «/atlas» sirve atlas.html, «/atlas/» lleva a «/atlas» (si
    no, las rutas relativas de la página quedan bajo /atlas/) y una ruta que no existe responde 404 con 404.html si lo
    hay. Solo GET y HEAD, también en los atajos."""

    def lookup_path(self, path):
        try:
            return super().lookup_path(path)
        except ValueError:  # «%00» en la ruta: os.stat no acepta el carácter nulo
            return "", None
        except PermissionError:
            raise HTTPException(401)  # como StaticFiles
        except OSError as e:
            if e.errno == errno.ENAMETOOLONG:
                return "", None
            raise

    async def _archivo(self, path):
        completa, st = await anyio.to_thread.run_sync(self.lookup_path, path)
        return (completa, st) if st is not None and stat.S_ISREG(st.st_mode) else (None, None)

    async def get_response(self, path, scope):
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(405, headers={"Allow": "GET, HEAD"})
        if path not in ("", "."):
            completa, st = await self._archivo(path)
            if st is None and "." not in path.rsplit("/", 1)[-1]:
                completa, st = await self._archivo(path + ".html")  # «/atlas» sirve atlas.html
            if st is not None and not scope["path"].endswith("/"):
                return self.file_response(completa, st, scope)
            if st is not None and (await self._archivo(os.path.join(path, "index.html")))[1] is None:
                # «/atlas/» → «/atlas». La ruta normalizada no lleva barras repetidas: el destino nunca es «//otro-sitio»
                destino = (scope.get("root_path") or "").rstrip("/") + "/" + path.replace(os.sep, "/")
                consulta = scope.get("query_string", b"").decode("latin-1")
                return RedirectResponse(destino + (f"?{consulta}" if consulta else ""), 308)
        return await super().get_response(path, scope)  # la raíz, las carpetas con index.html y el 404


class _ScriptsEnLinea(HTMLParser):
    """Texto exacto de cada <script> sin src de una página (incluidos los importmap)."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.textos, self._partes = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._partes = None if dict(attrs).get("src") is not None else []

    def handle_data(self, data):
        if self._partes is not None:
            self._partes.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._partes is not None:
            self.textos.append("".join(self._partes))
            self._partes = None


def hashes_en_linea(directorio: Path) -> list[str]:
    """'sha256-…' de cada <script> en línea de los .html de site/, como lo calcula el navegador (UTF-8; read_text ya
    convierte los fines de línea a \\n, como el parser de HTML)."""
    hashes = set()
    for pagina in sorted(directorio.rglob("*.html")):
        p = _ScriptsEnLinea()
        p.feed(pagina.read_text(encoding="utf-8", errors="replace"))
        p.close()
        hashes |= {"'sha256-" + base64.b64encode(hashlib.sha256(t.encode("utf-8")).digest()).decode() + "'"
                   for t in p.textos}
    return sorted(hashes)


def politica_sitio(directorio: Path) -> str:
    """CSP del sitio público, calculada al arrancar a partir de site/. Solo corren los scripts del propio origen y los
    <script> en línea que trae site/ (por su hash): ni CDN ni un <script> inyectado. 'wasm-unsafe-eval' deja compilar los
    decodificadores WebAssembly de Draco (y de Basis y meshopt) y no habilita eval de JavaScript. blob: y data: son las
    texturas, mallas y workers que arma three (DRACOLoader y KTX2Loader corren en workers blob:)."""
    return "; ".join([
        "default-src 'self'",
        "script-src " + " ".join(["'self'", "'wasm-unsafe-eval'", *hashes_en_linea(directorio)]),
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob:",
        "connect-src 'self' blob: data:",
        "worker-src 'self' blob:",
        "media-src 'self' blob: data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


class CabecerasSitio:
    """Cabeceras de seguridad en TODAS las respuestas del sitio público, también en los errores: la CSP del sitio,
    nosniff, X-XSS-Protection, Referrer-Policy y sin Server. Los HTTPException de StaticFiles (404, 405…) se responden
    aquí: si subieran a la aplicación de Starlette, saldrían sin estas cabeceras."""

    def __init__(self, app, politica: str):
        self.app = app
        self.cabeceras = [(b"content-security-policy", politica.encode()), (b"x-content-type-options", b"nosniff"),
                          (b"x-xss-protection", b"1; mode=block"), (b"referrer-policy", b"strict-origin-when-cross-origin")]
        self.quitar = {k for k, _ in self.cabeceras} | {b"server"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        empezada = False

        async def enviar(msg):
            nonlocal empezada
            if msg["type"] == "http.response.start":
                empezada = True
                msg = {**msg, "headers": [(k, v) for k, v in msg.get("headers", []) if k.lower() not in self.quitar]
                       + self.cabeceras}
            await send(msg)

        try:
            await self.app(scope, receive, enviar)
        except HTTPException as e:
            if empezada:
                raise
            await PlainTextResponse(e.detail, e.status_code, headers=e.headers)(scope, receive, enviar)
        except Exception:
            if empezada:
                raise
            log.exception("Error al servir %r", scope.get("path"))
            await PlainTextResponse("Internal Server Error", 500)(scope, receive, enviar)


def sitio_publico(directorio: Path):
    if not (directorio / "index.html").exists():
        log.error("No existe %s/index.html: corra scripts/build_data.py y scripts/build_site.py", directorio)

        async def sin_sitio(scope, receive, send):
            await PlainTextResponse("El sitio todavía no se ha construido", 503)(scope, receive, send)
        return CabecerasSitio(sin_sitio, politica_sitio(directorio))
    politica = politica_sitio(directorio)
    log.info("CSP del sitio público: %d scripts en línea por su hash", politica.count("'sha256-"))
    return CabecerasSitio(GZipMiddleware(Sitio(directory=directorio, html=True), minimum_size=1024), politica)


# ───────────────────────────── Panel ─────────────────────────────

AVISO = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,
initial-scale=1"><meta name="robots" content="noindex"><title>Panel no disponible</title><style>body{{font:16px/1.5
system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 20px;color:#111}}b{{color:#c8101a}}</style></head><body>
<h1>Panel no disponible</h1><p><b>{motivo}</b></p><p>El sitio público sigue en línea. Revise las variables del servicio
en Railway (<code>ADMIN</code>, <code>password</code> y <code>MONGODB_URI</code>) y vuelva a desplegar.</p><p><a href="/">
Volver al sitio</a></p></body></html>"""


def panel_no_disponible(motivo: str):
    async def responder(scope, receive, send):
        if scope["type"] != "http":
            return
        await HTMLResponse(AVISO.format(motivo=escape(motivo)), 503, headers={"Cache-Control": "no-store",
                                                                       "X-Robots-Tag": "noindex"})(scope, receive, send)
    return responder


def cargar_panel(cfg=None):
    """(app del panel, motivo si no se pudo crear). Un error del panel nunca tumba el sitio."""
    try:
        from app.main import crear_app
        panel = crear_app(cfg)
    except Exception as e:  # falta MONGODB_URI en Railway, variable mal escrita…
        log.error("El panel no pudo iniciar: %s", e)
        return None, str(e) if isinstance(e, RuntimeError) else "No se pudo iniciar el panel (vea el registro)."
    panel.state.listo = False  # la API responde 503 hasta que MongoDB conecte
    return panel, None


async def conectar_panel(panel, intento_max_s: int = 60) -> None:
    """Prepara MongoDB del panel en segundo plano y reintenta con espera creciente hasta lograrlo."""
    from app.main import preparar
    espera = 2
    while True:
        try:
            await asyncio.to_thread(preparar, panel)
            log.info("Panel listo en %s/", PREFIJO)
            return
        except Exception as e:
            log.warning("MongoDB todavía no responde (%s). Nuevo intento en %s s", type(e).__name__, espera)
            await asyncio.sleep(espera)
            espera = min(espera * 2, intento_max_s)


# ───────────────────────────── Aplicación ─────────────────────────────

def crear_servidor(cfg=None, sitio: Path | None = None) -> Starlette:
    sitio = Path(os.environ.get("SITIO_DIR") or sitio or RAIZ / "site")
    panel, motivo = cargar_panel(cfg)

    @asynccontextmanager
    async def ciclo(app):
        tarea = asyncio.create_task(conectar_panel(panel)) if panel is not None else None
        yield
        if tarea:
            tarea.cancel()
        if panel is not None:
            panel.state.cliente.close()

    async def salud(request):
        return PlainTextResponse("ok")

    async def al_panel(request):
        return RedirectResponse(PREFIJO + "/", 308)

    rutas = [
        Route("/health", salud),
        Route(PREFIJO, al_panel),
        Mount(PREFIJO, app=panel if panel is not None else panel_no_disponible(motivo)),
        Mount("/", app=sitio_publico(sitio)),
    ]
    app = Starlette(routes=rutas, lifespan=ciclo)
    app.state.panel = panel
    return app


def __getattr__(nombre: str):
    """`uvicorn servidor:app` crea el servidor al pedirlo; importar el módulo (pruebas) no lo crea."""
    if nombre == "app":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        globals()["app"] = crear_servidor()
        return globals()["app"]
    raise AttributeError(nombre)
