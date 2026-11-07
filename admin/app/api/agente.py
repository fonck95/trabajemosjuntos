"""API del asistente (en construcción: la completa el núcleo, ver docs/agente.md).

Rutas: GET /api/agente/estado, GET /api/agente/conversaciones, GET y DELETE /api/agente/conversaciones/{cid},
POST /api/agente/mensajes y POST /api/agente/confirmaciones (estas dos responden NDJSON en streaming)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..acceso import Quien, requiere

r = APIRouter(prefix="/api", tags=["agente"])


@r.get("/agente/estado")
def estado(quien: Quien = Depends(requiere("cuenta"))):
    return {"disponible": False, "motivo": "en_construccion"}


@r.get("/agente/conversaciones")
def conversaciones(quien: Quien = Depends(requiere("agente.usar"))):
    raise HTTPException(501, "En construcción")


@r.get("/agente/conversaciones/{cid}")
def conversacion(cid: int, quien: Quien = Depends(requiere("agente.usar"))):
    raise HTTPException(501, "En construcción")


@r.delete("/agente/conversaciones/{cid}")
def borrar_conversacion(cid: int, quien: Quien = Depends(requiere("agente.usar"))):
    raise HTTPException(501, "En construcción")


@r.post("/agente/mensajes")
async def mensajes(quien: Quien = Depends(requiere("agente.usar"))):
    raise HTTPException(501, "En construcción")


@r.post("/agente/confirmaciones")
async def confirmaciones(quien: Quien = Depends(requiere("agente.usar"))):
    raise HTTPException(501, "En construcción")
