"""La pantalla en off: la presentación de la propuesta que manejan los agentes (el asistente del panel y uno externo por
MCP) y que la vista Presentación en modo en off (/presentacion?off=1) sigue desde cualquier navegador: el proyector, un
televisor o la misma pestaña.

Cada usuario tiene una (`pantallas`, _id = uid; 0 el administrador): el capítulo y el paso, la explicación en pantalla,
lo que se ve (el panel de texto o «Solo 3D», el índice, las fichas), si llena la ventana y lo visual de la presentación
técnica (`VISUAL`: la cámara con su encuadre, su rumbo, su elevación, su acercamiento y a qué apunta, la obra enfocada,
hoy o con el proyecto, la ficha técnica abierta, la inmersión en un modelo del atlas, las piezas de la maqueta que se
muestran, se ocultan o se aíslan, las partes que se les quitan y el tema). Al cambiar de paso lo visual vuelve a lo del
paso, salvo el tema. Y tres acciones que NO son estado (`ACCIONES`) y pidió la última orden `visual`: `mover` (el viaje
de la cámara), `animar` (repetir la animación del paso) y `simular` (los controles de la simulación del modelo a la vista:
el del atlas o, sin uno, la maqueta 3D; `recorrido.MAX_SIMULAR` a lo sumo); la pantalla las hace una vez, con la versión
que las trae. La API anota
la última versión que le entregó (`entregada_v`, `entregar`): ya recibidas, cualquier otra orden, un cambio de paso o el
cierre de un recorrido las deja en nada; mientras la pantalla abierta no las recibe, la orden siguiente no las pisa
(`guardar_orden`): se juntan con las suyas (dos órdenes seguidas, o en paralelo, de un agente se hacen las dos), salvo
que cambie de paso. Solo la cambian las órdenes de un agente: lo que se toca a mano en la vista del panel no la mueve.
La versión `v` sube con cada cambio; la pantalla pregunta cada poco por ella (`GET /api/pantalla?v=`) y aplica solo lo
nuevo. Cada pregunta deja `visto`: así un agente sabe si hay una pantalla abierta (`conectada`).

Y el recorrido narrado (`app/recorrido.py`): el último que armó un agente, con su destino (la vista de la pestaña o
el proyector, o la pantalla en off: donde suena, en un solo lugar), el último control que le mandaron (`control_recorrido`,
que la pantalla aplica una sola vez por número) y el avance que manda la página que lo reproduce (`progreso`, sin subir
la versión). Mientras un recorrido no está cerrado, la base guardada (capítulo, paso y lo visual) es su última escena (la
que queda al terminar), pero lo que la sala ve es la escena en curso (`a_la_vista`): de esa parten el contexto del
asistente, el estado y las órdenes. Se cierra al terminar (un avance final: «fin», «error» o «detenido») o cuando otra
orden lo «colapsa» (`colapsar`), y en los dos casos la base pasa a ser la escena donde iba.

Y la presentación automática (`app/automatica.py`): con ella encendida (`auto`: si está activa, el capítulo y el paso
por donde va, cuál es su plan y cuántas vueltas lleva), la pantalla en off recorre sola toda la presentación, un plan
por capítulo con una frase muy resumida por paso, que arma el servidor sin modelo. La pantalla los pide uno tras otro
(`siguiente_auto`) cuando no suena ninguno. Un plan de un agente la interrumpe (suelta el suyo: `auto.rid` queda en
None y la posición se queda) y, cuando termina, sigue en el paso que se estaba diciendo. Se apaga con `detener_auto`,
con el control «detener» sobre su plan o cuando alguien lo detiene a propósito en la pantalla (una tecla, un botón:
salir de la vista en off no la apaga). Cuando arma su plan guarda el último plan que no era suyo
(`recorrido_previo`): «Volver a reproducir» de esa tarjeta sigue sirviendo.

No guarda datos de personas: el guion de la propuesta es público y todo texto para la pantalla pasa antes por las reglas
de lo que se proyecta (`app/proyectable.py`): sin «@», números de 7 o más dígitos ni costos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import re
import secrets

from pymongo import ReturnDocument
from pymongo.database import Database

from . import automatica
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
# Lo que no es estado: el movimiento de la cámara, la animación del paso y la simulación del modelo del atlas que pidió
# la última orden `visual`
ACCIONES_INICIALES = {"mover": None, "animar": False, "simular": None}
ACCIONES = tuple(ACCIONES_INICIALES)
CAMPOS = ("capitulo", "paso", "explicacion", "panel", "indice", "fichas", "completa", "orden_completa", *VISUAL,
          *ACCIONES)
# Una pantalla pregunta cada 1,5 s (vistas/presentacion.js): sin preguntas en este tiempo, se da por cerrada. Holgado: un
# navegador espacia los relojes de una pestaña que no está a la vista
VIVA_S = 10
# Quién la cambió: el asistente del panel, un agente por MCP, los controles del panel (la tarjeta del recorrido, el
# botón «Automática») o la presentación automática (el plan que arma el servidor: solo `siguiente_auto` lo guarda)
ORIGENES = ("asistente", "mcp", "panel", "auto")
# Los «detenido» que no cierran el recorrido: el traspaso de la pestaña al proyector (sigue allá, con el mismo id) y el
# reemplazo (la página empezó otro: si es el mismo id, es ese el que sigue)
NO_CIERRAN = ("proyector", "reemplazo")
# Los «detenido» del plan automático que además apagan la presentación automática: los que alguien hizo a propósito en
# esa pantalla (una tecla, un botón; `motivo` de reproductor.js). Cualquier otro (una vista que se desmonta,
# `otra_orden`) solo suelta el plan: sigue encendida y con su posición
DETIENEN_AUTO = ("tecla", "boton")
# Cuánto dice el contexto que un recorrido terminó (o se cerró), y cuándo se da por abandonado uno que nunca terminó: un
# recorrido dura a lo sumo 5 minutos, pero en pausa no llegan avances y una ronda de preguntas puede ser larga
MOSTRAR_TERMINADO = timedelta(minutes=2)
ABANDONADO = timedelta(minutes=30)
# La presentación automática: cuánto puede pasar sin noticias de su plan (un avance, o recién armado) antes de darlo por
# caído y armar otro (la pantalla se recargó o se cerró a mitad; un plan vivo avisa cada frase), y cuántos planes
# seguidos pueden terminar en error antes de que se apague sola (la presentación no responde)
SIN_NOTICIAS_AUTO_S = 30
MAX_FALLAS_AUTO = 3
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
    lo del paso; de una lista (mostrar, ocultar, sin) solo se va lo que no vale. Y las tres acciones, con su forma
    (`simular`, contra los controles del modelo que queda a la vista: el del atlas o, sin uno, la maqueta 3D en ese
    capítulo; si alguno no vale, no va ninguno)."""
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
    controles = getattr(guion, "controles", lambda *_: [])
    modelo = rec.simulable_en(e["capitulo"], e["paso"], e["inmersion"], guion)
    if e["simular"] is not None and rec.simular_problemas(e["simular"], controles(modelo, e["capitulo"])):
        e["simular"] = None


def conectada(doc: dict | None, ahora: datetime | None = None) -> bool:
    """¿Hay una pantalla en off abierta? (preguntó por su estado hace menos de VIVA_S)."""
    visto = _aware((doc or {}).get("visto"))
    return visto is not None and (ahora or _ahora()) - visto < timedelta(seconds=VIVA_S)


def para_pantalla(e: dict, doc: dict | None = None, guion: Any = None, ahora: datetime | None = None) -> dict:
    """Lo que recibe la pantalla: la versión y los campos y, si hay uno para ella (destino pantalla en off, sin cerrar),
    el recorrido con su edad (calculada aquí: el reloj del navegador puede estar corrido), el último control y el
    avance con su antigüedad. Con uno que suena en la pestaña o el proyector (destino vista), los campos son los de su
    escena en curso: una pantalla en off que se abre a mitad muestra lo que la sala ve, no la última escena. Y `auto`: la
    presentación automática ({activa, capitulo, paso}, o None si nunca se encendió); su plan viaja con `auto: true`
    (la pantalla no espera para empezarlo y, cuando termina, pide el siguiente)."""
    r = recorrido_de(doc, guion) if guion is not None else None
    if r and r["destino"] == "vista" and not r["cerrado"]:
        e = estado(a_la_vista(doc, guion, r), guion)
    out = {"v": e["v"], **{k: e[k] for k in CAMPOS}, "recorrido": None, "control_recorrido": None, "progreso": None,
           "auto": auto_para_pantalla(doc, guion) if guion is not None else None}
    ahora = ahora or _ahora()
    if r and r["destino"] == "pantalla_off" and not r["cerrado"]:
        creado = _aware(r.get("creado")) or ahora
        out["recorrido"] = {**{k: r[k] for k in ("id", "titulo", "escenas", "cierre")},
                            "edad_s": max(0, int((ahora - creado).total_seconds())),
                            **({"auto": True} if r["auto"] else {}), **({"abierto": True} if r["abierto"] else {})}
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
    (el guion cambió, un texto ya no pasa las reglas, alguien lo tocó en la base), None. `auto`: lo armó la
    presentación automática (no tiene tarjeta en el chat ni es un plan del asistente). `externo`: lo escribió una
    aplicación externa por MCP (o es una copia de uno así: «reproducir»), con frases que no generó el sistema: la voz
    clonada no lo narra (`agente/voz.py`)."""
    r = (doc or {}).get("recorrido")
    if not isinstance(r, dict) or r.get("destino") not in rec.DESTINOS or not isinstance(r.get("cerrado"), bool):
        return None
    # (`al_dia`: uno guardado antes del plan guiado, con lo que le falta en lo del paso)
    absoluto = rec.al_dia({k: r.get(k) for k in ("id", "titulo", "escenas", "cierre")})
    if rec.validar(absoluto, guion):
        return None
    return {**absoluto, "destino": r["destino"], "cerrado": r["cerrado"], "creado": r.get("creado"),
            "auto": r.get("auto") is True, "externo": r.get("externo") is True,
            "en_flujo": r.get("en_flujo") is True, "abierto": r.get("abierto") is True}


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


def _poner_recorrido(absoluto: dict, destino: str, por: str, abierto: bool = False) -> dict:
    """Lo que se escribe al guardar un recorrido nuevo: sin control ni avance, con la base en su última escena y sin
    explicación. `externo`: lo escribió un agente por MCP, o es la copia de uno así (`controlar` «reproducir» la pasa
    con `externo`): la marca no se pierde aunque otro lo vuelva a reproducir. `abierto`: el plan en flujo que el panel
    todavía está escribiendo (`agente/redactor.py`): crece con `crecer_recorrido` y queda con `en_flujo` para siempre
    (su avance puede contar menos pasos de los guardados: el navegador recibe los nuevos un momento después)."""
    flujo = {"en_flujo": True, "abierto": True} if abierto else {}
    return {**rec.estado_de_escena(absoluto["escenas"][-1]),
            "recorrido": {**{k: absoluto[k] for k in ("id", "titulo", "escenas", "cierre")}, "destino": destino,
                          "creado": _ahora(), "cerrado": False, "auto": por == "auto",
                          "externo": por == "mcp" or absoluto.get("externo") is True, **flujo},
            "control_recorrido": None, "progreso": None, "actualizada": _ahora(), "por": por}


def guardar_recorrido(db: Database, uid: int, absoluto: dict, destino: str, por: str, abierto: bool = False) -> dict:
    """Guarda un recorrido nuevo de un agente o del panel (reemplaza al anterior), sin control ni avance, con la base
    en su última escena y sin explicación. Sube la versión. Si sonaba el plan de la presentación automática, lo suelta
    (`auto.rid` en None): la posición se queda y, cuando este termine, sigue desde ahí. (El plan automático lo guarda
    `siguiente_auto`.) `abierto`: un plan en flujo que se sigue escribiendo (`crecer_recorrido`)."""
    if destino not in rec.DESTINOS or por not in ORIGENES or por == "auto":
        raise ValueError("pantalla.guardar_recorrido")
    doc = db.pantallas.find_one_and_update(
        {"_id": uid}, {"$set": _poner_recorrido(absoluto, destino, por, abierto), "$inc": {"v": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    # (desde la escritura de arriba el plan automático ya no es el vigente, y `auto_de` no lo da por suyo: esto solo
    # deja `auto.rid` como es. Aparte y con filtro: una pantalla que nunca la encendió no gana un `auto` a medias)
    if isinstance(doc.get("auto"), dict) and doc["auto"].get("rid") is not None:
        doc = db.pantallas.find_one_and_update({"_id": uid, "auto.rid": doc["auto"]["rid"]}, {"$set": {"auto.rid": None}},
                                               return_document=ReturnDocument.AFTER) or doc
    return doc


def crecer_recorrido(db: Database, uid: int, absoluto: dict, abierto: bool) -> dict | None:
    """El plan en flujo `absoluto` (el mismo id, con los pasos que ya tenía y los nuevos, y su cierre) mientras el panel
    lo escribe (`agente/redactor.py`): solo sobre ese recorrido, todavía sin cerrar y en flujo. Sube la versión (la
    pantalla en off ve los pasos nuevos en su próxima pregunta) y deja la base en su última escena, como al guardarlo.
    Con `abierto` en False ya está entero. Devuelve el documento nuevo, o None si ya no es el vigente (la persona lo
    detuvo, otra orden lo cerró, llegó otro): entonces el panel deja de escribirlo."""
    return db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": absoluto["id"], "recorrido.cerrado": False, "recorrido.en_flujo": True},
        {"$set": {**rec.estado_de_escena(absoluto["escenas"][-1]), "recorrido.titulo": absoluto["titulo"],
                  "recorrido.escenas": absoluto["escenas"], "recorrido.cierre": absoluto["cierre"],
                  "recorrido.abierto": bool(abierto), "actualizada": _ahora()},
         "$inc": {"v": 1}},
        return_document=ReturnDocument.AFTER)


def colapsar(db: Database, uid: int, guion: Any, por: str = "asistente", rid: str | None = None) -> dict | None:
    """Si hay un recorrido sin cerrar (con `rid`, solo si es ese), lo cierra y deja como base la escena que la sala está
    viendo (la del último avance o, sin avance, la última), sin explicación: así la orden que lo interrumpe parte de lo
    que se ve. Devuelve el documento nuevo, o None si no había nada que cerrar. Con `rid`, uno que llegó entretanto (otro
    agente armó otro recorrido) no se cierra por una orden que iba para el anterior; y la escritura solo vale sobre uno
    todavía abierto. Si era el de la presentación automática, queda suelto (`auto.rid` en None): sigue encendida y con
    su posición, y la pantalla pedirá el siguiente desde ese paso."""
    doc = leer(db, uid)
    r = recorrido_de(doc, guion)
    if not r or r["cerrado"] or (rid is not None and r["id"] != rid):
        return None
    return db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": r["id"], "recorrido.cerrado": False},
        {"$set": {**base_en_curso(doc, r), "recorrido.cerrado": True, "actualizada": _ahora(), "por": por,
                  **({"auto.rid": None} if isinstance(doc.get("auto"), dict) else {})},
         "$inc": {"v": 1}},
        return_document=ReturnDocument.AFTER)


def guardar_progreso(db: Database, uid: int, p: dict, guion: Any = None) -> bool:
    """El avance que manda la página que reproduce (ya con su forma validada por la API): solo si es del recorrido
    guardado y sin cerrar, sin subir la versión (la pantalla no tiene nada nuevo que aplicar). Los avisos se juntan, sin
    repetirse, hasta 8. Un avance final (`recorrido.TERMINALES`) además lo cierra, con la base en la escena donde quedó,
    y sube la versión: así la pantalla en off que lo narró recibe lo que muestra, el contexto lo da por terminado y un
    control o una orden posterior no lo toma por vivo. Salvo un «detenido» de NO_CIERRAN. Devuelve False si el recorrido
    no es ese o ya está cerrado (la API responde 409 y la página que todavía lo reproduce lo detiene). Si es el plan de
    la presentación automática, además lleva su posición (`_auto_tras_avance`; con `guion`, ya en un paso que existe)."""
    doc = db.pantallas.find_one({"_id": uid}, {"recorrido": 1, "progreso": 1, "auto": 1})
    r = (doc or {}).get("recorrido")
    # (un plan en flujo crece en el servidor antes que en el navegador: su avance puede contar menos pasos)
    total = len(r.get("escenas") or []) if isinstance(r, dict) else 0
    if not isinstance(r, dict) or r.get("id") != p["rid"] or r.get("cerrado") is not False or p["n"] > total or \
            (p["de"] > total if r.get("en_flujo") is True else p["de"] != total):
        return False
    previos = [a for a in ((doc.get("progreso") or {}).get("avisos") or []) if (doc.get("progreso") or {}).get("rid") == p["rid"]]
    if p.get("aviso"):
        previos = [a for a in previos if a != {"n": p["n"], "tipo": p["aviso"]}] + [{"n": p["n"], "tipo": p["aviso"]}]
    pr = {k: p[k] for k in ("rid", "n", "de", "fase", "frase", "voz") if k in p}
    if p.get("motivo"):
        pr["motivo"] = p["motivo"]
    cambios: dict = {"$set": {"progreso": {**pr, "avisos": previos[-8:], "en": _ahora()}}}
    cierra = p["fase"] in rec.TERMINALES and not (p["fase"] == "detenido" and p.get("motivo") in NO_CIERRAN)
    a = doc.get("auto")
    if isinstance(a, dict) and a.get("activa") is True and a.get("rid") == p["rid"]:
        cambios["$set"].update(_auto_tras_avance(a, r, p, guion, cierra))
    if cierra:
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
    escritura llegó otro). Sobre el plan de la presentación automática: «detener» además la apaga (pausar, no) y
    «reproducir» lo vuelve a empezar como plan automático. Con la automática encendida, «reproducir» con el id del
    último plan que no era suyo (`recorrido_previo`: la automática lo reemplazó al seguir) lo vuelve a empezar con un
    id nuevo, como antes de que ella armara el suyo: la interrumpe y, cuando termine, ella sigue desde su paso."""
    if accion not in rec.CONTROLES or por not in ORIGENES:
        raise ValueError("pantalla.controlar")
    doc = leer(db, uid)
    r = recorrido_de(doc, guion)
    if not r or (rid is not None and r["id"] != rid) or (r["cerrado"] and accion != "reproducir"):
        previo = recorrido_previo(doc, guion) if accion == "reproducir" and rid is not None else None
        if previo and previo["id"] == rid:
            nuevo = {**{k: previo[k] for k in ("titulo", "escenas", "cierre")}, "id": secrets.token_hex(6),
                     "externo": previo["externo"]}
            doc = guardar_recorrido(db, uid, nuevo, previo["destino"], por)
            return {"recorrido": recorrido_de(doc, guion), "doc": doc}
        raise ValueError("sin_recorrido")
    a = auto_de(doc, guion)
    es_auto = bool(a and a["activa"] and a["rid"] == r["id"])
    if accion == "reproducir":
        nuevo = {**{k: r[k] for k in ("titulo", "escenas", "cierre")}, "id": secrets.token_hex(6),
                 "externo": r["externo"]}
        doc = (_guardar_plan_auto(db, uid, nuevo, a) if es_auto else None) or \
            guardar_recorrido(db, uid, nuevo, r["destino"], por)
        return {"recorrido": recorrido_de(doc, guion), "doc": doc}
    n = ((doc or {}).get("control_recorrido") or {}).get("n")
    n = n + 1 if isinstance(n, int) and not isinstance(n, bool) else 1
    doc = db.pantallas.find_one_and_update(
        {"_id": uid, "recorrido.id": r["id"], "recorrido.cerrado": False},
        {"$set": {"control_recorrido": {"accion": accion, "n": n, "rid": r["id"], "en": _ahora()},
                  "actualizada": _ahora(), "por": por,
                  **({"auto.activa": False, "auto.rid": None} if es_auto and accion == "detener" else {})},
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
    return {"id": r["id"], "titulo": r["titulo"], "destino": r["destino"], "cerrado": r["cerrado"], "auto": r["auto"],
            "escena": n, "de": len(r["escenas"]), "fase": fase,
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


# ───────────────────────────── La presentación automática ─────────────────────────────

def auto_de(doc: dict | None, guion: Any) -> dict | None:
    """El estado de la presentación automática: {activa, capitulo, paso, rid, vueltas, fallas}, o None si nunca se
    encendió. `paso` es el que se está narrando o el próximo a narrar (desde 1), siempre uno que existe en el guion
    vigente (`automatica.posicion`: un paso más allá del último es el primero del capítulo siguiente). `rid`, el id de
    su plan mientras suena: None si está apagada o si el recorrido guardado ya no es ese o está cerrado."""
    a = (doc or {}).get("auto")
    if not isinstance(a, dict) or not isinstance(a.get("activa"), bool):
        return None
    capitulo, paso, vuelta = automatica.posicion(guion, a.get("capitulo"), a.get("paso"))
    r = (doc or {}).get("recorrido")
    suyo = a["activa"] and isinstance(a.get("rid"), str) and isinstance(r, dict) and r.get("id") == a["rid"] and \
        r.get("cerrado") is False
    return {"activa": a["activa"], "capitulo": capitulo, "paso": paso, "rid": a["rid"] if suyo else None,
            "vueltas": (a["vueltas"] if _entero(a.get("vueltas"), 0, 10 ** 9) else 0) + vuelta,
            "fallas": a["fallas"] if _entero(a.get("fallas"), 0, MAX_FALLAS_AUTO) else 0}


def auto_para_pantalla(doc: dict | None, guion: Any) -> dict | None:
    """`auto` de `GET /api/pantalla`: {activa, capitulo, paso}, o None si nunca se encendió."""
    a = auto_de(doc, guion)
    return a and {k: a[k] for k in ("activa", "capitulo", "paso")}


def auto_para_persona(doc: dict | None, guion: Any) -> dict:
    """La presentación automática como se le dice a la persona (la respuesta de `POST /api/pantalla/auto`, la acción
    del chat): {activa, capitulo, nombre, paso, de}. Si nunca se encendió: apagada, en el primer paso de la presentación."""
    a = auto_de(doc, guion) or {"activa": False, "capitulo": guion.capitulos[0]["id"], "paso": 1}
    c = guion.capitulos[guion.por_id(a["capitulo"])]
    return {"activa": a["activa"], "capitulo": c["id"], "nombre": c["nombre"], "paso": a["paso"], "de": len(c["pasos"])}


def plan_sonando(doc: dict | None, guion: Any, ahora: datetime | None = None) -> bool:
    """¿Suena un plan? Uno sin cerrar cuyo último avance no es final. En pausa suena mientras no esté abandonado
    (`resumen_recorrido`). Y uno del que no hay noticias (un avance, un control o recién guardado) no suena: la página
    que lo narraba se cerró o se recargó, o nunca empezó. El plazo es `rec.VIGENCIA_RECORRIDO_S` (lo que una pantalla
    espera para narrar uno nuevo) y, para el de la presentación automática, SIN_NOTICIAS_AUTO_S (lo pide la misma
    pantalla que tendría que estar narrándolo)."""
    r = recorrido_de(doc, guion)
    if not r or r["cerrado"]:
        return False
    pr = progreso_de(doc, r) or {}
    ahora = ahora or _ahora()
    if pr.get("fase") == "pausa":
        return resumen_recorrido(doc, guion, ahora) is not None
    c = (doc or {}).get("control_recorrido")
    control = _aware(c.get("en")) if isinstance(c, dict) and c.get("rid") == r["id"] else None
    vivo = max((t for t in (_aware(pr.get("en")), _aware(r.get("creado")), control) if t), default=None)
    plazo = SIN_NOTICIAS_AUTO_S if r["auto"] else rec.VIGENCIA_RECORRIDO_S
    return vivo is not None and ahora - vivo < timedelta(seconds=plazo)


def _guardar_plan_auto(db: Database, uid: int, plan: dict, a: dict, si: dict | None = None,
                       previo: dict | None = None) -> dict | None:
    """Guarda `plan` como el de la presentación automática (para la pantalla en off, `por` = auto) y deja la posición
    en su primer paso, en una sola escritura. Solo si sigue encendida y, con `si`, si el documento sigue como se leyó
    (su versión): un plan o una orden que llegó entretanto manda. Con `previo` (el recorrido que reemplaza, si no era
    de la automática), lo guarda como `recorrido_previo`: «Volver a reproducir» de su tarjeta lo trae (`controlar`).
    Devuelve el documento nuevo, o None si no se guardó."""
    esc = plan["escenas"][0]
    return db.pantallas.find_one_and_update(
        {"_id": uid, "auto.activa": True, **(si or {})},
        {"$set": {**_poner_recorrido(plan, "pantalla_off", "auto"),
                  "auto": {"activa": True, "capitulo": esc["capitulo"], "paso": esc["paso"], "rid": plan["id"],
                           "vueltas": a["vueltas"], "fallas": a["fallas"]},
                  **({"recorrido_previo": previo} if previo else {})},
         "$inc": {"v": 1}}, return_document=ReturnDocument.AFTER)


def _armar_auto(db: Database, uid: int, guion: Any, doc: dict | None, si: dict | None = None) -> dict | None:
    """Arma el plan que sigue desde la posición de `doc` (`automatica.plan_desde`: el capítulo desde ese paso o, si ahí
    no queda nada que narrar, el siguiente) y lo guarda. Si el recorrido que reemplaza no era de la automática (un plan
    del asistente o del panel), queda como `recorrido_previo`. Devuelve el documento nuevo, o None si no hay nada que
    armar."""
    a = auto_de(doc, guion)
    x = automatica.plan_desde(guion, guion.por_id(a["capitulo"]), a["paso"]) if a and a["activa"] else None
    if x is None:
        return None
    plan, vueltas = x
    r = (doc or {}).get("recorrido")
    previo = r if isinstance(r, dict) and r.get("auto") is not True and isinstance(r.get("id"), str) else None
    return _guardar_plan_auto(db, uid, plan, {**a, "vueltas": a["vueltas"] + vueltas}, si, previo)


def recorrido_previo(doc: dict | None, guion: Any) -> dict | None:
    """El último plan que no era de la presentación automática, si después de él solo sonaron planes suyos (el
    recorrido guardado es uno de la automática) y sigue valiendo contra el guion vigente (`recorrido_de`); si no, None.
    Así «Volver a reproducir» de su tarjeta sirve con la automática encendida como sin ella: hasta que llegue otro plan
    que no sea de la automática."""
    actual = recorrido_de(doc, guion)
    previo = (doc or {}).get("recorrido_previo")
    if not actual or not actual["auto"] or not isinstance(previo, dict):
        return None
    r = recorrido_de({"recorrido": previo}, guion)
    return r if r and not r["auto"] else None


def iniciar_auto(db: Database, uid: int, guion: Any, por: str, ci: int = 0, ahora: datetime | None = None) -> dict:
    """Enciende la presentación automática desde el primer paso del capítulo `ci` (por omisión, el primero) y sube la
    versión. Si hay una pantalla en off abierta, arma y guarda ya el primer plan (reemplaza al que suene); si no, queda
    encendida y empieza cuando una se abra y lo pida. Devuelve el documento nuevo."""
    if por not in ORIGENES or por == "auto":
        raise ValueError("pantalla.iniciar_auto")
    a = {"activa": True, "capitulo": guion.capitulos[ci]["id"], "paso": 1, "rid": None, "vueltas": 0, "fallas": 0}
    # (sube la versión: las acciones de la última orden `visual` quedan en nada, o la pantalla las haría otra vez)
    doc = db.pantallas.find_one_and_update(
        {"_id": uid}, {"$set": {"auto": a, **ACCIONES_INICIALES, "actualizada": _ahora(), "por": por}, "$inc": {"v": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return (_armar_auto(db, uid, guion, doc) if conectada(doc, ahora) else None) or doc


def siguiente_auto(db: Database, uid: int, guion: Any, ahora: datetime | None = None) -> dict | None:
    """Lo que pide la pantalla en off cuando no narra nada: si la presentación automática está encendida y no suena
    ningún plan (`plan_sonando`), arma el que sigue desde su posición y lo guarda. Devuelve ese recorrido, o None si no
    había nada que hacer (apagada, un plan sonando o en pausa, o algo cambió entre la lectura y la escritura)."""
    doc = leer(db, uid)
    a = auto_de(doc, guion)
    if not a or not a["activa"] or plan_sonando(doc, guion, ahora):
        return None
    nuevo = _armar_auto(db, uid, guion, doc, si={"v": doc.get("v")})
    return recorrido_de(nuevo, guion) if nuevo else None


def detener_auto(db: Database, uid: int, guion: Any, por: str) -> dict | None:
    """Apaga la presentación automática (sube la versión) y, si su plan sonaba, lo cierra con la escena en curso como
    base. La posición se queda. Primero la apaga: así la pantalla no alcanza a pedir otro plan entre una cosa y la
    otra. Como toda orden que sube la versión, deja las acciones (`ACCIONES`) en nada. Devuelve el documento (el mismo
    si ya estaba apagada o nunca se encendió)."""
    if por not in ORIGENES or por == "auto":
        raise ValueError("pantalla.detener_auto")
    doc = leer(db, uid)
    a = auto_de(doc, guion)
    if not a or not a["activa"]:
        return doc
    # (sube la versión: las acciones de la última orden `visual` quedan en nada, o la pantalla las haría otra vez)
    doc = db.pantallas.find_one_and_update(
        {"_id": uid}, {"$set": {"auto.activa": False, "auto.rid": None, **ACCIONES_INICIALES, "actualizada": _ahora(),
                                "por": por}, "$inc": {"v": 1}}, return_document=ReturnDocument.AFTER)
    return (colapsar(db, uid, guion, por, rid=a["rid"]) if a["rid"] else None) or doc


def _auto_tras_avance(a: dict, r: dict, p: dict, guion: Any, cierra: bool) -> dict:
    """Lo que cambia de `auto` (el guardado, activo) con el avance `p` de su plan `r`, como claves de `$set`:
    * la posición: el paso de la escena en curso; con «cierre» o «fin» (ya se dijo todo), el que sigue al último del
      plan (`automatica.posicion`: el primero del capítulo siguiente o, después del último, el de la presentación, con
      una vuelta más); en pausa o detenido, se queda;
    * «fin»: suelta el plan (`rid` en None); la pantalla pedirá el siguiente;
    * «detenido» (que cierra): suelta el plan y, si lo detuvo alguien a propósito en esa pantalla (DETIENEN_AUTO: una
      tecla o un botón), se apaga. El de una vista que se desmonta (salir del modo en off, ir a otra vista del panel:
      `otra_orden`) no la apaga: queda encendida en ese paso y la pantalla que se abra después sigue desde ahí;
    * «error»: suelta el plan; si la escena falló, la salta; al tercero seguido sin haber vuelto a narrar
      (MAX_FALLAS_AUTO) se apaga: no insiste sobre una presentación que no responde."""
    fase = p["fase"]
    try:
        esc, ultima = r["escenas"][p["n"] - 1], r["escenas"][-1]
        if fase in ("cierre", "fin"):
            pos = (ultima["capitulo"], ultima["paso"] + 1)
        elif fase == "error" and p.get("motivo") == "escena_fallida":
            pos = (esc["capitulo"], esc["paso"] + 1)
        elif fase in ("pausa", *rec.TERMINALES):
            pos = None
        else:
            pos = (esc["capitulo"], esc["paso"])
    except (KeyError, IndexError, TypeError):   # alguien tocó el recorrido en la base
        pos = None
    out: dict = {}
    if pos is not None:
        capitulo, paso, vuelta = automatica.posicion(guion, *pos) if guion is not None else (*pos, 0)
        if (capitulo, paso) != (a.get("capitulo"), a.get("paso")):
            out.update({"auto.capitulo": capitulo, "auto.paso": paso})
            if vuelta:
                out["auto.vueltas"] = (a["vueltas"] if _entero(a.get("vueltas"), 0, 10 ** 9) else 0) + vuelta
    if fase == "fin":
        out.update({"auto.rid": None, "auto.fallas": 0})
    elif fase == "error":
        fallas = (a["fallas"] if _entero(a.get("fallas"), 0, MAX_FALLAS_AUTO) else 0) + 1
        out.update({"auto.rid": None, "auto.fallas": fallas, **({"auto.activa": False} if fallas >= MAX_FALLAS_AUTO else {})})
    elif cierra:   # solo un detener a propósito la apaga; la vista que se va (`otra_orden`) solo suelta el plan
        out.update({"auto.rid": None, **({"auto.activa": False} if p.get("motivo") in DETIENEN_AUTO else {})})
    elif fase == "narrando" and a.get("fallas"):
        out["auto.fallas"] = 0   # volvió a narrar: los errores de antes ya no cuentan
    return out


def describir_auto(doc: dict | None, guion: Any, ahora: datetime | None = None) -> str:
    """La presentación automática para el contexto del asistente, o «» si está apagada: dónde va y qué hacer si la
    persona pregunta algo (un plan corto la interrumpe y, cuando termina, sigue sola)."""
    a = auto_de(doc, guion)
    if not a or not a["activa"]:
        return ""
    c = guion.capitulos[guion.por_id(a["capitulo"])]
    donde = f"{c['nombre']} ({c['id']}), paso {a['paso']} de {len(c['pasos'])}"
    x = resumen_recorrido(doc, guion, ahora) or {}
    if not conectada(doc, ahora):
        t = ("Presentación automática encendida, pero no hay una pantalla en off abierta: empieza sola (en "
             f"{donde}) cuando la persona abra la vista Presentación en modo en off")
    elif not a["rid"] and plan_sonando(doc, guion, ahora):
        t = f"Presentación automática encendida, en espera mientras termina ese plan: después sigue sola en {donde}"
    else:
        t = ("Presentación automática encendida: la pantalla en off recorre sola toda la presentación, muy resumida; "
             f"va en {donde}")
        if a["rid"] and x.get("id") == a["rid"]:
            t += (", en pausa" if x["fase"] == "pausa" else "") + \
                (f"; voz: {x['voz'].replace('_', ' ')}" if x.get("voz") else "")
    return (f"{t}. Si la persona pregunta algo, respóndele con un plan CORTO (plan con largo corto, o recorrido de 3 a 5 pasos): la interrumpe "
            "y, cuando termina, sigue sola desde ese paso. No la detengas ni la reinicies si no te lo piden (op "
            "automatica)")


def leer(db: Database, uid: int) -> dict | None:
    return db.pantallas.find_one({"_id": uid})


def guardar(db: Database, uid: int, cambios: dict, por: str, si: dict | None = None) -> dict | None:
    """Aplica `cambios` (solo campos de CAMPOS) y sube la versión. Devuelve el documento nuevo. Con `si`, solo si el
    documento sigue así (esos campos con esos valores; un campo que falta vale None): si no, no escribe y devuelve None."""
    malos = set(cambios) - set(CAMPOS)
    if malos or por not in ORIGENES:
        raise ValueError(f"pantalla.guardar: {sorted(malos) or por}")
    return db.pantallas.find_one_and_update(
        {"_id": uid, **(si or {})}, {"$set": {**cambios, "actualizada": _ahora(), "por": por}, "$inc": {"v": 1}},
        upsert=si is None, return_document=ReturnDocument.AFTER)


def acciones_pendientes(doc: dict | None, ahora: datetime | None = None) -> dict:
    """Las acciones guardadas (`ACCIONES`, solo las que hacen algo) que la pantalla en off abierta todavía no recibió:
    las de una versión posterior a la última que le entregó la API (`entregada_v`). {} si no hay, si ya las recibió o si
    no hay una pantalla abierta (la que se abre después no hace las de antes: no tiene con qué compararlas)."""
    if not doc or not conectada(doc, ahora):
        return {}
    v, dada = doc.get("v"), doc.get("entregada_v")
    if isinstance(dada, int) and not isinstance(dada, bool) and isinstance(v, int) and dada >= v:
        return {}
    return {k: doc[k] for k in ACCIONES if doc.get(k) not in (None, False)}


def juntar_acciones(doc: dict, pendientes: dict, cambios: dict) -> dict | None:
    """Las acciones de una orden (`cambios`) junto con las que la pantalla todavía no recibió (`pendientes`), para que no
    se pierdan: la simulación se suma detrás, en orden, si la orden no cambia de modelo del atlas (si abre otro, las de
    antes ya no tienen dónde hacerse y se van) y si juntas no pasan de `recorrido.MAX_SIMULAR`; la animación vale si
    alguna la pide; el viaje de la cámara, el que haya (dos no se pueden juntar). Devuelve las tres acciones, o None si
    no caben juntas (dos viajes de la cámara o demasiados controles): hay que esperar a que la pantalla reciba las de
    antes."""
    out = {k: cambios.get(k, ACCIONES_INICIALES[k]) for k in ACCIONES}
    if pendientes.get("mover") is not None:
        if out["mover"] is not None:
            return None
        out["mover"] = pendientes["mover"]
    out["animar"] = out["animar"] is True or pendientes.get("animar") is True
    previa = pendientes.get("simular")
    if previa and cambios.get("inmersion", doc.get("inmersion")) == doc.get("inmersion"):
        juntos = [*previa, *(out["simular"] or [])]
        if len(juntos) > rec.MAX_SIMULAR:
            return None
        out["simular"] = juntos
    return out


def guardar_orden(db: Database, uid: int, cambios: dict, por: str, esperar: bool = True) -> dict | None:
    """`guardar` para la orden de un agente (`cambios` con sus `ACCIONES`). Con una pantalla en off abierta, las acciones
    que todavía no recibió (`acciones_pendientes`) no se pisan: se juntan con las de la orden (`juntar_acciones`), salvo
    que la orden cambie de paso (ya no tienen dónde hacerse). Y la escritura solo vale sobre el documento como se leyó
    (su versión y lo entregado): si entretanto llegó otra orden (dos en paralelo) o la pantalla recibió las de antes,
    devuelve None y quien llama vuelve a intentar con el documento nuevo. También None si no caben juntas y `esperar`:
    hay que dar tiempo a que la pantalla las reciba (sin `esperar`, las de antes se pierden). Sin pantalla abierta es
    `guardar`, como siempre. Devuelve el documento nuevo."""
    doc = leer(db, uid)
    if not conectada(doc):
        return guardar(db, uid, cambios, por)
    pendientes = acciones_pendientes(doc)
    if pendientes and not any(k in cambios and cambios[k] != doc.get(k) for k in ("capitulo", "paso")):
        juntas = juntar_acciones(doc, pendientes, cambios)
        if juntas is None and esperar:
            return None
        cambios = {**cambios, **(juntas or {})}
    return guardar(db, uid, cambios, por, si={"v": doc.get("v"), "entregada_v": doc.get("entregada_v")})


def marcar_vista(db: Database, uid: int) -> dict | None:
    """La pantalla preguntó: queda `visto` (está abierta). Devuelve el documento (None si nunca recibió una orden)."""
    return db.pantallas.find_one_and_update({"_id": uid}, {"$set": {"visto": _ahora()}}, upsert=True,
                                            return_document=ReturnDocument.AFTER)


def entregar(db: Database, uid: int, v: int | None) -> dict | None:
    """La pantalla en off pregunta, con la versión `v` que ya tiene (`GET /api/pantalla`): queda como abierta (`visto`)
    y la versión vigente, como entregada (`entregada_v`: desde ahí sus acciones ya no son pendientes). Devuelve el
    documento a entregar, o None si es la versión que ya tiene. La marca vale solo sobre la versión que se leyó: si en
    medio llegó una orden, se vuelve a leer y se entrega esa (así unas acciones que la orden juntó con otras todavía no
    entregadas no llegan dos veces)."""
    doc = marcar_vista(db, uid)
    for _ in range(5):
        vigente, dada = int(doc.get("v") or 0), doc.get("entregada_v")
        if isinstance(dada, int) and not isinstance(dada, bool) and dada >= vigente:
            break
        marcado = db.pantallas.find_one_and_update({"_id": uid, "v": doc.get("v")}, {"$set": {"entregada_v": vigente}},
                                                   return_document=ReturnDocument.AFTER)
        if marcado is not None:
            doc = marcado
            break
        doc = leer(db, uid) or doc
    return None if v is not None and v == int(doc.get("v") or 0) else doc


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
