#!/usr/bin/env python3
"""La plata que no se convirtió en obra, por gobierno (síntesis).

Genera:
  data/comparativa/dinero_no_hecho.json   (lo lee la web: vista "Seis gobiernos", modo "La plata")
  docs/10-dinero-no-hecho-por-gobierno.md (explicación con tablas, método y limitaciones)

Insumos (todos en el repositorio; este script no descarga nada):
  data/comparativa/panel_anual.json     IPC base 2026, población, ingresos e inversión por gobierno
  data/comparativa/fugas_secop.json     contratación de la alcaldía por año (SECOP, pesos corrientes)
  data/comparativa/sgr_fondos.json      regalías, proyectos SGR, saldos y fondos externos (pesos corrientes)
  data/comparativa/costo_no_hacer.json  costos unitarios, contrafactual solar, ahorro de regalías, recaudo
  data/gobiernos.json                   periodos, alcaldes, qué se hizo y qué faltó

Todo se lleva a millones de pesos constantes de 2026 con el IPC de panel_anual.json
(promedio ene–sep 2026 = 1,0; cada año con su IPC promedio). Un saldo medido en una fecha
se deflacta con el IPC del año de esa fecha.

Uso:  python3 scripts/build_dinero_no_hecho.py
"""
import json
import re
import statistics
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COMP = RAIZ / 'data' / 'comparativa'
SALIDA = COMP / 'dinero_no_hecho.json'
DOC = RAIZ / 'docs' / '10-dinero-no-hecho-por-gobierno.md'
CORTE = '2026-10-21'

PANEL = json.load(open(COMP / 'panel_anual.json', encoding='utf-8'))
FUGAS = json.load(open(COMP / 'fugas_secop.json', encoding='utf-8'))
SGR = json.load(open(COMP / 'sgr_fondos.json', encoding='utf-8'))
CNH = json.load(open(COMP / 'costo_no_hacer.json', encoding='utf-8'))
GOB = json.load(open(RAIZ / 'data' / 'gobiernos.json', encoding='utf-8'))

IPC = {int(k): float(v) for k, v in PANEL['ipc'].items()}
POB = {int(k): float(v) for k, v in PANEL['poblacion'].items()}
IND = {i['id']: i for i in PANEL['indicadores']}

F_PANEL = 'data/comparativa/panel_anual.json'
F_FUGAS = 'data/comparativa/fugas_secop.json'
F_SGR = 'data/comparativa/sgr_fondos.json'
F_CNH = 'data/comparativa/costo_no_hacer.json'
F_GOB = 'data/gobiernos.json'
URL_SECOP = 'https://www.datos.gov.co/d/rpmr-utcd'


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def a26(pesos_corrientes, anio):
    """Pesos corrientes de un año → millones de pesos de 2026."""
    anio = min(max(int(anio), min(IPC)), max(IPC))
    return pesos_corrientes / 1e6 / IPC[anio]


def a26_prom(pesos_corrientes, anios):
    """Pesos de un rango de años (p. ej. un bienio) → millones de 2026 con el IPC promedio del rango."""
    f = statistics.mean(IPC[a] for a in anios)
    return pesos_corrientes / 1e6 / f


def r1(x):
    return None if x is None else round(float(x), 1)


def fmt(v, dec=0):
    """Número con formato colombiano: 12.345,6"""
    if v is None:
        return '—'
    q = Decimal(str(abs(v))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    s = f'{q:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('−' if v < 0 else '') + s


def mm(v, dec=0):
    if v is None:
        return '—'
    return f'−${fmt(-v, dec)} M' if v < 0 else f'${fmt(v, dec)} M'


def anios_de(pid):
    a, b = pid.split('-')
    return list(range(int(a), int(b) + 1))


def corto(s, n=150):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[: n - 1].rstrip() + '…'


SIGLAS = ['APS', 'PDET', 'EOT', 'EDU', 'CIC', 'PAE', 'E.S.E.', 'ESE', 'PTAR', 'MGA', 'AMMA', 'INVÍAS', 'OCAD', 'SGR', 'SAS', 'S.A.S.', 'E.S.P.', 'ESP', 'MPIO']


def frase_objeto(s, n=120):
    """Pasa a minúscula los textos escritos casi todo en mayúscula (como los registra SECOP o GESPROY), sin dañar siglas."""
    s = corto(s, n)
    letras = [ch for ch in s if ch.isalpha()]
    if letras and sum(ch.isupper() for ch in letras) / len(letras) > 0.5:
        s = s.lower()
        for sg in SIGLAS:
            s = re.sub(r'(?<![\w.])' + re.escape(sg.lower()) + r'(?![\w])', sg, s)
        for nombre in ['Yondó', 'Yondo', 'Antioquia', 'Medellín', 'Magdalena', 'San Miguel del Tigre', 'Puerto Nare', 'Yolombó', 'Caño Negro', 'Caño Don Juan',
                       'La Ye', 'San Francisco', 'San Luis Beltrán', 'Barrancabermeja', 'Casabe', 'José Domingo Oliveros', 'El Paraíso']:
            s = re.sub(re.escape(nombre.lower()), nombre, s)
    return s[:1].upper() + s[1:]


# ---------------------------------------------------------------------------
# costos unitarios (de costo_no_hacer.json) y unidades de equivalencia
# ---------------------------------------------------------------------------
CU = {c['id']: c for c in CNH['costos_unitarios']}
UNIDADES = {  # id de costo_no_hacer → unidad corta en plural para la web
    'aula_dotada': 'aulas escolares dotadas',
    'vis_rural': 'viviendas VIS rurales',
    'km_placa_huella': 'km de placa huella',
    'ptar_12000_hab': 'plantas de tratamiento de aguas residuales (PTAR)',
    'kwp_solar_cubierta': 'kWp solares en cubiertas',
    'ambulancia_medicalizada_tam': 'ambulancias medicalizadas',
    'beca_universitaria_anual': 'becas universitarias de un año',
}
SINGULAR = {
    'aula_dotada': 'aula escolar dotada', 'vis_rural': 'vivienda VIS rural', 'km_placa_huella': 'km de placa huella',
    'ptar_12000_hab': 'PTAR para el casco urbano', 'kwp_solar_cubierta': 'kWp solar en cubierta',
    'ambulancia_medicalizada_tam': 'ambulancia medicalizada', 'beca_universitaria_anual': 'beca universitaria de un año',
    'vis_urbana': 'vivienda VIS urbana', 'km_pavimento_urbano': 'km de vía urbana pavimentada', 'cdi': 'CDI',
}
PLURAL_EXTRA = {'vis_urbana': 'viviendas VIS urbanas', 'km_pavimento_urbano': 'km de vía urbana pavimentada', 'cdi': 'CDI'}


def cu(id_):
    return CU[id_]['costo_cop_2026'] / 1e6


def cu_min(id_):
    return CU[id_]['min'] / 1e6


def cu_max(id_):
    return CU[id_]['max'] / 1e6


def eq_texto(valor, id_):
    n = valor / cu(id_)
    nombre = SINGULAR[id_] if round(n, 1) == 1 else (UNIDADES.get(id_) or PLURAL_EXTRA.get(id_))
    if id_ == 'ptar_12000_hab':
        nombre = 'PTAR para el casco urbano' if round(n, 1) == 1 else 'PTAR como la que necesita el casco urbano'
    return f'≈ {fmt(n, 1 if n < 10 else 0)} {nombre}'


# ---------------------------------------------------------------------------
# insumos por año (alcaldía, SECOP) y por periodo
# ---------------------------------------------------------------------------
SECOP_ALC = {r['anio']: r for r in FUGAS['por_anio'] if r['entidad'] == 'Alcaldía'}
RES_ALC = {r['periodo']: r for r in FUGAS['resumen_alcaldia_por_periodo']}
PANEL_PER = {p['id']: p for p in PANEL['periodos']}
SGR_RES = {p['periodo']: p for p in SGR['resumen_por_periodo']}
SGR_PROY = {p['periodo']: p for p in SGR['proyectos_por_periodo']}
SGR_AD = {b['bienio']: b for b in SGR['asignaciones_directas']}
FONDOS = {}
for f in SGR['fondos']:
    n = f['fondo']
    k = ('OCAD_PAZ' if n.startswith('OCAD Paz') else 'INCENTIVO' if n.startswith('Incentivo') else 'AIL' if n.startswith('Asignación para la Inversión')
         else 'OXI' if n.startswith('Obras por') else 'FENOGE' if n.startswith('FENOGE') else 'MINTIC' if n.startswith('MinTIC')
         else 'FINDETER' if n.startswith('Findeter') else 'ADAPTACION' if n.startswith('Fondo Adaptación') else 'COOPERACION')
    FONDOS[k] = f
SOLAR = {r['gobierno_que_inicia']: r for r in CNH['contrafactual_solar']['resultados']}
AHORRO = {r['anio']: r for r in CNH['contrafactual_ahorro_regalias']['filas']}
RECAUDO = {r['periodo']: r for r in CNH['recaudo_potencial']['por_periodo']}
CATASTRO = CNH['recaudo_potencial']['escenario_catastro']
TASA = {r['anio']: r for r in CNH['aguas_residuales']['tasa_retributiva']['serie']}
TASA_INFO = CNH['aguas_residuales']['tasa_retributiva']

# proyectos SGR que ejecutó la EDU de Medellín como contratista del municipio (docs/01-diagnostico-sectorial.md, tabla de brechas)
BPIN_EDU = {'20201301010644', '20201301010781', '2022003050005', '2022003050034', '20211301012365', '2023058930013'}

# literatura para el sobrecosto de contratar sin competencia
LIT_SOBRECOSTO = [
    {'ref': 'Titl, V. (2024). Reform of Single-Bidding in Public Procurement: More Competition, Lower Price. IDEA Study 3/2024 (CERGE-EI); versión académica: The One and Only: Single-Bidding in Public Procurement, U.S.E. Working Paper 23-08, Universidad de Utrecht.',
     'hallazgo': 'En Chequia, prohibir la adjudicación de contratos con una sola oferta bajó los precios cerca de 6 % del costo estimado.',
     'url': 'https://idea-en.cerge-ei.cz/files/IDEA_Studie_03_2024_Verejne_zakazky_abstract_EN.pdf ; https://www.uu.nl/sites/default/files/LEG_USE_WP_23-08%20%282%29.pdf',
     'uso': 'piso del rango (5 %)'},
    {'ref': 'OCDE (2014). OECD Foreign Bribery Report: An Analysis of the Crime of Bribery of Foreign Public Officials.',
     'hallazgo': 'En 427 casos de soborno, el soborno promedio fue 10,9 % del valor de la transacción; el 57 % de los casos buscaba ganar contratos públicos.',
     'url': 'https://doi.org/10.1787/9789264226616-en',
     'uso': 'orden de magnitud del valor central (10 %)'},
    {'ref': 'PwC y Ecorys para la Comisión Europea (OLAF) (2013). Identifying and reducing corruption in public procurement in the EU.',
     'hallazgo': 'En contratos con corrupción o con señales de ella ("casos grises"), la pérdida pública directa fue 18 % del presupuesto del proyecto, 13 % atribuible a la corrupción.',
     'url': 'https://dspace.library.uu.nl/handle/1874/309580',
     'uso': 'techo del rango (15 %), solo alcanzable si hubiera corrupción'},
    {'ref': 'Szucs, F. (2024). Discretion and Favoritism in Public Procurement. Journal of the European Economic Association 22(1): 117–160.',
     'hallazgo': 'En Hungría, cuando el comprador puede elegir sin subasta abierta los precios suben y ganan contratistas menos productivos y con conexiones políticas.',
     'url': 'https://doi.org/10.1093/jeea/jvad017',
     'uso': 'dirección del efecto'},
    {'ref': 'Gallego, J., Prem, M. y Vargas, J. F. (2021). Inefficient Procurement in Times of Pandemia. SSRN 3600572 (antes: Corruption in the Times of Pandemia, Universidad del Rosario, DT 250, 2020).',
     'hallazgo': 'En Colombia, en 2020 los municipios con más riesgo de corrupción pasaron a contratación no competitiva y subieron el valor de sus contratos; esos contratos tuvieron más sobrecostos.',
     'url': 'https://papers.ssrn.com/abstract=3600572',
     'uso': 'evidencia colombiana de la dirección del efecto'},
]
SOBRECOSTO = {'min': 0.05, 'central': 0.10, 'max': 0.15}


# ---------------------------------------------------------------------------
# categorías
# ---------------------------------------------------------------------------
CATEGORIAS = [
    {'id': 'estudios_sin_obra', 'nombre': 'Estudios y diseños sin obra posterior', 'tipo': 'estimado',
     'descripcion': 'Estudios, diseños y consultorías que la alcaldía pagó y que no tienen después, en SECOP, una obra con objeto parecido.',
     'metodo': 'Suma por año de "estudios.sin_obra_valor_sin_mixtos" de la alcaldía (fugas_secop.json; regla de similitud de palabras del objeto ≥ 0,30 con obras firmadas el mismo año o después). Se excluyen los contratos mixtos (diseño y obra en el mismo contrato, como el de $11.696 M con la EDU): su obra está adentro o ya se cuenta en "plata girada sin avance". Mínimo: se restan los planes de ordenamiento, que no llevan a una obra directa. Es estimado porque la coincidencia por palabras puede fallar en los dos sentidos.'},
    {'id': 'girado_sin_avance', 'nombre': 'Plata girada sin avance físico equivalente', 'tipo': 'hecho',
     'descripcion': 'Regalías ya pagadas a proyectos cuya obra avanza menos que los pagos (SGR), incluidos los ejecutados con la EDU de Medellín como contratista del municipio.',
     'metodo': 'Por proyecto SGR con ejecutor municipal: valor × (ejecución financiera − ejecución física) / 100, con datos de GESPROY (sgr_fondos.json). Cada proyecto se asigna al gobierno que lo aprobó; como los pagos se reparten en varios años, se deflacta con el IPC promedio desde el año de su primer contrato hasta 2025. Los proyectos de INVÍAS u otras entidades nacionales no se suman al gobierno municipal; se mencionan en el detalle. Para la plata que no es de regalías no hay datos abiertos de avance físico.'},
    {'id': 'saldos_regalias', 'nombre': 'Regalías sin aprobar o sin comprometer', 'tipo': 'hecho',
     'descripcion': 'Regalías asignadas a Yondó que, en la fecha de corte oficial más cercana al cierre del gobierno, no se habían aprobado en proyectos o no se habían comprometido.',
     'metodo': 'Saldos oficiales de sgr_fondos.json (CHIP, SICODIS y MinHacienda): asignaciones directas, incentivos del Acto Legislativo 04 de 2017 y del Incentivo a la Producción, y Asignación para la Inversión Local. Se toma un solo corte por gobierno (el bienio que cerró en su periodo) para no sumar dos fotos de la misma plata. Un saldo no es plata perdida: pasa al bienio siguiente; mide plata disponible que no se volvió obra a tiempo.'},
    {'id': 'sobrecosto_sin_competencia', 'nombre': 'Sobrecosto probable por contratar sin competencia', 'tipo': 'estimado',
     'descripcion': 'El valor contratado sin competencia es un hecho registrado en SECOP; lo que se pudo pagar de más por no competir es una estimación con rango (5 %, 10 % y 15 %).',
     'metodo': 'Base por año (alcaldía): valor sin competencia (contratación directa, régimen especial y convenios) menos OPS y menos estudios sin obra ya contados; más los procesos competitivos con un solo oferente. Las transferencias a Aguas y Aseo y al hospital se dejan en la base porque esas entidades vuelven a contratar sin competencia (régimen especial), salvo los convenios para subsidiar tarifas, que no son compras. A la base del gobierno se le restan la plata girada sin avance ya contada y una copia de cada registro duplicado identificado. Sobrecosto = base × 5 % (mínimo), 10 % (central) y 15 % (máximo), según la literatura citada en "literatura_sobrecosto".'},
    {'id': 'ops_nomina_paralela', 'nombre': 'Nómina paralela (OPS) por encima de lo usual', 'tipo': 'estimado',
     'descripcion': 'Gasto en contratos de prestación de servicios (OPS) por encima del nivel que Yondó mismo tuvo en un año típico.',
     'metodo': 'Referencia: mediana del gasto anual en OPS por habitante de 2012 a 2025 (años con registro completo en SECOP), en pesos de 2026. Exceso de cada año = (OPS del año − referencia × población del año), si es positivo. Rango: con el percentil 75 de esos años como referencia (mínimo) y con el percentil 25 (máximo). No es un tope legal: la ley no fija uno, pero prohíbe usar OPS para funciones permanentes (Corte Constitucional, Sentencia C-614 de 2009).'},
    {'id': 'recaudo_no_cobrado', 'nombre': 'Recaudo propio que se dejó de cobrar', 'tipo': 'estimado',
     'descripcion': 'Predial e ICA que Yondó habría recaudado con el esfuerzo de municipios comparables o con un catastro actualizado.',
     'metodo': 'Central: brecha frente a la mediana de 7 comparables (costo_no_hacer.json); es cero en todos los periodos porque Yondó recaudó más por habitante. Máximo: brecha frente al percentil 75 de los comparables y, desde 2021 (catastro desactualizado), el predial adicional con el avalúo por habitante de Puerto Berrío (≈$1.498 M al año, ilustrativo); en predial se toma el mayor de los dos para no sumarlos.'},
    {'id': 'costo_vertimientos', 'nombre': 'Tasa retributiva por verter aguas residuales sin tratar', 'tipo': 'estimado',
     'descripcion': 'Lo que cuesta cada año, en tasa ambiental, verter al río y las ciénagas las aguas negras del casco urbano sin una PTAR.',
     'metodo': 'Suma de la tasa retributiva estimada con factor regional 1 (costo_no_hacer.json, aguas_residuales); máximo con el caudal medido por la Superservicios en 2019 (hasta 1,98 veces). El valor facturado por Corantioquia no es público.'},
    {'id': 'fondos_no_gestionados', 'nombre': 'Fondos externos no gestionados', 'tipo': 'contrafactual',
     'descripcion': 'Plata de fondos nacionales o de cooperación que Yondó pudo pedir, como lo hicieron municipios parecidos, y no pidió.',
     'metodo': 'Rangos de sgr_fondos.json repartidos entre gobiernos sin repetir la misma oportunidad: Obras por Impuestos (ventana 2018–2023, un proyecto vial mediano por gobierno como central), MinTIC Centros Digitales, Fondo Adaptación (central 0: no se verificó que Yondó registrara daños en 2010–2011), cooperación internacional (central: una donación pequeña por gobierno), OCAD Paz y FENOGE (2024–2027). Findeter no se suma: es crédito. Los saldos del Incentivo a la Producción y de la Asignación para la Inversión Local van en "saldos de regalías" porque ya son de Yondó.'},
    {'id': 'ahorro_solar', 'nombre': 'Ahorro solar no capturado', 'tipo': 'contrafactual',
     'descripcion': 'Ahorro neto en facturas de energía, hasta 2026, si las 13 sedes públicas del plan (469 kWp) se hubieran puesto solares al empezar el gobierno.',
     'metodo': 'Contrafactual de costo_no_hacer.json, solo solar, neto con valor residual, escenario central y rango alto/bajo. Si el neto es negativo (2008) se registra cero: no habría convenido. Cada gobierno es un escenario aparte; no se suman entre gobiernos.'},
    {'id': 'ahorro_regalias', 'nombre': 'Ahorro de regalías no constituido', 'tipo': 'contrafactual',
     'descripcion': 'Lo que valdría hoy un fondo local con el 10 % de las regalías directas de 2004–2011, cuando el municipio las manejaba directamente.',
     'metodo': 'Aportes anuales del 10 % (costo_no_hacer.json) que crecen al 3 % real (central) o 4 % (máximo) hasta 2026; mínimo: el aporte sin rendimiento. Desde 2012 el Sistema General de Regalías ahorra a nivel nacional (Fondo de Ahorro y Estabilización) y no aplica.'},
]
CAT_TIPO = {c['id']: c['tipo'] for c in CATEGORIAS}
CAT_NOMBRE = {c['id']: c['nombre'] for c in CATEGORIAS}


def fuga(cat, valor, mn=None, mx=None, detalle='', items=None, fuentes=None, sin_dato=False, **extra):
    d = {'categoria': cat, 'valor': r1(valor), 'min': r1(mn), 'max': r1(mx), 'tipo': CAT_TIPO[cat],
         'detalle': ' '.join(detalle.split()), 'items': items or [], 'fuentes': fuentes or []}
    if sin_dato:
        d['sin_dato'] = True
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# referencia de OPS (mediana y cuartiles del gasto por habitante 2012–2025)
# ---------------------------------------------------------------------------
OPS_PC = {a: a26(SECOP_ALC[a]['ops']['valor'], a) * 1e6 / POB[a] for a in SECOP_ALC if a in POB and SECOP_ALC[a]['ops']['n']}
_ref_years = [a for a in range(2012, 2026) if a in OPS_PC]
_q = statistics.quantiles([OPS_PC[a] for a in _ref_years], n=4)
OPS_REF = {'p25': _q[0], 'mediana': statistics.median(OPS_PC[a] for a in _ref_years), 'p75': _q[2]}


# ---------------------------------------------------------------------------
# cálculo por periodo
# ---------------------------------------------------------------------------
def girado_sin_avance(pid):
    p = SGR_PROY[pid]
    items, total, otros = [], 0.0, []
    for it in p['items']:
        g = it.get('girado_sin_avance') or 0
        if g <= 0:
            continue
        anio = int(it.get('primer_contrato_vigencia') or it['anio'])
        # los pagos se reparten entre el primer contrato y el último año con ejecución (≤ 2025): IPC promedio de esos años
        v = a26_prom(g, range(min(anio, 2025), 2026))
        nombre = frase_objeto(it['nombre'], 110)
        fuente = (f"GESPROY y MapaInversiones, BPIN {it['bpin']} (https://www.datos.gov.co/d/mzgh-shtp): avance físico {fmt(it['ej_fisica'])} % "
                  f"y financiero {fmt(it['ej_financiera'])} %; {F_SGR}")
        if it['grupo_ejecutor'] == 'municipio':
            total += v
            items.append({'nombre': nombre + (' (ejecutada con la EDU de Medellín)' if it['bpin'] in BPIN_EDU else ''), 'anio': int(anio),
                          'valor': r1(v), 'fuente': fuente, 'bpin': it['bpin'], 'valor_proyecto': r1(a26(it['valor'], it['anio'])),
                          'avance_fisico_pct': it['ej_fisica'], 'avance_financiero_pct': it['ej_financiera'], 'edu': it['bpin'] in BPIN_EDU,
                          **({'alertas_datos': it['alertas_datos']} if it.get('alertas_datos') else {})})
        else:
            otros.append((it['ejecutor'], v, it['bpin']))
    items.sort(key=lambda x: -x['valor'])
    return total, items, otros


def calcular_periodo(pid):
    anios = anios_de(pid)
    ap = PANEL_PER[pid]['agregados']
    ing = ap['ingresos_totales']['suma_mm_2026']
    anios_plata = ap['ingresos_totales']['anios_con_dato']
    trib = IND['tributarios']['serie']
    propios = sum(trib[str(a)] for a in anios_plata if str(a) in trib)
    sec_anios = [a for a in anios if a in SECOP_ALC]
    fugas = []

    # --- A. estudios sin obra ------------------------------------------------
    est = sum(a26(SECOP_ALC[a]['estudios']['sin_obra_valor_sin_mixtos'], a) for a in sec_anios)
    est_con_mixtos = sum(a26(SECOP_ALC[a]['estudios']['sin_obra_valor'], a) for a in sec_anios)
    n_sin = sum(SECOP_ALC[a]['estudios']['sin_obra_n'] - SECOP_ALC[a]['estudios']['sin_obra_mixtos_n'] for a in sec_anios)
    n_eval = sum(SECOP_ALC[a]['estudios']['evaluados_n'] for a in sec_anios)
    n_con = sum(SECOP_ALC[a]['estudios']['con_obra_n'] for a in sec_anios)
    tops = [t for t in FUGAS['estudios_sin_obra_top'] if t['entidad'] == 'Alcaldía' and t['anio'] in anios]
    planes = sum(a26(t['valor'], t['anio']) for t in tops if t.get('nota') and t['nota'].startswith('Planes'))
    items = [{'nombre': frase_objeto(t['objeto']) + (f" ({t['contratista'].split(' (')[0]})" if t.get('contratista') and not t['contratista'].startswith('Persona natural') else ''),
              'anio': t['anio'], 'valor': r1(a26(t['valor'], t['anio'])), 'fuente': t['url'],
              'nota': t.get('nota')} for t in tops if not (t.get('nota') or '').startswith('El mismo contrato incluye obra')]
    mixtos = [t for t in tops if (t.get('nota') or '').startswith('El mismo contrato incluye obra')]
    det = (f"{n_sin} estudios o consultorías de la alcaldía sin obra posterior identificable en SECOP, de {n_eval} evaluados ({n_con} con obra). "
           + (f"Con los contratos mixtos (diseño y obra juntos) serían {mm(est_con_mixtos)}; no se cuentan porque su obra va dentro del contrato o ya está en 'plata girada sin avance'." if est_con_mixtos - est >= 0.5 else ''))
    if planes:
        det += f" Incluye {mm(planes)} de planes de ordenamiento: no llevan a una obra, pero se pagaron; el mínimo los resta."
    if pid == '2004-2007':
        det = 'SECOP no tiene estudios de la alcaldía en estos años (solo 41 contratos en 2007). Sin dato: no significa que no hubo estudios sin obra.'
    fugas.append(fuga('estudios_sin_obra', est, est - planes, est, det, items, [F_FUGAS, URL_SECOP], sin_dato=(pid == '2004-2007'),
                      con_mixtos=r1(est_con_mixtos), mixtos_excluidos=[{'nombre': frase_objeto(t['objeto'], 90), 'anio': t['anio'], 'valor': r1(a26(t['valor'], t['anio'])), 'fuente': t['url']} for t in mixtos]))

    # --- B. plata girada sin avance ----------------------------------------
    gsa, gitems, otros = girado_sin_avance(pid)
    det = ''
    if gitems:
        edu = sum(i['valor'] for i in gitems if i['edu'])
        det = f"{len(gitems)} proyectos de regalías con ejecutor municipal pagaron más de lo que avanzó la obra."
        if edu:
            det += f" {mm(edu)} corresponden a proyectos que el municipio delegó en la EDU de Medellín."
    if otros:
        det += ' No se suman (ejecutor nacional): ' + '; '.join(f"{'INVÍAS' if 'NACIONAL DE VIAS' in e.upper() else e.title()} {mm(v)} (BPIN {b}, vías terciarias PDET del OCAD Paz)" for e, v, b in otros) + '.'
    if pid in ('2004-2007', '2008-2011'):
        det = 'Antes de 2012 no hay registro abierto de proyectos de regalías con avance físico (BPIN): no se puede saber en qué obras terminó cada peso del régimen anterior.'
    elif not gitems:
        det = 'Ningún proyecto de regalías aprobado en este periodo tiene pagos por encima del avance de obra.' + (det if otros else '')
    det += ' Para la plata propia (no regalías) no hay datos abiertos de avance físico: SECOP I no publica pagos y SECOP II no publica avance de obra.'
    fugas.append(fuga('girado_sin_avance', gsa, None, None, det.strip(), gitems, [F_SGR, 'https://www.datos.gov.co/d/mzgh-shtp', 'docs/01-diagnostico-sectorial.md'],
                      sin_dato=pid in ('2004-2007', '2008-2011'),
                      no_sumado_ejecutor_nacional=r1(sum(v for _, v, _ in otros))))

    # --- C. saldos de regalías ---------------------------------------------
    sal_items, sal_ctx, sal_det = [], [], ''
    if pid == '2016-2019':
        b = SGR_AD['2015-2016']
        sal_items.append({'nombre': 'Asignaciones directas recaudadas y no comprometidas al cierre del bienio 2015–2016 (CHIP)', 'anio': 2016,
                          'valor': r1(a26(b['saldo'], 2016)), 'fuente': b['fuente'], 'cruza_dos_gobiernos': True})
        b2 = SGR_AD['2017-2018']
        sal_ctx.append({'nombre': 'Saldo de asignaciones directas sin aprobar acumulado 2012–junio de 2018 (SICODIS); no se suma: es otra foto de la misma plata', 'anio': 2018,
                        'valor': r1(a26(b2['saldo'], 2018)), 'fuente': b2['fuente'], 'en_total': False})
        sal_ctx.append({'nombre': 'SGR presupuestado y sin comprometer a septiembre de 2018 (CHIP); no se suma: es otra foto', 'anio': 2018,
                        'valor': r1(a26(b2['sin_comprometer_sgr_chip_sep2018'], 2018)), 'fuente': b2['fuente'], 'en_total': False})
        sal_det = (f"Al cierre de 2016 quedaban {mm(a26(b['saldo'], 2016))} de regalías en caja sin comprometer ({mm(a26(b['recaudo_ad_no_presupuestado'], 2016))} ni siquiera se habían "
                   f"incorporado al presupuesto). En junio de 2018 el saldo sin aprobar llegó a {mm(a26(b2['saldo'], 2018))}; buena parte se aprobó en 2019, el año con más aprobaciones de la serie.")
    elif pid == '2020-2023':
        b = SGR_AD['2021-2022']
        inc = FONDOS['INCENTIVO']['yondo_obtuvo']
        ail = FONDOS['AIL']['yondo_obtuvo']
        sal_items += [
            {'nombre': 'Asignaciones directas sin comprometer al cierre del bienio 2021–2022 (CHIP)', 'anio': 2022, 'valor': r1(a26(b['saldo'], 2022)), 'fuente': b['fuente']},
            {'nombre': 'Incentivos del Acto Legislativo 04 de 2017 que pasaron sin usar a 2023–2024', 'anio': 2022, 'valor': r1(a26(inc['incentivos_al04_sin_usar_inicio_2023'], 2022)),
             'fuente': 'https://www.datos.gov.co/d/5ka2-and2 (disponibilidad inicial 2023-2024); ' + F_SGR},
            {'nombre': 'Asignación para la Inversión Local sin comprometer, 2021–2022 (CHIP)', 'anio': 2022, 'valor': r1(a26(ail['sin_comprometer_2021_2022'], 2022)),
             'fuente': 'https://www.datos.gov.co/d/xr2w-9eg2 y https://www.datos.gov.co/d/qkv4-ek54; ' + F_SGR},
        ]
        b0 = SGR_AD['2019-2020']
        sal_ctx.append({'nombre': 'Saldo de asignaciones directas que pasó de 2019–2020 a 2021–2022 (no se suma: es una foto anterior)', 'anio': 2020,
                        'valor': r1(a26(b0['saldo'], 2020)), 'fuente': b0['fuente'], 'en_total': False})
        sal_det = (f"Al cierre de 2022 quedaban sin comprometer {mm(a26(b['saldo'], 2022))} de asignaciones directas, {mm(a26(inc['incentivos_al04_sin_usar_inicio_2023'], 2022))} de incentivos "
                   f"del OCAD Paz y {mm(a26(ail['sin_comprometer_2021_2022'], 2022))} de la Asignación para la Inversión Local. Además, {mm(a26(b['paso_al_siguiente_bienio_sin_pagar'], 2022))} comprometidos pasaron sin pagar al bienio siguiente.")
    elif pid == '2024-2027':
        b = SGR_AD['2025-2026']
        inc = FONDOS['INCENTIVO']['yondo_obtuvo']
        ail = FONDOS['AIL']['yondo_obtuvo']
        ail_sin = ail['presupuesto_2025_2026'] - ail['aprobado_2025_2026']
        sal_items += [
            {'nombre': 'Asignaciones directas sin aprobar en proyectos, bienio 2025–2026 (corte oct-2026, MinHacienda)', 'anio': 2026, 'valor': r1(b['saldo'] / 1e6), 'fuente': b['fuente']},
            {'nombre': 'Incentivo a la Producción del SGR sin aprobar, 2025–2026 (solo 2,4 % aprobado)', 'anio': 2026, 'valor': r1(inc['saldo_sin_aprobar'] / 1e6),
             'fuente': 'https://www.datos.gov.co/d/e624-d9uy (corte oct-2026); ' + F_SGR},
            {'nombre': 'Asignación para la Inversión Local sin aprobar, 2025–2026', 'anio': 2026, 'valor': r1(ail_sin / 1e6), 'fuente': 'https://www.datos.gov.co/d/e624-d9uy (corte oct-2026); ' + F_SGR},
        ]
        b0 = SGR_AD['2023-2024']
        sal_ctx.append({'nombre': 'Asignaciones directas sin comprometer al cierre de 2023–2024 (bienio compartido; no se suma: es una foto anterior)', 'anio': 2024,
                        'valor': r1(a26(b0['saldo'], 2024)), 'fuente': b0['fuente'], 'en_total': False})
        sal_det = (f"Periodo en curso: a octubre de 2026 hay {mm(b['saldo'] / 1e6)} de asignaciones directas sin aprobar ({mm(b['saldo_en_caja'] / 1e6)} en caja), {mm(inc['saldo_sin_aprobar'] / 1e6)} "
                   f"del Incentivo a la Producción (pares: San Pablo aprobó 83 %, Cantagallo 43 %) y {mm(ail_sin / 1e6)} de inversión local. El bienio cierra en diciembre de 2026: todavía se puede aprobar.")
    elif pid == '2012-2015':
        sal_det = 'No hay un saldo oficial al cierre de 2015. El saldo del bienio 2015–2016 se asigna al gobierno siguiente, que lo cerró.'
    else:
        sal_det = 'Antes de 2012 las regalías directas entraban al presupuesto municipal sin bolsas ni bienios: no hay saldos de regalías comparables.'
    sal = sum(i['valor'] for i in sal_items)
    fugas.append(fuga('saldos_regalias', sal, None, None, sal_det, sal_items + sal_ctx, [F_SGR, 'https://www.datos.gov.co/d/e624-d9uy', 'https://sicodis.dnp.gov.co'],
                      sin_dato=pid in ('2004-2007', '2008-2011', '2012-2015')))

    # --- D. sobrecosto por contratar sin competencia -------------------------
    base_bruta = sincomp = valor_alc = uo = ops_v = tr_v = 0.0
    for a in sec_anios:
        r = SECOP_ALC[a]
        sc = r['sin_competencia']['valor']
        b = max(0.0, sc - r['ops']['valor'] - r['estudios']['sin_obra_valor_sin_mixtos'])
        base_bruta += a26(b, a)
        uo += a26(r['un_oferente']['un_oferente_valor'], a)
        sincomp += a26(sc, a)
        valor_alc += a26(r['valor'], a)
        ops_v += a26(r['ops']['valor'], a)
        tr_v += a26(r['transferencias_internas']['valor'], a)
    conv_alc = [c for c in FUGAS['convenios_delegada'] if c['entidad'] == 'Alcaldía' and c['anio'] in anios]
    # subsidios a las tarifas de servicios públicos: transferencia, no compra (no lleva sobrecosto)
    subs = sum(a26(c['valor'], c['anio']) for c in conv_alc if 'SUBSIDI' in c['objeto'].upper())
    # posibles registros duplicados (misma fecha, valor y contratista): se resta una copia
    dup_g = {}
    for c in conv_alc:
        if c.get('posible_registro_duplicado'):
            dup_g.setdefault((c['anio'], c['valor']), []).append(c)
    dup = sum(a26(k[1], k[0]) * (len(v) - 1) for k, v in dup_g.items())
    base = max(0.0, base_bruta - subs - dup + uo - gsa)
    conv = sorted([c for c in FUGAS['convenios_delegada'] if c['entidad'] == 'Alcaldía' and c['anio'] in anios],
                  key=lambda c: -c['valor'])[:3]
    citems = [{'nombre': f"Base (contrato sin competencia): {frase_objeto(c['objeto'], 100)} — {c['contratista'].split(' (')[0]}", 'anio': c['anio'],
               'valor': r1(a26(c['valor'], c['anio'])), 'fuente': c['url'], 'en_total': False} for c in conv]
    pct_sc = 100 * sincomp / valor_alc if valor_alc else None
    restas = [x for x in [f'{mm(ops_v)} de OPS' if ops_v >= 0.5 else '', 'los estudios sin obra' if est >= 0.5 else '',
                          f'{mm(gsa)} de plata girada sin avance' if gsa >= 0.5 else '', f'{mm(subs)} de subsidios a las tarifas' if subs else '',
                          f'{mm(dup)} de un registro duplicado' if dup else ''] if x]
    det = f"Hecho: la alcaldía contrató {mm(sincomp)} sin competencia ({fmt(pct_sc, 1)} % de {mm(valor_alc)}, pesos de 2026; SECOP). Base para el sobrecosto: {mm(base)}"
    partes = []
    if restas:
        partes.append('se restan ' + (', '.join(restas[:-1]) + ' y ' + restas[-1] if len(restas) > 1 else restas[0]))
    if uo >= 0.5:
        partes.append(f'se suman {mm(uo)} de procesos competitivos con un solo oferente')
    det += (' (' + '; '.join(partes) + ').' if partes else '.')
    if tr_v >= 0.5:
        det += f' Incluye {mm(tr_v)} transferidos a Aguas y Aseo y al hospital, que esas entidades contratan a su vez por régimen especial.'
    det += ' Sobrecosto probable: 10 % (rango 5–15 %). No prueba corrupción: mide el precio de renunciar a la competencia.'
    if pid == '2004-2007':
        det = 'Solo hay 41 contratos de la alcaldía en SECOP, todos de 2007. ' + det
    if pid == '2008-2011':
        det += ' SECOP está subregistrado en estos años (39 a 205 contratos por año): la base real fue mayor.'
    if pid == '2020-2023':
        det += ' En 8 de los 9 procesos competitivos con dato hubo un solo oferente; la EDU concentró el 40 % del valor.'
    if pid == '2024-2027':
        det += ' 71 de 102 procesos competitivos tuvieron un solo oferente. Datos de 2024 a octubre de 2026.'
    fugas.append(fuga('sobrecosto_sin_competencia', base * SOBRECOSTO['central'], base * SOBRECOSTO['min'], base * SOBRECOSTO['max'], det, citems,
                      [F_FUGAS, URL_SECOP] + [x['url'].split(' ;')[0] for x in LIT_SOBRECOSTO[:3]],
                      base_hecho=r1(base), valor_sin_competencia_hecho=r1(sincomp), pct_valor_sin_competencia=r1(pct_sc)))

    # --- E. nómina paralela OPS ----------------------------------------------
    ex = {'central': 0.0, 'min': 0.0, 'max': 0.0}
    oitems = []
    ops_n = ops_val = form_n = form_v = 0
    for a in sec_anios:
        r = SECOP_ALC[a]
        v = a26(r['ops']['valor'], a)
        ops_n += r['ops']['n']
        ops_val += v
        form_n += r['ops']['formulacion_n']
        form_v += a26(r['ops']['formulacion_valor'], a)
        if not r['ops']['n']:
            continue
        e_c = max(0.0, v - OPS_REF['mediana'] * POB[a] / 1e6)
        ex['central'] += e_c
        ex['min'] += max(0.0, v - OPS_REF['p75'] * POB[a] / 1e6)
        ex['max'] += max(0.0, v - OPS_REF['p25'] * POB[a] / 1e6)
        pers = IND['ops_personas']['serie'].get(str(a))
        if e_c > 0:
            oitems.append({'nombre': f"OPS {a}: {r['ops']['n']} contratos{f', {fmt(pers)} personas' if pers else ''}, {mm(v)} ({fmt(v * 1e6 / POB[a])} pesos de 2026 por habitante)",
                           'anio': a, 'valor': r1(e_c), 'fuente': f'{F_FUGAS} (por_anio, Alcaldía, ops); población DANE en {F_PANEL}'})
    det = (f"{fmt(ops_n)} contratos OPS por {mm(ops_val)} de 2026, de ellos {fmt(form_n)} de formulación de proyectos por {mm(form_v)}. "
           f"Referencia: {fmt(OPS_REF['mediana'])} pesos de 2026 por habitante al año (mediana 2012–2025; rango {fmt(OPS_REF['p25'])}–{fmt(OPS_REF['p75'])}).") if sec_anios else ''
    if pid == '2004-2007':
        det = 'SECOP no registra OPS de la alcaldía en estos años. Sin dato.'
    if pid == '2024-2027':
        det += ' 2026 va hasta octubre.'
    if pid == '2012-2015':
        det += ' Las OPS pasaron de 91 contratos en 2008–2011 a 1.862: la nómina paralela se volvió estructural.'
    fugas.append(fuga('ops_nomina_paralela', ex['central'], ex['min'], ex['max'], det, oitems, [F_FUGAS, URL_SECOP, 'Corte Constitucional, Sentencia C-614 de 2009'],
                      sin_dato=(pid == '2004-2007'), ops_contratos=ops_n, ops_valor=r1(ops_val), ops_formulacion_contratos=form_n, ops_formulacion_valor=r1(form_v)))

    # --- F. recaudo propio ------------------------------------------------
    rc = RECAUDO[pid]
    med = rc['predial']['mediana_7']['dejado_de_recaudar_mm_2026'] + rc['ica']['mediana_7']['dejado_de_recaudar_mm_2026']
    p75_pred = rc['predial']['p75_7']['dejado_de_recaudar_mm_2026']
    p75_ica = rc['ica']['p75_7']['dejado_de_recaudar_mm_2026']
    anios_cat = [a for a in anios if 2021 <= a <= 2023] if pid == '2020-2023' else ([2024] if pid == '2024-2027' else [])
    cat_v = CATASTRO['adicional_anual_mm_2026'] * len(anios_cat)
    mx = max(p75_pred, cat_v) + p75_ica
    dif = rc['predial']['mediana_7']['diferencia_mm_2026'] + rc['ica']['mediana_7']['diferencia_mm_2026']
    det = f"Frente a la mediana de 7 comparables Yondó recaudó {mm(-dif)} más en predial e ICA (pesos de 2026): no hay rezago. "
    if p75_pred + p75_ica > 0 or cat_v:
        det += 'Máximo: ' + ' y '.join(x for x in [f'brecha con el percentil 75 de los comparables ({mm(p75_pred + p75_ica)})' if p75_pred + p75_ica > 0 else '',
                                                  f"predial con catastro actualizado ({mm(cat_v)} en {len(anios_cat)} año{'s' if len(anios_cat) > 1 else ''})" if cat_v else ''] if x) + '.'
    else:
        det += 'Tampoco hay brecha frente al percentil 75.'
    if pid == '2024-2027':
        det += ' Solo 2024 tiene dato comparable; en 2025 el predial subió a $3.044 M (CUIPO).'
    det += ' La extracción de petróleo no paga ICA por ley (art. 16 del Código de Petróleos; art. 39 de la Ley 14 de 1983): no es recaudo perdido.'
    fugas.append(fuga('recaudo_no_cobrado', med, 0, mx, det, [], [F_CNH + ' (recaudo_potencial)', 'https://terridata.dnp.gov.co']))

    # --- G. tasa retributiva --------------------------------------------------
    tv = sum(TASA[a]['tasa_fr1_mm_2026'] for a in anios if a in TASA)
    fac = TASA_INFO['anual_2026_por_caudal_medido_fr1_mm'][1] / TASA_INFO['anual_2026_fr1_mm']
    det = (f"Yondó no tiene PTAR: en 2019 vertía 55,34 L/s sin tratar (Superservicios, 2020). Tasa estimada con factor regional 1; con el caudal medido sería hasta {fmt(fac, 2)} veces. "
           "En 2020 Aguas y Aseo debía $175 M a Corantioquia por tasas desde 2018 (hecho).") if tv else ''
    fugas.append(fuga('costo_vertimientos', tv, tv, tv * fac, det, [], [F_CNH + ' (aguas_residuales)',
                      'https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf']))

    # --- H. fondos externos no gestionados -------------------------------------
    fitems, flist = [], []
    oxi = FONDOS['OXI']
    f_oxi = statistics.mean(IPC[a] for a in range(2018, 2026))
    def add_fondo(clave, nombre, c, mn_, mx_, comparable, suma=True, desde=None, nota=None):
        f = FONDOS[clave]
        flist.append({'fondo': nombre, 'desde': desde or f['desde'], 'monto_referencia': r1(c), 'min': r1(mn_), 'max': r1(mx_),
                      'comparable': comparable, 'fuente': '; '.join(f.get('evidencia', [])[:2]) + f'; {F_SGR}', 'suma_en_total': suma,
                      **({'nota': nota} if nota else {})})
        if suma:
            fitems.append({'nombre': nombre, 'anio': None, 'valor': r1(c), 'min': r1(mn_), 'max': r1(mx_), 'fuente': '; '.join(f.get('evidencia', [])[:1]) + f'; {F_SGR}'})
    if pid == '2008-2011':
        f = FONDOS['ADAPTACION']
        add_fondo('ADAPTACION', 'Fondo Adaptación (ola invernal 2010–2011)', 0, 0, f['monto_referencia_max'] / 1e6 / IPC[2015],
                  'Puerto Nare, ribereño y de tamaño parecido, recibió $1.671 M en 7 intervenciones; Yondó, $30 M en 2. Baja certeza: no se verificó que Yondó registrara daños.')
    if pid in ('2016-2019', '2020-2023'):
        add_fondo('OXI', 'Obras por Impuestos (proyecto vial propio con una empresa, como Ecopetrol)', oxi['monto_referencia_min'] / 1e6 / f_oxi,
                  oxi['monto_referencia_min'] / 2 / 1e6 / f_oxi, oxi['monto_referencia_max'] / 2 / 1e6 / f_oxi,
                  'Entre 2018 y 2023 Yondó, con Ecopetrol operando en su territorio, solo tuvo un proyecto de dotación escolar en 2019 ($1.169 M); Cantagallo tuvo uno propio de $5.333 M. En 2024 llegó la vía El Paraíso–La Raya–Las Lomas ($52.237 M).',
                  desde=2018)
    if pid == '2020-2023':
        f = FONDOS['MINTIC']
        add_fondo('MINTIC', 'MinTIC – Centros Digitales rurales', f['monto_referencia_central'] / 1e6 / IPC[2023], f['monto_referencia_min'] / 1e6 / IPC[2023],
                  f['monto_referencia_max'] / 1e6 / IPC[2023], 'Yondó tiene 4 sedes conectadas; Remedios y San Pablo, 18; Cantagallo, 12 (corte oct-2023).')
    if pid in ('2012-2015', '2016-2019', '2020-2023', '2024-2027'):
        f = FONDOS['COOPERACION']
        add_fondo('COOPERACION', 'Cooperación internacional no reembolsable', f['monto_referencia_min'] / 1e6 / IPC[2024], 0, f['monto_referencia_max'] / 1e6 / IPC[2024],
                  'En el registro de APC solo aparece una donación de Japón para Yondó (2014, US$106.715); la Unión Europea financió proyectos en 5 municipios del Sur de Bolívar (2016, US$1,68 M). Baja certeza.')
    if pid == '2024-2027':
        f = FONDOS['OCAD_PAZ']
        add_fondo('OCAD_PAZ', 'OCAD Paz – Asignación para la Paz (municipios PDET)', f['monto_referencia_central'] / 1e6 / statistics.mean([IPC[2025], IPC[2026]]),
                  0, f['monto_referencia_max'] / 1e6 / statistics.mean([IPC[2025], IPC[2026]]),
                  'En 2025–2026 el OCAD Paz aprobó $37.669 M para Yondó y $99.346 M para Cantagallo; la central es la mediana de los pares del Sur de Bolívar menos lo de Yondó. Todavía se puede gestionar.')
        f = FONDOS['FENOGE']
        add_fondo('FENOGE', 'FENOGE – hospital o sedes públicas con solar', (f['monto_referencia_min'] + f['monto_referencia_max']) / 2 / 1e6 / IPC[2025],
                  f['monto_referencia_min'] / 1e6 / IPC[2025], f['monto_referencia_max'] / 1e6 / IPC[2025],
                  'En 2025 FENOGE dejó autosuficiente con 230 kWp el hospital de Simití, en la misma subregión PDET ($3.152 M). En Yondó no se halló ningún proyecto.')
    if pid in ('2020-2023', '2024-2027'):
        f = FONDOS['FINDETER']
        flist.append({'fondo': 'Findeter – crédito con tasa compensada', 'desde': f['desde'], 'monto_referencia': r1(f['monto_referencia_min'] / 1e6 / IPC[2024]),
                      'min': r1(f['monto_referencia_min'] / 1e6 / IPC[2024]), 'max': r1(f['monto_referencia_max'] / 1e6 / IPC[2024]),
                      'comparable': 'Capacidad de crédito prudente (20–40 % de los ingresos corrientes de 2024); Yondó no pagó intereses de deuda en 2020–2024. Es crédito: no se suma.',
                      'fuente': f'data/fuentes/serie_fiscal_oec.csv; {F_SGR}', 'suma_en_total': False})
    if pid in ('2020-2023', '2024-2027'):
        f = FONDOS['INCENTIVO']
        flist.append({'fondo': 'Incentivo a la Producción del SGR (línea "Territorios energéticos", hasta $8.000 M)', 'desde': f['desde'],
                      'monto_referencia': r1((f['yondo_obtuvo']['incentivos_al04_sin_usar_inicio_2023'] / 1e6 / IPC[2022]) if pid == '2020-2023' else f['yondo_obtuvo']['saldo_sin_aprobar'] / 1e6),
                      'comparable': ('Incentivos del Acto Legislativo 04 de 2017: $4.079 M corrientes pasaron sin usar a 2021–2022 y $3.687 M a 2023–2024. Ya era plata de Yondó: se cuenta en "saldos de regalías".'
                                     if pid == '2020-2023' else
                                     'San Pablo aprobó el 83 % de su bolsa 2025–2026, Cantagallo el 43 % y Remedios el 37 %; Yondó el 2,4 %. Ya es plata de Yondó: se cuenta en "saldos de regalías".'),
                      'fuente': f'https://www.datos.gov.co/d/e624-d9uy; {F_SGR}', 'suma_en_total': False})
    fv = sum(i['valor'] for i in fitems)
    fmn = sum(i['min'] for i in fitems)
    fmx = sum(i['max'] for i in fitems)
    det = {'2004-2007': 'Sin fondos comparables identificados para estos años.',
           '2008-2011': 'Fondo Adaptación con central cero: depende de daños de 2010–2011 que no se verificaron.',
           '2012-2015': 'Solo cooperación internacional, con baja certeza.',
           '2016-2019': 'Obras por Impuestos empezó en 2018; Yondó, con Ecopetrol en su territorio, no tuvo un proyecto vial propio hasta 2024.',
           '2020-2023': 'En el OCAD Paz Yondó sí consiguió plata (el problema fue ejecutarla). Lo que faltó fue Obras por Impuestos viales y Centros Digitales.',
           '2024-2027': 'Periodo en curso: el OCAD Paz y FENOGE todavía se pueden gestionar antes de 2027.'}[pid]
    fugas.append(fuga('fondos_no_gestionados', fv, fmn, fmx, det + ' Findeter no se suma (es crédito).' if pid in ('2020-2023', '2024-2027') else det,
                      fitems, [F_SGR], sin_dato=not fitems))

    # --- I. ahorro solar no capturado ---------------------------------------
    s = SOLAR.get(pid)
    if s:
        c = s['solo_solar']['central']
        rng = s['solo_solar']['rango_neto_con_residual']
        neto = c['neto_hasta_2026_con_valor_residual'] / 1e6
        valor = max(0.0, neto)
        det = (f"Instalar 469 kWp en {s['anio_instalacion']} costaba {mm(c['inversion_cop_2026'] / 1e6)} de 2026; habría ahorrado {mm(c['ahorro_bruto_hasta_2026'] / 1e6)} en facturas hasta 2026 "
               f"(neto con valor residual: {mm(neto)}" + (f"; se pagaba sola en {c['anio_recuperacion']})." if c.get('anio_recuperacion') else ').'))
        if neto <= 0:
            det += ' No se habría pagado: la solar era unas 7 veces más cara que en 2024. Se registra cero.'
        if pid == '2024-2027':
            det += ' Hoy cada año de espera cuesta unos $566 M en facturas.'
        fugas.append(fuga('ahorro_solar', valor, max(0.0, rng[0] / 1e6), max(0.0, rng[1] / 1e6), det, [], [F_CNH + ' (contrafactual_solar)']))
    else:
        fugas.append(fuga('ahorro_solar', 0, 0, 0, 'No calculado: en 2004–2007 la solar costaba aún más que en 2008, cuando instalarla no se habría pagado.', [], [F_CNH], sin_dato=True))

    # --- J. ahorro de regalías ------------------------------------------------
    fil = [AHORRO[a] for a in anios if a in AHORRO]
    if fil:
        ap_ = sum(f['aporte_mm_2026'] for f in fil)
        v3 = sum(f['valor_2026_r3_mm'] for f in fil)
        v4 = sum(f['valor_2026_r4_mm'] for f in fil)
        det = (f"El 10 % de las regalías directas de estos años era {mm(ap_)} de 2026; guardado al 3–4 % real valdría hoy {mm(v3)} a {mm(v4)}, "
               f"y solo sus rendimientos darían {mm(v3 * 0.03)} a {mm(v4 * 0.04)} al año sin tocar el capital.")
        fugas.append(fuga('ahorro_regalias', v3, ap_, v4, det, [{'nombre': f"Aporte de {f['anio']} (10 % de {mm(f['regalias_giradas_mm_corrientes'])} corrientes)", 'anio': f['anio'],
                                                           'valor': r1(f['valor_2026_r3_mm']), 'fuente': F_CNH + ' (contrafactual_ahorro_regalias)'} for f in fil],
                          [F_CNH + ' (contrafactual_ahorro_regalias)', 'data/fuentes/serie_fiscal_oec.csv']))
    else:
        fugas.append(fuga('ahorro_regalias', 0, 0, 0, 'No aplica: desde 2012 el Sistema General de Regalías ahorra a nivel nacional (Fondo de Ahorro y Estabilización) y el municipio no maneja regalías directas.',
                          [], [F_CNH], sin_dato=True))

    tot = {t: sum(f['valor'] or 0 for f in fugas if f['tipo'] == t) for t in ('hecho', 'estimado', 'contrafactual')}
    return {
        'ingresos': r1(ing), 'inversion': r1(ap['inversion']['suma_mm_2026']), 'regalias': r1(ap['regalias']['suma_mm_2026']),
        'sgp': r1(ap['sgp']['suma_mm_2026']), 'propios': r1(propios),
        'anios_con_dato_plata': anios_plata,
        'fugas': fugas,
        'total_hecho': r1(tot['hecho']), 'total_estimado': r1(tot['estimado']), 'total_contrafactual': r1(tot['contrafactual']),
        'sin_obra': r1(tot['hecho'] + tot['estimado']),
        'sin_obra_rango': [r1(sum((f['min'] if f['min'] is not None else f['valor']) for f in fugas if f['tipo'] != 'contrafactual')),
                           r1(sum((f['max'] if f['max'] is not None else f['valor']) for f in fugas if f['tipo'] != 'contrafactual'))],
        'flist': flist, 'gsa_items': gitems,
    }


# ---------------------------------------------------------------------------
# equivalencias, pudo_hacerse y lectura
# ---------------------------------------------------------------------------
PREFERENCIA = {
    '2004-2007': ['aula_dotada', 'beca_universitaria_anual', 'ambulancia_medicalizada_tam', 'km_placa_huella', 'ptar_12000_hab', 'vis_rural', 'kwp_solar_cubierta'],
    '2008-2011': ['km_placa_huella', 'ptar_12000_hab', 'aula_dotada', 'beca_universitaria_anual', 'vis_rural', 'ambulancia_medicalizada_tam', 'kwp_solar_cubierta'],
    '2012-2015': ['aula_dotada', 'beca_universitaria_anual', 'ptar_12000_hab', 'km_placa_huella', 'vis_rural', 'ambulancia_medicalizada_tam', 'kwp_solar_cubierta'],
    '2016-2019': ['aula_dotada', 'vis_rural', 'km_placa_huella', 'ptar_12000_hab', 'beca_universitaria_anual', 'ambulancia_medicalizada_tam', 'kwp_solar_cubierta'],
    '2020-2023': ['vis_rural', 'ptar_12000_hab', 'km_placa_huella', 'ambulancia_medicalizada_tam', 'aula_dotada', 'beca_universitaria_anual', 'kwp_solar_cubierta'],
    '2024-2027': ['ptar_12000_hab', 'kwp_solar_cubierta', 'ambulancia_medicalizada_tam', 'aula_dotada', 'beca_universitaria_anual', 'km_placa_huella', 'vis_rural'],
}


def equivalencias(pid, valor):
    out = []
    for id_ in PREFERENCIA[pid]:
        n = valor / cu(id_)
        if 1 <= n <= 999:
            out.append({'unidad': UNIDADES[id_], 'n': r1(n), 'costo_unitario': r1(cu(id_)), 'id': id_,
                        'rango_n': [r1(valor / cu_max(id_)), r1(valor / cu_min(id_))], 'certeza_costo': CU[id_]['certeza']})
        if len(out) == 4:
            break
    return out


def item_pudo(que, costo, unidad, por_que_no, fuente, sin_obra, rango=None, extra_eq=None, cubierto=True):
    eq = eq_texto(costo, unidad) if unidad else ''
    if extra_eq:
        eq = f'{eq}; {extra_eq}' if eq else extra_eq
    d = {'que': que, 'costo': r1(costo), 'equivalencia': eq, 'por_que_no': por_que_no, 'fuente': fuente,
         'cubierto_con_plata_sin_obra_pct': r1(min(999.0, 100 * sin_obra / costo)) if costo and cubierto else None}
    if rango:
        d['costo_rango'] = [r1(rango[0]), r1(rango[1])]
    return d


PTAR_FUENTE = (f"{F_CNH} (costos_unitarios: ptar_12000_hab, PTAR de Tenjo, Corozal y Salónica indexadas); Superservicios 2020: "
               "https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf")


def pudo_hacerse(pid, c):
    so = c['sin_obra']
    F = {f['categoria']: f for f in c['fugas']}
    ptar = cu('ptar_12000_hab')
    rngp = [cu_min('ptar_12000_hab'), cu_max('ptar_12000_hab')]
    global PTAR_EQ
    PTAR_EQ = f"1 PTAR (costo entre {mm(rngp[0])} y {mm(rngp[1])}; sin colectores)"
    sol = SOLAR.get(pid)
    out = []
    if pid == '2004-2007':
        ah = F['ahorro_regalias']
        out.append(item_pudo('PTAR para el casco urbano (unos 12.000 habitantes)', ptar, None,
                             f"El plan 2005–2007 se apoyó en un Plan Maestro de Acueducto y Alcantarillado, pero la planta no se construyó; en 2019 Yondó vertía 55 L/s sin tratar. El 10 % de las regalías de estos cuatro años ({mm(ah['min'])} de 2026) alcanzaba para pagarla.",
                             PTAR_FUENTE + f'; {F_GOB}', so, rngp, extra_eq=PTAR_EQ))
        out.append(item_pudo('Fondo local de ahorro con el 10 % de las regalías directas', ah['min'], None,
                             'Ninguna norma obligaba a ahorrar regalías directas y no se creó un fondo local, aunque las regalías eran el 56 % de los ingresos.',
                             F_CNH + ' (contrafactual_ahorro_regalias)', so, extra_eq=f"hoy valdría {mm(ah['valor'])} (3 % real) {eq_texto(ah['valor'], 'aula_dotada')}", cubierto=False))
        out.append(item_pudo('10 aulas dotadas para ampliar la educación media', 10 * cu('aula_dotada'), 'aula_dotada',
                             'La cobertura neta en media era de 14 %: 86 de cada 100 jóvenes de 15–16 años no estaban matriculados en media.',
                             f"{F_CNH} (aula_dotada); docs/02-marco-comparativo-2004-2027.md (matriz, MEN)", so, [10 * cu_min('aula_dotada'), 10 * cu_max('aula_dotada')]))
    elif pid == '2008-2011':
        ah = F['ahorro_regalias']
        out.append(item_pudo('Vía Yondó–Puerto Berrío en placa huella (71 km, meta del plan 2008–2011)', 71 * cu('km_placa_huella'), 'km_placa_huella',
                             f"La vía siguió sin pavimentar (sin avance según la Gobernación en mayo de 2025). La plata sin obra de este gobierno ({mm(so)}) alcanzaba para unos {fmt(so / cu('km_placa_huella'))} km.",
                             f"{F_CNH} (km_placa_huella); {F_GOB}", so, [71 * cu_min('km_placa_huella'), 71 * cu_max('km_placa_huella')]))
        out.append(item_pudo('Fondo local de ahorro con el 10 % de las regalías, en su máximo histórico', ah['min'], None,
                             'Con regalías en máximos no se creó un ahorro ni una base económica distinta al petróleo.',
                             F_CNH + ' (contrafactual_ahorro_regalias); ' + F_GOB, so, extra_eq=f"hoy valdría {mm(ah['valor'])} {eq_texto(ah['valor'], 'ptar_12000_hab')}", cubierto=False))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             'Siguió pendiente: el plan priorizó vías y redes, y las aguas residuales se siguieron vertiendo sin tratar.', PTAR_FUENTE, so, rngp, extra_eq=PTAR_EQ))
    elif pid == '2012-2015':
        ciud = a26(7090e6, 2016)
        out.append(item_pudo('Ciudadela Educativa (diseñada en 2014 por $300 M)', ciud, 'aula_dotada',
                             'Se diseñó en 2014 y la obra quedó suspendida en el periodo siguiente. Costo: lo previsto en el plan 2016–2019 ($7.090 M de 2016).',
                             f"{F_GOB}; SECOP https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=14-15-2238279", so))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             'Siguió pendiente, y los estudios de acueductos rurales de 2013 ($1.159 M) tampoco tienen obra posterior identificable.', PTAR_FUENTE, so, rngp, extra_eq=PTAR_EQ))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2012', ci['inversion_cop_2026'] / 1e6, None,
                                 f"No se hizo. Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)} netos.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
        out.append(item_pudo('400 becas universitarias de un año (100 por año) para bachilleres', 400 * cu('beca_universitaria_anual'), 'beca_universitaria_anual',
                             f"La cobertura neta en media era de 21,5 %; mientras tanto las OPS pasaron de 91 a 1.862 contratos ({mm(F['ops_nomina_paralela']['valor'])} por encima de lo usual).",
                             f"{F_CNH} (beca_universitaria_anual, supuesto); {F_GOB}", so))
    elif pid == '2016-2019':
        ciud = a26(7090e6, 2016)
        out.append(item_pudo('Terminar la Ciudadela Educativa', ciud, 'aula_dotada', 'Tenía $7.090 M en el plan 2016–2019 y siguió sin terminar.', F_GOB, so))
        lapaz = a26(13336e6, 2019)
        out.append(item_pudo('Vivienda para reubicar el barrio La Paz', lapaz, 'vis_urbana', 'Empezó en 2019 y seguía en ejecución en 2026.', F_GOB, so))
        oxi = FONDOS['OXI']['monto_referencia_min'] / 1e6 / statistics.mean(IPC[a] for a in range(2018, 2026))
        out.append(item_pudo('Una vía terciaria por Obras por Impuestos con una empresa del territorio', oxi, 'km_placa_huella',
                             'Obras por Impuestos empezó en 2018; Yondó no tuvo proyectos viales propios en el banco de la ART (solo uno de dotación escolar en 2019, $1.169 M).',
                             '; '.join(FONDOS['OXI']['evidencia'][:1]) + f'; {F_SGR}', so))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2016', ci['inversion_cop_2026'] / 1e6, None,
                                 f"La Ley 1715 de 2014 ya daba incentivos. Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)} netos.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
    elif pid == '2020-2023':
        viv = sum(i['valor'] for i in c['gsa_items'] if i['bpin'] in ('2022003050005', '2022003050034'))
        out.append(item_pudo('Terminar las viviendas contratadas con la EDU (dos proyectos de regalías)', viv, 'vis_rural',
                             'Al cierre del periodo iban en 9 % y 17 % de obra con 88 % y 89 % de los recursos girados; el DNP alertó en agosto de 2024 alto riesgo de pérdida. Costo: lo girado sin avance equivalente.',
                             f'{F_SGR} (BPIN 2022003050034 y 2022003050005); docs/01-diagnostico-sectorial.md', so))
        ye = sum(i['valor'] for i in c['gsa_items'] if i['bpin'] == '20201301010644')
        out.append(item_pudo('Terminar el corredor Ye de Marley–San Francisco (OCAD Paz)', ye, 'km_placa_huella',
                             '61 % de obra con 90 % de los recursos pagados. Costo: lo girado sin avance equivalente.', f'{F_SGR} (BPIN 20201301010644)', so))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             'Se adoptó el EOT 2022–2035, pero no hay PTAR; la canalización de colectores de las estaciones de bombeo sigue en formulación ($67.640 M, BPIN 20201301010649).',
                             PTAR_FUENTE, so, rngp, extra_eq=PTAR_EQ))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2020', ci['inversion_cop_2026'] / 1e6, None,
                                 f"Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)} netos; FENOGE y la convocatoria de incentivos la podían financiar.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
        md = FONDOS['MINTIC']
        out.append(item_pudo('Centros Digitales en 10 sedes rurales más (MinTIC)', md['monto_referencia_central'] / 1e6 / IPC[2023], None,
                             'Yondó tiene 4 sedes conectadas, todas en San Miguel del Tigre; sus vecinos, entre 9 y 18.', '; '.join(md['evidencia'][:1]) + f'; {F_SGR}', so,
                             extra_eq='≈ 10 sedes educativas rurales con internet'))
    elif pid == '2024-2027':
        sal = F['saldos_regalias']['valor']
        out.append(item_pudo('Aprobar antes de diciembre de 2026 las regalías que ya están asignadas a Yondó', sal, 'ptar_12000_hab',
                             'Aún se puede: a octubre de 2026 siguen sin aprobar asignaciones directas, el Incentivo a la Producción y la inversión local del bienio 2025–2026.',
                             f'https://www.datos.gov.co/d/e624-d9uy (corte oct-2026); {F_SGR}', so))
        out.append(item_pudo('Red Energética Pública: solar en 13 sedes, baterías en 7 sedes críticas y control (proyecto 1)', 7204, None,
                             'Aún se puede: cabe en la línea "Territorios energéticos" (hasta $8.000 M). El único proyecto de energía presentado en 2025 no cumplió requisitos; cada año de espera cuesta unos $566 M en facturas.',
                             'docs/07-portafolio-presupuesto.md; docs/05-microrred-domotica-mintic.md; ' + F_CNH, so,
                             extra_eq='469 kWp solares en cubiertas y 770 kWh de baterías; compra 57 % menos energía'))
        out.append(item_pudo('Terminar los estudios del Plan Maestro y construir la PTAR del casco urbano', 1800 + ptar, 'ptar_12000_hab',
                             'Aún se puede empezar: los estudios del Plan Maestro ($2.898 M, 56 %) están "inactivos"; terminarlos cuesta unos $1.800 M y son requisito de la PTAR.',
                             'docs/07-portafolio-presupuesto.md; ' + PTAR_FUENTE, so, [1800 + rngp[0], 1800 + rngp[1]]))
        out.append(item_pudo('Hospital seguro, verde e inteligente (red eléctrica, telesalud, ambulancia medicalizada, puesto rural)', 8100, 'ambulancia_medicalizada_tam',
                             'Aún se puede: la red eléctrica del hospital ($5.483 M) está en formulación desde 2017; la ventana de financiación es 2027–2029.',
                             'docs/06-hospital-2028-financiacion.md; docs/07-portafolio-presupuesto.md', so))
        gsa_prev = sum(f['valor'] for f in [x for x in RESULTADOS['2020-2023']['fugas'] if x['categoria'] == 'girado_sin_avance'])
        out.append(item_pudo('Auditoría técnica y plan de terminación de las obras con brecha', 600, None,
                             f"Aún se puede: busca recuperar o terminar {mm(gsa_prev)} de regalías girados sin avance equivalente en proyectos aprobados en 2020–2023.",
                             'docs/07-portafolio-presupuesto.md; ' + F_SGR, so, extra_eq=f"protege {mm(gsa_prev)} ya girados"))
    return out


def lectura(pid, c):
    F = {f['categoria']: f for f in c['fugas']}
    eqs = c['equivalencias']
    eq1 = f"{fmt(eqs[0]['n'], 1 if eqs[0]['n'] < 10 else 0)} {eqs[0]['unidad']}" if eqs else ''
    so, ing = c['sin_obra'], c['ingresos']
    if pid == '2004-2007':
        return (f"Entraron {mm(ing)} de 2026, el {fmt(100 * c['regalias'] / ing)} % por regalías. SECOP casi no tiene contratos de estos años, así que solo se estimaron {mm(so)} sin obra: "
                f"no es que no haya habido fugas, es que no hay cómo verlas. La oportunidad más clara fue no ahorrar: el 10 % de esas regalías valdría hoy {mm(F['ahorro_regalias']['valor'])}, casi dos PTAR.")
    if pid == '2008-2011':
        return (f"Fue el gobierno con más regalías del régimen anterior: entraron {mm(ing)} de 2026. En los pocos contratos que registró SECOP hay {mm(so)} sin obra o en sobrecosto probable "
                f"(≈ {eq1}). Si hubiera guardado el 10 % de las regalías, hoy Yondó tendría {mm(F['ahorro_regalias']['valor'])}, y la vía a Puerto Berrío siguió sin pavimentar.")
    if pid == '2012-2015':
        return (f"Entraron {mm(ing)} de 2026. Hay {mm(so)} que no se convirtieron en obra según los registros y las estimaciones, sobre todo por la nómina paralela: "
                f"{mm(F['ops_nomina_paralela']['valor'])} en OPS por encima de lo usual y {mm(F['estudios_sin_obra']['valor'])} en estudios sin obra, como los de la Ciudadela Educativa. "
                f"Con esa plata alcanzaba para {eq1}.")
    if pid == '2016-2019':
        return (f"Entraron {mm(ing)} de 2026 y fue el gobierno que más contrató con competencia (69 % del valor). Aun así quedan {mm(so)} sin obra: "
                f"{mm(F['saldos_regalias']['valor'])} de regalías sin comprometer al cierre de 2016 y {mm(F['ops_nomina_paralela']['valor'] + F['sobrecosto_sin_competencia']['valor'])} entre OPS y sobrecosto probable. "
                f"La Ciudadela Educativa y la vivienda de La Paz siguieron sin terminar.")
    if pid == '2020-2023':
        return (f"Entraron {mm(ing)} de 2026 y se invirtió más que nunca, pero {mm(c['total_hecho'])} quedaron registrados sin convertirse en obra: {mm(F['girado_sin_avance']['valor'])} de regalías "
                f"pagados por encima del avance de vivienda y vías, casi todo en proyectos delegados en la EDU de Medellín. Con el 82 % contratado sin competencia, el sobrecosto probable suma "
                f"{mm(F['sobrecosto_sin_competencia']['valor'])}; en total, {mm(so)} alcanzaban para {eq1}.")
    if pid == '2024-2027':
        return (f"Periodo en curso (datos parciales a octubre de 2026). Lo más grande no es plata perdida sino plata quieta: {mm(F['saldos_regalias']['valor'])} de regalías asignadas a Yondó "
                f"siguen sin aprobar y el bienio cierra en diciembre de 2026. Con eso y con fondos aún disponibles (OCAD Paz, FENOGE) se pueden financiar la red solar pública, el hospital y los estudios de la PTAR.")
    return ''


# ---------------------------------------------------------------------------
# armado
# ---------------------------------------------------------------------------
RESULTADOS = {}
periodos = []
for g in GOB['periodos']:
    pid = g['id']
    c = calcular_periodo(pid)
    RESULTADOS[pid] = c
for g in GOB['periodos']:
    pid = g['id']
    c = RESULTADOS[pid]
    c['equivalencias'] = equivalencias(pid, c['sin_obra'])
    per = {
        'id': pid, 'alcalde': g['alcalde'],
        'en_curso': pid == '2024-2027',
        'ingresos': c['ingresos'], 'inversion': c['inversion'], 'regalias': c['regalias'], 'sgp': c['sgp'], 'propios': c['propios'],
        'anios_con_dato_plata': c['anios_con_dato_plata'],
        'fugas': c['fugas'],
        'total_hecho': c['total_hecho'], 'total_estimado': c['total_estimado'], 'total_contrafactual': c['total_contrafactual'],
        'sin_obra': c['sin_obra'], 'sin_obra_rango': c['sin_obra_rango'],
        'sin_obra_pct_ingresos': r1(100 * c['sin_obra'] / c['ingresos']) if c['ingresos'] and pid != '2024-2027' else None,
        'pudo_hacerse': pudo_hacerse(pid, c),
        'equivalencias': c['equivalencias'],
        'fondos_no_gestionados': c['flist'],
        'lectura': lectura(pid, c),
    }
    if pid == '2024-2027':
        per['nota'] = ('Periodo en curso. Ingresos, inversión, regalías, SGP e impuestos propios solo tienen 2024 completo (operaciones de caja del DNP); '
                       'la contratación va de enero de 2024 al 20 de octubre de 2026 y los saldos de regalías tienen corte de octubre de 2026.')
    if pid == '2004-2007':
        per['nota'] = 'SECOP casi no tiene registros de estos años (41 contratos de la alcaldía en 2007): un cero aquí es "sin dato", no "sin fugas".'
    if pid == '2008-2011':
        per['nota'] = 'SECOP está subregistrado (39 a 205 contratos de la alcaldía por año, frente a más de 400 desde 2012): las cifras de contratación son un piso.'
    periodos.append(per)


def totales_por_categoria():
    filas = []
    for cat in CATEGORIAS:
        fila = {'categoria': cat['id'], 'nombre': cat['nombre'], 'tipo': cat['tipo'], 'por_periodo': {}}
        for p in periodos:
            f = next(x for x in p['fugas'] if x['categoria'] == cat['id'])
            fila['por_periodo'][p['id']] = f['valor']
        sumable = cat['id'] not in ('saldos_regalias', 'ahorro_solar')
        fila['sumable_entre_gobiernos'] = sumable
        fila['total_2004_2026'] = r1(sum(v or 0 for v in fila['por_periodo'].values())) if sumable else None
        if not sumable:
            fila['nota'] = ('Son fotos de saldos en fechas distintas: parte de la plata pudo pasar de un gobierno al siguiente.' if cat['id'] == 'saldos_regalias'
                            else 'Cada gobierno es un escenario alternativo (instalar en 2012, o en 2016, o en 2020…): no se suman.')
        filas.append(fila)
    return filas


TOTALES = totales_por_categoria()

METODO = (
    'Para cada gobierno se suma la plata que no se convirtió en obra en tres niveles de certeza. Hecho: registros oficiales verificables (regalías pagadas por encima del avance físico '
    'en GESPROY y saldos de regalías sin aprobar o sin comprometer en CHIP, SICODIS y MinHacienda). Estimado: cálculos con método y rango sobre registros oficiales (estudios sin obra '
    'posterior en SECOP, sobrecosto probable por contratar sin competencia, OPS por encima de lo usual, recaudo y tasa retributiva). Contrafactual: lo que pudo pasar con otra decisión '
    '(fondos externos no gestionados, ahorro solar y ahorro de regalías); no es plata perdida. Todo va en millones de pesos de 2026: cada valor se deflacta con el IPC del DANE del año '
    'en que ocurrió (panel_anual.json). Para no contar dos veces la misma plata: (1) los contratos mixtos de diseño y obra no entran en estudios sin obra; (2) a la base del sobrecosto '
    'se le restan las OPS, las transferencias a Aguas y Aseo y al hospital, los estudios sin obra y la plata girada sin avance; (3) de los saldos se toma un solo corte por gobierno; '
    '(4) los saldos del Incentivo a la Producción y de la inversión local cuentan como saldos (hecho) y no como fondos no gestionados; (5) Findeter no se suma por ser crédito; '
    '(6) los proyectos de regalías hechos con la EDU se cuentan una vez, como plata girada sin avance. "Sin obra" = hecho + estimado; las equivalencias dividen ese valor por el costo '
    'unitario de 2026. Ninguna cifra señala a personas: describe hechos y oportunidades perdidas.'
)

LIMITACIONES = [
    'SECOP casi no tiene contratos de Yondó antes de 2011 (41 de la alcaldía en 2007 y entre 39 y 205 por año en 2008–2011): para 2004–2011 los ceros son "sin dato" y las cifras de contratación son un piso.',
    'La coincidencia estudio → obra se hace por palabras del objeto: hay falsos negativos (obras hechas por la Gobernación, Ecopetrol, Findeter o la EDU con otras palabras) y falsos positivos. Es una agenda de verificación.',
    'El sobrecosto por contratar sin competencia es una estimación con rango tomado de estudios de otros países y de Colombia; no hay una medición directa de precios para Yondó. Contratar directamente es legal en muchos casos (convenios interadministrativos, OPS, régimen especial).',
    'Hay 24 registros de SECOP de $100 M o más que parecen duplicados (12 de más por $11.677 M corrientes). El único ubicado en los datos publicados de la alcaldía ($5.407 M en 2020, con Aguas y Aseo) se resta de la base del sobrecosto. Los demás ($6.270 M) no se pueden ubicar por año con fugas_secop.json; si fueran de la alcaldía y sin competencia, el sobrecosto central total bajaría a lo sumo unos $630 M corrientes.',
    'La referencia de OPS es interna (el propio Yondó en un año típico 2012–2025): mide cuánto se alejó cada gobierno de lo usual, no un estándar nacional, que no existe en datos abiertos. Un cambio en cómo se registraron las OPS en SECOP II puede afectar la comparación.',
    'Plata girada sin avance solo existe para proyectos de regalías (GESPROY). Para la plata propia y para los convenios con la EDU no hay datos abiertos de avance físico ni de pagos (SECOP I no publica pagos; los anticipos solo constan en el expediente).',
    'GESPROY y MapaInversiones no coinciden en varios proyectos (ver alertas_datos en sgr_fondos.json); se usa GESPROY. Los proyectos aprobados en 2015, 2019 y 2023 pudieron aprobarse a comienzos del año siguiente (bienios compartidos).',
    'Los saldos de regalías no son plata perdida: en el SGR pasan al bienio siguiente. Miden plata disponible que no se volvió obra a tiempo, y no se suman entre gobiernos.',
    'Los fondos externos son contrafactuales con certeza variable (Fondo Adaptación y cooperación, baja); dependen de convocatorias, de terceros (empresas en Obras por Impuestos) y de proyectos bien formulados.',
    'Los costos unitarios se indexan con el IPC; los costos de construcción subieron más que el IPC en 2021–2023, así que algunas equivalencias pueden quedar altas (cuentan más obras de las que alcanzarían).',
    'El periodo 2024–2027 está en curso: ingresos solo de 2024, contratación hasta el 20 de octubre de 2026 y saldos a octubre de 2026.',
    'Las cifras de este archivo heredan las limitaciones de sus insumos: panel_anual.json, fugas_secop.json, sgr_fondos.json y costo_no_hacer.json.',
]

NOTAS_LEGALES = [
    'Este análisis describe hechos registrados y oportunidades perdidas. No acusa a ninguna persona: una investigación no es una condena y toda persona se presume inocente mientras no se le declare culpable (Constitución Política, art. 29).',
    'Solo se nombra a los alcaldes, como responsables políticos de cada periodo. No se publican nombres ni documentos de personas naturales contratistas ni de otros funcionarios (Ley 1581 de 2012, protección de datos personales).',
    'La contratación directa es legal en los casos que prevé la ley: prestación de servicios y apoyo a la gestión y convenios interadministrativos (Ley 1150 de 2007, art. 2, num. 4), convenios con entidades sin ánimo de lucro (Decreto 092 de 2017) y régimen especial de las empresas de servicios públicos (Ley 142 de 1994, art. 31) y de las E.S.E. (Ley 100 de 1993, art. 195). El sobrecosto estimado mide el costo probable de no competir, no una ilegalidad.',
    'Los contratos de prestación de servicios no pueden usarse para funciones permanentes de la entidad (Ley 80 de 1993, art. 32, num. 3; Corte Constitucional, Sentencia C-614 de 2009). El exceso de OPS frente a lo usual es un indicio que debe contrastarse con la planta de personal.',
    'Los saldos de regalías no se pierden: lo no ejecutado pasa al bienio siguiente (Ley 2056 de 2020). Se muestran como plata que no se convirtió en obra a tiempo.',
    'La explotación de petróleo no es base del ICA municipal (Decreto 1056 de 1953, Código de Petróleos, art. 16; Ley 14 de 1983, art. 39): no se cuenta como recaudo dejado de cobrar.',
    'Las alertas de órganos de control (DNP, Procuraduría, Contraloría, Fiscalía) se citan en data/gobiernos.json con su estado procesal; este archivo no las usa para calcular montos.',
]

COSTOS_UNITARIOS = [{
    'id': id_, 'unidad': UNIDADES.get(id_) or PLURAL_EXTRA.get(id_), 'nombre': CU[id_]['nombre'], 'costo': r1(cu(id_)), 'min': r1(cu_min(id_)), 'max': r1(cu_max(id_)),
    'certeza': CU[id_]['certeza'], 'fuente': CU[id_]['fuente'], 'nota': CU[id_].get('nota'),
} for id_ in list(UNIDADES) + ['vis_urbana']]

salida = {
    'titulo': 'La plata que no se convirtió en obra, por gobierno (Yondó, 2004–2027)',
    'generado_por': 'scripts/build_dinero_no_hecho.py',
    'fecha_corte': CORTE,
    'moneda': 'millones de COP constantes de 2026',
    'deflactor': f"IPC DANE, promedio de cada año; 2026 = promedio ene–sep 2026 (158,284; base dic-2018 = 100). Mismo IPC de {F_PANEL} y {F_CNH}.",
    'metodo': METODO,
    'como_leer': [
        'hecho: registro oficial verificable (con enlace o archivo).',
        'estimado: cálculo con método explícito y rango (min–max).',
        'contrafactual: lo que pudo pasar con otra decisión; no es plata perdida ni una acusación.',
        '"sin_obra" = total_hecho + total_estimado. Los contrafactuales van aparte.',
        'Un valor 0 con "sin_dato": true significa que no hay datos para medirlo, no que no existió.',
        'Los items con "en_total": false son contexto y no se suman al valor de la fuga.',
    ],
    'categorias': CATEGORIAS,
    'literatura_sobrecosto': LIT_SOBRECOSTO,
    'referencia_ops': {'pesos_2026_por_habitante_al_anio': {k: round(v) for k, v in OPS_REF.items()}, 'anios': _ref_years,
                       'serie_pesos_2026_por_habitante': {a: round(OPS_PC[a]) for a in sorted(OPS_PC)},
                       'nota': 'Mediana (central), percentil 75 (mínimo de exceso) y percentil 25 (máximo de exceso) del gasto anual en OPS de la alcaldía por habitante, 2012–2025.'},
    'periodos': periodos,
    'totales_por_categoria': TOTALES,
    'costos_unitarios': COSTOS_UNITARIOS,
    'limitaciones': LIMITACIONES,
    'notas_legales': NOTAS_LEGALES,
    'insumos': [F_PANEL, F_FUGAS, F_SGR, F_CNH, F_GOB],
}


# ---------------------------------------------------------------------------
# validación
# ---------------------------------------------------------------------------
def validar(d):
    ids = {c['id'] for c in d['categorias']}
    tipos = {'hecho', 'estimado', 'contrafactual'}
    assert d['moneda'] == 'millones de COP constantes de 2026'
    assert len(d['periodos']) == 6
    for p in d['periodos']:
        for k in ('ingresos', 'inversion', 'regalias', 'sgp', 'propios', 'total_hecho', 'total_estimado', 'total_contrafactual'):
            assert isinstance(p[k], (int, float)), (p['id'], k)
        cats = [f['categoria'] for f in p['fugas']]
        assert set(cats) == ids and len(cats) == len(ids), (p['id'], cats)
        for f in p['fugas']:
            assert f['tipo'] in tipos and isinstance(f['valor'], (int, float)) and f['valor'] >= 0, (p['id'], f['categoria'])
            if f['min'] is not None:
                assert f['min'] <= f['valor'] + 0.11 and f['valor'] <= f['max'] + 0.11, (p['id'], f['categoria'], f['min'], f['valor'], f['max'])
            for it in f['items']:
                assert {'nombre', 'anio', 'valor', 'fuente'} <= set(it), (p['id'], f['categoria'], it)
            if f['valor'] and f['tipo'] != 'contrafactual':
                assert f['fuentes'], (p['id'], f['categoria'])
        for t in tipos:
            s = round(sum(f['valor'] for f in p['fugas'] if f['tipo'] == t), 1)
            assert abs(s - p['total_' + t]) < 0.25, (p['id'], t, s, p['total_' + t])
        assert 1 <= len(p['equivalencias']) <= 4, p['id']
        for e in p['equivalencias']:
            assert abs(e['n'] - p['sin_obra'] / e['costo_unitario']) < 0.2 + 0.01 * e['n'], (p['id'], e)
        for x in p['pudo_hacerse']:
            assert isinstance(x['costo'], (int, float)) and x['que'] and x['fuente'] and x['por_que_no'], (p['id'], x)
        n_frases = p['lectura'].count('. ') + 1
        assert 2 <= n_frases <= 3, (p['id'], n_frases, p['lectura'])
    # coherencia con los insumos
    for p in d['periodos']:
        pp = PANEL_PER[p['id']]['agregados']
        assert abs(p['ingresos'] - pp['ingresos_totales']['suma_mm_2026']) < 1
    return True


def suma_fuga(p, cat):
    return next(f for f in p['fugas'] if f['categoria'] == cat)


# ---------------------------------------------------------------------------
# documento Markdown
# ---------------------------------------------------------------------------
def tabla(filas, cab, alinear):
    out = ['| ' + ' | '.join(cab) + ' |', '|' + '|'.join('---:' if a == 'r' else '---' for a in alinear) + '|']
    out += ['| ' + ' | '.join(str(c) for c in f) + ' |' for f in filas]
    return '\n'.join(out)


def rango(f):
    if f['min'] is None or f['max'] is None or (abs(f['min'] - f['valor']) < 0.05 and abs(f['max'] - f['valor']) < 0.05):
        return '—'
    return f"{fmt(f['min'])}–{fmt(f['max'])}"


def doc_md(d):
    L = []
    L.append('# 10 · La plata que no se convirtió en obra, gobierno por gobierno (2004–2027)')
    L.append('')
    L.append('> Documento generado por `scripts/build_dinero_no_hecho.py` a partir de `data/comparativa/panel_anual.json`, `fugas_secop.json`, `sgr_fondos.json`, '
             '`costo_no_hacer.json` y `data/gobiernos.json`. Los datos completos, con cada ítem y su fuente, están en `data/comparativa/dinero_no_hecho.json` '
             '(vista **Seis gobiernos → La plata** del atlas). Todas las cifras están en **millones de pesos de 2026** (M).')
    L.append('')
    L.append('## 1. Qué mide este documento')
    L.append('')
    L.append('Cada gobierno de Yondó recibió una cantidad de plata y la convirtió, en parte, en obras. Aquí se cuenta la parte que **no** se convirtió en obra o que se perdió en el camino, '
             'y lo que **pudo entrar o ahorrarse** y no se gestionó. Se separa en tres niveles de certeza:')
    L.append('')
    L.append('- **Hecho**: está en un registro oficial que cualquiera puede revisar. Por ejemplo, regalías pagadas a una obra que va en 9 % de avance con 88 % de los recursos girados (GESPROY).')
    L.append('- **Estimado**: se calcula con un método explícito sobre registros oficiales y se da con un rango. Por ejemplo, el sobrecosto probable por contratar sin competencia.')
    L.append('- **Contrafactual**: lo que pudo pasar con otra decisión. Por ejemplo, cuánto valdría hoy un fondo con el 10 % de las regalías de 2004–2011. **No es plata perdida ni una acusación.**')
    L.append('')
    L.append('"Sin obra" es la suma de hecho y estimado. Los contrafactuales van aparte y nunca se suman con lo anterior.')
    L.append('')
    L.append('## 2. Resumen por gobierno')
    L.append('')
    filas = []
    for p in d['periodos']:
        filas.append([p['id'], p['alcalde'].split(' (')[0].split(';')[0], fmt(p['ingresos']) + (' (2024)' if p['en_curso'] else ''), fmt(p['total_hecho']), fmt(p['total_estimado']),
                      f"**{fmt(p['sin_obra'])}**", f"{fmt(p['sin_obra_rango'][0])}–{fmt(p['sin_obra_rango'][1])}", (f"{fmt(p['sin_obra_pct_ingresos'], 1)} %" if p['sin_obra_pct_ingresos'] is not None else 'no comparable'), fmt(p['total_contrafactual'])])
    L.append(tabla(filas, ['Periodo', 'Alcalde', 'Ingresos', 'Hecho', 'Estimado', 'Sin obra', 'Rango sin obra', '% de ingresos', 'Contrafactual'],
                   ['l', 'l', 'r', 'r', 'r', 'r', 'r', 'r', 'r']))
    L.append('')
    L.append('Ingresos: operaciones efectivas de caja del DNP (FUT vía TerriData), sumadas en pesos de 2026. 2024–2027 solo tiene 2024; su contratación y sus saldos llegan a octubre de 2026, '
             'por eso su porcentaje sobre ingresos no es comparable. En 2004–2011 SECOP casi no tiene registros: las cifras bajas de esos años reflejan falta de datos, no buena gestión.')
    L.append('')
    L.append('### Por categoría')
    L.append('')
    cab = ['Categoría', 'Tipo'] + [p['id'] for p in d['periodos']] + ['Total']
    filas = []
    for t in d['totales_por_categoria']:
        filas.append([t['nombre'], t['tipo']] + [fmt(t['por_periodo'][p['id']]) for p in d['periodos']] + [fmt(t['total_2004_2026']) if t['sumable_entre_gobiernos'] else 'no se suma'])
    L.append(tabla(filas, cab, ['l', 'l'] + ['r'] * 7))
    L.append('')
    L.append('Los saldos de regalías son fotos en fechas distintas (parte de la plata pasa de un gobierno al siguiente) y el ahorro solar es un escenario distinto para cada gobierno: por eso no se suman entre gobiernos.')
    L.append('')
    L.append('## 3. Cada gobierno')
    L.append('')
    for p in d['periodos']:
        L.append(f"### {p['id'].replace('-', '–')} · {p['alcalde']}")
        L.append('')
        if p.get('nota'):
            L.append(f"> {p['nota']}")
            L.append('')
        L.append(f"**En pocas palabras.** {p['lectura']}")
        L.append('')
        L.append(f"Plata del periodo (M de 2026): ingresos {fmt(p['ingresos'])} · inversión {fmt(p['inversion'])} · regalías {fmt(p['regalias'])} · SGP {fmt(p['sgp'])} · impuestos propios {fmt(p['propios'])}"
                 + (' (solo 2024).' if p['en_curso'] else '.'))
        L.append('')
        filas = []
        for f in sorted(p['fugas'], key=lambda x: (['hecho', 'estimado', 'contrafactual'].index(x['tipo']), -(x['valor'] or 0))):
            val = 'sin dato' if f.get('sin_dato') and not f['valor'] else fmt(f['valor'])
            filas.append([CAT_NOMBRE[f['categoria']], f['tipo'], val, rango(f), f['detalle'].replace('|', '/')])
        L.append(tabla(filas, ['Categoría', 'Tipo', 'Valor (M)', 'Rango', 'Detalle'], ['l', 'l', 'r', 'r', 'l']))
        L.append('')
        L.append(f"**Total:** hecho {mm(p['total_hecho'])} · estimado {mm(p['total_estimado'])} · **sin obra {mm(p['sin_obra'])}** (rango {mm(p['sin_obra_rango'][0])}–{mm(p['sin_obra_rango'][1])}) · contrafactual {mm(p['total_contrafactual'])}.")
        L.append('')
        gi = suma_fuga(p, 'girado_sin_avance')['items']
        if gi:
            L.append('Proyectos de regalías con pagos por encima del avance de obra:')
            L.append('')
            L.append(tabla([[it['nombre'], it['bpin'], f"{fmt(it['avance_fisico_pct'])} % / {fmt(it['avance_financiero_pct'])} %", fmt(it['valor'])] for it in gi],
                           ['Proyecto', 'BPIN', 'Avance físico / financiero', 'Girado sin avance (M)'], ['l', 'l', 'r', 'r']))
            L.append('')
        if p['equivalencias']:
            L.append('**Con la plata sin obra alcanzaba para:** ' + ' · '.join(f"{fmt(e['n'], 1 if e['n'] < 10 else 0)} {e['unidad']} (a {mm(e['costo_unitario'], 1 if e['costo_unitario'] < 100 else 0)} c/u)" for e in p['equivalencias']) + '.')
            L.append('')
        L.append('**Lo que Yondó necesitaba y pudo hacerse' + (' (y aún se puede)' if p['en_curso'] else '') + ':**')
        L.append('')
        L.append(tabla([[x['que'], fmt(x['costo']), x['equivalencia'], x['por_que_no']] for x in p['pudo_hacerse']],
                       ['Qué', 'Costo (M de 2026)', 'Equivale a', 'Por qué no se hizo' if not p['en_curso'] else 'Situación'], ['l', 'r', 'l', 'l']))
        L.append('')
        if p['fondos_no_gestionados']:
            L.append('**Fondos externos de referencia:**')
            L.append('')
            L.append(tabla([[f['fondo'], fmt(f['monto_referencia']), (f"{fmt(f['min'])}–{fmt(f['max'])}" if f.get('min') is not None and f.get('max') is not None else '—'),
                             'sí' if f['suma_en_total'] else 'no', f['comparable']] for f in p['fondos_no_gestionados']],
                           ['Fondo', 'Referencia (M)', 'Rango', '¿Se suma?', 'Comparable'], ['l', 'r', 'r', 'l', 'l']))
            L.append('')
    L.append('## 4. Metodología')
    L.append('')
    L.append(d['metodo'])
    L.append('')
    L.append(tabla([[c['nombre'], c['tipo'], c['metodo']] for c in d['categorias']], ['Categoría', 'Tipo', 'Cómo se calcula'], ['l', 'l', 'l']))
    L.append('')
    L.append('### Cómo se evita contar dos veces la misma plata')
    L.append('')
    L.append('1. **Estudios con obra adentro.** Los contratos que incluyen diseño y construcción (como el de $11.696 M con la EDU en 2021) no cuentan como estudios sin obra: su obra va dentro del contrato o ya está en "plata girada sin avance".')
    L.append('2. **Sobrecosto.** A la base del sobrecosto se le restan las OPS (tienen su propia categoría), los estudios sin obra, la plata girada sin avance, los convenios para subsidiar tarifas (no son compras) y una copia de cada registro duplicado, para no aplicar el 10 % a una plata que ya se contó entera. Se cuentan solo los contratos de la alcaldía: lo que la alcaldía transfiere a Aguas y Aseo y al hospital entra una vez, cuando sale de la alcaldía, y no otra vez cuando esas entidades lo contratan.')
    L.append('3. **EDU de Medellín.** De los $84.016 M contratados con la EDU, $77.704 M son seis proyectos de regalías; su brecha entre pagos y obra se cuenta una sola vez, en "plata girada sin avance".')
    L.append('4. **Saldos.** Se toma un solo corte por gobierno (el bienio que cerró en su periodo). Los cortes anteriores se muestran como contexto y no se suman. Los saldos no se suman entre gobiernos.')
    L.append('5. **Fondos.** Los saldos del Incentivo a la Producción y de la Asignación para la Inversión Local ya son de Yondó: van en saldos (hecho), no en fondos no gestionados. Obras por Impuestos (ventana 2018–2023) se reparte entre los dos gobiernos sin repetir el rango. Findeter no se suma porque es crédito.')
    L.append('6. **Recaudo.** En el máximo, el predial con catastro actualizado y la brecha de predial con el percentil 75 no se suman: se toma el mayor.')
    L.append('')
    L.append('### Referencia del sobrecosto por contratar sin competencia')
    L.append('')
    L.append('El rango 5 %–10 %–15 % se apoya en esta literatura. Ninguna cifra prueba que en Yondó haya habido corrupción: miden lo que suele costar renunciar a la competencia.')
    L.append('')
    L.append(tabla([[x['ref'], x['hallazgo'], x['uso'], x['url']] for x in d['literatura_sobrecosto']], ['Estudio', 'Hallazgo', 'Uso aquí', 'Enlace'], ['l', 'l', 'l', 'l']))
    L.append('')
    L.append('### Referencia de la nómina paralela (OPS)')
    L.append('')
    ro = d['referencia_ops']['pesos_2026_por_habitante_al_anio']
    L.append(f"La ley no fija un tope de contratos de prestación de servicios, pero sí prohíbe usarlos para funciones permanentes (Sentencia C-614 de 2009). Como no hay un estándar nacional en datos abiertos, "
             f"la referencia es el propio Yondó: la mediana del gasto anual en OPS por habitante en 2012–2025 ({fmt(ro['mediana'])} pesos de 2026). El rango usa el percentil 75 ({fmt(ro['p75'])}) y el 25 ({fmt(ro['p25'])}).")
    L.append('')
    serie = d['referencia_ops']['serie_pesos_2026_por_habitante']
    L.append(tabla([[str(a) + (' (hasta octubre)' if str(a) == '2026' else ' (SECOP incompleto)' if int(a) < 2012 else ''), fmt(v)] for a, v in serie.items()],
                   ['Año', 'OPS por habitante (pesos de 2026)'], ['l', 'r']))
    L.append('')
    L.append('### Costos unitarios de las equivalencias')
    L.append('')
    L.append(tabla([[c['unidad'], fmt(c['costo'], 1 if c['costo'] < 100 else 0), f"{fmt(c['min'], 1 if c['min'] < 100 else 0)}–{fmt(c['max'], 1 if c['max'] < 100 else 0)}", c['certeza']] for c in d['costos_unitarios']],
                   ['Unidad', 'Costo central (M de 2026)', 'Rango', 'Certeza'], ['l', 'r', 'r', 'l']))
    L.append('')
    L.append('Fuentes de cada costo en `data/comparativa/costo_no_hacer.json` (campo `costos_unitarios`). Son órdenes de magnitud: una obra real necesita estudios, predios, interventoría y operación.')
    L.append('')
    L.append('## 5. Limitaciones')
    L.append('')
    L += [f'- {x}' for x in d['limitaciones']]
    L.append('')
    L.append('## 6. Notas legales')
    L.append('')
    L += [f'- {x}' for x in d['notas_legales']]
    L.append('')
    L.append('## 7. Fuentes')
    L.append('')
    L.append('- SECOP I y II, SECOP Integrado: https://www.datos.gov.co/d/rpmr-utcd (vía `data/comparativa/fugas_secop.json`).')
    L.append('- GESPROY y MapaInversiones (proyectos de regalías): https://www.datos.gov.co/d/mzgh-shtp; MinHacienda, presupuesto SGR 2025–2026: https://www.datos.gov.co/d/e624-d9uy; CHIP y SICODIS (vía `data/comparativa/sgr_fondos.json`).')
    L.append('- DNP, operaciones efectivas de caja (TerriData): https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 (vía `data/comparativa/panel_anual.json`).')
    L.append('- IPC del DANE: https://www.dane.gov.co/files/operaciones/IPC/sep2026/anex-IPC-Indices-sep2026.xlsx.')
    L.append('- Costos unitarios, contrafactual solar, ahorro de regalías, recaudo y tasa retributiva: `data/comparativa/costo_no_hacer.json`.')
    L.append('- Superservicios, evaluación integral de Aguas y Aseo de Yondó (2020): https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf.')
    L.append('- Hechos de cada gobierno: `data/gobiernos.json` y `docs/anexos/A-gobiernos-2004-2027.md`.')
    L.append('')
    return '\n'.join(L)


if __name__ == '__main__':
    validar(salida)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    DOC.write_text(doc_md(salida), encoding='utf-8')
    print(f'Escrito {SALIDA.relative_to(RAIZ)} y {DOC.relative_to(RAIZ)}')
    print(f"{'periodo':10} {'ingresos':>9} {'hecho':>8} {'estimado':>9} {'sin_obra':>9} {'contraf':>8}")
    for p in salida['periodos']:
        print(f"{p['id']:10} {p['ingresos']:9.0f} {p['total_hecho']:8.0f} {p['total_estimado']:9.0f} {p['sin_obra']:9.0f} {p['total_contrafactual']:8.0f}")
    for t in salida['totales_por_categoria']:
        print(f"  {t['categoria']:28} " + ' '.join(f"{(v or 0):8.0f}" for v in t['por_periodo'].values()) + f"  total={t['total_2004_2026']}")
