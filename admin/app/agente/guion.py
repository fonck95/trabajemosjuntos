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
* Cada capítulo trae también su `maqueta`: las piezas de la maqueta 3D que el plan guiado puede mostrar, ocultar o
  aislar, y las partes que se les pueden quitar (`tecnica.maqueta` de general.json), solo con su id y su nombre. Las
  capas, los grupos y los nodos de cada pieza no vienen: son de la presentación (visual.js), al modelo no le sirven.
  Cuando la pieza es un componente del capítulo lleva su mismo id. Si la propuesta no trae catálogo, el capítulo queda
  sin `maqueta` y la herramienta descarta con un aviso lo que se pida de ella.
* Cada inmersión del catálogo trae sus `controles`: los de adentro del modelo del atlas que el plan y la op `visual`
  accionan con `simular` (los deslizadores, las opciones y los botones del simulador sísmico, los niveles del
  recorrido, las herramientas del modelo BIM…: data/propuesta/simulaciones.json, que build_propuesta.py revisa y copia
  a `tecnica.inmersiones`). Cada uno con su id, su nombre, su tipo (accion, numero, opcion o si_no), su rango o sus
  opciones y una frase de ayuda: el modelo los pide por id o por nombre y la herramienta los resuelve aquí
  (`Guion.control`). Una inmersión sin controles los trae vacíos.
* La maqueta 3D también tiene los suyos (`maqueta` del guion, arriba, con la forma de una inmersión pero fuera de
  `inmersiones`: la clave «maqueta» de simulaciones.json, que build_propuesta.py copia a `tecnica.simulaciones_maqueta`):
  la hora del día, el día entero, las luces y el partido en la cancha. `simular` los acciona cuando no hay un modelo del
  atlas a la vista. Un control puede valer solo en unos capítulos (`capitulos`: el partido, en urbanismo);
  `Guion.controles(MAQUETA, capítulo)` da los de ese capítulo, sin esa clave.
* Un paso puede traer su `narracion`: la frase muy resumida, escrita a mano, que dice la presentación automática en
  ese paso (`tecnica.narracion[capítulo][id del paso]` de general.json; app/automatica.py), con la voz de la
  presentación (`lenguaje.py`: hoy la trae cada paso). Es opcional: sin ella, la automática dice la primera frase del
  texto del paso. Sin plata, como todo lo demás. No va en lo que lee el modelo para armar un plan
  (`capitulo_para_leer`): él escribe sus frases.
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
VERSION = 3
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
# Los tipos de control de una simulación del atlas (`simular`; app/recorrido.py y web/js/escenario.js los mismos)
TIPOS_CONTROL = ("accion", "numero", "opcion", "si_no")
# El modelo de las simulaciones cuando no hay uno del atlas a la vista: la maqueta 3D (la misma palabra que la cierra en
# `inmersion`; app/recorrido.py tiene la misma constante: una prueba las compara). Ninguna inmersión puede llamarse así
MAQUETA = "maqueta"
NOMBRE_MAQUETA = "La maqueta 3D"


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
    narracion = plano(sin_plata(_narracion(datos, c.get("id"), p.get("id"))))
    if narracion:
        out["narracion"] = narracion
    return out


def _narracion(datos: dict, capitulo: Any, paso: Any) -> Any:
    """La narración escrita a mano de un paso para la presentación automática (`tecnica.narracion[capítulo][paso]`), o
    None. Defensivo: lo que no es un objeto de objetos no trae ninguna."""
    tec = datos.get("tecnica") if isinstance(datos.get("tecnica"), dict) else {}
    del_capitulo = (tec.get("narracion") or {}).get(capitulo) if isinstance(tec.get("narracion"), dict) else None
    return del_capitulo.get(paso) if isinstance(del_capitulo, dict) and isinstance(paso, str) else None


def _numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _controles(lista: Any, capitulos: bool = False) -> list[dict]:
    """Los controles de la simulación de una inmersión para el modelo (`controles` de `tecnica.inmersiones`): id,
    nombre, tipo, el rango y la unidad de un número, las opciones (id y nombre) y la ayuda, en texto plano y en su orden.
    Con `capitulos` (los de la maqueta), también los capítulos en que vale cada uno, si lo dice. Defensivo: lo que no es
    un control con id y un tipo conocido no va (build_propuesta.py ya lo avisó); `problemas` dice después si un id no
    tiene la forma o se repite."""
    out = []
    for c in lista if isinstance(lista, list) else []:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or c.get("tipo") not in TIPOS_CONTROL:
            continue
        x: dict[str, Any] = {"id": c["id"], "nombre": plano(c.get("nombre")) or c["id"], "tipo": c["tipo"]}
        if c["tipo"] == "numero":
            x.update({k: c[k] for k in ("min", "max", "paso") if _numero(c.get(k))})
            if plano(c.get("unidad")):
                x["unidad"] = plano(c["unidad"])
        elif c["tipo"] == "opcion":
            x["opciones"] = [{"id": o["id"], "nombre": plano(o.get("nombre")) or o["id"]}
                             for o in (c.get("opciones") if isinstance(c.get("opciones"), list) else [])
                             if isinstance(o, dict) and isinstance(o.get("id"), str)]
        if plano(c.get("ayuda")):
            x["ayuda"] = plano(c["ayuda"])
        if capitulos and isinstance(c.get("capitulos"), list):
            x["capitulos"] = [k for k in c["capitulos"] if isinstance(k, str)]
        out.append(x)
    return out


def _maqueta(piezas: Any) -> list[dict]:
    """Las piezas de la maqueta de un capítulo para el modelo (`tecnica.maqueta[capítulo]`): id, nombre y las partes que
    se les pueden quitar (id y nombre), en su orden. Defensivo: lo que no es una pieza con id (o una parte con id) no
    va; sin nombre, queda el id. `problemas` dice después si un id no tiene la forma o se repite."""
    out = []
    for x in piezas if isinstance(piezas, list) else []:
        if not isinstance(x, dict) or not isinstance(x.get("id"), str):
            continue
        partes = [{"id": p["id"], "nombre": plano(p.get("nombre")) or p["id"]}
                  for p in (x.get("partes") if isinstance(x.get("partes"), list) else [])
                  if isinstance(p, dict) and isinstance(p.get("id"), str)]
        out.append({"id": x["id"], "nombre": plano(x.get("nombre")) or x["id"], "partes": partes})
    return out


def derivar(datos: dict) -> dict:
    """El guion de la presentación técnica a partir de web/data/propuesta.json (lo que arma build_propuesta.py):
    capítulos en el orden de main.js, cada uno con sus pasos, sus componentes y las piezas de su maqueta, y el catálogo
    de inmersiones del atlas. Siempre el mismo resultado para los mismos datos (sin fechas ni nada que cambie solo)."""
    tec = datos.get("tecnica") if isinstance(datos.get("tecnica"), dict) else {}
    catalogo = [i for i in tec.get("inmersiones") or [] if isinstance(i, dict) and isinstance(i.get("id"), str)]
    inmersiones = {i["id"]: i for i in catalogo}
    maquetas = tec.get("maqueta") if isinstance(tec.get("maqueta"), dict) else {}
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
        maqueta = _maqueta(maquetas.get(c["id"]))
        if maqueta:
            # lo que el plan guiado puede mostrar, ocultar, aislar o apuntar con la cámara en este capítulo
            cap["maqueta"] = maqueta
        cap["pasos"] = [_paso(datos, c, p, inmersiones) for p in c["pasos"]]
        capitulos.append(cap)
    out = {"version": VERSION, "modo": MODO, "fuente": "web/data/propuesta.json",
           "inmersiones": [{"id": i["id"], "nombre": plano(i.get("nombre")), "muestra": plano(i.get("texto")),
                            "controles": _controles(i.get("controles"))} for i in catalogo],
           "capitulos": capitulos}
    sm = tec.get("simulaciones_maqueta")
    if isinstance(sm, list) and sm:
        # las simulaciones de la maqueta 3D (sin un modelo del atlas a la vista): como una inmersión, fuera del catálogo
        out["maqueta"] = {"id": MAQUETA, "nombre": NOMBRE_MAQUETA, "controles": _controles(sm, capitulos=True)}
    return out


def problemas(g: dict) -> list[str]:
    """Lo que impediría usar el guion (lo revisa build_propuesta.py antes de escribirlo y `Guion.desde` al cargarlo):
    ids de capítulo, de paso, de componente, de inmersión, de pieza de la maqueta o de una de sus partes que no cumplen
    la forma que aceptan la herramienta y el navegador, repetidos, capítulos con más pasos que el tope, un paso que pesa
    más de `MAX_BYTES_PASO` o que lleva a una inmersión que no está en el catálogo. Y los controles de cada inmersión
    y de la maqueta: ids que no cumplen la forma o se repiten, un tipo desconocido, un número sin un rango (min < max),
    una opción sin opciones (o con ids inválidos o repetidos) o, en la maqueta, `capitulos` que no es una lista de ids
    de capítulos del guion."""
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
    for i in inm:
        out += [f"inmersión {i.get('id') if isinstance(i, dict) else i!r}: {x}"
                for x in _problemas_controles(i.get("controles", []) if isinstance(i, dict) else [])]
    if MAQUETA in ids_inm:
        out.append(f"una inmersión no puede llamarse «{MAQUETA}»")
    if "maqueta" in g:
        mq = g["maqueta"]
        if not isinstance(mq, dict) or mq.get("id") != MAQUETA:
            out.append(f"la maqueta de las simulaciones no tiene la forma {{id: {MAQUETA}, controles}}")
        else:
            out += [f"maqueta: {x}" for x in _problemas_controles(mq.get("controles", []))]
            # cada capítulo nombrado tiene que ser del guion: uno que no está dejaría el control fuera de todos, sin aviso
            ids_caps = {c.get("id") for c in caps if isinstance(c, dict)}
            for c in mq.get("controles") if isinstance(mq.get("controles"), list) else []:
                k = c.get("capitulos") if isinstance(c, dict) else None
                if k is not None and (not isinstance(k, list) or not k or
                                      any(not isinstance(x, str) or not ID.fullmatch(x) for x in k)):
                    out.append(f"maqueta: {c.get('id')}: capitulos es una lista de ids de capítulo")
                elif k is not None:
                    out += [f"maqueta: {c.get('id')}: el capítulo «{x}» no existe" for x in k if x not in ids_caps]
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
        maqueta = c.get("maqueta", [])
        if not isinstance(maqueta, list) or not all(isinstance(x, dict) for x in maqueta):
            out.append(f"{cid}: la maqueta no es una lista de piezas")
            maqueta = []
        ids_m = [x.get("id") for x in maqueta]
        for x in maqueta:
            if not isinstance(x.get("id"), str) or not ID_PASO.fullmatch(x["id"]):
                out.append(f"{cid}: pieza de la maqueta con un id que no es de letras minúsculas, números o «_»: "
                           f"{x.get('id')!r}")
            partes = x.get("partes", [])
            ids_p = [p.get("id") if isinstance(p, dict) else None for p in partes] if isinstance(partes, list) else [None]
            if any(not isinstance(p, str) or not ID_PASO.fullmatch(p) for p in ids_p) or len(set(ids_p)) != len(ids_p):
                out.append(f"{cid}/{x.get('id')}: partes de la pieza con un id inválido o repetido")
        if len(set(map(str, ids_m))) != len(ids_m):
            out.append(f"{cid}: ids de pieza de la maqueta repetidos")
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


def _problemas_controles(controles: Any) -> list[str]:
    """Lo que impide accionar los controles de una inmersión (`problemas`)."""
    if not isinstance(controles, list):
        return ["los controles no son una lista"]
    out, vistos = [], set()
    for c in controles:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not ID_PASO.fullmatch(cid):
            out.append(f"control con un id que no es de letras minúsculas, números o «_»: {cid!r}")
            continue
        if cid in vistos:
            out.append(f"control repetido: {cid}")
        vistos.add(cid)
        tipo = c.get("tipo")
        if tipo not in TIPOS_CONTROL:
            out.append(f"{cid}: el tipo {tipo!r} no es {', '.join(TIPOS_CONTROL)}")
        elif tipo == "numero" and not (_numero(c.get("min")) and _numero(c.get("max")) and c["min"] < c["max"]):
            out.append(f"{cid}: un número lleva min y max, con min < max")
        elif tipo == "numero" and "paso" in c and not (_numero(c["paso"]) and c["paso"] > 0):
            out.append(f"{cid}: el paso es un número positivo")
        elif tipo == "opcion":
            ops = c.get("opciones")
            ids = [o.get("id") if isinstance(o, dict) else None for o in ops] if isinstance(ops, list) else []
            if not ids or any(not isinstance(o, str) or not ID_PASO.fullmatch(o) for o in ids) or len(set(ids)) != len(ids):
                out.append(f"{cid}: las opciones no tienen ids válidos y sin repetir")
    return out


# ───────────────────────────── El guion en el panel ─────────────────────────────

_VACIAS = frozenset("el la los las de del un una y en al lo".split())


def parecido(lista: list[dict], texto: Any) -> dict | None:
    """El elemento de `lista` ({id, nombre}) que se pidió con `texto`: el que tiene ese id o ese nombre (sin tildes ni
    mayúsculas) o, si ninguno es igual, el único que tiene todas las palabras pedidas al comienzo de alguna de las de
    su id o su nombre. None si no hay, o si hay varios así (ambiguo: mejor decirlo que adivinar)."""
    k = clave(texto)
    if not k:
        return None

    def igual(k: str) -> dict | None:
        return next((x for x in lista if k in (clave(x["id"]), clave(x.get("nombre")))), None)

    x = igual(k)
    if x is not None:
        return x
    # Sin las palabras vacías («la torre» es `torre`); una palabra corta tiene que estar entera («red» no es «reducción»):
    # resolver en silencio a lo que no se pidió es peor que decir que no está
    pedidas = [p for p in k.split() if p not in _VACIAS]
    if not pedidas:
        return None
    x = igual(" ".join(pedidas))
    if x is not None:
        return x
    parecidos = [x for x in lista
                 if all(any(s == p if len(p) < 4 else s.startswith(p)
                            for s in clave(f"{x['id']} {x.get('nombre') or ''}").split()) for p in pedidas)]
    return parecidos[0] if len(parecidos) == 1 else None


@dataclass(frozen=True)
class Resolucion:
    """El capítulo que se pidió por id o por nombre: su índice, o None con los candidatos (ambiguo o inexistente)."""
    indice: int | None
    candidatos: tuple[int, ...] = ()


@dataclass(frozen=True)
class Guion:
    capitulos: tuple[dict, ...]
    inmersiones: tuple[dict, ...] = ()
    # las simulaciones de la maqueta 3D ({id: MAQUETA, nombre, controles}), o None (un guion de antes)
    maqueta: dict | None = None

    @classmethod
    def desde(cls, datos: Any) -> "Guion":
        malos = problemas(datos)
        if malos:
            raise ValueError("Guion de la presentación inválido: " + "; ".join(malos[:5]))
        return cls(tuple(datos["capitulos"]), tuple(datos.get("inmersiones") or ()),
                   datos.get("maqueta") if isinstance(datos.get("maqueta"), dict) else None)

    def componentes(self, ci: int) -> list[dict]:
        """Los componentes del capítulo `ci` (id, nombre y si la cámara los puede enfocar); [] si no tiene."""
        return list(self.capitulos[ci].get("componentes") or [])

    def componente(self, ci: int, texto: Any) -> dict | None:
        """El componente del capítulo `ci` por su id o su nombre (sin tildes ni mayúsculas), o None."""
        k = clave(texto)
        if not k:
            return None
        return next((x for x in self.componentes(ci) if k in (clave(x["id"]), clave(x["nombre"]))), None)

    def piezas(self, ci: int) -> list[dict]:
        """Las piezas de la maqueta del capítulo `ci` que se pueden mostrar, ocultar o aislar: [{id, nombre, partes:
        [{id, nombre}]}]; [] si el capítulo no tiene (o el guion es de antes del catálogo)."""
        return [{"id": x["id"], "nombre": x.get("nombre") or x["id"], "partes": list(x.get("partes") or [])}
                for x in self.capitulos[ci].get("maqueta") or []]

    def pieza(self, ci: int, texto: Any) -> dict | None:
        """La pieza de la maqueta del capítulo `ci` por su id o su nombre (sin tildes ni mayúsculas), o None. Si
        ninguna es igual, la única que tiene todas las palabras pedidas al comienzo de alguna de las suyas («torre
        nueva» → la torre; «red» en Aguas no: son varias); con varias así, None (`parecido`)."""
        return parecido(self.piezas(ci), texto)

    def parte(self, ci: int, pieza_id: Any, texto: Any) -> dict | None:
        """La parte `texto` (id o nombre) de la pieza `pieza_id` del capítulo `ci`, o None."""
        x = next((p for p in self.piezas(ci) if p["id"] == pieza_id), None)
        return parecido(x["partes"], texto) if x else None

    def mirable(self, ci: int, texto: Any) -> dict | None:
        """A qué puede apuntar la cámara en el capítulo `ci` sin cambiar lo que se ve (`mirar`): una pieza de la
        maqueta o un componente con lugar en ella, por id o por nombre; {id, nombre} o None."""
        x = self.pieza(ci, texto)
        if x is None:
            x = parecido([k for k in self.componentes(ci) if k.get("enfoque")], texto)
        return {"id": x["id"], "nombre": x["nombre"]} if x else None

    def inmersion(self, texto: Any) -> dict | None:
        """La inmersión del catálogo por su id o su nombre, o None."""
        k = clave(texto)
        if not k:
            return None
        return next((i for i in self.inmersiones if k in (clave(i["id"]), clave(i.get("nombre")))), None)

    def controles(self, modelo: Any, capitulo: Any = None) -> list[dict]:
        """Los controles de la simulación del modelo `modelo`, en su orden: los de la inmersión con ese id o, con
        MAQUETA, los de la maqueta 3D que valen en el `capitulo` (su id o su índice), sin `capitulos` ([] sin capítulo).
        [] si no tiene o no existe."""
        if modelo == MAQUETA:
            if isinstance(capitulo, int) and not isinstance(capitulo, bool) and 0 <= capitulo < len(self.capitulos):
                capitulo = self.capitulos[capitulo]["id"]
            if not isinstance(capitulo, str):
                return []
            return [{k: v for k, v in c.items() if k != "capitulos"} for c in (self.maqueta or {}).get("controles") or []
                    if not c.get("capitulos") or capitulo in c["capitulos"]]
        i = next((x for x in self.inmersiones if x["id"] == modelo), None) if isinstance(modelo, str) else None
        return list((i or {}).get("controles") or [])

    def control(self, modelo: Any, texto: Any, capitulo: Any = None) -> dict | None:
        """El control del modelo `modelo` (una inmersión, o MAQUETA en `capitulo`) por su id o su nombre (`parecido`: sin
        tildes ni mayúsculas, o el único que tiene esas palabras), o None."""
        return parecido(self.controles(modelo, capitulo), texto)

    def nombre_modelo(self, modelo: Any) -> str:
        """El nombre del modelo de una simulación: «La maqueta 3D» o el de la inmersión (o su id)."""
        if modelo == MAQUETA:
            return NOMBRE_MAQUETA
        return (self.inmersion(modelo) or {}).get("nombre") or str(modelo)

    def inmersiones_del_capitulo(self, ci: int) -> list[str]:
        """Los ids de las inmersiones que muestran los pasos del capítulo `ci`, en su orden y sin repetir."""
        ids = [(p.get("inmersion") or {}).get("id") for p in self.capitulos[ci]["pasos"] if p.get("tipo") == "inmersion"]
        return list(dict.fromkeys(i for i in ids if isinstance(i, str)))

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

    def capitulo_para_leer(self, ci: int, tope: int = 34000) -> dict:
        """Todo lo de un capítulo para armar un plan guiado (un recorrido narrado), de una vez: sus pasos (con lo que
        muestra cada uno y lo que se puede resaltar), la ficha técnica de cada componente (una sola vez: el paso dice
        cuál con su id), las piezas de la maqueta que se pueden mostrar, ocultar, aislar o apuntar con la cámara, con
        las partes que se les pueden quitar (`maqueta`; una pieza sin partes va sin esa clave) y el catálogo de
        inmersiones, con los controles de la simulación de las que muestran los pasos del capítulo, y los de la maqueta
        3D en este capítulo (`controles_maqueta`: lo que acciona `simular` sin un modelo del atlas). Si pasa de `tope`
        bytes (con la nota de la herramienta, por debajo de `MAX_CONTENIDO`), las fichas van sin descripción ni
        referentes; si todavía pasa, los controles van sin su ayuda. Los pasos van sin su `narracion`: es la frase de la
        presentación automática, que el modelo no dice (escribe la suya) y que solo le restaría lugar a las fichas."""
        c = self.capitulos[ci]
        pasos = []
        for pi, p in enumerate(c["pasos"]):
            x = {k: v for k, v in p.items() if k not in ("componente", "narracion")}
            if isinstance(p.get("componente"), dict):
                x["componente"] = p["componente"].get("id")
            if isinstance(p.get("inmersion"), dict):
                x["inmersion"] = p["inmersion"].get("id")
            pasos.append({"n": pi + 1, **x, "resaltable": self.resaltable(ci, pi)})
        fichas = [{**{k: v for k, v in x.items() if k != "enfoque"}, "lugar_en_la_maqueta": bool(x.get("enfoque"))}
                  for x in self.componentes(ci)]
        suyas = set(self.inmersiones_del_capitulo(ci))
        out = {"capitulo": {k: c[k] for k in ("id", "nombre", "lema") if c.get(k)}, "pasos": pasos,
               "componentes": fichas,
               "maqueta": [{k: v for k, v in x.items() if v or k != "partes"} for x in self.piezas(ci)],
               "controles_maqueta": self.controles(MAQUETA, ci),
               "inmersiones": [{"id": i["id"], "nombre": i.get("nombre"), "muestra": i.get("muestra"),
                                **({"controles": i["controles"]} if i["id"] in suyas and i.get("controles") else {})}
                               for i in self.inmersiones]}
        pesa = lambda: len(json.dumps(out, ensure_ascii=False).encode("utf-8"))   # noqa: E731
        if pesa() > tope:
            out["componentes"] = [{k: v for k, v in x.items() if k not in ("descripcion", "proyectos_tipo")}
                                  for x in fichas]
            out["recortado"] = "Las fichas van sin descripción ni referentes para caber: pídalas con visual detalle."
        if pesa() > tope:
            for i in out["inmersiones"]:
                if i.get("controles"):
                    i["controles"] = [{k: v for k, v in x.items() if k != "ayuda"} for x in i["controles"]]
            out["controles_maqueta"] = [{k: v for k, v in x.items() if k != "ayuda"} for x in out["controles_maqueta"]]
            out["recortado"] += " Los controles de las simulaciones van sin su ayuda."
        return out

    def indice(self) -> dict:
        """Capítulos con su id, nombre, los títulos de sus pasos, los ids de sus componentes (los que la cámara enfoca
        marcados), los de las piezas de su maqueta (sus nombres y sus partes, en `capitulo_para_leer`) y los de los
        controles de la maqueta 3D en ese capítulo, y el catálogo de inmersiones con los ids de sus controles (los que
        acciona `simular`; sus nombres, rangos y opciones, en `capitulo_para_leer` y al abrirla): lo que el modelo
        necesita para elegir, en pocos KB."""
        caps = []
        for c in self.capitulos:
            cap = {"id": c["id"], "nombre": c["nombre"], "pasos": [p["titulo"] for p in c["pasos"]]}
            if c.get("componentes"):
                cap["componentes"] = [x["id"] + ("" if x.get("enfoque") else " (sin lugar en la maqueta)")
                                      for x in c["componentes"]]
            if c.get("maqueta"):
                cap["maqueta"] = [x["id"] for x in c["maqueta"]]
            sim = self.controles(MAQUETA, c["id"])
            if sim:
                cap["controles_maqueta"] = [x["id"] for x in sim]
            caps.append(cap)
        return {"capitulos": caps, "total_pasos": self.total_pasos(),
                "inmersiones": [{"id": i["id"], "nombre": i.get("nombre"),
                                 **({"controles": [x["id"] for x in i["controles"]]} if i.get("controles") else {})}
                                for i in self.inmersiones]}


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
