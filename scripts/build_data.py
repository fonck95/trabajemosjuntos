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

# --- Réplicas de las sedes (data/edificios/*.json + web/models/edificios/manifest.json) y calles de OpenStreetMap
import math
calles = load('geo/calles.json') if (D / 'geo/calles.json').exists() else {'origen': {'lat': 7.0065, 'lon': -73.9115}, 'calles': [], 'agua': [], 'canos': []}
lat0, lon0 = calles['origen']['lat'], calles['origen']['lon']
man_path = R / 'web/models/edificios/manifest.json'
manifest = {m['id']: m for m in json.loads(man_path.read_text(encoding='utf-8'))} if man_path.exists() else {}
nodos = {n_['id']: n_ for n_ in mr['nodos']}
CORTO = {'alcaldia': 'Alcaldía + CCED', 'hospital': 'Hospital', 'policia': 'Policía', 'bomberos': 'Bomberos', 'ptap': 'Planta de agua (PTAP)',
         'captacion': 'Captación', 'ptap_veredal': 'Planta veredal', 'tanque_elevado': 'Tanque elevado', 'ie_led': 'I.E. L. E. Díaz', 'ie_prim': 'Sede La Patria',
         'ie_megacolegio': 'Megacolegio', 'parque_edu': 'Parque Educativo', 'cultura': 'Biblioteca', 'casa_cultura': 'Casa de la Cultura', 'coliseo': 'Coliseo',
         'cpsam': 'Centro Vida', 'concejo': 'Concejo', 'registraduria': 'Registraduría', 'aguas_aseo_sede': 'Aguas y Aseo', 'cic': 'CIC', 'bienestar_anciano': 'Bienestar del Anciano'}
EDIFICIOS = []
for f in sorted((D / 'edificios').glob('*.json')):
    s = json.loads(f.read_text(encoding='utf-8'))
    m = manifest.get(s['id'], {})
    ad = s.get('adecuaciones', {})
    vols = s.get('volumenes', [])
    pisos = max((v.get('pisos', 1) for v in vols), default=1)
    nodo = nodos.get(s.get('nodo_microrred') or s['id'])
    EDIFICIOS.append({
        'id': s['id'], 'nombre': s.get('nombre', s['id']), 'corto': s.get('nombre_corto') or CORTO.get(s['id']) or (nodo or {}).get('corto') or s.get('nombre', s['id']),
        'nodo_microrred': s.get('nodo_microrred'), 'direccion': s.get('direccion'),
        'lat': s['lat'], 'lon': s['lon'],
        'x': round((s['lon'] - lon0) * 111320 * math.cos(math.radians(lat0)), 1), 'y': round((s['lat'] - lat0) * 111320, 1),
        'confianza': (s.get('ubicacion') or {}).get('confianza'),
        'pisos': f"{len(vols)} volumen{'es' if len(vols) != 1 else ''}, hasta {pisos} piso{'s' if pisos != 1 else ''}",
        'kwp_plan': ad.get('kwp_plan'), 'kwp_factible': m.get('kwp_modelado', ad.get('kwp_factible')), 'modulos': m.get('modulos'),
        'bess': ({k: ad['bess'].get(k) for k in ('kwh', 'kw', 'tipo')} if ad.get('bess') else None),
        'domotica': ad.get('domotica', []), 'obras_civiles': ad.get('obras_civiles', []), 'notas': ad.get('notas'),
        'incertidumbres': s.get('incertidumbres', []), 'fuentes': m.get('fuentes', []),
        'puntos': ([{'tipo': 'bess', 'x': ad['bess']['centro'][0], 'y': ad['bess']['centro'][1]}] if (ad.get('bess') or {}).get('centro') else [])
                  + [{'tipo': 'marquesina', 'x': a['centro'][0], 'y': a['centro'][1]} for a in ad.get('fv', []) if a.get('tipo') == 'marquesina' and a.get('centro')],
        'archivo': m.get('archivo'), 'archivo_lod1': m.get('archivo_lod1'), 'tamano': m.get('tamano'),
        'bytes': m.get('bytes'), 'triangulos': m.get('triangulos'),
        # puntos del modelo (metros, y arriba) donde se dibujan el tablero/medidor, el gateway IoT y la acometida
        'conexion': m.get('conexion'),
    })
CALLES = calles
# huellas de edificaciones (contexto urbano): archivo aparte para no engordar data.js
if (D / 'geo/huellas.json').exists():
    (R / 'web/models/contexto').mkdir(parents=True, exist_ok=True)
    (R / 'web/models/contexto/huellas.json').write_text((D / 'geo/huellas.json').read_text(encoding='utf-8'), encoding='utf-8')

# --- Comparativa: plata que no se volvió obra por gobierno y panel anual (data/comparativa/)
opt = lambda p_: load(p_) if (D / p_).exists() else {}
_din = opt('comparativa/dinero_no_hecho.json')
# para la web basta lo que se dibuja: por fuga, los 6 ítems de mayor valor (el JSON completo queda en data/comparativa/)
def _fuga(f):
    f = dict(f)
    if isinstance(f.get('items'), list):
        f['items'] = sorted(f['items'], key=lambda x: -(x.get('valor') or 0) if isinstance(x, dict) else 0)[:6]
    f.pop('fuentes_detalle', None)
    return f
DINERO = {k: _din[k] for k in ('moneda', 'como_leer', 'categorias', 'limitaciones', 'notas_legales', 'fecha_corte') if k in _din}
if _din:
    DINERO['periodos'] = [{**p_, 'fugas': [_fuga(f) for f in p_.get('fugas', [])]} for p_ in _din['periodos']]
_panel = opt('comparativa/panel_anual.json')
PANEL = {'anios': _panel.get('anios', []), 'indicadores': _panel.get('indicadores', [])} if _panel else {}

# --- Red de distribución: distancias por la vía entre sedes y red propuesta (scripts/geo/red_distancias.py) y su presupuesto
_dist = opt('red/distancias.json')
RED = {}
if _dist:
    RED = {k: _dist[k] for k in ('fuente', 'metodo', 'raiz', 'puntos', 'matriz_via_km', 'matriz_recta_km') if k in _dist}
    RED['arbol'] = {**_dist['arbol'], 'tramos': [{**t, 'ruta': [[round(x), round(y)] for x, y in t['ruta']]} for t in _dist['arbol']['tramos']]}
    _pres = opt('red/presupuesto_red.json')
    if _pres: RED['presupuesto'] = _pres

out = {
    'EDIFICIOS': EDIFICIOS, 'CALLES': CALLES, 'DINERO': DINERO, 'PANEL': PANEL, 'RED': RED,
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
