"""Georreferenciación de direcciones de Yondó, de la más precisa a la menos precisa.

1. **Dirección con placa en el casco urbano** («CL 49 # 45-12»): la grilla de nomenclatura (`geo/grilla_casco.json`,
   cruces de calles y carreras de OpenStreetMap) se ajusta localmente con un plano ponderado y da la coordenada
   del predio, también en calles que OSM no tiene con nombre. Precisión «direccion» (o «direccion_aprox» si la
   placa cae un poco fuera de la grilla conocida).
2. **Barrio, vereda, caserío o centro poblado** reconocido en el nomenclátor: su punto. Precisión = tipo de lugar.
3. Nada reconocible: sin coordenada. La persona cuenta en los indicadores pero no se dibuja en el mapa.

Nunca se inventa precisión: cada coordenada guarda de dónde salió, y el mapa dispersa visualmente los puntos de
barrio o vereda sin tocar el dato guardado.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .direcciones import CASCO, Direccion, Lugar, Nomenclator, leer, zona_por_texto

RAIZ_GEO = Path(__file__).resolve().parents[2] / "geo"


@dataclass
class Ubicacion:
    lat: float | None
    lon: float | None
    precision: str | None   # direccion | direccion_aprox | barrio | sector | caserio | centro_poblado | vereda | corregimiento
    zona: str | None        # urbana | rural
    lugar: Lugar | None
    confianza: float


def _valor(num: str | None) -> float | None:
    """«47» → 47, «47D» → 47.6, «47 BIS» → 47.1, «47 BIS A» (de leer(): «47 BISA») → 47.108, «47A BIS» → 47.25."""
    if not num:
        return None
    # La letra no puede ser la B de «BIS»
    m = re.match(r"^(\d{1,3})\s*([A-F](?!IS))?(?:\s*(BIS)\s*([A-F])?)?", num)
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2):
        v += ("ABCDEF".index(m.group(2)) + 1) * 0.15
    if m.group(3):
        v += 0.1
        if m.group(4):  # entre «47 BIS» y «47A»
            v += ("ABCDEF".index(m.group(4)) + 1) * 0.008
    return v


class GrillaCasco:
    """Convierte (calle, carrera) en (lat, lon) con un ajuste afín local sobre los cruces conocidos."""

    def __init__(self, puntos: list[dict]):
        self.p = [(q["cl"], q["kr"], q["lat"], q["lon"]) for q in puntos]

    @classmethod
    def desde_archivo(cls, ruta: Path | None = None) -> "GrillaCasco":
        ruta = ruta or RAIZ_GEO / "grilla_casco.json"
        if not ruta.exists():
            return cls([])
        return cls(json.loads(ruta.read_text(encoding="utf-8"))["puntos"])

    def ubicar(self, cl: float, kr: float) -> tuple[float, float, float] | None:
        """(lat, lon, distancia en cuadras al cruce conocido más cercano) o None si está fuera de la grilla."""
        if len(self.p) < 3:
            return None
        cerca = sorted(((math.hypot(cl - c, kr - k), c, k, la, lo) for c, k, la, lo in self.p))[:12]
        dmin = cerca[0][0]
        if dmin > 6.0:  # más de seis cuadras fuera de los cruces conocidos: no se extrapola
            return None
        sigma = max(1.5, dmin)
        # Mínimos cuadrados ponderados: lat = a + b·cl + c·kr (y lo mismo para lon)
        S = [[0.0] * 3 for _ in range(3)]
        bl = [0.0] * 3
        bo = [0.0] * 3
        for d, c, k, la, lo in cerca:
            w = math.exp(-(d * d) / (2 * sigma * sigma))
            v = (1.0, c - cl, k - kr)
            for i in range(3):
                for j in range(3):
                    S[i][j] += w * v[i] * v[j]
                bl[i] += w * v[i] * la
                bo[i] += w * v[i] * lo
        det = _det3(S)
        if abs(det) < 1e-9:
            w = [(1 / (d + 0.05) ** 2, la, lo) for d, _, _, la, lo in cerca[:4]]
            t = sum(x[0] for x in w)
            return sum(x[0] * x[1] for x in w) / t, sum(x[0] * x[2] for x in w) / t, dmin
        lat = _det3(_col(S, 0, bl)) / det
        lon = _det3(_col(S, 0, bo)) / det
        return lat, lon, dmin

    def ubicar_direccion(self, d: Direccion) -> tuple[float, float, float] | None:
        n, x = _valor(d.num), _valor(d.cruce)
        if n is None or x is None:
            return None
        placa = min(int(d.placa), 95) / 100 if d.placa and d.placa.isdigit() else 0.3
        if d.via in ("CL", "DG"):
            return self.ubicar(n, x + placa)
        if d.via in ("KR", "TV"):
            return self.ubicar(x + placa, n)
        return None


def _det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _col(m, j, v):
    return [[v[i] if c == j else m[i][c] for c in range(3)] for i in range(3)]


class Geocodificador:
    def __init__(self, nomenclator: Nomenclator, grilla: GrillaCasco):
        self.nom = nomenclator
        self.grilla = grilla

    def ubicar(self, texto: object) -> tuple[Direccion, Ubicacion]:
        d = leer(texto)
        r = self.grilla.ubicar_direccion(d) if d.tiene_placa else None
        # Una placa que cae en la grilla del casco decide entre homónimos («LA PAZ» barrio o vereda)
        lugar, todos, conf = self.nom.reconocer(d, casco=r is not None and r[2] <= 2.5)
        zona = lugar.zona if lugar else zona_por_texto(d)
        en_casco = zona != "rural" and (lugar is None or (lugar.zona == "urbana" and lugar.padre in (None, "", CASCO)))
        if r and en_casco:
            lat, lon, dist = r
            return d, Ubicacion(round(lat, 6), round(lon, 6), "direccion" if dist <= 2.5 else "direccion_aprox",
                                "urbana", lugar, 1.0 if dist <= 2.5 else 0.7 if dist <= 4 else 0.5)
        if lugar is not None:
            if lugar.lat is not None:
                return d, Ubicacion(lugar.lat, lugar.lon, lugar.tipo, lugar.zona, lugar, conf)
            return d, Ubicacion(None, None, None, lugar.zona, lugar, conf)
        return d, Ubicacion(None, None, None, zona, None, 0.0)
