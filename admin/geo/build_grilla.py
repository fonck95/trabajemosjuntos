"""Grilla de nomenclatura del casco urbano de Yondó a partir de OpenStreetMap.

Lee los extractos de OSM que ya están en `data/geo/` (© colaboradores de OpenStreetMap, ODbL), toma las vías con
nombre «Calle N» / «Carrera N» y calcula dónde se cruza cada calle con cada carrera. Esos cruces son los puntos de
control con los que `app/pipeline/geocodificador.py` convierte «CL 49 # 45-12» en una coordenada, también para las
calles que OSM no tiene con nombre (se interpolan entre las vecinas).

Uso: python3 admin/geo/build_grilla.py   →   admin/geo/grilla_casco.json
"""
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

R = Path(__file__).resolve().parents[2]
FUENTES = ["osm_amplio.xml", "osm_vias.xml", "osm_map.xml", "osm_corredor_puente.xml"]
CENTRO = (7.0065, -73.9115)
RADIO_M = 2600  # el casco urbano; descarta homónimas lejanas («Carrera 7» de otra vereda)
NOMBRE = re.compile(r"^(Calle|Carrera|Diagonal|Transversal)\s+(\d{1,3})\s*([A-F])?(?:\s*Bis)?$", re.I)


def a_metros(lat, lon):
    k = 111_320.0
    return ((lon - CENTRO[1]) * k * math.cos(math.radians(CENTRO[0])), (lat - CENTRO[0]) * k)


def a_grados(x, y):
    k = 111_320.0
    return (CENTRO[0] + y / k, CENTRO[1] + x / (k * math.cos(math.radians(CENTRO[0]))))


def numero(n, letra):
    """«47» → 47.0, «47D» → 47.6: las letras van entre la vía y la siguiente."""
    return int(n) + (("ABCDEF".index(letra.upper()) + 1) * 0.15 if letra else 0.0)


def cruce(p1, p2, q1, q2):
    """Intersección de los segmentos p1p2 y q1q2, o None."""
    d = (p2[0] - p1[0]) * (q2[1] - q1[1]) - (p2[1] - p1[1]) * (q2[0] - q1[0])
    if abs(d) < 1e-9:
        return None
    t = ((q1[0] - p1[0]) * (q2[1] - q1[1]) - (q1[1] - p1[1]) * (q2[0] - q1[0])) / d
    u = ((q1[0] - p1[0]) * (p2[1] - p1[1]) - (q1[1] - p1[1]) * (p2[0] - p1[0])) / d
    if -0.02 <= t <= 1.02 and -0.02 <= u <= 1.02:
        return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))
    return None


def proyectar(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = vx * vx + vy * vy or 1e-9
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L))
    q = (a[0] + t * vx, a[1] + t * vy)
    return q, math.dist(p, q)


def main():
    vias = {}  # (tipo, numero) → lista de polilíneas en metros
    for f in FUENTES:
        raiz = ET.parse(R / "data" / "geo" / f).getroot()
        nodos = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in raiz.findall("node")}
        for w in raiz.findall("way"):
            tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
            m = NOMBRE.match(tags.get("name", "").strip()) if "highway" in tags else None
            if not m:
                continue
            pts = [a_metros(*nodos[nd.get("ref")]) for nd in w.findall("nd") if nd.get("ref") in nodos]
            if len(pts) < 2 or min(math.hypot(*p) for p in pts) > RADIO_M:
                continue
            tipo = {"calle": "CL", "carrera": "KR", "diagonal": "CL", "transversal": "KR"}[m.group(1).lower()]
            clave = (tipo, numero(m.group(2), m.group(3)))
            linea = [round(c, 1) for p in pts for c in p]
            lista = vias.setdefault(clave, [])
            if linea not in lista:
                lista.append(linea)

    def segmentos(clave):
        for linea in vias[clave]:
            pts = list(zip(linea[::2], linea[1::2]))
            yield from zip(pts, pts[1:])

    puntos = []
    calles = sorted(k for k in vias if k[0] == "CL")
    carreras = sorted(k for k in vias if k[0] == "KR")
    for c in calles:
        for k in carreras:
            hallado = None
            for a, b in segmentos(c):
                for p, q in segmentos(k):
                    x = cruce(a, b, p, q)
                    if x:
                        hallado = x
                        break
                if hallado:
                    break
            if not hallado:  # se tocan casi: extremos a menos de 20 m
                mejor = None
                for a, b in segmentos(c):
                    for p, q in segmentos(k):
                        for punto, (s1, s2) in ((p, (a, b)), (q, (a, b)), (a, (p, q)), (b, (p, q))):
                            proy, d = proyectar(punto, s1, s2)
                            if d < 20 and (mejor is None or d < mejor[1]):
                                mejor = (((punto[0] + proy[0]) / 2, (punto[1] + proy[1]) / 2), d)
                if mejor:
                    hallado = mejor[0]
            if hallado:
                lat, lon = a_grados(*hallado)
                puntos.append({"cl": c[1], "kr": k[1], "lat": round(lat, 6), "lon": round(lon, 6)})

    salida = {
        "fuente": "© colaboradores de OpenStreetMap (ODbL); extractos de data/geo/",
        "centro": {"lat": CENTRO[0], "lon": CENTRO[1]},
        "calles": sorted({c[1] for c in calles}),
        "carreras": sorted({k[1] for k in carreras}),
        "puntos": puntos,
        "vias": [{"tipo": t, "num": n, "lineas": [[list(a_grados(x, y))[::-1] for x, y in zip(l[::2], l[1::2])] for l in ls]}
                 for (t, n), ls in sorted(vias.items())],
    }
    for v in salida["vias"]:
        v["lineas"] = [[[round(lon, 6), round(lat, 6)] for lon, lat in l] for l in v["lineas"]]
    destino = Path(__file__).with_name("grilla_casco.json")
    destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(calles)} calles, {len(carreras)} carreras, {len(puntos)} cruces → {destino}")


if __name__ == "__main__":
    main()
