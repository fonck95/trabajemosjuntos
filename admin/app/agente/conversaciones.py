"""Lo que el asistente guarda en MongoDB: conversaciones, mensajes y uso diario. Todo síncrono (pymongo): el bucle lo
llama con `run_in_threadpool`.

* `agente_conversaciones`: una por conversación, de un solo dueño (`uid`). Guarda congelados el `system` y la lista
  de herramientas con que se creó (la caché del proveedor y el razonamiento conservado exigen que el prefijo no
  cambie), las definiciones de Mnemo, el proveedor del modelo (`proveedor`: «mnemo» o «anthropic»; las de antes, sin
  el campo, son de Anthropic) y el modelo que se le pidió (`modelo`), `personas` (los ids de las personas cuyos datos
  vio el modelo: si alguna se suprime o deja de autorizar, la conversación se borra entera), lo que espera aprobación
  (`pendiente`), lo que la persona no aprobó al quitarlo (`rechazadas`: los `tool_use` que vuelven como rechazados si
  el turno se corta antes de guardar sus resultados), las escrituras de Mnemo ya mandadas (`mnemo_intentadas`, que
  anota `herramientas/mnemo.py`: Mnemo no tiene clave de idempotencia) y el candado del turno en curso
  (`ocupada_hasta`: el turno lo renueva mientras corre y vence solo en `ARRIENDO`, así un proceso caído no deja la
  conversación tomada más de un minuto y medio).
* `agente_mensajes`: un documento por mensaje, con `seq` creciente; nunca se edita lo guardado (append-only). Los
  bloques van como texto JSON (`contenido`): vuelven idénticos al reenviarlos y aceptan cualquier clave que escriba el
  modelo (también «$x» o «a.b»). `replay` dice si el mensaje se le reenvía al modelo (un rechazo o un aviso, no).
* `agente_uso`: mensajes, tokens y (con Mnemo) créditos por persona y día (hora de Colombia), para el tope diario y
  para ver el gasto.
* `agente_olvidos`: quién dejó de autorizar en la última hora (`persona_id` y `ts`, nada más; lo anota
  `db.olvidar_en_conversaciones`). Un turno que leía a esa persona cuando llegó el «no» todavía no la tenía anotada:
  la busca ahí al anotarla (`dejaron_de_autorizar`).
* Retención: `expira` (fecha) de la conversación y de sus mensajes se renueva en cada turno; los índices TTL de
  `db._indices()` los borran solos al vencer.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import modelo
from .llm import CENTINELA

CONVERSACIONES, MENSAJES, USO, OLVIDOS = "agente_conversaciones", "agente_mensajes", "agente_uso", "agente_olvidos"
ARRIENDO = timedelta(seconds=90)  # el turno lo renueva cada `bucle.RENOVAR_S` mientras corre
LISTA_MAX = 30
TITULO_MAX = 80
TOPE_TOKENS = 300_000  # entrada de la última ronda: pasado esto la conversación no admite más (409 «larga»)
TOPE_MENSAJES = 400
PROVEEDOR_POR_DEFECTO = "anthropic"  # el de las conversaciones creadas antes de que se guardara


class ConversacionBorrada(Exception):
    """La conversación desapareció a mitad del turno: su dueño la borró o se suprimió una persona que aparecía en
    ella. Lo que quedaba por guardar no se guarda."""


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def a_json(x: Any) -> str:
    # ASCII: un carácter suelto inválido (un sustituto UTF-16 que mandó el modelo) no rompe el BSON
    return json.dumps(x, ensure_ascii=True, separators=(",", ":"), default=str)


def de_json(texto: Any, defecto: Any = None) -> Any:
    if not isinstance(texto, str):
        return defecto
    try:
        return json.loads(texto)
    except (TypeError, ValueError):
        return defecto


def texto_valido(s: str) -> str:
    """El texto sin sustitutos sueltos (llegan de un JSON con «\\ud800»): MongoDB solo guarda UTF-8 válido."""
    return s.encode("utf-8", "replace").decode("utf-8")


def limpio(x: Any) -> Any:
    """`x` sin sustitutos sueltos en sus textos (los que no caben en UTF-8). El SDK manda el JSON en UTF-8 y un
    carácter así en el historial haría fallar cada petición siguiente de la conversación. Lo que ya es válido vuelve
    tal cual (el mismo objeto): no cambia el prefijo de la conversación."""
    if isinstance(x, str):
        try:
            x.encode("utf-8")
            return x
        except UnicodeEncodeError:
            return x.encode("utf-8", "replace").decode("utf-8")
    if isinstance(x, list):
        return [limpio(v) for v in x]
    if isinstance(x, dict):
        return {(limpio(k) if isinstance(k, str) else k): limpio(v) for k, v in x.items()}
    return x


def titulo_de(texto: str) -> str:
    """Los primeros 80 caracteres del primer mensaje (sin llamar al modelo)."""
    return re.sub(r"\s+", " ", texto_valido(texto)).strip()[:TITULO_MAX] or "Conversación"


# ───────────────────────────── Conversaciones ─────────────────────────────

def crear(db: Database, cid: int, uid: int, titulo: str, sistema: str, herramientas: list[dict], mnemo: list[dict],
          dias: int, turno: str, modelo_ia: str, proveedor: str = PROVEEDOR_POR_DEFECTO) -> dict:
    """Crea la conversación ya tomada por el turno que la crea, con su proveedor del modelo congelado."""
    t = ahora()
    doc = {"_id": cid, "uid": uid, "titulo": titulo, "sistema": sistema, "herramientas": a_json(herramientas),
           "mnemo": a_json(mnemo), "proveedor": proveedor, "modelo": modelo_ia, "personas": [], "n_mensajes": 0,
           "tokens_ultima": 0, "pendiente": None, "creada": t, "actualizada": t, "expira": t + timedelta(days=dias),
           "ocupada_hasta": t + ARRIENDO, "turno": turno}
    db[CONVERSACIONES].insert_one(doc)
    return doc


def proveedor_de(conv: dict | None) -> str:
    """El proveedor del modelo con que se creó la conversación («mnemo» o «anthropic»)."""
    p = (conv or {}).get("proveedor")
    return p if isinstance(p, str) and p else PROVEEDOR_POR_DEFECTO


def de_usuario(db: Database, cid: int, uid: int) -> dict | None:
    """La conversación si existe y es de `uid` (si no, None: para la API, 404 en los dos casos)."""
    return db[CONVERSACIONES].find_one({"_id": cid, "uid": uid})


def larga(conv: dict) -> bool:
    return (conv.get("tokens_ultima") or 0) > TOPE_TOKENS or (conv.get("n_mensajes") or 0) >= TOPE_MENSAJES


def listar(db: Database, uid: int) -> list[dict]:
    """Las 30 más recientes de `uid`, sin cargar lo pesado (dos del mismo milisegundo: primero la más nueva)."""
    filas = db[CONVERSACIONES].aggregate([
        {"$match": {"uid": uid}}, {"$sort": {"actualizada": -1, "_id": -1}}, {"$limit": LISTA_MAX},
        {"$project": {"titulo": 1, "actualizada": 1, "pendiente": {"$ne": [{"$ifNull": ["$pendiente", None]}, None]}}},
    ])
    return [{"id": f["_id"], "titulo": f.get("titulo") or "Conversación",
             "actualizada": f["actualizada"].isoformat() if isinstance(f.get("actualizada"), datetime) else None,
             "pendiente": bool(f.get("pendiente"))} for f in filas]


def tomar(db: Database, cid: int, uid: int, turno: str) -> dict | None:
    """El candado del turno: la conversación de `uid` si no la tiene otro turno vigente (None si la tiene)."""
    t = ahora()
    return db[CONVERSACIONES].find_one_and_update(
        {"_id": cid, "uid": uid, "$or": [{"ocupada_hasta": None}, {"ocupada_hasta": {"$lte": t}}]},
        {"$set": {"ocupada_hasta": t + ARRIENDO, "turno": turno}}, return_document=ReturnDocument.AFTER)


def renovar_candado(db: Database, cid: int, turno: str) -> bool:
    """Alarga el candado mientras su turno sigue vivo: si el proceso muere, vence solo en `ARRIENDO`. False si ya
    no es de ese turno."""
    r = db[CONVERSACIONES].update_one({"_id": cid, "turno": turno}, {"$set": {"ocupada_hasta": ahora() + ARRIENDO}})
    return r.matched_count == 1


def soltar(db: Database, cid: int, turno: str) -> None:
    db[CONVERSACIONES].update_one({"_id": cid, "turno": turno}, {"$set": {"ocupada_hasta": None, "turno": None}})


def ocupada(conv: dict) -> bool:
    hasta = conv.get("ocupada_hasta")
    return isinstance(hasta, datetime) and hasta > ahora()


def otra_ocupada(db: Database, uid: int, cid: int | None) -> bool:
    """¿Tiene `uid` un turno vigente en otra conversación? (un turno a la vez por persona, también entre procesos)"""
    q: dict[str, Any] = {"uid": uid, "ocupada_hasta": {"$gt": ahora()}}
    if cid is not None:
        q["_id"] = {"$ne": cid}
    return db[CONVERSACIONES].find_one(q, {"_id": 1}) is not None


def renovar(db: Database, cid: int, dias: int) -> datetime:
    """Mueve el vencimiento de la conversación y de sus mensajes a `dias` desde hoy (se usa: se conserva)."""
    expira = ahora() + timedelta(days=dias)
    db[CONVERSACIONES].update_one({"_id": cid}, {"$set": {"expira": expira}})
    db[MENSAJES].update_many({"conversacion": cid}, {"$set": {"expira": expira}})
    return expira


def sumar_personas(db: Database, cid: int, ids: set[int]) -> None:
    if ids:
        db[CONVERSACIONES].update_one({"_id": cid}, {"$addToSet": {"personas": {"$each": sorted(ids)}}})


def tiene_personas(db: Database, cid: Any) -> bool:
    """¿El modelo ya recibió en esta conversación datos de alguna persona (`personas` no está vacía)? Lo que escribe en
    ella no se proyecta ante una sala (la guarda de la herramienta `presentacion`). Sin conversación, no."""
    if not isinstance(cid, int) or isinstance(cid, bool):
        return False
    return db[CONVERSACIONES].find_one({"_id": cid, "personas.0": {"$exists": True}}, {"_id": 1}) is not None


def suprimidas(db: Database, ids: set[int]) -> list[int]:
    """Las de `ids` que ya se suprimieron (la supresión pudo llegar mientras una herramienta las leía)."""
    return [p["_id"] for p in db.personas.find({"_id": {"$in": sorted(ids)}, "eliminado": True}, {"_id": 1})]


def dejaron_de_autorizar(db: Database, ids: set[int], desde: datetime) -> list[int]:
    """Las de `ids` que dejaron de autorizar desde `desde` (`db.olvidar_en_conversaciones` lo anota en `OLVIDOS` antes
    de borrar las conversaciones que ya las tenían): el «no» pudo llegar mientras una herramienta las leía."""
    q = {"persona_id": {"$in": sorted(ids)}, "ts": {"$gte": desde}}
    return sorted({d["persona_id"] for d in db[OLVIDOS].find(q, {"persona_id": 1})})


def borrar(db: Database, cid: int, uid: int) -> bool:
    """Borra la conversación de `uid` y sus mensajes (los mensajes antes y después: no queda ninguno huérfano aunque un
    turno de otro proceso alcance a guardar uno en el medio)."""
    if db[CONVERSACIONES].find_one({"_id": cid, "uid": uid}, {"_id": 1}) is None:
        return False
    db[MENSAJES].delete_many({"conversacion": cid})
    db[CONVERSACIONES].delete_one({"_id": cid, "uid": uid})
    db[MENSAJES].delete_many({"conversacion": cid})
    return True


# ───────────────────────────── Lo que espera aprobación ─────────────────────────────

def pendiente_de(conv: dict | None) -> dict | None:
    p = de_json((conv or {}).get("pendiente"))
    return p if isinstance(p, dict) and isinstance(p.get("llamadas"), list) else None


def poner_pendiente(db: Database, cid: int, pendiente: dict) -> None:
    db[CONVERSACIONES].update_one({"_id": cid}, {"$set": {"pendiente": a_json(pendiente)}})


def quitar_pendiente(db: Database, cid: int, crudo: str, rechazadas: list[str] = ()) -> bool:
    """Quita `crudo` (el texto guardado) solo si sigue siendo lo pendiente: así dos turnos no lo atienden dos veces. En
    el mismo paso guarda lo que la persona no aprobó (`rechazadas`, ids de `tool_use`): si el turno se corta antes de
    guardar los resultados, el siguiente se lo devuelve al modelo como rechazado."""
    r = db[CONVERSACIONES].update_one({"_id": cid, "pendiente": crudo},
                                      {"$set": {"pendiente": None, "rechazadas": list(rechazadas)}})
    return r.modified_count == 1


# ───────────────────────────── Mensajes ─────────────────────────────

def guardar(db: Database, cid: int, uid: int, expira: datetime, rol: str, contenido: Any = None, replay: bool = True,
            campos: dict | None = None, tokens: int | None = None) -> int:
    """Agrega un mensaje al final (append-only) y devuelve su `seq`. Lanza `ConversacionBorrada` si ya no existe."""
    t = ahora()
    poner: dict[str, Any] = {"actualizada": t}
    if tokens is not None:
        poner["tokens_ultima"] = tokens
    c = db[CONVERSACIONES].find_one_and_update({"_id": cid}, {"$inc": {"n_mensajes": 1}, "$set": poner},
                                               projection={"n_mensajes": 1}, return_document=ReturnDocument.AFTER)
    if c is None:
        raise ConversacionBorrada()
    # Los campos también sin sustitutos sueltos: un resumen de herramienta puede citar un texto remoto cortado a mitad
    # de un emoji, y MongoDB solo guarda UTF-8 válido
    doc: dict[str, Any] = {"conversacion": cid, "uid": uid, "seq": c["n_mensajes"], "rol": rol, "replay": replay,
                           "ts": t, "expira": expira, **limpio(campos or {})}
    if contenido is not None:
        doc["contenido"] = a_json(contenido)
    db[MENSAJES].insert_one(doc)
    return doc["seq"]


def historial(db: Database, cid: int) -> list[dict]:
    """Los mensajes que se le reenvían al modelo, en orden: [{role, content}]."""
    out = []
    for d in db[MENSAJES].find({"conversacion": cid, "replay": True}, {"rol": 1, "contenido": 1}).sort("seq", 1):
        contenido = de_json(d.get("contenido"))
        if d.get("rol") in ("user", "assistant") and isinstance(contenido, list):
            out.append({"role": d["rol"], "content": contenido})
    return out


def mensajes_de(db: Database, cid: int) -> list[dict]:
    return list(db[MENSAJES].find({"conversacion": cid}).sort("seq", 1))


def para_interfaz(conv: dict, docs: list[dict], etiquetas: dict[str, str]) -> dict:
    """La conversación como la pinta el widget: `mensajes` de la persona (su texto, sin el contexto del panel) y del
    asistente (partes: texto, notas de progreso, herramientas con su estado y avisos), lo que espera aprobación (con
    `vieja` si su tarjeta la guardó una versión anterior del panel, que no mostraba los valores enteros) y su
    `proveedor`. Las notas de progreso son los `thinking` de Anthropic (con `display: "updates"`); los de Mnemo son
    resúmenes del razonamiento del modelo y no se muestran."""
    proveedor = proveedor_de(conv)
    notas = proveedor == "anthropic"
    mensajes: list[dict] = []
    actual: dict | None = None
    partes: dict[str, dict] = {}

    def del_asistente() -> list[dict]:
        nonlocal actual
        if actual is None:
            actual = {"rol": "asistente", "partes": []}
            mensajes.append(actual)
        return actual["partes"]

    def estado(lista: Any) -> None:
        for h in lista if isinstance(lista, list) else []:
            p = partes.get(h.get("id")) if isinstance(h, dict) else None
            if p is not None:
                p["estado"], p["resumen"] = h.get("estado") or p["estado"], h.get("resumen") or ""

    for d in docs:
        rol = d.get("rol")
        if rol == "user":
            estado(d.get("herramientas"))
            if isinstance(d.get("texto"), str):
                mensajes.append({"rol": "usuario", "texto": d["texto"]})
                actual = None
        elif rol == "assistant" and d.get("replay"):
            for b in de_json(d.get("contenido"), []):
                t = b.get("type") if isinstance(b, dict) else None
                if t == "text" and b.get("text"):
                    ps = del_asistente()
                    if ps and ps[-1]["tipo"] == "texto":
                        ps[-1]["texto"] += b["text"]
                    else:
                        ps.append({"tipo": "texto", "texto": b["text"]})
                elif t == "thinking" and notas and b.get("thinking") and b["thinking"] != CENTINELA:
                    del_asistente().append({"tipo": "progreso", "texto": b["thinking"]})
                elif t == "tool_use":
                    nombre = str(b.get("name") or "")[:64]
                    p = {"tipo": "herramienta", "id": b.get("id"), "nombre": nombre,
                         "etiqueta": etiquetas.get(nombre, nombre), "estado": "error", "resumen": "Interrumpida"}
                    partes[str(b.get("id"))] = p
                    del_asistente().append(p)
        elif rol == "aviso":
            del_asistente().append({"tipo": "aviso", "texto": d.get("texto") or "", "nivel": d.get("nivel") or "info"})
    pendientes = []
    pend = pendiente_de(conv)
    if pend is not None:
        estado(pend.get("ui"))
        for ll in pend["llamadas"]:
            if not isinstance(ll, dict):
                continue
            if ll.get("id") in partes:
                partes[ll["id"]]["estado"], partes[ll["id"]]["resumen"] = "pendiente", ""
            tarjeta = ll.get("confirmacion") if isinstance(ll.get("confirmacion"), dict) else {}
            p = {"id": ll.get("id"), "nombre": ll.get("nombre"), "etiqueta": ll.get("etiqueta") or ll.get("nombre"),
                 "titulo": tarjeta.get("titulo"), "detalle": tarjeta.get("detalle") or [],
                 "aviso": tarjeta.get("aviso")}
            if tarjeta.get("entera") is not True:
                # La guardó una versión anterior del panel, que cortaba cada valor a 500 caracteres sin marcarlo: el
                # widget no ofrece aprobarla (y el servidor no la aprueba, `bucle.abrir_confirmacion`)
                p["vieja"] = True
            pendientes.append(p)
    return {"id": conv["_id"], "titulo": conv.get("titulo") or "Conversación", "mensajes": mensajes,
            "pendientes": pendientes, "proveedor": proveedor}


# ───────────────────────────── Uso diario ─────────────────────────────

def _dia() -> str:
    return modelo.hoy_local().isoformat()


def contar_mensaje(db: Database, uid: int, maximo: int) -> int | None:
    """Suma un mensaje al día de `uid` si no llegó a `maximo` y devuelve cuántos lleva; None si ya llegó. Atómico: con
    el documento lleno el filtro no casa y el upsert choca con su `_id`."""
    if maximo <= 0:
        return None
    dia = _dia()
    try:
        d = db[USO].find_one_and_update(
            {"_id": f"{uid}|{dia}", "mensajes": {"$lt": maximo}},
            {"$inc": {"mensajes": 1}, "$set": {"ts": ahora()},
             "$setOnInsert": {"uid": uid, "dia": dia, "entrada": 0, "salida": 0, "cache_lectura": 0,
                              "cache_escritura": 0}},
            upsert=True, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        return None
    return int(d["mensajes"])


def uso_de(db: Database, uid: int) -> int:
    d = db[USO].find_one({"_id": f"{uid}|{_dia()}"}, {"mensajes": 1})
    return int((d or {}).get("mensajes") or 0)


def sumar_uso(db: Database, uid: int, entrada: int, salida: int, lectura: int, escritura: int,
              creditos: float | None = None) -> None:
    """Suma una ronda al día de `uid`: tokens y, con Mnemo, los créditos de la cuenta conectada que gastó."""
    dia = _dia()
    sumar: dict[str, Any] = {"entrada": entrada, "salida": salida, "cache_lectura": lectura,
                             "cache_escritura": escritura}
    if creditos:
        sumar["creditos"] = float(creditos)
    db[USO].update_one({"_id": f"{uid}|{dia}"}, {
        "$inc": sumar, "$set": {"ts": ahora()}, "$setOnInsert": {"uid": uid, "dia": dia, "mensajes": 0}}, upsert=True)
