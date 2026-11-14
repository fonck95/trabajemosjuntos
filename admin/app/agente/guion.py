"""El guion de la presentación técnica de la propuesta 2028–2031 (web/propuesta.html?modo=tecnica): lo que el asistente
sabe de cada capítulo y de cada paso para presentarla y explicarla (la herramienta `presentacion`,
`herramientas/interfaz.py`), y lo que puede mostrar en ella (las obras que enfoca la cámara, las fichas técnicas y las
inmersiones en los modelos del atlas).

Por qué está hecho así:

* El asistente del panel y los agentes por MCP muestran la presentación TÉCNICA: lo que se construye, dónde, cómo
  funciona y cómo se mide, sin costos ni financiación (esos van en la propuesta para la gestión, web/propuesta.html sin
  `modo`). Por eso el guion tampoco los trae: lo que no está en pantalla el modelo no lo explica.
* Lo genera `scripts/build_propuesta.py` (con `derivar`) a partir de lo mismo que lee la presentación
  (web/data/propuesta.json) y queda versionado aquí, en `propuesta_guion.json`: así lo tiene también el panel que se
  despliega aparte (Root Directory = admin), que no trae web/. Una prueba (test_agente_presentacion.py) lo compara con
  lo que se deriva de web/data/propuesta.json: si alguien cambia la propuesta y no lo regenera, falla.
* Son datos públicos de la propuesta, los mismos que se ven en pantalla: nada de la base de habitantes. Por eso no pasa
  por `minimizar`.
* Los capítulos van en el orden y con los nombres de `capsTecnica` en web/js/propuesta/main.js (la portada, los módulos
  en el orden de general.json y el cronograma de obra), y sus pasos son los de `pasosTecnicos`: los del módulo sin el de
  financiación, con las inmersiones de general.json (`tecnica.pasos`) detrás del paso que dicen y, al final, el de
  metas. El asistente y la presentación cuentan los pasos igual (la dirección `#salud/4` es el cuarto).
* Lo que tiene plata se quita con las mismas reglas que main.js (`sin_plata`, `cifra_tecnica`, `especificacion_tecnica`):
  un paréntesis con «$», la frase que lo lleve y, en una especificación, el tramo entre «·» o «;»; una cifra en pesos o
  en millones no se muestra. Una prueba con Node compara las dos implementaciones con cada texto de la propuesta.
* Cada paso trae lo que su panel muestra (`RENDER_TECNICA` de main.js, con los mismos títulos y textos de respaldo), en
  texto plano: sin HTML y sin los espacios que no se cortan ni las uniones de palabras (U+2060) que pone
  build_propuesta.py para el panel. Cada capítulo trae sus componentes (id, nombre y si la cámara los puede enfocar) y
  el guion, el catálogo de inmersiones del atlas: con eso la herramienta valida `visual` antes de tocar la pantalla.
* Nada se acorta: la herramienta le dice al modelo que explique «con esos datos (no invente otros)». El único tope es
  lo que pesa un paso para el modelo (`MAX_BYTES_PASO`): si una propuesta nueva lo pasa, `problemas` lo dice y
  build_propuesta.py --estricto falla, para decidir qué se saca en vez de cortar en silencio.
* Solo usa la biblioteca estándar: build_propuesta.py lo carga por su ruta, sin las dependencias del panel. El panel lo
  lee con `cargar` (con caché por la fecha del archivo; es lectura de disco: desde una corrutina va con
  `run_in_threadpool`).
"""
from __future__ import annotations

import html
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUTA = Path(__file__).with_name("propuesta_guion.json")
VERSION = 2
MODO = "tecnica"
# Lo que pesa a lo sumo un paso para el modelo (su JSON en UTF-8, como lo manda `Resultado.texto_para_modelo`): muy por
# debajo de `MAX_CONTENIDO` (40.000) de la herramienta. El más pesado, el cronograma de obra (los plazos de todos los
# componentes), pesa unos 9 KB
MAX_BYTES_PASO = 12000
MAX_PASOS = 60       # el tope de `paso` en la herramienta y en el navegador
# Los capítulos que no salen de `modulos`, con los nombres que tienen fijos en web/js/propuesta/main.js (`capsTecnica`)
FIJOS_ANTES = (("portada", "Portada", "Portada"),)
FIJOS_DESPUES = (("ruta", "Cronograma de obra", "Cronograma"),)
ID = re.compile(r"[a-z_]{2,40}")
ID_PASO = re.compile(r"[a-z0-9_]{1,40}")
# Los títulos fijos de los pasos que arma main.js (`pasosTecnicos`, `capsTecnica`) cuando general.json no trae otro
TITULO_METAS = "Lo que cambia y cómo se mide"
TITULO_CRONOGRAMA = "Cronograma de obra"


# ───────────────────────────── Texto plano ─────────────────────────────

_ETIQUETA = re.compile(r"<[^>]*>")
# Lo que build_propuesta.py pone para que el panel no parta una cifra (espacios que no se cortan, unión de palabras) y
# el guion blando de las palabras largas: en el guion son un espacio común o nada
_ESPACIOS_DUROS = str.maketrans({"\xa0": " ", "\U0000202f": " ", "\U00002007": " ", "\U00002060": None, "\xad": None})


def plano(v: Any) -> str:
    """Texto de una línea sin HTML ni entidades y sin los espacios que no se cortan. Entero: nunca se acorta."""
    if not isinstance(v, str):
        return ""
    t = html.unescape(_ETIQUETA.sub("", v)).translate(_ESPACIOS_DUROS)
    return " ".join(t.split())


def clave(v: Any) -> str:
    """Para comparar nombres: sin tildes, en minúsculas y con las palabras separadas por un espacio («Cómo se
    financia» → «como se financia»; «agro-industria» → «agro industria»)."""
    if not isinstance(v, str):
        return ""
    t = unicodedata.normalize("NFKD", v.translate(_ESPACIOS_DUROS))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


# ───────────────────────────── Sin plata (las mismas reglas de main.js) ─────────────────────────────

# Lo que delata plata en un texto: el signo de pesos o «millones de pesos»
PLATA = re.compile(r"\$|millones de pesos")
# Un paréntesis (sin otro adentro) que lleva plata, con el espacio de antes
_PARENTESIS = re.compile(r"\s*\([^()]*\$[^()]*\)")
# Dónde termina una frase: un punto, un signo de cierre de pregunta o de exclamación, espacio y una mayúscula, un signo
# de apertura, un paréntesis o una etiqueta (no un número: «Res. 3100» no parte)
_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«(<])")
# Los tramos de una especificación («100 casas · $6.801 M · 9 % de obra»)
_TRAMO = re.compile(r"\s+·\s+|;\s+")
_ANTES_DE_SIGNO = re.compile(r"\s+([,.;:])")
# La especificación cuyo nombre es de plata («Costo anual», «Tope del subsidio») no va, diga lo que diga
CLAVE_PLATA = re.compile(r"costo|valor|precio|subsidio|tope|presupuest|financ|cr[eé]dito|aporte|tarifa", re.I)


def _sin_parentesis(t: str) -> str:
    antes = None
    while antes != t:
        antes, t = t, _PARENTESIS.sub("", t)
    return t


def sin_plata(t: Any, tramos: bool = False) -> str:
    """El texto sin lo que tiene plata (`sinPlata` de main.js): los paréntesis con «$», los tramos entre «·» o «;» que
    la lleven (con `tramos`, las especificaciones) y las frases que la lleven. Lo demás queda igual, con su HTML."""
    if not isinstance(t, str):
        return ""
    if not PLATA.search(t):
        return t
    t = _sin_parentesis(t)
    if tramos:
        t = " · ".join(x for x in _TRAMO.split(t) if x.strip() and not PLATA.search(x))
    t = " ".join(f for f in _FRASE.split(t) if f.strip() and not PLATA.search(f))
    return _ANTES_DE_SIGNO.sub(r"\1", t).strip()


def cifra_tecnica(c: Any) -> dict | None:
    """Una cifra grande sin plata (`cifraTecnica` de main.js): no va si su valor o su rótulo hablan de pesos o de
    millones; el rótulo pierde los paréntesis con «$»."""
    if not isinstance(c, dict) or not isinstance(c.get("v"), str) or not c["v"].strip():
        return None
    rotulo = _sin_parentesis(c.get("l") or "") if isinstance(c.get("l"), str) else ""
    if PLATA.search(c["v"]) or PLATA.search(rotulo) or "millones" in rotulo.lower():
        return None
    return {**c, "l": _ANTES_DE_SIGNO.sub(r"\1", rotulo).strip()}


def especificacion_tecnica(e: Any) -> tuple[str, str] | None:
    """[nombre, valor] de una especificación sin plata (`especificacionTecnica` de main.js), o None si no queda nada."""
    if not isinstance(e, (list, tuple)) or len(e) != 2 or not all(isinstance(x, str) for x in e):
        return None
    if CLAVE_PLATA.search(e[0]) or PLATA.search(e[0]):
        return None
    v = sin_plata(e[1], tramos=True)
    return (e[0], v) if v else None


# ───────────────────────────── Los capítulos y los pasos de la presentación técnica ─────────────────────────────

def pasos_tecnicos(m: dict, tec: dict) -> list[dict]:
    """Los pasos de un módulo en la presentación técnica (`pasosTecnicos` de main.js): los suyos sin el de financiación,
    cada inmersión de `tec.pasos` detrás del paso que dice `despues_de` (o al final, si no está) y, si el módulo tiene
    metas, el paso de metas."""
    pasos = [p for p in m.get("pasos") or [] if isinstance(p, dict) and p.get("tipo") != "financiacion"]
    extra = (tec.get("pasos") or {}).get(m.get("id")) if isinstance(tec.get("pasos"), dict) else None
    for e in extra if isinstance(extra, list) else []:
        if not isinstance(e, dict):
            continue
        k = next((i for i, p in enumerate(pasos) if p.get("id") == e.get("despues_de")), None)
        pasos.insert(len(pasos) if k is None else k + 1, e)
    if m.get("metas"):
        metas = tec.get("metas") if isinstance(tec.get("metas"), dict) else {}
        pasos.append({"id": "metas", "tipo": "metas", "titulo": metas.get("titulo") or TITULO_METAS,
                      "texto": metas.get("texto") or ""})
    return pasos


def capitulos_tecnicos(datos: dict) -> list[dict]:
    """Los capítulos de la presentación técnica, en el orden de `capsTecnica` de main.js, cada uno con sus pasos."""
    tec = datos.get("tecnica") if isinstance(datos.get("tecnica"), dict) else {}
    tp = tec.get("portada") if isinstance(tec.get("portada"), dict) else {}
    portada = datos.get("portada") if isinstance(datos.get("portada"), dict) else {}
    cid, nombre, corto = FIJOS_ANTES[0]
    caps = [{**portada, **tp, "id": cid, "nombre": nombre, "corto": corto, "pasos": [
        {"id": "inicio", "tipo": "portada", "titulo": tp.get("titulo") or portada.get("titulo"),
         "texto": tp.get("texto") or "", "nota": tp.get("nota") or ""},
        *[p for p in portada.get("pasos") or [] if isinstance(p, dict) and p.get("tipo") != "portada"]]}]
    caps += [{**m, "pasos": pasos_tecnicos(m, tec)} for m in datos.get("modulos") or [] if isinstance(m, dict)]
    cr = tec.get("cronograma") if isinstance(tec.get("cronograma"), dict) else {}
    cid, nombre, corto = FIJOS_DESPUES[0]
    caps.append({"id": cid, "nombre": nombre, "corto": corto, "pasos": [
        {"id": "cronograma", "tipo": "cronograma", "titulo": cr.get("titulo") or TITULO_CRONOGRAMA,
         "texto": cr.get("texto") or "", "nota": cr.get("nota") or ""}]})
    return caps


# ───────────────────────────── Del JSON de la presentación al guion ─────────────────────────────

def _lista(v: Any) -> list[str]:
    return [x for x in (plano(sin_plata(x)) for x in (v if isinstance(v, list) else [])) if x]


def _cifras(v: Any) -> list[dict]:
    """Las cifras grandes sin plata (`cifras` de main.js): el valor, su rótulo y, si la trae, la fuente."""
    out = []
    for c in v if isinstance(v, list) else []:
        c = cifra_tecnica(c)
        if c and plano(c.get("v")):
            out.append({k: x for k, x in (("v", plano(c.get("v"))), ("l", plano(c.get("l"))),
                                          ("fuente", plano(c.get("fuente")))) if x})
    return out


def _leyenda(v: Any) -> list[str]:
    return [t for t in (plano(x.get("texto")) for x in (v if isinstance(v, list) else []) if isinstance(x, dict)) if t]


def _tipos(v: Any) -> list[str]:
    """Los nombres de los proyectos tipo y referentes, sin plata (`chipsTipo` de main.js)."""
    return [t for t in (plano(sin_plata(x.get("nombre"))) for x in (v if isinstance(v, list) else [])
                        if isinstance(x, dict)) if t]


def ficha_tecnica(x: dict) -> dict:
    """La ficha técnica de un componente (`fichaTecnica` de main.js): lo que hace, sus especificaciones sin plata, el
    proyecto tipo o referente, dónde y el plazo."""
    specs = [plano(f"{e[0]}: {e[1]}") for e in map(especificacion_tecnica, x.get("especificaciones") or []) if e]
    out = {"id": x.get("id"), "nombre": plano(x.get("nombre")), "resumen": plano(sin_plata(x.get("resumen"))),
           "descripcion": plano(sin_plata(x.get("descripcion"))), "especificaciones": [e for e in specs if e],
           "proyectos_tipo": _tipos(x.get("proyecto_tipo")), "ubicacion": plano(sin_plata(x.get("ubicacion"))),
           "plazo": plano(sin_plata(x.get("plazo"))), "enfoque": bool(x.get("enfoque"))}
    return {k: v for k, v in out.items() if v not in ("", [], None)}


def meta_tecnica(x: Any) -> str:
    """Una meta como la muestra el paso de metas: «indicador: base → meta» (sin plata; sin indicador, nada)."""
    if not isinstance(x, dict) or not isinstance(x.get("indicador"), str) or PLATA.search(x["indicador"]):
        return ""
    base, meta = plano(sin_plata(x.get("base"))) or "—", plano(sin_plata(x.get("meta"))) or "—"
    return plano(f"{x['indicador']}: {base} → {meta}")


def bytes_de(paso: dict) -> int:
    """Lo que pesa un paso para el modelo: su JSON en UTF-8 (como lo manda `Resultado.texto_para_modelo`)."""
    return len(json.dumps(paso, ensure_ascii=False).encode("utf-8"))


# El título de un paso que no trae el suyo, según su tipo (los respaldos de `RENDER_TECNICA` en main.js)
TITULO_POR_TIPO = {"componentes": "Qué se construye", "metas": TITULO_METAS, "cronograma": TITULO_CRONOGRAMA}


def _paso(datos: dict, c: dict, p: dict, inmersiones: dict[str, dict]) -> dict:
    """Lo que muestra el panel en el paso `p` del capítulo `c` (`RENDER_TECNICA` de main.js), con sus mismos respaldos."""
    tipo = p.get("tipo") if isinstance(p.get("tipo"), str) else "texto"
    x = next((k for k in c.get("componentes") or [] if isinstance(k, dict) and k.get("id") == p.get("componente")),
             None) if tipo == "componente" else None
    respaldo = {"portada": c.get("titulo"), "portadilla": c.get("lema"), "componente": (x or {}).get("nombre"),
                "texto": c.get("nombre")}.get(tipo, TITULO_POR_TIPO.get(tipo))
    titulo = plano(p.get("titulo") or respaldo) or plano(c.get("nombre"))
    texto = p.get("texto") or {"portada": c.get("lema"), "portadilla": c.get("problema"),
                               "componente": (x or {}).get("descripcion")}.get(tipo)
    out: dict[str, Any] = {"id": p.get("id"), "tipo": tipo, "titulo": titulo, "texto": plano(sin_plata(texto))}
    cifras = _cifras(p.get("cifras") or (c.get("cifras") if tipo in ("portada", "portadilla") else None))
    if cifras:
        out["cifras"] = cifras
    if x:
        ficha = ficha_tecnica(x)
        if not p.get("texto"):
            ficha.pop("descripcion", None)   # sin texto propio, el texto del paso ya es la descripción
        out["componente"] = ficha
    if tipo == "portada":
        out["modulos"] = [{k: v for k, v in (("id", m.get("id")), ("nombre", plano(m.get("nombre"))),
                                             ("lema", plano(m.get("lema"))),
                                             ("componentes", len(m.get("componentes") or []))) if v}
                          for m in datos.get("modulos") or [] if isinstance(m, dict)]
    elif tipo == "portadilla":
        propuesta = plano(sin_plata(c.get("propuesta")))
        if propuesta:
            out["propuesta"] = propuesta
    elif tipo == "componentes":
        out["componentes"] = [{k: v for k, v in (("nombre", plano(k.get("nombre"))),
                                                 ("resumen", plano(sin_plata(k.get("resumen")))),
                                                 ("plazo", plano(sin_plata(k.get("plazo"))))) if v}
                              for k in c.get("componentes") or [] if isinstance(k, dict)]
    elif tipo == "comparacion":
        for lado in ("antes", "despues"):
            d = p.get(lado) if isinstance(p.get(lado), dict) else {}
            t = " · ".join(v for v in (plano(d.get("titulo")), plano(sin_plata(d.get("texto")))) if v)
            if t:
                out[lado] = t
    elif tipo == "inmersion":
        i = inmersiones.get(p.get("inmersion")) or {}
        out["inmersion"] = {k: v for k, v in (("id", p.get("inmersion")), ("nombre", plano(i.get("nombre"))),
                                              ("muestra", plano(i.get("texto")))) if v}
    elif tipo == "metas":
        metas = [t for t in map(meta_tecnica, c.get("metas") or []) if t]
        if metas:
            out["metas"] = metas
    elif tipo == "cronograma":
        out["obras"] = [{"modulo": plano(m.get("nombre")), "componentes": [
            plano(f"{k.get('nombre')}: {sin_plata(k.get('plazo'))}") for k in m.get("componentes") or []
            if isinstance(k, dict) and plano(sin_plata(k.get("plazo")))]}
            for m in datos.get("modulos") or [] if isinstance(m, dict)]
    lista = _lista(p.get("lista"))
    if lista:
        out["lista"] = lista
    nota = plano(sin_plata(p.get("nota")))
    if nota:
        out["nota"] = nota
    leyenda = _leyenda(p.get("leyenda"))
    if leyenda:
        out["leyenda"] = leyenda
    return out


def derivar(datos: dict) -> dict:
    """El guion de la presentación técnica a partir de web/data/propuesta.json (lo que arma build_propuesta.py):
    capítulos en el orden de main.js, cada uno con sus pasos y sus componentes, y el catálogo de inmersiones del atlas.
    Siempre el mismo resultado para los mismos datos (sin fechas ni nada que cambie solo)."""
    tec = datos.get("tecnica") if isinstance(datos.get("tecnica"), dict) else {}
    catalogo = [i for i in tec.get("inmersiones") or [] if isinstance(i, dict) and isinstance(i.get("id"), str)]
    inmersiones = {i["id"]: i for i in catalogo}
    capitulos = []
    for c in capitulos_tecnicos(datos):
        cap: dict[str, Any] = {"id": c["id"], "nombre": plano(c.get("nombre")),
                               "corto": plano(c.get("corto") or c.get("nombre"))}
        lema = plano(c.get("lema") or c.get("subtitulo"))
        if lema:
            cap["lema"] = lema
        comps = [k for k in c.get("componentes") or [] if isinstance(k, dict) and isinstance(k.get("id"), str)]
        if comps:
            # la ficha técnica de cada uno: la herramienta la devuelve cuando el asistente la muestra (detalle) o la
            # enfoca, para que explique con esos datos
            cap["componentes"] = [{**ficha_tecnica(k), "enfoque": bool(k.get("enfoque"))} for k in comps]
        cap["pasos"] = [_paso(datos, c, p, inmersiones) for p in c["pasos"]]
        capitulos.append(cap)
    return {"version": VERSION, "modo": MODO, "fuente": "web/data/propuesta.json",
            "inmersiones": [{"id": i["id"], "nombre": plano(i.get("nombre")), "muestra": plano(i.get("texto"))}
                            for i in catalogo],
            "capitulos": capitulos}


def problemas(g: dict) -> list[str]:
    """Lo que impediría usar el guion (lo revisa build_propuesta.py antes de escribirlo y `Guion.desde` al cargarlo):
    ids de capítulo, de paso, de componente o de inmersión que no cumplen la forma que aceptan la herramienta y el
    navegador, repetidos, capítulos con más pasos que el tope, un paso que pesa más de `MAX_BYTES_PASO` o que lleva a
    una inmersión que no está en el catálogo."""
    out = []
    caps = g.get("capitulos") if isinstance(g, dict) else None
    if not isinstance(caps, list) or not caps:
        return ["el guion no tiene capítulos"]
    inm = g.get("inmersiones") if isinstance(g.get("inmersiones"), list) else []
    ids_inm = [i.get("id") if isinstance(i, dict) else None for i in inm]
    for i in ids_inm:
        if not isinstance(i, str) or not ID_PASO.fullmatch(i):
            out.append(f"inmersión con un id que no es de letras minúsculas, números o «_»: {i!r}")
    if len(set(map(str, ids_inm))) != len(ids_inm):
        out.append("ids de inmersión repetidos")
    vistos = set()
    for c in caps:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not ID.fullmatch(cid):
            out.append(f"capítulo con un id que no es de 2 a 40 letras minúsculas o «_»: {cid!r}")
            continue
        if cid in vistos:
            out.append(f"capítulo repetido: {cid}")
        vistos.add(cid)
        comps = c.get("componentes") if isinstance(c.get("componentes"), list) else []
        ids_c = [k.get("id") if isinstance(k, dict) else None for k in comps]
        for k in ids_c:
            if not isinstance(k, str) or not ID_PASO.fullmatch(k):
                out.append(f"{cid}: componente con un id que no es de letras minúsculas, números o «_»: {k!r}")
        if len(set(map(str, ids_c))) != len(ids_c):
            out.append(f"{cid}: ids de componente repetidos")
        pasos = c.get("pasos")
        if not isinstance(pasos, list) or not 1 <= len(pasos) <= MAX_PASOS:
            out.append(f"{cid}: debe tener de 1 a {MAX_PASOS} pasos")
            continue
        ids = [p.get("id") if isinstance(p, dict) else None for p in pasos]
        for pid in ids:
            if not isinstance(pid, str) or not ID_PASO.fullmatch(pid):
                out.append(f"{cid}: paso con un id que no es de letras minúsculas, números o «_»: {pid!r}")
        if len(set(map(str, ids))) != len(ids):
            out.append(f"{cid}: ids de paso repetidos")
        for p in pasos:
            if isinstance(p, dict) and not p.get("titulo"):
                out.append(f"{cid}/{p.get('id')}: paso sin título")
            elif isinstance(p, dict) and bytes_de(p) > MAX_BYTES_PASO:
                out.append(f"{cid}/{p.get('id')}: el paso pesa {bytes_de(p)} bytes (el tope es {MAX_BYTES_PASO})")
            if isinstance(p, dict) and p.get("tipo") == "inmersion" and \
                    (p.get("inmersion") or {}).get("id") not in ids_inm:
                out.append(f"{cid}/{p.get('id')}: lleva a una inmersión que no está en el catálogo")
    return out


# ───────────────────────────── El guion en el panel ─────────────────────────────

@dataclass(frozen=True)
class Resolucion:
    """El capítulo que se pidió por id o por nombre: su índice, o None con los candidatos (ambiguo o inexistente)."""
    indice: int | None
    candidatos: tuple[int, ...] = ()


@dataclass(frozen=True)
class Guion:
    capitulos: tuple[dict, ...]
    inmersiones: tuple[dict, ...] = ()

    @classmethod
    def desde(cls, datos: Any) -> "Guion":
        malos = problemas(datos)
        if malos:
            raise ValueError("Guion de la presentación inválido: " + "; ".join(malos[:5]))
        return cls(tuple(datos["capitulos"]), tuple(datos.get("inmersiones") or ()))

    def componentes(self, ci: int) -> list[dict]:
        """Los componentes del capítulo `ci` (id, nombre y si la cámara los puede enfocar); [] si no tiene."""
        return list(self.capitulos[ci].get("componentes") or [])

    def componente(self, ci: int, texto: Any) -> dict | None:
        """El componente del capítulo `ci` por su id o su nombre (sin tildes ni mayúsculas), o None."""
        k = clave(texto)
        if not k:
            return None
        return next((x for x in self.componentes(ci) if k in (clave(x["id"]), clave(x["nombre"]))), None)

    def inmersion(self, texto: Any) -> dict | None:
        """La inmersión del catálogo por su id o su nombre, o None."""
        k = clave(texto)
        if not k:
            return None
        return next((i for i in self.inmersiones if k in (clave(i["id"]), clave(i.get("nombre")))), None)

    def __len__(self) -> int:
        return len(self.capitulos)

    def total_pasos(self) -> int:
        return sum(len(c["pasos"]) for c in self.capitulos)

    def por_id(self, cid: Any) -> int | None:
        return next((i for i, c in enumerate(self.capitulos) if c["id"] == cid), None) if isinstance(cid, str) else None

    def buscar(self, texto: str) -> Resolucion:
        """El capítulo por su id o su nombre (el largo o el corto), sin importar tildes ni mayúsculas. Si no hay uno
        igual, los que tienen todas las palabras pedidas al comienzo de alguna de las suyas («agua» → Aguas): uno solo
        es ese; varios, ambiguo."""
        k = clave(texto)
        if not k:
            return Resolucion(None)
        exactos = [i for i, c in enumerate(self.capitulos)
                   if k in {clave(c["id"]), clave(c["nombre"]), clave(c.get("corto"))}]
        if len(exactos) == 1:
            return Resolucion(exactos[0])
        if exactos:
            return Resolucion(None, tuple(exactos))
        pedidas = k.split()
        parecidos = []
        for i, c in enumerate(self.capitulos):
            suyas = set(clave(" ".join((c["id"], c["nombre"], c.get("corto") or ""))).split())
            if all(any(s.startswith(p) for s in suyas) for p in pedidas):
                parecidos.append(i)
        if len(parecidos) == 1:
            return Resolucion(parecidos[0])
        return Resolucion(None, tuple(parecidos))

    def paso(self, ci: int, paso: int | str | None) -> int | None:
        """El índice (desde 0) del paso `paso` del capítulo `ci`: su número desde 1 o su id; None si no existe."""
        pasos = self.capitulos[ci]["pasos"]
        if paso is None:
            return 0
        if isinstance(paso, str) and paso.strip().isdigit():
            paso = int(paso.strip())
        if isinstance(paso, int) and not isinstance(paso, bool):
            return paso - 1 if 1 <= paso <= len(pasos) else None
        return next((i for i, p in enumerate(pasos) if p["id"] == paso), None)

    def vecino(self, ci: int, pi: int, d: int) -> tuple[int, int]:
        """El paso siguiente (`d` = 1) o el anterior (-1), como `vecino` de main.js: al terminar un capítulo se pasa al
        primero del siguiente (o al último del anterior); en el último paso de la presentación (o en el primero) se
        queda."""
        n = len(self.capitulos[ci]["pasos"])
        pi += d
        if pi >= n:
            if ci < len(self.capitulos) - 1:
                ci, pi = ci + 1, 0
            else:
                pi = n - 1
        if pi < 0:
            if ci > 0:
                ci -= 1
                pi = len(self.capitulos[ci]["pasos"]) - 1
            else:
                pi = 0
        return ci, pi

    def especificaciones(self, ci: int, componente: Any) -> list[str]:
        """Los nombres de las especificaciones sin plata de un componente del capítulo (la parte antes de «:», en el orden
        de su hoja técnica: la del panel en su paso y la de su ficha)."""
        x = self.componente(ci, componente) if isinstance(componente, str) else None
        return [e.split(": ", 1)[0] for e in (x or {}).get("especificaciones") or []]

    def resaltable(self, ci: int, pi: int) -> dict:
        """Lo que un recorrido puede señalar en el paso `pi` del capítulo `ci` (`resaltar` de main.js): cuántas cifras,
        puntos (la lista o, en el de metas, las metas) y filas de la leyenda muestra, los nombres de las especificaciones
        de la hoja del panel (en un paso de componente) y las tarjetas de componentes (en el paso de componentes)."""
        p = self.capitulos[ci]["pasos"][pi]
        comp = p.get("componente") if isinstance(p.get("componente"), dict) else {}
        out = {"cifras": len(p.get("cifras") or []),
               "puntos": len(p.get("metas") or []) if p.get("tipo") == "metas" else len(p.get("lista") or []),
               "leyenda": len(p.get("leyenda") or []),
               "especificaciones": [e.split(": ", 1)[0] for e in comp.get("especificaciones") or []]}
        if p.get("tipo") == "componentes":
            out["componentes"] = [x["id"] for x in self.componentes(ci)]
        return out

    def capitulo_para_leer(self, ci: int, tope: int = 32000) -> dict:
        """Todo lo de un capítulo para armar un recorrido narrado, de una vez: sus pasos (con lo que muestra cada uno y
        lo que se puede resaltar), la ficha técnica de cada componente (una sola vez: el paso dice cuál con su id) y el
        catálogo de inmersiones. Si pasa de `tope` bytes, las fichas van sin descripción ni referentes."""
        c = self.capitulos[ci]
        pasos = []
        for pi, p in enumerate(c["pasos"]):
            x = {k: v for k, v in p.items() if k != "componente"}
            if isinstance(p.get("componente"), dict):
                x["componente"] = p["componente"].get("id")
            if isinstance(p.get("inmersion"), dict):
                x["inmersion"] = p["inmersion"].get("id")
            pasos.append({"n": pi + 1, **x, "resaltable": self.resaltable(ci, pi)})
        fichas = [{**{k: v for k, v in x.items() if k != "enfoque"}, "lugar_en_la_maqueta": bool(x.get("enfoque"))}
                  for x in self.componentes(ci)]
        out = {"capitulo": {k: c[k] for k in ("id", "nombre", "lema") if c.get(k)}, "pasos": pasos,
               "componentes": fichas,
               "inmersiones": [{"id": i["id"], "nombre": i.get("nombre"), "muestra": i.get("muestra")}
                               for i in self.inmersiones]}
        if len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > tope:
            out["componentes"] = [{k: v for k, v in x.items() if k not in ("descripcion", "proyectos_tipo")}
                                  for x in fichas]
            out["recortado"] = "Las fichas van sin descripción ni referentes para caber: pídalas con visual detalle."
        return out

    def indice(self) -> dict:
        """Capítulos con su id, nombre, los títulos de sus pasos y los ids de sus componentes (los que la cámara enfoca
        marcados), y el catálogo de inmersiones: lo que el modelo necesita para elegir, en pocos KB."""
        caps = []
        for c in self.capitulos:
            cap = {"id": c["id"], "nombre": c["nombre"], "pasos": [p["titulo"] for p in c["pasos"]]}
            if c.get("componentes"):
                cap["componentes"] = [x["id"] + ("" if x.get("enfoque") else " (sin lugar en la maqueta)")
                                      for x in c["componentes"]]
            caps.append(cap)
        return {"capitulos": caps, "total_pasos": self.total_pasos(),
                "inmersiones": [{"id": i["id"], "nombre": i.get("nombre")} for i in self.inmersiones]}


_cache: tuple[tuple, Guion] | None = None
_candado = threading.Lock()


def cargar(ruta: Path | None = None) -> Guion | None:
    """El guion versionado (`propuesta_guion.json`), o None si no está. Se vuelve a leer solo si el archivo cambió
    (fecha y tamaño). Un archivo dañado lanza ValueError: es un error del despliegue, no del modelo."""
    global _cache
    ruta = ruta or RUTA
    try:
        st = ruta.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    marca = (str(ruta), st.st_mtime_ns, st.st_size)
    with _candado:
        if _cache is not None and _cache[0] == marca:
            return _cache[1]
    try:
        g = Guion.desde(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"No se pudo leer el guion de la presentación ({type(e).__name__})") from None
    with _candado:
        _cache = (marca, g)
    return g


def hay_guion() -> bool:
    """¿Está el guion en este despliegue? (`disponible` de la herramienta: sin él no se ofrece)."""
    return RUTA.is_file()
