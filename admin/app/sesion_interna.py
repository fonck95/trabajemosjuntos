"""La sesión interna con que corre una herramienta del asistente que pide un agente externo por MCP (`api/mcp.py`).

Por qué una sesión y no otra vía: las herramientas llaman a la API del panel (`agente.interno.ApiInterna`) con una
cookie y su CSRF, y así cada llamada pasa por la misma guardia de siempre (`GuardiaApi`, `sesion_actual`,
`rechazo_de_cuenta`, `requiere`): usuario activo, la huella de su versión vigente (cambio de clave, de rol, «Cerrar
sesiones»), permisos, alcance, proyección por rol, lecturas y auditoría. Una segunda forma de autenticar dentro de la
guardia tendría que copiar todo eso y podría desviarse.

* Se abre una por cada `tools/call` (y por nada más) y se cierra al terminar, en un `finally`: dura como mucho
  `DURACION_S` (el índice TTL de `sesiones.expira` y `sesion_actual` la vencen aunque el proceso se caiga a mitad).
* El token nunca sale del proceso: no va en una cookie del navegador ni en una respuesta. En la base queda solo su
  SHA-256, como el de cualquier sesión.
* Lleva `via` («mcp»): `crear_sesion` no la cuenta al cerrar las sesiones más viejas de la persona (un agente externo no
  le cierra al navegador la suya), el detalle de Usuarios no la lista, y `acceso.Quien.via` y la auditoría marcan que
  el cambio llegó por un agente externo.
* Se escribe en `app.state.db`: es la base que lee la guardia (las pruebas que reemplazan `obtener_db` no la tocan).
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi.concurrency import run_in_threadpool
from pymongo.database import Database

from .acceso import VIAS
from .seguridad import ROLES_USUARIO, _hash, huella, huella_usuario

DURACION_S = 300


@dataclass(frozen=True)
class SesionInterna:
    """Lo que hace falta para pedir a la API con esta sesión: el token (la cookie), su CSRF y su id en `sesiones`."""
    token: str
    csrf: str
    sid: str


def abrir(db: Database, cfg: Any, uid: int, *, via: str = "mcp", ip: str | None = None,
          segundos: int = DURACION_S) -> SesionInterna:
    """Abre una sesión interna de `uid` (0: el administrador de `.env`). Lanza `PermissionError` si la persona ya no
    puede tener sesión (inactiva, borrada o con un rol que no es de usuario): falla cerrada, como `sesion_actual`."""
    if via not in VIAS:
        raise ValueError(f"Vía desconocida: {via!r}")
    if uid:
        u = db.usuarios.find_one({"_id": uid, "activo": True}, {"usuario": 1, "rol": 1, "version": 1})
        if not u or u.get("rol") not in ROLES_USUARIO:
            raise PermissionError("La cuenta ya no puede abrir sesión")
        usuario, rol, version, firma = u.get("usuario"), u["rol"], u.get("version"), huella_usuario(cfg, u)
    else:
        # El administrador sale de la sesión con uid 0 firmada con la credencial vigente (`acceso._quien_de`)
        usuario, rol, version, firma = cfg.usuario, "admin", None, huella(cfg)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    ahora = datetime.now(timezone.utc)
    sid = _hash(token)
    db.sesiones.insert_one({"_id": sid, "usuario": usuario, "uid": uid or 0, "rol": rol, "version": version,
                            "csrf": csrf, "huella": firma, "creada": ahora,
                            "expira": ahora + timedelta(seconds=segundos), "ultima_actividad": ahora, "ip": ip,
                            "agente": via, "via": via})
    return SesionInterna(token, csrf, sid)


def cerrar(db: Database, sid: str) -> None:
    """Borra la sesión interna (solo una con `via`: nunca la de un navegador, aunque se pase su id)."""
    db.sesiones.delete_one({"_id": sid, "via": {"$exists": True}})


@asynccontextmanager
async def api_interna(app: Any, uid: int, *, via: str = "mcp", ip: str | None = None) -> AsyncIterator[Any]:
    """`ApiInterna` con una sesión interna de `uid` en la base de la guardia (`app.state.db`); al salir, cierra el
    cliente y borra la sesión aunque la herramienta haya fallado o la hayan cancelado. Lanza `PermissionError` si la
    persona ya no puede tener sesión."""
    from .agente.interno import ApiInterna  # aquí: el cliente interno importa la capa de herramientas
    db = app.state.db
    s = await run_in_threadpool(abrir, db, app.state.cfg, uid, via=via, ip=ip)
    api = ApiInterna(app, s.token, s.csrf, ip)
    try:
        yield api
    finally:
        try:
            await api.cerrar()
        finally:
            await run_in_threadpool(cerrar, db, s.sid)
