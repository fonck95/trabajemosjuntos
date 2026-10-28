#!/usr/bin/env python3
"""La plata que no se convirtió en obra a tiempo, por gobierno (síntesis).

Genera:
  data/comparativa/dinero_no_hecho.json   (lo lee la web: vista "Seis gobiernos", modo "La plata")
  docs/10-dinero-no-hecho-por-gobierno.md (explicación con tablas, método y limitaciones)

Insumos (todos en el repositorio; este script no descarga nada):
  data/comparativa/panel_anual.json     IPC base 2026, población, ingresos e inversión por gobierno
  data/comparativa/fugas_secop.json     contratación de la alcaldía por año (SECOP, pesos corrientes); usa los campos "ajustes"
  data/comparativa/sgr_fondos.json      regalías, proyectos SGR, saldos y fondos externos (pesos corrientes)
  data/comparativa/costo_no_hacer.json  costos unitarios, IPC mensual, contrafactual solar, ahorro de regalías, recaudo, tasa retributiva
  data/gobiernos.json                   periodos, alcaldes, qué se hizo y qué faltó

Todo se lleva a millones de pesos constantes de 2026 con el IPC del DANE (promedio ene–sep 2026 = 1,0).
Un flujo de un año se deflacta con el IPC promedio de ese año; un saldo medido en una fecha, con el IPC
del mes de esa fecha (serie mensual de costo_no_hacer.json).

Cinco niveles, que no se mezclan:
  hecho          registro oficial (o cálculo directo sobre registros oficiales) verificable
  estimado       cálculo con método y rango
  plata quieta   saldos de regalías sin comprometer en una fecha: hecho, pero no es plata perdida
  indicio        gasto en OPS por encima de lo usual: alerta para revisar, no plata sin obra
  contrafactual  lo que pudo pasar con otra decisión
"Sin obra" = hecho + estimado.

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
# Saldo posterior de asignaciones directas sin aprobar del bienio 2025–2026 (millones de pesos de 2026), el que usa la propuesta
# 2028–2031. No trae el desglose entre directas y anticipadas, así que no reemplaza el corte de MinHacienda de sgr_fondos.json
# (CORTE): se da aparte, como salvedad, igual que en docs/11 (sección 8). Si CORTE llega a esa fecha, la salvedad desaparece.
AD_SIN_APROBAR_POSTERIOR = {'fecha': '2026-10-27', 'valor': 7297,
                            'fuente': 'data/propuesta/modulos/salud.json (propuesta 2028–2031; sin desglose entre directas y '
                                      'anticipadas); docs/11, sección 8'}

PANEL = json.load(open(COMP / 'panel_anual.json', encoding='utf-8'))
FUGAS = json.load(open(COMP / 'fugas_secop.json', encoding='utf-8'))
SGR = json.load(open(COMP / 'sgr_fondos.json', encoding='utf-8'))
CNH = json.load(open(COMP / 'costo_no_hacer.json', encoding='utf-8'))
GOB = json.load(open(RAIZ / 'data' / 'gobiernos.json', encoding='utf-8'))

IPC = {int(k): float(v) for k, v in PANEL['ipc'].items()}
POB = {int(k): float(v) for k, v in PANEL['poblacion'].items()}
IND = {i['id']: i for i in PANEL['indicadores']}
COB_MEDIA = IND['cob_neta_media']['serie']                                  # cobertura neta en media (MEN, TerriData)
COB_MEDIA_0507 = statistics.mean(COB_MEDIA[str(a)] for a in range(2005, 2008))
COB_MEDIA_1215 = statistics.mean(COB_MEDIA[str(a)] for a in range(2012, 2016))
IPC_MES = {int(k): v for k, v in CNH['series_usadas']['ipc_dane']['mensual'].items()}
IPC_BASE = float(CNH['series_usadas']['ipc_dane']['base_2026'])

F_PANEL = 'data/comparativa/panel_anual.json'
F_FUGAS = 'data/comparativa/fugas_secop.json'
F_SGR = 'data/comparativa/sgr_fondos.json'
F_CNH = 'data/comparativa/costo_no_hacer.json'
F_GOB = 'data/gobiernos.json'
F_ANEXO_A = 'docs/anexos/A-gobiernos-2004-2027.md'
URL_SECOP = 'https://www.datos.gov.co/d/rpmr-utcd'
URL_GESPROY = 'https://www.datos.gov.co/d/mzgh-shtp'
URL_MINHAC = 'https://www.datos.gov.co/d/e624-d9uy'
URL_DNP_ALERTA = ('El Colombiano, 26-ago-2024: https://www.elcolombiano.com/medellin/escandalo-ocad-paz-edu-alcaldia-yondo-obras-CN25287252 ; '
                  'Blu Radio, 28-ago-2024: https://www.bluradio.com/regiones/antioquia/dnp-cuestiono-contratos-por-mas-de-16-000-millones-firmados-con-la-edu-rg10')
PERIODOS_IDS = [g['id'] for g in GOB['periodos']]


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def a26(pesos_corrientes, anio):
    """Flujo en pesos corrientes de un año → millones de pesos de 2026 (IPC promedio del año)."""
    anio = int(anio)
    assert min(IPC) <= anio <= max(IPC), f'año sin IPC: {anio}'
    return pesos_corrientes / 1e6 / IPC[anio]


def a26_prom(pesos_corrientes, anios):
    """Pesos repartidos en varios años → millones de 2026 con el IPC promedio de esos años."""
    anios = list(anios)
    assert anios and all(a in IPC for a in anios), anios
    return pesos_corrientes / 1e6 / statistics.mean(IPC[a] for a in anios)


def a26_mes(pesos_corrientes, anio, mes):
    """Saldo medido en una fecha → millones de 2026 con el IPC del mes del corte."""
    return pesos_corrientes / 1e6 / (IPC_MES[int(anio)][mes - 1] / IPC_BASE)


def factor_mes(anio, mes):
    return IPC_MES[int(anio)][mes - 1] / IPC_BASE


def r1(x):
    return None if x is None else round(float(x), 1)


def fmt(v, dec=0):
    """Número con formato colombiano: 12.345,6"""
    if v is None:
        return '—'
    q = Decimal(str(abs(v))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    s = f'{q:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('−' if v < 0 and float(q) != 0 else '') + s


def mm(v, dec=0):
    if v is None:
        return '—'
    return f'−${fmt(-v, dec)} M' if v < 0 else f'${fmt(v, dec)} M'


def mmc(pesos, anio):
    """Cifra citada en pesos corrientes, con su año."""
    return f'${fmt(pesos / 1e6)} M en pesos corrientes de {anio}'


def plural(n, singular, plural_):
    return f'{fmt(n)} {singular if n == 1 else plural_}'


MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def fecha_corta(iso):
    """2026-10-21 → 21-oct-2026"""
    a, m, d = iso.split('-')
    return f'{int(d)}-{MESES[int(m) - 1][:3]}-{a}'


def fecha_larga(iso):
    """2026-10-21 → 21 de octubre de 2026"""
    a, m, d = iso.split('-')
    return f'{int(d)} de {MESES[int(m) - 1]} de {a}'


def salvedad_ad(ad_corte):
    """Saldo posterior de asignaciones directas sin aprobar frente al de CORTE; vacío si no es posterior a CORTE."""
    p = AD_SIN_APROBAR_POSTERIOR
    if p['fecha'] <= CORTE:
        return ''
    return (f"al {fecha_corta(p['fecha'])} las asignaciones directas sin aprobar eran ≈ {mm(p['valor'])}, frente a {mm(ad_corte)} "
            f"el {fecha_corta(CORTE)} (docs/11, sección 8)")


def frase_salvedad_ad(ad_corte):
    """La salvedad como frase aparte (con espacio inicial y punto final), o nada."""
    s = salvedad_ad(ad_corte)
    return f' {s[0].upper()}{s[1:]}.' if s else ''


def pct(a, b, dec=0):
    return fmt(100 * a / b, dec) if b else '—'


def anios_de(pid):
    a, b = pid.split('-')
    return list(range(int(a), int(b) + 1))


def periodo_de(anio):
    return next(p for p in PERIODOS_IDS if int(p[:4]) <= int(anio) <= int(p[5:]))


def corto(s, n=150):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[: n - 1].rstrip() + '…'


SIGLAS = ['APS', 'PDET', 'EOT', 'EDU', 'CIC', 'PAE', 'E.S.E.', 'ESE', 'PTAR', 'MGA', 'AMMA', 'INVÍAS', 'OCAD', 'SGR', 'SAS', 'S.A.S.', 'E.S.P.', 'ESP', 'MPIO', 'IEC']


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


# Nombres como figuran en el registro mercantil cuando SECOP trae una abreviatura
NOMBRES_REGISTRADOS = {
    'asomiguelarcangel': ('Asociación Centro de Bienestar del Anciano y Centro Vida para el Desarrollo del Adulto Mayor San Miguel Arcángel '
                          '(RUES, Cámara de Comercio de Barrancabermeja, NIT 900108408: https://www.datos.gov.co/d/c82u-588k)'),
}
NO_PUBLICABLE = ('Persona natural', 'Nombre no publicado', 'Sin dato')


def contratista_publicable(nombre):
    """Nombre de empresa o entidad para mostrar; None si es persona natural o no se pudo confirmar que sea empresa."""
    n = (nombre or '').strip()
    if not n or n.startswith(NO_PUBLICABLE):
        return None
    n = NOMBRES_REGISTRADOS.get(n.lower(), n)
    return n.split(' (antes')[0].split(' (NIT')[0] if not n.startswith('Asociación Centro de Bienestar') else n


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


def eq_texto(valor, id_, con_rango=False):
    n = valor / cu(id_)
    nombre = SINGULAR[id_] if round(n, 1) == 1 else (UNIDADES.get(id_) or PLURAL_EXTRA.get(id_))
    if id_ == 'ptar_12000_hab':
        nombre = 'PTAR para el casco urbano' if round(n, 1) == 1 else 'PTAR como la que necesita el casco urbano'
    t = f'≈ {fmt(n, 1 if n < 10 else 0)} {nombre}'
    if con_rango:
        a, b = valor / cu_max(id_), valor / cu_min(id_)
        t += f' (entre {fmt(a, 1 if a < 10 else 0)} y {fmt(b, 1 if b < 10 else 0)}, según el costo unitario)'
    return t


# ---------------------------------------------------------------------------
# insumos por año (alcaldía, SECOP) y por periodo
# ---------------------------------------------------------------------------
SECOP_ALC = {r['anio']: r for r in FUGAS['por_anio'] if r['entidad'] == 'Alcaldía'}
SECOP_ENT = {(r['entidad'], r['anio']): r for r in FUGAS['por_anio']}
AJ = FUGAS['ajustes_dinero_no_hecho']
CIUDADELA = next(e for e in AJ['estudios_obra_hallada_fuera'] if e['motivo'] == 'obra_suspendida')
ACUED = next(e for e in AJ['estudios_obra_hallada_fuera'] if 'acueductos rurales' in e['etiqueta'])
RES_ALC = {r['periodo']: r for r in FUGAS['resumen_alcaldia_por_periodo']}
COBERTURA = {r['anio']: r for r in FUGAS['cobertura_contratos_por_anio']}
N_ALC_2007 = COBERTURA[2007]['Alcaldía']                                   # contratos de la alcaldía en SECOP en 2007 (el primer año con registros)
N_ALC_0811 = [COBERTURA[a]['Alcaldía'] for a in range(2008, 2012)]
PANEL_PER = {p['id']: p for p in PANEL['periodos']}
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
OXI_PROPIOS = {int(x['anio']): {'anio': int(x['anio']), 'valor': x['valor']} for x in FONDOS['OXI']['yondo_obtuvo']['propios']}
OXI_2019, OXI_2024 = OXI_PROPIOS[2019], OXI_PROPIOS[2024]
COOP_USD = FONDOS['COOPERACION']['yondo_obtuvo']['monto_usd']
COOP_UE_USD = FONDOS['COOPERACION']['comparables'][0]['monto_usd']
ESPERA_SOLAR = CNH['contrafactual_solar']['costo_de_esperar_desde_2026']['ahorro_bruto_anual_solo_solar_cop_2026'] / 1e6
AHORRO = {r['anio']: r for r in CNH['contrafactual_ahorro_regalias']['filas']}
RECAUDO = {r['periodo']: r for r in CNH['recaudo_potencial']['por_periodo']}
RECAUDO_BAJO = CNH['recaudo_potencial']['anios_yondo_por_debajo_de_la_mediana']
CATASTRO = CNH['recaudo_potencial']['escenario_catastro']
TASA = {r['anio']: r for r in CNH['aguas_residuales']['tasa_retributiva']['serie']}
TASA_INFO = CNH['aguas_residuales']['tasa_retributiva']
TASA_EVITABLE = 0.80   # una PTAR que remueva 80 % de la carga reduce la tasa en esa proporción (costo_no_hacer.json, tasa_retributiva.lectura)
MESES_2026 = 10        # la serie de 2026 es anual; el corte es octubre: se cuentan 10/12

# proyectos SGR que ejecutó la EDU de Medellín como contratista del municipio (docs/01-diagnostico-sectorial.md, tabla de brechas; anexo A, §8)
BPIN_EDU = {'20201301010644', '20201301010781', '2022003050005', '2022003050034', '20211301012365', '2023058930013'}
EDU_PROY = {it['bpin']: it['valor'] for p_ in SGR['proyectos_por_periodo'] for it in p_['items'] if it['bpin'] in BPIN_EDU}
EDU_CONTRATOS = [c for c in FUGAS['convenios_delegada'] if c['entidad'] == 'Alcaldía' and 'Desarrollo Urbano de Medellín' in c['contratista']]
EDU_MIXTO = max((c for c in EDU_CONTRATOS if 'DISE' in c['objeto'].upper() and 'DELEGADA' in c['objeto'].upper()), key=lambda c: c['valor'])
EJ_HECHO = next(it for p_ in SGR['proyectos_por_periodo'] for it in p_['items'] if it['bpin'] == '2022003050034')
BPIN_EDU_YARUMAL = {'2022003050005', '2022003050034'}   # contrato 134-2023: en 2026 figura a nombre de la E. D. T. de Yarumal (anexo A, §8.3)
# proyectos de varios municipios que el registro no marca como multimunicipales; parte de Yondó según el anexo A, §8.3
MULTI_POR_NOMBRE = {'2022003050005': {'municipios': 'Puerto Nare, Yolombó y Yondó', 'parte_yondo': 60 / 150,
                                      'nota': '150 viviendas en Puerto Nare, Yolombó y Yondó, 60 en Yondó (anexo A, §8.3); las ejecuta el municipio de Yondó con regalías del departamento'}}
SERVICIO_RE = re.compile(r'ALIMENTACI|TRANSPORTE ESCOLAR|ATENCI[OÓ]N PRIMARIA|\bAPS\b|ESTUDIOS Y DISE', re.I)

# literatura para el costo de contratar sin competencia
LIT_SOBRECOSTO = [
    {'ref': 'Titl, V. (2024). Reform of Single-Bidding in Public Procurement: More Competition, Lower Price. IDEA Study 3/2024 (CERGE-EI); versión académica: The One and Only: Single-Bidding in Public Procurement, U.S.E. Working Paper 23-08, Universidad de Utrecht.',
     'hallazgo': 'En Chequia, prohibir la adjudicación de contratos con una sola oferta bajó los precios cerca de 6 % del costo estimado. Mide precios, sin suponer corrupción.',
     'url': 'https://idea-en.cerge-ei.cz/files/IDEA_Studie_03_2024_Verejne_zakazky_abstract_EN.pdf ; https://www.uu.nl/sites/default/files/LEG_USE_WP_23-08%20%282%29.pdf',
     'uso': 'valor central (6 %); la mitad (3 %) es el mínimo, porque no todo contrato directo habría bajado de precio con competencia'},
    {'ref': 'Szucs, F. (2024). Discretion and Favoritism in Public Procurement. Journal of the European Economic Association 22(1): 117–160; versión de trabajo resumida por el autor en VoxDev.',
     'hallazgo': 'En Hungría, cuando el comprador puede negociar en vez de hacer una subasta abierta, el precio de cada peso de gasto público sube cerca de 8 centavos y ganan contratistas menos productivos y con conexiones políticas.',
     'url': 'https://doi.org/10.1093/jeea/jvad017 ; https://voxdev.org/topic/public-economics/how-organise-public-procurement',
     'uso': 'máximo del rango (10 %, algo por encima de los 8 centavos)'},
    {'ref': 'Gallego, J., Prem, M. y Vargas, J. F. (2021). Inefficient Procurement in Times of Pandemia. SSRN 3600572 (antes: Corruption in the Times of Pandemia, Universidad del Rosario, DT 250, 2020).',
     'hallazgo': 'En Colombia, en 2020 los municipios con más riesgo de corrupción pasaron a contratación no competitiva y subieron el valor de sus contratos; esos contratos tuvieron más sobrecostos.',
     'url': 'https://papers.ssrn.com/abstract=3600572',
     'uso': 'evidencia colombiana de la dirección del efecto'},
    {'ref': 'OCDE (2014). OECD Foreign Bribery Report: An Analysis of the Crime of Bribery of Foreign Public Officials.',
     'hallazgo': 'En 427 casos de soborno probado, el soborno promedio fue 10,9 % del valor de la transacción.',
     'url': 'https://doi.org/10.1787/9789264226616-en',
     'uso': 'solo contexto: mide sobornos en casos de corrupción probada; no se usa en el rango'},
    {'ref': 'PwC y Ecorys para la Comisión Europea (OLAF) (2013). Identifying and reducing corruption in public procurement in the EU.',
     'hallazgo': 'En contratos con corrupción o con señales de ella ("casos grises"), la pérdida pública directa fue 13 % a 18 % del presupuesto del proyecto.',
     'url': 'https://dspace.library.uu.nl/handle/1874/309580',
     'uso': 'solo contexto: escenario con corrupción, que nadie ha probado en Yondó; no se usa en el rango'},
]
SOBRECOSTO = {'min': 0.03, 'central': 0.06, 'max': 0.10}

GLOSARIO = [
    ('Contrafactual', 'lo que habría pasado con otra decisión. Sirve para dimensionar oportunidades, no es plata perdida.'),
    ('Pesos de 2026', 'pesos de otros años llevados a su valor de hoy con el índice de precios (IPC) del DANE, para poder compararlos.'),
    ('Pesos corrientes', 'el valor tal como se registró en su año, sin llevarlo a pesos de hoy.'),
    ('Bienio', 'periodo de dos años del presupuesto de regalías (Sistema General de Regalías, desde 2012).'),
    ('BPIN', 'número con el que se registra un proyecto de inversión pública.'),
    ('OCAD', 'órgano que aprueba proyectos de regalías. El OCAD Paz es nacional y aprueba proyectos de municipios PDET.'),
    ('Incentivo a la producción', ('parte de las regalías que premia a los municipios productores. Desde el Acto Legislativo 04 de 2017 sus proyectos los '
                                   'aprueba el OCAD Paz; el municipio los formula y presenta. En el registro de MinHacienda aparece como bolsa IPAZ. Aquí se '
                                   'le llama siempre "incentivo a la producción".')),
    ('EDU de Medellín', 'Empresa de Desarrollo Urbano de Medellín, empresa pública de otro municipio a la que Yondó delegó obras con convenios interadministrativos.'),
    ('OPS', 'contrato de prestación de servicios (con una persona o una empresa).'),
    ('Contratación sin competencia', 'contratación directa, régimen especial o convenios: se escoge al contratista sin que compitan varias ofertas. Es legal en muchos casos.'),
    ('Pagado y avance de obra', 'en los proyectos de regalías, lo que se ha pagado (avance financiero) y lo que se ha construido o entregado (avance físico), en porcentaje.'),
    ('Mediana', 'el valor del medio: la mitad de los años está por encima y la otra mitad por debajo.'),
    ('Percentil 25 y percentil 75', ('el valor que deja por debajo a la cuarta parte de los datos (percentil 25) o a las tres cuartas partes (percentil 75). '
                                     'Sirven para dar un rango alrededor de la mediana.')),
]


# ---------------------------------------------------------------------------
# categorías
# ---------------------------------------------------------------------------
TIPOS = ('hecho', 'estimado', 'plata quieta', 'indicio', 'contrafactual')
TIPOS_SIN_OBRA = ('hecho', 'estimado')
CATEGORIAS = [
    {'id': 'estudios_sin_obra', 'nombre': 'Estudios sin obra posterior hallada en el SECOP de la alcaldía', 'tipo': 'estimado',
     'descripcion': ('Estudios, diseños y consultorías que la alcaldía pagó y para los que no se halló después, en su SECOP, una obra con objeto parecido. '
                     'El contratista entregó el estudio: "sin obra" se refiere a la decisión posterior del municipio, y "no hallada" no quiere decir que no exista.'),
     'metodo': ('Suma por año de "ajustes.estudios" de la alcaldía (fugas_secop.json): similitud de palabras del objeto menor que 0,30 con las obras de la alcaldía '
                'firmadas el mismo año o después. Se excluyen los contratos mixtos (diseño y obra en el mismo contrato) y los estudios cuya obra consta fuera '
                'del SECOP de la alcaldía (acueductos rurales de 2013, José Domingo Oliveros de 2022), cuya obra se suspendió (Ciudadela Educativa de 2014) o '
                'que no son estudios previos (seguimiento técnico de 2018). Central: sin los estudios de los últimos 18 meses (su obra puede no haberse firmado). '
                'Mínimo: umbral de similitud 0,20 (más obras halladas) y sin planes de ordenamiento, de desarrollo o de gestión del riesgo, que no llevan a una '
                'obra directa. Máximo: umbral 0,40, con los estudios recientes.')},
    {'id': 'girado_sin_avance', 'nombre': 'Pagos por delante del avance reportado (regalías, a octubre de 2026)', 'tipo': 'hecho',
     'descripcion': ('Recursos de proyectos de regalías con ejecutor municipal (pueden incluir cofinanciación) pagados por encima de lo que avanzó la obra o la '
                     'entrega del servicio, según GESPROY a octubre de 2026. Es un cálculo directo sobre registros oficiales. En los proyectos que siguen en '
                     'ejecución la brecha puede cerrarse, y parte de ella puede ser un anticipo legal.'),
     'metodo': ('Por proyecto SGR con ejecutor municipal: valor × (avance financiero − avance físico) / 100 (sgr_fondos.json, GESPROY, corte oct-2026; el valor '
                'es el total del proyecto y puede incluir cofinanciación). El valor en pesos corrientes es el dato; para llevarlo a pesos de 2026 se supone '
                'que los pagos de MinHacienda de 2025–2026 se hicieron en esos años y el resto se repartió entre el año del primer contrato y 2024. Cada '
                'proyecto se asigna al gobierno que lo aprobó, aunque parte de los pagos ocurriera en el siguiente. Central: todos los proyectos con brecha, '
                'salvo los del gobierno en curso que siguen en ejecución. Mínimo: sin servicios (alimentación y transporte escolar, atención primaria), sin '
                'proyectos con registros contradictorios, sin los fechados en un bienio compartido entre dos gobiernos, con solo la parte de Yondó en los '
                'proyectos de varios municipios y con el IPC más alto. Máximo: todos, con el IPC del año del primer contrato. Los proyectos de INVÍAS u otras '
                'entidades nacionales no se suman.')},
    {'id': 'saldos_regalias', 'nombre': 'Plata quieta: regalías sin comprometer al cierre del bienio', 'tipo': 'plata quieta',
     'descripcion': ('Regalías del presupuesto del municipio que, al cierre del último bienio que terminó dentro del gobierno, no se habían comprometido. Es un '
                     'hecho, pero no es plata perdida: pasa al bienio siguiente. Por eso no se suma a "sin obra" ni entre gobiernos.'),
     'metodo': ('Una sola regla para todos: el último bienio que cerró dentro del periodo y la misma medida, presupuesto menos compromisos (CHIP): 2017–2018 '
                'para 2016–2019 (corte más cercano al cierre con dato abierto: septiembre de 2018, todo el capítulo SGR), 2021–2022 para 2020–2023 y '
                '2023–2024 para 2024–2027 (asignaciones directas, más el incentivo a la producción y la inversión local que pasaron sin usar). Se deflacta con '
                'el IPC del mes del corte. El bienio 2015–2016 cruza dos gobiernos y se muestra aparte, sin sumarlo a ninguno, porque en 2016–2019 cerró después '
                'otro bienio completo (2017–2018). En 2024–2027 el único bienio cerrado es 2023–2024, que empezó en el gobierno anterior: se usa, con esa '
                'advertencia. El bienio 2025–2026 sigue abierto: se muestra como "por aprobar" y no se suma.')},
    {'id': 'sobrecosto_sin_competencia', 'nombre': 'Costo posible de contratar sin competencia', 'tipo': 'estimado',
     'descripcion': ('El valor contratado sin competencia es un hecho registrado en SECOP; lo que se pudo pagar de más por no competir es una estimación con '
                     'rango (3 %, 6 % y 10 %). No prueba corrupción ni ilegalidad.'),
     'metodo': ('Línea 1, compras de la alcaldía a terceros: valor sin competencia (contratación directa, régimen especial y convenios) sin OPS, sin estudios '
                'sin obra, sin transferencias a Aguas y Aseo, al hospital u otra entidad de Yondó (incluidos los subsidios a las tarifas) y sin empréstitos; '
                'más los procesos competitivos con un solo oferente (fugas_secop.json, ajustes.base_sobrecosto). Se le resta la plata ya contada en "pagos '
                'por delante del avance". Línea 2, plata transferida: para cada año y entidad, el menor valor entre lo que la alcaldía transfirió a Aguas y '
                'Aseo o al hospital (sin subsidios) y lo que esa entidad contrató sin competencia ese año, solo en años con datos de esa entidad en SECOP. '
                'La línea 1 incluye los convenios con la EDU de Medellín, que Yondó escogió sin competencia; la EDU contrató después por su cuenta y no se '
                'sabe si con competencia. Costo = base × 6 % (central). Mínimo: 3 % solo sobre la línea 1, sin la EDU y sin la segunda copia de los posibles '
                'registros duplicados. Máximo: 10 % sobre las dos líneas.')},
    {'id': 'ops_nomina_paralela', 'nombre': 'Gasto en OPS por encima de lo usual en Yondó', 'tipo': 'indicio',
     'descripcion': ('Gasto en contratos de prestación de servicios (OPS) por encima del nivel que Yondó mismo tuvo en un año típico. Los contratistas '
                     'prestaron servicios: el exceso es una alerta para comparar con la planta de personal, no plata sin obra. No se suma a "sin obra".'),
     'metodo': ('OPS de la alcaldía sin transferencias a entidades de Yondó, subsidios, convenios para aunar esfuerzos, contratos con instituciones públicas ni la '
                'segunda copia de registros duplicados (fugas_secop.json, ajustes.ops). Referencia: mediana del gasto anual en OPS por habitante de 2012 a '
                '2025, en pesos de 2026. Exceso de cada año = OPS del año − referencia × población, si es positivo. También se publica la desviación neta '
                'del periodo (los años por debajo restan). Rango: con el percentil 75 (mínimo) y el 25 (máximo). La ley no fija un tope, pero prohíbe usar OPS '
                'para funciones permanentes (Corte Constitucional, Sentencia C-614 de 2009).')},
    {'id': 'recaudo_no_cobrado', 'nombre': 'Recaudo propio que se dejó de cobrar', 'tipo': 'estimado',
     'descripcion': 'Predial e ICA que Yondó habría recaudado con el esfuerzo de municipios comparables o con un catastro actualizado.',
     'metodo': ('Central: brecha frente a la mediana de 7 comparables, sumada por periodo (costo_no_hacer.json); un año por debajo de la mediana se compensa con '
                'los años en que Yondó recaudó más. Máximo: brecha frente al percentil 75 de los comparables y, desde 2021 (catastro desactualizado), el '
                f"predial adicional con el avalúo por habitante de Puerto Berrío (≈{mm(CATASTRO['adicional_anual_mm_2026'])} de 2026 al año, ilustrativo); en predial "
                'se toma el mayor de los dos.')},
    {'id': 'costo_vertimientos', 'nombre': 'Tasa retributiva evitable por no tener PTAR', 'tipo': 'estimado',
     'descripcion': ('Parte de la tasa ambiental que se habría evitado con una PTAR. La paga Aguas y Aseo (el prestador del servicio), no la alcaldía; el municipio '
                     'responde por que el servicio se preste.'),
     'metodo': ('80 % de la tasa retributiva estimada con factor regional 1 (costo_no_hacer.json, aguas_residuales): una PTAR que remueva 80 % de la carga '
                'reduce la tasa en esa proporción. 2026 se cuenta por 10 meses. Máximo con el caudal medido por la Superservicios en 2019 (hasta 1,98 veces), '
                'que se aplica también a los años anteriores. El valor facturado por Corantioquia no es público.')},
    {'id': 'fondos_no_gestionados', 'nombre': 'Fondos externos no obtenidos', 'tipo': 'contrafactual',
     'descripcion': ('Plata de fondos nacionales o de cooperación que municipios parecidos obtuvieron; no se halló que Yondó la obtuviera ni que la solicitara. '
                     'Algunos dependen de terceros (en Obras por Impuestos, de que una empresa escoja el proyecto).'),
     'metodo': ('Rangos de sgr_fondos.json repartidos entre gobiernos sin repetir la misma oportunidad: Obras por Impuestos (ventana 2018–2023: el proyecto vial '
                'mediano del país como central para toda la ventana, repartido por años, 2 de 6 para 2016–2019 y 4 de 6 para 2020–2023; mínimo 0), MinTIC Centros '
                'Digitales, Fondo Adaptación (central 0: no se verificó que Yondó registrara daños en 2010–2011), cooperación internacional (central: una donación '
                'pequeña por gobierno; 0 en 2012–2015, cuando Yondó sí recibió una), OCAD Paz y FENOGE (2024–2027). Findeter no se suma: es crédito.')},
    {'id': 'ahorro_solar', 'nombre': 'Beneficio solar no capturado', 'tipo': 'contrafactual',
     'descripcion': ('Beneficio neto, hasta 2026, si las 13 sedes públicas del plan (469 kWp) se hubieran puesto solares al empezar el gobierno: ahorro en facturas '
                     'menos inversión y mantenimiento, más el valor que el equipo conserva en 2026.'),
     'metodo': ('Contrafactual de costo_no_hacer.json, solo solar, escenario central y rango con valor residual. Se publican aparte el ahorro neto en facturas y el '
                'valor residual. Si el neto es negativo (2008) se registra cero: no habría convenido. Cada gobierno es un escenario aparte; no se suman entre gobiernos.')},
    {'id': 'ahorro_regalias', 'nombre': 'Fondo local de ahorro con regalías (no se creó)', 'tipo': 'contrafactual',
     'descripcion': 'Lo que valdría hoy un fondo local con el 10 % de las regalías directas de 2004–2011, cuando el municipio las recibía directamente.',
     'metodo': ('Aportes anuales del 10 % (costo_no_hacer.json) que crecen al 3 % real (central) o 4 % (máximo) hasta 2026; mínimo: el aporte sin rendimiento. '
                'Es adicional al ahorro obligatorio en el Fondo de Ahorro y Estabilización Petrolera (FAEP, Ley 209 de 1995), cuya subcuenta para Yondó no se '
                'revisó: si parte de esas regalías quedó retenida allí, este contrafactual está sobrestimado. Desde 2012 el Sistema General de Regalías ahorra a '
                'nivel nacional y no aplica.')},
]
CAT_TIPO = {c['id']: c['tipo'] for c in CATEGORIAS}
CAT_NOMBRE = {c['id']: c['nombre'] for c in CATEGORIAS}


def fuga(cat, valor, mn=None, mx=None, detalle='', items=None, fuentes=None, sin_dato=False, no_aplica=False, **extra):
    d = {'categoria': cat, 'valor': r1(valor), 'min': r1(mn), 'max': r1(mx), 'tipo': CAT_TIPO[cat],
         'detalle': ' '.join(detalle.split()), 'items': items or [], 'fuentes': fuentes or []}
    if sin_dato:
        d['sin_dato'] = True
    if no_aplica:
        d['no_aplica'] = True
    d.update(extra)
    return d


def item(nombre, anio, valor, fuente, en_total=True, **extra):
    return {'nombre': nombre, 'anio': anio, 'valor': r1(valor), 'fuente': fuente, 'en_total': en_total, **extra}


# ---------------------------------------------------------------------------
# referencia de OPS (mediana y cuartiles del gasto por habitante 2012–2025, serie ajustada)
# ---------------------------------------------------------------------------
def ops_aj(a):
    return SECOP_ALC[a]['ajustes']['ops']


OPS_PC = {a: a26(ops_aj(a)['valor'], a) * 1e6 / POB[a] for a in SECOP_ALC if a in POB and ops_aj(a)['n']}
OPS_PC_ORIG = {a: a26(SECOP_ALC[a]['ops']['valor'], a) * 1e6 / POB[a] for a in SECOP_ALC if a in POB and SECOP_ALC[a]['ops']['n']}
_ref_years = [a for a in range(2012, 2026) if a in OPS_PC]
_q = statistics.quantiles([OPS_PC[a] for a in _ref_years], n=4)
OPS_REF = {'p25': _q[0], 'mediana': statistics.median(OPS_PC[a] for a in _ref_years), 'p75': _q[2]}
OPS_REF_ORIG = statistics.median(OPS_PC_ORIG[a] for a in _ref_years)
OPS_PUBLICADAS = sum(r['ops']['n'] for r in SECOP_ALC.values())
OPS_RECLAS_N = sum(r['ajustes']['ops']['reclasificadas_n'] for r in SECOP_ALC.values())
OPS_DUP_N = sum(r['ajustes']['ops']['duplicados_n'] for r in SECOP_ALC.values())
assert OPS_PUBLICADAS == 5580, OPS_PUBLICADAS   # cifra ya publicada (docs/03)


# ---------------------------------------------------------------------------
# cálculo por periodo
# ---------------------------------------------------------------------------
def deflactores(it):
    """Factores IPC (central, mínimo de valor, máximo de valor) para la brecha de un proyecto SGR."""
    anio = int(it.get('primer_contrato_vigencia') or it['anio'])
    assert anio <= max(IPC), it['bpin']
    pag = it.get('pagado') or 0
    p2526 = min(pag, ((it.get('minhacienda_2025_2026') or {}).get('pagado') or 0))
    resto = pag - p2526
    anios_resto = list(range(anio, max(anio, 2024) + 1)) if anio <= 2024 else [anio]
    f_resto = statistics.mean(IPC[a] for a in anios_resto)
    f_2526 = statistics.mean([IPC[2025], IPC[2026]])
    f_c = (resto * f_resto + p2526 * f_2526) / pag if pag else f_resto
    f_prom = statistics.mean(IPC[a] for a in range(anio, max(anio, 2025) + 1))   # pagos repartidos hasta 2025
    f_alto = max(f_c, f_prom)
    f_bajo = IPC[anio]                                                         # todo pagado el año del primer contrato
    return anio, f_c, f_alto, f_bajo, p2526


def girado_sin_avance(pid):
    p = SGR_PROY[pid]
    en_curso = pid == '2024-2027'
    items, otros = [], []
    tot = {'central': 0.0, 'min': 0.0, 'max': 0.0, 'corriente': 0.0}
    for it in p['items']:
        g = it.get('girado_sin_avance') or 0
        if g <= 0:
            continue
        if it['grupo_ejecutor'] != 'municipio':
            anio = int(it.get('primer_contrato_vigencia') or it['anio'])
            otros.append((it['ejecutor'], a26_prom(g, range(anio, max(anio, 2025) + 1)), it['bpin']))
            continue
        anio, f_c, f_alto, f_bajo, p2526 = deflactores(it)
        en_ejec = it.get('clase') != 'terminado'
        servicio = bool(SERVICIO_RE.search(it['nombre']))
        alertas = list(it.get('alertas_datos') or [])
        if it.get('estado_mapa') == 'Terminado' and (it.get('estado_gesproy') or '').upper().startswith('EN EJEC') and it['ej_fisica'] < 95:
            alertas.append(f"MapaInversiones lo da por terminado y GESPROY lo reporta en ejecución con {fmt(it['ej_fisica'])} % de avance físico")
        contradictorio = any('más que el valor aprobado' in a or 'MapaInversiones lo da por terminado' in a for a in alertas)
        multi = MULTI_POR_NOMBRE.get(it['bpin'])
        parte = multi['parte_yondo'] if multi else 1.0
        v_c, v_lo, v_hi = g / 1e6 / f_c, g / 1e6 / f_alto, g / 1e6 / f_bajo
        en_central = not (en_curso and en_ejec)
        en_min = en_central and not servicio and not contradictorio and not it.get('anio_en_bienio_compartido')
        tot['central'] += v_c if en_central else 0
        tot['min'] += v_lo * parte if en_min else 0
        tot['max'] += v_hi
        tot['corriente'] += g if en_central else 0
        etiqueta = ''
        if it['bpin'] in BPIN_EDU_YARUMAL:
            etiqueta = ' (EDU de Medellín y después E. D. T. de Yarumal)'
        elif it['bpin'] in BPIN_EDU:
            etiqueta = ' (EDU de Medellín)'
        fuente = (f"GESPROY y MapaInversiones, BPIN {it['bpin']} ({URL_GESPROY}, corte oct-2026): avance físico {fmt(it['ej_fisica'])} % "
                  f"y financiero {fmt(it['ej_financiera'])} %; {F_SGR}")
        d = item(frase_objeto(it['nombre'], 110) + etiqueta, anio, v_c if en_central else 0, fuente, en_total=en_central,
                 bpin=it['bpin'], valor_corriente=round(g), valor_rango=[r1(v_lo * parte if en_min else 0), r1(v_hi)],
                 valor_si_se_contara=r1(v_c),
                 recursos_del_proyecto=r1(a26(it['valor'], it['anio'])), recursos_del_proyecto_nota='valor total en GESPROY; puede incluir cofinanciación',
                 avance_fisico_pct=it['ej_fisica'], avance_financiero_pct=it['ej_financiera'], estado_gesproy=it.get('estado_gesproy'),
                 estado_mapa=it.get('estado_mapa'), subestado=' '.join(str(it.get('subestado') or '').split()),
                 en_ejecucion=en_ejec, servicio=servicio, anio_en_bienio_compartido=bool(it.get('anio_en_bienio_compartido')),
                 pagado_2025_2026_corriente=round(p2526), edu=it['bpin'] in BPIN_EDU)
        if multi:
            d['varios_municipios'] = multi['nota']
        if alertas:
            d['alertas_datos'] = alertas
        if en_curso and en_ejec:
            d['nota'] = 'Sigue en ejecución en el gobierno actual: la brecha puede cerrarse. No se suma.'
        items.append(d)
    items.sort(key=lambda x: -(x['valor_si_se_contara'] or 0))
    return tot, items, otros


def saldos(pid):
    """Plata quieta: último bienio cerrado dentro del periodo, presupuesto menos compromisos."""
    items, ctx, det, pendiente = [], [], '', None
    inc = FONDOS['INCENTIVO']['yondo_obtuvo']
    ail = FONDOS['AIL']['yondo_obtuvo']
    if pid == '2016-2019':
        b2 = SGR_AD['2017-2018']
        v = a26_mes(b2['sin_comprometer_sgr_chip_sep2018'], 2018, 9)
        items.append(item('Regalías del SGR presupuestadas y sin comprometer, bienio 2017–2018, corte de septiembre de 2018 (CHIP; todas las fuentes del capítulo SGR)',
                          2018, v, b2['fuente'], valor_corriente=b2['sin_comprometer_sgr_chip_sep2018'], fecha_corte='2018-09-30',
                          medida='presupuesto − compromisos', deflactor=f"IPC de sep-2018 ({fmt(IPC_MES[2018][8], 2)} / {fmt(IPC_BASE, 3)})"))
        b = SGR_AD['2015-2016']
        ctx.append(item('Bienio 2015–2016 (compartido con el gobierno anterior; no se suma a ninguno): presupuesto SGR sin comprometer al cierre de 2016 (CHIP)',
                        2016, a26_mes(b['sin_comprometer_sgr_chip'], 2016, 12), b['fuente'], en_total=False, valor_corriente=b['sin_comprometer_sgr_chip'],
                        fecha_corte='2016-12-31', medida='presupuesto − compromisos', cruza_dos_gobiernos=True))
        ctx.append(item('Bienio 2015–2016 (compartido; no se suma): regalías del SGR en caja sin comprometer al cierre de 2016, todas las fuentes; incluye saldos que venían de 2012–2014',
                        2016, a26_mes(b['saldo'], 2016, 12), b['fuente'], en_total=False, valor_corriente=b['saldo'], fecha_corte='2016-12-31',
                        medida='recaudo − compromisos (caja)', cruza_dos_gobiernos=True))
        ctx.append(item('Saldo de asignaciones directas sin aprobar acumulado 2012–junio de 2018 (SICODIS): otra medida (asignado − aprobado); no se suma',
                        2018, a26_mes(b2['saldo'], 2018, 6), b2['fuente'], en_total=False, valor_corriente=b2['saldo'], fecha_corte='2018-06-30',
                        medida='asignado − aprobado'))
        det = (f"Al corte de septiembre de 2018, tres meses antes de cerrar el bienio 2017–2018, quedaban {mm(v)} de regalías presupuestadas sin comprometer "
               f"(CHIP; no hay dato abierto al cierre de diciembre). Con otra medida, el saldo sin aprobar acumulado desde 2012 era {mm(a26_mes(b2['saldo'], 2018, 6))} "
               f"en junio de 2018; buena parte se aprobó en 2019, el año con más aprobaciones de la serie. El bienio 2015–2016 empezó en el gobierno anterior: "
               f"su saldo se muestra aparte ({mm(a26_mes(b['sin_comprometer_sgr_chip'], 2016, 12))} de presupuesto sin comprometer; {mm(a26_mes(b['saldo'], 2016, 12))} "
               f"en caja, que incluye plata heredada de 2012–2014).")
    elif pid == '2020-2023':
        b = SGR_AD['2021-2022']
        items += [
            item('Asignaciones directas presupuestadas y sin comprometer al cierre del bienio 2021–2022 (CHIP)', 2022, a26_mes(b['saldo'], 2022, 12), b['fuente'],
                 valor_corriente=b['saldo'], fecha_corte='2022-12-31', medida='presupuesto − compromisos'),
            item('Incentivo a la producción (lo aprueba el OCAD Paz) que pasó sin usar a 2023–2024', 2022,
                 a26_mes(inc['incentivos_al04_sin_usar_inicio_2023'], 2022, 12), f'https://www.datos.gov.co/d/5ka2-and2 (disponibilidad inicial 2023-2024); {F_SGR}',
                 valor_corriente=inc['incentivos_al04_sin_usar_inicio_2023'], fecha_corte='2022-12-31', medida='disponibilidad inicial del bienio siguiente'),
            item('Asignación para la Inversión Local presupuestada y sin comprometer, 2021–2022 (CHIP)', 2022, a26_mes(ail['sin_comprometer_2021_2022'], 2022, 12),
                 'https://www.datos.gov.co/d/xr2w-9eg2 y https://www.datos.gov.co/d/qkv4-ek54; ' + F_SGR,
                 valor_corriente=ail['sin_comprometer_2021_2022'], fecha_corte='2022-12-31', medida='presupuesto − compromisos'),
        ]
        b0 = SGR_AD['2019-2020']
        ctx.append(item('Saldo de asignaciones directas que pasó de 2019–2020 a 2021–2022 (foto anterior; no se suma)', 2020, a26_mes(b0['saldo'], 2020, 12), b0['fuente'],
                        en_total=False, valor_corriente=b0['saldo'], fecha_corte='2020-12-31', medida='disponibilidad inicial del bienio siguiente'))
        det = (f"Al cierre de 2022 quedaban sin comprometer {mm(items[0]['valor'])} de asignaciones directas, {mm(items[1]['valor'])} del incentivo a la producción "
               f"(sus proyectos los aprueba el OCAD Paz) y "
               f"{mm(items[2]['valor'])} de la Asignación para la Inversión Local. Además, {mmc(b['paso_al_siguiente_bienio_sin_pagar'], 2022)} comprometidos "
               f"pasaron sin pagar al bienio siguiente.")
    elif pid == '2024-2027':
        b0 = SGR_AD['2023-2024']
        items += [
            item('Asignaciones directas presupuestadas y sin comprometer al cierre del bienio 2023–2024 (CHIP)', 2024, a26_mes(b0['saldo'], 2024, 12), b0['fuente'],
                 valor_corriente=b0['saldo'], fecha_corte='2024-12-31', medida='presupuesto − compromisos', cruza_dos_gobiernos=True),
            item('Incentivo a la producción (lo aprueba el OCAD Paz) que pasó sin usar a 2025–2026', 2024, a26_mes(inc['incentivos_al04_sin_usar_inicio_2025'], 2024, 12),
                 f'https://www.datos.gov.co/d/5ka2-and2; {F_SGR}', valor_corriente=inc['incentivos_al04_sin_usar_inicio_2025'], fecha_corte='2024-12-31',
                 medida='disponibilidad inicial del bienio siguiente'),
            item('Asignación para la Inversión Local presupuestada y sin comprometer, 2023–2024 (CHIP)', 2024, a26_mes(ail['sin_comprometer_2023_2024'], 2024, 12),
                 F_SGR, valor_corriente=ail['sin_comprometer_2023_2024'], fecha_corte='2024-12-31', medida='presupuesto − compromisos'),
        ]
        b = SGR_AD['2025-2026']
        ail_sin = ail['presupuesto_2025_2026'] - ail['aprobado_2025_2026']
        pend_items = [
            item('Asignaciones directas sin aprobar en proyectos, bienio 2025–2026 (las aprueba el municipio)', 2026, b['saldo'] / 1e6, b['fuente'], en_total=False,
                 aprueba='municipio', fecha_corte=CORTE, medida='presupuesto − aprobado', en_curso=True),
            item('Asignación para la Inversión Local sin aprobar, 2025–2026 (la aprueba el municipio)', 2026, ail_sin / 1e6, f'{URL_MINHAC} (corte oct-2026); {F_SGR}',
                 en_total=False, aprueba='municipio', fecha_corte=CORTE, medida='presupuesto − aprobado', en_curso=True),
            item('Incentivo a la producción sin aprobar, 2025–2026 (bolsa IPAZ en MinHacienda): el municipio formula y presenta, el OCAD Paz (nacional) aprueba',
                 2026, inc['saldo_sin_aprobar'] / 1e6, f'{URL_MINHAC} (corte oct-2026); {F_SGR}', en_total=False, aprueba='OCAD Paz',
                 fecha_corte=CORTE, medida='presupuesto − aprobado', en_curso=True),
        ]
        ctx += pend_items
        pendiente = {'total': r1(sum(i['valor'] for i in pend_items)), 'aprueba_municipio': r1(pend_items[0]['valor'] + pend_items[1]['valor']),
                     'asignaciones_directas': r1(pend_items[0]['valor']),
                     'aprueba_ocad_paz': r1(pend_items[2]['valor']), 'en_caja_asignaciones_directas': r1(b['saldo_en_caja'] / 1e6), 'corte': CORTE,
                     'nota': 'Bienio abierto hasta diciembre de 2026: todavía se puede aprobar. No se suma a la plata quieta ni a "sin obra".'}
        if salvedad_ad(pendiente['asignaciones_directas']):
            pendiente['asignaciones_directas_posterior'] = dict(AD_SIN_APROBAR_POSTERIOR)
        det = (f"Al cierre del bienio 2023–2024 quedaban sin comprometer {mm(sum(i['valor'] for i in items))}, casi todo de asignaciones directas. Ese bienio "
               f"empezó en 2023, en el gobierno anterior: la mitad de su ejecución le corresponde a él, pero es el único bienio que ha cerrado en este periodo. "
               f"Aparte, y sin sumar: el bienio 2025–2026 sigue abierto y con corte del {fecha_corta(CORTE)} había {mm(pendiente['total'])} por aprobar, "
               f"{mm(pendiente['aprueba_municipio'])} que aprueba el municipio y {mm(pendiente['aprueba_ocad_paz'])} del incentivo a la producción que aprueba el "
               f"OCAD Paz." + frase_salvedad_ad(pendiente['asignaciones_directas']))
    elif pid == '2012-2015':
        det = ('No hay un saldo oficial al cierre del bienio 2013–2014, el último que cerró en este gobierno. El bienio 2015–2016 cruza dos gobiernos y se muestra '
               'aparte en 2016–2019, sin sumarlo a ninguno.')
    else:
        det = 'Antes de 2012 las regalías directas entraban al presupuesto municipal sin bolsas ni bienios: no hay saldos comparables.'
    return items, ctx, det, pendiente


def calcular_periodo(pid):
    anios = anios_de(pid)
    ap = PANEL_PER[pid]['agregados']
    ing = ap['ingresos_totales']['suma_mm_2026']
    anios_plata = ap['ingresos_totales']['anios_con_dato']
    propios = ap['tributarios']['suma_mm_2026']
    sec_anios = [a for a in anios if a in SECOP_ALC]
    fugas = []

    # --- A. estudios sin obra ------------------------------------------------
    E = {a: SECOP_ALC[a]['ajustes']['estudios'] for a in sec_anios}
    est = sum(a26(E[a]['central_valor'], a) for a in sec_anios)
    est_min = sum(a26(E[a]['minimo_valor'], a) for a in sec_anios)
    est_max = sum(a26(E[a]['maximo_valor'], a) for a in sec_anios)
    rec = sum(a26(E[a]['recientes_valor'], a) for a in sec_anios)
    planes = sum(a26(E[a]['planes_valor'], a) for a in sec_anios)
    est_sc = sum(a26(E[a]['sin_obra_valor_sin_competencia'], a) for a in sec_anios)
    mixtos = sum(a26(SECOP_ALC[a]['estudios']['sin_obra_valor'] - SECOP_ALC[a]['estudios']['sin_obra_valor_sin_mixtos'], a) for a in sec_anios)
    n_sin = sum(E[a]['sin_obra_n'] for a in sec_anios)
    n_eval = sum(SECOP_ALC[a]['estudios']['evaluados_n'] for a in sec_anios)
    n_con = sum(SECOP_ALC[a]['estudios']['con_obra_n'] for a in sec_anios)
    lista = [e for e in AJ['estudios_sin_obra_alcaldia'] if e['anio'] in anios]
    eitems = []
    for e in sorted(lista, key=lambda x: -x['valor']):
        c = contratista_publicable(e['contratista'])
        nota = ('Plan: no lleva a una obra directa (se resta en el mínimo).' if e['plan'] else None)
        if e['reciente']:
            nota = 'Firmado en los últimos 18 meses: su obra todavía puede no haberse firmado (pendiente; no se suma al central).'
        eitems.append(item(frase_objeto(e['objeto']) + (f' ({c})' if c else ''), e['anio'], a26(e['valor'], e['anio']), e['url'], en_total=not e['reciente'],
                           valor_corriente=e['valor'], modalidad=e['modalidad'], sin_competencia=e['sin_competencia'],
                           similitud_maxima_con_una_obra=e['similitud_maxima_con_una_obra'], **({'nota': nota} if nota else {})))
    fuera = [e for e in AJ['estudios_obra_hallada_fuera'] if e['anio'] in anios]
    for e in fuera:
        eitems.append(item(e['etiqueta'][:1].upper() + e['etiqueta'][1:] + ' — no se cuenta: ' + {'obra_posterior': 'su obra consta fuera del SECOP de la alcaldía',
                                                                                   'obra_suspendida': 'hubo obra y quedó suspendida',
                                                                                   'no_es_estudio_previo': 'no es un estudio previo a una obra'}[e['motivo']],
                           e['anio'], a26(e['valor'], e['anio']), e['url'], en_total=False, valor_corriente=e['valor'], evidencia=e['evidencia']))
    det = (f"{n_sin} estudios o consultorías de la alcaldía sin obra posterior hallada en su SECOP, de {n_eval} evaluados ({n_con} con obra según la regla de palabras). "
           f"{mm(est_sc)} de ellos se contrataron sin competencia.")
    if fuera:
        det += (' No se cuentan ' + '; '.join(f"los {e['etiqueta']}, {mmc(e['valor'], e['anio'])}" if e['etiqueta'].startswith('estudios') else f"el {e['etiqueta']}, {mmc(e['valor'], e['anio'])}" for e in fuera)
                + ': su obra consta fuera del SECOP de la alcaldía, se suspendió o no son estudios previos (fugas_secop.json, estudios_obra_hallada_fuera).')
    if mixtos >= 0.5:
        det += f" Tampoco los contratos mixtos de diseño y obra ({mm(mixtos)}): su obra va dentro del contrato o ya está en 'pagos por delante del avance'."
    if planes >= 0.5:
        det += f" Incluye {mm(planes)} de planes (ordenamiento, desarrollo, gestión del riesgo): no llevan a una obra, pero se pagaron; el mínimo los resta."
    if rec >= 0.5:
        det += f" {mm(rec)} son estudios de los últimos 18 meses: quedan como pendientes y solo entran en el máximo."
    if pid == '2004-2007':
        det = f'SECOP no tiene estudios de la alcaldía en estos años (solo {N_ALC_2007} contratos en 2007). Sin dato: no significa que no hubo estudios sin obra.'
    fugas.append(fuga('estudios_sin_obra', est, min(est_min, est), max(est_max, est), det, eitems, [F_FUGAS, URL_SECOP, F_ANEXO_A + ' (§8)'],
                      sin_dato=(pid == '2004-2007'), mixtos_excluidos=r1(mixtos), recientes_pendientes=r1(rec), planes=r1(planes)))

    # --- B. pagos por delante del avance -------------------------------------
    g, gitems, otros = girado_sin_avance(pid)
    gsa = g['central']
    det = ''
    if gitems:
        en_tot = [i for i in gitems if i['en_total']]
        edu = sum(i['valor'] for i in en_tot if i['edu'])
        det = (f"{len(en_tot)} proyectos de regalías con ejecutor municipal tienen pagos por encima del avance reportado en GESPROY a octubre de 2026 "
               f"(${fmt(g['corriente'] / 1e6)} M en pesos corrientes de cada pago; {mm(gsa)} de 2026).")
        if edu:
            det += f" {mm(edu)} corresponden a proyectos que el municipio delegó en la EDU de Medellín."
        ej = [i for i in en_tot if i['en_ejecucion']]
        v_ej = sum(i['valor'] for i in ej)
        if ej:
            det += (f" {mm(gsa - v_ej)} están en proyectos ya terminados, donde la brecha no se cierra con más obra, y {mm(v_ej)} en "
                    f"{plural(len(ej), 'proyecto que sigue', 'proyectos que siguen')} en ejecución: ahí la brecha puede cerrarse y parte puede ser un anticipo legal.")
        p2526 = sum(i['pagado_2025_2026_corriente'] for i in en_tot)
        if p2526 and pid != '2024-2027':
            det += (f" De lo pagado en estos proyectos, {mmc(p2526, '2025–2026')} se pagaron en 2025–2026 (MinHacienda), en el gobierno siguiente: la brecha se "
                    f"atribuye al gobierno que aprobó y contrató, no al que pagó.")
        serv = [i for i in en_tot if i['servicio']]
        if serv:
            det += f" {plural(len(serv), 'es un servicio', 'son servicios')} (alimentación o transporte escolar, atención primaria): ahí el avance es de entrega, no de obra."
        alerta = [i for i in gitems if i.get('alertas_datos')]
        if alerta:
            det += f" {plural(len(alerta), 'tiene', 'tienen')} alertas de datos (registros que no coinciden entre GESPROY y MapaInversiones); el mínimo excluye los contradictorios."
        if any(i.get('varios_municipios') for i in gitems):
            det += ' El proyecto de vivienda 2022003050005 es de tres municipios (Puerto Nare, Yolombó y Yondó; 60 de 150 viviendas en Yondó): el mínimo cuenta solo esa parte.'
        if pid == '2024-2027':
            nn = [i for i in gitems if not i['en_total']]
            det += f" No se suman {plural(len(nn), 'proyecto que sigue', 'proyectos que siguen')} en ejecución en el gobierno actual ({mm(sum(i['valor_si_se_contara'] for i in nn))})."
    if otros:
        det += ' No se suman (ejecutor nacional): ' + '; '.join(f"{'INVÍAS' if 'NACIONAL DE VIAS' in e.upper() else e.title()} {mm(v)} (BPIN {b}, vías terciarias PDET del OCAD Paz)" for e, v, b in otros) + '.'
    if pid in ('2004-2007', '2008-2011'):
        det = 'Antes de 2012 no hay registro abierto de proyectos de regalías con avance físico (BPIN): no se puede saber en qué obras terminó cada peso del régimen anterior.'
    elif not gitems:
        det = 'Ningún proyecto de regalías aprobado en este periodo tiene pagos por encima del avance de obra.' + (det if otros else '')
    det += ' Para la plata propia (no regalías) no hay datos abiertos de avance físico: SECOP I no publica pagos y SECOP II no publica avance de obra.'
    fugas.append(fuga('girado_sin_avance', gsa, g['min'], g['max'], det.strip(), gitems, [F_SGR, URL_GESPROY, 'docs/01-diagnostico-sectorial.md', F_ANEXO_A + ' (§8)'],
                      sin_dato=pid in ('2004-2007', '2008-2011'), valor_corriente=round(g['corriente']), corte_avance='2026-10-21',
                      valor_terminados=r1(sum(i['valor'] for i in gitems if i['en_total'] and not i['en_ejecucion'])),
                      valor_en_ejecucion=r1(sum(i['valor'] for i in gitems if i['en_total'] and i['en_ejecucion'])),
                      certeza=('hecho con cálculo: valor × (avance financiero − avance físico) sobre GESPROY a octubre de 2026; el valor en pesos de 2026 '
                               'depende de cuándo se pagó (rango)'),
                      no_sumado_ejecutor_nacional=r1(sum(v for _, v, _ in otros))))

    # --- C. plata quieta (saldos de regalías) --------------------------------
    sal_items, sal_ctx, sal_det, pendiente = saldos(pid)
    sal = sum(i['valor'] for i in sal_items)
    fugas.append(fuga('saldos_regalias', sal, None, None, sal_det, sal_items + sal_ctx, [F_SGR, URL_MINHAC, 'https://sicodis.dnp.gov.co', 'https://www.chip.gov.co'],
                      sin_dato=pid == '2012-2015', no_aplica=pid in ('2004-2007', '2008-2011'), certeza='hecho (foto de un saldo; no es plata perdida)',
                      **({'pendiente_por_aprobar': pendiente} if pendiente else {})))

    # --- D. costo posible de contratar sin competencia -----------------------
    priv = uo_v = dups = sincomp = valor_alc = tr_tot = tr_cov = tr_sin = subs = edu_b = 0.0
    anios_tr_sin = []
    for a in sec_anios:
        r = SECOP_ALC[a]
        bs = r['ajustes']['base_sobrecosto']
        priv += a26(bs['sin_competencia_valor'] + bs['un_oferente_valor'], a)
        uo_v += a26(bs['un_oferente_valor'], a)
        dups += a26(bs['duplicados_valor'], a)
        edu_b += a26(bs['edu_valor'], a)
        sincomp += a26(r['sin_competencia']['valor'], a)
        valor_alc += a26(r['valor'], a)
        subs += a26(r['ajustes']['subsidios_tarifas']['valor'], a)
        for dest, ent in (('aguas', 'Aguas y Aseo'), ('hospital', 'Hospital')):
            t = r['ajustes']['transferencias'][dest]
            tval = t['sin_competencia_valor'] - t['subsidios_valor']
            tr_tot += a26(t['valor'], a)
            if tval <= 0:
                continue
            er = SECOP_ENT.get((ent, a))
            if er and er['contratos'] >= 5:
                e_v = er['ajustes']['propios_sin_competencia_sin_ops_valor']
                tr_cov += a26(min(tval, e_v), a)
            else:
                tr_sin += a26(tval, a)
                anios_tr_sin.append(a)
    base1 = max(0.0, priv - gsa)
    base = base1 + tr_cov
    central = base * SOBRECOSTO['central']
    g_max_no_edu = sum(i['valor_rango'][1] for i in gitems if not i['edu'])
    mn = max(0.0, priv - dups - edu_b - g_max_no_edu) * SOBRECOSTO['min']   # sin la EDU (y sin su brecha, que va dentro de sus convenios)
    mx = (max(0.0, priv - g['min']) + tr_cov) * SOBRECOSTO['max']
    uo_c = min(central, uo_v * SOBRECOSTO['central'])
    pct_sc = 100 * sincomp / valor_alc if valor_alc else None
    conv = [c for c in FUGAS['convenios_delegada'] if c['entidad'] == 'Alcaldía' and c['anio'] in anios
            and not re.search(r'Aguas y Aseo|Hospital|E\.S\.E', c['contratista']) and 'SUBSIDI' not in c['objeto'].upper()]
    citems = []
    for c in sorted(conv, key=lambda c: -c['valor'])[:3]:
        n = contratista_publicable(c['contratista'])
        citems.append(item(f"Contrato de referencia de la base (no se afirma sobrecosto en él): {frase_objeto(c['objeto'], 100)}" + (f' — {n}' if n else ''),
                           c['anio'], a26(c['valor'], c['anio']), c['url'], en_total=False, valor_corriente=c['valor']))
    det = (f"Hecho: la alcaldía contrató {mm(sincomp)} sin competencia ({fmt(pct_sc, 1)} % de {mm(valor_alc)}, pesos de 2026; SECOP). "
           f"Línea 1, compras a terceros: {mm(priv)}" + (f", de ellos {mm(uo_v)} en procesos competitivos con un solo oferente" if uo_v >= 0.5 else '')
           + (f"; se restan {mm(min(gsa, priv))} ya contados en pagos por delante del avance" if gsa >= 0.5 else '') + f"; base {mm(base1)}.")
    if edu_b >= 0.5:
        det += (f" La línea 1 incluye {mm(edu_b)} de convenios con la EDU de Medellín, empresa pública de otro municipio que Yondó escogió sin "
                f"competencia; la EDU contrató después por su cuenta y sus contratos derivados de 2021–2023 no figuran en SECOP con el nombre de Yondó, "
                f"así que no se sabe si compitieron. El mínimo no cuenta la EDU.")
    if tr_tot >= 0.5:
        det += (f" Las transferencias a Aguas y Aseo, al hospital y a otras entidades de Yondó ({mm(tr_tot)}" + (f", de ellos {mm(subs)} de subsidios a las tarifas" if subs >= 0.5 else '')
                + ') no son compras y salen de esa base.')
    if tr_cov >= 0.5:
        det += f" Línea 2: de lo transferido, {mm(tr_cov)} pudo contratarse sin competencia por esas entidades (acotado por lo que contrataron así ese año)."
    if tr_sin >= 0.5:
        det += (f" Para {mm(tr_sin)} transferidos en años sin datos de Aguas y Aseo o del hospital en SECOP ({', '.join(str(x) for x in sorted(set(anios_tr_sin)))}) "
                f"no hay dato y no se estima nada.")
    det += (f" Costo posible: 6 % de la base, {mm(central)}" + (f" ({mm(base1 * SOBRECOSTO['central'])} por compras a terceros y "
                                                              f"{mm(tr_cov * SOBRECOSTO['central'])} por lo transferido)" if tr_cov >= 0.5 else '')
            + "; rango 3–10 %. No prueba corrupción: mide el precio usual de renunciar a la competencia.")
    if dups >= 0.5:
        det += f" El mínimo quita {mm(dups)} de posibles registros duplicados no verificados."
    if pid == '2004-2007':
        det = f'Solo hay {N_ALC_2007} contratos de la alcaldía en SECOP, todos de 2007. ' + det
    if pid == '2008-2011':
        cob = [COBERTURA[a]['Alcaldía'] for a in range(2008, 2012)]
        det += f' SECOP está subregistrado en estos años ({min(cob)} a {max(cob)} contratos por año): la base real fue mayor.'
    if pid in ('2020-2023', '2024-2027'):
        uo_n = sum(SECOP_ALC[a]['un_oferente']['un_oferente_n'] for a in sec_anios)
        uo_d = sum(SECOP_ALC[a]['un_oferente']['procesos_competitivos_con_dato'] for a in sec_anios)
        det += f" En {uo_n} de los {uo_d} procesos competitivos con dato de SECOP II hubo un solo oferente (este dato no existe para gobiernos anteriores)."
    if pid == '2020-2023':
        edu_v = sum(a26(SECOP_ALC[a]['convenios']['edu_valor'], a) for a in sec_anios)
        det += f" Los convenios con la EDU de Medellín ({mm(edu_v)}) fueron el {pct(edu_v, valor_alc)} % del valor contratado."
    if pid == '2024-2027':
        det += ' Datos de 2024 a octubre de 2026.'
    fugas.append(fuga('sobrecosto_sin_competencia', central, mn, mx, det, citems,
                      [F_FUGAS, URL_SECOP] + [x['url'].split(' ;')[0] for x in LIT_SOBRECOSTO[:2]],
                      base_hecho=r1(base), base_compras_terceros=r1(base1), base_transferencias=r1(tr_cov), transferencias_sin_dato=r1(tr_sin),
                      base_edu=r1(edu_b), costo_compras_terceros=r1(base1 * SOBRECOSTO['central']), costo_transferencias=r1(tr_cov * SOBRECOSTO['central']),
                      transferencias_total=r1(tr_tot), subsidios_tarifas=r1(subs), un_oferente_base=r1(uo_v), valor_un_oferente=r1(uo_c),
                      valor_sin_competencia_hecho=r1(sincomp), pct_valor_sin_competencia=r1(pct_sc)))

    # --- E. OPS por encima de lo usual (indicio) -----------------------------
    ex = {'central': 0.0, 'min': 0.0, 'max': 0.0, 'neto': 0.0}
    oitems = []
    ops_n = ops_val = form_n = form_v = ops_n_orig = rec_n = rec_v = dup_v = 0
    for a in sec_anios:
        r = SECOP_ALC[a]
        o = ops_aj(a)
        v = a26(o['valor'], a)
        ops_n += o['n']
        ops_n_orig += r['ops']['n']
        ops_val += v
        form_n += o['formulacion_n']
        form_v += a26(o['formulacion_valor'], a)
        rec_n += o['reclasificadas_n']
        rec_v += a26(o['reclasificadas_valor'], a)
        dup_v += a26(o['duplicados_valor'], a)
        if not o['n']:
            continue
        ref = OPS_REF['mediana'] * POB[a] / 1e6
        e_c = max(0.0, v - ref)
        ex['central'] += e_c
        ex['neto'] += v - ref
        ex['min'] += max(0.0, v - OPS_REF['p75'] * POB[a] / 1e6)
        ex['max'] += max(0.0, v - OPS_REF['p25'] * POB[a] / 1e6)
        pers = IND['ops_personas']['serie'].get(str(a))
        if e_c > 0:
            oitems.append(item(f"OPS {a}: {o['n']} contratos{f', {fmt(pers)} personas' if pers else ''}, {mm(v)} ({fmt(v * 1e6 / POB[a])} pesos de 2026 por habitante, "
                               f"{fmt(v * 1e6 / POB[a] / OPS_REF['mediana'], 1)} veces la mediana)", a, e_c,
                               f'{F_FUGAS} (por_anio, Alcaldía, ajustes.ops); población DANE en {F_PANEL}'))
    det = (f"{fmt(ops_n)} contratos OPS por {mm(ops_val)} de 2026, de ellos {fmt(form_n)} de formulación de proyectos por {mm(form_v)}. "
           f"Referencia: {fmt(OPS_REF['mediana'])} pesos de 2026 por habitante al año (mediana de Yondó en 2012–2025; rango entre el percentil 25, "
           f"{fmt(OPS_REF['p25'])}, y el 75, {fmt(OPS_REF['p75'])}; esos años mezclan SECOP I, hasta 2023, y SECOP II, desde 2024). "
           f"Suma de los años por encima: {mm(ex['central'])}; desviación neta del periodo (los años por debajo restan): {mm(ex['neto'])}. ") if sec_anios else ''
    if rec_n:
        det += (f"{'Se quitó' if rec_n == 1 else 'Se quitaron'} {plural(rec_n, 'contrato', 'contratos')} que la clasificación ponía en OPS pero no {'es' if rec_n == 1 else 'son'} prestación de servicios ({mm(rec_v)}: transferencias a Aguas y Aseo o al "
                f"hospital, subsidios a tarifas y convenios para aunar esfuerzos)" + (f" y {mm(dup_v)} de registros duplicados" if dup_v >= 0.5 else '') + '. ')
    det += 'Es un indicio para comparar con la planta de personal: los contratistas prestaron servicios.'
    if pid == '2004-2007':
        det = 'SECOP no registra OPS de la alcaldía en estos años. Sin dato.'
    if pid == '2008-2011':
        det += ' SECOP está incompleto antes de 2012: la comparación con años posteriores no es confiable.'
    if pid == '2024-2027':
        det += ' 2026 va hasta octubre. Desde 2024 la alcaldía publica en SECOP II (antes, en SECOP I): un cambio de registro puede afectar la comparación.'
    fugas.append(fuga('ops_nomina_paralela', ex['central'], ex['min'], ex['max'], det, oitems, [F_FUGAS, URL_SECOP, 'Corte Constitucional, Sentencia C-614 de 2009'],
                      sin_dato=(pid == '2004-2007'), certeza='estimado (indicio por revisar)', desviacion_neta=r1(ex['neto']),
                      ops_contratos=ops_n, ops_contratos_sin_ajuste=ops_n_orig, ops_valor=r1(ops_val), ops_reclasificadas_contratos=rec_n,
                      ops_reclasificadas_valor=r1(rec_v), ops_formulacion_contratos=form_n, ops_formulacion_valor=r1(form_v)))

    # --- F. recaudo propio ------------------------------------------------
    rc = RECAUDO[pid]
    med = rc['predial']['mediana_7']['dejado_de_recaudar_mm_2026'] + rc['ica']['mediana_7']['dejado_de_recaudar_mm_2026']
    p75_pred = rc['predial']['p75_7']['dejado_de_recaudar_mm_2026']
    p75_ica = rc['ica']['p75_7']['dejado_de_recaudar_mm_2026']
    anios_cat = [a for a in anios if 2021 <= a <= 2023] if pid == '2020-2023' else ([2024] if pid == '2024-2027' else [])
    cat_v = CATASTRO['adicional_anual_mm_2026'] * len(anios_cat)
    mx_r = max(p75_pred, cat_v) + p75_ica
    dif = rc['predial']['mediana_7']['diferencia_mm_2026'] + rc['ica']['mediana_7']['diferencia_mm_2026']
    det = f"Frente a la mediana de 7 comparables Yondó recaudó {mm(-dif)} más en predial e ICA (pesos de 2026, suma del periodo). "
    bajos = [a for a in RECAUDO_BAJO.get('ica', []) + RECAUDO_BAJO.get('predial', []) if a in anios]
    if bajos:
        det += (f"En {' y '.join(str(a) for a in sorted(set(bajos)))} el ICA por habitante estuvo por debajo de la mediana; esa brecha se compensa con los años en que "
                f"recaudó más (la comparación es por periodo, no año por año). ")
    if cat_v:
        cat_t = f"el predial con catastro actualizado ({mm(cat_v)} en {len(anios_cat)} año{'s' if len(anios_cat) > 1 else ''})"
        det += (f"Máximo ({mm(mx_r)}): " + (f"en predial, el mayor entre la brecha con el percentil 75 de los comparables ({mm(p75_pred)}) y {cat_t}" if p75_pred > 0
                                            else f"{cat_t}; frente al percentil 75 de los comparables no hay brecha de predial")
                + (f", más la brecha de ICA con el percentil 75 ({mm(p75_ica)})" if p75_ica > 0 else '') + '.')
    elif p75_pred + p75_ica > 0:
        det += f'Máximo: brecha con el percentil 75 de los comparables ({mm(p75_pred + p75_ica)}).'
    else:
        det += 'Tampoco hay brecha frente al percentil 75.'
    if pid == '2024-2027':
        det += ' Solo 2024 tiene dato comparable; en 2025 el predial subió a $3.044 M (pesos corrientes de 2025, CUIPO).'
    det += ' La extracción de petróleo no paga ICA por ley (art. 16 del Código de Petróleos; art. 39 de la Ley 14 de 1983): no es recaudo perdido.'
    fugas.append(fuga('recaudo_no_cobrado', med, 0, mx_r, det, [], [F_CNH + ' (recaudo_potencial)', 'https://terridata.dnp.gov.co']))

    # --- G. tasa retributiva evitable ----------------------------------------
    tv = sum(TASA[a]['tasa_fr1_mm_2026'] * (MESES_2026 / 12 if a == 2026 else 1) for a in anios if a in TASA) * TASA_EVITABLE
    fac = TASA_INFO['anual_2026_por_caudal_medido_fr1_mm'][1] / TASA_INFO['anual_2026_fr1_mm']
    det = (f"Yondó no tiene PTAR: en 2019 vertía 55,34 L/s sin tratar (Superservicios, 2020). Se cuenta el 80 % de la tasa estimada con factor regional 1, la parte "
           f"que una PTAR evitaría; con el caudal medido en 2019 sería hasta {fmt(fac, 2)} veces. La paga Aguas y Aseo, no la alcaldía. En 2020 Aguas y Aseo debía "
           f"$175 M (pesos corrientes de 2020) a Corantioquia por tasas desde 2018 (hecho).") if tv else ''
    if pid == '2024-2027' and tv:
        det += ' 2026 se cuenta por 10 meses.'
    if pid in ('2004-2007', '2008-2011', '2012-2015', '2016-2019') and tv:
        det += ' El caudal medido en 2019 se aplica también a estos años.'
    fugas.append(fuga('costo_vertimientos', tv, tv, tv * fac, det, [], [F_CNH + ' (aguas_residuales)',
                      'https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf'],
                      quien_paga='Aguas y Aseo de Yondó S.A. E.S.P.'))

    # --- H. fondos externos no obtenidos -------------------------------------
    fitems, flist = [], []
    oxi = FONDOS['OXI']
    f_oxi = statistics.mean(IPC[a] for a in range(2018, 2026))
    parte_oxi = {'2016-2019': 2 / 6, '2020-2023': 4 / 6}

    def add_fondo(clave, nombre, c, mn_, mx_, comparable, suma=True, desde=None, nota=None):
        f = FONDOS[clave]
        flist.append({'fondo': nombre, 'desde': desde or f['desde'], 'monto_referencia': r1(c), 'min': r1(mn_), 'max': r1(mx_),
                      'comparable': comparable, 'fuente': '; '.join(f.get('evidencia', [])[:2]) + f'; {F_SGR}', 'suma_en_total': suma,
                      **({'nota': nota} if nota else {})})
        if suma:
            fitems.append(item(nombre, None, c, '; '.join(f.get('evidencia', [])[:1]) + f'; {F_SGR}', min=r1(mn_), max=r1(mx_)))
    if pid == '2008-2011':
        f = FONDOS['ADAPTACION']
        pn = next(c for c in f['comparables'] if c['municipio'] == 'Puerto Nare')
        yo = f['yondo_obtuvo']
        n_yo = re.search(r'(\d+) intervenciones', yo['texto'])
        add_fondo('ADAPTACION', 'Fondo Adaptación (ola invernal 2010–2011)', 0, 0, f['monto_referencia_max'] / 1e6 / IPC[2015],
                  (f"Puerto Nare, ribereño y de tamaño parecido, recibió ${fmt(pn['monto'] / 1e6)} M (pesos corrientes de 2012–2018) en {pn['intervenciones']} "
                   f"intervenciones; Yondó, ${fmt(yo['monto'] / 1e6)} M (pesos corrientes) en {n_yo.group(1) if n_yo else 'pocas'}. Baja certeza: no se verificó "
                   f"que Yondó registrara daños."))
    if pid in parte_oxi:
        pares = [c for c in oxi['comparables'] if isinstance(c.get('monto'), (int, float))]
        med_pares = statistics.median(c['monto'] for c in pares)
        con_proy = sorted((c for c in pares if c['monto']), key=lambda c: -c['monto'])
        add_fondo('OXI', 'Obras por Impuestos (proyecto vial propio, si una empresa contribuyente lo escogía)',
                  oxi['monto_referencia_min'] / 1e6 / f_oxi * parte_oxi[pid], 0, oxi['monto_referencia_max'] / 1e6 / f_oxi * parte_oxi[pid],
                  (f"Ventana 2018–2023 ({'2 de 6 años' if pid == '2016-2019' else '4 de 6 años'} en este gobierno). Entre los proyectos aprobados (ART 2018–2025) Yondó "
                   f"solo tuvo uno, de dotación escolar con Ecopetrol en {OXI_2019['anio']} ({mmc(OXI_2019['valor'], OXI_2019['anio'])}). De {len(pares)} municipios "
                   f"comparables, {sum(1 for c in pares if not c['monto'])} no tuvieron proyecto propio (mediana de los pares: {mm(med_pares / 1e6)}); "
                   + '; '.join(f"{c['municipio']} tuvo uno de ${fmt(c['monto'] / 1e6)} M" for c in con_proy) + " (pesos corrientes). "
                   f"En {OXI_2024['anio']} llegó la vía El Paraíso–La Raya–Las Lomas ({mmc(OXI_2024['valor'], OXI_2024['anio'])}, según la ART). Depende de que una "
                   f"empresa escoja el proyecto."), desde=2018)
    if pid == '2020-2023':
        f = FONDOS['MINTIC']
        sedes = [c['sedes'] for c in f['comparables'] if c.get('sedes')]
        add_fondo('MINTIC', 'MinTIC – Centros Digitales rurales', f['monto_referencia_central'] / 1e6 / IPC[2023], f['monto_referencia_min'] / 1e6 / IPC[2023],
                  f['monto_referencia_max'] / 1e6 / IPC[2023],
                  (f"Yondó tiene {f['yondo_obtuvo']['sedes']} sedes conectadas; sus {len(sedes)} comparables, entre {min(sedes)} y {max(sedes)} (corte oct-2023). "
                   f"El valor por sede (${fmt(f['monto_referencia_min'] / 1e6, 1)} M, pesos corrientes de 2023) es la inversión que registra MinTIC, un estándar del "
                   f"programa, no un costo medido en Yondó."))
    if pid in ('2016-2019', '2020-2023', '2024-2027'):
        f = FONDOS['COOPERACION']
        add_fondo('COOPERACION', 'Cooperación internacional no reembolsable', f['monto_referencia_min'] / 1e6 / IPC[2024], 0, f['monto_referencia_max'] / 1e6 / IPC[2024],
                  (f"En el registro de APC solo aparece una donación de Japón para Yondó (2014, US${fmt(COOP_USD)}); la Unión Europea financió proyectos en 5 "
                   f"municipios del Sur de Bolívar (2016, US${fmt(COOP_UE_USD / 1e6, 2)} millones). Baja certeza."))
    if pid == '2012-2015':
        f = FONDOS['COOPERACION']
        add_fondo('COOPERACION', 'Cooperación internacional no reembolsable', 0, 0, f['monto_referencia_max'] / 1e6 / IPC[2024],
                  (f"Central 0: en 2014 Yondó sí recibió una donación de Japón (US${fmt(COOP_USD)}, vía de la vereda Caño Bodegas; APC). El máximo es la parte de un "
                   f"municipio en un proyecto regional de la Unión Europea."))
    if pid == '2024-2027':
        f = FONDOS['OCAD_PAZ']
        add_fondo('OCAD_PAZ', 'OCAD Paz – Asignación para la Paz (municipios PDET)', f['monto_referencia_central'] / 1e6 / statistics.mean([IPC[2025], IPC[2026]]),
                  0, f['monto_referencia_max'] / 1e6 / statistics.mean([IPC[2025], IPC[2026]]),
                  (f"En 2025–2026 el OCAD Paz aprobó ${fmt(f['yondo_obtuvo']['aprobado_2025_2026'] / 1e6)} M para Yondó y "
                   f"${fmt(next(c['monto'] for c in f['comparables'] if c['municipio'] == 'Cantagallo') / 1e6)} M para Cantagallo (pesos corrientes); la central es la "
                   f"mediana de los pares del Sur de Bolívar menos lo de Yondó. Todavía se puede gestionar."))
        f = FONDOS['FENOGE']
        add_fondo('FENOGE', 'FENOGE – hospital o sedes públicas con solar', (f['monto_referencia_min'] + f['monto_referencia_max']) / 2 / 1e6 / IPC[2025],
                  f['monto_referencia_min'] / 1e6 / IPC[2025], f['monto_referencia_max'] / 1e6 / IPC[2025],
                  (f"En 2025 FENOGE dejó autosuficiente con 230 kWp el hospital de Simití, en la misma subregión PDET "
                   f"(${fmt(next(c['monto'] for c in f['comparables'] if c['municipio'] == 'Simití') / 1e6)} M, pesos corrientes de 2025). En Yondó no se halló ningún proyecto."))
    if pid in ('2020-2023', '2024-2027'):
        f = FONDOS['FINDETER']
        flist.append({'fondo': 'Findeter – crédito con tasa compensada', 'desde': f['desde'], 'monto_referencia': r1(f['monto_referencia_min'] / 1e6 / IPC[2024]),
                      'min': r1(f['monto_referencia_min'] / 1e6 / IPC[2024]), 'max': r1(f['monto_referencia_max'] / 1e6 / IPC[2024]),
                      'comparable': 'Capacidad de crédito prudente (20–40 % de los ingresos corrientes de 2024); Yondó no pagó intereses de deuda en 2020–2024. Es crédito: no se suma.',
                      'fuente': f'data/fuentes/serie_fiscal_oec.csv; {F_SGR}', 'suma_en_total': False})
    if pid in ('2020-2023', '2024-2027'):
        f = FONDOS['INCENTIVO']
        pares = [c for c in f['comparables'] if c.get('pct_aprobado') is not None]
        pp = sorted(c['pct_aprobado'] for c in pares)
        yo_pct = 100 * f['yondo_obtuvo']['aprobado_2025_2026'] / f['yondo_obtuvo']['presupuesto_2025_2026']
        texto_pares = (f"Pares (bolsa IPAZ 2025–2026, corte oct-2026): " + ', '.join(f"{c['municipio']} {fmt(c['pct_aprobado'], 1)} %" for c in sorted(pares, key=lambda c: c['pct_aprobado']))
                       + f". Mediana {fmt(statistics.median(pp), 1)} %, rango {fmt(min(pp), 1)}–{fmt(max(pp), 1)} %; Yondó {fmt(yo_pct, 1)} %. En la mitad de los pares la bolsa está casi sin aprobar: "
                       f"Yondó está por debajo de la mediana, pero no es un caso aislado.")
        flist.append({'fondo': 'Incentivo a la producción (lo aprueba el OCAD Paz; bolsa IPAZ en MinHacienda), con la línea "Territorios energéticos" (hasta 2 proyectos y $8.000 M por municipio, pesos corrientes de 2025)', 'desde': f['desde'],
                      'monto_referencia': r1((f['yondo_obtuvo']['incentivos_al04_sin_usar_inicio_2023'] / 1e6 / factor_mes(2022, 12)) if pid == '2020-2023' else f['yondo_obtuvo']['saldo_sin_aprobar'] / 1e6),
                      'comparable': (f"Del incentivo a la producción pasaron sin usar {mmc(f['yondo_obtuvo']['incentivos_al04_sin_usar_inicio_2021'], 2020)} a 2021–2022 "
                                     f"y {mmc(f['yondo_obtuvo']['incentivos_al04_sin_usar_inicio_2023'], 2022)} a 2023–2024. Ya era plata de Yondó: se cuenta como plata quieta."
                                     if pid == '2020-2023' else texto_pares + ' Ya es plata asignada a Yondó: se muestra como "por aprobar".'),
                      'fuente': f'{URL_MINHAC}; {F_SGR}', 'suma_en_total': False})
    fv = sum(i['valor'] for i in fitems)
    fmn = sum(i['min'] for i in fitems)
    fmx = sum(i['max'] for i in fitems)
    det = {'2004-2007': 'Sin fondos comparables identificados para estos años.',
           '2008-2011': 'Fondo Adaptación con central cero: depende de daños de 2010–2011 que no se verificaron.',
           '2012-2015': 'Solo cooperación internacional, con central cero: en 2014 Yondó recibió una donación de Japón.',
           '2016-2019': 'Obras por Impuestos empezó en 2018 (dos años de la ventana caen en este gobierno); Yondó no tuvo un proyecto vial propio hasta 2024.',
           '2020-2023': 'En el OCAD Paz Yondó sí consiguió plata (el problema fue ejecutarla). Lo que no se obtuvo fue Obras por Impuestos viales y Centros Digitales.',
           '2024-2027': 'Periodo en curso: el OCAD Paz y FENOGE todavía se pueden gestionar antes de 2027.'}[pid]
    fugas.append(fuga('fondos_no_gestionados', fv, fmn, fmx, det + ' Findeter no se suma (es crédito).' if pid in ('2020-2023', '2024-2027') else det,
                      fitems, [F_SGR], sin_dato=not flist))

    # --- I. beneficio solar no capturado -------------------------------------
    s = SOLAR.get(pid)
    if s:
        c = s['solo_solar']['central']
        rng = s['solo_solar']['rango_neto_con_residual']
        neto = c['neto_hasta_2026_con_valor_residual'] / 1e6
        neto_sr = c['neto_hasta_2026_sin_valor_residual'] / 1e6
        resid = c['valor_residual_2026'] / 1e6
        valor = max(0.0, neto)
        det = (f"Instalar 469 kWp en {s['anio_instalacion']} costaba {mm(c['inversion_cop_2026'] / 1e6)} de 2026. Hasta 2026 el ahorro en facturas, menos la inversión y el "
               f"mantenimiento, daría {mm(neto_sr)}; el equipo conservaría un valor de {mm(resid)}; beneficio neto: {mm(neto)}"
               + (f" (se pagaba solo en {c['anio_recuperacion']})." if c.get('anio_recuperacion') else '.'))
        if neto <= 0:
            det += ' No se habría pagado: la solar era unas 7 veces más cara que en 2024. Se registra cero.'
        elif neto_sr < 0:
            det += ' En caja todavía no se habría pagado: el beneficio sale sobre todo del valor del equipo.'
        if pid == '2024-2027':
            det += f' Hoy cada año de espera cuesta unos {mm(ESPERA_SOLAR)} en facturas.'
        fugas.append(fuga('ahorro_solar', valor, max(0.0, rng[0] / 1e6), max(0.0, rng[1] / 1e6), det, [], [F_CNH + ' (contrafactual_solar)'],
                          neto_sin_valor_residual=r1(neto_sr), valor_residual=r1(resid)))
    else:
        fugas.append(fuga('ahorro_solar', 0, 0, 0, 'No calculado: en 2004–2007 la solar costaba aún más que en 2008, cuando instalarla no se habría pagado.', [], [F_CNH], sin_dato=True))

    # --- J. fondo local de ahorro con regalías --------------------------------
    fil = [AHORRO[a] for a in anios if a in AHORRO]
    if fil:
        ap_ = sum(f['aporte_mm_2026'] for f in fil)
        v3 = sum(f['valor_2026_r3_mm'] for f in fil)
        v4 = sum(f['valor_2026_r4_mm'] for f in fil)
        det = (f"Contrafactual: el 10 % de las regalías directas de estos años era {mm(ap_)} de 2026; guardado al 3–4 % real valdría hoy {mm(v3)} a {mm(v4)}, "
               f"y solo sus rendimientos darían {mm(v3 * 0.03)} a {mm(v4 * 0.04)} al año sin tocar el capital. Es adicional al ahorro obligatorio del FAEP "
               f"(Ley 209 de 1995), cuya subcuenta para Yondó no se revisó: si parte de estas regalías quedó retenida allí, el contrafactual está sobrestimado.")
        aitems = [item(f"Aporte de {f['anio']} (10 % de {mmc(f['regalias_giradas_mm_corrientes'] * 1e6, f['anio'])})"
                       + (' — quién gobernó en 2004 está por verificar' if f['anio'] == 2004 else ''), f['anio'], f['valor_2026_r3_mm'],
                       F_CNH + ' (contrafactual_ahorro_regalias)') for f in fil]
        fugas.append(fuga('ahorro_regalias', v3, ap_, v4, det, aitems, [F_CNH + ' (contrafactual_ahorro_regalias)', 'data/fuentes/serie_fiscal_oec.csv', 'Ley 209 de 1995 (FAEP)']))
    else:
        fugas.append(fuga('ahorro_regalias', 0, 0, 0, 'No aplica: desde 2012 el Sistema General de Regalías ahorra a nivel nacional (Fondo de Ahorro y Estabilización) y el municipio no recibe regalías directas.',
                          [], [F_CNH], no_aplica=True))

    tot = {t: sum(f['valor'] or 0 for f in fugas if f['tipo'] == t) for t in TIPOS}
    so_fugas = [f for f in fugas if f['tipo'] in TIPOS_SIN_OBRA]
    so = tot['hecho'] + tot['estimado']
    comparable = pid in ('2012-2015', '2016-2019', '2020-2023')
    uo_f = next(f for f in fugas if f['categoria'] == 'sobrecosto_sin_competencia')['valor_un_oferente']
    return {
        'ingresos': r1(ing), 'inversion': r1(ap['inversion']['suma_mm_2026']), 'regalias': r1(ap['regalias']['suma_mm_2026']),
        'sgp': r1(ap['sgp']['suma_mm_2026']), 'propios': r1(propios),
        'anios_con_dato_plata': anios_plata,
        'fugas': fugas,
        'total_hecho': r1(tot['hecho']), 'total_estimado': r1(tot['estimado']), 'total_plata_quieta': r1(tot['plata quieta']),
        'total_indicio': r1(tot['indicio']), 'total_contrafactual': r1(tot['contrafactual']),
        'sin_obra': r1(so),
        'sin_obra_rango': [r1(sum((f['min'] if f['min'] is not None else f['valor']) for f in so_fugas)),
                           r1(sum((f['max'] if f['max'] is not None else f['valor']) for f in so_fugas))],
        'sin_obra_comparable': r1(so - uo_f) if comparable else None,
        'categorias_sin_obra_con_dato': f"{sum(1 for f in so_fugas if not f.get('sin_dato'))} de {len(so_fugas)}",
        'pendiente_por_aprobar': pendiente,
        'flist': flist, 'gsa_items': gitems, 'gsa': g,
    }


# ---------------------------------------------------------------------------
# equivalencias, pudo_hacerse y lectura
# ---------------------------------------------------------------------------
PREFERENCIA = {
    '2004-2007': ['aula_dotada', 'beca_universitaria_anual', 'km_placa_huella', 'ptar_12000_hab', 'vis_rural', 'kwp_solar_cubierta'],
    '2008-2011': ['km_placa_huella', 'ptar_12000_hab', 'aula_dotada', 'beca_universitaria_anual', 'vis_rural', 'kwp_solar_cubierta'],
    '2012-2015': ['aula_dotada', 'beca_universitaria_anual', 'ptar_12000_hab', 'km_placa_huella', 'vis_rural', 'kwp_solar_cubierta'],
    '2016-2019': ['aula_dotada', 'vis_rural', 'km_placa_huella', 'ptar_12000_hab', 'beca_universitaria_anual', 'kwp_solar_cubierta'],
    '2020-2023': ['vis_rural', 'ptar_12000_hab', 'km_placa_huella', 'aula_dotada', 'beca_universitaria_anual', 'kwp_solar_cubierta'],
    '2024-2027': ['ptar_12000_hab', 'kwp_solar_cubierta', 'aula_dotada', 'beca_universitaria_anual', 'km_placa_huella', 'vis_rural'],
}


def equivalencias(pid, valor, rango):
    out = []
    for id_ in PREFERENCIA[pid]:
        n = valor / cu(id_)
        if 1 <= n <= 999:
            out.append({'unidad': UNIDADES[id_], 'n': r1(n), 'costo_unitario': r1(cu(id_)), 'id': id_,
                        'rango_n': [r1(rango[0] / cu_max(id_)), r1(rango[1] / cu_min(id_))], 'certeza_costo': CU[id_]['certeza'],
                        'base': 'sin obra, valor central (hecho + estimado)'})
        if len(out) == 4:
            break
    return out


def item_pudo(que, costo, unidad, por_que_no, fuente, sin_obra, rango=None, extra_eq=None, cubierto=True, con_rango=False):
    eq = eq_texto(costo, unidad, con_rango) if unidad else ''
    if extra_eq:
        eq = f'{eq}; {extra_eq}' if eq else extra_eq
    pc = 100 * sin_obra / costo if costo and cubierto else None
    d = {'que': que, 'costo': r1(costo), 'equivalencia': eq, 'por_que_no': por_que_no, 'fuente': fuente,
         'cubierto_con_plata_sin_obra_pct': r1(pc) if pc is not None and pc <= 999 else None}
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
    ptar_eq = f"1 PTAR (costo entre {mm(rngp[0])} y {mm(rngp[1])}; sin colectores)"
    sol = SOLAR.get(pid)
    out = []
    if pid == '2004-2007':
        ah = F['ahorro_regalias']
        alcanza = 'alcanzaba' if ah['min'] >= rngp[0] else 'no alcanzaba'
        out.append(item_pudo('PTAR para el casco urbano (unos 12.000 habitantes)', ptar, None,
                             f"El plan 2005–2007 se apoyó en un Plan Maestro de Acueducto y Alcantarillado, pero la planta no se construyó; en 2019 Yondó vertía 55 L/s sin "
                             f"tratar. El 10 % de las regalías de estos cuatro años ({mm(ah['min'])} de 2026) {alcanza} para una PTAR al costo más bajo de referencia "
                             f"({mm(rngp[0])}), sin colectores.", PTAR_FUENTE + f'; {F_GOB}', so, rngp, extra_eq=ptar_eq))
        out.append(item_pudo('Fondo local de ahorro con el 10 % de las regalías directas (contrafactual)', ah['min'], None,
                             f"No se creó un fondo local, aunque las regalías eran el {pct(c['regalias'], c['ingresos'])} % de los ingresos. Es adicional al ahorro "
                             f"obligatorio del FAEP (Ley 209 de 1995), cuyo saldo para Yondó no se revisó.",
                             F_CNH + ' (contrafactual_ahorro_regalias)', so, extra_eq=f"hoy valdría {mm(ah['valor'])} (3 % real), {eq_texto(ah['valor'], 'aula_dotada')}", cubierto=False))
        out.append(item_pudo('10 aulas dotadas para ampliar la educación media', 10 * cu('aula_dotada'), 'aula_dotada',
                             (f"La cobertura neta en media era de {fmt(COB_MEDIA_0507)} % (promedio 2005–2007, MEN en TerriData): {fmt(100 - COB_MEDIA_0507)} de cada 100 "
                              f"jóvenes de 15–16 años no estaban matriculados en media."),
                             f"{F_CNH} (aula_dotada); {F_PANEL} (cob_neta_media, MEN en TerriData)", so, [10 * cu_min('aula_dotada'), 10 * cu_max('aula_dotada')]))
    elif pid == '2008-2011':
        ah = F['ahorro_regalias']
        km_a, km_b = c['sin_obra_rango'][0] / cu_max('km_placa_huella'), c['sin_obra_rango'][1] / cu_min('km_placa_huella')
        out.append(item_pudo('Mejorar la vía Yondó–Puerto Berrío (meta de 71 km del plan 2008–2011)', 71 * cu('km_placa_huella'), 'km_placa_huella',
                             f"La vía siguió sin pavimentar (sin avance según la Gobernación en mayo de 2025). El costo se estimó como placa huella, un supuesto de este "
                             f"cálculo y no del plan. La plata sin obra de este gobierno ({mm(so)}) alcanzaba para unos {fmt(so / cu('km_placa_huella'))} km "
                             f"(entre {fmt(km_a)} y {fmt(km_b)} km, según el costo y el rango).",
                             f"{F_CNH} (km_placa_huella); {F_GOB}", so, [71 * cu_min('km_placa_huella'), 71 * cu_max('km_placa_huella')]))
        out.append(item_pudo('Fondo local de ahorro con el 10 % de las regalías, en su máximo histórico (contrafactual)', ah['min'], None,
                             'No se creó un fondo local de ahorro. Es adicional al ahorro obligatorio del FAEP, cuyo saldo para Yondó no se revisó.',
                             F_CNH + ' (contrafactual_ahorro_regalias); ' + F_GOB, so, extra_eq=f"hoy valdría {mm(ah['valor'])}, {eq_texto(ah['valor'], 'ptar_12000_hab')}", cubierto=False))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             'Siguió pendiente y las aguas residuales se siguieron vertiendo sin tratar.', PTAR_FUENTE, so, rngp, extra_eq=ptar_eq))
    elif pid == '2012-2015':
        ciud = a26(7090e6, 2016)
        out.append(item_pudo(f"Ciudadela Educativa (diseñada en {CIUDADELA['anio']} por {mmc(CIUDADELA['valor'], CIUDADELA['anio'])})", ciud, 'aula_dotada',
                             'Se diseñó en 2014 y hubo contrato de obra, que quedó suspendido (el plan 2020–2023 habla de su "reinicio"). Costo: lo previsto en el plan 2016–2019 ($7.090 M, pesos corrientes de 2016).',
                             f"{F_GOB}; {F_ANEXO_A} (§8.6); SECOP https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=14-15-2238279", so))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             (f"Siguió pendiente. Los estudios de 18 acueductos rurales de {ACUED['anio']} ({mmc(ACUED['valor'], ACUED['anio'])}) sí tuvieron después obras "
                              f"de acueductos veredales (BPIN 2013058930013 y 2015058930003)."),
                             PTAR_FUENTE + f'; {F_ANEXO_A} (§8.7)', so, rngp, extra_eq=ptar_eq))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2012', ci['inversion_cop_2026'] / 1e6, None,
                                 f"No se hizo. Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría un beneficio neto de {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)}.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
        out.append(item_pudo('400 becas universitarias de un año (100 por año) para bachilleres', 400 * cu('beca_universitaria_anual'), 'beca_universitaria_anual',
                             f"La cobertura neta en media fue de {fmt(COB_MEDIA_1215, 1)} % en promedio de 2012–2015 ({fmt(COB_MEDIA['2015'], 1)} % en 2015; MEN en TerriData).",
                             f"{F_CNH} (beca_universitaria_anual, supuesto); {F_PANEL} (cob_neta_media)", so))
    elif pid == '2016-2019':
        ciud = a26(7090e6, 2016)
        out.append(item_pudo('Terminar la Ciudadela Educativa', ciud, 'aula_dotada', 'Tenía $7.090 M (pesos corrientes de 2016) en el plan 2016–2019 y siguió sin terminar.', F_GOB, so))
        lapaz = a26(13336e6, 2019)
        out.append(item_pudo('Vivienda para reubicar el barrio La Paz', lapaz, 'vis_urbana', 'Empezó en 2019 y seguía en ejecución en 2026.', F_GOB, so))
        oxi = FONDOS['OXI']['monto_referencia_min'] / 1e6 / statistics.mean(IPC[a] for a in range(2018, 2026))
        out.append(item_pudo('Una vía terciaria por Obras por Impuestos (si una empresa contribuyente escogía el proyecto)', oxi, 'km_placa_huella',
                             (f"Obras por Impuestos empezó en 2018. Entre los proyectos aprobados (ART 2018–2025) Yondó solo tuvo uno, de dotación escolar en "
                              f"{OXI_2019['anio']} ({mmc(OXI_2019['valor'], OXI_2019['anio'])})."),
                             '; '.join(FONDOS['OXI']['evidencia'][:1]) + f'; {F_SGR}', so, con_rango=True))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2016', ci['inversion_cop_2026'] / 1e6, None,
                                 f"La Ley 1715 de 2014 ya daba incentivos. Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría un beneficio neto de {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)}.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
    elif pid == '2020-2023':
        vv = [i for i in c['gsa_items'] if i['bpin'] in ('2022003050005', '2022003050034')]
        viv = sum(i['valor'] for i in vv)
        vv_s = sorted(vv, key=lambda i: i['avance_fisico_pct'])
        out.append(item_pudo('Terminar las viviendas contratadas con la EDU (dos proyectos de regalías)', viv, 'vis_rural',
                             (f"A octubre de 2026 (GESPROY) van en {' y '.join(fmt(i['avance_fisico_pct']) + ' %' for i in vv_s)} de obra con "
                              f"{' y '.join(fmt(i['avance_financiero_pct']) + ' %' for i in vv_s)} de los recursos girados. En agosto de 2024 el DNP alertó "
                              f"\"alto riesgo de pérdida de recursos\". La ejecución estaba delegada en la EDU, que informó dificultades con sus contratistas y un "
                              f"proceso sancionatorio (anexo A, §8.3). Costo: lo pagado por delante del avance."),
                             f'{F_SGR} (BPIN 2022003050034 y 2022003050005); {URL_DNP_ALERTA}; {F_ANEXO_A} (§5.4 y §8.3)', so))
        ye = [i for i in c['gsa_items'] if i['bpin'] == '20201301010644']
        if ye:
            y0 = ye[0]
            out.append(item_pudo('Terminar el corredor Ye de Marley–San Francisco (OCAD Paz)', y0['valor'], 'km_placa_huella',
                                 (f"A octubre de 2026 (GESPROY), {fmt(y0['avance_fisico_pct'])} % de obra con {fmt(y0['avance_financiero_pct'])} % pagado; de lo pagado, "
                                  f"{mmc(y0['pagado_2025_2026_corriente'], '2025–2026')} se pagó en 2025–2026, en el gobierno siguiente. Costo: lo pagado por delante del avance."),
                                 f'{F_SGR} (BPIN 20201301010644); {F_ANEXO_A} (§8.1)', so, con_rango=True))
        out.append(item_pudo('PTAR para el casco urbano', ptar, None,
                             'Se adoptó el EOT 2022–2035, pero no hay PTAR; la canalización de colectores de las estaciones de bombeo sigue en formulación ($67.640 M, valor del proyecto en pesos corrientes; BPIN 20201301010649).',
                             PTAR_FUENTE, so, rngp, extra_eq=ptar_eq))
        if sol:
            ci = sol['solo_solar']['central']
            out.append(item_pudo('Solar en las 13 sedes públicas (469 kWp) instalada en 2020', ci['inversion_cop_2026'] / 1e6, None,
                                 f"Se habría pagado sola en {ci['anio_recuperacion']} y a 2026 dejaría un beneficio neto de {mm(ci['neto_hasta_2026_con_valor_residual'] / 1e6)}; FENOGE y la convocatoria de incentivos la podían financiar.",
                                 F_CNH + ' (contrafactual_solar)', so, extra_eq='469 kWp solares en cubiertas'))
        md = FONDOS['MINTIC']
        sedes = [x['sedes'] for x in md['comparables'] if x.get('sedes')]
        out.append(item_pudo('Centros Digitales en 10 sedes rurales más (MinTIC)', md['monto_referencia_central'] / 1e6 / IPC[2023], None,
                             f"Yondó tiene {md['yondo_obtuvo']['sedes']} sedes conectadas, todas en San Miguel del Tigre; sus comparables, entre {min(sedes)} y {max(sedes)}. "
                             f"El costo usa la inversión por sede que registra MinTIC (estándar del programa).",
                             '; '.join(md['evidencia'][:1]) + f'; {F_SGR}', so, extra_eq='≈ 10 sedes educativas rurales con internet'))
    elif pid == '2024-2027':
        pend = c['pendiente_por_aprobar']
        inc = FONDOS['INCENTIVO']
        pares = sorted(x['pct_aprobado'] for x in inc['comparables'] if x.get('pct_aprobado') is not None)
        ail = FONDOS['AIL']
        ail_p = sorted(x['pct_aprobado'] for x in ail['comparables'] if x.get('pct_aprobado') is not None)
        ail_y = 100 * ail['yondo_obtuvo']['aprobado_2025_2026'] / ail['yondo_obtuvo']['presupuesto_2025_2026']
        out.append(item_pudo('Aprobar antes de diciembre de 2026 las regalías que ya están asignadas a Yondó', pend['total'], 'ptar_12000_hab',
                             (f"Aún se puede. Con corte del {fecha_corta(CORTE)} seguían sin aprobar {mm(pend['aprueba_municipio'])} que aprueba el municipio (asignaciones "
                              f"directas e inversión local) y {mm(pend['aprueba_ocad_paz'])} del incentivo a la producción, que el municipio formula y el OCAD Paz aprueba. "
                              f"En esa bolsa la mediana de los pares aprobó {fmt(statistics.median(pares), 1)} % (rango {fmt(pares[0], 1)}–{fmt(pares[-1], 1)} %); en "
                              f"inversión local Yondó aprobó {fmt(ail_y, 1)} %, por encima de la mediana de sus pares ({fmt(statistics.median(ail_p), 1)} %)."
                              + frase_salvedad_ad(pend['asignaciones_directas'])),
                             f'{URL_MINHAC} (corte oct-2026); {F_SGR}', so, cubierto=False))
        # la Red Energética y el hospital, con los cambios del 22-oct-2026 (docs/05, docs/07 y docs/11)
        out.append(item_pudo('Red Energética Pública: solar en 13 sedes, baterías en 7 sedes críticas y control (proyecto 1; $5.829 M sin el nodo del hospital, '
                             'que pasó a la torre)', 7204, None,
                             f'Aún se puede: cabe en la línea "Territorios energéticos" del incentivo a la producción (hasta $8.000 M). El único proyecto de energía presentado en 2025 no cumplió requisitos; cada año de espera cuesta unos {mm(ESPERA_SOLAR)} en facturas.',
                             'docs/07-portafolio-presupuesto.md; docs/05-microrred-domotica-mintic.md; ' + F_CNH, so,
                             extra_eq='469 kWp solares en cubiertas y 770 kWh de baterías; compra 57 % menos energía'))
        out.append(item_pudo('Terminar los estudios del Plan Maestro y construir la PTAR del casco urbano', 1800 + ptar, 'ptar_12000_hab',
                             'Aún se puede empezar: los estudios del Plan Maestro ($2.898 M, pesos corrientes; 56 % de avance) están "inactivos"; terminarlos cuesta unos $1.800 M y son requisito de la PTAR.',
                             'docs/07-portafolio-presupuesto.md; ' + PTAR_FUENTE, so, [1800 + rngp[0], 1800 + rngp[1]]))
        out.append(item_pudo('Hospital seguro, verde e inteligente (red eléctrica, telesalud, ambulancia medicalizada, puesto rural)', 8100, None,
                             'Aún se puede: la red eléctrica del hospital ($5.483 M, pesos corrientes) está en formulación desde 2017; la ventana de financiación es 2027–2029. '
                             'Actualización del 22-oct-2026: este proyecto lo reemplaza la torre de servicios de primer nivel ($37.137 M, docs/11).',
                             'docs/06-hospital-2028-financiacion.md; docs/07-portafolio-presupuesto.md', so,
                             extra_eq='red eléctrica nueva, telesalud, una ambulancia medicalizada y un puesto de salud rural'))
        gsa_prev = RESULTADOS['2020-2023']['gsa']['central']
        out.append(item_pudo('Auditoría técnica y plan de terminación de las obras con brecha', 600, None,
                             f"Aún se puede: busca recuperar o terminar {mm(gsa_prev)} de recursos de regalías pagados por delante del avance en proyectos aprobados en 2020–2023.",
                             'docs/07-portafolio-presupuesto.md; ' + F_SGR, so, extra_eq=f"protege {mm(gsa_prev)} ya pagados"))
    return out


def lectura(pid, c):
    F = {f['categoria']: f for f in c['fugas']}
    so, ing = c['sin_obra'], c['ingresos']
    rg = c['sin_obra_rango']
    if pid == '2004-2007':
        return (f"Entraron {mm(ing)} de 2026, el {pct(c['regalias'], ing)} % por regalías, y SECOP casi no tiene contratos de estos años: no se puede saber si hubo "
                f"plata sin obra, así que los {mm(so)} estimados son un piso y no una medida. La oportunidad perdida más clara es un contrafactual: un fondo local con el "
                f"10 % de esas regalías valdría hoy {mm(F['ahorro_regalias']['valor'])}, aparte del ahorro obligatorio del FAEP, que no se revisó.")
    if pid == '2008-2011':
        cob = [COBERTURA[a]['Alcaldía'] for a in range(2008, 2012)]
        return (f"Fue el gobierno con más regalías del régimen anterior: entraron {mm(ing)} de 2026. En los pocos contratos que registró SECOP ({min(cob)} a {max(cob)} "
                f"por año) hay {mm(so)} sin obra o en costo posible de contratar sin competencia, una cifra que es un piso. Contrafactual: un fondo local con el 10 % de "
                f"esas regalías valdría hoy {mm(F['ahorro_regalias']['valor'])}, y la vía a Puerto Berrío siguió sin pavimentar.")
    if pid == '2012-2015':
        return (f"Entraron {mm(ing)} de 2026 y, según los registros y las estimaciones, {mm(so)} no se convirtieron en obra (rango {mm(rg[0])}–{mm(rg[1])}): "
                f"{mm(F['sobrecosto_sin_competencia']['valor'])} de costo posible de contratar sin competencia y {mm(F['estudios_sin_obra']['valor'])} en estudios sin obra "
                f"posterior hallada. Aparte, el gasto en OPS estuvo {mm(F['ops_nomina_paralela']['valor'])} por encima de lo usual en Yondó: es un indicio para comparar "
                f"con la planta de personal, no plata sin obra.")
    if pid == '2016-2019':
        pc = 100 - RES_ALC[pid]['pct_sin_competencia']
        mas = all(RES_ALC[pid]['pct_sin_competencia'] <= RES_ALC[p]['pct_sin_competencia'] for p in RES_ALC)
        return (f"Entraron {mm(ing)} de 2026 y {'fue el gobierno que más contrató con competencia' if mas else 'contrató con competencia'} ({fmt(pc)} % del valor). "
                f"Quedan {mm(so)} sin obra o en costo posible de no competir, y en septiembre de 2018, poco antes de cerrar su último bienio, había "
                f"{mm(F['saldos_regalias']['valor'])} de regalías sin comprometer, que no se pierden. La Ciudadela Educativa y la vivienda de La Paz siguieron sin terminar.")
    if pid == '2020-2023':
        gi = [i for i in c['gsa_items'] if i['en_total']]
        edu = 100 * sum(i['valor'] for i in gi if i['edu']) / F['girado_sin_avance']['valor'] if F['girado_sin_avance']['valor'] else 0
        mas_inv = all(c['inversion'] >= RESULTADOS[p]['inversion'] for p in RESULTADOS)
        gs = F['girado_sin_avance']
        return (f"Entraron {mm(ing)} de 2026{' y se invirtió más que en cualquier otro gobierno' if mas_inv else ''}, pero {mm(gs['valor'])} de "
                f"recursos de proyectos de regalías se pagaron por delante del avance reportado a octubre de 2026: el {fmt(edu)} % en proyectos delegados en la EDU "
                f"de Medellín (vivienda, vías y un parque) y el {pct(gs['valor_en_ejecucion'], gs['valor'])} % en obras que siguen en ejecución, donde la brecha "
                f"todavía puede cerrarse. Con el {fmt(F['sobrecosto_sin_competencia']['pct_valor_sin_competencia'])} % contratado sin competencia, el costo posible de no competir "
                f"suma {mm(F['sobrecosto_sin_competencia']['valor'])}; en total, {mm(so)} sin obra (rango {mm(rg[0])}–{mm(rg[1])}). Además, al cierre de 2022 "
                f"quedaban {mm(F['saldos_regalias']['valor'])} de regalías sin comprometer, que pasaron al bienio siguiente.")
    if pid == '2024-2027':
        p = c['pendiente_por_aprobar']
        sv = salvedad_ad(p['asignaciones_directas'])
        return (f"Periodo en curso (datos parciales a octubre de 2026). Lo más grande no es plata perdida sino plata por aprobar: con corte del {fecha_corta(CORTE)} "
                f"quedaban {mm(p['total'])} de regalías del bienio 2025–2026, {mm(p['aprueba_municipio'])} que aprueba el municipio y {mm(p['aprueba_ocad_paz'])} del "
                f"incentivo a la producción que aprueba el OCAD Paz, y el bienio cierra en diciembre de 2026" + (f"; {sv}" if sv else '') + ". "
                f"Con esa plata y con fondos aún disponibles (OCAD Paz, FENOGE) se pueden financiar la red solar pública, el hospital y los estudios de la PTAR: "
                f"el incentivo va a proyectos de energía, como la red solar, y el hospital se paga con asignaciones directas, inversión local y la Asignación para "
                f"la Paz del OCAD Paz (docs/11).")
    return ''


# ---------------------------------------------------------------------------
# armado
# ---------------------------------------------------------------------------
def alcalde_corto(g):
    if g['id'] == '2004-2007':
        return 'Wilfrido Uzuriaga Aponzá (2005–2007; 2004 por verificar)'
    return g['alcalde'].split(' (')[0].split(';')[0]


RESULTADOS = {}
periodos = []
for g in GOB['periodos']:
    RESULTADOS[g['id']] = calcular_periodo(g['id'])
for g in GOB['periodos']:
    pid = g['id']
    c = RESULTADOS[pid]
    c['equivalencias'] = equivalencias(pid, c['sin_obra'], c['sin_obra_rango'])
    comparable = c['sin_obra_comparable'] is not None
    per = {
        'id': pid, 'alcalde': g['alcalde'], 'alcalde_corto': alcalde_corto(g),
        'en_curso': pid == '2024-2027',
        'ingresos': c['ingresos'], 'inversion': c['inversion'], 'regalias': c['regalias'], 'sgp': c['sgp'], 'propios': c['propios'],
        'anios_con_dato_plata': c['anios_con_dato_plata'],
        'fugas': c['fugas'],
        'total_hecho': c['total_hecho'], 'total_estimado': c['total_estimado'], 'total_plata_quieta': c['total_plata_quieta'],
        'total_indicio': c['total_indicio'], 'total_contrafactual': c['total_contrafactual'],
        'sin_obra': c['sin_obra'], 'sin_obra_rango': c['sin_obra_rango'],
        'categorias_sin_obra_con_dato': c['categorias_sin_obra_con_dato'],
        'sin_obra_pct_ingresos': r1(100 * c['sin_obra'] / c['ingresos']) if comparable else None,
        'sin_obra_comparable': c['sin_obra_comparable'],
        'sin_obra_comparable_pct_ingresos': r1(100 * c['sin_obra_comparable'] / c['ingresos']) if comparable else None,
        'pudo_hacerse': pudo_hacerse(pid, c),
        'equivalencias': c['equivalencias'],
        'fondos_no_gestionados': c['flist'],
        'lectura': lectura(pid, c),
    }
    if c['pendiente_por_aprobar']:
        per['pendiente_por_aprobar'] = c['pendiente_por_aprobar']
    if pid == '2024-2027':
        per['nota'] = ('Periodo en curso. Ingresos, inversión, regalías, SGP e impuestos propios solo tienen 2024 completo (operaciones de caja del DNP); '
                       'la contratación va de enero de 2024 al 20 de octubre de 2026 y las regalías por aprobar tienen corte del '
                       f'{fecha_larga(CORTE)}.')
    if pid == '2004-2007':
        ing04 = IND['ingresos_totales']['serie'].get('2004') if 'ingresos_totales' in IND else None
        per['nota'] = (f'SECOP casi no tiene registros de estos años ({N_ALC_2007} contratos de la alcaldía en 2007): un cero aquí es "sin dato", no "cero pérdidas". '
                       'Wilfrido Uzuriaga Aponzá gobernó en 2005–2007; quién gobernó en 2004 está por verificar, y los totales del periodo incluyen 2004'
                       + (f' (ingresos de {mm(ing04)} de 2026 y {mm(AHORRO[2004]["valor_2026_r3_mm"])} del fondo de ahorro contrafactual).' if ing04 else '.'))
    if pid == '2008-2011':
        cob = [COBERTURA[a]['Alcaldía'] for a in range(2008, 2012)]
        per['nota'] = (f'SECOP está subregistrado ({min(cob)} a {max(cob)} contratos de la alcaldía por año, frente a más de 400 desde 2012): las cifras de '
                       'contratación son un piso. No hay registro abierto del avance de las obras de regalías de estos años.')
    periodos.append(per)


def totales_por_categoria():
    filas = []
    for cat in CATEGORIAS:
        fila = {'categoria': cat['id'], 'nombre': cat['nombre'], 'tipo': cat['tipo'], 'por_periodo': {}, 'marcas': {}}
        for p in periodos:
            f = next(x for x in p['fugas'] if x['categoria'] == cat['id'])
            if f.get('no_aplica'):
                fila['por_periodo'][p['id']] = None
                fila['marcas'][p['id']] = 'no_aplica'
            elif f.get('sin_dato') and not f['valor']:
                fila['por_periodo'][p['id']] = None
                fila['marcas'][p['id']] = 'sin_dato'
            else:
                fila['por_periodo'][p['id']] = f['valor']
        sumable = cat['id'] not in ('saldos_regalias', 'ahorro_solar')
        fila['sumable_entre_gobiernos'] = sumable
        fila['total_2004_2026'] = r1(sum(v or 0 for v in fila['por_periodo'].values())) if sumable else None
        if not sumable:
            fila['nota'] = ('Son fotos de saldos en fechas distintas y la plata pasa de un bienio al siguiente: no se suman entre gobiernos.' if cat['id'] == 'saldos_regalias'
                            else 'Cada gobierno es un escenario alternativo (instalar en 2012, o en 2016, o en 2020…): no se suman.')
        filas.append(fila)
    return filas


TOTALES = totales_por_categoria()
DUPS = AJ['posibles_duplicados']
DUPS_ALC = [x for x in DUPS if x['entidad'] == 'Alcaldía']


def resumen_dups():
    exceso = sum(x['valor'] * (x['registros'] - 1) for x in DUPS)
    partes = []
    for x in sorted(DUPS_ALC, key=lambda z: z['fecha']):
        partes.append(f"{x['anio']} {mmc(x['valor'], x['anio']).split(' (')[0]} ({x['categoria'].split(' /')[0].lower()}"
                      + (', transferencia a una entidad de Yondó' if x['transferencia_interna'] else '') + ')')
    otras = [x for x in DUPS if x['entidad'] != 'Alcaldía']
    ej = max(DUPS_ALC, key=lambda z: z['valor'])
    return (f"Hay {sum(x['registros'] for x in DUPS)} registros de SECOP de $100 M o más que parecen duplicados (misma entidad, fecha, valor y contratista, con objeto "
            f"parecido): {sum(x['registros'] - 1 for x in DUPS)} copias de más por ${fmt(exceso / 1e6)} M corrientes. {len(DUPS_ALC)} grupos son de la alcaldía: "
            + '; '.join(partes) + (f"; {len(otras)} de otras entidades." if otras else '.') +
            ' Cómo se tratan: en OPS se quita la segunda copia (mismo contratista, día, valor y objeto); las transferencias ya no entran en la línea 1 del costo de '
            'contratar sin competencia; en lo demás la copia se quita solo en el mínimo, porque no se verificó en el expediente que sea el mismo contrato '
            f"(por ejemplo, los {plural(ej['registros'], 'registro', 'registros')} de {mmc(ej['valor'], ej['anio'])} con {contratista_publicable(ej['contratista']) or 'el mismo contratista'} "
            f"tienen constancias distintas, {' y '.join(ej['numeros'])}). La lista está en fugas_secop.json, ajustes_dinero_no_hecho.posibles_duplicados.")


METODO = (
    'Para cada gobierno se cuenta la plata que no se convirtió en obra a tiempo, en cinco niveles que no se mezclan. Hecho: pagos de proyectos de regalías por delante '
    'del avance reportado en GESPROY (un cálculo directo sobre registros oficiales, con rango). Estimado: cálculos con método y rango sobre registros oficiales '
    '(estudios sin obra posterior hallada en el SECOP de la alcaldía, costo posible de contratar sin competencia, recaudo y tasa retributiva evitable). '
    '"Sin obra" = hecho + estimado. Aparte, y sin sumarse a "sin obra": la plata quieta (regalías sin comprometer al cierre de un bienio, que no se pierden), los '
    'indicios (gasto en OPS por encima de lo usual en Yondó, que es una alerta y no plata sin obra) y los contrafactuales (fondos externos no obtenidos, beneficio '
    'solar y fondo de ahorro con regalías), que no son plata perdida. Todo va en millones de pesos de 2026: un flujo se deflacta con el IPC del DANE de su año y un '
    'saldo con el IPC del mes del corte. Para no contar dos veces la misma plata: (1) los contratos mixtos de diseño y obra no entran en estudios sin obra; (2) la '
    'base del costo de contratar sin competencia es lo que la alcaldía compró a terceros: se le quitan las OPS, los estudios sin obra, las transferencias a Aguas y '
    'Aseo, al hospital y a otras entidades de Yondó (incluidos los subsidios a las tarifas y los pagos al hospital por población pobre no afiliada o por gastos de '
    'operación), los empréstitos y la plata ya contada en pagos por delante del avance; lo transferido entra en una línea aparte solo hasta lo que esas entidades '
    'contrataron sin competencia ese año, en años con datos; (3) de los saldos se toma un solo corte por gobierno, con la misma regla y medida; (4) Findeter no se '
    'suma por ser crédito; (5) los proyectos de regalías hechos con la EDU se cuentan una vez, como pagos por delante del avance. Las equivalencias dividen el valor '
    'central de "sin obra" por el costo unitario de 2026, con su rango. Las cifras describen a la administración municipal de cada periodo, no a la persona del '
    'alcalde, y no implican responsabilidad penal, fiscal ni disciplinaria.'
)


def limitaciones():
    return [
        (f'SECOP casi no tiene contratos de Yondó antes de 2012 ({N_ALC_2007} de la alcaldía en 2007 y entre {min(N_ALC_0811)} y {max(N_ALC_0811)} por año en '
         f'2008–2011, frente a {fmt(COBERTURA[2012]["Alcaldía"])} en 2012): para 2004–2011 los ceros son "sin dato", las cifras de contratación son un piso y el '
         'porcentaje sobre ingresos no es comparable.'),
        'La coincidencia estudio → obra se hace por palabras del objeto y solo con las obras del SECOP de la alcaldía: hay falsos negativos (obras hechas por Aguas y Aseo, la Gobernación, Ecopetrol, Findeter o la EDU con otras palabras) y falsos positivos. Se corrigieron a mano cinco casos con evidencia (fugas_secop.json, estudios_obra_hallada_fuera) y se da un rango con umbrales de 0,20 y 0,40. Es una agenda de verificación.',
        'El costo de contratar sin competencia es una estimación con rango tomado de estudios de otros países y de Colombia; no hay una medición directa de precios para Yondó. Contratar directamente es legal en muchos casos (convenios interadministrativos, OPS, régimen especial). Los estudios sobre sobornos y corrupción se citan solo como contexto y no entran en el rango.',
        resumen_dups(),
        ('La referencia de OPS es interna (el propio Yondó en un año típico 2012–2025): mide cuánto se alejó cada gobierno de lo usual, no un estándar nacional, '
         'que no existe en datos abiertos. Hasta 2023 la alcaldía publicó casi todo en SECOP I y desde 2024 en SECOP II: el cambio de sistema puede afectar la '
         f'comparación. La cifra publicada de {fmt(OPS_PUBLICADAS)} OPS (2008–2026) se mantiene por continuidad; para este cálculo se quitaron '
         f'{fmt(OPS_RECLAS_N)} contratos que la clasificación ponía en OPS sin serlo (transferencias, subsidios, convenios para aunar esfuerzos e instituciones '
         f'públicas) y {fmt(OPS_DUP_N)} segundas copias de registros duplicados, y quedan {fmt(OPS_PUBLICADAS - OPS_RECLAS_N - OPS_DUP_N)} '
         '(fugas_secop.json, ajustes_dinero_no_hecho.ops_reclasificadas_alcaldia).'),
        'Los pagos por delante del avance solo existen para proyectos de regalías (GESPROY). Para la plata propia y para los convenios con la EDU no hay datos abiertos de avance físico ni de pagos (SECOP I no publica pagos; los anticipos solo constan en el expediente). La brecha se mide a octubre de 2026, incluye pagos hechos después de cada gobierno y se atribuye al gobierno que aprobó el proyecto.',
        'GESPROY y MapaInversiones no coinciden en varios proyectos (estado o pagos): se usa GESPROY y el mínimo excluye los contradictorios. El año de aprobación es estimado: los proyectos fechados en 2015, 2019 y 2023 pudieron aprobarse a comienzos del año siguiente (bienios compartidos) y el mínimo los excluye. El valor de cada proyecto es el total de GESPROY y puede incluir cofinanciación.',
        'Los saldos de regalías no son plata perdida: en el SGR pasan al bienio siguiente. Para 2016–2019 no hay dato abierto al cierre de 2018 y se usa el corte de septiembre de 2018, con todo el capítulo SGR; para 2020–2023 y 2024–2027 se usan las asignaciones directas más los incentivos y la inversión local. La medida es la misma (presupuesto menos compromisos), salvo los incentivos, que se miden como plata que pasó sin usar al bienio siguiente.',
        'El recaudo dejado de cobrar se compara por periodo: un año por debajo de los comparables (el ICA de 2004 y 2005) se compensa con años por encima.',
        'La tasa retributiva es un costo de Aguas y Aseo; se estima con factor regional 1 y con el caudal medido en 2019 también para los años anteriores, y una parte no se pagó (deuda de $175 M en 2020, pesos corrientes).',
        'Los fondos externos son contrafactuales con certeza variable (Fondo Adaptación y cooperación, baja); dependen de convocatorias, de terceros (empresas en Obras por Impuestos) y de proyectos bien formulados. No se halló que Yondó los obtuviera ni que los solicitara, pero un registro ausente no prueba que no se pidieron.',
        'El fondo de ahorro con regalías no descuenta el ahorro obligatorio que Yondó, como municipio productor, pudo tener en el FAEP (Ley 209 de 1995): falta consultar el saldo y los retiros de esa subcuenta en MinHacienda o el Banco de la República.',
        'Los costos unitarios se indexan con el IPC; los costos de construcción subieron más que el IPC en 2021–2023, así que algunas equivalencias pueden quedar altas (cuentan más obras de las que alcanzarían).',
        'El periodo 2024–2027 está en curso: ingresos solo de 2024, contratación hasta el 20 de octubre de 2026 y regalías por aprobar a octubre de 2026.',
        'Las cifras de este archivo heredan las limitaciones de sus insumos: panel_anual.json, fugas_secop.json, sgr_fondos.json y costo_no_hacer.json.',
    ]


LIMITACIONES = limitaciones()

NOTAS_LEGALES = [
    'Este análisis describe hechos registrados y oportunidades perdidas. No acusa a ninguna persona: una investigación no es una condena y toda persona se presume inocente mientras no se le declare culpable (Constitución Política, art. 29).',
    'Las cifras describen a la administración municipal de cada periodo, no a la persona del alcalde. Solo se nombra a los alcaldes, como responsables políticos de cada periodo. No se publican nombres ni documentos de personas naturales contratistas ni de otros funcionarios (Ley 1581 de 2012, protección de datos personales).',
    'Cuando se nombra a una empresa o entidad contratista es para ubicar el contrato. No se afirma que haya cobrado de más ni que su trabajo fuera inútil: el costo de no competir es una estimación agregada y "sin obra" se refiere a decisiones posteriores del municipio.',
    'La contratación directa es legal en los casos que prevé la ley: prestación de servicios y apoyo a la gestión y convenios interadministrativos (Ley 1150 de 2007, art. 2, num. 4), convenios con entidades sin ánimo de lucro (Decreto 092 de 2017) y régimen especial de las empresas de servicios públicos (Ley 142 de 1994, art. 31) y de las E.S.E. (Ley 100 de 1993, art. 195). El costo estimado mide el precio usual de no competir, no una ilegalidad.',
    'Los contratos de prestación de servicios no pueden usarse para funciones permanentes de la entidad (Ley 80 de 1993, art. 32, num. 3; Corte Constitucional, Sentencia C-614 de 2009). El gasto en OPS por encima de lo usual es un indicio que debe contrastarse con la planta de personal.',
    'Los saldos de regalías no se pierden: lo no ejecutado pasa al bienio siguiente (Ley 2056 de 2020). Se muestran como plata quieta, aparte.',
    'La explotación de petróleo no es base del ICA municipal (Decreto 1056 de 1953, Código de Petróleos, art. 16; Ley 14 de 1983, art. 39): no se cuenta como recaudo dejado de cobrar.',
    'Las alertas de órganos de control (DNP, Procuraduría, Contraloría, Fiscalía) se citan en data/gobiernos.json con su estado procesal; este archivo no las usa para calcular montos.',
]

COSTOS_UNITARIOS = [{
    'id': id_, 'unidad': UNIDADES.get(id_) or PLURAL_EXTRA.get(id_), 'nombre': CU[id_]['nombre'], 'costo': r1(cu(id_)), 'min': r1(cu_min(id_)), 'max': r1(cu_max(id_)),
    'certeza': CU[id_]['certeza'], 'fuente': CU[id_]['fuente'], 'nota': CU[id_].get('nota'),
} for id_ in list(UNIDADES) + ['vis_urbana']]

COMO_LEER = [
    'Las cifras describen a la administración municipal de cada periodo, no a la persona del alcalde. No implican responsabilidad penal, fiscal ni disciplinaria: una investigación no es una condena.',
    'hecho: registro oficial verificable, o cálculo directo sobre registros oficiales (con enlace o archivo).',
    'estimado: cálculo con método explícito y rango (min–max).',
    'plata quieta: saldo de regalías sin comprometer en una fecha; es un hecho, pero no es plata perdida y no se suma a "sin obra".',
    'indicio: alerta para revisar (gasto en OPS por encima de lo usual); no se suma a "sin obra".',
    'contrafactual: lo que pudo pasar con otra decisión; no es plata perdida ni una acusación.',
    '"sin_obra" = total_hecho + total_estimado. "sin_obra_comparable" quita lo que solo se mide en algunos gobiernos (un solo oferente, que solo existe en SECOP II) y solo se da para 2012–2023.',
    'Un valor 0 con "sin_dato": true significa que no hay datos para medirlo, no que no existió; "no_aplica": true, que la categoría no existía en ese periodo. En totales_por_categoria esos casos van como null con su marca.',
    'Los items con "en_total": false son contexto y no se suman al valor de la fuga; los que tienen "en_total": true suman ese valor.',
]

salida = {
    'titulo': 'La plata que no se convirtió en obra a tiempo, por gobierno (Yondó, 2004–2027)',
    'generado_por': 'scripts/build_dinero_no_hecho.py',
    'fecha_corte': CORTE,
    'moneda': 'millones de COP constantes de 2026',
    'deflactor': (f"IPC DANE (base dic-2018 = 100). Flujos: promedio de cada año; 2026 = promedio ene–sep 2026 ({fmt(IPC_BASE, 3)}). Saldos con fecha: IPC del mes del "
                  f"corte (por ejemplo, dic-2022 = {fmt(IPC_MES[2022][11], 2)} / {fmt(IPC_BASE, 3)}). Mismo IPC de {F_PANEL} y {F_CNH}."),
    'metodo': METODO,
    'como_leer': COMO_LEER,
    'glosario': [{'termino': t, 'significa': s} for t, s in GLOSARIO],
    'categorias': CATEGORIAS,
    'literatura_sobrecosto': LIT_SOBRECOSTO,
    'tasas_sobrecosto': SOBRECOSTO,
    'referencia_ops': {'pesos_2026_por_habitante_al_anio': {k: round(v) for k, v in OPS_REF.items()}, 'anios': _ref_years,
                       'mediana_sin_ajustar': round(OPS_REF_ORIG),
                       'serie_pesos_2026_por_habitante': {a: round(OPS_PC[a]) for a in sorted(OPS_PC)},
                       'serie_sin_ajustar_pesos_2026_por_habitante': {a: round(OPS_PC_ORIG[a]) for a in sorted(OPS_PC_ORIG)},
                       'nota': ('Mediana (central), percentil 75 (mínimo de exceso) y percentil 25 (máximo de exceso) del gasto anual en OPS de la alcaldía por habitante, '
                                '2012–2025, sin transferencias, subsidios, convenios ni registros duplicados (fugas_secop.json, ajustes.ops).')},
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
CEDULA_RE = re.compile(r'(?i)(c[ée]dula|\bC\.\s?C\.|\bCC\b)\s*(de ciudadan[ií]a)?\s*(No\.?|N[°º]|:)?\s*\d[\d.]{4,}')


def validar(d):
    ids = {c['id'] for c in d['categorias']}
    assert d['moneda'] == 'millones de COP constantes de 2026'
    assert len(d['periodos']) == 6
    for p in d['periodos']:
        for k in ('ingresos', 'inversion', 'regalias', 'sgp', 'propios', 'total_hecho', 'total_estimado', 'total_plata_quieta', 'total_indicio', 'total_contrafactual'):
            assert isinstance(p[k], (int, float)), (p['id'], k)
        cats = [f['categoria'] for f in p['fugas']]
        assert set(cats) == ids and len(cats) == len(ids), (p['id'], cats)
        for f in p['fugas']:
            assert f['tipo'] in TIPOS and isinstance(f['valor'], (int, float)) and f['valor'] >= 0, (p['id'], f['categoria'])
            if f['min'] is not None:
                assert f['min'] <= f['valor'] + 0.11 and f['valor'] <= f['max'] + 0.11, (p['id'], f['categoria'], f['min'], f['valor'], f['max'])
            for it in f['items']:
                assert {'nombre', 'anio', 'valor', 'fuente', 'en_total'} <= set(it), (p['id'], f['categoria'], it)
            en = [it for it in f['items'] if it['en_total']]
            if en:
                s = sum(it['valor'] for it in en)
                assert abs(s - f['valor']) <= 0.06 * len(en) + 0.1, (p['id'], f['categoria'], s, f['valor'])
            if f['valor'] and f['tipo'] != 'contrafactual':
                assert f['fuentes'], (p['id'], f['categoria'])
        for t in TIPOS:
            s = round(sum(f['valor'] for f in p['fugas'] if f['tipo'] == t), 1)
            assert abs(s - p['total_' + t.replace(' ', '_')]) < 0.25, (p['id'], t, s)
        assert abs(p['sin_obra'] - p['total_hecho'] - p['total_estimado']) < 0.25, p['id']
        assert p['sin_obra_rango'][0] <= p['sin_obra'] + 0.2 <= p['sin_obra_rango'][1] + 0.4, (p['id'], p['sin_obra_rango'])
        sc = next(f for f in p['fugas'] if f['categoria'] == 'sobrecosto_sin_competencia')
        assert sc['base_compras_terceros'] <= sc['valor_sin_competencia_hecho'] + sc['un_oferente_base'] + 0.1, (p['id'], 'base > sin competencia')
        assert abs(sc['valor'] - sc['base_hecho'] * SOBRECOSTO['central']) < 0.2, p['id']
        assert abs(sc['valor'] - sc['costo_compras_terceros'] - sc['costo_transferencias']) < 0.2, p['id']
        gs = next(f for f in p['fugas'] if f['categoria'] == 'girado_sin_avance')
        assert sc['base_edu'] <= sc['base_compras_terceros'] + gs['valor'] + 0.1, (p['id'], 'EDU > línea 1')
        assert abs(gs['valor'] - (gs.get('valor_terminados') or 0) - (gs.get('valor_en_ejecucion') or 0)) < 0.2, (p['id'], 'girado: terminados + en ejecución')
        # lo que no es "sin obra" (plata quieta, indicio, contrafactual) no entra en sin_obra
        assert abs(p['sin_obra'] - sum(f['valor'] for f in p['fugas'] if f['tipo'] in TIPOS_SIN_OBRA)) < 0.25, p['id']
        assert 1 <= len(p['equivalencias']) <= 4, p['id']
        for e in p['equivalencias']:
            assert abs(e['n'] - p['sin_obra'] / e['costo_unitario']) < 0.2 + 0.01 * e['n'], (p['id'], e)
        for x in p['pudo_hacerse']:
            assert isinstance(x['costo'], (int, float)) and x['que'] and x['fuente'] and x['por_que_no'], (p['id'], x)
            assert x['cubierto_con_plata_sin_obra_pct'] is None or x['cubierto_con_plata_sin_obra_pct'] <= 999, x
        for fo in p['fondos_no_gestionados']:
            if fo.get('min') is not None and fo.get('max') is not None and isinstance(fo.get('monto_referencia'), (int, float)):
                assert fo['min'] - 0.11 <= fo['monto_referencia'] <= fo['max'] + 0.11, (p['id'], fo['fondo'])
        n_frases = p['lectura'].count('. ') + 1
        assert 2 <= n_frases <= 3, (p['id'], n_frases, p['lectura'])
    # totales por categoría coherentes con las fugas
    for t in d['totales_por_categoria']:
        for p in d['periodos']:
            f = next(x for x in p['fugas'] if x['categoria'] == t['categoria'])
            v = t['por_periodo'][p['id']]
            assert (v is None and t['marcas'].get(p['id'])) or abs(v - f['valor']) < 0.01, (t['categoria'], p['id'])
        if t['sumable_entre_gobiernos']:
            assert abs(t['total_2004_2026'] - sum(v or 0 for v in t['por_periodo'].values())) < 0.25, t['categoria']
    # coherencia con los insumos
    for p in d['periodos']:
        pp = PANEL_PER[p['id']]['agregados']
        assert abs(p['ingresos'] - pp['ingresos_totales']['suma_mm_2026']) < 1
        assert abs(p['propios'] - pp['tributarios']['suma_mm_2026']) < 0.06
    # datos personales: ningún número de cédula ni nombre de persona natural publicado
    texto = json.dumps(d, ensure_ascii=False)
    assert not CEDULA_RE.search(texto), CEDULA_RE.search(texto).group(0)
    assert 'Persona natural (nombre no publicado)' not in json.dumps([f['items'] for p in d['periodos'] for f in p['fugas']], ensure_ascii=False)
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


def valor_md(f):
    if f.get('no_aplica'):
        return 'no aplica'
    if f.get('sin_dato') and not f['valor']:
        return 's. d.'
    return fmt(f['valor'])


def valor_mm(f):
    if f.get('no_aplica'):
        return 'no aplica'
    if f.get('sin_dato') and not f['valor']:
        return 's. d.'
    return mm(f['valor'])


def doc_md(d):
    L = []
    L.append('# 10 · La plata que no se convirtió en obra a tiempo, gobierno por gobierno (2004–2027)')
    L.append('')
    L.append('> Documento generado por `scripts/build_dinero_no_hecho.py` a partir de `data/comparativa/panel_anual.json`, `fugas_secop.json`, `sgr_fondos.json`, '
             '`costo_no_hacer.json` y `data/gobiernos.json`. Los datos completos, con cada ítem y su fuente, están en `data/comparativa/dinero_no_hecho.json` '
             '(vista **Seis gobiernos → La plata** del atlas). Las cifras calculadas están en **millones de pesos de 2026** (M); las citas de un registro '
             'dicen "pesos corrientes" y su año.')
    L.append('')
    L.append('## 1. Qué mide este documento')
    L.append('')
    L.append('Cada gobierno de Yondó recibió una cantidad de plata y la convirtió, en parte, en obras. Aquí se cuenta la parte que **no** se convirtió en obra a tiempo '
             'o que pudo rendir más, y lo que **pudo entrar o ahorrarse** y no se obtuvo. Se separa en cinco niveles que no se mezclan:')
    L.append('')
    L.append('- **Hecho**: está en un registro oficial que cualquiera puede revisar, o sale de un cálculo directo sobre él. Por ejemplo, recursos de una obra de '
             f"regalías que va en {fmt(EJ_HECHO['ej_fisica'])} % de avance con {fmt(EJ_HECHO['ej_financiera'])} % pagado (GESPROY, octubre de 2026).")
    L.append('- **Estimado**: se calcula con un método explícito sobre registros oficiales y se da con un rango. Por ejemplo, el costo posible de contratar sin competencia.')
    L.append('- **Plata quieta**: regalías sin comprometer al cierre de un bienio. Es un hecho, pero **no es plata perdida**: pasa al bienio siguiente.')
    L.append('- **Indicio**: una alerta para revisar, como el gasto en contratos de prestación de servicios (OPS) por encima de lo usual en Yondó. Los servicios se prestaron.')
    L.append('- **Contrafactual**: lo que pudo pasar con otra decisión. Por ejemplo, cuánto valdría hoy un fondo con el 10 % de las regalías de 2004–2011. **No es plata perdida ni una acusación.**')
    L.append('')
    L.append('"Sin obra" es la suma de hecho y estimado. La plata quieta, los indicios y los contrafactuales van aparte y nunca se suman con lo anterior.')
    L.append('')
    L.append('> **Importante.** Las cifras describen a la administración municipal de cada periodo, no a la persona del alcalde. No implican responsabilidad penal, '
             'fiscal ni disciplinaria: una investigación no es una condena.')
    L.append('')
    L.append('**Palabras que se usan aquí.** ' + ' '.join(f"*{x['termino']}*: {x['significa']}" for x in d['glosario']))
    L.append('')
    L.append('## 2. Resumen por gobierno')
    L.append('')
    filas = []
    for p in d['periodos']:
        filas.append([p['id'], p['alcalde_corto'], fmt(p['ingresos']) + (' (2024)' if p['en_curso'] else ''),
                      fmt(p['total_hecho']) if p['id'] not in ('2004-2007', '2008-2011') else 's. d.', fmt(p['total_estimado']),
                      f"**{fmt(p['sin_obra'])}**", f"{fmt(p['sin_obra_rango'][0])}–{fmt(p['sin_obra_rango'][1])}", p['categorias_sin_obra_con_dato'],
                      (f"{fmt(p['sin_obra_pct_ingresos'], 1)} %" if p['sin_obra_pct_ingresos'] is not None else 'no comparable'),
                      valor_md(suma_fuga(p, 'saldos_regalias')), valor_md(suma_fuga(p, 'ops_nomina_paralela')), fmt(p['total_contrafactual'])])
    L.append(tabla(filas, ['Periodo', 'Alcalde', 'Ingresos', 'Hecho', 'Estimado', 'Sin obra', 'Rango sin obra', 'Categorías con dato', '% de ingresos',
                           'Plata quieta (aparte)', 'Indicio OPS (aparte)', 'Contrafactual (aparte)'],
                   ['l', 'l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r']))
    L.append('')
    comp = [p for p in d['periodos'] if p['sin_obra_comparable'] is not None]
    L.append('Ingresos: operaciones efectivas de caja del DNP (FUT vía TerriData), sumadas en pesos de 2026. "s. d." = sin dato. "Categorías con dato" dice cuántas de '
             'las cinco categorías de "sin obra" se pueden medir en cada gobierno. En 2004–2011 SECOP casi no tiene registros y no hay avance de las obras de regalías: '
             'esas cifras reflejan falta de datos y no permiten juzgar la gestión de esos años, ni para bien ni para mal; por eso su porcentaje sobre ingresos no es '
             'comparable. 2024–2027 solo tiene ingresos de 2024 y está en curso.')
    L.append('')
    L.append('Subtotal comparable 2012–2023 (las mismas categorías medidas igual; sin "un solo oferente", que solo existe en SECOP II): '
             + '; '.join(f"{p['id']}: {mm(p['sin_obra_comparable'])} ({fmt(p['sin_obra_comparable_pct_ingresos'], 1)} % de los ingresos)" for p in comp) + '.')
    L.append('')
    pend = next(p for p in d['periodos'] if p.get('pendiente_por_aprobar'))['pendiente_por_aprobar']
    L.append(f"Regalías por aprobar del bienio 2025–2026 (abierto hasta diciembre de 2026; no se suman), con corte del {fecha_corta(CORTE)}: {mm(pend['total'])}, "
             f"de ellos {mm(pend['aprueba_municipio'])} que aprueba el municipio y {mm(pend['aprueba_ocad_paz'])} del incentivo a la producción que aprueba el OCAD Paz."
             + frase_salvedad_ad(pend['asignaciones_directas']))
    L.append('')
    L.append('### Por categoría')
    L.append('')
    cab = ['Categoría', 'Tipo'] + [p['id'] for p in d['periodos']] + ['Total']
    filas = []
    for t in d['totales_por_categoria']:
        celdas = []
        for p in d['periodos']:
            v = t['por_periodo'][p['id']]
            celdas.append({'sin_dato': 's. d.', 'no_aplica': 'no aplica'}.get(t['marcas'].get(p['id']), fmt(v)) if v is None else fmt(v))
        filas.append([t['nombre'], t['tipo']] + celdas + [fmt(t['total_2004_2026']) if t['sumable_entre_gobiernos'] else 'no se suma'])
    L.append(tabla(filas, cab, ['l', 'l'] + ['r'] * 7))
    L.append('')
    L.append('La plata quieta son fotos de saldos en fechas distintas (la plata pasa de un bienio al siguiente) y el beneficio solar es un escenario distinto para cada gobierno: por eso no se suman entre gobiernos.')
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
        for f in sorted(p['fugas'], key=lambda x: (TIPOS.index(x['tipo']), -(x['valor'] or 0))):
            filas.append([CAT_NOMBRE[f['categoria']], f['tipo'], valor_md(f), rango(f), f['detalle'].replace('|', '/')])
        L.append(tabla(filas, ['Categoría', 'Tipo', 'Valor (M)', 'Rango', 'Detalle'], ['l', 'l', 'r', 'r', 'l']))
        L.append('')
        L.append(f"**Total:** hecho {valor_mm(suma_fuga(p, 'girado_sin_avance'))} · estimado {mm(p['total_estimado'])} · **sin obra {mm(p['sin_obra'])}** (rango {mm(p['sin_obra_rango'][0])}–{mm(p['sin_obra_rango'][1])}). "
                 f"Aparte: plata quieta {valor_mm(suma_fuga(p, 'saldos_regalias'))} · indicio OPS {valor_mm(suma_fuga(p, 'ops_nomina_paralela'))} · contrafactual {mm(p['total_contrafactual'])}.")
        L.append('')
        gi = suma_fuga(p, 'girado_sin_avance')['items']
        if gi:
            L.append('Proyectos de regalías con pagos por encima del avance reportado (GESPROY, octubre de 2026):')
            L.append('')
            L.append(tabla([[it['nombre'], it['bpin'], f"{fmt(it['avance_fisico_pct'])} % / {fmt(it['avance_financiero_pct'])} %",
                             (it.get('estado_gesproy') or '').capitalize(), fmt(it['valor_corriente'] / 1e6), fmt(it['valor']) if it['en_total'] else f"no se suma ({fmt(it['valor_si_se_contara'])})",
                             '; '.join(it.get('alertas_datos', []) + ([it['varios_municipios']] if it.get('varios_municipios') else []) + (['bienio compartido'] if it['anio_en_bienio_compartido'] else [])) or '—']
                            for it in gi],
                           ['Proyecto', 'BPIN', 'Avance físico / pagado', 'Estado', 'Brecha (M corrientes)', 'Brecha (M de 2026)', 'Alertas de datos'], ['l', 'l', 'r', 'l', 'r', 'r', 'l']))
            L.append('')
        if p['equivalencias']:
            L.append('**Para dimensionar, el valor central de "sin obra" equivale a:** ' + ' · '.join(
                f"{fmt(e['n'], 1 if e['n'] < 10 else 0)} {e['unidad']} (entre {fmt(e['rango_n'][0], 1 if e['rango_n'][0] < 10 else 0)} y {fmt(e['rango_n'][1], 1 if e['rango_n'][1] < 10 else 0)}; a {mm(e['costo_unitario'], 1 if e['costo_unitario'] < 100 else 0)} c/u)"
                for e in p['equivalencias'])
                + (f". De ese valor, {mm(p['total_hecho'])} es hecho y {mm(p['total_estimado'])} estimado." if not suma_fuga(p, 'girado_sin_avance').get('sin_dato')
                   else '. Todo ese valor es estimado: el hecho no tiene dato en estos años.'))
            L.append('')
        L.append('**Lo que Yondó necesitaba y pudo hacerse' + (' (y aún se puede)' if p['en_curso'] else '') + ':**')
        L.append('')
        L.append(tabla([[x['que'], fmt(x['costo']), x['equivalencia'], x['por_que_no']] for x in p['pudo_hacerse']],
                       ['Qué', 'Costo (M de 2026)', 'Equivale a', 'Qué pasó' if not p['en_curso'] else 'Situación'], ['l', 'r', 'l', 'l']))
        L.append('')
        if p['fondos_no_gestionados']:
            L.append('**Fondos externos de referencia:**')
            L.append('')
            L.append(tabla([[f['fondo'], fmt(f['monto_referencia']), (f"{fmt(f['min'])}–{fmt(f['max'])}" if f.get('min') is not None and f.get('max') is not None else '—'),
                             'sí' if f['suma_en_total'] else 'no', f['comparable']] for f in p['fondos_no_gestionados']],
                           ['Fondo', 'Referencia (M de 2026)', 'Rango', '¿Se suma?', 'Comparable'], ['l', 'r', 'r', 'l', 'l']))
            L.append('')
    L.append('## 4. Metodología')
    L.append('')
    L.append(d['metodo'])
    L.append('')
    L.append(tabla([[c['nombre'], c['tipo'], c['metodo']] for c in d['categorias']], ['Categoría', 'Tipo', 'Cómo se calcula'], ['l', 'l', 'l']))
    L.append('')
    L.append('### Cómo se evita contar dos veces la misma plata')
    L.append('')
    L.append(f'1. **Estudios con obra adentro.** Los contratos que incluyen diseño y construcción (como el de {mmc(EDU_MIXTO["valor"], EDU_MIXTO["anio"])}, con la EDU) '
             'no cuentan como estudios sin obra: su obra va dentro del contrato o ya está en "pagos por delante del avance".')
    L.append('2. **Costo de contratar sin competencia.** La base es lo que la alcaldía compró a terceros: se le quitan las OPS (tienen su propia categoría), los estudios sin obra, las transferencias a Aguas y Aseo, al hospital y a otras entidades de Yondó (subsidios a las tarifas, pagos por población pobre no afiliada, gastos de operación), los empréstitos y la plata ya contada en pagos por delante del avance. Lo transferido entra en una segunda línea solo hasta lo que esas entidades contrataron sin competencia ese año, y solo en años con datos.')
    L.append(f'3. **EDU de Medellín.** Con la EDU se firmaron {plural(len(EDU_CONTRATOS), "contrato", "contratos")} por {mmc(sum(c["valor"] for c in EDU_CONTRATOS), "2021–2023")} '
             f'(SECOP). Esos contratos financiaron, entre otros, {plural(len(EDU_PROY), "proyecto", "proyectos")} de regalías cuyo valor total en GESPROY es '
             f'${fmt(sum(EDU_PROY.values()) / 1e6)} M (pesos corrientes; valor de los proyectos, no de los contratos, y uno de ellos es de tres municipios). '
             'Su brecha entre pagos y avance se cuenta una sola vez, en "pagos por delante del avance", y se resta de la base del costo de no competir. El '
             'resto de los convenios con la EDU queda en la línea 1 de esa base, salvo en el mínimo.')
    L.append('4. **Plata quieta.** Un solo corte por gobierno, con la misma regla (el último bienio que cerró en su periodo) y la misma medida (presupuesto menos compromisos). Los cortes anteriores y el bienio compartido 2015–2016 se muestran como contexto y no se suman. La plata quieta no se suma a "sin obra" ni entre gobiernos.')
    L.append('5. **Fondos.** Los saldos del incentivo a la producción y de la inversión local ya son de Yondó: van como plata quieta o por aprobar, no como fondos no obtenidos. Obras por Impuestos (ventana 2018–2023) se reparte por años entre los dos gobiernos sin repetir la oportunidad. Findeter no se suma porque es crédito.')
    L.append('6. **Recaudo.** En el máximo, el predial con catastro actualizado y la brecha de predial con el percentil 75 no se suman: se toma el mayor.')
    L.append('')
    L.append('### Referencia del costo de contratar sin competencia')
    L.append('')
    L.append('El rango 3 %–6 %–10 % se apoya en estudios que miden precios. Ninguna cifra prueba que en Yondó haya habido corrupción: miden lo que suele costar renunciar a la competencia. Los estudios sobre sobornos y corrupción se muestran solo como contexto.')
    L.append('')
    L.append(tabla([[x['ref'], x['hallazgo'], x['uso'], x['url']] for x in d['literatura_sobrecosto']], ['Estudio', 'Hallazgo', 'Uso aquí', 'Enlace'], ['l', 'l', 'l', 'l']))
    L.append('')
    L.append('### Referencia del gasto en OPS')
    L.append('')
    ro = d['referencia_ops']['pesos_2026_por_habitante_al_anio']
    L.append(f"La ley no fija un tope de contratos de prestación de servicios, pero sí prohíbe usarlos para funciones permanentes (Sentencia C-614 de 2009). Como no hay un estándar nacional en datos abiertos, "
             f"la referencia es el propio Yondó: la mediana del gasto anual en OPS por habitante en 2012–2025 ({fmt(ro['mediana'])} pesos de 2026; {fmt(d['referencia_ops']['mediana_sin_ajustar'])} "
             f"antes de quitar transferencias, subsidios, convenios y duplicados). El rango usa el percentil 75 ({fmt(ro['p75'])}) y el 25 ({fmt(ro['p25'])}).")
    L.append('')
    serie = d['referencia_ops']['serie_pesos_2026_por_habitante']
    serie0 = d['referencia_ops']['serie_sin_ajustar_pesos_2026_por_habitante']
    L.append(tabla([[str(a) + (' (hasta octubre)' if str(a) == '2026' else ' (SECOP incompleto)' if int(a) < 2012 else ''), fmt(v), fmt(serie0.get(a)), fmt(v / ro['mediana'], 2)] for a, v in serie.items()],
                   ['Año', 'OPS por habitante (pesos de 2026)', 'Sin ajustar', 'Veces la mediana'], ['l', 'r', 'r', 'r']))
    L.append('')
    L.append('### Costos unitarios de las equivalencias')
    L.append('')
    L.append(tabla([[c['unidad'], fmt(c['costo'], 1 if c['costo'] < 100 else 0), f"{fmt(c['min'], 1 if c['min'] < 100 else 0)}–{fmt(c['max'], 1 if c['max'] < 100 else 0)}", c['certeza']] for c in d['costos_unitarios']],
                   ['Unidad', 'Costo central (M de 2026)', 'Rango', 'Certeza'], ['l', 'r', 'r', 'l']))
    L.append('')
    L.append('Fuentes de cada costo en `data/comparativa/costo_no_hacer.json` (campo `costos_unitarios`). Son órdenes de magnitud: una obra real necesita estudios, predios, interventoría y operación. '
             'En Yondó los suelos blandos y las zonas inundables empujan el costo por kilómetro hacia el máximo; por eso las equivalencias se dan con rango.')
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
    L.append('- SECOP I y II, SECOP Integrado: https://www.datos.gov.co/d/rpmr-utcd (vía `data/comparativa/fugas_secop.json`, campos `ajustes` y `ajustes_dinero_no_hecho`).')
    L.append('- GESPROY y MapaInversiones (proyectos de regalías): https://www.datos.gov.co/d/mzgh-shtp; MinHacienda, presupuesto SGR 2025–2026: https://www.datos.gov.co/d/e624-d9uy; CHIP y SICODIS (vía `data/comparativa/sgr_fondos.json`).')
    L.append('- DNP, operaciones efectivas de caja (TerriData): https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 (vía `data/comparativa/panel_anual.json`).')
    L.append('- IPC del DANE, serie mensual: https://www.dane.gov.co/files/operaciones/IPC/sep2026/anex-IPC-Indices-sep2026.xlsx.')
    L.append('- Costos unitarios, contrafactual solar, ahorro de regalías, recaudo y tasa retributiva: `data/comparativa/costo_no_hacer.json`.')
    L.append('- Superservicios, evaluación integral de Aguas y Aseo de Yondó (2020): https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf.')
    L.append('- Alerta del DNP sobre las viviendas (agosto de 2024): https://www.elcolombiano.com/medellin/escandalo-ocad-paz-edu-alcaldia-yondo-obras-CN25287252 y https://www.bluradio.com/regiones/antioquia/dnp-cuestiono-contratos-por-mas-de-16-000-millones-firmados-con-la-edu-rg10.')
    L.append('- Registro mercantil (RUES): https://www.datos.gov.co/d/c82u-588k.')
    L.append('- Hechos de cada gobierno: `data/gobiernos.json` y `docs/anexos/A-gobiernos-2004-2027.md`.')
    L.append('')
    return '\n'.join(L)


if __name__ == '__main__':
    validar(salida)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    DOC.write_text(doc_md(salida), encoding='utf-8')
    print(f'Escrito {SALIDA.relative_to(RAIZ)} y {DOC.relative_to(RAIZ)}')
    print(f"{'periodo':10} {'ingresos':>9} {'hecho':>8} {'estimado':>9} {'sin_obra':>9} {'rango':>15} {'quieta':>8} {'indicio':>8} {'contraf':>8}")
    for p in salida['periodos']:
        print(f"{p['id']:10} {p['ingresos']:9.0f} {p['total_hecho']:8.0f} {p['total_estimado']:9.0f} {p['sin_obra']:9.0f} {p['sin_obra_rango'][0]:7.0f}-{p['sin_obra_rango'][1]:<7.0f} "
              f"{p['total_plata_quieta']:8.0f} {p['total_indicio']:8.0f} {p['total_contrafactual']:8.0f}")
    for t in salida['totales_por_categoria']:
        print(f"  {t['categoria']:28} " + ' '.join(f"{(v or 0):8.0f}" for v in t['por_periodo'].values()) + f"  total={t['total_2004_2026']}")
