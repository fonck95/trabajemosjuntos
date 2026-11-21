"""Líderes: quién trajo a quién (el «Liderado por» de cada ficha).

Una persona marcada como líder o como concejal (`lider` o `concejal`, en su ficha: `modelo.TIPOS_LIDERAN`) trae a
otras, en general votantes. Cada ficha guarda en `lideres` a quienes la trajeron, uno o varios:
[{id, asignado_en, asignado_por, asignado_por_uid}]. Con más de uno, varios están captando a la misma persona, y eso se
ve en la ficha, en Habitantes (filtro `varios_lideres`) y en la lista de líderes.

* Es un dato político, como `lider`. A y K lo ven y lo cambian todo. P (`lideres.asignar`) lo ve en la ficha de las
  personas de su zona y de las que registró (`proyeccion.tipo_visible`, sin quién asignó), busca líderes y concejales
  de toda la campaña (`candidatos`: por nombre o por la cédula completa, sin conteos) y asigna uno, pero nunca quita:
  ni un líder (`quitar`, `requiere("admin")`) ni lo que A o K quitaron (409 `lider_quitado`). La lista de líderes con
  sus conteos (`listar`) es solo de A y K. C nunca lo recibe; el asistente tampoco (`minimizar` es una lista blanca y
  `lideres` está en sus vedados), y la auditoría lo oculta.
* Solo se asigna una ficha activa marcada como líder o como concejal, y nadie es su propio líder. Al unir fichas, los
  líderes del origen pasan al destino y quien tenía como líder al origen pasa a tener al destino
  (`db.reapuntar_lideres`); al suprimir una ficha, sale de los líderes de todas (`db.limpiar_ligados`). Quitarle a
  alguien la marca de líder no le quita a quienes trajo: siguen con él, y la ficha lo muestra como «ya no marcado como
  líder».
"""
from __future__ import annotations

import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo import ASCENDING
from pymongo.database import Database

from .. import acceso, modelo, proyeccion
from .. import db as bd
from ..acceso import Quien, requiere
from ..pipeline import texto as tx
from ..seguridad import obtener_db
from .personas import FUERA_DE_ZONA, _lit, _prohibido, escribir, etapa_actualizado, ficha_respuesta

r = APIRouter(prefix="/api", tags=["lideres"])

MAX_LIDERES = 10
MAX_CANDIDATOS = 12
# Para quien no administra, un solo mensaje: con el nombre de la ficha (o con un mensaje distinto para cada motivo),
# P leería el nombre de cualquier id, también de quien no autorizó, sin pasar por el presupuesto diario
ELIJA_DE_LA_LISTA = {"mensaje": "Elija un líder o concejal de la lista", "campo": "lider_id"}
LIDER_QUITADO = {"mensaje": "El administrador o el coordinador le quitó ese líder a esta persona: pídales que lo "
                            "vuelvan a asignar", "codigo": "lider_quitado", "campo": "lider_id"}


def exigir_lider(db: Database, lid: int, pid: int | None, quien: Quien | None = None) -> dict:
    """La ficha activa `lid`, marcada como líder o como concejal, que puede ser líder de `pid` (no de sí misma). 422
    si no. Para quien no administra (sin `quien`, también), además debe haber autorizado el tratamiento, y el 422 es
    el mismo para todo motivo (`ELIJA_DE_LA_LISTA`): no dice el nombre ni si la ficha existe."""
    if pid is not None and lid == pid:
        raise HTTPException(422, {"mensaje": "Una persona no puede ser su propio líder", "campo": "lider_id"})
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA},
                             {"nombre": 1, "consentimiento": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})
    if not proyeccion.administra(quien):
        if l is None or not modelo.lidera(l) or l.get("consentimiento") == "no":
            raise HTTPException(422, dict(ELIJA_DE_LA_LISTA))
        return l
    if l is None:
        raise HTTPException(422, {"mensaje": "Esa ficha de líder no existe, se unió o se suprimió", "campo": "lider_id"})
    if not modelo.lidera(l):
        raise HTTPException(422, {"mensaje": f"{l.get('nombre') or 'Esa persona'} no está marcada como líder ni como "
                                             "concejal: márquela en su ficha primero", "campo": "lider_id"})
    return l


def _tipo_lider(l: dict) -> str | None:
    """«concejal» o «lider» (concejal primero si es las dos cosas); None si ya no está marcada como ninguna."""
    return next((t for t in modelo.TIPOS_LIDERAN if l.get(t) is True), None)


def lideres_de(db: Database, p: dict, administra: bool = True) -> list[dict]:
    """Los líderes de la ficha `p` (el «Liderado por»): [{id, nombre, tipo, marcado, asignado_en, asignado_por}], en el
    orden en que se asignaron (`tipo`: concejal o lider). Una ficha de líder que ya no está activa no sale (la unión y
    la supresión los limpian). Para quien no administra (la ficha de P): sin `asignado_por`, que es el usuario de otro
    miembro del equipo, y sin los líderes que no autorizaron el tratamiento: para P quien no autorizó es la ficha
    mínima, sin tipo, y estar en el «Liderado por» de alguien ya diría que lidera."""
    asignados = [l for l in p.get("lideres") or [] if isinstance(l, dict) and isinstance(l.get("id"), int)]
    if not asignados:
        return []
    fichas = {x["_id"]: x for x in db.personas.find(
        {"_id": {"$in": [l["id"] for l in asignados]}, **bd.ACTIVA,
         **({} if administra else {"consentimiento": {"$ne": "no"}})},
        {"nombre": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})}
    return [{"id": l["id"], "nombre": fichas[l["id"]].get("nombre"), "tipo": _tipo_lider(fichas[l["id"]]),
             "marcado": modelo.lidera(fichas[l["id"]]), "asignado_en": l.get("asignado_en"),
             **({"asignado_por": l.get("asignado_por")} if administra else {})}
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
def asignar(pid: int, body: LiderIn, db: Database = Depends(obtener_db),
            quien: Quien = Depends(requiere("lideres.asignar", limitar=True))):
    """Asigna un líder a la persona. Si ya lo tenía, no cambia nada (se puede repetir sin daño). P solo en las personas
    de su zona o que registró (403 `fuera_de_zona`) y nunca devuelve un líder que A o K le quitaron a esa persona (409
    `lider_quitado`): eso lo deciden ellos."""
    adm = quien.administra
    p = proyeccion.persona_activa(db, pid, {"lideres": 1, "consentimiento": 1, "lideres_quitados": 1,
                                            **proyeccion.CAMPOS_TIPO_VISIBLE})
    proyeccion.exigir_tratable(p, quien, "editar")
    if not adm and not proyeccion.tipo_visible(db, quien, p):  # depende de la zona, no de los líderes que tiene
        raise _prohibido(FUERA_DE_ZONA, codigo="fuera_de_zona", campo="lider_id")
    actuales = [l.get("id") for l in p.get("lideres") or [] if isinstance(l, dict)]
    # Ya lo tenía (aunque después le quitaran la marca de líder). Para quien no administra, uno que no autorizó no sale
    # en su ficha (`lideres_de`): sigue de largo hasta el 422 genérico, como cualquier id, y nunca dice que lo tiene
    if body.lider_id in actuales and (adm or not db.personas.count_documents(
            {"_id": body.lider_id, "consentimiento": "no"}, limit=1)):
        return ficha_respuesta(db, quien, pid)
    # Lo que no depende del líder va antes de `exigir_lider`: si no, que siga de largo (al tope de líderes) en vez del
    # 422 genérico diría sin costo si un id es un líder o concejal
    if len(actuales) >= MAX_LIDERES:
        raise HTTPException(422, f"Una persona puede tener hasta {MAX_LIDERES} líderes")
    # Que sea un líder o concejal antes del 409 de abajo: así nunca dice de quién fue líder una ficha que ya no lo es
    exigir_lider(db, body.lider_id, pid, quien)
    if not adm and body.lider_id in (p.get("lideres_quitados") or []):
        raise HTTPException(409, dict(LIDER_QUITADO))
    # El líder sale con su nombre en la respuesta: cuenta en el presupuesto diario de P (como en `candidatos`)
    acceso.registrar_lecturas(db, quien, [body.lider_id])
    nuevo = {"id": body.lider_id, "asignado_en": bd.ahora(), "asignado_por": quien.usuario,
             "asignado_por_uid": quien.uid}
    # Condicional: dos asignaciones del mismo líder a la vez dejan una sola. Si A o K lo habían quitado, deja de
    # contar como quitado; para P, en cambio, la escritura exige que siga sin estar quitado (A o K pudieron quitarlo
    # mientras tanto)
    condiciones = [{"lideres.id": {"$ne": body.lider_id}}]
    if not adm:
        condiciones.append({"lideres_quitados": {"$ne": body.lider_id}})
    if escribir(db, pid, [{"$set": {"lideres": {"$concatArrays": [{"$ifNull": ["$lideres", []]}, [_lit(nuevo)]]},
                                    "lideres_quitados": {"$setDifference": [{"$ifNull": ["$lideres_quitados", []]},
                                                                            [body.lider_id]]}}},
                          etapa_actualizado(quien)], condiciones):
        bd.auditar(db, quien, "asignar_lider", "persona", pid, {"lider_id": body.lider_id}, campos=["lideres"])
    elif not adm and db.personas.count_documents({"_id": pid, "lideres_quitados": body.lider_id}, limit=1):
        raise HTTPException(409, dict(LIDER_QUITADO))
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


def _consulta_candidatos(q: str) -> dict | None:
    """Lo que busca `candidatos`: con letras, cada palabra (solo sus letras) en `nombre_norm`, 3 letras o más en total,
    como la búsqueda del consultor; solo con dígitos (sin espacios, puntos ni guiones), la cédula exacta, actual o
    anterior, de 5 a 11 dígitos: nunca por partes de un número. None: no hay nada que buscar."""
    digitos = re.sub(r"[\s.\-]", "", q or "")
    if digitos and re.fullmatch(r"[0-9]+", digitos):
        return {"$or": [{"cedula": digitos}, {"cedulas_anteriores": digitos}]} if 5 <= len(digitos) <= 11 else None
    toks = [x for x in (re.sub(r"[^A-Z]", "", t) for t in tx.limpiar(q).split()) if x][:6]
    if len("".join(toks)) < 3:
        return None
    return {"$and": [{"nombre_norm": {"$regex": re.escape(t)}} for t in toks]}


# Va antes de `listar` y de cualquier ruta `/lideres/{id}` que se agregue: «candidatos» no es un id
@r.get("/lideres/candidatos")
def candidatos(q: str = Query("", max_length=120), db: Database = Depends(obtener_db),
               quien: Quien = Depends(requiere("lideres.asignar", limitar=True))):
    """El buscador del «Liderado por»: hasta 12 fichas activas de toda la campaña marcadas como líder o como concejal
    que casan con `q` (por nombre o por la cédula completa, `_consulta_candidatos`), por nombre. Sin conteos ni la
    cédula completa, también para A y K (su vista general es `GET /api/lideres`). Para quien no administra, sin las
    personas que no autorizaron. Cuenta en el presupuesto diario de P."""
    busca = _consulta_candidatos(q)
    if busca is None:
        return {"lideres": []}
    y = [dict(bd.ACTIVA), {"$or": [{t: True} for t in modelo.TIPOS_LIDERAN]}, busca]
    if not quien.administra:
        y.append({"consentimiento": {"$ne": "no"}})
    docs = list(db.personas.find({"$and": y}, {"nombre": 1, "cedula": 1, "lugar_id": 1, "lugar_texto": 1,
                                                **{t: 1 for t in modelo.TIPOS_LIDERAN}})
                .sort([("nombre_norm", ASCENDING), ("_id", ASCENDING)]).limit(MAX_CANDIDATOS))
    acceso.registrar_lecturas(db, quien, [l["_id"] for l in docs])
    lids = {l.get("lugar_id") for l in docs if l.get("lugar_id") is not None}
    lugares = {x["_id"]: x.get("nombre") for x in db.lugares.find({"_id": {"$in": list(lids)}}, {"nombre": 1})} \
        if lids else {}
    return {"lideres": [{"id": l["_id"], "nombre": l.get("nombre"), "tipo": _tipo_lider(l),
                         "lugar": lugares.get(l.get("lugar_id")) or l.get("lugar_texto"),
                         "cedula_ult3": acceso.enmascarar_cedula(l.get("cedula"))} for l in docs]}


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
