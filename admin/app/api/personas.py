"""Directorio de habitantes: búsqueda, ficha, edición, notas, ubicación manual, fusión y supresión."""
from __future__ import annotations

import re
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from rapidfuzz import fuzz

from .. import db as bd
from ..pipeline import texto as tx
from ..pipeline.importar import georreferenciar
from ..seguridad import Admin, obtener_db, requiere_admin
from .filtros import Filtros, filtro, filtros_query

r = APIRouter(prefix="/api", tags=["personas"])

ORDENES = {
    "nombre": [("nombre_norm", ASCENDING)], "completitud": [("completitud", DESCENDING), ("nombre_norm", ASCENDING)],
    "-completitud": [("completitud", ASCENDING), ("nombre_norm", ASCENDING)], "reciente": [("actualizado_en", DESCENDING)],
    "contacto": [("ultimo_contacto", DESCENDING), ("nombre_norm", ASCENDING)],
}
EDITABLES = {"nombre", "cedula", "sexo", "edad", "fecha_nacimiento", "telefono", "telefono2", "correo", "direccion",
             "ocupacion", "nivel_educativo", "personas_hogar", "lider", "consentimiento", "consentimiento_fecha",
             "observaciones", "puesto_votacion", "mesa"}
LISTA_CAMPOS = {"nombre": 1, "cedula": 1, "telefono": 1, "lugar_id": 1, "lugar_texto": 1, "zona": 1, "geo_precision": 1,
                "completitud": 1, "fuentes": 1, "asistencias.reunion_id": 1, "lider": 1, "consentimiento": 1, "ultimo_contacto": 1}


def mapa_lugares(db: Database) -> dict[int, dict]:
    return {l["_id"]: l for l in db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1})}


@r.get("/personas")
def listar(f: Filtros = Depends(filtros_query), orden: str = "nombre", pagina: int = 1, por_pagina: int = 50,
           db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    q = filtro(f)
    por_pagina = max(10, min(por_pagina, 200))
    pagina = max(1, pagina)
    total = db.personas.count_documents(q)
    lugares = mapa_lugares(db)
    filas = []
    for p in db.personas.find(q, LISTA_CAMPOS).sort(ORDENES.get(orden, ORDENES["nombre"])).skip((pagina - 1) * por_pagina).limit(por_pagina):
        lg = lugares.get(p.get("lugar_id")) or {}
        filas.append({
            "id": p["_id"], "nombre": p["nombre"], "cedula": p.get("cedula"), "telefono": p.get("telefono"),
            "lugar": lg.get("nombre") or p.get("lugar_texto"), "lugar_tipo": lg.get("tipo"), "zona": p.get("zona"),
            "precision": p.get("geo_precision"), "completitud": p.get("completitud", 0), "fuentes": p.get("fuentes", []),
            "reuniones": len(p.get("asistencias", [])), "lider": bool(p.get("lider")), "consentimiento": p.get("consentimiento"),
            "ultimo_contacto": p.get("ultimo_contacto"),
        })
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "filas": filas}


@r.get("/buscar")
def buscar(q: str, db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    """Autocompletar rápido (registro de asistentes en una reunión)."""
    if len(q.strip()) < 2:
        return []
    lugares = mapa_lugares(db)
    inicio = tx.limpiar(q)
    filas = list(db.personas.find(filtro(Filtros(q=q)), {"nombre": 1, "nombre_norm": 1, "cedula": 1, "telefono": 1,
                                                          "lugar_id": 1, "lugar_texto": 1, "completitud": 1}).limit(60))
    filas.sort(key=lambda p: (not (p.get("nombre_norm") or "").startswith(inicio), -p.get("completitud", 0)))
    return [{"id": p["_id"], "nombre": p["nombre"], "cedula": p.get("cedula"), "telefono": p.get("telefono"),
             "lugar": (lugares.get(p.get("lugar_id")) or {}).get("nombre") or p.get("lugar_texto"),
             "completitud": p.get("completitud", 0)} for p in filas[:12]]


def _persona(db: Database, pid: int) -> dict:
    p = db.personas.find_one({"_id": pid})
    if p is None or p.get("eliminado"):
        raise HTTPException(404, "No existe")
    if p.get("fusionada_en"):
        raise HTTPException(409, {"mensaje": "Esta ficha se unió con otra", "id": p["fusionada_en"]})
    d = {k: v for k, v in p.items() if k not in ("_id", "tramites", "notas", "origen", "asistencias", "etiquetas")}
    d["id"] = pid
    lg = db.lugares.find_one({"_id": p.get("lugar_id")}, {"nombre": 1, "tipo": 1, "zona": 1}) if p.get("lugar_id") else None
    d["lugar_nombre"], d["lugar_tipo"] = (lg or {}).get("nombre"), (lg or {}).get("tipo")
    et = {e["_id"]: e for e in db.etiquetas.find({"_id": {"$in": p.get("etiquetas", [])}})}
    d["etiquetas"] = [{"id": e["_id"], "nombre": e["nombre"], "grupo": e["grupo"]}
                      for e in sorted(et.values(), key=lambda e: (e["grupo"], e.get("orden", 0)))]
    d["tramites"] = sorted(({k: t.get(k) for k in ("fecha", "tipo", "ficha", "direccion", "telefono", "correo")}
                            for t in p.get("tramites", [])), key=lambda t: t["fecha"] or "", reverse=True)
    rids = {a["reunion_id"] for a in p.get("asistencias", [])} | {n.get("reunion_id") for n in p.get("notas", []) if n.get("reunion_id")}
    reus = {x["_id"]: x for x in db.reuniones.find({"_id": {"$in": list(rids)}}, {"titulo": 1, "fecha": 1, "lugar_texto": 1})}
    d["reuniones"] = sorted(({"id": a["reunion_id"], "titulo": reus[a["reunion_id"]]["titulo"], "fecha": reus[a["reunion_id"]]["fecha"],
                              "lugar_texto": reus[a["reunion_id"]].get("lugar_texto"), "rol": a.get("rol"), "nota": a.get("nota")}
                             for a in p.get("asistencias", []) if a["reunion_id"] in reus), key=lambda x: x["fecha"] or "", reverse=True)
    d["notas"] = sorted(({"id": n["id"], "texto": n["texto"], "autor": n.get("autor"), "creado_en": n["creado_en"],
                          "reunion_id": n.get("reunion_id"), "reunion": (reus.get(n.get("reunion_id")) or {}).get("titulo")}
                         for n in p.get("notas", [])), key=lambda n: n["creado_en"], reverse=True)
    d["origen"] = [{"fuente": o["fuente"], "datos": o["datos"]} for o in p.get("origen", [])]
    bd.cerrar_coincidencias_imposibles(db, [pid])
    coin = []
    for c in db.coincidencias.find({"estado": "pendiente", "$or": [{"persona_id": pid}, {"candidato_id": pid}]}):
        otro = c["candidato_id"] if c["persona_id"] == pid else c["persona_id"]
        o = db.personas.find_one({"_id": otro}, {"nombre": 1})
        if o:
            coin.append({"id": c["_id"], "puntaje": c["puntaje"], "estado": c["estado"], "otro_id": otro, "otro_nombre": o["nombre"]})
    d["coincidencias"] = coin
    d["historial"] = [{"ts": h["ts"], "usuario": h.get("usuario"), "accion": h["accion"], "detalle": h.get("detalle")}
                      for h in db.auditoria.find({"entidad": "persona", "entidad_id": pid}).sort("_id", -1).limit(40)]
    return d


@r.get("/personas/{pid}")
def ver(pid: int, db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    return _persona(db, pid)


class PersonaIn(BaseModel):
    nombre: str | None = Field(None, max_length=160)
    cedula: str | None = Field(None, max_length=20)
    sexo: Literal["F", "M", ""] | None = None
    edad: int | None = Field(None, ge=0, le=120)
    fecha_nacimiento: str | None = Field(None, max_length=10)
    telefono: str | None = Field(None, max_length=30)
    telefono2: str | None = Field(None, max_length=30)
    correo: str | None = Field(None, max_length=120)
    direccion: str | None = Field(None, max_length=240)
    ocupacion: str | None = Field(None, max_length=120)
    nivel_educativo: str | None = Field(None, max_length=60)
    personas_hogar: int | None = Field(None, ge=0, le=40)
    lider: bool | None = None
    consentimiento: Literal["si", "no", "pendiente"] | None = None
    consentimiento_fecha: str | None = Field(None, max_length=10)
    observaciones: str | None = Field(None, max_length=4000)
    puesto_votacion: str | None = Field(None, max_length=120)
    mesa: str | None = Field(None, max_length=40)
    lugar_id: int | None = None
    etiquetas: list[int] | None = None
    extra: dict[str, Any] | None = None

    @field_validator("fecha_nacimiento", "consentimiento_fecha")
    @classmethod
    def _fecha(cls, v):
        if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Use el formato AAAA-MM-DD")
        return v or None


def _limpiar_entrada(datos: dict) -> dict:
    out = {}
    for k, v in datos.items():
        if k not in EDITABLES:
            continue
        if isinstance(v, str):
            v = v.strip()
        if k == "nombre":
            v = tx.nombre_visible(v)
            if not tx.nombre_norm(v):
                raise HTTPException(422, "El nombre no puede quedar vacío")
        elif k == "cedula":
            v = tx.cedula(v) or None
            if datos.get("cedula") and not v:
                raise HTTPException(422, "La cédula debe tener entre 5 y 11 dígitos")
        elif k in ("telefono", "telefono2"):
            tels = tx.telefonos(v)
            if v and not tels:
                raise HTTPException(422, f"Teléfono no válido: {v}")
            v = tels[0] if tels else None
        elif k == "correo":
            c = tx.correo(v)
            if v and not c:
                raise HTTPException(422, f"Correo no válido: {v}")
            v = c or None
        elif k == "lider":
            v = bool(v)
        elif v == "":
            v = None
        out[k] = v
    return out


def _extra_y_etiquetas(db: Database, actual: dict, body: PersonaIn) -> dict:
    """Devuelve el $set para campos propios y etiquetas (solo los que existen en el catálogo)."""
    cambios = {}
    if body.extra is not None:
        claves = {c["clave"] for c in db.campos.find({"activo": True}, {"clave": 1})}
        extra = dict(actual.get("extra") or {})
        for k, v in body.extra.items():
            if k in claves:
                if v in (None, ""):
                    extra.pop(k, None)
                else:
                    extra[k] = str(v)[:500] if not isinstance(v, (int, float, bool)) else v
        cambios["extra"] = extra
    if body.etiquetas is not None:
        validas = {e["_id"] for e in db.etiquetas.find({}, {"_id": 1})}
        cambios["etiquetas"] = [e for e in dict.fromkeys(body.etiquetas) if e in validas]
    return cambios


def _cedula_libre(db: Database, cedula: str | None, pid: int | None = None) -> None:
    if not cedula:
        return
    otro = db.personas.find_one({"cedula": cedula, "_id": {"$ne": pid}, "eliminado": {"$ne": True}}, {"nombre": 1})
    if otro:
        raise HTTPException(409, {"mensaje": f"La cédula ya pertenece a {otro['nombre']}", "id": otro["_id"]})


def _guardar(db: Database, pid: int, cambios: dict) -> None:
    if not cambios:
        return
    db.personas.update_one({"_id": pid}, {"$set": {**cambios, "actualizado_en": bd.ahora()}})


@r.patch("/personas/{pid}")
def editar(pid: int, body: PersonaIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    antes = db.personas.find_one({"_id": pid, **bd.ACTIVA})
    if antes is None:
        raise HTTPException(404, "No existe")
    datos = _limpiar_entrada(body.model_dump(exclude_unset=True))
    _cedula_libre(db, datos.get("cedula"), pid)
    if "nombre" in datos:
        datos["nombre_norm"] = tx.nombre_norm(datos["nombre"])
    diff = {k: {"antes": antes.get(k), "despues": v} for k, v in datos.items() if antes.get(k) != v and k != "nombre_norm"}
    extra = _extra_y_etiquetas(db, antes, body)
    diff.update({k: v for k, v in extra.items() if antes.get(k) != v})
    cambios = {**datos, **extra}
    if "lugar_id" in body.model_fields_set and body.lugar_id != antes.get("lugar_id"):
        lg = db.lugares.find_one({"_id": body.lugar_id}) if body.lugar_id else None
        if body.lugar_id and lg is None:
            raise HTTPException(422, "Lugar no existe")
        cambios.update({"lugar_id": lg["_id"] if lg else None, "zona": lg["zona"] if lg else None})
        # Barrio o vereda elegido a mano: se conserva al recalcular y la persona sigue el punto del lugar (o el de su
        # placa). Un punto puesto en el mapa no se mueve. Quitar el lugar vuelve a la ubicación automática.
        if antes.get("geo_manual") not in bd.PUNTO_MANUAL:
            cambios["geo_manual"] = "lugar" if lg else False
        diff["lugar_id"] = {"antes": antes.get("lugar_id"), "despues": body.lugar_id}
    _guardar(db, pid, cambios)
    if "direccion" in diff or "lugar_id" in diff:
        georreferenciar(db, [pid])
    if "cedula" in diff:
        bd.cerrar_coincidencias_imposibles(db, [pid])
    bd.recalcular_completitud(db, [pid])
    if diff:
        bd.auditar(db, adm.usuario, "editar", "persona", pid, diff, adm.ip)
    return _persona(db, pid)


class NuevaPersona(PersonaIn):
    nombre: str = Field(..., min_length=3, max_length=160)
    forzar: bool = False
    reunion_id: int | None = None


@r.post("/personas", status_code=201)
def crear(body: NuevaPersona, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    datos = _limpiar_entrada(body.model_dump(exclude_unset=True, exclude={"forzar", "reunion_id", "etiquetas", "extra", "lugar_id"}))
    _cedula_libre(db, datos.get("cedula"))
    lg = db.lugares.find_one({"_id": body.lugar_id}, {"zona": 1}) if body.lugar_id else None
    if body.lugar_id and lg is None:
        raise HTTPException(422, "Lugar no existe")
    if not body.forzar:
        parecidas = _parecidas(db, datos["nombre"], datos.get("telefono"))
        if parecidas:
            raise HTTPException(409, {"mensaje": "Ya hay personas parecidas", "parecidas": parecidas})
    reunion = db.reuniones.find_one({"_id": body.reunion_id}) if body.reunion_id else None
    fuente = "reunion" if reunion else "manual"
    doc = bd.nueva_persona(db, datos, fuente)
    doc.update(_extra_y_etiquetas(db, doc, body))
    if reunion:
        doc["asistencias"] = [{"reunion_id": reunion["_id"], "rol": None, "nota": None, "creado_en": bd.ahora()}]
        doc["ultimo_contacto"] = reunion["fecha"]
        doc["reunion_origen"] = reunion["_id"]  # la reunión donde se registró (cuenta como persona nueva de esa reunión)
    if lg:  # barrio o vereda elegido a mano: georreferenciar lo conserva y toma su punto (o el de la placa)
        doc.update({"lugar_id": lg["_id"], "zona": lg["zona"], "geo_manual": "lugar"})
    db.personas.insert_one(doc)
    pid = doc["_id"]
    georreferenciar(db, [pid])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, adm.usuario, "crear", "persona", pid, {"fuente": fuente, **datos}, adm.ip)
    return _persona(db, pid)


def _parecidas(db: Database, nombre: str, telefono: str | None, excluir: int | None = None) -> list[dict]:
    n = tx.nombre_norm(nombre)
    toks = tx.tokens_nombre(nombre)
    if not toks:
        return []
    raro = max(toks, key=len)
    lugares = mapa_lugares(db)
    q = {**bd.ACTIVA, "_id": {"$ne": excluir}, "$or": [{"nombre_norm": {"$regex": re.escape(raro)}}, {"telefono": telefono or "-"}]}
    out = []
    for f in db.personas.find(q, {"nombre": 1, "nombre_norm": 1, "cedula": 1, "telefono": 1, "lugar_id": 1, "lugar_texto": 1}).limit(400):
        s = fuzz.token_set_ratio(n, f["nombre_norm"])
        if s >= 85 or (telefono and f.get("telefono") == telefono and s >= 60):
            out.append({"id": f["_id"], "nombre": f["nombre"], "cedula": f.get("cedula"), "telefono": f.get("telefono"),
                        "lugar": (lugares.get(f.get("lugar_id")) or {}).get("nombre") or f.get("lugar_texto"), "parecido": round(s)})
    return sorted(out, key=lambda x: -x["parecido"])[:8]


@r.get("/personas/{pid}/parecidas")
def parecidas(pid: int, db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    p = db.personas.find_one({"_id": pid}, {"nombre": 1, "telefono": 1})
    if p is None:
        raise HTTPException(404, "No existe")
    return _parecidas(db, p["nombre"], p.get("telefono"), pid)


class NotaIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)
    reunion_id: int | None = None


@r.post("/personas/{pid}/notas", status_code=201)
def nota(pid: int, body: NotaIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    nueva = {"id": str(ObjectId()), "texto": body.texto.strip(), "autor": adm.usuario, "creado_en": bd.ahora(),
             "reunion_id": body.reunion_id}
    r_ = db.personas.update_one({"_id": pid, **bd.ACTIVA}, {"$push": {"notas": nueva},
                                                           "$max": {"ultimo_contacto": bd.ahora()[:10]},
                                                           "$set": {"actualizado_en": bd.ahora()}})
    if not r_.matched_count:
        raise HTTPException(404, "No existe")
    bd.auditar(db, adm.usuario, "nota", "persona", pid, {"reunion_id": body.reunion_id}, adm.ip)
    return _persona(db, pid)


@r.delete("/personas/{pid}/notas/{nid}")
def borrar_nota(pid: int, nid: str, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    db.personas.update_one({"_id": pid}, {"$pull": {"notas": {"id": nid}}})
    bd.auditar(db, adm.usuario, "borrar_nota", "persona", pid, {"nota": nid}, adm.ip)
    return _persona(db, pid)


class UbicacionIn(BaseModel):
    lat: float = Field(..., ge=6.3, le=7.5)
    lon: float = Field(..., ge=-74.6, le=-73.6)


@r.put("/personas/{pid}/ubicacion")
def ubicar(pid: int, body: UbicacionIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    antes = db.personas.find_one({"_id": pid}, {"lat": 1, "lon": 1})
    if antes is None:
        raise HTTPException(404, "No existe")
    _guardar(db, pid, {"lat": round(body.lat, 6), "lon": round(body.lon, 6), "geo_precision": "manual", "geo_manual": "punto"})
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, adm.usuario, "ubicar", "persona", pid,
               {"antes": [antes.get("lat"), antes.get("lon")], "despues": [body.lat, body.lon]}, adm.ip)
    return _persona(db, pid)


@r.delete("/personas/{pid}/ubicacion")
def ubicacion_automatica(pid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    _guardar(db, pid, {"geo_manual": False})
    georreferenciar(db, [pid])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, adm.usuario, "ubicacion_automatica", "persona", pid, None, adm.ip)
    return _persona(db, pid)


class FusionIn(BaseModel):
    con_id: int


@r.post("/personas/{pid}/fusionar")
def fusionar(pid: int, body: FusionIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    a = db.personas.find_one({"_id": pid, **bd.ACTIVA}, {"cedula": 1})
    b = db.personas.find_one({"_id": body.con_id, **bd.ACTIVA}, {"cedula": 1})
    if a is None or b is None or pid == body.con_id:
        raise HTTPException(404, "Alguna de las dos fichas no existe")
    if a.get("cedula") and b.get("cedula") and a["cedula"] != b["cedula"]:
        raise HTTPException(409, "Las dos fichas tienen cédulas distintas: son personas diferentes")
    bd.fusionar(db, pid, body.con_id, adm.usuario, adm.ip)
    return _persona(db, pid)


@r.delete("/personas/{pid}")
def suprimir(pid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    """Supresión a pedido del titular (Ley 1581): borra los datos personales de la ficha y de las unidas con ella,
    quita sus datos de la auditoría y deja una huella cifrada para que una importación no la vuelva a crear."""
    if not db.personas.find_one({"_id": pid}, {"_id": 1}):
        raise HTTPException(404, "No existe")
    bd.suprimir(db, pid, adm.usuario, adm.ip)
    return {"ok": True}
