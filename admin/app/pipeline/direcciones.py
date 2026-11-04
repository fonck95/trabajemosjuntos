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
from typing import NamedTuple

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
REFERENCIA = {"FRENTE", "CERCA", "DETRAS", "JUNTO", "DIAGONAL", "ATRAS", "ESQUINA", "CERCANO", "DONDE", "ENTRADA",
              "LADO", "CONTIGUO", "ENSEGUIDA", "ANTES", "DESPUES"}
# Palabras que solo enlazan la referencia con lo que sigue («CERCA AL BARRIO…»)
ENLACE = {"A", "AL", "DE", "DEL", "LA", "EL", "LOS", "LAS", "EN"}
# Palabras que cortan el nombre de un lugar
CORTE = set(VIAS) | set(LUGARES) | MANZANA | LOTE | CASA | REFERENCIA | {
    "#", "-", "EN", "FRENTE", "DIAGONAL", "CERCA", "DETRAS", "JUNTO", "AL", "CON", "VIA", "CUADRA", "POR", "ETAPA",
    "APTO", "AP", "PISO", "SIN", "S", "NOMENCLATURA", "KM", "KILOMETRO", "ENTRADA", "SALIDA", "LADO", "ATRAS",
    "ESQUINA", "LOCAL", "BLOQUE", "INTERIOR", "PRIMERA", "SEGUNDA", "TERCERA", "VIVIENDA", "CERCANO", "DONDE",
}
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
    # Tokens que no nombran el lugar de la persona: referencias («FRENTE A LA CEIBA») y nombres de finca
    fuera: list[bool] = field(default_factory=list, repr=False)

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
        d.pop("fuera", None)
        return d


# Unidades que llevan una letra: en «MZ B. LT 5» o «LOTE B/ MZ 4» la B es la manzana o el lote, no «BARRIO»
_UNIDAD_PREVIA = re.compile(r"(?:^|[^A-Z0-9])(?:MZ|MZA|MANZANA|MNZ|MANZ|LT|LOTE|LTE|CASA|CS|BLOQUE|TORRE|INTERIOR|ETAPA"
                            r"|APTO|AP)$")


def _b_barrio(m: re.Match) -> str:
    return m.group(0) if _UNIDAD_PREVIA.search(m.string[:m.start()].rstrip(" .")) else " BARRIO "


def _preparar(texto: str) -> str:
    s = limpiar(texto)  # (limpiar ya deja «N°» como «N» y «Nº» como «NO»)
    # «B/ LA PAZ» y «B. LA PAZ» (así escribe normalizada()) son barrio; tras un número («47B/», «47 B.») o tras una
    # unidad («MZ B. LT 5») es letra
    s = re.sub(r"(?<![A-Z0-9])B\s*/\s*(?=[A-Z])", _b_barrio, s)
    s = re.sub(r"(?<![A-Z0-9])(?<!\d )B\.\s*(?=[A-Z]{2})", _b_barrio, s)
    # «S.N.», «S. N.», «S N.»: sin nomenclatura (antes de que su «N.» pase a «#»)
    s = re.sub(r"\bS\s*[./ ]\s*N\b\s*\.?(?!\s*\d)", " S N ", s)
    # «No.», «Nro.», «N.» → «#», solo como palabra suelta («EL LLANO.» no se toca)
    s = re.sub(r"\bN(?:O|RO|UM)?\s*\.", " # ", s)
    s = re.sub(r"[()\[\]{}\"'`´,;:_/\\|*]", " ", s)
    s = s.replace(".", " ")
    # Palabras clave pegadas al nombre anterior: «ESPERANZAMANZANA 4» → «ESPERANZA MANZANA 4»
    s = re.sub(r"([A-Z]{3,})(MANZANA|CALLE|CARRERA|LOTE|VEREDA|BARRIO)(?=[\s\d]|$)", r"\1 \2", s)
    # Letras y dígitos pegados: «KR55» → «KR 55», «55#» → «55 #»; conserva el sufijo de una letra («47D»)
    s = re.sub(r"(?<=[A-Z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[A-Z]{2,})", " ", s)
    s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " - ", s)
    # También tras la letra o el BIS del cruce: «45A-12», «45 A-12», «45 BIS-12» (no toca «X-10» ni «K-5»)
    s = re.sub(r"(?:(?<=\d[A-Z])|(?<=\d [A-JL-WYZ])|(?<=BIS))\s*-\s*(?=\d)", " - ", s)
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


# Signos con que se parte a mano una dirección en trozos («FRENTE A LA ESCUELA, LA CONDOR», «… TIENDA - CENTRAL»).
# _preparar() los borra: se ubican antes para que una referencia no se trague el trozo siguiente
_SEPARADOR = re.compile(r"[,;|]|/|\.(?=\s|$)|\s-\s(?=[A-Z])")
_PALABRA_PREVIA = re.compile(r"(?:^|[^A-Z0-9])([A-Z0-9]+)\s*$")
# Palabras clave que se abrevian con punto («BRR.», «CORR.», «MANZ.»): ese punto no parte la dirección
_ABREVIADAS = set(VIAS) | set(LUGARES) | MANZANA | LOTE | CASA | NUMERO


def _cortes(original: str, toks: list[str]) -> set[int]:
    """Índices de los tokens que empiezan un trozo nuevo tras una coma, punto y coma, barra, guion suelto o el punto
    que cierra una palabra. Vacío si los trozos no reproducen los mismos tokens (entonces no se usa ninguno)."""
    s = limpiar(original)
    trozos, ini = [], 0
    for m in _SEPARADOR.finditer(s):
        previa = _PALABRA_PREVIA.search(s[:m.start()])
        palabra = previa.group(1) if previa else ""
        if m.group() == "/" and palabra == "B":  # «B/ LA PAZ» es barrio
            continue
        if m.group() == "." and (len(palabra) < 4 or not palabra.isalpha() or palabra in _ABREVIADAS):
            continue  # «SRA.», «PTO.», «12.», «BRR.»
        trozos.append(s[ini:m.start()])
        ini = m.end()
    if not trozos:
        return set()
    trozos.append(s[ini:])
    cortes: set[int] = set()
    juntos: list[str] = []
    for t in trozos:
        tt = _preparar(t).split()
        if tt and juntos:
            cortes.add(len(juntos))
        juntos += tt
    return cortes if juntos == toks else set()


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
                    if k < n and toks[k] == "BIS":  # «45 BIS-12»
                        d.cruce += " BIS"
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

    # 3) Referencias («FRENTE AL PARQUE», «AL LADO DE LA UNION»): llegan hasta la siguiente palabra clave de lugar o
    # de vía, salvo que esta siga a la referencia sin más («CERCA AL BARRIO LA PAZ» es todo referencia), o hasta el
    # siguiente trozo de la dirección («CERCA AL COLEGIO, PUERTO CASABE»; no «CERCA AL BARRIO, LA PAZ»)
    fuera = [False] * n
    cortes = _cortes(original, toks)
    for i, t in enumerate(toks):
        if t not in REFERENCIA or usados[i] or fuera[i]:
            continue
        ini = i - 1 if t == "LADO" and i and toks[i - 1] in ("AL", "A") else i
        j = i + 1
        # «… # 47-20 ESQUINA BARRIO VILLA MARIA», «… ESQUINA, VILLA MARIA»: ESQUINA sin «DE/DEL…» detrás dice que la
        # casa es esquinera, no remite a otro sitio («ESQUINA DEL PARQUE» sí es referencia)
        if not (t == "ESQUINA" and (j >= n or toks[j] not in ENLACE)):
            while j < n and not (j in cortes and toks[j - 1] not in LUGARES) and not (
                    (toks[j] in LUGARES or toks[j] in VIAS) and any(x not in ENLACE for x in toks[i + 1:j])):
                j += 1
        fuera[ini:j] = [True] * (j - ini)
        if d.referencia is None:
            d.referencia = " ".join(toks[ini:j])[:120]

    # 4) Lugar con palabra clave («BARRIO VILLA MARIA», «VEREDA LA CONDOR», «FINCA EL MANANTIAL»)
    def nombre_desde(j: int) -> tuple[str, int]:
        palabras = []
        while j < n and toks[j] not in CORTE and not _DIG.match(toks[j]):
            palabras.append(toks[j])
            j += 1
        return " ".join(palabras), j

    for i, t in enumerate(toks):
        if t in LUGARES and not usados[i] and not fuera[i]:
            nombre, fin = nombre_desde(i + 1)
            if not nombre:
                continue
            tipo = LUGARES[t]
            if tipo == "FINCA":
                d.finca = d.finca or nombre
                fuera[i + 1:fin] = [True] * (fin - i - 1)  # el nombre de la finca no compite como lugar
            elif d.lugar_texto is None or (d.tipo_lugar in ("SECTOR", "CASERIO", "ASENTAMIENTO") and tipo in ("BARRIO", "VEREDA", "CORREGIMIENTO")):
                d.lugar_texto, d.tipo_lugar = nombre, tipo
            usados[i:fin] = [True] * (fin - i)
    d.fuera = fuera

    # 5) Sin palabra clave: el texto del comienzo es el lugar («JORGE ELIECER GAITAN, KR 54…», «LA CONDOR»), o el del
    # trozo que sigue a una referencia inicial («CERCA AL COLEGIO, BARBACOAS»)
    if d.lugar_texto is None:
        nombre, _ = nombre_desde(0)
        if not nombre and n and fuera[0]:
            sig = next((c for c in sorted(cortes) if not fuera[c]), None)
            if sig is not None:
                nombre, _ = nombre_desde(sig)
                nombre = nombre if len(nombre) > 1 else ""
        if nombre and nombre not in NO_LUGAR:
            d.lugar_texto = nombre
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
# Palabras clave que dicen sin duda que el lugar es rural
RURAL_EXPLICITO = {"VEREDA", "CORREGIMIENTO", "CASERIO"}
# Lo nombrado con estas palabras manda sobre otros lugares que no estén dentro de él
ANCLA = {"BARRIO", "URBANIZACION", "VEREDA", "CORREGIMIENTO"}


class _Hallado(NamedTuple):
    lugar: Lugar
    conf: float
    palabra: str | None   # palabra clave que lo nombra («VEREDA»…) o None
    frase: str            # texto que casó
    pos: int = -1         # token donde empieza la frase (-1: casó por parecido, no por alias exacto)


def _del_casco(lg: Lugar) -> bool:
    return lg.zona == "urbana" and lg.padre in (None, "", CASCO)


class Nomenclator:
    """Reconoce barrios, veredas y centros poblados dentro de una dirección."""

    def __init__(self, lugares: list[Lugar]):
        self.lugares = lugares
        self.por_alias: dict[str, list[Lugar]] = {}
        for lg in lugares:
            variantes = set()
            for a in {limpiar(lg.nombre), *map(limpiar, lg.alias)}:
                a = re.sub(r"[^A-Z0-9 ]", " ", a)
                a = re.sub(r"\s+", " ", a).strip()
                if a and a not in NO_LUGAR:
                    # «LA ROMPIDA N 1» también como «LA ROMPIDA # 1», que es como quedan «No. 1» y «#1» al leer
                    variantes |= {a, re.sub(r"\b(?:N|NO|NRO|NUMERO)\s+(?=\d)", "# ", a)}
            for a in variantes:
                self.por_alias.setdefault(a, []).append(lg)
        self.max_n = max((len(a.split()) for a in self.por_alias), default=1)
        self._lista = list(self.por_alias)

    def _elegir(self, candidatos: list[Lugar], palabra: str | None, casco: bool = False) -> Lugar:
        if palabra and palabra in TIPO_PALABRA:
            preferidos = [c for c in candidatos if c.tipo in TIPO_PALABRA[palabra]]
            if preferidos:
                candidatos = preferidos
        # Homónimos («LA PAZ» barrio y vereda): con BARRIO, o con placa del casco y sin VEREDA delante, gana el del casco
        urbano = palabra in ("BARRIO", "URBANIZACION") or (casco and palabra not in RURAL_EXPLICITO)
        return max(candidatos, key=lambda c: (urbano and _del_casco(c), c.lat is not None, PRIORIDAD.get(c.tipo, 0)))

    def _buscar(self, d: Direccion, casco: bool, fuera: list[bool]) -> list[_Hallado]:
        """Alias exactos en la dirección, del más largo al más corto, sin entrar en los tokens `fuera`."""
        toks = d.tokens
        hallados: list[_Hallado] = []
        i = 0
        while i < len(toks):
            for largo in range(min(self.max_n, len(toks) - i), 0, -1):
                frase = " ".join(toks[i:i + largo])
                # Las referencias («FRENTE A LA CEIBA») y el nombre de la finca no son el lugar de la persona, salvo
                # que el alias incluya la palabra clave («HACIENDA ITE»)
                if frase not in self.por_alias or fuera[i] or (any(fuera[i + 1:i + largo]) and toks[i] not in LUGARES):
                    continue
                previa = toks[i - 1] if i else None
                # La palabra clave va delante o dentro del alias («BARRIO CENTRAL», «URBANIZACION LA PAZ»)
                palabra = LUGARES.get(toks[i] if largo > 1 and toks[i] in LUGARES else previa or "")
                # Un nombre de una sola palabra («PARAISO», «GAITAN») solo cuenta si viene tras la palabra clave
                # o si es todo el lugar escrito
                if largo == 1 and not palabra and frase != (d.lugar_texto or ""):
                    continue
                hallados.append(_Hallado(self._elegir(self.por_alias[frase], palabra, casco), 1.0, palabra, frase, i))
                i += largo - 1
                break
            i += 1
        return hallados

    def _de_pueblo(self, d: Direccion, h: _Hallado) -> bool:
        """«… DE LA CONDOR», «… DE SAN MIGUEL DEL TIGRE»: un centro poblado o corregimiento de dos palabras o más que
        dice de dónde es lo nombrado en la referencia."""
        return (h.pos > 0 and " " in h.frase and d.tokens[h.pos - 1] in ("DE", "DEL")
                and any(c.tipo in ("centro_poblado", "corregimiento") for c in self.por_alias.get(h.frase, ())))

    def reconocer(self, d: Direccion, casco: bool = False) -> tuple[Lugar | None, list[Lugar], float]:
        """Devuelve (lugar elegido, todos los encontrados, confianza 0-1).

        `casco`: la dirección trae una placa que cae dentro de la grilla del casco urbano. Entonces gana el homónimo
        del casco, y una vereda o un sector nombrados sin VEREDA/CORREGIMIENTO/CASERIO no se imponen a la placa."""
        fuera = d.fuera if len(d.fuera) == len(d.tokens) else [False] * len(d.tokens)
        hallados = self._buscar(d, casco, fuera)
        if not hallados and not casco and any(fuera):
            # Solo hay lugares dentro de la referencia: «CERCA A LA VEREDA LA UNION» da al menos esa vereda, si la
            # nombra con su palabra clave, y «FRENTE A LA ESCUELA DE LA CONDOR» el centro poblado de la escuela
            # («CERCA DEL PARQUE LA PAZ» y «DETRAS DE LA CEIBA» no dan nada)
            hallados = [h for h in self._buscar(d, casco, [False] * len(fuera))
                        if h.palabra in ANCLA or self._de_pueblo(d, h)]

        if not hallados and d.lugar_texto and d.lugar_texto not in NO_LUGAR and len(d.lugar_texto) >= 4:
            factor = 1.0
            m = process.extractOne(d.lugar_texto, self._lista, scorer=fuzz.ratio, score_cutoff=86)
            if m is None:
                # «SAN MIGUEL DEL TIGRE BARR…»: el alias está contenido en el texto. Nunca al revés: «BOCAS» o
                # «PUERTO» caben en muchos alias y no dicen cuál
                cortos = [a for a in self._lista if 6 <= len(a) <= len(d.lugar_texto)]
                m = process.extractOne(d.lugar_texto, cortos, scorer=fuzz.partial_ratio, score_cutoff=93)
                factor = 0.7
            if m is None and len(d.lugar_texto.split()) >= 2:
                # Abreviado por sus primeras palabras («SAN MIGUEL», «SAN LUIS»), solo si todas llevan al mismo lugar
                pref = [a for a in self._lista if a.startswith(d.lugar_texto + " ")]
                if pref and len({lg.nombre for a in pref for lg in self.por_alias[a]}) == 1:
                    m = (min(pref, key=len), 100.0)
            if m:
                lg = self._elegir(self.por_alias[m[0]], d.tipo_lugar, casco)
                # Un parecido no basta para mandar a una vereda a quien escribió BARRIO o una placa del casco
                if lg.zona != "rural" or not (casco or d.tipo_lugar in ("BARRIO", "URBANIZACION")):
                    hallados.append(_Hallado(lg, round(m[1] / 100 * factor, 3), d.tipo_lugar, d.lugar_texto))

        lugares = [h.lugar for h in hallados]
        if casco:  # la placa del casco pesa más que una vereda o un sector nombrados sin su palabra clave
            hallados = [h for h in hallados if not (h.lugar.zona == "rural" and h.palabra not in RURAL_EXPLICITO
                                                    and h.lugar.tipo in ("vereda", "sector", "caserio"))]
        if not hallados:
            return None, lugares, 0.0
        # Si la dirección nombra un corregimiento o vereda, un barrio del casco con el mismo nombre no aplica
        # (con placa del casco, solo si lo nombra con su palabra clave)
        if any(h.lugar.zona == "rural" and h.lugar.tipo in ("corregimiento", "centro_poblado", "vereda")
               and (not casco or h.palabra in RURAL_EXPLICITO) for h in hallados):
            candidatos = [h for h in hallados if h.lugar.zona == "rural" or (h.lugar.padre and h.lugar.padre != CASCO)]
        else:
            candidatos = hallados
        # Un lugar que contiene a otro de los nombrados es solo contexto («VEREDA EL TOTUMO SAN MIGUEL DEL TIGRE»)
        padres = {h.lugar.padre for h in candidatos if h.lugar.padre and h.lugar.padre != h.lugar.nombre}
        hojas = [h for h in candidatos if h.lugar.nombre not in padres] or candidatos
        # Lo nombrado con BARRIO/VEREDA/CORREGIMIENTO (o el lugar escrito sin palabra clave) manda: otro lugar solo le
        # gana por PRIORIDAD si está dentro de él. Así «VEREDA LA CONDOR SECTOR LAS FLORES» no se va al sector homónimo
        # de otra vereda, y «VEREDA SAN LUIS BELTRAN SECTOR LA PRIMAVERA» sí da el sector
        anclas = [h for h in candidatos if h.palabra in ANCLA or h.frase == d.lugar_texto]
        if anclas:
            dentro = {a.lugar.nombre for a in anclas} | {a.lugar.padre for a in anclas
                                                          if a.lugar.tipo in ("centro_poblado", "caserio") and a.lugar.padre}
            hojas = [h for h in hojas if h in anclas or h.lugar.padre in dentro] or hojas
        mejor = max(hojas, key=lambda h: (h.lugar.lat is not None, PRIORIDAD.get(h.lugar.tipo, 0), h.conf))
        return mejor.lugar, lugares, mejor.conf


def zona_por_texto(d: Direccion) -> str | None:
    """Zona deducida solo del texto, cuando el lugar no está en el nomenclátor."""
    if d.tipo_lugar in ("VEREDA", "CASERIO", "CORREGIMIENTO") or d.finca:
        return "rural"
    if d.tipo_lugar in ("BARRIO", "URBANIZACION") or d.tiene_placa:
        return "urbana"
    return None
