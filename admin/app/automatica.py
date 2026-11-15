"""La presentación automática: la pantalla en off recorre sola toda la presentación técnica, capítulo por capítulo, con
una frase muy resumida por cada paso. Sin modelo y sin costo: la narración sale del propio guion (`agente/guion.py`).

Aquí está lo puro: qué se dice en cada paso (`narracion_del_paso`), el plan de un capítulo (`plan_del_capitulo`: un
recorrido absoluto como los que arma el asistente, `app/recorrido.py`, con una escena por paso) y por dónde sigue
(`posicion`, `plan_desde`). El estado (si está encendida, por dónde va, cuál es su plan) vive en el documento de la
pantalla en off (`app/pantalla.py`, clave `auto`); la pantalla pide los planes uno tras otro
(`POST /api/pantalla/auto/siguiente`) y los narra como cualquier otro. Un plan del asistente la interrumpe y, cuando
termina, sigue en el paso que se estaba diciendo.

Qué se dice en un paso, en este orden: la narración escrita a mano (`tecnica.narracion[capítulo][id del paso]` de
data/propuesta/general.json, que `guion.derivar` deja en el paso como `narracion`); en un paso de metas, la primera
meta, resumida (`primera_meta`: la frase de su texto es la misma en todos los módulos); si no, la primera frase del
texto del paso (`resumir`); si no sirve y el título es breve (un rótulo como «Cinco piezas, una sola red»), una
frase corta del texto o de las cifras del paso (`frase_corta`); y si nada de eso, su título. Todo pasa por las reglas
de lo que se proyecta (`app/proyectable.py`) y nada habla de costos: lo que no pasa no se dice, y un paso sin nada que
decir se salta.

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
# Un título de menos de TITULO_BREVE caracteres es un rótulo («Un solo hospital para 22.429 habitantes», «Cinco piezas,
# una sola red»), no una frase que diga algo sola: antes de decirlo se busca una frase corta del paso (`frase_corta`).
# Uno más largo ya es una frase («Menos basura a la celda: ECA y compostaje en el mismo predio») y se dice tal cual
_TITULO_BREVE = 50
# Donde se parte una frase en ideas para `frase_corta`: un punto y coma seguido de un espacio (lo que va antes y lo
# que va después son dos oraciones). En los dos puntos no: lo que sigue suele ser una lista o un detalle sin sujeto
_PUNTO_Y_COMA = re.compile(r";(?= )")
# Una meta del paso de metas: «Indicador: línea base → meta (año)». Al resumirla se quitan los paréntesis (la fuente
# y el año de la línea base, las aclaraciones), salvo el año de la meta, que queda dicho: «(2031)» → «en 2031»
_FLECHA = "→"
_ANIO = re.compile(r"\s*\(((?:19|20)[0-9]{2})\)")
_PARENTESIS = re.compile(r"\s*\([^()]*\)")
_SIN_DATO = re.compile(r"^(?:[—–-]+|sin dato\b.*)$", re.I)


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


def _como_frase(t: str) -> str:
    """Un trozo de texto como frase: sin la puntuación suelta de los bordes, con mayúscula inicial y punto final."""
    t = " ".join(t.split()).strip(" ,;:")
    return _con_punto(t[:1].upper() + t[1:]) if t else ""


def _minuscula(t: str) -> str:
    """`t` con minúscula inicial para ir dentro de una frase («Sedes rurales…» → «sedes rurales…»), salvo si empieza
    por una sigla o un número («PSMV vigente…», «EBAR y PTAR…», «0 %»)."""
    return t[0].lower() + t[1:] if len(t) > 1 and t[0].isupper() and t[1].islower() else t


def _ideas(frase: str) -> list[str]:
    """Las partes de `frase` separadas por punto y coma, cada una como frase (`_como_frase`); nunca partida dentro de
    un paréntesis o de unas comillas. Sin punto y coma, ninguna: la frase entera ya se miró."""
    cortes = [m.start() for m in _PUNTO_Y_COMA.finditer(frase) if _equilibrado(frase[:m.start()])]
    if not cortes:
        return []
    return [_como_frase(frase[a:b]) for a, b in zip([0, *(c + 1 for c in cortes)], [*cortes, len(frase)])]


def _decible(t: str, minimo: int, maximo: int) -> str | None:
    """`t` como se proyecta si mide entre `minimo` y `maximo` caracteres, no deja un paréntesis ni unas comillas a
    medias, no habla de costos y pasa las reglas de lo que se proyecta; si no, None."""
    if not minimo <= len(t) <= maximo or not _equilibrado(t) or _DE_COSTOS.search(t):
        return None
    return _proyectable(t, maximo)


def frase_corta(p: dict) -> str:
    """Una frase corta (de MIN_CORTE a MAX_AUTO caracteres) para un paso cuyo título es solo un rótulo y cuya primera
    frase no sirve (muy larga sin dónde cortarla, o habla de costos): la primera idea del texto que quepa, en orden
    (cada frase entera o, si es larga, cada una de sus partes separadas por punto y coma) y, si ninguna, la primera
    cifra del paso (su valor y su leyenda: «1 sede pública de salud habilitada…»). Sin costos y pasando las reglas de
    lo que se proyecta. «» si no hay ninguna (entonces se dice el título)."""
    ideas: list[str] = []
    texto = p.get("texto")
    if isinstance(texto, str) and texto.strip():
        for frase in rec.partir_frases(texto):
            ideas += [frase, *_ideas(frase)]
    for c in p.get("cifras") if isinstance(p.get("cifras"), list) else ():
        v, leyenda = (c.get("v"), c.get("l")) if isinstance(c, dict) else (None, None)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool) and isinstance(leyenda, str):
            ideas.append(_como_frase(f"{v} {leyenda}"))
    return next((t for t in (_decible(x, MIN_CORTE, MAX_AUTO) for x in ideas) if t), "")


def _sin_parentesis(t: str, anio: bool = False) -> str:
    """`t` sin lo que va entre paréntesis (también anidados), con los espacios en uno; con `anio`, el de un año queda
    dicho («5 (2031)» → «5 en 2031»)."""
    if anio:
        t = _ANIO.sub(r" en \1", t)
    previo = None
    while previo != t:
        previo, t = t, _PARENTESIS.sub("", t)
    return " ".join(t.split()).strip(" ,;:")


def primera_meta(p: dict) -> str:
    """Lo que se dice en un paso de metas (`metas`: «Indicador: línea base → meta (año)»): su primera meta, resumida,
    sin los paréntesis salvo el año de la meta: «La primera meta: sedes rurales de salud habilitadas en el REPS, de 0 a
    5 en 2031.» Si con la línea base pasa de MAX_AUTO + HOLGURA caracteres (o no hay línea base), solo la meta: «La
    primera meta, laboratorio clínico: propio, 24 horas…». Sin costos y pasando las reglas de lo que se proyecta. «» si
    el paso no trae metas o la primera no se puede decir (entonces se sigue con su texto)."""
    metas = p.get("metas")
    m = metas[0] if isinstance(metas, list) and metas else None
    if not isinstance(m, str) or m.count(_FLECHA) != 1:
        return ""
    antes, _, despues = m.partition(_FLECHA)
    nombre, dos_puntos, base = antes.partition(": ")
    # de la línea base, solo el dato: lo que sigue a una coma, un punto y coma o dos puntos es una aclaración
    # («9 h, de 4:00 a 13:00» → «9 h»; «0 %: licencia vencida…» → «0 %»)
    base = re.split(r"[,;:](?= )", _sin_parentesis(base), maxsplit=1)[0]
    nombre, base, meta = _sin_parentesis(nombre), _sin_parentesis(base), _sin_parentesis(despues, anio=True)
    if not dos_puntos or not nombre or not meta or _SIN_DATO.match(meta):
        return ""
    nombre, meta = _minuscula(nombre), _minuscula(meta)
    formas = [f"La primera meta: {nombre}, de {_minuscula(base)} a {meta}"] if base and not _SIN_DATO.match(base) else []
    formas.append(f"La primera meta, {nombre}: {meta}")
    return next((t for t in (_decible(_con_punto(x), 10, MAX_AUTO + HOLGURA) for x in formas) if t), "")


def _candidatas(p: dict):
    """Lo que se puede decir en el paso `p`, en el orden de `narracion_del_paso`; cada una se calcula solo si la
    anterior no sirvió."""
    yield p.get("narracion")
    yield primera_meta(p)
    frase = resumir(p.get("texto"))
    yield "" if _DE_COSTOS.search(frase) else frase
    titulo = _con_punto(p.get("titulo"))
    if len(titulo) < _TITULO_BREVE:
        yield frase_corta(p)
    yield titulo


def narracion_del_paso(g: Any, ci: int, pi: int) -> str | None:
    """Lo que la presentación automática dice en el paso `pi` (desde 0) del capítulo `ci`: una frase muy resumida. La
    escrita a mano si el guion la trae (`narracion`); en un paso de metas, la primera meta (`primera_meta`); si no, la
    primera frase de su texto (`resumir`), salvo que hable de costos; si no y el título es breve, una frase corta del
    texto o de las cifras del paso (`frase_corta`); si no, su título. La primera que pase las reglas de lo que se
    proyecta; None si ninguna (ese paso se salta)."""
    p = g.capitulos[ci]["pasos"][pi]
    return next((t for t in map(_proyectable, _candidatas(p)) if t), None)


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
