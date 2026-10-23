import sys, math, numpy as np
sys.path.insert(0,'.')
from sim import simulate
from gmpe import bchydro_slab, zhao06_slab
base = dict(beta_s=4.5, rho_s=3.35, rad=0.55, fs=2.0, part=1/math.sqrt(2), beta_Q=3.5, impedance_deep=True,
            Q0=251., eta=0.58, dur='lin', dur_b=0.05, kappa0=0.035)
scen = [(5.0,92.,150.),(5.5,92.,150.),(6.2,92.,150.),(6.2,0.,150.),(6.2,200.,150.),(6.2,300.,150.),(6.8,92.,150.),(6.2,92.,100.)]
for name, segs, dss in [('D R^-1->200, R^-0.5', [(1.0,200.),(0.5,None)], [500.,700.]), ('E R^-1 todo', [(1.0,None)], [800.,1100.])]:
    for ds in dss:
        p = dict(base, dsigma=ds, segs=segs)
        rows=[]
        for M,Re,h in scen:
            o = simulate(M, Re, h, p, vs30=270., nsim=12)
            R = math.sqrt(Re**2+h**2)
            rows.append([math.log(o[imt]/math.sqrt(bchydro_slab(imt,M,R,h,270.)[0]*zhao06_slab(imt,M,R,h,270.)[0])) for imt in ['pga',0.2,0.5,1.0]])
        r=np.array(rows)
        print(name,'ds',ds,'IMT',np.round(r.mean(0),2),'glob',round(float(r.mean()),2),'escen',np.round(r.mean(1),2))
