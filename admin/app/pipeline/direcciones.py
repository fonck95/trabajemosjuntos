"""Lectura y normalización de direcciones de Yondó.

Las direcciones llegan escritas a mano: «BARRIO TRES DE OCTUBRE CALLE 49 # 45  12», «JORGE ELIECER GAITAN, KR 54# 51-20
FRENTE AL PARQUE», «VEREDA SAN LUIS BELTRAN EN EL CASERIO», «BARRIO NUEVA ESPERANZAMANZANA 4 LOTE 18»… Este módulo las
parte en componentes (vía, número, cruce, placa, manzana, lote, lugar, referencia) y las vuelve a escribir con la
nomenclatura abreviada estándar (CL, KR, DG, TV, AV, MZ, LT), por ejemplo «CL 49 # 45-12, B. TRES DE OCTUBRE».

El reconocimiento del barrio o la vereda contra el nomenclátor está en `Nomenclator`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from rapidfuzz import fuzz, process

from .texto import limpiar

VIAS = {
    "CL": "CL", "CLL": "CL", "CALLE": "CL", "CALL": "CL", "CALE": "CL", "CLLE": "CL", "CAL": "CL", "CALLLE": "CL",
    "KR": "KR", "K": "KR", "CR": "KR", "CRA": "KR", "KRA": "KR", "CARRERA": "KR", "CRR": "KR", "CRRA": "KR", "CARERA": "KR",
    "CARR": "KR", "KRR": "KR", "CARREA": "KR", "CARRRERA": "KR", "CARREARA": "KR", "CRA.": "KR",
    "DG": "DG", "DIAG": "DG", "DIAGONAL": "DG",
    "TV": "TV", "TR": "TV", "TRANSV": "TV", "TRANSVERSAL": "TV", "TRANS": "TV", "TRASVERSAL": "TV",
    "AV": "AV", "AVENIDA": "AV", "AVDA": "AV",
}
LUGARES = {
    "BARRIO": "BARRIO", "BRR": "BARRIO", "BRIO": "BARRIO", "BARIO": "BARRIO", "BARRRIO": "BARRIO",
    "VEREDA": "VEREDA", "VDA": "VEREDA", "VREDA": "VEREDA",  "VRDA": "VEREDA", "VERDA": "VEREDA", "VERREDA": "VEREDA", "VERADA": "VEREDA",
    "CORREGIMIENTO": "CORREGIMIENTO", "CORRIGIMIENTO": "CORREGIMIENTO", "CORREGIMENTO": "CORREGIMIENTO",
    "CGTO": "CORREGIMIENTO", "CORR": "CORREGIMIENTO",
    "SECTOR": "SECTOR", "URBANIZACION": "URBANIZACION", "URB": "URBANIZACION", "CIUDADELA": "URBANIZACION",
    "CASERIO": "CASERIO", "ASENTAMIENTO": "ASENTAMIENTO", "ACENTAMIENTO": "ASENTAMIENTO",
    "INVASION": "ASENTAMIENTO", "FINCA": "FINCA", "FCA": "FINCA", "HACIENDA": "FINCA", "PARCELA": "FINCA",
}
MANZANA = {"MZ", "MZA", "MANZANA", "MNZ", "MANZ"}
LOTE = {"LT", "LOTE", "LTE"}
CASA = {"CASA", "CS"}
NUMERO = {"#", "NO", "NRO", "N", "NUM", "NUMERO", "X", "CON"}
# Palabras que cortan el nombre de un lugar
CORTE = set(VIAS) | set(LUGARES) | MANZANA | LOTE | CASA | {
    "#", "-", "EN", "FRENTE", "DIAGONAL", "CERCA", "DETRAS", "JUNTO", "AL", "CON", "VIA", "CUADRA", "POR", "ETAPA",
    "APTO", "AP", "PISO", "SIN", "S", "NOMENCLATURA", "KM", "KILOMETRO", "ENTRADA", "SALIDA", "LADO", "ATRAS",
    "ESQUINA", "LOCAL", "BLOQUE", "INTERIOR", "PRIMERA", "SEGUNDA", "TERCERA", "VIVIENDA", "CERCANO", "DONDE",
}
REFERENCIA = {"FRENTE", "CERCA", "DETRAS", "JUNTO", "DIAGONAL", "ATRAS", "ESQUINA", "CERCANO", "DONDE", "ENTRADA"}
# Palabras sueltas que llegan como lugar y no lo son
NO_LUGAR = {"", "X", "K", "Y", "NA", "N A", "SIN DATO", "NINGUNA", "NO", "NO TIENE", "SIN", "SN", "YONDO", "CASABE",
            "YONDO ANTIOQUIA", "ANTIOQUIA", "MUNICIPIO", "CENTRO POBLADO", "ZONA RURAL", "RURAL", "URBANO"}

_NUM = re.compile(r"^\d{1,3}[A-Z]?$")
_DIG = re.compile(r"^\d+$")


@dataclass
class Direccion:
    original: str
    limpia: str = ""
    via: str | None = None
    num: str | None = None
    cruce: str | None = None
    placa: str | None = None
    mz: str | None = None
    lt: str | None = None
    casa: str | None = None
    lugar_texto: str | None = None
    tipo_lugar: str | None = None
    finca: str | None = None
    referencia: str | None = None
    sin_nomenclatura: bool = False
    tokens: list[str] = field(default_factory=list, repr=False)

    @property
    def tiene_placa(self) -> bool:
        return bool(self.via and self.num and self.cruce)

    def via_texto(self) -> str:
        """'CL 49 # 45-12' o 'KR 54' si no hay cruce."""
        if not (self.via and self.num):
            return ""
        s = f"{self.via} {self.num}"
        if self.cruce:
            s += f" # {self.cruce}" + (f"-{self.placa}" if self.placa else "")
        return s

    def normalizada(self, lugar: str | None = None, tipo: str | None = None) -> str:
        """Dirección reescrita con abreviaturas estándar. `lugar`/`tipo` son los oficiales del nomenclátor."""
        partes: list[str] = []
        v = self.via_texto()
        if v:
            partes.append(v)
        if self.mz:
            partes.append(f"MZ {self.mz}" + (f" LT {self.lt}" if self.lt else ""))
        elif self.lt:
            partes.append(f"LT {self.lt}")
        if self.casa and not v:
            partes.append(f"CASA {self.casa}")
        nombre = lugar or self.lugar_texto
        t = tipo or self.tipo_lugar
        if nombre:
            pref = {"BARRIO": "B.", "VEREDA": "VDA.", "CORREGIMIENTO": "CORR.", "SECTOR": "SECTOR",
                    "URBANIZACION": "URB.", "CASERIO": "CASERÍO", "CENTRO_POBLADO": "C.P.", "ASENTAMIENTO": "ASENT.",
                    "barrio": "B.", "vereda": "VDA.", "corregimiento": "CORR.", "caserio": "CASERÍO",
                    "centro_poblado": "C.P.", "sector": "SECTOR"}.get(t or "", "")
            partes.append(f"{pref} {nombre}".strip())
        if self.finca:
            partes.append(f"FINCA {self.finca}")
        if not partes and self.sin_nomenclatura:
            return "SIN NOMENCLATURA"
        return ", ".join(partes)

    def componentes(self) -> dict:
        d = asdict(self)
        d.pop("tokens", None)
        return d


def _preparar(texto: str) -> str:
    s = limpiar(texto)
    s = s.replace("N°", " # ").replace("NO.", " # ").replace("Nº", " # ")
    s = re.sub(r"[()\[\]{}\"'`´,;:_/\\|*]", " ", s)
    s = s.replace(".", " ")
    # Palabras clave pegadas al nombre anterior: «ESPERANZAMANZANA 4» → «ESPERANZA MANZANA 4»
    s = re.sub(r"([A-Z]{3,})(MANZANA|CALLE|CARRERA|LOTE|VEREDA|BARRIO)(?=[\s\d]|$)", r"\1 \2", s)
    # Letras y dígitos pegados: «KR55» → «KR 55», «55#» → «55 #»; conserva el sufijo de una letra («47D»)
    s = re.sub(r"(?<=[A-Z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[A-Z]{2,})", " ", s)
    s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " - ", s)
    s = s.replace("#", " # ")
    s = re.sub(r"\s-\s(?!\d)|(?<!\d)\s?-\s?(?=[A-Z])", " ", s)
    # Veredas con nombre de kilómetro o de campo petrolero: «X-10», «X 1O», «K -5», «KM 5», «KILOMETRO CINCO» → «X10», «K5»
    s = re.sub(r"\b(?:KILOMETRO|KM)\s*(?:CINCO|5)\b", "K5", s)
    # (K solo con un dígito: «K 45» es una carrera)
    s = re.sub(r"(?:^|(?<=[A-Z] ))(?:X\s?-?\s?(1O|\d{1,2})|K\s?-?\s?(\d))\b",
               lambda m: ("X" + m.group(1).replace("O", "0")) if m.group(1) else "K" + m.group(2), s)
    return re.sub(r"\s+", " ", s).strip()


def _es_num(t: str) -> bool:
    return bool(_NUM.match(t))


def leer(texto: object) -> Direccion:
    """Parte una dirección escrita a mano en sus componentes."""
    original = "" if texto is None else str(texto).strip()
    d = Direccion(original=original)
    s = _preparar(original)
    d.limpia = s
    toks = s.split()
    d.tokens = toks
    n = len(toks)
    usados = [False] * n
    if "SIN NOMENCLATURA" in s or re.search(r"\bS N\b|\bSIN DIRECCION\b", s):
        d.sin_nomenclatura = True

    # 1) Vía principal con número, cruce y placa
    i = 0
    while i < n and not d.via:
        t = toks[i]
        if t in VIAS and i + 1 < n:
            j = i + 1
            if toks[j] in NUMERO and j + 1 < n and _es_num(toks[j + 1]):  # «CL No 49»
                j += 1
            if _es_num(toks[j]):
                d.via, d.num = VIAS[t], toks[j]
                usados[i:j + 1] = [True] * (j + 1 - i)
                k = j + 1
                if k < n and toks[k] == "BIS":
                    d.num += " BIS"
                    usados[k] = True
                    k += 1
                if k < n and len(toks[k]) == 1 and toks[k].isalpha() and toks[k] not in NUMERO:  # «47 D»
                    d.num += toks[k]
                    usados[k] = True
                    k += 1
                # separador opcional y vía del cruce opcional («CON CALLE 44», «KR43-50-99»)
                while k < n and (toks[k] in NUMERO or toks[k] in VIAS or (toks[k] == "-" and k + 1 < n and _DIG.match(toks[k + 1]))):
                    usados[k] = True
                    k += 1
                if k < n and re.match(r"^\d{4}$", toks[k]):  # cruce y placa pegados: «CLL 52 N 4610» → 46-10
                    d.cruce, d.placa = toks[k][:2], toks[k][2:]
                    usados[k] = True
                    k += 1
                elif k < n and _es_num(toks[k]):
                    d.cruce = toks[k]
                    usados[k] = True
                    k += 1
                    if k < n and len(toks[k]) == 1 and toks[k].isalpha() and toks[k] not in NUMERO:
                        d.cruce += toks[k]
                        usados[k] = True
                        k += 1
                    if k < n and toks[k] == "-":
                        usados[k] = True
                        k += 1
                    if k < n and _DIG.match(toks[k]) and len(toks[k]) <= 3:
                        d.placa = toks[k]
                        usados[k] = True
                        k += 1
                i = k
                continue
        i += 1

    # 2) Manzana, lote y casa
    for i, t in enumerate(toks):
        if i + 1 >= n:
            break
        sig = toks[i + 1]
        if t in MANZANA and re.match(r"^[A-Z0-9]{1,4}$", sig):
            d.mz = d.mz or sig
            usados[i] = usados[i + 1] = True
        elif t in LOTE and re.match(r"^[A-Z0-9]{1,4}$", sig):
            d.lt = d.lt or sig
            usados[i] = usados[i + 1] = True
        elif t in CASA and _DIG.match(sig):
            d.casa = d.casa or sig
            usados[i] = usados[i + 1] = True

    # 3) Lugar con palabra clave («BARRIO VILLA MARIA», «VEREDA LA CONDOR», «FINCA EL MANANTIAL»)
    def nombre_desde(j: int) -> tuple[str, int]:
        palabras = []
        while j < n and toks[j] not in CORTE and not _DIG.match(toks[j]):
            palabras.append(toks[j])
            j += 1
        return " ".join(palabras), j

    for i, t in enumerate(toks):
        if t in LUGARES and not usados[i]:
            nombre, fin = nombre_desde(i + 1)
            if not nombre:
                continue
            tipo = LUGARES[t]
            if tipo == "FINCA":
                d.finca = d.finca or nombre
            elif d.lugar_texto is None or (d.tipo_lugar in ("SECTOR", "CASERIO", "ASENTAMIENTO") and tipo in ("BARRIO", "VEREDA", "CORREGIMIENTO")):
                d.lugar_texto, d.tipo_lugar = nombre, tipo
            usados[i:fin] = [True] * (fin - i)

    # 4) Sin palabra clave: el texto del comienzo es el lugar («JORGE ELIECER GAITAN, KR 54…», «LA CONDOR»)
    if d.lugar_texto is None:
        nombre, _ = nombre_desde(0)
        if nombre and nombre not in NO_LUGAR:
            d.lugar_texto = nombre

    # 5) Referencia («FRENTE AL PARQUE»)
    for i, t in enumerate(toks):
        if t in REFERENCIA:
            d.referencia = " ".join(toks[i:])[:120]
            break
    return d


# ───────────────────────────── Nomenclátor ─────────────────────────────

@dataclass
class Lugar:
    id: int
    nombre: str
    tipo: str            # barrio | vereda | corregimiento | centro_poblado | caserio | sector
    zona: str            # urbana | rural
    lat: float | None
    lon: float | None
    alias: tuple[str, ...] = ()
    padre: str | None = None  # corregimiento o vereda que lo contiene


TIPO_PALABRA = {"BARRIO": {"barrio", "sector"}, "URBANIZACION": {"barrio", "sector"},
                "VEREDA": {"vereda", "caserio", "centro_poblado"}, "CASERIO": {"caserio", "vereda", "centro_poblado"},
                "CORREGIMIENTO": {"corregimiento", "centro_poblado"}, "SECTOR": {"sector", "barrio", "vereda"},
                "ASENTAMIENTO": {"barrio", "sector", "caserio", "vereda"}}
CASCO = "YONDO"  # los barrios del casco urbano tienen este «padre» en el nomenclátor
# Cuánto vale cada tipo cuando varios lugares aparecen en la misma dirección: gana el más preciso
PRIORIDAD = {"barrio": 5, "sector": 4, "caserio": 3, "centro_poblado": 3, "vereda": 2, "corregimiento": 1}


class Nomenclator:
    """Reconoce barrios, veredas y centros poblados dentro de una dirección."""

    def __init__(self, lugares: list[Lugar]):
        self.lugares = lugares
        self.por_alias: dict[str, list[Lugar]] = {}
        for lg in lugares:
            for a in {limpiar(lg.nombre), *map(limpiar, lg.alias)}:
                a = re.sub(r"[^A-Z0-9 ]", " ", a)
                a = re.sub(r"\s+", " ", a).strip()
                if a and a not in NO_LUGAR:
                    self.por_alias.setdefault(a, []).append(lg)
        self.max_n = max((len(a.split()) for a in self.por_alias), default=1)
        self._lista = list(self.por_alias)

    def _elegir(self, candidatos: list[Lugar], palabra: str | None) -> Lugar:
        if palabra and palabra in TIPO_PALABRA:
            preferidos = [c for c in candidatos if c.tipo in TIPO_PALABRA[palabra]]
            if preferidos:
                candidatos = preferidos
        return max(candidatos, key=lambda c: (c.lat is not None, PRIORIDAD.get(c.tipo, 0)))

    def reconocer(self, d: Direccion) -> tuple[Lugar | None, list[Lugar], float]:
        """Devuelve (lugar elegido, todos los encontrados, confianza 0-1)."""
        toks = d.tokens
        hallados: list[tuple[Lugar, int, int, float]] = []  # lugar, inicio, largo, confianza
        i = 0
        while i < len(toks):
            for largo in range(min(self.max_n, len(toks) - i), 0, -1):
                frase = " ".join(toks[i:i + largo])
                if frase in self.por_alias:
                    previa = toks[i - 1] if i else None
                    palabra = LUGARES.get(previa or "", None)
                    # Un nombre de una sola palabra («PARAISO», «GAITAN») solo cuenta si viene tras la palabra clave
                    # o si es todo el lugar escrito
                    if largo == 1 and not palabra and frase != (d.lugar_texto or ""):
                        continue
                    hallados.append((self._elegir(self.por_alias[frase], palabra), i, largo, 1.0))
                    i += largo - 1
                    break
            i += 1

        if not hallados and d.lugar_texto and d.lugar_texto not in NO_LUGAR and len(d.lugar_texto) >= 4:
            m = process.extractOne(d.lugar_texto, self._lista, scorer=fuzz.ratio, score_cutoff=86)
            if m is None:
                # «SAN MIGUEL DEL TIGRE BARR…»: el alias está contenido en el texto
                m = process.extractOne(d.lugar_texto, self._lista, scorer=fuzz.partial_ratio, score_cutoff=93)
                if m and len(m[0]) < 6:
                    m = None
            if m:
                hallados.append((self._elegir(self.por_alias[m[0]], d.tipo_lugar), 0, 0, m[1] / 100))

        if not hallados:
            return None, [], 0.0
        lugares = [h[0] for h in hallados]
        rurales = [lg for lg in lugares if lg.zona == "rural"]
        # Si la dirección nombra un corregimiento o vereda, un barrio del casco con el mismo nombre no aplica
        if rurales and any(lg.tipo in ("corregimiento", "centro_poblado", "vereda") for lg in rurales):
            candidatos = [h for h in hallados if h[0].zona == "rural" or (h[0].padre and h[0].padre != CASCO)]
        else:
            candidatos = hallados
        mejor = max(candidatos, key=lambda h: (h[0].lat is not None, PRIORIDAD.get(h[0].tipo, 0), h[3]))
        return mejor[0], lugares, mejor[3]


def zona_por_texto(d: Direccion) -> str | None:
    """Zona deducida solo del texto, cuando el lugar no está en el nomenclátor."""
    if d.tipo_lugar in ("VEREDA", "CASERIO", "CORREGIMIENTO") or d.finca:
        return "rural"
    if d.tipo_lugar in ("BARRIO", "URBANIZACION") or d.tiene_placa:
        return "urbana"
    return None
