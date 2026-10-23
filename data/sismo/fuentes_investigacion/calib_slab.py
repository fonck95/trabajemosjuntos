import sys, math, numpy as np
sys.path.insert(0,'.')
from sim import simulate
from gmpe import bchydro_slab, zhao06_slab
base = dict(beta_s=4.5, rho_s=3.35, rad=0.55, fs=2.0, part=1/math.sqrt(2), beta_Q=3.5,
            kappa0=0.04, impedance_deep=True)
variants = {
 'A: R^-1 todo, Q=180f^0.45, Dp=0.05R': dict(segs=[(1.0,None)], Q0=180., eta=0.45, dur='lin', dur_b=0.05),
 'B: R^-1 a 100 y R^-0.5, Q=251f^0.58, Dp=0.05R': dict(segs=[(1.0,100.),(0.5,None)], Q0=251., eta=0.58, dur='lin', dur_b=0.05),
 'C: R^-1 todo, Q=251f^0.58, Dp=BT14': dict(segs=[(1.0,None)], Q0=251., eta=0.58, dur='BT14'),
}
# Nest scenarios: h=150, Repi 0..300
scen = [(5.0,92.,150.),(6.2,92.,150.),(6.2,0.,150.),(6.2,200.,150.),(6.2,300.,150.),(6.8,92.,150.),(5.5,92.,150.)]
for name, v in variants.items():
    for ds in [100., 200., 400.]:
        p = dict(base, dsigma=ds, **v)
        rows=[]
        for M,Re,h in scen:
            o = simulate(M, Re, h, p, vs30=270., nsim=12)
            R = math.sqrt(Re**2+h**2)
            rr=[]
            for imt in ['pga',0.2,0.5,1.0]:
                gb = bchydro_slab(imt, M, R, h, 270.)[0]; gz = zhao06_slab(imt, M, R, h, 270.)[0]
                gm = math.sqrt(gb*gz)
                rr.append(math.log(o[imt]/gm))
            rows.append(rr)
        r=np.array(rows)
        print(name,'dsigma',ds,'IMT',np.round(r.mean(0),2),'glob',round(float(r.mean()),2),'escen',np.round(r.mean(1),2))
