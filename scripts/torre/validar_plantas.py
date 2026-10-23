"""Valida la planta de la torre con las reglas V1 a V20 del contrato (ESPECIFICACION_INTEGRACION.md, 3.5).

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
}
SOLO_PROGRAMA = ('V2', 'V6', 'V15', 'V16', 'V20')

TIPOS_ESPACIO = ('recinto', 'circulacion', 'nucleo')
ABRE = ('adentro', 'afuera', 'corrediza', 'doble')
TIPOS_CONEXION = ('escalera', 'ascensor', 'escalera_abierta', 'montacargas')
TIPOS_NUCLEO = ('escalera', 'ascensor', 'montacargas', 'ductos')

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
}
COLUMNA_LIBRE_PERMITIDA = re.compile(r'gimnasio|expansi[oó]n|espera', re.I)
RE_PLOMADO = re.compile(r'rayos\s*x|periapical', re.I)
RE_VENTANA_EXIGIDA = re.compile(r'hospitaliz|habitaci[oó]n|TPR|parto|posparto|observaci[oó]n|consultorio|terapia|fisioterapia', re.I)
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
        for k in ('puertas', 'corredores', 'evacuacion', 'zonas', 'accesos_permitidos'):
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
        self.muros = {m.get('id'): m for m in n.get('muros', []) if isinstance(m, dict)}
        self.puertas = [p for p in n.get('puertas', []) if isinstance(p, dict)]
        self.ventanas = [v for v in n.get('ventanas', []) if isinstance(v, dict)]
        self.contorno = C.orientar_antihorario(n['contorno']) if poligono_valido(n.get('contorno')) else None

    def muros_validos(self):
        return [m for m in self.muros.values() if punto(m.get('a')) and punto(m.get('b'))
                and (C.es_horizontal(m['a'], m['b']) or C.es_vertical(m['a'], m['b']))
                and math.dist(m['a'][:2], m['b'][:2]) > TOL]

    def espacio_en(self, pt):
        for rid, p in self.pol.items():
            if C.punto_en_poligono(pt, p, 0.0):
                return rid
        return None


class Validador:
    def __init__(self, plantas: dict, informe: C.Informe, fixture: bool, programa: dict | None, reglas: dict):
        self.pl = plantas
        self.inf = informe
        self.fixture = fixture
        self.programa = programa
        self.reglas = reglas
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
            if not isinstance(d, dict) or not num(d.get('espesor_m')) or d['espesor_m'] <= 0:
                self.err('V1', f'tipos_muro.{t} sin espesor_m positivo')
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
            if tipo == 'circulacion':
                m = C.RE_CIRCULACION.match(str(rid))
                if not m or m.group(1) != P:
                    self.err('V1', f'{q}id de circulación mal formado (se espera {P}-CIRC-nn)')
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
                    al = C.area_poligono(nv.libre[rid])
                    if not num(r.get('area_libre_m2')) or abs(r['area_libre_m2'] - al) > 0.01:
                        self.err('V1', f'{q}area_libre_m2 = {r.get("area_libre_m2")} y el polígono libre mide {al:.3f} m²')
                if not C.poligono_dentro_de(nv.libre[rid], p, TOL):
                    self.err('V1', f'{q}el polígono libre se sale del polígono a ejes')
            mn = r.get('minimo_1633')
            if mn is not None and not (isinstance(mn, dict) and num(mn.get('m2')) and num(mn.get('lado_m'))
                                       and isinstance(mn.get('cita'), str)):
                self.err('V1', f'{q}minimo_1633 debe ser null o {{m2, lado_m, cita}}')
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
            if not num(m.get('altura')) or m['altura'] <= 0:
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
                elif lado not in nv.pol:
                    self.err('V1', f'{q}lado {nombre_lado} {lado!r} no es un recinto del nivel')
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
            dif = C.area_poligono(esperado) + C.area_poligono(dado) - 2 * C.area_interseccion(esperado, dado)
            if dif > 0.01:
                self.err('V1', f'{pre}{rid}: el polígono libre no corresponde a desplazar cada borde la mitad del espesor '
                               f'de su muro (diferencia {dif:.3f} m²; esperado {C.redondear_todo(esperado, 3)})')

        # puertas
        vecinos = {rid: set() for rid in nv.por_id}
        puertas_de = {rid: set() for rid in nv.por_id}
        for pt in nv.puertas:
            pid = pt.get('id')
            q = f'{pre}{pid}: '
            mm = C.RE_PUERTA.match(str(pid))
            if not mm or mm.group(1) != P:
                self.err('V1', f'{q}id de puerta mal formado (se espera {P}-PT-nnn)')
            m = nv.muros.get(pt.get('muro'))
            if m is None:
                self.err('V1', f'{q}el muro {pt.get("muro")!r} no existe')
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
                if lado != 'exterior' and lado not in nv.por_id:
                    self.err('V1', f'{q}{lado!r} no es un recinto del nivel ni «exterior»')
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
            for a_, b_ in ((de, ha), (ha, de)):
                if a_ in vecinos:
                    vecinos[a_].add(b_)
                    puertas_de[a_].add(pid)
        for r in nv.espacios:
            rid = r.get('id')
            if 'acceso' in r and isinstance(r['acceso'], list) and set(r['acceso']) != vecinos.get(rid, set()):
                self.err('V1', f'{pre}{rid}: «acceso» = {sorted(r["acceso"])} y sus puertas llevan a '
                               f'{sorted(vecinos.get(rid, set()), key=str)}')
            if 'puertas' in r and isinstance(r['puertas'], list) and set(r['puertas']) != puertas_de.get(rid, set()):
                self.err('V1', f'{pre}{rid}: «puertas» = {sorted(r["puertas"])} y las que lo tocan son '
                               f'{sorted(puertas_de.get(rid, set()), key=str)}')

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
            rid = nu.get('recinto')
            if rid not in nv.pol:
                self.err('V1', f'{q}el recinto {rid!r} no existe')
            elif not poligono_valido(nu.get('poligono')) or not C.poligono_dentro_de(nu['poligono'], nv.pol[rid], TOL):
                self.err('V1', f'{q}el polígono del núcleo no queda dentro de su recinto {rid}')

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
                al = C.area_poligono(nv.libre[rid])
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
        for r in nv.espacios:
            if r.get('tipo') not in ('recinto', 'nucleo'):
                continue
            self.inf.revisado('V9')
            ok = False
            for otro in adyacentes.get(r.get('id'), ()):
                o = nv.por_id[otro]
                if o.get('tipo') == 'circulacion' or self._permitido(r, o):
                    ok = True
                    break
            if not ok:
                self.err('V9', f'{nv.id}: {r.get("id")} ({r.get("ambiente")}) no tiene puerta a una circulación ni a un '
                               'recinto de accesos_permitidos')
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
        sueltos = [rid for rid in nv.por_id if rid not in vistos]
        if sueltos:
            self.err('V10', f'{nv.id}: recintos que no se alcanzan por puertas: {sueltos}')

    # ------------------------------------------------------------------------------------------------ V11 y V12
    def v11(self, nv: Nivel):
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
                if not r:
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

    def _barridos(self, nv: Nivel):
        salida = []
        for pt in nv.puertas:
            m = nv.muros.get(pt.get('muro'))
            if m is None or not punto(pt.get('centro')) or not num(pt.get('ancho')) or not punto(m.get('a')):
                continue
            for h in C.hojas_puerta(pt, m, nv.pol):
                pts = [x for x in C.sector(h['bisagra'], h['radio'], h['ang0'], h['ang1'])
                       if C.distancia_punto_segmento(x, m['a'], m['b']) > m.get('espesor', 0) / 2 + 0.005]
                salida.append((pt, m, h, pts))
        return salida

    def v12(self, nv: Nivel):
        barridos = self._barridos(nv)
        for pt, m, h, pts in barridos:
            self.inf.revisado('V12')
            lado = h['lado']
            if lado == 'exterior' or lado not in nv.libre:
                continue
            fuera = [x for x in pts if not C.punto_en_poligono(x, nv.libre[lado], 0.01)]
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
        for r in nv.espacios:
            if r.get('tipo') != 'circulacion' or r.get('id') not in nv.libre:
                continue
            self.inf.revisado('V13')
            w = C.ancho_minimo(nv.libre[r['id']])
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

    def v14(self, nv: Nivel):
        ev = self.reglas['evacuacion']
        if nv.contorno is None or not nv.libre:
            return
        protegidas = {nu.get('recinto') for nu in nv.d.get('nucleos', []) if nu.get('tipo') == 'escalera'}
        x0, y0, x1, y1 = C.caja(nv.contorno)
        rej = C.Rejilla(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, 0.10)
        for rid, p in nv.libre.items():
            if rid not in protegidas:
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

        for pt in nv.puertas:
            pid = pt.get('id')
            if pid not in vanos:
                continue
            for lado in (pt.get('desde'), pt.get('hacia')):
                r = nv.por_id.get(lado)
                if not r or r.get('tipo') == 'circulacion' or lado in protegidas:
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
                malos = [m['id'] for m in tramo if m.get('tipo') != 'plomado']
                if malos:
                    self.err('V18', f'{nv.id}: {r["id"]} ({r.get("ambiente")}): muros sin plomo {malos}')
                if C.largo_cubierto(s0, s1, [(m['a'], m['b']) for m in tramo]) < math.dist(s0, s1) - TOL:
                    self.err('V18', f'{nv.id}: {r["id"]}: el borde {s0} → {s1} no está cubierto por muros plomados')

    def v19(self, nv: Nivel):
        for r in nv.espacios:
            if r.get('tipo') != 'recinto':
                continue
            texto = f'{r.get("ambiente", "")} {r.get("servicio_programa", "")}'
            if not RE_VENTANA_EXIGIDA.search(texto) or r.get('id') not in nv.pol:
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

    @staticmethod
    def piso_programa(piso):
        if isinstance(piso, int):
            return f'P{piso}'
        if isinstance(piso, str) and 'bloque' in piso.lower():
            return 'BT'
        return None

    def v2_v6(self, niveles: list[Nivel]):
        amb = self.ambientes()
        cuenta = {}
        for nv in niveles:
            for r in nv.espacios:
                f = r.get('fila')
                if r.get('tipo') == 'circulacion' or not isinstance(f, int):
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
                if self.piso_programa(a.get('piso')) != nv.id:
                    self.err('V2', f'{q}la fila {f} es del piso {a.get("piso")!r}, no de {nv.id}')
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
        for f, a in enumerate(amb):
            if self.piso_programa(a.get('piso')) is None:
                continue
            if cuenta.get(f, 0) != a.get('cantidad'):
                self.err('V2', f'fila {f} («{a.get("nombre")}», piso {a.get("piso")}): {cuenta.get(f, 0)} recintos y la '
                               f'cantidad es {a.get("cantidad")}')
        esperado = {}
        for a in amb:
            k = self.piso_programa(a.get('piso'))
            if k:
                esperado[k] = esperado.get(k, 0) + a.get('cantidad', 0)
        obtenido = {nv.id: sum(1 for r in nv.espacios if r.get('tipo') != 'circulacion' and isinstance(r.get('fila'), int))
                    for nv in niveles}
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
            if nv.id == 'BT':
                continue
            pols = [(nu.get('tipo'), nu.get('poligono')) for nu in nv.d.get('nucleos', []) if poligono_valido(nu.get('poligono'))]
            for clave, (tipo, r) in rects.items():
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
            if nv.id == 'BT' or nv.contorno is None:
                continue
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
            util = sum(C.area_poligono(nv.pol[r['id']]) for r in nv.espacios if r.get('tipo') == 'recinto' and r.get('id') in nv.pol)
            meta = resumen[nv.id].get('m2_util', 0)
            if util < meta - 1e-6:
                self.err('V20', f'{nv.id}: {util:.1f} m² útiles a ejes < {meta} m² útiles del programa')

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
        if not (self.pl.get('zonas') if self.fixture else self.reglas.get('zonas')):
            self.inf.omitir('V17', 'no hay zonas definidas' + (' en el fixture' if self.fixture else ' en reglas_planta.json'))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Valida la planta de la torre (reglas V1-V20 del contrato, 3.5).')
    ap.add_argument('--archivo', type=Path, help='archivo de plantas a validar con todas las reglas')
    ap.add_argument('--fixture', nargs='?', type=Path, const=C.FIXTURES / 'plantas_min.json',
                    help='valida un fixture y omite V2, V6, V15, V16 y V20 (por defecto scripts/fixtures/torre/plantas_min.json)')
    ap.add_argument('--programa', type=Path, default=C.PROGRAMA)
    ap.add_argument('--reglas', type=Path, default=C.REGLAS_PLANTA)
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
    Validador(plantas, inf, fixture, programa, reglas).correr()
    inf.salir()


if __name__ == '__main__':
    main()
