"""Usuarios del panel: alta, roles, claves, sesiones, desbloqueo y asignación, la cuenta propia (cambio de clave,
compromiso de confidencialidad e indicadores) e indicadores por usuario (5.1) y por zona (5.3).

* Gestionan usuarios el administrador (A) y el coordinador (K). K crea planilleros y consultores, edita su nombre y
  asignación, los desactiva, reactiva, desbloquea y les restablece la clave, y ve a todos con sus indicadores; no crea
  coordinadores, no toca la cuenta de otro coordinador y no cambia roles (403 `permiso`). Eso es solo de A.
* Los coordinadores no tienen asignación: como A, trabajan sobre toda la base.
* Los usuarios nunca se borran: se desactivan. Desactivar, cambiar el rol, restablecer la clave y «Cerrar sesiones»
  suben su `version`, y sus sesiones caen en la petición siguiente. Desactivar, reactivar, cambiar el rol o la
  asignación borra además sus conversaciones con el asistente: lo que el modelo le mostró era de su rol o su zona de
  antes.
* La clave temporal se muestra una sola vez (en la respuesta del alta o del restablecimiento), vence a las 72 h y no
  va a la auditoría ni a ningún GET.
* Los indicadores de varios usuarios se calculan con un `$group` por usuario, no con una consulta por usuario:
  planilleros sobre `auditoria` (lo suyo y lo que capturaron en planillas), consultores sobre `acercamientos` (sin los
  anulados; los anonimizados por una supresión se siguen contando) y fichas vistas sobre `lecturas`. El bloque
  `administracion` (importaciones, exportaciones, uniones, supresiones y usuarios creados) sale de `auditoria`.
* `tratables=1` (lo manda el asistente) en la lista de usuarios y en el avance: lo que cada uno hizo con las personas y
  las cifras de cada lugar sin contar a quienes no autorizaron el tratamiento de sus datos. Las demás herramientas del
  asistente no los cuentan, y la resta diría algo de ellos (que a alguien de una vereda lo llamaron hoy, o que tiene
  cédula). La interfaz no lo manda y cuenta a todos.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import acceso, geometria, modelo
from .. import db as bd
from ..acceso import Quien, requiere
from ..seguridad import (MAX_POR_IP, VENTANA_S, base_de, crear_sesion, ip_de, marcar_dispositivo, obtener_db,
                         reservar_intento, resolver_intento)

r = APIRouter(prefix="/api", tags=["usuarios"])
GESTIONAR = requiere("usuarios.gestionar")
CUENTA = requiere("cuenta")
AGRUPAR = {"dia": "%Y-%m-%d", "semana": "%G-S%V", "mes": "%Y-%m"}
# Trabajo de administración que cuenta en los indicadores (el de A y K): acción de la auditoría → indicador
ACCIONES_ADMINISTRACION = {"importar": "importaciones", "exportar": "exportaciones",
                           "exportar_asistentes": "exportaciones", "fusionar": "uniones", "suprimir": "supresiones",
                           "crear_usuario": "usuarios_creados"}


# ───────────────────────────── Periodo ─────────────────────────────

def _utc(d: date) -> str:
    """Inicio del día `d` en hora de Colombia, como texto ISO UTC (el formato de `ts` en la auditoría)."""
    return datetime.combine(d, time.min, tzinfo=modelo.ZONA).astimezone(timezone.utc).isoformat()


def periodo(desde: str | None, hasta: str | None, dias: int = 30,
            maximo_dias: int | None = 731) -> tuple[date, date, str, str]:
    """(desde, hasta, ts_desde, ts_hasta): fechas locales inclusivas (por defecto, los últimos `dias` días) y los
    límites en ISO UTC para comparar con `ts` (`ts_desde <= ts < ts_hasta`)."""
    h = modelo.fecha_valida(hasta) if hasta else modelo.hoy_local()
    d = modelo.fecha_valida(desde) if desde else (h - timedelta(days=dias - 1) if h else None)
    if d is None or h is None:
        raise HTTPException(422, "Use fechas con el formato AAAA-MM-DD")
    if d > h:
        raise HTTPException(422, "«Desde» no puede ser posterior a «hasta»")
    if maximo_dias and (h - d).days >= maximo_dias:
        raise HTTPException(422, f"El periodo no puede pasar de {maximo_dias} días")
    return d, h, _utc(d), _utc(h + timedelta(days=1))


# ───────────────────────────── Indicadores (5.1) ─────────────────────────────

def _cuenta(cond: dict) -> dict:
    return {"$sum": {"$cond": [cond, 1, 0]}}


def _lista(campo: str) -> dict:
    return {"$cond": [{"$isArray": campo}, campo, []]}


def _vacio_planillero() -> dict:
    return {"creadas": 0, "creadas_por_planilla": 0, "creadas_netas": 0, "actualizadas": 0, "con_datos_nuevos": 0,
            "correcciones": 0, "completados": {k: 0 for k in modelo.CAMPOS_AVANCE}, "telefonos_agregados": 0,
            "autorizaciones": {"si": 0, "no": 0}, "asistencias": 0, "ubicadas": 0, "fichas_vistas": 0,
            "personas_vistas": 0,
            "calidad": {"telefonos_luego_equivocados": 0, "cedulas_en_conflicto": 0, "duplicados_unidos": 0}}


def _vacio_consultor() -> dict:
    return {"acercamientos": 0, "personas": 0, "contactadas": 0, "por_canal": {k: 0 for k in modelo.CANALES},
            "por_resultado": {k: 0 for k in modelo.RESULTADOS}, "no_contactar": 0, "autorizaciones_obtenidas": 0,
            "cedulas_dictadas": 0, "fuera_de_horario": 0}


def _vacio_administracion() -> dict:
    return {k: 0 for k in dict.fromkeys(ACCIONES_ADMINISTRACION.values())}


def _base_auditoria(uids: list[int], ts_desde: str, ts_hasta: str, sin: list[int] = ()) -> list[dict]:
    """Entradas sobre personas del periodo, atribuidas a quien capturó la planilla o, si no hay, a quien actuó. `sin`:
    personas que no cuentan (`tratables`)."""
    return [
        {"$match": {"$or": [{"uid": {"$in": uids}}, {"capturado_por": {"$in": uids}}], "entidad": "persona",
                    "ts": {"$gte": ts_desde, "$lt": ts_hasta}, **({"entidad_id": {"$nin": sin}} if sin else {})}},
        {"$set": {"_q": {"$ifNull": ["$capturado_por", "$uid"]}, "_campos": _lista("$campos"),
                  "_compl": _lista("$completados")}},
        {"$match": {"_q": {"$in": uids}}},
    ]


def _efectivo() -> dict:
    return {"$ifNull": ["$efectivo", {"$in": ["$resultado", sorted(modelo.EFECTIVOS)]}]}


def _base_acercamientos(uids: list[int], ts_desde: str, ts_hasta: str, sin: list[int] = ()) -> dict:
    return {"$match": {"uid": {"$in": uids}, "ts": {"$gte": ts_desde, "$lt": ts_hasta}, "anulado": {"$ne": True},
                       **({"persona_id": {"$nin": sin}} if sin else {})}}


def _no_autorizaron(db: Database) -> list[int]:
    """Quienes no autorizaron el tratamiento de sus datos: lo que no cuentan las cifras con `tratables`."""
    return db.personas.distinct("_id", {"consentimiento": "no"})


def indicadores(db: Database, uids: list[int], d: date, h: date, ts_desde: str, ts_hasta: str,
                tratables: bool = False) -> dict[int, dict]:
    """Indicadores del periodo de cada usuario de `uids`: `{uid: {planillero: {...}, consultor: {...},
    administracion: {...}}}`. Con `tratables`, lo que hizo con las personas no cuenta a quienes no autorizaron (lo que
    administró, sí: no es de una persona)."""
    uids = list(dict.fromkeys(uids))
    out = {u: {"planillero": _vacio_planillero(), "consultor": _vacio_consultor(),
               "administracion": _vacio_administracion()} for u in uids}
    if not uids:
        return out
    sin = _no_autorizaron(db) if tratables else []
    edicion = list(modelo.ACCIONES_EDICION)
    es_crear = {"$eq": ["$accion", "crear"]}
    facetas = next(db.auditoria.aggregate(_base_auditoria(uids, ts_desde, ts_hasta, sin) + [{"$facet": {
        "personas": [
            {"$group": {"_id": {"q": "$_q", "p": "$entidad_id"},
                        "creadas": _cuenta(es_crear),
                        "por_planilla": _cuenta({"$and": [es_crear, {"$ne": [{"$ifNull": ["$capturado_por", None]}, None]}]}),
                        "edito": {"$max": {"$and": [{"$in": ["$accion", edicion]}, {"$gt": [{"$size": "$_campos"}, 0]}]}},
                        "nuevos": {"$max": {"$gt": [{"$size": "$_compl"}, 0]}},
                        "correcciones": {"$sum": {"$cond": [{"$eq": ["$accion", "editar"]},
                                                            {"$size": {"$setDifference": ["$_campos", "$_compl"]}}, 0]}},
                        "telefonos": _cuenta({"$eq": ["$accion", "telefono_agregar"]}),
                        "asistencias": _cuenta({"$eq": ["$accion", "asistencia"]}),
                        "ubico": {"$max": {"$eq": ["$accion", "ubicar"]}}}},
            {"$group": {"_id": "$_id.q", "creadas": {"$sum": "$creadas"}, "creadas_por_planilla": {"$sum": "$por_planilla"},
                        "creadas_pids": {"$push": {"$cond": [{"$gt": ["$creadas", 0]}, "$_id.p", None]}},
                        "actualizadas": _cuenta("$edito"), "con_datos_nuevos": _cuenta("$nuevos"),
                        "correcciones": {"$sum": "$correcciones"}, "telefonos_agregados": {"$sum": "$telefonos"},
                        "asistencias": {"$sum": "$asistencias"}, "ubicadas": _cuenta("$ubico")}},
        ],
        "completados": [{"$unwind": "$_compl"}, {"$group": {"_id": {"q": "$_q", "c": "$_compl"}, "n": {"$sum": 1}}}],
        "autorizaciones": [{"$match": {"accion": "autorizacion"}},
                           {"$group": {"_id": {"q": "$_q", "e": "$estado"}, "n": {"$sum": 1}}}],
    }}]), {})
    creadas: dict[int, list] = {}
    for x in facetas.get("personas", []):
        p = out[x["_id"]]["planillero"]
        for k in ("creadas", "creadas_por_planilla", "actualizadas", "con_datos_nuevos", "correcciones",
                  "telefonos_agregados", "asistencias", "ubicadas"):
            p[k] = x[k]
        creadas[x["_id"]] = [i for i in x["creadas_pids"] if i is not None]
    for x in facetas.get("completados", []):
        if isinstance(x["_id"].get("c"), str):
            c = out[x["_id"]["q"]]["planillero"]["completados"]
            c[x["_id"]["c"]] = c.get(x["_id"]["c"], 0) + x["n"]
    for x in facetas.get("autorizaciones", []):
        a = out[x["_id"]["q"]]["planillero"]["autorizaciones"]
        estado = x["_id"].get("e") or "sin_estado"
        a[estado] = a.get(estado, 0) + x["n"]
    # Las creadas que hoy están unidas a otra ficha eran duplicados: no cuentan en las netas
    todas = [i for v in creadas.values() for i in v]
    unidas = {x["_id"] for x in db.personas.find({"_id": {"$in": todas}, "fusionada_en": {"$ne": None}}, {"_id": 1})} if todas else set()
    for u, pids in creadas.items():
        p = out[u]["planillero"]
        p["calidad"]["duplicados_unidos"] = sum(1 for i in pids if i in unidas)
    for u in uids:
        p = out[u]["planillero"]
        p["creadas_netas"] = p["creadas"] - p["calidad"]["duplicados_unidos"]
    leidas = {"uid": {"$in": uids}, "dia": {"$gte": d.isoformat(), "$lte": h.isoformat()},
              **({"pid": {"$nin": sin}} if sin else {})}
    for x in db.lecturas.aggregate([{"$match": leidas},
                                    {"$group": {"_id": "$uid", "n": {"$sum": 1}, "fichas": _cuenta({"$eq": ["$ficha", True]})}}]):
        out[x["_id"]]["planillero"].update(personas_vistas=x["n"], fichas_vistas=x["fichas"])
    malos = ["equivocado", "inexistente"]
    for x in db.personas.aggregate([
            {"$match": {"telefonos": {"$elemMatch": {"agregado_por": {"$in": uids}, "estado": {"$in": malos}}},
                        **({"consentimiento": {"$ne": "no"}} if tratables else {})}},
            {"$unwind": "$telefonos"},
            {"$match": {"telefonos.agregado_por": {"$in": uids}, "telefonos.estado": {"$in": malos}}},
            {"$group": {"_id": "$telefonos.agregado_por", "n": {"$sum": 1}}}]):
        out[x["_id"]]["planillero"]["calidad"]["telefonos_luego_equivocados"] = x["n"]
    # Conflictos de cédula cuyo registro (planilla o dictado) es de ese usuario
    autor = {"$ifNull": ["$registro.capturado_por", {"$ifNull": ["$registro.uid", {"$ifNull": ["$creado_por.uid", "$creado_por"]}]}]}
    for x in db.conflictos_cedula.aggregate([
            {"$match": {"$or": [{"registro.capturado_por": {"$in": uids}}, {"registro.uid": {"$in": uids}},
                                {"creado_por.uid": {"$in": uids}}, {"creado_por": {"$in": uids}}],
                        "creado_en": {"$gte": ts_desde, "$lt": ts_hasta},
                        **({"persona_id": {"$nin": sin}} if sin else {})}},
            {"$group": {"_id": autor, "n": {"$sum": 1}}}]):
        if x["_id"] in out:
            out[x["_id"]]["planillero"]["calidad"]["cedulas_en_conflicto"] = x["n"]
    dictadas = {"$in": ["cedula", _lista("$datos_dictados")]}
    facetas = next(db.acercamientos.aggregate([_base_acercamientos(uids, ts_desde, ts_hasta, sin), {"$facet": {
        "personas": [
            {"$group": {"_id": {"u": "$uid", "p": "$persona_id"}, "n": {"$sum": 1}, "efectivo": {"$max": _efectivo()},
                        "no_contactar": _cuenta({"$eq": ["$resultado", "no_contactar"]}),
                        "autorizaciones": _cuenta({"$ne": [{"$ifNull": ["$autorizacion_id", None]}, None]}),
                        "dictadas": _cuenta(dictadas), "fuera": _cuenta({"$eq": ["$fuera_de_horario", True]})}},
            {"$group": {"_id": "$_id.u", "acercamientos": {"$sum": "$n"}, "personas": {"$sum": 1},
                        "contactadas": _cuenta("$efectivo"), "no_contactar": {"$sum": "$no_contactar"},
                        "autorizaciones_obtenidas": {"$sum": "$autorizaciones"}, "cedulas_dictadas": {"$sum": "$dictadas"},
                        "fuera_de_horario": {"$sum": "$fuera"}}},
        ],
        "canal": [{"$group": {"_id": {"u": "$uid", "k": "$canal"}, "n": {"$sum": 1}}}],
        "resultado": [{"$group": {"_id": {"u": "$uid", "k": "$resultado"}, "n": {"$sum": 1}}}],
    }}]), {})
    for x in facetas.get("personas", []):
        c = out[x["_id"]]["consultor"]
        for k in ("acercamientos", "personas", "contactadas", "no_contactar", "autorizaciones_obtenidas",
                  "cedulas_dictadas", "fuera_de_horario"):
            c[k] = x[k]
    for faceta, clave in (("canal", "por_canal"), ("resultado", "por_resultado")):
        for x in facetas.get(faceta, []):
            k = x["_id"].get("k")
            if isinstance(k, str):
                d_ = out[x["_id"]["u"]]["consultor"][clave]
                d_[k] = d_.get(k, 0) + x["n"]
    # Importó, exportó, unió, suprimió o creó usuarios (lo de A y K; los demás quedan en cero)
    for x in db.auditoria.aggregate([
            {"$match": {"uid": {"$in": uids}, "accion": {"$in": list(ACCIONES_ADMINISTRACION)},
                        "ts": {"$gte": ts_desde, "$lt": ts_hasta}}},
            {"$group": {"_id": {"u": "$uid", "a": "$accion"}, "n": {"$sum": 1}}}]):
        a = out[x["_id"]["u"]]["administracion"]
        clave = ACCIONES_ADMINISTRACION[x["_id"]["a"]]
        a[clave] += x["n"]
    return out


def serie(db: Database, uid: int, ts_desde: str, ts_hasta: str, agrupar: str = "dia") -> list[dict]:
    """Serie del periodo por día, semana o mes: fichas creadas, personas actualizadas y acercamientos. Cuenta personas
    distintas en cada periodo: no suma al total."""
    fecha = {"$dateToString": {"format": AGRUPAR[agrupar], "timezone": "-05:00", "onNull": None, "date": {
        "$cond": [{"$eq": [{"$type": "$ts"}, "date"]}, "$ts",
                  {"$dateFromString": {"dateString": {"$toString": "$ts"}, "onError": None, "onNull": None}}]}}}
    filas: dict[str, dict] = {}

    def fila(f: str) -> dict:
        return filas.setdefault(f, {"fecha": f, "creadas": 0, "actualizadas": 0, "acercamientos": 0})

    for x in db.auditoria.aggregate(_base_auditoria([uid], ts_desde, ts_hasta) + [
            {"$set": {"_f": fecha}},
            {"$group": {"_id": {"f": "$_f", "p": "$entidad_id"}, "creadas": _cuenta({"$eq": ["$accion", "crear"]}),
                        "edito": {"$max": {"$and": [{"$in": ["$accion", list(modelo.ACCIONES_EDICION)]},
                                                    {"$gt": [{"$size": "$_campos"}, 0]}]}}}},
            {"$group": {"_id": "$_id.f", "creadas": {"$sum": "$creadas"}, "actualizadas": _cuenta("$edito")}}]):
        if x["_id"]:
            fila(x["_id"]).update(creadas=x["creadas"], actualizadas=x["actualizadas"])
    for x in db.acercamientos.aggregate([_base_acercamientos([uid], ts_desde, ts_hasta), {"$set": {"_f": fecha}},
                                         {"$group": {"_id": "$_f", "n": {"$sum": 1}}}]):
        if x["_id"]:
            fila(x["_id"])["acercamientos"] = x["n"]
    return [filas[k] for k in sorted(filas)]


def indicadores_de(db: Database, u: dict, desde: str | None, hasta: str | None, agrupar: str) -> dict:
    """Los indicadores de 5.1 de un usuario (o del administrador, uid 0), con su serie."""
    if agrupar not in AGRUPAR:
        raise HTTPException(422, "agrupar debe ser dia, semana o mes")
    d, h, td, th = periodo(desde, hasta)
    ind = indicadores(db, [u["_id"]], d, h, td, th)[u["_id"]]
    return {"uid": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
            "desde": d.isoformat(), "hasta": h.isoformat(), "agrupar": agrupar, **ind,
            "serie": serie(db, u["_id"], td, th, agrupar)}


def _pendientes_autorizacion(db: Database) -> int:
    """Personas vigentes con número usable que esperan autorización: las que la cola no puede llamar."""
    return db.personas.count_documents({**modelo.filtro_vigente(), "consentimiento": {"$nin": ["si", "no"]},
                                        "telefono": {"$ne": None}})


# ───────────────────────────── Usuarios ─────────────────────────────

class Asignacion(BaseModel):
    lugares: list[int] = Field(default_factory=list, max_length=500)
    areas: list[int] = Field(default_factory=list, max_length=200)


class UsuarioNuevo(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=40)
    nombre: str = Field(..., min_length=3, max_length=80)
    rol: Literal["coordinador", "planillero", "consultor"]
    telefono: str | None = Field(None, max_length=30)
    asignacion: Asignacion | None = None


class UsuarioCambio(BaseModel):
    nombre: str | None = Field(None, min_length=3, max_length=80)
    rol: Literal["coordinador", "planillero", "consultor"] | None = None
    activo: bool | None = None
    telefono: str | None = Field(None, max_length=30)
    asignacion: Asignacion | None = None


def _exigir_sobre(adm: Quien, rol: str | None) -> None:
    """403 si `adm` no puede crear ni tocar la cuenta de un usuario con ese `rol`: los coordinadores (y cualquier rol
    que no sea de campo: falla cerrada) solo los gestiona A."""
    if rol not in acceso.ROLES_CAMPO and not adm.puede("usuarios.coordinadores"):
        raise HTTPException(403, {**acceso.SIN_PERMISO,
                                  "mensaje": "Solo el administrador gestiona a los coordinadores"})


def _sin_asignacion(rol: str | None, asignacion: dict) -> None:
    if rol in acceso.ROLES_ADMIN and (asignacion["lugares"] or asignacion["areas"]):
        raise HTTPException(422, "Un coordinador no tiene asignación: trabaja sobre toda la base")


def _reservado(cfg, usuario: str) -> bool:
    """Nombres reservados y el del administrador, sin distinguir mayúsculas."""
    return usuario in acceso.RESERVADOS or usuario == (cfg.usuario or "").strip().lower()


def _asignacion(db: Database, a: Asignacion | None) -> dict:
    """Lugares y áreas que existen, sin repetir."""
    a = a or Asignacion()
    lugares, areas = sorted(set(a.lugares)), sorted(set(a.areas))
    faltan = set(lugares) - {x["_id"] for x in db.lugares.find({"_id": {"$in": lugares}}, {"_id": 1})}
    if faltan:
        raise HTTPException(422, f"No existen estos barrios o veredas: {sorted(faltan)}")
    faltan = set(areas) - {x["_id"] for x in db.areas.find({"_id": {"$in": areas}}, {"_id": 1})}
    if faltan:
        raise HTTPException(422, f"No existen estas áreas: {sorted(faltan)}")
    return {"lugares": lugares, "areas": areas}


def _telefono(t: str | None) -> str | None:
    return " ".join((t or "").split()) or None


def _estado(db: Database, usuarios: list[dict]) -> dict:
    """Bloqueos (fallos recientes de su nombre), alertas de ingresos de las últimas 24 h y el día de hoy."""
    clave = acceso.clave_ingresos(db)
    por_h = {acceso.nombre_h(db, u.get("usuario"), clave): u["_id"] for u in usuarios}
    ahora = datetime.now(timezone.utc)
    bloqueados = {por_h[x["_id"]] for x in db.intentos.aggregate([
        {"$match": {"nombre_h": {"$in": list(por_h)}, "ok": False, "ts": {"$gt": ahora - timedelta(seconds=VENTANA_S)}}},
        {"$group": {"_id": "$nombre_h", "n": {"$sum": 1}}}, {"$match": {"n": {"$gte": MAX_POR_IP}}}])}
    hace_un_dia = (ahora - timedelta(hours=24)).replace(microsecond=0).isoformat()
    ingresos = {a["entidad_id"] for a in db.auditoria.find(
        {"accion": "alerta_ingresos", "entidad": "usuario", "entidad_id": {"$in": [u["_id"] for u in usuarios]},
         "ts": {"$gte": hace_un_dia}}, {"entidad_id": 1})}
    return {"bloqueados": bloqueados, "ingresos": ingresos, "hoy": modelo.hoy_local().isoformat(), "por_h": por_h}


def _fila(u: dict, est: dict, ind: dict | None = None) -> dict:
    """Lo que A y K ven de un usuario: nunca la clave ni su hash."""
    vencida = acceso.clave_vencida(u)
    alertas = []
    if u["_id"] in est["bloqueados"]:
        alertas.append("bloqueo")
    if (u.get("volumen") or {}).get("dia") == est["hoy"]:
        alertas.append("volumen")
    if u["_id"] in est["ingresos"]:
        alertas.append("ingresos")
    if vencida:
        alertas.append("clave_vencida")
    a = u.get("asignacion") or {}
    fila = {"id": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
            "activo": bool(u.get("activo")), "telefono": u.get("telefono"), "ultimo_ingreso": u.get("ultimo_ingreso"),
            "creado_en": u.get("creado_en"), "desactivado_en": u.get("desactivado_en"),
            "debe_cambiar_clave": bool(u.get("debe_cambiar_clave")),
            "clave_temporal_vence": u.get("clave_temporal_vence") if u.get("debe_cambiar_clave") else None,
            "clave_vencida": vencida, "bloqueado": u["_id"] in est["bloqueados"], "alertas": alertas,
            "volumen_hoy": (u.get("volumen") or {}).get("rechazos", 0) if "volumen" in alertas else 0,
            "compromiso_version": u.get("compromiso_version"),
            "asignacion": {"lugares": list(a.get("lugares") or []), "areas": list(a.get("areas") or [])}}
    if ind is not None:
        fila["indicadores"] = ind
    return fila


def _usuario(db: Database, uid: int) -> dict:
    u = db.usuarios.find_one({"_id": uid}, {"clave": 0})
    if u is None:
        raise HTTPException(404, "No existe ese usuario")
    return u


def _detalle(db: Database, u: dict) -> dict:
    est = _estado(db, [u])
    nh = next(iter(est["por_h"]))
    sesiones = [{"creada": s.get("creada"), "ultima_actividad": s.get("ultima_actividad"), "expira": s.get("expira"),
                 "ip": s.get("ip"), "agente": s.get("agente")}
                for s in db.sesiones.find({"uid": u["_id"]}).sort("creada", -1)]
    intentos = [{"ts": x.get("ts"), "ip": x.get("ip")}
                for x in db.intentos.find({"nombre_h": nh, "ok": False}).sort("ts", -1).limit(20)]
    return {**_fila(u, est), "sesiones": sesiones, "intentos_recientes": intentos}


@r.get("/usuarios")
def listar(desde: str | None = None, hasta: str | None = None, tratables: int = 0, db: Database = Depends(obtener_db),
           _: Quien = Depends(GESTIONAR)):
    """Los usuarios con sus indicadores del periodo; con `tratables` (el asistente), sin contar a quienes no
    autorizaron."""
    d, h, td, th = periodo(desde, hasta)
    usuarios = list(db.usuarios.find({}, {"clave": 0}).sort([("activo", -1), ("usuario", 1)]))
    ind = indicadores(db, [u["_id"] for u in usuarios], d, h, td, th, bool(tratables))
    est = _estado(db, usuarios)
    return [_fila(u, est, ind.get(u["_id"])) for u in usuarios]


@r.post("/usuarios", status_code=201)
def crear(body: UsuarioNuevo, request: Request, db: Database = Depends(obtener_db), adm: Quien = Depends(GESTIONAR)):
    _exigir_sobre(adm, body.rol)
    usuario = body.usuario.strip().lower()
    if not acceso.USUARIO_VALIDO.fullmatch(usuario):
        raise HTTPException(422, "El usuario lleva de 3 a 40 letras sin tildes, números, punto, guion o guion bajo")
    if _reservado(request.app.state.cfg, usuario):
        raise HTTPException(409, "Ese nombre de usuario está reservado; elija otro")
    if db.usuarios.find_one({"usuario": usuario}, {"_id": 1}):
        raise HTTPException(409, "Ya existe un usuario con ese nombre")
    asignacion = _asignacion(db, body.asignacion)
    _sin_asignacion(body.rol, asignacion)
    temporal, vence = acceso.clave_temporal(), acceso.vence_temporal()
    clave = acceso.hashear_clave(temporal)
    uid, ahora = bd.siguiente_id(db, "usuarios"), bd.ahora()
    try:
        db.usuarios.insert_one({
            "_id": uid, "usuario": usuario, "nombre": " ".join(body.nombre.split()), "rol": body.rol, "activo": True,
            "clave": clave, "version": 1, "debe_cambiar_clave": True, "clave_temporal_vence": vence,
            "compromiso_version": None, "compromiso_en": None, "telefono": _telefono(body.telefono),
            "asignacion": asignacion, "creado_por": adm.uid, "creado_en": ahora, "actualizado_en": ahora,
            "ultimo_ingreso": None, "desactivado_en": None})
    except DuplicateKeyError:
        raise HTTPException(409, "Ya existe un usuario con ese nombre")
    bd.auditar(db, adm, "crear_usuario", "usuario", uid, {"usuario": usuario, "rol": body.rol, "asignacion": asignacion})
    return {"id": uid, "usuario": usuario, "clave_temporal": temporal, "vence": vence}


@r.get("/usuarios/indicadores")
def indicadores_todos(desde: str | None = None, hasta: str | None = None, db: Database = Depends(obtener_db),
                      _: Quien = Depends(GESTIONAR)):
    d, h, td, th = periodo(desde, hasta)
    usuarios = list(db.usuarios.find({}, {"usuario": 1, "nombre": 1, "rol": 1, "activo": 1}).sort("usuario", 1))
    ind = indicadores(db, [u["_id"] for u in usuarios], d, h, td, th)
    filas = [{"uid": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
              "activo": bool(u.get("activo")), **ind[u["_id"]]} for u in usuarios]
    suma = lambda f: sum(f(x) for x in filas)  # noqa: E731
    totales = {
        "coordinadores_activos": sum(1 for u in usuarios if u.get("activo") and u.get("rol") == "coordinador"),
        "planilleros_activos": sum(1 for u in usuarios if u.get("activo") and u.get("rol") == "planillero"),
        "consultores_activos": sum(1 for u in usuarios if u.get("activo") and u.get("rol") == "consultor"),
        "creadas": suma(lambda x: x["planillero"]["creadas"]),
        "creadas_netas": suma(lambda x: x["planillero"]["creadas_netas"]),
        "actualizadas": suma(lambda x: x["planillero"]["actualizadas"]),
        "cedulas": suma(lambda x: x["planillero"]["completados"].get("cedula", 0)),
        "puestos": suma(lambda x: x["planillero"]["completados"].get("puesto", 0)),
        "mesas": suma(lambda x: x["planillero"]["completados"].get("mesa", 0)),
        "acercamientos": suma(lambda x: x["consultor"]["acercamientos"]),
        "contactadas": suma(lambda x: x["consultor"]["contactadas"]),
        "pendientes_autorizacion": _pendientes_autorizacion(db),
    }
    return {"desde": d.isoformat(), "hasta": h.isoformat(), "totales": totales, "usuarios": filas}


@r.get("/usuarios/avance")
def avance(por: Literal["lugar", "area"] = "lugar", tratables: int = 0, db: Database = Depends(obtener_db),
           _: Quien = Depends(GESTIONAR)):
    """Avance por cada barrio, vereda o área asignada (5.3): responsables, personas vigentes y porcentajes. Con
    `tratables` (el asistente), sin quienes no autorizaron."""
    clave = "lugares" if por == "lugar" else "areas"
    responsables: dict[int, list] = {}
    for u in db.usuarios.find({"activo": True}, {"usuario": 1, "nombre": 1, "rol": 1, "asignacion": 1}).sort("usuario", 1):
        for i in (u.get("asignacion") or {}).get(clave) or []:
            responsables.setdefault(i, []).append({"id": u["_id"], "usuario": u.get("usuario"), "nombre": u.get("nombre"),
                                                   "rol": u.get("rol")})
    medidas = {
        "n": {"$sum": 1},
        "cedula": _cuenta({"$ne": [{"$ifNull": ["$cedula", None]}, None]}),
        "puesto_mesa": _cuenta({"$and": [{"$not": [{"$in": [{"$ifNull": ["$puesto_votacion", None]}, [None, ""]]}]},
                                         {"$not": [{"$in": [{"$ifNull": ["$mesa", None]}, [None, ""]]}]}]}),
        "telefono": _cuenta({"$ne": [{"$ifNull": ["$telefono", None]}, None]}),
        "contactadas": _cuenta({"$eq": [{"$ifNull": ["$abordaje.estado", None]}, "contactado"]}),
    }
    ids = sorted(responsables)
    vigente = {**modelo.filtro_vigente(), **({"consentimiento": {"$ne": "no"}} if tratables else {})}
    datos, nombres = {}, {}
    if por == "lugar":
        nombres = {x["_id"]: x.get("nombre") for x in db.lugares.find({"_id": {"$in": ids}}, {"nombre": 1})}
        datos = {x["_id"]: x for x in db.personas.aggregate([{"$match": {**vigente, "lugar_id": {"$in": ids}}},
                                                             {"$group": {"_id": "$lugar_id", **medidas}}])}
    else:
        for a in db.areas.find({"_id": {"$in": ids}}, {"nombre": 1, "poligono": 1}):
            nombres[a["_id"]] = a.get("nombre")
            pol = a.get("poligono")
            geo = pol if isinstance(pol, dict) and pol.get("type") else (geometria.a_geojson(pol) if isinstance(pol, list) else None)
            if geo is None:
                continue
            x = next(db.personas.aggregate([{"$match": {**vigente, "punto": {"$geoWithin": {"$geometry": geo}}}},
                                            {"$group": {"_id": None, **medidas}}]), None)
            if x:
                datos[a["_id"]] = x

    def pct(x: dict, k: str) -> int:
        return round(100 * x.get(k, 0) / x["n"]) if x.get("n") else 0

    filas = []
    for i in ids:
        x = datos.get(i) or {"n": 0}
        filas.append({"id": i, "nombre": nombres.get(i), "responsables": responsables[i], "personas": x["n"],
                      "pct_cedula": pct(x, "cedula"), "pct_puesto_mesa": pct(x, "puesto_mesa"),
                      "pct_telefono": pct(x, "telefono"), "pct_contactadas": pct(x, "contactadas")})
    filas.sort(key=lambda f: (-f["personas"], f["nombre"] or ""))
    return {"por": por, "filas": filas}


@r.get("/usuarios/{uid}")
def ver(uid: int, db: Database = Depends(obtener_db), _: Quien = Depends(GESTIONAR)):
    return _detalle(db, _usuario(db, uid))


@r.patch("/usuarios/{uid}")
def editar(uid: int, body: UsuarioCambio, request: Request, db: Database = Depends(obtener_db),
           adm: Quien = Depends(GESTIONAR)):
    datos = body.model_dump(exclude_unset=True)
    if "rol" in datos and not adm.puede("usuarios.roles"):  # el rol se fija al crear; cambiarlo es solo de A
        raise HTTPException(403, {**acceso.SIN_PERMISO, "mensaje": "Solo el administrador cambia el rol de un usuario"})
    for k in ("nombre", "rol", "activo"):
        if k in datos and datos[k] is None:
            raise HTTPException(422, f"{k}: no puede quedar vacío")
    u = _usuario(db, uid)
    _exigir_sobre(adm, u.get("rol"))
    if "rol" in datos:
        _exigir_sobre(adm, datos["rol"])
    rol = datos.get("rol") or u.get("rol")
    cambios: dict = {}
    if "nombre" in datos and " ".join(datos["nombre"].split()) != u.get("nombre"):
        cambios["nombre"] = " ".join(datos["nombre"].split())
    if "rol" in datos and datos["rol"] != u.get("rol"):
        cambios["rol"] = datos["rol"]
    if "activo" in datos and datos["activo"] != bool(u.get("activo")):
        if datos["activo"] and _reservado(request.app.state.cfg, u.get("usuario") or ""):
            raise HTTPException(409, "Este usuario tiene un nombre reservado o el del administrador: no se puede activar")
        cambios["activo"] = datos["activo"]
    if "telefono" in datos and _telefono(datos["telefono"]) != u.get("telefono"):
        cambios["telefono"] = _telefono(datos["telefono"])
    antes = {"lugares": list((u.get("asignacion") or {}).get("lugares") or []),
             "areas": list((u.get("asignacion") or {}).get("areas") or [])}
    if "asignacion" in datos:
        a = _asignacion(db, body.asignacion)
        _sin_asignacion(rol, a)
        if a != antes:
            cambios["asignacion"] = a
    elif rol in acceso.ROLES_ADMIN and (antes["lugares"] or antes["areas"]):
        cambios["asignacion"] = {"lugares": [], "areas": []}  # al pasar a coordinador deja la asignación
    if not cambios:
        return _detalle(db, u)
    cierra = "rol" in cambios or "activo" in cambios
    ahora = bd.ahora()
    extra = {"desactivado_en": None if cambios["activo"] else ahora} if "activo" in cambios else {}
    actualizacion = {"$set": {**cambios, **extra, "actualizado_en": ahora}}
    if cierra:
        actualizacion["$inc"] = {"version": 1}
    db.usuarios.update_one({"_id": uid}, actualizacion)
    if cierra:
        db.sesiones.delete_many({"uid": uid})
    if cierra or "asignacion" in cambios:
        # Lo que el asistente le mostró era de su rol o su zona de antes, y se le reenvía al modelo en cada ronda:
        # sus conversaciones se borran (como al suprimir a una persona)
        bd.borrar_conversaciones(db, {"uid": uid})
    bd.auditar(db, adm, "editar_usuario", "usuario", uid,
               {k: {"antes": u.get(k), "despues": v} for k, v in cambios.items()})
    return _detalle(db, _usuario(db, uid))


@r.post("/usuarios/{uid}/clave")
def restablecer_clave(uid: int, db: Database = Depends(obtener_db), adm: Quien = Depends(GESTIONAR)):
    _exigir_sobre(adm, _usuario(db, uid).get("rol"))
    temporal, vence = acceso.clave_temporal(), acceso.vence_temporal()
    db.usuarios.update_one({"_id": uid}, {"$set": {"clave": acceso.hashear_clave(temporal), "debe_cambiar_clave": True,
                                                   "clave_temporal_vence": vence, "actualizado_en": bd.ahora()},
                                          "$inc": {"version": 1}})
    db.sesiones.delete_many({"uid": uid})
    bd.auditar(db, adm, "restablecer_clave", "usuario", uid, {"vence": vence})
    return {"clave_temporal": temporal, "vence": vence}


@r.delete("/usuarios/{uid}/sesiones")
def cerrar_sesiones(uid: int, db: Database = Depends(obtener_db), adm: Quien = Depends(GESTIONAR)):
    _exigir_sobre(adm, _usuario(db, uid).get("rol"))
    n = acceso.cerrar_sesiones(db, uid)
    bd.auditar(db, adm, "cerrar_sesiones", "usuario", uid, {"cerradas": n})
    return {"cerradas": n}


@r.delete("/usuarios/{uid}/bloqueo")
def desbloquear(uid: int, db: Database = Depends(obtener_db), adm: Quien = Depends(GESTIONAR)):
    u = _usuario(db, uid)
    _exigir_sobre(adm, u.get("rol"))
    n = db.intentos.delete_many({"nombre_h": acceso.nombre_h(db, u.get("usuario")), "ok": False}).deleted_count
    bd.auditar(db, adm, "desbloquear", "usuario", uid, {"fallos": n})
    return {"ok": True}


@r.get("/usuarios/{uid}/indicadores")
def indicadores_usuario(uid: int, desde: str | None = None, hasta: str | None = None, agrupar: str = "dia",
                        db: Database = Depends(obtener_db), _: Quien = Depends(GESTIONAR)):
    return indicadores_de(db, _usuario(db, uid), desde, hasta, agrupar)


# ───────────────────────────── Mi cuenta ─────────────────────────────

class ClaveIn(BaseModel):
    actual: str = Field(..., max_length=256)
    nueva: str = Field(..., max_length=256)


class CompromisoIn(BaseModel):
    version: str = Field(..., max_length=40)


@r.post("/yo/clave")
def cambiar_clave(body: ClaveIn, request: Request, response: Response, db: Database = Depends(obtener_db),
                  quien: Quien = Depends(CUENTA)):
    if quien.es_admin:
        raise HTTPException(409, "La clave del administrador se cambia en Railway (variable password)")
    cfg, ip = request.app.state.cfg, ip_de(request)
    u = db.usuarios.find_one({"_id": quien.uid, "activo": True})
    if u is None:
        raise HTTPException(401, "Inicie sesión")
    nh = acceso.nombre_h(db, u["usuario"])
    # Los intentos con la clave actual tienen el mismo límite que el ingreso; cuentan solo los de esta sesión
    sesion = (request.scope.get("state") or {}).get("sesion") or {}
    marca_h = hashlib.sha256(f"sesion|{sesion.get('_id')}".encode()).hexdigest()
    iid, espera = reservar_intento(db, ip, conocido=True, marca_h=marca_h, nombre_h=nh)
    if iid is None:
        raise HTTPException(429, f"Demasiados intentos. Espere {espera} segundos.", headers={"Retry-After": str(espera)})
    try:
        ok = acceso.verificar_clave(u.get("clave"), body.actual)
    except HTTPException:
        db.intentos.delete_one({"_id": iid})
        raise
    resolver_intento(db, iid, ip, ok, nh)
    if not ok:
        raise HTTPException(422, "La clave actual no es correcta")
    if body.nueva == body.actual:
        raise HTTPException(422, "La clave nueva debe ser distinta de la actual")
    acceso.validar_clave_nueva(u["usuario"], body.nueva)
    nuevo = db.usuarios.find_one_and_update(
        {"_id": u["_id"], "activo": True},
        {"$set": {"clave": acceso.hashear_clave(body.nueva), "debe_cambiar_clave": False, "clave_temporal_vence": None,
                  "actualizado_en": bd.ahora()}, "$inc": {"version": 1}},
        projection={"version": 1, "rol": 1, "usuario": 1}, return_document=ReturnDocument.AFTER)
    if nuevo is None:
        raise HTTPException(401, "Inicie sesión")
    # La versión nueva cierra todas sus sesiones; esta sigue con una sesión nueva
    db.sesiones.delete_many({"uid": u["_id"]})
    aj = modelo.leer_ajustes(db)
    csrf = crear_sesion(db, cfg, response, nuevo["usuario"], request, uid=u["_id"], rol=nuevo["rol"],
                        version=nuevo["version"], horas=aj["sesion"].get("horas_max"))
    marcar_dispositivo(cfg, response, base_de(request), u["_id"], nuevo["version"])
    bd.auditar(db, quien, "cambiar_clave", "usuario", u["_id"])
    return {"csrf": csrf}


@r.post("/yo/compromiso")
def aceptar_compromiso(body: CompromisoIn, db: Database = Depends(obtener_db), quien: Quien = Depends(CUENTA)):
    if quien.es_admin:
        return {"ok": True}
    vigente = modelo.leer_ajustes(db)["compromiso_version"]
    if body.version != vigente:
        raise HTTPException(409, {"mensaje": "El compromiso cambió. Recargue la página y léalo de nuevo.",
                                  "codigo": "compromiso"})
    db.usuarios.update_one({"_id": quien.uid}, {"$set": {"compromiso_version": vigente, "compromiso_en": bd.ahora()}})
    bd.auditar(db, quien, "aceptar_compromiso", "usuario", quien.uid, {"version": vigente})
    return {"ok": True}


@r.get("/yo/indicadores")
def mis_indicadores(desde: str | None = None, hasta: str | None = None, agrupar: str = "dia",
                    db: Database = Depends(obtener_db), quien: Quien = Depends(CUENTA)):
    u = {"_id": 0, "usuario": quien.usuario, "nombre": quien.nombre, "rol": "admin"} if quien.es_admin else \
        _usuario(db, quien.uid)
    return indicadores_de(db, u, desde, hasta, agrupar)
