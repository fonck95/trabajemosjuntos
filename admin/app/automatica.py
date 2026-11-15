"""La presentación automática: la pantalla en off recorre sola toda la presentación técnica, capítulo por capítulo, con
una frase muy resumida por cada paso. Sin modelo y sin costo: la narración sale del propio guion (`agente/guion.py`).

Aquí está lo puro: qué se dice en cada paso (`narracion_del_paso`), el plan de un capítulo (`plan_del_capitulo`: un
recorrido absoluto como los que arma el asistente, `app/recorrido.py`, con una escena por paso) y por dónde sigue
(`posicion`, `plan_desde`). El estado (si está encendida, por dónde va, cuál es su plan) vive en el documento de la
pantalla en off (`app/pantalla.py`, clave `auto`); la pantalla pide los planes uno tras otro
(`POST /api/pantalla/auto/siguiente`) y los narra como cualquier otro. Un plan del asistente la interrumpe y, cuando
termina, sigue en el paso que se estaba diciendo.

Qué se dice en un paso, en este orden: la narración escrita a mano (`tecnica.narracion[capítulo][id del paso]` de
data/propuesta/general.json, que `guion.derivar` deja en el paso como `narracion`); si no hay, la primera frase del
texto del paso (`resumir`); si no sirve, su título. Todo pasa por las reglas de lo que se proyecta
(`app/proyectable.py`): lo que no pasa no se dice, y un paso sin nada que decir se salta.

Solo usa la biblioteca estándar, `app/recorrido.py` y `app/proyectable.py`: no importa nada del panel."""
from __future__ import annotations

import re
import secrets
from typing import Any

from . import recorrido as rec
from .proyectable import texto_proyectable

# «Muy resumida»: una frase de hasta MAX_AUTO caracteres. La primera frase del paso que pase por poco (HOLGURA) va
# entera; más larga, se corta donde termina una idea (`resumir`) y lo que queda tiene al menos MIN_CORTE. La escrita a
# mano puede llegar al tope de cualquier narración (`rec.MAX_NARRACION`)
MAX_AUTO = 180
HOLGURA = 20
MIN_CORTE = 40
# Lo que tarda la pantalla en pedir el plan siguiente cuando termina uno automático (`ESPERA_AUTO_MS` de
# vistas/presentacion.js): solo para estimar cuánto dura la vuelta completa
ESPERA_ENTRE_PLANES_MS = 1500
# Dónde se puede cortar una frase larga: un punto y coma o dos puntos seguidos de un espacio (los de «4:00» no lo
# son); lo que queda antes es una idea completa. En una coma no: ahí se parte una enumeración o un inciso («…la
# portería con báscula y, sobre la vía interna.»)
_PAUSA = re.compile(r"[;:](?= )")
# La presentación técnica no habla de costos: el guion ya viene sin montos, pero una frase puede quedar hablando de la
# plata sin nombrar una cifra en pesos («la torre se lleva el 76 % del costo del módulo»). Esa no se narra: va el título
_DE_COSTOS = re.compile(r"\bcost[oa]s?\b|\binversi[oó]n(?:es)?\b|\bpresupuest|\bfinanciaci[oó]n\b", re.I)
_CIERRA = (".", "!", "?", "…")


def _proyectable(t: Any, maximo: int = rec.MAX_NARRACION) -> str | None:
    """El texto como se proyecta (con los espacios en uno), o None si no es texto o no pasa las reglas."""
    if not isinstance(t, str) or not t.strip():
        return None
    try:
        return texto_proyectable(t, maximo)
    except ValueError:
        return None


def _equilibrado(t: str) -> bool:
    return t.count("(") == t.count(")") and t.count("«") == t.count("»")


def resumir(texto: Any, tope: int = MAX_AUTO, holgura: int = HOLGURA) -> str:
    """La primera frase de `texto` (`rec.partir_frases`: una sigla con puntos no la parte). Si pasa de `tope` + `holgura`,
    cortada con punto final en su último punto y coma o dos puntos que deje entre MIN_CORTE y `tope` caracteres, nunca
    dentro de un paréntesis o de unas comillas. «» si no hay texto o no hay dónde cortarla (entonces se dice el título)."""
    if not isinstance(texto, str) or not texto.strip():
        return ""
    frase = rec.partir_frases(texto)[0]
    if len(frase) <= tope + holgura:
        return frase
    corte = None
    for m in _PAUSA.finditer(frase):
        if m.start() + 1 > tope:
            break
        if m.start() >= MIN_CORTE and _equilibrado(frase[:m.start()]):
            corte = m.start()
    return frase[:corte].rstrip() + "." if corte is not None else ""


def _con_punto(t: Any) -> str:
    """Un título como frase: con su punto final («Cinco piezas, una sola red.»)."""
    t = " ".join(t.split()) if isinstance(t, str) else ""
    return t if not t or t.endswith(_CIERRA) else t + "."


def narracion_del_paso(g: Any, ci: int, pi: int) -> str | None:
    """Lo que la presentación automática dice en el paso `pi` (desde 0) del capítulo `ci`: una frase muy resumida. La
    escrita a mano si el guion la trae (`narracion`); si no, la primera frase de su texto (`resumir`), salvo que hable
    de costos; si no, su título. La primera de las tres que pase las reglas de lo que se proyecta; None si ninguna
    (ese paso se salta)."""
    p = g.capitulos[ci]["pasos"][pi]
    frase = resumir(p.get("texto"))
    candidatas = (p.get("narracion"), "" if _DE_COSTOS.search(frase) else frase, _con_punto(p.get("titulo")))
    return next((t for t in map(_proyectable, candidatas) if t), None)


def plan_del_capitulo(g: Any, ci: int, desde: int = 1) -> dict | None:
    """El plan automático del capítulo `ci` desde su paso `desde` (desde 1): un recorrido ABSOLUTO válido
    (`rec.validar(r, g) == []`) con el nombre del capítulo por título y una escena por paso: su narración
    (`narracion_del_paso`), el panel a la vista, lo visual del paso, la animación propia del paso y un movimiento suave
    de la cámara que alterna el sentido (`rec.mover_suave`, el del plan guiado; no dentro de un modelo del atlas). Sin
    cierre: lo que sigue es el capítulo siguiente. Un paso sin nada que decir se salta. Lleva a lo sumo
    `rec.MAX_ESCENAS` escenas y `rec.MAX_DURACION_MS`: si el capítulo no cabe, el plan termina antes y el siguiente
    sigue desde ahí (`posicion`). None si no queda ningún paso narrable."""
    c = g.capitulos[ci]
    escenas: list[dict] = []
    suaves = 0
    for pi in range(max(0, desde - 1), len(c["pasos"])):
        narracion = narracion_del_paso(g, ci, pi)
        if narracion is None:
            continue
        esc = {"capitulo": c["id"], "paso": pi + 1, "panel": True, "visual": rec.visual_inicial(), "resaltar": None,
               "mover": None, "animar": True, "frases": rec.partir_frases(narracion), "sostener_ms": 0}
        if rec.inmersion_de(esc, g) is None:
            esc["mover"] = rec.mover_suave(suaves)
            suaves += 1
        esc["sostener_ms"] = rec.sostener_por_omision(esc, escenas[-1] if escenas else None, g)
        escenas.append(esc)
        if len(escenas) > 1 and rec.duracion_ms({"escenas": escenas, "cierre": None}, g) > rec.MAX_DURACION_MS:
            escenas.pop()
            break
        if len(escenas) == rec.MAX_ESCENAS:
            break
    if not escenas:
        return None
    r = {"id": secrets.token_hex(6), "titulo": _proyectable(c.get("nombre"), rec.MAX_TITULO) or "Presentación",
         "escenas": escenas, "cierre": None}
    return r if not rec.validar(r, g) else None   # (no debería fallar: todo sale del guion y ya pasó las reglas)


def posicion(g: Any, capitulo: Any, paso: Any) -> tuple[str, int, int]:
    """La posición (capítulo, paso) llevada a una que existe en el guion, y las vueltas que eso suma (0 o 1): un paso
    más allá del último del capítulo es el primero del capítulo siguiente y, después del último capítulo, el primero de
    la presentación (una vuelta más). Un capítulo que ya no está (el guion cambió) es el primero; un paso que no es un
    número desde 1, el primero."""
    ci = g.por_id(capitulo)
    if ci is None:
        return g.capitulos[0]["id"], 1, 0
    if isinstance(paso, bool) or not isinstance(paso, int) or paso < 1:
        paso = 1
    vueltas = 0
    if paso > len(g.capitulos[ci]["pasos"]):
        ci, paso = ci + 1, 1
        if ci >= len(g.capitulos):
            ci, vueltas = 0, 1
    return g.capitulos[ci]["id"], paso, vueltas


def plan_desde(g: Any, ci: int, paso: int = 1) -> tuple[dict, int] | None:
    """El plan que sigue desde (`ci`, `paso`): el del primer capítulo que tenga algo que narrar desde ahí, dando a lo
    sumo una vuelta entera, y las vueltas que se dieron al buscarlo. None si ningún capítulo tiene nada que narrar."""
    vueltas = 0
    for _ in range(len(g.capitulos) + 1):
        plan = plan_del_capitulo(g, ci, paso)
        if plan is not None:
            return plan, vueltas
        ci, paso = ci + 1, 1
        if ci >= len(g.capitulos):
            ci, vueltas = 0, vueltas + 1
    return None


def duracion_de_la_vuelta_ms(g: Any) -> int:
    """Lo que tarda, más o menos, la vuelta completa: los planes de todos los capítulos (`rec.duracion_ms`, sin la
    espera de un plan nuevo ni la de las preguntas del final, que el automático no hace) y lo que la pantalla tarda en
    pedir el siguiente."""
    total = 0
    for ci in range(len(g.capitulos)):
        paso = 1
        while paso <= len(g.capitulos[ci]["pasos"]):
            plan = plan_del_capitulo(g, ci, paso)
            if plan is None:
                break
            total += rec.duracion_ms(plan, g) - rec.PREVIA_MS - rec.PREGUNTAS_MS - rec.FIN_MS + ESPERA_ENTRE_PLANES_MS
            paso = plan["escenas"][-1]["paso"] + 1
    return total
