import sys, math, numpy as np
sys.path.insert(0,'.')
import pyrvt
from sim import *
# Campbell 2003 WNA params, BJ97 rock amp table (as in pyrvt), duration 1/f0+0.05R
BJ_F=np.array([0.01,0.09,0.16,0.51,0.84,1.25,2.26,3.17,6.05,16.60,61.20,100.00]); BJ_A=np.array([1.00,1.10,1.18,1.42,1.58,1.74,2.06,2.25,2.58,3.13,4.00,4.40])
p = dict(beta_s=3.5, rho_s=2.8, dsigma=100.0, rad=0.55, fs=2.0, part=1/math.sqrt(2), Q0=180., eta=0.45, beta_Q=3.5,
         kappa0=0.04, segs=[(1.0,40.),(0.5,None)], dur='lin', dur_b=0.05)
import sim
for M, Repi, h in [(6.5, 20., 8.), (5.5, 50., 8.)]:
    m = pyrvt.motions.SourceTheoryMotion(M, Repi, 'wna', depth=h)
    T = np.array([0.2,0.5,1.0])
    sa = m.calc_osc_accels(1/T, 0.05)
    # time domain with BJ97 amp and no soil factor
    sim.amp760 = lambda f: np.interp(np.log(np.maximum(f,0.01)), np.log(BJ_F), BJ_A)
    sim.soil_factor = lambda f, vs, pg: 1.0
    out = simulate(M, Repi, h, p, vs30=760, nsim=40)
    print('M',M,'R',Repi,'RVT pga',round(float(m.calc_peak()),4),'Sa',np.round(sa,4),'| TD pga',round(out['pga'],4),'Sa',[round(out[t],4) for t in (0.2,0.5,1.0)], 'Tgm',round(out['Tgm'],2), 'D595', round(out['d595'],2))
