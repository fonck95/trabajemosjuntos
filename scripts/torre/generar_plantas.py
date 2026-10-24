"""Genera la planta de toda la torre (data/edificios/torre_hospital_plantas.json) desde el trazado escrito a mano.

Contrato: data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md, secciones 3 (plantas) y 16 (recorrer TODA la torre:
exteriores, pisos 1 a 4, núcleos con escaleras caminables, bloque técnico y cubierta).

Uso:
  python3 scripts/torre/generar_plantas.py            # escribe el archivo solo si cambió (dos corridas = mismos bytes)
  python3 scripts/torre/generar_plantas.py --verificar # regenera en memoria y sale con 1 si el archivo no está al día

Insumos (todos versionados):
  data/edificios/torre_hospital_trazado.json          el diseño (anteproyecto): rectángulos o polígonos ortogonales de cada
                                                     recinto, puertas, vanos abiertos, núcleos, escaleras y entradas
  data/proyectos/torre_hospital/reglas_planta.json    tipos de muro, mínimos de la Res. 1633, anchos de puerta, zonas,
                                                     accesos permitidos, grupos de color y climatización
  data/proyectos/torre_hospital/programa.json         ambientes (fila, nombre, cantidad, área), huella y núcleos
  data/proyectos/torre_hospital/normas.json           colores de la señalización (Res. 1633) y climatización (Cuadro 4)

Qué deriva (3.3): ids de la regla 1.3, polígonos a ejes y libres, áreas, muros con espesor y lados (uno por borde
compartido; fachadas fundidas por lado), vanos de puertas, ventanas en fachada, columnas de la retícula, núcleos,
conexiones verticales, tramos y descansos de las escaleras con sus cotas, pasos entre niveles y el resumen por nivel.
Solo biblioteca estándar (Python 3.12). Salida determinista (comun.escribir_json; sin fecha del sistema).
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

ORDEN_NIVELES = ('EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB')
NIVELES_PISO = ('P1', 'P2', 'P3', 'P4')
# Tipos de muro que pueden ganar en un borde (el más exigente gana, 3.3). Los de contorno exterior (parapeto,
# cerramiento) y el vano abierto se asignan por regla del nivel o del trazado.
# Niveles donde una puerta de otro nivel que llega allí abre su vano espejo (exteriores a ±0,00: P1 y el pasaje del bloque
# técnico llegan a los patios y a la plaza). En la cubierta, la terraza del piso 3 está 4,20 m abajo: la puerta de la
# escalera sur es del piso 4 y su vano ya está en el muro del núcleo de ese piso.
NIVELES_CON_ESPEJO = ('EXT',)
RANGO = {'abierto': 0, 'liviano': 1, 'bloque': 2, 'parapeto': 2, 'cerramiento': 2, 'fachada': 3, 'nucleo': 4,
         'plomado': 5}
TIPOS_NUCLEO_MURO = ('escalera', 'ascensor', 'montacargas')
TOL = 1e-6


class ErrorTrazado(ValueError):
    pass


# ----------------------------------------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------------------------------------
def r2(v):
    return C.redondear(v, 2)


def r3(v):
    return C.redondear(v, 3)


def pt(v, nd=3):
    return [C.redondear(v[0], nd), C.redondear(v[1], nd)]


def clave_pt(v):
    return (C._k(v[0]), C._k(v[1]))


def clave_seg(a, b):
    ka, kb = clave_pt(a), clave_pt(b)
    return (ka, kb) if ka <= kb else (kb, ka)


def diferencia(p, quitar) -> list[list[float]]:
    """Polígono ortogonal p menos los rectángulos `quitar` (el resultado debe quedar de una pieza y sin huecos)."""
    rects = C.rectangulos_menos(p, quitar, TOL)
    return contorno_de_union([C.rect_a_poligono(list(r)) for r in rects])


def contorno_de_union(poligonos) -> list[list[float]]:
    """Contorno (polígono ortogonal antihorario, sin huecos) de la unión de polígonos ortogonales que se tocan."""
    xs = sorted({C._k(v[0]) for p in poligonos for v in p})
    ys = sorted({C._k(v[1]) for p in poligonos for v in p})
    rects = [r for p in poligonos for r in C.rectangulos(p)]
    nx, ny = len(xs) - 1, len(ys) - 1
    lleno = [[False] * nx for _ in range(ny)]
    for j in range(ny):
        yc = (ys[j] + ys[j + 1]) / 2
        for i in range(nx):
            xc = (xs[i] + xs[i + 1]) / 2
            lleno[j][i] = any(r[0] - TOL <= xc <= r[2] + TOL and r[1] - TOL <= yc <= r[3] + TOL for r in rects)
    sig = {}
    for j in range(ny):
        for i in range(nx):
            if not lleno[j][i]:
                continue
            x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
            if j == 0 or not lleno[j - 1][i]:
                sig.setdefault((x0, y0), []).append((x1, y0))
            if i == nx - 1 or not lleno[j][i + 1]:
                sig.setdefault((x1, y0), []).append((x1, y1))
            if j == ny - 1 or not lleno[j + 1][i]:
                sig.setdefault((x1, y1), []).append((x0, y1))
            if i == 0 or not lleno[j][i - 1]:
                sig.setdefault((x0, y1), []).append((x0, y0))
    if not sig:
        raise ErrorTrazado('contorno vacío')
    inicio = min(sig)
    lazo, actual = [inicio], inicio
    usados = 0
    total = sum(len(v) for v in sig.values())
    while True:
        siguientes = sig.get(actual)
        if not siguientes:
            raise ErrorTrazado('el contorno de la unión no se cierra')
        nxt = siguientes.pop(0)
        usados += 1
        if nxt == inicio:
            break
        lazo.append(nxt)
        actual = nxt
    if usados != total:
        raise ErrorTrazado('la unión de recintos del nivel tiene huecos o partes sueltas')
    return C.orientar_antihorario(C.limpiar_poligono([list(v) for v in lazo]))


# ----------------------------------------------------------------------------------------------------------------------
# Generador
# ----------------------------------------------------------------------------------------------------------------------
class Generador:
    def __init__(self, trazado: dict, programa: dict, reglas: dict, normas: dict, insumos: list[Path]):
        self.tz = trazado
        self.prog = programa
        self.amb = programa['ambientes']
        self.reglas = reglas
        self.normas = normas
        self.insumos = insumos
        self.citas: list[str] = []
        self.errores: list[str] = []
        self.cat_puertas = {p['categoria']: p for p in reglas['puertas']}
        self.re_bloque = re.compile(reglas['muros']['bloque_patron'], re.I)
        self.re_plomado = re.compile(reglas['muros']['plomado_patron'], re.I)
        self.de_paso = {self._fila(ref) for ref in reglas.get('recintos_de_paso', [])}
        self.zonas_nivel = {}

    # ------------------------------------------------------------------------------------------------ referencias
    def _fila(self, ref) -> int:
        try:
            return C.resolver_ambiente(ref, self.amb)
        except C.ErrorAmbiente as e:
            raise ErrorTrazado(str(e)) from None

    def nivel_de_fila(self, fila: int) -> str | None:
        por_fila = self.reglas['niveles']['nivel_por_fila']
        if str(fila) in por_fila:
            return por_fila[str(fila)]
        piso = self.amb[fila].get('piso')
        if isinstance(piso, int):
            return f'P{piso}'
        return self.reglas['niveles']['piso_a_nivel'].get(str(piso))

    def cita(self, texto: str | None) -> str | None:
        if texto and texto not in self.citas:
            self.citas.append(texto)
        return texto

    # ------------------------------------------------------------------------------------------------ recintos
    def grupo(self, servicio: str | None, ambiente: str, fila: int | None, tipo: str, dado: str | None) -> str:
        if dado:
            return dado
        if tipo == 'circulacion':
            return 'circulacion'
        g = self.reglas['servicio_a_grupo']
        for o in g.get('por_fila', []):
            if fila is not None and self._fila(o['ambiente']) == fila:
                return o['grupo']
        return g['por_servicio'].get(servicio or '', 'apoyo_y_servicios_generales')

    def zona_acceso(self, servicio, ambiente, tipo):
        za = self.reglas['zona_acceso']
        for o in za.get('patrones', []):
            if re.search(o['patron'], ambiente or '', re.I):
                return o['zona']
        if tipo == 'circulacion':
            return za.get('circulacion', 'no_restringido')
        return za['por_servicio'].get(servicio or '', za.get('defecto', 'semirrestringido'))

    def climatizacion(self, servicio, ambiente):
        filas = {f['ambiente']: f for f in self.normas['parametros_diseno']['climatizacion_cuadro4']['filas']}
        for o in self.reglas['climatizacion']['patrones']:
            if re.search(o['patron'], f'{ambiente} {servicio or ""}', re.I):
                f = filas.get(o['fila_cuadro4'])
                if f is None:
                    raise ErrorTrazado(f'climatización: «{o["fila_cuadro4"]}» no está en normas.json → climatizacion_cuadro4')
                d = {'presion': f.get('presion'), 'temp_c': f.get('temp_c'), 'hr_pct': f.get('hr_pct')}
                if f.get('cambios_h') is not None:
                    d['cambios_h'] = f['cambios_h']
                if f.get('filtro'):
                    d['filtro'] = f['filtro']
                d['fuente'] = self.cita(f'normas.json → climatizacion_cuadro4 ({o["fila_cuadro4"]}); Res. 1633, Anexo 1, Cuadro 4')
                return d
        return None

    def minimo(self, fila):
        for m in self.reglas['minimos']:
            if self._fila(m['ambiente']) == fila:
                return {'m2': m['m2'], 'lado_m': m.get('lado_m'), 'cita': self.cita(m['cita']), 'tipo_dato': m['tipo_dato']}
        return None

    def espacios(self, N: str, tn: dict) -> list[dict]:
        salida = []
        vistos = set()
        for r in tn['recintos']:
            if 'rect' in r:
                p = C.rect_a_poligono(r['rect'])
            elif 'poligono' in r:
                p = C.orientar_antihorario(C.limpiar_poligono(r['poligono']))
            else:
                raise ErrorTrazado(f'{N}: recinto sin rect ni poligono: {r}')
            for v in p:
                if not (C.es_multiplo(v[0], 0.05) and C.es_multiplo(v[1], 0.05)):
                    raise ErrorTrazado(f'{N}: coordenada que no es múltiplo de 0,05 m en {r}')
            e = {'_p': p, '_t': r}
            if 'fila' in r:
                fila = self._fila(r['fila']) if not isinstance(r['fila'], int) else r['fila']
                a = self.amb[fila]
                if self.nivel_de_fila(fila) != N:
                    raise ErrorTrazado(f'{N}: la fila {fila} («{a["nombre"]}», piso {a.get("piso")!r}) no va en este nivel')
                k = r.get('k', 1)
                e.update(id=C.id_recinto(N, fila, k), fila=fila, k=k, de=a['cantidad'], ambiente=a['nombre'],
                         servicio_programa=a['servicio'], programado=True)
                tipo = r.get('tipo', 'recinto')
            elif 'circ' in r:
                e.update(id=C.id_circulacion(N, r['circ']), ambiente=r['nombre'], programado=False)
                tipo = 'circulacion'
            elif 'tec' in r:
                e.update(id=C.id_tecnico(N, r['tec']), ambiente=r['nombre'], programado=False,
                         servicio_programa=r.get('servicio'))
                tipo = r.get('tipo', 'recinto')
            else:
                raise ErrorTrazado(f'{N}: recinto sin fila, circ ni tec: {r}')
            if e['id'] in vistos:
                raise ErrorTrazado(f'{N}: recinto repetido {e["id"]}')
            vistos.add(e['id'])
            e['tipo'] = tipo
            e['exterior'] = bool(r.get('exterior'))
            e['transitable'] = r.get('transitable', True)
            e['de_paso'] = tipo == 'circulacion' or e.get('fila') in self.de_paso or bool(r.get('de_paso'))
            salida.append(e)
        return salida

    # ------------------------------------------------------------------------------------------------ muros
    def tipo_borde(self, N, tn, e1, e2, nucleo_ids, abiertos, forzados) -> str:
        """Tipo de muro de un borde entre e1 y e2 (e2 None = afuera del contorno)."""
        par = frozenset([e1['id'], e2['id'] if e2 else 'exterior'])
        if par in forzados:
            return forzados[par]
        cands = []
        if e2 is None:
            if e1['exterior']:
                return tn.get('muro_borde_exterior', 'cerramiento')
            cands.append('fachada')
        elif e1['exterior'] and e2['exterior']:
            cands.append('abierto')
        elif e1['exterior'] or e2['exterior']:
            cands.append('fachada')
        else:
            cands.append('liviano')
        for e in (e1, e2):
            if e is None:
                continue
            if self.re_plomado.search(e['ambiente']):
                cands.append('plomado')
            if e['id'] in nucleo_ids:
                cands.append('nucleo')
            if not e['exterior'] and (self.re_bloque.search(f'{e["ambiente"]} {e.get("servicio_programa") or ""}')
                                      or e['_t'].get('muro') == 'bloque'):
                cands.append('bloque')
        t = max(cands, key=lambda x: RANGO[x])
        if par in abiertos:
            if t in ('nucleo', 'plomado', 'fachada'):
                raise ErrorTrazado(f'{N}: no se puede abrir el borde {sorted(par)} (es {t})')
            return 'abierto'
        return t

    def muros(self, N, tn, esp, contorno, nucleo_ids):
        pref = lambda x: x if x == 'exterior' or x.startswith(N + '-') else f'{N}-{x}'
        abiertos = {frozenset(pref(x) for x in par) for par in tn.get('abiertos', [])}
        forzados = {frozenset(pref(x) for x in f['entre']): f['tipo'] for f in tn.get('muros_forzados', [])}
        por_id = {e['id']: e for e in esp}
        cortes = [v for e in esp for v in e['_p']] + list(contorno)
        segs = {}
        for e in esp:
            for a, b in C.bordes(C.partir_bordes(e['_p'], cortes)):
                if math.dist(a, b) <= TOL:
                    continue
                segs.setdefault(clave_seg(a, b), []).append(e['id'])
        elementales = []
        for (ka, kb), ids in segs.items():
            a, b = list(ka), list(kb)
            if len(ids) > 2:
                raise ErrorTrazado(f'{N}: el borde {a}-{b} lo comparten {ids} (traslape)')
            if len(ids) == 1:
                if not C.segmento_en_borde(a, b, contorno):
                    raise ErrorTrazado(f'{N}: el borde {a}-{b} de {ids[0]} no toca otro recinto ni el contorno (hueco)')
                e1, e2 = por_id[ids[0]], None
            else:
                e1, e2 = por_id[ids[0]], por_id[ids[1]]
            t = self.tipo_borde(N, tn, e1, e2, nucleo_ids, abiertos, forzados)
            if e2 is None:
                clave = ('ext', t) if t == 'fachada' else ('ext1', e1['id'], t)
            else:
                clave = ('int', tuple(sorted((e1['id'], e2['id']))), t)
            elementales.append((clave, a, b))
        # fundir tramos colineales contiguos con la misma clave
        grupos = {}
        for clave, a, b in elementales:
            hz = abs(a[1] - b[1]) <= TOL
            linea = ('h', C._k(a[1])) if hz else ('v', C._k(a[0]))
            eje = 0 if hz else 1
            lo, hi = sorted((a[eje], b[eje]))
            grupos.setdefault((clave, linea), []).append((lo, hi))
        crudos = []
        for (clave, linea), tramos in grupos.items():
            tramos.sort()
            actual = list(tramos[0])
            for lo, hi in tramos[1:]:
                if abs(lo - actual[1]) <= TOL:
                    actual[1] = hi
                else:
                    crudos.append((clave, linea, tuple(actual)))
                    actual = [lo, hi]
            crudos.append((clave, linea, tuple(actual)))
        tipos = self.reglas['tipos_muro']
        salida = []
        for clave, linea, (lo, hi) in crudos:
            t = clave[-1]
            if linea[0] == 'h':
                a, b = [lo, linea[1]], [hi, linea[1]]
            else:
                a, b = [linea[1], lo], [linea[1], hi]
            nl = C.normal_unitaria_izquierda(a, b)
            m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
            izq = (m[0] + 0.02 * nl[0], m[1] + 0.02 * nl[1])
            der = (m[0] - 0.02 * nl[0], m[1] - 0.02 * nl[1])

            def dueño(p):
                for e in esp:
                    if C.punto_en_poligono(p, e['_p'], 0.0):
                        return e['id']
                return None

            if clave[0] == 'int':
                li, ld = dueño(izq), dueño(der)
                if {li, ld} != set(clave[1]):
                    raise ErrorTrazado(f'{N}: no se pudo orientar el muro {a}-{b} entre {clave[1]}')
                lados = [li, ld]
            else:
                if not C.punto_en_poligono(izq, contorno, 0.0):
                    a, b = b, a
                    izq, der = der, izq
                lados = [None, 'exterior'] if clave[0] == 'ext' else [clave[1], 'exterior']
            d = tipos[t]
            # cota de la base (16.6 y revisión adversarial): un muro de un recinto con z_piso_m distinto de 0 (la terraza del
            # piso 3 dentro del nivel de cubierta) arranca en el piso más alto de sus lados; si es 0, no se escribe
            zs = [float(por_id[x]['_t'].get('z_piso_m') or 0.0) for x in lados if x in por_id]
            z_base = max(zs) if zs else 0.0
            alto_d = d.get('altura')
            if alto_d == 'entrepiso':
                altura = tn['altura_entrepiso_m']
            elif alto_d == 'libre':
                altura = tn['altura_libre_m']
            else:
                altura = float(alto_d)
            w = {'a': pt(a), 'b': pt(b), 'tipo': t, 'espesor': d['espesor_m'], 'altura': altura,
                 'lados': lados, 'estructural': bool(d.get('estructural'))}
            if abs(z_base) > 1e-9:
                w['z_base_m'] = r2(z_base)
            salida.append(w)
        salida.sort(key=lambda w: (min(w['a'][1], w['b'][1]), min(w['a'][0], w['b'][0]),
                                   max(w['a'][1], w['b'][1]), max(w['a'][0], w['b'][0])))
        for i, w in enumerate(salida, 1):
            w['id'] = C.id_muro(N, i)
        return [{k: w[k] for k in ('id', 'a', 'b', 'tipo', 'espesor', 'altura', 'z_base_m', 'lados', 'estructural') if k in w}
                for w in salida]

    @staticmethod
    def poligono_libre(p, muros):
        cortes = [v for m in muros for v in (m['a'], m['b'])]
        pp = C.partir_bordes(p, cortes)
        ds = []
        for s0, s1 in C.bordes(pp):
            esp = [m['espesor'] for m in muros if C.solape_colineal(s0, s1, m['a'], m['b'], 1e-6)]
            ds.append(max(esp) / 2 if esp else 0.0)
        return [pt(v) for v in C.desplazar_adentro(pp, ds)]

    # ------------------------------------------------------------------------------------------------ puertas
    def categoria_puerta(self, e) -> str | None:
        if e is None:
            return None
        texto = e['ambiente']
        for o in self.reglas['categoria_puerta']:
            if re.search(o['patron'], texto, re.I):
                return o['categoria']
        return None

    def ancho_requerido(self, cat, lados):
        req, cita = 0.0, ''
        c = self.cat_puertas.get(cat)
        if c:
            req, cita = c['ancho_m'], c.get('cita', '')
        for e in lados:
            if e is None:
                continue
            for c in self.cat_puertas.values():
                if e['ambiente'] in c.get('ambientes', []) and c['ancho_m'] > req:
                    req, cita = c['ancho_m'], c.get('cita', '')
        return req, cita

    def puertas(self, N, tn, esp, muros, contorno):
        por_id = {e['id']: e for e in esp}
        pref = lambda x: x if x == 'exterior' or x.startswith(N + '-') else f'{N}-{x}'
        salida = []
        for i, d in enumerate(tn.get('puertas', []), 1):
            A, B = (pref(x) for x in d['entre'])
            for x in (A, B):
                if x != 'exterior' and x not in por_id:
                    raise ErrorTrazado(f'{N}: puerta {d}: {x} no es un recinto del nivel')
            if 'exterior' in (A, B):
                rid = B if A == 'exterior' else A
                cand = [m for m in muros if 'exterior' in m['lados']
                        and (rid in m['lados'] or (m['lados'][0] is None
                                                   and C.largo_cubierto(m['a'], m['b'], C.bordes(por_id[rid]['_p'])) > TOL))]
                comunes = []
                for m in cand:
                    for s0, s1 in C.bordes(por_id[rid]['_p']):
                        s = C.solape_colineal(s0, s1, m['a'], m['b'])
                        if s:
                            comunes.append((s, m))
            else:
                cand = [m for m in muros if set(m['lados']) == {A, B}]
                comunes = [((m['a'], m['b']), m) for m in cand]
            if not comunes:
                raise ErrorTrazado(f'{N}: no hay muro entre {A} y {B} para la puerta {d}')
            if any(m['tipo'] == 'abierto' for _, m in comunes):
                raise ErrorTrazado(f'{N}: {A} y {B} están unidos por un vano abierto; la puerta {d} sobra')
            pos = d.get('pos', 0.5)
            if isinstance(pos, (int, float)):
                (s0, s1), muro = max(comunes, key=lambda c: math.dist(c[0][0], c[0][1]))
                c = [s0[0] + (s1[0] - s0[0]) * pos, s0[1] + (s1[1] - s0[1]) * pos]
            else:
                c = list(pos)
                muro = None
                for (s0, s1), m in comunes:
                    if C.distancia_punto_segmento(c, s0, s1) <= 1e-6:
                        muro = m
                        break
                if muro is None:
                    raise ErrorTrazado(f'{N}: el punto {c} de la puerta {d} no está en el borde común de {A} y {B}')
            # desde / hacia
            eA, eB = por_id.get(A), por_id.get(B)
            if A == 'exterior' or B == 'exterior':
                desde, hacia = 'exterior', (B if A == 'exterior' else A)
            elif d.get('desde'):
                desde = pref(d['desde'])
                hacia = B if desde == A else A
            elif eA['de_paso'] and not eB['de_paso']:
                desde, hacia = A, B
            elif eB['de_paso'] and not eA['de_paso']:
                desde, hacia = B, A
            else:
                desde, hacia = A, B
            e_h = por_id.get(hacia)
            e_d = por_id.get(desde)
            cat = d.get('categoria') or self.categoria_puerta(e_h) or self.categoria_puerta(e_d) or 'consultorio'
            if cat not in self.cat_puertas:
                raise ErrorTrazado(f'{N}: categoría de puerta desconocida {cat!r}')
            req, cita = self.ancho_requerido(cat, (e_h, e_d))
            ancho = max(float(d.get('ancho', 0.0)), req)
            hojas = d.get('hojas', 2 if ancho >= 1.40 - 1e-9 else 1)
            abre = d.get('abre')
            if abre is None:
                abre = self.reglas['abre_por_categoria'].get(cat, 'adentro')
            tipo = d.get('tipo') or ('corrediza' if abre == 'corrediza' else 'batiente')
            p = {'id': C.id_puerta(N, i), 'muro': muro['id'], 'centro': pt(c), 'ancho': r2(ancho), 'alto': 2.1,
                 'hojas': hojas, 'desde': desde, 'hacia': hacia, 'abre': abre}
            if abre not in ('corrediza',):
                p['bisagra'] = d.get('bisagra', 'izquierda')
            p['tipo'] = tipo
            p['categoria'] = cat
            p['cita_ancho'] = self.cita(cita) if cita else None
            if d.get('nombre'):
                p['nombre'] = d['nombre']
            if d.get('lleva_a'):
                la = dict(d['lleva_a'])
                p['lleva_a'] = la
            salida.append(p)
        return salida

    # ------------------------------------------------------------------------------------------------ subrecintos
    def subrecintos(self, N, tn, esp, muros, puertas) -> dict:
        """Baños y cabinas dentro de un recinto (revisión adversarial: el inodoro y la ducha no quedan sueltos en la
        habitación). El trazado los da en el recinto («banos»: rect, nombre y puerta); el área sigue contando en el recinto del
        programa. Cada uno lleva tabique de placa de yeso RH (liviano) donde no toca el borde del recinto y su puerta, que
        abre hacia el recinto (corrediza por defecto, NTC 6047 para las unidades PMR; numeral por confirmar)."""
        por_id = {e['id']: e for e in esp}
        salida = {}
        tipos = self.reglas['tipos_muro']
        nuevos_muros = []
        for e in esp:
            banos = e['_t'].get('banos') or []
            if not banos:
                continue
            P = e['_p']
            subs = []
            for k, b in enumerate(banos, 1):
                r = [float(v) for v in b['rect']]
                for v in r:
                    if not C.es_multiplo(v, 0.05):
                        raise ErrorTrazado(f'{N}: {e["id"]}: el baño {b} no está en múltiplos de 0,05 m')
                q = C.rect_a_poligono(r)
                if not C.poligono_dentro_de(q, P, 1e-6):
                    raise ErrorTrazado(f'{N}: {e["id"]}: el baño {r} se sale del recinto')
                subs.append({'id': f'{e["id"]}-B{k}', 'nombre': b.get('nombre', 'Baño'), '_r': r, '_p': q, '_b': b})
            # tabiques: bordes de cada baño que no están sobre el borde del recinto (los compartidos entre cabinas, uno solo)
            hechos = {}
            vertices = [v for sb in subs for v in sb['_p']] + [v for v in P]
            for sb in subs:
                for a, bb in C.bordes(C.partir_bordes(sb['_p'], vertices)):
                    if C.segmento_en_borde(a, bb, P):
                        continue
                    clave = clave_seg(a, bb)
                    if clave in hechos:
                        hechos[clave]['lados'][hechos[clave]['_vacio']] = sb['id']
                        continue
                    nl = C.normal_unitaria_izquierda(a, bb)
                    m_ = [(a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2]
                    izq = (m_[0] + 0.02 * nl[0], m_[1] + 0.02 * nl[1])
                    dentro_izq = C.punto_en_poligono(izq, sb['_p'], 0.0)
                    lados = [sb['id'], e['id']] if dentro_izq else [e['id'], sb['id']]
                    d = tipos['liviano']
                    w = {'a': pt(a), 'b': pt(bb), 'tipo': 'liviano', 'espesor': d['espesor_m'], 'altura': tn['altura_libre_m'],
                         'lados': lados, 'estructural': False, '_vacio': 1 if dentro_izq else 0}
                    hechos[clave] = w
                    nuevos_muros.append(w)
            salida[e['id']] = subs
        for w in nuevos_muros:
            w.pop('_vacio')
        nuevos_muros.sort(key=lambda w: (min(w['a'][1], w['b'][1]), min(w['a'][0], w['b'][0]), w['lados']))
        for w in nuevos_muros:
            w['id'] = C.id_muro(N, len(muros) + 1)
            muros.append({k: w[k] for k in ('id', 'a', 'b', 'tipo', 'espesor', 'altura', 'lados', 'estructural')})
        # puertas de los baños
        for rid, subs in salida.items():
            for sb in subs:
                b = sb['_b']
                pd = b.get('puerta') or {}
                c = [float(v) for v in pd['pos']]
                cand = [m for m in muros if sb['id'] in m['lados'] and C.distancia_punto_segmento(c, m['a'], m['b']) <= 1e-6]
                if not cand:
                    raise ErrorTrazado(f'{N}: {sb["id"]}: la puerta {c} no está sobre un tabique del baño')
                m = cand[0]
                otro = next(x for x in m['lados'] if x != sb['id'])
                e_sub = {'ambiente': sb['nombre']}
                cat = pd.get('categoria') or self.categoria_puerta(e_sub) or 'unidad_sanitaria'
                req, cita = self.ancho_requerido(cat, ())
                ancho = max(float(pd.get('ancho', 0.0)), req)
                abre = pd.get('abre', 'corrediza')
                p = {'id': C.id_puerta(N, len(puertas) + 1), 'muro': m['id'], 'centro': pt(c), 'ancho': r2(ancho), 'alto': 2.1,
                     'hojas': 1, 'desde': otro, 'hacia': sb['id'], 'abre': abre}
                if abre != 'corrediza':
                    p['bisagra'] = pd.get('bisagra', 'izquierda')
                p['tipo'] = 'corrediza' if abre == 'corrediza' else 'batiente'
                p['categoria'] = cat
                p['cita_ancho'] = self.cita(cita) if cita else None
                p['nombre'] = f'Puerta de {sb["nombre"][0].lower()}{sb["nombre"][1:]}'
                puertas.append(p)
                sb['puertas'] = [p['id']]
        return salida

    # ------------------------------------------------------------------------------------------------ ventanas
    def ventanas(self, N, tn, esp, muros, puertas, columnas=()):
        if not tn.get('ventanas', True):
            return []
        sin = {x if x.startswith(N + '-') else f'{N}-{x}' for x in tn.get('sin_ventana', [])}
        vparams = self.reglas['ventanas']
        salida = []
        for e in esp:
            if (e['id'] in sin or e['tipo'] == 'nucleo' or e['exterior'] or not e['transitable']
                    or e['_t'].get('sin_ventana')):
                continue
            for s0, s1 in C.bordes(e['_p']):
                for m in muros:
                    if 'exterior' not in m['lados'] or m['tipo'] not in ('fachada',):
                        continue
                    s = C.solape_colineal(s0, s1, m['a'], m['b'])
                    if not s:
                        continue
                    hz = C.es_horizontal(*s)
                    eje = 0 if hz else 1
                    lo, hi = sorted((s[0][eje], s[1][eje]))
                    fijo = s[0][1 - eje]
                    # tramos libres de puertas
                    ocupados = []
                    for p in puertas:
                        if p['muro'] != m['id']:
                            continue
                        c = p['centro'][eje]
                        ocupados.append((c - p['ancho'] / 2 - 0.30, c + p['ancho'] / 2 + 0.30))
                    for col in columnas:
                        if abs(col[1 - eje] - fijo) <= col[2 + (1 - eje)] / 2 + 1e-6:
                            ocupados.append((col[eje] - col[2 + eje] / 2, col[eje] + col[2 + eje] / 2))
                    # los baños del recinto no llevan ventana (extracción mecánica, CUB-A223) y la del recinto no cruza su
                    # tabique
                    for bn in e['_t'].get('banos') or []:
                        q = [float(v) for v in bn['rect']]
                        if abs(q[1 - eje] - fijo) <= 1e-6 or abs(q[3 - eje] - fijo) <= 1e-6:
                            ocupados.append((q[eje] - 0.06, q[2 + eje] + 0.06))
                    libres = [(lo + vparams['margen_m'], hi - vparams['margen_m'])]
                    for o0, o1 in sorted(ocupados):
                        nuevos = []
                        for l0, l1 in libres:
                            if o1 <= l0 or o0 >= l1:
                                nuevos.append((l0, l1))
                                continue
                            if o0 > l0:
                                nuevos.append((l0, o0))
                            if o1 < l1:
                                nuevos.append((o1, l1))
                        libres = nuevos
                    for l0, l1 in libres:
                        if l1 - l0 < vparams['ancho_min_m'] - 1e-9:
                            continue
                        cc = (l0 + l1) / 2
                        centro = [cc, fijo] if hz else [fijo, cc]
                        salida.append({'muro': m['id'], 'centro': pt(centro), 'ancho': r2(l1 - l0),
                                       'antepecho': vparams['antepecho_m'], 'alto': vparams['alto_m'], '_r': e['id']})
        salida.sort(key=lambda v: (v['centro'][1], v['centro'][0]))
        for i, v in enumerate(salida, 1):
            v['id'] = C.id_ventana(N, i)
        return salida

    # ------------------------------------------------------------------------------------------------ escaleras
    def escaleras(self, niveles_z: dict) -> dict:
        """{nivel: [escalera]} con los tramos de la subida desde cada nivel (cotas relativas al piso del nivel)."""
        salida = {}
        for es in self.tz.get('escaleras', []):
            x0, y0, x1, y1 = es['rect']
            m = es.get('muro_m', 0.30) / 2
            cx0, cy0, cx1, cy1 = x0 + m, y0 + m, x1 - m, y1 - m
            ancho_t = es['ancho_tramo_m']
            huellas = es['huellas_por_tramo']
            huella = es['huella_m']
            largo_t = huellas * huella
            eje_largo = 'y' if (cy1 - cy0) >= (cx1 - cx0) else 'x'
            L = (cy1 - cy0) if eje_largo == 'y' else (cx1 - cx0)
            W = (cx1 - cx0) if eje_largo == 'y' else (cy1 - cy0)
            d_piso = es.get('descanso_piso_m', (L - largo_t) / 2)
            d_medio = L - largo_t - d_piso
            ojo = W - 2 * ancho_t
            # el descanso de piso puede ser más corto solo si se abre a una circulación del nivel (escalera abierta)
            d_piso_min = 0.30 if 'descanso_piso_m' in es else 1.2
            if d_piso < d_piso_min or d_medio < 1.2 or ojo < 0:
                raise ErrorTrazado(f'escalera {es["id"]}: no caben los tramos ({L:.2f} × {W:.2f} m libres)')
            lado_piso = es['descanso_piso']          # 'sur' | 'norte' | 'oeste' | 'este'
            carril = es['carril_subida']             # carril del primer tramo: 'oeste' | 'este' | 'sur' | 'norte'

            def franja(t0, t1, w0, w1):
                """Rectángulo en coordenadas (largo, ancho) medidas desde el lado del descanso de piso y desde el
                carril de subida → [x0, y0, x1, y1] de planta."""
                if eje_largo == 'y':
                    ya, yb = (cy0 + t0, cy0 + t1) if lado_piso == 'sur' else (cy1 - t1, cy1 - t0)
                    xa, xb = (cx0 + w0, cx0 + w1) if carril == 'oeste' else (cx1 - w1, cx1 - w0)
                    return [r2(xa), r2(ya), r2(xb), r2(yb)]
                xa, xb = (cx0 + t0, cx0 + t1) if lado_piso == 'oeste' else (cx1 - t1, cx1 - t0)
                ya, yb = (cy0 + w0, cy0 + w1) if carril == 'sur' else (cy1 - w1, cy1 - w0)
                return [r2(xa), r2(ya), r2(xb), r2(yb)]

            rumbo_ida = {'sur': 90, 'norte': 270, 'oeste': 0, 'este': 180}[lado_piso]
            rumbo_vuelta = (rumbo_ida + 180) % 360
            nivs = es['niveles']
            for i, N in enumerate(nivs):
                rec = es['recintos'][N]
                d = {'id': es['id'], 'recinto': f'{N}-{rec}', 'nombre': es['nombre']}
                partes = [{'tipo': 'descanso_piso', 'rect': franja(0, d_piso, 0, W), 'z': 0.0}]
                if i + 1 < len(nivs):
                    N2 = nivs[i + 1]
                    h = niveles_z[N2] - niveles_z[N]
                    n_ch = 2 * (huellas + 1)
                    ch = h / n_ch
                    zm = h / 2
                    partes += [
                        {'tipo': 'tramo', 'rect': franja(d_piso, d_piso + largo_t, 0, ancho_t), 'z0': 0.0, 'z1': r3(zm),
                         'sube_hacia_deg': rumbo_ida, 'contrahuellas': huellas + 1, 'contrahuella_m': r3(ch),
                         'huella_m': huella, 'ancho_m': ancho_t},
                        {'tipo': 'descanso_intermedio', 'rect': franja(d_piso + largo_t, L, 0, W), 'z': r3(zm)},
                        {'tipo': 'tramo', 'rect': franja(d_piso, d_piso + largo_t, W - ancho_t, W), 'z0': r3(zm),
                         'z1': r3(h), 'sube_hacia_deg': rumbo_vuelta, 'contrahuellas': huellas + 1,
                         'contrahuella_m': r3(ch), 'huella_m': huella, 'ancho_m': ancho_t},
                    ]
                    d['sube_a'] = N2
                    d['altura_a_salvar_m'] = r3(h)
                else:
                    d['sube_a'] = None
                d['baja_a'] = nivs[i - 1] if i > 0 else None
                if ojo > 0.05:
                    d['ojo'] = franja(d_piso, d_piso + largo_t, ancho_t, W - ancho_t)
                d['partes'] = partes
                d['notas'] = es.get('notas', [])
                salida.setdefault(N, []).append(d)
        return salida

    # ------------------------------------------------------------------------------------------------ nivel
    def nivel(self, tn: dict, escaleras: dict) -> dict:
        N = tn['id']
        esp = self.espacios(N, tn)
        pref = lambda x: x if x.startswith(N + '-') else f'{N}-{x}'
        por_id = {e['id']: e for e in esp}
        if 'contorno' in tn:
            contorno = C.orientar_antihorario(C.limpiar_poligono(tn['contorno']))
        else:
            contorno = contorno_de_union([e['_p'] for e in esp])
        # núcleos
        nucleos = []
        nucleo_ids = set()
        for nu in tn.get('nucleos', []):
            recs = [pref(x) for x in (nu.get('recintos') or [nu['recinto']])]
            for x in recs:
                if x not in por_id:
                    raise ErrorTrazado(f'{N}: el núcleo {nu["id"]} cita {x}, que no existe')
            if 'rect' in nu:
                pol = C.rect_a_poligono(nu['rect'])
            elif len(recs) == 1:
                pol = por_id[recs[0]]['_p']
            else:
                pol = contorno_de_union([por_id[x]['_p'] for x in recs])
            d = {'id': f'{N}-NUC-{nu["id"]}', 'tipo': nu['tipo'], 'recinto': recs[0]}
            if len(recs) > 1:
                d['recintos'] = recs
            d['poligono'] = [pt(v) for v in pol]
            if nu.get('nombre'):
                d['nombre'] = nu['nombre']
            nucleos.append(d)
            if nu['tipo'] in TIPOS_NUCLEO_MURO and nu.get('muro_de_nucleo', True):
                nucleo_ids.update(recs)
        muros = self.muros(N, tn, esp, contorno, nucleo_ids)
        puertas = self.puertas(N, tn, esp, muros, contorno)
        subs_de = self.subrecintos(N, tn, esp, muros, puertas)
        # columnas de la retícula
        columnas = []
        if N in NIVELES_PISO:
            ret = self.tz['reticula']
            for ey in ret['ejes_y']:
                for ex in ret['ejes_x']:
                    if C.punto_en_poligono((ex['x'], ey['y']), contorno, 1e-3):
                        columnas.append({'id': f'{ex["id"]}{ey["id"]}', 'x': ex['x'], 'y': ey['y'], 'b': 0.6, 'h': 0.6})
        ventanas = self.ventanas(N, tn, esp, muros, puertas, [(c['x'], c['y'], c['b'], c['h']) for c in columnas])
        # vecinos por puertas y vanos abiertos
        vecinos = {e['id']: set() for e in esp}
        puertas_de = {e['id']: set() for e in esp}
        ids_sub = {sb['id'] for subs in subs_de.values() for sb in subs}
        for p in puertas:
            if p['desde'] in ids_sub or p['hacia'] in ids_sub:
                continue                      # la puerta de un baño se lista en su subrecinto
            for x, y in ((p['desde'], p['hacia']), (p['hacia'], p['desde'])):
                if x in vecinos:
                    vecinos[x].add(y)
                    puertas_de[x].add(p['id'])
        for m in muros:
            if m['tipo'] == 'abierto' and None not in m['lados'] and 'exterior' not in m['lados']:
                vecinos[m['lados'][0]].add(m['lados'][1])
                vecinos[m['lados'][1]].add(m['lados'][0])
        ventanas_de = {}
        for v in ventanas:
            ventanas_de.setdefault(v.pop('_r'), []).append(v['id'])
        # recintos
        recintos = []
        avisos_libre = 0
        for e in esp:
            t = e['_t']
            p = e['_p']
            libre = self.poligono_libre(p, muros)
            subs_out = []
            if e['id'] in subs_de:
                # el polígono libre del recinto descuenta sus baños (con media espesura del tabique alrededor)
                media = self.reglas['tipos_muro']['liviano']['espesor_m'] / 2
                quitar = [[sb['_r'][0] - media, sb['_r'][1] - media, sb['_r'][2] + media, sb['_r'][3] + media] for sb in subs_de[e['id']]]
                libre = [pt(v) for v in diferencia(libre, quitar)]
                for sb in subs_de[e['id']]:
                    sl = self.poligono_libre(sb['_p'], muros)
                    subs_out.append({'id': sb['id'], 'nombre': sb['nombre'], 'poligono': [pt(v) for v in sb['_p']],
                                     'poligono_libre': sl, 'area_ejes_m2': r2(C.area_poligono(sb['_p'])),
                                     'area_libre_m2': r2(C.area_poligono(sl)), 'puertas': sb['puertas']})
            al = C.area_poligono(libre)
            r = {'id': e['id']}
            if e.get('fila') is not None:
                r.update(fila=e['fila'], k=e['k'], de=e['de'])
            r['ambiente'] = e['ambiente']
            if e.get('servicio_programa'):
                r['servicio_programa'] = e['servicio_programa']
            r['grupo_1633'] = self.grupo(e.get('servicio_programa'), e['ambiente'], e.get('fila'), e['tipo'], t.get('grupo'))
            r['zona_acceso'] = self.zona_acceso(e.get('servicio_programa'), e['ambiente'], e['tipo'])
            r['tipo'] = e['tipo']
            if not e['programado'] and e['tipo'] != 'circulacion':
                r['programado'] = False
            if e['de_paso'] and e['tipo'] != 'circulacion':
                r['de_paso'] = True
            if e['exterior']:
                r['exterior'] = True
            if not e['transitable']:
                r['transitable'] = False
            if t.get('z_piso_m') is not None:
                r['z_piso_m'] = t['z_piso_m']
            if t.get('rampa'):
                r['rampa'] = t['rampa']
            r['poligono'] = [pt(v) for v in p]
            r['poligono_libre'] = libre
            r['area_ejes_m2'] = r2(C.area_poligono(p))
            r['area_libre_m2'] = r2(al)
            if e.get('fila') is not None:
                r['area_programa_m2'] = self.amb[e['fila']].get('m2_unitario')
                r['minimo_1633'] = self.minimo(e['fila'])
            elif e['tipo'] != 'circulacion':
                r['area_programa_m2'] = None
                r['minimo_1633'] = None
            if e['tipo'] == 'circulacion':
                r['ancho_libre_m'] = r2(C.ancho_minimo(libre, C.MUESCA_IGNORADA_M))
                r['evacuacion'] = bool(t.get('evacuacion'))
                r['camillas'] = bool(t.get('camillas'))
            r['acceso'] = sorted(vecinos[e['id']])
            r['puertas'] = sorted(puertas_de[e['id']])
            if subs_out:
                r['subrecintos'] = subs_out
            r['ventanas'] = sorted(ventanas_de.get(e['id'], []))
            cl = None if (e['exterior'] or e['tipo'] == 'circulacion') else self.climatizacion(e.get('servicio_programa'), e['ambiente'])
            if cl:
                r['climatizacion'] = cl
            notas = list(t.get('notas', []))
            mn = r.get('minimo_1633')
            al_total = al + sum(sb['area_libre_m2'] for sb in subs_out)     # el baño cuenta en el recinto del programa
            if mn and al_total < mn['m2'] - 1e-6:
                avisos_libre += 1
                notas.append(self.reglas['nota_area_libre'])
            r['notas'] = notas
            recintos.append(r)
        # conexiones verticales
        piso = tn['piso']
        conexiones = []
        for cv in self.tz.get('conexiones_verticales', []):
            if piso in cv['pisos']:
                conexiones.append({k: cv[k] for k in ('id', 'tipo', 'nombre', 'pisos', 'puntos') if k in cv})
        entradas = [dict(x) for x in tn.get('entradas_recorrido', [])]
        obst = []
        for o in tn.get('obstaculos_recorrido', []):
            d = {'id': o['id'], 'nombre': o['nombre']}
            d['poligono'] = [pt(v) for v in (C.rect_a_poligono(o['rect']) if 'rect' in o else o['poligono'])]
            for k in ('altura_m', 'z_piso_m'):
                if k in o:
                    d[k] = o[k]
            obst.append(d)
        nivel = {'id': N, 'piso': piso, 'nombre': tn['nombre'], 'z': tn['z'],
                 'altura_entrepiso_m': tn['altura_entrepiso_m'], 'altura_libre_m': tn['altura_libre_m']}
        if tn.get('notas'):
            nivel['notas'] = tn['notas']
        nivel['contorno'] = [pt(v) for v in contorno]
        if tn.get('cerramiento'):
            nivel['cerramiento'] = tn['cerramiento']
        nivel.update(columnas=columnas, recintos=recintos, nucleos=nucleos, muros=muros, puertas=puertas,
                     ventanas=ventanas, conexiones_verticales=conexiones, escaleras=escaleras.get(N, []),
                     entradas_recorrido=entradas, obstaculos_recorrido=obst)
        if tn.get('paneles_solares'):
            nivel['paneles_solares'] = tn['paneles_solares']
        nivel['_avisos_libre'] = avisos_libre
        return nivel

    @staticmethod
    def puerta_espejo(otro: dict, p: dict, rid: str, nivel_p: str) -> str:
        """Vano en el nivel de exteriores donde llega una puerta de otro nivel (revisión adversarial: la fachada y el
        cerramiento no pueden quedar ciegos donde están los pasos). Es la misma puerta vista desde afuera: mismo centro,
        ancho, tipo y apertura; la hoja la dibuja el nivel de la puerta (espejo_de)."""
        cands = [m for m in otro['muros'] if m['tipo'] != 'abierto'
                 and C.distancia_punto_segmento(p['centro'], m['a'], m['b']) <= 1e-6]
        if not cands:
            raise ErrorTrazado(f'{p["id"]}: en {otro["id"]} no hay muro en {p["centro"]} para el vano espejo')
        cands.sort(key=lambda m: (rid not in m['lados'], m['id']))
        m = cands[0]
        otro_lado = [x for x in m['lados'] if x != rid]
        e = {'id': C.id_puerta(otro['id'], len(otro['puertas']) + 1), 'muro': m['id'], 'centro': p['centro'],
             'ancho': p['ancho'], 'alto': p['alto'], 'hojas': p['hojas'], 'desde': rid,
             'hacia': (otro_lado[0] if otro_lado and otro_lado[0] else 'exterior'), 'abre': p['abre']}
        if 'bisagra' in p:
            e['bisagra'] = p['bisagra']
        e.update(tipo=p['tipo'], categoria=p['categoria'], cita_ancho=p.get('cita_ancho'))
        if p.get('nombre'):
            e['nombre'] = p['nombre']
        e['espejo_de'] = {'nivel': nivel_p, 'puerta': p['id']}
        otro['puertas'].append(e)
        por_id = {r['id']: r for r in otro['recintos']}
        for a, b in ((e['desde'], e['hacia']), (e['hacia'], e['desde'])):
            if a in por_id:
                por_id[a]['puertas'] = sorted(set(por_id[a]['puertas']) | {e['id']})
                por_id[a]['acceso'] = sorted(set(por_id[a]['acceso']) | {b})
        return e['id']

    # ------------------------------------------------------------------------------------------------ todo
    def generar(self) -> dict:
        tz = self.tz
        niveles_t = tz['niveles']
        ids = [n['id'] for n in niveles_t]
        if sorted(ids, key=ORDEN_NIVELES.index) != ids or len(set(ids)) != len(ids):
            raise ErrorTrazado(f'niveles fuera de orden o repetidos: {ids} (orden {ORDEN_NIVELES})')
        niveles_z = {n['id']: n['z'] for n in niveles_t}
        esc = self.escaleras(niveles_z)
        niveles = [self.nivel(tn, esc) for tn in niveles_t]
        # pasos entre niveles (puertas a «exterior» que llevan a otro nivel)
        por_nivel = {n['id']: n for n in niveles}
        for n in niveles:
            n['pasos_entre_niveles'] = []
        for n in niveles:
            for p in n['puertas']:
                la = p.get('lleva_a')
                if not la:
                    continue
                if la['nivel'] not in por_nivel:
                    raise ErrorTrazado(f'{p["id"]}: lleva_a un nivel que no existe ({la["nivel"]})')
                otro = por_nivel[la['nivel']]
                if la['recinto'] not in {r['id'] for r in otro['recintos']}:
                    raise ErrorTrazado(f'{p["id"]}: lleva_a {la["recinto"]}, que no está en {la["nivel"]}')
                n['pasos_entre_niveles'].append({'puerta': p['id'], 'punto': p['centro'], 'recinto': p['hacia'],
                                                 'otro_nivel': la['nivel'], 'otro_recinto': la['recinto']})
                espejo = self.puerta_espejo(otro, p, la['recinto'], n['id']) if la['nivel'] in NIVELES_CON_ESPEJO else None
                otro['pasos_entre_niveles'].append({'puerta': espejo, 'punto': p['centro'], 'recinto': la['recinto'],
                                                    'otro_nivel': n['id'], 'otro_recinto': p['hacia'],
                                                    'puerta_del_otro_nivel': p['id']})
        for n in niveles:
            n['pasos_entre_niveles'].sort(key=lambda x: (x['punto'][1], x['punto'][0], x['otro_nivel']))
        # grupos de color (Res. 1633, Cuadros 2 y 3)
        colores = self.normas['parametros_diseno']['senalizacion_colores']
        tonos = self.reglas['grupos_1633']['tonos_hex']
        cita_col = self.cita(self.reglas['grupos_1633']['cita'])
        grupos = {}
        for g, nombre in self.reglas['grupos_1633']['nombres'].items():
            color = colores['servicios'].get(g) or self.reglas['grupos_1633']['colores_fuera_de_la_norma'].get(g)
            if color is None:
                raise ErrorTrazado(f'grupo {g} sin color en normas.json')
            grupos[g] = {'nombre': nombre, 'color': color, 'color_hex': tonos[color], 'cita': cita_col}
        usados = {r['grupo_1633'] for n in niveles for r in n['recintos']}
        faltan = usados - set(grupos)
        if faltan:
            raise ErrorTrazado(f'grupos sin color: {sorted(faltan)}')
        for c in tz.get('citas_fijas', []):
            self.cita(c)
        resumen = {
            'recintos_por_nivel': {n['id']: sum(1 for r in n['recintos'] if r.get('fila') is not None) for n in niveles},
            'recintos_no_programados_por_nivel': {n['id']: sum(1 for r in n['recintos'] if r.get('fila') is None and r['tipo'] != 'circulacion') for n in niveles},
            'circulaciones_por_nivel': {n['id']: sum(1 for r in n['recintos'] if r['tipo'] == 'circulacion') for n in niveles},
            'espacios_por_nivel': {n['id']: len(n['recintos']) for n in niveles},
            'area_ejes_por_nivel_m2': {n['id']: r2(sum(r['area_ejes_m2'] for r in n['recintos'])) for n in niveles},
            'area_util_programa_a_ejes_por_nivel_m2': {},
            'area_circulacion_por_nivel_m2': {n['id']: r2(sum(r['area_ejes_m2'] for r in n['recintos'] if r['tipo'] == 'circulacion')) for n in niveles},
            'muros_por_nivel': {n['id']: len(n['muros']) for n in niveles},
            'puertas_por_nivel': {n['id']: len(n['puertas']) for n in niveles},
            'ventanas_por_nivel': {n['id']: len(n['ventanas']) for n in niveles},
            'avisos_area_libre': sum(n['_avisos_libre'] for n in niveles),
        }
        util_srv = {f'P{r["piso"]}': set(r.get('m2_util_por_servicio', {})) for r in self.prog.get('resumen_por_piso', [])}
        for n in niveles:
            if n['id'] in util_srv:
                resumen['area_util_programa_a_ejes_por_nivel_m2'][n['id']] = r2(sum(
                    r['area_ejes_m2'] for r in n['recintos'] if r.get('servicio_programa') in util_srv[n['id']]
                    and r.get('fila') is not None))
        for n in niveles:
            n.pop('_avisos_libre')
        ret = tz['reticula']
        salida = {
            'id': 'torre_hospital_plantas',
            'version': tz['version'],
            'generado_por': 'scripts/torre/generar_plantas.py',
            'fecha': tz['fecha'],
            'tipo_dato': 'estimacion',
            'estado': tz['estado'],
            'marco': C.MARCO,
            'modulo_m': self.normas['parametros_diseno']['modulo_hospitalario_m']['valor'],
            'reticula': {'ejes_x': ret['ejes_x'], 'ejes_y': ret['ejes_y']},
            'convenciones': tz['convenciones'],
            'tipos_muro': {k: {kk: vv for kk, vv in v.items() if kk != 'altura'} | {'altura': v.get('altura')}
                           for k, v in self.reglas['tipos_muro'].items()},
            'niveles': C.redondear_todo(niveles, 3),
            'zonas': {k: v for k, v in self.reglas.get('zonas', {}).items() if k in {n['id'] for n in niveles} or k == 'nota'},
            'grupos_1633': grupos,
            'nota_colores': self.reglas['grupos_1633']['nota'],
            'citas': self.citas,
            'resumen': resumen,
            'decisiones': self.reglas.get('decisiones', []) + tz.get('decisiones', []),
            'fuentes': tz['fuentes'],
            'insumos_sha1': C.insumos_sha1(self.insumos),
        }
        return salida


def main(argv=None):
    ap = argparse.ArgumentParser(description='Genera torre_hospital_plantas.json desde el trazado (3.1-3.3 y 16).')
    ap.add_argument('--trazado', type=Path, default=C.TRAZADO)
    ap.add_argument('--reglas', type=Path, default=C.REGLAS_PLANTA)
    ap.add_argument('--programa', type=Path, default=C.PROGRAMA)
    ap.add_argument('--normas', type=Path, default=C.NORMAS)
    ap.add_argument('--salida', type=Path, default=C.PLANTAS)
    ap.add_argument('--verificar', action='store_true', help='no escribe: sale con 1 si el archivo no está al día')
    a = ap.parse_args(argv)
    try:
        g = Generador(C.cargar_json(a.trazado), C.cargar_json(a.programa), C.cargar_json(a.reglas),
                      C.cargar_json(a.normas), [a.trazado, a.reglas, a.programa, a.normas])
        datos = g.generar()
    except (ErrorTrazado, FileNotFoundError, ValueError, KeyError) as e:
        sys.stderr.write(f'generar_plantas: ERROR: {e}\n')
        sys.exit(1)
    if a.verificar:
        actual = a.salida.read_text(encoding='utf-8') if a.salida.exists() else ''
        if actual != C.texto_json(datos):
            sys.stderr.write(f'generar_plantas: {C.relativa(a.salida)} no está al día; corra el generador\n')
            sys.exit(1)
        print(f'generar_plantas: {C.relativa(a.salida)} al día')
        return
    escribio = C.escribir_json(a.salida, datos)
    r = datos['resumen']
    print(f'generar_plantas: {"escribió" if escribio else "sin cambios en"} {C.relativa(a.salida)}')
    print('  recintos del programa por nivel: ' + ', '.join(f'{k} {v}' for k, v in r['recintos_por_nivel'].items()))
    print('  no programados: ' + ', '.join(f'{k} {v}' for k, v in r['recintos_no_programados_por_nivel'].items()))
    print('  circulaciones: ' + ', '.join(f'{k} {v}' for k, v in r['circulaciones_por_nivel'].items()))
    print(f'  muros {sum(r["muros_por_nivel"].values())}, puertas {sum(r["puertas_por_nivel"].values())}, '
          f'ventanas {sum(r["ventanas_por_nivel"].values())}; recintos con área libre bajo el mínimo: {r["avisos_area_libre"]}')


if __name__ == '__main__':
    main()
