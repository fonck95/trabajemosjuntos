"""Llamadas del asistente a la API del panel, dentro del mismo proceso y con la sesión del usuario del turno.

Las herramientas no reimplementan las reglas: piden a las mismas rutas que usa la interfaz, por ASGI y sin red, con la
cookie de sesión, el CSRF y la IP de la petición del chat. Así cada llamada pasa por GuardiaApi y por `requiere`
(sesión vigente, permisos, límite de frecuencia), por el alcance de planilleros y consultores, el presupuesto diario y
las lecturas, la proyección por rol, el bloqueo de quien no autorizó, la idempotencia y la auditoría con el uid y el rol
de quien pregunta. Va directo a la app del panel (`request.app`), no al servidor único: no pide otro cupo de
`LimitePanel` y no puede interbloquearse con el turno que la llama.

Las respuestas que no son 2xx se convierten en `ErrorHerramienta` con el `detail` de la API, que el modelo le explica a
la persona. Un 401 o un 503 terminan el turno (`fatal`)."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx2

from ..seguridad import COOKIE
from .herramientas.base import ErrorHerramienta

log = logging.getLogger("panel")
BASE_INTERNA = "http://panel.interno"
PLAZO_S = 60.0


def _detalle(r: httpx2.Response) -> Any:
    try:
        datos = r.json()
    except (json.JSONDecodeError, ValueError):
        return (r.text or "").strip()[:500] or None
    return datos.get("detail", datos) if isinstance(datos, dict) else datos


def error_de(r: httpx2.Response) -> ErrorHerramienta:
    """La respuesta de error de la API como `ErrorHerramienta` (sin datos personales nuevos: es el `detail` que la
    interfaz ya mostraría al mismo usuario)."""
    d = _detalle(r)
    mensaje = d.get("mensaje") if isinstance(d, dict) else (d if isinstance(d, str) else None)
    codigo = d.get("codigo") if isinstance(d, dict) else None
    extra = {k: v for k, v in d.items() if k not in ("mensaje", "codigo")} if isinstance(d, dict) else None
    s = r.status_code
    if s == 401:
        return ErrorHerramienta("La sesión terminó. Hay que volver a ingresar al panel.", "sesion", estado=s, fatal=True)
    if s == 503:
        return ErrorHerramienta("La base de datos no responde en este momento. Intente de nuevo en un rato.", "base",
                                estado=s, fatal=True)
    if s == 403:
        return ErrorHerramienta(mensaje or "Su rol no permite esta acción.", codigo or "permiso", estado=s,
                                detalle=extra or None)
    if s == 404:
        return ErrorHerramienta(mensaje or "No existe.", codigo or "no_existe", estado=s, detalle=extra or None)
    if s == 429:
        # «volumen» (tope diario de personas) y el tope de mensajes del asistente no se arreglan reintentando
        return ErrorHerramienta(mensaje or "Demasiadas consultas seguidas.", codigo or "frecuencia", estado=s,
                                detalle=extra or None, fatal=(codigo == "volumen"))
    if s in (409, 422, 400, 413):
        return ErrorHerramienta(mensaje or (d if isinstance(d, str) else "La API rechazó la petición."),
                                codigo or ("invalido" if s != 409 else "conflicto"), estado=s,
                                detalle=extra if extra else (d if not isinstance(d, (str, dict)) else None))
    log.warning("Asistente: la API interna respondió %s", s)
    return ErrorHerramienta("La API del panel falló al atender la herramienta.", "error", estado=s)


class ApiInterna:
    """Cliente de la API del panel con la identidad del usuario del turno. Se crea por turno y se cierra al final."""

    def __init__(self, app: Any, cookie: str, csrf: str, ip: str | None = None):
        cabeceras = {"cookie": f"{COOKIE}={cookie}", "x-csrf-token": csrf, "accept": "application/json",
                     "accept-encoding": "identity", "user-agent": "panel-asistente"}
        if ip:
            cabeceras["x-real-ip"] = ip
        self._cliente = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False), base_url=BASE_INTERNA,
            headers=cabeceras, timeout=PLAZO_S, trust_env=False, follow_redirects=False)

    @classmethod
    def desde_peticion(cls, request: Any) -> "ApiInterna":
        """Con la cookie, el CSRF y la IP de la petición del chat (la sesión ya validada por GuardiaApi)."""
        from ..seguridad import ip_de
        sesion = (request.scope.get("state") or {}).get("sesion") or {}
        return cls(request.app, request.cookies.get(COOKIE, ""), str(sesion.get("csrf") or ""), ip_de(request))

    async def pedir(self, metodo: str, ruta: str, *, params: dict | None = None, json_: Any = None,
                    clave: str | None = None, respuesta: bool = False) -> Any:
        """`metodo` y `ruta` (`/api/...`) de una ruta existente; `params` sin vacíos; `clave` = Idempotency-Key de una
        escritura (la misma para el mismo `tool_use`). Devuelve el JSON (o la respuesta entera con `respuesta`)."""
        if not ruta.startswith("/api/"):
            raise ValueError("Solo rutas de la API del panel")
        limpio = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        cab = {"idempotency-key": clave} if clave else None
        try:
            r = await self._cliente.request(metodo, ruta, params=limpio or None, json=json_, headers=cab)
        except httpx2.TimeoutException:
            raise ErrorHerramienta("La API del panel tardó demasiado en responder.", "plazo") from None
        except httpx2.HTTPError as e:
            log.warning("Asistente: la API interna falló (%s)", type(e).__name__)
            raise ErrorHerramienta("No se pudo consultar la API del panel.", "error") from None
        if r.status_code >= 400:
            raise error_de(r)
        if respuesta:
            return r
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except (json.JSONDecodeError, ValueError):
            raise ErrorHerramienta("La API del panel respondió algo que no es JSON.", "error") from None

    async def get(self, ruta: str, params: dict | None = None, **kw: Any) -> Any:
        return await self.pedir("GET", ruta, params=params, **kw)

    async def post(self, ruta: str, cuerpo: Any = None, **kw: Any) -> Any:
        return await self.pedir("POST", ruta, json_=cuerpo if cuerpo is not None else {}, **kw)

    async def patch(self, ruta: str, cuerpo: Any = None, **kw: Any) -> Any:
        return await self.pedir("PATCH", ruta, json_=cuerpo if cuerpo is not None else {}, **kw)

    async def put(self, ruta: str, cuerpo: Any = None, **kw: Any) -> Any:
        return await self.pedir("PUT", ruta, json_=cuerpo if cuerpo is not None else {}, **kw)

    async def cerrar(self) -> None:
        await self._cliente.aclose()
