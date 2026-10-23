import sys, math, json
sys.path.insert(0,'.')
from gmpe import bchydro_slab, zhao06_slab, bssa14, zhao06_asc
def hav(a,b):
    R=6371.0; la1,lo1=map(math.radians,a); la2,lo2=map(math.radians,b)
    d=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(d))
Y=(7.005,-73.915)
for n,p in [('nido 6.80,-73.10',(6.80,-73.10)),('nido 6.82,-73.17',(6.82,-73.17)),('nido 6.75,-73.05',(6.75,-73.05)),('Bucaramanga ciudad',(7.12,-73.12)),('San Jose del Palmar',(4.97,-76.23)),('Pereira',(4.81,-75.69)),('Barrancabermeja',(7.065,-73.85)),('Armenia',(4.53,-75.68))]:
    print(n, round(hav(Y,p),1))
# NSR-10
Aa=Av=0.15; Fa=1.5; Fv=2.2; I=1.5
TC=0.48*Av*Fv/(Aa*Fa); T0=0.1*Av*Fv/(Aa*Fa); TL=2.4*Fv
def Sa(T):
    if T<=TC: return 2.5*Aa*Fa*I
    if T<=TL: return 1.2*Av*Fv*I/T
    return 1.2*Av*Fv*TL*I/T**2
def Sa_din(T):
    return 2.5*Aa*Fa*I*(0.4+0.6*T/T0) if T<T0 else Sa(T)
Ta=0.047*17.1**0.9
print('TC',round(TC,3),'T0',round(T0,4),'TL',TL,'Ta',round(Ta,3),'Sa(Ta)',round(Sa(Ta),3))
print({T:round(Sa(T),3) for T in [0.0,0.2,0.5,1.0,2.0]}, 'Sa_din(0)',round(Sa_din(0),3))
print('Sa/I (sin importancia) a 0,2/0,5/1,0:', [round(Sa(T)/I,3) for T in [0.2,0.5,1.0]], 'Aa*Fa', Aa*Fa)
# GMPE scenarios
sc=[('nido_frecuente',5.0,92.,150.,'slab'),('nido_2015',6.2,92.,150.,'slab'),('nido_max_hip',7.0,92.,150.,'slab'),
    ('cimitarra',6.5,20.,10.,'asc'),('palestina',7.0,70.,12.,'asc'),('la_salina',6.5,47.,10.,'asc'),('bucaramanga_sm',7.0,92.,12.,'asc')]
for name,M,Re,h,t in sc:
    R=math.sqrt(Re**2+h**2)
    out={}
    if t=='slab':
        for imt in ['pga',0.2,0.5,1.0]:
            b=bchydro_slab(imt,M,R,h,270.)[0]; z=zhao06_slab(imt,M,R,h,270.)[0]
            out[str(imt)]=(round(b,4),round(z,4))
    else:
        for imt in ['pga',0.2,0.5,1.0]:
            b=bssa14(imt,M,max(Re-0,0),270.,'U')[0]; z=zhao06_asc(imt,M,R,h,270.)[0]
            out[str(imt)]=(round(b,4),round(z,4))
    print(name,M,Re,h,'Rhyp',round(R,1),out)
