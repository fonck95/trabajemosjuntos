"""Lo que se proyecta ante una sala: las reglas de todo texto que el modelo escribe para la pantalla de la presentación
(la explicación, la narración y el cierre de un recorrido). Las usan la herramienta `presentacion`
(`agente/herramientas/interfaz.py`), el recorrido (`app/recorrido.py`) y la pantalla en off (`app/pantalla.py`); las
mismas reglas están en `explicacionVisible` de web/js/agente-presentacion.js y en `textoVisible` de
web/js/propuesta/mando.js, y una prueba compara los tres lados con las mismas frases.

Solo usa la biblioteca estándar y no importa nada del panel: así nadie se importa en círculo."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

# Una o dos frases cortas: lo que el subtítulo de la presentación muestra entero en cualquier pantalla, del celular al
# proyector (web/propuesta.html no lo recorta). `MAX_EXPLICACION` de agente-presentacion.js y de mando.js: una prueba
# los compara. Es el tope por omisión: el título y los puntos del cierre de un recorrido tienen el suyo
MAX_EXPLICACION = 220
# Lo que delata plata en un texto (`PLATA` de agente/guion.py y de web/js/propuesta/tecnica.js)
PLATA = re.compile(r"\$|millones de pesos")
# Lo que la explicación no puede traer: la ve una sala entera en un proyector. Caracteres que no se ven o que cambian
# cómo se ve el resto (de control, de formato como las marcas de dirección o el espacio de ancho cero, separadores de
# línea, sustitutos sueltos, de uso privado, sin asignar, los rellenos que se ven como nada y los selectores de
# variante), más de dos acentos apilados, una «@» (un correo, un usuario) o un número de 7 o más dígitos (una cédula, un
# teléfono, un código), también escrito por grupos. Las dos últimas se buscan en la forma NFKC del texto: así la «@» de
# ancho completo (＠) o la pequeña (﹫), los dígitos de ancho completo o en superíndice y los guiones de compatibilidad
# cuentan como los comunes. Las mismas reglas, en `explicacionVisible` de agente-presentacion.js y en `textoVisible` de
# mando.js
_NO_SE_VEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_RELLENOS = frozenset("\U0000034f\U0000115f\U00001160\U000017b4\U000017b5\U00002800\U00003164\U0000ffa0")
_SELECTORES = re.compile("[\U0000180b-\U0000180f\U0000fe00-\U0000fe0f\U000e0000-\U000e0fff]")
# Una tirada de dígitos con lo que los separa al escribir un teléfono o una cédula: un espacio, un guion, una raya, el
# signo menos o una barra (con un espacio a cada lado o sin él), un paréntesis que cierra («(604) 832 12 34»), y pegados
# entre dos dígitos el punto, la coma, el «_», el punto medio o el paréntesis que abre («71.234.567», «1,023,456,789»).
# Un paréntesis que abre después de un espacio no une («en 2018 (3.383)»), ni el punto o la coma seguidos de un espacio
# («en 2031. 300 familias», «2028, 2029 y 2030»)
_GUIONES = "\\-\u2010-\u2015\u2212"
_TIRADA = re.compile(rf"\d+(?:(?:[.,_\u00b7(]|\) ?|\)? ?[{_GUIONES}/] ?\(?| )\d+)*")
DIGITOS_MAX = 6
# Lo que sí puede tener 7 dígitos o más: un periodo («2028–2031», «2028-2031», «2028/2031») y un rango de dos cifras
# como las de la propuesta («$116.294 – 210.000 M», «1.346–1.500 kWh»), de menor a mayor. Solo con dígitos ASCII
_PERIODO = re.compile(rf"((?:19|20)[0-9]{{2}}) ?[{_GUIONES}/] ?((?:19|20)[0-9]{{2}})")
_CIFRA = r"[0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?"
_RANGO = re.compile(rf"({_CIFRA}) ?[{_GUIONES}] ?({_CIFRA})")
# Y una fecha (`minimizar._FECHAS`, que tampoco las enmascara): día/mes/año o año/mes/día, con barra, guion, raya o
# punto (el mismo a los dos lados, con un espacio o sin él: «15/11/2026», «2026-11-15», «15 / 11 / 2026»), de 1900 a
# 2099 y que exista en el calendario. Suma 8 dígitos y la tirada la tomaría por una cédula; el modelo las escribe con
# naturalidad (plazos, radicaciones, reuniones). Se apartan antes de buscar las tiradas, como hace minimizar: así lo que
# va pegado a una fecha se mira solo («el 15/11/2026 300 123 4567» sigue frenado). Solo con dígitos ASCII
_FECHA = re.compile(rf"(?<!\d)(?:([0-9]{{4}}) ?([.{_GUIONES}/]) ?([0-9]{{1,2}}) ?\2 ?([0-9]{{1,2}})"
                    rf"|([0-9]{{1,2}}) ?([.{_GUIONES}/]) ?([0-9]{{1,2}}) ?\6 ?([0-9]{{4}}))(?!\d)")
# Y un monto en pesos con su signo y sus puntos de miles («$1.156.350», el costo por habitante que trae el guion): la
# tirada va justo después de «$», en grupos de tres y con 7 cifras enteras a lo sumo, las del monto más largo del
# guion. Sin ese tope pasaban una cédula o un teléfono escritos con «$» y puntos («$1.023.456.789», «$71.234.567»)
_MONTO = re.compile(r"(?:[0-9]{1,3}|[0-9]\.[0-9]{3})\.[0-9]{3}(?:,[0-9]{1,2})?")


def _cifra(t: str) -> float:
    """«116.294» → 116294; «1,62» → 1.62 (el punto de miles y la coma decimal de la presentación)."""
    return float(t.replace(".", "").replace(",", "."))


def _es_fecha(m: re.Match) -> bool:
    """¿Es `m` (de `_FECHA`) un día que existe, de 1900 a 2099? («31/02/2026» no: se mira como cualquier número)."""
    a, mes, dia = (m.group(1), m.group(3), m.group(4)) if m.group(1) else (m.group(8), m.group(7), m.group(5))
    try:
        return 1900 <= date(int(a), int(mes), int(dia)).year <= 2099
    except ValueError:
        return False


def numero_largo(t: str) -> str | None:
    """La primera tirada de más de DIGITOS_MAX dígitos de `t` (ya en NFKC y con los espacios en uno) que no es un
    periodo, un rango de cifras, una fecha ni un monto en pesos, o None. Las fechas válidas se quitan antes (cada una
    corta la tirada)."""
    t = _FECHA.sub(lambda m: " | " if _es_fecha(m) else m.group(0), t)
    for m in _TIRADA.finditer(t):
        tirada = m.group(0)
        if len(re.findall(r"\d", tirada)) <= DIGITOS_MAX:
            continue
        if re.search(r"\$ ?$", t[:m.start()]) and _MONTO.fullmatch(tirada):
            continue
        p = _PERIODO.fullmatch(tirada)
        if p and int(p.group(1)) <= int(p.group(2)):
            continue
        r = _RANGO.fullmatch(tirada)
        if r and _cifra(r.group(1)) <= _cifra(r.group(2)):
            continue
        return tirada
    return None


def texto_proyectable(v: str, maximo: int = MAX_EXPLICACION, plata: bool = True) -> str:
    """Un texto para la pantalla: un solo renglón que se ve tal cual es (los espacios seguidos quedan en uno, como los
    pinta el navegador), de hasta `maximo` caracteres, sin datos que identifiquen a nadie y, con `plata` en False (los
    textos del recorrido de la presentación técnica, que no muestra costos), sin «$» ni «millones de pesos». Se devuelve
    como lo escribió el modelo (sin NFKC: «m²» no pasa a «m2»); la forma NFKC solo sirve para buscar la «@» y los
    números."""
    if not isinstance(v, str):
        raise ValueError("El texto para la pantalla tiene que ser texto")
    marcas = 0
    for c in v:
        cat = unicodedata.category(c)
        if (cat in _NO_SE_VEN and c not in "\t\n\r") or c in _RELLENOS or _SELECTORES.match(c):
            raise ValueError("La explicación trae caracteres invisibles o de control: escríbala sin ellos")
        marcas = marcas + 1 if cat in ("Mn", "Me") else 0
        if marcas > 2:
            raise ValueError("La explicación trae demasiados acentos seguidos sobre una letra")
    v = " ".join(v.split())
    if not v:
        raise ValueError("La explicación está vacía")
    if len(v) > maximo:
        raise ValueError(f"El texto para la pantalla pasa de {maximo} caracteres: acórtelo (una idea, en lenguaje hablado)")
    k = " ".join(unicodedata.normalize("NFKC", v).split())
    if "@" in k:
        raise ValueError("La explicación se proyecta ante la sala: no puede llevar «@» (un correo o un usuario). "
                         "Escríbala sin ella y, si hace falta, dé el dato en el chat")
    if numero_largo(k):
        raise ValueError("La explicación se proyecta ante la sala: no puede llevar números de 7 o más dígitos "
                         "(cédulas, teléfonos o códigos como el BPIN), tampoco con espacios, puntos, guiones o barras. "
                         "Escriba los montos como los trae el guion («$106.271 M», «$1,2 – 1,4 billones»), un periodo "
                         "como «2028–2031» y una fecha como «15/11/2026» o «2026-11-15» (día, mes y año que existan), "
                         "separe dos números seguidos con una palabra o una coma («en 2028, 300 viviendas») y deje los "
                         "códigos para el chat")
    if not plata and PLATA.search(k):
        raise ValueError("La presentación técnica no muestra costos: escriba el texto sin montos («$», «millones de "
                         "pesos»); la plata, si hace falta, en el chat")
    return v
