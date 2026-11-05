"""Acercamientos y trabajo de campo (sección 4): registro, anulación, historial, «Mi trabajo», colas del consultor,
«siguiente», «tomar» e insignias.

* Un acercamiento es de solo inserción: un error se corrige anulándolo (el autor durante 24 h; A y K siempre), y la
  anulación revierte los efectos sobre teléfonos y situación si siguen como los dejó.
* `abordaje` tiene una sola vía de escritura: insertar o anular hace `$inc abordaje_seq`; después se recalcula
  `resumen_abordaje` y se escribe con el filtro `{_id, abordaje_seq: leído}` (hasta 3 intentos).
* `BASE_COLA` es una sola y la usan todas las listas, `siguiente` y `tomar`. `siguiente` es atómico: dos consultores
  nunca reciben a la misma persona.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from .. import acceso, modelo, proyeccion
from .. import db as bd
from ..acceso import Quien, requiere
from ..seguridad import obtener_db
from . import personas as per
from .filtros import alcance_de, base_cola, en_alcance_consultor, exigir_alcance_consultor, falta, telefonos_ocultos

r = APIRouter(prefix="/api", tags=["acercamientos"])

POR_PAGINA_COLA, PAGINAS_COLA = 20, 10
MINUTOS_EN_CURSO = 20
MAX_EN_CURSO = 3
HORAS_ANULAR = 24
CANALES_P = ("visita", "reunion")


def BASE_COLA(db: Database, quien: Any, hoy: date | None = None, ajustes: dict | None = None) -> dict:  # noqa: N802
    """La base de la cola (4.5): VIGENTE, con teléfono usable, contacto habilitado (o pendiente con la política y
    alguna fuente distinta de trámites), sin reclamo, adulto conocido, sin «no contactar», libre y en su alcance."""
    return base_cola(db, quien, hoy, ajustes)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _inicio_dia(d: date) -> str:
    """Comienzo del día `d` de Colombia, en texto ISO UTC (como `ts`)."""
    return _iso(datetime.combine(d, datetime.min.time(), modelo.ZONA))


# ───────────────────────────── Resumen ─────────────────────────────

def recalcular_abordaje(db: Database, pid: int) -> dict | None:
    """Recalcula `abordaje` desde los acercamientos no anulados y lo escribe solo si nadie insertó o anuló otro entre
    tanto (`abordaje_seq`); si cambió, vuelve a intentar (hasta 3 veces)."""
    resumen = None
    for _ in range(3):
        p = db.personas.find_one({"_id": pid}, {"abordaje_seq": 1, "consentimiento": 1})
        if p is None:
            return None
        acs = list(db.acercamientos.find({"persona_id": pid, "anulado": {"$ne": True}}))
        resumen = modelo.resumen_abordaje(acs, p.get("consentimiento"))
        if db.personas.update_one({"_id": pid, "abordaje_seq": p.get("abordaje_seq")},
                                  {"$set": {"abordaje": resumen}}).matched_count:
            return resumen
    return resumen


def _tras_cambio(db: Database, pid: int) -> dict | None:
    db.personas.update_one({"_id": pid}, {"$inc": {"abordaje_seq": 1}})
    return recalcular_abordaje(db, pid)


# ───────────────────────────── Reuniones como acercamiento (4.4) ─────────────────────────────

def crear_automatico(db: Database, pid: int, reunion: dict, quien: Any) -> int | None:
    """Asistir a una reunión cuenta como abordaje: `{canal: reunion, resultado: contesto, auto: true}`."""
    if db.acercamientos.find_one({"persona_id": pid, "reunion_id": reunion["_id"], "auto": True,
                                  "anulado": {"$ne": True}}, {"_id": 1}):
        return None
    aid = bd.siguiente_id(db, "acercamientos")
    db.acercamientos.insert_one(_documento(aid, pid, quien, canal="reunion", resultado="contesto", telefono=None,
                                           nota=None, fecha=reunion.get("fecha") or modelo.hoy_local().isoformat(),
                                           reunion_id=reunion["_id"], auto=True))
    _tras_cambio(db, pid)
    return aid


def anular_automatico(db: Database, pid: int, rid: int, quien: Any, motivo: str) -> int:
    """Quitar al asistente o borrar la reunión anula su acercamiento automático (nunca se borra)."""
    n = db.acercamientos.update_many({"persona_id": pid, "reunion_id": rid, "auto": True, "anulado": {"$ne": True}},
                                     {"$set": {"anulado": True, "anulado_por": getattr(quien, "uid", None),
                                               "anulado_en": bd.ahora(), "motivo_anulacion": motivo}}).modified_count
    if n:
        _tras_cambio(db, pid)
    return n


# ───────────────────────────── Registro (4.2) ─────────────────────────────

class DictadosIn(BaseModel):
    cedula: str | None = Field(None, max_length=20)
    cedula_confirmacion: str | None = Field(None, max_length=20)
    puesto_id: int | None = None
    mesa: str | int | None = None


class AcercamientoIn(BaseModel):
    canal: Literal["llamada", "whatsapp", "sms", "visita", "reunion", "correo", "otro"]
    resultado: Literal["contesto", "no_contesto", "buzon", "volver_llamar", "numero_equivocado", "numero_inexistente",
                       "actualizo_datos", "pidio_informacion", "solicitud_derechos", "no_contactar", "no_vive_aqui",
                       "fallecio"]
    telefono_indice: int | None = Field(None, ge=0, le=50)
    telefono: str | None = Field(None, max_length=20)
    nota: str | None = Field(None, max_length=2000)
    proximo: str | None = Field(None, max_length=10)
    proximo_franja: Literal["manana", "tarde", "noche"] | None = None
    confirma_numero: bool = False
    alcance: Literal["numero", "persona"] | None = None
    pedir_actualizacion: bool = False
    se_fue_del_municipio: bool = False
    solicitud_tipo: Literal["consulta", "correccion", "supresion", "otro"] = "consulta"
    autorizacion: per.AutorizacionIn | None = None
    datos_dictados: DictadosIn | None = None
    excepcion: str | None = Field(None, max_length=300)

    @field_validator("proximo")
    @classmethod
    def _p(cls, v):
        return per.fecha_iso(v) or None


def _documento(aid: int, pid: int, quien: Any, *, canal: str, resultado: str, telefono: str | None, nota: str | None,
               fecha: str, **campos) -> dict:
    doc = {"_id": aid, "persona_id": pid, "ts": bd.ahora(), "fecha": fecha, "uid": getattr(quien, "uid", None),
           "usuario": getattr(quien, "usuario", None), "rol": getattr(quien, "rol", None), "canal": canal,
           "telefono": telefono, "resultado": resultado, "efectivo": resultado in modelo.EFECTIVOS, "nota": nota,
           "proximo": None, "proximo_franja": None, "confirma_numero": False, "alcance": None, "reunion_id": None,
           "autorizacion_id": None, "datos_dictados": [], "efectos": [], "fuera_de_horario": False, "auto": False,
           "anulado": False, "anulado_por": None, "anulado_en": None, "motivo_anulacion": None, "suprimido": False,
           "clave_migracion": None}
    doc.update(campos)
    return doc


def fuera_de_horario(ajustes: dict, ahora: datetime | None = None) -> bool:
    """¿Fuera de `ajustes.horario` (hora de Colombia)? La Ley 2300 se usa solo como aviso: no bloquea."""
    local = (ahora or _ahora()).astimezone(modelo.ZONA)
    h = ajustes.get("horario") or {}
    rango = h.get("semana") if local.weekday() < 5 else h.get("sabado") if local.weekday() == 5 else h.get("domingo")
    if not rango or not isinstance(rango, (list, tuple)) or len(rango) != 2:
        return True
    hm = local.strftime("%H:%M")
    return not (str(rango[0]) <= hm < str(rango[1]))


def _no_contactable(motivo: str) -> HTTPException:
    mensajes = {"no_autorizo": "Esta persona no autorizó el contacto", "menor": "No se contacta a menores de edad",
                "edad_desconocida": "No se sabe si es mayor de edad", "reclamo": "Tiene un reclamo en trámite",
                "situacion": "Se reportó como fallecida o que ya no vive en Yondó",
                "pendiente": "No ha autorizado el contacto", "no_habilitado": "Su autorización falta confirmarla",
                "canal": "No autorizó ese canal"}
    return HTTPException(409, {"mensaje": mensajes.get(motivo, "No se puede contactar"), "codigo": "no_contactable",
                               "motivo": motivo})


def _telefono_elegido(p: dict, body: AcercamientoIn) -> str | None:
    us = [t.get("numero") for t in modelo.usables(modelo.telefonos_de(p))]
    if body.telefono_indice is not None:
        if body.telefono_indice >= len(us):
            raise HTTPException(422, "Ese número no se puede usar")
        return us[body.telefono_indice]
    if body.telefono:
        if body.telefono not in us:
            raise HTTPException(422, "Ese número no se puede usar")
        return body.telefono
    if body.canal in proyeccion.CANALES_TELEFONO:
        raise HTTPException(422, "Elija el número con el que se comunicó")
    return None


def _cedula_dictada(db: Database, p: dict, quien: Quien, d: DictadosIn, aj: dict) -> str | None:
    """2.7: la cédula que dicta el titular va siempre a revisión de A (`conflictos_cedula{motivo: dictada}`), con
    tope diario por consultor. La respuesta es la misma exista o no (no sirve de oráculo)."""
    if not d.cedula:
        return None
    if p.get("cedula"):
        raise HTTPException(422, "Esta ficha ya tiene cédula")
    c = per.validar_documento(d.cedula, "CC")
    if c != per.validar_documento(d.cedula_confirmacion, "CC"):
        raise HTTPException(422, "La cédula y su confirmación no coinciden")
    tope = int(aj.get("tope_cedulas_dictadas") or 0)
    hechas = db.conflictos_cedula.count_documents({"motivo": "dictada", "creado_por.uid": quien.uid,
                                                   "creado_en": {"$gte": _inicio_dia(modelo.hoy_local())}})
    if hechas >= tope:
        raise HTTPException(429, {"mensaje": f"Llegó al tope de {tope} cédulas dictadas hoy", "codigo": "volumen"})
    return c


def _registrar_dictada(db: Database, pid: int, cedula: str, quien: Quien, aid: int) -> None:
    clave = hashlib.sha1(f"dictada|{cedula}|{pid}|consultor|{quien.uid}".encode()).hexdigest()
    nuevo = bd.siguiente_id(db, "conflictos_cedula")
    db.conflictos_cedula.update_one({"clave": clave}, {"$setOnInsert": {
        "_id": nuevo, "clave": clave, "cedula": cedula, "persona_id": pid, "motivo": "dictada", "fuente": "consultor",
        "importacion_id": None, "registro": {"uid": quien.uid, "usuario": quien.usuario, "acercamiento_id": aid},
        "puntaje_nombre": None, "estado": "pendiente", "creado_por": per.autor(quien), "creado_en": bd.ahora(),
        "resuelto_por": None, "resuelto_en": None, "resolucion": None}}, upsert=True)


def _efecto_tel(t: dict, cambios: dict) -> list[dict]:
    """Efectos sobre un número: lo que había y lo que queda, para poder revertirlo al anular."""
    out = []
    for k, v in cambios.items():
        antes = t.get(k) if k != "estado" else (t.get("estado") or "sin_verificar")
        if antes != v:
            out.append({"tipo": f"telefono_{k}", "numero": t.get("numero"), "antes": antes, "despues": v})
    return out


@r.post("/personas/{pid}/acercamientos")
def registrar(pid: int, body: AcercamientoIn, request: Request, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("acercamientos.registrar"))):
    previa = acceso.idempotencia_previa(db, quien, request)
    if previa is not None:
        return previa
    aj = modelo.leer_ajustes(db)
    hoy = modelo.hoy_local()
    p = proyeccion.persona_activa(db, pid)
    consultor = not quien.administra and quien.rol == "consultor"
    planillero = not quien.administra and quien.rol == "planillero"
    # 1. Ficha activa y alcance; para C, además, contactable
    if consultor:
        exigir_alcance_consultor(db, p, quien)
    proyeccion.exigir_tratable(p, quien, "acercamiento")
    if consultor:
        if body.canal in CANALES_P:
            raise per._prohibido("El consultor registra llamadas y mensajes")
        motivo = proyeccion.motivo_no_contactable(p, aj, hoy, body.canal)
        if motivo:
            raise _no_contactable(motivo)
    # 3. Canales de P: visita o reunión, que no usan un número. P no elige número: si lo eligiera, el acercamiento le
    # devolvería entero uno que no ve (el de un menor) y el 422 de un índice inexistente diría cuántos hay
    if planillero and body.canal not in CANALES_P:
        raise per._prohibido("El planillero registra visitas y reuniones")
    if planillero and (body.telefono_indice is not None or body.telefono):
        raise HTTPException(422, "Una visita o una reunión no lleva número")
    # 2. Teléfono
    numero = _telefono_elegido(p, body)
    if body.resultado in ("numero_equivocado", "numero_inexistente") and not numero:
        raise HTTPException(422, "Elija el número")
    if body.resultado == "no_contactar" and body.alcance is None:
        raise HTTPException(422, "Diga si pidió no ser contactado en este número o en ninguno")
    if body.resultado == "no_contactar" and body.alcance == "numero" and not numero:
        raise HTTPException(422, "Elija el número")
    # 4. Autorización (reglas de 1.6)
    evento = per.validar_autorizacion(db, body.autorizacion, quien) if body.autorizacion else None
    # 5. Datos dictados por C (solo si faltan)
    dictada = None
    v_dictada: dict = {}
    avisos: list[str] = []
    if body.datos_dictados:
        if not consultor and not quien.administra:
            raise HTTPException(422, "Escriba esos datos en la ficha")
        d = body.datos_dictados
        dictada = _cedula_dictada(db, p, quien, d, aj)
        if d.puesto_id is not None or d.mesa not in (None, ""):
            datos_v = {k: x for k, x in (("puesto_id", d.puesto_id), ("mesa", d.mesa)) if x not in (None, "")}
            v_dictada = per.cambios_votacion(db, {**datos_v, "_pid": pid}, quien, fuente="consultor", completar=True)
            v_dictada["estado"] = "sin_verificar" if v_dictada.get("estado") != "por_confirmar" else "por_confirmar"
    # 6. Horario: solo aviso
    fuera = body.canal not in CANALES_P and fuera_de_horario(aj)
    if fuera:
        avisos.append("Fuera del horario de contacto: quedó registrado como tal")
    # Efectos
    ts = bd.ahora()
    tels = modelo.telefonos_de(p)
    t = next((x for x in tels if x.get("numero") == numero), {"numero": numero})
    cambios_tel: dict = {}
    if body.resultado == "contesto" and numero:
        if body.confirma_numero:
            cambios_tel["estado"] = "confirmado"
        if body.canal == "whatsapp":
            cambios_tel["whatsapp"] = True
    elif body.resultado == "numero_equivocado":
        cambios_tel["estado"] = "equivocado"
    elif body.resultado == "numero_inexistente":
        cambios_tel["estado"] = "inexistente"
    elif body.resultado == "no_contactar" and body.alcance == "numero":
        cambios_tel["no_contactar"] = True
    efectos = _efecto_tel(t, cambios_tel) if numero else []
    etapas: list[dict] = []
    if efectos:
        etapas += modelo.expr_estado_telefono(numero, {**{e["tipo"][9:]: e["despues"] for e in efectos},
                                                        "estado_por": quien.uid, "estado_en": ts})
        etapas.append(per.etapa_sin_telefono())
    sit = None
    if body.resultado == "fallecio":
        sit = "fallecida"
    elif body.resultado == "no_vive_aqui":
        etapas.append(per.etapa_requiere("direccion", quien, body.nota))
        if body.se_fue_del_municipio:
            sit = "no_reside"
    if sit:
        efectos.append({"tipo": "situacion", "antes": p.get("situacion"), "despues": sit})
        etapas.append(per.etapa_situacion(sit, quien, "acercamiento"))
    if body.resultado == "actualizo_datos" and body.pedir_actualizacion:
        etapas.append(per.etapa_requiere("pedido_consultor", quien, body.nota, solo_si_falta=False))
    if v_dictada:
        ev, _ = per.etapas_votacion(v_dictada, quien, completar=True)
        etapas += ev
    fecha = hoy.isoformat()
    if body.resultado in modelo.EFECTIVOS:
        etapas.append({"$set": {"ultimo_contacto": {"$max": ["$ultimo_contacto", fecha]}}})
    etapas += [{"$set": {"en_curso": None}}, per.etapa_actualizado(quien)]
    per.escribir(db, pid, etapas)
    aid = bd.siguiente_id(db, "acercamientos")
    datos_dictados = (["cedula"] if dictada else []) + (["puesto"] if v_dictada.get("puesto_id") is not None else []) \
        + (["mesa"] if v_dictada.get("mesa") is not None else [])
    db.acercamientos.insert_one(_documento(
        aid, pid, quien, canal=body.canal, resultado=body.resultado, telefono=numero,
        nota=(body.nota or "").strip() or None, fecha=fecha, proximo=body.proximo if body.resultado == "volver_llamar" else None,
        proximo_franja=body.proximo_franja if body.resultado == "volver_llamar" else None,
        confirma_numero=body.confirma_numero, alcance=body.alcance if body.resultado == "no_contactar" else None,
        datos_dictados=datos_dictados, efectos=efectos, fuera_de_horario=fuera, excepcion=body.excepcion))
    if dictada:
        _registrar_dictada(db, pid, dictada, quien, aid)
        avisos.append("Cédula registrada para revisión")
    if body.resultado == "solicitud_derechos":
        per.crear_solicitud(db, pid, body.solicitud_tipo, quien, body.nota, canal=body.canal)
    if body.resultado == "no_contactar" and body.alcance == "persona":
        medio = "verbal_telefono" if body.canal in ("llamada",) else "mensaje" if body.canal in ("whatsapp", "sms") \
            else "verbal_presencial"
        per.registrar_autorizacion(db, pid, quien, {
            "estado": "revocada", "medio": medio, "canales": [], "canales_implicitos": False, "sensibles": [],
            "mayor_declarado": False, "evidencia": f"Pidió no ser contactado ({modelo.CANALES[body.canal]})",
            "fecha_declarada": None, "nota": None, "reunion_id": None}, acercamiento_id=aid)
    if evento:
        aut_id = per.registrar_autorizacion(db, pid, quien, evento, acercamiento_id=aid)
        db.acercamientos.update_one({"_id": aid}, {"$set": {"autorizacion_id": aut_id}})
    resumen = _tras_cambio(db, pid) or {}
    # Llegar al máximo de intentos crea `requiere_actualizacion{no_contesta}` (pasa a la lista de visitas de P)
    if (resumen.get("intentos_sin_exito") or 0) >= _entero(aj, "max_intentos_sin_exito", 4):
        db.personas.update_one({"_id": pid, "requiere_actualizacion": None}, {"$set": {"requiere_actualizacion": {
            "motivo": "no_contesta", "uid": None, "usuario": None, "ts": bd.ahora(), "nota": None}}})
    bd.recalcular_completitud(db, [pid])
    bd.auditar(db, quien, "acercamiento", "persona", pid, {"acercamiento_id": aid, "fuera_de_horario": fuera},
               completados=[k for k in ("puesto", "mesa") if k in datos_dictados] or None,
               canal=body.canal, resultado=body.resultado)
    cuerpo = per.ficha_respuesta(db, quien, pid, avisos)
    cuerpo["acercamiento_id"] = aid
    acceso.idempotencia_guardar(db, quien, request, 200, cuerpo, persona_id=pid)
    return cuerpo


def _fila_acercamiento(a: dict, quien: Quien, menor: bool = False) -> dict:
    """La fila del rol (`proyeccion.acercamiento_para`) con el id de la persona."""
    d = proyeccion.acercamiento_para(a, proyeccion.rol_de(quien), quien.administra, menor)
    return {"id": d.pop("id"), "persona_id": a.get("persona_id"), **d}


@r.get("/personas/{pid}/acercamientos")
def de_persona(pid: int, pagina: int = Query(1, ge=1, le=1000), db: Database = Depends(obtener_db),
               quien: Quien = Depends(requiere("acercamientos.ver"))):
    p = proyeccion.cargar(db, pid)
    per.exigir_ficha_consultor(db, p, quien)
    if not quien.administra and p.get("consentimiento") == "no":
        raise HTTPException(409, dict(proyeccion.NO_AUTORIZO))
    q = {"persona_id": pid, "suprimido": {"$ne": True}}
    total = db.acercamientos.count_documents(q)
    menor = modelo.es_menor(p)
    filas = [_fila_acercamiento(a, quien, menor) for a in db.acercamientos.find(q)
             .sort([("ts", DESCENDING), ("_id", DESCENDING)]).skip((pagina - 1) * 50).limit(50)]
    acceso.registrar_lecturas(db, quien, [pid])
    return {"total": total, "filas": filas}


class AnularIn(BaseModel):
    motivo: str = Field("", max_length=300)


@r.post("/acercamientos/{aid}/anular")
def anular(aid: int, body: AnularIn, db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("acercamientos.registrar"))):
    """El autor puede anular durante 24 h; A y K, siempre. Revierte los efectos sobre teléfonos y situación si el valor
    actual sigue siendo el que dejó este acercamiento. Las autorizaciones y solicitudes no se revierten."""
    a = db.acercamientos.find_one({"_id": aid})
    if a is None or a.get("suprimido"):
        raise HTTPException(404, "El acercamiento no existe")
    pid = a["persona_id"]
    if not quien.administra:
        limite = _iso(_ahora() - timedelta(hours=HORAS_ANULAR))
        if a.get("uid") != quien.uid or str(a.get("ts") or "") < limite:
            raise per._prohibido("Solo su autor lo anula, y durante 24 horas")
    if a.get("anulado"):
        return per.ficha_respuesta(db, quien, pid)
    res = db.acercamientos.update_one({"_id": aid, "anulado": {"$ne": True}}, {"$set": {
        "anulado": True, "anulado_por": quien.uid, "anulado_en": bd.ahora(), "motivo_anulacion": body.motivo.strip() or None}})
    if res.modified_count:
        etapas = []
        for e in a.get("efectos") or []:
            if str(e.get("tipo", "")).startswith("telefono_") and e.get("numero"):
                campo = e["tipo"][9:]
                actual = {"$ifNull": [f"$$t.{campo}", "sin_verificar" if campo == "estado" else None]}
                etapas.append({"$set": {"telefonos": {"$map": {"input": modelo.TELS_ACTUALES, "as": "t", "in": {"$cond": [
                    {"$and": [{"$eq": ["$$t.numero", {"$literal": e["numero"]}]}, {"$eq": [actual, {"$literal": e["despues"]}]}]},
                    {"$mergeObjects": ["$$t", {"$literal": {campo: e["antes"]}}]}, "$$t"]}}}}})
            elif e.get("tipo") == "situacion":
                etapas.append({"$set": {"situacion": {"$cond": [
                    {"$eq": ["$situacion.estado", {"$literal": e["despues"]}]}, {"$literal": e.get("antes")}, "$situacion"]}}})
        if etapas:
            etapas.append(modelo.ETAPA_DERIVAR_TELEFONOS)
            db.personas.update_one({"_id": pid}, etapas)
        _tras_cambio(db, pid)
        bd.recalcular_completitud(db, [pid])
        bd.auditar(db, quien, "anular_acercamiento", "persona", pid, {"acercamiento_id": aid, "motivo": body.motivo},
                   canal=a.get("canal"), resultado=a.get("resultado"))
    if db.personas.count_documents({"_id": pid, **bd.ACTIVA}, limit=1) == 0:
        return {"ok": True}
    return per.ficha_respuesta(db, quien, pid)


@r.get("/acercamientos")
def listar(uid: int | None = None, desde: str | None = None, hasta: str | None = None, resultado: str | None = None,
           pagina: int = Query(1, ge=1, le=10_000), db: Database = Depends(obtener_db),
           quien: Quien = Depends(requiere("admin"))):
    q: dict = {"suprimido": {"$ne": True}}
    if uid is not None:
        q["uid"] = uid
    if resultado:
        q["resultado"] = resultado
    rango = {}
    if desde:
        rango["$gte"] = per.fecha_iso(desde) if len(desde) == 10 else desde
    if hasta:
        rango["$lte"] = per.fecha_iso(hasta) if len(hasta) == 10 else hasta
    if rango:
        q["fecha"] = rango
    total = db.acercamientos.count_documents(q)
    docs = list(db.acercamientos.find(q).sort([("ts", DESCENDING), ("_id", DESCENDING)]).skip((pagina - 1) * 50).limit(50))
    nombres = {p["_id"]: p.get("nombre") for p in db.personas.find({"_id": {"$in": [a["persona_id"] for a in docs]}},
                                                                   {"nombre": 1})}
    return {"total": total, "filas": [{**_fila_acercamiento(a, quien), "persona": nombres.get(a["persona_id"])}
                                      for a in docs]}


# ───────────────────────────── Colas del consultor (4.5) ─────────────────────────────

LISTAS_C = {"por_llamar": "Por llamar", "volver_a_llamar": "Volver a llamar", "seguimiento": "Seguimiento",
            "mis_hoy": "Hoy"}
ORDEN_COLA = {
    "por_llamar": [("completitud", DESCENDING), ("_id", ASCENDING)],
    "volver_a_llamar": [("abordaje.proximo", ASCENDING), ("abordaje.proximo_franja", ASCENDING),
                        ("abordaje.ultimo_fecha", ASCENDING), ("_id", ASCENDING)],
    "seguimiento": [("abordaje.ultimo_fecha", ASCENDING), ("_id", ASCENDING)],
}


def _entero(aj: dict, clave: str, defecto: int) -> int:
    try:
        return int(aj.get(clave)) if aj.get(clave) is not None else defecto
    except (TypeError, ValueError):
        return defecto


def _volver(hoy: date, aj: dict) -> dict:
    limite = (hoy - timedelta(days=_entero(aj, "dias_entre_intentos", 2))).isoformat()
    return {"abordaje.n": {"$gte": 1},
            "abordaje.intentos_sin_exito": {"$lt": _entero(aj, "max_intentos_sin_exito", 4)},
            "$or": [{"abordaje.proximo": {"$ne": None, "$lte": hoy.isoformat()}},
                    {"abordaje.ultimo_resultado": {"$in": list(modelo.SIN_EXITO)},
                     "abordaje.ultimo_fecha": {"$lte": limite}}]}


def condicion_lista(lista: str, hoy: date, aj: dict) -> dict | None:
    """Condición de cada lista sobre BASE_COLA. Las listas no se solapan y quien ya contestó no vuelve a «por llamar»."""
    if lista == "por_llamar":
        return {"$or": [{"abordaje": None}, {"abordaje.n": {"$in": [0, None]}}]}
    if lista == "volver_a_llamar":
        return _volver(hoy, aj)
    if lista == "seguimiento":
        if not aj.get("seguimiento_activo"):
            return None
        limite = (hoy - timedelta(days=_entero(aj, "dias_seguimiento", 60))).isoformat()
        return {"$and": [{"abordaje.estado": "contactado", "abordaje.ultimo_fecha": {"$lte": limite}},
                         {"$nor": [_volver(hoy, aj)]}]}
    raise HTTPException(422, "Lista desconocida")


def consulta_lista(db: Database, quien: Quien, lista: str, hoy: date, aj: dict) -> dict | None:
    cond = condicion_lista(lista, hoy, aj)
    if cond is None:
        return None
    return {"$and": [BASE_COLA(db, quien, hoy, aj), cond]}


def _mis_hoy(db: Database, quien: Quien, hoy: date) -> list[int]:
    vistos: dict[int, None] = {}
    for a in db.acercamientos.find({"uid": quien.uid, "fecha": hoy.isoformat(), "anulado": {"$ne": True},
                                    "auto": {"$ne": True}}, {"persona_id": 1}).sort([("ts", DESCENDING), ("_id", DESCENDING)]):
        vistos.setdefault(a["persona_id"], None)
    return list(vistos)


@r.get("/trabajo/cola")
def cola(lista: str = "por_llamar", pagina: int = Query(1, ge=1, le=PAGINAS_COLA), db: Database = Depends(obtener_db),
         quien: Quien = Depends(requiere("trabajo.cola", limitar=True))):
    per.exigir_listas_del_dia(db, quien)
    hoy, aj = modelo.hoy_local(), modelo.leer_ajustes(db)
    ctx = proyeccion.contexto(db)
    salto = (pagina - 1) * POR_PAGINA_COLA
    if lista == "mis_hoy":
        ids = _mis_hoy(db, quien, hoy)
        total = len(ids)
        ids = ids[salto:salto + POR_PAGINA_COLA]
        por_id = {p["_id"]: p for p in db.personas.find({"_id": {"$in": ids}, **bd.ACTIVA}, proyeccion.CAMPOS_PARA_FILA)}
        docs = [por_id[i] for i in ids if i in por_id]
    else:
        q = consulta_lista(db, quien, lista, hoy, aj)
        if q is None:
            return {"total": 0, "filas": [], "lista": lista}
        total = min(db.personas.count_documents(q), POR_PAGINA_COLA * PAGINAS_COLA)
        docs = list(db.personas.find(q, proyeccion.CAMPOS_PARA_FILA).sort(ORDEN_COLA[lista]).skip(salto)
                    .limit(POR_PAGINA_COLA))
    acceso.registrar_lecturas(db, quien, [p["_id"] for p in docs])
    return {"total": total, "lista": lista, "filas": [proyeccion.fila_cola(p, ctx) for p in docs]}


def _liberar_exceso(db: Database, quien: Quien) -> None:
    """Un usuario tiene como máximo 3 personas tomadas: al tomar una cuarta se libera la más vieja."""
    ahora = _iso(_ahora())
    mias = list(db.personas.find({"en_curso.uid": quien.uid, "en_curso.hasta": {"$gt": ahora}}, {"en_curso": 1})
                .sort([("en_curso.desde", DESCENDING), ("_id", DESCENDING)]))
    for p in mias[MAX_EN_CURSO:]:
        db.personas.update_one({"_id": p["_id"], "en_curso.uid": quien.uid}, {"$set": {"en_curso": None}})


def _marca(quien: Quien) -> dict:
    ahora = _ahora()
    return {"uid": quien.uid, "usuario": quien.usuario, "desde": _iso(ahora),
            "hasta": _iso(ahora + timedelta(minutes=MINUTOS_EN_CURSO))}


@r.post("/trabajo/siguiente")
def siguiente(lista: str = "por_llamar", db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("trabajo.cola", limitar=True))):
    """La siguiente persona de la lista, tomada de forma atómica (`find_one_and_update`): dos consultores nunca
    reciben a la misma. 204 si la cola está vacía (GET /api/trabajo da la explicación y los pendientes)."""
    hoy, aj = modelo.hoy_local(), modelo.leer_ajustes(db)
    if lista not in ORDEN_COLA:
        raise HTTPException(422, "Lista desconocida")
    q = consulta_lista(db, quien, lista, hoy, aj)
    if q is None:
        return Response(status_code=204, headers={"X-Cola": "vacia"})
    ahora = _iso(_ahora())
    # Una nueva: no la que ya tiene en sus manos
    q = {"$and": [q, {"$or": [{"en_curso": None}, {"en_curso.hasta": {"$lte": ahora}}]}]}
    p = db.personas.find_one_and_update(q, {"$set": {"en_curso": _marca(quien)}}, sort=ORDEN_COLA[lista],
                                        projection={"_id": 1}, return_document=ReturnDocument.AFTER)
    if p is None:
        return Response(status_code=204, headers={"X-Cola": "vacia"})
    _liberar_exceso(db, quien)
    return proyeccion.ficha_para(db, quien, p["_id"])


@r.post("/trabajo/tomar/{pid}")
def tomar(pid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("trabajo.cola"))):
    """Toma a una persona fuera de la cola (por ejemplo, una llamada entrante): debe cumplir BASE_COLA, sin las
    condiciones de tiempo de las listas. 409 `tomada` si otro la tiene."""
    hoy, aj = modelo.hoy_local(), modelo.leer_ajustes(db)
    p = proyeccion.persona_activa(db, pid)
    marca = _marca(quien)
    tomada = db.personas.find_one_and_update({"$and": [{"_id": pid}, BASE_COLA(db, quien, hoy, aj)]},
                                             {"$set": {"en_curso": marca}}, projection={"_id": 1})
    if tomada is None:
        ec = p.get("en_curso") if isinstance(p.get("en_curso"), dict) else None
        if ec and ec.get("uid") != quien.uid and str(ec.get("hasta") or "") > _iso(_ahora()):
            raise HTTPException(409, {"mensaje": f"{ec.get('usuario')} está trabajando con esta persona",
                                      "codigo": "tomada", "usuario": ec.get("usuario")})
        motivo = proyeccion.motivo_no_contactable(p, aj, hoy)
        if motivo:
            raise _no_contactable(motivo)
        alcance = alcance_de(db, quien)
        if alcance and db.personas.count_documents({"$and": [{"_id": pid}, alcance]}, limit=1) == 0:
            raise per._prohibido("Esta persona no está en su asignación")
        raise HTTPException(409, {"mensaje": "Esta persona no tiene un número que se pueda usar",
                                  "codigo": "no_contactable", "motivo": "telefono"})
    _liberar_exceso(db, quien)
    return {"hasta": marca["hasta"]}


@r.delete("/trabajo/tomar/{pid}")
def soltar(pid: int, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("trabajo.cola"))):
    q = {"_id": pid} if quien.administra else {"_id": pid, "en_curso.uid": quien.uid}
    n = db.personas.update_one(q, {"$set": {"en_curso": None}}).modified_count
    return {"ok": True, "liberada": bool(n)}


# ───────────────────────────── Mi trabajo (7.7) ─────────────────────────────

def _listas_p(hoy: date, aj: dict, completo: bool = True) -> list[tuple[str, str, dict, str]]:
    """(clave, título, condición, enlace a Habitantes) de las tarjetas del planillero. Sin `completo` (P), la de los
    teléfonos no cuenta a los menores (P no ve sus teléfonos), igual que su enlace a Habitantes (`filtros.filtro`)."""
    dias = int(aj.get("dias_reintento_dato") or 90)
    visitar = ["no_contesta", "sin_telefono_valido", "direccion"]
    sin_tel = falta("telefono", hoy, dias) if completo else {"$and": [falta("telefono", hoy, dias),
                                                                      {"$nor": [telefonos_ocultos(hoy)]}]}
    return [
        ("sin_cedula", "Sin cédula", falta("cedula", hoy, dias), "sin_cedula=1&orden=lugar"),
        ("sin_puesto_mesa", "Sin puesto o mesa", {"$or": [falta("puesto", hoy, dias), falta("mesa", hoy, dias)]},
         "sin_puesto_mesa=1"),
        ("puesto_por_confirmar", "Puesto por confirmar", modelo.filtro_estado_votacion("por_confirmar",
                                                                                         aj.get("eleccion_vigente")),
         "votacion_estado=por_confirmar"),
        ("pendientes_actualizar", "Pendientes de actualizar", {"requiere_actualizacion": {"$ne": None}},
         "requiere_actualizacion=1"),
        ("visitar", "Visitar: no contestan o sin número", {"requiere_actualizacion.motivo": {"$in": visitar}},
         "requiere_actualizacion=" + ",".join(visitar)),
        ("sin_telefono", "Sin teléfono", sin_tel, "sin_telefono=1"),
        ("sin_autorizacion", "Sin autorización", {"consentimiento": {"$in": ["pendiente", None]}},
         "consentimiento=pendiente"),
        ("sin_lugar", "Sin barrio o vereda", falta("lugar", hoy, dias), "sin_lugar=1"),
    ]


def _conteo_periodo(db: Database, quien: Quien, desde: date) -> dict:
    inicio = _inicio_dia(desde)
    if quien.rol == "consultor" and not quien.administra:
        acs = list(db.acercamientos.find({"uid": quien.uid, "ts": {"$gte": inicio}, "anulado": {"$ne": True}},
                                         {"persona_id": 1, "efectivo": 1}))
        return {"acercamientos": len(acs), "personas": len({a["persona_id"] for a in acs}),
                "contactadas": len({a["persona_id"] for a in acs if a.get("efectivo")})}
    q = {"uid": quien.uid, "entidad": "persona", "ts": {"$gte": inicio}}
    return {"creadas": db.auditoria.count_documents({**q, "accion": "crear"}),
            "actualizadas": len(db.auditoria.distinct("entidad_id", {**q, "accion": {"$in": list(modelo.ACCIONES_EDICION)}})),
            "acercamientos": db.acercamientos.count_documents({"uid": quien.uid, "ts": {"$gte": inicio},
                                                               "anulado": {"$ne": True}})}


def _como_usuario(db: Database, uid: int) -> Quien:
    """A y K ven «Mi trabajo» de un usuario (el selector de 7.7): su rol, su alcance y sus conteos."""
    u = db.usuarios.find_one({"_id": uid}, {"clave": 0})
    if u is None or u.get("rol") not in acceso.ROLES:
        raise HTTPException(404, "El usuario no existe")
    asig = u.get("asignacion") or {}
    return Quien(uid=u["_id"], usuario=u.get("usuario"), nombre=u.get("nombre"), rol=u["rol"],
                 permisos=acceso.PERMISOS.get(u["rol"], frozenset()),
                 asignacion=None if u["rol"] in ("admin", "coordinador") else
                 {"lugares": list(asig.get("lugares") or []), "areas": list(asig.get("areas") or [])})


@r.get("/trabajo")
def trabajo(uid: int | None = None, db: Database = Depends(obtener_db),
            quien: Quien = Depends(requiere("trabajo.ver"))):
    if uid is not None and uid != quien.uid:
        if not quien.administra:
            raise per._prohibido("Solo ve su propio trabajo")
        quien = _como_usuario(db, uid)
    hoy, aj = modelo.hoy_local(), modelo.leer_ajustes(db)
    alcance = alcance_de(db, quien)
    asig = per_asignacion(db, quien)
    base = [modelo.filtro_vigente(), {"consentimiento": {"$ne": "no"}}]
    if alcance:
        base.append(alcance)
    # Con teléfono: P y C no cuentan los de un menor (no los ven)
    con_tel = [{"telefono": {"$ne": None}}] + ([] if quien.administra else [{"$nor": [modelo.filtro_menor(hoy)]}])
    pendientes = db.personas.count_documents({"$and": [*base, {"consentimiento": {"$in": ["pendiente", None]}},
                                                       *con_tel]})
    listas = []
    if not quien.administra and quien.rol == "consultor":
        for clave, titulo in LISTAS_C.items():
            if clave == "mis_hoy":
                n = len(_mis_hoy(db, quien, hoy))
            else:
                q = consulta_lista(db, quien, clave, hoy, aj)
                if q is None:
                    continue
                n = db.personas.count_documents(q)
            listas.append({"clave": clave, "titulo": titulo, "n": n, "enlace": f"/trabajo?lista={clave}"})
    else:
        for clave, titulo, cond, enlace in _listas_p(hoy, aj, quien.administra):
            n = db.personas.count_documents({"$and": [*base, cond]})
            listas.append({"clave": clave, "titulo": titulo, "n": n,
                           "enlace": f"/personas?situacion=vigentes&tratables=1&{enlace}"})
        if not quien.administra:
            # Como su enlace a Habitantes (`mios=1`): sin quien no autorizó (quién la editó después no se ve)
            n = db.personas.count_documents({"$and": [dict(bd.ACTIVA), {"consentimiento": {"$ne": "no"}},
                                                      {"$or": [{"creado_por.uid": quien.uid},
                                                               {"actualizado_por.uid": quien.uid}]}]})
            listas.append({"clave": "mis_recientes", "titulo": "Mis registros recientes", "n": n,
                           "enlace": "/personas?mios=1&orden=reciente"})
    semana = hoy - timedelta(days=hoy.weekday())
    return {"rol": quien.rol, "alcance": asig, "listas": listas,
            "politica": {k: aj.get(k) for k in ("contactar_pendientes", "dias_entre_intentos", "max_intentos_sin_exito",
                                                 "seguimiento_activo", "dias_seguimiento")},
            "pendientes_sin_autorizacion": pendientes, "hoy": _conteo_periodo(db, quien, hoy),
            "semana": _conteo_periodo(db, quien, semana)}


def per_asignacion(db: Database, quien: Quien) -> dict | None:
    """Los lugares y áreas asignados (con su nombre); None para A y K."""
    if quien.administra:
        return None
    a = quien.asignacion or {}
    lugares = [{"id": l["_id"], "nombre": l.get("nombre")} for l in
               db.lugares.find({"_id": {"$in": list(a.get("lugares") or [])}}, {"nombre": 1})]
    areas = [{"id": x["_id"], "nombre": x.get("nombre")} for x in
             db.areas.find({"_id": {"$in": list(a.get("areas") or [])}}, {"nombre": 1})]
    return {"lugares": lugares, "areas": areas}


# ───────────────────────────── Insignias (5.4) ─────────────────────────────

@r.get("/insignias")
def insignias(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("insignias"))):
    """Conteos livianos para el menú. Reemplaza pedir todos los indicadores."""
    out = {"calidad": 0, "conflictos": 0, "solicitudes": 0, "situaciones": 0, "trabajo": 0}
    hoy, aj = modelo.hoy_local(), modelo.leer_ajustes(db)
    vigente_req = {"$and": [modelo.filtro_vigente(), {"requiere_actualizacion": {"$ne": None}}]}
    if quien.administra:
        out["calidad"] = len(db.coincidencias.distinct("persona_id", {"estado": "pendiente"}))
        out["conflictos"] = db.conflictos_cedula.count_documents({"estado": "pendiente"})
        out["solicitudes"] = db.solicitudes.count_documents({"estado": {"$in": ["pendiente", "en_tramite"]}})
        out["situaciones"] = db.personas.count_documents({**bd.ACTIVA, "situacion.estado": {"$in": ["fallecida", "no_reside"]},
                                                          "situacion.confirmada": {"$ne": True}})
        out["trabajo"] = db.personas.count_documents(vigente_req)
    elif quien.rol == "planillero":
        # Como «Pendientes de actualizar» de Mi trabajo: sin quien no autorizó (P no ve su `requiere_actualizacion`)
        alcance = alcance_de(db, quien)
        q = {"$and": [vigente_req, {"consentimiento": {"$ne": "no"}}, *([alcance] if alcance else [])]}
        out["trabajo"] = db.personas.count_documents(q)
    elif quien.rol == "consultor":
        q = consulta_lista(db, quien, "volver_a_llamar", hoy, aj)
        out["trabajo"] = db.personas.count_documents(q) if q else 0
    return out


__all__ = ["r", "BASE_COLA", "recalcular_abordaje", "crear_automatico", "anular_automatico", "en_alcance_consultor"]
