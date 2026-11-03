"""MongoDB: conexión, índices, nomenclátor inicial y operaciones comunes sobre personas.

Colecciones (todas con `_id` entero para que las direcciones del panel sean cortas, salvo sesiones y auditoría):

* `personas`: una por habitante. Lleva adentro sus trámites, notas, listas, etiquetas, asistencias y el registro
  original de cada fuente, así una ficha se lee de una sola vez.
* `lugares`, `reuniones`, `coincidencias`, `etiquetas`, `campos`, `importaciones`.
* `sesiones` e `intentos` (con caducidad automática), `auditoria`, `contadores`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from pymongo.database import Database

from .pipeline import texto as tx
from .pipeline.direcciones import Lugar

GAZETTEER = Path(__file__).resolve().parents[1] / "geo" / "gazetteer.json"
ACTIVA = {"eliminado": {"$ne": True}, "fusionada_en": None}

ETIQUETAS_INICIALES = [
    ("Vivienda", "necesidad"), ("Agua potable", "necesidad"), ("Saneamiento", "necesidad"), ("Salud", "necesidad"),
    ("Empleo", "necesidad"), ("Educación", "necesidad"), ("Vías", "necesidad"), ("Energía", "necesidad"),
    ("Conectividad", "necesidad"), ("Seguridad", "necesidad"), ("Adulto mayor", "necesidad"),
    ("Discapacidad", "necesidad"), ("Primera infancia", "necesidad"), ("Proyecto productivo", "necesidad"),
    ("Víctima del conflicto", "interes"), ("Campesino", "interes"), ("Pescador", "interes"), ("Joven", "interes"),
    ("Mujer cabeza de hogar", "interes"), ("Líder comunitario", "rol"), ("JAC", "rol"), ("Voluntario", "rol"),
]

# Campos de la ficha con su valor inicial: así toda persona tiene la misma forma
PERSONA_VACIA: dict[str, Any] = {
    "nombre": None, "nombre_norm": None, "cedula": None, "sexo": None, "edad": None, "fecha_nacimiento": None,
    "telefono": None, "telefono2": None, "correo": None, "direccion": None, "direccion_norm": None, "lugar_id": None,
    "lugar_texto": None, "zona": None, "lat": None, "lon": None, "geo_precision": None, "geo_manual": False,
    "ficha": None, "puesto_votacion": None, "mesa": None, "ocupacion": None, "nivel_educativo": None,
    "personas_hogar": None, "lider": False, "consentimiento": "pendiente", "consentimiento_fecha": None,
    "observaciones": None, "extra": {}, "fuentes": [], "clave_tramites": None, "completitud": 0, "ultimo_contacto": None,
    "fusionada_en": None, "eliminado": False, "listas": [], "etiquetas": [], "tramites": [], "notas": [], "origen": [],
    "asistencias": [],
}


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def conectar(uri: str, nombre: str | None = None) -> tuple[MongoClient, Database]:
    cliente = MongoClient(uri, serverSelectionTimeoutMS=8000, tz_aware=True, appname="panel-yondo")
    try:
        db = cliente.get_default_database()
    except Exception:  # la URI no trae base de datos (Railway)
        db = None
    if nombre or db is None:
        db = cliente[nombre or "panel_yondo"]
    return cliente, db


def siguiente_id(db: Database, coleccion: str, cuantos: int = 1) -> int:
    """Reserva `cuantos` identificadores consecutivos y devuelve el primero."""
    c = db.contadores.find_one_and_update({"_id": coleccion}, {"$inc": {"n": cuantos}}, upsert=True,
                                          return_document=ReturnDocument.AFTER)
    return c["n"] - cuantos + 1


def inicializar(db: Database) -> None:
    p = db.personas
    p.create_index("nombre_norm")
    p.create_index("cedula", unique=True, partialFilterExpression={"cedula": {"$type": "string"}})
    p.create_index("clave_tramites", unique=True, partialFilterExpression={"clave_tramites": {"$type": "string"}})
    for campo in ("telefono", "lugar_id", "asistencias.reunion_id", "tramites.id_externo", "etiquetas", "listas",
                  "fuentes", "completitud"):
        p.create_index(campo)
    p.create_index([("eliminado", ASCENDING), ("fusionada_en", ASCENDING)])
    db.lugares.create_index([("nombre", ASCENDING), ("tipo", ASCENDING)], unique=True)
    db.coincidencias.create_index([("persona_id", ASCENDING), ("candidato_id", ASCENDING)], unique=True)
    db.coincidencias.create_index("estado")
    db.reuniones.create_index([("fecha", DESCENDING)])
    db.etiquetas.create_index("nombre", unique=True)
    db.campos.create_index("clave", unique=True)
    db.auditoria.create_index([("entidad", ASCENDING), ("entidad_id", ASCENDING)])
    db.sesiones.create_index("expira", expireAfterSeconds=0)
    db.intentos.create_index("ts", expireAfterSeconds=24 * 3600)
    db.intentos.create_index([("ip", ASCENDING), ("ts", ASCENDING)])
    if db.etiquetas.estimated_document_count() == 0:
        primero = siguiente_id(db, "etiquetas", len(ETIQUETAS_INICIALES))
        db.etiquetas.insert_many([{"_id": primero + i, "nombre": n, "grupo": g, "orden": i}
                                  for i, (n, g) in enumerate(ETIQUETAS_INICIALES)])
    sembrar_lugares(db)


def sembrar_lugares(db: Database, ruta: Path = GAZETTEER) -> int:
    """Carga el nomenclátor público (geo/gazetteer.json). No pisa los lugares editados a mano.

    En las veredas se prefiere el `nucleo` (caserío, escuela o centro poblado) al centroide del polígono: ahí vive
    la gente."""
    if not ruta.exists():
        return 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nuevos = 0
    for lg in datos.get("lugares", []):
        nombre = tx.limpiar(lg["nombre"])
        punto = lg.get("nucleo") or {}
        lat = punto.get("lat", lg.get("lat"))
        lon = punto.get("lon", lg.get("lon"))
        alias = sorted({tx.limpiar(a) for a in [*lg.get("alias", []), *lg.get("alias_ambiguos", [])]} - {nombre})
        campos = {
            "zona": lg.get("zona") or ("urbana" if lg["tipo"] == "barrio" else "rural"), "lat": lat, "lon": lon,
            "alias": alias, "padre": tx.limpiar(lg.get("padre")) or None, "fuente": lg.get("fuente"),
            "precision": "nucleo" if punto else lg.get("precision"), "geom": lg.get("geom"),
            "codigo_dane": lg.get("codigo_dane"), "nota": lg.get("nota"),
        }
        actual = db.lugares.find_one({"nombre": nombre, "tipo": lg["tipo"]}, {"editado": 1})
        if actual is None:
            db.lugares.insert_one({"_id": siguiente_id(db, "lugares"), "nombre": nombre, "tipo": lg["tipo"],
                                   "editado": False, "creado_en": ahora(), **campos})
            nuevos += 1
        elif not actual.get("editado"):
            db.lugares.update_one({"_id": actual["_id"]}, {"$set": campos})
    return nuevos


def lugares(db: Database) -> list[Lugar]:
    return [Lugar(l["_id"], l["nombre"], l["tipo"], l["zona"], l.get("lat"), l.get("lon"), tuple(l.get("alias") or ()),
                  l.get("padre")) for l in db.lugares.find({}, {"geom": 0})]


def auditar(db: Database, usuario: str | None, accion: str, entidad: str | None = None,
            entidad_id: int | None = None, detalle: Any = None, ip: str | None = None) -> None:
    db.auditoria.insert_one({
        "ts": ahora(), "usuario": usuario, "accion": accion, "entidad": entidad, "entidad_id": entidad_id,
        "detalle": json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None, "ip": ip,
    })


# ───────────────────────────── Completitud del perfil ─────────────────────────────

PESOS = [  # (campo, puntos) — suma 100
    ("cedula", 15), ("telefono", 15), ("direccion", 8), ("ubicacion", 15), ("sexo", 5), ("edad", 5), ("correo", 5),
    ("ocupacion", 6), ("nivel_educativo", 5), ("personas_hogar", 5), ("necesidades", 10), ("consentimiento", 6),
]


def completitud(p: dict) -> int:
    pts = 0
    for campo, peso in PESOS:
        if campo == "ubicacion":
            prec = p.get("geo_precision")
            pts += peso if prec in ("direccion", "manual") else (peso // 2 if prec else 0)
        elif campo == "edad":
            pts += peso if (p.get("edad") or p.get("fecha_nacimiento")) else 0
        elif campo == "necesidades":
            pts += peso if p.get("etiquetas") else 0
        elif campo == "consentimiento":
            pts += peso if p.get("consentimiento") == "si" else 0
        else:
            pts += peso if p.get(campo) not in (None, "", 0) else 0
    return pts


def recalcular_completitud(db: Database, ids: Iterable[int] | None = None) -> None:
    filtro = dict(ACTIVA) if ids is None else {"_id": {"$in": list(ids)}}
    campos = {c: 1 for c, _ in PESOS if c not in ("ubicacion", "necesidades")}
    campos |= {"geo_precision": 1, "fecha_nacimiento": 1, "etiquetas": 1, "completitud": 1}
    ops = []
    for p in db.personas.find(filtro, campos):
        c = completitud(p)
        if c != p.get("completitud"):
            ops.append(UpdateOne({"_id": p["_id"]}, {"$set": {"completitud": c}}))
    if ops:
        db.personas.bulk_write(ops, ordered=False)


# ───────────────────────────── Personas ─────────────────────────────

def nueva_persona(db: Database, datos: dict, fuente: str) -> dict:
    doc = {**PERSONA_VACIA, "extra": {}, "fuentes": [fuente], "listas": [], "etiquetas": [], "tramites": [], "notas": [],
           "origen": [], "asistencias": [], **datos}
    if "_id" not in datos:
        doc["_id"] = siguiente_id(db, "personas")
    doc["nombre_norm"] = tx.nombre_norm(doc["nombre"])
    doc["creado_en"] = doc["actualizado_en"] = ahora()
    return doc


def completar_doc(doc: dict, datos: dict) -> list[str]:
    """Llena en el documento solo los campos vacíos. La importación nunca pisa lo editado en el panel."""
    cambios = []
    for k, v in datos.items():
        if v in (None, "") or doc.get(k) not in (None, ""):
            continue
        if k == "telefono" and v == doc.get("telefono2"):
            continue
        if k == "telefono2" and v == doc.get("telefono"):
            continue
        doc[k] = v
        cambios.append(k)
    return cambios


def fusionar(db: Database, destino: int, origen: int, usuario: str | None, ip: str | None = None) -> None:
    """Une `origen` en `destino`: completa vacíos y junta trámites, listas, etiquetas, reuniones, notas y fuentes."""
    if destino == origen:
        return
    d = db.personas.find_one({"_id": destino})
    o = db.personas.find_one({"_id": origen})
    if d is None or o is None:
        return
    # Libera primero las claves únicas del origen
    db.personas.update_one({"_id": origen}, {"$set": {"cedula": None, "clave_tramites": None}})
    if o.get("telefono") and d.get("telefono") and o["telefono"] != d["telefono"] and not d.get("telefono2"):
        d["telefono2"] = o["telefono"]
    escalares = [k for k in PERSONA_VACIA if not isinstance(PERSONA_VACIA[k], (list, dict, bool))
                 and k not in ("nombre", "nombre_norm", "fusionada_en", "completitud", "consentimiento")]
    completar_doc(d, {k: o.get(k) for k in escalares})
    if d.get("consentimiento") == "pendiente" and o.get("consentimiento") in ("si", "no"):
        d["consentimiento"], d["consentimiento_fecha"] = o["consentimiento"], o.get("consentimiento_fecha")
    d["lider"] = bool(d.get("lider") or o.get("lider"))
    d["extra"] = {**(o.get("extra") or {}), **(d.get("extra") or {})}
    for k in ("fuentes", "listas", "etiquetas"):
        d[k] = list(dict.fromkeys([*(d.get(k) or []), *(o.get(k) or [])]))
    ya = {t.get("id_externo") for t in d.get("tramites", [])}
    d["tramites"] = [*d.get("tramites", []), *[t for t in o.get("tramites", []) if t.get("id_externo") not in ya]]
    d["notas"] = [*d.get("notas", []), *o.get("notas", [])]
    d["origen"] = [*d.get("origen", []), *o.get("origen", [])]
    reus = {a["reunion_id"] for a in d.get("asistencias", [])}
    d["asistencias"] = [*d.get("asistencias", []), *[a for a in o.get("asistencias", []) if a["reunion_id"] not in reus]]
    d["ultimo_contacto"] = max(filter(None, [d.get("ultimo_contacto"), o.get("ultimo_contacto")]), default=None)
    d["actualizado_en"] = ahora()
    d["completitud"] = completitud(d)
    db.personas.replace_one({"_id": destino}, d)
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "actualizado_en": ahora()}})
    par = {"$or": [{"persona_id": origen, "candidato_id": destino}, {"persona_id": destino, "candidato_id": origen}]}
    db.coincidencias.update_many({**par, "estado": "pendiente"}, {"$set": {"estado": "aceptada"}})
    db.coincidencias.delete_many({"estado": "pendiente", "$or": [{"persona_id": origen}, {"candidato_id": origen}]})
    auditar(db, usuario, "fusionar", "persona", destino, {"origen": origen}, ip)
