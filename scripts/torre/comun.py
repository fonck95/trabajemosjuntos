"""Utilidades compartidas de los scripts de la torre (plantas, exigencias, inventario y matriz de habilitación).

Contrato: data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md (secciones 0, 1.3, 3, 4 y Anexo A).
Solo biblioteca estándar (Python 3.12). Lo usan generar_plantas.py, validar_plantas.py, normalizar_exigencias.py,
generar_inventario.py, validar_inventario.py y test_torre.py.

Qué trae:
- rutas del repositorio y carga y escritura determinista de JSON (misma entrada, mismos bytes);
- huellas SHA-1 y SHA-256 de archivos (campo insumos_sha1 de los generados, 10.1);
- identificadores estables de la regla 1.3 (recintos, circulaciones, muros, puertas, ventanas, líneas, unidades, exigencias);
- redondeos sin «-0.0» y comprobación de múltiplos (rejilla de 0,05 m del trazado);
- conversión de marco: x este, y norte, z arriba (metros desde el ancla) → three.js (X, Y, Z) = (x, nivel.z + z, −y);
- geometría de polígonos ortogonales y de rectángulos girados (áreas, contención, traslapes, bordes comunes,
  desplazamiento de bordes hacia adentro para el polígono libre, ancho mínimo) y una rejilla con distancias
  (búsqueda en anchura con pesos, 8 vecinos) para recorridos de evacuación y pasos libres;
- referencias a ambientes de programa.json por fila o por {servicio_programa, nombre} (regla común del 3.4);
- el informe JSON que imprimen los validadores.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / 'data'
TORRE = DATOS / 'proyectos' / 'torre_hospital'
EDIFICIOS = DATOS / 'edificios'
FUENTES_INVESTIGACION = TORRE / 'fuentes_investigacion'
FIXTURES = RAIZ / 'scripts' / 'fixtures' / 'torre'

PROGRAMA = TORRE / 'programa.json'
DOTACION = TORRE / 'dotacion.json'
LABORATORIO = TORRE / 'laboratorio.json'
NORMAS = TORRE / 'normas.json'
CATALOGO = TORRE / 'catalogo_equipos.json'
IMPLEMENTOS = TORRE / 'implementos.json'
REGLAS_PLANTA = TORRE / 'reglas_planta.json'
REGLAS_UBICACION = TORRE / 'reglas_ubicacion.json'
REGLAS_EXIGENCIAS = TORRE / 'reglas_exigencias.json'
EXIGENCIAS = TORRE / 'exigencias_3100.json'
INVENTARIO = TORRE / 'inventario_dotacion.json'
HABILITACION = TORRE / 'habilitacion.json'
TRAZADO = EDIFICIOS / 'torre_hospital_trazado.json'
PLANTAS = EDIFICIOS / 'torre_hospital_plantas.json'


def relativa(ruta) -> str:
    """Ruta relativa a la raíz del repositorio (para informes y campos insumos_sha1); si no se puede, la absoluta."""
    p = Path(ruta).resolve()
    try:
        return p.relative_to(RAIZ).as_posix()
    except ValueError:
        return p.as_posix()


# --------------------------------------------------------------------------------------------------------------------
# JSON: carga y escritura determinista
# --------------------------------------------------------------------------------------------------------------------
def cargar_json(ruta):
    """Lee un JSON en UTF-8. Falla con un mensaje claro si el archivo no existe o no es JSON válido."""
    p = Path(ruta)
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise FileNotFoundError(f'no existe el archivo {relativa(p)}') from None
    except json.JSONDecodeError as e:
        raise ValueError(f'{relativa(p)} no es JSON válido: {e}') from None


def _plano(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(', ', ': '))


def _formatear(v, sangria: int, ancho: int) -> str:
    plano = _plano(v)
    if not isinstance(v, (dict, list)) or not v or sangria + len(plano) <= ancho:
        return plano
    pre = ' ' * (sangria + 1)
    if isinstance(v, dict):
        partes = [f'{pre}{json.dumps(k, ensure_ascii=False)}: {_formatear(x, sangria + 1, ancho)}' for k, x in v.items()]
        return '{\n' + ',\n'.join(partes) + '\n' + ' ' * sangria + '}'
    partes = [pre + _formatear(x, sangria + 1, ancho) for x in v]
    return '[\n' + ',\n'.join(partes) + '\n' + ' ' * sangria + ']'


def texto_json(datos, compacto: bool = False, ancho: int = 120) -> str:
    """Texto JSON determinista: sin escapar tildes, sangría de 1 espacio y los objetos y listas cortos en una sola línea
    (así las coordenadas no ocupan una línea por número). `compacto=True` da la forma web, sin espacios."""
    if compacto:
        return json.dumps(datos, ensure_ascii=False, separators=(',', ':')) + '\n'
    return _formatear(datos, 0, ancho) + '\n'


def escribir_json(ruta, datos, compacto: bool = False, ancho: int = 120) -> bool:
    """Escribe el JSON solo si cambió. Devuelve True si escribió (así una segunda corrida no toca el archivo)."""
    p = Path(ruta)
    texto = texto_json(datos, compacto=compacto, ancho=ancho)
    if p.exists() and p.read_text(encoding='utf-8') == texto:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding='utf-8')
    return True


def sha1_texto(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def sha1_archivo(ruta) -> str:
    return hashlib.sha1(Path(ruta).read_bytes()).hexdigest()


def sha256_archivo(ruta) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def insumos_sha1(rutas) -> dict:
    """{nombre del archivo: sha1} en el orden dado (campo insumos_sha1 de los archivos generados, 10.1)."""
    return {Path(r).name: sha1_archivo(r) for r in rutas}


# --------------------------------------------------------------------------------------------------------------------
# Identificadores estables (1.3)
# --------------------------------------------------------------------------------------------------------------------
# letra del tipo de línea de dotación → (origen por defecto, nombre del tipo)
LETRAS_LINEA = {'e': 'equipo', 'm': 'mobiliario', 'f': 'equipamiento fijo', 'c': 'equipo de laboratorio.json',
                'x': 'cierre de brechas', 'i': 'infraestructura (capa del 16.3; sin precio de dotación)'}
ORIGEN_POR_LETRA = {'e': 'dotacion', 'm': 'dotacion', 'f': 'dotacion', 'c': 'laboratorio', 'x': 'cierre_brechas',
                    'i': 'infraestructura'}
SRV_EXIGENCIA = ('URG', 'HOS', 'PAR', 'EST', 'EXP', 'CEX', 'ODO', 'TEL', 'VAC', 'FAR', 'TER', 'LAB', 'TOM', 'IMG', 'ROD',
                 'TIC')

# Niveles de la planta (3.3 y 16.1): EXT (exteriores inmediatos, cota 0), P1-P4, BT (bloque técnico) y CUB (cubierta)
RE_NIVEL = re.compile(r'^(P[1-4]|BT|CUB|EXT)$')
RE_RECINTO = re.compile(r'^(P[1-4]|BT|CUB|EXT)-A(\d{3})-(\d{2})$')
RE_CIRCULACION = re.compile(r'^(P[1-4]|BT|CUB|EXT)-CIRC-(\d{2})$')
# recinto técnico o de apoyo que no está en programa.json (16.1: «créalo como recinto no programado»; estimación)
RE_TECNICO = re.compile(r'^(P[1-4]|BT|CUB|EXT)-TEC-(\d{2})$')
RE_NUCLEO = re.compile(r'^(P[1-4]|BT|CUB|EXT)-NUC-[A-Z0-9][A-Z0-9-]*$')
RE_MURO = re.compile(r'^(P[1-4]|BT|CUB|EXT)-M-(\d{4})$')
RE_PUERTA = re.compile(r'^(P[1-4]|BT|CUB|EXT)-PT-(\d{3})$')
RE_VENTANA = re.compile(r'^(P[1-4]|BT|CUB|EXT)-VN-(\d{3})$')
RE_LINEA = re.compile(r'^L-([a-z0-9_]+)-([emfcxi])-([0-9a-f]{6})$')
RE_UNIDAD = re.compile(r'^U-([a-z0-9_]+)-([0-9a-f]{6})-(\d{3})(?:-c(\d+))?$')
RE_EXIGENCIA = re.compile(r'^EX-(?:(' + '|'.join(SRV_EXIGENCIA) + r')-(\d{3})|TOD-([CA])(\d{2}))$')
RE_COLOR = re.compile(r'^#[0-9a-f]{6}$')


def prefijo_nivel(piso) -> str:
    """1 → «P1»; «BT» o «bloque técnico» → «BT»; «CUB» → «CUB»; «EXT» o «exterior» → «EXT»."""
    if isinstance(piso, int) and 1 <= piso <= 4:
        return f'P{piso}'
    s = str(piso).strip().upper()
    if s in ('BT', 'BLOQUE TÉCNICO', 'BLOQUE TECNICO'):
        return 'BT'
    if s in ('CUB', 'CUBIERTA'):
        return 'CUB'
    if s in ('EXT', 'EXTERIOR', 'EXTERIORES'):
        return 'EXT'
    if re.fullmatch(r'P?[1-4]', s):
        return 'P' + s[-1]
    raise ValueError(f'piso desconocido: {piso!r}')


def id_recinto(piso, fila: int, k: int) -> str:
    """Recinto del programa: P{piso}-A{fila:03d}-{k:02d} (BT-A{fila:03d}-{k:02d} en el bloque técnico)."""
    return f'{prefijo_nivel(piso)}-A{fila:03d}-{k:02d}'


def id_circulacion(piso, n: int) -> str:
    return f'{prefijo_nivel(piso)}-CIRC-{n:02d}'


def id_tecnico(piso, n: int) -> str:
    """Recinto no programado (técnico o de apoyo que pide el 16 y no trae programa.json): {nivel}-TEC-{nn}."""
    return f'{prefijo_nivel(piso)}-TEC-{n:02d}'


def id_muro(piso, n: int) -> str:
    return f'{prefijo_nivel(piso)}-M-{n:04d}'


def id_puerta(piso, n: int) -> str:
    return f'{prefijo_nivel(piso)}-PT-{n:03d}'


def id_ventana(piso, n: int) -> str:
    return f'{prefijo_nivel(piso)}-VN-{n:03d}'


def h6(origen: str, servicio: str, letra: str, nombre: str) -> str:
    """6 primeros caracteres hexadecimales del SHA-1 (UTF-8) de «origen|servicio|tipo|nombre exacto» (1.3)."""
    if letra not in LETRAS_LINEA:
        raise ValueError(f'letra de tipo desconocida: {letra!r} (se espera una de {"".join(LETRAS_LINEA)})')
    return sha1_texto(f'{origen}|{servicio}|{letra}|{nombre}')[:6]


def id_linea(servicio: str, letra: str, nombre: str, origen: str | None = None) -> str:
    """Línea de dotación: L-{servicio}-{tipo}-{h6}. El origen por defecto sale de la letra (dotacion, laboratorio o
    cierre_brechas); el equipamiento fijo usa servicio «fijo» y origen «dotacion»."""
    origen = origen or ORIGEN_POR_LETRA[letra]
    return f'L-{servicio}-{letra}-{h6(origen, servicio, letra, nombre)}'


def partes_linea(id_l: str) -> tuple[str, str, str]:
    """'L-urgencias-e-2cd8df' → ('urgencias', 'e', '2cd8df')."""
    m = RE_LINEA.match(id_l)
    if not m:
        raise ValueError(f'id de línea mal formado: {id_l!r}')
    return m.group(1), m.group(2), m.group(3)


def id_unidad(servicio: str, h: str, k: int) -> str:
    """Unidad física: U-{servicio}-{h6}-{k:03d}."""
    return f'U-{servicio}-{h}-{k:03d}'


def id_unidad_de_linea(id_l: str, k: int) -> str:
    servicio, _, h = partes_linea(id_l)
    return id_unidad(servicio, h, k)


def id_componente(id_u: str, n: int) -> str:
    """Componente de una unidad (kits, laringoscopio neonatal): {id de la unidad}-c{n}."""
    return f'{id_u}-c{n}'


def id_exigencia(srv: str, n: int) -> str:
    if srv not in SRV_EXIGENCIA:
        raise ValueError(f'servicio de exigencia desconocido: {srv!r}')
    return f'EX-{srv}-{n:03d}'


def id_exigencia_todos(archivo: str, n: int) -> str:
    """Filas de «todos los servicios»: C = consulta y ambulatorio, A = apoyo diagnóstico."""
    if archivo not in ('C', 'A'):
        raise ValueError('el archivo de «todos los servicios» es C (consulta) o A (apoyo)')
    return f'EX-TOD-{archivo}{n:02d}'


# --------------------------------------------------------------------------------------------------------------------
# Redondeos
# --------------------------------------------------------------------------------------------------------------------
def redondear(x: float, nd: int = 2) -> float:
    """Redondeo a nd decimales sin «-0.0» (para que dos corridas escriban lo mismo)."""
    r = round(float(x), nd)
    return 0.0 if r == 0 else r


def redondear_todo(v, nd: int = 2):
    """Redondea todos los números de punto flotante de una estructura (listas y diccionarios anidados)."""
    if isinstance(v, float):
        return redondear(v, nd)
    if isinstance(v, list):
        return [redondear_todo(x, nd) for x in v]
    if isinstance(v, tuple):
        return [redondear_todo(x, nd) for x in v]
    if isinstance(v, dict):
        return {k: redondear_todo(x, nd) for k, x in v.items()}
    return v


def es_multiplo(x: float, paso: float, origen: float = 0.0, tol: float = 1e-6) -> bool:
    q = (x - origen) / paso
    return abs(q - round(q)) * paso <= tol


# --------------------------------------------------------------------------------------------------------------------
# Marco de coordenadas (0): x este, y norte, z arriba; metros desde el ancla
# --------------------------------------------------------------------------------------------------------------------
ANCLA = {'lat': 7.005271, 'lon': -73.914597}
MARCO = {'ancla': dict(ANCLA), 'ejes': 'x este, y norte, z arriba; metros', 'a_three': '(X, Y, Z) = (x, z, -y)'}


def a_three(p, nivel_z: float = 0.0) -> tuple[float, float, float]:
    """(x, y, z sobre el piso terminado) → (X, Y, Z) de three.js = (x, nivel.z + z, −y)."""
    x, y = p[0], p[1]
    z = p[2] if len(p) > 2 else 0.0
    return (x, nivel_z + z, 0.0 - y)


def desde_three(P, nivel_z: float = 0.0) -> tuple[float, float, float]:
    X, Y, Z = P
    return (X, 0.0 - Z, Y - nivel_z)


def giro_three(rotacion_z: float) -> float:
    """Giro antihorario en planta θ (desde +x) → rotation.y de three.js (es el mismo valor)."""
    return rotacion_z


def a_wgs84(x: float, y: float) -> tuple[float, float]:
    """Metros del marco → (lat, lon) con la fórmula de programa.json → implantacion.marco_de_coordenadas."""
    lat = ANCLA['lat'] + y / 111320
    lon = ANCLA['lon'] + x / (111320 * math.cos(math.radians(ANCLA['lat'])))
    return lat, lon


def angulo_normalizado(grados: float) -> float:
    """Ángulo en [0, 360)."""
    g = math.fmod(grados, 360.0)
    return g + 360.0 if g < 0 else g


# --------------------------------------------------------------------------------------------------------------------
# Geometría en planta
# --------------------------------------------------------------------------------------------------------------------
EPS = 1e-6


def _k(v: float) -> float:
    """Clave numérica estable para comparar coordenadas (múltiplos de 1 µm)."""
    return round(v, 6) + 0.0


def rect_a_poligono(r) -> list[list[float]]:
    """[x0, y0, x1, y1] → polígono antihorario [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]."""
    x0, y0, x1, y1 = r
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def area_con_signo(p) -> float:
    s = 0.0
    n = len(p)
    for i in range(n):
        x0, y0 = p[i][0], p[i][1]
        x1, y1 = p[(i + 1) % n][0], p[(i + 1) % n][1]
        s += x0 * y1 - x1 * y0
    return s / 2


def area_poligono(p) -> float:
    return abs(area_con_signo(p))


def orientar_antihorario(p) -> list[list[float]]:
    q = [list(v[:2]) for v in p]
    return q if area_con_signo(q) >= 0 else q[::-1]


def caja(p) -> tuple[float, float, float, float]:
    xs = [v[0] for v in p]
    ys = [v[1] for v in p]
    return min(xs), min(ys), max(xs), max(ys)


def cajas_se_tocan(a, b, tol: float = 0.0) -> bool:
    return not (a[2] < b[0] - tol or b[2] < a[0] - tol or a[3] < b[1] - tol or b[3] < a[1] - tol)


def bordes(p) -> list[tuple[list[float], list[float]]]:
    return [(p[i], p[(i + 1) % len(p)]) for i in range(len(p))]


def perimetro(p) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in bordes(p))


def centroide(p) -> tuple[float, float]:
    """Centroide de área (si el área es nula, el promedio de los vértices)."""
    a = area_con_signo(p)
    if abs(a) < EPS:
        return sum(v[0] for v in p) / len(p), sum(v[1] for v in p) / len(p)
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in ((u[:2], v[:2]) for u, v in bordes(p)):
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return cx / (6 * a), cy / (6 * a)


def es_ortogonal(p, tol: float = EPS) -> bool:
    return all(abs(a[0] - b[0]) <= tol or abs(a[1] - b[1]) <= tol for a, b in bordes(p))


def limpiar_poligono(p, tol: float = EPS) -> list[list[float]]:
    """Quita vértices repetidos y vértices intermedios colineales."""
    q = []
    for v in p:
        if not q or math.dist(q[-1], v[:2]) > tol:
            q.append([v[0], v[1]])
    if len(q) > 1 and math.dist(q[0], q[-1]) <= tol:
        q.pop()
    cambio = True
    while cambio and len(q) > 3:
        cambio = False
        for i in range(len(q)):
            a, b, c = q[i - 1], q[i], q[(i + 1) % len(q)]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) <= tol:
                q.pop(i)
                cambio = True
                break
    return q


def distancia_punto_segmento(pt, a, b) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist(pt[:2], a[:2])
    t = max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / L2))
    return math.hypot(pt[0] - (ax + t * dx), pt[1] - (ay + t * dy))


def distancia_a_borde(pt, p) -> float:
    return min(distancia_punto_segmento(pt, a, b) for a, b in bordes(p))


def punto_en_poligono(pt, p, tol: float = EPS) -> bool:
    """True si el punto está dentro del polígono o a menos de `tol` de su borde."""
    if distancia_a_borde(pt, p) <= tol:
        return True
    x, y = pt[0], pt[1]
    dentro = False
    n = len(p)
    for i in range(n):
        x0, y0 = p[i][0], p[i][1]
        x1, y1 = p[(i + 1) % n][0], p[(i + 1) % n][1]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xc > x:
                dentro = not dentro
    return dentro


def punto_estrictamente_dentro(pt, p, tol: float = EPS) -> bool:
    """Dentro y a más de `tol` del borde."""
    return distancia_a_borde(pt, p) > tol and punto_en_poligono(pt, p, 0.0)


def _rejilla_comun(poligonos):
    xs = sorted({_k(v[0]) for p in poligonos for v in p})
    ys = sorted({_k(v[1]) for p in poligonos for v in p})
    return xs, ys


def rectangulos(p) -> list[tuple[float, float, float, float]]:
    """Descompone un polígono ortogonal en rectángulos (x0, y0, x1, y1) sin traslapes, por filas: celdas de la rejilla
    de sus coordenadas, unidas en tramos horizontales y luego en vertical cuando los tramos coinciden."""
    xs, ys = _rejilla_comun([p])
    filas = []
    for j in range(len(ys) - 1):
        yc = (ys[j] + ys[j + 1]) / 2
        tramos, ini = [], None
        for i in range(len(xs) - 1):
            lleno = punto_en_poligono(((xs[i] + xs[i + 1]) / 2, yc), p, 0.0)
            if lleno and ini is None:
                ini = xs[i]
            if not lleno and ini is not None:
                tramos.append((ini, xs[i]))
                ini = None
        if ini is not None:
            tramos.append((ini, xs[-1]))
        filas.append((ys[j], ys[j + 1], tramos))
    salida, abiertos = [], {}
    for y0, y1, tramos in filas:
        nuevos = {}
        for t in tramos:
            if t in abiertos:
                nuevos[t] = (abiertos[t][0], y1)
            else:
                nuevos[t] = (y0, y1)
        for t, (a, b) in abiertos.items():
            if t not in nuevos:
                salida.append((t[0], a, t[1], b))
        abiertos = nuevos
    for t, (a, b) in abiertos.items():
        salida.append((t[0], a, t[1], b))
    return sorted(salida, key=lambda r: (r[1], r[0]))


def _area_celdas(poligonos, condicion) -> float:
    """Área de las celdas de la rejilla común cuyo centro cumple `condicion(lista de booleanos de pertenencia)`."""
    xs, ys = _rejilla_comun(poligonos)
    cajas_p = [caja(p) for p in poligonos]
    total = 0.0
    for j in range(len(ys) - 1):
        yc = (ys[j] + ys[j + 1]) / 2
        for i in range(len(xs) - 1):
            xc = (xs[i] + xs[i + 1]) / 2
            dentro = []
            for p, c in zip(poligonos, cajas_p):
                dentro.append(c[0] <= xc <= c[2] and c[1] <= yc <= c[3] and punto_en_poligono((xc, yc), p, 0.0))
            if condicion(dentro):
                total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return total


def area_interseccion(p, q) -> float:
    """Área de la intersección de dos polígonos ortogonales (exacta sobre la rejilla de sus coordenadas)."""
    if not cajas_se_tocan(caja(p), caja(q)):
        return 0.0
    return _area_celdas([p, q], all)


def area_libre(p, columnas=()) -> float:
    """Área libre de un recinto: la de su polígono libre (entre caras de muro) menos la de las columnas que entran en él
    (17.1: las columnas del prediseño DMO, de 0,80 m y 0,90 m en el eje A, sobresalen hasta 0,34 m de la cara del muro)."""
    a = area_poligono(p)
    for c in columnas or ():
        b, h = float(c.get('b', 0.6)) / 2, float(c.get('h', 0.6)) / 2
        a -= area_interseccion(p, rect_a_poligono([c['x'] - b, c['y'] - h, c['x'] + b, c['y'] + h]))
    return a


def area_union(poligonos) -> float:
    """Área de la unión de polígonos ortogonales."""
    if not poligonos:
        return 0.0
    return _area_celdas(list(poligonos), any)


def poligono_dentro_de(p, contenedor, tol: float = 1e-3) -> bool:
    """True si el polígono (ortogonal o convexo) queda dentro del contenedor ortogonal, con tolerancia `tol`:
    todos sus vértices adentro (o a menos de tol del borde) y ningún vértice del contenedor dentro de él."""
    if not all(punto_en_poligono(v, contenedor, tol) for v in p):
        return False
    if any(punto_estrictamente_dentro(v, p, tol) for v in contenedor):
        return False
    # bordes del polígono que cruzan el exterior del contenedor (polígonos no convexos): probar puntos medios
    return all(punto_en_poligono(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), contenedor, tol) for a, b in bordes(p))


def restar_rectangulo(r, q, tol: float = EPS) -> list[tuple[float, float, float, float]]:
    """Rectángulos (hasta 4, sin traslapes) de r menos q; r y q son (x0, y0, x1, y1)."""
    if q[2] <= r[0] + tol or q[0] >= r[2] - tol or q[3] <= r[1] + tol or q[1] >= r[3] - tol:
        return [tuple(r)]
    out = []
    if q[1] > r[1] + tol:
        out.append((r[0], r[1], r[2], q[1]))
    if q[3] < r[3] - tol:
        out.append((r[0], q[3], r[2], r[3]))
    y0, y1 = max(r[1], q[1]), min(r[3], q[3])
    if q[0] > r[0] + tol:
        out.append((r[0], y0, q[0], y1))
    if q[2] < r[2] - tol:
        out.append((q[2], y0, r[2], y1))
    return [x for x in out if x[2] - x[0] > tol and x[3] - x[1] > tol]


def rectangulos_menos(p, quitar, tol: float = EPS) -> list[tuple[float, float, float, float]]:
    """Rectángulos sin traslapes del polígono ortogonal p menos los rectángulos `quitar` (x0, y0, x1, y1)."""
    rects = list(rectangulos(p))
    for q in quitar:
        rects = [x for r in rects for x in restar_rectangulo(r, q, tol)]
    return rects


def subrecintos(nivel: dict) -> list[tuple[dict, dict]]:
    """[(subrecinto, recinto que lo contiene)] del nivel: baños y cabinas dentro de un recinto (revisión adversarial).
    Su área cuenta en el recinto del programa; tienen polígono, polígono libre y puertas propios."""
    return [(sb, r) for r in nivel.get('recintos', []) if isinstance(r, dict)
            for sb in r.get('subrecintos') or [] if isinstance(sb, dict)]


# Muesca del polígono libre que no cuenta como angostamiento (cambio de espesor de muro entre recintos vecinos).
MUESCA_IGNORADA_M = 0.10


def ancho_minimo(p, ignorar_m: float = 0.0) -> float:
    """Ancho mínimo de un polígono ortogonal: el menor, sobre todos sus puntos, de las cuerdas horizontal y vertical que
    pasan por el punto. En un rectángulo es su lado menor; en una L, el ancho de su brazo más angosto.
    ignorar_m > 0 descarta las franjas más delgadas que eso (las muescas de un polígono libre donde cambia el espesor
    del muro: no angostan el paso)."""
    xs, ys = _rejilla_comun([p])
    nx, ny = len(xs) - 1, len(ys) - 1
    lleno = [[punto_en_poligono(((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2), p, 0.0) for i in range(nx)]
             for j in range(ny)]
    horiz = [[0.0] * nx for _ in range(ny)]
    vert = [[0.0] * nx for _ in range(ny)]
    for j in range(ny):
        i = 0
        while i < nx:
            if not lleno[j][i]:
                i += 1
                continue
            k = i
            while k < nx and lleno[j][k]:
                k += 1
            for m in range(i, k):
                horiz[j][m] = xs[k] - xs[i]
            i = k
    for i in range(nx):
        j = 0
        while j < ny:
            if not lleno[j][i]:
                j += 1
                continue
            k = j
            while k < ny and lleno[k][i]:
                k += 1
            for m in range(j, k):
                vert[m][i] = ys[k] - ys[j]
            j = k
    valores = [min(horiz[j][i], vert[j][i]) for j in range(ny) for i in range(nx) if lleno[j][i]
               and (ignorar_m <= 0 or (xs[i + 1] - xs[i] >= ignorar_m and ys[j + 1] - ys[j] >= ignorar_m))]
    return min(valores) if valores else 0.0


def lado_menor_rect(p) -> float:
    x0, y0, x1, y1 = caja(p)
    return min(x1 - x0, y1 - y0)


def es_horizontal(a, b, tol: float = EPS) -> bool:
    return abs(a[1] - b[1]) <= tol


def es_vertical(a, b, tol: float = EPS) -> bool:
    return abs(a[0] - b[0]) <= tol


def solape_colineal(a, b, c, d, tol: float = EPS):
    """Si los segmentos ortogonales ab y cd son colineales y se solapan en un tramo de largo > tol, devuelve ese tramo
    ((x0, y0), (x1, y1)) ordenado; si no, None."""
    if es_horizontal(a, b, tol) and es_horizontal(c, d, tol) and abs(a[1] - c[1]) <= tol:
        lo = max(min(a[0], b[0]), min(c[0], d[0]))
        hi = min(max(a[0], b[0]), max(c[0], d[0]))
        if hi - lo > tol:
            return (lo, a[1]), (hi, a[1])
    if es_vertical(a, b, tol) and es_vertical(c, d, tol) and abs(a[0] - c[0]) <= tol:
        lo = max(min(a[1], b[1]), min(c[1], d[1]))
        hi = min(max(a[1], b[1]), max(c[1], d[1]))
        if hi - lo > tol:
            return (a[0], lo), (a[0], hi)
    return None


def bordes_comunes(p, q, tol: float = EPS) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Tramos de borde que comparten dos polígonos ortogonales (largo > tol)."""
    salida = []
    for a, b in bordes(p):
        for c, d in bordes(q):
            s = solape_colineal(a, b, c, d, tol)
            if s:
                salida.append(s)
    return salida


def largo_cubierto(a, b, segmentos, tol: float = EPS) -> float:
    """Largo del segmento ab cubierto por la unión de `segmentos` colineales con él."""
    eje = 0 if es_horizontal(a, b, tol) else 1
    lo, hi = sorted((a[eje], b[eje]))
    tramos = []
    for c, d in segmentos:
        s = solape_colineal(a, b, c, d, tol)
        if s:
            tramos.append(sorted((s[0][eje], s[1][eje])))
    tramos.sort()
    total, fin = 0.0, lo
    for t0, t1 in tramos:
        t0, t1 = max(t0, fin), min(t1, hi)
        if t1 > t0:
            total += t1 - t0
            fin = t1
    return total


def segmento_en_borde(a, b, p, tol: float = EPS) -> bool:
    """True si el segmento ab queda entero sobre el borde del polígono ortogonal p."""
    return largo_cubierto(a, b, bordes(p), tol) >= math.dist(a[:2], b[:2]) - tol


def partir_bordes(p, cortes, tol: float = EPS) -> list[list[float]]:
    """Inserta en los bordes de p los puntos de `cortes` que caen dentro de un borde (sin repetir vértices)."""
    salida = []
    for a, b in bordes(p):
        salida.append([a[0], a[1]])
        L = math.dist(a[:2], b[:2])
        if L <= tol:
            continue
        intermedios = []
        for c in cortes:
            if distancia_punto_segmento(c, a, b) <= tol:
                t = math.dist(a[:2], c[:2]) / L
                if tol / L < t < 1 - tol / L:
                    intermedios.append((t, [c[0], c[1]]))
        for _, c in sorted(intermedios):
            if math.dist(salida[-1], c) > tol:
                salida.append(c)
    return salida


def desplazar_adentro(p, distancias) -> list[list[float]]:
    """Desplaza hacia adentro cada borde de un polígono ortogonal antihorario la distancia indicada para ese borde
    (`distancias[i]` es la del borde p[i] → p[i+1]). Dos bordes colineales seguidos con distancias distintas dejan un
    escalón. Es el polígono libre del 3.3: cada borde a ejes se corre la mitad del espesor del muro que lo ocupa."""
    n = len(p)
    if area_con_signo(p) < 0:
        raise ValueError('desplazar_adentro espera un polígono antihorario')
    if len(distancias) != n:
        raise ValueError('hace falta una distancia por borde')
    dirs, normales = [], []
    for a, b in bordes(p):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        dirs.append((ux, uy))
        normales.append((-uy, ux))
    salida = []
    for i in range(n):
        j = (i + 1) % n
        v = p[j]
        di, dj = distancias[i], distancias[j]
        ni, nj = normales[i], normales[j]
        colineales = abs(dirs[i][0] * dirs[j][1] - dirs[i][1] * dirs[j][0]) < 1e-9
        if colineales:
            salida.append([v[0] + di * ni[0], v[1] + di * ni[1]])
            if abs(di - dj) > EPS:
                salida.append([v[0] + dj * nj[0], v[1] + dj * nj[1]])
        else:
            salida.append([v[0] + di * ni[0] + dj * nj[0], v[1] + di * ni[1] + dj * nj[1]])
    # el vértice de salida i corresponde a p[i+1]: se rota para que empiece en el que corresponde a p[0]
    salida = salida[-1:] + salida[:-1] if salida else salida
    return limpiar_poligono(salida)


def rect_girado(cx: float, cy: float, ancho: float, fondo: float, rot: float) -> list[list[float]]:
    """Huella de un objeto: centro, ancho (x local), fondo (y local) y giro antihorario (rad) → 4 esquinas antihorarias."""
    c, s = math.cos(rot), math.sin(rot)
    pts = []
    for lx, ly in ((-ancho / 2, -fondo / 2), (ancho / 2, -fondo / 2), (ancho / 2, fondo / 2), (-ancho / 2, fondo / 2)):
        pts.append([cx + lx * c - ly * s, cy + lx * s + ly * c])
    return pts


def a_local(pt, cx: float, cy: float, rot: float) -> tuple[float, float]:
    """Punto de planta → ejes locales de un objeto (x local = ancho, y local = fondo)."""
    dx, dy = pt[0] - cx, pt[1] - cy
    c, s = math.cos(rot), math.sin(rot)
    return dx * c + dy * s, -dx * s + dy * c


def convexos_se_traslapan(a, b, tol: float = 1e-3) -> bool:
    """Separación por ejes (dos polígonos convexos): True si se penetran más de `tol` en todas las direcciones."""
    for poly in (a, b):
        for p0, p1 in bordes(poly):
            nx, ny = -(p1[1] - p0[1]), p1[0] - p0[0]
            L = math.hypot(nx, ny)
            if L == 0:
                continue
            nx, ny = nx / L, ny / L
            pa = [v[0] * nx + v[1] * ny for v in a]
            pb = [v[0] * nx + v[1] * ny for v in b]
            if min(max(pa), max(pb)) - max(min(pa), min(pb)) <= tol:
                return False
    return True


def sector(centro, radio: float, ang0: float, ang1: float, paso: float = 0.05) -> list[tuple[float, float]]:
    """Puntos de muestra de un sector circular (barrido de una hoja de puerta), sin el centro: anillos cada `paso`."""
    pts = []
    r = paso
    while r <= radio + EPS:
        n = max(2, int(math.ceil(abs(ang1 - ang0) * r / paso)) + 1)
        for k in range(n):
            t = ang0 + (ang1 - ang0) * k / (n - 1)
            pts.append((centro[0] + r * math.cos(t), centro[1] + r * math.sin(t)))
        r += paso
    return pts


def en_sector(pt, centro, radio: float, ang0: float, ang1: float, tol: float = 1e-3) -> bool:
    """True si el punto está estrictamente dentro del sector (con margen `tol`)."""
    dx, dy = pt[0] - centro[0], pt[1] - centro[1]
    r = math.hypot(dx, dy)
    if r <= tol or r >= radio - tol:
        return False
    lo, hi = min(ang0, ang1), max(ang0, ang1)
    t = math.atan2(dy, dx)
    for k in (-2, -1, 0, 1, 2):
        tt = t + 2 * math.pi * k
        if lo + tol / max(r, tol) < tt < hi - tol / max(r, tol):
            return True
    return False


# --------------------------------------------------------------------------------------------------------------------
# Rejilla de 0,10 m con distancias (V10, V14, I6)
# --------------------------------------------------------------------------------------------------------------------
class Rejilla:
    """Rejilla regular sobre una caja de la planta. `libre[i]` = 1 si la celda es transitable. Las celdas se marcan por
    su centro. Distancias con pesos (1 en ortogonal, √2 en diagonal; sin cortar esquinas bloqueadas)."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float, celda: float = 0.10):
        self.x0, self.y0, self.celda = x0, y0, celda
        self.nx = max(1, int(math.ceil((x1 - x0) / celda - 1e-9)))
        self.ny = max(1, int(math.ceil((y1 - y0) / celda - 1e-9)))
        self.libre = bytearray(self.nx * self.ny)

    def centro(self, i: int, j: int) -> tuple[float, float]:
        return self.x0 + (i + 0.5) * self.celda, self.y0 + (j + 0.5) * self.celda

    def celda_de(self, x: float, y: float) -> tuple[int, int] | None:
        i = int(math.floor((x - self.x0) / self.celda))
        j = int(math.floor((y - self.y0) / self.celda))
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return i, j
        return None

    def _rango(self, a: float, b: float, origen: float, n: int) -> range:
        lo = int(math.ceil((min(a, b) - origen) / self.celda - 0.5 - 1e-9))
        hi = int(math.floor((max(a, b) - origen) / self.celda - 0.5 + 1e-9))
        return range(max(0, lo), min(n - 1, hi) + 1)

    def pintar_rect(self, x0: float, y0: float, x1: float, y1: float, valor: int = 1) -> None:
        for j in self._rango(y0, y1, self.y0, self.ny):
            base = j * self.nx
            for i in self._rango(x0, x1, self.x0, self.nx):
                self.libre[base + i] = valor

    def pintar_poligono(self, p, valor: int = 1) -> None:
        if es_ortogonal(p):
            for r in rectangulos(p):
                self.pintar_rect(*r, valor=valor)
            return
        x0, y0, x1, y1 = caja(p)
        for j in self._rango(y0, y1, self.y0, self.ny):
            for i in self._rango(x0, x1, self.x0, self.nx):
                if punto_en_poligono(self.centro(i, j), p, 0.0):
                    self.libre[j * self.nx + i] = valor

    def es_libre(self, i: int, j: int) -> bool:
        return 0 <= i < self.nx and 0 <= j < self.ny and self.libre[j * self.nx + i] == 1

    def distancias(self, semillas, transitable=None) -> list[float]:
        """Distancia en metros desde el conjunto de celdas semilla a cada celda (inf si no se alcanza).
        `transitable`: bytearray opcional (por defecto, self.libre)."""
        t = self.libre if transitable is None else transitable
        nx, ny, c = self.nx, self.ny, self.celda
        dist = [math.inf] * (nx * ny)
        cola = []
        for i, j in semillas:
            if 0 <= i < nx and 0 <= j < ny and t[j * nx + i]:
                dist[j * nx + i] = 0.0
                cola.append((0.0, i, j))
        heapq.heapify(cola)
        d2 = c * math.sqrt(2)
        vecinos = ((1, 0, c), (-1, 0, c), (0, 1, c), (0, -1, c), (1, 1, d2), (1, -1, d2), (-1, 1, d2), (-1, -1, d2))
        while cola:
            d, i, j = heapq.heappop(cola)
            if d > dist[j * nx + i]:
                continue
            for di, dj, w in vecinos:
                a, b = i + di, j + dj
                if not (0 <= a < nx and 0 <= b < ny) or not t[b * nx + a]:
                    continue
                if di and dj and not (t[j * nx + a] and t[b * nx + i]):
                    continue
                nd = d + w
                if nd < dist[b * nx + a]:
                    dist[b * nx + a] = nd
                    heapq.heappush(cola, (nd, a, b))
        return dist

    def holgura(self) -> list[float]:
        """Distancia de cada celda libre al centro de la celda bloqueada más cercana (las de afuera de la caja cuentan
        como bloqueadas)."""
        nx, ny = self.nx, self.ny
        todas = bytearray(b'\x01' * (nx * ny))
        semillas = [(i, j) for j in range(ny) for i in range(nx) if not self.libre[j * nx + i]]
        # borde exterior de la caja: celdas libres del perímetro quedan a media celda del afuera
        dist = self.distancias(semillas, todas) if semillas else [math.inf] * (nx * ny)
        for j in range(ny):
            for i in range(nx):
                borde = min(i + 1, nx - i, j + 1, ny - j) * self.celda
                if borde < dist[j * nx + i]:
                    dist[j * nx + i] = borde
        return dist


# --------------------------------------------------------------------------------------------------------------------
# Programa: referencias a ambientes (regla común del 3.4)
# --------------------------------------------------------------------------------------------------------------------
class ErrorAmbiente(ValueError):
    pass


def resolver_ambiente(ref, ambientes) -> int:
    """Devuelve la fila de `ambientes` (lista de programa.json → ambientes, o una lista equivalente de fixture) a la que
    apunta `ref`: un entero (fila), {"fila": n[, "nombre": …]}, {"servicio_programa": …, "nombre": …} o un nombre suelto.
    Falla si el nombre no existe, si corresponde a más de una fila sin desambiguar, o si la fila y el nombre no coinciden."""
    if isinstance(ref, bool):
        raise ErrorAmbiente(f'referencia de ambiente no válida: {ref!r}')
    if isinstance(ref, int):
        if not 0 <= ref < len(ambientes):
            raise ErrorAmbiente(f'la fila {ref} no existe (hay {len(ambientes)})')
        return ref
    if isinstance(ref, str):
        ref = {'nombre': ref}
    if not isinstance(ref, dict):
        raise ErrorAmbiente(f'referencia de ambiente no válida: {ref!r}')
    if 'fila' in ref:
        f = resolver_ambiente(ref['fila'], ambientes)
        if 'nombre' in ref and ambientes[f].get('nombre') != ref['nombre']:
            raise ErrorAmbiente(f'la fila {f} es «{ambientes[f].get("nombre")}», no «{ref["nombre"]}»')
        if 'servicio_programa' in ref and ambientes[f].get('servicio') != ref['servicio_programa']:
            raise ErrorAmbiente(f'la fila {f} es del servicio «{ambientes[f].get("servicio")}», no «{ref["servicio_programa"]}»')
        return f
    nombre = ref.get('nombre')
    if not nombre:
        raise ErrorAmbiente(f'la referencia no trae fila ni nombre: {ref!r}')
    filas = [i for i, a in enumerate(ambientes) if a.get('nombre') == nombre]
    if 'servicio_programa' in ref:
        filas = [i for i in filas if ambientes[i].get('servicio') == ref['servicio_programa']]
    if 'piso' in ref:
        filas = [i for i in filas if ambientes[i].get('piso') == ref['piso']]
    if not filas:
        raise ErrorAmbiente(f'no hay ninguna fila «{nombre}»' + (f' en «{ref["servicio_programa"]}»' if 'servicio_programa' in ref else ''))
    if len(filas) > 1:
        raise ErrorAmbiente(f'«{nombre}» corresponde a {len(filas)} filas ({", ".join(map(str, filas))}): '
                            'hay que citar la fila o el par {servicio_programa, nombre}')
    return filas[0]


def nombres_repetidos(ambientes) -> dict[str, list[int]]:
    """{nombre: [filas]} de los nombres que aparecen en más de una fila del programa."""
    por = {}
    for i, a in enumerate(ambientes):
        por.setdefault(a.get('nombre'), []).append(i)
    return {k: v for k, v in por.items() if len(v) > 1}


# --------------------------------------------------------------------------------------------------------------------
# Informe de los validadores
# --------------------------------------------------------------------------------------------------------------------
class Informe:
    """Informe JSON por reglas: cada regla tiene tipo (duro o aviso), estado (ok, error, aviso u omitida), lo revisado
    y los mensajes. `salir()` imprime el JSON en la salida estándar, un resumen de una línea en la de errores y sale
    con 1 si hubo errores duros."""

    MAX_MENSAJES = 300

    def __init__(self, herramienta: str, reglas: dict[str, tuple[str, str]], **cabecera):
        self.herramienta = herramienta
        self.cabecera = cabecera
        self.reglas = {k: {'regla': k, 'descripcion': d, 'tipo': t, 'estado': 'ok', 'revisados': 0,
                           'errores': [], 'avisos': []} for k, (d, t) in reglas.items()}

    def _r(self, regla):
        if regla not in self.reglas:
            self.reglas[regla] = {'regla': regla, 'descripcion': '', 'tipo': 'duro', 'estado': 'ok', 'revisados': 0,
                                  'errores': [], 'avisos': []}
        return self.reglas[regla]

    def error(self, regla: str, mensaje: str) -> None:
        self._r(regla)['errores'].append(mensaje)

    def aviso(self, regla: str, mensaje: str) -> None:
        self._r(regla)['avisos'].append(mensaje)

    def revisado(self, regla: str, n: int = 1) -> None:
        self._r(regla)['revisados'] += n

    def omitir(self, regla: str, motivo: str) -> None:
        r = self._r(regla)
        r['estado'] = 'omitida'
        r['motivo'] = motivo

    def omitir_resto(self, motivo: str) -> None:
        """Marca como omitidas las reglas que no alcanzaron a correr (por ejemplo, si no se pudo leer el archivo)."""
        for k, r in self.reglas.items():
            if not r['errores'] and not r['avisos'] and not r['revisados'] and r['estado'] != 'omitida':
                self.omitir(k, motivo)

    def errores_duros(self) -> int:
        return sum(len(r['errores']) for r in self.reglas.values() if r['estado'] != 'omitida')

    def como_dict(self) -> dict:
        reglas = []
        for r in self.reglas.values():
            r = dict(r)
            if r['estado'] != 'omitida':
                r['estado'] = 'error' if r['errores'] else ('aviso' if r['avisos'] else 'ok')
            for campo in ('errores', 'avisos'):
                if len(r[campo]) > self.MAX_MENSAJES:
                    resto = len(r[campo]) - self.MAX_MENSAJES
                    r[campo] = r[campo][:self.MAX_MENSAJES] + [f'… y {resto} más']
            reglas.append(r)
        n_err = self.errores_duros()
        n_av = sum(len(r['avisos']) for r in self.reglas.values() if r['estado'] != 'omitida')
        return {'herramienta': self.herramienta, **self.cabecera,
                'resultado': 'errores' if n_err else 'sin errores duros', 'errores_duros': n_err, 'avisos': n_av,
                'reglas': reglas}

    def salir(self) -> None:
        d = self.como_dict()
        sys.stdout.write(texto_json(d))
        estados = ' '.join(f'{r["regla"]}:{r["estado"]}' for r in d['reglas'])
        sys.stderr.write(f'{self.herramienta}: {d["errores_duros"]} errores duros, {d["avisos"]} avisos · {estados}\n')
        sys.exit(1 if d['errores_duros'] else 0)


# --------------------------------------------------------------------------------------------------------------------
# Puertas: hojas y barrido (V12 de la planta, I5 del inventario)
# --------------------------------------------------------------------------------------------------------------------
def normal_unitaria_izquierda(a, b) -> tuple[float, float]:
    """Normal unitaria a la izquierda del segmento a → b (lado «izquierdo» de los muros, 3.3)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return -dy / L, dx / L


def normal_hacia(a, b, punto, poligono, paso: float = 0.05) -> tuple[float, float] | None:
    """Normal unitaria del muro a-b que, desde `punto` (sobre el muro), entra en `poligono`; None si ninguna entra."""
    nx, ny = normal_unitaria_izquierda(a, b)
    if punto_en_poligono((punto[0] + paso * nx, punto[1] + paso * ny), poligono, 0.0):
        return nx, ny
    if punto_en_poligono((punto[0] - paso * nx, punto[1] - paso * ny), poligono, 0.0):
        return -nx, -ny
    return None


def hojas_puerta(puerta, muro, poligonos) -> list[dict]:
    """Hojas batientes de una puerta y el sector que barre cada una.
    Convención: mirando desde `desde` hacia `hacia`, «bisagra: izquierda» pone la bisagra de una hoja a la izquierda
    (es el valor por defecto). `abre`: adentro (barre el lado `hacia`), afuera (el lado `desde`), doble (los dos: vaivén),
    corrediza (no barre). Con 2 hojas, una bisagra en cada extremo. `poligonos`: {id de recinto: polígono a ejes}.
    Devuelve [{lado, bisagra: (x, y), radio, ang0, ang1}] con ang0 < ang1 en radianes (sector antihorario)."""
    abre = puerta.get('abre')
    if abre == 'corrediza' or puerta.get('tipo') == 'corrediza':
        return []
    a, b, c = muro['a'], muro['b'], puerta['centro']
    desde, hacia = puerta.get('desde'), puerta.get('hacia')
    n_h = None
    if hacia in poligonos:
        n_h = normal_hacia(a, b, c, poligonos[hacia])
    if n_h is None and desde in poligonos:
        n_d = normal_hacia(a, b, c, poligonos[desde])
        n_h = None if n_d is None else (-n_d[0], -n_d[1])
    if n_h is None:
        return []
    lados = {'adentro': [(hacia, n_h)], 'afuera': [(desde, (-n_h[0], -n_h[1]))],
             'doble': [(hacia, n_h), (desde, (-n_h[0], -n_h[1]))]}.get(abre, [])
    izq = (-n_h[1], n_h[0])
    ancho, hojas = float(puerta['ancho']), max(1, int(puerta.get('hojas', 1)))
    if hojas == 1:
        s = -1.0 if puerta.get('bisagra') == 'derecha' else 1.0
        bisagras = [((c[0] + s * izq[0] * ancho / 2, c[1] + s * izq[1] * ancho / 2), (-s * izq[0], -s * izq[1]), ancho)]
    else:
        w = ancho / 2
        bisagras = [((c[0] + izq[0] * w, c[1] + izq[1] * w), (-izq[0], -izq[1]), w),
                    ((c[0] - izq[0] * w, c[1] - izq[1] * w), (izq[0], izq[1]), w)]
    salida = []
    for lado, n in lados:
        for h, cerrada, radio in bisagras:
            t0 = math.atan2(cerrada[1], cerrada[0])
            giro = cerrada[0] * n[1] - cerrada[1] * n[0]
            ang0, ang1 = (t0, t0 + math.pi / 2) if giro > 0 else (t0 - math.pi / 2, t0)
            salida.append({'lado': lado, 'bisagra': h, 'radio': radio, 'ang0': ang0, 'ang1': ang1})
    return salida


def vano_puerta(puerta, muro, extra: float = 0.06) -> list[float]:
    """Rectángulo [x0, y0, x1, y1] del vano de una puerta en un muro ortogonal: el ancho de la puerta a lo largo del muro
    y el espesor del muro más `extra` a cada lado a través de él."""
    c, w = puerta['centro'], float(puerta['ancho']) / 2
    e = float(muro.get('espesor', 0.2)) / 2 + extra
    if es_horizontal(muro['a'], muro['b']):
        return [c[0] - w, c[1] - e, c[0] + w, c[1] + e]
    return [c[0] - e, c[1] - w, c[0] + e, c[1] + w]


# --------------------------------------------------------------------------------------------------------------------
# Paso físico (V22 de la planta, I17 del inventario): ¿se puede caminar, con el cuerpo, de las entradas a cada recinto?
# --------------------------------------------------------------------------------------------------------------------
RADIO_CAMINANTE_M = 0.30          # radio del caminante del recorrido (6.4)
RADIO_CAMILLA_M = 0.45            # medio ancho de una camilla con quien la empuja (0,90 m de paso libre; estimación)


def rejilla_de_paso(nivel: dict, obstaculos=(), celda: float = 0.05):
    """Rejilla del nivel con lo que se pisa: el polígono libre de cada espacio transitable (descontadas las columnas), los
    vanos de las puertas y, como obstáculos, las columnas, los obstáculos del recorrido, los ojos de las escaleras y los
    rectángulos `obstaculos` [x0, y0, x1, y1] (huellas de piso del inventario). Los subrecintos (baños y cabinas) se pisan
    como los recintos."""
    recs = [r for r in nivel.get('recintos', []) if isinstance(r, dict) and r.get('poligono')]
    cont = nivel.get('contorno') or [v for r in recs for v in r['poligono']]
    xs = [v[0] for v in cont]
    ys = [v[1] for v in cont]
    rej = Rejilla(min(xs) - 1.0, min(ys) - 1.0, max(xs) + 1.0, max(ys) + 1.0, celda)
    for r in recs:
        if r.get('transitable') is False:
            continue
        rej.pintar_poligono(orientar_antihorario(r.get('poligono_libre') or r['poligono']))
    for sb, r in subrecintos(nivel):
        if r.get('transitable') is not False and sb.get('poligono_libre'):
            rej.pintar_poligono(orientar_antihorario(sb['poligono_libre']))
    muros = {m.get('id'): m for m in nivel.get('muros', [])}
    for p in nivel.get('puertas', []):
        m = muros.get(p.get('muro'))
        if m is not None:
            rej.pintar_rect(*vano_puerta(p, m, extra=0.0))
    for c in nivel.get('columnas', []):
        b, h = float(c.get('b', 0.6)) / 2, float(c.get('h', 0.6)) / 2
        rej.pintar_rect(c['x'] - b, c['y'] - h, c['x'] + b, c['y'] + h, valor=0)
    for o in nivel.get('obstaculos_recorrido', []):
        rej.pintar_poligono(orientar_antihorario(o['poligono']), valor=0)
    for e in nivel.get('escaleras', []):
        if isinstance(e.get('ojo'), list):
            rej.pintar_rect(*e['ojo'], valor=0)
    for o in obstaculos:
        rej.pintar_rect(*o, valor=0)
    return rej


def erosionar(rej: 'Rejilla', radio: float) -> bytearray:
    """Celdas donde cabe el centro de un círculo de `radio` sin tocar ninguna celda bloqueada (distancia del centro de la
    celda a la caja de la celda bloqueada; lo de afuera de la rejilla cuenta como bloqueado)."""
    nx, ny, c = rej.nx, rej.ny, rej.celda
    libre = rej.libre
    k = int(math.ceil(radio / c + 0.5))
    spans = []
    for dj in range(-k, k + 1):
        dy = max(0.0, abs(dj) * c - c / 2)
        if dy >= radio:
            continue
        # |di| máximo con max(0, |di|·c − c/2)² + dy² < radio²
        w = 0
        while True:
            dx = max(0.0, (w + 1) * c - c / 2)
            if dx * dx + dy * dy < radio * radio - 1e-12:
                w += 1
            else:
                break
        spans.append((dj, w))
    pasa = bytearray(libre)
    for j in range(ny):
        base = j * nx
        for i in range(nx):
            if libre[base + i]:
                continue
            # solo las celdas bloqueadas que tocan una libre (las demás no cambian nada)
            if not ((i > 0 and libre[base + i - 1]) or (i < nx - 1 and libre[base + i + 1]) or
                    (j > 0 and libre[base - nx + i]) or (j < ny - 1 and libre[base + nx + i])):
                continue
            for dj, w in spans:
                jj = j + dj
                if 0 <= jj < ny:
                    a, b = max(0, i - w), min(nx, i + w + 1)
                    pasa[jj * nx + a: jj * nx + b] = bytes(b - a)
    # el borde de la rejilla también es pared
    for j in range(ny):
        for i in list(range(min(k, nx))) + list(range(max(0, nx - k), nx)):
            pasa[j * nx + i] = 0
    for j in list(range(min(k, ny))) + list(range(max(0, ny - k), ny)):
        pasa[j * nx: (j + 1) * nx] = bytes(nx)
    return pasa


def alcance_fisico(nivel: dict, radio: float, semillas, obstaculos=(), celda: float = 0.05, recintos=None) -> dict:
    """Componentes por las que se camina con un cuerpo de `radio` desde `semillas` [(nombre, (x, y))]. Devuelve
    {componentes: [[nombres]], sin_lugar: [nombres de semillas sin celda libre a 0,6 m], no_alcanzables: [ids de
    recinto o de subrecinto sin ninguna celda alcanzable], celdas_alcanzables: n}. `recintos`: ids a revisar (por
    defecto, todos los transitables y sus subrecintos)."""
    rej = rejilla_de_paso(nivel, obstaculos, celda)
    pasa = erosionar(rej, radio)
    nx, ny = rej.nx, rej.ny
    comp = [0] * (nx * ny)
    etiquetas = {}
    sin_lugar = []
    actual = 0
    alcance_r = int(round(0.6 / celda))
    pols = {r['id']: orientar_antihorario(r.get('poligono_libre') or r['poligono']) for r in nivel.get('recintos', [])
            if r.get('id') and r.get('poligono')}
    grupo_de = {}
    for sem in semillas:
        nombre, pt = sem[0], sem[1]
        rid = sem[2] if len(sem) > 2 else None
        pol = pols.get(rid)
        ij = rej.celda_de(pt[0], pt[1])
        mejor = None
        if ij is not None:
            for dj in range(-alcance_r, alcance_r + 1):
                for di in range(-alcance_r, alcance_r + 1):
                    a, b = ij[0] + di, ij[1] + dj
                    if 0 <= a < nx and 0 <= b < ny and pasa[b * nx + a]:
                        d = di * di + dj * dj
                        if (mejor is None or d < mejor[0]) and (pol is None or punto_en_poligono(rej.centro(a, b), pol, 0.0)):
                            mejor = (d, a, b)
        if mejor is None:
            sin_lugar.append(nombre)
            continue
        k0 = mejor[2] * nx + mejor[1]
        if not comp[k0]:
            actual += 1
            comp[k0] = actual
            pila = [k0]
            while pila:
                k = pila.pop()
                i, j = k % nx, k // nx
                for kk in ((k - 1) if i > 0 else -1, (k + 1) if i < nx - 1 else -1,
                           (k - nx) if j > 0 else -1, (k + nx) if j < ny - 1 else -1):
                    if kk >= 0 and pasa[kk] and not comp[kk]:
                        comp[kk] = actual
                        pila.append(kk)
        etiquetas.setdefault(comp[k0], []).append(nombre)
        grupo_de[nombre] = sem[3] if len(sem) > 3 else 0.0
    alcanzadas = set(etiquetas)
    # una componente por cota de piso: la terraza del piso 3 (z −4,2 en la cubierta) es otro piso aunque esté en el nivel
    por_cota = {}
    for et, noms in etiquetas.items():
        for z in sorted({grupo_de[n] for n in noms}):
            por_cota.setdefault(z, []).append(noms)
    no_alcanzables = []
    revisar = [r for r in nivel.get('recintos', []) if isinstance(r, dict)]
    revisar += [dict(sb, transitable=r.get('transitable')) for sb, r in subrecintos(nivel)]
    for r in revisar:
        if r.get('transitable') is False or not r.get('poligono'):
            continue
        if recintos is not None and r.get('id') not in recintos:
            continue
        pol = orientar_antihorario(r.get('poligono_libre') or r['poligono'])
        x0, y0, x1, y1 = caja(pol)
        ok = False
        rects = rectangulos(pol) if es_ortogonal(pol) else [(x0, y0, x1, y1)]
        for q in rects:
            for j in rej._rango(q[1], q[3], rej.y0, ny):
                base = j * nx
                for i in rej._rango(q[0], q[2], rej.x0, nx):
                    if comp[base + i] in alcanzadas:
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
        if not ok:
            no_alcanzables.append(r.get('id'))
    return {'componentes': list(etiquetas.values()), 'por_cota': por_cota, 'sin_lugar': sin_lugar, 'no_alcanzables': no_alcanzables,
            'celdas_alcanzables': sum(1 for v in comp if v in alcanzadas)}


def semillas_de_paso(nivel: dict) -> list:
    """Entradas del recorrido, conexiones verticales del nivel y pasos a otros niveles: [(nombre, (x, y), recinto, cota)].
    El recinto es donde se busca la celda libre más cercana (el de la puerta en los pasos, que caen sobre el muro); la cota
    es z_piso_m de ese recinto (0 si no la trae)."""
    recs = [r for r in nivel.get('recintos', []) if r.get('poligono')]
    por_id = {r['id']: r for r in recs}

    def donde(pt):
        for r in recs:
            if r.get('transitable') is not False and punto_en_poligono(pt, orientar_antihorario(r['poligono']), 0.0):
                return r['id']
        return None

    def cota(rid):
        return float((por_id.get(rid) or {}).get('z_piso_m') or 0.0)
    out = []
    for e in nivel.get('entradas_recorrido', []):
        if e.get('punto'):
            rid = donde(e['punto'])
            out.append((f'entrada {e.get("id")}', e['punto'], rid, cota(rid)))
    clave = 'cubierta' if nivel.get('id') == 'CUB' else str(nivel.get('piso'))
    for cv in nivel.get('conexiones_verticales', []):
        p = (cv.get('puntos') or {}).get(clave)
        if p and cv.get('tipo') != 'montacargas':
            rid = donde(p)
            out.append((f'{cv.get("tipo")} {cv.get("id")}', p, rid, cota(rid)))
    for p in nivel.get('pasos_entre_niveles', []):
        rid = p.get('recinto')
        out.append((f'paso a {p.get("otro_nivel")} ({p.get("puerta") or p.get("puerta_del_otro_nivel")})', p['punto'], rid, cota(rid)))
    return out



def _cuerda(p, eje: int, t: float) -> list[tuple[float, float]]:
    """Intervalos del polígono ortogonal p sobre la recta perpendicular al eje `eje` (0: recta x = t; 1: recta y = t)."""
    # muestreo por celdas finas de 1 cm: robusto con polígonos ortogonales cualesquiera
    x0, y0, x1, y1 = caja(p)
    paso = 0.01
    if eje == 0:
        lo, hi, fijo = y0, y1, t
    else:
        lo, hi, fijo = x0, x1, t
    n = int(math.ceil((hi - lo) / paso))
    tramos, ini = [], None
    for k in range(n + 1):
        u = lo + (k + 0.5) * paso
        pt = (fijo, u) if eje == 0 else (u, fijo)
        d = u <= hi and punto_en_poligono(pt, p, 0.0)
        if d and ini is None:
            ini = u - paso / 2
        if not d and ini is not None:
            tramos.append((ini, u - paso / 2))
            ini = None
    if ini is not None:
        tramos.append((ini, hi))
    return tramos


def ancho_en_columnas(p, columnas) -> tuple[float, tuple | None]:
    """Ancho libre de un corredor (polígono libre p) en la sección de cada columna que lo invade: la cuerda transversal
    (perpendicular al eje largo del corredor) por la columna, menos la columna. Así mide la revisión: «en la sección de
    cada columna». Devuelve (ancho mínimo, columna) o (inf, None) si ninguna columna lo toca."""
    p = orientar_antihorario(p)
    x0, y0, x1, y1 = caja(p)
    largo_x = (x1 - x0) >= (y1 - y0)
    mejor, donde = math.inf, None
    for c in columnas:
        if c[2] <= x0 + 1e-6 or c[0] >= x1 - 1e-6 or c[3] <= y0 + 1e-6 or c[1] >= y1 - 1e-6:
            continue
        # muestras a lo largo del eje largo, dentro de la columna
        a0, a1 = (c[0], c[2]) if largo_x else (c[1], c[3])
        b0, b1 = (x0, x1) if largo_x else (y0, y1)
        a0, a1 = max(a0, b0) + 0.03, min(a1, b1) - 0.03
        if a1 < a0:
            continue
        for t in (a0, (a0 + a1) / 2, a1):
            eje = 0 if largo_x else 1         # recta x = t (corredor largo en x) o y = t (largo en y)
            tramos = _cuerda(p, eje, t)
            if not tramos:
                continue
            col = (c[1], c[3]) if eje == 0 else (c[0], c[2])
            libres = []
            for u0, u1 in tramos:
                if col[1] <= u0 or col[0] >= u1:
                    libres.append((u0, u1))
                    continue
                if col[0] > u0:
                    libres.append((u0, col[0]))
                if col[1] < u1:
                    libres.append((col[1], u1))
            # el tramo que toca la columna (el que queda a su lado dentro del corredor)
            junto = [u1 - u0 for u0, u1 in libres if abs(u0 - col[1]) < 1e-6 or abs(u1 - col[0]) < 1e-6]
            if junto:
                w = max(junto)
                if w < mejor:
                    mejor, donde = w, c
    return mejor, donde


def ancho_libre_con_columnas(p, columnas, celda: float = 0.05, ignorar_m: float = 0.10) -> tuple[float, tuple | None]:
    """Ancho libre mínimo de un polígono ortogonal (el libre de un corredor) descontando las columnas que lo invaden
    (rectángulos [x0, y0, x1, y1]): en cada celda libre, la menor de las cuerdas horizontal y vertical por dentro del
    polígono y fuera de las columnas; se ignoran las celdas de las franjas más delgadas que `ignorar_m` (muescas del
    polígono libre). Devuelve (ancho, punto donde se da)."""
    p = orientar_antihorario(p)
    x0, y0, x1, y1 = caja(p)
    nx = max(1, int(math.ceil((x1 - x0) / celda - 1e-9)))
    ny = max(1, int(math.ceil((y1 - y0) / celda - 1e-9)))
    dentro = bytearray(nx * ny)
    for r in rectangulos(p):
        i0 = int(math.ceil((r[0] - x0) / celda - 0.5 - 1e-9)); i1 = int(math.floor((r[2] - x0) / celda - 0.5 + 1e-9))
        j0 = int(math.ceil((r[1] - y0) / celda - 0.5 - 1e-9)); j1 = int(math.floor((r[3] - y0) / celda - 0.5 + 1e-9))
        for j in range(max(0, j0), min(ny - 1, j1) + 1):
            for i in range(max(0, i0), min(nx - 1, i1) + 1):
                dentro[j * nx + i] = 1
    toca = False
    for c in columnas:
        if c[2] <= x0 or c[0] >= x1 or c[3] <= y0 or c[1] >= y1:
            continue
        toca = True
        i0 = int(math.ceil((c[0] - x0) / celda - 0.5 - 1e-9)); i1 = int(math.floor((c[2] - x0) / celda - 0.5 + 1e-9))
        j0 = int(math.ceil((c[1] - y0) / celda - 0.5 - 1e-9)); j1 = int(math.floor((c[3] - y0) / celda - 0.5 + 1e-9))
        for j in range(max(0, j0), min(ny - 1, j1) + 1):
            for i in range(max(0, i0), min(nx - 1, i1) + 1):
                dentro[j * nx + i] = 0
    if not toca:
        return ancho_minimo(p, ignorar_m), None
    h = [0] * (nx * ny)
    v = [0] * (nx * ny)
    for j in range(ny):
        i = 0
        while i < nx:
            if not dentro[j * nx + i]:
                i += 1
                continue
            k = i
            while k < nx and dentro[j * nx + k]:
                k += 1
            for m in range(i, k):
                h[j * nx + m] = k - i
            i = k
    for i in range(nx):
        j = 0
        while j < ny:
            if not dentro[j * nx + i]:
                j += 1
                continue
            k = j
            while k < ny and dentro[k * nx + i]:
                k += 1
            for m in range(j, k):
                v[m * nx + i] = k - j
            j = k
    ig = int(round(ignorar_m / celda))
    mejor, donde = None, None
    for k in range(nx * ny):
        if not dentro[k]:
            continue
        w = min(h[k], v[k])
        if w <= ig:
            continue
        if mejor is None or w < mejor:
            mejor, donde = w, (round(x0 + (k % nx + 0.5) * celda, 2), round(y0 + (k // nx + 0.5) * celda, 2))
    return (mejor * celda if mejor is not None else 0.0), donde
