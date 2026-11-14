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

Y el recorrido narrado (`app/recorrido.py`): el último que armó un agente, con su destino (la vista de la pestaña o
el proyector, o la pantalla en off: donde suena, en un solo lugar), el último control que le mandaron (`control_recorrido`,
que la pantalla aplica una sola vez por número) y el avance que manda la página que lo reproduce (`progreso`, sin subir
la versión). Mientras un recorrido no está cerrado, la base (capítulo, paso y lo visual) es su última escena; otra orden lo
«colapsa» (`colapsar`): deja como base la escena que la sala está viendo y lo cierra.

No guarda datos de personas: el guion de la propuesta es público y todo texto para la pantalla pasa antes por las reglas
de lo que se proyecta (`app/proyectable.py`): sin «@» ni números de 7 o más dígitos (y los del recorrido, sin plata)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import re
import secrets

from pymongo import ReturnDocument
from pymongo.database import Database

from . import recorrido as rec

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
# Quién la cambió: el asistente del panel, un agente por MCP o los controles del panel (la tarjeta del recorrido)
ORIGENES = ("asistente", "mcp", "panel")
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


def para_pantalla(e: dict, doc: dict | None = None, guion: Any = None, ahora: datetime | None = None) -> dict:
    """Lo que recibe la pantalla: la versión y los campos y, si hay uno para ella (destino pantalla en off, sin cerrar),
    el recorrido con su edad (calculada aquí: el reloj del navegador puede estar corrido), el último control y el
    avance con su antigüedad."""
    out = {"v": e["v"], **{k: e[k] for k in CAMPOS}, "recorrido": None, "control_recorrido": None, "progreso": None}
    r = recorrido_de(doc, guion) if guion is not None else None
    ahora = ahora or _ahora()
    if r and r["destino"] == "pantalla_off" and not r["cerrado"]:
        creado = _aware(r.get("creado")) or ahora
        out["recorrido"] = {**{k: r[k] for k in ("id", "titulo", "escenas", "cierre")},
                            "edad_s": max(0, int((ahora - creado).total_seconds()))}
        c = (doc or {}).get("control_recorrido")
        if isinstance(c, dict) and c.get("rid") == r["id"] and c.get("accion") in rec.CONTROLES and \
                isinstance(c.get("n"), int):
            out["control_recorrido"] = {"rid": c["rid"], "accion": c["accion"], "n": c["n"]}
        pr = progreso_de(doc, r)
        if pr:
            out["progreso"] = {**{k: pr[k] for k in ("rid", "n", "de", "fase")},
                               "hace_s": max(0, int((ahora - (_aware(pr.get("en")) or ahora)).total_seconds()))}
    return out


# ───────────────────────────── El recorrido narrado ─────────────────────────────

def recorrido_de(doc: dict | None, guion: Any) -> dict | None:
    """El recorrido guardado, si sigue valiendo contra el guion vigente (`recorrido.validar`) y tiene destino; si no
    (el guion cambió, un texto ya no pasa las reglas, alguien lo tocó en la base), None."""
    r = (doc or {}).get("recorrido")
    if not isinstance(r, dict) or r.get("destino") not in rec.DESTINOS or not isinstance(r.get("cerrado"), bool):
        return None
    absoluto = {k: r.get(k) for k in ("id", "titulo", "escenas", "cierre")}
    if rec.validar(absoluto, guion):
        return None
    return {**absoluto, "destino": r["destino"], "cerrado": r["cerrado"], "creado": r.get("creado")}


def progreso_de(doc: dict | None, r: dict | None) -> dict | None:
    """El último avance guardado, si es del recorrido `r`."""
    pr = (doc or {}).get("progreso")
    if not r or not isinstance(pr, dict) or pr.get("rid") != r["id"]:
        return None
    return pr


def escena_actual(doc: dict | None, r: dict) -> int:
    """El número de la escena que la sala está viendo: la del último avance o, sin avance, la última (la base)."""
    pr = progreso_de(doc, r)
    n = pr.get("n") if pr else None
    return n if isinstance(n, int) and 1 <= n <= len(r["escenas"]) else len(r["escenas"])


def guardar_recorrido(db: Database, uid: int, absoluto: dict, destino: str, por: str) -> dict:
    """Guarda un recorrido nuevo (reemplaza al anterior), sin control ni avance, con la base en su última escena y sin
    explicación. Sube la versión."""
    if destino not in rec.DESTINOS or por not in ORIGENES:
        raise ValueError("pantalla.guardar_recorrido")
    base = rec.estado_de_escena(absoluto["escenas"][-1])
    return db.pantallas.find_one_and_update(
        {"_id": uid}, {"$set": {**base, "recorrido": {**absoluto, "destino": destino, "creado": _ahora(),
                                                       "cerrado": False},
                               "control_recorrido": None, "progreso": None, "actualizada": _ahora(), "por": por},
                       "$inc": {"v": 1}}, upsert=True, return_document=ReturnDocument.AFTER)


def colapsar(db: Database, uid: int, guion: Any, por: str = "asistente") -> dict | None:
    """Si hay un recorrido sin cerrar, lo cierra y deja como base la escena que la sala está viendo (la del último avance
    o, sin avance, la última), sin explicación: así la orden que lo interrumpe parte de lo que se ve. Devuelve el
    documento nuevo, o None si no había nada que cerrar."""
    doc = leer(db, uid)
    r = recorrido_de(doc, guion)
    if not r or r["cerrado"]:
        return None
    base = rec.estado_de_escena(r["escenas"][escena_actual(doc, r) - 1])
    return db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": r["id"]},
        {"$set": {**base, "recorrido.cerrado": True, "actualizada": _ahora(), "por": por}, "$inc": {"v": 1}},
        return_document=ReturnDocument.AFTER)


def guardar_progreso(db: Database, uid: int, p: dict) -> bool:
    """El avance que manda la página que reproduce (ya con su forma validada por la API): solo si es del recorrido
    guardado y sin cerrar, sin subir la versión (la pantalla no tiene nada nuevo que aplicar). Los avisos se juntan, sin
    repetirse, hasta 8. Devuelve False si el recorrido no es ese."""
    doc = db.pantallas.find_one({"_id": uid}, {"recorrido": 1, "progreso": 1})
    r = (doc or {}).get("recorrido")
    if not isinstance(r, dict) or r.get("id") != p["rid"] or r.get("cerrado") is not False or \
            p["n"] > len(r.get("escenas") or []) or p["de"] != len(r.get("escenas") or []):
        return False
    previos = [a for a in ((doc.get("progreso") or {}).get("avisos") or []) if (doc.get("progreso") or {}).get("rid") == p["rid"]]
    if p.get("aviso"):
        previos = [a for a in previos if a != {"n": p["n"], "tipo": p["aviso"]}] + [{"n": p["n"], "tipo": p["aviso"]}]
    pr = {k: p[k] for k in ("rid", "n", "de", "fase", "frase", "voz") if k in p}
    if p.get("motivo"):
        pr["motivo"] = p["motivo"]
    db.pantallas.update_one({"_id": uid, "recorrido.id": p["rid"]},
                            {"$set": {"progreso": {**pr, "avisos": previos[-8:], "en": _ahora()}}})
    return True


def controlar(db: Database, uid: int, guion: Any, accion: str, por: str, rid: str | None = None) -> dict:
    """Un control del recorrido (`recorrido.CONTROLES`): queda con su número (la pantalla aplica cada uno una sola vez)
    y sube la versión. «detener» además lo colapsa; «reproducir» lo vuelve a empezar con un id nuevo (también uno ya
    cerrado). Devuelve {"recorrido", "doc"}; ValueError «sin_recorrido» si no hay uno (o `rid` no es el suyo)."""
    if accion not in rec.CONTROLES or por not in ORIGENES:
        raise ValueError("pantalla.controlar")
    doc = leer(db, uid)
    r = recorrido_de(doc, guion)
    if not r or (rid is not None and r["id"] != rid) or (r["cerrado"] and accion != "reproducir"):
        raise ValueError("sin_recorrido")
    if accion == "reproducir":
        nuevo = {**{k: r[k] for k in ("titulo", "escenas", "cierre")}, "id": secrets.token_hex(6)}
        doc = guardar_recorrido(db, uid, nuevo, r["destino"], por)
        return {"recorrido": recorrido_de(doc, guion), "doc": doc}
    n = ((doc or {}).get("control_recorrido") or {}).get("n")
    n = n + 1 if isinstance(n, int) and not isinstance(n, bool) else 1
    doc = db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": r["id"]},
        {"$set": {"control_recorrido": {"accion": accion, "n": n, "rid": r["id"]}, "actualizada": _ahora(), "por": por},
         "$inc": {"v": 1}}, return_document=ReturnDocument.AFTER)
    if accion == "detener":
        doc = colapsar(db, uid, guion, por) or doc
    return {"recorrido": recorrido_de(doc, guion), "doc": doc}


def resumen_recorrido(doc: dict | None, guion: Any, ahora: datetime | None = None) -> dict | None:
    """Dónde va el recorrido para el modelo (`estado`, el contexto del panel): None si no hay uno o si está cerrado
    desde hace más de 2 minutos."""
    r = recorrido_de(doc, guion)
    if not r:
        return None
    pr = progreso_de(doc, r) or {}
    ahora = ahora or _ahora()
    en = _aware(pr.get("en"))
    if r["cerrado"] and (not en or ahora - en > timedelta(minutes=2)):
        return None
    n = escena_actual(doc, r)
    esc = r["escenas"][n - 1]
    fase = pr.get("fase") or "sin_avance"
    if r["cerrado"] and fase not in rec.TERMINALES:
        fase = "detenido"   # lo cerró otra orden o un control: el último avance quedó a medias
    return {"id": r["id"], "titulo": r["titulo"], "destino": r["destino"], "cerrado": r["cerrado"], "escena": n,
            "de": len(r["escenas"]), "fase": fase,
            "motivo": pr.get("motivo"), "voz": pr.get("voz"), "narracion_en_curso": " ".join(esc["frases"]),
            "avisos": pr.get("avisos") or [],
            "hace_s": max(0, int((ahora - en).total_seconds())) if en else None}


FASE = {"preparando": "preparando la imagen", "narrando": "narrando", "sosteniendo": "mirando", "cierre": "en el cierre",
        "pausa": "en pausa", "fin": "terminado", "detenido": "detenido", "error": "detenido por un error",
        "sin_avance": "sin avance todavía"}
DONDE = {"vista": "en la pestaña o el proyector", "pantalla_off": "en la pantalla en off"}
AVISO = {"atlas": "el modelo del atlas no cargó", "resaltar": "no encontró lo que resaltar",
         "asiento": "la imagen tardó en asentarse", "voz": "la voz no pudo hablar"}


def describir_recorrido(x: dict | None) -> str:
    """«Recorrido «La torre del hospital» en la pantalla en off: escena 3 de 6, narrando; voz: activa; avisos: escena 5,
    el modelo del atlas no cargó» (`resumen_recorrido`), o «»."""
    if not x:
        return ""
    t = f"Recorrido «{x['titulo']}» {DONDE[x['destino']]}: escena {x['escena']} de {x['de']}, {FASE.get(x['fase'], x['fase'])}"
    if x.get("motivo") == "mensaje" and x["fase"] == "pausa":
        t += " porque la persona escribió"
    if x.get("voz"):
        t += f"; voz: {x['voz'].replace('_', ' ')}"
    if x["avisos"]:
        t += "; avisos: " + ", ".join(f"escena {a['n']}, {AVISO.get(a['tipo'], a['tipo'])}" for a in x["avisos"][:4])
    return t


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
