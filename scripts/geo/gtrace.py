# gtrace.py spec.json out.png zoom radio [src=google|esri] [clat clon] [grid]
import sys, json, math, io, urllib.request
from PIL import Image, ImageDraw
spec=json.load(open(sys.argv[1])); out=sys.argv[2]; z=int(sys.argv[3]); r=float(sys.argv[4])
src=sys.argv[5] if len(sys.argv)>5 else 'google'
lat0,lon0=spec['lat'],spec['lon']
clat,clon=(float(sys.argv[6]),float(sys.argv[7])) if len(sys.argv)>7 else (lat0,lon0)
grid=len(sys.argv)>8 and sys.argv[8]=='grid'
def rect_pts(v):
    cx,cy=v['centro']; L,A=v['largo'],v['ancho']; rr=math.radians(v.get('rumbo_eje',0))
    ux,uy=math.sin(rr),math.cos(rr); vx,vy=math.cos(rr),-math.sin(rr)
    return [(cx+sx*L/2*ux+sy*A/2*vx, cy+sx*L/2*uy+sy*A/2*vy) for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))]
def pts_of(o):
    if 'poligono' in o: return [tuple(p) for p in o['poligono']]
    if 'centro' in o and 'largo' in o: return rect_pts(o)
shapes=[(v.get('id','?'),pts_of(v),(255,40,40)) for v in spec.get('volumenes',[])]
shapes+=[(e.get('tipo','?'),pts_of(e),(255,220,0)) for e in spec.get('elementos',[]) if pts_of(e) and e.get('tipo')!='arbol']
ad=spec.get('adecuaciones',{})
shapes+=[('FV',pts_of(f),(0,230,255)) for f in ad.get('fv',[]) if pts_of(f)]
if ad.get('bess') and pts_of(ad['bess']): shapes.append(('BESS',pts_of(ad['bess']),(255,0,255)))
def px(la,lo):
    n=256*2**z
    return (lo+180)/360*n,(1-math.log(math.tan(math.radians(la))+1/math.cos(math.radians(la)))/math.pi)/2*n
mpp=156543.03392*math.cos(math.radians(lat0))/2**z
cx,cy=px(clat,clon); h=r/mpp; x0,y0=cx-h,cy-h
ax,ay=px(lat0,lon0)
img=Image.new('RGB',(int(2*h),int(2*h)))
for tx in range(int(x0//256),int((x0+2*h)//256)+1):
    for ty in range(int(y0//256),int((y0+2*h)//256)+1):
        url=(f'https://mt1.google.com/vt/lyrs=s&x={tx}&y={ty}&z={z}' if src=='google' else f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}')
        try: t=Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read())).convert('RGB')
        except Exception as e: print('fallo',e); continue
        img.paste(t,(int(tx*256-x0),int(ty*256-y0)))
if len(sys.argv)>9: img=img.resize((img.width*int(sys.argv[9]),img.height*int(sys.argv[9])),Image.LANCZOS); mpp/=int(sys.argv[9]); h*=int(sys.argv[9])
d=ImageDraw.Draw(img)
offx,offy=(ax-cx)*(1 if len(sys.argv)<=9 else int(sys.argv[9])),(ay-cy)*(1 if len(sys.argv)<=9 else int(sys.argv[9]))
toimg=lambda p:(h+offx+p[0]/mpp, h+offy-p[1]/mpp)
if grid:
    for k in range(-200,201,5):
        X,Y=toimg((k,k)); col=(255,255,255) if k%10 else (255,255,0)
        d.line([(X,0),(X,img.height)],fill=col,width=1); d.line([(0,Y),(img.width,Y)],fill=col,width=1)
        if k%10==0: d.text((X+2,2),str(k),fill='yellow'); d.text((2,Y+2),str(k),fill='yellow')
if spec.get('_no_shapes') is None and not (len(sys.argv)>10 and sys.argv[10]=='noshapes'):
  for label,ps,col in shapes:
    if not ps: continue
    q=[toimg(p) for p in ps]; d.line(q+[q[0]],fill=col,width=2)
    mx,my=sum(a for a,_ in q)/len(q),sum(b for _,b in q)/len(q); d.text((mx-8,my-6),str(label),fill=col)
w=10/mpp; d.rectangle([10,img.height-20,10+w,img.height-14],fill='white')
img.save(out); print(out,img.size,f'{mpp:.3f} m/px')
