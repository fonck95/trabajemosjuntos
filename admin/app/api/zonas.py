"""Zonas (áreas) dibujadas en el mapa (6): guardarlas con nombre, editarlas, borrarlas y asignarlas.

* Solo A y K (`zonas.gestionar`): el mapa y la medición de zonas no son de planilleros ni consultores (10.2). Ellos
  reciben las áreas como alcance (`usuarios.asignacion.areas`) y no ven estas rutas.
* `poligono` llega como anillo `[[lon, lat], …]`, como texto «lon,lat;…» (el de la URL) o como GeoJSON Polygon. Se
  guarda como anillo limpio (`geometria.validar_anillo`: 6 decimales, de 3 a 150 vértices dentro de Yondó, sin lados
  cruzados, entre 100 m² y 4 000 km²) con su área y su perímetro; 422 `{codigo: "poligono"}` si no sirve.
* Tope de 200 áreas (409). El nombre es único sin distinguir mayúsculas (409). El color sale de una paleta fija y
  cumple `^#[0-9a-fA-F]{6}$` (422).
* La asignación vive en dos lugares que se mantienen iguales: `areas.asignada_a` y `usuarios.asignacion.areas` (de
  este último salen el alcance de P y C y el avance por zona). Al leer, los asignados salen de `usuarios`, así se ve
  también lo que se cambió desde Usuarios. Solo se asignan planilleros y consultores: K y A no tienen asignación.
* Borrar quita el área de la asignación de todos. La auditoría guarda el área completa (con el polígono codificado):
  nada se pierde.
* Lo que cambia el alcance de un usuario le borra sus conversaciones con el asistente, como en Usuarios: lo que el
  modelo le mostró era de su zona de antes. Al crear o editar, a los que ganan o pierden el área; al redibujarla o
  borrarla, a todos los que la tenían o la tienen. El nombre, la descripción y el color no borran nada.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo import IndexModel
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, OperationFailure

from .. import acceso, geometria
from .. import db as bd
from ..acceso import Quien, requiere
from ..seguridad import obtener_db

log = logging.getLogger("panel")
r = APIRouter(prefix="/api", tags=["zonas"])
GESTIONAR = requiere("zonas.gestionar")

TOPE = 200
COLOR = r"^#[0-9a-fA-F]{6}$"
# Paleta fija de la interfaz (PALETA de web/js/zona.js; el rojo queda para «los lados se cruzan»). El servidor acepta
# cualquier #rrggbb válido
PALETA = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#3d3d3a")
_preparadas: set[str] = set()


class AreaNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=2, max_length=80)
    descripcion: str | None = Field(None, max_length=500)
    color: str | None = Field(None, pattern=COLOR)
    poligono: Any
    asignada_a: list[int] = Field(default_factory=list, max_length=200)


class AreaCambio(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str | None = Field(None, min_length=2, max_length=80)
    descripcion: str | None = Field(None, max_length=500)
    color: str | None = Field(None, pattern=COLOR)
    poligono: Any = None
    asignada_a: list[int] | None = Field(None, max_length=200)


def _preparar(db: Database) -> None:
    """Los índices de `areas` (1.10), los mismos que crea `db.inicializar`: aquí por si esta base aún no los tiene."""
    if db.name in _preparadas:
        return
    try:
        db.areas.create_indexes([IndexModel("nombre", unique=True), IndexModel("asignada_a")])
    except OperationFailure as e:  # ya existen con otras opciones: no se tocan
        log.warning("Índices de areas: %s", e)
    _preparadas.add(db.name)


def _nombre(n: str) -> str:
    n = " ".join((n or "").split())
    if len(n) < 2:
        raise HTTPException(422, "Escriba un nombre para la zona")
    return n


def _exigir_nombre_libre(db: Database, nombre: str, aid: int | None = None) -> None:
    q: dict = {"nombre": {"$regex": f"^{re.escape(nombre)}$", "$options": "i"}}
    if aid is not None:
        q["_id"] = {"$ne": aid}
    if db.areas.find_one(q, {"_id": 1}):
        raise HTTPException(409, f"Ya hay una zona llamada «{nombre}»")


def _asignables(db: Database, uids: list[int]) -> list[int]:
    """Los uid sin repetir, en orden; 422 si alguno no es un planillero o consultor."""
    uids = list(dict.fromkeys(uids))
    hay = {u["_id"] for u in db.usuarios.find({"_id": {"$in": uids}, "rol": {"$in": list(acceso.ROLES_CAMPO)}},
                                               {"_id": 1})}
    faltan = [u for u in uids if u not in hay]
    if faltan:
        raise HTTPException(422, f"Solo se asignan zonas a planilleros y consultores: {faltan}")
    return uids


def _sin_area(aid: int) -> dict:
    return {"$filter": {"input": {"$ifNull": ["$asignacion.areas", []]}, "cond": {"$ne": ["$$this", aid]}}}


def _sincronizar(db: Database, aid: int, uids: list[int]) -> None:
    """`usuarios.asignacion.areas` queda con `aid` exactamente en `uids` (escrituras parciales, sin tocar lo demás)."""
    if uids:
        db.usuarios.update_many({"_id": {"$in": uids}, "asignacion.areas": {"$ne": aid}}, [{"$set": {"asignacion": {
            "$mergeObjects": ["$asignacion", {"areas": {"$concatArrays": [_sin_area(aid), [aid]]}}]}}}])
    db.usuarios.update_many({"_id": {"$nin": uids}, "asignacion.areas": aid}, [{"$set": {"asignacion": {
        "$mergeObjects": ["$asignacion", {"areas": _sin_area(aid)}]}}}])


def _con_area(db: Database, aid: int) -> set[int]:
    """Quienes tienen el área en su alcance (`usuarios.asignacion.areas`, de donde sale)."""
    return {u["_id"] for u in db.usuarios.find({"asignacion.areas": aid}, {"_id": 1})}


def _olvidar(db: Database, uids: set[int]) -> None:
    """Borra las conversaciones con el asistente de quienes cambió el alcance (`usuarios.editar` hace lo mismo): el
    historial se le reenvía al modelo en cada ronda con fichas de la zona de antes."""
    if uids:
        bd.borrar_conversaciones(db, {"uid": {"$in": sorted(uids)}})


def _asignados(db: Database, ids: list[int]) -> dict[int, list[dict]]:
    """Por área, los usuarios que la tienen asignada (de `usuarios`, la fuente del alcance)."""
    out: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        for u in db.usuarios.find({"asignacion.areas": {"$in": ids}, "rol": {"$in": list(acceso.ROLES_CAMPO)}},
                                  {"usuario": 1, "nombre": 1, "rol": 1, "activo": 1, "asignacion.areas": 1}
                                  ).sort("usuario", 1):
            fila = {"id": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
                    "activo": bool(u.get("activo"))}
            for i in (u.get("asignacion") or {}).get("areas") or []:
                if i in out:
                    out[i].append(fila)
    return out


def _salida(a: dict, asignados: list[dict]) -> dict:
    anillo = a.get("poligono") or []
    if isinstance(anillo, dict):  # un área guardada como GeoJSON (de otra versión): se entrega como anillo
        anillo = geometria._abierto((anillo.get("coordinates") or [[]])[0])
    return {"id": a["_id"], "nombre": a.get("nombre"), "descripcion": a.get("descripcion"), "color": a.get("color"),
            "poligono": anillo, "codificado": geometria.codificar(anillo) if anillo else "",
            "vertices": len(anillo), "area_m2": a.get("area_m2"), "perimetro_m": a.get("perimetro_m"),
            "asignada_a": [u["id"] for u in asignados], "asignados": asignados,
            "creado_por": a.get("creado_por"), "creado_en": a.get("creado_en"), "actualizado_en": a.get("actualizado_en")}


def _cargar(db: Database, aid: int) -> dict:
    a = db.areas.find_one({"_id": aid})
    if a is None:
        raise HTTPException(404, "La zona no existe")
    return a


def _para_auditoria(a: dict) -> dict:
    """El área completa para la auditoría, con el polígono codificado (así un borrado no pierde nada)."""
    anillo = a.get("poligono") if isinstance(a.get("poligono"), list) else []
    return {"nombre": a.get("nombre"), "descripcion": a.get("descripcion"), "color": a.get("color"),
            "poligono": geometria.codificar(anillo) if anillo else None, "area_m2": a.get("area_m2"),
            "perimetro_m": a.get("perimetro_m"), "asignada_a": list(a.get("asignada_a") or [])}


@r.get("/areas")
def listar(db: Database = Depends(obtener_db), _: Quien = Depends(GESTIONAR)):
    areas = list(db.areas.find().sort("nombre", 1).limit(TOPE * 2))
    asig = _asignados(db, [a["_id"] for a in areas])
    return {"tope": TOPE, "paleta": list(PALETA), "areas": [_salida(a, asig[a["_id"]]) for a in areas]}


@r.post("/areas", status_code=201)
def crear(a: AreaNueva, db: Database = Depends(obtener_db), quien: Quien = Depends(GESTIONAR)):
    _preparar(db)
    nombre = _nombre(a.nombre)
    anillo = geometria.anillo_de(a.poligono)
    uids = _asignables(db, a.asignada_a)
    if db.areas.count_documents({}) >= TOPE:
        raise HTTPException(409, f"Ya hay {TOPE} zonas guardadas: borre alguna antes de guardar otra")
    _exigir_nombre_libre(db, nombre)
    ahora = bd.ahora()
    doc = {"_id": bd.siguiente_id(db, "areas"), "nombre": nombre, "descripcion": (a.descripcion or "").strip() or None,
           "poligono": anillo, **geometria.medidas(anillo), "color": (a.color or PALETA[0]).lower(),
           "asignada_a": uids, "creado_por": quien.uid, "creado_en": ahora, "actualizado_en": ahora}
    try:
        db.areas.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"Ya hay una zona llamada «{nombre}»") from None
    _sincronizar(db, doc["_id"], uids)
    _olvidar(db, set(uids))
    bd.auditar(db, quien, "crear_area", "area", doc["_id"], _para_auditoria(doc))
    return _salida(doc, _asignados(db, [doc["_id"]])[doc["_id"]])


@r.get("/areas/{aid}")
def ver(aid: int, db: Database = Depends(obtener_db), _: Quien = Depends(GESTIONAR)):
    a = _cargar(db, aid)
    return _salida(a, _asignados(db, [aid])[aid])


@r.patch("/areas/{aid}")
def editar(aid: int, c: AreaCambio, db: Database = Depends(obtener_db), quien: Quien = Depends(GESTIONAR)):
    _preparar(db)
    antes = _cargar(db, aid)
    dado = c.model_fields_set
    cambios: dict = {}
    if "nombre" in dado and c.nombre is not None:
        nombre = _nombre(c.nombre)
        if nombre != antes.get("nombre"):
            _exigir_nombre_libre(db, nombre, aid)
            cambios["nombre"] = nombre
    if "descripcion" in dado:
        d = (c.descripcion or "").strip() or None
        if d != antes.get("descripcion"):
            cambios["descripcion"] = d
    if "color" in dado and c.color is not None and c.color.lower() != antes.get("color"):
        cambios["color"] = c.color.lower()
    if "poligono" in dado and c.poligono is not None:
        anillo = geometria.anillo_de(c.poligono)
        if anillo != antes.get("poligono"):
            cambios.update(poligono=anillo, **geometria.medidas(anillo))
    uids = None
    if "asignada_a" in dado and c.asignada_a is not None:
        uids = _asignables(db, c.asignada_a)
        actuales = [u["id"] for u in _asignados(db, [aid])[aid]]
        if sorted(uids) != sorted(actuales) or sorted(uids) != sorted(antes.get("asignada_a") or []):
            cambios["asignada_a"] = uids
    if cambios:
        cambios["actualizado_en"] = bd.ahora()
        tenian = _con_area(db, aid)
        try:
            db.areas.update_one({"_id": aid}, {"$set": cambios})
        except DuplicateKeyError:
            raise HTTPException(409, f"Ya hay una zona llamada «{cambios.get('nombre')}»") from None
        if uids is not None:
            _sincronizar(db, aid, uids)
        tienen = set(uids) if uids is not None else tenian
        # Redibujarla cambia el alcance de todos los que la tienen; asignarla, el de los que la ganan o la pierden
        _olvidar(db, (tenian | tienen) if "poligono" in cambios else (tenian ^ tienen))
        campos = sorted(k for k in cambios if k not in ("actualizado_en", "area_m2", "perimetro_m"))
        previo = _para_auditoria(antes)
        bd.auditar(db, quien, "editar_area", "area", aid,
                   {"nombre": cambios.get("nombre", antes.get("nombre")),
                    "antes": {k: previo.get(k) for k in campos},
                    "despues": {k: _para_auditoria({**antes, **cambios}).get(k) for k in campos}})
    a = _cargar(db, aid)
    return _salida(a, _asignados(db, [aid])[aid])


@r.delete("/areas/{aid}")
def borrar(aid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(GESTIONAR)):
    a = _cargar(db, aid)
    asignados = [u["id"] for u in _asignados(db, [aid])[aid]]
    tenian = _con_area(db, aid)
    db.areas.delete_one({"_id": aid})
    _sincronizar(db, aid, [])
    _olvidar(db, tenian)
    bd.auditar(db, quien, "borrar_area", "area", aid, {**_para_auditoria(a), "asignada_a": asignados})
    return {"ok": True, "desasignados": len(asignados)}
