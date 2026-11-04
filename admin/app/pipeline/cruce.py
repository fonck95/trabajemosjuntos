"""Agrupación de trámites por persona y cruce por nombre entre bases.

1. **Agrupar**: la base de trámites trae una fila por solicitud; la misma persona aparece varias veces (reencuesta,
   modificación de ficha…). Se agrupa por nombre normalizado y se unen variantes de digitación («FABIO MAURICO» /
   «FABIO MAURICIO», «ROJAS» / «ROJA», una inicial de más, los apellidos delante) solo cuando además comparten
   teléfono, correo o ficha; dos nombres de pila distintos («JUAN CARLOS» / «JUAN CAMILO», «JOSE MARIA» /
   «MARIA JOSE») no se unen aunque compartan la ficha del hogar, y uno casi igual («DANIEL» / «DANIELA»,
   «ROSALBA» / «OSALBA») con la misma ficha y teléfono va a revisión. Un mismo nombre con fichas y teléfonos sin nada
   en común son homónimos y quedan como personas separadas.
2. **Cruzar**: cada persona con cédula se compara por nombre contra las personas de la base de trámites. El puntaje
   pondera cada palabra por lo rara que es (un «MARIA» pesa poco, un «ZAPATEIRO» mucho), tolera errores de digitación
   (Jaro-Winkler) y no depende del orden de nombres y apellidos. Compartir teléfono o correo suma evidencia. Lo dudoso
   no se une solo: queda en la cola de revisión del panel.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process
from rapidfuzz.distance import OSA, JaroWinkler

from . import texto as tx
from .lectores import FilaCedula, FilaTramite

UMBRAL_AUTO = 0.93       # nombre casi idéntico y sin rival cercano
UMBRAL_AUTO_TEL = 0.80   # nombre muy parecido y además comparten teléfono o correo
UMBRAL_REVISION = 0.70   # se propone al administrador
MARGEN = 0.08            # distancia mínima con el segundo candidato para unir sin revisar


@dataclass
class PersonaTramites:
    clave: str                         # nombre normalizado del grupo («…#ficha» si es un homónimo separado)
    separado_de: str | None = None     # clave del grupo con el mismo nombre del que se separó (para revisarlo)
    nombres: Counter = field(default_factory=Counter)
    fichas: Counter = field(default_factory=Counter)
    telefonos: Counter = field(default_factory=Counter)
    correos: Counter = field(default_factory=Counter)
    filas: list[FilaTramite] = field(default_factory=list)
    # Claves de grupos con la misma ficha y el mismo teléfono y un nombre de pila casi igual («ROSALBA»/«OSALBA»,
    # «DANIEL»/«DANIELA»): errata o hermanos, lo decide el administrador
    parecidos: list[str] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return self.nombres.most_common(1)[0][0]

    @property
    def ultima(self) -> FilaTramite:
        return max(self.filas, key=lambda f: (f.fecha or "", f.id_externo))

    def tokens(self) -> list[str]:
        return tx.tokens_nombre(self.nombre)


class _Union:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, a: str) -> str:
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def agrupar_tramites(filas: list[FilaTramite]) -> list[PersonaTramites]:
    por_nombre: dict[str, list[FilaTramite]] = defaultdict(list)
    for f in filas:
        por_nombre[tx.nombre_norm(f.nombre)].append(f)
    # En cuántos nombres distintos aparece cada palabra (dos grafías frecuentes son dos nombres reales)
    frec = Counter(t for k in por_nombre for t in set(tx.tokens_nombre(k)))

    u = _Union()
    for k in por_nombre:
        u.find(k)
    # Variantes de un mismo nombre que comparten un dato de contacto o la ficha
    por_dato: dict[str, set[str]] = defaultdict(set)
    fichas_de: dict[str, set[str]] = defaultdict(set)
    tels_de: dict[str, set[str]] = defaultdict(set)
    for k, fs in por_nombre.items():
        for f in fs:
            for t in f.telefonos:
                por_dato["t" + t].add(k)
                tels_de[k].add(t)
            if f.correo:
                por_dato["c" + f.correo].add(k)
            if f.ficha:
                por_dato["f" + f.ficha].add(k)
                fichas_de[k].add(f.ficha)
    vistos: set[tuple[str, str]] = set()
    con_inicial: list[tuple[str, str]] = []   # (nombre sin la inicial, nombre con ella)
    dudosos: list[tuple[str, str, str]] = []  # (nombre, nombre, ficha común)
    for claves in por_dato.values():
        if 1 < len(claves) <= 12:
            cl = sorted(claves)
            for i, a in enumerate(cl):
                for b in cl[i + 1:]:
                    if (a, b) in vistos:
                        continue
                    vistos.add((a, b))
                    r = _comparar_nombres(a, b, frec)
                    if r == "igual":
                        u.union(a, b)
                    elif r == "inicial":
                        con_inicial.append(tuple(sorted((a, b), key=lambda x: len(tx.tokens_nombre(x, True)))))
                    elif r == "dudoso" and fichas_de[a] & fichas_de[b] and tels_de[a] & tels_de[b]:
                        dudosos.append((a, b, min(fichas_de[a] & fichas_de[b])))
    # Una inicial de más («JUAN C PEREZ GOMEZ» / «JUAN PEREZ GOMEZ») es la misma persona, salvo que el nombre sin
    # inicial sirva también para otra («JUAN D PEREZ GOMEZ»): entonces no se sabe de cuál de los dos es
    largos_de: dict[str, set[str]] = defaultdict(set)
    for corto, largo in con_inicial:
        largos_de[u.find(corto)].add(u.find(largo))
    for raiz, largos in largos_de.items():
        if len({u.find(x) for x in largos}) == 1:
            u.union(raiz, next(iter(largos)))

    por_grupo: dict[str, list[FilaTramite]] = defaultdict(list)
    for k, fs in por_nombre.items():
        por_grupo[u.find(k)].extend(fs)
    grupos: list[PersonaTramites] = []
    for r, fs in por_grupo.items():
        partes = _separar_homonimos(fs)
        for i, parte in enumerate(partes):
            # El homónimo separado lleva su ficha en la clave para que reimportar lo vuelva a encontrar
            g = PersonaTramites(clave=r if i == 0 else f"{r}#{min(f.ficha for f in parte if f.ficha)}",
                                separado_de=r if i else None)
            for f in parte:
                g.filas.append(f)
                g.nombres[f.nombre] += 1
                if f.ficha:
                    g.fichas[f.ficha] += 1
                for t in f.telefonos:
                    g.telefonos[t] += 1
                if f.correo:
                    g.correos[f.correo] += 1
            grupos.append(g)
    # Los casi iguales que quedaron separados van a revisión entre las fichas que comparten
    if dudosos:
        grupo_de = {(tx.nombre_norm(f.nombre), f.ficha): g for g in grupos for f in g.filas}
        for a, b, ficha in dudosos:
            ga, gb = grupo_de.get((a, ficha)), grupo_de.get((b, ficha))
            if ga is not None and gb is not None and ga is not gb and gb.clave not in ga.parecidos \
                    and ga.clave not in gb.parecidos:
                ga.parecidos.append(gb.clave)
    return grupos


def _separar_homonimos(filas: list[FilaTramite]) -> list[list[FilaTramite]]:
    """Parte un grupo cuando trae personas distintas con el mismo nombre: partes con ficha y teléfono propios y sin
    ningún dato en común («JOSE GARCIA» de dos hogares). Lo que no tiene ficha y teléfono se queda con la primera
    parte, porque la misma persona puede pedir una ficha nueva o no dar el teléfono."""
    u = _Union()
    for i, f in enumerate(filas):
        u.find(f"#{i}")
        for dato in [*("t" + t for t in f.telefonos), *(["c" + f.correo] if f.correo else []),
                     *(["f" + f.ficha] if f.ficha else [])]:
            u.union(f"#{i}", dato)
    partes: dict[str, list[FilaTramite]] = defaultdict(list)
    for i, f in enumerate(filas):
        partes[u.find(f"#{i}")].append(f)
    # La primera es la del trámite más antiguo: conserva la clave de siempre
    orden = sorted(partes.values(), key=lambda p: min((f.fecha or "9999", f.id_externo) for f in p))
    firmes = [p for p in orden if any(f.ficha for f in p) and any(f.telefonos for f in p)]
    if len(firmes) < 2:
        return [filas]
    resto = [f for p in orden if not any(p is q for q in firmes) for f in p]
    return [firmes[0] + resto, *firmes[1:]]


def _mismo_nombre_digitado(a: str, b: str, frec: Counter | None = None) -> bool:
    """Dos escrituras del mismo nombre completo (no dos parientes que comparten teléfono o ficha)."""
    return _comparar_nombres(a, b, frec or Counter()) in ("igual", "inicial")


def _alineados(ta: list[str], tb: list[str]):
    """(k, diferencias) entre `ta` y cada rotación de `tb`: k=0 es el mismo orden; las demás cubren «APELLIDOS NOMBRES»
    frente a «NOMBRES APELLIDOS». Las diferencias son (posición, palabra de ta, palabra de tb)."""
    for k in range(len(tb)):
        rb = tb[k:] + tb[:k]
        yield k, [(p, x, y) for p, (x, y) in enumerate(zip(ta, rb)) if x != y]


def _comparar_nombres(a: str, b: str, frec: Counter) -> str:
    """«igual»: el mismo nombre mal escrito; «inicial»: igual salvo una inicial de más («JUAN C PEREZ GOMEZ» /
    «JUAN PEREZ GOMEZ»); «dudoso»: un nombre de pila casi igual que también puede ser el de un hermano
    («ROSALBA»/«OSALBA», «DANIEL»/«DANIELA»); «distinto».

    Palabra por palabra y en orden: todas iguales salvo a lo sumo una, y esa debe ser una errata («MAURICO»/«MAURICIO»,
    «ROJAS»/«ROJA»), no otro nombre («CARLOS»/«CAMILO», «JUAN C»/«JUAN D»). Los mismos nombres de pila en otro orden
    («JOSE MARIA»/«MARIA JOSE») son dos personas."""
    ta, tb = tx.tokens_nombre(a, iniciales=True), tx.tokens_nombre(b, iniciales=True)
    if len(ta) < 2 or len(tb) < 2:
        return "distinto"
    if len(ta) != len(tb):
        corto, largo = sorted((ta, tb), key=len)
        if len(largo) == len(corto) + 1 and len(corto) >= 3:
            for q, t in enumerate(largo):
                if len(t) == 1 and any(not difs for _, difs in _alineados(corto, largo[:q] + largo[q + 1:])):
                    return "inicial"
        return "distinto"
    n = len(ta)
    resultado = "distinto"
    for k, difs in _alineados(ta, tb):
        if not difs:
            return "igual"
        if len(difs) == 1:
            p, x, y = difs[0]
            # En el orden de siempre, con tres palabras o más las dos últimas son apellidos; con dos, la segunda
            r = _errata(x, y, frec, apellido=not k and p >= max(1, n - 2))
            if r == "igual":
                return "igual"
            if r == "dudoso":
                resultado = "dudoso"
    return resultado


def _errata(x: str, y: str, frec: Counter, apellido: bool = False) -> str:
    """¿Son `x` y `y` la misma palabra mal escrita? «igual», «distinto» o «dudoso»: sería una errata en un apellido,
    pero en un nombre de pila puede ser el de un hermano.

    En un hogar dos personas se distinguen por el nombre de pila, no por una letra de un apellido: en los apellidos
    vale cualquier errata pequeña («ROJAS»/«ROJA», «PEREZ»/«PREZ», «BUELVAS»/«BUELVSA»). En los nombres de pila, además,
    la primera letra debe coincidir, la palabra corta debe tener 5 letras o más y no puede ser el masculino o el
    femenino del otro (DANIEL/DANIELA, ANDRES/ANDREA, MARIO/MARIA)."""
    if tx.fonetico(x) == tx.fonetico(y):  # JHON/JOHN, YESICA/JESSICA, LEGUIZAMO/LEGUISAMO
        return "igual"
    corta, larga = sorted((x, y), key=len)
    if len(corta) < 2 or OSA.distance(x, y) > (1 if len(corta) < 7 else 2):
        return "distinto"
    # Dos grafías que se repiten en muchos nombres distintos son dos nombres reales (y no una errata del otro)
    fx, fy = frec.get(x, 0), frec.get(y, 0)
    if min(fx, fy) >= 3 and min(fx, fy) >= 0.2 * max(fx, fy):
        return "distinto"
    if apellido:
        return "igual"
    if x[0] != y[0] or len(corta) < 5 or _genero(x, y):
        return "dudoso"
    return "igual"


def _genero(x: str, y: str) -> bool:
    """¿Difieren en la A final del femenino? DANIEL/DANIELA, MARIO/MARIA, ANDRES/ANDREA, también con otra errata
    (GABRIIEL/GABRIELA); no una letra cambiada de sitio (BUELVAS/BUELVSA, FLORALBA/FLORALAB)."""
    if (x[-1] == "A") == (y[-1] == "A"):
        return False
    a, o = (x, y) if x[-1] == "A" else (y, x)
    return min(OSA.distance(a[:-1], o), OSA.distance(a[:-1], o[:-1])) < OSA.distance(a, o)


# ───────────────────────────── Cruce por nombre ─────────────────────────────

class ComparadorNombres:
    """Puntaje 0-1 entre dos nombres, ponderado por la rareza de cada palabra."""

    def __init__(self, nombres: list[list[str]]):
        df = Counter()
        for toks in nombres:
            df.update(set(toks))
        self.n = max(len(nombres), 1)
        self.df = df
        self.vocab = list(df)

    def idf(self, t: str) -> float:
        return math.log((self.n + 1) / (self.df.get(t, 0) + 1)) + 1.0

    @staticmethod
    def sim_token(a: str, b: str) -> float:
        if a == b:
            return 1.0
        fa, fb = tx.fonetico(a), tx.fonetico(b)
        if fa == fb:
            return 0.97
        if len(a) < 4 or len(b) < 4 or fa[0] != fb[0]:
            return 0.0
        s = max(JaroWinkler.similarity(a, b), JaroWinkler.similarity(fa, fb))
        return s if s >= 0.93 else 0.0

    def puntaje(self, a: list[str], b: list[str]) -> tuple[float, int]:
        """(puntaje, palabras que coinciden). Exige al menos dos palabras en común."""
        if not a or not b:
            return 0.0, 0
        corto, largo = (a, b) if len(a) <= len(b) else (b, a)
        libres = list(largo)
        suma_c = suma_l = 0.0
        coinciden = 0
        for t in corto:
            mejor, sim = None, 0.0
            for u in libres:
                s = self.sim_token(t, u)
                if s > sim:
                    mejor, sim = u, s
            if mejor is not None:
                libres.remove(mejor)
                coinciden += 1
                suma_c += self.idf(t) * sim
                suma_l += self.idf(mejor) * sim
        total_c = sum(self.idf(t) for t in corto)
        total_l = sum(self.idf(t) for t in largo)
        if coinciden < 2:
            return 0.0, coinciden
        cobertura_corto = min(1.0, suma_c / total_c)
        cobertura_largo = min(1.0, suma_l / total_l)
        p = 0.65 * cobertura_corto + 0.35 * cobertura_largo
        # Una palabra del nombre corto que no aparece en el largo es un nombre distinto (hermanos, madre e hija):
        # pesa en contra, no solo deja de sumar
        p *= 0.75 ** (len(corto) - coinciden)
        return p, coinciden


@dataclass
class Candidato:
    indice: int            # posición en la lista de personas de trámites
    puntaje: float         # puntaje final (nombre + evidencia)
    puntaje_nombre: float
    palabras: int
    telefono: bool
    correo: bool


@dataclass
class ResultadoCruce:
    fila: FilaCedula
    estado: str            # auto | revision | sin_coincidencia
    candidatos: list[Candidato]

    @property
    def mejor(self) -> Candidato | None:
        return self.candidatos[0] if self.candidatos else None


def cruzar(personas: list, filas: list[FilaCedula]) -> list[ResultadoCruce]:
    """`personas`: objetos con .nombre, .telefonos y .correos (colecciones). Devuelve un resultado por fila."""
    tok_p = [tx.tokens_nombre(p.nombre) for p in personas]
    tok_c = [tx.tokens_nombre(f.nombre) for f in filas]
    comp = ComparadorNombres(tok_p + tok_c)

    indice: dict[str, set[int]] = defaultdict(set)
    for i, toks in enumerate(tok_p):
        for t in toks:
            indice[t].add(i)
    vocab = list(indice)
    fon: dict[str, set[str]] = defaultdict(set)
    for v in vocab:
        fon[tx.fonetico(v)].add(v)

    resultados = []
    for f, toks in zip(filas, tok_c):
        posibles: Counter = Counter()
        for t in toks:
            vecinos = {t} if t in indice else set()
            vecinos |= fon.get(tx.fonetico(t), set())
            if len(t) >= 4:
                for v, s, _ in process.extract(t, vocab, scorer=fuzz.ratio, limit=4, score_cutoff=88):
                    vecinos.add(v)
            for v in vecinos:
                for i in indice[v]:
                    posibles[i] += 1
        tels, mail = set(f.telefonos), f.correo
        cands: list[Candidato] = []
        for i, n in posibles.items():
            if n < 2:
                continue
            pn, palabras = comp.puntaje(toks, tok_p[i])
            if pn <= 0:
                continue
            tel = bool(tels & set(personas[i].telefonos))
            cor = bool(mail and mail in personas[i].correos)
            # El teléfono o el correo compartido confirma un nombre parecido; no vuelve parecido un nombre distinto
            # (en una familia todos dan el mismo celular)
            final = min(1.0, pn + ((0.15 if tel else 0) + (0.15 if cor else 0) if pn >= 0.6 else 0))
            cands.append(Candidato(i, round(final, 4), round(pn, 4), palabras, tel, cor))
        cands.sort(key=lambda c: (c.puntaje, c.puntaje_nombre), reverse=True)
        cands = cands[:3]
        estado = "sin_coincidencia"
        if cands:
            m = cands[0]
            segundo = cands[1].puntaje if len(cands) > 1 else 0.0
            evidencia = m.telefono or m.correo
            if (m.puntaje_nombre >= UMBRAL_AUTO and (m.puntaje - segundo >= MARGEN or evidencia)) or \
               (m.puntaje_nombre >= UMBRAL_AUTO_TEL and evidencia and m.puntaje - segundo >= MARGEN / 2):
                estado = "auto"
            elif m.puntaje >= UMBRAL_REVISION:
                estado = "revision"
        resultados.append(ResultadoCruce(f, estado, cands if estado != "sin_coincidencia" else []))
    return resultados
