"""Sesión, importación, exportación, catálogos, campos personalizados, etiquetas y auditoría."""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from pydantic import BaseModel, Field
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import acceso, modelo
from .. import db as bd
from ..acceso import Quien, requiere
from ..pipeline import importar as imp
from ..pipeline import texto as tx
from ..seguridad import (ROLES_USUARIO, USUARIO_DESCONOCIDO, base_de, cerrar_sesion, crear_sesion, credenciales_validas,
                         dispositivo_valido, ip_de, marcar_dispositivo, obtener_db, reservar_intento, resolver_intento,
                         sesion_actual, usuario_correcto)
from .filtros import Filtros, filtro, filtros_query
from .personas import mapa_lugares

r = APIRouter(prefix="/api", tags=["sistema"])

ALERTA_FALLOS = 20  # fallos de un mismo nombre en 24 h que generan la alerta de ingresos (una vez por día)


class LoginIn(BaseModel):
    usuario: str = Field(..., max_length=120)
    clave: str = Field(..., max_length=256)


def datos_sesion(cfg, s: dict, csrf: str | None = None, u: dict | None = None, ajustes: dict | None = None) -> dict:
    """Lo que devuelven /api/login y /api/yo: quién es, su rol y permisos, el CSRF y lo que tiene pendiente."""
    expira = s["expira"].isoformat() if isinstance(s.get("expira"), datetime) else s.get("expira")
    if u is None:
        q = acceso.quien_admin(cfg)
        return {"uid": 0, "usuario": q.usuario, "nombre": q.nombre, "rol": "admin", "permisos": sorted(q.permisos),
                "csrf": csrf or s["csrf"], "expira": expira, "debe_cambiar_clave": False,
                "compromiso_pendiente": False, "compromiso": None}
    aj = ajustes or {}
    vigente = aj.get("compromiso_version")
    return {"uid": u["_id"], "usuario": u["usuario"], "nombre": u.get("nombre"), "rol": u["rol"],
            "permisos": sorted(acceso.PERMISOS.get(u["rol"], ())), "csrf": csrf or s["csrf"], "expira": expira,
            "debe_cambiar_clave": bool(u.get("debe_cambiar_clave")),
            "compromiso_pendiente": u.get("compromiso_version") != vigente,
            "compromiso": {"version": vigente, "puntos": acceso.texto_compromiso(vigente),
                           "aceptado": u.get("compromiso_version") == vigente, "aceptado_en": u.get("compromiso_en")}}


def _inicio_del_dia_utc() -> str:
    hoy = datetime.combine(modelo.hoy_local(), datetime.min.time(), tzinfo=modelo.ZONA)
    return hoy.astimezone(timezone.utc).isoformat()


def _alerta_ingresos(db: Database, nombre_h: str, cuenta: str, uid: int | None) -> None:
    """Más de 20 fallos de un mismo nombre en 24 h: se audita `alerta_ingresos` una vez por día, sin cambiar la
    respuesta (no hay bloqueo por nombre). `cuenta` nunca es lo escrito: es la cuenta que existe o «desconocido»."""
    desde = datetime.now(timezone.utc) - timedelta(hours=24)
    n = db.intentos.count_documents({"nombre_h": nombre_h, "ok": False, "ts": {"$gt": desde}})
    if n <= ALERTA_FALLOS:
        return
    if db.auditoria.find_one({"accion": "alerta_ingresos", "nombre_h": nombre_h, "ts": {"$gte": _inicio_del_dia_utc()}},
                             {"_id": 1}):
        return
    bd.auditar(db, "sistema", "alerta_ingresos", "usuario" if uid is not None else None, uid,
               {"fallos": n, "usuario": cuenta}, nombre_h=nombre_h)


@r.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Database = Depends(obtener_db)):
    cfg = request.app.state.cfg
    if not cfg.usuario or not cfg.clave:
        raise HTTPException(503, "El panel no tiene credenciales: defina las variables ADMIN y password")
    ip = ip_de(request)
    nombre = body.usuario.strip()
    nh = acceso.nombre_h(db, nombre)
    u = db.usuarios.find_one({"usuario": nombre.lower()}) if nombre else None
    # La cuenta que se intenta: el administrador (comparación exacta, como credenciales_validas), un usuario o ninguna
    cuenta = 0 if nombre == cfg.usuario else (u["_id"] if u else None)
    marca = dispositivo_valido(cfg, request, cuenta, (u or {}).get("version"))
    marca_h = hashlib.sha256(marca.encode()).hexdigest() if marca else None
    iid, espera = reservar_intento(db, ip, conocido=bool(marca), marca_h=marca_h, nombre_h=nh)
    if iid is None:
        texto = f"{espera} segundos" if espera < 120 else f"{-(-espera // 60)} minutos"
        raise HTTPException(429, f"Demasiados intentos. Espere {texto}.", headers={"Retry-After": str(espera)})
    try:
        # Siempre las dos comprobaciones, exista o no el usuario: la respuesta tarda lo mismo
        ok_admin = credenciales_validas(cfg, nombre, body.clave)
        ok_clave = acceso.verificar_clave((u or {}).get("clave"), body.clave)
    except HTTPException:
        db.intentos.delete_one({"_id": iid})  # sin turno para comprobar la clave (503): no cuenta como intento
        raise
    # Activo y clave temporal vigente se miran después de la clave: la respuesta es el mismo 401
    ok_usuario = (not ok_admin and u is not None and ok_clave and u.get("activo") is True
                  and u.get("rol") in ROLES_USUARIO and not acceso.clave_vencida(u))
    resolver_intento(db, iid, ip, ok_admin or ok_usuario, nh)
    if not (ok_admin or ok_usuario):
        # Lo escrito como usuario no se guarda (a veces es la clave): solo la cuenta, si existe
        correcto = usuario_correcto(cfg, nombre)
        de_usuario = u is not None and not correcto
        cuenta_txt = cfg.usuario if correcto else (u["usuario"] if u else USUARIO_DESCONOCIDO)
        bd.auditar(db, cuenta_txt, "ingreso_fallido", "usuario" if de_usuario else None, u["_id"] if de_usuario else None,
                   detalle={"usuario_correcto": correcto or de_usuario}, ip=ip)
        _alerta_ingresos(db, nh, cuenta_txt, 0 if correcto else (u["_id"] if u else None))
        raise HTTPException(401, "Usuario o clave incorrectos")
    if ok_admin:
        csrf = crear_sesion(db, cfg, response, cfg.usuario, request)
        marcar_dispositivo(cfg, response, base_de(request))
        bd.auditar(db, acceso.quien_admin(cfg, ip), "ingreso")
        return datos_sesion(cfg, db.sesiones.find_one({"csrf": csrf}, {"expira": 1}) or {}, csrf)
    aj = modelo.leer_ajustes(db)
    csrf = crear_sesion(db, cfg, response, u["usuario"], request, uid=u["_id"], rol=u["rol"], version=u.get("version"),
                        horas=aj["sesion"].get("horas_max"))
    marcar_dispositivo(cfg, response, base_de(request), u["_id"], u.get("version"))
    db.usuarios.update_one({"_id": u["_id"]}, {"$set": {"ultimo_ingreso": bd.ahora()}})
    q = Quien(uid=u["_id"], usuario=u["usuario"], nombre=u.get("nombre"), rol=u["rol"], ip=ip)
    bd.auditar(db, q, "ingreso")
    return datos_sesion(cfg, db.sesiones.find_one({"csrf": csrf}, {"expira": 1}) or {}, csrf, u, aj)


@r.post("/logout")
def logout(request: Request, response: Response, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("cuenta"))):
    cerrar_sesion(db, request, response)
    bd.auditar(db, quien, "salida")
    return {"ok": True}


@r.get("/yo")
def yo(request: Request, db: Database = Depends(obtener_db)):
    s = sesion_actual(db, request)
    cfg = request.app.state.cfg
    if s is None:
        raise HTTPException(401, {"mensaje": "Inicie sesión", "configurado": bool(cfg.usuario and cfg.clave)})
    return datos_sesion(cfg, s, None, s.get("_usuario"), s.get("_ajustes"))


# ───────────────────────────── Importación y exportación ─────────────────────────────

@r.post("/importar")
async def importar(request: Request, archivos: list[UploadFile] = File(...), capturado_por: int | None = Form(None),
                   db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("importar"))):
    cfg = request.app.state.cfg
    if capturado_por is not None:
        planillero = await run_in_threadpool(db.usuarios.find_one, {"_id": capturado_por, "rol": "planillero"}, {"_id": 1})
        if planillero is None:
            raise HTTPException(422, "«Capturado por» debe ser un planillero")
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
            res = await run_in_threadpool(imp.importar, db, rutas, adm.usuario, nombres, quien=adm,
                                          capturado_por=capturado_por)
        except Exception as e:
            # La importación tiene un turno: otra en curso responde 409 (la excepción trae codigo="importando")
            if getattr(e, "codigo", None) == "importando":
                raise HTTPException(409, {"mensaje": str(e) or "Ya hay una importación en curso. Espere a que termine.",
                                          "codigo": "importando"})
            if isinstance(e, ValueError):
                raise HTTPException(422, str(e))
            raise
        return res.dict()
    finally:
        # Los Excel no se guardan: solo quedan los datos en la base
        shutil.rmtree(tmp, ignore_errors=True)


@r.get("/importaciones")
def importaciones(db: Database = Depends(obtener_db), _: Quien = Depends(requiere("importar"))):
    return [{"id": x["_id"], "ts": x["ts"], "usuario": x.get("usuario"), "archivo": x.get("archivo"), "tipo": x.get("tipo"),
             "resumen": x.get("resumen") or {}, "capturado_por": x.get("capturado_por")}
            for x in db.importaciones.find().sort("_id", -1).limit(30)]


COLUMNAS = [
    ("id", "ID"), ("nombre", "Nombre"), ("tipo_documento", "Tipo de documento"), ("cedula", "Cédula"),
    ("cedula_verificada", "Cédula verificada"), ("sexo", "Sexo"), ("edad", "Edad"),
    ("fecha_nacimiento", "Fecha de nacimiento"), ("edad_calculada", "Edad calculada"), ("rango_edad", "Rango de edad"),
    ("telefono", "Teléfono"), ("telefono2", "Teléfono 2"), ("otros_telefonos", "Otros teléfonos usables"),
    ("telefonos_no_usables", "Teléfonos no usables"), ("correo", "Correo"), ("direccion", "Dirección original"),
    ("direccion_norm", "Dirección normalizada"), ("lugar", "Barrio / vereda"), ("lugar_tipo", "Tipo de lugar"),
    ("zona", "Zona"), ("lat", "Latitud"), ("lon", "Longitud"), ("geo_precision", "Precisión"), ("ficha", "Ficha"),
    ("puesto_votacion", "Puesto de votación"), ("puesto_codigo", "Código del puesto"), ("mesa", "Mesa"),
    ("votacion_estado", "Estado de la votación"), ("donde_vota", "Dónde vota"), ("ocupacion", "Ocupación"),
    ("nivel_educativo", "Nivel educativo"), ("estado_civil", "Estado civil"), ("situacion_laboral", "Situación laboral"),
    ("personas_hogar", "Personas en el hogar"), ("jefe_hogar", "Jefe de hogar"),
    ("tenencia_vivienda", "Tenencia de la vivienda"), ("estrato", "Estrato"), ("regimen_salud", "Régimen de salud"),
    ("lider", "Líder"), ("etiquetas", "Necesidades / etiquetas"), ("listas", "Listas"), ("reuniones", "Reuniones"),
    ("consentimiento", "Autorización de datos"), ("abordaje", "Abordaje"), ("ultimo_acercamiento", "Último acercamiento"),
    ("situacion", "Situación"), ("completitud", "Completitud %"), ("fuentes", "Fuentes"),
    ("ultimo_contacto", "Último contacto"), ("creado_por", "Creado por"), ("actualizado_por", "Actualizado por"),
]
MOTIVO_POR_DEFECTO = "operacion_interna"


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


def _si_no(v) -> str | None:
    return "Sí" if v is True else ("No" if v is False else None)


def _telefonos(p: dict) -> tuple[str, str]:
    """(otros números usables, números no usables con su estado), separados por «; »."""
    principales = {p.get("telefono"), p.get("telefono2")}
    tels = modelo.telefonos_de(p)
    otros = [t["numero"] for t in tels if modelo.es_usable(t) and t.get("numero") not in principales]
    malos = [f"{t.get('numero')} ({'no contactar' if t.get('no_contactar') else modelo.ESTADOS_TELEFONO.get(t.get('estado'), t.get('estado'))})"
             for t in tels if not modelo.es_usable(t)]
    return "; ".join(str(x) for x in otros if x), "; ".join(malos)


def filtros_auditables(f: Filtros) -> dict:
    """Los filtros de una exportación para la auditoría: lo buscado nunca va en claro, solo su largo."""
    d = f.model_dump(exclude_none=True)
    if "q" in d:
        d["q_longitud"] = len(d.pop("q"))
    return d


@r.get("/exportar.xlsx")
def exportar(f: Filtros = Depends(filtros_query), incluir_sin_autorizacion: int = 0, incluir_listas: int = 0,
             incluir_sensibles: int = 0, motivo: str | None = Query(None, max_length=200),
             db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("exportar"))):
    motivo = (motivo or "").strip() or None
    if (incluir_listas or incluir_sensibles) and not motivo:
        raise HTTPException(422, "Para exportar listas o datos sensibles indique el motivo")
    if incluir_sin_autorizacion and not motivo:
        motivo = MOTIVO_POR_DEFECTO
    aj = modelo.leer_ajustes(db)
    hoy = modelo.hoy_local()
    filtro_campos = {"activo": True} if incluir_sensibles else {"activo": True, "sensible": {"$ne": True}}
    campos = list(db.campos.find(filtro_campos).sort([("orden", 1), ("_id", 1)]))
    lugares = mapa_lugares(db)
    etiquetas = {e["_id"]: e["nombre"] for e in db.etiquetas.find() if incluir_sensibles or not e.get("sensible")}
    codigos = {x["_id"]: x.get("codigo") for x in db.puestos.find({}, {"codigo": 1})}
    columnas = [c for c in COLUMNAS if c[0] != "listas" or incluir_listas]
    sensibles = list(modelo.SENSIBLES.items()) if incluir_sensibles else []
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Base única")
    ws.append([t for _, t in columnas] + [s["etiqueta"] for _, s in sensibles] + [celda(c["etiqueta"]) for c in campos])
    n = 0
    q = filtro(f)
    excluidas = 0 if incluir_sin_autorizacion else db.personas.count_documents({"$and": [q, {"consentimiento": "no"}]})
    proy = {"tramites": 0, "notas": 0, "origen": 0, "alternos": 0, "procedencia": 0, "historial": 0}
    if not incluir_sensibles:
        proy["sensibles"] = 0
    for p in db.personas.find(con_autorizacion(q, incluir_sin_autorizacion), proy).sort("nombre_norm", 1):
        lg = lugares.get(p.get("lugar_id")) or {}
        v = p.get("votacion") if isinstance(p.get("votacion"), dict) else {}
        ab = p.get("abordaje") if isinstance(p.get("abordaje"), dict) else {}
        edad = modelo.edad_efectiva(p, hoy)
        otros, malos = _telefonos(p)
        estado_v = modelo.estado_votacion_efectivo(p.get("votacion"), aj["eleccion_vigente"])
        donde = modelo.DONDE_VOTA.get(v.get("donde"), v.get("donde"))
        if donde and v.get("municipio"):
            donde = f"{donde}: {v['municipio']}"
        valores = {
            **p, "id": p["_id"], "lugar": lg.get("nombre") or p.get("lugar_texto"), "lugar_tipo": lg.get("tipo"),
            "cedula_verificada": _si_no(p.get("cedula_verificada")), "edad_calculada": edad,
            "rango_edad": modelo.rango_edad(edad), "otros_telefonos": otros, "telefonos_no_usables": malos,
            "puesto_codigo": codigos.get(v.get("puesto_id")),
            "votacion_estado": modelo.ESTADOS_VOTACION.get(estado_v, estado_v), "donde_vota": donde,
            "jefe_hogar": _si_no(p.get("jefe_hogar")),
            "etiquetas": ", ".join(etiquetas[e] for e in p.get("etiquetas", []) if e in etiquetas),
            "listas": "; ".join(p.get("listas", [])), "reuniones": len(p.get("asistencias", [])),
            "fuentes": ", ".join(p.get("fuentes", [])), "lider": "Sí" if p.get("lider") else "",
            "abordaje": modelo.ESTADOS_ABORDAJE.get(ab.get("estado"), ab.get("estado")),
            "ultimo_acercamiento": ab.get("ultimo_fecha"),
            "situacion": modelo.SITUACIONES.get((p.get("situacion") or {}).get("estado"), (p.get("situacion") or {}).get("estado")),
            "creado_por": (p.get("creado_por") or {}).get("usuario") if isinstance(p.get("creado_por"), dict) else None,
            "actualizado_por": (p.get("actualizado_por") or {}).get("usuario") if isinstance(p.get("actualizado_por"), dict) else None,
        }
        extra = p.get("extra") or {}
        sens = p.get("sensibles") if isinstance(p.get("sensibles"), dict) else {}
        ws.append([celda(valores.get(k)) for k, _ in columnas] + [celda(sens.get(k)) for k, _ in sensibles]
                  + [celda(extra.get(c["clave"])) for c in campos])
        n += 1
    buf = io.BytesIO()
    wb.save(buf)
    bd.auditar(db, adm, "exportar", None, None, {
        "filas": n, "filtros": filtros_auditables(f), "excluidas_sin_autorizacion": excluidas,
        "incluir_sin_autorizacion": bool(incluir_sin_autorizacion), "incluir_listas": bool(incluir_listas),
        "incluir_sensibles": bool(incluir_sensibles), "motivo": motivo})
    return StreamingResponse(iter([buf.getvalue()]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="base-unica-yondo-{bd.ahora()[:10]}.xlsx"'})


# ───────────────────────────── Catálogos, campos personalizados y etiquetas ─────────────────────────────

def subir_version_catalogos(db: Database) -> None:
    """Sube `meta.catalogos_version` (un entero): los navegadores vuelven a pedir los catálogos. Va en cada cambio de
    campos, etiquetas, lugares, puestos o ajustes."""
    db.meta.update_one({"_id": "catalogos_version"}, {"$inc": {"valor": 1}}, upsert=True)


def _version_catalogos(db: Database) -> str:
    # Se resume el documento entero: cualquier campo que suba (valor, n, version…) cambia la etiqueta
    doc = {k: v for k, v in (db.meta.find_one({"_id": "catalogos_version"}) or {}).items() if k != "_id"}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _comunes(aj: dict) -> dict:
    return {
        "eleccion_vigente": aj.get("eleccion_vigente"), "aviso_privacidad": aj.get("aviso_privacidad"),
        "politica": {k: aj.get(k) for k in ("contactar_pendientes", "dias_entre_intentos", "max_intentos_sin_exito",
                                            "seguimiento_activo", "dias_seguimiento", "horario")},
        "sensibles_activos": bool(aj.get("sensibles_activos")), "enlace_consulta_puesto": aj.get("enlace_consulta_puesto"),
    }


def _lugares(db: Database) -> list[dict]:
    return [{"id": l["_id"], "nombre": l["nombre"], "tipo": l["tipo"], "zona": l["zona"]}
            for l in db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1}).sort("nombre", 1)]


def _puestos(db: Database, aj: dict, rol: str) -> list[dict]:
    q = {"eleccion": aj.get("eleccion_vigente")}
    if rol != "admin":
        q["activo"] = {"$ne": False}
    filas = []
    for x in db.puestos.find(q).sort([("codigo", 1), ("_id", 1)]):
        f = {"id": x["_id"], "codigo": x.get("codigo"), "nombre": x.get("nombre")}
        if rol != "consultor":
            f.update(area=x.get("area"), mesas=x.get("mesas"), lugar_id=x.get("lugar_id"))
        if rol == "admin":
            f.update(activo=x.get("activo", True), alias=x.get("alias") or [])
        filas.append(f)
    return filas


def _catalogos_admin(db: Database, aj: dict) -> dict:
    from collections import Counter
    uso = Counter(e for p in db.personas.find({**bd.ACTIVA, "etiquetas.0": {"$exists": True}}, {"etiquetas": 1}) for e in p["etiquetas"])
    return {
        "campos": [{"id": c["_id"], **{k: v for k, v in c.items() if k != "_id"}, "sensible": bool(c.get("sensible"))}
                   for c in db.campos.find().sort([("orden", 1), ("_id", 1)])],
        "etiquetas": [{"id": e["_id"], "nombre": e["nombre"], "grupo": e["grupo"], "orden": e.get("orden", 0), "n": uso[e["_id"]],
                       "sensible": bool(e.get("sensible"))}
                      for e in db.etiquetas.find().sort([("grupo", 1), ("orden", 1), ("nombre", 1)])],
        "listas": sorted(x for x in db.personas.distinct("listas", bd.ACTIVA) if x),
        "lugares": _lugares(db),
        "puestos": _puestos(db, aj, "admin"),
        "usuarios": [{"id": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
                      "activo": bool(u.get("activo"))}
                     for u in db.usuarios.find({}, {"usuario": 1, "nombre": 1, "rol": 1, "activo": 1}).sort("usuario", 1)],
        **_comunes(aj),
    }


def _catalogos_usuario(db: Database, quien: Quien, aj: dict) -> dict:
    """Recorte por rol: sin etiquetas ni campos sensibles, sin listas, sin conteos de uso ni usuarios. El consultor
    no edita fichas: no recibe campos ni etiquetas."""
    planillero = quien.rol == "planillero"
    return {
        "campos": [{"id": c["_id"], "clave": c["clave"], "etiqueta": c["etiqueta"], "tipo": c["tipo"],
                    "opciones": c.get("opciones") or [], "orden": c.get("orden", 0), "activo": True}
                   for c in db.campos.find({"activo": True, "sensible": {"$ne": True}}).sort([("orden", 1), ("_id", 1)])]
        if planillero else [],
        "etiquetas": [{"id": e["_id"], "nombre": e["nombre"], "grupo": e["grupo"], "orden": e.get("orden", 0)}
                      for e in db.etiquetas.find({"sensible": {"$ne": True}}).sort([("grupo", 1), ("orden", 1), ("nombre", 1)])]
        if planillero else [],
        "lugares": _lugares(db),
        "puestos": _puestos(db, aj, quien.rol),
        **_comunes(aj),
    }


def _coincide(request: Request, etag: str) -> bool:
    enviados = [x.strip() for x in (request.headers.get("if-none-match") or "").split(",")]
    return etag in enviados or "*" in enviados


@r.get("/catalogos")
def catalogos(request: Request, response: Response, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("catalogos.ver"))):
    """Catálogos del rol, con `ETag`: el navegador los guarda durante la sesión y los revalida con If-None-Match. Para P
    y C la etiqueta es la versión de los catálogos (304 sin calcular nada); para A, que recibe conteos de uso, es el
    resumen de la respuesta."""
    aj = modelo.leer_ajustes(db)
    if quien.es_admin:
        cuerpo = _catalogos_admin(db, aj)
        resumen = hashlib.sha256(json.dumps(cuerpo, sort_keys=True, default=str).encode()).hexdigest()[:16]
        etag = f'W/"admin-{resumen}"'
    else:
        etag = f'W/"{quien.rol}-{_version_catalogos(db)}"'
        cuerpo = None
    if _coincide(request, etag):
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return cuerpo if cuerpo is not None else _catalogos_usuario(db, quien, aj)


class CampoIn(BaseModel):
    etiqueta: str | None = Field(None, min_length=2, max_length=60)
    tipo: Literal["texto", "numero", "si_no", "opcion", "fecha"] | None = None
    opciones: list[str] | None = None
    orden: int | None = None
    activo: bool | None = None
    sensible: bool | None = None


@r.post("/campos", status_code=201)
def crear_campo(body: CampoIn, db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("admin"))):
    if not body.etiqueta or not body.tipo:
        raise HTTPException(422, "Nombre y tipo son obligatorios")
    clave = re.sub(r"[^a-z0-9]+", "_", tx.sin_tildes(body.etiqueta).lower()).strip("_")[:40] or "campo"
    base, n = clave, 2
    while db.campos.find_one({"clave": clave}, {"_id": 1}):
        clave, n = f"{base}_{n}", n + 1
    cid = bd.siguiente_id(db, "campos")
    db.campos.insert_one({"_id": cid, "clave": clave, "etiqueta": body.etiqueta.strip(), "tipo": body.tipo,
                          "opciones": [o.strip() for o in body.opciones or [] if o.strip()], "orden": body.orden or cid,
                          "activo": True, "sensible": bool(body.sensible)})
    subir_version_catalogos(db)
    bd.auditar(db, adm, "crear_campo", "campo", cid, body.model_dump())
    return {"clave": clave}


@r.patch("/campos/{cid}")
def editar_campo(cid: int, body: CampoIn, db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("admin"))):
    datos = body.model_dump(exclude_unset=True)
    if datos:
        db.campos.update_one({"_id": cid}, {"$set": datos})
        subir_version_catalogos(db)
        bd.auditar(db, adm, "editar_campo", "campo", cid, datos)
    return {"ok": True}


class EtiquetaIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    grupo: Literal["necesidad", "interes", "rol"] = "necesidad"
    sensible: bool = False


@r.post("/etiquetas", status_code=201)
def crear_etiqueta(body: EtiquetaIn, db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("admin"))):
    eid = bd.siguiente_id(db, "etiquetas")
    try:
        db.etiquetas.insert_one({"_id": eid, "nombre": body.nombre.strip(), "grupo": body.grupo, "orden": eid,
                                 "sensible": body.sensible})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe")
    subir_version_catalogos(db)
    bd.auditar(db, adm, "crear_etiqueta", "etiqueta", eid, body.model_dump())
    return {"id": eid}


@r.delete("/etiquetas/{eid}")
def borrar_etiqueta(eid: int, db: Database = Depends(obtener_db), adm: Quien = Depends(requiere("admin"))):
    db.etiquetas.delete_one({"_id": eid})
    db.personas.update_many({"etiquetas": eid}, {"$pull": {"etiquetas": eid}})
    bd.recalcular_completitud(db)
    subir_version_catalogos(db)
    bd.auditar(db, adm, "borrar_etiqueta", "etiqueta", eid, None)
    return {"ok": True}


@r.get("/auditoria")
def auditoria(pagina: int = 1, uid: int | None = None, accion: str | None = Query(None, max_length=40),
              entidad: str | None = Query(None, max_length=20), entidad_id: int | None = None,
              desde: str | None = None, hasta: str | None = None, db: Database = Depends(obtener_db),
              _: Quien = Depends(requiere("admin"))):
    from .usuarios import periodo
    pagina = max(1, pagina)
    q: dict = {}
    if uid is not None:
        q["uid"] = uid
    if accion:
        q["accion"] = accion
    if entidad:
        q["entidad"] = entidad
    if entidad_id is not None:
        q["entidad_id"] = entidad_id
    if desde or hasta:
        _, _, ts_desde, ts_hasta = periodo(desde or "2000-01-01", hasta, maximo_dias=None)
        q["ts"] = {"$gte": ts_desde, "$lt": ts_hasta}
    orden = [("ts", -1), ("_id", -1)] if q else [("_id", -1)]
    filas = [{k: a.get(k) for k in ("ts", "usuario", "uid", "rol", "accion", "entidad", "entidad_id", "detalle", "ip")}
             for a in db.auditoria.find(q).sort(orden).skip((pagina - 1) * 100).limit(100)]
    return {"total": db.auditoria.count_documents(q) if q else db.auditoria.estimated_document_count(), "filas": filas}
