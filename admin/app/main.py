"""Panel de administración de la base única de habitantes de Yondó.

Arranque local:  uvicorn app.main:app --reload --no-access-log --no-server-header   (desde admin/, con ADMIN, password y MONGODB_URI en el entorno
o en admin/.env)
"""
from __future__ import annotations

import asyncio
import logging
from html import escape
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import ConnectionFailure
from starlette.middleware.gzip import GZipMiddleware

from . import acceso, config, db, migraciones
from .agente import proveedores
from .api import (acercamientos, agente, agente_mnemo, ajustes, calidad, personas, reuniones, sistema, tablero,
                  usuarios, zonas)
from .seguridad import (CabecerasSeguras, Cortacircuitos, GuardiaApi, base_de, limpiar_al_iniciar, ruta_interna,
                        sin_base)

WEB = Path(__file__).resolve().parents[1] / "web"
INDICE = (WEB / "index.html").read_text(encoding="utf-8")
log = logging.getLogger("panel")
INTENTOS_ARRANQUE = 3  # panel solo: intentos de conectar a MongoDB (2 s entre uno y otro) antes de cortar el arranque
# Las respuestas en flujo del asistente (NDJSON): cada evento tiene que llegar en cuanto sale
RUTAS_EN_FLUJO = frozenset({"/api/agente/mensajes", "/api/agente/confirmaciones"})


class GZipSalvoFlujos(GZipMiddleware):
    """GZip para todo menos las respuestas en flujo del asistente.

    El GZipMiddleware de Starlette (0.41) escribe cada trozo de una respuesta en flujo en un GzipFile sin vaciarlo:
    zlib retiene la salida y el navegador recibía todos los eventos juntos al final del turno. Los navegadores siempre
    piden gzip y `fetch` no lo puede evitar, así que esas rutas se excluyen aquí (las cabeceras de seguridad y la guardia
    se aplican igual)."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and ruta_interna(scope) in RUTAS_EN_FLUJO:
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def preparar(app: FastAPI) -> None:
    """Conecta y prepara MongoDB (índices, nomenclátor, etiquetas). Lanza la excepción si MongoDB no responde."""
    cfg = app.state.cfg
    # Los avisos van antes de conectar: si MongoDB no responde, el arranque se corta ahí
    if not cfg.usuario or not cfg.clave:
        log.warning("Faltan las variables ADMIN y password: nadie podrá ingresar al panel")
    elif len(cfg.clave) < 10:
        log.warning("La clave del panel tiene menos de 10 caracteres; use una más larga")
    try:
        db.inicializar(app.state.db)
    except migraciones.ErrorMigracion as e:
        # MongoDB responde, pero la migración del esquema falló: la causa real queda en el registro
        log.error("No se pudo migrar la base de datos: %s", e)
        raise
    except Exception:
        log.error("No se pudo conectar o preparar MongoDB en %s: revise la variable MONGODB_URI",
                  config.sin_credenciales(cfg.mongodb_uri))
        raise
    acceso.preparar(app.state.db)
    limpiar_al_iniciar(app.state.db, cfg)
    app.state.listo = True


@asynccontextmanager
async def ciclo(app: FastAPI):
    # Panel solo (uvicorn app.main:app): si MongoDB no responde tras unos intentos, el arranque se corta y el
    # despliegue falla. Los intentos compensan la espera corta de pymongo (db.TIEMPOS_MS) en un arranque en frío.
    for intento in range(1, INTENTOS_ARRANQUE + 1):
        try:
            await asyncio.to_thread(preparar, app)
            break
        except ConnectionFailure:
            if intento == INTENTOS_ARRANQUE:
                raise
            await asyncio.sleep(2)
    yield
    await proveedores.cerrar(app)  # los clientes de Anthropic y de Mnemo del asistente, si llegaron a crearse
    app.state.cliente.close()


def crear_app(cfg: config.Config | None = None) -> FastAPI:
    # httpx2 (lo usan el asistente y el SDK de Anthropic) registra a INFO la URL completa de cada petición: las llamadas
    # internas del asistente llevan cédulas y teléfonos en la consulta y no pueden quedar en el registro del servicio
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    app = FastAPI(title="Panel Yondó", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)
    app.state.cfg = cfg or config.cargar()
    app.state.cliente, app.state.db = db.conectar(app.state.cfg.mongodb_uri, app.state.cfg.mongodb_db or None)
    app.state.cortacircuitos = Cortacircuitos()
    # La guardia va por dentro de las demás: nada lee el cuerpo antes que ella, y sus respuestas llevan las cabeceras
    app.add_middleware(GuardiaApi)
    app.add_middleware(GZipSalvoFlujos, minimum_size=1024)
    app.add_middleware(CabecerasSeguras)
    for m in (sistema, tablero, personas, reuniones, calidad, usuarios, acercamientos, zonas, ajustes, agente,
              agente_mnemo):
        app.include_router(m.r)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        errores = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"detail": "; ".join(errores) or "Datos no válidos"}, status_code=422)

    @app.exception_handler(ConnectionFailure)
    async def _sin_conexion(request: Request, exc: ConnectionFailure):
        # MongoDB caído o colgado: 503 con una línea en el registro (no un 500 con la traza) y una pausa sin tocarlo
        app.state.cortacircuitos.fallo(exc)
        return sin_base(ruta_interna(request.scope))

    @app.get("/salud", include_in_schema=False)
    def salud():
        # Mientras conecta o en la pausa del cortacircuitos, la guardia responde 503 sin llegar aquí
        try:
            app.state.db.command("ping")
        except ConnectionFailure:
            raise
        except Exception:
            return JSONResponse({"ok": False, "detail": "Sin conexión a MongoDB"}, status_code=503)
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str, request: Request):
        # Toda ruta que no sea de la API ni un archivo estático carga la aplicación (enrutado en el navegador)
        if ruta.startswith("api/"):
            return JSONResponse({"detail": "No existe"}, status_code=404)
        # El panel puede ir montado bajo un prefijo (/panel dentro del sitio): las rutas absolutas de la página lo
        # llevan, y el navegador lo lee de <meta name="panel-base"> para la API y el enrutado
        base = base_de(request)
        pagina = INDICE.replace('"/static/', f'"{base}/static/').replace(
            '<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta name="panel-base" content="{escape(base)}">')
        return HTMLResponse(pagina, headers={"Cache-Control": "no-cache"})

    return app


def __getattr__(nombre: str):
    """`uvicorn app.main:app` (panel solo) crea la aplicación al pedirla; importar el módulo no la crea."""
    if nombre == "app":
        globals()["app"] = crear_app()
        return globals()["app"]
    raise AttributeError(nombre)
