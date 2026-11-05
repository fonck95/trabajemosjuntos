"""Geometría de las zonas dibujadas en el mapa: validación del anillo, área, perímetro y codificación en la URL.

* Un anillo es una lista de vértices [lon, lat], abierto (sin repetir el primero al final).
* El área es la esférica de Turf y d3 (radio 6 378 137 m) y el perímetro, haversine (radio 6 371 008,8 m): las mismas
  fórmulas que web/js/zona.js, así el navegador y el servidor miden igual.
* `validar_anillo` responde 422 `{codigo: "poligono"}` con el motivo; lo usan el filtro `poligono` y las áreas.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from fastapi import HTTPException

from .modelo import RANGO_YONDO

R_AREA = 6378137.0
R_PERIMETRO = 6371008.8
MIN_VERTICES, MAX_VERTICES = 3, 150
AREA_MIN_M2, AREA_MAX_M2 = 100.0, 4000e6
LARGO_MAXIMO = 4000  # del texto «lon,lat;…» en la URL
DECIMALES = 6


class PoligonoInvalido(HTTPException):
    def __init__(self, mensaje: str):
        super().__init__(422, {"mensaje": mensaje, "codigo": "poligono"})


def _abierto(anillo: Iterable[Any]) -> list:
    a = list(anillo)
    while len(a) > 1 and list(a[0]) == list(a[-1]):
        a.pop()
    return a


def area_m2(anillo: Iterable[Any]) -> float:
    """Área en m² (esférica, como Turf y d3)."""
    a = _abierto(anillo)
    k = math.pi / 180
    s = 0.0
    for i, (l1, f1) in enumerate(a):
        l2, f2 = a[(i + 1) % len(a)]
        s += (l2 - l1) * k * (2 + math.sin(f1 * k) + math.sin(f2 * k))
    return abs(s * R_AREA * R_AREA / 2)


def _haversine(a: Any, b: Any) -> float:
    k = math.pi / 180
    (l1, f1), (l2, f2) = a, b
    h = math.sin((f2 - f1) * k / 2) ** 2 + math.cos(f1 * k) * math.cos(f2 * k) * math.sin((l2 - l1) * k / 2) ** 2
    return 2 * R_PERIMETRO * math.asin(min(1.0, math.sqrt(h)))


def perimetro_m(anillo: Iterable[Any]) -> float:
    """Perímetro en metros (haversine), incluido el lado que cierra el anillo."""
    a = _abierto(anillo)
    if len(a) < 2:
        return 0.0
    return sum(_haversine(a[i], a[(i + 1) % len(a)]) for i in range(len(a)))


def _orientacion(a: tuple, b: tuple, c: tuple) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _sobre(a: tuple, b: tuple, c: tuple) -> bool:
    """c (alineado con a y b) cae dentro del segmento ab."""
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def _se_tocan(p1: tuple, p2: tuple, p3: tuple, p4: tuple) -> bool:
    o1, o2, o3, o4 = _orientacion(p1, p2, p3), _orientacion(p1, p2, p4), _orientacion(p3, p4, p1), _orientacion(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and _sobre(p1, p2, p3)) or (o2 == 0 and _sobre(p1, p2, p4)) or \
        (o3 == 0 and _sobre(p3, p4, p1)) or (o4 == 0 and _sobre(p3, p4, p2))


def se_cruza(anillo: Iterable[Any]) -> bool:
    """¿Algún par de lados se cruza o se toca (fuera del vértice que comparten dos lados seguidos)? Plano, sobre
    lon/lat en millonésimas de grado (enteros: sin errores de redondeo)."""
    a = [(round(lon * 1e6), round(lat * 1e6)) for lon, lat in _abierto(anillo)]
    n = len(a)
    if n < 3:
        return False
    lados = [(a[i], a[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        p1, p2 = lados[i]
        for j in range(i + 1, n):
            p3, p4 = lados[j]
            if j == i + 1 or (i == 0 and j == n - 1):
                # Seguidos: comparten un vértice. Se cruzan solo si vuelven sobre sí mismos (alineados y superpuestos)
                comun, x, y = (p2, p1, p4) if j == i + 1 else (p1, p2, p3)
                if _orientacion(x, comun, y) == 0 and (_sobre(comun, x, y) or _sobre(comun, y, x)):
                    return True
                continue
            if _se_tocan(p1, p2, p3, p4):
                return True
    return False


def _numero(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise PoligonoInvalido("Hay un vértice que no es un número")
    return float(v)


def validar_anillo(anillo: Any) -> list[list[float]]:
    """El anillo limpio (6 decimales, sin vértices repetidos seguidos ni el de cierre) o 422 `{codigo: "poligono"}`:
    de 3 a 150 vértices, todos dentro de Yondó, sin lados cruzados y con un área entre 100 m² y 4 000 km²."""
    if not isinstance(anillo, (list, tuple)) or len(anillo) > 4 * MAX_VERTICES:
        raise PoligonoInvalido(f"El polígono necesita de {MIN_VERTICES} a {MAX_VERTICES} vértices")
    limpio: list[list[float]] = []
    for v in anillo:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise PoligonoInvalido("Cada vértice es un par [lon, lat]")
        x = [round(_numero(v[0]), DECIMALES), round(_numero(v[1]), DECIMALES)]
        if not limpio or limpio[-1] != x:
            limpio.append(x)
    limpio = _abierto(limpio)
    if not MIN_VERTICES <= len(limpio) <= MAX_VERTICES:
        raise PoligonoInvalido(f"El polígono necesita de {MIN_VERTICES} a {MAX_VERTICES} vértices")
    (lon_min, lat_min), (lon_max, lat_max) = RANGO_YONDO
    if any(not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max) for lon, lat in limpio):
        raise PoligonoInvalido("Hay vértices fuera de Yondó")
    if se_cruza(limpio):
        raise PoligonoInvalido("Los lados se cruzan")
    if not AREA_MIN_M2 <= area_m2(limpio) <= AREA_MAX_M2:
        raise PoligonoInvalido("El área debe estar entre 100 m² y 4 000 km²")
    return limpio


def anillo_de(valor: Any) -> list[list[float]]:
    """El anillo validado de lo que manda el cliente: una lista de vértices [lon, lat], un texto «lon,lat;…» o un
    GeoJSON Polygon (su anillo exterior). 422 `{codigo: "poligono"}` con cualquier otra cosa."""
    if isinstance(valor, str):
        valor = decodificar(valor)
    elif isinstance(valor, dict) and valor.get("type") == "Polygon" and isinstance(valor.get("coordinates"), list) \
            and valor["coordinates"]:
        valor = valor["coordinates"][0]
    return validar_anillo(valor)


def medidas(anillo: Iterable[Any]) -> dict:
    """Área (m², redondeada al metro) y perímetro (m, al decímetro) de un anillo ya validado."""
    a = list(anillo)
    return {"area_m2": round(area_m2(a)), "perimetro_m": round(perimetro_m(a), 1)}


def a_geojson(anillo: Iterable[Any]) -> dict:
    """GeoJSON Polygon (anillo cerrado) para `$geoWithin` con `$geometry`."""
    a = [list(v) for v in _abierto(anillo)]
    return {"type": "Polygon", "coordinates": [a + [list(a[0])]]} if a else {"type": "Polygon", "coordinates": [[]]}


def _texto(x: float) -> str:
    s = f"{x:.{DECIMALES}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def codificar(anillo: Iterable[Any]) -> str:
    """«lon,lat;lon,lat;…» con 6 decimales como máximo (el parámetro `poligono` de la URL)."""
    return ";".join(f"{_texto(lon)},{_texto(lat)}" for lon, lat in _abierto(anillo))


def decodificar(texto: Any) -> list[list[float]]:
    """El anillo de un texto «lon,lat;…» (sin validarlo: eso es `validar_anillo`). 422 si no se puede leer."""
    if not isinstance(texto, str) or len(texto) > LARGO_MAXIMO:
        raise PoligonoInvalido("El polígono no se puede leer")
    anillo = []
    for par in texto.split(";"):
        if not par.strip():
            continue
        partes = par.split(",")
        if len(partes) != 2:
            raise PoligonoInvalido("El polígono no se puede leer")
        try:
            lon, lat = float(partes[0]), float(partes[1])
        except ValueError:
            raise PoligonoInvalido("El polígono no se puede leer") from None
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise PoligonoInvalido("El polígono no se puede leer")
        anillo.append([lon, lat])
    return anillo
