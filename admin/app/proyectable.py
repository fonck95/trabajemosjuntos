"""Lo que se proyecta ante una sala: las reglas de todo texto que el modelo escribe para la pantalla de la presentación
técnica (la explicación, la narración y el cierre de un recorrido), que no muestra costos. Las usan la herramienta `presentacion`
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
# Lo que delata un costo en un texto proyectado: el signo (también 💲; el «＄» de ancho completo y el «﹩» pequeño quedan
# como «$» en la forma NFKC), «COP», «pesos», «billones de», «billón de» o «millones de pesos», en mayúsculas o
# minúsculas. La misma
# regla, en `PLATA` de mando.js y de agente-presentacion.js. (La de agente/guion.py y tecnica.js, que limpia los datos
# de la propuesta antes de mostrarlos, es otra cosa y no cambia con esta.) Con `\b` de ASCII, como el de JavaScript: si
# no, junto a una letra con tilde («copó») los tres lados decidirían distinto. Sigue siendo una alerta, no una prueba:
# «cuesta 106.271 millones» pasa; por eso el modelo tampoco recibe costos en el guion
PLATA = re.compile(r"[$\U0001F4B2]|\bcop\b|\bpesos\b|\bbill(?:ones|[o\u00f3\u00d3]n) de\b|millones de pesos", re.I | re.A)
# Lo que la explicación no puede traer: la ve una sala entera en un proyector. Caracteres que no se ven o que cambian
# cómo se ve el resto (de control, de formato como las marcas de dirección o el espacio de ancho cero, separadores de
# línea, sustitutos sueltos, de uso privado, sin asignar, los rellenos que se ven como nada y los selectores de
# variante), más de dos acentos apilados, una «@» (un correo, un usuario), un número de 7 o más dígitos (una cédula, un
# teléfono, un código), también escrito por grupos, o un costo (PLATA). Las tres últimas se buscan en la forma NFKC del
# texto: así la «@» de ancho completo (＠) o la pequeña (﹫), los dígitos de ancho completo o en superíndice y los
# guiones de compatibilidad cuentan como los comunes. Las mismas reglas, en `explicacionVisible` de
# agente-presentacion.js y en `textoVisible` de mando.js
_NO_SE_VEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_RELLENOS = frozenset("\U0000034f\U0000115f\U00001160\U000017b4\U000017b5\U00002800\U00003164\U0000ffa0")
_SELECTORES = re.compile("[\U0000180b-\U0000180f\U0000fe00-\U0000fe0f\U000e0000-\U000e0fff]")
# Una tirada de dígitos con lo que los separa al escribir un teléfono o una cédula: un espacio, un guion, una raya, el
# signo menos o una barra (con un espacio a cada lado o sin él), un paréntesis que cierra («(604) 832 12 34»), y pegados
# entre dos dígitos el punto, la coma, el «_», el punto medio, el paréntesis que abre, el apóstrofo recto o tipográfico
# (de apertura o de cierre), el acento agudo, el grave y los modificadores que se usan como apóstrofo, la prima y los
# puntos de viñeta (' ‘ ’ ´ ` ʹ ʼ ′ ‧ • ∙ ・; el «´» queda en la forma NFKC como un espacio y un acento combinante, que
# también une): «71.234.567», «1,023,456,789» y «71'234.567» o «71´234.567», con el apóstrofo de los millones, que es
# como se escribe a mano una cédula en Colombia. Un paréntesis que abre después de un espacio no une
# («en 2018 (3.383)»), ni el punto o la coma seguidos de un espacio («en 2031. 300 familias», «2028, 2029 y 2030»); los
# dos puntos tampoco (una escala, «1:100.000»)
_GUIONES = "\\-\u2010-\u2015\u2212"
_TIRADA = re.compile(rf"\d+(?:(?:[.,_\u00b7'\u2018\u2019\u2032\u2027\u2022\u2219\u30fb\u0060\u02b9\u02bc(]| \u0301|\) ?|\)? ?[{_GUIONES}/] ?\(?| )\d+)*")
DIGITOS_MAX = 6
# Lo que sí puede tener 7 dígitos o más: un periodo («2028–2031», «2028-2031», «2028/2031») y un rango de dos cifras
# como las de la propuesta («116.294 – 210.000», «1.346–1.500 kWh»), de menor a mayor. Solo con dígitos ASCII
_PERIODO = re.compile(rf"((?:19|20)[0-9]{{2}}) ?[{_GUIONES}/] ?((?:19|20)[0-9]{{2}})")
_CIFRA = r"[0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?"
_RANGO = re.compile(rf"({_CIFRA}) ?[{_GUIONES}] ?({_CIFRA})")
# Y una fecha (`minimizar._FECHAS`, que tampoco las enmascara): día/mes/año o año/mes/día, con barra, guion, raya o
# punto (el mismo a los dos lados, con un espacio o sin él: «15/11/2026», «2026-11-15», «15 / 11 / 2026»), de 1900 a
# 2099 y que exista en el calendario. Suma 8 dígitos y la tirada la tomaría por una cédula; el modelo las escribe con
# naturalidad (plazos, radicaciones, reuniones). Se apartan antes de buscar las tiradas, como hace minimizar: así lo que
# va pegado a una fecha se mira solo («el 15/11/2026 300 123 4567» sigue frenado). Solo con dígitos ASCII. (Un monto en
# pesos, «$1.156.350», ya no es excepción: lo proyectado no lleva costos y PLATA lo frena antes)
_FECHA = re.compile(rf"(?<!\d)(?:([0-9]{{4}}) ?([.{_GUIONES}/]) ?([0-9]{{1,2}}) ?\2 ?([0-9]{{1,2}})"
                    rf"|([0-9]{{1,2}}) ?([.{_GUIONES}/]) ?([0-9]{{1,2}}) ?\6 ?([0-9]{{4}}))(?!\d)")


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
    periodo, un rango de cifras ni una fecha, o None. Las fechas válidas se quitan antes (cada una corta la tirada)."""
    t = _FECHA.sub(lambda m: " | " if _es_fecha(m) else m.group(0), t)
    for m in _TIRADA.finditer(t):
        tirada = m.group(0)
        if len(re.findall(r"\d", tirada)) <= DIGITOS_MAX:
            continue
        p = _PERIODO.fullmatch(tirada)
        if p and int(p.group(1)) <= int(p.group(2)):
            continue
        r = _RANGO.fullmatch(tirada)
        if r and _cifra(r.group(1)) <= _cifra(r.group(2)):
            continue
        return tirada
    return None


def texto_proyectable(v: str, maximo: int = MAX_EXPLICACION) -> str:
    """Un texto para la pantalla: un solo renglón que se ve tal cual es (los espacios seguidos quedan en uno, como los
    pinta el navegador), de hasta `maximo` caracteres, sin datos que identifiquen a nadie y sin costos (PLATA). Es la
    regla de todo lo que se proyecta en la presentación técnica, la explicación y el recorrido por igual: sin una opción
    que deje pasar la plata, así ningún texto la proyecta por olvido. Se devuelve como lo escribió el modelo (sin NFKC:
    «m²» no pasa a «m2»); la forma NFKC solo sirve para buscar la «@», los números y la plata."""
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
    # La plata antes que los números: un monto («$1.156.350») se frena por lo que es, con el mensaje que lo dice
    if PLATA.search(k):
        raise ValueError("La presentación técnica no muestra costos: escriba el texto sin montos («$», «COP», «pesos», "
                         "«millones de pesos»); la plata, si hace falta, en el chat")
    if numero_largo(k):
        raise ValueError("La explicación se proyecta ante la sala: no puede llevar números de 7 o más dígitos "
                         "(cédulas, teléfonos o códigos como el BPIN), tampoco con espacios, puntos, guiones, barras o "
                         "apóstrofos. Escriba un periodo como «2028–2031» y una fecha como «15/11/2026» o «2026-11-15» "
                         "(día, mes y año que existan), separe dos números seguidos con una palabra o una coma («en "
                         "2028, 300 viviendas») y deje los códigos para el chat")
    return v
