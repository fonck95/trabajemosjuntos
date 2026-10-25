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

_CADENA = {}
def _insumos_viejos(ruta_gen, gen=None, pila=()):
    """Insumos de un archivo generado que cambiaron después de generarlo, siguiendo la cadena: si un insumo es a su vez un
    generado (trae insumos_sha1) y está desactualizado, el archivo también lo está aunque el hash del insumo coincida (p. ej.
    el inventario generado con unas plantas que ya no corresponden a su trazado)."""
    clave = str(ruta_gen)
    if clave in _CADENA:
        return _CADENA[clave]
    if gen is None:
        try:
            gen = json.loads(Path(ruta_gen).read_text(encoding='utf-8'))
        except ValueError:
            return []
    hs = gen.get('insumos_sha1') if isinstance(gen, dict) else None
    malos = []
    for n_, h in (hs or {}).items():
        r = _ruta_insumo(n_)
        if r is None:
            malos.append(f'{n_} (no se encuentra)')
        elif _sha(r) != h:
            malos.append(f'{n_} (cambió)')
        elif r.suffix == '.json' and str(r) not in pila and r.stat().st_size < 50e6:
            sub = _insumos_viejos(r, None, pila + (clave,))
            if sub:
                malos.append(f'{n_} (está desactualizado frente a {", ".join(sub)})')
    _CADENA[clave] = malos
    return malos

def _al_dia(nombre_web, gen, ruta_gen):
    """True si insumos_sha1 de gen coincide con los archivos actuales (y los de sus insumos generados); si no, avisa por qué."""
    hs = gen.get('insumos_sha1')
    if not isinstance(hs, dict) or not hs:
        _no_exportar(nombre_web, f'{ruta_gen.relative_to(R)} no trae insumos_sha1')
        return False
    malos = _insumos_viejos(ruta_gen, gen)
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
    """El ítem de dotacion.json (o de laboratorio.json) al que apunta la ref de una línea del inventario. Las líneas de
    infraestructura y de contexto (16.3) no tienen ítem de dotación: devuelve None."""
    r, o = l.get('ref') or {}, l.get('origen')
    try:
        if o == 'infraestructura':
            return None
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

def _precio_linea(l, dot, lab):
    """Precio web de una línea del inventario. Dotación, equipamiento fijo y cierre de brechas: de dotacion.json; laboratorio:
    de laboratorio.json; infraestructura y contexto (16.3): sin precio de dotación (es obra o contexto; el ítem de obra va en
    cita_presupuesto). Lanza ValueError si la ref no lleva a un ítem con el mismo nombre."""
    if l.get('origen') == 'infraestructura':
        return {'precio': None, 'rango': None, 'tipo_precio': l.get('tipo_precio') or 'obra', 'fuentes_precio': [],
                'metodo_precio': l.get('metodo_precio') or ''}
    item = _item_de_linea(l, dot, lab)
    if item is None or (item.get('nombre') and item.get('nombre') != l.get('nombre')):
        raise ValueError(f'la línea {l.get("id")} no corresponde a su ítem de la dotación ({l.get("ref")})')
    p_ = _precio(item, l.get('origen'))
    if not p_['metodo_precio']:            # laboratorio.json no trae método: se explica con el del inventario
        p_['metodo_precio'] = l.get('metodo_precio') or ''
    return p_

def _precio_dotacion(l, dot):
    """Precio unitario de dotacion.json de una línea de dotación, equipamiento fijo o cierre de brechas; None en las demás
    (laboratorio en comodato, infraestructura) o si la línea no existe."""
    if not l or l.get('origen') not in ('dotacion', 'cierre_brechas'):
        return None
    it = _item_de_linea(l, dot, {})
    return it.get('precio_unitario_cop_2026') if it and it.get('nombre') == l.get('nombre') else None

def _redondear_planta(o):
    """Coordenadas (números dentro de listas: puntos, rectángulos, polígonos) con 2 decimales y el resto con 3 (contrahuellas,
    kWp por módulo), para no perder la cota de un peldaño."""
    if isinstance(o, dict):
        return {k: _redondear_planta(v) for k, v in o.items()}
    if isinstance(o, list):
        return [round(x, 2) if isinstance(x, float) else _redondear_planta(x) for x in o]
    return round(o, 3) if isinstance(o, float) else o

def _dentro(p, pol):
    """¿El punto p = (x, y) está dentro del polígono (lista de [x, y])? Regla par-impar."""
    x, y, c, n_ = p[0], p[1], False, len(pol)
    for i in range(n_):
        (x1, y1), (x2, y2) = pol[i], pol[(i + 1) % n_]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c

# Archivos web que se parten si pasan su límite (10.1; la tarea pide partir por nivel y documentarlo). El archivo principal
# queda con lo que no se parte y con «partes» {archivos, nota}; cada parte {base}_{sufijo}.json trae trozos de listas (se
# concatenan en el orden de «archivos») y de diccionarios (se suman). La vista (torre.js → leer) junta las partes antes de
# pasar los datos a cada modo, así que C y E reciben el mismo esquema que si fuera un solo archivo.
def _partir_plantas(todo, lim):
    """Un archivo por nivel (EXT, P1-P4, BT, CUB)."""
    return {k: v for k, v in todo.items() if k != 'niveles'}, [(nv.get('id') or str(i), {'niveles': [nv]}) for i, nv in enumerate(todo.get('niveles') or [])]

def _partir_matriz(todo, lim):
    """Servicios seguidos, en grupos que caben en el 90 % del límite."""
    grupos, act = [], []
    for sv in todo.get('servicios') or []:
        if act and _kb({'servicios': act + [sv]}) > 0.9 * lim:
            grupos.append(act); act = []
        act.append(sv)
    if act:
        grupos.append(act)
    return {k: v for k, v in todo.items() if k != 'servicios'}, [(str(i + 1), {'servicios': g}) for i, g in enumerate(grupos)]

def _partir_inventario(todo, lim):
    """Las unidades (y sus datos extra) por nivel, en el orden de por_nivel (las unidades ya vienen ordenadas por nivel, así
    que los índices apoyo_idx, dentro_de_idx y componente_de_idx valen igual en el archivo juntado), y los implementos aparte."""
    fuera = ('unidades', 'unidades_extra', 'implementos', 'implementos_info')
    principal = {k: v for k, v in todo.items() if k not in fuera}
    us, ex, partes = todo.get('unidades') or [], todo.get('unidades_extra') or {}, []
    for nivel, (i0, i1) in (todo.get('por_nivel') or {}).items():
        partes.append((nivel, {'unidades': us[i0:i1], 'unidades_extra': {k: v for k, v in ex.items() if i0 <= int(k) < i1}}))
    partes.append(('implementos', {'implementos': todo.get('implementos') or {}, 'implementos_info': todo.get('implementos_info') or {}}))
    return principal, partes

_PARTIR = {'torre_plantas.json': _partir_plantas, 'torre_habilitacion.json': _partir_matriz, 'torre_inventario.json': _partir_inventario}

def _quitar_partes(nombre):
    base = nombre[:-len('.json')]
    for f in (R / 'web/data').glob(base + '_*.json'):
        f.unlink()

def _kb(obj):
    return len(json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) / 1024

def _escribir_web_partible(nombre, obj):
    """Escribe obj en un solo archivo si cabe en su límite; si no, lo parte (_PARTIR) en archivos que caben cada uno."""
    _quitar_partes(nombre)
    lim = LIMITES_KB.get(nombre)
    if lim is None or _kb(obj) <= lim:
        _escribir_web(nombre, obj)
        return
    principal, partes = _PARTIR[nombre](obj, lim)
    base = nombre[:-len('.json')]
    archivos = [f'{base}_{suf}.json' for suf, _ in partes]
    principal['partes'] = {'archivos': archivos, 'nota': f'Partido por tamaño: en un solo archivo pasaría de {lim} KB. Cada parte trae '
                                                          'trozos de listas (se concatenan en este orden) y de diccionarios (se suman).'}
    print(f'{nombre}: {_kb(obj):.0f} KB en un solo archivo pasa el máximo de {lim} KB; se parte en {len(archivos)} archivos más el principal')
    _escribir_web(nombre, principal)
    for (suf, parte), arch in zip(partes, archivos):
        ruta = R / 'web/data' / arch
        ruta.write_text(json.dumps(parte, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        kb = ruta.stat().st_size / 1024
        print(f'  {arch} {kb:.0f} KB (máximo {lim} KB)')
        if kb > lim:
            _aviso(f'{arch} pesa {kb:.0f} KB y el máximo del contrato es {lim} KB')

# ------------------------------------------------------------------------------------------------ inventario (10.2 y 16)
_RE_COMP = __import__('re').compile(r'^(U-.+-\d{3})-c\d+$')
_PISO_WEB = {'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4, 'BT': 'BT', 'CUB': 'CUB'}   # EXT y fuera de la torre: piso null (ver por_nivel)
_ORDEN_NIVELES = ('EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB', 'fuera_de_la_torre')
_CAMPOS_LINEA = ('justificacion_recomendado', 'nota_exigencias', 'adquisicion', 'modelo_de_compra', 'en_presupuesto', 'nota_precio',
                 'tipo_precio_referencia', 'tecnologia_controlada', 'es_dispositivo_medico', 'capa', 'variante', 'cita_presupuesto',
                 'sin_unidades', 'proyecto', 'naturaleza', 'depende_de', 'componentes_texto', 'riesgo_doble_conteo_con_obra')

# mantenimiento preventivo de cada línea: el texto depende de la capa (y del comodato en el laboratorio); va una vez en
# «mantenimiento_preventivo» y la línea solo lo trae si es distinto
_PREVENTIVO = {'fabricante': 'según el manual del fabricante, con hoja de vida (Res. 3100, num. 11.1.3)',
               'edificacion': 'mantenimiento de la edificación',
               'comodato': 'a cargo del proveedor del comodato, según el manual del fabricante, con hoja de vida'}
def _preventivo_por_defecto(l):
    if l.get('capa') in ('infraestructura', 'contexto'):
        return _PREVENTIVO['edificacion']
    if l.get('adquisicion') == 'comodato':
        return _PREVENTIVO['comodato']
    return _PREVENTIVO['fabricante']

def _linea_web(l, dot, lab):
    cr, mt, rg = l.get('clase_riesgo') or {}, l.get('mantenimiento') or {}, l.get('registro_invima') or {}
    w = {'id': l['id'], 'nombre': l.get('nombre'), 'servicio': l.get('servicio'), 'tipo': l.get('tipo'), 'cantidad': l.get('cantidad'),
         'modelo3d': l.get('modelo3d'), 'especificacion': l.get('especificacion'),
         'clase': {'vigente': cr.get('vigente'), 'estado': cr.get('estado'), 'revision': l.get('clase_riesgo_revision'),
                   **({'regla': cr['regla']} if cr.get('regla') else {})},
         'registro': {k: rg.get(k) for k in ('requerido', 'via', 'usado_permitido', 'nota') if k in rg},
         'exigencias': [{'id': e.get('id'), 'exigible': e.get('exigible')} for e in l.get('exigencias') or []],
         'prioridad': l.get('prioridad'), 'prioridad_revisada': l.get('prioridad_revisada'), 'norma_base': l.get('norma_base'),
         'mantenimiento': {k: mt.get(k) for k in ('anual_pct', 'vida_util_anios', 'personal_inscrito_invima', 'calibracion')},
         'componentes': l.get('componentes') or [], 'plantilla': l.get('plantilla_contenido'),
         **_precio_linea(l, dot, lab)}
    for k in _CAMPOS_LINEA:
        if l.get(k) is not None:
            w[k] = l[k]
    if mt.get('preventivo') and mt['preventivo'] != _preventivo_por_defecto(l):
        w['mantenimiento']['preventivo'] = mt['preventivo']
    if l.get('dim_m'):
        w['dim'] = l['dim_m']                           # medida propia de la línea (manda sobre la del catálogo)
    for k in ('parte_de_linea', 'dentro_de_linea'):     # {linea, nombre, item?}: la línea madre que ya tiene el precio
        if l.get(k):
            w[k] = {kk: vv for kk, vv in l[k].items() if vv is not None}
    return _sin_internos(w)

def _extra_unidad(u, plantilla_linea):
    """Lo que la fila de 13 columnas no lleva: subrecinto, medida y variante propias, paneles, ubicación de zona, compartimiento,
    contenido propio y, en las unidades componente de un kit, sus campos propios (nombre, modelo 3D, clase, registro)."""
    e = {}
    if u.get('subrecinto'):
        e['sub'] = u['subrecinto']
    if u.get('variante'):
        e['var'] = u['variante']
    if u.get('dim_m'):
        e['dim'] = u['dim_m']
    if u.get('compartimiento'):
        e['comp'] = u['compartimiento']
    if u.get('ubicacion'):
        e['ubic'] = u['ubicacion']
    if u.get('propuesta_obra'):
        e['obra'] = u['propuesta_obra']
    p = u.get('paneles')
    if p:
        e['fv'] = {k: p[k] for k in ('grupo', 'fila', 'modulos', 'kwp', 'tipo_dato') if p.get(k) is not None}
    pc = (u.get('contenido') or {}).get('plantilla')
    if pc and pc != plantilla_linea:
        e['plantilla'] = pc
    if u.get('componente_de'):
        cr, rg, mt = u.get('clase_riesgo') or {}, u.get('registro_invima') or {}, u.get('mantenimiento') or {}
        e.update({'n': u.get('nombre'), 'm3d': u.get('modelo3d'),
                  'clase': {k: cr.get(k) for k in ('vigente', 'estado', 'regla') if cr.get(k) is not None},
                  'registro': {k: rg.get(k) for k in ('requerido', 'via', 'usado_permitido', 'nota') if k in rg},
                  'mant': {k: mt.get(k) for k in ('anual_pct', 'calibracion', 'personal_inscrito_invima') if k in mt}})
    return e

def _recinto_por_posicion(u, pl_niveles):
    """Recinto de referencia de una unidad de zona sin recinto (pérgola, marquesina): el de su nivel que contiene su centro en
    planta, en la cota de piso más alta que no quede por encima de la unidad."""
    nv = pl_niveles.get(u.get('nivel'))
    pos = u.get('posicion')
    if not nv or not pos:
        return None
    cands = [r for r in nv.get('recintos', []) if r.get('poligono') and _dentro(pos, r['poligono']) and (r.get('z_piso_m') or 0) <= pos[2] + 1e-6]
    cands.sort(key=lambda r: -(r.get('z_piso_m') or 0))
    return cands[0]['id'] if cands else None

def _item_implemento(it):
    alm = it.get('almacenamiento') or {}
    donde = alm.get('donde') or {}
    w = {'n': it.get('nombre'), 'c': it.get('cantidad'), 'comp': it.get('compartimiento'), 'tipo': it.get('tipo'),
         'verif': it.get('verificacion'), 'clase': it.get('clase_riesgo'), 'reg': (it.get('registro_invima') or {}).get('requerido'),
         'fuente': it.get('fuente'), 'pres': it.get('presentacion'), 'm3d': it.get('modelo3d'), 'pruebas': it.get('pruebas') or None,
         'pm': it.get('pruebas_mes'), 'metodo': it.get('metodo'), 'regimen': it.get('regimen'), 'td': it.get('tipo_dato'),
         'nota_clase': it.get('nota_clase'),
         'alm': ({k: v for k, v in (('cond', alm.get('condicion')), ('donde', donde.get('linea')), ('donde_n', donde.get('nombre'))) if v is not None}
                 if alm else None)}
    return {k: v for k, v in w.items() if v is not None}

def torre_inventario_web(inv, dot, lab, cat, imp, hab, pl=None):
    """Forma web compacta del inventario (10.2), con lo que pide el recorrido de toda la torre (16): capa de cada línea,
    infraestructura y contexto sin precio de dotación, unidades componente, paneles por fila, subrecintos y unidades de zona."""
    # las líneas de servicio sin unidades físicas (dosimetría anual…) van aparte: la forma web cuenta en «lineas» solo lo que
    # tiene unidades en el recorrido (validar_inventario --web exige unidades k = 1..cantidad para cada línea)
    lineas, idx_linea, sin_unidades = [], {}, []
    for l in inv.get('lineas', []):
        if l.get('tipo') == 'servicio' or l.get('sin_unidades'):
            sin_unidades.append(_linea_web(l, dot, lab))
            continue
        idx_linea[l['id']] = len(lineas)
        lineas.append(_linea_web(l, dot, lab))
    modelos = (cat or {}).get('modelos', {})
    pl_niveles = {nv.get('id'): nv for nv in (pl or {}).get('niveles', [])}
    # unidades ordenadas por nivel (orden estable dentro de cada uno): así cada nivel es un tramo seguido de «unidades»
    # (por_nivel da [desde, hasta)) y el archivo se puede partir por nivel sin cambiar los índices
    rango_nv = {n_: i for i, n_ in enumerate(_ORDEN_NIVELES)}
    us = sorted(inv.get('unidades', []), key=lambda u: rango_nv.get(u.get('nivel') or 'fuera_de_la_torre', len(rango_nv)))
    idx_u = {u['id']: i for i, u in enumerate(us)}
    filas, extra, por_nivel, por_posicion = [], {}, {}, []
    for i, u in enumerate(us):
        l = lineas[idx_linea[u['linea']]]
        x, y, z = (list(u.get('posicion') or []) + [0.0, 0.0, 0.0])[:3]
        m3d = u.get('modelo3d') or l.get('modelo3d')
        montaje = u.get('montaje') or (modelos.get(m3d) or {}).get('montaje') or 'piso'   # la lavandería (fuera de la torre) no trae montaje
        recinto, e = u.get('recinto'), _extra_unidad(u, l.get('plantilla'))
        if recinto is None and u.get('estado') not in ('fuera_de_la_torre', 'cubierta') and u.get('posicion'):
            recinto = _recinto_por_posicion(u, pl_niveles)
            if recinto:
                e['recinto_por_posicion'] = True
                por_posicion.append(u['id'])
        m_ = _RE_COMP.match(u['id'])
        filas.append([u['id'], idx_linea[u['linea']], _PISO_WEB.get(u.get('nivel')), recinto, round(x, 3), round(y, 3), round(z, 3),
                      round(u.get('rotacion_z') or 0.0, 4), idx_u.get(u.get('apoyo'), -1), idx_u.get(u.get('dentro_de'), -1),
                      idx_u.get(m_.group(1), -1) if m_ else -1, montaje, u.get('estado')])
        if e:
            extra[str(i)] = e
        nv_ = u.get('nivel') or 'fuera_de_la_torre'
        por_nivel[nv_] = [por_nivel.get(nv_, [i])[0], i + 1]
    if por_posicion:
        print(f'  torre_inventario.json: {len(por_posicion)} unidades de zona sin recinto llevan el recinto que contiene su posición (recinto_por_posicion)')
    # catálogo: los modelos de las líneas, de las unidades componente y de los implementos que se dibujan (reactivos, gradillas)
    usados = {l['modelo3d'] for l in lineas if l.get('modelo3d')} | {e['m3d'] for e in extra.values() if e.get('m3d')}
    for pl_ in ((imp or {}).get('plantillas') or {}).values():
        usados |= {it['modelo3d'] for it in pl_.get('items', []) if it.get('modelo3d')}
    falta = sorted(m_ for m_ in usados if m_ not in modelos)
    if falta:
        raise ValueError(f'modelos 3D sin entrada en catalogo_equipos.json: {falta}')
    catalogo = {}
    for m_ in sorted(usados):
        c = modelos[m_]
        catalogo[m_] = {'f': c.get('familia'), 'dim': c.get('dim_m'), 'b': c.get('b_m', min(c['dim_m'][0], c['dim_m'][1]) / 2), 'mont': c.get('montaje'), 'anc': c.get('anclaje'),
                        'masa': c.get('masa_kg'), 'hcg': c.get('h_cg_m'), 'mu': c.get('mu'), 'cont': bool(c.get('contenedor')), 'comp': c.get('compartimientos', [])}
    plantillas = (imp or {}).get('plantillas') or {}
    implementos = {nom_: [_item_implemento(it) for it in p_.get('items', [])] for nom_, p_ in plantillas.items()}
    implementos_info = {nom_: {k: v for k, v in (('descripcion', p_.get('descripcion')), ('norma', p_.get('norma')), ('definicion', p_.get('definicion'))) if v}
                        for nom_, p_ in plantillas.items()}
    # por recinto, el estado de la matriz y sus exigencias exigibles (las por confirmar van solo en el conteo, 4.8)
    exigible = {e.get('id'): e.get('exigible') for sv in (hab or {}).get('servicios', []) for e in sv.get('exigencias') or [] if isinstance(e, dict)}
    recintos = {rid: {'estado': r.get('estado'), 'exig': [x for x in r.get('exigencias', []) if exigible.get(x, 'si') == 'si'], 'por_confirmar': r.get('por_confirmar', 0)}
                for rid, r in ((hab or {}).get('por_recinto') or {}).items()}
    # totales por servicio, sumados aquí con los precios de la dotación (una sola fuente de precio), con la misma regla del
    # inventario: unidades base (sin componentes) de las listas de equipos y mobiliario de cada servicio
    l_datos = {l['id']: l for l in inv.get('lineas', [])}
    por_srv = {}
    for u, f in zip(us, filas):
        lr = l_datos[u['linea']]
        lista = (lr.get('ref') or {}).get('lista')
        if u.get('componente_de') or lr.get('origen') != 'dotacion' or lista not in ('equipos', 'mobiliario'):
            continue
        t = por_srv.setdefault(lr['servicio'], {'unidades': 0, 'equipos_cop_2026': 0, 'mobiliario_cop_2026': 0})
        t['unidades'] += 1
        t['equipos_cop_2026' if lista == 'equipos' else 'mobiliario_cop_2026'] += lineas[f[1]].get('precio') or 0
    for s_ in dot.get('servicios', []):
        t = por_srv.setdefault(s_.get('id'), {'unidades': 0, 'equipos_cop_2026': 0, 'mobiliario_cop_2026': 0})
        td = s_.get('totales') or {}
        t['coincide_con_dotacion'] = t['equipos_cop_2026'] == td.get('equipos_cop_2026') and t['mobiliario_cop_2026'] == td.get('mobiliario_cop_2026')
        if not t['coincide_con_dotacion']:
            _aviso(f'torre_inventario.json: las unidades de {s_.get("id")} no suman el total de la dotación')
    tot_inv = inv.get('totales') or {}
    totales = {'por_servicio': por_srv, **{k: tot_inv[k] for k in ('equipamiento_fijo', 'laboratorio_json', 'habilitacion_cop_2026', 'cierre_brechas',
                                                                  'infraestructura', 'unidades') if k in tot_inv}}
    return {'v': 2, 'fecha': inv.get('fecha'), 'moneda_y_base': inv.get('moneda_y_base'), 'norma_vigente': inv.get('norma_vigente'),
            'estado_planta': inv.get('estado_planta'), 'capas': inv.get('capas'), 'campos_al_comprar': inv.get('campos_res3100_decreto4725'),
            'catalogo': catalogo, 'lineas': lineas, 'lineas_sin_unidades': sin_unidades,
            'columnas_unidades': ['id', 'linea_idx', 'piso', 'recinto', 'x', 'y', 'z', 'rot_z', 'apoyo_idx', 'dentro_de_idx', 'componente_de_idx', 'montaje', 'estado'],
            'unidades': filas, 'unidades_extra': extra, 'por_nivel': por_nivel, 'mantenimiento_preventivo': _PREVENTIVO,
            'implementos': implementos, 'implementos_info': implementos_info, 'recintos': recintos,
            'fuera_de_la_torre': [{k: v for k, v in f.items() if k in ('linea', 'nombre', 'unidad', 'ubicacion')} for f in inv.get('fuera_de_la_torre') or []],
            'totales': _sin_internos(totales),
            'convenciones': {
                'piso': '1 a 4, «BT» (bloque técnico) o «CUB» (cubierta y terraza del piso 3); null en los exteriores y fuera de la torre. Las unidades van ordenadas por nivel y por_nivel da el tramo [desde, hasta) de cada uno (EXT, P1-P4, BT, CUB, fuera_de_la_torre).',
                'mantenimiento': 'preventivo: si la línea no lo trae, es mantenimiento_preventivo.edificacion en la infraestructura y el contexto, .comodato en los equipos de laboratorio en comodato y .fabricante en el resto.',
                'z': 'Altura sobre el piso terminado del nivel (la terraza del piso 3 queda a -4,2 m de la cubierta).',
                'unidades_extra': 'Por índice de unidad: sub (subrecinto: baño con tabique y puerta), dim (medida propia [ancho, fondo, alto] m, manda sobre la de la línea y la del catálogo), var (variante), comp (compartimiento del contenedor), fv (fila de paneles solares), ubic (ubicación de zona), recinto_por_posicion (unidad de zona sin recinto en los datos: el recinto es el que contiene su posición), obra (ajuste de obra propuesto), plantilla (contenido propio) y, en los componentes de un kit, n, m3d, clase, registro y mant propios.',
                'lineas': 'lineas_sin_unidades: servicios contratados (dosimetría…) con la misma forma, sin unidades en el recorrido. capa: dotacion, fijo, laboratorio, cierre_brechas, infraestructura o contexto. La infraestructura y el contexto no tienen precio de dotación: cita_presupuesto da el ítem de obra y parte_de_linea la línea de equipamiento fijo que ya lo incluye. dim es la medida propia de la línea.',
                'implementos': 'n nombre, c cantidad, comp compartimiento, tipo, verif verificación, clase, reg registro INVIMA requerido, pres presentación, alm almacenamiento {cond, donde (línea de la nevera o estante), donde_n}, m3d modelo 3D, pruebas, pm pruebas al mes, metodo, regimen, td tipo de dato.'}}

# ------------------------------------------------------------------------------------------------ plantas (3.3 y 16)
def torre_plantas_web(pl):
    """Forma compacta de las plantas (3.3) con todo lo que pide el recorrido de toda la torre (16): niveles EXT, P1-P4, BT y
    CUB; recintos con su polígono libre y sus subrecintos (baños con tabique y puerta); muros con z_base_m; puertas con lleva_a
    y espejo_de; ventanas; escaleras con sus partes; pasos entre niveles; obstáculos con z_piso_m; rampa; paneles por fila.
    Las citas repetidas van una vez en la tabla «citas» y cada objeto lleva su índice en «cita»; sin «fuentes»; coordenadas
    con 2 decimales. El polígono libre se publica (el 3.3 lo omitía): sin él, los baños de los subrecintos no se pisan."""
    citas = list(pl.get('citas') or [])
    pos = {t: i for i, t in enumerate(citas)}
    def cita(t):
        if t is None:
            return None
        if t not in pos:
            pos[t] = len(citas); citas.append(t)
        return pos[t]
    def con_cita(o, campo):
        if isinstance(o, dict) and o.get(campo):
            o = dict(o); o['cita'] = cita(o.pop(campo))
        return o
    niveles = []
    for nv in pl.get('niveles', []):
        nv = dict(nv)
        rs = []
        for r in nv.get('recintos', []):
            r = dict(r)
            if isinstance(r.get('minimo_1633'), dict):
                r['minimo_1633'] = {**r['minimo_1633'], 'cita': cita(r['minimo_1633'].get('cita'))}
            if isinstance(r.get('climatizacion'), dict):
                r['climatizacion'] = con_cita(r['climatizacion'], 'fuente')
            rs.append(r)
        nv['recintos'] = rs
        nv['puertas'] = [con_cita(pt, 'cita_ancho') for pt in nv.get('puertas', [])]
        if nv.get('paneles_solares'):
            nv['paneles_solares'] = [con_cita(p_, 'fuente') for p_ in nv['paneles_solares']]
        niveles.append(nv)
    out = {k: v for k, v in pl.items() if k not in ('niveles', 'citas', 'fuentes')}
    out['tipos_muro'] = {k: con_cita(v, 'fuente') for k, v in (pl.get('tipos_muro') or {}).items()}
    out['niveles'] = niveles
    out['citas'] = citas
    return _redondear_planta(_sin_internos(out))

# ------------------------------------------------------------------------------------------------ matriz de cumplimiento (4.8)
_INTERNOS_MATRIZ = {'origen_regla'}
def torre_habilitacion_web(hab, inv, dot):
    """Matriz de cumplimiento en dotación e infraestructura: el mismo esquema, sin campos internos. Los precios del cierre de
    brechas de los faltantes se vuelven a leer de dotacion.json (una sola fuente de precio)."""
    por_id = {l['id']: l for l in (inv or {}).get('lineas', [])}
    def limpiar(o):
        if isinstance(o, dict):
            return {k: limpiar(v) for k, v in o.items() if k not in _INTERNOS_MATRIZ}
        if isinstance(o, list):
            return [limpiar(x) for x in o]
        return o
    out = limpiar(_sin_internos(hab))
    for sv in out.get('servicios') or []:
        for it in (sv.get('faltantes') or {}).get('cierre_de_brechas') or []:
            l = por_id.get(it.get('linea'))
            if l is None:
                continue
            p_ = _precio_dotacion(l, dot)
            if 'precio_unitario_cop_2026' in it and p_ != it.get('precio_unitario_cop_2026'):
                _aviso(f'torre_habilitacion.json: el precio de {it.get("linea")} en la matriz no es el de la dotación; se publica el de la dotación')
            it['precio_unitario_cop_2026'] = p_
            it['total_cop_2026'] = p_ * (it.get('cantidad') or 0) if p_ is not None else None
    return out

# ------------------------------------------------------------------------------------------------ contraste (9.1)
def torre_contraste_web(c, dot, lab, inv):
    """Contraste con el proyecto tipo (9.1): sin búsquedas ni acceso a fuentes. El costo de la dotación de cada ambiente se
    calcula aquí con los precios de dotacion.json (no se copia a mano): Σ precio × cantidad de la fila (lineas_torre[].cantidad,
    la parte de la línea que va a ese ambiente; si no viene, la de la línea); en las filas de servicios completos
    (servicios_torre), el total de esos servicios en dotacion.json menos las líneas que ya cuentan otras filas (excluye_lineas).
    Es el mismo cálculo de validar_contraste.py (K6)."""
    out = {k: v for k, v in c.items() if k not in ('busquedas', 'acceso_a_fuentes')}
    if inv is None:
        # sin inventario al día no hay de dónde sacar las líneas de cada fila: se publica sin costos (un solo aviso)
        _aviso('torre_contraste.json: el inventario no está al día; la dotación por ambiente se publica sin costo')
        out['dotacion_por_ambiente'] = [{**{k: v for k, v in f.items() if not k.startswith('costo_torre')}, 'costo_torre_cop_2026': None}
                                        for f in out.get('dotacion_por_ambiente') or []]
        return _sin_internos(out)
    por_id = {l['id']: l for l in (inv or {}).get('lineas', [])}
    srv_dot = {s_.get('id'): s_ for s_ in dot.get('servicios', [])}
    filas, sin_base = [], 0
    for f in out.get('dotacion_por_ambiente') or []:
        f = {k: v for k, v in f.items() if not k.startswith('costo_torre')}
        lt, st = f.get('lineas_torre'), f.get('servicios_torre')
        if lt is None and st is None:
            sin_base += 1
            filas.append(f)
            continue
        total, sin_precio, faltan = 0, 0, []
        for e in lt or []:
            l = por_id.get(e.get('linea'))
            if l is None:
                faltan.append(e.get('linea')); continue
            p_ = _precio_dotacion(l, dot)
            if p_ is None:
                sin_precio += 1
            else:
                total += p_ * (e.get('cantidad') if e.get('cantidad') is not None else (l.get('cantidad') or 0))
        for s_ in st or []:
            if s_ not in srv_dot:
                faltan.append(s_); continue
            total += (srv_dot[s_].get('totales') or {}).get('total_cop_2026') or 0
        for e in f.get('excluye_lineas') or []:
            l = por_id.get(e.get('linea'))
            if l is None:
                faltan.append(e.get('linea')); continue
            p_ = _precio_dotacion(l, dot)
            if p_ is not None:
                total -= p_ * (e.get('cantidad') or 0)
        if faltan:
            _aviso(f'torre_contraste.json: {f.get("id")} cita {", ".join(map(str, faltan))}, que no están en el inventario ni en la dotación; se publica sin costo')
            f['costo_torre_cop_2026'] = None
        else:
            f['costo_torre_cop_2026'] = total
            if sin_precio:
                f['costo_torre_lineas_sin_precio'] = sin_precio
        filas.append(f)
    if 'dotacion_por_ambiente' in out:
        out['dotacion_por_ambiente'] = filas
        out['costo_torre_tipo'] = ('cálculo propio: precios de la dotación × cantidad de cada fila; en las filas de servicios completos, '
                                   'el total de esos servicios menos las líneas que ya cuentan otras filas')
    if sin_base:
        _aviso(f'torre_contraste.json: {sin_base} filas de dotacion_por_ambiente sin lineas_torre ni servicios_torre; se publican sin costo (el precio no se copia a mano)')
    return _sin_internos(out)

def _validar_inventario_web(web, cat):
    """Revisa la forma web completa del inventario (con todas sus partes) con la validación de B (validar_web de
    scripts/torre/validar_inventario.py, la misma de «--web»): el archivo principal solo no pasa cuando está partido.
    Si encuentra errores, avisa (no detiene la construcción)."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location('validar_inventario', R / 'scripts/torre/validar_inventario.py')
        vi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vi)
        inf = vi.C.Informe('validar_inventario', {**vi.REGLAS_WEB, **{k: vi.REGLAS[k] for k in ('I1', 'I8', 'I9', 'I10', 'I11', 'I12')}}, modo='web')
        vi.validar_web(inf, web, cat or {})
    except Exception as e:                                  # el validador es de otro equipo: si cambia, se avisa y se sigue
        _aviso(f'torre_inventario.json: no se pudo correr validar_inventario sobre la forma web ({type(e).__name__}: {e})')
        return
    d = inf.como_dict()
    print(f'  validar_inventario --web (forma completa, con las partes juntas): {d["errores_duros"]} errores duros, {d["avisos"]} avisos')
    if d['errores_duros']:
        malos = [f'{r["regla"]}: {m}' for r in d['reglas'] for m in r['errores']][:5]
        _aviso(f'torre_inventario.json no pasa validar_inventario --web ({d["errores_duros"]} errores; p. ej. ' + ' · '.join(malos) + ')')

# ------------------------------------------------------------------------------------------------ estructura sísmica (7.2 y 17)
# El simulador (web/js/sismo/modelo.js y motor.js), la vista sísmica y el modo BIM leen de la estructura los bloques (niveles,
# pórticos con nodos y elementos, resortes de mampostería), las secciones con sus propiedades de rótula, los materiales, el
# diseño, el amortiguamiento y el sistema. Lo descriptivo del prediseño queda en data/sismo y no viaja a la web: el despiece,
# la cimentación y las cantidades (el modo BIM los lee de su propio modelo), las tablas largas y los textos de método del
# prediseño, y en cada sección el texto del cálculo, el refuerzo en palabras, el diagrama momento-curvatura, la interacción
# P-M y las resistencias de diseño (φMn, φVn, Mpr) y de gravedad de los chequeos del prediseño, que ningún módulo web usa (el
# motor usa las propiedades esperadas y nominales: My, Mn, Vn, θp). Así el archivo baja de ≈ 1,2 MB a menos de los 250 KB
# del 10.1 sin cambiar un solo número de los que usa el motor: scripts/qa/torre_qa.mjs --solo datos corre el mismo cálculo
# con los dos archivos y lo compara bit a bit.
_EST_FUERA = ('insumos_sha1', 'generado_por', 'refuerzo', 'cimentacion', 'cantidades')
_PREDISENO_FUERA = ('columna_fuerte_viga_debil', 'cortante_por_capacidad', 'cuantias', 'chequeos', 'coordinacion_bim', 'eleccion_muros',
                    'historial_de_ajustes', 'metodo_secciones')
_SECCION_FUERA = ('calculo', 'refuerzo', 'momento_curvatura', 'momento_curvatura_neg', 'interaccion_PM', 'Mpr_kNm', 'Mpr_pos_kNm', 'Mpr_neg_kNm',
                  'phiMn_kNm', 'phiMn_pos_kNm', 'phiMn_neg_kNm', 'phiVn_kN', 'P_gravedad_kN', 'b_ala')
_RESORTE_FUERA = ('calculo',)

def sismo_estructura_web(est):
    web = {k: v for k, v in est.items() if k not in _EST_FUERA}
    if isinstance(web.get('prediseno'), dict):
        web['prediseno'] = {k: v for k, v in web['prediseno'].items() if k not in _PREDISENO_FUERA}
    if isinstance(web.get('secciones'), dict):
        web['secciones'] = {k: {kk: vv for kk, vv in s.items() if kk not in _SECCION_FUERA} if isinstance(s, dict) else s
                            for k, s in web['secciones'].items()}
    web['bloques'] = [{**b, 'resortes': [{k: v for k, v in r.items() if k not in _RESORTE_FUERA} for r in b.get('resortes') or []]}
                      if isinstance(b, dict) and 'resortes' in b else b for b in web.get('bloques') or []]
    return web

def _exportar_torre_y_sismo():
    tdir = D / 'proyectos/torre_hospital'
    dot = json.loads((tdir / 'dotacion.json').read_text(encoding='utf-8')) if (tdir / 'dotacion.json').exists() else {}
    lab = json.loads((tdir / 'laboratorio.json').read_text(encoding='utf-8')) if (tdir / 'laboratorio.json').exists() else {}
    opt_t = lambda n_: json.loads((tdir / n_).read_text(encoding='utf-8')) if (tdir / n_).exists() else None
    # plantas de toda la torre (B): EXT, P1-P4, BT y CUB
    pl = _cargar_generado('torre_plantas.json', D / 'edificios/torre_hospital_plantas.json')
    if pl is not None:
        _escribir_web_partible('torre_plantas.json', torre_plantas_web(pl))
    else:
        _quitar_partes('torre_plantas.json')
    inv = _web_torre_inventario_datos()
    # matriz de cumplimiento en dotación e infraestructura (B)
    hab = _cargar_generado('torre_habilitacion.json', tdir / 'habilitacion.json')
    if hab is not None:
        _escribir_web_partible('torre_habilitacion.json', torre_habilitacion_web(hab, inv, dot))
    else:
        _quitar_partes('torre_habilitacion.json')
    # inventario (B): con el catálogo 3D, los implementos y la planta (recinto de referencia de las unidades de zona)
    if inv is not None:
        try:
            cat = opt_t('catalogo_equipos.json')
            web_inv = torre_inventario_web(inv, dot, lab, cat, opt_t('implementos.json'), hab, pl)
            _validar_inventario_web(web_inv, cat)
            _escribir_web_partible('torre_inventario.json', web_inv)
        except ValueError as e:
            _no_exportar('torre_inventario.json', str(e))
            _quitar_partes('torre_inventario.json')
    else:
        _quitar_partes('torre_inventario.json')
    # contraste con el proyecto tipo (E); no es un generado: se exporta si existe
    c = opt_t('proyecto_tipo_contraste.json')
    if c is None:
        _ausente('torre_contraste.json', tdir / 'proyecto_tipo_contraste.json')
    else:
        _escribir_web('torre_contraste.json', torre_contraste_web(c, dot, lab, inv))
    # simulador sísmico (A): estructura (generada) y amenaza (a mano)
    est = _cargar_generado('sismo_torre_estructura.json', D / 'sismo/torre_hospital_estructura.json')
    if est is not None:
        _escribir_web('sismo_torre_estructura.json', sismo_estructura_web(est))
    am = D / 'sismo/amenaza.json'
    if am.exists():
        _escribir_web('sismo_amenaza.json', json.loads(am.read_text(encoding='utf-8')))
    else:
        _ausente('sismo_amenaza.json', am)
    # generados que no van a la web pero de los que salen cifras de la vista o de los documentos (escenarios del docs/14,
    # exigencias de la matriz): solo se revisa que estén al día, con el mismo aviso
    for ruta in (D / 'sismo/escenarios.json', tdir / 'exigencias_3100.json'):
        if ruta.exists():
            viejos = _insumos_viejos(ruta)
            if viejos:
                _aviso(f'{ruta.relative_to(R)} está desactualizado frente a ' + ', '.join(viejos) + '; hay que regenerarlo')

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
    # de los APU, la vista muestra el resumen y el detalle de cada análisis (materiales con su precio, equipo, mano de obra y
    # AIU): la lista de insumos, la de equipos base y el método no se dibujan y quedan en data/ (así torre.json cabe en 620 KB)
    if 'apu' in TORRE:
        TORRE['apu'] = {k: v for k, v in TORRE['apu'].items() if k not in ('insumos', 'equipos_base', 'metodo')}
    (R / 'web/data').mkdir(parents=True, exist_ok=True)
    _escribir_web('torre.json', TORRE)
    _exportar_torre_y_sismo()
    # --- bim: inicio (equipo F, especificación 17.4-17.5; solo este bloque es de F) ---
    # modelo BIM de la torre para el modo «Modelo BIM»: web/data/torre_bim*.json desde data/bim (scripts/bim/web_bim.py),
    # solo si el modelo, las interferencias y la validación del IFC están al día con sus insumos (insumos_sha1)
    def _exportar_bim():
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('web_bim', R / 'scripts/bim/web_bim.py')
        web_bim = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(web_bim)
        LIMITES_KB.update({'torre_bim.json': 150, 'torre_bim_interferencias.json': 900})
        for _niv in ('CIM-PIL', 'CIM', 'BT', 'EXT', 'P1', 'P2', 'P3', 'P4', 'CUB'):
            LIMITES_KB[f'torre_bim_{_niv}.json'] = 1100
            LIMITES_KB[f'torre_bim_ref_{_niv}.json'] = 900
        viejos = {p_.name for p_ in (R / 'web/data').glob('torre_bim*.json')}
        escritos = web_bim.exportar(_escribir_web, _aviso, _cargar_generado)
        for n_ in sorted(viejos - set(escritos)):                 # lo que ya no sale (modelo desactualizado o nivel vacío)
            (R / 'web/data' / n_).unlink(missing_ok=True)         # (el índice ya lo borró _no_exportar si estaba desactualizado)
    try:
        _exportar_bim()
    except Exception as _e:                                       # el modelo BIM nunca detiene el resto de la exportación
        _aviso(f'torre_bim*.json no se exportó: {type(_e).__name__}: {_e}')
    # --- bim: fin ---

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
