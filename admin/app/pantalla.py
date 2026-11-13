"""La pantalla en off: la presentación de la propuesta que manejan los agentes (el asistente del panel y uno externo por
MCP) y que la vista Presentación en modo en off (/presentacion?off=1) sigue desde cualquier navegador: el proyector, un
televisor o la misma pestaña.

Cada usuario tiene una (`pantallas`, _id = uid; 0 el administrador): el capítulo y el paso, la explicación en pantalla,
lo que se ve (el panel de texto o «Solo 3D», el índice, las fichas), si llena la ventana y lo visual de la presentación
técnica (`VISUAL`: la cámara, la obra enfocada, hoy o con el proyecto, la ficha técnica abierta, la inmersión en un
modelo del atlas y el tema). Al cambiar de paso lo visual vuelve a lo del paso, salvo el tema. Solo la cambian las órdenes de
un agente: lo que se toca a mano en la vista del panel no la mueve. La versión `v` sube con cada cambio; la pantalla
pregunta cada poco por ella (`GET /api/pantalla?v=`) y aplica solo lo nuevo. Cada pregunta deja `visto`: así un agente
sabe si hay una pantalla abierta (`conectada`).

No guarda datos de personas: el guion de la propuesta es público y la explicación pasa antes por las reglas del
subtítulo (`interfaz._explicacion_visible`): sin «@» ni números de 7 o más dígitos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import re

from pymongo import ReturnDocument
from pymongo.database import Database

# Lo que guarda la pantalla además de `v`, `actualizada`, `por` y `visto`. `orden_completa` cambia con cada orden de
# pantalla completa (aunque `completa` no cambie): la pantalla que la devolvió con Escape vuelve a llenar la ventana
# Lo visual de la presentación técnica (la op `visual` de la herramienta, la orden `visual` de mando.js), con lo que vale
# en cada paso. El tema no vuelve al cambiar de paso: None es «el del navegador»
VISUAL_INICIAL = {"enfoque": None, "camara": "paso", "rumbo": None, "girar": False, "comparar": "proyecto",
                  "detalle": None, "inmersion": None}
VISUAL = (*VISUAL_INICIAL, "tema")
CAMARAS = ("paso", "aerea", "oblicua", "rasante", "cerca", "lejos")
CAMPOS = ("capitulo", "paso", "explicacion", "panel", "indice", "fichas", "completa", "orden_completa", *VISUAL)
# Una pantalla pregunta cada 1,5 s (vistas/presentacion.js): sin preguntas en este tiempo, se da por cerrada. Holgado: un
# navegador espacia los relojes de una pestaña que no está a la vista
VIVA_S = 10
# Quién la cambió: el asistente del panel o un agente por MCP
ORIGENES = ("asistente", "mcp")
_ID_PIEZA = re.compile(r"[a-z0-9_]{1,40}")   # un componente o una inmersión (`ID_PASO` del guion)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(t: Any) -> datetime | None:
    if not isinstance(t, datetime):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def inicial(guion: Any) -> dict:
    """La pantalla antes de la primera orden: la portada, con el panel de texto y sin llenar la ventana."""
    return {"capitulo": guion.capitulos[0]["id"], "paso": 1, "explicacion": None, "panel": True, "indice": False,
            "fichas": False, "completa": False, "orden_completa": 0, **VISUAL_INICIAL, "tema": None}


def estado(doc: dict | None, guion: Any) -> dict:
    """El estado vigente (lo guardado sobre el inicial) con `v`. Si el guion cambió y el capítulo o el paso guardados ya no
    existen, vuelve a la portada sin explicación (era la de otro paso)."""
    e = inicial(guion)
    for k in CAMPOS:
        if doc and k in doc:
            e[k] = doc[k]
    ci = guion.por_id(e["capitulo"]) if isinstance(e["capitulo"], str) else None
    paso = e["paso"]
    if ci is None or isinstance(paso, bool) or not isinstance(paso, int) or \
            not 1 <= paso <= len(guion.capitulos[ci]["pasos"]):
        base = inicial(guion)
        e.update(capitulo=base["capitulo"], paso=1, explicacion=None, **VISUAL_INICIAL)
    for k in ("panel", "indice", "fichas", "completa"):
        e[k] = e[k] is True if k != "panel" else e[k] is not False
    if not isinstance(e["explicacion"], str) or not e["explicacion"]:
        e["explicacion"] = None
    if isinstance(e["orden_completa"], bool) or not isinstance(e["orden_completa"], int) or e["orden_completa"] < 0:
        e["orden_completa"] = 0
    _visual_valido(e, guion)
    e["v"] = int(doc.get("v") or 0) if doc else 0
    return e


def _id_pieza(v: Any) -> bool:
    return isinstance(v, str) and bool(_ID_PIEZA.fullmatch(v))


def _visual_valido(e: dict, guion: Any) -> None:
    """Lo visual guardado, con los valores que admite la presentación: lo que no cumple (o un componente que ya no
    está en el capítulo, una inmersión que ya no está en el catálogo, si el guion cambió) vuelve a lo del paso."""
    ci = guion.por_id(e["capitulo"])
    ids = {x["id"] for x in guion.capitulos[ci].get("componentes") or []} if ci is not None else set()
    lugar = {x["id"] for x in guion.capitulos[ci].get("componentes") or [] if x.get("enfoque")} if ci is not None else set()
    inm = {i["id"] for i in getattr(guion, "inmersiones", ()) or ()} | {"maqueta"}
    buenos = {"enfoque": e["enfoque"] is None or (_id_pieza(e["enfoque"]) and e["enfoque"] in lugar),
              "detalle": e["detalle"] is None or (_id_pieza(e["detalle"]) and e["detalle"] in ids),
              "inmersion": e["inmersion"] is None or (_id_pieza(e["inmersion"]) and e["inmersion"] in inm),
              "camara": e["camara"] in CAMARAS,
              "rumbo": e["rumbo"] is None or (isinstance(e["rumbo"], int) and not isinstance(e["rumbo"], bool)
                                              and 0 <= e["rumbo"] <= 359),
              "girar": isinstance(e["girar"], bool), "comparar": e["comparar"] in ("hoy", "proyecto")}
    for k, bien in buenos.items():
        if not bien:
            e[k] = VISUAL_INICIAL[k]
    if e["tema"] not in (None, "claro", "oscuro"):
        e["tema"] = None


def conectada(doc: dict | None, ahora: datetime | None = None) -> bool:
    """¿Hay una pantalla en off abierta? (preguntó por su estado hace menos de VIVA_S)."""
    visto = _aware((doc or {}).get("visto"))
    return visto is not None and (ahora or _ahora()) - visto < timedelta(seconds=VIVA_S)


def para_pantalla(e: dict) -> dict:
    """Lo que recibe la pantalla: la versión y los campos, nada más."""
    return {"v": e["v"], **{k: e[k] for k in CAMPOS}}


def leer(db: Database, uid: int) -> dict | None:
    return db.pantallas.find_one({"_id": uid})


def guardar(db: Database, uid: int, cambios: dict, por: str) -> dict:
    """Aplica `cambios` (solo campos de CAMPOS) y sube la versión. Devuelve el documento nuevo."""
    malos = set(cambios) - set(CAMPOS)
    if malos or por not in ORIGENES:
        raise ValueError(f"pantalla.guardar: {sorted(malos) or por}")
    return db.pantallas.find_one_and_update(
        {"_id": uid}, {"$set": {**cambios, "actualizada": _ahora(), "por": por}, "$inc": {"v": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)


def marcar_vista(db: Database, uid: int) -> dict | None:
    """La pantalla preguntó: queda `visto` (está abierta). Devuelve el documento (None si nunca recibió una orden)."""
    return db.pantallas.find_one_and_update({"_id": uid}, {"$set": {"visto": _ahora()}}, upsert=True,
                                            return_document=ReturnDocument.AFTER)


def describir(e: dict, guion: Any) -> str:
    """«Vivienda (vivienda), paso 3 de 6: <título>; en pantalla: «…»; Solo 3D; llena la ventana» para el contexto del
    asistente y para el estado que devuelve la herramienta."""
    ci = guion.por_id(e["capitulo"])
    c = guion.capitulos[ci]
    titulo = " ".join(str(c["pasos"][e["paso"] - 1].get("titulo") or "").split())[:160]
    partes = [f"{c['nombre']} ({c['id']}), paso {e['paso']} de {len(c['pasos'])}" + (f": {titulo}" if titulo else "")]
    if e["explicacion"]:
        partes.append(f"en pantalla: «{e['explicacion']}»")
    if not e["panel"]:
        partes.append("Solo 3D (sin el panel de texto)")
    if e["indice"]:
        partes.append("con el índice abierto")
    if e["fichas"]:
        partes.append("con las fichas abiertas")
    if e["completa"]:
        partes.append("llena la ventana")
    nombres = {x["id"]: x.get("nombre") or x["id"] for x in c.get("componentes") or []}
    inm = {i["id"]: i.get("nombre") or i["id"] for i in getattr(guion, "inmersiones", ()) or ()}
    if e.get("inmersion") == "maqueta":
        partes.append("la maqueta en lugar del modelo del atlas del paso")
    elif e.get("inmersion"):
        partes.append(f"el modelo del atlas «{inm.get(e['inmersion'], e['inmersion'])}» ({e['inmersion']})")
    if e.get("enfoque"):
        partes.append(f"la cámara en «{nombres.get(e['enfoque'], e['enfoque'])}» ({e['enfoque']})")
    if e.get("detalle"):
        partes.append(f"la ficha técnica de «{nombres.get(e['detalle'], e['detalle'])}» ({e['detalle']})")
    if e.get("comparar") == "hoy":
        partes.append("el sitio como está hoy (sin el proyecto)")
    camara = [x for x in (f"vista {e['camara']}" if e.get("camara") not in (None, "paso") else "",
                          f"mirando desde el rumbo {e['rumbo']}°" if e.get("rumbo") is not None else "",
                          "girando" if e.get("girar") else "") if x]
    if camara:
        partes.append("cámara: " + ", ".join(camara))
    if e.get("tema"):
        partes.append(f"tema {e['tema']}")
    return "; ".join(partes)
