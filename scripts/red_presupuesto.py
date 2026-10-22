# Presupuesto de la red de distribución propuesta (media tensión 13,2 kV aérea + fibra óptica) por capítulos ("por mayores")
# e ítems ("por menores"), y costo de cada tramo. Usa las distancias por la vía (data/red/distancias.json, de
# scripts/geo/red_distancias.py) y los precios y APU verificados (data/red/precios_unitarios.json, apu_red.json, parametros.json).
# Salida: data/red/presupuesto_red.json     Uso: python3 scripts/red_presupuesto.py
#
# Reglas (data/red/parametros.json → reglas_presupuesto_por_tramo): MT = km urbanos × APU-06U + km rurales × APU-06R (los
# ítems salen de los componentes de cada APU escalados a los km reales); un transformador APU-08 por sede según su carga;
# una acometida con medidor bidireccional (APU-11) por sede; fibra ADSS sobre los mismos postes (APU-09) con su conexión por
# sede (APU-13) y el nodo del CCED (APU-14); preliminares por km (topografía, RETIE, y en lo rural servidumbre y poda);
# ingeniería 4 %, PMA/PMT/SST 1,5 % del costo directo e interventoría 8 % sobre la obra. Precisión clase 4 de AACE (−30 % / +50 %).
import json, math, os

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
J = lambda p: json.load(open(os.path.join(R, p), encoding='utf-8'))
dist, pu, apus, par = J('data/red/distancias.json'), J('data/red/precios_unitarios.json'), J('data/red/apu_red.json'), J('data/red/parametros.json')
mr = J('data/microrred.json')
P = {i['codigo']: i for i in pu['items']}
A = {a['codigo']: a for a in apus['apus']}
precio = lambda c: P[c]['precio_cop_2026']
URBANO_M = 1100          # los tramos a menos de 1,1 km del centro del casco urbano se cuentan como urbanos
ind = par['indirectos']
f_dir = 1 + ind['AIU']['total'] + ind['AIU']['utilidad'] * ind['IVA_sobre_utilidad']   # precio con AIU / costo directo

# --- km urbanos y rurales de red nueva por tramo
def partir(t):
    ru = t['ruta']; urb = rur = 0.0
    for (x0, y0), (x1, y1) in zip(ru, ru[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if math.hypot((x0 + x1) / 2, (y0 + y1) / 2) < URBANO_M: urb += L
        else: rur += L
    tot = (urb + rur) or 1
    return t['km_red_nueva'] * urb / tot, t['km_red_nueva'] * rur / tot
tramos = []
for t in dist['arbol']['tramos']:
    ku, kr = partir(t)
    tramos.append({'de': t['de'], 'a': t['a'], 'km_via': t['km_via'], 'km_red_nueva': t['km_red_nueva'], 'km_urbanos': round(ku, 3), 'km_rurales': round(kr, 3)})
KU, KR = sum(t['km_urbanos'] for t in tramos), sum(t['km_rurales'] for t in tramos)

# --- transformador por sede según la carga del nodo de la microrred (kWh/mes → pico con factor de carga) o por tipo de sede
nodos = {n['id']: n for n in mr['nodos']}
edif = {}
for f in sorted(os.listdir(os.path.join(R, 'data/edificios'))):
    if f.endswith('.json'):
        s = J(f'data/edificios/{f}')
        if s.get('id') and not s.get('reemplazado_por'): edif[s['id']] = s
# reparto del nodo del hospital entre la torre nueva (servicios asistenciales 24 h) y el edificio actual (administrativo)
REPARTO = {'torre_hospital': ('hospital', 0.7), 'hospital': ('hospital', 0.3), 'captacion': ('ptap', None)}
# cargas sin nodo propio: bombas de los pozos (2 × 11–17 kW), planta veredal (2 × 25 HP), oficinas y colegios
FIJO_KVA = {'captacion': 45, 'ptap_veredal': 45, 'ie_megacolegio': 45, 'cic': 45, 'concejo': 25, 'registraduria': 25, 'aguas_aseo_sede': 25, 'casa_cultura': 25}
SIN_TRAFO = {'tanque_elevado': 'solo telemetría; se alimenta en baja tensión desde la planta', 'relleno_parque': 'su subestación de 800 kW y la línea a EPM están en el presupuesto del parque'}
TAM = [(25, 'APU-08-25'), (37.5, 'APU-08-375'), (45, 'APU-08-45'), (75, 'APU-08'), (112.5, 'APU-08-1125')]
def kva(id_):
    if id_ in FIJO_KVA: return FIJO_KVA[id_], 'tamaño por tipo de carga (sin nodo propio en el plan)'
    nid, frac = REPARTO.get(id_, (edif.get(id_, {}).get('nodo_microrred') or id_, 1.0))
    n = nodos.get(nid)
    if not n: return 25, 'oficina pequeña (sin nodo en el plan)'
    kwh = n['kwh_mes'] * (frac or 1.0)
    pico = kwh / 720 / 0.4           # factor de carga 0,4
    k = pico / 0.9                   # factor de potencia 0,9
    return next((t for t, _ in TAM if t >= k), 112.5), f'{fmt(kwh)} kWh/mes → pico ≈ {pico:.0f} kW → {k:.0f} kVA'
fmt = lambda v: f'{v:,.0f}'.replace(',', '.')

sedes = [t['a'] for t in tramos]                    # cada tramo lleva a una sede nueva; la raíz (alcaldía) también
raiz = dist['raiz']
todas = [raiz] + sedes
trafos = []
for s in todas:
    if s in SIN_TRAFO: continue
    k, por = kva(s); cod = dict((t, c) for t, c in TAM)[k]
    trafos.append({'sede': s, 'kva': k, 'codigo': cod, 'por_que': por})
con_acometida = [s for s in todas if s not in SIN_TRAFO]

# --- capítulos
def item(cod, cant, desc=None, unidad=None, vu=None, nota=None):
    vu = precio(cod) if vu is None else vu
    return {'codigo': cod, 'descripcion': desc or P[cod]['descripcion'], 'unidad': unidad or P[cod]['unidad'], 'cantidad': round(cant, 3), 'valor_unitario': round(vu), 'total': round(cant * vu), **({'nota': nota} if nota else {})}
def items_apu(cod, km):
    """Ítems ("por menores") de un APU por km escalados a los km reales, a precio con AIU."""
    a = A[cod]; fa = a['precio_unitario_total'] / a['costo_directo']; out = []
    for c in a.get('componentes_apu', []):
        out.append({'codigo': c['codigo_apu'], 'descripcion': c['descripcion'], 'unidad': c['unidad'], 'cantidad': round(c['cantidad'] * km, 2), 'valor_unitario': round(c['costo_directo_unitario'] * fa), 'total': round(c['subtotal'] * km * fa)})
    for m in a.get('materiales', []):
        out.append({'codigo': m.get('codigo_insumo', ''), 'descripcion': m['descripcion'], 'unidad': m['unidad'], 'cantidad': round(m['cantidad'] * km, 2), 'valor_unitario': round(m['precio_unitario'] * fa), 'total': round(m['subtotal'] * km * fa)})
    for k_ in ('equipo', 'transporte'):
        for m in a.get(k_, []):
            sub = m.get('subtotal', 0)
            out.append({'codigo': m.get('codigo_insumo', k_), 'descripcion': m['descripcion'], 'unidad': m.get('unidad', 'global'), 'cantidad': round(km, 3), 'valor_unitario': round(sub * fa), 'total': round(sub * km * fa)})
    for m in a.get('mano_de_obra', []):
        out.append({'codigo': 'MO', 'descripcion': f"Mano de obra: {m['cuadrilla']} — {m['actividad']}", 'unidad': 'km', 'cantidad': round(km, 3), 'valor_unitario': round(m['subtotal'] * fa), 'total': round(m['subtotal'] * km * fa)})
    return out
caps = []
caps.append({'nombre': 'Red de media tensión aérea 13,2 kV — zona urbana', 'unidad_resumen': f'{KU:.2f} km × APU-06U', 'items': items_apu('APU-06U', KU)})
caps.append({'nombre': 'Red de media tensión aérea 13,2 kV — zona rural', 'unidad_resumen': f'{KR:.2f} km × APU-06R', 'items': items_apu('APU-06R', KR)})
caps.append({'nombre': 'Transformadores de distribución (uno por sede)', 'items': [item(t['codigo'], 1, f"Transformador de {str(t['kva']).replace('.', ',')} kVA instalado — {nombre}", nota=t['por_que']) for t in trafos for nombre in [edif.get(t['sede'], {}).get('nombre', t['sede'])]]})
caps.append({'nombre': 'Acometidas y medición bidireccional', 'items': [item('APU-11', len(con_acometida), nota='Una por sede: acometida trifásica y medidor bidireccional con comunicación')]})
ramas = sum(1 for s in set(t['de'] for t in tramos) if sum(1 for t in tramos if t['de'] == s) > 1)
caps.append({'nombre': 'Protección y maniobra', 'items': [item('CREG-N2EQ35', 1, nota='En la salida del alimentador'), item('CREG-N2EQ29', ramas, nota='Uno por derivación principal del árbol')]})
caps.append({'nombre': 'Fibra óptica sobre los mismos postes (datos al CCED)', 'items': [
    item('APU-09', KU * par['fibra'].get('factor_cable', {}).get('valor', 1.06), nota='ADSS 24 hilos en zona urbana (incluye 6 % de reservas)'),
    item('APU-09-Rural', KR * par['fibra'].get('factor_cable', {}).get('valor', 1.06), nota='ADSS 24 hilos en zona rural'),
    item('APU-13', len(sedes), nota='Conexión GPON de cada sede'), item('APU-14', 1, nota='Nodo central en el CCED (alcaldía)')]})
for c in caps: c['total'] = sum(i['total'] for i in c['items'])
obra = sum(c['total'] for c in caps)
gestion = [item('GES-TOPO', KU + KR), item('GES-RETIE-KM', KU + KR), item('GES-SERV', KR), item('GES-PODA', KR),
           item('GES-RETIE-TR', len(trafos)), item('GES-RETIE-AC', len(con_acometida)), item('GES-EPM', 1)]
caps.insert(0, {'nombre': 'Preliminares, permisos y trámites', 'items': gestion, 'total': sum(i['total'] for i in gestion)})
directo = obra / f_dir
indirectos = [
    {'nombre': 'Ingeniería de detalle', 'base': 'obra', 'porcentaje': ind['ingenieria_detalle']['valor'], 'total': round(obra * ind['ingenieria_detalle']['valor'])},
    {'nombre': 'Plan de manejo ambiental, de tráfico y SST', 'base': 'costo directo', 'porcentaje': ind['pma_pmt_sst']['valor'], 'total': round(directo * ind['pma_pmt_sst']['valor'])},
    {'nombre': 'Interventoría', 'base': 'obra', 'porcentaje': ind['interventoria']['valor'], 'total': round(obra * ind['interventoria']['valor'])},
]
total = obra + caps[0]['total'] + sum(i['total'] for i in indirectos)

# --- costo por tramo (red y fibra del tramo + transformador, acometida y conexión de datos de la sede a la que llega)
cu = lambda c, km: precio(c) * km
tr_de = {t['sede']: precio(t['codigo']) for t in trafos}
for t in tramos:
    ku, kr = t['km_urbanos'], t['km_rurales']
    red = cu('APU-06U', ku) + cu('APU-06R', kr) + (cu('APU-09', ku) + cu('APU-09-Rural', kr)) * 1.06 + (ku + kr) * (precio('GES-TOPO') + precio('GES-RETIE-KM')) + kr * (precio('GES-SERV') + precio('GES-PODA'))
    sede = tr_de.get(t['a'], 0) + (precio('APU-11') if t['a'] not in SIN_TRAFO else 0) + precio('APU-13')
    t['costo_red'] = round(red); t['costo_sede'] = round(sede); t['costo_total'] = round((red + sede) * (1 + ind['ingenieria_detalle']['valor'] + ind['interventoria']['valor']))
    if t['a'] in SIN_TRAFO: t['nota'] = SIN_TRAFO[t['a']]

out = {
    'titulo': 'Presupuesto de la red de distribución propuesta: media tensión 13,2 kV aérea y fibra óptica entre las sedes',
    'moneda': 'pesos colombianos de 2026; precios con AIU (27 % más IVA sobre la utilidad) en la obra',
    'precision': ind.get('precision_presupuesto', 'Clase 4 de AACE: −30 % / +50 %'),
    'raiz': raiz, 'km_urbanos': round(KU, 3), 'km_rurales': round(KR, 3), 'km_total': round(KU + KR, 3),
    'capitulos': caps, 'indirectos': indirectos,
    'totales': {'obra_cop_2026': round(obra), 'preliminares_y_tramites_cop_2026': caps[0]['total'], 'indirectos_cop_2026': sum(i['total'] for i in indirectos),
                'total_cop_2026': round(total), 'rango_cop_2026': [round(total * 0.7), round(total * 1.5)],
                'costo_por_km_red_cop_2026': round((caps[1]['total'] + caps[2]['total']) / max(0.001, KU + KR))},
    'por_tramo': tramos,
    'supuestos': [
        f'Distancias por la vía de OpenStreetMap y árbol de mínima longitud (scripts/geo/red_distancias.py); km urbanos a menos de {URBANO_M / 1000:.1f} km del centro.',
        'La subestación de EPM no se pudo ubicar con certeza: la red arranca en la alcaldía (CCED) y su enlace a la subestación se suma cuando se conozca.',
        'Un transformador nuevo por sede; si una sede ya tiene transformador propio con capacidad, ese ítem se descuenta.',
        'El tramo al parque del relleno tiene su línea y subestación en el presupuesto del parque (docs/12); aquí se cuenta solo si se construye como parte de esta red.',
        'Fibra ADSS sobre los postes de la red nueva (sin arriendo); sobre postes de EPM se paga arriendo (tope de la CRC).',
        'No incluye la generación solar ni las baterías (van en cada sede) ni la red subterránea (unas 7 veces más cara por km).',
    ],
}
json.dump(out, open(os.path.join(R, 'data/red/presupuesto_red.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"Red {KU:.2f} km urbanos + {KR:.2f} km rurales · obra {fmt(obra)} · preliminares {fmt(caps[0]['total'])} · total {fmt(total)} COP 2026")
for c in caps: print(f"  {c['nombre']:<58} {fmt(c['total']):>16}")
for i in indirectos: print(f"  {i['nombre']:<58} {fmt(i['total']):>16}")
