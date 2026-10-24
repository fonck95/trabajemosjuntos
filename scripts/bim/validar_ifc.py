"""Valida los IFC de la torre con IfcOpenShell (solo para validar: no es dependencia del sitio).

    <venv>/bin/python scripts/bim/validar_ifc.py

El venv de validación trae ifcopenshell 0.9 y numpy (y, si están, pytest para las reglas EXPRESS y pyproj para
contrastar la proyección). Comprueba en cada archivo:
- esquema IFC4 sin errores (ifcopenshell.validate, con las reglas WHERE de EXPRESS cuando hay pytest);
- GlobalId de 22 caracteres válidos y únicos; los compartidos entre los dos archivos (proyecto, sitio, edificio,
  niveles, fases y partidas) son los mismos y no hay otros repetidos;
- conteos por clase y cantidades iguales a las de data/bim/torre_hospital.bim.json: volumen de concreto (Qto y
  volumen de la geometría teselada por IfcOpenShell), barras y peso del acero;
- georreferenciación: IfcMapConversion e IfcProjectedCRS EPSG:9377 iguales al JSON y, con PROJ (pyproj), el este y el
  norte del ancla y el giro del eje x;
- una muestra determinista de geometrías (caja envolvente de IfcOpenShell frente a la del JSON);
- conjuntos Pset_ y Qto_ frente a las plantillas de IFC4 ADD2 (nombre, aplicabilidad, propiedad, forma y tipo de dato);
- 4D: cada tarea tiene como salidas (IfcRelAssignsToProduct) los elementos de su fase y ninguna entrada;
- 5D: el total de cada IfcCostItem (ifcopenshell.util.cost) igual al de comparacion_presupuesto.
Escribe data/bim/validacion_ifc.json (sin horas ni tiempos: dos corridas, mismos bytes)."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ifcopenshell  # noqa: E402
import ifcopenshell.geom  # noqa: E402
import ifcopenshell.guid  # noqa: E402
import ifcopenshell.util.cost  # noqa: E402
import ifcopenshell.util.pset  # noqa: E402
import ifcopenshell.util.sequence  # noqa: E402
import ifcopenshell.util.shape  # noqa: E402
import ifcopenshell.validate  # noqa: E402
import numpy as np  # noqa: E402

import despiece as DSP  # noqa: E402
import generar_bim as G  # noqa: E402
from comun import BIM, R, escribir_json, local_a_geo, r, rel, sha1  # noqa: E402

ENTRADA = BIM / 'torre_hospital.bim.json'
SALIDA = BIM / 'validacion_ifc.json'
IFC = [R / 'web/models/torre_hospital.ifc', R / 'web/models/torre_hospital_refuerzo.ifc']
CONCRETO = ('concreto_28', 'concreto_21')


def validar_esquema(f):
    try:
        import _pytest  # noqa: F401
        express = True
    except ImportError:
        express = False
    lg = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, lg, express_rules=express)
    errores = [s for s in lg.statements if s.get('level') == 'error']
    detalle = sorted({str(s.get('message'))[:200] for s in errores})[:20]
    return {'errores': len(errores), 'reglas_express': express, 'detalle': detalle}


def guids(f):
    out = [x.GlobalId for x in f.by_type('IfcRoot')]
    malos = []
    for g in out:
        try:
            ok = len(g) == 22 and len(ifcopenshell.guid.expand(g)) == 32 and g[0] in '0123'
        except Exception:
            ok = False
        if not ok:
            malos.append(g)
    return out, malos


def qto(x, nombre):
    for rel_ in getattr(x, 'IsDefinedBy', []) or []:
        if rel_.is_a('IfcRelDefinesByProperties') and rel_.RelatingPropertyDefinition.is_a('IfcElementQuantity'):
            for q in rel_.RelatingPropertyDefinition.Quantities:
                if q.Name == nombre:
                    return q[3]
    return None


def material(x):
    for rel_ in getattr(x, 'HasAssociations', []) or []:
        if rel_.is_a('IfcRelAssociatesMaterial'):
            return rel_.RelatingMaterial.Name
    return None


FORMA = {'P_SINGLEVALUE': 'IfcPropertySingleValue', 'P_BOUNDEDVALUE': 'IfcPropertyBoundedValue',
         'P_ENUMERATEDVALUE': 'IfcPropertyEnumeratedValue', 'P_LISTVALUE': 'IfcPropertyListValue',
         'P_TABLEVALUE': 'IfcPropertyTableValue', 'P_REFERENCEVALUE': 'IfcPropertyReferenceValue'}
QTIPO = {'Q_LENGTH': 'IfcQuantityLength', 'Q_AREA': 'IfcQuantityArea', 'Q_VOLUME': 'IfcQuantityVolume', 'Q_COUNT': 'IfcQuantityCount',
         'Q_WEIGHT': 'IfcQuantityWeight', 'Q_TIME': 'IfcQuantityTime'}


def plantillas(f):
    """Conjuntos con prefijo reservado (Pset_ y Qto_) frente a las plantillas de IFC4 ADD2 de buildingSMART
    (ifcopenshell.util.pset.get_template('IFC4')): el conjunto existe y aplica a la clase, cada propiedad existe y tiene
    la forma (simple, acotada, enumerada) y el tipo de dato de la plantilla; las cantidades, su tipo (longitud, área...)."""
    t = ifcopenshell.util.pset.get_template('IFC4')
    problemas = {}
    n_conj = n_props = 0

    def mal(msg):
        problemas[msg] = problemas.get(msg, 0) + 1

    def tipos(p):
        if p.is_a('IfcPropertySingleValue'):
            return [p.NominalValue]
        if p.is_a('IfcPropertyBoundedValue'):
            return [v for v in (p.UpperBoundValue, p.LowerBoundValue, p.SetPointValue) if v is not None]
        if p.is_a('IfcPropertyEnumeratedValue'):
            return list(p.EnumerationValues or [])
        return []
    conjuntos = [(rel.RelatingPropertyDefinition, [o.is_a() for o in rel.RelatedObjects]) for rel in f.by_type('IfcRelDefinesByProperties')]
    conjuntos += [(mp, None) for mp in f.by_type('IfcMaterialProperties')]
    for pd, clases in conjuntos:
        nombre = pd.Name or ''
        if not nombre.startswith(('Pset_', 'Qto_')):
            continue
        n_conj += 1
        tpl = t.get_by_name(nombre)
        if tpl is None:
            mal(f'{nombre}: el conjunto no existe en IFC4 (prefijo reservado)')
            continue
        for c in sorted(set(clases or [])):
            if nombre not in t.get_applicable_names(c):
                mal(f'{nombre}: no aplica a {c} según la plantilla')
        props = {p.Name: p for p in tpl.HasPropertyTemplates}
        es_qto = pd.is_a('IfcElementQuantity')
        for p in (pd.Quantities if es_qto else pd.HasProperties if pd.is_a('IfcPropertySet') else pd.Properties):
            n_props += 1
            pt = props.get(p.Name)
            if pt is None:
                mal(f'{nombre}.{p.Name}: la propiedad no está en la plantilla de IFC4')
                continue
            if es_qto:
                if QTIPO.get(pt.TemplateType) != p.is_a():
                    mal(f'{nombre}.{p.Name}: es {p.is_a()} y la plantilla pide {QTIPO.get(pt.TemplateType)}')
                continue
            if FORMA.get(pt.TemplateType) != p.is_a():
                mal(f'{nombre}.{p.Name}: es {p.is_a()} y la plantilla pide {FORMA.get(pt.TemplateType)}')
            for v in tipos(p):
                if pt.PrimaryMeasureType and v.is_a() != pt.PrimaryMeasureType:
                    mal(f'{nombre}.{p.Name}: tipo {v.is_a()} y la plantilla pide {pt.PrimaryMeasureType}')
            if p.is_a('IfcPropertyEnumeratedValue') and pt.Enumerators:
                validos = {x.wrappedValue for x in pt.Enumerators.EnumerationValues}
                for v in p.EnumerationValues or []:
                    if v.wrappedValue not in validos:
                        mal(f'{nombre}.{p.Name}: «{v.wrappedValue}» no está en {pt.Enumerators.Name}')
    return {'conjuntos_revisados': n_conj, 'propiedades_revisadas': n_props, 'problemas': len(problemas),
            'detalle': [f'{k} ({v} veces)' for k, v in sorted(problemas.items())][:40]}


def cuatro_d(f, M, E, J):
    """Cada tarea con elementos en este archivo los tiene como SALIDAS (IfcRelAssignsToProduct, lo que leen los visores
    4D) y ninguno como entrada; los elementos de cada fase en el IFC son los del JSON (sin los espacios)."""
    esperado = {}
    for x in f.by_type('IfcProduct'):
        e = E.get(x.GlobalId)
        if e and e.get('fase') and e['clase'] != 'IfcSpace':
            esperado[e['fase']] = esperado.get(e['fase'], 0) + 1
        j = J.get(x.GlobalId)
        if j:
            esperado[j['fase']] = esperado.get(j['fase'], 0) + 1
    filas, err = [], 0
    for task in f.by_type('IfcTask'):
        sal = ifcopenshell.util.sequence.get_task_outputs(task)
        ent = ifcopenshell.util.sequence.get_task_inputs(task)
        n_esp = esperado.get(task.Identification, 0)
        ok = len(sal) == n_esp and not ent and (n_esp == 0 or len(sal) > 0)
        err += 0 if ok else 1
        filas.append({'tarea': task.Identification, 'tipo': task.PredefinedType, 'salidas': len(sal), 'entradas': len(ent),
                      'json': n_esp, 'igual': ok})
    sin_salida = [x['tarea'] for x in filas if x['json'] and not x['salidas']]
    return {'tareas': len(filas), 'con_salidas': sum(1 for x in filas if x['salidas']), 'sin_salida_y_con_elementos': sin_salida,
            'errores': err, 'por_tarea': sorted(filas, key=lambda x: x['tarea'])}


def cinco_d(f, M):
    """Total de cada IfcCostItem (ifcopenshell.util.cost: valores × cantidad) frente a comparacion_presupuesto del JSON:
    con cantidad del modelo, valor unitario × cantidad del modelo; sin ella, el valor del presupuesto; en los indirectos,
    el valor del presupuesto o, fuera de él, la suma de las unidades enlazadas."""
    filas = {x['item']: x for x in M['comparacion_presupuesto']}
    cs = f.by_type('IfcCostSchedule')
    raices = ifcopenshell.util.cost.get_root_cost_items(cs[0]) if cs else []
    out, err = [], 0
    for ci in f.by_type('IfcCostItem'):
        fila = filas.get(ci.Identification)
        valor = sum(ifcopenshell.util.cost.calculate_applied_value(ci, cv) for cv in ci.CostValues or [])
        q = ifcopenshell.util.cost.get_total_quantity(ci)
        total = valor * (1.0 if q is None else q)
        if fila is None:
            esperado = None
        elif fila['capitulo'] == 'indirectos':
            esperado = fila['presupuesto_valor'] if fila['presupuesto_valor'] is not None else fila['bim_valor']
        elif fila['bim_cantidad'] is not None:
            esperado = fila['valor_unitario'] * fila['bim_cantidad']
        else:
            esperado = fila['presupuesto_valor']
        ok = esperado is not None and abs(total - esperado) <= max(1.0, 1e-6 * abs(esperado)) and bool(ci.CostValues)
        err += 0 if ok else 1
        out.append({'item': ci.Identification, 'total_ifc': r(total, 0), 'esperado': r(esperado, 0) if esperado is not None else None,
                    'cantidad_ifc': r(q, 3) if q is not None else None, 'igual': ok})
    en_cronograma = len(raices) == len(out)
    return {'partidas': len(out), 'en_el_presupuesto_ifc': len(raices), 'errores': err + (0 if en_cronograma else 1),
            'total_ifc': r(sum(x['total_ifc'] for x in out), 0), 'distintas': [x for x in out if not x['igual']][:20],
            'partidas_detalle': sorted(out, key=lambda x: x['item'])}


def main():
    M = json.loads(ENTRADA.read_text(encoding='utf-8'))
    nombres_mat = {k: v['nombre'] for k, v in M['materiales'].items()}
    E = {e['guid']: e for e in M['elementos']}
    J = {j['guid']: j for j in M['refuerzo']}
    st = ifcopenshell.geom.settings()
    st.set('use-world-coords', True)
    salida = {'id': 'validacion_ifc', 'generado_por': 'scripts/bim/validar_ifc.py',
              'herramienta': f'IfcOpenShell {ifcopenshell.version}', 'modelo': rel(ENTRADA),
              'insumos_sha1': {rel(ENTRADA): sha1(ENTRADA), **{rel(p): sha1(p) for p in IFC if p.exists()}}, 'archivos': []}
    todos_guid = {}
    errores_tot = 0
    for ruta in IFC:
        if not ruta.exists():
            continue
        f = ifcopenshell.open(str(ruta))
        res = {'archivo': rel(ruta), 'mb': r(ruta.stat().st_size / 1e6, 2), 'esquema': f.schema,
               'entidades': len(list(f))}
        res['validacion_esquema'] = validar_esquema(f)
        errores_tot += res['validacion_esquema']['errores']
        gs, malos = guids(f)
        dup = sorted({g for g in gs if gs.count(g) > 1}) if len(set(gs)) != len(gs) else []
        res['globalid'] = {'total': len(gs), 'unicos': len(set(gs)), 'repetidos': len(dup), 'formato_invalido': len(malos)}
        errores_tot += len(dup) + len(malos)
        todos_guid[res['archivo']] = set(gs)
        # ---------------------------------------------------------------------------------------- conteos
        conteos = []
        es_ref = 'refuerzo' in ruta.name
        if not es_ref:
            json_c = {}
            for e in M['elementos']:
                json_c[e['clase']] = json_c.get(e['clase'], 0) + 1
            json_c['IfcOpeningElement'] = sum(1 for e in M['elementos'] if e.get('vano'))
            for c in sorted(json_c):
                n_ifc = len([x for x in f.by_type(c) if x.is_a() == c])
                conteos.append({'clase': c, 'ifc': n_ifc, 'json': json_c[c], 'igual': n_ifc == json_c[c]})
            enlazados = sum(1 for x in f.by_type('IfcProduct') if x.GlobalId in E)
            res['elementos_del_json_en_el_ifc'] = {'ifc': enlazados, 'json': len(M['elementos']), 'igual': enlazados == len(M['elementos'])}
            errores_tot += 0 if enlazados == len(M['elementos']) else 1
        else:
            n_ifc = len(f.by_type('IfcReinforcingBar'))
            conteos.append({'clase': 'IfcReinforcingBar', 'ifc': n_ifc, 'json': len(M['refuerzo']), 'igual': n_ifc == len(M['refuerzo'])})
            hosts = len({j['host'] for j in M['refuerzo']})
            n_ens = len([x for x in f.by_type('IfcElementAssembly') if x.PredefinedType == 'REINFORCEMENT_UNIT'])
            conteos.append({'clase': 'IfcElementAssembly (REINFORCEMENT_UNIT)', 'ifc': n_ens, 'json': hosts, 'igual': n_ens == hosts})
        res['conteos'] = conteos
        errores_tot += sum(0 if c['igual'] else 1 for c in conteos)
        # ------------------------------------------------------------------------------------- cantidades
        if not es_ref:
            v_qto = v_geo = v_json = 0.0
            n_conc = 0
            peor = []
            for x in f.by_type('IfcElement'):
                e = E.get(x.GlobalId)
                if not e or e.get('material') not in CONCRETO or e['clase'] in ('IfcStair', 'IfcElementAssembly'):
                    continue
                if material(x) != nombres_mat[e['material']]:
                    errores_tot += 1
                n_conc += 1
                q = qto(x, 'NetVolume') or qto(x, 'GrossVolume')
                v_qto += q or 0.0
                vj = G.volumen(e['geometria'])
                v_json += vj
                sh = ifcopenshell.geom.create_shape(st, x)
                vg = ifcopenshell.util.shape.get_volume(sh.geometry)
                v_geo += vg
                peor.append((abs(vg - vj), e['id'], vg, vj))
            peor.sort(reverse=True)
            res['concreto'] = {'elementos': n_conc, 'qto_m3': r(v_qto, 2), 'geometria_ifcopenshell_m3': r(v_geo, 2), 'json_m3': r(v_json, 2),
                               'dif_qto_m3': r(v_qto - v_json, 3), 'dif_geometria_m3': r(v_geo - v_json, 3),
                               'mayor_dif_elemento': {'id': peor[0][1], 'ifcopenshell_m3': r(peor[0][2], 4), 'json_m3': r(peor[0][3], 4)} if peor else None,
                               'nota': 'concreto de los elementos con geometría propia (sin contar dos veces escaleras y conjuntos)'}
            if abs(v_geo - v_json) > 0.001 * v_json or abs(v_qto - v_json) > 0.01:
                errores_tot += 1
        else:
            kg = sum(qto(x, 'Weight') or 0.0 for x in f.by_type('IfcReinforcingBar'))
            n = sum(qto(x, 'Count') or 0 for x in f.by_type('IfcReinforcingBar'))
            items = sum(len(x.Representation.Representations[0].Items) for x in f.by_type('IfcReinforcingBar'))
            res['acero'] = {'peso_qto_kg': r(kg, 1), 'json_kg': r(sum(j['kg'] for j in M['refuerzo']), 1), 'barras_qto': int(n),
                            'barras_geometria': items, 'barras_json': M['totales']['barras'],
                            'igual': abs(kg - sum(j['kg'] for j in M['refuerzo'])) < 1.0 and int(n) == M['totales']['barras'] == items}
            errores_tot += 0 if res['acero']['igual'] else 1
        # -------------------------------------------------------------------- muestra de geometrías (cajas)
        muestra = []
        if not es_ref:
            vistos = {}
            for e in M['elementos']:
                c = e['clase']
                if c in ('IfcStair', 'IfcElementAssembly') or vistos.get(c, 0) >= 3:
                    continue
                vistos[c] = vistos.get(c, 0) + 1
                sh = ifcopenshell.geom.create_shape(st, f.by_guid(e['guid']))
                v = np.array(sh.geometry.verts).reshape(-1, 3)
                a, b = G.limites(e['geometria'])
                d = max(float(np.abs(v.min(0) - np.array(a)).max()), float(np.abs(v.max(0) - np.array(b)).max()))
                muestra.append({'id': e['id'], 'clase': c, 'dif_caja_m': r(d, 4)})
        else:
            vistos = {}
            for j in M['refuerzo']:
                if vistos.get(j['rol'], 0) >= 1 or j['n'] > 60:
                    continue
                vistos[j['rol']] = 1
                sh = ifcopenshell.geom.create_shape(st, f.by_guid(j['guid']))
                v = np.array(sh.geometry.verts).reshape(-1, 3)
                pts = np.array([[p[i] + c[i] for i in range(3)] for c in j['copias'] for p in DSP.polilinea(j)])
                a, b = pts.min(0), pts.max(0)
                # la caja de la barra sobresale del eje a lo sumo un radio
                d = max(float(np.abs(v.min(0) - a).max()), float(np.abs(v.max(0) - b).max())) - j['db'] / 2
                muestra.append({'id': j['id'], 'rol': j['rol'], 'dif_caja_m': r(max(d, 0.0), 4)})
        res['plantillas_ifc4'] = plantillas(f)
        errores_tot += res['plantillas_ifc4']['problemas']
        res['cuatro_d'] = cuatro_d(f, M, E, J)
        errores_tot += res['cuatro_d']['errores']
        res['cinco_d'] = cinco_d(f, M)
        errores_tot += res['cinco_d']['errores']
        res['muestra_geometria'] = {'n': len(muestra), 'max_dif_caja_m': max((m_['dif_caja_m'] for m_ in muestra), default=0.0),
                                    'elementos': muestra}
        if res['muestra_geometria']['max_dif_caja_m'] > 0.005:
            errores_tot += 1
        # ------------------------------------------------------------------------------ georreferenciación
        mc = f.by_type('IfcMapConversion')[0]
        crs = mc.TargetCRS
        g = M['georreferenciacion']
        site = f.by_type('IfcSite')[0]

        def dms(v):
            return math.copysign(abs(v[0]) + abs(v[1]) / 60 + abs(v[2]) / 3600 + abs(v[3]) / 3.6e9, v[0] if v[0] else v[1] or v[2] or v[3])
        geo = {'crs': crs.Name, 'datum': crs.GeodeticDatum, 'proyeccion': crs.MapProjection, 'este_m': mc.Eastings, 'norte_m': mc.Northings,
               'altura_m': mc.OrthogonalHeight, 'eje_x': [mc.XAxisAbscissa, mc.XAxisOrdinate], 'escala': mc.Scale,
               'sitio_lat': r(dms(site.RefLatitude), 7), 'sitio_lon': r(dms(site.RefLongitude), 7),
               'igual_al_json': (crs.Name == 'EPSG:9377' and abs(mc.Eastings - g['este_m']) < 1e-3 and abs(mc.Northings - g['norte_m']) < 1e-3
                                 and abs(mc.XAxisAbscissa - g['eje_x_abscisa']) < 1e-9 and abs(mc.XAxisOrdinate - g['eje_x_ordenada']) < 1e-9
                                 and abs(dms(site.RefLatitude) - g['ancla']['lat']) < 1e-6 and abs(dms(site.RefLongitude) - g['ancla']['lon']) < 1e-6)}
        try:
            from pyproj import Transformer
            t = Transformer.from_crs(4326, 9377, always_xy=True)
            E0, N0 = t.transform(g['ancla']['lon'], g['ancla']['lat'])
            lat_e, lon_e = local_a_geo(50.0, 0.0, g['ancla'])
            Ee, Ne = t.transform(lon_e, lat_e)
            ang_proj = math.atan2(Ne - N0, Ee - E0)
            ang_ifc = math.atan2(mc.XAxisOrdinate, mc.XAxisAbscissa)
            geo['pyproj'] = {'este_m': r(E0, 3), 'norte_m': r(N0, 3), 'dif_este_mm': r((mc.Eastings - E0) * 1000, 2),
                             'dif_norte_mm': r((mc.Northings - N0) * 1000, 2), 'dif_giro_microrad': r((ang_ifc - ang_proj) * 1e6, 3)}
            geo['igual_a_proj'] = abs(mc.Eastings - E0) < 0.005 and abs(mc.Northings - N0) < 0.005 and abs(ang_ifc - ang_proj) < 1e-6
            errores_tot += 0 if geo['igual_a_proj'] else 1
        except ImportError:
            geo['pyproj'] = 'no disponible en el venv: solo se compara con el JSON'
        errores_tot += 0 if geo['igual_al_json'] else 1
        res['georreferenciacion'] = geo
        salida['archivos'].append(res)
    # ------------------------------------------------------------------------------------------- federación
    if len(todos_guid) == 2:
        a, b = list(todos_guid.values())
        comunes = a & b
        esperados = {M['niveles'][i]['guid'] for i in range(len(M['niveles']))}
        esperados |= {f_['guid'] for f_ in M['cronograma']['fases']}
        from comun import guid as G_
        esperados |= {G_('proyecto|torre_hospital'), G_('sitio|torre_hospital'), G_('edificio|torre_hospital'), G_('4d|programa'),
                      G_('5d|presupuesto'), G_('rel|proyecto-sitio'), G_('rel|sitio-edificio'), G_('rel|edificio-niveles'),
                      G_('rel|4d|programa-tareas')}
        inesperados = sorted(comunes - esperados)
        salida['federacion'] = {'guid_compartidos': len(comunes), 'esperados': len(esperados), 'faltan': len(esperados - comunes),
                                'colisiones_inesperadas': len(inesperados), 'ejemplos': inesperados[:5],
                                'nota': 'los dos archivos comparten proyecto, sitio, edificio, niveles, fases y programa; nada más'}
        errores_tot += len(inesperados) + len(esperados - comunes)
    salida['errores'] = errores_tot
    salida['resultado'] = 'sin errores' if errores_tot == 0 else f'{errores_tot} errores'
    escribir_json(SALIDA, salida)
    print(f'{rel(SALIDA)}: {salida["resultado"]}')
    for a in salida['archivos']:
        print(f'  {a["archivo"]}: {a["mb"]} MB, {a["entidades"]} entidades, esquema {a["validacion_esquema"]["errores"]} errores '
              f'(EXPRESS: {"sí" if a["validacion_esquema"]["reglas_express"] else "no"}), GlobalId {a["globalid"]}')
        if 'concreto' in a:
            print(f'    concreto: {a["concreto"]}')
        if 'acero' in a:
            print(f'    acero: {a["acero"]}')
        print(f'    georreferenciación: {a["georreferenciacion"].get("pyproj")}')
        pt = a['plantillas_ifc4']
        print(f'    plantillas IFC4: {pt["conjuntos_revisados"]} conjuntos, {pt["propiedades_revisadas"]} propiedades, {pt["problemas"]} problemas')
        for d in pt['detalle']:
            print(f'      - {d}')
        c4 = a['cuatro_d']
        print(f'    4D: {c4["tareas"]} tareas, {c4["con_salidas"]} con salidas, errores {c4["errores"]}')
        c5 = a['cinco_d']
        print(f'    5D: {c5["partidas"]} partidas ({c5["en_el_presupuesto_ifc"]} en el IfcCostSchedule), total {c5["total_ifc"]:,.0f}, errores {c5["errores"]}')
        for d in c5['distintas']:
            print(f'      - {d}')
    sys.exit(0 if errores_tot == 0 else 1)


if __name__ == '__main__':
    main()
