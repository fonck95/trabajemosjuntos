"""Sesión, importación, exportación, campos personalizados, etiquetas y auditoría."""
from __future__ import annotations

import io
import re
import shutil
import tempfile
from pathlib import Path
from typing import Literal

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from pydantic import BaseModel, Field
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import db as bd
from ..pipeline import importar as imp
from ..pipeline import texto as tx
from ..seguridad import (Admin, USUARIO_DESCONOCIDO, cerrar_sesion, crear_sesion, credenciales_validas,
                         dispositivo_conocido, ip_de, marcar_dispositivo, obtener_db, requiere_admin,
                         reservar_intento, resolver_intento, sesion_actual, usuario_correcto)
from .filtros import Filtros, filtro, filtros_query
from .personas import mapa_lugares

r = APIRouter(prefix="/api", tags=["sistema"])


class LoginIn(BaseModel):
    usuario: str = Field(..., max_length=120)
    clave: str = Field(..., max_length=256)


@r.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Database = Depends(obtener_db)):
    cfg = request.app.state.cfg
    if not cfg.usuario or not cfg.clave:
        raise HTTPException(503, "El panel no tiene credenciales: defina las variables ADMIN y password")
    ip = ip_de(request)
    iid, espera = reservar_intento(db, ip, conocido=dispositivo_conocido(cfg, request))
    if iid is None:
        texto = f"{espera} segundos" if espera < 120 else f"{-(-espera // 60)} minutos"
        raise HTTPException(429, f"Demasiados intentos. Espere {texto}.", headers={"Retry-After": str(espera)})
    usuario = body.usuario.strip()
    ok = credenciales_validas(cfg, usuario, body.clave)
    resolver_intento(db, iid, ip, ok)
    if not ok:
        # Lo escrito como usuario no se guarda (a veces es la clave): solo si coincidía con el configurado
        correcto = usuario_correcto(cfg, usuario)
        bd.auditar(db, cfg.usuario if correcto else USUARIO_DESCONOCIDO, "ingreso_fallido",
                   detalle={"usuario_correcto": correcto}, ip=ip)
        raise HTTPException(401, "Usuario o clave incorrectos")
    csrf = crear_sesion(db, cfg, response, cfg.usuario, request)
    marcar_dispositivo(cfg, response)
    bd.auditar(db, cfg.usuario, "ingreso", ip=ip)
    return {"usuario": cfg.usuario, "csrf": csrf}


@r.post("/logout")
def logout(request: Request, response: Response, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    cerrar_sesion(db, request, response)
    bd.auditar(db, adm.usuario, "salida", ip=adm.ip)
    return {"ok": True}


@r.get("/yo")
def yo(request: Request, db: Database = Depends(obtener_db)):
    s = sesion_actual(db, request)
    cfg = request.app.state.cfg
    if s is None:
        raise HTTPException(401, {"mensaje": "Inicie sesión", "configurado": bool(cfg.usuario and cfg.clave)})
    return {"usuario": s["usuario"], "csrf": s["csrf"], "expira": s["expira"].isoformat()}


# ───────────────────────────── Importación y exportación ─────────────────────────────

@r.post("/importar")
async def importar(request: Request, archivos: list[UploadFile] = File(...), db: Database = Depends(obtener_db),
                   adm: Admin = Depends(requiere_admin)):
    cfg = request.app.state.cfg
    tmp = Path(tempfile.mkdtemp(prefix="panel-import-"))
    try:
        rutas, nombres = [], []
        if len(archivos) > 6:
            raise HTTPException(422, "Suba como máximo 6 archivos por importación")
        for i, a in enumerate(archivos):
            if not (a.filename or "").lower().endswith((".xlsx", ".xlsm")):
                raise HTTPException(422, f"{a.filename}: solo se aceptan archivos .xlsx")
            destino = tmp / f"{i}.xlsx"
            total = 0
            with destino.open("wb") as f:
                while bloque := await a.read(1 << 20):
                    total += len(bloque)
                    if total > cfg.max_subida_mb << 20:
                        raise HTTPException(413, f"{a.filename} supera {cfg.max_subida_mb} MB")
                    f.write(bloque)
            rutas.append(destino)
            nombres.append(Path(a.filename or f"archivo-{i}.xlsx").name[:120])
        try:
            res = await run_in_threadpool(imp.importar, db, rutas, adm.usuario, nombres)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return res.dict()
    finally:
        # Los Excel no se guardan: solo quedan los datos en la base
        shutil.rmtree(tmp, ignore_errors=True)


@r.get("/importaciones")
def importaciones(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    return [{"id": x["_id"], "ts": x["ts"], "usuario": x.get("usuario"), "archivo": x.get("archivo"), "tipo": x.get("tipo"),
             "resumen": x.get("resumen") or {}} for x in db.importaciones.find().sort("_id", -1).limit(30)]


COLUMNAS = [("id", "ID"), ("nombre", "Nombre"), ("cedula", "Cédula"), ("sexo", "Sexo"), ("edad", "Edad"),
            ("telefono", "Teléfono"), ("telefono2", "Teléfono 2"), ("correo", "Correo"), ("direccion", "Dirección original"),
            ("direccion_norm", "Dirección normalizada"), ("lugar", "Barrio / vereda"), ("lugar_tipo", "Tipo de lugar"),
            ("zona", "Zona"), ("lat", "Latitud"), ("lon", "Longitud"), ("geo_precision", "Precisión"), ("ficha", "Ficha"),
            ("puesto_votacion", "Puesto de votación"), ("mesa", "Mesa"), ("ocupacion", "Ocupación"),
            ("nivel_educativo", "Nivel educativo"), ("personas_hogar", "Personas en el hogar"), ("lider", "Líder"),
            ("etiquetas", "Necesidades / etiquetas"), ("listas", "Listas"), ("reuniones", "Reuniones"),
            ("consentimiento", "Autorización de datos"), ("completitud", "Completitud %"), ("fuentes", "Fuentes"),
            ("ultimo_contacto", "Último contacto")]


def celda(v):
    """Quita los caracteres de control que XLSX no admite (con uno solo fallaba toda la exportación) y evita que
    Excel interprete un texto como fórmula (inyección en hojas de cálculo)."""
    if isinstance(v, str):
        v = ILLEGAL_CHARACTERS_RE.sub("", v)  # antes de mirar el primer carácter: «\x01=X» queda «'=X»
        if v[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + v
    return v


def con_autorizacion(q: dict, incluir_sin_autorizacion: int) -> dict:
    """Quien dijo que no autoriza el tratamiento de sus datos no sale en las exportaciones, salvo que se pida."""
    return q if incluir_sin_autorizacion else {"$and": [q, {"consentimiento": {"$ne": "no"}}]}


@r.get("/exportar.xlsx")
def exportar(f: Filtros = Depends(filtros_query), incluir_sin_autorizacion: int = 0, db: Database = Depends(obtener_db),
             adm: Admin = Depends(requiere_admin)):
    campos = list(db.campos.find({"activo": True}).sort([("orden", 1), ("_id", 1)]))
    lugares = mapa_lugares(db)
    etiquetas = {e["_id"]: e["nombre"] for e in db.etiquetas.find()}
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Base única")
    ws.append([t for _, t in COLUMNAS] + [celda(c["etiqueta"]) for c in campos])
    n = 0
    q = filtro(f)
    excluidas = 0 if incluir_sin_autorizacion else db.personas.count_documents({"$and": [q, {"consentimiento": "no"}]})
    proy = {"tramites": 0, "notas": 0, "origen": 0}
    for p in db.personas.find(con_autorizacion(q, incluir_sin_autorizacion), proy).sort("nombre_norm", 1):
        lg = lugares.get(p.get("lugar_id")) or {}
        valores = {**p, "id": p["_id"], "lugar": lg.get("nombre") or p.get("lugar_texto"), "lugar_tipo": lg.get("tipo"),
                   "etiquetas": ", ".join(etiquetas.get(e, "") for e in p.get("etiquetas", [])),
                   "listas": "; ".join(p.get("listas", [])), "reuniones": len(p.get("asistencias", [])),
                   "fuentes": ", ".join(p.get("fuentes", [])), "lider": "Sí" if p.get("lider") else ""}
        extra = p.get("extra") or {}
        ws.append([celda(valores.get(k)) for k, _ in COLUMNAS] + [celda(extra.get(c["clave"])) for c in campos])
        n += 1
    buf = io.BytesIO()
    wb.save(buf)
    bd.auditar(db, adm.usuario, "exportar", None, None, {"filas": n, "filtros": f.model_dump(exclude_none=True),
                                                         "excluidas_sin_autorizacion": excluidas}, adm.ip)
    return StreamingResponse(iter([buf.getvalue()]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="base-unica-yondo-{bd.ahora()[:10]}.xlsx"'})


# ───────────────────────────── Campos personalizados y etiquetas ─────────────────────────────

class CampoIn(BaseModel):
    etiqueta: str | None = Field(None, min_length=2, max_length=60)
    tipo: Literal["texto", "numero", "si_no", "opcion", "fecha"] | None = None
    opciones: list[str] | None = None
    orden: int | None = None
    activo: bool | None = None


@r.get("/catalogos")
def catalogos(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    from collections import Counter
    uso = Counter(e for p in db.personas.find({**bd.ACTIVA, "etiquetas.0": {"$exists": True}}, {"etiquetas": 1}) for e in p["etiquetas"])
    return {
        "campos": [{"id": c["_id"], **{k: v for k, v in c.items() if k != "_id"}} for c in db.campos.find().sort([("orden", 1), ("_id", 1)])],
        "etiquetas": [{"id": e["_id"], "nombre": e["nombre"], "grupo": e["grupo"], "orden": e.get("orden", 0), "n": uso[e["_id"]]}
                      for e in db.etiquetas.find().sort([("grupo", 1), ("orden", 1), ("nombre", 1)])],
        "listas": sorted(x for x in db.personas.distinct("listas", bd.ACTIVA) if x),
        "lugares": [{"id": l["_id"], "nombre": l["nombre"], "tipo": l["tipo"], "zona": l["zona"]}
                    for l in db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1}).sort("nombre", 1)],
    }


@r.post("/campos", status_code=201)
def crear_campo(body: CampoIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not body.etiqueta or not body.tipo:
        raise HTTPException(422, "Nombre y tipo son obligatorios")
    clave = re.sub(r"[^a-z0-9]+", "_", tx.sin_tildes(body.etiqueta).lower()).strip("_")[:40] or "campo"
    base, n = clave, 2
    while db.campos.find_one({"clave": clave}, {"_id": 1}):
        clave, n = f"{base}_{n}", n + 1
    cid = bd.siguiente_id(db, "campos")
    db.campos.insert_one({"_id": cid, "clave": clave, "etiqueta": body.etiqueta.strip(), "tipo": body.tipo,
                          "opciones": [o.strip() for o in body.opciones or [] if o.strip()], "orden": body.orden or cid,
                          "activo": True})
    bd.auditar(db, adm.usuario, "crear_campo", "campo", cid, body.model_dump(), adm.ip)
    return {"clave": clave}


@r.patch("/campos/{cid}")
def editar_campo(cid: int, body: CampoIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    datos = body.model_dump(exclude_unset=True)
    if datos:
        db.campos.update_one({"_id": cid}, {"$set": datos})
        bd.auditar(db, adm.usuario, "editar_campo", "campo", cid, datos, adm.ip)
    return {"ok": True}


class EtiquetaIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    grupo: Literal["necesidad", "interes", "rol"] = "necesidad"


@r.post("/etiquetas", status_code=201)
def crear_etiqueta(body: EtiquetaIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    eid = bd.siguiente_id(db, "etiquetas")
    try:
        db.etiquetas.insert_one({"_id": eid, "nombre": body.nombre.strip(), "grupo": body.grupo, "orden": eid})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe")
    bd.auditar(db, adm.usuario, "crear_etiqueta", "etiqueta", eid, body.model_dump(), adm.ip)
    return {"id": eid}


@r.delete("/etiquetas/{eid}")
def borrar_etiqueta(eid: int, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    db.etiquetas.delete_one({"_id": eid})
    db.personas.update_many({"etiquetas": eid}, {"$pull": {"etiquetas": eid}})
    bd.recalcular_completitud(db)
    bd.auditar(db, adm.usuario, "borrar_etiqueta", "etiqueta", eid, None, adm.ip)
    return {"ok": True}


@r.get("/auditoria")
def auditoria(pagina: int = 1, db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    pagina = max(1, pagina)
    filas = [{k: a.get(k) for k in ("ts", "usuario", "accion", "entidad", "entidad_id", "detalle", "ip")}
             for a in db.auditoria.find().sort("_id", -1).skip((pagina - 1) * 100).limit(100)]
    return {"total": db.auditoria.estimated_document_count(), "filas": filas}
