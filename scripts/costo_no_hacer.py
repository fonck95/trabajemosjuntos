#!/usr/bin/env python3
"""Costo de no hacer, recaudo potencial y equivalencias en obras (tarea D4).

Genera data/comparativa/costo_no_hacer.json.

Qué calcula:
  1. Costos unitarios de obras y equipos en pesos de 2026 (con fuente y rango).
  2. Contrafactual solar: ¿cuánto se habría ahorrado neto hasta 2026 si los 469 kWp y
     770 kWh del plan se hubieran instalado al inicio de cada gobierno (2008-2024)?
  3. Contrafactual de ahorro: 10 % de las regalías directas 2004-2011 en un fondo con
     rendimiento real de 3-4 %.
  4. Recaudo potencial de predial e ICA frente a municipios comparables (TerriData).
  5. Costo de no tratar las aguas residuales (tasa retributiva estimada).

Uso:
  python3 -I scripts/costo_no_hacer.py --cache /ruta/temporal
  (descarga los perfiles de TerriData en --cache si no están; no escribe nada más
  que el JSON de salida).

Todas las series externas usadas están copiadas abajo con su fuente y fecha de consulta
(21-oct-2026). Pesos de 2026 = promedio del IPC de enero a septiembre de 2026 (DANE).
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "comparativa" / "costo_no_hacer.json"
CONSULTA = "2026-10-21"

# ---------------------------------------------------------------------------
# 1. Series externas (copiadas de la fuente; ver "fuente" en el JSON)
# ---------------------------------------------------------------------------

# IPC total nacional, DANE, índice base dic-2018 = 100, serie de empalme 2003-2026.
# https://www.dane.gov.co/files/operaciones/IPC/sep2026/anex-IPC-Indices-sep2026.xlsx
IPC_MENSUAL = {
    2003: [50.42, 50.98, 51.51, 52.1, 52.36, 52.33, 52.26, 52.42, 52.53, 52.56, 52.75, 53.07],
    2004: [53.54, 54.18, 54.71, 54.96, 55.17, 55.51, 55.49, 55.51, 55.67, 55.66, 55.82, 55.99],
    2005: [56.45, 57.02, 57.46, 57.72, 57.95, 58.18, 58.21, 58.21, 58.46, 58.6, 58.66, 58.7],
    2006: [59.02, 59.41, 59.83, 60.09, 60.29, 60.48, 60.73, 60.96, 61.14, 61.05, 61.19, 61.33],
    2007: [61.8, 62.53, 63.29, 63.85, 64.05, 64.12, 64.23, 64.14, 64.2, 64.2, 64.51, 64.82],
    2008: [65.51, 66.5, 67.04, 67.51, 68.14, 68.73, 69.06, 69.19, 69.06, 69.3, 69.49, 69.8],
    2009: [70.21, 70.8, 71.15, 71.38, 71.39, 71.35, 71.32, 71.35, 71.28, 71.19, 71.14, 71.2],
    2010: [71.69, 72.28, 72.46, 72.79, 72.87, 72.95, 72.92, 73.0, 72.9, 72.84, 72.98, 73.45],
    2011: [74.12, 74.57, 74.77, 74.86, 75.07, 75.31, 75.42, 75.39, 75.62, 75.77, 75.87, 76.19],
    2012: [76.75, 77.22, 77.31, 77.42, 77.66, 77.72, 77.7, 77.73, 77.96, 78.08, 77.98, 78.05],
    2013: [78.28, 78.63, 78.79, 78.99, 79.21, 79.39, 79.43, 79.5, 79.73, 79.52, 79.35, 79.56],
    2014: [79.95, 80.45, 80.77, 81.14, 81.53, 81.61, 81.73, 81.9, 82.01, 82.14, 82.25, 82.47],
    2015: [83.0, 83.96, 84.45, 84.9, 85.12, 85.21, 85.37, 85.78, 86.39, 86.98, 87.51, 88.05],
    2016: [89.19, 90.33, 91.18, 91.63, 92.1, 92.54, 93.02, 92.73, 92.68, 92.62, 92.73, 93.11],
    2017: [94.07, 95.01, 95.46, 95.91, 96.12, 96.23, 96.18, 96.32, 96.36, 96.37, 96.55, 96.92],
    2018: [97.53, 98.22, 98.45, 98.91, 99.16, 99.31, 99.18, 99.3, 99.47, 99.59, 99.7, 100.0],
    2019: [100.6, 101.18, 101.62, 102.12, 102.44, 102.71, 102.94, 103.03, 103.26, 103.43, 103.54, 103.8],
    2020: [104.24, 104.94, 105.53, 105.7, 105.36, 104.97, 104.97, 104.96, 105.29, 105.23, 105.08, 105.48],
    2021: [105.91, 106.58, 107.12, 107.76, 108.84, 108.78, 109.14, 109.62, 110.04, 110.06, 110.6, 111.41],
    2022: [113.26, 115.11, 116.26, 117.71, 118.7, 119.31, 120.27, 121.5, 122.63, 123.51, 124.46, 126.03],
    2023: [128.27, 130.4, 131.77, 132.8, 133.38, 133.78, 134.45, 135.39, 136.11, 136.45, 137.09, 137.72],
    2024: [138.98, 140.49, 141.48, 142.32, 142.92, 143.38, 143.67, 143.67, 144.02, 143.83, 144.22, 144.88],
    2025: [146.24, 147.9, 148.68, 149.66, 150.14, 150.3, 150.71, 150.99, 151.48, 151.76, 151.87, 152.27],
    2026: [154.07, 155.73, 156.94, 158.17, 158.91, 159.53, 159.79, 160.42, 161.0],
}

# TRM promedio anual (promedio simple de los registros diarios publicados).
# https://www.datos.gov.co/resource/32sa-8pi3.json (Superintendencia Financiera)
TRM = {2004: 2626.28, 2005: 2320.90, 2006: 2358.46, 2007: 2077.57, 2008: 1964.54, 2009: 2156.26,
       2010: 1897.56, 2011: 1846.78, 2012: 1796.66, 2013: 1869.35, 2014: 2001.34, 2015: 2748.26,
       2016: 3050.97, 2017: 2950.54, 2018: 2956.05, 2019: 3282.26, 2020: 3696.31, 2021: 3749.12,
       2022: 4251.47, 2023: 4323.97, 2024: 4075.04, 2025: 4052.27, 2026: 3474.87}

# IPC de Estados Unidos (CPI-U, promedio anual). FRED, serie CPIAUCNS.
# https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS&fq=Annual&fam=avg
US_CPI = {2004: 188.883, 2005: 195.292, 2006: 201.592, 2007: 207.342, 2008: 215.303, 2009: 214.537,
          2010: 218.056, 2011: 224.939, 2012: 229.594, 2013: 232.957, 2014: 236.736, 2015: 237.017,
          2016: 240.007, 2017: 245.120, 2018: 251.107, 2019: 255.657, 2020: 258.811, 2021: 270.970,
          2022: 292.655, 2023: 304.702, 2024: 313.689, 2025: 321.943}

# IRENA, Renewable Power Generation Costs in 2024 (jul-2025), figura 3.1/3.2: costo total
# instalado promedio ponderado mundial de la solar a gran escala, USD de 2024 por kW.
# https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2025/Jul/IRENA_TEC_RPGC_in_2024_2025.pdf
IRENA_PV = {2010: 5283, 2011: 4659, 2012: 3537, 2013: 3107, 2014: 2849, 2015: 2140, 2016: 1958,
            2017: 1683, 2018: 1438, 2019: 1188, 2020: 1044, 2021: 973, 2022: 930, 2023: 776, 2024: 691}
# 2008 no está en IRENA. Dos extrapolaciones:
#  a) precio instalado de EE. UU. (LBNL Tracking the Sun vía Our World in Data):
#     2008 = 8,818 y 2010 = 7,089 USD/W -> razón 1,244.
#     https://ourworldindata.org/grapher/solar-pv-system-costs
#  b) precio del módulo (IRENA/Nemet/Farmer-Lafond vía OWID, USD de 2025 por W):
#     2008 = 4,749 y 2010 = 2,512; se suma la diferencia al costo de 2010.
#     https://ourworldindata.org/grapher/solar-pv-prices
LBNL_US_2008, LBNL_US_2010 = 8.817956, 7.089459
MODULO_2008, MODULO_2010 = 4.7491965, 2.5118067  # USD 2025/W
# IRENA (misma publicación, figura 9.2): costo total instalado de proyectos de baterías,
# USD de 2024 por kWh útil: 2.571 en 2010 y 192 en 2024 (BNEF; Schmidt y Staffell).
IRENA_BESS_2010, IRENA_BESS_2024 = 2571, 192

# Tarifa EPM "Oficial y exentos de contribución", nivel de tensión 1, activos propiedad de EPM,
# mercado regulado de Antioquia, COP/kWh (publicaciones mensuales de EPM).
# 2009-2022: https://www.epm.com.co/clientesyusuarios/energia/tarifas-energia/tarifas-anos-anteriores-energia
# 2023-2026: https://www.epm.com.co/clientesyusuarios/energia/tarifas-energia/
# 2016-2021 verificado también con https://www.datos.gov.co/resource/sfcd-b3ey.json
TARIFA_OFICIAL_EPM = {
    2009: {1: 289.01, 3: 301.66, 4: 301.8, 5: 302.62, 6: 295.78, 7: 294.42, 8: 294.42, 9: 294.55, 10: 294.55, 11: 298.23, 12: 298.65},
    2010: {1: 303.13, 2: 307.68, 3: 312.3, 4: 318.54, 5: 321.73, 6: 323.34, 7: 324.95, 8: 324.95, 9: 324.95, 10: 324.95, 11: 324.95, 12: 329.83},
    2011: {1: 334.49, 2: 337.54, 3: 337.54, 4: 337.54, 5: 339.91, 6: 346.71, 7: 348.79, 8: 349.83, 10: 352.28, 11: 359.33, 12: 360.25},
    2012: {1: 360.25, 2: 370.17, 3: 357.65, 4: 358.65, 5: 363.52, 6: 366.24, 7: 372.87, 8: 370.11, 9: 368.6, 10: 368.62, 11: 365.5, 12: 367.0},
    2013: {1: 367.41, 2: 367.99, 3: 367.29, 4: 375.45, 5: 379.54, 6: 370.81, 7: 371.11, 8: 381.52, 9: 383.44, 10: 378.26, 11: 376.81, 12: 364.08},
    2014: {1: 379.07, 2: 375.57, 3: 387.38, 4: 382.95, 5: 390.61, 6: 398.42, 7: 406.39, 8: 414.52, 9: 407.59, 10: 395.56, 11: 392.87, 12: 384.96},
    2015: {1: 395.17, 2: 399.24, 3: 407.38, 4: 417.19, 5: 405.03, 6: 409.02, 7: 409.5, 8: 412.73, 9: 417.29, 10: 430.41, 11: 436.86, 12: 435.94},
    2016: {1: 442.48, 2: 449.12, 3: 455.86, 4: 462.7, 5: 469.64, 6: 476.68, 7: 483.83, 8: 491.09, 9: 498.45, 10: 482.5, 11: 461.85, 12: 471.84},
    2017: {1: 447.16, 2: 455.88, 3: 477.51, 4: 463.38, 5: 453.75, 6: 447.03, 7: 468.82, 8: 473.08, 9: 462.25, 10: 469.42, 11: 469.42, 12: 470.6},
    2018: {1: 467.58, 2: 474.47, 3: 492.59, 4: 486.38, 5: 473.02, 6: 486.95, 7: 496.33, 8: 495.22, 9: 496.96, 10: 500.31, 11: 509.8, 12: 498.36},
    2019: {1: 501.74, 2: 512.43, 3: 534.86, 4: 523.29, 5: 506.3, 6: 511.58, 7: 513.35, 8: 525.5, 9: 520.72, 10: 528.57, 11: 539.21, 12: 519.27},
    2020: {1: 520.2, 2: 567.36, 3: 567.36, 4: 567.36, 5: 567.36, 6: 567.36, 7: 567.36, 8: 567.36, 9: 567.36, 10: 567.36, 11: 567.36, 12: 570.2},
    2021: {1: 573.05, 2: 576.49, 3: 579.94, 4: 583.42, 5: 586.92, 6: 590.45, 7: 593.99, 8: 597.55, 9: 602.33, 10: 607.15, 11: 612.01, 12: 616.9},
    2022: {1: 621.84, 2: 626.81, 3: 658.16, 4: 664.74, 5: 678.03, 6: 705.15, 7: 733.36, 8: 762.69, 9: 767.27, 10: 750.54, 11: 750.54, 12: 756.32},
    2023: {1: 765.85, 2: 779.48, 3: 792.42, 4: 800.74, 5: 806.99, 6: 802.15, 7: 797.33, 8: 792.55, 9: 798.1, 10: 842.79, 11: 884.93, 12: 888.47},
    2024: {1: 898.85, 2: 870.45, 3: 884.21, 4: 899.5, 5: 943.74, 6: 842.86, 7: 848.54, 8: 854.74, 9: 842.28, 10: 876.14, 11: 906.16, 12: 891.09},
    2025: {1: 913.53, 2: 919.84, 3: 923.2, 4: 890.31, 5: 836.5, 6: 846.43, 7: 888.86, 8: 901.37, 10: 885.65, 11: 861.88, 12: 859.19},
    2026: {1: 859.19, 2: 801.24, 3: 864.69, 4: 864.06, 5: 876.97, 6: 902.28, 7: 921.38, 8: 960.34, 9: 958.38, 10: 991.29},
}
RAZON_ESPD = 1.10  # ESPD (acueducto) / oficial en las mismas hojas: 317,91/289,01 (ene-2009) y 1.090,41/991,29 (oct-2026)
RAZON_EXCEDENTES = 877 / 991.29  # (tarifa - Cv) / tarifa, crédito AGPE <=100 kW (data/microrred.json)

# Tarifa mínima de la tasa retributiva (MinAmbiente), $/kg. Se actualiza cada año con el IPC.
# https://www.minambiente.gov.co/wp-content/uploads/2023/01/TASA-RETRIBUTIVA-POR-VERTIMIENTOS-PUNTUALES-AL-AGUA.pdf
TM_RETRIBUTIVA = {2010: (106.05, 45.35), 2011: (109.41, 46.79), 2012: (113.49, 48.53), 2013: (116.26, 49.72),
                  2014: (118.52, 50.68), 2015: (122.86, 52.54), 2016: (131.17, 56.09), 2017: (138.72, 59.32),
                  2018: (144.39, 61.75), 2019: (148.99, 63.71), 2020: (154.65, 66.13), 2021: (157.14, 67.20),
                  2022: (165.97, 70.97), 2023: (187.75, 80.28), 2024: (205.17, 87.73)}

# Producción fiscalizada de crudo (ANH), barriles por mes, promedio del año.
# https://www.datos.gov.co/resource/fdvb-hsrf.json
CRUDO_BBL_MES = {
    "05893": {2014: 669976, 2015: 665523, 2016: 543414, 2017: 483412, 2018: 421600, 2019: 400891, 2020: 399984,
              2021: 375191, 2022: 385270, 2023: 379190, 2024: 354259},
    "13160": {2014: 289987, 2015: 344764, 2016: 343629, 2017: 288681, 2018: 293520, 2019: 426881, 2020: 474824,
              2021: 458138, 2022: 407975, 2023: 362254, 2024: 334815},
}

# Compras de ambulancias en SECOP II (una unidad por contrato), valor del contrato en pesos.
# https://www.datos.gov.co/resource/jbjy-vk9h.json (consulta: objeto con "AMBULANCIA", 2025-2026)
SECOP_TAB = [  # (fecha, entidad o municipio, valor)
    ("2026-10-09", "ESE Guamal (Magdalena)", 320873950), ("2026-10-08", "ESE San Pedro de Iguaque (Boyacá)", 271204999),
    ("2026-10-08", "Hospital San Rafael de Risaralda (Caldas)", 297500000), ("2026-10-01", "Hospital Valle de Tenza, sede Almeida (Boyacá)", 276000000),
    ("2026-09-30", "Hospital de González (Cesar)", 231457472), ("2026-09-16", "Hospital San Luis de Gaceno (Boyacá), 4x4", 425000000),
    ("2026-09-02", "Municipio de Pisba (Boyacá)", 416800000), ("2026-08-20", "ESE de Segovia (Antioquia), 4x4", 380000000),
    ("2026-08-19", "ESE Guaduas (Cundinamarca)", 417000000), ("2026-08-13", "ESE Ramiriquí (Boyacá), 4x4", 367543740),
    ("2026-07-27", "ESE Lebrija (Santander)", 324000000), ("2026-07-27", "ESE Putumayo", 424000000),
    ("2026-07-01", "ESE Funza (Cundinamarca)", 392000000), ("2026-06-22", "ESE Florián (Santander)", 297800000),
    ("2026-06-05", "ESE Monguí (Boyacá)", 352000000), ("2026-04-30", "ESE Susacón (Boyacá), 4x4", 323705000),
    ("2026-04-29", "Hospital de Aguazul (Casanare)", 378000000), ("2026-04-23", "ESE El Carmen de Bolívar", 304950000),
    ("2026-04-14", "Hospital Kennedy, Riofrío (Valle)", 389900000), ("2026-04-13", "ESE La Gloria (Cesar)", 267000000),
    ("2026-04-10", "ESE Hatillo de Loba (Bolívar)", 301000000), ("2026-04-08", "Municipio de Victoria (Caldas)", 280000000),
    ("2026-04-01", "Hospital San Vicente de Paúl", 325526172), ("2026-03-30", "Hospital de La Jagua de Ibirico (Cesar)", 329038538),
    ("2026-03-27", "ESE Achí (Bolívar)", 372713550), ("2026-03-26", "Clínica Girón ESE (Santander)", 247379999),
    ("2026-03-26", "Hospital de Guamal (Meta), 4x4", 295481000), ("2026-03-13", "Hospital de Miraflores (Boyacá)", 315190000),
    ("2026-03-10", "Hospital de Roncesvalles (Tolima)", 335000000), ("2026-03-06", "ESE Sáchica (Boyacá), 4x4", 397000000),
    ("2026-03-03", "Hospital de La Victoria (Valle)", 370990000), ("2026-02-27", "Hospital de Cáqueza (Cundinamarca)", 350000000),
    ("2026-02-18", "ESE San Eduardo (Boyacá)", 260000000), ("2026-02-06", "Hospital de Yolombó (Antioquia)", 347294117),
    ("2026-02-04", "Hospital Santo Domingo Savio (Santander)", 337500000), ("2026-01-30", "ESE Los Santos (Santander)", 272000000),
    ("2026-01-05", "ESE La Uvita (Boyacá)", 269000000), ("2025-12-31", "Hospital de Filadelfia (Caldas)", 297500000),
    ("2025-12-30", "Hospital Tomás Uribe (Valle)", 325000000), ("2025-12-29", "ESE Arauca", 284243696),
    ("2025-12-23", "Hospital San Vicente de Paúl (Caldas)", 324850000), ("2025-12-22", "Hospital Sagrado Corazón (Quindío)", 331900000),
]
SECOP_TAM = [
    ("2026-09-29", "Hospital de Aguazul (Casanare)", 480000000), ("2026-09-03", "Hospital Reina Sofía, Lérida (Tolima)", 434000000),
    ("2026-08-27", "Hospital de Miraflores (Boyacá)", 400000000), ("2026-06-05", "ESE Nuestra Señora del Carmen (Cundinamarca), 4x4", 449800000),
    ("2026-04-06", "Hospital San Rafael, El Espinal (Tolima)", 451500000),
]

SMMLV_2026 = 1750905  # Decreto 1469 de 2025, sostenido por el Decreto 0159 de 2026

COMPARABLES = {
    "05579": "Puerto Berrío", "05585": "Puerto Nare", "68081": "Barrancabermeja", "13160": "Cantagallo",
    "13670": "San Pablo", "05604": "Remedios", "05736": "Segovia",
}
YONDO = "05893"
PERIODOS = [("2004-2007", 2004, 2007), ("2008-2011", 2008, 2011), ("2012-2015", 2012, 2015),
            ("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2027", 2024, 2027)]
INICIO_GOBIERNO = [2008, 2012, 2016, 2020, 2024]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def ipc_prom(anio):
    v = IPC_MENSUAL[anio]
    return sum(v) / len(v)


IPC_BASE = ipc_prom(2026)  # ene-sep 2026


def a_2026(valor, anio):
    """Lleva pesos corrientes de un año a pesos de 2026 con el IPC promedio del año."""
    return valor * IPC_BASE / ipc_prom(anio)


def r(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def es(x, d=0):
    """Número con formato de Colombia: punto para miles y coma para decimales."""
    t = f"{x:,.{d}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


def mediana(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def percentil(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def tarifa_oficial(anio):
    """Promedio anual de la tarifa oficial NT1 de EPM (COP corrientes/kWh)."""
    if anio in TARIFA_OFICIAL_EPM:
        m = TARIFA_OFICIAL_EPM[anio]
        return sum(m.values()) / len(m)
    if anio == 2008:  # sin publicación disponible: tarifa real constante respecto a 2009
        return tarifa_oficial(2009) * ipc_prom(2008) / ipc_prom(2009)
    raise KeyError(anio)


def leer_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 2. Costos unitarios (pesos de 2026)
# ---------------------------------------------------------------------------
def costos_unitarios():
    def idx(valor, anio):
        return a_2026(valor, anio)

    tab = statistics.median(v for _, _, v in SECOP_TAB)
    tab_min, tab_max = min(v for _, _, v in SECOP_TAB), max(v for _, _, v in SECOP_TAB)
    tam = statistics.median(v for _, _, v in SECOP_TAM)
    tam_min, tam_max = min(v for _, _, v in SECOP_TAM), max(v for _, _, v in SECOP_TAM)

    ffie_cali = 12_600e6 / 14  # 2025, todo incluido (comedor, cocina, baterías)
    ph_ant = 65_000e6 / 89  # 2024
    ph_invias = 636e6  # 2019
    ph_narino = 4_319e6 / 2  # 2026
    pav_sju = 1_967_782_592 / 1.204  # 2022
    pav_pb = 1_453_822_264 / 0.340  # MGA 2020, aprobado 2023
    vis_r_local = 6_801e6 / 100  # 2022
    vis_u_local = 9_351e6 / 150  # 2022
    ptar_tenjo = 9_300e6 / 12_000  # 2021
    ptar_corozal = 67_000e6 / 64_214  # 2024
    ptar_riofrio = 6_000e6 / 3_150  # 2022, incluye optimización de alcantarillado
    turbo_conex = 1_115e6 / 170  # 2016-2019 (se indexa desde 2018), incluye redes
    led_bog = 58_000e6 / 80_000  # 2019, solo compra
    tab_yondo_2014 = 141_408_000
    cdi_laceja = 1_947e6 + 345e6  # 2019, 320 niños
    cdi_marinilla = 6_000e6 + 300e6  # 2022, 300 niños
    cdi_cartagena = 7_500e6 + 1_000e6  # 2019, 210 niños

    ptar_pc = sorted([idx(ptar_tenjo, 2021), idx(ptar_corozal, 2024), idx(ptar_riofrio, 2022)])
    ptar_pc_c = statistics.median(ptar_pc)

    items = [
        {
            "id": "aula_dotada", "nombre": "Aula escolar nueva y dotada", "unidad": "aula",
            "costo_cop_2026": 600e6, "min": 400e6, "max": idx(ffie_cali, 2025),
            "fuente": "MEN/FFIE, I.E. Bienestar Social (Cali), nov-2025: $12.600 M por 14 aulas con comedor, cocina y 22 baterías sanitarias "
                      "https://www.mineducacion.gov.co/1780/w3-article-426696.html ; costo por m² de colegio 7,6 M (Medellín) y 8,2 M (promedio nacional) "
                      "según prensa: https://abceconomia.co/2025/11/04/medellin-invierte-26-mil-millones-para-construir-megacolegio/",
            "nota": "Estimado. Máximo = caso FFIE todo incluido (12.600/14, indexado). Central: un aula con su parte de circulaciones y baterías "
                    "ocupa unos 80-90 m² brutos; a 5-7,6 M/m² más 40 M de dotación da 400-700 M. El FFIE tiene hallazgos fiscales por sobrecostos por m²; "
                    "se pide cotizar con el MEN antes de usar.",
            "certeza": "estimado",
        },
        {
            "id": "km_placa_huella", "nombre": "Kilómetro de placa huella en vía terciaria", "unidad": "km",
            "costo_cop_2026": 1_000e6, "min": idx(ph_ant, 2024), "max": ph_narino,
            "fuente": "Gobernación de Antioquia y Comité de Cafeteros (2024): más de $65.000 M para 1 km en cada uno de 89 municipios "
                      "https://www.elcolombiano.com/antioquia/contruccion-de-placa-huella-en-89-municipios-de-antioquia-LH24237840 ; "
                      "INVÍAS, programa Colombia Rural (2019): $636.000 por metro de placa huella https://www.centrodemocratico.com/wp-content/uploads/2019/12/INVIAS.pdf ; "
                      "Gobernación de Nariño (jul-2026): 2 km por $4.319 M https://narino.gov.co/wp-content/uploads/2026/07/Boletin-de-Prensa-N0264-Corredor-rural-de-San-Pablo-mejora-su-transitabilidad-5-07-2026.pdf",
            "nota": f"Estimado. Antioquia 2024 indexado = {es(idx(ph_ant, 2024)/1e6)} M/km; INVÍAS 2019 indexado = {es(idx(ph_invias, 2019)/1e6)} M/km "
                    "(solo placa huella); Nariño 2026 con obras de drenaje = 2.160 M/km. Central redondeado a 1.000 M/km. "
                    "En Yondó, los suelos blandos y las zonas inundables empujan hacia el máximo.",
            "certeza": "estimado",
        },
        {
            "id": "km_pavimento_urbano", "nombre": "Kilómetro de vía urbana en pavimento rígido", "unidad": "km",
            "costo_cop_2026": (idx(pav_sju, 2022) + idx(pav_pb, 2023)) / 2, "min": idx(pav_sju, 2022), "max": idx(pav_pb, 2023),
            "fuente": "Concepto de viabilidad, San Juan de Urabá (feb-2022): 1.204 m por $1.967,8 M "
                      "https://antioquia.gov.co/images/PDF2/Planeacion/OCAD-SecretariaPlaneacion/2022/Aprobacion-de-proyectos/Departamental/Documentos%20aprobaci%C3%B3n%20-%202020056590012/Concepto%20tecnico%20viabilidad%20-%202020056590012.pdf ; "
                      "MGA Puerto Berrío, BPIN 2020055790087 (aprobado 2023): 0,340 km por $1.453,8 M con demolición "
                      "https://antioquia.gov.co/images/PDF2/Planeacion/OCAD-SecretariaPlaneacion/2023/Aprobacion-de-proyectos/Departamental/Documentos%20aprobaci%C3%B3n%20-%202020055790087%20-%20Pavimento%20rigido%20Puerto%20Berrio/MGA%20-%202020055790087.pdf",
            "nota": "Estimado: promedio de dos proyectos de la región indexados con IPC. No incluye redes de acueducto y alcantarillado bajo la vía.",
            "certeza": "estimado",
        },
        {
            "id": "vis_rural", "nombre": "Vivienda de interés social rural nueva", "unidad": "vivienda",
            "costo_cop_2026": (idx(vis_r_local, 2022) + 90 * SMMLV_2026) / 2, "min": idx(vis_r_local, 2022), "max": 90 * SMMLV_2026,
            "fuente": "Proyecto 2022003050034, 100 viviendas rurales en Yondó por $6.801 M (docs/anexos/A-gobiernos-2004-2027.md); "
                      "Decreto 0585 de 2025: subsidio de vivienda rural en especie hasta 90 SMMLV "
                      "https://sidn.ramajudicial.gov.co/SIDN/NORMATIVA/TEXTOS_COMPLETOS/5_DECRETOS/DECRETOS%202025/DECRETO%200585%20DE%202025.PDF ; "
                      "SMMLV 2026 = $1.750.905 (Decreto 1469 de 2025)",
            "nota": "Estimado. Mínimo = valor contratado en Yondó en 2022 indexado (ese proyecto lleva 9 % de avance físico con 88 % pagado, así que "
                    "no prueba que alcance). Máximo = tope del subsidio en especie (90 SMMLV). Central = punto medio.",
            "certeza": "estimado",
        },
        {
            "id": "vis_urbana", "nombre": "Vivienda de interés social urbana", "unidad": "vivienda",
            "costo_cop_2026": 90 * SMMLV_2026, "min": idx(vis_u_local, 2022), "max": 135 * SMMLV_2026,
            "fuente": "Ley 2294 de 2023, art. 293: tope VIS de 135 SMMLV; vivienda de interés prioritario de 90 SMMLV (Ley 1955 de 2019, art. 85); "
                      "proyecto 2022003050005, 150 viviendas en Puerto Nare, Yolombó y Yondó por $9.351 M (docs/anexos/A-gobiernos-2004-2027.md)",
            "nota": "Estimado. Central = 90 SMMLV (valor de una vivienda prioritaria). Máximo = tope VIS (135 SMMLV). Mínimo = valor por vivienda "
                    "del proyecto regional de 2022 indexado (17 % de avance físico, 89 % de recursos girados).",
            "certeza": "estimado",
        },
        {
            "id": "ptar_12000_hab", "nombre": "Planta de tratamiento de aguas residuales (PTAR) para unos 12.000 habitantes", "unidad": "planta",
            "costo_cop_2026": ptar_pc_c * 12_000, "min": ptar_pc[0] * 12_000, "max": ptar_pc[-1] * 12_000,
            "fuente": "PTAR de Tenjo (El Espectador, 28-sep-2021): más de $9.300 M para más de 12.000 personas, 40 L/s "
                      "https://www.elespectador.com/bogota/tenjo-estrena-una-de-las-ptar-mas-modernas-de-cundinamarca/ ; "
                      "PTAR de Corozal (MinVivienda, 4-mar-2024): $67.000 M para 64.214 habitantes "
                      "https://minvivienda.gov.co/sala-de-prensa/minvivienda-llega-con-buenas-noticias-en-materia-de-agua-para-el-departamento-de-sucre ; "
                      "PTAR de Salónica, Riofrío (MinVivienda, 13-abr-2022): más de $6.000 M para 3.150 habitantes, con obras de alcantarillado "
                      "https://minvivienda.gov.co/sala-de-prensa/gobierno-nacional-entrego-ptar-en-riofrio-valle-del-cauca-con-inversion-de-mas-de-6000-millones",
            "nota": "Estimado: costo por habitante (mediana de los tres casos indexados) × 12.000. No incluye colectores e interceptores; en Yondó "
                    "el proyecto de canalización de colectores de las estaciones de bombeo figura en formulación por $67.640 M (BPIN 20201301010649). "
                    "El costo real sale del Plan Maestro (hoy inactivo).",
            "certeza": "estimado",
        },
        {
            "id": "ptar_por_habitante", "nombre": "PTAR: costo por habitante servido", "unidad": "habitante",
            "costo_cop_2026": ptar_pc_c, "min": ptar_pc[0], "max": ptar_pc[-1],
            "fuente": "Mismos tres casos de la fila anterior (Tenjo 2021, Corozal 2024, Salónica-Riofrío 2022), indexados con IPC.",
            "nota": f"Tenjo = {es(idx(ptar_tenjo, 2021))}; Corozal = {es(idx(ptar_corozal, 2024))}; Salónica = {es(idx(ptar_riofrio, 2022))} pesos de 2026 por habitante. "
                    "Las plantas pequeñas cuestan más por habitante.",
            "certeza": "estimado",
        },
        {
            "id": "conexion_alcantarillado", "nombre": "Conexión domiciliaria de alcantarillado (acometida y caja de inspección)", "unidad": "vivienda",
            "costo_cop_2026": 2.5e6, "min": 1.0e6, "max": idx(turbo_conex, 2018),
            "fuente": "Gobernación de Antioquia, barrio Gaitán de Turbo (plan 2016-2019): $1.115 M para 170 conexiones nuevas de alcantarillado con redes "
                      "https://antioquia.gov.co/noticias-gerencia-servicios-publicos/barrio-gaitán-de-turbo-tendrá-nuevas-redes-de-alcantarillado-por-1-115-millones ; "
                      "AMB Bucaramanga, costo directo de conexión de acueducto 2025 ($607.219 hasta 1\") "
                      "https://www.amb.com.co/amb/wp-content/Documentos/Documentos-interes-normativos/ActoGerenciaNo007-2025.pdf",
            "nota": "Supuesto con referencia. No se halló un costo publicado de la acometida de alcantarillado sola. Central: tubería de 6\" desde la casa "
                    "hasta el colector más caja de inspección, unas 4 veces una acometida de acueducto. Máximo = caso de Turbo, que incluye redes locales.",
            "certeza": "supuesto",
        },
        {
            "id": "kwp_solar_cubierta", "nombre": "kWp solar instalado en cubierta (sede pública, ≤100 kW)", "unidad": "kWp",
            "costo_cop_2026": 3.5e6, "min": 2.8e6, "max": 4.0e6,
            "fuente": "data/presupuesto_microrred.json (rango de mercado 2026 para solar comercial, docs/05 y docs/anexos/D-energia-mintic.md)",
            "nota": "Supuesto de prefactibilidad (−30 % / +50 %). Marquesina: 5,0 M/kWp; montaje en piso: 3,2 M/kWp.",
            "certeza": "supuesto",
        },
        {
            "id": "kwh_bateria", "nombre": "kWh de baterías LFP instaladas con inversor híbrido", "unidad": "kWh",
            "costo_cop_2026": 1.4e6, "min": 1.0e6, "max": 2.2e6,
            "fuente": "data/presupuesto_microrred.json (BNEF 2025 y escala pequeña en Yondó, docs/anexos/D-energia-mintic.md)",
            "nota": "Supuesto de prefactibilidad. IRENA da USD 192/kWh para proyectos grandes en 2024; la escala pequeña y la logística lo encarecen.",
            "certeza": "supuesto",
        },
        {
            "id": "luminaria_led", "nombre": "Luminaria LED de alumbrado público instalada", "unidad": "luminaria",
            "costo_cop_2026": 2.5e6, "min": idx(led_bog, 2019), "max": 3.0e6,
            "fuente": "docs/07-portafolio-presupuesto.md (proyecto 7: $2.500 M para unas 1.000 luminarias); Bogotá 2019: más de $58.000 M por 80.000 luminarias LED "
                      "https://bogota.gov.co/asi-vamos/alcaldia-instala-80000-luminarias-led-en-bogota",
            "nota": "Estimado. Mínimo = compra a gran escala en Bogotá indexada (solo equipo). Máximo supuesto con brazo, cableado y dictamen RETILAP.",
            "certeza": "estimado",
        },
        {
            "id": "ambulancia_basica_tab", "nombre": "Ambulancia de transporte asistencial básico (TAB) dotada", "unidad": "vehículo",
            "costo_cop_2026": tab, "min": tab_min, "max": tab_max,
            "fuente": f"SECOP II, {len(SECOP_TAB)} contratos de compra de una TAB (dic-2025 a oct-2026) https://www.datos.gov.co/resource/jbjy-vk9h.json",
            "nota": f"Hecho (mediana de contratos firmados). Referencias locales: TAB de la E.S.E. de Yondó en 2014 = $141,4 M (≈{es(idx(tab_yondo_2014, 2014)/1e6)} M de 2026); "
                    "Antioquia entregó 14 TAB 4x4 en 2021 por $8.359,4 M (docs/anexos/C-hospital-2028.md).",
            "certeza": "hecho",
        },
        {
            "id": "ambulancia_medicalizada_tam", "nombre": "Ambulancia de transporte asistencial medicalizado (TAM) dotada", "unidad": "vehículo",
            "costo_cop_2026": tam, "min": tam_min, "max": max(tam_max, 650e6),
            "fuente": f"SECOP II, {len(SECOP_TAM)} contratos de compra de una TAM (abr-oct 2026) https://www.datos.gov.co/resource/jbjy-vk9h.json ; "
                      "docs/06-hospital-2028-financiacion.md (supuesto de $650 M para Yondó)",
            "nota": "Hecho (mediana de contratos). El máximo toma el supuesto del repositorio para Yondó (650 M), que incluye equipos de cuidado crítico.",
            "certeza": "hecho",
        },
        {
            "id": "puesto_salud_rural", "nombre": "Puesto de salud rural nuevo y dotado", "unidad": "puesto",
            "costo_cop_2026": 1_500e6, "min": 1_200e6, "max": 1_900e6,
            "fuente": "El Heraldo (15-jun-2026): puesto de salud de El Rincón, San Diego (Cesar), más de $1.900 M "
                      "https://www.elheraldo.co/cesar/2026/06/15/construiran-puesto-de-salud-en-el-rincon-zona-rural-de-san-diego-cesar/ ; "
                      "docs/06-hospital-2028-financiacion.md (puesto de San Miguel del Tigre con solar aislada: $1.200 M, supuesto)",
            "nota": "Estimado: entre el supuesto del repositorio y el caso de Cesar.",
            "certeza": "estimado",
        },
        {
            "id": "cdi", "nombre": "Centro de Desarrollo Infantil (CDI) nuevo y dotado, 200-300 niños", "unidad": "CDI",
            "costo_cop_2026": idx(cdi_marinilla, 2022), "min": idx(cdi_laceja, 2019), "max": idx(cdi_cartagena, 2019),
            "fuente": "ICBF: CDI de Marinilla (4-mar-2022), más de $6.000 M de obra y $300 M de dotación, 300 niños https://www.icbf.gov.co/node/173646 ; "
                      "CDI de La Ceja (2019), $1.947 M de obra y $345 M de dotación, 320 niños "
                      "https://antioquia.gov.co/index.php/noticias-gerencia-infancia-adolescencia-y-juventud/nueva-ciudadela-integral-para-la-primera-infancia-en-el-municipio-de-la-ceja ; "
                      "CDI Flor del Campo, Cartagena (2-nov-2019), $7.500 M de obra y $1.000 M de dotación, 210 niños "
                      "https://www.icbf.gov.co/noticias/icbf-pone-en-marcha-nuevo-centro-de-desarrollo-infantil-en-cartagena",
            "nota": "Estimado: central = Marinilla indexado (mediana de los tres casos). La operación anual va aparte (Marinilla: $1.177 M al año).",
            "certeza": "estimado",
        },
        {
            "id": "beca_universitaria_anual", "nombre": "Beca universitaria anual (sostenimiento y matrícula)", "unidad": "estudiante-año",
            "costo_cop_2026": 10 * SMMLV_2026, "min": 5 * SMMLV_2026, "max": 20 * SMMLV_2026,
            "fuente": "SMMLV 2026 (Decreto 1469 de 2025); subsidio de sostenimiento ICETEX 2026 de $1.306.119 por semestre "
                      "https://forbes.co/economia-y-finanzas/icetex-girara-apoyos-y-condonaciones-por-259-933-millones-para-estudiantes-con-credito-educativo",
            "nota": "Supuesto. Central: 1 SMMLV al mes por 10 meses para vivir en Barrancabermeja o Medellín, con matrícula cubierta por la gratuidad "
                    "en universidad pública. Mínimo: medio SMMLV al mes. Máximo: universidad privada (≈5 SMMLV por semestre) más sostenimiento.",
            "certeza": "supuesto",
        },
        {
            "id": "km_red_acueducto", "nombre": "Kilómetro de red urbana de acueducto (PVC 3-6\", con rotura y reposición de vía y acometidas)", "unidad": "km",
            "costo_cop_2026": 550e6, "min": idx(51_768_094 / 0.8, 2023), "max": 900e6,
            "fuente": "SECOP II: instalación de 800 m de tubería de 6\" en acueducto veredal de San Luis (Tolima), $51,8 M (mar-2023) "
                      "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.4121809 ; "
                      "AMB 2025, conexión de acueducto $607.219 (ver fila de alcantarillado)",
            "nota": "Supuesto armado por componentes: tubería y accesorios (≈60.000 $/m), excavación y relleno (≈100.000 $/m), rotura y reposición de "
                    "pavimento (≈200.000 $/m), válvulas e hidrantes (20 %) y unas 25 acometidas por cada 100 m. Mínimo = tubería rural sin pavimento.",
            "certeza": "supuesto",
        },
    ]
    for it in items:
        for k in ("costo_cop_2026", "min", "max"):
            it[k] = r(it[k])
        it["fecha_precio"] = "2026 (referencias de otros años indexadas con IPC DANE promedio anual)"
    return items


# ---------------------------------------------------------------------------
# 3. Contrafactual solar
# ---------------------------------------------------------------------------
STEPS, DT = 96, 0.25


def solar_shape(h):
    return 0.0 if (h <= 6 or h >= 18) else math.sin(math.pi * (h - 6) / 12) ** 1.3


SHAPE_INT = sum(solar_shape(i * DT + DT / 2) * DT for i in range(STEPS))


def simular_nodo(nodo, perfil, kwp, rend, bess, eff_rt, soc_max, soc_res):
    """Día típico por sede (frontera propia). Devuelve kWh/día: pv, ahorro (demanda - compra), exportado."""
    suma = sum(perfil)
    dem_dia = nodo["kwh_mes"] / 30
    kwh, kw = (bess["kwh"], bess["kw"]) if bess else (0.0, 0.0)
    eff = math.sqrt(eff_rt)

    def correr(soc0):
        soc = soc0
        pv_t = dem_t = imp_t = exp_t = 0.0
        for i in range(STEPS):
            h = i * DT + DT / 2
            pv = kwp * rend * solar_shape(h) / SHAPE_INT
            dem = dem_dia * perfil[int(h) % 24] / suma
            net = dem - pv
            if net < 0:
                room = max(0.0, (soc_max * kwh - soc) / DT / eff) if kwh else 0.0
                ch = min(-net, kw, room)
                soc += ch * eff * DT
                exp_t += (-net - ch) * DT
            else:
                avail = max(0.0, (soc - soc_res * kwh) / DT) * eff if kwh else 0.0
                dis = min(net, kw, avail)
                soc -= dis / eff * DT
                imp_t += (net - dis) * DT
            pv_t += pv * DT
            dem_t += dem * DT
        return soc, pv_t, dem_t, imp_t, exp_t

    soc = soc_res * kwh
    for _ in range(3):
        soc = correr(soc)[0]
    _, pv_t, dem_t, imp_t, exp_t = correr(soc)
    return {"pv": pv_t, "demanda": dem_t, "ahorro": dem_t - imp_t, "exportado": exp_t}


def contrafactual_solar(micro, presu):
    P = micro["parametros"]
    rend = P["rendimiento_kwh_kwp_dia"]
    nodos = {n["id"]: dict(n) for n in micro["nodos"]}
    # el centro de datos del CCED está dentro del Palacio Municipal: misma frontera
    nodos["alcaldia"]["kwh_mes"] += nodos.pop("ccd")["kwh_mes"]
    bess = {b["nodo"]: b for b in micro["bess"]}

    # costo local de 2026 (ponderado por tipo de montaje del presupuesto)
    gen = [i for i in presu["items"] if i["grupo"] == "Generación"]
    kwp_tot = sum(i["cantidad"] for i in gen)
    pv_local = sum(i["cantidad"] * i["unitario"] for i in gen) / kwp_tot
    bat = [i for i in presu["items"] if i["grupo"] == "Almacenamiento"][0]
    kwh_tot, bess_local = bat["cantidad"], bat["unitario"]

    # perfil de autoconsumo por sede (con y sin baterías)
    sedes = []
    tot = {"solo_solar": {"pv": 0, "ahorro_of": 0, "ahorro_espd": 0, "exp": 0},
           "solar_baterias": {"pv": 0, "ahorro_of": 0, "ahorro_espd": 0, "exp": 0}}
    for nid, n in nodos.items():
        if not n.get("pv_kwp"):
            continue
        perfil = micro["perfiles"][n["perfil"]]
        a = simular_nodo(n, perfil, n["pv_kwp"], rend, None, P["eficiencia_ida_vuelta_bess"], P["soc_max"], P["soc_reserva"])
        b = simular_nodo(n, perfil, n["pv_kwp"], rend, bess.get(nid), P["eficiencia_ida_vuelta_bess"], P["soc_max"], P["soc_reserva"])
        espd = "tarifa" in n
        for key, res in (("solo_solar", a), ("solar_baterias", b)):
            t = tot[key]
            t["pv"] += res["pv"] * 365
            t["ahorro_espd" if espd else "ahorro_of"] += res["ahorro"] * 365
            t["exp"] += res["exportado"] * 365
        sedes.append({"sede": n["nombre"], "kwp": n["pv_kwp"], "kwh_bateria": bess.get(nid, {}).get("kwh", 0),
                      "tarifa": "ESPD (oficial × 1,10)" if espd else "oficial",
                      "pv_kwh_anio": r(a["pv"] * 365),
                      "autoconsumo_sin_bateria_pct": r(100 * a["ahorro"] / a["pv"], 1),
                      "autoconsumo_con_bateria_pct": r(100 * b["ahorro"] / b["pv"], 1)})

    def F_pv(anio, irena=None):
        """Cuántas veces más caro era 1 kWp ese año que en 2024, medido en pesos de 2026."""
        if anio > 2024:  # sin dato IRENA: se usa el costo local de 2026 tal cual
            return 1.0
        v = irena if irena is not None else IRENA_PV[anio]
        num = v * US_CPI[anio] / US_CPI[2024] * TRM[anio] * IPC_BASE / ipc_prom(anio)
        den = IRENA_PV[2024] * TRM[2024] * IPC_BASE / ipc_prom(2024)
        return num / den

    lam = math.log(IRENA_BESS_2024 / IRENA_BESS_2010) / 14

    def irena_bess(anio):
        return IRENA_BESS_2010 * math.exp(lam * (anio - 2010))

    def F_bess(anio):
        if anio > 2024:
            return 1.0
        num = irena_bess(anio) * US_CPI[anio] / US_CPI[2024] * TRM[anio] * IPC_BASE / ipc_prom(anio)
        den = IRENA_BESS_2024 * TRM[2024] * IPC_BASE / ipc_prom(2024)
        return num / den

    pv2008 = {"lbnl": IRENA_PV[2010] * LBNL_US_2008 / LBNL_US_2010,
              "modulo": IRENA_PV[2010] + (MODULO_2008 - MODULO_2010) * 1000 * US_CPI[2024] / US_CPI[2025]}
    IRENA_PV[2008] = (pv2008["lbnl"] + pv2008["modulo"]) / 2

    def tarifa_real(anio):
        return a_2026(tarifa_oficial(anio), anio)

    def escenario(t0, kind, pv_unit, bess_unit, om_pct, degr, vida_bess, irena08=None):
        T = tot[kind]
        con_bat = kind == "solar_baterias"
        f_pv = F_pv(t0, irena08) if (t0 == 2008 and irena08) else F_pv(t0)
        capex_pv = pv_unit * kwp_tot * f_pv * 1.10  # +10 % ingeniería e interventoría
        capex_b = bess_unit * kwh_tot * F_bess(t0) * 1.10 if con_bat else 0.0
        om_anual = om_pct * (pv_unit * kwp_tot + (bess_unit * kwh_tot if con_bat else 0))
        flujo, acumulado, pago = [], -(capex_pv + capex_b), None
        ahorro_tot = om_tot = repos_tot = 0.0
        for y in range(t0, 2027):
            frac = 0.5 if y == t0 else 1.0
            edad = (y - t0) + (0.25 if y == t0 else 0.5)
            d = (1 - degr) ** edad
            tar = tarifa_real(y)
            val_exc = tar * RAZON_EXCEDENTES if y >= 2018 else 0.0
            ahorro = frac * d * (T["ahorro_of"] * tar + T["ahorro_espd"] * tar * RAZON_ESPD + T["exp"] * val_exc)
            om = frac * om_anual
            repos = 0.0
            if y == t0 + 12:  # inversores
                repos += 0.10 * pv_unit * kwp_tot * F_pv(y) * 1.10
            if con_bat and y > t0 and (y - t0) % vida_bess == 0:
                repos += bess_unit * kwh_tot * F_bess(y) * 1.10
            neto = ahorro - om - repos
            acumulado += neto
            ahorro_tot += ahorro
            om_tot += om
            repos_tot += repos
            if pago is None and acumulado >= 0:
                pago = y
            flujo.append({"anio": y, "tarifa_oficial_cop_2026_kwh": r(tar, 1), "ahorro": r(ahorro), "om": r(om),
                          "reposiciones": r(repos), "acumulado": r(acumulado)})
        # valor residual: vida que le queda × costo de reponerlo en 2026
        vida_pv = 25
        edad_fin = 2027 - (t0 + 0.5)
        resid_pv = max(0.0, 1 - edad_fin / vida_pv) * pv_unit * kwp_tot
        resid_b = 0.0
        if con_bat:
            ult = t0 + vida_bess * int((2026 - t0) // vida_bess)
            edad_b = 2027 - (ult + (0.5 if ult == t0 else 0))
            resid_b = max(0.0, 1 - edad_b / vida_bess) * bess_unit * kwh_tot
        neto_sin = ahorro_tot - capex_pv - capex_b - om_tot - repos_tot
        return {
            "anio_instalacion": t0,
            "factor_costo_pv_vs_2024": r(f_pv, 2),
            "factor_costo_bateria_vs_2024": r(F_bess(t0), 2) if con_bat else None,
            "inversion_cop_2026": r(capex_pv + capex_b),
            "inversion_pv_cop_2026_por_kwp": r(capex_pv / kwp_tot / 1.10),
            "ahorro_bruto_hasta_2026": r(ahorro_tot),
            "operacion_y_mantenimiento": r(om_tot),
            "reposiciones": r(repos_tot),
            "neto_hasta_2026_sin_valor_residual": r(neto_sin),
            "valor_residual_2026": r(resid_pv + resid_b),
            "neto_hasta_2026_con_valor_residual": r(neto_sin + resid_pv + resid_b),
            "anio_recuperacion": pago,
            "flujo_anual": flujo,
        }

    casos = {"bajo": dict(pv=pv_local * 2.8 / 3.5, b=1.0e6, om=0.01, degr=0.004, vida=15, i08="modulo"),
             "central": dict(pv=pv_local, b=bess_local, om=0.015, degr=0.005, vida=12, i08=None),
             "alto": dict(pv=pv_local * 4.0 / 3.5, b=2.2e6, om=0.02, degr=0.008, vida=10, i08="lbnl")}
    # "bajo" = supuestos favorables a la solar (costos bajos); "alto" = costos altos

    resultados = []
    for t0 in INICIO_GOBIERNO:
        fila = {"gobierno_que_inicia": f"{t0}-{t0 + 3}", "anio_instalacion": t0}
        for kind in ("solo_solar", "solar_baterias"):
            esc = {}
            for nombre, c in casos.items():
                ir08 = pv2008[c["i08"]] if (t0 == 2008 and c["i08"]) else None
                e = escenario(t0, kind, c["pv"], c["b"], c["om"], c["degr"], c["vida"], ir08)
                if nombre != "central":
                    e.pop("flujo_anual")
                esc[nombre] = e
            fila[kind] = {
                "central": esc["central"],
                "rango_neto_sin_residual": [esc["alto"]["neto_hasta_2026_sin_valor_residual"], esc["bajo"]["neto_hasta_2026_sin_valor_residual"]],
                "rango_neto_con_residual": [esc["alto"]["neto_hasta_2026_con_valor_residual"], esc["bajo"]["neto_hasta_2026_con_valor_residual"]],
            }
        resultados.append(fila)

    # costo de esperar hoy: ahorro bruto de un año a la tarifa promedio de 2026
    T = tot["solo_solar"]
    tar26 = tarifa_real(2026)
    ahorro_2026 = T["ahorro_of"] * tar26 + T["ahorro_espd"] * tar26 * RAZON_ESPD + T["exp"] * tar26 * RAZON_EXCEDENTES
    om_2026 = 0.015 * pv_local * kwp_tot

    return {
        "tipo": "contrafactual",
        "pregunta": "Si las 13 sedes públicas del plan (469 kWp solares y 770 kWh de baterías) se hubieran instalado al inicio de cada gobierno, "
                    "con los costos y tarifas de ese año, ¿cuánto se habría ahorrado neto hasta 2026, en pesos de 2026?",
        "metodo": [
            "Producción: 469 kWp × 3,69 kWh/kWp·día (data/microrred.json, Global Solar Atlas con 16 % de pérdidas) con la misma campana solar de web/js/sim.js.",
            "Autoconsumo: día típico de 15 minutos por sede, cada una como frontera propia con sus perfiles de consumo (sin domótica ni bombeo diurno). "
            "El centro de datos se suma al Palacio Municipal. Las baterías cargan con sobrantes hasta 95 % y descargan hasta la reserva de 35 %.",
            "Valor de la energía: tarifa EPM oficial nivel 1 (promedio de cada año; acueducto con tarifa ESPD = oficial × 1,10). "
            "Excedentes: valen cero antes de 2018 (no había regla para acreditarlos; la creó la CREG 030 de 2018) y tarifa − Cv (88,5 % de la tarifa) desde 2018.",
            "Costo de instalar cada año: costo de 2026 en Yondó (data/presupuesto_microrred.json: 3,53 M/kWp ponderado y 1,4 M/kWh) × factor IRENA, "
            "que dice cuántas veces más caro era instalar ese año que en 2024, medido en pesos de 2026 (costo IRENA en USD de 2024 → USD del año con el IPC "
            "de EE. UU. → pesos del año con la TRM → pesos de 2026 con el IPC del DANE). Se suma 10 % de ingeniería e interventoría.",
            "Supuesto clave: la diferencia de precio entre Yondó y el promedio mundial se mantiene constante. Como 2026 se compara con 2024 (último dato "
            "IRENA) y los precios siguieron bajando, los costos históricos quedan algo altos: el cálculo es conservador.",
            "Operación y mantenimiento: 1,5 % al año del costo de 2026. Degradación de paneles: 0,5 % al año. Inversores: se reponen al año 12 "
            "(10 % del costo solar de ese año). Baterías: vida de 12 años y se reponen al precio de ese año.",
            "Primer año: medio año de operación (contratar e instalar toma unos 6 meses). Horizonte: hasta el 31 de diciembre de 2026, sin descuento (pesos constantes).",
            "Valor residual: vida útil que le queda al equipo en 2026 (paneles 25 años, baterías 12) por lo que costaría reponerlo hoy.",
            "Rango: 'alto' = costos altos (4,0 M/kWp, 2,2 M/kWh, O&M 2 %, degradación 0,8 %, baterías de 10 años); 'bajo' = costos bajos "
            "(2,8 M/kWp, 1,0 M/kWh, O&M 1 %, degradación 0,4 %, baterías de 15 años). En 2008 se usan las dos extrapolaciones de IRENA.",
        ],
        "insumos": {
            "kwp": kwp_tot, "kwh_baterias": kwh_tot,
            "costo_pv_2026_cop_kwp_ponderado": r(pv_local), "costo_bateria_2026_cop_kwh": r(bess_local),
            "produccion_anio_1_kwh": r(tot["solo_solar"]["pv"]),
            "autoconsumo_total_sin_baterias_pct": r(100 * (tot["solo_solar"]["ahorro_of"] + tot["solo_solar"]["ahorro_espd"]) / tot["solo_solar"]["pv"], 1),
            "autoconsumo_total_con_baterias_pct": r(100 * (tot["solar_baterias"]["ahorro_of"] + tot["solar_baterias"]["ahorro_espd"]) / tot["solar_baterias"]["pv"], 1),
            "irena_pv_2008_extrapolado_usd2024_kw": {"lbnl": r(pv2008["lbnl"]), "modulo": r(pv2008["modulo"]), "central": r(IRENA_PV[2008])},
            "irena_bateria_interpolada_usd2024_kwh": {str(y): r(irena_bess(y)) for y in (2008, 2012, 2016, 2020, 2024)},
            "factor_costo_pv_vs_2024": {str(y): r(F_pv(y), 2) for y in INICIO_GOBIERNO},
            "factor_costo_bateria_vs_2024": {str(y): r(F_bess(y), 2) for y in INICIO_GOBIERNO},
            "por_sede": sedes,
        },
        "resultados": resultados,
        "costo_de_esperar_desde_2026": {
            "tipo": "estimado",
            "ahorro_bruto_anual_solo_solar_cop_2026": r(ahorro_2026),
            "om_anual_cop_2026": r(om_2026),
            "nota": "Cada año sin la solar del plan, las cuentas oficiales pagan a EPM unos "
                    f"${es(ahorro_2026/1e6)} M más de lo necesario (tarifa promedio de 2026, sin domótica ni bombeo diurno, que el plan suma aparte).",
        },
        "advertencias": [
            "Antes de 2014 (Ley 1715) no había incentivos tributarios ni reglas de conexión para autogeneradores; el contrafactual 2008 es teórico.",
            "En 2008-2012 las baterías de litio para edificios casi no existían en el mercado; el costo de 2008 se extrapola de la tendencia IRENA. "
            "Los resultados con baterías para esos años son ilustrativos.",
            "Las baterías se justifican por resiliencia (hospital, acueducto, fuerza pública); en la factura aportan poco cuando los excedentes se acreditan.",
            "No incluye el beneficio de evitar cortes, el diésel ahorrado ni el CO2 evitado.",
        ],
    }


# ---------------------------------------------------------------------------
# 4. Fondo de ahorro de regalías
# ---------------------------------------------------------------------------
def contrafactual_regalias(fiscal):
    filas, tot = [], {"regalias": 0, "aporte": 0, "aporte_2026": 0, "r0": 0, "r3": 0, "r4": 0}
    for row in fiscal:
        y = int(row["anio"])
        if not 2004 <= y <= 2011:
            continue
        reg = float(row["regalias_giradas_mm_derivado"])
        ap = 0.10 * reg
        ap26 = a_2026(ap, y)
        n = 2026 - y
        v0, v3, v4 = ap26, ap26 * 1.03 ** n, ap26 * 1.04 ** n
        filas.append({"anio": y, "regalias_giradas_mm_corrientes": r(reg, 1), "aporte_10pct_mm_corrientes": r(ap, 1),
                      "factor_ipc_a_2026": r(IPC_BASE / ipc_prom(y), 4), "aporte_mm_2026": r(ap26, 1),
                      "anios_de_rendimiento": n, "valor_2026_r3_mm": r(v3, 1), "valor_2026_r4_mm": r(v4, 1)})
        tot["regalias"] += reg
        tot["aporte"] += ap
        tot["aporte_2026"] += ap26
        tot["r0"] += v0
        tot["r3"] += v3
        tot["r4"] += v4
    return {
        "tipo": "contrafactual",
        "pregunta": "Si 10 % de las regalías directas giradas a Yondó en 2004-2011 se hubiera guardado en un fondo con rendimiento real de 3-4 % "
                    "al año, ¿cuánto valdría en 2026, en pesos de 2026?",
        "metodo": "Aporte al final de cada año = 10 % de las regalías giradas (data/fuentes/serie_fiscal_oec.csv, columna regalias_giradas_mm_derivado: "
                  "regalías per cápita de TerriData × población DANE). Cada aporte se lleva a pesos de 2026 con el IPC promedio del año (DANE) y "
                  "crece al 3 % o al 4 % real por año hasta 2026. Al ser rendimiento real, el resultado ya está en pesos de 2026.",
        "filas": filas,
        "totales": {
            "regalias_2004_2011_mm_corrientes": r(tot["regalias"], 1),
            "regalias_2004_2011_mm_2026": r(sum(a_2026(float(x["regalias_giradas_mm_derivado"]), int(x["anio"])) for x in fiscal if 2004 <= int(x["anio"]) <= 2011), 1),
            "ahorro_10pct_mm_corrientes": r(tot["aporte"], 1),
            "ahorro_10pct_mm_2026_sin_rendimiento": r(tot["r0"], 1),
            "valor_fondo_2026_r3_mm": r(tot["r3"], 1),
            "valor_fondo_2026_r4_mm": r(tot["r4"], 1),
            "rendimiento_real_anual_si_se_gastan_solo_los_rendimientos_mm": [r(tot["r3"] * 0.03, 1), r(tot["r4"] * 0.04, 1)],
        },
        "nota": "El Sistema General de Regalías (Ley 1530 de 2012) creó un Fondo de Ahorro y Estabilización nacional; este contrafactual imagina "
                "un fondo local adicional. Un fondo así habría dado un ingreso permanente: solo con los rendimientos reales (3-4 % del saldo) se "
                "pagaría cada año la cifra de la última fila sin tocar el capital.",
    }


# ---------------------------------------------------------------------------
# 5. Recaudo potencial (TerriData)
# ---------------------------------------------------------------------------
def descargar_terridata(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    rutas = {}
    for cod in [YONDO] + list(COMPARABLES):
        txt = cache / f"TerriData{cod}.txt"
        if not txt.exists():
            z = cache / f"TerriData{cod}.txt.zip"
            if not z.exists():
                url = f"https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData{cod}.txt.zip"
                urllib.request.urlretrieve(url, z)
            with zipfile.ZipFile(z) as zf:
                nombre = [n for n in zf.namelist() if n.endswith(".txt")][0]
                txt.write_bytes(zf.read(nombre))
        rutas[cod] = txt
    return rutas


def num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def leer_terridata(ruta):
    want = {
        "Ingresos per cápita por impuesto predial": "predial_pc",
        "Ingresos per cápita por impuesto a la Industria y al comercio": "ica_pc",
        "Avalúo catastral total": "avaluo_mm",
        "Estado del catastro urbano": "catastro_urbano",
        "Estado del catastro rural": "catastro_rural",
    }
    d = {v: {} for v in want.values()}
    d["pob"] = {}
    nombre = None
    with open(ruta, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\r\n").split("|")
            if len(p) < 13 or not p[9].isdigit():
                continue
            anio = int(p[9])
            nombre = p[3]
            if p[4] == "Descripción general" and p[6] == "Población total":
                d["pob"][anio] = num(p[7])
            elif p[6] in want:
                k = want[p[6]]
                d[k][anio] = p[8].strip() if k.startswith("catastro") else num(p[7])
    d["nombre"] = nombre
    return d


def recaudo_potencial(cache):
    rutas = descargar_terridata(cache)
    td = {cod: leer_terridata(p) for cod, p in rutas.items()}
    anios = range(2004, 2025)

    def val(cod, key, y):
        v = td[cod][key].get(y)
        return v if (v is not None and v > 0) else None  # cero = dato faltante en TerriData

    tabla, por_periodo = [], []
    for imp in ("predial", "ica"):
        key = f"{imp}_pc"
        for y in anios:
            yo = val(YONDO, key, y)
            comps = {COMPARABLES[c]: val(c, key, y) for c in COMPARABLES}
            vals_sin_barranca = [v for n, v in comps.items() if n != "Barrancabermeja" and v is not None]
            vals = [v for v in comps.values() if v is not None]
            tabla.append({"impuesto": imp, "anio": y, "yondo_pc_corrientes": r(yo),
                          "comparables_pc_corrientes": {n: r(v) for n, v in comps.items()},
                          "mediana_7": r(mediana(vals)), "mediana_6_sin_barrancabermeja": r(mediana(vals_sin_barranca)),
                          "p75_7": r(percentil(vals, 0.75)), "n_comparables_con_dato": len(vals)})

    def resumen(imp, y0, y1, ref):
        real = pot = 0.0
        anios_ok = []
        for y in range(y0, min(y1, 2024) + 1):
            fila = next(f for f in tabla if f["impuesto"] == imp and f["anio"] == y)
            yo = val(YONDO, f"{imp}_pc", y)
            m = fila[ref]
            pob = td[YONDO]["pob"][y]
            if yo is None or m is None:
                continue
            real += a_2026(yo * pob / 1e6, y)
            pot += a_2026(m * pob / 1e6, y)
            anios_ok.append(y)
        return real, pot, anios_ok

    for nombre, y0, y1 in PERIODOS:
        fila = {"periodo": nombre}
        for imp in ("predial", "ica"):
            for ref in ("mediana_7", "mediana_6_sin_barrancabermeja", "p75_7"):
                real, pot, ok = resumen(imp, y0, y1, ref)
                fila.setdefault(imp, {})[ref] = {
                    "recaudo_yondo_mm_2026": r(real, 1), "recaudo_con_esfuerzo_de_referencia_mm_2026": r(pot, 1),
                    "dejado_de_recaudar_mm_2026": r(max(0.0, pot - real), 1), "diferencia_mm_2026": r(pot - real, 1),
                    "anios": ok}
        por_periodo.append(fila)

    # tasa efectiva del predial: pesos de predial por cada $1.000 de avalúo catastral
    tasas = []
    for y in range(2012, 2025):
        fila = {"anio": y}
        for cod in [YONDO] + list(COMPARABLES):
            pc, pob, av = val(cod, "predial_pc", y), td[cod]["pob"].get(y), val(cod, "avaluo_mm", y)
            fila[td[cod]["nombre"]] = r(pc * pob / 1e6 / av * 1000, 2) if (pc and pob and av) else None
        comps = [fila[COMPARABLES[c]] for c in COMPARABLES if fila.get(COMPARABLES[c]) is not None]
        fila["mediana_comparables"] = r(mediana(comps), 2) if comps else None
        yo = fila.get("Yondó")
        av_y = val(YONDO, "avaluo_mm", y)
        if yo is not None and fila["mediana_comparables"] is not None and av_y:
            fila["predial_yondo_con_tasa_mediana_mm_2026"] = r(a_2026(av_y * fila["mediana_comparables"] / 1000, y), 1)
            fila["predial_yondo_real_mm_2026"] = r(a_2026(av_y * yo / 1000, y), 1)
        if fila["mediana_comparables"] is not None:
            tasas.append(fila)

    # ICA por barril producido (solo municipios cuya base principal es el petróleo de campo)
    ica_bbl = []
    for y in range(2014, 2025):
        fila = {"anio": y}
        for cod in CRUDO_BBL_MES:
            pc, pob = val(cod, "ica_pc", y), td[cod]["pob"].get(y)
            bbl = CRUDO_BBL_MES[cod][y] * 12
            fila[td[cod]["nombre"]] = {"ica_mm_corrientes": r(pc * pob / 1e6, 1) if pc else None,
                                       "barriles_anio": bbl,
                                       "ica_cop_2026_por_barril": r(a_2026(pc * pob / bbl, y)) if pc else None}
        ica_bbl.append(fila)

    perfil = {}
    for cod in [YONDO] + list(COMPARABLES):
        t = td[cod]
        perfil[t["nombre"]] = {
            "codigo_dane": cod,
            "poblacion_2024": r(t["pob"].get(2024)),
            "avaluo_catastral_2024_mm": r(t["avaluo_mm"].get(2024), 0),
            "avaluo_por_habitante_2024_cop": r(t["avaluo_mm"][2024] * 1e6 / t["pob"][2024]) if t["avaluo_mm"].get(2024) else None,
            "catastro_urbano_2024": t["catastro_urbano"].get(2024), "catastro_rural_2024": t["catastro_rural"].get(2024),
            "predial_pc_2024_cop": r(val(cod, "predial_pc", 2024)), "ica_pc_2024_cop": r(val(cod, "ica_pc", 2024)),
        }

    # años en que Yondó recaudó por habitante menos que la mediana de los siete comparables
    bajo = {imp: [f["anio"] for f in tabla if f["impuesto"] == imp and f["yondo_pc_corrientes"] is not None
                  and f["mediana_7"] is not None and f["yondo_pc_corrientes"] < f["mediana_7"]] for imp in ("predial", "ica")}

    # escenario de catastro: avalúo por habitante de Puerto Berrío (catastro actualizado en 2020-2023) con la tasa efectiva de Yondó
    t_y, t_pb = td[YONDO], td["05579"]
    av_pc_pb = t_pb["avaluo_mm"][2024] * 1e6 / t_pb["pob"][2024]
    av_pc_y = t_y["avaluo_mm"][2024] * 1e6 / t_y["pob"][2024]
    tasa_y24 = val(YONDO, "predial_pc", 2024) * t_y["pob"][2024] / (t_y["avaluo_mm"][2024] * 1e6) * 1000
    pred_esc = av_pc_pb * t_y["pob"][2024] * tasa_y24 / 1000 / 1e6
    pred_real = val(YONDO, "predial_pc", 2024) * t_y["pob"][2024] / 1e6
    escenario_catastro = {
        "tipo": "contrafactual",
        "pregunta": "¿Cuánto predial recaudaría Yondó si su avalúo catastral por habitante fuera el de Puerto Berrío, que actualizó su catastro "
                    "(urbano y rural 'Actualizado total' en 2020-2023), manteniendo la tasa efectiva de Yondó de 2024?",
        "avaluo_por_habitante_2024_cop": {"Yondó": r(av_pc_y), "Puerto Berrío": r(av_pc_pb)},
        "tasa_efectiva_yondo_2024_por_mil": r(tasa_y24, 2),
        "predial_2024_real_mm_corrientes": r(pred_real, 1),
        "predial_2024_con_avaluo_de_puerto_berrio_mm_corrientes": r(pred_esc, 1),
        "adicional_anual_mm_2026": r(a_2026(pred_esc - pred_real, 2024), 1),
        "nota": "Ilustrativo: el avalúo depende del valor de la tierra y de las construcciones, que no son iguales en los dos municipios. Muestra el "
                "orden de magnitud de una actualización catastral, que en Yondó está pendiente (catastro urbano y rural 'Desactualizado' en "
                "TerriData 2021-2024). En 2025 el predial de Yondó subió a $3.044 M según CUIPO (docs/anexos/B-finanzas-regalias.md, §5.3).",
    }

    tot = {}
    for imp in ("predial", "ica"):
        for ref in ("mediana_7", "mediana_6_sin_barrancabermeja", "p75_7"):
            tot.setdefault(imp, {})[ref] = {
                "dejado_de_recaudar_mm_2026_2004_2024": r(sum(p[imp][ref]["dejado_de_recaudar_mm_2026"] for p in por_periodo), 1),
                "diferencia_neta_mm_2026_2004_2024": r(sum(p[imp][ref]["diferencia_mm_2026"] for p in por_periodo), 1)}

    return {
        "tipo": "estimado (recaudo real = hecho; recaudo con esfuerzo de referencia = contrafactual)",
        "pregunta": "¿Cuánto más habría recaudado Yondó por predial e ICA si hubiera tenido el esfuerzo fiscal (recaudo por habitante) de la mediana "
                    "de municipios comparables?",
        "fuente": "TerriData (DNP), perfiles descargables por municipio, dimensión Finanzas públicas → Operaciones efectivas de caja (DNP con datos "
                  "del FUT y DANE): 'Ingresos per cápita por impuesto predial' e 'Ingresos per cápita por impuesto a la Industria y al comercio'; "
                  "dimensión Ordenamiento territorial → Catastro (IGAC). https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData{codigo}.txt.zip "
                  f"(archivos del 7-ago-2026, consultados el {CONSULTA}).",
        "comparables": COMPARABLES,
        "metodo": [
            "Recaudo de cada año = recaudo per cápita × población DANE de TerriData; se lleva a pesos de 2026 con el IPC promedio del año.",
            "Esfuerzo de referencia: mediana del recaudo per cápita de los comparables con dato ese año (siete con Barrancabermeja y seis sin ella). "
            "También se muestra el percentil 75 como meta exigente.",
            "Dejado de recaudar = (referencia − Yondó) × población de Yondó, sumado por periodo; si Yondó recaudó más que la referencia, se registra cero "
            "y la diferencia negativa se muestra aparte.",
            "Un valor cero en TerriData se trata como dato faltante (por ejemplo, el predial de Puerto Berrío en 2016).",
            "El periodo 2024-2027 solo tiene 2024.",
        ],
        "por_periodo": por_periodo,
        "totales_2004_2024": tot,
        "tasa_efectiva_predial_por_mil": {
            "metodo": "Predial recaudado ÷ avalúo catastral total × 1.000 (pesos por cada $1.000 de avalúo). Normaliza por el tamaño de la base: "
                      "un municipio con más predios valiosos recauda más sin mayor esfuerzo.",
            "serie": tasas,
        },
        "ica_por_barril": {
            "metodo": "ICA total ÷ barriles fiscalizados en el año (ANH, https://www.datos.gov.co/resource/fdvb-hsrf.json). Solo Yondó y Cantagallo: "
                      "los dos tienen campos de Ecopetrol y poca industria. Barrancabermeja (refinería) y Puerto Nare (cemento) no son comparables por barril.",
            "serie": ica_bbl,
        },
        "anios_yondo_por_debajo_de_la_mediana": bajo,
        "escenario_catastro": escenario_catastro,
        "perfil_2024": perfil,
        "base_petrolera_ica": [
            "La extracción de petróleo tiene un trato especial en el ICA: el art. 16 del Código de Petróleos (Decreto 1056 de 1953) y el art. 39 de la "
            "Ley 14 de 1983 limitan el impuesto municipal sobre la explotación cuando el municipio recibe regalías. Por eso la producción de Ecopetrol "
            "en Casabe no es, por sí misma, base gravable de ICA.",
            "En CUIPO, el 98 % del ICA de Yondó se clasifica como actividades de servicios (2023-2025): sale sobre todo de contratistas de servicios "
            "petroleros (docs/anexos/B-finanzas-regalias.md, §5.3). Cuánto paga directamente Ecopetrol debe pedirse a la Secretaría de Hacienda.",
            "Bases nuevas que conviene revisar con Hacienda: la granja solar La Iguana de Ecopetrol (26 MWp, en Yondó desde dic-2025) y el acuerdo "
            "Ecopetrol-Parex de 2026 para Casabe (más actividad de contratistas).",
        ],
        "lectura": None,  # se completa en main()
    }


# ---------------------------------------------------------------------------
# 6. Aguas residuales: tasa retributiva
# ---------------------------------------------------------------------------
def tm_anio(anio):
    """Tarifa mínima (DBO, SST) del año en pesos corrientes; antes de 2010 se devuelve con el IPC de diciembre."""
    if anio in TM_RETRIBUTIVA:
        return TM_RETRIBUTIVA[anio]
    if anio > 2024:
        dbo, sst = TM_RETRIBUTIVA[2024]
        for y in range(2024, anio):
            f = IPC_MENSUAL[y][11] / IPC_MENSUAL[y - 1][11]
            dbo, sst = dbo * f, sst * f
        return dbo, sst
    dbo, sst = TM_RETRIBUTIVA[2010]
    for y in range(2009, anio - 1, -1):
        f = IPC_MENSUAL[y][11] / IPC_MENSUAL[y - 1][11]
        dbo, sst = dbo / f, sst / f
    return dbo, sst


def aguas_residuales(soc):
    cab = soc["poblacion_cabecera_dane_base_cnpv2018"]["serie"]
    cob05, cob18 = 79.18, 89.45  # cobertura de alcantarillado urbana, censos 2005 y 2018 (series_sociales.json)
    G = 0.050  # kg/hab·día de DBO5 y de SST (RAS 2000, Título E, aporte per cápita de diseño)

    def cobertura(y):
        if y <= 2005:
            return cob05 / 100
        if y >= 2018:
            return cob18 / 100
        return (cob05 + (cob18 - cob05) * (y - 2005) / 13) / 100

    filas, acum1 = [], 0.0
    for y in range(2004, 2027):
        pob = cab[str(y)] * cobertura(y)
        carga = pob * G * 365  # kg/año (igual para DBO y SST)
        dbo, sst = tm_anio(y)
        tasa = carga * (dbo + sst)
        tasa26 = a_2026(tasa, y)
        acum1 += tasa26
        filas.append({"anio": y, "poblacion_conectada": r(pob), "carga_dbo_kg": r(carga), "carga_sst_kg": r(carga),
                      "tm_dbo": r(dbo, 2), "tm_sst": r(sst, 2), "tasa_fr1_mm_corrientes": r(tasa / 1e6, 1),
                      "tasa_fr1_mm_2026": r(tasa26 / 1e6, 1)})
    f26 = filas[-1]
    # variante por caudal medido (Superservicios 2020): 55,34 L/s a 150-220 mg/L de DBO y SST
    q = 13.52 + 16.51 + 10.62 + 14.69
    dbo26, sst26 = tm_anio(2026)
    carga_q = [q * 86400 * 365 * c / 1000 for c in (0.150, 0.220)]  # L/s × s/año × g/L ÷ 1.000 = kg/año
    tasa_q = [c * (dbo26 + sst26) / 1e6 for c in carga_q]
    return {
        "hechos": [
            "Superservicios (evaluación integral de Aguas & Aseo de Yondó, sep-2020): 'el vertimiento se realiza sin tratamiento alguno a cuerpos de "
            "agua cercanos a las estaciones de vertimiento, con excepción del cribado y sedimentación' en las estaciones de bombeo. Caudales vertidos "
            "en 2019: Progreso 13,52 L/s, Paraíso 16,51, Prado 10,62 y Victoria 14,69 (55,34 L/s en total). "
            "https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf",
            "El mismo informe registra cuentas por pagar a Corantioquia por $175 M con más de 360 días 'desde 2018', por tasa por uso del agua y "
            "tasa retributiva, y anota que podría no haberse causado ni pagado lo de 2018 y 2019.",
            "El Plan de Saneamiento y Manejo de Vertimientos (PSMV) lo aprobó Corantioquia en 2014 por 10 años (vencido en 2024 según ese plazo).",
            "Yondó no tiene PTAR en 2026 (data/gobiernos.json); los estudios del nuevo Plan Maestro (BPIN 2024058930006) figuran inactivos.",
        ],
        "tasa_retributiva": {
            "tipo": "estimado",
            "metodo": "Tasa = carga contaminante × tarifa mínima × factor regional (FR), para DBO5 y SST. Carga = población urbana conectada al "
                      "alcantarillado (DANE, cabecera; cobertura urbana 79,2 % en 2005 y 89,5 % en 2018, interpolada) × 50 g/hab·día de DBO5 y de SST "
                      "(aporte per cápita de diseño del RAS). Tarifa mínima de MinAmbiente (2010-2024), extendida con el IPC de diciembre a 2004-2009 y "
                      "2025-2026. FR entre 1,00 y 5,50 (Decreto 1553 de 2024; hasta 2024 los prestadores de alcantarillado aplicaron FR = 1 por la Ley 2294 de 2023).",
            "anual_2026_fr1_mm": f26["tasa_fr1_mm_2026"],
            "anual_2026_fr5_5_mm": r(f26["tasa_fr1_mm_2026"] * 5.5, 1),
            "anual_2026_por_caudal_medido_fr1_mm": [r(tasa_q[0], 1), r(tasa_q[1], 1)],
            "anual_2026_por_caudal_medido_fr5_5_mm": [r(tasa_q[0] * 5.5, 1), r(tasa_q[1] * 5.5, 1)],
            "acumulado_2004_2026_fr1_mm_2026": r(acum1 / 1e6, 1),
            "serie": filas,
            "lectura": "Con FR = 1, el vertimiento sin tratar le cuesta a Aguas y Aseo unos "
                       f"${es(f26['tasa_fr1_mm_2026'])} M al año en tasa retributiva (hasta ${es(tasa_q[1])} M si se calcula con el caudal medido). "
                       "Con el factor regional máximo (5,5) serían varios cientos de millones al año. Una PTAR que remueva 80 % de la carga reduciría "
                       "la tasa en una proporción parecida. El valor realmente facturado por Corantioquia no es público: hay que pedirlo.",
        },
        "no_cuantificado": [
            "Salud: no hay datos públicos de enfermedad diarreica o de piel atribuible al vertimiento en Yondó; atribuir casos exige un estudio epidemiológico.",
            "Pesca y ciénagas: no hay series de captura ni de calidad del agua del caño receptor y las ciénagas que permitan valorar el daño.",
            "Multas y sanciones ambientales: no se encontró un proceso sancionatorio público de Corantioquia contra el prestador.",
            "Costo de oportunidad de las regalías: los recursos de saneamiento del SGP (≈$2.700 M en 2025, docs/anexos/B) existen, pero no hay un "
            "proyecto de PTAR listo para financiar.",
        ],
    }


# ---------------------------------------------------------------------------
# 7. Equivalencias
# ---------------------------------------------------------------------------
def equivalencias(montos, costos):
    sel = ["aula_dotada", "km_placa_huella", "km_pavimento_urbano", "vis_rural", "vis_urbana", "ptar_12000_hab",
           "conexion_alcantarillado", "luminaria_led", "ambulancia_basica_tab", "ambulancia_medicalizada_tam",
           "puesto_salud_rural", "cdi", "beca_universitaria_anual", "km_red_acueducto"]
    cu = {c["id"]: c for c in costos}
    out = []
    for m in montos:
        fila = {"monto": m["nombre"], "valor_mm_2026": r(m["valor_mm"], 1), "tipo": m["tipo"], "origen": m["origen"], "equivale_a": []}
        for k in sel:
            c = cu[k]
            v = m["valor_mm"] * 1e6
            fila["equivale_a"].append({
                "id": k, "unidad": c["unidad"], "nombre": c["nombre"],
                "cantidad_central": r(v / c["costo_cop_2026"], 1),
                "cantidad_rango": [r(v / c["max"], 1), r(v / c["min"], 1)]})
        out.append(fila)
    return out


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, help="carpeta temporal para los perfiles de TerriData")
    args = ap.parse_args()

    micro = leer_json(RAIZ / "data" / "microrred.json")
    presu = leer_json(RAIZ / "data" / "presupuesto_microrred.json")
    soc = leer_json(RAIZ / "data" / "fuentes" / "series_sociales.json")
    with open(RAIZ / "data" / "fuentes" / "serie_fiscal_oec.csv", encoding="utf-8") as f:
        fiscal = list(csv.DictReader(f))

    costos = costos_unitarios()
    solar = contrafactual_solar(micro, presu)
    reg = contrafactual_regalias(fiscal)
    rec = recaudo_potencial(args.cache)
    agua = aguas_residuales(soc)

    # lectura del recaudo potencial
    tp = rec["totales_2004_2024"]
    bajo = rec["anios_yondo_por_debajo_de_la_mediana"]
    esc = rec["escenario_catastro"]
    ica_bbl = rec["ica_por_barril"]["serie"]
    prom_bbl = {m: statistics.mean(f[m]["ica_cop_2026_por_barril"] for f in ica_bbl) for m in ("Yondó", "Cantagallo")}
    rec["lectura"] = (
        "Frente a la mediana de los siete comparables, Yondó recaudó más predial e ICA por habitante en todos los periodos "
        f"(años por debajo de la mediana: predial {bajo['predial'] or 'ninguno'}; ICA {bajo['ica'] or 'ninguno'}). Lo 'dejado de recaudar' "
        f"suma ${es(tp['predial']['mediana_7']['dejado_de_recaudar_mm_2026_2004_2024'])} M en predial y "
        f"${es(tp['ica']['mediana_7']['dejado_de_recaudar_mm_2026_2004_2024'])} M en ICA (pesos de 2026, 2004-2024). "
        "Con la meta exigente del percentil 75, la brecha sube a "
        f"${es(tp['predial']['p75_7']['dejado_de_recaudar_mm_2026_2004_2024'])} M en predial y "
        f"${es(tp['ica']['p75_7']['dejado_de_recaudar_mm_2026_2004_2024'])} M en ICA. "
        f"El ICA por barril de Yondó (≈{es(prom_bbl['Yondó'])} pesos de 2026, promedio 2014-2024) es unas {es(prom_bbl['Yondó']/prom_bbl['Cantagallo'], 1)} veces "
        f"el de Cantagallo (≈{es(prom_bbl['Cantagallo'])}). No hay evidencia de un rezago frente a los vecinos: el potencial está en actualizar el "
        f"catastro (desactualizado desde 2021; con el avalúo por habitante de Puerto Berrío serían ≈${es(esc['adicional_anual_mm_2026'])} M más al año) "
        "y en revisar con Hacienda las bases nuevas del ICA."
    )

    # fila "solo solar, central" del mejor y del peor año
    mejor = max(solar["resultados"], key=lambda x: x["solo_solar"]["central"]["neto_hasta_2026_con_valor_residual"])
    tot_reg = reg["totales"]
    montos = [
        {"nombre": "Fondo de regalías 2004-2011 (10 %) en 2026, rendimiento real 3 %", "valor_mm": tot_reg["valor_fondo_2026_r3_mm"],
         "tipo": "contrafactual", "origen": "contrafactual_ahorro_regalias"},
        {"nombre": "Fondo de regalías 2004-2011 (10 %) en 2026, rendimiento real 4 %", "valor_mm": tot_reg["valor_fondo_2026_r4_mm"],
         "tipo": "contrafactual", "origen": "contrafactual_ahorro_regalias"},
        {"nombre": "10 % de las regalías 2004-2011, solo protegido de la inflación", "valor_mm": tot_reg["ahorro_10pct_mm_2026_sin_rendimiento"],
         "tipo": "hecho (deflactado)", "origen": "contrafactual_ahorro_regalias"},
        {"nombre": f"Ahorro neto solar si se instalaba en {mejor['anio_instalacion']} (solo solar, con valor residual)",
         "valor_mm": mejor["solo_solar"]["central"]["neto_hasta_2026_con_valor_residual"] / 1e6, "tipo": "contrafactual",
         "origen": "contrafactual_solar"},
        {"nombre": "Ahorro bruto anual de la solar del plan a tarifas de 2026 (lo que se pierde cada año de espera)",
         "valor_mm": solar["costo_de_esperar_desde_2026"]["ahorro_bruto_anual_solo_solar_cop_2026"] / 1e6, "tipo": "estimado",
         "origen": "contrafactual_solar"},
        {"nombre": "Tasa retributiva acumulada 2004-2026 con FR = 1 (vertimiento sin tratar)", "valor_mm": agua["tasa_retributiva"]["acumulado_2004_2026_fr1_mm_2026"],
         "tipo": "estimado", "origen": "aguas_residuales"},
    ]
    regalias_periodo = []
    for nombre, y0, y1 in PERIODOS:
        filas = [x for x in fiscal if y0 <= int(x["anio"]) <= y1]
        reg26 = sum(a_2026(float(x["regalias_giradas_mm_derivado"]), int(x["anio"])) for x in filas)
        inv26 = sum(a_2026(float(x["inversion_mm"]), int(x["anio"])) for x in filas)
        ing26 = sum(a_2026(float(x["ingresos_totales_mm"]), int(x["anio"])) for x in filas)
        regalias_periodo.append({"periodo": nombre, "anios_con_dato": [int(x["anio"]) for x in filas],
                                 "ingresos_totales_mm_2026": r(ing26, 1), "regalias_giradas_mm_2026": r(reg26, 1),
                                 "inversion_mm_2026": r(inv26, 1), "diez_por_ciento_regalias_mm_2026": r(reg26 * 0.10, 1)})
        montos.append({"nombre": f"10 % de las regalías giradas en {nombre}", "valor_mm": reg26 * 0.10, "tipo": "hecho (deflactado)",
                       "origen": "escala_por_periodo"})

    ipc_anual = {str(y): r(ipc_prom(y), 3) for y in range(2004, 2027)}
    salida = {
        "titulo": "Costo de no hacer, recaudo potencial y equivalencias en obras (Yondó, 2004-2026)",
        "generado_por": "scripts/costo_no_hacer.py",
        "fecha_corte": CONSULTA,
        "moneda": "Millones o pesos de 2026 (promedio del IPC DANE de enero a septiembre de 2026), salvo que diga 'corrientes'.",
        "convenciones": {
            "hecho": "Dato tomado de una fuente oficial, a lo sumo deflactado con el IPC.",
            "estimado": "Cálculo con método explícito sobre datos oficiales o de mercado; se da un rango.",
            "supuesto": "Valor de diseño o de mercado sin fuente única; se reemplaza con cotización.",
            "contrafactual": "Lo que habría pasado con otra decisión. No es un hecho ni una acusación: sirve para dimensionar.",
        },
        "aviso": "Ninguna cifra de este archivo señala a personas. Los contrafactuales muestran oportunidades, no responsabilidades individuales.",
        "series_usadas": {
            "ipc_dane": {"fuente": "https://www.dane.gov.co/files/operaciones/IPC/sep2026/anex-IPC-Indices-sep2026.xlsx (índice base dic-2018 = 100)",
                         "promedio_anual": ipc_anual, "base_2026": r(IPC_BASE, 3),
                         "diciembre": {str(y): IPC_MENSUAL[y][11] for y in range(2003, 2026)},
                         "factor_a_pesos_2026": {str(y): r(IPC_BASE / ipc_prom(y), 4) for y in range(2004, 2027)}},
            "trm_promedio_anual": {"fuente": "https://www.datos.gov.co/resource/32sa-8pi3.json", "valores": {str(k): v for k, v in TRM.items()}},
            "ipc_eeuu": {"fuente": "https://fred.stlouisfed.org/series/CPIAUCNS (promedio anual)", "valores": {str(k): v for k, v in US_CPI.items()}},
            "irena_solar_usd2024_kw": {"fuente": "IRENA, Renewable Power Generation Costs in 2024, fig. 3.1-3.2 "
                                                 "https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2025/Jul/IRENA_TEC_RPGC_in_2024_2025.pdf",
                                       "valores": {str(k): v for k, v in sorted(IRENA_PV.items())}, "nota": "2008 extrapolado (ver contrafactual_solar.insumos)."},
            "irena_baterias_usd2024_kwh": {"fuente": "IRENA, misma publicación, fig. 9.2 (BNEF; Schmidt y Staffell)",
                                           "valores": {"2010": IRENA_BESS_2010, "2024": IRENA_BESS_2024},
                                           "nota": "Años intermedios por interpolación logarítmica (caída constante de 17 % al año)."},
            "tarifa_epm_oficial_nt1": {
                "fuente": "Publicaciones mensuales de tarifas de EPM, mercado regulado de Antioquia, 'Oficial y exentos de contribución', nivel 1, "
                          "activos propiedad de EPM: https://www.epm.com.co/clientesyusuarios/energia/tarifas-energia/tarifas-anos-anteriores-energia "
                          "y https://www.epm.com.co/clientesyusuarios/energia/tarifas-energia/ ; 2016-2021 cotejado con https://www.datos.gov.co/resource/sfcd-b3ey.json",
                "promedio_anual_cop_corrientes_kwh": {str(y): r(tarifa_oficial(y), 2) for y in range(2008, 2027)},
                "meses_con_dato": {str(y): len(TARIFA_OFICIAL_EPM.get(y, {})) for y in range(2008, 2027)},
                "nota": "2008 estimado (no hay publicación en el portal de EPM): tarifa real constante respecto a 2009. 2026 = promedio de enero a octubre. "
                        "Se supone que Yondó paga la tarifa del mercado de Antioquia de EPM en todo el periodo.",
            },
            "smmlv_2026": {"valor": SMMLV_2026, "fuente": "Decreto 1469 de 2025 (sostenido por el Decreto 0159 de 2026)"},
        },
        "costos_unitarios": costos,
        "contrafactual_solar": solar,
        "contrafactual_ahorro_regalias": reg,
        "recaudo_potencial": rec,
        "aguas_residuales": agua,
        "escala_por_periodo": {
            "tipo": "hecho (deflactado)",
            "fuente": "data/fuentes/serie_fiscal_oec.csv (OEC, DNP-FUT vía TerriData), deflactado con IPC DANE.",
            "nota": "Sirve para dimensionar: qué tamaño tiene la plata de cada gobierno en pesos de hoy. 2024-2027 solo tiene 2024.",
            "filas": regalias_periodo,
        },
        "equivalencias": {
            "metodo": "Cantidad = monto ÷ costo unitario central; el rango usa el costo máximo y el mínimo. Son órdenes de magnitud: una obra real "
                      "requiere estudios, predios, interventoría y operación.",
            "filas": equivalencias(montos, costos),
        },
        "limitaciones": [
            "Los costos unitarios históricos se indexan con el IPC; los costos de construcción subieron más que el IPC en 2021-2023, así que algunas "
            "referencias indexadas pueden quedarse cortas.",
            "Los comparables tienen escalas y economías distintas (Barrancabermeja es ciudad con refinería; Remedios y Segovia son mineros de oro).",
            "TerriData calcula el recaudo per cápita con la población DANE vigente al publicar; cambios de base de población alteran el per cápita.",
            "El contrafactual solar usa perfiles de consumo supuestos (data/microrred.json) que deben reemplazarse con 12 facturas por cuenta.",
            "La tasa retributiva estimada no es lo facturado: Corantioquia y Aguas y Aseo de Yondó deben publicar el valor real.",
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Escrito {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    sys.exit(main())
