"""Exporta el modelo BIM de la torre a IFC4 (escritor STEP propio, determinista; solo biblioteca estándar).

    python3 scripts/bim/exportar_ifc.py               # web/models/torre_hospital.ifc (+ torre_hospital_refuerzo.ifc)
    python3 scripts/bim/exportar_ifc.py --verificar   # regenera en memoria y compara con los archivos

Lee data/bim/torre_hospital.bim.json (generar_bim.py). Si el modelo completo pasa de LIMITE_MB, se parte en dos
archivos federados que comparten los GlobalId del proyecto, el sitio, el edificio, los niveles, las fases y las
partidas: torre_hospital.ifc (ARQ + EST + CIM + FIJO + DOT) y torre_hospital_refuerzo.ifc (REF).

Contenido: IfcProject con unidades SI y pesos colombianos; contexto con norte verdadero; IfcSite georreferenciado
(IfcMapConversion e IfcProjectedCRS EPSG:9377 desde el ancla del contrato); IfcBuilding e IfcBuildingStorey; IfcSpace
por recinto; muros, losas, columnas, vigas, escaleras, puertas y ventanas con sus vanos (IfcOpeningElement,
IfcRelVoidsElement, IfcRelFillsElement); dados, vigas de amarre y pilotes; refuerzo como IfcReinforcingBar con
IfcSweptDiskSolid (un IfcReinforcingBar por juego de barras iguales, como permite IFC4, con una copia por barra);
dotación y equipamiento fijo con sus clases de IFC4; materiales; conjuntos de propiedades; cantidades; 4D (IfcWorkSchedule,
IfcTask, IfcRelAssignsToProduct: cada elemento es la salida de su tarea) y 5D (IfcCostSchedule, IfcCostItem con
valor unitario y cantidad, IfcRelAssignsToControl).

Modelo de prefactibilidad: no reemplaza los diseños firmados."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import BIM, R, WEB, angulo_dms, area_poligono, guid, leer, rel  # noqa: E402
import despiece as DSP  # noqa: E402

ENTRADA = BIM / 'torre_hospital.bim.json'
SALIDA = WEB / 'models/torre_hospital.ifc'
SALIDA_REF = WEB / 'models/torre_hospital_refuerzo.ifc'
LIMITE_MB = 15.0


# ================================================================================================ escritor STEP
class Ref(int):
    pass


class Enum(str):
    pass


class T:
    """Valor con tipo explícito: IFCLABEL('x'), IFCLENGTHMEASURE(1.)..."""
    __slots__ = ('tipo', 'v')

    def __init__(self, tipo, v):
        self.tipo, self.v = tipo, v


class Real(float):
    """Real con más decimales (relaciones de la georreferenciación)."""
    pass


DERIVADO = object()


def fmt_real(v, dec=6):
    v = float(v)
    if v == 0 or abs(v) < 0.5 * 10 ** -dec:
        return '0.'
    if abs(v) < 1e12:
        s = f'{v:.{dec}f}'.rstrip('0')
        return '0.' if s in ('-0.', '0.') else s
    return f'{v:.{dec}E}'


def step_str(s):
    out, buf = [], []

    def flush():
        if buf:
            out.append('\\X2\\' + ''.join(f'{ord(c):04X}' for c in buf) + '\\X0\\')
            buf.clear()
    for ch in s:
        o = ord(ch)
        if 32 <= o <= 126:
            flush()
            out.append("''" if ch == "'" else '\\\\' if ch == '\\' else ch)
        elif o < 0x10000:
            buf.append(ch)
        else:
            flush()
            out.append('?')
    flush()
    return "'" + ''.join(out) + "'"


def fmt(v):
    if v is None:
        return '$'
    if v is DERIVADO:
        return '*'
    if isinstance(v, Ref):
        return f'#{int(v)}'
    if isinstance(v, Enum):
        return f'.{v}.'
    if isinstance(v, bool):
        return '.T.' if v else '.F.'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Real):
        return fmt_real(v, 12)
    if isinstance(v, float):
        return fmt_real(v)
    if isinstance(v, str):
        return step_str(v)
    if isinstance(v, T):
        return f'{v.tipo}({fmt(v.v)})'
    if isinstance(v, (list, tuple)):
        return '(' + ','.join(fmt(x) for x in v) + ')'
    raise TypeError(type(v))


class Step:
    def __init__(self):
        self.lineas = []
        self.memo = {}
        self.cuenta = {}

    def e(self, nombre, *args):
        n = len(self.lineas) + 1
        self.lineas.append(f'#{n}={nombre.upper()}({",".join(fmt(a) for a in args)});')
        self.cuenta[nombre] = self.cuenta.get(nombre, 0) + 1
        return Ref(n)

    def u(self, nombre, *args):
        """Entidad compartida (misma línea → mismo #)."""
        clave = (nombre, tuple(fmt(a) for a in args))
        r_ = self.memo.get(clave)
        if r_ is None:
            r_ = self.memo[clave] = self.e(nombre, *args)
        return r_

    def texto(self, nombre_archivo, fecha, descripcion):
        head = ['ISO-10303-21;', 'HEADER;',
                f"FILE_DESCRIPTION(('ViewDefinition [DesignTransferView_V1.0]',{step_str(descripcion)[0:]}),'2;1');",
                f"FILE_NAME({step_str(nombre_archivo)},'{fecha}T00:00:00',('Equipo F (BIM), Atlas Yond\\X2\\00F3\\X0\\ 2028'),"
                f"('Atlas Yond\\X2\\00F3\\X0\\ 2028'),'scripts/bim/exportar_ifc.py','Atlas Yond\\X2\\00F3\\X0\\ 2028 exportar_ifc 1.0','');",
                "FILE_SCHEMA(('IFC4'));", 'ENDSEC;', 'DATA;']
        return '\n'.join(head + self.lineas + ['ENDSEC;', 'END-ISO-10303-21;', ''])


# ============================================================================================== tipos de valores
# Tipo de dato de cada propiedad de los Pset de IFC4 ADD2 que usa el modelo, copiado de las plantillas de buildingSMART
# (Pset_IFC4_ADD2); validar_ifc.py compara cada conjunto con ifcopenshell.util.pset.get_template('IFC4'): nombre del
# conjunto, propiedad, tipo de dato y forma (valor simple, acotado o enumerado). Una propiedad de un Pset_ que no esté
# aquí detiene la exportación: lo que IFC4 no define va en los conjuntos propios AtlasYondo_*.
PL = 'IfcPositiveLengthMeasure'
PLANTILLA_IFC4 = {
    'Pset_BeamCommon': {'Reference': 'IfcIdentifier', 'Span': PL, 'Slope': 'IfcPlaneAngleMeasure', 'LoadBearing': 'IfcBoolean',
                        'IsExternal': 'IfcBoolean'},
    'Pset_ColumnCommon': {'Reference': 'IfcIdentifier', 'Slope': 'IfcPlaneAngleMeasure', 'LoadBearing': 'IfcBoolean', 'IsExternal': 'IfcBoolean'},
    'Pset_ConcreteElementGeneral': {'StrengthClass': 'IfcLabel', 'ConcreteCover': PL, 'ReinforcementStrengthClass': 'IfcLabel'},
    'Pset_CoveringCommon': {'Reference': 'IfcIdentifier', 'IsExternal': 'IfcBoolean'},
    'Pset_DoorCommon': {'Reference': 'IfcIdentifier', 'IsExternal': 'IfcBoolean', 'FireRating': 'IfcLabel', 'HandicapAccessible': 'IfcBoolean',
                        'FireExit': 'IfcBoolean'},
    'Pset_FootingCommon': {'Reference': 'IfcIdentifier', 'LoadBearing': 'IfcBoolean'},
    'Pset_ManufacturerTypeInformation': {'ModelLabel': 'IfcLabel', 'ProductionYear': 'IfcLabel'},
    'Pset_PileCommon': {'Reference': 'IfcIdentifier', 'LoadBearing': 'IfcBoolean'},
    'Pset_ReinforcementBarCountOfIndependentFooting': {'Reference': 'IfcLabel', 'XDirectionLowerBarCount': 'IfcInteger',
                                                       'YDirectionLowerBarCount': 'IfcInteger'},
    'Pset_ReinforcementBarPitchOfBeam': {'Reference': 'IfcLabel', 'StirrupBarPitch': PL},
    'Pset_ReinforcementBarPitchOfColumn': {'Reference': 'IfcLabel', 'HoopBarPitch': PL, 'XDirectionTieHoopBarPitch': PL,
                                           'XDirectionTieHoopCount': 'IfcInteger', 'YDirectionTieHoopBarPitch': PL,
                                           'YDirectionTieHoopCount': 'IfcInteger'},
    'Pset_ReinforcementBarPitchOfSlab': {'Reference': 'IfcLabel', 'LongOutsideTopBarPitch': PL, 'ShortOutsideTopBarPitch': PL},
    'Pset_ReinforcementBarPitchOfWall': {'Reference': 'IfcLabel', 'VerticalBarPitch': PL, 'HorizontalBarPitch': PL,
                                         'BarAllocationType': ('IfcLabel', 'enumerado')},
    'Pset_ServiceLife': {'ServiceLifeDuration': ('IfcDuration', 'acotado')},
    'Pset_SlabCommon': {'Reference': 'IfcIdentifier', 'LoadBearing': 'IfcBoolean', 'IsExternal': 'IfcBoolean'},
    'Pset_SpaceCommon': {'Reference': 'IfcIdentifier', 'IsExternal': 'IfcBoolean', 'GrossPlannedArea': 'IfcAreaMeasure',
                         'PubliclyAccessible': 'IfcBoolean'},
    'Pset_StairCommon': {'NumberOfRiser': 'IfcCountMeasure', 'RiserHeight': PL, 'TreadLength': PL, 'FireExit': 'IfcBoolean'},
    'Pset_StairFlightCommon': {'NumberOfRiser': 'IfcCountMeasure', 'NumberOfTreads': 'IfcCountMeasure', 'RiserHeight': PL, 'TreadLength': PL},
    'Pset_WallCommon': {'Reference': 'IfcIdentifier', 'IsExternal': 'IfcBoolean', 'LoadBearing': 'IfcBoolean', 'ExtendToStructure': 'IfcBoolean'},
    'Pset_WindowCommon': {'Reference': 'IfcIdentifier', 'IsExternal': 'IfcBoolean'},
}
ENUMERACIONES = {('Pset_ReinforcementBarPitchOfWall', 'BarAllocationType'):
                 ('PEnum_ReinforcementBarAllocationType', ('SINGLE', 'DOUBLE', 'ALTERNATE', 'OTHER', 'USERDEFINED', 'NOTDEFINED'))}
TEXTO = {'Nota', 'Fuente', 'Norma', 'Descripcion5D', 'NotaAnalisis', 'Etiqueta', 'Zona', 'Ganchos'}


def forma_propiedad(pset, nombre):
    t = PLANTILLA_IFC4.get(pset, {}).get(nombre)
    return t[1] if isinstance(t, tuple) else 'simple'


def valor(nombre, v, pset=None):
    """Valor tipado: en los Pset_ de IFC4, con el tipo de su plantilla; en los conjuntos propios, por el nombre y el valor."""
    if pset and pset.startswith('Pset_'):
        t = PLANTILLA_IFC4.get(pset, {}).get(nombre)
        if t is None:
            raise SystemExit(f'{pset}.{nombre} no está en la plantilla de IFC4: va en un conjunto propio (AtlasYondo_*)')
        t = t[0] if isinstance(t, tuple) else t
        if t == 'IfcBoolean':
            return T('IFCBOOLEAN', bool(v))
        if t in ('IfcIdentifier', 'IfcLabel'):
            return T(t.upper(), str(v)[:255])
        if t == 'IfcText':
            return T('IFCTEXT', str(v))
        if t == 'IfcInteger':
            return T('IFCINTEGER', int(v))
        if t == 'IfcDuration':
            return T('IFCDURATION', f'P{int(v)}Y')
        return T(t.upper(), float(v))
    if isinstance(v, bool):
        return T('IFCBOOLEAN', v)
    if nombre.startswith(('Inicio', 'Fin')) and isinstance(v, str):
        return T('IFCDATE', v)
    if nombre.startswith(('Valor', 'Precio')) and isinstance(v, (int, float)):
        return T('IFCMONETARYMEASURE', float(v))
    if isinstance(v, int):
        return T('IFCINTEGER', v)
    if isinstance(v, float):
        return T('IFCREAL', v)
    s = str(v)
    if nombre in TEXTO or len(s) > 255:
        return T('IFCTEXT', s)
    return T('IFCLABEL', s)


def tipo_cantidad(nombre):
    if nombre == 'Count':
        return 'IfcQuantityCount'
    if 'Weight' in nombre:
        return 'IfcQuantityWeight'
    if 'Volume' in nombre:
        return 'IfcQuantityVolume'
    if 'Area' in nombre:
        return 'IfcQuantityArea'
    return 'IfcQuantityLength'


COLORES = {'concreto_28': (0.72, 0.72, 0.70, 0.0), 'concreto_21': (0.66, 0.66, 0.63, 0.0), 'acero_420': (0.55, 0.16, 0.12, 0.0),
           'malla_electrosoldada': (0.45, 0.30, 0.25, 0.0), 'ladrillo_fachada': (0.70, 0.36, 0.24, 0.0), 'bloque_arcilla': (0.86, 0.80, 0.72, 0.0),
           'bloque_nucleo': (0.80, 0.80, 0.78, 0.0), 'placa_yeso': (0.95, 0.95, 0.93, 0.0), 'bloque_plomado': (0.60, 0.62, 0.68, 0.0),
           'parapeto': (0.82, 0.78, 0.72, 0.0), 'cerramiento': (0.40, 0.45, 0.40, 0.5), 'aluminio_vidrio': (0.55, 0.75, 0.85, 0.6),
           'puerta_hospitalaria': (0.55, 0.62, 0.70, 0.0), 'vinilo': (0.70, 0.78, 0.74, 0.0), 'porcelanato': (0.88, 0.88, 0.86, 0.0),
           'mortero_cuarzo': (0.60, 0.60, 0.58, 0.0), 'cielo_fibra': (0.97, 0.97, 0.96, 0.0), 'cielo_yeso': (0.98, 0.98, 0.97, 0.0),
           'cubierta': (0.90, 0.90, 0.92, 0.0), 'equipo': (0.35, 0.55, 0.75, 0.0), None: (0.85, 0.90, 0.95, 0.85)}


# ======================================================================================================= modelo
class Exportador:
    def __init__(self, M, parte):
        self.M = M
        self.parte = parte                 # 'todo', 'principal' o 'refuerzo'
        self.S = Step()
        s = self.S
        self.origen3 = s.u('IfcCartesianPoint', (0.0, 0.0, 0.0))
        self.dz = s.u('IfcDirection', (0.0, 0.0, 1.0))
        self.dx = s.u('IfcDirection', (1.0, 0.0, 0.0))
        self.eje0 = s.u('IfcAxis2Placement3D', self.origen3, None, None)
        self.elev = {n['id']: n['elevacion'] for n in M['niveles']}
        self.estilos = {}

    # ---------------------------------------------------------------------------------------- encabezado y espacio
    def proyecto(self):
        s, M = self.S, self.M
        g = M['georreferenciacion']
        u = [s.e('IfcSIUnit', DERIVADO, Enum('LENGTHUNIT'), None, Enum('METRE')),
             s.e('IfcSIUnit', DERIVADO, Enum('AREAUNIT'), None, Enum('SQUARE_METRE')),
             s.e('IfcSIUnit', DERIVADO, Enum('VOLUMEUNIT'), None, Enum('CUBIC_METRE')),
             s.e('IfcSIUnit', DERIVADO, Enum('MASSUNIT'), Enum('KILO'), Enum('GRAM')),
             s.e('IfcSIUnit', DERIVADO, Enum('PLANEANGLEUNIT'), None, Enum('RADIAN')),
             s.e('IfcSIUnit', DERIVADO, Enum('TIMEUNIT'), None, Enum('SECOND')),
             s.e('IfcSIUnit', DERIVADO, Enum('PRESSUREUNIT'), None, Enum('PASCAL')),
             s.e('IfcMonetaryUnit', 'COP')]
        self.metro = u[0]
        unidades = s.e('IfcUnitAssignment', u)
        norte = s.e('IfcDirection', (0.0, 1.0))
        wcs = s.e('IfcAxis2Placement3D', self.origen3, None, None)
        self.ctx = s.e('IfcGeometricRepresentationContext', None, 'Model', 3, 1.0e-5, wcs, norte)
        self.body = s.e('IfcGeometricRepresentationSubContext', 'Body', 'Model', DERIVADO, DERIVADO, DERIVADO, DERIVADO, self.ctx, None,
                        Enum('MODEL_VIEW'), None)
        crs = s.e('IfcProjectedCRS', 'EPSG:9377', g['crs_nombre'] + ' (Origen Nacional, Resolución IGAC 471 de 2020)', 'MAGNA-SIRGAS 2018',
                  None, 'Transverse Mercator', None, self.metro)
        s.e('IfcMapConversion', self.ctx, crs, float(g['este_m']), float(g['norte_m']), float(g['altura_ortometrica_m']),
            Real(g['eje_x_abscisa']), Real(g['eje_x_ordenada']), 1.0)
        self.proj = s.e('IfcProject', guid('proyecto|torre_hospital'), None, 'Torre de servicios de primer nivel - Hospital Héctor Abad Gómez (Yondó)',
                        M['estado'] + ' ' + M['tipo_dato'], None, 'Atlas Yondó 2028: modelo BIM federado (' +
                        ('arquitectura, estructura, cimentación, equipamiento fijo y dotación' if self.parte == 'principal' else
                         'refuerzo' if self.parte == 'refuerzo' else 'todas las disciplinas') + ')', 'Prefactibilidad', [self.ctx], unidades)
        anc = g['ancla']
        pl_site = s.e('IfcLocalPlacement', None, self.eje0)
        self.site = s.e('IfcSite', guid('sitio|torre_hospital'), None, 'Predio del Hospital Héctor Abad Gómez', 'Yondó, Antioquia (Colombia)',
                        None, pl_site, None, 'Lote de la torre', Enum('ELEMENT'), angulo_dms(anc['lat']), angulo_dms(anc['lon']),
                        float(g['altura_ortometrica_m']), None, None)
        pl_bld = s.e('IfcLocalPlacement', pl_site, self.eje0)
        self.bld = s.e('IfcBuilding', guid('edificio|torre_hospital'), None, 'Torre de servicios de primer nivel', M['nombre'], None, pl_bld,
                       None, 'Torre del hospital', Enum('ELEMENT'), float(g['altura_ortometrica_m']), None, None)
        s.e('IfcRelAggregates', guid('rel|proyecto-sitio'), None, None, None, self.proj, [self.site])
        s.e('IfcRelAggregates', guid('rel|sitio-edificio'), None, None, None, self.site, [self.bld])
        self.niveles = {}
        self.pl_nivel = {}
        for n in M['niveles']:
            pt = s.u('IfcCartesianPoint', (0.0, 0.0, float(n['elevacion'])))
            pl = s.e('IfcLocalPlacement', pl_bld, s.e('IfcAxis2Placement3D', pt, None, None))
            self.pl_nivel[n['id']] = pl
            self.niveles[n['id']] = s.e('IfcBuildingStorey', n['guid'], None, n['id'], n['nombre'], None, pl, None, n['nombre'],
                                        Enum('ELEMENT'), float(n['elevacion']))
        s.e('IfcRelAggregates', guid('rel|edificio-niveles'), None, None, None, self.bld, [self.niveles[n['id']] for n in M['niveles']])

    # --------------------------------------------------------------------------------------------- geometría
    def estilo(self, mat):
        if mat not in self.estilos:
            r_, g_, b_, tr = COLORES.get(mat, COLORES[None])
            s = self.S
            col = s.e('IfcColourRgb', None, r_, g_, b_)
            sh = s.e('IfcSurfaceStyleShading', col, tr)
            self.estilos[mat] = s.e('IfcSurfaceStyle', mat or 'espacio', Enum('BOTH'), [sh])
        return self.estilos[mat]

    def pts2(self, pts, cerrar=True, ccw=None):
        p = [(float(x), float(y)) for x, y in pts]
        if ccw is not None and (area_poligono(p) > 0) != ccw:
            p = p[::-1]
        if cerrar:
            p = p + [p[0]]
        lista = self.S.e('IfcCartesianPointList2D', p)
        return self.S.e('IfcIndexedPolyCurve', lista, None, False)

    def solidos(self, g, ez):
        """Sólidos de la geometría con coordenadas relativas a la cota del nivel ez."""
        s = self.S
        t = g['tipo']
        if t == 'caja':
            (x0, y0, z0), (x1, y1, z1) = g['min'], g['max']
            prof = s.u('IfcRectangleProfileDef', Enum('AREA'), None, None, float(x1 - x0), float(y1 - y0))
            pos = s.e('IfcAxis2Placement3D', s.e('IfcCartesianPoint', ((x0 + x1) / 2, (y0 + y1) / 2, z0 - ez)), None, None)
            return [s.e('IfcExtrudedAreaSolid', prof, pos, self.dz, float(z1 - z0))]
        if t == 'prisma':
            if g.get('huecos'):
                prof = s.e('IfcArbitraryProfileDefWithVoids', Enum('AREA'), None, self.pts2(g['planta'], ccw=True),
                           [self.pts2(h, ccw=False) for h in g['huecos']])
            else:
                prof = s.e('IfcArbitraryClosedProfileDef', Enum('AREA'), None, self.pts2(g['planta'], ccw=True))
            pos = s.e('IfcAxis2Placement3D', s.e('IfcCartesianPoint', (0.0, 0.0, g['z0'] - ez)), None, None)
            return [s.e('IfcExtrudedAreaSolid', prof, pos, self.dz, float(g['z1'] - g['z0']))]
        if t == 'cilindro':
            prof = s.u('IfcCircleProfileDef', Enum('AREA'), None, None, float(g['radio']))
            pos = s.e('IfcAxis2Placement3D', s.e('IfcCartesianPoint', (g['centro'][0], g['centro'][1], g['z0'] - ez)), None, None)
            return [s.e('IfcExtrudedAreaSolid', prof, pos, self.dz, float(g['z1'] - g['z0']))]
        if t == 'perfil':
            prof = s.e('IfcArbitraryClosedProfileDef', Enum('AREA'), None, self.pts2(g['puntos']))
            o = g['origen']
            pos = s.e('IfcAxis2Placement3D', s.e('IfcCartesianPoint', (o[0], o[1], o[2] - ez)), s.u('IfcDirection', tuple(float(c) for c in g['w'])),
                      s.u('IfcDirection', tuple(float(c) for c in g['u'])))
            return [s.e('IfcExtrudedAreaSolid', prof, pos, self.dz, float(g['largo']))]
        if t == 'caja_girada':
            cx, cy, z = g['centro']
            w, d, h = g['dim']
            prof = s.u('IfcRectangleProfileDef', Enum('AREA'), None, None, float(w), float(d))
            rot = g['rot']
            k4 = round(rot / (math.pi / 2))
            if abs(rot - k4 * math.pi / 2) < 1e-3:            # giros de 90° exactos (el inventario redondea a 4 decimales)
                c_, s_ = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)][k4 % 4]
            else:
                c_, s_ = round(math.cos(rot), 9), round(math.sin(rot), 9)
            girado = (c_, s_) != (1.0, 0.0)
            pos = s.e('IfcAxis2Placement3D', s.e('IfcCartesianPoint', (cx, cy, z - ez)), self.dz if girado else None,
                      s.u('IfcDirection', (c_, s_, 0.0)) if girado else None)
            return [s.e('IfcExtrudedAreaSolid', prof, pos, self.dz, float(h))]
        if t == 'compuesta':
            out = []
            for p in g['partes']:
                out += self.solidos(p, ez)
            return out
        raise ValueError(t)

    def forma(self, g, ez, mat):
        items = self.solidos(g, ez)
        if not items:
            return None
        est = self.estilo(mat)
        for it in items:
            self.S.e('IfcStyledItem', it, [est], None)
        rep = self.S.e('IfcShapeRepresentation', self.body, 'Body', 'SweptSolid', items)
        return self.S.e('IfcProductDefinitionShape', None, None, [rep])

    # ------------------------------------------------------------------------------------------- propiedades
    def propiedad(self, pset, k, v):
        s = self.S
        forma = forma_propiedad(pset, k)
        if forma == 'acotado':                 # IfcPropertyBoundedValue: solo el valor de referencia (SetPointValue)
            return s.u('IfcPropertyBoundedValue', k, None, None, None, None, valor(k, v, pset))
        if forma == 'enumerado':
            nom, vals = ENUMERACIONES[(pset, k)]
            enum = s.u('IfcPropertyEnumeration', nom, [T('IFCLABEL', x) for x in vals], None)
            return s.u('IfcPropertyEnumeratedValue', k, None, [valor(k, v, pset)], enum)
        return s.u('IfcPropertySingleValue', k, None, valor(k, v, pset), None)

    def pset(self, nombre, props, objetos, clave):
        s = self.S
        lista = [self.propiedad(nombre, k, v) for k, v in props.items() if v is not None]
        if not lista:
            return
        ps = s.e('IfcPropertySet', guid(f'pset|{nombre}|{clave}'), None, nombre, None, lista)
        s.e('IfcRelDefinesByProperties', guid(f'rel|pset|{nombre}|{clave}'), None, None, None, objetos, ps)

    def qto(self, nombre, vals, objeto, clave, metodo=None):
        s = self.S
        lista = []
        for k, v in vals.items():
            if v is None:
                continue
            tq = tipo_cantidad(k)
            lista.append(s.u(tq, k, None, None, float(v) if tq != 'IfcQuantityCount' else float(v), None))
        if not lista:
            return
        q = s.e('IfcElementQuantity', guid(f'qto|{nombre}|{clave}'), None, nombre, None, metodo, lista)
        s.e('IfcRelDefinesByProperties', guid(f'rel|qto|{nombre}|{clave}'), None, None, None, [objeto], q)

    def atlas(self, e, fases):
        a = dict(e['atlas'])
        a['IdAtlas'] = e['id']
        a['Disciplina'] = e['disciplina']
        if e.get('costo'):
            c = e['costo'][0]
            a['Item5D'] = c['item']
            if c.get('apu'):
                a['APU'] = c['apu']
            if c.get('cantidad') is not None:
                a['Cantidad5D'] = float(c['cantidad'])
            if c.get('valor') is not None:
                a['Valor5D'] = float(c['valor'])
            if len(e['costo']) > 1:
                a['Item5D_2'] = e['costo'][1]['item']
                if e['costo'][1].get('valor') is not None:
                    a['Valor5D_2'] = float(e['costo'][1]['valor'])
            if c.get('nota'):
                a['Nota5D'] = c['nota']
        if e.get('fase'):
            f = fases[e['fase']]
            a['Fase4D'] = f['id']
            a['Inicio4D'] = f['inicio']
            a['Fin4D'] = f['fin']
        an = e.get('analisis')
        if an:
            if an.get('elementos'):
                a['IdAnalisis'] = ', '.join(an['elementos'])
            if an.get('nota'):
                a['NotaAnalisis'] = an['nota']
            if an.get('grupo'):
                a['GrupoCimentacion'] = an['grupo']
            if an.get('apoyos'):
                a['Apoyos'] = ', '.join(an['apoyos'])
        if e.get('refuerzo_texto'):
            a['Refuerzo'] = e['refuerzo_texto']
        a['Aviso'] = self.M['estado']
        return {k: v for k, v in a.items() if v is not None}

    # -------------------------------------------------------------------------------------------- elementos
    def elementos(self):
        s, M = self.S, self.M
        fases = {f['id']: f for f in M['cronograma']['fases']}
        self.ref = {}
        contenidos = {}
        por_material = {}
        espacios = {}
        cubre = {}
        agregados = {}
        ids_modelo = {e['id'] for e in M['elementos']}
        for e in M['elementos']:
            if e['clase'] == 'IfcSpace':
                espacios[e['id']] = e
        for e in M['elementos']:
            ez = self.elev[e['nivel']]
            pl = self.pl_nivel[e['nivel']]
            rep = self.forma(e['geometria'], ez, e.get('material')) if e['geometria'].get('tipo') != 'compuesta' or e['geometria']['partes'] else None
            nombre = e['nombre'][:255]
            desc = e['atlas'].get('Nota')
            c, tp = e['clase'], Enum(e['tipo_predefinido'])
            ot = e.get('objeto_tipo')
            base = [e['guid'], None, nombre, desc, ot if (e['tipo_predefinido'] == 'USERDEFINED') else None, pl, rep]
            if c == 'IfcSpace':
                x = s.e(c, *base[:7], e['nombre'][:255], Enum('ELEMENT'), tp, None)
            elif c == 'IfcDoor':
                x = s.e(c, *base, e['id'], float(e['alto_total']), float(e['ancho_total']), tp, Enum(e.get('operacion', 'NOTDEFINED')), None)
            elif c == 'IfcWindow':
                x = s.e(c, *base, e['id'], float(e['alto_total']), float(e['ancho_total']), tp, Enum('SINGLE_PANEL'), None)
            elif c == 'IfcStairFlight':
                p = e['psets'].get('Pset_StairFlightCommon', {})
                x = s.e(c, *base, e['id'], p.get('NumberOfRiser'), p.get('NumberOfTreads'), float(p['RiserHeight']), float(p['TreadLength']), tp)
            elif c == 'IfcPile':
                x = s.e(c, *base, e['id'], tp, None)
            elif c == 'IfcElementAssembly':
                x = s.e(c, *base, e['id'], Enum('SITE'), tp)
            else:
                if e['tipo_predefinido'] == 'USERDEFINED' and not ot:
                    base[4] = e.get('objeto_tipo') or e['clase'][3:].upper()
                x = s.e(c, *base, e['id'], tp)
            self.ref[e['id']] = x
            if c == 'IfcSpace':
                continue
            padre = e.get('parte_de') or e.get('componente_de')
            if padre and padre in ids_modelo:
                agregados.setdefault(padre, []).append(x)
            else:
                contenidos.setdefault(e.get('contenedor') or e['nivel'], []).append(x)
            if e.get('material'):
                por_material.setdefault(e['material'], []).append(x)
            if c == 'IfcCovering' and e.get('espacio'):
                cubre.setdefault(e['espacio'], []).append(x)
        # vanos de puertas y ventanas
        for e in M['elementos']:
            v = e.get('vano')
            if not v or v['muro'] not in self.ref:
                continue
            ez = self.elev[e['nivel']]
            rep = self.forma(v['geometria'], ez, None)
            op = s.e('IfcOpeningElement', v['guid'], None, f'Vano de {e["id"]}', None, None, self.pl_nivel[e['nivel']], rep, v['id'], Enum('OPENING'))
            s.e('IfcRelVoidsElement', guid(f'rel|vano|{v["id"]}'), None, None, None, self.ref[v['muro']], op)
            s.e('IfcRelFillsElement', guid(f'rel|llena|{v["id"]}'), None, None, None, op, self.ref[e['id']])
        # espacios en los niveles (agregación) y relaciones
        por_nivel_esp = {}
        for e in M['elementos']:
            if e['clase'] == 'IfcSpace':
                por_nivel_esp.setdefault(e['nivel'], []).append(self.ref[e['id']])
        for niv in sorted(por_nivel_esp):
            s.e('IfcRelAggregates', guid(f'rel|nivel-espacios|{niv}'), None, None, None, self.niveles[niv], por_nivel_esp[niv])
        for cont in sorted(contenidos):
            destino = self.niveles.get(cont) or self.ref.get(cont)
            s.e('IfcRelContainedInSpatialStructure', guid(f'rel|contenido|{cont}'), None, None, None, contenidos[cont], destino)
        for padre in sorted(agregados):
            s.e('IfcRelAggregates', guid(f'rel|partes|{padre}'), None, None, None, self.ref[padre], agregados[padre])
        for esp in sorted(cubre):
            s.e('IfcRelCoversSpaces', guid(f'rel|cubre|{esp}'), None, None, None, self.ref[esp], cubre[esp])
        self.materiales(por_material)
        # propiedades: las comunes se comparten cuando son iguales; la propia y las cantidades van por elemento
        comunes = {}
        for e in M['elementos']:
            x = self.ref[e['id']]
            for nombre, props in e['psets'].items():
                clave = (nombre, tuple(sorted((k, fmt(valor(k, v, nombre))) for k, v in props.items())))
                comunes.setdefault(clave, (nombre, props, []))[2].append(x)
            self.pset('AtlasYondo_Torre', self.atlas(e, fases), [x], e['id'])
            for nombre, vals in e['qto'].items():
                self.qto(nombre, vals, x, e['id'], 'Geometría del modelo BIM (cálculo propio)')
        for i, clave in enumerate(sorted(comunes, key=lambda c: (c[0], c[1]))):
            nombre, props, objs = comunes[clave]
            self.pset(nombre, props, objs, f'{i:05d}')
        return fases

    def materiales(self, por_material):
        s, M = self.S, self.M
        props_mat = {
            'concreto_28': [('Pset_MaterialCommon', {'MassDensity': ('IFCMASSDENSITYMEASURE', 2400.0)}),
                            ('Pset_MaterialMechanical', {'YoungModulus': ('IFCMODULUSOFELASTICITYMEASURE', 24.87e9),
                                                         'PoissonRatio': ('IFCPOSITIVERATIOMEASURE', 0.2)}),
                            ('Pset_MaterialConcrete', {'CompressiveStrength': ('IFCPRESSUREMEASURE', 28.0e6)})],
            'acero_420': [('Pset_MaterialCommon', {'MassDensity': ('IFCMASSDENSITYMEASURE', 7850.0)}),
                          ('Pset_MaterialMechanical', {'YoungModulus': ('IFCMODULUSOFELASTICITYMEASURE', 200.0e9)}),
                          ('Pset_MaterialSteel', {'YieldStress': ('IFCPRESSUREMEASURE', 420.0e6), 'UltimateStress': ('IFCPRESSUREMEASURE', 550.0e6)})],
        }
        for mid in sorted(por_material):
            m = M['materiales'][mid]
            mat = s.e('IfcMaterial', m['nombre'], m['fuente'], m['categoria'])
            for nombre, pr in props_mat.get(mid, []):
                lista = [s.e('IfcPropertySingleValue', k, None, T(t, v), None) for k, (t, v) in pr.items()]
                s.e('IfcMaterialProperties', nombre, None, lista, mat)
            s.e('IfcRelAssociatesMaterial', guid(f'rel|material|{mid}|{self.parte}'), None, None, None, por_material[mid], mat)

    # --------------------------------------------------------------------------------------------- refuerzo
    def refuerzo(self, fases):
        s, M = self.S, self.M
        host = {e['id']: e for e in M['elementos']}
        acero = []
        por_nivel = {}
        ensambles = {}
        rep_ident = s.u('IfcCartesianTransformationOperator3D', None, None, self.origen3, None, None)
        estilo = self.estilo('acero_420')
        mapas = {}
        for j in M['refuerzo']:
            ez = self.elev[j['nivel']]
            pts = DSP.polilinea(j)
            # cada juego se coloca en el primer punto de su eje; los juegos con la misma forma relativa comparten el mapa
            b0 = (round(pts[0][0], 4), round(pts[0][1], 4), round(pts[0][2] - ez, 4))
            relp = tuple(tuple(round(p[i] - pts[0][i], 4) + 0.0 for i in range(3)) for p in pts)
            clave = (round(float(j['db']), 5), relp)
            mapa = mapas.get(clave)
            if mapa is None:
                lista = s.e('IfcCartesianPointList3D', [tuple(float(c) for c in q) for q in relp])
                curva = s.e('IfcIndexedPolyCurve', lista, None, False)
                sds = s.e('IfcSweptDiskSolid', curva, float(j['db']) / 2, None, None, None)
                s.e('IfcStyledItem', sds, [estilo], None)
                rmap = s.e('IfcShapeRepresentation', self.body, 'Body', 'AdvancedSweptSolid', [sds])
                mapa = mapas[clave] = s.e('IfcRepresentationMap', self.eje0, rmap)
            pl_j = s.e('IfcLocalPlacement', self.pl_nivel[j['nivel']],
                       s.u('IfcAxis2Placement3D', s.u('IfcCartesianPoint', tuple(float(c) + 0.0 for c in b0)), None, None))
            items = []
            for c in j['copias']:
                if abs(c[0]) < 1e-9 and abs(c[1]) < 1e-9 and abs(c[2]) < 1e-9:
                    op = rep_ident
                else:
                    op = s.u('IfcCartesianTransformationOperator3D', None, None, s.u('IfcCartesianPoint', (float(c[0]), float(c[1]), float(c[2]))), None, None)
                items.append(s.e('IfcMappedItem', mapa, op))
            rep = s.e('IfcShapeRepresentation', self.body, 'Body', 'MappedRepresentation', items)
            pds = s.e('IfcProductDefinitionShape', None, None, [rep])
            db = float(j['db'])
            area = math.pi * db * db / 4
            nombre = (f'{j["etiqueta"]} · {j["host"]}')[:255]
            x = s.e('IfcReinforcingBar', j['guid'], None, nombre, j.get('zona'), j['rol'], pl_j, pds, j['id'], None,
                    db, area, float(j['largo']), Enum(j['tipo_predefinido']), Enum('PLAIN') if j['num'] is None else Enum('TEXTURED'))
            acero.append(x)
            ensambles.setdefault(j['host'], []).append(x)
            a = {'IdAtlas': j['id'], 'Disciplina': 'REF', 'Anfitrion': j['host'], 'AnfitrionGlobalId': host[j['host']]['guid'],
                 'Designacion': f'N.º {j["num"]}' if j['num'] else f'Ø {j.get("diam_mm", 0):g} mm (malla electrosoldada)',
                 'Etiqueta': j['etiqueta'], 'Zona': j.get('zona'), 'Ganchos': j.get('ganchos'), 'Rol': j['rol'],
                 'TipoDato': 'cálculo propio (despiece de A en geometría real; equipo F)',
                 'Fuente': 'data/sismo/torre_hospital_estructura.json → refuerzo y cimentacion', 'Norma': 'NSR-10 C.7, C.12 y C.21; NTC 2289',
                 'Item5D': j['costo'][0]['item'], 'Cantidad5D': float(j['costo'][0]['cantidad']), 'Valor5D': float(j['costo'][0]['valor']),
                 'Fase4D': j['fase'], 'Inicio4D': fases[j['fase']]['inicio'], 'Fin4D': fases[j['fase']]['fin']}
            self.pset('AtlasYondo_Refuerzo', {k: v for k, v in a.items() if v is not None}, [x], j['id'])
            self.qto('Qto_ReinforcingElementBaseQuantities', {'Count': j['n'], 'Length': j['largo'] * j['n'], 'Weight': j['kg']}, x, j['id'],
                     'Geometría de las barras (eje con dobleces) × masa nominal NTC 2289')
            self.ref[j['id']] = x
        # armaduras por elemento anfitrión (IfcElementAssembly, REINFORCEMENT_UNIT) contenidas en el nivel del anfitrión
        for hid in sorted(ensambles):
            h = host[hid]
            ens = s.e('IfcElementAssembly', guid(f'armadura|{hid}'), None, f'Armadura de {hid}'[:255], h['nombre'][:255], None,
                      self.pl_nivel[h['nivel']], None, f'ARM-{hid}', Enum('FACTORY') if False else Enum('SITE'), Enum('REINFORCEMENT_UNIT'))
            s.e('IfcRelAggregates', guid(f'rel|armadura|{hid}'), None, None, None, ens, ensambles[hid])
            por_nivel.setdefault(h['nivel'], []).append(ens)
            self.pset('AtlasYondo_Refuerzo', {'Anfitrion': hid, 'AnfitrionGlobalId': h['guid'], 'Refuerzo': h.get('refuerzo_texto')}, [ens], 'ARM-' + hid)
            self.ref['ARM-' + hid] = ens
        for niv in sorted(por_nivel):
            s.e('IfcRelContainedInSpatialStructure', guid(f'rel|contenido-refuerzo|{niv}'), None, None, None, por_nivel[niv], self.niveles[niv])
        if acero:
            m = M['materiales']['acero_420']
            mat = s.e('IfcMaterial', m['nombre'], m['fuente'], m['categoria'])
            s.e('IfcRelAssociatesMaterial', guid(f'rel|material|acero_420|{self.parte}'), None, None, None, acero, mat)

    # ------------------------------------------------------------------------------------------------ 4D y 5D
    def cronograma_y_costos(self, fases, ids):
        """4D: cada elemento es la SALIDA de su tarea (IfcRelAssignsToProduct: la tarea produce el elemento), como lo leen
        los visores 4D; los espacios no se construyen y no son salida de ninguna tarea. 5D: cada partida es un
        IfcCostItem del IfcCostSchedule (IfcRelAssignsToControl) con su valor unitario y la cantidad del modelo, o la
        del presupuesto si el modelo no la mide; los elementos se asignan a su partida (IfcRelAssignsToControl)."""
        s, M = self.S, self.M
        fecha = M['fecha'] + 'T00:00:00'
        ws = s.e('IfcWorkSchedule', guid('4d|programa'), None, 'Programa de obra de la torre (4D)', M['cronograma']['nota'], None, 'PO-TORRE',
                 fecha, None, 'Cronograma de docs/11, sección 10, repartido por piso y disciplina', None, None,
                 min(f['inicio'] for f in M['cronograma']['fases']) + 'T00:00:00', max(f['fin'] for f in M['cronograma']['fases']) + 'T00:00:00',
                 Enum('PLANNED'))
        tareas = []
        tarea_de = {}
        for f in M['cronograma']['fases']:
            tt = s.e('IfcTaskTime', None, None, None, None, None, f['inicio'] + 'T00:00:00', f['fin'] + 'T23:59:59',
                     *([None] * 13))
            tipo, ot = tipo_tarea(f)
            t = s.e('IfcTask', f['guid'], None, f['nombre'][:255], f'Etapa {f["etapa"]} del cronograma: {f["etapa_nombre"]}', ot, f['id'], None,
                    None, None, False, None, tt, Enum(tipo))
            tareas.append(t)
            tarea_de[f['id']] = t
        s.e('IfcRelAssignsToControl', guid('rel|4d|programa-tareas'), None, None, None, tareas, None, ws)
        # salidas: una relación por elemento (IFC4: un solo producto por IfcRelAssignsToProduct)
        for e in M['elementos']:
            if e['id'] in ids and e.get('fase') and e['id'] in self.ref and e['clase'] != 'IfcSpace':
                s.e('IfcRelAssignsToProduct', guid(f'rel|4d-salida|{e["id"]}'), None, None, None, [tarea_de[e['fase']]], None, self.ref[e['id']])
        for j in M['refuerzo']:
            if j['id'] in ids:
                s.e('IfcRelAssignsToProduct', guid(f'rel|4d-salida|{j["id"]}'), None, None, None, [tarea_de[j['fase']]], None, self.ref[j['id']])
        # 5D
        cs = s.e('IfcCostSchedule', guid('5d|presupuesto'), None, 'Presupuesto de obra y dotación (5D)',
                 'Ítems de presupuesto.json (costo directo, pesos constantes de 2026) e indirectos de la dotación. Total de cada partida = '
                 'valor unitario × cantidad (del modelo o, si el modelo no la mide, del presupuesto); en los indirectos, el valor del '
                 'presupuesto o, fuera de él, la suma de las unidades del inventario.', None, 'PRES-TORRE',
                 Enum('BUDGET'), 'prefactibilidad', None, fecha)
        por_item = {}
        for e in M['elementos']:
            if e['id'] in ids and e['id'] in self.ref:
                for c in e.get('costo', []):
                    por_item.setdefault(c['item'], []).append(self.ref[e['id']])
        for j in M['refuerzo']:
            if j['id'] in ids:
                por_item.setdefault(j['costo'][0]['item'], []).append(self.ref[j['id']])
        P = M['presupuesto']
        items = []
        filas = {f['item']: f for f in M['comparacion_presupuesto']}
        for codigo in sorted(por_item, key=_orden):
            fila = filas.get(codigo, {})
            if codigo in P['items']:
                it = P['items'][codigo]
                cv = s.e('IfcCostValue', 'Valor unitario (costo directo)', it.get('tipo_precio'), T('IFCMONETARYMEASURE', float(it['valor_unitario'])),
                         None, None, None, None, None, None, None)
                tq = {'m3': 'IfcQuantityVolume', 'm2': 'IfcQuantityArea', 'kg': 'IfcQuantityWeight', 'ml': 'IfcQuantityLength'}.get(it['unidad'], 'IfcQuantityCount')
                if fila.get('bim_cantidad') is not None:
                    cant = [s.e(tq, 'Cantidad del modelo', f'{it["unidad"]} (cálculo propio sobre la geometría del modelo)', None,
                                float(fila['bim_cantidad']), None)]
                elif it['unidad'] != 'global' or float(it['cantidad']) != 1.0:
                    cant = [s.e(tq, 'Cantidad del presupuesto', f'{it["unidad"]} (estimación de presupuesto.json: el modelo no la mide)', None,
                                float(it['cantidad']), None)]
                else:
                    cant = []
                ci = s.e('IfcCostItem', guid(f'5d|{codigo}'), None, it['descripcion'][:255], (f'APU {it["apu"]}' if it.get('apu') else None), None,
                         codigo, Enum('NOTDEFINED'), [cv], cant or None)
            else:
                ind = P['indirectos'][codigo]
                if ind.get('valor') is not None:
                    cvs = [s.e('IfcCostValue', 'Valor del presupuesto', ind['grupo'], T('IFCMONETARYMEASURE', float(ind['valor'])), None, None, None,
                               None, None, None, None)]
                else:
                    cvs = [s.e('IfcCostValue', 'Suma de las unidades enlazadas', 'fuera de presupuesto.json: valor de mercado de las unidades '
                               'del inventario (estimación)', T('IFCMONETARYMEASURE', float(fila.get('bim_valor') or 0.0)), None, None, None,
                               None, None, None, None)]
                ci = s.e('IfcCostItem', guid(f'5d|{codigo}'), None, ind['descripcion'][:255], ind['grupo'], None, codigo, Enum('NOTDEFINED'),
                         cvs, None)
            items.append(ci)
            s.e('IfcRelAssignsToControl', guid(f'rel|5d|{codigo}|{self.parte}'), None, None, None, por_item[codigo], None, ci)
        s.e('IfcRelAssignsToControl', guid(f'rel|5d|presupuesto-partidas|{self.parte}'), None, None, None, items, None, cs)
        s.e('IfcRelDeclares', guid(f'rel|declara|4d5d|{self.parte}'), None, None, None, self.proj, [ws, cs])


def tipo_tarea(f):
    """Tipo de tarea de IFC4 (IfcTaskTypeEnum) según la fase: obra, instalación de equipos o puesta en marcha."""
    if f['id'].startswith(('F9-FIJ', 'F10-DOT')):
        return 'INSTALLATION', None
    if f['id'].startswith('F11'):
        return 'USERDEFINED', 'PUESTA_EN_MARCHA'
    return 'CONSTRUCTION', None


def _orden(c):
    if '.' in c and c.split('.')[0].isdigit():
        a, b = c.split('.')
        return (0, int(a), int(b), '')
    return (1, 0, 0, c)


def exportar(M, parte):
    X = Exportador(M, parte)
    X.proyecto()
    ids = set()
    if parte in ('todo', 'principal'):
        fases = X.elementos()
        ids |= {e['id'] for e in M['elementos']}
    else:
        fases = {f['id']: f for f in M['cronograma']['fases']}
        X.ref = {}
    if parte in ('todo', 'refuerzo'):
        X.refuerzo(fases)
        ids |= {j['id'] for j in M['refuerzo']}
    X.cronograma_y_costos(fases, ids)
    nombre = {'todo': SALIDA.name, 'principal': SALIDA.name, 'refuerzo': SALIDA_REF.name}[parte]
    desc = {'todo': 'Modelo completo', 'principal': 'ARQ + EST + CIM + FIJO + DOT', 'refuerzo': 'REF (refuerzo)'}[parte]
    return X.S.texto(nombre, M['fecha'], f'Torre del hospital de Yondó, {desc}. {M["estado"]}'), X.S.cuenta


def main():
    M = leer(ENTRADA)
    texto, cuenta = exportar(M, 'todo')
    salidas = {}
    if len(texto.encode('utf-8')) / 1e6 > LIMITE_MB:
        for parte, ruta in (('principal', SALIDA), ('refuerzo', SALIDA_REF)):
            salidas[ruta] = exportar(M, parte)
    else:
        salidas[SALIDA] = (texto, cuenta)
    verificar = '--verificar' in sys.argv
    ok = True
    for ruta, (txt, cta) in salidas.items():
        b = txt.encode('utf-8')
        if verificar:
            igual = ruta.exists() and ruta.read_bytes() == b
            ok &= igual
            print(f'{rel(ruta)}: ' + ('al día' if igual else 'DESACTUALIZADO'))
            continue
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b)
        print(f'{rel(ruta)}: {len(b) / 1e6:.2f} MB, {txt.count(chr(10))} líneas')
    if not verificar and SALIDA in salidas and SALIDA_REF not in salidas and SALIDA_REF.exists():
        SALIDA_REF.unlink()
    if verificar:
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
