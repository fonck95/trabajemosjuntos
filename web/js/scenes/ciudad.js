// Escena 3D: el casco urbano de Yondó con las réplicas de cada dependencia pública en su posición real
// (levantadas con satélite y Street View) y el conmutador "Hoy / Con el proyecto" que muestra las
// adecuaciones: solar en cubiertas, marquesinas, baterías, inversores, cubiertas nuevas y cargadores.
import { THREE, Stage, tokens, onTheme, mat, Flow, arc, fmtN, gsap } from '../core.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS, CALLES, MICRORRED } from '../data.js';

// cámara inicial que mete todas las sedes urbanas en pantalla (con margen para las etiquetas), mirando desde el
// sur a ~55° de elevación: busca la distancia y recentra el objetivo sobre la caja proyectada
function encuadre(urb, cx, cy, el) {
  const asp = Math.max(0.55, (el.clientWidth || 14) / (el.clientHeight || 10));
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

export function mount(root) {
  const el = root.querySelector('.stage');
  // encuadre inicial: centro y extensión de las sedes levantadas
  // las sedes rurales (acueducto, a ~2 km) quedan fuera del encuadre inicial; se llega a ellas desde la lista
  const urb = EDIFICIOS.filter((e) => Math.hypot(e.x, e.y) < 900);
  const xs = urb.map((e) => e.x), ys = urb.map((e) => e.y);
  const farR = Math.max(1500, ...EDIFICIOS.map((e) => Math.hypot(e.x, e.y) + 400));
  const cx = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0, cy = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : 0;
  const st = new Stage(el, { ...encuadre(urb, cx, cy, el), fov: 38, minDist: 25, maxDist: 1500, tone: 'aces', exposure: 1.05 });
  st.camera.far = 5000; st.camera.updateProjectionMatrix();
  const sc = st.sunLight.shadow.camera; Object.assign(sc, { left: -520, right: 520, top: 520, bottom: -520, near: 1, far: 1600 });
  st.sunLight.position.set(260, 520, 180); st.sunLight.shadow.mapSize.set(4096, 4096); st.sunLight.shadow.normalBias = 0.6;
  const T = tokens();
  const S = st.scene;
  const M = { ground: mat(T.ground), road: mat(T.ground.clone().lerp(T.ink, 0.22), { roughness: 0.95, side: THREE.DoubleSide }), water: mat(T.water, { roughness: 0.25, metalness: 0.1, side: THREE.DoubleSide }), block: mat(T.surface, { roughness: 1 }) };

  // terreno, calles (cintas con ancho por jerarquía) y agua desde OpenStreetMap
  const ground = new THREE.Mesh(new THREE.CircleGeometry(farR, 96), M.ground); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.05; ground.receiveShadow = true; S.add(ground);
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
  const canos = new THREE.Mesh(ribbon(CALLES.canos, 0.03), M.water); S.add(canos);
  CALLES.agua.forEach((a) => {
    const sh = new THREE.Shape(a.p.map(([x, y]) => new THREE.Vector2(x, y)));
    const g = new THREE.ShapeGeometry(sh); g.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(g, M.water); m.position.y = 0.01; S.add(m);
  });
  st.freeze(ground); st.freeze(roads); st.freeze(canos);

  // contexto: casas y locales del casco urbano a partir de huellas abiertas (Microsoft, ODbL), con alturas de 1–2 pisos
  const ctxMats = { wall: mat(T.wall, { roughness: 0.95 }), roof: mat(T.roof, { roughness: 0.9 }) };
  fetch(new URL('../../models/contexto/huellas.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((hu) => {
    if (!hu?.poligonos?.length) return;
    const boxes = EDIFICIOS.map((e) => { const [sx, , sz] = e.tamano || [20, 8, 20]; return [e.x, e.y, sx / 2 + 1, sz / 2 + 1]; });
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
  let proyecto = true;
  const items = EDIFICIOS.map((e) => {
    const g = new THREE.Group(); g.position.set(e.x, 0, -e.y); S.add(g);
    const [sx, sy, sz] = e.tamano || [20, 8, 20];
    const ph = new THREE.Mesh(new THREE.BoxGeometry(Math.max(4, sx - 4), Math.max(3, sy - 3), Math.max(4, sz - 4)), mat(T.wall, { transparent: true, opacity: 0.55 }));
    ph.position.y = Math.max(3, sy - 3) / 2; g.add(ph);
    const it = { e, g, ph, lod: null, loaded: false };
    if (e.archivo) {
      it.lod = progressiveLOD([{ url: e.archivo, distance: 0 }, { url: e.archivo_lod1, distance: 140 }], (lod) => {
        ph.visible = false; it.loaded = true; applyMode(lod, false); st.updateShadows();
      });
      g.add(it.lod);
    }
    const lab = st.label(`<b>${e.corto || e.nombre}</b>${e.kwp_factible ? `<br><small>${fmtN(e.kwp_factible, 0)} kWp${e.bess ? ` · ${fmtN(e.bess.kwh)} kWh` : ''}</small>` : ''}`, 'lbl-node', [0, sy + 4, 0], g);
    lab.element.style.pointerEvents = 'auto'; lab.element.style.cursor = 'pointer';
    lab.element.addEventListener('click', () => select(it));
    it.lab = lab;
    st.pickable(g, { onPick: () => select(it) });
    return it;
  });
  // etiquetas sin encimarse: de abajo hacia arriba en pantalla, la que choca con una ya puesta sube lo justo
  const v3 = new THREE.Vector3();
  function declutter() {
    const W = el.clientWidth, H = el.clientHeight, placed = [];
    items.map((it) => {
      const e = it.lab.element; it.lab.getWorldPosition(v3).project(st.camera);
      return { e, x: ((v3.x + 1) / 2) * W, y: ((1 - v3.y) / 2) * H, w: e.offsetWidth, h: e.offsetHeight, on: !e.hidden && v3.z < 1 };
    }).filter((r) => r.on && r.w).sort((a, b) => b.y - a.y).forEach((r) => {
      let y = r.y;
      for (let k = 0; k < 10; k++) {
        const hit = placed.find((p) => Math.abs(p.x - r.x) < (p.w + r.w) / 2 + 4 && Math.abs(p.y - y) < (p.h + r.h) / 2 + 3);
        if (!hit) break;
        y = hit.y - (hit.h + r.h) / 2 - 3;
      }
      placed.push({ ...r, y }); r.e.style.marginTop = y < r.y - 0.5 ? `${y - r.y}px` : '';
    });
  }
  st.onFrame(() => { items.forEach((it) => it.lod?.update(st.camera)); declutter(); return false; });

  // capa de datos MinTIC: cada sede reporta al centro de control (CCED, en la alcaldía)
  const hub = items.find((it) => it.e.id === 'alcaldia') || items[0];
  const flows = hub ? items.filter((it) => it !== hub).map((it) => new Flow(S, arc([it.e.x, 8, -it.e.y], [hub.e.x, 12, -hub.e.y], 40), T.data, { max: 14, size: 0.8, tube: 0.25 })) : [];
  let showFlows = true;
  flows.forEach((f) => f.set(0.6, 1));
  st.onFrame((dt) => { if (!showFlows) return false; flows.forEach((f) => f.update(dt, 1)); return flows.length > 0; });

  function applyMode(obj, animate = true) {
    obj.traverse((o) => {
      if (o.name === 'adecuaciones') {
        if (animate && gsap && proyecto) { o.visible = true; gsap.fromTo(o.scale, { y: 0.01 }, { y: 1, duration: 0.9, ease: 'back.out(1.6)', onUpdate: () => st.invalidate() }); }
        else o.visible = proyecto;
      }
      if (o.name === 'cubierta_actual' && o.userData.reemplazada) o.visible = !proyecto;
    });
  }
  const modeBtns = root.querySelectorAll('[data-modo-ciudad]');
  modeBtns.forEach((b) => b.addEventListener('click', () => {
    proyecto = b.dataset.modoCiudad === 'proyecto';
    modeBtns.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    items.forEach((it) => it.lod && applyMode(it.lod, true));
    st.updateShadows();
  }));
  root.querySelector('#cd-flujos')?.addEventListener('change', (ev) => { showFlows = ev.target.checked; flows.forEach((f) => f.visible(showFlows)); st.invalidate(); });
  root.querySelector('#cd-etiquetas')?.addEventListener('change', (ev) => { items.forEach((it) => { it.lab.element.hidden = !ev.target.checked; }); st.invalidate(); });

  // lista de sedes y ficha de detalle
  const list = root.querySelector('[data-slot="ciudad.lista"]');
  const card = root.querySelector('[data-slot="ciudad.ficha"]');
  list.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}" aria-pressed="false">${it.e.corto || it.e.nombre}</button>`).join('') || '<p class="note">Aún no hay sedes levantadas.</p>';
  list.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => select(items[+b.dataset.i])));
  const node = (id) => MICRORRED.nodos.find((n) => n.id === id);
  const conf = { alta: 'Ubicación confirmada', media: 'Ubicación probable', baja: 'Ubicación por confirmar' };
  function select(it) {
    const e = it.e, n = node(e.nodo_microrred);
    list.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(items[+b.dataset.i] === it)));
    const [sx, sy, sz] = e.tamano || [20, 8, 20], r = Math.max(sx, sz, 18);
    st.flyTo([e.x - r * 1.1, sy + r * 0.9, -e.y + r * 1.25], [e.x, sy * 0.3, -e.y], 1.6);
    const fuentes = (e.fuentes || []).filter((f) => f.url).slice(0, 4);
    const pv = e.kwp_factible != null ? `<b>${fmtN(e.kwp_factible, 1)} kWp</b> en ${fmtN(e.modulos || 0)} módulos${e.kwp_plan != null ? ` · plan ${fmtN(e.kwp_plan, 0)} kWp` : ''}` : 'Sin arreglo solar';
    card.innerHTML = `<h4>${e.nombre}</h4>
      <p class="note">${conf[e.confianza] || ''}${e.direccion ? ` · ${e.direccion}` : ''}</p>
      <dl class="kv">
        <dt>Solar</dt><dd>${pv}</dd>
        ${e.bess ? `<dt>Baterías</dt><dd>${fmtN(e.bess.kwh)} kWh / ${fmtN(e.bess.kw)} kW${e.bess.tipo ? ` · ${e.bess.tipo.replace('_', ' ')}` : ''}</dd>` : ''}
        ${n ? `<dt>Consumo</dt><dd>${fmtN(n.kwh_mes)} kWh/mes · prioridad ${n.prioridad}${n.isla ? ' · funciona en isla' : ''}</dd>` : ''}
        ${e.pisos ? `<dt>Edificio</dt><dd>${e.pisos}</dd>` : ''}
      </dl>
      ${e.obras_civiles?.length ? `<p><b>Obras previas</b></p><ul class="tight">${e.obras_civiles.map((x) => `<li>${x}</li>`).join('')}</ul>` : ''}
      ${e.domotica?.length ? `<p><b>Domótica</b></p><p class="note">${e.domotica.join(' · ')}</p>` : ''}
      ${e.notas ? `<p class="note">${e.notas}</p>` : ''}
      ${fuentes.length ? `<p><b>Ver el edificio real</b></p><p>${fuentes.map((f, k) => `<a href="${f.url}" target="_blank" rel="noopener">${f.tipo === 'street_view' ? `Street View${f.fecha ? ` (${f.fecha})` : ''}` : `Fuente ${k + 1}`}</a>`).join(' · ')}</p>` : ''}
      ${e.incertidumbres?.length ? `<details><summary>Lo que no se pudo verificar (${e.incertidumbres.length})</summary><ul class="tight">${e.incertidumbres.map((x) => `<li>${x}</li>`).join('')}</ul></details>` : ''}`;
    if (gsap) gsap.from(card, { opacity: 0, y: 8, duration: 0.35, ease: 'power2.out' });
  }

  // cifras del conjunto
  const tiles = root.querySelector('[data-slot="ciudad.tiles"]');
  const kwp = EDIFICIOS.reduce((a, e) => a + (e.kwp_factible || 0), 0), plan = EDIFICIOS.reduce((a, e) => a + (e.kwp_plan || 0), 0);
  const kwh = EDIFICIOS.reduce((a, e) => a + (e.bess?.kwh || 0), 0), mods = EDIFICIOS.reduce((a, e) => a + (e.modulos || 0), 0);
  tiles.innerHTML = `<div class="tile"><b data-n="${EDIFICIOS.length}">${EDIFICIOS.length}</b><span>Sedes modeladas</span></div>
    <div class="tile"><b data-n="${kwp.toFixed(0)}">${fmtN(kwp, 0)}</b><span>kWp que caben en las cubiertas reales${plan ? ` (plan ${fmtN(plan, 0)})` : ''}</span></div>
    <div class="tile"><b data-n="${mods}">${fmtN(mods)}</b><span>Módulos de 550 Wp</span></div>
    <div class="tile"><b data-n="${kwh}">${fmtN(kwh)}</b><span>kWh de baterías</span></div>`;
  root.querySelector('[data-slot="ciudad.tabla"]').innerHTML = `<table><thead><tr><th>Sede</th><th class="n">kWp plan</th><th class="n">kWp que caben</th><th class="n">Módulos</th><th class="n">Baterías kWh</th><th>Ubicación</th><th>Modelo</th></tr></thead><tbody>${EDIFICIOS.map((e) => `<tr><td>${e.nombre}</td><td class="n">${e.kwp_plan != null ? fmtN(e.kwp_plan, 0) : '—'}</td><td class="n">${e.kwp_factible != null ? fmtN(e.kwp_factible, 1) : '—'}</td><td class="n">${fmtN(e.modulos || 0)}</td><td class="n">${e.bess ? fmtN(e.bess.kwh) : '—'}</td><td>${e.confianza || '—'}</td><td class="note">${e.bytes ? `${fmtN(e.bytes / 1024, 0)} KB · ${fmtN(e.triangulos)} triángulos` : '—'}</td></tr>`).join('')}</tbody></table>`;

  onTheme((t) => { ctxMats.wall.color.copy(t.wall); ctxMats.roof.color.copy(t.roof); M.ground.color.copy(t.ground); M.road.color.copy(t.ground.clone().lerp(t.ink, 0.22)); M.water.color.copy(t.water); M.block.color.copy(t.surface); flows.forEach((f) => f.setColor(t.data)); });
  return st;
}
