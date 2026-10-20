"""Genera web/js/data.js a partir de los JSON de data/ (única fuente de verdad del sitio).

Uso: python3 scripts/build_data.py
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data'
load = lambda p: json.loads((D / p).read_text(encoding='utf-8'))

sec = load('secop/secop_resumen.json')
textos = load('textos.json')

# --- SECOP: matriz periodo × categoría por entidad
PERIODOS = ['2008-2011', '2012-2015', '2016-2019', '2020-2023', '2024-2027']
CATS = [  # el orden de filas sigue el orden de la paleta categórica (pares adyacentes validados)
    ('Obra', 'Obra pública', 'Obra', 1),
    ('OPS / apoyo a la gestión', 'OPS y apoyo a la gestión', 'OPS', 2),
    ('Interventoría', 'Interventoría', 'Interventoría', 3),
    ('Convenios / interadministrativos', 'Convenios e interadministrativos', 'Convenios', 4),
    ('Otros servicios', 'Otros servicios', 'Otros serv.', 5),
    ('Suministro / compraventa', 'Suministro y compraventa', 'Suministro', 6),
    ('Estudios / consultoría', 'Estudios, diseños y consultoría', 'Estudios', 7),
]
por = {}
for r in sec['por_periodo']:
    if r['periodo'] not in PERIODOS:
        continue
    por.setdefault(r['ent'], {}).setdefault(r['periodo'], {})[r['categoria']] = {'n': r['n'], 'valor': r['valor']}

def tot(ent, cat=None, periodos=PERIODOS, campo='valor'):
    s = 0
    for p in periodos:
        for c, v in por.get(ent, {}).get(p, {}).items():
            if cat is None or c == cat:
                s += v[campo]
    return s

def cop(v):
    if v >= 1e12:
        return f"${v / 1e12:.2f} billones".replace('.', ',')
    if v >= 1e9:
        return f"${v / 1e9:,.1f} mil M".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"${v / 1e6:,.0f} M".replace(',', '.')

def n(v):
    return f"{v:,.0f}".replace(',', '.')

directa = sec['directa_por_periodo']
d2026 = [x for x in directa if x['periodo'] in ('2020-2023', '2024-2027')]
pct_dir_20_26 = sum(x['valor'] * x['pct_valor_directa'] for x in d2026) / sum(x['valor'] for x in d2026)
edu = sum(t['valor'] for t in sec['edu'])
n_edu = len(sec['edu'])
aguas_conv = sum(t['valor'] for t in sec['top_juridicas_alcaldia'] if 'AGUAS Y ASEO' in t['nom_raz_social_contratista'].upper())
estudios = sec['estudios']
est_obra = [e for e in estudios if e['obra_relacionada_probable']]
est_liq = [e for e in est_obra if (e['estado_obra'] or '').lower() in ('liquidado', 'terminado')]
ops_form = [x for x in sec['ops_formulacion'] if x['ent'] == 'ALCALDIA']

kpis = {
    'ALCALDIA': [
        {'v': cop(tot('ALCALDIA')), 'l': 'contratado 2008–2026 (SECOP, depurado)'},
        {'v': f"{pct_dir_20_26:.0f} %".replace('.', ','), 'l': 'del valor 2020–2026 sin competencia (contratación directa o régimen especial)'},
        {'v': n(tot('ALCALDIA', 'OPS / apoyo a la gestión', campo='n')), 'l': 'contratos OPS y de apoyo a la gestión 2008–2026'},
        {'v': cop(edu), 'l': 'en administración delegada con la EDU de Medellín (2021–2023)'},
    ],
    'HOSPITAL': [
        {'v': cop(tot('HOSPITAL')), 'l': 'registrado en SECOP (cobertura muy incompleta)'},
        {'v': n(tot('HOSPITAL', 'OPS / apoyo a la gestión', campo='n')), 'l': 'contratos OPS registrados'},
        {'v': f"{100 * tot('HOSPITAL', 'OPS / apoyo a la gestión') / max(1, tot('HOSPITAL')):.0f} %", 'l': 'del valor registrado es OPS'},
        {'v': '2016–2019', 'l': 'periodo sin ningún contrato publicado'},
    ],
    'AGUAS': [
        {'v': cop(tot('AGUAS')), 'l': 'contratado por Aguas y Aseo de Yondó 2011–2026'},
        {'v': cop(aguas_conv), 'l': 'transferido por la alcaldía a la empresa vía convenios'},
        {'v': n(tot('AGUAS', campo='n')), 'l': 'contratos registrados'},
        {'v': n(tot('AGUAS', 'OPS / apoyo a la gestión', campo='n')), 'l': 'de ellos, OPS y apoyo'},
    ],
}

# Ingresos en caja por periodo (Operaciones Efectivas de Caja, DNP–FUT vía TerriData)
import csv
oec = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv'))}
sgp = {int(r['anio']): float(r['Total asignado SGP']) for r in csv.DictReader(open(D / 'fuentes/sgp_sicodis.csv'))}
ingresos = {}
for p in PERIODOS:
    ys = [y for y in range(int(p[:4]), int(p[:4]) + 4) if y in oec]
    ingresos[p] = {'valor': sum(float(oec[y]['ingresos_totales_mm']) for y in ys) * 1e6,
                   'regalias': sum(float(oec[y]['regalias_giradas_mm_derivado']) for y in ys) * 1e6,
                   'nota': 'ingresos en caja' + ('' if len(ys) == 4 else f" (solo {ys[0]})")}
ing_total = sum(float(r['ingresos_totales_mm']) for y, r in oec.items() if 2004 <= y <= 2024) * 1e6
reg_0411 = sum(float(oec[y]['regalias_giradas_mm_derivado']) for y in range(2004, 2012)) * 1e6
sgp_0424 = sum(v for y, v in sgp.items() if 2004 <= y <= 2024)

SECOP = {
    'periodos': PERIODOS,
    'ingresos': ingresos,
    'categorias': [{'key': k, 'label': l, 'corto': c, 'slot': s} for k, l, c, s in CATS],
    'por_periodo': por,
    'directa': directa,
    'top_celdas': [t for t in sec['top_celdas'] if t['periodo'] in PERIODOS],
    'kpis': kpis,
    'hallazgos': textos['hallazgos_dinero'],
    'registros': {'brutos': sec['registros_brutos'], 'limpios': sec['registros_limpios']},
}

top_est = sorted(estudios, key=lambda e: -e['valor'])[:16]
EMBUDO = {
    'etapas': [
        {'etapa': 'Estudios, diseños y consultorías', 'n': len(estudios), 'valor': sum(e['valor'] for e in estudios), 'unidad': 'contratos', 'slot': 7,
         'nota': 'Contratos de la alcaldía 2008–2026 cuyo objeto es estudiar, diseñar, formular o planear (SECOP).'},
        {'etapa': 'Con obra posterior identificable', 'n': len(est_obra), 'valor': sum(e['valor'] for e in est_obra), 'unidad': 'contratos', 'slot': 4,
         'nota': 'Se halló en SECOP una obra posterior con objeto similar (coincidencia de palabras clave ≥ 30 %). Es un indicio, no una prueba.'},
        {'etapa': 'Obra liquidada o terminada', 'n': len(est_liq), 'valor': sum(e['valor'] for e in est_liq), 'unidad': 'contratos', 'slot': 1,
         'nota': 'La obra relacionada figura como liquidada o terminada en SECOP.'},
    ],
    'ops_formulacion': {'n': sum(x['n'] for x in ops_form), 'valor': sum(x['valor'] for x in ops_form), 'por_periodo': ops_form},
    'rupturas': textos['rupturas_embudo'],
    'estudios': [{'anio': e['anio'], 'valor': e['valor'], 'objeto': e['objeto'][:180].capitalize(), 'obra': (e['obra_relacionada_probable'] or '')[:110].capitalize() or None,
                  'anio_obra': e['anio_obra']} for e in top_est],
}

per = load('periodos.json')
mr = load('microrred.json')
mr['presupuesto'] = load('presupuesto_microrred.json')
hosp = load('hospital2028.json')
ruta = load('ruta.json')

# Textos con cifras calculadas
fill = {
    '{TOTAL_ALC}': cop(tot('ALCALDIA')), '{PCT_DIR}': f"{pct_dir_20_26:.0f}", '{N_OPS}': n(tot('ALCALDIA', 'OPS / apoyo a la gestión', campo='n')),
    '{EDU}': cop(edu), '{N_EDU}': str(n_edu), '{N_EST}': str(len(estudios)), '{V_EST}': cop(sum(e['valor'] for e in estudios)), '{N_EST_OBRA}': str(len(est_obra)),
    '{PCT_EST_OBRA}': f"{100 * len(est_obra) / len(estudios):.0f}", '{N_EST_LIQ}': str(len(est_liq)),
    '{N_OPS_FORM}': n(EMBUDO['ops_formulacion']['n']), '{V_OPS_FORM}': cop(EMBUDO['ops_formulacion']['valor']),
    '{REG_BRUTOS}': n(sec['registros_brutos']), '{REG_LIMPIOS}': n(sec['registros_limpios']),
    '{ING_TOTAL}': cop(ing_total), '{REG_0411}': cop(reg_0411), '{SGP_0424}': cop(sgp_0424),
}
def subst(o):
    if isinstance(o, str):
        for k, v in fill.items():
            o = o.replace(k, v)
        return o
    if isinstance(o, list):
        return [subst(x) for x in o]
    if isinstance(o, dict):
        return {k: subst(v) for k, v in o.items()}
    return o

out = {
    'TEXTOS': subst({k: v for k, v in textos.items() if isinstance(v, str)}),
    'SECOP': subst(SECOP), 'EMBUDO': subst(EMBUDO),
    'PERIODOS': subst(per['periodos']), 'AREAS': subst(per['areas']),
    'MICRORRED': mr, 'HOSPITAL': subst(hosp), 'RUTA': subst(ruta),
}
js = '// Generado por scripts/build_data.py — no editar a mano.\n' + ''.join(
    f"export const {k} = {json.dumps(v, ensure_ascii=False, separators=(',', ':'))};\n" for k, v in out.items())
(R / 'web/js/data.js').write_text(js, encoding='utf-8')
(D / 'cifras_calculadas.json').write_text(json.dumps(fill, ensure_ascii=False, indent=1), encoding='utf-8')
print('data.js', len(js) // 1024, 'KB')
for k, v in fill.items():
    print(f'  {k} = {v}')
