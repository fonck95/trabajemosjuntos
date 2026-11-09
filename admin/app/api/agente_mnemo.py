"""La conexión del asistente con la cuenta de Mnemo del administrador (OAuth 2.1, `agente/mnemo_conexion.py`). Todas
las rutas son solo del administrador (`requiere("agente.conectar")`, en `acceso.SOLO_ADMIN`: el coordinador recibe 403
`permiso`) y, como todo POST y DELETE del panel, exigen el CSRF de la sesión.

* POST /api/agente/mnemo/conectar `{url?}` → `{"autorizar": URL de autorización de Mnemo}`. Sin `url`, la sugerida
  (`MNEMO_MCP_URL` o la última usada). El navegador va ahí con `location.assign` (la CSP no deja mandar un formulario
  a Mnemo y el panel no abre ventanas). Mnemo vuelve a `<origen><base>/ajustes?code=…&state=…&iss=…` (o `error=…`):
  una página de la SPA, porque la cookie del panel (SameSite=Strict) no viaja en esa navegación; la página quita la
  query de la URL y manda lo recibido a la ruta siguiente, ya con la cookie y el CSRF.
* POST /api/agente/mnemo/volver `{code?, state, iss?, error?, error_description?}` → la vista de la conexión
  (`mnemo_conexion.vista` con `url_sugerida`, la misma forma que `GET /api/agente/estado` → `mnemo.conexion`).
* DELETE /api/agente/mnemo → la vista más `"revocada": bool | None` (¿Mnemo revocó la concesión?).

Errores: 400, 409 o 502 con `{"codigo", "mensaje"}` (`mnemo_conexion.ErrorConexion`): `url`, `descubrimiento`,
`recurso`, `sin_oauth`, `servidor`, `sin_modelo` (ese Mnemo no ofrece usar sus modelos: hay que actualizarlo; con
`ANTHROPIC_API_KEY` sí se conecta, para sus herramientas), `registro`, `red` (502), `estado`, `emisor`, `denegada`,
`autorizacion`, `canje` y `conflicto` (409). La vuelta (`redirect_uri`) sale de la petición:
`{esquema}://{host}{base}/ajustes`. Detrás de HTTPS (`cookie_segura`, como en Railway) el esquema es siempre https:
uvicorn (`--proxy-headers`) solo lo cambia si `X-Forwarded-Proto` es exactamente un valor conocido, y con la cabecera
ausente, en mayúsculas o con una lista (proxies encadenados) quedaría en http, que Mnemo no acepta fuera de loopback.

El módulo de la conexión se importa al usarlo, como el bucle en `api/agente.py`: `crear_app` no depende de que el
catálogo de herramientas cargue."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..acceso import Quien, requiere
from ..seguridad import base_de, sesion_actual

r = APIRouter(prefix="/api", tags=["agente"])


class ConectarIn(BaseModel):
    url: str | None = Field(None, max_length=300)


class VolverIn(BaseModel):
    code: str | None = Field(None, max_length=2000)
    state: str = Field(..., min_length=1, max_length=200)
    iss: str | None = Field(None, max_length=300)
    error: str | None = Field(None, max_length=100)
    error_description: str | None = Field(None, max_length=500)


def _redirect_uri(request: Request) -> str:
    """La vuelta de Mnemo: la vista de Ajustes del panel, en el mismo origen y con el prefijo con que está montado.
    Con `cookie_segura` el panel solo funciona por HTTPS (la cookie es Secure): la vuelta es https aunque el esquema
    que vio uvicorn sea http (sin el puerto 80 de http, si el proxy lo dejó en `Host`). En local, el de la petición."""
    esquema, netloc = request.url.scheme, request.url.netloc
    if request.app.state.cfg.cookie_segura and esquema != "https":
        esquema = "https"
        if netloc.endswith(":80"):
            netloc = netloc[:-3]
    return f"{esquema}://{netloc}{base_de(request)}/ajustes"


async def _sesion(request: Request) -> str:
    """El id de la sesión (el hash de la cookie): el pendiente queda atado a ella."""
    s = (request.scope.get("state") or {}).get("sesion")
    if s is None:
        s = await run_in_threadpool(sesion_actual, request.app.state.db, request)
    if s is None or not s.get("_id"):
        raise HTTPException(401, "Inicie sesión")
    return str(s["_id"])


def _error(e) -> HTTPException:
    return HTTPException(e.estado, e.para_api())


@r.post("/agente/mnemo/conectar")
async def conectar(cuerpo: ConectarIn, request: Request, quien: Quien = Depends(requiere("agente.conectar"))):
    from ..agente import mnemo_conexion
    try:
        autorizar = await mnemo_conexion.iniciar(request.app, quien, url=cuerpo.url,
                                                 redirect_uri=_redirect_uri(request), sesion=await _sesion(request))
    except mnemo_conexion.ErrorConexion as e:
        raise _error(e) from None
    return {"autorizar": autorizar}


@r.post("/agente/mnemo/volver")
async def volver(cuerpo: VolverIn, request: Request, quien: Quien = Depends(requiere("agente.conectar"))):
    from ..agente import mnemo_conexion
    try:
        return await mnemo_conexion.volver(request.app, quien, sesion=await _sesion(request), state=cuerpo.state,
                                           code=cuerpo.code, iss=cuerpo.iss, error=cuerpo.error,
                                           error_description=cuerpo.error_description)
    except mnemo_conexion.ErrorConexion as e:
        raise _error(e) from None


@r.delete("/agente/mnemo")
async def desconectar(request: Request, quien: Quien = Depends(requiere("agente.conectar"))):
    from ..agente import mnemo_conexion
    try:
        return await mnemo_conexion.desconectar(request.app, quien)
    except mnemo_conexion.ErrorConexion as e:
        raise _error(e) from None
