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


TC_UD = 0.5 * FV / FA             # s, esquina del espectro de umbral de daño (ver espectro_umbral)


def espectro_umbral(T, Ad=AD):
    """Sa (g) del umbral de daño, NSR-10 A.12.3 (ξ = 2 %, sin I): meseta 3,0·Ad·Fa y rama 1,5·Ad·Fv/T, con la esquina
    en TC = 0,5·Fv/Fa. Es la forma de la NSR-98 (3,0·Ad y 1,5·Ad·S/T) con los coeficientes de sitio de la NSR-10:
    3,0 = 2,5·1,2 y 1,5 = 1,2·1,25 son la meseta y la rama del espectro de diseño corregidas de 5 % a 2 % de
    amortiguamiento, y el suelo amplifica la meseta con Fa y la rama con Fv como en el de diseño (A.2.6). Texto exacto
    de A.12.3 por confirmar: si la meseta fuera 3,0·Ad sin Fa, esta forma queda del lado seguro (1,5 veces mayor)."""
    return 3.0 * Ad * FA if T <= TC_UD else 1.5 * Ad * FV / T


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


# Muros de los núcleos (E1). Paños posibles (contrato 7.2): la cara occidental (x = 3,1) de las dos escaleras y del
# foso de ascensores (muros en y) y las caras norte y sur de las dos escaleras (muros en x, líneas 3, 4, 6 y 7). Las
# caras orientales (x = 8,6, fachada sobre el eje D) no se usan: correrían el centro de rigidez más al oriente, y el
# centro de masa está en x ≈ −1,6. Las puertas de las escaleras (torre_hospital_plantas.json, equipo B) parten los
# muros en x = 3,1: la norte en y = 15,3 (vano de 1,20 m en los 4 pisos) y la sur en y = −6,3 (pisos 3 y 4; en los
# pisos 1 y 2 la planta la pone en el muro y = −7,6, ver «pendientes»). Un muro estructural con un vano de piso a
# dintel en cada piso es, para la flexión en su plano, el machón que queda: el alma va de la jamba al otro extremo,
# y el machón corto del otro lado de la puerta (0,7 m) trabaja como aleta del muro en x de esa esquina. El dintel
# sobre el vano (viga de acople) no se modela: queda del lado de la menor rigidez (limitación declarada).
# Cuáles paños son estructurales lo decide el prediseño (DIMENSIONES['muros'], con el historial de ajustes): el
# resto de los núcleos se construye en mampostería separada de la estructura (bloque de concreto de celdas llenas,
# 2 h de resistencia al fuego para las escaleras, NSR-10 Tabla J.3.4-3, por confirmar).
PUERTA_ESC_N = (14.7, 15.9)       # vano de la puerta de la escalera norte en x = 3,1 (planta de B: centro 15,3, ancho 1,2)
PUERTA_ESC_S = (-6.9, -5.7)       # vano de la puerta de la escalera sur en x = 3,1 (planta de B, pisos 3 y 4: centro −6,3)
MUROS = [
    {'portico': 'MY-N6', 'dir': 'y', 'c': XN, 'alma': (PUERTA_ESC_N[1], 22.4), 'eje': '6',
     'tramo': 'N entre 6 y 7 (cara occidental de la escalera norte, de la puerta al eje 7)', 'nucleo': 'escalera_norte',
     'i': ('libre', 'jamba norte de la puerta de la escalera (y = 15,9)'), 'j': ('aleta', 'MX-7')},
    {'portico': 'MY-N3', 'dir': 'y', 'c': XN, 'alma': (PUERTA_ESC_S[1], 0.8), 'eje': '3',
     'tramo': 'N entre 3 y 4 (cara occidental de la escalera sur, de la puerta al eje 4)', 'nucleo': 'escalera_sur',
     'i': ('libre', 'jamba norte de la puerta de la escalera (y = −5,7)'), 'j': ('aleta', 'MX-4')},
    {'portico': 'MY-N4', 'dir': 'y', 'c': XN, 'alma': (1.6, 7.2), 'eje': '4',
     'tramo': 'N entre 4 y 5 (cara occidental del foso de ascensores)', 'nucleo': 'ascensores',
     'i': ('foso', 1.6), 'j': ('foso', 7.2)},
    {'portico': 'MX-3', 'dir': 'x', 'c': -7.6, 'alma': (XN, 8.6), 'eje': 'D',
     'tramo': '3 entre N y D (cara sur de la escalera sur)', 'nucleo': 'escalera_sur',
     'i': ('machon', 'MY-N3', -7.6, PUERTA_ESC_S[0]), 'j': ('columna', 'D', '3')},
    {'portico': 'MX-4', 'dir': 'x', 'c': 0.8, 'alma': (XN, 8.6), 'eje': 'D',
     'tramo': '4 entre N y D (cara norte de la escalera sur)', 'nucleo': 'escalera_sur',
     'i': ('aleta', 'MY-N3'), 'j': ('columna', 'D', '4')},
    {'portico': 'MX-6', 'dir': 'x', 'c': 14.0, 'alma': (XN, 8.6), 'eje': 'D',
     'tramo': '6 entre N y D (cara sur de la escalera norte)', 'nucleo': 'escalera_norte',
     'i': ('machon', 'MY-N6', 14.0, PUERTA_ESC_N[0]), 'j': ('columna', 'D', '6')},
    {'portico': 'MX-7', 'dir': 'x', 'c': 22.4, 'alma': (XN, 8.6), 'eje': 'D',
     'tramo': '7 entre N y D (cara norte de la escalera norte)', 'nucleo': 'escalera_norte',
     'i': ('aleta', 'MY-N6'), 'j': ('columna', 'D', '7')},
]
MURO_DEF = {m['portico']: m for m in MUROS}


def geometria_muro(m, activos, t_de, cb):
    """Sección en planta de un muro con sus aletas efectivas (E1; NSR-10 C.21.9.5.2, por confirmar: el ancho de la
    aleta medido desde la cara del alma es el menor entre la mitad de la distancia al alma paralela vecina, el 25 % de
    la altura total del muro y lo que de verdad mide). u = coordenada a lo largo del alma (y en los muros en y, x en
    los muros en x). → dict con partes [{tipo: alma|aleta|columna, u0, u1, ancho}], rect, notas, concreto (tramos
    que se pesan con este muro: alma y machón; la aleta que es alma de otro muro se pesa con ese otro) y el largo."""
    t = t_de(m['portico'])
    hw = H_TOTAL
    a0, a1 = m['alma']
    partes, notas, concreto = [], [], []
    u_ini, u_fin = a0, a1
    otros = [o for o in MUROS if o['portico'] in activos and o['dir'] == m['dir'] and o['portico'] != m['portico']]

    def aleta(s_a, signo_lejos, largo_real, tf, quien):
        """Aleta en u = s_a que se extiende en la dirección perpendicular hacia signo_lejos (±1)."""
        vecinos = [abs(o['c'] - m['c']) for o in otros if (o['c'] - m['c']) * signo_lejos > 1e-9]
        lim = [(0.25 * hw, f'0,25·hw = {es(0.25 * hw)}'), (largo_real, f'longitud real = {es(largo_real)}')]
        if vecinos:
            lim.append((min(vecinos) / 2, f'mitad de la distancia al alma vecina = {es(min(vecinos) / 2)}'))
        bf = min(lim)[0]
        partes.append({'tipo': 'aleta', 'u0': s_a - tf / 2, 'u1': s_a + tf / 2, 'ancho': t + bf, 'de': quien})
        notas.append(f'aleta en u = {es(s_a)} ({quien}): ancho efectivo desde la cara del alma = min('
                     + '; '.join(x[1] for x in lim) + f') = {es(bf)} m')
        return bf

    for lado in ('i', 'j'):
        ext = m[lado]
        s_a = a0 if lado == 'i' else a1
        hacia = 1 if lado == 'i' else -1            # el alma sigue hacia +u desde i y hacia −u desde j
        if ext[0] == 'libre':
            notas.append(f'borde libre en u = {es(s_a)}: {ext[1]}')
        elif ext[0] == 'aleta' and ext[1] in activos:
            f = MURO_DEF[ext[1]]
            tf = t_de(ext[1])
            lejos = f['alma'][1] if abs(f['alma'][1] - m['c']) > abs(f['alma'][0] - m['c']) else f['alma'][0]
            signo = 1 if lejos > m['c'] else -1
            aleta(s_a, signo, abs(lejos - m['c']) - t / 2, tf, f'alma del muro {ext[1]}')
            if lado == 'i':
                u_ini = s_a + tf / 2
            else:
                u_fin = s_a - tf / 2
        elif ext[0] == 'machon' and ext[1] in activos:
            tf = t_de(ext[1])
            c0, c1 = ext[2], ext[3]
            largo = abs(c1 - c0) - t / 2
            signo = 1 if c1 > c0 else -1
            aleta(s_a, signo, largo, tf, f'machón de {es(abs(c1 - c0))} m del muro x = {es(XN)} junto a la puerta')
            concreto.append(('machon', (XN, c0 + signo * t / 2, XN, c1) if m['dir'] == 'x' else (c0, XN, c1, XN), tf))
            u_ini = s_a + tf / 2 if lado == 'i' else u_ini
            if lado == 'j':
                u_fin = s_a - tf / 2
        elif ext[0] == 'foso':
            # caras y = 1,6 y y = 7,2 del foso (de x = 3,1 a 6,1): de concreto si el muro del foso es estructural
            tf = t
            largo = (6.1 - XN) - t / 2
            signo = 1
            aleta(s_a, signo, largo, tf, f'cara y = {es(s_a)} del foso de ascensores')
            concreto.append(('aleta_foso', (XN + t / 2, s_a, 6.1, s_a), tf))
            if lado == 'i':
                u_ini = s_a + tf / 2
            else:
                u_fin = s_a - tf / 2
        elif ext[0] == 'columna':
            b = cb(ext[1], ext[2])
            partes.append({'tipo': 'columna', 'u0': s_a - b / 2, 'u1': s_a + b / 2, 'ancho': b,
                           'de': f'columna {ext[1]}{ext[2]}'})
            notas.append(f'columna {ext[1]}{ext[2]} de {es(b)} × {es(b)} m como elemento de borde en u = {es(s_a)}')
            if lado == 'i':
                u_ini = s_a + b / 2
            else:
                u_fin = s_a - b / 2
        else:
            # aleta o machón que no es estructural: el alma llega hasta el eje del paño perpendicular más t/2
            notas.append(f'sin aleta en u = {es(s_a)} ({ext[1]} no es estructural)')
            if lado == 'i':
                u_ini = s_a - t / 2
            else:
                u_fin = s_a + t / 2
    partes.append({'tipo': 'alma', 'u0': u_ini, 'u1': u_fin, 'ancho': t, 'de': 'alma'})
    partes.sort(key=lambda p: p['u0'])
    if m['dir'] == 'x':
        concreto.append(('alma', (u_ini, m['c'], u_fin, m['c']), t))
    else:
        concreto.append(('alma', (m['c'], u_ini, m['c'], u_fin), t))
    rect = [(p['u0'], p['u1'], p['ancho']) for p in partes]
    A, uc, I = props_rectangulos(rect)
    Av = sum((p['u1'] - p['u0']) * p['ancho'] for p in partes if p['tipo'] == 'alma')
    return {'partes': partes, 'rect': rect, 'notas': notas, 'concreto': concreto, 't': t, 'A': A, 'uc': uc, 'I': I,
            'Av': Av, 'u0': min(p['u0'] for p in partes), 'u1': max(p['u1'] for p in partes),
            'l_alma': u_fin - u_ini}


def props_rectangulos(rect):
    """Área, centroide (u) e inercia de una sección de rectángulos (u0, u1, ancho)."""
    A = sum((u1 - u0) * b for u0, u1, b in rect)
    uc = sum((u1 - u0) * b * (u0 + u1) / 2 for u0, u1, b in rect) / A
    I = sum(b * (u1 - u0) ** 3 / 12 + (u1 - u0) * b * ((u0 + u1) / 2 - uc) ** 2 for u0, u1, b in rect)
    return A, uc, I


def paneles_nucleo(activos):
    """Todos los paños de los núcleos con su material: concreto si forman parte de un muro estructural (alma, aleta del
    foso o machón junto a una puerta) y mampostería separada si no. → [{nombre, tramo (x0, y0, x1, y1), material,
    muro}]. Lo usan las masas, la geometría para la vista y el modelo BIM."""
    def act(*ids):
        return all(i in activos for i in ids)
    n0, n1 = PUERTA_ESC_N
    s0, s1 = PUERTA_ESC_S
    filas = [
        ('escalera norte, cara occidental al norte de la puerta', (XN, n1, XN, 22.4), act('MY-N6'), 'MY-N6'),
        ('escalera norte, machón al sur de la puerta', (XN, 14.0, XN, n0), act('MY-N6', 'MX-6'), 'MX-6'),
        ('escalera norte, cara sur (y = 14,0)', (XN, 14.0, 8.6, 14.0), act('MX-6'), 'MX-6'),
        ('escalera norte, cara norte (y = 22,4)', (XN, 22.4, 8.6, 22.4), act('MX-7'), 'MX-7'),
        ('escalera norte, cara oriental (x = 8,6)', (8.6, 14.0, 8.6, 22.4), False, None),
        ('escalera sur, cara occidental al norte de la puerta', (XN, s1, XN, 0.8), act('MY-N3'), 'MY-N3'),
        ('escalera sur, machón al sur de la puerta', (XN, -7.6, XN, s0), act('MY-N3', 'MX-3'), 'MX-3'),
        ('escalera sur, cara sur (y = −7,6)', (XN, -7.6, 8.6, -7.6), act('MX-3'), 'MX-3'),
        ('escalera sur, cara norte (y = 0,8)', (XN, 0.8, 8.6, 0.8), act('MX-4'), 'MX-4'),
        ('escalera sur, cara oriental (x = 8,6)', (8.6, -7.6, 8.6, 0.8), False, None),
        ('foso de ascensores, cara occidental (x = 3,1)', (XN, 1.6, XN, 7.2), act('MY-N4'), 'MY-N4'),
        ('foso de ascensores, cara y = 1,6', (XN, 1.6, 6.1, 1.6), act('MY-N4'), 'MY-N4'),
        ('foso de ascensores, cara y = 7,2', (XN, 7.2, 6.1, 7.2), act('MY-N4'), 'MY-N4'),
        ('foso de ascensores, cara oriental con las puertas (x = 6,1)', (6.1, 1.6, 6.1, 7.2), False, None),
        ('foso de ascensores, separación entre cabinas (y = 4,4)', (XN, 4.4, 6.1, 4.4), False, None),
        ('montacargas general, cara occidental (x = 3,1)', (XN, 0.8, XN, 1.6), False, None),
        ('montacargas general, cara oriental (x = 6,1)', (6.1, 0.8, 6.1, 1.6), False, None),
    ]
    out = []
    for nombre, tramo, es_conc, muro in filas:
        out.append({'nombre': nombre, 'tramo': tramo, 'material': 'concreto' if es_conc else 'mamposteria',
                    'muro': muro if es_conc else None})
    return out


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
    'bloque_nucleo_kN_m2': (3.00, 'bloque de concreto de 15 cm con celdas llenas y pañete en los paños de núcleo que no son '
                                  'estructurales (2 h de resistencia al fuego; Tabla B.3.4.2, por confirmar)'),
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
        """(b, h) de las vigas del pórtico Y-nombre_x: la del eje si DIMENSIONES la fija, si no la de borde (A, D) o
        la interior (B, C)."""
        if nombre_x in dim.get('vy_eje', {}):
            return dim['vy_eje'][nombre_x]
        return dim['vy_borde'] if nombre_x in ('A', 'D') else dim['vy_int']

    def h_viga_x(nombre_y):
        if nombre_y in dim.get('vx_linea', {}):
            return dim['vx_linea'][nombre_y]
        return dim.get('vx_borde', dim['vx']) if nombre_y in ('1', '7') else dim['vx']

    def cb(nx, ny):
        """Lado de la columna cuadrada del cruce (nx, ny): el mayor entre el general, el de su eje x (col_eje) y el de
        su línea y (col_linea); las de fachada pueden ser mayores (col_borde)."""
        lados = [col_b, dim.get('col_eje', {}).get(nx, 0.0), dim.get('col_linea', {}).get(ny, 0.0)]
        if nx in ('A', 'D') or ny in ('1', '7'):
            lados.append(dim.get('col_borde', 0.0))
        return max(lados)

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
        g = geometria_muro(m, activos, t_de, cb)
        tw, A, I, Av, uc = g['t'], g['A'], g['I'], g['Av'], g['uc']
        pid = m['portico']
        P = {'id': pid, 'dir': m['dir'], 'c': m['c'], 'nodos': [], 'elementos': [], 'cargas': {}, 'muro': m}
        for k in range(0, NIV + 1):
            P['nodos'].append({'id': nodo_id(pid, m['eje'], k), 's': uc, 'nivel': k, 'eje': m['eje']})
        lado = pid[3:] if m['dir'] == 'x' else 'N' + m['eje']
        for k in range(1, NIV + 1):
            eid = f'{pid[:2]}-{lado}{m["eje"] if m["dir"] == "x" else ""}-{k}'
            P['elementos'].append({'id': eid, 'tipo': 'muro_concreto', 'i': nodo_id(pid, m['eje'], k - 1),
                                   'j': nodo_id(pid, m['eje'], k), 'b': tw, 'h': g['u1'] - g['u0'], 'arms': [0.0, 0.0],
                                   'eje': m['tramo'], 'nivel': k, 'A': A, 'I': I, 'Av': Av, 'rect': g['rect']})
        muros[pid] = {'def': m, **g}
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
    # muros: el concreto de cada paño una sola vez (la aleta que es alma de otro muro se pesa con ese otro)
    for pid, mu in muros.items():
        largo = 0.0
        for _, (x0, y0, x1, y1), tt in mu['concreto']:
            l_ = math.hypot(x1 - x0, y1 - y0)
            largo += l_ * tt / mu['t']
            for k in range(1, NIV + 1):
                h = Z[k] - Z[k - 1]
                W = tt * l_ * h * GAMMA_C
                carga_nodo(pid, nodo_muro(pid, k), 'D', W)
                masa(k, W / 2, 0, 0, 'muros_de_concreto', ('linea', x0, y0, x1, y1))
                masa(k - 1, W / 2, 0, 0, 'muros_de_concreto', ('linea', x0, y0, x1, y1))
        mu['largo_fisico'] = largo
    # paños de los núcleos que no son estructurales: mampostería separada de la estructura (bloque de concreto de
    # 15 cm con celdas llenas, ≈ 3,0 kN/m² con pañete; estimación con NSR-10 Tabla B.3.4.2-4, por confirmar). Se
    # apoyan en la losa de cada piso (carga en la viga o el muro de su línea) y su masa va mitad a cada nivel.
    nucleos_mamp = [(x['nombre'], x['tramo']) for x in paneles_nucleo(activos) if x['material'] == 'mamposteria']
    w_mamp = CARGAS_MUERTAS['bloque_nucleo_kN_m2'][0]
    def apoyar_en_lineas_x(W, y_m, k, caso='D'):
        """Lleva una carga W del nivel k (sobre las vigas secundarias del núcleo, de 1,4 a 8,6 en x) a las dos líneas
        X que la encierran, por la regla de la palanca: al nodo del muro en x si es estructural; si no, a la viga
        C-D de esa línea como carga repartida de la misma resultante."""
        lin = sorted(EJES_Y, key=lambda e: e[1])
        n0, y0_ = max(((n, yy) for n, yy in lin if yy <= y_m + 1e-9), key=lambda e: e[1])
        n1, y1_ = min(((n, yy) for n, yy in lin if yy >= y_m - 1e-9), key=lambda e: e[1])
        partes_ = [(n0, 1.0)] if n0 == n1 else [(n0, (y1_ - y_m) / (y1_ - y0_)), (n1, (y_m - y0_) / (y1_ - y0_))]
        for n_, f_ in partes_:
            if f_ == 0:
                continue
            pm_ = f'MX-{n_}'
            if pm_ in activos:
                carga_nodo(pm_, nodo_muro(pm_, k), caso, W * f_)
            else:
                for eid, frac in vigas_x(n_, 1.4, 8.6, k):
                    carga_viga(eid, caso, W * f_ / elem[eid][1]['L'])

    for nombre, (x0, y0, x1, y1) in nucleos_mamp:
        l_ = math.hypot(x1 - x0, y1 - y0)
        for p in range(1, NIV + 1):
            h = Z[p] - Z[p - 1]
            W = w_mamp * l_ * h
            masa(p - 1, W / 2, 0, 0, 'mamposteria_de_nucleos', ('linea', x0, y0, x1, y1))
            masa(p, W / 2, 0, 0, 'mamposteria_de_nucleos', ('linea', x0, y0, x1, y1))
            if p < 2:
                continue                                        # el piso 1 se apoya en el contrapiso
            k = p - 1
            if abs(x0 - x1) < 1e-9 and abs(x0 - 8.6) < 1e-9:
                for eid, frac in vigas_y('D', min(y0, y1), max(y0, y1), k):
                    carga_viga(eid, 'D', W / l_ * frac)
            elif abs(y0 - y1) < 1e-9 and any(abs(y0 - yy) < 1e-9 for _, yy in EJES_Y):
                apoyar_en_lineas_x(W, y0, k)
            else:
                apoyar_en_lineas_x(W, (y0 + y1) / 2, k)

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
                    # los tramos se apoyan en los descansos y los descansos en las dos líneas extremas del núcleo (y0 y
                    # y1): en el muro en x si es estructural o, si es de mampostería, en la viga de descanso que llega
                    # a la viga C-D de esa línea (apoyar_en_lineas_x)
                    for y_lin in nu['y']:
                        apoyar_en_lineas_x(W_D / 4, y_lin, kk, 'D')
                        apoyar_en_lineas_x(W_L / 4, y_lin, kk, 'L')
    # casetas de escalera y sobrerrecorrido de ascensores sobre la cubierta (programa.json; estimación)
    casetas = []
    for nombre, pid_y, pids_x in (('escalera_norte', 'MY-N6', ('MX-6', 'MX-7')), ('escalera_sur', 'MY-N3', ('MX-3', 'MX-4'))):
        nu = NUCLEOS[nombre]
        a = (nu['x'][1] - nu['x'][0]) * (nu['y'][1] - nu['y'][0])
        per = 2 * ((nu['x'][1] - nu['x'][0]) + (nu['y'][1] - nu['y'][0]))
        W = a * (0.15 * GAMMA_C + cm_['cubierta_kPa'][0]) + per * 3.3 * cm_['ladrillo_fachada_kN_m2'][0]
        casetas.append({'id': f'caseta_{nombre}', 'W_kN': W, 'area_m2': a})
        masa(4, W, (nu['x'][0] + nu['x'][1]) / 2, (nu['y'][0] + nu['y'][1]) / 2, 'casetas')
        for y_lin in nu['y']:
            apoyar_en_lineas_x(W / 2, y_lin, 4, 'D')
    nu = NUCLEOS['ascensores']
    W_sob = 17.2 * 1.8 * 0.20 * GAMMA_C + 16.8 * (0.15 * GAMMA_C + cm_['cubierta_kPa'][0]) + 60.0
    casetas.append({'id': 'sobrerrecorrido_ascensores', 'W_kN': W_sob, 'area_m2': 16.8,
                    'nota': 'muros de 0,20 m y 1,8 m de alto, placa de 0,15 m y 60 kN de máquinas sin cuarto (estimación)'})
    masa(4, W_sob, 4.6, 4.4, 'casetas')
    if 'MY-N4' in activos:
        carga_nodo('MY-N4', nodo_muro('MY-N4', 4), 'D', W_sob)
    else:
        apoyar_en_lineas_x(W_sob, 4.4, 4, 'D')

    # ---- vigas cortas entre la columna C y el muro (líneas 3, 4, 6 y 7): no están en el modelo (ver docstring) ----
    acoples = []
    for ny, yl in EJES_Y:
        if yl not in lineas_muro_x:
            continue
        for k in niveles_de_linea_x(yl):
            cC = cb('C', ny)
            ln = (XN - t_de(f'MY-N{"6" if yl > 10 else "3"}') / 2) - (EJX['C'] + cC / 2)
            # viga banda del alto de la losa nervada y del ancho de la columna: con ln/h > 2 no necesita refuerzo
            # diagonal (C.21.9.7) y casi no acopla el pórtico con el muro, que es lo que supone el modelo
            vb_, vh_ = cC, H_LOSA
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
    # redundancia (A.3.3.8; a falta de su texto, la prueba de ASCE/SEI 7-16 12.3.4.2 a y Tabla 12.3-3, de donde viene
    # φr = 0,75 ≈ 1/ρ con ρ = 1,3; por confirmar). Cada entrepiso que toma más del 35 % del cortante basal debe cumplir la
    # tabla: en muros, solo entran en la prueba los de relación altura del piso/longitud > 1,0 (Fig. 12.3-2:
    # h_piso/l_muro; aquí con la longitud del alma, la menor, del lado seguro); su remoción no debe quitar más de un
    # tercio de la RESISTENCIA del piso ni dejar torsión extrema. En pórticos, perder el momento en los dos extremos de
    # una viga (se revisa después del diseño, chequeo RED). La fracción del cortante elástico que toma cada muro y la
    # torsión sin él se informan, pero no son la prueba (revisión A6: con esa fracción salía φr = 0,75 sin que ningún
    # muro entrara en la prueba).
    redund = []
    for pid in torre['muros']:
        mu_ = torre['muros'][pid]
        s = 'x' if mu_['def']['dir'] == 'x' else 'y'
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
        h_l = max((Z[k] - Z[k - 1]) / mu_['l_alma'] for k in pm.niveles)
        sujeto = h_l > 1.0
        # un muro sujeto a la prueba necesitaría la resistencia del piso con y sin él, que solo se conoce después del
        # diseño: mientras tanto, φr = 0,75 (del lado seguro). En esta torre ninguno entra (h/l ≤ 0,91).
        redund.append({'muro': pid, 'sentido': s, 'h_piso_sobre_l_alma_max': h_l, 'sujeto_a_la_prueba': sujeto,
                       'fraccion_cortante_elastico_entrepiso_1': abs(V_muro) / V_piso, 'cociente_torsional_sin_el': cq,
                       'cumple': not sujeto})
    phi_r = 1.0 if all(x['cumple'] for x in redund) else 0.75
    sis = SISTEMAS['dual']
    R = phi_a * phi_p * phi_r * sis['R0']
    return {'participacion': part, 'cociente_torsional': rt, 'phi_p': phi_p, 'tipo_p': tipo_p, 'rigidez_entrepiso': rig,
            'irr_1A': irr_1A, 'irr_2A': irr_2A, 'geometrica_3A': geo, 'phi_a': phi_a, 'redundancia': redund,
            'phi_r': phi_r, 'R0': sis['R0'], 'Omega0': sis['Omega0'], 'R': R, 'tabla': sis['tabla'], 'uso': sis['uso'],
            'R_con_phi_r_075': phi_a * phi_p * 0.75 * sis['R0']}


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
    """Sección del muro con su refuerzo: dos cortinas verticales (N.º, s) en el alma y en el ancho efectivo de las
    aletas, barras de borde (n, N.º) a 0,10 m de cada extremo del alma y las barras de la columna de borde (muros en x;
    col_barras = (n, N.º) de su diseño como columna)."""
    num_c, s_c = cortina
    barras = []
    for p in mu['partes']:
        u0, u1, w = p['u0'], p['u1'], p['ancho']
        if p['tipo'] == 'columna':
            if col_barras:
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
        if p['tipo'] == 'aleta':
            # las dos cortinas corren a lo largo del ancho efectivo w (perpendicular al plano): en u es una franja
            n_barras = 2 * max(2, int(w / s_c) + 1)
            barras.append(((u0 + u1) / 2, area(n_barras, num_c)))
        else:
            largo = u1 - u0
            nb = max(2, int((largo - 2 * rec) / s_c) + 1)
            for i in range(nb):
                barras.append((u0 + rec + (largo - 2 * rec) * i / max(nb - 1, 1), area(2, num_c)))
    alma = next(p for p in mu['partes'] if p['tipo'] == 'alma')
    for (n, num), uu in ((borde_i, alma['u0'] + 0.10), (borde_j, alma['u1'] - 0.10)):
        if n:
            barras.append((uu, area(n, num)))
    return Seccion(mu['rect'], barras, [], rho_s=0.0, ke=K_PRIESTLEY['muro'])


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
    l_alma = mu['l_alma']
    Acv = mu['Av']                                       # área del alma (las aletas no toman cortante en el plano)
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
        Vn_max = 0.83 * math.sqrt(FC) * Acv * 1000                      # C.21.9.4.4: tope de la resistencia utilizable
        Vn = min(Acv * 1000 * (ac * math.sqrt(FC) + rho_t * FY), Vn_max)
        Vn_e = min(Acv * 1000 * (ac * math.sqrt(FCE) + rho_t * FYE), 0.83 * math.sqrt(FCE) * Acv * 1000)
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
        b, h = ac['b'], ac['h']
        # refuerzo mínimo de viga (C.10.5.1) arriba y abajo: la viga banda no tiene demanda sísmica propia en el modelo
        # (no está en él); su cortante sale de su propia capacidad (Mpr en los dos extremos)
        sup = elegir_barras(b, as_minima_viga(b, h - 0.065), REC['viga'], 3) or (3, 5)
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
                       'k': k, 'Ng': Ng, 'dem': dem}
        columnas[f]['transversal'] = transversal_columna(columnas[f], ln_columna(cop), (Pmin, Pmax))
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
            cD = mu['def']['j'][1:]
            fD = f'C-{cD[0]}{cD[1]}-1'
            col_b = (columnas[fD]['n'], columnas[fD]['num']) if fD in columnas and 'n' in columnas[fD] else (12, 7)
        muros[pid] = {'niveles': disenar_muro(mu, dem, mu['t'], col_b, delta_u, R), 'delta_u': delta_u, 'col_barras': col_b,
                      'dem': dem}
    return {'G': G_, 'vigas': vigas, 'acoples': acoples, 'columnas': columnas, 'muros': muros, 'E25': E25,
            'res25': res25, 'mod25': mod25, 'sMnb': sMnb, 'E_el': E_el}



def transversal_columna(c, ln, P_rango):
    """Refuerzo transversal de una columna DMO (NSR-10 C.21.3.5, numerales por confirmar) con dos criterios más
    exigentes que se adoptan por ser grupo IV: el área de confinamiento Ash de C.21.6.4.4 (la de DES) en la zona lo y el
    cortante por capacidad con Mpr de la propia columna (C.21.6.5.1, también de DES; del lado seguro frente a C.21.3.3,
    que permite el cortante de Mn). c: diseño de la columna (b, n, num, sec); ln: altura libre (m); P_rango: (Pmin,
    Pmax) mayoradas (compresión +). → dict con estribos, ganchos, so, lo, cortante."""
    opciones = [transversal_columna_con(c, ln, P_rango, de_num) for de_num in (4, 5)]
    return min(opciones, key=lambda t: (t['no_alcanza'], round(t['kg_m'], 6), t['num']))


def transversal_columna_con(c, ln, P_rango, de_num):
    b, n, num, sec = c['b'], c['n'], c['num'], c['sec']
    rec = REC['columna']
    db = BARRAS[num][0] / 1000
    nf = n // 4 + 1                                     # barras por cara, con las esquinas
    d = b - rec - BARRAS[de_num][0] / 1000 - db / 2
    # Mpr: el mayor en el rango de carga axial (1,25·fy, φ = 1), en los dos extremos (doble curvatura)
    Mpr = max(sec.resistencia(P, 'sup', FC, FY_PR)[0] for P in (P_rango[0], P_rango[1], 0.4 * sec.Po()))
    Ve = 2 * Mpr / ln
    Nu = max(P_rango[0], 0.0)
    Ag = b * b
    Vc = 0.17 * (1 + Nu / (14 * Ag * 1000)) * math.sqrt(FC) * b * d * 1000          # C.11.2.1.2
    # separación en la zona confinada (DMO, C.21.3.5.2): 8·db, 16·d_estribo, b/3 y 150 mm
    so = min(8 * db, 16 * BARRAS[de_num][0] / 1000, b / 3, 0.150)
    so = math.floor(so / 0.025 + 1e-9) * 0.025
    lo = max(ln / 6, b, 0.50)                                                       # C.21.3.5.? (≥ 500 mm)
    lo = math.ceil(lo / 0.05 - 1e-9) * 0.05
    # ramas por dirección: apoyo lateral de las esquinas y de barras alternas (C.7.10.5.3: ninguna barra sin apoyo a más
    # de 150 mm libres de una apoyada) y Ash
    sep = (b - 2 * (rec + BARRAS[de_num][0] / 1000) - db) / (nf - 1)
    if sep - db <= 0.150:
        apoyadas = math.ceil(nf / 2) + (1 if nf % 2 == 0 else 0)
    else:
        apoyadas = nf
    bc = b - 2 * rec                                                                # núcleo hasta la cara exterior del estribo
    Ach = bc * bc

    def ash_req(s_):                                                                # m², C.21.6.4.4 con la separación s_
        return max(0.3 * s_ * bc * FC / FY * (Ag / Ach - 1), 0.09 * s_ * bc * FC / FY)
    Ab = BARRAS[de_num][1] * 1e-6
    # ramas por dirección: cada gancho suplementario abraza una barra longitudinal de la cara (C.7.10.5.3 y C.21.6.4.2),
    # así que no puede haber más ramas que barras por cara (revisión A6: había columnas de 5 barras por cara con 7
    # ramas). Si el Ash o el cortante piden más, se cierra la separación (hasta 75 mm) en lugar de agregar ramas.
    Vs_req = max(Ve / 0.75 - Vc, 0.0)
    ramas = min(max(apoyadas, 2), nf)
    s_lo = so
    while True:
        falta_ash = ramas * Ab < ash_req(s_lo) - 1e-12
        falta_v = Vs_req > 0 and ramas * Ab * FY * 1000 * d / s_lo < Vs_req - 1e-9
        if not (falta_ash or falta_v):
            break
        if ramas < nf:
            ramas += 1
        elif s_lo > 0.075 + 1e-9:
            s_lo = round(s_lo - 0.025, 3)
        else:
            break
    no_alcanza = ramas * Ab < ash_req(s_lo) - 1e-12 or (Vs_req > 0 and ramas * Ab * FY * 1000 * d / s_lo < Vs_req - 1e-9)
    Ash_req = ash_req(s_lo)
    s_v = ramas * Ab * FY * 1000 * d / Vs_req if Vs_req > 0 else so
    Vs = ramas * Ab * FY * 1000 * d / s_lo
    # fuera de lo: C.7.10.5.2 y C.11.4.5.1 (16·db, 48·d_estribo, b, d/2) y el mismo cortante
    s_c = min(16 * db, 48 * BARRAS[de_num][0] / 1000, b, d / 2, s_v)
    s_c = max(math.floor(s_c / 0.025 + 1e-9) * 0.025, s_lo)
    Vn = Vc + Vs
    Vn_e = 0.17 * (1 + Nu / (14 * Ag * 1000)) * math.sqrt(FCE) * b * d * 1000 + ramas * Ab * FYE * 1000 * d / s_lo
    rho_t = ramas * Ab / (b * s_lo)
    rho_s = 2 * ramas * Ab * (bc - BARRAS[de_num][0] / 1000) / (Ach * s_lo)       # cuantía volumétrica (2 direcciones)
    # acero transversal por metro de columna (para escoger el diámetro): zona lo en los dos extremos y el resto
    largo_rama = (b - 2 * rec) + 2 * max(6 * BARRAS[de_num][0] / 1000, 0.075)
    n_lo = 2 * lo / s_lo
    n_c = max(ln - 2 * lo, 0.0) / s_c
    kg_m = 2 * ramas * largo_rama * BARRAS[de_num][2] * (n_lo + n_c) / ln
    return {'num': de_num, 'ramas': ramas, 'ganchos_suplementarios': max(ramas - 2, 0), 's_lo': round(s_lo, 3),
            'kg_m': kg_m, 'no_alcanza': no_alcanza,
            's_centro': round(s_c, 3), 'so_max': round(so, 3), 'lo': round(lo, 3), 'Ash_req_mm2': Ash_req * 1e6,
            'Ash_mm2': ramas * Ab * 1e6, 'Mpr': Mpr, 'Ve': Ve, 'Vc': Vc, 'Vs': Vs, 'Vn': Vn, 'phiVn': 0.75 * Vn,
            'Vn_max': Vc + 0.66 * math.sqrt(FC) * b * d * 1000, 'Vn_e': Vn_e, 'rho_t': rho_t, 'rho_s': rho_s, 'd': d,
            'ln': ln, 'apoyadas_por_cara': apoyadas, 'barras_por_cara': nf}


def ln_columna(copias):
    """Altura libre de la columna: la menor longitud flexible de sus copias (la viga más peraltada en la cabeza)."""
    return min(e['Lf'] for pm, e in copias.values())


# Haselton y otros (2016) y ASCE/SEI 41-17 dan los parámetros de las rótulas; el endurecimiento sale de los dos:
#   H = (Mc − My)/θcap,pl con Mc/My y θcap,pl de Haselton, y α = H/k_e = (Mc/My − 1)·θy/θcap,pl (k_e = My/θy).
def endurecimiento_haselton(nu, rho_sh, theta_y):
    th, mc = haselton(nu, rho_sh)
    return max((mc - 1) * theta_y / th, 1e-3), th, mc


def mc_puntos(mc, n_dec=6):
    """Momento-curvatura para la salida: [φ (1/m), M (kN·m)] con 6 cifras significativas."""
    return [[rs(f, 4), rs(M, 4)] for f, M in mc]


def props_viga_rotula(e, dv):
    """Propiedades nominales y esperadas de la rótula de una viga (E3, E16) con su sección T (malla de la loseta en el
    ala para el momento negativo, C.21.6.2.2)."""
    b, h, Lf = e['b'], e['h'], e['Lf']
    I = b * h ** 3 / 12
    EIf = EC * 1000 * I * 0.35
    sn, sp = dv['sec_neg'], dv['sec_pos']
    My_n, phy_n = sn.fluencia(0.0, 'inf', FC, FY)
    My_p, phy_p = sp.fluencia(0.0, 'sup', FC, FY)
    Mye_n, phye_n = sn.fluencia(0.0, 'inf', FCE, FYE)
    Mye_p, phye_p = sp.fluencia(0.0, 'sup', FCE, FYE)
    Mn_e_n = sn.resistencia(0.0, 'inf', FCE, FYE)[0]
    Mn_e_p = sp.resistencia(0.0, 'sup', FCE, FYE)[0]
    d = dv['d']
    est = dv['est_hz']
    Vs = est['Av'] * FY * 1000 * d / est['s']
    Vn = dv['Vc_hz'] + Vs
    Vn_e = (dv['Vc_hz'] / math.sqrt(FC) * math.sqrt(FCE)) + est['Av'] * FYE * 1000 * d / est['s']
    rho_n, rho_p = dv['rho_sup'], dv['rho_inf']
    conforme = est['s'] <= d / 3 + 1e-9 and Vs >= 0.75 * dv['Ve']
    v = dv['Ve'] / (b * d * 1000 * math.sqrt(FCE))
    a, bb, IO, LS, CP = asce_viga(rho_n, rho_p, v, conforme)
    ty = My_n * Lf / (6 * EIf)
    tye = Mye_n * Lf / (6 * EIf)
    rho_sh = est['Av'] / (b * est['s'])
    alfa, th_h, mcmy = endurecimiento_haselton(0.0, rho_sh, tye)
    mce = sn.momento_curvatura(0.0, 'inf', FCE, FYE, phye_n)
    return {
        'tipo': 'rectangular', 'b': b, 'h': h, 'b_ala': rs(dv['b_ala'], 4), 'material': 'concreto_28', 'A': rs(b * h, 6),
        'I': rs(I, 6), 'Av': rs(5 / 6 * b * h, 6), 'factor_fisuracion': 0.35,
        'refuerzo': {'superior': f'{dv["sup"][0]} N.º {dv["sup"][1]}', 'inferior': f'{dv["inf"][0]} N.º {dv["inf"][1]}',
                     'estribos': f'N.º {est["num"]} de {est["ramas"]} ramas c/{es(est["s"], 3)} en 2h',
                     'rho_sup': r(rho_n, 5), 'rho_inf': r(rho_p, 5)},
        'My_kNm': r(My_n, 1), 'My_pos_kNm': r(My_p, 1), 'My_neg_kNm': r(My_n, 1),
        'Mn_kNm': r(dv['Mn_neg'], 1), 'Mn_pos_kNm': r(dv['Mn_pos'], 1), 'Mn_neg_kNm': r(dv['Mn_neg'], 1),
        'phiMn_kNm': r(dv['phiMn_neg'], 1), 'phiMn_pos_kNm': r(dv['phiMn_pos'], 1),
        'Mpr_kNm': r(dv['Mpr_neg'], 1), 'Mpr_pos_kNm': r(dv['Mpr_pos'], 1),
        'theta_y': rs(ty, 5), 'theta_p_cap': r(a, 5), 'theta_p_b': r(bb, 5),
        'Vn_kN': r(Vn, 1), 'phiVn_kN': r(0.75 * Vn, 1),
        'My_e_kNm': r(Mye_n, 1), 'My_e_pos_kNm': r(Mye_p, 1), 'My_e_neg_kNm': r(Mye_n, 1),
        'Mn_e_kNm': r(Mn_e_n, 1), 'Mn_e_pos_kNm': r(Mn_e_p, 1), 'Vn_e_kN': r(Vn_e, 1), 'theta_y_e': rs(tye, 5),
        'theta_p_IO': r(IO, 5), 'theta_p_LS': r(LS, 5), 'theta_p_CP': r(CP, 5),
        'endurecimiento': r(alfa, 4), 'histeresis': 'bilineal',
        'momento_curvatura': mc_puntos(mce),
        'calculo': (f'viga T, ala {es(dv["b_ala"])} m; L_f = {es(Lf, 3)} m; ASCE 41 T10-7 {"C" if conforme else "NC"}, '
                    f'(ρ − ρ\')/ρbal = {es((rho_n - rho_p) / (0.85 * BETA1 * FC / FY * 600 / (600 + FY)), 2)}, '
                    f'V/(bw·d·√f\'cE) = {es(v * PSI, 1)} psi; Haselton: Mc/My = {es(mcmy, 3)}, θcap,pl = {es(th_h, 4)}'),
    }


def props_columna_rotula(e, c, tr, Pg):
    """Propiedades de la rótula de una copia de columna (P = carga de gravedad D + 0,25·L, compresión +)."""
    b, Lf = c['b'], e['Lf']
    sec = c['sec']
    I = b ** 4 / 12
    EIf = EC * 1000 * I * 0.70
    My, phy = sec.fluencia(Pg, 'sup', FC, FY)
    Mye, phye = sec.fluencia(Pg, 'sup', FCE, FYE)
    Mn, cc, et, phi = sec.resistencia(Pg, 'sup')
    Mn_e = sec.resistencia(Pg, 'sup', FCE, FYE)[0]
    Mpr = sec.resistencia(Pg, 'sup', FC, FY_PR)[0]
    ty = My * Lf / (6 * EIf)
    tye = Mye * Lf / (6 * EIf)
    VyE = 2 * Mye / Lf
    a, bb, IO, LS, CP = asce_columna(Pg, b * b, tr['rho_t'], VyE / tr['Vn_e'])
    nu = Pg / (b * b * FC * 1000)
    alfa, th_h, mcmy = endurecimiento_haselton(nu, tr['rho_t'], tye)
    mce = sec.momento_curvatura(Pg, 'sup', FCE, FYE, phye)
    pm = []
    for f in (-0.10, 0.0, 0.15, 0.30, 0.45):
        P = f * b * b * FCE * 1000
        pm.append([r(-P, 0), r(sec.fluencia(P, 'sup', FCE, FYE)[0], 0)])
    return {
        'tipo': 'rectangular', 'b': b, 'h': b, 'material': 'concreto_28', 'A': rs(b * b, 6), 'I': rs(I, 6),
        'Av': rs(5 / 6 * b * b, 6), 'factor_fisuracion': 0.70,
        'refuerzo': {'longitudinal': f'{c["n"]} N.º {c["num"]}', 'rho': r(area(c['n'], c['num']) / (b * b), 5),
                     'estribos': f'N.º {tr["num"]} de {tr["ramas"]} ramas por dirección c/{es(tr["s_lo"], 3)} en lo = {es(tr["lo"])} m'},
        'P_gravedad_kN': r(Pg, 1),
        'My_kNm': r(My, 1), 'Mn_kNm': r(Mn, 1), 'phiMn_kNm': r(phi * Mn, 1), 'Mpr_kNm': r(Mpr, 1),
        'theta_y': rs(ty, 5), 'theta_p_cap': r(a, 5), 'theta_p_b': r(bb, 5),
        'Vn_kN': r(tr['Vn'], 1), 'phiVn_kN': r(tr['phiVn'], 1),
        'My_e_kNm': r(Mye, 1), 'Mn_e_kNm': r(Mn_e, 1), 'Vn_e_kN': r(tr['Vn_e'], 1), 'theta_y_e': rs(tye, 5),
        'theta_p_IO': r(IO, 5), 'theta_p_LS': r(LS, 5), 'theta_p_CP': r(CP, 5),
        'interaccion_PM': pm,
        'endurecimiento': r(alfa, 4), 'histeresis': 'bilineal',
        'momento_curvatura': mc_puntos(mce),
        'calculo': (f'P = {es(Pg, 0)} kN; L_f = {es(Lf, 3)} m; ρs = {es(tr["rho_s"], 4)}; ASCE 41 T10-8: '
                    f'N/(Ag·f\'cE) = {es(nu / F_ESP_C, 3)}, ρt = {es(tr["rho_t"], 4)}, VyE/VColOE = {es(VyE / tr["Vn_e"], 2)}; '
                    f'Haselton: Mc/My = {es(mcmy, 3)}, θcap,pl = {es(th_h, 4)}'),
    }


def props_muro_rotula(mu, dm, h1):
    """Propiedades de la rótula de la base de un muro (E1, E3, E16): momento-curvatura con la aleta en compresión
    (My_pos: borde de mayor u comprimido) y en tracción (My_neg), lp = min(0,5·lw; altura del piso 1)."""
    n1 = dm['niveles'][0]
    sec = n1['sec']
    Pg = n1['Pg']
    lw = mu['u1'] - mu['u0']
    lp = min(0.5 * lw, h1)
    EIf = EC * 1000 * mu['I'] * 0.35
    Myp, fyp = sec.fluencia(Pg, 'sup', FC, FY)
    Myn, fyn = sec.fluencia(Pg, 'inf', FC, FY)
    Myep, fyep = sec.fluencia(Pg, 'sup', FCE, FYE)
    Myen, fyen = sec.fluencia(Pg, 'inf', FCE, FYE)
    Mn_e = max(sec.resistencia(Pg, c_, FCE, FYE)[0] for c_ in ('sup', 'inf'))
    My = max(Myp, Myn)
    Mye = max(Myep, Myen)
    ty = My * lp / EIf
    tye = Mye * lp / EIf
    # ASCE/SEI 41-17 Tabla 10-19 (muros controlados por flexión)
    As = sum(a_ for u_, a_ in sec.barras if (u_ - sec.uc) < 0)       # barras del lado traccionado con My_pos
    x1 = (As * FYE * 1000 + Pg) / (mu['t'] * lw * FCE * 1000)
    v = n1['Ve'] / (mu['Av'] * 1000 * math.sqrt(FCE)) * PSI
    tabla = ASCE_MURO[bool(n1['requiere_borde'])]
    a, bb, IO, LS, CP = interp2(x1, 0.10, 0.25, v, 4.0, 6.0, tabla)
    mc_p = sec.momento_curvatura(Pg, 'sup', FCE, FYE, fyep)
    mc_n = sec.momento_curvatura(Pg, 'inf', FCE, FYE, fyen)
    # endurecimiento con el momento-curvatura: H = (Mmax − My)/((φmax − φy)·lp) y α = H/(EI_fis/lp)
    Mmax = max(M for f_, M in mc_p)
    fmax = max(f_ for f_, M in mc_p if M == Mmax)
    alfa = max((Mmax - Myep) / (EIf * max(fmax - fyep, 1e-9)), 1e-3) if fmax > fyep else 0.01
    return {
        'tipo': 'muro', 'b': mu['t'], 'h': rs(lw, 5), 'material': 'concreto_28',
        'aletas': [{'u0': rs(p['u0'], 5), 'u1': rs(p['u1'], 5), 'ancho_m': rs(p['ancho'], 5), 'de': p['de']}
                   for p in mu['partes'] if p['tipo'] != 'alma'],
        'A': rs(mu['A'], 6), 'I': rs(mu['I'], 6), 'Av': rs(mu['Av'], 6), 'factor_fisuracion': 0.35, 'lp_m': rs(lp, 5),
        'refuerzo': {'cortina_vertical': f'2 cortinas N.º {n1["cortina_v"][0]} c/{es(n1["cortina_v"][1])}',
                     'cortina_horizontal': f'2 cortinas N.º {n1["cortina_h"][0]} c/{es(n1["cortina_h"][1])}',
                     'borde_i': f'{n1["borde_i"][0]} N.º {n1["borde_i"][1]}', 'borde_j': f'{n1["borde_j"][0]} N.º {n1["borde_j"][1]}'},
        'P_gravedad_kN': r(Pg, 1),
        'My_kNm': r(My, 0), 'My_pos_kNm': r(Myp, 0), 'My_neg_kNm': r(Myn, 0),
        'Mn_kNm': r(max(n1['Mn_pos'], n1['Mn_neg']), 0), 'phiMn_kNm': r(max(n1['phiMn_pos'], n1['phiMn_neg']), 0),
        'Mpr_kNm': r(n1['Mpr'], 0), 'theta_y': rs(ty, 5), 'theta_p_cap': r(a, 5), 'theta_p_b': r(bb, 5),
        'Vn_kN': r(n1['Vn'], 0), 'phiVn_kN': r(n1['phiVn'], 0),
        'My_e_kNm': r(Mye, 0), 'My_e_pos_kNm': r(Myep, 0), 'My_e_neg_kNm': r(Myen, 0), 'Mn_e_kNm': r(Mn_e, 0),
        'Vn_e_kN': r(n1['Vn_e'], 0), 'theta_y_e': rs(tye, 5),
        'theta_p_IO': r(IO, 5), 'theta_p_LS': r(LS, 5), 'theta_p_CP': r(CP, 5),
        'endurecimiento': r(alfa, 4), 'histeresis': 'bilineal',
        'momento_curvatura': mc_puntos(mc_p), 'momento_curvatura_neg': mc_puntos(mc_n),
        'calculo': (f'aletas efectivas (C.21.9.5.2); P = {es(Pg, 0)} kN; lp = min(0,5·lw; h1) = {es(lp, 3)} m; ASCE 41 '
                    f'T10-19 {"con" if n1["requiere_borde"] else "sin"} borde confinado, ((As − A\'s)·fyE + P)/(tw·lw·f\'cE) = '
                    f'{es(x1, 3)}, V/(tw·lw·√f\'cE) = {es(v, 1)} psi; endurecimiento del momento-curvatura'),
    }


def secciones_y_rotulas(torre, D):
    """Una sección por grupo de elementos con propiedades idénticas (deduplicadas por contenido); nombres estables:
    V-{b}x{h}-{n}, C-{b}-{n}, MURO-{pórtico}. → (secciones, asignación {id del elemento: nombre})."""
    secciones = {}
    por_contenido = {}
    asignacion = {}
    cont = {'V': 0, 'C': 0}

    def registrar(eid, pref, props):
        clave = json.dumps(props, sort_keys=True, ensure_ascii=False)
        if clave in por_contenido:
            asignacion[eid] = por_contenido[clave]
            return
        cont[pref] += 1
        cm_ = int(round(props['b'] * 100))
        nombre = (f'V{cm_}x{int(round(props["h"] * 100))}-{cont[pref]:03d}' if pref == 'V'
                  else f'C{cm_}-{cont[pref]:03d}')
        por_contenido[clave] = nombre
        secciones[nombre] = props
        asignacion[eid] = nombre

    for P in torre['porticos']:
        for e in P['elementos']:
            if e['tipo'] == 'viga':
                registrar(e['id'], 'V', props_viga_rotula(e, D['vigas'][e['id']]))
    for f, c in D['columnas'].items():
        if c.get('falla'):
            continue
        for plano, (pm, e) in sorted(c['copias'].items()):
            registrar(e['id'], 'C', props_columna_rotula(e, c, c['transversal'], c['Pg']))
    for pid, dm in D['muros'].items():
        mu = torre['muros'][pid]
        nombre = f'MURO-{pid}'
        secciones[nombre] = props_muro_rotula(mu, dm, Z[1] - Z[0])
        for e in torre['por_id'][pid]['elementos']:
            asignacion[e['id']] = nombre
    return secciones, asignacion


# =================================================================================================================
# 9. Mampostería (Tomaževič), amortiguamiento, cimentación, losa, escaleras, despiece y cantidades
# =================================================================================================================
MAMPOSTERIA = {
    'ladrillo': {'tipo': 'mamposteria', 'fm_MPa': 4.0, 'Em_MPa': 2800.0, 'Gm_MPa': 1120.0, 'tau0_MPa': 0.12,
                 'peso_kN_m3': 18.0, 't_m': 0.15,
                 'fuente': 'ladrillo prensado a la vista de 15 cm (presupuesto.json 4.03); Em = 700·f\'m y Gm = 0,4·Em '
                           '(NSR-10 D.5.2, por confirmar); τ0 de ensayos de compresión diagonal de mampostería de arcilla '
                           '(Tomaževič, 1999, cap. 3; estimación)'},
    'bloque': {'tipo': 'mamposteria', 'fm_MPa': 3.0, 'Em_MPa': 2100.0, 'Gm_MPa': 840.0, 'tau0_MPa': 0.10,
               'peso_kN_m3': 13.5, 't_m': 0.12,
               'fuente': 'bloque de arcilla N.º 5 de perforación horizontal (presupuesto.json 4.01); mismas relaciones; '
                         'estimación'},
}
ESTADOS_DANO = [{'nombre': 'leve', 'deriva': 0.001}, {'nombre': 'moderado', 'deriva': 0.003},
                {'nombre': 'extenso', 'deriva': 0.006}, {'nombre': 'colapso', 'deriva': 0.01}]


def envolvente_tomazevic(L, t, h, mat, aberturas, sigma0_kPa):
    """Envolvente trilineal de un muro de relleno (Tomaževič, 1999): rigidez de un paño empotrado arriba y abajo con
    flexión y cortante, k0 = 1/(h³/(12·Em·I) + 1,2·h/(Gm·A)), sobre el largo neto L·(1 − aberturas); resistencia a
    tensión diagonal Vmax = A·ft/b·√(1 + σ0/ft) con ft = 1,5·τ0 y b = h/L entre 1 y 1,5 (Turnšek y Čačovič, 1971);
    fisuración en 0,75·Vmax con k0; Vmax a 0,3 % de h y desplazamiento último a 1 % de h; resistencia residual 20 %."""
    Ln = L * (1 - aberturas)
    A = Ln * t
    I = t * Ln ** 3 / 12
    Em, Gm = mat['Em_MPa'] * 1000, mat['Gm_MPa'] * 1000
    k0 = 1 / (h ** 3 / (12 * Em * I) + 1.2 * h / (Gm * A))
    ft = 1.5 * mat['tau0_MPa'] * 1000
    bfac = min(max(h / Ln, 1.0), 1.5)
    Vmax = A * ft / bfac * math.sqrt(1 + sigma0_kPa / ft)
    Vcr = 0.75 * Vmax
    return {'k0_kN_m': r(k0, 0), 'Vcr_kN': r(Vcr, 1), 'dcr_m': rs(Vcr / k0, 4), 'Vmax_kN': r(Vmax, 1),
            'dmax_m': rs(0.003 * h, 4), 'du_m': rs(0.01 * h, 4), 'residual': 0.2}


def rigidez_secante(env, delta):
    """Rigidez secante de la envolvente (kN/m) al desplazamiento delta (m)."""
    if delta <= env['dcr_m']:
        return env['k0_kN_m']
    if delta <= env['dmax_m']:
        V = env['Vcr_kN'] + (env['Vmax_kN'] - env['Vcr_kN']) * (delta - env['dcr_m']) / (env['dmax_m'] - env['dcr_m'])
        return V / delta
    return env['Vmax_kN'] / delta


def mamposteria(torre, presupuesto):
    """Muros de mampostería como resortes laterales (E5): fachada en ladrillo en las líneas perimetrales de cada piso
    (25 % de vanos: 600 m² de ventanas sobre 2.407 m² de fachada, presupuesto.json 4.03) y muros de bloque repartidos
    por partes iguales en las líneas interiores de cada dirección (1.557 m² de bloque, presupuesto.json 4.01, por piso
    en proporción al área). Todos aislados (grupo IV: NSR-10 A.9, separación de la estructura); el escenario «sin
    aislar» lo da el motor con noEstructurales = 'confinados' (por eso no se escribe un segundo juego: se contaría dos
    veces). Altura libre = entrepiso menos el peralte de la viga de la línea."""
    nv = torre['niveles']
    a_bloque = item(presupuesto, '4.01')['cantidad']
    area_pisos = sum(area_poligono(n['contorno']) for n in nv)
    resortes = []
    for k in range(1, NIV + 1):
        n = nv[k - 1]
        h_ent = n['h']
        ys = Y_RETROCESO if k == 4 else -19.6
        fachadas = [('x', '1' if k < 4 else '3', ys, -13.0, 8.6), ('x', '7', 22.4, -13.0, 8.6),
                    ('y', 'A', -13.0, ys, 22.4), ('y', 'D', 8.6, ys, 22.4)]
        lineas_muro_x = {torre['muros'][p]['def']['c'] for p in torre['muros'] if torre['muros'][p]['def']['dir'] == 'x'}
        for d, lin, c, a0, a1 in fachadas:
            if d == 'x' and c in lineas_muro_x:
                a1 = 1.4                                    # el vano C-D de esa línea es el muro de concreto
            pid = f'{"X" if d == "x" else "Y"}-{lin}'
            P = torre['por_id'][pid]
            hv = max(e['h'] for e in P['elementos'] if e['tipo'] == 'viga' and e['nivel'] == k)
            h = h_ent - hv
            L = a1 - a0
            mat = MAMPOSTERIA['ladrillo']
            sigma0 = mat['peso_kN_m3'] * h / 2
            env = envolvente_tomazevic(L, mat['t_m'], h, mat, 0.25, sigma0)
            pos = [a0, c, a1, c] if d == 'x' else [c, a0, c, a1]
            resortes.append({'id': f'M-F{lin}-{k}', 'tipo': 'muro_mamposteria', 'direccion': d, 'coordenada': c,
                             'nivel': k, 'aislado': True, 'portico': pid, 'posicion': pos, 'L': r(L, 3),
                             't': mat['t_m'], 'h': r(h, 3), 'material': 'ladrillo', 'aberturas_pct': 25,
                             'envolvente': env, 'histeresis': 'tomazevic', 'modo_falla': 'tension_diagonal',
                             'estados_de_dano': ESTADOS_DANO,
                             'calculo': f'fachada en ladrillo de 15 cm en la línea {lin}, piso {k}: largo {es(L)} m con 25 % de vanos, '
                                        f'altura libre {es(h)} m; envolvente de Tomaževič con σ0 = {es(sigma0, 1)} kPa (peso propio)'})
        # bloque interior: el área del piso repartida mitad en x y mitad en y, por partes iguales entre las líneas
        a_piso = a_bloque * area_poligono(n['contorno']) / area_pisos
        L_dir = a_piso / (h_ent - 0.8) / 2
        int_x = [(ny, yy) for ny, yy in EJES_Y if ny not in ('1', '7') and (k < 4 or yy > Y_RETROCESO + 1e-9)]
        int_y = [('B', EJX['B']), ('C', EJX['C'])]
        for d, lineas in (('x', int_x), ('y', int_y)):
            for lin, c in lineas:
                pid = f'{"X" if d == "x" else "Y"}-{lin}'
                P = torre['por_id'][pid]
                hv = max(e['h'] for e in P['elementos'] if e['tipo'] == 'viga' and e['nivel'] == k)
                h = h_ent - hv
                L = L_dir / len(lineas)
                mat = MAMPOSTERIA['bloque']
                sigma0 = mat['peso_kN_m3'] * h / 2
                env = envolvente_tomazevic(L, mat['t_m'], h, mat, 0.15, sigma0)
                cont = n['contorno']
                lo_, hi_ = ((min(q[0] for q in cont), max(q[0] for q in cont)) if d == 'x' else
                            (min(q[1] for q in cont), max(q[1] for q in cont)))
                mid = (lo_ + hi_) / 2
                pos = [mid - L / 2, c, mid + L / 2, c] if d == 'x' else [c, mid - L / 2, c, mid + L / 2]
                resortes.append({'id': f'M-B{lin}-{k}', 'tipo': 'muro_mamposteria', 'direccion': d, 'coordenada': c,
                                 'nivel': k, 'aislado': True, 'portico': pid, 'posicion': [r(x_, 3) for x_ in pos],
                                 'L': r(L, 3), 't': mat['t_m'], 'h': r(h, 3), 'material': 'bloque', 'aberturas_pct': 15,
                                 'envolvente': env, 'histeresis': 'tomazevic', 'modo_falla': 'tension_diagonal',
                                 'estados_de_dano': ESTADOS_DANO,
                                 'calculo': f'muros de bloque del piso {k} en la línea {lin} (estimación: {es(a_piso, 0)} m² del piso '
                                            f'repartidos mitad en x y mitad en y entre {len(lineas)} líneas; posición '
                                            f'representativa): largo {es(L)} m, 15 % de vanos, altura libre {es(h)} m'})
    return resortes


def resortes_para_analisis(resortes, niveles, deriva=0.002):
    """Resortes lineales del escenario con la mampostería adherida para el umbral de daño: rigidez secante de la
    envolvente a la deriva límite de 0,2 % (linealización equivalente)."""
    out = []
    for rr in resortes:
        h = niveles[rr['nivel'] - 1]['h']
        out.append({'portico': rr['portico'], 'nivel': rr['nivel'], 'k': rigidez_secante(rr['envolvente'], deriva * h)})
    return out


def amortiguamiento_y_anclas(mod, xi=XI):
    """Períodos ancla de Rayleigh (E8) con la rigidez inicial (elástica condensada + K_PΔ): Ti = T1 y Tj = el menor
    entre el período con el que la masa participativa acumulada llega a 90 % en x y en y y 0,2·T1. a0 y a1 con ξ
    exacto en las dos anclas, como el motor (ESQUEMA.md, «Amortiguamiento»): ξ_r = (a0 + a1·k_r)/(2ω_r) con
    k_r = φ_rᵀK_elφ_r (φ normalizados a la masa; K_el sin P-Delta ni mampostería) y ρ = k/ω² en cada ancla
    (interpolada linealmente en ln ω entre modos vecinos si el ancla no es un modo): a1 = 2ξ(ωj − ωi)/(ρj·ωj² −
    ρi·ωi²), a0 = 2ξ·ωi − a1·ρi·ωi² (con ρ = 1, la fórmula de siempre). ξ efectivo de los 12 primeros modos."""
    modos = mod.modos(12, pdelta=True)
    T1 = modos[0]['T']
    cx = cy = 0.0
    Tj = None
    for m in modos:
        cx += m['mx']
        cy += m['my']
        if cx >= 0.9 and cy >= 0.9:
            Tj = m['T']
            break
    Tj = min(Tj if Tj else modos[-1]['T'], 0.2 * T1)
    n = 3 * mod.N
    kel = []
    for m in modos:
        phi = m['phi']
        mn = sum(mod.m[a] * phi[a] ** 2 for a in range(n))
        kel.append(sum(phi[a] * mod.K[a][b] * phi[b] for a in range(n) for b in range(n)) / mn)
    om = [m['w'] for m in modos]
    rho_m = [k / w ** 2 for k, w in zip(kel, om)]

    def rho(w):
        if w <= om[0]:
            return rho_m[0]
        if w >= om[-1]:
            return rho_m[-1]
        r = 1
        while om[r] < w:
            r += 1
        t = math.log(w / om[r - 1]) / math.log(om[r] / om[r - 1]) if om[r] > om[r - 1] else 0.0
        return rho_m[r - 1] + t * (rho_m[r] - rho_m[r - 1])

    wi, wj = 2 * math.pi / T1, 2 * math.pi / Tj
    ri, rj = rho(wi), rho(wj)
    a1 = 2 * xi * (wj - wi) / (rj * wj ** 2 - ri * wi ** 2)
    a0 = 2 * xi * wi - a1 * ri * wi ** 2
    xis = [(a0 + a1 * k) / (2 * w) for k, w in zip(kel, om)]
    return {'modos': modos, 'Ti': T1, 'Tj': Tj, 'a0': a0, 'a1': a1, 'xi': xis, 'cum_x': cx, 'cum_y': cy}


# ---- cimentación (contrato 17.2) ---------------------------------------------------------------------------------
# Perfil de suelo SUPUESTO (estimación hasta el estudio geotécnico; perfil D de amenaza.json): aluvial del Magdalena,
# relleno y descapote hasta 1,5 m, limo arcilloso de consistencia media hasta 6,0 m (Su = 60 kPa) y arena media a densa
# debajo (N60 = 25), con el nivel freático a 1,0 m. Capacidad de pilotes preexcavados con el método de la FHWA
# (O'Neill y Reese, 1999; Brown y otros, 2010, FHWA-NHI-10-016): fuste en arcilla α·Su con α = 0,55 sin el primer
# 1,5 m del fuste; fuste en arena β·σ'v con β = 1,5 − 0,245·√z (z en m, 0,25 ≤ β ≤ 1,2); punta en arena 57,5·N60 kPa
# (≤ 2,9 MPa). Factores de seguridad de la NSR-10 Tabla H.4.7-1 (por confirmar): 3,0 con D + L y 1,5 con el sismo.
SUELO = {
    'nivel_freatico_m': 1.0, 'gamma_kN_m3': 18.0, 'gamma_sum_kN_m3': 8.0,
    'capas': [
        {'hasta_m': 1.5, 'tipo': 'relleno', 'nota': 'relleno y descapote: no se cuenta'},
        {'hasta_m': 6.0, 'tipo': 'arcilla', 'Su_kPa': 60.0, 'alfa': 0.55, 'nota': 'limo arcilloso de consistencia media'},
        {'hasta_m': 40.0, 'tipo': 'arena', 'N60': 25, 'nota': 'arena media a densa'},
    ],
    'kh_nota': 'módulo de reacción horizontal kh = 67·Su/D (Davisson, 1970) en el limo de la cabeza del pilote',
    'fuente': "estimación con los métodos de O'Neill y Reese (1999) y FHWA-NHI-10-016 (Brown y otros, 2010); "
              'la fijan el estudio geotécnico y las pruebas de carga (NSR-10 H.4 y H.6, por confirmar)',
}
FS_ESTATICO, FS_SISMO = 3.0, 1.5
D_PILOTE = 0.60
COTA_FONDO_DADO = 1.50          # m bajo el piso terminado del piso 1 (dado de 1,10 m bajo 0,40 m de relleno y contrapiso)
S_PILOTES = 3 * D_PILOTE        # separación mínima entre centros (3·D; NSR-10 H.?, por confirmar)
BORDE_PILOTE = D_PILOTE / 2 + 0.15


def sigma_v_ef(z):
    """Esfuerzo vertical efectivo (kPa) a la profundidad z (m) desde el piso terminado."""
    nf = SUELO['nivel_freatico_m']
    if z <= nf:
        return SUELO['gamma_kN_m3'] * z
    return SUELO['gamma_kN_m3'] * nf + SUELO['gamma_sum_kN_m3'] * (z - nf)


def capacidad_pilote(L, D=D_PILOTE, z0=COTA_FONDO_DADO):
    """Capacidad última (kN) de un pilote preexcavado de diámetro D y largo L con la cabeza a z0: fuste por capas
    (integración con paso de 0,05 m) y punta; tracción = 0,75 del fuste (estimación conservadora para la arena)."""
    per = math.pi * D
    Qs_arc = Qs_are = 0.0
    n = int(round(L / 0.05))
    for i in range(n):
        z = z0 + (i + 0.5) * 0.05
        capa = next(c for c in SUELO['capas'] if z <= c['hasta_m'])
        if capa['tipo'] == 'arcilla':
            if z - z0 < 1.5 or z > z0 + L - D:
                continue                          # FHWA: sin el primer 1,5 m ni el último diámetro en arcilla
            fs = capa['alfa'] * capa['Su_kPa']
            Qs_arc += fs * per * 0.05
        elif capa['tipo'] == 'arena':
            beta = min(max(1.5 - 0.245 * math.sqrt(z), 0.25), 1.2)
            Qs_are += beta * sigma_v_ef(z) * per * 0.05
    zt = z0 + L
    capa_t = next(c for c in SUELO['capas'] if zt <= c['hasta_m'])
    qp = min(57.5 * capa_t['N60'], 2900.0) if capa_t['tipo'] == 'arena' else 9 * capa_t['Su_kPa']
    Qp = qp * math.pi * D * D / 4
    Qs = Qs_arc + Qs_are
    return {'L': L, 'Qs_arcilla': Qs_arc, 'Qs_arena': Qs_are, 'Qs': Qs, 'qp_kPa': qp, 'Qp': Qp, 'Qult': Qs + Qp,
            'Qadm': (Qs + Qp) / FS_ESTATICO, 'Qsismo': (Qs + Qp) / FS_SISMO, 'Tult': 0.75 * Qs, 'Tsismo': 0.75 * Qs / FS_SISMO,
            # peso neto del pilote: el del concreto menos el del suelo que reemplaza (la capacidad se mide en la cabeza)
            'peso': (GAMMA_C - SUELO['gamma_kN_m3']) * math.pi * D * D / 4 * L}


def disposicion(n, s=S_PILOTES):
    """Posiciones (x, y) de n pilotes respecto al centro del dado: 2 en línea, 3 en triángulo, 4 en cuadro, 5 en
    tresbolillo y rejillas de 2×3, 3×3, 3×4 y 4×4."""
    if n == 1:
        return [(0.0, 0.0)]
    if n == 2:
        return [(-s / 2, 0.0), (s / 2, 0.0)]
    if n == 3:
        h = s * math.sqrt(3) / 2
        return [(-s / 2, -h / 3), (s / 2, -h / 3), (0.0, 2 * h / 3)]
    if n == 5:
        a = s / math.sqrt(2)
        return [(-a, -a), (a, -a), (-a, a), (a, a), (0.0, 0.0)]
    filas = {4: (2, 2), 6: (2, 3), 9: (3, 3), 12: (3, 4), 16: (4, 4)}[n]
    out = []
    for i in range(filas[0]):
        for j in range(filas[1]):
            out.append(((j - (filas[1] - 1) / 2) * s, (i - (filas[0] - 1) / 2) * s))
    return out


def reacciones_pilotes(pos, N, Mx, My):
    """Reacciones de un grupo de pilotes bajo un dado rígido: P_i = N/n + My·x_i/Σx² + Mx·y_i/Σy² (Mx: momento que
    carga los pilotes de y > 0; My: los de x > 0). N y P de compresión positivos."""
    n = len(pos)
    sx = sum(x * x for x, y in pos)
    sy = sum(y * y for x, y in pos)
    return [N / n + (My * x / sx if sx > 0 else 0.0) + (Mx * y / sy if sy > 0 else 0.0) for x, y in pos]


def seccion_circular(D, n, num, rec):
    """Pilote circular por franjas (30) con n barras N.º num repartidas en un círculo: para el diagrama P-M."""
    R = D / 2
    k = 30
    rect = []
    for i in range(k):
        u0 = -R + 2 * R * i / k
        u1 = -R + 2 * R * (i + 1) / k
        um = (u0 + u1) / 2
        rect.append((u0 + R, u1 + R, 2 * math.sqrt(max(R * R - um * um, 0.0))))
    rb = R - rec - BARRAS[3][0] / 1000 - BARRAS[num][0] / 2000
    barras = [(R + rb * math.cos(2 * math.pi * i / n), area(1, num)) for i in range(n)]
    return Seccion(rect, barras, [], rho_s=0.0, ke=0.95)


def reacciones_base(torre, D, A, Omega0):
    """Reacciones en la base de cada apoyo (columnas físicas y muros) por caso: D, L, Lr (gravedad) y sísmico de diseño
    reducido por R en x e y (100 % + 30 %, valores absolutos): N (compresión +), Mx (momento que carga el lado +y),
    My (carga el lado +x) y los cortantes."""
    res = A['resp']
    G_ = D['G']
    E_el = D['E_el']
    out = {}
    for f, c in D['columnas'].items():
        if c.get('k') != 1 or c.get('falla'):
            continue
        g = {cs: 0.0 for cs in ('D', 'L', 'Lr')}
        ex = {'N': [0.0, 0.0], 'Mx': [0.0, 0.0], 'My': [0.0, 0.0], 'Vx': [0.0, 0.0], 'Vy': [0.0, 0.0]}
        gm = {'Mx': {cs: 0.0 for cs in g}, 'My': {cs: 0.0 for cs in g}}
        for plano, (pm, e) in c['copias'].items():
            for cs in g:
                fz = fuerzas_elemento(res, G_[cs], e['id'])
                g[cs] += -fz[3]
                # momento de la base (extremo i): en la copia X carga el lado +x (My); en la Y, el lado +y (Mx)
                gm['My' if plano == 'X' else 'Mx'][cs] += fz[0]
            for comb in (0, 1):
                ex['N'][comb] += E_el(e['id'], 3, True)[comb]
                if plano == 'X':
                    ex['My'][comb] += E_el(e['id'], 0, True)[comb]
                    ex['Vx'][comb] += E_el(e['id'], 2, True)[comb]
                else:
                    ex['Mx'][comb] += E_el(e['id'], 0, True)[comb]
                    ex['Vy'][comb] += E_el(e['id'], 2, True)[comb]
        pm, e = next(iter(c['copias'].values()))
        nx, ny = e['eje'].split('-')
        # sismo de capacidad: Ω0·E sin pasar de lo que la columna puede entregar (Mpr en la base, Ve) ni, en la carga
        # axial, de la suma de los cortantes de capacidad (Mpr⁻ + Mpr⁺)/L_f de las vigas que llegan a la columna en
        # todos los pisos de encima (lo más que el sismo puede colgar o empujar sobre ella)
        Mpr = c['transversal']['Mpr']
        Ve = c['transversal']['Ve']
        pila = [ff for ff in D['columnas'] if ff.rsplit('-', 1)[0] == f.rsplit('-', 1)[0]]
        Ncap = 0.0
        for ff in pila:
            for plano, (pm_, e_) in D['columnas'][ff]['copias'].items():
                for x_ in pm_.el:
                    ev = x_['e']
                    if ev['tipo'] == 'viga' and e_['j'] in (ev['i'], ev['j']):
                        dv = D['vigas'][ev['id']]
                        Ncap += dv['Vmpr']
        ecap = {'N': [min(Omega0 * v, Ncap) for v in ex['N']], 'Mx': [min(Omega0 * v, Mpr) for v in ex['Mx']],
                'My': [min(Omega0 * v, Mpr) for v in ex['My']], 'Vx': [min(Omega0 * v, Ve) for v in ex['Vx']],
                'Vy': [min(Omega0 * v, Ve) for v in ex['Vy']]}
        out[f'C-{nx}{ny}'] = {'tipo': 'columna', 'x': EJX[nx], 'y': EJY[ny], 'b': c['b'], 'g': g, 'gm': gm, 'E': ex,
                              'Ecap': ecap, 'eje': f'{nx}-{ny}'}
    for pid, mu in torre['muros'].items():
        m = mu['def']
        e1 = next(e for e in torre['por_id'][pid]['elementos'] if e['nivel'] == 1)
        g = {cs: -fuerzas_elemento(res, G_[cs], e1['id'])[3] for cs in ('D', 'L', 'Lr')}
        Mb = [E_el(e1['id'], 0, False)[cmb] for cmb in (0, 1)]
        Vb = [E_el(e1['id'], 2, False)[cmb] for cmb in (0, 1)]
        if m['dir'] == 'x':
            x, y = mu['uc'], m['c']
            ex = {'N': [0.0, 0.0], 'Mx': [0.0, 0.0], 'My': Mb, 'Vx': Vb, 'Vy': [0.0, 0.0]}
        else:
            x, y = m['c'], mu['uc']
            ex = {'N': [0.0, 0.0], 'Mx': Mb, 'My': [0.0, 0.0], 'Vx': [0.0, 0.0], 'Vy': Vb}
        # sismo de capacidad del muro: el momento probable de la base (Mpr con 1,25·fy) y su cortante por capacidad Ve,
        # sin pasar de Ω0·E (lo que el muro puede entregar a la cimentación; diseño por capacidad)
        n1 = D['muros'][pid]['niveles'][0]
        Mcap = [min(Omega0 * v, n1['Mpr']) for v in Mb]
        Vcap = [min(Omega0 * v, n1['Ve']) for v in Vb]
        if m['dir'] == 'x':
            ecap = {'N': [0.0, 0.0], 'Mx': [0.0, 0.0], 'My': Mcap, 'Vx': Vcap, 'Vy': [0.0, 0.0]}
        else:
            ecap = {'N': [0.0, 0.0], 'Mx': Mcap, 'My': [0.0, 0.0], 'Vx': [0.0, 0.0], 'Vy': Vcap}
        out[pid] = {'tipo': 'muro', 'x': x, 'y': y, 'g': g, 'gm': {'Mx': {cs: 0.0 for cs in g}, 'My': {cs: 0.0 for cs in g}},
                    'E': ex, 'Ecap': ecap, 'nucleo': m['nucleo']}
    return out


def combinaciones_cimentacion(cargas, R, Omega0):
    """Combinaciones sobre un grupo de apoyos ya llevados al centro del grupo: lista de (nombre, N, Mx, My, tipo).
    'estatico': D + L + Lr en servicio (FS 3,0 de H.4.7-1); 'sismo': servicio con el sismo de diseño de B.2.3 (esfuerzos
    de trabajo: D + 0,7E y D + 0,75L + 0,75·0,7E, con E = Fs/R; FS 1,5); 'sismo_min': 0,6D − 0,7E (tracción);
    'capacidad': D + 0,25L ± Ecap, con el sismo que de verdad pueden entregar los muros y columnas (Mpr y Ve, sin pasar de
    Ω0·E): la cimentación no debe fallar antes que la superestructura (FS 1,0 sobre la capacidad última); 'mayorada':
    NSR-10 B.2.4 (1,4D; 1,2D + 1,6L + 0,5Lr; 1,2D + 1,0L ± E; 0,9D ± E) para el refuerzo."""
    g, E, Ec = cargas['g'], cargas['E'], cargas['Ecap']

    def grav(fD, fL, fLr):
        return (fD * g['D'] + fL * g['L'] + fLr * g['Lr'],
                sum(f * cargas['Mxg'][cs] for f, cs in ((fD, 'D'), (fL, 'L'), (fLr, 'Lr'))),
                sum(f * cargas['Myg'][cs] for f, cs in ((fD, 'D'), (fL, 'L'), (fLr, 'Lr'))))
    out = [('D + L + Lr', *grav(1, 1, 1), 'estatico')]
    for cmb in (0, 1):
        nc = '100 % x + 30 % y' if cmb == 0 else '30 % x + 100 % y'
        for sN, sx, sy in ((1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)):
            NE, MxE, MyE = sN * E['N'][cmb], sx * E['Mx'][cmb], sy * E['My'][cmb]
            NC, MxC, MyC = sN * Ec['N'][cmb], sx * Ec['Mx'][cmb], sy * Ec['My'][cmb]
            for nombre, (fD, fL, fLr), fE, Es, tipo in (
                    ('D + 0,7E', (1, 0, 0), 0.7, (NE, MxE, MyE), 'sismo'),
                    ('D + 0,75(L + Lr) + 0,525E', (1, 0.75, 0.75), 0.525, (NE, MxE, MyE), 'sismo'),
                    ('0,6D + 0,7E', (0.6, 0, 0), 0.7, (NE, MxE, MyE), 'sismo_min'),
                    ('D + 0,25L + Ecap', (1, 0.25, 0), 1.0, (NC, MxC, MyC), 'capacidad'),
                    ('0,9D + Ecap', (0.9, 0, 0), 1.0, (NC, MxC, MyC), 'capacidad'),
                    ('1,2D + 1,0L + E', (1.2, 1.0, 0), 1.0, (NE, MxE, MyE), 'mayorada'),
                    ('0,9D + E', (0.9, 0, 0), 1.0, (NE, MxE, MyE), 'mayorada')):
                N0, Mx0, My0 = grav(fD, fL, fLr)
                out.append((f'{nombre} ({nc})', N0 + fE * Es[0], Mx0 + fE * Es[1], My0 + fE * Es[2], tipo))
    out.append(('1,4D', *grav(1.4, 0, 0), 'mayorada'))
    out.append(('1,2D + 1,6L + 0,5Lr', *grav(1.2, 1.6, 0.5), 'mayorada'))
    return out


def barras_por_metro(As_m2_por_m, nums=(5, 6, 7, 8), s_max=0.30, s_min=0.10):
    """Barras (N.º, separación) que dan As (m²/m) con la menor área; separación múltiplo de 2,5 cm."""
    mejor = None
    for num in nums:
        Ab = BARRAS[num][1] * 1e-6
        s_ = math.floor(min(Ab / max(As_m2_por_m, 1e-9), s_max) / 0.025 + 1e-9) * 0.025
        if s_ < s_min:
            continue
        A_real = Ab / s_
        clave = (round(A_real, 9), num)
        if mejor is None or clave < mejor[0]:
            mejor = (clave, (num, round(s_, 3), A_real))
    return mejor[1] if mejor else (8, s_min, BARRAS[8][1] * 1e-6 / s_min)


def punzonamiento_vc(b0, d, beta=1.0, alfa_s=40):
    """Vc de punzonamiento (kN), NSR-10 C.11.11.2.1: el menor de 0,17(1 + 2/β), 0,083(αs·d/b0 + 2) y 0,33 por √f'c·b0·d."""
    k = min(0.17 * (1 + 2 / beta), 0.083 * (alfa_s * d / b0 + 2), 0.33)
    return k * math.sqrt(FC) * b0 * d * 1000


def disenar_dado(apoyo, combos, pos, B, Lc, b_col, cap_pilote, nombre):
    """Dado de un grupo de pilotes bajo una columna: espesor por punzonamiento de la columna y de la esquina, cortante
    en una dirección a d de la cara y flexión en la cara de la columna (NSR-10 C.15.5 y C.11.11), con las reacciones
    mayoradas de los pilotes; parrilla inferior en las dos direcciones, parrilla superior y refuerzo lateral."""
    rec = REC['dado_fondo']
    may = [c for c in combos if c[4] in ('mayorada',)]
    for h in [x / 20 for x in range(16, 61)]:                   # 0,80 a 3,00 m
        d = h - rec - 0.10 - BARRAS[7][0] / 1000                 # el pilote entra 0,10 m en el dado
        ok = True
        peor = {}
        Vu_p_max = 0.0
        Mu = {'x': 0.0, 'y': 0.0}
        Vu1 = {'x': 0.0, 'y': 0.0}
        for nombre_c, N, Mx, My, _ in may:
            Pi = reacciones_pilotes(pos, N, Mx, My)
            Vu_p_max = max(Vu_p_max, max(Pi))
            # punzonamiento de la columna: pilotes con el centro fuera del perímetro crítico a d/2
            a = b_col / 2 + d / 2
            fuera = sum(P for P, (x, y) in zip(Pi, pos) if abs(x) > a or abs(y) > a)
            b0 = 4 * (b_col + d)
            if fuera > 0.75 * punzonamiento_vc(b0, d):
                ok = False
            for eje, idx in (('x', 0), ('y', 1)):
                for lado in (1, -1):
                    sel = [(P, q[idx] * lado) for P, q in zip(Pi, pos) if q[idx] * lado > b_col / 2]
                    M = sum(P * (u - b_col / 2) for P, u in sel)
                    V = sum(P for P, u in sel if u > b_col / 2 + d)
                    Mu[eje] = max(Mu[eje], M)
                    Vu1[eje] = max(Vu1[eje], V)
        ancho = {'x': Lc, 'y': B}
        for eje in ('x', 'y'):
            if Vu1[eje] > 0.75 * 0.17 * math.sqrt(FC) * ancho[eje] * d * 1000:
                ok = False
        # punzonamiento del pilote más cargado en la esquina: perímetro de medio círculo a d/2 más los dos bordes
        b0p = math.pi * (D_PILOTE + d) / 2 + 2 * BORDE_PILOTE
        if Vu_p_max > 0.75 * punzonamiento_vc(b0p, d, 1.0, 20):
            ok = False
        if any(as_requerida(Mu[e_], {'x': Lc, 'y': B}[e_], d) / {'x': Lc, 'y': B}[e_] > BARRAS[8][1] * 1e-6 / 0.10
               for e_ in ('x', 'y')):
            ok = False
        if ok:
            break
    # flexión: refuerzo inferior en las dos direcciones (≥ 0,0018·b·h, C.7.12; separación ≤ 0,30 m)
    refuerzo = {}
    for eje, ancho_ in (('x', Lc), ('y', B)):
        As = max(as_requerida(Mu[eje], ancho_, d), 0.0018 * ancho_ * h)
        num, s_, Ar = barras_por_metro(As / ancho_)
        refuerzo[f'inferior_{eje}'] = {'num': num, 's': s_, 'n': int((ancho_ - 2 * 0.075) / s_) + 1, 'As_req_mm2': As * 1e6,
                                       'Mu_kNm': Mu[eje]}
    # superior: tracción arriba solo con pilotes en tracción (0,9D − Ω0·E); mínimo de retracción en la cara superior
    Tmin = min(min(reacciones_pilotes(pos, N, Mx, My)) for _, N, Mx, My, t in combos if t in ('mayorada', 'capacidad'))
    num_s, s_s, _ = barras_por_metro(max(0.0009 * h, 0.0), nums=(5, 6), s_max=0.25)
    refuerzo['superior'] = {'num': num_s, 's': s_s, 'nota': 'parrilla superior en las dos direcciones (retracción y '
                            'tracción de pilotes en 0,9D − Ω0·E)', 'P_min_pilote_kN': Tmin}
    refuerzo['lateral'] = {'num': 4, 's': 0.30, 'nota': 'refuerzo perimetral de piel (C.10.6.7, por confirmar)'}
    return {'h': h, 'd': d, 'Mu': Mu, 'Vu1': Vu1, 'Vu_pilote': Vu_p_max, 'refuerzo': refuerzo, 'ok': ok}


def opciones_pilotes():
    return (2, 3, 4, 5, 6, 9, 12, 16)


def tamano_dado(n, b_col):
    pos = disposicion(n)
    xs = [x for x, y in pos]
    ys = [y for x, y in pos]
    Lc = max(max(xs) - min(xs) + 2 * BORDE_PILOTE, b_col + 0.30)
    B = max(max(ys) - min(ys) + 2 * BORDE_PILOTE, b_col + 0.30)
    return pos, round(math.ceil(Lc / 0.05 - 1e-9) * 0.05, 3), round(math.ceil(B / 0.05 - 1e-9) * 0.05, 3)


def verificar_grupo(combos, pos, cap):
    """Reacciones extremas por tipo de combinación y si cumplen la capacidad geotécnica."""
    ext = {}
    for nombre_c, N, Mx, My, tipo in combos:
        Pi = reacciones_pilotes(pos, N, Mx, My)
        e = ext.setdefault(tipo, {'max': -1e99, 'min': 1e99, 'max_c': '', 'min_c': ''})
        if max(Pi) > e['max']:
            e['max'], e['max_c'] = max(Pi), nombre_c
        if min(Pi) < e['min']:
            e['min'], e['min_c'] = min(Pi), nombre_c
    # geotecnia: NSR-10 H.4.7-1 con las combinaciones de servicio (B.2.3). El sismo de capacidad no se usa para la
    # capacidad geotécnica (si los pilotes llegan a su capacidad última bajo el momento probable de un muro, el núcleo
    # se mece sobre su cimentación y eso limita la demanda; ASCE/SEI 41-17 8.4 y ASCE/SEI 7-16 12.13.5 tampoco piden Ω0
    # para el suelo): se informa en 'capacidad' y sí se usa para el refuerzo y el anclaje de los pilotes
    ok = (ext['estatico']['max'] <= cap['Qadm'] and ext['sismo']['max'] <= cap['Qsismo']
          and ext['sismo_min']['min'] >= -cap['Tsismo'])
    # y que el pilote de 0,60 m se pueda armar con la tracción y la compresión del sismo de capacidad: a lo sumo 16 N.º 8
    # (separación libre ≥ 1,5·db en el círculo) con margen para el momento de la cabeza (60 % de φ·As·fy en tracción y
    # 80 % de φPn,max en compresión; disenar_pilote hace después la revisión P-M completa)
    As_max = area(16, 8)
    Ag = math.pi * D_PILOTE ** 2 / 4
    T_lim = 0.6 * 0.9 * As_max * FY * 1000
    P_lim = 0.8 * 0.85 * 0.75 * (0.85 * FC * (Ag - As_max) + FY * As_max) * 1000
    ok = ok and -ext['capacidad']['min'] <= T_lim and ext['capacidad']['max'] <= P_lim
    return ok, ext


def rect_planta_muro(mu):
    """Rectángulos en planta (x0, y0, x1, y1) de las partes de un muro (alma, aletas propias y columna de borde)."""
    m = mu['def']
    out = []
    for p in mu['partes']:
        if p['tipo'] == 'aleta' and p['de'].startswith('alma del muro'):
            continue                                  # es el alma de otro muro: la pone ese muro
        if p['tipo'] == 'columna':
            w = p['ancho']
        elif p['tipo'] == 'aleta':
            w = mu['t']                               # en planta el machón o la cara del foso es del espesor del muro
        else:
            w = mu['t']
        if m['dir'] == 'x':
            out.append((p['u0'], m['c'] - w / 2, p['u1'], m['c'] + w / 2))
        else:
            out.append((m['c'] - w / 2, p['u0'], m['c'] + w / 2, p['u1']))
    return out


def cimentacion(torre, D, A, S, presupuesto):
    """Prediseño de la cimentación (contrato 17.2): dados de pilotes bajo las columnas, losas de pilotes (dados
    combinados) bajo los núcleos, largo de pilote escogido por el menor total de metros, pilotes armados, vigas de
    amarre, contrapiso, fosos y cisternas. La base del modelo sísmico sigue empotrada en la cara superior de los
    dados (sin interacción suelo-estructura, 17.2)."""
    R, Om = S['R'], S['Omega0']
    reac = reacciones_base(torre, D, A, Om)
    # ---- grupos: un dado por columna; una losa de pilotes por núcleo con sus muros y las columnas que caen en ella --
    grupos = {}
    for pid, mu in torre['muros'].items():
        nuc = mu['def']['nucleo']
        g = grupos.setdefault(f'LP-{nuc}', {'tipo': 'losa', 'apoyos': [], 'rects': []})
        g['apoyos'].append(pid)
        g['rects'] += rect_planta_muro(mu)
    margen = BORDE_PILOTE
    for gid, g in grupos.items():
        xs = [q[0] for q in g['rects']] + [q[2] for q in g['rects']]
        ys = [q[1] for q in g['rects']] + [q[3] for q in g['rects']]
        g['caja'] = [min(xs) - margen, min(ys) - margen, max(xs) + margen, max(ys) + margen]
    columnas = sorted([k for k, v in reac.items() if v['tipo'] == 'columna'])
    # columnas dentro de una losa o cuyo dado de 4 pilotes la toca: se unen a la losa (y la losa crece)
    for _ in range(3):
        for cid in columnas:
            if any(cid in g['apoyos'] for g in grupos.values()):
                continue
            a = reac[cid]
            _, Lc, B = tamano_dado(4, a['b'])
            dado = [a['x'] - Lc / 2, a['y'] - B / 2, a['x'] + Lc / 2, a['y'] + B / 2]
            for gid, g in grupos.items():
                c_ = g['caja']
                if dado[0] < c_[2] and dado[2] > c_[0] and dado[1] < c_[3] and dado[3] > c_[1]:
                    g['apoyos'].append(cid)
                    g['caja'] = [min(c_[0], a['x'] - a['b'] / 2 - margen), min(c_[1], a['y'] - a['b'] / 2 - margen),
                                 max(c_[2], a['x'] + a['b'] / 2 + margen), max(c_[3], a['y'] + a['b'] / 2 + margen)]
                    break
    for cid in columnas:
        if not any(cid in g['apoyos'] for g in grupos.values()):
            grupos[f'D-{cid[2:]}'] = {'tipo': 'dado', 'apoyos': [cid]}
    for g in grupos.values():
        if g['tipo'] == 'losa':
            g['caja'] = [round(math.floor(g['caja'][0] / 0.05 + 1e-9) * 0.05, 3), round(math.floor(g['caja'][1] / 0.05 + 1e-9) * 0.05, 3),
                         round(math.ceil(g['caja'][2] / 0.05 - 1e-9) * 0.05, 3), round(math.ceil(g['caja'][3] / 0.05 - 1e-9) * 0.05, 3)]

    def cargas_grupo(g, xc, yc, h, W_propio):
        """Cargas del grupo llevadas al centro de la rejilla de pilotes (xc, yc), con el peso propio del dado y el
        relleno, y el cortante sísmico por el espesor h (momento en la cabeza de los pilotes)."""
        gt = {cs: 0.0 for cs in ('D', 'L', 'Lr')}
        Mxg = Myg = 0.0
        E = {'N': [0.0, 0.0], 'Mx': [0.0, 0.0], 'My': [0.0, 0.0], 'Vx': [0.0, 0.0], 'Vy': [0.0, 0.0]}
        Ec = {k: [0.0, 0.0] for k in E}
        Mxg = {cs: 0.0 for cs in gt}
        Myg = {cs: 0.0 for cs in gt}
        for aid in g['apoyos']:
            a = reac[aid]
            for cs in gt:
                Mxg[cs] += a['g'][cs] * (a['y'] - yc) + a['gm']['Mx'][cs]
                Myg[cs] += a['g'][cs] * (a['x'] - xc) + a['gm']['My'][cs]
                gt[cs] += a['g'][cs]
            for dst, src in ((E, a['E']), (Ec, a['Ecap'])):
                for cmb in (0, 1):
                    dst['N'][cmb] += src['N'][cmb]
                    dst['Mx'][cmb] += src['Mx'][cmb] + src['N'][cmb] * abs(a['y'] - yc) + src['Vy'][cmb] * h
                    dst['My'][cmb] += src['My'][cmb] + src['N'][cmb] * abs(a['x'] - xc) + src['Vx'][cmb] * h
                    dst['Vx'][cmb] += src['Vx'][cmb]
                    dst['Vy'][cmb] += src['Vy'][cmb]
        gt['D'] += W_propio
        return {'g': gt, 'E': E, 'Ecap': Ec, 'Mxg': Mxg, 'Myg': Myg}

    def rejillas_losa(caja):
        Lx = caja[2] - caja[0] - 2 * BORDE_PILOTE
        Ly = caja[3] - caja[1] - 2 * BORDE_PILOTE
        nxm = int(Lx / S_PILOTES + 1e-9) + 1
        nym = int(Ly / S_PILOTES + 1e-9) + 1
        ops = []
        for nx_ in range(2, nxm + 1):
            for ny_ in range(2, nym + 1):
                sx, sy = Lx / (nx_ - 1), Ly / (ny_ - 1)
                pos = [(-Lx / 2 + i * sx, -Ly / 2 + j * sy) for j in range(ny_) for i in range(nx_)]
                ops.append((nx_ * ny_, nx_, ny_, sx, sy, pos))
        return sorted(ops, key=lambda o: (o[0], o[1]))

    def resolver_grupo(g, cap, h):
        if g['tipo'] == 'dado':
            a = reac[g['apoyos'][0]]
            for n in opciones_pilotes():
                pos, Lc, B = tamano_dado(n, a['b'])
                W = Lc * B * h * GAMMA_C + Lc * B * 0.25 * SUELO['gamma_kN_m3'] + n * cap['peso']
                cg = cargas_grupo(g, a['x'], a['y'], h, W)
                combos = combinaciones_cimentacion(cg, R, Om)
                ok, ext = verificar_grupo(combos, pos, cap)
                if ok:
                    return {'n': n, 'pos': pos, 'Lc': Lc, 'B': B, 'xc': a['x'], 'yc': a['y'], 'cargas': cg, 'combos': combos,
                            'ext': ext, 'cap_Qadm': cap['Qadm']}
            return None
        for ampl in (0.0, 0.9, 1.8, 2.7):
            # la losa crece por todos los lados (de media separación en media separación) hasta que los pilotes
            # tengan brazo suficiente para el momento de vuelco de los muros
            caja = [g['caja'][0] - ampl, g['caja'][1] - ampl, g['caja'][2] + ampl, g['caja'][3] + ampl]
            xc, yc = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
            Lc, B = caja[2] - caja[0], caja[3] - caja[1]
            for n, nx_, ny_, sx, sy, pos in rejillas_losa(caja):
                W = Lc * B * h * GAMMA_C + n * cap['peso']
                cg = cargas_grupo(g, xc, yc, h, W)
                combos = combinaciones_cimentacion(cg, R, Om)
                ok, ext = verificar_grupo(combos, pos, cap)
                if ok:
                    return {'n': n, 'nx': nx_, 'ny': ny_, 'sx': sx, 'sy': sy, 'pos': pos, 'Lc': Lc, 'B': B, 'xc': xc,
                            'yc': yc, 'caja': [round(q, 3) for q in caja], 'ampliacion_m': ampl, 'cargas': cg,
                            'combos': combos, 'ext': ext, 'cap_Qadm': cap['Qadm']}
        return None

    def huella_dado(cid, n):
        a = reac[cid]
        _, Lc, B = tamano_dado(n, a['b'])
        return [a['x'] - Lc / 2, a['y'] - B / 2, a['x'] + Lc / 2, a['y'] + B / 2]

    def se_tocan(p_, q_):
        return p_[0] < q_[2] and p_[2] > q_[0] and p_[1] < q_[3] and p_[3] > q_[1]

    # ---- largo de pilote: el de menor total de metros con todos los grupos resueltos --------------------------------
    for _vuelta in range(6):
        cambio = False
        cap12 = capacidad_pilote(15.0)
        for gid, g in list(grupos.items()):
            if g['tipo'] != 'losa':
                continue
            sl = resolver_grupo(g, cap12, 1.40)
            caja = sl['caja'] if sl else [g['caja'][0] - 2.7, g['caja'][1] - 2.7, g['caja'][2] + 2.7, g['caja'][3] + 2.7]
            for gid2, g2 in list(grupos.items()):
                if g2['tipo'] != 'dado':
                    continue
                cid = g2['apoyos'][0]
                sd = resolver_grupo(g2, cap12, 1.10)
                if se_tocan(caja, huella_dado(cid, sd['n'] if sd else 9)):
                    g['apoyos'].append(cid)
                    a = reac[cid]
                    c_ = g['caja']
                    g['caja'] = [min(c_[0], a['x'] - a['b'] / 2 - margen), min(c_[1], a['y'] - a['b'] / 2 - margen),
                                 max(c_[2], a['x'] + a['b'] / 2 + margen), max(c_[3], a['y'] + a['b'] / 2 + margen)]
                    del grupos[gid2]
                    cambio = True
        if not cambio:
            break
    def resolver_todo():
        estudio = []
        elegido = None
        for L in (12.0, 15.0, 18.0, 21.0):
            cap = capacidad_pilote(L)
            sol = {}
            for gid, g in grupos.items():
                sol[gid] = resolver_grupo(g, cap, 1.10 if g['tipo'] == 'dado' else 1.40)
            if any(v is None for v in sol.values()):
                estudio.append({'L_m': L, 'Qult_kN': r(cap['Qult'], 0), 'resuelve': False})
                continue
            n_tot = sum(v['n'] for v in sol.values())
            estudio.append({'L_m': L, 'Qult_kN': r(cap['Qult'], 0), 'Qadm_kN': r(cap['Qadm'], 0), 'resuelve': True,
                            'pilotes': n_tot, 'metros': r(n_tot * L, 1)})
            if elegido is None or n_tot * L < elegido[0] - 1e-9:
                elegido = (n_tot * L, L, cap, sol)
        return elegido, estudio

    def huella_sol(gid, sg):
        g = grupos[gid]
        if g['tipo'] == 'dado':
            return (sg['xc'] - sg['Lc'] / 2, sg['yc'] - sg['B'] / 2, sg['xc'] + sg['Lc'] / 2, sg['yc'] + sg['B'] / 2)
        return tuple(sg['caja'])

    # dados que quedan casi pegados (menos de 1,2 m libres entre caras en un eje) se funden en un dado combinado: una
    # viga de amarre tan corta no tiene sentido (el asentamiento diferencial le daría un momento sin límite)
    fusiones = []
    for _vuelta in range(8):
        (_, L_pil, cap, sol), estudio = resolver_todo()
        grupo_de = {aid: gid for gid, g in grupos.items() for aid in g['apoyos']}
        pegados = None
        for d_, lin, c, ejes in ([('x', ny, yy, [(nx, xx) for nx, xx in EJES_X]) for ny, yy in EJES_Y] +
                                 [('y', nx, xx, [(ny, yy) for ny, yy in EJES_Y]) for nx, xx in EJES_X]):
            ap = [(grupo_de[cid], e2) for e2, v in ejes
                  for cid in ([f'C-{e2}{lin}'] if d_ == 'x' else [f'C-{lin}{e2}']) if cid in grupo_de]
            for (g0, e0), (g1, e1) in zip(ap[:-1], ap[1:]):
                if g0 == g1:
                    continue
                h0, h1 = huella_sol(g0, sol[g0]), huella_sol(g1, sol[g1])
                libre = (h1[0] - h0[2]) if d_ == 'x' else (h1[1] - h0[3])
                if libre < 1.2:
                    pegados = (g0, g1, libre, f'{lin}: {e0}-{e1}')
                    break
            if pegados:
                break
        if not pegados:
            break
        g0, g1, libre, donde = pegados
        h0, h1 = huella_sol(g0, sol[g0]), huella_sol(g1, sol[g1])
        caja = [min(h0[0], h1[0]), min(h0[1], h1[1]), max(h0[2], h1[2]), max(h0[3], h1[3])]
        A0, A1 = grupos.pop(g0), grupos.pop(g1)
        nuevo_id = g0 if A0['tipo'] == 'losa' else (g1 if A1['tipo'] == 'losa' else 'DC-' + '-'.join(
            x[2:] for x in A0['apoyos'] + A1['apoyos']))
        grupos[nuevo_id] = {'tipo': 'losa', 'apoyos': A0['apoyos'] + A1['apoyos'],
                            'rects': A0.get('rects', []) + A1.get('rects', []),
                            'caja': [round(q, 3) for q in caja]}
        fusiones.append({'grupos': [g0, g1], 'resultado': nuevo_id, 'libre_m': r(libre, 3), 'eje': donde})
    # ---- diseño estructural de dados y losas de pilotes -------------------------------------------------------------
    elementos = []
    for gid, g in sorted(grupos.items()):
        sg = sol[gid]
        if g['tipo'] == 'dado':
            a = reac[g['apoyos'][0]]
            dd = disenar_dado(a, sg['combos'], sg['pos'], sg['B'], sg['Lc'], a['b'], cap, gid)
        else:
            dd = disenar_losa_pilotes(torre, g, sg, reac)
        sg['diseno'] = dd
        elementos.append((gid, g, sg))
    # ---- pilotes de cada grupo: refuerzo con su mayor compresión, su tracción y el cortante en la cabeza -------------
    for gid, g, sg in elementos:
        Vg = max(max(sg['cargas']['E']['Vx']), max(sg['cargas']['E']['Vy']))
        sg['pilote'] = disenar_pilote(L_pil, cap, sg, Vg / sg['n'])
    V_tot = max(sum(sum(a_['E']['Vx'][c_] for a_ in reac.values()) for c_ in (0, 1)),
                sum(sum(a_['E']['Vy'][c_] for a_ in reac.values()) for c_ in (0, 1)))
    vigas_am = vigas_de_amarre(torre, elementos, reac, sol)
    otros = fosos_contrapiso_cisternas(torre, elementos)
    return {'reacciones': reac, 'grupos': grupos, 'L_pilote': L_pil, 'capacidad': cap, 'estudio_largo': estudio,
            'fusiones': fusiones,
            'elementos': elementos, 'vigas_amarre': vigas_am, 'otros': otros, 'V_base_kN': V_tot}


def disenar_losa_pilotes(torre, g, sg, reac):
    """Losa de pilotes bajo un núcleo (dado combinado): espesor por punzonamiento del pilote más cargado y por
    cortante en una dirección; flexión con la franja de cada pilote en voladizo desde la cara del muro o columna más
    cercana (momento P·a por el ancho tributario), en las dos caras (la superior con los pilotes en tracción)."""
    rec = REC['dado_fondo']
    caras = list(g['rects'])
    for aid in g['apoyos']:
        a = reac[aid]
        if a['tipo'] == 'columna':
            caras.append((a['x'] - a['b'] / 2, a['y'] - a['b'] / 2, a['x'] + a['b'] / 2, a['y'] + a['b'] / 2))
    pos = [(sg['xc'] + x, sg['yc'] + y) for x, y in sg['pos']]
    may = [c for c in sg['combos'] if c[4] in ('mayorada', 'capacidad')]
    Pmax = [max(reacciones_pilotes(sg['pos'], N, Mx, My)[i] for _, N, Mx, My, t in may if t == 'mayorada')
            for i in range(len(pos))]
    Pmin = [min(reacciones_pilotes(sg['pos'], N, Mx, My)[i] for _, N, Mx, My, t in may) for i in range(len(pos))]
    brazos = []
    for px, py in pos:
        mejor = None
        for x0, y0, x1, y1 in caras:
            dx = max(x0 - px, 0.0, px - x1)
            dy = max(y0 - py, 0.0, py - y1)
            dist = math.hypot(dx, dy)
            if mejor is None or dist < mejor[0]:
                mejor = (dist, 'x' if dx >= dy else 'y')
        brazos.append(mejor)
    s_perp = {'x': sg['sy'], 'y': sg['sx']}
    Mu = {'x': 0.0, 'y': 0.0}
    Mu_sup = {'x': 0.0, 'y': 0.0}
    for P, Pm, (a, dirn) in zip(Pmax, Pmin, brazos):
        Mu[dirn] = max(Mu[dirn], P * a / s_perp[dirn])
        if Pm < 0:
            Mu_sup[dirn] = max(Mu_sup[dirn], -Pm * a / s_perp[dirn])
    As_capa = BARRAS[8][1] * 1e-6 / 0.10                       # N.º 8 c/0,10: lo más que cabe en una capa
    for h in [x / 20 for x in range(24, 61)]:                   # 1,20 a 3,00 m
        d = h - rec - 0.10 - BARRAS[7][0] / 1000
        ok = max(Pmax) <= 0.75 * punzonamiento_vc(math.pi * (D_PILOTE + d), d)
        for P, (a, dirn) in zip(Pmax, brazos):
            if a > d and P / s_perp[dirn] > 0.75 * 0.17 * math.sqrt(FC) * d * 1000:
                ok = False
        if max(as_requerida(max(Mu.values()), 1.0, d), as_requerida(max(Mu_sup.values()), 1.0, d)) > As_capa:
            ok = False
        if ok:
            break
    refuerzo = {}
    for eje in ('x', 'y'):
        As = max(as_requerida(Mu[eje], 1.0, d), 0.0018 * h / 2 * 1.0, 0.0012 * h)
        num, s_, Ar = barras_por_metro(As)
        refuerzo[f'inferior_{eje}'] = {'num': num, 's': s_, 'Mu_kNm_m': Mu[eje], 'As_req_mm2_m': As * 1e6}
        As_s = max(as_requerida(Mu_sup[eje], 1.0, d), 0.0009 * h)
        num, s_, Ar = barras_por_metro(As_s, nums=(5, 6, 7))
        refuerzo[f'superior_{eje}'] = {'num': num, 's': s_, 'Mu_kNm_m': Mu_sup[eje], 'As_req_mm2_m': As_s * 1e6}
    refuerzo['lateral'] = {'num': 4, 's': 0.30, 'nota': 'refuerzo perimetral de piel'}
    return {'h': h, 'd': d, 'Mu': Mu, 'Mu_sup': Mu_sup, 'Vu_pilote': max(Pmax), 'P_min_pilote': min(Pmin),
            'refuerzo': refuerzo, 'caras': caras, 'ok': ok}


def disenar_pilote(L, cap, sg, V_pilote):
    """Refuerzo de los pilotes de un grupo: longitudinal con ρ ≥ 0,5 % en todo el largo (criterio adoptado; NSR-10
    C.15.11 y título H, por confirmar), espiral N.º 3 confinante en la cabeza; P-M con la mayor compresión mayorada y la
    de capacidad, tracción con el sismo de capacidad (anclaje del pilote: la cimentación no debe fallar antes que la
    estructura) y el momento de la cabeza empotrada en el dado bajo el cortante sísmico de diseño repartido por igual
    entre los pilotes del grupo (sin contar el empuje pasivo sobre el dado, del lado seguro), M = V/(2·λ) con
    λ = (kh·D/(4·EI))^(1/4) (viga larga sobre fundación elástica de Winkler con la cabeza empotrada; Hetényi, 1946)."""
    Pu = sg['ext']['mayorada']['max']
    Pu_om = sg['ext']['capacidad']['max']
    Tu = max(-min(sg['ext']['capacidad']['min'], sg['ext']['mayorada']['min']), 0.0)
    arc = next(c for c in SUELO['capas'] if c['tipo'] == 'arcilla')
    kh = 67 * arc['Su_kPa'] / D_PILOTE                       # kN/m³
    Ip = math.pi * D_PILOTE ** 4 / 64
    EIp = 0.5 * EC * 1000 * Ip                               # fisurado (C.10.10.4.1: 0,35-0,70; se toma 0,5)
    lam = (kh * D_PILOTE / (4 * EIp)) ** 0.25
    Mu = V_pilote / (2 * lam)
    Ag = math.pi * D_PILOTE ** 2 / 4
    rec = REC['pilote']
    elegido = None
    for n in (6, 7, 8, 9, 10, 12, 14, 16):
        for num in (6, 7, 8):
            As = area(n, num)
            if As / Ag < 0.005:
                continue
            sec = seccion_circular(D_PILOTE, n, num, rec)
            phiPmax = 0.85 * 0.75 * (0.85 * FC * (Ag - As) + FY * As) * 1000
            ok = phiPmax >= Pu
            for P in (Pu, Pu_om, -Tu, 0.0):
                pm = sec.phiMn_rapido(P, 'sup')
                if pm is None or pm < Mu:
                    ok = False
            if 0.9 * As * FY * 1000 < Tu:
                ok = False
            if ok:
                elegido = (As, n, num, sec, phiPmax)
                break
        if elegido:
            break
    As, n, num, sec, phiPmax = elegido
    Dc = D_PILOTE - 2 * rec
    rho_s = 4 * BARRAS[3][1] / (Dc * 1000 * 75)
    zona = max(3.0, 5 * D_PILOTE)
    ld = ldh_sismico(num) + 0.10
    largo_barra = L + ld
    # canasta en dos tramos: la tracción baja a lo largo del fuste a medida que la fricción la pasa al suelo (lineal con
    # fuste uniforme: Tu/2 a la mitad del largo) y el momento de la cabeza se apaga a unos 3/λ de profundidad; la mitad
    # inferior lleva la mitad de las barras (al menos 6 y ρ ≥ 0,25 %), traslapadas con 1,3·ld
    n_inf = max(6, (n + 1) // 2, math.ceil(0.0025 * Ag / (BARRAS[num][1] * 1e-6) - 1e-9))
    largo_sup = L / 2 + ld + traslapo(num)
    largo_inf = L / 2
    n_esp_conf = zona / 0.075
    n_esp_resto = (L - zona) / 0.15
    largo_vuelta = math.pi * (Dc - BARRAS[3][0] / 1000)
    kg = (n * largo_sup + n_inf * largo_inf) * BARRAS[num][2] + (n_esp_conf + n_esp_resto) * largo_vuelta * BARRAS[3][2]
    return {'n': n, 'num': num, 'n_mitad_inferior': n_inf, 'As_mm2': As * 1e6, 'rho': As / Ag, 'Pu_kN': Pu,
            'Pu_capacidad_kN': Pu_om, 'Tu_kN': Tu,
            'V_kN': V_pilote, 'lambda_1_m': lam, 'Mu_kNm': Mu, 'phiPn_max_kN': phiPmax,
            'phiMn_kNm': sec.phiMn_rapido(Pu, 'sup'), 'espiral': {'num': 3, 's_cabeza': 0.075, 'zona_m': zona, 's_resto': 0.15,
                                                                  'rho_s': rho_s, 'rho_s_min': 0.12 * FC / FY},
            'anclaje_en_dado_m': ld, 'largo_barra_m': largo_sup, 'largo_mitad_inferior_m': largo_inf, 'kg': kg,
            'volumen_m3': Ag * L,
            'calculo': f'kh = 67·Su/D = {es(kh, 0)} kN/m³ (Davisson, 1970), EI fisurado = 0,5·Ec·Ig = {es(EIp, 0)} kN·m², '
                       f'λ = {es(lam, 3)} 1/m; V por pilote = V del grupo/n = {es(V_pilote, 1)} kN; M = V/(2λ) = {es(Mu, 1)} kN·m; '
                       f'φPn,max = 0,85·0,75·[0,85·f\'c·(Ag − As) + fy·As] (espiral, C.10.3.6.1)'}


def vigas_de_amarre(torre, elementos, reac, sol):
    """Vigas de amarre entre dados vecinos en cada eje (NSR-10 C.15.13, por confirmar): fuerza axial de tracción o
    compresión 0,25·Aa·Pu de la columna más cargada que amarra; momento por el asentamiento diferencial entre los dos
    grupos de pilotes, M = 6·EI_fis·Δ/ln² (empotrada en los dos extremos), más el peso propio y el muro de fachada del
    piso 1 en las de borde (w·ln²/10); refuerzo simétrico (el asentamiento puede ir en los dos sentidos)."""
    huella = {}
    for gid, g, sg in elementos:
        if g['tipo'] == 'dado':
            a = reac[g['apoyos'][0]]
            huella[gid] = (a['x'] - sg['Lc'] / 2, a['y'] - sg['B'] / 2, a['x'] + sg['Lc'] / 2, a['y'] + sg['B'] / 2)
        else:
            huella[gid] = tuple(g['caja'])
    grupo_de = {}
    for gid, g, sg in elementos:
        for aid in g['apoyos']:
            grupo_de[aid] = gid
    Pu_col = {}
    s_serv = {}
    for gid, g, sg in elementos:
        Pu_col[gid] = sg['ext']['mayorada']['max'] * sg['n'] / max(len(g['apoyos']), 1)
        # asentamiento de servicio de la cabeza: ≈ 1 % de D con la carga admisible y proporcional a la carga (curvas
        # normalizadas de carga y asentamiento de pilotes preexcavados, O'Neill y Reese, 1999; estimación)
        s_serv[gid] = 0.01 * D_PILOTE * sg['ext']['estatico']['max'] / sol[gid]['cap_Qadm']
    w_fach = torre['q']['fachada_m2'] * (Z[1] - 0.6)
    out = []
    lineas = [('x', ny, yy, [(nx, xx) for nx, xx in EJES_X]) for ny, yy in EJES_Y] + \
             [('y', nx, xx, [(ny, yy) for ny, yy in EJES_Y]) for nx, xx in EJES_X]
    for d_, lin, c, ejes in lineas:
        apoyos = []
        for e2, v in ejes:
            cid = f'C-{e2}{lin}' if d_ == 'x' else f'C-{lin}{e2}'
            if cid in grupo_de:
                apoyos.append((v, grupo_de[cid], e2))
        for (v0, g0, e0), (v1, g1, e1) in zip(apoyos[:-1], apoyos[1:]):
            if g0 == g1:
                continue
            h0, h1 = huella[g0], huella[g1]
            if d_ == 'x':
                a0, a1 = h0[2], h1[0]
            else:
                a0, a1 = h0[3], h1[1]
            ln = a1 - a0
            if ln <= 0.05:
                continue
            borde = lin in ('1', '7', 'A', 'D')
            T = 0.25 * AA * max(Pu_col[g0], Pu_col[g1])
            # asentamiento diferencial: el que dan las cargas más un 25 % del menor de los dos por la variabilidad del
            # suelo entre dos grupos de pilotes vecinos (estimación)
            delta = abs(s_serv[g0] - s_serv[g1]) + 0.25 * min(s_serv[g0], s_serv[g1])
            for b, h in ((0.40, 0.50), (0.40, 0.60), (0.40, 0.70), (0.50, 0.70), (0.50, 0.80)):
                d = h - REC['viga_amarre'] - 0.0095 - 0.0095
                EIf = 0.35 * EC * 1000 * b * h ** 3 / 12
                Ms = 6 * EIf * delta / ln ** 2
                w = b * h * GAMMA_C + (w_fach if borde else 0.0)
                Mg = w * ln ** 2 / 10
                Mu = 1.2 * (Mg + Ms)
                As = as_requerida(Mu, b, d) + T / (0.9 * FY * 1000) / 2
                As = max(As, as_minima_viga(b, d))
                barras = elegir_barras(b, As, REC['viga_amarre'], 3, nmin=3, nums=(5, 6, 7), max_filas=1) \
                    if As < 0.04 * b * h else None
                Vu = 1.2 * w * ln / 2 + 1.2 * 2 * Ms / ln
                s_e = min(d / 2, 0.30)
                ok = barras is not None and Vu <= 0.75 * (0.17 * math.sqrt(FC) * b * d * 1000 + 2 * BARRAS[3][1] * 1e-6 * FY * 1000 * d / s_e) \
                    and min(b, h) >= ln / 20
                if ok:
                    break
            out.append({'id': f'VC-{lin}-{e0}{e1}', 'linea': lin, 'direccion': d_, 'coordenada': c, 'desde': g0, 'hasta': g1,
                        'tramo': [a0, a1], 'ln': ln, 'b': b, 'h': h, 'T_kN': T, 'delta_m': delta, 'Ms_kNm': Ms, 'Mg_kNm': Mg,
                        'Mu_kNm': Mu,
                        'Vu_kN': Vu, 'superior': barras, 'inferior': barras, 'estribos': {'num': 3, 'ramas': 2,
                                                                                         's': math.floor(s_e / 0.025 + 1e-9) * 0.025},
                        'borde': borde})
    return out


def fosos_contrapiso_cisternas(torre, elementos):
    """Contrapiso del piso 1 (lo que no ocupan dados y losas de pilotes), foso de los ascensores y del montacargas, y
    cisternas enterradas bajo el patio de servicio (programa.json: 40 m³ de agua potable, ≈ 30 m³ contra incendio y
    ≈ 20 m³ de aguas lluvias) con empuje de tierra en reposo y agua (NSR-10 C.23, tanques y compartimientos estancos:
    esfuerzo del acero en servicio limitado para controlar la fisuración, por confirmar)."""
    # contrapiso: área de la huella de los pisos 1-3 menos la de dados y losas que caen dentro
    x0, y0, x1, y1 = -13.0, -19.6, 8.6, 22.4
    ocupado = 0.0
    for gid, g, sg in elementos:
        if g['tipo'] == 'dado':
            cx, cy = sg['xc'], sg['yc']
            q = (cx - sg['Lc'] / 2, cy - sg['B'] / 2, cx + sg['Lc'] / 2, cy + sg['B'] / 2)
        else:
            q = g['caja']
        ix = max(0.0, min(q[2], x1) - max(q[0], x0))
        iy = max(0.0, min(q[3], y1) - max(q[1], y0))
        ocupado += ix * iy
    foso_asc = {'id': 'FOSO-ASC', 'nombre': 'Foso de los ascensores camilleros (2 cabinas)', 'x': [XN, 6.1], 'y': [1.6, 7.2],
                'profundidad_m': 1.50, 'muro_e_m': 0.25, 'losa_e_m': 0.35,
                'nota': 'profundidad de 1,50 m para ascensores camilleros de 1,0 m/s sin cuarto de máquinas (estimación; la fija '
                        'el fabricante); se apoya en el suelo (carga ≈ 40 kPa) y se revisa la subpresión con el freático a 1,0 m'}
    foso_mc = {'id': 'FOSO-MC', 'nombre': 'Foso del montacargas general', 'x': [XN, 6.1], 'y': [0.8, 1.6], 'profundidad_m': 0.60,
               'muro_e_m': 0.20, 'losa_e_m': 0.25, 'nota': 'montacargas de 0,80 × 0,80 m (estimación)'}
    fosos = []
    for f in (foso_asc, foso_mc):
        Lx, Ly = f['x'][1] - f['x'][0], f['y'][1] - f['y'][0]
        prof = f['profundidad_m'] + f['losa_e_m']
        vol = Lx * Ly * f['losa_e_m'] + 2 * (Lx + Ly) * f['profundidad_m'] * f['muro_e_m']
        W = vol * GAMMA_C
        sub = 10.0 * max(prof - SUELO['nivel_freatico_m'], 0.0) * Lx * Ly
        # muro del foso: losa vertical apoyada en el contrapiso y en la losa de fondo con el empuje de tierra en reposo
        # (K0 = 0,5), el agua y 10 kPa de sobrecarga: M ≈ p_max·h²/9√3 (carga triangular) + q·h²/8, mayorado 1,6
        h_ = f['profundidad_m']
        p_max = 0.5 * sigma_v_ef(prof) + 10.0 * max(prof - SUELO['nivel_freatico_m'], 0.0)
        Mu = 1.6 * (p_max * h_ ** 2 / (9 * math.sqrt(3)) + 0.5 * 10.0 * h_ ** 2 / 8)
        dm = f['muro_e_m'] - 0.05 - 0.008
        As = max(as_requerida(Mu, 1.0, dm), 0.0030 * f['muro_e_m'])
        num, s_, _ = barras_por_metro(As / 2 if As == 0.0030 * f['muro_e_m'] else As, nums=(4, 5), s_max=0.25)
        f.update({'volumen_m3': vol, 'peso_kN': W, 'subpresion_kN': sub, 'FS_flotacion': W / sub if sub > 0 else None,
                  'Mu_muro_kNm_m': Mu, 'refuerzo': {'muros': f'N.º {num} c/{es(s_, 3)} en las dos caras y las dos direcciones',
                                                     'losa': f'N.º {num} c/{es(s_, 3)} arriba y abajo en las dos direcciones',
                                                     'num': num, 's': s_}})
        fosos.append(f)
        ocupado += Lx * Ly
    area_cp = (x1 - x0) * (y1 - y0) - ocupado
    contrapiso = {'area_m2': area_cp, 'espesor_m': 0.15, 'concreto': '21 MPa', 'volumen_m3': area_cp * 0.15,
                  'malla': 'malla electrosoldada de Ø 7 mm c/0,125 m en las dos direcciones (308 mm²/m = 0,21 % ≥ 0,18 %, C.7.12)',
                  'malla_kg_m2': 2 * 0.302 / 0.125, 'juntas': 'juntas de contracción cada 4,5 m como máximo (≈ 30 veces el '
                  'espesor; estimación con ACI 302/360) y juntas de aislamiento alrededor de columnas, dados y núcleos',
                  'base': 'sobre 0,20 m de base granular y relleno seleccionado compactado (presupuesto.json 2.10 y 2.11)'}
    # cisternas: caja enterrada con 3 compartimientos bajo el patio de servicio (x −19,5 a −10,5; y −28,0 a −24,8)
    cis = {'id': 'CIS-1', 'nombre': 'Cisternas enterradas (agua potable 40 m³, contra incendio 30 m³, lluvias 20 m³)',
           'x': [-19.5, -10.5], 'y': [-28.0, -24.8], 'muro_e_m': 0.30, 'losa_fondo_e_m': 0.35, 'losa_tapa_e_m': 0.25,
           'nota': 'estructura independiente de la torre (bajo el patio del bloque técnico); compartimientos de 40, 30 y 20 m³ útiles'}
    t_m = cis['muro_e_m']
    Lx_i = (cis['x'][1] - cis['x'][0]) - 2 * t_m - 2 * 0.25            # dos tabiques internos de 0,25 m
    Ly_i = (cis['y'][1] - cis['y'][0]) - 2 * t_m
    util = 90.0
    h_agua = util / (Lx_i * Ly_i)
    h_int = math.ceil((h_agua + 0.40) / 0.05 - 1e-9) * 0.05
    prof = h_int + cis['losa_fondo_e_m'] + cis['losa_tapa_e_m']
    Lx, Ly = cis['x'][1] - cis['x'][0], cis['y'][1] - cis['y'][0]
    vol = (Lx * Ly * (cis['losa_fondo_e_m'] + cis['losa_tapa_e_m']) + 2 * (Lx + Ly - 2 * t_m) * h_int * t_m
           + 2 * (Ly - 2 * t_m) * h_int * 0.25)
    W = vol * GAMMA_C
    sub = 10.0 * max(prof - SUELO['nivel_freatico_m'], 0.0) * Lx * Ly
    relleno_tapa = 0.0
    # muro exterior: losa vertical simplemente apoyada en la tapa y el fondo (luz h_int), con tierra en reposo (K0 = 0,5),
    # agua y 10 kPa de sobrecarga del patio (cisterna vacía); servicio con fs ≤ 140 MPa para controlar la fisuración
    p_top = 0.5 * (sigma_v_ef(cis['losa_tapa_e_m']) + 10.0)
    p_bot = 0.5 * (sigma_v_ef(prof) + 10.0) + 10.0 * max(prof - SUELO['nivel_freatico_m'], 0.0)
    Ls = h_int
    Ms = p_top * Ls ** 2 / 8 + (p_bot - p_top) * Ls ** 2 / (9 * math.sqrt(3))
    dm = t_m - 0.05 - 0.008
    As_serv = Ms / (140e3 * 0.9 * dm)                       # fs = 140 MPa (ACI 350 para exposición normal; por confirmar)
    As_res = 1.7 * Ms / (0.9 * FY * 1000 * 0.9 * dm)
    As = max(As_serv, As_res, 0.0030 * t_m)
    num, s_, _ = barras_por_metro(As, nums=(5, 6), s_max=0.20)
    cis.update({'h_agua_m': h_agua, 'h_interior_m': h_int, 'profundidad_m': prof, 'volumen_m3': vol, 'peso_kN': W,
                'subpresion_kN': sub, 'FS_flotacion': (W + relleno_tapa) / sub if sub > 0 else None,
                'Ms_muro_kNm_m': Ms, 'As_muro_mm2_m': As * 1e6,
                'refuerzo': {'muros': f'N.º {num} c/{es(s_, 3)} en las dos caras (vertical) y N.º 4 c/0,20 horizontal',
                             'losa_fondo': f'N.º {num} c/{es(s_, 3)} arriba y abajo en las dos direcciones',
                             'tapa': 'N.º 4 c/0,15 abajo y N.º 4 c/0,25 arriba (sobrecarga vehicular liviana del patio, estimación)',
                             'num': num, 's': s_},
                'impermeabilizacion': 'concreto con impermeabilizante integral y cristalizante en las caras interiores '
                                      '(presupuesto.json 2.09 y 2.14); cintas de PVC en las juntas de construcción'})
    if cis['FS_flotacion'] is not None and cis['FS_flotacion'] < 1.2:
        # se alarga la losa de fondo en un talón que carga relleno hasta tener FS ≥ 1,2 (estimación)
        falta = 1.2 * sub - W
        talon = falta / (2 * (Lx + Ly) * (prof - cis['losa_fondo_e_m']) * SUELO['gamma_sum_kN_m3'])
        cis['talon_m'] = math.ceil(talon / 0.05 - 1e-9) * 0.05
        cis['FS_flotacion'] = (W + 2 * (Lx + Ly) * cis['talon_m'] * (prof - cis['losa_fondo_e_m']) * SUELO['gamma_sum_kN_m3']
                               + 2 * (Lx + Ly) * cis['talon_m'] * cis['losa_fondo_e_m'] * GAMMA_C) / sub
        cis['volumen_m3'] += 2 * (Lx + Ly) * cis['talon_m'] * cis['losa_fondo_e_m']
    return {'contrapiso': contrapiso, 'fosos': fosos, 'cisternas': [cis]}


# ---- losa nervada y escaleras ------------------------------------------------------------------------------------
def disenar_losa(torre):
    """Losa nervada en una dirección (viguetas en x, de pórtico Y a pórtico Y; NSR-10 C.8.13): nervios de 0,12 m cada
    0,80 m, 0,45 m de altura total con loseta de 0,05 m, riostra a la mitad de cada luz (≤ 4 m entre riostras) y malla
    en la loseta. Momentos con los coeficientes de C.8.3.3 (luces y cargas parecidas, carga viva ≤ 3 veces la muerta):
    luz extrema w·ln²/14 positivo y w·ln²/24 en el apoyo exterior (viga de borde), luz interior w·ln²/16; negativo en
    el primer apoyo interior w·ln²/10 (más de dos luces) y w·ln²/11 en los demás; cortante 1,15·w·ln/2 en el primer
    apoyo interior. Los paños cortos junto a los núcleos se toman simplemente apoyados (w·ln²/8) con refuerzo superior
    mínimo. Cortante de nervaduras: φVc = 0,75·1,1·0,17·√f'c·bw·d (C.8.13.8); sin estribos mínimos (C.11.4.6.1 b)."""
    out = []
    bw, s_n, h, t_l = NERVIO_B, NERVIO_S, H_LOSA, LOSETA
    d = h - REC['vigueta'] - 0.0095 - 0.0127 / 2
    for p in torre['paneles']:
        k = p['nivel']
        x0, x1 = p['x0'], p['x1']
        luz = x1 - x0
        # apoyos: media viga Y a cada lado (o la cara del muro)
        ln = luz - 0.25 - 0.25
        ejes_x = [e for e, xx in EJES_X if abs(xx - x0) < 1e-6], [e for e, xx in EJES_X if abs(xx - x1) < 1e-6]
        par = (ejes_x[0][0] if ejes_x[0] else None, ejes_x[1][0] if ejes_x[1] else None)
        if par == ('A', 'B') or par == ('C', 'D'):
            caso = 'extrema'
        elif par == ('B', 'C'):
            caso = 'interior'
        else:
            caso = 'simple'
        wD = p['qD'] * s_n
        wL = (p['qL'] + 0.0) * s_n
        wLr = p['qLr'] * s_n
        wu = max(1.4 * wD, 1.2 * wD + 1.6 * wL + 0.5 * wLr, 1.2 * wD + 1.0 * wL + 1.6 * wLr)
        if caso == 'extrema':
            Mpos = wu * ln ** 2 / 14
            Mneg_int = wu * ln ** 2 / 10
            Mneg_ext = wu * ln ** 2 / 24
            Vu = 1.15 * wu * ln / 2
        elif caso == 'interior':
            Mpos = wu * ln ** 2 / 16
            Mneg_int = Mneg_ext = wu * ln ** 2 / 10
            Vu = 1.15 * wu * ln / 2
        else:
            Mpos = wu * ln ** 2 / 8
            Mneg_int = Mneg_ext = wu * ln ** 2 / 24
            Vu = wu * ln / 2
        # positivo: sección T con ala de 0,80 m (bloque dentro de la loseta si a ≤ 0,05 m)
        As_p = max(as_requerida(Mpos, s_n, d), as_minima_viga(bw, d))
        inf = elegir_barras(bw, As_p, REC['vigueta'], 3, nmin=1, nums=(4, 5, 6), max_filas=1) or (2, 6)
        As_n = max(as_requerida(max(Mneg_int, Mneg_ext), bw, d), as_minima_viga(bw, d))
        sup = elegir_barras(bw, As_n, REC['vigueta'], 3, nmin=1, nums=(4, 5, 6), max_filas=1) or (2, 6)
        phiVc = 0.75 * 1.1 * 0.17 * math.sqrt(FC) * bw * d * 1000
        if Vu > phiVc:
            s_e = min(d / 2, 2 * BARRAS[3][1] * 1e-6 * FY * 1000 * d / (Vu / 0.75 - phiVc / 0.75))
            estribos = {'num': 3, 's': math.floor(s_e / 0.025 + 1e-9) * 0.025, 'zona_m': ln / 4, 'nota': 'cerca de los apoyos'}
        else:
            estribos = None
        n_nerv = max(1, round((p['y1'] - p['y0']) / s_n))
        area_p = (x1 - x0) * (p['y1'] - p['y0'])
        def nombre_y(yy):
            n_ = [e for e, v in EJES_Y if abs(v - yy) < 1e-6]
            return n_[0] if n_ else f'({es(yy, 1)})'
        def nombre_x(xx):
            n_ = [e for e, v in EJES_X if abs(v - xx) < 1e-6]
            return n_[0] if n_ else ('N' if abs(xx - XN) < 1e-6 else f'({es(xx, 1)})')
        out.append({'id': f'LN{k}-{nombre_x(x0)}{nombre_x(x1)}-{nombre_y(p["y0"])}{nombre_y(p["y1"])}', 'nivel': k, 'tipo': p['tipo'],
                    'x0': x0, 'x1': x1, 'y0': p['y0'], 'y1': p['y1'], 'luz': luz, 'ln': ln, 'caso': caso, 'wu_kN_m': wu,
                    'Mpos': Mpos, 'Mneg_int': Mneg_int, 'Mneg_ext': Mneg_ext, 'Vu': Vu, 'phiVc': phiVc,
                    'inferior': inf, 'superior': sup, 'estribos': estribos, 'n_nervios': n_nerv, 'area_m2': area_p,
                    'h_ln': h / ln if ln > 0 else None})
    return out


def disenar_escaleras(torre):
    """Escaleras: losa quebrada de 0,20 m por tramo, apoyada en las vigas de los descansos (luz de cálculo = proyección
    del tramo más medio descanso a cada lado), simplemente apoyada: Mu = wu·L²/8 con wu = 1,2·D + 1,6·L (L = 5,0 kPa
    de escaleras de evacuación); refuerzo principal abajo, superior mínimo en los apoyos y repartición (C.7.12)."""
    out = []
    for e in torre['escaleras']:
        t = e['espesor_m']
        L = e['tramo_horizontal_m'] + e['descanso_m']
        cos = e['tramo_horizontal_m'] / e['tramo_inclinado_m']
        qD = t * GAMMA_C / cos + e['contrahuella_m'] / 2 * GAMMA_C + CARGAS_MUERTAS['acabado_piso_kPa'][0]
        wu = 1.2 * qD + 1.6 * VIVA_ESCALERA
        Mu = wu * L ** 2 / 8
        d = t - REC['escalera'] - 0.008
        As = max(as_requerida(Mu, 1.0, d), 0.0018 * t)
        num, s_, _ = barras_por_metro(As, nums=(4, 5, 6), s_max=0.25)
        As_t = 0.0018 * t
        num_t, s_t, _ = barras_por_metro(As_t, nums=(3, 4), s_max=0.30)
        out.append({'id': f'ESC-{"N" if e["nucleo"] == "escalera_norte" else "S"}-{e["piso"]}', **e, 'L_calculo_m': L,
                    'wu_kPa': wu, 'Mu_kNm_m': Mu, 'principal': (num, s_), 'reparticion': (num_t, s_t),
                    'superior': (num_t if num_t >= 4 else 4, 0.25), 'h_L': t / L})
    return out


# ---- despiece del refuerzo (contrato 17.3) -----------------------------------------------------------------------
def kg_barra(num, largo, n=1):
    return n * largo * BARRAS[num][2]


def gancho_sismico(num_e):
    """Extensión de un gancho sísmico de 135° de estribo: 6·db ≥ 75 mm (NSR-10 C.21.1 y C.7.1.3), más el doblez."""
    db = BARRAS[num_e][0] / 1000
    return max(6 * db, 0.075) + 3 * db


def largo_estribo(b, h, rec, num_e):
    db = BARRAS[num_e][0] / 1000
    return 2 * (b - 2 * rec - db) + 2 * (h - 2 * rec - db) + 2 * gancho_sismico(num_e)


def gancho_90(num):
    """Gancho estándar de 90°: 12·db de extensión más el doblez (C.7.1.2)."""
    db = BARRAS[num][0] / 1000
    return 12 * db + 4 * db


def n_estribos(largo, s, primero=0.05):
    return max(int(math.floor((largo - primero) / s + 1e-9)) + 1, 0) if largo > primero else 0


def despiece_columnas(torre, D):
    """Despiece de cada columna física por piso: barras por cara, traslapo en la mitad central de la altura libre
    (clase B = 1,3·ld, C.12.15; en la mitad central como pide C.21.6.3.2), estribos cerrados con ganchos de 135° y
    ganchos suplementarios en lo (zona confinada en los dos extremos) y en el nudo, separación mayor en el centro."""
    out = []
    por_fis = {}
    for P in torre['porticos']:
        for e in P['elementos']:
            if e['tipo'] == 'columna':
                por_fis.setdefault(e['fisico'], []).append((P, e))
    vigas_en = {}
    for P in torre['porticos']:
        for e in P['elementos']:
            if e['tipo'] == 'viga':
                for nid in (e['i'], e['j']):
                    vigas_en.setdefault((P['id'], nid), []).append(e)
    for f in sorted(por_fis, key=lambda q: (q.split('-')[1], int(q.split('-')[2]))):
        c = D['columnas'][f]
        P, e = por_fis[f][0]
        nx, ny = e['eje'].split('-')
        k = e['nivel']
        x, y = EJX[nx], EJY[ny]
        b = c['b']
        tr = c['transversal']
        h_ent = Z[k] - Z[k - 1]
        h_viga = max(ee['arms'][1] for _, ee in por_fis[f])
        ln = h_ent - h_viga
        num, n = c['num'], c['n']
        db = BARRAS[num][0] / 1000
        lap = traslapo(num)
        arriba = f'{f.rsplit("-", 1)[0]}-{k + 1}' in D['columnas']
        largo_long = h_ent + (lap if arriba else (h_viga - REC['columna'] + gancho_90(num) - h_viga))
        if k == 1:
            largo_long += ldh_sismico(num) + gancho_90(num)       # anclaje en el dado con gancho
        kg_long = kg_barra(num, largo_long, n)
        rec = REC['columna']
        ne_lo = 2 * n_estribos(tr['lo'], tr['s_lo'])
        ne_c = max(int(math.ceil((ln - 2 * tr['lo']) / tr['s_centro'] - 1e-9)) - 1, 0)
        ne_nudo = max(int(math.ceil(h_viga / tr['s_lo'] - 1e-9)), 1)
        n_sets = ne_lo + ne_c + ne_nudo
        l_est = largo_estribo(b, b, rec, tr['num'])
        l_gs = (b - 2 * rec) + 2 * gancho_sismico(tr['num'])
        kg_tr = kg_barra(tr['num'], l_est, n_sets) + kg_barra(tr['num'], l_gs, n_sets * 2 * tr['ganchos_suplementarios'])
        vol = b * b * h_ent
        out.append({'id': f, 'eje': e['eje'], 'nivel': k, 'x': x, 'y': y, 'z0': Z[k - 1], 'z1': Z[k], 'b': b, 'h': b,
                    'longitudinal': {'n': n, 'num': num, 'por_cara': n // 4 + 1, 'recubrimiento_m': rec,
                                     'traslapo': {'z_centro': r(Z[k - 1] + ln / 2, 3), 'largo_m': r(lap, 3)} if arriba else None,
                                     'anclaje': ('en el dado: ldh + gancho de 90°' if k == 1 else
                                                 ('gancho de 90° en el nudo de cubierta' if not arriba else 'continúa al piso de arriba'))},
                    'estribos': {'num': tr['num'], 'ramas_por_direccion': tr['ramas'],
                                 'ganchos_suplementarios_por_direccion': tr['ganchos_suplementarios'], 'gancho': '135°',
                                 'lo_m': tr['lo'], 's_lo_m': tr['s_lo'], 's_centro_m': tr['s_centro'],
                                 'nudo': {'alto_m': h_viga, 's_m': tr['s_lo']}, 'primer_estribo_m': 0.05,
                                 'juegos': n_sets},
                    'texto': f'{n} N.º {num} ({n // 4 + 1} por cara); E N.º {tr["num"]} de {tr["ramas"]} ramas c/{es(tr["s_lo"], 3)} '
                             f'en lo = {es(tr["lo"])} m y c/{es(tr["s_centro"], 3)} en el centro',
                    'kg': kg_long + kg_tr, 'kg_longitudinal': kg_long, 'kg_transversal': kg_tr, 'm3': vol})
    return out


def despiece_vigas(torre, D):
    """Despiece de cada viga: corridas superiores e inferiores (ancladas con gancho en los nudos exteriores, C.21.7.5 /
    C.12.5, y traslapadas fuera de las zonas 2h), bastones superiores en los apoyos con su largo desde la cara,
    bastones inferiores en el vano si hacen falta, estribos cerrados con ganchos de 135° en 2h desde cada cara (primer
    estribo a 0,05 m) y en el centro."""
    out = []
    for P in torre['porticos']:
        if P['id'].startswith('M'):
            continue
        idx = P['idx']
        vigas_linea = [e for e in P['elementos'] if e['tipo'] == 'viga']
        for e in vigas_linea:
            dv = D['vigas'][e['id']]
            ni, nj = idx[e['i']], idx[e['j']]
            k = e['nivel']
            si, sj = ni['s'], nj['s']
            z = Z[k]
            xyz_i = [si, P['c'], z] if P['dir'] == 'x' else [P['c'], si, z]
            xyz_j = [sj, P['c'], z] if P['dir'] == 'x' else [P['c'], sj, z]
            ext_i = not any(o['j'] == e['i'] for o in vigas_linea)
            ext_j = not any(o['i'] == e['j'] for o in vigas_linea)
            b, h, L, Lf = e['b'], e['h'], e['L'], e['Lf']
            di, dj = e['arms']
            ns, nums = dv['corr_sup']
            ni_, numi = dv['inf']
            ad_i = (di * 2 - REC['columna'] + gancho_90(nums)) if ext_i else di
            ad_j = (dj * 2 - REC['columna'] + gancho_90(nums)) if ext_j else dj
            # corridas: largo de centro a centro de los nudos (más el anclaje en los extremos) y un traslapo cada 12 m
            lap_s, lap_i = traslapo(nums, True), traslapo(numi)
            l_sup = Lf + ad_i + ad_j + lap_s * Lf / 12
            l_inf = Lf + ad_i + ad_j + lap_i * Lf / 12
            kg = kg_barra(nums, l_sup, ns) + kg_barra(numi, l_inf, ni_)
            n_bast = dv['sup'][0] - ns
            bast = None
            if n_bast > 0 and (dv['L_baston_i'] > 0 or dv['L_baston_j'] > 0):
                bast = {'n': n_bast, 'num': dv['sup'][1], 'largo_desde_cara_i_m': r(dv['L_baston_i'], 3),
                        'largo_desde_cara_j_m': r(dv['L_baston_j'], 3)}
                kg += kg_barra(dv['sup'][1], dv['L_baston_i'] + (2 * di - REC['columna'] + gancho_90(dv['sup'][1]) if ext_i else di), n_bast)
                kg += kg_barra(dv['sup'][1], dv['L_baston_j'] + (2 * dj - REC['columna'] + gancho_90(dv['sup'][1]) if ext_j else dj), n_bast)
            elif n_bast > 0:
                # sin corte: todas las superiores corridas
                kg += kg_barra(dv['sup'][1], l_sup, n_bast)
            vano = None
            if dv['extra_inf'] and dv['vano_inf']:
                vano = {'n': dv['extra_inf'][0], 'num': dv['extra_inf'][1], 'desde_cara_i_m': r(dv['vano_inf'][0], 3),
                        'hasta_m': r(dv['vano_inf'][1], 3)}
                kg += kg_barra(dv['extra_inf'][1], dv['vano_inf'][1] - dv['vano_inf'][0], dv['extra_inf'][0])
            eh, ec = dv['est_hz'], dv['est_c']
            zona = 2 * h
            n_hz = 2 * n_estribos(zona, eh['s'])
            n_c = max(int(math.ceil((Lf - 2 * zona) / ec['s'] - 1e-9)) - 1, 0)
            l_e = largo_estribo(b, h, REC['viga'], eh['num'])
            kg_e = kg_barra(eh['num'], l_e, n_hz * eh['ramas'] / 2) + kg_barra(ec['num'], l_e, n_c * ec['ramas'] / 2)
            kg += kg_e
            vol = b * (h - torre['q']['t_eq']) * Lf
            out.append({'id': e['id'], 'portico': P['id'], 'eje': e['eje'], 'nivel': k, 'xyz_i': xyz_i, 'xyz_j': xyz_j,
                        'b': b, 'h': h, 'L': r(L, 3), 'ln': r(Lf, 3), 'b_ala': r(dv['b_ala'], 3),
                        'superior': {'corridas': {'n': ns, 'num': nums}, 'bastones': bast,
                                     'anclaje': {'i': 'gancho de 90° en el nudo exterior' if ext_i else 'continúa',
                                                 'j': 'gancho de 90° en el nudo exterior' if ext_j else 'continúa'}},
                        'inferior': {'corridas': {'n': ni_, 'num': numi}, 'vano': vano},
                        'estribos': {'num': eh['num'], 'ramas': eh['ramas'], 's_2h_m': eh['s'], 'zona_m': r(zona, 3),
                                     's_centro_m': ec['s'], 'num_centro': ec['num'], 'primer_estribo_m': 0.05,
                                     'gancho': '135°', 'juegos': n_hz + n_c},
                        'traslapos': 'superiores en el tercio central de la luz e inferiores fuera de las zonas 2h y de '
                                     'los nudos (C.21.5.2.3, criterio adoptado en DMO)',
                        'texto': f'sup. {dv["sup"][0]} N.º {dv["sup"][1]} ({ns} corridas); inf. {ni_} N.º {numi}'
                                 + (f' + {vano["n"]} N.º {vano["num"]} en el vano' if vano else '')
                                 + f'; E N.º {eh["num"]} c/{es(eh["s"], 3)} en 2h = {es(zona)} m y c/{es(ec["s"], 3)} en el centro',
                        'kg': kg, 'kg_estribos': kg_e, 'm3': vol})
    for aid, ac in D['acoples'].items():
        b, h, ln = ac['b'], ac['h'], ac['ln']
        n, num = ac['sup']
        l_b = ln + 2 * (ldh_sismico(num) + gancho_90(num))
        est = ac['est']
        n_e = n_estribos(ln, est['s'])
        kg = kg_barra(num, l_b, 2 * n) + kg_barra(est['num'], largo_estribo(b, h, REC['viga'], est['num']), n_e * est['ramas'] / 2)
        out.append({'id': aid, 'portico': f'X-{ac["linea"]}', 'eje': f'{ac["linea"]} entre C y el muro', 'nivel': ac['nivel'],
                    'xyz_i': [ac['desde'][1], ac['y'], Z[ac['nivel']]], 'xyz_j': [ac['hasta'][1], ac['y'], Z[ac['nivel']]],
                    'b': b, 'h': h, 'L': r(ln, 3), 'ln': r(ln, 3), 'tipo': 'viga banda de enlace columna-muro (fuera del modelo)',
                    'superior': {'corridas': {'n': n, 'num': num}, 'bastones': None, 'anclaje': {'i': 'gancho en el nudo', 'j': 'gancho en el muro'}},
                    'inferior': {'corridas': {'n': n, 'num': num}, 'vano': None},
                    'estribos': {'num': est['num'], 'ramas': est['ramas'], 's_2h_m': est['s'], 'zona_m': r(ln, 3),
                                 's_centro_m': est['s'], 'num_centro': est['num'], 'primer_estribo_m': 0.05, 'gancho': '135°',
                                 'juegos': n_e},
                    'texto': f'{n} N.º {num} arriba y abajo; E N.º {est["num"]} de {est["ramas"]} ramas c/{es(est["s"], 3)} en toda la luz',
                    'kg': kg, 'kg_estribos': 0.0, 'm3': b * max(h - torre['q']['t_eq'], 0.0) * ln})
    return out


def despiece_muros(torre, D):
    """Despiece de cada muro por piso: dos cortinas verticales y horizontales (C.21.9.2 y C.14.3), barras de borde en
    los extremos del alma y elemento de borde confinado donde lo pide C.21.9.6.2; traslapo de las verticales en la base
    de cada piso (clase B; las de borde, 1,3·ld) y horizontales con gancho alrededor de las barras de borde."""
    out = []
    for pid, dm in D['muros'].items():
        mu = torre['muros'][pid]
        m = mu['def']
        for nv in dm['niveles']:
            k = nv['nivel']
            h_ent = Z[k] - Z[k - 1]
            t = mu['t']
            numv, sv = nv['cortina_v']
            numh, sh = nv['cortina_h']
            largo = sum(math.hypot(q[1][2] - q[1][0], q[1][3] - q[1][1]) for q in mu['concreto'])
            n_v = 2 * (int(largo / sv) + 1)
            l_v = h_ent + traslapo(numv)
            n_h = 2 * (int(h_ent / sh) + 1)
            l_h = largo + 2 * gancho_90(numh)
            kg = kg_barra(numv, l_v, n_v) + kg_barra(numh, l_h, n_h)
            bordes = []
            for lado in ('i', 'j'):
                n, num = nv[f'borde_{lado}']
                if n:
                    kg += kg_barra(num, h_ent + traslapo(num) + (ldh_sismico(num) + gancho_90(num) if k == 1 else 0.0), n)
                    bordes.append({'lado': lado, 'n': n, 'num': num})
            vol = t * largo * h_ent
            planta = [[r(q, 3) for q in rr] for rr in rect_planta_muro(mu)]
            out.append({'id': next(e['id'] for e in torre['por_id'][pid]['elementos'] if e['nivel'] == k), 'muro': pid,
                        'nivel': k, 'z0': Z[k - 1], 'z1': Z[k], 't': t, 'planta': planta, 'direccion': m['dir'],
                        'cortina_vertical': {'capas': 2, 'num': numv, 's_m': sv},
                        'cortina_horizontal': {'capas': 2, 'num': numh, 's_m': sh},
                        'bordes': bordes, 'elemento_de_borde_confinado': bool(nv['requiere_borde']),
                        'traslapo_vertical_m': r(traslapo(numv), 3),
                        'texto': f'2 cortinas N.º {numv} c/{es(sv)} (vertical) y N.º {numh} c/{es(sh)} (horizontal); bordes: '
                                 + ', '.join(f'{b_["n"]} N.º {b_["num"]} en {b_["lado"]}' for b_ in bordes),
                        'kg': kg, 'm3': vol})
    return out


def despiece_losas(losas):
    out = []
    for p in losas:
        n_n = p['n_nervios']
        ni, numi = p['inferior']
        ns, nums = p['superior']
        l_inf = p['luz'] + 0.30
        l_sup = 2 * (p['ln'] / 3 + 0.25)
        kg = kg_barra(numi, l_inf, ni * n_n) + kg_barra(nums, l_sup, ns * n_n)
        # riostra a la mitad de la luz: 1 N.º 4 arriba y abajo a todo lo largo del paño
        largo_r = p['y1'] - p['y0']
        kg += kg_barra(4, largo_r + 0.3, 2)
        kg += p['area_m2'] * 2 * MALLA[5.0][1] / 0.20
        if p['estribos']:
            n_e = 2 * n_estribos(p['estribos']['zona_m'], p['estribos']['s'])
            kg += kg_barra(3, largo_estribo(NERVIO_B, H_LOSA, REC['vigueta'], 3), n_e * n_n)
        vol = p['area_m2'] * t_equivalente_losa()
        out.append({'id': p['id'], 'nivel': p['nivel'], 'tipo': p['tipo'], 'x0': p['x0'], 'x1': p['x1'], 'y0': p['y0'],
                    'y1': p['y1'], 'z': Z[p['nivel']], 'direccion_nervios': 'x',
                    'nervios': {'n': n_n, 'separacion_m': NERVIO_S, 'b_m': NERVIO_B, 'h_m': H_LOSA, 'loseta_m': LOSETA},
                    'inferior_por_nervio': {'n': ni, 'num': numi, 'largo_m': r(l_inf, 3)},
                    'superior_por_nervio': {'n': ns, 'num': nums, 'largo_desde_cara_m': r(p['ln'] / 3, 3)},
                    'estribos': p['estribos'], 'riostras': {'n': 1, 'b_m': NERVIO_B, 'refuerzo': '1 N.º 4 arriba y 1 abajo'},
                    'malla_loseta': 'Ø 5 mm c/0,20 m en las dos direcciones (0,20 % de la loseta, C.7.12)',
                    'texto': f'nervios de 0,12 × 0,45 c/0,80: inf. {ni} N.º {numi}, sup. {ns} N.º {nums} en los apoyos (ln/3)',
                    'kg': kg, 'm3': vol})
    return out


def despiece_escaleras(esc):
    out = []
    for e in esc:
        num, s_ = e['principal']
        numt, st = e['reparticion']
        ancho = 2 * e['ancho_tramo_m']
        largo = 2 * e['tramo_inclinado_m'] + 2 * e['descanso_m']
        n_p = int(ancho / s_) + 1
        n_t = int(largo / st) + 1
        kg = kg_barra(num, largo + 0.6, n_p) + kg_barra(numt, ancho, n_t) + kg_barra(4, 2 * 1.2, int(ancho / 0.25) + 1) * 2
        out.append({'id': e['id'], 'nucleo': e['nucleo'], 'piso': e['piso'], 'espesor_m': e['espesor_m'],
                    'principal': {'num': num, 's_m': s_}, 'reparticion': {'num': numt, 's_m': st},
                    'superior_apoyos': {'num': 4, 's_m': 0.25, 'largo_m': 1.2},
                    'texto': f'losa de {es(e["espesor_m"])} m: N.º {num} c/{es(s_, 3)} abajo (principal) y N.º {numt} c/{es(st, 3)} de repartición',
                    'kg': kg, 'm3': e['volumen_m3']})
    return out


def despiece_cimentacion(C):
    """Despiece de pilotes (canasta), dados y losas de pilotes (parrillas), vigas de amarre, contrapiso, fosos y
    cisternas, con su geometría para el modelo BIM (cotas desde el piso terminado del piso 1, z = 0)."""
    L = C['L_pilote']
    pilotes, dados, vigas, = [], [], []
    for gid, g, sg in C['elementos']:
        dd = sg['diseno']
        h = dd['h']
        z_fondo = -(COTA_FONDO_DADO + max(h - 1.10, 0.0)) if g['tipo'] == 'dado' else -(COTA_FONDO_DADO + max(h - 1.10, 0.0))
        z_tope = z_fondo + h
        pil = sg['pilote']
        pos_abs = [[r(sg['xc'] + x, 3), r(sg['yc'] + y, 3)] for x, y in sg['pos']]
        pilotes.append({'grupo': gid, 'n': sg['n'], 'D_m': D_PILOTE, 'L_m': L, 'z_cabeza': r(z_fondo + 0.10, 3),
                        'z_punta': r(z_fondo + 0.10 - L, 3), 'posiciones': pos_abs,
                        'longitudinal': {'n': pil['n'], 'num': pil['num'], 'largo_m': r(pil['largo_barra_m'], 3),
                                         'anclaje_en_dado_m': r(pil['anclaje_en_dado_m'], 3),
                                         'mitad_inferior': {'n': pil['n_mitad_inferior'], 'num': pil['num'],
                                                            'largo_m': r(pil['largo_mitad_inferior_m'], 3)}},
                        'espiral': {'num': 3, 's_cabeza_m': 0.075, 'zona_cabeza_m': pil['espiral']['zona_m'], 's_resto_m': 0.15},
                        'recubrimiento_m': REC['pilote'],
                        'texto': f'{pil["n"]} N.º {pil["num"]} en la mitad superior y {pil["n_mitad_inferior"]} N.º {pil["num"]} en la '
                                 f'inferior; espiral N.º 3 c/0,075 en los {es(pil["espiral"]["zona_m"])} m de la cabeza y c/0,15 abajo',
                        'kg': pil['kg'] * sg['n'], 'kg_por_pilote': pil['kg'], 'm3': pil['volumen_m3'] * sg['n'],
                        'ml': L * sg['n']})
        Lx, Ly = sg['Lc'], sg['B']
        kg = 0.0
        ref = dd['refuerzo']
        rec = REC['dado_fondo']
        for eje, largo_b, ancho_b in (('x', Lx, Ly), ('y', Ly, Lx)):
            clave = f'inferior_{eje}'
            num, s_ = ref[clave]['num'], ref[clave]['s']
            n = int((ancho_b - 2 * rec) / s_) + 1
            kg += kg_barra(num, largo_b - 2 * rec + 2 * (h - 2 * rec), n)          # con las patas dobladas hacia arriba
            clave_s = f'superior_{eje}' if f'superior_{eje}' in ref else 'superior'
            num_s, s_s = ref[clave_s]['num'], ref[clave_s]['s']
            n_s = int((ancho_b - 2 * rec) / s_s) + 1
            kg += kg_barra(num_s, largo_b - 2 * rec + 2 * 0.30, n_s)
        per = 2 * (Lx + Ly)
        kg += kg_barra(4, per + 0.6, int((h - 2 * rec) / 0.30) + 1)
        vol = Lx * Ly * h
        dados.append({'id': gid, 'tipo': 'dado' if g['tipo'] == 'dado' else 'losa_de_pilotes', 'apoyos': g['apoyos'],
                      'x0': r(sg['xc'] - Lx / 2, 3), 'y0': r(sg['yc'] - Ly / 2, 3), 'x1': r(sg['xc'] + Lx / 2, 3),
                      'y1': r(sg['yc'] + Ly / 2, 3), 'z_fondo': r(z_fondo, 3), 'z_tope': r(z_tope, 3), 'h': h,
                      'pilotes': sg['n'], 'refuerzo': {k_: {kk: (r(v, 3) if isinstance(v, float) else v) for kk, v in d_.items()}
                                                         for k_, d_ in ref.items()},
                      'texto': (f'{"dado" if g["tipo"] == "dado" else "losa de pilotes"} de {es(Lx)} × {es(Ly)} × {es(h)} m con '
                                f'{sg["n"]} pilotes; parrilla inferior N.º {ref["inferior_x"]["num"]} c/{es(ref["inferior_x"]["s"], 3)} '
                                f'(x) y N.º {ref["inferior_y"]["num"]} c/{es(ref["inferior_y"]["s"], 3)} (y)'),
                      'kg': kg, 'm3': vol})
    for v in C['vigas_amarre']:
        n, num = v['superior']
        e = v['estribos']
        largo = v['ln'] + 2 * (ldh_sismico(num) + gancho_90(num))
        kg = kg_barra(num, largo, 2 * n) + kg_barra(3, largo_estribo(v['b'], v['h'], REC['viga_amarre'], 3), n_estribos(v['ln'], e['s']))
        kg += kg_barra(4, v['ln'] + 0.6, 2) if v['h'] >= 0.6 else 0.0           # piel en las de 0,60 m o más (C.10.6.7)
        vigas.append({'id': v['id'], 'linea': v['linea'], 'direccion': v['direccion'], 'coordenada': v['coordenada'],
                      'desde': v['desde'], 'hasta': v['hasta'], 'tramo': [r(q, 3) for q in v['tramo']], 'b': v['b'], 'h': v['h'],
                      'z_tope': -0.15, 'superior': {'n': n, 'num': num}, 'inferior': {'n': n, 'num': num},
                      'estribos': {'num': 3, 'ramas': 2, 's_m': e['s']},
                      'texto': f'{n} N.º {num} arriba y abajo; E N.º 3 c/{es(e["s"], 3)}', 'kg': kg,
                      'm3': v['b'] * v['h'] * v['ln']})
    o = C['otros']
    cp = o['contrapiso']
    fosos = []
    for f in o['fosos']:
        Lx, Ly = f['x'][1] - f['x'][0], f['y'][1] - f['y'][0]
        num, s_ = f['refuerzo']['num'], f['refuerzo']['s']
        area_caras = 2 * (Lx + Ly) * f['profundidad_m'] * 2 + Lx * Ly * 2
        kg = area_caras * 2 / s_ * BARRAS[num][2]
        fosos.append({**{k_: f[k_] for k_ in ('id', 'nombre', 'x', 'y', 'profundidad_m', 'muro_e_m', 'losa_e_m', 'nota')},
                      'z_fondo': r(-(f['profundidad_m'] + f['losa_e_m']), 3), 'refuerzo': f['refuerzo'],
                      'kg': kg, 'm3': f['volumen_m3']})
    cisternas = []
    for c_ in o['cisternas']:
        Lx, Ly = c_['x'][1] - c_['x'][0], c_['y'][1] - c_['y'][0]
        num, s_ = c_['refuerzo']['num'], c_['refuerzo']['s']
        area_muros = (2 * (Lx + Ly) + 2 * Ly) * c_['h_interior_m']
        kg = area_muros * 2 / s_ * BARRAS[num][2] + area_muros * 2 / 0.20 * BARRAS[4][2]
        kg += Lx * Ly * 2 * 2 / s_ * BARRAS[num][2] + Lx * Ly * (1 / 0.15 + 1 / 0.25) * 2 * BARRAS[4][2] / 2
        cisternas.append({**{k_: c_[k_] for k_ in ('id', 'nombre', 'x', 'y', 'muro_e_m', 'losa_fondo_e_m', 'losa_tapa_e_m', 'nota',
                                                    'impermeabilizacion')},
                          'h_interior_m': r(c_['h_interior_m'], 3), 'h_agua_m': r(c_['h_agua_m'], 3),
                          'z_fondo': r(-c_['profundidad_m'], 3), 'talon_m': c_.get('talon_m', 0.0),
                          'refuerzo': c_['refuerzo'], 'kg': kg, 'm3': c_['volumen_m3']})
    contrapiso = {**cp, 'kg': cp['area_m2'] * cp['malla_kg_m2'], 'm3': cp['volumen_m3']}
    return {'pilotes': pilotes, 'dados': dados, 'vigas_amarre': vigas, 'contrapiso': contrapiso, 'fosos': fosos,
            'cisternas': cisternas}


def cantidades(ref, cim, presupuesto):
    """Cantidades de concreto y acero por tipo, cuantías (kg/m³) y comparación con presupuesto.json (capítulos 2 y 3):
    diferencia de cantidad por ítem y su efecto en el costo directo con el valor unitario del ítem (sin AIU). El
    presupuesto no se edita: la diferencia queda como pendiente con su cifra (contrato 17.3)."""
    def suma(lista, campo):
        return sum(x[campo] for x in lista)
    tipos = {
        'columnas': (suma(ref['columnas'], 'm3'), suma(ref['columnas'], 'kg')),
        'muros': (suma(ref['muros'], 'm3'), suma(ref['muros'], 'kg')),
        'vigas': (suma(ref['vigas'], 'm3'), suma(ref['vigas'], 'kg')),
        'losas': (suma(ref['losas'], 'm3'), suma(ref['losas'], 'kg')),
        'escaleras': (suma(ref['escaleras'], 'm3'), suma(ref['escaleras'], 'kg')),
        'pilotes': (suma(cim['pilotes'], 'm3'), suma(cim['pilotes'], 'kg')),
        'dados_y_losas_de_pilotes': (suma(cim['dados'], 'm3'), suma(cim['dados'], 'kg')),
        'vigas_de_amarre': (suma(cim['vigas_amarre'], 'm3'), suma(cim['vigas_amarre'], 'kg')),
        'fosos_y_cisternas': (suma(cim['fosos'], 'm3') + suma(cim['cisternas'], 'm3'),
                              suma(cim['fosos'], 'kg') + suma(cim['cisternas'], 'kg')),
        'contrapiso': (cim['contrapiso']['m3'], cim['contrapiso']['kg']),
    }
    por_tipo = {k: {'m3': r(v[0], 1), 'kg': r(v[1], 0), 'kg_m3': r(v[1] / v[0], 1) if v[0] else None} for k, v in tipos.items()}
    ml_pilotes = suma(cim['pilotes'], 'ml')
    n_pilotes = sum(p['n'] for p in cim['pilotes'])
    acero_sup = sum(tipos[k][1] for k in ('columnas', 'muros', 'vigas', 'losas', 'escaleras'))
    acero_cim = sum(tipos[k][1] for k in ('pilotes', 'dados_y_losas_de_pilotes', 'vigas_de_amarre', 'fosos_y_cisternas'))
    filas = [
        ('3.01', 'Concreto en columnas', 'm3', tipos['columnas'][0]),
        ('3.02', 'Concreto en muros estructurales', 'm3', tipos['muros'][0]),
        ('3.03', 'Concreto en vigas y losa nervada', 'm3', tipos['vigas'][0] + tipos['losas'][0]),
        ('3.04', 'Concreto en escaleras', 'm3', tipos['escaleras'][0]),
        ('3.05', 'Acero de refuerzo de la superestructura', 'kg', acero_sup),
        ('2.04', 'Pilote preexcavado de 0,60 m', 'ml', ml_pilotes),
        ('2.05', 'Descabezado de pilotes', 'un', n_pilotes),
        ('2.07', 'Concreto en dados (y losas de pilotes de los núcleos)', 'm3', tipos['dados_y_losas_de_pilotes'][0]),
        ('2.08', 'Concreto en vigas de cimentación', 'm3', tipos['vigas_de_amarre'][0]),
        ('2.09', 'Concreto en cisternas y fosos', 'm3', tipos['fosos_y_cisternas'][0]),
        ('2.12', 'Losa de contrapiso de la torre (el ítem incluye además 143,6 m² del bloque técnico y residuos)', 'm2',
         cim['contrapiso']['area_m2'] + 125.6 + 18.0),
        ('2.13', 'Acero de refuerzo de cimentación', 'kg', acero_cim),
    ]
    comparacion = []
    total = 0.0
    for cod, nombre, und, cant in filas:
        it = item(presupuesto, cod)
        delta = cant - it['cantidad']
        pesos = delta * it['valor_unitario_costo_directo']
        total += pesos
        comparacion.append({'item': cod, 'descripcion': nombre, 'unidad': und, 'presupuesto': it['cantidad'],
                            'prediseno': r(cant, 1), 'diferencia': r(delta, 1),
                            'diferencia_pct': r(100 * delta / it['cantidad'], 1) if it['cantidad'] else None,
                            'valor_unitario_cop': it['valor_unitario_costo_directo'], 'efecto_cop': r(pesos, 0)})
    cuantias_pres = {'columnas': 220, 'muros': 130, 'vigas': 170, 'losas': 90, 'escaleras': 100, 'dados_y_losas_de_pilotes': 90,
                     'vigas_de_amarre': 130, 'fosos_y_cisternas': 110}
    return {'por_tipo': por_tipo, 'pilotes': {'n': n_pilotes, 'ml': ml_pilotes, 'kg_ml': r(tipos['pilotes'][1] / ml_pilotes, 2)},
            'acero_superestructura_kg': r(acero_sup, 0), 'acero_cimentacion_kg': r(acero_cim, 0),
            'cuantias_presupuesto_kg_m3': cuantias_pres, 'comparacion_presupuesto': comparacion,
            'efecto_total_costo_directo_cop': r(total, 0),
            'nota': 'Diferencia sobre el costo directo con los valores unitarios del presupuesto (sin AIU ni imprevistos); el '
                    'presupuesto no se edita: queda como pendiente del equipo B con estas cifras.'}


# =================================================================================================================
# 10. Dimensiones adoptadas, historial de ajustes, armado del JSON y verificación
# =================================================================================================================
MUROS_TODOS = [m['portico'] for m in MUROS]
MUROS_ADOPTADOS = ['MY-N6', 'MY-N3', 'MX-3', 'MX-4', 'MX-7']
# Historial del prediseño (se recalcula en cada corrida; ver «prediseno.historial_de_ajustes»): el punto de partida del
# presupuesto no cumple y cada ajuste dice por qué se hizo.
AJUSTES = [
    ('0', 'Punto de partida del presupuesto: columnas de 0,60 m, vigas de 0,40 × 0,60 m y los 7 paños de núcleo posibles',
     {'col': 0.60, 'muro_t': 0.30, 'vx': (0.40, 0.60), 'vy_borde': (0.40, 0.60), 'vy_int': (0.40, 0.60), 'muros': MUROS_TODOS}),
    ('1', 'Paños de muro que equilibran la torsión: sin la cara sur de la escalera norte (MX-6) ni el foso (MY-N4)',
     {'col': 0.60, 'muro_t': 0.30, 'vx': (0.40, 0.60), 'vy_borde': (0.40, 0.60), 'vy_int': (0.40, 0.60), 'muros': MUROS_ADOPTADOS}),
    ('2', 'Pórticos más rígidos: columnas de 0,80 m y vigas de 0,40 × 0,80 m',
     {'col': 0.80, 'muro_t': 0.30, 'vx': (0.40, 0.80), 'vy_borde': (0.40, 0.80), 'vy_int': (0.40, 0.80), 'muros': MUROS_ADOPTADOS}),
    ('3', 'El pórtico de la fachada occidental (eje A, el más lejano de los núcleos) con columnas de 0,90 m y vigas de '
          '0,50 × 0,90 m para bajar el giro de la planta (con muros de 0,30 m el cortante por capacidad de la base de los '
          'muros en x pasa el tope 0,83·√f\'c·Acv)',
     {'col': 0.80, 'col_eje': {'A': 0.90}, 'muro_t': 0.30, 'vx': (0.40, 0.80), 'vy_borde': (0.40, 0.80), 'vy_int': (0.40, 0.80),
      'vy_eje': {'A': (0.50, 0.90)}, 'muros': MUROS_ADOPTADOS}),
    ('4', 'Adoptado: muros de 0,35 m (más área de alma para el cortante por capacidad)',
     {'col': 0.80, 'col_eje': {'A': 0.90}, 'muro_t': 0.35, 'vx': (0.40, 0.80), 'vy_borde': (0.40, 0.80), 'vy_int': (0.40, 0.80),
      'vy_eje': {'A': (0.50, 0.90)}, 'muros': MUROS_ADOPTADOS}),
]
DIMENSIONES = AJUSTES[-1][2]
LIMITE_TORSION = 1.4          # criterio del prediseño: sin irregularidad torsional extrema (1bP) en un edificio indispensable


def resumen_rapido(torre, A, S):
    return {'T1_s': r(A['modos'][0]['T'], 4), 'T1x_s': r(A['T1x'], 4), 'T1y_s': r(A['T1y'], 4),
            'cociente_torsional': {s_: r(S['cociente_torsional'][s_], 3) for s_ in ('x', 'y')},
            'deriva_max_pct': r(100 * max(d['deriva'] for d in A['derivas']), 3),
            'deriva_umbral_max_pct': r(100 * max(d['deriva'] for d in A['umbral']['derivas']), 3),
            'R': r(S['R'], 3), 'masa_total_t': r(sum(n['masa_t'] for n in torre['niveles']), 1)}


def centro_de_rigidez(mod, niveles):
    """Centro de rigidez de cada nivel (ESQUEMA.md): el punto donde una fuerza aplicada solo en ese nivel no lo hace
    girar, con la flexibilidad elástica condensada F: e_y = F[rz,ux]/F[rz,rz] y e_x = −F[rz,uy]/F[rz,rz]."""
    F = mod.flexibilidad()
    out = []
    for k, nv in enumerate(niveles):
        a = 3 * k
        frr = F[a + 2][a + 2]
        ey = F[a + 2][a] / frr
        ex = -F[a + 2][a + 1] / frr
        xc, yc = nv['cm']
        out.append({'nivel': nv['id'], 'cm': [r(xc, 3), r(yc, 3)], 'centro_rigidez': [r(xc + ex, 3), r(yc + ey, 3)],
                    'excentricidad': [r(ex, 3), r(ey, 3)]})
    return out


def armar(insumos_sha1):
    """Corre todo el prediseño y devuelve (estructura JSON, chequeos, resumen para imprimir)."""
    pres = leer(INSUMOS['presupuesto'])
    prog = leer(INSUMOS['programa'])
    validar_geometria(prog)
    # ---- historial de ajustes ----------------------------------------------------------------------------------------
    historial = []
    for clave, texto, dim in AJUSTES[:-1]:
        t_ = construir(dim, pres)
        A_ = analizar(t_)
        S_ = sistema_y_R(t_, A_)
        historial.append({'paso': clave, 'cambio': texto, **resumen_rapido(t_, A_, S_)})
    # ---- estructura adoptada ----------------------------------------------------------------------------------------
    torre = construir(DIMENSIONES, pres)
    resortes = mamposteria(torre, pres)
    A = analizar(torre, resortes=resortes_para_analisis(resortes, torre['niveles']))
    S = sistema_y_R(torre, A)
    historial.append({'paso': AJUSTES[-1][0], 'cambio': AJUSTES[-1][1], **resumen_rapido(torre, A, S)})
    D = disenar(torre, A, S['R'], S['Omega0'])
    secciones, asignacion = secciones_y_rotulas(torre, D)
    am = amortiguamiento_y_anclas(A['modelo'])
    C = cimentacion(torre, D, A, S, pres)
    losas = disenar_losa(torre)
    escaleras = disenar_escaleras(torre)
    ref = {'columnas': despiece_columnas(torre, D), 'vigas': despiece_vigas(torre, D), 'muros': despiece_muros(torre, D),
           'losas': despiece_losas(losas), 'escaleras': despiece_escaleras(escaleras)}
    cim = despiece_cimentacion(C)
    cant = cantidades(ref, cim, pres)
    est = salida_json(torre, A, S, D, secciones, asignacion, resortes, am, C, losas, escaleras, ref, cim, cant, historial,
                      insumos_sha1)
    return est


def chequeo(lista, cid, descripcion, valor, limite, cumple, fuente, detalle=None):
    lista.append({'id': cid, 'descripcion': descripcion, 'valor': valor, 'limite': limite, 'cumple': bool(cumple),
                  'fuente': fuente, **({'detalle': detalle} if detalle else {})})


def chequeos_prediseno(torre, A, S, D, C, losas, secciones, est):
    """Todos los chequeos del contrato (13.1 y 17.7); todos bloquean."""
    ch = []
    nv = torre['niveles']
    fr = {s_: [f['fraccion_porticos'] for f in S['participacion'][s_]] for s_ in ('x', 'y')}
    chequeo(ch, 'P0', 'Sistema estructural fijado en el paso 0 (dual DMO): fracción del cortante que toman los pórticos en el '
            'modelo elástico (entrepiso 1) y pórticos diseñados solos para el 25 % del cortante (A.3.2.1.4)',
            {s_: r(fr[s_][0], 3) for s_ in fr}, '25 % de diseño independiente', True, 'NSR-10 A.3.2.1.4 y Tabla A.3-4 (por confirmar)')
    chequeo(ch, 'R', 'R = φa·φp·φr·R0 con cada factor justificado', r(S['R'], 3),
            f'{S["phi_a"]}·{S["phi_p"]}·{S["phi_r"]}·{S["R0"]}', True, 'NSR-10 A.3.3.3 (por confirmar)')
    rt = max(S['cociente_torsional'].values())
    chequeo(ch, 'IRR-1P', 'Irregularidad torsional: deriva máxima de un extremo / promedio de los dos extremos (sin la '
            'extrema, 1bP, en un edificio indispensable)', r(rt, 3), LIMITE_TORSION, rt <= LIMITE_TORSION,
            'NSR-10 Tabla A.3-6, 1aP y 1bP (por confirmar)')
    chequeo(ch, 'IRR-3A', 'Irregularidad geométrica en altura por el retroceso del piso 4 (reportada; entra en φa)',
            r(S['geometrica_3A'], 3), 1.30, True, 'NSR-10 Tabla A.3-7, 3A (por confirmar)')
    T_fhe = {s_: A['fhe'][s_]['T'] for s_ in ('x', 'y')}
    chequeo(ch, 'TA', 'Período de la FHE limitado a Cu·Ta (Ta de «otros sistemas», Ct = 0,049 y α = 0,75)',
            {s_: r(T_fhe[s_], 4) for s_ in T_fhe}, r(A['CuTa'], 4), all(T_fhe[s_] <= A['CuTa'] + 1e-12 for s_ in T_fhe),
            'NSR-10 A.4.2.1 y Tabla A.4.2-1 (por confirmar)')
    aj = {s_: A['ajuste'][s_]['factor'] * A['ajuste'][s_]['V_modal'] / A['ajuste'][s_]['V_fhe'] for s_ in ('x', 'y')}
    chequeo(ch, 'AJ', 'Cortante modal ajustado ≥ 90 % de la FHE (estructura irregular)', {s_: r(aj[s_], 4) for s_ in aj},
            0.90, all(v >= 0.90 - 1e-9 for v in aj.values()), 'NSR-10 A.5.4.5 (por confirmar)')
    dmax = max(d['deriva'] for d in A['derivas'])
    chequeo(ch, 'DER', 'Deriva vectorial máxima con el espectro de diseño (sin reducir por R), en los vértices del contorno',
            r(dmax, 5), 0.01, dmax <= 0.01, 'NSR-10 A.6.3.1 y Tabla A.6.4-1 (E9)')
    dud = max(d['deriva'] for d in A['umbral']['derivas'])
    chequeo(ch, 'UD', 'Umbral de daño (Ad = 0,04; ξ = 2 %) con los muros de mampostería aislados', r(dud, 5), 0.004,
            dud <= 0.004, 'NSR-10 A.12 y Tabla A.12.5-1')
    dum = max(d['deriva'] for d in A['umbral_mamposteria']['derivas'])
    chequeo(ch, 'UD-M', 'Umbral de daño con la mampostería adherida (rigidez secante a 0,2 %)', r(dum, 5), 0.002, dum <= 0.002,
            'NSR-10 Tabla A.12.5-1 (mampostería que no cumple A.12.5.3.1)')
    th = max(max(f_['x'], f_['y']) for f_ in A['estabilidad'])
    chequeo(ch, 'PD', 'Índice de estabilidad θ = P·Δ/(V·h) (si ≤ 0,10 no hace falta amplificar por P-Delta)', r(th, 5), 0.10,
            th <= 0.10, 'NSR-10 A.6.2.3 (por confirmar)')
    # columna fuerte - viga débil
    cvd, exentos = [], 0
    for f, c in D['columnas'].items():
        for plano, v in c['cvd'].items():
            if c['arriba'].get(plano) is None:
                exentos += 1
            else:
                cvd.append((v, f, plano))
    peor = min(cvd)
    chequeo(ch, 'CFVD', 'Columna fuerte-viga débil ΣMnc ≥ 1,2·ΣMnb en todos los nudos con columna encima', r(peor[0], 3), 1.2,
            peor[0] >= 1.2, 'NSR-10 C.21.6.2.2 (exigido por el contrato también en DMO)',
            f'peor nudo: cabeza de {peor[1]} en el plano {peor[2]}; {exentos} nudos de cubierta exentos (sin columna encima)')
    # cortante por capacidad y flexión
    malas_v = [eid for eid, dv in D['vigas'].items() if dv['phiVn_hz'] < dv['Ve'] - 1e-6 or dv['Vs_hz'] > dv['Vs_max'] + 1e-6
               or dv['est_hz'].get('no_alcanza')]
    malas_c = [f for f, c in D['columnas'].items() if c['transversal']['phiVn'] < c['transversal']['Ve'] - 1e-6
               or c['transversal']['Vs'] > 0.66 * math.sqrt(FC) * c['b'] * c['transversal']['d'] * 1000 + 1e-6
               or c['transversal']['no_alcanza'] or c['transversal']['ramas'] > c['transversal']['barras_por_cara']]
    malas_m = [f'{pid}-{nv_["nivel"]}' for pid, dm in D['muros'].items() for nv_ in dm['niveles']
               if nv_['phiVn'] < nv_['Ve'] - 1e-6]
    malos_a = [aid for aid, ac in D['acoples'].items() if not ac['Vn_max_ok'] or ac['est'].get('no_alcanza')]
    chequeo(ch, 'VCAP', 'Cortante por capacidad cubierto (vigas con Mpr, columnas con Mpr, muros con la sobrerresistencia '
            'a flexión y vigas de enlace)', len(malas_v) + len(malas_c) + len(malas_m) + len(malos_a), 0,
            not (malas_v or malas_c or malas_m or malos_a), 'NSR-10 C.21.3.3, C.21.5.4, C.21.6.5 y C.21.9.4 (por confirmar)',
            ', '.join(malas_v + malas_c + malas_m + malos_a) or None)
    flex_v = [eid for eid, dv in D['vigas'].items() if dv['phiMn_neg'] < dv['Mneg_u'] - 1e-6 or dv['phiMn_pos'] < dv['Mpos_u'] - 1e-6]
    flex_c = [f for f, c in D['columnas'].items() if c['util_PM'] > 1.0 + 1e-9]
    flex_m = [f'{pid}-{nv_["nivel"]}' for pid, dm in D['muros'].items() for nv_ in dm['niveles']
              if min(nv_['phiMn_pos'], nv_['phiMn_neg']) < nv_['Mu'] - 1e-6]
    chequeo(ch, 'FLEX', 'Flexión y flexocompresión: φMn ≥ Mu en vigas y muros, contorno de carga biaxial ≤ 1 en columnas',
            len(flex_v) + len(flex_c) + len(flex_m), 0, not (flex_v or flex_c or flex_m), 'NSR-10 C.10 y C.21',
            ', '.join(flex_v + flex_c + flex_m) or None)
    rho_c = [area(c['n'], c['num']) / (c['b'] ** 2) for c in D['columnas'].values()]
    rho_v = [max(dv['rho_sup'], dv['rho_inf']) for dv in D['vigas'].values()]
    chequeo(ch, 'CUANT', 'Cuantías: columnas entre 1 % y 4 % (C.21.6.3.1); vigas ≤ 2,5 % (C.21.5.2.1)',
            {'columnas': [r(min(rho_c), 4), r(max(rho_c), 4)], 'vigas_max': r(max(rho_v), 4)}, {'columnas': [0.01, 0.04], 'vigas': 0.025},
            min(rho_c) >= 0.01 - 1e-9 and max(rho_c) <= 0.04 and max(rho_v) <= 0.025, 'NSR-10 C.21 (por confirmar)')
    so_mal = [f for f, c in D['columnas'].items() if c['transversal']['s_lo'] > c['transversal']['so_max'] + 1e-9
              or c['transversal']['Ash_mm2'] < c['transversal']['Ash_req_mm2'] - 1e-6
              or c['transversal']['ramas'] > c['transversal']['barras_por_cara']]
    chequeo(ch, 'DMO', 'Detallado DMO de columnas: so ≤ min(8·db, 16·d_estribo, b/3, 150 mm) en lo ≥ max(ln/6, b, 500 mm), '
            'Ash de C.21.6.4.4 y a lo sumo una rama por barra de la cara (cada gancho abraza una barra)',
            len(so_mal), 0, not so_mal, 'NSR-10 C.21.3.5, C.21.6.4.2, C.21.6.4.4 y C.7.10.5.3 (por confirmar)', ', '.join(so_mal) or None)
    bordes = [f'{pid}-{nv_["nivel"]}' for pid, dm in D['muros'].items() for nv_ in dm['niveles'] if nv_['requiere_borde']]
    chequeo(ch, 'BORDE', 'Muros: profundidad del eje neutro c frente a lw/(600·δu/hw) (elementos de borde especiales)',
            len(bordes), 0, True, 'NSR-10 C.21.9.6.2 (por confirmar)',
            ('requieren elemento de borde confinado (se detalla): ' + ', '.join(bordes)) if bordes else 'ningún muro lo requiere')
    # cimentación
    geo = [gid for gid, g, sg in C['elementos'] if not verificar_grupo(sg['combos'], sg['pos'], C['capacidad'])[0]]
    estr = [gid for gid, g, sg in C['elementos'] if not sg['diseno']['ok']]
    chequeo(ch, 'CIM-GEO', 'Capacidad de los pilotes en cada grupo (estática FS 3 y sismo de servicio FS 1,5, en compresión y '
            'en tracción)',
            len(geo), 0, not geo, 'NSR-10 H.4.7-1 (por confirmar) y FHWA-NHI-10-016', ', '.join(geo) or None)
    chequeo(ch, 'CIM-EST', 'Dados y losas de pilotes: punzonamiento de la columna y del pilote, cortante y flexión',
            len(estr), 0, not estr, 'NSR-10 C.15.5 y C.11.11', ', '.join(estr) or None)
    va_mal = [v['id'] for v in C['vigas_amarre'] if not v['superior']]
    chequeo(ch, 'CIM-VA', 'Vigas de amarre: 0,25·Aa·Pu axial y asentamiento diferencial', len(va_mal), 0, not va_mal,
            'NSR-10 C.15.13 (por confirmar)', ', '.join(va_mal) or None)
    pil_mal = [gid for gid, g, sg in C['elementos'] if sg['pilote']['phiPn_max_kN'] < sg['pilote']['Pu_kN']]
    chequeo(ch, 'CIM-PIL', 'Pilotes: φPn,max ≥ Pu, P-M en la cabeza con el cortante de diseño y tracción de capacidad',
            len(pil_mal), 0, not pil_mal, 'NSR-10 C.10.3.6 y título H (por confirmar)', ', '.join(pil_mal) or None)
    los_mal = [p['id'] for p in losas if p['ln'] > 0 and p['ln'] / H_LOSA > (16 if p['caso'] == 'simple' else
                                                                        (18.5 if p['caso'] == 'extrema' else 21)) + 1e-9]
    chequeo(ch, 'LOSA', 'Losa nervada: altura mínima sin cálculo de deflexiones (ln/16, ln/18,5 y ln/21)', len(los_mal), 0,
            not los_mal, 'NSR-10 Tabla C.9.5(a)', ', '.join(los_mal) or None)
    # θy de la estructura publicada contra la fórmula del esquema (± 1 %), como validar_resultado.mjs
    peor_t = 0.0
    for b_ in est['bloques']:
        alturas = {k + 1: n_['altura_entrepiso'] for k, n_ in enumerate(b_['niveles'])}
        zs = [0.0] + [n_['z'] for n_ in b_['niveles']]
        for P in b_['porticos']:
            ns_ = {n_['id']: n_ for n_ in P['nodos']}
            for e in P['elementos']:
                sc = secciones[e['seccion']]
                EI = EC * 1000 * sc['I'] * sc['factor_fisuracion']
                if e['tipo'] == 'muro_concreto':
                    lar = sc['lp_m']
                else:
                    ni_, nj_ = ns_[e['i']], ns_[e['j']]
                    L_ = (nj_['s'] - ni_['s']) if e['tipo'] == 'viga' else zs[nj_['nivel']] - zs[ni_['nivel']]
                    lar = (L_ - sum(e.get('brazo_rigido_m', [0, 0]))) / 6
                for campo, My in (('theta_y', sc['My_kNm']), ('theta_y_e', sc['My_e_kNm'])):
                    peor_t = max(peor_t, abs(sc[campo] / (My * lar / EI) - 1))
    chequeo(ch, 'THY', 'theta_y = My·L_f/(6·EI_fis) (o My·lp/EI_fis en muros) en cada elemento, como lo revisa '
            'validar_resultado.mjs', r(peor_t, 5), 0.01, peor_t <= 0.01, 'data/sismo/ESQUEMA.md')
    return ch


METODO_SECCIONES = (
    'Cada sección del modelo: A, I e Av brutas de la sección rectangular (vigas sin ala) o con aletas efectivas (muros), '
    'factor de fisuración (columnas 0,70; vigas y muros 0,35). My y My_e por fibras: primera fluencia del acero más '
    'traccionado (εy) o 0,002 en la fibra extrema de concreto, lo que pase primero (Priestley y otros, 2007), con concreto '
    'confinado de Mander y otros (1988) en el núcleo y acero bilineal con 1 % de endurecimiento; Mn y Mn_e con el bloque de '
    'Whitney y εcu = 0,003 (C.10.2); φMn con φ de C.9.3.2.2; Mpr con 1,25·fy y φ = 1 (C.21.5.4.1). Propiedades esperadas '
    "(E16): f'cE = 1,5·f'c y fyE = 1,25·fy (ASCE/SEI 41-17 Tabla 10-1) y φ = 1. theta_y = My·L_f/(6·EI_fis) en vigas y "
    'columnas (doble curvatura) y My·lp/EI_fis en muros; theta_y_e igual con My_e. theta_p_cap («a»), theta_p_b («b») y '
    'los límites IO, LS y CP de ASCE/SEI 41-17 (tablas 10-7, 10-8 y 10-19). endurecimiento = H/k_e: en vigas y columnas '
    '(Mc/My − 1)·θy_e/θcap,pl con Mc/My y θcap,pl de Haselton y otros (2016); en muros, (Mmax − My_e)/(EI_fis·(φmax − φy)) '
    'del momento-curvatura esperado. Vn con Vc + Vs del refuerzo transversal de la zona de rótula (Vc = 0 si el cortante '
    'del sismo es más de la mitad del de diseño, C.21.5.4.2); en muros, Acv·(αc·√f\'c + ρt·fy) ≤ 0,83·√f\'c·Acv.')

VERIFICACION_NSR10 = {
    'zona_de_amenaza': 'intermedia: Aa = Av = 0,15 (Yondó, Apéndice A-4; amenaza.json → nsr10) y NSR-10 A.2.3 define la zona '
                       'intermedia con 0,10 < Aa ≤ 0,20 (numeral por confirmar)',
    'capacidad_de_disipacion': 'DMO: en zona intermedia las tablas A.3-1 a A.3-4 piden como mínimo capacidad moderada de '
                               'disipación de energía para el concreto reforzado (A.3.1, por confirmar); el sistema dual de muros '
                               'de concreto DMO con pórticos DMO está permitido sin límite de altura en zona intermedia',
    'grupo_IV': 'Revisión (de memoria del texto de la NSR-10; el 24-oct-2026 no se pudo abrir el Título A desde este entorno): '
                'el grupo de uso IV no cambia la capacidad de disipación exigida en zona intermedia; sí exige I = 1,5 '
                '(A.2.5), la verificación del umbral de daño (A.12, Ad = 0,04), el grado de desempeño superior de los '
                'elementos no estructurales (A.9) y la supervisión técnica (título I y Ley 400 de 1997). Por confirmar con '
                'el texto oficial. Por ser un hospital, el prediseño adopta además criterios más exigentes que el mínimo '
                'DMO, todos declarados: confinamiento Ash de DES en las columnas (C.21.6.4.4), cortante por capacidad con '
                'Mpr (1,25·fy) en vigas, columnas y muros, columna fuerte-viga débil en todos los nudos, sin '
                'irregularidad torsional extrema y cimentación revisada con el sismo de capacidad.',
    'tablas': 'R0 = 6,0 y Ω0 = 2,5 de la fila de muros de concreto DMO con pórticos de concreto DMO de la Tabla A.3-4 '
              '(sistema dual); valores por confirmar con el texto',
}


def salida_json(torre, A, S, D, secciones, asignacion, resortes, am, C, losas, escaleras, ref, cim, cant, historial,
                insumos_sha1):
    nv = torre['niveles']
    res = A['resp']
    # ---- niveles ----------------------------------------------------------------------------------------------------
    niveles = []
    for n in nv:
        niveles.append({'id': n['id'], 'z': n['z'], 'altura_entrepiso': r(n['h'], 3), 'masa_t': r(n['masa_t'], 3),
                        'Jz_t_m2': r(n['Jz_t_m2'], 1), 'cm': [r(n['cm'][0], 4), r(n['cm'][1], 4)],
                        'contorno': n['contorno'], 'peso_sismico_kN': r(n['masa_t'] * G, 2),
                        'P_sobre_entrepiso_kN': r(n['P_sobre_kN'], 1),
                        'detalle_masa': {k: r(v, 2) for k, v in sorted(n['detalle'].items())}})
    # ---- pórticos ---------------------------------------------------------------------------------------------------
    porticos = []
    for P in torre['porticos']:
        nodos = []
        for nd in P['nodos']:
            z = Z[nd['nivel']]
            xyz = [nd['s'], P['c'], z] if P['dir'] == 'x' else [P['c'], nd['s'], z]
            o = {'id': nd['id'], 's': r(nd['s'], 4), 'nivel': nd['nivel'], 'xyz': [r(q, 4) for q in xyz]}
            c = P['cargas'].get(nd['id'])
            if c:
                o['carga_kN'] = r(c['D'] + FRACCION_VIVA_MASA * c['L'], 2)
            nodos.append(o)
        elementos = []
        for e in P['elementos']:
            o = {'id': e['id'], 'tipo': e['tipo']}
            if e['tipo'] == 'columna':
                o['fisico'] = e['fisico']
            o.update({'i': e['i'], 'j': e['j'], 'seccion': asignacion[e['id']], 'eje': e['eje'], 'nivel': e['nivel']})
            if e['tipo'] != 'muro_concreto':
                o['brazo_rigido_m'] = [r(e['arms'][0], 3), r(e['arms'][1], 3)]
            if e['tipo'] == 'viga':
                o['w_gravedad_kN_m'] = r(e['w']['D'] + FRACCION_VIVA_MASA * e['w']['L'], 3)
            elementos.append(o)
        porticos.append({'id': P['id'], 'direccion': P['dir'], 'coordenada': P['c'], 'nodos': nodos,
                         'apoyos': {nd['id']: 'empotrado' for nd in P['nodos'] if nd['nivel'] == 0},
                         'elementos': elementos})
    resortes_out = [{k: v for k, v in rr.items() if k != 'portico'} for rr in resortes]
    # ---- prediseño --------------------------------------------------------------------------------------------------
    modos = A['modos']
    modos_out = [{'T_s': r(m['T'], 5), 'masa_x': r(m['mx'], 4), 'masa_y': r(m['my'], 4), 'masa_rz': r(m['mr'], 4)} for m in modos]
    fhe = {s_: {'T_s': r(A['fhe'][s_]['T'], 4), 'Sa_g': r(A['fhe'][s_]['Sa'], 4), 'k': A['fhe'][s_]['k'],
                'W_kN': r(A['fhe'][s_]['W'], 1), 'Vs_kN': r(A['fhe'][s_]['Vs'], 1),
                'Vs_reducido_kN': r(A['fhe'][s_]['Vs'] / S['R'], 1),
                'F_kN': [r(f, 1) for f in A['fhe'][s_]['F']]} for s_ in ('x', 'y')}
    modal = {s_: {'V_modal_kN': r(A['ajuste'][s_]['V_modal'], 1), 'factor_ajuste': r(A['ajuste'][s_]['factor'], 4),
                  'minimo': A['ajuste'][s_]['minimo']} for s_ in ('x', 'y')}
    derivas = [{'entrepiso': d['entrepiso'], 'deriva': r(d['deriva'], 6), 'punto': d['punto'], 'dx_m': r(d['dx_m'], 5),
                'dy_m': r(d['dy_m'], 5), 'combinacion': d['combinacion']} for d in A['derivas']]
    der_port = {}
    E = A['E']
    for pm in A['modelo'].porticos:
        fila = []
        for k in pm.niveles:
            i = res.i_port[(pm.id, k)]
            dx_, dy_ = abs(E['x'][i]), abs(E['y'][i])
            fila.append(r(max(dx_ + 0.3 * dy_, 0.3 * dx_ + dy_) / nv[k - 1]['h'], 6))
        der_port[pm.id] = fila
    ud = {'aislados': [{'entrepiso': d['entrepiso'], 'deriva': r(d['deriva'], 6), 'punto': d['punto']}
                       for d in A['umbral']['derivas']],
          'mamposteria_adherida': [{'entrepiso': d['entrepiso'], 'deriva': r(d['deriva'], 6), 'punto': d['punto']}
                                   for d in A['umbral_mamposteria']['derivas']],
          'espectro': f'Sa = 3,0·Ad·Fa = {es(3 * AD * FA, 3)} g hasta TC = 0,5·Fv/Fa = {es(TC_UD, 3)} s y 1,5·Ad·Fv/T después; '
                      'ξ = 2 % en la combinación modal (CQC) y torsión accidental del 5 %',
          'limites': {'aislados': 0.004, 'mamposteria_adherida': 0.002}}
    tors = {s_: [{'entrepiso': q['entrepiso'], 'cociente': r(q['cociente'], 4), 'Ax': r(q['Ax'], 4)} for q in A['torsion'][s_]]
            for s_ in ('x', 'y')}
    cr = centro_de_rigidez(A['modelo'], nv)
    cvd = []
    for f, c in sorted(D['columnas'].items()):
        for plano, v in sorted(c['cvd'].items()):
            cvd.append({'columna': f, 'plano': plano, 'nudo': 'cabeza', 'cociente': r(v, 3),
                        'exento': c['arriba'].get(plano) is None})
    capac = {
        'vigas': [{'id': eid, 'Ve_kN': r(dv['Ve'], 1), 'phiVn_kN': r(dv['phiVn_hz'], 1), 'Vc_en_2h': r(dv['Vc_hz'], 1)}
                  for eid, dv in sorted(D['vigas'].items())],
        'columnas': [{'id': f, 'Ve_kN': r(c['transversal']['Ve'], 1), 'phiVn_kN': r(c['transversal']['phiVn'], 1)}
                     for f, c in sorted(D['columnas'].items())],
        'muros': [{'id': f'{pid}-{nv_["nivel"]}', 'Vu_kN': r(nv_['Vu'], 1), 'Omega_v': r(nv_['Omega_v'], 3),
                   'Ve_kN': r(nv_['Ve'], 1), 'phiVn_kN': r(nv_['phiVn'], 1), 'omega_v_informativo': r(nv_['omega_v'], 2),
                   'Ve_con_omega_v_kN': r(nv_['Ve_din'], 1), 'Mu_kNm': r(nv_['Mu'], 0),
                   'phiMn_kNm': r(min(nv_['phiMn_pos'], nv_['phiMn_neg']), 0), 'c_max_m': r(nv_['c_max'], 3),
                   'c_limite_m': r(nv_['c_lim'], 3), 'requiere_borde': nv_['requiere_borde']}
                  for pid, dm in sorted(D['muros'].items()) for nv_ in dm['niveles']],
    }
    prediseno = {
        'metodo': ('Modelo pseudotridimensional de Wilson y Dovey (1972) en Python, la misma idealización del motor '
                   '(web/js/sismo/modelo.js): pórticos planos condensados por complemento de Schur sobre diafragmas '
                   'rígidos, Timoshenko con brazos rígidos, axial EA/L_f, inercias fisuradas (columnas 0,70, vigas y '
                   'muros 0,35), modos por Jacobi sobre K y M simétricos (12 modos), combinación CQC (Der Kiureghian, '
                   '1981), FHE con T ≤ Cu·Ta, torsión accidental del 5 % amplificada por Ax = (δmax/1,2·δprom)² y '
                   'efectos ortogonales 100 % + 30 %. Secciones por fibras (Whitney para Mn, Mander para el '
                   'momento-curvatura, acero con endurecimiento del 1 %).'),
        'metodo_secciones': METODO_SECCIONES,
        'historial_de_ajustes': historial,
        'dimensiones_adoptadas': {
            'columnas': f'{es(DIMENSIONES["col"])} × {es(DIMENSIONES["col"])} m; eje A (fachada occidental): '
                        f'{es(DIMENSIONES["col_eje"]["A"])} × {es(DIMENSIONES["col_eje"]["A"])} m',
            'vigas': f'{es(DIMENSIONES["vx"][0])} × {es(DIMENSIONES["vx"][1])} m; eje A: '
                     f'{es(DIMENSIONES["vy_eje"]["A"][0])} × {es(DIMENSIONES["vy_eje"]["A"][1])} m; vigas banda de '
                     f'{es(H_LOSA)} m entre la columna C y los muros',
            'muros': f'{len(MUROS_ADOPTADOS)} paños de {es(DIMENSIONES["muro_t"])} m: ' + ', '.join(MUROS_ADOPTADOS),
            'losa': f'nervada de {es(H_LOSA)} m (nervios de {es(NERVIO_B)} m cada {es(NERVIO_S)} m, loseta de {es(LOSETA)} m)',
            'concreto': f"f'c = {es(FC, 0)} MPa; acero fy = {es(FY, 0)} MPa (NTC 2289)",
        },
        'eleccion_muros': {
            'activos': MUROS_ADOPTADOS,
            'longitud_alma_m': r(sum(torre['muros'][p]['l_alma'] for p in torre['muros']), 2),
            'longitud_concreto_m': r(sum(torre['muros'][p]['largo_fisico'] for p in torre['muros']), 2),
            'presupuesto_m': 45.0,
            'paneles_de_nucleo': [{'nombre': x['nombre'], 'tramo': list(x['tramo']), 'material': x['material'], 'muro': x['muro']}
                                  for x in paneles_nucleo(MUROS_ADOPTADOS)],
            'por_que': ('Con los 7 paños posibles el centro de rigidez queda casi 5 m al oriente del de masa y la torsión es '
                        'extrema (1bP). Quitando la cara sur de la escalera norte (MX-6) y el foso (MY-N4) los muros en x '
                        'quedan repartidos a lado y lado del centro de masa en y, y los dos muros en y son los machones '
                        'de 6,5 m que dejan las puertas; el resto de los núcleos va en mampostería separada.'),
            'notas_por_muro': {p: torre['muros'][p]['notas'] for p in torre['muros']},
        },
        'R': {'R0': S['R0'], 'Omega0': S['Omega0'], 'phi_a': S['phi_a'], 'phi_p': S['phi_p'], 'phi_r': S['phi_r'], 'R': r(S['R'], 4),
              'justificacion': {
                  'phi_a': f'0,9 por la irregularidad geométrica en altura 3A (42/30 = {es(S["geometrica_3A"], 2)} > 1,30); '
                           'sin 1A (piso flexible) ni 2A (masa)',
                  'phi_p': f'{S["phi_p"]} por la irregularidad torsional {S["tipo_p"]} (cociente '
                           f'{es(max(S["cociente_torsional"].values()), 3)})',
                  'phi_r': ('0,75: algún muro con relación altura del piso/longitud > 1,0 entra en la prueba de remoción '
                            '(ASCE/SEI 7-16 12.3.4.2 a y Tabla 12.3-3, a falta del texto de NSR-10 A.3.3.8; por confirmar) y '
                            'la resistencia del piso sin él no se revisa antes del diseño') if S['phi_r'] < 1 else
                           ('1,0: ningún muro tiene relación altura del piso/longitud > 1,0 (h/l máximo '
                            f'{es(max(x["h_piso_sobre_l_alma_max"] for x in S["redundancia"]), 2)}), así que ninguno entra '
                            'en la prueba de remoción de ASCE/SEI 7-16 12.3.4.2 a y Tabla 12.3-3 (a falta del texto de '
                            'NSR-10 A.3.3.8; por confirmar), y perder el momento en los dos extremos de una viga quita a lo '
                            'sumo una fracción pequeña de la resistencia del piso (chequeo RED). La fracción del cortante '
                            'elástico que toma un muro no es la prueba: la prueba compara resistencias'),
                  'R_si_phi_r_fuera_075': r(S['R_con_phi_r_075'], 4),
                  'nota_phi_r': ('Mientras el numeral A.3.3.8 siga por confirmar: con φr = 0,75 sería R = '
                                 f'{es(S["R_con_phi_r_075"], 3)} y las fuerzas de diseño, '
                                 f'{es(100 * (S["R"] / S["R_con_phi_r_075"] - 1), 0)} % mayores.')}},
        'redundancia': [{'muro': x['muro'], 'h_piso_sobre_l_alma_max': r(x['h_piso_sobre_l_alma_max'], 3),
                         'sujeto_a_la_prueba': x['sujeto_a_la_prueba'],
                         'fraccion_cortante_elastico_entrepiso_1': r(x['fraccion_cortante_elastico_entrepiso_1'], 3),
                         'cociente_torsional_sin_el': r(x['cociente_torsional_sin_el'], 3), 'cumple': x['cumple'],
                         'nota': ('informativos: la fracción del cortante elástico y la torsión sin el muro no deciden φr '
                                  'si el muro no entra en la prueba')}
                        for x in S['redundancia']],
        'irregularidades': {
            'torsional_1P': {'cocientes': tors, 'maximo': {s_: r(S['cociente_torsional'][s_], 4) for s_ in ('x', 'y')},
                             'tipo': S['tipo_p'], 'limites': [1.2, 1.4]},
            'geometrica_3A': {'cociente': r(S['geometrica_3A'], 3), 'limite': 1.3, 'irregular': S['geometrica_3A'] > 1.3},
            'rigidez_1A': [{**x, 'k_kN_m': r(x['k_kN_m'], 0), 'k_sobre_k_arriba': r(x['k_sobre_k_arriba'], 3),
                            'k_sobre_prom3': r(x['k_sobre_prom3'], 3)} for x in S['irr_1A']],
            'masa_2A': [{'nivel': x['nivel'], 'cociente': r(x['cociente'], 3)} for x in S['irr_2A']],
        },
        'participacion_porticos': {s_: [{'entrepiso': f['entrepiso'], 'porticos_kN': r(f['porticos_kN'], 1),
                                         'muros_kN': r(f['muros_kN'], 1), 'fraccion_porticos': r(f['fraccion_porticos'], 4)}
                                        for f in S['participacion'][s_]] for s_ in ('x', 'y')},
        'periodos': {'modos': modos_out, 'T1x_s': r(A['T1x'], 5), 'T1y_s': r(A['T1y'], 5),
                     'Ta_s': r(A['Ta'], 4), 'Cu': r(CU, 4), 'CuTa_s': r(A['CuTa'], 4),
                     'fila_Ta': 'Tabla A.4.2-1, «otros sistemas» (con muros): Ct = 0,049 y α = 0,75 (por confirmar)'},
        'cortante_basal': {'fhe': fhe, 'modal': modal},
        'derivas_vector': derivas, 'derivas_porticos': der_port, 'derivas_umbral_dano': ud,
        'estabilidad': [{'entrepiso': k + 1, 'x': r(f_['x'], 5), 'y': r(f_['y'], 5)} for k, f_ in enumerate(A['estabilidad'])],
        'centro_rigidez': cr,
        'amortiguamiento': {'periodos_ancla_s': [r(am['Ti'], 5), r(am['Tj'], 5)], 'a0': r(am['a0'], 6), 'a1': r(am['a1'], 8),
                            'xi_modos': [r(x, 5) for x in am['xi']],
                            'masa_acumulada_12_modos': {'x': r(am['cum_x'], 4), 'y': r(am['cum_y'], 4)},
                            'regla': 'E8: Ti = T1; Tj = min(período con 90 % de masa acumulada en x y en y, 0,2·T1), con la '
                                     'rigidez inicial (elástica condensada más K_PΔ); a0 y a1 con ξ exacto en las dos anclas '
                                     '(a0 + a1·k_r = 2ξ·ω_r, k_r = φ_rᵀK_elφ_r), y estas anclas solo valen con los muros de '
                                     'mampostería aislados como en el archivo (con «confinados» el motor las recalcula)'},
        'columna_fuerte_viga_debil': cvd,
        'cortante_por_capacidad': capac,
        'cuantias': {'columnas': {f: r(area(c['n'], c['num']) / c['b'] ** 2, 5) for f, c in sorted(D['columnas'].items())},
                     'vigas': {eid: [r(dv['rho_sup'], 5), r(dv['rho_inf'], 5)] for eid, dv in sorted(D['vigas'].items())}},
        'verificacion_nsr10': VERIFICACION_NSR10,
    }
    # ---- cimentación (17.2) -----------------------------------------------------------------------------------------
    cap = C['capacidad']
    cimentacion_out = {
        'suelo_supuesto': SUELO,
        'pilote': {'D_m': D_PILOTE, 'L_m': C['L_pilote'], 'separacion_min_m': S_PILOTES,
                   'capacidad_kN': {k: r(v, 1) for k, v in cap.items() if k != 'L'},
                   'FS': {'estatico': FS_ESTATICO, 'sismo': FS_SISMO, 'capacidad': 1.0},
                   'estudio_de_largo': C['estudio_largo'],
                   'eleccion': 'el largo con el menor total de metros de pilote que resuelve todos los grupos'},
        'reacciones': {k: {'x': r(v['x'], 3), 'y': r(v['y'], 3), 'D_kN': r(v['g']['D'], 1), 'L_kN': r(v['g']['L'], 1),
                           'Lr_kN': r(v['g']['Lr'], 1),
                           'E_kN_kNm': {q: [r(z_, 1) for z_ in v['E'][q]] for q in v['E']},
                           'Ecap_kN_kNm': {q: [r(z_, 1) for z_ in v['Ecap'][q]] for q in v['Ecap']}}
                       for k, v in sorted(C['reacciones'].items())},
        'grupos': [{'id': gid, 'tipo': g['tipo'], 'apoyos': g['apoyos'], 'n_pilotes': sg['n'],
                    'reacciones_pilote_kN': {t: {'max': r(e_['max'], 1), 'min': r(e_['min'], 1), 'max_por': e_['max_c'],
                                                 'min_por': e_['min_c']} for t, e_ in sg['ext'].items()},
                    'h_m': sg['diseno']['h'], 'pilote': {k: (r(v, 4) if isinstance(v, float) else v)
                                                        for k, v in sg['pilote'].items() if k not in ('espiral',)}}
                   for gid, g, sg in C['elementos']],
        'combinaciones': ('estático D + L + Lr (FS 3,0); sismo de servicio D + 0,7E y D + 0,75(L + Lr) + 0,525E (B.2.3; '
                          'FS 1,5); 0,6D + 0,7E en tracción; capacidad D + 0,25L ± Ecap con Ecap = min(Ω0·E; Mpr y Ve de '
                          'muros y columnas) y FS 1,0; mayoradas de B.2.4 para el refuerzo'),
        'nota': 'En la simulación la base sigue empotrada en la cara superior de los dados (sin interacción suelo-estructura).',
        **cim,
    }
    est = {
        'id': 'torre_hospital',
        'nombre': 'Torre del hospital de Yondó (4 pisos, 21,6 × 42,0 m, retroceso del piso 4)',
        'tipo_dato': 'calculo_propio',
        'generado_por': 'scripts/sismo/estructura_torre.py',
        'fecha': FECHA,
        'insumos_sha1': insumos_sha1,
        'sistema_estructural': ('sistema dual: muros de concreto en los núcleos de escaleras con pórticos de concreto '
                                'resistentes a momento, capacidad moderada de disipación de energía (DMO), NSR-10 C.21'),
        'norma': 'NSR-10, títulos A, B, C y H (zona de amenaza sísmica intermedia, grupo de uso IV)',
        'ejes': {'x': [{'id': n, 'x': x} for n, x in EJES_X] + [{'id': 'N', 'x': XN, 'auxiliar': True,
                                                                  'nota': 'cara occidental de los núcleos'}],
                 'y': [{'id': n, 'y': y} for n, y in EJES_Y]},
        'sistema': {'tipo': 'dual', 'fraccion_cortante_porticos': {s_: r(S['participacion'][s_][0]['fraccion_porticos'], 4)
                                                                   for s_ in ('x', 'y')},
                    'tabla': SISTEMAS['dual']['tabla'], 'R0': S['R0'], 'Omega0': S['Omega0'],
                    'justificacion': ('Paso 0. Con el modelo elástico y la FHE, los pórticos toman en el entrepiso 1 el '
                                      f'{es(100 * S["participacion"]["x"][0]["fraccion_porticos"], 1)} % del cortante en x y el '
                                      f'{es(100 * S["participacion"]["y"][0]["fraccion_porticos"], 1)} % en y (el resto, los muros). '
                                      'La NSR-10 (A.3.2.1.4) no clasifica el sistema por esa fracción: exige que el pórtico '
                                      'espacial, esencialmente completo y capaz de llevar las cargas verticales, se diseñe '
                                      'para resistir por sí solo al menos el 25 % del cortante sísmico de diseño. El prediseño '
                                      'lo hace (envolvente de las fuerzas del modelo completo y del modelo de solo pórticos con '
                                      'el 25 % de la FHE y su torsión accidental), así que el sistema es dual (Tabla A.3-4). '
                                      'Desviación del contrato (7.2, paso 0), que tomaba la fracción elástica como criterio.')},
        'materiales': {
            'concreto_28': {'tipo': 'concreto', 'fc_MPa': FC, 'Ec_MPa': EC, 'nu': NU, 'peso_kN_m3': GAMMA_C,
                            'fuente': "NSR-10 C.8.5.1: Ec = 4700·√f'c; f'c del presupuesto (capítulo 3)",
                            'factor_esperado': F_ESP_C},
            'acero_420': {'tipo': 'acero', 'fy_MPa': FY, 'fu_MPa': FU, 'Es_MPa': ES, 'factor_esperado': F_ESP_S,
                          'fuente': 'NTC 2289 (grado 420); factores esperados de ASCE/SEI 41-17 Tabla 10-1'},
            'ladrillo': {k: v for k, v in MAMPOSTERIA['ladrillo'].items() if k != 't_m'},
            'bloque': {k: v for k, v in MAMPOSTERIA['bloque'].items() if k != 't_m'},
        },
        'secciones': secciones,
        'bloques': [{'id': 'torre', 'niveles': niveles, 'porticos': porticos, 'resortes': resortes_out}],
        'amortiguamiento': {'tipo': 'rayleigh', 'xi': XI, 'periodos_ancla_s': [r(am['Ti'], 5), r(am['Tj'], 5)],
                            'rigidez': 'inicial_parte_elastica'},
        'p_delta': True,
        'limites': {'deriva': 0.01, 'deriva_umbral_dano': 0.004, 'deriva_umbral_dano_mamposteria': 0.002,
                    'tipo_deriva': 'vectorial en los vértices del contorno',
                    'fuente': 'NSR-10 A.6.3.1, A.6.4.1 y Tabla A.12.5-1'},
        'diseno': {'Aa': AA, 'Av': AV, 'Ad': AD, 'suelo': 'D', 'Fa': FA, 'Fv': FV, 'I': IMP, 'zona': 'intermedia',
                   'capacidad_disipacion': 'DMO', 'Ta_s': r(A['Ta'], 4), 'CuTa_s': r(A['CuTa'], 4),
                   'Sa_g': r(A['fhe']['x']['Sa'], 4), 'R': r(S['R'], 4), 'Omega0': S['Omega0'],
                   'Vs_kN': r(A['fhe']['x']['Vs'], 1)},
        'prediseno': prediseno,
        'cimentacion': cimentacion_out,
        'refuerzo': {'convenciones': {
            'barras': {f'N.º {k}': {'db_mm': v[0], 'area_mm2': v[1], 'kg_m': v[2]} for k, v in BARRAS.items()},
            'designacion': 'NTC 2289, fy = 420 MPa; N.º n = n/8 de pulgada (NSR-10 Tabla C.3.5.3-2)',
            'recubrimientos_m': REC, 'ganchos': 'estribos y ganchos suplementarios con 135° y 6·db ≥ 75 mm (C.7.1.3 y '
                                                'C.21.1); barras ancladas en nudos exteriores con gancho de 90° y ldh de '
                                                'C.21.7.5.1', 'traslapos': 'clase B = 1,3·ld (C.12.15)',
            'cotas': 'z desde el piso terminado del piso 1; columnas y muros por piso de z0 a z1; vigas por su eje en z del nivel'},
            **ref},
        'cantidades': cant,
        'fuentes': [
            'data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md (7.2, 13.1 y 17)',
            'data/proyectos/torre_hospital/presupuesto.json (capítulos 2, 3 y 4) y programa.json (geometría, núcleos, cubierta)',
            'data/edificios/torre_hospital_plantas.json (vanos de las puertas de las escaleras; equipo B)',
            'data/sismo/amenaza.json → nsr10 (Aa, Av, Ad, Fa, Fv, I)',
            'NSR-10 (Decreto 926 de 2010 y sus modificaciones), títulos A, B, C y H; numerales «por confirmar» en cada texto',
            'Wilson, E. L. y Dovey, H. H. (1972), Three-dimensional analysis of building systems — TABS',
            'Der Kiureghian, A. (1981), A response spectrum method for random vibration analysis of MDF systems',
            'Mander, J. B., Priestley, M. J. N. y Park, R. (1988), Theoretical stress-strain model for confined concrete',
            'Priestley, M. J. N., Calvi, G. M. y Kowalsky, M. J. (2007), Displacement-Based Seismic Design of Structures',
            'ASCE/SEI 41-17, Seismic Evaluation and Retrofit of Existing Buildings, cap. 10 (tablas 10-1, 10-7, 10-8 y 10-19)',
            'Haselton, C. B., Liel, A. B., Taylor Lange, S. y Deierlein, G. G. (2016), ACI Structural Journal 113(6)',
            'Tomaževič, M. (1999), Earthquake-Resistant Design of Masonry Buildings; Turnšek y Čačovič (1971)',
            "O'Neill, M. W. y Reese, L. C. (1999) y Brown y otros (2010), FHWA-NHI-10-016, Drilled Shafts",
            'Davisson, M. T. (1970) y Hetényi, M. (1946), pilotes con carga lateral',
        ],
        'supuestos': [
            'Sin estudio de suelos: perfil D de amenaza.json y perfil estratigráfico supuesto (cimentacion.suelo_supuesto); '
            'la capacidad de los pilotes es una estimación que fijan el estudio geotécnico y las pruebas de carga.',
            'Base empotrada en la cara superior de los dados; sin interacción suelo-estructura (17.2).',
            'Masa sísmica = carga muerta + 25 % de la viva de los pisos (7.2); la viva de cubierta no entra en la masa.',
            'Los paños de núcleo que no son estructurales se construyen en mampostería separada de la estructura; las '
            'puertas de las escaleras van apiladas en x = 3,1 (y = 15,3 al norte y y = −6,3 al sur) en todos los pisos.',
            'Las vigas banda entre la columna C y los muros no entran en el modelo (casi no acoplan); se diseñan por capacidad.',
            'Cargas muertas de acabados, instalaciones, fachada y divisorios desde las cantidades del presupuesto (capítulo 4) '
            'con pesos unitarios del título B (por confirmar).',
        ],
        'incertidumbres': [
            'Numerales de la NSR-10 citados de memoria (el Título A no se pudo abrir el 24-oct-2026): «por confirmar» en cada uno.',
            'R0 y Ω0 del sistema dual DMO (6,0 y 2,5) por confirmar con la Tabla A.3-4.',
            'Parámetros de las rótulas de ASCE/SEI 41-17 (a, b, IO, LS, CP) y del endurecimiento de Haselton y otros (2016): '
            'son de modelado, no de diseño.',
            'Perfil del suelo, capacidad de pilotes, asentamientos y nivel freático: estimaciones.',
            'La mampostería se reparte en líneas representativas (no en su posición exacta de la planta de B).',
        ],
    }
    est['prediseno']['chequeos'] = chequeos_prediseno(torre, A, S, D, C, losas, secciones, est)
    return est


def validar_amenaza(amenaza):
    """Los parámetros del espectro de este script deben ser los de amenaza.json (dato oficial)."""
    n = amenaza['nsr10']
    pares = [('Aa', n['Aa']['valor'], AA), ('Av', n['Av']['valor'], AV), ('Ad', n['Ad']['valor'], AD),
             ('Fa', n['Fa']['valor_yondo'], FA), ('Fv', n['Fv']['valor_yondo'], FV), ('I', n['I']['valor'], IMP)]
    malos = [f'{k}: {a} ≠ {b}' for k, a, b in pares if abs(a - b) > 1e-12]
    if malos:
        raise SystemExit('amenaza.json no coincide con los parámetros del prediseño: ' + '; '.join(malos))


def serializar(est):
    return json.dumps(est, ensure_ascii=False, indent=1) + '\n'


def imprimir_resumen(est, informe=False):
    p = est['prediseno']
    print(f'Sistema: {est["sistema"]["tipo"]} DMO; R0 = {p["R"]["R0"]}, Ω0 = {p["R"]["Omega0"]}, '
          f'R = {p["R"]["phi_a"]}·{p["R"]["phi_p"]}·{p["R"]["phi_r"]}·{p["R"]["R0"]} = {p["R"]["R"]}')
    per = p['periodos']
    print(f'Períodos: T1 = {per["modos"][0]["T_s"]} s, T1x = {per["T1x_s"]} s, T1y = {per["T1y_s"]} s; '
          f'Ta = {per["Ta_s"]} s, Cu·Ta = {per["CuTa_s"]} s')
    for s_ in ('x', 'y'):
        f = p['cortante_basal']['fhe'][s_]
        m = p['cortante_basal']['modal'][s_]
        print(f'FHE {s_}: T = {f["T_s"]} s, Sa = {f["Sa_g"]} g, Vs = {f["Vs_kN"]} kN (Vs/R = {f["Vs_reducido_kN"]} kN); '
              f'modal {m["V_modal_kN"]} kN, factor de ajuste {m["factor_ajuste"]}')
    print('Historial de ajustes:')
    for h in p['historial_de_ajustes']:
        print(f'  {h["paso"]}. {h["cambio"][:90]}… T1 = {h["T1_s"]} s, torsión x/y = {h["cociente_torsional"]["x"]}/'
              f'{h["cociente_torsional"]["y"]}, deriva {h["deriva_max_pct"]} %, umbral {h["deriva_umbral_max_pct"]} %, R = {h["R"]}')
    cim = est['cimentacion']
    print(f'Cimentación: pilotes de {cim["pilote"]["D_m"]} m × {cim["pilote"]["L_m"]} m, {est["cantidades"]["pilotes"]["n"]} '
          f'pilotes ({est["cantidades"]["pilotes"]["ml"]} m); Qult = {cim["pilote"]["capacidad_kN"]["Qult"]} kN')
    print(f'Cantidades: superestructura {est["cantidades"]["acero_superestructura_kg"]} kg de acero; cimentación '
          f'{est["cantidades"]["acero_cimentacion_kg"]} kg; efecto en el costo directo frente al presupuesto: '
          f'{es(est["cantidades"]["efecto_total_costo_directo_cop"], 0)} COP')
    if informe:
        for c in est['cantidades']['comparacion_presupuesto']:
            print(f'  {c["item"]} {c["descripcion"][:60]}: {c["presupuesto"]} → {c["prediseno"]} {c["unidad"]} '
                  f'({c["diferencia_pct"]} %, {es(c["efecto_cop"], 0)} COP)')
    print('Chequeos:')
    for c in p['chequeos']:
        print(f'  {"✓" if c["cumple"] else "✗"} {c["id"]:8s} {c["descripcion"][:96]}: {c["valor"]} (límite {c["limite"]})'
              + (f' — {c["detalle"]}' if c.get('detalle') and (informe or not c['cumple']) else ''))
    return all(c['cumple'] for c in p['chequeos'])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--verificar', action='store_true', help='regenera en memoria y compara byte a byte con el archivo')
    ap.add_argument('--informe', action='store_true', help='imprime además el detalle')
    args = ap.parse_args()
    validar_amenaza(leer(INSUMOS['amenaza']))
    insumos = {INSUMOS[k]: sha1(INSUMOS[k]) for k in ('presupuesto', 'programa', 'amenaza')}
    est = armar(insumos)
    texto = serializar(est)
    ok = imprimir_resumen(est, args.informe)
    if args.verificar:
        actual = SALIDA.read_bytes() if SALIDA.exists() else b''
        igual = actual == texto.encode('utf-8')
        print(f'{SALIDA.relative_to(RAIZ)}: {"idéntico byte a byte" if igual else "DIFIERE de lo que genera el script"} '
              f'({len(texto.encode("utf-8")) / 1024:.0f} KB)')
        sys.exit(0 if (igual and ok) else 1)
    SALIDA.write_text(texto, encoding='utf-8')
    print(f'escrito {SALIDA.relative_to(RAIZ)} ({len(texto.encode("utf-8")) / 1024:.0f} KB)')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
