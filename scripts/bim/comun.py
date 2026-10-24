"""Utilidades comunes del modelo BIM de la torre (equipo F): rutas, lectura y escritura deterministas, GlobalId IFC,
proyección al Origen Nacional (EPSG:9377) y geometría simple.

Solo biblioteca estándar de Python 3.12. Todo lo que se escribe sale igual en dos corridas (sin fechas del reloj, sin
azar, con el orden fijo de las listas y con los números redondeados)."""
import hashlib
import json
import math
from pathlib import Path

R = Path(__file__).resolve().parent.parent.parent
D = R / 'data'
BIM = D / 'bim'
WEB = R / 'web'

INSUMOS = {
    'plantas': D / 'edificios/torre_hospital_plantas.json',
    'estructura': D / 'sismo/torre_hospital_estructura.json',
    'inventario': D / 'proyectos/torre_hospital/inventario_dotacion.json',
    'catalogo': D / 'proyectos/torre_hospital/catalogo_equipos.json',
    'presupuesto': D / 'proyectos/torre_hospital/presupuesto.json',
    'apu': D / 'proyectos/torre_hospital/apu.json',
    'programa': D / 'proyectos/torre_hospital/programa.json',
    'cronograma': R / 'docs/11-torre-hospital-nivel-1.md',
}


def leer(ruta):
    return json.loads(Path(ruta).read_text(encoding='utf-8'))


def sha1(ruta):
    return hashlib.sha1(Path(ruta).read_bytes()).hexdigest()


def rel(ruta):
    return str(Path(ruta).resolve().relative_to(R))


def r(x, n=4):
    """Redondeo estable (sin −0,0)."""
    if x is None:
        return None
    v = round(float(x), n)
    return 0.0 if v == 0 else v


def rp(p, n=4):
    return [r(c, n) for c in p]


def escribir_json(ruta, obj, listas_por_linea=()):
    """JSON en UTF-8 sin espacios, con un salto de línea por clave de primer nivel y, en las listas nombradas en
    listas_por_linea, uno por elemento (diferencias legibles en git). Mismos bytes en cada corrida."""
    partes = []
    for k, v in obj.items():
        if k in listas_por_linea and isinstance(v, list):
            filas = ',\n'.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in v)
            partes.append(f'{json.dumps(k)}:[\n{filas}\n]')
        else:
            partes.append(f'{json.dumps(k)}:{json.dumps(v, ensure_ascii=False, separators=(",", ":"))}')
    texto = '{\n' + ',\n'.join(partes) + '\n}\n'
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(texto, encoding='utf-8')
    return len(texto.encode('utf-8'))


# ---------------------------------------------------------------------------------------------------- GlobalId IFC
_B64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'


def _b64(v, n):
    return ''.join(_B64[(v >> (6 * i)) & 63] for i in range(n - 1, -1, -1))


def guid(clave):
    """GlobalId IFC determinista de 22 caracteres: los 128 bits de un UUID de versión 5 (SHA-1 del espacio de nombres
    «atlas-yondo/torre_hospital» y la clave) comprimidos con el alfabeto de IFC (como ifcopenshell.guid.compress)."""
    h = bytearray(hashlib.sha1(('atlas-yondo/torre_hospital|' + clave).encode('utf-8')).digest()[:16])
    h[6] = (h[6] & 0x0F) | 0x50          # versión 5
    h[8] = (h[8] & 0x3F) | 0x80          # variante RFC 4122
    out = _b64(h[0], 2)
    for i in range(1, 16, 3):
        out += _b64((h[i] << 16) | (h[i + 1] << 8) | h[i + 2], 4)
    return out


# ------------------------------------------------------------------------------- proyección transversa de Mercator
# EPSG:9377 «MAGNA-SIRGAS 2018 / Origen-Nacional» (Resolución IGAC 471 de 2020 y 529 de 2020): elipsoide GRS 1980,
# latitud de origen 4° N, meridiano central 73° W, factor de escala 0,9992, falso este 5.000.000 m, falso norte
# 2.000.000 m. Fórmulas de Krüger en la forma de la nota guía 7-2 de IOGP (EPSG), «Transverse Mercator (JHS)».
CRS_9377 = {'epsg': 9377, 'nombre': 'MAGNA-SIRGAS 2018 / Origen-Nacional', 'datum': 'MAGNA-SIRGAS 2018',
            'proyeccion': 'Transverse Mercator', 'lat0': 4.0, 'lon0': -73.0, 'k0': 0.9992, 'FE': 5000000.0,
            'FN': 2000000.0, 'a': 6378137.0, 'inv_f': 298.257222101}


def tm_directa(lat, lon, crs=CRS_9377):
    a, f = crs['a'], 1 / crs['inv_f']
    e = math.sqrt(f * (2 - f))
    n = f / (2 - f)
    B = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    h = [n / 2 - 2 / 3 * n ** 2 + 5 / 16 * n ** 3 + 41 / 180 * n ** 4,
         13 / 48 * n ** 2 - 3 / 5 * n ** 3 + 557 / 1440 * n ** 4,
         61 / 240 * n ** 3 - 103 / 140 * n ** 4,
         49561 / 161280 * n ** 4]

    def xi_eta(phi, dl):
        Q = math.asinh(math.tan(phi)) - e * math.atanh(e * math.sin(phi))
        beta = math.atan(math.sinh(Q))
        eta0 = math.atanh(math.cos(beta) * math.sin(dl))
        xi0 = math.asin(math.sin(beta) * math.cosh(eta0))
        xi = xi0 + sum(h[k] * math.sin(2 * (k + 1) * xi0) * math.cosh(2 * (k + 1) * eta0) for k in range(4))
        eta = eta0 + sum(h[k] * math.cos(2 * (k + 1) * xi0) * math.sinh(2 * (k + 1) * eta0) for k in range(4))
        return xi, eta

    xi_o, _ = xi_eta(math.radians(crs['lat0']), 0.0)
    xi, eta = xi_eta(math.radians(lat), math.radians(lon - crs['lon0']))
    E = crs['FE'] + crs['k0'] * B * eta
    N = crs['FN'] + crs['k0'] * (B * xi - B * xi_o)
    return E, N


def local_a_geo(x, y, ancla):
    """Marco del proyecto (programa.json → implantacion.marco_de_coordenadas.conversion_a_wgs84)."""
    lat = ancla['lat'] + y / 111320.0
    lon = ancla['lon'] + x / (111320.0 * math.cos(math.radians(ancla['lat'])))
    return lat, lon


def georreferencia(ancla):
    """Este y norte del ancla en EPSG:9377, dirección del eje x local (el este verdadero) en la cuadrícula, convergencia
    de meridianos y factor de escala del punto (cálculo propio con las fórmulas de arriba)."""
    E0, N0 = tm_directa(ancla['lat'], ancla['lon'])
    d = 50.0
    lat_e, lon_e = local_a_geo(d, 0.0, ancla)
    Ee, Ne = tm_directa(lat_e, lon_e)
    lat_n, lon_n = local_a_geo(0.0, d, ancla)
    En, Nn = tm_directa(lat_n, lon_n)
    ux, uy = Ee - E0, Ne - N0
    L = math.hypot(ux, uy)
    # convergencia: rumbo de cuadrícula del norte verdadero (positivo si el norte verdadero queda al este del de la cuadrícula)
    conv = math.degrees(math.atan2(En - E0, Nn - N0))
    # factor de escala del punto con un arco corto sobre el paralelo (elipsoide): radio del paralelo ν·cos φ
    a, f = CRS_9377['a'], 1 / CRS_9377['inv_f']
    e2 = f * (2 - f)
    phi = math.radians(ancla['lat'])
    nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    dlon = math.radians(lon_e - ancla['lon'])
    s_elip = nu * math.cos(phi) * dlon
    k = L / s_elip
    return {'este': E0, 'norte': N0, 'eje_x': [ux / L, uy / L], 'convergencia_deg': conv, 'factor_escala': k}


def angulo_dms(v):
    """Ángulo en grados → IfcCompoundPlaneAngleMeasure (grados, minutos, segundos, millonésimas), todos con el signo."""
    s = -1 if v < 0 else 1
    a = abs(v)
    g = int(a)
    m_ = int((a - g) * 60)
    seg = (a - g - m_ / 60) * 3600
    sec = int(seg)
    mic = int(round((seg - sec) * 1e6))
    if mic == 1000000:
        sec, mic = sec + 1, 0
    return [s * g, s * m_, s * sec, s * mic]


# ------------------------------------------------------------------------------------------------ geometría simple
def area_poligono(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def perimetro(p):
    return sum(math.dist(p[i], p[(i + 1) % len(p)]) for i in range(len(p)))


def caja_de_puntos(pts):
    xs, ys, zs = zip(*pts)
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def solape_cajas(a0, a1, b0, b1):
    """Penetración por eje entre dos cajas alineadas (negativo = separación)."""
    return [min(a1[i], b1[i]) - max(a0[i], b0[i]) for i in range(3)]


def norm(v):
    L = math.sqrt(sum(c * c for c in v))
    return [c / L for c in v] if L else list(v)


def cruz(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def suma(a, b, k=1.0):
    return [a[i] + k * b[i] for i in range(len(a))]


def largo_polilinea(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def fecha_iso(texto_mes, fin=False):
    """'2028-11' → '2028-11-01' (o el último día del mes si fin)."""
    y, m = (int(x) for x in texto_mes.split('-'))
    if not fin:
        return f'{y:04d}-{m:02d}-01'
    dias = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return f'{y:04d}-{m:02d}-{dias:02d}'
