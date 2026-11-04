"""Filtros comunes del directorio, el mapa y la exportación (mismos parámetros en las tres), traducidos a MongoDB."""
from __future__ import annotations

import re

from fastapi import Query
from pydantic import BaseModel

from ..db import ACTIVA
from ..pipeline import texto as tx

APROXIMADAS = ["barrio", "sector", "caserio", "centro_poblado", "vereda", "corregimiento", "direccion_aprox"]


class Filtros(BaseModel):
    q: str | None = None
    zona: str | None = None
    lugar_id: int | None = None
    fuente: str | None = None
    lista: str | None = None
    etiqueta: int | None = None
    con_cedula: int | None = None
    con_telefono: int | None = None
    precision: str | None = None
    reunion_id: int | None = None
    asistio: int | None = None
    consentimiento: str | None = None
    lider: int | None = None
    sexo: str | None = None
    completitud_max: int | None = None
    ids: str | None = None


def filtros_query(
    q: str | None = Query(None, max_length=120), zona: str | None = None, lugar_id: int | None = None,
    fuente: str | None = None, lista: str | None = Query(None, max_length=120), etiqueta: int | None = None,
    con_cedula: int | None = None, con_telefono: int | None = None, precision: str | None = None,
    reunion_id: int | None = None, asistio: int | None = None, consentimiento: str | None = None,
    lider: int | None = None, sexo: str | None = None, completitud_max: int | None = None,
    ids: str | None = Query(None, max_length=4000),
) -> Filtros:
    return Filtros(**{k: v for k, v in locals().items()})


def filtro(f: Filtros) -> dict:
    """Documento de consulta de MongoDB para los filtros dados (solo personas activas)."""
    y: list[dict] = [dict(ACTIVA)]
    if f.q:
        for tok in tx.limpiar(f.q).split()[:6]:
            digitos = re.sub(r"\D", "", tok)
            if digitos and len(digitos) >= 4 and digitos == tok:
                rx = re.escape(digitos)
                y.append({"$or": [{"cedula": {"$regex": "^" + rx}}, {"telefono": {"$regex": rx}},
                                  {"telefono2": {"$regex": rx}}, {"ficha": {"$regex": rx}}]})
            else:
                limpio = re.sub(r"[^A-Z0-9@.]", "", tok)
                if not limpio:
                    continue
                rx = re.escape(limpio)
                y.append({"$or": [{"nombre_norm": {"$regex": rx}}, {"direccion_norm": {"$regex": rx}},
                                  {"lugar_texto": {"$regex": rx}}, {"correo": {"$regex": rx, "$options": "i"}}]})
    if f.zona in ("urbana", "rural"):
        y.append({"zona": f.zona})
    elif f.zona == "sin":
        y.append({"zona": None})
    if f.lugar_id is not None:  # 0 = sin barrio ni vereda reconocidos
        y.append({"lugar_id": f.lugar_id or None})
    if f.fuente == "ambas":
        y.append({"fuentes": {"$all": ["tramites", "cedulas"]}})
    elif f.fuente in ("tramites", "cedulas", "reunion", "manual"):
        y.append({"fuentes": f.fuente})
    if f.lista:
        y.append({"listas": f.lista})
    if f.etiqueta:
        y.append({"etiquetas": f.etiqueta})
    if f.con_cedula is not None:
        y.append({"cedula": {"$ne": None}} if f.con_cedula else {"cedula": None})
    if f.con_telefono is not None:
        y.append({"telefono": {"$ne": None}} if f.con_telefono else {"telefono": None})
    if f.precision == "exacta":
        y.append({"geo_precision": {"$in": ["direccion", "manual"]}})
    elif f.precision == "aproximada":
        y.append({"geo_precision": {"$in": APROXIMADAS}})
    elif f.precision == "sin":
        y.append({"lat": None})
    if f.reunion_id:
        y.append({"asistencias.reunion_id": f.reunion_id})
    if f.asistio is not None:
        y.append({"asistencias.0": {"$exists": bool(f.asistio)}})
    if f.consentimiento in ("si", "no", "pendiente"):
        y.append({"consentimiento": f.consentimiento})
    if f.lider:
        y.append({"lider": True})
    if f.sexo in ("F", "M"):
        y.append({"sexo": f.sexo})
    if f.ids:
        y.append({"_id": {"$in": [int(x) for x in re.findall(r"\d+", f.ids)[:500]]}})
    if f.completitud_max is not None:
        y.append({"completitud": {"$lte": f.completitud_max}})
    return {"$and": y}
