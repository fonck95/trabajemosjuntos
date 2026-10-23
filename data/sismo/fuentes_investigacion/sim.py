"""Boore (2003) time-domain stochastic point-source simulation, numpy only.
Reference implementation for checking parameter choices (not the repo engine)."""
import numpy as np, math
G = 9.80665
# Boore (2016) generic Vs30=760 amplification (from StochasticGroundMotionSimulation.jl, PJSsiteAmpStructs.jl)
B16_F = np.array([0.001,0.010,0.015,0.021,0.031,0.045,0.065,0.095,0.138,0.200,0.291,0.423,0.615,0.894,1.301,1.892,2.751,4.000,5.817,8.459,12.301,17.889,26.014,37.830,55.012,80.000,1e3])
B16_A = np.array([1.00,1.00,1.01,1.02,1.02,1.04,1.06,1.09,1.13,1.18,1.25,1.32,1.41,1.51,1.64,1.80,1.99,2.18,2.38,2.56,2.75,2.95,3.17,3.42,3.68,3.96,3.96])
# BSSA14 site coefficients: T, c, Vc, f4, f5 (OpenQuake boore_2014.py)
BS_SITE = np.array([
[0.010,-0.603720,1500.20,-0.148330,-0.007010],[0.020,-0.573880,1500.36,-0.147100,-0.007280],
[0.030,-0.534140,1502.95,-0.154850,-0.007350],[0.050,-0.457950,1501.42,-0.192000,-0.006470],
[0.075,-0.444110,1494.00,-0.235000,-0.005730],[0.100,-0.487240,1479.12,-0.249160,-0.005600],
[0.150,-0.579620,1442.85,-0.257130,-0.005850],[0.200,-0.687620,1392.61,-0.246580,-0.006140],
[0.300,-0.841650,1308.47,-0.219120,-0.006700],[0.400,-0.910920,1252.66,-0.195820,-0.007130],
[0.500,-0.969300,1203.91,-0.175000,-0.007440],[0.750,-1.015400,1147.59,-0.138660,-0.008120],
[1.000,-1.050000,1109.95,-0.105210,-0.008440],[1.500,-1.045400,1072.39,-0.062000,-0.007710],
[2.000,-1.039200,1009.49,-0.036136,-0.004790],[3.000,-1.011200,922.43,-0.013577,-0.001830],
[4.000,-0.969380,844.48,-0.003212,-0.001520],[5.000,-0.919540,793.13,-0.000255,-0.001440],
[7.500,-0.776650,771.01,-0.000055,-0.001370],[10.00,-0.655750,775.00,0.000000,-0.001360]])

def amp760(f):
    return np.interp(np.log(np.maximum(f,1e-3)), np.log(B16_F), B16_A)

def soil_factor(f, vs30, pgar_g):
    T = 1.0/np.maximum(f,1e-6)
    lnT = np.log(np.clip(T, 0.01, 10.0))
    lt = np.log(BS_SITE[:,0])
    c = np.interp(lnT, lt, BS_SITE[:,1]); Vc = np.interp(lnT, lt, BS_SITE[:,2])
    f4 = np.interp(lnT, lt, BS_SITE[:,3]); f5 = np.interp(lnT, lt, BS_SITE[:,4])
    flin = c*np.log(np.minimum(vs30,Vc)/760.0)
    f2 = f4*(np.exp(f5*(min(vs30,760.0)-360.0)) - np.exp(f5*400.0))
    fnl = f2*np.log((pgar_g+0.1)/0.1)
    return np.exp(flin+fnl)

def geo_spread(R, segs):
    """segs: list of (exponent, R_end or None). Continuous piecewise power law, R0=1 km."""
    g = 1.0; r0 = 1.0
    for p, rend in segs:
        r1 = R if rend is None else min(R, rend)
        if r1 > r0:
            g *= (r0/r1)**p
            r0 = r1
        if rend is None or R <= rend: break
    return g

def bt14_dp(R):
    D=[0,7,45,125,175,270]; P=[0.0,2.4,8.4,10.9,17.4,34.2]
    return float(np.interp(R,D,P)) if R<=270 else 34.2+0.156*(R-270)

def fourier_acc(f, M, R, p, site_amp):
    """Fourier acceleration amplitude (cm/s) at hypocentral/effective distance R (km)."""
    M0 = 10**(1.5*M+16.05)
    f0 = 4.906e6*p['beta_s']*(p['dsigma']/M0)**(1/3)
    C = p['rad']*p['fs']*p['part']/(4*math.pi*p['rho_s']*p['beta_s']**3*1.0)*1e-20
    src = C*M0/(1+(f/f0)**2)
    Q = np.maximum(p['Q0']*np.maximum(f,1e-6)**p['eta'], p.get('Qmin',0.0))
    path = geo_spread(R, p['segs'])*np.exp(-math.pi*f*R/(Q*p['beta_Q']))
    site = site_amp*np.exp(-math.pi*p['kappa0']*f)
    return (2*math.pi*f)**2*src*path*site, f0

def window(t, teta, eps=0.2, eta=0.05):
    b = -eps*math.log(eta)/(1+eps*(math.log(eps)-1)); c = b/eps; a = (math.e/eps)**b
    x = np.maximum(t/teta, 0)
    w = a*x**b*np.exp(-c*x)
    w[t>teta] = 0.0
    return w

def simulate(M, Repi, h, p, vs30=270.0, nsim=30, dt=0.005, periods=(0.2,0.5,1.0), seed0=1, return_ts=False):
    R = math.sqrt(Repi**2+h**2)
    if p.get('h_ff'):
        R = math.sqrt(R**2 + p['h_ff'](M)**2)
    M0 = 10**(1.5*M+16.05); f0 = 4.906e6*p['beta_s']*(p['dsigma']/M0)**(1/3)
    Tgm = 1.0/f0 + (bt14_dp(R) if p['dur']=='BT14' else p['dur_b']*R)
    teta = 2.0*Tgm
    nw = int(round(teta/dt))
    npad = int(2**math.ceil(math.log2(nw + int(40.0/dt))))
    f = np.fft.rfftfreq(npad, dt); f[0] = 1e-6
    imp = math.sqrt(p['rho_s']*p['beta_s']/(2.8*3.5)) if p.get('impedance_deep') else 1.0
    A_rock, _ = fourier_acc(f, M, R, p, amp760(f)*imp)
    rng = np.random.default_rng(seed0)
    res = {'pgar':[], 'pga':[], 'pgv':[], 'arias':[], 'd595':[]}
    for T in periods: res[T]=[]
    t = np.arange(nw)*dt
    w = window(t, teta)
    for k in range(nsim):
        n = rng.standard_normal(nw)*w
        x = np.zeros(npad); x[:nw] = n
        Z = np.fft.rfft(x)
        Zn = Z/np.sqrt(np.mean(np.abs(Z)**2))
        # rock pass
        Xr = Zn*A_rock/dt
        ar = np.fft.irfft(Xr, npad)          # cm/s2
        pgar = np.max(np.abs(ar))/100/G
        A_soil = A_rock*soil_factor(f, vs30, pgar)
        X = Zn*A_soil/dt
        a = np.fft.irfft(X, npad)
        res['pgar'].append(pgar); res['pga'].append(np.max(np.abs(a))/100/G)
        # velocity via frequency domain
        V = X/(2j*math.pi*f); V[0]=0
        v = np.fft.irfft(V, npad); res['pgv'].append(np.max(np.abs(v)))
        Ia = math.pi/(2*G)*np.sum((a/100)**2)*dt; res['arias'].append(Ia)
        cum = np.cumsum((a/100)**2); cum/=cum[-1]
        res['d595'].append((np.searchsorted(cum,0.95)-np.searchsorted(cum,0.05))*dt)
        for T in periods:
            wn = 2*math.pi/T; z=0.05; om=2*math.pi*f
            H = -1.0/(wn**2-om**2+2j*z*wn*om)
            u = np.fft.irfft(X*H, npad)
            res[T].append(wn**2*np.max(np.abs(u))/100/G)
    out = {k: float(np.exp(np.mean(np.log(v)))) for k,v in res.items()}
    out.update(R=R, f0=f0, Tgm=Tgm)
    return out
