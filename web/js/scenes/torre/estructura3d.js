// Estructura de la torre en 3D para la vista sísmica (equipo D; especificación de integración, 8.3).
// Dibuja lo que calculó el motor (Resultados, 7.6) en el paso i del deslizador, sin animación propia:
//  · columnas, vigas y muros de concreto como líneas gruesas (LineSegments2) de 8 tramos por elemento. La posición de
//    cada tramo sale de los desplazamientos del diafragma de cada nivel (ux, uy, rz en el centro de masa, con la
//    compatibilidad del 7.4: dx = ux − (y − yc)·rz, dy = uy + (x − xc)·rz), de los giros de los nodos en su pórtico y del
//    desplazamiento vertical de los nodos, interpolados con los polinomios de Hermite; la rotación plástica de una
//    rótula se resta del giro del nodo en ese extremo, así el quiebre se ve. Una sola columna física por eje: en x usa
//    su pórtico X y en y su pórtico Y;
//  · color por demanda/capacidad del elemento en ese paso (|M|/Mn esperado, |V|/Vn esperado, θp/θp de ocupación
//    inmediata o el máximo de los tres). En una columna física, la combinación de sus dos pórticos con el contorno de
//    Bresler de α = 1,5 (aproximación para mostrar; estimación);
//  · losas de cada nivel como placas que se mueven como cuerpo rígido (el diafragma rígido es la hipótesis del modelo);
//  · rótulas que fluyeron como esferas en los extremos (tamaño ∝ θp/θp de ocupación inmediata) con un anillo del color
//    del nivel de desempeño superado (IO, LS, CP);
//  · muros de mampostería como paneles con el color del daño que alcanzaron; la estructura sin deformar en gris fino;
//  · deriva vectorial de cada entrepiso en ese paso, en una etiqueta por nivel;
//  · equipos de la dotación del piso elegido sobre su losa (cajas que se mueven con ella), coloreados por lo que calculó
//    el motor, con un anillo en el piso de radio = media diagonal de su huella + lo que deslizaron (a escala real).
// La geometría se crea una vez; en cada paso se escriben los arreglos existentes (instanceStart.data.array.set(…) y
// needsUpdate), nunca setPositions() (crea búferes nuevos en three 0.160).
import { THREE } from '../../core.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';

export const TRAMOS = 8;
// cortes de la leyenda de demanda/capacidad (8.3): ≤ 0,5 · 0,5-0,8 · 0,8-1,0 · > 1,0
export const CORTES_DC = [0.5, 0.8, 1.0];
// estados de daño de la mampostería en orden (7.6)
export const ESTADOS_MURO = ['sin_dano', 'leve', 'moderado', 'extenso', 'colapso'];
const H = [(s) => 1 - 3 * s * s + 2 * s * s * s, (s) => s - 2 * s * s + s * s * s, (s) => 3 * s * s - 2 * s * s * s, (s) => -s * s + s * s * s];
const HT = Array.from({ length: TRAMOS + 1 }, (_, q) => H.map((f) => f(q / TRAMOS)));   // tabla de Hermite por punto

// paleta de la leyenda a partir de los tokens del tema
export function paletaDC(c) {
  return [c.good.clone(), c.good.clone().lerp(c.warn, 0.5), c.warn.clone(), c.bad.clone()];
}
export function paletaMuro(c) {
  return [c.good.clone(), c.good.clone().lerp(c.warn, 0.5), c.warn.clone(), c.warn.clone().lerp(c.bad, 0.5), c.bad.clone()];
}
export const binDC = (v) => (v <= CORTES_DC[0] ? 0 : v <= CORTES_DC[1] ? 1 : v <= CORTES_DC[2] ? 2 : 3);

// info: { elementos, nodos (de «listo»), niveles: [{ z, cm: [x, y], contorno: [[x, y]…], h }], nivelNodo: Int16Array(nN)
//         (0 = base; k = 1…N nivel global), porticos: { id: { direccion } }, secciones: { id: sección }, elemSeccion: [id],
//         muros: [{ id, a: [x, y], b: [x, y], k, h, hEntrepiso, aislado, estados: [{ nombre, deriva }] }] }
// opciones: tier ('baja' | 'media' | 'alta'), colores (tokens()), renderer, etiqueta(html, pos, padre) → CSS2DObject
export function crearEstructura3D(info, { tier = 'media', colores, renderer, etiqueta } = {}) {
  const { elementos, nodos, niveles, nivelNodo, porticos = {}, secciones = {}, muros = [] } = info;
  const nE = elementos.length, nN = nodos.length, N = niveles.length;
  const idxNodo = new Map(nodos.map((n, k) => [n.id, k]));
  const idxElem = new Map(elementos.map((e, k) => [e.id, k]));
  const dirDe = (p) => porticos[p]?.direccion || (/^[MV]?X|^X/i.test(String(p)) ? 'x' : 'y');
  const grupo = new THREE.Group();
  grupo.name = 'estructura_sismo';
  let col = colores, pal = paletaDC(col), palM = paletaMuro(col);

  // ------------------------------------------------------------ elementos dibujados (columnas físicas fundidas)
  const dib = [], porFisico = new Map(), elemDib = new Int32Array(nE).fill(-1);
  elementos.forEach((e, k) => {
    const [xi, yi, zi] = e.xyz_i, [xj, yj, zj] = e.xyz_j;
    const vertical = Math.abs(zj - zi) > Math.hypot(xj - xi, yj - yi);
    const tipo = e.tipo === 'muro_concreto' ? 'muro' : vertical ? 'columna' : 'viga';
    let d = tipo === 'columna' && e.fisico ? porFisico.get(e.fisico) : null;
    if (!d) {
      const iAbajo = !vertical || zi <= zj;
      d = { id: e.id, tipo, A: iAbajo ? e.xyz_i : e.xyz_j, B: iAbajo ? e.xyz_j : e.xyz_i, planos: {}, elems: [], vertical };
      d.L = vertical ? d.B[2] - d.A[2] : 0;
      d.dir = vertical ? null : Math.abs(xj - xi) >= Math.abs(yj - yi) ? 'x' : 'y';
      dib.push(d);
      if (tipo === 'columna' && e.fisico) porFisico.set(e.fisico, d);
    }
    const dir = vertical ? dirDe(e.portico) : d.dir, ni = idxNodo.get(e.i) ?? -1, nj = idxNodo.get(e.j) ?? -1;
    const iEnA = vertical ? Math.abs(zi - d.A[2]) <= Math.abs(zj - d.A[2]) : true;
    if (!d.planos[dir]) d.planos[dir] = { k, nA: iEnA ? ni : nj, nB: iEnA ? nj : ni, extA: iEnA ? 0 : 1, extB: iEnA ? 1 : 0 };
    d.elems.push(k);
    elemDib[k] = dib.indexOf(d);
  });
  dib.forEach((d) => {
    const p = d.planos.x || d.planos.y;
    d.nA = p.nA; d.nB = p.nB;
    d.kA = d.nA >= 0 ? nivelNodo[d.nA] : 0; d.kB = d.nB >= 0 ? nivelNodo[d.nB] : 0;
    if (!d.vertical) d.Ls = d.dir === 'x' ? d.B[0] - d.A[0] : d.B[1] - d.A[1];
  });
  const lin = dib.map((d, q) => q).filter((q) => dib[q].tipo !== 'muro'), mur = dib.map((d, q) => q).filter((q) => dib[q].tipo === 'muro');
  const P = TRAMOS + 1, pts = new Float32Array(dib.length * P * 3);   // puntos dibujados (coordenadas de three)

  // ------------------------------------------------------------ líneas (LineSegments2): geometría fija, arreglos reescritos
  const capaLineas = (lista, ancho) => {
    const g = new LineSegmentsGeometry();
    g.setPositions(new Float32Array(Math.max(1, lista.length) * TRAMOS * 6));
    g.setColors(new Float32Array(Math.max(1, lista.length) * TRAMOS * 6));
    const m = new LineMaterial({ linewidth: ancho, vertexColors: true, worldUnits: false, toneMapped: false });
    const o = new LineSegments2(g, m);
    o.frustumCulled = false;
    o.visible = lista.length > 0;
    grupo.add(o);
    return { o, g, m, lista, pos: g.attributes.instanceStart.data, colr: g.attributes.instanceColorStart.data };
  };
  const anchoBase = tier === 'baja' ? 2.5 : 3;
  const capas = [capaLineas(lin, anchoBase), capaLineas(mur, anchoBase * 2.4)];
  // resaltado del elemento elegido (encima de todo)
  const sel = capaLineas([0], anchoBase * 2.6);
  // el elegido va en el color de los datos (violeta): el rojo ya dice «supera la capacidad»
  sel.m.vertexColors = false; sel.m.color.copy(col.data); sel.m.depthTest = false; sel.o.renderOrder = 10; sel.o.visible = false;
  let elegido = -1;

  // fantasma sin deformar
  const fant = new Float32Array(dib.length * 6);
  dib.forEach((d, q) => fant.set([d.A[0], d.A[2], -d.A[1], d.B[0], d.B[2], -d.B[1]], q * 6));
  const gFant = new THREE.BufferGeometry(); gFant.setAttribute('position', new THREE.BufferAttribute(fant, 3));
  const mFant = new THREE.LineBasicMaterial({ color: col.muted, transparent: true, opacity: 0.55, toneMapped: false });
  const fantasma = new THREE.LineSegments(gFant, mFant); fantasma.frustumCulled = false; grupo.add(fantasma);

  // ------------------------------------------------------------ losas: una placa y su borde por nivel
  const mLosa = new THREE.MeshBasicMaterial({ color: col.muted, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  const mBorde = new THREE.LineBasicMaterial({ color: col.ink, transparent: true, opacity: 0.55, toneMapped: false });
  const losas = niveles.map((nv) => {
    const c = nv.contorno?.length >= 3 ? nv.contorno : null;
    const o = new THREE.Group(); o.matrixAutoUpdate = false; grupo.add(o);
    if (c) {
      const sh = new THREE.Shape(c.map(([x, y]) => new THREE.Vector2(x, y)));
      const g = new THREE.ShapeGeometry(sh); g.rotateX(-Math.PI / 2); g.translate(0, nv.z, 0);
      const placa = new THREE.Mesh(g, mLosa); placa.renderOrder = 1; o.add(placa);
      const b = new THREE.BufferGeometry().setFromPoints(c.map(([x, y]) => new THREE.Vector3(x, nv.z, -y)));
      o.add(new THREE.LineLoop(b, mBorde));
    }
    return o;
  });
  const _m = new THREE.Matrix4();
  // matriz lineal del diafragma (misma cinemática que las líneas, sin aproximar el giro de otra manera)
  const matrizNivel = (k, ux, uy, rz, e, out) => {
    if (k <= 0) return out.identity();
    const [cx, cy] = niveles[k - 1].cm;
    return out.set(1, 0, e * rz, e * (ux + rz * cy), 0, 1, 0, 0, -e * rz, 0, 1, -e * uy + e * rz * cx, 0, 0, 0, 1);
  };

  // ------------------------------------------------------------ rótulas: esferas instanciadas y anillos de nivel
  const capRot = Math.max(1, dib.length * 2);
  const diag = Math.hypot(...['x', 'y', 'z'].map((_, a) => { let lo = Infinity, hi = -Infinity; dib.forEach((d) => { for (const p of [d.A, d.B]) { lo = Math.min(lo, p[a]); hi = Math.max(hi, p[a]); } }); return hi - lo || 1; }));
  const r0 = THREE.MathUtils.clamp(diag * 0.007, 0.06, 0.32);
  const mEsf = new THREE.MeshBasicMaterial({ color: col.ink, toneMapped: false });
  const esferas = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, tier === 'baja' ? 0 : 1), mEsf, capRot);
  const anillos = new THREE.InstancedMesh(new THREE.TorusGeometry(1, 0.2, 4, tier === 'baja' ? 10 : 16).rotateX(Math.PI / 2), new THREE.MeshBasicMaterial({ toneMapped: false }), capRot);
  for (let q = 0; q < capRot; q++) anillos.setColorAt(q, new THREE.Color(1, 1, 1));
  esferas.count = anillos.count = 0;
  esferas.frustumCulled = anillos.frustumCulled = false;
  esferas.renderOrder = anillos.renderOrder = 5;
  grupo.add(esferas, anillos);

  // ------------------------------------------------------------ muros de mampostería (paneles, una malla)
  const nM = muros.length;
  const gMur = new THREE.BufferGeometry();
  const posM = new Float32Array(Math.max(1, nM) * 6 * 3), colM = new Float32Array(Math.max(1, nM) * 6 * 3);
  gMur.setAttribute('position', new THREE.BufferAttribute(posM, 3)); gMur.setAttribute('color', new THREE.BufferAttribute(colM, 3));
  const mMur = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false, toneMapped: false });
  const panelM = new THREE.Mesh(gMur, mMur); panelM.frustumCulled = false; panelM.visible = nM > 0; panelM.renderOrder = 2; grupo.add(panelM);

  // ------------------------------------------------------------ equipos de la dotación (cajas instanciadas)
  // los que deslizaron llevan en el piso un anillo de radio = media diagonal de su huella + lo que deslizaron (a escala
  // real: el motor da cuánto deslizó, no hacia dónde)
  let equipos = [], cajas = null, anillosEq = null, conAnillo = [];
  const mCaja = new THREE.MeshLambertMaterial({ toneMapped: false });
  const mAnilloEq = new THREE.MeshBasicMaterial({ color: col.warn, side: THREE.DoubleSide, toneMapped: false });

  // ------------------------------------------------------------ etiquetas de deriva por entrepiso
  // en el vértice del suroriente de cada nivel; la caja se abre hacia el occidente (hacia el edificio), así no se sale
  // del recuadro cuando la torre lo llena (la cámara mira desde el suroccidente)
  const etiquetas = [];
  if (etiqueta) niveles.forEach((nv, k) => {
    const c = nv.contorno?.length ? nv.contorno : [nv.cm];
    const v = c.reduce((a, p) => (p[0] - p[1] > a[0] - a[1] ? p : a), c[0]);
    const o = etiqueta('<span class="lbl-node"></span>', [v[0] + 0.5, nv.z, -v[1] + 0.5], grupo);
    o.userData.k = k; etiquetas.push(o);
  });

  // ------------------------------------------------------------ estado del resultado (cachés por Resultados)
  let R = null, thpPos = null, K = 0, acum = null, estMuro = null, actual = { i: -1, escala: 1, campo: 'dc' };
  function preparar(Rn) {
    R = Rn;
    thpPos = new Int32Array(nE).fill(-1);
    const L = R.thp?.elementos || [];
    K = L.length;
    for (let q = 0; q < K; q++) thpPos[L[q]] = q;
    // bits de rótulas acumulados (O lógico hasta cada paso): una rótula que fluyó queda marcada
    const nt = R.t.length;
    acum = new Uint8Array(nt * nE);
    if (R.rotulas) for (let i = 0; i < nt; i++) for (let k = 0; k < nE; k++) acum[i * nE + k] = R.rotulas[i * nE + k] | (i ? acum[(i - 1) * nE + k] : 0);
    // estado acumulado de cada muro de mampostería con la deriva en su plano (desde el diafragma); en el último paso,
    // el que dio el motor (que lo evalúa en cada Δt)
    estMuro = new Uint8Array(Math.max(1, nt * nM));
    const finales = new Map((R.muros_mamposteria || []).map((m) => [m.id, ESTADOS_MURO.indexOf(m.estado)]));
    muros.forEach((w, q) => {
      let maxD = 0;
      const ux = (w.b[0] - w.a[0]), uy = (w.b[1] - w.a[1]), l = Math.hypot(ux, uy) || 1, mx = (w.a[0] + w.b[0]) / 2, my = (w.a[1] + w.b[1]) / 2;
      for (let i = 0; i < nt; i++) {
        const [ax, ay] = desp(i, w.k, mx, my, 1), [bx, by] = desp(i, w.k - 1, mx, my, 1);
        const dr = Math.abs(((ax - bx) * ux + (ay - by) * uy) / l) / (w.hEntrepiso || w.h || 1);
        maxD = Math.max(maxD, dr);
        let s = 0; (w.estados || []).forEach((e, j) => { if (maxD >= e.deriva) s = Math.max(s, (ESTADOS_MURO.indexOf(e.nombre) + 1) || j + 1); });
        if (i === nt - 1 && finales.has(w.id)) s = Math.max(s, finales.get(w.id));
        estMuro[i * nM + q] = s;
      }
    });
  }
  const NL = () => R.u.length / R.t.length / 3;
  // desplazamiento en planta (x, y del marco de la especificación) de un punto del nivel k en el paso i
  function desp(i, k, x, y, e) {
    if (k <= 0 || k > N) return [0, 0];
    const o = (i * NL() + (k - 1)) * 3, ux = R.u[o], uy = R.u[o + 1], rz = R.u[o + 2], [cx, cy] = niveles[k - 1].cm;
    return [e * (ux - (y - cy) * rz), e * (uy + (x - cx) * rz)];
  }
  const tp = (k, ext, i) => { const q = thpPos[k]; return q < 0 ? 0 : R.thp.valores[(i * K + q) * 2 + ext] * 1e-5; };
  const giro = (n, i) => (n >= 0 && R.giros ? R.giros[i * nN + n] : 0);
  const vNodo = (n, i) => (n >= 0 && R.v_nodos ? R.v_nodos[i * nN + n] : 0);

  // puntos deformados del elemento dibujado q en el paso i (exageración e)
  function puntos(q, i, e) {
    const d = dib[q], o = q * P * 3, [xA, yA, zA] = d.A, [xB, yB, zB] = d.B;
    const [dxA, dyA] = desp(i, d.kA, xA, yA, e), [dxB, dyB] = desp(i, d.kB, xB, yB, e);
    const vA = e * vNodo(d.nA, i), vB = e * vNodo(d.nB, i);
    if (d.vertical) {
      // pendiente lateral dw/dz = −θ (giro antihorario en el plano s–z de cada pórtico), sin la rotación plástica
      const px = d.planos.x, py = d.planos.y, L = d.L;
      const sx = px ? [-(giro(px.nA, i) - tp(px.k, px.extA, i)) * e * L, -(giro(px.nB, i) - tp(px.k, px.extB, i)) * e * L] : null;
      const sy = py ? [-(giro(py.nA, i) - tp(py.k, py.extA, i)) * e * L, -(giro(py.nB, i) - tp(py.k, py.extB, i)) * e * L] : null;
      for (let s = 0; s < P; s++) {
        const [h1, h2, h3, h4] = HT[s], f = s / TRAMOS;
        const wx = sx ? h1 * dxA + h2 * sx[0] + h3 * dxB + h4 * sx[1] : dxA + (dxB - dxA) * f;
        const wy = sy ? h1 * dyA + h2 * sy[0] + h3 * dyB + h4 * sy[1] : dyA + (dyB - dyA) * f;
        const x = xA + (xB - xA) * f + wx, y = yA + (yB - yA) * f + wy, z = zA + (zB - zA) * f + vA + (vB - vA) * f;
        pts[o + s * 3] = x; pts[o + s * 3 + 1] = z; pts[o + s * 3 + 2] = -y;
      }
    } else {
      // viga: en planta, lineal entre los extremos (diafragma); en vertical, Hermite con dv/ds = θ − θp
      const p = d.planos[d.dir], Ls = d.Ls;
      const tA = (giro(p.nA, i) - tp(p.k, p.extA, i)) * e * Ls, tB = (giro(p.nB, i) - tp(p.k, p.extB, i)) * e * Ls;
      for (let s = 0; s < P; s++) {
        const [h1, h2, h3, h4] = HT[s], f = s / TRAMOS;
        const x = xA + (xB - xA) * f + dxA + (dxB - dxA) * f, y = yA + (yB - yA) * f + dyA + (dyB - dyA) * f;
        const z = zA + (zB - zA) * f + h1 * vA + h2 * tA + h3 * vB + h4 * tB;
        pts[o + s * 3] = x; pts[o + s * 3 + 1] = z; pts[o + s * 3 + 2] = -y;
      }
    }
  }
  const CAMPOS = { max: 'dc', dc: 'dc', flexion: 'dc_flexion', cortante: 'dc_cortante', rotacion: 'dc_rotacion' };
  // demanda/capacidad del elemento dibujado q en el paso i (cociente)
  function dcDe(q, i, campo) {
    const a = R[CAMPOS[campo] || 'dc'];
    if (!a) return 0;
    const d = dib[q], px = d.planos.x, py = d.planos.y;
    if (d.vertical && px && py && d.tipo === 'columna') {
      const vx = a[i * nE + px.k] / 100, vy = a[i * nE + py.k] / 100;
      return (vx ** 1.5 + vy ** 1.5) ** (1 / 1.5);
    }
    return a[i * nE + (px || py).k] / 100;
  }
  function escribirLineas(capa, i, campo) {
    const P6 = capa.pos.array, C6 = capa.colr.array;
    capa.lista.forEach((q, n) => {
      const o = q * P * 3, c = pal[binDC(dcDe(q, i, campo))];
      for (let s = 0; s < TRAMOS; s++) {
        const b = (n * TRAMOS + s) * 6;
        P6[b] = pts[o + s * 3]; P6[b + 1] = pts[o + s * 3 + 1]; P6[b + 2] = pts[o + s * 3 + 2];
        P6[b + 3] = pts[o + s * 3 + 3]; P6[b + 4] = pts[o + s * 3 + 4]; P6[b + 5] = pts[o + s * 3 + 5];
        C6[b] = C6[b + 3] = c.r; C6[b + 1] = C6[b + 4] = c.g; C6[b + 2] = C6[b + 5] = c.b;
      }
    });
    capa.pos.needsUpdate = true; capa.colr.needsUpdate = true;
  }
  function escribirSeleccion() {
    sel.o.visible = elegido >= 0;
    if (elegido < 0) return;
    const P6 = sel.pos.array, o = elegido * P * 3;
    for (let s = 0; s < TRAMOS; s++) for (let a = 0; a < 6; a++) P6[s * 6 + a] = pts[o + s * 3 + a];
    sel.pos.needsUpdate = true;
  }
  // punto a una fracción f del extremo A (f = 0) o B (f = 1) del polígono dibujado
  const _v = new THREE.Vector3();
  function enPolilinea(q, f, out) {
    const o = q * P * 3, u = f * TRAMOS, s = Math.min(TRAMOS - 1, Math.floor(u)), r = u - s;
    return out.set(pts[o + s * 3] + (pts[o + s * 3 + 3] - pts[o + s * 3]) * r, pts[o + s * 3 + 1] + (pts[o + s * 3 + 4] - pts[o + s * 3 + 1]) * r, pts[o + s * 3 + 2] + (pts[o + s * 3 + 5] - pts[o + s * 3 + 2]) * r);
  }
  const _q = new THREE.Quaternion(), _s = new THREE.Vector3(), _c = new THREE.Color();
  function escribirRotulas(i) {
    let n = 0;
    const palR = [col.warn, col.warn.clone().lerp(col.bad, 0.5), col.bad];
    dib.forEach((d, q) => {
      for (const [ext, f] of [['A', 0.07], ['B', 0.93]]) {
        let fl = false, nivel = -1, rel = 0;
        for (const k of d.elems) {
          const pl = Object.values(d.planos).find((p) => p.k === k) || { extA: 0, extB: 1 };
          const e = ext === 'A' ? pl.extA : pl.extB, b = acum[i * nE + k];
          if (b & (e === 0 ? 1 : 2)) fl = true;
          if (b & 64) nivel = Math.max(nivel, 2);
          if (b & (e === 0 ? 16 : 32)) nivel = Math.max(nivel, 1);
          if (b & (e === 0 ? 4 : 8)) nivel = Math.max(nivel, 0);
          const sec = secciones[info.elemSeccion?.[k]];
          const io = sec?.theta_p_IO || 0;
          if (io > 0) rel = Math.max(rel, Math.abs(tp(k, e, i)) / io);
        }
        if (!fl) continue;
        const r = r0 * (0.75 + 0.45 * Math.min(4, rel));
        enPolilinea(q, f, _v);
        esferas.setMatrixAt(n, _m.compose(_v, _q.identity(), _s.set(r, r, r)));
        if (nivel >= 0) { anillos.setMatrixAt(n, _m.compose(_v, _q, _s.set(r * 1.9, r * 1.9, r * 1.9))); anillos.setColorAt(n, palR[nivel]); }
        else anillos.setMatrixAt(n, _m.makeScale(0, 0, 0));
        n++;
      }
    });
    esferas.count = anillos.count = n;
    esferas.instanceMatrix.needsUpdate = anillos.instanceMatrix.needsUpdate = true;
    if (anillos.instanceColor) anillos.instanceColor.needsUpdate = true;
    return n;
  }
  function escribirMuros(i, e) {
    const nt = R.t.length;
    muros.forEach((w, q) => {
      const zb = niveles[w.k - 2]?.z ?? 0, fr = Math.min(1, (w.h || 0) / (w.hEntrepiso || w.h || 1));
      const pt = (p, arriba) => {
        const [bx, by] = desp(i, w.k - 1, p[0], p[1], e), [tx, ty] = desp(i, w.k, p[0], p[1], e);
        const dx = arriba ? bx + (tx - bx) * fr : bx, dy = arriba ? by + (ty - by) * fr : by;
        return [p[0] + dx, zb + (arriba ? w.h : 0), -(p[1] + dy)];
      };
      const a0 = pt(w.a, false), b0 = pt(w.b, false), a1 = pt(w.a, true), b1 = pt(w.b, true);
      posM.set([...a0, ...b0, ...b1, ...a0, ...b1, ...a1], q * 18);
      const c = palM[estMuro[Math.min(i, nt - 1) * nM + q]] || palM[0];
      for (let v = 0; v < 6; v++) colM.set([c.r, c.g, c.b], q * 18 + v * 3);
    });
    gMur.attributes.position.needsUpdate = true; gMur.attributes.color.needsUpdate = true;
  }
  const _mb = new THREE.Matrix4(), _ml = new THREE.Matrix4();
  function escribirEquipos(i, e) {
    if (!cajas) return;
    const nivel = (q) => { if (q.k > 0) { const o = (i * NL() + (q.k - 1)) * 3; return matrizNivel(q.k, R.u[o], R.u[o + 1], R.u[o + 2], e, _ml); } return _ml.identity(); };
    equipos.forEach((q, n) => { cajas.setMatrixAt(n, _mb.multiplyMatrices(nivel(q), q.base)); });
    cajas.instanceMatrix.needsUpdate = true;
    if (anillosEq) { conAnillo.forEach((q, n) => { anillosEq.setMatrixAt(n, _mb.multiplyMatrices(nivel(q), q.baseAnillo)); }); anillosEq.instanceMatrix.needsUpdate = true; }
  }
  const fmtPct = (v) => (v * 100).toLocaleString('es-CO', { maximumFractionDigits: 2, minimumFractionDigits: 2 });

  function actualizar(i, Rn, escala = 1, campo = 'dc') {
    if (!Rn?.u) return;
    if (Rn !== R) preparar(Rn);
    const nt = R.t.length;
    i = Math.max(0, Math.min(nt - 1, i | 0));
    actual = { i, escala, campo };
    for (let q = 0; q < dib.length; q++) puntos(q, i, escala);
    capas.forEach((c) => c.lista.length && escribirLineas(c, i, campo));
    escribirSeleccion();
    losas.forEach((o, k) => {
      const b = (i * NL() + k) * 3;
      matrizNivel(k + 1, R.u[b], R.u[b + 1], R.u[b + 2], escala, o.matrix);
      o.matrixWorldNeedsUpdate = true;
    });
    escribirRotulas(i);
    if (nM) escribirMuros(i, escala);
    escribirEquipos(i, escala);
    etiquetas.forEach((o) => {
      const k = o.userData.k, dv = R.derivas_vector ? R.derivas_vector[i * NL() + k] : null;
      const html = `<b>Entrepiso ${k + 1}</b><span class="lv">${dv == null ? '' : `${fmtPct(dv)} %`}</span>`, caja = o.element.firstElementChild || o.element;
      if (caja.innerHTML !== html) caja.innerHTML = html;
      const b = (i * NL() + k) * 3;
      matrizNivel(k + 1, R.u[b], R.u[b + 1], R.u[b + 2], escala, _ml);
      if (!o.userData.p0) o.userData.p0 = o.position.clone();
      o.position.copy(o.userData.p0).applyMatrix4(_ml);
    });
  }

  return {
    grupo,
    dibujados: dib.length,
    actualizar,
    // elemento elegido (id de cualquiera de sus pórticos) o null
    seleccionar(id) {
      const k = id == null ? -1 : idxElem.get(id) ?? -1;
      elegido = k >= 0 ? elemDib[k] : -1;
      escribirSeleccion();
    },
    // elemento más cercano al rayo (en ángulo visto desde la cámara), si pasa a menos de ≈ 1° de él
    pick(raycaster) {
      if (actual.i < 0) return null;
      const ray = raycaster.ray, a = new THREE.Vector3(), b = new THREE.Vector3(), enRayo = new THREE.Vector3(), enSeg = new THREE.Vector3();
      let mejor = -1, ang = 0.018;
      for (let q = 0; q < dib.length; q++) {
        const o = q * P * 3;
        for (let s = 0; s < TRAMOS; s++) {
          a.fromArray(pts, o + s * 3); b.fromArray(pts, o + s * 3 + 3);
          const d2 = ray.distanceSqToSegment(a, b, enRayo, enSeg), lejos = enRayo.distanceTo(ray.origin);
          if (lejos <= 0) continue;
          const t = Math.sqrt(d2) / lejos;
          if (t < ang) { ang = t; mejor = q; }
        }
      }
      return mejor >= 0 ? dib[mejor].id : null;
    },
    // elementos de un elemento dibujado (los dos pórticos de una columna física)
    elementosDe(id) { const k = idxElem.get(id); return k == null ? [] : dib[elemDib[k]].elems.map((e) => elementos[e].id); },
    // centro de masa de la cubierta tal como se dibuja en el paso i: [x, y, z] del marco de la especificación
    posicionCubierta(i) {
      if (!R) return null;
      if (i !== actual.i) actualizar(i, R, actual.escala, actual.campo);
      let k = 0; niveles.forEach((nv, q) => { if (nv.z > niveles[k].z) k = q; });
      const [cx, cy] = niveles[k].cm, v = new THREE.Vector3(cx, niveles[k].z, -cy).applyMatrix4(losas[k].matrix);
      return [v.x, -v.z, v.y];
    },
    // caja de la estructura (para encuadrar la cámara), con margen para la deformada exagerada
    caja(margen = 2) {
      const b = new THREE.Box3();
      dib.forEach((d) => { b.expandByPoint(_v.set(d.A[0], d.A[2], -d.A[1])); b.expandByPoint(_v.set(d.B[0], d.B[2], -d.B[1])); });
      return b.expandByScalar(margen);
    },
    // equipos: [{ unidad, k (nivel global sobre el que se apoyan; 0 = suelo), x, y, z (cota absoluta de la base), dim, rot,
    //   color, desliza_m (deslizamiento máximo que calculó el motor, m) }]
    ponerEquipos(lista) {
      if (cajas) { grupo.remove(cajas); cajas.geometry.dispose(); cajas = null; }
      if (anillosEq) { grupo.remove(anillosEq); anillosEq.geometry.dispose(); anillosEq = null; }
      equipos = (lista || []).map((q) => ({ ...q, base: new THREE.Matrix4().compose(new THREE.Vector3(q.x, q.z + q.dim[2] / 2, -q.y), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), q.rot || 0), new THREE.Vector3(Math.max(0.05, q.dim[0]), Math.max(0.05, q.dim[2]), Math.max(0.05, q.dim[1]))) }));
      conAnillo = equipos.filter((q) => q.desliza_m > 0).map((q) => {
        const r = Math.hypot(q.dim[0], q.dim[1]) / 2 + q.desliza_m;
        return { ...q, baseAnillo: new THREE.Matrix4().compose(new THREE.Vector3(q.x, q.z + 0.02, -q.y), new THREE.Quaternion(), new THREE.Vector3(r, 1, r)) };
      });
      if (!equipos.length) return;
      cajas = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mCaja, equipos.length);
      equipos.forEach((q, n) => { cajas.setMatrixAt(n, q.base); cajas.setColorAt(n, q.color || col.muted); });
      cajas.frustumCulled = false;
      grupo.add(cajas);
      if (conAnillo.length) {
        anillosEq = new THREE.InstancedMesh(new THREE.RingGeometry(0.9, 1, tier === 'baja' ? 20 : 32).rotateX(-Math.PI / 2), mAnilloEq, conAnillo.length);
        conAnillo.forEach((q, n) => anillosEq.setMatrixAt(n, q.baseAnillo));
        anillosEq.frustumCulled = false;
        grupo.add(anillosEq);
      }
      if (R && actual.i >= 0) escribirEquipos(actual.i, actual.escala);
    },
    resolucion(w, h) { [...capas, sel].forEach((c) => c.m.resolution.set(w, h)); },
    tema(c) {
      col = c; pal = paletaDC(c); palM = paletaMuro(c);
      mFant.color.copy(c.muted); mLosa.color.copy(c.muted); mBorde.color.copy(c.ink); mEsf.color.copy(c.ink); sel.m.color.copy(c.data); mAnilloEq.color.copy(c.warn);
      if (R && actual.i >= 0) actualizar(actual.i, R, actual.escala, actual.campo);
    },
    paleta: () => ({ dc: pal, muro: palM }),
    etiquetas,
    rotulasVisibles: () => esferas.count,
    dispose() {
      etiquetas.forEach((o) => { o.element.remove(); o.parent?.remove(o); });
      grupo.traverse((o) => { o.geometry?.dispose?.(); });
      [mFant, mLosa, mBorde, mEsf, mMur, mCaja, mAnilloEq, anillos.material, ...capas.map((c) => c.m), sel.m].forEach((m) => m.dispose());
      grupo.parent?.remove(grupo);
    },
  };
}
