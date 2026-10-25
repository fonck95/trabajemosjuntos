"""Detección de interferencias del modelo BIM de la torre (equipo F, contrato 17.4).

    python3 scripts/bim/interferencias.py              # escribe data/bim/interferencias.json
    python3 scripts/bim/interferencias.py --verificar  # regenera en memoria y compara (rc 1 si difiere)

Revisa sobre data/bim/torre_hospital.bim.json (solo biblioteca estándar):
 1. unidades de dotación y equipamiento fijo contra columnas, arranques y muros estructurales;
 2. vanos de puertas contra columnas y muros estructurales;
 3. choques de concreto entre elementos de estructura, cimentación y escaleras (incluye fosos contra losas de pilotes y
    vigas de amarre), y muros de mampostería, fachada y cerramientos de todos los niveles contra columnas, vigas, muros
    estructurales, losas y cimentación;
 4. ductos verticales contra losas y vigas de cada nivel, y su salida bajo el contrapiso contra la cimentación;
 5. escaleras: losas sin abertura y altura libre sobre los peldaños;
 6. refuerzo: separación libre entre barras paralelas (NSR-10 C.7.6) y tamaño del agregado (C.3.3.2);
 7. refuerzo: recubrimientos medidos en la geometría frente a C.7.7.1 según la exposición;
 8. refuerzo: barras que se cruzan (penetración de una barra en otra);
 9. refuerzo fuera del concreto (con su causa: un insumo que no cuadra o el dibujo del modelo) y pilotes dentro de su
    dado con la distancia al borde del prediseño y el recubrimiento del dado para su canasta;
10. coherencia de los insumos (vigas de amarre que no se apoyan, esquinas de núcleo sin concreto, bordes de losa sin
    apoyo, cotas de las cisternas frente al bloque técnico, muros de contención que pasan la cara de su apoyo, área de
    acero de las parrillas de los dados frente a la requerida, conteo y paso de los estribos y de las cortinas frente al
    diseño).
El recubrimiento corto es del modelo (F) si el que especifica el prediseño ya cumple la NSR-10, y del prediseño (A) si no.
Cada interferencia lleva ids, posición, medida, severidad, propuesta, responsable y estado. Lo que es del modelo BIM
(equipo F) se corrige en generar_bim.py/despiece.py; lo de otros equipos queda pendiente con su evidencia.
Modelo de prefactibilidad: no reemplaza los diseños firmados."""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import despiece as DSP  # noqa: E402
from comun import BIM, INSUMOS, escribir_json, leer, r, rel, rp, sha1  # noqa: E402

ENTRADA = BIM / 'torre_hospital.bim.json'
SALIDA = BIM / 'interferencias.json'
AGREGADO = 0.019              # tamaño máximo nominal del agregado (3/4"): estimación de A (AGREGADO_MM)
TOL_SOLIDO = 0.01             # m: penetración mínima entre sólidos que se informa
TOL_BARRA = 0.0015            # m: penetración mínima entre barras que se informa
ALTURA_LIBRE = 2.05           # m sobre la nariz de los peldaños (NSR-10 K.3, por confirmar)

SEVERIDAD = {'dura': 'choque físico o incumplimiento de norma: hay que corregirlo antes del diseño definitivo',
             'media': 'congestión o falta de holgura: se resuelve en el detallado o en obra con una instrucción',
             'leve': 'contacto o diferencia dentro de las tolerancias de construcción'}


# =============================================================================================== geometría
def _min(nombre):
    """Nombre dentro de una frase: minúscula solo la primera letra (los códigos de ejes y elementos quedan en mayúscula)."""
    return nombre[:1].lower() + nombre[1:] if nombre else nombre


def partes(g):
    """Cajas (min, max) de la geometría; los cilindros y perfiles por su caja envolvente (marcados)."""
    t = g['tipo']
    if t == 'caja':
        return [(tuple(g['min']), tuple(g['max']), 'caja')]
    if t == 'prisma':
        xs = [p[0] for p in g['planta']]
        ys = [p[1] for p in g['planta']]
        return [((min(xs), min(ys), g['z0']), (max(xs), max(ys), g['z1']), 'caja' if len(g['planta']) == 4 and not g.get('huecos') else 'envolvente')]
    if t == 'cilindro':
        cx, cy = g['centro']
        R_ = g['radio']
        return [((cx - R_, cy - R_, g['z0']), (cx + R_, cy + R_, g['z1']), 'cilindro')]
    if t == 'perfil':
        pts = []
        for u, v in g['puntos']:
            for w in (0.0, g['largo']):
                pts.append([g['origen'][i] + g['u'][i] * u + g['v'][i] * v + g['w'][i] * w for i in range(3)])
        return [(tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)), 'perfil')]
    if t == 'caja_girada':
        cx, cy, z = g['centro']
        w, d, h = g['dim']
        c, s = math.cos(g['rot']), math.sin(g['rot'])
        xs = [cx + c * a - s * b for a in (-w / 2, w / 2) for b in (-d / 2, d / 2)]
        ys = [cy + s * a + c * b for a in (-w / 2, w / 2) for b in (-d / 2, d / 2)]
        return [((min(xs), min(ys), z), (max(xs), max(ys), z + h), 'girada')]
    if t == 'compuesta':
        out = []
        for p in g['partes']:
            out += partes(p)
        return out
    raise ValueError(t)


def solape(a0, a1, b0, b1):
    return [min(a1[i], b1[i]) - max(a0[i], b0[i]) for i in range(3)]


def obb_aabb(g, b0, b1):
    """Penetración (m) de una caja girada contra una caja alineada (ejes separadores en planta + z)."""
    cx, cy, z = g['centro']
    w, d, h = g['dim']
    zs = min(z + h, b1[2]) - max(z, b0[2])
    if zs <= 0:
        return zs
    c, s = math.cos(g['rot']), math.sin(g['rot'])
    P = [(cx + c * a - s * b, cy + s * a + c * b) for a, b in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]
    Q = [(b0[0], b0[1]), (b1[0], b0[1]), (b1[0], b1[1]), (b0[0], b1[1])]
    pen = zs
    for ax in ((1.0, 0.0), (0.0, 1.0), (c, s), (-s, c)):
        pa = [p[0] * ax[0] + p[1] * ax[1] for p in P]
        pb = [q[0] * ax[0] + q[1] * ax[1] for q in Q]
        o = min(max(pa), max(pb)) - max(min(pa), min(pb))
        if o <= 0:
            return o
        pen = min(pen, o)
    return pen


class Indice:
    """Índice espacial de cajas (rejilla de 1 m en planta)."""

    def __init__(self, cajas, celda=1.0):
        self.c = celda
        self.cajas = cajas
        self.grid = {}
        for i, (a, b, *_rest) in enumerate(cajas):
            for gx in range(int(math.floor(a[0] / celda)), int(math.floor(b[0] / celda)) + 1):
                for gy in range(int(math.floor(a[1] / celda)), int(math.floor(b[1] / celda)) + 1):
                    self.grid.setdefault((gx, gy), []).append(i)

    def cerca(self, a, b):
        out = set()
        for gx in range(int(math.floor(a[0] / self.c)), int(math.floor(b[0] / self.c)) + 1):
            for gy in range(int(math.floor(a[1] / self.c)), int(math.floor(b[1] / self.c)) + 1):
                out.update(self.grid.get((gx, gy), ()))
        return sorted(out)

    def en(self, p, tol=0.0):
        """Índices de cajas que contienen el punto (con tolerancia)."""
        gx, gy = int(math.floor(p[0] / self.c)), int(math.floor(p[1] / self.c))
        out = []
        for i in self.grid.get((gx, gy), ()):
            a, b = self.cajas[i][0], self.cajas[i][1]
            if all(a[k] - tol <= p[k] <= b[k] + tol for k in range(3)):
                if self.cajas[i][2] == 'cilindro':
                    cx, cy, R_ = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (b[0] - a[0]) / 2
                    if math.hypot(p[0] - cx, p[1] - cy) > R_ + tol:
                        continue
                out.append(i)
        return out


def dist_seg(p1, q1, p2, q2):
    """Distancia mínima entre dos segmentos 3D y el punto medio entre los más cercanos."""
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    rr = [p1[i] - p2[i] for i in range(3)]
    a = sum(x * x for x in d1)
    e = sum(x * x for x in d2)
    f = sum(d2[i] * rr[i] for i in range(3))
    if a <= 1e-12 and e <= 1e-12:
        s = t = 0.0
    elif a <= 1e-12:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = sum(d1[i] * rr[i] for i in range(3))
        if e <= 1e-12:
            t, s = 0.0, max(0.0, min(1.0, -c / a))
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            den = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / den)) if den > 1e-14 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    c1 = [p1[i] + d1[i] * s for i in range(3)]
    c2 = [p2[i] + d2[i] * t for i in range(3)]
    return math.dist(c1, c2), [(c1[i] + c2[i]) / 2 for i in range(3)]


# ================================================================================================= registro
def coma_decimal(s):
    """Cifras del texto con coma decimal (1.5 cm → 1,5 cm); los numerales de las normas (C.7.7.1) y los ítems del
    presupuesto (ítem 2.09) no cambian."""
    return re.sub(r'(?<![\w.])(?<!ítem )(?<!ítems )(?<!fila )(-?\d+)\.(\d+)(?![\w.])', r'\1,\2', s) if isinstance(s, str) else s


class Registro:
    def __init__(self):
        self.lista = []

    def add(self, categoria, severidad, elementos, posicion, descripcion, propuesta, responsable, estado='pendiente', medida=None,
            norma=None, casos=1):
        descripcion, propuesta = coma_decimal(descripcion), coma_decimal(propuesta)
        self.lista.append({'categoria': categoria, 'severidad': severidad, 'elementos': list(elementos),
                           'posicion': rp(posicion, 3) if posicion else None, 'medida': medida or {}, 'descripcion': descripcion,
                           'propuesta': propuesta, 'responsable': responsable, 'estado': estado, 'norma': norma, 'casos': casos})


def nivel_z(z):
    for nid, z0 in (('CUB', 17.1), ('P4', 12.9), ('P3', 8.7), ('P2', 4.5), ('P1', 0.0)):
        if z >= z0 - 0.05:
            return nid
    return 'CIM'


# ========================================================================================== 1-2. unidades y puertas
def unidades_y_puertas(M, E, Rg):
    estr = [(a, b, e['id']) for e in M['elementos'] if (e['disciplina'] in ('EST', 'CIM') and e['clase'] in ('IfcColumn', 'IfcWall'))
            for (a, b, _t) in partes(e['geometria'])]
    idx = Indice([(a, b, 'caja') for a, b, _ in estr])
    n_u = 0
    for e in M['elementos']:
        if e['disciplina'] not in ('DOT', 'FIJO'):
            continue
        n_u += 1
        vistos = set()
        # una unidad es una caja girada; las filas solares elevadas son el plano de módulos y sus dos postes
        for g in (e['geometria']['partes'] if e['geometria']['tipo'] == 'compuesta' else [e['geometria']]):
            (a, b, _t), = partes(g)
            for i in idx.cerca(a, b):
                b0, b1, sid = estr[i]
                pen = obb_aabb(g, b0, b1)
                if pen > TOL_SOLIDO and sid not in vistos:
                    vistos.add(sid)
                    Rg.add('unidad contra estructura', 'dura' if pen > 0.05 else 'leve', [e['id'], sid], [g['centro'][0], g['centro'][1], g['centro'][2] + g['dim'][2] / 2],
                           f'«{e["nombre"]}» se mete {pen * 100:.1f} cm en {_min(E[sid]["nombre"])}.',
                           f'Correr la unidad al menos {pen * 100 + 1:.0f} cm hacia el recinto (regla de ubicación del inventario).', 'B',
                           medida={'penetracion_m': r(pen, 3)}, norma='Res. 3100 de 2019 (ubicación de la dotación) y NSR-10 A.9 (anclaje; numeral por confirmar)')
    n_p = 0
    for e in M['elementos']:
        v = e.get('vano')
        if e['clase'] != 'IfcDoor' or not v:
            continue
        n_p += 1
        (a, b, _t), = partes(v['geometria'])
        for i in idx.cerca(a, b):
            b0, b1, sid = estr[i]
            o = solape(a, b, b0, b1)
            if min(o) > 0.005:
                eje = 'x' if (b[0] - a[0]) > (b[1] - a[1]) else 'y'
                pen = o[0] if eje == 'x' else o[1]
                Rg.add('puerta contra estructura', 'dura', [e['id'], sid], [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, a[2] + 1.0],
                       f'El vano de «{e["nombre"]}» ({e.get("ancho_total")} m) se mete {pen * 100:.1f} cm en {_min(E[sid]["nombre"])}.',
                       f'Correr la puerta {pen * 100 + 2:.0f} cm a lo largo del muro (o reducir la hoja si el ancho mínimo lo permite).', 'B',
                       medida={'penetracion_m': r(pen, 3)}, norma='NSR-10 K.3.14 y C.21 (no se perforan columnas ni muros estructurales; numerales por confirmar)')
    return {'unidades_revisadas': n_u, 'puertas_revisadas': n_p}


# ================================================================================================ 3. concreto
def concreto(M, E, Rg):
    sol = []
    for e in M['elementos']:
        if e.get('material') not in ('concreto_28', 'concreto_21') or e['clase'] in ('IfcStair', 'IfcElementAssembly'):
            continue
        for (a, b, t) in partes(e['geometria']):
            sol.append((a, b, t, e['id']))
    sol.sort(key=lambda s_: s_[0][0])
    vistos = {}
    activos = []
    for i, (a, b, t, eid) in enumerate(sol):
        activos = [j for j in activos if sol[j][1][0] > a[0] + TOL_SOLIDO]
        for j in activos:
            a2, b2, t2, eid2 = sol[j]
            if eid2 == eid or E[eid].get('parte_de') and E[eid].get('parte_de') == E[eid2].get('parte_de'):
                continue
            o = solape(a, b, a2, b2)
            if min(o) <= TOL_SOLIDO:
                continue
            if 'cilindro' in (t, t2):
                # pilote contra su dado: la cabeza entra 0,10 m (empotramiento de A); se acepta sin informar
                pil, otro = (eid, eid2) if t == 'cilindro' else (eid2, eid)
                if E[otro]['clase'] == 'IfcFooting' and o[2] <= 0.105:
                    continue
            clave = tuple(sorted((eid, eid2)))
            v = o[0] * o[1] * o[2]
            prev = vistos.get(clave)
            if prev is None or v > prev[0]:
                vistos[clave] = (v, o, [(max(a[k], a2[k]) + min(b[k], b2[k])) / 2 for k in range(3)])
        activos.append(i)
    for (x, y), (v, o, pos) in sorted(vistos.items()):
        ex, ey = E[x], E[y]
        clases = {ex['clase'], ey['clase']}
        disc = {ex['disciplina'], ey['disciplina']}
        par = ' y '.join(sorted([_min(ex['nombre']), _min(ey['nombre'])]))
        if any(z_.get('parte_de', '').startswith(('ESC-', )) for z_ in (ex, ey)) and 'CP-1' in (x, y):
            Rg.add('concreto contra concreto', 'leve', [x, y], pos, f'El arranque del tramo de escalera se apoya dentro del contrapiso ({v:.3f} m³ comunes).',
                   'Fundir el arranque del tramo con el contrapiso (criterio del modelo).', 'F', 'aceptada (criterio del modelo)', {'volumen_m3': r(v, 3)})
            continue
        arr = [z_ for z_ in (x, y) if z_.startswith('ARR-')]
        if arr and min(o[0], o[1]) <= 0.031 and (len(arr) == 2 or any(E[z_].get('parte_de', '').startswith('ESC-') for z_ in (x, y))):
            Rg.add('concreto contra concreto', 'leve', [x, y], pos,
                   f'{par[0].upper() + par[1:]} se tocan en el sobreancho del arranque ({min(o[0], o[1]) * 100:.1f} cm; {v:.3f} m³ comunes): '
                   'el arranque se ensancha bajo el piso para el recubrimiento contra el relleno y se funde con lo que tiene al lado.',
                   'Fundir junto (criterio del modelo); el despiece no cambia.', 'F', 'aceptada (criterio del modelo)',
                   {'volumen_m3': r(v, 3), 'solape_m': rp(o, 3)})
            continue
        if x.startswith('FOSO') or y.startswith('FOSO'):
            cat, resp = 'foso contra cimentación', 'A'
            prop = ('Bajar la losa de pilotes bajo el foso (fondo del foso más su losa) o separar el foso de la losa de pilotes, y '
                    'revisar los pilotes que quedan bajo el foso.')
        elif 'FOOTING_BEAM' in (ex['tipo_predefinido'], ey['tipo_predefinido']) and 'PILE_CAP' in (ex['tipo_predefinido'], ey['tipo_predefinido']):
            cat, resp = 'viga de amarre contra dado o losa de pilotes', 'A'
            prop = 'Recortar la viga de amarre en la cara de la losa de pilotes (su tramo se calculó con una losa más pequeña) o unirla a la losa.'
        elif disc == {'ARQ', 'EST'} or disc == {'ARQ'}:
            cat, resp = 'escalera contra estructura', 'B'
            prop = 'Dejar la abertura de la escalera en la losa (con vigas de borde) o mover la escalera.'
        else:
            cat, resp = 'concreto contra concreto', 'A y F'
            prop = 'Revisar las cotas y dimensiones de los dos elementos.'
        Rg.add(cat, 'dura' if v > 0.01 else 'media', [x, y], pos, f'{par[0].upper() + par[1:]} ocupan el mismo espacio: {v:.3f} m³ '
               f'({o[0]:.2f} × {o[1]:.2f} × {o[2]:.2f} m).', prop, resp, medida={'volumen_m3': r(v, 3), 'solape_m': rp(o, 3)})
    return {'solidos': len(sol)}


# ================================================================================ 3b. mampostería contra estructura
def mamposteria(M, E, Rg):
    """Muros no estructurales (ARQ: mampostería, placa de yeso, fachada, cerramientos) de todos los niveles contra
    columnas, vigas, muros estructurales y losas de la estructura y la cimentación: el modelo corta los muros en las
    columnas y los termina bajo la viga o la losa; si se meten en el concreto, es un error del modelo (F)."""
    est = [(a, b, e['id']) for e in M['elementos'] if e['disciplina'] in ('EST', 'CIM')
           and e['clase'] in ('IfcColumn', 'IfcBeam', 'IfcWall', 'IfcSlab', 'IfcFooting')
           for (a, b, _t) in partes(e['geometria'])]
    idx = Indice([(a, b, 'caja') for a, b, _ in est])
    n = 0
    peor = {}
    for e in M['elementos']:
        if e['disciplina'] != 'ARQ' or e['clase'] != 'IfcWall':
            continue
        n += 1
        for (a, b, _t) in partes(e['geometria']):
            for i in idx.cerca(a, b):
                b0, b1, sid = est[i]
                o = solape(a, b, b0, b1)
                if min(o) <= TOL_SOLIDO:
                    continue
                v = o[0] * o[1] * o[2]
                q = peor.get((e['id'], sid))
                if q is None or v > q[0]:
                    peor[(e['id'], sid)] = (v, o, [(max(a[k], b0[k]) + min(b[k], b1[k])) / 2 for k in range(3)])
    for (wid, sid), (v, o, pos) in sorted(peor.items()):
        w, s_ = E[wid], E[sid]
        if s_['disciplina'] == 'CIM' and w['nivel'] in ('BT', 'EXT'):
            # el bloque técnico y los patios (B) contra la cimentación de la torre o las cisternas (A): cotas por coordinar
            prop = (f'Coordinar las cotas del {"bloque técnico" if w["nivel"] == "BT" else "exterior"} con la cimentación: '
                    f'{_min(s_["nombre"])} ocupa {o[2]:.2f} m de la altura del muro sobre su piso. Correr el muro fuera del '
                    'elemento de cimentación, o bajar o recortar ese elemento (prediseño de A).')
            resp = 'A y B'
        else:
            prop = ('Cortar el muro en la cara de la columna o del muro estructural y terminarlo bajo la viga o la losa, con junta '
                    'de dilatación (NSR-10 A.9), en el modelo.')
            resp = 'F'
        Rg.add('mampostería contra estructura', 'dura' if v > 0.01 else 'media', [wid, sid], pos,
               f'El {_min(w["nombre"])} ({wid}) se mete en {_min(s_["nombre"])}: {v:.3f} m³ comunes '
               f'({o[0]:.2f} × {o[1]:.2f} × {o[2]:.2f} m).', prop, resp, medida={'volumen_m3': r(v, 4), 'solape_m': rp(o, 3)},
               norma='NSR-10 A.9.4 (elementos no estructurales separados de la estructura, por confirmar)')
    return {'muros_revisados': n, 'parejas_con_choque': len(peor)}


# ============================================================================================ 4. ductos y fosos
def ductos(M, E, pl, Rg):
    niveles = {n['id']: n for n in pl['niveles']}
    duct = {}
    for nid in ('P1', 'P2', 'P3', 'P4'):
        for rc in niveles[nid]['recintos']:
            if 'Ductos verticales' in rc['ambiente']:
                duct[nid] = rc
    est_sup = {}
    for e in M['elementos']:
        if e['disciplina'] == 'EST' and e['clase'] in ('IfcSlab', 'IfcBeam'):
            est_sup.setdefault(e['nivel'], []).append(e)
    sig = {'P1': 'P2', 'P2': 'P3', 'P3': 'P4', 'P4': 'CUB'}
    from generar_bim import restar_rects  # noqa
    def celdas(pol):
        """Rectángulos que forman un polígono ortogonal (el ducto de un piso puede tener forma de L): las celdas de la
        rejilla de sus coordenadas cuyo centro queda dentro."""
        xs = sorted({q[0] for q in pol})
        ys = sorted({q[1] for q in pol})

        def dentro(x, y):
            c = False
            for (x1, y1), (x2, y2) in zip(pol, pol[1:] + pol[:1]):
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    c = not c
            return c
        return [[x0, y0, x1, y1] for x0, x1 in zip(xs, xs[1:]) for y0, y1 in zip(ys, ys[1:]) if dentro((x0 + x1) / 2, (y0 + y1) / 2)]

    def corte(cs, a, b, minimo):
        """Parte de la planta de una caja (a, b) dentro del ducto: área y rectángulo envolvente."""
        area, env = 0.0, None
        for q in cs:
            o = [min(q[2], b[0]) - max(q[0], a[0]), min(q[3], b[1]) - max(q[1], a[1])]
            if min(o) > minimo:
                area += o[0] * o[1]
                w = [max(q[0], a[0]), max(q[1], a[1]), min(q[2], b[0]), min(q[3], b[1])]
                env = w if env is None else [min(env[0], w[0]), min(env[1], w[1]), max(env[2], w[2]), max(env[3], w[3])]
        return area, env
    for nid, rc in duct.items():
        pol = rc['poligono']
        # el ducto es su polígono (no el rectángulo que lo envuelve)
        cs = celdas([list(q) for q in pol])
        xs = sorted({p[0] for p in pol})
        ys = sorted({p[1] for p in pol})
        rect = [min(xs), min(ys), max(xs), max(ys)]
        z = niveles[sig[nid]]['z']
        for e in est_sup.get(sig[nid], []):
            for (a, b, _t) in partes(e['geometria']):
                area, env = corte(cs, a, b, 0.02)
                if env and a[2] < z + 0.01:
                    o = [env[2] - env[0], env[3] - env[1]]
                    if e['clase'] == 'IfcBeam':
                        Rg.add('ducto contra estructura', 'dura', [rc['id'], e['id']], [(env[0] + env[2]) / 2, (env[1] + env[3]) / 2, z - 0.4],
                               f'La {_min(e["nombre"])} atraviesa el ducto vertical {rc["id"]} ({o[0]:.2f} × {o[1]:.2f} m de la sección del ducto).',
                               'Retirar el borde del ducto a la cara de la viga (el ducto queda libre bajo la viga) o desviar los montantes.', 'B',
                               medida={'area_m2': r(area, 3)}, norma='NSR-10 C.21 (no se perforan vigas de pórticos DMO sin diseño; por confirmar)')
                    break
            else:
                continue
        # la losa que cierra el ducto: donde el ducto sigue en el piso de arriba falta la abertura (A); donde el ducto de este
        # piso es más grande que el de arriba (se angosta), primero B fija la forma del ducto y luego A ajusta la abertura
        arriba = duct.get(sig[nid]) or rc
        cs_ar = celdas([list(q) for q in arriba['poligono']])
        cs_com = [w for q in cs for v in cs_ar for w in [[max(q[0], v[0]), max(q[1], v[1]), min(q[2], v[2]), min(q[3], v[3])]]
                  if w[2] - w[0] > 1e-9 and w[3] - w[1] > 1e-9]
        losas = [e for e in est_sup.get(sig[nid], []) if e['clase'] == 'IfcSlab']
        for e in losas:
            area = area_com = 0.0
            for (a, b, _t) in partes(e['geometria']):
                if b[2] > z - 0.06:
                    area += corte(cs, a, b, 0.0)[0]
                    area_com += corte(cs_com, a, b, 0.0)[0]
            if area > 0.05:
                angosta = area - area_com > 0.05
                Rg.add('ducto contra estructura', 'dura', [rc['id'], e['id']], [(rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, z],
                       f'La losa {e["id"]} del nivel {z:.2f} no tiene abertura para el ducto vertical {rc["id"]} ({area:.1f} m² de losa dentro del ducto'
                       + (f'; {area - area_com:.1f} m² en la parte del ducto que no sigue en el piso de arriba, donde el ducto se angosta)' if angosta else ')') + '.',
                       ('Fijar la forma del ducto en los dos pisos (que el de arriba crezca o que el de abajo se recorte, equipo B) y dejar la '
                        'abertura de la losa en la parte común, con nervios y vigas de borde a su alrededor (prediseño de A).') if angosta else
                       'Dejar la abertura del ducto en la losa nervada, con nervios y vigas de borde a su alrededor (prediseño de A).',
                       'A y B' if angosta else 'A',
                       medida={'area_m2': r(area, 2), 'area_donde_se_angosta_m2': r(area - area_com, 2)},
                       norma='NSR-10 C.13.5 (aberturas en losas, por confirmar)')
    # continuidad vertical del ducto (B)
    if len(duct) >= 2:
        com = None
        for nid in ('P1', 'P2', 'P3', 'P4'):
            rc = duct.get(nid)
            if not rc:
                continue
            xs = [p[0] for p in rc['poligono']]
            ys = [p[1] for p in rc['poligono']]
            q = [min(xs), min(ys), max(xs), max(ys)]
            com = q if com is None else [max(com[0], q[0]), max(com[1], q[1]), min(com[2], q[2]), min(com[3], q[3])]
        formas = {nid: [r(min(p[0] for p in duct[nid]['poligono']), 2), r(min(p[1] for p in duct[nid]['poligono']), 2),
                        r(max(p[0] for p in duct[nid]['poligono']), 2), r(max(p[1] for p in duct[nid]['poligono']), 2)] for nid in duct}
        if len({tuple(v) for v in formas.values()}) > 1:
            Rg.add('ducto contra estructura', 'media', [duct[n]['id'] for n in sorted(duct)], [(com[0] + com[2]) / 2, (com[1] + com[3]) / 2, 8.0],
                   'El ducto vertical cambia de forma de un piso a otro: los montantes solo pueden ir en la parte común '
                   f'(x {com[0]:.2f} a {com[2]:.2f}; y {com[1]:.2f} a {com[3]:.2f}).',
                   'Alinear el ducto en los cuatro pisos a la parte común (y libre de la viga del eje 6).', 'B',
                   medida={'rectangulo_por_piso': formas, 'comun': rp(com, 2)})
    # salida de redes bajo el ducto del piso 1 (−1,0 m) contra la cimentación
    if 'P1' in duct:
        rc = duct['P1']
        cs = celdas([list(q) for q in rc['poligono']])
        for e in M['elementos']:
            if e['disciplina'] != 'CIM' or e['clase'] not in ('IfcFooting',):
                continue
            for (a, b, _t) in partes(e['geometria']):
                area, env = corte(cs, a, b, 0.02)
                if env and b[2] > -1.0:
                    o = [env[2] - env[0], env[3] - env[1]]
                    Rg.add('ducto contra cimentación', 'media', [rc['id'], e['id']], [(env[0] + env[2]) / 2, (env[1] + env[3]) / 2, b[2]],
                           f'Bajo el ducto {rc["id"]} queda {_min(e["nombre"])} con su cara superior a {b[2]:.2f} m: '
                           f'las redes que bajan del ducto (desagües y acometidas, ≈ −0,60 a −1,00 m) la cruzan en {o[0]:.2f} × {o[1]:.2f} m.',
                           'Dejar pases con camisa en la viga de amarre (fuera del tercio central de su altura no; en su mitad) o sacar las redes '
                           'por el costado del ducto que no tiene cimentación debajo; coordinar con el diseño hidrosanitario.', 'A y B',
                           medida={'cara_superior_m': r(b[2], 3), 'area_m2': r(area, 3)}, norma='NSR-10 C.15.13 y C.6.3 (pases) (por confirmar)')
                    break
    return {'ductos': sorted(duct)}


# ================================================================================================= 5. escaleras
def escaleras(M, E, Rg):
    obst = [e for e in M['elementos'] if e['disciplina'] == 'EST' and e['clase'] in ('IfcBeam', 'IfcSlab')]
    obst_partes = [(a, b, e['id']) for e in obst for (a, b, _t) in partes(e['geometria'])]
    idx = Indice([(a, b, 'caja') for a, b, _ in obst_partes])
    n = 0
    for e in M['elementos']:
        if e['clase'] != 'IfcStairFlight':
            continue
        n += 1
        g = e['geometria']
        ps = e['psets']['Pset_StairFlightCommon']
        nr, rr, gg = ps['NumberOfRiser'], ps['RiserHeight'], ps['TreadLength']
        o, u, w = g['origen'], g['u'], g['w']
        peor = {}
        for k in range(nr - 1):
            for fw in (0.25, 0.5, 0.75):
                uu = (k + 0.5) * gg
                zt = o[2] + (k + 1) * rr
                p = [o[i] + u[i] * uu + w[i] * g['largo'] * fw for i in range(3)]
                for i in idx.cerca([p[0], p[1], 0], [p[0], p[1], 0]):
                    a, b, sid = obst_partes[i]
                    if a[0] <= p[0] <= b[0] and a[1] <= p[1] <= b[1] and b[2] > zt - 0.02:
                        h = a[2] - zt
                        if h < ALTURA_LIBRE:
                            q = peor.get(sid)
                            if q is None or h < q[0]:
                                peor[sid] = (h, [p[0], p[1], zt])
        for sid, (h, pos) in sorted(peor.items()):
            corta = h < -0.05
            Rg.add('escalera contra estructura', 'dura', [e['id'], sid], pos,
                   (f'{E[sid]["nombre"]} corta el {_min(e["nombre"])}: no hay abertura en la losa.' if corta else
                    f'Sobre el {_min(e["nombre"])} pasa {_min(E[sid]["nombre"])} a {h:.2f} m de la nariz del peldaño '
                    f'(mínimo {ALTURA_LIBRE:.2f} m).'),
                   ('Dejar la abertura de la escalera en la losa con vigas de borde (A) o reubicar la escalera fuera de la viga (B).'
                    if E[sid]['clase'] == 'IfcSlab' or corta else 'Reubicar la escalera o el tramo para que no pase bajo la viga, o subir la viga (A y B).'),
                   'A y B', medida={'altura_libre_m': r(h, 2), 'minimo_m': ALTURA_LIBRE}, norma='NSR-10 K.3.8 (escaleras; altura libre por confirmar)')
    return {'tramos': n}


# ===================================================================================================== refuerzo
def instancias(j):
    pl = DSP.polilinea(j)
    for c in j['copias']:
        yield [[p[i] + c[i] for i in range(3)] for p in pl]


def direccion(pts):
    best, L = None, 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d > L:
            L, best = d, [(b[i] - a[i]) / d for i in range(3)]
    return best or [1.0, 0.0, 0.0]


COMPRESION = ('longitudinal', 'borde_', 'longitudinal_superior', 'longitudinal_inferior')
TIPO_HOST = {}


def tipo_host(e):
    i = e['id']
    if i.startswith('ARR-C'):
        return 'arranque_columna'
    if i.startswith('ARR-M'):
        return 'arranque_muro'
    if e['clase'] == 'IfcColumn':
        return 'columna'
    if e['clase'] == 'IfcBeam':
        return 'viga'
    if e['clase'] == 'IfcSlab' and e['disciplina'] == 'EST':
        return 'losa'
    if e['clase'] == 'IfcWall' and e['disciplina'] == 'EST':
        return 'muro'
    if e['clase'] == 'IfcStair':
        return 'escalera'
    if e['clase'] == 'IfcPile':
        return 'pilote'
    if e['clase'] == 'IfcFooting' and e['tipo_predefinido'] == 'PILE_CAP':
        return 'dado'
    if e['clase'] == 'IfcFooting':
        return 'viga_amarre'
    if i.startswith('FOSO'):
        return 'foso'
    if i.startswith('CIS'):
        return 'cisterna'
    if i == 'CP-1':
        return 'contrapiso'
    if e.get('objeto_tipo') == 'RETAININGWALL':
        return 'muro_contencion'
    return 'otro'


def rec_especificado(est):
    """Recubrimiento que especifica el prediseño de A por tipo de elemento (para saber de quién es un faltante)."""
    c = est['refuerzo']['convenciones']['recubrimientos_m']
    C = est['cimentacion']
    return {'columna': c['columna'], 'viga': c['viga'], 'losa': min(c['vigueta'], c['loseta']), 'muro': c['muro'],
            'escalera': c['escalera'], 'pilote': C['pilotes'][0]['recubrimiento_m'], 'dado': c['dado_lados'],
            'viga_amarre': c['viga_amarre'], 'foso': c['foso'], 'cisterna': c['foso'],
            **({'muro_contencion': min(m['refuerzo']['recubrimiento_m'] for m in C['muros_contencion'])} if C.get('muros_contencion') else {})}


REC_ESPEC = {}

# recubrimiento mínimo de NSR-10 C.7.7.1 por exposición (por confirmar): (caras laterales y de arriba, cara de abajo)
REC_MIN = {'columna': (0.040, 0.040, 'C.7.7.1 c: vigas y columnas no expuestas, 40 mm a los estribos'),
           'viga': (0.040, 0.040, 'C.7.7.1 c: vigas no expuestas, 40 mm a los estribos'),
           'losa': (0.020, 0.020, 'C.7.7.1 c: losas, muros y viguetas no expuestos, 20 mm (N.º 11 o menores)'),
           'muro': (0.020, 0.020, 'C.7.7.1 c: muros no expuestos, 20 mm'),
           'escalera': (0.020, 0.020, 'C.7.7.1 c: losas no expuestas, 20 mm'),
           'arranque_columna': (0.050, 0.050, 'C.7.7.1 b: concreto expuesto al suelo, 50 mm (N.º 6 a 18)'),
           'arranque_muro': (0.040, 0.040, 'C.7.7.1 b: concreto expuesto al suelo, 40 mm (N.º 5 o menores) y 50 mm (N.º 6 a 18)'),
           'pilote': (0.075, 0.075, 'C.7.7.1 a: concreto vaciado contra el suelo, 75 mm'),
           'dado': (0.050, 0.050, 'C.7.7.1 b: 50 mm expuesto al suelo; el fondo va sobre solado de limpieza (presupuesto, ítem 2.06)'),
           'viga_amarre': (0.040, 0.050, 'C.7.7.1 b: 40 mm (N.º 5 o menores) expuesto al suelo; 50 mm sobre el solado (ítem 2.06)'),
           'foso': (0.040, 0.050, 'C.7.7.1 b: muros expuestos al suelo 40 mm (N.º 5 o menores); losa de fondo sobre solado 50 mm'),
           'cisterna': (0.050, 0.050, 'C.7.7.1 b y C.23 (por confirmar): 50 mm en muros y fondo contra el suelo y el agua'),
           'contrapiso': (0.040, 0.040, 'losa sobre el terreno con base granular (C.7.7.1 b, por confirmar)'),
           'muro_contencion': (0.040, 0.040, 'C.7.7.1 b: concreto expuesto al suelo o a la intemperie, 40 mm (N.º 5 o menores)')}


def causa_fuera(h, p, coh):
    """Por qué una barra sale del concreto y de quién es: de un insumo que no cuadra (A) o del dibujo del modelo (F)."""
    th = tipo_host(h)
    if th == 'viga_amarre' and h['id'] in coh['vigas_amarre_altas']:
        return ('la viga de amarre no llega al dado (su fondo queda sobre la cara superior del dado, ver «coherencia de la '
                'cimentación»), así que su anclaje no tiene concreto.', 'A',
                'Bajar la viga de amarre para que entre al dado (o subir los dados); entonces el anclaje queda dentro del dado.')
    if th == 'viga_amarre' and h['id'] in coh.get('vigas', {}):
        v = coh['vigas'][h['id']]
        for lado in ('desde', 'hasta'):
            d = coh['dados'].get(v[lado])
            if d and d['x0'] - 0.6 <= p[0] <= d['x1'] + 0.6 and d['y0'] - 0.6 <= p[1] <= d['y1'] + 0.6 and p[2] > d['z_tope']:
                return (f'la viga de amarre entra solo {(d["z_tope"] - (v["z_tope"] - v["h"])) * 100:.0f} cm en {d["id"]} (su cara superior '
                        f'está a {d["z_tope"]:.2f} m y la viga va de {v["z_tope"] - v["h"]:.2f} a {v["z_tope"]:.2f} m): sus barras llegan '
                        'al dado por encima de él y el anclaje no tiene concreto.', 'A',
                        f'Bajar la viga de amarre o subir la cara superior de {d["id"]} para que las barras se anclen dentro del dado.')
    if th == 'losa' and h.get('apoyos_sin_estructura'):
        a, b = limites_caja(h)
        if not (a[0] - 0.01 <= p[0] <= b[0] + 0.01 and a[1] - 0.01 <= p[1] <= b[1] + 0.01):
            return ('las barras de los nervios pasan el borde de la losa que no tiene viga ni muro (ver «coherencia de la '
                    'estructura»): del otro lado no hay nervio que las reciba.', 'A',
                    'Agregar la viga de borde que falta en ese eje; con ella las barras se anclan en la viga.')
    if th == 'viga' and h['id'].startswith('VA-'):
        return ('la viga banda es más ancha que el muro donde se ancla: las barras de los lados no tienen concreto para su '
                'longitud de desarrollo.', 'A',
                'Angostar la viga banda en el apoyo al espesor del muro (o anclar esas barras con gancho dentro del muro y la columna).')
    return ('el dibujo de la barra en el modelo se sale del elemento.', 'F', 'Corregir el anclaje o la cota de la barra en el despiece del modelo.')


def limites_caja(e):
    bs = [(a, b) for (a, b, _t) in partes(e['geometria'])]
    return [min(q[0][i] for q in bs) for i in range(3)], [max(q[1][i] for q in bs) for i in range(3)]


def refuerzo(M, E, Rg, solidos, coherencia_insumos=None):
    coherencia_insumos = coherencia_insumos or {'vigas_amarre_altas': set()}
    refs = M['refuerzo']
    host = {e['id']: e for e in M['elementos']}
    resumen = {}
    # ---------------------------------------------------------------- 6. separación libre entre barras paralelas
    req_comp = lambda db: max(1.5 * db, 0.040, 4 / 3 * AGREGADO)  # noqa: E731
    req_gen = lambda db: max(db, 0.025, 4 / 3 * AGREGADO)  # noqa: E731
    por_host = {}
    for j in refs:
        if any(k in j['rol'] for k in ('estribo', 'gancho', 'espiral', 'piel', 'reparticion', 'riostra')):
            continue
        por_host.setdefault(j['host'], []).append(j)
    sep_rev = 0
    for hid in sorted(por_host):
        h = host[hid]
        a0, a1 = None, None
        for (a, b, _t) in partes(h['geometria']) if h['geometria'].get('partes', True) else []:
            a0 = list(a) if a0 is None else [min(a0[i], a[i]) for i in range(3)]
            a1 = list(b) if a1 is None else [max(a1[i], b[i]) for i in range(3)]
        if a0 is None:
            continue
        grupos = {}
        for j in por_host[hid]:
            d = direccion(DSP.polilinea(j))
            k = max(range(3), key=lambda i: abs(d[i]))
            grupos.setdefault(k, []).append(j)
        for k, js in grupos.items():
            for fr in (0.3, 0.5, 0.7):
                plano = a0[k] + (a1[k] - a0[k]) * fr
                pts = []
                for j in js:
                    for inst in instancias(j):
                        for p, q in zip(inst, inst[1:]):
                            if (p[k] - plano) * (q[k] - plano) <= 0 and abs(q[k] - p[k]) > 1e-9:
                                d = [(q[i] - p[i]) for i in range(3)]
                                if abs(d[k]) / math.sqrt(sum(x * x for x in d)) < 0.9:
                                    continue
                                t = (plano - p[k]) / (q[k] - p[k])
                                pts.append(([p[i] + t * d[i] for i in range(3)], j['db'], j['id'], j['rol'], j['num']))
                                break
                sep_rev += len(pts)
                peor = None
                for i in range(len(pts)):
                    for jj in range(i + 1, len(pts)):
                        p1, d1, s1, r1, n1 = pts[i]
                        p2, d2, s2, r2, n2 = pts[jj]
                        if ('malla' in r1) != ('malla' in r2):
                            continue                          # la malla se amarra a las barras: se revisa solo entre mallas
                        libre = math.dist(p1, p2) - (d1 + d2) / 2
                        if libre < -TOL_BARRA:
                            if (hid, 'sup') not in resumen:
                                resumen[(hid, 'sup')] = True
                                Rg.add('barras superpuestas', 'dura', [hid, s1, s2], [(p1[q] + p2[q]) / 2 for q in range(3)],
                                       f'En {_min(h["nombre"])} dos barras paralelas ocupan el mismo espacio ({-libre * 1000:.0f} mm).',
                                       'Correr una de las dos en el despiece del modelo.', 'F', medida={'superposicion_mm': r(-libre * 1000, 1)})
                            continue
                        if libre < 0.0015 and n1 == n2:
                            continue                          # traslapo de contacto (C.12.14.2.1)
                        dbm = max(d1, d2)
                        comp = any(r_.startswith(COMPRESION) for r_ in (r1, r2)) and tipo_host(h) in ('columna', 'arranque_columna', 'muro', 'pilote')
                        req = req_comp(dbm) if comp else req_gen(dbm)
                        if libre < req - 0.001 and (peor is None or libre - req < peor[0]):
                            peor = (libre - req, libre, req, p1, p2, s1, s2, comp)
                if peor:
                    _, libre, req, p1, p2, s1, s2, comp = peor
                    clave = (hid, 'sep')
                    if clave in resumen:
                        continue
                    resumen[clave] = True
                    Rg.add('separación libre entre barras', 'media' if libre >= 0.02 else 'dura', [hid, s1, s2],
                           [(p1[i] + p2[i]) / 2 for i in range(3)],
                           f'En {_min(h["nombre"])} la separación libre entre barras paralelas es {libre * 1000:.0f} mm; '
                           f'la NSR-10 pide {req * 1000:.0f} mm ({"1,5·db y 40 mm en elementos a compresión" if comp else "db y 25 mm"}, '
                           f'y 4/3 del agregado de {AGREGADO * 1000:.0f} mm).',
                           'Repartir las barras en paquetes de dos (C.7.6.6) o usar menos barras de mayor diámetro con la misma área.', 'A',
                           medida={'libre_mm': r(libre * 1000, 1), 'minimo_mm': r(req * 1000, 1)},
                           norma='NSR-10 C.7.6.1, C.7.6.3 y C.3.3.2 (por confirmar)')
    # ---------------------------------------------------------------------------------- 7 y 9. recubrimiento y dentro
    idx = Indice([(a, b, t) for (a, b, t, _eid) in solidos])
    rec_min = {}
    fuera = {}
    for j in refs:
        h = host[j['host']]
        th = tipo_host(h)
        if 'param' in j and h['geometria'].get('tipo') == 'cilindro':
            # espiral: el recubrimiento se mide con la hélice (radio del eje + db/2 frente al radio del pilote), no con la
            # polilínea que la dibuja
            cov = h['geometria']['radio'] - (j['param']['radio'] + j['db'] / 2)
            req_lat, _rf, cita = REC_MIN.get(th, (0.0, 0.0, ''))
            if cov < req_lat - 0.001:
                cx, cy = j['param']['centro']
                rec_min[j['id']] = (cov, req_lat, [cx + j['param']['radio'], cy, j['param']['tramos'][0]['z1']], 'radial', cita)
            continue
        hp = [(a, b, t) for (a, b, t) in partes(h['geometria'])] if h['geometria'].get('partes', True) else []
        if h['clase'] in ('IfcStair', 'IfcElementAssembly'):
            hp = [(a, b, t) for pid in h.get('partes', []) for (a, b, t) in partes(host[pid]['geometria'])]
        d = direccion(DSP.polilinea(j))
        kmain = max(range(3), key=lambda i: abs(d[i])) if 'estribo' not in j['rol'] and 'gancho' not in j['rol'] else None
        if kmain is None and len(j['copias']) > 1:
            c0, c1 = j['copias'][0], j['copias'][-1]
            dd = [c1[i] - c0[i] for i in range(3)]
            kmain = max(range(3), key=lambda i: abs(dd[i]))
        cops = j['copias']
        sel = {0, len(cops) - 1}
        for k in range(3):
            sel.add(min(range(len(cops)), key=lambda q: cops[q][k]))
            sel.add(max(range(len(cops)), key=lambda q: cops[q][k]))
        pl = DSP.polilinea(j)
        paso = max(1, len(pl) // 24)
        muestra = pl[::paso] + [pl[-1]]
        rad = j['db'] / 2
        for qi in sorted(sel):
            c = cops[qi]
            for p0 in muestra:
                p = [p0[i] + c[i] for i in range(3)]
                dentro = idx.en(p, 0.003)
                if not dentro:
                    # distancia al concreto más cercano (para el informe)
                    best = None
                    for i in idx.cerca([p[0] - 1, p[1] - 1, 0], [p[0] + 1, p[1] + 1, 0]):
                        a, b, _t = idx.cajas[i]
                        dd = math.sqrt(sum(max(a[k] - p[k], 0, p[k] - b[k]) ** 2 for k in range(3)))
                        best = dd if best is None else min(best, dd)
                    f = fuera.setdefault(j['id'], [0, 0.0, p])
                    f[0] += 1
                    if best is None or best > f[1]:
                        f[1] = best if best is not None else 9.9
                        f[2] = p
                    continue
                for (a, b, t) in hp:
                    if not all(a[k] - 0.003 <= p[k] <= b[k] + 0.003 for k in range(3)):
                        continue
                    req_lat, req_fondo, cita = REC_MIN.get(th, (0.0, 0.0, ''))
                    caras = []
                    if t == 'cilindro':
                        cx, cy, R_ = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (b[0] - a[0]) / 2
                        caras.append(('radial', R_ - math.hypot(p[0] - cx, p[1] - cy), req_lat, None))
                    else:
                        for k in range(3):
                            if k == kmain:
                                continue
                            caras.append((f'{"xyz"[k]}-', p[k] - a[k], req_fondo if k == 2 else req_lat, (k, -1)))
                            caras.append((f'{"xyz"[k]}+', b[k] - p[k], req_lat, (k, 1)))
                    for nombre, dist, req, eje in caras:
                        cov = dist - rad
                        if cov >= req - 0.001:
                            continue
                        if eje is not None:
                            k, sg = eje
                            probe = list(p)
                            probe[k] += sg * (dist + 0.01)
                            if idx.en(probe, 0.0):
                                continue                   # cara contra otro concreto: no es recubrimiento
                        q = rec_min.get(j['id'])
                        if q is None or cov < q[0]:
                            rec_min[j['id']] = (cov, req, p, nombre, cita)
                    break
    por_j = {x['id']: x for x in refs}
    for sid, (cov, req, p, cara, cita) in sorted(rec_min.items()):
        j = por_j[sid]
        h = host[j['host']]
        th = tipo_host(h)
        # si el recubrimiento que especifica el prediseño ya cumple la NSR-10, lo que falta viene del dibujo del modelo (F);
        # si no, del prediseño (A)
        espec = REC_ESPEC.get(th)
        modelo = espec is None or espec >= req - 0.001
        resp = 'F' if modelo else 'A'
        Rg.add('recubrimiento', 'dura' if cov < req - 0.010 else 'media', [j['host'], sid], p,
               f'«{j["etiqueta"]}» en {_min(h["nombre"])} queda con {cov * 1000:.0f} mm de recubrimiento en la cara {cara}; '
               f'la NSR-10 pide {req * 1000:.0f} mm para esa exposición'
               + (f' y el prediseño especifica {espec * 1000:.0f} mm: la diferencia es del dibujo del modelo.' if modelo and espec is not None
                  else '.' if modelo else f'; el prediseño especifica {espec * 1000:.0f} mm.'),
               ('Corregir la posición de la barra en el despiece del modelo (o la geometría del elemento que la aloja).' if modelo else
                'Aumentar el recubrimiento especificado del elemento (prediseño) o proteger la cara.'), resp,
               medida={'recubrimiento_mm': r(cov * 1000, 1), 'minimo_mm': r(req * 1000, 1),
                       'especificado_mm': r(espec * 1000, 1) if espec is not None else None},
               norma=f'NSR-10 {cita} (por confirmar)')
    for sid, (n, dmax, p) in sorted(fuera.items()):
        j = por_j[sid]
        h = host[j['host']]
        causa, resp, prop = causa_fuera(h, p, coherencia_insumos)
        Rg.add('refuerzo fuera del concreto', 'dura' if dmax > 0.02 else 'media', [j['host'], sid], p,
               f'«{j["etiqueta"]}» de {_min(h["nombre"])} sale del concreto (hasta {dmax * 100:.0f} cm, {n} puntos de la muestra): {causa}',
               prop, resp, medida={'fuera_m': r(dmax, 3), 'puntos': n})
    return {'puntos_de_separacion': sep_rev, 'juegos_con_recubrimiento_corto': len(rec_min), 'juegos_fuera_del_concreto': len(fuera)}


def choques_barras(M, E, Rg):
    """8. Barras que se cruzan: rejilla de 0,5 m sobre las cajas de cada barra; distancia entre segmentos."""
    refs = M['refuerzo']
    celda = 0.5
    inst = []                     # (juego, copia, segmentos, caja0, caja1)
    formas = {}
    for si, j in enumerate(refs):
        pl = DSP.polilinea(j)
        segs = list(zip(pl, pl[1:]))
        a = [min(p[i] for p in pl) - j['db'] / 2 for i in range(3)]
        b = [max(p[i] for p in pl) + j['db'] / 2 for i in range(3)]
        formas[si] = (segs, a, b)
        for ci, c in enumerate(j['copias']):
            inst.append((si, ci, [a[i] + c[i] for i in range(3)], [b[i] + c[i] for i in range(3)]))
    grid = {}
    for ii, (si, ci, a, b) in enumerate(inst):
        for gx in range(int(math.floor(a[0] / celda)), int(math.floor(b[0] / celda)) + 1):
            for gy in range(int(math.floor(a[1] / celda)), int(math.floor(b[1] / celda)) + 1):
                for gz in range(int(math.floor(a[2] / celda)), int(math.floor(b[2] / celda)) + 1):
                    grid.setdefault((gx, gy, gz), []).append(ii)
    host = [j['host'] for j in refs]
    rol = [j['rol'] for j in refs]
    grupo = [j.get('grupo', j['host']) for j in refs]
    pares = set()
    for cel in grid.values():
        if len(cel) < 2:
            continue
        for x in range(len(cel)):
            i1 = cel[x]
            s1, _, a1, b1 = inst[i1]
            for y in range(x + 1, len(cel)):
                i2 = cel[y]
                s2, _, a2, b2 = inst[i2]
                if s1 == s2:
                    continue
                if a1[0] > b2[0] or a2[0] > b1[0] or a1[1] > b2[1] or a2[1] > b1[1] or a1[2] > b2[2] or a2[2] > b1[2]:
                    continue
                pares.add((i1, i2) if i1 < i2 else (i2, i1))
    agrupado = {}
    for i1, i2 in sorted(pares):
        s1, c1, _, _ = inst[i1]
        s2, c2, _, _ = inst[i2]
        j1, j2 = refs[s1], refs[s2]
        o1, o2 = j1['copias'][c1], j2['copias'][c2]
        r12 = (j1['db'] + j2['db']) / 2
        mejor = None
        for p, q in formas[s1][0]:
            P = [p[i] + o1[i] for i in range(3)]
            Q = [q[i] + o1[i] for i in range(3)]
            lo = [min(P[i], Q[i]) - r12 for i in range(3)]
            hi = [max(P[i], Q[i]) + r12 for i in range(3)]
            dP = [Q[i] - P[i] for i in range(3)]
            LP = math.sqrt(sum(x * x for x in dP)) or 1.0
            for u, v in formas[s2][0]:
                U = [u[i] + o2[i] for i in range(3)]
                V = [v[i] + o2[i] for i in range(3)]
                if min(U[0], V[0]) > hi[0] or max(U[0], V[0]) < lo[0] or min(U[1], V[1]) > hi[1] or max(U[1], V[1]) < lo[1] \
                        or min(U[2], V[2]) > hi[2] or max(U[2], V[2]) < lo[2]:
                    continue
                dU = [V[i] - U[i] for i in range(3)]
                LU = math.sqrt(sum(x * x for x in dU)) or 1.0
                if abs(sum(dP[i] * dU[i] for i in range(3))) / (LP * LU) > 0.985:
                    continue          # paralelas: traslapos y continuidad; su separación la revisa el punto 6
                d, pos = dist_seg(P, Q, U, V)
                if mejor is None or d < mejor[0]:
                    mejor = (d, pos)
        if mejor is None:
            continue
        pen = r12 - mejor[0]
        if pen <= TOL_BARRA:
            continue
        mismo = grupo[s1] == grupo[s2]
        amarre = ('estribo', 'gancho', 'espiral')
        if mismo and (rol[s1].startswith(amarre) or rol[s2].startswith(amarre)) and pen <= 0.0065:
            continue                  # barra en el doblez del estribo o del gancho que la amarra (asiento de diseño)
        clave = tuple(sorted([(grupo[s1], rol[s1]), (grupo[s2], rol[s2])]))
        g = agrupado.setdefault(clave, {'n': 0, 'pen': 0.0, 'pos': None, 'juegos': set(), 'hosts': set()})
        g['n'] += 1
        g['juegos'] |= {j1['id'], j2['id']}
        g['hosts'] |= {host[s1], host[s2]}
        if pen > g['pen']:
            g['pen'], g['pos'] = pen, mejor[1]
    for ((h1, r1), (h2, r2)), g in sorted(agrupado.items()):
        sev = 'media'                 # en el detallado o en obra se corre una de las barras hasta un diámetro
        Rg.add('barras que se cruzan', sev, sorted(g['hosts']) + sorted(g['juegos'])[:6], g['pos'],
               f'{g["n"]} cruce(s) entre {r1.replace("_", " ")} de {h1} y {r2.replace("_", " ")} de {h2}: las barras se meten '
               f'hasta {g["pen"] * 1000:.0f} mm una en otra.',
               'Correr una de las capas en el detallado (en obra se desplazan hasta un diámetro) o ajustar la posición en el despiece.',
               'A y F', medida={'penetracion_max_mm': r(g['pen'] * 1000, 1), 'cruces': g['n']}, casos=g['n'],
               norma='NSR-10 C.7.5 (colocación del refuerzo) y C.7.6 (por confirmar)')
    return {'instancias': len(inst), 'parejas_revisadas': len(pares), 'grupos_con_cruces': len(agrupado)}


# ======================================================================================== 9b. pilotes en sus dados
def pilotes_en_dados(M, E, est, Rg):
    """Cada pilote dentro de su dado con la distancia al borde del prediseño (del centro del pilote a la cara del dado,
    D/2 + 0,15 m) y las barras del pilote que entran al dado con el recubrimiento del dado."""
    dados = {d['id']: d for d in est['cimentacion']['dados']}
    rec_d = REC_ESPEC.get('dado', 0.075)
    barras = {}
    for j in M['refuerzo']:
        if j['rol'] == 'longitudinal_superior':
            barras.setdefault(j['host'], []).append(j)
    n = 0
    for e in M['elementos']:
        if e['clase'] != 'IfcPile' or e.get('grupo') not in dados:
            continue
        d = dados[e['grupo']]
        n += 1
        g = e['geometria']
        cx, cy = g['centro']
        Rp = g['radio']
        caras = {'x0': cx - d['x0'], 'x1': d['x1'] - cx, 'y0': cy - d['y0'], 'y1': d['y1'] - cy}
        lado = min(caras, key=caras.get)
        borde = caras[lado]
        req_b = Rp + 0.15
        cov = None
        for j in barras.get(e['id'], []):
            for c in j['copias']:
                x, y = j['forma'][0][0] + c[0], j['forma'][0][1] + c[1]
                q = min(x - d['x0'], d['x1'] - x, y - d['y0'], d['y1'] - y) - j['db'] / 2
                cov = q if cov is None else min(cov, q)
        if borde >= req_b - 0.001 and (cov is None or cov >= rec_d - 0.001):
            continue
        k = 0 if lado[0] == 'x' else 1
        ps = [q['geometria']['centro'][k] for q in M['elementos'] if q['clase'] == 'IfcPile' and q.get('grupo') == d['id']]
        L_nec = max(ps) - min(ps) + 2 * req_b
        L_act = (d['x1'] - d['x0']) if k == 0 else (d['y1'] - d['y0'])
        txt = (f'El {_min(e["nombre"])} sobresale {(Rp - borde) * 100:.1f} cm de la cara de {d["id"]}' if borde < Rp else
               f'El {_min(e["nombre"])} queda con su cara a {(borde - Rp) * 100:.1f} cm de la cara de {d["id"]}')
        txt += (f' (el prediseño pide 15 cm: centro a cara {req_b:.2f} m y aquí hay {borde:.3f} m)'
                + (f'; las barras del pilote que entran al dado quedan con {cov * 1000:.0f} mm de recubrimiento lateral (el dado pide '
                   f'{rec_d * 1000:.0f} mm)' if cov is not None and cov < rec_d - 0.001 else '') + '.')
        Rg.add('pilote fuera del dado', 'dura', [e['id'], d['id']], [cx, cy, d['z_fondo'] + 0.3], txt,
               f'Centrar el dado en el grupo de pilotes (y no en la columna) o agrandarlo de {L_act:.2f} a {L_nec:.2f} m en {"x" if k == 0 else "y"} '
               '(prediseño).', 'A',
               medida={'centro_a_cara_m': r(borde, 3), 'minimo_m': r(req_b, 3), 'recubrimiento_barras_mm': r(cov * 1000, 1) if cov is not None else None,
                       'ancho_necesario_m': r(L_nec, 3), 'ancho_del_dado_m': r(L_act, 3)},
               norma='NSR-10 C.15 y H.4 (distancia al borde de los pilotes, por confirmar) y C.7.7.1 a (75 mm)')
    return {'pilotes_revisados': n}


# ================================================================================================= 10. coherencia
def coherencia(M, E, est, pl, Rg):
    C = est['cimentacion']
    dados = {d['id']: d for d in C['dados']}
    n = 0
    # vigas de amarre: su fondo frente a la cara superior de los dados que une
    for v in C['vigas_amarre']:
        n += 1
        fondo = v['z_tope'] - v['h']
        for lado in ('desde', 'hasta'):
            d = dados[v[lado]]
            if fondo > d['z_tope'] + 1e-6:
                Rg.add('coherencia de la cimentación', 'dura', [v['id'], d['id']],
                       [v['tramo'][0] if lado == 'desde' else v['tramo'][1], v['coordenada'], (fondo + d['z_tope']) / 2] if v['direccion'] == 'x'
                       else [v['coordenada'], v['tramo'][0] if lado == 'desde' else v['tramo'][1], (fondo + d['z_tope']) / 2],
                       f'La viga de amarre {v["id"]} (fondo a {fondo:.2f} m) termina en la cara de {d["id"]} pero queda '
                       f'{(fondo - d["z_tope"]) * 100:.0f} cm por encima de su cara superior ({d["z_tope"]:.2f} m): no se apoya en el dado y su '
                       'anclaje (ldh con gancho) queda fuera del concreto.',
                       'Bajar la viga de amarre para que entre al dado (fondo bajo la cara superior del dado) o subir los dados; '
                       'o prolongarla hasta el arranque de la columna.', 'A',
                       medida={'fondo_viga_m': r(fondo, 3), 'tope_dado_m': d['z_tope'], 'separacion_m': r(fondo - d['z_tope'], 3)},
                       norma='NSR-10 C.15.13 (vigas de amarre, por confirmar)')
                break
    # muros de contención: el muro entero sobre su apoyo (dado o viga de amarre) para anclar sus verticales
    for m in C.get('muros_contencion') or []:
        sup = DSP.apoyo_continuo(C, m)
        x0, x1 = m['tramo']
        fuera = [(lado, q) for lado, q in (('occidental', (sup[0] - x0) if sup else x1 - x0), ('oriental', (x1 - sup[1]) if sup else 0.0)) if q > 0.005]
        for lado, q in fuera:
            xe = x0 if lado == 'occidental' else x1
            ap = m['sobre']
            cara = (f'x = {sup[0] if lado == "occidental" else sup[1]:.2f}'.replace('.', ',')) if sup else 'sin apoyo'
            Rg.add('coherencia de la cimentación', 'media', [m['id'], ap], [xe, sum(m['y']) / 2, m['z_fondo']],
                   f'El extremo {lado} del muro de contención {m["id"]} pasa {q * 100:.0f} cm la cara de su apoyo ({ap}, {cara}): '
                   'ese tramo queda sobre el relleno y sus barras verticales no tienen dónde anclarse (el modelo reparte las verticales '
                   'sobre el dado).',
                   f'Alargar {ap} {q * 100:.0f} cm hacia ese lado o terminar el muro en la cara del dado y cerrar el borde del pasaje '
                   'de otra forma (prediseño y arquitectura).', 'A',
                   medida={'fuera_del_apoyo_m': r(q, 3)}, norma='NSR-10 C.14.3, C.15 y título H (estructuras de contención); numerales por confirmar')
    # esquinas de los núcleos sin concreto (muros que se encuentran en L): el alma en x arranca en la cara del muro en y
    muros = [m for m in est['refuerzo']['muros'] if m['nivel'] == 1]
    todos = [rr for m in muros for rr in m['planta']]
    for mx in [m for m in muros if m['direccion'] == 'x']:
        for my in [m for m in muros if m['direccion'] == 'y']:
            for q in mx['planta']:
                for w in my['planta']:
                    if abs(q[0] - w[2]) < 1e-6 and (abs(q[1] - w[3]) < 1e-6 or abs(q[3] - w[1]) < 1e-6):
                        esq = [w[0], q[1], w[2], q[3]]
                        if any(abs(z[0] - esq[0]) < 1e-6 and abs(z[1] - esq[1]) < 1e-6 and abs(z[2] - esq[2]) < 1e-6 for z in todos):
                            continue
                        Rg.add('coherencia de la estructura', 'dura', [mx['muro'], my['muro']], [(esq[0] + esq[2]) / 2, (esq[1] + esq[3]) / 2, 2.0],
                               f'La esquina entre los muros {mx["muro"]} y {my["muro"]} ({esq[2] - esq[0]:.2f} × {esq[3] - esq[1]:.2f} m) no es de '
                               'ningún muro: queda sin concreto en todos los pisos y sus barras horizontales no se cruzan.',
                               'Asignar la esquina a uno de los dos muros y anclar ahí las horizontales de ambos (son '
                               f'≈ {(esq[2] - esq[0]) * (esq[3] - esq[1]) * 17.1:.1f} m³ en la altura de la torre).', 'A',
                               medida={'esquina': rp(esq, 3)}, norma='NSR-10 C.21.9.6 y C.21.9.2 (por confirmar)')
    # bordes de losa sin viga ni muro estructural
    for e in M['elementos']:
        for s_ in e.get('apoyos_sin_estructura') or []:
            Rg.add('coherencia de la estructura', 'media', [e['id']], None,
                   f'El borde {s_["borde"]} de la losa {e["id"]} no tiene viga ni muro estructural en {s_["largo_m"] - s_["apoyado_m"]:.2f} m de '
                   f'sus {s_["largo_m"]:.2f} m: los nervios se apoyarían en mampostería.',
                   'Agregar una viga de borde en ese eje o apoyar los nervios en el muro estructural más cercano.', 'A',
                   medida=s_, norma='NSR-10 C.8.13 (por confirmar)')
    # cisternas frente al bloque técnico
    bt = next(n_ for n_ in pl['niveles'] if n_['id'] == 'BT')
    for c in C['cisternas']:
        tope = c['z_fondo'] + c['losa_fondo_e_m'] + c['h_interior_m'] + c['losa_tapa_e_m']
        if abs(tope - bt['z']) > 0.05:
            Rg.add('coherencia de la cimentación', 'media', [c['id'], 'BT'], [(c['x'][0] + c['x'][1]) / 2, (c['y'][0] + c['y'][1]) / 2, tope],
                   f'La tapa de las cisternas queda a {tope:.2f} m y el patio del bloque técnico está a {bt["z"]:.2f} m: '
                   f'{(tope - bt["z"]) * 100:.0f} cm de diferencia.',
                   'Fijar una sola cota: si el patio queda a −1,50 m, bajar las cisternas 1,50 m (revisar la subpresión); si no, ajustar el bloque técnico.',
                   'A y B', medida={'tapa_m': r(tope, 3), 'patio_m': bt['z']})
    # parrillas de los dados: el área de acero dibujada (las barras que caben en el ancho útil) frente al As requerido de A
    for e in M['elementos']:
        pdib = e.get('parrillas_dibujadas')
        if not pdib:
            continue
        d = dados.get(e['id'])
        for eje in ('x', 'y'):
            q = pdib.get(f'inferior_{eje}')
            req = (q or {}).get('As_req_mm2')
            if not q or not req:
                continue
            falta = (req - q['As_dibujada_mm2']) / req
            nA = q.get('n_A')
            AsA = nA * DSP.BARRAS[q['num']][1] if nA else None
            if falta <= 1e-6 and (AsA is None or AsA >= req - 1e-6):
                continue
            Rg.add('coherencia del despiece', 'dura' if falta > 0.05 else 'media', [e['id']],
                   [(d['x0'] + d['x1']) / 2, (d['y0'] + d['y1']) / 2, d['z_fondo']],
                   f'La parrilla inferior en {eje} del dado {e["id"]} lleva {q["n_dibujadas"]} N.º {q["num"]} '
                   f'({q["As_dibujada_mm2"]:.0f} mm²) y el prediseño requiere {req:.0f} mm²: faltan {max(falta, 0) * 100:.1f} %'
                   + (f'. El prediseño indica {nA} barras ({AsA:.0f} mm²)' if nA else '') + f' a {q["s_A_m"]:.3f} m'
                   + (f'; {q["ajuste"]}' if q.get('ajuste') else '') + '.',
                   f'Aumentar el diámetro (N.º {q["num"] + 1}) o el número de barras de la parrilla hasta {req:.0f} mm² (prediseño).', 'A',
                   medida={'As_dibujada_mm2': q['As_dibujada_mm2'], 'As_req_mm2': req, 'faltante_pct': r(100 * max(falta, 0), 1),
                           'n_prediseno': nA, 'n_dibujadas': q['n_dibujadas'], 's_prediseno_m': q['s_A_m'], 's_dibujada_m': q['s_dibujada_m']},
                   norma='NSR-10 C.15.4 y C.10.5 (flexión del dado, por confirmar)')
    # estribos: conteo y paso del modelo frente a los juegos de A (verificación de generar_bim). A cuenta los de cada zona
    # (el centro desde el último estribo de la zona confinada, n = ⌈hueco/s⌉ − 1) y los del nudo a s_lo; no cuenta los que
    # el modelo tenga que agregar en el nudo cuando, al correrlos fuera de las barras de las vigas, no hay sitio para
    # mantener el paso s_lo con los suyos (criterio acordado en la revisión A7): esos van aparte, con su peso
    V = M.get('verificacion_estribos') or {}
    extra_nudos = {}
    for tipo, nom, s_zona in (('columnas', 'columnas', 's_lo_m'), ('vigas', 'vigas', 's_2h_m')):
        filas = V.get(tipo) or {}
        mas = {k: x['juegos_estribos'] - x.get('estribos_extra_nudo', 0) - x['juegos_A'] for k, x in filas.items()
               if x['juegos_estribos'] - x.get('estribos_extra_nudo', 0) != x['juegos_A']}
        if tipo == 'columnas':
            extra_nudos = {k: x['estribos_extra_nudo'] for k, x in filas.items() if x.get('estribos_extra_nudo')}
        if mas:
            ej = max(mas, key=lambda k: (abs(mas[k]), k))
            Rg.add('coherencia del despiece', 'media', sorted(mas)[:12], None,
                   f'En {len(mas)} de {len(filas)} {nom} el modelo y el prediseño no cuentan los mismos estribos '
                   f'({sum(mas.values()):+d} en total, sin los que el modelo agrega en los nudos; p. ej. {ej}: '
                   f'{filas[ej]["juegos_estribos"] - filas[ej].get("estribos_extra_nudo", 0)} frente a {filas[ej]["juegos_A"]}). '
                   'Los dos deben repartir el centro desde el último estribo de cada zona confinada (n = ⌈hueco/s⌉ − 1).',
                   'Revisar el conteo de estribos del prediseño frente al reparto del modelo.', 'A',
                   medida={'elementos': len(mas), 'estribos_de_diferencia': sum(mas.values())}, norma='NSR-10 C.21.3.4 y C.21.3.5 (por confirmar)')
        malos = {k: x for k, x in filas.items() if x['paso_max_m'] > x['s_centro_m'] + 1e-4 or
                 x.get('paso_max_lo_m', x.get('paso_max_2h_m', 0.0)) > x[s_zona] + 1e-4 or
                 x.get('paso_max_nudo_m', 0.0) > x.get('s_lo_m', 9.9) + 1e-4}
        for k, x in sorted(malos.items()):
            Rg.add('coherencia del despiece', 'dura', [k], None,
                   f'En {k} el paso de los estribos llega a {max(x["paso_max_m"], x.get("paso_max_nudo_m", 0.0)):.3f} m.',
                   'Corregir el reparto de estribos del modelo.', 'F', medida=x)
    kg_extra = 0.0
    if extra_nudos:
        # peso de un juego (estribo y sus ganchos suplementarios) de cada columna por los estribos agregados
        por_juego = {}
        for j in M['refuerzo']:
            if j['host'] in extra_nudos and j['rol'] in ('estribo', 'gancho_suplementario_x', 'gancho_suplementario_y') and j['copias']:
                por_juego.setdefault(j['host'], {}).setdefault(j['rol'], j['kg'] / len(j['copias']))
        kg_extra = sum(sum(por_juego.get(h, {}).values()) * n_ for h, n_ in extra_nudos.items())
    for mid, x in sorted((V.get('cortinas') or {}).items()):
        if x['exceso_h_m'] > 1e-4 or x['exceso_v_m'] > 1e-4:
            Rg.add('coherencia del despiece', 'dura', [mid], None,
                   f'En el muro {mid} el paso de la cortina pasa del de diseño en {max(x["exceso_h_m"], x["exceso_v_m"]) * 1000:.0f} mm.',
                   'Corregir el reparto de la cortina en el modelo.', 'F', medida=x)
    # traslapos de columnas (C.21.6.3.2): las barras de cada piso atraviesan su nudo de arriba y se traslapan en la mitad
    # central de la altura libre del piso de arriba. Se revisa que el traslapo de A quede ahí, que el piso de arriba no
    # lleve más acero que el de abajo (bajo el traslapo su zona confinada de abajo tiene las barras del piso de abajo) y
    # que el peso dibujado siga al de A (A pesa cada barra del traslapo de abajo, o del dado, al de arriba)
    cols = {}
    for c in est['refuerzo']['columnas']:
        cols.setdefault(c['id'].rsplit('-', 1)[0], []).append(c)
    kg_mod = {}
    for j in M['refuerzo']:
        if j['rol'] == 'longitudinal' and j['host'] in E and E[j['host']]['clase'] == 'IfcColumn':
            kg_mod[j['host']] = kg_mod.get(j['host'], 0.0) + j['kg']
    fuera, mas_arriba, lineas, d_kg, kg_A = [], [], 0, {}, {}
    for lin, ps in sorted(cols.items()):
        ps = sorted(ps, key=lambda c: c['nivel'])
        lineas += 1
        for a, b in zip(ps, ps[1:]):
            lap = a['longitudinal']['traslapo']
            if lap:
                ln_b = (b['z1'] - b['z0']) - b['estribos']['nudo']['alto_m']
                q0, q1 = b['z0'] + ln_b / 4, b['z0'] + 3 * ln_b / 4
                z_a, z_b = lap['z_centro'] - lap['largo_m'] / 2, lap['z_centro'] + lap['largo_m'] / 2
                if z_a < q0 - 1e-3 or z_b > q1 + 1e-3:
                    fuera.append((a['id'], r(z_a, 2), r(z_b, 2), r(q0, 2), r(q1, 2)))
            As_a = a['longitudinal']['n'] * DSP.BARRAS[a['longitudinal']['num']][1]
            As_b = b['longitudinal']['n'] * DSP.BARRAS[b['longitudinal']['num']][1]
            if As_b > As_a + 1e-6:
                mas_arriba.append((b['id'], r(As_a, 0), r(As_b, 0)))
        for c in ps:
            if c['id'] in kg_mod:
                d_kg[c['nivel']] = d_kg.get(c['nivel'], 0.0) + kg_mod[c['id']] - c['kg_longitudinal']
                kg_A[c['nivel']] = kg_A.get(c['nivel'], 0.0) + c['kg_longitudinal']
    if fuera:
        Rg.add('coherencia del despiece', 'media', sorted({f_[0] for f_ in fuera})[:12], None,
               f'En {len(fuera)} columnas el traslapo de las barras no queda en la mitad central de la altura libre del piso de '
               f'arriba (p. ej. {fuera[0][0]}: de {fuera[0][1]:.2f} a {fuera[0][2]:.2f} m; la mitad central va de {fuera[0][3]:.2f} '
               f'a {fuera[0][4]:.2f} m). El modelo lo dibuja donde lo pone el prediseño.',
               'Ubicar el traslapo en la mitad central de la altura libre del piso de arriba (C.21.6.3.2).', 'A',
               medida={'columnas': len(fuera)}, norma='NSR-10 C.21.6.3.2 y C.12.17 (por confirmar)')
    if mas_arriba:
        Rg.add('coherencia del despiece', 'media', sorted({m_[0] for m_ in mas_arriba})[:12], None,
               f'En {len(mas_arriba)} tramos de columna el piso de arriba lleva más acero que el de abajo (p. ej. {mas_arriba[0][0]}: '
               f'{mas_arriba[0][2]:.0f} mm² frente a {mas_arriba[0][1]:.0f} mm² abajo): como el traslapo va a media altura del piso de '
               'arriba, su zona confinada de abajo queda con las barras del piso de abajo.',
               'Subir el armado del piso de abajo hasta el del piso de arriba o confirmar que la sección bajo el traslapo basta.', 'A',
               medida={'tramos': len(mas_arriba)}, norma='NSR-10 C.21.6.3.2 y C.10.3 (por confirmar)')
    peor = max(d_kg, key=lambda k_: abs(d_kg[k_]) / max(kg_A.get(k_, 1.0), 1.0)) if d_kg else None
    if peor is not None and abs(d_kg[peor]) > 0.02 * kg_A[peor]:
        Rg.add('coherencia del despiece', 'media', [], None,
               f'El peso de las barras longitudinales de las columnas del piso {peor} en el modelo difiere {d_kg[peor]:+.0f} kg '
               f'({100 * d_kg[peor] / kg_A[peor]:+.1f} %) del que calcula el prediseño.',
               'Revisar el largo de las barras (traslapos, anclajes y ganchos) en el modelo y en el prediseño.', 'F',
               medida={'diferencia_kg_modelo_menos_A_por_piso': {str(k_): r(v_, 0) for k_, v_ in sorted(d_kg.items())}})
    return {'vigas_de_amarre': n,
            'traslapos_columnas': {'lineas': lineas, 'fuera_de_la_mitad_central': len(fuera), 'piso_de_arriba_con_mas_acero': len(mas_arriba),
                                   'diferencia_kg_modelo_menos_A_por_piso': {str(k_): r(v_, 0) for k_, v_ in sorted(d_kg.items())},
                                   'diferencia_pct_por_piso': {str(k_): r(100 * v_ / kg_A[k_], 2) for k_, v_ in sorted(d_kg.items()) if kg_A.get(k_)}},
            'estribos_extra_en_nudos': {'columnas': len(extra_nudos), 'estribos': sum(extra_nudos.values()), 'kg': r(kg_extra, 0),
                                        'criterio': 'se agregan solo cuando, corridos fuera de las barras de las vigas, los estribos '
                                                    'que cuenta el prediseño no caben con el paso de la zona confinada entre las franjas de barras de las vigas'}}


# ========================================================================================================= main
def generar():
    M = leer(ENTRADA)
    est = leer(INSUMOS['estructura'])
    pl = leer(INSUMOS['plantas'])
    E = {e['id']: e for e in M['elementos']}
    Rg = Registro()
    res = {}
    res['unidades_y_puertas'] = unidades_y_puertas(M, E, Rg)
    sol = []
    for e in M['elementos']:
        if e.get('material') in ('concreto_28', 'concreto_21') and e['clase'] not in ('IfcStair', 'IfcElementAssembly'):
            for (a, b, t) in partes(e['geometria']):
                sol.append((a, b, t if t in ('cilindro',) else 'caja', e['id']))
    res['concreto'] = concreto(M, E, Rg)
    res['mamposteria'] = mamposteria(M, E, Rg)
    res['ductos'] = ductos(M, E, pl, Rg)
    res['escaleras'] = escaleras(M, E, Rg)
    REC_ESPEC.clear()
    REC_ESPEC.update(rec_especificado(est))
    dados_ = {d['id']: d for d in est['cimentacion']['dados']}
    altas = {v['id'] for v in est['cimentacion']['vigas_amarre']
             if any(v['z_tope'] - v['h'] > dados_[v[l]]['z_tope'] + 1e-6 for l in ('desde', 'hasta') if v[l] in dados_)}
    res['refuerzo'] = refuerzo(M, E, Rg, sol, {'vigas_amarre_altas': altas, 'dados': dados_,
                                               'vigas': {v['id']: v for v in est['cimentacion']['vigas_amarre']}})
    res['pilotes_en_dados'] = pilotes_en_dados(M, E, est, Rg)
    res['barras'] = choques_barras(M, E, Rg)
    res['coherencia'] = coherencia(M, E, est, pl, Rg)
    orden_sev = {'dura': 0, 'media': 1, 'leve': 2}
    lista = sorted(Rg.lista, key=lambda x: (orden_sev[x['severidad']], x['categoria'], x['elementos'], x['posicion'] or [0, 0, 0]))
    for i, x in enumerate(lista):
        x['id'] = f'INT-{i + 1:04d}'
        x['guids'] = [E[e]['guid'] for e in x['elementos'] if e in E]
        x['nivel'] = nivel_z(x['posicion'][2]) if x['posicion'] else None
    resumen = {}
    for x in lista:
        k = resumen.setdefault(x['categoria'], {'dura': 0, 'media': 0, 'leve': 0, 'casos': 0})
        k[x['severidad']] += 1
        k['casos'] += x['casos']
    por_resp = {}
    for x in lista:
        k = por_resp.setdefault(x['responsable'], {'dura': 0, 'media': 0, 'leve': 0})
        k[x['severidad']] += 1
    pendientes_duras = [x['id'] for x in lista if x['severidad'] == 'dura' and x['estado'] == 'pendiente']
    return {
        'id': 'torre_hospital_interferencias', 'generado_por': 'scripts/bim/interferencias.py', 'fecha': M['fecha'],
        'tipo_dato': 'cálculo propio (detección geométrica sobre el modelo BIM)', 'estado': M['estado'],
        'insumos_sha1': {rel(ENTRADA): sha1(ENTRADA), rel(INSUMOS['estructura']): sha1(INSUMOS['estructura']),
                         rel(INSUMOS['plantas']): sha1(INSUMOS['plantas'])},
        'criterios': {'tolerancia_solidos_m': TOL_SOLIDO, 'tolerancia_barras_m': TOL_BARRA, 'agregado_m': AGREGADO,
                      'altura_libre_escaleras_m': ALTURA_LIBRE, 'severidad': SEVERIDAD,
                      'aceptadas': ['empotramiento de 0,10 m de la cabeza de los pilotes en dados y losas de pilotes (A)',
                                    'barras longitudinales en el doblez de su estribo o gancho (≤ 6,5 mm: asiento de diseño)',
                                    'traslapos de contacto (C.12.14.2.1)']},
        'revisado': res,
        'resumen': {'total': len(lista), 'por_categoria': dict(sorted(resumen.items())), 'por_responsable': dict(sorted(por_resp.items())),
                    'duras_pendientes': len(pendientes_duras)},
        'interferencias': lista,
    }


def main():
    out = generar()
    if '--verificar' in sys.argv:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / 'x.json'
            escribir_json(tmp, out, ('interferencias',))
            igual = SALIDA.exists() and tmp.read_bytes() == SALIDA.read_bytes()
        print('al día' if igual else 'DESACTUALIZADO')
        sys.exit(0 if igual else 1)
    escribir_json(SALIDA, out, ('interferencias',))
    s = out['resumen']
    print(f'{rel(SALIDA)}: {s["total"]} interferencias ({s["duras_pendientes"]} duras pendientes)')
    for k, v in s['por_categoria'].items():
        print(f'  {k}: {v}')
    print('  por responsable:', s['por_responsable'])
    print('  revisado:', out['revisado'])


if __name__ == '__main__':
    main()
