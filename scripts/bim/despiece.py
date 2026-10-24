"""Despiece del refuerzo en geometría real (equipo F, contrato 17.3 y 17.4).

Lee el despiece de A (data/sismo/torre_hospital_estructura.json → refuerzo y cimentacion), sin cambiar ningún número
de diseño (número de barras, N.º, separaciones, zonas confinadas, recubrimientos, largos de traslapo y de anclaje), y
lo convierte en JUEGOS de barras idénticas: una polilínea de eje (con los dobleces redondeados y los ganchos) y la lista
de copias (traslaciones). Un juego es lo que IFC4 permite representar con un IfcReinforcingBar («una o varias barras
iguales, por ejemplo una fila»). Las espirales de los pilotes van en forma paramétrica (hélice) y se expanden con
expandir().

Lo que el despiece de A no fija y aquí se decide para dibujar (criterios del modelo, documentados en el BIM):
- Columnas: las barras de cada piso se traslapan en la mitad central de la altura libre (z_centro y largo de A); las
  de abajo se doblan hacia adentro un diámetro (pendiente 1:6) para quedar al lado de las de arriba (traslapo de
  contacto). En el piso 1 bajan por el arranque (entre la cara superior del dado y el piso) hasta la parrilla inferior
  del dado y terminan con gancho de 90° hacia afuera; en el último piso, gancho de 90° hacia adentro bajo la cubierta.
  Estribos: primer estribo a 0,05 m, zona lo arriba y abajo, centro y nudo con los conteos de A. Ganchos
  suplementarios al lado de las barras intermedias, un diámetro de estribo por encima del estribo (x) o dos (y).
- Vigas: barras superiores e inferiores dentro de las esquinas de los estribos; las vigas en y llevan su capa superior
  un diámetro N.º 8 más abajo y la inferior uno más arriba, para cruzar las de x en los nudos. Las corridas de luces
  vecinas con el mismo armado son continuas; si cambia el armado, la barra termina en el eje del nudo (como pesa A);
  en los nudos exteriores, gancho de 90° por dentro de las barras de la columna. Traslapos cada 12 m (largo comercial):
  arriba en el centro de la luz y abajo fuera de las zonas 2h (C.21.5.2.3, criterio de A).
- Losa nervada: barras de los nervios dentro de sus estribos; la malla de la loseta encima (recubrimiento de 20 mm) y
  las barras superiores de los nervios y sus estribos debajo de la malla.
- Muros: barras de borde en parejas (u de A) dentro de los estribos especiales; horizontales de las cortinas por dentro
  de las barras de borde y verticales por dentro de las horizontales; las horizontales empiezan a medio paso para no
  coincidir con los estribos de borde.
- Cimentación: parrillas centradas en el dado; pilotes con canasta de 8 barras arriba y 6 abajo traslapadas y espiral.

Todas las cotas en metros, z desde el piso terminado del piso 1."""
import bisect
import math

from comun import r, rp, largo_polilinea

# Barras NTC 2289 (A: refuerzo.convenciones.barras): diámetro (mm), área (mm²), masa (kg/m)
BARRAS = {3: (9.5, 71.0, 0.560), 4: (12.7, 129.0, 0.994), 5: (15.9, 199.0, 1.552), 6: (19.1, 284.0, 2.235),
          7: (22.2, 387.0, 3.042), 8: (25.4, 510.0, 3.973)}
MALLA = {5.0: (19.6, 0.154), 7.0: (38.5, 0.302)}       # alambre de malla electrosoldada: área (mm²), kg/m
FC, FY = 28.0, 420.0
S8 = 0.0254                                            # diámetro N.º 8: separación de capas en los nudos


def db_de(num):
    return BARRAS[num][0] / 1000


def ld_traccion(num, sup=False):
    """NSR-10 C.12.2.2 (la misma fórmula de A)."""
    db = db_de(num)
    k = 2.1 if num <= 6 else 1.7
    return max(FY * (1.3 if sup else 1.0) / (k * math.sqrt(FC)) * db, 0.300)


def ldh_sismico(num):
    db = db_de(num)
    return max(FY * db / (5.4 * math.sqrt(FC)), 8 * db, 0.150)


def traslapo(num, sup=False):
    return 1.3 * ld_traccion(num, sup)


def radio_doblez(num, estribo=False):
    """Radio del eje de la barra en un doblez: diámetro interior 4·db en estribos N.º 3-5 y 6·db en barras N.º 3-8
    (NSR-10 C.7.2.1 y C.7.2.2) → radio de eje = D/2 + db/2."""
    db = db_de(num)
    return (2.0 if estribo and num <= 5 else 3.0) * db + db / 2


def cola_135(num):
    """Extensión recta de un gancho sísmico de 135°: 6·db ≥ 75 mm (C.7.1.3 y C.21.1)."""
    return max(6 * db_de(num), 0.075)


def cola_90(num):
    """Extensión recta de un gancho estándar de 90°: 12·db (C.7.1.2)."""
    return 12 * db_de(num)


def n_estribos(largo, s, primero=0.05):
    return max(int(math.floor((largo - primero) / s + 1e-9)) + 1, 0) if largo > primero else 0


# ------------------------------------------------------------------------------------------------------- vectores
def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _add(a, b, k=1.0):
    return [a[i] + k * b[i] for i in range(3)]


def _mul(a, k):
    return [c * k for c in a]


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(a):
    L = math.sqrt(_dot(a, a))
    return [c / L for c in a] if L > 0 else [0.0, 0.0, 0.0]


def doblar(pts, radio, nseg=4):
    """Redondea los vértices interiores de la polilínea con arcos (Bézier cuadrática de nseg tramos) del radio de eje
    dado. El largo de la barra es el de la polilínea redondeada."""
    if len(pts) < 3 or radio <= 0:
        return [list(p) for p in pts]
    out = [list(pts[0])]
    for i in range(1, len(pts) - 1):
        A, P, C = pts[i - 1], pts[i], pts[i + 1]
        u, w = _norm(_sub(P, A)), _norm(_sub(C, P))
        c = max(-1.0, min(1.0, _dot(u, w)))
        th = math.acos(c)
        if th < 1e-6:
            out.append(list(P))
            continue
        t = radio * math.tan(th / 2)
        t = min(t, 0.49 * math.dist(A, P) if i > 1 else 0.9 * math.dist(A, P),
                0.49 * math.dist(P, C) if i < len(pts) - 2 else 0.9 * math.dist(P, C))
        T1, T2 = _add(P, u, -t), _add(P, w, t)
        for k in range(nseg + 1):
            s = k / nseg
            out.append([(1 - s) ** 2 * T1[j] + 2 * s * (1 - s) * P[j] + s * s * T2[j] for j in range(3)])
    out.append(list(pts[-1]))
    # quitar puntos repetidos
    lim = [out[0]]
    for p in out[1:]:
        if math.dist(p, lim[-1]) > 1e-6:
            lim.append(p)
    return lim


def _arco(c, R, t0, t1, n=4):
    return [(c[0] + R * math.cos(t0 + (t1 - t0) * k / n), c[1] + R * math.sin(t0 + (t1 - t0) * k / n)) for k in range(n + 1)]


def estribo_cerrado(o, ea, eb, hx, hy, num, n_desfase, gancho=135, db_esq=None):
    """Estribo cerrado en el plano (ea, eb) centrado en o; hx, hy: semilados del EJE de la barra. Las esquinas son arcos
    de radio R = máx(2,5·de, (de + db)/2) (diámetro interior 4·de, C.7.2.2) alrededor de las barras de esquina, y los
    dos ganchos (de 135° con cola de 6·de ≥ 75 mm, o de 90° en nervios) envuelven la barra de la esquina (−hx, +hy): sus
    colas son tangentes al doblez y quedan a los lados de la barra. El segundo extremo se corre un diámetro según
    n_desfase (los ganchos se superponen en la obra)."""
    db = db_de(num)
    R = max(2.5 * db, (db + (db_esq or db)) / 2)
    R = min(R, hx * 0.95, hy * 0.95)
    L = cola_135(num) if gancho == 135 else cola_90(num)
    cTL, cTR, cBR, cBL = (-hx + R, hy - R), (hx - R, hy - R), (hx - R, -hy + R), (-hx + R, -hy + R)
    r45 = math.pi / 4
    pts = []
    if gancho == 135:
        a0 = (cTL[0] + R * math.cos(5 * r45), cTL[1] + R * math.sin(5 * r45))
        dcola = (math.cos(-r45), math.sin(-r45))
        # en secciones angostas la cola se endereza para no salirse ni tocar la barra de la otra esquina
        lim_a = (hx - (db_esq or db) - db) - a0[0]
        ta = min(L * dcola[0], max(lim_a, 0.0))
        tb = -math.sqrt(max(L * L - ta * ta, 0.0))
        pts.append((a0[0] + ta, a0[1] + tb, 0.0))
        pts += [(x, y, 0.0) for x, y in _arco(cTL, R, 5 * r45, 2 * r45, 6)]
    else:
        pts.append((cTL[0] - R, cTL[1] - L, 0.0))
        pts += [(x, y, 0.0) for x, y in _arco(cTL, R, math.pi, math.pi / 2, 4)]
    pts += [(x, y, 0.0) for x, y in _arco(cTR, R, math.pi / 2, 0.0, 4)]
    pts += [(x, y, 0.0) for x, y in _arco(cBR, R, 0.0, -math.pi / 2, 4)]
    pts += [(x, y, 0.0) for x, y in _arco(cBL, R, -math.pi / 2, -math.pi, 4)]
    if gancho == 135:
        fin = _arco(cTL, R, math.pi, r45, 6)
        e0 = fin[-1]
        lim_a = (hx - (db_esq or db) - db) - e0[0]
        ta = min(L * dcola[0], max(lim_a, 0.0))
        tb = -math.sqrt(max(L * L - ta * ta, 0.0))
        fin = fin + [(e0[0] + ta, e0[1] + tb)]
    else:
        fin = _arco(cTL, R, math.pi, math.pi / 2, 4) + [(cTL[0] + L, hy)]
    pts += [(x, y, db) for x, y in fin]
    return [[o[i] + a * ea[i] + b * eb[i] + w * n_desfase[i] for i in range(3)] for a, b, w in pts]


def gancho_envolvente(b0, b1, lado, rho, num):
    """Gancho suplementario entre las barras b0 y b1 (centros, en el plano del gancho): corre al lado de ellas (a rho del
    centro, hacia −lado) y en cada extremo envuelve la barra 135° con cola tangente de 6·db ≥ 75 mm hacia el núcleo."""
    d = _norm(_sub(b1, b0))
    n = lado
    L = cola_135(num)

    def P(cen, u, v):
        return [cen[i] + d[i] * u + n[i] * v for i in range(3)]
    pts = []
    # extremo b0: llega desde la cola, envuelve la barra pasando por −d y termina a −rho·n yendo hacia b1
    for k in range(7):
        t = math.radians(135) - math.radians(135) * k / 6        # ángulo medido desde −n, girando por −d
        pts.append(P(b0, -rho * math.sin(t), -rho * math.cos(t)))
    c0 = pts[0]
    t0 = [d[i] * math.cos(math.radians(45)) + n[i] * math.sin(math.radians(45)) for i in range(3)]
    pts = [[c0[i] + t0[i] * L for i in range(3)]] + pts
    for k in range(7):
        t = math.radians(135) * k / 6
        pts.append(P(b1, rho * math.sin(t), -rho * math.cos(t)))
    c1 = pts[-1]
    t1 = [-d[i] * math.cos(math.radians(45)) + n[i] * math.sin(math.radians(45)) for i in range(3)]
    pts.append([c1[i] + t1[i] * L for i in range(3)])
    return pts


def esquina_en_doblez(c, hh, num, num_e):
    """Coordenada de una barra de esquina asentada en el doblez del estribo (radio interior 2·de): no puede quedar a
    c = hh − (de + db)/2 de los dos ramales a la vez sin meterse en el arco; se corre hacia adentro en diagonal."""
    db, de = db_de(num), db_de(num_e)
    R = radio_doblez(num_e, True)
    lim = (hh - R) + max(R - (de + db) / 2, 0.0) / math.sqrt(2)
    return min(c, lim)


# ---------------------------------------------------------------------------------------------------------- juegos
class Juegos:
    """Juegos de barras iguales: forma (polilínea de eje de la primera barra, absoluta) + copias (traslaciones)."""

    def __init__(self):
        self.lista = []
        self._n = {}

    def agregar(self, host, rol, num, forma, copias, etiqueta, zona=None, ganchos=None, diam_mm=None, kg_m=None,
                param=None, nivel=None, nota=None, grupo=None):
        if not copias:
            return None
        k = self._n.get(host, 0) + 1
        self._n[host] = k
        db = db_de(num) if num else diam_mm / 1000
        kgm = BARRAS[num][2] if num else kg_m
        if param is not None:
            L = largo_parametrico(param)
        else:
            forma = [rp(p, 4) for p in forma]
            L = largo_polilinea(forma)
        cps = [rp(c, 4) for c in copias]
        j = {'id': f'R-{host}-{k:02d}', 'host': host, 'rol': rol, 'num': num, 'db': r(db, 4)}
        if not num:
            j['diam_mm'] = diam_mm
        j['etiqueta'] = etiqueta
        if zona is not None:
            j['zona'] = zona
        if ganchos is not None:
            j['ganchos'] = ganchos
        j.update({'largo': r(L, 3), 'n': len(cps), 'kg': r(L * len(cps) * kgm, 2), 'kg_m': kgm})
        if param is not None:
            j['param'] = param
        else:
            j['forma'] = forma
        j['copias'] = cps
        if nivel:
            j['nivel'] = nivel
        if nota:
            j['nota'] = nota
        j['grupo'] = grupo or host
        self.lista.append(j)
        return j


def largo_parametrico(p):
    if p['tipo'] == 'espiral':
        L = 0.0
        for t in p['tramos']:
            vueltas = (t['z1'] - t['z0']) / t['paso']
            L += vueltas * math.hypot(2 * math.pi * p['radio'], t['paso'])
        return L
    raise ValueError(p['tipo'])


def expandir_param(p, puntos_por_vuelta=24):
    """Polilínea de una forma paramétrica (la espiral baja desde z1 hasta z0 por tramos de paso distinto). Los vértices van
    a un radio tal que la polilínea se aparta lo mismo hacia afuera (en los vértices) que hacia adentro (en la mitad de
    cada cuerda): con 24 lados por vuelta, ± 1 mm de la hélice real; el recubrimiento se mide con la hélice."""
    if p['tipo'] != 'espiral':
        raise ValueError(p['tipo'])
    cx, cy = p['centro']
    R = p['radio'] * 2 / (1 + math.cos(math.pi / puntos_por_vuelta))
    pts = []
    ang = 0.0
    tramos = sorted(p['tramos'], key=lambda t: -t['z1'])
    for t in tramos:
        vueltas = (t['z1'] - t['z0']) / t['paso']
        n = max(int(round(vueltas * puntos_por_vuelta)), 1)
        for i in range(n + (1 if t is tramos[-1] else 0)):
            z = t['z1'] - (t['z1'] - t['z0']) * i / n
            pts.append([cx + R * math.cos(ang), cy + R * math.sin(ang), z])
            ang += 2 * math.pi * vueltas / n
    return pts


def polilinea(j):
    return j['forma'] if 'forma' in j else expandir_param(j['param'])


# ======================================================================================================= columnas
def _caras_columna(n, num, b, rec, num_e):
    """Posiciones (relativas al centro) de las n barras repartidas en 4 caras con nf por cara, y la normal hacia
    afuera de cada una (para ganchos y dobleces)."""
    nf = n // 4 + 1
    c = b / 2 - rec - db_de(num_e) - db_de(num) / 2
    ce = esquina_en_doblez(c, b / 2 - rec - db_de(num_e) / 2, num, num_e)
    pos = []
    for i in range(nf):
        t = -c + 2 * c * i / (nf - 1)
        pos += [(t, -c), (c, t), (-t, c), (-c, -t)]
    pos = [(math.copysign(ce, px), math.copysign(ce, py)) if abs(px) > c - 1e-9 and abs(py) > c - 1e-9 else (px, py)
           for px, py in pos]
    unicos = []
    for p in pos:
        if not any(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for q in unicos):
            unicos.append(p)
    out = []
    for (px, py) in unicos:
        nx = (1 if px > ce - 1e-9 else -1 if px < -ce + 1e-9 else 0)
        ny = (1 if py > ce - 1e-9 else -1 if py < -ce + 1e-9 else 0)
        out.append(((px, py), (nx, ny)))
    out.sort(key=lambda q: (round(q[0][1], 6), round(q[0][0], 6)))
    return out, c, nf


def _elegir(intermedias, k):
    """k posiciones simétricas de la lista de intermedias (si sobra una, se deja la del centro)."""
    m = len(intermedias)
    if k >= m:
        return list(intermedias)
    if k <= 0:
        return []
    idx = sorted({int(round((i + 0.5) * m / k - 0.5)) for i in range(k)})
    if m % 2 == 1 and k % 2 == 0 and m // 2 in idx:
        idx = [i for i in range(m) if i != m // 2][:k] if k == m - 1 else idx
    return [intermedias[i] for i in idx]


def _reparto_centro(a_, b_, s):
    """Estribos entre el último de una zona confinada (a_) y el primero de la otra (b_), a paso uniforme ≤ s."""
    n_c = max(int(math.ceil((b_ - a_) / s - 1e-9)) - 1, 0)
    return [a_ + (b_ - a_) * (i + 1) / (n_c + 1) for i in range(n_c)]


def paso_max(zs):
    zs = sorted(zs)
    return max([b - a for a, b in zip(zs, zs[1:])] or [0.0])


def zs_estribos_columna(z0, h_ent, h_viga, lo, s_lo, s_c, toda):
    """Zona lo abajo y arriba de la luz libre (primero a 0,05 m de la cara), el centro repartido entre el último estribo de
    la zona de abajo y el primero de la de arriba (paso ≤ s del centro, también en la transición) y el nudo."""
    ln = h_ent - h_viga
    n_lo = n_estribos(lo, s_lo)
    abajo = [z0 + 0.05 + i * s_lo for i in range(n_lo)]
    arriba = [z0 + ln - 0.05 - i * s_lo for i in range(n_lo)]
    if abajo and arriba and min(arriba) - max(abajo) < s_lo - 1e-9:          # zonas que se tocan: todo a s_lo
        abajo = [z0 + 0.05 + (ln - 0.10) * i / max(int(math.ceil((ln - 0.10) / s_lo - 1e-9)), 1)
                 for i in range(int(math.ceil((ln - 0.10) / s_lo - 1e-9)) + 1)]
        arriba, centro = [], []
    else:
        centro = _reparto_centro(max(abajo), min(arriba), s_lo if toda else s_c)
    n_nudo = max(int(math.ceil(h_viga / s_lo - 1e-9)), 1)
    nudo = [z0 + ln + (i + 0.5) * h_viga / n_nudo for i in range(n_nudo)]
    zs = sorted(abajo + centro + arriba + nudo)
    return zs, {'lo_abajo': len(abajo), 'centro': len(centro), 'lo_arriba': len(arriba), 'nudo': len(nudo)}


def _evitar_capas(zs, zmin, zmax, capas, de, fallas=None):
    """Corre cada z de estribo del nudo (y de sus ganchos suplementarios, a +de y +2·de) fuera de las bandas de las
    barras de las vigas (z, db) que cruzan el nudo."""
    def libre(z):
        return all(abs(z + k * de - zc) >= (dc + de) / 2 + 0.002 for zc, dc in capas for k in (0, 1, 2))
    out = []
    for z in zs:
        if zmin - 1e-9 <= z <= zmax + 1e-9 and libre(z) and all(abs(z - q) > 3 * de + 0.002 for q in out):
            out.append(z)
            continue
        mejor = None
        for k in range(1, 40):
            for sg in (1, -1):
                zz = z + sg * k * 0.0025
                if zmin <= zz <= zmax and libre(zz) and all(abs(zz - q) > 3 * de + 0.002 for q in out):
                    mejor = zz
                    break
            if mejor is not None:
                break
        if mejor is None and fallas is not None:
            fallas.append(z)
        out.append(mejor if mejor is not None else z)
    return out


def _d_punto_seg2(p, a, b):
    ax, ay = a[0], a[1]
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _amarres_columna(x, y, z, b, rec, barras, cc, nf, ng, num, num_e):
    """Estribo cerrado y ganchos suplementarios de un armado (posiciones relativas al centro) en la altura z:
    [(rol, forma, etiqueta corta)]. Los ganchos en x van a +de y los de y a +2·de sobre el estribo."""
    db, de = db_de(num), db_de(num_e)
    hh = b / 2 - rec - de / 2
    out = [('estribo', estribo_cerrado([x, y, z], [1, 0, 0], [0, 1, 0], hh, hh, num_e, [0, 0, -1], db_esq=db))]
    inter = [-cc + 2 * cc * j / (nf - 1) for j in range(1, nf - 1)]
    for direc, dz in (('x', de), ('y', 2 * de)):
        for t in _elegir(inter, ng):
            # el gancho va al lado del centro de la barra que amarra y su cola vuelve por el lado de la barra
            sg = 1 if t > 1e-9 else -1 if t < -1e-9 else 1
            rho = (db + de) / 2 + 0.0005
            if direc == 'x':
                b0_, b1_, lado = [x - cc, y + t, z + dz], [x + cc, y + t, z + dz], [0, sg, 0]
            else:
                b0_, b1_, lado = [x + t, y - cc, z + dz], [x + t, y + cc, z + dz], [sg, 0, 0]
            out.append((f'gancho_suplementario_{direc}', gancho_envolvente(b0_, b1_, lado, rho, num_e)))
    return out


def _ubicar_traslapo(abajo, arriba, amarres, x, y, db, db_up, de, c_lim):
    """Posición de cada barra de abajo en el traslapo (relativa al centro): se queda donde está si no toca las barras de
    arriba ni los estribos y ganchos del armado de arriba; si no, se dobla al sitio libre más cercano junto a una barra de
    arriba (traslapo de contacto, o a un diámetro). Criterio del modelo (C.7.8.1 y C.12.17)."""
    segs = []
    for _rol, forma in amarres:
        segs += [((a[0] - x, a[1] - y), (b_[0] - x, b_[1] - y)) for a, b_ in zip(forma, forma[1:])]
    r_am = (db + de) / 2 + 0.0008
    r_ar = (db + db_up) / 2 + 0.0005
    puestas = []

    def libre(q):
        if abs(q[0]) > c_lim + 1e-9 or abs(q[1]) > c_lim + 1e-9:
            return False
        if any(math.hypot(q[0] - u[0], q[1] - u[1]) < r_ar - 1e-9 for (u, _n) in arriba):
            return False
        if any(math.hypot(q[0] - u[0], q[1] - u[1]) < db + 0.001 for u in puestas):
            return False
        return all(_d_punto_seg2(q, a, b_) >= r_am for a, b_ in segs)
    orden = sorted(range(len(abajo)), key=lambda i: (round(min(math.hypot(abajo[i][0][0] - u[0], abajo[i][0][1] - u[1])
                                                                 for (u, _n) in arriba), 6), i))
    res = {}
    for i in orden:
        p = abajo[i][0]
        if libre(p):
            res[i] = p
            puestas.append(p)
            continue
        mejor = None
        for (u, _n) in arriba:
            if math.hypot(u[0] - p[0], u[1] - p[1]) > 0.15:
                continue
            for anillo, castigo in ((r_ar, 0.0), (r_ar + db + 0.002, 0.02)):
                for k in range(36):
                    a = math.radians(10 * k)
                    q = (round(u[0] + anillo * math.cos(a), 5), round(u[1] + anillo * math.sin(a), 5))
                    d = math.hypot(q[0] - p[0], q[1] - p[1]) + castigo
                    if (mejor is None or d < mejor[0] - 1e-9) and libre(q):
                        mejor = (d, q)
        q = mejor[1] if mejor else p
        res[i] = q
        puestas.append(q)
    return [res[i] for i in range(len(abajo))]


def columnas(J, est, bases, capas_nudo=None):
    """bases: {'C-A1': {'z_tope': cara superior del dado o losa de pilotes, 'z_parrilla': z del tope de la parrilla
    inferior, 'host_arranque': id del arranque}}"""
    ref = est['refuerzo']
    rec = ref['convenciones']['recubrimientos_m']['columna']
    por_linea = {}
    for c in ref['columnas']:
        por_linea.setdefault(c['id'].rsplit('-', 1)[0], []).append(c)
    resumen = {}
    for linea in sorted(por_linea):
        pisos = sorted(por_linea[linea], key=lambda c: c['nivel'])
        N = len(pisos)
        base = bases[linea]
        for i, c in enumerate(pisos):
            k = c['nivel']
            host = c['id']
            num, n = c['longitudinal']['num'], c['longitudinal']['n']
            e = c['estribos']
            num_e = e['num']
            db, de = db_de(num), db_de(num_e)
            b = c['b']
            x, y = c['x'], c['y']
            z0, z1 = c['z0'], c['z1']
            barras, cc, nf = _caras_columna(n, num, b, rec, num_e)
            R = radio_doblez(num)
            lap = c['longitudinal']['traslapo']
            lap_abajo = pisos[i - 1]['longitudinal']['traslapo'] if i > 0 else None
            pareja = {}
            cambio = None                                 # armado de arriba (amarres desde z_cambio)
            if lap and i + 1 < N and abs(pisos[i + 1]['b'] - b) < 1e-9:
                cs = pisos[i + 1]
                num_up, n_up = cs['longitudinal']['num'], cs['longitudinal']['n']
                arriba_b, cc_up, nf_up = _caras_columna(n_up, num_up, b, rec, cs['estribos']['num'])
                db_up = db_de(num_up)
                ng_c = max(e['ganchos_suplementarios_por_direccion'], cs['estribos']['ganchos_suplementarios_por_direccion'])
                am_up = _amarres_columna(x, y, 0.0, b, rec, arriba_b, cc_up, nf_up, ng_c, num_up, num_e)
                c_lim = b / 2 - rec - de - db / 2 + 1e-6
                sitios = _ubicar_traslapo(barras, arriba_b, am_up, x, y, db, db_up, de, c_lim)
                for ((px, py), _n), (tx, ty) in zip(barras, sitios):
                    if math.hypot(tx - px, ty - py) > 1e-6:
                        pareja[(px, py)] = (tx, ty)
                desv_max = max([math.hypot(tx - px, ty - py) for (px, py), (tx, ty) in pareja.items()] or [0.0])
                zc0_ = lap['z_centro'] - lap['largo_m'] / 2
                cambio = {'z': zc0_ - (max(6 * desv_max, 0.05) if pareja else 0.0) - 0.01, 'barras': arriba_b, 'cc': cc_up,
                          'nf': nf_up, 'ng': ng_c, 'num': num_up}
            # ---- longitudinales: un juego por dirección de gancho o doblez
            grupos = {}
            for (px, py), (nx, ny) in barras:
                if k == 1:
                    zb = base['z_parrilla'] + db / 2
                else:
                    zb = lap_abajo['z_centro'] - lap_abajo['largo_m'] / 2
                pts = []
                if k == 1:
                    gx, gy = (nx, ny) if (nx or ny) else (1, 0)
                    L = math.hypot(gx, gy)
                    pts.append([x + px + gx / L * (cola_90(num) + R), y + py + gy / L * (cola_90(num) + R), zb])
                pts.append([x + px, y + py, zb])
                if lap:                                   # sigue al piso de arriba: doblez y traslapo en su mitad central
                    zc0 = lap['z_centro'] - lap['largo_m'] / 2
                    zc1 = lap['z_centro'] + lap['largo_m'] / 2
                    if (px, py) in pareja:                # al lado de la barra de arriba (traslapo de contacto)
                        tx, ty = pareja[(px, py)]
                        desv = math.hypot(tx - px, ty - py)
                        pts.append([x + px, y + py, zc0 - max(6 * desv, 0.05)])
                        pts.append([x + tx, y + ty, zc0])
                        pts.append([x + tx, y + ty, zc1])
                    else:                                 # sin pareja arriba: sigue derecha y se desarrolla (C.12.2)
                        pts.append([x + px, y + py, zc1])
                    gancho = '90° en el dado' if k == 1 else None
                else:                                     # último piso: gancho de 90° hacia adentro bajo la cubierta, por
                    # debajo de las barras superiores de las vigas en x y en y (recubrimiento, estribo N.º 3 y dos capas N.º 8);
                    # los ganchos de las caras x, de las caras y y de las esquinas van a tres alturas para no cruzarse
                    nivel_g = 2 if (nx and ny) else (1 if ny else 0)
                    zt = z1 - 0.04 - db_de(3) - 2 * S8 - db / 2 - 0.003 - nivel_g * (db + 0.002)
                    pts.append([x + px, y + py, zt])
                    gx, gy = (-nx, -ny) if (nx or ny) else (1, 0)
                    L = math.hypot(gx, gy)
                    pts.append([x + px + gx / L * (cola_90(num) + R), y + py + gy / L * (cola_90(num) + R), zt])
                    gancho = ('90° en el dado y ' if k == 1 else '') + '90° bajo la cubierta'
                forma = doblar(pts, R)
                rel_ = tuple(round(q[k_] - (pts[0][k_] if k_ < 2 else 0.0), 4) for q in pts for k_ in range(3))
                clave = (nx, ny, rel_)
                g = grupos.setdefault(clave, {'forma': forma, 'origen': (pts[0][0], pts[0][1]), 'copias': [], 'gancho': gancho})
                g['copias'].append([pts[0][0] - g['origen'][0], pts[0][1] - g['origen'][1], 0.0])
            et = f'{n} N.º {num} ({nf} por cara)'
            for clave in sorted(grupos):
                g = grupos[clave]
                J.agregar(host, 'longitudinal', num, g['forma'], g['copias'], et,
                          zona='traslapo en la mitad central' if lap else 'hasta la cubierta', ganchos=g['gancho'],
                          nivel=f'P{k}', grupo=linea)
            # ---- estribos y ganchos suplementarios
            h_ent = z1 - z0
            h_viga = e['nudo']['alto_m']
            zs, conteo = zs_estribos_columna(z0, h_ent, h_viga, e['lo_m'], e['s_lo_m'], e['s_centro_m'],
                                             e['confinada_toda_la_altura'])
            capas = list((capas_nudo or {}).get((linea, k), []))
            if not lap:                                   # ganchos de las barras bajo la cubierta (tres alturas)
                for ng in range(3):
                    capas.append((z1 - 0.04 - db_de(3) - 2 * S8 - db / 2 - 0.003 - ng * (db + 0.002), db))
            if capas:
                # los estribos del nudo se corren fuera de las capas de las vigas; si eso abre un paso mayor que s_lo, se
                # agrega un estribo al nudo
                ln_ = h_ent - h_viga
                nudo = [z for z in zs if z > z0 + ln_ - 1e-9]
                resto = [z for z in zs if z <= z0 + ln_ - 1e-9]
                opciones = []
                for extra in range(5):
                    n_n = len(nudo) + extra
                    fallas = []
                    cand = _evitar_capas([z0 + ln_ + (i + 0.5) * h_viga / n_n for i in range(n_n)], z0 + ln_ + 0.02, z1 - 0.06,
                                         capas, db_de(num_e), fallas)
                    pm = paso_max([max(resto)] + cand)
                    opciones.append((len(fallas) > 0, pm > e['s_lo_m'] + 1e-6, extra, cand))
                    if not fallas and pm <= e['s_lo_m'] + 1e-6:
                        break
                # la primera opción sin estribos encima de las barras de las vigas y con paso ≤ s_lo; si no hay, la de menos faltas
                cand = min(opciones, key=lambda q: (q[0], q[1], q[2]))[3]
                conteo['nudo'] = len(cand)
                zs = sorted(resto + cand)
            hh = b / 2 - rec - de / 2
            et_e = (f'E N.º {num_e} de {e["ramas_por_direccion"]} ramas c/{_es(e["s_lo_m"], 3)} en lo = {_es(e["lo_m"])} m '
                    f'y c/{_es(e["s_centro_m"], 3)} en el centro')
            zona_e = (f'lo abajo {conteo["lo_abajo"]}, centro {conteo["centro"]}, lo arriba {conteo["lo_arriba"]}, '
                      f'nudo {conteo["nudo"]}')
            ng = e['ganchos_suplementarios_por_direccion']
            tramos_z = [(zs, barras, cc, nf, ng, num, None)]
            if cambio:
                # desde el traslapo los amarres abrazan el armado de arriba (las barras de abajo quedan a su lado)
                z_a = [z for z in zs if z < cambio['z']]
                z_b = [z for z in zs if z >= cambio['z']]
                tramos_z = ([(z_a, barras, cc, nf, ng, num, None)] if z_a else []) + \
                    ([(z_b, cambio['barras'], cambio['cc'], cambio['nf'], cambio['ng'], cambio['num'],
                       'desde el traslapo, con el armado del piso de arriba')] if z_b else [])
            for zz, bb, cc_, nf_, ng_, num_, nota_ in tramos_z:
                for rol_, forma in _amarres_columna(x, y, zz[0], b, rec, bb, cc_, nf_, ng_, num_, num_e):
                    cop = [[0, 0, z - zz[0]] for z in zz]
                    if rol_ == 'estribo':
                        J.agregar(host, 'estribo', num_e, forma, cop, et_e, zona=zona_e, ganchos='135°', nivel=f'P{k}',
                                  grupo=linea, nota=nota_)
                    else:
                        J.agregar(host, rol_, num_e, forma, cop, f'gancho suplementario N.º {num_e} en {rol_[-1]}',
                                  ganchos='135° en los dos extremos', nivel=f'P{k}', grupo=linea, nota=nota_)
            ln_ = h_ent - h_viga
            lo_z = [z for z in zs if z <= z0 + e['lo_m'] + 1e-9 or z0 + ln_ - e['lo_m'] - 1e-9 <= z <= z0 + ln_ + 1e-9]
            resumen[host] = {'juegos_estribos': len(zs), 'juegos_A': e['juegos'], 'paso_max_m': r(paso_max(zs), 4),
                             'paso_max_lo_m': r(max(paso_max([z for z in lo_z if z <= z0 + e['lo_m'] + 1e-9]),
                                                    paso_max([z for z in lo_z if z > z0 + e['lo_m'] + 1e-9])), 4),
                             's_lo_m': e['s_lo_m'], 's_centro_m': e['s_lo_m'] if e['confinada_toda_la_altura'] else e['s_centro_m']}
            # ---- arranque (entre la cara superior del dado y el piso 1): estribos a s_lo
            if k == 1:
                za, zb_ = base['z_tope'], z0
                n_a = n_estribos(zb_ - za, e['s_lo_m'])
                if n_a:
                    zsa = [za + 0.05 + j * e['s_lo_m'] for j in range(n_a)]
                    forma = estribo_cerrado([x, y, zsa[0]], [1, 0, 0], [0, 1, 0], hh, hh, num_e, [0, 0, -1], db_esq=db)
                    J.agregar(base['host_arranque'], 'estribo', num_e, forma, [[0, 0, z - zsa[0]] for z in zsa],
                              f'E N.º {num_e} c/{_es(e["s_lo_m"], 3)} en el arranque', ganchos='135°', nivel='CIM',
                              nota='el arranque no está en el despiece de A; se confina como la zona lo (criterio del modelo)', grupo=linea)
    return resumen


def _es(v, n=2):
    s = f'{v:.{n}f}'.rstrip('0').rstrip('.') if n > 2 else f'{v:.{n}f}'
    return s.replace('.', ',')


# ========================================================================================================== vigas
def _filas(n, num, b, rec, num_e):
    """Reparto de A (filas_barras): por_fila = max(2, ⌊(b − 2·rec − 2·de + s)/(db + s)⌋), s = max(25,3 mm, db)."""
    db, de = db_de(num), db_de(num_e)
    s = max(max(0.025, 4 / 3 * 0.019), db)
    por_fila = max(2, int((b - 2 * rec - 2 * de + s) / (db + s)))
    filas, resto, d = [], n, rec + de + db / 2
    while resto > 0:
        k = min(resto, por_fila)
        filas.append((k, d))
        resto -= k
        d += db + max(0.025, db)
    return filas


def _laterales(k, b, rec, num, num_e):
    db, de = db_de(num), db_de(num_e)
    c = b / 2 - rec - de - db / 2
    if k == 1:
        return [0.0]
    return [-c + 2 * c * i / (k - 1) for i in range(k)]


TRASLAPOS = {}          # (pórtico, nivel) → [(s0, s1, capa)]: zonas de traslapo de las corridas
VERIF_VIGAS = {}        # viga → conteo y pasos de sus estribos (verificación)
LATERALES = {}          # (id de viga, capa) → posiciones laterales de la primera fila de corridas


def vigas(J, est, columnas_por_nodo, info_vigas):
    """info_vigas[id] = {'s_i', 's_j' (coordenada a lo largo del eje de las caras), 'eje': 'x'|'y', 'c': coordenada de
    la línea, 'z', 'ext_i', 'ext_j', 'col_i', 'col_j' (lado de la columna en el nudo, o None), 'db_col_i'...}."""
    ref = est['refuerzo']
    rec = ref['convenciones']['recubrimientos_m']['viga']
    TRASLAPOS.clear()
    LATERALES.clear()
    VERIF_VIGAS.clear()
    lineas = {}
    for v in ref['vigas']:
        lineas.setdefault((v['portico'], v['nivel']), []).append(v)
    for clave in sorted(lineas):
        vs = sorted(lineas[clave], key=lambda v: info_vigas[v['id']]['s_i'])
        for capa in ('superior', 'inferior'):
            _corridas_linea(J, vs, capa, rec, info_vigas)
        for v in vs:
            _estribos_viga(J, v, rec, info_vigas[v['id']])
    return dict(VERIF_VIGAS)


def _corridas_linea(J, vs, capa, rec, info):
    """Corridas superiores o inferiores de una línea de vigas de un nivel: tramos con el mismo armado son continuos."""
    runs = []
    for v in vs:
        cor = v[capa]['corridas']
        key = (cor['n'], cor['num'], v['b'], v['h'])
        if runs and runs[-1]['key'] == key and abs(info[runs[-1]['vigas'][-1]['id']]['nodo_j'] - info[v['id']]['nodo_i']) < 1e-6:
            runs[-1]['vigas'].append(v)
        else:
            runs.append({'key': key, 'vigas': [v]})
    for run in runs:
        n, num, b, h = run['key']
        v0, v1 = run['vigas'][0], run['vigas'][-1]
        i0, i1 = info[v0['id']], info[v1['id']]
        eje, c, z = i0['eje'], i0['c'], i0['z']
        db, num_e = db_de(num), max(w['estribos']['num'] for w in run['vigas'])   # el estribo más grueso de la corrida
        de = db_de(num_e)
        R = radio_doblez(num)
        # extremos: nudo exterior → hasta la cara lejana menos recubrimiento, estribo y barra de la columna, con gancho;
        # nudo interior (cambia el armado o termina la línea en un muro) → eje del nudo (como A)
        if i0['ext_i']:
            s_a = i0['nodo_i'] - i0['medio_col_i'] + rec + de + i0['db_col_i'] + db / 2 + 0.005
        else:
            s_a = i0['nodo_i']
        if i1['ext_j']:
            s_b = i1['nodo_j'] + i1['medio_col_j'] - rec - de - i1['db_col_j'] - db / 2 - 0.005
        else:
            s_b = i1['nodo_j']
        if v0.get('tipo'):                       # viga banda columna-muro: anclajes rectos más gancho (A: ldh + gancho)
            s_a = i0['s_i'] - ldh_sismico(num)
            s_b = i1['s_j'] + ldh_sismico(num)
        filas = _filas(n, num, b, rec, num_e)
        c_lat = b / 2 - rec - de - db / 2
        c_esq = esquina_en_doblez(c_lat, b / 2 - rec - de / 2, num, num_e)
        filas = [(kk, dd + (c_lat - c_esq) if fi == 0 else dd) for fi, (kk, dd) in enumerate(filas)]
        bajar = S8 if eje == 'y' else 0.0       # capas de las vigas en y: por debajo (o encima) de las de x en los nudos
        if capa == 'inferior':
            # los ganchos de abajo van por dentro de los de arriba para que sus colas no coincidan
            db_sup = db_de(v0['superior']['corridas']['num'])
            if i0['ext_i'] and not v0.get('tipo'):
                s_a += (db_sup + db) / 2 + 0.005
            if i1['ext_j'] and not v1.get('tipo'):
                s_b -= (db_sup + db) / 2 + 0.005
        L = s_b - s_a
        lap = traslapo(num, capa == 'superior')
        n_lap = max(int(math.ceil(L / 12.0 - 1e-9)) - 1, 0)
        centros = []
        arriba_ = [((a_ + b_) / 2) for a_, b_, cp in TRASLAPOS.get((v0['portico'], v0['nivel']), []) if cp == 'superior']
        for q in range(n_lap):
            objetivo = s_a + L * (q + 1) / (n_lap + 1)
            candidatas = run['vigas']
            if capa == 'inferior':
                libres = [w for w in run['vigas'] if not any(info[w['id']]['s_i'] <= c_ <= info[w['id']]['s_j'] for c_ in arriba_)]
                candidatas = libres or run['vigas']
            vv = min(candidatas, key=lambda w: abs((info[w['id']]['s_i'] + info[w['id']]['s_j']) / 2 - objetivo))
            iv = info[vv['id']]
            if capa == 'superior':
                cen = (iv['s_i'] + iv['s_j']) / 2
            else:
                cen = iv['s_i'] + 2 * vv['h'] + lap / 2 + 0.05
                if cen + lap / 2 > iv['s_j'] - 2 * vv['h']:
                    cen = (iv['s_i'] + iv['s_j']) / 2
            if centros and abs(cen - centros[-1]) < lap:
                continue
            centros.append(cen)
        cortes = [s_a] + centros + [s_b]
        for cen in centros:
            TRASLAPOS.setdefault((v0['portico'], v0['nivel']), []).append((cen - lap / 2 - 6 * db - 0.05, cen + lap / 2 + 0.05, capa))
        signo_g = -1 if capa == 'superior' else 1
        hosts = [w['id'] for w in run['vigas']]
        # barras de las columnas que atraviesan los nudos de la corrida: las intermedias pasan entre ellas
        prohib = []
        for w in run['vigas']:
            for lado in ('i', 'j'):
                for (bx, by, dbc) in info[w['id']].get(f'barras_col_{lado}', []):
                    tt = (by if eje == 'x' else bx) - c
                    if abs(tt) < b / 2:
                        prohib.append((tt - (db + dbc) / 2 - 0.002, tt + (db + dbc) / 2 + 0.002))
        # colas de los ganchos de los estribos de la corrida (arriba o abajo, según la zona) en el corte transversal
        secciones = []
        for w in run['vigas']:
            ne_w = w['estribos']['num']
            de_w = db_de(ne_w)
            hx_w, hy_w = w['b'] / 2 - rec - de_w / 2, w['h'] / 2 - rec - de_w / 2 - (S8 if eje == 'y' else 0.0)
            for eb_ in ([0, 1, 0], [0, -1, 0]):
                f2 = estribo_cerrado([0, 0, 0], [1, 0, 0], eb_, hx_w, hy_w, ne_w, [0, 0, 1],
                                     db_esq=db_de(w['superior']['corridas']['num']))
                secciones.append(([(q[0], q[1]) for q in f2], de_w))
        for fila_i, (k, d) in enumerate(filas):
            zb = (z - d - bajar) if capa == 'superior' else (z - h + d + bajar)
            lats = _laterales(k, b, rec, num, num_e)
            zr = zb - (z - h / 2)
            prohib_e = []
            for f2, de_w in secciones:
                r12 = (db + de_w) / 2 - 0.0005
                segs = list(zip(f2, f2[1:]))
                malo = None
                for q in range(-int(b * 500), int(b * 500) + 1):
                    t_ = q / 1000
                    cerca = any(_d_punto_seg2((t_, zr), a_, b2) < r12 for a_, b2 in segs)
                    if cerca and malo is None:
                        malo = t_
                    elif not cerca and malo is not None:
                        prohib_e.append((malo - 0.0005, t_ - 0.0005))
                        malo = None
                if malo is not None:
                    prohib_e.append((malo - 0.0005, b / 2))
            if fila_i == 0 and len(lats) > 1:
                lats = [-c_esq + 2 * c_esq * q / (len(lats) - 1) for q in range(len(lats))]
            if len(lats) > 2 and (prohib or prohib_e):
                s_min = db + max(db, 0.0254)
                lats = [lats[0]] + _colocar_1d(lats[1:-1], prohib + prohib_e, s_min, lats[0] + s_min, lats[-1] - s_min) + [lats[-1]]
            if fila_i == 0:
                for w in run['vigas']:
                    LATERALES[(w['id'], capa)] = list(lats)
            for t in range(len(cortes) - 1):
                sa = cortes[t] - (lap / 2 if t > 0 else 0.0)
                sb = cortes[t + 1] + (lap / 2 if t < len(cortes) - 2 else 0.0)
                grupos = {}
                for lat in lats:
                    sg = -1 if lat > 1e-9 else 1
                    pts = []
                    if t == 0 and i0['ext_i'] and not v0.get('tipo'):
                        pts.append(_p(eje, c, sa, lat, zb + signo_g * (cola_90(num) + R)))
                    elif t == 0 and v0.get('tipo'):
                        pts.append(_p(eje, c, sa, lat, zb + signo_g * (cola_90(num) + R)))
                    pts.append(_p(eje, c, sa, lat, zb))
                    if t < len(cortes) - 2:                 # traslapo al final de este tramo: doblez hacia adentro
                        s0 = cortes[t + 1] - lap / 2
                        pts.append(_p(eje, c, s0 - 6 * db, lat, zb))
                        pts.append(_p(eje, c, s0, lat + sg * db, zb))
                        pts.append(_p(eje, c, sb, lat + sg * db, zb))
                    else:
                        pts.append(_p(eje, c, sb, lat, zb))
                        if (i1['ext_j'] and not v1.get('tipo')) or v1.get('tipo'):
                            pts.append(_p(eje, c, sb, lat, zb + signo_g * (cola_90(num) + R)))
                    forma = doblar(pts, R)
                    g = grupos.setdefault(sg, {'forma': forma, 'lat0': lat, 'copias': []})
                    dl = lat - g['lat0']
                    g['copias'].append([dl, 0.0, 0.0] if eje == 'y' else [0.0, dl, 0.0])
                host = _host_en(run['vigas'], info, (sa + sb) / 2)
                gan = []
                if t == 0 and (i0['ext_i'] or v0.get('tipo')):
                    gan.append('90° en el nudo inicial')
                if t == len(cortes) - 2 and (i1['ext_j'] or v1.get('tipo')):
                    gan.append('90° en el nudo final')
                for sg in sorted(grupos):
                    g = grupos[sg]
                    J.agregar(host, f'{capa}_corrida', num, g['forma'], g['copias'],
                              f'{"sup." if capa == "superior" else "inf."} {n} N.º {num}' + (f' (fila {fila_i + 1})' if len(filas) > 1 else ''),
                              zona=('continua por ' + ', '.join(hosts)) if len(hosts) > 1 else None,
                              ganchos=' y '.join(gan) or None, nivel=None, grupo=f'{v0["portico"]}@{v0["nivel"]}')


def _host_en(vigas_run, info, s):
    for w in vigas_run:
        iw = info[w['id']]
        if iw['nodo_i'] - 1e-6 <= s <= iw['nodo_j'] + 1e-6:
            return w['id']
    return vigas_run[0]['id']


def _p(eje, c, s, lat, z):
    return [s, c + lat, z] if eje == 'x' else [c + lat, s, z]


def _estribos_viga(J, v, rec, iv):
    e = v['estribos']
    num_e = e['num']
    de = db_de(num_e)
    b, h = v['b'], v['h']
    eje, c, z = iv['eje'], iv['c'], iv['z']
    sa, sb = iv['s_i'], iv['s_j']
    Lf = sb - sa
    zona = e['zona_m']
    s2, sc = e['s_2h_m'], e['s_centro_m']
    n_hz = n_estribos(zona, s2) if not v.get('tipo') else n_estribos(Lf, s2)
    abajo = [sa + 0.05 + i * s2 for i in range(n_hz)]
    pos = list(abajo)
    if not v.get('tipo'):
        arriba = [sb - 0.05 - i * s2 for i in range(n_hz)]
        if min(arriba) - max(abajo) < s2 - 1e-9:                # zonas 2h que se tocan: toda la luz a s_2h
            n_ = int(math.ceil((Lf - 0.10) / s2 - 1e-9))
            pos = [sa + 0.05 + (Lf - 0.10) * i / max(n_, 1) for i in range(n_ + 1)]
        else:
            # el centro se reparte entre el último estribo de la zona 2h de un extremo y el primero del otro: así el paso
            # no pasa de s_centro (≤ d/2, C.21.3.4) ni en la transición
            pos += arriba + _reparto_centro(max(abajo), min(arriba), sc)
    pos = sorted(pos)
    VERIF_VIGAS[v['id']] = {'juegos_estribos': len(pos), 'juegos_A': e['juegos'], 'paso_max_m': r(paso_max(pos + [sa, sb]), 4),
                            'paso_max_2h_m': r(max(paso_max([q for q in pos if q <= sa + zona + 1e-9]),
                                                   paso_max([q for q in pos if q >= sb - zona - 1e-9])), 4),
                            's_2h_m': s2, 's_centro_m': sc if not v.get('tipo') else s2}
    hx, hy = b / 2 - rec - de / 2, h / 2 - rec - de / 2
    if eje == 'y':
        hy -= S8                       # las barras de las vigas en y van una capa N.º 8 por dentro (cruce en los nudos)
    ea = [0, 1, 0] if eje == 'x' else [1, 0, 0]
    eax = [1, 0, 0] if eje == 'x' else [0, 1, 0]
    o = _p(eje, c, pos[0], 0.0, z - h / 2)
    # los ganchos van arriba; donde se traslapan las barras de arriba, abajo (el traslapo ocupa la esquina del gancho)
    zonas = TRASLAPOS.get((v['portico'], v['nivel']), [])
    abajo = [q for q in pos if any(a <= q <= b and cp == 'superior' for a, b, cp in zonas)]
    arriba = [q for q in pos if q not in abajo]
    for lista, eb, txt in ((arriba, [0, 0, 1], 'arriba'), (abajo, [0, 0, -1], 'abajo')):
        if not lista:
            continue
        o = _p(eje, c, lista[0], 0.0, z - h / 2)
        forma = estribo_cerrado(o, ea, eb, hx, hy, num_e, eax, db_esq=db_de(v['superior']['corridas']['num']))
        cop = [[p - lista[0], 0, 0] if eje == 'x' else [0, p - lista[0], 0] for p in lista]
        J.agregar(v['id'], 'estribo', num_e, forma, cop,
                  f'E N.º {num_e} c/{_es(s2, 3)} en 2h = {_es(zona)} m y c/{_es(sc, 3)} en el centro' if not v.get('tipo')
                  else f'E N.º {num_e} de {e["ramas"]} ramas c/{_es(s2, 3)} en toda la luz',
                  zona=f'{len(lista)} de {len(pos)} estribos (A: {e["juegos"]}); ganchos {txt}', ganchos='135°',
                  grupo=f'{v["portico"]}@{v["nivel"]}')
    cop = [[p - pos[0], 0, 0] if eje == 'x' else [0, p - pos[0], 0] for p in pos]
    extra = e['ramas'] - 2
    if extra > 0:
        dbs = db_de(v['superior']['corridas']['num'])
        lats = LATERALES.get((v['id'], 'superior')) or _laterales(v['superior']['corridas']['n'], b, rec,
                                                                  v['superior']['corridas']['num'], num_e)
        inter = lats[1:-1] or [0.0]
        for lat in _elegir(inter, extra):
            rho = (dbs + de) / 2 + 0.0005
            b0_ = _p(eje, c, pos[0] + de, lat, z - h / 2 - hy + (de + dbs) / 2)
            b1_ = _p(eje, c, pos[0] + de, lat, z - h / 2 + hy - (de + dbs) / 2)
            forma = gancho_envolvente(b0_, b1_, [-q for q in ea] if lat > 0 else ea, rho, num_e)
            J.agregar(v['id'], 'gancho_suplementario', num_e, forma, cop, f'rama adicional N.º {num_e}',
                      ganchos='135° en los dos extremos', grupo=f'{v["portico"]}@{v["nivel"]}')


# ========================================================================================================== losas
def _recortar_x(xa, xb, y, obst, rec=0.04):
    """Tramo [xa, xb] de una barra en x a la altura y, cortado en las caras de los obstáculos que cruza (columnas y
    muros del piso), con el recubrimiento: se queda el tramo más largo."""
    tramos = [(xa, xb)]
    for (x0, y0, x1, y1) in obst:
        if not (y0 - 0.005 <= y <= y1 + 0.005):
            continue
        nuevo = []
        for a, b in tramos:
            if x1 <= a or x0 >= b:
                nuevo.append((a, b))
                continue
            if x0 - rec > a:
                nuevo.append((a, x0 - rec))
            if x1 + rec < b:
                nuevo.append((x1 + rec, b))
        tramos = nuevo
    return max(tramos, key=lambda q: q[1] - q[0]) if tramos else None


def losas(J, est, apoyos_x, obst_por_nivel=None):
    """apoyos_x(x, y0, y1, nivel) → semiancho del apoyo (viga en y o muro) en la línea x, o 0 si no hay."""
    ref = est['refuerzo']
    rec = ref['convenciones']['recubrimientos_m']['vigueta']
    for p in ref['losas']:
        host = p['id']
        x0, x1, y0, y1, z = p['x0'], p['x1'], p['y0'], p['y1'], p['z']
        nv = p['nervios']
        n_n = nv['n']
        hb0, hb1 = apoyos_x(x0, y0, y1, p['nivel']), apoyos_x(x1, y0, y1, p['nivel'])
        cara0, cara1 = x0 + hb0, x1 - hb1
        ln = cara1 - cara0
        ys = [y0 + (y1 - y0) * (i + 0.5) / n_n for i in range(n_n)]
        h, bw, tl = nv['h_m'], nv['b_m'], nv['loseta_m']
        # malla de la loseta (Ø 5 mm c/0,20 en las dos direcciones), arriba con 20 mm de recubrimiento
        zmx = z - rec - 0.0025
        zmy = z - rec - 0.005 - 0.0025
        nx_ = int((y1 - y0) / 0.20)
        ny_ = int((x1 - x0) / 0.20)
        obst_m = (obst_por_nivel or {}).get(p['nivel'], [])
        # la malla se corta en las columnas y los muros (no pasa por dentro de ellos: cruzaría sus estribos)
        for eje_m, n_m, zm in (('x', nx_, zmx), ('y', ny_, zmy)):
            grupos_m = {}
            for i in range(n_m):
                fijo = (y0 + 0.1 + 0.2 * i) if eje_m == 'x' else (x0 + 0.1 + 0.2 * i)
                a_, b_ = (x0, x1) if eje_m == 'x' else (y0, y1)
                for t_ in _tramos_libres(0 if eje_m == 'x' else 1, a_, b_, fijo, obst_m, 0.02):
                    grupos_m.setdefault((r(t_[0], 4), r(t_[1], 4)), []).append(fijo)
            for (a_, b_), fs in sorted(grupos_m.items()):
                forma = ([[a_, fs[0], zm], [b_, fs[0], zm]] if eje_m == 'x' else [[fs[0], a_, zm], [fs[0], b_, zm]])
                J.agregar(host, f'malla_{eje_m}', None, forma,
                          [[0, f - fs[0], 0] if eje_m == 'x' else [f - fs[0], 0, 0] for f in fs], f'malla Ø 5 mm c/0,20 ({eje_m})',
                          diam_mm=5.0, kg_m=MALLA[5.0][1])
        # estribos de los nervios (cerca de los apoyos), debajo de la malla
        num_e = 3
        de = db_de(num_e)
        z_tope_e = z - rec - 0.010                       # bajo las dos capas de la malla
        z_fondo_e = z - h + rec
        hx_e = bw / 2 - rec - de / 2
        hy_e = (z_tope_e - z_fondo_e - de) / 2
        zc_e = (z_tope_e + z_fondo_e) / 2
        e = p.get('estribos')
        if e:
            pos = [cara0 + 0.05 + i * e['s'] for i in range(n_estribos(e['zona_m'], e['s']))]
            pos += [cara1 - 0.05 - i * e['s'] for i in range(n_estribos(e['zona_m'], e['s']))]
            obst_ = (obst_por_nivel or {}).get(p['nivel'], [])
            # ganchos de 135° hacia el núcleo del nervio (un gancho de 90° de 12·db quedaría acostado en la loseta de 5 cm)
            forma = estribo_cerrado([pos[0], ys[0], zc_e], [0, 1, 0], [0, 0, 1], hx_e, hy_e, num_e, [1, 0, 0], gancho=135,
                                    db_esq=db_de(p['superior_por_nervio']['num']))
            # no en los nervios que una columna o un muro interrumpe en ese punto (el nervio no existe ahí)
            cop = [[px - pos[0], yy - ys[0], 0] for yy in ys for px in sorted(pos)
                   if not any(x0_ - bw / 2 - 0.02 <= px <= x1_ + bw / 2 + 0.02 and y0_ - bw / 2 <= yy <= y1_ + bw / 2
                              for (x0_, y0_, x1_, y1_) in obst_)]
            J.agregar(host, 'estribo_nervio', num_e, forma, cop, f'E N.º 3 c/{_es(e["s"], 3)} en los nervios cerca de los apoyos',
                      ganchos='135°')
        # inferiores de los nervios: largo de A (luz entre ejes + 0,30), centradas en el paño
        inf = p['inferior_por_nervio']
        num_i, n_i = inf['num'], inf['n']
        dbi = db_de(num_i)
        zi = z - h + rec + (de if e else 0.0) + dbi / 2
        li = inf['largo_m']
        xa, xb = (x0 + x1) / 2 - li / 2, (x0 + x1) / 2 + li / 2
        lats = _laterales(n_i, bw, rec, num_i, num_e) if n_i > 1 else [0.0]
        obst = (obst_por_nivel or {}).get(p['nivel'], [])
        # nervios cuyas barras chocan con una columna o un muro: barra recortada en la cara (juego aparte)
        grupos_i = {}
        for yy in ys:
            for lat in lats:
                t_ = _recortar_x(xa, xb, yy + lat, obst)
                if t_:
                    grupos_i.setdefault((r(t_[0], 4), r(t_[1], 4)), []).append(yy + lat)
        for (a_, b_), yl in sorted(grupos_i.items()):
            J.agregar(host, 'inferior_nervio', num_i, [[a_, yl[0], zi], [b_, yl[0], zi]], [[0, q - yl[0], 0] for q in yl],
                      f'inf. {n_i} N.º {num_i} por nervio')
        # superiores de los nervios en los apoyos: ln/3 desde la cara y 0,25 m dentro del apoyo
        sup = p['superior_por_nervio']
        num_s, n_s = sup['num'], sup['n']
        dbs = db_de(num_s)
        zs_ = z_tope_e - (de if e else 0.0) - dbs / 2
        L3 = sup['largo_desde_cara_m']
        lats = _laterales(n_s, bw, rec, num_s, num_e) if n_s > 1 else [0.0]
        for lado, xa_, xb_ in (('i', cara0 - 0.25, cara0 + L3), ('j', cara1 - L3, cara1 + 0.25)):
            grupos_s = {}
            for yy in ys:
                for lat in lats:
                    t_ = _recortar_x(xa_, xb_, yy + lat, obst)
                    if t_ and t_[1] - t_[0] > 0.3:
                        grupos_s.setdefault((r(t_[0], 4), r(t_[1], 4)), []).append(yy + lat)
            for (a_, b_), yl in sorted(grupos_s.items()):
                J.agregar(host, f'superior_nervio_{lado}', num_s, [[a_, yl[0], zs_], [b_, yl[0], zs_]],
                          [[0, q - yl[0], 0] for q in yl], f'sup. {n_s} N.º {num_s} por nervio en el apoyo {lado}')
        # riostra a la mitad de la luz: 1 N.º 4 arriba y 1 abajo entre las caras de las vigas del paño (y)
        xr = (x0 + x1) / 2
        ya_r, yb_r = p.get('_y_caras', (y0, y1))
        J.agregar(host, 'riostra', 4, [[xr, ya_r + 0.03, zi + 0.02], [xr, yb_r - 0.03, zi + 0.02]],
                  [[0, 0, 0], [0, 0, zs_ - zi - 0.04]], 'riostra: 1 N.º 4 arriba y 1 abajo')


# ========================================================================================================== muros
def muros(J, est, bases_muro):
    VERIF_CORTINAS.clear()
    ref = est['refuerzo']
    rec = ref['convenciones']['recubrimientos_m']['muro']
    por_muro = {}
    for m in ref['muros']:
        por_muro.setdefault(m['muro'], []).append(m)
    for mid in sorted(por_muro):
        pisos = sorted(por_muro[mid], key=lambda m: m['nivel'])
        prev_fila, prev_s = None, None                       # última fila horizontal del piso de abajo (el paso sigue)
        for idx, m in enumerate(pisos):
            host = m['id']
            k = m['nivel']
            z0, z1 = m['z0'], m['z1']
            t = m['t']
            alma = m['_alma']                 # (u0, u1, c): extremos del alma y coordenada de la línea (de generar_bim)
            eje = m['direccion']
            u0, u1, c = alma
            # ---- bordes
            lb = {}
            for bo in m['bordes']:
                if bo.get('columna_de_borde'):
                    lb[bo['lado']] = 0.0
                    continue
                lb[bo['lado']] = bo['lb_m']
                num, n = bo['num'], bo['n']
                db = db_de(num)
                e = bo['estribos']
                de = db_de(e['num'])
                c0 = rec + de + db / 2
                off = t / 2 - c0
                us = [(u0 + q) if bo['lado'] == 'i' else (u1 - q) for q in bo['parejas_desde_el_extremo_m']]
                zb = bases_muro[mid]['z_parrilla'] + db / 2 if k == 1 else z0
                arriba = idx + 1 < len(pisos)
                if arriba:
                    zt = z1                                    # acoplador mecánico en la base del piso de arriba
                    pts = [[0, 0, zb], [0, 0, zt]]
                    gan = 'acoplador mecánico arriba'
                else:
                    zt = z1 - 0.04 - de - db / 2
                    sgn = 1 if bo['lado'] == 'i' else -1
                    pts = [[0, 0, zb], [0, 0, zt], [sgn * (cola_90(num) + radio_doblez(num)), 0, zt]]
                    gan = 'gancho de 90° en la cubierta'
                if k == 1:
                    sgn = -1 if bo['lado'] == 'i' else 1
                    pts = [[sgn * (cola_90(num) + radio_doblez(num)), 0, zb]] + pts
                    gan = 'gancho de 90° en la losa de pilotes; ' + gan
                cop = []
                ref_u = us[0]
                # las parejas de los extremos de la zona van en los dobleces del estribo especial (se corren hacia adentro)
                hh_t = t / 2 - rec - de / 2
                corr = off - esquina_en_doblez(off, hh_t, num, e['num'])
                sg_u = 1 if bo['lado'] == 'i' else -1
                for qi, uu in enumerate(us):
                    du = (sg_u * corr if qi == 0 else -sg_u * corr if qi == len(us) - 1 else 0.0) if len(us) > 1 else 0.0
                    for s in (-1, 1):
                        dt = -s * corr if qi in (0, len(us) - 1) else 0.0
                        cop.append(_mu(eje, uu - ref_u + du, s * off + off + dt, 0.0))
                base = [_mu(eje, ref_u + p[0], c - off, p[2]) for p in pts]
                forma = doblar(base, radio_doblez(num))
                J.agregar(host, f'borde_{bo["lado"]}', num, forma, cop, f'{n} N.º {num} en el borde {bo["lado"]}',
                          zona=f'lb = {_es(bo["lb_m"])} m', ganchos=gan, nivel=f'P{k}', grupo=mid)
                # estribos especiales del borde: cerrado alrededor de la zona + ramas en el espesor; en el piso 1 siguen por el
                # arranque hasta la losa de pilotes (el elemento de borde se confina hasta su apoyo, C.21.9.6.4, por confirmar)
                hl = (bo['lb_m'] - 2 * rec - de) / 2
                ht = t / 2 - rec - de / 2
                uc = (u0 + bo['lb_m'] / 2) if bo['lado'] == 'i' else (u1 - bo['lb_m'] / 2)
                za_b = bases_muro[mid]['z_tope'] if k == 1 else z0
                zs_todos = [za_b + 0.05 + i * e['s_m'] for i in range(n_estribos(z1 - za_b, e['s_m']))]
                ea = [1, 0, 0] if eje == 'x' else [0, 1, 0]
                eb = [0, 1, 0] if eje == 'x' else [1, 0, 0]
                ramas = e['ramas_espesor'] - 2
                cands = [uu for uu in us if abs(uu - us[0]) > 1e-6 and abs(uu - us[-1]) > 1e-6] or us[1:-1]
                elegidos = _elegir(sorted(cands), ramas) if ramas > 0 else []
                for hst, zs in ((host, [zz for zz in zs_todos if zz >= z0 - 1e-9]),
                                (bases_muro[mid]['host_arranque'], [zz for zz in zs_todos if zz < z0 - 1e-9])):
                    if not zs:
                        continue
                    nota_a = None if hst == host else 'el arranque no está en el despiece de A: el confinamiento del borde sigue hasta la losa de pilotes (criterio del modelo)'
                    niv_ = f'P{k}' if hst == host else 'CIM'
                    o = _mu(eje, uc, c, zs[0])
                    forma = estribo_cerrado(o, ea, eb, hl, ht, e['num'], [0, 0, -1], db_esq=db)
                    J.agregar(hst, f'estribo_borde_{bo["lado"]}', e['num'], forma, [[0, 0, zz - zs[0]] for zz in zs],
                              f'E N.º {e["num"]} c/{_es(e["s_m"], 3)} ({e["tipo"]})', ganchos='135°', nivel=niv_, grupo=mid, nota=nota_a)
                    for qn, uu in enumerate(elegidos):
                        # rama al lado de la pareja que amarra, con la cola hacia ella; ramas vecinas a distinta altura
                        dz_r = de * (1 + qn % 2)
                        rho = (db + de) / 2 + 0.0005
                        b0_ = _mu(eje, uu, c - off, zs[0] + dz_r)
                        b1_ = _mu(eje, uu, c + off, zs[0] + dz_r)
                        forma = gancho_envolvente(b0_, b1_, [-q for q in ea] if bo['lado'] == 'i' else list(ea), rho, e['num'])
                        J.agregar(hst, f'gancho_borde_{bo["lado"]}', e['num'], forma, [[0, 0, zz - zs[0]] for zz in zs],
                                  f'rama N.º {e["num"]} en el espesor', ganchos='135° en los dos extremos', nivel=niv_, grupo=mid, nota=nota_a)
            # ---- cortinas: horizontales por dentro de las de borde; verticales por dentro de las horizontales
            cv, ch = m['cortina_vertical'], m['cortina_horizontal']
            numv, sv, numh, sh = cv['num'], cv['s_m'], ch['num'], ch['s_m']
            dbv, dbh = db_de(numv), db_de(numh)
            db_borde = max([db_de(bo['num']) for bo in m['bordes'] if not bo.get('columna_de_borde')] or [0.0])
            de_b = db_de(4)
            off_h = t / 2 - (rec + de_b + db_borde) - dbh / 2 - 0.002
            for bo in m['bordes']:                                  # por dentro de las parejas corridas a los dobleces
                if bo.get('columna_de_borde'):
                    continue
                db_, ne_ = db_de(bo['num']), bo['estribos']['num']
                de_ = db_de(ne_)
                off_b = t / 2 - (rec + de_ + db_ / 2)
                off_b -= off_b - esquina_en_doblez(off_b, t / 2 - rec - de_ / 2, bo['num'], ne_)
                off_h = min(off_h, off_b - (db_ + dbh) / 2 - 0.001)
            off_v = off_h - dbh / 2 - dbv / 2
            # horizontales: filas repartidas en toda la altura del tramo, con la losa (en el piso 1, desde la losa de pilotes,
            # por el arranque): la primera y la última a ≤ s/2 de los extremos, así el paso sigue igual a través de la losa
            za = bases_muro[mid]['z_tope'] if k == 1 else z0
            bandas = []                                             # estribos de borde y sus ramas (z − de, z, z + de, z + 2·de)
            for bo in m['bordes']:
                if bo.get('columna_de_borde'):
                    continue
                e_ = bo['estribos']
                de_ = db_de(e_['num'])
                for zz in [za + 0.05 + i * e_['s_m'] for i in range(n_estribos(z1 - za, e_['s_m']))]:
                    bandas += [(zz + q * de_, de_) for q in (-1, 0, 1, 2)]
            zh = _filas_cortina(za, z1, sh, bandas, dbh, prev=prev_fila, s_prev=prev_s, hay_arriba=idx + 1 < len(pisos))
            prev_fila, prev_s = (zh[-1] if zh else prev_fila), sh
            VERIF_CORTINAS.setdefault(mid, {'filas': [], 'verticales': {}})['filas'].extend((zz, sh) for zz in zh)
            # barras rectas de extremo a extremo del alma y, en cada extremo, una horquilla (barra en U) del mismo N.º que
            # abraza el extremo y se traslapa con las dos caras (contacto, un diámetro encima): el gancho de 90° de 12·db de
            # las dos caras no cabe en el espesor sin cruzarse (C.7.1.2 y C.21.9, criterio del modelo)
            ua, ub = u0 + rec + 0.01, u1 - rec - 0.01
            R = radio_doblez(numh)
            lap_h = traslapo(numh)
            for hst, zz_ in ((host, [zz for zz in zh if zz >= z0 - 1e-9]), (bases_muro[mid]['host_arranque'], [zz for zz in zh if zz < z0 - 1e-9])):
                if not zz_:
                    continue
                niv_ = f'P{k}' if hst == host else 'CIM'
                nota_a = None if hst == host else 'el arranque no está en el despiece de A: la cortina horizontal sigue hasta la losa de pilotes (criterio del modelo)'
                for s in (-1, 1):
                    J.agregar(hst, 'cortina_horizontal', numh, [_mu(eje, ua, c + s * off_h, zz_[0]), _mu(eje, ub, c + s * off_h, zz_[0])],
                              [[0, 0, zz - zz_[0]] for zz in zz_], f'N.º {numh} c/{_es(sh, 3)} horizontal ({"cara 1" if s < 0 else "cara 2"})',
                              ganchos='horquilla en U en cada extremo', nivel=niv_, grupo=mid, nota=nota_a)
                for lado, u_e, sg in (('i', ua, 1), ('j', ub, -1)):
                    pts = [_mu(eje, u_e + sg * lap_h, c - off_h, zz_[0] + dbh), _mu(eje, u_e, c - off_h, zz_[0] + dbh),
                           _mu(eje, u_e, c + off_h, zz_[0] + dbh), _mu(eje, u_e + sg * lap_h, c + off_h, zz_[0] + dbh)]
                    J.agregar(hst, 'cortina_horizontal_horquilla', numh, doblar(pts, R), [[0, 0, zz - zz_[0]] for zz in zz_],
                              f'horquilla N.º {numh} en el extremo {lado}', zona=f'traslapo de {_es(lap_h)} m con las dos caras',
                              ganchos='U de 180° alrededor del extremo', nivel=niv_, grupo=mid, nota=nota_a)
            # verticales: entre las zonas de borde, a paso ≤ s; traslapo en la base del piso de arriba; bajo la cubierta, rectas
            # con una horquilla en U invertida que abraza las dos caras (por la misma razón que las horizontales)
            holg = R + (dbh + dbv) / 2 + 0.005                      # fuera del doblez de las horquillas de las horizontales
            ua_v = max(u0 + lb.get('i', 0.0) + 0.05, ua + holg)
            ub_v = min(u1 - lb.get('j', 0.0) - 0.05, ub - holg)
            nv_ = int(math.ceil((ub_v - ua_v) / sv - 1e-9)) + 1
            us_v = [ua_v + (ub_v - ua_v) * i / (nv_ - 1) for i in range(nv_)] if nv_ > 1 else [(ua_v + ub_v) / 2]
            VERIF_CORTINAS[mid]['verticales'][host] = (r(max([b_ - a_ for a_, b_ in zip(us_v, us_v[1:])] or [0.0]), 4), sv)
            lapv = m['traslapo_vertical_m']
            zb = bases_muro[mid]['z_parrilla'] + dbv / 2 if k == 1 else z0
            arriba = idx + 1 < len(pisos)
            zt = z1 - 0.04 - dbv / 2
            for s in (-1, 1):
                if arriba:
                    pts = [[0, 0, zb], [0, 0, z1 + lapv]]
                    gan = None
                else:
                    pts = [[0, 0, zb], [0, 0, zt]]
                    gan = 'horquilla en U invertida bajo la cubierta'
                if k == 1:
                    pts = [[0, s * (cola_90(numv) + radio_doblez(numv)), zb]] + pts
                    gan = '90° en la losa de pilotes' + (' y ' + gan if gan else '')
                base = [_mu(eje, us_v[0], c + s * off_v + p[1], p[2]) for p in pts]
                J.agregar(host, 'cortina_vertical', numv, doblar(base, radio_doblez(numv)),
                          [_mu(eje, uu - us_v[0], 0.0, 0.0) for uu in us_v],
                          f'N.º {numv} c/{_es(sv, 3)} vertical ({"cara 1" if s < 0 else "cara 2"})',
                          zona=f'traslapo de {_es(lapv)} m en la base del piso de arriba' if arriba else None, ganchos=gan,
                          nivel=f'P{k}', grupo=mid)
            if not arriba:
                lap_v = traslapo(numv)
                du = dbv + 0.001                                    # al lado de cada vertical (traslapo de contacto)
                pts = [_mu(eje, us_v[0] + du, c - off_v, zt - lap_v), _mu(eje, us_v[0] + du, c - off_v, zt),
                       _mu(eje, us_v[0] + du, c + off_v, zt), _mu(eje, us_v[0] + du, c + off_v, zt - lap_v)]
                J.agregar(host, 'cortina_vertical_horquilla', numv, doblar(pts, radio_doblez(numv)),
                          [_mu(eje, uu - us_v[0], 0.0, 0.0) for uu in us_v], f'horquilla N.º {numv} bajo la cubierta',
                          zona=f'traslapo de {_es(lap_v)} m con las dos caras', ganchos='U de 180° invertida', nivel=f'P{k}', grupo=mid)


VERIF_CORTINAS = {}     # muro → {'filas': [(z, s)] de todas las filas horizontales, 'verticales': {piso: (paso máximo, s)}}


def _filas_cortina(za, zb, s, bandas, dbh, prev=None, s_prev=None, hay_arriba=False):
    """Filas de la cortina horizontal de un piso del muro (za a zb), a paso ≤ s y continuas con las del piso de abajo (prev:
    su última fila; entre los dos pisos el paso no pasa del mayor de los dos) y de arriba. Abajo del todo (losa de pilotes)
    y arriba del todo (cubierta), la primera y la última a ≤ s/2 (con elementos de borde, la primera va en la primera
    ventana libre sobre el primer estribo de borde, a ≈ 0,10 m). Sin elementos de borde, a paso uniforme. Con ellos, cada
    fila (y su horquilla, un diámetro encima) va en una ventana libre entre las bandas de los estribos de borde y sus ramas:
    de abajo arriba se toma la ventana más lejana que no pase de s."""
    lo = za + 0.02 if prev is None else prev + 3 * dbh + 0.002
    hi = zb - 1e-4 if hay_arriba else zb - 0.02 - dbh
    s0 = s if prev is None else max(s, s_prev or s)
    proh = []
    for zc, dc in bandas:
        h = (dc + dbh) / 2 + 0.002
        proh += [(zc - h, zc + h), (zc - h - dbh, zc + h - dbh)]
    proh.sort()
    iv = []
    for a, b in proh:
        if iv and a <= iv[-1][1]:
            iv[-1][1] = max(iv[-1][1], b)
        else:
            iv.append([a, b])
    libres, y = [], lo
    for a, b in iv:
        if b <= y:
            continue
        if a > y:
            libres.append((y, min(a, hi)))
        y = max(y, b)
        if y >= hi:
            break
    if y < hi:
        libres.append((y, hi))
    cand = []
    for f0, f1 in libres:
        L_ = f1 - f0
        if L_ < 0:
            continue
        k = max(int(math.ceil(L_ / (s / 2) - 1e-9)), 1)
        cand += [f0 + L_ * (i + 0.5) / k for i in range(k)]
    cand.sort()
    if not cand:
        return []
    ref0 = za + s / 2 if prev is None else prev + s0
    bajas = [c for c in cand if c <= ref0 + 1e-9]
    cur = bajas[-1] if bajas else cand[0]
    filas = [cur]
    while hay_arriba or zb - cur > s / 2 + 1e-9:
        sig = [c for c in cand if cur + 1e-9 < c <= cur + s + 1e-9]
        if not sig:
            mas = [c for c in cand if c > cur + 1e-9]
            if not mas:
                break
            cur = mas[0]
        else:
            cierre = [c for c in sig if zb - c <= s / 2 + 1e-9] if not hay_arriba else []
            cur = cierre[0] if cierre else sig[-1]
        filas.append(cur)
    return filas


def _mu(eje, u, c, z):
    """Punto en la línea de un muro: u a lo largo del alma y c en la otra coordenada."""
    return [u, c, z] if eje == 'x' else [c, u, z]


# ====================================================================================================== escaleras
def _tramos_libres(k, a, b, fijo, obst, rec=0.04, minimo=0.3):
    """Todos los tramos (de más de `minimo`) de [a, b] a lo largo del eje k en la coordenada fija, fuera de los obstáculos."""
    j = 1 - k
    tramos = [(a, b)]
    for q in obst:
        if not (q[j] - 0.005 <= fijo <= q[j + 2] + 0.005):
            continue
        q0, q1 = q[k], q[k + 2]
        nuevo = []
        for s0, s1 in tramos:
            if q1 <= s0 or q0 >= s1:
                nuevo.append((s0, s1))
                continue
            if q0 - rec > s0:
                nuevo.append((s0, q0 - rec))
            if q1 + rec < s1:
                nuevo.append((q1 + rec, s1))
        tramos = nuevo
    return [t for t in tramos if t[1] - t[0] > minimo]


def _tramo_en(k, a, b, fijo, obst, rec=0.04):
    """Tramo [a, b] de una barra a lo largo del eje k (0 = x, 1 = y) en la coordenada fija de la otra, cortado en las caras
    de las columnas y muros que cruza (con el recubrimiento): el más largo."""
    if k == 0:
        return _recortar_x(a, b, fijo, obst, rec)
    return _recortar_x(a, b, fijo, [(q[1], q[0], q[3], q[2]) for q in obst], rec)


def escaleras(J, est, tramos_por_esc, obst_por_nivel=None):
    """tramos_por_esc[id] = {'tramos': [{'p0': inicio del eje en planta y z, 'run': dirección (x, y), 'lat': dirección
    transversal, 'L': largo horizontal, 'H': subida, 'ancho', 'des0': largo del descanso de abajo, 'des1': del de arriba,
    'z0', 'z1', 't'}], 'descansos': [{'id', 'rect', 'zt', 't', 'corrida': 'x' | 'y'}]}. Cada descanso se arma como losa
    en dos direcciones en todo su ancho: las principales de los tramos que llegan a él siguen por su ancho, se agregan
    principales donde no llegan (entre los tramos y en los bordes) y la repartición lo cruza entero."""
    ref = est['refuerzo']
    rec = ref['convenciones']['recubrimientos_m']['escalera']
    principales = []                  # (eje lateral, posición lateral, run0, run1, z) de las barras de los tramos en los descansos
    datos = {}
    for e in ref['escaleras']:
        host = e['id']
        dd = tramos_por_esc.get(host) or {}
        tramos = dd.get('tramos') or []
        datos[host] = (e, dd.get('descansos') or [])
        num, s_ = e['principal']['num'], e['principal']['s_m']
        numt, st = e['reparticion']['num'], e['reparticion']['s_m']
        nums, ss, Ls = e['superior_apoyos']['num'], e['superior_apoyos']['s_m'], e['superior_apoyos']['largo_m']
        db = db_de(num)
        for ti, tr in enumerate(tramos):
            run, lat = tr['run'], tr['lat']
            t = tr['t']
            L, H = tr['L'], tr['H']
            nr_ = tr.get('nr', 13)
            pend = (H / nr_) / (L / (nr_ - 1))                      # contrahuella / huella
            cos = 1 / math.sqrt(1 + pend * pend)
            # eje de las barras principales: cara inferior + recubrimiento, por el descanso de abajo, el tramo y el de arriba
            zf = rec + db / 2
            p0 = tr['p0']

            def P(u, v, w):
                return [p0[0] + run[0] * u + lat[0] * w, p0[1] + run[1] * u + lat[1] * w, p0[2] + v]
            t0 = tr.get('t0', t)
            # línea inclinada de las barras: paralela a la cara inferior a zf; quiebres donde corta las líneas de las
            # barras de los descansos (abajo en u_b, arriba en u_t, antes del quiebre del concreto)
            zb = -t0 + zf + (0.03 if t0 < t else 0.0)
            zi0 = -(t - zf) / cos
            u_b = (zb - zi0) / pend
            u_t = (H - t + zf - zi0) / pend
            pts = [P(-tr['des0'] + rec, zb, 0), P(u_b, zb, 0), P(u_t, H - t + zf, 0), P(L + tr['des1'] - rec, H - t + zf, 0)]
            n_p = int(math.ceil((tr['ancho'] - 2 * rec - db) / s_ - 1e-9)) + 1          # paso ≤ s de A
            ws = [rec + db / 2 + (tr['ancho'] - 2 * rec - db) * i / (n_p - 1) for i in range(n_p)]
            base = [_add(q, [lat[0] * ws[0], lat[1] * ws[0], 0]) for q in pts]
            J.agregar(host, 'principal', num, doblar(base, radio_doblez(num)),
                      [[lat[0] * (w - ws[0]), lat[1] * (w - ws[0]), 0] for w in ws],
                      f'N.º {num} c/{_es(s_, 3)} abajo (tramo {ti + 1})', nivel=f'P{e["piso"]}')
            k_lat = 0 if abs(lat[0]) > 0.5 else 1
            k_run = 1 - k_lat
            for (ua, ub, zz) in ((-tr['des0'] + rec, 0.0, zb), (L, L + tr['des1'] - rec, H - t + zf)):
                a_, b_ = P(ua, zz, 0), P(ub, zz, 0)
                for w in ws:
                    principales.append((k_lat, P(0, 0, w)[k_lat], min(a_[k_run], b_[k_run]), max(a_[k_run], b_[k_run]), a_[2]))
            # repartición: transversales sobre las principales a lo largo del tramo; en la parte plana del arranque (antes
            # del quiebre u_b) van sobre las principales planas, dentro del concreto del descanso o del contrapiso
            dbt = db_de(numt)
            n_t = int(math.ceil(math.hypot(L - 0.10, pend * (L - 0.10)) / st - 1e-9)) + 1

            def z_rep(u):
                if u <= u_b:
                    return zb + (db + dbt) / 2
                return min(zi0 + pend * u, H - t + zf) + (db + dbt) / 2 / cos
            us_t = [0.05 + (L - 0.10) * i / max(n_t - 1, 1) for i in range(n_t)]
            zr0 = z_rep(us_t[0])
            cop = [[run[0] * (u - us_t[0]), run[1] * (u - us_t[0]), z_rep(u) - zr0] for u in us_t]
            a = P(us_t[0], zr0, rec)
            b_ = P(us_t[0], zr0, tr['ancho'] - rec)
            J.agregar(host, 'reparticion', numt, [a, b_], cop, f'N.º {numt} c/{_es(st, 3)} de repartición (tramo {ti + 1})',
                      nivel=f'P{e["piso"]}')
            # superiores en los apoyos (arranque y llegada del tramo): N.º 4 c/0,25 de 1,20 m
            dbs = db_de(nums)
            n_s = int(math.ceil((tr['ancho'] - 2 * rec - dbs) / ss - 1e-9)) + 1
            ws2 = [rec + dbs / 2 + (tr['ancho'] - 2 * rec - dbs) * i / (n_s - 1) for i in range(n_s)]
            zt = rec + dbs / 2
            zti = zt / cos                     # en la parte inclinada, el recubrimiento se mide perpendicular a las esquinas
            for lado in ('arranque', 'llegada'):  # interiores de los peldaños (línea z = pendiente·u)
                if lado == 'arranque':
                    u_q = (zti - zt) / pend
                    pts_s = [P(-Ls / 2, -zt, ws2[0]), P(u_q, -zt, ws2[0]), P(Ls / 2, Ls / 2 * pend - zti, ws2[0])]
                else:
                    ul = L - Ls / 2
                    pts_s = [P(ul, ul * pend - zti, ws2[0]), P(L - 0.03, (L - 0.03) * pend - zti, ws2[0]),
                             P(L + 0.15, H - zt, ws2[0]), P(L + Ls / 2, H - zt, ws2[0])]
                J.agregar(host, f'superior_{lado}', nums, doblar(pts_s, radio_doblez(nums)),
                          [[lat[0] * (w - ws2[0]), lat[1] * (w - ws2[0]), 0] for w in ws2],
                          f'N.º {nums} c/{_es(ss, 3)} arriba en el {lado} (tramo {ti + 1})', nivel=f'P{e["piso"]}')
    # descansos: losa en dos direcciones en todo su ancho
    for host in sorted(datos):
        e, descansos = datos[host]
        num, s_ = e['principal']['num'], e['principal']['s_m']
        numt, st = e['reparticion']['num'], e['reparticion']['s_m']
        db, dbt = db_de(num), db_de(numt)
        for d in descansos:
            x0, y0, x1, y1 = d['rect']
            zp = d['zt'] - d['t'] + rec + db / 2
            k_run = 1 if d['corrida'] == 'y' else 0
            k_lat = 1 - k_run
            l0, l1 = (x0, x1) if k_lat == 0 else (y0, y1)
            r0, r1 = (y0, y1) if k_run == 1 else (x0, x1)
            # principales de los tramos que llegan a este descanso (misma capa, dentro de su planta)
            hay = sorted({round(w, 4) for (kl, w, a_, b_, z) in principales if kl == k_lat and abs(z - zp) < 0.01
                          and a_ < r1 - 0.05 and b_ > r0 + 0.05 and l0 < w < l1})
            e0, e1 = l0 + rec + db / 2, l1 - rec - db / 2
            nuevas = []
            anclas = [(e0, False)] + [(w, True) for w in hay] + [(e1, False)]
            for (wa, ba), (wb, bb) in zip(anclas, anclas[1:]):
                g = wb - wa
                if g <= s_ + 1e-6:
                    if not ba and (not nuevas or abs(nuevas[-1] - wa) > 1e-6) and g > 0.5 * s_:
                        nuevas.append(wa)
                    continue
                n_ = int(math.ceil(g / s_ - 1e-9))
                for i in range(0 if not ba else 1, n_ + (0 if bb else 1)):
                    q = wa + g * i / n_
                    if not nuevas or abs(nuevas[-1] - q) > 1e-6:
                        nuevas.append(q)
            nuevas = [q for q in nuevas if all(abs(q - w) > db + 0.002 for w in hay)]
            def pt(w, r_, z):
                return [w, r_, z] if k_lat == 0 else [r_, w, z]
            obst = (obst_por_nivel or {}).get(e['piso'], [])
            # las barras del descanso se cortan en las caras de las columnas y muros que lo atraviesan
            grupos = {}
            for q in nuevas:
                t_ = _tramo_en(k_run, r0 + rec, r1 - rec, q, obst)
                if t_ and t_[1] - t_[0] > 0.3:
                    grupos.setdefault((r(t_[0], 4), r(t_[1], 4)), []).append(q)
            for (a_, b_), qs in sorted(grupos.items()):
                J.agregar(host, 'principal_descanso', num, [pt(qs[0], a_, zp), pt(qs[0], b_, zp)],
                          [pt(q - qs[0], 0.0, 0.0) for q in qs], f'N.º {num} c/{_es(s_, 3)} abajo en el descanso',
                          zona=f'{d["id"]}: donde no llegan las principales de los tramos', nivel=f'P{e["piso"]}')
            zr = zp + (db + dbt) / 2
            n_r = int(math.ceil((r1 - r0 - 2 * rec - dbt) / st - 1e-9)) + 1
            rs_ = [r0 + rec + dbt / 2 + (r1 - r0 - 2 * rec - dbt) * i / max(n_r - 1, 1) for i in range(n_r)]
            grupos = {}
            for q in rs_:
                t_ = _tramo_en(k_lat, l0 + rec, l1 - rec, q, obst)
                if t_ and t_[1] - t_[0] > 0.3:
                    grupos.setdefault((r(t_[0], 4), r(t_[1], 4)), []).append(q)
            for (a_, b_), qs in sorted(grupos.items()):
                J.agregar(host, 'reparticion_descanso', numt, [pt(a_, qs[0], zr), pt(b_, qs[0], zr)],
                          [pt(0.0, q - qs[0], 0.0) for q in qs], f'N.º {numt} c/{_es(st, 3)} de repartición en el descanso',
                          zona=f'{d["id"]}: en todo su ancho', nivel=f'P{e["piso"]}')


# =================================================================================================== cimentación
def pilotes(J, est, id_pilote):
    C = est['cimentacion']
    rec = C['pilotes'][0]['recubrimiento_m']
    for g in C['pilotes']:
        D = g['D_m']
        lo = g['longitudinal']
        num = lo['num']
        db = db_de(num)
        de = db_de(g['espiral']['num'])
        rc = D / 2 - rec - de - db / 2
        z_top = g['z_cabeza'] + lo['anclaje_en_dado_m']
        z_bot_sup = z_top - lo['largo_m']
        mi = lo['mitad_inferior']
        z_bot = g['z_punta'] + rec
        z_top_inf = z_bot + mi['largo_m']
        for kp, (px, py) in enumerate(g['posiciones']):
            host = id_pilote(g['grupo'], kp)
            ang = [2 * math.pi * i / lo['n'] for i in range(lo['n'])]
            p0 = [px + rc, py, z_top]
            J.agregar(host, 'longitudinal_superior', num, [p0, [px + rc, py, z_bot_sup]],
                      [[px + rc * math.cos(a) - p0[0], py + rc * math.sin(a) - p0[1], 0] for a in ang],
                      f'{lo["n"]} N.º {num} en la mitad superior', zona=f'{_es(lo["largo_m"])} m con '
                      f'{_es(lo["anclaje_en_dado_m"])} m dentro del dado', nivel='CIM-PIL')
            # inferiores al lado de las superiores (traslapo de contacto)
            sel = sorted({int(round(j * lo['n'] / mi['n'])) % lo['n'] for j in range(mi['n'])})
            dang = (db + 0.001) / rc
            angs = [ang[i] + dang for i in sel]
            q0 = [px + rc * math.cos(angs[0]), py + rc * math.sin(angs[0]), z_top_inf]
            J.agregar(host, 'longitudinal_inferior', num, [q0, [q0[0], q0[1], z_bot]],
                      [[px + rc * math.cos(a) - q0[0], py + rc * math.sin(a) - q0[1], 0] for a in angs],
                      f'{mi["n"]} N.º {num} en la mitad inferior', zona=f'traslapo de {_es(z_top_inf - z_bot_sup)} m',
                      nivel='CIM-PIL')
            es_ = g['espiral']
            rs = D / 2 - rec - de / 2
            z_esp_top = g['z_cabeza'] - 0.05
            z_c = z_esp_top - es_['zona_cabeza_m']
            param = {'tipo': 'espiral', 'centro': [r(px, 4), r(py, 4)], 'radio': r(rs, 4),
                     'tramos': [{'z0': r(z_c, 4), 'z1': r(z_esp_top, 4), 'paso': es_['s_cabeza_m']},
                                {'z0': r(z_bot, 4), 'z1': r(z_c, 4), 'paso': es_['s_resto_m']}]}
            J.agregar(host, 'espiral', es_['num'], None, [[0, 0, 0]],
                      f'espiral N.º {es_["num"]} c/{_es(es_["s_cabeza_m"], 3)} en {_es(es_["zona_cabeza_m"])} m y c/{_es(es_["s_resto_m"], 3)} abajo',
                      param=param, nivel='CIM-PIL')


def _colocar_1d(nom, prohibidos, s_min, lo, hi):
    """Posiciones de barras paralelas cerca de las nominales (ordenadas), fuera de los intervalos prohibidos (a, b), a s_min
    o más entre sí y dentro de [lo, hi]: de izquierda a derecha y, si no caben, de derecha a izquierda; si tampoco, las
    nominales (criterio del modelo para pasar entre las barras de otro elemento)."""
    if not nom:
        return []
    iv = []
    for a, b in sorted(prohibidos):
        if b < lo - 0.5 or a > hi + 0.5:
            continue
        if iv and a <= iv[-1][1]:
            iv[-1][1] = max(iv[-1][1], b)
        else:
            iv.append([a, b])
    if not iv:
        return list(nom)
    inicios = [a for a, _b in iv]

    def pasada(nom_, iv_, inicios_, lo_, hi_):
        out, prev = [], None
        for p in nom_:
            lb = lo_ if prev is None else max(lo_, prev + s_min)
            q = max(p, lb)
            i = bisect.bisect_right(inicios_, q) - 1
            if i >= 0 and iv_[i][0] < q < iv_[i][1]:
                arriba, abajo = iv_[i][1], iv_[i][0]
                q = abajo if (abajo >= lb and q - abajo <= arriba - q) else arriba
            out.append(q)
            prev = q
        return out if out[-1] <= hi_ + 1e-9 else None
    res = pasada(nom, iv, inicios, lo, hi)
    if res is None:                                     # de derecha a izquierda (espejo)
        iv_m = [[-b, -a] for a, b in reversed(iv)]
        res_m = pasada([-p for p in reversed(nom)], iv_m, [a for a, _b in iv_m], -hi, -lo)
        res = [-p for p in reversed(res_m)] if res_m is not None else list(nom)
    return [round(p, 5) for p in res]


def _verticales_en(J, caja_):
    """Barras casi verticales de los juegos ya generados que atraviesan la caja (x0, y0, z0, x1, y1, z1): (x, y, db)."""
    x0, y0, z0, x1, y1, z1 = caja_
    out = []
    for j in J.lista:
        if 'forma' not in j:
            continue
        f = j['forma']
        for a, b in zip(f, f[1:]):
            if abs(b[2] - a[2]) > 0.3 and abs(b[0] - a[0]) < 0.02 and abs(b[1] - a[1]) < 0.02:
                za, zb = sorted((a[2], b[2]))
                if zb < z0 or za > z1:
                    continue
                for c in j['copias']:
                    x, y = a[0] + c[0], a[1] + c[1]
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        out.append((x, y, j['db']))
    return sorted(set((round(x, 4), round(y, 4), d) for x, y, d in out))


def _parrilla_1d(centro, span, util, n, sp, verticales, db):
    """Posiciones de las n barras de una parrilla (nominal: centradas cada sp) corridas lo justo para pasar entre las
    barras verticales (posición, diámetro) que la atraviesan, sin salir del ancho útil."""
    nom = [centro - span / 2 + i * sp for i in range(n)]
    proh = [(v - (db + vd) / 2 - 0.002, v + (db + vd) / 2 + 0.002) for v, vd in verticales]
    return _colocar_1d(nom, proh, db + max(db, 0.0254), centro - util / 2, centro + util / 2)


def dados(J, est):
    C = est['cimentacion']
    rec = C['dados'][0].get('rec', 0.075)
    out = {}
    for d in C['dados']:
        host = d['id']
        x0, x1, y0, y1 = d['x0'], d['x1'], d['y0'], d['y1']
        zf, zt = d['z_fondo'], d['z_tope']
        h = zt - zf
        ref = d['refuerzo']
        Lx, Ly = x1 - x0, y1 - y0
        # parrilla inferior: x abajo, y encima; patas dobladas hacia arriba (U)
        ix, iy = ref['inferior_x'], ref['inferior_y']
        dbx, dby = db_de(ix['num']), db_de(iy['num'])
        zx = zf + rec + dbx / 2
        zy = zx + dbx / 2 + dby / 2
        for eje, sp, z, num in (('x', ix['s'], zx, ix['num']), ('y', iy['s'], zy, iy['num'])):
            ancho = Ly if eje == 'x' else Lx
            n = int((ancho - 2 * rec) / sp) + 1
            span = (n - 1) * sp
            R = radio_doblez(num)
            db_ = db_de(num)
            # las barras de esta dirección quedan por dentro de las patas y sus dobleces de la otra (que suben en sus extremos)
            otro = dby if eje == 'x' else dbx
            num_o = iy['num'] if eje == 'x' else ix['num']
            borde = rec + otro / 2 + radio_doblez(num_o) + (otro + db_) / 2 + 0.002
            util = ancho - 2 * borde
            if span > util:
                sp = util / (n - 1) if n > 1 else sp
                span = (n - 1) * sp
            vert = _verticales_en(J, (x0, y0, z - db_ / 2, x1, y1, z + db_ / 2))
            if eje == 'x':
                pos = _parrilla_1d((y0 + y1) / 2, span, util, n, sp, [(vy, vd) for vx, vy, vd in vert], db_)
                yc0 = pos[0]
                pts = [[x0 + rec, yc0, zt - rec], [x0 + rec, yc0, z], [x1 - rec, yc0, z], [x1 - rec, yc0, zt - rec]]
                cop = [[0, q - yc0, 0] for q in pos]
            else:
                pos = _parrilla_1d((x0 + x1) / 2, span, util, n, sp, [(vx, vd) for vx, vy, vd in vert], db_)
                xc0 = pos[0]
                pts = [[xc0, y0 + rec + dbx, zt - rec], [xc0, y0 + rec + dbx, z], [xc0, y1 - rec - dbx, z], [xc0, y1 - rec - dbx, zt - rec]]
                cop = [[q - xc0, 0, 0] for q in pos]
            J.agregar(host, f'parrilla_inferior_{eje}', num, doblar(pts, R), cop,
                      f'parrilla inferior N.º {num} c/{_es(sp, 3)} ({eje})', ganchos='patas a 90° hasta arriba', nivel='CIM')
            rf = ix if eje == 'x' else iy
            out.setdefault(host, {})[f'inferior_{eje}'] = {
                'num': num, 's_A_m': rf['s'], 'n_A': rf.get('n'), 's_dibujada_m': r(sp, 4), 'n_dibujadas': n,
                'As_dibujada_mm2': r(n * BARRAS[num][1], 0), 'As_req_mm2': rf.get('As_req_mm2'),
                'ajuste': (f'en el ancho útil entre las patas de la otra dirección ({_es(util, 2)} m) caben {n} barras a {_es(sp, 3)} m'
                           if abs(sp - rf['s']) > 5e-4 else None)}
        out[host]['z_parrilla'] = zy + dby / 2
        dmax = max(dbx, dby)
        # parrilla superior: x arriba, y debajo; patas de 0,30 m hacia abajo
        for eje in ('x', 'y'):
            sref = ref.get(f'superior_{eje}') or ref.get('superior')
            num, sp = sref['num'], sref['s']
            db = db_de(num)
            ancho = Ly if eje == 'x' else Lx
            n = int((ancho - 2 * rec) / sp) + 1
            span = (n - 1) * sp
            z = zt - rec - db / 2 - (0.0 if eje == 'x' else db)
            R = radio_doblez(num)
            # por dentro de las patas de la otra dirección (bajan a 0,03 m en x y a 0,06 m en y del recubrimiento) y de su doblez
            pata = 0.06 if eje == 'x' else 0.03
            util = ancho - 2 * (rec + pata + db / 2 + radio_doblez(num) + db + 0.002)
            if span > util:
                sp = util / (n - 1) if n > 1 else sp
                span = (n - 1) * sp
            vert = _verticales_en(J, (x0, y0, z - db / 2, x1, y1, z + db / 2))
            if eje == 'x':
                pos = _parrilla_1d((y0 + y1) / 2, span, util, n, sp, [(vy, vd) for vx, vy, vd in vert], db)
                yc0 = pos[0]
                pts = [[x0 + rec + 0.03, yc0, z - 0.30], [x0 + rec + 0.03, yc0, z], [x1 - rec - 0.03, yc0, z], [x1 - rec - 0.03, yc0, z - 0.30]]
                cop = [[0, q - yc0, 0] for q in pos]
            else:
                pos = _parrilla_1d((x0 + x1) / 2, span, util, n, sp, [(vx, vd) for vx, vy, vd in vert], db)
                xc0 = pos[0]
                pts = [[xc0, y0 + rec + 0.06, z - 0.30], [xc0, y0 + rec + 0.06, z], [xc0, y1 - rec - 0.06, z], [xc0, y1 - rec - 0.06, z - 0.30]]
                cop = [[q - xc0, 0, 0] for q in pos]
            J.agregar(host, f'parrilla_superior_{eje}', num, doblar(pts, R), cop,
                      f'parrilla superior N.º {num} c/{_es(sp, 3)} ({eje})', ganchos='patas de 0,30 m hacia abajo', nivel='CIM')
        # refuerzo de piel: anillos horizontales N.º 4 c/0,30
        lat = ref.get('lateral')
        if lat:
            num, sp = lat['num'], lat['s']
            db = db_de(num)
            o = rec + 2 * max(dbx, dby) + db / 2 + 0.003          # por dentro de las patas de las parrillas
            nz = int((h - 2 * rec) / sp) + 1
            z_lo, z_hi = zf + rec + 0.10, zt - rec - 0.30 - 0.06      # por debajo de las patas de la parrilla superior
            nz = max(1, min(nz, int((z_hi - z_lo) / sp) + 1)) if z_hi > z_lo else 1
            zs = [z_lo + i * (z_hi - z_lo) / max(nz - 1, 1) for i in range(nz)] if z_hi > z_lo else [z_lo]
            pts = [[x0 + o, y0 + o, zs[0]], [x1 - o, y0 + o, zs[0]], [x1 - o, y1 - o, zs[0]], [x0 + o, y1 - o, zs[0]],
                   [x0 + o, y0 + o, zs[0] + db], [x0 + o + 0.6, y0 + o, zs[0] + db]]
            J.agregar(host, 'piel', num, doblar(pts, radio_doblez(num)), [[0, 0, z - zs[0]] for z in zs],
                      f'piel N.º {num} c/{_es(sp, 3)}', zona='anillo con traslapo de 0,60 m', nivel='CIM')
    return out


def vigas_amarre(J, est):
    C = est['cimentacion']
    rec = 0.05
    for v in C['vigas_amarre']:
        host = v['id']
        a, b_ = v['tramo']
        c = v['coordenada']
        eje = v['direccion']
        zt = v['z_tope']
        h, b = v['h'], v['b']
        num_e = v['estribos']['num']
        de = db_de(num_e)
        for capa in ('superior', 'inferior'):
            n, num = v[capa]['n'], v[capa]['num']
            db = db_de(num)
            R = radio_doblez(num)
            z = zt - rec - de - db / 2 if capa == 'superior' else zt - h + rec + de + db / 2
            la = ldh_sismico(num)
            sg = -1 if capa == 'superior' else 1
            lats = _laterales(n, b, rec, num, num_e)
            pts = [_p(eje, c, a - la, lats[0], z + sg * (cola_90(num) + R)), _p(eje, c, a - la, lats[0], z),
                   _p(eje, c, b_ + la, lats[0], z), _p(eje, c, b_ + la, lats[0], z + sg * (cola_90(num) + R))]
            cop = [[0, l_ - lats[0], 0] if eje == 'x' else [l_ - lats[0], 0, 0] for l_ in lats]
            J.agregar(host, capa, num, doblar(pts, R), cop, f'{n} N.º {num} {"arriba" if capa == "superior" else "abajo"}',
                      zona=f'ldh = {_es(la, 3)} m en cada dado', ganchos='90° en los dos extremos', nivel='CIM')
        s = v['estribos']['s_m']
        pos = [a + 0.05 + i * s for i in range(n_estribos(b_ - a, s))]
        hx, hy = b / 2 - rec - de / 2, h / 2 - rec - de / 2
        ea = [0, 1, 0] if eje == 'x' else [1, 0, 0]
        eax = [1, 0, 0] if eje == 'x' else [0, 1, 0]
        forma = estribo_cerrado(_p(eje, c, pos[0], 0, zt - h / 2), ea, [0, 0, 1], hx, hy, num_e, eax, db_esq=db_de(v['superior']['num']))
        J.agregar(host, 'estribo', num_e, forma, [[p - pos[0], 0, 0] if eje == 'x' else [0, p - pos[0], 0] for p in pos],
                  f'E N.º {num_e} c/{_es(s, 3)}', ganchos='135°', nivel='CIM')


def mallas_caja(J, host, caras, num, s, rec, etiqueta, nivel):
    """Mallas en caras planas: caras = [(origen, eu, ev, Lu, Lv, normal_hacia_adentro)], dos direcciones."""
    db = db_de(num)
    for ci, (o, eu, ev, Lu, Lv, nin) in enumerate(caras):
        for direc, (ea, La, eb, Lb, capa) in enumerate(((eu, Lu, ev, Lv, 0), (ev, Lv, eu, Lu, 1))):
            n = int(math.ceil((Lb - 2 * rec) / s - 1e-9)) + 1              # paso ≤ s
            if n < 1 or La - 2 * rec <= 0:
                continue
            prof = rec + db / 2 + capa * db
            # la barra de borde a rec + db/2 de la cara lateral (recubrimiento rec a su superficie)
            p0 = [o[i] + ea[i] * rec + eb[i] * (rec + db / 2) + nin[i] * prof for i in range(3)]
            p1 = [p0[i] + ea[i] * (La - 2 * rec) for i in range(3)]
            paso = (Lb - 2 * rec - db) / max(n - 1, 1)
            J.agregar(host, 'malla_losa' if abs(nin[2]) > 0.5 else 'malla_muro', num, [p0, p1],
                      [[eb[i] * paso * k for i in range(3)] for k in range(n)], etiqueta, zona=f'cara {ci + 1}, dirección {direc + 1}', nivel=nivel)


def fosos_y_cisternas(J, est):
    C = est['cimentacion']
    for f in C['fosos']:
        host = f['id']
        x0, x1 = f['x']
        y0, y1 = f['y']
        zf = f['z_fondo']
        e, el = f['muro_e_m'], f['losa_e_m']
        num, s = f['refuerzo']['num'], f['refuerzo']['s']
        rec = 0.05
        ztop = 0.0 - 0.15
        caras = []
        # losa de fondo: cara inferior y superior
        caras.append(([x0, y0, zf], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, 1]))
        caras.append(([x0, y0, zf + el], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, -1]))
        hm = ztop - (zf + el)
        for (o, eu, Lu, nin) in (([x0, y0, zf + el], [1, 0, 0], x1 - x0, [0, 1, 0]), ([x0, y1, zf + el], [1, 0, 0], x1 - x0, [0, -1, 0]),
                                 ([x0, y0 + e, zf + el], [0, 1, 0], y1 - y0 - 2 * e, [1, 0, 0]),
                                 ([x1, y0 + e, zf + el], [0, 1, 0], y1 - y0 - 2 * e, [-1, 0, 0])):
            caras.append((o, eu, [0, 0, 1], Lu, hm, nin))
            o2 = [o[i] + nin[i] * e for i in range(3)]
            caras.append((o2, eu, [0, 0, 1], Lu, hm, [-c for c in nin]))
        mallas_caja(J, host, caras, num, s, rec, f'N.º {num} c/{_es(s, 3)} en las dos caras y direcciones', 'CIM')
    for c in C['cisternas']:
        host = c['id']
        x0, x1 = c['x']
        y0, y1 = c['y']
        zf = c['z_fondo']
        e, ef, et = c['muro_e_m'], c['losa_fondo_e_m'], c['losa_tapa_e_m']
        num, s = c['refuerzo']['num'], c['refuerzo']['s']
        rec = 0.05
        zt = zf + ef + c['h_interior_m'] + et
        # losa de fondo (N.º 8 c/0,10 arriba y abajo) y tapa (N.º 4: c/0,15 abajo y c/0,25 arriba)
        mallas_caja(J, host, [([x0, y0, zf], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, 1]),
                              ([x0, y0, zf + ef], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, -1])],
                    num, s, 0.075, f'losa de fondo N.º {num} c/{_es(s, 3)}', 'CIM')
        mallas_caja(J, host, [([x0, y0, zt - et], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, 1])], 4, 0.15, rec,
                    'tapa N.º 4 c/0,15 abajo', 'CIM')
        mallas_caja(J, host, [([x0, y0, zt], [1, 0, 0], [0, 1, 0], x1 - x0, y1 - y0, [0, 0, -1])], 4, 0.25, rec,
                    'tapa N.º 4 c/0,25 arriba', 'CIM')
        # muros exteriores y los dos tabiques: verticales N.º num c/s y horizontales N.º 4 c/0,20 en las dos caras
        hm = c['h_interior_m']
        z0 = zf + ef
        Lx = x1 - x0
        xi = Lx - 2 * e - 2 * 0.25
        tabiques = [x0 + e + xi * 40 / 90, x0 + e + xi * 40 / 90 + 0.25 + xi * 30 / 90]
        muros_ = [([x0, y0, z0], [1, 0, 0], Lx, [0, 1, 0], e), ([x0, y1, z0], [1, 0, 0], Lx, [0, -1, 0], e),
                  ([x0, y0 + e, z0], [0, 1, 0], y1 - y0 - 2 * e, [1, 0, 0], e), ([x1, y0 + e, z0], [0, 1, 0], y1 - y0 - 2 * e, [-1, 0, 0], e)]
        for tx in tabiques:
            muros_.append(([tx, y0 + e, z0], [0, 1, 0], y1 - y0 - 2 * e, [1, 0, 0], 0.25))
        for (o, eu, Lu, nin, esp) in muros_:
            for cara in (0, 1):
                oo = o if cara == 0 else [o[i] + nin[i] * esp for i in range(3)]
                nn = nin if cara == 0 else [-q for q in nin]
                db = db_de(num)
                prof = rec + db / 2
                nv_ = int(math.ceil((Lu - 2 * rec - db) / s - 1e-9)) + 1
                paso_v = (Lu - 2 * rec - db) / max(nv_ - 1, 1)
                p0 = [oo[i] + eu[i] * (rec + db / 2) + nn[i] * prof for i in range(3)]
                J.agregar(host, 'muro_vertical', num, [p0, [p0[0], p0[1], p0[2] + hm]],
                          [[eu[i] * paso_v * k for i in range(3)] for k in range(nv_)], f'N.º {num} c/{_es(s, 3)} vertical', nivel='CIM')
                dbh = db_de(4)
                prof_h = prof + db / 2 + dbh / 2
                nh = int(hm / 0.20) + 1
                p0 = [oo[i] + eu[i] * rec + nn[i] * prof_h for i in range(3)]
                p0[2] = z0 + 0.10
                p1 = [p0[i] + eu[i] * (Lu - 2 * rec) for i in range(3)]
                J.agregar(host, 'muro_horizontal', 4, [p0, p1], [[0, 0, 0.20 * k] for k in range(nh) if 0.10 + 0.20 * k < hm],
                          'N.º 4 c/0,20 horizontal', nivel='CIM')


def contrapiso(J, est, rect, huecos):
    """Malla electrosoldada Ø 7 mm c/0,125 en las dos direcciones, a media altura de la losa de 0,15 m, cortada en los
    huecos (fosos y columnas)."""
    x0, y0, x1, y1 = rect
    zx, zy = -0.075 + 0.0035, -0.075 - 0.0035
    tramos = {}

    def cortar(a, b, fijo, eje):
        segs = [(a, b)]
        for h in huecos:
            hx0, hy0, hx1, hy1 = h
            if eje == 'x' and not (hy0 < fijo < hy1):
                continue
            if eje == 'y' and not (hx0 < fijo < hx1):
                continue
            ca, cb = (hx0, hx1) if eje == 'x' else (hy0, hy1)
            nuevo = []
            for s0, s1 in segs:
                if cb <= s0 or ca >= s1:
                    nuevo.append((s0, s1))
                    continue
                if ca - 0.05 > s0:
                    nuevo.append((s0, ca - 0.05))
                if cb + 0.05 < s1:
                    nuevo.append((cb + 0.05, s1))
            segs = nuevo
        return segs
    ny = int((y1 - y0 - 0.10) / 0.125) + 1
    for i in range(ny):
        y = y0 + 0.05 + i * 0.125
        for s0, s1 in cortar(x0 + 0.05, x1 - 0.05, y, 'x'):
            tramos.setdefault(('x', r(s0, 4), r(s1, 4)), []).append(y)
    nx = int((x1 - x0 - 0.10) / 0.125) + 1
    for i in range(nx):
        x = x0 + 0.05 + i * 0.125
        for s0, s1 in cortar(y0 + 0.05, y1 - 0.05, x, 'y'):
            tramos.setdefault(('y', r(s0, 4), r(s1, 4)), []).append(x)
    for (eje, s0, s1) in sorted(tramos):
        cs = tramos[(eje, s0, s1)]
        if eje == 'x':
            forma = [[s0, cs[0], zx], [s1, cs[0], zx]]
            cop = [[0, c - cs[0], 0] for c in cs]
        else:
            forma = [[cs[0], s0, zy], [cs[0], s1, zy]]
            cop = [[c - cs[0], 0, 0] for c in cs]
        J.agregar('CP-1', f'malla_{eje}', None, forma, cop, f'malla Ø 7 mm c/0,125 ({eje})', diam_mm=7.0,
                  kg_m=MALLA[7.0][1], nivel='CIM')
