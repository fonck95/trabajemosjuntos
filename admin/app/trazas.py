"""Traza de las reuniones en lo que se le hace a una persona.

Cada entrada de la auditoría sobre una persona (`db.auditar` con entidad «persona») que hace alguien del equipo lleva
en `reuniones` los ids de las reuniones en que se hizo. Así la ficha muestra, cambio por cambio, «durante la reunión
X», y la reunión, a quién se intervino mientras duraba (aunque no se haya registrado como asistente).

Una reunión entra en la traza de un cambio si:

1. la ruta la nombra (`reunion`): la asistencia o el retiro de un asistente, la nota escrita en la reunión, el alta de
   una persona en la reunión; o
2. el cambio se hace desde la pantalla de la reunión (el modo reunión manda la cabecera `X-Reunion`, que llega en
   `Quien.reunion`) y quien lo hace puede ver esa reunión (la suya, una abierta al equipo, o A y K todas); o
3. la reunión está en curso (su fecha, entre la hora de inicio y la de fin en hora de Colombia: `modelo.ventana_reunion`)
   y la persona es asistente de ella o quien hace el cambio la creó. Si la persona asiste a una reunión en curso,
   cuentan solo esas; si no, las que creó quien hace el cambio. Una reunión en curso de otra persona del equipo a la
   que la persona no asiste no cuenta: el cambio puede venir de otro lugar.

No llevan traza las lecturas (`SIN_TRAZA`), lo que hace el sistema ni las importaciones (que escriben la auditoría
aparte): subir una planilla durante una reunión no es intervenir a cada persona de la planilla.
La traza nunca impide guardar: si algo falla al calcularla, el cambio se audita sin ella.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from . import modelo

log = logging.getLogger(__name__)

# Acciones sobre una persona que no la cambian (o que la borran: la supresión no deja rastro de reuniones)
SIN_TRAZA = frozenset({"ver_sensibles", "suprimir"})
# Registrar o quitar la asistencia lleva la traza de su reunión, pero no es intervenir a la persona: no cuenta en las
# intervenciones (una persona agregada por error y quitada no aparece como intervenida)
SOLO_ASISTENCIA = ["asistencia", "quitar_asistencia"]
_PROY = {"fecha": 1, "hora": 1, "hora_fin": 1, "creado_por_uid": 1, "abierta_a_equipo": 1}


def _visible(r: dict, quien: Any) -> bool:
    return bool(getattr(quien, "administra", False)) or r.get("creado_por_uid") == getattr(quien, "uid", None) \
        or bool(r.get("abierta_a_equipo"))


def en_curso(db: Database, ts: datetime | None = None) -> list[dict]:
    """Las reuniones en curso en `ts` (ahora, si no se pasa). Una reunión sin hora de fin puede pasar de la medianoche,
    así que se miran las de hoy y las de ayer."""
    ts = ts or datetime.now(timezone.utc)
    hoy = ts.astimezone(modelo.ZONA).date()
    fechas = [hoy.isoformat(), (hoy - timedelta(days=1)).isoformat()]
    return [r for r in db.reuniones.find({"fecha": {"$in": fechas}}, _PROY) if modelo.durante_reunion(r, ts)]


def reuniones_del_cambio(db: Database, quien: Any, accion: str, pid: int, reunion: int | None = None,
                         ts: datetime | None = None) -> list[int]:
    """Los ids (ordenados) de las reuniones en que se hizo `accion` sobre la persona `pid` (ver el docstring del
    módulo). Vacío para el sistema, las lecturas o si algo falla."""
    if quien is None or isinstance(quien, str) or accion in SIN_TRAZA:
        return []
    try:
        ids: set[int] = set()
        if isinstance(reunion, int) and not isinstance(reunion, bool):
            ids.add(reunion)
        pantalla = getattr(quien, "reunion", None)
        if isinstance(pantalla, int) and not isinstance(pantalla, bool) and pantalla not in ids:
            r = db.reuniones.find_one({"_id": pantalla}, _PROY)
            if r is not None and _visible(r, quien):
                ids.add(pantalla)
        curso = en_curso(db, ts)
        if curso:
            p = db.personas.find_one({"_id": pid}, {"asistencias.reunion_id": 1}) or {}
            asiste = {a.get("reunion_id") for a in p.get("asistencias") or [] if isinstance(a, dict)}
            suyas = [r["_id"] for r in curso if r["_id"] in asiste] \
                or [r["_id"] for r in curso if r.get("creado_por_uid") == getattr(quien, "uid", None)]
            ids.update(suyas)
        return sorted(ids)
    except Exception:  # noqa: BLE001 — la traza nunca impide guardar el cambio
        log.exception("No se pudo calcular la traza de reuniones de la persona %s", pid)
        return []


def resumen_reuniones(db: Database, entradas: list[dict]) -> dict[int, dict]:
    """{id: {id, titulo, fecha, hora, hora_fin}} de las reuniones que nombran las `entradas` de auditoría."""
    rids = {r for e in entradas for r in e.get("reuniones") or [] if isinstance(r, int)}
    if not rids:
        return {}
    return {x["_id"]: {"id": x["_id"], "titulo": x.get("titulo"), "fecha": x.get("fecha"), "hora": x.get("hora"),
                       "hora_fin": x.get("hora_fin")}
            for x in db.reuniones.find({"_id": {"$in": sorted(rids)}}, {"titulo": 1, "fecha": 1, "hora": 1, "hora_fin": 1})}


def traza(entrada: dict, reuniones: dict[int, dict]) -> list[dict]:
    """Las reuniones de una entrada de auditoría, cada una con `durante`: si el cambio cayó dentro de su horario (si
    no, se hizo desde la pantalla de la reunión o la nombraba, fuera de hora). Las reuniones borradas no salen."""
    out = []
    for rid in entrada.get("reuniones") or []:
        r = reuniones.get(rid)
        if r is not None:
            out.append({**r, "durante": modelo.durante_reunion(r, entrada.get("ts"))})
    return out


def intervenciones_persona(db: Database, pid: int, asistencias: list[dict] | None) -> list[dict]:
    """Por reunión, lo que se le hizo a la persona `pid` en ella (sin contar registrar o quitar su asistencia):
    [{id, titulo, fecha, hora, hora_fin, cambios, acciones, primera, ultima, asistio}], la más reciente primero."""
    grupos = list(db.auditoria.aggregate([
        {"$match": {"entidad": "persona", "entidad_id": pid, "reuniones.0": {"$exists": True},
                    "accion": {"$nin": SOLO_ASISTENCIA}}},
        {"$unwind": "$reuniones"},
        {"$group": {"_id": "$reuniones", "cambios": {"$sum": 1}, "acciones": {"$addToSet": "$accion"},
                    "primera": {"$min": "$ts"}, "ultima": {"$max": "$ts"}}},
    ]))
    if not grupos:
        return []
    reus = resumen_reuniones(db, [{"reuniones": [g["_id"] for g in grupos]}])
    asiste = {a.get("reunion_id") for a in asistencias or [] if isinstance(a, dict)}
    out = [{**reus[g["_id"]], "cambios": g["cambios"], "acciones": sorted(a for a in g["acciones"] if a),
            "primera": g["primera"], "ultima": g["ultima"], "asistio": g["_id"] in asiste}
           for g in grupos if g["_id"] in reus]
    out.sort(key=lambda x: (x.get("fecha") or "", x.get("ultima") or ""), reverse=True)
    return out


def intervenidas_reunion(db: Database, rid: int) -> dict[int, dict]:
    """{persona_id: {cambios, acciones, primera, ultima}} de las personas a las que se les hizo algo en la reunión (sin
    contar registrar o quitar su asistencia)."""
    out = {}
    for g in db.auditoria.aggregate([
        {"$match": {"reuniones": rid, "entidad": "persona", "accion": {"$nin": SOLO_ASISTENCIA}}},
        {"$group": {"_id": "$entidad_id", "cambios": {"$sum": 1}, "acciones": {"$addToSet": "$accion"},
                    "primera": {"$min": "$ts"}, "ultima": {"$max": "$ts"}}},
    ]):
        if isinstance(g["_id"], int):
            out[g["_id"]] = {"cambios": g["cambios"], "acciones": sorted(a for a in g["acciones"] if a),
                             "primera": g["primera"], "ultima": g["ultima"]}
    return out
