// Escena 3D: el casco urbano de Yondó con las réplicas de cada dependencia pública en su posición real
// (levantadas con satélite y Street View) y el conmutador "Hoy / Con el proyecto" que muestra las
// adecuaciones: solar en cubiertas, marquesinas, baterías, inversores, cubiertas nuevas y cargadores.
// Se recorre sede por sede (‹ ›, flechas del teclado, la lista o doble clic) y cada sede muestra su conexión:
// tablero con medidor bidireccional, gateway IoT y enlace de datos al centro de control (CCED) en la alcaldía.
import { THREE, Stage, engine, tokens, onTheme, mat, arc, fmtN, gsap, solidBox, conexionLabels } from '../core.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS, CALLES, MICRORRED } from '../data.js';

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
<div class="leyenda3d" aria-hidden="true"><span><i class="ln"></i>Enlace de datos al CCED</span><span><i class="pt pw"></i>Tablero y medidor bidireccional</span><span><i class="pt dt"></i>Gateway IoT</span></div>`;

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
  const st = new Stage(el, { ...vista, fov: 38, minDist: 6, maxDist: 1500, fit: 1, declutter: true, tone: 'aces', exposure: 1.05 });
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
  function resaltar(it) {
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

  onTheme((t) => {
    ctxMats.wall.color.copy(t.wall); ctxMats.roof.color.copy(t.roof); M.ground.color.copy(t.ground); M.road.color.copy(t.ground.clone().lerp(t.ink, 0.22));
    M.water.color.copy(t.water); M.cano.color.copy(t.water); M.block.color.copy(t.surface); anillo.material.color.copy(t.accent);
    links.forEach((l) => { l.base.material.color.copy(t.data); l.dash.material.color.copy(t.data); });
  });
  return st;
}
