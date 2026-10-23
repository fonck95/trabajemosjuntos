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
# corta en el último espacio antes de n caracteres y termina en «…» (no a mitad de palabra)
def _corta(t, n):
    t = ' '.join(str(t).split())
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0].rstrip(' ,;:-') + '…'
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
    'estudios': [{'anio': e['anio'], 'valor': e['valor'], 'objeto': _corta(e['objeto'], 180).capitalize(), 'obra': _corta(e['obra_relacionada_probable'] or '', 110).capitalize() or None,
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
         'cpsam': 'Centro Vida', 'concejo': 'Concejo', 'registraduria': 'Registraduría', 'aguas_aseo_sede': 'Aguas y Aseo', 'cic': 'CIC', 'bienestar_anciano': 'Bienestar del Anciano', 'torre_hospital': 'Torre del hospital', 'relleno_parque': 'Parque solar del relleno'}
EDIFICIOS = []
for f in sorted((D / 'edificios').glob('*.json')):
    s = json.loads(f.read_text(encoding='utf-8'))
    if s.get('reemplazado_por'): continue   # levantamiento reemplazado por otra especificación (no se dibuja)
    if 'lat' not in s or 'lon' not in s: continue   # no es una sede: plantas y trazado de la torre (torre_hospital_plantas.json…)
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
        'pisos': f"{len(vols)} {'volumen' if len(vols) == 1 else 'volúmenes'}, hasta {pisos} piso{'s' if pisos != 1 else ''}",
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

# --- Datos de los modos nuevos de la torre (recorrido, dotación para la habilitación, contraste y simulador sísmico):
# especificación de integración, 10.1. Cada archivo se escribe solo si su insumo existe y está al día; si falta, se avisa y
# se sigue (los equipos que los generan trabajan en paralelo). Los generados guardan insumos_sha1 = {archivo: sha1}: si un
# insumo cambió después de generarlos, no se exportan hasta regenerarlos (así CI no necesita pasos nuevos).
import hashlib
AVISOS_WEB = []
LIMITES_KB = {'torre.json': 620, 'torre_plantas.json': 500, 'torre_inventario.json': 700, 'torre_habilitacion.json': 300,
              'torre_contraste.json': 150, 'sismo_torre_estructura.json': 250, 'sismo_amenaza.json': 90}
# carpetas donde se buscan los insumos que nombra insumos_sha1 (por nombre de archivo, o por ruta desde la raíz si la trae)
_CARPETAS_INSUMOS = [D / 'edificios', D / 'proyectos/torre_hospital', D / 'sismo', D, D / 'proyectos/torre_hospital/fuentes_investigacion', D / 'sismo/fuentes_investigacion']
# campos internos que no llegan a la web (10.1): trazas de origen, notas internas, huellas y rutas de archivo
_INTERNOS = {'origen', 'ref', 'fuente_reparto', 'nota_interna', 'insumos_sha1', 'sha256_dotacion', 'generado_por'}

def _aviso(m):
    AVISOS_WEB.append(m)
    print('  AVISO:', m)

def _escribir_web(nombre, obj):
    ruta = R / 'web/data' / nombre
    ruta.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    kb = ruta.stat().st_size / 1024
    lim = LIMITES_KB.get(nombre)
    print(f'{nombre} {kb:.0f} KB' + (f' (máximo {lim} KB)' if lim else ''))
    if lim and kb > lim:
        _aviso(f'{nombre} pesa {kb:.0f} KB y el máximo del contrato es {lim} KB')

def _no_exportar(nombre, motivo):
    """No escribe el archivo web y borra la copia vieja, para que la vista no muestre datos desactualizados."""
    _aviso(f'{nombre} no se exporta: {motivo}')
    vieja = R / 'web/data' / nombre
    if vieja.exists():
        vieja.unlink()

def _ausente(nombre, ruta):
    """El insumo todavía no existe: no se escribe el archivo web (y se borra una copia vieja, que ya no tendría de dónde salir)."""
    print(f'{nombre}: todavía no existe {ruta.relative_to(R)}; no se escribe')
    vieja = R / 'web/data' / nombre
    if vieja.exists():
        vieja.unlink()

def _sha(ruta, algo='sha1'):
    return hashlib.new(algo, Path(ruta).read_bytes()).hexdigest()

def _ruta_insumo(nombre):
    if '/' in nombre and (R / nombre).exists():
        return R / nombre
    return next((c / nombre for c in _CARPETAS_INSUMOS if (c / nombre).exists()), None)

def _al_dia(nombre_web, gen, ruta_gen):
    """True si insumos_sha1 de gen coincide con los archivos actuales; si no, avisa por qué."""
    hs = gen.get('insumos_sha1')
    if not isinstance(hs, dict) or not hs:
        _no_exportar(nombre_web, f'{ruta_gen.relative_to(R)} no trae insumos_sha1')
        return False
    malos = []
    for n_, h in hs.items():
        r = _ruta_insumo(n_)
        if r is None:
            malos.append(f'{n_} (no se encuentra)')
        elif _sha(r) != h:
            malos.append(f'{n_} (cambió)')
    if malos:
        _no_exportar(nombre_web, f'{ruta_gen.relative_to(R)} está desactualizado frente a ' + ', '.join(malos) + '; hay que regenerarlo')
        return False
    return True

def _cargar_generado(nombre_web, ruta):
    """Lee un archivo generado si existe y está al día; si no, None (con aviso cuando existe pero no sirve)."""
    if not ruta.exists():
        _ausente(nombre_web, ruta)
        return None
    try:
        gen = json.loads(ruta.read_text(encoding='utf-8'))
    except ValueError as e:
        _no_exportar(nombre_web, f'{ruta.relative_to(R)} no es JSON válido ({e})')
        return None
    return gen if _al_dia(nombre_web, gen, ruta) else None

def _sin_internos(o):
    if isinstance(o, dict):
        return {k: _sin_internos(v) for k, v in o.items() if k not in _INTERNOS}
    if isinstance(o, list):
        return [_sin_internos(x) for x in o]
    return o

def _redondear(o, d=2):
    if isinstance(o, float):
        return round(o, d)
    if isinstance(o, dict):
        return {k: _redondear(v, d) for k, v in o.items()}
    if isinstance(o, list):
        return [_redondear(x, d) for x in o]
    return o

def _fuentes(texto):
    """Las referencias del campo «fuente» (separadas por «;» fuera de paréntesis), todas y no solo la primera (4.5)."""
    if not texto:
        return []
    partes, nivel, act = [], 0, ''
    for ch in str(texto):
        nivel += (ch == '(') - (ch == ')')
        if ch == ';' and nivel <= 0:
            partes.append(act); act = ''
        else:
            act += ch
    partes.append(act)
    return [x.strip() for x in partes if x.strip()]

_INV_DATOS = {}
def _web_torre_inventario_datos():
    """inventario_dotacion.json si existe, está al día y coincide con el dotacion.json actual (sha256_dotacion); si no, None."""
    if 'v' not in _INV_DATOS:
        ruta = D / 'proyectos/torre_hospital/inventario_dotacion.json'
        inv = _cargar_generado('torre_inventario.json', ruta)
        dot = D / 'proyectos/torre_hospital/dotacion.json'
        if inv is not None and inv.get('sha256_dotacion') != _sha(dot, 'sha256'):
            _no_exportar('torre_inventario.json', 'sha256_dotacion del inventario no corresponde al dotacion.json actual; hay que regenerarlo')
            inv = None
        _INV_DATOS['v'] = inv
    return _INV_DATOS['v']

def _item_de_linea(l, dot, lab):
    """El ítem de dotacion.json (o de laboratorio.json) al que apunta la ref de una línea del inventario."""
    r, o = l.get('ref') or {}, l.get('origen')
    try:
        if o == 'laboratorio':
            return lab.get('equipos', [])[r['idx']]
        if o == 'cierre_brechas':
            return (dot.get('cierre_brechas_habilitacion') or {}).get('items', [])[r['idx']]
        if r.get('lista') == 'equipamiento_fijo':
            return dot.get('equipamiento_fijo', [])[r['idx']]
        srv = next(s_ for s_ in dot.get('servicios', []) if s_.get('id') == r.get('servicio'))
        return srv.get(r.get('lista'), [])[r['idx']]
    except (KeyError, IndexError, TypeError, StopIteration):
        return None

def _precio(item, origen):
    """Precio, rango, tipo, fuentes y método de una línea: una sola fuente de precio, la de dotacion.json o laboratorio.json (10.1)."""
    if origen == 'laboratorio':
        pm = item.get('precio_mercado') or {}
        return {'precio': pm.get('valor'), 'rango': pm.get('rango'), 'tipo_precio': pm.get('tipo') or 'valor_de_mercado',
                'fuentes_precio': _fuentes(pm.get('fuente')), 'metodo_precio': pm.get('metodo') or item.get('metodo_precio') or ''}
    return {'precio': item.get('precio_unitario_cop_2026'), 'rango': item.get('rango_precio_unitario_cop_2026'), 'tipo_precio': item.get('tipo_precio') or 'por_cotizar',
            'fuentes_precio': _fuentes(item.get('fuente')), 'metodo_precio': item.get('metodo_precio') or ''}

_RE_COMP = __import__('re').compile(r'^(U-.+-\d{3})-c\d+$')
def torre_inventario_web(inv, dot, lab, cat, imp, hab):
    """Forma web compacta del inventario (10.2)."""
    lineas, idx_linea = [], {}
    for l in inv.get('lineas', []):
        item = _item_de_linea(l, dot, lab)
        if item is None or (item.get('nombre') and item.get('nombre') != l.get('nombre')):
            raise ValueError(f'la línea {l.get("id")} no corresponde a su ítem de la dotación ({l.get("ref")})')
        cr, mt, rg = l.get('clase_riesgo') or {}, l.get('mantenimiento') or {}, l.get('registro_invima') or {}
        w = {'id': l['id'], 'nombre': l.get('nombre'), 'servicio': l.get('servicio'), 'tipo': l.get('tipo'), 'cantidad': l.get('cantidad'),
             'modelo3d': l.get('modelo3d'), 'especificacion': l.get('especificacion'),
             'clase': {'vigente': cr.get('vigente'), 'estado': cr.get('estado'), 'revision': l.get('clase_riesgo_revision')},
             'registro': {k: rg.get(k) for k in ('requerido', 'via', 'usado_permitido', 'nota') if k in rg},
             'exigencias': [{'id': e.get('id'), 'exigible': e.get('exigible')} for e in l.get('exigencias') or []],
             'prioridad': l.get('prioridad'), 'prioridad_revisada': l.get('prioridad_revisada'), 'norma_base': l.get('norma_base'),
             'mantenimiento': {k: mt.get(k) for k in ('anual_pct', 'vida_util_anios', 'personal_inscrito_invima', 'calibracion')},
             'componentes': l.get('componentes') or [], 'plantilla': l.get('plantilla_contenido'),
             **_precio(item, l.get('origen'))}
        for k in ('justificacion_recomendado', 'nota_exigencias', 'adquisicion', 'en_presupuesto', 'nota_precio', 'tecnologia_controlada', 'es_dispositivo_medico'):
            if l.get(k) is not None:
                w[k] = l[k]
        idx_linea[l['id']] = len(lineas)
        lineas.append(_sin_internos(w))
    us = inv.get('unidades', [])
    idx_u = {u['id']: i for i, u in enumerate(us)}
    filas = []
    for u in us:
        x, y, z = (list(u.get('posicion') or []) + [0.0, 0.0, 0.0])[:3]
        m_ = _RE_COMP.match(u['id'])
        filas.append([u['id'], idx_linea[u['linea']], u.get('piso'), u.get('recinto'), round(x, 3), round(y, 3), round(z, 3), round(u.get('rotacion_z') or 0.0, 4),
                      idx_u.get(u.get('apoyo'), -1), idx_u.get(u.get('dentro_de'), -1), idx_u.get(m_.group(1), -1) if m_ else -1, u.get('montaje'), u.get('estado')])
    modelos = (cat or {}).get('modelos', {})
    usados = sorted({l['modelo3d'] for l in lineas if l.get('modelo3d')})
    falta = [m_ for m_ in usados if m_ not in modelos]
    if falta:
        raise ValueError(f'modelos 3D sin entrada en catalogo_equipos.json: {falta}')
    catalogo = {}
    for m_ in usados:
        c = modelos[m_]
        catalogo[m_] = {'f': c.get('familia'), 'dim': c.get('dim_m'), 'b': c.get('b_m', min(c['dim_m'][0], c['dim_m'][1]) / 2), 'mont': c.get('montaje'), 'anc': c.get('anclaje'),
                        'masa': c.get('masa_kg'), 'hcg': c.get('h_cg_m'), 'mu': c.get('mu'), 'cont': bool(c.get('contenedor')), 'comp': c.get('compartimientos', [])}
    implementos = {}
    for nom_, pl in ((imp or {}).get('plantillas') or {}).items():
        implementos[nom_] = [{k2: v for k2, v in (('n', it.get('nombre')), ('c', it.get('cantidad')), ('comp', it.get('compartimiento')), ('tipo', it.get('tipo')),
                                                ('verif', it.get('verificacion')), ('clase', it.get('clase_riesgo')), ('reg', (it.get('registro_invima') or {}).get('requerido')),
                                                ('fuente', it.get('fuente'))) if v is not None} for it in pl.get('items', [])]
    # por recinto, el estado de la matriz y sus exigencias exigibles (las por confirmar van solo en el conteo, 4.8)
    exigible = {e.get('id'): e.get('exigible') for sv in (hab or {}).get('servicios', []) for e in sv.get('exigencias') or [] if isinstance(e, dict)}
    recintos = {rid: {'estado': r.get('estado'), 'exig': [x for x in r.get('exigencias', []) if exigible.get(x, 'si') == 'si'], 'por_confirmar': r.get('por_confirmar', 0)}
                for rid, r in ((hab or {}).get('por_recinto') or {}).items()}
    # totales: por servicio, sumados aquí con los precios de la dotación; el resto (laboratorio, habilitación, cierre) del inventario
    por_srv = {}
    for f in filas:
        l = lineas[f[1]]
        t = por_srv.setdefault(l['servicio'], {'unidades': 0, 'equipos_cop_2026': 0, 'mobiliario_cop_2026': 0})
        t['unidades'] += 1
        if _RE_COMP.match(f[0]) or l.get('tipo') not in ('equipo', 'mobiliario') or (l['id'].split('-')[-2] in ('c', 'x')):
            continue
        t[{'equipo': 'equipos_cop_2026', 'mobiliario': 'mobiliario_cop_2026'}[l['tipo']]] += l.get('precio') or 0
    tot_inv = inv.get('totales') or {}
    totales = {'por_servicio': por_srv, **{k: tot_inv[k] for k in ('laboratorio_json', 'habilitacion_cop_2026', 'cierre_brechas') if k in tot_inv}}
    return {'v': 2, 'catalogo': catalogo, 'lineas': lineas,
            'columnas_unidades': ['id', 'linea_idx', 'piso', 'recinto', 'x', 'y', 'z', 'rot_z', 'apoyo_idx', 'dentro_de_idx', 'componente_de_idx', 'montaje', 'estado'],
            'unidades': filas, 'implementos': implementos, 'recintos': recintos, 'totales': _sin_internos(totales)}

def torre_plantas_web(pl):
    """Forma compacta de las plantas (3.3): citas repetidas en una tabla (cada objeto lleva su índice en «cita»), sin
    poligono_libre ni fuentes largas, coordenadas con 2 decimales."""
    citas = list(pl.get('citas') or [])
    def cita(t):
        if t is None:
            return None
        if t not in citas:
            citas.append(t)
        return citas.index(t)
    niveles = []
    for nv in pl.get('niveles', []):
        nv = dict(nv)
        rs = []
        for r in nv.get('recintos', []):
            r = {k: v for k, v in r.items() if k != 'poligono_libre'}
            if isinstance(r.get('minimo_1633'), dict):
                r['minimo_1633'] = {**r['minimo_1633'], 'cita': cita(r['minimo_1633'].get('cita'))}
            if isinstance(r.get('climatizacion'), dict) and r['climatizacion'].get('fuente'):
                cl = dict(r['climatizacion'])
                cl['cita'] = cita(cl.pop('fuente'))
                r['climatizacion'] = cl
            rs.append(r)
        nv['recintos'] = rs
        nv['puertas'] = [{**{k: v for k, v in pt.items() if k != 'cita_ancho'}, **({'cita': cita(pt['cita_ancho'])} if pt.get('cita_ancho') else {})} for pt in nv.get('puertas', [])]
        niveles.append(nv)
    out = {k: v for k, v in pl.items() if k not in ('niveles', 'citas', 'fuentes')}
    out['niveles'] = niveles
    out['citas'] = citas
    return _redondear(_sin_internos(out), 2)

def torre_contraste_web(c, dot, lab, inv):
    """Contraste con el proyecto tipo (9.1): sin búsquedas ni acceso a fuentes; el costo de la dotación de cada ambiente se
    calcula aquí desde lineas_torre con los precios de dotacion.json (no se copia a mano)."""
    out = {k: v for k, v in c.items() if k not in ('busquedas', 'acceso_a_fuentes')}
    por_id = {l['id']: l for l in (inv or {}).get('lineas', [])}
    filas, sin_lineas = [], 0
    for f in out.get('dotacion_por_ambiente') or []:
        f = dict(f)
        f.pop('costo_torre_cop_2026', None)
        lt = f.get('lineas_torre')
        if isinstance(lt, list):
            items = [(por_id.get(x.get('linea')), x) for x in lt]
            if all(l for l, _ in items):
                tot = 0
                for l, _ in items:
                    it = _item_de_linea(l, dot, lab) or {}
                    p_ = _precio(it, l.get('origen'))['precio']
                    tot += (p_ or 0) * (l.get('cantidad') or 0)
                f['costo_torre_cop_2026'] = tot
                f['costo_torre_tipo'] = 'cálculo propio (precios de la dotación × cantidades)'
            else:
                f['costo_torre_cop_2026'] = None
        else:
            sin_lineas += 1
        filas.append(f)
    if 'dotacion_por_ambiente' in out:
        out['dotacion_por_ambiente'] = filas
    if sin_lineas:
        _aviso(f'torre_contraste.json: {sin_lineas} filas de dotacion_por_ambiente sin lineas_torre; se publican sin costo (el precio no se copia a mano)')
    return _sin_internos(out)

def _exportar_torre_y_sismo():
    tdir = D / 'proyectos/torre_hospital'
    dot = json.loads((tdir / 'dotacion.json').read_text(encoding='utf-8')) if (tdir / 'dotacion.json').exists() else {}
    lab = json.loads((tdir / 'laboratorio.json').read_text(encoding='utf-8')) if (tdir / 'laboratorio.json').exists() else {}
    opt_t = lambda n_: json.loads((tdir / n_).read_text(encoding='utf-8')) if (tdir / n_).exists() else None
    # plantas por piso (B)
    pl = _cargar_generado('torre_plantas.json', D / 'edificios/torre_hospital_plantas.json')
    if pl is not None:
        _escribir_web('torre_plantas.json', torre_plantas_web(pl))
    # matriz de cumplimiento en dotación e infraestructura (B)
    hab = _cargar_generado('torre_habilitacion.json', tdir / 'habilitacion.json')
    if hab is not None:
        _escribir_web('torre_habilitacion.json', _sin_internos(hab))
    # inventario (B): con el catálogo 3D y los implementos
    inv = _web_torre_inventario_datos()
    if inv is not None:
        try:
            _escribir_web('torre_inventario.json', torre_inventario_web(inv, dot, lab, opt_t('catalogo_equipos.json'), opt_t('implementos.json'), hab))
        except ValueError as e:
            _no_exportar('torre_inventario.json', str(e))
    # contraste con el proyecto tipo (E); no es un generado: se exporta si existe
    c = opt_t('proyecto_tipo_contraste.json')
    if c is None:
        _ausente('torre_contraste.json', tdir / 'proyecto_tipo_contraste.json')
    else:
        _escribir_web('torre_contraste.json', torre_contraste_web(c, dot, lab, inv))
    # simulador sísmico (A): estructura (generada) y amenaza (a mano)
    est = _cargar_generado('sismo_torre_estructura.json', D / 'sismo/torre_hospital_estructura.json')
    if est is not None:
        _escribir_web('sismo_torre_estructura.json', {k: v for k, v in est.items() if k not in ('insumos_sha1', 'generado_por')})
    am = D / 'sismo/amenaza.json'
    if am.exists():
        _escribir_web('sismo_amenaza.json', json.loads(am.read_text(encoding='utf-8')))
    else:
        _ausente('sismo_amenaza.json', am)

# --- Torre de servicios de primer nivel (data/proyectos/torre_hospital/): archivo aparte que la vista carga al abrirse
def _sel(d, keys):
    return {k: d[k] for k in keys if k in d} if isinstance(d, dict) else {}
_tdir = D / 'proyectos/torre_hospital'
# exigencias que el inventario enlaza a cada línea de dotacion.json (por su ref), para la ficha de cada equipo en torre.json
def _exigencias_por_ref():
    inv = _web_torre_inventario_datos()
    out = {}
    for l in (inv or {}).get('lineas', []):
        r = l.get('ref') or {}
        if l.get('origen') == 'dotacion' and r.get('lista') in ('equipos', 'mobiliario'):
            out[(r.get('servicio'), r['lista'], r.get('idx'))] = [{'id': e['id'], 'exigible': e.get('exigible')} for e in l.get('exigencias') or [] if e.get('id')]
    return out
_EQ = ('nombre', 'cantidad', 'clase_riesgo', 'precio_unitario_cop_2026', 'total_cop_2026', 'tipo_precio', 'prioridad', 'especificacion', 'nota')
def _equipo_web(e, srv, lista, i, exig):
    o = _sel(e, _EQ)
    if (srv, lista, i) in exig:
        o['exigencias'] = exig[(srv, lista, i)]
    return o
if _tdir.exists():
    _t = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted(_tdir.glob('*.json'))}
    _pr, _no, _pt, _do, _la = (_t.get(k, {}) for k in ('programa', 'normas', 'proyecto_tipo', 'dotacion', 'laboratorio'))
    _exig = _exigencias_por_ref()
    TORRE = {
        'programa': {**_sel(_pr, ('resumen', 'totales', 'resumen_por_piso', 'servicios', 'capacidad_resultante', 'uso_del_edificio_actual', 'demanda')),
                     'ambientes': [_sel(a_, ('servicio', 'nombre', 'cantidad', 'm2_unitario', 'm2_total', 'piso')) for a_ in _pr.get('ambientes', [])],
                     'implantacion': _sel(_pr.get('implantacion', {}), ('huella', 'accesos', 'demoliciones', 'pisos_y_alturas', 'zonificacion_en_planta', 'materiales_y_volumetria', 'cubierta_tecnica'))},
        'normas': _sel(_no, ('proyecto_en_breve', 'normas', 'checklist_485', 'parametros_diseno', 'conflictos_entre_normas')),
        'proyecto_tipo': _sel(_pt, ('respuesta_corta', 'proyectos_tipo', 'seleccion', 'escalamiento_a_torre', 'estetica')),
        'dotacion': {**_sel(_do, ('resumen', 'totales_generales', 'totales_equipamiento_fijo', 'comparaciones', 'proyectos_articulados', 'requisitos_res_485_para_dotacion', 'laboratorio_resumen')),
                     # cada equipo y mueble con su especificación, su nota y las exigencias que le enlaza el inventario (10.1)
                     'servicios': [{**_sel(s_, ('id', 'nombre', 'piso', 'capacidad', 'norma', 'totales')),
                                    **{lista: [_equipo_web(e_, s_.get('id'), lista, i, _exig) for i, e_ in enumerate(s_.get(lista, []))] for lista in ('equipos', 'mobiliario')}}
                                   for s_ in _do.get('servicios', [])],
                     'equipamiento_fijo': [_sel(e_, ('nombre', 'cantidad', 'precio_unitario_cop_2026', 'total_cop_2026', 'tipo_precio')) for e_ in _do.get('equipamiento_fijo', [])]},
        'laboratorio': {**_sel(_la, ('resumen', 'totales_menu', 'areas', 'area_total_laboratorio_piso2_m2', 'costos_operacion_anual', 'modelo_de_compra', 'lis', 'calidad', 'referencia_de_muestras')),
                        'menu': [_sel(m_, ('id', 'prueba', 'seccion', 'metodo', 'equipo', 'ruta', 'tiempo_respuesta', 'volumen_mes')) for m_ in _la.get('menu', [])],
                        'equipos': [{**_sel(e_, ('nombre', 'cantidad', 'funcion', 'capacidad', 'modelo_de_compra')), 'precio': (e_.get('precio_mercado') or {}).get('valor'), 'uso_pico_pct': (e_.get('carga') or {}).get('uso_en_hora_pico_pct')} for e_ in _la.get('equipos', [])]},
    }
    for k in ('presupuesto', 'apu', 'financiacion', 'proyectos'):
        if k in _t: TORRE[k] = _t[k]
    (R / 'web/data').mkdir(parents=True, exist_ok=True)
    _escribir_web('torre.json', TORRE)
    _exportar_torre_y_sismo()

# --- Parque ecotecnológico sobre el relleno sanitario (data/proyectos/parque_relleno/): archivo aparte para su vista
_pdir = D / 'proyectos/parque_relleno'
if _pdir.exists():
    _pq = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted(_pdir.glob('*.json'))}
    PARQUE = {
        'diagnostico': _sel(_pq.get('diagnostico', {}), ('respuesta_corta', 'sitio', 'estado_legal_y_operacion', 'toneladas', 'clausura_requisitos', 'posclausura', 'alternativa_regional')),
        'energia': _sel(_pq.get('energia', {}), ('respuesta_corta', 'recurso_solar', 'granja', 'solar_propia_del_parque', 'conexion_a_la_red', 'estratos_1_y_2', 'cobertura_de_hogares', 'ahorro_anual', 'costo_de_la_energia_solar', 'figura_legal')),
        'programa': _sel(_pq.get('programa', {}), ('idea', 'regla_de_oro', 'inspiracion_proyectos_tipo_dnp', 'componentes', 'usuarios_esperados', 'operacion', 'cronograma_fases')),
        'presupuesto': _sel(_pq.get('presupuesto', {}), ('clase', 'capitulos', 'costo_directo', 'interventoria', 'gestion_social_y_ambiental', 'imprevistos', 'total', 'total_millones', 'rango_millones', 'por_fase_millones', 'costos_anuales_millones')),
        'financiacion': _sel(_pq.get('financiacion', {}), ('total_a_financiar_millones', 'principio', 'fuentes', 'mezcla_sugerida_millones', 'compuertas')),
    }
    (R / 'web/data').mkdir(parents=True, exist_ok=True)
    (R / 'web/data/parque.json').write_text(json.dumps(PARQUE, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('parque.json', (R / 'web/data/parque.json').stat().st_size // 1024, 'KB')

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
print(f'Avisos de los datos de la torre y del simulador: {len(AVISOS_WEB)}')
for a_ in AVISOS_WEB:
    print('  -', a_)
