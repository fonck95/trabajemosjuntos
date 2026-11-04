"""Reuniones: agenda, registro de asistentes y lo que se aprende de cada habitante en ellas.

La asistencia vive dentro de cada persona (`asistencias`), así su historial se lee de una vez. Asistir cuenta como
acercamiento (4.4): agregar a alguien crea un acercamiento automático y quitarlo (o borrar la reunión) lo anula.

* A y K ven y editan todas; A (o K) marca `abierta_a_equipo`. P ve las suyas y las abiertas al equipo y, de las demás,
  solo cuántas hay (cabecera `X-Reuniones-Ajenas`). La lista de asistentes usa la proyección de fila del rol.
* Toda escritura sobre la persona exige que la ficha siga activa y que se pueda tratar (`exigir_tratable`).
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from .. import acceso, proyeccion
from .. import db as bd
from ..acceso import Quien, requiere
from ..seguridad import obtener_db
from . import acercamientos as ac
from .personas import fecha_iso, mapa_lugares

r = APIRouter(prefix="/api/reuniones", tags=["reuniones"])


class ReunionIn(BaseModel):
    titulo: str | None = Field(None, min_length=3, max_length=160)
    fecha: str | None = None
    hora: str | None = Field(None, max_length=5)
    lugar_texto: str | None = Field(None, max_length=160)
    lugar_id: int | None = None
    lat: float | None = Field(None, ge=6.3, le=7.5)
    lon: float | None = Field(None, ge=-74.6, le=-73.6)
    tema: str | None = Field(None, max_length=160)
    descripcion: str | None = Field(None, max_length=4000)
    compromisos: str | None = Field(None, max_length=4000)
    abierta_a_equipo: bool | None = None

    @field_validator("fecha")
    @classmethod
    def _f(cls, v):
        return fecha_iso(v)  # vacía la rechazan crear y editar («necesita título y fecha»)

    @field_validator("titulo")
    @classmethod
    def _t(cls, v):
        if v is not None and len(v.strip()) < 3:
            raise ValueError("El título necesita al menos 3 letras")
        return v.strip() if v is not None else None


def _propia_o_abierta(x: dict, quien: Quien) -> bool:
    return quien.administra or x.get("creado_por_uid") == quien.uid or bool(x.get("abierta_a_equipo"))


def _cargar(db: Database, rid: int, quien: Quien, propia: bool = False) -> dict:
    """La reunión, si el rol puede verla (P: suyas o abiertas al equipo; con `propia`, solo las suyas)."""
    x = db.reuniones.find_one({"_id": rid})
    if x is None:
        raise HTTPException(404, "No existe")
    if not quien.administra:
        if propia and x.get("creado_por_uid") != quien.uid:
            raise HTTPException(403, {"mensaje": "Solo puede cambiar sus propias reuniones", "codigo": "permiso"})
        if not _propia_o_abierta(x, quien):
            raise HTTPException(403, {"mensaje": "Esa reunión no es suya ni está abierta al equipo", "codigo": "permiso"})
    return x


def _reunion(db: Database, rid: int, quien: Quien) -> dict:
    x = _cargar(db, rid, quien)
    adm = quien.administra
    campos = ("titulo", "fecha", "hora", "lugar_texto", "lugar_id", "lat", "lon", "tema", "descripcion", "compromisos",
              "abierta_a_equipo", "creado_en", "actualizado_en", "creado_por_uid")
    d = {k: x.get(k) for k in campos}
    if adm:
        d["creado_por"] = x.get("creado_por")
    d["id"] = rid
    d["abierta_a_equipo"] = bool(x.get("abierta_a_equipo"))
    d["propia"] = x.get("creado_por_uid") == quien.uid
    lg = db.lugares.find_one({"_id": x.get("lugar_id")}, {"nombre": 1}) if x.get("lugar_id") else None
    d["lugar_nombre"] = (lg or {}).get("nombre")
    ctx = proyeccion.contexto(db)
    docs, extra, necesidades = [], [], Counter()
    for p in db.personas.find({**bd.ACTIVA, "asistencias.reunion_id": rid},
                              {**{c: 1 for c in proyeccion.CAMPOS_PARA_FILA if not c.startswith("asistencias")},
                               "asistencias": 1, "etiquetas": 1}):
        a = next(a for a in p["asistencias"] if a["reunion_id"] == rid)
        ets = [ctx.etiquetas[e] for e in p.get("etiquetas", []) if e in ctx.etiquetas
               and (adm or e not in ctx.sensibles_et)]
        no = not adm and p.get("consentimiento") == "no"
        if not no:
            necesidades.update(e["nombre"] for e in ets if e.get("grupo") == "necesidad")
        docs.append(proyeccion.fila_completa(p, ctx))
        extra.append({"rol": a.get("rol"), "creado_en": a.get("creado_en"),
                      **({} if no else {"etiquetas": [e["nombre"] for e in ets]}),
                      **({"nota": a.get("nota")} if adm else {})})
    acceso.registrar_lecturas(db, quien, [f["id"] for f in docs])
    asist = [{**f, **e} for f, e in zip(proyeccion.filas_para(quien, docs), extra)]
    # Con la misma marca de segundo, el último registrado primero (el orden de llegada desempata)
    d["asistentes"] = [a for _, a in sorted(enumerate(asist), key=lambda x: (x[1]["creado_en"] or "", x[0]), reverse=True)]
    d["necesidades"] = [{"nombre": n, "n": c} for n, c in necesidades.most_common()]
    return d


@r.get("")
def listar(response: Response, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("reuniones.ver"))):
    conteo = Counter()
    nuevos = Counter()  # personas que se registraron en esa reunión (no en otra a la que también asistieron)
    proy = {"asistencias.reunion_id": 1, "asistencias.creado_en": 1, "fuentes": 1, "reunion_origen": 1}
    for p in db.personas.find({**bd.ACTIVA, "asistencias.0": {"$exists": True}}, proy):
        for a in p["asistencias"]:
            conteo[a["reunion_id"]] += 1
        origen = p.get("reunion_origen")
        if origen is None and "reunion" in p.get("fuentes", []):
            # Fichas anteriores a `reunion_origen`: la reunión de su primera asistencia
            origen = min(p["asistencias"], key=lambda a: a.get("creado_en") or "")["reunion_id"]
        if origen is not None and any(a["reunion_id"] == origen for a in p["asistencias"]):
            nuevos[origen] += 1
    lugares = mapa_lugares(db)
    todas = list(db.reuniones.find().sort([("fecha", -1), ("_id", -1)]))
    visibles = [x for x in todas if _propia_o_abierta(x, quien)]
    if not quien.administra:  # de las demás, P solo ve cuántas hay
        response.headers["X-Reuniones-Ajenas"] = str(len(todas) - len(visibles))
    return [{"id": x["_id"], "titulo": x["titulo"], "fecha": x["fecha"], "hora": x.get("hora"), "tema": x.get("tema"),
             "lugar": (lugares.get(x.get("lugar_id")) or {}).get("nombre") or x.get("lugar_texto"), "lat": x.get("lat"),
             "lon": x.get("lon"), "asistentes": conteo[x["_id"]], "nuevos": nuevos[x["_id"]],
             "abierta_a_equipo": bool(x.get("abierta_a_equipo")), "propia": x.get("creado_por_uid") == quien.uid}
            for x in visibles]


def _ubicar_desde_lugar(db: Database, datos: dict) -> None:
    if not datos.get("lugar_id"):
        return
    lg = db.lugares.find_one({"_id": datos["lugar_id"]}, {"nombre": 1, "lat": 1, "lon": 1})
    if lg is None:
        raise HTTPException(422, "Lugar no existe")
    if datos.get("lat") is None:
        datos["lat"], datos["lon"] = lg.get("lat"), lg.get("lon")
    if not datos.get("lugar_texto"):  # sin sitio escrito, el historial de la ficha muestra el barrio o vereda
        datos["lugar_texto"] = lg["nombre"]


def _exigir_apertura(body: ReunionIn, quien: Quien) -> None:
    if body.abierta_a_equipo is not None and not quien.administra:
        raise HTTPException(403, {"mensaje": "Solo el administrador abre una reunión al equipo", "codigo": "permiso",
                                  "campo": "abierta_a_equipo"})


@r.post("", status_code=201)
def crear(body: ReunionIn, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("reuniones.crear"))):
    if not body.titulo or not body.fecha:
        raise HTTPException(422, "La reunión necesita título y fecha")
    _exigir_apertura(body, quien)
    datos = {k: None for k in ReunionIn.model_fields} | body.model_dump(exclude_none=True)
    datos["abierta_a_equipo"] = bool(datos.get("abierta_a_equipo"))
    _ubicar_desde_lugar(db, datos)
    rid = bd.siguiente_id(db, "reuniones")
    db.reuniones.insert_one({"_id": rid, **datos, "creado_por": quien.usuario, "creado_por_uid": quien.uid,
                             "creado_en": bd.ahora(), "actualizado_en": bd.ahora()})
    bd.auditar(db, quien, "crear", "reunion", rid, datos)
    return _reunion(db, rid, quien)


@r.get("/{rid}")
def ver(rid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("reuniones.ver"))):
    return _reunion(db, rid, quien)


@r.patch("/{rid}")
def editar(rid: int, body: ReunionIn, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("reuniones.crear"))):
    _cargar(db, rid, quien, propia=True)
    _exigir_apertura(body, quien)
    antes = _reunion(db, rid, quien)
    datos = body.model_dump(exclude_unset=True)
    if any(k in datos and not datos[k] for k in ("titulo", "fecha")):
        raise HTTPException(422, "La reunión necesita título y fecha")
    if "lugar_id" in datos:
        if "lat" not in datos:
            datos["lat"] = datos["lon"] = None
        if "lugar_texto" not in datos and antes.get("lugar_texto") == antes.get("lugar_nombre"):
            datos["lugar_texto"] = None  # el sitio era el nombre del barrio anterior: cambia con él
        _ubicar_desde_lugar(db, datos)
    if datos:
        db.reuniones.update_one({"_id": rid}, {"$set": {**datos, "actualizado_en": bd.ahora()}})
        bd.auditar(db, quien, "editar", "reunion", rid, datos)
    return _reunion(db, rid, quien)


@r.delete("/{rid}")
def borrar(rid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    _cargar(db, rid, quien)
    for p in db.personas.find({"asistencias.reunion_id": rid}, {"_id": 1}):
        ac.anular_automatico(db, p["_id"], rid, quien, "Se borró la reunión")
    db.reuniones.delete_one({"_id": rid})
    db.personas.update_many({"asistencias.reunion_id": rid}, {"$pull": {"asistencias": {"reunion_id": rid}}})
    db.personas.update_many({"notas.reunion_id": rid}, {"$set": {"notas.$[n].reunion_id": None}},
                            array_filters=[{"n.reunion_id": rid}])
    bd.auditar(db, quien, "borrar", "reunion", rid, None)
    return {"ok": True}


class AsistenteIn(BaseModel):
    persona_id: int
    rol: str | None = Field(None, max_length=60)
    nota: str | None = Field(None, max_length=1000)


@r.post("/{rid}/asistentes", status_code=201)
def agregar(rid: int, body: AsistenteIn, request: Request, db: Database = Depends(obtener_db),
            quien: Quien = Depends(requiere("reuniones.asistentes"))):
    previa = acceso.idempotencia_previa(db, quien, request)
    if previa is not None:
        return previa
    reu = _cargar(db, rid, quien)
    p = proyeccion.persona_activa(db, body.persona_id, {"asistencias": 1, "consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "asistencia")
    ya = any(a["reunion_id"] == rid for a in p.get("asistencias", []))
    if ya:
        cambios = {f"asistencias.$[a].{k}": v for k, v in (("rol", body.rol), ("nota", body.nota)) if v}
        if cambios:
            db.personas.update_one({"_id": body.persona_id, **bd.ACTIVA}, {"$set": cambios},
                                   array_filters=[{"a.reunion_id": rid}])
    else:
        res = db.personas.update_one({"_id": body.persona_id, **bd.ACTIVA, "asistencias.reunion_id": {"$ne": rid}}, {
            "$push": {"asistencias": {"reunion_id": rid, "rol": body.rol, "nota": body.nota, "creado_en": bd.ahora()}},
            "$max": {"ultimo_contacto": reu["fecha"]},
            "$set": {"actualizado_en": bd.ahora(), "actualizado_por": {"uid": quien.uid, "usuario": quien.usuario,
                                                                        "rol": quien.rol, "ts": bd.ahora()}}})
        if not res.matched_count and db.personas.count_documents({"_id": body.persona_id, **bd.ACTIVA}, limit=1) == 0:
            raise HTTPException(409, "La ficha se unió o se suprimió")
        ac.crear_automatico(db, body.persona_id, reu, quien)
    bd.auditar(db, quien, "asistencia", "persona", body.persona_id, {"reunion_id": rid})
    cuerpo = _reunion(db, rid, quien)
    acceso.idempotencia_guardar(db, quien, request, 201, cuerpo, persona_id=body.persona_id)
    return cuerpo


@r.delete("/{rid}/asistentes/{pid}")
def quitar(rid: int, pid: int, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("reuniones.asistentes"))):
    _cargar(db, rid, quien)
    p = proyeccion.persona_activa(db, pid, {"consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "asistencia")
    res = db.personas.update_one({"_id": pid, **bd.ACTIVA}, {"$pull": {"asistencias": {"reunion_id": rid}}})
    if not res.matched_count:
        raise HTTPException(409, "La ficha se unió o se suprimió")
    ac.anular_automatico(db, pid, rid, quien, "Se quitó de la reunión")
    bd.auditar(db, quien, "quitar_asistencia", "persona", pid, {"reunion_id": rid})
    return _reunion(db, rid, quien)


@r.get("/{rid}/asistentes.csv")
def exportar(rid: int, incluir_sin_autorizacion: int = 0, db: Database = Depends(obtener_db),
             quien: Quien = Depends(requiere("exportar"))):
    from .sistema import celda
    d = _reunion(db, rid, quien)
    autorizacion = {p["_id"]: p.get("consentimiento") for p in
                    db.personas.find({"asistencias.reunion_id": rid}, {"consentimiento": 1})}
    # Quien dijo que no autoriza el tratamiento de sus datos no sale, salvo que se pida
    filas = [a for a in d["asistentes"] if incluir_sin_autorizacion or autorizacion.get(a["id"]) != "no"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Nombre", "Cédula", "Teléfono", "Barrio/Vereda", "Rol", "Nota", "Necesidades", "Autorización de datos"])
    for a in filas:
        w.writerow([celda(v) for v in (a["nombre"], a.get("cedula") or "", a.get("telefono") or "", a.get("lugar") or "",
                                        a.get("rol") or "", a.get("nota") or "", ", ".join(a.get("etiquetas") or []),
                                        autorizacion.get(a["id"]) or "")])
    bd.auditar(db, quien, "exportar_asistentes", "reunion", rid,
               {"filas": len(filas), "excluidas_sin_autorizacion": len(d["asistentes"]) - len(filas)})
    nombre = re.sub(r"[^A-Za-z0-9]+", "-", d.get("titulo") or "reunion")[:40]
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="asistentes-{d["fecha"]}-{nombre}.csv"'})
