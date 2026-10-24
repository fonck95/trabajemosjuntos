#!/usr/bin/env python3
"""Prediseño estructural de la torre del hospital (NSR-10, grupo IV, amenaza intermedia, DMO) y modelo del simulador.

Escribe data/sismo/torre_hospital_estructura.json en el formato de data/sismo/ESQUEMA.md (versión 2, cambios E1-E16)
con los pasos del contrato de integración (data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md, 7.2, 13.1 y
17, que prevalece): sistema estructural, cargas del título B, masas por nivel, análisis pseudotridimensional propio
(fuerza horizontal equivalente y modal espectral), irregularidades, R, derivas vectoriales con el sismo de diseño y
con el umbral de daño, diseño de vigas, columnas y muros con capacidad moderada de disipación de energía (DMO),
columna fuerte-viga débil, cortante por capacidad, propiedades de rótula (nominales y esperadas), cimentación
(pilotes, dados, vigas de amarre, contrapiso, foso y cisternas) y el despiece del refuerzo de cada elemento con sus
cantidades comparadas con presupuesto.json.

Uso (Python 3.12, solo biblioteca estándar; determinista: misma salida byte a byte):
    python3 scripts/sismo/estructura_torre.py              # escribe el JSON e imprime el resumen de chequeos
    python3 scripts/sismo/estructura_torre.py --verificar  # regenera en memoria, compara byte a byte con el archivo
                                                           # e imprime los chequeos; sale 1 si difiere o si uno falla
    python3 scripts/sismo/estructura_torre.py --informe    # además imprime el detalle por elemento

Convenciones: kN, m, s, t (= kN·s²/m), rad; esfuerzos en MPa solo en materiales y fórmulas de sección (se dice).
x al este, y al norte, z arriba; mismo marco de programa.json. Los numerales de la NSR-10 que no se pudieron cotejar
con el texto oficial van marcados «por confirmar» (el 24-oct-2026 el proxy de esta sesión rechazó todas las copias
del Título A; ver «verificacion_nsr10» en el JSON).

Estructura del programa (en este orden):
  1. utilidades y álgebra lineal (eliminación de Gauss, Jacobi);
  2. materiales, barras y parámetros normativos (con su fuente);
  3. geometría (ejes, niveles, columnas, vigas, muros, contornos);
  4. cargas del título B y masas por nivel;
  5. secciones: análisis por fibras (bloque de Whitney, Mander, acero bilineal), P-M, momento-curvatura;
  6. modelo pseudotridimensional (Wilson y Dovey): pórticos condensados, diafragmas, modos, espectral, FHE;
  7. procedimiento NSR-10: sistema, Ta, R, irregularidades, derivas, umbral de daño, índice de estabilidad;
  8. diseño de elementos y propiedades de rótula (ASCE/SEI 41-17, Haselton y otros 2016);
  9. mampostería (Tomaževič), cimentación, despiece del refuerzo y cantidades;
 10. armado del JSON y verificación.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / 'data' / 'sismo' / 'torre_hospital_estructura.json'
INSUMOS = {
    'presupuesto': 'data/proyectos/torre_hospital/presupuesto.json',
    'programa': 'data/proyectos/torre_hospital/programa.json',
    'amenaza': 'data/sismo/amenaza.json',
}
FECHA = '2026-10-24'
G = 9.80665                      # m/s² (ESQUEMA.md)


# =================================================================================================================
# 1. Utilidades y álgebra lineal (densa; las matrices son chicas: ≤ 60 grados de libertad por pórtico, 12 globales)
# =================================================================================================================
def r(x, n=4):
    """Redondeo para la salida (cifras decimales fijas; -0.0 → 0.0 para que la salida sea estable)."""
    if x is None:
        return None
    v = round(float(x), n)
    return 0.0 if v == 0 else v


def rs(x, cifras=5):
    """Redondeo a cifras significativas (para propiedades que van de 10⁻⁴ a 10⁵)."""
    if x == 0 or x is None:
        return 0.0 if x == 0 else None
    return float(f'{x:.{cifras}g}')


def ceros(n, m=None):
    return [0.0] * n if m is None else [[0.0] * m for _ in range(n)]


def lu(A):
    """Factorización LU con pivoteo parcial (Doolittle, en sitio sobre una copia). → (LU, piv)."""
    n = len(A)
    a = [fila[:] for fila in A]
    piv = list(range(n))
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(a[i][k]))
        if abs(a[p][k]) < 1e-300:
            raise ValueError('matriz singular')
        if p != k:
            a[k], a[p] = a[p], a[k]
            piv[k], piv[p] = piv[p], piv[k]
        akk = a[k][k]
        fk = a[k]
        for i in range(k + 1, n):
            fi = a[i]
            m = fi[k] / akk
            if m != 0.0:
                fi[k] = m
                for j in range(k + 1, n):
                    fi[j] -= m * fk[j]
            else:
                fi[k] = 0.0
    return a, piv


def lu_resolver(f, b):
    a, piv = f
    n = len(a)
    y = [b[piv[i]] for i in range(n)]
    for i in range(n):
        fi = a[i]
        s = y[i]
        for j in range(i):
            s -= fi[j] * y[j]
        y[i] = s
    for i in range(n - 1, -1, -1):
        fi = a[i]
        s = y[i]
        for j in range(i + 1, n):
            s -= fi[j] * y[j]
        y[i] = s / fi[i]
    return y


def resolver(A, b):
    return lu_resolver(lu(A), b)


def jacobi(A, tol=1e-15, max_barridos=100):
    """Valores y vectores propios de una matriz simétrica (Jacobi cíclico). → (valores, vectores por columna)."""
    n = len(A)
    a = [fila[:] for fila in A]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_barridos):
        fuera = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        diag = sum(a[i][i] ** 2 for i in range(n))
        if fuera <= tol * tol * diag:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


def sha1(ruta):
    return hashlib.sha1((RAIZ / ruta).read_bytes()).hexdigest()


def leer(ruta):
    return json.loads((RAIZ / ruta).read_text(encoding='utf-8'))


def es(x, n=2):
    """Número con coma decimal para los textos (estilo del repositorio)."""
    return f'{x:,.{n}f}'.replace(',', ' ').replace('.', ',').replace(' ', '.')


# =================================================================================================================
# 2. Materiales, barras y parámetros normativos
# =================================================================================================================
FC = 28.0                         # MPa, concreto de 28 MPa (presupuesto.json, capítulo 3)
EC = 24870.0                      # MPa, NSR-10 C.8.5.1: Ec = 4700·√f'c = 24.870 MPa
NU = 0.2                          # Poisson del concreto
GC = EC / (2 * (1 + NU))          # MPa, módulo de cortante isótropo
GAMMA_C = 24.0                    # kN/m³, concreto reforzado (NSR-10 Tabla B.3.2-1, por confirmar)
FY = 420.0                        # MPa, acero NTC 2289 grado 420
FU = 550.0                        # MPa, resistencia mínima a tracción de NTC 2289 (fu ≥ 1,25·fy real; por confirmar)
ES = 200000.0                     # MPa
EPS_Y = FY / ES
BETA1 = 0.85                      # NSR-10 C.10.2.7.3 (f'c ≤ 28 MPa)
# Propiedades esperadas (E16): ASCE/SEI 41-17, Tabla 10-1 (factores de resistencia esperada): concreto 1,50; acero 1,25
F_ESP_C, F_ESP_S = 1.50, 1.25
FCE, FYE = F_ESP_C * FC, F_ESP_S * FY
FY_PR = 1.25 * FY                 # Mpr: 1,25·fy y φ = 1 (NSR-10 C.21.5.4.1 y C.21.6.5.1)
AGREGADO_MM = 19.0                # tamaño máximo nominal supuesto del agregado (3/4"; estimación)

# Barras corrugadas NTC 2289 con designación en octavos de pulgada (NSR-10, Tabla C.3.5.3-2): diámetro (mm),
# área (mm²) y masa (kg/m)
BARRAS = {
    3: (9.5, 71.0, 0.560),
    4: (12.7, 129.0, 0.994),
    5: (15.9, 199.0, 1.552),
    6: (19.1, 284.0, 2.235),
    7: (22.2, 387.0, 3.042),
    8: (25.4, 510.0, 3.973),
}
# Malla electrosoldada (NTC 5806; se diseña con fy = 420 MPa, del lado seguro): diámetro (mm) → (área mm², kg/m)
MALLA = {5.0: (19.6, 0.154), 7.0: (38.5, 0.302)}

# Recubrimientos libres (NSR-10 C.7.7.1, por confirmar): m
REC = {'viga': 0.040, 'columna': 0.040, 'muro': 0.025, 'vigueta': 0.020, 'loseta': 0.020, 'escalera': 0.020,
       'dado_fondo': 0.075, 'dado_lados': 0.075, 'pilote': 0.075, 'viga_amarre': 0.050, 'foso': 0.050}

# Espectro NSR-10 para Yondó (amenaza.json → nsr10; dato oficial, suelo D)
AA, AV, FA, FV, IMP = 0.15, 0.15, 1.5, 2.2, 1.5
AD = 0.04                         # umbral de daño (Apéndice A-4)
H_TOTAL = 17.1                    # m, cubierta del piso 4


def espectro_nsr10(T, I=IMP, Aa=AA, Av=AV, Fa=FA, Fv=FV, rama_corta=False):
    """Sa (g), NSR-10 A.2.6 (ecuaciones A.2.6-1 a A.2.6-9, numeración por confirmar). rama_corta: para T < T0 en el
    análisis dinámico se puede usar Sa = 2,5·Aa·Fa·I·(0,4 + 0,6·T/T0) (A.2.6; aquí no se usa: del lado seguro)."""
    TC = 0.48 * Av * Fv / (Aa * Fa)
    TL = 2.4 * Fv
    T0 = 0.10 * Av * Fv / (Aa * Fa)
    if rama_corta and T < T0:
        return 2.5 * Aa * Fa * I * (0.4 + 0.6 * T / T0)
    if T <= TC:
        return 2.5 * Aa * Fa * I
    if T <= TL:
        return 1.2 * Av * Fv * I / T
    return 1.2 * Av * Fv * TL * I / T ** 2


S_UD = 1.25 * FV                  # coeficiente de sitio del umbral de daño, S = 1,25·Fv (Decreto 92 de 2011, A.12.3)


def espectro_umbral(T, Ad=AD):
    """Sa (g) del umbral de daño, NSR-10 A.12.3 (amortiguamiento del 2 %, sin I): meseta 3·Ad y rama 1,5·Ad·S/T con
    S = 1,25·Fv (por confirmar: es la forma de la NSR-98 que conserva la NSR-10; la meseta corresponde a 2,5·1,2 y la
    rama a 1,2·1,25 del espectro de diseño, el ajuste de 5 % a 2 % de amortiguamiento). TC_ud = 0,5·S."""
    TC = 0.5 * S_UD
    return 3.0 * Ad if T <= TC else 1.5 * Ad * S_UD / T


# Sistema estructural y R0 (NSR-10, tablas A.3-2, A.3-3 y A.3-4, fila DMO; valores por confirmar con el texto)
SISTEMAS = {
    'dual': {'tabla': 'NSR-10 Tabla A.3-4 (sistema dual), 1.c: muros de concreto con capacidad moderada de disipación '
                      'de energía (DMO) con pórticos de concreto DMO', 'R0': 6.0, 'Omega0': 2.5,
             'uso': 'zona de amenaza intermedia: permitido sin límite de altura (por confirmar)'},
    'combinado': {'tabla': 'NSR-10 Tabla A.3-2 (sistema combinado), 2.b: muros de concreto DMO con pórticos de '
                           'concreto DMO', 'R0': 5.0, 'Omega0': 2.5,
                  'uso': 'zona de amenaza intermedia: permitido (altura por confirmar)'},
    'porticos': {'tabla': 'NSR-10 Tabla A.3-3: pórticos de concreto DMO', 'R0': 5.0, 'Omega0': 3.0, 'uso': ''},
}
CT_OTROS, ALFA_OTROS = 0.049, 0.75          # Tabla A.4.2-1, «otros sistemas» (con muros; por confirmar)
CT_PORT, ALFA_PORT = 0.047, 0.90            # Tabla A.4.2-1, pórticos de concreto (no aplica con muros)
CU = max(1.75 - 1.2 * AV * FV, 1.2)         # A.4.2.1
XI = 0.05


# =================================================================================================================
# 3. Geometría (contrato 1.2 y programa.json)
# =================================================================================================================
EJES_X = [('A', -13.0), ('B', -5.8), ('C', 1.4), ('D', 8.6)]
EJES_Y = [('1', -19.6), ('2', -12.4), ('3', -7.6), ('4', 0.8), ('5', 8.0), ('6', 14.0), ('7', 22.4)]
XN = 3.1                                       # eje auxiliar «N»: cara occidental de los núcleos (programa.json)
EJX = dict(EJES_X)
EJY = dict(EJES_Y)
Z = [0.0, 4.5, 8.7, 12.9, 17.1]               # niveles del 1.2: piso 1, 2, 3, 4 y cubierta del piso 4
NIV = 4
Y_RETROCESO = -7.6                             # el piso 4 (entrepiso 4) solo existe con y ≥ −7,6 (líneas 3-7)
CONTORNO_COMPLETO = [[-13.0, -19.6], [8.6, -19.6], [8.6, 22.4], [-13.0, 22.4]]
CONTORNO_P4 = [[-13.0, -7.6], [8.6, -7.6], [8.6, 22.4], [-13.0, 22.4]]
CONTORNOS = [CONTORNO_COMPLETO, CONTORNO_COMPLETO, CONTORNO_COMPLETO, CONTORNO_P4]   # niveles 1 a 4
NUCLEOS = {
    'escalera_norte': {'x': (3.1, 8.6), 'y': (14.0, 22.4)},
    'escalera_sur': {'x': (3.1, 8.6), 'y': (-7.6, 0.8)},
    'ascensores': {'x': (3.1, 6.1), 'y': (1.6, 7.2)},
}
H_LOSA = 0.45                                  # losa nervada: altura total (m)
LOSETA = 0.05                                  # loseta superior (m)
NERVIO_B, NERVIO_S = 0.12, 0.80                # ancho del nervio y separación entre ejes (m)


def niveles_de_linea_x(ly):
    """Niveles (1..4) que tiene un pórtico X en la línea de y = ly: el piso 4 solo en las líneas 3-7."""
    return [1, 2, 3, 4] if ly >= Y_RETROCESO - 1e-9 else [1, 2, 3]


def existe_columna(x, y, k):
    """Columna del entrepiso k (1..4) en el cruce (x, y)."""
    return k <= 3 or y >= Y_RETROCESO - 1e-9


def validar_geometria(programa):
    """El contrato fija la geometría (1.2); si programa.json cambió, el prediseño se debe rehacer: falla con aviso."""
    imp = programa['implantacion']
    h = {x['id']: x for x in imp['huella']}
    errores = []
    if h['torre_pisos_1_a_3']['limites'] != {'x': [-13.0, 8.6], 'y': [-19.6, 22.4]}:
        errores.append('huella de los pisos 1-3')
    if h['torre_piso_4']['limites'] != {'x': [-13.0, 8.6], 'y': [-7.6, 22.4]}:
        errores.append('huella del piso 4')
    niv = imp['pisos_y_alturas']['niveles_m']
    if [niv['piso_1'], niv['piso_2'], niv['piso_3'], niv['piso_4'], niv['cubierta_piso_4']] != Z:
        errores.append('niveles')
    for k, v in NUCLEOS.items():
        lim = imp['nucleos_verticales'][k]['limites']
        if tuple(lim['x']) != v['x'] or tuple(lim['y']) != v['y']:
            errores.append(f'núcleo {k}')
    if errores:
        raise SystemExit('programa.json no coincide con la geometría del contrato (1.2): ' + ', '.join(errores))


# Muros de los núcleos (E1). Cerca de los ≈ 45 m lineales del presupuesto (3.02): las caras occidentales (x = 3,1)
# de las dos escaleras y del foso de ascensores (muros en y) y las caras norte y sur de las dos escaleras (muros en
# x, sobre las líneas 3, 4, 6 y 7). Total: 8,4 + 8,4 + 5,6 + 4 × 5,5 = 44,4 m. Se dejan sin muro estructural las
# caras orientales (x = 8,6, fachada sobre el eje D) para no correr el centro de rigidez más al oriente: el centro
# de masa está cerca de x ≈ −2 (ver «eleccion_muros» en el JSON, con la excentricidad que resulta).
MUROS = [
    {'portico': 'MY-N6', 'dir': 'y', 'c': XN, 's0': 14.0, 's1': 22.4, 'eje': '6', 'tramo': 'N entre 6 y 7',
     'nucleo': 'escalera_norte', 'forma': 'C', 'aletas': ('MX-6', 'MX-7')},
    {'portico': 'MY-N3', 'dir': 'y', 'c': XN, 's0': -7.6, 's1': 0.8, 'eje': '3', 'tramo': 'N entre 3 y 4',
     'nucleo': 'escalera_sur', 'forma': 'C', 'aletas': ('MX-3', 'MX-4')},
    {'portico': 'MY-N4', 'dir': 'y', 'c': XN, 's0': 1.6, 's1': 7.2, 'eje': '4', 'tramo': 'N entre 4 y 5 (foso de ascensores)',
     'nucleo': 'ascensores', 'forma': 'R', 'aletas': ()},
    {'portico': 'MX-3', 'dir': 'x', 'c': -7.6, 's0': XN, 's1': 8.6, 'eje': 'D', 'tramo': '3 entre N y D',
     'nucleo': 'escalera_sur', 'forma': 'L', 'aleta_de': 'MY-N3', 'columna': ('D', '3'), 'vecino': 0.8},
    {'portico': 'MX-4', 'dir': 'x', 'c': 0.8, 's0': XN, 's1': 8.6, 'eje': 'D', 'tramo': '4 entre N y D',
     'nucleo': 'escalera_sur', 'forma': 'L', 'aleta_de': 'MY-N3', 'columna': ('D', '4'), 'vecino': -7.6},
    {'portico': 'MX-6', 'dir': 'x', 'c': 14.0, 's0': XN, 's1': 8.6, 'eje': 'D', 'tramo': '6 entre N y D',
     'nucleo': 'escalera_norte', 'forma': 'L', 'aleta_de': 'MY-N6', 'columna': ('D', '6'), 'vecino': 22.4},
    {'portico': 'MX-7', 'dir': 'x', 'c': 22.4, 's0': XN, 's1': 8.6, 'eje': 'D', 'tramo': '7 entre N y D',
     'nucleo': 'escalera_norte', 'forma': 'L', 'aleta_de': 'MY-N6', 'columna': ('D', '7'), 'vecino': 14.0},
]
LINEAS_CON_MURO_X = {m['c'] for m in MUROS if m['dir'] == 'x'}     # líneas 3, 4, 6 y 7: el vano C-D es muro


def secciones_muro(m, t, col_b, activos, t_de):
    """Rectángulos de la sección en el plano del muro (u a lo largo del muro; ancho perpendicular) con las aletas
    efectivas de NSR-10 C.21.9.5.2 (por confirmar): desde la cara del alma, la menor entre la mitad de la distancia al
    alma vecina, el 25 % de la altura total del muro y lo que de verdad mide la aleta. Solo cuentan como aletas los
    paños estructurales (activos). → (rectángulos, notas)."""
    hw = H_TOTAL
    rect, notas = [], []
    if m['forma'] == 'C':
        # alma en y entre los muros en x de la misma escalera (aletas en los dos bordes si los dos son estructurales)
        largo_aleta = 8.6 - (XN + t / 2)                 # hasta el eje D (fachada)
        bf = min(0.25 * hw, largo_aleta)                 # no hay otra alma en y dentro del núcleo
        for extremo, (s_a, aleta) in enumerate(((m['s0'], m['aletas'][0]), (m['s1'], m['aletas'][1]))):
            if aleta in activos:
                tf = t_de(aleta)
                u0, u1 = (s_a - tf / 2, s_a + tf / 2)
                rect.append((u0, u1, t + bf))
                notas.append(f'aleta del borde {"sur" if extremo == 0 else "norte"}: muro {aleta}; ancho efectivo desde la '
                             f'cara del alma = min(0,25·hw = {es(0.25 * hw)}; longitud real {es(largo_aleta)}) = {es(bf)} m')
            else:
                notas.append(f'sin aleta en el borde {"sur" if extremo == 0 else "norte"} ({aleta} no es estructural)')
        a0 = max([x[1] for x in rect if x[0] < m['s0'] + 0.5], default=m['s0'])
        a1 = min([x[0] for x in rect if x[1] > m['s1'] - 0.5], default=m['s1'])
        rect.append((a0, a1, t))
        rect.sort()
    elif m['forma'] == 'R':
        rect.append((m['s0'], m['s1'], t))
        notas.append('rectangular (las otras caras del foso no son estructurales)')
    else:
        # alma en x; aleta en el borde occidental (muro en y de la escalera) y columna del eje D en el oriental
        dist = abs(m['vecino'] - m['c'])
        ty = t_de(m['aleta_de'])
        if m['aleta_de'] in activos:
            bf = min(0.25 * hw, dist / 2 if m['vecino_activo'] else dist - t / 2, dist - t / 2)
            notas.append(f'aleta en el borde occidental (muro {m["aleta_de"]}): ancho efectivo desde la cara del alma = '
                         f'min(0,25·hw = {es(0.25 * hw)}; ' + (f'mitad de la distancia a la otra alma = {es(dist / 2)}'
                                                                if m['vecino_activo'] else f'longitud real = {es(dist - t / 2)}')
                         + f') = {es(bf)} m')
            rect.append((XN - ty / 2, XN + ty / 2, t + bf))
            u_alma = XN + ty / 2
        else:
            u_alma = XN - t / 2
        notas.append(f'columna {m["columna"][0]}{m["columna"][1]} de {es(col_b)} × {es(col_b)} m como elemento de borde oriental')
        rect.append((u_alma, 8.6 - col_b / 2, t))
        rect.append((8.6 - col_b / 2, 8.6 + col_b / 2, col_b))
    return rect, notas


def props_rectangulos(rect):
    """Área, centroide (u) e inercia de una sección de rectángulos (u0, u1, ancho)."""
    A = sum((u1 - u0) * b for u0, u1, b in rect)
    uc = sum((u1 - u0) * b * (u0 + u1) / 2 for u0, u1, b in rect) / A
    I = sum(b * (u1 - u0) ** 3 / 12 + (u1 - u0) * b * ((u0 + u1) / 2 - uc) ** 2 for u0, u1, b in rect)
    return A, uc, I


# =================================================================================================================
# 4. Cargas del título B y masas
# =================================================================================================================
# Pesos unitarios (NSR-10 título B; tablas B.3.2-1, B.3.4.1-1 a B.3.4.1-3, B.3.4.2; numerales y valores por
# confirmar con el texto, «estimación» donde se dice)
CARGAS_MUERTAS = {
    'acabado_piso_kPa': (1.10, 'baldosa o vinilo sobre 25 mm de mortero de nivelación (NSR-10 Tabla B.3.4.1-3, por confirmar)'),
    'cielo_kPa': (0.25, 'cielo raso registrable sobre perfilería (NSR-10 Tabla B.3.4.1-1, por confirmar)'),
    'instalaciones_kPa': (0.50, 'ductos de aire, gases medicinales, bandejas y rociadores colgados (hospital; estimación sobre '
                                'los 0,20 kPa de ductos mecánicos de la Tabla B.3.4.1-1)'),
    'cubierta_kPa': (1.40, 'impermeabilización, aislamiento térmico y mortero de pendiente de 50 mm promedio (estimación con '
                           'la Tabla B.3.4.1-3)'),
    'paneles_solares_kPa': (0.20, 'módulo de 2,28 × 1,13 m de ≈ 28 kg con su estructura sobre 3,0 m² de cubierta (programa.json; '
                                  'estimación)'),
    'ladrillo_fachada_kN_m2': (2.90, 'ladrillo prensado a la vista de 150 mm (γ ≈ 18 kN/m³) con pañete interior (Tabla B.3.4.2, '
                                     'por confirmar)'),
    'bloque_kN_m2': (2.00, 'bloque de arcilla N.º 5 (120 mm) pañetado por las dos caras (Tabla B.3.4.2, por confirmar)'),
    'liviano_kN_m2': (0.50, 'muro liviano en placa de yeso RH doble cara con aislamiento (estimación)'),
    'ventana_kN_m2': (0.45, 'ventanería de aluminio y vidrio (Tabla B.3.4.2, por confirmar)'),
    'celosia_kN_m2': (0.15, 'celosías de aluminio extruido (estimación)'),
    'alero_kN_m': (0.35, 'alero de 1,40 m en aluminio compuesto sobre estructura metálica (estimación)'),
}
# Carga viva (NSR-10 Tabla B.4.2.1-1, por confirmar): institucional: cirugía y laboratorios 4,0; cuartos privados
# 2,0; corredores y escaleras 5,0; oficinas y consultorios 2,0; gimnasios y salones 5,0; almacenamiento liviano 6,0.
# Promedio por piso con la zonificación de programa.json (estimación de las fracciones de área).
VIVA_POR_PISO = {
    2: ([(0.20, 4.0, 'laboratorio clínico'), (0.35, 2.0, 'consultorios, vacunación y ecografía'),
         (0.35, 5.0, 'corredores y salas de espera'), (0.10, 6.0, 'farmacia (almacenamiento liviano)')], 'piso 2'),
    3: ([(0.45, 2.0, 'habitaciones'), (0.20, 4.0, 'partos (TPR) y esterilización'), (0.35, 5.0, 'corredores')], 'piso 3'),
    4: ([(0.25, 5.0, 'terapias y gimnasio'), (0.30, 2.0, 'odontología y consultorios'),
         (0.10, 5.0, 'salón de telesalud y expansión'), (0.35, 5.0, 'corredores')], 'piso 4'),
}
VIVA_CUBIERTA = 1.80          # kPa, cubierta de concreto transitable para mantenimiento (Tabla B.4.2.1-2, por confirmar)
VIVA_ESCALERA = 5.0           # kPa, escaleras de evacuación (Tabla B.4.2.1-1)
FRACCION_VIVA_MASA = 0.25     # masa sísmica = muerta + 25 % de la viva de los pisos (supuesto del contrato, 7.2)


def viva_piso(p):
    filas, _ = VIVA_POR_PISO[p]
    return sum(f * q for f, q, _ in filas)


def area_poligono(pol):
    return 0.5 * abs(sum(pol[i][0] * pol[i - 1][1] - pol[i - 1][0] * pol[i][1] for i in range(len(pol))))


class Masa:
    """Acumulador de masa por nivel: masa (t), momentos de primer orden y momento polar respecto al origen."""

    def __init__(self):
        self.m = 0.0
        self.mx = 0.0
        self.my = 0.0
        self.j0 = 0.0      # Σ (J propio + m·r²) respecto al origen
        self.detalle = {}

    def punto(self, m, x, y, cat, j=0.0):
        if m == 0:
            return
        self.m += m
        self.mx += m * x
        self.my += m * y
        self.j0 += j + m * (x * x + y * y)
        self.detalle[cat] = self.detalle.get(cat, 0.0) + m

    def rect(self, m, x0, x1, y0, y1, cat):
        self.punto(m, (x0 + x1) / 2, (y0 + y1) / 2, cat, m * ((x1 - x0) ** 2 + (y1 - y0) ** 2) / 12)

    def linea(self, m, x0, y0, x1, y1, cat):
        L2 = (x1 - x0) ** 2 + (y1 - y0) ** 2
        self.punto(m, (x0 + x1) / 2, (y0 + y1) / 2, cat, m * L2 / 12)

    def cm(self):
        return self.mx / self.m, self.my / self.m

    def jz(self):
        xc, yc = self.cm()
        return self.j0 - self.m * (xc * xc + yc * yc)


def item(presupuesto, codigo):
    for c in presupuesto['capitulos']:
        for it in c.get('items', []):
            if it['codigo'] == codigo:
                return it
    raise KeyError(codigo)


def t_equivalente_losa():
    """Espesor equivalente de concreto de la losa nervada (m³/m²): loseta + nervios + una riostra por luz de 7,20 m
    (NSR-10 C.8.13; nervios de 0,12 m cada 0,80 m, altura total 0,45 m)."""
    nervios = NERVIO_B * (H_LOSA - LOSETA) / NERVIO_S
    riostra = NERVIO_B * (H_LOSA - LOSETA) / 7.2
    return LOSETA + nervios + riostra


def construir(dim, presupuesto):
    """Arma la torre: pórticos del modelo (con cargas de gravedad D, L y Lr por elemento y por nodo), columnas y vigas
    físicas, muros, paneles de losa, fachadas, escaleras y masas por nivel. dim: dimensiones (sección 7, ajustes)."""
    cm_ = CARGAS_MUERTAS
    col_b = dim['col']
    t_m = dim['muro_t']
    activos = list(dim.get('muros', [m['portico'] for m in MUROS]))
    t_de = lambda pid: dim.get('t_muro', {}).get(pid, t_m)
    lineas_muro_x = {m['c'] for m in MUROS if m['dir'] == 'x' and m['portico'] in activos}
    t_eq = t_equivalente_losa()
    q_losa = t_eq * GAMMA_C
    q_ins = cm_['cielo_kPa'][0] + cm_['instalaciones_kPa'][0]
    # ---- muros divisorios y fachada desde las cantidades del capítulo 4 de presupuesto.json -----------------------
    a_bloque = item(presupuesto, '4.01')['cantidad']
    a_liviano = item(presupuesto, '4.02')['cantidad']
    a_ladrillo = item(presupuesto, '4.03')['cantidad']
    a_celosia = item(presupuesto, '4.05')['cantidad']
    ml_alero = item(presupuesto, '4.06')['cantidad']
    a_fachada_bruta, a_ventanas = 2407.0, 600.0          # texto de 4.03: «fachada bruta de 2.407 m² menos 600 m²»
    area_pisos = 3 * 907.2 + 648.0                       # m² construidos de la torre (programa.json)
    q_div = (a_bloque * cm_['bloque_kN_m2'][0] + a_liviano * cm_['liviano_kN_m2'][0]) / area_pisos
    w_fach_m2 = (a_ladrillo * cm_['ladrillo_fachada_kN_m2'][0] + a_ventanas * cm_['ventana_kN_m2'][0]) / a_fachada_bruta
    fachada_oeste = 42.0 * 12.9 + 30.0 * 4.2
    w_celosia_m2 = a_celosia * cm_['celosia_kN_m2'][0] / fachada_oeste
    w_alero = cm_['alero_kN_m'][0] * ml_alero / (4 * 2 * 21.6)     # por metro de borde norte y sur, en cada nivel
    paneles_frac = {'terraza': 71 * 3.0 / (21.6 * 12.0), 'cubierta': 119 * 3.0 / 648.0}   # programa.json, cubierta técnica

    masas = [Masa() for _ in range(NIV)]

    def masa(k, W, x, y, cat, forma=None):
        """Suma un peso W (kN) al nivel k (1..4) como masa W/g; forma: None (punto), ('rect', x0, x1, y0, y1) o ('linea', …)."""
        if k < 1 or k > NIV or W == 0:
            return
        m = W / G
        if forma is None:
            masas[k - 1].punto(m, x, y, cat)
        elif forma[0] == 'rect':
            masas[k - 1].rect(m, *forma[1:], cat)
        else:
            masas[k - 1].linea(m, *forma[1:], cat)

    # ---- pórticos: nodos y elementos ------------------------------------------------------------------------------
    porticos = []
    columnas = {}      # físicas: (ex, ey, k) → dict
    vigas = {}         # id → dict (físicas = las del modelo, más las vigas cortas que llegan a los muros)

    def h_viga_y(nombre_x):
        return dim['vy_borde'] if nombre_x in ('A', 'D') else dim['vy_int']

    def h_viga_x(nombre_y):
        return dim.get('vx_borde', dim['vx']) if nombre_y in ('1', '7') else dim['vx']

    def cb(nx, ny):
        """Lado de la columna cuadrada del cruce (nx, ny): las de fachada pueden ser mayores (ajustes, sección 7)."""
        return dim.get('col_borde', col_b) if (nx in ('A', 'D') or ny in ('1', '7')) else col_b

    def nodo_id(pid, eje, k):
        return f'{pid}/{eje}{k}'

    for ny, yl in EJES_Y:
        pid = f'X-{ny}'
        niveles = niveles_de_linea_x(yl)
        ejes = [(nx, xl) for nx, xl in EJES_X if not (yl in lineas_muro_x and nx == 'D')]
        P = {'id': pid, 'dir': 'x', 'c': yl, 'nodos': [], 'elementos': [], 'cargas': {}}
        vxb, vxh = h_viga_x(ny)
        for k in [0] + niveles:
            for nx, xl in ejes:
                P['nodos'].append({'id': nodo_id(pid, nx, k), 's': xl, 'nivel': k, 'eje': nx})
        for k in niveles:
            for nx, xl in ejes:
                fis = f'C-{nx}{ny}-{k}'
                P['elementos'].append({'id': f'{fis}@X', 'fisico': fis, 'tipo': 'columna', 'i': nodo_id(pid, nx, k - 1),
                                       'j': nodo_id(pid, nx, k), 'b': cb(nx, ny), 'h': cb(nx, ny), 'arms': [0.0, vxh],
                                       'eje': f'{nx}-{ny}', 'nivel': k})
            for (n1, x1), (n2, x2) in zip(ejes[:-1], ejes[1:]):
                P['elementos'].append({'id': f'VX-{ny}-{n1}{n2}-{k}', 'tipo': 'viga', 'i': nodo_id(pid, n1, k),
                                       'j': nodo_id(pid, n2, k), 'b': vxb, 'h': vxh, 'arms': [cb(n1, ny) / 2, cb(n2, ny) / 2],
                                       'eje': f'{ny} entre {n1} y {n2}', 'nivel': k})
        porticos.append(P)
    for nx, xl in EJES_X:
        pid = f'Y-{nx}'
        P = {'id': pid, 'dir': 'y', 'c': xl, 'nodos': [], 'elementos': [], 'cargas': {}}
        vb, vh = h_viga_y(nx)
        for k in range(0, NIV + 1):
            for ny, yl in EJES_Y:
                if k == 0 or existe_columna(xl, yl, k):
                    P['nodos'].append({'id': nodo_id(pid, ny, k), 's': yl, 'nivel': k, 'eje': ny})
        for k in range(1, NIV + 1):
            ejes = [(ny, yl) for ny, yl in EJES_Y if existe_columna(xl, yl, k)]
            for ny, yl in ejes:
                fis = f'C-{nx}{ny}-{k}'
                P['elementos'].append({'id': f'{fis}@Y', 'fisico': fis, 'tipo': 'columna', 'i': nodo_id(pid, ny, k - 1),
                                       'j': nodo_id(pid, ny, k), 'b': cb(nx, ny), 'h': cb(nx, ny), 'arms': [0.0, vh],
                                       'eje': f'{nx}-{ny}', 'nivel': k})
            for (n1, y1), (n2, y2) in zip(ejes[:-1], ejes[1:]):
                P['elementos'].append({'id': f'VY-{nx}-{n1}{n2}-{k}', 'tipo': 'viga', 'i': nodo_id(pid, n1, k),
                                       'j': nodo_id(pid, n2, k), 'b': vb, 'h': vh, 'arms': [cb(nx, n1) / 2, cb(nx, n2) / 2],
                                       'eje': f'{nx} entre {n1} y {n2}', 'nivel': k})
        porticos.append(P)
    # muros (pórticos de muros, E1): nodo en el centroide de la sección, un elemento por entrepiso
    muros = {}
    for m0 in MUROS:
        if m0['portico'] not in activos:
            continue
        m = dict(m0)
        if m['dir'] == 'x':
            m['vecino_activo'] = any(o['dir'] == 'x' and o['c'] == m['vecino'] and o['portico'] in activos for o in MUROS)
        tw = t_de(m['portico'])
        cD = cb('D', m['columna'][1]) if m['dir'] == 'x' else col_b
        m['col_borde_b'] = cD
        rect, notas = secciones_muro(m, tw, cD, activos, t_de)
        A, uc, I = props_rectangulos(rect)
        alma = [x for x in rect if abs(x[2] - tw) < 1e-9]
        if m['forma'] == 'R':
            Av = 5 / 6 * A
        else:
            Av = sum((x[1] - x[0]) * x[2] for x in alma)   # área del alma (las aletas no toman cortante en el plano)
        u0 = min(x[0] for x in rect)
        u1 = max(x[1] for x in rect)
        pid = m['portico']
        P = {'id': pid, 'dir': m['dir'], 'c': m['c'], 'nodos': [], 'elementos': [], 'cargas': {}, 'muro': m}
        for k in range(0, NIV + 1):
            P['nodos'].append({'id': nodo_id(pid, m['eje'], k), 's': uc, 'nivel': k, 'eje': m['eje']})
        lado = pid[3:] if m['dir'] == 'x' else 'N' + m['eje']
        for k in range(1, NIV + 1):
            eid = f'{pid[:2]}-{lado}{m["eje"] if m["dir"] == "x" else ""}-{k}'
            P['elementos'].append({'id': eid, 'tipo': 'muro_concreto', 'i': nodo_id(pid, m['eje'], k - 1),
                                   'j': nodo_id(pid, m['eje'], k), 'b': tw, 'h': u1 - u0, 'arms': [0.0, 0.0],
                                   'eje': m['tramo'], 'nivel': k, 'A': A, 'I': I, 'Av': Av, 'rect': rect})
        muros[pid] = {'def': m, 'rect': rect, 'notas': notas, 'A': A, 'I': I, 'Av': Av, 'uc': uc, 'u0': u0, 'u1': u1, 't': tw}
        porticos.append(P)

    # propiedades elásticas de cada elemento (iguales a las de web/js/sismo/modelo.js)
    zniv = Z
    for P in porticos:
        nodos = {n['id']: n for n in P['nodos']}
        for e in P['elementos']:
            ni, nj = nodos[e['i']], nodos[e['j']]
            if e['tipo'] == 'viga':
                L = nj['s'] - ni['s']
                e['fis'] = 0.35
            else:
                L = zniv[nj['nivel']] - zniv[ni['nivel']]
                e['fis'] = 0.70 if e['tipo'] == 'columna' else 0.35
            if e['tipo'] != 'muro_concreto':
                e['A'] = e['b'] * e['h']
                e['I'] = e['b'] * e['h'] ** 3 / 12
                e['Av'] = 5 / 6 * e['A']
            e['L'] = L
            e['Lf'] = L - e['arms'][0] - e['arms'][1]
            e['EI'] = EC * 1000 * e['I'] * e['fis']
            e['GAv'] = GC * 1000 * e['Av']
            e['EA'] = EC * 1000 * e['A'] if e['tipo'] != 'viga' else 0.0
            e['w'] = {'D': 0.0, 'L': 0.0, 'Lr': 0.0}
        P['idx'] = nodos

    por_id = {P['id']: P for P in porticos}
    elem = {e['id']: (P, e) for P in porticos for e in P['elementos']}

    def carga_nodo(pid, nid, caso, val):
        c = por_id[pid]['cargas'].setdefault(nid, {'D': 0.0, 'L': 0.0, 'Lr': 0.0})
        c[caso] += val

    def carga_viga(eid, caso, w):
        elem[eid][1]['w'][caso] += w

    def vigas_y(nx, y0, y1, k):
        """Elementos de la línea Y-nx en el nivel k que cubren [y0, y1] con la fracción que les toca."""
        out = []
        for e in por_id[f'Y-{nx}']['elementos']:
            if e['tipo'] != 'viga' or e['nivel'] != k:
                continue
            P = por_id[f'Y-{nx}']
            a, b = P['idx'][e['i']]['s'], P['idx'][e['j']]['s']
            sol = min(b, y1) - max(a, y0)
            if sol > 1e-9:
                out.append((e['id'], sol / (b - a)))
        return out

    def vigas_x(ny, x0, x1, k):
        out = []
        P = por_id.get(f'X-{ny}')
        for e in P['elementos']:
            if e['tipo'] != 'viga' or e['nivel'] != k:
                continue
            a, b = P['idx'][e['i']]['s'], P['idx'][e['j']]['s']
            sol = min(b, x1) - max(a, x0)
            if sol > 1e-9:
                out.append((e['id'], sol / (b - a)))
        return out

    def nodo_muro(pid, k):
        m = por_id[pid]['muro']
        return nodo_id(pid, m['eje'], k)

    # ---- losas: paneles con viguetas en x (luz de 7,20 m entre los pórticos Y) ------------------------------------
    paneles = []
    for k in range(1, NIV + 1):
        for (na, xa), (nb, xb) in zip(EJES_X[:-1], EJES_X[1:]):
            for (n0, y0), (n1, y1) in zip(EJES_Y[:-1], EJES_Y[1:]):
                if k == 4 and y0 < Y_RETROCESO - 1e-9:
                    continue
                tipo = 'piso' if k <= 2 or (k == 3 and y0 >= Y_RETROCESO - 1e-9) else ('terraza' if k == 3 else 'cubierta')
                sub = []
                if (na, nb) == ('C', 'D') and (y0, y1) in ((14.0, 22.4), (-7.6, 0.8)):
                    muro = 'MY-N6' if y0 == 14.0 else 'MY-N3'
                    sub.append((xa, XN, y0, y1, ('Y', na), ('M', muro)))
                elif (na, nb) == ('C', 'D') and (y0, y1) == (0.8, 8.0):
                    sub.append((xa, xb, 0.8, 1.6, ('Y', na), ('Y', nb)))
                    sub.append((xa, XN, 1.6, 7.2, ('Y', na), ('M', 'MY-N4')))
                    sub.append((6.1, xb, 1.6, 7.2, ('VS', None), ('Y', nb)))
                    sub.append((xa, xb, 7.2, 8.0, ('Y', na), ('Y', nb)))
                else:
                    sub.append((xa, xb, y0, y1, ('Y', na), ('Y', nb)))
                for (x0, x1, yy0, yy1, sw, se) in sub:
                    paneles.append({'nivel': k, 'tipo': tipo, 'x0': x0, 'x1': x1, 'y0': yy0, 'y1': yy1, 'apoyos': (sw, se),
                                    'extra_D_kN': 0.0})
    # equipos de cubierta (programa.json → cubierta_tecnica; pesos y posiciones: estimación)
    equipos = [
        {'id': 'tanques_respaldo', 'W_kN': 2 * (5.0 * 9.80665 + 5.0), 'x': -1.0, 'y': 18.0,
         'nota': '2 tanques de 5 m³ llenos (agua 49 kN cada uno) más 5 kN de tanque y base'},
        {'id': 'condensadoras', 'W_kN': 36.0, 'x': -6.0, 'y': 10.0, 'nota': '≈ 40 m² de unidades condensadoras (≈ 12 de 300 kg)'},
        {'id': 'extractores', 'W_kN': 10.0, 'x': -6.0, 'y': 2.0, 'nota': '≈ 10 m² de extractores'},
        {'id': 'agua_caliente_solar', 'W_kN': 8.0, 'x': -1.0, 'y': 6.0, 'nota': '≈ 10 m² de colectores con su tanque'},
    ]
    for eq in equipos:
        for p in paneles:
            if p['nivel'] == 4 and p['x0'] <= eq['x'] <= p['x1'] and p['y0'] <= eq['y'] <= p['y1']:
                p['extra_D_kN'] += eq['W_kN']
                break
    for p in paneles:
        a = (p['x1'] - p['x0']) * (p['y1'] - p['y0'])
        if p['tipo'] == 'piso':
            qD = q_losa + cm_['acabado_piso_kPa'][0] + q_ins + q_div
            qL, qLr = viva_piso(p['nivel'] + 1), 0.0
        else:
            qD = q_losa + cm_['cubierta_kPa'][0] + q_ins + cm_['paneles_solares_kPa'][0] * paneles_frac[p['tipo']]
            qL, qLr = 0.0, VIVA_CUBIERTA
        qD += p['extra_D_kN'] / a
        p.update({'area': a, 'qD': qD, 'qL': qL, 'qLr': qLr})
        k = p['nivel']
        # masa: todo el panel en su nivel, menos los divisorios (mitad abajo y mitad arriba, ver más abajo)
        qD_masa = qD - (q_div if p['tipo'] == 'piso' else 0.0)
        forma = ('rect', p['x0'], p['x1'], p['y0'], p['y1'])
        masa(k, q_losa * a, 0, 0, 'losa', forma)
        masa(k, (qD_masa - q_losa) * a - p['extra_D_kN'], 0, 0, 'acabados_e_instalaciones', forma)
        if p['extra_D_kN']:
            for eq in equipos:
                if p['x0'] <= eq['x'] <= p['x1'] and p['y0'] <= eq['y'] <= p['y1']:
                    masa(k, eq['W_kN'], eq['x'], eq['y'], 'equipos_de_cubierta')
        masa(k, FRACCION_VIVA_MASA * qL * a, 0, 0, 'viva_25pct', forma)
        # reparto a los apoyos: la mitad de la luz a cada lado (viguetas en una dirección)
        luz = p['x1'] - p['x0']
        for apoyo in p['apoyos']:
            for caso, q in (('D', qD), ('L', qL), ('Lr', qLr)):
                if q == 0:
                    continue
                w_lineal = q * luz / 2                      # kN/m a lo largo del apoyo
                if apoyo[0] == 'Y':
                    for eid, frac in vigas_y(apoyo[1], p['y0'], p['y1'], k):
                        e = elem[eid][1]
                        # carga uniforme equivalente sobre el elemento (misma resultante)
                        carga_viga(eid, caso, w_lineal * frac)
                elif apoyo[0] == 'M' and apoyo[1] in activos:
                    carga_nodo(apoyo[1], nodo_muro(apoyo[1], k), caso, w_lineal * (p['y1'] - p['y0']))
                elif apoyo[0] == 'M':
                    # cara del núcleo sin muro estructural: viga de borde en x = 3,1 entre los muros en x del núcleo
                    # (o entre las vigas X de esas líneas), la mitad de la carga a cada extremo
                    W = w_lineal * (p['y1'] - p['y0'])
                    lin0 = max((yv, n) for n, yv in EJES_Y if yv <= p['y0'] + 1e-9)[1]
                    lin1 = min((yv, n) for n, yv in EJES_Y if yv >= p['y1'] - 1e-9)[1]
                    for nyl in (lin0, lin1):
                        pm_ = f'MX-{nyl}'
                        if pm_ in activos:
                            carga_nodo(pm_, nodo_muro(pm_, k), caso, W / 2)
                        else:
                            for eid, frac in vigas_x(nyl, 1.4, 8.6, k):
                                carga_viga(eid, caso, W / 2 / elem[eid][1]['L'])
                else:
                    # viga secundaria en x = 6,1 (borde del foso), de y = 0,8 a 8,0: la mitad al muro MX-4 y la mitad a
                    # la viga X-5 C-D (como carga uniforme de la misma resultante)
                    W = w_lineal * (p['y1'] - p['y0'])
                    if 'MX-4' in activos:
                        carga_nodo('MX-4', nodo_muro('MX-4', k), caso, W / 2)
                    else:
                        for eid, frac in vigas_x('4', 1.4, 8.6, k):
                            carga_viga(eid, caso, W / 2 / elem[eid][1]['L'])
                    for eid, frac in vigas_x('5', 1.4, 8.6, k):
                        carga_viga(eid, caso, W / 2 / elem[eid][1]['L'])
    # franja de loseta sobre las vigas X (paralelas a las viguetas): media separación entre nervios a cada lado
    for P in porticos:
        if P['dir'] != 'x' or P['id'].startswith('M'):
            continue
        for e in P['elementos']:
            if e['tipo'] != 'viga':
                continue
            k = e['nivel']
            borde = P['c'] in (-19.6, 22.4) or (k == 4 and P['c'] == Y_RETROCESO)
            ancho = NERVIO_S / 2 * (1 if borde else 2)
            x_med = (P['idx'][e['i']]['s'] + P['idx'][e['j']]['s']) / 2
            tipo = 'piso' if k <= 2 or (k == 3 and P['c'] >= Y_RETROCESO) else ('terraza' if k == 3 else 'cubierta')
            if tipo == 'piso':
                carga_viga(e['id'], 'D', ancho * (LOSETA * GAMMA_C + cm_['acabado_piso_kPa'][0] + q_ins + q_div))
                carga_viga(e['id'], 'L', ancho * viva_piso(k + 1))
            else:
                carga_viga(e['id'], 'D', ancho * (LOSETA * GAMMA_C + cm_['cubierta_kPa'][0] + q_ins))
                carga_viga(e['id'], 'Lr', ancho * VIVA_CUBIERTA)
            masa(k, ancho * e['L'] * (LOSETA * GAMMA_C + (cm_['acabado_piso_kPa'][0] + q_ins if tipo == 'piso' else cm_['cubierta_kPa'][0] + q_ins)),
                 0, 0, 'acabados_e_instalaciones',
                 ('linea', P['idx'][e['i']]['s'], P['c'], P['idx'][e['j']]['s'], P['c']))
            if tipo == 'piso':
                masa(k, FRACCION_VIVA_MASA * ancho * e['L'] * viva_piso(k + 1), x_med, P['c'], 'viva_25pct')

    # ---- peso propio de vigas, columnas y muros --------------------------------------------------------------------
    for P in porticos:
        for e in P['elementos']:
            ni, nj = P['idx'][e['i']], P['idx'][e['j']]
            if e['tipo'] == 'viga':
                # la parte de la viga bajo el espesor equivalente de la losa (la loseta y los nervios ya están en la losa)
                w = e['b'] * (e['h'] - t_eq) * GAMMA_C
                carga_viga(e['id'], 'D', w)
                if P['dir'] == 'x':
                    seg = ('linea', ni['s'], P['c'], nj['s'], P['c'])
                else:
                    seg = ('linea', P['c'], ni['s'], P['c'], nj['s'])
                masa(e['nivel'], w * e['L'], 0, 0, 'vigas', seg)
            elif e['tipo'] == 'columna' and P['dir'] == 'y':
                # una sola vez (en su copia Y): el peso al nodo de arriba; la masa, mitad a cada nivel
                W = e['b'] * e['h'] * e['L'] * GAMMA_C
                carga_nodo(P['id'], e['j'], 'D', W)
                x, y = P['c'], nj['s']
                masa(nj['nivel'], W / 2, x, y, 'columnas')
                masa(ni['nivel'], W / 2, x, y, 'columnas')
    # muros: el concreto de cada paño una sola vez (las aletas efectivas no se vuelven a pesar)
    for pid, mu in muros.items():
        m = mu['def']
        tw = mu['t']
        if m['forma'] in ('C', 'R'):
            largo = (m['s1'] - m['s0']) + (tw if m['forma'] == 'C' else 0.0)
            x0, y0, x1, y1 = m['c'], m['s0'], m['c'], m['s1']
        else:
            x_ini = XN + t_de(m['aleta_de']) / 2 if m['aleta_de'] in activos else XN - tw / 2
            largo = (8.6 - m['col_borde_b'] / 2) - x_ini
            x0, y0, x1, y1 = x_ini, m['c'], 8.6 - m['col_borde_b'] / 2, m['c']
        mu['largo_fisico'] = largo
        for k in range(1, NIV + 1):
            h = Z[k] - Z[k - 1]
            W = tw * largo * h * GAMMA_C
            carga_nodo(pid, nodo_muro(pid, k), 'D', W)
            masa(k, W / 2, 0, 0, 'muros_de_concreto', ('linea', x0, y0, x1, y1))
            masa(k - 1, W / 2, 0, 0, 'muros_de_concreto', ('linea', x0, y0, x1, y1))

    # ---- divisorios (mitad de la masa a cada nivel del entrepiso; la carga de gravedad ya va en la losa de abajo) --
    for p in range(1, NIV + 1):
        cont = CONTORNO_P4 if p == 4 else CONTORNO_COMPLETO
        x0, y0 = cont[0]
        x1, y1 = cont[2]
        a = area_poligono(cont) - (5.5 * 8.4 * 2 + 3.0 * 5.6)
        W = q_div * a
        masa(p - 1, W / 2, 0, 0, 'muros_divisorios', ('rect', x0, x1, y0, y1))
        masa(p, W / 2, 0, 0, 'muros_divisorios', ('rect', x0, x1, y0, y1))

    # ---- fachadas, celosías, aleros y antepechos ---------------------------------------------------------------------
    fachadas = []
    for p in range(1, NIV + 1):
        h = Z[p] - Z[p - 1]
        ys, yn = (Y_RETROCESO if p == 4 else -19.6), 22.4
        bordes = [('X', '1' if p < 4 else '3', ys, -13.0, 8.6), ('X', '7', yn, -13.0, 8.6),
                  ('Y', 'A', -13.0, ys, yn), ('Y', 'D', 8.6, ys, yn)]
        for tipo, linea, c, a0, a1 in bordes:
            w = w_fach_m2 * h + (w_celosia_m2 * h if (tipo, linea) == ('Y', 'A') else 0.0)
            tramos = [(a0, a1)]
            if tipo == 'X' and c in lineas_muro_x:
                tramos = [(a0, 1.4)]                       # el vano C-D de esa línea es el muro de concreto
            for t0, t1 in tramos:
                fachadas.append({'piso': p, 'tipo': tipo, 'linea': linea, 'c': c, 'desde': t0, 'hasta': t1, 'h': h, 'w_kN_m': w})
                largo = t1 - t0
                if tipo == 'X':
                    seg = ('linea', t0, c, t1, c)
                else:
                    seg = ('linea', c, t0, c, t1)
                masa(p - 1, w * largo / 2, 0, 0, 'fachada', seg)
                masa(p, w * largo / 2, 0, 0, 'fachada', seg)
                if p >= 2:
                    # se apoya en la viga de borde del nivel de abajo
                    k = p - 1
                    if tipo == 'X':
                        for eid, frac in vigas_x(linea, t0, t1, k):
                            carga_viga(eid, 'D', w * frac)
                    else:
                        for eid, frac in vigas_y(linea, t0, t1, k):
                            carga_viga(eid, 'D', w * frac)
    # antepechos de 1,20 m en ladrillo: cubierta del piso 4 y terraza del piso 3 (sur)
    antepechos = [(4, 'X', '3', Y_RETROCESO, -13.0, 8.6), (4, 'X', '7', 22.4, -13.0, 8.6), (4, 'Y', 'A', -13.0, Y_RETROCESO, 22.4),
                  (4, 'Y', 'D', 8.6, Y_RETROCESO, 22.4), (3, 'X', '1', -19.6, -13.0, 8.6), (3, 'Y', 'A', -13.0, -19.6, Y_RETROCESO),
                  (3, 'Y', 'D', 8.6, -19.6, Y_RETROCESO)]
    w_ant = 1.2 * cm_['ladrillo_fachada_kN_m2'][0]
    for k, tipo, linea, c, t0, t1 in antepechos:
        tramos = [(t0, 1.4)] if (tipo == 'X' and c in lineas_muro_x) else [(t0, t1)]
        for a0, a1 in tramos:
            seg = ('linea', a0, c, a1, c) if tipo == 'X' else ('linea', c, a0, c, a1)
            masa(k, w_ant * (a1 - a0), 0, 0, 'fachada', seg)
            for eid, frac in (vigas_x(linea, a0, a1, k) if tipo == 'X' else vigas_y(linea, a0, a1, k)):
                carga_viga(eid, 'D', w_ant * frac)
    # aleros en los bordes norte y sur de cada nivel
    for k in range(1, NIV + 1):
        for linea, c in ((('1' if k < 3 else ('3' if k == 4 else '1')), (-19.6 if k <= 3 else Y_RETROCESO)), ('7', 22.4)):
            masa(k, w_alero * 21.6, 0, 0, 'fachada', ('linea', -13.0, c, 8.6, c))
            tramos = [(-13.0, 1.4)] if c in lineas_muro_x else [(-13.0, 8.6)]
            for a0, a1 in tramos:
                for eid, frac in vigas_x(linea, a0, a1, k):
                    carga_viga(eid, 'D', w_alero * frac)

    # ---- escaleras (2 núcleos; 2 tramos y 2 descansos por entrepiso; losa de 0,20 m) -------------------------------
    escaleras = []
    for nombre, pid_y, pids_x in (('escalera_norte', 'MY-N6', ('MX-6', 'MX-7')), ('escalera_sur', 'MY-N3', ('MX-3', 'MX-4'))):
        nu = NUCLEOS[nombre]
        xc, yc = (nu['x'][0] + nu['x'][1]) / 2, (nu['y'][0] + nu['y'][1]) / 2
        ancho_int = (nu['x'][1] - nu['x'][0]) - t_m           # 5,2 m entre el muro y la fachada
        largo_int = (nu['y'][1] - nu['y'][0]) - t_m           # 8,1 m entre los muros en x
        for p in range(1, NIV + 1):
            h = Z[p] - Z[p - 1]
            n_cont = math.ceil(h / 2 / 0.18)                    # contrahuellas por tramo (≤ 0,18 m: NSR-10 K.3.8, por confirmar)
            ch = h / 2 / n_cont
            huella = 0.28
            l_h = (n_cont - 1) * huella
            incl = math.hypot(l_h, h / 2)
            descanso = (largo_int - l_h) / 2
            e_losa = 0.20
            vol_tramos = 2 * 2.4 * (incl * e_losa + l_h * ch / 2)
            vol_desc = 2 * ancho_int * descanso * e_losa
            W_D = (vol_tramos + vol_desc) * GAMMA_C + cm_['acabado_piso_kPa'][0] * ancho_int * largo_int
            W_L = VIVA_ESCALERA * ancho_int * largo_int
            escaleras.append({'nucleo': nombre, 'piso': p, 'contrahuellas_por_tramo': n_cont, 'contrahuella_m': ch,
                              'huella_m': huella, 'tramo_horizontal_m': l_h, 'tramo_inclinado_m': incl,
                              'descanso_m': descanso, 'ancho_tramo_m': 2.4, 'ancho_nucleo_m': ancho_int,
                              'largo_nucleo_m': largo_int, 'espesor_m': e_losa, 'volumen_m3': vol_tramos + vol_desc,
                              'W_D_kN': W_D, 'W_L_kN': W_L})
            for kk in (p - 1, p):
                masa(kk, W_D / 2, xc, yc, 'escaleras')
                masa(kk, FRACCION_VIVA_MASA * W_L / 2, xc, yc, 'viva_25pct')
                if kk >= 1:
                    # los descansos se apoyan en los muros en x del núcleo; si alguno no es estructural, en los demás
                    apoyos = [q for q in pids_x if q in activos] or [q for q in (pid_y,) if q in activos]
                    for pid in apoyos:
                        carga_nodo(pid, nodo_muro(pid, kk), 'D', W_D / 2 / len(apoyos))
                        carga_nodo(pid, nodo_muro(pid, kk), 'L', W_L / 2 / len(apoyos))
    # casetas de escalera y sobrerrecorrido de ascensores sobre la cubierta (programa.json; estimación)
    casetas = []
    for nombre, pid_y, pids_x in (('escalera_norte', 'MY-N6', ('MX-6', 'MX-7')), ('escalera_sur', 'MY-N3', ('MX-3', 'MX-4'))):
        nu = NUCLEOS[nombre]
        a = (nu['x'][1] - nu['x'][0]) * (nu['y'][1] - nu['y'][0])
        per = 2 * ((nu['x'][1] - nu['x'][0]) + (nu['y'][1] - nu['y'][0]))
        W = a * (0.15 * GAMMA_C + cm_['cubierta_kPa'][0]) + per * 3.3 * cm_['ladrillo_fachada_kN_m2'][0]
        casetas.append({'id': f'caseta_{nombre}', 'W_kN': W, 'area_m2': a})
        masa(4, W, (nu['x'][0] + nu['x'][1]) / 2, (nu['y'][0] + nu['y'][1]) / 2, 'casetas')
        apoyos = [q for q in (pid_y,) + pids_x if q in activos]
        for pid in apoyos:
            carga_nodo(pid, nodo_muro(pid, 4), 'D', W / len(apoyos))
        if not apoyos:
            for ny_ in pids_x:
                for eid, frac in vigas_x(ny_[3:], 1.4, 8.6, 4):
                    carga_viga(eid, 'D', W / 2 / elem[eid][1]['L'])
    nu = NUCLEOS['ascensores']
    W_sob = 17.2 * 1.8 * 0.20 * GAMMA_C + 16.8 * (0.15 * GAMMA_C + cm_['cubierta_kPa'][0]) + 60.0
    casetas.append({'id': 'sobrerrecorrido_ascensores', 'W_kN': W_sob, 'area_m2': 16.8,
                    'nota': 'muros de 0,20 m y 1,8 m de alto, placa de 0,15 m y 60 kN de máquinas sin cuarto (estimación)'})
    masa(4, W_sob, 4.6, 4.4, 'casetas')
    if 'MY-N4' in activos:
        carga_nodo('MY-N4', nodo_muro('MY-N4', 4), 'D', W_sob)
    else:
        for ny_ in ('4', '5'):
            for eid, frac in vigas_x(ny_, 1.4, 8.6, 4):
                carga_viga(eid, 'D', W_sob / 2 / elem[eid][1]['L'])

    # ---- vigas cortas entre la columna C y el muro (líneas 3, 4, 6 y 7): no están en el modelo (ver docstring) ----
    acoples = []
    for ny, yl in EJES_Y:
        if yl not in lineas_muro_x:
            continue
        for k in niveles_de_linea_x(yl):
            cC = cb('C', ny)
            ln = (XN - t_de(f'MY-N{"6" if yl > 10 else "3"}') / 2) - (EJX['C'] + cC / 2)
            vb_, vh_ = h_viga_x(ny)
            acoples.append({'id': f'VA-{ny}-CN-{k}', 'linea': ny, 'nivel': k, 'b': vb_, 'h': vh_, 'ln': ln,
                            'desde': ('C', EJX['C'] + cC / 2), 'hasta': (f'muro MX-{ny}', EJX['C'] + cC / 2 + ln), 'y': yl})

    # ---- niveles: masa, centro de masa, Jz y contorno ---------------------------------------------------------------
    niveles = []
    for k in range(1, NIV + 1):
        M = masas[k - 1]
        xc, yc = M.cm()
        niveles.append({'id': f'N{k}', 'z': Z[k], 'h': Z[k] - Z[k - 1], 'masa_t': M.m, 'Jz_t_m2': M.jz(), 'cm': (xc, yc),
                        'peso_kN': M.m * G, 'contorno': CONTORNOS[k - 1], 'detalle': dict(M.detalle)})
    for k in range(NIV):
        niveles[k]['P_sobre_kN'] = sum(n['peso_kN'] for n in niveles[k:])

    return {'dim': dim, 'porticos': porticos, 'por_id': por_id, 'elem': elem, 'muros': muros, 'paneles': paneles,
            'fachadas': fachadas, 'escaleras': escaleras, 'casetas': casetas, 'equipos': equipos, 'acoples': acoples,
            'niveles': niveles, 'q': {'losa': q_losa, 't_eq': t_eq, 'div': q_div, 'fachada_m2': w_fach_m2,
                                      'celosia_m2': w_celosia_m2, 'alero_m': w_alero, 'instalaciones': q_ins,
                                      'antepecho_m': w_ant, 'paneles_frac': paneles_frac}}


# =================================================================================================================
# 5. Secciones: análisis por fibras
# =================================================================================================================
# Convención interna: u a lo largo del peralte (en el plano de flexión), compresión positiva en P y en ε; el sentido
# de flexión se da por la cara comprimida ('sup' = la de mayor u). Unidades: m, m², MPa en los materiales y kN, kN·m
# en las resultantes (MPa·m² = 1.000 kN).
K_PRIESTLEY = {'columna': 0.75, 'viga': 0.75, 'muro': 0.60}    # coeficiente de confinamiento efectivo ke
#  (Priestley, Calvi y Kowalsky, 2007, «Displacement-Based Seismic Design of Structures», sección 4.2.6)


class Seccion:
    """Sección por franjas: rect = [(u0, u1, ancho)] sin solapes; barras = [(u, As m²)]; nucleo = [(u0, u1, ancho)]
    confinado (subconjunto de rect) con su cuantía volumétrica de estribos rho_s y su fyh (MPa)."""

    def __init__(self, rect, barras, nucleo=(), rho_s=0.0, fyh=FY, ke=0.75, n=150):
        self.rect = list(rect)
        self.u_min = min(x[0] for x in rect)
        self.u_max = max(x[1] for x in rect)
        A, uc, I = props_rectangulos(rect)
        self.Ag, self.uc, self.Ig = A, uc, I
        self.barras = sorted(barras)
        self.As = sum(a for _, a in barras)
        # franjas entre los cambios de ancho (bordes de los rectángulos y del núcleo), cada tramo con ≥ 8 franjas
        # y franjas de a lo sumo h/n: así las aletas delgadas y anchas quedan bien integradas
        cortes = sorted({x for r_ in list(rect) + list(nucleo) for x in r_[:2]})
        h = self.u_max - self.u_min
        self.fibras = []      # (u, área no confinada, área confinada)
        for a0, a1 in zip(cortes[:-1], cortes[1:]):
            if a1 - a0 < 1e-12:
                continue
            um = (a0 + a1) / 2
            b = sum(w for u0, u1, w in rect if u0 <= um < u1)
            bc = sum(w for u0, u1, w in nucleo if u0 <= um < u1)
            if b == 0:
                continue
            k = max(8, math.ceil((a1 - a0) / (h / n)))
            du = (a1 - a0) / k
            for i in range(k):
                self.fibras.append((a0 + (i + 0.5) * du, (b - bc) * du, bc * du))
        # el área de las barras desplaza concreto: se descuenta de la franja más cercana
        for ub, a in self.barras:
            i = min(range(len(self.fibras)), key=lambda j: abs(self.fibras[j][0] - ub))
            u, an, ac = self.fibras[i]
            if ac >= a:
                self.fibras[i] = (u, an, ac - a)
            else:
                self.fibras[i] = (u, max(an - (a - ac), 0.0), 0.0)
        self.barras_desplazan = [(ub, a) for ub, a in self.barras]
        self.rho_s, self.fyh, self.ke = rho_s, fyh, ke
        self._cache_conf = {}
        self.fibras_mc = self.fibras

    # ---- distancia desde la cara comprimida ---------------------------------------------------------------------
    def d(self, u, cara):
        return self.u_max - u if cara == 'sup' else u - self.u_min

    def brazo(self, u, cara):
        return (u - self.uc) if cara == 'sup' else (self.uc - u)

    def peralte(self):
        return self.u_max - self.u_min

    def d_traccion(self, cara):
        """Distancia de la barra más traccionada a la cara comprimida."""
        return max(self.d(u, cara) for u, _ in self.barras)

    # ---- resistencia con el bloque de Whitney (NSR-10 C.10.2) ------------------------------------------------------
    def whitney(self, c, cara, fc, fy):
        """Bloque rectangular equivalente 0,85·f'c sobre a = β1·c (C.10.2.7), integrado exactamente sobre los
        rectángulos; acero elastoplástico con εcu = 0,003; el concreto que ocupan las barras comprimidas se descuenta."""
        a = BETA1 * c
        P = M = 0.0
        for u0, u1, w in self.rect:
            if cara == 'sup':
                lo_, hi_ = max(u0, self.u_max - a), u1
            else:
                lo_, hi_ = u0, min(u1, self.u_min + a)
            if hi_ > lo_:
                F = 0.85 * fc * w * (hi_ - lo_) * 1000
                P += F
                M += F * self.brazo((lo_ + hi_) / 2, cara)
        for u, As in self.barras:
            dd = self.d(u, cara)
            eps = 0.003 * (c - dd) / c
            fs = max(min(ES * eps, fy), -fy)
            if dd < a:
                fs -= 0.85 * fc
            F = fs * As * 1000
            P += F
            M += F * self.brazo(u, cara)
        return P, M

    def resistencia(self, P_obj, cara, fc=FC, fy=FY):
        """Mn (kN·m) para la carga axial P_obj (kN, compresión +) y la cara comprimida; → (Mn, c, εt, φ)."""
        h = self.peralte()
        lo, hi = 1e-5 * h, 20 * h
        Plo, _ = self.whitney(lo, cara, fc, fy)
        Phi, _ = self.whitney(hi, cara, fc, fy)
        if P_obj <= Plo:
            c = lo
        elif P_obj >= Phi:
            c = hi
        else:
            for _ in range(80):
                c = (lo + hi) / 2
                Pc, _ = self.whitney(c, cara, fc, fy)
                if Pc < P_obj:
                    lo = c
                else:
                    hi = c
            c = (lo + hi) / 2
        _, M = self.whitney(c, cara, fc, fy)
        dt = self.d_traccion(cara)
        et = 0.003 * (dt - c) / c
        # φ de NSR-10 C.9.3.2.2 (estribos): 0,65 si εt ≤ εy; 0,90 si εt ≥ 0,005; lineal entre los dos
        phi = 0.65 if et <= EPS_Y else (0.90 if et >= 0.005 else 0.65 + 0.25 * (et - EPS_Y) / (0.005 - EPS_Y))
        return M, c, et, phi

    def Po(self, fc=FC, fy=FY):
        return (0.85 * fc * (self.Ag - self.As) + fy * self.As) * 1000

    def phiPn_max(self):
        """NSR-10 C.10.3.6.2 (estribos): φPn,max = 0,80·φ·[0,85 f'c (Ag − Ast) + fy Ast], φ = 0,65."""
        return 0.80 * 0.65 * self.Po()

    def To(self, fy=FY):
        return fy * self.As * 1000

    def diagrama_PM(self, cara, n=40):
        """Puntos (φPn, φMn) del diagrama de interacción, de tracción pura a compresión (sin el tope φPn,max)."""
        h = self.peralte()
        out = []
        for i in range(n + 1):
            c = h * (0.02 + 3.0 * (i / n) ** 1.6)
            P, M = self.whitney(c, cara, FC, FY)
            dt = self.d_traccion(cara)
            et = 0.003 * (dt - c) / c
            phi = 0.65 if et <= EPS_Y else (0.90 if et >= 0.005 else 0.65 + 0.25 * (et - EPS_Y) / (0.005 - EPS_Y))
            out.append((phi * P, phi * M, P, M))
        out.insert(0, (-0.9 * self.To(), 0.0, -self.To(), 0.0))
        return out

    def _phi_c(self, c, cara):
        dt = self.d_traccion(cara)
        et = 0.003 * (dt - c) / c
        return 0.65 if et <= EPS_Y else (0.90 if et >= 0.005 else 0.65 + 0.25 * (et - EPS_Y) / (0.005 - EPS_Y))

    def tabla_PM(self, cara):
        """Diagrama (φPn, φMn, Pn, Mn) en 70 puntos de c, ordenado por φPn (crece con c); se guarda por cara."""
        if not hasattr(self, '_tablas'):
            self._tablas = {}
        if cara not in self._tablas:
            h = self.peralte()
            filas = []
            for i in range(91):
                c = h * 2e-4 * (4.0 / 2e-4) ** (i / 90)          # de 0,0002·h a 4·h, espaciado geométrico
                P, M = self.whitney(c, cara, FC, FY)
                ph = self._phi_c(c, cara)
                filas.append((ph * P, ph * M, P, M))
            self._tablas[cara] = filas
        return self._tablas[cara]

    def phiMn_rapido(self, Pu, cara):
        """φMn para Pu por interpolación lineal en el diagrama (None si Pu > φPn,max o Pu < −φTn)."""
        if Pu > self.phiPn_max():
            return None
        t = self.tabla_PM(cara)
        if Pu <= t[0][0]:
            return t[0][1] if Pu >= -0.9 * self.To() else None
        for a, b in zip(t[:-1], t[1:]):
            if a[0] <= Pu <= b[0]:
                f = (Pu - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
                return a[1] + f * (b[1] - a[1])
        return t[-1][1]

    def Mn_rapido(self, P, cara):
        """Mn nominal (φ = 1) para P por interpolación."""
        t = self.tabla_PM(cara)
        if P <= t[0][2]:
            return t[0][3]
        for a, b in zip(t[:-1], t[1:]):
            if a[2] <= P <= b[2]:
                f = (P - a[2]) / (b[2] - a[2]) if b[2] > a[2] else 0.0
                return a[3] + f * (b[3] - a[3])
        return t[-1][3]

    def phiMn_en(self, Pu, cara):
        """φMn (kN·m) para la carga mayorada Pu (kN, compresión +): se busca c con φ(c)·Pn(c) = Pu (φPn crece con c);
        None si Pu excede φPn,max (NSR-10 C.10.3.6.2)."""
        if Pu > self.phiPn_max():
            return None
        h = self.peralte()
        lo, hi = 1e-5 * h, 20 * h
        for _ in range(80):
            c = (lo + hi) / 2
            P, _ = self.whitney(c, cara, FC, FY)
            if self._phi_c(c, cara) * P < Pu:
                lo = c
            else:
                hi = c
        c = (lo + hi) / 2
        _, M = self.whitney(c, cara, FC, FY)
        return self._phi_c(c, cara) * M

    # ---- momento-curvatura (Mander para el concreto, acero bilineal con endurecimiento) ---------------------------
    def _conf(self, fco):
        """Concreto confinado de Mander, Priestley y Park (1988): f'cc con la presión lateral efectiva
        f'l = ke·ρs·fyh/2 (ρs volumétrica repartida en las dos direcciones); εcc = 0,002·[1 + 5(f'cc/f'co − 1)];
        εcu = 0,004 + 1,4·ρs·fyh·εsu/f'cc con εsu = 0,10 (Priestley, Calvi y Kowalsky, 2007)."""
        clave = round(fco, 6)
        if clave not in self._cache_conf:
            fl = self.ke * self.rho_s * self.fyh / 2
            fcc = fco * (-1.254 + 2.254 * math.sqrt(1 + 7.94 * fl / fco) - 2 * fl / fco)
            ecc = 0.002 * (1 + 5 * (fcc / fco - 1))
            ecu = 0.004 + 1.4 * self.rho_s * self.fyh * 0.10 / fcc
            Ec = 4700 * math.sqrt(fco)
            r_c = Ec / (Ec - fcc / ecc)
            r_u = Ec / (Ec - fco / 0.002)
            f2 = fco * 2 * r_u / (r_u - 1 + 2 ** r_u)        # esfuerzo del concreto sin confinar en 2·εco
            self._cache_conf[clave] = (fcc, ecc, ecu, r_c, r_u, f2)
        return self._cache_conf[clave]

    def _sigma_c(self, eps, fco, conf):
        fcc, ecc, ecu, r_c, r_u, f2 = self._conf(fco)
        if eps <= 0:
            return 0.0
        if conf:
            if eps > ecu:
                return 0.0
            x = eps / ecc
            return fcc * x * r_c / (r_c - 1 + x ** r_c)
        if eps > 0.005:
            return 0.0
        if eps > 0.004:
            # tramo de descascaramiento: recta desde 2·εco = 0,004 hasta cero en εsp = 0,005 (Mander y otros, 1988)
            return f2 * (0.005 - eps) / (0.005 - 0.004)
        x = eps / 0.002
        return fco * x * r_u / (r_u - 1 + x ** r_u)

    @staticmethod
    def _acero(eps, fy):
        """Acero bilineal con endurecimiento del 1 % de Es (hasta εs = 0,10)."""
        ey = fy / ES
        a = abs(eps)
        if a <= ey:
            return ES * eps
        f = fy + 0.01 * ES * (min(a, 0.10) - ey)
        return f if eps > 0 else -f

    def _fuerzas(self, e0, phi, cara, fco, fy):
        """Con la deformación e0 de la cara comprimida y la curvatura phi: (P, M)."""
        P = M = 0.0
        for u, an, ac in self.fibras_mc:
            eps = e0 - phi * self.d(u, cara)
            if eps <= 0:
                continue
            F = (self._sigma_c(eps, fco, False) * an + (self._sigma_c(eps, fco, True) * ac if ac else 0.0)) * 1000
            P += F
            M += F * self.brazo(u, cara)
        for u, As in self.barras:
            eps = e0 - phi * self.d(u, cara)
            F = self._acero(eps, fy) * As * 1000
            P += F
            M += F * self.brazo(u, cara)
        return P, M

    def _equilibrio(self, phi, P_obj, cara, fco, fy):
        """e0 con P(e0, phi) = P_obj en la rama física (la menor e0 que equilibra): barrido y bisección, con la cara
        comprimida por debajo de la deformación última del núcleo (después P deja de crecer con e0)."""
        _, _, ecu, *_ = self._conf(fco)
        hi_max = max(ecu, 0.004) * 1.2
        lo = -0.003
        P_lo, _ = self._fuerzas(lo, phi, cara, fco, fy)
        if P_lo >= P_obj:
            return None
        n = 24
        hi = None
        for i in range(1, n + 1):
            e = lo + (hi_max - lo) * i / n
            Pe, _ = self._fuerzas(e, phi, cara, fco, fy)
            if Pe >= P_obj:
                hi = e
                break
            lo = e
        if hi is None:
            return None
        for _ in range(40):
            e0 = (lo + hi) / 2
            Pe, _ = self._fuerzas(e0, phi, cara, fco, fy)
            if Pe < P_obj:
                lo = e0
            else:
                hi = e0
        e0 = (lo + hi) / 2
        return e0, self._fuerzas(e0, phi, cara, fco, fy)[1]

    def fluencia(self, P_obj, cara, fco, fy):
        """Primera fluencia (My, φy): la barra más traccionada llega a εy o la cara comprimida a 0,002, lo que pase
        primero (Priestley y otros, 2007). Con la profundidad del eje neutro c: φ = εy/(dt − c) o φ = 0,002/c, y
        P(c) crece con c: bisección en c para cada criterio; se toma el de menor curvatura."""
        ey = fy / ES
        dt = self.d_traccion(cara)
        h = self.peralte()
        sol = []
        for crit in ('acero', 'concreto'):
            def estado(c):
                phi = ey / (dt - c) if crit == 'acero' else 0.002 / c
                return phi, phi * c
            # con el criterio del acero, c llega hasta donde la cara comprimida alcanza 0,002 (después manda el concreto)
            lo, hi = 1e-4 * h, (0.002 * dt / (ey + 0.002) if crit == 'acero' else 3 * h)
            Plo = self._fuerzas(estado(lo)[1], estado(lo)[0], cara, fco, fy)[0]
            Phi = self._fuerzas(estado(hi)[1], estado(hi)[0], cara, fco, fy)[0]
            if not (Plo <= P_obj <= Phi):
                continue
            for _ in range(50):
                c = (lo + hi) / 2
                phi, e0 = estado(c)
                if self._fuerzas(e0, phi, cara, fco, fy)[0] < P_obj:
                    lo = c
                else:
                    hi = c
            phi, e0 = estado((lo + hi) / 2)
            # el criterio vale si el otro no se alcanzó antes: εs ≤ εy y e0 ≤ 0,002
            es_t = phi * dt - e0
            if es_t <= ey * 1.0001 and e0 <= 0.002 * 1.0001:
                sol.append((phi, self._fuerzas(e0, phi, cara, fco, fy)[1]))
        if not sol:
            return 0.0, 0.0
        phi, M = min(sol)
        return M, phi

    def momento_curvatura(self, P_obj, cara, fco, fy, phi_y):
        """Puntos [φ, M] de 0 a la curvatura última (núcleo en εcu, barra en 0,06 o caída al 80 % del máximo)."""
        pts = [[0.0, 0.0]]
        Mmax = 0.0
        _, _, ecu, *_ = self._conf(fco)
        for f in (1.0, 2.0, 4.0, 7.0, 11.0, 16.0, 22.0, 30.0):
            phi = phi_y * f
            r_ = self._equilibrio(phi, P_obj, cara, fco, fy)
            if r_ is None:
                break
            e0, M = r_
            es_t = phi * self.d_traccion(cara) - e0
            if e0 > max(ecu, 0.004) or es_t > 0.06 or (Mmax > 0 and M < 0.8 * Mmax):
                break
            Mmax = max(Mmax, M)
            pts.append([phi, M])
        return pts


def rect_viga(b, h, b_ala):
    """Viga T: alma de ancho b hasta la loseta y ala de ancho efectivo b_ala en la loseta (u = 0 abajo)."""
    if b_ala <= b:
        return [(0.0, h, b)]
    return [(0.0, h - LOSETA, b), (h - LOSETA, h, b_ala)]


def area(nbar, num):
    return nbar * BARRAS[num][1] * 1e-6


def ld_traccion(num, sup=False, fc=FC, fy=FY):
    """Longitud de desarrollo en tracción, NSR-10 C.12.2.2 (separación y recubrimiento ≥ db y estribos mínimos):
    ld = fy·ψt·ψe/(2,1·λ·√f'c)·db para N.º 6 o menores y /(1,7·λ·√f'c) para N.º 7 o mayores; ψt = 1,3 en barras
    superiores; ≥ 300 mm."""
    db = BARRAS[num][0] / 1000
    psi_t = 1.3 if sup else 1.0
    k = 2.1 if num <= 6 else 1.7
    return max(fy * psi_t / (k * math.sqrt(fc)) * db, 0.300)


def ldh_sismico(num, fc=FC, fy=FY):
    """Gancho estándar de 90° en nudos sísmicos, NSR-10 C.21.7.5.1: ldh = fy·db/(5,4·√f'c) ≥ 8·db ≥ 150 mm."""
    db = BARRAS[num][0] / 1000
    return max(fy * db / (5.4 * math.sqrt(fc)), 8 * db, 0.150)


def traslapo(num, sup=False):
    """Empalme por traslapo clase B = 1,3·ld (NSR-10 C.12.15.1)."""
    return 1.3 * ld_traccion(num, sup)


# =================================================================================================================
# 6. Modelo pseudotridimensional (Wilson y Dovey, 1972): la misma idealización de web/js/sismo/modelo.js
# =================================================================================================================
class PorticoM:
    """Pórtico plano con un desplazamiento lateral por nivel y v, θ por nodo libre, condensados por complemento de
    Schur: K̂ = K_ll − K_lc·K_cc⁻¹·K_cl. Elemento de Timoshenko sobre la longitud flexible con brazos rígidos (E2),
    axial EA/L_f en columnas y muros; las vigas no se alargan (sus extremos están en el mismo diafragma)."""

    def __init__(self, P, niveles, resortes=()):
        self.P = P
        self.id = P['id']
        self.dir = 0 if P['dir'] == 'x' else 1
        self.c = P['c']
        nodos = P['nodos']
        pres = sorted({n['nivel'] for n in nodos if n['nivel'] > 0})
        self.niveles = pres
        self.nl = len(pres)
        lat = {k: i for i, k in enumerate(pres)}
        libres = sorted([n for n in nodos if n['nivel'] > 0], key=lambda n: (n['nivel'], n['s']))
        self.dof = {}
        nc = 0
        for n in libres:
            self.dof[n['id']] = (lat[n['nivel']], self.nl + nc, self.nl + nc + 1)
            nc += 2
        for n in nodos:
            if n['nivel'] == 0:
                self.dof[n['id']] = (-1, -1, -1)
        self.nc = nc
        self.n = self.nl + nc
        # filas de compatibilidad con el diafragma (índices globales 3(k−1) + {0, 1, 2})
        self.T = []
        for k in pres:
            nv = niveles[k - 1]
            xc, yc = nv['cm']
            if self.dir == 0:
                self.T.append(((3 * (k - 1), 1.0), (3 * (k - 1) + 2, -(self.c - yc))))
            else:
                self.T.append(((3 * (k - 1) + 1, 1.0), (3 * (k - 1) + 2, self.c - xc)))
        # elementos
        self.el = []
        K = ceros(self.n, self.n)
        for e in P['elementos']:
            ni, nj = P['idx'][e['i']], P['idx'][e['j']]
            di, dj = e['arms']
            Lf = e['Lf']
            iL = 1.0 / Lf
            if e['tipo'] == 'viga':
                A = [[0, iL, 1 + di * iL, 0, -iL, dj * iL], [0, iL, di * iL, 0, -iL, 1 + dj * iL], [0, 0, 0, 0, 0, 0]]
            else:
                A = [[-iL, 0, 1 + di * iL, iL, 0, dj * iL], [-iL, 0, di * iL, iL, 0, 1 + dj * iL], [0, -1, 0, 0, 1, 0]]
            sC = iL / e['GAv']
            f11 = Lf / (3 * e['EI']) + sC
            f12 = -Lf / (6 * e['EI']) + sC
            det = f11 * f11 - f12 * f12
            Kb = [[f11 / det, -f12 / det], [-f12 / det, f11 / det]]
            kax = e['EA'] / Lf if e['tipo'] != 'viga' else 0.0
            d = list(self.dof[e['i']]) + list(self.dof[e['j']])
            Ke = ceros(6, 6)
            for a in range(6):
                for b in range(6):
                    s = 0.0
                    for p in range(2):
                        for q in range(2):
                            s += A[p][a] * Kb[p][q] * A[q][b]
                    s += kax * A[2][a] * A[2][b]
                    Ke[a][b] = s
            for a in range(6):
                if d[a] < 0:
                    continue
                for b in range(6):
                    if d[b] >= 0:
                        K[d[a]][d[b]] += Ke[a][b]
            self.el.append({'e': e, 'A': A, 'Kb': Kb, 'kax': kax, 'd': d, 'Lf': Lf, 'di': di, 'dj': dj})
        # resortes laterales (mampostería no aislada) entre niveles consecutivos de la línea
        for rr in resortes:
            k = rr['nivel']
            a = lat.get(k)
            b = lat.get(k - 1) if k > 1 else None
            K[a][a] += rr['k']
            if b is not None:
                K[b][b] += rr['k']
                K[a][b] -= rr['k']
                K[b][a] -= rr['k']
        self.K = K
        nl = self.nl
        Kcc = [fila[nl:] for fila in K[nl:]]
        self.Kcl = [fila[:nl] for fila in K[nl:]]
        self.Klc = [fila[nl:] for fila in K[:nl]]
        self.Kll = [fila[:nl] for fila in K[:nl]]
        self.fcc = lu(Kcc)
        cols = [lu_resolver(self.fcc, [self.Kcl[i][j] for i in range(self.nc)]) for j in range(nl)]
        self.X = cols                                           # X[j] = K_cc⁻¹·K_cl[:, j]
        self.Kh = [[self.Kll[i][j] - sum(self.Klc[i][m] * cols[j][m] for m in range(self.nc)) for j in range(nl)]
                   for i in range(nl)]

    def cargas_gravedad(self, caso):
        """Vector de cargas (n) del caso 'D', 'L', 'Lr' o 'S' (sísmico: D + 0,25·L) con las cargas del vano llevadas a
        los nudos (θ0 de viga simplemente apoyada) y las cargas de los nodos."""
        Pv = ceros(self.n)
        for x in self.el:
            e = x['e']
            w = (e['w']['D'] + FRACCION_VIVA_MASA * e['w']['L']) if caso == 'S' else e['w'][caso]
            if e['tipo'] != 'viga' or w == 0:
                continue
            Lf, di, dj = x['Lf'], x['di'], x['dj']
            R = w * Lf / 2
            c0 = w * Lf ** 3 / (24 * e['EI'])
            th0 = (-c0, c0)
            loc = [0.0, -(R + w * di), -(R * di + w * di * di / 2), 0.0, -(R + w * dj), R * dj + w * dj * dj / 2]
            # + Aᵀ·Kb·θ0 (equilibrio con M = Kb·(A·u − θ0))
            Kt = [x['Kb'][0][0] * th0[0] + x['Kb'][0][1] * th0[1], x['Kb'][1][0] * th0[0] + x['Kb'][1][1] * th0[1]]
            for a in range(6):
                loc[a] += x['A'][0][a] * Kt[0] + x['A'][1][a] * Kt[1]
            for a in range(6):
                if x['d'][a] >= 0:
                    Pv[x['d'][a]] += loc[a]
        for nid, c in self.P['cargas'].items():
            val = (c['D'] + FRACCION_VIVA_MASA * c['L']) if caso == 'S' else c[caso]
            iv = self.dof[nid][1]
            if iv >= 0:
                Pv[iv] -= val
        return Pv

    def condensar_cargas(self, Pv):
        """Fuerza lateral equivalente de las cargas en los grados condensados: P̂ = P_l − K_lc·K_cc⁻¹·P_c."""
        nl = self.nl
        y = lu_resolver(self.fcc, Pv[nl:])
        return [Pv[i] - sum(self.Klc[i][m] * y[m] for m in range(self.nc)) for i in range(nl)]

    def lateral(self, U):
        return [sum(c * U[g] for g, c in fila) for fila in self.T]

    def recuperar(self, ul, Pv=None):
        """Desplazamientos completos del pórtico con los laterales ul (y las cargas Pv en los condensados)."""
        nl = self.nl
        rhs = [(Pv[nl + i] if Pv else 0.0) - sum(self.Kcl[i][j] * ul[j] for j in range(nl)) for i in range(self.nc)]
        uc = lu_resolver(self.fcc, rhs)
        return list(ul) + uc

    def fuerzas(self, u, caso=None):
        """Fuerzas de cada elemento: Mi, Mj (en las caras, antihorarios +), V (de la parte flexible, sin carga del vano),
        N (tracción +) y w del caso."""
        out = []
        for x in self.el:
            e = x['e']
            ue = [u[a] if a >= 0 else 0.0 for a in x['d']]
            q = [sum(x['A'][p][a] * ue[a] for a in range(6)) for p in range(3)]
            w = 0.0
            if caso and e['tipo'] == 'viga':
                w = (e['w']['D'] + FRACCION_VIVA_MASA * e['w']['L']) if caso == 'S' else e['w'][caso]
                c0 = w * x['Lf'] ** 3 / (24 * e['EI'])
                q[0] += c0
                q[1] -= c0
            Mi = x['Kb'][0][0] * q[0] + x['Kb'][0][1] * q[1]
            Mj = x['Kb'][1][0] * q[0] + x['Kb'][1][1] * q[1]
            N = x['kax'] * q[2]
            out.append({'Mi': Mi, 'Mj': Mj, 'V': (Mi + Mj) / x['Lf'], 'N': N, 'w': w})
        return out


class Modelo:
    """Ensamble de los pórticos en los diafragmas: K = Σ Tᵀ·K̂·T (3N × 3N), masa diagonal (m, m, Jz)."""

    def __init__(self, torre, filtro=None, resortes=None):
        self.niveles = torre['niveles']
        self.N = len(self.niveles)
        self.porticos = []
        for P in torre['porticos']:
            if filtro and not filtro(P):
                continue
            rs_ = [x for x in (resortes or []) if x['portico'] == P['id']]
            self.porticos.append(PorticoM(P, self.niveles, rs_))
        n = 3 * self.N
        self.K = ceros(n, n)
        for pm in self.porticos:
            for a, fa in enumerate(pm.T):
                for b, fb in enumerate(pm.T):
                    kab = pm.Kh[a][b]
                    for ga, ca in fa:
                        for gb, cb in fb:
                            self.K[ga][gb] += ca * kab * cb
        self.m = []
        for nv in self.niveles:
            self.m += [nv['masa_t'], nv['masa_t'], nv['Jz_t_m2']]
        self.fK = lu(self.K)

    def pdelta(self):
        """K_PΔ lineal por nivel con el peso y el centro de masa de cada nivel de encima (E14; contrato 7.4)."""
        n = 3 * self.N
        Kp = ceros(n, n)
        nv = self.niveles
        for k in range(1, self.N + 1):
            h = nv[k - 1]['h']
            for j in range(k, self.N + 1):
                W = nv[j - 1]['peso_kN']
                xj, yj = nv[j - 1]['cm']
                filas = []
                bx = ceros(n)
                bx[3 * (k - 1)] += 1
                bx[3 * (k - 1) + 2] += -(yj - nv[k - 1]['cm'][1])
                by = ceros(n)
                by[3 * (k - 1) + 1] += 1
                by[3 * (k - 1) + 2] += xj - nv[k - 1]['cm'][0]
                br = ceros(n)
                br[3 * (k - 1) + 2] += 1
                if k > 1:
                    bx[3 * (k - 2)] -= 1
                    bx[3 * (k - 2) + 2] -= -(yj - nv[k - 2]['cm'][1])
                    by[3 * (k - 2) + 1] -= 1
                    by[3 * (k - 2) + 2] -= xj - nv[k - 2]['cm'][0]
                    br[3 * (k - 2) + 2] -= 1
                r2 = nv[j - 1]['Jz_t_m2'] / nv[j - 1]['masa_t']
                for v, f in ((bx, 1.0), (by, 1.0), (br, r2)):
                    for a in range(n):
                        if v[a] == 0:
                            continue
                        for b in range(n):
                            if v[b] != 0:
                                Kp[a][b] -= f * W / h * v[a] * v[b]
        return Kp

    def modos(self, n_modos=12, pdelta=False):
        n = 3 * self.N
        K = [fila[:] for fila in self.K]
        if pdelta:
            Kp = self.pdelta()
            K = [[K[a][b] + Kp[a][b] for b in range(n)] for a in range(n)]
        s = [1 / math.sqrt(x) for x in self.m]
        Ks = [[s[a] * K[a][b] * s[b] for b in range(n)] for a in range(n)]
        lam, V = jacobi(Ks)
        orden = sorted(range(n), key=lambda i: lam[i])
        modos = []
        mt = self.m
        mtot = sum(mt[0::3])
        jtot = sum(mt[2::3])
        for i in orden[:n_modos]:
            phi = [V[a][i] * s[a] for a in range(n)]
            g = max(range(n), key=lambda a: abs(phi[a]))
            if phi[g] < 0:
                phi = [-x for x in phi]
            w = math.sqrt(max(lam[i], 1e-12))
            Gx = sum(mt[3 * k] * phi[3 * k] for k in range(self.N))
            Gy = sum(mt[3 * k + 1] * phi[3 * k + 1] for k in range(self.N))
            Gr = sum(mt[3 * k + 2] * phi[3 * k + 2] for k in range(self.N))
            modos.append({'w': w, 'T': 2 * math.pi / w, 'phi': phi, 'Gx': Gx, 'Gy': Gy, 'Gr': Gr,
                          'mx': Gx * Gx / mtot, 'my': Gy * Gy / mtot, 'mr': Gr * Gr / jtot})
        return modos

    def resolver(self, F):
        return lu_resolver(self.fK, F)

    def flexibilidad(self):
        n = 3 * self.N
        cols = [self.resolver([1.0 if a == j else 0.0 for a in range(n)]) for j in range(n)]
        return [[cols[j][i] for j in range(n)] for i in range(n)]


def rho_cqc(wi, wj, xi=XI):
    """Coeficiente de correlación de la combinación cuadrática completa (Der Kiureghian, 1981), igual amortiguamiento."""
    b = wj / wi
    return 8 * xi * xi * (1 + b) * b ** 1.5 / ((1 - b * b) ** 2 + 4 * xi * xi * b * (1 + b) ** 2)


def cqc(valores, modos, xi=XI):
    s = 0.0
    for i, vi in enumerate(valores):
        for j, vj in enumerate(valores):
            s += rho_cqc(modos[i]['w'], modos[j]['w'], xi) * vi * vj
    return math.sqrt(max(s, 0.0))


def desplazamiento_punto(U, niveles, k, x, y):
    """Desplazamiento (dx, dy) del punto (x, y) del diafragma k (1..N); k = 0 es el suelo."""
    if k == 0:
        return 0.0, 0.0
    xc, yc = niveles[k - 1]['cm']
    ux, uy, rz = U[3 * (k - 1)], U[3 * (k - 1) + 1], U[3 * (k - 1) + 2]
    return ux - (y - yc) * rz, uy + (x - xc) * rz


def deriva_punto(U, niveles, k, x, y):
    a = desplazamiento_punto(U, niveles, k, x, y)
    b = desplazamiento_punto(U, niveles, k - 1, x, y)
    return a[0] - b[0], a[1] - b[1]


# =================================================================================================================
# 7. Procedimiento NSR-10: respuestas, fuerza horizontal equivalente, modal espectral, derivas e irregularidades
# =================================================================================================================
class Respuestas:
    """Vector plano de respuestas de un estado de desplazamientos U (3N) del diafragma: fuerzas de cada elemento
    (Mi, Mj, V, N), derivas en los vértices de cada entrepiso (Δx, Δy), deriva de cada pórtico por entrepiso, cortante
    por entrepiso de pórticos y muros en x e y, deriva del centro de masa y U. Así la combinación modal (CQC) se aplica
    a cada número por separado, como pide la NSR-10 A.5.4.4 (por confirmar)."""

    def __init__(self, modelo):
        self.mod = modelo
        nv = modelo.niveles
        self.i_el = {}
        n = 0
        for pm in modelo.porticos:
            for x in pm.el:
                self.i_el[x['e']['id']] = n
                n += 4
        self.i_vert = {}
        for k in range(1, modelo.N + 1):
            for iv, (x, y) in enumerate(nv[k - 1]['contorno']):
                self.i_vert[(k, iv)] = n
                n += 2
        self.i_port = {}
        for pm in modelo.porticos:
            for k in pm.niveles:
                self.i_port[(pm.id, k)] = n
                n += 1
        self.i_piso = {}
        for k in range(1, modelo.N + 1):
            self.i_piso[k] = n
            n += 4
        self.i_cm = {}
        for k in range(1, modelo.N + 1):
            self.i_cm[k] = n
            n += 2
        self.i_U = n
        n += 3 * modelo.N
        self.n = n

    def calcular(self, U, Pv_por_portico=None, caso=None):
        mod = self.mod
        nv = mod.niveles
        v = [0.0] * self.n
        for pm in mod.porticos:
            ul = pm.lateral(U)
            Pv = Pv_por_portico.get(pm.id) if Pv_por_portico else None
            u = pm.recuperar(ul, Pv)
            fz = pm.fuerzas(u, caso)
            for x, f in zip(pm.el, fz):
                i = self.i_el[x['e']['id']]
                v[i:i + 4] = [f['Mi'], f['Mj'], f['V'], f['N']]
                e = x['e']
                if e['tipo'] != 'viga':
                    k = e['nivel']
                    j = self.i_piso[k] + (0 if pm.dir == 0 else 2) + (1 if e['tipo'] == 'muro_concreto' else 0)
                    v[j] += f['V']
            for a, k in enumerate(pm.niveles):
                abajo = pm.niveles.index(k - 1) if (k - 1) in pm.niveles else None
                v[self.i_port[(pm.id, k)]] = ul[a] - (ul[abajo] if abajo is not None else 0.0)
        for k in range(1, mod.N + 1):
            for iv, (x, y) in enumerate(nv[k - 1]['contorno']):
                dx, dy = deriva_punto(U, nv, k, x, y)
                i = self.i_vert[(k, iv)]
                v[i], v[i + 1] = dx, dy
            xc, yc = nv[k - 1]['cm']
            dx, dy = deriva_punto(U, nv, k, xc, yc)
            v[self.i_cm[k]], v[self.i_cm[k] + 1] = dx, dy
        v[self.i_U:self.i_U + 3 * mod.N] = list(U)
        return v


def combinar_cqc(vectores, modos, factores, xi=XI):
    """CQC de cada componente con los factores modales (Γ·Sd)."""
    nm = len(modos)
    rho = [[rho_cqc(modos[i]['w'], modos[j]['w'], xi) for j in range(nm)] for i in range(nm)]
    n = len(vectores[0])
    out = [0.0] * n
    for c in range(n):
        a = [vectores[i][c] * factores[i] for i in range(nm)]
        s = 0.0
        for i in range(nm):
            ai = a[i]
            if ai == 0.0:
                continue
            fila = rho[i]
            for j in range(nm):
                s += fila[j] * ai * a[j]
        out[c] = math.sqrt(max(s, 0.0))
    return out


def fhe(niveles, T, Sa_func, sentido):
    """Fuerza horizontal equivalente (NSR-10 A.4.3): Vs = Sa·W; Fx = Cvx·Vs, Cvx = mx·hx^k/Σ mi·hi^k; k = 1 si
    T ≤ 0,5 s, 0,75 + 0,5·T si 0,5 < T ≤ 2,5 s, 2 si T > 2,5 s (numerales por confirmar)."""
    Sa = Sa_func(T)
    W = sum(n['peso_kN'] for n in niveles)
    Vs = Sa * W
    kexp = 1.0 if T <= 0.5 else (0.75 + 0.5 * T if T <= 2.5 else 2.0)
    s = sum(n['masa_t'] * n['z'] ** kexp for n in niveles)
    F = [Vs * n['masa_t'] * n['z'] ** kexp / s for n in niveles]
    return {'T': T, 'Sa': Sa, 'W': W, 'Vs': Vs, 'k': kexp, 'F': F, 'sentido': sentido}


def dim_perpendicular(nv, sentido):
    xs = [p[0] for p in nv['contorno']]
    ys = [p[1] for p in nv['contorno']]
    return (max(ys) - min(ys)) if sentido == 'x' else (max(xs) - min(xs))


def vector_fuerzas(niveles, F, sentido, Mt=None):
    n = 3 * len(niveles)
    v = ceros(n)
    for k, f in enumerate(F):
        v[3 * k + (0 if sentido == 'x' else 1)] = f
        if Mt:
            v[3 * k + 2] = Mt[k]
    return v


def cociente_torsional(U, niveles, sentido):
    """Irregularidad torsional (NSR-10 Tabla A.3-6, 1aP/1bP): deriva máxima de un extremo / promedio de los dos
    extremos, medida en la dirección de la carga, en cada entrepiso."""
    out = []
    for k in range(1, len(niveles) + 1):
        cont = niveles[k - 1]['contorno']
        if sentido == 'x':
            ys = [p[1] for p in cont]
            pts = [(niveles[k - 1]['cm'][0], min(ys)), (niveles[k - 1]['cm'][0], max(ys))]
            d = [abs(deriva_punto(U, niveles, k, x, y)[0]) for x, y in pts]
        else:
            xs = [p[0] for p in cont]
            pts = [(min(xs), niveles[k - 1]['cm'][1]), (max(xs), niveles[k - 1]['cm'][1])]
            d = [abs(deriva_punto(U, niveles, k, x, y)[1]) for x, y in pts]
        prom = (d[0] + d[1]) / 2
        out.append({'entrepiso': k, 'extremos': pts, 'derivas_m': d, 'cociente': max(d) / prom if prom > 0 else 1.0})
    return out


def analizar(torre, R=None, resortes=None, xi_ud=0.02):
    """Análisis elástico completo con el modelo pseudotridimensional. Devuelve modos, FHE, modal escalado, derivas
    (diseño y umbral de daño), irregularidades, participación de pórticos y muros y las respuestas para el diseño."""
    nv = torre['niveles']
    mod = Modelo(torre)
    modos = mod.modos(12)
    modos_pd = mod.modos(12, pdelta=True)
    T1x = max(modos, key=lambda m: m['mx'])['T']
    T1y = max(modos, key=lambda m: m['my'])['T']
    Ta = CT_OTROS * H_TOTAL ** ALFA_OTROS
    res = Respuestas(mod)
    # ---- FHE con T ≤ Cu·Ta (A.4.2.1) ------------------------------------------------------------------------------
    f = {}
    for s, T1 in (('x', T1x), ('y', T1y)):
        f[s] = fhe(nv, min(T1, CU * Ta), espectro_nsr10, s)
    # casos estáticos: fuerzas en el centro de masa y momentos de torsión accidental (A.3.6.7: 5 % de la dimensión
    # perpendicular a la dirección en estudio)
    est = {}
    for s in ('x', 'y'):
        U = mod.resolver(vector_fuerzas(nv, f[s]['F'], s))
        Mt = [0.05 * dim_perpendicular(nv[k], s) * f[s]['F'][k] for k in range(len(nv))]
        Ut = mod.resolver(vector_fuerzas(nv, [0.0] * len(nv), s, Mt))
        est[s] = {'U': U, 'Ut': Ut, 'Mt': Mt}
    # irregularidad torsional con la FHE y la torsión accidental (el signo que da el mayor cociente)
    tors = {}
    for s in ('x', 'y'):
        U, Ut = est[s]['U'], est[s]['Ut']
        mas = cociente_torsional([a + b for a, b in zip(U, Ut)], nv, s)
        men = cociente_torsional([a - b for a, b in zip(U, Ut)], nv, s)
        tors[s] = [max(a, b, key=lambda q: q['cociente']) for a, b in zip(mas, men)]
        # amplificación de la torsión accidental (A.3.6.7.?, por confirmar): Ax = (δmax/(1,2·δprom))² entre 1 y 3
        for q in tors[s]:
            d = q['derivas_m']
            prom = (d[0] + d[1]) / 2
            q['Ax'] = min(max((max(d) / (1.2 * prom)) ** 2, 1.0), 3.0) if prom > 0 else 1.0
    for s in ('x', 'y'):
        Ax = [q['Ax'] for q in tors[s]]
        est[s]['Ax'] = Ax
        est[s]['Ut_amp'] = mod.resolver(vector_fuerzas(nv, [0.0] * len(nv), s,
                                                         [a * m for a, m in zip(Ax, est[s]['Mt'])]))
    # ---- modal espectral ------------------------------------------------------------------------------------------
    vec_modos = [res.calcular(m['phi']) for m in modos]
    modal = {}
    for s in ('x', 'y'):
        fac = [(m['Gx'] if s == 'x' else m['Gy']) * espectro_nsr10(m['T']) * G / m['w'] ** 2 for m in modos]
        modal[s] = combinar_cqc(vec_modos, modos, fac)
    # cortante basal modal y ajuste a ≥ 90 % de la FHE (estructura irregular, A.5.4.5)
    ajuste = {}
    for s, (j0, jm) in (('x', (0, 1)), ('y', (2, 3))):
        Vb = 0.0
        # cortante basal = Σ fuerzas de inercia: CQC del cortante de cada modo (no de la suma de valores absolutos)
        fac = [(m['Gx'] if s == 'x' else m['Gy']) * espectro_nsr10(m['T']) * G / m['w'] ** 2 for m in modos]
        cort = []
        for m, fc in zip(modos, fac):
            ii = 3 * 0
            Vm = sum(nv[k]['masa_t'] * m['w'] ** 2 * m['phi'][3 * k + (0 if s == 'x' else 1)] for k in range(len(nv)))
            cort.append(Vm)
        Vb = cqc([c * a for c, a in zip(cort, fac)], modos)
        ajuste[s] = {'V_modal': Vb, 'V_fhe': f[s]['Vs'], 'minimo': 0.90, 'factor': max(1.0, 0.90 * f[s]['Vs'] / Vb)}
    # ---- respuestas de diseño (sin reducir por R): modal ajustado + torsión accidental amplificada ------------------
    def con_torsion(s, amp=True):
        Ut = est[s]['Ut_amp'] if amp else est[s]['Ut']
        tv = res.calcular(Ut)
        a = ajuste[s]['factor']
        return [a * m + abs(t) for m, t in zip(modal[s], tv)]
    E = {s: con_torsion(s) for s in ('x', 'y')}
    # ---- derivas vectoriales en los vértices con 100 % + 30 % (A.3.6.3) ----------------------------------------------
    derivas = derivas_vectoriales(res, E, nv)
    # índice de estabilidad (A.6.2.3) con las derivas del centro de masa y el cortante del entrepiso
    estab = []
    for k in range(1, len(nv) + 1):
        P = nv[k - 1]['P_sobre_kN']
        h = nv[k - 1]['h']
        fila = {}
        for s, c in (('x', 0), ('y', 1)):
            d = E[s][res.i_cm[k] + c]
            V = E[s][res.i_piso[k] + 2 * c] + E[s][res.i_piso[k] + 2 * c + 1]
            fila[s] = P * d / (V * h) if V > 0 else 0.0
        estab.append(fila)
    # ---- umbral de daño (A.12): espectro de Ad con ξ = 2 %, sin R ni I, con la torsión accidental ------------------
    ud = umbral_de_dano(mod, res, modos, vec_modos, nv, xi_ud)
    out = {'modelo': mod, 'resp': res, 'modos': modos, 'modos_pd': modos_pd, 'T1x': T1x, 'T1y': T1y, 'Ta': Ta,
           'CuTa': CU * Ta, 'fhe': f, 'estaticos': est, 'torsion': tors, 'modal': modal, 'ajuste': ajuste, 'E': E,
           'derivas': derivas, 'estabilidad': estab, 'umbral': ud, 'vec_modos': vec_modos}
    if resortes:
        modm = Modelo(torre, resortes=resortes)
        resm = Respuestas(modm)
        modos_m = modm.modos(12)
        vm = [resm.calcular(m['phi']) for m in modos_m]
        out['umbral_mamposteria'] = umbral_de_dano(modm, resm, modos_m, vm, nv, xi_ud)
        out['modos_mamposteria'] = modos_m
    return out


def derivas_vectoriales(res, E, nv):
    """Máximo por entrepiso de √(Δx² + Δy²)/h en los vértices del contorno (E9) con las combinaciones 100 % + 30 %."""
    out = []
    for k in range(1, len(nv) + 1):
        h = nv[k - 1]['h']
        mejor = None
        for iv, (x, y) in enumerate(nv[k - 1]['contorno']):
            i = res.i_vert[(k, iv)]
            for a, b in ((1.0, 0.3), (0.3, 1.0)):
                dx = a * E['x'][i] + b * E['y'][i]
                dy = a * E['x'][i + 1] + b * E['y'][i + 1]
                d = math.hypot(dx, dy) / h
                if mejor is None or d > mejor['deriva']:
                    mejor = {'entrepiso': k, 'deriva': d, 'punto': [x, y], 'dx_m': dx, 'dy_m': dy,
                             'combinacion': '100 % x + 30 % y' if a == 1.0 else '30 % x + 100 % y'}
        out.append(mejor)
    return out


def umbral_de_dano(mod, res, modos, vec_modos, nv, xi):
    E = {}
    for s in ('x', 'y'):
        fac = [(m['Gx'] if s == 'x' else m['Gy']) * espectro_umbral(m['T']) * G / m['w'] ** 2 for m in modos]
        modal = combinar_cqc(vec_modos, modos, fac, xi)
        # torsión accidental con las fuerzas del umbral (distribución de la FHE con el período del modelo)
        T1 = max(modos, key=lambda m: m['mx' if s == 'x' else 'my'])['T']
        ff = fhe(nv, T1, espectro_umbral, s)
        Mt = [0.05 * dim_perpendicular(nv[k], s) * ff['F'][k] for k in range(len(nv))]
        tv = res.calcular(mod.resolver(vector_fuerzas(nv, [0.0] * len(nv), s, Mt)))
        E[s] = [m + abs(t) for m, t in zip(modal, tv)]
    return {'E': E, 'derivas': derivas_vectoriales(res, E, nv)}


def sistema_y_R(torre, A):
    """Paso 0 y R: fracción del cortante en los pórticos (modelo elástico, FHE sin torsión), sistema dual con la
    condición de diseñar los pórticos solos para el 25 % (A.3.2.1.4), irregularidades en planta (1aP/1bP) y en altura
    (1A, 2A, 3A; 5A se revisa después del diseño), redundancia (prueba de remoción, ASCE/SEI 7-16 12.3.4.2 a, a falta
    del texto de A.3.3.8) y R = φa·φp·φr·R0 (A.3.3.3)."""
    nv = torre['niveles']
    res, mod = A['resp'], A['modelo']
    part = {}
    for s, c in (('x', 0), ('y', 1)):
        v = res.calcular(A['estaticos'][s]['U'])
        filas = []
        for k in range(1, len(nv) + 1):
            i = res.i_piso[k] + 2 * c
            filas.append({'entrepiso': k, 'porticos_kN': v[i], 'muros_kN': v[i + 1], 'fraccion_porticos': v[i] / (v[i] + v[i + 1])})
        part[s] = filas
    # irregularidad torsional
    rt = {s: max(q['cociente'] for q in A['torsion'][s]) for s in ('x', 'y')}
    r_max = max(rt.values())
    phi_p = 0.8 if r_max > 1.4 else (0.9 if r_max > 1.2 else 1.0)
    tipo_p = '1bP' if r_max > 1.4 else ('1aP' if r_max > 1.2 else 'ninguna')
    # rigidez de entrepiso con la FHE (V/δ en el centro de masa) para 1A
    rig = {}
    for s, c in (('x', 0), ('y', 1)):
        v = res.calcular(A['estaticos'][s]['U'])
        filas = []
        for k in range(1, len(nv) + 1):
            V = v[res.i_piso[k] + 2 * c] + v[res.i_piso[k] + 2 * c + 1]
            d = v[res.i_cm[k] + c]
            filas.append(V / d if d else 0.0)
        rig[s] = filas
    irr_1A = []
    for s in ('x', 'y'):
        kk = rig[s]
        for k in range(len(kk) - 1):
            arriba = kk[k + 1:k + 4]
            r1 = kk[k] / kk[k + 1]
            r3 = kk[k] / (sum(arriba) / len(arriba))
            irr_1A.append({'sentido': s, 'entrepiso': k + 1, 'k_kN_m': kk[k], 'k_sobre_k_arriba': r1, 'k_sobre_prom3': r3,
                           'irregular': r1 < 0.7 or r3 < 0.8})
    masas = [n['masa_t'] for n in nv]
    irr_2A = [{'nivel': k + 1, 'cociente': max(masas[k] / masas[k - 1] if k > 0 else 0, masas[k] / masas[k + 1] if k < len(masas) - 1 else 0)}
              for k in range(len(masas) - 1)]                           # la cubierta no cuenta (A.3.3.5, por confirmar)
    geo = 42.0 / 30.0
    phi_a = 0.9 if geo > 1.3 else 1.0
    if any(x['irregular'] for x in irr_1A) or any(x['cociente'] > 1.5 for x in irr_2A):
        phi_a = min(phi_a, 0.9)
    # redundancia: quitar cada muro y ver (a) cuánto cortante de su entrepiso tomaba y (b) si la torsión se vuelve extrema
    redund = []
    for pid in torre['muros']:
        s = 'x' if torre['muros'][pid]['def']['dir'] == 'x' else 'y'
        c = 0 if s == 'x' else 1
        v = res.calcular(A['estaticos'][s]['U'])
        V_piso = v[res.i_piso[1] + 2 * c] + v[res.i_piso[1] + 2 * c + 1]
        pm = next(p_ for p_ in mod.porticos if p_.id == pid)
        V_muro = sum(f['V'] for x, f in zip(pm.el, pm.fuerzas(pm.recuperar(pm.lateral(A['estaticos'][s]['U'])))) if x['e']['nivel'] == 1)
        sin = Modelo(torre, filtro=lambda P, q=pid: P['id'] != q)
        U = sin.resolver(vector_fuerzas(nv, A['fhe'][s]['F'], s))
        Mt = [0.05 * dim_perpendicular(nv[k], s) * A['fhe'][s]['F'][k] for k in range(len(nv))]
        Ut = sin.resolver(vector_fuerzas(nv, [0.0] * len(nv), s, Mt))
        cq = max(max(q['cociente'] for q in cociente_torsional([a + b for a, b in zip(U, Ut)], nv, s)),
                 max(q['cociente'] for q in cociente_torsional([a - b for a, b in zip(U, Ut)], nv, s)))
        redund.append({'muro': pid, 'sentido': s, 'fraccion_cortante_entrepiso_1': abs(V_muro) / V_piso,
                       'cociente_torsional_sin_el': cq, 'cumple': abs(V_muro) / V_piso <= 0.33 and cq <= 1.4})
    phi_r = 1.0 if all(x['cumple'] for x in redund) else 0.75
    sis = SISTEMAS['dual']
    R = phi_a * phi_p * phi_r * sis['R0']
    return {'participacion': part, 'cociente_torsional': rt, 'phi_p': phi_p, 'tipo_p': tipo_p, 'rigidez_entrepiso': rig,
            'irr_1A': irr_1A, 'irr_2A': irr_2A, 'geometrica_3A': geo, 'phi_a': phi_a, 'redundancia': redund,
            'phi_r': phi_r, 'R0': sis['R0'], 'Omega0': sis['Omega0'], 'R': R, 'tabla': sis['tabla'], 'uso': sis['uso']}


def gravedad(torre, mod, res, caso):
    """Análisis estático lineal de un caso de gravedad ('D', 'L', 'Lr' o 'S' = D + 0,25·L) con el diafragma libre."""
    Pv = {pm.id: pm.cargas_gravedad(caso) for pm in mod.porticos}
    F = ceros(3 * mod.N)
    for pm in mod.porticos:
        Ph = pm.condensar_cargas(Pv[pm.id])
        for a, fila in enumerate(pm.T):
            for g, c in fila:
                F[g] += c * Ph[a]
    U = mod.resolver(F)
    return res.calcular(U, Pv, caso), U


def fuerzas_elemento(res, v, eid):
    i = res.i_el[eid]
    return v[i:i + 4]


# =================================================================================================================
# 8. Diseño de elementos (DMO, NSR-10 C.21.3 y C.21.4; generales de C.7, C.10, C.11 y C.12) y propiedades de rótula
# =================================================================================================================
COMBOS = [   # NSR-10 B.2.4.2 (resistencia): (nombre, D, L, Lr, E)
    ('1,4D', 1.4, 0.0, 0.0, 0.0),
    ('1,2D + 1,6L + 0,5Lr', 1.2, 1.6, 0.5, 0.0),
    ('1,2D + 1,0L + 1,6Lr', 1.2, 1.0, 1.6, 0.0),
    ('1,2D + 1,0L + 1,0E', 1.2, 1.0, 0.0, 1.0),
    ('0,9D + 1,0E', 0.9, 0.0, 0.0, 1.0),
]
SEP_LIBRE = max(0.025, 4 / 3 * AGREGADO_MM / 1000)       # NSR-10 C.7.6.1 y C.3.3.2: ≥ db, 25 mm y 4/3 del agregado


def filas_barras(n, num, b, rec, num_est):
    """Reparte n barras N.º num en filas dentro del ancho b; → [(n_fila, distancia del centro de la fila a la cara)]."""
    db = BARRAS[num][0] / 1000
    de = BARRAS[num_est][0] / 1000
    s = max(SEP_LIBRE, db)
    por_fila = max(2, int((b - 2 * rec - 2 * de + s) / (db + s)))
    filas = []
    resto = n
    y = rec + de + db / 2
    while resto > 0:
        k = min(resto, por_fila)
        filas.append((k, y))
        resto -= k
        y += db + max(0.025, db)
    return filas, por_fila


def seccion_viga(b, h, b_ala, sup, inf, rec=REC['viga'], num_est=3, malla_losa=0.0, nucleo=False, rho_s=0.0):
    """Sección de viga T con barras superiores sup = (n, num) e inferiores inf = (n, num) (más la malla de la loseta
    dentro del ala, mm²/m, para el momento negativo de C.21.6.2.2)."""
    barras = []
    for (n, num), arriba in ((sup, True), (inf, False)):
        if n == 0:
            continue
        filas, _ = filas_barras(n, num, b, rec, num_est)
        for k, yy in filas:
            barras.append((h - yy if arriba else yy, area(k, num)))
    if malla_losa and b_ala > b:
        barras.append((h - LOSETA / 2, malla_losa * 1e-6 * (b_ala - b)))
    rect = rect_viga(b, h, b_ala)
    nuc = []
    if nucleo:
        de = BARRAS[num_est][0] / 1000
        nuc = [(rec + de / 2, h - rec - de / 2, b - 2 * rec - de)]
    return Seccion(rect, barras, nuc, rho_s=rho_s, ke=K_PRIESTLEY['viga'])


def seccion_columna(b, n, num, rec=REC['columna'], num_est=4, rho_s=0.0):
    """Columna cuadrada b × b con n barras N.º num repartidas en las 4 caras (n múltiplo de 4); flexión en una dirección."""
    nf = n // 4 + 1                                   # barras por cara, con las esquinas
    db = BARRAS[num][0] / 1000
    de = BARRAS[num_est][0] / 1000
    y0 = rec + de + db / 2
    y1 = b - y0
    barras = [(y0, area(nf, num)), (y1, area(nf, num))]
    for i in range(1, nf - 1):
        barras.append((y0 + (y1 - y0) * i / (nf - 1), area(2, num)))
    nuc = [(rec + de / 2, b - rec - de / 2, b - 2 * rec - de)]
    return Seccion([(0.0, b, b)], barras, nuc, rho_s=rho_s, ke=K_PRIESTLEY['columna'])


def elegir_barras(b, As_req, rec, num_est, nmin=2, nums=(5, 6, 7, 8), max_filas=2):
    """La combinación (n, N.º) de menor área que cubre As_req en ≤ 2 filas (C.7.6); desempate: menos barras."""
    mejor = None
    for num in nums:
        n = max(nmin, math.ceil(As_req / (BARRAS[num][1] * 1e-6) - 1e-9))
        filas, por_fila = filas_barras(n, num, b, rec, num_est)
        if len(filas) > max_filas:
            continue
        A = area(n, num)
        clave = (round(A * (1 + 0.03 * n), 8), n)
        if mejor is None or clave < mejor[0]:
            mejor = (clave, (n, num))
    return mejor[1] if mejor else None


def as_requerida(Mu, b, d, fc=FC, fy=FY, phi=0.9):
    """As de una sección rectangular con refuerzo a tracción para Mu (kN·m): bloque de Whitney (C.10.2.7)."""
    if Mu <= 0:
        return 0.0
    Rn = Mu / (phi * b * d * d) / 1000                     # MPa
    t = 1 - 2 * Rn / (0.85 * fc)
    if t <= 0:
        return float('inf')
    rho = 0.85 * fc / fy * (1 - math.sqrt(t))
    return rho * b * d


def as_minima_viga(b, d):
    """NSR-10 C.10.5.1: As,min = max(0,25·√f'c/fy; 1,4/fy)·bw·d."""
    return max(0.25 * math.sqrt(FC) / FY, 1.4 / FY) * b * d


def interp2(x, x0, x1, y, y0, y1, tabla):
    """Interpolación bilineal en una tabla {(i, j): valores} con i ∈ {0, 1} (x0, x1) y j ∈ {0, 1} (y0, y1)."""
    tx = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
    ty = min(max((y - y0) / (y1 - y0), 0.0), 1.0)
    out = []
    for k in range(len(tabla[(0, 0)])):
        v0 = tabla[(0, 0)][k] * (1 - tx) + tabla[(1, 0)][k] * tx
        v1 = tabla[(0, 1)][k] * (1 - tx) + tabla[(1, 1)][k] * tx
        out.append(v0 * (1 - ty) + v1 * ty)
    return out


# ASCE/SEI 41-17, Tabla 10-7 (vigas controladas por flexión): (a, b, IO, LS, CP) en rad, por (ρ − ρ')/ρbal (≤ 0 o
# ≥ 0,5) y V/(bw·d·√f'c) (≤ 3 o ≥ 6 en unidades de psi = 0,249 o 0,498 en MPa); C = refuerzo transversal conforme
ASCE_VIGA = {
    'C': {(0, 0): (0.025, 0.05, 0.010, 0.025, 0.05), (0, 1): (0.02, 0.04, 0.005, 0.02, 0.04),
          (1, 0): (0.02, 0.03, 0.005, 0.02, 0.03), (1, 1): (0.015, 0.02, 0.005, 0.015, 0.02)},
    'NC': {(0, 0): (0.02, 0.03, 0.005, 0.02, 0.03), (0, 1): (0.01, 0.015, 0.0015, 0.01, 0.015),
           (1, 0): (0.01, 0.015, 0.005, 0.01, 0.015), (1, 1): (0.005, 0.01, 0.0015, 0.005, 0.01)},
}
# ASCE/SEI 41-17, Tabla 10-19 (muros controlados por flexión): por ((As − A's)·fy + P)/(tw·lw·f'c) (≤ 0,1 o ≥ 0,25),
# V/(tw·lw·√f'c) (≤ 4 o ≥ 6 en psi = 0,332 o 0,498 en MPa) y elemento de borde confinado
ASCE_MURO = {
    True: {(0, 0): (0.015, 0.020, 0.005, 0.015, 0.020), (0, 1): (0.010, 0.015, 0.004, 0.010, 0.015),
           (1, 0): (0.009, 0.012, 0.003, 0.009, 0.012), (1, 1): (0.005, 0.010, 0.0015, 0.005, 0.010)},
    False: {(0, 0): (0.008, 0.015, 0.002, 0.008, 0.015), (0, 1): (0.006, 0.010, 0.002, 0.006, 0.010),
            (1, 0): (0.003, 0.005, 0.001, 0.003, 0.005), (1, 1): (0.002, 0.004, 0.001, 0.002, 0.004)},
}
PSI = 12.04                    # V/(b·d·√f'c): unidades de psi = 12,04 × unidades de MPa (√145,04)


def asce_viga(rho, rho_p, v_mpa, conforme):
    rho_bal = 0.85 * BETA1 * FC / FY * 600 / (600 + FY)
    x = (rho - rho_p) / rho_bal
    return interp2(x, 0.0, 0.5, v_mpa * PSI, 3.0, 6.0, ASCE_VIGA['C' if conforme else 'NC'])


def asce_columna(N_UD, Ag, rho_t, VyE_VcolOE):
    """ASCE/SEI 41-17, Tabla 10-8 (columnas rectangulares, ecuaciones de modelado; Ghannoum y Matamoros, 2014):
    a = 0,042 − 0,043·N/(Ag·f'cE) + 0,63·ρt − 0,023·VyE/VColOE ≥ 0; b = 0,5/(5 + N/(0,8·Ag·f'cE)·(1/ρt)·(f'cE/fytE)) − 0,01 ≥ a;
    IO = 0,15·a ≤ 0,005; LS = 0,5·b; CP = 0,7·b (ρt ≤ 0,0175)."""
    nu = min(max(N_UD / (Ag * FCE * 1000), 0.0), 0.5)
    rt = min(rho_t, 0.0175)
    a = max(0.042 - 0.043 * nu + 0.63 * rt - 0.023 * min(VyE_VcolOE, 1.0), 0.0)
    b = max(0.5 / (5 + nu / 0.8 / rt * FCE / FYE) - 0.01, a)
    return a, b, min(0.15 * a, 0.005), 0.5 * b, 0.7 * b


def haselton(nu, rho_sh, fc=FC):
    """Haselton, Liel, Taylor Lange y Deierlein (2016), ACI Structural Journal 113(6): θcap,pl y Mc/My (f'c en MPa)."""
    th = 0.13 * (1 + 0.55 * 1.0) * 0.13 ** nu * (0.02 + 40 * rho_sh) ** 0.65 * 0.57 ** (0.01 * fc)
    mc = 1.25 * 0.89 ** nu * 0.91 ** (0.01 * fc)
    return th, mc


def estribos(Ve, Vc, d, s_max, num=3, ramas=2, fyt=FY, phi=0.75):
    """Separación de estribos para Ve (kN): Av·fyt·d/s ≥ Ve/φ − Vc (C.11.4.7.2), redondeada a 0,025 m hacia abajo,
    con s ≤ s_max. Si no alcanza con 0,075 m, sube a N.º 4 y luego agrega ramas."""
    for n_, r_ in ((num, ramas), (4, ramas), (4, ramas + 1), (4, ramas + 2), (4, ramas + 4)):
        Av = r_ * BARRAS[n_][1] * 1e-6
        Vs_req = max(Ve / phi - Vc, 0.0)
        s = s_max if Vs_req <= 0 else min(s_max, Av * fyt * 1000 * d / Vs_req)
        s = math.floor(s / 0.025 + 1e-9) * 0.025
        if s >= (0.10 if n_ == 3 else 0.075):
            return {'num': n_, 'ramas': r_, 's': round(s, 3), 'Av': Av}
    return {'num': 4, 'ramas': ramas + 4, 's': 0.075, 'Av': (ramas + 4) * BARRAS[4][1] * 1e-6, 'no_alcanza': True}


def capacidades(sec, P, cara, rho_s):
    """Propiedades de una sección para la rótula (E16): nominales (My con momento-curvatura de Mander y f'c, Mn y φMn
    con Whitney y εcu = 0,003, Mpr con 1,25·fy) y esperadas (f'cE = 1,5·f'c, fyE = 1,25·fy; φ = 1)."""
    Mn, c, et, phi = sec.resistencia(P, cara)
    Mpr, *_ = sec.resistencia(P, cara, FC, FY_PR)
    Mn_e, *_ = sec.resistencia(P, cara, FCE, FYE)
    My, phi_y = sec.fluencia(P, cara, FC, FY)
    My_e, phi_ye = sec.fluencia(P, cara, FCE, FYE)
    mc = sec.momento_curvatura(P, cara, FCE, FYE, phi_ye)
    mc_n = sec.momento_curvatura(P, cara, FC, FY, phi_y)
    return {'Mn': Mn, 'phiMn': phi * Mn, 'phi': phi, 'c': c, 'et': et, 'Mpr': Mpr, 'Mn_e': Mn_e, 'My': My, 'phi_y': phi_y,
            'My_e': My_e, 'phi_ye': phi_ye, 'mc_e': mc, 'mc': mc_n}


def b_ala(b, borde, Lf):
    """Ancho efectivo del ala (NSR-10 C.8.12.2 y C.8.12.3) con la loseta de 0,05 m como ala."""
    if borde:
        return b + min(Lf / 12, 6 * LOSETA, 3.0)
    return min(b + 2 * min(8 * LOSETA, 3.0), b + Lf / 4)


MALLA_LOSETA = MALLA[5.0][0] / 0.20 * 1000 / 1000      # mm²/m: malla de Ø5 mm cada 0,20 m en la loseta


def envolvente_viga(e, g, Ed):
    """Combinaciones de una viga: lista de (nombre, m_i, m_j, w, V_i, V_j) con la parte sísmica en los dos sentidos
    (en un pórtico que se desplaza, los momentos sísmicos de los dos extremos tienen el mismo signo antihorario)."""
    Lf = e['Lf']
    out = []
    for nombre, cD, cL, cLr, cE in COMBOS:
        Mi = cD * g['D'][0] + cL * g['L'][0] + cLr * g['Lr'][0]
        Mj = cD * g['D'][1] + cL * g['L'][1] + cLr * g['Lr'][1]
        w = cD * e['w']['D'] + cL * e['w']['L'] + cLr * e['w']['Lr']
        for sgn in ((1, -1) if cE else (0,)):
            Mi_t = Mi + sgn * cE * Ed[0]
            Mj_t = Mj + sgn * cE * Ed[1]
            V = (Mi_t + Mj_t) / Lf
            out.append((nombre + ('' if not cE else (' (+)' if sgn > 0 else ' (−)')), -Mi_t, Mj_t, w, V - w * Lf / 2, V + w * Lf / 2))
    return out


def momento_en(c, x, Lf):
    _, mi, mj, w, _, _ = c
    return mi + (mj - mi) * x / Lf + w * x * (Lf - x) / 2


def disenar_viga(e, g, Ed, borde):
    """Diseño de una viga DMO (NSR-10 C.21.3.4, C.10, C.11, C.12): refuerzo longitudinal superior (igual en los dos
    apoyos) e inferior, cortes de los bastones con la envolvente de momentos, estribos con el cortante por capacidad
    (Mpr, C.21.5.4.1, del lado seguro frente a C.21.3.3) y propiedades de la sección."""
    b, h, Lf = e['b'], e['h'], e['Lf']
    rec = REC['viga']
    combos = envolvente_viga(e, g, Ed)
    n_pts = 41
    xs = [Lf * i / (n_pts - 1) for i in range(n_pts)]
    m_env_neg = [max(0.0, max(-momento_en(c, x, Lf) for c in combos)) for x in xs]
    m_env_pos = [max(0.0, max(momento_en(c, x, Lf) for c in combos)) for x in xs]
    Mneg = max(m_env_neg[0], m_env_neg[-1])
    Mpos_cara = max(m_env_pos[0], m_env_pos[-1])
    Mpos_vano = max(m_env_pos)
    bf = b_ala(b, borde, Lf)
    num_e = 3

    def d_de(n, num):
        filas, _ = filas_barras(n, num, b, rec, num_e)
        At = sum(k for k, _ in filas)
        return h - sum(k * y for k, y in filas) / At

    # superior (momento negativo en las caras): mismo armado en los dos apoyos
    sup = None
    As_req = max(as_requerida(Mneg, b, h - 0.07), as_minima_viga(b, h - 0.07))
    sup = elegir_barras(b, As_req, rec, num_e)
    for _ in range(20):
        sec = seccion_viga(b, h, b, sup, (2, 5), rec)
        Mn, c, et, phi = sec.resistencia(0.0, 'inf')
        if phi * Mn >= Mneg and area(*sup) >= as_minima_viga(b, d_de(*sup)):
            break
        sup = elegir_barras(b, area(*sup) * 1.05 + 1e-6, rec, num_e)
    # inferior en las caras: M+ ≥ M−/3 en la cara (C.21.3.4.1) y As,min
    Mn_sup = phi * Mn
    req_inf = max(Mpos_cara, Mn_sup / 3)
    inf = elegir_barras(b, max(as_requerida(req_inf, b, h - 0.07), as_minima_viga(b, h - 0.07)), rec, num_e)
    for _ in range(20):
        sec = seccion_viga(b, h, bf, sup, inf, rec)
        Mn_p, c, et, phi_p = sec.resistencia(0.0, 'sup')
        if phi_p * Mn_p >= req_inf and area(*inf) >= as_minima_viga(b, d_de(*inf)):
            break
        inf = elegir_barras(b, area(*inf) * 1.05 + 1e-6, rec, num_e)
    # corridas inferiores: todas las barras inferiores de las caras; corridas superiores: desde 2 barras (C.21.3.4.1:
    # en toda sección ≥ 1/5 de la resistencia máxima en las caras) y se agregan mientras un bastón pase de 1/3 de la luz
    corr_inf = inf
    db_sup = BARRAS[sup[1]][0] / 1000
    db_inf = BARRAS[inf[1]][0] / 1000
    d = d_de(*sup)

    def corte_desde(lado, phiMn_c):
        """Largo del bastón desde la cara: último punto con demanda negativa mayor que φMn de las corridas, más
        max(d, 12·db) (C.12.10.3), y al menos ld de barra superior (C.12.10.4)."""
        idx = range(n_pts) if lado == 'i' else range(n_pts - 1, -1, -1)
        ult = 0.0
        for i in idx:
            x = xs[i] if lado == 'i' else Lf - xs[i]
            if m_env_neg[i] > phiMn_c:
                ult = max(ult, x)
        largo = ult + max(d, 12 * db_sup)
        return min(max(largo, ld_traccion(sup[1], True)), Lf)

    L_i = L_j = 0.0
    for nc in range(2, sup[0] + 1):
        corr_sup = (nc, sup[1])
        phiMn_corr_neg = 0.9 * seccion_viga(b, h, b, corr_sup, corr_inf, rec).resistencia(0.0, 'inf')[0]
        if nc == sup[0]:
            L_i = L_j = 0.0
            break
        if phiMn_corr_neg < Mn_sup / 5:
            continue
        L_i, L_j = corte_desde('i', phiMn_corr_neg), corte_desde('j', phiMn_corr_neg)
        if max(L_i, L_j) <= Lf / 3:
            break
    phiMn_corr_pos = 0.9 * seccion_viga(b, h, bf, corr_sup, corr_inf, rec).resistencia(0.0, 'sup')[0]
    # bastones inferiores en el centro si el momento positivo del vano supera a las corridas
    extra_inf = None
    if Mpos_vano > phiMn_corr_pos:
        n_extra = 0
        for k in range(1, 8):
            tot = (inf[0] + k, inf[1])
            if 0.9 * seccion_viga(b, h, bf, corr_sup, tot, rec).resistencia(0.0, 'sup')[0] >= Mpos_vano:
                n_extra = k
                break
        extra_inf = (n_extra or 2, inf[1])
    vano_inf = None
    if extra_inf:
        dentro = [x for x, m in zip(xs, m_env_pos) if m > phiMn_corr_pos]
        x1 = max(min(dentro) - max(d, 12 * db_inf), 0.0)
        x2 = min(max(dentro) + max(d, 12 * db_inf), Lf)
        if x2 - x1 < 2 * ld_traccion(inf[1]):
            cen = (x1 + x2) / 2
            x1, x2 = max(cen - ld_traccion(inf[1]), 0.0), min(cen + ld_traccion(inf[1]), Lf)
        vano_inf = (x1, x2)
    # capacidades en las caras (con la malla de la loseta en el ala para el momento negativo, C.21.6.2.2)
    sec_neg = seccion_viga(b, h, bf, sup, inf, rec, malla_losa=MALLA_LOSETA)
    sec_pos = seccion_viga(b, h, bf, sup, inf, rec)
    # estribos: cortante por capacidad con Mpr en las dos caras y la carga 1,2D + 1,0L (C.21.5.4.1)
    Mpr_neg = sec_neg.resistencia(0.0, 'inf', FC, FY_PR)[0]
    Mpr_pos = sec_pos.resistencia(0.0, 'sup', FC, FY_PR)[0]
    wu = 1.2 * e['w']['D'] + 1.0 * e['w']['L'] + 0.5 * e['w']['Lr']
    Vg = wu * Lf / 2
    Vmpr = (Mpr_neg + Mpr_pos) / Lf
    Ve = Vmpr + Vg
    Vu_analisis = max(max(abs(c[4]), abs(c[5])) for c in combos)
    Ve = max(Ve, Vu_analisis)
    Vc = 0.17 * math.sqrt(FC) * b * d * 1000
    Vc_hz = 0.0 if Vmpr >= 0.5 * Ve else Vc                          # C.21.5.4.2
    db_min = min(db_sup, db_inf)
    s_hz_max = min(d / 4, 8 * db_min, 24 * BARRAS[3][0] / 1000, 0.300)
    est_hz = estribos(Ve, Vc_hz, d, s_hz_max, 3, 2)
    if est_hz['num'] == 4:
        s_hz_max = min(d / 4, 8 * db_min, 24 * BARRAS[4][0] / 1000, 0.300)
        est_hz = estribos(Ve, Vc_hz, d, s_hz_max, 4, est_hz['ramas'])
    Vu_c = max(Ve - wu * 2 * h, 0.0)
    est_c = estribos(Vu_c, Vc, d, d / 2, est_hz['num'], est_hz['ramas'])
    Vs_max = 0.66 * math.sqrt(FC) * b * d * 1000                       # C.11.4.7.9
    Vs_hz = est_hz['Av'] * FY * 1000 * d / est_hz['s']
    return {
        'b': b, 'h': h, 'Lf': Lf, 'b_ala': bf, 'd': d, 'sup': sup, 'inf': inf, 'corr_sup': corr_sup, 'extra_inf': extra_inf,
        'L_baston_i': L_i, 'L_baston_j': L_j, 'vano_inf': vano_inf, 'Mneg_u': Mneg, 'Mpos_u': Mpos_cara, 'Mvano_u': Mpos_vano,
        'phiMn_neg': 0.9 * sec_neg.resistencia(0.0, 'inf')[0], 'phiMn_pos': 0.9 * sec_pos.resistencia(0.0, 'sup')[0],
        'Mn_neg': sec_neg.resistencia(0.0, 'inf')[0], 'Mn_pos': sec_pos.resistencia(0.0, 'sup')[0],
        'Mpr_neg': Mpr_neg, 'Mpr_pos': Mpr_pos, 'Ve': Ve, 'Vmpr': Vmpr, 'Vg': Vg, 'Vc': Vc, 'Vc_hz': Vc_hz,
        'est_hz': est_hz, 'est_c': est_c, 'zona_conf': 2 * h, 'Vs_hz': Vs_hz, 'Vs_max': Vs_max,
        'phiVn_hz': 0.75 * (Vc_hz + Vs_hz), 'sec_neg': sec_neg, 'sec_pos': sec_pos, 'wu': wu,
        'rho_sup': area(*sup) / (b * d), 'rho_inf': area(*inf) / (b * d),
    }


ALFA_BRESLER = 1.16      # contorno de carga de Bresler (1960) con β = 0,55, el extremo conservador de la PCA (Parme y otros, 1966)
CANDIDATOS_COL = sorted([(n, num) for n in (12, 16, 20, 24, 28) for num in (6, 7, 8)], key=lambda x: (area(*x), x[0]))


def columna_cabe(b, n, num, rec=REC['columna']):
    """Separación libre entre barras longitudinales ≥ max(1,5·db; 40 mm) (NSR-10 C.7.6.3)."""
    nf = n // 4 + 1
    db = BARRAS[num][0] / 1000
    libre = (b - 2 * (rec + BARRAS[4][0] / 1000) - db) / (nf - 1) - db
    return libre >= max(1.5 * db, 0.040)


def disenar_columna(fis, copias, demandas, nudo_sup, b, col_arriba, cache):
    """Columna física (sus copias X e Y del modelo): refuerzo longitudinal mínimo que cumple flexocompresión biaxial
    (contorno de carga), 1 % ≤ ρ ≤ 4 % y columna fuerte-viga débil ΣMnc ≥ 1,2·ΣMnb en el nudo de arriba (con la columna
    de arriba ya diseñada: se diseña de arriba hacia abajo); estribos DMO y cortante por capacidad.
    demandas: lista de (Pu, Mux, Muy) mayoradas (compresión +). nudo_sup: {'X': ΣMnb, 'Y': ΣMnb} (o None)."""
    Ag = b * b
    Pmin = min(d[0] for d in demandas)
    Pmax = max(d[0] for d in demandas)
    elegido = None
    revisados = []
    for n, num in CANDIDATOS_COL:
        rho = area(n, num) / Ag
        if rho < 0.01 - 1e-9 or rho > 0.04 or not columna_cabe(b, n, num):
            continue
        clave = (b, n, num)
        if clave not in cache:
            cache[clave] = seccion_columna(b, n, num)
        sec = cache[clave]
        ok = True
        peor = 0.0
        for Pu, Mx, My in demandas:
            pm = sec.phiMn_rapido(Pu, 'sup')
            if pm is None or pm <= 0:
                ok = False
                peor = 9.9
                break
            u = (abs(Mx) / pm) ** ALFA_BRESLER + (abs(My) / pm) ** ALFA_BRESLER
            peor = max(peor, u)
        if peor > 1.0:
            ok = False
        # columna fuerte-viga débil en el nudo de arriba (Mnc con φ = 1 y la carga axial que da el menor Mn)
        Mnc = min(sec.Mn_rapido(Pmin, 'sup'), sec.Mn_rapido(Pmax, 'sup'))
        cvd = {}
        if nudo_sup:
            for plano, sMnb in nudo_sup.items():
                if sMnb is None:
                    continue
                Mnc_arr = col_arriba[plano] if col_arriba and col_arriba.get(plano) is not None else 0.0
                cvd[plano] = (Mnc + Mnc_arr) / sMnb if sMnb > 0 else 99.0
                if Mnc_arr > 0 and cvd[plano] < 1.2:
                    ok = False
        revisados.append((n, num, round(peor, 3), {k: round(v, 3) for k, v in cvd.items()}))
        if ok:
            elegido = (n, num, sec, peor, Mnc, cvd)
            break
    return elegido, revisados


def seccion_muro_refuerzo(mu, t, cortina, borde_i, borde_j, col_barras=None, rec=REC['muro']):
    """Sección del muro con su refuerzo: dos cortinas verticales (num, s) en alma y aletas, barras de borde en los dos
    extremos del alma (n, num) dentro de 0,6 m, y las barras de la columna de borde (MX)."""
    rect = mu['rect']
    num_c, s_c = cortina
    barras = []
    for u0, u1, w in rect:
        es_columna = col_barras and abs(w - mu['def'].get('col_borde_b', -1)) < 1e-9 and u0 > 8.0
        if es_columna:
            n, num = col_barras
            nf = n // 4 + 1
            db = BARRAS[num][0] / 1000
            y0 = u0 + REC['columna'] + BARRAS[4][0] / 1000 + db / 2
            y1 = u1 - REC['columna'] - BARRAS[4][0] / 1000 - db / 2
            barras.append((y0, area(nf, num)))
            barras.append((y1, area(nf, num)))
            for i in range(1, nf - 1):
                barras.append((y0 + (y1 - y0) * i / (nf - 1), area(2, num)))
            continue
        largo = u1 - u0
        if w > t + 1e-9:
            # aleta: las cortinas corren a lo largo del ancho w (perpendicular al plano); en u es una franja delgada
            n_barras = 2 * max(2, int(w / s_c) + 1)
            barras.append(((u0 + u1) / 2, area(n_barras, num_c)))
        else:
            nb = max(2, int(largo / s_c) + 1)
            for i in range(nb):
                barras.append((u0 + rec + (largo - 2 * rec) * i / max(nb - 1, 1), area(2, num_c)))
    # barras de borde en los extremos del alma (junto a la aleta, o en el extremo libre)
    alma = [x for x in rect if abs(x[2] - t) < 1e-9]
    ua0 = min(x[0] for x in alma)
    ua1 = max(x[1] for x in alma)
    for (n, num), uu in ((borde_i, ua0 + 0.10), (borde_j, ua1 - 0.10)):
        if n:
            barras.append((uu, area(n, num)))
    nuc = []
    return Seccion(rect, barras, nuc, rho_s=0.0, ke=K_PRIESTLEY['muro'])


def cortina_muro(t):
    """Dos cortinas de refuerzo distribuido con ρ ≥ 0,0025 en las dos direcciones (NSR-10 C.21.9.2.1; dos cortinas
    por espesor ≥ 0,20 m y C.14.3.4) y separación ≤ 3t y ≤ 0,45 m."""
    for num, s in ((3, 0.20), (4, 0.30), (4, 0.25), (4, 0.20), (5, 0.20), (5, 0.15)):
        if 2 * BARRAS[num][1] * 1e-6 / (s * t) >= 0.0025 and s <= min(3 * t, 0.45):
            return (num, s)
    return (5, 0.15)


def disenar_muro(mu, niveles_e, t, col_barras, delta_u, R):
    """Muro DMO (NSR-10 C.21.9 con los criterios DMO del capítulo; numerales por confirmar): por nivel, barras de borde
    para φMn ≥ Mu en los dos sentidos con la carga axial mayorada; cortante por capacidad: el que corresponde a la
    sobrerresistencia a flexión de la base, Ve = Ωv·Vu con Ωv = Mpr/Mu (≥ 1, sin pasar del cortante elástico R·Vu), con
    φ = 0,75 (más exigente que C.21.9.4, que diseña con Vu); la amplificación dinámica de modos altos ωv = 0,9 + ns/10 de
    ACI 318-19 18.10.3.1.2 se informa. Elementos de borde por desplazamiento (C.21.9.6.2) y por esfuerzo (C.21.9.6.3,
    informativo).
    niveles_e: por nivel k, dict con Pu_max, Pu_min (compresión +), Mu (kN·m, en la base del tramo), Vu, Pg (D + 0,25·L)."""
    m = mu['def']
    cort = cortina_muro(t)
    lw = mu['u1'] - mu['u0']
    hw = H_TOTAL
    alma = [x for x in mu['rect'] if abs(x[2] - t) < 1e-9]
    l_alma = sum(x[1] - x[0] for x in alma)
    Acv = mu['Av'] if m['forma'] != 'R' else t * lw
    out = []
    Omega_v = None
    for k, dem in enumerate(niveles_e, start=1):
        borde = {'i': (0, 5), 'j': (0, 5)}
        sec = None
        for intento in range(40):
            sec = seccion_muro_refuerzo(mu, t, cort, borde['i'], borde['j'], col_barras)
            falta = []
            for cara, lado in (('sup', 'i'), ('inf', 'j')):
                # cara 'sup' comprimida = borde de mayor u comprimido → tracción en el borde i (menor u)
                for Pu in (dem['Pu_max'], dem['Pu_min']):
                    pm = sec.phiMn_rapido(Pu, cara)
                    if pm is None or pm < dem['Mu']:
                        falta.append(lado)
            if not falta:
                break
            for lado in sorted(set(falta)):
                n, num = borde[lado]
                if n < 4:
                    borde[lado] = (n + 2, num)
                elif num < 8:
                    borde[lado] = (n, num + 1)
                else:
                    borde[lado] = (n + 2, num)
        cap_pos = sec.resistencia(dem['Pg'], 'sup')
        cap_neg = sec.resistencia(dem['Pg'], 'inf')
        Mpr = max(sec.resistencia(dem['Pu_max'], c_, FC, FY_PR)[0] for c_ in ('sup', 'inf'))
        if k == 1:
            Omega_v = min(max(1.0, Mpr / dem['Mu']), R) if dem['Mu'] > 0 else R
        omega_v = 0.9 + NIV / 10                                     # ACI 318-19 18.10.3.1.2, ns = 4 ≤ 6
        Ve = Omega_v * dem['Vu']
        Ve_din = min(Omega_v * omega_v, R) * dem['Vu']
        ac = 0.25 if hw / lw <= 1.5 else (0.17 if hw / lw >= 2.0 else 0.25 - 0.08 * (hw / lw - 1.5) / 0.5)
        rho_t_req = max((Ve / 0.75 / (Acv * 1000) - ac * math.sqrt(FC)) / FY, 0.0025)
        cort_h = cort
        for num, s in ((3, 0.20), (4, 0.30), (4, 0.25), (4, 0.20), (4, 0.15), (5, 0.15), (5, 0.10)):
            if 2 * BARRAS[num][1] * 1e-6 / (s * t) >= rho_t_req and s <= min(3 * t, 0.45):
                cort_h = (num, s)
                break
        rho_t = 2 * BARRAS[cort_h[0]][1] * 1e-6 / (cort_h[1] * t)
        Vn = Acv * 1000 * (ac * math.sqrt(FC) + rho_t * FY)
        Vn_max = 0.83 * math.sqrt(FC) * Acv * 1000                      # C.21.9.4.4
        Vn_e = Acv * 1000 * (ac * math.sqrt(FCE) + rho_t * FYE)
        # elementos de borde (base): c con la mayor compresión y Mn; δu de diseño en la cubierta del muro
        c_max = max(sec.resistencia(dem['Pu_max'], c_)[1] for c_ in ('sup', 'inf'))
        lim = lw / (600 * max(delta_u / hw, 0.007))
        req_borde = k == 1 and c_max >= lim
        sigma = dem['Pu_max'] / (mu['A'] * 1000) + dem['Mu'] * (lw / 2) / (mu['I'] * 1000)
        out.append({'nivel': k, 'borde_i': borde['i'], 'borde_j': borde['j'], 'cortina_v': cort, 'cortina_h': cort_h,
                    'sec': sec, 'Mn_pos': cap_pos[0], 'Mn_neg': cap_neg[0], 'phiMn_pos': cap_pos[3] * cap_pos[0],
                    'phiMn_neg': cap_neg[3] * cap_neg[0], 'Mpr': Mpr, 'Mu': dem['Mu'], 'Vu': dem['Vu'], 'Ve': Ve,
                    'Omega_v': Omega_v, 'omega_v': omega_v, 'Ve_din': Ve_din, 'alfa_c': ac, 'rho_t': rho_t, 'Vn': Vn, 'phiVn': 0.75 * Vn,
                    'Vn_max': Vn_max, 'Vn_e': Vn_e, 'c_max': c_max, 'c_lim': lim, 'requiere_borde': req_borde,
                    'sigma_MPa': sigma, 'Acv': Acv, 'lw': lw, 'l_alma': l_alma, 'Pg': dem['Pg'],
                    'Pu_max': dem['Pu_max'], 'Pu_min': dem['Pu_min']})
    return out


def disenar(torre, A, R, Omega0):
    """Diseño de todos los elementos con las fuerzas sísmicas reducidas por R (E = Fs/R, NSR-10 A.3.1) y la
    envolvente del 25 % del cortante para los pórticos solos (sistema dual, A.3.2.1.4)."""
    mod, res = A['modelo'], A['resp']
    G_ = {c: gravedad(torre, mod, res, c)[0] for c in ('D', 'L', 'Lr', 'S')}
    Ex, Ey = A['E']['x'], A['E']['y']
    # 25 % del cortante de la FHE en los pórticos solos (con su torsión accidental)
    mod25 = Modelo(torre, filtro=lambda P: not P['id'].startswith('M'))
    res25 = Respuestas(mod25)
    nv = torre['niveles']
    E25 = {}
    for s in ('x', 'y'):
        F = [0.25 * f for f in A['fhe'][s]['F']]
        U = mod25.resolver(vector_fuerzas(nv, F, s))
        Mt = [0.05 * dim_perpendicular(nv[k], s) * F[k] * A['estaticos'][s]['Ax'][k] for k in range(len(nv))]
        Ut = mod25.resolver(vector_fuerzas(nv, [0.0] * len(nv), s, Mt))
        a, b = res25.calcular(U), res25.calcular(Ut)
        E25[s] = [abs(p) + abs(q) for p, q in zip(a, b)]
    # capacidad de los pórticos solos frente al 25 %: se informa con su cortante basal
    def comp(vec, r_, eid, c):
        return abs(vec[r_.i_el[eid] + c])

    def E_el(eid, c, con25=True):
        """Componente c (0 Mi, 1 Mj, 2 V, 3 N) sísmica de diseño de un elemento: (100 % x + 30 % y; 30 % x + 100 % y)
        reducida por R, con la envolvente del 25 % de los pórticos solos."""
        ax, ay = comp(Ex, res, eid, c), comp(Ey, res, eid, c)
        out = [(ax + 0.3 * ay) / R, (0.3 * ax + ay) / R]
        if con25 and eid in res25.i_el:
            bx, by = comp(E25['x'], res25, eid, c), comp(E25['y'], res25, eid, c)
            out = [max(out[0], (bx + 0.3 * by) / R), max(out[1], (0.3 * bx + by) / R)]
        return out

    def g_el(eid):
        return {c: fuerzas_elemento(res, G_[c], eid) for c in ('D', 'L', 'Lr', 'S')}

    elementos = {}
    for pm in mod.porticos:
        for x in pm.el:
            e = x['e']
            elementos[e['id']] = (pm, e)
    # ---- vigas ----------------------------------------------------------------------------------------------------
    vigas = {}
    for eid, (pm, e) in elementos.items():
        if e['tipo'] != 'viga':
            continue
        Ed = [max(E_el(eid, c)) for c in range(3)]
        borde = (pm.dir == 0 and pm.c in (-19.6, 22.4)) or (pm.dir == 1 and pm.c in (-13.0, 8.6)) or \
                (pm.dir == 0 and e['nivel'] == 4 and pm.c == Y_RETROCESO)
        vigas[eid] = disenar_viga(e, g_el(eid), Ed, borde)
        vigas[eid]['pm'] = pm.id
        vigas[eid]['Ed'] = Ed
    # vigas cortas columna C – muro (no están en el modelo): armado simétrico igual al superior de la viga B-C de esa
    # línea, cortante por capacidad con Mpr en los dos extremos (el muro gira y les impone doble curvatura)
    acoples = {}
    for ac in torre['acoples']:
        vbc = vigas.get(f'VX-{ac["linea"]}-BC-{ac["nivel"]}')
        sup = vbc['sup'] if vbc else (3, 6)
        b, h = ac['b'], ac['h']
        sec = seccion_viga(b, h, b_ala(b, False, ac['ln']), sup, sup, malla_losa=MALLA_LOSETA)
        Mn = sec.resistencia(0.0, 'inf')[0]
        Mpr = sec.resistencia(0.0, 'inf', FC, FY_PR)[0]
        d = h - REC['viga'] - 0.0095 - BARRAS[sup[1]][0] / 2000
        Ve = 2 * Mpr / ac['ln'] + 0.5 * (vbc['wu'] if vbc else 30.0) * ac['ln']
        s_max = min(d / 4, 8 * BARRAS[sup[1]][0] / 1000, 0.30)
        est = estribos(Ve, 0.0, d, s_max, 4, 2)
        diagonal = ac['ln'] / h < 2.0 and Ve > 0.33 * math.sqrt(FC) * b * d * 1000
        acoples[ac['id']] = {**ac, 'sup': sup, 'inf': sup, 'Mn': Mn, 'Mpr': Mpr, 'Ve': Ve, 'est': est, 'd': d,
                             'ln_h': ac['ln'] / h, 'requiere_diagonal': diagonal,
                             'Vn_max_ok': Ve <= 0.75 * 0.83 * math.sqrt(FC) * b * d * 1000}

    # ---- nudos: ΣMnb por pórtico (vigas a cada lado; en las líneas con muro, la viga corta al oriente de C) ----------
    def sMnb(pm, nodo):
        izq = der = None
        for x in pm.el:
            e = x['e']
            if e['tipo'] != 'viga':
                continue
            if e['j'] == nodo['id']:
                izq = vigas[e['id']]
            if e['i'] == nodo['id']:
                der = vigas[e['id']]
        extra = None
        if pm.dir == 0 and nodo['eje'] == 'C' and pm.c in {a['y'] for a in torre['acoples']}:
            extra = acoples.get(f'VA-{pm.id[2:]}-CN-{nodo["nivel"]}')
        Mn_neg_d = der['Mn_neg'] if der else (extra['Mn'] if extra else 0.0)
        Mn_pos_d = der['Mn_pos'] if der else (extra['Mn'] if extra else 0.0)
        Mn_neg_i = izq['Mn_neg'] if izq else 0.0
        Mn_pos_i = izq['Mn_pos'] if izq else 0.0
        return max(Mn_neg_i + Mn_pos_d, Mn_pos_i + Mn_neg_d)

    # ---- columnas (de arriba hacia abajo) -------------------------------------------------------------------------
    fis = {}
    for eid, (pm, e) in elementos.items():
        if e['tipo'] == 'columna':
            fis.setdefault(e['fisico'], {})['X' if pm.dir == 0 else 'Y'] = (pm, e)
    orden = sorted(fis, key=lambda f: (-int(f.rsplit('-', 1)[1]), f))
    columnas = {}
    cache = {}
    for f in orden:
        cop = fis[f]
        b = next(iter(cop.values()))[1]['b']
        # gravedad: axial de las dos copias (cada una lleva las cargas de sus vigas); momentos de cada copia
        Ng = {c: sum(fuerzas_elemento(res, G_[c], e['id'])[3] for pm, e in cop.values()) for c in ('D', 'L', 'Lr', 'S')}
        dem = []
        for nombre, cD, cL, cLr, cE in COMBOS:
            Pg = -(cD * Ng['D'] + cL * Ng['L'] + cLr * Ng['Lr'])
            for orto in ((1.0, 0.3), (0.3, 1.0)):
                NE = 0.0
                ME = {}
                for plano, (pm, e) in cop.items():
                    i = res.i_el[e['id']]
                    NE += (orto[0] * abs(Ex[i + 3]) + orto[1] * abs(Ey[i + 3])) / R
                    ME[plano] = [(orto[0] * abs(Ex[i + c]) + orto[1] * abs(Ey[i + c])) / R for c in (0, 1)]
                    if e['id'] in res25.i_el:
                        j = res25.i_el[e['id']]
                        ME[plano] = [max(ME[plano][c], (orto[0] * E25['x'][j + c] + orto[1] * E25['y'][j + c]) / R) for c in (0, 1)]
                for extremo in (0, 1):
                    Mg = {}
                    for plano, (pm, e) in cop.items():
                        Mg[plano] = abs(sum(f_ * fuerzas_elemento(res, G_[c], e['id'])[extremo]
                                            for f_, c in ((cD, 'D'), (cL, 'L'), (cLr, 'Lr'))))
                    Mx = Mg.get('X', 0.0) + cE * ME.get('X', [0, 0])[extremo]
                    My = Mg.get('Y', 0.0) + cE * ME.get('Y', [0, 0])[extremo]
                    for sgn in ((1, -1) if cE else (0,)):
                        dem.append((Pg + sgn * cE * NE, Mx, My))
        # nudo de arriba en cada plano y columna de arriba (ya diseñada)
        k = int(f.rsplit('-', 1)[1])
        f_arr = f.rsplit('-', 1)[0] + f'-{k + 1}'
        nudo, arriba = {}, {}
        for plano, (pm, e) in cop.items():
            nodo = pm.P['idx'][e['j']]
            nudo[plano] = sMnb(pm, nodo)
            arriba[plano] = columnas[f_arr]['Mnc'] if f_arr in columnas else None
        elegido, revisados = disenar_columna(f, cop, dem, nudo, b, arriba, cache)
        if elegido is None:
            columnas[f] = {'falla': True, 'revisados': revisados, 'b': b, 'copias': cop, 'dem': dem}
            continue
        n, num, sec, util, Mnc, cvd = elegido
        Pmin = min(d_[0] for d_ in dem)
        Pmax = max(d_[0] for d_ in dem)
        Pg_s = -Ng['S']
        columnas[f] = {'b': b, 'n': n, 'num': num, 'sec': sec, 'util_PM': util, 'Mnc': Mnc, 'cvd': cvd, 'copias': cop,
                       'Pmin': Pmin, 'Pmax': Pmax, 'Pg': Pg_s, 'nudo': nudo, 'arriba': arriba, 'revisados': revisados,
                       'k': k, 'Ng': Ng}
    # ---- muros ----------------------------------------------------------------------------------------------------
    muros = {}
    for pid, mu in torre['muros'].items():
        pm = next(p_ for p_ in mod.porticos if p_.id == pid)
        dem = []
        for x in pm.el:
            e = x['e']
            gD = fuerzas_elemento(res, G_['D'], e['id'])
            gL = fuerzas_elemento(res, G_['L'], e['id'])
            gS = fuerzas_elemento(res, G_['S'], e['id'])
            Ed = E_el(e['id'], 0, False)
            Vd = E_el(e['id'], 2, False)
            dem.append({'Pu_max': -(1.2 * gD[3] + 1.0 * gL[3]), 'Pu_min': -(0.9 * gD[3]), 'Mu': max(Ed),
                        'Vu': max(Vd), 'Pg': -gS[3]})
        # desplazamiento de diseño (sin reducir) en la cubierta del muro: suma de las derivas del pórtico
        delta_u = sum(max(abs(Ex[res.i_port[(pid, k)]]) + 0.3 * abs(Ey[res.i_port[(pid, k)]]),
                          0.3 * abs(Ex[res.i_port[(pid, k)]]) + abs(Ey[res.i_port[(pid, k)]])) for k in pm.niveles)
        col_b = None
        if mu['def']['dir'] == 'x':
            cD = mu['def']['columna']
            fD = f'C-{cD[0]}{cD[1]}-1'
            col_b = (columnas[fD]['n'], columnas[fD]['num']) if fD in columnas and 'n' in columnas[fD] else (12, 7)
        muros[pid] = {'niveles': disenar_muro(mu, dem, mu['t'], col_b, delta_u, R), 'delta_u': delta_u, 'col_barras': col_b,
                      'dem': dem}
    return {'G': G_, 'vigas': vigas, 'acoples': acoples, 'columnas': columnas, 'muros': muros, 'E25': E25,
            'res25': res25, 'mod25': mod25, 'sMnb': sMnb, 'E_el': E_el}


# >>> CONTINUA
