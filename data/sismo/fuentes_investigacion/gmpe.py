"""GMPEs transcribed from OpenQuake hazardlib (zhao_2006.py, abrahamson_2015.py, boore_2014.py),
cross-checked against pygmm 0.8.0 CSVs (BC Hydro, BSSA14). Units: g."""
import math
G = 9.80665
# ---------------- Zhao et al. 2006 ----------------
Z_ASC = {  # IMT: a b c d e FR CH C1 C2 C3 C4 sigma QC WC tauC
 'pga': [1.101,-0.00564,0.0055,1.080,0.01412,0.251,0.293,1.111,1.344,1.355,1.420,0.604,0.0,0.0,0.303],
 0.2:   [1.147,-0.00659,0.0120,1.014,0.01462,0.260,1.280,1.669,2.085,2.001,2.030,0.692,0.0,0.0,0.312],
 0.5:   [1.250,-0.00338,0.0060,1.008,0.01114,0.247,-0.207,0.071,0.515,0.934,0.955,0.653,-0.0126,0.0116,0.338],
 1.0:   [1.479,-0.00220,0.0020,1.115,0.01005,0.211,-2.451,-2.152,-1.776,-1.523,-1.084,0.657,-0.0899,0.0440,0.338],
}
Z_SSLAB = {  # SS SSL PS QS WS tauS
 'pga': [2.607,-0.528,0.1392,0.1584,-0.0529,0.321],
 0.2:   [1.901,-0.372,0.1631,0.1856,-0.0644,0.324],
 0.5:   [2.629,-0.554,0.1381,0.1078,-0.0008,0.272],
 1.0:   [2.233,-0.509,0.1060,0.0314,0.0498,0.286],
}
def zhao06_slab(imt, M, rrup, h, vs30):
    a,b,c,d,e,FR,CH,C1,C2,C3,C4,sig,QC,WC,tauC = Z_ASC[imt]
    SS,SSL,PS,QS,WS,tauS = Z_SSLAB[imt]
    x = max(rrup, 0.1)
    r = x + c*math.exp(d*M)
    hh = min(h,125.0)
    dep = e*(hh-15.0) if hh>=15.0 else 0.0
    if vs30>1100: Ck=CH
    elif vs30>600: Ck=C1
    elif vs30>300: Ck=C2
    elif vs30>200: Ck=C3
    else: Ck=C4
    lny = a*M + b*x - math.log(r) + dep + SS + SSL*math.log(x) + Ck + PS*(M-6.5)+QS*(M-6.5)**2+WS
    return math.exp(lny)/100.0/G, math.sqrt(sig**2+tauS**2)
def zhao06_asc(imt, M, rrup, h, vs30, reverse=False):
    a,b,c,d,e,FR,CH,C1,C2,C3,C4,sig,QC,WC,tauC = Z_ASC[imt]
    x = max(rrup,0.1); r = x + c*math.exp(d*M)
    hh=min(h,125.0); dep = e*(hh-15.0) if hh>=15.0 else 0.0
    if vs30>1100: Ck=CH
    elif vs30>600: Ck=C1
    elif vs30>300: Ck=C2
    elif vs30>200: Ck=C3
    else: Ck=C4
    lny = a*M + b*x - math.log(r) + dep + (FR if reverse else 0) + Ck + QC*(M-6.3)**2+WC
    return math.exp(lny)/100.0/G, math.sqrt(sig**2+tauC**2)
# ---------------- BC Hydro (Abrahamson et al. 2016) intraslab ----------------
BC = {  # vlin b theta1 theta2 theta6 theta7 theta8 theta10 theta11 theta12 theta13 theta14 theta15 theta16 phi tau sigma
 'pga': [865.1,-1.186,4.2203,-1.35,-0.0012,1.0988,-1.42,3.12,0.0130,0.980,-0.0135,-0.40,0.9969,-1.00,0.6,0.43,0.74],
 0.2:   [748.2,-2.188,5.2684,-1.40,-0.0018,1.1648,-1.49,3.03,0.0129,2.076,-0.0162,-0.35,1.2230,-1.25,0.6,0.43,0.74],
 0.5:   [456.6,-2.669,4.0181,-1.08,-0.0044,0.5799,-0.82,1.92,0.0125,2.399,-0.0231,-0.19,0.6620,-0.62,0.6,0.43,0.74],
 1.0:   [400.0,-1.955,2.7981,-0.85,-0.0062,0.1746,-0.34,1.10,0.0114,1.470,-0.0363,-0.07,0.3300,-0.14,0.6,0.43,0.74],
}
BCK = dict(n=1.18, c=1.88, theta3=0.1, theta4=0.9, theta5=0.0, theta9=0.4, c4=10.0, C1=7.8)
def _bc_core(C, M, rhypo, h, dc1=-0.3, backarc=False):
    vlin,b,t1,t2,t6,t7,t8,t10,t11,t12,t13,t14,t15,t16,phi,tau,sig = C
    k=BCK
    Mc = k['C1']+dc1
    fmag = (k['theta4'] if M<=Mc else k['theta5'])*(M-Mc) + t13*(10-M)**2
    R = rhypo
    fdist = (t2 + t14 + k['theta3']*(M-7.8))*math.log(R + k['c4']*math.exp((M-6.0)*k['theta9'])) + t6*R + t10
    fdep = t11*(min(h,120.0)-60.0)
    ffaba = (t7 + t8*math.log(max(R,85.0)/40.0)) if backarc else 0.0
    return t1 + k['theta4']*dc1 + fmag + fdist + fdep + ffaba
def bchydro_slab(imt, M, rhypo, h, vs30, backarc=False):
    Cp = BC['pga']; C = BC[imt]; k=BCK
    # PGA on rock vs30=1000
    lnp = _bc_core(Cp, M, rhypo, h, backarc=backarc) + (Cp[9] + Cp[1]*k['n'])*math.log(1000.0/Cp[0])
    pga1000 = math.exp(lnp)
    vlin,b = C[0],C[1]; t12=C[9]
    vs = min(vs30,1000.0); arg = vs/vlin
    if vs30 >= vlin:
        fsite = t12*math.log(arg) + b*k['n']*math.log(arg)
    else:
        fsite = t12*math.log(arg) - b*math.log(pga1000+k['c']) + b*math.log(pga1000 + k['c']*arg**k['n'])
    return math.exp(_bc_core(C, M, rhypo, h, backarc=backarc) + fsite), C[16], pga1000
# ---------------- BSSA14 ----------------
BS = {  # e0 e1 e2 e3 e4 e5 e6 Mh c1 c2 c3 h Dc3 c Vc f4 f5 f6 f7 R1 R2 DfR DfV f1 f2 tau1 tau2
 'pga':[0.4473,0.4856,0.2459,0.4539,1.431,0.05053,-0.1662,5.5,-1.134,0.1917,-0.008088,4.5,0,-0.6,1500,-0.15,-0.00701,-9.9,-9.9,110,270,0.1,0.07,0.695,0.495,0.398,0.348],
 0.2:[1.3255,1.359,1.122,1.3414,1.1349,-0.11096,-0.15852,5.92,-1.0607,0.14489,-0.007717,4.61,0,-0.68762,1392.61,-0.24658,-0.00614,-9.9,-9.9,90.91,270,0.136,0.045,0.711,0.539,0.344,0.309],
 0.5:[0.96991,0.99106,0.7615,1.012,1.0384,-0.23522,0.029119,6.2,-1.1459,0.12015,-0.00322,5.34,0,-0.9693,1203.91,-0.175,-0.00744,-9.9,-9.9,105.54,265,0.109,0.06,0.615,0.599,0.41,0.224],
 1.0:[0.3932,0.4218,0.207,0.4124,1.5004,-0.18983,0.17895,6.2,-1.193,0.10248,-0.00121,5.74,0,-1.05,1109.95,-0.10521,-0.00844,0.36695,0.20789,116.39,270,0.098,0.02,0.553,0.625,0.498,0.298],
}
def _bssa_lnrock(C, M, rjb, mech):
    e0,e1,e2,e3,e4,e5,e6,Mh,c1,c2,c3,h,Dc3 = C[:13]
    E = {'U':e0,'SS':e1,'NS':e2,'RS':e3}[mech]
    fm = E + (e4*(M-Mh)+e5*(M-Mh)**2 if M<=Mh else e6*(M-Mh))
    R = math.sqrt(rjb**2+h**2)
    fp = (c1 + c2*(M-4.5))*math.log(R/1.0) + (c3+Dc3)*(R-1.0)
    return fm+fp
def bssa14(imt, M, rjb, vs30, mech='U'):
    pgar = math.exp(_bssa_lnrock(BS['pga'], M, rjb, mech))
    C = BS[imt]
    c,Vc,f4,f5 = C[13],C[14],C[15],C[16]
    flin = c*math.log(min(vs30,Vc)/760.0)
    f2 = f4*(math.exp(f5*(min(vs30,760.0)-360.0)) - math.exp(f5*(760.0-360.0)))
    fnl = 0.0 + f2*math.log((pgar+0.1)/0.1)
    tau = C[25] if M<=4.5 else (C[26] if M>=5.5 else C[25]+(C[26]-C[25])*(M-4.5))
    phiM = C[23] if M<=4.5 else (C[24] if M>=5.5 else C[23]+(C[24]-C[23])*(M-4.5))
    R1,R2,DfR,DfV = C[19],C[20],C[21],C[22]
    if rjb>R2: phiM += DfR
    elif rjb>R1: phiM += DfR*math.log(rjb/R1)/math.log(R2/R1)
    if vs30<=225: phiM -= DfV
    elif vs30<=300: phiM -= DfV*math.log(300/vs30)/math.log(300/225)
    return math.exp(_bssa_lnrock(C, M, rjb, mech)+flin+fnl), math.sqrt(tau**2+phiM**2), pgar, flin, fnl
