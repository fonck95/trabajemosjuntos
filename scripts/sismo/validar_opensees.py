#!/usr/bin/env python3
"""Validación del motor sísmico (web/js/sismo/) con OpenSees 3.8 y la misma idealización (contrato de la torre, 7.9).

Uso (venv con scripts/sismo/requisitos_validacion.txt: openseespy==3.8.0 y numpy; Node ≥ 18 en el PATH):
    python scripts/sismo/validar_opensees.py               # casos de control y torre; escribe data/sismo/validacion_opensees.json
    python scripts/sismo/validar_opensees.py --solo control
    python scripts/sismo/validar_opensees.py --salida otra.json

El registro, a0, a1 y las propiedades que el motor usa de verdad salen de `node scripts/sismo/exportar_caso.mjs`
(este programa no reimplementa la síntesis ni las reglas de las secciones). Sale con código 1 si algún criterio del
7.9 no se cumple.

Réplica de la idealización (modelo 3D, ndm 3, ndf 6; lo mismo que dice ESQUEMA.md):
- Cada pórtico tiene sus propios nodos (como TABS). Los nodos de cada nivel son esclavos de `rigidDiaphragm 3` con
  el maestro en el centro de masa: `mass(m, m, 0, 0, 0, Jz)` y `fix(0, 0, 1, 1, 1, 0)`. En los esclavos no se
  restringe ux, uy ni rz; solo el giro fuera del plano (rx en los pórticos X, ry en los Y). Inercia fuera del plano y
  torsión de los elementos despreciables (Iy = J = 10⁻⁶·I). Bases empotradas en los 6 gdl.
- Parte elástica: `ElasticTimoshenkoBeam` con E, G = E/(2(1 + ν)), A, I·factor_fisuracion y Av sobre la longitud
  flexible L_f; brazos rígidos como `elasticBeamColumn` 10³ veces más rígidos entre el nudo y la cara (no
  `rigidLink`, que chocaría con el diafragma).
- Rótulas: `zeroLength` rotacional entre la cara y el nodo interno del elemento elástico, sin Rayleigh, con
  k0 = 10³·k_e (k_e = 6EI/L_f, o EI/lp en la base de los muros, la misma del motor) y pendiente después de la
  fluencia b·k0 = α·k_e = H. Simétricas: `Steel01(My_e, k0, b = α/10³)`. Asimétricas (vigas y muros, E3):
  `Parallel(ElasticPP(k0 − H, My_pos/k0, −My_neg/k0), Elastic(H))`, que es el mismo endurecimiento cinemático
  bilineal (un resorte elastoplástico perfecto en paralelo con uno elástico: Masing) con fluencia distinta en cada
  sentido. Los otros 5 gdl de la rótula: `equalDOF` cuando la cara no es esclava del diafragma; si lo es (nudo sin
  brazo), el nodo interno también es esclavo del mismo diafragma (mismo punto: mismos ux, uy, rz) y uz se une con un
  resorte de 10¹² kN/m (≥ 10⁵ veces la rigidez axial de cualquier elemento). Motivo, medido en este entorno: con el
  manejador Transformation, un `equalDOF` cuyo nodo retenido es esclavo de `rigidDiaphragm` da desplazamientos
  errados (restricciones encadenadas: 112 % de error en un pórtico de prueba).
- Rayleigh `rayleigh(a0, 0, a1, 0)` con los a0 y a1 del motor (E8); los `zeroLength` no llevan Rayleigh y las
  columnas de gravedad tampoco (región con factores nulos).
- P-Delta con columnas de gravedad: por cada nivel j, 4 pilas articuladas (`geomTransf PDelta`, axial alta, flexión
  despreciable) en CM_j ± r_j en x y en y, r_j = √(Jz_j/m_j), desde el nivel j hasta la base, con W_j/4 cada una y sus
  nodos esclavos del diafragma de cada nivel.
- Gravedad con `loadConst -time 0.0`; `integrator Newmark 0.5 0.25`; `constraints Transformation`.
- Energía amortiguada de OpenSees: a0·∫u̇ᵀMu̇ en los maestros más a1·∫ėᵀK_e ė en la parte elástica de cada elemento,
  con las velocidades de los extremos que da OpenSees (la misma regla del trapecio del motor).
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import openseespy.opensees as ops

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / 'data' / 'sismo' / 'validacion_opensees.json'
G = 9.80665
FACTOR_RIGIDO = 1e3      # brazos y k0 de las rótulas: 10³ veces más rígidos (7.9)
PENAL = 1e12             # kN/m: resorte de uz entre la cara y el nodo interno cuando los dos son esclavos
FUERA = 1e-6             # Iy = J = FUERA·I (fuera del plano y torsión despreciables)


def redondear(x, cifras=6):
    """Redondeo a cifras significativas para que el JSON no cambie por el último bit."""
    if x is None:
        return None
    if isinstance(x, (list, tuple, np.ndarray)):
        return [redondear(v, cifras) for v in x]
    if isinstance(x, dict):
        return {k: redondear(v, cifras) for k, v in x.items()}
    if isinstance(x, (bool, str, int)) and not isinstance(x, (float, np.floating)):
        return x
    x = float(x)
    if x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else None
    return float(f'{x:.{cifras}g}')


def exportar(escenario, salida, *extra, estructura=None):
    """Corre scripts/sismo/exportar_caso.mjs y lee su salida."""
    cmd = ['node', str(RAIZ / 'scripts' / 'sismo' / 'exportar_caso.mjs'), escenario, str(salida), *extra]
    if estructura:
        cmd += ['--estructura', str(estructura)]
    subprocess.run(cmd, cwd=RAIZ, check=True, stdout=subprocess.DEVNULL)
    return json.loads(Path(salida).read_text(encoding='utf-8'))


# =================================================================================================================
# Réplica en OpenSees
# =================================================================================================================
class Replica:
    """Modelo de OpenSees armado con el modelo de referencia que exporta exportar_caso.mjs (caso['modelo'])."""

    def __init__(self, modelo, *, rotulas=True, pdelta=None, factor_rigido=FACTOR_RIGIDO):
        self.m = modelo
        self.rotulas = rotulas
        self.pdelta = modelo['p_delta'] if pdelta is None else pdelta
        self.fr = factor_rigido
        self.porticos = {P['id']: P for P in modelo['porticos']}
        self.port_de = {}
        for P in modelo['porticos']:
            for ie in P['elementos']:
                self.port_de[ie] = P

    # ---- armado -------------------------------------------------------------------------------------------------
    def armar(self, gravedad=True):
        m = self.m
        ops.wipe()
        ops.model('basic', '-ndm', 3, '-ndf', 6)
        # Pórticos X: plano x-z, z local = y global → flexión en el plano alrededor de z local (Iz) y y local en el
        # plano. Pórticos Y: plano y-z, z local = x global. Columnas de gravedad: verticales, con P-Delta.
        ops.geomTransf('Linear', 1, 0.0, 1.0, 0.0)
        ops.geomTransf('Linear', 2, 1.0, 0.0, 0.0)
        ops.geomTransf('PDelta', 3, 1.0, 0.0, 0.0)
        self.sig_nodo = 1
        self.sig_ele = 1
        niveles = m['niveles']
        self.maestro = []
        self.esclavos = [[] for _ in niveles]
        z_nivel = [nv['z'] for nv in niveles]
        for g, nv in enumerate(niveles):
            t = self._nodo(nv['cm'][0], nv['cm'][1], nv['z'])
            ops.fix(t, 0, 0, 1, 1, 1, 0)
            ops.mass(t, nv['masa_t'], nv['masa_t'], 0.0, 0.0, 0.0, nv['Jz_t_m2'])
            self.maestro.append(t)
        # nodos de los pórticos
        self.tag_nodo = {}
        self.nodo_esclavo = {}       # tag → índice del diafragma (o −1)
        self.base = []               # nodos fijos de los pórticos en la base (reacciones = cortante basal)
        self.base_xy = []
        self.apoyo = set()
        g_de_nivel = {}
        for g, nv in enumerate(niveles):
            g_de_nivel[(nv['bloque'], round(nv['z'], 6))] = g
        for P in m['porticos']:
            dirx = P['direccion'] == 'x'
            for n in P['nodos']:
                x, y, z = n['xyz']
                t = self._nodo(x, y, z)
                self.tag_nodo[n['id']] = t
                if n['nivel'] == 0:
                    if n['apoyo'] == 'articulado':
                        # libre solo el giro en el plano
                        ops.fix(t, 1, 1, 1, 0 if not dirx else 1, 0 if dirx else 1, 1)
                    else:
                        ops.fix(t, 1, 1, 1, 1, 1, 1)
                    self.nodo_esclavo[t] = -1
                    self.apoyo.add(t)
                    self.base.append(t)
                    self.base_xy.append((x, y))
                else:
                    self._fijar_fuera(t, dirx)
                    g = self._nivel_de(P, n, g_de_nivel)
                    self.esclavos[g].append(t)
                    self.nodo_esclavo[t] = g
        # elementos
        self.flex = []               # (ie, tag del elástico, nodo i, nodo j, pórtico X?, vertical?)
        self.rot = []                # (ie, extremo, tag zeroLength, k0, H, modelo)
        self.cargas_viga = []
        for ie, e in enumerate(m['elementos']):
            self._elemento(ie, e)
        # columnas de gravedad (P-Delta, E14)
        self.pd_ele = []
        self.pd_tope = []
        if self.pdelta:
            for blq in sorted(set(nv['bloque'] for nv in niveles)):
                gs = [g for g, nv in enumerate(niveles) if nv['bloque'] == blq]
                for jj, gj in enumerate(gs):
                    nv = niveles[gj]
                    r = math.sqrt(nv['Jz_t_m2'] / nv['masa_t'])
                    for dx, dy in ((r, 0.0), (-r, 0.0), (0.0, r), (0.0, -r)):
                        x, y = nv['cm'][0] + dx, nv['cm'][1] + dy
                        abajo = self._nodo(x, y, 0.0)
                        ops.fix(abajo, 1, 1, 1, 1, 1, 1)
                        for gk in gs[: jj + 1]:
                            arriba = self._nodo(x, y, z_nivel[gk])
                            ops.fix(arriba, 0, 0, 0, 1, 1, 0)
                            self.esclavos[gk].append(arriba)
                            t = self._ele()
                            # axial muy alta (EA/L ≈ 10⁹ kN/m) y flexión despreciable (EI = 10⁻⁶ kN·m²: con los
                            # giros fijos, 12EI/h³ ≈ 10⁻⁷ kN/m por pila; con EI = 1 las 4 pilas sumaban 0,7 % al
                            # término de torsión de K_PΔ del caso de control 1)
                            ops.element('elasticBeamColumn', t, abajo, arriba, 1.0, 1e10, 4e9, 1e-16, 1e-16, 1e-16, 3)
                            self.pd_ele.append(t)
                            abajo = arriba
                        self.pd_tope.append((abajo, nv['peso_kN'] / 4.0))
        for g, t in enumerate(self.maestro):
            if self.esclavos[g]:
                ops.rigidDiaphragm(3, t, *self.esclavos[g])
        if gravedad:
            self.gravedad()

    def _nodo(self, x, y, z):
        t = self.sig_nodo
        self.sig_nodo += 1
        ops.node(t, float(x), float(y), float(z))
        return t

    def _ele(self):
        t = self.sig_ele
        self.sig_ele += 1
        return t

    @staticmethod
    def _fijar_fuera(t, dirx):
        # giro fuera del plano: rx en los pórticos X, ry en los Y
        ops.fix(t, 0, 0, 0, 1 if dirx else 0, 0 if dirx else 1, 0)

    @staticmethod
    def _nivel_de(P, n, g_de_nivel):
        return g_de_nivel[(P['bloque'], round(n['z'], 6))]

    def _elemento(self, ie, e):
        P = self.port_de[ie]
        dirx = P['direccion'] == 'x'
        transf = 1 if dirx else 2
        ni, nj = self.tag_nodo[e['i']], self.tag_nodo[e['j']]
        xi = np.array(ops.nodeCoord(ni))
        xj = np.array(ops.nodeCoord(nj))
        L = float(np.linalg.norm(xj - xi))
        u = (xj - xi) / L
        vertical = e['tipo'] != 'viga'
        di, dj = e['di'], e['dj']
        I = e['I_fis']
        E, Gm, A = e['E'], e['G'], e['A']
        # caras (extremos de la parte flexible) y brazos rígidos
        cara_i, cara_j = ni, nj
        if di > 0:
            cara_i = self._nodo(*(xi + di * u))
            self._fijar_fuera(cara_i, dirx)
            self.nodo_esclavo[cara_i] = -1
            self._brazo(ni, cara_i, e, transf)
        if dj > 0:
            cara_j = self._nodo(*(xj - dj * u))
            self._fijar_fuera(cara_j, dirx)
            self.nodo_esclavo[cara_j] = -1
            self._brazo(cara_j, nj, e, transf)
        int_i = self._rotula(ie, 0, e, cara_i, dirx) if (self.rotulas and e['rotula_i']['modelo'] != 'ninguna') else cara_i
        int_j = self._rotula(ie, 1, e, cara_j, dirx) if (self.rotulas and e['rotula_j']['modelo'] != 'ninguna') else cara_j
        t = self._ele()
        if e['Av'] is None:
            ops.element('elasticBeamColumn', t, int_i, int_j, A, E, Gm, FUERA * I, FUERA * I, I, transf)
        else:
            ops.element('ElasticTimoshenkoBeam', t, int_i, int_j, E, Gm, A, FUERA * I, FUERA * I, I, e['Av'], e['Av'], transf)
        self.flex.append((ie, t, int_i, int_j, dirx, vertical))
        if e['w'] != 0:
            # carga de gravedad de la viga hacia abajo: y local = −z global en los pórticos X y +z en los Y
            wy = e['w'] if dirx else -e['w']
            self.cargas_viga.append((t, wy))

    def _brazo(self, a, b, e, transf):
        t = self._ele()
        I = e['I_fis']
        fr = self.fr
        ops.element('elasticBeamColumn', t, a, b, e['A'], fr * e['E'], fr * e['G'], FUERA * I, FUERA * I, I, transf)
        if e['w'] != 0:
            self.cargas_viga.append((t, e['w'] if transf == 1 else -e['w']))

    def _rotula(self, ie, extremo, e, cara, dirx):
        r = e['rotula_i'] if extremo == 0 else e['rotula_j']
        if r['modelo'] != 'bilineal':
            raise SystemExit(f"rótula {r['modelo']} en {e['id']}: la réplica solo trae la bilineal (la torre no usa Clough)")
        xyz = ops.nodeCoord(cara)
        interno = self._nodo(*xyz)
        k0 = self.fr * r['ke']
        H = r['H']
        mat = self._ele() + 500000
        if abs(r['sup'] - r['inf']) <= 1e-9 * r['sup']:
            ops.uniaxialMaterial('Steel01', mat, r['sup'], k0, H / k0)
        else:
            ops.uniaxialMaterial('ElasticPP', mat + 1000000, k0 - H, r['sup'] / k0, -r['inf'] / k0)
            ops.uniaxialMaterial('Elastic', mat + 2000000, H)
            ops.uniaxialMaterial('Parallel', mat, mat + 1000000, mat + 2000000)
        t = self._ele()
        # Orientación: la deformación del material es θp con el signo del esquema (antihorario en el plano del
        # pórtico, s a la derecha): en los pórticos X, θ = −θy global; en los Y, θ = +θx. Con el nodo 1 = cara y el
        # nodo 2 = interno, e = θ2 − θ1 alrededor del eje local: eje +y en X da e = θ_cara − θ_interno = θp; en Y se
        # gira el elemento para que su x local sea −x global (y local = +y global).
        esclava = self.nodo_esclavo.get(cara, -1) >= 0
        if dirx:
            orient = ['-orient', 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
            dir_rot = 5
        else:
            orient = ['-orient', -1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
            dir_rot = 4
        if esclava:
            # cara esclava del diafragma: el interno también (mismo punto: mismos ux, uy, rz); uz con resorte rígido
            pen = self._ele() + 500000
            ops.uniaxialMaterial('Elastic', pen, PENAL)
            self._fijar_fuera(interno, dirx)
            g = self.nodo_esclavo[cara]
            self.esclavos[g].append(interno)
            self.nodo_esclavo[interno] = g
            ops.element('zeroLength', t, cara, interno, '-mat', mat, pen, '-dir', dir_rot, 3, *orient)
        elif cara in self.apoyo:
            # rótula sobre el apoyo (base sin brazo): el nodo interno queda fijo en todo menos el giro de la rótula,
            # así sus reacciones son las fuerzas del elemento (con equalDOF hacia el apoyo, OpenSees no las sumaría
            # a la reacción del apoyo: se pierden en la restricción)
            libre = 5 if dirx else 4
            ops.fix(interno, *[0 if k == libre else 1 for k in range(1, 7)])
            self.nodo_esclavo[interno] = -1
            ops.element('zeroLength', t, cara, interno, '-mat', mat, '-dir', dir_rot, *orient)
            self.base.append(interno)
            self.base_xy.append(tuple(xyz[:2]))
        else:
            self._fijar_fuera(interno, dirx)
            self.nodo_esclavo[interno] = -1
            ops.element('zeroLength', t, cara, interno, '-mat', mat, '-dir', dir_rot, *orient)
            # los gdl que no son la rótula ni el giro fuera del plano (fijo en los dos nodos): ux, uy, uz y rz
            ops.equalDOF(cara, interno, 1, 2, 3, 6)
        self.rot.append((ie, extremo, t, k0, H, r['sup'], r['inf'], 'steel01' if abs(r['sup'] - r['inf']) <= 1e-9 * r['sup'] else 'paralelo'))
        return interno

    # ---- gravedad -----------------------------------------------------------------------------------------------
    def gravedad(self):
        m = self.m
        ops.timeSeries('Linear', 1)
        ops.pattern('Plain', 1, 1)
        for t, wy in self.cargas_viga:
            ops.eleLoad('-ele', t, '-type', '-beamUniform', wy, 0.0)
        for P in m['porticos']:
            for n in P['nodos']:
                if n['carga_kN']:
                    ops.load(self.tag_nodo[n['id']], 0.0, 0.0, -n['carga_kN'], 0.0, 0.0, 0.0)
        for t, W in self.pd_tope:
            ops.load(t, 0.0, 0.0, -W, 0.0, 0.0, 0.0)
        self._sistema()
        ops.test('NormDispIncr', 1e-10, 50)
        ops.algorithm('Newton')
        ops.integrator('LoadControl', 0.1)
        ops.analysis('Static')
        if ops.analyze(10) != 0:
            raise RuntimeError('la gravedad no convergió en OpenSees')
        ops.loadConst('-time', 0.0)
        ops.wipeAnalysis()
        self.u_g = self.desplazamientos()

    @staticmethod
    def _sistema():
        # ProfileSPD (perfil, simétrica definida positiva): en la torre tarda 38 ms por paso frente a 67 de UmfPack,
        # con los mismos resultados (períodos a 10⁻⁹). SparseSYM es más rápido, pero en este entorno da el caso de
        # control 1 errado (97 %) y un valor propio negativo en la torre: no se usa.
        ops.constraints('Transformation')
        ops.numberer('RCM')
        ops.system('ProfileSPD')

    def desplazamientos(self):
        """(ux, uy, rz) de los maestros, 3N."""
        u = []
        for t in self.maestro:
            d = ops.nodeDisp(t)
            u += [d[0], d[1], d[5]]
        return np.array(u)

    def velocidades(self):
        v = []
        for t in self.maestro:
            d = ops.nodeVel(t)
            v += [d[0], d[1], d[5]]
        return np.array(v)

    # ---- rigidez lateral condensada de OpenSees -----------------------------------------------------------------
    def flexibilidad(self):
        """Columnas de la flexibilidad lateral: carga unitaria en cada gdl de cada maestro (estado de gravedad)."""
        nd = 3 * len(self.maestro)
        F = np.zeros((nd, nd))
        dof = (1, 2, 6)
        for a in range(nd):
            g, c = divmod(a, 3)
            ops.timeSeries('Linear', 100 + a)
            ops.pattern('Plain', 100 + a, 100 + a)
            carga = [0.0] * 6
            carga[dof[c] - 1] = 1.0
            ops.load(self.maestro[g], *carga)
            self._sistema()
            ops.test('NormDispIncr', 1e-14, 10)
            ops.algorithm('Linear')
            ops.integrator('LoadControl', 1.0)
            ops.analysis('Static')
            ops.analyze(1)
            F[:, a] = self.desplazamientos() - self.u_g
            ops.integrator('LoadControl', -1.0)
            ops.analysis('Static')
            ops.analyze(1)
            ops.remove('loadPattern', 100 + a)
            ops.wipeAnalysis()
        return 0.5 * (F + F.T)

    # ---- análisis dinámico ----------------------------------------------------------------------------------------
    def dinamico(self, caso, *, dt_salida=0.02, informe=None):
        """Newmark de aceleración promedio con el registro del caso. Devuelve series y envolventes comparables."""
        reg = caso['registro']
        am = caso['amortiguamiento']
        dt = reg['dt']
        n = reg['n'] - 1
        ops.timeSeries('Path', 11, '-dt', dt, '-values', *reg['agx'])
        ops.timeSeries('Path', 12, '-dt', dt, '-values', *reg['agy'])
        ops.pattern('UniformExcitation', 11, 1, '-accel', 11)
        ops.pattern('UniformExcitation', 12, 2, '-accel', 12)
        ops.rayleigh(am['a0'], 0.0, am['a1'], 0.0)
        if self.pd_ele:
            ops.region(1, '-ele', *self.pd_ele, '-rayleigh', 0.0, 0.0, 0.0, 0.0)
        self.tol = 1e-9                    # m: la misma del motor sobre la corrección (‖Δu‖ ≤ 10⁻⁹)
        self.rescates = self.particiones = 0
        self._analisis(self.ALGORITMOS[0])

        m = self.m
        niveles = m['niveles']
        N = len(niveles)
        masa = np.array(m['masa'])
        a0, a1 = am['a0'], am['a1']
        # datos de la parte elástica para la energía amortiguada (mismas f11, f12 y kax del motor)
        el = m['elementos']
        nf = len(self.flex)
        K11 = np.zeros(nf); K12 = np.zeros(nf); K22 = np.zeros(nf); KAX = np.zeros(nf); LF = np.zeros(nf)
        VERT = np.zeros(nf, bool); DIRX = np.zeros(nf, bool)
        nodos_v = []
        for k, (ie, t, a, b, dirx, vert) in enumerate(self.flex):
            e = el[ie]
            det = e['f11'] * e['f11'] - e['f12'] * e['f12']
            K11[k] = e['f11'] / det; K12[k] = -e['f12'] / det; K22[k] = e['f11'] / det
            KAX[k] = e['kax']; LF[k] = e['Lf']; VERT[k] = vert; DIRX[k] = dirx
            nodos_v += [a, b]
        idx_v = {t: i for i, t in enumerate(sorted(set(nodos_v)))}
        lista_v = sorted(idx_v, key=idx_v.get)
        IA = np.array([idx_v[self.flex[k][2]] for k in range(nf)])
        IB = np.array([idx_v[self.flex[k][3]] for k in range(nf)])

        def tasas():
            V = np.array([ops.nodeVel(t) for t in lista_v])         # (nodos, 6)
            # en el plano: s (x en X, y en Y), z y θ antihorario (−θy en X, +θx en Y)
            sa = np.where(DIRX, V[IA, 0], V[IA, 1]); sb = np.where(DIRX, V[IB, 0], V[IB, 1])
            za = V[IA, 2]; zb = V[IB, 2]
            ta = np.where(DIRX, -V[IA, 4], V[IA, 3]); tb = np.where(DIRX, -V[IB, 4], V[IB, 3])
            psi = np.where(VERT, -(sb - sa) / LF, (zb - za) / LF)
            ei = ta - psi
            ej = tb - psi
            dl = np.where(VERT, zb - za, 0.0)
            return ei, ej, dl

        hinges = self.rot
        nh = len(hinges)
        H_k0 = np.array([h[3] for h in hinges]); H_H = np.array([h[4] for h in hinges])
        es_par = np.array([h[7] == 'paralelo' for h in hinges])
        thp_max = np.zeros(nh)
        t_fluye = np.full(nh, -1.0)
        E_hist = 0.0
        def_ant = np.zeros(nh); M_ant = np.zeros(nh)
        for k, h in enumerate(hinges):
            def_ant[k] = ops.eleResponse(h[2], 'basicDeformation')[0]
            M_ant[k] = self._momento(h[2])

        u_hist = np.zeros((n + 1, 3 * N))
        u_hist[0] = self.desplazamientos()
        v_ant = self.velocidades()
        ei0, ej0, dl0 = tasas()
        E_a0 = 0.0
        E_a1 = 0.0
        paso_sal = int(round(dt_salida / dt))
        cortante = []
        t_sal = []
        x0, y0 = niveles[0]['cm']
        for i in range(n):
            if self._avanzar(dt) != 0:
                raise RuntimeError(f'OpenSees no convergió en t = {(i + 1) * dt:.3f} s')
            u_hist[i + 1] = self.desplazamientos()
            v = self.velocidades()
            # a0·M: ∫u̇ᵀ a0 M u̇ dt por trapecios sobre Δu = Δt/2·(u̇_n + u̇_{n+1}) (exacto en Newmark promedio)
            vm = 0.5 * (v + v_ant)
            E_a0 += dt * a0 * float(np.sum(masa * vm * vm))
            v_ant = v
            ei1, ej1, dl1 = tasas()
            si = 0.5 * (ei0 + ei1); sj = 0.5 * (ej0 + ej1); sd = 0.5 * (dl0 + dl1)
            E_a1 += dt * a1 * float(np.sum(K11 * si * si + 2 * K12 * si * sj + K22 * sj * sj + KAX * sd * sd))
            ei0, ej0, dl0 = ei1, ej1, dl1
            # rótulas: θp = deformación − parte elástica (σ/k0 en Steel01; σ_pp/(k0 − H) en el paralelo)
            for k, h in enumerate(hinges):
                d = ops.eleResponse(h[2], 'basicDeformation')[0]
                M = self._momento(h[2])
                E_hist += 0.5 * (M + M_ant[k]) * (d - def_ant[k])
                def_ant[k] = d; M_ant[k] = M
                if es_par[k]:
                    tp = d - (M - H_H[k] * d) / (H_k0[k] - H_H[k])
                else:
                    tp = d - M / H_k0[k]
                a = abs(tp)
                if a > thp_max[k]:
                    thp_max[k] = a
                if t_fluye[k] < 0 and a > 1e-9:
                    t_fluye[k] = (i + 1) * dt
            if (i + 1) % paso_sal == 0:
                cortante.append(self.cortante_basal(x0, y0))
                t_sal.append((i + 1) * dt)
            if informe and (i + 1) % 1000 == 0:
                informe(f'    t = {(i + 1) * dt:.2f} s')
        return {
            'u': u_hist, 'dt': dt, 'cortante': np.array(cortante), 't_salida': np.array(t_sal),
            'E_amortiguada': E_a0 + E_a1, 'E_a0': E_a0, 'E_a1': E_a1, 'E_histeretica': E_hist,
            'thp_max': thp_max, 't_fluye': t_fluye, 'pasos_rescatados': self.rescates, 'pasos_partidos': self.particiones,
        }

    @staticmethod
    def _momento(t):
        return ops.eleResponse(t, 'basicForce')[0]

    # Algoritmos de cada paso, en orden. Newton completo converge en 1 a 3 iteraciones mientras las rótulas no se
    # invierten. Con rótulas de k0 = 10³·k_e, en una inversión el primer tanteo con la tangente comprometida (la de
    # después de la fluencia, α·k_e) salta al otro lado de la superficie y Newton oscila sin converger (medido a
    # t = 3,47 y 4,04 s del caso no lineal de la torre). Entonces se usa Newton-Krylov con la tangente inicial (la
    # elástica, que no salta; la aceleración de Krylov, Carlson y Miller 1998, compensa que no se actualice cuando las
    # rótulas fluyen: 3 a 7 iteraciones donde Newton no convergía en 200), luego Krylov con la tangente del paso y
    # Newton con búsqueda lineal; si nada converge, el paso se parte en 10 (hasta 3 veces). Todos llevan a la misma
    # solución (la prueba con el paso partido en 100 da los mismos desplazamientos).
    # Medido en este entorno: después de un intento fallido, OpenSees 3.8 deja contaminado el análisis (vuelve el
    # dominio al último paso, pero el siguiente algoritmo tampoco converge, ni siquiera el que sí converge desde un
    # análisis limpio); por eso cada intento nuevo arma el análisis otra vez (wipeAnalysis), que parte del estado
    # comprometido de los nodos y los elementos.
    ALGORITMOS = (
        ('Newton',),
        ('KrylovNewton', '-iterate', 'initial', '-increment', 'initial', '-maxDim', 10),
        ('KrylovNewton', '-maxDim', 10),
        ('NewtonLineSearch', '-type', 'Interpolated', '-tol', 0.8),
    )

    def _analisis(self, alg):
        ops.wipeAnalysis()
        self._sistema()
        ops.test('NormDispIncr', self.tol, 100)
        ops.algorithm(*alg)
        ops.integrator('Newmark', 0.5, 0.25)
        ops.analysis('Transient')

    def _avanzar(self, dt, nivel=0):
        """Un paso de Newmark; devuelve 0 si avanzó."""
        ok = ops.analyze(1, dt)
        if ok == 0:
            return 0
        self.rescates += 1
        for alg in self.ALGORITMOS[1:]:
            self._analisis(alg)
            ok = ops.analyze(1, dt)
            if ok == 0:
                break
        self._analisis(self.ALGORITMOS[0])
        if ok == 0 or nivel >= 3:
            return ok
        self.particiones += 1
        for _ in range(10):
            ok = self._avanzar(dt / 10, nivel + 1)
            if ok != 0:
                return ok
        return 0

    def cortante_basal(self, x0, y0):
        """Vx, Vy (kN) y torsor (kN·m, alrededor del CM del nivel 1) de los elementos del entrepiso 1, con su
        amortiguamiento: menos la suma de las reacciones de los nodos de base de los pórticos."""
        # «-dynamic»: fuerzas resistentes con el amortiguamiento de Rayleigh (y la inercia, que en la base es nula);
        # «-rayleigh» daría solo el amortiguamiento
        ops.reactions('-dynamic')
        Vx = Vy = T = 0.0
        for t, (x, y) in zip(self.base, self.base_xy):
            r = ops.nodeReaction(t)
            fx, fy = -r[0], -r[1]
            Vx += fx; Vy += fy
            T += (x - x0) * fy - (y - y0) * fx
        return (Vx, Vy, T)


# =================================================================================================================
# Utilidades de comparación
# =================================================================================================================
def deriva_vectorial(niveles, u):
    """Máximo de √(Δx² + Δy²)/h en los vértices del contorno de cada entrepiso (la misma regla del motor, E9)."""
    N = len(niveles)
    d = np.zeros(N)
    for g, nv in enumerate(niveles):
        ab = nv['abajo']
        mx = 0.0
        for x, y in nv['contorno']:
            dx = u[3 * g] - (y - nv['cm'][1]) * u[3 * g + 2]
            dy = u[3 * g + 1] + (x - nv['cm'][0]) * u[3 * g + 2]
            if ab >= 0:
                nb = niveles[ab]
                dx -= u[3 * ab] - (y - nb['cm'][1]) * u[3 * ab + 2]
                dy -= u[3 * ab + 1] + (x - nb['cm'][0]) * u[3 * ab + 2]
            mx = max(mx, math.hypot(dx, dy) / nv['h'])
        d[g] = mx
    return d


def periodos(K, masa, n=None):
    m = np.asarray(masa)
    S = K / np.sqrt(np.outer(m, m))
    w2, _ = np.linalg.eigh(0.5 * (S + S.T))
    w2 = np.sort(w2)
    T = 2 * np.pi / np.sqrt(w2)
    return T[:n] if n else T


def rel(a, b):
    return abs(a - b) / abs(b) if b != 0 else abs(a - b)


# =================================================================================================================
# Caso de control 1: un piso y tres pórticos contra la condensación pseudotridimensional exacta
# =================================================================================================================
def estructura_control_1():
    """Un piso de 3,5 m, dos pórticos X (y = 0 y y = 6, columnas distintas) y uno Y (x = 0): rigidez excéntrica,
    Timoshenko con Av = 5A/6, columnas con rigidez axial (EA/L) y CM corrido para acoplar ux, uy y rz."""
    def rect(b, h, fis):
        A = b * h
        return {'tipo': 'rectangular', 'b': b, 'h': h, 'material': 'c28', 'A': A, 'I': b * h ** 3 / 12, 'Av': 5 * A / 6,
                'factor_fisuracion': fis, 'My_kNm': 1e6, 'Mn_kNm': 1e6, 'phiMn_kNm': 1e6, 'Mpr_kNm': 1e6, 'theta_y': 0.01,
                'theta_p_cap': 0.03, 'Vn_kN': 1e6, 'phiVn_kN': 1e6, 'endurecimiento': 0.02, 'histeresis': 'bilineal', 'calculo': 'caso de control'}
    sec = {'C40': rect(0.4, 0.4, 0.7), 'C50': rect(0.5, 0.5, 0.7), 'C45': rect(0.45, 0.45, 0.7), 'V30': rect(0.3, 0.5, 0.35)}

    def portico(pid, direc, c, cols, viga, s=(0.0, 6.0)):
        nodos, el = [], []
        for k, sk in enumerate(s):
            nodos += [{'id': f'{pid}/{k}0', 's': sk, 'nivel': 0}, {'id': f'{pid}/{k}1', 's': sk, 'nivel': 1}]
            el.append({'id': f'C-{pid}-{k}', 'tipo': 'columna', 'i': f'{pid}/{k}0', 'j': f'{pid}/{k}1', 'seccion': cols, 'nivel': 1})
        el.append({'id': f'V-{pid}', 'tipo': 'viga', 'i': f'{pid}/01', 'j': f'{pid}/11', 'seccion': viga, 'nivel': 1})
        return {'id': pid, 'direccion': direc, 'coordenada': c, 'nodos': nodos,
                'apoyos': {f'{pid}/{k}0': 'empotrado' for k in range(len(s))}, 'elementos': el}
    return {
        'id': 'control_1', 'nombre': 'Caso de control 1 (7.9): un piso y tres pórticos', 'tipo_dato': 'calculo_propio',
        'sistema_estructural': 'pórticos', 'norma': '—',
        'materiales': {'c28': {'tipo': 'concreto', 'fc_MPa': 28, 'Ec_MPa': 24870, 'nu': 0.2, 'peso_kN_m3': 24}},
        'secciones': sec,
        'bloques': [{'id': 'b', 'niveles': [{'id': 'N1', 'z': 3.5, 'altura_entrepiso': 3.5, 'masa_t': 60.0, 'Jz_t_m2': 60.0 * (6 ** 2 + 6 ** 2) / 12,
                                             'cm': [2.4, 3.6], 'peso_sismico_kN': 60.0 * G, 'contorno': [[0, 0], [6, 0], [6, 6], [0, 6]]}],
                     'porticos': [portico('X-1', 'x', 0.0, 'C40', 'V30'), portico('X-2', 'x', 6.0, 'C50', 'V30'), portico('Y-A', 'y', 0.0, 'C45', 'V30')],
                     'resortes': []}],
        'amortiguamiento': {'tipo': 'rayleigh', 'xi': 0.05, 'periodos_ancla_s': None, 'rigidez': 'inicial_parte_elastica'},
        'p_delta': True, 'limites': {'deriva': 0.01}, 'diseno': {}, 'fuentes': [], 'supuestos': [], 'incertidumbres': [],
    }


def condensacion_exacta(est):
    """Rigidez lateral condensada y K_PΔ del caso de control, armadas aquí sin el motor: rigidez de Timoshenko del
    pórtico plano (Przemieniecki, Theory of Matrix Structural Analysis, 1968, cap. 5) con Φ = 12EI/(G·Av·L²),
    condensación estática de v y θ y compatibilidad del diafragma; P-Delta con las 4 columnas articuladas de cada
    nivel (−(W/4)/h sobre el desplazamiento relativo de cada una)."""
    b = est['bloques'][0]
    nv = b['niveles'][0]
    xc, yc = nv['cm']
    mat = est['materiales']['c28']
    E = mat['Ec_MPa'] * 1000
    Gm = E / (2 * (1 + mat['nu']))
    K = np.zeros((3, 3))
    for P in b['porticos']:
        nodos = {n['id']: n for n in P['nodos']}
        libres = [n['id'] for n in P['nodos'] if n['nivel'] > 0]
        # gdl del pórtico: 0 = lateral del nivel; luego (v, θ) de cada nodo libre
        idx = {nid: 1 + 2 * k for k, nid in enumerate(libres)}
        n = 1 + 2 * len(libres)
        Kp = np.zeros((n, n))
        for e in P['elementos']:
            s = est['secciones'][e['seccion']]
            ni, nj = nodos[e['i']], nodos[e['j']]
            EI = E * s['I'] * s['factor_fisuracion']
            EA = E * s['A']
            if e['tipo'] == 'viga':
                L = nj['s'] - ni['s']
                c, sn = 1.0, 0.0      # x local = +s
            else:
                L = 3.5
                c, sn = 0.0, 1.0      # x local = +z
            Phi = 12 * EI / (Gm * s['Av'] * L ** 2)
            k = np.zeros((6, 6))
            a = EA / L
            k[0, 0] = k[3, 3] = a; k[0, 3] = k[3, 0] = -a
            f = EI / (L ** 3 * (1 + Phi))
            kb = f * np.array([[12, 6 * L, -12, 6 * L], [6 * L, (4 + Phi) * L * L, -6 * L, (2 - Phi) * L * L],
                               [-12, -6 * L, 12, -6 * L], [6 * L, (2 - Phi) * L * L, -6 * L, (4 + Phi) * L * L]])
            ib = [1, 2, 4, 5]
            for p in range(4):
                for q in range(4):
                    k[ib[p], ib[q]] = kb[p, q]
            # T: [u, w, θ] locales desde [d_s, d_z, θ] (θ antihorario en el plano s-z)
            R = np.array([[c, sn, 0], [-sn, c, 0], [0, 0, 1]])
            T = np.zeros((6, 6)); T[:3, :3] = R; T[3:, 3:] = R
            kg = T.T @ k @ T
            # gdl del elemento: [d_i, v_i, θ_i, d_j, v_j, θ_j] → índices del pórtico (−1 = fijo)
            def g(nd):
                if nd['nivel'] == 0:
                    return [-1, -1, -1]
                return [0, idx[nd['id']], idx[nd['id']] + 1]
            gi = g(ni) + g(nj)
            for p in range(6):
                for q in range(6):
                    if gi[p] >= 0 and gi[q] >= 0:
                        Kp[gi[p], gi[q]] += kg[p, q]
        Kll = Kp[:1, :1]; Klc = Kp[:1, 1:]; Kcc = Kp[1:, 1:]
        Kh = Kll - Klc @ np.linalg.solve(Kcc, Klc.T)
        Tp = np.array([[1.0, 0.0, -(P['coordenada'] - yc)]]) if P['direccion'] == 'x' else np.array([[0.0, 1.0, P['coordenada'] - xc]])
        K += Tp.T @ Kh @ Tp
    # P-Delta: 4 columnas articuladas en CM ± r con W/4
    r = math.sqrt(nv['Jz_t_m2'] / nv['masa_t'])
    Kpd = np.zeros((3, 3))
    for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r)):
        x, y = xc + dx, yc + dy
        bx = np.array([1.0, 0.0, -(y - yc)])
        by = np.array([0.0, 1.0, x - xc])
        Kpd -= (nv['peso_sismico_kN'] / 4) / nv['altura_entrepiso'] * (np.outer(bx, bx) + np.outer(by, by))
    return K, Kpd


def control_1(tmp, informe):
    est = estructura_control_1()
    ruta = Path(tmp) / 'control_1.json'
    ruta.write_text(json.dumps(est), encoding='utf-8')
    caso = exportar('ninguno', Path(tmp) / 'caso_control_1.json', estructura=ruta)
    Kex, Kpd_ex = condensacion_exacta(est)
    Km = np.array(caso['modelo']['K_lateral'])
    Kpd_m = np.array(caso['modelo']['K_PDelta'])
    nv = est['bloques'][0]['niveles'][0]
    r = math.sqrt(nv['Jz_t_m2'] / nv['masa_t'])
    F = np.array([100.0, 50.0, 30.0])
    escala = np.array([1.0, 1.0, r])          # rz × r: las tres componentes en metros
    res = {'descripcion': 'Un piso de 3,5 m, pórticos X-1 (y = 0, columnas 0,40 m), X-2 (y = 6, 0,50 m) y Y-A (x = 0, 0,45 m), '
                          'vigas 0,30 × 0,50 m, Timoshenko con Av = 5A/6, CM en (2,4; 3,6); cargas F = (100 kN, 50 kN, 30 kN·m) en el CM.',
           'referencia': 'condensación pseudotridimensional exacta armada en este programa (Timoshenko de Przemieniecki, '
                         'condensación estática y compatibilidad del diafragma; P-Delta con 4 columnas articuladas)',
           'tolerancia': 1e-5, 'casos': []}
    ok_todo = True
    # el motor contra la condensación exacta (matrices)
    eK = float(np.max(np.abs(Km - Kex)) / np.max(np.abs(Kex)))
    ePD = float(np.max(np.abs(Kpd_m - Kpd_ex)) / np.max(np.abs(Kpd_ex)))
    res['motor_K_lateral_error'] = eK
    res['motor_K_PDelta_error'] = ePD
    ok_todo &= eK < 1e-9 and ePD < 1e-9
    for pdelta in (False, True):
        u_ex = np.linalg.solve(Kex + (Kpd_ex if pdelta else 0), F)
        u_mo = np.linalg.solve(Km + (Kpd_m if pdelta else 0), F)
        for rotulas, nombre in ((False, 'elástico (rótulas rígidas, como el motor antes de fluir)'),
                                (True, 'con las rótulas zeroLength de k0 = 10³·k_e (informativo)')):
            R = Replica(caso['modelo'], rotulas=rotulas, pdelta=pdelta)
            R.armar(gravedad=True)
            ops.timeSeries('Linear', 50)
            ops.pattern('Plain', 50, 50)
            ops.load(R.maestro[0], F[0], F[1], 0.0, 0.0, 0.0, F[2])
            Replica._sistema()
            ops.test('NormDispIncr', 1e-14, 10)
            ops.algorithm('Linear')
            ops.integrator('LoadControl', 1.0)
            ops.analysis('Static')
            ops.analyze(1)
            u_os = R.desplazamientos() - R.u_g
            err = float(np.max(np.abs((u_os - u_ex) * escala)) / np.max(np.abs(u_ex * escala)))
            err_m = float(np.max(np.abs((u_mo - u_ex) * escala)) / np.max(np.abs(u_ex * escala)))
            cumple = err < res['tolerancia'] if not rotulas else True
            if not rotulas:
                ok_todo &= cumple and err_m < 1e-9
            res['casos'].append({
                'p_delta': pdelta, 'modelo_opensees': nombre, 'u_exacta': u_ex.tolist(), 'u_opensees': u_os.tolist(), 'u_motor': u_mo.tolist(),
                'error_opensees': err, 'error_motor': err_m, 'cumple': bool(cumple),
            })
            informe(f'  control 1, {"con" if pdelta else "sin"} P-Delta, {nombre}: error OpenSees {err:.2e}, motor {err_m:.2e}')
    # el residuo de la réplica es la rigidez fuera del plano que pide el 7.9 (Iy = J = 10⁻⁶·I): con 10⁻⁹·I baja 1.000 veces
    global FUERA
    guardado = FUERA
    try:
        FUERA = guardado * 1e-3
        R = Replica(caso['modelo'], rotulas=False, pdelta=True)
        R.armar(gravedad=True)
        ops.timeSeries('Linear', 50)
        ops.pattern('Plain', 50, 50)
        ops.load(R.maestro[0], F[0], F[1], 0.0, 0.0, 0.0, F[2])
        Replica._sistema()
        ops.test('NormDispIncr', 1e-14, 10)
        ops.algorithm('Linear')
        ops.integrator('LoadControl', 1.0)
        ops.analysis('Static')
        ops.analyze(1)
        u_os = R.desplazamientos() - R.u_g
        u_ex = np.linalg.solve(Kex + Kpd_ex, F)
        res['error_con_fuera_del_plano_1e-9'] = float(np.max(np.abs((u_os - u_ex) * escala)) / np.max(np.abs(u_ex * escala)))
    finally:
        FUERA = guardado
    informe(f'  control 1 con Iy = J = 10⁻⁹·I (la rigidez fuera del plano explica el residuo): error {res["error_con_fuera_del_plano_1e-9"]:.2e}')
    res['cumple'] = bool(ok_todo)
    return res


# =================================================================================================================
# Caso de control 2: ciclo cuasiestático de una rótula en serie con su parte elástica (tabla de T7)
# =================================================================================================================
T7_TABLA = {
    'bilineal': [(0.01, 100, 0), (0.03, 105.825, 0.019417), (0.019417, 0, 0.019417), (0.01, -94.175, 0.019417),
                 (-0.03, -105.825, -0.019417), (-0.019417, 0, -0.019417), (-0.01, 94.175, -0.019417)],
}


def control_2(informe):
    """Rótula (zeroLength con el material de la réplica) en serie con su parte elástica k_e (zeroLength elástico),
    con el giro total impuesto 0 → 0,030 → −0,030 → 0,030 rad (tabla del 7.8). Se prueban las dos formas de la
    réplica: Steel01 (simétrica) y Parallel(ElasticPP, Elastic) (la de fluencia asimétrica), más una corrida
    asimétrica contra la rótula del motor (rotulaEnSerie de histeresis.js)."""
    My, ke, alfa = 100.0, 1e4, 0.03
    H = alfa * ke
    kpost = ke * H / (ke + H)
    Mp = My + kpost * 0.02
    tp = (Mp - My) / H
    exactos = [0.01, 0.03, tp, tp - (2 * My - Mp) / ke, -0.03, -tp, -tp + (2 * My - Mp) / ke]
    res = {'descripcion': 'Rótula con My = 100 kN·m, k_e = 10⁴ kN·m/rad, α = 0,03; giro total 0 → 0,030 → −0,030 → 0,030 rad.',
           'tolerancia': 0.005, 'formas': []}
    ok_todo = True
    for forma in ('steel01', 'paralelo'):
        lazo = ciclo_serie(forma, My, My, ke, alfa, exactos)
        filas = []
        peor = 0.0
        for (th_t, M_t, tp_t), (th, M, thp) in zip(T7_TABLA['bilineal'], lazo):
            eM = abs(M - M_t) / My
            eP = abs(thp - tp_t) / 0.019417
            peor = max(peor, eM, eP)
            filas.append({'theta': th, 'M_tabla': M_t, 'M_opensees': M, 'thp_tabla': tp_t, 'thp_opensees': thp})
        ok_todo &= peor < res['tolerancia']
        res['formas'].append({'material': 'Steel01(My, k0 = 10³·k_e, b = α/10³)' if forma == 'steel01' else
                              'Parallel(ElasticPP(k0 − H, My/k0, −My/k0), Elastic(H))', 'puntos': filas, 'error_max': peor,
                              'cumple': bool(peor < res['tolerancia'])})
        informe(f'  control 2, {forma}: error máximo {peor:.2e} (de My en M y de 0,019417 rad en θp)')
    # asimétrica: la réplica de las vigas contra la rótula del motor
    Mpos, Mneg = 100.0, 60.0
    ths = [0.01, 0.03, -0.03, 0.03, -0.012, 0.0]
    motor = rotula_motor(Mpos, Mneg, ke, alfa, ths)
    os_ = ciclo_serie('paralelo', Mpos, Mneg, ke, alfa, ths)
    peor = max(abs(a[1] - b['M']) / Mpos for a, b in zip(os_, motor))
    res['asimetrica'] = {'My_pos': Mpos, 'My_neg': Mneg, 'theta': ths, 'M_motor': [b['M'] for b in motor],
                         'M_opensees': [a[1] for a in os_], 'error_max': peor, 'cumple': bool(peor < res['tolerancia'])}
    ok_todo &= peor < res['tolerancia']
    informe(f'  control 2, asimétrica contra el motor: error máximo {peor:.2e}')
    res['cumple'] = bool(ok_todo)
    return res


def ciclo_serie(forma, Mpos, Mneg, ke, alfa, puntos, paso=2e-5, fino=1e-7, n_fino=60):
    """Giro total impuesto por un sp en el extremo; vuelve (θ, M, θp) en cada punto. Pasos de 2·10⁻⁵ rad y, tras
    cada inversión, 60 pasos de 10⁻⁷ rad: con k0 = 10³·k_e, el primer tanteo de Newton con la tangente comprometida
    (después de la fluencia) salta al otro lado de la superficie si el paso es grande."""
    H = alfa * ke
    k0 = FACTOR_RIGIDO * ke
    ops.wipe()
    ops.model('basic', '-ndm', 2, '-ndf', 3)
    for t in (1, 2, 3):
        ops.node(t, 0.0, 0.0)
    ops.fix(1, 1, 1, 1); ops.fix(2, 1, 1, 0); ops.fix(3, 1, 1, 0)
    ops.uniaxialMaterial('Elastic', 1, ke)
    if forma == 'steel01':
        ops.uniaxialMaterial('Steel01', 2, Mpos, k0, H / k0)
    else:
        ops.uniaxialMaterial('ElasticPP', 3, k0 - H, Mpos / k0, -Mneg / k0)
        ops.uniaxialMaterial('Elastic', 4, H)
        ops.uniaxialMaterial('Parallel', 2, 3, 4)
    ops.element('zeroLength', 1, 1, 2, '-mat', 2, '-dir', 3)
    ops.element('zeroLength', 2, 2, 3, '-mat', 1, '-dir', 3)
    # recorrido de θ: pasos que terminan exactamente en cada punto
    th, ruta, marcas, ant = 0.0, [], [], 0.0
    sentido = 0
    for obj in puntos:
        s = 1 if obj > th else -1
        cambio = s != sentido
        sentido = s
        k = 0
        while abs(obj - th) > 1e-15:
            h = fino if (cambio and k < n_fino) else paso
            th = obj if abs(obj - th) <= h else th + s * h
            ruta.append(th)
            k += 1
        marcas.append(len(ruta) - 1)
    ops.timeSeries('Path', 1, '-time', *range(len(ruta) + 1), '-values', 0.0, *ruta)
    ops.pattern('Plain', 1, 1)
    ops.sp(3, 3, 1.0)
    ops.system('BandGeneral'); ops.numberer('Plain'); ops.constraints('Transformation')
    ops.test('NormDispIncr', 1e-15, 50)
    ops.algorithm('Newton')
    ops.integrator('LoadControl', 1.0)
    ops.analysis('Static')
    salida = []
    im = 0
    for k in range(len(ruta)):
        if ops.analyze(1) != 0:
            ops.algorithm('KrylovNewton')
            if ops.analyze(1) != 0:
                raise RuntimeError(f'ciclo de la rótula ({forma}) sin converger en θ = {ruta[k]:.6f}')
            ops.algorithm('Newton')
        if k == marcas[im]:
            M = ops.eleResponse(2, 'basicForce')[0]
            d = ops.eleResponse(1, 'basicDeformation')[0]
            Mh = ops.eleResponse(1, 'basicForce')[0]
            thp = d - (Mh / k0 if forma == 'steel01' else (Mh - H * d) / (k0 - H))
            salida.append((ops.nodeDisp(3, 3), M, thp))
            im += 1
            if im == len(marcas):
                break
    return salida


def rotula_motor(Mpos, Mneg, ke, alfa, puntos):
    """La rótula del motor (rotulaEnSerie de web/js/sismo/histeresis.js) en los mismos puntos."""
    js = ("import { rotulaEnSerie, BILINEAL } from './web/js/sismo/histeresis.js';"
          f"const r = rotulaEnSerie({{ modelo: BILINEAL, My_pos: {Mpos}, My_neg: {Mneg}, alfa: {alfa}, ke: {ke} }});"
          f"const pts = {json.dumps(puntos)}; const out = [];"
          "let th = 0;"
          "for (const p of pts) { const n = 2000; const a = th; for (let s = 1; s <= n; s++) { th = a + (p - a) * s / n; const q = r.imponer(th); if (s === n) out.push(q); } }"
          "console.log(JSON.stringify(out));")
    r = subprocess.run(['node', '--input-type=module', '-e', js], cwd=RAIZ, check=True, capture_output=True, text=True)
    return json.loads(r.stdout)


# =================================================================================================================
# La torre
# =================================================================================================================
def modos_torre(caso, informe):
    R = Replica(caso['modelo'])
    R.armar(gravedad=True)
    F = R.flexibilidad()
    K_os = np.linalg.inv(F)
    masa = np.array(caso['modelo']['masa'])
    T_os = periodos(K_os, masa, 6)
    T_mo = np.array(caso['modelo']['modos']['periodos_s'][:6])
    # eigen de OpenSees sobre el modelo completo (masa solo en los maestros)
    T_eig = None
    try:
        Replica._sistema()
        w2 = ops.eigen('-genBandArpack', 6)
        T_eig = [2 * math.pi / math.sqrt(x) for x in w2]
    except Exception as ex:          # noqa: BLE001 — se informa y se sigue con la flexibilidad condensada
        informe(f'  eigen de OpenSees no disponible ({ex}); se usa la flexibilidad condensada')
    K_mo = np.array(caso['modelo']['K_lateral']) + np.array(caso['modelo']['K_PDelta'])
    eK = float(np.max(np.abs(K_os - K_mo)) / np.max(np.abs(K_mo)))
    e_T = [rel(a, b) for a, b in zip(T_os, T_mo)]
    e_eig = [rel(a, b) for a, b in zip(T_eig, T_mo)] if T_eig else None
    u_g_mo = np.array(caso['modelo']['gravedad']['uD'])
    informe(f'  períodos: motor {np.round(T_mo, 4).tolist()} · OpenSees {np.round(T_os, 4).tolist()} · error máx {max(e_T):.2e}')
    return {
        'periodos_motor_s': T_mo.tolist(), 'periodos_opensees_s': T_os.tolist(), 'periodos_eigen_opensees_s': T_eig,
        'error_periodos': e_T, 'error_periodos_eigen': e_eig, 'error_max': max(e_T + (e_eig or [])), 'tolerancia': 0.01,
        'rigidez_lateral_error_max': eK,
        'gravedad': {'u_motor': u_g_mo.tolist(), 'u_opensees': R.u_g.tolist()},
        'cumple': bool(max(e_T + (e_eig or [])) < 0.01),
        'nota': 'Períodos con la rigidez inicial después de la gravedad, con P-Delta; los de OpenSees salen de la '
                'flexibilidad lateral condensada (3N cargas unitarias en los maestros) y, como control, de eigen.',
    }


def corrida(caso, informe):
    R = Replica(caso['modelo'])
    R.armar(gravedad=True)
    r = R.dinamico(caso, informe=informe)
    niveles = caso['modelo']['niveles']
    N = len(niveles)
    u = r['u']
    # envolventes de OpenSees en cada Δt
    dv = np.max(np.array([deriva_vectorial(niveles, u[i]) for i in range(u.shape[0])]), axis=0)
    umax = np.max(np.abs(u), axis=0)
    mo = caso['motor']
    dv_mo = np.array(mo['envolventes']['deriva_vector_max'])
    umax_mo = np.array(mo['envolventes']['u_max'])
    Vmo = np.array(mo['cortante_basal']).reshape(-1, 3)
    Vos = r['cortante']
    # cortante basal pico (series de salida en los mismos instantes; la del motor empieza en t = 0)
    pico_mo = [float(np.max(np.abs(Vmo[1:, c]))) for c in range(3)]
    pico_os = [float(np.max(np.abs(Vos[:, c]))) for c in range(3)]
    u_mo = np.array(mo['u_completa']).reshape(-1, 3 * N)
    ref = np.max(np.abs(u_mo[:, 3 * (N - 1): 3 * (N - 1) + 2]))
    err_hist = float(np.max(np.abs(u[:, 3 * (N - 1): 3 * (N - 1) + 2] - u_mo[:, 3 * (N - 1): 3 * (N - 1) + 2])) / ref)
    # rótulas: elementos que fluyen y primera fluencia
    el = caso['modelo']['elementos']
    fluyen_os = {}
    for k, h in enumerate(R.rot):
        if r['t_fluye'][k] >= 0:
            ide = el[h[0]]['id']
            fluyen_os[ide] = min(fluyen_os.get(ide, 1e9), r['t_fluye'][k])
    fl_mo = dict((a, b) for a, b in mo['primera_fluencia'])
    A, B = set(fluyen_os), set(fl_mo)
    jac = len(A & B) / len(A | B) if (A | B) else 1.0
    t1_mo = min(fl_mo.values()) if fl_mo else None
    t1_os = min(fluyen_os.values()) if fluyen_os else None
    dif_t = [abs(fluyen_os[k] - fl_mo[k]) for k in A & B]
    Eam_mo = mo['energia_final_kJ']['amortiguada']
    Eh_mo = mo['energia_final_kJ']['histeretica']
    return {
        'escenario': caso['escenario'], 'opciones': {k: caso['opciones'][k] for k in ('dt_s', 'duracion_s', 'escala', 'factor', 'angulo_deg', 'calidad', 'p_delta')},
        'pga_g': [caso['registro']['pga_x_g'], caso['registro']['pga_y_g']],
        'deriva_vector_max': {'motor': dv_mo.tolist(), 'opensees': dv.tolist(), 'error': [rel(a, b) for a, b in zip(dv, dv_mo)]},
        'u_max_cubierta': {'motor': umax_mo[3 * (N - 1): 3 * (N - 1) + 2].tolist(), 'opensees': umax[3 * (N - 1): 3 * (N - 1) + 2].tolist(),
                           'error': [rel(umax[3 * (N - 1) + c], umax_mo[3 * (N - 1) + c]) for c in range(2)]},
        'historia_cubierta_error': err_hist,
        'cortante_basal_pico': {'motor_kN': pico_mo, 'opensees_kN': pico_os, 'error': [rel(a, b) for a, b in zip(pico_os, pico_mo)]},
        'fluencia': {'motor': len(B), 'opensees': len(A), 'comunes': len(A & B), 'jaccard': jac,
                     'solo_motor': sorted(B - A)[:20], 'solo_opensees': sorted(A - B)[:20],
                     't_primera_motor_s': t1_mo, 't_primera_opensees_s': t1_os,
                     'dif_t_primera_s': (abs(t1_os - t1_mo) if (t1_mo is not None and t1_os is not None) else None),
                     'dif_t_por_elemento_s': {'mediana': float(np.median(dif_t)) if dif_t else None, 'maxima': max(dif_t) if dif_t else None,
                                              'fraccion_dentro_de_0_1_s': (sum(d <= 0.1 for d in dif_t) / len(dif_t)) if dif_t else None}},
        'energia_amortiguada_kJ': {'motor': Eam_mo, 'opensees': r['E_amortiguada'], 'opensees_a0': r['E_a0'], 'opensees_a1': r['E_a1'],
                                   'error': rel(r['E_amortiguada'], Eam_mo)},
        'energia_histeretica_kJ': {'motor': Eh_mo, 'opensees': r['E_histeretica'], 'error': rel(r['E_histeretica'], Eh_mo) if Eh_mo > 0 else None},
        'opensees_pasos_rescatados': r['pasos_rescatados'], 'opensees_pasos_partidos': r['pasos_partidos'],
    }


def principal():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--solo', choices=['control', 'torre'], default=None)
    ap.add_argument('--salida', default=str(SALIDA))
    ap.add_argument('--silencio', action='store_true')
    args = ap.parse_args()
    informe = (lambda s: None) if args.silencio else (lambda s: print(s, flush=True))
    import importlib.metadata as md
    salida = {
        'version': 1,
        'generado_por': 'scripts/sismo/validar_opensees.py',
        'contrato': 'ESPECIFICACION_INTEGRACION.md, 7.9',
        'entorno': {'openseespy': md.version('openseespy'), 'numpy': np.__version__},
        'idealizacion': (__doc__.split('Réplica de la idealización')[1]).strip(),
        'criterios': [],
    }
    criterios = salida['criterios']

    def criterio(nombre, valor, tolerancia, ok, detalle=''):
        criterios.append({'criterio': nombre, 'valor': redondear(valor, 4), 'tolerancia': tolerancia, 'cumple': bool(ok), 'detalle': detalle})
        informe(f'{"✓" if ok else "✗"} {nombre}: {valor if not isinstance(valor, float) else f"{valor:.3g}"} (tolerancia {tolerancia}) {detalle}')

    with tempfile.TemporaryDirectory() as tmp:
        if args.solo in (None, 'control'):
            informe('Caso de control 1: un piso y tres pórticos')
            c1 = control_1(tmp, informe)
            salida['control_1'] = redondear(c1, 8)
            e1 = max(c['error_opensees'] for c in c1['casos'] if 'elástico' in c['modelo_opensees'])
            criterio('Control 1: desplazamientos de OpenSees contra la condensación exacta (sin y con P-Delta)', e1, 1e-5, c1['cumple'],
                     f'motor contra la exacta: K {c1["motor_K_lateral_error"]:.1e}, K_PΔ {c1["motor_K_PDelta_error"]:.1e}')
            informe('Caso de control 2: ciclo de una rótula (tabla de T7)')
            c2 = control_2(informe)
            salida['control_2'] = redondear(c2, 8)
            e2 = max([f['error_max'] for f in c2['formas']] + [c2['asimetrica']['error_max']])
            criterio('Control 2: ciclo cuasiestático de la rótula contra la tabla de T7 (y la asimétrica contra el motor)', e2, 0.005, c2['cumple'])
        if args.solo in (None, 'torre'):
            informe('Torre: modelo y períodos')
            caso_e = exportar('nido_2015', Path(tmp) / 'nido.json')
            mt = modos_torre(caso_e, informe)
            salida['torre'] = {'estructura': caso_e['estructura'], 'amortiguamiento': redondear(caso_e['amortiguamiento']),
                               'modos': redondear(mt)}
            criterio('Torre: períodos de los 6 primeros modos', mt['error_max'], 0.01, mt['cumple'])
            informe('Torre: corrida elástica (nido_2015, Δt = 0,005 s)')
            ce = corrida(caso_e, informe)
            salida['torre']['elastica'] = redondear(ce)
            ed = max(ce['deriva_vector_max']['error'])
            ev = max(ce['cortante_basal_pico']['error'][:2])
            criterio('Torre elástica: deriva vectorial máxima por piso', ed, 0.03, ed < 0.03)
            criterio('Torre elástica: cortante basal pico (Vx, Vy)', ev, 0.03, ev < 0.03)
            informe('Torre: corrida no lineal (local_hip con la escala «nivel de diseño NSR-10»)')
            caso_n = exportar('local_hip', Path(tmp) / 'local.json', '--escala', 'nsr10')
            cn = corrida(caso_n, informe)
            salida['torre']['no_lineal'] = redondear(cn)
            eu = max(cn['u_max_cubierta']['error'])
            ed = max(cn['deriva_vector_max']['error'])
            fl = cn['fluencia']
            criterio('Torre no lineal: desplazamiento máximo de la cubierta (x, y)', eu, 0.10, eu < 0.10)
            criterio('Torre no lineal: deriva vectorial máxima por piso', ed, 0.10, ed < 0.10)
            criterio('Torre no lineal: elementos que fluyen (índice de Jaccard)', fl['jaccard'], '≥ 0,8', fl['jaccard'] >= 0.8,
                     f'motor {fl["motor"]}, OpenSees {fl["opensees"]}, comunes {fl["comunes"]}')
            criterio('Torre no lineal: primera fluencia (s)', fl['dif_t_primera_s'], 0.1,
                     fl['dif_t_primera_s'] is not None and fl['dif_t_primera_s'] <= 0.1,
                     f'motor {fl["t_primera_motor_s"]} s, OpenSees {fl["t_primera_opensees_s"]} s')
            ea = cn['energia_amortiguada_kJ']['error']
            criterio('Torre no lineal: energía amortiguada', ea, 0.05, ea < 0.05)
    salida['cumple_todo'] = all(c['cumple'] for c in criterios)
    Path(args.salida).write_text(json.dumps(salida, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    informe(f'{"Todo cumple" if salida["cumple_todo"] else "HAY CRITERIOS QUE NO CUMPLEN"} · {args.salida}')
    return 0 if salida['cumple_todo'] else 1


if __name__ == '__main__':
    sys.exit(principal())
