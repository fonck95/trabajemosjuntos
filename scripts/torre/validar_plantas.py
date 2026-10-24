"""Valida la planta de la torre con las reglas V1 a V20 del contrato (ESPECIFICACION_INTEGRACION.md, 3.5), V21 y V22 de
la sección 16 y V23 del prediseño estructural DMO (17.1).

Uso:
  python3 scripts/torre/validar_plantas.py                     # data/edificios/torre_hospital_plantas.json, todas las reglas
  python3 scripts/torre/validar_plantas.py --archivo RUTA      # otro archivo de plantas, todas las reglas
  python3 scripts/torre/validar_plantas.py --fixture [RUTA]    # fixture (por defecto scripts/fixtures/torre/plantas_min.json):
                                                               # omite V2, V6, V15, V16 y V20, que dependen del programa
                                                               # y de la retícula real
  Opciones: --programa RUTA (programa.json) y --reglas RUTA (reglas_planta.json; si no existe, se usan los valores
  por defecto del 3.4).

Imprime un informe JSON en la salida estándar (y un resumen de una línea en la de errores) y sale con 1 si hay errores
duros. Solo biblioteca estándar. Geometría ortogonal (rectángulos y polígonos ortogonales); recorridos por búsqueda con
pesos sobre una rejilla de 0,10 m.

Alcance ampliado (16): además de P1-P4 y BT valida los niveles EXT (exteriores inmediatos) y CUB (cubierta técnica).
Conceptos que el validador entiende (los escribe generar_plantas.py):
- muros de tipo «abierto» (espesor 0): vano abierto entre dos espacios; cuenta como acceso en V9 y V10 y no lleva puerta;
- recintos «de_paso» (vestíbulos, salas de espera, esclusa, puesto de enfermería): cuentan como circulación en V9;
- recintos no programados {nivel}-TEC-nn (programado: false): técnicos o de apoyo que pide el 16 y no trae el programa;
- recintos exteriores (exterior: true) y no transitables (transitable: false: huecos, sobrerrecorrido, huella de la torre);
- núcleos con varios recintos (ascensores: dos huecos), escaleras caminables por tramos y descansos con cotas (V21);
- V14 se aplica a los niveles cerrados (P1-P4 y BT); en EXT y CUB no aplica (son exteriores).
- Prediseño DMO (17.1, V23): «nucleo» es el muro estructural de concreto de 0,35 m y va solo sobre los paños que eligió el
  prediseño (data/sismo/torre_hospital_estructura.json → prediseno.eleccion_muros); el resto del borde de los núcleos es
  «nucleo_mamposteria». Las columnas tienen la sección del prediseño (0,80 m; 0,90 m en el eje A) y el área libre de cada
  recinto descuenta la parte de las columnas que entra en su polígono libre (V1 y V8).
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

REGLAS = {
    'V1': ('Esquema: campos, tipos, ids únicos y referencias; muros sobre los bordes, lados y cobertura; polígono libre', 'duro'),
    'V2': ('Conteo: recintos de cada fila = cantidad del programa; nombre y piso coinciden', 'duro'),
    'V3': ('Cada recinto dentro del contorno de su nivel (tolerancia 1 mm)', 'duro'),
    'V4': ('Sin traslapes entre recintos, circulaciones y núcleos (intersección < 0,01 m²)', 'duro'),
    'V5': ('Teselado: la unión de recintos es el contorno (diferencia ≤ 0,5 %)', 'duro'),
    'V6': ('Área a ejes ≥ área del programa − 0,05 m²', 'duro'),
    'V7': ('Área a ejes ≥ mínimo de la Res. 1633 y lado menor a ejes ≥ lado mínimo', 'duro'),
    'V8': ('Área libre bajo el mínimo de la Res. 1633 (por confirmar si se mide libre o a ejes)', 'aviso'),
    'V9': ('Cada recinto con al menos una puerta a una circulación o a un recinto de accesos_permitidos', 'duro'),
    'V10': ('Conectividad: todos los recintos alcanzables por puertas desde las conexiones verticales o entradas', 'duro'),
    'V11': ('Puertas: ancho ≥ el de su categoría; centro sobre su muro; ancho ≤ largo del muro − 0,10 m; alto 2,10 m', 'duro'),
    'V12': ('Abatimiento: el arco de una hoja no cruza otro arco ni un muro', 'duro'),
    'V13': ('Corredores: evacuación ≥ 2,40 m libres (duro); con camillas ≥ 2,80 m libres (aviso)', 'duro'),
    'V14': ('Evacuación: puerta de cada recinto a ≤ 30 m de una salida protegida y cualquier punto a ≤ 45 m', 'duro'),
    'V15': ('Núcleos iguales a programa.json → nucleos_verticales y conexiones verticales dentro de su núcleo', 'duro'),
    'V16': ('Columnas en las intersecciones de los ejes, dentro de un muro, en el contorno o en el borde de un corredor', 'duro'),
    'V17': ('Centroide de cada recinto dentro de la zona de su servicio', 'aviso'),
    'V18': ('Sala de rayos X y periapical con todos sus muros plomados', 'duro'),
    'V19': ('Hospitalización, TPR, observación, consultorios y terapias con ventana a fachada o patio', 'aviso'),
    'V20': ('Suma de áreas a ejes útiles por piso ≥ m² útiles del programa', 'duro'),
    'V21': ('Escaleras caminables: tramos y descansos dentro de su núcleo, con cotas continuas de piso a piso (16.1)', 'duro'),
    'V22': ('Paso físico (16 y 6.4): con muros, columnas y obstáculos del recorrido, un caminante de radio 0,30 m llega a cada '
            'recinto desde las entradas, conexiones y pasos de su nivel, en una sola zona por cota de piso; con radio 0,45 m '
            '(camilla) llega a los recintos de puertas para camas o camillas', 'duro'),
    'V23': ('Prediseño estructural DMO (17.1): columnas con la sección del prediseño; muros estructurales de concreto solo y '
            'completos sobre los paños del prediseño, sin puertas, vanos ni ventanas; cielo raso bajo las vigas; fosos y '
            'cisternas iguales a la cimentación', 'duro'),
}
SOLO_PROGRAMA = ('V2', 'V6', 'V15', 'V16', 'V20', 'V23')
ESTRUCTURA = C.DATOS / 'sismo' / 'torre_hospital_estructura.json'
MARCO_PUERTA_M = 0.05          # el vano de una puerta (hoja + marco) no puede tocar un muro estructural

TIPOS_ESPACIO = ('recinto', 'circulacion', 'nucleo')
ABRE = ('adentro', 'afuera', 'corrediza', 'doble')
TIPOS_CONEXION = ('escalera', 'ascensor', 'escalera_abierta', 'montacargas')
TIPOS_NUCLEO = ('escalera', 'ascensor', 'montacargas', 'ductos')
NIVELES_PISO = ('P1', 'P2', 'P3', 'P4')
NIVELES_EXTERIORES = ('EXT', 'CUB')

# Valores por defecto del 3.4 (se usan si reglas_planta.json no existe o no trae la clave)
REGLAS_PLANTA_DEFECTO = {
    'puertas': [
        {'categoria': 'camillas_procedimientos', 'ancho_m': 1.40, 'cita': 'Res. 1633, Cuadro 1'},
        {'categoria': 'camas', 'ancho_m': 1.20, 'cita': 'Res. 1633, Cuadro 1; NSR-10 K.3.14.2.3'},
        {'categoria': 'consultorio', 'ancho_m': 1.00, 'cita': 'Res. 1633, Cuadro 1'},
        {'categoria': 'bano', 'ancho_m': 1.00, 'cita': 'Res. 1633, Cuadro 1'},
        {'categoria': 'deposito', 'ancho_m': 0.90, 'cita': 'Res. 1633, Cuadro 1'},
        {'categoria': 'evacuacion', 'ancho_m': 1.10, 'cita': 'NSR-10 K.3.14.2.3 (puertas de salida para camas; normas.json)'},
    ],
    'corredores': {'evacuacion_min_m': 2.40, 'camillas_recomendado_m': 2.80, 'interno_min_m': 1.20},
    'evacuacion': {'puerta_a_escalera_max_m': 30.0, 'cualquier_punto_max_m': 45.0},
    'zonas': {},
    'accesos_permitidos': [],
    'niveles': {'piso_a_nivel': {'bloque técnico': 'BT'}, 'nivel_por_fila': {}},
}
COLUMNA_LIBRE_PERMITIDA = re.compile(r'gimnasio|expansi[oó]n|espera|vest[ií]bulo', re.I)
RE_PLOMADO = re.compile(r'rayos\s*x|periapical', re.I)
# Ambientes donde el paciente permanece o se atiende (habitaciones, TPR, observación, consultorios, terapias); los baños,
# depósitos y cuartos de apoyo de esos servicios no se exigen con ventana.
RE_VENTANA_EXIGIDA = re.compile(r'^(habitaci[oó]n|observaci[oó]n|consultorio|cub[ií]culo de atenci[oó]n|gimnasio|'
                                r'sala de procedimientos de terapia|ambiente individual de aislamiento)', re.I)
TOL = 1e-3


def num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def punto(v) -> bool:
    return isinstance(v, (list, tuple)) and len(v) >= 2 and num(v[0]) and num(v[1])


def poligono_valido(p) -> bool:
    return isinstance(p, list) and len(p) >= 4 and all(punto(v) for v in p) and C.area_poligono(p) > 1e-9


def cargar_reglas(ruta: Path | None) -> dict:
    r = {k: (list(v) if isinstance(v, list) else dict(v)) for k, v in REGLAS_PLANTA_DEFECTO.items()}
    r['fuente'] = 'valores por defecto del contrato (3.4)'
    if ruta and ruta.exists():
        dato = C.cargar_json(ruta)
        for k in ('puertas', 'corredores', 'evacuacion', 'zonas', 'accesos_permitidos', 'niveles'):
            if k in dato:
                if k == 'puertas':
                    cats = {p['categoria']: p for p in r['puertas']}
                    cats.update({p['categoria']: p for p in dato['puertas']})
                    r['puertas'] = list(cats.values())
                elif isinstance(dato[k], dict) and isinstance(r[k], dict):
                    r[k] = {**r[k], **dato[k]}
                else:
                    r[k] = dato[k]
        r['fuente'] = C.relativa(ruta)
    return r


class Nivel:
    """Índices de un nivel de la planta para no recalcular en cada regla."""

    def __init__(self, n: dict):
        self.d = n
        self.id = n.get('id')
        self.espacios = [r for r in n.get('recintos', []) if isinstance(r, dict)]
        self.por_id = {r.get('id'): r for r in self.espacios}
        self.pol = {r['id']: C.orientar_antihorario(r['poligono']) for r in self.espacios
                    if isinstance(r.get('id'), str) and poligono_valido(r.get('poligono'))}
        self.libre = {r['id']: C.orientar_antihorario(r['poligono_libre']) for r in self.espacios
                      if isinstance(r.get('id'), str) and poligono_valido(r.get('poligono_libre'))}
        # subrecintos (baños y cabinas dentro de un recinto; revisión adversarial): id → (subrecinto, recinto que lo contiene)
        self.subs = {sb['id']: (sb, r) for sb, r in C.subrecintos(n) if isinstance(sb.get('id'), str)}
        self.pol_sub = {sid: C.orientar_antihorario(sb['poligono']) for sid, (sb, r) in self.subs.items()
                        if poligono_valido(sb.get('poligono'))}
        self.libre_sub = {sid: C.orientar_antihorario(sb['poligono_libre']) for sid, (sb, r) in self.subs.items()
                          if poligono_valido(sb.get('poligono_libre'))}
        self.muros = {m.get('id'): m for m in n.get('muros', []) if isinstance(m, dict)}
        self.puertas = [p for p in n.get('puertas', []) if isinstance(p, dict)]
        self.ventanas = [v for v in n.get('ventanas', []) if isinstance(v, dict)]
        self.contorno = C.orientar_antihorario(n['contorno']) if poligono_valido(n.get('contorno')) else None
        # vanos abiertos (muros de tipo «abierto» entre dos espacios del nivel): cuentan como paso en V9 y V10
        self.abiertos = {rid: set() for rid in self.por_id}
        for m in self.muros.values():
            lados = m.get('lados')
            if m.get('tipo') == 'abierto' and isinstance(lados, list) and len(lados) == 2 \
                    and lados[0] in self.por_id and lados[1] in self.por_id:
                self.abiertos[lados[0]].add(lados[1])
                self.abiertos[lados[1]].add(lados[0])

    def padre(self, sid):
        """Recinto que contiene al subrecinto `sid` (None si no es un subrecinto)."""
        return self.subs[sid][1].get('id') if sid in self.subs else None

    def es_paso(self, rid) -> bool:
        """Circulación o recinto de paso (vestíbulo, espera, esclusa…): cuenta como circulación en V9."""
        r = self.por_id.get(rid) or {}
        return r.get('tipo') == 'circulacion' or bool(r.get('de_paso'))

    def transitable(self, rid) -> bool:
        return (self.por_id.get(rid) or {}).get('transitable', True) is not False

    def muros_validos(self):
        return [m for m in self.muros.values() if punto(m.get('a')) and punto(m.get('b'))
                and (C.es_horizontal(m['a'], m['b']) or C.es_vertical(m['a'], m['b']))
                and math.dist(m['a'][:2], m['b'][:2]) > TOL]

    def columnas(self) -> list[dict]:
        return [c for c in self.d.get('columnas', []) or [] if isinstance(c, dict) and num(c.get('x')) and num(c.get('y'))]

    def espacio_en(self, pt):
        for rid, p in self.pol.items():
            if C.punto_en_poligono(pt, p, 0.0):
                return rid
        return None


def rects_columnas(nv) -> list[tuple]:
    out = []
    for c in nv.d.get('columnas', []) or []:
        if isinstance(c, dict) and num(c.get('x')) and num(c.get('y')):
            b, h = float(c.get('b', 0.6)) / 2, float(c.get('h', 0.6)) / 2
            out.append((c['x'] - b, c['y'] - h, c['x'] + b, c['y'] + h, c.get('id')))
    return out


def libre_de_columnas(lo: float, hi: float, a, b, cols) -> tuple[float, list]:
    """Tramo libre más largo de [lo, hi] sobre la recta del muro a-b, descontadas las columnas que la cruzan."""
    hz = C.es_horizontal(a, b)
    fijo = a[1] if hz else a[0]
    tramos, tapan = [(lo, hi)], []
    for q in cols:
        if hz and not (q[1] + 1e-6 < fijo < q[3] - 1e-6):
            continue
        if not hz and not (q[0] + 1e-6 < fijo < q[2] - 1e-6):
            continue
        c0, c1 = (q[0], q[2]) if hz else (q[1], q[3])
        nuevos = []
        for t0, t1 in tramos:
            if c1 <= t0 + 1e-9 or c0 >= t1 - 1e-9:
                nuevos.append((t0, t1))
                continue
            tapan.append(q[4])
            if c0 > t0:
                nuevos.append((t0, c0))
            if c1 < t1:
                nuevos.append((c1, t1))
        tramos = nuevos
    return max([t1 - t0 for t0, t1 in tramos] or [0.0]), sorted(set(tapan))


class Validador:
    def __init__(self, plantas: dict, informe: C.Informe, fixture: bool, programa: dict | None, reglas: dict,
                 estructura: dict | None = None):
        self.pl = plantas
        self.inf = informe
        self.fixture = fixture
        self.programa = programa
        self.reglas = reglas
        self.estructura = estructura
        self.cat_puertas = {p['categoria']: p for p in reglas['puertas']}

    # ------------------------------------------------------------------------------------------------ utilidades
    def err(self, regla, msg):
        self.inf.error(regla, msg)

    def av(self, regla, msg):
        self.inf.aviso(regla, msg)

    # ------------------------------------------------------------------------------------------------ V1
    def v1_general(self):
        pl = self.pl
        for campo, tipo in (('id', str), ('version', int), ('tipo_dato', str), ('marco', dict), ('reticula', dict),
                            ('tipos_muro', dict), ('niveles', list), ('grupos_1633', dict)):
            if not isinstance(pl.get(campo), tipo):
                self.err('V1', f'falta el campo «{campo}» o no es {tipo.__name__}')
        if not num(pl.get('modulo_m')):
            self.err('V1', 'falta «modulo_m» numérico')
        marco = pl.get('marco') or {}
        if marco.get('ancla') != C.ANCLA:
            self.err('V1', f'marco.ancla debe ser {C.ANCLA}')
        ret = pl.get('reticula') or {}
        for clave, coord in (('ejes_x', 'x'), ('ejes_y', 'y')):
            ejes = ret.get(clave)
            if not isinstance(ejes, list) or not ejes or not all(isinstance(e, dict) and isinstance(e.get('id'), str)
                                                                  and num(e.get(coord)) for e in ejes):
                self.err('V1', f'reticula.{clave} debe ser una lista de {{id, {coord}}}')
        for t, d in (pl.get('tipos_muro') or {}).items():
            if not isinstance(d, dict) or not num(d.get('espesor_m')) or d['espesor_m'] < 0 \
                    or (d['espesor_m'] == 0 and t != 'abierto'):
                self.err('V1', f'tipos_muro.{t} sin espesor_m positivo (solo el vano «abierto» tiene espesor 0)')
        for g, d in (pl.get('grupos_1633') or {}).items():
            if not isinstance(d, dict) or not isinstance(d.get('nombre'), str) or not isinstance(d.get('cita'), str):
                self.err('V1', f'grupos_1633.{g} sin nombre o sin cita')
            elif not isinstance(d.get('color_hex'), str) or not C.RE_COLOR.match(d['color_hex'].lower()):
                self.err('V1', f'grupos_1633.{g}.color_hex no es un color #rrggbb: {d.get("color_hex")!r}')
        ids_niveles = [n.get('id') for n in pl.get('niveles') or [] if isinstance(n, dict)]
        if len(ids_niveles) != len(set(ids_niveles)):
            self.err('V1', f'ids de nivel repetidos: {ids_niveles}')
        todos = [r.get('id') for n in pl.get('niveles') or [] if isinstance(n, dict) for r in n.get('recintos', [])
                 if isinstance(r, dict)]
        rep = sorted({x for x in todos if todos.count(x) > 1}, key=str)
        if rep:
            self.err('V1', f'ids de recinto repetidos entre niveles: {rep}')
        self.inf.revisado('V1')

    def v1_nivel(self, nv: Nivel):
        n, P = nv.d, nv.id
        pre = f'{P}: '
        if not isinstance(P, str) or not C.RE_NIVEL.match(P):
            self.err('V1', f'id de nivel no válido: {P!r}')
            return
        try:
            if C.prefijo_nivel(n.get('piso')) != P:
                self.err('V1', f'{pre}el piso {n.get("piso")!r} no corresponde al id del nivel')
        except ValueError as e:
            self.err('V1', f'{pre}{e}')
        for campo in ('z', 'altura_entrepiso_m', 'altura_libre_m'):
            if not num(n.get(campo)):
                self.err('V1', f'{pre}falta «{campo}» numérico')
        for campo in ('columnas', 'recintos', 'nucleos', 'muros', 'puertas', 'ventanas', 'conexiones_verticales',
                      'entradas_recorrido', 'obstaculos_recorrido'):
            if not isinstance(n.get(campo), list):
                self.err('V1', f'{pre}falta la lista «{campo}»')
        if nv.contorno is None:
            self.err('V1', f'{pre}contorno ausente o no válido')
            return
        if not C.es_ortogonal(nv.contorno):
            self.err('V1', f'{pre}el contorno no es ortogonal')
        grupos = self.pl.get('grupos_1633') or {}
        tipos_muro = self.pl.get('tipos_muro') or {}
        ret = self.pl.get('reticula') or {}
        x0 = (ret.get('ejes_x') or [{'x': 0}])[0].get('x', 0)
        y0 = (ret.get('ejes_y') or [{'y': 0}])[0].get('y', 0)
        modulo = 0.60   # el trazado va, cuando se pueda, en múltiplos de 0,60 m desde los ejes (3.2; aviso)

        # ids únicos en el nivel
        ids = []
        for clave in ('recintos', 'muros', 'puertas', 'ventanas', 'nucleos'):
            ids += [x.get('id') for x in n.get(clave, []) if isinstance(x, dict)]
        ids += [sb.get('id') for sb, _ in C.subrecintos(n)]
        rep = sorted({x for x in ids if ids.count(x) > 1}, key=str)
        if rep:
            self.err('V1', f'{pre}ids repetidos: {rep}')

        # recintos, circulaciones y núcleos
        for r in nv.espacios:
            rid = r.get('id')
            q = f'{pre}{rid}: '
            tipo = r.get('tipo')
            if tipo not in TIPOS_ESPACIO:
                self.err('V1', f'{q}tipo {tipo!r} no es uno de {TIPOS_ESPACIO}')
            if not isinstance(r.get('ambiente'), str) or not r['ambiente']:
                self.err('V1', f'{q}falta «ambiente»')
            if tipo == 'circulacion' and r.get('fila') is None:
                m = C.RE_CIRCULACION.match(str(rid))
                if not m or m.group(1) != P:
                    self.err('V1', f'{q}id de circulación mal formado (se espera {P}-CIRC-nn)')
            elif r.get('programado') is False:
                m = C.RE_TECNICO.match(str(rid))
                if not m or m.group(1) != P:
                    self.err('V1', f'{q}id de recinto no programado mal formado (se espera {P}-TEC-nn)')
                if r.get('grupo_1633') not in grupos:
                    self.err('V1', f'{q}grupo_1633 {r.get("grupo_1633")!r} no está en grupos_1633')
                if not any('estimaci' in str(x) for x in r.get('notas') or []):
                    self.err('V1', f'{q}un recinto no programado debe llevar la nota «estimación» (16.1)')
            else:
                m = C.RE_RECINTO.match(str(rid))
                if not m or m.group(1) != P:
                    self.err('V1', f'{q}id de recinto mal formado (se espera {P}-Afff-kk)')
                for campo in ('fila', 'k', 'de'):
                    if not isinstance(r.get(campo), int) or isinstance(r.get(campo), bool):
                        self.err('V1', f'{q}falta «{campo}» entero')
                if m and isinstance(r.get('fila'), int) and isinstance(r.get('k'), int):
                    if int(m.group(2)) != r['fila'] or int(m.group(3)) != r['k']:
                        self.err('V1', f'{q}el id no corresponde a fila {r["fila"]} y k {r["k"]} (regla 1.3)')
                if isinstance(r.get('k'), int) and isinstance(r.get('de'), int) and not 1 <= r['k'] <= r['de']:
                    self.err('V1', f'{q}k = {r["k"]} fuera de 1…{r["de"]}')
                if not isinstance(r.get('servicio_programa'), str):
                    self.err('V1', f'{q}falta «servicio_programa»')
                if r.get('grupo_1633') not in grupos:
                    self.err('V1', f'{q}grupo_1633 {r.get("grupo_1633")!r} no está en grupos_1633')
            if tipo == 'circulacion' and 'grupo_1633' in r and r['grupo_1633'] not in grupos:
                self.err('V1', f'{q}grupo_1633 {r["grupo_1633"]!r} no está en grupos_1633')
            if rid not in nv.pol:
                self.err('V1', f'{q}polígono ausente o no válido')
                continue
            p = nv.pol[rid]
            if not C.es_ortogonal(p):
                self.err('V1', f'{q}el polígono no es ortogonal')
            fuera = [v for v in r['poligono'] if not (C.es_multiplo(v[0], 0.05) and C.es_multiplo(v[1], 0.05))]
            if fuera:
                self.err('V1', f'{q}coordenadas que no son múltiplo de 0,05 m: {fuera}')
            fuera_mod = [v for v in r['poligono'] if not (C.es_multiplo(v[0], modulo, x0) and C.es_multiplo(v[1], modulo, y0))]
            if fuera_mod:
                self.av('V1', f'{q}vértices que no caen en múltiplos de 0,60 m desde los ejes: {fuera_mod}')
            if not num(r.get('area_ejes_m2')) or abs(r['area_ejes_m2'] - C.area_poligono(p)) > 0.01:
                self.err('V1', f'{q}area_ejes_m2 = {r.get("area_ejes_m2")} y el polígono mide {C.area_poligono(p):.3f} m²')
            if rid not in nv.libre:
                self.err('V1', f'{q}falta poligono_libre válido')
            else:
                if 'area_libre_m2' in r or tipo == 'recinto':
                    al = C.area_libre(nv.libre[rid], nv.columnas())
                    if not num(r.get('area_libre_m2')) or abs(r['area_libre_m2'] - al) > 0.01:
                        self.err('V1', f'{q}area_libre_m2 = {r.get("area_libre_m2")} y el polígono libre, sin las columnas, '
                                       f'mide {al:.3f} m²')
                if not C.poligono_dentro_de(nv.libre[rid], p, TOL):
                    self.err('V1', f'{q}el polígono libre se sale del polígono a ejes')
            mn = r.get('minimo_1633')
            if mn is not None and not (isinstance(mn, dict) and num(mn.get('m2'))
                                       and (mn.get('lado_m') is None or num(mn.get('lado_m')))
                                       and isinstance(mn.get('cita'), str)):
                self.err('V1', f'{q}minimo_1633 debe ser null o {{m2, lado_m (o null), cita}}')
            for clave in ('acceso', 'puertas', 'ventanas'):
                if clave in r and not isinstance(r[clave], list):
                    self.err('V1', f'{q}«{clave}» debe ser una lista')

        # muros
        validos = []
        for m in nv.muros.values():
            mid = m.get('id')
            q = f'{pre}{mid}: '
            mm = C.RE_MURO.match(str(mid))
            if not mm or mm.group(1) != P:
                self.err('V1', f'{q}id de muro mal formado (se espera {P}-M-nnnn)')
            if not (punto(m.get('a')) and punto(m.get('b'))):
                self.err('V1', f'{q}faltan los extremos a y b')
                continue
            a, b = m['a'], m['b']
            if not (C.es_horizontal(a, b) or C.es_vertical(a, b)) or math.dist(a[:2], b[:2]) <= TOL:
                self.err('V1', f'{q}el muro no es horizontal ni vertical o no tiene largo')
                continue
            if not all(C.es_multiplo(v, 0.05) for v in (*a[:2], *b[:2])):
                self.err('V1', f'{q}extremos que no son múltiplo de 0,05 m')
            t = m.get('tipo')
            if t not in tipos_muro:
                self.err('V1', f'{q}tipo {t!r} no está en tipos_muro')
            elif not num(m.get('espesor')) or abs(m['espesor'] - tipos_muro[t].get('espesor_m', -1)) > 1e-6:
                self.err('V1', f'{q}espesor {m.get("espesor")} distinto del de su tipo ({tipos_muro[t].get("espesor_m")})')
            if not num(m.get('altura')) or (m['altura'] <= 0 and t != 'abierto'):
                self.err('V1', f'{q}falta altura positiva')
            if not isinstance(m.get('estructural'), bool):
                self.err('V1', f'{q}«estructural» debe ser booleano')
            lados = m.get('lados')
            if not (isinstance(lados, list) and len(lados) == 2):
                self.err('V1', f'{q}«lados» debe ser [izquierdo, derecho]')
                continue
            validos.append(m)
            nl = C.normal_unitaria_izquierda(a, b)
            for s, lado in ((1, lados[0]), (-1, lados[1])):
                prueba = [((a[0] + (b[0] - a[0]) * f) + s * 0.02 * nl[0], (a[1] + (b[1] - a[1]) * f) + s * 0.02 * nl[1])
                          for f in (0.25, 0.5, 0.75)]
                nombre_lado = 'izquierdo' if s == 1 else 'derecho'
                if lado is None:
                    if t != 'fachada' or 'exterior' not in lados:
                        self.err('V1', f'{q}lado {nombre_lado} null solo se permite en muros de fachada con el otro lado «exterior»')
                    elif not all(C.punto_en_poligono(x, nv.contorno, 0.0) for x in prueba):
                        self.err('V1', f'{q}el lado {nombre_lado} (null) debería quedar dentro del contorno')
                elif lado == 'exterior':
                    if any(C.punto_en_poligono(x, nv.contorno, 0.0) for x in prueba):
                        self.err('V1', f'{q}el lado {nombre_lado} dice «exterior» pero queda dentro del contorno (mirando de a a b)')
                    if not C.segmento_en_borde(a, b, nv.contorno):
                        self.err('V1', f'{q}muro con lado exterior que no está sobre el contorno')
                elif lado in nv.subs:
                    otro = lados[1] if s == 1 else lados[0]
                    if otro != nv.padre(lado) and nv.padre(otro) != nv.padre(lado):
                        self.err('V1', f'{q}el tabique del subrecinto {lado} debe separarlo de {nv.padre(lado)} o de otro '
                                       f'subrecinto del mismo recinto (separa {lados})')
                    elif lado not in nv.pol_sub:
                        self.err('V1', f'{q}el subrecinto {lado} no tiene polígono válido')
                    elif not C.segmento_en_borde(a, b, nv.pol_sub[lado]):
                        self.err('V1', f'{q}no está sobre el borde del subrecinto {lado}')
                    elif not all(C.punto_en_poligono(x, nv.pol_sub[lado], 0.0) for x in prueba):
                        self.err('V1', f'{q}{lado} no queda a su lado {nombre_lado} (mirando de a a b)')
                elif lado not in nv.pol:
                    self.err('V1', f'{q}lado {nombre_lado} {lado!r} no es un recinto del nivel')
                elif nv.padre(lados[1] if s == 1 else lados[0]) == lado:
                    # tabique de un baño visto desde el recinto que lo contiene: ese lado es del recinto y no de sus baños
                    if not all(C.punto_en_poligono(x, nv.pol[lado], 0.0) for x in prueba) or any(
                            C.punto_en_poligono(x, nv.pol_sub[sid], 0.0) for x in prueba for sid in nv.pol_sub
                            if nv.padre(sid) == lado):
                        self.err('V1', f'{q}{lado} no queda a su lado {nombre_lado} (mirando de a a b), afuera de sus baños')
                else:
                    if not C.segmento_en_borde(a, b, nv.pol[lado]):
                        self.err('V1', f'{q}no está sobre el borde de {lado}')
                    elif not all(C.punto_en_poligono(x, nv.pol[lado], 0.0) for x in prueba):
                        self.err('V1', f'{q}{lado} no queda a su lado {nombre_lado} (mirando de a a b)')
        # muros duplicados
        for i, m1 in enumerate(validos):
            for m2 in validos[i + 1:]:
                if C.solape_colineal(m1['a'], m1['b'], m2['a'], m2['b'], 0.01):
                    self.err('V1', f'{pre}{m1["id"]} y {m2["id"]} se solapan')
        # cobertura: cada borde común entre dos espacios y cada borde del contorno lleva muro
        ids_pol = list(nv.pol)
        cajas = {k: C.caja(v) for k, v in nv.pol.items()}
        for i, r1 in enumerate(ids_pol):
            for r2 in ids_pol[i + 1:]:
                if not C.cajas_se_tocan(cajas[r1], cajas[r2], TOL):
                    continue
                segs = [(m['a'], m['b']) for m in validos if set(m['lados']) == {r1, r2}]
                for s0, s1 in C.bordes_comunes(nv.pol[r1], nv.pol[r2]):
                    L = math.dist(s0, s1)
                    if C.largo_cubierto(s0, s1, segs) < L - TOL:
                        self.err('V1', f'{pre}el borde común entre {r1} y {r2} ({s0} → {s1}) no está cubierto por un '
                                       f'muro con esos dos lados')
        self._subrecintos(nv, validos)
        segs_ext = [(m['a'], m['b']) for m in validos if 'exterior' in m['lados']]
        for s0, s1 in C.bordes(nv.contorno):
            if C.largo_cubierto(s0, s1, segs_ext) < math.dist(s0[:2], s1[:2]) - TOL:
                self.err('V1', f'{pre}el borde del contorno {s0} → {s1} no está cubierto por muros de fachada')

        # polígono libre: cada borde a ejes se corre la mitad del espesor del muro que lo ocupa
        for rid, p in nv.pol.items():
            if rid not in nv.libre:
                continue
            cortes = [v for m in validos for v in (m['a'], m['b'])]
            pp = C.partir_bordes(p, cortes)
            ds = []
            for s0, s1 in C.bordes(pp):
                esp = [m['espesor'] for m in validos if num(m.get('espesor'))
                       and C.solape_colineal(s0, s1, m['a'], m['b'], 1e-6)]
                ds.append(max(esp) / 2 if esp else 0.0)
            esperado = C.desplazar_adentro(pp, ds)
            dado = nv.libre[rid]
            quitar = self._huecos_de_banos(nv, rid, validos)
            if quitar:
                # el polígono libre del recinto descuenta sus baños y la mitad del tabique que los rodea
                rects = C.rectangulos_menos(esperado, quitar)
                a_esp = sum((r_[2] - r_[0]) * (r_[3] - r_[1]) for r_ in rects)
                inter = sum(C.area_interseccion(C.rect_a_poligono(list(r_)), dado) for r_ in rects)
                dif = a_esp + C.area_poligono(dado) - 2 * inter
                esperado = [list(r_) for r_ in rects]
            else:
                dif = C.area_poligono(esperado) + C.area_poligono(dado) - 2 * C.area_interseccion(esperado, dado)
            if dif > 0.01:
                self.err('V1', f'{pre}{rid}: el polígono libre no corresponde a desplazar cada borde la mitad del espesor '
                               f'de su muro (diferencia {dif:.3f} m²; esperado {C.redondear_todo(esperado, 3)})')

        # puertas
        vecinos = {rid: set() for rid in nv.por_id}
        puertas_de = {rid: set() for rid in nv.por_id}
        puertas_sub = {}
        for pt in nv.puertas:
            pid = pt.get('id')
            q = f'{pre}{pid}: '
            mm = C.RE_PUERTA.match(str(pid))
            if not mm or mm.group(1) != P:
                self.err('V1', f'{q}id de puerta mal formado (se espera {P}-PT-nnn)')
            m = nv.muros.get(pt.get('muro'))
            if m is None:
                self.err('V1', f'{q}el muro {pt.get("muro")!r} no existe')
            elif m.get('tipo') == 'abierto':
                self.err('V1', f'{q}la puerta está en un vano abierto (sobra: el paso ya es libre)')
            if not punto(pt.get('centro')) or not num(pt.get('ancho')) or not num(pt.get('alto')):
                self.err('V1', f'{q}faltan centro, ancho o alto')
                continue
            if not isinstance(pt.get('hojas'), int) or pt['hojas'] < 1:
                self.err('V1', f'{q}«hojas» debe ser un entero ≥ 1')
            if pt.get('abre') not in ABRE:
                self.err('V1', f'{q}«abre» {pt.get("abre")!r} no es uno de {ABRE}')
            if 'bisagra' in pt and pt['bisagra'] not in ('izquierda', 'derecha'):
                self.err('V1', f'{q}«bisagra» debe ser izquierda o derecha')
            if not isinstance(pt.get('categoria'), str):
                self.err('V1', f'{q}falta «categoria»')
            de, ha = pt.get('desde'), pt.get('hacia')
            for lado in (de, ha):
                if lado != 'exterior' and lado not in nv.por_id and lado not in nv.subs:
                    self.err('V1', f'{q}{lado!r} no es un recinto ni un subrecinto del nivel ni «exterior»')
            if de == ha:
                self.err('V1', f'{q}desde y hacia son el mismo')
            if m is not None and isinstance(m.get('lados'), list) and len(m['lados']) == 2:
                lados = set(m['lados'])
                if None in lados:
                    otro = ha if de == 'exterior' else de
                    if 'exterior' not in (de, ha):
                        self.err('V1', f'{q}una puerta en un muro de fachada debe ir hacia «exterior»')
                    elif otro in nv.pol and C.distancia_a_borde(pt['centro'], nv.pol[otro]) > TOL:
                        self.err('V1', f'{q}{otro} no está junto a la puerta')
                elif {de, ha} != lados:
                    self.err('V1', f'{q}une {de} y {ha}, pero su muro separa {m["lados"]}')
            if de in nv.subs or ha in nv.subs:
                for x in (de, ha):
                    if x in nv.subs:
                        puertas_sub.setdefault(x, set()).add(pid)
                continue                  # la puerta de un baño se lista en su subrecinto, no en el recinto
            for a_, b_ in ((de, ha), (ha, de)):
                if a_ in vecinos:
                    vecinos[a_].add(b_)
                    puertas_de[a_].add(pid)
        for rid, otros in nv.abiertos.items():
            vecinos.setdefault(rid, set()).update(otros)
        for r in nv.espacios:
            rid = r.get('id')
            if 'acceso' in r and isinstance(r['acceso'], list) and set(r['acceso']) != vecinos.get(rid, set()):
                self.err('V1', f'{pre}{rid}: «acceso» = {sorted(r["acceso"])} y sus puertas y vanos abiertos llevan a '
                               f'{sorted(vecinos.get(rid, set()), key=str)}')
            if 'puertas' in r and isinstance(r['puertas'], list) and set(r['puertas']) != puertas_de.get(rid, set()):
                self.err('V1', f'{pre}{rid}: «puertas» = {sorted(r["puertas"])} y las que lo tocan son '
                               f'{sorted(puertas_de.get(rid, set()), key=str)}')
        for sid, (sb, r) in nv.subs.items():
            if not isinstance(sb.get('puertas'), list) or set(sb['puertas']) != puertas_sub.get(sid, set()):
                self.err('V1', f'{pre}{sid}: «puertas» = {sb.get("puertas")} y las que lo tocan son '
                               f'{sorted(puertas_sub.get(sid, set()))}')
            if not puertas_sub.get(sid):
                self.err('V9', f'{pre}{sid} ({sb.get("nombre")}): el baño no tiene puerta')
            self.inf.revisado('V9')

        # ventanas
        ventanas_de = {}
        for v in nv.ventanas:
            vid = v.get('id')
            q = f'{pre}{vid}: '
            mm = C.RE_VENTANA.match(str(vid))
            if not mm or mm.group(1) != P:
                self.err('V1', f'{q}id de ventana mal formado (se espera {P}-VN-nnn)')
            m = nv.muros.get(v.get('muro'))
            if m is None or not punto(m.get('a')):
                self.err('V1', f'{q}el muro {v.get("muro")!r} no existe')
                continue
            if not (punto(v.get('centro')) and num(v.get('ancho')) and num(v.get('antepecho')) and num(v.get('alto'))):
                self.err('V1', f'{q}faltan centro, ancho, antepecho o alto')
                continue
            if 'exterior' not in (m.get('lados') or []):
                self.err('V1', f'{q}la ventana va en un muro que no da al exterior')
            if C.distancia_punto_segmento(v['centro'], m['a'], m['b']) > TOL:
                self.err('V1', f'{q}el centro no está sobre su muro')
                continue
            u = (C.es_horizontal(m['a'], m['b']))
            c, w = v['centro'], v['ancho'] / 2
            s0, s1 = ((c[0] - w, c[1]), (c[0] + w, c[1])) if u else ((c[0], c[1] - w), (c[0], c[1] + w))
            if C.largo_cubierto(s0, s1, [(m['a'], m['b'])]) < 2 * w - TOL:
                self.err('V1', f'{q}la ventana se sale de su muro')
            if v['antepecho'] + v['alto'] > m.get('altura', 0) + TOL:
                self.err('V1', f'{q}antepecho + alto supera la altura del muro')
            dueños = [rid for rid, p in nv.pol.items() if C.segmento_en_borde(s0, s1, p)]
            if len(dueños) != 1:
                self.err('V1', f'{q}la ventana debe quedar sobre el borde de un solo recinto (queda en {dueños})')
            else:
                ventanas_de.setdefault(dueños[0], set()).add(vid)
        for r in nv.espacios:
            if 'ventanas' in r and isinstance(r['ventanas'], list) and set(r['ventanas']) != ventanas_de.get(r.get('id'), set()):
                self.err('V1', f'{pre}{r.get("id")}: «ventanas» = {sorted(r["ventanas"])} y las que están en su borde son '
                               f'{sorted(ventanas_de.get(r.get("id"), set()))}')

        # núcleos
        for nu in n.get('nucleos', []):
            q = f'{pre}{nu.get("id")}: '
            mm = C.RE_NUCLEO.match(str(nu.get('id')))
            if not mm or mm.group(1) != P:
                self.err('V1', f'{q}id de núcleo mal formado (se espera {P}-NUC-…)')
            if nu.get('tipo') not in TIPOS_NUCLEO:
                self.err('V1', f'{q}tipo {nu.get("tipo")!r} no es uno de {TIPOS_NUCLEO}')
            recs = nu.get('recintos') or [nu.get('recinto')]
            if nu.get('recinto') not in recs:
                self.err('V1', f'{q}«recinto» debe ser uno de «recintos»')
            faltan = [x for x in recs if x not in nv.pol]
            if faltan:
                self.err('V1', f'{q}recintos que no existen: {faltan}')
            elif not poligono_valido(nu.get('poligono')):
                self.err('V1', f'{q}polígono del núcleo no válido')
            else:
                pols = [nv.pol[x] for x in recs]
                ap = C.area_poligono(nu['poligono'])
                dentro = sum(C.area_interseccion(nu['poligono'], q_) for q_ in pols)
                if dentro < ap - 0.01:
                    self.err('V1', f'{q}el polígono del núcleo no queda dentro de sus recintos {recs}')

        # conexiones verticales
        for cv in n.get('conexiones_verticales', []):
            q = f'{pre}conexión {cv.get("id")}: '
            if not isinstance(cv.get('id'), str):
                self.err('V1', f'{q}falta id')
            if cv.get('tipo') not in TIPOS_CONEXION:
                self.err('V1', f'{q}tipo {cv.get("tipo")!r} no es uno de {TIPOS_CONEXION}')
            pisos = cv.get('pisos')
            if not isinstance(pisos, list) or not pisos:
                self.err('V1', f'{q}falta la lista de pisos')
                continue
            if n.get('piso') not in pisos:
                self.err('V1', f'{q}el piso {n.get("piso")} no está en {pisos}')
            pts = cv.get('puntos') or {}
            p_aqui = pts.get(str(n.get('piso')))
            if not punto(p_aqui):
                self.err('V1', f'{q}falta el punto del piso {n.get("piso")}')
            elif nv.espacio_en(p_aqui) is None:
                self.err('V1', f'{q}el punto {p_aqui} no cae en ningún recinto')

        # entradas, columnas y obstáculos
        for e in n.get('entradas_recorrido', []):
            q = f'{pre}entrada {e.get("id")}: '
            if not (isinstance(e.get('id'), str) and punto(e.get('punto')) and num(e.get('mirando_deg'))
                    and isinstance(e.get('nombre'), str)):
                self.err('V1', f'{q}debe tener id, punto, mirando_deg y nombre')
            elif nv.espacio_en(e['punto']) is None:
                self.err('V1', f'{q}el punto {e["punto"]} no cae en ningún recinto')
        for col in n.get('columnas', []):
            if not (isinstance(col, dict) and isinstance(col.get('id'), str) and all(num(col.get(k)) for k in ('x', 'y', 'b', 'h'))):
                self.err('V1', f'{pre}columna mal formada: {col}')
        for ob in n.get('obstaculos_recorrido', []):
            p = ob.get('poligono') if isinstance(ob, dict) else ob
            if not poligono_valido(p):
                self.err('V1', f'{pre}obstáculo del recorrido sin polígono válido: {ob}')
        self.inf.revisado('V1')

    def _huecos_de_banos(self, nv: Nivel, rid, validos) -> list:
        """Rectángulos de los baños del recinto agrandados la mitad del espesor de su tabique."""
        out = []
        for sid, (sb, r) in nv.subs.items():
            if r.get('id') != rid or sid not in nv.pol_sub:
                continue
            esp = [m['espesor'] for m in validos if sid in m['lados'] and num(m.get('espesor'))]
            e = max(esp) / 2 if esp else 0.0
            x0, y0, x1, y1 = C.caja(nv.pol_sub[sid])
            out.append((x0 - e, y0 - e, x1 + e, y1 + e))
        return out

    def _subrecintos(self, nv: Nivel, validos):
        """Baños y cabinas (revisión adversarial): dentro de su recinto, sin traslaparse, con tabique en cada borde que no
        es borde del recinto, polígono libre y áreas coherentes. El área sigue contando en el recinto del programa."""
        pre = f'{nv.id}: '
        for sid, (sb, r) in nv.subs.items():
            rid = r.get('id')
            q = f'{pre}{sid}: '
            self.inf.revisado('V1')
            if not re.fullmatch(re.escape(str(rid)) + r'-B\d+', sid):
                self.err('V1', f'{q}id de subrecinto mal formado (se espera {rid}-Bn)')
            if not isinstance(sb.get('nombre'), str) or not sb['nombre']:
                self.err('V1', f'{q}falta «nombre»')
            if sid not in nv.pol_sub or rid not in nv.pol:
                self.err('V1', f'{q}polígono ausente o no válido')
                continue
            p, P = nv.pol_sub[sid], nv.pol[rid]
            if not C.es_ortogonal(p):
                self.err('V1', f'{q}el polígono no es ortogonal')
            if any(not (C.es_multiplo(v[0], 0.05) and C.es_multiplo(v[1], 0.05)) for v in sb['poligono']):
                self.err('V1', f'{q}coordenadas que no son múltiplo de 0,05 m')
            if not C.poligono_dentro_de(p, P, TOL):
                self.err('V1', f'{q}se sale de {rid}')
            for sid2 in nv.pol_sub:
                if sid2 > sid and nv.padre(sid2) == rid and C.area_interseccion(p, nv.pol_sub[sid2]) >= 0.01:
                    self.err('V1', f'{q}se traslapa con {sid2}')
            if not num(sb.get('area_ejes_m2')) or abs(sb['area_ejes_m2'] - C.area_poligono(p)) > 0.01:
                self.err('V1', f'{q}area_ejes_m2 = {sb.get("area_ejes_m2")} y el polígono mide {C.area_poligono(p):.3f} m²')
            # tabiques: cada borde del baño va sobre el borde del recinto o sobre un tabique del baño
            segs = [(m['a'], m['b']) for m in validos if sid in m['lados']]
            for s0, s1 in C.bordes(p):
                L = math.dist(s0, s1)
                if C.largo_cubierto(s0, s1, C.bordes(P)) + C.largo_cubierto(s0, s1, segs) < L - TOL:
                    self.err('V1', f'{q}el borde {s0} → {s1} no lleva tabique ni es borde de {rid}')
            if sid not in nv.libre_sub:
                self.err('V1', f'{q}falta poligono_libre válido')
                continue
            lp = nv.libre_sub[sid]
            al = C.area_libre(lp, nv.columnas())
            if not num(sb.get('area_libre_m2')) or abs(sb['area_libre_m2'] - al) > 0.01:
                self.err('V1', f'{q}area_libre_m2 = {sb.get("area_libre_m2")} y el polígono libre, sin las columnas, mide {al:.3f} m²')
            if not C.poligono_dentro_de(lp, p, TOL):
                self.err('V1', f'{q}el polígono libre se sale del polígono a ejes')
            cortes = [v for m in validos for v in (m['a'], m['b'])]
            pp = C.partir_bordes(p, cortes)
            ds = []
            for s0, s1 in C.bordes(pp):
                esp = [m['espesor'] for m in validos if num(m.get('espesor')) and C.solape_colineal(s0, s1, m['a'], m['b'], 1e-6)]
                ds.append(max(esp) / 2 if esp else 0.0)
            esperado = C.desplazar_adentro(pp, ds)
            dif = C.area_poligono(esperado) + C.area_poligono(lp) - 2 * C.area_interseccion(esperado, lp)
            if dif > 0.01:
                self.err('V1', f'{q}el polígono libre no corresponde a desplazar cada borde la mitad del espesor de su muro '
                               f'(diferencia {dif:.3f} m²)')

    def v1_conexiones(self, niveles: list[Nivel]):
        """La misma conexión vertical aparece igual en todos los pisos que une."""
        por_id = {}
        pisos_presentes = {nv.d.get('piso') for nv in niveles}
        for nv in niveles:
            for cv in nv.d.get('conexiones_verticales', []):
                por_id.setdefault(cv.get('id'), []).append((nv, cv))
        for cid, lista in por_id.items():
            base = lista[0][1]
            for nv, cv in lista[1:]:
                if cv.get('pisos') != base.get('pisos') or cv.get('tipo') != base.get('tipo'):
                    self.err('V1', f'conexión {cid}: pisos o tipo distintos entre niveles')
            presentes = {nv.d.get('piso') for nv, _ in lista}
            faltan = [p for p in (base.get('pisos') or []) if p in pisos_presentes and p not in presentes]
            if faltan:
                self.err('V1', f'conexión {cid}: no aparece en los niveles de los pisos {faltan}')

    # ------------------------------------------------------------------------------------------------ V3 a V5
    def v3_v4_v5(self, nv: Nivel):
        if nv.contorno is None:
            return
        for rid, p in nv.pol.items():
            self.inf.revisado('V3')
            if not C.poligono_dentro_de(p, nv.contorno, TOL):
                self.err('V3', f'{nv.id}: {rid} se sale del contorno')
        ids = list(nv.pol)
        cajas = {k: C.caja(v) for k, v in nv.pol.items()}
        for i, r1 in enumerate(ids):
            for r2 in ids[i + 1:]:
                if not C.cajas_se_tocan(cajas[r1], cajas[r2]):
                    continue
                self.inf.revisado('V4')
                a = C.area_interseccion(nv.pol[r1], nv.pol[r2])
                if a >= 0.01:
                    self.err('V4', f'{nv.id}: {r1} y {r2} se traslapan {a:.3f} m²')
        ac = C.area_poligono(nv.contorno)
        au = C.area_union([C.rect_a_poligono(r) for p in nv.pol.values() for r in C.rectangulos(p)]) if nv.pol else 0.0
        self.inf.revisado('V5')
        if ac > 0 and abs(ac - au) / ac > 0.005:
            self.err('V5', f'{nv.id}: la unión de recintos mide {au:.2f} m² y el contorno {ac:.2f} m² '
                           f'(diferencia {100 * abs(ac - au) / ac:.2f} % > 0,5 %)')

    # ------------------------------------------------------------------------------------------------ V7 y V8
    def v7_v8(self, nv: Nivel):
        for r in nv.espacios:
            mn = r.get('minimo_1633')
            rid = r.get('id')
            if not isinstance(mn, dict) or rid not in nv.pol:
                continue
            self.inf.revisado('V7')
            ae = C.area_poligono(nv.pol[rid])
            if num(mn.get('m2')) and ae < mn['m2'] - 0.005:
                self.err('V7', f'{nv.id}: {rid} ({r.get("ambiente")}) mide {ae:.2f} m² a ejes; mínimo {mn["m2"]} m² ({mn.get("cita")})')
            lado = C.ancho_minimo(nv.pol[rid])
            if num(mn.get('lado_m')) and lado < mn['lado_m'] - 0.005:
                self.err('V7', f'{nv.id}: {rid} tiene lado menor de {lado:.2f} m a ejes; mínimo {mn["lado_m"]} m')
            if rid in nv.libre and num(mn.get('m2')):
                self.inf.revisado('V8')
                cols = nv.columnas()
                al = C.area_libre(nv.libre[rid], cols) + sum(C.area_libre(nv.libre_sub[sid], cols) for sid in nv.libre_sub
                                                             if nv.padre(sid) == rid)
                if al < mn['m2'] - 1e-6:
                    self.av('V8', f'{nv.id}: {rid} ({r.get("ambiente")}): {al:.2f} m² libres frente a {mn["m2"]} m² del mínimo; '
                                  'por confirmar si el mínimo de la Res. 1633 se mide libre o a ejes (Anexo 1, definiciones)')

    # ------------------------------------------------------------------------------------------------ V9 y V10
    def _permitido(self, r_dest, r_desde) -> bool:
        for ap in self.reglas.get('accesos_permitidos', []) + self.pl.get('accesos_permitidos', []):
            amb = ap.get('ambiente')
            amb = amb if isinstance(amb, dict) else {'nombre': amb}
            if amb.get('nombre') != r_dest.get('ambiente'):
                continue
            if 'servicio_programa' in amb and amb['servicio_programa'] != r_dest.get('servicio_programa'):
                continue
            if 'fila' in amb and amb['fila'] != r_dest.get('fila'):
                continue
            for d in ap.get('desde', []):
                d = d if isinstance(d, dict) else {'nombre': d}
                if d.get('nombre') == r_desde.get('ambiente') and d.get('servicio_programa', r_desde.get('servicio_programa')) == r_desde.get('servicio_programa'):
                    return True
        return False

    def v9_v10(self, nv: Nivel):
        adyacentes = {rid: set() for rid in nv.por_id}
        for pt in nv.puertas:
            de, ha = pt.get('desde'), pt.get('hacia')
            if de in adyacentes and ha in adyacentes:
                adyacentes[de].add(ha)
                adyacentes[ha].add(de)
        for rid, otros in nv.abiertos.items():
            adyacentes[rid].update(otros)
        for r in nv.espacios:
            if r.get('tipo') not in ('recinto', 'nucleo') or not nv.transitable(r.get('id')):
                continue
            self.inf.revisado('V9')
            ok = False
            for otro in adyacentes.get(r.get('id'), ()):
                o = nv.por_id[otro]
                if nv.es_paso(otro) or self._permitido(r, o):
                    ok = True
                    break
            if not ok:
                self.err('V9', f'{nv.id}: {r.get("id")} ({r.get("ambiente")}) no tiene puerta ni vano a una circulación, '
                               'a un recinto de paso ni a un recinto de accesos_permitidos')
        semillas = set()
        for cv in nv.d.get('conexiones_verticales', []):
            p = (cv.get('puntos') or {}).get(str(nv.d.get('piso')))
            if punto(p) and nv.espacio_en(p):
                semillas.add(nv.espacio_en(p))
        for e in nv.d.get('entradas_recorrido', []):
            if punto(e.get('punto')) and nv.espacio_en(e['punto']):
                semillas.add(nv.espacio_en(e['punto']))
        for pt in nv.puertas:
            if 'exterior' in (pt.get('desde'), pt.get('hacia')):
                semillas.add(pt['hacia'] if pt.get('desde') == 'exterior' else pt.get('desde'))
        for pa in nv.d.get('pasos_entre_niveles', []):
            if pa.get('recinto') in nv.por_id:
                semillas.add(pa['recinto'])
        semillas.discard(None)
        self.inf.revisado('V10')
        if not semillas:
            self.err('V10', f'{nv.id}: sin conexiones verticales, entradas ni puertas a exterior desde donde recorrer')
            return
        vistos, pila = set(semillas), list(semillas)
        while pila:
            x = pila.pop()
            for y in adyacentes.get(x, ()):
                if y not in vistos:
                    vistos.add(y)
                    pila.append(y)
        sueltos = [rid for rid in nv.por_id if rid not in vistos and nv.transitable(rid)]
        if sueltos:
            self.err('V10', f'{nv.id}: recintos que no se alcanzan por puertas: {sueltos}')

    # ------------------------------------------------------------------------------------------------ V11 y V12
    def v11(self, nv: Nivel):
        cols = rects_columnas(nv)
        for pt in nv.puertas:
            m = nv.muros.get(pt.get('muro'))
            if m is None or not punto(pt.get('centro')) or not num(pt.get('ancho')) or not punto(m.get('a')):
                continue
            self.inf.revisado('V11')
            q = f'{nv.id}: {pt.get("id")}: '
            cat = self.cat_puertas.get(pt.get('categoria'))
            if cat is None:
                self.err('V11', f'{q}categoría {pt.get("categoria")!r} sin ancho mínimo (no está en reglas_planta → puertas)')
                req, cita = 0.0, ''
            else:
                req, cita = cat['ancho_m'], cat.get('cita', '')
            for lado in (pt.get('desde'), pt.get('hacia')):
                r = nv.por_id.get(lado)
                if not r or pt.get('desde') in nv.subs or pt.get('hacia') in nv.subs:
                    continue
                for c in self.cat_puertas.values():
                    if r.get('ambiente') in c.get('ambientes', []) and c['ancho_m'] > req:
                        req, cita = c['ancho_m'], f'{c.get("cita", "")} (categoría {c["categoria"]} por {r.get("ambiente")})'
            if pt['ancho'] < req - 1e-6:
                self.err('V11', f'{q}ancho {pt["ancho"]} m < {req} m ({cita})')
            a, b, c = m['a'], m['b'], pt['centro']
            if C.distancia_punto_segmento(c, a, b) > TOL:
                self.err('V11', f'{q}el centro {c} no está sobre su muro {m.get("id")}')
            L = math.dist(a[:2], b[:2])
            if pt['ancho'] > L - 0.10 + 1e-6:
                self.err('V11', f'{q}ancho {pt["ancho"]} m > largo del muro ({L:.2f} m) − 0,10 m')
            if min(math.dist(c[:2], a[:2]), math.dist(c[:2], b[:2])) < pt['ancho'] / 2 - TOL:
                self.err('V11', f'{q}la puerta se sale de su muro')
            if not num(pt.get('alto')) or pt['alto'] < 2.10 - 1e-6:
                self.err('V11', f'{q}alto {pt.get("alto")} m < 2,10 m (Res. 1633, Cuadro 1)')
            # revisión adversarial: una columna de la retícula no puede tapar el vano
            e = 0 if C.es_horizontal(a, b) else 1
            libre, tapan = libre_de_columnas(c[e] - pt['ancho'] / 2, c[e] + pt['ancho'] / 2, a, b, cols)
            if tapan and libre < req - 1e-6:
                self.err('V11', f'{q}la columna {", ".join(map(str, tapan))} tapa el vano: quedan {libre:.2f} m libres '
                                f'< {req} m ({cita})')
        for m in nv.muros.values():
            if m.get('tipo') != 'abierto' or not punto(m.get('a')) or not punto(m.get('b')):
                continue
            a, b = m['a'], m['b']
            e = 0 if C.es_horizontal(a, b) else 1
            lo, hi = sorted((a[e], b[e]))
            libre, tapan = libre_de_columnas(lo, hi, a, b, cols)
            if tapan and libre < 0.90 - 1e-6:
                self.err('V11', f'{nv.id}: vano abierto {m.get("id")} {m.get("lados")}: la columna {", ".join(map(str, tapan))} '
                                f'deja {libre:.2f} m libres (< 0,90 m, paso de una silla de ruedas)')

    def _barridos(self, nv: Nivel):
        salida = []
        for pt in nv.puertas:
            if pt.get('espejo_de'):
                continue
            m = nv.muros.get(pt.get('muro'))
            if m is None or not punto(pt.get('centro')) or not num(pt.get('ancho')) or not punto(m.get('a')):
                continue
            for h in C.hojas_puerta(pt, m, {**nv.pol, **nv.pol_sub}):
                pts = [x for x in C.sector(h['bisagra'], h['radio'], h['ang0'], h['ang1'])
                       if C.distancia_punto_segmento(x, m['a'], m['b']) > m.get('espesor', 0) / 2 + 0.005]
                salida.append((pt, m, h, pts))
        return salida

    def v12(self, nv: Nivel):
        barridos = self._barridos(nv)
        cols = rects_columnas(nv)
        for pt, m, h, pts in barridos:
            self.inf.revisado('V12')
            choca = sorted({q[4] for q in cols for x in pts if q[0] + 0.005 < x[0] < q[2] - 0.005 and q[1] + 0.005 < x[1] < q[3] - 0.005})
            if choca:
                self.err('V12', f'{nv.id}: {pt.get("id")}: el barrido de la hoja choca con la columna {", ".join(map(str, choca))}')
            lado = h['lado']
            libres = nv.libre_sub if lado in nv.libre_sub else nv.libre
            if lado == 'exterior' or lado not in libres:
                continue
            fuera = [x for x in pts if not C.punto_en_poligono(x, libres[lado], 0.01)]
            if fuera:
                self.err('V12', f'{nv.id}: {pt.get("id")}: el barrido de la hoja (bisagra en {C.redondear_todo(list(h["bisagra"]), 2)}) '
                                f'cruza un muro de {lado}')
        for i, (p1, m1, h1, pts1) in enumerate(barridos):
            for p2, m2, h2, pts2 in barridos[i + 1:]:
                if p1 is p2:
                    continue
                if math.dist(h1['bisagra'], h2['bisagra']) > h1['radio'] + h2['radio']:
                    continue
                if any(C.en_sector(x, h2['bisagra'], h2['radio'], h2['ang0'], h2['ang1'], 0.01) for x in pts1):
                    self.err('V12', f'{nv.id}: los barridos de {p1.get("id")} y {p2.get("id")} se cruzan')

    # ------------------------------------------------------------------------------------------------ V13 y V14
    def v13(self, nv: Nivel):
        cor = self.reglas['corredores']
        cols = rects_columnas(nv)
        for r in nv.espacios:
            if r.get('tipo') != 'circulacion' or r.get('id') not in nv.libre:
                continue
            self.inf.revisado('V13')
            w = C.ancho_minimo(nv.libre[r['id']], C.MUESCA_IGNORADA_M)
            q = f'{nv.id}: {r["id"]} ({r.get("ambiente")}): '
            if num(r.get('ancho_libre_m')) and abs(r['ancho_libre_m'] - w) > 0.01:
                self.err('V13', f'{q}ancho_libre_m = {r["ancho_libre_m"]} y el polígono libre da {w:.3f} m')
            if r.get('evacuacion') and w < cor['evacuacion_min_m'] - 0.005:
                self.err('V13', f'{q}{w:.2f} m libres < {cor["evacuacion_min_m"]} m (corredor de evacuación; Res. 1633, '
                                'num. 3.3.6 b.1; NSR-10 K.3.14.2.2)')
            if r.get('camillas') and w < cor['camillas_recomendado_m'] - 0.005:
                self.av('V13', f'{q}{w:.2f} m libres < {cor["camillas_recomendado_m"]} m recomendados donde pasan camillas')
            if not r.get('evacuacion') and w < cor['interno_min_m'] - 0.005:
                self.av('V13', f'{q}{w:.2f} m libres < {cor["interno_min_m"]} m de un pasillo interno')
            # revisión adversarial: el ancho libre en la sección de cada columna que invade el corredor
            if r.get('evacuacion') and cols:
                wc, col = C.ancho_en_columnas(nv.libre[r['id']], cols)
                if col is not None and wc < cor['evacuacion_min_m'] - 0.005:
                    self.av('V13', f'{q}{wc:.2f} m libres en la sección de la columna {col[4]} (entre caras de muro '
                                   f'{w:.2f} m) < {cor["evacuacion_min_m"]} m; ver reglas_planta → decisiones (columnas)')

    def v14(self, nv: Nivel):
        ev = self.reglas['evacuacion']
        if nv.contorno is None or not nv.libre:
            return
        protegidas = {nu.get('recinto') for nu in nv.d.get('nucleos', []) if nu.get('tipo') == 'escalera'}
        x0, y0, x1, y1 = C.caja(nv.contorno)
        rej = C.Rejilla(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, 0.10)
        for rid, p in nv.libre.items():
            if rid not in protegidas and nv.transitable(rid):
                rej.pintar_poligono(p)
        for sid, p in nv.libre_sub.items():
            if nv.transitable(nv.padre(sid)):
                rej.pintar_poligono(p)
        salidas, vanos = [], {}
        for pt in nv.puertas:
            m = nv.muros.get(pt.get('muro'))
            if m is None or not punto(pt.get('centro')) or not num(pt.get('ancho')) or not punto(m.get('a')):
                continue
            r = C.vano_puerta(pt, m)
            vanos[pt.get('id')] = r
            lados = (pt.get('desde'), pt.get('hacia'))
            if any(l in protegidas for l in lados) or 'exterior' in lados:
                salidas.append(r)
            else:
                rej.pintar_rect(*r)
        self.inf.revisado('V14')
        if not salidas:
            self.err('V14', f'{nv.id}: sin puerta a una escalera protegida ni al exterior')
            return
        semillas = []
        for r in salidas:
            rej.pintar_rect(*r)
            for j in rej._rango(r[1], r[3], rej.y0, rej.ny):
                for i in rej._rango(r[0], r[2], rej.x0, rej.nx):
                    semillas.append((i, j))
        dist = rej.distancias(semillas)

        def en(r):
            vals = [dist[j * rej.nx + i] for j in rej._rango(r[1], r[3], rej.y0, rej.ny)
                    for i in rej._rango(r[0], r[2], rej.x0, rej.nx)]
            return min(vals) if vals else math.inf

        # Las puertas de cabina de ascensor, de montacargas y de ductos no son puertas de salida de un recinto
        # ocupado: el recorrido se mide desde las puertas de los recintos (K.3.14.1.2); sus celdas igual cuentan abajo.
        huecos = set()
        for nu in nv.d.get('nucleos', []):
            if isinstance(nu, dict) and nu.get('tipo') in ('ascensor', 'montacargas', 'ductos'):
                huecos.update(nu.get('recintos') or [nu.get('recinto')])
        for pt in nv.puertas:
            pid = pt.get('id')
            if pid not in vanos or pt.get('desde') in huecos or pt.get('hacia') in huecos:
                continue
            for lado in (pt.get('desde'), pt.get('hacia')):
                r = nv.por_id.get(lado)
                if not r or r.get('tipo') == 'circulacion' or lado in protegidas or not nv.transitable(lado):
                    continue
                d = en(vanos[pid])
                if d > ev['puerta_a_escalera_max_m'] + 1e-6:
                    txt = 'no tiene camino' if math.isinf(d) else f'queda a {d:.1f} m'
                    self.err('V14', f'{nv.id}: la puerta {pid} de {lado} {txt} de la salida protegida más cercana '
                                    f'(máximo {ev["puerta_a_escalera_max_m"]} m; NSR-10 K.3.14.1.2)')
        libres = [k for k in range(len(rej.libre)) if rej.libre[k]]
        sin_camino = [k for k in libres if math.isinf(dist[k])]
        if sin_camino:
            i, j = sin_camino[0] % rej.nx, sin_camino[0] // rej.nx
            self.err('V14', f'{nv.id}: {len(sin_camino)} celdas de 0,10 m sin camino a una salida (por ejemplo en '
                            f'{C.redondear_todo(list(rej.centro(i, j)), 2)})')
        alcanzadas = [dist[k] for k in libres if not math.isinf(dist[k])]
        if alcanzadas:
            peor = max(alcanzadas)
            if peor > ev['cualquier_punto_max_m'] + 1e-6:
                k = next(k for k in libres if dist[k] == peor)
                self.err('V14', f'{nv.id}: hay puntos a {peor:.1f} m de una salida protegida (máximo '
                                f'{ev["cualquier_punto_max_m"]} m; NSR-10 Tabla K.3.6-1), por ejemplo '
                                f'{C.redondear_todo(list(rej.centro(k % rej.nx, k // rej.nx)), 2)}')

    # ------------------------------------------------------------------------------------------------ V17 a V19
    def v17(self, nv: Nivel):
        zonas = (self.pl.get('zonas') if self.fixture else self.reglas.get('zonas')) or {}
        zonas = zonas.get(nv.id, [])
        if not zonas:
            return
        for r in nv.espacios:
            sp = r.get('servicio_programa')
            mias = [z for z in zonas if z.get('servicio_programa') == sp]
            if not mias or r.get('id') not in nv.pol:
                continue
            self.inf.revisado('V17')
            cx, cy = C.centroide(nv.pol[r['id']])
            if not any(z['x'][0] - TOL <= cx <= z['x'][1] + TOL and z['y'][0] - TOL <= cy <= z['y'][1] + TOL for z in mias):
                self.av('V17', f'{nv.id}: {r["id"]} ({r.get("ambiente")}): el centroide ({cx:.2f}; {cy:.2f}) queda fuera de '
                               f'la zona de «{sp}»')

    def v18(self, nv: Nivel):
        validos = nv.muros_validos()
        for r in nv.espacios:
            if not RE_PLOMADO.search(str(r.get('ambiente', ''))) or r.get('id') not in nv.pol:
                continue
            self.inf.revisado('V18')
            for s0, s1 in C.bordes(nv.pol[r['id']]):
                tramo = [m for m in validos if C.solape_colineal(s0, s1, m['a'], m['b'])]
                # un muro estructural de concreto (0,35 m) blinda más que la lámina de ≈ 2 mm de plomo (prediseño DMO;
                # cálculo de blindaje pendiente, Res. 1811 de 2025)
                malos = [m['id'] for m in tramo if m.get('tipo') != 'plomado' and not (m.get('tipo') == 'nucleo' and m.get('estructural'))]
                if malos:
                    self.err('V18', f'{nv.id}: {r["id"]} ({r.get("ambiente")}): muros sin plomo {malos}')
                if C.largo_cubierto(s0, s1, [(m['a'], m['b']) for m in tramo]) < math.dist(s0, s1) - TOL:
                    self.err('V18', f'{nv.id}: {r["id"]}: el borde {s0} → {s1} no está cubierto por muros plomados')

    def v19(self, nv: Nivel):
        for r in nv.espacios:
            if r.get('tipo') != 'recinto':
                continue
            if not RE_VENTANA_EXIGIDA.search(str(r.get('ambiente', ''))) or r.get('id') not in nv.pol:
                continue
            self.inf.revisado('V19')
            tiene = False
            for v in nv.ventanas:
                m = nv.muros.get(v.get('muro'))
                if m and punto(v.get('centro')) and C.distancia_a_borde(v['centro'], nv.pol[r['id']]) <= TOL:
                    tiene = True
                    break
            if not tiene:
                self.av('V19', f'{nv.id}: {r["id"]} ({r.get("ambiente")}) sin ventana a fachada o patio (Res. 1633, '
                               'iluminación y ventilación natural; numeral por confirmar)')

    # ------------------------------------------------------------------------------------------------ reglas con programa
    def ambientes(self):
        return (self.programa or {}).get('ambientes', [])

    def nivel_de_fila(self, f):
        """Nivel de la planta donde va la fila f (reglas_planta.json → niveles; 16.1)."""
        niv = self.reglas.get('niveles') or {}
        por_fila = niv.get('nivel_por_fila') or {}
        if str(f) in por_fila:
            return por_fila[str(f)]
        piso = self.ambientes()[f].get('piso')
        if isinstance(piso, int):
            return f'P{piso}'
        return (niv.get('piso_a_nivel') or {}).get(str(piso))

    def v2_v6(self, niveles: list[Nivel]):
        amb = self.ambientes()
        cuenta = {}
        for nv in niveles:
            for r in nv.espacios:
                f = r.get('fila')
                if not isinstance(f, int) or isinstance(f, bool):
                    continue
                cuenta[f] = cuenta.get(f, 0) + 1
                q = f'{nv.id}: {r.get("id")}: '
                self.inf.revisado('V2')
                if not 0 <= f < len(amb):
                    self.err('V2', f'{q}la fila {f} no existe en programa.json')
                    continue
                a = amb[f]
                if a.get('nombre') != r.get('ambiente'):
                    self.err('V2', f'{q}ambiente «{r.get("ambiente")}» y la fila {f} es «{a.get("nombre")}» (¿se reordenó programa.json?)')
                if self.nivel_de_fila(f) != nv.id:
                    self.err('V2', f'{q}la fila {f} es del piso {a.get("piso")!r} (nivel {self.nivel_de_fila(f)}), no de {nv.id}')
                if a.get('servicio') != r.get('servicio_programa'):
                    self.err('V2', f'{q}servicio «{r.get("servicio_programa")}» y la fila {f} es de «{a.get("servicio")}»')
                if r.get('de') != a.get('cantidad'):
                    self.err('V2', f'{q}de = {r.get("de")} y la fila {f} tiene cantidad {a.get("cantidad")}')
                # V6
                self.inf.revisado('V6')
                m2 = a.get('m2_unitario')
                if num(m2):
                    if num(r.get('area_programa_m2')) and abs(r['area_programa_m2'] - m2) > 1e-6:
                        self.err('V6', f'{q}area_programa_m2 = {r["area_programa_m2"]} y el programa dice {m2}')
                    ae = C.area_poligono(nv.pol[r['id']]) if r.get('id') in nv.pol else 0.0
                    if ae < m2 - 0.05 - 1e-9:
                        self.err('V6', f'{q}{ae:.2f} m² a ejes < {m2} m² del programa − 0,05')
        presentes = {nv.id for nv in niveles}
        for f, a in enumerate(amb):
            if self.nivel_de_fila(f) is None:
                continue
            if self.nivel_de_fila(f) not in presentes:
                self.err('V2', f'fila {f} («{a.get("nombre")}»): su nivel {self.nivel_de_fila(f)} no está en la planta')
                continue
            if cuenta.get(f, 0) != a.get('cantidad'):
                self.err('V2', f'fila {f} («{a.get("nombre")}», piso {a.get("piso")}): {cuenta.get(f, 0)} recintos y la '
                               f'cantidad es {a.get("cantidad")}')
        esperado = {}
        for f, a in enumerate(amb):
            k = self.nivel_de_fila(f)
            if k:
                esperado[k] = esperado.get(k, 0) + a.get('cantidad', 0)
        obtenido = {nv.id: sum(1 for r in nv.espacios if isinstance(r.get('fila'), int)) for nv in niveles}
        for k, v in sorted(esperado.items()):
            if obtenido.get(k, 0) != v:
                self.err('V2', f'{k}: {obtenido.get(k, 0)} recintos del programa y se esperan {v}')

    def v15(self, niveles: list[Nivel]):
        nucleos = ((self.programa or {}).get('implantacion') or {}).get('nucleos_verticales') or {}
        rects = {}
        for clave, tipo in (('escalera_norte', 'escalera'), ('escalera_sur', 'escalera'), ('ascensores', 'ascensor')):
            lim = (nucleos.get(clave) or {}).get('limites')
            if lim:
                rects[clave] = (tipo, C.rect_a_poligono([lim['x'][0], lim['y'][0], lim['x'][1], lim['y'][1]]))
        if not rects:
            self.err('V15', 'programa.json no trae implantacion.nucleos_verticales con límites')
            return
        for nv in niveles:
            if nv.id not in NIVELES_PISO and nv.id != 'CUB':
                continue
            pols = [(nu.get('tipo'), nu.get('poligono')) for nu in nv.d.get('nucleos', []) if poligono_valido(nu.get('poligono'))]
            for clave, (tipo, r) in rects.items():
                if nv.id == 'CUB' and not any(t == tipo for t, _ in pols):
                    continue
                self.inf.revisado('V15')
                ok = any(t == tipo and abs(C.area_poligono(p) - C.area_poligono(r)) < 0.01
                         and C.area_interseccion(p, r) > C.area_poligono(r) - 0.01 for t, p in pols)
                if not ok:
                    self.err('V15', f'{nv.id}: falta el núcleo «{clave}» ({tipo}) exacto: {r}')
            for cv in nv.d.get('conexiones_verticales', []):
                if cv.get('tipo') not in ('escalera', 'ascensor', 'montacargas'):
                    continue
                p = (cv.get('puntos') or {}).get(str(nv.d.get('piso')))
                if not punto(p):
                    continue
                if not any(C.punto_en_poligono(p, q, 0.0) for t, q in pols):
                    self.err('V15', f'{nv.id}: el punto de la conexión {cv.get("id")} ({cv.get("tipo")}) no está dentro de un núcleo')

    def v16(self, niveles: list[Nivel]):
        ret = self.pl.get('reticula') or {}
        xs = [e['x'] for e in ret.get('ejes_x', []) if num(e.get('x'))]
        ys = [e['y'] for e in ret.get('ejes_y', []) if num(e.get('y'))]
        for nv in niveles:
            if nv.id not in NIVELES_PISO or nv.contorno is None:
                continue
            ojos = [e['ojo'] for e in nv.d.get('escaleras', []) if isinstance(e, dict) and isinstance(e.get('ojo'), list)]
            esperadas = [(x, y) for x in xs for y in ys if C.punto_en_poligono((x, y), nv.contorno, TOL)]
            cols = [c for c in nv.d.get('columnas', []) if isinstance(c, dict) and num(c.get('x')) and num(c.get('y'))]
            self.inf.revisado('V16')
            for x, y in esperadas:
                if not any(abs(c['x'] - x) <= 0.01 and abs(c['y'] - y) <= 0.01 for c in cols):
                    self.err('V16', f'{nv.id}: falta la columna en ({x}; {y})')
            if len(cols) != len(esperadas):
                self.err('V16', f'{nv.id}: {len(cols)} columnas y hay {len(esperadas)} intersecciones de ejes dentro del contorno')
            muros = nv.muros_validos()
            for c in cols:
                pt = (c['x'], c['y'])
                if any(C.distancia_punto_segmento(pt, m['a'], m['b']) <= max(m.get('espesor', 0) / 2, 0.30) + TOL for m in muros):
                    continue
                if C.distancia_a_borde(pt, nv.contorno) <= 0.30 + TOL:
                    continue
                if any(nv.por_id[rid].get('tipo') == 'circulacion' and C.distancia_a_borde(pt, p) <= 0.30 + TOL
                       for rid, p in nv.pol.items()):
                    continue
                if any(o[0] + 0.3 - TOL <= pt[0] <= o[2] - 0.3 + TOL and o[1] + 0.3 - TOL <= pt[1] <= o[3] - 0.3 + TOL
                       for o in ojos):
                    continue          # en el ojo de una escalera abierta: la columna sube entre los dos tramos
                donde = nv.espacio_en(pt)
                amb = nv.por_id.get(donde, {}).get('ambiente', '')
                if not COLUMNA_LIBRE_PERMITIDA.search(amb):
                    self.err('V16', f'{nv.id}: la columna {c.get("id")} queda suelta dentro de {donde} ({amb})')

    def v20(self, niveles: list[Nivel]):
        resumen = {f'P{r["piso"]}': r for r in (self.programa or {}).get('resumen_por_piso', []) if isinstance(r.get('piso'), int)}
        for nv in niveles:
            if nv.id not in resumen:
                continue
            self.inf.revisado('V20')
            servicios = set(resumen[nv.id].get('m2_util_por_servicio') or {})
            util = sum(C.area_poligono(nv.pol[r['id']]) for r in nv.espacios
                       if isinstance(r.get('fila'), int) and r.get('id') in nv.pol
                       and (not servicios or r.get('servicio_programa') in servicios))
            meta = resumen[nv.id].get('m2_util', 0)
            if util < meta - 1e-6:
                self.err('V20', f'{nv.id}: {util:.1f} m² útiles a ejes < {meta} m² útiles del programa')

    # ------------------------------------------------------------------------------------------------ V21
    def v21(self, niveles: list[Nivel]):
        """Escaleras caminables (16.1): partes dentro del recinto, cotas continuas y la misma escalera en el nivel de
        llegada. Contrahuella entre 0,10 y 0,18 m y huella ≥ 0,28 m: valores usuales de diseño (numeral de la NSR-10 por
        confirmar), no se cita norma."""
        por_id = {nv.id: nv for nv in niveles}
        for nv in niveles:
            for es in nv.d.get('escaleras', []):
                q = f'{nv.id}: escalera {es.get("id")}: '
                self.inf.revisado('V21')
                rid = es.get('recinto')
                if rid not in nv.pol:
                    self.err('V21', f'{q}el recinto {rid!r} no existe')
                    continue
                partes = es.get('partes') or []
                if not partes or partes[0].get('tipo') != 'descanso_piso' or partes[0].get('z') != 0:
                    self.err('V21', f'{q}debe empezar en un descanso de piso a cota 0')
                z = 0.0
                for pa in partes:
                    r = pa.get('rect')
                    if not (isinstance(r, list) and len(r) == 4 and all(num(v) for v in r) and r[2] > r[0] and r[3] > r[1]):
                        self.err('V21', f'{q}parte sin rectángulo válido: {pa}')
                        continue
                    if not C.poligono_dentro_de(C.rect_a_poligono(r), nv.pol[rid], 0.01):
                        self.err('V21', f'{q}la parte {pa.get("tipo")} {r} se sale del recinto {rid}')
                    if pa.get('tipo') == 'tramo':
                        z0, z1, n_, ch = pa.get('z0'), pa.get('z1'), pa.get('contrahuellas'), pa.get('contrahuella_m')
                        if not (num(z0) and num(z1) and isinstance(n_, int) and num(ch)) or z1 <= z0:
                            self.err('V21', f'{q}tramo sin cotas o contrahuellas válidas')
                            continue
                        if abs(z0 - z) > 0.002:
                            self.err('V21', f'{q}el tramo empieza en {z0} m y la parte anterior queda en {z} m')
                        if abs((z1 - z0) / n_ - ch) > 0.002:
                            self.err('V21', f'{q}contrahuella {ch} m y el tramo sube {z1 - z0:.3f} m en {n_} contrahuellas')
                        if not 0.10 <= ch <= 0.18 or not num(pa.get('huella_m')) or pa['huella_m'] < 0.28 - 1e-9:
                            self.err('V21', f'{q}contrahuella {ch} m o huella {pa.get("huella_m")} m fuera de lo usual (0,10-0,18 y ≥ 0,28)')
                        z = z1
                    elif num(pa.get('z')):
                        if abs(pa['z'] - z) > 0.002:
                            self.err('V21', f'{q}el descanso está a {pa["z"]} m y el tramo anterior llega a {z} m')
                        z = pa['z']
                destino = es.get('sube_a')
                if destino:
                    otro = por_id.get(destino)
                    if otro is None:
                        self.err('V21', f'{q}sube a {destino}, que no está en la planta')
                        continue
                    h = otro.d.get('z', 0) - nv.d.get('z', 0)
                    if abs(z - h) > 0.002:
                        self.err('V21', f'{q}llega a {z} m y el nivel {destino} está {h:.3f} m más arriba')
                    llegada = [e for e in otro.d.get('escaleras', []) if e.get('id') == es.get('id')]
                    if not llegada:
                        self.err('V21', f'{q}el nivel {destino} no tiene la escalera {es.get("id")}')
                    elif llegada[0]['partes'][0].get('rect') != partes[0].get('rect'):
                        self.err('V21', f'{q}el descanso de llegada en {destino} no coincide con el de salida')

    # ------------------------------------------------------------------------------------------------ V22
    def v22(self, niveles: list[Nivel]):
        """Paso físico (revisión adversarial): el grafo de puertas de V10 no ve muros, columnas ni vanos tapados."""
        camillas = {c for c in ('camas', 'camillas_procedimientos') if c in self.cat_puertas}
        for nv in niveles:
            if not nv.espacios or nv.contorno is None and not nv.d.get('recintos'):
                continue
            self.inf.revisado('V22')
            # en los exteriores, cada paso a otro nivel necesita su vano (puerta espejo) en el muro del nivel
            if nv.id == 'EXT':
                for pa in nv.d.get('pasos_entre_niveles', []):
                    if not pa.get('puerta'):
                        self.err('V22', f'{nv.id}: el paso a {pa.get("otro_nivel")} en {pa.get("punto")} no tiene vano en el muro')
            sem = C.semillas_de_paso(nv.d)
            if not sem:
                continue
            r = C.alcance_fisico(nv.d, 0.30, sem)
            for nombre in r['sin_lugar']:
                self.err('V22', f'{nv.id}: {nombre}: no hay dónde pararse a menos de 0,60 m (radio 0,30 m)')
            for z, grupos in sorted(r['por_cota'].items()):
                if len(grupos) > 1:
                    self.err('V22', f'{nv.id}: a la cota {z:+.2f} m hay {len(grupos)} zonas sin paso entre sí: '
                                    + ' | '.join(', '.join(g) for g in grupos))
            for rid in r['no_alcanzables']:
                amb = (nv.por_id.get(rid) or {}).get('ambiente') or (nv.subs[rid][0].get('nombre') if rid in nv.subs else '') or ''
                if amb.startswith('Montacargas'):
                    continue              # cabina de carga: no la usa una persona
                self.err('V22', f'{nv.id}: {rid} ({amb}): ningún punto alcanzable con radio 0,30 m')
            con_camilla = {x for pt in nv.puertas if pt.get('categoria') in camillas and not pt.get('espejo_de')
                           for x in (pt.get('desde'), pt.get('hacia')) if x in nv.por_id}
            if con_camilla:
                r2 = C.alcance_fisico(nv.d, 0.45, sem, recintos=con_camilla)
                for rid in r2['no_alcanzables']:
                    self.err('V22', f'{nv.id}: {rid} ({(nv.por_id.get(rid) or {}).get("ambiente")}): una camilla '
                                    '(radio 0,45 m) no llega por su puerta de camas o camillas')

    # ------------------------------------------------------------------------------------------------ V23
    def v23(self, niveles: list[Nivel]):
        """Prediseño DMO (17.1): la planta usa las dimensiones de data/sismo/torre_hospital_estructura.json (equipo A):
        columnas por eje y piso, muros estructurales solo y completos sobre los paños del prediseño (sin vanos), cielo
        raso bajo las vigas y fosos y cisternas de la cimentación."""
        est = self.estructura
        if not isinstance(est, dict):
            self.inf.omitir('V23', 'no se pudo leer data/sismo/torre_hospital_estructura.json (prediseño del equipo A)')
            return
        S = est.get('secciones') or {}
        col_sec, muro_esp, vigas = {}, {}, {}
        for b in est.get('bloques') or []:
            for po in b.get('porticos') or []:
                for e in po.get('elementos') or []:
                    sec = S.get(e.get('seccion')) or {}
                    if e.get('tipo') == 'columna':
                        col_sec[(str(e.get('eje')), e.get('nivel'))] = (sec.get('b'), sec.get('h'))
                    elif e.get('tipo') == 'muro_concreto':
                        muro_esp[po.get('id')] = sec.get('b')
                    elif e.get('tipo') == 'viga' and num(sec.get('h')):
                        vigas.setdefault(e.get('nivel'), []).append(float(sec['h']))
        paneles = [p for p in ((est.get('prediseno') or {}).get('eleccion_muros') or {}).get('paneles_de_nucleo', [])
                   if p.get('material') == 'concreto']
        niveles_est = {nv.d.get('piso') for nv in niveles if nv.id in NIVELES_PISO}
        for nv in niveles:
            piso = nv.d.get('piso')
            muros = nv.muros_validos()
            nucleo = [m for m in muros if m.get('tipo') == 'nucleo']
            if nv.id not in NIVELES_PISO:
                for m in nucleo:
                    self.err('V23', f'{nv.id}: {m.get("id")} es muro estructural y el prediseño no tiene muros en este nivel')
                continue
            self.inf.revisado('V23')
            # columnas
            vistas = set()
            for c in nv.columnas():
                cid = str(c.get('id'))
                clave = (f'{cid[0]}-{cid[1:]}', piso)
                vistas.add(clave)
                bh = col_sec.get(clave)
                if bh is None:
                    self.err('V23', f'{nv.id}: la columna {cid} no está en el prediseño (eje {clave[0]}, piso {piso})')
                elif not (num(c.get('b')) and num(c.get('h')) and abs(c['b'] - bh[0]) <= 1e-6 and abs(c['h'] - bh[1]) <= 1e-6):
                    self.err('V23', f'{nv.id}: la columna {cid} mide {c.get("b")} × {c.get("h")} m y el prediseño dice '
                                    f'{bh[0]} × {bh[1]} m')
            for clave in col_sec:
                if clave[1] == piso and clave not in vistas:
                    self.err('V23', f'{nv.id}: falta la columna del eje {clave[0]} del prediseño')
            # muros estructurales: solo y completos sobre los paños del prediseño, con su espesor
            for m in nucleo:
                pan = [pn for pn in paneles if C.distancia_punto_segmento(m['a'], pn['tramo'][:2], pn['tramo'][2:]) <= 1e-6
                       and C.distancia_punto_segmento(m['b'], pn['tramo'][:2], pn['tramo'][2:]) <= 1e-6]
                if not pan:
                    self.err('V23', f'{nv.id}: {m.get("id")} ({m["a"]} → {m["b"]}) es muro estructural y no está sobre un paño '
                                    'de concreto del prediseño')
                    continue
                esp = muro_esp.get(pan[0].get('muro'))
                if not num(esp) or abs(m.get('espesor', -1) - esp) > 1e-6 or m.get('estructural') is not True:
                    self.err('V23', f'{nv.id}: {m.get("id")} mide {m.get("espesor")} m y el muro {pan[0].get("muro")} del '
                                    f'prediseño {esp} m (o no está marcado estructural)')
            for pn in paneles:
                a, b = pn['tramo'][:2], pn['tramo'][2:]
                cub = C.largo_cubierto(a, b, [(m['a'], m['b']) for m in nucleo])
                if cub < math.dist(a, b) - TOL:
                    self.err('V23', f'{nv.id}: el paño {pn.get("nombre")} del muro {pn.get("muro")} ({a} → {b}) no es muro '
                                    f'estructural en toda su longitud ({cub:.2f} de {math.dist(a, b):.2f} m)')
            for pt in nv.puertas:
                m = nv.muros.get(pt.get('muro'))
                if m is None or not punto(pt.get('centro')) or not num(pt.get('ancho')) or not punto(m.get('a')):
                    continue
                if m.get('tipo') == 'nucleo':
                    self.err('V23', f'{nv.id}: la puerta {pt.get("id")} perfora el muro estructural {m.get("id")}')
                    continue
                hz = C.es_horizontal(m['a'], m['b'])
                e, f = (0, 1) if hz else (1, 0)
                lo = pt['centro'][e] - pt['ancho'] / 2 - MARCO_PUERTA_M
                hi = pt['centro'][e] + pt['ancho'] / 2 + MARCO_PUERTA_M
                for w in nucleo:
                    if C.es_horizontal(w['a'], w['b']) != hz or abs(w['a'][f] - pt['centro'][f]) > 1e-6:
                        continue
                    w0, w1 = sorted((w['a'][e], w['b'][e]))
                    if min(hi, w1) - max(lo, w0) > 1e-6:
                        self.err('V23', f'{nv.id}: el vano de la puerta {pt.get("id")} (hoja y marco de 5 cm) se mete en el '
                                        f'muro estructural {w.get("id")}')
            for v in nv.ventanas:
                m = nv.muros.get(v.get('muro'))
                if m is not None and m.get('tipo') == 'nucleo':
                    self.err('V23', f'{nv.id}: la ventana {v.get("id")} queda en el muro estructural {m.get("id")}')
            # alturas: el cielo raso cabe bajo la viga más alta del piso
            hs = vigas.get(piso) or []
            ed = nv.d.get('estructura') or {}
            H = nv.d.get('altura_entrepiso_m')
            if not hs or not num(H):
                self.err('V23', f'{nv.id}: sin vigas del prediseño en el piso {piso} o sin altura de entrepiso')
            else:
                bajo_min = H - max(hs)
                if not num(ed.get('altura_libre_bajo_viga_min_m')) or abs(ed['altura_libre_bajo_viga_min_m'] - bajo_min) > 0.005:
                    self.err('V23', f'{nv.id}: altura libre bajo la viga más alta {ed.get("altura_libre_bajo_viga_min_m")} m; '
                                    f'con el prediseño es {bajo_min:.2f} m')
                if num(nv.d.get('altura_libre_m')) and nv.d['altura_libre_m'] > bajo_min + 1e-6:
                    self.err('V23', f'{nv.id}: el cielo raso ({nv.d["altura_libre_m"]} m) queda por encima de las vigas '
                                    f'({bajo_min:.2f} m libres)')
        if not niveles_est:
            self.err('V23', 'la planta no tiene los pisos 1 a 4 del prediseño')
        # fosos y cisternas de la cimentación
        cim = est.get('cimentacion') or {}
        br = {b.get('id'): (nv, b) for nv in niveles for b in nv.d.get('bajo_rasante', []) or [] if isinstance(b, dict)}
        for f in cim.get('fosos', []) or []:
            nb = br.get(f.get('id'))
            if nb is None:
                self.err('V23', f'falta el foso {f.get("id")} de la cimentación en la planta (bajo_rasante)')
                continue
            nv, b = nb
            q = C.rect_a_poligono([f['x'][0], f['y'][0], f['x'][1], f['y'][1]])
            if not poligono_valido(b.get('poligono')) or abs(C.area_interseccion(q, b['poligono']) - C.area_poligono(q)) > 1e-3 \
                    or abs(C.area_poligono(b['poligono']) - C.area_poligono(q)) > 1e-3:
                self.err('V23', f'{nv.id}: el foso {f.get("id")} no tiene la huella de la cimentación')
            for k in ('profundidad_m',):
                if not num(b.get(k)) or abs(b[k] - f.get(k, -1)) > 1e-6:
                    self.err('V23', f'{nv.id}: el foso {f.get("id")} tiene {k} = {b.get(k)} y la cimentación {f.get(k)}')
            if not num(b.get('z_fondo_m')) or abs(b['z_fondo_m'] - f.get('z_fondo', -99)) > 1e-6:
                self.err('V23', f'{nv.id}: el foso {f.get("id")} tiene el fondo en {b.get("z_fondo_m")} y la cimentación en '
                                f'{f.get("z_fondo")}')
            nus = [nu for nu in nv.d.get('nucleos', []) if nu.get('id') == b.get('nucleo')]
            if not nus or not C.poligono_dentro_de(q, nus[0].get('poligono'), 1e-3):
                self.err('V23', f'{nv.id}: el foso {f.get("id")} no queda bajo su núcleo {b.get("nucleo")}')
        for c in cim.get('cisternas', []) or []:
            nb = br.get(c.get('id'))
            if nb is None:
                self.err('V23', f'falta la cisterna {c.get("id")} de la cimentación en la planta (bajo_rasante)')
                continue
            nv, b = nb
            q = C.rect_a_poligono([c['x'][0], c['y'][0], c['x'][1], c['y'][1]])
            if not poligono_valido(b.get('poligono')) or abs(C.area_interseccion(q, b['poligono']) - C.area_poligono(q)) > 1e-3 \
                    or abs(C.area_poligono(b['poligono']) - C.area_poligono(q)) > 1e-3:
                self.err('V23', f'{nv.id}: la cisterna {c.get("id")} no tiene la huella de la cimentación')
            prof = c.get('h_interior_m', 0) + c.get('losa_fondo_e_m', 0) + c.get('losa_tapa_e_m', 0)
            if not num(b.get('profundidad_m')) or abs(b['profundidad_m'] - prof) > 0.005:
                self.err('V23', f'{nv.id}: la cisterna {c.get("id")} tiene {b.get("profundidad_m")} m de profundidad y la '
                                f'cimentación {prof:.3f} m')
            sobre = [nv.pol.get(k.get('recinto')) for k in b.get('compartimientos', []) or []]
            if not sobre or any(x is None for x in sobre) or \
                    abs(sum(C.area_interseccion(q, x) for x in sobre) - C.area_poligono(q)) > 1e-3:
                self.err('V23', f'{nv.id}: la cisterna {c.get("id")} no queda bajo los recintos de sus compartimientos')

    # ------------------------------------------------------------------------------------------------ todo
    def correr(self):
        self.v1_general()
        niveles = [Nivel(n) for n in self.pl.get('niveles') or [] if isinstance(n, dict)]
        for nv in niveles:
            self.v1_nivel(nv)
        self.v1_conexiones(niveles)
        for nv in niveles:
            self.v3_v4_v5(nv)
            self.v7_v8(nv)
            self.v9_v10(nv)
            self.v11(nv)
            self.v12(nv)
            self.v13(nv)
            if nv.id not in NIVELES_EXTERIORES:
                self.v14(nv)
            self.v17(nv)
            self.v18(nv)
            self.v19(nv)
        if self.fixture:
            for k in SOLO_PROGRAMA:
                self.inf.omitir(k, 'fixture: depende de programa.json y de la retícula real (3.5)')
        elif self.programa is None:
            for k in SOLO_PROGRAMA:
                self.inf.error(k, 'no se pudo leer programa.json')
        else:
            self.v2_v6(niveles)
            self.v15(niveles)
            self.v16(niveles)
            self.v20(niveles)
            self.v23(niveles)
        self.v21(niveles)
        self.v22(niveles)
        if not (self.pl.get('zonas') if self.fixture else self.reglas.get('zonas')):
            self.inf.omitir('V17', 'no hay zonas definidas' + (' en el fixture' if self.fixture else ' en reglas_planta.json'))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Valida la planta de la torre (reglas V1-V20 del contrato, 3.5, V21 de las escaleras, 16.1, V22 de paso físico y V23 del prediseño DMO, 17.1).')
    ap.add_argument('--archivo', type=Path, help='archivo de plantas a validar con todas las reglas')
    ap.add_argument('--fixture', nargs='?', type=Path, const=C.FIXTURES / 'plantas_min.json',
                    help='valida un fixture y omite V2, V6, V15, V16 y V20 (por defecto scripts/fixtures/torre/plantas_min.json)')
    ap.add_argument('--programa', type=Path, default=C.PROGRAMA)
    ap.add_argument('--reglas', type=Path, default=C.REGLAS_PLANTA)
    ap.add_argument('--estructura', type=Path, default=ESTRUCTURA,
                    help='prediseño estructural del equipo A (V23); por defecto data/sismo/torre_hospital_estructura.json')
    a = ap.parse_args(argv)
    if a.archivo and a.fixture:
        ap.error('use --archivo o --fixture, no los dos')
    fixture = a.fixture is not None
    ruta = a.fixture or a.archivo or C.PLANTAS
    inf = C.Informe('validar_plantas', REGLAS, archivo=C.relativa(ruta), modo='fixture' if fixture else 'completo')
    try:
        plantas = C.cargar_json(ruta)
    except (FileNotFoundError, ValueError) as e:
        inf.error('V1', str(e))
        inf.omitir_resto('no se pudo leer el archivo de plantas')
        inf.salir()
    programa = None
    if not fixture:
        try:
            programa = C.cargar_json(a.programa)
        except (FileNotFoundError, ValueError):
            programa = None
    reglas = cargar_reglas(a.reglas)
    inf.cabecera['reglas_planta'] = reglas['fuente']
    estructura = None
    if not fixture:
        try:
            estructura = C.cargar_json(a.estructura)
            inf.cabecera['estructura'] = C.relativa(a.estructura)
        except (FileNotFoundError, ValueError):
            estructura = None
    Validador(plantas, inf, fixture, programa, reglas, estructura).correr()
    inf.salir()


if __name__ == '__main__':
    main()
