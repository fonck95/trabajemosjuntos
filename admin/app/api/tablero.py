"""Indicadores del tablero y datos del mapa 3D."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pymongo.database import Database

from ..db import ACTIVA
from ..seguridad import Admin, obtener_db, requiere_admin
from .filtros import Filtros, filtro, filtros_query

r = APIRouter(prefix="/api", tags=["tablero"])
GEO = Path(__file__).resolve().parents[2] / "geo"


def _rango_edad(e: int) -> str:
    return "0-17" if e < 18 else "18-28" if e < 29 else "29-40" if e < 41 else "41-59" if e < 60 else "60+"


def _rango_comp(c: int) -> str:
    return "0-24" if c < 25 else "25-49" if c < 50 else "50-74" if c < 75 else "75-100"


@r.get("/indicadores")
def indicadores(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    # 7 a 20 mil personas: se resume en una sola pasada en Python, que es más simple y rápido que diez agregaciones
    campos = {"cedula": 1, "telefono": 1, "correo": 1, "lat": 1, "geo_precision": 1, "fuentes": 1, "lider": 1,
              "consentimiento": 1, "completitud": 1, "zona": 1, "lugar_id": 1, "edad": 1, "sexo": 1, "etiquetas": 1,
              "listas": 1, "asistencias.reunion_id": 1, "tramites.ficha": 1, "tramites.fecha": 1, "tramites.tipo": 1}
    k = Counter()
    zonas, precision, lugares_n, edades, necesidades, listas, completitud = (Counter() for _ in range(7))
    fichas, meses, tipos = set(), Counter(), Counter()
    suma_comp = 0
    for p in db.personas.find(ACTIVA, campos):
        k["personas"] += 1
        k["con_cedula"] += bool(p.get("cedula"))
        k["con_telefono"] += bool(p.get("telefono"))
        k["con_correo"] += bool(p.get("correo"))
        k["ubicadas"] += p.get("lat") is not None
        k["ubicadas_exactas"] += p.get("geo_precision") in ("direccion", "manual")
        f = p.get("fuentes") or []
        k["en_ambas_bases"] += "tramites" in f and "cedulas" in f
        k["nuevas_en_reuniones"] += "reunion" in f
        k["lideres"] += bool(p.get("lider"))
        k["consentimiento_si"] += p.get("consentimiento") == "si"
        k["alcanzadas"] += bool(p.get("asistencias"))
        k["asistencias"] += len(p.get("asistencias") or [])
        suma_comp += p.get("completitud", 0)
        completitud[_rango_comp(p.get("completitud", 0))] += 1
        zonas[p.get("zona") or "sin"] += 1
        precision[p.get("geo_precision") or "sin"] += 1
        if p.get("lugar_id"):
            lugares_n[p["lugar_id"]] += 1
        if p.get("edad") is not None:
            edades[(_rango_edad(p["edad"]), p.get("sexo"))] += 1
        necesidades.update(p.get("etiquetas") or [])
        listas.update(p.get("listas") or [])
        for t in p.get("tramites") or []:
            if t.get("ficha"):
                fichas.add(t["ficha"])
            if t.get("fecha"):
                meses[t["fecha"][:7]] += 1
            tipos[t.get("tipo") or ""] += 1
    k["hogares"] = len(fichas)
    k["tramites"] = sum(tipos.values())
    k["reuniones"] = db.reuniones.count_documents({})
    k["completitud_media"] = round(suma_comp / k["personas"]) if k["personas"] else 0
    k["pendientes_revision"] = len(db.coincidencias.distinct("persona_id", {"estado": "pendiente"}))
    sin_punto = {l["_id"] for l in db.lugares.find({"lat": None}, {"_id": 1})}
    k["lugares_sin_punto"] = sum(1 for lid in lugares_n if lid in sin_punto)

    lg = {l["_id"]: l for l in db.lugares.find({"_id": {"$in": [i for i, _ in lugares_n.most_common(15)]}}, {"nombre": 1, "tipo": 1, "zona": 1})}
    et = {e["_id"]: e for e in db.etiquetas.find()}
    reus = list(db.reuniones.find({}, {"titulo": 1, "fecha": 1}).sort([("fecha", -1), ("_id", -1)]).limit(6))
    asist = Counter()
    if reus:
        for p in db.personas.find({**ACTIVA, "asistencias.reunion_id": {"$in": [x["_id"] for x in reus]}}, {"asistencias.reunion_id": 1}):
            asist.update(a["reunion_id"] for a in p["asistencias"])
    return {
        "kpi": dict(k),
        "zonas": dict(zonas), "precision": dict(precision),
        "lugares": [{"id": i, "nombre": lg[i]["nombre"], "tipo": lg[i]["tipo"], "zona": lg[i]["zona"], "n": n}
                    for i, n in lugares_n.most_common(15) if i in lg],
        "tramites_mes": [{"mes": m, "n": n} for m, n in sorted(meses.items())],
        "tramites_tipo": [{"tipo": t, "n": n} for t, n in tipos.most_common()],
        "edades": [{"rango": r_, "sexo": s, "n": n} for (r_, s), n in sorted(edades.items(), key=lambda x: (x[0][0], x[0][1] or ""))],
        "necesidades": [{"id": i, "nombre": et[i]["nombre"], "grupo": et[i]["grupo"], "n": n} for i, n in necesidades.most_common(12) if i in et],
        "listas": [{"lista": l, "n": n} for l, n in listas.most_common()],
        "completitud": [{"rango": r_, "n": completitud[r_]} for r_ in ("0-24", "25-49", "50-74", "75-100")],
        "reuniones": [{"id": x["_id"], "titulo": x["titulo"], "fecha": x["fecha"], "n": asist[x["_id"]]} for x in reus],
        "actividad": [{k_: a.get(k_) for k_ in ("ts", "usuario", "accion", "entidad", "entidad_id")}
                      for a in db.auditoria.find({"accion": {"$nin": ["ingreso", "salida", "ingreso_fallido"]}}).sort("_id", -1).limit(8)],
    }


PREC = {"direccion": 0, "manual": 0, "direccion_aprox": 1, "barrio": 2, "sector": 2, "caserio": 3, "centro_poblado": 3,
        "vereda": 4, "corregimiento": 5}


@r.get("/mapa/puntos")
def puntos(f: Filtros = Depends(filtros_query), db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    """Puntos compactos para el mapa: [id, lat, lon, precisión, rural, lugar_id, reuniones, completitud]."""
    q = filtro(f)
    total = db.personas.count_documents(q)
    datos = [[p["_id"], p["lat"], p["lon"], PREC.get(p.get("geo_precision"), 5), 1 if p.get("zona") == "rural" else 0,
              p.get("lugar_id") or 0, len(p.get("asistencias") or []), p.get("completitud", 0)]
             for p in db.personas.find({"$and": [q, {"lat": {"$ne": None}}]},
                                       {"lat": 1, "lon": 1, "geo_precision": 1, "zona": 1, "lugar_id": 1, "completitud": 1,
                                        "asistencias.reunion_id": 1})]
    return {"total": total, "ubicadas": len(datos), "puntos": datos}


@r.get("/mapa/capas")
def capas(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    """Límite municipal, polígonos de veredas y puntos de lugares con su conteo de personas."""
    limite = GEO / "yondo_limite.geojson"
    conteo = Counter(p.get("lugar_id") for p in db.personas.find({**ACTIVA, "lugar_id": {"$ne": None}}, {"lugar_id": 1}))
    lugares, veredas = [], []
    for l in db.lugares.find():
        props = {"id": l["_id"], "nombre": l["nombre"], "tipo": l["tipo"], "zona": l["zona"], "n": conteo.get(l["_id"], 0),
                 "fuente": l.get("fuente"), "precision": l.get("precision")}
        if l.get("lat") is not None:
            lugares.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [l["lon"], l["lat"]]}, "properties": props})
        if l.get("geom") and l["tipo"] in ("vereda", "corregimiento"):
            veredas.append({"type": "Feature", "geometry": l["geom"], "properties": props})
    asist = Counter(a["reunion_id"] for p in db.personas.find({**ACTIVA, "asistencias.0": {"$exists": True}}, {"asistencias.reunion_id": 1})
                    for a in p["asistencias"])
    reuniones = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["lon"], x["lat"]]},
                  "properties": {"id": x["_id"], "titulo": x["titulo"], "fecha": x["fecha"], "n": asist[x["_id"]]}}
                 for x in db.reuniones.find({"lat": {"$ne": None}})]
    return {
        "limite": json.loads(limite.read_text(encoding="utf-8")) if limite.exists() else None,
        "veredas": {"type": "FeatureCollection", "features": veredas},
        "lugares": {"type": "FeatureCollection", "features": lugares},
        "reuniones": {"type": "FeatureCollection", "features": reuniones},
    }


@r.get("/mapa/grilla.json")
def grilla(_: Admin = Depends(requiere_admin)):
    ruta = GEO / "grilla_casco.json"
    return Response(ruta.read_bytes() if ruta.exists() else b"{}", media_type="application/json")
