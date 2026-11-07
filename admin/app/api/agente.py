"""API del asistente del panel (docs/agente.md).

* GET /api/agente/estado — si el asistente está disponible para quien pregunta y por qué no (`requiere("cuenta")`:
  cualquier rol lo consulta para saber si mostrar el botón).
* GET /api/agente/conversaciones, GET y DELETE /api/agente/conversaciones/{cid} — las conversaciones propias: solo
  su dueño las ve o las borra (de otra persona es un 404, como si no existiera).
* POST /api/agente/mensajes y POST /api/agente/confirmaciones — un turno en flujo (NDJSON, `bucle.py`). Lo que impide
  el turno sale antes como JSON normal (503, 403, 404, 409, 429).

El módulo del bucle (y con él el catálogo de herramientas) se importa al usarlo: `crear_app` no depende de que cada
herramienta cargue, y una herramienta rota deja sin asistente, no sin panel."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field, StrictBool, field_validator
from pymongo.database import Database

from ..acceso import Quien, requiere
from ..agente import conversaciones as conv_db
from ..agente import politica
from ..seguridad import obtener_db

log = logging.getLogger("panel")
r = APIRouter(prefix="/api", tags=["agente"])

ID_MAX = 10**12  # los ids de conversación son enteros pequeños; más grande ni siquiera cabe en MongoDB
NO_EXISTE = {"codigo": "no_existe", "mensaje": "No existe esa conversación."}


class MensajeIn(BaseModel):
    conversacion: int | None = Field(None, ge=1, le=ID_MAX)
    texto: str = Field(..., min_length=1, max_length=4000)
    # La vista, la ficha abierta, los filtros y el mapa: una pista que se limpia y se acota en `sistema.py`
    contexto: dict[str, Any] | None = None

    @field_validator("texto")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("el mensaje está vacío")
        return v


class DecisionIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    aprobar: StrictBool


class ConfirmacionIn(BaseModel):
    conversacion: int = Field(..., ge=1, le=ID_MAX)
    decisiones: list[DecisionIn] = Field(..., min_length=1, max_length=20)


def _exigir_rol(quien: Quien, agente: dict) -> None:
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        raise HTTPException(403, {"codigo": "agente_apagado", "mensaje": "El asistente no está habilitado para su rol."})


def _mnemo_activo(quien: Quien, agente: dict, cfg: Any) -> bool:
    if not cfg.mnemo_configurado:
        return False
    try:
        from ..agente.herramientas import mnemo
        return bool(mnemo.disponible_para(quien, agente, cfg))
    except Exception as e:  # noqa: BLE001 - el estado nunca falla por Mnemo
        log.warning("Asistente: no se pudo saber si Mnemo está disponible (%s)", type(e).__name__)
        return False


def _etiquetas(conv: dict) -> dict[str, str]:
    """La etiqueta (en gerundio) de cada herramienta de la conversación, para pintar el historial."""
    try:
        from ..agente import herramientas
        from ..agente.herramientas import mnemo
        out = {n: h.etiqueta for n, h in herramientas.por_nombre().items()}
        defs = conv_db.de_json(conv.get("mnemo"), [])
        if defs:
            out.update({h.nombre: h.etiqueta for h in mnemo.desde_definiciones(defs)})
        return out
    except Exception as e:  # noqa: BLE001 - sin etiquetas se muestra el nombre
        log.warning("Asistente: no se pudieron leer las etiquetas de las herramientas (%s)", type(e).__name__)
        return {}


@r.get("/agente/estado")
def estado(request: Request, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("cuenta"))):
    cfg = request.app.state.cfg
    ajustes, agente = politica.leer(db)
    sesion = (request.scope.get("state") or {}).get("sesion")
    motivo = politica.motivo(quien, cfg, agente, sesion, db)
    mnemo = _mnemo_activo(quien, agente, cfg)
    return {"disponible": motivo is None, "motivo": motivo, "configurado": cfg.agente_configurado,
            "es_admin": quien.es_admin, "escritura": agente["escritura"],
            "limite": {"usados": conv_db.uso_de(db, quien.uid), "maximo": politica.mensajes_diarios(ajustes, quien.rol)},
            "mnemo": {"activo": mnemo, "origen": politica.origen_mnemo(cfg) if mnemo else None},
            "sugerencias": politica.sugerencias(quien.rol) if motivo is None else []}


@r.get("/agente/conversaciones")
def conversaciones(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("agente.usar"))):
    _exigir_rol(quien, politica.leer(db)[1])
    return {"conversaciones": conv_db.listar(db, quien.uid)}


@r.get("/agente/conversaciones/{cid}")
def conversacion(cid: int = Path(..., ge=1, le=ID_MAX), db: Database = Depends(obtener_db),
                 quien: Quien = Depends(requiere("agente.usar"))):
    _exigir_rol(quien, politica.leer(db)[1])
    conv = conv_db.de_usuario(db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, dict(NO_EXISTE))
    return conv_db.para_interfaz(conv, conv_db.mensajes_de(db, cid), _etiquetas(conv))


@r.delete("/agente/conversaciones/{cid}")
def borrar_conversacion(request: Request, cid: int = Path(..., ge=1, le=ID_MAX), db: Database = Depends(obtener_db),
                        quien: Quien = Depends(requiere("agente.usar"))):
    """Borra la conversación y sus mensajes (también con el rol apagado: los datos son de su dueño). No mientras un
    turno la está usando: ese turno seguiría guardando en ella."""
    conv = conv_db.de_usuario(db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, dict(NO_EXISTE))
    ocupacion = getattr(request.app.state, "agente_ocupacion", None)
    if conv_db.ocupada(conv) or (ocupacion is not None and ocupacion.ocupada(cid)):
        raise HTTPException(409, {"codigo": "ocupada", "mensaje": "El asistente todavía está respondiendo en esa "
                                                                  "conversación. Espere a que termine."})
    if not conv_db.borrar(db, cid, quien.uid):
        raise HTTPException(404, dict(NO_EXISTE))
    return {"ok": True}


@r.post("/agente/mensajes")
async def mensajes(cuerpo: MensajeIn, request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    from ..agente import bucle
    return await bucle.abrir_mensaje(request, quien, cuerpo.conversacion, cuerpo.texto, cuerpo.contexto)


@r.post("/agente/confirmaciones")
async def confirmaciones(cuerpo: ConfirmacionIn, request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    from ..agente import bucle
    return await bucle.abrir_confirmacion(request, quien, cuerpo.conversacion,
                                          {d.id: d.aprobar for d in cuerpo.decisiones})
