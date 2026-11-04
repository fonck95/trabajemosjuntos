"""Normalización de texto, nombres, teléfonos y correos.

Todo lo que se compara entre bases pasa por aquí: mayúsculas, sin tildes, sin signos y con los espacios
colapsados. La Ñ se conserva para mostrar, pero se pliega a N para comparar.
"""
from __future__ import annotations

import re
import unicodedata

_ESPACIOS = re.compile(r"\s+")
_NO_LETRA = re.compile(r"[^A-Z ]+")

# Partículas que no identifican a nadie: no suman ni restan al comparar nombres
PARTICULAS = frozenset({"DE", "DEL", "LA", "LAS", "LOS", "Y", "E", "VDA", "VIUDA"})


def sin_tildes(s: str) -> str:
    """Quita tildes y diéresis (también la de la Ñ) y deja ASCII."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def limpiar(s: object) -> str:
    """Texto en mayúsculas, sin tildes y con un solo espacio entre palabras. None → ''."""
    if s is None:
        return ""
    return _ESPACIOS.sub(" ", sin_tildes(str(s)).upper()).strip()


def nombre_visible(s: object) -> str:
    """Nombre para mostrar: mayúsculas, conserva tildes y Ñ, espacios colapsados."""
    if s is None:
        return ""
    return _ESPACIOS.sub(" ", str(s).upper()).strip()


def nombre_norm(s: object) -> str:
    """Nombre para comparar: solo letras A-Z y espacios."""
    return _ESPACIOS.sub(" ", _NO_LETRA.sub(" ", limpiar(s))).strip()


_DEL_PEGADO = re.compile(r"\bDEL(CARMEN|ROSARIO|SOCORRO|PILAR|CRISTO|VALLE|MAR|TRANSITO|PERPETUO|ROCIO|CARMEM)\b")


def tokens_nombre(s: object, iniciales: bool = False) -> list[str]:
    """Palabras del nombre que sí identifican (sin partículas ni, salvo que se pidan, iniciales sueltas).
    «DELCARMEN» → «CARMEN»."""
    n = _DEL_PEGADO.sub(r"DEL \1", nombre_norm(s))
    return [t for t in n.split() if t not in PARTICULAS and (iniciales or len(t) > 1)]


_FONETICA = [
    (re.compile(r"^Y(?=[AEIOU])"), "J"), (re.compile(r"PH"), "F"), (re.compile(r"TH"), "T"), (re.compile(r"JH"), "J"),
    (re.compile(r"SH"), "S"), (re.compile(r"KH"), "K"), (re.compile(r"QU(?=[EI])"), "K"), (re.compile(r"GU(?=[EI])"), "G"),
    (re.compile(r"C(?=[EI])"), "S"), (re.compile(r"G(?=[EI])"), "J"), (re.compile(r"C"), "K"), (re.compile(r"Q"), "K"),
    (re.compile(r"Z"), "S"), (re.compile(r"V"), "B"), (re.compile(r"W"), "U"), (re.compile(r"Y"), "I"),
    (re.compile(r"LL"), "I"), (re.compile(r"H"), ""), (re.compile(r"(.)\1+"), r"\1"),
]


def fonetico(t: str) -> str:
    """Clave fonética sencilla del español de Colombia: JHON/JOHN, NUVIA/NUBIA, YANETH/JANETH, DEISY/DEISI."""
    for patron, cambio in _FONETICA:
        t = patron.sub(cambio, t)
    return t


_PREFIJO_TRAMITE = re.compile(r"^\s*([A-ZÁÉÍÓÚÑ ]+?)\s+-\s+(.+)$")


def separar_tramite(s: object) -> tuple[str, str]:
    """'NUEVA ENCUESTA - ODILIA SARMIENTO' → ('NUEVA ENCUESTA', 'ODILIA SARMIENTO')."""
    txt = "" if s is None else str(s)
    m = _PREFIJO_TRAMITE.match(txt)
    if not m:
        return "", nombre_visible(txt)
    return limpiar(m.group(1)), nombre_visible(m.group(2))


# Un número dentro de un trozo con varios: celular, fijo 60X de 10 dígitos o fijo de 7, con o sin +57
_TEL = re.compile(r"(?<!\d)(?:\+?57[\s.-]?)?((?:3\d{2}|60\d)[\s.-]?\d{3}[\s.-]?\d{4}|\d{7})(?!\d)")
# «3001234567.0»: número leído de una celda numérica guardada como texto
_DECIMAL_CERO = re.compile(r"(?<![\d.,])(\d{7,12})[.,]0{1,2}(?![\d.,])")


def telefonos(s: object) -> list[str]:
    """Teléfonos colombianos válidos en el texto (celular de 10 dígitos que empieza por 3, o fijo de 7 o 10).

    Quita el indicativo +57 y descarta números de relleno (0000000, 1111111111…).
    """
    if s is None:
        return []
    txt = str(s)
    if isinstance(s, float) and s.is_integer():
        txt = str(int(s))
    salida: list[str] = []

    def agregar(d: str) -> None:
        if len(set(d)) > 2 and d not in salida:
            salida.append(d)

    for bruto in re.split(r"[;,/|]|\s-\s|\s{2,}|\b[yo]\b", txt, flags=re.I):
        bruto = _DECIMAL_CERO.sub(r"\1", bruto)
        d = re.sub(r"\D", "", bruto)
        if d.startswith("57") and len(d) == 12:
            d = d[2:]
        if len(d) == 10 and d[0] in "36" or len(d) == 7:
            agregar(d)
        elif len(d) == 20:  # dos números pegados
            for parte in (d[:10], d[10:]):
                if parte[0] == "3" or parte.startswith("60"):
                    agregar(parte)
        else:  # varios números en el mismo trozo: «8612345 3001234567»
            for m in _TEL.finditer(bruto):
                agregar(re.sub(r"\D", "", m.group(1)))
    return salida


_CORREO = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
_ARREGLOS_DOMINIO = {
    "gmail.comk": "gmail.com", "gmail.co": "gmail.com", "gmial.com": "gmail.com", "gmai.com": "gmail.com",
    "gmail.con": "gmail.com", "gamil.com": "gmail.com", "hotmail.con": "hotmail.com", "hotmal.com": "hotmail.com",
    "hotmail.co": "hotmail.com", "hotmai.com": "hotmail.com", "outlook.con": "outlook.com", "yahoo.con": "yahoo.com",
}
_CORREOS_RELLENO = ("notiene", "no@", "sincorreo", "ninguno", "na@", "noaplica", "xxx")


def correo(s: object) -> str:
    """Correo en minúsculas, con los errores de dominio más comunes corregidos. '' si no es válido."""
    if s is None:
        return ""
    c = str(s).strip().lower().replace(" ", "")
    if "@" not in c:
        return ""
    usuario, _, dominio = c.rpartition("@")
    dominio = _ARREGLOS_DOMINIO.get(dominio, dominio)
    c = f"{usuario}@{dominio}"
    if not _CORREO.match(c) or any(r in c for r in _CORREOS_RELLENO):
        return ""
    return c


def cedula(s: object) -> str:
    """Cédula como solo dígitos (5 a 11). '' si no parece una cédula."""
    if s is None:
        return ""
    if isinstance(s, float) and s.is_integer():
        s = int(s)
    if isinstance(s, str):
        # «12345678.0» (celda numérica guardada como texto): el decimal no es parte de la cédula. Con separadores de
        # miles («71.234.000») no se toca
        m = re.fullmatch(r"\s*(\d+)[.,]0{1,2}\s*", s)
        s = m.group(1) if m else s
    d = re.sub(r"\D", "", str(s))
    return d if 5 <= len(d) <= 11 and len(set(d)) > 1 else ""


def titulo(s: str) -> str:
    """'BRISAS DEL ORIENTE' → 'Brisas del Oriente' (para la interfaz)."""
    menores = {"de", "del", "la", "las", "los", "y", "el", "en"}
    palabras = s.lower().split()
    return " ".join(p if (i and p in menores) else p.capitalize() for i, p in enumerate(palabras))
