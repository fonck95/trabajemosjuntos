"""El plan guiado de la presentación técnica (por dentro, el recorrido narrado): lo que el agente presentador (el
asistente del panel o un agente por MCP) arma en UNA llamada (`presentacion`, op `recorrido`) y la pantalla ejecuta
sola, paso a paso, mostrando MIENTRAS explica.

Hacia el modelo y la persona se llama «plan» y «pasos»; aquí siguen `recorrido` y `escenas` (un «paso» ya es otra cosa
en el guion: el de un capítulo). Un recorrido son de 1 a MAX_ESCENAS escenas. Cada escena es una idea: lo que se dice
(sus frases, que se proyectan en el subtítulo y, si la voz está encendida, se leen en voz alta) y lo que ocurre MIENTRAS
se dice: el paso, «Solo 3D», la cámara (un encuadre con nombre o su rumbo, su elevación y su acercamiento, a qué apunta
y cómo viaja durante la frase: `mover`), las piezas de la maqueta que se muestran, se ocultan o se aíslan y las partes
que se les quitan, la obra enfocada, la ficha técnica, hoy o con el proyecto, un modelo del atlas, la animación del
paso (`animar`) y un resaltado de lo que se nombra. Nada espera a que la imagen se asiente (salvo la carga de un modelo
del atlas). Al final, un cierre de hasta tres ideas que queda en la sala con «¿Preguntas?».

Aquí está su forma absoluta (la que viaja al navegador y se guarda con la pantalla, `app/pantalla.py`): cada escena con
su estado completo (no un cambio sobre la anterior), así cualquier pantalla puede empezar, reanudar o saltar a cualquier
escena. Y las reglas que la validan, puras: `validar` corre al crearla (`agente/herramientas/interfaz.py`) y cada vez que
se lee de la base, contra el guion vigente. Los mismos topes, listas y tiempos están en web/js/propuesta/mando.js, en
web/js/agente-presentacion.js y en web/js/reproductor.js; una prueba los compara. `mover` y `animar` son acciones de
la escena, no estado: lo que queda de una escena (`estado_de_escena`) no las trae.

Solo usa la biblioteca estándar y `app/proyectable.py`: no importa nada del panel."""
from __future__ import annotations

import json
import re
from typing import Any

from .proyectable import texto_proyectable

MAX_ESCENAS = 12
MAX_FRASES = 3
MAX_NARRACION = 220   # una escena: juntas sus frases (el tope de la explicación)
MAX_TITULO = 80
MAX_PUNTO = 80
MAX_PUNTOS = 3
MAX_CIERRE = 200      # los puntos juntos: con « · » entre ellos el estado no pasa de 220
MAX_SUGERENCIA = 60
MAX_SUGERENCIAS = 3
MAX_SOSTENER_MS = 8000
# (doce escenas con lo visual completo, sus listas llenas y dos frases largas cada una pesan menos de 20 KB)
MAX_RECORRIDO_BYTES = 24576
# Doce pasos de dos frases largas duran unos 4 min y 10 s: con el tope de antes (4 min, para 8 escenas) no cabían
MAX_DURACION_MS = 300_000
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
# (`parcial`: parte de lo pedido no se pudo mostrar; la presentación lo descartó y aplicó lo demás)
AVISOS = ("atlas", "resaltar", "asiento", "voz", "parcial")
DESTINOS = ("vista", "pantalla_off")
CAMARAS = ("paso", "aerea", "oblicua", "rasante", "cerca", "lejos")
# Lo visual de una escena, en el orden de siempre (`VISUAL` de mando.js, del puente y de app/pantalla.py): el estado
# completo, con lo que vale en cada paso. `elevacion` (grados sobre el horizonte) y `zoom` (1 = el encuadre del paso; 2,
# el doble de cerca) mandan sobre lo que implique `camara`; `mirar` apunta la cámara a una pieza o a un componente con
# lugar SIN cambiar las capas; `mostrar`, `ocultar` y `aislar` son piezas de la maqueta del capítulo (`Guion.piezas`) y
# `sin`, partes quitadas («torre.cubierta»). Las listas, de 0 a MAX_LISTA, sin repetir
VISUAL = ("enfoque", "camara", "rumbo", "elevacion", "zoom", "mirar", "girar", "comparar", "detalle", "inmersion",
          "mostrar", "ocultar", "aislar", "sin")
VISUAL_INICIAL = {"enfoque": None, "camara": "paso", "rumbo": None, "elevacion": None, "zoom": None, "mirar": None,
                  "girar": False, "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": [],
                  "ocultar": [], "aislar": None, "sin": []}
LISTAS = ("mostrar", "ocultar", "sin")
MAX_LISTA = 8
ELEVACION = (8, 85)
ZOOM = (0.3, 3)
# `mover` (no es estado): lo que hace la cámara mientras dura la frase. `giro`: los grados que gira alrededor de lo que
# mira (positivo, el rumbo crece); `zoom` y `elevacion`: con cuáles TERMINA. None, o al menos una de las tres
MOVER = ("giro", "zoom", "elevacion")
GIRO = (-360, 360)
# Un recorrido nuevo se narra en la pantalla en off si llega a tiempo; uno viejo (la pantalla se abrió después) se aplica
# en silencio en su última escena. Y una pantalla que se recargó a mitad reanuda si su avance es reciente
VIGENCIA_RECORRIDO_S = 90
REANUDAR_S = 20
ID = re.compile(r"[0-9a-f]{12}")
ID_CAPITULO = re.compile(r"[a-z_]{2,40}")
ID_PIEZA = re.compile(r"[a-z0-9_]{1,40}")
ID_PARTE = re.compile(r"[a-z0-9_]{1,40}\.[a-z0-9_]{1,40}")   # la parte de una pieza: «pieza.parte»
# Los tiempos del reproductor (`reproductor.js` exporta los mismos): la espera antes del primer paso de un plan nuevo
# (el chat lo muestra entero antes de empezar), el respiro antes de la voz, la lectura (por caracteres, con un piso y
# un techo), lo que se sostiene y el cierre. La escena ya no espera a que la imagen se asiente (la cámara viaja
# mientras se narra): ASIENTO_MS y ASIENTO_ATLAS_MS solo sirven para estimar la duración (lo que tarda en responder la
# presentación al cambiar de paso o de capítulo, y la carga de un modelo del atlas, lo único que se espera)
PREVIA_MS = 1800
ASIENTO_MS = {"mismo": 0, "paso": 400, "capitulo": 600}
ASIENTO_ATLAS_MS = 4000
RESPIRO_MS = 350
ENTRE_FRASES_MS = 250
SOSTENER_MS = 1300
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


def narracion_ms(frases: list[str]) -> int:
    """Lo que dura la narración de una escena (`narracionMs` de reproductor.js: el `ms` de la orden `escena`, lo que la
    cámara tarda en llegar adonde termina): la lectura de sus frases y las pausas entre ellas."""
    return sum(lectura_ms(f) for f in frases) + ENTRE_FRASES_MS * max(0, len(frases) - 1)


def duracion_ms(r: dict, guion: Any = None) -> int:
    """La duración estimada de un recorrido absoluto (la que dice la herramienta y la tarjeta del chat), con la espera
    antes del primer paso de un plan nuevo."""
    total, anterior = PREVIA_MS, None
    for esc in r["escenas"]:
        cambio = "capitulo" if not anterior or anterior["capitulo"] != esc["capitulo"] else \
            "paso" if anterior["paso"] != esc["paso"] else "mismo"
        total += ASIENTO_MS[cambio] + (ASIENTO_ATLAS_MS if abre_atlas(esc, anterior, guion) else 0) + RESPIRO_MS
        total += narracion_ms(esc["frases"]) + esc["sostener_ms"]
        anterior = esc
    if r.get("cierre"):
        total += lectura_ms("En resumen. " + ". ".join(r["cierre"]["puntos"])) + CIERRE_SOSTENER_MS
    return total + PREGUNTAS_MS + FIN_MS


def visual_inicial() -> dict:
    """Lo visual de un paso recién abierto, con sus listas propias (VISUAL_INICIAL las comparte: no se tocan)."""
    return copia_visual(VISUAL_INICIAL)


def copia_visual(v: dict) -> dict:
    """Lo visual copiado: las listas (mostrar, ocultar, sin) no se comparten entre escenas."""
    return {k: list(x) if isinstance(x, list) else x for k, x in v.items()}


def estado_de_escena(esc: dict) -> dict:
    """Los campos de la pantalla (`pantalla.CAMPOS`) donde queda una escena: su paso, «Solo 3D» y lo visual, sin
    explicación ni índice ni fichas abiertos. `mover` y `animar` no son estado: el movimiento y la animación de la
    escena ya pasaron (quedan en None y False; `baseDeEscena` de vistas/presentacion.js hace lo mismo)."""
    return {"capitulo": esc["capitulo"], "paso": esc["paso"], "explicacion": None, "panel": esc["panel"],
            "indice": False, "fichas": False, **copia_visual(esc["visual"]), "mover": None, "animar": False}


def al_dia(r: Any) -> Any:
    """Un recorrido guardado antes del plan guiado (sus escenas sin `mover` ni `animar`, lo visual con siete partes),
    con lo que le falta en lo del paso: así el que estaba en la base al desplegar se sigue pudiendo cerrar, reanudar o
    volver a reproducir. Lo demás queda igual (lo dice `validar`); el que ya está al día vuelve tal cual."""
    if not isinstance(r, dict) or not isinstance(r.get("escenas"), list):
        return r
    escenas = []
    for esc in r["escenas"]:
        if isinstance(esc, dict) and isinstance(esc.get("visual"), dict):
            esc = {**esc, "visual": {**visual_inicial(), **esc["visual"]}, "mover": esc.get("mover"),
                   "animar": esc.get("animar", False)}
        escenas.append(esc)
    return {**r, "escenas": escenas}


def bytes_de(r: Any) -> int:
    return len(json.dumps(r, ensure_ascii=False).encode("utf-8"))


def _entero(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def zoom_valido(v: Any) -> bool:
    """De 0,3 a 3 con dos decimales a lo sumo (`zoomValido` del puente): 1 es el encuadre del paso; 2, el doble de cerca."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and ZOOM[0] <= v <= ZOOM[1] and \
        abs(v * 100 - round(v * 100)) < 1e-6


def _lista(v: Any, forma: re.Pattern) -> bool:
    return isinstance(v, list) and len(v) <= MAX_LISTA and all(isinstance(x, str) and forma.fullmatch(x) for x in v) \
        and len(set(v)) == len(v)


def mover_valido(m: Any) -> bool:
    """None, o {giro?, zoom?, elevacion?} con al menos una parte y cada una en su rango."""
    if m is None:
        return True
    if not isinstance(m, dict) or not m or set(m) - set(MOVER):
        return False
    return ("giro" not in m or _entero(m["giro"], *GIRO)) and ("zoom" not in m or zoom_valido(m["zoom"])) and \
        ("elevacion" not in m or _entero(m["elevacion"], *ELEVACION))


def _texto(v: Any, maximo: int) -> bool:
    if not isinstance(v, str):
        return False
    try:
        return texto_proyectable(v, maximo) == v
    except ValueError:
        return False


def _visual(v: Any, guion: Any, ci: int | None) -> list[str]:
    if not isinstance(v, dict) or set(v) != set(VISUAL):
        return ["lo visual no tiene sus partes"]
    out = []
    comps = {x["id"]: x for x in guion.componentes(ci)} if guion is not None and ci is not None else None
    piezas = {x["id"]: {p["id"] for p in x["partes"]} for x in guion.piezas(ci)} \
        if guion is not None and ci is not None else None
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
    if v["elevacion"] is not None and not _entero(v["elevacion"], *ELEVACION):
        out.append(f"la elevación va de {ELEVACION[0]} a {ELEVACION[1]}")
    if v["zoom"] is not None and not zoom_valido(v["zoom"]):
        out.append("el zoom va de 0,3 a 3")
    x = v["mirar"]
    if x is not None:
        if not isinstance(x, str) or not ID_PIEZA.fullmatch(x):
            out.append("mirar no es un id")
        elif piezas is not None and x not in piezas and not (comps.get(x) or {}).get("enfoque"):
            out.append(f"mirar «{x}» no es una pieza ni un componente con lugar en la maqueta del capítulo")
    for k in ("mostrar", "ocultar"):
        if not _lista(v[k], ID_PIEZA):
            out.append(f"{k} no es una lista de hasta {MAX_LISTA} piezas sin repetir")
        elif piezas is not None and any(x not in piezas for x in v[k]):
            out.append(f"{k}: «{next(x for x in v[k] if x not in piezas)}» no es una pieza de la maqueta del capítulo")
    x = v["aislar"]
    if x is not None:
        if not isinstance(x, str) or not ID_PIEZA.fullmatch(x):
            out.append("aislar no es un id")
        elif piezas is not None and x not in piezas:
            out.append(f"aislar «{x}» no es una pieza de la maqueta del capítulo")
    if not _lista(v["sin"], ID_PARTE):
        out.append(f"sin no es una lista de hasta {MAX_LISTA} partes («pieza.parte») sin repetir")
    elif piezas is not None:
        malas = [x for x in v["sin"] if x.split(".")[1] not in piezas.get(x.split(".")[0], ())]
        if malas:
            out.append(f"sin: «{malas[0]}» no es una parte de una pieza del capítulo")
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
    lo que se proyecta (sin plata, como todo lo de la presentación técnica), los topes y, con `guion`, que cada capítulo,
    paso, componente, pieza de la maqueta, parte, inmersión y resaltado exista en el guion vigente. Pura: la usan la
    herramienta al crearlo (ya compuesto: lo opcional que no resolvía se descartó antes, con su aviso) y la pantalla al
    leerlo de la base."""
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
    claves = {"capitulo", "paso", "panel", "visual", "resaltar", "mover", "animar", "frases", "sostener_ms"}
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
        if isinstance(esc["visual"], dict) and set(esc["visual"]) == set(VISUAL) and isinstance(esc["panel"], bool):
            out += [f"escena {n}: {x}" for x in _resaltar(esc["resaltar"], guion, ci, pi, esc)]
        if not mover_valido(esc["mover"]):
            out.append(f"escena {n}: mover no tiene la forma (giro, zoom o elevacion)")
        if not isinstance(esc["animar"], bool):
            out.append(f"escena {n}: animar es verdadero o falso")
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
