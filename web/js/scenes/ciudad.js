// Escena 3D: el casco urbano de Yondó con las réplicas de cada dependencia pública en su posición real
// (levantadas con satélite y Street View) y el conmutador "Hoy / Con el proyecto" que muestra las
// adecuaciones: solar en cubiertas, marquesinas, baterías, inversores, cubiertas nuevas y cargadores.
// Se recorre sede por sede (‹ ›, flechas del teclado, la lista o doble clic) y cada sede muestra su conexión:
// tablero con medidor bidireccional, gateway IoT y enlace de datos al centro de control (CCED) en la alcaldía.
import { THREE, Stage, engine, tokens, onTheme, mat, arc, fmtN, fmtCOP, gsap, solidBox, conexionLabels } from '../core.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS, CALLES, MICRORRED, RED } from '../data.js';

// cámara inicial que mete todas las sedes urbanas en pantalla (con margen para las etiquetas), mirando desde el
// sur a ~55° de elevación: busca la distancia y recentra el objetivo sobre la caja proyectada
function encuadre(urb, cx, cy) {
  // se encuadra para la proporción de escritorio; en pantallas angostas Stage aleja la cámara (fit: 1)
  const asp = 1.5;
  const c = new THREE.PerspectiveCamera(38, asp, 1, 5000), dir = new THREE.Vector3(-0.2, 0.82, 0.54).normalize();
  const pts = (urb.length ? urb : [{ x: 0, y: 0 }]).map((e) => new THREE.Vector3(e.x, 8, -e.y));
  const tgt = new THREE.Vector3(cx, 0, -cy), v = new THREE.Vector3(), right = new THREE.Vector3();
  const fwd = new THREE.Vector3(-dir.x, 0, -dir.z).normalize(), tanH = Math.tan(THREE.MathUtils.degToRad(19));
  let D = 300;
  const place = () => { c.position.copy(tgt).addScaledVector(dir, D); c.lookAt(tgt); c.updateMatrixWorld(); };
  const box = () => pts.reduce((b, p) => { v.copy(p).project(c); return [Math.min(b[0], v.x), Math.max(b[1], v.x), Math.min(b[2], v.y), Math.max(b[3], v.y)]; }, [1, -1, 1, -1]);
  for (let it = 0; it < 3; it++) {
    for (D = 250; D < 1450; D *= 1.04) { place(); const [x0, x1, y0, y1] = box(); if (x0 > -0.8 && x1 < 0.8 && y0 > -0.78 && y1 < 0.72) break; }
    const [x0, x1, y0, y1] = box();
    right.setFromMatrixColumn(c.matrixWorld, 0).setY(0).normalize();
    tgt.addScaledVector(right, ((x0 + x1) / 2) * D * tanH * asp).addScaledVector(fwd, (((y0 + y1) / 2 + 0.03) * D * tanH) / dir.y);
  }
  place();
  return { cam: c.position.toArray(), target: tgt.toArray() };
}

// recorrido: de la alcaldía a la sede más cercana y así sucesivamente; la planta rural queda de última
function recorrido(list) {
  const rest = [...list], out = [];
  let cur = rest.find((e) => e.id === 'alcaldia') || rest[0];
  while (cur) {
    out.push(cur); rest.splice(rest.indexOf(cur), 1);
    const c = cur; cur = rest.sort((a, b) => Math.hypot(a.x - c.x, a.y - c.y) - Math.hypot(b.x - c.x, b.y - c.y))[0];
  }
  return out;
}

const NAV = `<div class="nav3d" role="toolbar" aria-label="Recorrido por las sedes">
  <button type="button" data-nav="prev" aria-label="Sede anterior" title="Sede anterior (←)">‹</button>
  <span class="nav3d-name" aria-live="polite">Vista general</span>
  <button type="button" data-nav="next" aria-label="Sede siguiente" title="Sede siguiente (→)">›</button>
  <button type="button" data-nav="home" title="Vista general (Esc)">Todo</button>
  <button type="button" data-nav="spin" aria-pressed="false" title="Girar alrededor de la sede">Girar</button>
  <span class="sep" aria-hidden="true"></span>
  <button type="button" data-nav-modo="hoy" aria-pressed="false">Hoy</button>
  <button type="button" data-nav-modo="proyecto" aria-pressed="true">Proyecto</button>
</div>
<div class="leyenda3d" aria-hidden="true"><span><i class="ln pw"></i>Red eléctrica propuesta (km por la vía)</span><span><i class="ln"></i>Enlace de datos al CCED</span><span><i class="pt pw"></i>Tablero y medidor bidireccional</span><span><i class="pt dt"></i>Gateway IoT</span></div>`;

export function mount(root) {
  const el = root.querySelector('.stage');
  el.insertAdjacentHTML('beforeend', NAV);
  const lista = recorrido(EDIFICIOS);
  // encuadre inicial: centro y extensión de las sedes levantadas
  // las sedes rurales (acueducto, a ~2 km) quedan fuera del encuadre inicial; se llega a ellas desde la lista
  const urb = lista.filter((e) => Math.hypot(e.x, e.y) < 900);
  const xs = urb.map((e) => e.x), ys = urb.map((e) => e.y);
  const farR = Math.max(1500, ...lista.map((e) => Math.hypot(e.x, e.y) + 400));
  const cx = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0, cy = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : 0;
  const vista = encuadre(urb, cx, cy);
  const st = new Stage(el, { ...vista, fov: 38, minDist: 6, maxDist: 1500, fit: 1, declutter: ['lbl-node', 'lbl-km'], tone: 'aces', exposure: 1.05, sky: true, fog: { near: farR * 0.6, far: farR } });
  st.camera.far = 5000; st.camera.updateProjectionMatrix();
  // la rueda acerca hacia donde apunta el cursor y el arrastre con clic derecho se desliza sobre el piso
  Object.assign(st.controls, { zoomToCursor: true, screenSpacePanning: false, zoomSpeed: 1.15 });
  const sc = st.sunLight.shadow.camera; Object.assign(sc, { left: -520, right: 520, top: 520, bottom: -520, near: 1, far: 1600 });
  st.sunLight.position.set(260, 520, 180); st.sunLight.shadow.mapSize.set(4096, 4096); st.sunLight.shadow.normalBias = 0.6;
  const T = tokens();
  const S = st.scene;
  // capas planas del piso con polygonOffset: sin él, calles, caños y agua titilan contra el terreno a la distancia
  const capa = (m, k) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const M = {
    ground: mat(T.ground), block: mat(T.surface, { roughness: 1 }),
    road: capa(mat(T.ground.clone().lerp(T.ink, 0.22), { roughness: 0.95, side: THREE.DoubleSide }), 2),
    water: capa(mat(T.water, { roughness: 0.25, metalness: 0.1, side: THREE.DoubleSide }), 1),
    cano: capa(mat(T.water, { roughness: 0.25, metalness: 0.1, side: THREE.DoubleSide }), 3),
  };

  // terreno, calles (cintas con ancho por jerarquía) y agua desde OpenStreetMap
  const ground = new THREE.Mesh(new THREE.CircleGeometry(farR, 96), M.ground); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true; S.add(ground);
  const ribbon = (lines, y) => {
    const pos = [], idx = [];
    for (const l of lines) {
      const p = l.p, w = l.ancho / 2;
      for (let i = 0; i < p.length; i++) {
        const a = p[Math.max(0, i - 1)], b = p[Math.min(p.length - 1, i + 1)];
        let dx = b[0] - a[0], dy = b[1] - a[1]; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
        const k = pos.length / 3;
        pos.push(p[i][0] - dy * w, y, -(p[i][1] + dx * w), p[i][0] + dy * w, y, -(p[i][1] - dx * w));
        if (i) idx.push(k - 2, k, k - 1, k - 1, k, k + 1);
      }
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
    return g;
  };
  const roads = new THREE.Mesh(ribbon(CALLES.calles, 0.02), M.road); roads.receiveShadow = true; S.add(roads);
  const canos = new THREE.Mesh(ribbon(CALLES.canos, 0.04), M.cano); S.add(canos);
  CALLES.agua.forEach((a) => {
    const sh = new THREE.Shape(a.p.map(([x, y]) => new THREE.Vector2(x, y)));
    (a.huecos || []).forEach((h) => sh.holes.push(new THREE.Path(h.map(([x, y]) => new THREE.Vector2(x, y)))));
    const g = new THREE.ShapeGeometry(sh); g.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(g, M.water); m.position.y = 0; S.add(m); st.freeze(m);
  });
  st.freeze(ground); st.freeze(roads); st.freeze(canos);

  // contexto: casas y locales del casco urbano a partir de huellas abiertas (Microsoft, ODbL), con alturas de 1–2 pisos
  const ctxMats = { wall: mat(T.wall, { roughness: 0.95 }), roof: mat(T.roof, { roughness: 0.9 }) };
  fetch(new URL('../../models/contexto/huellas.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((hu) => {
    if (!hu?.poligonos?.length) return;
    const boxes = lista.map((e) => { const [sx, , sz] = e.tamano || [20, 8, 20]; return [e.x, e.y, sx / 2 + 1, sz / 2 + 1]; });
    const wp = [], rp = [];
    hu.poligonos.forEach((flat, k) => {
      const pts = []; for (let i = 0; i < flat.length; i += 2) pts.push(new THREE.Vector2(flat[i], flat[i + 1]));
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length, cy = pts.reduce((a, p) => a + p.y, 0) / pts.length;
      if (boxes.some(([bx, by, hx, hy]) => Math.abs(cx - bx) < hx && Math.abs(cy - by) < hy)) return;
      const area = Math.abs(THREE.ShapeUtils.area(pts));
      const h = 2.9 + (area > 160 ? 2.6 : 0) + ((k * 2654435761) % 5) * 0.25;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], b = pts[(i + 1) % pts.length];
        wp.push(a.x, 0, -a.y, b.x, 0, -b.y, b.x, h, -b.y, a.x, 0, -a.y, b.x, h, -b.y, a.x, h, -a.y);
      }
      THREE.ShapeUtils.triangulateShape(pts, []).forEach((t) => t.forEach((j) => rp.push(pts[j].x, h, -pts[j].y)));
    });
    const mk = (arr, m) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3)); g.computeVertexNormals(); const o = new THREE.Mesh(g, m); o.castShadow = true; o.receiveShadow = true; m.side = THREE.DoubleSide; S.add(o); st.freeze(o); return o; };
    mk(wp, ctxMats.wall); mk(rp, ctxMats.roof);
    st.updateShadows();
  }).catch(() => {});

  // réplicas de las sedes con dos niveles de detalle; mientras cargan se ve un volumen provisional
  let proyecto = true, actual = null, girar = false;
  const items = lista.map((e) => {
    const g = new THREE.Group(); g.position.set(e.x, 0, -e.y); S.add(g);
    const [sx, sy, sz] = e.tamano || [20, 8, 20];
    const ph = new THREE.Mesh(new THREE.BoxGeometry(Math.max(4, sx - 4), Math.max(3, sy - 3), Math.max(4, sz - 4)), mat(T.wall, { transparent: true, opacity: 0.55 }));
    ph.position.y = Math.max(3, sy - 3) / 2; g.add(ph);
    const it = { e, g, ph, lod: null, loaded: false, caja: null };
    if (e.archivo) {
      // el detalle completo se ve hasta ~260 m (también al enfocar la sede); más lejos, la versión liviana
      it.lod = progressiveLOD([{ url: e.archivo, distance: 0 }, { url: e.archivo_lod1, distance: 260 }], (lod) => {
        ph.visible = false; it.loaded = true; it.caja = null; applyMode(lod, false); st.updateShadows();
      });
      g.add(it.lod);
    }
    it.lab = st.label(`<b>${e.corto || e.nombre}</b>${e.kwp_factible ? `<br><small>${fmtN(e.kwp_factible, 0)} kWp${e.bess ? ` · ${fmtN(e.bess.kwh)} kWh` : ''}</small>` : ''}`, 'lbl-node', [0, sy + 4, 0], g);
    it.lab.element.style.pointerEvents = 'auto'; it.lab.element.style.cursor = 'pointer';
    it.lab.element.addEventListener('click', () => select(it));
    // puntos de la conexión (los exporta el generador en el manifiesto); se muestran con la sede seleccionada
    const cn = e.conexion || {};
    it.gw = new THREE.Vector3(...(cn.gateway || [0, sy + 1.5, 0]));
    it.cx = conexionLabels(st, cn, g, (pos) => acercar(it, pos));
    it.cx.forEach((l) => { l.visible = false; });
    st.pickable(g, { onPick: () => select(it), onEnter: () => it.lab.element.classList.add('hover'), onLeave: () => it.lab.element.classList.remove('hover') });
    return it;
  });
  const caja = (it) => it.caja || (it.caja = it.loaded ? solidBox(it.lod) : new THREE.Box3().setFromObject(it.ph));

  const v3 = new THREE.Vector3();
  st.onFrame(() => { items.forEach((it) => it.lod?.update(st.camera)); return false; });

  // red de datos MinTIC: cada sede reporta al CCED (alcaldía) por fibra o radio. Trazo de ancho fijo en pantalla
  // (se lee igual de cerca que a 1 km) y guiones que avanzan hacia la alcaldía para que se entienda el sentido
  const hub = items.find((it) => it.e.id === 'alcaldia') || items[0];
  const enlaces = new THREE.Group(); S.add(enlaces);
  const links = hub ? items.filter((it) => it !== hub).map((it) => {
    const a = it.gw.clone().add(it.g.position), b = hub.gw.clone().add(hub.g.position);
    const pts = arc(a.toArray(), b.toArray(), Math.min(140, 18 + a.distanceTo(b) * 0.12)).getPoints(72).flatMap((p) => [p.x, p.y, p.z]);
    const geo = new LineGeometry(); geo.setPositions(pts);
    const base = new Line2(geo, new LineMaterial({ color: T.data, linewidth: 2, transparent: true, opacity: 0.45, depthWrite: false }));
    const dash = new Line2(geo, new LineMaterial({ color: T.data, linewidth: 3.5, dashed: true, dashSize: 10, gapSize: 14, transparent: true, depthWrite: false }));
    dash.computeLineDistances();
    enlaces.add(base, dash);
    return { it, base, dash };
  }) : [];
  let showFlows = true;
  st.onFrame((dt) => {
    st.controls.autoRotate = girar && !st.flying; st.controls.autoRotateSpeed = 0.7;
    if (!showFlows || !links.length) return false;
    const w = el.clientWidth, h = el.clientHeight;
    links.forEach((l) => { l.base.material.resolution.set(w, h); l.dash.material.resolution.set(w, h); l.dash.material.dashOffset -= dt * 28; });
    return true;
  });
  // red eléctrica propuesta: árbol de mínima longitud por las vías (scripts/geo/red_distancias.py), cada tramo con su
  // distancia por la vía en km; trazo de ancho fijo en pantalla en el color de la potencia
  const redG = new THREE.Group(); S.add(redG);
  const nombreDe = (id) => lista.find((e) => e.id === id)?.corto || RED?.puntos?.find((p) => p.id === id)?.nombre || id;
  const tramos = (RED?.arbol?.tramos || []).map((t) => {
    const geo = new LineGeometry(); geo.setPositions(t.ruta.flatMap(([x, y]) => [x, 0.9, -y]));
    const line = new Line2(geo, new LineMaterial({ color: T.power, linewidth: 3, transparent: true, opacity: 0.95, depthWrite: false }));
    redG.add(line);
    // la etiqueta va en la mitad del recorrido (por longitud), no en la mitad de la recta
    const seg = t.ruta.slice(1).map((q, k) => Math.hypot(q[0] - t.ruta[k][0], q[1] - t.ruta[k][1])), L = seg.reduce((a, b) => a + b, 0);
    let acc = 0, mid = t.ruta[0];
    for (let k = 0; k < seg.length; k++) { if (acc + seg[k] >= L / 2) { const u = (L / 2 - acc) / (seg[k] || 1), a = t.ruta[k], b = t.ruta[k + 1]; mid = [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]; break; } acc += seg[k]; }
    const lab = st.label(`${fmtN(t.km_via, 2)} km`, 'lbl-km', [mid[0], 4, -mid[1]], redG);
    lab.element.title = `${nombreDe(t.de)} → ${nombreDe(t.a)}: ${fmtN(t.km_via, 3)} km por la vía (${fmtN(t.km_recta, 3)} km en línea recta)`;
    return { t, line, lab };
  });
  // infraestructura de la red propuesta: postes de concreto de 12 m con cruceta y tres aisladores, tres conductores con
  // flecha entre postes y un transformador en el poste más cercano a cada sede. Postes a 4 m del eje de la vía, cada
  // ~40 m en el casco urbano y ~70 m en la zona rural; donde varios tramos comparten calle se reutiliza el poste
  const postes = [], spans = new Set(), trafo = new Set();
  const posteCerca = (x, z) => postes.findIndex((p) => Math.hypot(p.x - x, p.z - z) < 14);
  const ponerPoste = (x, y, dx, dy) => { const z = -y, k = posteCerca(x, z); if (k >= 0) return k; postes.push({ x, z, dx, dz: -dy }); return postes.length - 1; };
  for (const r of tramos) {
    const pts = r.t.ruta.slice(1, -1); if (pts.length < 2) continue;
    const ids = []; let next = 0, acc = 0;
    for (let k = 0; k < pts.length - 1; k++) {
      const [x0, y0] = pts[k], [x1, y1] = pts[k + 1], L = Math.hypot(x1 - x0, y1 - y0); if (L < 0.5) continue;
      const ux = (x1 - x0) / L, uy = (y1 - y0) / L, vano = Math.hypot(x0, y0) < 1000 ? 40 : 70;
      while (next <= acc + L) { const s = next - acc; ids.push(ponerPoste(x0 + ux * s + uy * 4, y0 + uy * s - ux * 4, ux, uy)); next += vano; }
      acc += L;
    }
    const [xe, ye] = pts[pts.length - 1], [xp, yp] = pts[pts.length - 2], Le = Math.hypot(xe - xp, ye - yp) || 1;
    ids.push(ponerPoste(xe + ((ye - yp) / Le) * 4, ye - ((xe - xp) / Le) * 4, (xe - xp) / Le, (ye - yp) / Le));
    trafo.add(ids[ids.length - 1]);
    for (let k = 0; k < ids.length - 1; k++) if (ids[k] !== ids[k + 1]) spans.add(ids[k] < ids[k + 1] ? `${ids[k]}-${ids[k + 1]}` : `${ids[k + 1]}-${ids[k]}`);
  }
  if (postes.length) {
    const H = 12, yC = 11.35, fases = [-1.0, 0, 1.0];
    const mPoste = mat(new THREE.Color('#a9aba5'), { roughness: 0.9 }), mHerraje = mat(new THREE.Color('#8d949b'), { roughness: 0.45, metalness: 0.6 });
    const mAisl = mat(new THREE.Color('#dcd6c8'), { roughness: 0.35 }), mTrafo = mat(new THREE.Color('#7f878e'), { roughness: 0.5, metalness: 0.4 });
    const gPoste = new THREE.CylinderGeometry(0.1, 0.17, H, 8).translate(0, H / 2, 0);
    const gCruceta = mergeGeometries([new THREE.BoxGeometry(2.4, 0.1, 0.1).translate(0, yC, 0), new THREE.BoxGeometry(0.06, 0.06, 0.9).rotateX(0.75).translate(0.55, yC - 0.33, 0), new THREE.BoxGeometry(0.06, 0.06, 0.9).rotateX(0.75).translate(-0.55, yC - 0.33, 0)].map((g) => g.toNonIndexed()));
    const gAisl = mergeGeometries(fases.map((f) => new THREE.CylinderGeometry(0.06, 0.08, 0.28, 8).translate(f, yC + 0.19, 0).toNonIndexed()));
    const gTrafo = mergeGeometries([new THREE.CylinderGeometry(0.36, 0.36, 0.95, 14).translate(0, 9.3, 0.5), new THREE.BoxGeometry(0.3, 0.12, 0.3).translate(0, 8.75, 0.32), new THREE.CylinderGeometry(0.04, 0.04, 0.3, 6).translate(0, 9.92, 0.5)].map((g) => g.toNonIndexed()));
    const inst = (g, m, idx) => {
      const im = new THREE.InstancedMesh(g, m, idx.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
      idx.forEach((k, i) => { const p = postes[k]; q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.atan2(p.dx, p.dz)); m4.compose(new THREE.Vector3(p.x, 0, p.z), q, new THREE.Vector3(1, 1, 1)); im.setMatrixAt(i, m4); });
      im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); redG.add(im); st.freeze(im); return im;
    };
    const todos = postes.map((_, k) => k);
    inst(gPoste, mPoste, todos); inst(gCruceta, mHerraje, todos); inst(gAisl, mAisl, todos); inst(gTrafo, mTrafo, [...trafo]);
    // conductores: tres fases por vano con flecha, medidas sobre la perpendicular del vano (no se cruzan)
    const pos = [];
    for (const key of spans) {
      const [a, b] = key.split('-').map(Number), A = postes[a], B = postes[b], L = Math.hypot(B.x - A.x, B.z - A.z); if (L < 1) continue;
      const px = -(B.z - A.z) / L, pz = (B.x - A.x) / L, sag = 0.3 + L * 0.006;
      for (const f of fases) {
        let prev = null;
        for (let i = 0; i <= 8; i++) {
          const u = i / 8, x = A.x + (B.x - A.x) * u + px * f, z = A.z + (B.z - A.z) * u + pz * f, y = yC + 0.3 - sag * 4 * u * (1 - u);
          if (prev) pos.push(...prev, x, y, z); prev = [x, y, z];
        }
      }
    }
    const gC = new THREE.BufferGeometry(); gC.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    const cond = new THREE.LineSegments(gC, new THREE.LineBasicMaterial({ color: 0x2c3036, transparent: true, opacity: 0.85 }));
    redG.add(cond); st.freeze(cond);
    st.updateShadows();
  }
  let showRed = true;
  const verRed = (v) => { showRed = v; redG.visible = v; tramos.forEach((r) => { r.lab.visible = v; }); st.invalidate(); };
  st.onFrame(() => { if (showRed) tramos.forEach((r) => r.line.material.resolution.set(el.clientWidth, el.clientHeight)); return false; });
  function resaltar(it) {
    tramos.forEach((r) => {
      const on = !it || r.t.de === it.e.id || r.t.a === it.e.id;
      r.line.material.opacity = on ? 0.95 : 0.25; r.line.material.linewidth = it && on ? 5 : 3;
      r.lab.element.classList.toggle('dim', !on);
    });
    links.forEach((l) => {
      const on = !it || it === hub || l.it === it;
      l.base.material.opacity = on ? 0.5 : 0.1; l.dash.material.opacity = on ? 1 : 0.14;
      l.dash.material.linewidth = l.it === it ? 5.5 : 3.5; l.base.material.linewidth = l.it === it ? 3 : 2;
    });
  }

  function applyMode(obj, animate = true) {
    obj.traverse((o) => {
      if (o.name === 'adecuaciones') {
        if (animate && gsap && proyecto) { o.visible = true; gsap.fromTo(o.scale, { y: 0.01 }, { y: 1, duration: 0.9, ease: 'back.out(1.6)', onUpdate: () => st.invalidate() }); }
        else o.visible = proyecto;
      }
      if (o.name === 'cubierta_actual' && o.userData.reemplazada) o.visible = !proyecto;
      if (o.userData.demoler) o.visible = !proyecto; // lo que el proyecto demuele
    });
  }
  const modeBtns = root.querySelectorAll('[data-modo-ciudad], [data-nav-modo]');
  modeBtns.forEach((b) => b.addEventListener('click', () => {
    proyecto = (b.dataset.modoCiudad || b.dataset.navModo) === 'proyecto';
    modeBtns.forEach((x) => x.setAttribute('aria-pressed', String((x.dataset.modoCiudad || x.dataset.navModo) === (proyecto ? 'proyecto' : 'hoy'))));
    items.forEach((it) => { if (it.lod) applyMode(it.lod, true); it.cx.forEach((l) => { l.visible = it === actual && proyecto; }); });
    st.updateShadows();
  }));
  root.querySelector('#cd-flujos')?.addEventListener('change', (ev) => { showFlows = ev.target.checked; enlaces.visible = showFlows; st.invalidate(); });
  root.querySelector('#cd-red')?.addEventListener('change', (ev) => verRed(ev.target.checked));
  root.querySelector('#cd-etiquetas')?.addEventListener('change', (ev) => { items.forEach((it) => { it.lab.element.hidden = !ev.target.checked; }); st.invalidate(); });

  // anillo en el piso que marca la sede elegida
  // (trazo de ancho fijo en pantalla: se ve fino de cerca y de lejos)
  const anilloGeo = new LineGeometry();
  anilloGeo.setPositions(Array.from({ length: 129 }, (_, i) => { const a = (i / 128) * Math.PI * 2; return [Math.cos(a), 0, Math.sin(a)]; }).flat());
  const anillo = new Line2(anilloGeo, new LineMaterial({ color: T.accent, linewidth: 2.5, transparent: true, opacity: 0.95, depthWrite: false }));
  anillo.visible = false; S.add(anillo);
  st.onFrame(() => { anillo.material.resolution.set(el.clientWidth, el.clientHeight); return false; });

  // encuadre de una sede: su volumen cabe en pantalla; se conserva el rumbo con que se venía mirando (no
  // desorienta al pasar de una sede a otra) y la cámara queda a 30° de elevación
  function enfocar(it) {
    const box = caja(it), c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const rad = Math.max(14, Math.hypot(size.x, size.z) / 2);
    const h = v3.copy(st.camera.position).sub(st.controls.target).setY(0);
    if (h.lengthSq() < 1) h.set(-0.35, 0, 1);
    h.normalize();
    const elev = THREE.MathUtils.degToRad(30);
    st.frameBox(box, new THREE.Vector3(h.x * Math.cos(elev), Math.sin(elev), h.z * Math.cos(elev)), { margin: 0.72, duration: 1.5, ty: 0.3 });
    anillo.position.set(c.x, 0.3, c.z); anillo.scale.setScalar(rad * 1.02); anillo.visible = true;
    if (gsap) gsap.fromTo(anillo.material, { opacity: 0 }, { opacity: 0.95, duration: 0.5, delay: 1, onUpdate: () => st.invalidate() });
  }

  // primer plano de la conexión: afuera, frente al tablero, a ~13 m y con línea de vista libre
  function acercar(it, pos) {
    const p = new THREE.Vector3(...pos).add(it.g.position), c = caja(it).getCenter(new THREE.Vector3());
    const out = p.clone().sub(c).setY(0);
    if (out.lengthSq() < 1) out.set(0, 0, 1);
    p.y = Math.max(1, p.y - 1.4);
    st.closeUp(p, [it.g], out.normalize(), { dist: 13 });
  }

  // barra de recorrido sobre el escenario, teclado y doble clic
  const nav = el.querySelector('.nav3d'), nombre = nav.querySelector('.nav3d-name');
  const paso = (d) => select(items[((actual ? items.indexOf(actual) : d > 0 ? -1 : 0) + d + items.length) % items.length]);
  nav.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-nav]'); if (!b) return;
    if (b.dataset.nav === 'prev') paso(-1);
    else if (b.dataset.nav === 'next') paso(1);
    else if (b.dataset.nav === 'home') general();
    else if (b.dataset.nav === 'spin') { girar = !girar; b.setAttribute('aria-pressed', String(girar)); st.invalidate(); }
  });
  addEventListener('keydown', (ev) => {
    if (root.hidden || !st.isActive() || !st.inView || ev.altKey || ev.ctrlKey || ev.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;
    if (ev.key === 'ArrowRight') { paso(1); ev.preventDefault(); }
    else if (ev.key === 'ArrowLeft') { paso(-1); ev.preventDefault(); }
    else if (ev.key === 'Escape' && actual) general();
  });
  const piso = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), pt = new THREE.Vector3();
  el.addEventListener('dblclick', (ev) => {
    if (!st.isActive() || ev.target !== engine.renderer.domElement) return;
    const o = st._hit(ev), it = o && items.find((x) => x.g === o);
    if (it) { enfocar(it); return; }
    if (!st.ray.ray.intersectPlane(piso, pt)) return;
    const off = st.camera.position.clone().sub(st.controls.target).multiplyScalar(0.55);
    st.flyTo(pt.clone().add(off).toArray(), pt.toArray(), 1.1);
  });

  // lista de sedes y ficha de detalle
  const list = root.querySelector('[data-slot="ciudad.lista"]');
  const card = root.querySelector('[data-slot="ciudad.ficha"]');
  const cardInicial = card.innerHTML;
  list.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}" aria-pressed="false">${it.e.corto || it.e.nombre}</button>`).join('') || '<p class="note">Aún no hay sedes levantadas.</p>';
  list.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => select(items[+b.dataset.i])));
  const node = (id) => MICRORRED.nodos.find((n) => n.id === id);
  const conf = { alta: 'Ubicación confirmada', media: 'Ubicación probable', baja: 'Ubicación por confirmar' };
  function marcar(it) {
    list.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(items[+b.dataset.i] === it)));
    items.forEach((x) => {
      x.lab.element.classList.toggle('on', x === it); x.lab.element.classList.toggle('dim', !!it && x !== it);
      x.cx.forEach((l) => { l.visible = x === it && proyecto; });
    });
    resaltar(it);
    nombre.textContent = it ? `${items.indexOf(it) + 1}/${items.length} · ${it.e.corto || it.e.nombre}` : 'Vista general';
  }
  function general() {
    actual = null; marcar(null); anillo.visible = false; card.innerHTML = cardInicial;
    const f = st.fitFactor(), [tx, ty, tz] = vista.target, [px, py, pz] = vista.cam;
    st.flyTo([tx + (px - tx) * f, ty + (py - ty) * f, tz + (pz - tz) * f], vista.target, 1.4);
  }
  function select(it) {
    actual = it; marcar(it); enfocar(it);
    const e = it.e, n = node(e.nodo_microrred);
    const fuentes = (e.fuentes || []).filter((f) => f.url).slice(0, 4);
    const pv = e.kwp_factible != null ? `<b>${fmtN(e.kwp_factible, 1)} kWp</b> en ${fmtN(e.modulos || 0)} módulos${e.kwp_plan != null ? ` · plan ${fmtN(e.kwp_plan, 0)} kWp` : ''}` : 'Sin arreglo solar';
    card.innerHTML = `<h4>${e.nombre}</h4>
      <p class="note">${conf[e.confianza] || ''}${e.direccion ? ` · ${e.direccion}` : ''}</p>
      <dl class="kv">
        <dt>Solar</dt><dd>${pv}</dd>
        ${e.bess ? `<dt>Baterías</dt><dd>${fmtN(e.bess.kwh)} kWh / ${fmtN(e.bess.kw)} kW${e.bess.tipo ? ` · ${e.bess.tipo.replace('_', ' ')}` : ''}</dd>` : ''}
        ${e.conexion ? `<dt>Conexión</dt><dd style="white-space:normal">${e.conexion.nota || ''}</dd>` : ''}
        ${n ? `<dt>Consumo</dt><dd>${fmtN(n.kwh_mes)} kWh/mes · prioridad ${n.prioridad}${n.isla ? ' · funciona en isla' : ''}</dd>` : ''}
        ${e.pisos ? `<dt>Edificio</dt><dd>${e.pisos}</dd>` : ''}
      </dl>
      ${e.conexion ? `<p><b>Cómo se conecta</b></p><ul class="cx-ruta"><li>Paneles → inversores${e.bess ? ' → baterías' : ''} → tablero con medidor bidireccional</li><li>Tablero → ${/poste/i.test(e.conexion.nota || '') ? 'poste de la red de EPM' : 'acometida de EPM en la fachada'}</li><li class="dt">Gateway IoT → enlace de datos al CCED (alcaldía)</li></ul><p><button type="button" class="btn ghost" data-cx-cerca>Ver la conexión de cerca</button></p>` : ''}
      ${e.obras_civiles?.length ? `<p><b>Obras previas</b></p><ul class="tight">${e.obras_civiles.map((x) => `<li>${x}</li>`).join('')}</ul>` : ''}
      ${e.domotica?.length ? `<p><b>Domótica</b></p><p class="note">${e.domotica.join(' · ')}</p>` : ''}
      ${e.notas ? `<p class="note">${e.notas}</p>` : ''}
      ${fuentes.length ? `<p><b>Ver el edificio real</b></p><p>${fuentes.map((f, k) => `<a href="${f.url}" target="_blank" rel="noopener">${f.tipo === 'street_view' ? `Street View${f.fecha ? ` (${f.fecha})` : ''}` : `Fuente ${k + 1}`}</a>`).join(' · ')}</p>` : ''}
      ${e.incertidumbres?.length ? `<details><summary>Lo que no se pudo verificar (${e.incertidumbres.length})</summary><ul class="tight">${e.incertidumbres.map((x) => `<li>${x}</li>`).join('')}</ul></details>` : ''}`;
    card.querySelector('[data-cx-cerca]')?.addEventListener('click', () => acercar(it, it.e.conexion.tablero));
    if (gsap) gsap.from(card, { opacity: 0, y: 8, duration: 0.35, ease: 'power2.out' });
  }

  // cifras del conjunto
  const tiles = root.querySelector('[data-slot="ciudad.tiles"]');
  const kwp = lista.reduce((a, e) => a + (e.kwp_factible || 0), 0), plan = lista.reduce((a, e) => a + (e.kwp_plan || 0), 0);
  const kwh = lista.reduce((a, e) => a + (e.bess?.kwh || 0), 0), mods = lista.reduce((a, e) => a + (e.modulos || 0), 0);
  tiles.innerHTML = `<div class="tile"><b data-n="${lista.length}">${lista.length}</b><span>Sedes modeladas</span></div>
    <div class="tile"><b data-n="${kwp.toFixed(0)}">${fmtN(kwp, 0)}</b><span>kWp que caben en las cubiertas reales${plan ? ` (plan ${fmtN(plan, 0)})` : ''}</span></div>
    <div class="tile"><b data-n="${mods}">${fmtN(mods)}</b><span>Módulos de 550 Wp</span></div>
    <div class="tile"><b data-n="${kwh}">${fmtN(kwh)}</b><span>kWh de baterías</span></div>`;
  root.querySelector('[data-slot="ciudad.tabla"]').innerHTML = `<table><thead><tr><th>Sede</th><th class="n">kWp plan</th><th class="n">kWp que caben</th><th class="n">Módulos</th><th class="n">Baterías kWh</th><th>Ubicación</th><th>Modelo</th></tr></thead><tbody>${lista.map((e) => `<tr><td>${e.nombre}</td><td class="n">${e.kwp_plan != null ? fmtN(e.kwp_plan, 0) : '—'}</td><td class="n">${e.kwp_factible != null ? fmtN(e.kwp_factible, 1) : '—'}</td><td class="n">${fmtN(e.modulos || 0)}</td><td class="n">${e.bess ? fmtN(e.bess.kwh) : '—'}</td><td>${e.confianza || '—'}</td><td class="note">${e.bytes ? `${fmtN(e.bytes / 1024, 0)} KB · ${fmtN(e.triangulos)} triángulos` : '—'}</td></tr>`).join('')}</tbody></table>`;

  // distancias por la vía y presupuesto de la red (si ya se calculó)
  const redSlot = root.querySelector('[data-slot="ciudad.red"]');
  if (redSlot && RED?.arbol) {
    const A = RED.arbol, P = RED.presupuesto;
    const costo = Object.fromEntries((P?.por_tramo || []).map((t) => [`${t.de}>${t.a}`, t]));
    const caps = P?.capitulos || [], maxCap = Math.max(1, ...caps.map((c) => c.total));
    redSlot.innerHTML = `<p class="note">${RED.metodo || ''}</p>
      <div class="tbl-wrap"><table><thead><tr><th>Tramo</th><th class="n">km por la vía</th><th class="n">km en línea recta</th><th class="n">km de red nueva</th>${P ? '<th class="n">Costo del tramo</th>' : ''}</tr></thead><tbody>
      ${A.tramos.map((t) => { const c = costo[`${t.de}>${t.a}`]; return `<tr><td>${nombreDe(t.de)} → ${nombreDe(t.a)}${c?.nota ? `<br><small class="note">${c.nota}</small>` : ''}</td><td class="n">${fmtN(t.km_via, 3)}</td><td class="n">${fmtN(t.km_recta, 3)}</td><td class="n">${fmtN(t.km_red_nueva, 3)}</td>${P ? `<td class="n">${c ? fmtCOP(c.costo_total) : '—'}</td>` : ''}</tr>`; }).join('')}
      <tr><td><b>Total de la red propuesta</b></td><td class="n">${fmtN(A.km_suma_tramos, 2)}</td><td></td><td class="n"><b>${fmtN(A.km_total_red, 2)} km</b></td>${P ? `<td class="n"><b>${fmtCOP(P.totales.total_cop_2026)}</b></td>` : ''}</tr></tbody></table></div>
      <p><button type="button" class="btn ghost" data-csv>Descargar matriz de distancias entre todas las sedes (CSV)</button></p>
      ${P ? `<h4>Presupuesto por capítulos (por mayores) e ítems (por menores)</h4>
        <p class="note">${fmtN(P.km_urbanos, 2)} km urbanos y ${fmtN(P.km_rurales, 2)} km rurales de red nueva · ${P.moneda} · ${P.precision}</p>
        <div class="barras">${caps.map((c) => `<details class="fold"><summary><span class="bar-l">${c.nombre}${c.unidad_resumen ? `<br><small class="note">${c.unidad_resumen}</small>` : ''}</span><span class="bar"><i style="width:${(100 * c.total) / maxCap}%"></i></span><span class="bar-v">${fmtCOP(c.total)}</span></summary>
          <div class="tbl-wrap"><table><thead><tr><th>Ítem</th><th>Und.</th><th class="n">Cantidad</th><th class="n">Valor unitario</th><th class="n">Total</th></tr></thead><tbody>
          ${c.items.map((i) => `<tr><td>${i.descripcion}${i.nota ? `<br><small class="note">${i.nota}</small>` : ''}</td><td>${i.unidad}</td><td class="n">${fmtN(i.cantidad, 2)}</td><td class="n">${fmtCOP(i.valor_unitario)}</td><td class="n">${fmtCOP(i.total)}</td></tr>`).join('')}
          </tbody></table></div></details>`).join('')}</div>
        <dl class="kv" style="margin-top:10px">${P.indirectos.map((i) => `<dt>${i.nombre} (${fmtN(i.porcentaje * 100, 1)} % de ${i.base})</dt><dd>${fmtCOP(i.total)}</dd>`).join('')}
          <dt><b>Total</b></dt><dd><b>${fmtCOP(P.totales.total_cop_2026)}</b></dd><dt>Rango (−30 % / +50 %)</dt><dd>${fmtCOP(P.totales.rango_cop_2026[0])} a ${fmtCOP(P.totales.rango_cop_2026[1])}</dd></dl>
        <details class="fold"><summary>Supuestos</summary><ul class="tight">${P.supuestos.map((x) => `<li>${x}</li>`).join('')}</ul></details>` : '<p class="note">El presupuesto por capítulos e ítems se agrega cuando terminen de verificarse los precios.</p>'}`;
    redSlot.querySelector('[data-csv]').addEventListener('click', () => {
      const ids = RED.puntos.map((p) => p.id), head = ['km por la vía', ...ids.map(nombreDe)];
      const rows = [head, ...RED.matriz_via_km.map((r, i) => [nombreDe(ids[i]), ...r.map((v) => String(v).replace('.', ','))])];
      const csv = '\ufeff' + rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(';')).join('\n');
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); a.download = 'yondo_distancias_km.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  }

  onTheme((t) => {
    ctxMats.wall.color.copy(t.wall); ctxMats.roof.color.copy(t.roof); M.ground.color.copy(t.ground); M.road.color.copy(t.ground.clone().lerp(t.ink, 0.22));
    M.water.color.copy(t.water); M.cano.color.copy(t.water); M.block.color.copy(t.surface); anillo.material.color.copy(t.accent);
    links.forEach((l) => { l.base.material.color.copy(t.data); l.dash.material.color.copy(t.data); });
    tramos.forEach((r) => r.line.material.color.copy(t.power));
  });
  return st;
}
