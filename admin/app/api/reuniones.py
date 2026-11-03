"""Reuniones: agenda, registro de asistentes y lo que se aprende de cada habitante en ellas.

La asistencia vive dentro de cada persona (`asistencias`), así su historial se lee de una vez."""
from __future__ import annotations

import csv
import io
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from .. import db as bd
from ..seguridad import Admin, obtener_db, requiere_admin
from .personas import mapa_lugares

r = APIRouter(prefix="/api/reuniones", tags=["reuniones"])


class ReunionIn(BaseModel):
    titulo: str | None = Field(None, min_length=3, max_length=160)
    fecha: str | None = None
    hora: str | None = Field(None, max_length=5)
    lugar_texto: str | None = Field(None, max_length=160)
    lugar_id: int | None = None
    lat: float | None = Field(None, ge=6.3, le=7.5)
    lon: float | None = Field(None, ge=-74.6, le=-73.6)
    tema: str | None = Field(None, max_length=160)
    descripcion: str | None = Field(None, max_length=4000)
    compromisos: str | None = Field(None, max_length=4000)

    @field_validator("fecha")
    @classmethod
    def _f(cls, v):
        if v is not None and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Use el formato AAAA-MM-DD")
        return v


def _reunion(db: Database, rid: int) -> dict:
    x = db.reuniones.find_one({"_id": rid})
    if x is None:
        raise HTTPException(404, "No existe")
    d = {k: v for k, v in x.items() if k != "_id"}
    d["id"] = rid
    lg = db.lugares.find_one({"_id": x.get("lugar_id")}, {"nombre": 1}) if x.get("lugar_id") else None
    d["lugar_nombre"] = (lg or {}).get("nombre")
    lugares = mapa_lugares(db)
    etiquetas = {e["_id"]: e for e in db.etiquetas.find()}
    asist, necesidades = [], Counter()
    for p in db.personas.find({**bd.ACTIVA, "asistencias.reunion_id": rid},
                              {"nombre": 1, "cedula": 1, "telefono": 1, "lugar_id": 1, "lugar_texto": 1, "completitud": 1,
                               "asistencias": 1, "etiquetas": 1}):
        a = next(a for a in p["asistencias"] if a["reunion_id"] == rid)
        ets = [etiquetas[e] for e in p.get("etiquetas", []) if e in etiquetas]
        necesidades.update(e["nombre"] for e in ets if e["grupo"] == "necesidad")
        asist.append({"id": p["_id"], "nombre": p["nombre"], "cedula": p.get("cedula"), "telefono": p.get("telefono"),
                      "lugar": (lugares.get(p.get("lugar_id")) or {}).get("nombre") or p.get("lugar_texto"),
                      "completitud": p.get("completitud", 0), "rol": a.get("rol"), "nota": a.get("nota"),
                      "creado_en": a.get("creado_en"), "etiquetas": [e["nombre"] for e in ets]})
    d["asistentes"] = sorted(asist, key=lambda a: a["creado_en"] or "", reverse=True)
    d["necesidades"] = [{"nombre": n, "n": c} for n, c in necesidades.most_common()]
    return d


@r.get("")
def listar(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    conteo = Counter()
    nuevos = Counter()
    for p in db.personas.find({**bd.ACTIVA, "asistencias.0": {"$exists": True}}, {"asistencias.reunion_id": 1, "fuentes": 1}):
        for a in p["asistencias"]:
            conteo[a["reunion_id"]] += 1
            if "reunion" in p.get("fuentes", []):
                nuevos[a["reunion_id"]] += 1
    lugares = mapa_lugares(db)
    return [{"id": x["_id"], "titulo": x["titulo"], "fecha": x["fecha"], "hora": x.get("hora"), "tema": x.get("tema"),
             "lugar": (lugares.get(x.get("lugar_id")) or {}).get("nombre") or x.get("lugar_texto"), "lat": x.get("lat"),
             "lon": x.get("lon"), "asistentes": conteo[x["_id"]], "nuevos": nuevos[x["_id"]]}
            for x in db.reuniones.find().sort([("fecha", -1), ("_id", -1)])]


def _ubicar_desde_lugar(db: Database, datos: dict) -> None:
    if datos.get("lugar_id") and datos.get("lat") is None:
        lg = db.lugares.find_one({"_id": datos["lugar_id"]})
        if lg is None:
            raise HTTPException(422, "Lugar no existe")
        datos["lat"], datos["lon"] = lg.get("lat"), lg.get("lon")
        datos.setdefault("lugar_texto", lg["nombre"])


@r.post("", status_code=201)
def crear(body: ReunionIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not body.titulo or not body.fecha:
        raise HTTPException(422, "La reunión necesita título y fecha")
    datos = {k: None for k in ReunionIn.model_fields} | body.model_dump(exclude_none=True)
    _ubicar_desde_lugar(db, datos)
    rid = bd.siguiente_id(db, "reuniones")
    db.reuniones.insert_one({"_id": rid, **datos, "creado_por": adm.usuario, "creado_en": bd.ahora(), "actualizado_en": bd.ahora()})
    bd.auditar(db, adm.usuario, "crear", "reunion", rid, datos, adm.ip)
    return _reunion(db, rid)


@r.get("/{rid}")
def ver(rid: int, db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    return _reunion(db, rid)


@r.patch("/{rid}")
def editar(rid: int, body: ReunionIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    _reunion(db, rid)
    datos = body.model_dump(exclude_unset=True)
    if "lugar_id" in datos and "lat" not in datos:
        datos["lat"] = None
        _ubicar_desde_lugar(db, datos)
    if datos:
        db.reuniones.update_one({"_id": rid}, {"$set": {**datos, "actualizado_en": bd.ahora()}})
        bd.auditar(db, adm.usuario, "editar", "reunion", rid, datos, adm.ip)
    return _reunion(db, rid)


@r.delete("/{rid}")
def borrar(rid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    _reunion(db, rid)
    db.reuniones.delete_one({"_id": rid})
    db.personas.update_many({"asistencias.reunion_id": rid}, {"$pull": {"asistencias": {"reunion_id": rid}}})
    db.personas.update_many({"notas.reunion_id": rid}, {"$set": {"notas.$[n].reunion_id": None}},
                            array_filters=[{"n.reunion_id": rid}])
    bd.auditar(db, adm.usuario, "borrar", "reunion", rid, None, adm.ip)
    return {"ok": True}


class AsistenteIn(BaseModel):
    persona_id: int
    rol: str | None = Field(None, max_length=60)
    nota: str | None = Field(None, max_length=1000)


@r.post("/{rid}/asistentes", status_code=201)
def agregar(rid: int, body: AsistenteIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    reu = db.reuniones.find_one({"_id": rid}, {"fecha": 1})
    if reu is None:
        raise HTTPException(404, "Reunión no existe")
    p = db.personas.find_one({"_id": body.persona_id, **bd.ACTIVA}, {"asistencias": 1})
    if p is None:
        raise HTTPException(404, "Persona no existe")
    if any(a["reunion_id"] == rid for a in p.get("asistencias", [])):
        cambios = {f"asistencias.$[a].{k}": v for k, v in (("rol", body.rol), ("nota", body.nota)) if v}
        if cambios:
            db.personas.update_one({"_id": body.persona_id}, {"$set": cambios}, array_filters=[{"a.reunion_id": rid}])
    else:
        db.personas.update_one({"_id": body.persona_id}, {
            "$push": {"asistencias": {"reunion_id": rid, "rol": body.rol, "nota": body.nota, "creado_en": bd.ahora()}},
            "$max": {"ultimo_contacto": reu["fecha"]}, "$set": {"actualizado_en": bd.ahora()}})
    bd.auditar(db, adm.usuario, "asistencia", "persona", body.persona_id, {"reunion_id": rid}, adm.ip)
    return _reunion(db, rid)


@r.delete("/{rid}/asistentes/{pid}")
def quitar(rid: int, pid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    db.personas.update_one({"_id": pid}, {"$pull": {"asistencias": {"reunion_id": rid}}})
    bd.auditar(db, adm.usuario, "quitar_asistencia", "persona", pid, {"reunion_id": rid}, adm.ip)
    return _reunion(db, rid)


@r.get("/{rid}/asistentes.csv")
def exportar(rid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    from .sistema import celda
    d = _reunion(db, rid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Nombre", "Cédula", "Teléfono", "Barrio/Vereda", "Rol", "Nota", "Necesidades"])
    for a in d["asistentes"]:
        w.writerow([celda(v) for v in (a["nombre"], a["cedula"] or "", a["telefono"] or "", a["lugar"] or "", a["rol"] or "",
                                        a["nota"] or "", ", ".join(a["etiquetas"]))])
    bd.auditar(db, adm.usuario, "exportar_asistentes", "reunion", rid, {"filas": len(d["asistentes"])}, adm.ip)
    nombre = re.sub(r"[^A-Za-z0-9]+", "-", d["titulo"])[:40]
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="asistentes-{d["fecha"]}-{nombre}.csv"'})
