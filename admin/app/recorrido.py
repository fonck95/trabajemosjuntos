"""El recorrido narrado de la presentación técnica: lo que el agente presentador (el asistente del panel o un agente por
MCP) arma en UNA llamada (`presentacion`, op `recorrido`) y la pantalla reproduce sola, a ritmo humano.

Un recorrido son de 1 a MAX_ESCENAS escenas. Cada escena es una idea: lo que se dice (sus frases, que se proyectan en el
subtítulo y, si la sala activó la voz, se leen en voz alta) y lo que se ve mientras se dice (el paso, «Solo 3D», la
cámara, la obra enfocada, la ficha técnica, hoy o con el proyecto, un modelo del atlas y un resaltado de lo que se
nombra). Al final, un cierre de hasta tres ideas que queda en la sala con «¿Preguntas?».

Aquí está su forma absoluta (la que viaja al navegador y se guarda con la pantalla, `app/pantalla.py`): cada escena con
su estado completo (no un cambio sobre la anterior), así cualquier pantalla puede empezar, reanudar o saltar a cualquier
escena. Y las reglas que la validan, puras: `validar` corre al crearla (`agente/herramientas/interfaz.py`) y cada vez que
se lee de la base, contra el guion vigente. Los mismos topes y listas están en web/js/propuesta/mando.js y en
web/js/agente-presentacion.js; una prueba los compara.

Solo usa la biblioteca estándar y `app/proyectable.py`: no importa nada del panel."""
from __future__ import annotations

import json
import re
from typing import Any

from .proyectable import texto_proyectable

MAX_ESCENAS = 8
MAX_FRASES = 3
MAX_NARRACION = 220   # una escena: juntas sus frases (el tope de la explicación)
MAX_TITULO = 80
MAX_PUNTO = 80
MAX_PUNTOS = 3
MAX_CIERRE = 200      # los puntos juntos: con « · » entre ellos el estado no pasa de 220
MAX_SUGERENCIA = 60
MAX_SUGERENCIAS = 3
MAX_SOSTENER_MS = 8000
MAX_RECORRIDO_BYTES = 16384
MAX_DURACION_MS = 240_000
# Lo que se puede señalar en una escena (`resaltar` de main.js) y su tope
RESALTAR = {"cifra": 12, "punto": 20, "leyenda": 12, "especificacion": 20}
RESALTAR_TIPOS = (*RESALTAR, "componente")
EN = ("panel", "ficha")
# El avance que manda la pantalla que reproduce (`reproductor.js`) y los controles
FASES = ("preparando", "narrando", "sosteniendo", "cierre", "pausa", "fin", "detenido", "error")
TERMINALES = ("fin", "detenido", "error")
CONTROLES = ("pausar", "continuar", "siguiente", "anterior", "repetir", "reproducir", "detener")
VOCES = ("activa", "apagada", "sin_activar", "sin_voces")
MOTIVOS = ("persona", "tecla", "boton", "mensaje", "otra_orden", "reemplazo", "proyector", "sin_respuesta",
           "escena_fallida")
AVISOS = ("atlas", "resaltar", "asiento", "voz")
DESTINOS = ("vista", "pantalla_off")
CAMARAS = ("paso", "aerea", "oblicua", "rasante", "cerca", "lejos")
VISUAL = ("enfoque", "camara", "rumbo", "girar", "comparar", "detalle", "inmersion")
VISUAL_INICIAL = {"enfoque": None, "camara": "paso", "rumbo": None, "girar": False, "comparar": "proyecto",
                  "detalle": None, "inmersion": None}
# Un recorrido nuevo se narra en la pantalla en off si llega a tiempo; uno viejo (la pantalla se abrió después) se aplica
# en silencio en su última escena. Y una pantalla que se recargó a mitad reanuda si su avance es reciente
VIGENCIA_RECORRIDO_S = 90
REANUDAR_S = 20
ID = re.compile(r"[0-9a-f]{12}")
ID_CAPITULO = re.compile(r"[a-z_]{2,40}")
ID_PIEZA = re.compile(r"[a-z0-9_]{1,40}")
# Los tiempos del reproductor (`reproductor.js` exporta los mismos): el asiento de la imagen, el respiro antes de la
# voz, la lectura (por caracteres, con un piso y un techo), lo que se sostiene y el cierre
ASIENTO_MS = {"mismo": 900, "paso": 2400, "capitulo": 3600}
ASIENTO_ATLAS_MS = 4000
RESPIRO_MS = 350
ENTRE_FRASES_MS = 250
SOSTENER_MS = 1100
SOSTENER_MIRAR_MS = 2700
CIERRE_SOSTENER_MS = 4000
PREGUNTAS_MS = 12000
FIN_MS = 2500

# Dónde termina una frase: un punto, un cierre de pregunta o de exclamación, espacio y una mayúscula o un signo de
# apertura (`_FRASE` del guion), salvo después de una sigla con puntos («la E.S.E. Hospital…» no parte)
_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«(])")
_SIGLA = re.compile(r"(?:\b[A-ZÁÉÍÓÚÑ]\.){2,}$|\b(?:Res|art|Art|núm|No|Dr|Sr|Sra)\.$")


def partir_frases(texto: str) -> list[str]:
    """La narración en frases (de 1 a MAX_FRASES): las que siguen a la tercera se juntan con ella. La partición es una
    sola, aquí: el navegador recibe las frases ya partidas."""
    partes = [x.strip() for x in _FRASE.split(" ".join(str(texto).split())) if x.strip()]
    frases: list[str] = []
    for x in partes:
        if frases and _SIGLA.search(frases[-1]):
            frases[-1] = f"{frases[-1]} {x}"
        else:
            frases.append(x)
    if len(frases) > MAX_FRASES:
        frases = [*frases[:MAX_FRASES - 1], " ".join(frases[MAX_FRASES - 1:])]
    return frases or [" ".join(str(texto).split())]


def lectura_ms(texto: str) -> int:
    """Lo que tarda en leerse (o decirse) un texto: 62 ms por carácter más 1,5 s, entre 3,2 y 16 s."""
    return min(16000, max(3200, 1500 + 62 * len(texto)))


def abre_atlas(esc: dict, anterior: dict | None, guion: Any) -> bool:
    """¿La escena abre o cambia un modelo del atlas (una inmersión pedida o la de un paso de inmersión)?"""
    return inmersion_de(esc, guion) not in (None, inmersion_de(anterior, guion) if anterior else None)


def inmersion_de(esc: dict | None, guion: Any) -> str | None:
    """La inmersión que muestra una escena: la pedida, la del paso (un paso de inmersión) o ninguna."""
    if not esc:
        return None
    v = esc["visual"]["inmersion"]
    if v == "maqueta":
        return None
    if v:
        return v
    ci = guion.por_id(esc["capitulo"]) if guion is not None else None
    if ci is None:
        return None
    p = guion.capitulos[ci]["pasos"][esc["paso"] - 1]
    return (p.get("inmersion") or {}).get("id") if p.get("tipo") == "inmersion" else None


def sostener_por_omision(esc: dict, anterior: dict | None, guion: Any) -> int:
    """Lo que se sostiene la imagen después de narrar: más si hay algo que mirar (un modelo del atlas que se abre, el
    antes y después, la cámara que empieza a girar)."""
    ant = anterior["visual"] if anterior else VISUAL_INICIAL
    mirar = abre_atlas(esc, anterior, guion) or esc["visual"]["comparar"] != ant["comparar"] or \
        (esc["visual"]["girar"] and not ant["girar"])
    return SOSTENER_MIRAR_MS if mirar else SOSTENER_MS


def duracion_ms(r: dict, guion: Any = None) -> int:
    """La duración estimada de un recorrido absoluto (la que dice la herramienta y la tarjeta del chat)."""
    total, anterior = 0, None
    for esc in r["escenas"]:
        cambio = "capitulo" if not anterior or anterior["capitulo"] != esc["capitulo"] else \
            "paso" if anterior["paso"] != esc["paso"] else "mismo"
        total += ASIENTO_MS[cambio] + (ASIENTO_ATLAS_MS if abre_atlas(esc, anterior, guion) else 0) + RESPIRO_MS
        total += sum(lectura_ms(f) for f in esc["frases"]) + ENTRE_FRASES_MS * (len(esc["frases"]) - 1)
        total += esc["sostener_ms"]
        anterior = esc
    if r.get("cierre"):
        total += lectura_ms("En resumen. " + ". ".join(r["cierre"]["puntos"])) + CIERRE_SOSTENER_MS
    return total + PREGUNTAS_MS + FIN_MS


def estado_de_escena(esc: dict) -> dict:
    """Los campos de la pantalla (`pantalla.CAMPOS`) donde queda una escena: su paso, «Solo 3D» y lo visual, sin
    explicación ni índice ni fichas abiertos."""
    return {"capitulo": esc["capitulo"], "paso": esc["paso"], "explicacion": None, "panel": esc["panel"],
            "indice": False, "fichas": False, **esc["visual"]}


def bytes_de(r: Any) -> int:
    return len(json.dumps(r, ensure_ascii=False).encode("utf-8"))


def _entero(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _texto(v: Any, maximo: int) -> bool:
    if not isinstance(v, str):
        return False
    try:
        return texto_proyectable(v, maximo) == v
    except ValueError:
        return False


def _visual(v: Any, guion: Any, ci: int | None) -> list[str]:
    if not isinstance(v, dict) or set(v) != set(VISUAL):
        return ["lo visual no tiene sus siete partes"]
    out = []
    comps = {x["id"]: x for x in guion.componentes(ci)} if guion is not None and ci is not None else None
    inm = {i["id"] for i in getattr(guion, "inmersiones", ()) or ()}
    for k in ("enfoque", "detalle"):
        x = v[k]
        if x is None:
            continue
        if not isinstance(x, str) or not ID_PIEZA.fullmatch(x):
            out.append(f"{k} no es un id")
        elif comps is not None and (x not in comps or (k == "enfoque" and not comps[x].get("enfoque"))):
            out.append(f"{k} «{x}» no está en el capítulo" + (" con lugar en la maqueta" if k == "enfoque" else ""))
    x = v["inmersion"]
    if x is not None and (not isinstance(x, str) or not ID_PIEZA.fullmatch(x) or
                          (guion is not None and x != "maqueta" and x not in inm)):
        out.append("la inmersión no está en el catálogo")
    if v["camara"] not in CAMARAS:
        out.append("la cámara no es de la lista")
    if v["rumbo"] is not None and not _entero(v["rumbo"], 0, 359):
        out.append("el rumbo va de 0 a 359")
    if not isinstance(v["girar"], bool):
        out.append("girar es verdadero o falso")
    if v["comparar"] not in ("hoy", "proyecto"):
        out.append("comparar es hoy o proyecto")
    return out


def _resaltar(r: Any, guion: Any, ci: int | None, pi: int | None, esc: dict) -> list[str]:
    if r is None:
        return []
    if not isinstance(r, dict) or r.get("tipo") not in RESALTAR_TIPOS:
        return ["resaltar no tiene la forma"]
    tipo = r["tipo"]
    claves = {"tipo", "id"} if tipo == "componente" else {"tipo", "n", "en"} if tipo == "especificacion" else {"tipo", "n"}
    if set(r) != claves:
        return ["resaltar no tiene la forma"]
    if tipo == "componente":
        if not isinstance(r["id"], str) or not ID_PIEZA.fullmatch(r["id"]):
            return ["resaltar: el componente no es un id"]
    elif not _entero(r["n"], 1, RESALTAR[tipo]):
        return [f"resaltar: {tipo} va de 1 a {RESALTAR[tipo]}"]
    if tipo == "especificacion" and r["en"] not in EN:
        return ["resaltar: la especificación va en el panel o en la ficha"]
    if guion is None or ci is None or pi is None:
        return []
    if not esc["panel"] and tipo != "leyenda" and not (tipo == "especificacion" and r["en"] == "ficha"):
        return ["resaltar: con «Solo 3D» solo se señala la leyenda o la ficha"]
    hay = guion.resaltable(ci, pi)
    if tipo == "componente":
        return [] if r["id"] in hay.get("componentes", []) else ["resaltar: ese componente no tiene tarjeta en el paso"]
    if tipo == "especificacion":
        nombres = guion.especificaciones(ci, esc["visual"]["detalle"]) if r["en"] == "ficha" else hay["especificaciones"]
        return [] if r["n"] <= len(nombres) else ["resaltar: no hay esa especificación"]
    cuantos = {"cifra": hay["cifras"], "punto": hay["puntos"], "leyenda": hay["leyenda"]}[tipo]
    return [] if r["n"] <= cuantos else [f"resaltar: el paso no tiene {tipo} {r['n']}"]


def validar(r: Any, guion: Any = None) -> list[str]:
    """Lo que impide reproducir el recorrido absoluto `r` (vacío si nada): la forma exacta, los textos con las reglas de
    lo que se proyecta (sin plata, como todo lo de la presentación técnica), los topes y, con `guion`, que cada capítulo, paso, componente, inmersión y resaltado
    exista en el guion vigente. Pura: la usan la herramienta al crearlo y la pantalla al leerlo de la base."""
    if not isinstance(r, dict) or set(r) != {"id", "titulo", "escenas", "cierre"}:
        return ["el recorrido no tiene la forma"]
    out = []
    if not isinstance(r["id"], str) or not ID.fullmatch(r["id"]):
        out.append("el id del recorrido no vale")
    if not _texto(r["titulo"], MAX_TITULO):
        out.append("el título no se puede proyectar")
    escenas = r["escenas"]
    if not isinstance(escenas, list) or not 1 <= len(escenas) <= MAX_ESCENAS:
        return [*out, f"el recorrido lleva de 1 a {MAX_ESCENAS} escenas"]
    claves = {"capitulo", "paso", "panel", "visual", "resaltar", "frases", "sostener_ms"}
    for n, esc in enumerate(escenas, 1):
        if not isinstance(esc, dict) or set(esc) != claves:
            out.append(f"escena {n}: no tiene la forma")
            continue
        ci = guion.por_id(esc["capitulo"]) if guion is not None and isinstance(esc["capitulo"], str) else None
        if not isinstance(esc["capitulo"], str) or not ID_CAPITULO.fullmatch(esc["capitulo"]) or \
                (guion is not None and ci is None):
            out.append(f"escena {n}: el capítulo no existe")
            continue
        total = len(guion.capitulos[ci]["pasos"]) if ci is not None else 60
        pi = esc["paso"] - 1 if _entero(esc["paso"], 1, total) else None
        if pi is None:
            out.append(f"escena {n}: el paso no existe")
        if not isinstance(esc["panel"], bool):
            out.append(f"escena {n}: panel es verdadero o falso")
        out += [f"escena {n}: {x}" for x in _visual(esc["visual"], guion, ci)]
        if isinstance(esc["visual"], dict) and isinstance(esc["panel"], bool):
            out += [f"escena {n}: {x}" for x in _resaltar(esc["resaltar"], guion, ci, pi, esc)]
        frases = esc["frases"]
        if not isinstance(frases, list) or not 1 <= len(frases) <= MAX_FRASES or \
                not all(_texto(f, MAX_NARRACION) for f in frases) or \
                sum(len(f) for f in frases) + len(frases) - 1 > MAX_NARRACION:
            out.append(f"escena {n}: la narración no se puede proyectar")
        if not _entero(esc["sostener_ms"], 0, MAX_SOSTENER_MS):
            out.append(f"escena {n}: sostener va de 0 a 8 s")
    c = r["cierre"]
    if c is not None:
        if not isinstance(c, dict) or set(c) != {"puntos"} or not isinstance(c["puntos"], list) or \
                not 1 <= len(c["puntos"]) <= MAX_PUNTOS or not all(_texto(x, MAX_PUNTO) for x in c["puntos"]) or \
                sum(len(x) for x in c["puntos"]) > MAX_CIERRE:
            out.append("el cierre no se puede proyectar")
    if not out and bytes_de(r) > MAX_RECORRIDO_BYTES:
        out.append(f"el recorrido pesa más de {MAX_RECORRIDO_BYTES} bytes")
    return out
