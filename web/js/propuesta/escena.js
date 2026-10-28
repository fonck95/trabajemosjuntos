// Escena base de la propuesta 2028–2031: el territorio real de Yondó sobre el que cada módulo pone sus capas.
// Casco urbano (calles, caños y ciénagas de OpenStreetMap; casas a partir de huellas abiertas; réplicas de las sedes
// públicas tal como están HOY, sin los paneles por sede del atlas), el río Magdalena con sus islas, la vía al puente y el
// puente Guillermo Gaviria Correa. Usa el motor compartido (core.js): un solo Stage, render bajo demanda y LOD.
// Los encuadres respetan el panel: el objeto se centra en la parte de la pantalla que queda libre.
import { THREE, Stage, engine, tokens, onTheme, mat, gsap, solidBox, Flow, CSS2DObject } from '../core.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS, CALLES } from '../data.js';
import { V, cinta, losa, prisma, materiales, usarMateriales, dentro } from './geo3d.js';

const R_SUELO = 16000;

export function crearEscena(el, datos) {
  const terr = datos.territorio || {};
  const st = new Stage(el, { cam: [-900, 1500, 1900], target: [150, 0, -250], fov: 36, minDist: 6, maxDist: 16000, fit: 0, declutter: ['lbl-p'], tone: 'aces', exposure: 1.05, sky: true, fog: { near: 3000, far: 14000 } });
  st.camera.far = 40000; st.camera.updateProjectionMatrix();
  Object.assign(st.controls, { zoomToCursor: true, screenSpacePanning: false, zoomSpeed: 1.15, maxPolarAngle: Math.PI * 0.46 });
  // sombra: volumen de ±700 m que viaja con lo que se mira (el sol se corre con el objetivo de la cámara)
  // sol de media tarde (más bajo y cálido que en el atlas: sombras largas que dan relieve a la maqueta)
  const L = st.sunLight, sc = L.shadow.camera, SOL = new THREE.Vector3(430, 400, 250);
  L.color.set('#ffe6c2'); L.intensity = 2.35; st.hemi.color.set('#dfe9ff'); st.hemi.groundColor.set('#5b6650');
  Object.assign(sc, { left: -700, right: 700, top: 700, bottom: -700, near: 1, far: 2200 });
  L.shadow.mapSize.set(4096, 4096); L.shadow.normalBias = 0.6;
  st.scene.add(L.target);
  const ancla = new THREE.Vector3(1e9, 0, 0);
  st.onFrame(() => {
    const t = st.controls.target;
    if (Math.hypot(t.x - ancla.x, t.z - ancla.z) < 60) return false;
    ancla.set(Math.round(t.x / 50) * 50, 0, Math.round(t.z / 50) * 50);
    L.target.position.copy(ancla); L.position.copy(ancla).add(SOL); L.target.updateMatrixWorld(); L.updateMatrixWorld();
    st.updateShadows();
    return true;
  });
  // niebla según la distancia de la cámara: de cerca no deslava el pueblo y de lejos disuelve el borde del piso
  st.onFrame(() => {
    const d = st.camera.position.distanceTo(st.controls.target);
    st.fogCfg.near = Math.max(1500, d * 1.6); st.fogCfg.far = Math.max(7000, d * 5.5);
    return false;
  });

  const T = tokens(), S = st.scene, M = materiales(T);
  usarMateriales(M);
  const capa = (m, k) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const B = {
    ground: mat(T.ground.clone().lerp(new THREE.Color('#7f9a5a'), 0.18)), road: capa(mat(T.ground.clone().lerp(T.ink, 0.22), { roughness: 0.95, side: THREE.DoubleSide }), 2),
    water: capa(mat(T.water, { roughness: 0.22, metalness: 0.1, side: THREE.DoubleSide }), 1),
    rio: capa(mat(T.water, { roughness: 0.18, metalness: 0.12, side: THREE.DoubleSide }), 1),
    isla: capa(mat(new THREE.Color('#6f8f5a'), { roughness: 1, side: THREE.DoubleSide }), 2),
    cano: capa(mat(T.water, { roughness: 0.25, metalness: 0.1, side: THREE.DoubleSide }), 3),
  };
  const ground = new THREE.Mesh(new THREE.CircleGeometry(R_SUELO, 128), B.ground); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true; S.add(ground);
  const vias = new THREE.Mesh(cintas([...CALLES.calles, ...(terr.vias || [])], 0.02), B.road); vias.receiveShadow = true; S.add(vias);
  const canos = new THREE.Mesh(cintas(CALLES.canos, 0.04), B.cano); S.add(canos);
  CALLES.agua.forEach((a) => { const m = new THREE.Mesh(losa(a.p, 0, a.huecos || []), B.water); S.add(m); st.freeze(m); });
  if (terr.rio?.poligono) {
    const rio = new THREE.Mesh(losa(terr.rio.poligono, 0.01, terr.rio.islas || []), B.rio); rio.receiveShadow = true; S.add(rio); st.freeze(rio);
    (terr.rio.islas || []).forEach((i) => { const m = new THREE.Mesh(losa(i, 0.03), B.isla); m.receiveShadow = true; S.add(m); st.freeze(m); });
  }
  [ground, vias, canos].forEach((o) => st.freeze(o));

  // puente Guillermo Gaviria Correa: tablero a 14 m sobre el agua con pilas cada ~60 m y rampas en los estribos
  const puente = new THREE.Group(); S.add(puente);
  const tb = terr.puente?.tablero || [];
  if (tb.length > 1) {
    const sube = (k, n) => Math.min(14, Math.min(k, n - k) * 0.06);   // rampa de ~6 % en cada extremo
    const pts = []; for (let i = 1; i < tb.length; i++) { const [a, b] = [tb[i - 1], tb[i]], n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 10); for (let k = i > 1 ? 1 : 0; k <= n; k++) pts.push([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n]); }
    let acc = 0; const dist = pts.map((p, i) => (acc += i ? Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) : 0)), Ltot = acc;
    const geoT = [], geoP = [], cm = M.concreto;
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]], h0 = sube(dist[i - 1], Ltot), h1 = sube(dist[i], Ltot), L2 = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const g = new THREE.BoxGeometry(L2 + 0.4, 1.4, 13); g.rotateZ(Math.atan2(h1 - h0, L2)); g.rotateY(Math.atan2(b[1] - a[1], b[0] - a[0]));
      g.translate((a[0] + b[0]) / 2, (h0 + h1) / 2 + 0.7, -(a[1] + b[1]) / 2); geoT.push(g);
    }
    for (let s = 60; s < Ltot - 40; s += 60) {
      const i = dist.findIndex((d) => d >= s), p = pts[i], h = sube(s, Ltot);
      const g = new THREE.BoxGeometry(3, h, 9); g.rotateY(Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])); g.translate(p[0], h / 2, -p[1]); geoP.push(g);
    }
    const t = new THREE.Mesh(mergeGeometries(geoT.map((g) => g.toNonIndexed())), cm), p = new THREE.Mesh(mergeGeometries(geoP.map((g) => g.toNonIndexed())), cm);
    [t, p].forEach((o) => { o.castShadow = true; o.receiveShadow = true; puente.add(o); }); st.freeze(puente);
  }

  // contexto: casas y locales a partir de huellas abiertas (Microsoft, ODbL), con alturas de 1–2 pisos. Las que caen en una
  // zona de intervención (lotes que la propuesta transforma) van en mallas aparte para poder mostrar «hoy» y «proyecto»
  // fachadas y cubiertas con los colores de un pueblo del Magdalena Medio (zinc, fibrocemento, teja de barro, pintura)
  const ctxMats = { wall: mat(T.wall, { roughness: 0.95, side: THREE.DoubleSide, vertexColors: true }), roof: mat(T.wall, { roughness: 0.8, side: THREE.DoubleSide, vertexColors: true }) };
  const FACH = ['#f3f0e9', '#f5e7c9', '#e7eff2', '#f3dccf', '#e3eedb', '#efe2ec', '#f6f1d4', '#dde6f0'].map((c) => new THREE.Color(c));
  const CUB = ['#9aa2a7', '#9aa2a7', '#b9bec0', '#b9bec0', '#a9583c', '#c6c8c2', '#8e9692', '#5f7f9c', '#b46a48'].map((c) => new THREE.Color(c));
  const zonasHoy = (datos.zonas_intervencion || []).map((z) => ({ ...z, grupo: new THREE.Group() }));
  zonasHoy.forEach((z) => { z.grupo.name = `hoy.${z.id}`; S.add(z.grupo); });
  const huellas = [];
  const listoHuellas = fetch(new URL('../../models/contexto/huellas.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((hu) => {
    if (!hu?.poligonos?.length) return;
    const boxes = EDIFICIOS.map((e) => { const [sx, , sz] = e.tamano || [20, 8, 20]; return [e.x, e.y, sx / 2 + 1, sz / 2 + 1]; });
    const lotes = new Map([[null, { wp: [], rp: [], wc: [], rc: [] }], ...zonasHoy.map((z) => [z.id, { wp: [], rp: [], wc: [], rc: [] }])]);
    hu.poligonos.forEach((flat, k) => {
      const pts = []; for (let i = 0; i < flat.length; i += 2) pts.push(new THREE.Vector2(flat[i], flat[i + 1]));
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length, cy = pts.reduce((a, p) => a + p.y, 0) / pts.length;
      if (boxes.some(([bx, by, hx, hy]) => Math.abs(cx - bx) < hx && Math.abs(cy - by) < hy)) return;
      const area = Math.abs(THREE.ShapeUtils.area(pts)), h = 2.9 + (area > 160 ? 2.6 : 0) + ((k * 2654435761) % 5) * 0.25;
      const z = zonasHoy.find((zz) => dentro([cx, cy], zz.poligono));
      huellas.push({ pts: pts.map((p) => [p.x, p.y]), cx, cy, area, h, zona: z?.id || null });
      const { wp, rp, wc, rc } = lotes.get(z?.id || null), cf = FACH[(k * 7919) % FACH.length], cr = CUB[(k * 104729) % CUB.length];
      for (let i = 0; i < pts.length; i++) { const a = pts[i], b = pts[(i + 1) % pts.length]; wp.push(a.x, 0, -a.y, b.x, 0, -b.y, b.x, h, -b.y, a.x, 0, -a.y, b.x, h, -b.y, a.x, h, -a.y); for (let j = 0; j < 6; j++) wc.push(cf.r, cf.g, cf.b); }
      THREE.ShapeUtils.triangulateShape(pts, []).forEach((t) => t.forEach((j) => { rp.push(pts[j].x, h, -pts[j].y); rc.push(cr.r, cr.g, cr.b); }));
    });
    const mk = (arr, col, m, padre) => { if (!arr.length) return; const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); g.computeVertexNormals(); const o = new THREE.Mesh(g, m); o.castShadow = true; o.receiveShadow = true; padre.add(o); st.freeze(o); };
    lotes.forEach(({ wp, rp, wc, rc }, id) => { const padre = id ? zonasHoy.find((z) => z.id === id).grupo : S; mk(wp, wc, ctxMats.wall, padre); mk(rp, rc, ctxMats.roof, padre); });
    st.updateShadows();
  }).catch((e) => console.warn('huellas', e));

  // réplicas de las sedes públicas, en su estado de hoy (sin las adecuaciones del atlas: paneles, baterías, conexiones)
  const edificios = new Map();
  EDIFICIOS.forEach((e) => {
    const g = new THREE.Group(); g.position.copy(V(e.x, e.y)); S.add(g);
    const [sx, sy, sz] = e.tamano || [20, 8, 20];
    const ph = new THREE.Mesh(new THREE.BoxGeometry(Math.max(4, sx - 4), Math.max(3, sy - 3), Math.max(4, sz - 4)), mat(T.wall, { transparent: true, opacity: 0.55 }));
    ph.position.y = Math.max(3, sy - 3) / 2; g.add(ph);
    const it = { e, g, ph, lod: null, cargado: false, modo: { capa: 'hoy', sin: [] }, listo: [] };
    if (e.archivo) {
      it.lod = progressiveLOD([{ url: e.archivo, distance: 0 }, { url: e.archivo_lod1, distance: 300 }], (lod) => {
        ph.visible = false; it.cargado = true; aplicarModo(it); st.updateShadows();
        it.listo.splice(0).forEach((fn) => fn(it));
      });
      g.add(it.lod);
    }
    edificios.set(e.id, it);
  });
  st.onFrame(() => { edificios.forEach((it) => it.lod?.update(st.camera)); return false; });
  // modo de una réplica: 'hoy' (como está) o 'proyecto' (con sus adecuaciones, salvo las capas de «sin»)
  function aplicarModo(it) {
    if (!it.lod) return;
    const proy = it.modo.capa === 'proyecto';
    it.lod.traverse((o) => {
      if (o.name === 'adecuaciones') o.visible = proy;
      if (o.name === 'cubierta_actual' && o.userData.reemplazada) o.visible = !proy;
      if (o.userData.demoler) o.visible = !proy;
      if (proy && it.modo.sin.includes(o.name) && o.parent?.name === 'adecuaciones') o.visible = false;
    });
  }

  // ---------------------------------------------------------------- capas de los módulos y etiquetas
  const capas = new Map();
  function nuevaCapa(id) {
    if (capas.has(id)) return capas.get(id);
    const g = new THREE.Group(); g.name = id; g.visible = false; S.add(g); capas.set(id, g);
    return g;
  }
  // CSS2DRenderer no hereda la visibilidad del padre: cada etiqueta se muestra solo si toda su cadena es visible
  // etiquetas visibles: las de las capas visibles; en las vistas de conjunto (soloEtiquetas) solo las de algunas capas
  let soloCapas = null;
  function verEtiqueta(o) {
    let v = o.userData.ver !== false, permitida = !soloCapas;
    for (let p = o.parent; p; p = p.parent) { if (!p.visible) { v = false; break; } if (soloCapas?.has(p)) permitida = true; }
    o.visible = v && permitida;
  }
  function sincronizarEtiquetas() { S.traverse((o) => { if (o.isCSS2DObject) verEtiqueta(o); }); }
  // ancla: [cx, cy] del recuadro que cae sobre el punto (0,5 0,5 centrado; 0,5 1 el recuadro queda encima del punto)
  function etiqueta(html, { cls = 'lbl-p', pos = [0, 0, 0], padre = S, color, titulo, alClic, ancla } = {}) {
    const div = document.createElement('div');
    div.className = `lbl ${cls}`; div.innerHTML = html;
    if (color) div.style.setProperty('--mc', color);
    if (titulo) div.title = titulo;
    if (alClic) { div.style.pointerEvents = 'auto'; div.style.cursor = 'pointer'; div.addEventListener('click', alClic); }
    const o = new CSS2DObject(div); o.position.copy(V(pos[0], pos[1], pos[2] || 0)); if (ancla) o.center.set(ancla[0], ancla[1]); padre.add(o); st._labels.push(o);
    verEtiqueta(o);   // nace oculta si su capa lo está (los módulos que cargan tarde no destapan rótulos de otro paso)
    return o;
  }
  // líneas de ancho fijo en pantalla (enlaces, redes, contornos); el ancho se recalcula con el tamaño del lienzo
  const lineas = [];
  function linea(pts, { color = '#111', ancho = 3, h = 1, punteada = false, opacidad = 1, padre = S, guion = 8 } = {}) {
    const geo = new LineGeometry(); geo.setPositions(pts.flatMap(([x, y, hh]) => [x, hh ?? h, -y]));
    const m = new LineMaterial({ color: new THREE.Color(String(color).startsWith('--') ? '#888' : color), linewidth: ancho, transparent: true, opacity: opacidad, depthWrite: false, dashed: punteada, dashSize: guion, gapSize: guion });
    if (String(color).startsWith('--')) tenir(m, color);
    const o = new Line2(geo, m); if (punteada) o.computeLineDistances(); padre.add(o); lineas.push(m);
    return o;
  }
  st.onFrame(() => { const w = el.clientWidth, h = el.clientHeight; lineas.forEach((m) => m.resolution.set(w, h)); return false; });
  // flujos de partículas por una ruta (agua, energía, datos, carga): la densidad y la velocidad muestran el caudal
  const flujos = [];
  function flujo(pts, { color = '#2a78d6', h = 1, potencia = 0.8, max = 40, tam = 0.9, tubo = 0.25, padre } = {}) {
    const curva = new THREE.CatmullRomCurve3(pts.map(([x, y, hh]) => V(x, y, hh ?? h)), false, 'centripetal');
    const f = new Flow(padre || S, curva, new THREE.Color(color), { max, size: tam, tube: tubo });
    f.set(potencia, 1); flujos.push(f);
    return f;
  }
  st.onFrame((dt) => { let n = false; flujos.forEach((f) => { let vis = true; for (let p = f.mesh; p; p = p.parent) if (!p.visible) { vis = false; break; } if (vis && f.update(dt) !== false) n = true; }); return n; });

  // Etiquetas sin encimarse y dentro de la zona libre: tiene en cuenta el ancla de cada recuadro, corre en horizontal
  // las que el panel, la leyenda o el borde cortarían, sube lo justo las que chocan y oculta las de puntos que caen
  // debajo del panel o fuera de la pantalla. Reemplaza el de core.js solo en esta página.
  st.declutterLabels = function () {
    const z = zonaPx(), v = new THREE.Vector3(), items = [];
    for (const o of this._labels) {
      const e = o.element;
      if (!e.isConnected || e.style.display === 'none' || !(e.classList.contains('lbl-p') || e.classList.contains('lbl-geo'))) continue;
      o.getWorldPosition(v).project(this.camera);
      if (v.z > 1) continue;
      const w = e.offsetWidth, h = e.offsetHeight;
      if (!w) continue;
      const ax = ((v.x + 1) / 2) * z.W, ay = ((1 - v.y) / 2) * z.H, x = ax + (0.5 - o.center.x) * w, y = ay + (0.5 - o.center.y) * h;
      const fuera = ax < z.x0 - 14 || ax > z.x1 + 14 || ay < z.y0 - 14 || ay > z.y1 + 48;
      items.push({ e, x, y, w, h, fuera, mini: e.classList.contains('mini') || e.classList.contains('lbl-geo'), x2: Math.min(Math.max(x, z.x0 + w / 2 + 6), Math.max(z.x0 + w / 2 + 6, z.x1 - w / 2 - 6)) });
    }
    // primero los rótulos principales y después los chicos; cada uno sube lo justo para no chocar y, si arriba ya no cabe
    // sin encimarse (pasa en el celular), se oculta
    const puestas = [], choca = (r, y) => puestas.find((p) => Math.abs(p.x - r.x2) < (p.w + r.w) / 2 + 4 && Math.abs(p.y - y) < (p.h + r.h) / 2 + 3);
    const colocar = (r) => {
      let y = Math.min(r.y, z.y1 - r.h / 2 - 4);
      for (let k = 0; k < 14; k++) { const c = choca(r, y); if (!c) break; y = c.y - (c.h + r.h) / 2 - 3; }
      const tope = z.y0 + r.h / 2 + 4;
      if (y < tope) { y = tope; if (choca(r, y)) { r.fuera = true; return; } }
      r.dx = r.x2 - r.x; r.dy = y - r.y; puestas.push({ x: r.x2, y, w: r.w, h: r.h });
    };
    const visibles = items.filter((r) => !r.fuera).sort((a, b) => b.y - a.y);
    visibles.filter((r) => !r.mini).forEach(colocar);
    visibles.filter((r) => r.mini).forEach(colocar);
    items.forEach((r) => {
      r.e.classList.toggle('fuera', r.fuera);
      r.e.style.marginLeft = !r.fuera && Math.abs(r.dx) > 0.5 ? `${r.dx}px` : '';
      r.e.style.marginTop = !r.fuera && Math.abs(r.dy) > 0.5 ? `${r.dy}px` : '';
    });
  };
  // cubiertas del contexto en gris (para que se lean los techos que resalta un paso, como los mejoramientos)
  const colorCubierta = ctxMats.roof.color.clone();
  function contextoGris(v) {
    const m = ctxMats.roof;
    if (m.vertexColors === !v) return;
    m.vertexColors = !v; m.color.copy(v ? new THREE.Color('#c4c7c8') : colorCubierta); m.needsUpdate = true; st.invalidate();
  }

  // ---------------------------------------------------------------- encuadres que respetan el panel
  const elPanel = () => document.querySelector('.panel');
  // zona libre de la pantalla en coordenadas normalizadas (−1…1, y hacia arriba)
  function zonaPx() {
    const r = el.getBoundingClientRect(), W = r.width || 1, H = r.height || 1;
    let x0 = 0, x1 = W, y0 = 0, y1 = H;
    const ley = document.querySelector('.leyenda3d'), bl = ley?.childElementCount ? ley.getBoundingClientRect() : null;
    if (bl?.height && bl.top - r.top > H / 2) y1 = Math.min(y1, bl.top - r.top - 8);
    else if (bl?.height) y0 = Math.max(y0, bl.bottom - r.top + 6);   // en el celular la leyenda va arriba, bajo la barra
    const bar = document.querySelector('.barra')?.getBoundingClientRect(), ctl = document.querySelector('.control')?.getBoundingClientRect();
    if (bar) y0 = Math.max(y0, bar.bottom - r.top + 6);
    if (ctl) y1 = Math.min(y1, ctl.top - r.top - 6);
    const p = elPanel(), oculto = document.getElementById('pres')?.classList.contains('sin-panel');
    if (p && !oculto) {
      const b = p.getBoundingClientRect();
      if (b.width < W * 0.7) x0 = Math.max(x0, b.right - r.left + 16);
      else y1 = Math.min(y1, b.top - r.top - 8);
    }
    const riel = document.querySelector('.riel')?.getBoundingClientRect();
    if (riel && riel.width > W * 0.7) y0 = Math.max(y0, riel.bottom - r.top + 4);
    if (x1 - x0 < W * 0.25) { x0 = 0; x1 = W; }
    // con la hoja inferior del celular la franja libre puede ser baja, pero nunca se encuadra en la pantalla entera: la
    // obra quedaría debajo del texto. Se deja una franja mínima de 90 px.
    if (y1 - y0 < 90) y1 = Math.min(H, y0 + 90);
    return { x0, x1, y0, y1, W, H };
  }
  function zona() {
    const { x0, x1, y0, y1, W, H } = zonaPx();
    return { x0: (x0 / W) * 2 - 1, x1: (x1 / W) * 2 - 1, y0: 1 - (y1 / H) * 2, y1: 1 - (y0 / H) * 2 };
  }
  // puntos 3D de lo que hay que encuadrar: caja, objeto, lista de [x, y(, h)] o polígono
  function puntosDe(obj) {
    if (obj?.isBox3) { const b = obj, out = []; for (let i = 0; i < 8; i++) out.push(new THREE.Vector3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z)); return out; }
    if (obj?.isObject3D) return puntosDe(solidBox(obj, 0.2));
    return obj.map(([x, y, h]) => V(x, y, h || 0));
  }
  // encuadra (rumbo: desde dónde se mira, en grados desde el norte en sentido horario; elev: grados sobre el horizonte)
  function encuadrar(obj, { rumbo = 200, elev = 38, margen = 0.86, duracion = 1.8, alto = 0, minDist = 60 } = {}) {
    const pts = puntosDe(obj);
    if (!pts.length) return;
    if (alto) pts.push(...pts.map((p) => p.clone().setY(p.y + alto)));
    const z = zona(), cam = st.camera.clone(); cam.far = 1e7; cam.updateProjectionMatrix();
    const az = THREE.MathUtils.degToRad(rumbo), el2 = THREE.MathUtils.degToRad(elev);
    const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el2), Math.sin(el2), -Math.cos(az) * Math.cos(el2));
    const c = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(pts.length), tgt = c.clone(), v = new THREE.Vector3();
    const tanV = Math.tan(THREE.MathUtils.degToRad(cam.fov / 2)), zx = (z.x0 + z.x1) / 2, zy = (z.y0 + z.y1) / 2, zw = (z.x1 - z.x0) * margen, zh = (z.y1 - z.y0) * margen;
    let D = minDist;
    const bounds = () => pts.reduce((b, p) => { v.copy(p).project(cam); return [Math.min(b[0], v.x), Math.max(b[1], v.x), Math.min(b[2], v.y), Math.max(b[3], v.y), b[4] || v.z > 1]; }, [9, -9, 9, -9, false]);
    const colocar = () => { cam.position.copy(tgt).addScaledVector(dir, D); cam.lookAt(tgt); cam.updateMatrixWorld(); };
    for (let it = 0; it < 3; it++) {
      for (D = minDist; D < 60000; D *= 1.05) { colocar(); const [x0, x1, y0, y1, atras] = bounds(); if (!atras && x1 - x0 <= zw && y1 - y0 <= zh) break; }
      const [x0, x1, y0, y1] = bounds(), right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
      // corre el objetivo para que el centro de lo encuadrado caiga en el centro de la zona libre
      tgt.addScaledVector(right, (((x0 + x1) / 2 - zx) * D * tanV * cam.aspect)).addScaledVector(up, (((y0 + y1) / 2 - zy) * D * tanV));
    }
    colocar();
    st.controls.maxDistance = Math.max(st.controls.maxDistance, D * 2);
    st.userMoved = false;
    st.flyTo(cam.position.toArray(), tgt.toArray(), duracion);
    return D;
  }

  // ---------------------------------------------------------------- colores del tema (CSS) para materiales y líneas
  const css = (n) => new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888888');
  const tenidos = [];   // [material, variable CSS, ¿también el brillo propio?]
  function tenir(m, n, emisivo = false) { tenidos.push([m, n, emisivo]); m.color.copy(css(n)); if (emisivo && m.emissive) m.emissive.copy(css(n)); return m; }

  // ---------------------------------------------------------------- tema
  onTheme((t) => {
    tenidos.forEach(([m, n, e]) => { m.color.copy(css(n)); if (e && m.emissive) m.emissive.copy(css(n)); });
    ctxMats.wall.color.copy(t.wall); ctxMats.roof.color.copy(t.wall); B.ground.color.copy(t.ground.clone().lerp(new THREE.Color('#7f9a5a'), 0.18)); B.road.color.copy(t.ground.clone().lerp(t.ink, 0.22));
    B.water.color.copy(t.water); B.cano.color.copy(t.water); B.rio.color.copy(t.water); M.muro.color.copy(t.wall); M.agua.color.copy(t.water);
  });

  return {
    st, S, T, M, el, edificios, huellas, listoHuellas, zonasHoy, puente,
    capa: nuevaCapa, capas, etiqueta, linea, flujo, encuadrar, zona, sincronizarEtiquetas, css, tenir, contextoGris,
    colorModulo: (id) => css(`--m-${id}`),
    // muestra solo las capas pedidas (las demás se ocultan) y devuelve las que acaban de aparecer
    verCapas(ids) {
      const quiero = new Set(ids), nuevas = [];
      capas.forEach((g, id) => { const v = quiero.has(id); if (v && !g.visible) nuevas.push(id); g.visible = v; });
      sincronizarEtiquetas(); st.updateShadows();
      return nuevas;
    },
    soloEtiquetas(ids) { soloCapas = ids ? new Set(ids.map((id) => capas.get(id)).filter(Boolean)) : null; sincronizarEtiquetas(); },
    // estado de una zona de intervención: true muestra las casas de hoy, false las oculta (el proyecto ocupa el lote)
    verHoy(id, v) { const z = zonasHoy.find((zz) => zz.id === id); if (z) { z.grupo.visible = v; st.updateShadows(); } },
    modoEdificio(id, capa, sin = []) {
      const it = edificios.get(id); if (!it) return;
      it.modo = { capa, sin }; aplicarModo(it); st.updateShadows();
    },
    alCargarEdificio(id, fn) { const it = edificios.get(id); if (!it) return; if (it.cargado) fn(it); else it.listo.push(fn); },
    cajaEdificio(id) { const it = edificios.get(id); if (!it) return null; return it.cargado ? solidBox(it.lod) : new THREE.Box3().setFromObject(it.ph); },
  };
}

// cintas de ancho variable (calles, caños) en una sola geometría
function cintas(lines, h) {
  const pos = [], idx = [];
  for (const l of lines) {
    const p = l.p, w = l.ancho / 2;
    for (let i = 0; i < p.length; i++) {
      const a = p[Math.max(0, i - 1)], b = p[Math.min(p.length - 1, i + 1)];
      let dx = b[0] - a[0], dy = b[1] - a[1]; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
      const k = pos.length / 3;
      pos.push(p[i][0] - dy * w, h, -(p[i][1] + dx * w), p[i][0] + dy * w, h, -(p[i][1] - dx * w));
      if (i) idx.push(k - 2, k, k - 1, k - 1, k, k + 1);
    }
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}
