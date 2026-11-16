"""Genera web/data/propuesta.json para la presentación de la propuesta integral 2028–2031 (web/propuesta.html) y el
guion que usa el asistente del panel para presentarla (admin/app/agente/propuesta_guion.json).

Entradas (data/propuesta/):
  general.json        portada, catálogo de fuentes de financiación, hoja de ruta, pedidos y el orden de los módulos
  general.json        también la sección `tecnica`: la portada, las inmersiones en los modelos del atlas, sus pasos y los
                      títulos de la presentación técnica (web/propuesta.html?modo=tecnica, la que muestra el asistente)
  simulaciones.json   los controles de adentro de cada inmersión que el asistente acciona en el atlas (`simular`): se
                      revisan y se copian a cada inmersión de `tecnica.inmersiones` como `controles`; con la clave
                      «maqueta», los de la maqueta 3D (la hora, el día, las luces, el partido), a
                      `tecnica.simulaciones_maqueta`
  modulos/<id>.json   un archivo por módulo: diagnóstico, componentes con costo, financiación, gestión, metas y pasos
  geo.json            sitios y trazados de cada propuesta en metros del modelo (x al oriente, y al norte)
  territorio.json     río Magdalena, vías y puente (lo genera scripts/geo/territorio_propuesta.py)
A cada componente le agrega `enfoque`: dónde lo encuadra la cámara en la maqueta (el paso que lo desarrolla, sus sitios,
sus trazados o la réplica de una sede; ver ENFOQUES), o nada si no tiene un lugar propio.
Revisa el catálogo de piezas de la maqueta (`tecnica.maqueta` de general.json: lo que el asistente muestra, oculta o
aísla) contra las capas y los grupos del código de la presentación y contra los nodos de los modelos de las sedes.
Revisa que las sumas cuadren (componentes y fuentes contra la inversión de cada módulo) y que cada fuente, componente y
proyecto tipo citado exista, y que el Home (web/index.html) siga repitiendo el nombre y el lema de cada área, con su
enlace y su imagen; avisa lo que no cuadra sin detener la construcción.
Uso: python3 scripts/build_propuesta.py   (también lo llama scripts/build_data.py)
     python3 scripts/build_propuesta.py --estricto   (la CI: termina con error si hay avisos)
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data/propuesta'
avisos = []
aviso = lambda m: avisos.append(m)
load = lambda p: json.loads((D / p).read_text(encoding='utf-8'))

if not (D / 'general.json').exists():
    print('propuesta: falta data/propuesta/general.json; no se genera web/data/propuesta.json')
    raise SystemExit(0)

g = load('general.json')
fuentes = {f['id']: f for f in g.get('financiacion', {}).get('fuentes', [])}
modulos = []
for mid in g.get('orden_modulos', []):
    ruta = D / 'modulos' / f'{mid}.json'
    if not ruta.exists():
        aviso(f'falta el módulo {mid} (data/propuesta/modulos/{mid}.json)')
        continue
    m = json.loads(ruta.read_text(encoding='utf-8'))
    m.setdefault('id', mid)
    comps = m.get('componentes', [])
    suma = sum((c.get('costo') or {}).get('central') or 0 for c in comps)
    inv = m.get('inversion') or {}
    if not inv.get('central'):
        inv = m['inversion'] = {'min': sum((c.get('costo') or {}).get('min') or 0 for c in comps), 'central': suma,
                                'max': sum((c.get('costo') or {}).get('max') or 0 for c in comps)}
    elif suma and abs(suma - inv['central']) > 0.01 * inv['central']:
        aviso(f'{mid}: los componentes suman {suma:,.0f} M y la inversión dice {inv["central"]:,.0f} M')
    fin = sum(f.get('monto') or 0 for f in m.get('financiacion', []))
    if fin and abs(fin - inv['central']) > 0.01 * inv['central']:
        aviso(f'{mid}: las fuentes suman {fin:,.0f} M y la inversión es {inv["central"]:,.0f} M')
    for f in m.get('financiacion', []):
        if f.get('fuente') not in fuentes:
            aviso(f'{mid}: la fuente «{f.get("fuente")}» no está en el catálogo de general.json')
    for c in comps:
        for f in c.get('fuentes', []):
            if f not in fuentes:
                aviso(f'{mid}/{c.get("id")}: la fuente «{f}» no está en el catálogo de general.json')
        cc = c.get('costo') or {}
        if cc and not (cc.get('min', 0) <= cc.get('central', 0) <= cc.get('max', cc.get('central', 0))):
            aviso(f'{mid}/{c.get("id")}: el rango de costo no está en orden (mín ≤ central ≤ máx)')
    ids = {c.get('id') for c in comps}
    for p in m.get('pasos', []):
        if p.get('tipo') == 'componente' and p.get('componente') not in ids:
            aviso(f'{mid}: el paso «{p.get("id")}» cita el componente «{p.get("componente")}», que no existe')
    modulos.append(m)

geo = load('geo.json') if (D / 'geo.json').exists() else {}
terr = load('territorio.json') if (D / 'territorio.json').exists() else {}

# Dónde encuadra la cámara cada componente cuando el asistente lo pide (`visual` con `enfoque`, js/propuesta/main.js):
# 1) lo que diga ENFOQUES; 2) el paso que lo desarrolla (`componente` igual, o el de otro «mirador_…» para
#    «mirador_proteccion», como `pasoDeComp` de main.js): se ve el 3D de ese paso; 3) un sitio o un trazado de geo.json con
#    su mismo id: se encuadra con las capas principales del módulo. Sin nada de eso, no tiene lugar propio (una
#    titulación, el capital de trabajo, un acopio en otro corregimiento) y la herramienta no lo enfoca.
ENFOQUES = {
    'agroindustria': {'agua': {'sitios': ['ptar']}, 'predio': {'sitios': ['lote']}},
    'salud': {'ebs': {'paso': 'rural'}, 'ambulancias': {'edificios': ['hospital']}},
    'aguas': {'linea_base': {'paso': 'sistema'}, 'impulsion': {'paso': 'sistema'}, 'scada': {'paso': 'sistema'},
              'sectorizacion': {'paso': 'sectores'}, 'macromedicion': {'paso': 'sectores'},
              'micromedicion': {'paso': 'sectores'}, 'perdidas': {'paso': 'sectores'}},
    'saneamiento': {'plan_maestro': {'paso': 'colectores'}, 'emisario': {'paso': 'ptar'},
                    'compostaje': {'paso': 'residuos'}},
    'tic': {'zonas': {'paso': 'fibra'}},
}
edificios_json = R / 'data/edificios'
for m in modulos:
    g_m = geo.get(m['id']) or {}
    sitios = {x.get('id') for x in g_m.get('sitios', [])}
    trazos = {x.get('id') for x in g_m.get('trazados', [])}
    pasos_m = [x for x in m.get('pasos', []) if x.get('tipo') == 'componente']
    for c in m.get('componentes', []):
        cid = c.get('id')
        e = ENFOQUES.get(m['id'], {}).get(cid)
        if e is None:
            paso = next((x['id'] for x in pasos_m if x.get('componente') == cid), None)
            if paso is None and '_' in cid:
                paso = next((x['id'] for x in pasos_m if str(x.get('componente', '')).startswith(cid.split('_')[0] + '_')), None)
            e = {'paso': paso} if paso else {'sitios': [cid]} if cid in sitios else {'trazados': [cid]} if cid in trazos else None
        if e:
            for k in e.get('sitios', []):
                if k not in sitios:
                    aviso(f'{m["id"]}/{cid}: el enfoque cita el sitio «{k}», que no está en geo.json')
            for k in e.get('trazados', []):
                if k not in trazos:
                    aviso(f'{m["id"]}/{cid}: el enfoque cita el trazado «{k}», que no está en geo.json')
            if e.get('paso') and e['paso'] not in {x.get('id') for x in m.get('pasos', [])}:
                aviso(f'{m["id"]}/{cid}: el enfoque cita el paso «{e["paso"]}», que el módulo no tiene')
            for k in e.get('edificios', []):
                if edificios_json.exists() and not (edificios_json / f'{k}.json').exists():
                    aviso(f'{m["id"]}/{cid}: el enfoque cita la sede «{k}», que no está en data/edificios/')
            c['enfoque'] = e
        else:
            c.pop('enfoque', None)

# La presentación técnica: cada inmersión del catálogo lleva a una vista del atlas con un modo que existe, y cada paso
# nuevo va detrás de un paso del módulo (o de otro paso nuevo) y lleva a una inmersión del catálogo
tecnica = g.get('tecnica', {})
VISTAS_INMERSION = {'torre': {'hoy', 'torre', 'pisos', 'recorrido', 'laboratorio', 'sismo', 'bim'}, 'parque': {'hoy', 'parque'}}
catalogo = {i.get('id'): i for i in tecnica.get('inmersiones', [])}
for i in tecnica.get('inmersiones', []):
    if i.get('modo') not in VISTAS_INMERSION.get(i.get('vista'), set()):
        aviso(f'tecnica: la inmersión «{i.get("id")}» pide la vista «{i.get("vista")}» del atlas con el modo «{i.get("modo")}», que no existe')
for mid, extra in (tecnica.get('pasos') or {}).items():
    m = next((x for x in modulos if x['id'] == mid), None)
    if m is None:
        aviso(f'tecnica: hay pasos para el módulo «{mid}», que no está')
        continue
    ids = {x.get('id') for x in m.get('pasos', [])}
    for e in extra:
        if e.get('inmersion') not in catalogo:
            aviso(f'tecnica/{mid}: el paso «{e.get("id")}» lleva a la inmersión «{e.get("inmersion")}», que no está en el catálogo')
        if e.get('despues_de') not in ids:
            aviso(f'tecnica/{mid}: el paso «{e.get("id")}» va después de «{e.get("despues_de")}», que no está antes')
        if e.get('id') in ids:
            aviso(f'tecnica/{mid}: el paso «{e.get("id")}» repite el id de otro paso')
        ids.add(e.get('id'))
# Las simulaciones (data/propuesta/simulaciones.json, {inmersión: [control…]}): los controles de adentro de cada modelo del
# atlas que el asistente acciona con `simular` (los deslizadores, las opciones y los botones del simulador sísmico, los
# niveles y las capas del recorrido, las herramientas del modelo BIM…; web/js/escenario.js los acciona como la persona).
# Se revisa la forma de cada control (id, nombre, tipo, rangos, opciones), que la inmersión exista y que el atlas sepa
# accionarlo (las claves de ACCIONADORES en escenario.js para la vista y el modo de la inmersión), y se copia a cada
# inmersión de `tecnica.inmersiones` como `controles` (una lista vacía si no tiene). Lo que se acciona se ve en la sala, y
# lo proyectado nunca lleva costos: un control (o una de sus opciones) cuyo id o nombre hable de plata (5D, costo,
# presupuesto, valor, precio…) se avisa, y su ayuda tampoco puede hablar de eso
ID_CONTROL = re.compile(r'[a-z0-9_]{1,40}')
PLATA = r'5d|costos?|presupuestos?|precios?|plata|pesos|millones|cop|apu|financiaci[oó]n|inversi[oó]n'
PLATA_ID = re.compile(rf'(?<![a-z0-9])(?:{PLATA}|valor(?:es)?)(?![a-z0-9])|\$')
PLATA_AYUDA = re.compile(rf'(?<![a-z0-9])(?:{PLATA})(?![a-z0-9])|\$')
def habla_de_plata(t, regla=PLATA_ID):
    """Si el texto (un id, con sus guiones bajos como espacios, o un nombre, sin importar las mayúsculas) nombra plata."""
    return bool(regla.search(str(t or '').lower().replace('_', ' ')))
TIPOS_CONTROL = {'accion', 'numero', 'opcion', 'si_no'}
CAMPOS_CONTROL = {'id', 'nombre', 'tipo', 'min', 'max', 'paso', 'unidad', 'opciones', 'ayuda'}
ESCENARIO_JS = R / 'web/js/escenario.js'
def accionadores_js():
    """{'vista:modo': {ids de control}} de la tabla ACCIONADORES de web/js/escenario.js (una entrada puede ser una
    constante compartida, como la del recorrido y el laboratorio), o None si no se puede leer."""
    if not ESCENARIO_JS.exists():
        return None
    js = ESCENARIO_JS.read_text(encoding='utf-8')
    claves = lambda t: set(re.findall(r'^\s+([a-z0-9_]+): \{ como:', t, re.M))
    tabla = re.search(r'^const ACCIONADORES = \{\n(.*?)^\};', js, re.M | re.S)
    if not tabla:
        return None
    hay = {}
    for m in re.finditer(r"^  '([a-z]+:[a-z0-9_]+)': (?:([A-Z_]+),|\{\n(.*?)^  \},)", tabla.group(1), re.M | re.S):
        if m.group(2):
            c = re.search(rf'^const {m.group(2)} = \{{\n(.*?)^\}};', js, re.M | re.S)
            hay[m.group(1)] = claves(c.group(1)) if c else set()
        else:
            hay[m.group(1)] = claves(m.group(3))
    return hay
es_num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
# La maqueta 3D también tiene sus simulaciones (la clave reservada «maqueta» de simulaciones.json, con la misma forma):
# la hora del día, el día entero en unos segundos, las luminarias y el partido en la cancha, que el asistente acciona con
# `simular` cuando no hay un modelo del atlas a la vista (web/js/propuesta/simulacion.js las acciona). Solo ellas pueden
# decir en qué capítulos valen (`capitulos`; sin la clave, en todos). Se revisan con las mismas reglas, contra la tabla
# ACCIONADORES de simulacion.js, y las horas contra ORDEN_HORAS de ambiente.js; se copian tal cual a
# `tecnica.simulaciones_maqueta`
MAQUETA = 'maqueta'
SIMULACION_JS = R / 'web/js/propuesta/simulacion.js'
AMBIENTE_JS = R / 'web/js/propuesta/ambiente.js'
def accionadores_maqueta():
    """Los ids que sabe accionar la maqueta (las claves de ACCIONADORES en web/js/propuesta/simulacion.js), o None."""
    if not SIMULACION_JS.exists():
        return None
    m = re.search(r'const ACCIONADORES = \{\n(.*?)\n\s*\};', SIMULACION_JS.read_text(encoding='utf-8'), re.S)
    return set(re.findall(r'^\s{4}([a-z0-9_]+): ', m.group(1), re.M)) if m else None
def horas_maqueta():
    """Las horas de la maqueta en su orden (ORDEN_HORAS de web/js/propuesta/ambiente.js), o None."""
    m = re.search(r'export const ORDEN_HORAS = \[([^\]]*)\]', AMBIENTE_JS.read_text(encoding='utf-8')) if AMBIENTE_JS.exists() else None
    return re.findall(r"'([a-z0-9_]+)'", m.group(1)) if m else None
def revisar_controles(donde, lista, accionables, que_falta, extra=frozenset()):
    """Revisa la forma de cada control de `lista` (avisa con `donde`) y que esté en `accionables` (los ids que el código
    sabe accionar; None si no se pudo leer: entonces no se revisa; `que_falta`, el aviso si no está). `extra`: campos
    que esta lista admite además de los de un control. Devuelve cuántos controles con id válido tiene."""
    n = 0
    vistos, nombres = set(), set()
    for c in lista:
        if not isinstance(c, dict) or not isinstance(c.get('id'), str) or not ID_CONTROL.fullmatch(c['id']):
            aviso(f'{donde}: un control sin id válido ([a-z0-9_], hasta 40): {c.get("id") if isinstance(c, dict) else c!r}')
            continue
        cid, tipo = f'{donde}/{c["id"]}', c.get('tipo')
        n += 1
        if c['id'] in vistos:
            aviso(f'{cid}: el id del control está repetido en la inmersión')
        vistos.add(c['id'])
        nombre = str(c.get('nombre') or '').strip()
        if not nombre:
            aviso(f'{cid}: el control no tiene nombre')
        elif nombre.lower() in nombres:
            aviso(f'{cid}: el nombre «{nombre}» se repite en la inmersión (el asistente también los pide por nombre)')
        nombres.add(nombre.lower())
        for k in sorted(set(c) - CAMPOS_CONTROL - set(extra)):
            aviso(f'{cid}: el campo «{k}» no es de la forma de un control')
        if tipo not in TIPOS_CONTROL:
            aviso(f'{cid}: el tipo «{tipo}» no es accion, numero, opcion ni si_no')
        if c.get('ayuda') is not None and (not isinstance(c['ayuda'], str) or not c['ayuda'].strip()):
            aviso(f'{cid}: la ayuda no es un texto')
        if habla_de_plata(c['id']) or habla_de_plata(nombre) or habla_de_plata(c.get('ayuda'), PLATA_AYUDA):
            aviso(f'{cid}: el control habla de plata (5D, costo, presupuesto, valor…), y lo que se proyecta nunca lleva '
                  'costos: quítelo del catálogo')
        if tipo == 'numero':
            mn, mx, paso = c.get('min'), c.get('max'), c.get('paso')
            if not es_num(mn) or not es_num(mx) or mn >= mx:
                aviso(f'{cid}: un número pide min y max, con min < max')
            elif paso is not None and (not es_num(paso) or paso <= 0 or paso > mx - mn):
                aviso(f'{cid}: el paso debe ser positivo y no mayor que el rango')
            if c.get('unidad') is not None and not isinstance(c['unidad'], str):
                aviso(f'{cid}: la unidad no es un texto')
        elif any(k in c for k in ('min', 'max', 'paso', 'unidad')):
            aviso(f'{cid}: min, max, paso y unidad son solo de los controles de tipo numero')
        if tipo == 'opcion':
            ops, vistas_op = c.get('opciones'), set()
            if not isinstance(ops, list) or not ops:
                aviso(f'{cid}: una opción pide su lista de opciones')
                ops = []
            for o in ops:
                if not isinstance(o, dict) or not isinstance(o.get('id'), str) or not ID_CONTROL.fullmatch(o['id']) or o['id'] in vistas_op:
                    aviso(f'{cid}: una opción con id repetido o inválido: {o.get("id") if isinstance(o, dict) else o!r}')
                    continue
                vistas_op.add(o['id'])
                if not str(o.get('nombre') or '').strip():
                    aviso(f'{cid}.{o["id"]}: la opción no tiene nombre')
                if habla_de_plata(o['id']) or habla_de_plata(o.get('nombre')):
                    aviso(f'{cid}.{o["id"]}: la opción habla de plata (5D, costo, presupuesto, valor…), y lo que se '
                          'proyecta nunca lleva costos: quítela del catálogo')
        elif 'opciones' in c:
            aviso(f'{cid}: las opciones son solo de los controles de tipo opcion')
        if accionables is not None and c['id'] not in accionables:
            aviso(f'{cid}: {que_falta}')
    return n
simulaciones = load('simulaciones.json') if (D / 'simulaciones.json').exists() else {}
if not isinstance(simulaciones, dict):
    aviso('simulaciones.json no es un objeto {inmersión: [controles]}')
    simulaciones = {}
atlas_js = accionadores_js()
if atlas_js is None and any(k != MAQUETA for k in simulaciones):
    aviso('no se pudo leer la tabla ACCIONADORES de web/js/escenario.js para revisar las simulaciones')
if MAQUETA in catalogo:
    aviso(f'tecnica: una inmersión no puede llamarse «{MAQUETA}» (es la palabra que cierra el modelo del atlas)')
controles_total = 0
for iid, lista in simulaciones.items():
    if iid == MAQUETA:   # la maqueta 3D: aparte, más abajo
        continue
    donde = f'simulaciones/{iid}'
    inm = catalogo.get(iid)
    if inm is None:
        aviso(f'{donde}: no es una inmersión de tecnica.inmersiones')
    if not isinstance(lista, list):
        aviso(f'{donde}: no es una lista de controles')
        simulaciones[iid] = []
        continue
    clave_atlas = f'{inm.get("vista")}:{inm.get("modo")}' if inm else None
    if inm and atlas_js is not None and lista and clave_atlas not in atlas_js:
        aviso(f'{donde}: el atlas no tiene con qué accionar controles en «{clave_atlas}» (ACCIONADORES de web/js/escenario.js)')
    accionables = atlas_js[clave_atlas] if inm and atlas_js is not None and clave_atlas in atlas_js else None
    controles_total += revisar_controles(donde, lista, accionables, f'el atlas no sabe accionar este control en «{clave_atlas}» '
                                         '(ACCIONADORES de web/js/escenario.js)')
capitulos_tecnica = {'portada', 'ruta'} | {m['id'] for m in modulos}
sim_maqueta = simulaciones.get(MAQUETA) or []
if not isinstance(sim_maqueta, list):
    aviso(f'simulaciones/{MAQUETA}: no es una lista de controles')
    sim_maqueta = []
simulaciones[MAQUETA] = sim_maqueta
maqueta_js = accionadores_maqueta()
if maqueta_js is None and sim_maqueta:
    aviso('no se pudo leer la tabla ACCIONADORES de web/js/propuesta/simulacion.js para revisar las simulaciones de la maqueta')
controles_maqueta = revisar_controles(f'simulaciones/{MAQUETA}', sim_maqueta, maqueta_js,
                                      'la maqueta no sabe accionarlo (ACCIONADORES de web/js/propuesta/simulacion.js)',
                                      extra={'capitulos'})
for c in sim_maqueta:
    if not isinstance(c, dict) or 'capitulos' not in c:
        continue
    caps_c = c['capitulos']
    if not isinstance(caps_c, list) or not caps_c or not all(isinstance(x, str) for x in caps_c):
        aviso(f'simulaciones/{MAQUETA}/{c.get("id")}: capitulos es una lista de ids de capítulo')
        continue
    for x in caps_c:
        if x not in capitulos_tecnica:
            aviso(f'simulaciones/{MAQUETA}/{c.get("id")}: «{x}» no es un capítulo de la presentación técnica')
hora = next((c for c in sim_maqueta if isinstance(c, dict) and c.get('id') == 'hora'), None)
if hora is not None and isinstance(hora.get('opciones'), list):
    horas = horas_maqueta()
    pedidas = [o.get('id') for o in hora['opciones'] if isinstance(o, dict)]
    if horas is None:
        aviso('no se pudo leer ORDEN_HORAS de web/js/propuesta/ambiente.js para revisar las horas de la maqueta')
    elif pedidas != horas:
        aviso(f'simulaciones/{MAQUETA}/hora: las opciones ({", ".join(map(str, pedidas))}) no son las horas de la maqueta '
              f'en su orden ({", ".join(horas)}; ORDEN_HORAS de web/js/propuesta/ambiente.js)')
# El catálogo de piezas de la maqueta (`tecnica.maqueta`): lo que el asistente puede mostrar, ocultar o aislar en cada
# capítulo y las partes que les puede quitar (web/js/propuesta/visual.js; el guion solo le pasa al modelo ids y nombres).
# Se revisa contra lo que existe: los capítulos de la técnica, los ids de capa (literales `esc.capa('…')` de los módulos),
# los nombres de los grupos de las piezas (literales `capa('…')` de piezas/*.js, o las naves del parque, que llevan el id
# de su sitio de geo.json), los nodos de los modelos de las sedes (el bloque JSON de cada GLB) y los estados que expone
# cada módulo (`efectos: { … }`). Un id que no existe no rompe nada en pantalla (se ignora), pero el asistente creería
# haber mostrado algo: por eso avisa aquí
ID_PIEZA = re.compile(r'[a-z0-9_]{1,40}')
JS = R / 'web/js/propuesta'
CAPA_JS = re.compile(r"esc\.capa\('([a-z_.0-9]+)'\)")
GRUPO_JS = re.compile(r"\bcapa\((?:raiz, )?'([A-Za-z_0-9]+)'\)")
capas_js = {k for f in (JS / 'modulos').glob('*.js') for k in CAPA_JS.findall(f.read_text(encoding='utf-8'))}
grupos_js = {k for f in (JS / 'piezas').glob('*.js') for k in GRUPO_JS.findall(f.read_text(encoding='utf-8'))}
_nodos = {}
def nodos_glb(eid):
    """Los nombres de los nodos del modelo de una sede (su GLB de cerca), o None si no está."""
    if eid not in _nodos:
        f = R / f'web/models/edificios/{eid}_lod0.glb'
        try:
            b = f.read_bytes()
            _nodos[eid] = {x.get('name') for x in json.loads(b[20:20 + int.from_bytes(b[12:16], 'little')]).get('nodes', [])}
        except (OSError, ValueError):
            _nodos[eid] = None
    return _nodos[eid]
def efectos_js(cid):
    f = JS / 'modulos' / f'{cid}.js'
    m = re.search(r'\befectos:\s*\{([^\n]*)', f.read_text(encoding='utf-8')) if f.exists() else None
    return set(re.findall(r'[a-z_0-9]+', m.group(1))) if m else set()
maqueta = tecnica.get('maqueta') or {}
piezas_total = 0
if not isinstance(maqueta, dict):
    aviso('tecnica.maqueta no es un objeto {capítulo: [piezas]}')
    maqueta = {}
for cid, piezas in maqueta.items():
    donde = f'maqueta/{cid}'
    if cid not in capitulos_tecnica:
        aviso(f'{donde}: no es un capítulo de la presentación técnica')
    if not isinstance(piezas, list):
        aviso(f'{donde}: no es una lista de piezas')
        continue
    sitios_comp = {s.get('id') for s in ((geo.get(cid) or {}).get('sitios') or []) if s.get('rol') == 'componente'}
    grupo_vale = lambda n: n in grupos_js or n in sitios_comp
    vistos = set()
    for x in piezas:
        if not isinstance(x, dict) or not isinstance(x.get('id'), str) or not ID_PIEZA.fullmatch(x['id']):
            aviso(f'{donde}: una pieza sin id válido ([a-z0-9_], hasta 40): {x.get("id") if isinstance(x, dict) else x!r}')
            continue
        pid = f'{donde}/{x["id"]}'
        piezas_total += 1
        if x['id'] in vistos:
            aviso(f'{pid}: el id de la pieza está repetido en el capítulo')
        vistos.add(x['id'])
        if not str(x.get('nombre') or '').strip():
            aviso(f'{pid}: la pieza no tiene nombre')
        if not isinstance(x.get('capas'), list) or not x['capas']:
            aviso(f'{pid}: la pieza no dice sus capas')
        for k in x.get('capas') or []:
            if k not in capas_js:
                aviso(f'{pid}: la capa «{k}» no existe en web/js/propuesta/modulos/')
        for n in x.get('grupos') or []:
            if not grupo_vale(n):
                aviso(f'{pid}: el grupo «{n}» no está en web/js/propuesta/piezas/ ni es una nave de geo.json')
        r, nodos = x.get('replica'), None
        if r is not None:
            nodos = nodos_glb(r.get('id')) if isinstance(r, dict) else None
            if nodos is None:
                aviso(f'{pid}: la réplica «{r.get("id") if isinstance(r, dict) else r}» no tiene modelo en web/models/edificios/')
            for n in (r.get('sin') or []) if isinstance(r, dict) else []:
                if nodos is not None and n not in nodos:
                    aviso(f'{pid}: la réplica oculta el nodo «{n}», que no está en su modelo')
        if x.get('efecto') is not None and x['efecto'] not in efectos_js(cid):
            aviso(f'{pid}: el módulo no expone el estado «{x["efecto"]}» (efectos de web/js/propuesta/modulos/{cid}.js)')
        partes = set()
        for pt in x.get('partes') or []:
            if not isinstance(pt, dict) or not isinstance(pt.get('id'), str) or not ID_PIEZA.fullmatch(pt['id']) or pt['id'] in partes:
                aviso(f'{pid}: una parte con id repetido o inválido: {pt.get("id") if isinstance(pt, dict) else pt!r}')
                continue
            partes.add(pt['id'])
            if not str(pt.get('nombre') or '').strip():
                aviso(f'{pid}.{pt["id"]}: la parte no tiene nombre')
            if not pt.get('grupos') and not pt.get('nodos'):
                aviso(f'{pid}.{pt["id"]}: la parte no dice qué grupos o qué nodos la forman')
            for n in pt.get('grupos') or []:
                if not grupo_vale(n):
                    aviso(f'{pid}.{pt["id"]}: el grupo «{n}» no está en web/js/propuesta/piezas/ ni es una nave de geo.json')
            for n in pt.get('nodos') or []:
                if nodos is None or n not in nodos:
                    aviso(f'{pid}.{pt["id"]}: el nodo «{n}» no está en el modelo de la réplica de la pieza')
if not terr:
    aviso('falta data/propuesta/territorio.json (python3 scripts/geo/territorio_propuesta.py)')

out = {
    'meta': g.get('meta', {}),
    'portada': g.get('portada', {}),
    'modulos': modulos,
    'financiacion': g.get('financiacion', {}),
    'ruta': g.get('ruta', {}),
    'pedidos': g.get('pedidos', {}),
    'tecnica': tecnica,
    'zonas_intervencion': geo.get('zonas_intervencion', []),
    'geo': {k: v for k, v in geo.items() if k != 'zonas_intervencion'},
    'territorio': terr,
}
# espacios que no se cortan entre número y unidad («69 %», «10 × 22 m», «Lote 2», «1.ª etapa»): así una cifra no queda
# partida entre dos líneas del panel. Solo en los textos de la presentación (no en geo ni territorio) y nunca en URL.
NBSP = '\u00a0'
UNIDAD = re.compile(r'(\d)[ \t](%|m²|m³|km²?\b|ha\b|m\b|L/s|L/día|kWp|MWp|kWh|MWh|kW\b|MW\b|kV\b|t/día|t/mes|t/h|t\b|horas?\b|días?\b|años?\b|meses\b|M\b|millones\b|billones\b)')
POR = re.compile(r'(\d)[ \t]×[ \t](\d)')
ROTULO = re.compile(r'\b(Lote|lote|Fase|fase|Sector|sector|Bloque|bloque|Etapa|etapa|Tramo|tramo|Calle|Carrera|manzana)[ \t](\d)')
ORDINAL = re.compile(r'(\d\.[ªº])[ \t]')
# y un rango con raya entre cifras («2028–2031», «$5–8 M») no se parte después de la raya (unión de palabras U+2060)
RANGO = re.compile(r'(\d)–(?=\$?\d)')
UNION = '\u2060'
cambios = 0
def sin_cortes(v, clave=''):
    global cambios
    if isinstance(v, dict):
        return {k: sin_cortes(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [sin_cortes(x, clave) for x in v]
    if isinstance(v, str) and clave != 'url' and not v.startswith('http'):
        n = POR.sub(f'\\1{NBSP}×{NBSP}\\2', v)
        n = UNIDAD.sub(f'\\1{NBSP}\\2', n)
        n = ROTULO.sub(f'\\1{NBSP}\\2', n)
        n = ORDINAL.sub(f'\\1{NBSP}', n)
        n = RANGO.sub(f'\\1–{UNION}', n)
        cambios += n != v
        return n
    return v
for k in ('meta', 'portada', 'modulos', 'financiacion', 'ruta', 'pedidos', 'tecnica'):
    out[k] = sin_cortes(out[k])
# los controles de las simulaciones van tal cual (después de unir cifras y unidades): el asistente los pide por id o por
# nombre, y el nombre debe ser el mismo en el catálogo, en el guion y en el atlas
for i in out['tecnica'].get('inmersiones') or []:
    if isinstance(i, dict):
        i['controles'] = json.loads(json.dumps(simulaciones.get(i.get('id')) or []))
out['tecnica']['simulaciones_maqueta'] = json.loads(json.dumps(sim_maqueta))

# El Home repite en cada tarjeta el nombre y el lema del área, enlaza a su capítulo y muestra su imagen: si el módulo cambia,
# el Home se queda atrás sin que nadie lo note. Se revisa tarjeta por tarjeta, no el archivo entero (los ids del área
# también salen en las variables CSS y en los nombres de archivo). También se revisa que la lista de vistas del atlas que
# el Home manda a atlas.html sea la de las pestañas del atlas.
home = R / 'web/index.html'
if home.exists():
    h = home.read_text(encoding='utf-8')
    plano = lambda t: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t).replace('&nbsp;', ' ').replace('\u00a0', ' ').replace('\u2060', '')).strip().lower()
    tarjetas = {m.group(1): m.group(2) for m in re.finditer(r'<a class="area[^"]*"[^>]*href="propuesta\.html#([\w-]+)"[^>]*>(.*?)</a>', h, re.S)}
    for m in modulos:
        t = tarjetas.pop(m['id'], None)
        if t is None:
            aviso(f'el Home no tiene la tarjeta del área {m["id"]} (web/index.html)')
            continue
        nombre, nombres = re.search(r'<b>(.*?)</b>', t, re.S), list(dict.fromkeys(x for x in (m.get('corto'), m.get('nombre')) if x))
        if not nombre or plano(nombre.group(1)) not in {plano(x) for x in nombres}:
            aviso(f'la tarjeta de {m["id"]} en el Home no lleva su nombre ({" o ".join(f"«{x}»" for x in nombres)}) (web/index.html)')
        frase = re.search(r'<span class="frase">(.*?)</span>', t, re.S)
        if m.get('lema') and (not frase or plano(frase.group(1)) != plano(m['lema'])):
            aviso(f'el lema de {m["id"]} cambió y el Home sigue con otro: «{m["lema"]}» (web/index.html)')
        img = re.search(r'src="(img/home/[^"]+)"', t)
        if not img or img.group(1) != f'img/home/area-{m["id"]}.webp':
            aviso(f'la tarjeta de {m["id"]} en el Home no muestra img/home/area-{m["id"]}.webp (web/index.html)')
        if not (R / f'web/img/home/area-{m["id"]}.webp').exists():
            aviso(f'falta la imagen del Home para {m["id"]} (web/img/home/area-{m["id"]}.webp)')
    for sobra in tarjetas:
        aviso(f'el Home tiene una tarjeta de un área que no está en la propuesta: {sobra} (web/index.html)')
    for ref in sorted(set(re.findall(r'(?:src="|url\(|href="|content=")(img/home/[^")]+)', h))):
        if not (R / 'web' / ref).exists():
            aviso(f'el Home cita una imagen que no existe: web/{ref}')
    atlas = R / 'web/atlas.html'
    vistas = re.search(r'VISTAS_ATLAS = \[([^\]]*)\]', h)
    if atlas.exists() and vistas:
        enlaces = re.findall(r"'([\w-]+)'", vistas.group(1))
        pestanas = re.findall(r'<a href="#([\w-]+)" data-view="\1"', atlas.read_text(encoding='utf-8'))
        if sorted(enlaces) != sorted(pestanas):
            aviso(f'las vistas del atlas que el Home redirige ({", ".join(enlaces)}) no son las pestañas del atlas ({", ".join(pestanas)}) (web/index.html)')

dest = R / 'web/data/propuesta.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
total = sum((m.get('inversion') or {}).get('central') or 0 for m in modulos)
print(f'propuesta.json {dest.stat().st_size / 1024:.0f} KB: {len(modulos)} módulos, inversión central {total:,.0f} M'.replace(',', '.'))

# El guion para el asistente del panel (la herramienta `presentacion`): lo que muestra cada paso de la presentación
# técnica (la que muestran el asistente y los agentes por MCP), en texto plano y sin plata. Va
# versionado dentro de admin/ (así lo tiene también el panel desplegado aparte, que no trae web/) y lo arma
# admin/app/agente/guion.py con lo mismo que lee la presentación; una prueba del panel los compara. guion.py solo usa la
# biblioteca estándar: se carga por su ruta, sin las dependencias del panel.
spec = importlib.util.spec_from_file_location('guion_propuesta', R / 'admin/app/agente/guion.py')
guion_py = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guion_py  # dataclasses lo busca ahí
spec.loader.exec_module(guion_py)
guion = guion_py.derivar(json.loads(dest.read_text(encoding='utf-8')))
for p in guion_py.problemas(guion):
    aviso(f'guion del asistente: {p} (data/propuesta/)')
destino_guion = R / 'admin/app/agente/propuesta_guion.json'
destino_guion.write_text(json.dumps(guion, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(f'propuesta_guion.json {destino_guion.stat().st_size / 1024:.0f} KB (presentación técnica): '
      f'{len(guion["capitulos"])} capítulos, {sum(len(c["pasos"]) for c in guion["capitulos"])} pasos, '
      f'{len(guion["inmersiones"])} inmersiones, '
      f'{sum(1 for c in guion["capitulos"] for x in c.get("componentes", []) if x["enfoque"])} componentes con lugar en la maqueta')
print(f'Textos con cifras unidas a su unidad: {cambios}')
print(f'Catálogo de la maqueta: {piezas_total} piezas en {len(maqueta)} capítulos ({len(capas_js)} capas en los módulos)')
print(f'Simulaciones del atlas: {controles_total} controles en {sum(1 for k, v in simulaciones.items() if v and k != MAQUETA)} inmersiones')
print(f'Simulaciones de la maqueta: {controles_maqueta} controles')
print(f'Avisos de la propuesta: {len(avisos)}')
for a in avisos:
    print('  -', a)
if avisos and '--estricto' in sys.argv:
    raise SystemExit(1)
