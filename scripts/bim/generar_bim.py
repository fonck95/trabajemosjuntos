"""Modelo BIM federado de la torre del hospital (equipo F, contrato 17.4).

    python3 scripts/bim/generar_bim.py            # escribe data/bim/torre_hospital.bim.json
    python3 scripts/bim/generar_bim.py --verificar  # regenera en memoria y compara con el archivo (rc 1 si difiere)

Insumos (sin modificarlos): plantas de toda la torre (B), estructura con prediseño DMO, cimentación y despiece (A),
inventario de dotación y catálogo 3D (B), presupuesto y APU (T4) y el cronograma de docs/11, sección 10.

Disciplinas: ARQ (espacios, muros, puertas, ventanas, pisos y cielos, cubierta, escaleras), EST (columnas, vigas, losas
nervadas, muros estructurales), CIM (arranques, pilotes, dados y losas de pilotes, vigas de amarre, muros de contención,
contrapiso, fosos y cisternas), REF (refuerzo: juegos de barras en geometría real), FIJO (equipamiento fijo e infraestructura del
inventario) y DOT (dotación). Cada elemento lleva GlobalId IFC determinista, clase IFC4, nivel, geometría, material,
conjuntos de propiedades comunes de IFC y uno propio (tipo de dato, fuente, norma y numeral), cantidades (Qto),
vínculo 5D (ítem de presupuesto.json con su APU y su valor), 4D (fase y fechas del cronograma) y vínculo con el
análisis sísmico (ids de los elementos del modelo de A).

Modelo de prefactibilidad: no reemplaza los diseños firmados."""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import despiece as DSP  # noqa: E402
from comun import (BIM, D, INSUMOS, R, area_poligono, escribir_json, fecha_iso, georreferencia, guid, leer,  # noqa: E402
                   perimetro, r, rel, rp, sha1)

SALIDA = BIM / 'torre_hospital.bim.json'
AVISO = 'Modelo de prefactibilidad: no reemplaza los diseños firmados.'
SOBREANCHO_ARRANQUE_MURO = 0.015  # m por lado: 40 mm a las barras N.º 4 de la cortina contra el relleno (por confirmar)
SOBREANCHO_ARRANQUE = 0.01       # m por lado: recubrimiento de 50 mm contra el relleno (NSR-10 C.7.7.1 b, por confirmar)
RHO_C = 2400.0                     # kg/m³ de concreto reforzado (24 kN/m³ de A, NSR-10 Tabla B.3.2-1, por confirmar)
ALTURA_LIBRE_ESCALERA = 2.05       # m sobre la nariz de los peldaños (NSR-10 K.3, por confirmar)

# =================================================================================================== niveles
def niveles_ifc(pl, est):
    C = est['cimentacion']
    z_pil = min(p['z_punta'] for p in C['pilotes'])
    z_cim = min(d['z_fondo'] for d in C['dados'])
    nom = {n['id']: n['nombre'] for n in pl['niveles']}
    zs = {n['id']: n['z'] for n in pl['niveles']}
    out = [
        {'id': 'CIM-PIL', 'nombre': 'Cimentación profunda: pilotes', 'elevacion': r(z_pil, 3)},
        {'id': 'CIM', 'nombre': 'Cimentación: arranques, dados y losas de pilotes, vigas de amarre, contrapiso, fosos y cisternas',
         'elevacion': r(z_cim, 3)},
        {'id': 'BT', 'nombre': nom.get('BT', 'Bloque técnico'), 'elevacion': zs.get('BT', -1.5)},
        {'id': 'EXT', 'nombre': nom.get('EXT', 'Exteriores'), 'elevacion': zs.get('EXT', 0.0)},
    ]
    for k in ('P1', 'P2', 'P3', 'P4', 'CUB'):
        out.append({'id': k, 'nombre': nom[k], 'elevacion': zs[k]})
    for n in out:
        n['guid'] = guid('nivel|' + n['id'])
    return out


# ================================================================================================= materiales
MATERIALES = {
    'concreto_28': {'nombre': "Concreto de 28 MPa (f'c = 28 MPa)", 'categoria': 'concrete',
                    'fuente': 'presupuesto.json, capítulos 2 y 3; data/sismo/torre_hospital_estructura.json → materiales'},
    'concreto_21': {'nombre': 'Concreto de 21 MPa (contrapiso)', 'categoria': 'concrete', 'fuente': 'presupuesto.json, ítem 2.12'},
    'acero_420': {'nombre': 'Acero de refuerzo NTC 2289 grado 420 (fy = 420 MPa)', 'categoria': 'steel',
                  'fuente': 'NSR-10 C.3.5.3; data/sismo/torre_hospital_estructura.json → refuerzo.convenciones'},
    'malla_electrosoldada': {'nombre': 'Malla electrosoldada (NTC 5806)', 'categoria': 'steel', 'fuente': 'despiece de A'},
    'ladrillo_fachada': {'nombre': 'Ladrillo a la vista de 15 cm con pañete interior', 'categoria': 'brick', 'fuente': 'presupuesto.json, ítem 4.03'},
    'bloque_arcilla': {'nombre': 'Bloque de arcilla N.º 5 con pañete', 'categoria': 'block', 'fuente': 'presupuesto.json, ítem 4.01'},
    'bloque_nucleo': {'nombre': 'Bloque de concreto de 15 cm de celdas llenas con pañete (mampostería del núcleo)', 'categoria': 'block',
                      'fuente': 'torre_hospital_plantas.json → tipos_muro.nucleo_mamposteria'},
    'placa_yeso': {'nombre': 'Placa de yeso RH doble cara sobre perfilería', 'categoria': 'gypsum', 'fuente': 'presupuesto.json, ítem 4.02'},
    'bloque_plomado': {'nombre': 'Bloque con lámina de plomo de ≈ 2 mm', 'categoria': 'block', 'fuente': 'presupuesto.json, ítem 4.07'},
    'parapeto': {'nombre': 'Antepecho de mampostería con baranda', 'categoria': 'block', 'fuente': 'torre_hospital_plantas.json → tipos_muro.parapeto'},
    'cerramiento': {'nombre': 'Malla eslabonada sobre muro bajo', 'categoria': 'steel', 'fuente': 'presupuesto.json, ítem 17.08'},
    'aluminio_vidrio': {'nombre': 'Aluminio con vidrio laminado 4+4 mm', 'categoria': 'glass', 'fuente': 'presupuesto.json, ítem 7.01'},
    'puerta_hospitalaria': {'nombre': 'Puerta hospitalaria (acero o HPL)', 'categoria': 'steel', 'fuente': 'presupuesto.json, ítems 7.02 a 7.07'},
    'vinilo': {'nombre': 'Piso vinílico hospitalario de 2 mm', 'categoria': 'plastic', 'fuente': 'presupuesto.json, ítem 6.01'},
    'porcelanato': {'nombre': 'Porcelanato antideslizante', 'categoria': 'ceramic', 'fuente': 'presupuesto.json, ítem 6.03'},
    'mortero_cuarzo': {'nombre': 'Mortero endurecido con cuarzo', 'categoria': 'concrete', 'fuente': 'presupuesto.json, ítem 6.05'},
    'cielo_fibra': {'nombre': 'Cielo raso registrable en fibra mineral', 'categoria': 'gypsum', 'fuente': 'presupuesto.json, ítem 6.12'},
    'cielo_yeso': {'nombre': 'Cielo raso continuo en placa de yeso RH', 'categoria': 'gypsum', 'fuente': 'presupuesto.json, ítem 6.13'},
    'cubierta': {'nombre': 'Cubierta plana: mortero de pendiente, aislamiento de 50 mm y membrana APP', 'categoria': 'bitumen',
                 'fuente': 'presupuesto.json, ítem 5.01 (APU-14)'},
    'equipo': {'nombre': 'Equipo o mueble (material del fabricante)', 'categoria': 'composite', 'fuente': 'inventario_dotacion.json'},
}
TIPO_MURO_MATERIAL = {'fachada': 'ladrillo_fachada', 'bloque': 'bloque_arcilla', 'liviano': 'placa_yeso', 'plomado': 'bloque_plomado',
                      'nucleo_mamposteria': 'bloque_nucleo', 'parapeto': 'parapeto', 'cerramiento': 'cerramiento'}


# ======================================================================================================= 5D
class Costos:
    """Ítems de presupuesto.json (costo directo) y APU de apu.json; los indirectos de la dotación por grupo."""

    def __init__(self, pres, apu):
        self.items = {}
        for c in pres['capitulos']:
            for it in c['items']:
                self.items[it['codigo']] = {'codigo': it['codigo'], 'capitulo': c['codigo'], 'nombre_capitulo': c.get('capitulo'),
                                            'descripcion': it['descripcion'], 'unidad': it['unidad'], 'cantidad': it['cantidad'],
                                            'valor_unitario': it['valor_unitario_costo_directo'],
                                            'total': it['total_costo_directo'], 'apu': it.get('apu'),
                                            'tipo_precio': it.get('tipo_precio')}
        self.apu = {a['id']: {'id': a['id'], 'item': a['item'], 'unidad': a['unidad'], 'costo_directo': a['costo_directo'],
                              'precio_con_aiu': a.get('precio_unitario_con_aiu')} for a in apu['apus']}
        self.indirectos = {}
        for i, it in enumerate(pres['indirectos']):
            self.indirectos[f'IND-{i + 1:02d}'] = {'codigo': f'IND-{i + 1:02d}', 'grupo': it['grupo'], 'descripcion': it['concepto'],
                                                    'valor': it['valor'], 'proyecto': it.get('proyecto')}
        self.indirectos['CIERRE'] = {'codigo': 'CIERRE', 'grupo': 'Cierre de brechas', 'descripcion': 'Cierre de brechas para la '
                                     'habilitación (dotacion.json, sección aparte)', 'valor': None, 'proyecto': None}
        self.indirectos['LAB-MERCADO'] = {'codigo': 'LAB-MERCADO', 'grupo': 'Laboratorio clínico', 'descripcion': 'Analizadores de '
                                          'laboratorio.json en comodato, programa o compra (valor de mercado)', 'valor': None, 'proyecto': None}
        self.usados = set()

    def ind_por_grupo(self, grupo, contiene=None):
        for k, v in self.indirectos.items():
            if v['grupo'] == grupo and (contiene is None or contiene in v['descripcion']):
                return k
        raise KeyError(grupo)

    def v(self, codigo, cantidad, nota=None):
        """Vínculo 5D de un elemento con un ítem de obra: cantidad en la unidad del ítem y valor con su precio unitario."""
        it = self.items[codigo]
        self.usados.add(codigo)
        vu = it['valor_unitario']
        out = {'item': codigo, 'unidad': it['unidad'], 'cantidad': r(cantidad, 4) if cantidad is not None else None,
               'valor_unitario': vu, 'valor': r(cantidad * vu, 0) if cantidad is not None else None, 'apu': it['apu']}
        if nota:
            out['nota'] = nota
        return out

    def dot(self, codigo_ind, precio, nota=None):
        self.usados.add(codigo_ind)
        out = {'item': codigo_ind, 'unidad': 'un', 'cantidad': 1, 'valor_unitario': precio, 'valor': precio, 'apu': None}
        if nota:
            out['nota'] = nota
        return out


# ======================================================================================================= 4D
def leer_cronograma(ruta):
    """Tabla de la sección 10 de docs/11 (etapa, desde, hasta, meses, proyecto)."""
    txt = Path(ruta).read_text(encoding='utf-8')
    sec = txt.split('## 10. Cronograma', 1)[1].split('\n## ', 1)[0]
    etapas = []
    for linea in sec.splitlines():
        m = re.match(r'\|\s*(\d+)\.\s*(.+?)\s*\|\s*(\d{4}-\d{2})\s*\|\s*(\d{4}-\d{2})\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|', linea)
        if m:
            etapas.append({'etapa': int(m.group(1)), 'nombre': m.group(2), 'inicio': fecha_iso(m.group(3)),
                           'fin': fecha_iso(m.group(4), fin=True), 'meses': int(m.group(5)), 'proyecto': m.group(6)})
    if not etapas:
        raise SystemExit('No se encontró la tabla del cronograma en docs/11, sección 10')
    return etapas


def fases_4d(etapas):
    """Reparto propio (estimación) de las etapas 7 a 11 de docs/11 por piso y disciplina; cada fase cae dentro de su
    etapa (se verifica)."""
    F = []

    def f(id_, nombre, etapa, ini, fin, disc, niveles):
        F.append({'id': id_, 'nombre': nombre, 'etapa': etapa, 'inicio': ini, 'fin': fin, 'disciplina': disc, 'niveles': niveles})
    f('F7-PIL', 'Pilotes preexcavados (tras la demolición del antiguo Centro Vida)', 7, '2028-09-16', '2028-10-31', 'CIM', ['CIM-PIL'])
    f('F7-DAD', 'Dados, losas de pilotes, arranques, vigas de amarre y muros de contención', 7, '2028-11-01', '2028-12-15', 'CIM', ['CIM'])
    f('F7-FOS', 'Fosos, cisternas y contrapiso', 7, '2028-12-01', '2028-12-31', 'CIM', ['CIM'])
    est = [('1', '+4,50', '2028-12-16', '2029-02-15'), ('2', '+8,70', '2029-02-16', '2029-03-31'),
           ('3', '+12,90', '2029-04-01', '2029-05-15'), ('4', '+17,10 (cubierta)', '2029-05-16', '2029-06-30')]
    for k, z, a, b in est:
        f(f'F8-EST{k}', f'Estructura del piso {k}: columnas, muros, escaleras y losa del nivel {z}', 8, a, b, 'EST', [f'P{k}'])
    arq = [('1', '2029-02-16', '2029-03-31'), ('2', '2029-04-01', '2029-05-15'), ('3', '2029-05-16', '2029-06-30'),
           ('4', '2029-07-01', '2029-08-15')]
    for k, a, b in arq:
        f(f'F8-ARQ{k}', f'Mampostería, fachada y ventanas del piso {k}', 8, a, b, 'ARQ', [f'P{k}'])
    f('F8-CUB', 'Cubierta impermeabilizada, casetas y antepechos', 8, '2029-07-01', '2029-08-31', 'ARQ', ['CUB'])
    f('F8-BT', 'Bloque técnico y exteriores en obra gris', 8, '2029-03-01', '2029-06-30', 'ARQ', ['BT', 'EXT'])
    aca = [('1', '2029-05-01', '2029-07-15'), ('2', '2029-07-01', '2029-09-15'), ('3', '2029-09-01', '2029-11-15'),
           ('4', '2029-11-01', '2030-01-15')]
    for k, a, b in aca:
        f(f'F9-ACA{k}', f'Acabados del piso {k}: pisos, cielos rasos y puertas', 9, a, b, 'ARQ', [f'P{k}'])
    fij = [('1', '2029-06-01', '2029-08-15'), ('2', '2029-08-01', '2029-10-15'), ('3', '2029-10-01', '2029-12-15'),
           ('4', '2029-11-15', '2030-01-31')]
    for k, a, b in fij:
        f(f'F9-FIJ{k}', f'Aparatos sanitarios, gases, seguridad y equipamiento fijo del piso {k}', 9, a, b, 'FIJO', [f'P{k}'])
    f('F9-FIJBT', 'Subestación, planta eléctrica, UPS, baterías, bombas y central de gases del bloque técnico', 9, '2029-07-01',
      '2029-10-31', 'FIJO', ['BT', 'EXT'])
    f('F9-FIJCUB', 'Paneles solares, condensadoras y tanques de la cubierta', 9, '2029-09-01', '2029-12-31', 'FIJO', ['CUB'])
    dot = [('1', '2029-08-01', '2029-10-31'), ('2', '2029-10-01', '2029-12-31'), ('3', '2029-11-01', '2030-01-31'),
           ('4', '2029-12-01', '2030-02-28')]
    for k, a, b in dot:
        f(f'F10-DOT{k}', f'Compra e instalación de la dotación del piso {k}', 10, a, b, 'DOT', [f'P{k}'])
    f('F10-DOTBT', 'Dotación del bloque técnico, la cubierta y los exteriores', 10, '2030-01-01', '2030-02-28', 'DOT', ['BT', 'CUB', 'EXT'])
    f('F11-PEM', 'Puesta en marcha, habilitación y traslado de servicios', 11, '2030-02-01', '2030-04-30', None, [])
    E = {e['etapa']: e for e in etapas}
    for x in F:
        e = E[x['etapa']]
        if not (e['inicio'] <= x['inicio'] <= x['fin'] <= e['fin']):
            raise SystemExit(f'La fase {x["id"]} ({x["inicio"]} a {x["fin"]}) se sale de la etapa {x["etapa"]} ({e["inicio"]} a {e["fin"]})')
        x['etapa_nombre'] = e['nombre']
        x['guid'] = guid('fase|' + x['id'])
    return F


def fase_de(disc, nivel, sub=None):
    """sub: 'acabado' para puertas, pisos y cielos (etapa 9); la estructura de un nivel con losa en z = Z[k] es del piso k."""
    if disc == 'CIM':
        return 'F7-PIL' if nivel == 'CIM-PIL' else ('F7-FOS' if sub == 'fosos' else 'F7-DAD')
    if disc in ('EST', 'REF'):
        return f'F8-EST{sub}' if sub else 'F8-EST1'
    if disc == 'ARQ':
        if nivel in ('BT', 'EXT'):
            return 'F8-BT'
        if nivel == 'CUB':
            return 'F8-CUB'
        if sub == 'acabado':
            return f'F9-ACA{nivel[1]}'
        if sub and sub.startswith('est'):
            return f'F8-EST{sub[3:]}'
        return f'F8-ARQ{nivel[1]}'
    if disc == 'FIJO':
        if nivel in ('BT', 'EXT'):
            return 'F9-FIJBT'
        if nivel == 'CUB':
            return 'F9-FIJCUB'
        return f'F9-FIJ{nivel[1]}'
    if disc == 'DOT':
        if nivel in ('BT', 'EXT', 'CUB'):
            return 'F10-DOTBT'
        return f'F10-DOT{nivel[1]}'
    raise ValueError(disc)


# ================================================================================================= geometría
def caja(x0, y0, z0, x1, y1, z1):
    return {'tipo': 'caja', 'min': rp([min(x0, x1), min(y0, y1), min(z0, z1)]), 'max': rp([max(x0, x1), max(y0, y1), max(z0, z1)])}


def prisma(planta, z0, z1, huecos=None):
    g = {'tipo': 'prisma', 'planta': [rp(p) for p in planta], 'z0': r(z0), 'z1': r(z1)}
    if huecos:
        g['huecos'] = [[rp(p) for p in h] for h in huecos]
    return g


def volumen(g):
    t = g['tipo']
    if t == 'caja':
        return (g['max'][0] - g['min'][0]) * (g['max'][1] - g['min'][1]) * (g['max'][2] - g['min'][2])
    if t == 'prisma':
        A = abs(area_poligono(g['planta'])) - sum(abs(area_poligono(h)) for h in g.get('huecos', []))
        return A * (g['z1'] - g['z0'])
    if t == 'cilindro':
        return math.pi * g['radio'] ** 2 * (g['z1'] - g['z0'])
    if t == 'perfil':
        return abs(area_poligono(g['puntos'])) * g['largo']
    if t == 'caja_girada':
        return g['dim'][0] * g['dim'][1] * g['dim'][2]
    if t == 'compuesta':
        return sum(volumen(p) for p in g['partes'])
    raise ValueError(t)


def limites(g):
    """Caja alineada que envuelve la geometría (min, max)."""
    t = g['tipo']
    if t == 'caja':
        return g['min'], g['max']
    if t == 'prisma':
        xs = [p[0] for p in g['planta']]
        ys = [p[1] for p in g['planta']]
        return [min(xs), min(ys), g['z0']], [max(xs), max(ys), g['z1']]
    if t == 'cilindro':
        cx, cy = g['centro']
        return [cx - g['radio'], cy - g['radio'], g['z0']], [cx + g['radio'], cy + g['radio'], g['z1']]
    if t == 'perfil':
        pts = []
        for u, v in g['puntos']:
            for w in (0.0, g['largo']):
                pts.append([g['origen'][i] + g['u'][i] * u + g['v'][i] * v + g['w'][i] * w for i in range(3)])
        return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]
    if t == 'caja_girada':
        cx, cy, z = g['centro']
        w, d, h = g['dim']
        c, s = math.cos(g['rot']), math.sin(g['rot'])
        xs = [cx + c * a - s * b for a in (-w / 2, w / 2) for b in (-d / 2, d / 2)]
        ys = [cy + s * a + c * b for a in (-w / 2, w / 2) for b in (-d / 2, d / 2)]
        return [min(xs), min(ys), z], [max(xs), max(ys), z + h]
    if t == 'compuesta':
        bs = [limites(p) for p in g['partes']]
        return [min(b[0][i] for b in bs) for i in range(3)], [max(b[1][i] for b in bs) for i in range(3)]
    raise ValueError(t)


def solape_rect(a, b):
    """Rectángulos [x0, y0, x1, y1]: solape en x y en y (negativo = separados)."""
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


# ===================================================================================================== modelo
class Modelo:
    def __init__(self):
        self.elementos = []
        self.por_id = {}

    def agregar(self, e):
        if e['id'] in self.por_id:
            raise SystemExit(f'id repetido en el modelo BIM: {e["id"]}')
        e['guid'] = guid('elemento|' + e['id'])
        self.por_id[e['id']] = e
        self.elementos.append(e)
        return e


def elemento(id_, disc, clase, tipo, nombre, nivel, geo, material, atlas, qto=None, psets=None, costo=None, fase=None,
             contenedor=None, analisis=None, **extra):
    e = {'id': id_, 'disciplina': disc, 'clase': clase, 'tipo_predefinido': tipo, 'nombre': nombre, 'nivel': nivel,
         'contenedor': contenedor or nivel, 'geometria': geo, 'material': material, 'psets': psets or {},
         'atlas': atlas, 'qto': qto or {}, 'costo': costo or [], 'fase': fase, 'analisis': analisis}
    e.update(extra)
    return e


def atlas_pset(tipo_dato, fuente, norma=None, numeral=None, nota=None):
    out = {'TipoDato': tipo_dato, 'Fuente': fuente}
    if norma:
        out['Norma'] = norma
    if numeral:
        out['Numeral'] = numeral
    if nota:
        out['Nota'] = nota
    return out


# IFC4 no define cantidades base para IfcStair, IfcElementAssembly ni los equipos: van en un conjunto propio (el prefijo
# Qto_ es reservado de buildingSMART); lo mismo con las propiedades que la plantilla de IFC4 no trae (p. ej. LoadBearing
# de las escaleras, que va en AtlasYondo_Torre como «Portante»)
QTO_PROPIO = 'AtlasYondo_Cantidades'
TD_A = 'cálculo propio (prediseño estructural del equipo A)'
TD_B = 'estimación (anteproyecto ilustrativo del equipo B)'
TD_F = 'cálculo propio del modelo BIM (equipo F) con datos de A y B'
F_EST = 'Prediseño estructural DMO (data/sismo/torre_hospital_estructura.json)'
F_PL = 'Plantas del anteproyecto (data/edificios/torre_hospital_plantas.json)'
F_INV = 'Inventario de dotación (data/proyectos/torre_hospital/inventario_dotacion.json)'
NSR_C = 'NSR-10 Título C (concreto estructural)'


# ======================================================================================= disciplinas, LOD y LOIN
def _loin(geometria, tipo_geo, informacion, documentacion):
    """Nivel de información necesario (ISO 7817-1 / EN 17412-1): geometría, información alfanumérica y documentación,
    cada parte con su tipo de dato («por confirmar» lo que falta)."""
    return {'geometria': {'detalle': geometria, 'tipo_dato': tipo_geo},
            'informacion': [{'dato': d, 'tipo_dato': t} for d, t in informacion],
            'documentacion': [{'documento': d, 'tipo_dato': t} for d, t in documentacion]}


DISCIPLINAS = {
    'ARQ': {'nombre': 'Arquitectura', 'lod_objetivo': '300',
            'estado_actual': 'geometría del anteproyecto ilustrativo (cajas y prismas por objeto); sin planos firmados',
            'contenido': 'espacios, muros, puertas, ventanas, pisos, cielos, cubierta y escaleras',
            'loin': _loin('cajas y prismas por objeto; muros cortados en columnas y muros estructurales; vanos de puertas y ventanas',
                          'estimación (anteproyecto ilustrativo)',
                          [('código, GlobalId y clase IFC4', 'cálculo propio'), ('áreas a ejes y libres, alturas', 'estimación (anteproyecto)'),
                           ('materiales y acabados por tipo de recinto', 'estimación'), ('ítem del presupuesto (5D) y fase de obra (4D)', 'estimación'),
                           ('resistencia al fuego de muros y puertas', 'por confirmar')],
                          [('plantas del anteproyecto', 'estimación'), ('planos arquitectónicos firmados', 'por confirmar')])},
    'EST': {'nombre': 'Estructura', 'lod_objetivo': '350',
            'estado_actual': 'geometría tipo 350 sobre un prediseño DMO sin firmar; no apto para construcción',
            'contenido': 'columnas, vigas, losas nervadas y muros estructurales',
            'loin': _loin('secciones del prediseño: columnas de piso a piso, vigas entre caras, losas nervadas con nervios y riostra, muros',
                          'cálculo propio (prediseño)',
                          [('código, GlobalId y clase IFC4', 'cálculo propio'), ('materiales, secciones y recubrimientos', 'cálculo propio (prediseño)'),
                           ('vínculo con el modelo sísmico (D/C, rótulas, deriva)', 'cálculo propio'),
                           ('memoria de cálculo revisada', 'por confirmar')],
                          [('prediseño estructural DMO', 'cálculo propio'), ('diseño estructural y planos firmados', 'por confirmar')])},
    'CIM': {'nombre': 'Cimentación', 'lod_objetivo': '350',
            'estado_actual': 'geometría tipo 350 sobre un prediseño con capacidad de pilotes estimada; falta el estudio geotécnico',
            'contenido': 'arranques, pilotes, dados, losas de pilotes, vigas de amarre, muros de contención, contrapiso, fosos y cisternas',
            'loin': _loin('pilotes, dados, vigas de amarre, muros de contención, contrapiso, fosos y cisternas con sus cotas', 'cálculo propio (prediseño)',
                          [('código, GlobalId y clase IFC4', 'cálculo propio'), ('cargas de servicio y reacciones por pilote', 'cálculo propio'),
                           ('capacidad de los pilotes', 'estimación (la fija el estudio geotécnico)'),
                           ('parámetros del suelo y nivel freático', 'por confirmar')],
                          [('prediseño de la cimentación', 'cálculo propio'), ('estudio geotécnico', 'por confirmar'),
                           ('planos de cimentación firmados', 'por confirmar')])},
    'REF': {'nombre': 'Refuerzo', 'lod_objetivo': '400',
            'estado_actual': 'geometría de barras tipo 400 sobre un prediseño sin firmar; no apto para fabricación',
            'contenido': 'juegos de barras con su geometría (despiece del prediseño)',
            'loin': _loin('cada barra con su eje, dobleces y ganchos; un juego por grupo de barras iguales', 'cálculo propio (despiece del prediseño)',
                          [('designación (N.º), longitud, número y peso de las barras', 'cálculo propio'),
                           ('zonas confinadas, traslapos y anclajes', 'cálculo propio (despiece del prediseño)'),
                           ('cartilla de despiece revisada para figurar y cortar', 'por confirmar')],
                          [('despiece del prediseño', 'cálculo propio'), ('planos de refuerzo y cartilla firmados', 'por confirmar')])},
    'FIJO': {'nombre': 'Equipamiento fijo e infraestructura', 'lod_objetivo': '200',
             'estado_actual': 'cajas con la medida del catálogo, sin fabricante elegido',
             'contenido': 'aparatos sanitarios, gases, seguridad, energía y equipos fijos',
             'loin': _loin('una caja por equipo con la medida del catálogo', 'estimación (catálogo 3D)',
                           [('clase IFC4, ubicación y recinto', 'estimación (anteproyecto)'), ('ítem del presupuesto (5D)', 'estimación'),
                            ('marca, modelo, potencia y fichas técnicas', 'por confirmar')],
                           [('inventario de dotación e infraestructura', 'estimación'), ('diseños de redes firmados', 'por confirmar')])},
    'DOT': {'nombre': 'Dotación', 'lod_objetivo': '200-300',
            'estado_actual': 'cajas con la medida del catálogo, sin marca ni modelo (se completan al comprar)',
            'contenido': 'equipos biomédicos, mobiliario y laboratorio',
            'loin': _loin('una caja por unidad (en la vista, el modelo 3D del catálogo)', 'estimación (catálogo 3D)',
                          [('clase de riesgo y registro INVIMA', 'dato del inventario (revisión de la norma)'),
                           ('precio de referencia', 'estimación o referencia de mercado ajustada'),
                           ('marca, modelo, serie y hoja de vida', 'por confirmar (al comprar)')],
                          [('inventario de dotación', 'estimación'), ('fichas técnicas y registros sanitarios', 'por confirmar')])},
}


# ============================================================================================================ ARQ
def tipo_piso(amb):
    a = amb.lower()
    if any(k in a for k in ('baño', 'bano', 'sanitari', 'ducha', 'aseo', 'vestier', 'lavado', 'esteriliz')):
        return '6.03', 'porcelanato'
    if any(k in a for k in ('cuarto técnico', 'cuarto tecnico', 'eléctric', 'electric', 'bombas', 'residuos', 'subestaci', 'planta')):
        return '6.05', 'mortero_cuarzo'
    if any(k in a for k in ('sala de partos', 'parto', 'procedimientos')):
        return '6.02', 'vinilo'
    return '6.01', 'vinilo'


def tipo_cielo(amb):
    a = amb.lower()
    if any(k in a for k in ('baño', 'bano', 'sanitari', 'ducha', 'aseo', 'esteriliz', 'laboratorio', 'parto', 'lavado')):
        return '6.13', 'cielo_yeso'
    return '6.12', 'cielo_fibra'


def puerta_item(p, tipo_muro):
    cat, tipo, ancho = p.get('categoria'), p.get('tipo'), p['ancho']
    if tipo_muro == 'cerramiento':
        return '17.09', 'portón del cerramiento (ítem global)'
    if tipo_muro == 'plomado':
        return '7.06', 'puerta plomada de rayos X (ítem global)'
    if cat == 'evacuacion':
        return '7.05', None
    if tipo == 'automatica':
        return '7.07', None
    if cat == 'ascensor':
        return '14.01', 'puerta de cabina incluida en el ascensor'
    if cat == 'montacargas':
        return '14.02', 'puerta incluida en el montacargas'
    if ancho >= 1.15:
        return '7.02', None
    if ancho >= 0.95:
        return '7.03', None
    return '7.04', None


GLOBALES = {'7.06', '17.09', '14.01', '14.02', '17.12'}


class Estructura:
    """Índices de la estructura de A para la arquitectura y el despiece."""

    def __init__(self, est):
        self.est = est
        ref = est['refuerzo']
        self.Z = sorted({0.0} | {c['z1'] for c in ref['columnas']})
        self.columnas = {c['id']: c for c in ref['columnas']}
        self.vigas = ref['vigas']
        self.losas = ref['losas']
        self.muros = ref['muros']
        self.arms = {}
        self.portico_de = {}
        self.analisis_col = {}
        for P in est['bloques'][0]['porticos']:
            for e in P['elementos']:
                if e['tipo'] == 'viga':
                    self.arms[e['id']] = e.get('brazo_rigido_m', [0.0, 0.0])
                    self.portico_de[e['id']] = P
                elif e['tipo'] == 'columna':
                    self.analisis_col.setdefault(e['fisico'], []).append(e['id'])
                elif e['tipo'] == 'muro_concreto':
                    self.portico_de[e['id']] = P

    def nivel_de_z(self, z):
        return {0.0: 'P1', 4.5: 'P2', 8.7: 'P3', 12.9: 'P4', 17.1: 'CUB'}[round(z, 2)]

    def columna_en(self, x, y, k):
        for c in self.columnas.values():
            if c['nivel'] == k and abs(c['x'] - x) < 1e-6 and abs(c['y'] - y) < 1e-6:
                return c
        return None


def _altura_muro_planta(n, mu, tipos_muro):
    if tipos_muro[mu['tipo']].get('altura') == 'entrepiso' and isinstance(n['piso'], int):
        return n['altura_entrepiso_m']
    return mu.get('altura') or 0.0


def _rect_muro_planta(mu):
    a, b, e_ = mu['a'], mu['b'], mu['espesor']
    if abs(a[1] - b[1]) < 1e-9:
        u0, u1 = sorted([a[0], b[0]])
        return [u0, a[1] - e_ / 2, u1, a[1] + e_ / 2]
    u0, u1 = sorted([a[1], b[1]])
    return [a[0] - e_ / 2, u0, a[0] + e_ / 2, u1]


def _dentro_poligono(p, pol):
    x, y = p
    c = False
    for i in range(len(pol)):
        a, b = pol[i], pol[i - 1]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


NIVEL_CONTEXTO = 'EXT'
COBERTURA_CONTEXTO = 0.90          # fracción de la planta cubierta por elementos de otro nivel para tratarlo como contexto


def contexto_exterior(pl, S):
    """El nivel EXT de las plantas repite, para el recorrido, el perímetro de la torre (fachada, puertas de acceso y huella)
    que ya modelan el piso 1 y el bloque técnico. No se modela dos veces: se omiten del BIM (sin clase IFC, sin 5D) los
    muros de EXT cuya planta cubren en ≥ 90 % muros, columnas o muros estructurales de otro nivel que ocupan al menos la
    mitad de su altura, las puertas alojadas en esos muros y los recintos cuya área cubren en ≥ 90 % recintos de otro
    nivel. Devuelve {id: {'clase', 'motivo', 'coincide_con'}}."""
    tipos_muro = pl['tipos_muro']
    niv = {n['id']: n for n in pl['niveles']}
    ext = niv.get(NIVEL_CONTEXTO)
    if not ext:
        return {}
    otros = []                                      # (rect, z0, z1, id)
    for n in pl['niveles']:
        if n['id'] == NIVEL_CONTEXTO:
            continue
        for mu in n['muros']:
            if mu['tipo'] == 'abierto':
                continue
            otros.append((_rect_muro_planta(mu), n['z'], n['z'] + _altura_muro_planta(n, mu, tipos_muro), mu['id']))
    for c in S.columnas.values():
        otros.append(([c['x'] - c['b'] / 2, c['y'] - c['h'] / 2, c['x'] + c['b'] / 2, c['y'] + c['h'] / 2], c['z0'], c['z1'], c['id']))
    for m in S.muros:
        for rr in m['planta']:
            otros.append((list(rr), m['z0'], m['z1'], m['id']))
    out = {}
    for mu in ext['muros']:
        if mu['tipo'] == 'abierto':
            continue
        R0 = _rect_muro_planta(mu)
        z0, z1 = ext['z'], ext['z'] + _altura_muro_planta(ext, mu, tipos_muro)
        cub = [(o[0], o[3]) for o in otros if min(z1, o[2]) - max(z0, o[1]) >= 0.5 * (z1 - z0) - 1e-9
               and solape_rect(R0, o[0])[0] > 1e-6 and solape_rect(R0, o[0])[1] > 1e-6]
        if not cub:
            continue
        A0 = (R0[2] - R0[0]) * (R0[3] - R0[1])
        libre = sum((q[2] - q[0]) * (q[3] - q[1]) for q in restar_rects(R0, [c_[0] for c_ in cub]))
        f = 1 - libre / A0 if A0 > 0 else 0.0
        if f >= COBERTURA_CONTEXTO:
            ids = sorted({c_[1] for c_ in cub}, key=lambda i: (-max(solape_rect(R0, next(o[0] for o in cub if o[1] == i))), i))
            out[mu['id']] = {'clase': 'IfcWall', 'motivo': f'muro de {mu["tipo"]} del recorrido exterior: su planta la cubren en un '
                             f'{100 * f:.0f} % muros y estructura de otro nivel', 'coincide_con': ids[:6]}
    for p in ext['puertas']:
        if p['muro'] in out:
            esp = p.get('espejo_de') or {}
            out[p['id']] = {'clase': 'IfcDoor', 'motivo': 'puerta del recorrido exterior en un muro que ya modela otro nivel',
                            'coincide_con': [esp['puerta']] if esp.get('puerta') else []}
    h_esp = 2.5
    for rc in ext['recintos']:
        pol = rc['poligono']
        pols = [(q['poligono'], q['id']) for n in pl['niveles'] if n['id'] != NIVEL_CONTEXTO
                and min(ext['z'] + h_esp, n['z'] + (n.get('altura_entrepiso_m') or h_esp)) - max(ext['z'], n['z']) >= 0.5 * h_esp
                for q in n['recintos']]
        xs, ys = [q[0] for q in pol], [q[1] for q in pol]
        paso = 0.25
        t = c = 0
        ids = set()
        nx, ny = int((max(xs) - min(xs)) / paso) + 1, int((max(ys) - min(ys)) / paso) + 1
        for i in range(nx):
            for j in range(ny):
                q = (min(xs) + (i + 0.5) * paso, min(ys) + (j + 0.5) * paso)
                if not _dentro_poligono(q, pol):
                    continue
                t += 1
                for pg, pid in pols:
                    if _dentro_poligono(q, pg):
                        c += 1
                        ids.add(pid)
                        break
        if t and c / t >= COBERTURA_CONTEXTO:
            out[rc['id']] = {'clase': 'IfcSpace', 'motivo': f'recinto del recorrido exterior que es la huella de la torre: lo cubren en un '
                             f'{100 * c / t:.0f} % los recintos de otro nivel', 'coincide_con': sorted(ids)[:6] + (['…'] if len(ids) > 6 else [])}
    return out


def arquitectura(M, pl, S, cost, cat_niveles, bases=None):
    """Espacios, muros (cortados en columnas y muros estructurales), puertas, ventanas, pisos, cielos rasos, cubierta,
    bloque técnico y escaleras. Lo que el nivel EXT repite de otro nivel (contexto del recorrido) no se modela."""
    tipos_muro = pl['tipos_muro']
    contexto = contexto_exterior(pl, S)
    vigas_por_z, losas_por_z = {}, {}
    for v in S.vigas:
        z = v['xyz_i'][2]
        a, b = v['_caja']
        vigas_por_z.setdefault(round(z, 2), []).append((a, b, v))
    for p in S.losas:
        losas_por_z.setdefault(round(p['z'], 2), []).append(p)
    # columnas, muros estructurales y sus arranques (con su rango de cotas): los muros de cualquier nivel se cortan en los
    # que ocupan parte de su altura (también los del bloque técnico y los exteriores, que no son de un piso de la torre)
    obst = []
    for c in S.columnas.values():
        obst.append(([c['x'] - c['b'] / 2, c['y'] - c['h'] / 2, c['x'] + c['b'] / 2, c['y'] + c['h'] / 2], c['id'], c['z0'], c['z1']))
    for m in S.muros:
        for rr in m['_rects']:
            obst.append((rr, m['id'], m['z0'], m['z1']))
    for linea, b_ in (bases or {}).items():
        if b_['tipo'] == 'columna':
            c = S.columnas[f'{linea}-1']
            o = SOBREANCHO_ARRANQUE
            obst.append(([c['x'] - c['b'] / 2 - o, c['y'] - c['h'] / 2 - o, c['x'] + c['b'] / 2 + o, c['y'] + c['h'] / 2 + o],
                         b_['host_arranque'], b_['z_tope'], 0.0))
        else:
            ms = [m for m in S.muros if m['muro'] == linea and m['nivel'] == 1][0]
            for rr in rects_arranque_muro(ms, S):
                obst.append((rr, b_['host_arranque'], b_['z_tope'], 0.0))
    huecos_estr = {}
    resumen = {'muros_cortados': 0, 'muros_nucleo_a_est': 0, 'contexto': contexto}
    for n in pl['niveles']:
        nid, zn = n['id'], n['z']
        k = n['piso'] if isinstance(n['piso'], int) else None
        hl = n.get('altura_libre_m') or 2.5
        es_ext = nid in ('EXT', 'CUB')
        recintos = {rc['id']: rc for rc in n['recintos']}
        # ---------------- espacios
        for rc in n['recintos']:
            if rc['id'] in contexto:
                continue
            pol = rc['poligono']
            h = 2.5 if nid in ('EXT', 'CUB') else hl
            A = abs(area_poligono(pol))
            qto = {'Qto_SpaceBaseQuantities': {'Height': r(h, 3), 'GrossFloorArea': r(rc.get('area_ejes_m2') or A, 3),
                                               'NetFloorArea': r(rc.get('area_libre_m2') or A, 3),
                                               'GrossPerimeter': r(perimetro(pol), 3), 'GrossVolume': r(A * h, 3)}}
            ps = {'Pset_SpaceCommon': {'Reference': rc['ambiente'][:120], 'IsExternal': es_ext,
                                       'GrossPlannedArea': rc.get('area_programa_m2'),
                                       'PubliclyAccessible': rc.get('zona_acceso') == 'no_restringido'}}
            at = atlas_pset(TD_B, F_PL, 'Res. 1633 de 2025 (áreas mínimas) y Res. 3100 de 2019' if rc.get('minimo_1633') else None,
                            None, '; '.join(t_ for t_ in (f'servicio: {rc["servicio_programa"]}' if rc.get('servicio_programa') else '',
                                                           f'grupo de la Res. 1633: {rc["grupo_1633"]}' if rc.get('grupo_1633') else '') if t_) or None)
            M.agregar(elemento(rc['id'], 'ARQ', 'IfcSpace', 'INTERNAL' if not es_ext else 'EXTERNAL',
                               rc['ambiente'], nid, prisma(pol, zn, zn + h), None, at, qto, ps, [],
                               fase_de('ARQ', nid, 'acabado') if nid.startswith('P') else fase_de('ARQ', nid),
                               servicio=rc.get('servicio_programa'), area_minima_1633=rc.get('minimo_1633'),
                               area_programa=rc.get('area_programa_m2')))
        # ---------------- muros
        muros_seg = {}
        for mu in n['muros']:
            t = mu['tipo']
            if t == 'abierto':
                continue
            if t == 'nucleo':
                resumen['muros_nucleo_a_est'] += 1
                continue
            if mu['id'] in contexto:
                continue
            a, b = mu['a'], mu['b']
            eje = 'x' if abs(a[1] - b[1]) < 1e-9 else 'y'
            c = a[1] if eje == 'x' else a[0]
            u0, u1 = sorted([a[0], b[0]] if eje == 'x' else [a[1], b[1]])
            e_ = mu['espesor']
            rect = [u0, c - e_ / 2, u1, c + e_ / 2] if eje == 'x' else [c - e_ / 2, u0, c + e_ / 2, u1]
            # cortes en columnas y muros estructurales (y sus arranques) que ocupan parte de la altura del muro
            alt_n = n['altura_entrepiso_m'] if tipos_muro[t]['altura'] == 'entrepiso' and k else mu['altura']
            tramos = [(u0, u1)]
            for (orr, oid, oz0, oz1) in obst:
                if min(zn + alt_n, oz1) - max(zn, oz0) <= 0.05:
                    continue
                sx, sy = solape_rect(rect, orr)
                if sx > 0.001 and sy > 0.001:
                    ca, cb = (orr[0], orr[2]) if eje == 'x' else (orr[1], orr[3])
                    nuevo = []
                    for s0, s1 in tramos:
                        if cb <= s0 or ca >= s1:
                            nuevo.append((s0, s1))
                            continue
                        if ca > s0:
                            nuevo.append((s0, ca))
                        if cb < s1:
                            nuevo.append((cb, s1))
                    tramos = nuevo
            tramos = [q for q in tramos if q[1] - q[0] > 0.02]
            if len(tramos) != 1 or abs(tramos[0][0] - u0) > 1e-9 or abs(tramos[0][1] - u1) > 1e-9:
                resumen['muros_cortados'] += 1
            for ti, (s0, s1) in enumerate(tramos):
                wid = mu['id'] if len(tramos) == 1 else f'{mu["id"]}-{ti + 1}'
                # altura
                alt = tipos_muro[t]['altura']
                if alt == 'entrepiso' and k:
                    z_sig = zn + n['altura_entrepiso_m']
                    techo = z_sig
                    q_rect = [s0, c - e_ / 2, s1, c + e_ / 2] if eje == 'x' else [c - e_ / 2, s0, c + e_ / 2, s1]
                    for (va, vb, v) in vigas_por_z.get(round(z_sig, 2), []):
                        sx, sy = solape_rect(q_rect, [va[0], va[1], vb[0], vb[1]])
                        if sx > 0.001 and sy > 0.001:
                            techo = min(techo, va[2])
                    if techo == z_sig:
                        um = (s0 + s1) / 2
                        px, py = (um, c) if eje == 'x' else (c, um)
                        for p in losas_por_z.get(round(z_sig, 2), []):
                            if p['x0'] - 1e-6 <= px <= p['x1'] + 1e-6 and p['y0'] - 1e-6 <= py <= p['y1'] + 1e-6:
                                techo = min(techo, z_sig - p['nervios']['h_m'])
                    h = techo - zn
                else:
                    h = mu['altura']
                L = s1 - s0
                geo = caja(s0, c - e_ / 2, zn, s1, c + e_ / 2, zn + h) if eje == 'x' else caja(c - e_ / 2, s0, zn, c + e_ / 2, s1, zn + h)
                es_fach = t in ('fachada', 'cerramiento', 'parapeto') or 'exterior' in (mu.get('lados') or [])
                tipo_ifc = {'fachada': 'STANDARD', 'parapeto': 'PARAPET', 'cerramiento': 'USERDEFINED', 'nucleo_mamposteria': 'STANDARD'}.get(t, 'PARTITIONING')
                if n['id'] == 'BT':
                    costo = [cost.v('17.12', None, 'incluido en el m² del bloque técnico (ítem 17.12)')]
                elif t == 'cerramiento':
                    costo = [cost.v('17.08', L)]
                else:
                    item = {'fachada': '4.03', 'bloque': '4.01', 'liviano': '4.02', 'plomado': '4.07', 'nucleo_mamposteria': '4.01',
                            'parapeto': '4.01'}[t]
                    costo = [cost.v(item, L * h)]
                qto = {'Qto_WallBaseQuantities': {'Length': r(L, 3), 'Width': e_, 'Height': r(h, 3), 'GrossSideArea': r(L * h, 3),
                                                  'NetSideArea': r(L * h, 3), 'GrossVolume': r(L * h * e_, 4), 'NetVolume': r(L * h * e_, 4)}}
                ps = {'Pset_WallCommon': {'Reference': t, 'IsExternal': bool(es_fach), 'LoadBearing': False,
                                          'ExtendToStructure': alt == 'entrepiso'}}
                at = atlas_pset(TD_B, F_PL + ' y ' + tipos_muro[t].get('fuente', ''), 'NSR-10 A.9 (elementos no estructurales)',
                                'A.9.4 (por confirmar)', tipos_muro[t]['material'][:200])
                e = elemento(wid, 'ARQ', 'IfcWall', tipo_ifc, f'Muro de {tipos_muro[t]["material"].split(":")[0].split(" con ")[0]}',
                             nid, geo, TIPO_MURO_MATERIAL[t], at, qto, ps, costo, fase_de('ARQ', nid),
                             objeto_tipo='CERRAMIENTO' if t == 'cerramiento' else None, muro_planta=mu['id'],
                             _eje=eje, _c=c, _u=(s0, s1), _e=e_, _h=h, _z=zn)
                M.agregar(e)
                muros_seg.setdefault(mu['id'], []).append(e)
        tipo_muro_de = {mu['id']: mu['tipo'] for mu in n['muros']}

        def muro_host(mid, centro):
            for e in muros_seg.get(mid, []):
                u = centro[0] if e['_eje'] == 'x' else centro[1]
                if e['_u'][0] - 1e-6 <= u <= e['_u'][1] + 1e-6:
                    return e
            return None

        # ---------------- puertas
        for p in n['puertas']:
            if p['id'] in contexto:
                continue
            host = muro_host(p['muro'], p['centro'])
            tm = tipo_muro_de.get(p['muro'])
            cx, cy = p['centro']
            w, h = p['ancho'], p['alto']
            if host:
                eje, e_ = host['_eje'], host['_e']
            else:
                eje = 'x'
                e_ = 0.1
                for mu in n['muros']:
                    if mu['id'] == p['muro']:
                        eje = 'x' if abs(mu['a'][1] - mu['b'][1]) < 1e-9 else 'y'
            hoja = 0.05
            geo = (caja(cx - w / 2, cy - hoja / 2, zn, cx + w / 2, cy + hoja / 2, zn + h) if eje == 'x'
                   else caja(cx - hoja / 2, cy - w / 2, zn, cx + hoja / 2, cy + w / 2, zn + h))
            item, nota = puerta_item(p, tm)
            if n['id'] == 'BT':
                item, nota = '17.12', 'incluida en el m² del bloque técnico (ítem 17.12)'
            costo = [cost.v(item, None if item in GLOBALES else 1, nota)]
            op = {'batiente': 'SINGLE_SWING_LEFT' if p.get('bisagra') == 'izquierda' else 'SINGLE_SWING_RIGHT',
                  'corrediza': 'SLIDING_TO_LEFT', 'automatica': 'DOUBLE_DOOR_SLIDING', 'cortafuego': 'SINGLE_SWING_LEFT'}.get(p.get('tipo'), 'NOTDEFINED')
            if p.get('hojas') == 2 and p.get('tipo') in ('batiente', 'cortafuego'):
                op = 'DOUBLE_DOOR_SINGLE_SWING'
            if p.get('hojas') == 2 and p.get('tipo') == 'corrediza':
                op = 'DOUBLE_DOOR_SLIDING'
            ext = 'exterior' in (p.get('desde'), p.get('hacia')) or n['id'] == 'EXT'
            ps = {'Pset_DoorCommon': {'Reference': p.get('categoria'), 'IsExternal': bool(ext),
                                      'FireRating': '90 min' if p.get('categoria') == 'evacuacion' else None,
                                      'HandicapAccessible': w >= 0.9, 'FireExit': p.get('categoria') == 'evacuacion'}}
            at = atlas_pset(TD_B, F_PL, 'NSR-10 K.3.14 (puertas de salida) y Res. 1633 de 2025', None, p.get('cita_ancho'))
            vano = None
            if host:
                vid = p['id'] + '-V'
                vgeo = (caja(cx - w / 2, cy - e_ / 2 - 0.05, zn, cx + w / 2, cy + e_ / 2 + 0.05, zn + h) if eje == 'x'
                        else caja(cx - e_ / 2 - 0.05, cy - w / 2, zn, cx + e_ / 2 + 0.05, cy + w / 2, zn + h))
                vano = {'id': vid, 'guid': guid('vano|' + vid), 'geometria': vgeo, 'muro': host['id']}
                host.setdefault('vanos', []).append(vid)
                q = host['qto']['Qto_WallBaseQuantities']
                q['NetSideArea'] = r(q['NetSideArea'] - w * h, 3)
                q['NetVolume'] = r(q['NetVolume'] - w * h * e_, 4)
            M.agregar(elemento(p['id'], 'ARQ', 'IfcDoor', 'DOOR' if tm != 'cerramiento' else 'GATE', p.get('nombre') or f'Puerta {p.get("categoria")}',
                               nid, geo, 'puerta_hospitalaria', at,
                               {'Qto_DoorBaseQuantities': {'Width': w, 'Height': h, 'Area': r(w * h, 3)}}, ps, costo,
                               fase_de('ARQ', nid, 'acabado') if nid.startswith('P') else fase_de('ARQ', nid),
                               alto_total=h, ancho_total=w, operacion=op, vano=vano, muro_host=host['id'] if host else None))
        # ---------------- ventanas
        for v in n['ventanas']:
            if v['muro'] in contexto:
                continue
            host = muro_host(v['muro'], v['centro'])
            cx, cy = v['centro']
            w, h, ap = v['ancho'], v['alto'], v['antepecho']
            if host:
                eje, e_ = host['_eje'], host['_e']
            else:
                eje, e_ = 'x', 0.2
            mar = 0.06
            geo = (caja(cx - w / 2, cy - mar / 2, zn + ap, cx + w / 2, cy + mar / 2, zn + ap + h) if eje == 'x'
                   else caja(cx - mar / 2, cy - w / 2, zn + ap, cx + mar / 2, cy + w / 2, zn + ap + h))
            vano = None
            if host:
                vid = v['id'] + '-V'
                vgeo = (caja(cx - w / 2, cy - e_ / 2 - 0.05, zn + ap, cx + w / 2, cy + e_ / 2 + 0.05, zn + ap + h) if eje == 'x'
                        else caja(cx - e_ / 2 - 0.05, cy - w / 2, zn + ap, cx + e_ / 2 + 0.05, cy + w / 2, zn + ap + h))
                vano = {'id': vid, 'guid': guid('vano|' + vid), 'geometria': vgeo, 'muro': host['id']}
                host.setdefault('vanos', []).append(vid)
                q = host['qto']['Qto_WallBaseQuantities']
                q['NetSideArea'] = r(q['NetSideArea'] - w * h, 3)
                q['NetVolume'] = r(q['NetVolume'] - w * h * e_, 4)
            costo = [cost.v('7.01', w * h)] if n['id'] != 'BT' else [cost.v('17.12', None, 'incluida en el m² del bloque técnico')]
            M.agregar(elemento(v['id'], 'ARQ', 'IfcWindow', 'WINDOW', 'Ventana de aluminio con vidrio laminado', nid, geo,
                               'aluminio_vidrio', atlas_pset(TD_B, F_PL, 'Res. 1633 de 2025 (iluminación y ventilación natural)'),
                               {'Qto_WindowBaseQuantities': {'Width': w, 'Height': h, 'Area': r(w * h, 3)}},
                               {'Pset_WindowCommon': {'IsExternal': True, 'Reference': 'ventana de fachada'}}, costo,
                               fase_de('ARQ', nid), alto_total=h, ancho_total=w, vano=vano, muro_host=host['id'] if host else None))
        # ---------------- pisos y cielos (pisos 1 a 4)
        if nid in ('P1', 'P2', 'P3', 'P4'):
            for rc in n['recintos']:
                pol = rc['poligono']
                A = abs(area_poligono(pol))
                item, mat = tipo_piso(rc['ambiente'])
                if 'scalera' in rc['ambiente'] or 'scensor' in rc['ambiente'] or 'ucto' in rc['ambiente']:
                    continue
                M.agregar(elemento(f'{rc["id"]}-PISO', 'ARQ', 'IfcCovering', 'FLOORING', f'Piso de {rc["ambiente"][:60]}', nid,
                                   prisma(pol, zn, zn + 0.003), mat,
                                   atlas_pset('estimación (reparto propio por tipo de recinto)', 'presupuesto.json, capítulo 6',
                                              'Res. 1633 de 2025, Anexo 1', 'num. 3.3.8 (pisos lisos, lavables y continuos)'),
                                   {'Qto_CoveringBaseQuantities': {'Width': 0.003, 'GrossArea': r(A, 3), 'NetArea': r(rc.get('area_libre_m2') or A, 3)}},
                                   {'Pset_CoveringCommon': {'Reference': mat, 'IsExternal': False}},
                                   [cost.v(item, rc.get('area_libre_m2') or A)], fase_de('ARQ', nid, 'acabado'), espacio=rc['id']))
                item, mat = tipo_cielo(rc['ambiente'])
                M.agregar(elemento(f'{rc["id"]}-CIELO', 'ARQ', 'IfcCovering', 'CEILING', f'Cielo raso de {rc["ambiente"][:60]}', nid,
                                   prisma(pol, zn + hl, zn + hl + 0.015), mat,
                                   atlas_pset('estimación (reparto propio por tipo de recinto)', 'presupuesto.json, capítulo 6',
                                              'Res. 1633 de 2025, Anexo 1', 'num. 3.3.8'),
                                   {'Qto_CoveringBaseQuantities': {'Width': 0.015, 'GrossArea': r(A, 3), 'NetArea': r(rc.get('area_libre_m2') or A, 3)}},
                                   {'Pset_CoveringCommon': {'Reference': mat, 'IsExternal': False}},
                                   [cost.v(item, rc.get('area_libre_m2') or A)], fase_de('ARQ', nid, 'acabado'), espacio=rc['id']))
        # ---------------- bloque técnico: piso y cubierta (estructura independiente sin diseñar: estimación)
        if nid == 'BT':
            bloque = [rc['poligono'] for rc in n['recintos'] if rc['tipo'] == 'recinto' and rc['id'][3:7] in
                      ('A210', 'A211', 'A212', 'A213', 'A214', 'A215')]
            xs = [p[0] for pg in bloque for p in pg]
            ys = [p[1] for pg in bloque for p in pg]
            pol = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
            A = abs(area_poligono(pol))
            res = [rc for rc in n['recintos'] if 'residuos' in rc['ambiente'].lower() and rc['tipo'] == 'recinto']
            for rc in res:
                Ar = abs(area_poligono(rc['poligono']))
                M.agregar(elemento(f'{rc["id"]}-LOSA', 'ARQ', 'IfcSlab', 'BASESLAB', 'Losa de piso de la unidad central de residuos', 'BT',
                                   prisma(rc['poligono'], zn - 0.15, zn), 'concreto_21',
                                   atlas_pset('estimación', 'presupuesto.json, ítem 17.13; ' + F_PL),
                                   {'Qto_SlabBaseQuantities': {'Depth': 0.15, 'GrossArea': r(Ar, 3), 'NetArea': r(Ar, 3), 'GrossVolume': r(Ar * 0.15, 3), 'NetVolume': r(Ar * 0.15, 3)}},
                                   {'Pset_SlabCommon': {'LoadBearing': True, 'IsExternal': False}}, [cost.v('17.13', Ar)], fase_de('ARQ', 'BT')))
            M.agregar(elemento('BT-PISO', 'ARQ', 'IfcSlab', 'BASESLAB', 'Losa de piso del bloque técnico', 'BT', prisma(pol, zn - 0.15, zn),
                               'concreto_21', atlas_pset('estimación', 'presupuesto.json, ítem 17.12; ' + F_PL,
                                                         nota='el bloque técnico es una estructura independiente con junta; su estructura no está en el prediseño de A'),
                               {'Qto_SlabBaseQuantities': {'Depth': 0.15, 'GrossArea': r(A, 3), 'NetArea': r(A, 3), 'GrossVolume': r(A * 0.15, 3), 'NetVolume': r(A * 0.15, 3)}},
                               {'Pset_SlabCommon': {'LoadBearing': True, 'IsExternal': False}}, [cost.v('17.12', A)], fase_de('ARQ', 'BT')))
            M.agregar(elemento('BT-CUB', 'ARQ', 'IfcSlab', 'ROOF', 'Cubierta del bloque técnico', 'BT',
                               prisma(pol, zn + n['altura_entrepiso_m'] - 0.12, zn + n['altura_entrepiso_m']), 'concreto_21',
                               atlas_pset('estimación', 'presupuesto.json, ítem 17.12; ' + F_PL),
                               {'Qto_SlabBaseQuantities': {'Depth': 0.12, 'GrossArea': r(A, 3), 'NetArea': r(A, 3), 'GrossVolume': r(A * 0.12, 3), 'NetVolume': r(A * 0.12, 3)}},
                               {'Pset_SlabCommon': {'LoadBearing': True, 'IsExternal': True}},
                               [cost.v('17.12', None, 'incluida en el m² del bloque técnico')], fase_de('ARQ', 'BT')))
    # ---------------- cubierta impermeabilizada (sobre la losa del piso 4 y la terraza del piso 3)
    p4 = [[-13.0, -7.6], [3.1, -7.6], [3.1, 0.8], [8.6, 0.8], [8.6, 14.0], [3.1, 14.0], [3.1, 22.4], [-13.0, 22.4]]
    ter = [[-13.0, -19.6], [8.6, -19.6], [8.6, -7.6], [-13.0, -7.6]]
    for id_, pol, z, niv, nom in (('CUB-P4', p4, 17.1, 'CUB', 'Cubierta impermeabilizada del piso 4 (sin las casetas de las escaleras)'),
                                  ('CUB-P3', ter, 12.9, 'P4', 'Cubierta impermeabilizada de la terraza del piso 3')):
        A = abs(area_poligono(pol))
        M.agregar(elemento(id_, 'ARQ', 'IfcSlab', 'ROOF', nom, niv, prisma(pol, z, z + 0.10), 'cubierta',
                           atlas_pset('cálculo propio sobre las plantas', 'presupuesto.json, ítem 5.01 (APU-14); ' + F_PL,
                                      'Res. 1633 de 2025, Anexo 2', 'reflectividad de la cubierta (por confirmar)'),
                           {'Qto_SlabBaseQuantities': {'Depth': 0.10, 'GrossArea': r(A, 3), 'NetArea': r(A, 3), 'GrossVolume': r(A * 0.1, 3), 'NetVolume': r(A * 0.1, 3)}},
                           {'Pset_SlabCommon': {'IsExternal': True, 'LoadBearing': False}}, [cost.v('5.01', A)], 'F8-CUB'))
    return resumen


def escaleras_arq(M, pl, S, cost, est):
    """IfcStair por escalera y piso con sus tramos (IfcStairFlight, perfil de peldaños y losa de 0,20 m) y descansos
    (IfcSlab LANDING). El descanso de piso del piso 1 es el contrapiso. Devuelve los tramos para el despiece."""
    esp = {e['id']: e['espesor_m'] for e in est['refuerzo']['escaleras']}
    tramos_por_esc = {}
    nivs = {n['id']: n for n in pl['niveles']}
    orden = ['P1', 'P2', 'P3', 'P4', 'CUB']
    for i, nid in enumerate(orden[:-1]):
        n = nivs[nid]
        zn = n['z']
        k = n['piso']
        for esc in n['escaleras']:
            tramos = [p for p in esc['partes'] if p['tipo'] == 'tramo']
            if not tramos:
                continue
            sid = f'{esc["id"]}-{k}'
            t = esp.get(sid, 0.20)
            partes = []
            vol_total = 0.0
            area_huella = 0.0
            tr_desp = []
            des_desp = []
            desc = [p for p in esc['partes'] if p['tipo'].startswith('descanso')]
            sobre_losa = []
            # la escalera de cada piso lleva su descanso intermedio y el de llegada del nivel de arriba; su propio descanso
            # de piso es el de llegada de la escalera de abajo (en el piso 1, el contrapiso)
            sig = nivs[orden[i + 1]]
            llegada = [p for e2 in sig['escaleras'] if e2['id'] == esc['id'] for p in e2['partes'] if p['tipo'] == 'descanso_piso']
            # el descanso de llegada que cae sobre la losa del piso de arriba (la escalera abierta del vestíbulo, que llega a una
            # franja de piso) es esa losa: no se modela aparte; si la losa lo cubre en parte, solo la parte que queda libre
            piezas = [dict(q, _rect=q['rect']) for q in desc if q['tipo'] == 'descanso_intermedio']
            for q in llegada:
                z_ll = sig['z'] + q['z']
                cubre = [[L_['x0'], L_['y0'], L_['x1'], L_['y1']] for L_ in S.losas if abs(L_['z'] - z_ll) < 1e-6]
                libres_ = restar_rects(list(q['rect']), cubre)
                a_tot = (q['rect'][2] - q['rect'][0]) * (q['rect'][3] - q['rect'][1])
                a_lib = sum((w[2] - w[0]) * (w[3] - w[1]) for w in libres_)
                if a_lib < 0.02 * a_tot:
                    sobre_losa.append(f'El descanso de llegada (nivel {_m(z_ll)} m) es la losa de ese piso: no se modela aparte')
                    continue
                for w in (libres_ if a_lib < 0.98 * a_tot else [q['rect']]):
                    piezas.append(dict(q, _z_abs=z_ll, _rect=w))
            for p in piezas:
                zt = p.get('_z_abs', zn + p['z'])
                x0, y0, x1, y1 = p['_rect']
                g = caja(x0, y0, zt - t, x1, y1, zt)
                vol = volumen(g)
                vol_total += vol
                area_huella += (x1 - x0) * (y1 - y0)
                pid = f'{sid}-D{len(partes) + 1}'
                des_desp.append({'id': pid, 'rect': [x0, y0, x1, y1], 'zt': zt, 't': t})
                partes.append(elemento(pid, 'ARQ', 'IfcSlab', 'LANDING', f'Descanso de la {esc["nombre"].lower()}', nid, g, 'concreto_28',
                                       atlas_pset(TD_B, F_PL + '; espesor del despiece de A', NSR_C, 'C.7.12 y C.9 (por confirmar)'),
                                       {'Qto_SlabBaseQuantities': {'Depth': t, 'GrossArea': r((x1 - x0) * (y1 - y0), 3), 'GrossVolume': r(vol, 4), 'NetVolume': r(vol, 4)}},
                                       {'Pset_SlabCommon': {'LoadBearing': True, 'IsExternal': False}},
                                       [cost.v('3.04', vol)], fase_de('ARQ', nid, f'est{k}'), parte_de=sid))
            for j, tr in enumerate(tramos):
                x0, y0, x1, y1 = tr['rect']
                nr = tr['contrahuellas']
                ang = tr['sube_hacia_deg']
                if ang in (90, 270):
                    run = [0.0, 1.0] if ang == 90 else [0.0, -1.0]
                    L = y1 - y0
                    p0 = [x0, y0 if ang == 90 else y1]
                    ancho = x1 - x0
                    lat = [1.0, 0.0]
                else:
                    run = [1.0, 0.0] if ang == 0 else [-1.0, 0.0]
                    L = x1 - x0
                    p0 = [x0 if ang == 0 else x1, y0]
                    ancho = y1 - y0
                    lat = [0.0, 1.0]
                z0, z1 = zn + tr['z0'], zn + tr['z1']
                H = z1 - z0
                g_ = L / (nr - 1)
                rr = H / nr
                tv = t * math.hypot(g_, rr) / g_
                # perfil de peldaños con la losa paralela a la línea de los peldaños; la última contrahuella es el borde
                # del descanso de llegada (no se repite aquí)
                # la cara inferior inclinada sigue hasta cortar la cara inferior de los descansos (abajo en u_b y arriba
                # en u_k, debajo del descanso de llegada), como se funde el quiebre de la losa; el primer tramo del piso 1
                # arranca sobre el contrapiso (su cara inferior abajo es la del contrapiso)
                en_contrapiso = nid == 'P1' and abs(tr['z0']) < 1e-9
                t_b = 0.15 if en_contrapiso else t
                u_b = (tv - t_b) * g_ / rr
                u_k = (H - t + tv) * g_ / rr
                pts = [[0.0, -t_b], [0.0, rr]]
                for q in range(1, nr - 1):
                    pts += [[q * g_, q * rr], [q * g_, (q + 1) * rr]]
                pts += [[L, (nr - 1) * rr]]
                if abs((H - t) - (nr - 1) * rr) > 1e-6:
                    pts += [[L, H - t]]
                pts += [[u_k, H - t], [u_b, -t_b]]
                # el perfil se extruye a lo ancho: w = run × arriba (mano derecha)
                w = [run[1] * 1.0 - 0.0, -run[0] * 1.0, 0.0]
                w = [run[1], -run[0], 0.0]
                origen = [p0[0], p0[1], z0]
                # que la extrusión vaya hacia adentro del rectángulo del tramo
                if (lat[0] * w[0] + lat[1] * w[1]) < 0:
                    origen = [origen[0] + lat[0] * ancho, origen[1] + lat[1] * ancho, z0]
                geo = {'tipo': 'perfil', 'origen': rp(origen), 'u': [run[0], run[1], 0.0], 'v': [0.0, 0.0, 1.0], 'w': w,
                       'puntos': [rp(p) for p in pts], 'largo': r(ancho)}
                vol = volumen(geo)
                vol_total += vol
                area_huella += L * ancho
                fid = f'{sid}-T{j + 1}'
                partes.append(elemento(fid, 'ARQ', 'IfcStairFlight', 'STRAIGHT', f'Tramo {j + 1} de la {esc["nombre"].lower()}', nid, geo,
                                       'concreto_28', dict(atlas_pset(TD_B, F_PL + '; espesor del despiece de A', 'NSR-10 K.3.8 (escaleras de evacuación)', 'por confirmar'),
                                                           Portante=True),
                                       {'Qto_StairFlightBaseQuantities': {'Length': r(math.hypot(L, H), 3), 'GrossVolume': r(vol, 4), 'NetVolume': r(vol, 4)}},
                                       {'Pset_StairFlightCommon': {'NumberOfRiser': nr, 'NumberOfTreads': nr - 1, 'RiserHeight': r(rr, 4),
                                                                   'TreadLength': r(g_, 4)}},
                                       [cost.v('3.04', vol), cost.v('6.04', L * ancho)], fase_de('ARQ', nid, f'est{k}'), parte_de=sid,
                                       _tramo={'run': run, 'L': L, 'H': H, 'z0': z0, 'z1': z1, 'ancho': ancho, 'p0': p0}))
                # para el despiece: descansos de abajo y arriba a lo largo de la corrida
                des = [p for p in desc]
                def largo_descanso(z_):
                    for p in des + [dict(q, z=q['z'] + sig['z'] - zn) for q in llegada]:
                        if abs(zn + p['z'] - z_) < 1e-6:
                            x0d, y0d, x1d, y1d = p['rect']
                            return (y1d - y0d) if ang in (90, 270) else (x1d - x0d)
                    return 0.6
                tr_desp.append({'run': run, 'lat': lat, 'L': L, 'H': H, 'ancho': ancho, 'p0': [p0[0], p0[1], z0], 't': t, 'nr': nr,
                                'des0': 0.40 if en_contrapiso else min(largo_descanso(z0), 2.5), 't0': 0.15 if en_contrapiso else t,
                                'des1': min(largo_descanso(z1), 2.5), 'z0': z0, 'z1': z1})
            for d_ in des_desp:
                d_['corrida'] = 'y' if tramos[0]['sube_hacia_deg'] in (90, 270) else 'x'
            tramos_por_esc[sid] = {'tramos': tr_desp, 'descansos': des_desp}
            alturas = [tr['z1'] - tr['z0'] for tr in tramos]
            M.agregar(elemento(sid, 'ARQ', 'IfcStair', 'HALF_TURN_STAIR' if len(tramos) == 2 else 'STRAIGHT_RUN_STAIR', esc['nombre'],
                               nid, {'tipo': 'compuesta', 'partes': []}, 'concreto_28',
                               dict(atlas_pset(TD_B, F_PL + '; refuerzo y espesor del despiece de A', 'NSR-10 K.3.8 (escaleras de evacuación)', 'por confirmar',
                                               '; '.join(sobre_losa + esc.get('notas', []))[:400]), Portante=True),
                               {QTO_PROPIO: {'GrossVolume': r(vol_total, 4), 'NetVolume': r(vol_total, 4), 'Length': r(sum(alturas), 3)}},
                               {'Pset_StairCommon': {'NumberOfRiser': sum(tr['contrahuellas'] for tr in tramos),
                                                     'RiserHeight': tramos[0]['contrahuella_m'], 'TreadLength': tramos[0]['huella_m'],
                                                     'FireExit': 'evacuaci' in esc['nombre'].lower()}},
                               [], fase_de('ARQ', nid, f'est{k}'), partes=[p['id'] for p in partes],
                               analisis={'nota': 'la masa de las escaleras entra en el análisis por nivel (detalle_masa.escaleras); '
                                                 'las escaleras no son elementos del modelo sísmico'}))
            for p in partes:
                M.agregar(p)
    return tramos_por_esc


# ============================================================================================================ EST
def estructura(M, S, cost, est):
    ref = est['refuerzo']
    # columnas
    for c in ref['columnas']:
        k = c['nivel']
        b, h = c['b'], c['h']
        L = c['z1'] - c['z0']
        V = b * h * L
        seccion = next((e['seccion'] for P in est['bloques'][0]['porticos'] for e in P['elementos'] if e.get('fisico') == c['id']), None)
        ext = abs(c['x'] - (-13.0)) < 1e-6 or abs(c['x'] - 8.6) < 1e-6 or abs(c['y'] - (-19.6)) < 1e-6 or abs(c['y'] - 22.4) < 1e-6
        e = c['estribos']
        M.agregar(elemento(c['id'], 'EST', 'IfcColumn', 'COLUMN', f'Columna {c["eje"]} del piso {k} ({_m(b)} × {_m(h)} m)', f'P{k}',
                           caja(c['x'] - b / 2, c['y'] - h / 2, c['z0'], c['x'] + b / 2, c['y'] + h / 2, c['z1']), 'concreto_28',
                           atlas_pset(TD_A, F_EST, 'NSR-10 C.21 (pórticos DMO)', 'C.21.3 (por confirmar)', c['texto']),
                           {'Qto_ColumnBaseQuantities': {'Length': r(L, 3), 'CrossSectionArea': r(b * h, 4), 'OuterSurfaceArea': r(2 * (b + h) * L, 3),
                                                         'GrossVolume': r(V, 4), 'NetVolume': r(V, 4), 'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_ColumnCommon': {'Reference': seccion, 'LoadBearing': True, 'IsExternal': ext, 'Slope': 0.0},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.04,
                                                            'ReinforcementStrengthClass': 'NTC 2289 grado 420'},
                            'Pset_ReinforcementBarPitchOfColumn': {'Reference': c['texto'][:120], 'HoopBarPitch': e['s_lo_m'],
                                                                   'XDirectionTieHoopBarPitch': e['s_lo_m'],
                                                                   'XDirectionTieHoopCount': e['ganchos_suplementarios_por_direccion'],
                                                                   'YDirectionTieHoopBarPitch': e['s_lo_m'],
                                                                   'YDirectionTieHoopCount': e['ganchos_suplementarios_por_direccion']}},
                           [cost.v('3.01', V)], f'F8-EST{k}',
                           analisis={'elementos': sorted(S.analisis_col.get(c['id'], [])), 'fisico': c['id']},
                           refuerzo_texto=c['texto'], kg_A=r(c['kg'], 1)))
    # vigas
    for v in ref['vigas']:
        a, b_ = v['_caja']
        L = v['_Lf']
        V = (b_[0] - a[0]) * (b_[1] - a[1]) * (b_[2] - a[2])
        z = v['xyz_i'][2]
        k = round(z, 2)
        niv = S.nivel_de_z(z)
        piso = {4.5: 1, 8.7: 2, 12.9: 3, 17.1: 4}[k]
        M.agregar(elemento(v['id'], 'EST', 'IfcBeam', 'BEAM', f'Viga del eje {v["eje"]} ({_m(v["b"])} × {_m(v["h"])} m) del nivel {_m(z)}', niv,
                           caja(*a, *b_), 'concreto_28',
                           atlas_pset(TD_A, F_EST, 'NSR-10 C.21 (pórticos DMO)', 'C.21.3 (por confirmar)', v['texto']),
                           {'Qto_BeamBaseQuantities': {'Length': r(L, 3), 'CrossSectionArea': r(v['b'] * v['h'], 4),
                                                       'GrossVolume': r(V, 4), 'NetVolume': r(V, 4), 'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_BeamCommon': {'Reference': f'{_m(v["b"])} × {_m(v["h"])}', 'Span': r(v['L'], 3), 'LoadBearing': True,
                                                'IsExternal': False, 'Slope': 0.0},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.04},
                            'Pset_ReinforcementBarPitchOfBeam': {'Reference': v['texto'][:120], 'StirrupBarPitch': v['estribos']['s_2h_m']}},
                           [cost.v('3.03', V)], f'F8-EST{piso}',
                           analisis={'elementos': [v['id']]} if not v.get('tipo') else {'elementos': [], 'nota': 'viga banda de enlace: fuera del modelo de análisis (A)'},
                           refuerzo_texto=v['texto'], kg_A=r(v['kg'], 1)))
    # losas nervadas
    for p in ref['losas']:
        g = p['_geo']
        V = volumen(g)
        z = p['z']
        niv = S.nivel_de_z(z)
        piso = {4.5: 1, 8.7: 2, 12.9: 3, 17.1: 4}[round(z, 2)]
        Ag = (p['x1'] - p['x0']) * (p['y1'] - p['y0'])
        tipo = 'FLOOR' if p['tipo'] == 'piso' else 'ROOF'
        M.agregar(elemento(p['id'], 'EST', 'IfcSlab', tipo, f'Losa nervada {p["id"]} ({_m(p["nervios"]["h_m"])} m) del nivel {_m(z)}', niv, g,
                           'concreto_28', atlas_pset(TD_A, F_EST, 'NSR-10 C.8.13 (losas nervadas)', 'C.8.13 (por confirmar)', p['texto']),
                           {'Qto_SlabBaseQuantities': {'Width': r(p['y1'] - p['y0'], 3), 'Length': r(p['x1'] - p['x0'], 3), 'Depth': p['nervios']['h_m'],
                                                       'GrossArea': r(Ag, 3), 'NetArea': r(p['_area_neta'], 3), 'GrossVolume': r(V, 4),
                                                       'NetVolume': r(V, 4), 'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_SlabCommon': {'Reference': 'losa nervada en una dirección', 'LoadBearing': True, 'IsExternal': tipo == 'ROOF'},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.02},
                            'Pset_ReinforcementBarPitchOfSlab': {'Reference': p['texto'][:120], 'LongOutsideTopBarPitch': 0.20,
                                                                 'ShortOutsideTopBarPitch': 0.20}},
                           [cost.v('3.03', V)], f'F8-EST{piso}',
                           analisis={'elementos': [], 'diafragma': f'N{piso}', 'nota': 'diafragma rígido del nivel en el modelo de A'},
                           refuerzo_texto=p['texto'], kg_A=r(p['kg'], 1),
                           apoyos_sin_estructura=p.get('_sin_apoyo') or None))
    # muros estructurales
    for m in ref['muros']:
        k = m['nivel']
        g = prisma(_rect_pol(m['_rects'][0]), m['z0'], m['z1']) if len(m['_rects']) == 1 else \
            {'tipo': 'compuesta', 'partes': [prisma(_rect_pol(rr), m['z0'], m['z1']) for rr in m['_rects']]}
        V = volumen(g)
        L = sum(max(rr[2] - rr[0], rr[3] - rr[1]) for rr in m['_rects'])
        h = m['z1'] - m['z0']
        cv, ch = m['cortina_vertical'], m['cortina_horizontal']
        M.agregar(elemento(m['id'], 'EST', 'IfcWall', 'SHEAR', f'Muro estructural {m["muro"]} del piso {k} (0,35 m)', f'P{k}', g, 'concreto_28',
                           atlas_pset(TD_A, F_EST, 'NSR-10 C.21 (muros estructurales DMO)', 'C.21.9 (por confirmar)', m['texto'][:300]),
                           {'Qto_WallBaseQuantities': {'Length': r(L, 3), 'Width': m['t'], 'Height': r(h, 3), 'GrossSideArea': r(L * h, 3),
                                                       'NetSideArea': r(L * h, 3), 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4), 'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_WallCommon': {'Reference': 'muro estructural DMO', 'LoadBearing': True, 'IsExternal': False},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.025},
                            'Pset_ReinforcementBarPitchOfWall': {'Reference': m['texto'][:120], 'VerticalBarPitch': cv['s_m'],
                                                                 'HorizontalBarPitch': ch['s_m'], 'BarAllocationType': 'DOUBLE'}},
                           [cost.v('3.02', V)], f'F8-EST{k}', analisis={'elementos': [m['id']], 'muro': m['muro']},
                           refuerzo_texto=m['texto'][:300], kg_A=r(m['kg'], 1)))


def _m(v):
    return f'{v:.2f}'.replace('.', ',')


def planta_contrapiso(est):
    """[x0, y0, x1, y1] del contrapiso del prediseño (cimentacion.contrapiso.planta_m; antes de que A lo diera, la huella de
    los pisos 1-3)."""
    return list(est['cimentacion']['contrapiso'].get('planta_m') or [-13.0, -19.6, 8.6, 22.4])


def _rect_pol(rr):
    x0, y0, x1, y1 = rr
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# ============================================================================================================ CIM
def cimentacion(M, S, cost, est, bases):
    C = est['cimentacion']
    suelo = C['suelo_supuesto']
    pil = C['pilote']
    reac = C['reacciones']
    grupos = {g['id']: g for g in C['grupos']}
    # arranques de columnas y muros
    for linea, b in sorted(bases.items()):
        if b['tipo'] == 'columna':
            c = S.columnas[f'{linea}-1']
            z0, z1 = b['z_tope'], 0.0
            ba, ha = c['b'] + 2 * SOBREANCHO_ARRANQUE, c['h'] + 2 * SOBREANCHO_ARRANQUE
            V = ba * ha * (z1 - z0)
            M.agregar(elemento(b['host_arranque'], 'CIM', 'IfcColumn', 'COLUMN', f'Arranque (pedestal) de la columna {c["eje"]} sobre {b["apoyo"]}', 'CIM',
                               caja(c['x'] - ba / 2, c['y'] - ha / 2, z0, c['x'] + ba / 2, c['y'] + ha / 2, z1), 'concreto_28',
                               atlas_pset(TD_F, F_EST + ' (cotas de la cara superior del dado y del piso 1)', NSR_C, 'C.7.7.1 (recubrimiento contra el relleno) y C.15.8 (por confirmar)',
                                          'El despiece de A empieza la columna en el piso 1 (z = 0); el arranque llena el tramo hasta la cara superior del '
                                          'dado y es 1 cm más ancho por lado que la columna para dar 50 mm de recubrimiento contra el relleno.'),
                               {'Qto_ColumnBaseQuantities': {'Length': r(z1 - z0, 3), 'CrossSectionArea': r(ba * ha, 4), 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4)}},
                               {'Pset_ColumnCommon': {'Reference': 'arranque', 'LoadBearing': True, 'IsExternal': False},
                                'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.04}},
                               [cost.v('3.01', V, 'arranque bajo el piso 1: no está en las cantidades de A')], 'F7-DAD',
                               analisis={'elementos': [], 'nota': 'la base del modelo de A está empotrada en la cara superior del dado'}))
        else:
            ms = [m for m in S.muros if m['muro'] == linea and m['nivel'] == 1][0]
            z0, z1 = b['z_tope'], 0.0
            rects = rects_arranque_muro(ms, S)
            partes = [prisma(_rect_pol(rr), z0, z1) for rr in rects]
            g = partes[0] if len(partes) == 1 else {'tipo': 'compuesta', 'partes': partes}
            V = volumen(g)
            M.agregar(elemento(b['host_arranque'], 'CIM', 'IfcWall', 'SHEAR', f'Arranque del muro {linea} sobre {b["apoyo"]}', 'CIM', g, 'concreto_28',
                               atlas_pset(TD_F, F_EST, NSR_C, 'C.21.9 y C.7.7.1 (por confirmar)', 'tramo del muro entre la cara superior de la losa de pilotes y el '
                                          'piso 1, 1,5 cm más ancho por lado para el recubrimiento contra el relleno'),
                               {'Qto_WallBaseQuantities': {'Height': r(z1 - z0, 3), 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4)}},
                               {'Pset_WallCommon': {'Reference': 'arranque de muro estructural', 'LoadBearing': True, 'IsExternal': False}},
                               [cost.v('3.02', V, 'arranque bajo el piso 1: no está en las cantidades de A')], 'F7-DAD',
                               analisis={'elementos': [], 'nota': 'base del muro empotrada en la losa de pilotes en el modelo de A'}))
    # pilotes
    for g in C['pilotes']:
        for kp, (px, py) in enumerate(g['posiciones']):
            pid = f'PIL-{g["grupo"]}-{kp + 1}'
            L = g['z_cabeza'] - g['z_punta']
            Rr = g['D_m'] / 2
            V = math.pi * Rr * Rr * L
            gr = grupos[g['grupo']]
            M.agregar(elemento(pid, 'CIM', 'IfcPile', 'BORED', f'Pilote preexcavado {kp + 1} de {g["grupo"]} (Ø {_m(g["D_m"])} m, {_m(L)} m)', 'CIM-PIL',
                               {'tipo': 'cilindro', 'centro': rp([px, py]), 'radio': Rr, 'z0': r(g['z_punta']), 'z1': r(g['z_cabeza'])}, 'concreto_28',
                               atlas_pset('estimación (prediseño de A; la fija el estudio geotécnico)', F_EST + ' → cimentacion',
                                          'NSR-10 Título H (cimentaciones profundas)', 'H.4 y H.6 (por confirmar)', g['texto']),
                               {'Qto_PileBaseQuantities': {'Length': r(L, 3), 'CrossSectionArea': r(math.pi * Rr * Rr, 4), 'GrossVolume': r(V, 4),
                                                           'NetVolume': r(V, 4), 'NetWeight': r(V * RHO_C, 1)}},
                               {'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': g['recubrimiento_m']},
                                'Pset_PileCommon': {'Reference': 'pilote preexcavado', 'LoadBearing': True}},
                               [cost.v('2.04', L), cost.v('2.05', 1)], 'F7-PIL',
                               analisis={'grupo': g['grupo'], 'apoyos': gr['apoyos'], 'n_pilotes': gr['n_pilotes'],
                                         'capacidad_kN': {k_: pil['capacidad_kN'][k_] for k_ in ('Qadm', 'Qsismo', 'Tsismo')},
                                         'reaccion_max_kN': {k_: gr['reacciones_pilote_kN'][k_]['max'] for k_ in ('estatico', 'sismo', 'capacidad')},
                                         'reaccion_min_kN': {k_: gr['reacciones_pilote_kN'][k_]['min'] for k_ in ('estatico', 'sismo', 'capacidad')}},
                               cota_punta=g['z_punta'], cota_cabeza=g['z_cabeza'], grupo=g['grupo']))
    # dados y losas de pilotes
    for d in C['dados']:
        g = caja(d['x0'], d['y0'], d['z_fondo'], d['x1'], d['y1'], d['z_tope'])
        V = volumen(g)
        ref = d['refuerzo']
        Lx, Ly = d['x1'] - d['x0'], d['y1'] - d['y0']
        cargas = {a: {k_: reac[a][k_] for k_ in ('D_kN', 'L_kN', 'Lr_kN')} for a in d['apoyos'] if a in reac}
        es_dado = d['tipo'] == 'dado'
        M.agregar(elemento(d['id'], 'CIM', 'IfcFooting', 'PILE_CAP',
                           (f'Dado {d["id"]} de {_m(Lx)} × {_m(Ly)} × {_m(d["h"])} m con {d["pilotes"]} pilotes' if es_dado else
                            f'Losa de pilotes {d["id"][3:].replace("_", " ")} de {_m(Lx)} × {_m(Ly)} × {_m(d["h"])} m con {d["pilotes"]} pilotes'),
                           'CIM', g, 'concreto_28', atlas_pset(TD_A, F_EST + ' → cimentacion', 'NSR-10 C.15 (zapatas y dados)', 'C.15.5 y C.15.10 (por confirmar)', d['texto']),
                           {'Qto_FootingBaseQuantities': {'Length': r(Lx, 3), 'Width': r(Ly, 3), 'Height': d['h'], 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4),
                                                          'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_FootingCommon': {'Reference': 'dado de pilotes' if es_dado else 'losa de pilotes', 'LoadBearing': True},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.075},
                            'Pset_ReinforcementBarCountOfIndependentFooting': {'Reference': d['texto'][:120],
                                                                               'XDirectionLowerBarCount': int((Ly - 0.15) / ref['inferior_x']['s']) + 1,
                                                                               'YDirectionLowerBarCount': int((Lx - 0.15) / ref['inferior_y']['s']) + 1}},
                           [cost.v('2.07', V)], 'F7-DAD',
                           analisis={'apoyos': d['apoyos'], 'cargas_servicio_kN': cargas,
                                     'reacciones_pilote_kN': grupos[d['id']]['reacciones_pilote_kN'] if d['id'] in grupos else None},
                           refuerzo_texto=d['texto'], kg_A=r(d['kg'], 1), cota_fondo=d['z_fondo'], cota_tope=d['z_tope']))
    # vigas de amarre
    for v in C['vigas_amarre']:
        a, b_ = v['tramo']
        c = v['coordenada']
        zt = v['z_tope']
        g = caja(a, c - v['b'] / 2, zt - v['h'], b_, c + v['b'] / 2, zt) if v['direccion'] == 'x' else caja(c - v['b'] / 2, a, zt - v['h'], c + v['b'] / 2, b_, zt)
        V = volumen(g)
        M.agregar(elemento(v['id'], 'CIM', 'IfcFooting', 'FOOTING_BEAM', f'Viga de amarre {v["id"]} ({_m(v["b"])} × {_m(v["h"])} m) entre {v["desde"]} y {v["hasta"]}',
                           'CIM', g, 'concreto_28', atlas_pset(TD_A, F_EST + ' → cimentacion', 'NSR-10 C.15.13 (vigas de amarre)', 'C.15.13 (por confirmar)', v['texto']),
                           {'Qto_FootingBaseQuantities': {'Length': r(b_ - a, 3), 'Width': v['b'], 'Height': v['h'], 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4)}},
                           {'Pset_FootingCommon': {'Reference': 'viga de amarre', 'LoadBearing': True},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': 0.05}},
                           [cost.v('2.08', V)], 'F7-DAD', analisis={'une': [v['desde'], v['hasta']]}, refuerzo_texto=v['texto'], kg_A=r(v['kg'], 1)))
    # muros de contención del borde del pasaje del bloque técnico (sobre las vigas de amarre o en voladizo desde el dado)
    for m in C.get('muros_contencion') or []:
        x0, x1 = m['tramo']
        y0, y1 = m['y']
        g = caja(x0, y0, m['z_fondo'], x1, y1, m['z_tope'])
        V = volumen(g)
        L, h, t = x1 - x0, m['z_tope'] - m['z_fondo'], m['t_m']
        rv, rh, emp = m['refuerzo']['vertical'], m['refuerzo']['horizontal'], m['empuje']
        g_ = lambda v: f'{v:g}'.replace('.', ',')  # noqa: E731
        nota = (f'{m["texto"]}. {m["nota"][0].upper()}{m["nota"][1:]}; {m["apoyo"]} ({m["sobre"]}). Empuje en reposo (K0 = {g_(emp["K0"])}) con agua '
                f'y {g_(emp["sobrecarga_kPa"])} kPa de sobrecarga: Mu = {_m(emp["Mu_kNm_m"])} frente a φMn = {_m(emp["phiMn_kNm_m"])} kN·m/m y '
                f'Vu = {_m(emp["Vu_kN_m"])} frente a φVn = {_m(emp["phiVn_kN_m"])} kN/m (cálculo propio del prediseño)')
        M.agregar(elemento(m['id'], 'CIM', 'IfcWall', 'USERDEFINED',
                           f'Muro de contención {m["id"]} ({_m(t)} × {_m(h)} m) del borde del pasaje del bloque técnico', 'CIM', g, 'concreto_28',
                           atlas_pset(TD_A, F_EST + ' → cimentacion.muros_contencion', 'NSR-10 C.14.3 y título H (estructuras de contención)',
                                      'numerales por confirmar', nota),
                           {'Qto_WallBaseQuantities': {'Length': r(L, 3), 'Width': t, 'Height': r(h, 3), 'GrossSideArea': r(L * h, 3),
                                                       'NetSideArea': r(L * h, 3), 'GrossVolume': r(V, 4), 'NetVolume': r(V, 4),
                                                       'NetWeight': r(V * RHO_C, 1)}},
                           {'Pset_WallCommon': {'Reference': 'muro de contención', 'LoadBearing': True, 'IsExternal': True},
                            'Pset_ConcreteElementGeneral': {'StrengthClass': "f'c = 28 MPa", 'ConcreteCover': m['refuerzo']['recubrimiento_m']},
                            'Pset_ReinforcementBarPitchOfWall': {'Reference': m['texto'][:120], 'VerticalBarPitch': rv['s_m'],
                                                                 'HorizontalBarPitch': rh['s_m'], 'BarAllocationType': 'DOUBLE'}},
                           [cost.v('2.09', V, 'muro de contención: su concreto entra en la fila de fosos y cisternas (prediseño)')], 'F7-DAD',
                           objeto_tipo='RETAININGWALL', refuerzo_texto=m['texto'], kg_A=r(m['kg'], 1),
                           analisis={'nota': 'no está en el modelo sísmico: retiene el relleno frente al pasaje del bloque técnico',
                                     'sobre': m['sobre'], 'empuje': emp}))
    # contrapiso
    cp = C['contrapiso']
    rect = planta_contrapiso(est)
    huecos = []
    for f in C['fosos']:
        huecos.append([f['x'][0], f['y'][0], f['x'][1], f['y'][1]])
    for c in S.columnas.values():
        if c['nivel'] == 1:
            o = SOBREANCHO_ARRANQUE
            huecos.append([c['x'] - c['b'] / 2 - o, c['y'] - c['h'] / 2 - o, c['x'] + c['b'] / 2 + o, c['y'] + c['h'] / 2 + o])
    for m in S.muros:
        if m['nivel'] == 1:
            huecos += rects_arranque_muro(m, S)
    # los huecos de las columnas del borde cortan el contorno: la losa se arma con rectángulos (franjas sin huecos)
    partes = restar_rects(rect, huecos)
    g = {'tipo': 'compuesta', 'partes': [caja(q[0], q[1], -cp['espesor_m'], q[2], q[3], 0.0) for q in partes]}
    A = sum((q[2] - q[0]) * (q[3] - q[1]) for q in partes)
    M.agregar(elemento('CP-1', 'CIM', 'IfcSlab', 'BASESLAB', 'Losa de contrapiso del piso 1 (0,15 m)', 'CIM', g, 'concreto_21',
                       atlas_pset(TD_F, F_EST + ' → cimentacion.contrapiso; huella de los pisos 1-3', NSR_C, 'C.7.12 (refuerzo de retracción, por confirmar)',
                                  cp['malla'] + '. ' + cp['juntas']),
                       {'Qto_SlabBaseQuantities': {'Depth': cp['espesor_m'], 'GrossArea': r((rect[2] - rect[0]) * (rect[3] - rect[1]), 3), 'NetArea': r(A, 3),
                                                   'GrossVolume': r(A * cp['espesor_m'], 3), 'NetVolume': r(A * cp['espesor_m'], 3)}},
                       {'Pset_SlabCommon': {'Reference': 'contrapiso', 'LoadBearing': False, 'IsExternal': False},
                        'Pset_ConcreteElementGeneral': {'StrengthClass': 'f\'c = 21 MPa'}},
                       [cost.v('2.12', A)], 'F7-FOS', area_A=r(cp['area_m2'], 3)))
    # fosos y cisternas (conjuntos con su losa y sus muros)
    for f in C['fosos']:
        hf = huella_foso(f, S, bases)
        x0, x1 = hf['x']
        y0, y1 = hf['y']
        zf = f['z_fondo']
        e, el = f['muro_e_m'], f['losa_e_m']
        zt = -cp['espesor_m']
        losa = caja(x0, y0, zf, x1, y1, zf + el)
        muros_ = {'tipo': 'compuesta', 'partes': muros_foso(x0, y0, x1, y1, e, zf + el, zt, hf['compartidos'])}
        Vl, Vm = volumen(losa), volumen(muros_)
        nota_f = f['nota']
        if hf['compartidos']:
            nota_f += ('. Coordinación del modelo: ' + '; '.join(
                f'el lado {lado} del foso es el arranque del muro {", ".join(ms)}' for lado, ms in sorted(hf['compartidos'].items()))
                + ' (la huella del prediseño monta sobre ese muro; el modelo arranca la losa y los otros muros del foso en su cara, '
                'sin un muro propio en ese lado)')
        at = atlas_pset(TD_A, F_EST + ' → cimentacion.fosos', 'NSR-10 C.15 y C.23 (estructuras estancas, por confirmar)', None, nota_f)
        M.agregar(elemento(f['id'], 'CIM', 'IfcElementAssembly', 'USERDEFINED', f['nombre'], 'CIM', {'tipo': 'compuesta', 'partes': []}, 'concreto_28', at,
                           {QTO_PROPIO: {'GrossVolume': r(Vl + Vm, 4)}}, {}, [], 'F7-FOS', objeto_tipo='FOSO',
                           partes=[f['id'] + '-L', f['id'] + '-M'], refuerzo_texto=f['refuerzo']['muros'], kg_A=r(f['kg'], 1),
                           analisis={'nota': 'no está en el modelo sísmico; se apoya en el suelo'}))
        M.agregar(elemento(f['id'] + '-L', 'CIM', 'IfcSlab', 'BASESLAB', f'Losa de fondo del {f["nombre"].lower()}', 'CIM', losa, 'concreto_28', at,
                           {'Qto_SlabBaseQuantities': {'Depth': el, 'GrossVolume': r(Vl, 4), 'NetVolume': r(Vl, 4)}},
                           {'Pset_SlabCommon': {'LoadBearing': True, 'IsExternal': True}}, [cost.v('2.09', Vl)], 'F7-FOS', parte_de=f['id']))
        M.agregar(elemento(f['id'] + '-M', 'CIM', 'IfcWall', 'STANDARD', f'Muros del {f["nombre"].lower()}', 'CIM', muros_, 'concreto_28', at,
                           {'Qto_WallBaseQuantities': {'Width': e, 'GrossVolume': r(Vm, 4), 'NetVolume': r(Vm, 4)}},
                           {'Pset_WallCommon': {'LoadBearing': True, 'IsExternal': True}}, [cost.v('2.09', Vm)], 'F7-FOS', parte_de=f['id']))
    for c in C['cisternas']:
        x0, x1 = c['x']
        y0, y1 = c['y']
        zf = c['z_fondo']
        e, ef, et_ = c['muro_e_m'], c['losa_fondo_e_m'], c['losa_tapa_e_m']
        hi = c['h_interior_m']
        tal = c.get('talon_m', 0.0)
        z1 = zf + ef + hi
        Lx = x1 - x0
        xi = Lx - 2 * e - 2 * 0.25
        tab = [x0 + e + xi * 40 / 90, x0 + e + xi * 40 / 90 + 0.25 + xi * 30 / 90]
        fondo = caja(x0 - tal, y0 - tal, zf, x1 + tal, y1 + tal, zf + ef)
        tapa = caja(x0, y0, z1, x1, y1, z1 + et_)
        muros_ = {'tipo': 'compuesta', 'partes': [caja(x0, y0, zf + ef, x1, y0 + e, z1), caja(x0, y1 - e, zf + ef, x1, y1, z1),
                                                  caja(x0, y0 + e, zf + ef, x0 + e, y1 - e, z1), caja(x1 - e, y0 + e, zf + ef, x1, y1 - e, z1)]
                  + [caja(t_, y0 + e, zf + ef, t_ + 0.25, y1 - e, z1) for t_ in tab]}
        V3 = [volumen(fondo), volumen(muros_), volumen(tapa)]
        at = atlas_pset(TD_A, F_EST + ' → cimentacion.cisternas', 'NSR-10 C.23 (tanques y compartimientos estancos, por confirmar)', None,
                        c['nota'] + '. ' + c['impermeabilizacion'])
        M.agregar(elemento(c['id'], 'CIM', 'IfcElementAssembly', 'USERDEFINED', c['nombre'], 'CIM', {'tipo': 'compuesta', 'partes': []}, 'concreto_28', at,
                           {QTO_PROPIO: {'GrossVolume': r(sum(V3), 4)}}, {}, [], 'F7-FOS', objeto_tipo='CISTERNA',
                           partes=[c['id'] + '-F', c['id'] + '-M', c['id'] + '-T'], refuerzo_texto=c['refuerzo']['muros'], kg_A=r(c['kg'], 1),
                           analisis={'nota': 'estructura independiente bajo el patio del bloque técnico'}))
        for sub, g_, tipo, nom, cls in (('-F', fondo, 'BASESLAB', 'Losa de fondo con talón', 'IfcSlab'), ('-M', muros_, 'STANDARD', 'Muros y tabiques', 'IfcWall'),
                                        ('-T', tapa, 'ROOF', 'Tapa', 'IfcSlab')):
            V = volumen(g_)
            qn = 'Qto_SlabBaseQuantities' if cls == 'IfcSlab' else 'Qto_WallBaseQuantities'
            M.agregar(elemento(c['id'] + sub, 'CIM', cls, tipo, f'{nom} de las cisternas', 'CIM', g_, 'concreto_28', at,
                               {qn: {'GrossVolume': r(V, 4), 'NetVolume': r(V, 4)}},
                               {'Pset_SlabCommon' if cls == 'IfcSlab' else 'Pset_WallCommon': {'LoadBearing': True, 'IsExternal': True}},
                               [cost.v('2.09', V)], 'F7-FOS', parte_de=c['id']))


def huella_foso(f, S, bases):
    """Huella del foso en el modelo. Si un lado de la huella del prediseño cae dentro del arranque de un muro estructural
    que baja hasta el fondo del foso (el foso del montacargas junto a MX-4), ese muro es el lado del foso: la losa y los
    otros muros del foso arrancan en su cara y ese lado no lleva muro propio. Devuelve {'x', 'y', 'compartidos': {lado:
    [muros]}}."""
    x0, x1 = f['x']
    y0, y1 = f['y']
    arr = []
    for m in S.muros:
        b = bases.get(m['muro'])
        if m['nivel'] == 1 and b and b['z_tope'] <= f['z_fondo'] + 1e-6:
            arr += [(m['muro'], rr) for rr in rects_arranque_muro(m, S)]

    def cubre(iv, a, b_):
        p_ = a
        for u, v in sorted(iv):
            if u > p_ + 1e-6:
                return False
            p_ = max(p_, v)
        return p_ >= b_ - 1e-6
    comp = {}
    sur = [(mu, rr) for mu, rr in arr if rr[1] <= y0 + 1e-6 < rr[3] < y1 - 1e-6 and rr[0] < x1 and rr[2] > x0]
    if sur and cubre([(max(rr[0], x0), min(rr[2], x1)) for _, rr in sur], x0, x1):
        y0, comp['sur'] = min(rr[3] for _, rr in sur), sorted({mu for mu, _ in sur})
    norte = [(mu, rr) for mu, rr in arr if y0 + 1e-6 < rr[1] < y1 - 1e-6 <= rr[3] and rr[0] < x1 and rr[2] > x0]
    if norte and cubre([(max(rr[0], x0), min(rr[2], x1)) for _, rr in norte], x0, x1):
        y1, comp['norte'] = max(rr[1] for _, rr in norte), sorted({mu for mu, _ in norte})
    oeste = [(mu, rr) for mu, rr in arr if rr[0] <= x0 + 1e-6 < rr[2] < x1 - 1e-6 and rr[1] < y1 and rr[3] > y0]
    if oeste and cubre([(max(rr[1], y0), min(rr[3], y1)) for _, rr in oeste], y0, y1):
        x0, comp['oeste'] = min(rr[2] for _, rr in oeste), sorted({mu for mu, _ in oeste})
    este = [(mu, rr) for mu, rr in arr if x0 + 1e-6 < rr[0] < x1 - 1e-6 <= rr[2] and rr[1] < y1 and rr[3] > y0]
    if este and cubre([(max(rr[1], y0), min(rr[3], y1)) for _, rr in este], y0, y1):
        x1, comp['este'] = max(rr[0] for _, rr in este), sorted({mu for mu, _ in este})
    return {'x': [x0, x1], 'y': [y0, y1], 'compartidos': comp}


def muros_foso(x0, y0, x1, y1, e, z0, z1, compartidos):
    """Muros de un foso (cajas): los lados compartidos con un muro estructural no llevan muro propio."""
    out = []
    ys0 = y0 if 'sur' in compartidos else y0 + e
    ys1 = y1 if 'norte' in compartidos else y1 - e
    if 'sur' not in compartidos:
        out.append(caja(x0, y0, z0, x1, y0 + e, z1))
    if 'norte' not in compartidos:
        out.append(caja(x0, y1 - e, z0, x1, y1, z1))
    if 'oeste' not in compartidos:
        out.append(caja(x0, ys0, z0, x0 + e, ys1, z1))
    if 'este' not in compartidos:
        out.append(caja(x1 - e, ys0, z0, x1, ys1, z1))
    return out


def rects_arranque_muro(ms, S):
    """Planta del arranque de un muro (bajo el piso 1): 1,5 cm más ancha por cada cara contra el relleno, también en los
    extremos libres (no en los que se apoyan en una columna u otro muro), para dar 40 mm de recubrimiento."""
    o = SOBREANCHO_ARRANQUE_MURO
    vecinos = [[c['x'] - c['b'] / 2, c['y'] - c['h'] / 2, c['x'] + c['b'] / 2, c['y'] + c['h'] / 2] for c in S.columnas.values() if c['nivel'] == 1]
    vecinos += [list(rr) for m in S.muros if m['nivel'] == 1 for rr in m['_rects']]

    def toca(rr, k, v):
        # algún vecino con una cara en la coordenada v (eje k) que se solape con rr en el otro eje
        j = 1 - k
        return any(q != list(rr) and (abs(q[k] - v) < 0.002 or abs(q[k + 2] - v) < 0.002) and
                   min(q[j + 2], rr[j + 2]) - max(q[j], rr[j]) > 0.01 for q in vecinos)
    out = []
    for rr in ms['_rects']:
        x0, y0, x1, y1 = rr
        if ms['direccion'] == 'x':          # caras del espesor siempre; extremos solo si están libres
            y0, y1 = y0 - o, y1 + o
            x0 -= 0.0 if toca(rr, 0, rr[0]) else o
            x1 += 0.0 if toca(rr, 0, rr[2]) else o
        else:
            x0, x1 = x0 - o, x1 + o
            y0 -= 0.0 if toca(rr, 1, rr[1]) else o
            y1 += 0.0 if toca(rr, 1, rr[3]) else o
        out.append([x0, y0, x1, y1])
    return out


def restar_rects(R0, huecos):
    """Rectángulo R0 menos los huecos (rectángulos), como lista de rectángulos: franjas en x entre los bordes de los
    huecos, intervalos libres en y en cada franja, y franjas vecinas iguales unidas."""
    hs = []
    for h in huecos:
        q = [max(h[0], R0[0]), max(h[1], R0[1]), min(h[2], R0[2]), min(h[3], R0[3])]
        if q[2] - q[0] > 1e-9 and q[3] - q[1] > 1e-9:
            hs.append(q)
    xs = sorted({round(v, 6) for v in [R0[0], R0[2]] + [h[0] for h in hs] + [h[2] for h in hs]})
    tiras = []
    for x0, x1 in zip(xs, xs[1:]):
        xm = (x0 + x1) / 2
        cub = sorted((h[1], h[3]) for h in hs if h[0] < xm < h[2])
        libres, y = [], R0[1]
        for a, b in cub:
            if a > y + 1e-9:
                libres.append((round(y, 6), round(a, 6)))
            y = max(y, b)
        if y < R0[3] - 1e-9:
            libres.append((round(y, 6), round(R0[3], 6)))
        if tiras and tiras[-1][2] == libres and abs(tiras[-1][1] - x0) < 1e-9:
            tiras[-1] = (tiras[-1][0], x1, libres)
        else:
            tiras.append((x0, x1, libres))
    return [[x0, a, x1, b] for x0, x1, L in tiras for a, b in L]


def _unir_rects(rs):
    """Une rectángulos que se solapan o se tocan (para los huecos del contrapiso)."""
    rs = [list(x) for x in rs]
    cambio = True
    while cambio:
        cambio = False
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                sx, sy = solape_rect(a, b)
                if sx >= -1e-6 and sy >= -1e-6:
                    # solo si la unión es un rectángulo (comparten un lado completo) o uno contiene al otro
                    contiene = (a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]) or (b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3])
                    lado = (abs(a[1] - b[1]) < 1e-6 and abs(a[3] - b[3]) < 1e-6) or (abs(a[0] - b[0]) < 1e-6 and abs(a[2] - b[2]) < 1e-6)
                    if contiene or lado:
                        rs[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                        rs.pop(j)
                        cambio = True
                        break
            if cambio:
                break
    return sorted(rs)


# ================================================================================================= FIJO y DOT
CLASE_MODELO = {
    'lavamanos': ('IfcSanitaryTerminal', 'WASHHANDBASIN'), 'lavamanos_quirurgico': ('IfcSanitaryTerminal', 'WASHHANDBASIN'),
    'inodoro': ('IfcSanitaryTerminal', 'TOILETPAN'), 'ducha': ('IfcSanitaryTerminal', 'SHOWER'), 'poceta_aseo': ('IfcSanitaryTerminal', 'CISTERN'),
    'lavachatas': ('IfcSanitaryTerminal', 'SANITARYFOUNTAIN'), 'barra_apoyo': ('IfcFurniture', 'USERDEFINED'),
    'extintor': ('IfcFireSuppressionTerminal', 'SPRINKLERDEFLECTOR'), 'gabinete_incendio': ('IfcFireSuppressionTerminal', 'HOSEREEL'),
    'senal_evacuacion': ('IfcLightFixture', 'SECURITYLIGHTING'), 'toma_gases_cabecera': ('IfcOutlet', 'USERDEFINED'),
    'llamado_enfermeria': ('IfcCommunicationsAppliance', 'USERDEFINED'), 'transformador': ('IfcTransformer', 'VOLTAGE'),
    'tablero_electrico': ('IfcElectricDistributionBoard', 'DISTRIBUTIONBOARD'), 'banco_baterias': ('IfcElectricFlowStorageDevice', 'BATTERY'),
    'condensadora': ('IfcUnitaryEquipment', 'SPLITSYSTEM'), 'contenedor_residuos': ('IfcFurniture', 'USERDEFINED'),
    'meson': ('IfcFurniture', 'USERDEFINED'), 'montacargas': ('IfcTransportElement', 'LIFTINGGEAR'), 'panel_solar_fila': ('IfcSolarDevice', 'SOLARPANEL'),
    'tanque_agua': ('IfcTank', 'STORAGE'), 'planta_electrica': ('IfcElectricGenerator', 'ENGINEGENERATOR'),
    'ups_central': ('IfcElectricFlowStorageDevice', 'UPS'), 'ascensor_cabina': ('IfcTransportElement', 'ELEVATOR'),
    'montacargas_muestras': ('IfcTransportElement', 'LIFTINGGEAR'), 'manifold_gases': ('IfcMedicalDevice', 'OXYGENPLANT'),
    'generador_psa': ('IfcMedicalDevice', 'OXYGENGENERATOR'), 'equipo_presion': ('IfcPump', 'ENDSUCTION'),
    'tablero_sistema': ('IfcElectricDistributionBoard', 'USERDEFINED'), 'rack': ('IfcCommunicationsAppliance', 'NETWORKAPPLIANCE'),
    'nevera_mortuoria': ('IfcElectricAppliance', 'REFRIGERATOR'),
}
ITEM_FIJO = {'planta_electrica': '10.03', 'ups_central': '10.05', 'ascensor_cabina': '14.01', 'montacargas_muestras': '14.02',
             'manifold_gases': '12.02', 'condensadora': '13.01', 'equipo_presion': '8.17', 'tablero_sistema': '15.01', 'rack': '11.01',
             'nevera_mortuoria': '15.06'}


def dims_unidad(u, l, cat):
    """Medidas de la unidad como las usa el inventario (y el recorrido): primero las propias de la unidad (B las fija cuando
    la pieza o la zona que ocupa no es la nominal de la línea, p. ej. una fila de paneles o una caneca más angosta), luego
    las de la línea, la variante y el modelo del catálogo."""
    m = cat['modelos'].get(l.get('modelo3d')) or {}
    var = u.get('variante') or l.get('variante')
    dim = u.get('dim_m') or l.get('dim_m')
    if not dim and var and (m.get('variantes') or {}).get(var, {}).get('dim_m'):
        dim = m['variantes'][var]['dim_m']
    if not dim:
        dim = m.get('dim_m') or [0.5, 0.5, 0.5]
    return [float(v) for v in dim], u['posicion'][2], var


def inventario(M, inv, cat, pl, cost):
    L = {l['id']: l for l in inv['lineas']}
    recintos = {e['id'] for e in M.elementos if e['clase'] == 'IfcSpace'}
    zs = {n['id']: n['z'] for n in pl['niveles']}
    excluidas = {'fuera_de_la_torre': 0, 'contexto': 0}
    ind_dot = cost.ind_por_grupo('Dotación')
    ind_lab = cost.ind_por_grupo('Laboratorio clínico', 'compra la E.S.E.')
    ind_tic = cost.ind_por_grupo('Sistemas de información', 'Equipos TIC')
    ind_psa = cost.ind_por_grupo('Equipamiento fijo fuera de la obra')
    comp_de = {}
    for u in inv['unidades']:
        if u.get('componente_de'):
            comp_de.setdefault(u['componente_de'], []).append(u['id'])
    for u in inv['unidades']:
        l = L[u['linea']]
        if u.get('estado') == 'fuera_de_la_torre' or not u.get('posicion') or not u.get('nivel'):
            excluidas['fuera_de_la_torre'] += 1
            continue
        if l['capa'] == 'contexto':
            excluidas['contexto'] += 1
            continue
        nid = u['nivel']
        dim, zrel, var = dims_unidad(u, l, cat)
        x, y, _ = u['posicion']
        z = zs[nid] + zrel
        rot = r(u.get('rotacion_z') or 0.0, 4)
        modelo = l.get('modelo3d')
        if modelo == 'panel_solar_fila' and var == 'elevada' and zrel > dim[2]:
            # marquesina o pérgola: el plano de módulos a su altura sobre dos postes de 0,15 m en los extremos que bajan
            # hasta el piso del nivel (como la dibuja el recorrido)
            c_, s_ = math.cos(rot), math.sin(rot)
            partes_ = [{'tipo': 'caja_girada', 'centro': rp([x, y, z]), 'dim': rp(dim, 3), 'rot': rot}]
            for sg in (-1, 1):
                du = sg * (dim[0] / 2 - 0.08)
                partes_.append({'tipo': 'caja_girada', 'centro': rp([x + du * c_, y + du * s_, zs[nid]]), 'dim': [0.15, 0.15, r(zrel, 3)],
                                'rot': rot})
            geo = {'tipo': 'compuesta', 'partes': partes_}
        else:
            geo = {'tipo': 'caja_girada', 'centro': rp([x, y, z]), 'dim': rp(dim, 3), 'rot': rot}
        es_fijo = l['capa'] in ('fijo', 'infraestructura')
        disc = 'FIJO' if es_fijo else 'DOT'
        if es_fijo:
            clase, tipo = CLASE_MODELO.get(modelo, ('IfcBuildingElementProxy', 'NOTDEFINED'))
        else:
            dm = l.get('es_dispositivo_medico')
            if dm in ('si', 'ivd', 'por_confirmar'):
                clase, tipo = 'IfcMedicalDevice', 'USERDEFINED'
            elif l['tipo'] in ('mobiliario', 'cierre'):
                clase, tipo = 'IfcFurniture', 'USERDEFINED'
            else:
                clase, tipo = 'IfcElectricAppliance', 'USERDEFINED'
        # 5D
        costo = []
        if l['capa'] == 'infraestructura':
            cita = (l.get('cita_presupuesto') or [{}])[0].get('item')
            if cita and cita in cost.items:
                it = cost.items[cita]
                costo = [cost.v(cita, 1 if it['unidad'] in ('un', 'juego') else None,
                                None if it['unidad'] in ('un', 'juego') else f'parte del ítem {cita} ({it["unidad"]})')]
        elif l['capa'] == 'fijo':
            item = ITEM_FIJO.get(modelo)
            precio = l.get('precio_unitario_cop_2026')
            if l['nombre'].startswith('Generador de oxígeno'):
                costo = [cost.dot(ind_psa, precio, 'equipamiento fijo fuera de la obra (indirecto del presupuesto)')]
            elif item:
                it = cost.items[item]
                costo = [cost.v(item, 1 if it['unidad'] == 'un' else None, None if it['unidad'] == 'un' else
                                f'ítem global {item}: precio de la línea {precio:,} COP'.replace(',', '.') if precio else None)]
        else:
            precio = l.get('precio_unitario_cop_2026')
            if precio is not None and l['capa'] == 'dotacion':
                if l.get('servicio') in ('laboratorio', 'toma_muestras'):
                    ind = ind_lab
                elif l.get('servicio') in ('tic_apoyo', 'telemedicina'):
                    ind = ind_tic
                else:
                    ind = ind_dot
                costo = [cost.dot(ind, precio)]
            elif precio is not None and l['capa'] == 'cierre_brechas':
                costo = [cost.dot('CIERRE', precio, 'cierre de brechas para la habilitación: suma aparte (no está en presupuesto.json)')]
            elif precio is not None and l['capa'] == 'laboratorio':
                costo = [cost.dot('LAB-MERCADO', precio, 'analizador de laboratorio.json (comodato, programa o compra): valor de '
                                                          'mercado; no suma a la dotación ni al presupuesto')]
        rs = u.get('riesgo_sismico') or {}
        cr = l.get('clase_riesgo') or {}
        ps = {}
        if clase == 'IfcMedicalDevice' or l.get('es_dispositivo_medico') in ('si', 'ivd'):
            ps['Pset_ManufacturerTypeInformation'] = {'ModelLabel': l['nombre'][:120], 'ProductionYear': None}
        ps['Pset_ServiceLife'] = {'ServiceLifeDuration': (l.get('mantenimiento') or {}).get('vida_util_anios')}
        ps = {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in ps.items()}
        ps = {k: v for k, v in ps.items() if v}
        at = atlas_pset('estimación (ubicación del anteproyecto; equipo B)' if disc == 'DOT' else 'estimación (ubicación del anteproyecto; equipo B)',
                        F_INV, 'Res. 3100 de 2019 y Decreto 4725 de 2005' if disc == 'DOT' else 'Res. 3100 de 2019 y Res. 1633 de 2025',
                        None, (l.get('especificacion') or '')[:300])
        at.update({'Servicio': l.get('servicio'), 'Capa': l['capa'], 'Linea': l['id'], 'Montaje': u.get('montaje'),
                   'ClaseRiesgo': cr.get('vigente'), 'RegistroInvima': (l.get('registro_invima') or {}).get('requerido'),
                   'Anclaje': rs.get('anclaje'), 'MasaKg': rs.get('masa_kg'), 'Estado': u.get('estado')})
        cont = u.get('recinto') if u.get('recinto') in recintos else nid
        e = elemento(u['id'], disc, clase, tipo, l['nombre'], nid, geo, 'equipo', at,
                     {QTO_PROPIO: {'GrossVolume': r(dim[0] * dim[1] * dim[2], 4)}}, ps, costo,
                     fase_de(disc, nid), contenedor=cont, objeto_tipo=modelo,
                     analisis={'unidad': u['id'], 'riesgo_sismico': rs} if rs else None,
                     componente_de=u.get('componente_de'), dentro_de=u.get('dentro_de'), componentes=comp_de.get(u['id']))
        M.agregar(e)
    return excluidas


# ============================================================================================ preparación de A
def preparar_estructura(S, est, pl):
    """Cajas de vigas (de cara a cara), rectángulos de muros (sin la columna de borde), geometría de las losas con sus
    apoyos, y la información que necesita el despiece de vigas."""
    ref = est['refuerzo']
    rec_col = ref['convenciones']['recubrimientos_m']['columna']
    cols_por_k = {}
    for c in ref['columnas']:
        cols_por_k.setdefault(c['nivel'], []).append(c)
    info_vigas = {}
    for v in ref['vigas']:
        xi, yi, z = v['xyz_i']
        xj, yj, _ = v['xyz_j']
        eje = 'x' if abs(yi - yj) < 1e-9 else 'y'
        c = yi if eje == 'x' else xi
        ni, nj = (xi, xj) if eje == 'x' else (yi, yj)
        if v.get('tipo'):
            si, sj = min(ni, nj), max(ni, nj)
            di = dj = 0.0
            nodo_i, nodo_j = si, sj
        else:
            di, dj = S.arms.get(v['id'], [0.0, 0.0])
            if ni > nj:
                ni, nj, di, dj = nj, ni, dj, di
            nodo_i, nodo_j = ni, nj
            si, sj = ni + di, nj - dj
        k = v['nivel']

        def col(s):
            x_, y_ = (s, c) if eje == 'x' else (c, s)
            for cc in cols_por_k.get(k, []):
                if abs(cc['x'] - x_) < 1e-6 and abs(cc['y'] - y_) < 1e-6:
                    return cc
            return None
        ci, cj = col(nodo_i), col(nodo_j)

        def barras_nudo(s):
            # barras de la columna que atraviesan el nudo: las del piso de arriba (traslapan a media altura del piso)
            x_, y_ = (s, c) if eje == 'x' else (c, s)
            for kk in (k + 1, k):
                for cc in cols_por_k.get(kk, []):
                    if abs(cc['x'] - x_) < 1e-6 and abs(cc['y'] - y_) < 1e-6:
                        lo_ = cc['longitudinal']
                        bb, _c, _nf = DSP._caras_columna(lo_['n'], lo_['num'], cc['b'], rec_col, cc['estribos']['num'])
                        return [(x_ + px, y_ + py, DSP.db_de(lo_['num'])) for (px, py), _n in bb]
            return []
        info_vigas[v['id']] = {'barras_col_i': barras_nudo(nodo_i), 'barras_col_j': barras_nudo(nodo_j),'eje': eje, 'c': c, 'z': z, 'nodo_i': nodo_i, 'nodo_j': nodo_j, 's_i': si, 's_j': sj,
                               'medio_col_i': (ci['b'] / 2) if ci else 0.0, 'medio_col_j': (cj['b'] / 2) if cj else 0.0,
                               'db_col_i': DSP.db_de(ci['longitudinal']['num']) if ci else 0.0,
                               'db_col_j': DSP.db_de(cj['longitudinal']['num']) if cj else 0.0}
        b, h = v['b'], v['h']
        if eje == 'x':
            v['_caja'] = ([si, c - b / 2, z - h], [sj, c + b / 2, z])
        else:
            v['_caja'] = ([c - b / 2, si, z - h], [c + b / 2, sj, z])
        v['_Lf'] = sj - si
    # nudos exteriores (como A: ningún otro tramo de la misma línea del pórtico llega a ese nudo)
    lineas = {}
    for v in ref['vigas']:
        lineas.setdefault((v['portico'], v['nivel']), []).append(v)
    for vs in lineas.values():
        port = [w for w in vs if not w.get('tipo')]
        for v in vs:
            iv = info_vigas[v['id']]
            if v.get('tipo'):
                iv['ext_i'] = iv['ext_j'] = False
                continue
            iv['ext_i'] = not any(abs(info_vigas[w['id']]['nodo_j'] - iv['nodo_i']) < 1e-6 for w in port if w is not v)
            iv['ext_j'] = not any(abs(info_vigas[w['id']]['nodo_i'] - iv['nodo_j']) < 1e-6 for w in port if w is not v)
    # muros: rectángulos sin la columna de borde y extremos del alma
    for m in ref['muros']:
        cols = [cc for cc in cols_por_k.get(m['nivel'], [])]
        rects = []
        for rr in m['planta']:
            es_col = any(abs(rr[0] - (cc['x'] - cc['b'] / 2)) < 1e-6 and abs(rr[2] - (cc['x'] + cc['b'] / 2)) < 1e-6 and
                         abs(rr[1] - (cc['y'] - cc['h'] / 2)) < 1e-6 and abs(rr[3] - (cc['y'] + cc['h'] / 2)) < 1e-6 for cc in cols)
            if not es_col:
                rects.append(list(rr))
        m['_rects'] = rects
        eje = m['direccion']
        alma = max(rects, key=lambda rr: (rr[2] - rr[0]) if eje == 'x' else (rr[3] - rr[1]))
        if eje == 'x':
            m['_alma'] = (alma[0], alma[2], (alma[1] + alma[3]) / 2)
        else:
            m['_alma'] = (alma[1], alma[3], (alma[0] + alma[2]) / 2)
    # losas: apoyos (vigas en y o muros) y geometría (loseta entre caras de vigas, nervios, riostra)
    vigas_y = {}
    vigas_x = {}
    for v in ref['vigas']:
        iv = info_vigas[v['id']]
        (vigas_y if iv['eje'] == 'y' else vigas_x).setdefault(v['nivel'], []).append((iv, v))
    muros_k = {}
    for m in ref['muros']:
        muros_k.setdefault(m['nivel'], []).append(m)

    def apoyo(eje_linea, coord, a0, a1, k):
        """Semiancho de la viga o muro en la línea (x = coord si eje_linea == 'y') que cubre [a0, a1]."""
        hb = 0.0
        cubre = 0.0
        for iv, v in (vigas_y if eje_linea == 'y' else vigas_x).get(k, []):
            if abs(iv['c'] - coord) < 1e-6:
                s0, s1 = iv['nodo_i'], iv['nodo_j']
                sol = min(s1, a1) - max(s0, a0)
                if sol > 1e-6:
                    hb = max(hb, v['b'] / 2)
                    cubre += sol
        for m in muros_k.get(k, []):
            for rr in m['_rects']:
                if eje_linea == 'y' and rr[0] - 1e-6 <= coord <= rr[2] + 1e-6:
                    sol = min(rr[3], a1) - max(rr[1], a0)
                    if sol > 1e-6:
                        hb = max(hb, coord - rr[0] if coord - rr[0] > 1e-6 else (rr[2] - rr[0]) / 2)
                        cubre += sol
                if eje_linea == 'x' and rr[1] - 1e-6 <= coord <= rr[3] + 1e-6:
                    sol = min(rr[2], a1) - max(rr[0], a0)
                    if sol > 1e-6:
                        hb = max(hb, coord - rr[1] if coord - rr[1] > 1e-6 else (rr[3] - rr[1]) / 2)
                        cubre += sol
        return hb, cubre
    # vigas banda (columna-muro) más anchas que el muro: la losa tampoco se mete en ellas
    bandas_k = {}
    for v in ref['vigas']:
        if v.get('tipo'):
            iv = info_vigas[v['id']]
            rr = ([iv['s_i'], iv['c'] - v['b'] / 2, iv['s_j'], iv['c'] + v['b'] / 2] if iv['eje'] == 'x'
                  else [iv['c'] - v['b'] / 2, iv['s_i'], iv['c'] + v['b'] / 2, iv['s_j']])
            bandas_k.setdefault(v['nivel'], []).append(rr)
    for p in ref['losas']:
        k = p['nivel']
        x0, x1, y0, y1, z = p['x0'], p['x1'], p['y0'], p['y1'], p['z']
        nv = p['nervios']
        hb0, c0 = apoyo('y', x0, y0, y1, k)
        hb1, c1 = apoyo('y', x1, y0, y1, k)
        hy0, _ = apoyo('x', y0, x0, x1, k)
        hy1, _ = apoyo('x', y1, x0, x1, k)
        sin = []
        for lado, cubre, xx in (('x0', c0, x0), ('x1', c1, x1)):
            if cubre < (y1 - y0) - 0.05:
                sin.append({'borde': f'x = {_m(xx)}', 'apoyado_m': r(cubre, 2), 'largo_m': r(y1 - y0, 2)})
        p['_sin_apoyo'] = sin
        p['_apoyo_x'] = (hb0, hb1)
        xa, xb = x0 + hb0, x1 - hb1
        ya, yb = y0 + hy0, y1 - hy1
        # obstáculos del piso (columnas que llegan a la losa y muros estructurales): la losa no se mete en ellos
        obst = [[cc['x'] - cc['b'] / 2, cc['y'] - cc['h'] / 2, cc['x'] + cc['b'] / 2, cc['y'] + cc['h'] / 2]
                for cc in cols_por_k.get(k, [])] + [rr for m in muros_k.get(k, []) for rr in m['_rects']] + bandas_k.get(k, [])
        # la loseta llega hasta la cara de cada apoyo a lo largo del borde (no hasta la del más ancho): paño entre ejes menos
        # vigas, muros, vigas banda y columnas
        vig_k = [[iv_['s_i'], iv_['c'] - v_['b'] / 2, iv_['s_j'], iv_['c'] + v_['b'] / 2] if iv_['eje'] == 'x' else
                 [iv_['c'] - v_['b'] / 2, iv_['s_i'], iv_['c'] + v_['b'] / 2, iv_['s_j']]
                 for iv_, v_ in vigas_x.get(k, []) + vigas_y.get(k, []) if not v_.get('tipo')]
        loseta = restar_rects([x0, y0, x1, y1], obst + vig_k)
        partes = [caja(q[0], q[1], z - nv['loseta_m'], q[2], q[3], z) for q in loseta]
        n_n = nv['n']
        ys = [y0 + (y1 - y0) * (i + 0.5) / n_n for i in range(n_n)]
        bw = nv['b_m']
        for yy in ys:
            for q in restar_rects([xa, yy - bw / 2, xb, yy + bw / 2], obst):
                partes.append(caja(q[0], q[1], z - nv['h_m'], q[2], q[3], z - nv['loseta_m']))
        xr = (x0 + x1) / 2
        # riostra a la mitad de la luz, entre nervios
        bordes = [ya] + [q for yy in ys for q in (yy - bw / 2, yy + bw / 2)] + [yb]
        for i in range(0, len(bordes), 2):
            a_, b_ = bordes[i], bordes[i + 1]
            if b_ - a_ > 0.01:
                for q in restar_rects([xr - bw / 2, a_, xr + bw / 2, b_], obst):
                    partes.append(caja(q[0], q[1], z - nv['h_m'], q[2], q[3], z - nv['loseta_m']))
        p['_geo'] = {'tipo': 'compuesta', 'partes': partes}
        p['_area_neta'] = sum((q[2] - q[0]) * (q[3] - q[1]) for q in loseta)
        p['_y_caras'] = (ya, yb)

    def apoyos_x(x, y0, y1, k):
        return apoyo('y', x, y0, y1, k)[0]
    return info_vigas, apoyos_x


def bases_cimentacion(est):
    """Cara superior del dado o losa de pilotes bajo cada columna y muro, y z del tope de su parrilla inferior."""
    C = est['cimentacion']
    rec = 0.075
    out = {}
    for d in C['dados']:
        ix, iy = d['refuerzo']['inferior_x'], d['refuerzo']['inferior_y']
        zp = d['z_fondo'] + rec + DSP.db_de(ix['num']) + DSP.db_de(iy['num'])
        for a in d['apoyos']:
            tipo = 'columna' if a.startswith('C-') else 'muro'
            out[a] = {'tipo': tipo, 'apoyo': d['id'], 'z_tope': d['z_tope'], 'z_parrilla': zp,
                      'host_arranque': f'ARR-{a}'}
    return out


# =============================================================================================== refuerzo y 5D
def capas_de_vigas(J, S):
    """Cotas (z, db) de las barras de las vigas que cruzan cada nudo de columna (línea, piso): los estribos del nudo
    se corren para no coincidir con ellas."""
    cols = list(S.columnas.values())
    out = {}
    for j in J.lista:
        if not j['rol'].endswith('_corrida'):
            continue
        f = j['forma']
        for c in j['copias']:
            for a, b in zip(f, f[1:]):
                if abs(a[2] - b[2]) > 1e-6:
                    continue
                z = a[2] + c[2]
                xa, xb = sorted((a[0] + c[0], b[0] + c[0]))
                ya, yb = sorted((a[1] + c[1], b[1] + c[1]))
                for cc in cols:
                    if abs(cc['z1'] - z) > 1.0 or z > cc['z1'] or z < cc['z1'] - 1.0:
                        continue
                    if xa <= cc['x'] + cc['b'] / 2 and xb >= cc['x'] - cc['b'] / 2 and ya <= cc['y'] + cc['h'] / 2 and yb >= cc['y'] - cc['h'] / 2:
                        out.setdefault((cc['id'].rsplit('-', 1)[0], cc['nivel']), set()).add((round(z, 4), j['db']))
    return {k: sorted(v) for k, v in out.items()}


def refuerzo(M, S, est, bases, info_vigas, apoyos_x, tramos_esc, cost):
    J = DSP.Juegos()
    res_vig = DSP.vigas(J, est, None, info_vigas)
    res_col = DSP.columnas(J, est, bases, capas_de_vigas(J, S))
    obst = {}
    for c in S.columnas.values():
        obst.setdefault(c['nivel'], []).append([c['x'] - c['b'] / 2, c['y'] - c['h'] / 2, c['x'] + c['b'] / 2, c['y'] + c['h'] / 2])
    for m in S.muros:
        obst.setdefault(m['nivel'], []).extend([list(rr) for rr in m['_rects']])
    DSP.losas(J, est, apoyos_x, obst)
    DSP.muros(J, est, bases)
    DSP.escaleras(J, est, tramos_esc, obst)
    DSP.pilotes(J, est, lambda g, k: f'PIL-{g}-{k + 1}')
    dados_dib = DSP.dados(J, est)
    DSP.vigas_amarre(J, est)
    DSP.fosos_y_cisternas(J, est, {f['id']: huella_foso(f, S, bases) for f in est['cimentacion']['fosos']})
    huecos = []
    for c in S.columnas.values():
        if c['nivel'] == 1:
            o = SOBREANCHO_ARRANQUE
            huecos.append([c['x'] - c['b'] / 2 - o, c['y'] - c['h'] / 2 - o, c['x'] + c['b'] / 2 + o, c['y'] + c['h'] / 2 + o])
    for m in S.muros:
        if m['nivel'] == 1:
            huecos += rects_arranque_muro(m, S)
    for f in est['cimentacion']['fosos']:
        huecos.append([f['x'][0], f['y'][0], f['x'][1], f['y'][1]])
    DSP.contrapiso(J, est, planta_contrapiso(est), huecos)
    # los muros de contención al final: sus barras pasan entre las de la viga de amarre, el dado, el arranque y el contrapiso
    res_mc = DSP.muros_contencion(J, est, planta_contrapiso(est))
    for mid, q in sorted(res_mc.items()):
        if q['sin_lugar']:
            print(f'  aviso: {q["sin_lugar"]} barras del muro {mid} no encontraron lugar libre (quedan en su posición nominal): '
                  + '; '.join(q.get('detalle', [])))
    # parrillas de los dados: lo dibujado frente al prediseño (barras, separación y área de acero) para la ficha
    for hid, info in dados_dib.items():
        e_ = M.por_id.get(hid)
        if e_ is not None:
            e_['parrillas_dibujadas'] = {k: v for k, v in info.items() if k.startswith('inferior_')}
    # enlazar con los elementos: GlobalId, nivel, 4D y 5D (acero de superestructura 3.05 o de cimentación 2.13)
    for j in J.lista:
        h = M.por_id.get(j['host'])
        if h is None:
            raise SystemExit(f'el juego {j["id"]} no tiene elemento anfitrión ({j["host"]})')
        j['guid'] = guid('refuerzo|' + j['id'])
        j['nivel'] = h['nivel']
        j['fase'] = h['fase']
        j['disciplina'] = 'REF'
        cim = h['disciplina'] == 'CIM'
        c5 = cost.v('2.13' if cim else '3.05', j['kg'])
        j['costo'] = [{'item': c5['item'], 'cantidad': c5['cantidad'], 'valor': c5['valor']}]
        rol = j['rol']
        for k in ('kg_m', 'diam_mm', 'zona', 'ganchos', 'nota'):
            if j.get(k) is None:
                j.pop(k, None)
        j['tipo_predefinido'] = ('LIGATURE' if ('estribo' in rol or 'gancho' in rol or rol == 'espiral') else
                                 'EDGE' if rol.startswith('borde') else 'MAIN')
    # cortinas de los muros: paso de las filas horizontales en toda la altura (a través de las losas) y de las verticales
    cort = {}
    for mid, v in sorted(DSP.VERIF_CORTINAS.items()):
        fz = sorted(v['filas'])
        # paso entre filas consecutivas frente al s del tramo (entre dos pisos, el mayor de los dos)
        exc_h = max([(b[0] - a[0]) - max(a[1], b[1]) for a, b in zip(fz, fz[1:])] or [0.0])
        exc_v = max([p_ - s_ for p_, s_ in v['verticales'].values()] or [0.0])
        cort[mid] = {'s_h_m': sorted({q[1] for q in fz}), 'paso_h_max_m': r(DSP.paso_max([q[0] for q in fz]), 4),
                     'exceso_h_m': r(max(exc_h, 0.0), 4), 's_v_m': sorted({q[1] for q in v['verticales'].values()}),
                     'paso_v_max_m': r(max(q[0] for q in v['verticales'].values()), 4), 'exceso_v_m': r(max(exc_v, 0.0), 4),
                     'filas': len(fz)}
    verif = {'nota': ('Estribos: conteo del modelo frente a los juegos de A y paso máximo entre estribos consecutivos (en la zona '
                      'confinada frente a s_lo o s_2h, y en toda la luz frente a s del centro; en las columnas, del primer estribo '
                      'sobre el piso al último del nudo, bajo las barras superiores de las vigas). Cortinas: paso máximo entre filas '
                      'horizontales en toda la altura del muro (también a través de las losas) y entre verticales.'),
             'columnas': res_col, 'vigas': res_vig, 'cortinas': cort}
    return J.lista, verif


def cantidades_y_5d(M, refs, cost, est):
    """Concreto (m³) y acero (kg) por disciplina y capítulo, frente a presupuesto.json y a las cantidades de A."""
    por_item = {}
    for e in M.elementos:
        for c in e['costo']:
            q = por_item.setdefault(c['item'], {'cantidad': 0.0, 'valor': 0.0, 'n': 0, 'sin_cantidad': 0})
            q['n'] += 1
            if c['cantidad'] is None:
                q['sin_cantidad'] += 1
            else:
                q['cantidad'] += c['cantidad']
                q['valor'] += c['valor'] or 0.0
    for j in refs:
        c = j['costo'][0]
        q = por_item.setdefault(c['item'], {'cantidad': 0.0, 'valor': 0.0, 'n': 0, 'sin_cantidad': 0})
        q['n'] += 1
        q['cantidad'] += c['cantidad']
        q['valor'] += c['valor']
    filas = []
    for codigo in sorted(por_item, key=_orden_item):
        q = por_item[codigo]
        if codigo in cost.items:
            it = cost.items[codigo]
            pres_c = it['cantidad']
            con_cant = q['n'] - q['sin_cantidad']
            dif = q['cantidad'] - pres_c if con_cant and it['unidad'] != 'global' else None
            filas.append({'item': codigo, 'capitulo': it['capitulo'], 'descripcion': it['descripcion'], 'unidad': it['unidad'],
                          'apu': it['apu'], 'valor_unitario': it['valor_unitario'], 'presupuesto_cantidad': pres_c,
                          'presupuesto_valor': it['total'], 'bim_cantidad': r(q['cantidad'], 3) if con_cant else None,
                          'bim_valor': r(q['valor'], 0) if con_cant else None, 'elementos': q['n'],
                          'diferencia': r(dif, 3) if dif is not None else None,
                          'diferencia_pct': r(100 * dif / pres_c, 1) if dif is not None and pres_c else None,
                          'efecto_cop': r(dif * it['valor_unitario'], 0) if dif is not None else None,
                          'nota': (f'{q["sin_cantidad"]} elementos enlazados sin cantidad propia (ítem global o incluido en el m² de otro)'
                                   if q['sin_cantidad'] else None)})
        else:
            ind = cost.indirectos[codigo]
            filas.append({'item': codigo, 'capitulo': 'indirectos', 'descripcion': ind['descripcion'], 'unidad': 'global', 'apu': None,
                          'valor_unitario': None, 'presupuesto_cantidad': 1 if ind['valor'] is not None else None,
                          'presupuesto_valor': ind['valor'], 'bim_cantidad': None,
                          'bim_valor': r(q['valor'], 0), 'elementos': q['n'], 'diferencia': None, 'diferencia_pct': None,
                          'efecto_cop': r(q['valor'] - ind['valor'], 0) if ind['valor'] is not None else None,
                          'nota': ('suma de los precios de las unidades del inventario frente al valor del indirecto' if ind['valor'] is not None
                                   else 'fuera de presupuesto.json: se informa su valor')})
    # concreto y acero por disciplina y por tipo de A
    conc = {}
    for e in M.elementos:
        if e.get('material') in ('concreto_28', 'concreto_21') and e['clase'] not in ('IfcStair', 'IfcElementAssembly'):
            V = volumen(e['geometria'])
            d = conc.setdefault(e['disciplina'], {'m3': 0.0, 'kg': 0.0, 'por_clase': {}})
            d['m3'] += V
            d['por_clase'][e['clase']] = d['por_clase'].get(e['clase'], 0.0) + V
    host_disc = {e['id']: e['disciplina'] for e in M.elementos}
    for j in refs:
        d = conc.setdefault(host_disc[j['host']], {'m3': 0.0, 'kg': 0.0, 'por_clase': {}})
        d['kg'] += j['kg']
    disciplinas = {k: {'concreto_m3': r(v['m3'], 2), 'acero_kg': r(v['kg'], 0), 'cuantia_kg_m3': r(v['kg'] / v['m3'], 1) if v['m3'] else None,
                       'concreto_por_clase_m3': {kk: r(vv, 2) for kk, vv in sorted(v['por_clase'].items())}} for k, v in sorted(conc.items())}
    # frente a A (cantidades.por_tipo)
    grupos = {'columnas': ('IfcColumn', 'EST'), 'vigas': ('IfcBeam', 'EST'), 'losas': ('IfcSlab', 'EST'), 'muros': ('IfcWall', 'EST')}
    tipoA = est['cantidades']['por_tipo']
    kg_host = {}
    for j in refs:
        kg_host[j['host']] = kg_host.get(j['host'], 0.0) + j['kg']
    def suma(filtro):
        V = kg = 0.0
        for e in M.elementos:
            if filtro(e):
                V += volumen(e['geometria']) if e['clase'] not in ('IfcStair', 'IfcElementAssembly') else 0.0
                kg += kg_host.get(e['id'], 0.0)
        return V, kg
    filtros = {
        'columnas': lambda e: e['disciplina'] == 'EST' and e['clase'] == 'IfcColumn',
        'muros': lambda e: e['disciplina'] == 'EST' and e['clase'] == 'IfcWall',
        'vigas': lambda e: e['disciplina'] == 'EST' and e['clase'] == 'IfcBeam',
        'losas': lambda e: e['disciplina'] == 'EST' and e['clase'] == 'IfcSlab',
        'escaleras': lambda e: (e.get('parte_de') or e['id']).startswith(('ESC-N', 'ESC-S')),
        'pilotes': lambda e: e['clase'] == 'IfcPile',
        'dados_y_losas_de_pilotes': lambda e: e['clase'] == 'IfcFooting' and e['tipo_predefinido'] == 'PILE_CAP',
        'vigas_de_amarre': lambda e: e['clase'] == 'IfcFooting' and e['tipo_predefinido'] == 'FOOTING_BEAM',
        'fosos_y_cisternas': lambda e: e['id'].startswith(('FOSO', 'CIS')),
        'muros_de_contencion': lambda e: e.get('objeto_tipo') == 'RETAININGWALL',
        'contrapiso': lambda e: e['id'] == 'CP-1',
        'arranques': lambda e: e['id'].startswith('ARR-'),
    }
    frente_A = []
    for k, f in filtros.items():
        V, kg = suma(f)
        a = tipoA.get(k, {'m3': 0.0, 'kg': 0.0})
        frente_A.append({'tipo': k, 'bim_m3': r(V, 2), 'A_m3': a['m3'], 'dif_m3': r(V - a['m3'], 2), 'bim_kg': r(kg, 0), 'A_kg': a['kg'],
                         'dif_kg': r(kg - a['kg'], 0)})
    return filas, disciplinas, frente_A


def notas_frente_a_A(frente_A):
    """Por qué el acero dibujado difiere del que cuenta A, por tipo (cálculo propio con las cifras de frente_a_A)."""
    f = {x['tipo']: x for x in frente_A}

    def kg(t):
        return f'{f[t]["dif_kg"]:+,.0f} kg'.replace(',', '.') if t in f else ''
    return {
        'escaleras': (f'{kg("escaleras")}: el modelo arma cada tramo en su ancho real y cada descanso una sola vez, en su planta, '
                      'como losa en dos direcciones (las principales de los tramos siguen por el descanso, se agregan donde no '
                      'llegan y la repartición lo cruza entero); el descanso de cada piso es el de llegada de la escalera de abajo '
                      'y en el piso 1 es el contrapiso. el prediseño cuenta por piso dos descansos y el ancho de los dos tramos (4,80 m) por '
                      'el largo total de tramos y descansos.'),
        'columnas': (f'{kg("columnas")}: el modelo reparte los estribos del centro desde el último de la zona confinada (el paso '
                     'no pasa de s en la transición) y agrega estribos en el nudo para no cruzar las barras de las vigas; el prediseño cuenta '
                     'cada piso con su largo más el traslapo.'),
        'muros': (f'{kg("muros")}: el modelo lleva la cortina horizontal continua a través de las losas y por el arranque hasta la '
                  'losa de pilotes, con horquillas en U en los extremos (y bajo la cubierta, en las verticales), y confina los '
                  'bordes también en el arranque; el prediseño no cuenta esas barras.'),
        'losas': (f'{kg("losas")}: la malla de la loseta se corta en columnas y muros; el prediseño la cuenta sobre el área a ejes.'),
    }


def _orden_item(c):
    if c.startswith('IND'):
        return (999, int(c[4:]))
    if '.' not in c:
        return (1000, c)
    a, b = c.split('.')
    return (int(a), int(b))


# ========================================================================================================= main
def generar():
    pl = leer(INSUMOS['plantas'])
    est = leer(INSUMOS['estructura'])
    inv = leer(INSUMOS['inventario'])
    cat = leer(INSUMOS['catalogo'])
    pres = leer(INSUMOS['presupuesto'])
    apu = leer(INSUMOS['apu'])
    prog = leer(INSUMOS['programa'])
    etapas = leer_cronograma(INSUMOS['cronograma'])
    ancla = prog['implantacion']['marco_de_coordenadas']['ancla']
    cost = Costos(pres, apu)
    S = Estructura(est)
    info_vigas, apoyos_x = preparar_estructura(S, est, pl)
    bases = bases_cimentacion(est)
    M = Modelo()
    niveles = niveles_ifc(pl, est)
    fases = fases_4d(etapas)
    res_arq = arquitectura(M, pl, S, cost, niveles, bases)
    tramos_esc = escaleras_arq(M, pl, S, cost, est)
    estructura(M, S, cost, est)
    cimentacion(M, S, cost, est, bases)
    excl = inventario(M, inv, cat, pl, cost)
    refs, res_col = refuerzo(M, S, est, bases, info_vigas, apoyos_x, tramos_esc, cost)
    filas5d, disciplinas, frente_A = cantidades_y_5d(M, refs, cost, est)
    # limpiar claves internas y completar
    for e in M.elementos:
        for k in [k for k in e if k.startswith('_')]:
            del e[k]
        e['psets'] = {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in e['psets'].items()}
        e['psets'] = {k: v for k, v in e['psets'].items() if v}
        e['atlas'] = {k: v for k, v in e['atlas'].items() if v is not None}
        for k in ('objeto_tipo', 'componente_de', 'dentro_de', 'componentes', 'vano', 'muro_host', 'parte_de', 'partes',
                  'apoyos_sin_estructura', 'analisis'):
            if k in e and e[k] in (None, [], {}):
                del e[k]
    geo = georreferencia(ancla)
    conteo = {}
    for e in M.elementos:
        d = conteo.setdefault(e['disciplina'], {})
        d[e['clase']] = d.get(e['clase'], 0) + 1
    conteo['REF'] = {'IfcReinforcingBar': len(refs)}
    barras = sum(j['n'] for j in refs)
    kg = sum(j['kg'] for j in refs)
    ins = {rel(p): sha1(p) for p in INSUMOS.values()}
    for p in sorted((Path(__file__).parent).glob('*.py')):
        if p.name in ('generar_bim.py', 'despiece.py', 'comun.py'):
            ins[rel(p)] = sha1(p)
    fecha = max(pl.get('fecha', ''), est.get('fecha', ''), inv.get('fecha', ''))
    out = {
        'id': 'torre_hospital_bim',
        'version': 1,
        'nombre': 'Modelo BIM federado de la torre de servicios de primer nivel (Hospital Héctor Abad Gómez, Yondó)',
        'generado_por': 'scripts/bim/generar_bim.py',
        'fecha': fecha,
        'tipo_dato': 'cálculo propio (modelo de prefactibilidad sobre el anteproyecto de B y el prediseño de A)',
        'estado': AVISO,
        'esquema': ('IFC4 (ADD2 TC1); clases de IFC4; conjuntos Pset_ y Qto_ según las plantillas de IFC4 ADD2 (validar_ifc.py los compara '
                    'con ellas: nombre, propiedad, tipo de dato y forma); lo que IFC4 no define va en los conjuntos propios '
                    'AtlasYondo_Torre, AtlasYondo_Refuerzo y AtlasYondo_Cantidades'),
        'insumos_sha1': ins,
        'georreferenciacion': {
            'ancla': ancla, 'crs': 'EPSG:9377', 'crs_nombre': 'MAGNA-SIRGAS 2018 / Origen-Nacional', 'proyeccion': 'Transverse Mercator',
            'parametros': 'φ0 = 4° N, λ0 = 73° W, k0 = 0,9992, falso este 5.000.000 m, falso norte 2.000.000 m, GRS 1980',
            'este_m': r(geo['este'], 3), 'norte_m': r(geo['norte'], 3), 'eje_x_abscisa': r(geo['eje_x'][0], 9),
            'eje_x_ordenada': r(geo['eje_x'][1], 9), 'convergencia_deg': r(geo['convergencia_deg'], 6),
            'factor_escala_punto': r(geo['factor_escala'], 7), 'escala_ifc': 1.0,
            'altura_ortometrica_m': 75.0,
            'nota': ('Este y norte del ancla del contrato (sección 0) con las fórmulas de Krüger (cálculo propio; coinciden con PROJ a menos '
                     'de 1 mm, que es el redondeo del valor guardado; ver validacion_ifc.json). El eje x del proyecto es el este verdadero: en la cuadrícula gira '
                     'la convergencia de meridianos. La escala de IfcMapConversion queda en 1 porque las unidades son las mismas '
                     '(metro); el factor de escala del punto se informa aparte. La altura del ±0,00 (75 m s. n. m.) es una estimación '
                     '(rango de 75-100 m de normas.json): la fija el levantamiento topográfico.'),
            'tipo_dato': 'cálculo propio; altura: estimación'},
        'niveles': niveles,
        'disciplinas': DISCIPLINAS,
        'nota_lod': ('LOD objetivo: el del plan BIM (especificación 17.4) para un modelo coordinado. Estado actual: lo que el modelo es '
                     'hoy (prefactibilidad sobre un anteproyecto y un prediseño sin firmar); la web le suma las interferencias duras '
                     'pendientes de cada disciplina. LOIN: nivel de información necesario (geometría, información alfanumérica y '
                     'documentación) con el tipo de dato de cada parte.'),
        'materiales': MATERIALES,
        'presupuesto': {'items': {k: cost.items[k] for k in sorted(cost.usados, key=_orden_item) if k in cost.items},
                        'indirectos': {k: cost.indirectos[k] for k in sorted(cost.usados, key=_orden_item) if k in cost.indirectos},
                        'apu': {k: v for k, v in cost.apu.items() if any(cost.items[i]['apu'] == k for i in cost.usados if i in cost.items)},
                        'moneda': pres.get('moneda_y_base')},
        'cronograma': {'fuente': 'docs/11-torre-hospital-nivel-1.md, sección 10', 'etapas': etapas, 'fases': fases,
                       'nota': 'Las etapas son del cronograma (dato del proyecto); su reparto por piso y disciplina es una estimación de este modelo.'},
        'conteos': {k: dict(sorted(v.items())) for k, v in sorted(conteo.items())},
        'totales': {'elementos': len(M.elementos), 'juegos_de_barras': len(refs), 'barras': barras, 'acero_kg': r(kg, 0),
                    'unidades_excluidas': excl, 'muros_cortados_en_columnas': res_arq['muros_cortados'],
                    'muros_de_nucleo_que_son_estructura': res_arq['muros_nucleo_a_est']},
        'contexto_del_recorrido': {
            'nota': ('El nivel EXT de las plantas repite, para que el recorrido sea continuo, el perímetro de la torre (fachada, puertas de '
                     'acceso y huella) que ya modelan el piso 1 y el bloque técnico. Esos objetos no se modelan dos veces: quedan fuera '
                     'del BIM, del IFC y de las cantidades 5D (criterio del modelo).'),
            'omitidos': [dict(id=k, **v) for k, v in sorted(res_arq['contexto'].items())]},
        'cantidades': {'por_disciplina': disciplinas, 'frente_a_A': frente_A,
                       'nota': ('Volúmenes de la geometría del modelo (columnas de piso a piso; vigas entre caras de columnas; losas '
                                'entre caras de vigas con nervios y riostra; muros sin la columna de borde) y acero de los juegos de '
                                'barras dibujados. A mide las losas con el espesor equivalente sobre el área a ejes y descuenta de las '
                                'vigas ese espesor; por eso cambian vigas y losas por separado y casi nada su suma.'),
                       'notas_por_tipo': notas_frente_a_A(frente_A)},
        'comparacion_presupuesto': filas5d,
        'elementos': M.elementos,
        'refuerzo': refs,
        'verificacion_estribos': res_col,
    }
    return out


def main():
    out = generar()
    if '--verificar' in sys.argv:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / 'x.json'
            escribir_json(tmp, out, ('elementos', 'refuerzo'))
            igual = SALIDA.exists() and tmp.read_bytes() == SALIDA.read_bytes()
        print('al día' if igual else 'DESACTUALIZADO: corra python3 scripts/bim/generar_bim.py')
        sys.exit(0 if igual else 1)
    n = escribir_json(SALIDA, out, ('elementos', 'refuerzo'))
    t = out['totales']
    print(f'{rel(SALIDA)}: {n / 1e6:.2f} MB; {t["elementos"]} elementos, {t["juegos_de_barras"]} juegos de barras '
          f'({t["barras"]} barras, {t["acero_kg"]:,.0f} kg)'.replace(',', '.'))
    for k, v in out['conteos'].items():
        print(f'  {k}: ' + ', '.join(f'{c} {n_}' for c, n_ in v.items()))


if __name__ == '__main__':
    main()
