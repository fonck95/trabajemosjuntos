"""La pantalla en off (app/pantalla.py) y la clave con que un agente la maneja por MCP (app/api/mcp.py).

* `GET /api/pantalla?v=N`: la vista Presentación en modo en off pregunta cada poco. Con la versión que ya tiene, 204 sin
  cuerpo; si cambió, el estado entero. Cada pregunta deja la pantalla como abierta (`visto`).
* El recorrido narrado (`app/recorrido.py`): `POST /api/pantalla/progreso` (el avance que manda la página que lo
  reproduce: la pestaña, el proyector o la pantalla en off; no sube la versión ni marca la pantalla como abierta),
  `POST /api/pantalla/recorrido/control` (los botones de la tarjeta del chat cuando suena en otra pantalla) y
  `GET /api/pantalla/recorrido` (la tarjeta lo sigue; solo lectura, tampoco marca `visto`).
* `GET`, `POST` y `DELETE /api/pantalla/clave`: la clave MCP de la persona (una por persona; crear otra reemplaza la
  anterior). Se muestra una sola vez, al crearla: en la base queda su SHA-256 y la huella de la sesión de ese momento,
  así cambiar la clave del panel (o la credencial del administrador) la anula, como a las sesiones."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pymongo.database import Database

from .. import db as bd
from .. import pantalla
from .. import recorrido as rec
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
    return pantalla.para_pantalla(pantalla.estado(doc, g), doc, g)


# ───────────────────────────── El recorrido narrado ─────────────────────────────

class ProgresoEntrada(BaseModel):
    """El avance del reproductor (admin/web/js/reproductor.js): la forma exacta, con listas cerradas."""
    model_config = ConfigDict(extra="forbid")
    rid: str = Field(..., pattern=r"^[0-9a-f]{12}$")
    n: StrictInt = Field(..., ge=1, le=rec.MAX_ESCENAS)
    de: StrictInt = Field(..., ge=1, le=rec.MAX_ESCENAS)
    fase: Literal[rec.FASES]
    frase: StrictInt = Field(0, ge=0, le=rec.MAX_FRASES - 1)
    voz: Literal[rec.VOCES]
    motivo: Literal[rec.MOTIVOS] | None = None
    aviso: Literal[rec.AVISOS] | None = None
    t_ms: StrictInt = Field(0, ge=0, le=600_000)


class ControlEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rid: str = Field(..., pattern=r"^[0-9a-f]{12}$")
    accion: Literal[rec.CONTROLES]


def _guion():
    g = guion_presentacion.cargar()
    if g is None:
        raise HTTPException(404, "La presentación no está en este servidor")
    return g


@r.post("/pantalla/progreso", status_code=204)
def progreso(p: ProgresoEntrada, db: Database = Depends(obtener_db),
             quien: Quien = Depends(requiere("presentacion.ver"))):
    if p.n > p.de:
        raise HTTPException(422, "La escena pasa del total")
    if not pantalla.guardar_progreso(db, quien.uid, p.model_dump(exclude_none=True)):
        raise HTTPException(409, "Ese recorrido ya no es el vigente")
    return Response(status_code=204)


@r.post("/pantalla/recorrido/control")
def control_recorrido(c: ControlEntrada, db: Database = Depends(obtener_db),
                      quien: Quien = Depends(requiere("presentacion.ver"))):
    g = _guion()
    try:
        res = pantalla.controlar(db, quien.uid, g, c.accion, "panel", rid=c.rid)
    except ValueError:
        raise HTTPException(409, "No hay un recorrido sonando con ese id") from None
    x = pantalla.resumen_recorrido(res["doc"], g) or {}
    return {k: x.get(k) for k in ("id", "titulo", "escena", "de", "fase", "cerrado")}


@r.get("/pantalla/recorrido")
def ver_recorrido(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("presentacion.ver"))):
    """Dónde va el recorrido (para la tarjeta del chat cuando suena en otra pantalla). Solo lectura: no marca `visto`."""
    g = _guion()
    doc = pantalla.leer(db, quien.uid)
    x = pantalla.resumen_recorrido(doc, g)
    pr = pantalla.progreso_de(doc, pantalla.recorrido_de(doc, g)) or {}
    return {"recorrido": x and {k: x[k] for k in ("id", "titulo", "destino", "cerrado", "escena", "de", "fase",
                                                    "motivo", "voz", "hace_s")},
            "frase": pr.get("frase"), "avisos": (x or {}).get("avisos", [])}


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
