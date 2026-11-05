"""Directorio de habitantes: búsqueda, ficha, alta, edición, teléfonos, autorización, seguimiento, notas, ubicación,
fusión y supresión.

* Toda respuesta con una ficha o filas pasa por `proyeccion` (campos permitidos por rol) y queda en `lecturas`.
* Toda escritura es parcial y condicional: un solo `update_one` con un pipeline sobre `{_id, **ACTIVA}` (409 si la
  ficha se unió o se suprimió), con `base` como comparación por campo (409 `cambiada`). Nunca se reescribe la ficha.
* Toda escritura sobre una persona pasa por `exigir_tratable` (3.9): a quien no autorizó, P y C no lo tratan.
* P: alcance obligatorio en Habitantes, búsqueda y ficha libres (con presupuesto), no cambia una cédula existente, no
  vacía campos, no ve ni toca lo sensible. C: solo busca por nombre (o por un número completo) y trabaja dentro de su
  alcance (3.6).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from rapidfuzz import fuzz

from .. import acceso, modelo, proyeccion
from .. import db as bd
from ..acceso import Quien, requiere
from ..pipeline import texto as tx
from ..pipeline.cruce import ComparadorNombres
from ..pipeline.importar import georreferenciar
from ..seguridad import obtener_db
from .filtros import Filtros, consulta, exigir_alcance_consultor, filtro, filtros_query

r = APIRouter(prefix="/api", tags=["personas"])

ORDENES = {
    # Siempre termina en _id: con empates (misma completitud, mismo segundo) las páginas no repiten ni saltan fichas
    "nombre": [("nombre_norm", ASCENDING), ("_id", ASCENDING)],
    "completitud": [("completitud", DESCENDING), ("nombre_norm", ASCENDING), ("_id", ASCENDING)],
    "-completitud": [("completitud", ASCENDING), ("nombre_norm", ASCENDING), ("_id", ASCENDING)],
    "reciente": [("actualizado_en", DESCENDING), ("_id", DESCENDING)],
    "contacto": [("ultimo_contacto", DESCENDING), ("nombre_norm", ASCENDING), ("_id", ASCENDING)],
    # 4.6: los nulos van primero en un orden ascendente
    "por_llamar": [("abordaje.ultimo_ts", ASCENDING), ("completitud", DESCENDING), ("_id", ASCENDING)],
    "abordaje_reciente": [("abordaje.ultimo_ts", DESCENDING), ("_id", DESCENDING)],
    "lugar": [("lugar_id", ASCENDING), ("direccion_norm", ASCENDING), ("_id", ASCENDING)],
}
SIN_PERMISO = {"mensaje": "Su rol no permite esta acción", "codigo": "permiso"}
NO_ACTIVA = "La ficha se unió o se suprimió"


def _lit(v: Any) -> dict:
    return {"$literal": v}


def mapa_lugares(db: Database) -> dict[int, dict]:
    return {l["_id"]: l for l in db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1})}


def _prohibido(mensaje: str | None = None, **extra) -> HTTPException:
    return HTTPException(403, {**SIN_PERMISO, **({"mensaje": mensaje} if mensaje else {}), **extra})


def _es_consultor(quien: Quien) -> bool:
    return not quien.administra and quien.rol == "consultor"


def _es_planillero(quien: Quien) -> bool:
    return not quien.administra and quien.rol == "planillero"


def autor(quien: Quien) -> dict:
    return {"uid": quien.uid, "usuario": quien.usuario, "rol": quien.rol}


def ficha_respuesta(db: Database, quien: Quien, pid: int, avisos: list[str] | None = None) -> dict:
    """La ficha del rol después de una escritura (cuenta como lectura) con los avisos de la operación."""
    f = proyeccion.ficha_para(db, quien, pid)
    if avisos and "avisos" in f:
        f["avisos"] = list(dict.fromkeys([*avisos, *f["avisos"]]))
    return f


def _idempotente(db: Database, quien: Quien, request: Request):
    return acceso.idempotencia_previa(db, quien, request)


def _guardar_idem(db: Database, quien: Quien, request: Request, codigo: int, cuerpo: Any, pid: int | None) -> Any:
    acceso.idempotencia_guardar(db, quien, request, codigo, cuerpo, persona_id=pid)
    return cuerpo


def georreferenciar_y_punto(db: Database, ids: list[int]) -> None:
    """Ubica y deja `punto` al día (con `modelo.punto`, igual que la migración y la importación)."""
    georreferenciar(db, ids)
    ops = [UpdateOne({"_id": p["_id"]}, {"$set": {"punto": modelo.punto(p.get("lat"), p.get("lon"))}})
           for p in db.personas.find({"_id": {"$in": ids}}, {"lat": 1, "lon": 1, "punto": 1})
           if p.get("punto") != modelo.punto(p.get("lat"), p.get("lon"))]
    if ops:
        db.personas.bulk_write(ops, ordered=False)


# ───────────────────────────── Habitantes y búsqueda ─────────────────────────────

def exigir_listas_del_dia(db: Database, quien: Quien) -> None:
    """Después del primer 429 por volumen del día, P y C ya no reciben listas (Habitantes y colas) hasta mañana, ni
    siquiera de personas ya vistas: las listas son la vía de extracción masiva. La ficha ya vista se puede reabrir."""
    if quien.administra or quien.uid in (None, 0):
        return
    u = db.usuarios.find_one({"_id": quien.uid}, {"volumen": 1}) or {}
    v = u.get("volumen") if isinstance(u.get("volumen"), dict) else {}
    if v.get("dia") == modelo.hoy_local().isoformat() and (v.get("rechazos") or 0) >= 1:
        tope = acceso.presupuesto(db, quien.rol)
        raise HTTPException(429, {"mensaje": f"Llegó al tope de {tope} personas consultadas hoy. Podrá seguir mañana.",
                                  "codigo": "volumen"})


@r.get("/personas")
def listar(f: Filtros = Depends(filtros_query), orden: str = "nombre", pagina: int = 1, por_pagina: int = 50,
           db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("personas.listar", limitar=True))):
    q = consulta(db, quien, f, con_alcance=True)  # vedados (403) y alcance obligatorio para P
    exigir_listas_del_dia(db, quien)
    por_pagina = max(10, min(por_pagina, 200))
    pagina = max(1, min(pagina, 10_000))
    total = db.personas.count_documents(q)
    docs = list(db.personas.find(q, proyeccion.CAMPOS_PARA_FILA).sort(ORDENES.get(orden, ORDENES["nombre"]))
                .skip((pagina - 1) * por_pagina).limit(por_pagina))
    acceso.registrar_lecturas(db, quien, [p["_id"] for p in docs])
    ctx = proyeccion.contexto(db)
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina,
            "filas": proyeccion.filas_para(quien, [proyeccion.fila_completa(p, ctx) for p in docs])}


def _buscar_consultor(db: Database, quien: Quien, q: str) -> list[dict]:
    """Búsqueda del consultor (3.6): solo por nombre (3 letras o más, 10 resultados y campos reducidos); con dígitos,
    422, salvo un número completo de 10 dígitos (llamada entrante: coincidencia exacta, 3 resultados, auditada)."""
    digitos = re.sub(r"\D", "", q)
    if digitos:
        if len(digitos) != 10 or re.sub(r"[\d\s+()-]", "", q):
            raise HTTPException(422, "Busque por nombre, o por el número completo de 10 dígitos")
        docs = list(db.personas.find({**bd.ACTIVA, "$or": [{"telefonos.numero": digitos}, {"telefono": digitos},
                                                            {"telefono2": digitos}]}, proyeccion.CAMPOS_PARA_FILA).limit(3))
        bd.auditar(db, quien, "buscar_telefono", None, None, {"resultados": len(docs)})
    else:
        toks = [t for t in tx.limpiar(q).split() if re.sub(r"[^A-Z]", "", t)][:6]
        if len("".join(toks)) < 3:
            return []
        cond = [{"nombre_norm": {"$regex": re.escape(re.sub(r"[^A-Z]", "", t))}} for t in toks]
        docs = list(db.personas.find({"$and": [dict(bd.ACTIVA), *cond]}, proyeccion.CAMPOS_PARA_FILA)
                    .sort([("nombre_norm", ASCENDING), ("_id", ASCENDING)]).limit(10))
    acceso.registrar_lecturas(db, quien, [p["_id"] for p in docs])
    ctx = proyeccion.contexto(db)
    return proyeccion.filas_para(quien, [proyeccion.fila_completa(p, ctx) for p in docs])


@r.get("/buscar")
def buscar(q: str = Query(..., max_length=120), db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("personas.buscar", limitar=True))):
    """Autocompletar rápido (registro de asistentes, alta, llamada entrante). P busca en toda la base."""
    if _es_consultor(quien):
        return _buscar_consultor(db, quien, q)
    if len(q.strip()) < 2:
        return []
    inicio = tx.limpiar(q)
    docs = list(db.personas.find(filtro(Filtros(q=q)), proyeccion.CAMPOS_PARA_FILA).limit(60))
    docs.sort(key=lambda p: (not (p.get("nombre_norm") or "").startswith(inicio), -p.get("completitud", 0)))
    docs = docs[:12]
    acceso.registrar_lecturas(db, quien, [p["_id"] for p in docs])
    ctx = proyeccion.contexto(db)
    return proyeccion.filas_para(quien, [proyeccion.fila_completa(p, ctx) for p in docs])


# ───────────────────────────── Ficha ─────────────────────────────

def exigir_ficha_consultor(db: Database, p: dict, quien: Quien) -> None:
    """C: la persona debe estar en su alcance (tomada o con un acercamiento suyo reciente) y no ser menor."""
    if not _es_consultor(quien):
        return
    exigir_alcance_consultor(db, p, quien)
    if modelo.es_menor(p):
        raise HTTPException(409, {"mensaje": "No se contacta a menores de edad", "codigo": "no_contactable",
                                  "motivo": "menor"})


CAMPOS_RESUMEN = ("id", "nombre", "lugar_nombre", "zona", "geo_precision", "completitud", "consentimiento", "abordaje",
                  "rango_edad", "sexo", "telefono", "votacion")


@r.get("/personas/{pid}")
def ver(pid: int, resumen: int = 0, db: Database = Depends(obtener_db),
        quien: Quien = Depends(requiere("personas.ver"))):
    if resumen and not quien.puede("mapa.ver"):
        raise _prohibido("El resumen del mapa es solo para el administrador")
    p = proyeccion.cargar(db, pid)
    exigir_ficha_consultor(db, p, quien)
    f = proyeccion.ficha_para(db, quien, pid)
    if resumen:
        return {k: f.get(k) for k in CAMPOS_RESUMEN}
    return f


@r.get("/personas/{pid}/autorizaciones")
def autorizaciones(pid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    proyeccion.cargar(db, pid)
    return [{"id": e["_id"], **{k: e.get(k) for k in (*proyeccion.CAMPOS_AUTORIZACION, "evidencia_sha256",
                                                        "evidencia_fila", "texto_version", "clave_migracion")}}
            for e in db.autorizaciones.find({"persona_id": pid}).sort([("ts", DESCENDING), ("_id", DESCENDING)])]


@r.get("/personas/{pid}/sensibles")
def sensibles(pid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Los valores sensibles: solo A (y K), con un clic que queda auditado sin los valores."""
    p = proyeccion.cargar(db, pid)
    valores = {c: v for c, v in (p.get("sensibles") or {}).items() if c in modelo.SENSIBLES and v not in (None, "")}
    bd.auditar(db, quien, "ver_sensibles", "persona", pid, {"categorias": sorted(valores)})
    return {"sensibles": valores, "autorizados": list(p.get("sensibles_autorizados") or [])}


# ───────────────────────────── Validación de la entrada ─────────────────────────────

def fecha_iso(v: str | None) -> str | None:
    """Valida una fecha AAAA-MM-DD que además exista (1985-02-30 no). La usan las fichas y las reuniones."""
    if v:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Use el formato AAAA-MM-DD")
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Fecha inexistente: {v}") from None
    return v


TIPOS_DOC = Literal["CC", "TI", "CE", "PPT", "PEP", "PA"]


class PersonaIn(BaseModel):
    nombre: str | None = Field(None, max_length=160)
    cedula: str | None = Field(None, max_length=20)
    tipo_documento: TIPOS_DOC | None = None
    cedula_verificada: bool | None = None
    motivo_cambio_cedula: str | None = Field(None, max_length=300)
    sexo: Literal["F", "M", "N", ""] | None = None
    edad: int | None = Field(None, ge=0, le=120)
    fecha_nacimiento: str | None = Field(None, max_length=10)
    estado_civil: str | None = Field(None, max_length=60)
    nivel_educativo: str | None = Field(None, max_length=60)
    situacion_laboral: str | None = Field(None, max_length=60)
    ocupacion: str | None = Field(None, max_length=120)
    personas_hogar: int | None = Field(None, ge=0, le=40)
    jefe_hogar: bool | None = None
    tenencia_vivienda: str | None = Field(None, max_length=60)
    estrato: int | None = Field(None, ge=0, le=6)
    regimen_salud: str | None = Field(None, max_length=60)
    telefono: str | None = Field(None, max_length=60)
    telefono2: str | None = Field(None, max_length=60)
    correo: str | None = Field(None, max_length=120)
    direccion: str | None = Field(None, max_length=240)
    lugar_id: int | None = None
    puesto_id: int | None = None
    puesto_texto: str | None = Field(None, max_length=160)
    puesto_votacion: str | None = Field(None, max_length=160)  # el de siempre (A): se reconoce contra el catálogo
    mesa: str | int | None = Field(None)
    donde: Literal["yondo", "otro_municipio", "no_inscrito"] | None = None
    municipio: str | None = Field(None, max_length=80)
    votacion_verificada: bool | None = None
    lider: bool | None = None
    consentimiento: Literal["si", "no", "pendiente"] | None = None
    consentimiento_fecha: str | None = Field(None, max_length=10)
    consentimiento_medio: str | None = Field(None, max_length=40)
    consentimiento_canales: list[str] | None = Field(None, max_length=10)
    evidencia: str | None = Field(None, max_length=500)
    mayor_declarado: bool | None = None
    sensibles: dict[str, str | None] | None = None
    observaciones: str | None = Field(None, max_length=4000)
    etiquetas: list[int] | None = Field(None, max_length=200)
    etiquetas_base: list[int] | None = Field(None, max_length=200)
    extra: dict[str, Any] | None = None
    base: dict[str, Any] | None = None

    @field_validator("fecha_nacimiento", "consentimiento_fecha")
    @classmethod
    def _fecha(cls, v):
        return fecha_iso(v) or None

    @field_validator("mesa")
    @classmethod
    def _mesa(cls, v):
        if isinstance(v, str) and len(v) > 40:
            raise ValueError("La mesa es muy larga")
        return v


# Campos simples (un valor de primer nivel) y su clave canónica para la auditoría y los indicadores
SIMPLES = ("nombre", "sexo", "edad", "fecha_nacimiento", "estado_civil", "nivel_educativo", "situacion_laboral",
           "ocupacion", "personas_hogar", "jefe_hogar", "tenencia_vivienda", "estrato", "regimen_salud", "correo",
           "direccion", "observaciones", "lider", "cedula_verificada")
CATALOGOS = {"estado_civil": modelo.ESTADOS_CIVILES, "nivel_educativo": modelo.NIVELES,
             "situacion_laboral": modelo.SITUACIONES_LABORALES, "tenencia_vivienda": modelo.TENENCIAS,
             "regimen_salud": modelo.REGIMENES_SALUD}
CANONICO = {"fecha_nacimiento": "edad", "lugar_id": "lugar", "telefono": "telefono", "telefono2": "telefono",
            "puesto_id": "puesto", "puesto_texto": "puesto", "puesto_votacion": "puesto", "donde": "puesto",
            "municipio": "puesto", "votacion_verificada": "puesto", "consentimiento": "autorizacion",
            "consentimiento_fecha": "autorizacion", "tipo_documento": "cedula", "cedula_verificada": "cedula"}
VOTACION_ENTRADA = ("puesto_id", "puesto_texto", "puesto_votacion", "mesa", "donde", "municipio", "votacion_verificada")
# Lo que P no puede mandar (403 con el nombre del campo)
VEDADOS_P = ("lider", "motivo_cambio_cedula", "puesto_votacion", "consentimiento_fecha")


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v in ([], {})


def validar_documento(numero: Any, tipo: str | None) -> str | None:
    """CC y TI: de 5 a 11 dígitos (`tx.cedula`); CE, PPT, PEP y PA: de 4 a 15 letras o números, solo en el panel."""
    if _vacio(numero):
        return None
    if tipo in (None, "CC", "TI"):
        c = tx.cedula(numero)
        if not c:
            raise HTTPException(422, "La cédula debe tener entre 5 y 11 dígitos")
        return c
    s = re.sub(r"[\s.-]", "", str(numero)).upper()
    if not re.fullmatch(r"[A-Z0-9]{4,15}", s):
        raise HTTPException(422, "El documento debe tener de 4 a 15 letras o números")
    return s


def _limpiar_simple(k: str, v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
    if k == "nombre":
        v = tx.nombre_visible(v)
        if not tx.nombre_norm(v):
            raise HTTPException(422, "El nombre no puede quedar vacío")
        return v
    if k == "correo":
        if _vacio(v):
            return None
        c = tx.correo(v)
        if not c:
            raise HTTPException(422, f"Correo no válido: {v}")
        return c
    if k in ("lider", "cedula_verificada", "jefe_hogar"):
        return None if v is None else bool(v)
    if k == "sexo":
        return v or None
    if k in CATALOGOS and not _vacio(v) and v not in CATALOGOS[k]:
        raise HTTPException(422, f"Valor no válido para {k}: {v}")
    return None if _vacio(v) else v


def numeros(texto: Any) -> list[str]:
    """Todos los números de un texto (varios separados por coma, espacio o «/»), normalizados; 422 si no hay ninguno."""
    tels = tx.telefonos(texto)
    if not _vacio(texto) and not tels:
        raise HTTPException(422, f"Teléfono no válido: {texto}")
    return list(dict.fromkeys(tels))


# ───────────────────────────── Cédula ─────────────────────────────

def cedula_ocupada(db: Database, c: str | None, pid: int | None = None) -> None:
    """409 `cedula_ocupada` si la cédula es de otra ficha activa (también como cédula anterior)."""
    if not c:
        return
    otro = db.personas.find_one({"$or": [{"cedula": c}, {"cedulas_anteriores": c}], **bd.ACTIVA, "_id": {"$ne": pid}},
                                {"nombre": 1, "lugar_id": 1, "lugar_texto": 1})
    if otro:
        lg = db.lugares.find_one({"_id": otro.get("lugar_id")}, {"nombre": 1}) if otro.get("lugar_id") else None
        raise HTTPException(409, {"mensaje": f"La cédula ya pertenece a {otro['nombre']}", "codigo": "cedula_ocupada",
                                  "id": otro["_id"], "nombre": otro["nombre"],
                                  "lugar": (lg or {}).get("nombre") or otro.get("lugar_texto")})


def es_suprimida(db: Database, cedula: str | None = None, nombre: str | None = None, telefonos: list[str] = ()) -> bool:
    """¿Coincide con las huellas de alguien que pidió la supresión (cédula, o teléfono con nombre)?"""
    clave = bd.clave_supresion(db)
    hs = {bd.huella(clave, "cedula", cedula)} if cedula else set()
    if nombre:
        hs |= {bd.huella(clave, "nombre_tel", (t, nombre)) for t in telefonos or []}
    hs.discard(None)
    return bool(hs) and db.suprimidos.count_documents({"_id": {"$in": list(hs)}}, limit=1) > 0


SUPRIMIDA = {"mensaje": "Esta persona pidió que se suprimieran sus datos: no se puede registrar de nuevo",
             "codigo": "suprimida"}


# ───────────────────────────── Expresiones de escritura ─────────────────────────────

def _vacio_expr(campo: str) -> dict:
    return {"$in": [{"$ifNull": [f"${campo}", None]}, [None, ""]]}


def _alterno_viejo(campo: str, nuevo: Any, ts: str, uid: Any) -> dict:
    """Si el valor actual no está vacío y cambia, va a `alternos` con su procedencia."""
    return {"$cond": [{"$and": [{"$not": [_vacio_expr(campo)]}, {"$ne": [f"${campo}", _lit(nuevo)]}]},
                      [{"campo": campo, "valor": f"${campo}",
                        "fuente": {"$ifNull": [f"$procedencia.{campo}.fuente", "panel"]}, "ts": ts, "uid": uid}], []]}


def _alterno_entrante(campo: str, nuevo: Any, ts: str, uid: Any) -> dict:
    """Modo «completar»: si ya tiene otro valor, el que llega va a `alternos`."""
    return {"$cond": [{"$and": [{"$not": [_vacio_expr(campo)]}, {"$ne": [f"${campo}", _lit(nuevo)]}]},
                      [{"campo": campo, "valor": _lit(nuevo), "fuente": "panel", "ts": ts, "uid": uid}], []]}


def expr_alternos(candidatos: list[dict]) -> dict:
    """`alternos` actuales más los candidatos que no repiten (campo, valor), con tope de 100 (se descarta el más viejo)."""
    actuales = {"$ifNull": ["$alternos", []]}
    pares = {"$map": {"input": actuales, "as": "y", "in": ["$$y.campo", "$$y.valor"]}}
    nuevos = {"$filter": {"input": {"$concatArrays": candidatos}, "as": "x",
                          "cond": {"$not": [{"$in": [["$$x.campo", "$$x.valor"], pares]}]}}}
    return {"$slice": [{"$concatArrays": [actuales, nuevos]}, -100]}


def _expr_reactivar(nums: list[str], cambios: dict, forzar: bool) -> dict:
    """En esos números, los cambios; sin `forzar`, solo en los que no son usables (vuelven a «sin verificar»)."""
    cond = {"$in": ["$$t.numero", _lit(nums)]}
    if not forzar:
        cond = {"$and": [cond, {"$not": [{"$in": [{"$ifNull": ["$$t.estado", "sin_verificar"]}, sorted(modelo.USABLES)]}]}]}
    return {"$set": {"telefonos": {"$map": {"input": modelo.TELS_ACTUALES, "as": "t", "in": {"$cond": [
        cond, {"$mergeObjects": ["$$t", _lit(cambios)]}, "$$t"]}}}}}


def _etapa_segundo(numero: str) -> dict:
    """Pone el número justo después del primer número usable (así queda como `telefono2`)."""
    otros = {"$filter": {"input": "$$a", "as": "t", "cond": {"$ne": ["$$t.numero", _lit(numero)]}}}
    este = {"$filter": {"input": "$$a", "as": "t", "cond": {"$eq": ["$$t.numero", _lit(numero)]}}}
    usable = {"$and": [{"$in": [{"$ifNull": ["$$t.estado", "sin_verificar"]}, sorted(modelo.USABLES)]},
                       {"$ne": ["$$t.no_contactar", True]}]}
    primero = {"$arrayElemAt": [{"$map": {"input": {"$filter": {"input": "$$o", "as": "t", "cond": usable}}, "as": "u",
                                          "in": "$$u.numero"}}, 0]}
    return {"$set": {"telefonos": {"$let": {"vars": {"a": modelo.TELS_ACTUALES}, "in": {"$let": {
        "vars": {"o": otros, "e": este}, "in": {"$let": {
            "vars": {"j": {"$indexOfArray": [{"$map": {"input": "$$o", "as": "t", "in": "$$t.numero"}},
                                             {"$ifNull": [primero, "-"]}]}},
            "in": {"$cond": [{"$lt": ["$$j", 0]}, {"$concatArrays": ["$$e", "$$o"]}, {"$concatArrays": [
                {"$slice": ["$$o", 0, {"$add": ["$$j", 1]}]}, "$$e",
                {"$slice": ["$$o", {"$add": ["$$j", 1]}, {"$max": [1, {"$size": "$$o"}]}]}]}]}}}}}}}}}


def etapas_telefonos(nums: list[str], quien: Quien, fuente: str, *, estado: str = "sin_verificar", forzar: bool = False,
                     whatsapp: bool | None = None, nota: str | None = None, posicion: int | None = None) -> list[dict]:
    """Pipeline que agrega `nums` (los que ya están solo suman la fuente), deja su estado (sin `forzar`, solo los que
    no eran usables vuelven a `estado`), y los pone en la posición 0 (principal) o 1. Termina derivando telefono y
    telefono2. Nunca se escribe una lista calculada en Python."""
    ts, hoy = bd.ahora(), modelo.hoy_local().isoformat()
    campos: dict = {"agregado_por": quien.uid}
    if whatsapp is not None:
        campos["whatsapp"] = whatsapp
    if nota:
        campos["nota"] = nota
    if estado != "sin_verificar":
        campos.update(estado=estado, estado_por=quien.uid, estado_en=ts)
    etapas = modelo.expr_unir_telefonos([modelo.telefono_nuevo(n, fuente, hoy, **campos) for n in nums])[:-1]
    etapas.append(_expr_reactivar(nums, {"estado": estado, "estado_por": quien.uid, "estado_en": ts}, forzar))
    extra = {k: v for k, v in (("whatsapp", whatsapp), ("nota", nota)) if v is not None}
    if extra:
        etapas.append(_expr_reactivar(nums, extra, True))
    if posicion == 0:
        etapas += modelo.expr_principal(nums[0])[:-1]
    elif posicion == 1:
        etapas.append(_etapa_segundo(nums[0]))
    etapas.append(modelo.ETAPA_DERIVAR_TELEFONOS)
    return etapas


def etapa_requiere(motivo: str, quien: Quien | None, nota: str | None = None, solo_si_falta: bool = True) -> dict:
    """Fija `requiere_actualizacion` (si no hay otro pendiente). Solo se borra con «Marcar como atendido»."""
    valor = {"motivo": motivo, "uid": getattr(quien, "uid", None), "usuario": getattr(quien, "usuario", None),
             "ts": bd.ahora(), "nota": nota}
    if not solo_si_falta:
        return {"$set": {"requiere_actualizacion": _lit(valor)}}
    return {"$set": {"requiere_actualizacion": {"$ifNull": ["$requiere_actualizacion", _lit(valor)]}}}


def etapa_sin_telefono() -> dict:
    """Si ya no queda ningún número usable, `requiere_actualizacion{motivo: "sin_telefono_valido"}` (deja a la persona
    en la lista de visitas de P)."""
    valor = {"motivo": "sin_telefono_valido", "uid": None, "usuario": None, "ts": bd.ahora(), "nota": None}
    return {"$set": {"requiere_actualizacion": {"$cond": [
        {"$and": [{"$eq": [{"$ifNull": ["$telefono", None]}, None]},
                  {"$eq": [{"$ifNull": ["$requiere_actualizacion", None]}, None]},
                  {"$gt": [{"$size": {"$ifNull": ["$telefonos", []]}}, 0]}]},
        _lit(valor), "$requiere_actualizacion"]}}}


def etapa_actualizado(quien: Quien) -> dict:
    ts = bd.ahora()
    return {"$set": {"actualizado_en": ts, "actualizado_por": _lit({**autor(quien), "ts": ts})}}


def etapa_avance(claves: list[str], quien: Quien) -> dict | None:
    """`avance.<clave>` solo la primera vez en la vida de la ficha: vaciar y volver a llenar no suma."""
    if not claves:
        return None
    marca = {"uid": quien.uid, "ts": bd.ahora()}
    return {"$set": {"avance": {"$mergeObjects": [{"$ifNull": ["$avance", {}]}, {
        k: {"$ifNull": [f"$avance.{k}", _lit(marca)]} for k in claves}]}}}


def escribir(db: Database, pid: int, etapas: list[dict], condiciones: list[dict] | None = None) -> bool:
    """Una escritura condicional sobre la ficha activa. 409 si se unió o se suprimió; False si no se cumplieron las
    `condiciones` (quien llama decide el 409)."""
    etapas = [e for e in etapas if e]
    if not etapas:
        return True
    q = {"$and": [{"_id": pid}, dict(bd.ACTIVA), *(condiciones or [])]}
    try:
        res = db.personas.update_one(q, etapas)
    except DuplicateKeyError:
        raise HTTPException(409, {"mensaje": "La cédula ya pertenece a otra ficha", "codigo": "cedula_ocupada"}) from None
    if res.matched_count:
        return True
    if db.personas.count_documents({"_id": pid, **bd.ACTIVA}, limit=1) == 0:
        raise HTTPException(409, NO_ACTIVA)
    return False


# ───────────────────────────── Votación ─────────────────────────────

def _puestos(db: Database) -> list[dict]:
    aj = modelo.leer_ajustes(db)
    return list(db.puestos.find({"eleccion": aj.get("eleccion_vigente"), "activo": {"$ne": False}})) or \
        list(db.puestos.find({"activo": {"$ne": False}}))


def cambios_votacion(db: Database, datos: dict, quien: Quien, fuente: str = "panel", completar: bool = False) -> dict:
    """Las claves de `votacion` que cambian (1.4), validadas contra el catálogo. {} si no hay nada de votación."""
    if not any(k in datos for k in VOTACION_ENTRADA):
        return {}
    v: dict = {}
    puesto = None
    texto = datos.get("puesto_texto") if "puesto_texto" in datos else datos.get("puesto_votacion")
    if datos.get("puesto_id") is not None:
        puesto = db.puestos.find_one({"_id": datos["puesto_id"]})
        if puesto is None:
            raise HTTPException(422, "El puesto no existe")
        v.update(puesto_id=puesto["_id"], puesto_nombre=puesto.get("nombre"), puesto_texto=None)
    elif "puesto_id" in datos or "puesto_texto" in datos or "puesto_votacion" in datos:
        if _vacio(texto):
            v.update(puesto_id=None, puesto_nombre=None, puesto_texto=None)
        else:
            texto = str(texto).strip()
            pid_, ambiguo = modelo.reconocer_puesto(texto, _puestos(db))
            if pid_ is not None:
                puesto = db.puestos.find_one({"_id": pid_})
                v.update(puesto_id=pid_, puesto_nombre=(puesto or {}).get("nombre"), puesto_texto=None)
            else:
                v.update(puesto_id=None, puesto_nombre=None, puesto_texto=texto)
                if ambiguo:
                    v["estado"] = "por_confirmar"
    if "mesa" in datos:
        bruto = datos["mesa"]
        if _vacio(bruto):
            v.update(mesa=None, mesa_texto=None)
        else:
            n = modelo.normalizar_mesa(bruto)
            if puesto is None:
                actual = (db.personas.find_one({"_id": datos.get("_pid")}, {"votacion.puesto_id": 1}) or {}).get("votacion") \
                    if datos.get("_pid") else None
                if isinstance(actual, dict) and actual.get("puesto_id") is not None:
                    puesto = db.puestos.find_one({"_id": actual["puesto_id"]})
            tope = (puesto or {}).get("mesas") or modelo.MESAS_SIN_CATALOGO
            texto_mesa = str(bruto).strip() if isinstance(bruto, str) and not bruto.strip().isdigit() else None
            if n is None or not 1 <= n <= tope:
                v.update(mesa=None, mesa_texto=str(bruto).strip(), estado="por_confirmar")
            else:
                v.update(mesa=n, mesa_texto=texto_mesa)
    if "donde" in datos and datos["donde"]:
        v["donde"] = datos["donde"]
        if datos["donde"] != "otro_municipio":
            v["municipio"] = None
    if datos.get("municipio") is not None:
        v["municipio"] = str(datos["municipio"]).strip() or None
    if not v and "votacion_verificada" not in datos:
        return {}
    if "estado" not in v:
        if datos.get("votacion_verificada") is True:
            v["estado"] = "verificado"
        elif not completar:
            v["estado"] = "sin_verificar"
    if datos.get("votacion_verificada") is True and v.get("estado") == "verificado":
        v["fuente"] = "titular"
    else:
        v["fuente"] = fuente
    v.update(eleccion=modelo.leer_ajustes(db).get("eleccion_vigente"), registrado_por=quien.uid,
             registrado_en=bd.ahora())
    if "donde" not in v and (v.get("puesto_id") is not None or v.get("puesto_texto")):
        v["donde"] = "yondo"
    return v


CLAVES_VOTACION = ("puesto_id", "puesto_texto", "mesa", "mesa_texto", "donde", "municipio")


def etapas_votacion(v: dict, quien: Quien, completar: bool = False) -> tuple[list[dict], list[dict]]:
    """(etapas, candidatos a alternos). La votación se escribe siempre con $mergeObjects sobre su valor actual (un
    `$set "votacion.mesa"` sobre un null falla). En modo completar solo se llenan las claves vacías."""
    if not v:
        return [], []
    ts = bd.ahora()
    actual = {"$ifNull": ["$votacion", {}]}
    if completar:
        nuevo = {k: {"$cond": [{"$eq": [{"$ifNull": [f"$votacion.{k}", None]}, None]}, _lit(x), f"$votacion.{k}"]}
                 for k, x in v.items()}
        cambia = {"$or": [{"$ne": [{"$ifNull": [f"$votacion.{k}", None]}, None]} for k in CLAVES_VOTACION if k in v]
                  or [False]}
        candidatos = [{"$cond": [{"$and": [{"$eq": [{"$type": "$votacion"}, "object"]}, cambia,
                                           {"$or": [{"$ne": [f"$votacion.{k}", _lit(v[k])]} for k in CLAVES_VOTACION
                                                    if k in v and v[k] is not None] or [False]}]},
                                 [{"campo": "votacion", "valor": _lit({k: v.get(k) for k in CLAVES_VOTACION}),
                                   "fuente": v.get("fuente") or "panel", "ts": ts, "uid": quien.uid}], []]}]
        etapas = [{"$set": {"votacion": {"$mergeObjects": [actual, nuevo]}}}]
    else:
        cambia = {"$or": [{"$and": [{"$ne": [{"$ifNull": [f"$votacion.{k}", None]}, None]},
                                    {"$ne": [f"$votacion.{k}", _lit(v[k])]}]} for k in CLAVES_VOTACION if k in v]
                  or [False]}
        candidatos = [{"$cond": [{"$and": [{"$eq": [{"$type": "$votacion"}, "object"]}, cambia]},
                                 [{"campo": "votacion", "valor": {k: f"$votacion.{k}" for k in CLAVES_VOTACION},
                                   "fuente": {"$ifNull": ["$votacion.fuente", "panel"]}, "ts": ts, "uid": quien.uid}],
                                 []]}]
        etapas = [{"$set": {"votacion": {"$mergeObjects": [actual, _lit(v)]}}}]
    etapas.append(modelo.ETAPA_DERIVAR_VOTACION)
    return etapas, candidatos


# ───────────────────────────── Autorización (1.6) ─────────────────────────────

class AutorizacionIn(BaseModel):
    estado: Literal["si", "no", "revocada", "pendiente"]
    medio: str | None = Field(None, max_length=40)
    canales: list[str] = Field(default_factory=list, max_length=10)
    sensibles: list[str] = Field(default_factory=list, max_length=5)
    evidencia: str | None = Field(None, max_length=500)
    mayor_declarado: bool = False
    fecha_declarada: str | None = Field(None, max_length=10)
    nota: str | None = Field(None, max_length=1000)
    reunion_id: int | None = None

    @field_validator("fecha_declarada")
    @classmethod
    def _f(cls, v):
        return fecha_iso(v) or None


def validar_autorizacion(db: Database, a: AutorizacionIn, quien: Quien) -> dict:
    """Reglas por rol (1.6). Devuelve los campos del evento."""
    canales = list(dict.fromkeys(a.canales or []))
    if set(canales) - set(modelo.CANALES_AUTORIZACION):
        raise HTTPException(422, "Canal de autorización desconocido")
    if a.medio is not None and a.medio not in modelo.MEDIOS_AUTORIZACION:
        raise HTTPException(422, "Medio de autorización desconocido")
    sens = list(dict.fromkeys(a.sensibles or []))
    if set(sens) - set(modelo.SENSIBLES):
        raise HTTPException(422, "Categoría sensible desconocida")
    evidencia = (a.evidencia or "").strip() or None
    medio, implicitos = a.medio, False
    if quien.administra:
        if a.estado == "si" and not canales and medio in (None, "panel"):
            implicitos = True  # el «sí» heredado del panel (tests/test_datos.py:171): llamada, WhatsApp y SMS
        medio = medio or "panel"
    else:
        if a.estado == "pendiente":
            raise _prohibido("Solo el administrador corrige una autorización a «pendiente»")
        if medio in ("panel", "migrado", "declarado_planilla", "fusion"):
            raise HTTPException(422, "Ese medio no se puede usar desde aquí")
        if a.estado == "si":
            permitidos = modelo.MEDIOS_POR_ROL.get(quien.rol, [])
            if medio not in permitidos:
                raise HTTPException(422, f"Use uno de estos medios: {', '.join(modelo.MEDIOS_AUTORIZACION[m] for m in permitidos)}")
            if not evidencia:
                raise HTTPException(422, "Escriba la evidencia de la autorización (por ejemplo, planilla y folio)")
            if not canales:
                raise HTTPException(422, "Marque al menos un canal autorizado")
            if not a.mayor_declarado:
                raise HTTPException(422, "Marque «Declara ser mayor de 18 años»")
        medio = medio or ("verbal_telefono" if quien.rol == "consultor" else "verbal_presencial")
    if sens:
        if a.estado != "si":
            raise HTTPException(422, "Los datos sensibles solo se autorizan con un «sí»")
        if not modelo.leer_ajustes(db).get("sensibles_activos"):
            raise HTTPException(422, "Los datos sensibles están desactivados")
        if medio not in ("escrito", "formulario") and not evidencia:
            raise HTTPException(422, "Los datos sensibles exigen autorización escrita, por formulario o con evidencia")
    return {"estado": a.estado, "medio": medio, "canales": canales if a.estado == "si" else [],
            "canales_implicitos": implicitos, "sensibles": sens, "mayor_declarado": bool(a.mayor_declarado),
            "evidencia": evidencia, "fecha_declarada": a.fecha_declarada, "nota": (a.nota or "").strip() or None,
            "reunion_id": a.reunion_id}


def sumar_dias_habiles(desde: date, dias: int) -> date:
    d, n = desde, 0
    while n < dias:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return d


def crear_solicitud(db: Database, pid: int | None, tipo: str, quien: Quien | None, descripcion: str | None,
                    canal: str | None = None) -> int:
    """`solicitudes` (1.8) con su plazo legal en días hábiles. Marca `reclamo_en_tramite` en la ficha."""
    plazos = {"consulta": 10, "registro": None}
    dias = plazos.get(tipo, 15)
    sid = bd.siguiente_id(db, "solicitudes")
    ts = bd.ahora()
    db.solicitudes.insert_one({
        "_id": sid, "persona_id": pid, "tipo": tipo, "canal": canal, "descripcion": descripcion,
        "creado_por": autor(quien) if quien else None, "ts": ts,
        "vence": sumar_dias_habiles(modelo.hoy_local(), dias).isoformat() if dias else None,
        "estado": "pendiente", "respuesta": None, "resuelto_por": None, "resuelto_en": None})
    if pid is not None and tipo != "registro":
        db.personas.update_one({"_id": pid}, {"$set": {"reclamo_en_tramite": True}})
    return sid


def derivar_autorizacion(db: Database, pid: int) -> dict:
    """Escribe en la ficha los campos derivados de sus eventos (`consentimiento_vigente`) y recalcula el abordaje (que
    pasa a «no contactar» con un «no»). Con «no», borra los sensibles."""
    eventos = list(db.autorizaciones.find({"persona_id": pid}))
    d = modelo.consentimiento_vigente(eventos)
    cambios = dict(d)
    if d["consentimiento"] == "no":
        cambios.update(sensibles={}, sensibles_autorizados=[])
    db.personas.update_one({"_id": pid}, {"$set": cambios})
    from . import acercamientos as ac  # aquí: acercamientos importa este módulo
    ac.recalcular_abordaje(db, pid)
    return d


def registrar_autorizacion(db: Database, pid: int, quien: Quien, evento: dict, acercamiento_id: int | None = None) -> int:
    """Inserta el evento (solo inserción) y deriva la ficha. «revocada» abre una solicitud de revocatoria."""
    aid = bd.siguiente_id(db, "autorizaciones")
    aviso = modelo.leer_ajustes(db).get("aviso_privacidad") or {}
    db.autorizaciones.insert_one({
        "_id": aid, "persona_id": pid, **evento, "evidencia_sha256": None, "evidencia_fila": None,
        "texto_version": aviso.get("version"), "acercamiento_id": acercamiento_id, "uid": quien.uid,
        "usuario": quien.usuario, "rol": quien.rol, "capturado_por": None, "confirmada_por": None,
        "clave_migracion": None, "ts": bd.ahora()})
    derivar_autorizacion(db, pid)
    if evento["estado"] == "revocada":
        crear_solicitud(db, pid, "revocatoria", quien, "Revocó la autorización")
    bd.auditar(db, quien, "autorizacion", "persona", pid,
               {"autorizacion_id": aid, "medio": evento.get("medio"), "canales": evento.get("canales")},
               campos=["autorizacion"], estado=evento["estado"])
    return aid


@r.post("/personas/{pid}/autorizacion")
def autorizar(pid: int, body: AutorizacionIn, request: Request, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("personas.autorizacion"))):
    previa = _idempotente(db, quien, request)
    if previa is not None:
        return previa
    p = proyeccion.persona_activa(db, pid)
    exigir_ficha_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "autorizacion")
    if not quien.administra and p.get("consentimiento") == "no" and body.estado != "si":
        raise HTTPException(409, dict(proyeccion.NO_AUTORIZO))
    evento = validar_autorizacion(db, body, quien)
    registrar_autorizacion(db, pid, quien, evento)
    escribir(db, pid, [etapa_actualizado(quien)])
    bd.recalcular_completitud(db, [pid])
    return _guardar_idem(db, quien, request, 200, ficha_respuesta(db, quien, pid), pid)


# ───────────────────────────── Edición ─────────────────────────────

BASE_A_CAMPO = {"puesto_id": "votacion.puesto_id", "puesto_texto": "votacion.puesto_texto", "donde": "votacion.donde",
                "municipio": "votacion.municipio"}
BASE_PERMITIDOS = frozenset(SIMPLES) | {"cedula", "tipo_documento", "telefono", "telefono2", "lugar_id", "mesa",
                                       "puesto_votacion", "consentimiento", "consentimiento_fecha",
                                       *BASE_A_CAMPO.values()}


def _condiciones_base(base: dict | None) -> list[dict]:
    """La comparación por campo: la escritura solo se aplica si cada campo sigue con el valor que el cliente mostró."""
    out = []
    for k, v in (base or {}).items():
        campo = BASE_A_CAMPO.get(k, k)
        if campo not in BASE_PERMITIDOS:
            continue
        if not (v is None or isinstance(v, (str, int, float, bool))):
            raise HTTPException(422, f"Valor de base no válido para {k}")
        out.append({campo: {"$in": [None, ""]}} if _vacio(v) else {campo: v})
    return out


def _cambiada(db: Database, pid: int, base: dict, quien: Quien) -> HTTPException:
    p = db.personas.find_one({"_id": pid}) or {}
    campos, valores = [], {}
    menor = modelo.es_menor(p)
    for k, v in (base or {}).items():
        campo = BASE_A_CAMPO.get(k, k)
        if campo not in BASE_PERMITIDOS:
            continue
        actual = p
        for parte in campo.split("."):
            actual = actual.get(parte) if isinstance(actual, dict) else None
        if (None if _vacio(actual) else actual) != (None if _vacio(v) else v):
            campos.append(k)
            valores[k] = None if (k in ("telefono", "telefono2") and menor and not quien.administra) else actual
    return HTTPException(409, {"mensaje": "Otra persona cambió estos datos mientras usted editaba", "codigo": "cambiada",
                               "campos": campos, "valores_actuales": valores})


def _detalle(k: str, antes: Any, despues: Any, ctx_sens: set) -> dict:
    """Entrada de la auditoría con las máscaras de 1.9 (cédulas: 3 últimos dígitos; lo sensible, oculto)."""
    if k in ("cedula", "cedulas_anteriores"):
        return {"antes": acceso.enmascarar_cedula(antes), "despues": acceso.enmascarar_cedula(despues)}
    if k in ("lider", "sensibles"):
        return {"antes": "(oculto)", "despues": "(oculto)"}
    if k == "etiquetas":
        f = lambda xs: ["(oculto)" if e in ctx_sens else e for e in xs or []]  # noqa: E731
        return {"antes": f(antes), "despues": f(despues)}
    return {"antes": antes, "despues": despues}


@r.patch("/personas/{pid}")
def editar(pid: int, body: PersonaIn, modo: Literal["completar"] | None = None, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("personas.editar"))):
    antes = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(antes, quien, "editar")
    datos = body.model_dump(exclude_unset=True)
    base = datos.pop("base", None)
    completar = modo == "completar"
    p_rol = _es_planillero(quien)
    adm = quien.administra
    ts = bd.ahora()
    avisos_op: list[str] = []
    if p_rol:
        for k in VEDADOS_P:
            if k in datos and not (k == "consentimiento_fecha" and datos.get("consentimiento")):
                raise _prohibido(f"Su rol no puede cambiar «{k}»", campo=k)
    condiciones = _condiciones_base(base)
    sets: dict = {}
    candidatos: list[dict] = []
    procedencia: dict = {}
    etapas_extra: list[dict] = []
    diff: dict = {}
    despues = dict(antes)
    sens_et = proyeccion.etiquetas_sensibles(db)

    def poner(k: str, v: Any) -> None:
        actual = antes.get(k)
        if (None if _vacio(actual) else actual) == v:
            return
        if v is None and not _vacio(actual) and p_rol:
            raise HTTPException(422, "Pida la corrección al administrador: su rol no puede vaciar un dato")
        if completar and not _vacio(actual):
            if k in modelo.CAMPOS_PROCEDENCIA and v is not None:
                candidatos.append(_alterno_entrante(k, v, ts, quien.uid))
            avisos_op.append(f"«{modelo.ETIQUETAS_CAMPOS.get(k, k)}» ya tenía otro valor: el nuevo quedó como alterno")
            return
        if completar:
            sets[k] = {"$cond": [_vacio_expr(k), _lit(v), f"${k}"]}
        else:
            sets[k] = _lit(v)
            if k in modelo.CAMPOS_PROCEDENCIA:
                candidatos.append(_alterno_viejo(k, v, ts, quien.uid))
        if k in modelo.CAMPOS_PROCEDENCIA:
            procedencia[k] = {"fuente": "panel", "ts": ts, "uid": quien.uid}
        diff[k] = _detalle(k, actual, v, sens_et)
        despues[k] = v

    # Campos simples
    for k in SIMPLES:
        if k in datos:
            poner(k, _limpiar_simple(k, datos[k]))
    if "nombre" in sets:
        despues["nombre_norm"] = tx.nombre_norm(despues["nombre"])
        sets["nombre_norm"] = _lit(despues["nombre_norm"]) if not completar else sets["nombre"]
        sets["nombre_fon"] = _lit(modelo.claves_foneticas(despues["nombre"]))
    # Edad y fecha: edad_ref y los derivados se escriben juntos
    if "edad" in sets or "fecha_nacimiento" in sets:
        if "edad" in sets and despues.get("edad") is not None:
            despues["edad_ref"] = modelo.hoy_local().isoformat()
            sets["edad_ref"] = _lit(despues["edad_ref"])
        nac = modelo.calcular_nac(despues)
        for k2, v2 in nac.items():
            sets[k2] = _lit(v2)
    # Cédula y tipo de documento
    if "cedula" in datos or "tipo_documento" in datos:
        tipo = datos.get("tipo_documento", antes.get("tipo_documento"))
        nueva = validar_documento(datos["cedula"], tipo) if "cedula" in datos else antes.get("cedula")
        actual = antes.get("cedula") or None
        if nueva != actual:
            if actual and completar:
                raise HTTPException(422, "La cédula escrita es distinta de la de esta ficha: son personas diferentes")
            if actual and p_rol:
                raise _prohibido("Su rol no puede cambiar una cédula existente; pida la corrección al administrador",
                                 campo="cedula")
            if actual and not (body.motivo_cambio_cedula or "").strip():
                raise HTTPException(422, "Escriba el motivo del cambio de cédula")
            cedula_ocupada(db, nueva, pid)
            if nueva and es_suprimida(db, nueva):  # también A: solo el alta sigue, con forzar_suprimida
                raise HTTPException(409, dict(SUPRIMIDA))
            sets["cedula"] = _lit(nueva)
            sets["cedula_origen"] = _lit("panel" if nueva else None)
            if actual:
                candidatos.append(_alterno_viejo("cedula", nueva, ts, quien.uid))
                sets["cedulas_anteriores"] = {"$setUnion": [{"$ifNull": ["$cedulas_anteriores", []]}, [actual]]}
                condiciones.append({"cedula": actual})
            else:
                condiciones.append({"cedula": {"$in": [None, ""]}})
            procedencia["cedula"] = {"fuente": "panel", "ts": ts, "uid": quien.uid}
            diff["cedula"] = _detalle("cedula", actual, nueva, sens_et)
            if body.motivo_cambio_cedula:
                diff["motivo_cambio_cedula"] = body.motivo_cambio_cedula.strip()
            despues["cedula"] = nueva
            if nueva and "tipo_documento" not in datos and not antes.get("tipo_documento"):
                datos["tipo_documento"] = "CC"
        if "tipo_documento" in datos and datos["tipo_documento"] != antes.get("tipo_documento"):
            if p_rol and antes.get("cedula") and "cedula" not in sets:
                raise _prohibido("Su rol no puede cambiar el tipo de documento de una cédula existente",
                                 campo="tipo_documento")
            poner("tipo_documento", datos["tipo_documento"])
    if p_rol and datos.get("cedula") and despues.get("tipo_documento") == "TI":
        raise HTTPException(422, "No se registran menores de edad")
    # Lugar
    if "lugar_id" in datos and datos["lugar_id"] != antes.get("lugar_id"):
        if datos["lugar_id"] is None and p_rol and antes.get("lugar_id") is not None:
            raise HTTPException(422, "Pida la corrección al administrador: su rol no puede vaciar un dato")
        lg = db.lugares.find_one({"_id": datos["lugar_id"]}) if datos["lugar_id"] else None
        if datos["lugar_id"] and lg is None:
            raise HTTPException(422, "Lugar no existe")
        if not (completar and antes.get("lugar_id") is not None):
            sets.update(lugar_id=_lit(lg["_id"] if lg else None), zona=_lit(lg["zona"] if lg else None))
            # Barrio o vereda elegido a mano: se conserva al recalcular y la persona sigue el punto del lugar (o el de
            # su placa). Un punto puesto en el mapa no se mueve. Quitar el lugar vuelve a la ubicación automática.
            if antes.get("geo_manual") not in bd.PUNTO_MANUAL:
                sets["geo_manual"] = _lit("lugar" if lg else False)
            diff["lugar_id"] = {"antes": antes.get("lugar_id"), "despues": datos["lugar_id"]}
            despues["lugar_id"] = datos["lugar_id"]
    # Teléfonos (1.2): todos los números del texto; el primero a la posición 0 (o 1 para telefono2)
    etapas_tel: list[dict] = []
    for campo, posicion in (("telefono", 0), ("telefono2", 1)):
        if campo not in datos:
            continue
        if _vacio(datos[campo]):
            actual = antes.get(campo)
            if not actual:
                continue
            if not adm:
                raise HTTPException(422, "Use «Marcar como equivocado» o «Ya no lo usa»")
            etapas_tel += modelo.expr_estado_telefono(actual, {"estado": "retirado", "estado_por": quien.uid,
                                                              "estado_en": ts})
            diff[campo] = {"antes": actual, "despues": None, "retirado": True}
            continue
        nums = numeros(datos[campo])
        if nums == [antes.get(campo)] and campo == "telefono":
            continue
        etapas_tel += etapas_telefonos(nums, quien, "panel", posicion=None if completar else posicion)
        diff[campo] = {"antes": antes.get(campo), "despues": nums[0] if len(nums) == 1 else nums}
        despues["telefonos"] = modelo.unir_telefonos(modelo.telefonos_de(despues), nums)
        despues.update(modelo.derivar_telefonos(despues["telefonos"]))
    # Votación
    dv = {k: datos[k] for k in VOTACION_ENTRADA if k in datos}
    etapas_v: list[dict] = []
    if dv:
        if p_rol:
            vacios = [k for k in ("puesto_id", "puesto_texto", "mesa") if k in dv and _vacio(dv[k])]
            v_act = antes.get("votacion") if isinstance(antes.get("votacion"), dict) else {}
            if any((k == "mesa" and (v_act.get("mesa") is not None or antes.get("mesa")))
                   or (k != "mesa" and (v_act.get("puesto_id") is not None or v_act.get("puesto_texto")
                                        or antes.get("puesto_votacion"))) for k in vacios):
                raise HTTPException(422, "Pida la corrección al administrador: su rol no puede vaciar un dato")
        v = cambios_votacion(db, {**dv, "_pid": pid}, quien, completar=completar)
        etapas_v, cand_v = etapas_votacion(v, quien, completar)
        candidatos += cand_v
        if v:
            procedencia["votacion"] = {"fuente": "panel", "ts": ts, "uid": quien.uid}
            diff["votacion"] = {"antes": {k: (antes.get("votacion") or {}).get(k) for k in CLAVES_VOTACION}
                                if isinstance(antes.get("votacion"), dict) else None,
                                "despues": {k: v.get(k) for k in CLAVES_VOTACION if k in v}}
            despues["votacion"] = {**(antes.get("votacion") if isinstance(antes.get("votacion"), dict) else {}), **v}
    # Etiquetas (con etiquetas_base: la diferencia; P nunca toca las sensibles)
    if body.etiquetas is not None:
        validas = {e["_id"] for e in db.etiquetas.find({}, {"_id": 1})}
        nuevas = [e for e in dict.fromkeys(body.etiquetas) if e in validas]
        if p_rol and set(nuevas) & sens_et:
            raise _prohibido("Su rol no puede usar esa etiqueta", campo="etiquetas")
        if body.etiquetas_base is not None:
            base_et = set(body.etiquetas_base)
            agregar = [e for e in nuevas if e not in base_et]
            quitar = [e for e in base_et - set(nuevas) if not (p_rol and e in sens_et)]
            if agregar or quitar:
                sets["etiquetas"] = {"$setDifference": [{"$setUnion": [{"$ifNull": ["$etiquetas", []]}, _lit(agregar)]},
                                                        _lit(quitar)]}
                diff["etiquetas"] = _detalle("etiquetas", sorted(base_et), nuevas, sens_et)
        else:
            actuales = list(antes.get("etiquetas") or [])
            if p_rol:
                guardadas = [e for e in actuales if e in sens_et]
                final = list(dict.fromkeys(guardadas + nuevas))
                if set(final) != set(actuales):
                    sets["etiquetas"] = {"$concatArrays": [
                        {"$filter": {"input": {"$ifNull": ["$etiquetas", []]}, "as": "e",
                                     "cond": {"$in": ["$$e", _lit(sorted(sens_et))]}}}, _lit(nuevas)]}
                    diff["etiquetas"] = _detalle("etiquetas", actuales, final, sens_et)
            elif nuevas != actuales:
                sets["etiquetas"] = _lit(nuevas)
                diff["etiquetas"] = _detalle("etiquetas", actuales, nuevas, sens_et)
        despues["etiquetas"] = nuevas
    # Campos propios: campo por campo
    if body.extra is not None:
        activos = {c["clave"]: c for c in db.campos.find({"activo": True}, {"clave": 1, "sensible": 1})}
        poner_x, quitar_x = {}, []
        actual_x = antes.get("extra") or {}
        for k, v in body.extra.items():
            c = activos.get(k)
            if c is None:
                continue
            if c.get("sensible") and not adm:
                raise _prohibido("Su rol no puede cambiar ese campo", campo=f"extra.{k}")
            if _vacio(v):
                if k in actual_x:
                    if p_rol:
                        raise HTTPException(422, "Pida la corrección al administrador: su rol no puede vaciar un dato")
                    quitar_x.append(k)
            else:
                v = str(v)[:500] if not isinstance(v, (int, float, bool)) else v
                if actual_x.get(k) != v:
                    poner_x[k] = v
        if poner_x:
            etapas_extra.append({"$set": {"extra": {"$mergeObjects": [{"$ifNull": ["$extra", {}]}, _lit(poner_x)]}}})
        if quitar_x:
            etapas_extra.append({"$unset": [f"extra.{k}" for k in quitar_x]})
        if poner_x or quitar_x:
            diff["extra"] = {"antes": {k: ("(oculto)" if (activos[k].get("sensible")) else actual_x.get(k))
                                       for k in [*poner_x, *quitar_x]},
                             "despues": {k: ("(oculto)" if activos[k].get("sensible") else poner_x.get(k))
                                         for k in [*poner_x, *quitar_x]}}
    # Datos sensibles: solo con la categoría autorizada y los sensibles activos (1.3)
    if body.sensibles is not None:
        if not modelo.leer_ajustes(db).get("sensibles_activos"):
            raise HTTPException(422, "Los datos sensibles están desactivados")
        autorizados = set(antes.get("sensibles_autorizados") or [])
        poner_s, quitar_s = {}, []
        for c, v in body.sensibles.items():
            if c not in modelo.SENSIBLES:
                raise HTTPException(422, "Categoría sensible desconocida")
            if c not in autorizados:
                raise HTTPException(422, f"El titular no autorizó «{modelo.SENSIBLES[c]['etiqueta']}»")
            if _vacio(v):
                quitar_s.append(c)
            elif v not in modelo.SENSIBLES[c]["valores"]:
                raise HTTPException(422, "Valor sensible no válido")
            else:
                poner_s[c] = v
        if poner_s:
            etapas_extra.append({"$set": {"sensibles": {"$mergeObjects": [{"$ifNull": ["$sensibles", {}]},
                                                                          _lit(poner_s)]}}})
        if quitar_s:
            etapas_extra.append({"$unset": [f"sensibles.{c}" for c in quitar_s]})
        if poner_s or quitar_s:
            diff["sensibles"] = {"categorias": sorted([*poner_s, *quitar_s]), "valores": "(oculto)"}
    # Autorización por PATCH (crea un evento con las reglas de 1.6)
    evento = None
    if "consentimiento" in datos and datos["consentimiento"] is not None:
        estado = datos["consentimiento"]
        detalles = any(datos.get(k) for k in ("consentimiento_medio", "consentimiento_canales", "evidencia"))
        if estado != (antes.get("consentimiento") or "pendiente") or detalles:
            evento = validar_autorizacion(db, AutorizacionIn(
                estado=estado, medio=datos.get("consentimiento_medio"), canales=datos.get("consentimiento_canales") or [],
                evidencia=datos.get("evidencia"), mayor_declarado=bool(datos.get("mayor_declarado")),
                fecha_declarada=datos.get("consentimiento_fecha") if not adm else None), quien)
    claves_avance = modelo.completados(antes, despues)
    if evento and evento["estado"] == "si" and antes.get("consentimiento") != "si":
        claves_avance = list(dict.fromkeys([*claves_avance, "autorizacion"]))
    etapas: list[dict] = []
    if candidatos:
        sets["alternos"] = expr_alternos(candidatos)
    if procedencia:
        sets["procedencia"] = {"$mergeObjects": [{"$ifNull": ["$procedencia", {}]}, _lit(procedencia)]}
    if sets:
        etapas.append({"$set": sets})
    etapas += etapas_tel + etapas_v + etapas_extra
    hubo = bool(etapas) or evento is not None or ("consentimiento_fecha" in datos and adm)
    if hubo:
        etapas.append(etapa_avance(claves_avance, quien))
        etapas.append(etapa_actualizado(quien))
        if not escribir(db, pid, etapas, condiciones):
            if "cedula" in sets:
                actual = (db.personas.find_one({"_id": pid}, {"cedula": 1}) or {}).get("cedula")
                if actual and actual != antes.get("cedula"):
                    raise HTTPException(409, {"mensaje": "Otra persona registró una cédula en esta ficha mientras "
                                              "usted editaba", "codigo": "cambiada", "campos": ["cedula"],
                                              "valores_actuales": {"cedula": actual if adm else
                                                                   acceso.enmascarar_cedula(actual)}})
            raise _cambiada(db, pid, base, quien)
    if evento is not None:
        registrar_autorizacion(db, pid, quien, evento)
    if "consentimiento_fecha" in datos and adm:
        db.personas.update_one({"_id": pid}, {"$set": {"consentimiento_fecha": datos["consentimiento_fecha"] or None}})
        diff["consentimiento_fecha"] = {"antes": antes.get("consentimiento_fecha"),
                                        "despues": datos["consentimiento_fecha"] or None}
    if "direccion" in diff or "lugar_id" in diff:
        georreferenciar_y_punto(db, [pid])
    if "cedula" in diff:
        bd.cerrar_coincidencias_imposibles(db, [pid])
    if hubo:
        bd.recalcular_completitud(db, [pid])
    if diff:
        campos = sorted({CANONICO.get(k, k) for k in diff if k != "motivo_cambio_cedula"})
        bd.auditar(db, quien, "editar", "persona", pid, diff, campos=campos, completados=claves_avance)
    return ficha_respuesta(db, quien, pid, avisos_op)


# ───────────────────────────── Alta (2.4) ─────────────────────────────

class NuevaPersona(PersonaIn):
    nombre: str = Field(..., min_length=3, max_length=160)
    telefonos: list[str] | None = Field(None, max_length=10)
    forzar: bool = False
    forzar_suprimida: bool = False
    reunion_id: int | None = None
    autorizacion: AutorizacionIn | None = None


def _parecidas(db: Database, nombre: str, telefonos: list[str] | None = None, cedula: str | None = None,
               excluir: int | None = None) -> list[tuple[dict, float]]:
    """Fichas parecidas (2.4): candidatas por clave fonética, por cualquiera de sus números, por la cédula o por la
    palabra más rara del nombre; puntaje con `ComparadorNombres`. Corte: 0,80, o mismo teléfono y 0,60."""
    toks = tx.tokens_nombre(nombre)
    if not toks:
        return []
    n = tx.nombre_norm(nombre)
    claves = modelo.claves_foneticas(nombre)
    nums = [t for t in telefonos or [] if t]
    raro = max(toks, key=len)
    o: list[dict] = [{"nombre_fon": {"$in": claves}}, {"nombre_norm": {"$regex": re.escape(raro)}}]
    if nums:
        o += [{"telefonos.numero": {"$in": nums}}, {"telefono": {"$in": nums}}, {"telefono2": {"$in": nums}}]
    if cedula:
        o.append({"cedula": cedula})
    cand = list(db.personas.find({**bd.ACTIVA, "_id": {"$ne": excluir}, "$or": o}, proyeccion.CAMPOS_PARA_FILA).limit(400))
    comp = ComparadorNombres([tx.tokens_nombre(c.get("nombre")) for c in cand] + [toks])
    out = []
    for c in cand:
        s = comp.puntaje(toks, tx.tokens_nombre(c.get("nombre")))[0]
        s = max(s, fuzz.token_set_ratio(n, c.get("nombre_norm") or "") / 100 * 0.95)
        mismo_tel = bool(set(nums) & {t.get("numero") for t in modelo.telefonos_de(c)})
        if s >= 0.80 or (mismo_tel and s >= 0.60) or (cedula and c.get("cedula") == cedula):
            out.append((c, s))
    out.sort(key=lambda x: -x[1])
    return out[:8]


def filas_parecidas(db: Database, quien: Quien, encontradas: list[tuple[dict, float]], cedula: str | None) -> list[dict]:
    acceso.registrar_lecturas(db, quien, [c["_id"] for c, _ in encontradas])
    ctx = proyeccion.contexto(db)
    filas = proyeccion.filas_para(quien, [proyeccion.fila_completa(c, ctx) for c, _ in encontradas])
    for f, (c, s) in zip(filas, encontradas):
        f["parecido"] = round(s * 100)
        f["tiene_cedula"] = bool(c.get("cedula"))
        f["cedula_distinta"] = bool(cedula and c.get("cedula") and c["cedula"] != cedula)
    return filas


def _reunion_permitida(db: Database, rid: int | None, quien: Quien) -> dict | None:
    if not rid:
        return None
    reu = db.reuniones.find_one({"_id": rid})
    if reu is None:
        raise HTTPException(422, "La reunión no existe")
    if not quien.administra and reu.get("creado_por_uid") != quien.uid and not reu.get("abierta_a_equipo"):
        raise _prohibido("Esa reunión no es suya ni está abierta al equipo")
    return reu


def _alta_simultanea(db: Database, doc: dict) -> None:
    """Altas de los últimos 10 minutos con la misma clave fonética y el mismo teléfono o lugar → coincidencia."""
    claves = doc.get("nombre_fon") or []
    o = []
    nums = [t["numero"] for t in doc.get("telefonos") or []]
    if nums:
        o.append({"telefonos.numero": {"$in": nums}})
    if doc.get("lugar_id") is not None:
        o.append({"lugar_id": doc["lugar_id"]})
    if not claves or not o:
        return
    limite = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat()
    otros = db.personas.find({**bd.ACTIVA, "_id": {"$ne": doc["_id"]}, "creado_en": {"$gte": limite},
                              "nombre_fon": {"$in": claves}, "$or": o}, {"_id": 1}).limit(5)
    for x in otros:
        a, b = sorted((x["_id"], doc["_id"]))
        cid = bd.siguiente_id(db, "coincidencias")
        db.coincidencias.update_one({"persona_id": a, "candidato_id": b}, {"$setOnInsert": {
            "_id": cid, "persona_id": a, "candidato_id": b, "puntaje": None, "estado": "pendiente",
            "motivo": "alta_simultanea", "detalle": "Altas parecidas en menos de 10 minutos", "creado_en": bd.ahora()}},
            upsert=True)


@r.post("/personas", status_code=201)
def crear(body: NuevaPersona, request: Request, db: Database = Depends(obtener_db),
          quien: Quien = Depends(requiere("personas.crear"))):
    previa = _idempotente(db, quien, request)
    if previa is not None:
        return previa
    p_rol = _es_planillero(quien)
    adm = quien.administra
    datos = body.model_dump(exclude_unset=True)
    if p_rol:
        for k in VEDADOS_P:
            if k in datos:
                raise _prohibido(f"Su rol no puede cambiar «{k}»", campo=k)
    hoy = modelo.hoy_local()
    doc_datos: dict = {}
    for k in SIMPLES:
        if k in datos:
            v = _limpiar_simple(k, datos[k])
            if v is not None:
                doc_datos[k] = v
    tipo = datos.get("tipo_documento")
    cedula = validar_documento(datos.get("cedula"), tipo)
    if cedula and not tipo:
        tipo = "CC"
    nums = list(dict.fromkeys([*numeros(datos.get("telefono")), *numeros(datos.get("telefono2")),
                               *(n for t in body.telefonos or [] for n in numeros(t))]))
    previo = {**doc_datos, "tipo_documento": tipo, "creado_en": bd.ahora()}
    if p_rol and (tipo == "TI" or modelo.es_menor(previo, hoy)):
        raise HTTPException(422, "No se registran menores de edad")
    cedula_ocupada(db, cedula)
    if es_suprimida(db, cedula, doc_datos.get("nombre"), nums):
        if not (adm and body.forzar_suprimida and body.autorizacion and body.autorizacion.estado == "si"):
            raise HTTPException(409, dict(SUPRIMIDA))
    lg = db.lugares.find_one({"_id": body.lugar_id}, {"zona": 1}) if body.lugar_id else None
    if body.lugar_id and lg is None:
        raise HTTPException(422, "Lugar no existe")
    reunion = _reunion_permitida(db, body.reunion_id, quien)
    evento = validar_autorizacion(db, body.autorizacion, quien) if body.autorizacion else None
    if not body.forzar:
        encontradas = _parecidas(db, doc_datos["nombre"], nums, cedula)
        if encontradas:
            raise HTTPException(409, {"mensaje": "Ya hay personas parecidas", "codigo": "parecidas",
                                      "parecidas": filas_parecidas(db, quien, encontradas, cedula)})
    fuente = "reunion" if reunion else "manual"
    ts = bd.ahora()
    doc = bd.nueva_persona(db, doc_datos, fuente)
    fuente_tel = "reunion" if reunion else "panel"
    tels = [modelo.telefono_nuevo(n, fuente_tel, hoy.isoformat(), agregado_por=quien.uid) for n in nums]
    doc.update({"telefonos": tels, **modelo.derivar_telefonos(tels), "tipo_documento": tipo, "cedula": cedula,
                "cedula_origen": "panel" if cedula else None, "cedula_verificada": bool(doc_datos.get("cedula_verificada")),
                "creado_por": autor(quien), "actualizado_por": {**autor(quien), "ts": ts},
                "nombre_fon": modelo.claves_foneticas(doc["nombre"]), "abordaje": None, "abordaje_seq": 0,
                "situacion": None, "requiere_actualizacion": None, "en_curso": None})
    if doc.get("edad") is not None:
        doc["edad_ref"] = hoy.isoformat()
    doc.update(modelo.calcular_nac(doc, hoy))
    v = cambios_votacion(db, {k: datos[k] for k in VOTACION_ENTRADA if k in datos}, quien)
    if v:
        doc["votacion"] = v
        doc.update(modelo.derivar_votacion(v))
    procedencia = {k: {"fuente": "panel", "ts": ts, "uid": quien.uid} for k in modelo.CAMPOS_PROCEDENCIA
                   if not _vacio(doc.get(k))}
    doc["procedencia"] = procedencia
    if body.etiquetas:
        validas = {e["_id"] for e in db.etiquetas.find({}, {"_id": 1})}
        sens = proyeccion.etiquetas_sensibles(db)
        if p_rol and set(body.etiquetas) & sens:
            raise _prohibido("Su rol no puede usar esa etiqueta", campo="etiquetas")
        doc["etiquetas"] = [e for e in dict.fromkeys(body.etiquetas) if e in validas]
    if body.extra:
        activos = {c["clave"]: c for c in db.campos.find({"activo": True}, {"clave": 1, "sensible": 1})}
        extra = {}
        for k, x in body.extra.items():
            if k in activos and not _vacio(x):
                if activos[k].get("sensible") and not adm:
                    raise _prohibido("Su rol no puede cambiar ese campo", campo=f"extra.{k}")
                extra[k] = str(x)[:500] if not isinstance(x, (int, float, bool)) else x
        doc["extra"] = extra
    if reunion:
        doc["asistencias"] = [{"reunion_id": reunion["_id"], "rol": None, "nota": None, "creado_en": ts}]
        doc["ultimo_contacto"] = reunion["fecha"]
        doc["reunion_origen"] = reunion["_id"]  # la reunión donde se registró (cuenta como persona nueva de esa reunión)
    if lg:  # barrio o vereda elegido a mano: georreferenciar lo conserva y toma su punto (o el de la placa)
        doc.update({"lugar_id": lg["_id"], "zona": lg["zona"], "geo_manual": "lugar"})
    completados = modelo.completados(None, doc)
    doc["avance"] = {k: {"uid": quien.uid, "ts": ts} for k in completados}
    try:
        db.personas.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, {"mensaje": "La cédula ya pertenece a otra ficha", "codigo": "cedula_ocupada"}) from None
    pid = doc["_id"]
    georreferenciar_y_punto(db, [pid])
    if evento:
        registrar_autorizacion(db, pid, quien, evento)
        if evento["estado"] == "si":
            db.personas.update_one({"_id": pid, "avance.autorizacion": None},
                                   {"$set": {"avance.autorizacion": {"uid": quien.uid, "ts": ts}}})
            completados.append("autorizacion")
    bd.recalcular_completitud(db, [pid])
    if reunion:
        from . import acercamientos as ac
        ac.crear_automatico(db, pid, reunion, quien)
    _alta_simultanea(db, {**doc, "_id": pid})
    bd.auditar(db, quien, "crear", "persona", pid, {"fuente": fuente, "reunion_id": body.reunion_id},
               campos=sorted({CANONICO.get(k, k) for k in [*doc_datos, *(["cedula"] if cedula else []),
                                                           *(["telefono"] if nums else []), *(["puesto"] if v else [])]}),
               completados=completados)
    return _guardar_idem(db, quien, request, 201, ficha_respuesta(db, quien, pid), pid)


@r.get("/parecidas")
def parecidas_alta(nombre: str = Query("", max_length=160), cedula: str | None = Query(None, max_length=20),
                   telefono: str | None = Query(None, max_length=60), db: Database = Depends(obtener_db),
                   quien: Quien = Depends(requiere("personas.parecidas", limitar=True))):
    """Búsqueda en vivo del alta (7.6): filas del rol."""
    if len(tx.nombre_norm(nombre)) < 3:
        return []
    c = tx.cedula(cedula) or None
    return filas_parecidas(db, quien, _parecidas(db, nombre, tx.telefonos(telefono) if telefono else [], c), c)


@r.get("/personas/{pid}/parecidas")
def parecidas(pid: int, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("personas.parecidas", limitar=True))):
    p = proyeccion.cargar(db, pid)
    nums = [t.get("numero") for t in modelo.telefonos_de(p)]
    return filas_parecidas(db, quien, _parecidas(db, p["nombre"], nums, p.get("cedula"), pid), p.get("cedula"))


# ───────────────────────────── Teléfonos ─────────────────────────────

class TelefonoIn(BaseModel):
    numero: str = Field(..., min_length=7, max_length=120)
    whatsapp: bool | None = None
    confirmado: bool = False
    principal: bool = False
    anterior_no_usa: bool = False
    nota: str | None = Field(None, max_length=300)


@r.post("/personas/{pid}/telefonos")
def agregar_telefono(pid: int, body: TelefonoIn, request: Request, db: Database = Depends(obtener_db),
                     quien: Quien = Depends(requiere("personas.telefonos"))):
    previa = _idempotente(db, quien, request)
    if previa is not None:
        return previa
    p = proyeccion.persona_activa(db, pid)
    exigir_ficha_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "telefonos")
    nums = numeros(body.numero)
    consultor = _es_consultor(quien)
    # El que dicta el titular al consultor entra confirmado; en el panel, «sin verificar» salvo que lo confirme
    estado = "confirmado" if (consultor or body.confirmado) else "sin_verificar"
    anterior = p.get("telefono")
    etapas = etapas_telefonos(nums, quien, "consultor" if consultor else "panel", estado=estado, forzar=estado == "confirmado",
                              whatsapp=body.whatsapp, nota=body.nota, posicion=0 if body.principal else None)
    if body.principal and body.anterior_no_usa and anterior and anterior not in nums:
        etapas = modelo.expr_estado_telefono(anterior, {"estado": "no_usa", "estado_por": quien.uid,
                                                         "estado_en": bd.ahora()})[:-1] + etapas
    antes_tel = modelo.tiene_dato(p, "telefono")
    completados = [] if antes_tel else ["telefono"]
    escribir(db, pid, [*etapas, etapa_avance(completados, quien), etapa_actualizado(quien)])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "telefono_agregar", "persona", pid,
               {"numeros": [acceso.enmascarar_telefono(n) for n in nums], "principal": body.principal},
               campos=["telefono"], completados=completados)
    return _guardar_idem(db, quien, request, 200, ficha_respuesta(db, quien, pid), pid)


class TelefonoCambio(BaseModel):
    estado: Literal["sin_verificar", "confirmado", "no_usa", "equivocado", "inexistente"] | None = None
    whatsapp: bool | None = None
    no_contactar: bool | None = None
    nota: str | None = Field(None, max_length=300)


def _tiene_numero(p: dict, numero: str) -> bool:
    return any(t.get("numero") == numero for t in modelo.telefonos_de(p))


@r.patch("/personas/{pid}/telefonos/{numero}")
def cambiar_telefono(pid: int, numero: str, body: TelefonoCambio, db: Database = Depends(obtener_db),
                     quien: Quien = Depends(requiere("personas.telefonos"))):
    p = proyeccion.persona_activa(db, pid)
    exigir_ficha_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "telefonos")
    if not _tiene_numero(p, numero) or (_es_consultor(quien) and numero not in
                                        [t.get("numero") for t in modelo.usables(modelo.telefonos_de(p))]):
        raise HTTPException(404, "Ese número no está en la ficha")
    cambios = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "nota"}
    if not cambios:
        return ficha_respuesta(db, quien, pid)
    cambios.update(estado_por=quien.uid, estado_en=bd.ahora())
    etapas = modelo.expr_estado_telefono(numero, cambios) + [etapa_sin_telefono(), etapa_actualizado(quien)]
    escribir(db, pid, etapas)
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "telefono_estado", "persona", pid,
               {"numero": acceso.enmascarar_telefono(numero), **{k: v for k, v in cambios.items()
                                                                 if k in ("estado", "whatsapp", "no_contactar")}},
               campos=["telefono"], estado=cambios.get("estado"))
    return ficha_respuesta(db, quien, pid)


@r.post("/personas/{pid}/telefonos/{numero}/principal")
def hacer_principal(pid: int, numero: str, db: Database = Depends(obtener_db),
                    quien: Quien = Depends(requiere("personas.editar"))):
    p = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(p, quien, "telefonos")
    t = next((t for t in modelo.telefonos_de(p) if t.get("numero") == numero), None)
    if t is None:
        raise HTTPException(404, "Ese número no está en la ficha")
    if not modelo.es_usable(t):
        raise HTTPException(422, "Ese número no se puede usar: márquelo como confirmado primero")
    escribir(db, pid, [*modelo.expr_principal(numero), etapa_actualizado(quien)])
    bd.auditar(db, quien, "telefono_principal", "persona", pid, {"numero": acceso.enmascarar_telefono(numero)},
               campos=["telefono"])
    return ficha_respuesta(db, quien, pid)


@r.delete("/personas/{pid}/telefonos/{numero}")
def retirar_telefono(pid: int, numero: str, db: Database = Depends(obtener_db),
                     quien: Quien = Depends(requiere("admin"))):
    """Ningún número se borra: el administrador lo marca «retirado» y una importación no lo reactiva."""
    p = proyeccion.persona_activa(db, pid)
    if not _tiene_numero(p, numero):
        raise HTTPException(404, "Ese número no está en la ficha")
    escribir(db, pid, [*modelo.expr_estado_telefono(numero, {"estado": "retirado", "estado_por": quien.uid,
                                                            "estado_en": bd.ahora()}), etapa_actualizado(quien)])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "telefono_retirar", "persona", pid, {"numero": acceso.enmascarar_telefono(numero)},
               campos=["telefono"])
    return ficha_respuesta(db, quien, pid)


# ───────────────────────────── Seguimiento ─────────────────────────────

class DuplicadoIn(BaseModel):
    con_id: int
    nota: str | None = Field(None, max_length=500)


@r.post("/personas/{pid}/duplicado")
def reportar_duplicado(pid: int, body: DuplicadoIn, request: Request, db: Database = Depends(obtener_db),
                       quien: Quien = Depends(requiere("personas.duplicado"))):
    previa = _idempotente(db, quien, request)
    if previa is not None:
        return previa
    p = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(p, quien, "duplicado")
    if body.con_id == pid or db.personas.count_documents({"_id": body.con_id, **bd.ACTIVA}, limit=1) == 0:
        raise HTTPException(404, "La otra ficha no existe")
    a, b = sorted((pid, body.con_id))
    nuevo = bd.siguiente_id(db, "coincidencias")
    db.coincidencias.update_one({"persona_id": a, "candidato_id": b}, {"$setOnInsert": {
        "_id": nuevo, "persona_id": a, "candidato_id": b, "puntaje": None, "estado": "pendiente", "motivo": "reporte",
        "detalle": (body.nota or "").strip() or None, "creado_por": autor(quien), "creado_en": bd.ahora()}}, upsert=True)
    c = db.coincidencias.find_one({"persona_id": a, "candidato_id": b}, {"_id": 1})
    bd.auditar(db, quien, "reportar_duplicado", "persona", pid, {"coincidencia_id": c["_id"], "con_id": body.con_id})
    return _guardar_idem(db, quien, request, 200, {"id": c["_id"]}, pid)


class ActualizacionIn(BaseModel):
    nota: str | None = Field(None, max_length=1000)
    pedir: bool = False  # A: pide una actualización (motivo «administrador»)


@r.post("/personas/{pid}/actualizacion")
def marcar_atendido(pid: int, body: ActualizacionIn, db: Database = Depends(obtener_db),
                    quien: Quien = Depends(requiere("personas.editar"))):
    """«Marcar como atendido»: la única vía que borra `requiere_actualizacion` (1.7). A también puede pedir una."""
    p = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(p, quien, "editar")
    if body.pedir:
        if not quien.administra:
            raise _prohibido()
        escribir(db, pid, [etapa_requiere("administrador", quien, body.nota, solo_si_falta=False), etapa_actualizado(quien)])
        bd.auditar(db, quien, "pedir_actualizacion", "persona", pid, {"nota": body.nota})
        return ficha_respuesta(db, quien, pid)
    previo = p.get("requiere_actualizacion")
    if not previo:
        return ficha_respuesta(db, quien, pid)
    escribir(db, pid, [{"$set": {"requiere_actualizacion": None}}, etapa_actualizado(quien)])
    bd.auditar(db, quien, "actualizacion_atendida", "persona", pid,
               {"motivo": previo.get("motivo"), "pedida_por": previo.get("usuario"), "nota": body.nota},
               campos=["requiere_actualizacion"])
    return ficha_respuesta(db, quien, pid)


class SituacionIn(BaseModel):
    estado: Literal["activa", "fallecida", "no_reside"]
    confirmar: bool = False


def etapa_situacion(estado: str, quien: Quien | None, fuente: str, confirmada: bool = False) -> dict:
    valor = {"estado": estado, "confirmada": confirmada, "reportado_por": autor(quien) if quien else None,
             "ts": bd.ahora(), "fuente": fuente}
    return {"$set": {"situacion": _lit(valor), "en_curso": None}}


@r.post("/personas/{pid}/situacion")
def situacion(pid: int, body: SituacionIn, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("personas.situacion"))):
    """P y C reportan (sin confirmar); A confirma o revierte. La persona sale de colas y listas sin borrar nada."""
    p = proyeccion.persona_activa(db, pid)
    exigir_ficha_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "situacion")
    if not quien.administra and (body.estado == "activa" or body.confirmar):
        raise _prohibido("Solo el administrador confirma o revierte una situación")
    escribir(db, pid, [etapa_situacion(body.estado, quien, "panel", confirmada=quien.administra and
                                       (body.confirmar or body.estado == "activa")), etapa_actualizado(quien)])
    bd.auditar(db, quien, "situacion", "persona", pid, {"confirmada": body.confirmar}, campos=["situacion"],
               estado=body.estado)
    return ficha_respuesta(db, quien, pid)


class NoDisponibleIn(BaseModel):
    campo: Literal["cedula", "telefono", "mesa", "puesto", "edad", "sexo"]
    motivo: Literal["no_la_dio", "no_tiene", "no_sabe"] | None = None
    quitar: bool = False


@r.post("/personas/{pid}/no-disponible")
def no_disponible(pid: int, body: NoDisponibleIn, db: Database = Depends(obtener_db),
                  quien: Quien = Depends(requiere("personas.no_disponible"))):
    """«No lo tiene / No sabe / No la dio»: saca el campo de `faltan` y de las listas durante `dias_reintento_dato`."""
    p = proyeccion.persona_activa(db, pid)
    exigir_ficha_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "no_disponible")
    if _es_consultor(quien) and body.campo not in ("cedula", "puesto", "mesa"):
        raise _prohibido("Su rol solo marca la cédula, el puesto y la mesa", campo=body.campo)
    if body.quitar:
        etapa = {"$unset": [f"no_disponible.{body.campo}"]}
    else:
        if body.motivo is None:
            raise HTTPException(422, "Elija el motivo")
        marca = {"motivo": body.motivo, "uid": quien.uid, "ts": bd.ahora()}
        etapa = {"$set": {"no_disponible": {"$mergeObjects": [{"$ifNull": ["$no_disponible", {}]},
                                                              _lit({body.campo: marca})]}}}
    escribir(db, pid, [etapa, etapa_actualizado(quien)])
    bd.auditar(db, quien, "no_disponible", "persona", pid, {"campo": body.campo, "motivo": body.motivo,
                                                            "quitar": body.quitar}, campos=[body.campo])
    return ficha_respuesta(db, quien, pid)


# ───────────────────────────── Notas y ubicación ─────────────────────────────

class NotaIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)
    reunion_id: int | None = None


@r.post("/personas/{pid}/notas", status_code=201)
def nota(pid: int, body: NotaIn, request: Request, db: Database = Depends(obtener_db),
         quien: Quien = Depends(requiere("personas.notas"))):
    previa = _idempotente(db, quien, request)
    if previa is not None:
        return previa
    p = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(p, quien, "nota")
    nueva = {"id": str(ObjectId()), "texto": body.texto.strip(), "autor": quien.usuario, "autor_uid": quien.uid,
             "creado_en": bd.ahora(), "reunion_id": body.reunion_id}
    # Ya no toca `ultimo_contacto`: solo los acercamientos efectivos y las reuniones cuentan como contacto
    escribir(db, pid, [{"$set": {"notas": {"$concatArrays": [{"$ifNull": ["$notas", []]}, [_lit(nueva)]]}}},
                       etapa_actualizado(quien)])
    bd.auditar(db, quien, "nota", "persona", pid, {"reunion_id": body.reunion_id})
    return _guardar_idem(db, quien, request, 201, ficha_respuesta(db, quien, pid), pid)


@r.delete("/personas/{pid}/notas/{nid}")
def borrar_nota(pid: int, nid: str, db: Database = Depends(obtener_db),
                quien: Quien = Depends(requiere("personas.notas"))):
    p = proyeccion.persona_activa(db, pid)
    proyeccion.exigir_tratable(p, quien, "nota")
    n = next((n for n in p.get("notas") or [] if n.get("id") == nid), None)
    if n is None:
        raise HTTPException(404, "La nota no existe")
    if not quien.administra and n.get("autor_uid") != quien.uid:
        raise _prohibido("Solo puede borrar sus propias notas")
    escribir(db, pid, [{"$set": {"notas": {"$filter": {"input": {"$ifNull": ["$notas", []]}, "as": "n",
                                                        "cond": {"$ne": ["$$n.id", nid]}}}}}])
    bd.auditar(db, quien, "borrar_nota", "persona", pid, {"nota": nid})
    return ficha_respuesta(db, quien, pid)


class UbicacionIn(BaseModel):
    lat: float = Field(..., ge=6.3, le=7.5)
    lon: float = Field(..., ge=-74.6, le=-73.6)
    fuente: Literal["gps"] | None = None
    precision_m: int | None = Field(None, ge=0, le=100)


@r.put("/personas/{pid}/ubicacion")
def ubicar(pid: int, body: UbicacionIn, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("personas.ubicar"))):
    antes = proyeccion.persona_activa(db, pid, {"lat": 1, "lon": 1, "punto": 1, "consentimiento": 1})
    proyeccion.exigir_tratable(antes, quien, "ubicar")
    lat, lon = round(body.lat, 6), round(body.lon, 6)
    completados = [] if modelo.tiene_dato(antes, "ubicacion") else ["ubicacion"]
    escribir(db, pid, [{"$set": {"lat": lat, "lon": lon, "punto": _lit(modelo.punto(lat, lon)), "geo_precision": "manual",
                                 "geo_manual": "punto", "geo_fuente": _lit(body.fuente),
                                 "precision_m": _lit(body.precision_m)}},
                       etapa_avance(completados, quien), etapa_actualizado(quien)])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "ubicar", "persona", pid,
               {"antes": [antes.get("lat"), antes.get("lon")], "despues": [lat, lon], "fuente": body.fuente},
               campos=["ubicacion"], completados=completados)
    return ficha_respuesta(db, quien, pid)


@r.delete("/personas/{pid}/ubicacion")
def ubicacion_automatica(pid: int, db: Database = Depends(obtener_db),
                         quien: Quien = Depends(requiere("personas.ubicar"))):
    p = proyeccion.persona_activa(db, pid, {"consentimiento": 1})
    proyeccion.exigir_tratable(p, quien, "ubicar")
    escribir(db, pid, [{"$set": {"geo_manual": False, "geo_fuente": None, "precision_m": None}}, etapa_actualizado(quien)])
    georreferenciar_y_punto(db, [pid])
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "ubicacion_automatica", "persona", pid, None, campos=["ubicacion"])
    return ficha_respuesta(db, quien, pid)


# ───────────────────────────── Fusión y supresión (solo A y K) ─────────────────────────────

class FusionIn(BaseModel):
    con_id: int


@r.post("/personas/{pid}/fusionar")
def fusionar(pid: int, body: FusionIn, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    a = db.personas.find_one({"_id": pid, **bd.ACTIVA}, {"cedula": 1})
    b = db.personas.find_one({"_id": body.con_id, **bd.ACTIVA}, {"cedula": 1})
    if a is None or b is None or pid == body.con_id:
        raise HTTPException(404, "Alguna de las dos fichas no existe")
    if a.get("cedula") and b.get("cedula") and a["cedula"] != b["cedula"]:
        raise HTTPException(409, "Las dos fichas tienen cédulas distintas: son personas diferentes")
    bd.fusionar(db, pid, body.con_id, quien, quien.ip)
    db.acercamientos.update_many({"persona_id": body.con_id}, {"$set": {"persona_id": pid}})
    db.autorizaciones.update_many({"persona_id": body.con_id}, {"$set": {"persona_id": pid}})
    from . import acercamientos as ac
    ac.recalcular_abordaje(db, pid)
    return ficha_respuesta(db, quien, pid)


@r.delete("/personas/{pid}")
def suprimir(pid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("admin"))):
    """Supresión a pedido del titular (Ley 1581): borra los datos personales de la ficha y de las unidas con ella,
    quita sus datos de la auditoría y deja una huella cifrada para que una importación no la vuelva a crear."""
    if not db.personas.find_one({"_id": pid}, {"_id": 1}):
        raise HTTPException(404, "No existe")
    ids = bd.suprimir(db, pid, quien, quien.ip) or [pid]
    # Los acercamientos quedan anónimos (los indicadores no cambian) y se borra la idempotencia de esas fichas
    db.acercamientos.update_many({"persona_id": {"$in": ids}}, {"$set": {"nota": None, "telefono": None,
                                                                          "suprimido": True}})
    db.idempotencia.delete_many({"persona_id": {"$in": ids}})
    return {"ok": True}
