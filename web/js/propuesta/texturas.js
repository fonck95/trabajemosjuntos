// Texturas procedurales de la maqueta de la propuesta y el material que las pone en coordenadas del mundo.
// · Las texturas se pintan en un canvas al pedirlas por primera vez (sin archivos ni peticiones: la CSP del sitio no deja
//   cargar imágenes de otro origen y el Artifact no lleva archivos aparte). Todas se repiten sin costura (ruido periódico),
//   en potencias de 2, con mipmaps y filtro anisotrópico.
// · MatMundo es un MeshStandardMaterial que lee su textura en coordenadas del mundo y no en las UV de la geometría:
//   proyección plana (pisos, vías) o triplanar (muros, cubiertas, mobiliario), con la escala real de cada material (un
//   adoquín mide lo mismo en la plaza que en el andén). Las piezas se arman con cajas escaladas, extrusiones y geometrías
//   unidas sin UV: así todas llevan textura sin calcular coordenadas. Suma relieve (normal perturbada con la luminancia de
//   la textura, en metros, que se apaga con la distancia para no titilar) y variación de gran escala contra la repetición.
import { THREE } from '../core.js';

// ---------------------------------------------------------------- ruido periódico (sin costura) y pseudoaleatorio
function azar(semilla = 1) { let s = semilla >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
const ruidos = new Map();
/** Ruido de valor fractal de n × n que se repite: c celdas en la primera octava, el doble en cada una. Valores 0…1. */
export function ruido(n, c, semilla = 1, octavas = 4, persist = 0.5) {
  const k = `${n}|${c}|${semilla}|${octavas}|${persist}`;
  if (ruidos.has(k)) return ruidos.get(k);
  const out = new Float32Array(n * n);
  let amp = 1, tot = 0, cel = c;
  for (let o = 0; o < octavas && cel <= n; o++, amp *= persist, cel *= 2) {
    const g = new Float32Array(cel * cel), r = azar(semilla * 7919 + o * 104729 + 17);
    for (let i = 0; i < g.length; i++) g[i] = r();
    for (let y = 0; y < n; y++) {
      const fy = (y / n) * cel, y0 = Math.floor(fy), ty = fy - y0, sy = ty * ty * (3 - 2 * ty), y1 = (y0 + 1) % cel;
      for (let x = 0; x < n; x++) {
        const fx = (x / n) * cel, x0 = Math.floor(fx), tx = fx - x0, sx = tx * tx * (3 - 2 * tx), x1 = (x0 + 1) % cel;
        const a = g[y0 * cel + x0], b = g[y0 * cel + x1], cc = g[y1 * cel + x0], d = g[y1 * cel + x1];
        out[y * n + x] += amp * (a + (b - a) * sx + (cc - a) * sy + (a - b - cc + d) * sx * sy);
      }
    }
    tot += amp;
  }
  for (let i = 0; i < out.length; i++) out[i] /= tot;
  ruidos.set(k, out);
  return out;
}
const mezcla = (a, b, t) => a + (b - a) * t;
const lerpC = (a, b, t) => [mezcla(a[0], b[0], t), mezcla(a[1], b[1], t), mezcla(a[2], b[2], t)];
const sat = (v) => Math.max(0, Math.min(1, v));
const suave = (e0, e1, v) => { const t = sat((v - e0) / (e1 - e0)); return t * t * (3 - 2 * t); };

// ---------------------------------------------------------------- lienzos y texturas
const texturas = new Map();
// anisotropía pedida: three la limita al máximo del equipo al subir la textura (consultarlo aquí obligaría a esperar a la GPU)
const ANISOTROPIA = 8;
function lienzo(w, h = w) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
// Pinta píxel a píxel: fn(x, y) → [r, g, b] o [r, g, b, a] (0…255)
function pixeles(c, fn) {
  const x = c.getContext('2d'), im = x.createImageData(c.width, c.height), d = im.data;
  for (let j = 0; j < c.height; j++) for (let i = 0; i < c.width; i++) {
    const v = fn(i, j), p = (j * c.width + i) * 4;
    d[p] = v[0]; d[p + 1] = v[1]; d[p + 2] = v[2]; d[p + 3] = v.length > 3 ? v[3] : 255;
  }
  x.putImageData(im, 0, 0);
  return x;
}
function textura(nombre, crear, { color = true } = {}) {
  if (texturas.has(nombre)) return texturas.get(nombre);
  const c = crear(), t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.anisotropy = ANISOTROPIA; t.name = nombre;
  texturas.set(nombre, t);
  return t;
}

// Cada pintor devuelve un canvas. Los colores están en sRGB; los que se tiñen por instancia o por vértice (fachadas,
// zinc, caucho) se pintan claros y casi neutros para que el tinte mande
const PINTORES = {
  // césped corto de cancha y jardín (4 m): verde con matas más claras y oscuras
  cesped: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 8, 11), f2 = ruido(n, 64, 12, 2), r = azar(13);
    pixeles(c, (x, y) => { const k = sat(f1[y * n + x] * 0.55 + f2[y * n + x] * 0.45 + (r() - 0.5) * 0.3); return lerpC([58, 104, 42], [116, 158, 70], k); });
    return c;
  },
  // potrero y patios (220 m): verdes con manchas irregulares de pasto seco; poco contraste fino (de lejos no se ve la
  // repetición: la variación de gran escala del material hace el resto)
  potrero: () => {
    const n = 512, c = lienzo(n), f1 = ruido(n, 3, 21, 6, 0.55), f2 = ruido(n, 16, 22, 4), f3 = ruido(n, 128, 23, 2), r = azar(24);
    pixeles(c, (x, y) => {
      const i = y * n + x, seco = suave(0.45, 0.85, f1[i] * 0.6 + f2[i] * 0.4) * 0.35, k = 0.94 + 0.1 * f2[i] + (f3[i] - 0.5) * 0.1 + (r() - 0.5) * 0.05;
      const base = lerpC([84, 118, 54], [138, 134, 84], seco);
      return [base[0] * k, base[1] * k, base[2] * k];
    });
    return c;
  },
  // tierra apisonada de las vías destapadas (6 m): ocre grisáceo con huellas claras y piedritas
  tierra: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 4, 35, 4), f2 = ruido(n, 64, 36, 2), r = azar(37);
    pixeles(c, (x, y) => {
      const i = y * n + x, k = 0.86 + 0.2 * f1[i] + (f2[i] - 0.5) * 0.16, huella = Math.abs(((x / n) * 2) % 1 - 0.5) < 0.12 ? 1.06 : 1;
      if (r() > 0.97) return [150, 140, 126];
      return [176 * k * huella, 158 * k * huella, 128 * k * huella];
    });
    return c;
  },
  // asfalto (5 m): gris con agregado claro y manchas
  asfalto: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 4, 31, 3), f2 = ruido(n, 128, 32, 1), r = azar(33);
    pixeles(c, (x, y) => {
      const i = y * n + x, a = r(), k = 0.82 + 0.22 * f1[i] + (f2[i] - 0.5) * 0.3;
      if (a > 0.965) return [128, 126, 122];
      return [72 * k, 74 * k, 77 * k];
    });
    return c;
  },
  // adoquín de concreto (2,4 m): piezas de 30 × 15 cm a junta trabada, tonos beige y gris, junta y bisel
  adoquin: () => {
    const n = 512, c = lienzo(n), f = ruido(n, 64, 41, 2), r = azar(42), cols = 8, filas = 16, pw = n / cols, ph = n / filas;
    const tonos = [[198, 190, 176], [182, 175, 162], [208, 202, 190], [170, 163, 151], [190, 182, 170], [160, 156, 150]];
    const tono = []; for (let j = 0; j < filas; j++) for (let i = 0; i < cols + 1; i++) tono.push(tonos[Math.floor(r() * tonos.length)].map((v) => v * (0.94 + r() * 0.1)));
    pixeles(c, (x, y) => {
      const fi = Math.floor(y / ph), off = fi % 2 ? pw / 2 : 0, xx = (x + off) % n, ci = Math.floor(xx / pw), lx = xx - ci * pw, ly = y - fi * ph;
      const t = tono[fi * (cols + 1) + ci], k = 0.92 + 0.16 * f[y * n + x];
      if (lx < 2 || ly < 2) return [112, 108, 100];
      const bisel = lx < 4 || ly < 4 ? 1.08 : lx > pw - 3 || ly > ph - 3 ? 0.86 : 1;
      return [t[0] * k * bisel, t[1] * k * bisel, t[2] * k * bisel];
    });
    return c;
  },
  // concreto (3 m): gris claro con nubes, poros y junta en el borde de la losa
  concreto: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 4, 51, 4), f2 = ruido(n, 64, 52, 2), r = azar(53);
    pixeles(c, (x, y) => {
      const i = y * n + x, k = 0.88 + 0.16 * f1[i] + (f2[i] - 0.5) * 0.1 - (r() > 0.985 ? 0.12 : 0);
      if (x === 0 || y === 0) return [150, 148, 142];
      return [196 * k, 193 * k, 186 * k];
    });
    return c;
  },
  // pañete pintado (2 m): blanco con textura suave de llana (se tiñe)
  estuco: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 8, 61, 4), f2 = ruido(n, 128, 62, 1);
    pixeles(c, (x, y) => { const i = y * n + x, k = 0.9 + 0.08 * f1[i] + (f2[i] - 0.5) * 0.06; return [246 * k, 244 * k, 238 * k]; });
    return c;
  },
  // arcilla del cuadro de sóftbol (5 m): ocre con huellas y grumos
  arcilla: () => {
    const n = 256, c = lienzo(n), f1 = ruido(n, 8, 71, 4), f2 = ruido(n, 128, 72, 1), r = azar(73);
    pixeles(c, (x, y) => {
      const i = y * n + x, k = 0.86 + 0.2 * f1[i] + (f2[i] - 0.5) * 0.2;
      if (r() > 0.975) return [206, 142, 96];
      return [186 * k, 108 * k, 64 * k];
    });
    return c;
  },
  // tablas de madera (1,6 m): 10 tablas por tramo, veta y junta
  madera: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 16, 81, 3), r = azar(82), tablas = 10, h = n / tablas;
    const tonos = Array.from({ length: tablas }, () => [[156, 104, 62], [170, 118, 72], [142, 94, 56], [162, 112, 70]][Math.floor(r() * 4)]);
    pixeles(c, (x, y) => {
      const t = Math.floor(y / h), ly = y - t * h;
      if (ly < 2) return [70, 48, 32];
      const veta = 0.9 + 0.1 * Math.sin((x / n) * 40 + f[y * n + x] * 9 + t * 3), k = veta * (0.92 + 0.12 * f[y * n + x]);
      return tonos[t].map((v) => v * k);
    });
    return c;
  },
  // teja de barro (2 m, con UV: u a lo largo de la cumbrera, v por la pendiente): canales y filas
  teja: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 16, 91, 3), r = azar(92), canales = 8, filas = 6;
    const tonos = Array.from({ length: canales * filas }, () => [[174, 86, 52], [160, 76, 46], [186, 98, 62], [150, 72, 48]][Math.floor(r() * 4)]);
    pixeles(c, (x, y) => {
      const u = (x / n) * canales, v = (y / n) * filas, ci = Math.floor(u), fi = Math.floor(v), lu = u - ci, lv = v - fi;
      const onda = 0.68 + 0.32 * Math.sin(lu * Math.PI), borde = lv > 0.9 ? 0.62 : 1, k = onda * borde * (0.9 + 0.18 * f[y * n + x]);
      return tonos[fi * canales + ci].map((t) => t * k);
    });
    return c;
  },
  // zinc ondulado (1 m, con UV): ondas a lo largo de la pendiente, claro para teñirlo, con algo de óxido
  zinc: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 4, 101, 4), f2 = ruido(n, 32, 102, 2);
    pixeles(c, (x, y) => {
      const i = y * n + x, onda = 0.8 + 0.2 * Math.sin((x / n) * Math.PI * 2 * 13), oxido = suave(0.62, 0.85, f[i]) * 0.55, k = onda * (0.93 + 0.1 * f2[i]);
      return lerpC([226, 228, 230], [176, 124, 92], oxido).map((v) => v * k);
    });
    return c;
  },
  // ladrillo a la vista (1,04 m): soga trabada de 26 × 7,4 cm, tonos de barro cocido y mortero
  ladrillo: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 64, 111, 2), r = azar(112), cols = 4, filas = 14, pw = n / cols, ph = n / filas;
    const tonos = Array.from({ length: (cols + 1) * filas }, () => [[170, 84, 52], [182, 96, 60], [152, 74, 46], [192, 108, 70], [164, 90, 58]][Math.floor(r() * 5)].map((v) => v * (0.93 + r() * 0.12)));
    pixeles(c, (x, y) => {
      const fi = Math.floor(y / ph), off = fi % 2 ? pw / 2 : 0, xx = (x + off) % n, ci = Math.floor(xx / pw), lx = xx - ci * pw, ly = y - fi * ph;
      if (lx < 2.5 || ly < 2.5) return [204, 194, 178];
      const k = 0.9 + 0.18 * f[y * n + x];
      return tonos[fi * (cols + 1) + ci].map((v) => v * k);
    });
    return c;
  },
  // lona tensada (4 m): blanca con costuras cada metro
  membrana: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 4, 121, 3);
    pixeles(c, (x, y) => { const k = (0.94 + 0.06 * f[y * n + x]) * (x % 64 < 2 ? 0.86 : 1); return [246 * k, 245 * k, 240 * k]; });
    return c;
  },
  // caucho EPDM y pintura acrílica (1,2 m): granos claros y oscuros, casi neutro para teñirlo
  caucho: () => {
    const n = 256, c = lienzo(n), r = azar(131), f = ruido(n, 8, 132, 3);
    pixeles(c, (x, y) => { const a = r(), k = (0.9 + 0.1 * f[y * n + x]) * (a > 0.9 ? 1.12 : a < 0.08 ? 0.82 : 1); return [236 * k, 236 * k, 236 * k]; });
    return c;
  },
  // malla eslabonada (0,3 m): rombos de alambre; el alfa deja ver a través (de lejos queda una veladura)
  malla: () => {
    const n = 256, c = lienzo(n), k = 4, p = n / k;
    pixeles(c, (x, y) => {
      const a = ((x + y) % p + p) % p, b = ((x - y) % p + p) % p, dA = Math.min(a, p - a), dB = Math.min(b, p - b), d = Math.min(dA, dB);
      const al = sat(1.6 - d / 1.4);
      return [235, 238, 240, Math.round(al * 255)];
    });
    return c;
  },
  // bloque calado de ventilación (1,2 m): 4 × 6 huecos
  calado: () => {
    const n = 256, c = lienzo(n), f = ruido(n, 32, 141, 2);
    pixeles(c, (x, y) => {
      const lx = (x % 64) / 64, ly = (y % 42.67) / 42.67, hueco = lx > 0.18 && lx < 0.82 && ly > 0.2 && ly < 0.8, k = 0.9 + 0.12 * f[y * n + x];
      return hueco ? [58, 56, 54] : [214 * k, 208 * k, 196 * k];
    });
    return c;
  },
  // follaje (2,4 m): racimos de hojas, claro en las puntas y oscuro en los huecos (se tiñe por instancia)
  follaje: () => {
    const n = 512, c = lienzo(n), f1 = ruido(n, 12, 151, 4), f2 = ruido(n, 48, 152, 3);
    pixeles(c, (x, y) => { const i = y * n + x, k = 0.6 + 0.5 * suave(0.28, 0.78, f1[i] * 0.55 + f2[i] * 0.45); return [230 * k, 236 * k, 222 * k]; });
    return c;
  },
  // corteza de palma (1 m): anillos horizontales
  anillos: () => {
    const n = 128, c = lienzo(n), f = ruido(n, 16, 161, 2);
    pixeles(c, (x, y) => { const k = (0.82 + 0.18 * Math.abs(Math.sin((y / n) * Math.PI * 7))) * (0.92 + 0.1 * f[y * n + x]); return [168 * k, 150 * k, 126 * k]; });
    return c;
  },
};

/** Textura procedural por nombre (ver PINTORES). */
export const tex = (nombre) => textura(nombre, PINTORES[nombre]);
/** Ruido en escala de grises para la variación de gran escala y el relieve del agua (datos, no color). */
export const texRuido = () => textura('ruido', () => { const n = 256, c = lienzo(n), f = ruido(n, 4, 171, 5, 0.55); pixeles(c, (x, y) => { const v = f[y * n + x] * 255; return [v, v, v]; }); return c; }, { color: false });
export const texOlas = () => textura('olas', () => { const n = 256, c = lienzo(n), f = ruido(n, 8, 181, 4, 0.6), g = ruido(n, 32, 182, 2); pixeles(c, (x, y) => { const v = sat(f[y * n + x] * 0.7 + g[y * n + x] * 0.3) * 255; return [v, v, v]; }); return c; }, { color: false });

// Hoja de palma (con UV: u a lo largo de la hoja, v de un borde al otro): raquis y foliolos; el alfa recorta la silueta
export const texPalma = () => textura('palma', () => {
  const w = 512, h = 128, c = lienzo(w, h), x = c.getContext('2d');
  x.clearRect(0, 0, w, h);
  const g = x.createLinearGradient(0, 0, w, 0); g.addColorStop(0, '#5f8a3a'); g.addColorStop(1, '#86a84a');
  x.strokeStyle = g; x.lineCap = 'round';
  for (let i = 0; i < 46; i++) {
    const t = i / 46, px = 14 + t * (w - 30), largo = (h / 2 - 6) * Math.sin(Math.PI * (0.18 + t * 0.82)) ** 0.7;
    x.lineWidth = 5.5 - t * 2.5;
    [-1, 1].forEach((s) => { x.beginPath(); x.moveTo(px, h / 2); x.quadraticCurveTo(px + 10, h / 2 + s * largo * 0.6, px + 22, h / 2 + s * largo); x.stroke(); });
  }
  x.strokeStyle = '#7d7a4a'; x.lineWidth = 4; x.beginPath(); x.moveTo(0, h / 2); x.lineTo(w - 6, h / 2); x.stroke();
  return c;
});
// Hoja lanceolada (cordyline, heliconia, helecho): silueta en el alfa, nervio central más claro
export const texHoja = () => textura('hoja', () => {
  const w = 128, h = 256, c = lienzo(w, h), x = c.getContext('2d');
  x.clearRect(0, 0, w, h); x.fillStyle = '#ffffff';
  x.beginPath(); x.moveTo(w / 2, h - 2); x.bezierCurveTo(w * 1.02, h * 0.62, w * 0.9, h * 0.2, w / 2, 2); x.bezierCurveTo(w * 0.1, h * 0.2, -w * 0.02, h * 0.62, w / 2, h - 2); x.fill();
  x.strokeStyle = 'rgba(255,255,255,0.6)'; x.globalCompositeOperation = 'source-atop'; x.fillStyle = 'rgba(0,0,0,0.18)';
  for (let i = 0; i < 18; i++) { const y = 20 + i * 12; x.fillRect(0, y, w, 2); }
  x.globalCompositeOperation = 'source-over'; x.strokeStyle = 'rgba(255,255,240,0.9)'; x.lineWidth = 3; x.beginPath(); x.moveTo(w / 2, h - 2); x.lineTo(w / 2, 6); x.stroke();
  return c;
});

// Fachada de casa del pueblo (con UV: u en metros a lo largo del muro, v en metros de alto). Dos bandas de 6 m de alto:
// abajo (v 0–6) la fachada a la calle, con puerta, ventana con reja y zócalo; arriba (v 6–12) la culata o el muro lateral,
// con ventanas pequeñas. u de 5 a 6 m es muro liso (para muros cortos). Se tiñe con el color de cada casa
const FACH_W = 512, FACH_H = 1024, PXM = FACH_W / 6;   // 85,3 px por metro
function huecosFachada() {
  // [u0, v0, u1, v1, tipo] en metros; tipo: 'puerta' | 'ventana' | 'ventanita'
  return [
    [0.7, 0, 1.7, 2.2, 'puerta'], [2.6, 0.95, 4.2, 2.2, 'ventana'],                          // fachada, primer piso
    [0.8, 3.75, 2.2, 5.0, 'ventana'], [3.0, 3.75, 4.4, 5.0, 'ventana'],                     // fachada, segundo piso
    [1.6, 7.4, 2.4, 8.2, 'ventanita'], [3.4, 7.4, 4.2, 8.2, 'ventanita'], [2.2, 10.2, 3.6, 11.0, 'ventanita'],   // muro lateral
  ];
}
const enPx = (u, v) => [u * PXM, FACH_H - v * PXM];
export const texFachada = () => textura('fachada', () => {
  const c = lienzo(FACH_W, FACH_H), x = c.getContext('2d'), n = 256, f = ruido(n, 8, 191, 4);
  pixeles(c, (i, j) => { const k = 0.9 + 0.1 * f[(j % n) * n + (i % n)]; return [244 * k, 241 * k, 234 * k]; });
  // zócalo (más oscuro) y sombra bajo el alero de los dos pisos
  x.fillStyle = 'rgba(70,64,58,0.45)'; [0, 6].forEach((b) => { const [, y] = enPx(0, b + 0.55); x.fillRect(0, y, FACH_W, 0.55 * PXM); });
  x.fillStyle = 'rgba(80,80,80,0.18)'; x.fillRect(0, enPx(0, 3.02)[1], FACH_W, 0.12 * PXM);
  for (const [u0, v0, u1, v1, tipo] of huecosFachada()) {
    const [a, b] = enPx(u0, v1), [cx, d] = enPx(u1, v0), w = cx - a, h = d - b;
    x.fillStyle = '#f4f2ec'; x.fillRect(a - 6, b - 6, w + 12, h + 12);                         // marco
    if (tipo === 'puerta') {
      x.fillStyle = '#6d4a33'; x.fillRect(a, b, w, h);
      x.fillStyle = 'rgba(0,0,0,0.25)'; for (let k = 1; k < 4; k++) x.fillRect(a + 6, b + (h * k) / 4, w - 12, 3);
    } else {
      const g = x.createLinearGradient(a, b, a, d); g.addColorStop(0, '#5c6f7c'); g.addColorStop(1, '#2c3740');
      x.fillStyle = g; x.fillRect(a, b, w, h);
      x.fillStyle = 'rgba(255,255,255,0.18)'; x.fillRect(a + 4, b + 4, w * 0.4, h * 0.35);       // reflejo
      x.fillStyle = '#e9e6de'; x.fillRect(a + w / 2 - 2, b, 4, h);                               // parteluz
      if (tipo === 'ventana' && v0 < 3) { x.fillStyle = '#26292c'; for (let k = 1; k < 7; k++) x.fillRect(a + (w * k) / 7 - 1.5, b, 3, h); }   // reja
      x.fillStyle = '#d8d4ca'; x.fillRect(a - 10, d, w + 20, 8);                                 // alféizar
    }
  }
  return c;
});
// lo que brilla de noche en la fachada: los vidrios
export const texFachadaLuz = () => textura('fachadaLuz', () => {
  const c = lienzo(FACH_W / 4, FACH_H / 4), x = c.getContext('2d'), k = 0.25;
  x.fillStyle = '#000'; x.fillRect(0, 0, c.width, c.height);
  huecosFachada().forEach(([u0, v0, u1, v1, tipo], i) => {
    if (tipo === 'puerta') return;
    const [a, b] = enPx(u0, v1), [cx, d] = enPx(u1, v0);
    x.fillStyle = i % 3 === 1 ? '#3a2a14' : '#ffd9a0'; x.fillRect(a * k, b * k, (cx - a) * k, (d - b) * k);
  });
  return c;
});
export const FACHADA = { ancho: 6, alto: 12, lateral: 6, liso: [5, 6] };

// ---------------------------------------------------------------- material en coordenadas del mundo
let texMacro = null;
/** Lo que se apaga en equipos sin GPU o modestos (lo fija la escena antes del primer cuadro): relieve y variación de gran escala. */
export const ajustesMundo = { relieve: true, macro: true };
const VERT_DECL = 'varying vec3 vMundoPos;\nvarying vec3 vMundoNor;\n';
const VERT_CALC = `
  vec4 mwP = vec4( transformed, 1.0 );
  vec3 mwN = objectNormal;
  #ifdef USE_INSTANCING
    mwP = instanceMatrix * mwP; mwN = mat3( instanceMatrix ) * mwN;
  #endif
  mwP = modelMatrix * mwP;
  vMundoPos = mwP.xyz;
  vMundoNor = normalize( mat3( modelMatrix ) * mwN );`;
const FRAG_DECL = `varying vec3 vMundoPos;
varying vec3 vMundoNor;
uniform float uEsc;
uniform float uRel;
uniform float uMacro;
uniform sampler2D tMacro;
#ifdef MUNDO_ALTO
  uniform sampler2D tAlto;
  uniform float uEscAlto;
#endif
#ifdef MUNDO_FRANJAS
  uniform vec4 uFranja;
  uniform vec4 uFranja2;
  float mundoBanda( float x ) { float w = fwidth( x ) * 1.5, t = abs( fract( x ) - 0.5 ) * 2.0; return smoothstep( 0.5 - w, 0.5 + w, t ) * 2.0 - 1.0; }
#endif
vec4 mundoTex( sampler2D t, float e ) {
  #ifdef MUNDO_XZ
    return texture2D( t, vMundoPos.xz * e );
  #else
    vec3 b = pow( abs( normalize( vMundoNor ) ), vec3( 4.0 ) );
    b /= ( b.x + b.y + b.z );
    return texture2D( t, vMundoPos.zy * e ) * b.x + texture2D( t, vMundoPos.xz * e ) * b.y + texture2D( t, vMundoPos.xy * e ) * b.z;
  #endif
}`;
const FRAG_MAP = `
  float mundoH = 0.5;
  #ifdef USE_MAP
    vec4 sampledDiffuseColor = mundoTex( map, uEsc );
    diffuseColor *= sampledDiffuseColor;
    mundoH = dot( sampledDiffuseColor.rgb, vec3( 0.299, 0.587, 0.114 ) );
  #endif
  #ifdef MUNDO_ALTO
    mundoH = mundoTex( tAlto, uEscAlto ).r;
  #endif
  #ifdef MUNDO_FRANJAS
  {
    vec2 rel = vMundoPos.xz - uFranja.xy;
    float b1 = mundoBanda( dot( rel, uFranja.zw ) / uFranja2.x ), b2 = mundoBanda( dot( rel, vec2( - uFranja.w, uFranja.z ) ) / uFranja2.x );
    diffuseColor.rgb *= 1.0 + uFranja2.y * b1 + uFranja2.z * b2;
  }
  #endif
  #ifdef MUNDO_MACRO
    float mMac = texture2D( tMacro, vMundoPos.xz * 0.00131 ).r * 0.45 + texture2D( tMacro, vMundoPos.xz * 0.0047 + 0.31 ).r * 0.33 + texture2D( tMacro, vMundoPos.xz * 0.0163 + 0.67 ).r * 0.22;
    diffuseColor.rgb *= 1.0 + uMacro * ( mMac - 0.5 ) * 2.0;
  #endif`;
// relieve (Mikkelsen, «Bump Mapping Unparametrized Surfaces on the GPU»): la altura en metros es la luminancia de la
// textura por uRel; se apaga entre 40 y 160 m de la cámara, donde ya no se ve y solo haría ruido
const FRAG_RELIEVE = `
  #ifdef MUNDO_RELIEVE
  {
    float kR = uRel * ( 1.0 - smoothstep( 40.0, 160.0, length( vViewPosition ) ) );
    vec2 dH = vec2( dFdx( mundoH ), dFdy( mundoH ) ) * kR;
    vec3 sX = dFdx( - vViewPosition ), sY = dFdy( - vViewPosition );
    vec3 R1 = cross( sY, normal ), R2 = cross( normal, sX );
    float det = dot( sX, R1 ) * faceDirection;
    vec3 grad = sign( det ) * ( dH.x * R1 + dH.y * R2 );
    normal = normalize( abs( det ) * normal - grad );
  }
  #endif`;

/**
 * MeshStandardMaterial con la textura en coordenadas del mundo.
 * escala: metros que mide un tramo de la textura; modo: 'tri' (triplanar) o 'xz' (proyección desde arriba);
 * relieve: altura del relieve en metros (0 sin relieve); macro: variación de gran escala (0…0,4) contra la repetición;
 * alto: textura de altura para el relieve (si no, la luminancia del color) y escalaAlto, sus metros por tramo;
 * franjas: { origen: [x, z] de three, dir: [dx, dz] unitario, ancho, k, k2 }: franjas de corte del césped (k a lo largo de dir y
 * k2 en cruz), calculadas en el shader y suavizadas en el borde.
 */
export class MatMundo extends THREE.MeshStandardMaterial {
  constructor({ escala = 1, modo = 'tri', relieve = 0, macro = 0, alto = null, escalaAlto = null, franjas = null, ...p } = {}) {
    super(p);
    this.isMatMundo = true;
    this.mundo = { escala, modo, relieve, macro, alto, escalaAlto: escalaAlto || escala, franjas };
    this._uni = null;
  }
  get _rel() { return this.mundo.relieve > 0 && ajustesMundo.relieve; }
  get _mac() { return this.mundo.macro > 0 && ajustesMundo.macro; }
  get _defs() { const m = this.mundo; return `${m.modo}|${this._rel ? 'r' : ''}|${this._mac ? 'm' : ''}|${m.alto ? 'a' : ''}|${m.franjas ? 'f' : ''}`; }
  customProgramCacheKey() { return `mundo:${this._defs}`; }
  onBeforeCompile(sh) {
    const m = this.mundo;
    texMacro = texMacro || texRuido();
    sh.uniforms.uEsc = { value: 1 / m.escala };
    sh.uniforms.uRel = { value: m.relieve };
    sh.uniforms.uMacro = { value: m.macro };
    sh.uniforms.tMacro = { value: texMacro };
    if (m.alto) { sh.uniforms.tAlto = { value: m.alto }; sh.uniforms.uEscAlto = { value: 1 / m.escalaAlto }; }
    if (m.franjas) { const f = m.franjas; sh.uniforms.uFranja = { value: new THREE.Vector4(f.origen[0], f.origen[1], f.dir[0], f.dir[1]) }; sh.uniforms.uFranja2 = { value: new THREE.Vector4(f.ancho || 5, f.k ?? 0.08, f.k2 ?? 0, 0) }; }
    this._uni = sh.uniforms;
    const defs = [m.modo === 'xz' && '#define MUNDO_XZ', this._rel && '#define MUNDO_RELIEVE', this._mac && '#define MUNDO_MACRO', m.alto && '#define MUNDO_ALTO', m.franjas && '#define MUNDO_FRANJAS'].filter(Boolean).join('\n');
    sh.vertexShader = sh.vertexShader.replace('#include <common>', `#include <common>\n${VERT_DECL}`).replace('#include <worldpos_vertex>', `#include <worldpos_vertex>\n${VERT_CALC}`);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `${defs}\n#include <common>\n${FRAG_DECL}`)
      .replace('#include <map_fragment>', FRAG_MAP).replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>\n${FRAG_RELIEVE}`);
  }
  copy(src) { super.copy(src); if (src.mundo) { this.mundo = { ...src.mundo }; this.isMatMundo = true; } return this; }
}

// Materiales de la maqueta por tipo: textura, metros por tramo, proyección y relieve. opts cambia color, rugosidad,
// metal, lados, etc. Los materiales se crean nuevos cada vez (cada pieza puede teñir el suyo); las texturas se comparten
const TIPOS = {
  cesped: { t: 'cesped', escala: 4, modo: 'xz', macro: 0.14, relieve: 0.02, roughness: 0.96 },
  potrero: { t: 'potrero', escala: 173, modo: 'xz', macro: 0.34, roughness: 1 },
  tierra: { t: 'tierra', escala: 6, modo: 'xz', macro: 0.12, relieve: 0.006, roughness: 1 },
  asfalto: { t: 'asfalto', escala: 5, modo: 'xz', macro: 0.08, relieve: 0.004, roughness: 0.9 },
  adoquin: { t: 'adoquin', escala: 2.4, modo: 'xz', relieve: 0.014, roughness: 0.86, macro: 0.05 },
  concreto: { t: 'concreto', escala: 3, relieve: 0.004, roughness: 0.88 },
  estuco: { t: 'estuco', escala: 2, relieve: 0.003, roughness: 0.92 },
  arcilla: { t: 'arcilla', escala: 5, modo: 'xz', relieve: 0.012, roughness: 1, macro: 0.06 },
  madera: { t: 'madera', escala: 1.6, relieve: 0.006, roughness: 0.72 },
  teja: { t: 'teja', escala: 2, relieve: 0.03, roughness: 0.78 },
  zinc: { t: 'zinc', escala: 1, relieve: 0.02, roughness: 0.42, metalness: 0.55 },
  ladrillo: { t: 'ladrillo', escala: 1.04, relieve: 0.008, roughness: 0.9 },
  membrana: { t: 'membrana', escala: 4, roughness: 0.55, side: THREE.DoubleSide },
  caucho: { t: 'caucho', escala: 1.2, modo: 'xz', relieve: 0.004, roughness: 0.92 },
  malla: { t: 'malla', escala: 0.3, roughness: 0.5, metalness: 0.4, transparent: true, side: THREE.DoubleSide, depthWrite: false },
  calado: { t: 'calado', escala: 1.2, relieve: 0.02, roughness: 0.9 },
  follaje: { t: 'follaje', escala: 3.2, relieve: 0.05, roughness: 0.88 },
  corteza: { t: 'anillos', escala: 1, relieve: 0.02, roughness: 0.95 },
  roca: { t: 'concreto', escala: 1.4, relieve: 0.05, roughness: 1, flatShading: true },
};
/** Material texturizado por tipo (ver TIPOS); opts: cualquier propiedad de MeshStandardMaterial o de MatMundo. */
export function matT(tipo, opts = {}) {
  const b = TIPOS[tipo];
  if (!b) throw new Error(`material sin tipo: ${tipo}`);
  const { t, ...resto } = b, { color, ...o } = opts;
  const m = new MatMundo({ ...resto, map: tex(t), ...o });
  if (color !== undefined) m.color.set(color);
  return m;
}
/** Agua con relieve de olas (sin textura de color): río, caños, lagunas. */
export function matAgua(color, opts = {}) {
  return new MatMundo({ color: new THREE.Color(color), roughness: 0.12, metalness: 0.05, modo: 'xz', relieve: 0.06, alto: texOlas(), escalaAlto: 26, ...opts });
}
