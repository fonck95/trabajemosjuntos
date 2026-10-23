import sys, math, numpy as np
sys.path.insert(0,'.')
from sim import simulate
from gmpe import bssa14
ya15 = lambda M: 10**(-0.405+0.235*M)
base = dict(beta_s=3.5, rho_s=2.8, rad=0.55, fs=2.0, part=1/math.sqrt(2), Q0=180., eta=0.45, beta_Q=3.5,
            kappa0=0.04, segs=[(1.0,40.),(0.5,None)], dur='BT14', h_ff=ya15)
scen = [(5.5,10.,10.),(5.5,50.,10.),(6.5,10.,10.),(6.5,30.,10.),(6.5,90.,10.),(7.0,30.,10.),(7.0,90.,10.)]
for ds in [50., 75., 100., 150.]:
    p = dict(base, dsigma=ds)
    resid=[]
    for M,Rjb,h in scen:
        o = simulate(M, Rjb, h, p, vs30=270., nsim=16)
        for imt in ['pga',0.2,0.5,1.0]:
            g = bssa14(imt, M, Rjb, 270., 'U')[0]
            resid.append(math.log(o[imt]/g))
    r=np.array(resid).reshape(len(scen),4)
    print('dsigma',ds,'mean ln(sim/BSSA14) por IMT [pga,0.2,0.5,1.0]:',np.round(r.mean(0),3),'global',round(float(r.mean()),3))
    print('   por escenario', np.round(r.mean(1),2))
