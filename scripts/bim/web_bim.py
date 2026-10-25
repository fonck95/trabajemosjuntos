"""Datos del modo «Modelo BIM» de la vista (especificación 17.4-17.5, equipo F): de data/bim a web/data, compactos y
partidos por nivel.

  web/data/torre_bim.json                 índice: niveles, disciplinas, árbol con contadores, materiales, georreferenciación,
                                          cantidades, 5D, 4D, resumen de interferencias, validación y descargas del IFC
  web/data/torre_bim_<NIVEL>.json         elementos del nivel (geometría, Psets, Qto, 5D, 4D, vínculo con el análisis)
  web/data/torre_bim_ref_<NIVEL>.json     refuerzo de los elementos del nivel: formas relativas compartidas (mm) y juegos
                                          (base, copias, etiqueta…); los espirales de pilotes van como parámetros
  web/data/torre_bim_interferencias.json  lista completa de interferencias con su posición para «Ir a»

Lo llama scripts/build_data.py (bloque «bim»), que antes revisa que los generados estén al día (insumos_sha1). También
se puede correr solo: python3 scripts/bim/web_bim.py (escribe sin revisar). Biblioteca estándar; salida determinista.
Los textos llegan sin rutas de archivo ni claves internas: las fuentes se nombran en palabras."""
import json
import re
from pathlib import Path

# rutas propias (sin importar comun.py: build_data.py ya tiene cargado otro módulo con ese nombre)
R = Path(__file__).resolve().parents[2]
BIM = R / 'data/bim'
MODELO = BIM / 'torre_hospital.bim.json'
INTERF = BIM / 'interferencias.json'
VALID = BIM / 'validacion_ifc.json'
ESTRUCTURA = R / 'data/sismo/torre_hospital_estructura.json'
AVISO = 'Modelo de prefactibilidad: no reemplaza los diseños firmados.'

NOMBRES_CLASE = {
    'IfcSpace': 'Espacios (recintos)', 'IfcWall': 'Muros', 'IfcDoor': 'Puertas', 'IfcWindow': 'Ventanas', 'IfcSlab': 'Losas',
    'IfcCovering': 'Pisos y cielos', 'IfcStair': 'Escaleras', 'IfcStairFlight': 'Tramos de escalera', 'IfcColumn': 'Columnas',
    'IfcBeam': 'Vigas', 'IfcFooting': 'Dados, losas de pilotes y vigas de amarre', 'IfcPile': 'Pilotes',
    'IfcElementAssembly': 'Fosos y cisternas', 'IfcReinforcingBar': 'Barras de refuerzo', 'IfcMedicalDevice': 'Equipos biomédicos',
    'IfcFurniture': 'Mobiliario', 'IfcElectricAppliance': 'Aparatos eléctricos', 'IfcSanitaryTerminal': 'Aparatos sanitarios',
    'IfcFireSuppressionTerminal': 'Protección contra incendio', 'IfcLightFixture': 'Luminarias', 'IfcOutlet': 'Tomas y salidas',
    'IfcCommunicationsAppliance': 'Comunicaciones', 'IfcElectricDistributionBoard': 'Tableros eléctricos',
    'IfcElectricFlowStorageDevice': 'Almacenamiento de energía', 'IfcElectricGenerator': 'Planta eléctrica', 'IfcPump': 'Bombas',
    'IfcSolarDevice': 'Paneles solares', 'IfcTank': 'Tanques', 'IfcTransformer': 'Transformador', 'IfcTransportElement': 'Ascensores',
    'IfcUnitaryEquipment': 'Equipos de aire acondicionado'}
TIPO_ROL = {
    'longitudinal': 'barras longitudinales', 'estribo': 'estribos', 'gancho_suplementario': 'ganchos suplementarios',
    'gancho_suplementario_x': 'ganchos suplementarios en x', 'gancho_suplementario_y': 'ganchos suplementarios en y',
    'superior_corrida': 'superiores corridas', 'inferior_corrida': 'inferiores corridas', 'bastones': 'bastones',
    'malla_x': 'malla en x', 'malla_y': 'malla en y', 'inferior_nervio': 'inferiores de nervios', 'estribo_nervio': 'estribos de nervios',
    'borde_i': 'borde i', 'borde_j': 'borde j', 'estribo_borde_i': 'estribos del borde i', 'estribo_borde_j': 'estribos del borde j',
    'gancho_borde_i': 'ramas del borde i', 'gancho_borde_j': 'ramas del borde j', 'cortina_horizontal': 'cortina horizontal',
    'cortina_vertical': 'cortina vertical', 'principal': 'principales', 'reparticion': 'repartición',
    'superior_arranque': 'superiores del arranque', 'superior_llegada': 'superiores de la llegada',
    'longitudinal_superior': 'longitudinales de la mitad superior', 'longitudinal_inferior': 'longitudinales de la mitad inferior',
    'espiral': 'espiral', 'parrilla_inferior_x': 'parrilla inferior en x', 'parrilla_inferior_y': 'parrilla inferior en y',
    'parrilla_superior_x': 'parrilla superior en x', 'parrilla_superior_y': 'parrilla superior en y', 'piel': 'refuerzo de piel',
    'superior': 'superiores', 'inferior': 'inferiores', 'malla_losa': 'malla de losa', 'malla_muro': 'malla de muro', 'malla': 'malla'}

# nombres en palabras de los archivos que citan los textos del modelo (la web no muestra rutas)
_ARCHIVOS = [
    ('data/sismo/torre_hospital_estructura.json', 'prediseño estructural'),
    ('data/edificios/torre_hospital_plantas.json', 'plantas del anteproyecto'),
    ('torre_hospital_plantas.json', 'plantas del anteproyecto'),
    ('data/proyectos/torre_hospital/inventario_dotacion.json', 'inventario de dotación'),
    ('inventario_dotacion.json', 'inventario de dotación'),
    ('docs/11-torre-hospital-nivel-1.md', 'documento de la torre'),
    ('data/fuentes/ipc_dane.csv', 'serie del IPC del DANE'),
    ('validacion_ifc.json', 'la validación del IFC'),
    ('torre_hospital.json', 'modelo del sitio'),
    ('presupuesto.json', 'presupuesto de obra'),
    ('normas.json', 'matriz de normas'),
    ('programa.json', 'programa médico-arquitectónico'),
    ('laboratorio.json', 'estudio del laboratorio'),
    ('dotacion.json', 'dotación'),
    ('apu.json', 'análisis de precios unitarios'),
]
_ARCH = r'(?:[\w\-]+/)*[\w\-]+\.(?:json|md|csv|py|ifc)'
_FLECHA = r'(?:\s*→\s*[\w\.]+)?'


# los equipos de trabajo (A: prediseño estructural, B: arquitectura y dotación, F: modelo BIM) son nombres internos: en la
# web se dice de qué trabajo sale cada dato (los ejes «entre A y B» no se tocan: estas reglas piden la frase completa)
_EQUIPOS = [
    (r';\s*equipo [A-F]\)', ')'), (r'\s*\(equipo [A-F]\)', ''), (r'\s+del equipo [A-F]\b', ''), (r';\s*equipo F\b', ''),
    (r'\bdespiece de A\b', 'despiece del prediseño'), (r'\bprediseño de A\b', 'prediseño estructural'),
    (r'\banteproyecto de B\b', 'anteproyecto de arquitectura'), (r'\bmodelo de A\b', 'modelo estructural'),
    (r'\bcantidades de A\b', 'cantidades del prediseño'), (r'\bdatos de A y B\b', 'datos del prediseño y del anteproyecto'),
    (r'\bmodelo de análisis \(A\)', 'modelo de análisis'), (r'\(A y B\)', '(prediseño y arquitectura)'),
    (r'\(A\)', '(prediseño estructural)'), (r'\(B\)', '(arquitectura)'), (r'\bEl peso de A\b', 'El peso del prediseño'),
    (r'(?<=\. )A mide\b', 'El prediseño mide'), (r'^A mide\b', 'El prediseño mide'), (r'\(A: (\d+)\)', r'(prediseño: \1)'),
]


def sin_equipos(s):
    for a, b in _EQUIPOS:
        s = re.sub(a, b, s)
    return s


def texto(s):
    """Texto para la web: sin rutas ni campos internos («archivo.json → campo» se vuelve el nombre de la fuente) ni los
    nombres internos de los equipos."""
    if not isinstance(s, str):
        return s
    s = sin_equipos(s)
    if '.' not in s:
        return s
    s = re.sub(r'\s*\(\s*' + _ARCH + _FLECHA + r'\s*\)', '', s)                 # «(archivo.json → campo)» suelto
    s = re.sub(r'\s*[;,]\s*' + _ARCH + _FLECHA + r'(?=\s*\))', '', s)          # «…; archivo.json → campo)» al final de un paréntesis
    s = re.sub(r'\s*\(\s*' + _ARCH + r'\s*,\s*', ' (', s)                       # «(archivo.json, sección…» → «(sección…»
    s = re.sub(r'\bde (laboratorio|dotacion)\.json', lambda m: 'del estudio del laboratorio' if m.group(1) == 'laboratorio'
               else 'de la dotación', s)
    s = re.sub(r'\bver validacion_ifc\.json', 'ver la validación del IFC', s)
    s = re.sub(r'\bpresupuesto\.json (\d+\.\d+(?: y \d+\.\d+)*)',
               lambda m: ('ítems ' if ' y ' in m.group(1) else 'ítem ') + m.group(1) + ' del presupuesto', s)
    s = re.sub(r'\ben presupuesto\.json', 'en el presupuesto de obra', s)
    s = re.sub(r'\bde normas\.json', 'de la matriz de normas', s)
    s = re.sub(r'\(\s*programa\.json\s*→\s*pisos_y_alturas\.parapeto\s*=\s*', '(cota del antepecho del programa: ', s)
    for arch, nombre in _ARCHIVOS:
        s = re.sub(r'(?<![\w/])' + re.escape(arch) + _FLECHA, nombre, s)
    s = re.sub(r'\s*' + _ARCH + _FLECHA, '', s)                                # cualquier otro archivo
    s = re.sub(r'\s*→\s*[a-z_][\w.]*', '', s)                                    # «→ campo» que quede suelto
    return re.sub(r'\s{2,}', ' ', s).strip()


def limpio(o):
    if isinstance(o, dict):
        return {k: limpio(v) for k, v in o.items() if k not in ('generado_por', 'insumos_sha1')}
    if isinstance(o, list):
        return [limpio(v) for v in o]
    if isinstance(o, float):
        return round(o, 4) + 0.0
    return texto(o)


def _r(v, n=3):
    return round(float(v), n) + 0.0


def geo_web(g):
    """Geometría compacta (mm de precisión)."""
    if g is None:
        return None
    t = g['tipo']
    out = {'tipo': t}
    for k, v in g.items():
        if k == 'tipo':
            continue
        if k == 'partes':
            out[k] = [geo_web(p) for p in v]
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = _r(v, 4 if k == 'rot' else 3)
        elif isinstance(v, list):
            out[k] = json.loads(json.dumps(v), parse_float=lambda x: _r(float(x), 3))
        else:
            out[k] = v
    return out


def elemento_web(e):
    out = {}
    for k, v in e.items():
        if k == 'geometria':
            out[k] = geo_web(v)
        elif k == 'vano' and isinstance(v, dict):
            out[k] = {**{kk: vv for kk, vv in v.items() if kk != 'geometria'}, 'geometria': geo_web(v.get('geometria'))}
        else:
            out[k] = limpio(v)
    return out


def _mm(v):
    return int(round(v * 1000))


def exportar(escribir, aviso=print, revisar=None):
    """escribir(nombre, obj) escribe un archivo de web/data; revisar(nombre_web, ruta) devuelve el generado al día o None."""
    cargar = revisar or (lambda _n, ruta: json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else None)
    M = cargar('torre_bim.json', MODELO)
    if M is None:
        return []
    I = cargar('torre_bim_interferencias.json', INTERF)
    V = cargar('validación del IFC (en torre_bim.json)', VALID)
    escritos = []
    niveles = [n['id'] for n in M['niveles']]
    por_nivel = {n: [] for n in niveles}
    for e in M['elementos']:
        por_nivel.setdefault(e['nivel'], []).append(e)
    nivel_de = {e['id']: e['nivel'] for e in M['elementos']}
    # ---- refuerzo por nivel del anfitrión: formas relativas compartidas en mm y juegos
    ref_por_nivel = {}
    for j in M['refuerzo']:
        ref_por_nivel.setdefault(nivel_de.get(j['host'], j['nivel']), []).append(j)
    resumen_ref = {}
    archivos_ref = {}
    for niv in niveles:
        js = ref_por_nivel.get(niv) or []
        if not js:
            continue
        formas, idx, juegos = [], {}, []
        for j in js:
            w = {'id': j['id'], 'host': j['host'], 'rol': j['rol'], 'tipo': TIPO_ROL.get(j['rol'], j['rol'].replace('_', ' ')),
                 'num': j['num'], 'db_mm': _r(j['db'] * 1000, 1), 'etiqueta': texto(j['etiqueta']), 'n': j['n'],
                 'largo_m': _r(j['largo'], 3), 'kg': _r(j['kg'], 2), 'fase': j['fase'], 'guid': j['guid'],
                 'costo': [{'item': c['item'], 'cantidad': _r(c['cantidad'], 2), 'valor': _r(c['valor'], 0)} for c in j['costo']]}
            for k in ('zona', 'ganchos', 'nota', 'diam_mm'):
                if j.get(k) is not None:
                    w[k] = texto(j[k])
            if 'param' in j:                                   # espiral: la vista la arma con sus parámetros
                p = j['param']
                w['param'] = {'tipo': p['tipo'], 'centro': [_r(c) for c in p['centro']], 'radio': _r(p['radio'], 4),
                              'tramos': [{'z0': _r(t['z0']), 'z1': _r(t['z1']), 'paso': _r(t['paso'], 4)} for t in p['tramos']],
                              'lados_por_vuelta': 12}
            else:
                pts = j['forma']
                b0 = pts[0]
                rel_ = tuple((_mm(p[0] - b0[0]), _mm(p[1] - b0[1]), _mm(p[2] - b0[2])) for p in pts)
                if rel_ not in idx:
                    idx[rel_] = len(formas)
                    formas.append([c for q in rel_ for c in q])
                w['forma'] = idx[rel_]
                w['base'] = [_r(c, 4) for c in b0]
            w['copias'] = [[_mm(c[0]), _mm(c[1]), _mm(c[2])] for c in j['copias']]
            juegos.append(w)
            h = resumen_ref.setdefault(j['host'], {'juegos': 0, 'barras': 0, 'kg': 0.0})
            h['juegos'] += 1
            h['barras'] += j['n']
            h['kg'] += j['kg']
        nombre = f'torre_bim_ref_{niv}.json'
        escribir(nombre, {'nivel': niv, 'aviso': AVISO, 'tipo_dato': 'cálculo propio (despiece del prediseño estructural en geometría real)',
                          'unidades': 'base en metros (coordenadas del proyecto); formas y copias en milímetros: cada barra es la '
                                      'forma desplazada a base + copia; espirales por parámetros (radio, paso y cotas en metros)',
                          'formas': formas, 'juegos': juegos})
        escritos.append(nombre)
        archivos_ref[niv] = nombre
    # ---- elementos por nivel
    archivos_niv = {}
    arbol = {}
    for niv in niveles:
        es = por_nivel.get(niv) or []
        if not es:
            continue
        lista, fichas, i_f, psets, i_p = [], [], {}, [], {}
        for e in es:
            w = elemento_web(e)
            # fichas (Pset propio) y Psets repetidos van una sola vez por archivo: el elemento guarda su índice
            at = {k: v for k, v in (w.pop('atlas', None) or {}).items() if k not in ('Linea', 'Capa')}
            ps = w.pop('psets', None) or {}
            ml = (ps.get('Pset_ManufacturerTypeInformation') or {}).get('ModelLabel')
            if ml and e['nombre'].startswith(ml):
                ps = {k: v for k, v in ps.items() if k != 'Pset_ManufacturerTypeInformation'}
            for tabla, idx, val, clave in ((fichas, i_f, at, 'ficha'), (psets, i_p, ps, 'psets')):
                if val:
                    k_ = json.dumps(val, sort_keys=True, ensure_ascii=False)
                    if k_ not in idx:
                        idx[k_] = len(tabla)
                        tabla.append(val)
                    w[clave] = idx[k_]
            w['costo'] = [{k: c[k] for k in ('item', 'cantidad', 'valor', 'valor_unitario', 'nota') if c.get(k) is not None}
                          for c in w.get('costo') or []]
            if e['id'] in resumen_ref:
                rr = resumen_ref[e['id']]
                w['refuerzo'] = {'juegos': rr['juegos'], 'barras': rr['barras'], 'kg': _r(rr['kg'], 1)}
            lista.append(w)
            a = arbol.setdefault(e['disciplina'], {}).setdefault(niv, {})
            a[e['clase']] = a.get(e['clase'], 0) + 1
        nombre = f'torre_bim_{niv}.json'
        escribir(nombre, {'nivel': niv, 'aviso': AVISO,
                          'nota': 'ficha y psets de cada elemento son índices en las listas fichas (tipo de dato, fuente, norma y '
                                  'notas del modelo) y psets (conjuntos de propiedades de IFC) de este archivo; la unidad, el APU y '
                                  'el valor del presupuesto de cada ítem están en el índice (cinco_d.comparacion)',
                          'fichas': fichas, 'psets': psets, 'elementos': lista})
        escritos.append(nombre)
        archivos_niv[niv] = nombre
    for j in M['refuerzo']:
        niv = nivel_de.get(j['host'], j['nivel'])
        a = arbol.setdefault('REF', {}).setdefault(niv, {})
        a['IfcReinforcingBar'] = a.get('IfcReinforcingBar', 0) + 1
    # ---- interferencias (lista completa aparte) y su resumen en el índice
    res_int = None
    if I is not None:
        lista = []
        for x in I['interferencias']:
            w = {k: limpio(x[k]) for k in ('id', 'categoria', 'severidad', 'estado', 'responsable', 'nivel', 'descripcion',
                                          'propuesta', 'norma', 'casos') if x.get(k) is not None}
            w['elementos'] = [e for e in x['elementos'] if not e.startswith('R-')][:8]
            w['barras'] = [e for e in x['elementos'] if e.startswith('R-')][:8]
            if x.get('posicion'):
                w['posicion'] = [_r(c) for c in x['posicion']]
            if x.get('medida'):
                w['medida'] = limpio(x['medida'])
            lista.append(w)
        escribir('torre_bim_interferencias.json', {'aviso': AVISO, 'tipo_dato': texto(I['tipo_dato']), 'criterios': limpio(I['criterios']),
                                                   'resumen': I['resumen'], 'interferencias': lista})
        escritos.append('torre_bim_interferencias.json')
        res_int = {'resumen': I['resumen'], 'revisado': limpio(I.get('revisado')), 'archivo': 'torre_bim_interferencias.json'}
    # ---- validación del IFC (resumen)
    val = None
    if V is not None:
        val = {'herramienta': V['herramienta'], 'resultado': V['resultado'], 'errores': V['errores'], 'archivos': []}
        for a in V['archivos']:
            w = {'archivo': Path(a['archivo']).name, 'mb': a['mb'], 'esquema': a['esquema'], 'entidades': a['entidades'],
                 'errores_de_esquema': a['validacion_esquema']['errores'], 'reglas_express': a['validacion_esquema'].get('reglas_express'),
                 'globalid': a['globalid'], 'georreferenciacion': a.get('georreferenciacion')}
            for k in ('concreto', 'acero', 'elementos_del_json_en_el_ifc'):
                if k in a:
                    w[k] = limpio(a[k])
            # plantillas de propiedades de IFC4, 4D (tareas con sus elementos) y 5D (partidas del presupuesto): solo el resumen
            if a.get('plantillas_ifc4'):
                w['plantillas_ifc4'] = {k: a['plantillas_ifc4'][k] for k in ('conjuntos_revisados', 'propiedades_revisadas', 'problemas')}
            if a.get('cuatro_d'):
                w['cuatro_d'] = {k: a['cuatro_d'][k] for k in ('tareas', 'con_salidas', 'errores')}
            if a.get('cinco_d'):
                w['cinco_d'] = {k: a['cinco_d'][k] for k in ('partidas', 'en_el_presupuesto_ifc', 'errores', 'total_ifc')}
            if 'conteos' in a:
                w['conteos_iguales'] = all(c['igual'] for c in a['conteos'])
            val['archivos'].append(w)
        val['federacion'] = limpio(V.get('federacion'))
    # ---- 5D por disciplina y capítulo (valores de los elementos y del refuerzo)
    por_disc = {}
    for e in M['elementos']:
        for c in e.get('costo') or []:
            if c.get('valor'):
                d = por_disc.setdefault(e['disciplina'], {})
                cap = str(c['item']).split('.')[0] if '.' in str(c['item']) else str(c['item'])
                d[cap] = d.get(cap, 0.0) + c['valor']
    for j in M['refuerzo']:
        for c in j['costo']:
            d = por_disc.setdefault('REF', {})
            cap = c['item'].split('.')[0]
            d[cap] = d.get(cap, 0.0) + c['valor']
    cinco_d = {'tipo_dato': 'cálculo propio: cantidades del modelo × valor unitario del presupuesto (pesos constantes de 2026)',
               'comparacion': limpio(M['comparacion_presupuesto']),
               'por_disciplina_y_capitulo': {d: {k: _r(v, 0) for k, v in sorted(c.items())} for d, c in sorted(por_disc.items())},
               'capitulos': {k: texto(v) for k, v in sorted({str(i['capitulo']): i.get('nombre_capitulo') for i in M['presupuesto']['items'].values()
                                                              if i.get('capitulo') is not None}.items())},
               'moneda': texto(M['presupuesto'].get('moneda'))}
    cuatro_d = {'tipo_dato': 'estimación: fases repartidas por piso y disciplina dentro de las etapas del cronograma',
                'etapas': limpio(M['cronograma']['etapas']), 'fases': limpio([{k: f[k] for k in f if k != 'guid'} for f in M['cronograma']['fases']]),
                'fuente': texto(M['cronograma'].get('fuente'))}
    # ejes de la retícula (cortes verticales por eje y «refuerzo del eje» en la vista), del prediseño estructural
    ejes = None
    if ESTRUCTURA.exists():
        ej = json.loads(ESTRUCTURA.read_text(encoding='utf-8')).get('ejes') or {}
        ejes = {'x': [{'id': q['id'], 'x': _r(q['x'])} for q in ej.get('x', []) if not q.get('auxiliar')],
                'y': [{'id': q['id'], 'y': _r(q['y'])} for q in ej.get('y', []) if not q.get('auxiliar')],
                'nota': 'ejes A-D de occidente a oriente (coordenada x) y 1-7 de sur a norte (coordenada y), en metros del marco del proyecto'}
    ifc = []
    for nombre, cont in (('torre_hospital.ifc', 'arquitectura, estructura, cimentación, equipamiento fijo y dotación'),
                         ('torre_hospital_refuerzo.ifc', 'refuerzo (IfcReinforcingBar con su geometría de barra)')):
        ruta = R / 'web/models' / nombre
        if ruta.exists():
            ifc.append({'url': f'models/{nombre}', 'archivo': nombre, 'mb': round(ruta.stat().st_size / 1e6, 2), 'contenido': cont,
                        'esquema': 'IFC4'})
    # estado de cada disciplina: su LOD objetivo (plan BIM) frente a lo que el modelo es hoy, con las interferencias duras
    # pendientes en las que participa (leídas de interferencias.json)
    disc_de = {e['id']: e['disciplina'] for e in M['elementos']}
    duras = {}
    for x in (I or {}).get('interferencias', []):
        if x['severidad'] != 'dura' or x['estado'] != 'pendiente':
            continue
        for d in sorted({'REF' if q.startswith('R-') else disc_de.get(q) for q in x['elementos']} - {None}):
            duras[d] = duras.get(d, 0) + 1
    disciplinas = {}
    for k, v in M['disciplinas'].items():
        w = {**limpio(v), 'elementos': sum(M['conteos'].get(k, {}).values())}
        if I is not None:
            w['duras_pendientes'] = duras.get(k, 0)
            n_ = duras.get(k, 0)
            w['estado_actual'] = (f'{w["estado_actual"]}; {n_} interferencia{"s" if n_ != 1 else ""} dura{"s" if n_ != 1 else ""} pendiente{"s" if n_ != 1 else ""}' if n_
                                  else f'{w["estado_actual"]}; sin interferencias duras pendientes')
        disciplinas[k] = w
    indice = {
        'id': 'torre_bim', 'nombre': M['nombre'], 'fecha': M['fecha'], 'aviso': AVISO, 'tipo_dato': texto(M['tipo_dato']), 'esquema': M['esquema'],
        'georreferenciacion': limpio(M['georreferenciacion']),
        'niveles': [{k: n[k] for k in ('id', 'nombre', 'elevacion')} for n in M['niveles']], 'ejes': ejes,
        'disciplinas': disciplinas, 'nota_lod': texto(M.get('nota_lod')),
        'clases': {c: NOMBRES_CLASE.get(c, c) for c in sorted({e['clase'] for e in M['elementos']} | {'IfcReinforcingBar'})},
        'arbol': {d: {n: dict(sorted(c.items())) for n, c in sorted(v.items(), key=lambda q: niveles.index(q[0]))} for d, v in sorted(arbol.items())},
        'materiales': {k: {'nombre': v['nombre'], 'categoria': v['categoria'], 'fuente': texto(v.get('fuente'))} for k, v in M['materiales'].items()},
        'totales': {k: v for k, v in M['totales'].items() if not isinstance(v, dict)},
        'cantidades': limpio(M['cantidades']),
        'cinco_d': cinco_d, 'cuatro_d': cuatro_d, 'interferencias': res_int, 'validacion_ifc': val, 'ifc': ifc,
        'archivos': {'elementos': archivos_niv, 'refuerzo': archivos_ref},
        'notas': ['Cada elemento trae su GlobalId del IFC, su clase IFC4, Psets, cantidades, ítem del presupuesto (5D), fase del '
                  'cronograma (4D) y, si es estructural, el id del elemento en el modelo sísmico para pintar D/C y rótulas.',
                  'El refuerzo se dibuja por elemento o por eje (nunca la torre entera): cada juego es una forma desplazada a sus copias.']}
    escribir('torre_bim.json', indice)
    escritos.append('torre_bim.json')
    return escritos


def main():
    def escribir(nombre, obj):
        ruta = R / 'web/data' / nombre
        ruta.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{nombre} {ruta.stat().st_size / 1024:.0f} KB')
    exportar(escribir)


if __name__ == '__main__':
    main()
