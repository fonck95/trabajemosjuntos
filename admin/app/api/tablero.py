"""Indicadores del tablero y de una zona (5.2) y datos del mapa 3D (solo A y K).

`GET /api/indicadores` acepta los filtros comunes (incluidos `poligono` y `area_id`) y `alcance=tablero|zona`. El
cálculo es de una sola pasada (`resumir`), igual para ambos alcances; los denominadores de cobertura usan VIGENTE y las
fichas de fallecidos o de quienes ya no viven en Yondó se informan aparte. Una zona con menos de 10 personas no da
desgloses; una celda sensible con menos de 5 sale como «<5».
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pymongo.database import Database

from .. import geometria, modelo
from ..acceso import Quien, requiere
from ..db import ACTIVA, cerrar_coincidencias_imposibles
from ..seguridad import obtener_db
from .filtros import Filtros, filtro, filtros_query

r = APIRouter(prefix="/api", tags=["tablero"])
GEO = Path(__file__).resolve().parents[2] / "geo"
MINIMO_ZONA, MINIMO_SENSIBLE = 10, 5
DEMOGRAFIA = ("estado_civil", "nivel_educativo", "situacion_laboral", "estrato", "tenencia_vivienda", "regimen_salud")
CAMPOS = {k: 1 for k in (
    "cedula", "cedula_verificada", "tipo_documento", "telefono", "telefono2", "telefonos", "correo", "lat", "lon", "punto",
    "geo_precision", "fuentes", "lider", "consentimiento", "contacto_habilitado", "completitud", "zona", "lugar_id",
    "edad", "edad_ref", "fecha_nacimiento", "nac_aprox", "creado_en", "sexo", "etiquetas", "listas", "direccion",
    "ocupacion", "personas_hogar", "jefe_hogar", "votacion", "puesto_votacion", "mesa", "abordaje", "situacion",
    "asistencias.reunion_id", "tramites.ficha", "tramites.fecha", "tramites.tipo", *DEMOGRAFIA)}


def _rango_comp(c: int) -> str:
    return "0-24" if c < 25 else "25-49" if c < 50 else "50-74" if c < 75 else "75-100"


def resumir(personas: Iterable[dict], ajustes: dict, hoy=None, sensibles: bool = False, mesas: bool = False) -> dict:
    """Una sola pasada sobre las fichas: conteos, coberturas y desgloses (5.2)."""
    hoy = hoy or modelo.hoy_local()
    vigente_eleccion = ajustes.get("eleccion_vigente")
    k = Counter()
    zonas, precision, lugares_n, sin_ced_lugar, necesidades, listas, completitud = (Counter() for _ in range(7))
    edades, rangos, sexo, abordaje, autorizacion, fuentes = (Counter() for _ in range(6))
    puestos, puestos_mesa, mesas_n, campos_con = Counter(), Counter(), Counter(), Counter()
    demografia = {c: Counter() for c in DEMOGRAFIA}
    sens = {c: Counter() for c in modelo.SENSIBLES}
    fichas, meses, tipos = set(), Counter(), Counter()
    suma_comp = 0
    for p in personas:
        sit = (p.get("situacion") or {}).get("estado") if isinstance(p.get("situacion"), dict) else None
        if sit in ("fallecida", "no_reside"):
            k["no_vigentes"] += 1
            continue
        k["personas"] += 1
        k["con_cedula"] += bool(p.get("cedula"))
        k["sin_cedula"] += not p.get("cedula")
        k["cedulas_verificadas"] += bool(p.get("cedula")) and p.get("cedula_verificada") is True
        k["con_telefono"] += bool(p.get("telefono"))
        k["con_telefono_usable"] += bool(p.get("telefono"))
        k["con_varios_telefonos"] += bool(p.get("telefono2"))
        k["con_correo"] += bool(p.get("correo"))
        k["ubicadas"] += p.get("lat") is not None
        k["ubicadas_exactas"] += p.get("geo_precision") in ("direccion", "manual")
        f = p.get("fuentes") or []
        fuentes.update(f)
        k["en_ambas_bases"] += "tramites" in f and "cedulas" in f
        k["nuevas_en_reuniones"] += "reunion" in f
        k["lideres"] += bool(p.get("lider"))
        k["consentimiento_si"] += p.get("consentimiento") == "si"
        if p.get("consentimiento") == "si" and p.get("contacto_habilitado") is False and "contacto_habilitado" in p:
            autorizacion["por_confirmar"] += 1
        autorizacion[p.get("consentimiento") or "pendiente"] += 1
        k["alcanzadas"] += bool(p.get("asistencias"))
        k["asistencias"] += len(p.get("asistencias") or [])
        suma_comp += p.get("completitud", 0)
        completitud[_rango_comp(p.get("completitud", 0))] += 1
        zonas[p.get("zona") or "sin"] += 1
        precision[p.get("geo_precision") or "sin"] += 1
        if p.get("lugar_id"):
            lugares_n[p["lugar_id"]] += 1
            sin_ced_lugar[p["lugar_id"]] += not p.get("cedula")
        # Edad y sexo: quien no tiene sexo entra como «sin»
        sx = p.get("sexo") if p.get("sexo") in modelo.SEXOS else "sin"
        sexo[sx] += 1
        k["con_sexo"] += sx != "sin"
        rango = modelo.rango_edad(modelo.edad_efectiva(p, hoy))
        if rango:
            rangos[rango] += 1
            edades[(rango, sx)] += 1
            k["con_edad"] += 1
        else:
            k["sin_edad"] += 1
        k["menores"] += modelo.es_menor(p, hoy)
        # Votación
        v = p.get("votacion") if isinstance(p.get("votacion"), dict) else None
        k["con_puesto"] += modelo.tiene_dato(p, "puesto")
        k["con_mesa"] += modelo.tiene_dato(p, "mesa")
        if v:
            est = modelo.estado_votacion_efectivo(v, vigente_eleccion)
            k["votacion_verificada"] += est == "verificado"
            k["votacion_por_confirmar"] += est == "por_confirmar"
            k["otro_municipio"] += v.get("donde") == "otro_municipio"
            k["no_inscritos"] += v.get("donde") == "no_inscrito"
            if v.get("puesto_id") is not None:
                puestos[v["puesto_id"]] += 1
                if v.get("mesa") is not None:
                    puestos_mesa[v["puesto_id"]] += 1
                    if mesas:
                        mesas_n[(v["puesto_id"], v["mesa"])] += 1
            elif v.get("puesto_texto"):
                k["puesto_sin_catalogo"] += 1
            elif v.get("donde") not in ("otro_municipio", "no_inscrito"):
                k["sin_puesto"] += 1
        elif p.get("puesto_votacion"):
            k["puesto_sin_catalogo"] += 1
        else:
            k["sin_puesto"] += 1
        # Abordaje
        ab = p.get("abordaje") if isinstance(p.get("abordaje"), dict) else {}
        abordaje[ab.get("estado") or "sin_abordar"] += 1
        k["abordadas"] += (ab.get("n") or 0) >= 1
        k["contactadas"] += (ab.get("efectivos") or 0) >= 1
        for c in modelo.CAMPOS_AVANCE:
            campos_con[c] += modelo.tiene_dato(p, c)
        for c in DEMOGRAFIA:
            if p.get(c) not in (None, ""):
                demografia[c][str(p[c])] += 1
        if sensibles:
            for c, x in (p.get("sensibles") or {}).items():
                if c in sens and x not in (None, ""):
                    sens[c][x] += 1
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
    k["completitud_media"] = round(suma_comp / k["personas"]) if k["personas"] else 0
    return {"k": k, "zonas": zonas, "precision": precision, "lugares_n": lugares_n, "sin_ced_lugar": sin_ced_lugar,
            "necesidades": necesidades, "listas": listas, "completitud": completitud, "edades": edades,
            "rangos": rangos, "sexo": sexo, "abordaje": abordaje, "autorizacion": autorizacion, "fuentes": fuentes,
            "puestos": puestos, "puestos_mesa": puestos_mesa, "mesas": mesas_n, "campos_con": campos_con,
            "demografia": demografia, "sensibles": sens, "meses": meses, "tipos": tipos}


def _celda(n: int) -> Any:
    return "<5" if 0 < n < MINIMO_SENSIBLE else n


def _geometria(db: Database, f: Filtros) -> dict | None:
    """Área y perímetro de la zona pedida (polígono o área guardada)."""
    anillo = None
    if f.poligono:
        anillo = geometria.validar_anillo(geometria.decodificar(f.poligono))
    elif f.area_id is not None:
        a = db.areas.find_one({"_id": f.area_id}, {"poligono": 1, "area_m2": 1, "perimetro_m": 1}) or {}
        if a.get("area_m2") is not None:
            return {"m2": a.get("area_m2"), "perimetro_m": a.get("perimetro_m")}
        pol = a.get("poligono")
        if isinstance(pol, dict) and pol.get("type") == "Polygon":
            anillo = pol["coordinates"][0][:-1]
        elif isinstance(pol, list):
            anillo = pol
    if not anillo:
        return None
    return {"m2": round(geometria.area_m2(anillo)), "perimetro_m": round(geometria.perimetro_m(anillo))}


@r.get("/indicadores")
def indicadores(f: Filtros = Depends(filtros_query), alcance: Literal["tablero", "zona"] = "tablero",
                detalle: str | None = None, db: Database = Depends(obtener_db),
                quien: Quien = Depends(requiere("tablero.ver"))):
    aj = modelo.leer_ajustes(db)
    hoy = modelo.hoy_local()
    zona = alcance == "zona"
    sensibles = bool(aj.get("sensibles_activos"))
    campos = {**CAMPOS, **({"sensibles": 1} if sensibles else {})}
    q = filtro(f, hoy)
    s = resumir(db.personas.find(q, campos), aj, hoy, sensibles, mesas=zona or detalle == "mesas")
    k = s["k"]
    geo = f.poligono or f.area_id is not None
    out: dict = {}
    if geo:
        out["area"] = _geometria(db, f)
        sin_geo = f.model_copy(update={"poligono": None, "area_id": None})
        sin_geo._eleccion, sin_geo._dias_dato = f._eleccion, f._dias_dato
        out["sin_ubicacion"] = db.personas.count_documents({"$and": [filtro(sin_geo, hoy), {"punto": None}]})
    if zona and k["personas"] < MINIMO_ZONA:
        return {**out, "pocas": True, "kpi": {"personas": "<10"}, "zonas": {}, "precision": {}, "lugares": [],
                "edades": [], "sexo": {}, "rangos_edad": {}, "puestos": [], "demografia": {}, "abordaje": {},
                "autorizacion": {}, "completitud_campos": [], "cobertura_cedula": []}
    k["reuniones"] = db.reuniones.count_documents({})
    cerrar_coincidencias_imposibles(db)  # las que ya no se pueden aceptar no cuentan como pendientes
    k["pendientes_revision"] = len(db.coincidencias.distinct("persona_id", {"estado": "pendiente"}))
    sin_punto = {l["_id"] for l in db.lugares.find({"lat": None}, {"_id": 1})}
    k["lugares_sin_punto"] = sum(1 for lid in s["lugares_n"] if lid in sin_punto)
    lugares_n, sin_ced = s["lugares_n"], s["sin_ced_lugar"]
    top_sin = [i for i, n in sin_ced.most_common(15) if n]
    lg = {l["_id"]: l for l in db.lugares.find({"_id": {"$in": [i for i, _ in lugares_n.most_common(15)] + top_sin}},
                                               {"nombre": 1, "tipo": 1, "zona": 1})}
    et = {e["_id"]: e for e in db.etiquetas.find()}
    cat = {x["_id"]: x for x in db.puestos.find({"_id": {"$in": list(s["puestos"])}}, {"codigo": 1, "nombre": 1, "mesas": 1})}
    out.update({
        "kpi": dict(k),
        "zonas": dict(s["zonas"]), "precision": dict(s["precision"]),
        "lugares": [{"id": i, "nombre": lg[i]["nombre"], "tipo": lg[i]["tipo"], "zona": lg[i]["zona"], "n": n}
                    for i, n in lugares_n.most_common(15) if i in lg],
        "tramites_tipo": [{"tipo": t, "n": n} for t, n in s["tipos"].most_common()],
        "edades": [{"rango": r_, "sexo": sx, "n": n} for (r_, sx), n in
                   sorted(s["edades"].items(), key=lambda x: (modelo.RANGOS_EDAD.index(x[0][0]), x[0][1]))],
        "rangos_edad": {r_: s["rangos"].get(r_, 0) for r_ in modelo.RANGOS_EDAD},
        "sexo": {x: s["sexo"].get(x, 0) for x in (*modelo.SEXOS, "sin")},
        "sin_edad": k.get("sin_edad", 0),
        "necesidades": [{"id": i, "nombre": et[i]["nombre"], "grupo": et[i]["grupo"], "n": n}
                        for i, n in s["necesidades"].most_common(12) if i in et],
        "listas": [{"lista": l, "n": n} for l, n in s["listas"].most_common()],
        "completitud": [{"rango": r_, "n": s["completitud"][r_]} for r_ in ("0-24", "25-49", "50-74", "75-100")],
        "puestos": [{"id": i, "codigo": (cat.get(i) or {}).get("codigo"), "nombre": (cat.get(i) or {}).get("nombre"),
                     "n": n, "con_mesa": s["puestos_mesa"].get(i, 0), "mesas": (cat.get(i) or {}).get("mesas")}
                    for i, n in s["puestos"].most_common()],
        "puesto_sin_catalogo": k.get("puesto_sin_catalogo", 0), "sin_puesto": k.get("sin_puesto", 0),
        "cobertura_cedula": [{"id": i, "nombre": lg[i]["nombre"], "personas": lugares_n[i], "sin_cedula": sin_ced[i],
                              "con_cedula_pct": round(100 * (lugares_n[i] - sin_ced[i]) / lugares_n[i])}
                             for i in top_sin if i in lg],
        "completitud_campos": [{"campo": c, "etiqueta": modelo.ETIQUETAS_CAMPOS.get(c, c), "con": s["campos_con"][c]}
                               for c in modelo.CAMPOS_AVANCE],
        "abordaje": {e: s["abordaje"].get(e, 0) for e in modelo.ESTADOS_ABORDAJE},
        "autorizacion": {e: s["autorizacion"].get(e, 0) for e in ("si", "pendiente", "no", "por_confirmar")},
        "fuentes": dict(s["fuentes"]),
        "demografia": {c: dict(s["demografia"][c]) for c in DEMOGRAFIA},
    })
    if zona or detalle == "mesas":
        out["mesas"] = [{"puesto_id": pi, "mesa": m, "n": n} for (pi, m), n in sorted(s["mesas"].items())]
    if sensibles:
        out["sensibles"] = {c: {x: _celda(n) for x, n in s["sensibles"][c].items()} for c in modelo.SENSIBLES}
    if not zona:
        reus = list(db.reuniones.find({}, {"titulo": 1, "fecha": 1}).sort([("fecha", -1), ("_id", -1)]).limit(6))
        asist = Counter()
        if reus:
            # Con `tratables` (el asistente), sin quien no autorizó: que asistió es un dato suyo (como en Reuniones)
            tratable = {"consentimiento": {"$ne": "no"}} if f.tratables else {}
            de_estas = {"asistencias.reunion_id": {"$in": [x["_id"] for x in reus]}}
            for p in db.personas.find({**ACTIVA, **tratable, **de_estas}, {"asistencias.reunion_id": 1}):
                asist.update(a["reunion_id"] for a in p["asistencias"])
        out["tramites_mes"] = [{"mes": m, "n": n} for m, n in sorted(s["meses"].items())]
        out["reuniones"] = [{"id": x["_id"], "titulo": x["titulo"], "fecha": x["fecha"], "n": asist[x["_id"]]} for x in reus]
        out["actividad"] = [{k_: a.get(k_) for k_ in ("ts", "usuario", "accion", "entidad", "entidad_id")}
                            for a in db.auditoria.find({"accion": {"$nin": ["ingreso", "salida", "ingreso_fallido"]}})
                            .sort("_id", -1).limit(8)]
    return out


PREC = {"direccion": 0, "manual": 0, "direccion_aprox": 1, "barrio": 2, "sector": 2, "caserio": 3, "centro_poblado": 3,
        "vereda": 4, "corregimiento": 5}


@r.get("/mapa/puntos")
def puntos(f: Filtros = Depends(filtros_query), db: Database = Depends(obtener_db),
           _: Quien = Depends(requiere("mapa.ver"))):
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
def capas(db: Database = Depends(obtener_db), _: Quien = Depends(requiere("mapa.ver"))):
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
def grilla(_: Quien = Depends(requiere("mapa.ver"))):
    ruta = GEO / "grilla_casco.json"
    return Response(ruta.read_bytes() if ruta.exists() else b"{}", media_type="application/json")
