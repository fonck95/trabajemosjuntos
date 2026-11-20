"""Líderes: quién trajo a quién (el «Liderado por» de cada ficha).

Una persona marcada como líder o como concejal (`lider` o `concejal`, en su ficha: `modelo.TIPOS_LIDERAN`) trae a
otras, en general votantes. Cada ficha guarda en `lideres` a quienes la trajeron, uno o varios:
[{id, asignado_en, asignado_por, asignado_por_uid}]. Con más de uno, varios están captando a la misma persona, y eso se
ve en la ficha, en Habitantes (filtro `varios_lideres`) y en la lista de líderes.

* Es un dato político, como `lider`: solo A y K lo ven y lo cambian (`requiere("admin")`); P y C nunca lo reciben, el
  asistente tampoco (`minimizar` es una lista blanca y `lideres` está en sus vedados), y la auditoría lo oculta.
* Solo se asigna una ficha activa marcada como líder o como concejal, y nadie es su propio líder. Al unir fichas, los
  líderes del origen pasan al destino y quien tenía como líder al origen pasa a tener al destino
  (`db.reapuntar_lideres`); al suprimir una ficha, sale de los líderes de todas (`db.limpiar_ligados`). Quitarle a
  alguien la marca de líder no le quita a quienes trajo: siguen con él, y la ficha lo muestra como «ya no marcado como
  líder».
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.database import Database

from .. import db as bd
from .. import modelo, proyeccion
from ..acceso import Quien, requiere
from ..seguridad import obtener_db
from .personas import _lit, escribir, etapa_actualizado, ficha_respuesta

r = APIRouter(prefix="/api", tags=["lideres"])

MAX_LIDERES = 10


def exigir_lider(db: Database, lid: int, pid: int | None) -> dict:
    """La ficha activa `lid`, marcada como líder o como concejal, que puede ser líder de `pid` (no de sí misma). 422
    si no."""
    if pid is not None and lid == pid:
        raise HTTPException(422, {"mensaje": "Una persona no puede ser su propio líder", "campo": "lider_id"})
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA}, {"nombre": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})
    if l is None:
        raise HTTPException(422, {"mensaje": "Esa ficha de líder no existe, se unió o se suprimió", "campo": "lider_id"})
    if not modelo.lidera(l):
        raise HTTPException(422, {"mensaje": f"{l.get('nombre') or 'Esa persona'} no está marcada como líder ni como "
                                             "concejal: márquela en su ficha primero", "campo": "lider_id"})
    return l


def _tipo_lider(l: dict) -> str | None:
    """«concejal» o «lider» (concejal primero si es las dos cosas); None si ya no está marcada como ninguna."""
    return next((t for t in modelo.TIPOS_LIDERAN if l.get(t) is True), None)


def lideres_de(db: Database, p: dict) -> list[dict]:
    """Los líderes de la ficha `p` para la ficha de A y K: [{id, nombre, tipo, marcado, asignado_en, asignado_por}],
    en el orden en que se asignaron (`tipo`: concejal o lider). Una ficha de líder que ya no está activa no sale (la
    unión y la supresión los limpian)."""
    asignados = [l for l in p.get("lideres") or [] if isinstance(l, dict) and isinstance(l.get("id"), int)]
    if not asignados:
        return []
    fichas = {x["_id"]: x for x in db.personas.find({"_id": {"$in": [l["id"] for l in asignados]}, **bd.ACTIVA},
                                                    {"nombre": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})}
    return [{"id": l["id"], "nombre": fichas[l["id"]].get("nombre"), "tipo": _tipo_lider(fichas[l["id"]]),
             "marcado": modelo.lidera(fichas[l["id"]]), "asignado_en": l.get("asignado_en"),
             "asignado_por": l.get("asignado_por")}
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
    # Condicional: dos asignaciones del mismo líder a la vez dejan una sola. Si alguien lo había quitado, deja de
    # contar como quitado
    if escribir(db, pid, [{"$set": {"lideres": {"$concatArrays": [{"$ifNull": ["$lideres", []]}, [_lit(nuevo)]]},
                                    "lideres_quitados": {"$setDifference": [{"$ifNull": ["$lideres_quitados", []]},
                                                                            [body.lider_id]]}}},
                          etapa_actualizado(quien)], [{"lideres.id": {"$ne": body.lider_id}}]):
        bd.auditar(db, quien, "asignar_lider", "persona", pid, {"lider_id": body.lider_id}, campos=["lideres"])
    return ficha_respuesta(db, quien, pid)


@r.delete("/personas/{pid}/lideres/{lid}")
def quitar(pid: int, lid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Quita un líder de la persona (si no lo tenía, no cambia nada). Queda anotado en `lideres_quitados`: la
    importación de la base general no se lo vuelve a poner."""
    p = proyeccion.persona_activa(db, pid, {"lideres": 1, "consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "editar")
    if escribir(db, pid, [{"$set": {"lideres": {"$filter": {"input": {"$ifNull": ["$lideres", []]}, "as": "l",
                                                            "cond": {"$ne": ["$$l.id", lid]}}},
                                    "lideres_quitados": {"$setUnion": [{"$ifNull": ["$lideres_quitados", []]},
                                                                       [lid]]}}},
                          etapa_actualizado(quien)], [{"lideres.id": lid}]):
        bd.auditar(db, quien, "quitar_lider", "persona", pid, {"lider_id": lid}, campos=["lideres"])
    return ficha_respuesta(db, quien, pid)


@r.get("/lideres")
def listar(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Los líderes (las fichas marcadas como líder o como concejal y las que figuran como líder de alguien), cada uno
    con su tipo, cuántas personas trajo, cuántas de ellas son votantes y cuántas trae también otro líder; y cuántas
    personas tienen más de un líder."""
    traidas, compartidas, votantes = Counter(), Counter(), Counter()
    varias = 0
    for x in db.personas.find({**bd.ACTIVA, "lideres.0": {"$exists": True}}, {"lideres.id": 1, "votante": 1}):
        ids = {l.get("id") for l in x.get("lideres") or [] if isinstance(l, dict)}
        varias += len(ids) > 1
        for i in ids:
            traidas[i] += 1
            compartidas[i] += len(ids) > 1
            votantes[i] += x.get("votante") is True
    ctx = proyeccion.contexto(db)
    filas = []
    marcados = [{t: True} for t in modelo.TIPOS_LIDERAN]
    for l in db.personas.find({**bd.ACTIVA, "$or": [*marcados, {"_id": {"$in": list(traidas)}}]},
                              {"nombre": 1, "lugar_id": 1, "lugar_texto": 1, "cedula": 1,
                               **{t: 1 for t in modelo.TIPOS_LIDERAN}}):
        filas.append({"id": l["_id"], "nombre": l.get("nombre"), "tipo": _tipo_lider(l), "marcado": modelo.lidera(l),
                      "cedula": l.get("cedula"),  # A y K ven la cédula completa: el buscador la usa
                      "lugar": ctx.lugar(l.get("lugar_id")).get("nombre") or l.get("lugar_texto"),
                      "traidas": traidas[l["_id"]], "votantes": votantes[l["_id"]],
                      "compartidas": compartidas[l["_id"]]})
    filas.sort(key=lambda f: (-f["traidas"], f["nombre"] or ""))
    return {"lideres": filas, "personas_con_varios": varias}
