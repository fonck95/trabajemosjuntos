"""El guion de la presentación de la propuesta 2028–2031 (web/propuesta.html): lo que el asistente sabe de cada capítulo
y de cada paso para presentarla y explicarla (la herramienta `presentacion`, `herramientas/interfaz.py`).

Por qué está hecho así:

* Lo genera `scripts/build_propuesta.py` (con `derivar`) a partir de lo mismo que lee la presentación
  (web/data/propuesta.json) y queda versionado aquí, en `propuesta_guion.json`: así lo tiene también el panel que se
  despliega aparte (Root Directory = admin), que no trae web/. Una prueba (test_agente_presentacion.py) lo compara con
  lo que se deriva de web/data/propuesta.json: si alguien cambia la propuesta y no lo regenera, falla.
* Son datos públicos de la propuesta, los mismos que se ven en pantalla: nada de la base de habitantes. Por eso no pasa
  por `minimizar`.
* Los capítulos van en el orden y con los nombres de `caps` en web/js/propuesta/main.js (la portada, los módulos en el
  orden de general.json, la financiación, la hoja de ruta y los pedidos), y un capítulo sin pasos recibe el paso
  «inicio», como allí: el asistente y la presentación cuentan los pasos igual (la dirección `#vivienda/3` es el tercero).
  Otra prueba compara los nombres fijos con los de main.js.
* Cada paso trae lo que su panel muestra (`RENDER` de main.js, con los mismos títulos y textos de respaldo), en texto
  plano: sin HTML y sin los espacios que no se cortan ni las uniones de palabras (U+2060) que pone build_propuesta.py
  para el panel. Los textos se acotan (`MAX_TEXTO`) para que un paso le llegue al modelo en un par de KB.
* Solo usa la biblioteca estándar: build_propuesta.py lo carga por su ruta, sin las dependencias del panel. El panel lo
  lee con `cargar` (con caché por la fecha del archivo; pymongo no interviene, pero es lectura de disco: desde una
  corrutina va con `run_in_threadpool`).
"""
from __future__ import annotations

import html
import json
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

RUTA = Path(__file__).with_name("propuesta_guion.json")
VERSION = 1
MAX_TEXTO = 1500     # el texto principal de un paso
MAX_DETALLE = 600    # un texto secundario (nota, antes y después, lo que se pide)
MAX_CORTO = 240      # una línea de una lista, un rótulo de la leyenda o una cifra
MAX_LISTA = 12       # elementos de cada lista de un paso
MAX_PASOS = 60       # el tope de `paso` en la herramienta y en el navegador
# Los capítulos que no salen de `modulos`, con los nombres que tienen fijos en web/js/propuesta/main.js (`caps`)
FIJOS_ANTES = (("portada", "Portada", "Portada"),)
FIJOS_DESPUES = (("financiacion", "Cómo se financia", "Financiación"), ("ruta", "Hoja de ruta", "Ruta"),
                 ("pedidos", "Lo que pedimos", "Pedidos"))
ID = re.compile(r"[a-z_]{2,40}")
ID_PASO = re.compile(r"[a-z0-9_]{1,40}")


# ───────────────────────────── Texto plano ─────────────────────────────

_ETIQUETA = re.compile(r"<[^>]*>")
# Lo que build_propuesta.py pone para que el panel no parta una cifra (espacios que no se cortan, unión de palabras) y
# el guion blando de las palabras largas: en el guion son un espacio común o nada
_ESPACIOS_DUROS = str.maketrans({"\xa0": " ", "\U0000202f": " ", "\U00002007": " ", "\U00002060": None, "\xad": None})


def plano(v: Any, maximo: int = MAX_TEXTO) -> str:
    """Texto de una línea sin HTML ni entidades, sin los espacios que no se cortan y acotado a `maximo` caracteres
    (cortado en una palabra, con «…»)."""
    if not isinstance(v, str):
        return ""
    t = html.unescape(_ETIQUETA.sub("", v)).translate(_ESPACIOS_DUROS)
    t = " ".join(t.split())
    if len(t) <= maximo:
        return t
    corte = t[:maximo - 1]
    if " " in corte[maximo // 2:]:
        corte = corte[:corte.rindex(" ")]
    return corte.rstrip(" ,;:.") + "…"


def clave(v: Any) -> str:
    """Para comparar nombres: sin tildes, en minúsculas y con las palabras separadas por un espacio («Cómo se
    financia» → «como se financia»; «agro-industria» → «agro industria»)."""
    if not isinstance(v, str):
        return ""
    t = unicodedata.normalize("NFKD", v.translate(_ESPACIOS_DUROS))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


# ───────────────────────────── Cifras como las muestra la presentación ─────────────────────────────

def _numero(v: float, maximo: int, minimo: int = 0) -> str:
    """`toLocaleString('es-CO', {minimumFractionDigits, maximumFractionDigits})`: punto de miles, coma decimal y el
    redondeo de Intl (la mitad, hacia afuera)."""
    d = Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-maximo), rounding=ROUND_HALF_UP)
    entero, _, decimales = f"{abs(d):f}".partition(".")
    decimales = decimales.rstrip("0")
    decimales = decimales + "0" * max(0, minimo - len(decimales))
    entero = f"{int(entero):,}".replace(",", ".")
    return ("-" if d < 0 else "") + entero + (f",{decimales}" if decimales else "")


def _cifra2(v: float | None) -> float:
    """Dos cifras significativas (`cifra2` de main.js): una estimación de perfil no pretende más precisión."""
    if not v:
        return 0.0
    k = 10.0 ** (math.floor(math.log10(abs(v))) - 1)
    return math.floor(v / k + 0.5) * k  # Math.round de JavaScript


def millones(v: float | None) -> str:
    """Millones de pesos de 2026 en corto (`fmtM` de main.js): «$77,0 mil M», «$850 M», «$1,2 billones»."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
        return "—"
    a = abs(v)
    if a >= 1e6:
        return f"${_numero(v / 1e6, 2)} billones"
    if a >= 1000:
        return f"${_numero(v / 1000, 1, 1)} mil M"
    return f"${_numero(math.floor(v + 0.5), 0)} M"


def rango(minimo: Any, maximo: Any) -> str:
    """Un rango aproximado (`fmtRango` de main.js): «$54 – 100 mil M»; si los dos extremos coinciden, «≈ $77 mil M»."""
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x) for x in (minimo, maximo)):
        return "—"
    a, b = _cifra2(min(minimo, maximo)), _cifra2(max(minimo, maximo))
    if a == b:
        return f"≈ {millones(b)}"
    div, unidad, dec = (1e6, " billones", 2) if b >= 1e6 else (1000, " mil M", 1) if b >= 1000 else (1, " M", 0)
    return f"${_numero(a / div, dec)} – {_numero(b / div, dec)}{unidad}"


def rango_de(c: Any) -> str:
    """El rango de un objeto {min, central, max} (`rg` de main.js), o «» si no hay."""
    if not isinstance(c, dict) or c.get("central") is None and (c.get("min") is None or c.get("max") is None):
        return ""
    m = c.get("min") if c.get("min") is not None else c.get("central")
    x = c.get("max") if c.get("max") is not None else c.get("central")
    r = rango(m, x)
    return "" if r == "—" else r


def aproximado(v: Any) -> str:
    """Un valor suelto como aproximación (`aprox` de main.js)."""
    return f"≈ {millones(_cifra2(v))}" if isinstance(v, (int, float)) and not isinstance(v, bool) else ""


# ───────────────────────────── Del JSON de la presentación al guion ─────────────────────────────

def _lista(v: Any, maximo: int = MAX_CORTO) -> list[str]:
    out = [plano(x, maximo) for x in (v if isinstance(v, list) else [])]
    return [x for x in out if x][:MAX_LISTA]


def _cifras(v: Any) -> list[dict]:
    out = []
    for c in v if isinstance(v, list) else []:
        if isinstance(c, dict) and plano(c.get("v"), 40):
            out.append({"v": plano(c.get("v"), 40), "l": plano(c.get("l"), MAX_CORTO)})
    return out[:MAX_LISTA]


def _leyenda(v: Any) -> list[str]:
    return [t for t in (plano(x.get("texto"), MAX_CORTO) for x in (v if isinstance(v, list) else [])
                        if isinstance(x, dict)) if t][:MAX_LISTA]


def _fuentes_de(datos: dict) -> dict[str, dict]:
    fin = datos.get("financiacion") if isinstance(datos.get("financiacion"), dict) else {}
    return {f["id"]: f for f in fin.get("fuentes") or [] if isinstance(f, dict) and isinstance(f.get("id"), str)}


def _nombre_fuente(fuentes: dict[str, dict], fid: Any) -> str:
    f = fuentes.get(fid) if isinstance(fid, str) else None
    return plano((f or {}).get("corto") or (f or {}).get("nombre") or fid, 80)


def _margen(inv: Any) -> tuple[float, float]:
    """(mínimo, máximo) de la inversión de un módulo como fracción de la central: cada aporte se muestra con el mismo
    margen (`pilaFinanciacion` y `matriz` de main.js)."""
    if not isinstance(inv, dict) or not inv.get("central"):
        return 1.0, 1.0
    c = inv["central"]
    return (inv.get("min") if inv.get("min") is not None else c) / c, (inv.get("max") if inv.get("max") is not None
                                                                      else c) / c


def _mezcla(fin: Any, inv: Any, fuentes: dict[str, dict]) -> list[dict]:
    k0, k1 = _margen(inv)
    out = []
    for f in fin if isinstance(fin, list) else []:
        if isinstance(f, dict):
            monto = f.get("monto") or 0
            out.append({"fuente": _nombre_fuente(fuentes, f.get("fuente")), "monto": rango(monto * k0, monto * k1)})
    return out[:MAX_LISTA]


def _por_fuente(datos: dict, fuentes: dict[str, dict]) -> list[dict]:
    """Lo que aporta cada fuente a toda la propuesta, de mayor a menor (el paso `matriz`)."""
    totales: dict[str, list[float]] = {}
    for m in datos.get("modulos") or []:
        k0, k1 = _margen(m.get("inversion"))
        for x in m.get("financiacion") or []:
            if isinstance(x, dict) and x.get("fuente") in fuentes:
                t = totales.setdefault(x["fuente"], [0.0, 0.0, 0.0])
                monto = x.get("monto") or 0
                t[0], t[1], t[2] = t[0] + monto, t[1] + monto * k0, t[2] + monto * k1
    orden = sorted(((fid, t) for fid, t in totales.items() if t[0] > 0), key=lambda e: -e[1][0])
    return [{"fuente": _nombre_fuente(fuentes, fid), "monto": rango(t[1], t[2])} for fid, t in orden][:MAX_LISTA]


def _inversion_total(datos: dict) -> str:
    mods = [m for m in datos.get("modulos") or [] if isinstance(m, dict)]
    inv = [m.get("inversion") or {} for m in mods]
    lo = sum(i.get("min") if i.get("min") is not None else i.get("central") or 0 for i in inv)
    hi = sum(i.get("max") if i.get("max") is not None else i.get("central") or 0 for i in inv)
    return rango(lo, hi) if inv else ""


def _componente(x: dict) -> dict:
    """El componente de un paso `componente`: lo que dice su ficha en el panel."""
    out = {"nombre": plano(x.get("nombre"), MAX_CORTO), "resumen": plano(x.get("resumen"), MAX_DETALLE),
           "costo": rango_de(x.get("costo")), "plazo": plano(x.get("plazo"), 80),
           "ubicacion": plano(x.get("ubicacion"), MAX_DETALLE)}
    return {k: v for k, v in out.items() if v}


# El título de un paso que no trae el suyo, según su tipo (los respaldos de `RENDER` en main.js)
TITULO_POR_TIPO = {"componentes": "Qué se construye", "financiacion": "Cómo se financia",
                   "matriz": "Cómo se financia todo", "fuentes": "Las fuentes, una por una",
                   "ruta": "De la idea a la obra", "pedidos": "Lo que pedimos"}


def _paso(datos: dict, c: dict, p: dict, fuentes: dict[str, dict]) -> dict:
    """Lo que muestra el panel en el paso `p` del capítulo `c` (`RENDER` de main.js), con sus mismos respaldos."""
    tipo = p.get("tipo") if isinstance(p.get("tipo"), str) else "texto"
    x = next((k for k in c.get("componentes") or [] if isinstance(k, dict) and k.get("id") == p.get("componente")),
             None) if tipo == "componente" else None
    respaldo = {"portada": c.get("titulo"), "portadilla": c.get("lema"), "componente": (x or {}).get("nombre"),
                "texto": c.get("nombre")}.get(tipo, TITULO_POR_TIPO.get(tipo))
    titulo = plano(p.get("titulo") or respaldo, MAX_CORTO) or plano(c.get("nombre"), MAX_CORTO)
    texto = p.get("texto") or {"portada": c.get("lema"), "portadilla": c.get("problema"),
                               "componente": (x or {}).get("descripcion")}.get(tipo)
    out: dict[str, Any] = {"id": p.get("id"), "tipo": tipo, "titulo": titulo, "texto": plano(texto, MAX_TEXTO)}
    comp = _componente(x) if x else {}
    cifras = _cifras(p.get("cifras") or (c.get("cifras") if tipo in ("portada", "portadilla") else None))
    if cifras:
        out["cifras"] = cifras
    if comp:
        out["componente"] = comp
    if tipo == "portada":
        out["modulos"] = [{"nombre": plano(m.get("nombre"), 80), "inversion": rango_de(m.get("inversion"))}
                          for m in datos.get("modulos") or [] if isinstance(m, dict)]
        out["inversion_total"] = _inversion_total(datos)
    elif tipo == "portadilla":
        out.update({k: v for k, v in (("propuesta", plano(c.get("propuesta"), MAX_DETALLE)),
                                      ("inversion", rango_de(c.get("inversion")))) if v})
    elif tipo == "componentes":
        out["componentes"] = [{k: v for k, v in (("nombre", plano(x.get("nombre"), MAX_CORTO)),
                                                 ("costo", rango_de(x.get("costo")))) if v}
                              for x in c.get("componentes") or [] if isinstance(x, dict)][:MAX_LISTA]
        if c.get("inversion"):
            out["inversion"] = rango_de(c.get("inversion"))
    elif tipo == "comparacion":
        for lado in ("antes", "despues"):
            d = p.get(lado) if isinstance(p.get(lado), dict) else {}
            t = plano(" · ".join(x for x in (plano(d.get("titulo"), 80), plano(d.get("texto"), MAX_DETALLE)) if x),
                      MAX_DETALLE)
            if t:
                out[lado] = t
    elif tipo == "financiacion":
        g = c.get("gestion") if isinstance(c.get("gestion"), dict) else {}
        mezcla = _mezcla(c.get("financiacion"), c.get("inversion"), fuentes)
        if mezcla:
            out["mezcla"] = mezcla
        out.update({k: v for k, v in (("madurez", plano(g.get("madurez"), 40)),
                                      ("pedido", plano(g.get("pedido"), MAX_DETALLE))) if v})
    elif tipo == "matriz":
        out["por_fuente"] = _por_fuente(datos, fuentes)
        out["inversion_total"] = _inversion_total(datos)
    elif tipo == "fuentes":
        out["fuentes"] = [{k: v for k, v in (("nombre", plano(f.get("nombre"), 120)), ("tipo", plano(f.get("tipo"), 80)))
                           if v} for f in c.get("fuentes") or [] if isinstance(f, dict)][:MAX_LISTA]
    elif tipo == "ruta":
        out["fases"] = [plano(f"{f.get('nombre')} ({_anio(f.get('desde'))}–{_anio(f.get('hasta'))})", MAX_CORTO)
                        for f in c.get("fases") or [] if isinstance(f, dict)][:MAX_LISTA]
        out["hitos"] = [plano(f"{h.get('fecha')}: {h.get('texto')}", MAX_CORTO)
                        for h in c.get("hitos") or [] if isinstance(h, dict)][:MAX_LISTA]
    elif tipo == "pedidos":
        out["entidades"] = [{k: v for k, v in (("entidad", plano(e.get("entidad"), 120)),
                                                ("monto", aproximado(e.get("monto")) if e.get("monto") else ""),
                                                ("pedido", plano(e.get("pedido"), MAX_DETALLE))) if v}
                            for e in c.get("entidades") or [] if isinstance(e, dict)][:MAX_LISTA]
    lista = _lista(p.get("lista"))
    if lista:
        out["lista"] = lista
    nota = plano(p.get("nota"), MAX_DETALLE)
    if nota:
        out["nota"] = nota
    leyenda = _leyenda(p.get("leyenda"))
    if leyenda:
        out["leyenda"] = leyenda
    return out


def _anio(v: Any) -> str:
    return str(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else "?"


def derivar(datos: dict) -> dict:
    """El guion a partir de web/data/propuesta.json (lo que arma build_propuesta.py): capítulos en el orden de main.js,
    cada uno con sus pasos. Siempre el mismo resultado para los mismos datos (sin fechas ni nada que cambie solo)."""
    fuentes = _fuentes_de(datos)
    caps: list[dict] = []
    for cid, nombre, corto in FIJOS_ANTES:
        caps.append({**(datos.get(cid) if isinstance(datos.get(cid), dict) else {}), "id": cid, "nombre": nombre,
                     "corto": corto})
    caps += [dict(m) for m in datos.get("modulos") or [] if isinstance(m, dict)]
    for cid, nombre, corto in FIJOS_DESPUES:
        caps.append({**(datos.get(cid) if isinstance(datos.get(cid), dict) else {}), "id": cid, "nombre": nombre,
                     "corto": corto})
    capitulos = []
    for c in caps:
        pasos = [p for p in c.get("pasos") or [] if isinstance(p, dict)] or [{"id": "inicio", "tipo": "texto",
                                                                             "titulo": c.get("nombre")}]
        cap: dict[str, Any] = {"id": c["id"], "nombre": plano(c.get("nombre"), 80),
                               "corto": plano(c.get("corto") or c.get("nombre"), 40)}
        lema = plano(c.get("lema") or c.get("subtitulo"), MAX_CORTO)
        if lema:
            cap["lema"] = lema
        inv = rango_de(c.get("inversion"))
        if inv:
            cap["inversion"] = inv
        cap["pasos"] = [_paso(datos, c, p, fuentes) for p in pasos]
        capitulos.append(cap)
    return {"version": VERSION, "fuente": "web/data/propuesta.json", "capitulos": capitulos}


def problemas(g: dict) -> list[str]:
    """Lo que impediría usar el guion (lo revisa build_propuesta.py antes de escribirlo y `Guion.desde` al cargarlo):
    ids de capítulo o de paso que no cumplen la forma que aceptan la herramienta y el navegador, repetidos, o capítulos
    con más pasos que el tope."""
    out = []
    caps = g.get("capitulos") if isinstance(g, dict) else None
    if not isinstance(caps, list) or not caps:
        return ["el guion no tiene capítulos"]
    vistos = set()
    for c in caps:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not ID.fullmatch(cid):
            out.append(f"capítulo con un id que no es de 2 a 40 letras minúsculas o «_»: {cid!r}")
            continue
        if cid in vistos:
            out.append(f"capítulo repetido: {cid}")
        vistos.add(cid)
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

    @classmethod
    def desde(cls, datos: Any) -> "Guion":
        malos = problemas(datos)
        if malos:
            raise ValueError("Guion de la presentación inválido: " + "; ".join(malos[:5]))
        return cls(tuple(datos["capitulos"]))

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

    def indice(self) -> dict:
        """Capítulos con su id, nombre y los títulos de sus pasos (lo que el modelo necesita para elegir, en pocos KB)."""
        return {"capitulos": [{"id": c["id"], "nombre": c["nombre"], "pasos": [p["titulo"] for p in c["pasos"]]}
                              for c in self.capitulos], "total_pasos": self.total_pasos()}


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
