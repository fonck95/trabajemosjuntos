"""Líderes: quién trajo a quién.

Una persona marcada como líder (`lider`, en su ficha) trae a otras. Cada ficha guarda en `lideres` a los líderes que
la trajeron, uno o varios: [{id, asignado_en, asignado_por, asignado_por_uid}]. Con más de uno, varios líderes están
captando a la misma persona, y eso se ve en la ficha, en Habitantes (filtro `varios_lideres`) y en la lista de líderes.

* Es un dato político, como `lider`: solo A y K lo ven y lo cambian (`requiere("admin")`); P y C nunca lo reciben, el
  asistente tampoco (`minimizar` es una lista blanca y `lideres` está en sus vedados), y la auditoría lo oculta.
* Solo se asigna una ficha activa marcada como líder, y nadie es su propio líder. Al unir fichas, los líderes del
  origen pasan al destino y quien tenía como líder al origen pasa a tener al destino (`db.reapuntar_lideres`); al
  suprimir una ficha, sale de los líderes de todas (`db.limpiar_ligados`). Quitarle a alguien la marca de líder no le
  quita a quienes trajo: siguen con él, y la ficha lo muestra como «ya no marcado como líder».
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.database import Database

from .. import db as bd
from .. import proyeccion
from ..acceso import Quien, requiere
from ..seguridad import obtener_db
from .personas import _lit, escribir, etapa_actualizado, ficha_respuesta

r = APIRouter(prefix="/api", tags=["lideres"])

MAX_LIDERES = 10


def exigir_lider(db: Database, lid: int, pid: int | None) -> dict:
    """La ficha activa `lid`, marcada como líder, que puede ser líder de `pid` (no de sí misma). 422 si no."""
    if pid is not None and lid == pid:
        raise HTTPException(422, {"mensaje": "Una persona no puede ser su propio líder", "campo": "lider_id"})
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA}, {"nombre": 1, "lider": 1})
    if l is None:
        raise HTTPException(422, {"mensaje": "Esa ficha de líder no existe, se unió o se suprimió", "campo": "lider_id"})
    if not l.get("lider"):
        raise HTTPException(422, {"mensaje": f"{l.get('nombre') or 'Esa persona'} no está marcada como líder: márquela "
                                             "en su ficha primero", "campo": "lider_id"})
    return l


def lideres_de(db: Database, p: dict) -> list[dict]:
    """Los líderes de la ficha `p` para la ficha de A y K: [{id, nombre, marcado, asignado_en, asignado_por}], en el
    orden en que se asignaron. Una ficha de líder que ya no está activa no sale (la unión y la supresión los limpian)."""
    asignados = [l for l in p.get("lideres") or [] if isinstance(l, dict) and isinstance(l.get("id"), int)]
    if not asignados:
        return []
    fichas = {x["_id"]: x for x in db.personas.find({"_id": {"$in": [l["id"] for l in asignados]}, **bd.ACTIVA},
                                                    {"nombre": 1, "lider": 1})}
    return [{"id": l["id"], "nombre": fichas[l["id"]].get("nombre"), "marcado": bool(fichas[l["id"]].get("lider")),
             "asignado_en": l.get("asignado_en"), "asignado_por": l.get("asignado_por")}
            for l in asignados if l["id"] in fichas]


def traidas_de(db: Database, pid: int) -> dict:
    """Lo que trajo el líder `pid`: {total, compartidas} (compartidas: las que además trae otro líder)."""
    total = compartidas = 0
    for x in db.personas.find({**bd.ACTIVA, "lideres.id": pid}, {"lideres.id": 1}):
        total += 1
        compartidas += len({l.get("id") for l in x.get("lideres") or []}) > 1
    return {"total": total, "compartidas": compartidas}


class LiderIn(BaseModel):
    lider_id: int


@r.post("/personas/{pid}/lideres", status_code=201)
def asignar(pid: int, body: LiderIn, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Asigna un líder a la persona. Si ya lo tenía, no cambia nada (se puede repetir sin daño)."""
    p = proyeccion.persona_activa(db, pid, {"lideres": 1, "consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "editar")
    actuales = [l.get("id") for l in p.get("lideres") or [] if isinstance(l, dict)]
    if body.lider_id in actuales:  # ya lo tenía (aunque después le quitaran la marca de líder)
        return ficha_respuesta(db, quien, pid)
    exigir_lider(db, body.lider_id, pid)
    if len(actuales) >= MAX_LIDERES:
        raise HTTPException(422, f"Una persona puede tener hasta {MAX_LIDERES} líderes")
    nuevo = {"id": body.lider_id, "asignado_en": bd.ahora(), "asignado_por": quien.usuario,
             "asignado_por_uid": quien.uid}
    # Condicional: dos asignaciones del mismo líder a la vez dejan una sola
    if escribir(db, pid, [{"$set": {"lideres": {"$concatArrays": [{"$ifNull": ["$lideres", []]}, [_lit(nuevo)]]}}},
                          etapa_actualizado(quien)], [{"lideres.id": {"$ne": body.lider_id}}]):
        bd.auditar(db, quien, "asignar_lider", "persona", pid, {"lider_id": body.lider_id}, campos=["lideres"])
    return ficha_respuesta(db, quien, pid)


@r.delete("/personas/{pid}/lideres/{lid}")
def quitar(pid: int, lid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Quita un líder de la persona (si no lo tenía, no cambia nada)."""
    p = proyeccion.persona_activa(db, pid, {"lideres": 1, "consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "editar")
    if escribir(db, pid, [{"$set": {"lideres": {"$filter": {"input": {"$ifNull": ["$lideres", []]}, "as": "l",
                                                            "cond": {"$ne": ["$$l.id", lid]}}}}},
                          etapa_actualizado(quien)], [{"lideres.id": lid}]):
        bd.auditar(db, quien, "quitar_lider", "persona", pid, {"lider_id": lid}, campos=["lideres"])
    return ficha_respuesta(db, quien, pid)


@r.get("/lideres")
def listar(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Los líderes (las fichas marcadas como líder y las que figuran como líder de alguien), cada uno con cuántas
    personas trajo y cuántas de ellas trae también otro líder; y cuántas personas tienen más de un líder."""
    traidas, compartidas = Counter(), Counter()
    varias = 0
    for x in db.personas.find({**bd.ACTIVA, "lideres.0": {"$exists": True}}, {"lideres.id": 1}):
        ids = {l.get("id") for l in x.get("lideres") or [] if isinstance(l, dict)}
        varias += len(ids) > 1
        for i in ids:
            traidas[i] += 1
            compartidas[i] += len(ids) > 1
    ctx = proyeccion.contexto(db)
    filas = []
    for l in db.personas.find({**bd.ACTIVA, "$or": [{"lider": True}, {"_id": {"$in": list(traidas)}}]},
                              {"nombre": 1, "lider": 1, "lugar_id": 1, "lugar_texto": 1}):
        filas.append({"id": l["_id"], "nombre": l.get("nombre"), "marcado": bool(l.get("lider")),
                      "lugar": ctx.lugar(l.get("lugar_id")).get("nombre") or l.get("lugar_texto"),
                      "traidas": traidas[l["_id"]], "compartidas": compartidas[l["_id"]]})
    filas.sort(key=lambda f: (-f["traidas"], f["nombre"] or ""))
    return {"lideres": filas, "personas_con_varios": varias}
