"""Unificación en bloque de fichas duplicadas: grupos de coincidencias, señales, nivel de confianza, vista previa de la
ficha unida y resolución en lote.

La cola de coincidencias se revisaba par por par. Aquí los pares pendientes se juntan en **grupos**, los componentes
conexos (A~B y B~C forman {A, B, C}): unir A con B y luego B con C es unir los tres, así que se deciden juntos. Cada
grupo trae:

* las **señales** de cada par, calculadas sobre las fichas de ahora: el `puntaje` y el `detalle` guardados se
  calcularon contra la ficha que existía al proponer el par y, si después se unió con otra (`_reapuntar_coincidencias`),
  ya no dicen lo mismo;
* un **nivel** que ordena la revisión: «alta» se puede unir en lote, «media» y «baja» se miran una por una y
  «bloqueada» no se puede unir entera (dos cédulas distintas o una decisión humana anterior de que son distintas);
* la **vista previa** de la ficha unida: qué valor quedaría en cada campo, de qué fuente y qué pasaría a alternos.

Lo usan `GET /api/coincidencias/grupos` y `POST /api/coincidencias/lote` (api/calidad.py), solo de A y K: llevan las
fuentes reales (también «cedulas»), las listas y la procedencia. Nada de esto llega al asistente (no tiene herramienta
para unir y `agente/minimizar.py` no deja pasar fuentes ni coincidencias) ni a P o C.

Escala a miles de pares: una consulta por colección (coincidencias, personas, lugares) y el resto en memoria; nunca
una consulta por par.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from typing import Any, Iterable

from fastapi import HTTPException
from pymongo.database import Database

from . import db as bd
from . import modelo
from .pipeline import cruce
from .pipeline import texto as tx

NIVELES = ("alta", "media", "baja", "bloqueada")  # de mejor a peor: el nivel de un grupo es el peor de sus pares
MOTIVOS = ("cruce_cedula", "nombre_telefono", "homonimo", "variante", "reporte", "alta_simultanea")
# Señales a favor que casi solo comparte una misma persona (un número o un correo propio, la fecha exacta)
FUERTES = frozenset({"mismo_telefono", "mismo_correo", "cedula_anterior", "misma_fecha"})
UMBRAL_ALTA = 0.85        # puntaje del nombre que, con una señal fuerte, vuelve «alta» un par
PUNTAJE_SIN_DATO = 0.75   # los reportes y las altas simultáneas no traen puntaje: cuentan como un nombre parecido
TOPE_FICHAS = 6           # un grupo más grande suele ser una cadena por nombres comunes, no una persona
EDAD_PARECIDA = 2         # años entre los nacimientos (la edad declarada tiene ±1 año de error)
EDAD_DISTINTA = 5
TOPE_POR_PAGINA = 100
MAX_GRUPOS_LOTE, MAX_PARES_GRUPO, MAX_EXCLUIR = 50, 60, 20
TURNO = "importando"      # el mismo turno de la importación: unir en lote e importar se excluyen

# Lo que se lee de cada ficha: lo necesario para las señales, la comparación y la vista previa. Sin `notas`,
# `asistencias`, `origen`, `alternos` ni sensibles: con miles de pares, traer la ficha entera dominaría la respuesta.
PROYECCION = {k: 1 for k in (
    "nombre", "cedula", "cedulas_anteriores", "sexo", "edad", "edad_ref", "creado_en", "fecha_nacimiento", "nac_aprox",
    "nac_exacta", "telefono", "telefono2", "telefonos.numero", "telefonos.fuentes", "correo", "direccion",
    "direccion_norm", "lugar_id", "lugar_texto", "lat", "geo_precision", "geo_manual", "ficha", "votacion.puesto_id",
    "votacion.mesa", "fuentes", "procedencia", "tramites.telefono", "tramites.correo", "tramites.ficha", "listas",
    "completitud", "consentimiento")}

# (campo, etiqueta) de la vista previa, en el orden en que se muestran
CAMPOS_VISTA = (("nombre", "Nombre"), ("cedula", "Cédula"), ("telefonos", "Teléfonos"), ("correo", "Correo"),
                ("direccion", "Dirección"), ("lugar", "Barrio o vereda"), ("sexo", "Sexo"), ("edad", "Edad"),
                ("fecha_nacimiento", "Fecha de nacimiento"))
# Campos que la unión llena si el destino no los tiene y, si los tiene con otro valor, deja el del origen en `alternos`
# (los de `modelo.CAMPOS_PROCEDENCIA` que se muestran). La cédula no deja alternos: dos cédulas distintas no se unen
CON_ALTERNOS = frozenset({"correo", "direccion", "sexo", "edad", "fecha_nacimiento"})
# Fuentes que escribe una persona del equipo (ya con `clave_fuente`): dos fichas suyas no son «dos filas de la misma
# base», son el duplicado de siempre (la misma persona dada de alta dos veces: lo que buscan las altas simultáneas)
DEL_EQUIPO = frozenset({"equipo", "reunion", "consultor"})
NOMBRE_FUENTE = {"tramites": "trámites", "cedulas": "la base con cédula", "planilla": "planillas de campo"}


# ───────────────────────────── Lectura ─────────────────────────────

def cargar_fichas(db: Database, ids: Iterable[int]) -> dict[int, dict]:
    """Las fichas activas de `ids` en una sola consulta y con la proyección acotada (`PROYECCION`)."""
    ids = list(set(ids))
    if not ids:
        return {}
    return {p["_id"]: p for p in db.personas.find({"_id": {"$in": ids}, **bd.ACTIVA}, PROYECCION)}


def nombres_de_lugares(db: Database) -> dict[int, str]:
    return {l["_id"]: l.get("nombre") for l in db.lugares.find({}, {"nombre": 1})}


def rechazos_entre(db: Database, ids: Iterable[int]) -> set[frozenset]:
    """Pares de fichas activas de `ids` que una persona ya marcó como distintas, también los que se marcaron con una
    ficha que después se unió a una de ellas: un rechazo no se reapunta al unir (`_reapuntar_coincidencias` solo mueve
    las pendientes), así que aquí cada ficha unida sube a su ficha activa (`fusionada_en` siempre apunta a la raíz:
    `_unir_en` reencadena las que apuntaban al origen). Dos consultas, sean cuantas sean las fichas."""
    ids = set(ids)
    if len(ids) < 2:
        return set()
    raiz = {i: i for i in ids}
    for p in db.personas.find({"fusionada_en": {"$in": list(ids)}}, {"fusionada_en": 1}):
        raiz[p["_id"]] = p["fusionada_en"]
    todos = list(raiz)
    out: set[frozenset] = set()
    for c in db.coincidencias.find({"estado": "rechazada", "persona_id": {"$in": todos},
                                    "candidato_id": {"$in": todos}}, {"persona_id": 1, "candidato_id": 1}):
        a, b = raiz[c["persona_id"]], raiz[c["candidato_id"]]
        if a != b:
            out.add(frozenset((a, b)))
    return out


def detalle_y_nota(detalle: Any) -> tuple[dict, str | None]:
    """El `detalle` de una coincidencia siempre como dict, y la nota aparte. Tiene forma variable: un dict en las de la
    importación, un texto en las altas simultáneas y en el reporte con nota, y None en el reporte sin nota (con None la
    pestaña se caía al leer `detalle.homonimo`)."""
    if isinstance(detalle, dict):
        nota = detalle.get("nota")
        return dict(detalle), nota.strip() if isinstance(nota, str) and nota.strip() else None
    if isinstance(detalle, str) and detalle.strip():
        return {}, detalle.strip()
    return {}, None


# ───────────────────────────── Señales ─────────────────────────────

def _senal(clave: str, texto: str) -> dict:
    return {"clave": clave, "texto": texto}


def numeros(p: dict) -> set[str]:
    """Todos sus números, como `_Almacen.numeros` de la importación: la lista, los heredados y los de los trámites."""
    tels = {t.get("numero") for t in modelo.telefonos_de(p)} | {p.get("telefono"), p.get("telefono2")}
    tels |= {x for tr in p.get("tramites") or [] for x in str(tr.get("telefono") or "").split(";")}
    return {str(t).strip() for t in tels if t not in (None, "") and str(t).strip()}


def correos(p: dict) -> set[str]:
    """El correo de la ficha y los de sus trámites."""
    todos = [p.get("correo"), *(tr.get("correo") for tr in p.get("tramites") or [])]
    return {str(c).strip().lower() for c in todos if c and str(c).strip()}


def fichas_hogar(p: dict) -> set[str]:
    """La ficha del hogar (encuesta) de la persona y la de cada trámite suyo."""
    todas = [p.get("ficha"), *(tr.get("ficha") for tr in p.get("tramites") or [])]
    return {str(f).strip() for f in todas if f and str(f).strip()}


def nacimiento(p: dict) -> tuple[date | None, bool]:
    """(nacimiento, ¿exacto?): `nac_aprox`/`nac_exacta` guardados (los deriva `derivar`) o, en una ficha que no los
    tiene, calculados de la fecha o de la edad declarada."""
    nac = modelo.fecha_valida(p.get("nac_aprox"))
    if nac is not None:
        return nac, bool(p.get("nac_exacta"))
    if p.get("edad") is None and modelo.vacio(p.get("fecha_nacimiento")):
        return None, False
    c = modelo.calcular_nac(p)
    return modelo.fecha_valida(c["nac_aprox"]), bool(c["nac_exacta"])


def _sexo(p: dict) -> str | None:
    s = str(p.get("sexo") or "").strip().upper()
    return s or None


def _puesto(p: dict) -> tuple[Any, Any]:
    v = p.get("votacion")
    return (v.get("puesto_id"), v.get("mesa")) if isinstance(v, dict) else (None, None)


def clave_fuente(f: Any) -> str | None:
    """«manual» y «panel» son lo mismo (lo escribió el equipo); el resto, tal cual."""
    if not f:
        return None
    return "equipo" if f in ("manual", "panel") else str(f)


def _fuentes(p: dict) -> set[str]:
    return {k for f in p.get("fuentes") or [] if (k := clave_fuente(f))}


def _palabras_en_comun(ta: list[str], tb: list[str]) -> int:
    """Palabras del nombre que coinciden, contando la fonética (JHON/JOHN) y sin usar dos veces la misma."""
    return sum((Counter(tx.fonetico(t) for t in ta) & Counter(tx.fonetico(t) for t in tb)).values())


def _pares_de_pila(ta: list[str], tb: list[str]) -> list[tuple[str, str]]:
    """Las palabras distintas que caen donde va un nombre de pila, alineando los dos nombres como `cruce._alineados`
    (también «APELLIDOS NOMBRES» frente a «NOMBRES APELLIDOS»).

    Con el mismo largo se toma la rotación que menos palabras deja distintas; en el orden de siempre los nombres de pila
    son las palabras antes de los dos apellidos (como en `cruce._comparar_nombres`), y en otro orden no se sabe cuáles
    son, así que cuentan todas. Con largos distintos (falta una palabra), solo las primeras, y solo si ninguna de las
    dos aparece en el otro nombre: «MARIA DEL CARMEN RUIZ» / «CARMEN RUIZ» es un nombre omitido, no otro nombre."""
    fa, fb = [tx.fonetico(t) for t in ta], [tx.fonetico(t) for t in tb]
    if len(ta) == len(tb):
        n = len(ta)
        k, difs = min(cruce._alineados(fa, fb), key=lambda kd: (len(kd[1]), kd[0]))
        return [(ta[p], tb[(p + k) % n]) for p, _, _ in difs if k or p < max(1, n - 2)]
    if fa[0] == fb[0] or fa[0] in fb or fb[0] in fa:
        return []
    return [(ta[0], tb[0])]


def nombre_de_pila_distinto(nombre_a: Any, nombre_b: Any) -> dict | None:
    """Señal en contra si el nombre de pila es otro («JUAN» / «CARLOS») o casi el mismo pero de otro género o con otra
    letra al comienzo («DANIEL» / «DANIELA», «ROSALBA» / «OSALBA»): en un hogar dos personas se distinguen por el nombre
    de pila, y esos son justo los pares «variante» que el cruce deja para revisar. Usa las reglas del cruce
    (`_comparar_nombres`, `_errata`, `_genero`, la fonética): una errata («MAURICO» / «MAURICIO») no cuenta."""
    if cruce._comparar_nombres(str(nombre_a or ""), str(nombre_b or ""), Counter()) in ("igual", "inicial"):
        return None
    ta, tb = tx.tokens_nombre(nombre_a), tx.tokens_nombre(nombre_b)
    if len(ta) < 2 or len(tb) < 2:
        return None
    for x, y in _pares_de_pila(ta, tb):
        r = cruce._errata(x, y, Counter())
        if r == "igual":
            continue
        if r == "distinto":
            return _senal("nombre_pila_distinto", f"Nombre de pila distinto ({x} / {y})")
        # «dudoso»: casi la misma palabra (`_genero` solo dice algo de dos palabras así de cercanas)
        if cruce._genero(x, y):
            return _senal("nombre_pila_distinto", f"Nombre de pila de otro género ({x} / {y})")
        return _senal("nombre_pila_distinto", f"Nombre de pila casi igual ({x} / {y}): ¿errata o pariente?")
    return None


def senales(a: dict, b: dict, coincidencia: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(a favor, en contra) de que las fichas `a` y `b` sean la misma persona, cada señal `{clave, texto}`.

    A favor, fuertes: un teléfono o un correo en común (de la ficha o de sus trámites), la cédula de una entre las
    anteriores de la otra, la misma fecha de nacimiento exacta. Medias y débiles: la misma dirección o el mismo barrio,
    la misma ficha del hogar (es el mismo hogar: también la comparten los parientes), una edad parecida, el mismo puesto
    de votación, el nombre igual o varias palabras en común, que una sola tenga cédula (la unión la completa) y que
    vengan de fuentes que se complementan (trámites y base con cédula, el caso típico).

    En contra: sexo distinto, edades muy distintas, dos fechas exactas distintas, otro nombre de pila, un homónimo sin
    nada en común (`homonimo` sin teléfono, correo ni fecha) y dos filas de la misma base importada sin cédula (si la
    base las trajo separadas, suele ser por algo). `coincidencia` (el par guardado) solo se usa para el motivo."""
    favor: list[dict] = []
    contra: list[dict] = []
    tel = numeros(a) & numeros(b)
    if tel:
        favor.append(_senal("mismo_telefono", "Mismo teléfono" if len(tel) == 1 else f"{len(tel)} teléfonos en común"))
    if correos(a) & correos(b):
        favor.append(_senal("mismo_correo", "Mismo correo"))
    ca, cb = a.get("cedula"), b.get("cedula")
    if (ca and ca in (b.get("cedulas_anteriores") or [])) or (cb and cb in (a.get("cedulas_anteriores") or [])):
        favor.append(_senal("cedula_anterior", "La cédula de una figura como anterior en la otra"))
    (na, ea), (nb, eb) = nacimiento(a), nacimiento(b)
    misma_fecha = bool(na and nb and ea and eb and na == nb)
    if misma_fecha:
        favor.append(_senal("misma_fecha", "Misma fecha de nacimiento"))
    misma_dir = bool(a.get("direccion_norm") and a.get("direccion_norm") == b.get("direccion_norm"))
    if misma_dir:
        favor.append(_senal("misma_direccion", "Misma dirección"))
    elif a.get("lugar_id") is not None and a.get("lugar_id") == b.get("lugar_id"):  # la dirección ya lo incluye
        favor.append(_senal("mismo_lugar", "Mismo barrio o vereda"))
    if fichas_hogar(a) & fichas_hogar(b):
        favor.append(_senal("misma_ficha", "Misma ficha del hogar (también la comparten los parientes)"))
    anios = abs((na - nb).days) / 365.25 if na and nb else None
    if anios is not None and not (ea and eb) and anios <= EDAD_PARECIDA:
        favor.append(_senal("edad_parecida", "Edad parecida"))
    (pa, ma), (pb, mb) = _puesto(a), _puesto(b)
    if pa is not None and pa == pb:
        favor.append(_senal("mismo_puesto", "Mismo puesto y mesa de votación" if ma is not None and ma == mb
                            else "Mismo puesto de votación"))
    ta, tb = tx.tokens_nombre(a.get("nombre")), tx.tokens_nombre(b.get("nombre"))
    if tx.nombre_norm(a.get("nombre")) and tx.nombre_norm(a.get("nombre")) == tx.nombre_norm(b.get("nombre")):
        favor.append(_senal("nombre_igual", "Mismo nombre"))
    elif (n := _palabras_en_comun(ta, tb)) >= 2:
        favor.append(_senal("palabras", f"{n} palabras del nombre en común"))
    if bool(ca) != bool(cb):
        favor.append(_senal("completa_cedula", "Solo una tiene cédula: la unión la completa"))
    fa, fb = _fuentes(a), _fuentes(b)
    if fa and fb and not fa & fb:
        favor.append(_senal("fuentes_complementarias", "Vienen de fuentes distintas que se complementan"))

    sa, sb = _sexo(a), _sexo(b)
    if sa and sb and sa != sb:
        contra.append(_senal("sexo_distinto", "Sexo distinto"))
    if anios is not None and anios > EDAD_DISTINTA:
        contra.append(_senal("edad_distinta", f"Edades muy distintas (unos {round(anios)} años)"))
    if na and nb and ea and eb and na != nb:
        contra.append(_senal("fecha_distinta", "Fechas de nacimiento distintas"))
    pila = nombre_de_pila_distinto(a.get("nombre"), b.get("nombre"))
    if pila:
        contra.append(pila)
    motivo = (coincidencia or {}).get("motivo")
    if motivo == "homonimo" and not tel and not correos(a) & correos(b) and not misma_fecha:
        contra.append(_senal("homonimo_sin_evidencia",
                             "Mismo nombre sin teléfono, correo ni fecha en común: pueden ser homónimos"))
    if not ca and not cb and fa == fb and len(fa) == 1 and not fa & DEL_EQUIPO:
        f = next(iter(fa))
        contra.append(_senal("misma_fuente", f"Las dos vienen solo de {NOMBRE_FUENTE.get(f, f)} y sin cédula"))
    return favor, contra


def nivel_par(puntaje: float | None, favor: list[dict], contra: list[dict]) -> str:
    """«baja» con alguna señal en contra; «alta» sin señales en contra y con un nombre muy parecido y una señal fuerte,
    o con dos señales fuertes; si no, «media». Sin puntaje (reportes, altas simultáneas) cuenta como 0,75. `puntaje`
    es el del nombre (`puntaje_del_nombre`)."""
    if contra:
        return "baja"
    fuertes = sum(s["clave"] in FUERTES for s in favor)
    p = PUNTAJE_SIN_DATO if puntaje is None else puntaje
    return "alta" if (p >= UMBRAL_ALTA and fuertes >= 1) or fuertes >= 2 else "media"


def puntaje_del_nombre(c: dict) -> float | None:
    """El puntaje con que se decide el nivel: el del nombre solo (`detalle.puntaje_nombre`, el que guarda el cruce)
    cuando lo hay. El `puntaje` final ya suma 0,15 por el teléfono y 0,15 por el correo en común (`cruce.cruzar`):
    contarlo y además contar «mismo teléfono» como señal fuerte volvería «alta» un nombre de 0,70 con el celular de la
    familia, justo lo que la importación no quiso unir sola (exige 0,80 de nombre con teléfono)."""
    detalle, _ = detalle_y_nota(c.get("detalle"))
    pn = detalle.get("puntaje_nombre")
    return float(pn) if isinstance(pn, (int, float)) and not isinstance(pn, bool) else c.get("puntaje")


def _peor(*niveles: str) -> str:
    return max(niveles, key=NIVELES.index)


# ───────────────────────────── Destino, orden de unión y vista previa ─────────────────────────────

def _llave_destino(p: dict) -> tuple:
    return bool(p.get("cedula")), p.get("completitud") or 0, -p["_id"]


def destino_de(miembros: Iterable[dict]) -> int:
    """Qué ficha se conserva al unir: la que tiene cédula; si ninguna (o varias), la más completa; con empate, la de
    menor id (estable: no depende del orden en que llegaron, como sí pasaba con `conservar_por_defecto` en un par)."""
    return max(miembros, key=_llave_destino)["_id"]


def orden_union(miembros: Iterable[dict], destino: int) -> list[dict]:
    """El destino primero y luego el resto por (tiene cédula, completitud) de mayor a menor y menor id: así se unen en
    estrella (todas en el destino, nunca en cadena) y la primera que llena un campo vacío es la más confiable."""
    lista = list(miembros)
    return [p for p in lista if p["_id"] == destino] + sorted(
        (p for p in lista if p["_id"] != destino), key=_llave_destino, reverse=True)


def _fuente(p: dict, campo: str) -> str | None:
    """La fuente del valor de `campo` en la ficha: la de `procedencia` o, si no tiene, la primera de `fuentes` (la que
    la creó)."""
    prov = (p.get("procedencia") or {}).get(campo)
    if isinstance(prov, dict) and prov.get("fuente"):
        return prov["fuente"]
    return (p.get("fuentes") or [None])[0]


def _lugar(p: dict, lugares: dict) -> str | None:
    return lugares.get(p.get("lugar_id")) or p.get("lugar_texto") or None


def _edad(p: dict) -> int | None:
    """La edad declarada llevada a hoy, la que se muestra (la fecha de nacimiento va en su propio campo). La unión no
    compara esta sino la declarada (ver `_valor`), pero la ficha unida se queda con la edad y la `edad_ref` de la misma
    ficha, así que la edad de hoy de la ficha unida es justo esta."""
    return modelo.edad_efectiva({"edad": p.get("edad"), "edad_ref": p.get("edad_ref"), "creado_en": p.get("creado_en")})


def _valor(p: dict, campo: str) -> Any:
    """El valor de `campo` tal como lo compara la unión (`_pipeline_fusion` con `modelo.comparable`): lo guardado. En
    la edad es la declarada, no la llevada a hoy: 40 años declarados en 2016 y 40 declarados hoy no dejan alterno
    aunque hoy sean 50 y 40, y 40 de 2020 y 46 de hoy sí lo dejan aunque hoy sean los mismos 46."""
    v = p.get(campo)
    return None if modelo.vacio(v) else v


def _texto(v: Any) -> str | None:
    return None if v is None or modelo.vacio(v) else str(v)


def _telefonos(p: dict) -> list[str]:
    """Los números de la lista de la ficha, con los heredados que el código viejo dejó fuera (como los ve la unión)."""
    return list(dict.fromkeys(str(t["numero"]) for t in modelo.reconciliar_telefonos(p) if t.get("numero")))


def _fuente_telefonos(p: dict) -> str | None:
    """La fuente de los teléfonos de la ficha: la primera de su número principal (el primero de la lista) o, si ese
    número no anota ninguna, la de la ficha (`_fuente`). None si no tiene teléfonos. Los teléfonos no van en
    `procedencia`: cada número lleva sus `fuentes`."""
    for t in modelo.reconciliar_telefonos(p):
        if t.get("numero"):
            return (t.get("fuentes") or [None])[0] or _fuente(p, "telefonos")
    return None


def ubicacion_unida(orden: list[dict]) -> tuple[dict, dict | None, list[dict]]:
    """De qué fichas salen la ubicación y la dirección de la ficha unida, como las deja `db._pipeline_fusion` al unir en
    estrella en ese orden (el destino primero): la ubicación de una ficha pasa en bloque, con su dirección, si su
    `db.llave_ubicacion` supera la de lo que el destino tiene en ese momento (su ubicación y su dirección, que pudo
    llegar de otra para llenar el vacío), y la dirección que estaba pasa a alternos; si no pasa, su dirección solo llena
    el vacío o pasa a alternos. `georreferenciar` vuelve a ubicar la ficha unida con esa dirección y da la ubicación de
    la ficha de la que salió. Devuelve (la ficha de la ubicación, la de la dirección o None, las fichas cuya dirección
    pasa a alternos, en el orden en que pasan)."""
    geo = orden[0]
    dir_de = geo if _valor(geo, "direccion") is not None else None
    alternos: list[dict] = []
    for p in orden[1:]:
        d = _valor(p, "direccion")
        actual = _valor(dir_de, "direccion") if dir_de else None
        pasa = bd.llave_ubicacion(bd._rango_ubicacion(p), d) > bd.llave_ubicacion(bd._rango_ubicacion(geo), actual)
        if pasa:
            geo = p
        if d is None:
            continue
        if actual is None or pasa:
            if actual is not None and actual != d:
                alternos.append(dir_de)
            dir_de = p
        elif d != actual:
            alternos.append(p)
    return geo, dir_de, alternos


def vista_previa(miembros: Iterable[dict], destino: int, lugares: dict | None = None) -> list[dict]:
    """Cómo quedaría la ficha unida, campo por campo, replicando de forma aproximada `db._pipeline_fusion` con la unión
    en estrella de `orden_union`: queda el valor del destino si lo tiene; si no, el primero que lo tenga en el orden de
    unión. `otros` son los valores distintos de las demás que pasarían a `alternos` (solo en los campos que dejan
    alternos: el nombre del destino se conserva y la cédula no admite otra). La ubicación (el barrio o vereda) y la
    dirección pasan juntas, en bloque, de la ficha mejor ubicada (`ubicacion_unida`): la dirección del destino puede
    pasar a alternos. Los teléfonos se juntan todos. Cada valor lleva su fuente (`procedencia`, o la primera de
    `fuentes`) y la ficha de la que viene (`de`). Los valores van como texto (los teléfonos unidos con «, ») o null."""
    lugares = lugares or {}
    orden = orden_union(miembros, destino)
    if not orden:
        return []
    geo, dir_de, dir_alternos = ubicacion_unida(orden)
    salida = []
    for campo, etiqueta in CAMPOS_VISTA:
        fila: dict = {"campo": campo, "etiqueta": etiqueta, "valor": None, "fuente": None, "de": None, "otros": []}
        if campo == "direccion":
            queda = _texto(_valor(dir_de, campo)) if dir_de else None
            if queda is not None:
                fila.update(valor=queda, fuente=_fuente(dir_de, campo), de=dir_de["_id"])
            ya = {queda}  # la que queda no se repite en alternos
            for p in dir_alternos:
                if (t := _texto(_valor(p, campo))) not in ya:
                    ya.add(t)
                    fila["otros"].append({"valor": t, "fuente": _fuente(p, campo), "de": p["_id"]})
        elif campo == "telefonos":
            todos: list[str] = []
            primero = None
            for p in orden:
                for n in _telefonos(p):
                    if n not in todos:
                        todos.append(n)
                        primero = primero or p
            if todos:  # el primer número es el principal de `primero`: la fuente es la suya
                fila.update(valor=", ".join(todos), fuente=_fuente_telefonos(primero), de=primero["_id"])
        elif campo == "lugar":
            # La ubicación pasa en bloque de la mejor ubicada (`ubicacion_unida`), como en la unión
            if _lugar(geo, lugares):
                fila.update(valor=_lugar(geo, lugares), fuente=_fuente(geo, campo), de=geo["_id"])
        else:
            vistos: set[str] = set()  # lo que ya quedó o ya pasa a alternos, comparado como la unión
            for p in orden:
                v = _valor(p, campo)
                if v is None:
                    continue
                if not vistos:
                    # La edad se muestra llevada a hoy (si no se puede calcular, la escrita)
                    hoy = _edad(p) if campo == "edad" else None
                    fila.update(valor=_texto(v if hoy is None else hoy), fuente=_fuente(p, campo), de=p["_id"])
                elif campo in CON_ALTERNOS and _texto(v) not in vistos:
                    # Pasa a alternos lo que la unión guarda: el valor tal cual (la edad, la declarada)
                    fila["otros"].append({"valor": _texto(v), "fuente": _fuente(p, campo), "de": p["_id"]})
                vistos.add(_texto(v))
        salida.append(fila)
    return salida


def miembro(p: dict, lugares: dict) -> dict:
    """Una ficha del grupo tal como la compara la interfaz (columnas lado a lado). `procedencia` lleva solo la fuente de
    cada campo (sin quién ni cuándo) y, como la interfaz la busca ahí para pintar su insignia, también la de los
    teléfonos (`_fuente_telefonos`) y la del barrio o vereda (la ubicación no anota procedencia: la de la ficha), con
    la misma regla de la vista previa. Sin ellas, esas dos filas eran las únicas sin la fuente de cada ficha."""
    prov = {k: v["fuente"] for k, v in (p.get("procedencia") or {}).items() if isinstance(v, dict) and v.get("fuente")}
    for campo, fuente in (("telefonos", _fuente_telefonos(p)), ("lugar", _lugar(p, lugares) and _fuente(p, "lugar"))):
        if fuente:  # None sin teléfonos o sin barrio: no se inventa una fuente para lo que no hay
            prov.setdefault(campo, fuente)
    return {"id": p["_id"], "nombre": p.get("nombre"), "cedula": p.get("cedula") or None, "telefonos": _telefonos(p),
            "correo": p.get("correo") or None, "direccion": p.get("direccion") or None, "lugar": _lugar(p, lugares),
            "edad": modelo.edad_efectiva(p), "sexo": p.get("sexo") or None,
            "fecha_nacimiento": p.get("fecha_nacimiento") or None, "fuentes": list(p.get("fuentes") or []),
            "procedencia": prov, "tramites": len(p.get("tramites") or []), "listas": "; ".join(p.get("listas") or []),
            "completitud": p.get("completitud") or 0, "consentimiento": p.get("consentimiento"),
            # Con él (y la dirección: a igual rango pasa la que la tiene), la vista previa que la interfaz calcula al
            # elegir otra ficha sabe de cuál pasan en bloque la ubicación y la dirección (`ubicacion_unida`), como en
            # la unión
            "rango_ubicacion": bd._rango_ubicacion(p),
            # La edad de la vista previa, como la arma `vista_previa`: la unión compara la declarada tal cual (`_valor`,
            # en el mismo texto con que la compara `vista_previa`) y se muestra la declarada llevada a hoy (`_edad`).
            # `edad` es otra: la de hoy, también por la fecha de nacimiento. Con solo ella, la vista previa estimada
            # decía que 40 años declarados en 2016 (hoy 50) y 40 de hoy dejaban un alterno que la unión no deja, y
            # callaba el de 40 de 2020 frente a 46 de hoy (hoy los dos 46), que la unión sí deja
            "edad_declarada": _texto(_valor(p, "edad")), "edad_declarada_hoy": _edad(p)}


# ───────────────────────────── Grupos ─────────────────────────────

def _pares_unicos(coincidencias: Iterable[dict], fichas: dict) -> dict[frozenset, list[dict]]:
    """Los pares con las dos fichas activas, sin repetir: (a, b) y (b, a) pueden estar pendientes a la vez (el índice
    único depende del orden y `_reapuntar_coincidencias` solo choca con el mismo orden). Pasa seguido: la importación
    crea (ficha nueva, existente) y el reporte de un duplicado, (menor, mayor). El primero de cada lista (el de menor
    id) da el id del par (en la clave del grupo) y los demás se resuelven con él, pero se evalúan todos juntos
    (`evaluar_par`): el motivo, la nota y el puntaje de cada uno cuentan."""
    pares: dict[frozenset, list[dict]] = {}
    for c in sorted(coincidencias, key=lambda c: c["_id"]):
        a, b = c["persona_id"], c["candidato_id"]
        if a == b or a not in fichas or b not in fichas:
            continue
        pares.setdefault(frozenset((a, b)), []).append(c)
    return pares


def _componentes(pares: Iterable[frozenset]) -> list[list[frozenset]]:
    u = cruce._Union()
    pares = list(pares)
    for par in pares:
        a, b = sorted(par)
        u.union(a, b)
    grupos: dict[int, list[frozenset]] = {}
    for par in pares:
        grupos.setdefault(u.find(min(par)), []).append(par)
    return list(grupos.values())


def _nombre(p: dict) -> str:
    return p.get("nombre") or f"la ficha {p['_id']}"


def _menor_conocido(valores: Iterable[float | None]) -> float | None:
    """El menor de los puntajes que hay (None si ninguno): un reporte sin puntaje no tapa el del cruce."""
    hay = [v for v in valores if v is not None]
    return min(hay) if hay else None


def evaluar_par(lista: list[dict], fichas: dict) -> tuple[dict, set[str]]:
    """Un par del grupo con sus señales y su nivel, y los motivos de todos sus repetidos. `lista`: el par y el mismo
    en orden inverso (`_pares_unicos`), que se evalúan juntos: el reporte de alguien del equipo sobre un par que la
    importación ya había propuesto no se pierde (su motivo cuenta en el grupo y en el filtro, y su nota se ve), un
    «homonimo» en cualquiera de los dos cuenta para `homonimo_sin_evidencia` y el puntaje es el menor que haya. El
    primero (el de menor id) da el id y el orden de las fichas."""
    c = lista[0]
    a, b = fichas[c["persona_id"]], fichas[c["candidato_id"]]
    # `senales` solo mira el motivo de la coincidencia: el homónimo, si alguno lo es
    favor, contra = senales(a, b, next((x for x in lista if x.get("motivo") == "homonimo"), c))
    n = nivel_par(_menor_conocido(puntaje_del_nombre(x) for x in lista), favor, contra)
    notas = list(dict.fromkeys(nota for x in lista if (nota := detalle_y_nota(x.get("detalle"))[1])))
    return ({"id": c["_id"], "a": c["persona_id"], "b": c["candidato_id"],
             "puntaje": _menor_conocido(x.get("puntaje") for x in lista), "motivo": c.get("motivo"), "nivel": n,
             "nota": " · ".join(notas) or None, "a_favor": favor, "en_contra": contra},
            {x.get("motivo") for x in lista})


def evaluar_grupo(pares: dict[frozenset, list[dict]], fichas: dict, rechazos: set[frozenset],
                  lugares: dict) -> dict:
    """Un grupo con la forma de `GET /api/coincidencias/grupos`: miembros (el destino primero), pares con sus señales
    y su nivel (`evaluar_par`), nivel del grupo y avisos que explican por qué bajó o por qué está bloqueado, y la vista
    previa. `rechazos`: los pares marcados antes como distintos (de `rechazos_entre`; basta con los de este grupo)."""
    ids = sorted({i for par in pares for i in par})
    fs = [fichas[i] for i in ids]
    destino = destino_de(fs)
    orden = orden_union(fs, destino)
    salida_pares = []
    motivos: set = set()
    nivel = "alta"
    for lista in sorted(pares.values(), key=lambda lista: lista[0]["_id"]):
        salida, de_este = evaluar_par(lista, fichas)
        salida_pares.append(salida)
        motivos |= de_este
        nivel = _peor(nivel, salida["nivel"])
    avisos = []
    cedulas = sorted({p["cedula"] for p in fs if p.get("cedula")})
    bloqueada = False
    if len(cedulas) > 1:
        bloqueada = True
        avisos.append(f"Tienen {len(cedulas)} cédulas distintas: dos cédulas distintas nunca se unen. Marque «No es la "
                      "misma» en las que sobran.")
    for x, y in sorted(tuple(sorted(r)) for r in rechazos if r <= set(ids)):
        bloqueada = True
        avisos.append(f"Ya se marcó antes que {_nombre(fichas[x])} y {_nombre(fichas[y])} son personas distintas.")
    if len(ids) > TOPE_FICHAS:
        nivel = _peor(nivel, "baja")
        avisos.append(f"Grupo grande ({len(ids)} fichas): suele ser una cadena por nombres comunes. Revíselo con "
                      "cuidado.")
    else:
        # Las que no tienen coincidencia directa también quedarían unidas: lo que las contradice baja el grupo
        for i, x in enumerate(orden):
            for y in orden[i + 1:]:
                if frozenset((x["_id"], y["_id"])) in pares:
                    continue
                contra = [s for s in senales(x, y)[1] if s["clave"] != "homonimo_sin_evidencia"]
                if contra:
                    nivel = _peor(nivel, "baja")
                    avisos.append(f"{_nombre(x)} y {_nombre(y)} no tienen una coincidencia directa y quedarían unidas: "
                                  + "; ".join(s["texto"].lower() for s in contra) + ".")
    if any(p.get("consentimiento") == "no" for p in fs) and not all(p.get("consentimiento") == "no" for p in fs):
        # Al unir gana el «no» y se borran los datos sensibles que las otras autorizaron: con un falso positivo eso
        # no se deshace. Nunca «alta», así no entra en «Unir las N muy probables» sin que nadie vea el aviso
        nivel = _peor(nivel, "media")
        avisos.append("Una de las fichas no autorizó el tratamiento de sus datos: la ficha unida quedará sin "
                      "autorización («no» gana) y sin los datos sensibles de las otras. Por eso no se une con las muy "
                      "probables: revíselo.")
    puntajes = [p["puntaje"] for p in salida_pares if p["puntaje"] is not None]
    return {"clave": "-".join(str(p["id"]) for p in sorted(salida_pares, key=lambda p: p["id"])),
            "nivel": "bloqueada" if bloqueada else nivel,
            # El puntaje del grupo es el del par más débil: un grupo vale lo que su eslabón más flojo
            "puntaje": min(puntajes) if puntajes else None, "destino": destino,
            "motivos": [m for m in MOTIVOS if m in motivos] + sorted(m for m in motivos if m not in MOTIVOS and m),
            "avisos": avisos, "miembros": [miembro(p, lugares) for p in orden], "pares": salida_pares,
            "vista_previa": vista_previa(fs, destino, lugares)}


def armar_grupos(db: Database) -> list[dict]:
    """Todos los grupos de coincidencias pendientes, ya evaluados (sin orden ni filtros).

    Primero cierra las que ya no se pueden aceptar (`cerrar_coincidencias_imposibles`), lee todas las pendientes con una
    proyección mínima, descarta los pares con una ficha inactiva, quita los repetidos en orden inverso, arma los
    componentes conexos (union-find de `cruce._Union`) y carga de una vez las fichas, los rechazos y los lugares."""
    bd.cerrar_coincidencias_imposibles(db)
    pendientes = list(db.coincidencias.find({"estado": "pendiente"}, {"persona_id": 1, "candidato_id": 1, "puntaje": 1,
                                                                      "motivo": 1, "detalle": 1}))
    fichas = cargar_fichas(db, {c["persona_id"] for c in pendientes} | {c["candidato_id"] for c in pendientes})
    pares = _pares_unicos(pendientes, fichas)
    if not pares:
        return []
    rechazos_de: dict[int, set[frozenset]] = {}  # por ficha: cada grupo mira solo los suyos
    for r in rechazos_entre(db, {i for par in pares for i in par}):
        for i in r:
            rechazos_de.setdefault(i, set()).add(r)
    lugares = nombres_de_lugares(db)
    grupos = []
    for comp in _componentes(pares):
        ids = {i for par in comp for i in par}
        propios = {r for i in ids for r in rechazos_de.get(i, ()) if r <= ids}
        grupos.append(evaluar_grupo({par: pares[par] for par in comp}, fichas, propios, lugares))
    return grupos


def _llave_orden(g: dict) -> tuple:
    return (NIVELES.index(g["nivel"]), g["puntaje"] is None, -(g["puntaje"] or 0),
            [int(x) for x in g["clave"].split("-")])


def listar_grupos(db: Database, nivel: str | None = None, motivo: str | None = None, persona: int | None = None,
                  pagina: int = 1, por_pagina: int = 25) -> dict:
    """La respuesta de `GET /api/coincidencias/grupos`. Orden: alta, media, baja, bloqueada; dentro, puntaje de mayor a
    menor (sin puntaje al final) y luego la clave. `niveles` cuenta con el filtro de motivo pero sin el de nivel (para
    los botones de nivel) y `motivos` al revés; `persona` (el enlace «revisar» de la ficha) acota todo al grupo que la
    contiene. `total`, `pares` y `personas`, con todos los filtros."""
    grupos = armar_grupos(db)
    if persona is not None:
        grupos = [g for g in grupos if any(m["id"] == persona for m in g["miembros"])]
    con_motivo = [g for g in grupos if motivo is None or motivo in g["motivos"]]
    con_nivel = [g for g in grupos if nivel is None or g["nivel"] == nivel]
    niveles = Counter(g["nivel"] for g in con_motivo)
    motivos = Counter(m for g in con_nivel for m in g["motivos"])
    elegidos = sorted((g for g in con_motivo if nivel is None or g["nivel"] == nivel), key=_llave_orden)
    desde = (pagina - 1) * por_pagina
    return {"total": len(elegidos), "pares": sum(len(g["pares"]) for g in elegidos),
            "personas": sum(len(g["miembros"]) for g in elegidos),
            "niveles": {n: niveles.get(n, 0) for n in NIVELES}, "motivos": {m: motivos.get(m, 0) for m in MOTIVOS},
            "pagina": pagina, "por_pagina": por_pagina, "grupos": elegidos[desde:desde + por_pagina]}


# ───────────────────────────── Resolución en lote ─────────────────────────────

class LoteEnCurso(HTTPException):
    """Otra importación o unión en lote tiene el turno: 409 `importando`, sin tocar nada."""

    def __init__(self):
        super().__init__(409, {"codigo": "importando", "mensaje": "Hay una importación o una unión en lote en curso. "
                                                                  "Intente de nuevo cuando termine."})


def _error(decision: str, codigo: str, error: str, **extra) -> dict:
    return {"ok": False, "decision": decision, "codigo": codigo, "error": error, **extra}


def _conexas(ids: set[int], pares: Iterable[frozenset]) -> bool:
    """¿Las fichas `ids` quedan conectadas solo con los pares entre ellas?"""
    u = cruce._Union()
    for i in ids:
        u.find(i)
    for par in pares:
        if par <= ids:
            a, b = sorted(par)
            u.union(a, b)
    return len({u.find(i) for i in ids}) == 1


def _mascara(cedula: str) -> str:
    return f"···{str(cedula)[-3:]}"


def resolver_grupo(db: Database, g: dict, quien: Any, lote: int) -> tuple[dict, int | None]:
    """Resuelve un grupo del lote y devuelve (resultado, destino si se unió alguna ficha).

    Todo o nada en la validación, antes de escribir: re-lee los pares (deben seguir pendientes: si no, `cambio`) y las
    fichas activas; para unir, entre las incluidas (las del grupo menos las de `excluir`) a lo sumo una cédula
    (`cedulas_distintas`), ningún par marcado antes como distinto (`rechazada_antes`), conectadas por los pares del
    grupo (`no_conexo`) y `conservar` entre ellas (`conservar_invalida`). Luego marca como distintas las excluidas con
    las incluidas (antes de unir: la unión reapunta sus pares al destino) y une en estrella con `bd.fusionar` en el
    orden de `orden_union`, sin volver a ubicar cada vez (quien llama ubica todos los destinos al final). Si una unión
    falla a mitad, para el grupo con `parcial` y cuántas se unieron. `separar` marca todos sus pares como distintos."""
    decision = g["decision"]
    ids = list(dict.fromkeys(g["pares"]))
    guardados = list(db.coincidencias.find({"_id": {"$in": ids}}, {"persona_id": 1, "candidato_id": 1, "estado": 1}))
    if len(guardados) != len(ids) or any(c["estado"] != "pendiente" for c in guardados):
        return _error(decision, "cambio", "El grupo cambió: recargue."), None
    miembros = {c["persona_id"] for c in guardados} | {c["candidato_id"] for c in guardados}
    fichas = cargar_fichas(db, miembros)
    if set(fichas) != miembros:
        return _error(decision, "cambio", "Una de las fichas ya se unió o se suprimió: recargue."), None
    claves = {frozenset((c["persona_id"], c["candidato_id"])) for c in guardados}
    # Los repetidos en orden inverso de esos mismos pares se resuelven con ellos
    repetidos = [c for c in db.coincidencias.find(
        {"estado": "pendiente", "_id": {"$nin": ids}, "persona_id": {"$in": list(miembros)},
         "candidato_id": {"$in": list(miembros)}}, {"persona_id": 1, "candidato_id": 1})
        if frozenset((c["persona_id"], c["candidato_id"])) in claves]
    todos = guardados + repetidos
    todos_ids = [c["_id"] for c in todos]
    marca = {"resuelto_por": bd._nombre_de(quien), "resuelto_en": bd.ahora(), "lote": lote}
    if decision == "separar":
        r = db.coincidencias.update_many({"_id": {"$in": todos_ids}, "estado": "pendiente"},
                                         {"$set": {"estado": "rechazada", **marca}})
        return {"ok": True, "decision": decision, "unidas": 0, "separadas": r.modified_count}, None

    excluir = set(g.get("excluir") or [])
    if not excluir <= miembros:
        return _error(decision, "cambio", "Una ficha marcada como distinta ya no está en el grupo: recargue."), None
    incluidas = miembros - excluir
    if not incluidas:
        return _error(decision, "no_conexo", "Marcó todas las fichas como distintas: use «Son distintas»."), None
    cedulas = {fichas[i]["cedula"] for i in incluidas if fichas[i].get("cedula")}
    if len(cedulas) > 1:
        con = sorted((i for i in incluidas if fichas[i].get("cedula")), key=lambda i: fichas[i]["cedula"])
        return _error(decision, "cedulas_distintas", "Tienen cédulas distintas: " + ", ".join(
            f"{_nombre(fichas[i])} ({_mascara(fichas[i]['cedula'])})" for i in con)
            + ". Marque «No es la misma» en las que sobran."), None
    previos = [r for r in rechazos_entre(db, incluidas) if r <= incluidas]
    if previos:
        x, y = sorted(min(previos, key=sorted))
        return _error(decision, "rechazada_antes", f"Ya se marcó antes que {_nombre(fichas[x])} y {_nombre(fichas[y])} "
                                                   "son personas distintas: márquela como «No es la misma»."), None
    if len(incluidas) > 1 and not _conexas(incluidas, claves):
        return _error(decision, "no_conexo", "Sin la ficha excluida, las demás no tienen una coincidencia directa: "
                                             "únalas por separado."), None
    conservar = g.get("conservar")
    if conservar is not None and conservar not in incluidas:
        return _error(decision, "conservar_invalida",
                      "La ficha que eligió conservar no está entre las que se unen."), None

    destino = conservar if conservar is not None else destino_de(fichas[i] for i in incluidas)
    # Las excluidas no son la misma persona que las incluidas: sus pares con ellas quedan como distintos (y una
    # importación no los vuelve a proponer). Los pares entre dos excluidas siguen pendientes: pueden ser la misma
    sueltos = [c["_id"] for c in todos if len({c["persona_id"], c["candidato_id"]} & excluir) == 1]
    separadas = 0
    if sueltos:
        separadas = db.coincidencias.update_many({"_id": {"$in": sueltos}, "estado": "pendiente"},
                                                 {"$set": {"estado": "rechazada", **marca}}).modified_count
    unidas, falla = 0, None
    otras = orden_union([fichas[i] for i in incluidas], destino)[1:]
    for o in otras:
        try:
            bd.fusionar(db, destino, o["_id"], quien, getattr(quien, "ip", None), georef=False)
        except bd.FusionImposible as e:
            falla = e.detail
            break
        unidas += 1
    # Los pares del grupo que la unión aceptó llevan la ficha conservada y el lote (los que chocaron quedan cerrados)
    db.coincidencias.update_many({"_id": {"$in": todos_ids}, "estado": "aceptada"},
                                 {"$set": {"conservada": destino, **marca}})
    if falla is not None:
        return _error(decision, "parcial", f"Se unieron {unidas} de {len(otras)} fichas y la siguiente no se pudo unir "
                                           f"({falla}). Recargue y revise las que quedan.",
                      conservada=destino, unidas=unidas, separadas=separadas), destino if unidas else None
    return {"ok": True, "decision": decision, "conservada": destino, "unidas": unidas, "separadas": separadas}, \
        destino if unidas else None


def resolver_lote(db: Database, grupos: list[dict], quien: Any) -> dict:
    """`POST /api/coincidencias/lote`: resuelve los grupos en orden con el turno global de la importación (unir en lote
    e importar se excluyen: la importación carga las fichas en memoria y no vería las uniones), ubica una sola vez todos
    los destinos al final (en vez de una vez por unión) y deja una sola entrada de auditoría con los conteos, sin ids ni
    nombres: cada unión ya queda auditada una por una en `bd.fusionar`, con su persona."""
    from .pipeline import importar as imp  # aquí: el pipeline usa db, que no debe cargar este módulo
    dueño = uuid.uuid4().hex
    if not bd.tomar_turno(db, TURNO, dueño, imp.TURNO_MIN):
        raise LoteEnCurso()
    resultados: list[dict] = []
    destinos: list[int] = []
    try:
        lote = bd.siguiente_id(db, "lotes")
        for g in grupos:
            resultado, destino = resolver_grupo(db, g, quien, lote)
            resultados.append(resultado)
            if destino is not None:
                destinos.append(destino)
            bd.renovar_turno(db, TURNO, dueño, imp.TURNO_MIN)
    finally:
        try:
            if destinos:
                imp.georreferenciar(db, destinos)
                bd.recalcular_completitud(db, destinos)  # la ubicación cuenta en la completitud
        finally:
            bd.soltar_turno(db, TURNO, dueño)
    unidas = sum(r.get("unidas", 0) for r in resultados)
    separadas = sum(r.get("separadas", 0) for r in resultados)
    errores = sum(not r["ok"] for r in resultados)
    bd.auditar(db, quien, "resolver_lote", None, None, {"grupos": len(grupos), "unidas": unidas,
                                                        "separadas": separadas, "errores": errores},
               getattr(quien, "ip", None))
    return {"resultados": resultados, "unidas": unidas, "separadas": separadas, "errores": errores}
