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
<h1>Panel no disponible</h1><p><b>{motivo}</b></p><p>El sitio público sigue en línea. {consejo}</p><p><a href="/">
Volver al sitio</a></p></body></html>"""
CONSEJO = ("Revise las variables del servicio en Railway (<code>ADMIN</code>, <code>password</code> y "
           "<code>MONGODB_URI</code>) y vuelva a desplegar.")
CONSEJO_REINTENTO = ("El panel lo vuelve a intentar solo: recargue esta página en un minuto. Si el aviso sigue, revise "
                     "<code>MONGODB_URI</code> en las variables del servicio en Railway.")
REINTENTO = "No se pudo conectar con la base de datos."
OCUPADO = "El panel está atendiendo muchas peticiones. Intente de nuevo en unos segundos."
ESPERA_S = (2, 60)   # reintentos de crear el panel o de conectarlo a MongoDB: espera inicial y máxima
CUPOS_PANEL = 16     # peticiones del panel atendidas a la vez (anyio presta 40 hilos a todo el servidor)
ESPERA_CUPO_S = 2    # sin cupo en este tiempo, 503


def panel_no_disponible(motivo: str, reintenta: bool = False):
    cabeceras = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
    if reintenta:
        cabeceras["Retry-After"] = "60"
    pagina = AVISO.format(motivo=escape(motivo), consejo=CONSEJO_REINTENTO if reintenta else CONSEJO)

    async def responder(scope, receive, send):
        if scope["type"] != "http":
            return
        await HTMLResponse(pagina, 503, headers=cabeceras)(scope, receive, send)
    return responder


def cargar_panel(cfg=None):
    """(app del panel, motivo si no se pudo crear, ¿reintentar?). Un error del panel nunca tumba el sitio.

    Un RuntimeError es de configuración (falta MONGODB_URI, un número mal escrito…) y no se arregla sin volver a
    desplegar. Cualquier otro error se reintenta: pymongo resuelve el DNS de una URI mongodb+srv:// (Atlas) al crear
    el cliente, y un fallo pasajero del DNS no debe dejar el panel fuera hasta el próximo despliegue."""
    try:
        from app.main import crear_app
        panel = crear_app(cfg)
    except RuntimeError as e:
        log.error("El panel no pudo iniciar: %s", e)
        return None, str(e), False
    except Exception as e:
        from app.config import sin_credenciales
        log.warning("El panel no pudo iniciar (%s: %s). Se vuelve a intentar", type(e).__name__,
                    sin_credenciales(str(e))[:300])
        return None, REINTENTO, True
    panel.state.listo = False  # la API responde 503 hasta que MongoDB conecte
    return panel, None, False


async def conectar_panel(panel) -> None:
    """Prepara MongoDB del panel en segundo plano y reintenta con espera creciente hasta lograrlo."""
    from app.main import preparar
    espera, maximo = ESPERA_S
    while True:
        try:
            await asyncio.to_thread(preparar, panel)
            log.info("Panel listo en %s/", PREFIJO)
            return
        except Exception as e:
            log.warning("MongoDB todavía no responde (%s). Nuevo intento en %s s", type(e).__name__, espera)
            await asyncio.sleep(espera)
            espera = min(espera * 2, maximo)


class PanelDiferido:
    """Destino del montaje /panel que cambia en caliente: el aviso 503 mientras el panel no se pudo crear y el panel
    en cuanto se crea (ver `crear_servidor`)."""

    def __init__(self, destino):
        self.destino = destino

    async def __call__(self, scope, receive, send):
        await self.destino(scope, receive, send)


class LimitePanel:
    """Pocas peticiones del panel a la vez, para que el sitio público siempre tenga hilos libres.

    El panel (su guardia y sus endpoints) y los archivos del sitio (StaticFiles, FileResponse) usan el mismo grupo
    de 40 hilos de anyio. Si MongoDB se cae o se cuelga, cada petición del panel retiene su hilo hasta que vence la
    espera de pymongo; con este límite el panel nunca ocupa más de `cupos`. La que no consigue cupo en `espera_s`
    recibe 503 con Retry-After. 16 cupos sobran para 1 a 3 administradores: cada vista pide 1 o 2 cosas a la API a la
    vez y los archivos del panel se despachan en milisegundos."""

    def __init__(self, app, cupos: int, espera_s: float):
        self.app, self.cupos, self.espera_s = app, cupos, espera_s
        self._bucle = self._semaforo = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        bucle = asyncio.get_running_loop()
        if self._bucle is not bucle:  # uno por bucle de eventos (en las pruebas, cada cliente abre el suyo)
            self._bucle, self._semaforo = bucle, asyncio.Semaphore(self.cupos)
        semaforo = self._semaforo
        try:
            await asyncio.wait_for(semaforo.acquire(), self.espera_s)
        except TimeoutError:
            return await PlainTextResponse(OCUPADO, 503, headers={
                "Retry-After": "2", "Cache-Control": "no-store", "X-Robots-Tag": "noindex",
                "X-Content-Type-Options": "nosniff"})(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            semaforo.release()


# ───────────────────────────── Aplicación ─────────────────────────────

def crear_servidor(cfg=None, sitio: Path | None = None) -> Starlette:
    sitio = Path(os.environ.get("SITIO_DIR") or sitio or RAIZ / "site")
    panel, motivo, reintentar = cargar_panel(cfg)
    montaje = PanelDiferido(panel if panel is not None else panel_no_disponible(motivo, reintentar))

    async def iniciar_panel(app):
        """Si al arrancar no se pudo crear el panel, lo reintenta con espera creciente y lo monta en cuanto existe;
        luego lo conecta a MongoDB."""
        p, (espera, maximo) = app.state.panel, ESPERA_S
        while p is None:
            await asyncio.sleep(espera)
            espera = min(espera * 2, maximo)
            p, motivo, otra_vez = await asyncio.to_thread(cargar_panel, cfg)
            if p is None and not otra_vez:
                montaje.destino = panel_no_disponible(motivo)
                return
            if p is not None:
                app.state.panel = montaje.destino = p
                log.info("Panel creado en %s/: se conecta a MongoDB", PREFIJO)
        await conectar_panel(p)

    @asynccontextmanager
    async def ciclo(app):
        tarea = asyncio.create_task(iniciar_panel(app)) if panel is not None or reintentar else None
        yield
        if tarea:
            tarea.cancel()
        if app.state.panel is not None:
            app.state.panel.state.cliente.close()

    async def salud(request):
        return PlainTextResponse("ok")

    async def al_panel(request):
        return RedirectResponse(PREFIJO + "/", 308)

    rutas = [
        Route("/health", salud),
        Route(PREFIJO, al_panel),
        Mount(PREFIJO, app=LimitePanel(montaje, CUPOS_PANEL, ESPERA_CUPO_S)),
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
