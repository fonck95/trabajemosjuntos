"""La pantalla en off (app/pantalla.py) y la clave con que un agente la maneja por MCP (app/api/mcp.py).

* `GET /api/pantalla?v=N`: la vista Presentación en modo en off pregunta cada poco. Con la versión que ya tiene, 204 sin
  cuerpo; si cambió, el estado entero. Cada pregunta deja la pantalla como abierta (`visto`).
* `GET`, `POST` y `DELETE /api/pantalla/clave`: la clave MCP de la persona (una por persona; crear otra reemplaza la
  anterior). Se muestra una sola vez, al crearla: en la base queda su SHA-256 y la huella de la sesión de ese momento,
  así cambiar la clave del panel (o la credencial del administrador) la anula, como a las sesiones."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pymongo.database import Database

from .. import db as bd
from .. import pantalla
from ..acceso import Quien, requiere
from ..agente import guion as guion_presentacion
from ..seguridad import base_de, huella, huella_usuario, obtener_db

r = APIRouter(prefix="/api", tags=["pantalla"])

PREFIJO_CLAVE = "ypm_"   # se reconoce a simple vista (y en un escáner de secretos) sin decir nada de quién es


def huella_clave(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def huella_de_sesion(db: Database, cfg, uid: int) -> str | None:
    """La huella con que valen las sesiones de `uid` ahora (la del administrador de .env o la de ese usuario), o None si
    el usuario ya no existe o está inactivo."""
    if uid == 0:
        return huella(cfg)
    u = db.usuarios.find_one({"_id": uid, "activo": True}, {"version": 1})
    return huella_usuario(cfg, u) if u else None


def direccion_mcp(request: Request) -> str:
    """La dirección del servidor MCP tal como la ve quien está en el panel (en el servicio único, bajo /panel)."""
    return f"{request.url.scheme}://{request.url.netloc}{base_de(request)}/api/mcp"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@r.get("/pantalla")
def estado_pantalla(v: int | None = Query(None, ge=-1, le=2 ** 31), db: Database = Depends(obtener_db),
                    quien: Quien = Depends(requiere("presentacion.ver"))):
    doc = pantalla.marcar_vista(db, quien.uid)
    if v is not None and v == int(doc.get("v") or 0):
        return Response(status_code=204)
    g = guion_presentacion.cargar()
    if g is None:
        return Response(status_code=404)
    return pantalla.para_pantalla(pantalla.estado(doc, g))


def _info(doc: dict | None, request: Request) -> dict:
    return {"tiene": doc is not None, "creada": doc.get("creada") if doc else None,
            "usada": doc.get("usada") if doc else None, "direccion": direccion_mcp(request)}


@r.get("/pantalla/clave")
def ver_clave(request: Request, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("presentacion.ver"))):
    return _info(db.claves_mcp.find_one({"uid": quien.uid}, {"creada": 1, "usada": 1}), request)


@r.post("/pantalla/clave")
async def crear_clave(request: Request, db: Database = Depends(obtener_db),
                      quien: Quien = Depends(requiere("presentacion.ver"))):
    cfg = request.app.state.cfg

    def crear():
        firma = huella_de_sesion(db, cfg, quien.uid)
        clave = PREFIJO_CLAVE + secrets.token_urlsafe(32)
        db.claves_mcp.delete_many({"uid": quien.uid})
        db.claves_mcp.insert_one({"_id": huella_clave(clave), "uid": quien.uid, "huella": firma, "creada": _ahora(),
                                  "usada": None})
        bd.auditar(db, quien, "crear_clave_mcp", "usuario", quien.uid)
        return clave

    clave = await run_in_threadpool(crear)
    direccion = direccion_mcp(request)
    return {**_info({"creada": _ahora(), "usada": None}, request), "clave": clave,
            "direccion_con_clave": f"{direccion}?clave={clave}"}


@r.delete("/pantalla/clave")
def revocar_clave(request: Request, db: Database = Depends(obtener_db),
                  quien: Quien = Depends(requiere("presentacion.ver"))):
    borradas = db.claves_mcp.delete_many({"uid": quien.uid}).deleted_count
    if borradas:
        bd.auditar(db, quien, "revocar_clave_mcp", "usuario", quien.uid)
    return {"revocada": bool(borradas), **_info(None, request)}
