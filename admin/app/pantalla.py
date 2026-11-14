"""La pantalla en off: la presentación de la propuesta que manejan los agentes (el asistente del panel y uno externo por
MCP) y que la vista Presentación en modo en off (/presentacion?off=1) sigue desde cualquier navegador: el proyector, un
televisor o la misma pestaña.

Cada usuario tiene una (`pantallas`, _id = uid; 0 el administrador): el capítulo y el paso, la explicación en pantalla,
lo que se ve (el panel de texto o «Solo 3D», el índice, las fichas), si llena la ventana y lo visual de la presentación
técnica (`VISUAL`: la cámara con su encuadre, su rumbo, su elevación, su acercamiento y a qué apunta, la obra enfocada,
hoy o con el proyecto, la ficha técnica abierta, la inmersión en un modelo del atlas, las piezas de la maqueta que se
muestran, se ocultan o se aíslan, las partes que se les quitan y el tema). Al cambiar de paso lo visual vuelve a lo del
paso, salvo el tema. Y dos acciones que NO son estado (`ACCIONES`): `mover` (el viaje de la cámara que pidió la última
orden `visual`) y `animar` (repetir la animación del paso); la pantalla las hace una vez y cualquier otra orden, un
cambio de paso o el cierre de un recorrido las deja en nada. Solo la cambian las órdenes de
un agente: lo que se toca a mano en la vista del panel no la mueve. La versión `v` sube con cada cambio; la pantalla
pregunta cada poco por ella (`GET /api/pantalla?v=`) y aplica solo lo nuevo. Cada pregunta deja `visto`: así un agente
sabe si hay una pantalla abierta (`conectada`).

Y el recorrido narrado (`app/recorrido.py`): el último que armó un agente, con su destino (la vista de la pestaña o
el proyector, o la pantalla en off: donde suena, en un solo lugar), el último control que le mandaron (`control_recorrido`,
que la pantalla aplica una sola vez por número) y el avance que manda la página que lo reproduce (`progreso`, sin subir
la versión). Mientras un recorrido no está cerrado, la base guardada (capítulo, paso y lo visual) es su última escena (la
que queda al terminar), pero lo que la sala ve es la escena en curso (`a_la_vista`): de esa parten el contexto del
asistente, el estado y las órdenes. Se cierra al terminar (un avance final: «fin», «error» o «detenido») o cuando otra
orden lo «colapsa» (`colapsar`), y en los dos casos la base pasa a ser la escena donde iba.

No guarda datos de personas: el guion de la propuesta es público y todo texto para la pantalla pasa antes por las reglas
de lo que se proyecta (`app/proyectable.py`): sin «@», números de 7 o más dígitos ni costos."""
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
# (las mismas claves, en el mismo orden, en `VISUAL` de app/recorrido.py, de mando.js y del puente: una prueba las
# compara. Las listas de VISUAL_INICIAL no se tocan: `visual_inicial()` da una copia con las suyas)
VISUAL_INICIAL = {"enfoque": None, "camara": "paso", "rumbo": None, "elevacion": None, "zoom": None, "mirar": None,
                  "girar": False, "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": [],
                  "ocultar": [], "aislar": None, "sin": []}
VISUAL = (*VISUAL_INICIAL, "tema")
CAMARAS = ("paso", "aerea", "oblicua", "rasante", "cerca", "lejos")
# Lo que no es estado: el movimiento de la cámara y la animación del paso que pidió la última orden `visual`
ACCIONES_INICIALES = {"mover": None, "animar": False}
ACCIONES = tuple(ACCIONES_INICIALES)
CAMPOS = ("capitulo", "paso", "explicacion", "panel", "indice", "fichas", "completa", "orden_completa", *VISUAL,
          *ACCIONES)
# Una pantalla pregunta cada 1,5 s (vistas/presentacion.js): sin preguntas en este tiempo, se da por cerrada. Holgado: un
# navegador espacia los relojes de una pestaña que no está a la vista
VIVA_S = 10
# Quién la cambió: el asistente del panel, un agente por MCP o los controles del panel (la tarjeta del recorrido)
ORIGENES = ("asistente", "mcp", "panel")
# Los «detenido» que no cierran el recorrido: el traspaso de la pestaña al proyector (sigue allá, con el mismo id) y el
# reemplazo (la página empezó otro: si es el mismo id, es ese el que sigue)
NO_CIERRAN = ("proyector", "reemplazo")
# Cuánto dice el contexto que un recorrido terminó (o se cerró), y cuándo se da por abandonado uno que nunca terminó: un
# recorrido dura a lo sumo 5 minutos, pero en pausa no llegan avances y una ronda de preguntas puede ser larga
MOSTRAR_TERMINADO = timedelta(minutes=2)
ABANDONADO = timedelta(minutes=30)
_ID_PIEZA = re.compile(r"[a-z0-9_]{1,40}")   # un componente o una inmersión (`ID_PASO` del guion)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(t: Any) -> datetime | None:
    if not isinstance(t, datetime):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def visual_inicial() -> dict:
    """Lo visual de un paso recién abierto (sin el tema, que no vuelve), con sus listas propias."""
    return rec.copia_visual(VISUAL_INICIAL)


def inicial(guion: Any) -> dict:
    """La pantalla antes de la primera orden: la portada, con el panel de texto y sin llenar la ventana."""
    return {"capitulo": guion.capitulos[0]["id"], "paso": 1, "explicacion": None, "panel": True, "indice": False,
            "fichas": False, "completa": False, "orden_completa": 0, **visual_inicial(), "tema": None,
            **ACCIONES_INICIALES}


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
        e.update(capitulo=base["capitulo"], paso=1, explicacion=None, **visual_inicial(), **ACCIONES_INICIALES)
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


def _entero(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _visual_valido(e: dict, guion: Any) -> None:
    """Lo visual guardado, con los valores que admite la presentación: lo que no cumple (o un componente o una pieza de
    la maqueta que ya no está en el capítulo, una inmersión que ya no está en el catálogo, si el guion cambió) vuelve a
    lo del paso; de una lista (mostrar, ocultar, sin) solo se va lo que no vale. Y las dos acciones, con su forma."""
    ci = guion.por_id(e["capitulo"])
    ids = {x["id"] for x in guion.capitulos[ci].get("componentes") or []} if ci is not None else set()
    lugar = {x["id"] for x in guion.capitulos[ci].get("componentes") or [] if x.get("enfoque")} if ci is not None else set()
    piezas = {x["id"]: {p["id"] for p in x["partes"]} for x in guion.piezas(ci)} if ci is not None else {}
    inm = {i["id"] for i in getattr(guion, "inmersiones", ()) or ()} | {"maqueta"}
    for k in rec.LISTAS:
        vale = (lambda x: _id_pieza(x) and x in piezas) if k != "sin" else \
            (lambda x: isinstance(x, str) and bool(rec.ID_PARTE.fullmatch(x))
             and x.split(".")[1] in piezas.get(x.split(".")[0], ()))
        e[k] = list(dict.fromkeys(x for x in e[k] if vale(x)))[:rec.MAX_LISTA] if isinstance(e[k], list) else []
    buenos = {"enfoque": e["enfoque"] is None or (_id_pieza(e["enfoque"]) and e["enfoque"] in lugar),
              "detalle": e["detalle"] is None or (_id_pieza(e["detalle"]) and e["detalle"] in ids),
              "inmersion": e["inmersion"] is None or (_id_pieza(e["inmersion"]) and e["inmersion"] in inm),
              "camara": e["camara"] in CAMARAS,
              "rumbo": e["rumbo"] is None or _entero(e["rumbo"], 0, 359),
              "elevacion": e["elevacion"] is None or _entero(e["elevacion"], *rec.ELEVACION),
              "zoom": e["zoom"] is None or rec.zoom_valido(e["zoom"]),
              "mirar": e["mirar"] is None or (_id_pieza(e["mirar"]) and (e["mirar"] in piezas or e["mirar"] in lugar)),
              "aislar": e["aislar"] is None or (_id_pieza(e["aislar"]) and e["aislar"] in piezas),
              "girar": isinstance(e["girar"], bool), "comparar": e["comparar"] in ("hoy", "proyecto")}
    for k, bien in buenos.items():
        if not bien:
            e[k] = VISUAL_INICIAL[k]
    if e["tema"] not in (None, "claro", "oscuro"):
        e["tema"] = None
    if e["mover"] is not None and not rec.mover_valido(e["mover"]):
        e["mover"] = None
    e["animar"] = e["animar"] is True


def conectada(doc: dict | None, ahora: datetime | None = None) -> bool:
    """¿Hay una pantalla en off abierta? (preguntó por su estado hace menos de VIVA_S)."""
    visto = _aware((doc or {}).get("visto"))
    return visto is not None and (ahora or _ahora()) - visto < timedelta(seconds=VIVA_S)


def para_pantalla(e: dict, doc: dict | None = None, guion: Any = None, ahora: datetime | None = None) -> dict:
    """Lo que recibe la pantalla: la versión y los campos y, si hay uno para ella (destino pantalla en off, sin cerrar),
    el recorrido con su edad (calculada aquí: el reloj del navegador puede estar corrido), el último control y el
    avance con su antigüedad. Con uno que suena en la pestaña o el proyector (destino vista), los campos son los de su
    escena en curso: una pantalla en off que se abre a mitad muestra lo que la sala ve, no la última escena."""
    r = recorrido_de(doc, guion) if guion is not None else None
    if r and r["destino"] == "vista" and not r["cerrado"]:
        e = estado(a_la_vista(doc, guion, r), guion)
    out = {"v": e["v"], **{k: e[k] for k in CAMPOS}, "recorrido": None, "control_recorrido": None, "progreso": None}
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
    # (`al_dia`: uno guardado antes del plan guiado, con lo que le falta en lo del paso)
    absoluto = rec.al_dia({k: r.get(k) for k in ("id", "titulo", "escenas", "cierre")})
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


def base_en_curso(doc: dict | None, r: dict) -> dict:
    """Los campos de la pantalla en la escena del recorrido `r` que la sala está viendo (`escena_actual`)."""
    return rec.estado_de_escena(r["escenas"][escena_actual(doc, r) - 1])


def a_la_vista(doc: dict | None, guion: Any, r: dict | None = None) -> dict | None:
    """El documento con la base que la sala está viendo: con un recorrido sin cerrar (`r`, o el guardado), la de su
    escena en curso (la base guardada es la última escena, la que queda al terminar); si no, el mismo. Solo en memoria:
    es lo que dicen el contexto del asistente y el estado, y de donde parte una orden (`colapsar` la escribe al cerrarlo)."""
    r = r or recorrido_de(doc, guion)
    if not doc or not r or r["cerrado"]:
        return doc
    return {**doc, **base_en_curso(doc, r)}


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


def colapsar(db: Database, uid: int, guion: Any, por: str = "asistente", rid: str | None = None) -> dict | None:
    """Si hay un recorrido sin cerrar (con `rid`, solo si es ese), lo cierra y deja como base la escena que la sala está
    viendo (la del último avance o, sin avance, la última), sin explicación: así la orden que lo interrumpe parte de lo
    que se ve. Devuelve el documento nuevo, o None si no había nada que cerrar. Con `rid`, uno que llegó entretanto (otro
    agente armó otro recorrido) no se cierra por una orden que iba para el anterior; y la escritura solo vale sobre uno
    todavía abierto."""
    doc = leer(db, uid)
    r = recorrido_de(doc, guion)
    if not r or r["cerrado"] or (rid is not None and r["id"] != rid):
        return None
    return db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": r["id"], "recorrido.cerrado": False},
        {"$set": {**base_en_curso(doc, r), "recorrido.cerrado": True, "actualizada": _ahora(), "por": por},
         "$inc": {"v": 1}},
        return_document=ReturnDocument.AFTER)


def guardar_progreso(db: Database, uid: int, p: dict) -> bool:
    """El avance que manda la página que reproduce (ya con su forma validada por la API): solo si es del recorrido
    guardado y sin cerrar, sin subir la versión (la pantalla no tiene nada nuevo que aplicar). Los avisos se juntan, sin
    repetirse, hasta 8. Un avance final (`recorrido.TERMINALES`) además lo cierra, con la base en la escena donde quedó,
    y sube la versión: así la pantalla en off que lo narró recibe lo que muestra, el contexto lo da por terminado y un
    control o una orden posterior no lo toma por vivo. Salvo un «detenido» de NO_CIERRAN. Devuelve False si el recorrido
    no es ese o ya está cerrado (la API responde 409 y la página que todavía lo reproduce lo detiene)."""
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
    cambios: dict = {"$set": {"progreso": {**pr, "avisos": previos[-8:], "en": _ahora()}}}
    if p["fase"] in rec.TERMINALES and not (p["fase"] == "detenido" and p.get("motivo") in NO_CIERRAN):
        try:
            base = rec.estado_de_escena(rec.al_dia(r)["escenas"][p["n"] - 1])
        except (KeyError, TypeError):   # alguien la tocó en la base: se cierra igual (`estado` corrige lo que no vale)
            base = {}
        cambios["$set"].update({**base, "recorrido.cerrado": True, "actualizada": _ahora()})
        cambios["$inc"] = {"v": 1}
    # Sobre uno todavía abierto: si entretanto lo cerró otra orden (o llegó otro), el avance ya no es de nadie
    return db.pantallas.find_one_and_update({"_id": uid, "recorrido.id": p["rid"], "recorrido.cerrado": False},
                                            cambios) is not None


def controlar(db: Database, uid: int, guion: Any, accion: str, por: str, rid: str | None = None) -> dict:
    """Un control del recorrido (`recorrido.CONTROLES`): queda con su número (la pantalla aplica cada uno una sola vez)
    y sube la versión. «detener» además lo colapsa; «reproducir» lo vuelve a empezar con un id nuevo (también uno ya
    cerrado, si es el último: «Volver a reproducir» de la tarjeta pasa por aquí y sigue al id nuevo). Devuelve
    {"recorrido", "doc"}; ValueError «sin_recorrido» si no hay uno (o `rid` no es el suyo, o entre la lectura y la
    escritura llegó otro)."""
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
        {"_id": uid, "recorrido.id": r["id"], "recorrido.cerrado": False},
        {"$set": {"control_recorrido": {"accion": accion, "n": n, "rid": r["id"], "en": _ahora()},
                  "actualizada": _ahora(), "por": por},
         "$inc": {"v": 1}}, return_document=ReturnDocument.AFTER)
    if doc is None:   # entre la lectura y la escritura llegó otro recorrido (o este se cerró): el control no era para él
        raise ValueError("sin_recorrido")
    if accion == "detener":
        doc = colapsar(db, uid, guion, por, rid=r["id"]) or doc
    return {"recorrido": recorrido_de(doc, guion), "doc": doc}


def resumen_recorrido(doc: dict | None, guion: Any, ahora: datetime | None = None) -> dict | None:
    """Dónde va el recorrido para el modelo (`estado`, el contexto del panel): None si no hay uno, si terminó o se cerró
    hace más de MOSTRAR_TERMINADO o si quedó abandonado (sin avance ni control en ABANDONADO: la página que lo
    reproducía se cerró, o nunca sonó). Así el contexto no le dice al modelo, días después, que siga con uno que nadie oye."""
    r = recorrido_de(doc, guion)
    if not r:
        return None
    pr = progreso_de(doc, r) or {}
    ahora = ahora or _ahora()
    en = _aware(pr.get("en"))
    final = r["cerrado"] or pr.get("fase") in rec.TERMINALES
    if final and (not en or ahora - en > MOSTRAR_TERMINADO):
        return None
    # Lo último que pasó: un avance, la creación o un control de ESTE recorrido (tras una pausa larga, «continuar» lo
    # revive antes de que llegue el avance del que lo reproduce). Otra escritura de la pantalla (la pantalla completa)
    # no cuenta: reviviría para el modelo uno que nadie oye. En pausa con la pantalla en off abierta no hay abandono:
    # la sala lo tiene delante, aunque en pausa no lleguen avances
    c = (doc or {}).get("control_recorrido")
    control = _aware(c.get("en")) if isinstance(c, dict) and c.get("rid") == r["id"] else None
    vivo = max((t for t in (en, _aware(r.get("creado")), control) if t), default=ahora)
    en_pausa_viva = r["destino"] == "pantalla_off" and pr.get("fase") == "pausa" and conectada(doc, ahora)
    if not final and not en_pausa_viva and ahora - vivo > ABANDONADO:
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
         "asiento": "la imagen tardó en asentarse", "voz": "la voz no pudo hablar",
         "parcial": "parte de lo pedido no se pudo mostrar"}


def describir_recorrido(x: dict | None) -> str:
    """«Plan «La torre del hospital» en la pantalla en off: paso 3 de 6 del plan, narrando; voz: activa; avisos: paso 5,
    el modelo del atlas no cargó» (`resumen_recorrido`), o «». Para el modelo y la persona es un plan con pasos («del
    plan»: el paso del capítulo es otro y va en la línea de la presentación)."""
    if not x:
        return ""
    t = (f"Plan «{x['titulo']}» {DONDE[x['destino']]}: paso {x['escena']} de {x['de']} del plan, "
         f"{FASE.get(x['fase'], x['fase'])}")
    if x.get("motivo") == "mensaje" and x["fase"] == "pausa":
        t += " porque la persona escribió"
    if x.get("voz"):
        t += f"; voz: {x['voz'].replace('_', ' ')}"
    if x["avisos"]:
        t += "; avisos: " + ", ".join(f"paso {a['n']}, {AVISO.get(a['tipo'], a['tipo'])}" for a in x["avisos"][:4])
    if isinstance(x.get("hace_s"), int) and x["hace_s"] >= 60:   # en pausa es normal; si no, quizá ya nadie lo oye
        t += f"; el último avance llegó hace {x['hace_s'] // 60} min"
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
    piezas = {x["id"]: x for x in guion.piezas(ci)}
    nombre = lambda i: piezas[i]["nombre"] if i in piezas else nombres.get(i, i)   # noqa: E731

    def parte(i: str) -> str:
        pieza, _, pid = i.partition(".")
        suya = next((p["nombre"] for p in (piezas.get(pieza) or {}).get("partes", []) if p["id"] == pid), pid)
        return f"{suya} de «{nombre(pieza)}» ({i})"
    if e.get("aislar"):
        partes.append(f"solo se ve «{nombre(e['aislar'])}» ({e['aislar']}), el resto apagado o en gris")
    if e.get("mostrar"):
        partes.append("además muestra " + ", ".join(f"«{nombre(i)}» ({i})" for i in e["mostrar"]))
    if e.get("ocultar"):
        partes.append("oculta " + ", ".join(f"«{nombre(i)}» ({i})" for i in e["ocultar"]))
    if e.get("sin"):
        partes.append("sin " + ", ".join(parte(i) for i in e["sin"]))
    camara = [x for x in (f"vista {e['camara']}" if e.get("camara") not in (None, "paso") else "",
                          f"mirando desde el rumbo {e['rumbo']}°" if e.get("rumbo") is not None else "",
                          f"a {e['elevacion']}° sobre el horizonte" if e.get("elevacion") is not None else "",
                          f"zoom {e['zoom']:g}" if e.get("zoom") is not None else "",
                          f"apunta a «{nombre(e['mirar'])}» ({e['mirar']})" if e.get("mirar") else "",
                          "girando" if e.get("girar") else "") if x]
    if camara:
        partes.append("cámara: " + ", ".join(camara))
    if e.get("tema"):
        partes.append(f"tema {e['tema']}")
    return "; ".join(partes)
