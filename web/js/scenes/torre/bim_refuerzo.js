// Refuerzo en 3D del modo «Modelo BIM» (equipo F; especificación de integración 17.5, «Refuerzo y dónde va»).
// Cada juego de barras del despiece (web/data/torre_bim_ref_<NIVEL>.json) es una forma relativa en milímetros que se repite
// en sus copias (base + copia); los espirales de los pilotes vienen como parámetros (centro, radio y tramos con su paso).
// Se dibuja solo el refuerzo del elemento o del eje elegido, nunca el de toda la torre: cada tramo recto de cada barra es
// una instancia de un mismo cilindro (InstancedMesh: una sola llamada de dibujo para todas las barras), con su diámetro
// real y el color de su función (longitudinales, estribos y espirales, ganchos, bastones, mallas y parrillas).
// Las zonas (confinamiento lo, 2h de las vigas, bordes de muros, traslapos, cabeza del pilote) van en una sola malla
// transparente. Coordenadas: proyecto (x oriente, y norte, z arriba) → three (x, z, −y).
import { THREE } from '../../core.js';

// familias de barras por su función (rol del despiece) y sus colores (son del 3D, iguales en los dos temas)
export const FAMILIAS = [
  { id: 'longitudinal', nombre: 'Longitudinales y corridas', color: '#c0392b' },
  { id: 'bastones', nombre: 'Bastones (refuerzo en los apoyos)', color: '#e67e22' },
  { id: 'transversal', nombre: 'Estribos y espirales', color: '#2471a3' },
  { id: 'ganchos', nombre: 'Ganchos suplementarios y ramas', color: '#16a085' },
  { id: 'mallas', nombre: 'Mallas, parrillas y piel', color: '#27ae60' },
];
export const familia = (rol) => (/estribo|espiral/.test(rol) ? 'transversal' : /gancho/.test(rol) ? 'ganchos' : /bast/.test(rol) ? 'bastones'
  : /malla|parrilla|cortina_horizontal|muro_horizontal|reparticion|piel/.test(rol) ? 'mallas' : 'longitudinal');
const COLOR_FAM = Object.fromEntries(FAMILIAS.map((f) => [f.id, f.color]));

// polilíneas (puntos del proyecto, metros) de un juego: una por copia; el espiral, una sola
export function polilineas(j, formas) {
  if (j.param?.tipo === 'espiral') {
    const p = j.param, n = p.lados_por_vuelta || 12, [cx, cy] = p.centro, r = p.radio, pts = [];
    let a = 0;
    for (const t of [...p.tramos].sort((q, w) => q.z0 - w.z0)) {
      const vueltas = (t.z1 - t.z0) / t.paso, k = Math.max(1, Math.round(vueltas * n));
      for (let i = pts.length ? 1 : 0; i <= k; i++) { const s = i / k; pts.push([cx + r * Math.cos(a + 2 * Math.PI * vueltas * s), cy + r * Math.sin(a + 2 * Math.PI * vueltas * s), t.z0 + (t.z1 - t.z0) * s]); }
      a += 2 * Math.PI * vueltas;
    }
    return [pts];
  }
  const f = formas[j.forma], b = j.base;
  if (!f) return [];
  return (j.copias?.length ? j.copias : [[0, 0, 0]]).map((c) => {
    const pts = [];
    for (let i = 0; i < f.length; i += 3) pts.push([b[0] + (f[i] + c[0]) / 1000, b[1] + (f[i + 1] + c[1]) / 1000, b[2] + (f[i + 2] + c[2]) / 1000]);
    return pts;
  });
}

// conjuntos: [{ juegos: [j], formas, tono: 'normal' | 'apagado' }]; resaltar: Set de ids de juegos (interferencias)
export function crearRefuerzo3D(planos, { radial = 8 } = {}) {
  const grupo = new THREE.Group(); grupo.name = 'bim_refuerzo';
  const geo = new THREE.CylinderGeometry(1, 1, 1, radial, 1, true); geo.translate(0, 0.5, 0);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.1, side: THREE.DoubleSide, clippingPlanes: planos });
  // el color de cada barra también como emisión suave: así se lee su función aunque la luz le llegue de lado
  mat.onBeforeCompile = (sh) => { sh.fragmentShader = sh.fragmentShader.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\n#ifdef USE_COLOR\ntotalEmissiveRadiance += vColor * 0.35;\n#endif'); };
  mat.customProgramCacheKey = () => 'bim-barras';
  let malla = null, rangos = [], info = null, ultimas = [], discos = null;
  const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new THREE.Vector3(), _p = new THREE.Vector3(), _d = new THREE.Vector3(), Y = new THREE.Vector3(0, 1, 0);
  const cGris = new THREE.Color('#9a9a95'), cRes = new THREE.Color('#e02ad8');
  function limpiar() {
    if (malla) { grupo.remove(malla); malla.dispose(); malla = null; }
    cortar(null);
    rangos = []; info = null; ultimas = [];
  }
  // sección de las barras en un plano de corte: un disco del color de cada barra que cruza el plano, encima de la tapa
  // (los tubos cortados quedan bajo la tapa del concreto)
  const matD = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  function cortar(cfg) {
    if (discos) { grupo.remove(discos); discos.geometry.dispose(); discos = null; }
    if (!cfg || !ultimas.length) return 0;
    const k = cfg.tipo === 'h' ? 2 : cfg.tipo === 'x' ? 0 : 1, p = [], c = [], col = new THREE.Color(), N = 10;
    for (const b of ultimas) {
      col.set(b.color);
      for (const pl of b.pls) for (let i = 0; i + 1 < pl.length; i++) {
        const da = pl[i][k] - cfg.c, db = pl[i + 1][k] - cfg.c;
        if ((da < 0) === (db < 0) || Math.abs(da - db) < 1e-9) continue;
        const t = da / (da - db), q = pl[i].map((v, m) => v + t * (pl[i + 1][m] - v)), r = b.r * 1.15;
        // disco en el plano (coordenadas del proyecto): los dos ejes que no son k
        const [u, w] = [0, 1, 2].filter((m) => m !== k);
        for (let s2 = 0; s2 < N; s2++) {
          const a0 = (2 * Math.PI * s2) / N, a1 = (2 * Math.PI * (s2 + 1)) / N;
          for (const [du, dw] of [[0, 0], [Math.cos(a0) * r, Math.sin(a0) * r], [Math.cos(a1) * r, Math.sin(a1) * r]]) {
            const X = [...q]; X[u] += du; X[w] += dw;
            p.push(X[0], X[2], -X[1]); c.push(col.r, col.g, col.b);
          }
        }
      }
    }
    if (!p.length) return 0;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    g.computeBoundingSphere();
    discos = new THREE.Mesh(g, matD); discos.renderOrder = 7; discos.name = 'bim_secciones_barras';
    grupo.add(discos);
    return p.length / (9 * N);
  }
  function mostrar(conjuntos, { resaltar = null, minRadio = 0.005 } = {}) {
    limpiar();
    // primero se cuentan los tramos para reservar las instancias
    const barras = [];
    let total = 0, kg = 0, nb = 0;
    const caja = new THREE.Box3(), cajaPropia = new THREE.Box3();
    for (const cj of conjuntos) for (const j of cj.juegos) {
      const pls = polilineas(j, cj.formas);
      const segs = pls.reduce((s, p) => s + Math.max(0, p.length - 1), 0);
      if (!segs) continue;
      barras.push({ j, pls, segs, tono: cj.tono || 'normal' });
      total += segs;
      if (cj.tono !== 'apagado') { kg += j.kg || 0; nb += j.n || pls.length; }
    }
    if (!total) { info = { tramos: 0, barras: 0, kg: 0, caja, cajaPropia }; return info; }
    malla = new THREE.InstancedMesh(geo, mat, total);
    malla.name = 'bim_barras'; malla.frustumCulled = false; malla.renderOrder = 4;
    const col = new THREE.Color();
    let k = 0;
    for (const b of barras) {
      const r = Math.max(minRadio, (b.j.db_mm || 12.7) / 2000);
      col.set(b.tono === 'apagado' ? cGris : resaltar?.has(b.j.id) ? cRes : COLOR_FAM[familia(b.j.rol)]);
      const k0 = k;
      for (const pts of b.pls) {
        for (let i = 0; i + 1 < pts.length; i++) {
          const a = pts[i], c = pts[i + 1];
          _p.set(a[0], a[2], -a[1]); _d.set(c[0] - a[0], c[2] - a[2], -(c[1] - a[1]));
          const L = _d.length();
          if (L < 1e-6) { _m.makeScale(0, 0, 0); malla.setMatrixAt(k, _m); malla.setColorAt(k, col); k++; continue; }
          _d.divideScalar(L);
          _q.setFromUnitVectors(Y, _d);
          // cada tramo se alarga un radio por los dos extremos para que los dobleces no dejen huecos
          _p.addScaledVector(_d, -r * 0.5);
          _s.set(r, L + r, r);
          _m.compose(_p, _q, _s);
          malla.setMatrixAt(k, _m); malla.setColorAt(k, col);
          caja.expandByPoint(_p); if (b.tono !== 'apagado') cajaPropia.expandByPoint(_p);
          _p.addScaledVector(_d, L + r); caja.expandByPoint(_p); if (b.tono !== 'apagado') cajaPropia.expandByPoint(_p);
          k++;
        }
      }
      rangos.push({ k0, k1: k, j: b.j, tono: b.tono });
      if (b.tono !== 'apagado') ultimas.push({ pls: b.pls, r, color: resaltar?.has(b.j.id) ? '#e02ad8' : COLOR_FAM[familia(b.j.rol)] });
    }
    malla.instanceMatrix.needsUpdate = true;
    if (malla.instanceColor) malla.instanceColor.needsUpdate = true;
    malla.computeBoundingSphere();
    grupo.add(malla);
    info = { tramos: total, barras: nb, kg, caja, cajaPropia };
    return info;
  }
  // juego bajo el puntero (instancia → juego)
  function pick(ray) {
    if (!malla) return null;
    const h = ray.intersectObject(malla, false).find((x) => !planos.length || planos[0].distanceToPoint(x.point) >= 0);
    if (h?.instanceId == null) return null;
    let lo = 0, hi = rangos.length - 1;
    while (lo <= hi) { const m = (lo + hi) >> 1, r = rangos[m]; if (h.instanceId < r.k0) hi = m - 1; else if (h.instanceId >= r.k1) lo = m + 1; else return { juego: r.j, punto: h.point.clone(), tono: r.tono }; }
    return null;
  }
  return { grupo, mostrar, limpiar, pick, cortar, secciones: () => (discos ? discos.geometry.attributes.position.count / 30 : 0), info: () => info, tramos: () => (malla ? malla.count : 0), dispose() { limpiar(); geo.dispose(); mat.dispose(); matD.dispose(); } };
}

// zonas del armado como cajas transparentes (una sola malla): [{ min: [x, y, z], max: [x, y, z], color }]
export function crearBandas(bandas, planos) {
  const p = [], c = [], col = new THREE.Color();
  for (const b of bandas) {
    col.set(b.color);
    const [x0, y0, z0] = b.min, [x1, y1, z1] = b.max;
    const V = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]].map((q) => [q[0], q[2], -q[1]]);
    for (const [a, bb, cc, d] of [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]) for (const i of [a, bb, cc, a, cc, d]) { p.push(...V[i]); c.push(col.r, col.g, col.b); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
  g.computeBoundingSphere();
  const m = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide, clippingPlanes: planos });
  const malla = new THREE.Mesh(g, m); malla.renderOrder = 5; malla.name = 'bim_zonas';
  malla.userData.dispose = () => { g.dispose(); m.dispose(); };
  return malla;
}
