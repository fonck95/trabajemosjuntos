"""Servidor único del despliegue en Railway: el sitio público en la raíz y el panel en /panel/.

    uvicorn servidor:app --app-dir admin --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips=* \\
        --no-access-log

* `/` sirve `site/` (lo que arma `scripts/build_site.py`) como lo hacía Caddy: `{ruta}`, `{ruta}.html`,
  `{ruta}/index.html` y `404.html`, con las mismas cabeceras de seguridad y sin Content-Security-Policy (el visor 3D
  carga texturas desde blob:).
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

class Sitio(StaticFiles):
    """Archivos de site/ con los mismos atajos del Caddyfile anterior: «/atlas» sirve atlas.html, y una ruta que no
    existe responde 404 con 404.html si lo hay."""

    async def get_response(self, path, scope):
        ultimo = path.rsplit("/", 1)[-1]
        if path not in ("", ".") and not path.endswith("/") and "." not in ultimo:
            _, existe = await anyio.to_thread.run_sync(self.lookup_path, path)
            if existe is None:
                html, st = await anyio.to_thread.run_sync(self.lookup_path, path + ".html")
                if st is not None and stat.S_ISREG(st.st_mode):
                    return self.file_response(html, st, scope)
        return await super().get_response(path, scope)


class CabecerasSitio:
    """Las cabeceras que ponía Caddy al sitio público (sin CSP, que bloquearía las texturas blob: del visor 3D)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def enviar(msg):
            if msg["type"] == "http.response.start":
                h = [(k, v) for k, v in msg.get("headers", []) if k.lower() != b"server"]
                h += [(b"x-content-type-options", b"nosniff"), (b"x-xss-protection", b"1; mode=block"),
                      (b"referrer-policy", b"strict-origin-when-cross-origin")]
                msg = {**msg, "headers": h}
            await send(msg)

        await self.app(scope, receive, enviar)


def sitio_publico(directorio: Path):
    if not (directorio / "index.html").exists():
        log.error("No existe %s/index.html: corra scripts/build_data.py y scripts/build_site.py", directorio)

        async def sin_sitio(scope, receive, send):
            await PlainTextResponse("El sitio todavía no se ha construido", 503)(scope, receive, send)
        return sin_sitio
    return CabecerasSitio(GZipMiddleware(Sitio(directory=directorio, html=True), minimum_size=1024))


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
