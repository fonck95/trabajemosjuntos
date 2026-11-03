"""Agrupación de trámites por persona y cruce por nombre entre bases.

1. **Agrupar**: la base de trámites trae una fila por solicitud; la misma persona aparece varias veces (reencuesta,
   modificación de ficha…). Se agrupa por nombre normalizado y se unen variantes de digitación («FABIO MAURICO» /
   «FABIO MAURICIO») solo cuando además comparten teléfono, correo o ficha.
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
from rapidfuzz.distance import JaroWinkler

from . import texto as tx
from .lectores import FilaCedula, FilaTramite

UMBRAL_AUTO = 0.93       # nombre casi idéntico y sin rival cercano
UMBRAL_AUTO_TEL = 0.80   # nombre muy parecido y además comparten teléfono o correo
UMBRAL_REVISION = 0.70   # se propone al administrador
MARGEN = 0.08            # distancia mínima con el segundo candidato para unir sin revisar


@dataclass
class PersonaTramites:
    clave: str                         # nombre normalizado del grupo
    nombres: Counter = field(default_factory=Counter)
    fichas: Counter = field(default_factory=Counter)
    telefonos: Counter = field(default_factory=Counter)
    correos: Counter = field(default_factory=Counter)
    filas: list[FilaTramite] = field(default_factory=list)

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

    u = _Union()
    for k in por_nombre:
        u.find(k)
    # Variantes de un mismo nombre que comparten un dato de contacto o la ficha
    por_dato: dict[str, set[str]] = defaultdict(set)
    for k, fs in por_nombre.items():
        for f in fs:
            for t in f.telefonos:
                por_dato["t" + t].add(k)
            if f.correo:
                por_dato["c" + f.correo].add(k)
            if f.ficha:
                por_dato["f" + f.ficha].add(k)
    for claves in por_dato.values():
        if 1 < len(claves) <= 12:
            cl = sorted(claves)
            for i, a in enumerate(cl):
                for b in cl[i + 1:]:
                    if _mismo_nombre_digitado(a, b):
                        u.union(a, b)

    grupos: dict[str, PersonaTramites] = {}
    for k, fs in por_nombre.items():
        r = u.find(k)
        g = grupos.setdefault(r, PersonaTramites(clave=r))
        for f in fs:
            g.filas.append(f)
            g.nombres[f.nombre] += 1
            if f.ficha:
                g.fichas[f.ficha] += 1
            for t in f.telefonos:
                g.telefonos[t] += 1
            if f.correo:
                g.correos[f.correo] += 1
    return list(grupos.values())


def _mismo_nombre_digitado(a: str, b: str) -> bool:
    """Dos escrituras del mismo nombre completo (no dos parientes que comparten teléfono)."""
    ta, tb = a.split(), b.split()
    if abs(len(ta) - len(tb)) > 1:
        return False
    return fuzz.token_sort_ratio(a, b) >= 90 and fuzz.ratio(a, b) >= 85


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
