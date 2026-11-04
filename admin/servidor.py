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
from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
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
    decodificadores WebAssembly de Draco y meshopt y no habilita eval de JavaScript. Por eso aquí no corre el
    transcodificador Basis de KTX2Loader (embind arma funciones con new Function, también en su worker blob:, que hereda
    esta política): web/js/assets.js no registra KTX2 si no se puede evaluar código y avisa con un GLB que lo exige.
    blob: y data: son las texturas, mallas y workers que arma three (DRACOLoader corre en workers blob:)."""
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
<h1>Panel no disponible</h1><p><b>{motivo}</b></p><p>El sitio público sigue en línea. {consejo}</p><p><a href="/">
Volver al sitio</a></p></body></html>"""
CONSEJO = ("Revise las variables del servicio en Railway (<code>ADMIN</code>, <code>password</code> y "
           "<code>MONGODB_URI</code>) y vuelva a desplegar.")
CONSEJO_REINTENTO = ("El panel lo vuelve a intentar solo: recargue esta página en un minuto. Si el aviso sigue, revise "
                     "<code>MONGODB_URI</code> en las variables del servicio en Railway.")
REINTENTO = "No se pudo conectar con la base de datos."
OCUPADO = "El panel está atendiendo muchas peticiones. Intente de nuevo en unos segundos."
ESPERA_S = (2, 60)   # reintentos de crear el panel o de conectarlo a MongoDB: espera inicial y máxima
CUPOS_PANEL = 16     # peticiones de la API del panel atendidas a la vez (anyio presta 40 hilos a todo el servidor)
ESPERA_CUPO_S = 2    # sin cupo en este tiempo, 503
PLAZO_CUERPO_S = 10  # el cuerpo de una petición sin sesión (el ingreso) llega entero en este tiempo, o 408
SIN_CACHE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "X-Content-Type-Options": "nosniff"}


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


class CuerpoExcedido(Exception):
    """El cuerpo de la petición pasa del tope."""


def reglas_del_panel() -> tuple[frozenset, int]:
    """Rutas del panel que no piden sesión y el tope de su cuerpo (app/seguridad.py). Si el panel no se puede
    importar, en /panel/ queda el aviso 503, que no lee nada."""
    try:
        from app.seguridad import LIMITE_JSON, RUTAS_SIN_SESION
    except Exception:
        return frozenset(), 0
    return frozenset(RUTAS_SIN_SESION), LIMITE_JSON


class LimitePanel:
    """Pocas peticiones de la API del panel a la vez, para que el sitio público siempre tenga hilos libres.

    El panel (su guardia y sus endpoints) y los archivos del sitio (StaticFiles, FileResponse) usan el mismo grupo
    de 40 hilos de anyio. Si MongoDB se cae o se cuelga, cada petición de la API retiene su hilo hasta que vence la
    espera de pymongo; con este límite la API nunca ocupa más de `cupos`. La que no consigue cupo en `espera_s`
    recibe 503 con Retry-After. 16 cupos sobran para 1 a 3 administradores: cada vista pide 1 o 2 cosas a la API a la
    vez.

    Un cupo nunca espera bytes de un anónimo (16 conexiones que mandaban las cabeceras de un ingreso y no terminaban
    el cuerpo dejaban al administrador fuera del panel mientras quisieran):
    * Las páginas y los archivos del panel (todo lo que no es /api/* ni /salud) no tocan MongoDB y no piden cupo.
    * En las rutas sin sesión (`sin_sesion`: el ingreso), el cuerpo se lee entero antes de pedir cupo, con un plazo
      total (`plazo_s`: 408 y se cierra la conexión) y un tope (`limite`: 413), y se le entrega a la app.
    * El resto de /api/* no lee el cuerpo sin sesión: la guardia del panel (GuardiaApi) responde 401 antes."""

    def __init__(self, app, cupos: int, espera_s: float, sin_sesion=frozenset(), limite: int = 0,
                 plazo_s: float = PLAZO_CUERPO_S):
        self.app, self.cupos, self.espera_s = app, cupos, espera_s
        self.sin_sesion, self.limite, self.plazo_s = frozenset(sin_sesion), limite, plazo_s
        self._bucle = self._semaforo = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ruta, raiz = scope["path"], scope.get("root_path", "")
        ruta = (ruta[len(raiz):] or "/") if raiz and ruta.startswith(raiz) else ruta  # como seguridad.ruta_interna
        if not ruta.startswith("/api/") and ruta != "/salud":
            return await self.app(scope, receive, send)
        if ruta in self.sin_sesion:
            cabeceras = Headers(scope=scope)
            if cabeceras.get("content-length", "0") != "0" or "transfer-encoding" in cabeceras:
                receive = await self._cuerpo_entero(scope, receive, send, cabeceras)
                if receive is None:
                    return
        bucle = asyncio.get_running_loop()
        if self._bucle is not bucle:  # uno por bucle de eventos (en las pruebas, cada cliente abre el suyo)
            self._bucle, self._semaforo = bucle, asyncio.Semaphore(self.cupos)
        semaforo = self._semaforo
        try:
            await asyncio.wait_for(semaforo.acquire(), self.espera_s)
        except TimeoutError:
            return await PlainTextResponse(OCUPADO, 503, headers={
                "Retry-After": "2", **SIN_CACHE})(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            semaforo.release()

    async def _cuerpo_entero(self, scope, receive, send, cabeceras):
        """Lee el cuerpo entero y devuelve un `receive` que se lo entrega a la app. None si ya se respondió (408,
        413) o si el cliente se fue."""
        largo, partes, total = cabeceras.get("content-length", ""), [], 0
        try:
            if largo.isdigit() and int(largo) > self.limite:
                raise CuerpoExcedido
            async with asyncio.timeout(self.plazo_s):
                while True:
                    msg = await receive()
                    if msg["type"] == "http.disconnect":
                        return None
                    partes.append(msg.get("body", b""))
                    total += len(partes[-1])
                    if total > self.limite:
                        raise CuerpoExcedido
                    if not msg.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "La petición tardó demasiado en llegar"}, 408, headers={
                "Connection": "close", **SIN_CACHE})(scope, receive, send)
            return None
        except CuerpoExcedido:
            await JSONResponse({"detail": "La petición es demasiado grande"}, 413, headers={
                "Connection": "close", **SIN_CACHE})(scope, receive, send)
            return None
        cuerpo, entregado = b"".join(partes), False

        async def recibir():
            nonlocal entregado
            if entregado:
                return await receive()  # después del cuerpo solo queda la desconexión
            entregado = True
            return {"type": "http.request", "body": cuerpo, "more_body": False}
        return recibir


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
        Mount(PREFIJO, app=LimitePanel(montaje, CUPOS_PANEL, ESPERA_CUPO_S, *reglas_del_panel(), PLAZO_CUERPO_S)),
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
