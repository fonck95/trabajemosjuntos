#!/usr/bin/env python3
"""Implementación de referencia del movimiento del suelo del simulador sísmico (contrato de integración, 7.3 y 7.4).

Es el puerto en un solo archivo de data/sismo/fuentes_investigacion/sim.py y gmpe.py (la investigación), con las
reglas del contrato que el motor JavaScript (web/js/sismo/movimiento.js) también cumple:
  - método estocástico de fuente puntual de Boore (2003) con los 12 pasos de amenaza.json → notas_para_implementar;
  - banda de transición de profundidad de 40 a 70 km (cambio E15): ln A = (1 − w)·ln A_cortical + w·ln A_intraplaca,
    w = clamp((h − 40)/30, 0, 1), y Tgm lineal en w;
  - Δt = 0,005 s; ruido mulberry32 + Box-Muller; FFT radix-2 propia; dos componentes con semillas s y s + 1;
  - ventana desde t_pre = max(5·τ, 1 s), τ = 1/(2π·f0), y registro hasta t_pre después de la ventana (el porqué está
    en movimiento.js y en data/sismo/ESQUEMA.md, «Movimiento del suelo»);
  - no linealidad del suelo (BSSA14) con la media geométrica de los PGA en roca de las dos componentes;
  - GMPE (BC Hydro 2016 intraplaca, Zhao 2006 intraplaca y cortical, BSSA14) leyendo los coeficientes de
    amenaza.json (el JavaScript los lleva copiados: así las dos lecturas se controlan entre sí);
  - espectro de respuesta exacto para excitación lineal por tramos (Nigam y Jennings, 1969), espectro NSR-10.

Solo usa la biblioteca estándar (Python ≥ 3.11 por math.cbrt), para que corra en cualquier lado y para que la
prueba T15b del motor (node scripts/sismo/test_motor.mjs) la llame con el python3 del sistema. numpy solo se usa en
`--validar` (ver scripts/sismo/requisitos_validacion.txt), que compara esta FFT con numpy.fft y esta síntesis con la
de la investigación (sim.py, gmpe.py).

Uso:
    python3 scripts/sismo/estocastico.py escenario nido_2015 [--semilla 2028] [--vs30 270]
    python3 scripts/sismo/estocastico.py --consultas < consultas.json     # lo usa la prueba T15b (JSON → JSON)
    python3 scripts/sismo/estocastico.py --validar                         # con numpy
"""
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AMENAZA = RAIZ / 'data' / 'sismo' / 'amenaza.json'
G = 9.80665

# Constantes que en amenaza.json están solo dentro de fórmulas escritas (mismas que movimiento.js)
BRUNE_F0 = 4.906e6
MW_A_M0 = (1.5, 16.05)
ES_SOBRE_M0 = 1 / 20000
H_FF = (-0.405, 0.235)
BT14_MAS_ALLA = (270.0, 34.2, 0.156)
TCAMINO_INTRAPLACA_B = 0.05
# Δσ intraplaca según la profundidad (regla del motor, revisión A6; la deducción está en movimiento.js y ESQUEMA.md):
# Δσ(h) = Δσ_ref·exp((3/2)·θ·(min(h, hc) − hc)), θ = 0,0135/km (media de θ11 de BC Hydro y e de Zhao), hc = 120 km.
DSIGMA_INTRAPLACA_PROF = (0.0135, 120.0)
IMPEDANCIA_REF = (2.8, 3.5)
RELLENO_S = 40.0
F_CERO = 1e-6
PGA_BSSA_F3 = 0.1
VREF_BSSA = 760.0
CONSTANTES_TIEMPO_COLA = 5.0
COLA_MINIMA_S = 1.0


def clamp(x, a, b):
    return min(b, max(a, x))


def interp(x, xs, ys):
    """Lineal con xs creciente, recortada a los extremos (como numpy.interp y como movimiento.js)."""
    n = len(xs)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[n - 1]:
        return ys[n - 1]
    lo, hi = 0, n - 1
    while hi - lo > 1:
        m = (lo + hi) >> 1
        if xs[m] <= x:
            lo = m
        else:
            hi = m
    return ys[lo] + ((x - xs[lo]) / (xs[hi] - xs[lo])) * (ys[hi] - ys[lo])


# ---------------------------------------------------------------------------------------------------------------
# Azar: mulberry32 + Box-Muller (bit a bit igual a web/js/sismo/azar.js)
# ---------------------------------------------------------------------------------------------------------------
M32 = 0xFFFFFFFF


def _imul(a, b):
    return (a * b) & M32


def mulberry32(semilla):
    estado = [semilla & M32]

    def uniforme():
        a = (estado[0] + 0x6D2B79F5) & M32
        estado[0] = a
        t = _imul(a ^ (a >> 15), a | 1)
        t = ((t + _imul(t ^ (t >> 7), t | 61)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296.0
    return uniforme


def normales(semilla, n):
    u = mulberry32(semilla)
    out = [0.0] * n
    for i in range(0, n, 2):
        u1 = 1.0 - u()
        u2 = u()
        r = math.sqrt(-2.0 * math.log(u1))
        fase = 2.0 * math.pi * u2
        out[i] = r * math.cos(fase)
        if i + 1 < n:
            out[i + 1] = r * math.sin(fase)
    return out


# ---------------------------------------------------------------------------------------------------------------
# FFT radix-2 (mismo algoritmo que web/js/sismo/fft.js)
# ---------------------------------------------------------------------------------------------------------------
_TABLAS = {}


def siguiente_potencia2(m):
    n = 1
    while n < m:
        n *= 2
    return n


def _tablas(N):
    t = _TABLAS.get(N)
    if t is None:
        h = N >> 1
        t = ([math.cos(2 * math.pi * k / N) for k in range(h + 1)], [math.sin(2 * math.pi * k / N) for k in range(h + 1)])
        _TABLAS[N] = t
    return t


def _fft_compleja(re, im, M, signo, tab, paso):
    j = 0
    for i in range(1, M):
        bit = M >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
    c, s = tab
    tam = 2
    while tam <= M:
        mitad = tam >> 1
        zancada = (M // tam) * paso
        for ini in range(0, M, tam):
            for jj in range(mitad):
                k = jj * zancada
                wr = c[k]
                wi = signo * s[k]
                a = ini + jj
                b = a + mitad
                rb, ib = re[b], im[b]
                tr = wr * rb - wi * ib
                ti = wr * ib + wi * rb
                ra, ia = re[a], im[a]
                re[b] = ra - tr
                im[b] = ia - ti
                re[a] = ra + tr
                im[a] = ia + ti
        tam <<= 1


def rfft(x, N):
    M = N >> 1
    L = len(x)
    zr = [x[2 * m] if 2 * m < L else 0.0 for m in range(M)]
    zi = [x[2 * m + 1] if 2 * m + 1 < L else 0.0 for m in range(M)]
    tab = _tablas(N)
    _fft_compleja(zr, zi, M, -1, tab, 2)
    c, s = tab
    re = [0.0] * (M + 1)
    im = [0.0] * (M + 1)
    for k in range(M + 1):
        a = 0 if k == M else k
        b = 0 if k == 0 else M - k
        zkr, zki, zmr, zmi = zr[a], zi[a], zr[b], -zi[b]
        er, ei = 0.5 * (zkr + zmr), 0.5 * (zki + zmi)
        dr, di = zkr - zmr, zki - zmi
        o_r, o_i = 0.5 * di, -0.5 * dr
        wr, wi = c[k], -s[k]
        re[k] = er + wr * o_r - wi * o_i
        im[k] = ei + wr * o_i + wi * o_r
    return re, im


def irfft(re, im, N):
    M = N >> 1
    tab = _tablas(N)
    c, s = tab
    zr = [0.0] * M
    zi = [0.0] * M
    for k in range(M):
        xkr = re[k]
        xki = 0.0 if k == 0 else im[k]
        xmr = re[M - k]
        xmi = 0.0 if (M - k) == M else -im[M - k]
        er, ei = 0.5 * (xkr + xmr), 0.5 * (xki + xmi)
        dr, di = 0.5 * (xkr - xmr), 0.5 * (xki - xmi)
        wr, wi = c[k], s[k]
        o_r, o_i = dr * wr - di * wi, dr * wi + di * wr
        zr[k] = er - o_i
        zi[k] = ei + o_r
    _fft_compleja(zr, zi, M, +1, tab, 2)
    x = [0.0] * N
    for m in range(M):
        x[2 * m] = zr[m] / M
        x[2 * m + 1] = zi[m] / M
    return x


# ---------------------------------------------------------------------------------------------------------------
# Parámetros de amenaza.json
# ---------------------------------------------------------------------------------------------------------------
def leer_parametros(amenaza):
    pe = amenaza['parametros_estocasticos']
    c = pe['comunes']
    sh = c['ventana_saragoni_hart']
    sitio = amenaza['amplificacion_sitio']
    filas = sitio['factor_suelo_BSSA14']['filas']
    comunes = dict(Rtp=c['patron_radiacion_Rtp']['valor'], F=c['superficie_libre_F']['valor'], V=math.sqrt(0.5),
                   R0=c['R0_km']['valor'], unidades=c['factor_unidades']['valor'], eps=sh['epsilon'], eta=sh['eta'],
                   fTgm=sh['f_Tgm'], dt=c['simulacion']['dt_s'])

    def regimen(r, clave):
        return dict(regimen=clave, dsigma=r['delta_sigma_bar']['valor'], rho=r['rho_s_g_cm3']['valor'],
                    beta=r['beta_s_km_s']['valor'], tramos=r['dispersion_geometrica']['tramos'], Q0=r['Q']['Q0'],
                    etaQ=r['Q']['eta'], betaQ=r['Q']['beta_Q_km_s'], kappa=r['kappa0_s']['valor'])
    cort = regimen(pe['cortical'], 'cortical')
    dc = pe['cortical']['duracion_camino']
    cort.update(durR=dc['tabla_R_km'], durT=dc['tabla_Tcamino_s'], fimp=1.0)
    intra = regimen(pe['intraplaca_profunda'], 'intraplaca_profunda')
    intra['fimp'] = math.sqrt((intra['rho'] * intra['beta']) / (IMPEDANCIA_REF[0] * IMPEDANCIA_REF[1]))
    return dict(comunes=comunes, cortical=cort, intraplaca_profunda=intra,
                a760=dict(lnf=[math.log(f) for f in sitio['A760']['f_Hz']], A=sitio['A760']['A']),
                suelo=dict(lnT=[math.log(f[0]) for f in filas], c=[f[1] for f in filas], Vc=[f[2] for f in filas],
                           f4=[f[3] for f in filas], f5=[f[4] for f in filas], Tmin=filas[0][0], Tmax=filas[-1][0]),
                controles=amenaza['controles'])


def normalizar(p, amenaza):
    ctl = amenaza['controles']
    q = dict(p)
    for k in ('Mw', 'profundidad_km', 'distancia_epicentral_km', 'vs30_m_s'):
        if q.get(k) is None:
            q[k] = ctl[k]['defecto']
        if not (ctl[k]['min'] - 1e-9 <= q[k] <= ctl[k]['max'] + 1e-9):
            raise ValueError(f'{k} = {q[k]} fuera del rango {ctl[k]["min"]}…{ctl[k]["max"]}')
    q.setdefault('semilla', ctl['semilla']['defecto'])
    q.setdefault('regimen', 'auto')
    q.setdefault('escala_pgar', 1.0)
    if q['regimen'] not in ('auto', 'cortical', 'intraplaca_profunda'):
        raise ValueError(f'regimen = {q["regimen"]}')
    return q


def regimen_por_profundidad(h):
    w = clamp((h - 40.0) / 30.0, 0.0, 1.0)
    return ('cortical' if w <= 0 else 'intraplaca_profunda' if w >= 1 else 'transicion'), w


def momento(Mw):
    M0 = 10 ** (MW_A_M0[0] * Mw + MW_A_M0[1])
    return M0, M0 * 1e-7, M0 * 1e-7 * ES_SOBRE_M0


def dispersion(R, tramos):
    g, r0 = 1.0, 1.0
    for t in tramos:
        p, re = t['exponente'], t['hasta_km']
        r1 = R if re is None else min(R, re)
        if r1 > r0:
            g *= (r0 / r1) ** p
            r0 = r1
        if re is None or R <= re:
            break
    return g


def tcamino_bt14(R, t):
    if R > BT14_MAS_ALLA[0]:
        return BT14_MAS_ALLA[1] + BT14_MAS_ALLA[2] * (R - BT14_MAS_ALLA[0])
    return interp(R, t['durR'], t['durT'])


def terminos(q, P):
    Mw, h, Repi = q['Mw'], q['profundidad_km'], q['distancia_epicentral_km']
    if q['regimen'] == 'cortical':
        w = 0.0
    elif q['regimen'] == 'intraplaca_profunda':
        w = 1.0
    else:
        w = regimen_por_profundidad(h)[1]
    M0 = momento(Mw)[0]
    Rhip = math.hypot(Repi, h)
    c = P['comunes']
    lista = []

    def agregar(t, peso):
        th, hc = DSIGMA_INTRAPLACA_PROF
        dsigma = t['dsigma'] if t['regimen'] == 'cortical' else t['dsigma'] * math.exp(1.5 * th * (min(h, hc) - hc))
        f0 = BRUNE_F0 * t['beta'] * math.cbrt(dsigma / M0)
        C = (c['Rtp'] * c['F'] * c['V']) / (4 * math.pi * t['rho'] * t['beta'] ** 3 * c['R0']) * c['unidades']
        if t['regimen'] == 'cortical':
            hff = 10 ** (H_FF[0] + H_FF[1] * Mw)
            Ref = math.hypot(Rhip, hff)
            Tc = tcamino_bt14(Ref, t)
        else:
            Ref = Rhip
            Tc = TCAMINO_INTRAPLACA_B * Ref
        lista.append(dict(regimen=t['regimen'], peso=peso, t=t, dsigma=dsigma, M0=M0, f0=f0, C=C, Rhip=Rhip, Ref=Ref,
                          Z=dispersion(Ref, t['tramos']), Tcamino=Tc, Tgm=1 / f0 + Tc))
    if w < 1:
        agregar(P['cortical'], 1 - w)
    if w > 0:
        agregar(P['intraplaca_profunda'], w)
    return w, lista


def ln_amplitud_termino(T, f, lnA760):
    t = T['t']
    Q = t['Q0'] * f ** t['etaQ']
    return (math.log(T['C'] * T['M0']) + 2 * math.log(2 * math.pi * f) - math.log(1 + (f / T['f0']) ** 2) + math.log(T['Z'])
            - (math.pi * f * T['Ref']) / (Q * t['betaQ']) + lnA760 + math.log(t['fimp']) - math.pi * t['kappa'] * f)


def amp760(P, f):
    return interp(math.log(f), P['a760']['lnf'], P['a760']['A'])


def factor_suelo_coef(P, f, vs30):
    s = P['suelo']
    x = math.log(clamp(1 / f, s['Tmin'], s['Tmax']))
    c = interp(x, s['lnT'], s['c'])
    Vc = interp(x, s['lnT'], s['Vc'])
    f4 = interp(x, s['lnT'], s['f4'])
    f5 = interp(x, s['lnT'], s['f5'])
    lin = c * math.log(min(vs30, Vc) / VREF_BSSA)
    f2 = f4 * (math.exp(f5 * (min(vs30, VREF_BSSA) - 360)) - math.exp(f5 * (VREF_BSSA - 360)))
    return lin, f2


def ln_no_lineal(pgar):
    return math.log((pgar + PGA_BSSA_F3) / PGA_BSSA_F3)


def ln_amplitud_mezcla(lista, P, f):
    lnA760 = math.log(amp760(P, f))
    return sum(x['peso'] * ln_amplitud_termino(x, f, lnA760) for x in lista)


def pga_rvt(Afun, Tgm, fNyq):
    """Igual que pgaRVT de movimiento.js (Boore 2003; Cartwright y Longuet-Higgins 1956)."""
    nf, f1 = 4000, 1e-3
    r = math.log(fNyq / f1) / (nf - 1)
    m0 = m2 = m4 = 0.0
    fa, ga = f1, Afun(f1) ** 2
    for i in range(1, nf):
        fb = f1 * math.exp(r * i)
        gb = Afun(fb) ** 2
        df = fb - fa
        wa, wb = (2 * math.pi * fa) ** 2, (2 * math.pi * fb) ** 2
        m0 += df * (ga + gb)
        m2 += df * (wa * ga + wb * gb)
        m4 += df * (wa * wa * ga + wb * wb * gb)
        fa, ga = fb, gb
    arms = math.sqrt(m0 / Tgm)
    Nz = math.sqrt(m2 / m0) * Tgm / math.pi
    Ne = max(math.sqrt(m4 / m2) * Tgm / math.pi, Nz)
    xi = Nz / Ne
    zmax = math.sqrt(math.log(max(Ne * xi, 1)) + 40)
    nz = 4000
    h = zmax / nz

    def fz(z):
        return -math.expm1(Ne * math.log1p(-xi * math.exp(-z * z)))
    s = fz(0) + fz(zmax)
    for i in range(1, nz):
        s += (4 if i % 2 else 2) * fz(i * h)
    fp = math.sqrt(2) * s * h / 3
    return fp * arms / G


def espectro_objetivo(p, amenaza, f_Hz, pgar_g=None):
    """→ (roca, suelo, pgar_g) en m/s (como espectroObjetivo de movimiento.js)."""
    q = normalizar(p, amenaza)
    P = leer_parametros(amenaza)
    w, lista = terminos(q, P)
    Tgm = sum(x['peso'] * x['Tgm'] for x in lista)
    if pgar_g is None:
        pgar_g = pga_rvt(lambda f: math.exp(ln_amplitud_mezcla(lista, P, f)) * 0.01, Tgm, 1 / (2 * P['comunes']['dt']))
    L = ln_no_lineal(pgar_g * q['escala_pgar'])   # como en sintetizar: PGA en roca sin escalar × escala_pgar
    roca, suelo = [], []
    for f in f_Hz:
        if not f > 0:
            roca.append(0.0)
            suelo.append(0.0)
            continue
        a = math.exp(ln_amplitud_mezcla(lista, P, f)) * 0.01
        lin, f2 = factor_suelo_coef(P, f, q['vs30_m_s'])
        roca.append(a)
        suelo.append(a * math.exp(lin + f2 * L))
    return roca, suelo, pgar_g


def plan_sintesis(q, amenaza):
    P = leer_parametros(amenaza)
    c = P['comunes']
    dt = c['dt']
    w, lista = terminos(q, P)
    Tgm = sum(x['peso'] * x['Tgm'] for x in lista)
    t_eta = c['fTgm'] * Tgm
    nw = math.floor(t_eta / dt + 0.5)
    f0min = min(x['f0'] for x in lista)
    t_pad = max(CONSTANTES_TIEMPO_COLA / (2 * math.pi * f0min), COLA_MINIMA_S)
    n_pre = math.ceil(t_pad / dt)
    N = siguiente_potencia2(n_pre + nw + round(RELLENO_S / dt))
    n_reg = min(N, n_pre + nw + n_pre)
    b = (-c['eps'] * math.log(c['eta'])) / (1 + c['eps'] * (math.log(c['eps']) - 1))
    cc = b / c['eps']
    aa = (math.e / c['eps']) ** b
    ventana = []
    for i in range(nw):
        x = (i * dt) / t_eta
        ventana.append(0.0 if x > 1 else aa * x ** b * math.exp(-cc * x))
    M = N >> 1
    Aroca, lin, f2 = [], [], []
    for k in range(M + 1):
        f = F_CERO if k == 0 else k / (N * dt)
        Aroca.append(math.exp(ln_amplitud_mezcla(lista, P, f)) * 0.01)
        a, b2 = factor_suelo_coef(P, f, q['vs30_m_s'])
        lin.append(a)
        f2.append(b2)
    return dict(P=P, w=w, lista=lista, Tgm=Tgm, t_eta=t_eta, nw=nw, n_pre=n_pre, N=N, n_reg=n_reg, dt=dt,
                ventana=ventana, Aroca=Aroca, lin=lin, f2=f2)


def _ruido_normalizado(plan, semilla):
    nw, n_pre, N = plan['nw'], plan['n_pre'], plan['N']
    ruido = normales(semilla, nw)
    x = [0.0] * N
    for i in range(nw):
        x[n_pre + i] = ruido[i] * plan['ventana'][i]
    re, im = rfft(x, N)
    s = sum(re[k] * re[k] + im[k] * im[k] for k in range(len(re)))
    e = 1 / math.sqrt(s / len(re))
    return [v * e for v in re], [v * e for v in im]


def _pasada(plan, Zn, factor):
    N, A, dt = plan['N'], plan['Aroca'], plan['dt']
    re, im = Zn
    M = N >> 1
    R = [0.0] * (M + 1)
    I = [0.0] * (M + 1)
    for k in range(M + 1):
        a = (A[k] * factor[k] if factor is not None else A[k]) / dt
        R[k] = re[k] * a
        I[k] = im[k] * a
    return irfft(R, I, N)


def sintetizar(p, amenaza):
    """Dos componentes (semillas s y s + 1) en m/s², como sintetizar de movimiento.js."""
    q = normalizar(p, amenaza)
    plan = plan_sintesis(q, amenaza)
    semillas = [q['semilla'], q['semilla'] + 1]
    Zn = [_ruido_normalizado(plan, s) for s in semillas]
    roca = [_pasada(plan, z, None) for z in Zn]
    pga_roca = [max(abs(v) for v in a) / G for a in roca]
    pgar = math.sqrt(pga_roca[0] * pga_roca[1])
    L = ln_no_lineal(pgar * q['escala_pgar'])
    factor = [math.exp(plan['lin'][k] + plan['f2'][k] * L) for k in range(len(plan['lin']))]
    suelo = [_pasada(plan, z, factor) for z in Zn]
    n = plan['n_reg']
    ax, ay = suelo[0][:n], suelo[1][:n]
    f0 = math.exp(sum(x['peso'] * math.log(x['f0']) for x in plan['lista']))
    return dict(dt=plan['dt'], n=n, ax=ax, ay=ay,
                meta=dict(f0_Hz=f0, Tgm_s=plan['Tgm'], t_eta_s=plan['t_eta'], w_transicion=plan['w'], n_fft=plan['N'],
                          t_inicio_ventana_s=plan['n_pre'] * plan['dt'], pga_roca_g=pgar, pga_roca_x_g=pga_roca[0],
                          pga_roca_y_g=pga_roca[1]),
                intensidades=dict(x=intensidades(ax, plan['dt']), y=intensidades(ay, plan['dt'])))


def intensidades(a, dt):
    n = len(a)
    pga = v = d = pgv = pgd = 0.0
    cum = [0.0] * n
    for i in range(n):
        ai = a[i]
        pga = max(pga, abs(ai))
        if i > 0:
            vn = v + 0.5 * (a[i - 1] + ai) * dt
            d += 0.5 * (v + vn) * dt
            v = vn
            cum[i] = cum[i - 1] + 0.5 * (a[i - 1] * a[i - 1] + ai * ai) * dt
        pgv = max(pgv, abs(v))
        pgd = max(pgd, abs(d))
    tot = cum[-1] if n else 0.0

    def instante(frac):
        if not tot > 0:
            return 0.0
        meta = frac * tot
        i = 0
        while i < n - 1 and cum[i] < meta:
            i += 1
        if i == 0:
            return 0.0
        de = cum[i] - cum[i - 1]
        return (i - 1 + ((meta - cum[i - 1]) / de if de > 0 else 0.0)) * dt
    t5, t95 = instante(0.05), instante(0.95)
    return dict(pga_g=pga / G, pgv_cm_s=pgv * 100, pgd_cm=pgd * 100, arias_m_s=math.pi / (2 * G) * tot,
                d595_s=t95 - t5, t5_s=t5, t95_s=t95)


def espectro_respuesta(a, dt, periodos, xi=0.05):
    """Nigam y Jennings (1969), con un período amortiguado de vibración libre después del registro."""
    n = len(a)
    raiz = math.sqrt(1 - xi * xi)
    Sa, Sd = [], []
    for T in periodos:
        if T == 0:   # oscilador rígido: Sa(0) = PGA
            Sa.append(max(abs(v) for v in a) / G)
            Sd.append(0.0)
            continue
        w = 2 * math.pi / T
        wd = w * raiz
        E, S, C = math.exp(-xi * w * dt), math.sin(wd * dt), math.cos(wd * dt)
        r = xi / raiz
        a11, a12 = E * (r * S + C), E * S / wd
        a21, a22 = -w / raiz * E * S, E * (C - r * S)
        t1, t2 = (2 * xi * xi - 1) / (w * w * dt), 2 * xi / (w ** 3 * dt)
        b11 = E * ((t1 + xi / w) * S / wd + (t2 + 1 / (w * w)) * C) - t2
        b12 = -E * (t1 * S / wd + t2 * C) - 1 / (w * w) + t2
        b21 = E * ((t1 + xi / w) * (C - r * S) - (t2 + 1 / (w * w)) * (wd * S + xi * w * C)) + 1 / (w * w * dt)
        b22 = -E * (t1 * (C - r * S) - t2 * (wd * S + xi * w * C)) - 1 / (w * w * dt)
        extra = math.ceil(2 * math.pi / wd / dt)
        u = v = umax = 0.0
        for i in range(n - 1 + extra):
            ai = a[i] if i < n else 0.0
            aj = a[i + 1] if i + 1 < n else 0.0
            u, v = a11 * u + a12 * v + b11 * ai + b12 * aj, a21 * u + a22 * v + b21 * ai + b22 * aj
            umax = max(umax, abs(u))
        Sd.append(umax)
        Sa.append(w * w * umax / G)
    return Sa, Sd


def espectro_nsr10(T, Aa, Av, Fa, Fv, I=1.0):
    TC, TL = 0.48 * Av * Fv / (Aa * Fa), 2.4 * Fv
    if T <= TC:
        return 2.5 * Aa * Fa * I
    if T <= TL:
        return 1.2 * Av * Fv * I / T
    return 1.2 * Av * Fv * TL * I / T ** 2


# ---------------------------------------------------------------------------------------------------------------
# GMPE con los coeficientes de amenaza.json → gmpe
# ---------------------------------------------------------------------------------------------------------------
def _fila(amenaza, modelo, imt):
    b = amenaza['gmpe'][modelo]
    f = next(r for r in b['coeficientes'] if r[0] == imt)
    return dict(zip(b['columnas'], f))


def _bchydro(amenaza, imt, M, R, Zh, vs30):
    K = amenaza['gmpe']['bchydro2016_intraslab']['constantes']
    dC1 = K['DeltaC1_intraplaca']

    def nucleo(C):
        Mc = K['C1'] + dC1
        fmag = (K['theta4'] if M <= Mc else K['theta5']) * (M - Mc) + C['theta13'] * (10 - M) ** 2
        fdist = ((C['theta2'] + C['theta14'] + K['theta3'] * (M - 7.8)) * math.log(R + K['c4'] * math.exp((M - 6) * K['theta9']))
                 + C['theta6'] * R + C['theta10'])
        fdepth = C['theta11'] * (min(Zh, 120) - 60)
        return C['theta1'] + K['theta4'] * dC1 + fmag + fdist + fdepth
    Cp = _fila(amenaza, 'bchydro2016_intraslab', 'PGA')
    pga1000 = math.exp(nucleo(Cp) + (Cp['theta12'] + Cp['b'] * K['n']) * math.log(1000 / Cp['Vlin']))
    C = _fila(amenaza, 'bchydro2016_intraslab', imt)
    vs = min(vs30, 1000)
    if vs30 < C['Vlin']:
        fs = (C['theta12'] * math.log(vs / C['Vlin']) - C['b'] * math.log(pga1000 + K['c'])
              + C['b'] * math.log(pga1000 + K['c'] * (vs / C['Vlin']) ** K['n']))
    else:
        fs = (C['theta12'] + C['b'] * K['n']) * math.log(vs / C['Vlin'])
    return nucleo(C) + fs, C['sigma']


def _zhao(amenaza, imt, M, x, h, vs30, intraplaca):
    C = _fila(amenaza, 'zhao2006_intraslab', imt)
    xx = max(x, 0.1)
    r = xx + C['c'] * math.exp(C['d'] * M)
    hh = min(h, 125)
    prof = C['e'] * (hh - 15) if hh >= 15 else 0.0
    Ck = C['CH'] if vs30 > 1100 else C['C1'] if vs30 > 600 else C['C2'] if vs30 > 300 else C['C3'] if vs30 > 200 else C['C4']
    ln = C['a'] * M + C['b'] * xx - math.log(r) + prof + Ck
    if intraplaca:
        ln += C['SS'] + C['SSL'] * math.log(xx) + C['PS'] * (M - 6.5) + C['QS'] * (M - 6.5) ** 2 + C['WS']
        tau = C['tauS']
    else:
        K = _fila(amenaza, 'zhao2006_cortical', imt)
        ln += K['QC'] * (M - 6.3) ** 2 + K['WC']
        tau = K['tauC']
    return ln - math.log(G * 100), math.sqrt(C['sigma'] ** 2 + tau ** 2)


def _bssa14(amenaza, imt, M, Rjb, vs30):
    def roca(C):
        e = C['e0']   # mecanismo no especificado
        FE = e + C['e4'] * (M - C['Mh']) + C['e5'] * (M - C['Mh']) ** 2 if M <= C['Mh'] else e + C['e6'] * (M - C['Mh'])
        R = math.hypot(Rjb, C['h'])
        return FE + (C['c1'] + C['c2'] * (M - 4.5)) * math.log(R) + C['c3'] * (R - 1)
    pgar = math.exp(roca(_fila(amenaza, 'bssa14', 'PGA')))
    C = _fila(amenaza, 'bssa14', imt)
    Flin = C['c'] * math.log(min(vs30, C['Vc']) / VREF_BSSA)
    f2 = C['f4'] * (math.exp(C['f5'] * (min(vs30, VREF_BSSA) - 360)) - math.exp(C['f5'] * (VREF_BSSA - 360)))
    Fnl = f2 * ln_no_lineal(pgar)
    tau = C['tau1'] if M <= 4.5 else C['tau2'] if M >= 5.5 else C['tau1'] + (C['tau2'] - C['tau1']) * (M - 4.5)
    phi = C['phi1'] if M <= 4.5 else C['phi2'] if M >= 5.5 else C['phi1'] + (C['phi2'] - C['phi1']) * (M - 4.5)
    if Rjb > C['R2']:
        phi += C['DphiR']
    elif Rjb > C['R1']:
        phi += C['DphiR'] * math.log(Rjb / C['R1']) / math.log(C['R2'] / C['R1'])
    if vs30 <= 225:
        phi -= C['DphiV']
    elif vs30 <= 300:
        phi -= C['DphiV'] * math.log(300 / vs30) / math.log(300 / 225)
    return roca(C) + Flin + Fnl, math.hypot(tau, phi)


def gmpe(amenaza, modelo, esc, periodos):
    """Mismas reglas de períodos que gmpe() de movimiento.js (PGA si T ≤ 0,01; ln-ln entre 0,2 y 1,0; NaN fuera)."""
    h, Repi = esc.get('profundidad_km'), esc.get('distancia_epicentral_km')
    Rhip = esc['Rhip_km'] if 'Rhip_km' in esc else math.hypot(Repi, h) if None not in (Repi, h) else None
    Mw, vs30 = esc['Mw'], esc['vs30_m_s']

    def imt_en(imt):
        if modelo == 'bchydro2016_intraslab':
            return _bchydro(amenaza, imt, Mw, Rhip, h, vs30)
        if modelo == 'zhao2006_intraslab':
            return _zhao(amenaza, imt, Mw, esc.get('Rrup_km', Rhip), h, vs30, True)
        if modelo == 'zhao2006_cortical':
            return _zhao(amenaza, imt, Mw, esc.get('Rrup_km', Rhip), h, vs30, False)
        if modelo == 'bssa14':
            return _bssa14(amenaza, imt, Mw, esc.get('Rjb_km', Repi), vs30)
        raise ValueError(modelo)
    tabla = [('PGA', 0.01), ('0.2', 0.2), ('0.5', 0.5), ('1.0', 1.0)]
    med, sig = [], []
    for T in periodos:
        if T <= 0.01:
            ln, s = imt_en('PGA')
        elif 0.2 - 1e-12 <= T <= 1.0 + 1e-12:
            j = 1
            while j < len(tabla) - 2 and T > tabla[j + 1][1]:
                j += 1
            (ia, Ta), (ib, Tb) = tabla[j], tabla[j + 1]
            A, B = imt_en(ia), imt_en(ib)
            u = (math.log(T) - math.log(Ta)) / (math.log(Tb) - math.log(Ta))
            ln, s = A[0] + u * (B[0] - A[0]), A[1] + u * (B[1] - A[1])
        else:
            ln, s = float('nan'), float('nan')
        med.append(math.exp(ln))
        sig.append(s)
    return med, sig


# ---------------------------------------------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------------------------------------------
def leer_amenaza():
    return json.loads(AMENAZA.read_text(encoding='utf-8'))


def _json_seguro(x):
    """NaN → None (JSON estándar)."""
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, list):
        return [_json_seguro(v) for v in x]
    if isinstance(x, dict):
        return {k: _json_seguro(v) for k, v in x.items()}
    return x


def responder(c, amenaza):
    acc = c['accion']
    if acc == 'objetivo':
        roca, suelo, pgar = espectro_objetivo(c['p'], amenaza, c['f_Hz'], c.get('pgar_g'))
        return dict(roca=roca, suelo=suelo, pgar_g=pgar)
    if acc == 'sintetizar':
        return sintetizar(c['p'], amenaza)
    if acc == 'espectro_respuesta':
        Sa, Sd = espectro_respuesta(c['a'], c['dt'], c['periodos'], c.get('xi', 0.05))
        return dict(Sa_g=Sa, Sd_m=Sd)
    if acc == 'gmpe':
        med, sig = gmpe(amenaza, c['modelo'], c['esc'], c['periodos'])
        return dict(mediana_g=med, sigma_ln=sig)
    if acc == 'nsr10':
        d = c['diseno']
        return dict(Sa_g=[espectro_nsr10(T, d['Aa'], d['Av'], d['Fa'], d['Fv'], d.get('I', 1.0)) for T in c['T']])
    if acc == 'mulberry32':
        u = mulberry32(c['semilla'])
        return dict(u=[u() for _ in range(c['n'])])
    raise ValueError(f'acción desconocida: {acc}')


def escenario(nombre, semilla, vs30):
    amenaza = leer_amenaza()
    e = next(x for x in amenaza['escenarios'] if x['id'] == nombre)
    p = dict(Mw=e['Mw'], profundidad_km=e['profundidad_km'], distancia_epicentral_km=e['distancia_epicentral_km'],
             vs30_m_s=vs30, semilla=semilla)
    r = sintetizar(p, amenaza)
    m = r['meta']
    print(f"{nombre}: Mw {e['Mw']}, h {e['profundidad_km']} km, Repi {e['distancia_epicentral_km']} km, Vs30 {vs30} m/s, semilla {semilla}")
    print(f"  f0 = {m['f0_Hz']:.4f} Hz · Tgm = {m['Tgm_s']:.2f} s · w = {m['w_transicion']:.3f} · N = {m['n_fft']} · "
          f"registro de {r['n'] * r['dt']:.2f} s · PGA en roca {m['pga_roca_g']:.4f} g")
    T = [0.2, 0.5, 1.0]
    for comp in ('x', 'y'):
        i = r['intensidades'][comp]
        Sa, _ = espectro_respuesta(r['a' + comp], r['dt'], T)
        print(f"  {comp}: PGA {i['pga_g']:.4f} g · PGV {i['pgv_cm_s']:.2f} cm/s · PGD {i['pgd_cm']:.2f} cm · Arias "
              f"{i['arias_m_s']:.4f} m/s · D5-95 {i['d595_s']:.2f} s · Sa(0,2/0,5/1,0) = " + ' / '.join(f'{s:.4f}' for s in Sa) + ' g')


def validar():
    """Con numpy: FFT contra numpy.fft, espectro objetivo contra sim.py y conjunto de 24 contra amenaza.json."""
    import importlib.util
    import numpy as np
    sys.dont_write_bytecode = True
    fuentes = RAIZ / 'data' / 'sismo' / 'fuentes_investigacion'
    sys.path.insert(0, str(fuentes))
    spec = importlib.util.spec_from_file_location('sim_investigacion', fuentes / 'sim.py')
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    spec = importlib.util.spec_from_file_location('gmpe_investigacion', fuentes / 'gmpe.py')
    gm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gm)
    amenaza = leer_amenaza()
    fallas = 0

    def informe(nombre, error, tol):
        nonlocal fallas
        ok = error <= tol
        fallas += 0 if ok else 1
        print(f"{'✓' if ok else '✗'} {nombre}: error {error:.3g} (tolerancia {tol:.3g})")
    rng = np.random.default_rng(1)
    for N in (8, 1024, 16384):
        x = rng.standard_normal(N)
        re, im = rfft(list(x), N)
        X = np.fft.rfft(x)
        informe(f'rfft contra numpy (N = {N})', float(np.max(np.abs(np.array(re) + 1j * np.array(im) - X)) / np.max(np.abs(X))), 1e-13)
        y = irfft(list(X.real), list(X.imag), N)
        informe(f'irfft contra numpy (N = {N})', float(np.max(np.abs(np.array(y) - np.fft.irfft(X, N)))), 1e-13)
    # Espectro objetivo de un régimen puro contra sim.fourier_acc (la investigación), en cm/s
    CORT = dict(beta_s=3.5, rho_s=2.8, rad=0.55, fs=2.0, part=1 / math.sqrt(2), Q0=180., eta=0.45, beta_Q=3.5, kappa0=0.04,
                segs=[(1.0, 40.), (0.5, None)], dsigma=100.)
    SLAB = dict(beta_s=4.5, rho_s=3.35, rad=0.55, fs=2.0, part=1 / math.sqrt(2), beta_Q=3.5, Q0=251., eta=0.58,
                kappa0=0.035, segs=[(1.0, None)], dsigma=800.)
    f = np.array([0.1, 0.5, 1.0, 5.0, 20.0])
    for nombre, M, Re, h, par, imp in (('nido_2015', 6.2, 92., 150., SLAB, True), ('cimitarra', 6.5, 20., 10., CORT, False)):
        R = math.hypot(Re, h)
        if not imp:
            R = math.hypot(R, 10 ** (-0.405 + 0.235 * M))
        fimp = math.sqrt(3.35 * 4.5 / (2.8 * 3.5)) if imp else 1.0
        ref, _ = sim.fourier_acc(f, M, R, par, sim.amp760(f) * fimp)
        pgar = 0.05
        roca, suelo, _ = espectro_objetivo(dict(Mw=M, profundidad_km=h, distancia_epicentral_km=Re, vs30_m_s=270), amenaza, list(f), pgar)
        informe(f'espectro objetivo en roca contra sim.py ({nombre})', float(np.max(np.abs(np.array(roca) * 100 / ref - 1))), 1e-9)
        ref_s = ref * sim.soil_factor(f, 270., pgar)
        informe(f'espectro objetivo en suelo contra sim.py ({nombre})', float(np.max(np.abs(np.array(suelo) * 100 / ref_s - 1))), 1e-9)
    # GMPE contra gmpe.py (la investigación)
    for modelo, fun in (('bchydro2016_intraslab', lambda imt, e: gm.bchydro_slab(imt, e['Mw'], e['Rhip_km'], e['profundidad_km'], e['vs30_m_s'])[0]),
                        ('zhao2006_intraslab', lambda imt, e: gm.zhao06_slab(imt, e['Mw'], e['Rhip_km'], e['profundidad_km'], e['vs30_m_s'])[0]),
                        ('zhao2006_cortical', lambda imt, e: gm.zhao06_asc(imt, e['Mw'], e['Rhip_km'], e['profundidad_km'], e['vs30_m_s'])[0]),
                        ('bssa14', lambda imt, e: gm.bssa14(imt, e['Mw'], e['distancia_epicentral_km'], e['vs30_m_s'])[0])):
        peor = 0.0
        for Mw in (5.0, 6.2, 7.0):
            for Re, h in ((5., 10.), (50., 30.), (92., 150.), (250., 120.)):
                e = dict(Mw=Mw, profundidad_km=h, distancia_epicentral_km=Re, Rhip_km=math.hypot(Re, h), vs30_m_s=270.)
                med, _ = gmpe(amenaza, modelo, e, [0.0, 0.2, 0.5, 1.0])
                for imt, v in zip(('pga', 0.2, 0.5, 1.0), med):
                    peor = max(peor, abs(v / fun(imt, e) - 1))
        informe(f'GMPE {modelo} contra gmpe.py (48 casos)', peor, 1e-12)
    # Conjunto de 24 componentes contra los resultados de la investigación (±25 %, la semilla)
    for nombre in ('nido_2015', 'cimitarra'):
        e = next(x for x in amenaza['escenarios'] if x['id'] == nombre)
        ref = e['resultado_estocastico_vs30_270']
        pga, sa = [], []
        for k in range(12):
            r = sintetizar(dict(Mw=e['Mw'], profundidad_km=e['profundidad_km'], distancia_epicentral_km=e['distancia_epicentral_km'],
                                vs30_m_s=270, semilla=7 + 2 * k), amenaza)
            for comp in ('x', 'y'):
                pga.append(r['intensidades'][comp]['pga_g'])
                sa.append(espectro_respuesta(r['a' + comp], r['dt'], [0.2, 0.5, 1.0])[0])
        gm_pga = math.exp(sum(math.log(v) for v in pga) / len(pga))
        informe(f'{nombre}: PGA media geométrica {gm_pga:.4f} g contra {ref["PGA_g"]} g', abs(gm_pga / ref['PGA_g'] - 1), 0.25)
        for j, (T, clave) in enumerate(((0.2, 'Sa02_g'), (0.5, 'Sa05_g'), (1.0, 'Sa10_g'))):
            g_ = math.exp(sum(math.log(s[j]) for s in sa) / len(sa))
            informe(f'{nombre}: Sa({T}) {g_:.4f} g contra {ref[clave]} g', abs(g_ / ref[clave] - 1), 0.25)
    print('validación:', 'en verde' if not fallas else f'{fallas} fallas')
    return 1 if fallas else 0


def main(argv):
    if '--consultas' in argv:
        amenaza = leer_amenaza()
        consultas = json.load(sys.stdin)
        json.dump(_json_seguro([responder(c, amenaza) for c in consultas]), sys.stdout)
        return 0
    if '--validar' in argv:
        return validar()
    if len(argv) >= 2 and argv[0] == 'escenario':
        semilla = int(argv[argv.index('--semilla') + 1]) if '--semilla' in argv else 2028
        vs30 = float(argv[argv.index('--vs30') + 1]) if '--vs30' in argv else 270.0
        escenario(argv[1], semilla, vs30)
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
