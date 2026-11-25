"""La pantalla en off (app/pantalla.py) y la clave con que un agente la maneja por MCP (app/api/mcp.py).

* `GET /api/pantalla?v=N`: la vista Presentación en modo en off pregunta cada poco. Con la versión que ya tiene, 204 sin
  cuerpo; si cambió, el estado entero. Cada pregunta deja la pantalla como abierta (`visto`) y la versión vigente como
  entregada (`pantalla.entregar`): hasta entonces, una orden siguiente no pisa las acciones que esa versión trae.
* El recorrido narrado (`app/recorrido.py`): `POST /api/pantalla/progreso` (el avance que manda la página que lo
  reproduce: la pestaña, el proyector o la pantalla en off; no marca la pantalla como abierta; uno final lo cierra y,
  si el recorrido ya no es el vigente o está cerrado, 409: la página que todavía lo reproduce lo detiene),
  `POST /api/pantalla/recorrido/control` (los botones de la tarjeta del chat cuando suena en otra pantalla, y «Volver a
  reproducir» en cualquier destino: vuelve con el id del nuevo) y `GET /api/pantalla/recorrido` (la tarjeta lo sigue;
  solo lectura, tampoco marca `visto`).
* La presentación automática (`app/automatica.py`): `POST /api/pantalla/auto` la enciende (desde un capítulo, si se
  dice) o la apaga (el botón «Automática» de la pantalla en off y la franja del chat), y
  `POST /api/pantalla/auto/siguiente` es lo que pide la pantalla en off cuando no narra nada: si está encendida y no
  suena ningún plan, el servidor arma el del capítulo que sigue (200 con su id; si no hay nada que hacer, 204).
* `GET`, `POST` y `DELETE /api/pantalla/clave`: las claves MCP de la persona. Hay dos, cada una de un tipo, y crear
  otra reemplaza solo la de su tipo:
  - la de la presentación (`tipo: "presentacion"`, la de siempre; también las guardadas sin `tipo`): maneja la
    pantalla en off y nada más; vale en `Authorization: Bearer` o en `?clave=` y no vence;
  - la de datos (`tipo: "datos"`, `alcances` ⊂ {lectura, analitica, escritura}, nunca la presentación): un agente
    externo lee personas (solo A: es sacar datos del panel, como exportar), analítica agregada (A y K) o propone
    cambios que la persona aprueba en Mi cuenta (A y K). Va solo en `Authorization: Bearer` (en una dirección queda en
    los registros de proxies), vence a los `DIAS_CLAVE_DATOS` días y nunca proyecta. Revocarla o reemplazarla anula sus
    propuestas pendientes (`anular_propuestas`).
  Se muestra una sola vez, al crearla: en la base queda su SHA-256 y la huella de la sesión de ese momento, así
  cambiar la clave del panel (o la credencial del administrador) la anula, como a las sesiones. Los alcances se
  comprueban al crearla y otra vez en cada llamada (`alcances_de_datos`: el rol, los ajustes `agente_mcp` y
  `agente.escritura`)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pymongo.database import Database

from .. import db as bd
from .. import pantalla
from .. import recorrido as rec
from ..acceso import Quien, requiere
from ..agente import guion as guion_presentacion
from ..seguridad import SIN_PERMISO, base_de, huella, huella_usuario, obtener_db

r = APIRouter(prefix="/api", tags=["pantalla"])

PREFIJO_CLAVE = "ypm_"   # se reconoce a simple vista (y en un escáner de secretos) sin decir nada de quién es
PREFIJO_CLAVE_DATOS = "ypd_"  # la de datos se distingue de la de la presentación a simple vista
ALCANCES_DATOS = ("lectura", "analitica", "escritura")
DIAS_CLAVE_DATOS = 30
# Una propuesta decidida (o anulada) se guarda sin su tarjeta este tiempo: el agente consulta cómo terminó
DIAS_PROPUESTA_DECIDIDA = 7


def huella_clave(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def huella_de_sesion(db: Database, cfg, uid: int) -> str | None:
    """La huella con que valen las sesiones de `uid` ahora (la del administrador de .env o la de ese usuario), o None si
    el usuario ya no existe o está inactivo."""
    if uid == 0:
        return huella(cfg)
    u = db.usuarios.find_one({"_id": uid, "activo": True}, {"version": 1})
    return huella_usuario(cfg, u) if u else None


def direccion_mcp(request: Request) -> str:
    """La dirección del servidor MCP tal como la ve quien está en el panel (en el servicio único, bajo /panel)."""
    return f"{request.url.scheme}://{request.url.netloc}{base_de(request)}/api/mcp"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@r.get("/pantalla")
def estado_pantalla(v: int | None = Query(None, ge=-1, le=2 ** 31), latido: bool = Query(False),
                    db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("presentacion.ver"))):
    # Un latido (la pantalla en off mientras carga o en una espera larga) solo dice que sigue abierta: no se le entrega
    # nada, porque no aplica la respuesta, y marcar su versión como entregada perdería las acciones que trae
    if latido is True:   # (llamada directa, sin FastAPI, el valor por omisión es el objeto Query)
        pantalla.marcar_vista(db, quien.uid)
        return Response(status_code=204)
    doc = pantalla.entregar(db, quien.uid, v)
    if doc is None:
        return Response(status_code=204)
    g = guion_presentacion.cargar()
    if g is None:
        return Response(status_code=404)
    return pantalla.para_pantalla(pantalla.estado(doc, g), doc, g)


# ───────────────────────────── El recorrido narrado ─────────────────────────────

class ProgresoEntrada(BaseModel):
    """El avance del reproductor (admin/web/js/reproductor.js): la forma exacta, con listas cerradas."""
    model_config = ConfigDict(extra="forbid")
    rid: str = Field(..., pattern=r"^[0-9a-f]{12}$")
    n: StrictInt = Field(..., ge=1, le=rec.MAX_ESCENAS)
    de: StrictInt = Field(..., ge=1, le=rec.MAX_ESCENAS)
    fase: Literal[rec.FASES]
    frase: StrictInt = Field(0, ge=0, le=rec.MAX_FRASES - 1)
    voz: Literal[rec.VOCES]
    motivo: Literal[rec.MOTIVOS] | None = None
    aviso: Literal[rec.AVISOS] | None = None
    t_ms: StrictInt = Field(0, ge=0, le=600_000)


class ControlEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rid: str = Field(..., pattern=r"^[0-9a-f]{12}$")
    accion: Literal[rec.CONTROLES]


class AutoEntrada(BaseModel):
    """Encender o apagar la presentación automática; al encenderla, el capítulo (su id) donde empieza."""
    model_config = ConfigDict(extra="forbid")
    accion: Literal["iniciar", "detener"]
    capitulo: str | None = Field(None, pattern=r"^[a-z_]{2,40}$")


def _guion():
    g = guion_presentacion.cargar()
    if g is None:
        raise HTTPException(404, "La presentación no está en este servidor")
    return g


def _guion_o_nada():
    """El guion, o None si no está o no se puede leer (el avance de un recorrido se guarda igual)."""
    try:
        return guion_presentacion.cargar()
    except ValueError:
        return None


@r.post("/pantalla/progreso", status_code=204)
def progreso(p: ProgresoEntrada, db: Database = Depends(obtener_db),
             quien: Quien = Depends(requiere("presentacion.ver"))):
    if p.n > p.de:
        raise HTTPException(422, "La escena pasa del total")
    # (con el guion: si el plan es el de la presentación automática, su posición queda en un paso que existe)
    if not pantalla.guardar_progreso(db, quien.uid, p.model_dump(exclude_none=True), _guion_o_nada()):
        raise HTTPException(409, "Ese recorrido ya no es el vigente")
    return Response(status_code=204)


@r.post("/pantalla/recorrido/control")
def control_recorrido(c: ControlEntrada, db: Database = Depends(obtener_db),
                      quien: Quien = Depends(requiere("presentacion.ver"))):
    g = _guion()
    try:
        res = pantalla.controlar(db, quien.uid, g, c.accion, "panel", rid=c.rid)
    except ValueError:
        raise HTTPException(409, "No hay un recorrido sonando con ese id") from None
    # El id es el del recorrido que quedó (con «reproducir», el nuevo: la tarjeta sigue ese), aunque el resumen ya no lo
    # nombre (uno detenido antes de su primer avance)
    r, x = res["recorrido"] or {}, pantalla.resumen_recorrido(res["doc"], g) or {}
    return {"id": r.get("id"), "titulo": r.get("titulo"), "escena": x.get("escena"), "de": len(r.get("escenas") or []),
            "fase": x.get("fase"), "cerrado": r.get("cerrado")}


@r.get("/pantalla/recorrido")
def ver_recorrido(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("presentacion.ver"))):
    """Dónde va el recorrido (para la tarjeta del chat cuando suena en otra pantalla). Solo lectura: no marca `visto`."""
    g = _guion()
    doc = pantalla.leer(db, quien.uid)
    x = pantalla.resumen_recorrido(doc, g)
    v = pantalla.recorrido_de(doc, g)
    pr = pantalla.progreso_de(doc, v) or {}
    return {"recorrido": x and {k: x[k] for k in ("id", "titulo", "destino", "cerrado", "escena", "de", "fase",
                                                    "motivo", "voz", "hace_s")},
            "frase": pr.get("frase"), "avisos": (x or {}).get("avisos", []),
            # la presentación automática ({activa, capitulo, paso} o null), como en `GET /api/pantalla`
            "auto": pantalla.auto_para_pantalla(doc, g),
            # la pantalla en off sigue abierta (preguntó hace poco): en pausa no hay avances, esto dice si alguien la oye
            "conectada": pantalla.conectada(doc),
            # el último recorrido guardado, aunque el resumen ya no lo nombre (terminó hace rato, quedó abandonado): la
            # tarjeta lo mira antes de reanudar uno que se cortó
            "vigente": v and {"id": v["id"], "cerrado": v["cerrado"]}}


# ───────────────────────────── La presentación automática ─────────────────────────────

@r.post("/pantalla/auto")
def presentacion_automatica(a: AutoEntrada, db: Database = Depends(obtener_db),
                            quien: Quien = Depends(requiere("presentacion.ver"))):
    """La enciende (desde el primer paso del capítulo que se diga; sin capítulo, desde la portada) o la apaga. Responde
    {auto: {activa, capitulo, nombre, paso, de}}."""
    g = _guion()
    if a.accion == "iniciar":
        ci = g.por_id(a.capitulo) if a.capitulo is not None else 0
        if ci is None:
            raise HTTPException(422, "Ese capítulo no está en la presentación")
        doc = pantalla.iniciar_auto(db, quien.uid, g, "panel", ci)
    else:
        doc = pantalla.detener_auto(db, quien.uid, g, "panel")
    return {"auto": pantalla.auto_para_persona(doc, g)}


@r.post("/pantalla/auto/siguiente")
def siguiente_automatico(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("presentacion.ver"))):
    """Lo que pide la pantalla en off cuando no narra nada. 200 con el id del plan que armó (le llega en su próxima
    pregunta por el estado, con `auto: true`), o 204 si no había nada que hacer: está apagada o suena otro plan."""
    plan = pantalla.siguiente_auto(db, quien.uid, _guion())
    return {"id": plan["id"]} if plan else Response(status_code=204)


def tipo_de(doc: dict | None) -> str:
    """El tipo de una clave guardada: «datos» solo si lo dice; sin `tipo` (las de antes) es la de la presentación."""
    return "datos" if (doc or {}).get("tipo") == "datos" else "presentacion"


def vencida(doc: dict, ahora: datetime | None = None) -> bool:
    """¿Ya venció esta clave? Solo la de datos tiene `expira` (el índice TTL la borra, pero hasta un minuto después)."""
    expira = doc.get("expira")
    if expira is None:
        return tipo_de(doc) == "datos"  # una de datos sin fecha no vale: falla cerrada
    if not isinstance(expira, datetime):
        return True
    expira = expira if expira.tzinfo else expira.replace(tzinfo=timezone.utc)
    return expira <= (ahora or _ahora())


def alcances_de_datos(quien: Quien, ajustes: dict | None) -> dict[str, str | None]:
    """Por cada alcance de una clave de datos, None si `quien` puede tenerlo ahora o, si no, por qué (para mostrarlo).
    `ajustes`: los del panel (`politica.leer`). Se mira al crear la clave y en cada llamada por MCP:
    * todos: rol en `agente_mcp.roles` (solo A y K pueden estar) y `agente.usar`;
    * lectura (personas una por una): solo quien puede `exportar` (A): entregarlas a un cliente externo es sacarlas del
      panel, y el compromiso de confidencialidad se lo prohíbe al equipo;
    * analitica (cifras agregadas, con celdas pequeñas ocultas): `analitica.ver` (A y K);
    * escritura (propuestas que la persona aprueba en el panel): `agente.escritura` y `agente_mcp.escritura`."""
    from ..agente import politica  # aquí: politica importa el proveedor del modelo
    mcp, agente = politica.ajustes_mcp(ajustes), politica.ajustes_agente(ajustes)
    base = None
    if not quien.administra or quien.rol not in mcp["roles"]:
        base = ("Su rol no tiene datos por MCP: el administrador lo habilita en Ajustes (agentes por MCP)."
                if quien.administra else "Los datos por MCP son solo del administrador y los coordinadores.")
    elif not quien.puede("agente.usar"):
        base = "Su rol no usa el asistente."
    motivos: dict[str, str | None] = {}
    for a in ALCANCES_DATOS:
        if base:
            motivos[a] = base
        elif a == "lectura" and not quien.puede("exportar"):
            motivos[a] = ("Solo el administrador: leer personas por MCP es sacar sus datos del panel, como "
                          "exportarlos.")
        elif a == "analitica" and not quien.puede("analitica.ver"):
            motivos[a] = "Su rol no ve la analítica."
        elif a == "escritura" and not (agente["escritura"] and mcp["escritura"]):
            motivos[a] = "Las propuestas de cambios están apagadas en Ajustes."
        else:
            motivos[a] = None
    return motivos


def anular_propuestas(db: Database, claves_h: list[str], codigo: str = "clave_revocada") -> int:
    """Anula las propuestas pendientes (`mcp_propuestas`, app/api/mcp.py) de esas claves: una clave revocada,
    reemplazada o vencida ya no habla por la persona, y quien la robó no debe dejarle cambios por aprobar. Quedan sin
    su tarjeta (los valores eran de personas) y vencen a los `DIAS_PROPUESTA_DECIDIDA` días. Devuelve cuántas."""
    if not claves_h:
        return 0
    ahora = _ahora()
    mensaje = ("Se anuló: la clave con que se propuso se revocó o se reemplazó." if codigo == "clave_revocada" else
               "Se anuló: la clave con que se propuso ya no vale.")
    return db.mcp_propuestas.update_many(
        {"clave_h": {"$in": list(claves_h)}, "estado": "pendiente"},
        {"$set": {"estado": "anulada", "decidida_en": ahora, "expira": ahora + timedelta(days=DIAS_PROPUESTA_DECIDIDA),
                  "error": {"codigo": codigo, "mensaje": mensaje}},
         "$unset": {"entrada": "", "confirmacion": ""}}).modified_count


def _info(doc: dict | None, request: Request) -> dict:
    return {"tiene": doc is not None, "creada": doc.get("creada") if doc else None,
            "usada": doc.get("usada") if doc else None, "direccion": direccion_mcp(request)}


def info_claves(db: Database, request: Request, quien: Quien) -> dict:
    """Lo que ve Mi cuenta: la clave de la presentación arriba (como siempre: `tiene`, `creada`, `usada`, `direccion`),
    la de datos en `datos` (`alcances` guardados y `vigentes`: los que hoy valen), los alcances de datos que la persona
    puede pedir (`permitidos`) y por qué no los demás (`motivos`), y cuántas propuestas esperan su aprobación."""
    from ..agente import politica  # aquí: politica importa el proveedor del modelo
    ahora = _ahora()
    docs = list(db.claves_mcp.find({"uid": quien.uid}, {"creada": 1, "usada": 1, "tipo": 1, "alcances": 1,
                                                        "expira": 1}))
    presentacion = next((d for d in docs if tipo_de(d) == "presentacion"), None)
    datos = next((d for d in docs if tipo_de(d) == "datos" and not vencida(d, ahora)), None)
    motivos = alcances_de_datos(quien, politica.leer(db)[0])
    alcances = [a for a in (datos or {}).get("alcances") or [] if a in ALCANCES_DATOS]
    pendientes = db.mcp_propuestas.count_documents({"uid": quien.uid, "estado": "pendiente", "vence": {"$gt": ahora}})
    return {**_info(presentacion, request),
            "datos": {"tiene": datos is not None, "creada": (datos or {}).get("creada"),
                      "usada": (datos or {}).get("usada"), "expira": (datos or {}).get("expira"),
                      "alcances": alcances, "vigentes": [a for a in alcances if motivos.get(a) is None]},
            "permitidos": [a for a in ALCANCES_DATOS if motivos[a] is None],
            "motivos": {a: m for a, m in motivos.items() if m}, "propuestas_pendientes": pendientes}


@r.get("/pantalla/clave")
def ver_clave(request: Request, db: Database = Depends(obtener_db),
              quien: Quien = Depends(requiere("presentacion.ver"))):
    return info_claves(db, request, quien)


class ClaveEntrada(BaseModel):
    """El cuerpo opcional de POST /api/pantalla/clave. Sin cuerpo (o `{}`) es la de la presentación, como siempre."""
    model_config = ConfigDict(extra="forbid")
    tipo: Literal["presentacion", "datos"] | None = None
    alcances: list[Literal["presentacion", "lectura", "analitica", "escritura"]] | None = Field(None, max_length=4)


def _tipo_y_alcances(cuerpo: ClaveEntrada | None) -> tuple[str, list[str]]:
    """(tipo, alcances) pedidos, o 422 si no casan: la de la presentación no lleva datos y la de datos nunca lleva la
    presentación (cada una en su equipo: la del proyector no debe poder leer personas)."""
    alcances = sorted(set((cuerpo.alcances if cuerpo else None) or []))
    tipo = (cuerpo.tipo if cuerpo else None) or ("datos" if any(a != "presentacion" for a in alcances) else
                                                 "presentacion")
    if tipo == "presentacion":
        if alcances not in ([], ["presentacion"]):
            raise HTTPException(422, "La clave de la presentación no lleva datos: cree aparte la clave de datos")
        return tipo, ["presentacion"]
    if not alcances or "presentacion" in alcances:
        raise HTTPException(422, "La clave de datos lleva uno o más de lectura, analitica y escritura (nunca la "
                                 "presentación: esa tiene su propia clave)")
    return tipo, alcances


@r.post("/pantalla/clave")
async def crear_clave(request: Request, cuerpo: ClaveEntrada | None = None, db: Database = Depends(obtener_db),
                      quien: Quien = Depends(requiere("presentacion.ver"))):
    cfg = request.app.state.cfg
    tipo, alcances = _tipo_y_alcances(cuerpo)

    def crear():
        if tipo == "datos":
            from ..agente import politica  # aquí: politica importa el proveedor del modelo
            motivos = alcances_de_datos(quien, politica.leer(db)[0])
            negados = [a for a in alcances if motivos.get(a)]
            if negados:
                raise HTTPException(403, {**SIN_PERMISO, "mensaje": motivos[negados[0]], "alcances": negados})
        firma = huella_de_sesion(db, cfg, quien.uid)
        ahora = _ahora()
        doc = {"uid": quien.uid, "huella": firma, "creada": ahora, "usada": None, "tipo": tipo, "alcances": alcances}
        if tipo == "datos":
            clave = PREFIJO_CLAVE_DATOS + secrets.token_urlsafe(32)
            viejas = [d["_id"] for d in db.claves_mcp.find({"uid": quien.uid, "tipo": "datos"}, {"_id": 1})]
            anular_propuestas(db, viejas)
            db.claves_mcp.delete_many({"uid": quien.uid, "tipo": "datos"})
            doc["expira"] = ahora + timedelta(days=DIAS_CLAVE_DATOS)
        else:
            clave = PREFIJO_CLAVE + secrets.token_urlsafe(32)
            db.claves_mcp.delete_many({"uid": quien.uid, "tipo": {"$ne": "datos"}})
        db.claves_mcp.insert_one({"_id": huella_clave(clave), **doc})
        bd.auditar(db, quien, "crear_clave_mcp", "usuario", quien.uid, {"tipo": tipo, "alcances": alcances})
        return clave, doc.get("expira")

    clave, expira = await run_in_threadpool(crear)
    info = await run_in_threadpool(info_claves, db, request, quien)
    nueva = {"clave": clave, "tipo": tipo, "alcances": alcances}
    if tipo == "datos":  # solo la cabecera: nunca una dirección con la clave
        return {**info, **nueva, "expira": expira}
    return {**info, **nueva, "direccion_con_clave": f"{direccion_mcp(request)}?clave={clave}"}


@r.delete("/pantalla/clave")
def revocar_clave(request: Request, tipo: Literal["presentacion", "datos"] | None = Query(None),
                  db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("presentacion.ver"))):
    """Revoca la clave de ese tipo (sin `tipo`, las dos). Las propuestas pendientes de la de datos quedan anuladas."""
    docs = [d for d in db.claves_mcp.find({"uid": quien.uid}, {"tipo": 1}) if tipo is None or tipo_de(d) == tipo]
    anular_propuestas(db, [d["_id"] for d in docs if tipo_de(d) == "datos"])
    borradas = db.claves_mcp.delete_many({"_id": {"$in": [d["_id"] for d in docs]}}).deleted_count if docs else 0
    if borradas:
        bd.auditar(db, quien, "revocar_clave_mcp", "usuario", quien.uid, {"tipo": tipo or "todas"})
    return {"revocada": bool(borradas), **info_claves(db, request, quien)}
