"""Panel de administración de la base única de habitantes de Yondó.

Arranque local:  uvicorn app.main:app --reload --no-access-log   (desde admin/, con ADMIN, password y MONGODB_URI en el entorno
o en admin/.env)
"""
from __future__ import annotations

import logging
import re
from html import escape
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import config, db
from .api import calidad, personas, reuniones, sistema, tablero
from .seguridad import CabecerasSeguras, GuardiaApi, base_de, limpiar_al_iniciar

WEB = Path(__file__).resolve().parents[1] / "web"
INDICE = (WEB / "index.html").read_text(encoding="utf-8")
log = logging.getLogger("panel")


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
    except Exception:
        log.error("No se pudo conectar o preparar MongoDB en %s: revise la variable MONGODB_URI",
                  re.sub(r"//[^@/]*@", "//", cfg.mongodb_uri))  # sin usuario ni clave de la URI
        raise
    limpiar_al_iniciar(app.state.db, cfg)
    app.state.listo = True


@asynccontextmanager
async def ciclo(app: FastAPI):
    # Panel solo (uvicorn app.main:app): si MongoDB no responde, el arranque se corta y el despliegue falla
    preparar(app)
    yield
    app.state.cliente.close()


def crear_app(cfg: config.Config | None = None) -> FastAPI:
    app = FastAPI(title="Panel Yondó", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)
    app.state.cfg = cfg or config.cargar()
    app.state.cliente, app.state.db = db.conectar(app.state.cfg.mongodb_uri, app.state.cfg.mongodb_db or None)
    # La guardia va por dentro de las demás: nada lee el cuerpo antes que ella, y sus respuestas llevan las cabeceras
    app.add_middleware(GuardiaApi)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CabecerasSeguras)
    for m in (sistema, tablero, personas, reuniones, calidad):
        app.include_router(m.r)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        errores = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"detail": "; ".join(errores) or "Datos no válidos"}, status_code=422)

    @app.get("/salud", include_in_schema=False)
    def salud():
        try:
            app.state.db.command("ping")
            return {"ok": True}
        except Exception:
            return JSONResponse({"ok": False, "detail": "Sin conexión a MongoDB"}, status_code=503)

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
