#!/usr/bin/env python3
"""Cálculo de referencia independiente del motor sobre scripts/fixtures/torre/estructura_min.json (Anexo A.3).

En la ola 0 el motor JavaScript (web/js/sismo/) todavía no existía y este programa escribió los fixtures del Anexo
A.4. Desde la ola 2 los fixtures (`resultado_min.json`, `serie_elemento_min.json` y el bloque generado de
`trabajador_simulado.js`) los escribe el motor (`node scripts/sismo/fixtures_min.mjs`), y este programa queda como
**segunda implementación** del mismo cálculo: escribe `scripts/fixtures/torre/referencia_min.json` (los Resultados
del 7.6 del mismo caso) y la prueba R0 de `node scripts/sismo/test_motor.mjs` compara el motor con él (10⁻⁶ del
máximo de cada arreglo; D/C, rótulas y thp idénticos). Usa las reglas corregidas del esquema (ola 1): θ0 de la
carga del vano sin el término de cortante y ξ de los modos sin la mampostería (data/sismo/ESQUEMA.md, «Reglas que el
motor asume» y «Amortiguamiento»).

Uso (Python 3 con numpy; ver scripts/sismo/requisitos_validacion.txt):
    python scripts/sismo/referencia_min.py              # escribe scripts/fixtures/torre/referencia_min.json
    python scripts/sismo/referencia_min.py --verificar  # recalcula y compara byte a byte; sale 1 si algo cambió
    python scripts/sismo/referencia_min.py --informe    # además imprime el detalle de la corrida

Qué resuelve (mismas reglas del contrato, 7.4 y data/sismo/ESQUEMA.md):
- Modelo pseudotridimensional (Wilson y Dovey): diafragma rígido por nivel con ux, uy, rz en el centro de masa;
  pórticos planos con v y θ por nodo. Aquí todos los grados de libertad se resuelven juntos en un solo sistema de
  Newton-Raphson (es lo mismo que condensar por complemento de Schur en cada iteración: misma solución).
- Elemento de Giberson: parte elástica de Timoshenko (flexión + cortante, longitud flexible L_f con brazos rígidos),
  carga de gravedad del vano con los giros de viga simplemente apoyada θ0 = w·L_f³/(24EI)·[−1, 1] (el cortante no
  gira la sección en el apoyo: ESQUEMA.md), rigidez axial EA/L_f y rótulas rígido-
  plásticas en los extremos con propiedades esperadas (My_e, asimétricas en vigas) y endurecimiento cinemático
  H = α·6EI_fis/L_f. Retorno al estado admisible 2 × 2 probando los 4 conjuntos activos; tangente consistente.
- Amortiguamiento de Rayleigh a0·M + a1·(parte elástica de cada elemento, también la axial), sin las rótulas,
  con los períodos ancla del cambio E8; M = K_e·(e + a1·ė) dentro de cada elemento.
- P-Delta lineal por nivel con el peso y la posición del centro de masa de cada nivel de encima (E14).
- Gravedad primero (análisis estático), y el dinámico parte de ese estado.
- Newmark de aceleración promedio (γ = 1/2, β = 1/4) con Newton-Raphson completo y partición del paso.
- Balance de energía con las dos igualdades del 7.4; deriva vectorial en los vértices del contorno (E9);
  demanda/capacidad con propiedades esperadas (E16); equipos no anclados (deslizamiento de Coulomb e inicio del
  balanceo, Shenton 1996).

Qué se simplificó (frente al motor que pide el contrato):
- El registro NO es la síntesis estocástica de `params`: es un **pulso de prueba** (rectangular, componente 1 =
  +1 m/s², componente 2 = −0,5 m/s², desde t = 0,005 s) multiplicado por `escala`. Con solo 0,04 s de cálculo
  (nt = 3 del Anexo A.4), ningún acelerograma sintético produce fluencia: la ventana de Saragoni-Hart arranca en
  cero. El campo `params` conserva el escenario por defecto (nido_2015) para que la vista tenga qué mostrar, y
  `origen_registro` dice qué se usó (campo opcional, ESQUEMA.md).
- Solo histéresis bilineal (no Clough) y solo vigas y columnas (no muros de concreto): es lo que trae el fixture.
- Mampostería sin aislar con la envolvente trilineal de Tomaževič y descarga orientada al origen (secante), sin
  degradación cíclica; su energía se reparte en elástica (½·F·Δ) e histerética (el resto).
- Equipos: aceleración media del paso, régimen evaluado con la dirección de la aceleración en el instante de
  aceleración máxima; deslizamiento 2D de Coulomb integrado por tramos de aceleración constante.
- Centro de rigidez de cada nivel: punto donde una fuerza aplicada solo en ese nivel no lo hace girar (flexibilidad
  condensada sin P-Delta).
Todo eso está a la vista abajo; los números de salida van redondeados a Float32 (o a los enteros del 7.6).
"""
import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / 'scripts' / 'fixtures' / 'torre'
G = 9.80665

# ---------------------------------------------------------------------------------------------------------------
# Parámetros de la corrida (los del Anexo A.4)
# ---------------------------------------------------------------------------------------------------------------
DT = 0.005                 # paso de cálculo (s), igual al de la síntesis
DT_SALIDA = 0.02           # paso de salida (s)
DURACION = 0.04            # nt = 3: 0; 0,02; 0,04 s
ESCALA = 25                # multiplica el pulso base
PULSO_BASE = (1.0, -0.5)   # m/s² en las componentes 1 y 2 (antes de la escala)
ANGULO_DEG = 0.0           # componente 1 a lo largo de +x (antihorario desde el este)
TOLERANCIA = 1e-6
MAX_ITER = 20
MAX_SUBDIV = 4
TOL_DU = 1e-9

# Equipos de prueba (EquipoRiesgo del 7.4). Los ids siguen el formato del 1.3 con hash ilustrativo.
EQUIPOS = [
    {'unidad': 'U-consulta_externa-2d1bfe-001', 'piso': 2, 'x': 1.2, 'y': 3.8, 'z_sobre_piso': 0.0, 'anclaje': 'apoyado',
     'masa_kg': 60.0, 'h_cg_m': 0.45, 'mu': 0.3, 'bx_m': 0.30, 'by_m': 0.25, 'rot_z': 0.0},
    {'unidad': 'U-hospitalizacion-5d13f8-001', 'piso': 2, 'x': 4.4, 'y': 0.6, 'z_sobre_piso': 0.0, 'anclaje': 'apoyado',
     'masa_kg': 90.0, 'h_cg_m': 0.95, 'mu': 0.5, 'bx_m': 0.30, 'by_m': 0.20, 'rot_z': math.pi / 2},
    {'unidad': 'U-fijo-91b0de-001', 'piso': 'CUB', 'x': 3.5, 'y': 3.5, 'z_sobre_piso': 0.0, 'anclaje': 'anclado',
     'masa_kg': 200.0, 'h_cg_m': 0.70, 'mu': 0.5, 'bx_m': 0.50, 'by_m': 0.40, 'rot_z': 0.0},
]
ANCLADOS = {'anclado', 'pared', 'cielo', 'en_nucleo'}

# Bits de `rotulas` (7.6)
B_FLU_I, B_FLU_J, B_IO_I, B_IO_J, B_LS_I, B_LS_J, B_CP, B_V = 1, 2, 4, 8, 16, 32, 64, 128


# ---------------------------------------------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------------------------------------------
def armar_modelo(est):
    if len(est['bloques']) != 1:
        raise SystemExit('referencia_min.py resuelve un solo bloque')
    blq = est['bloques'][0]
    niveles = blq['niveles']
    N = len(niveles)
    z = [0.0] + [nv['z'] for nv in niveles]
    nd = 3 * N
    # grados de libertad condensados: v y θ de cada nodo libre
    cond = []          # (nodo_global, 'v'|'t')
    nodos = []         # lista global de nodos en el orden del archivo
    for p in blq['porticos']:
        for n in p['nodos']:
            apoyo = p.get('apoyos', {}).get(n['id'])
            if n['nivel'] == 0 and apoyo is None:
                raise SystemExit(f'nodo de base sin apoyo: {n["id"]}')
            nodos.append({'id': n['id'], 'portico': p['id'], 's': n['s'], 'nivel': n['nivel'], 'apoyo': apoyo})
    idx_nodo = {n['id']: k for k, n in enumerate(nodos)}
    gdl_v, gdl_t = {}, {}
    for k, n in enumerate(nodos):
        if n['apoyo'] == 'empotrado':
            continue
        if n['apoyo'] is None:
            gdl_v[k] = nd + len(cond); cond.append((k, 'v'))
        if n['apoyo'] in (None, 'articulado'):
            gdl_t[k] = nd + len(cond); cond.append((k, 't'))
    ndof = nd + len(cond)

    def fila_lateral(direccion, coord, k):
        """Desplazamiento lateral de una línea de pórtico en el nivel k (fila sobre los gdl)."""
        f = np.zeros(ndof)
        if k == 0:
            return f
        nv = niveles[k - 1]
        xc, yc = nv['cm']
        b = 3 * (k - 1)
        if direccion == 'x':
            f[b] = 1.0; f[b + 2] = -(coord - yc)
        else:
            f[b + 1] = 1.0; f[b + 2] = (coord - xc)
        return f

    porticos = {p['id']: p for p in blq['porticos']}

    def cinematica(k):
        n = nodos[k]
        p = porticos[n['portico']]
        d = fila_lateral(p['direccion'], p['coordenada'], n['nivel'])
        v = np.zeros(ndof); t = np.zeros(ndof)
        if k in gdl_v:
            v[gdl_v[k]] = 1.0
        if k in gdl_t:
            t[gdl_t[k]] = 1.0
        return d, v, t

    mats, secs = est['materiales'], est['secciones']
    elementos = []
    P_g = np.zeros(ndof)
    for p in blq['porticos']:
        for e in p['elementos']:
            if e['tipo'] not in ('columna', 'viga'):
                raise SystemExit(f'referencia_min.py solo resuelve vigas y columnas ({e["id"]} es {e["tipo"]})')
            sec = secs[e['seccion']]
            mat = mats[sec['material']]
            E = mat['Ec_MPa'] * 1000.0
            Gm = E / (2 * (1 + mat['nu']))
            EI = E * sec['I'] * sec['factor_fisuracion']
            GAv = Gm * sec['Av']
            EA = E * sec['A']
            ki, kj = idx_nodo[e['i']], idx_nodo[e['j']]
            ni, nj = nodos[ki], nodos[kj]
            di, dj = e.get('brazo_rigido_m', [0.0, 0.0])
            (dI, vI, tI), (dJ, vJ, tJ) = cinematica(ki), cinematica(kj)
            if e['tipo'] == 'columna':
                L = z[nj['nivel']] - z[ni['nivel']]
                Lf = L - di - dj
                # extremos de la parte flexible: d' = d ∓ brazo·θ ; cuerda ψ = −(d'_j − d'_i)/L_f
                dIf = dI - di * tI
                dJf = dJ + dj * tJ
                cuerda = (dJf - dIf) / Lf          # = −ψ
                a = np.vstack([tI + cuerda, tJ + cuerda, vJ - vI])
                w = 0.0
            else:
                L = nj['s'] - ni['s']
                if L <= 0:
                    raise SystemExit(f'viga con i a la derecha de j: {e["id"]}')
                Lf = L - di - dj
                vIf = vI + di * tI
                vJf = vJ - dj * tJ
                psi = (vJf - vIf) / Lf
                a = np.vstack([tI - psi, tJ - psi, dJ - dI])
                w = e.get('w_gravedad_kN_m', 0.0)
                # cargas de gravedad del vano y de los brazos llevadas a los nodos (trabajo virtual)
                R = w * Lf / 2.0
                P_g -= (R + w * di) * vI + (R * di + w * di * di / 2.0) * tI
                P_g -= (R + w * dj) * vJ - (R * dj + w * dj * dj / 2.0) * tJ
            fe = (Lf / (6 * EI)) * np.array([[2.0, -1.0], [-1.0, 2.0]]) + (1.0 / (GAv * Lf)) * np.ones((2, 2))
            Ke = np.linalg.inv(fe)
            # giros de la viga simplemente apoyada: c = w·L_f³/(24EI). El cortante no gira la sección en el apoyo
            # (trabajo virtual: ∫V_w·v_i/(G·Av) dx = 0 con v_i = 1/L_f constante y V_w antisimétrico; ESQUEMA.md)
            c0 = w * Lf ** 3 / (24 * EI)
            alfa = sec.get('endurecimiento', 0.0) or 1e-4
            ke = 6 * EI / Lf
            My = sec.get('My_e_kNm', sec['My_kNm'])
            if e['tipo'] == 'viga':
                Mpos = sec.get('My_e_pos_kNm', My); Mneg = sec.get('My_e_neg_kNm', My)
                # momento de extremo antihorario positivo: en i, M > 0 tracciona arriba (negativo de flexión)
                sup = np.array([Mneg, Mpos]); inf = np.array([Mpos, Mneg])
            else:
                sup = np.array([My, My]); inf = np.array([My, My])
            elementos.append({
                'id': e['id'], 'tipo': e['tipo'], 'portico': p['id'], 'nivel': e['nivel'], 'fisico': e.get('fisico', e['id']),
                'i': e['i'], 'j': e['j'], 'seccion': e['seccion'], 'a': a, 'L': L, 'Lf': Lf, 'w': w, 'EI': EI, 'EA': EA,
                'Ke': Ke, 'kax': EA / Lf, 'th0': np.array([-c0, c0]), 'H': np.array([alfa * ke, alfa * ke]),
                'sup': sup, 'inf': inf, 'Mn_e': sec['Mn_e_kNm'], 'Vn_e': sec['Vn_e_kN'],
                'IO': sec['theta_p_IO'], 'LS': sec['theta_p_LS'], 'CP': sec['theta_p_CP'],
            })
    for p in blq['porticos']:
        for n in p['nodos']:
            if 'carga_kN' in n:
                _, v, _ = cinematica(idx_nodo[n['id']])
                P_g -= n['carga_kN'] * v

    # resortes de mampostería
    muros = []
    for r in blq.get('resortes', []):
        if r['tipo'] != 'muro_mamposteria':
            continue
        k = r['nivel']
        b = fila_lateral(r['direccion'], r['coordenada'], k) - fila_lateral(r['direccion'], r['coordenada'], k - 1)
        muros.append({'id': r['id'], 'aislado': r.get('aislado', False), 'b': b, 'env': r['envolvente'], 'h': niveles[k - 1]['altura_entrepiso'],
                      'estados': r['estados_de_dano'], 'nivel': k, 'direccion': r['direccion'], 'coordenada': r['coordenada']})

    # masas
    mdiag = np.zeros(ndof)
    iota_x, iota_y = np.zeros(ndof), np.zeros(ndof)
    for k, nv in enumerate(niveles):
        mdiag[3 * k] = mdiag[3 * k + 1] = nv['masa_t']
        mdiag[3 * k + 2] = nv['Jz_t_m2']
        iota_x[3 * k] = 1.0; iota_y[3 * k + 1] = 1.0

    # P-Delta por nivel (E14): 4 columnas articuladas equivalentes en CM_j ± r_j
    Kpd = np.zeros((ndof, ndof))
    if est.get('p_delta', True):
        for k in range(1, N + 1):
            h = niveles[k - 1]['altura_entrepiso']
            for j in range(k, N + 1):
                nj_ = niveles[j - 1]
                xj, yj = nj_['cm']
                W = nj_['peso_sismico_kN']
                bx = fila_lateral('x', yj, k) - fila_lateral('x', yj, k - 1)
                by = fila_lateral('y', xj, k) - fila_lateral('y', xj, k - 1)
                br = np.zeros(ndof)
                br[3 * (k - 1) + 2] = 1.0
                if k > 1:
                    br[3 * (k - 2) + 2] = -1.0
                Kpd -= (W / h) * (np.outer(bx, bx) + np.outer(by, by) + (nj_['Jz_t_m2'] / nj_['masa_t']) * np.outer(br, br))

    return {'est': est, 'niveles': niveles, 'N': N, 'nd': nd, 'ndof': ndof, 'nodos': nodos, 'gdl_v': gdl_v, 'gdl_t': gdl_t,
            'elementos': elementos, 'muros': muros, 'P_g': P_g, 'mdiag': mdiag, 'iota_x': iota_x, 'iota_y': iota_y,
            'Kpd': Kpd, 'z': z, 'porticos': blq['porticos'], 'fila_lateral': fila_lateral, 'ncond': len(cond)}


# ---------------------------------------------------------------------------------------------------------------
# Elemento de Giberson con amortiguamiento de su parte elástica
# ---------------------------------------------------------------------------------------------------------------
def estado_inicial_elemento():
    return {'thp': np.zeros(2), 'e': np.zeros(2), 'ed': np.zeros(2), 'dl': 0.0, 'dld': 0.0}


def respuesta_elemento(el, est, q, dt, a1):
    """q = deformaciones básicas (θ_i, θ_j, δ). dt = None para el análisis estático (sin amortiguamiento)."""
    Ke, kax = el['Ke'], el['kax']
    if dt is None:
        Kt_el, h, kaxt, hax = Ke, np.zeros(2), kax, 0.0
    else:
        fac = 1.0 + 2.0 * a1 / dt
        Kt_el = fac * Ke
        h = -a1 * (Ke @ (2.0 * est['e'] / dt + est['ed']))
        kaxt = fac * kax
        hax = -a1 * kax * (2.0 * est['dl'] / dt + est['dld'])
    th = q[:2] - el['th0']
    thp_n = est['thp']
    H = el['H']
    beta_n = H * thp_n
    Mtr = Kt_el @ (th - thp_n) + h
    rel = Mtr - beta_n
    eps = 1e-9 * max(1.0, float(np.max(el['sup'])))
    elegido = None
    for S in ((), (0,), (1,), (0, 1)):
        dthp = np.zeros(2)
        signos = np.array([1.0 if rel[k] >= 0 else -1.0 for k in range(2)])
        if S:
            idx = list(S)
            lim = np.array([el['sup'][k] if signos[k] > 0 else el['inf'][k] for k in idx])
            A = Kt_el[np.ix_(idx, idx)] + np.diag(H[idx])
            bvec = rel[idx] - signos[idx] * lim
            dthp[idx] = np.linalg.solve(A, bvec)
            if np.any(signos[idx] * dthp[idx] < -1e-14):
                continue
        M = Mtr - Kt_el @ dthp
        beta = beta_n + H * dthp
        ok = True
        for k in range(2):
            if k in S:
                continue
            r = M[k] - beta[k]
            if r > el['sup'][k] + eps or r < -el['inf'][k] - eps:
                ok = False
        if ok:
            elegido = (S, dthp, M)
            break
    if elegido is None:
        raise RuntimeError(f'sin conjunto activo admisible en {el["id"]}')
    S, dthp, M = elegido
    f = np.linalg.inv(Kt_el)
    for k in S:
        f[k, k] += 1.0 / H[k]
    Kt = np.linalg.inv(f)
    thp = thp_n + dthp
    e = th - thp
    dl = q[2]
    N = kaxt * dl + hax
    Kt3 = np.zeros((3, 3))
    Kt3[:2, :2] = Kt
    Kt3[2, 2] = kaxt
    return {'Q': np.array([M[0], M[1], N]), 'Kt3': Kt3, 'thp': thp, 'e': e, 'dl': dl, 'activas': S}


def cerrar_elemento(el, est, tr, dt, a1):
    """Estado comprometido del paso y la parte de amortiguamiento de los momentos (para la energía)."""
    e_new, dl_new = tr['e'], tr['dl']
    if dt is None:
        ed, dld = np.zeros(2), 0.0
    else:
        ed = 2.0 * (e_new - est['e']) / dt - est['ed']
        dld = 2.0 * (dl_new - est['dl']) / dt - est['dld']
    return {'thp': tr['thp'], 'e': e_new, 'ed': ed, 'dl': dl_new, 'dld': dld}


# ---------------------------------------------------------------------------------------------------------------
# Mampostería: envolvente trilineal (Tomaževič) con descarga orientada al origen
# ---------------------------------------------------------------------------------------------------------------
def envolvente_muro(env, x):
    """Fuerza y pendiente de la envolvente para x = |Δ| ≥ 0."""
    k0 = env['Vcr_kN'] / env['dcr_m']
    pts = [(0.0, 0.0), (env['dcr_m'], env['Vcr_kN']), (env['dmax_m'], env['Vmax_kN']), (env['du_m'], env['Vmax_kN']),
           (1.2 * env['du_m'], env['residual'] * env['Vmax_kN'])]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x <= x1:
            pend = (y1 - y0) / (x1 - x0)
            return y0 + pend * (x - x0), pend
    return pts[-1][1], 0.0 if x > 0 else k0


def respuesta_muro(mu, est, Delta):
    if mu['aislado']:
        return 0.0, 0.0, est['dmax']
    x = abs(Delta)
    if x >= est['dmax']:
        F, k = envolvente_muro(mu['env'], x)
        return math.copysign(F, Delta), k, x
    Fm, _ = envolvente_muro(mu['env'], est['dmax'])
    ks = Fm / est['dmax']
    return ks * Delta, ks, est['dmax']


# ---------------------------------------------------------------------------------------------------------------
# Ensamble
# ---------------------------------------------------------------------------------------------------------------
def ensamblar(mod, u, est_el, est_mu, dt, a1):
    ndof = mod['ndof']
    F = np.zeros(ndof)
    K = np.zeros((ndof, ndof))
    tr_el = []
    for el, st in zip(mod['elementos'], est_el):
        q = el['a'] @ u
        tr = respuesta_elemento(el, st, q, dt, a1)
        F += el['a'].T @ tr['Q']
        K += el['a'].T @ tr['Kt3'] @ el['a']
        tr_el.append(tr)
    tr_mu = []
    for mu, st in zip(mod['muros'], est_mu):
        D = float(mu['b'] @ u)
        Fm, km, dmax = respuesta_muro(mu, st, D)
        F += Fm * mu['b']
        K += km * np.outer(mu['b'], mu['b'])
        tr_mu.append({'F': Fm, 'D': D, 'dmax': dmax})
    return F, K, tr_el, tr_mu


def gravedad(mod):
    ndof = mod['ndof']
    u = np.zeros(ndof)
    est_el = [estado_inicial_elemento() for _ in mod['elementos']]
    est_mu = [{'dmax': 0.0} for _ in mod['muros']]
    n_inc = 5
    for inc in range(1, n_inc + 1):
        P = mod['P_g'] * inc / n_inc
        for it in range(MAX_ITER):
            F, K, tr_el, tr_mu = ensamblar(mod, u, est_el, est_mu, None, 0.0)
            R = P - F - mod['Kpd'] @ u
            if np.max(np.abs(R)) <= TOLERANCIA * max(np.max(np.abs(P)), 1.0) and it > 0:
                break
            du = np.linalg.solve(K + mod['Kpd'], R)
            u += du
        est_el = [cerrar_elemento(el, st, tr, None, 0.0) for el, st, tr in zip(mod['elementos'], est_el, tr_el)]
        est_mu = [{'dmax': t['dmax']} for t in tr_mu]
    F, K, tr_el, tr_mu = ensamblar(mod, u, est_el, est_mu, None, 0.0)
    return u, est_el, est_mu, tr_el, tr_mu


# ---------------------------------------------------------------------------------------------------------------
# Modos, centro de rigidez y amortiguamiento (E8)
# ---------------------------------------------------------------------------------------------------------------
def rigidez_condensada(mod, u_g, est_el, est_mu, con_pdelta, con_muros=True):
    _, K, _, tr_mu = ensamblar(mod, u_g, est_el, est_mu, None, 0.0)
    if not con_muros:
        # sin la mampostería (no lleva amortiguamiento de Rayleigh): se resta su tangente
        for mu, st in zip(mod['muros'], est_mu):
            _, km, _ = respuesta_muro(mu, st, float(mu['b'] @ u_g))
            K = K - km * np.outer(mu['b'], mu['b'])
    if con_pdelta:
        K = K + mod['Kpd']
    nd = mod['nd']
    Kdd, Kdc, Kcc = K[:nd, :nd], K[:nd, nd:], K[nd:, nd:]
    return Kdd - Kdc @ np.linalg.solve(Kcc, Kdc.T)


def modos(mod, KL):
    nd, N = mod['nd'], mod['N']
    m = mod['mdiag'][:nd]
    Mi = 1.0 / np.sqrt(m)
    A = (Mi[:, None] * KL) * Mi[None, :]
    w2, V = np.linalg.eigh((A + A.T) / 2)
    orden = np.argsort(w2)
    w2, V = w2[orden], V[:, orden]
    phi = Mi[:, None] * V            # normalizados con φᵀMφ = 1
    for r in range(nd):              # signo determinista: la componente de mayor valor absoluto es positiva
        k = int(np.argmax(np.abs(phi[:, r])))
        if phi[k, r] < 0:
            phi[:, r] *= -1
    ix = np.zeros(nd); iy = np.zeros(nd); ir = np.zeros(nd)
    ix[0::3] = 1; iy[1::3] = 1; ir[2::3] = 1
    Mx = float(np.sum(m[0::3])); My_ = float(np.sum(m[1::3])); Mr = float(np.sum(m[2::3]))
    gam = {'x': phi.T @ (m * ix), 'y': phi.T @ (m * iy), 'rz': phi.T @ (m * ir)}
    part = {'x': gam['x'] ** 2 / Mx, 'y': gam['y'] ** 2 / My_, 'rz': gam['rz'] ** 2 / Mr}
    w = np.sqrt(np.maximum(w2, 0.0))
    T = 2 * math.pi / w
    rx = int(np.argmax(part['x'])); ry = int(np.argmax(part['y']))
    return {'T': T, 'w': w, 'phi': phi, 'part': part, 'T1x': float(T[rx]), 'T1y': float(T[ry])}


def amortiguamiento(md, KL_el, m, xi):
    """Rayleigh de la parte elástica (E8) con ξ exacto en las dos anclas (ESQUEMA.md, «Amortiguamiento»):
    ξ_r = (a0 + a1·k_r)/(2ω_r), k_r = φ_rᵀ·K_el·φ_r (φ normalizado a la masa; K_el sin mampostería ni P-Delta).
    Con ρ = k/ω² en cada ancla (interpolada linealmente en ln ω entre modos vecinos si el ancla no es un modo):
    a1 = 2ξ(ωj − ωi)/(ρj·ωj² − ρi·ωi²), a0 = 2ξ·ωi − a1·ρi·ωi². Con ρ = 1 es la fórmula de siempre."""
    T = md['T']
    T1 = float(T[0])
    cx = np.cumsum(md['part']['x']); cy = np.cumsum(md['part']['y'])
    r90 = len(T) - 1
    for r in range(len(T)):
        if cx[r] >= 0.9 and cy[r] >= 0.9:
            r90 = r
            break
    Ti, Tj = T1, min(float(T[r90]), 0.2 * T1)
    w = md['w']
    k = np.array([float(md['phi'][:, r] @ KL_el @ md['phi'][:, r]) for r in range(len(T))])
    rho_m = k / w ** 2

    def rho(wa):
        if wa <= w[0]:
            return float(rho_m[0])
        if wa >= w[-1]:
            return float(rho_m[-1])
        r = int(np.searchsorted(w, wa))       # w[r - 1] < wa <= w[r]
        t = math.log(wa / w[r - 1]) / math.log(w[r] / w[r - 1]) if w[r] > w[r - 1] else 0.0
        return float(rho_m[r - 1] + t * (rho_m[r] - rho_m[r - 1]))

    wi, wj = 2 * math.pi / Ti, 2 * math.pi / Tj
    ri, rj = rho(wi), rho(wj)
    a1 = 2 * xi * (wj - wi) / (rj * wj ** 2 - ri * wi ** 2)
    a0 = 2 * xi * wi - a1 * ri * wi ** 2
    xis = [(a0 + a1 * float(k[r])) / (2 * w[r]) for r in range(min(12, len(T)))]
    return {'a0': a0, 'a1': a1, 'periodos_ancla_s': [Ti, Tj], 'xi_modos': xis, 'r90': r90}


def centro_rigidez(mod, KL_el):
    Fl = np.linalg.inv(KL_el)
    cr, exc = [], []
    for k, nv in enumerate(mod['niveles']):
        b = 3 * k
        xc, yc = nv['cm']
        frr = Fl[b + 2, b + 2]
        y = yc + Fl[b + 2, b] / frr
        x = xc - Fl[b + 2, b + 1] / frr
        cr.append([x, y])
        exc.append([x - xc, y - yc])
    return cr, exc


# ---------------------------------------------------------------------------------------------------------------
# Equipos no anclados (7.4)
# ---------------------------------------------------------------------------------------------------------------
def b_psi(eq, a):
    c, s = math.cos(eq['rot_z']), math.sin(eq['rot_z'])
    ax_l = c * a[0] + s * a[1]
    ay_l = -s * a[0] + c * a[1]
    nrm = math.hypot(ax_l, ay_l)
    if nrm == 0:
        return min(eq['bx_m'], eq['by_m'])
    cp, sp = abs(ax_l) / nrm, abs(ay_l) / nrm
    cands = []
    if cp > 1e-12:
        cands.append(eq['bx_m'] / cp)
    if sp > 1e-12:
        cands.append(eq['by_m'] / sp)
    return min(cands)


def regimen_equipo(eq, a):
    if eq['anclaje'] in ANCLADOS:
        return 'anclado'
    rb = b_psi(eq, a) / eq['h_cg_m']
    mu = eq['mu']
    if abs(mu - rb) / max(mu, rb) < 0.10:
        return 'frontera'
    return 'desliza' if mu < rb else 'balancea'


def nivel_equipo(mod, piso):
    """Nivel del diafragma que sostiene al equipo: piso 1 y BT = suelo (0); piso p = nivel p − 1; CUB = cubierta."""
    if piso in (1, 'BT'):
        return 0
    if piso == 'CUB':
        return mod['N']
    return int(piso) - 1


def acel_equipo(mod, eq, acc_rel, ag):
    k = nivel_equipo(mod, eq['piso'])
    if k == 0:
        return np.array(ag, dtype=float)
    nv = mod['niveles'][k - 1]
    xc, yc = nv['cm']
    b = 3 * (k - 1)
    return np.array([acc_rel[b] - (eq['y'] - yc) * acc_rel[b + 2] + ag[0],
                     acc_rel[b + 1] + (eq['x'] - xc) * acc_rel[b + 2] + ag[1]])


def paso_equipo(eq, st, a_ini, a_fin, dt):
    a_fin = np.asarray(a_fin)
    amag = float(np.hypot(*a_fin))
    reg = regimen_equipo(eq, a_fin)
    if amag > st['a_max']:
        st['a_max'] = amag
        st['regimen'] = reg
        st['rb_en_max'] = b_psi(eq, a_fin) / eq['h_cg_m']
    if reg == 'anclado':
        return
    rb = b_psi(eq, a_fin) / eq['h_cg_m']
    if reg in ('balancea', 'frontera') and amag > G * rb:
        st['inicia_balanceo'] = True
    if reg not in ('desliza', 'frontera'):
        return
    am = 0.5 * (np.asarray(a_ini) + a_fin)
    mug = eq['mu'] * G
    am_n = float(np.hypot(*am))
    sd = st['sd']
    sdn = float(np.hypot(*sd))
    if sdn == 0.0:
        if am_n <= mug:
            return
        acc = -(am_n - mug) * am / am_n          # arranca en contra de la aceleración del piso
    else:
        acc = -am - mug * sd / sdn
    sd_new = sd + acc * dt
    if sdn > 0.0 and float(sd_new @ sd) < 0.0:
        # se detiene dentro del paso
        proy = -float(acc @ sd) / sdn
        ts = sdn / proy if proy > 0 else dt
        st['s'] = st['s'] + sd * ts + 0.5 * acc * ts * ts
        st['sd'] = np.zeros(2)
    else:
        st['s'] = st['s'] + sd * dt + 0.5 * acc * dt * dt
        st['sd'] = sd_new
    st['s_max'] = max(st['s_max'], float(np.hypot(*st['s'])))


# ---------------------------------------------------------------------------------------------------------------
# Análisis dinámico
# ---------------------------------------------------------------------------------------------------------------
def registro_pulso():
    n = int(round(DURACION / DT)) + 1
    t = np.arange(n) * DT
    a1 = np.where(np.arange(n) >= 1, PULSO_BASE[0] * ESCALA, 0.0)
    a2 = np.where(np.arange(n) >= 1, PULSO_BASE[1] * ESCALA, 0.0)
    c, s = math.cos(math.radians(ANGULO_DEG)), math.sin(math.radians(ANGULO_DEG))
    ax = c * a1 - s * a2
    ay = s * a1 + c * a2
    return t, ax, ay


def vertices_entrepiso(mod, k):
    return mod['niveles'][k - 1]['contorno']


def cinematica_punto(mod, u, k, x, y):
    if k == 0:
        return 0.0, 0.0
    nv = mod['niveles'][k - 1]
    xc, yc = nv['cm']
    b = 3 * (k - 1)
    return u[b] - (y - yc) * u[b + 2], u[b + 1] + (x - xc) * u[b + 2]


def analizar(mod, u_g, est_el_g, est_mu_g, amort):
    nd, ndof, N = mod['nd'], mod['ndof'], mod['N']
    m = mod['mdiag']
    a0, a1 = amort['a0'], amort['a1']
    Kpd = mod['Kpd']
    els, mus = mod['elementos'], mod['muros']
    nE = len(els)
    t_reg, ax_reg, ay_reg = registro_pulso()
    paso_sal = int(round(DT_SALIDA / DT))

    # estado
    u = u_g.copy()
    v = np.zeros(ndof); acc = np.zeros(ndof)
    acc[:nd] = -(mod['iota_x'] * ax_reg[0] + mod['iota_y'] * ay_reg[0])[:nd]
    est_el = [dict(s) for s in est_el_g]
    est_mu = [dict(s) for s in est_mu_g]
    F0, _, tr_el, tr_mu = ensamblar(mod, u, est_el, est_mu, DT, a1)
    Q_prev = [tr['Q'].copy() for tr in tr_el]
    D_prev = [np.zeros(2) for _ in els]
    Dax_prev = [0.0 for _ in els]
    Fm_prev = [t['F'] for t in tr_mu]
    Fr_prev = (F0 + Kpd @ u)[:nd].copy()
    e_g = [s['e'].copy() for s in est_el]
    dl_g = [s['dl'] for s in est_el]
    uc_g = u[nd:].copy()
    Pg_c = mod['P_g'][nd:]

    E = {'entrada': 0.0, 'a0': 0.0, 'amort_el': 0.0, 'hist': 0.0, 'muro_trabajo': [0.0] * len(mus), 'def': 0.0}
    eq_st = [{'a_max': 0.0, 'regimen': regimen_equipo(eq, [1.0, 0.0]), 'rb_en_max': None, 'inicia_balanceo': False,
              's': np.zeros(2), 'sd': np.zeros(2), 's_max': 0.0} for eq in EQUIPOS]

    # salidas y envolventes
    sal = {k: [] for k in ('t', 'ag', 'u', 'a_abs', 'giros', 'v_nodos', 'dc', 'dc_flexion', 'dc_cortante', 'dc_rotacion',
                           'rotulas', 'thp', 'derivas', 'derivas_vector', 'cortante_basal', 'energia')}
    series = [{k: [] for k in ('Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc')} for _ in els]
    env = {
        'u_max': np.zeros(N * 3), 'deriva_max': np.zeros(N * 2), 't_deriva_max': np.zeros(N * 2),
        'deriva_vector_max': np.zeros(N), 'punto_deriva_vector': np.zeros(N * 2), 't_deriva_vector_max': np.zeros(N),
        'a_abs_max': np.zeros(N * 3), 'dc_max': np.zeros(nE), 't_dc_max': np.zeros(nE), 'gobierna': np.zeros(nE, dtype=int),
        'Mi_max': np.zeros(nE), 'Mj_max': np.zeros(nE), 'V_max': np.zeros(nE), 'N_min': np.full(nE, np.inf), 'N_max': np.full(nE, -np.inf),
        'thp_max': np.zeros(nE * 2), 't_primera_fluencia': np.full(nE * 2, -1.0),
    }
    env_porticos = np.zeros((len(mod['porticos']), N))
    bits_acum = np.zeros(nE, dtype=int)
    muro_dmax = [0.0] * len(mus)
    V_piso_max = np.zeros((N, 2)); D_piso_max = np.zeros((N, 2))
    calidad = {'pasos': 0, 'iter': 0, 'subdivisiones': 0, 'no_convergidos': 0, 'err_e': 0.0, 'err_d': 0.0}
    E_in_max = [0.0]
    historia_thp = []

    def fuerzas_elemento(el, Q):
        Mi, Mj, Nx = Q
        Vm = (Mi + Mj) / el['Lf']
        Vi = Vm - el['w'] * el['Lf'] / 2
        Vj = Vm + el['w'] * el['Lf'] / 2
        V = Vi if abs(Vi) >= abs(Vj) else Vj
        return Mi, Mj, V, Nx

    def evaluar(t, u, v, acc_rel, ag, Q_list, est_list, activas_list, tr_mu, es_salida):
        # envolventes por Δt (y por salida)
        a_abs = acc_rel[:nd].copy()
        a_abs[0::3] += ag[0]; a_abs[1::3] += ag[1]
        env['u_max'] = np.maximum(env['u_max'], np.abs(u[:nd]))
        env['a_abs_max'] = np.maximum(env['a_abs_max'], np.abs(a_abs))
        der = np.zeros((N, 2))
        for ip, p in enumerate(mod['porticos']):
            niveles_p = sorted({n['nivel'] for n in p['nodos']})
            col = 0 if p['direccion'] == 'x' else 1
            for k in range(1, N + 1):
                if k not in niveles_p or (k - 1) not in niveles_p:
                    continue
                h = mod['niveles'][k - 1]['altura_entrepiso']
                fk = mod['fila_lateral'](p['direccion'], p['coordenada'], k)
                fk1 = mod['fila_lateral'](p['direccion'], p['coordenada'], k - 1)
                dr = abs(float((fk - fk1) @ u)) / h
                der[k - 1, col] = max(der[k - 1, col], dr)
                env_porticos[ip, k - 1] = max(env_porticos[ip, k - 1], dr)
        dvec = np.zeros(N)
        for k in range(1, N + 1):
            h = mod['niveles'][k - 1]['altura_entrepiso']
            for (x, y) in vertices_entrepiso(mod, k):
                ux1, uy1 = cinematica_punto(mod, u, k, x, y)
                ux0, uy0 = cinematica_punto(mod, u, k - 1, x, y)
                dv = math.hypot(ux1 - ux0, uy1 - uy0) / h
                if dv > dvec[k - 1]:
                    dvec[k - 1] = dv
                if dv > env['deriva_vector_max'][k - 1]:
                    env['deriva_vector_max'][k - 1] = dv
                    env['punto_deriva_vector'][2 * (k - 1):2 * k] = [x, y]
                    env['t_deriva_vector_max'][k - 1] = t
            for c in range(2):
                if der[k - 1, c] > env['deriva_max'][2 * (k - 1) + c]:
                    env['deriva_max'][2 * (k - 1) + c] = der[k - 1, c]
                    env['t_deriva_max'][2 * (k - 1) + c] = t
        # cortantes por entrepiso (para la base y el índice de estabilidad)
        Vpiso = np.zeros((N, 3))  # Vx, Vy, torsor respecto al CM del nivel inferior... del nivel 1 para la base
        xc1, yc1 = mod['niveles'][0]['cm']
        for el, Q in zip(els, Q_list):
            if el['tipo'] != 'columna':
                continue
            p = next(pp for pp in mod['porticos'] if pp['id'] == el['portico'])
            Vc = (Q[0] + Q[1]) / el['Lf']
            k = el['nivel']
            if p['direccion'] == 'x':
                Vpiso[k - 1, 0] += Vc
                Vpiso[k - 1, 2] += -(p['coordenada'] - yc1) * Vc
            else:
                Vpiso[k - 1, 1] += Vc
                Vpiso[k - 1, 2] += (p['coordenada'] - xc1) * Vc
        for mu, tm in zip(mus, tr_mu):
            k = mu['nivel']
            if mu['direccion'] == 'x':
                Vpiso[k - 1, 0] += tm['F']; Vpiso[k - 1, 2] += -(mu['coordenada'] - yc1) * tm['F']
            else:
                Vpiso[k - 1, 1] += tm['F']; Vpiso[k - 1, 2] += (mu['coordenada'] - xc1) * tm['F']
        for k in range(1, N + 1):
            for c in range(2):
                V_piso_max[k - 1, c] = max(V_piso_max[k - 1, c], abs(Vpiso[k - 1, c]))
            xk, yk = mod['niveles'][k - 1]['cm']
            dx = cinematica_punto(mod, u, k, xk, yk)
            dx0 = cinematica_punto(mod, u, k - 1, xk, yk)
            for c in range(2):
                D_piso_max[k - 1, c] = max(D_piso_max[k - 1, c], abs(dx[c] - dx0[c]))
        # elementos
        dcs = np.zeros((nE, 4))
        bits = np.zeros(nE, dtype=int)
        for ie, (el, Q, st, S) in enumerate(zip(els, Q_list, est_list, activas_list)):
            Mi, Mj, V, Nx = fuerzas_elemento(el, Q)
            thp = st['thp']
            fl = max(abs(Mi), abs(Mj)) / el['Mn_e']
            Vabs = max(abs((Mi + Mj) / el['Lf'] - el['w'] * el['Lf'] / 2), abs((Mi + Mj) / el['Lf'] + el['w'] * el['Lf'] / 2))
            co = Vabs / el['Vn_e']
            ro = max(abs(thp[0]), abs(thp[1])) / el['IO']
            dcm = max(fl, co, ro)
            dcs[ie] = [dcm, fl, co, ro]
            if dcm > env['dc_max'][ie]:
                env['dc_max'][ie] = dcm
                env['t_dc_max'][ie] = t
                env['gobierna'][ie] = int(np.argmax([fl, co, ro]))
            env['Mi_max'][ie] = max(env['Mi_max'][ie], abs(Mi))
            env['Mj_max'][ie] = max(env['Mj_max'][ie], abs(Mj))
            env['V_max'][ie] = max(env['V_max'][ie], Vabs)
            env['N_min'][ie] = min(env['N_min'][ie], Nx)
            env['N_max'][ie] = max(env['N_max'][ie], Nx)
            for k in range(2):
                env['thp_max'][2 * ie + k] = max(env['thp_max'][2 * ie + k], abs(thp[k]))
                if k in S and env['t_primera_fluencia'][2 * ie + k] < 0:
                    env['t_primera_fluencia'][2 * ie + k] = t
            b = 0
            if 0 in S: b |= B_FLU_I
            if 1 in S: b |= B_FLU_J
            if abs(thp[0]) > el['IO']: b |= B_IO_I
            if abs(thp[1]) > el['IO']: b |= B_IO_J
            if abs(thp[0]) > el['LS']: b |= B_LS_I
            if abs(thp[1]) > el['LS']: b |= B_LS_J
            if max(abs(thp[0]), abs(thp[1])) > el['CP']: b |= B_CP
            if Vabs > el['Vn_e']: b |= B_V
            bits[ie] = b
        bits_acum[:] |= bits
        for im, (mu, tm) in enumerate(zip(mus, tr_mu)):
            muro_dmax[im] = max(muro_dmax[im], abs(tm['D']) / mu['h'])
        if not es_salida:
            return
        # salida
        sal['t'].append(t)
        sal['ag'].extend([ag[0], ag[1]])
        sal['u'].extend(u[:nd].tolist())
        sal['a_abs'].extend(a_abs.tolist())
        gir, vn = [], []
        for kn, n in enumerate(mod['nodos']):
            gir.append(float(u[mod['gdl_t'][kn]]) if kn in mod['gdl_t'] else 0.0)
            vn.append(float(u[mod['gdl_v'][kn]]) if kn in mod['gdl_v'] else 0.0)
        sal['giros'].extend(gir)
        sal['v_nodos'].extend(vn)
        for key, c in (('dc', 0), ('dc_flexion', 1), ('dc_cortante', 2), ('dc_rotacion', 3)):
            sal[key].extend([min(255, int(round(100 * x))) for x in dcs[:, c]])
        sal['rotulas'].extend(bits_acum.tolist())
        bits_acum[:] = 0
        historia_thp.append(np.array([s['thp'].copy() for s in est_list]))
        sal['derivas'].extend(der.ravel().tolist())
        sal['derivas_vector'].extend(dvec.tolist())
        sal['cortante_basal'].extend([Vpiso[0, 0], Vpiso[0, 1], Vpiso[0, 2]])
        for ie, (el, Q, st) in enumerate(zip(els, Q_list, est_list)):
            Mi, Mj, V, Nx = fuerzas_elemento(el, Q)
            se = series[ie]
            se['Mi'].append(Mi); se['Mj'].append(Mj); se['V'].append(V); se['N'].append(Nx)
            se['thp_i'].append(st['thp'][0]); se['thp_j'].append(st['thp'][1])
            se['dc'].append(dcs[ie, 0])

    def energias_actuales(u, v, est_list, tr_mu):
        E_cin = 0.5 * float(v[:nd] @ (m[:nd] * v[:nd]))
        E_el = 0.0
        for el, st, eg, dg in zip(els, est_list, e_g, dl_g):
            E_el += 0.5 * (float(st['e'] @ el['Ke'] @ st['e']) - float(eg @ el['Ke'] @ eg))
            E_el += 0.5 * el['kax'] * (st['dl'] ** 2 - dg ** 2)
        E_el -= float(Pg_c @ (u[nd:] - uc_g))
        E_mu_el = sum(0.5 * tm['F'] * tm['D'] for tm in tr_mu)
        E_mu_hist = sum(E['muro_trabajo'][i] - 0.5 * tm['F'] * tm['D'] for i, tm in enumerate(tr_mu))
        W_pd = 0.5 * (float(u[:nd] @ Kpd[:nd, :nd] @ u[:nd]) - float(u_g[:nd] @ Kpd[:nd, :nd] @ u_g[:nd]))
        return E_cin, E_el + E_mu_el, E['hist'] + E_mu_hist, W_pd

    # estado t = 0
    act0 = [tr['activas'] for tr in tr_el]
    evaluar(0.0, u, v, acc, (ax_reg[0], ay_reg[0]), Q_prev, est_el, act0, tr_mu, True)
    sal['energia'].extend([0.0] * 6)

    def un_paso(dt, ag0, ag1, profundidad):
        nonlocal u, v, acc, est_el, est_mu, Q_prev, D_prev, Dax_prev, Fm_prev, Fr_prev
        P = mod['P_g'] - m * (mod['iota_x'] * ag1[0] + mod['iota_y'] * ag1[1])
        un = u.copy()
        uu = u.copy()
        uu[:nd] = u[:nd] + dt * v[:nd] + dt * dt / 4 * acc[:nd]
        du_ult = np.inf
        conv = False
        for it in range(1, MAX_ITER + 1):
            F, K, tr_el, tr_mu = ensamblar(mod, uu, est_el, est_mu, dt, a1)
            ac = np.zeros(ndof); ve = np.zeros(ndof)
            ac[:nd] = 4 / dt ** 2 * (uu[:nd] - un[:nd]) - 4 / dt * v[:nd] - acc[:nd]
            ve[:nd] = 2 / dt * (uu[:nd] - un[:nd]) - v[:nd]
            R = P - F - Kpd @ uu - m * ac - a0 * m * ve
            if np.max(np.abs(R)) <= TOLERANCIA * max(np.max(np.abs(P)), 1.0) and du_ult <= TOL_DU:
                conv = True
                break
            Keff = K + Kpd + np.diag(m * (4 / dt ** 2 + 2 * a0 / dt))
            du = np.linalg.solve(Keff, R)
            uu = uu + du
            du_ult = float(np.max(np.abs(du)))
        calidad['iter'] += it
        if not conv:
            if profundidad >= MAX_SUBDIV:
                calidad['no_convergidos'] += 1
                raise RuntimeError('no_converge')
            calidad['subdivisiones'] += 1
            agm = ((ag0[0] + ag1[0]) / 2, (ag0[1] + ag1[1]) / 2)
            un_paso(dt / 2, ag0, agm, profundidad + 1)
            un_paso(dt / 2, agm, ag1, profundidad + 1)
            return
        calidad['pasos'] += 1
        # cerrar el paso: energías por la regla del trapecio (exacta para Newmark de aceleración promedio)
        du_d = uu[:nd] - un[:nd]
        E['entrada'] += -float(du_d @ (m[:nd] * (mod['iota_x'][:nd] * (ag0[0] + ag1[0]) / 2 + mod['iota_y'][:nd] * (ag0[1] + ag1[1]) / 2)))
        E['a0'] += float(du_d @ (a0 * m[:nd] * (v[:nd] + ve[:nd]) / 2))
        nuevos = []
        for ie, (el, st, tr) in enumerate(zip(els, est_el, tr_el)):
            ns = cerrar_elemento(el, st, tr, dt, a1)
            D = a1 * (el['Ke'] @ ns['ed'])
            Dax = a1 * el['kax'] * ns['dld']
            E['amort_el'] += float((ns['e'] - st['e']) @ (D_prev[ie] + D) / 2) + (ns['dl'] - st['dl']) * (Dax_prev[ie] + Dax) / 2
            E['hist'] += float((ns['thp'] - st['thp']) @ (Q_prev[ie][:2] + tr['Q'][:2]) / 2)
            D_prev[ie], Dax_prev[ie] = D, Dax
            Q_prev[ie] = tr['Q'].copy()
            nuevos.append(ns)
        for im, tm in enumerate(tr_mu):
            D_old = float(mus[im]['b'] @ un)
            E['muro_trabajo'][im] += (tm['D'] - D_old) * (Fm_prev[im] + tm['F']) / 2
            Fm_prev[im] = tm['F']
        Fr = (F + Kpd @ uu)[:nd]
        E['def'] += float(du_d @ (Fr_prev + Fr) / 2)
        Fr_prev = Fr.copy()
        a_ini_eq = [acel_equipo(mod, eq, acc, ag0) for eq in EQUIPOS]
        est_el = nuevos
        est_mu = [{'dmax': tm['dmax']} for tm in tr_mu]
        u = uu
        v = ve
        acc = ac
        for eq, st, ai in zip(EQUIPOS, eq_st, a_ini_eq):
            paso_equipo(eq, st, ai, acel_equipo(mod, eq, acc, ag1), dt)
        # balance
        E_cin, E_el, E_hist, W_pd = energias_actuales(u, v, est_el, tr_mu)
        E_in_max[0] = max(E_in_max[0], abs(E['entrada']))
        ref = max(E_in_max[0], 1e-12)
        err_e = abs(E['entrada'] - (E_cin + E['a0'] + E['amort_el'] + E_el + E_hist + W_pd)) / ref
        err_d = abs(E['def'] - (E_el + E['amort_el'] + E_hist + W_pd)) / ref
        calidad['err_e'] = max(calidad['err_e'], err_e)
        calidad['err_d'] = max(calidad['err_d'], err_d)
        un_paso.ultimo = (tr_el, tr_mu, E_cin, E_el, E_hist, W_pd)   # estado del último subpaso, para evaluar()

    n_pasos = len(t_reg) - 1
    for i in range(n_pasos):
        un_paso(DT, (ax_reg[i], ay_reg[i]), (ax_reg[i + 1], ay_reg[i + 1]), 0)
        tr_el, tr_mu, E_cin, E_el, E_hist, W_pd = un_paso.ultimo
        t = t_reg[i + 1]
        es_sal = (i + 1) % paso_sal == 0
        evaluar(t, u, v, acc, (ax_reg[i + 1], ay_reg[i + 1]), [tr['Q'] for tr in tr_el], est_el, [tr['activas'] for tr in tr_el], tr_mu, es_sal)
        if es_sal:
            sal['energia'].extend([E['entrada'], E_cin, E_el, E['a0'] + E['amort_el'], E_hist, W_pd])

    # índice de estabilidad (NSR-10 A.6.2.3 con envolventes): Q_k = P_k·Δ_k,max / (V_k,max·h_k)
    indice = 0.0
    for k in range(1, N + 1):
        Pk = sum(nv['peso_sismico_kN'] for nv in mod['niveles'][k - 1:])
        h = mod['niveles'][k - 1]['altura_entrepiso']
        for c in range(2):
            if V_piso_max[k - 1, c] > 0:
                indice = max(indice, Pk * D_piso_max[k - 1, c] / (V_piso_max[k - 1, c] * h))

    # equipos
    equipos = []
    for eq, st in zip(EQUIPOS, eq_st):
        reg = st['regimen']
        anclado = reg == 'anclado'
        rb = st['rb_en_max']
        if anclado:
            razon = None
        elif reg == 'desliza':
            razon = min(st['a_max'], eq['mu'] * G) / (G * rb)
        else:
            razon = st['a_max'] / (G * rb)
        equipos.append({
            'unidad': eq['unidad'], 'anclaje': eq['anclaje'], 'regimen': reg, 'a_max_m_s2': st['a_max'],
            'desliza': (not anclado) and st['s_max'] > 0.0, 'deslizamiento_max_m': 0.0 if anclado else st['s_max'],
            'deslizamiento_final_m': 0.0 if anclado else float(np.hypot(*st['s'])),
            'inicia_balanceo': bool(st['inicia_balanceo']), 'razon_vuelco': razon,
            'fuerza_anclaje_kN': eq['masa_kg'] * st['a_max'] / 1000.0 if anclado else None,
        })

    muros = []
    for mu, dmx in zip(mus, muro_dmax):
        estado = 'sin_dano'
        for ed in mu['estados']:
            if dmx >= ed['deriva']:
                estado = ed['nombre']
        muros.append({'id': mu['id'], 'aislado': mu['aislado'], 'deriva_max': dmx, 'estado': estado})

    return {'sal': sal, 'series': series, 'env': env, 'env_porticos': env_porticos, 'equipos': equipos, 'muros': muros,
            'calidad': calidad, 'indice': indice, 'historia_thp': historia_thp, 't_reg': t_reg, 'ax': ax_reg, 'ay': ay_reg}


# ---------------------------------------------------------------------------------------------------------------
# Movimiento del fixture (para el bloque generado de trabajador_simulado.js)
# ---------------------------------------------------------------------------------------------------------------
def nigam_jennings(a, dt, T, xi, n_total):
    """Respuesta exacta de un oscilador a una excitación lineal por tramos (Nigam y Jennings, 1969)."""
    w = 2 * math.pi / T
    wd = w * math.sqrt(1 - xi * xi)
    e = math.exp(-xi * w * dt)
    s, c = math.sin(wd * dt), math.cos(wd * dt)
    a11 = e * (xi / math.sqrt(1 - xi * xi) * s + c)
    a12 = e / wd * s
    a21 = -w / math.sqrt(1 - xi * xi) * e * s
    a22 = e * (c - xi / math.sqrt(1 - xi * xi) * s)
    t1 = (2 * xi * xi - 1) / (w * w * dt)
    t2 = 2 * xi / (w ** 3 * dt)
    b11 = e * ((t1 + xi / w) * s / wd + (t2 + 1 / (w * w)) * c) - t2
    b12 = -e * (t1 * s / wd + t2 * c) - 1 / (w * w) + t2
    b21 = e * ((t1 + xi / w) * (c - xi / math.sqrt(1 - xi * xi) * s) - (t2 + 1 / (w * w)) * (wd * s + xi * w * c)) + 1 / (w * w * dt)
    b22 = -e * (t1 * (c - xi / math.sqrt(1 - xi * xi) * s) - t2 * (wd * s + xi * w * c)) - 1 / (w * w * dt)
    ag = np.zeros(n_total)
    ag[:len(a)] = a
    u = vv = 0.0
    umax = 0.0
    for i in range(n_total - 1):
        u, vv = a11 * u + a12 * vv + b11 * ag[i] + b12 * ag[i + 1], a21 * u + a22 * vv + b21 * ag[i] + b22 * ag[i + 1]
        umax = max(umax, abs(u))
    return w * w * umax, umax


def intensidades(a, dt):
    n = len(a)
    vel = np.concatenate([[0.0], np.cumsum((a[1:] + a[:-1]) / 2 * dt)])
    des = np.concatenate([[0.0], np.cumsum((vel[1:] + vel[:-1]) / 2 * dt)])
    ia = np.concatenate([[0.0], np.cumsum((a[1:] ** 2 + a[:-1] ** 2) / 2 * dt)])
    tot = ia[-1]
    t = np.arange(n) * dt
    t5 = float(np.interp(0.05 * tot, ia, t)) if tot > 0 else 0.0
    t95 = float(np.interp(0.95 * tot, ia, t)) if tot > 0 else 0.0
    return {'pga_g': float(np.max(np.abs(a))) / G, 'pgv_cm_s': float(np.max(np.abs(vel))) * 100, 'pgd_cm': float(np.max(np.abs(des))) * 100,
            'arias_m_s': math.pi / (2 * G) * float(tot), 'd595_s': t95 - t5, 't5_s': t5, 't95_s': t95}


def cargar_gmpe():
    """GMPE de la investigación (fuentes_investigacion/gmpe.py), sin dejar __pycache__ en esa carpeta."""
    sys.dont_write_bytecode = True
    ruta = RAIZ / 'data' / 'sismo' / 'fuentes_investigacion' / 'gmpe.py'
    spec = importlib.util.spec_from_file_location('gmpe_investigacion', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def espectro_nsr10(T, Aa, Av, Fa, Fv, I):
    TC = 0.48 * Av * Fv / (Aa * Fa)
    TL = 2.4 * Fv
    T = np.asarray(T)
    return np.where(T <= TC, 2.5 * Aa * Fa * I, np.where(T <= TL, 1.2 * Av * Fv * I / T, 1.2 * Av * Fv * TL * I / T ** 2))


def movimiento_fixture(amenaza, params, res):
    t, ax, ay = res['t_reg'], res['ax'], res['ay']
    pe = amenaza['parametros_estocasticos']['intraplaca_profunda']
    Mw, h, Re = params['Mw'], params['profundidad_km'], params['distancia_epicentral_km']
    M0 = 10 ** (1.5 * Mw + 16.05)
    ds, beta, rho = pe['delta_sigma_bar']['valor'], pe['beta_s_km_s']['valor'], pe['rho_s_g_cm3']['valor']
    f0 = 4.906e6 * beta * (ds / M0) ** (1 / 3)
    Rhip = math.hypot(Re, h)
    Tgm = 1 / f0 + 0.05 * Rhip
    w = min(max((h - 40) / 30, 0.0), 1.0)
    meta = {'M0_dina_cm': M0, 'M0_N_m': M0 * 1e-7, 'energia_J_aprox': M0 * 1e-7 / 2e4, 'f0_Hz': f0, 'delta_sigma_bar': ds,
            'beta_s_km_s': beta, 'rho_s_g_cm3': rho, 'Q0': pe['Q']['Q0'], 'eta': pe['Q']['eta'], 'kappa0_s': pe['kappa0_s']['valor'],
            'Rhip_km': Rhip, 'Ref_km': Rhip, 'Tgm_s': Tgm, 't_eta_s': 2 * Tgm,
            'regimen': 'intraplaca_profunda' if w >= 1 else ('cortical' if w <= 0 else 'transicion'), 'w_transicion': w, 'pga_roca_g': None}
    Ts = np.exp(np.linspace(math.log(0.02), math.log(5.0), 60))
    n_tot = len(ax) + int(round(8.0 / DT))
    Sa_x = [nigam_jennings(ax, DT, T, 0.05, n_tot)[0] / G for T in Ts]
    Sa_y = [nigam_jennings(ay, DT, T, 0.05, n_tot)[0] / G for T in Ts]
    nf = 1024
    Fx = np.abs(np.fft.rfft(ax, nf)) * DT
    Fy = np.abs(np.fft.rfft(ay, nf)) * DT
    f = np.arange(len(Fx)) / (nf * DT)
    gm = cargar_gmpe()
    Tg = [0.0, 0.2, 0.5, 1.0]
    imts = ['pga', 0.2, 0.5, 1.0]
    bc = [gm.bchydro_slab(i, Mw, Rhip, h, params['vs30_m_s']) for i in imts]
    zh = [gm.zhao06_slab(i, Mw, Rhip, h, params['vs30_m_s']) for i in imts]
    est = res['est']
    d = est['diseno']
    con_I = espectro_nsr10(Ts, d['Aa'], d['Av'], d['Fa'], d['Fv'], d['I'])
    sin_I = espectro_nsr10(Ts, d['Aa'], d['Av'], d['Fa'], d['Fv'], 1.0)
    Ad = amenaza['nsr10']['Ad']['valor']
    umbral = espectro_nsr10(Ts, Ad, Ad, d['Fa'], d['Fv'], 1.0)
    return {
        'tipo': 'movimiento', 'id': 'prueba',
        'registro': {'dt': DT, 'n': len(ax), 'ax': ax.tolist(), 'ay': ay.tolist(), 'meta': meta,
                     'intensidades': {'x': intensidades(ax, DT), 'y': intensidades(ay, DT)},
                     'avisos': ['Trabajador simulado: el registro es el pulso de prueba del fixture (escala ×%g), no la síntesis de estos parámetros.' % ESCALA,
                                'Espectro de umbral de daño con la forma del de diseño y Ad (forma de A.12.3 por confirmar).']},
        'espectro': {'T': Ts.tolist(), 'Sa_x': Sa_x, 'Sa_y': Sa_y},
        'fourier': {'f': f[1:].tolist(), 'A_x': Fx[1:].tolist(), 'A_y': Fy[1:].tolist()},
        'gmpe': [{'nombre': 'BC Hydro 2016 (intraplaca)', 'peso': 0.5, 'T': Tg, 'mediana_g': [b[0] for b in bc], 'sigma_ln': [b[1] for b in bc]},
                 {'nombre': 'Zhao et al. 2006 (intraplaca)', 'peso': 0.5, 'T': Tg, 'mediana_g': [z_[0] for z_ in zh], 'sigma_ln': [z_[1] for z_ in zh]}],
        'nsr10': {'T': Ts.tolist(), 'con_I': con_I.tolist(), 'sin_I': sin_I.tolist(), 'umbral_dano': umbral.tolist()},
    }


# ---------------------------------------------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------------------------------------------
RUIDO = 1e-12   # |x| menor que esto es ruido de redondeo del análisis de gravedad (m, rad, kN, kJ): se escribe 0


def f32(x):
    """Número redondeado a Float32, escrito con la representación más corta que lo recupera."""
    v = float(np.float32(x))
    if abs(v) < RUIDO:
        return 0.0
    return float(str(np.float32(v)))


def corto(x, cifras=7):
    if x is None:
        return None
    if abs(x) < RUIDO:
        return 0.0
    return float(f'{x:.{cifras}g}')


def a_json(obj, sangria=0):
    """JSON legible: listas de números en una línea; objetos con una clave por línea."""
    esp = '  ' * sangria
    if isinstance(obj, dict):
        if not obj:
            return '{}'
        if sangria >= 2 and all(not isinstance(v, dict) and not (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v))
                                for v in obj.values()):
            linea = '{ ' + ', '.join(f'{json.dumps(k, ensure_ascii=False)}: {a_json(v)}' for k, v in obj.items()) + ' }'
            if len(linea) <= 240:
                return linea
        partes = [f'{esp}  {json.dumps(k, ensure_ascii=False)}: {a_json(v, sangria + 1)}' for k, v in obj.items()]
        return '{\n' + ',\n'.join(partes) + '\n' + esp + '}'
    if isinstance(obj, list):
        if all(not isinstance(v, (dict, list)) for v in obj):
            return '[' + ', '.join(json.dumps(v, ensure_ascii=False) for v in obj) + ']'
        partes = [f'{esp}  {a_json(v, sangria + 1)}' for v in obj]
        return '[\n' + ',\n'.join(partes) + '\n' + esp + ']'
    return json.dumps(obj, ensure_ascii=False)


def construir(informe=False):
    est = json.loads((FIXTURES / 'estructura_min.json').read_text(encoding='utf-8'))
    amenaza = json.loads((RAIZ / 'data' / 'sismo' / 'amenaza.json').read_text(encoding='utf-8'))
    esc = next(e for e in amenaza['escenarios'] if e['id'] == 'nido_2015')
    params = {'Mw': esc['Mw'], 'profundidad_km': esc['profundidad_km'], 'distancia_epicentral_km': esc['distancia_epicentral_km'],
              'vs30_m_s': amenaza['controles']['vs30_m_s']['defecto'], 'semilla': amenaza['controles']['semilla']['defecto']}

    mod = armar_modelo(est)
    u_g, est_el, est_mu, tr_el, tr_mu = gravedad(mod)
    KL = rigidez_condensada(mod, u_g, est_el, est_mu, True)
    KL_el = rigidez_condensada(mod, u_g, est_el, est_mu, False)
    KL_amort = rigidez_condensada(mod, u_g, est_el, est_mu, False, con_muros=False)
    md = modos(mod, KL)
    am = amortiguamiento(md, KL_amort, mod['mdiag'][:mod['nd']], est['amortiguamiento']['xi'])
    res = analizar(mod, u_g, est_el, est_mu, am)
    res['est'] = est
    nE, N, nN, nP = len(mod['elementos']), mod['N'], len(mod['nodos']), len(mod['porticos'])
    sal, env = res['sal'], res['env']
    nt = len(sal['t'])

    # thp de los elementos que fluyen alguna vez
    H = np.array(res['historia_thp'])           # nt × nE × 2
    fluyen = [ie for ie in range(nE) if np.any(H[:, ie, :] != 0.0)]
    valores = []
    for it in range(nt):
        for ie in fluyen:
            for k in range(2):
                valores.append(int(max(-32768, min(32767, round(H[it, ie, k] * 1e5)))))

    resultado = {
        'version': 1, 'id': 'prueba', 'duracion_calculo_ms': 1,
        'params': params,
        'opciones': {'dt_s': DT, 'dt_salida_s': DT_SALIDA, 'duracion_s': DURACION, 'calidad': 'normal', 'angulo_deg': ANGULO_DEG, 'escala': ESCALA},
        'origen_registro': {
            'tipo': 'pulso_prueba',
            'descripcion': 'Pulso rectangular de prueba (componente 1: +1 m/s², componente 2: −0,5 m/s², desde t = 0,005 s) multiplicado por la escala; no es la síntesis de los parámetros del sismo (fixture del cálculo de referencia).',
        },
        'factor_escala': None, 'iteraciones_escala': 0,
        'amortiguamiento': {'a0': corto(am['a0']), 'a1': corto(am['a1']), 'periodos_ancla_s': [corto(x) for x in am['periodos_ancla_s']],
                            'xi_modos': [f32(x) for x in am['xi_modos']]},
        't': [f32(x) for x in sal['t']],
        'ag': [f32(x) for x in sal['ag']],
        'u': [f32(x) for x in sal['u']],
        'a_abs': [f32(x) for x in sal['a_abs']],
        'giros': [f32(x) for x in sal['giros']],
        'v_nodos': [f32(x) for x in sal['v_nodos']],
        'dc': sal['dc'], 'dc_flexion': sal['dc_flexion'], 'dc_cortante': sal['dc_cortante'], 'dc_rotacion': sal['dc_rotacion'],
        'rotulas': [int(b) for b in sal['rotulas']],
        'thp': {'elementos': fluyen, 'valores': valores},
        'derivas': [f32(x) for x in sal['derivas']],
        'derivas_vector': [f32(x) for x in sal['derivas_vector']],
        'derivas_porticos_env': [f32(x) for x in res['env_porticos'].ravel()],
        'cortante_basal': [f32(x) for x in sal['cortante_basal']],
        'energia': [f32(x) for x in sal['energia']],
        'envolventes': {
            'u_max': [f32(x) for x in env['u_max']], 'deriva_max': [f32(x) for x in env['deriva_max']],
            't_deriva_max': [f32(x) for x in env['t_deriva_max']], 'deriva_vector_max': [f32(x) for x in env['deriva_vector_max']],
            'punto_deriva_vector': [f32(x) for x in env['punto_deriva_vector']], 't_deriva_vector_max': [f32(x) for x in env['t_deriva_vector_max']],
            'a_abs_max': [f32(x) for x in env['a_abs_max']], 'dc_max': [f32(x) for x in env['dc_max']], 't_dc_max': [f32(x) for x in env['t_dc_max']],
            'gobierna': [int(x) for x in env['gobierna']], 'Mi_max': [f32(x) for x in env['Mi_max']], 'Mj_max': [f32(x) for x in env['Mj_max']],
            'V_max': [f32(x) for x in env['V_max']], 'N_min': [f32(x) for x in env['N_min']], 'N_max': [f32(x) for x in env['N_max']],
            'thp_max': [f32(x) for x in env['thp_max']], 't_primera_fluencia': [f32(x) for x in env['t_primera_fluencia']],
        },
        'muros_mamposteria': [{'id': mu['id'], 'aislado': mu['aislado'], 'deriva_max': f32(mu['deriva_max']), 'estado': mu['estado']} for mu in res['muros']],
        'equipos': [{k: (f32(v) if isinstance(v, float) else v) for k, v in eq.items()} for eq in res['equipos']],
        'calidad_numerica': {
            'pasos': res['calidad']['pasos'], 'iteraciones_promedio': corto(res['calidad']['iter'] / max(res['calidad']['pasos'], 1), 4),
            'subdivisiones': res['calidad']['subdivisiones'], 'no_convergidos': res['calidad']['no_convergidos'],
            'error_energia_max': float(f"{res['calidad']['err_e']:.3g}"), 'error_deformacion_max': float(f"{res['calidad']['err_d']:.3g}"),
            'indice_estabilidad_max': corto(res['indice'], 4),
        },
    }

    claves_serie = ('Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc')
    ie = next(i for i, el in enumerate(mod['elementos']) if el['id'] == 'C-A1-1@X')   # el elemento del Anexo A.4
    serie = {'tipo': 'serie_elemento', 'id': 'prueba', 'elemento': mod['elementos'][ie]['id'], 't': resultado['t']}
    for k in claves_serie:
        serie[k] = [f32(x) for x in res['series'][ie][k]]
    series = {el['id']: {k: [f32(x) for x in res['series'][i][k]] for k in claves_serie} for i, el in enumerate(mod['elementos'])}

    # bloque del trabajador simulado: 'listo' y 'movimiento'
    xyz_nodo = {}
    for n in mod['nodos']:
        p = next(pp for pp in mod['porticos'] if pp['id'] == n['portico'])
        z = mod['z'][n['nivel']]
        xyz_nodo[n['id']] = [n['s'], p['coordenada'], z] if p['direccion'] == 'x' else [p['coordenada'], n['s'], z]
    cr, exc = centro_rigidez(mod, KL_el)
    masa = sum(nv['masa_t'] for nv in mod['niveles'])
    peso = sum(nv['peso_sismico_kN'] for nv in mod['niveles'])
    cm = [sum(nv['masa_t'] * nv['cm'][c] for nv in mod['niveles']) / masa for c in range(2)]
    nmod = min(12, mod['nd'])
    listo = {
        'tipo': 'listo', 'id': 'prueba',
        'resumen': {'niveles': N, 'porticos': nP, 'nodos': nN, 'elementos': nE, 'gdl_dinamicos': mod['nd'], 'gdl_condensados': mod['ncond'],
                    'masa_total_t': corto(masa), 'peso_kN': corto(peso), 'cm': [corto(c) for c in cm],
                    'centro_rigidez': [[corto(v, 6) for v in c] for c in cr], 'excentricidad': [[corto(v, 6) for v in c] for c in exc],
                    'sistema': est['sistema_estructural']},
        'elementos': [{'id': el['id'], 'tipo': el['tipo'], 'portico': el['portico'], 'nivel': el['nivel'], 'fisico': el['fisico'],
                       'i': el['i'], 'j': el['j'], 'xyz_i': xyz_nodo[el['i']], 'xyz_j': xyz_nodo[el['j']], 'seccion': el['seccion']} for el in mod['elementos']],
        'nodos': [{'id': n['id'], 'portico': n['portico'], 'xyz': xyz_nodo[n['id']]} for n in mod['nodos']],
        'modos': {'periodos_s': [corto(x, 6) for x in md['T'][:nmod]],
                  'masa_participativa': {c: [corto(x, 5) for x in md['part'][c][:nmod]] for c in ('x', 'y', 'rz')},
                  'formas': [[corto(x, 6) for x in md['phi'][:, r]] for r in range(nmod)],
                  'T1x': corto(md['T1x'], 6), 'T1y': corto(md['T1y'], 6)},
        'amortiguamiento': resultado['amortiguamiento'],
    }
    movimiento = movimiento_fixture(amenaza, params, res)
    for k in ('ax', 'ay'):
        movimiento['registro'][k] = [f32(x) for x in movimiento['registro'][k]]
    movimiento['registro']['meta'] = {k: (corto(v) if isinstance(v, float) else v) for k, v in movimiento['registro']['meta'].items()}
    for c in ('x', 'y'):
        movimiento['registro']['intensidades'][c] = {k: corto(v, 6) for k, v in movimiento['registro']['intensidades'][c].items()}
    for grupo in ('espectro', 'fourier', 'nsr10'):
        movimiento[grupo] = {k: [f32(x) for x in v] for k, v in movimiento[grupo].items()}
    for g in movimiento['gmpe']:
        g['mediana_g'] = [corto(x, 5) for x in g['mediana_g']]
        g['sigma_ln'] = [corto(x, 4) for x in g['sigma_ln']]

    if informe:
        print('Períodos (s):', [round(x, 4) for x in md['T']])
        print('Masa participativa x:', [round(x, 3) for x in md['part']['x']], 'y:', [round(x, 3) for x in md['part']['y']])
        print('Amortiguamiento:', am)
        print('Centro de rigidez:', cr, 'excentricidad:', exc)
        print('Elementos que fluyen:', [mod['elementos'][i]['id'] for i in fluyen])
        print('Calidad:', res['calidad'], 'índice de estabilidad:', res['indice'])
        print('Muros:', res['muros'])
        print('Equipos:', res['equipos'])
        print('u final:', [round(x, 5) for x in sal['u'][-6:]])
        print('Energía final:', [round(x, 4) for x in sal['energia'][-6:]])
        print('Serie', serie['elemento'], {k: serie[k] for k in ('Mi', 'Mj', 'thp_i', 'dc')})
    return resultado, serie, {'listo': listo, 'movimiento': movimiento, 'series': series}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--verificar', action='store_true', help='recalcula y compara con el archivo versionado')
    ap.add_argument('--informe', action='store_true', help='imprime el detalle de la corrida')
    args = ap.parse_args()
    resultado, serie, gen = construir(args.informe)
    # la referencia: los Resultados del caso (con la serie de C-A1-1@X), para la prueba R0 del motor
    resultado['serie_elemento'] = {k: serie[k] for k in ('elemento', 'Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc')}
    ruta = FIXTURES / 'referencia_min.json'
    texto = a_json(resultado) + '\n'
    actual = ruta.read_text(encoding='utf-8') if ruta.exists() else None
    cal = resultado['calidad_numerica']
    print(f"pasos {cal['pasos']} · iteraciones promedio {cal['iteraciones_promedio']} · error de energía {cal['error_energia_max']} · "
          f"error de deformación {cal['error_deformacion_max']} · elementos que fluyen {len(resultado['thp']['elementos'])}")
    if args.verificar:
        if actual != texto:
            print(f'DIFERENTE: {ruta.relative_to(RAIZ).as_posix()} (correr sin --verificar y revisar el cambio)')
            sys.exit(1)
        print('referencia al día: idéntica byte a byte')
    elif actual != texto:
        ruta.write_text(texto, encoding='utf-8')
        print('escrito', ruta.relative_to(RAIZ).as_posix())


if __name__ == '__main__':
    main()
