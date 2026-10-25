// Modelo BIM de la torre en 3D (equipo F; especificación de integración 17.5).
// Arma la geometría de los elementos del modelo federado (web/data/torre_bim_<NIVEL>.json) fundida por disciplina —una malla
// por disciplina y una sola malla de aristas—, con un índice de elemento por vértice (atributo «eid») y dos texturas de
// estado por elemento (visible, elegido, en obra en el 4D, transparencia y color propio). Así ocultar, aislar, resaltar,
// colorear con el simulador o avanzar el cronograma cambia unos bytes de una textura y no crea mallas ni llamadas de dibujo.
// Los cortes son planos de recorte de three (horizontales por nivel y verticales por eje) con tapa: los polígonos de la
// sección se calculan con la geometría de cada elemento (cajas, prismas, cilindros y perfiles extruidos) y se rellenan con
// un rayado de corte; el renderizador del atlas no tiene búfer de esténcil, así que la tapa no puede salir de él.
// Coordenadas: el proyecto usa x al oriente, y al norte y z arriba (metros, marco de la especificación); three usa (x, z, −y).
import { THREE } from '../../core.js';

export const DISCIPLINAS = ['ARQ', 'EST', 'CIM', 'FIJO', 'DOT'];
// colores del modelo (son del 3D, no del tema): materiales de arquitectura y tonos de la estructura
const COLOR_MAT = {
  concreto_28: '#b8b4ab', concreto_21: '#c8c3b8', bloque_arcilla: '#dcc0ac', ladrillo_fachada: '#c4876a', placa_yeso: '#ebeae4',
  bloque_nucleo: '#a9a69e', bloque_plomado: '#8f97a4', parapeto: '#d7d3c8', cerramiento: '#8b9188', puerta_hospitalaria: '#7a90a8',
  aluminio_vidrio: '#cfe9f5', vinilo: '#93bcb3', porcelanato: '#e4ddcf', mortero_cuarzo: '#c4c1b9', cielo_fibra: '#f0efe9',
  cielo_yeso: '#f3f2ec', cubierta: '#97a199',
};
const COLOR_CLASE = {
  IfcColumn: '#9d998f', IfcBeam: '#b3aea2', IfcSlab: '#c9c4b9', IfcWall: '#a39f95', IfcPile: '#8f9aa6', IfcFooting: '#a9b0b7',
  IfcElementAssembly: '#9da5ad', IfcMedicalDevice: '#5b8fc7', IfcFurniture: '#c9a77c', IfcElectricAppliance: '#7fa6c9',
  IfcSanitaryTerminal: '#f2f2f0', IfcFireSuppressionTerminal: '#d64541', IfcLightFixture: '#f3d36b', IfcOutlet: '#e9e4d8',
  IfcCommunicationsAppliance: '#6e7f91', IfcElectricDistributionBoard: '#8e959c', IfcElectricFlowStorageDevice: '#6c8f6e',
  IfcElectricGenerator: '#c7a24a', IfcPump: '#4f7fa8', IfcSolarDevice: '#2d3f5c', IfcTank: '#9fb4bf', IfcTransformer: '#7d8a74',
  IfcTransportElement: '#a7adb3', IfcUnitaryEquipment: '#b8c2c8',
};
// tapa de corte por material: concreto gris oscuro, mampostería rojiza, lo demás gris claro
const TAPA = { concreto: '#77736b', mamposteria: '#b07259', otro: '#a3a8ad' };
const esConcreto = (e) => /^concreto/.test(e.material || '');
const esMamposteria = (e) => /bloque|ladrillo|parapeto/.test(e.material || '');

// cubeta de geometría de un elemento: las disciplinas, más el vidrio y los espacios aparte (transparentes)
export function cubeta(e) {
  if (e.clase === 'IfcSpace') return 'ESP';
  if (e.clase === 'IfcWindow' || e.material === 'aluminio_vidrio') return 'VID';
  return e.disciplina;
}
const CUBETAS = ['ARQ', 'VID', 'ESP', 'EST', 'CIM', 'FIJO', 'DOT'];
const DISC_DE = { ARQ: 'ARQ', VID: 'ARQ', ESP: 'ARQ', EST: 'EST', CIM: 'CIM', FIJO: 'FIJO', DOT: 'DOT' };
// las cubiertas de piso y cielo (3 mm) no tienen sección que valga la pena; los espacios son volúmenes de aire
const sinTapa = (e) => e.clase === 'IfcSpace' || e.clase === 'IfcCovering';

export function colorElemento(e) {
  if (e.disciplina === 'EST' || e.disciplina === 'CIM') return COLOR_CLASE[e.clase] || '#a8a49a';
  if (e.disciplina === 'ARQ') return COLOR_MAT[e.material] || (e.clase === 'IfcSpace' ? '#7fb2d9' : '#d8d5cc');
  return COLOR_CLASE[e.clase] || '#cfd4d9';
}

// ------------------------------------------------------------------ sólidos: todo es un polígono extruido
// un sólido: { poli: [[a, b]…] (2D), o: [x, y, z], a1, a2 (ejes del polígono), d (dirección de extrusión), L, suave }
function solidos(g, out = []) {
  if (!g) return out;
  const t = g.tipo;
  if (t === 'caja') {
    const [x0, y0, z0] = g.min, [x1, y1, z1] = g.max;
    if (x1 - x0 > 1e-6 && y1 - y0 > 1e-6 && z1 - z0 > 1e-6) out.push({ poli: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], o: [0, 0, z0], a1: [1, 0, 0], a2: [0, 1, 0], d: [0, 0, 1], L: z1 - z0, plano: true });
  } else if (t === 'prisma') {
    if (g.z1 - g.z0 > 1e-6 && g.planta?.length >= 3) out.push({ poli: g.planta, o: [0, 0, g.z0], a1: [1, 0, 0], a2: [0, 1, 0], d: [0, 0, 1], L: g.z1 - g.z0, plano: true });
  } else if (t === 'cilindro') {
    const n = 20, [cx, cy] = g.centro, r = g.radio;
    out.push({ poli: Array.from({ length: n }, (_, k) => [cx + r * Math.cos((2 * Math.PI * k) / n), cy + r * Math.sin((2 * Math.PI * k) / n)]), o: [0, 0, g.z0], a1: [1, 0, 0], a2: [0, 1, 0], d: [0, 0, 1], L: g.z1 - g.z0, plano: true, suave: true, circulo: { cx, cy, r } });
  } else if (t === 'caja_girada') {
    const [cx, cy, z] = g.centro, [w, dd, h] = g.dim, c = Math.cos(g.rot || 0), s = Math.sin(g.rot || 0);
    const p = (u, v) => [cx + u * c - v * s, cy + u * s + v * c];
    out.push({ poli: [p(-w / 2, -dd / 2), p(w / 2, -dd / 2), p(w / 2, dd / 2), p(-w / 2, dd / 2)], o: [0, 0, z], a1: [1, 0, 0], a2: [0, 1, 0], d: [0, 0, 1], L: h, plano: true });
  } else if (t === 'perfil') {
    out.push({ poli: g.puntos, o: g.origen, a1: g.u, a2: g.v || cruz(g.w, g.u), d: g.w, L: g.largo });
  } else if (t === 'compuesta') (g.partes || []).forEach((p) => solidos(p, out));
  return out;
}
const cruz = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const area2 = (P) => { let s = 0; for (let i = 0; i < P.length; i++) { const a = P[i], b = P[(i + 1) % P.length]; s += a[0] * b[1] - b[0] * a[1]; } return s / 2; };
// punto del sólido (u, v en el polígono y t en la extrusión) en coordenadas del proyecto
const punto = (S, u, v, t) => [S.o[0] + u * S.a1[0] + v * S.a2[0] + t * S.d[0], S.o[1] + u * S.a1[1] + v * S.a2[1] + t * S.d[1], S.o[2] + u * S.a1[2] + v * S.a2[2] + t * S.d[2]];

// triangulación de un polígono simple; cada triángulo queda antihorario en (u, v)
function triangulos2D(P) {
  const T = THREE.ShapeUtils.triangulateShape(P.map(([u, v]) => new THREE.Vector2(u, v)), []);
  return T.map(([i, j, k]) => ((P[j][0] - P[i][0]) * (P[k][1] - P[i][1]) - (P[j][1] - P[i][1]) * (P[k][0] - P[i][0]) < 0 ? [i, k, j] : [i, j, k]));
}
// acumulador de triángulos (sin índices, normales planas) de una cubeta
class Acum {
  constructor() { this.p = []; this.n = []; this.c = []; this.e = []; }
  tri(a, b, c, col, eid, na, nb, nc) {
    let nx, ny, nz;
    if (!na) {
      const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
      nx = uy * vz - uz * vy; ny = uz * vx - ux * vz; nz = ux * vy - uy * vx;
      const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
    }
    for (const [q, nn] of [[a, na], [b, nb], [c, nc]]) {
      this.p.push(q[0], q[2], -q[1]);
      if (nn) this.n.push(nn[0], nn[2], -nn[1]); else this.n.push(nx, nz, -ny);
      this.c.push(col.r, col.g, col.b); this.e.push(eid);
    }
  }
  get vertices() { return this.e.length; }
}
// sólido → triángulos (tapas y caras laterales) y aristas
function triangular(S, acc, col, eid, aristas) {
  let P = S.poli;
  const ccw = area2(P) > 0;
  // la orientación del polígono en su plano define hacia dónde mira cada cara: se corrige con el signo de (a1 × a2) · d
  const sgn = Math.sign(cruz(S.a1, S.a2).reduce((s, v, i) => s + v * S.d[i], 0)) || 1;
  if (!ccw) P = [...P].reverse();
  const tris = triangulos2D(P);
  const abajo = P.map(([u, v]) => punto(S, u, v, 0)), arriba = P.map(([u, v]) => punto(S, u, v, S.L));
  for (const [i, j, k] of tris) {
    if (sgn > 0) { acc.tri(arriba[i], arriba[j], arriba[k], col, eid); acc.tri(abajo[i], abajo[k], abajo[j], col, eid); }
    else { acc.tri(arriba[i], arriba[k], arriba[j], col, eid); acc.tri(abajo[i], abajo[j], abajo[k], col, eid); }
  }
  const n = P.length, cen = S.circulo;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, a0 = abajo[i], b0 = abajo[j], a1 = arriba[i], b1 = arriba[j];
    if (cen) {
      const na = [(P[i][0] - cen.cx) / cen.r, (P[i][1] - cen.cy) / cen.r, 0], nb = [(P[j][0] - cen.cx) / cen.r, (P[j][1] - cen.cy) / cen.r, 0];
      acc.tri(a0, b0, b1, col, eid, na, nb, nb); acc.tri(a0, b1, a1, col, eid, na, nb, na);
    } else if (sgn > 0) { acc.tri(a0, b0, b1, col, eid); acc.tri(a0, b1, a1, col, eid); } else { acc.tri(a0, b1, b0, col, eid); acc.tri(a0, a1, b1, col, eid); }
  }
  if (aristas) {
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      aristas.seg(abajo[i], abajo[j], eid); aristas.seg(arriba[i], arriba[j], eid);
      if (!cen) {
        // aristas verticales solo en las esquinas (no entre tramos colineales de un perfil)
        const a = P[(i + n - 1) % n], b = P[i], c = P[j];
        const giro = Math.abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]));
        if (giro > 1e-6) aristas.seg(abajo[i], arriba[i], eid);
      }
    }
    if (cen) { aristas.seg(abajo[0], arriba[0], eid); aristas.seg(abajo[n >> 1], arriba[n >> 1], eid); }
  }
}
class AcumLineas {
  constructor() { this.p = []; this.e = []; }
  seg(a, b, eid) { this.p.push(a[0], a[2], -a[1], b[0], b[2], -b[1]); this.e.push(eid, eid); }
}

// ------------------------------------------------------------------ sombreado con el estado por elemento
const VERT_DECL = `attribute float eid;
uniform sampler2D tBimEst; uniform sampler2D tBimCol; uniform vec2 tBimTam;
varying vec4 vBimCol; varying vec4 vBimEst;`;
const VERT_LEER = `vec2 uvBim = vec2((mod(eid, tBimTam.x) + 0.5) / tBimTam.x, (floor(eid / tBimTam.x) + 0.5) / tBimTam.y);
vBimEst = texture2D(tBimEst, uvBim); vBimCol = texture2D(tBimCol, uvBim);`;
const VERT_OCULTAR = 'if (vBimEst.r < 0.5) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);';
const FRAG_DECL = 'varying vec4 vBimCol; varying vec4 vBimEst; uniform vec3 cBimSel; uniform vec3 cBim4D;';
const FRAG_COLOR = `diffuseColor.rgb = mix(diffuseColor.rgb, vBimCol.rgb, vBimCol.a);
diffuseColor.rgb = mix(diffuseColor.rgb, cBim4D, step(0.5, vBimEst.b) * 0.6);
diffuseColor.rgb = mix(diffuseColor.rgb, cBimSel, vBimEst.g * 0.45);`;
function conEstado(material, U, { lineas = false } = {}) {
  material.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = `${VERT_DECL}\n${sh.vertexShader}`.replace('#include <begin_vertex>', `#include <begin_vertex>\n${VERT_LEER}`).replace('#include <project_vertex>', `#include <project_vertex>\n${VERT_OCULTAR}`);
    let f = `${FRAG_DECL}\n${sh.fragmentShader}`.replace('#include <color_fragment>', `#include <color_fragment>\n${FRAG_COLOR}`);
    if (lineas) f = f.replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.a *= vBimEst.a;');
    else f = f.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += cBimSel * vBimEst.g * 0.35;');
    sh.fragmentShader = f;
  };
  material.customProgramCacheKey = () => (lineas ? 'bim-estado-lineas' : 'bim-estado');
  return material;
}

// tapa de corte: color por vértice y rayado a 45° en el plano del corte (coordenadas «hc» en metros)
function materialTapa() {
  return new THREE.ShaderMaterial({
    uniforms: { paso: { value: 0.16 } },
    vertexShader: `attribute vec3 color; attribute vec2 hc; varying vec3 vC; varying vec2 vH;
      #include <common>
      #include <logdepthbuf_pars_vertex>
      void main() { vC = color; vH = hc; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      #include <logdepthbuf_vertex>
      }`,
    fragmentShader: `uniform float paso; varying vec3 vC; varying vec2 vH;
      #include <logdepthbuf_pars_fragment>
      void main() {
      #include <logdepthbuf_fragment>
        float s = (vH.x + vH.y) / paso; float w = fwidth(s) * 1.2; float f = abs(fract(s) - 0.5);
        float raya = 1.0 - smoothstep(0.08, 0.08 + w, f);
        gl_FragColor = vec4(mix(vC, vC * 0.55, raya * 0.9), 1.0);
        #include <colorspace_fragment>
      }`,
    side: THREE.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
    extensions: { derivatives: true },
  });
}

// intervalos [a, b] donde la recta (coordenada k del polígono = c) corta el polígono, en la otra coordenada
function intervalos(P, k, c) {
  const o = 1 - k, xs = [];
  for (let i = 0; i < P.length; i++) {
    const a = P[i], b = P[(i + 1) % P.length];
    if ((a[k] <= c) !== (b[k] <= c)) xs.push(a[o] + ((c - a[k]) / (b[k] - a[k])) * (b[o] - a[o]));
  }
  xs.sort((p, q) => p - q);
  const out = [];
  for (let i = 0; i + 1 < xs.length; i += 2) if (xs[i + 1] - xs[i] > 1e-6) out.push([xs[i], xs[i + 1]]);
  return out;
}

// polígonos (puntos del proyecto) que deja un plano { tipo: 'h' | 'x' | 'y', c } al cortar los sólidos de un elemento; la
// tapa del corte en 3D y la sección del despiece en 2D salen de aquí
export const solidosDe = (geometria) => solidos(geometria);
export function poligonosCorte(sols, corte) {
  const out = [], t = corte.tipo, k = corte.c;
  for (const S of sols) {
    const vertical = S.d[2] === 1;
    if (t === 'h' && vertical) {
      if (S.o[2] < k && S.o[2] + S.L > k) out.push(S.poli.map(([x, y]) => [x, y, k]));
    } else if (vertical) {
      // plano vertical x = k (o y = k) contra un prisma vertical: intervalos de la planta × su altura
      const z0 = S.o[2], z1 = S.o[2] + S.L;
      for (const [a, b] of intervalos(S.poli, t === 'x' ? 0 : 1, k)) out.push(t === 'x' ? [[k, a, z0], [k, b, z0], [k, b, z1], [k, a, z1]] : [[a, k, z0], [b, k, z0], [b, k, z1], [a, k, z1]]);
    } else {
      // perfil extruido en horizontal (escaleras)
      const eje = t === 'h' ? 2 : t === 'x' ? 0 : 1;
      if (Math.abs(S.d[eje]) > 0.9) {
        // el plano corta la extrusión: el perfil entero, si la cota cae dentro del largo
        const t0 = (k - S.o[eje]) / S.d[eje];
        if (t0 > 0 && t0 < S.L) out.push(S.poli.map(([u, v]) => punto(S, u, v, t0)));
      } else {
        // el plano es paralelo a la extrusión: corta el perfil en una recta (en u o en v) → intervalos × el largo
        const ku = Math.abs(S.a1[eje]) > 0.9 ? 0 : 1, cu = (k - S.o[eje]) / (ku === 0 ? S.a1[eje] : S.a2[eje]);
        const uv = (s) => (ku === 0 ? [cu, s] : [s, cu]);
        for (const [a, b] of intervalos(S.poli, ku, cu)) out.push([punto(S, ...uv(a), 0), punto(S, ...uv(b), 0), punto(S, ...uv(b), S.L), punto(S, ...uv(a), S.L)]);
      }
    }
  }
  return out;
}

// ------------------------------------------------------------------ el modelo
// lista: [{ e }] en el orden de los índices globales (gi); opciones: { segmentos }
export function crearModelo3D(lista, { tier = 'media' } = {}) {
  const N = lista.length, W = 128, H = Math.max(1, Math.ceil(N / W));
  const est = new Uint8Array(W * H * 4), colr = new Uint8Array(W * H * 4);
  for (let i = 0; i < N; i++) { est[4 * i] = 255; est[4 * i + 3] = 255; }
  const tEst = new THREE.DataTexture(est, W, H, THREE.RGBAFormat), tCol = new THREE.DataTexture(colr, W, H, THREE.RGBAFormat);
  for (const t of [tEst, tCol]) { t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; }
  const U = { tBimEst: { value: tEst }, tBimCol: { value: tCol }, tBimTam: { value: new THREE.Vector2(W, H) }, cBimSel: { value: new THREE.Color('#e3141b') }, cBim4D: { value: new THREE.Color('#f0a020') } };
  const grupo = new THREE.Group(); grupo.name = 'bim_modelo';
  const planos = [];   // planos de recorte vigentes (el mismo arreglo en todos los materiales del modelo)

  // geometría por cubeta; rango de vértices de cada elemento (para el fantasma del refuerzo y la caja)
  const acc = Object.fromEntries(CUBETAS.map((c) => [c, new Acum()])), lin = new AcumLineas();
  const rango = new Int32Array(N * 3), rangoL = new Int32Array(N * 2), cajas = new Float32Array(N * 6), cub = new Array(N);
  const sol = new Array(N);
  const col = new THREE.Color();
  lista.forEach(({ e }, gi) => {
    const c = cubeta(e); cub[gi] = c;
    const S = solidos(e.geometria);
    sol[gi] = S;
    const a = acc[c], v0 = a.vertices, l0 = lin.e.length;
    col.set(colorElemento(e));   // THREE.Color guarda en lineal (el espacio de trabajo de three): va tal cual al atributo
    const conAristas = c !== 'ESP' && e.clase !== 'IfcCovering';
    for (const s of S) triangular(s, a, col, gi, conAristas ? lin : null);
    rango[3 * gi] = CUBETAS.indexOf(c); rango[3 * gi + 1] = v0; rango[3 * gi + 2] = a.vertices - v0;
    rangoL[2 * gi] = l0; rangoL[2 * gi + 1] = lin.e.length - l0;
    // caja del elemento (coordenadas del proyecto)
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (let k = v0; k < a.vertices; k++) {
      const x = a.p[3 * k], y = -a.p[3 * k + 2], z = a.p[3 * k + 1];
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; if (z < z0) z0 = z; if (z > z1) z1 = z;
    }
    if (!(x1 >= x0)) { x0 = y0 = z0 = x1 = y1 = z1 = 0; }
    cajas.set([x0, y0, z0, x1, y1, z1], 6 * gi);
  });
  const mats = {}, mallas = {};
  const segOpacidad = { VID: 0.38, ESP: 0.16 };
  for (const c of CUBETAS) {
    const a = acc[c];
    if (!a.vertices) continue;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(a.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(a.n, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(a.c, 3));
    g.setAttribute('eid', new THREE.Float32BufferAttribute(a.e, 1));
    g.computeBoundingSphere(); g.computeBoundingBox();
    const transp = c in segOpacidad;
    const m = conEstado(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: c === 'VID' ? 0.25 : 0.82, metalness: 0, transparent: transp, opacity: segOpacidad[c] ?? 1, depthWrite: !transp, side: c === 'ESP' ? THREE.DoubleSide : THREE.FrontSide, clippingPlanes: planos, clipShadows: true }), U);
    m.userData.opacidad0 = segOpacidad[c] ?? 1;
    const me = new THREE.Mesh(g, m);
    me.name = `bim_${c}`; me.receiveShadow = c !== 'ESP' && c !== 'VID'; me.castShadow = false;
    me.renderOrder = transp ? 2 : 0;
    me.userData.cubeta = c;
    mats[c] = m; mallas[c] = me; grupo.add(me);
    acc[c] = null;
  }
  const gL = new THREE.BufferGeometry();
  gL.setAttribute('position', new THREE.Float32BufferAttribute(lin.p, 3));
  gL.setAttribute('eid', new THREE.Float32BufferAttribute(lin.e, 1));
  gL.computeBoundingSphere();
  const matL = conEstado(new THREE.LineBasicMaterial({ color: '#2a2a28', transparent: true, opacity: 0.38, depthWrite: false, clippingPlanes: planos }), U, { lineas: true });
  const aristas = new THREE.LineSegments(gL, matL); aristas.name = 'bim_aristas'; aristas.renderOrder = 1;
  grupo.add(aristas);
  const posL = lin.p; // se guardan para la selección y el fantasma
  lin.p = null;

  // ---- estado
  const modoDisc = Object.fromEntries(DISCIPLINAS.map((d) => [d, 'normal']));
  const alfaDisc = { normal: 255, transparente: 70, oculta: 0 };
  let sucio = true;
  const E = {
    visible: (gi, v) => { est[4 * gi] = v ? 255 : 0; sucio = true; },
    esVisible: (gi) => est[4 * gi] > 127,
    sel: (gi, v) => { est[4 * gi + 1] = v; sucio = true; },
    fase: (gi, v) => { est[4 * gi + 2] = v ? 255 : 0; sucio = true; },
    color: (gi, c, a = 255) => { if (c) { colr[4 * gi] = Math.round(c.r * 255); colr[4 * gi + 1] = Math.round(c.g * 255); colr[4 * gi + 2] = Math.round(c.b * 255); } colr[4 * gi + 3] = c ? a : 0; sucio = true; },
    sinColor: () => { for (let i = 0; i < N; i++) colr[4 * i + 3] = 0; sucio = true; },
    sinSel: () => { for (let i = 0; i < N; i++) est[4 * i + 1] = 0; sucio = true; },
    sinFase: () => { for (let i = 0; i < N; i++) est[4 * i + 2] = 0; sucio = true; },
  };
  // los THREE.Color (tokens del tema o colores fijos) ya están en lineal, como lo que se mezcla en el sombreador
  E.colorSRGB = (gi, c, a = 255) => E.color(gi, c || null, a);

  function disciplina(d, modo) {
    modoDisc[d] = modo;
    for (const c of CUBETAS) {
      if (DISC_DE[c] !== d || !mats[c]) continue;
      const m = mats[c], tr = modo === 'transparente' || m.userData.opacidad0 < 1;
      m.transparent = tr; m.opacity = modo === 'transparente' ? Math.min(0.2, m.userData.opacidad0) : m.userData.opacidad0; m.depthWrite = !tr;
      m.needsUpdate = true;
      mallas[c].renderOrder = tr ? 2 : 0;
    }
    for (let i = 0; i < N; i++) if (DISC_DE[cub[i]] === d) est[4 * i + 3] = alfaDisc[modo];
    sucio = true;
  }
  // visibilidad final por elemento: la decide quien llama (bim.js) con filtro(gi) → bool; aquí se aplica la de disciplina
  function aplicarVisibles(filtro) {
    for (let i = 0; i < N; i++) est[4 * i] = modoDisc[DISC_DE[cub[i]]] !== 'oculta' && filtro(i) ? 255 : 0;
    sucio = true;
  }
  function subir() {
    if (!sucio) return false;
    sucio = false;
    tEst.needsUpdate = true; tCol.needsUpdate = true;
    // una cubeta sin nada a la vista no se dibuja (ni gasta su llamada)
    const hay = Object.fromEntries(CUBETAS.map((c) => [c, false]));
    let lineas = false;
    for (let i = 0; i < N; i++) if (est[4 * i] > 127) { hay[cub[i]] = true; if (rangoL[2 * i + 1]) lineas = true; }
    for (const c of CUBETAS) if (mallas[c]) mallas[c].visible = hay[c] && modoDisc[DISC_DE[c]] !== 'oculta';
    aristas.visible = lineas;
    if (corte) tapas();
    return true;
  }

  // ---- cortes con tapa
  let corte = null, tapa = null, conTapa = null;   // conTapa(gi): elementos que llevan tapa aunque estén ocultos (el fantasma)
  const matTapa = materialTapa();
  function plano(cfg) {
    if (cfg.tipo === 'h') return new THREE.Plane(new THREE.Vector3(0, -1, 0), cfg.c);
    if (cfg.tipo === 'x') return cfg.lado < 0 ? new THREE.Plane(new THREE.Vector3(-1, 0, 0), cfg.c) : new THREE.Plane(new THREE.Vector3(1, 0, 0), -cfg.c);
    return cfg.lado < 0 ? new THREE.Plane(new THREE.Vector3(0, 0, 1), cfg.c) : new THREE.Plane(new THREE.Vector3(0, 0, -1), -cfg.c);
  }
  function cortar(cfg, extra = null) {
    corte = cfg; conTapa = extra;
    planos.length = 0;
    if (cfg) planos.push(plano(cfg));
    for (const m of [...Object.values(mats), matL]) m.needsUpdate = true;
    sucio = true;
    if (!cfg && tapa) { grupo.remove(tapa); tapa.geometry.dispose(); tapa = null; }
    subir();
    return planos[0] || null;
  }
  // polígonos de la sección de cada sólido con el plano vigente → malla de la tapa
  function tapas() {
    if (tapa) { grupo.remove(tapa); tapa.geometry.dispose(); tapa = null; }
    if (!corte) return;
    const p = [], c = [], h = [], cc = new THREE.Color(), t = corte.tipo, k = corte.c;
    const hcDe = (q) => (t === 'h' ? [q[0], q[1]] : t === 'x' ? [q[1], q[2]] : [q[0], q[2]]);
    for (let gi = 0; gi < N; gi++) {
      if (!(est[4 * gi] > 127 || conTapa?.(gi))) continue;
      const e = lista[gi].e;
      if (sinTapa(e) || modoDisc[DISC_DE[cub[gi]]] === 'transparente' && !conTapa?.(gi)) continue;
      const b = 6 * gi, ax = t === 'h' ? 2 : t === 'x' ? 0 : 1;
      if (!(cajas[b + ax] < k && cajas[b + 3 + ax] > k)) continue;
      cc.set(esConcreto(e) ? TAPA.concreto : esMamposteria(e) ? TAPA.mamposteria : TAPA.otro);
      for (const pol of poligonosCorte(sol[gi], corte)) {
        const P2 = pol.map(hcDe);
        for (const [i, j, m] of triangulos2D(P2)) for (const q of [i, j, m]) { const X = pol[q]; p.push(X[0], X[2], -X[1]); c.push(cc.r, cc.g, cc.b); h.push(P2[q][0], P2[q][1]); }
      }
    }
    if (!p.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    g.setAttribute('hc', new THREE.Float32BufferAttribute(h, 2));
    g.computeBoundingSphere();
    tapa = new THREE.Mesh(g, matTapa); tapa.name = 'bim_tapa'; tapa.renderOrder = 1;
    grupo.add(tapa);
  }

  // ---- selección: aristas del elemento elegido en el color de acento (sobre el modelo)
  let selL = null;
  const matSel = new THREE.LineBasicMaterial({ color: '#e3141b', depthTest: false, transparent: true, opacity: 0.95, clippingPlanes: planos });
  function aristasDe(gis) {
    const p = [];
    for (const gi of gis) { const [l0, n] = [rangoL[2 * gi], rangoL[2 * gi + 1]]; for (let k = l0; k < l0 + n; k++) p.push(posL[3 * k], posL[3 * k + 1], posL[3 * k + 2]); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.computeBoundingSphere();
    return g;
  }
  function resaltar(gis) {
    if (selL) { grupo.remove(selL); selL.geometry.dispose(); selL = null; }
    if (!gis?.length) return;
    selL = new THREE.LineSegments(aristasDe(gis), matSel); selL.renderOrder = 5; selL.name = 'bim_sel';
    grupo.add(selL);
  }

  // ---- fantasma: copia transparente de unos elementos (el concreto alrededor del refuerzo) con sus aristas
  function fantasma(gis, { opacidad = 0.16 } = {}) {
    const p = [], n = [], cc = [];
    const geos = Object.fromEntries(Object.entries(mallas).map(([k, m]) => [k, m.geometry]));
    for (const gi of gis) {
      const g = geos[CUBETAS[rango[3 * gi]]];
      if (!g) continue;
      const P = g.attributes.position.array, Nn = g.attributes.normal.array, Cc = g.attributes.color.array, v0 = rango[3 * gi + 1], nv = rango[3 * gi + 2];
      for (let k = v0; k < v0 + nv; k++) { p.push(P[3 * k], P[3 * k + 1], P[3 * k + 2]); n.push(Nn[3 * k], Nn[3 * k + 1], Nn[3 * k + 2]); cc.push(Cc[3 * k], Cc[3 * k + 1], Cc[3 * k + 2]); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(n, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(cc, 3));
    g.computeBoundingSphere();
    const m = new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: opacidad, depthWrite: false, roughness: 0.9, side: THREE.DoubleSide, clippingPlanes: planos });
    const malla = new THREE.Mesh(g, m); malla.renderOrder = 3;
    const l = new THREE.LineSegments(aristasDe(gis), new THREE.LineBasicMaterial({ color: '#3b3b38', transparent: true, opacity: 0.55, depthWrite: false, clippingPlanes: planos }));
    l.renderOrder = 3;
    const fg = new THREE.Group(); fg.name = 'bim_fantasma'; fg.add(malla, l);
    fg.userData.dispose = () => { g.dispose(); m.dispose(); l.geometry.dispose(); l.material.dispose(); };
    return fg;
  }

  // ---- selección con el puntero: el primer impacto en un elemento visible y del lado que deja el corte
  const _p = new THREE.Vector3();
  function pick(ray) {
    const objs = Object.values(mallas).filter((m) => m.visible && m.userData.cubeta !== 'ESP');
    const hits = ray.intersectObjects(objs, false);
    for (const h of hits) {
      const gi = h.object.geometry.attributes.eid.getX(h.face.a);
      if (est[4 * gi] < 128) continue;
      if (planos.length && planos[0].distanceToPoint(_p.copy(h.point)) < 0) continue;
      return { gi, punto: h.point.clone() };
    }
    return null;
  }

  // caja (three) de un conjunto de elementos
  function caja(gis) {
    const b = new THREE.Box3();
    for (const gi of gis) { const o = 6 * gi; b.expandByPoint(new THREE.Vector3(cajas[o], cajas[o + 2], -cajas[o + 1])); b.expandByPoint(new THREE.Vector3(cajas[o + 3], cajas[o + 5], -cajas[o + 4])); }
    return b;
  }
  const cajaProyecto = (gi) => Array.from(cajas.subarray(6 * gi, 6 * gi + 6));

  function tema(t) { U.cBimSel.value.copy(t.accent); matSel.color.copy(t.accent); U.cBim4D.value.copy(t.warn); }

  function dispose() {
    for (const m of Object.values(mallas)) { m.geometry.dispose(); m.material.dispose(); }
    gL.dispose(); matL.dispose(); matTapa.dispose(); matSel.dispose(); tEst.dispose(); tCol.dispose();
    if (tapa) tapa.geometry.dispose();
    if (selL) selL.geometry.dispose();
  }
  const triangulos = () => Object.values(mallas).reduce((s, m) => s + m.geometry.attributes.position.count / 3, 0);
  return {
    grupo, N, E, planos, disciplina, modoDisc, aplicarVisibles, subir, cortar, corte: () => corte, plano: () => planos[0] || null, resaltar, fantasma, pick, caja, cajaProyecto,
    tema, dispose, triangulos, mallas, aristas, cubetaDe: (gi) => cub[gi], disciplinaDe: (gi) => DISC_DE[cub[gi]], tapa: () => tapa,
  };
}

// ------------------------------------------------------------------ terreno: opaco, semitransparente o cortado alrededor de la cimentación
// El suelo de la escena (CircleGeometry) y los «entorno» de los modelos del sitio son de torre.js: aquí solo se les cambia el
// material por una copia mientras dure el modo, y se devuelve el original al salir (como hace el recorrido con su visibilidad)
export function crearTerreno(st, { hueco, fondo = -18 }) {
  const grupo = new THREE.Group(); grupo.name = 'bim_terreno';
  let modo = 'opaco';
  // material original de cada malla tocada: el vigente cuando se le puso la copia (si el sitio lo cambia, se toma el nuevo)
  const originales = new Map();
  // las mallas se buscan en cada cambio y se vigilan mientras el terreno no esté opaco: el suelo del sitio (grupo
  // «entorno» de los modelos del exterior) puede llegar o rehacerse después de entrar a la cimentación
  const buscar = () => {
    const L = st.scene.children.filter((o) => o.isMesh && o.geometry?.type === 'CircleGeometry');
    st.scene.traverse((o) => { if (o.name === 'entorno') o.traverse((q) => { if (q.isMesh && !L.includes(q)) L.push(q); }); });
    return L;
  };
  // hueco: rectángulo del proyecto [x0, y0, x1, y1]; planos cuyo lado negativo es el interior (clipIntersection). Del lado
  // que da a la cámara el hueco se abre 30 m (el plano se corre): el borde cercano de la excavación no tapa los pilotes
  const [x0, y0, x1, y1] = hueco, ABRE = 30;
  const planosHueco = [new THREE.Plane(new THREE.Vector3(-1, 0, 0), x0), new THREE.Plane(new THREE.Vector3(1, 0, 0), -x1), new THREE.Plane(new THREE.Vector3(0, 0, 1), y0), new THREE.Plane(new THREE.Vector3(0, 0, -1), -y1)];
  function abrirHaciaCamara() {
    const c = st.camera.position, px = c.x, py = -c.z;
    const k = [x0 - (px < x0 ? ABRE : 0), -(x1 + (px > x1 ? ABRE : 0)), y0 - (py < y0 ? ABRE : 0), -(y1 + (py > y1 ? ABRE : 0))];
    let cambio = false;
    planosHueco.forEach((q, i) => { if (q.constant !== k[i]) { q.constant = k[i]; cambio = true; } });
    return cambio;
  }
  // foso de la excavación: caja vista por dentro (BackSide): se ven las paredes del fondo y el piso, nunca las de adelante
  const gF = new THREE.BoxGeometry(x1 - x0, -fondo, y1 - y0);
  const cF = [], pos = gF.attributes.position, ccol = new THREE.Color(), arriba = new THREE.Color('#c9b08a'), abajo = new THREE.Color('#9a7f5c');
  for (let i = 0; i < pos.count; i++) { const s = (pos.getY(i) + -fondo / 2) / -fondo; ccol.copy(abajo).lerp(arriba, s); cF.push(ccol.r, ccol.g, ccol.b); }
  gF.setAttribute('color', new THREE.Float32BufferAttribute(cF, 3));
  const foso = new THREE.Mesh(gF, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.BackSide, roughness: 1 }));
  foso.position.set((x0 + x1) / 2, fondo / 2 - 0.07, -(y0 + y1) / 2); foso.name = 'bim_foso';
  grupo.add(foso);
  const esCopia = (mt) => (Array.isArray(mt) ? mt.length > 0 && mt.every((q) => q?.userData?.bimCopia) : !!mt?.userData?.bimCopia);
  const liberar = (mt) => [].concat(mt).forEach((q) => { if (q?.userData?.bimCopia) q.dispose(); });
  const copia = (mm, m) => {
    const c = mm.clone();
    if (m === 'semi') Object.assign(c, { transparent: true, opacity: 0.3, depthWrite: false });
    else Object.assign(c, { clippingPlanes: planosHueco, clipIntersection: true, side: THREE.DoubleSide });
    c.userData.bimCopia = true; c.userData.bimModo = m;
    return c;
  };
  function aplicarA(o, m) {
    if (!esCopia(o.material)) originales.set(o, o.material);
    const orig = originales.get(o);
    if (esCopia(o.material)) liberar(o.material);
    if (m === 'opaco') { o.material = orig; originales.delete(o); return; }
    o.material = Array.isArray(orig) ? orig.map((q) => copia(q, m)) : copia(orig, m);
  }
  const modoDe = (o) => [].concat(o.material)[0]?.userData?.bimModo;
  function poner(m) {
    modo = m;
    const L = buscar(), vivas = new Set(L);
    for (const [o, orig] of [...originales]) if (!vivas.has(o)) { if (esCopia(o.material)) { liberar(o.material); o.material = orig; } originales.delete(o); }
    if (m === 'cortado') abrirHaciaCamara();
    for (const o of L) aplicarA(o, m);
    grupo.visible = m === 'cortado';
    st.invalidate(true);
  }
  // vigilancia mientras el terreno no está opaco: el hueco sigue a la cámara y las mallas nuevas o rehechas reciben su copia
  let tUlt = -1;
  const vigilar = (_dt, t) => {
    if (modo === 'opaco') return false;
    let cambio = modo === 'cortado' && abrirHaciaCamara();
    if (t - tUlt > 0.5) {
      tUlt = t;
      for (const o of buscar()) if (!esCopia(o.material) || modoDe(o) !== modo) { aplicarA(o, modo); cambio = true; }
    }
    return cambio;
  };
  st.onFrame(vigilar);
  function restaurar() {
    for (const [o, orig] of originales) { if (esCopia(o.material)) { liberar(o.material); o.material = orig; } }
    originales.clear(); modo = 'opaco'; grupo.visible = false;
  }
  // ¿el punto (three) cae en el hueco recortado del suelo?
  const enHueco = (p) => modo === 'cortado' && planosHueco.every((q) => q.distanceToPoint(p) < 0);
  grupo.visible = false;
  return {
    grupo, poner, restaurar, modo: () => modo, mallas: buscar, enHueco, esCopia,
    dispose() { restaurar(); const k = st.frameFns?.indexOf(vigilar) ?? -1; if (k >= 0) st.frameFns.splice(k, 1); gF.dispose(); foso.material.dispose(); },
  };
}
