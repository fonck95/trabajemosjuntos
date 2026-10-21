# Utilidades compartidas: rumbo, distancia y proyección en perspectiva de un panorama equirectangular
import math
import numpy as np
from PIL import Image

def bearing(la1, lo1, la2, lo2):
    y = math.sin(math.radians(lo2-lo1))*math.cos(math.radians(la2))
    x = math.cos(math.radians(la1))*math.sin(math.radians(la2)) - math.sin(math.radians(la1))*math.cos(math.radians(la2))*math.cos(math.radians(lo2-lo1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360
def dist(la1, lo1, la2, lo2):
    k = 111320; return math.hypot((la2-la1)*k, (lo2-lo1)*k*math.cos(math.radians(la1)))
def persp(eq, yaw_deg, pitch_deg=8, fov=75, W=1200, H=800):
    eq = np.asarray(eq); h, w = eq.shape[:2]
    f = (W/2)/math.tan(math.radians(fov)/2)
    xs, ys = np.meshgrid(np.arange(W)-W/2, np.arange(H)-H/2)
    d = np.stack([xs, -ys, np.full_like(xs, f, dtype=float)], -1); d /= np.linalg.norm(d, axis=-1, keepdims=True)
    p = math.radians(pitch_deg); cp, sp = math.cos(p), math.sin(p)
    y2 = d[...,1]*cp + d[...,2]*sp; z2 = -d[...,1]*sp + d[...,2]*cp
    lonr = np.arctan2(d[...,0], z2) + math.radians(yaw_deg); latr = np.arcsin(np.clip(y2, -1, 1))
    # en los panoramas de Google la columna central corresponde al rumbo del carro (heading): se suma media vuelta
    u = ((lonr/(2*math.pi) + 0.5) % 1.0) * w; v = (0.5 - latr/math.pi) * h
    return Image.fromarray(eq[np.clip(v.astype(int), 0, h-1), np.clip(u.astype(int), 0, w-1)])
