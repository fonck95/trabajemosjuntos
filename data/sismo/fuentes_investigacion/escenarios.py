import sys, math, json
sys.path.insert(0,'.')
from sim import simulate
from gmpe import bchydro_slab, zhao06_slab, bssa14, zhao06_asc
ya15 = lambda M: 10**(-0.405+0.235*M)
CORT = dict(beta_s=3.5, rho_s=2.8, rad=0.55, fs=2.0, part=1/math.sqrt(2), Q0=180., eta=0.45, beta_Q=3.5,
            kappa0=0.04, segs=[(1.0,40.),(0.5,None)], dur='BT14', h_ff=ya15, dsigma=100.)
SLAB = dict(beta_s=4.5, rho_s=3.35, rad=0.55, fs=2.0, part=1/math.sqrt(2), beta_Q=3.5, impedance_deep=True,
            Q0=251., eta=0.58, dur='lin', dur_b=0.05, kappa0=0.035, segs=[(1.0,None)], dsigma=800.)
sc=[('nido_frecuente',5.0,92.,150.,'slab'),('nido_2015',6.2,92.,150.,'slab'),('nido_max_hip',7.0,92.,150.,'slab'),
    ('cimitarra',6.5,20.,10.,'asc'),('la_salina',6.5,47.,10.,'asc'),('palestina',7.0,70.,12.,'asc'),('bucaramanga_sm',7.0,92.,12.,'asc'),
    ('local_hip',6.0,5.,10.,'asc')]
out={}
for name,M,Re,h,t in sc:
    p = SLAB if t=='slab' else CORT
    o = simulate(M,Re,h,p,vs30=270.,nsim=24,seed0=7)
    R=math.sqrt(Re**2+h**2)
    g={}
    for imt in ['pga',0.2,0.5,1.0]:
        if t=='slab': g[str(imt)]=[round(bchydro_slab(imt,M,R,h,270.)[0],4), round(zhao06_slab(imt,M,R,h,270.)[0],4)]
        else: g[str(imt)]=[round(bssa14(imt,M,Re,270.,'U')[0],4), round(zhao06_asc(imt,M,R,h,270.)[0],4)]
    out[name]=dict(Mw=M,Repi=Re,h=h,R_hip=round(R,1),R_usada=round(o['R'],1),f0_Hz=round(o['f0'],3),Tgm_s=round(o['Tgm'],2),
        estocastico=dict(PGA_roca760_g=round(o['pgar'],4),PGA_g=round(o['pga'],4),Sa02_g=round(o[0.2],4),Sa05_g=round(o[0.5],4),Sa10_g=round(o[1.0],4),
                         PGV_cm_s=round(o['pgv'],2),Arias_m_s=round(o['arias'],4),D595_s=round(o['d595'],1)),
        gmpe=g)
    print(name, json.dumps(out[name]))
json.dump(out, open('escenarios_out.json','w'), indent=1)
