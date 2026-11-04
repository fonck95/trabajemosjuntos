"""Calidad de datos: revisión de coincidencias por nombre y nomenclátor de lugares."""
from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import db as bd
from ..pipeline import texto as tx
from ..pipeline.importar import georreferenciar
from ..seguridad import Admin, obtener_db, requiere_admin
from .personas import mapa_lugares

r = APIRouter(prefix="/api", tags=["calidad"])


def _resumen(p: dict, lugares: dict) -> dict:
    return {"id": p["_id"], "nombre": p["nombre"], "cedula": p.get("cedula"), "telefono": p.get("telefono"),
            "telefono2": p.get("telefono2"), "correo": p.get("correo"), "direccion": p.get("direccion"),
            "fuentes": p.get("fuentes", []), "edad": p.get("edad"), "sexo": p.get("sexo"),
            "lugar": (lugares.get(p.get("lugar_id")) or {}).get("nombre") or p.get("lugar_texto"),
            "tramites": len(p.get("tramites") or []), "listas": "; ".join(p.get("listas") or [])}


@r.get("/coincidencias")
def coincidencias(estado: str = "pendiente", db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    if estado == "pendiente":  # las que ya no se pueden aceptar no se muestran (quedan cerradas)
        bd.cerrar_coincidencias_imposibles(db)
    lista = list(db.coincidencias.find({"estado": estado}).sort("puntaje", -1).limit(300))
    ids = {c["persona_id"] for c in lista} | {c["candidato_id"] for c in lista}
    personas = {p["_id"]: p for p in db.personas.find({"_id": {"$in": list(ids)}, **bd.ACTIVA},
                                                      {"notas": 0, "origen": 0, "asistencias": 0})}
    lugares = mapa_lugares(db)
    return [{"id": c["_id"], "puntaje": c["puntaje"], "detalle": c.get("detalle", {}), "estado": c["estado"],
             "persona": _resumen(personas[c["persona_id"]], lugares), "candidato": _resumen(personas[c["candidato_id"]], lugares)}
            for c in lista if c["persona_id"] in personas and c["candidato_id"] in personas]


class Decision(BaseModel):
    decision: Literal["aceptar", "rechazar"]


@r.post("/coincidencias/{cid}")
def resolver(cid: int, body: Decision, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    c = db.coincidencias.find_one({"_id": cid, "estado": "pendiente"})
    if c is None:
        raise HTTPException(404, "Ya fue resuelta o no existe")
    marca = {"resuelto_por": adm.usuario, "resuelto_en": bd.ahora()}
    if body.decision == "aceptar":
        a = db.personas.find_one({"_id": c["persona_id"], **bd.ACTIVA}, {"cedula": 1})
        b = db.personas.find_one({"_id": c["candidato_id"], **bd.ACTIVA}, {"cedula": 1})
        if a is None or b is None or (a.get("cedula") and b.get("cedula") and a["cedula"] != b["cedula"]):
            bd.cerrar_coincidencias_imposibles(db, [c["persona_id"]])
            raise HTTPException(409, "Tienen cédulas distintas" if a and b else "Una de las fichas ya se unió o suprimió")
        # Se conserva la ficha de trámites (tiene historial y ubicación) y recibe la cédula
        db.coincidencias.update_one({"_id": cid}, {"$set": {"estado": "aceptada", **marca}})
        bd.fusionar(db, c["candidato_id"], c["persona_id"], adm.usuario, adm.ip)
        georreferenciar(db, [c["candidato_id"]])
    else:
        db.coincidencias.update_one({"_id": cid}, {"$set": {"estado": "rechazada", **marca}})
        bd.auditar(db, adm.usuario, "rechazar_coincidencia", "persona", c["persona_id"], {"candidato": c["candidato_id"]}, adm.ip)
    return {"ok": True}


@r.get("/lugares")
def lugares(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    conteo = Counter(p.get("lugar_id") for p in db.personas.find({**bd.ACTIVA, "lugar_id": {"$ne": None}}, {"lugar_id": 1}))
    salida = [{"id": l["_id"], "nombre": l["nombre"], "tipo": l["tipo"], "zona": l["zona"], "lat": l.get("lat"), "lon": l.get("lon"),
               "alias": l.get("alias") or [], "padre": l.get("padre"), "fuente": l.get("fuente"), "precision": l.get("precision"),
               "tiene_poligono": bool(l.get("geom")), "n": conteo.get(l["_id"], 0)}
              for l in db.lugares.find({}, {"geom.type": 1, "nombre": 1, "tipo": 1, "zona": 1, "lat": 1, "lon": 1, "alias": 1, "padre": 1, "fuente": 1, "precision": 1})]
    return sorted(salida, key=lambda x: (-x["n"], x["nombre"]))


@r.get("/lugares/sin-reconocer")
def sin_reconocer(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    """Lugares escritos en las direcciones que no casan con el nomenclátor (para crearlos o agregarlos como alias)."""
    c = Counter(p["lugar_texto"] for p in db.personas.find({**bd.ACTIVA, "lugar_id": None, "lugar_texto": {"$ne": None}},
                                                           {"lugar_texto": 1}))
    return [{"texto": t, "n": n} for t, n in c.most_common(80) if n >= 2]


class LugarIn(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=80)
    tipo: Literal["barrio", "sector", "vereda", "caserio", "centro_poblado", "corregimiento"] | None = None
    zona: Literal["urbana", "rural"] | None = None
    lat: float | None = Field(None, ge=6.3, le=7.5)
    lon: float | None = Field(None, ge=-74.6, le=-73.6)
    alias: list[str] | None = None
    padre: str | None = Field(None, max_length=80)


def _recalcular(db: Database) -> None:
    georreferenciar(db)
    bd.recalcular_completitud(db)


@r.post("/lugares", status_code=201)
def crear_lugar(body: LugarIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not body.nombre or not body.tipo:
        raise HTTPException(422, "Nombre y tipo son obligatorios")
    zona = body.zona or ("urbana" if body.tipo in ("barrio", "sector") else "rural")
    lid = bd.siguiente_id(db, "lugares")
    try:
        db.lugares.insert_one({
            "_id": lid, "nombre": tx.limpiar(body.nombre), "tipo": body.tipo, "zona": zona, "lat": body.lat, "lon": body.lon,
            "alias": sorted({tx.limpiar(a) for a in body.alias or [] if a.strip()}),
            "padre": tx.limpiar(body.padre) or ("YONDO" if zona == "urbana" else None), "fuente": "manual",
            "precision": "manual" if body.lat is not None else None, "geom": None, "editado": True, "creado_en": bd.ahora()})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un lugar con ese nombre y tipo")
    bd.auditar(db, adm.usuario, "crear", "lugar", lid, body.model_dump(), adm.ip)
    _recalcular(db)
    return {"id": lid}


@r.patch("/lugares/{lid}")
def editar_lugar(lid: int, body: LugarIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not db.lugares.find_one({"_id": lid}, {"_id": 1}):
        raise HTTPException(404, "No existe")
    datos = body.model_dump(exclude_unset=True)
    if "nombre" in datos:
        datos["nombre"] = tx.limpiar(datos["nombre"])
    if "alias" in datos:
        datos["alias"] = sorted({tx.limpiar(a) for a in datos["alias"] or [] if a.strip()})
    if "lat" in datos:
        datos.update({"precision": "manual", "fuente": "manual"})
    if datos:
        db.lugares.update_one({"_id": lid}, {"$set": {**datos, "editado": True}})
        bd.auditar(db, adm.usuario, "editar", "lugar", lid, datos, adm.ip)
        _recalcular(db)
    return {"ok": True}


@r.post("/georreferenciar")
def regeocodificar(db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    res = georreferenciar(db)
    bd.recalcular_completitud(db)
    bd.auditar(db, adm.usuario, "georreferenciar", None, None, res, adm.ip)
    return res
