"""Calidad de datos: coincidencias por nombre, conflictos de cédula, solicitudes de los titulares, situaciones
reportadas, confirmación de autorizaciones de planilla y nomenclátor de lugares."""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import db as bd
from .. import modelo
from ..acceso import Quien, requiere
from ..pipeline import texto as tx
from ..pipeline.importar import aplicar_registro, georreferenciar
from ..seguridad import Admin, obtener_db, requiere_admin
from . import filtros
from .personas import cedula_en_union, mapa_lugares

r = APIRouter(prefix="/api", tags=["calidad"])


def _resumen(p: dict, lugares: dict) -> dict:
    return {"id": p["_id"], "nombre": p["nombre"], "cedula": p.get("cedula"), "telefono": p.get("telefono"),
            "telefono2": p.get("telefono2"), "correo": p.get("correo"), "direccion": p.get("direccion"),
            "fuentes": p.get("fuentes", []), "edad": p.get("edad"), "sexo": p.get("sexo"),
            "lugar": (lugares.get(p.get("lugar_id")) or {}).get("nombre") or p.get("lugar_texto"),
            "tramites": len(p.get("tramites") or []), "listas": "; ".join(p.get("listas") or []),
            "completitud": p.get("completitud", 0), "consentimiento": p.get("consentimiento")}


# ───────────────────────────── Coincidencias por nombre ─────────────────────────────

@r.get("/coincidencias")
def coincidencias(estado: str = "pendiente", db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    if estado == "pendiente":  # las que ya no se pueden aceptar no se muestran (quedan cerradas)
        bd.cerrar_coincidencias_imposibles(db)
    lista = list(db.coincidencias.find({"estado": estado}).sort("puntaje", -1).limit(300))
    ids = {c["persona_id"] for c in lista} | {c["candidato_id"] for c in lista}
    personas = {p["_id"]: p for p in db.personas.find({"_id": {"$in": list(ids)}, **bd.ACTIVA},
                                                      {"notas": 0, "origen": 0, "asistencias": 0})}
    lugares = mapa_lugares(db)
    return [{"id": c["_id"], "puntaje": c["puntaje"], "detalle": c.get("detalle", {}), "estado": c["estado"],
             "motivo": c.get("motivo"), "persona": _resumen(personas[c["persona_id"]], lugares),
             "candidato": _resumen(personas[c["candidato_id"]], lugares)}
            for c in lista if c["persona_id"] in personas and c["candidato_id"] in personas]


class Decision(BaseModel):
    decision: Literal["aceptar", "rechazar"]
    conservar: Literal["persona", "candidato"] | None = None


def conservar_por_defecto(a: dict, b: dict) -> str:
    """Qué ficha se conserva al unir: la que tiene cédula; si ninguna (o las dos), la más completa."""
    if bool(a.get("cedula")) != bool(b.get("cedula")):
        return "persona" if a.get("cedula") else "candidato"
    return "persona" if (a.get("completitud") or 0) > (b.get("completitud") or 0) else "candidato"


@r.post("/coincidencias/{cid}")
def resolver(cid: int, body: Decision, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    c = db.coincidencias.find_one({"_id": cid, "estado": "pendiente"})
    if c is None:
        raise HTTPException(404, "Ya fue resuelta o no existe")
    marca = {"resuelto_por": adm.usuario, "resuelto_en": bd.ahora()}
    if body.decision == "aceptar":
        a = db.personas.find_one({"_id": c["persona_id"], **bd.ACTIVA}, {"cedula": 1, "completitud": 1})
        b = db.personas.find_one({"_id": c["candidato_id"], **bd.ACTIVA}, {"cedula": 1, "completitud": 1})
        if a is None or b is None or (a.get("cedula") and b.get("cedula") and a["cedula"] != b["cedula"]):
            bd.cerrar_coincidencias_imposibles(db, [c["persona_id"]])
            raise HTTPException(409, "Tienen cédulas distintas" if a and b else "Una de las fichas ya se unió o suprimió")
        conservar = body.conservar or conservar_por_defecto(a, b)
        destino, origen = (a, b) if conservar == "persona" else (b, a)
        db.coincidencias.update_one({"_id": cid}, {"$set": {"estado": "aceptada", "conservada": destino["_id"], **marca}})
        try:
            bd.fusionar(db, destino["_id"], origen["_id"], adm, adm.ip)
        except bd.FusionImposible:
            db.coincidencias.update_one({"_id": cid}, {"$set": {"estado": "pendiente"}})
            raise
        georreferenciar(db, [destino["_id"]])
        return {"ok": True, "id": destino["_id"]}
    db.coincidencias.update_one({"_id": cid}, {"$set": {"estado": "rechazada", **marca}})
    bd.auditar(db, adm, "rechazar_coincidencia", "persona", c["persona_id"], {"candidato": c["candidato_id"]}, adm.ip)
    return {"ok": True}


# ───────────────────────────── Conflictos de cédula ─────────────────────────────

def cedula_ocupada(db: Database, cedula: str, salvo: int | None = None) -> dict | None:
    """La ficha activa que ya tiene esa cédula (actual o anterior), si hay."""
    return db.personas.find_one({"$or": [{"cedula": cedula}, {"cedulas_anteriores": cedula}], "_id": {"$ne": salvo},
                                 **bd.ACTIVA}, {"nombre": 1, "cedula": 1, "lugar_id": 1, "lugar_texto": 1})


def exigir_cedula_libre(db: Database, cedula: str, salvo: int | None = None) -> None:
    """409 `cedula_ocupada` si otra ficha la tiene (o una unión la está moviendo: dice a qué ficha); 409 `suprimida` si
    su titular pidió la supresión. La unión se mira primero: si ya no puede terminar, su origen vuelve con la cédula."""
    traspaso = bd.traspaso_de(db, cedula)
    otra = cedula_ocupada(db, cedula, salvo)
    if otra:
        raise HTTPException(409, {"mensaje": f"La cédula ya pertenece a {otra['nombre']}", "codigo": "cedula_ocupada",
                                  "id": otra["_id"], "nombre": otra["nombre"]})
    if traspaso:
        raise HTTPException(409, cedula_en_union(db, traspaso))
    h = bd.huella(bd.clave_supresion(db), "cedula", cedula)
    if h and db.suprimidos.find_one({"_id": h}, {"_id": 1}):
        raise HTTPException(409, {"mensaje": "El titular de esa cédula pidió la supresión de sus datos",
                                  "codigo": "suprimida"})


ESTADOS_CONFLICTO = ("pendiente", "aplicado", "corregido", "descartado", "reportado")
MOTIVO_DEVUELTA = "Cédula devuelta a su ficha tras una unión que no se hizo"


@r.get("/conflictos")
def conflictos(estado: Literal["pendiente", "aplicado", "corregido", "descartado", "reportado"] = "pendiente",
               db: Database = Depends(obtener_db), _: Quien = Depends(requiere("calidad.ver"))):
    lista = list(db.conflictos_cedula.find({"estado": estado}).sort("_id", -1).limit(300))
    ids = {c["persona_id"] for c in lista} | {c.get("otra_persona") for c in lista if c.get("otra_persona")}
    duenas = {}
    for c in lista:
        if c["motivo"] == "dictada" and c.get("cedula"):
            otra = cedula_ocupada(db, c["cedula"], c["persona_id"])
            if otra:
                duenas[c["_id"]] = otra["_id"]
                ids.add(otra["_id"])
    personas = {p["_id"]: p for p in db.personas.find({"_id": {"$in": list(ids)}, **bd.ACTIVA},
                                                      {"notas": 0, "origen": 0, "asistencias": 0, "tramites": 0})}
    lugares = mapa_lugares(db)
    salida = []
    for c in lista:
        reg = c.get("registro") or {}
        salida.append({
            "id": c["_id"], "motivo": c["motivo"], "cedula": c.get("cedula"), "fuente": c.get("fuente"),
            "estado": c["estado"], "creado_en": c.get("creado_en"), "puntaje_nombre": c.get("puntaje_nombre"),
            "registro": {k: reg.get(k) for k in ("nombre", "cedula", "tipo_documento", "telefonos", "direccion",
                                                 "lugar_texto", "sexo", "edad", "fecha_nacimiento", "fila", "fuente")}
            | {"cedula_digitada": (reg.get("datos") or {}).get("cedula_digitada"),
               "cedula_repetida": (reg.get("datos") or {}).get("cedula_repetida")},
            "persona": _resumen(personas[c["persona_id"]], lugares) if c["persona_id"] in personas else None,
            "otra_persona": _resumen(personas[c["otra_persona"]], lugares) if c.get("otra_persona") in personas else None,
            "duena": _resumen(personas[duenas[c["_id"]]], lugares) if duenas.get(c["_id"]) in personas else None,
            "resolucion": c.get("resolucion")})
    return salida


class ConflictoIn(BaseModel):
    decision: Literal["aplicar", "descartar", "corregir", "reportar"]
    cedula_correcta: str | None = Field(None, max_length=20)
    motivo: str | None = Field(None, max_length=300)


def _cerrar_conflicto(db: Database, c: dict, estado: str, quien: Quien, resolucion: dict) -> None:
    db.conflictos_cedula.update_one({"_id": c["_id"]}, {"$set": {
        "estado": estado, "resuelto_por": quien.uid, "resuelto_en": bd.ahora(), "resolucion": resolucion}})


def _poner_cedula(db: Database, pid: int, cedula: str, origen: str, quien: Quien, antes: str | None,
                  motivo: str | None = None, procedencia: dict | None = None) -> None:
    """Escribe la cédula solo si la ficha sigue activa y con la cédula que se leyó; la anterior pasa a
    `cedulas_anteriores`. `procedencia`: la de la cédula, si no es una escrita ahora en el panel o dictada (la que
    tenía la ficha antes de una unión que no se hizo)."""
    prov = procedencia or {"fuente": "panel" if origen != "consultor" else "consultor", "ts": bd.ahora(),
                           "uid": quien.uid}
    s = {"cedula": cedula, "cedula_origen": origen, "actualizado_en": bd.ahora(),
         "tipo_documento": {"$ifNull": ["$tipo_documento", "CC"]},
         "procedencia": {"$mergeObjects": [{"$ifNull": ["$procedencia", {}]}, {"cedula": {"$literal": prov}}]},
         "actualizado_por": {"$literal": {"uid": quien.uid, "usuario": quien.usuario, "rol": quien.rol, "ts": bd.ahora()}}}
    if antes:
        s["cedulas_anteriores"] = modelo._expr_union("$cedulas_anteriores", {"$literal": [antes]})
    try:
        hecho = db.personas.update_one({"_id": pid, **bd.ACTIVA, "cedula": antes}, [{"$set": s}])
    except DuplicateKeyError:
        raise HTTPException(409, {"mensaje": "Otra ficha tomó esa cédula", "codigo": "cedula_ocupada"})
    if hecho.matched_count == 0:
        raise HTTPException(409, {"mensaje": "La ficha cambió o ya no está activa; recargue", "codigo": "cambiada"})
    bd.cerrar_coincidencias_imposibles(db, [pid])
    bd.derivar(db, [pid])
    bd.auditar(db, quien, "editar", "persona", pid, {"cedula": {"antes": antes, "despues": cedula},
                                                     "motivo_cambio_cedula": motivo}, campos=["cedula"],
               completados=[] if (antes or procedencia) else ["cedula"])


@r.post("/conflictos/{cid}")
def resolver_conflicto(cid: int, body: ConflictoIn, db: Database = Depends(obtener_db),
                       quien: Quien = Depends(requiere("calidad.resolver"))):
    c = db.conflictos_cedula.find_one({"_id": cid, "estado": "pendiente"})
    if c is None:
        raise HTTPException(404, "Ya fue resuelto o no existe")
    pid = c["persona_id"]
    p = db.personas.find_one({"_id": pid, **bd.ACTIVA}, {"cedula": 1, "nombre": 1})
    if p is None and body.decision != "descartar":
        raise HTTPException(409, "La ficha ya se unió o se suprimió; descarte el conflicto")
    detalle = {"conflicto_id": cid, "motivo": c["motivo"], "decision": body.decision}
    if body.decision == "descartar":
        _cerrar_conflicto(db, c, "descartado", quien, {"decision": "descartar"})
    elif body.decision == "corregir":
        ced = tx.cedula(body.cedula_correcta) if body.cedula_correcta else ""
        if not ced:
            raise HTTPException(422, "Escriba la cédula correcta (5 a 11 dígitos)")
        if ced != p.get("cedula"):
            exigir_cedula_libre(db, ced, pid)
            _poner_cedula(db, pid, ced, "panel", quien, p.get("cedula"),
                          body.motivo or "Corrección de un posible error de digitación")
        _cerrar_conflicto(db, c, "corregido", quien, {"decision": "corregir"})
    elif body.decision == "reportar":
        otra = cedula_ocupada(db, c.get("cedula") or "", pid)
        if otra is None:
            raise HTTPException(409, "La cédula ya no pertenece a otra ficha: use «Aplicar»")
        try:
            db.coincidencias.insert_one({"_id": bd.siguiente_id(db, "coincidencias"), "persona_id": pid,
                                         "candidato_id": otra["_id"], "puntaje": c.get("puntaje_nombre") or 0,
                                         "estado": "pendiente", "motivo": "reporte",
                                         "detalle": {"reporte": True, "conflicto_id": cid}})
        except DuplicateKeyError:
            pass
        _cerrar_conflicto(db, c, "reportado", quien, {"decision": "reportar", "candidato_id": otra["_id"]})
    elif c["motivo"] == "dictada":
        if p.get("cedula"):
            raise HTTPException(409, {"mensaje": "La ficha ya tiene cédula", "codigo": "cambiada"})
        exigir_cedula_libre(db, c["cedula"], pid)
        if c.get("fuente") == "fusion":
            # La cédula era de la propia ficha antes de una unión que no se hizo (`bd._devolver_origen`): vuelve con
            # su procedencia de entonces, no como dictada al consultor
            reg = c.get("registro") or {}
            prov = reg.get("procedencia") if isinstance(reg.get("procedencia"), dict) else None
            _poner_cedula(db, pid, c["cedula"], reg.get("cedula_origen") or "panel", quien, None,
                          MOTIVO_DEVUELTA, procedencia={k: prov.get(k) for k in ("fuente", "ts", "uid")} if prov
                          else None)
        else:
            _poner_cedula(db, pid, c["cedula"], "consultor", quien, None, "Cédula dictada por el titular al consultor")
        _cerrar_conflicto(db, c, "aplicado", quien, {"decision": "aplicar"})
    elif c["motivo"] == "posible_digitacion":
        raise HTTPException(422, "Use «Corregir cédula» o «Descartar»: una posible digitación nunca une fichas")
    else:  # nombre distinto o cédula anterior: la fila es de esta persona y la completa
        if not aplicar_registro(db, pid, c.get("registro") or {}, quien):
            raise HTTPException(409, "La ficha ya se unió o se suprimió")
        _cerrar_conflicto(db, c, "aplicado", quien, {"decision": "aplicar"})
    bd.auditar(db, quien, "resolver_conflicto", "persona", pid, detalle)
    return {"ok": True}


# ───────────────────────────── Solicitudes de los titulares ─────────────────────────────

class SolicitudIn(BaseModel):
    persona_id: int | None = None
    tipo: Literal["consulta", "correccion", "supresion", "revocatoria", "otro", "registro"]
    canal: str | None = Field(None, max_length=40)
    descripcion: str = Field(..., min_length=3, max_length=2000)


def _vence(tipo: str, desde: date | None = None) -> str | None:
    dias = modelo.PLAZOS_SOLICITUD.get(tipo)
    return modelo.sumar_dias_habiles(desde or modelo.hoy_local(), dias).isoformat() if dias else None


def _reclamo(db: Database, pid: int | None) -> None:
    """`reclamo_en_tramite` de la ficha: hay un reclamo o una solicitud sin clasificar abierta (`bd.reclamo_abierto`)."""
    if pid is None:
        return
    db.personas.update_one({"_id": pid}, {"$set": {"reclamo_en_tramite": bd.reclamo_abierto(db, pid)}})


@r.post("/solicitudes", status_code=201)
def crear_solicitud(body: SolicitudIn, db: Database = Depends(obtener_db),
                    quien: Quien = Depends(requiere("solicitudes.crear"))):
    if body.persona_id is not None:
        p = db.personas.find_one({"_id": body.persona_id, **bd.ACTIVA})
        if p is None:
            raise HTTPException(404, "No existe")
        en_alcance = getattr(filtros, "en_alcance_consultor", None)  # alcance del consultor (grupo 3)
        if quien.rol == "consultor" and en_alcance is not None and not en_alcance(p, quien):
            raise HTTPException(403, {"mensaje": "Su rol no permite esta acción", "codigo": "permiso"})
    elif body.tipo not in ("registro", "otro", "consulta"):
        raise HTTPException(422, "Indique la persona de la solicitud")
    sid = bd.siguiente_id(db, "solicitudes")
    vence = _vence(body.tipo)
    db.solicitudes.insert_one({
        "_id": sid, "persona_id": body.persona_id, "tipo": body.tipo, "canal": body.canal,
        "descripcion": body.descripcion.strip(), "creado_por": {"uid": quien.uid, "usuario": quien.usuario, "rol": quien.rol},
        "ts": bd.ahora(), "vence": vence, "estado": "pendiente", "respuesta": None, "resuelto_por": None,
        "resuelto_en": None})
    pid = body.persona_id
    if pid is not None:
        # Si la ficha se unió con otra mientras tanto, la solicitud (y su marca) va a la ficha unida: a quien pidió
        # suprimir sus datos no se le llama desde ninguna de las dos. Crear una solicitud solo pone la marca (una
        # lectura de las solicitudes mientras la unión las mueve no la quita)
        pid = bd.unida_en(db, pid) or pid
        bd.marcar_reclamo(db, pid)
        bd.auditar(db, quien, "solicitud_crear", "persona", pid, {"solicitud_id": sid, "tipo": body.tipo})
    else:
        bd.auditar(db, quien, "solicitud_crear", "solicitud", sid, {"tipo": body.tipo})
    return {"id": sid, "vence": vence, "persona_id": pid}


@r.get("/solicitudes")
def solicitudes(estado: str | None = "abiertas", tipo: str | None = None, db: Database = Depends(obtener_db),
                _: Quien = Depends(requiere("calidad.ver"))):
    q: dict = {}
    if estado == "abiertas":
        q["estado"] = {"$in": list(modelo.ABIERTAS)}
    elif estado in modelo.ESTADOS_SOLICITUD:
        q["estado"] = estado
    if tipo in modelo.TIPOS_SOLICITUD:
        q["tipo"] = tipo
    lista = sorted(db.solicitudes.find(q).sort("_id", -1).limit(500),
                   key=lambda s: (s.get("vence") is None, s.get("vence") or "", s["_id"]))  # sin plazo, al final
    nombres = {p["_id"]: p["nombre"] for p in db.personas.find(
        {"_id": {"$in": [s["persona_id"] for s in lista if s.get("persona_id") is not None]}}, {"nombre": 1})}
    hoy = modelo.hoy_local()
    salida = []
    for s in lista:
        vence = modelo.fecha_valida(s.get("vence"))
        dias = (vence - hoy).days if vence else None
        salida.append({"id": s["_id"], "persona_id": s.get("persona_id"), "persona": nombres.get(s.get("persona_id")),
                       "tipo": s["tipo"], "canal": s.get("canal"), "descripcion": s.get("descripcion"),
                       "creado_por": s.get("creado_por"), "ts": s.get("ts"), "vence": s.get("vence"),
                       "dias_restantes": dias, "vencida": dias is not None and dias < 0 and s["estado"] in modelo.ABIERTAS,
                       "estado": s["estado"], "respuesta": s.get("respuesta"), "resuelto_en": s.get("resuelto_en")})
    return salida


class SolicitudCambio(BaseModel):
    estado: Literal["pendiente", "en_tramite", "resuelta", "rechazada"] | None = None
    respuesta: str | None = Field(None, max_length=2000)


@r.patch("/solicitudes/{sid}")
def editar_solicitud(sid: int, body: SolicitudCambio, db: Database = Depends(obtener_db),
                     quien: Quien = Depends(requiere("calidad.resolver"))):
    s = db.solicitudes.find_one({"_id": sid})
    if s is None:
        raise HTTPException(404, "No existe")
    datos = body.model_dump(exclude_unset=True)
    if not datos:
        return {"ok": True}
    if datos.get("estado") in ("resuelta", "rechazada"):
        datos.update(resuelto_por=quien.uid, resuelto_en=bd.ahora())
    elif "estado" in datos:
        datos.update(resuelto_por=None, resuelto_en=None)
    db.solicitudes.update_one({"_id": sid}, {"$set": datos})
    _reclamo(db, s.get("persona_id"))
    detalle = {"solicitud_id": sid, "estado": datos.get("estado")}
    if s.get("persona_id") is not None:
        bd.auditar(db, quien, "solicitud_editar", "persona", s["persona_id"], detalle)
    else:
        bd.auditar(db, quien, "solicitud_editar", "solicitud", sid, detalle)
    return {"ok": True}


# ───────────────────────────── Situaciones reportadas ─────────────────────────────

@r.get("/situaciones")
def situaciones(todas: int = 0, db: Database = Depends(obtener_db), _: Quien = Depends(requiere("calidad.ver"))):
    q: dict = {**bd.ACTIVA, "situacion.estado": {"$in": ["fallecida", "no_reside"]}}
    if not todas:
        q["situacion.confirmada"] = {"$ne": True}
    lugares = mapa_lugares(db)
    return [{"id": p["_id"], "nombre": p["nombre"], "situacion": p.get("situacion"),
             "lugar": (lugares.get(p.get("lugar_id")) or {}).get("nombre") or p.get("lugar_texto")}
            for p in db.personas.find(q, {"nombre": 1, "situacion": 1, "lugar_id": 1, "lugar_texto": 1})
            .sort("situacion.ts", -1).limit(300)]


class SituacionDecision(BaseModel):
    decision: Literal["confirmar", "revertir"]


@r.post("/situaciones/{pid}")
def resolver_situacion(pid: int, body: SituacionDecision, db: Database = Depends(obtener_db),
                       quien: Quien = Depends(requiere("calidad.resolver"))):
    """Confirma lo reportado (la persona sigue fuera de colas e indicadores, sin borrarse) o lo revierte (vuelve a
    estar activa)."""
    p = db.personas.find_one({"_id": pid, **bd.ACTIVA, "situacion.estado": {"$in": ["fallecida", "no_reside"]}},
                             {"situacion": 1})
    if p is None:
        raise HTTPException(404, "No hay una situación reportada para esta persona")
    ts = bd.ahora()
    if body.decision == "confirmar":
        nueva = {**p["situacion"], "confirmada": True, "confirmada_por": quien.uid, "confirmada_en": ts}
    else:
        nueva = {"estado": "activa", "confirmada": True, "reportado_por": quien.uid, "ts": ts, "fuente": "administrador",
                 "revierte": p["situacion"].get("estado")}
    db.personas.update_one({"_id": pid, **bd.ACTIVA}, {"$set": {"situacion": nueva, "actualizado_en": ts}})
    bd.auditar(db, quien, "situacion", "persona", pid, {"decision": body.decision}, campos=["situacion"],
               estado=nueva["estado"])
    return {"ok": True, "situacion": nueva}


# ───────────────────────────── Autorizaciones de planilla ─────────────────────────────

class ConfirmarIn(BaseModel):
    evidencia: str = Field(..., min_length=5, max_length=500)


@r.post("/importaciones/{iid}/confirmar-autorizaciones")
def confirmar_autorizaciones(iid: int, body: ConfirmarIn, db: Database = Depends(obtener_db),
                             quien: Quien = Depends(requiere("importar"))):
    """Los «sí» declarados en una planilla («declarado en planilla») no habilitan la cola hasta que el administrador
    los confirma con la evidencia física. Las autorizaciones son de solo inserción: cada confirmación es un evento
    nuevo, y solo se confirma la que sigue vigente (no una que se revocó después)."""
    if db.importaciones.find_one({"_id": iid}, {"_id": 1}) is None:
        raise HTTPException(404, "No existe esa importación")
    hechas, pids = 0, []
    for ev in db.autorizaciones.find({"importacion_id": iid, "estado": "si", "medio": "declarado_planilla",
                                      "confirmada_por": None, "persona_id": {"$ne": None}}):
        pid = ev["persona_id"]
        if db.personas.find_one({"_id": pid, **bd.ACTIVA}, {"_id": 1}) is None:
            continue
        ultimo = max(db.autorizaciones.find({"persona_id": pid}),
                     key=lambda e: (str(e.get("ts") or ""), e["_id"]))
        if ultimo["_id"] != ev["_id"]:
            continue
        nuevo = bd.autorizacion_doc(
            db, pid, "si", "declarado_planilla", canales=ev.get("canales") or [],
            canales_implicitos=bool(ev.get("canales_implicitos")), sensibles=ev.get("sensibles") or [],
            mayor_declarado=bool(ev.get("mayor_declarado")), evidencia=body.evidencia.strip(),
            evidencia_sha256=ev.get("evidencia_sha256"), texto_version=ev.get("texto_version"),
            fecha_declarada=ev.get("fecha_declarada"), uid=quien.uid, usuario=quien.usuario, rol=quien.rol,
            capturado_por=ev.get("capturado_por"), confirmada_por=quien.uid, importacion_id=iid,
            nota=f"Confirma la autorización {ev['_id']}", clave_migracion=f"confirma:{ev['_id']}")
        try:
            db.autorizaciones.insert_one(nuevo)
        except DuplicateKeyError:
            continue
        hechas += 1
        pids.append(pid)
    bd.derivar(db, pids)
    bd.auditar(db, quien, "confirmar_autorizaciones", "importacion", iid, {"confirmadas": hechas})
    return {"confirmadas": hechas}


# ───────────────────────────── Lugares ─────────────────────────────

@r.get("/lugares")
def lugares(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    conteo = Counter(p.get("lugar_id") for p in db.personas.find({**bd.ACTIVA, "lugar_id": {"$ne": None}}, {"lugar_id": 1}))
    salida = [{"id": l["_id"], "nombre": l["nombre"], "tipo": l["tipo"], "zona": l["zona"], "lat": l.get("lat"), "lon": l.get("lon"),
               "alias": l.get("alias") or [], "padre": l.get("padre"), "fuente": l.get("fuente"), "precision": l.get("precision"),
               "tiene_poligono": bool(l.get("geom")), "n": conteo.get(l["_id"], 0)}
              for l in db.lugares.find({}, {"geom.type": 1, "nombre": 1, "tipo": 1, "zona": 1, "lat": 1, "lon": 1, "alias": 1, "padre": 1, "fuente": 1, "precision": 1})]
    return sorted(salida, key=lambda x: (-x["n"], x["nombre"]))


@r.get("/lugares/sin-reconocer")
def sin_reconocer(db: Database = Depends(obtener_db), _: Admin = Depends(requiere_admin)):
    """Lugares escritos en las direcciones que no casan con el nomenclátor (para crearlos o agregarlos como alias)."""
    c = Counter(p["lugar_texto"] for p in db.personas.find({**bd.ACTIVA, "lugar_id": None, "lugar_texto": {"$ne": None}},
                                                           {"lugar_texto": 1}))
    return [{"texto": t, "n": n} for t, n in c.most_common(80) if n >= 2]


class LugarIn(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=80)
    tipo: Literal["barrio", "sector", "vereda", "caserio", "centro_poblado", "corregimiento"] | None = None
    zona: Literal["urbana", "rural"] | None = None
    lat: float | None = Field(None, ge=6.3, le=7.5)
    lon: float | None = Field(None, ge=-74.6, le=-73.6)
    alias: list[str] | None = None
    padre: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _punto_completo(self):
        # Latitud y longitud van juntas: un lugar con una sola dejaría a su gente con un punto roto
        enviados = self.model_fields_set & {"lat", "lon"}
        if enviados and (enviados != {"lat", "lon"} or (self.lat is None) != (self.lon is None)):
            raise ValueError("Indique latitud y longitud juntas (o ninguna)")
        return self


def _recalcular(db: Database) -> None:
    georreferenciar(db)
    bd.recalcular_completitud(db)


@r.post("/lugares", status_code=201)
def crear_lugar(body: LugarIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not body.nombre or not body.tipo:
        raise HTTPException(422, "Nombre y tipo son obligatorios")
    zona = body.zona or ("urbana" if body.tipo in ("barrio", "sector") else "rural")
    lid = bd.siguiente_id(db, "lugares")
    try:
        db.lugares.insert_one({
            "_id": lid, "nombre": tx.limpiar(body.nombre), "tipo": body.tipo, "zona": zona, "lat": body.lat, "lon": body.lon,
            "alias": sorted({tx.limpiar(a) for a in body.alias or [] if a.strip()}),
            "padre": tx.limpiar(body.padre) or ("YONDO" if zona == "urbana" else None), "fuente": "manual",
            "precision": "manual" if body.lat is not None else None, "geom": None, "editado": True, "creado_en": bd.ahora()})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un lugar con ese nombre y tipo")
    bd.auditar(db, adm, "crear", "lugar", lid, body.model_dump(), adm.ip)
    bd.subir_catalogos_version(db)
    _recalcular(db)
    return {"id": lid}


@r.patch("/lugares/{lid}")
def editar_lugar(lid: int, body: LugarIn, db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    if not db.lugares.find_one({"_id": lid}, {"_id": 1}):
        raise HTTPException(404, "No existe")
    datos = body.model_dump(exclude_unset=True)
    if "nombre" in datos:
        datos["nombre"] = tx.limpiar(datos["nombre"])
    if "alias" in datos:
        datos["alias"] = sorted({tx.limpiar(a) for a in datos["alias"] or [] if a.strip()})
    if "lat" in datos:
        datos.update({"precision": "manual", "fuente": "manual"})
    if datos:
        db.lugares.update_one({"_id": lid}, {"$set": {**datos, "editado": True}})
        bd.auditar(db, adm, "editar", "lugar", lid, datos, adm.ip)
        bd.subir_catalogos_version(db)
        _recalcular(db)
    return {"ok": True}


@r.post("/georreferenciar")
def regeocodificar(db: Database = Depends(obtener_db), adm: Admin = Depends(requiere_admin)):
    res = georreferenciar(db)
    bd.recalcular_completitud(db)
    bd.auditar(db, adm, "georreferenciar", None, None, res, adm.ip)
    return res
