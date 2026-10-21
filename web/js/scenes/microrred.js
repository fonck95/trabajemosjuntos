// Escena 3D: Red Energética Pública de Yondó. Casco urbano esquemático (no a escala) con cada
// edificio público, su generación solar, baterías, flujos de energía y la capa digital IoT/MinTIC.
import { THREE, Stage, tokens, onTheme, mat, box, solarArray, Flow, arc, fmtCOP, fmtN, reducedMotion, PANEL } from '../core.js';
import { loadModel, instancedFromModel, instantiate } from '../assets.js';
import { simulate, STEPS } from '../sim.js';
import { MICRORRED as M } from '../data.js';

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [40, 48, 62], target: [-3, 0, -1], maxDist: 130, env: false });
  const T = tokens();
  const S = st.scene;
  const mats = {
    ground: mat(T.ground), road: mat(T.line), water: mat(T.water, { roughness: 0.25, metalness: 0.1, transparent: true, opacity: 0.92 }),
    wall: mat(T.wall), roof: mat(T.roof), pv: mat(0x1d3557, { roughness: 0.35, metalness: 0.35 }), frame: mat(0x9aa5ad),
    bess: mat(T.s[3]), gen: mat(T.s[1]), dark: mat(T.ink), glass: mat(0x8fb3c9, { roughness: 0.2, metalness: 0.3, emissive: 0x000000 }),
    tree: mat(0x3f7d4e), trunk: mat(0x6b4f3a), lamp: new THREE.MeshBasicMaterial({ color: 0x333333 }),
  };

  // Terreno, río Magdalena al oriente y retícula vial
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(90, 70), mats.ground);
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; S.add(ground);
  const river = new THREE.Mesh(new THREE.PlaneGeometry(22, 70), mats.water);
  river.rotation.x = -Math.PI / 2; river.position.set(36, 0.03, 0); S.add(river);
  st.label('Río Magdalena', 'lbl-geo', [38, 0.5, 24]);
  st.label('hacia Barrancabermeja ⟶', 'lbl-geo', [38, 0.5, -6]);
  [-24, -12, 0, 12].forEach((z) => { const r = box(70, 0.04, 1.6, mats.road, -8, 0.01, z + 6); r.castShadow = false; S.add(r); });
  [-24, -12, 3, 16].forEach((x) => { const r = box(1.6, 0.04, 56, mats.road, x, 0.012, 0); r.castShadow = false; S.add(r); });
  // Parque principal e iglesia como referencia urbana
  const park = box(8, 0.08, 6, mats.tree, 3, 0, -1.5); park.material = mat(0x6f9e6a); S.add(park);
  const church = new THREE.Group(); church.add(box(4, 5, 7, mats.wall)); church.add(box(1.8, 9, 1.8, mats.wall, 0, 0, -3.2));
  church.position.set(9.5, 0, -1); S.add(church);
  // árboles: dos mallas instanciadas (troncos y copas) en vez de 52 objetos
  const crowns = new THREE.InstancedMesh(new THREE.SphereGeometry(0.9, 8, 6), mats.tree, 26);
  const trunks = new THREE.InstancedMesh(new THREE.BoxGeometry(0.25, 1.2, 0.25), mats.trunk, 26);
  for (let i = 0; i < 26; i++) {
    const a = i * 2.4, x = -34 + (i % 13) * 5.2 + Math.sin(a) * 1.2, z = i < 13 ? 25 : -27 + Math.cos(a);
    crowns.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 1.8, z));
    trunks.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 0.6, z));
  }
  crowns.castShadow = trunks.castShadow = true;
  S.add(crowns, trunks);

  // Edificios públicos
  const nodeObj = {};
  const hub = new THREE.Vector3(3, 0.4, -4.5);
  const fab = {
    palacio(n) { const g = new THREE.Group(); g.add(box(n.dim[0], n.dim[1], n.dim[2], mats.wall)); g.add(box(n.dim[0] * 0.3, 1.4, 1, mats.roof, 0, n.dim[1], n.dim[2] / 2 - 0.5)); return g; },
    hospital(n) {
      const g = new THREE.Group();
      g.add(box(n.dim[0], n.dim[1], n.dim[2], mats.wall));
      g.add(box(5, 3, 6, mats.wall, n.dim[0] / 2 + 2.5, 0, 1));
      const h = st.label('H', 'lbl-h', [0, n.dim[1] + 0.6, n.dim[2] / 2 - 1], g);
      // marquesina solar en parqueadero (carport) al sur
      const cp = solarArray(12, 2, mats.pv, mats.frame); cp.position.set(-1, 2.6, n.dim[2] / 2 + 4); g.add(cp);
      [-6, 0, 6].forEach((x) => g.add(box(0.25, 2.6, 0.25, mats.frame, x - 1, 0, n.dim[2] / 2 + 4)));
      return g;
    },
    policia(n) { const g = new THREE.Group(); g.add(box(...n.dim, mats.wall)); g.add(box(0.15, 5, 0.15, mats.dark, n.dim[0] / 2 - 0.6, n.dim[1], 0)); return g; },
    bomberos(n) { const g = new THREE.Group(); g.add(box(...n.dim, mats.wall)); g.add(box(n.dim[0] * 0.8, 3, 0.2, mat(T.bad), 0, 0, n.dim[2] / 2 + 0.05)); return g; },
    ptap(n) {
      const g = new THREE.Group(); g.add(box(...n.dim, mats.wall));
      [[-6.5, -1.5], [-6.5, 3.5]].forEach(([x, z]) => { const t = new THREE.Mesh(new THREE.CylinderGeometry(2, 2, 3.4, 24), mats.wall); t.position.set(x, 1.7, z); t.castShadow = true; g.add(t); });
      const pv = solarArray(10, 3, mats.pv, mats.frame); pv.position.set(0, 0, 8.5); g.add(pv);
      return g;
    },
    colegio(n) {
      const g = new THREE.Group();
      g.add(box(n.dim[0], n.dim[1], 2.6, mats.wall, 0, 0, -n.dim[2] / 2 + 1.3));
      g.add(box(2.6, n.dim[1], n.dim[2], mats.wall, -n.dim[0] / 2 + 1.3, 0, 0));
      g.add(box(n.dim[0] * 0.6, 0.06, n.dim[2] * 0.55, mat(0xb88d5e), 1.5, 0, 1.2));
      return g;
    },
    cultura(n) { const g = new THREE.Group(); g.add(box(...n.dim, mats.wall)); return g; },
    cuidado(n) { const g = new THREE.Group(); g.add(box(...n.dim, mats.wall)); g.add(box(n.dim[0] * 0.5, 0.06, 3, mat(0x6f9e6a), 0, 0, n.dim[2] / 2 + 1.6)); return g; },
    coliseo(n) {
      const g = new THREE.Group(); g.add(box(n.dim[0], n.dim[1] * 0.6, n.dim[2], mats.wall));
      // bóveda: cilindro achatado con eje en X; la mitad inferior queda oculta dentro de los muros
      const roof = new THREE.Mesh(new THREE.CylinderGeometry(n.dim[2] / 2, n.dim[2] / 2, n.dim[0], 28), mats.roof);
      roof.rotation.z = Math.PI / 2; roof.scale.x = 0.35; roof.position.y = n.dim[1] * 0.6; roof.castShadow = true;
      g.add(roof);
      return g;
    },
  };

  const roofPV = (n, g) => {
    if (!n.pv_kwp || ['hospital', 'ptap'].includes(n.forma)) return;
    const panels = Math.round(n.pv_kwp / 0.55); // módulos de 550 Wp
    const cols = Math.max(2, Math.min(Math.floor(n.dim[0] / 1.05) - 1, Math.ceil(Math.sqrt(panels * 1.6))));
    const rows = Math.max(1, Math.min(Math.floor(n.dim[2] / (PANEL.l + 0.15)) - 1, Math.ceil(panels / cols)));
    const a = solarArray(cols, rows, mats.pv, null);
    a.position.set(0, (n.forma === 'coliseo' ? n.dim[1] * 0.6 + (n.dim[2] / 2) * 0.35 : n.dim[1]) + 0.05, 0);
    g.add(a);
  };

  const panel = root.querySelector('.node-info');
  const showNode = (n) => {
    const bess = M.bess.filter((b) => b.nodo === n.id);
    panel.innerHTML = `<h4>${n.nombre}</h4>
      <dl class="kv">
        <dt>Consumo supuesto</dt><dd>${fmtN(n.kwh_mes)} kWh/mes</dd>
        <dt>Solar propuesta</dt><dd>${n.pv_kwp ? fmtN(n.pv_kwp) + ' kWp' : '—'}</dd>
        <dt>Baterías</dt><dd>${bess.length ? bess.map((b) => `${fmtN(b.kwh)} kWh / ${fmtN(b.kw)} kW`).join(', ') : '—'}</dd>
        <dt>Prioridad en falla</dt><dd><span class="pill p${n.prioridad}">P${n.prioridad}</span> ${n.isla ? 'en microrred aislable' : 'se desconecta en falla'}</dd>
      </dl>${n.nota ? `<p class="note">${n.nota}</p>` : ''}`;
  };

  M.nodos.forEach((n) => {
    let g;
    if (n.forma === 'virtual' || n.forma === 'alumbrado') { g = new THREE.Group(); }
    else {
      g = fab[n.forma](n);
      roofPV(n, g);
      g.traverse((o) => { if (o.isMesh) o.userData.baseMat = o.material; });
    }
    g.position.set(n.pos[0], 0, n.pos[1]);
    S.add(g);
    if (n.forma !== 'virtual' && n.forma !== 'alumbrado') {
      const lab = st.label(`<b>${n.corto}</b><span class="lv"></span>`, 'lbl-node', [0, n.dim[1] + 2.2, 0], g);
      st.pickable(g, { onPick: () => showNode(n) });
      const top = new THREE.Vector3(n.pos[0], 0.4, n.pos[1]);
      const flow = new Flow(S, arc([top.x, 0.4, top.z], [hub.x, hub.y, hub.z], 2 + top.distanceTo(hub) * 0.08), T.sun, { max: 22 });
      // capa digital: paquetes de datos hacia el CCED
      const data = new Flow(S, arc([top.x, n.dim[1] + 0.5, top.z], [0, 11, -9], 3 + top.distanceTo(hub) * 0.12), T.data, { max: 6, size: 0.12 });
      data.tube.material.opacity = 0.18;
      nodeObj[n.id] = { n, g, lab, flow, data };
    } else nodeObj[n.id] = { n, g };
  });

  // Baterías (contenedores) y planta de respaldo
  const bessObjs = M.bess.map((b) => {
    const n = M.nodos.find((x) => x.id === b.nodo);
    const len = 1.6 + b.kwh / 120;
    const hgt = b.kwh >= 100 ? 2.4 : 1.4;
    const c = new THREE.Group();
    c.add(box(len, hgt, hgt, mats.bess));
    const fw = len - 0.3;
    const fill = box(fw, 0.14, 0.4, mat(T.good, { emissive: T.good, emissiveIntensity: 0.5 }), 0, hgt + 0.02, 0); c.add(fill);
    // contenedores grandes en patio; gabinetes pequeños junto a la fachada lateral de cada sede
    const off = { hospital: [-9, 9.5], alcaldia: [-8, 1], ptap: [-1, -6.5] }[b.nodo] || [n.dim[0] / 2 + 1.4, 0];
    c.position.set(n.pos[0] + off[0], 0, n.pos[1] + off[1]);
    S.add(c);
    if (b.kwh >= 100) st.label(`BESS ${fmtN(b.kwh)} kWh`, 'lbl-small', [0, hgt + 0.8, 0], c);
    st.pickable(c, { onPick: () => { panel.innerHTML = `<h4>Baterías LFP · ${n.nombre}</h4><dl class="kv"><dt>Energía</dt><dd>${fmtN(b.kwh)} kWh</dd><dt>Potencia</dt><dd>${fmtN(b.kw)} kW</dd><dt>Función</dt><dd>Autoconsumo de día, respaldo en falla, recorte de pico nocturno</dd></dl>`; } });
    return { b, c, fill, len, hgt, fw };
  });
  const hosp = M.nodos.find((x) => x.id === 'hospital');
  const genOn = mat(T.bad, { emissive: T.bad, emissiveIntensity: 0.5 });
  const gen = new THREE.Group(); gen.add(box(3.2, 2, 1.8, mats.gen)); gen.add(box(0.3, 1.2, 0.3, mats.dark, 1.2, 2, 0));
  gen.position.set(hosp.pos[0] - 9, 0, hosp.pos[1] - 4); S.add(gen);
  st.label(`Planta ${M.genset.kw} kW`, 'lbl-small', [0, 3, 0], gen);

  // Punto de conexión al operador de red + CCED
  const sub = new THREE.Group();
  sub.add(box(4, 0.3, 4, mats.road));
  [-1, 1].forEach((x) => sub.add(box(1.2, 2.2, 1.2, mats.roof, x, 0.3, 0)));
  for (let i = 0; i < 3; i++) sub.add(box(0.12, 6, 0.12, mats.dark, -1.5 + i * 1.5, 0.3, -1.6));
  sub.position.set(M.conexion.pos[0], 0, M.conexion.pos[1]); S.add(sub);
  st.label('S/E Yondó · EPM', 'lbl-node', [0, 7.5, 0], sub);
  const gridFlow = new Flow(S, arc([sub.position.x, 0.6, sub.position.z], [hub.x, hub.y, hub.z], 6), T.s[0], { max: 30, size: 0.2 });
  const hubMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.8, 20), mats.dark); hubMesh.position.copy(hub); S.add(hubMesh);
  st.label('Barra de la comunidad energética', 'lbl-small', [hub.x, 2.2, hub.z]);
  const cced = new THREE.Mesh(new THREE.SphereGeometry(0.6, 16, 12), new THREE.MeshBasicMaterial({ color: T.data })); cced.position.set(0, 11, -9); S.add(cced);
  st.label('CCED · EMS + IoT (MinTIC)', 'lbl-data', [0, 12.6, -9]);
  const brk = st.label('✕ red caída', 'lbl-alert', [(sub.position.x + hub.x) / 2, 7, (sub.position.z + hub.z) / 2]);

  // Alumbrado público: postes a lo largo de las vías
  const headMat = new THREE.MeshBasicMaterial({ color: 0x333333 });
  const lampPos = [];
  for (let x = -30; x <= 22; x += 6.5) for (const z of [-17.2, -5.2, 6.8]) lampPos.push([x, z]);
  const poles = new THREE.InstancedMesh(new THREE.BoxGeometry(0.08, 2.6, 0.08), mats.frame, lampPos.length);
  const heads = new THREE.InstancedMesh(new THREE.SphereGeometry(0.22, 8, 6), headMat, lampPos.length);
  lampPos.forEach(([x, z], i) => { poles.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 1.3, z)); heads.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 2.7, z)); });
  S.add(poles, heads);

  // ===== Simulación y controles
  const q = (s) => root.querySelector(s);
  const ctl = { hour: q('#mr-hour'), play: q('#mr-play'), nub: q('#mr-nub'), isla: q('#mr-isla'), dr: q('#mr-dr'), dom: q('#mr-dom'), energy: q('#mr-l-energy'), digital: q('#mr-l-data') };
  let sim, hour = 12, playing = !reducedMotion;
  const out = (k, v) => { const e = root.querySelector(`[data-o="${k}"]`); if (e) e.textContent = v; };
  const rerun = () => {
    sim = simulate(M, { nubosidad: +ctl.nub.value / 100, isla: ctl.isla.checked, dr: ctl.dr.checked, domotica: ctl.dom.checked });
    const r = sim.resumen;
    out('auto', `${fmtN(r.autosuficiencia * 100, 0)} %`);
    out('auto-l', ctl.isla.checked ? 'Demanda atendida en isla' : 'Autosuficiencia del día');
    out('crit', `${fmtN(r.criticas_atendidas * 100, 0)} %`);
    out('ahorro', ctl.isla.checked ? '—' : fmtCOP(r.ahorro_cop_dia * 365));
    out('co2', ctl.isla.checked ? '—' : `${fmtN((r.co2_evitado_kg_dia * 365) / 1000, 0)} t`);
    out('diesel', `${fmtN(r.diesel_litros, 0)} L`);
    drawChart();
  };

  // mini-gráfico de 24 h (SVG) con FV, demanda y estado de la batería
  const svg = q('.mr-chart');
  function drawChart() {
    const W = 320, H = 120, pad = 22;
    const s = sim.steps;
    const maxP = Math.max(...s.map((x) => Math.max(x.pv, x.demand))) * 1.1;
    const X = (i) => pad + (i / (STEPS - 1)) * (W - pad - 6), Y = (v) => H - 16 - (v / maxP) * (H - 30);
    const line = (f) => s.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(f(x)).toFixed(1)}`).join('');
    const area = `${line((x) => x.pv)}L${X(STEPS - 1)},${Y(0)}L${X(0)},${Y(0)}Z`;
    const socLine = s.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${(H - 16 - x.soc * (H - 30)).toFixed(1)}`).join('');
    const ticks = [0, 6, 12, 18, 24].map((h) => `<text x="${X(Math.min(STEPS - 1, h * 4))}" y="${H - 3}" text-anchor="middle">${h}h</text>`).join('');
    const yt = [0, maxP / 2].map((v) => `<line x1="${pad}" x2="${W - 6}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${pad - 3}" y="${Y(v) + 3}" text-anchor="end">${fmtN(v, 0)}</text>`).join('');
    svg.innerHTML = `${yt}<path d="${area}" class="pv"/><path d="${line((x) => x.served)}" class="dem"/><path d="${socLine}" class="soc"/>${ticks}<line class="now" x1="0" x2="0" y1="8" y2="${H - 16}"/>`;
    svg.dataset.x0 = pad; svg.dataset.w = W - pad - 6;
  }

  function applyHour() {
    const i = Math.min(STEPS - 1, Math.floor(hour * 4));
    const s = sim.steps[i];
    const isla = ctl.isla.checked;
    const hh = Math.floor(hour), mm = Math.floor((hour % 1) * 60);
    out('hora', `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`);
    out('pv', `${fmtN(s.pv, 0)} kW`); out('dem', `${fmtN(s.served, 0)} kW`);
    out('bat', `${s.batt >= 0 ? 'entrega' : 'carga'} ${fmtN(Math.abs(s.batt), 0)} kW`);
    out('soc', `${fmtN(s.soc * 100, 0)} %`);
    out('red', isla ? 'sin red' : s.grid >= 0 ? `compra ${fmtN(s.grid, 0)} kW` : `vende ${fmtN(-s.grid, 0)} kW`);
    out('gen', `${fmtN(s.gen, 0)} kW`);
    const nl = svg.querySelector('.now'); if (nl) { const x = +svg.dataset.x0 + (i / (STEPS - 1)) * +svg.dataset.w; nl.setAttribute('x1', x); nl.setAttribute('x2', x); }
    // luz del sol y noche
    const sun = Math.max(0, Math.sin((Math.PI * (hour - 6)) / 12));
    st.sunLight.intensity = 0.15 + 1.6 * sun;
    st.hemi.intensity = 0.35 + 0.8 * sun;
    const ang = ((hour - 6) / 12) * Math.PI;
    st.sunLight.position.set(Math.cos(ang) * 50, 8 + Math.sin(Math.max(0, ang)) * 50, 18);
    const night = sun < 0.08;
    const lampOn = night && !isla;
    headMat.color.set(lampOn ? 0xffd27a : 0x333333);
    // flujos por edificio
    const maxKW = 260;
    s.per.forEach((p) => {
      const o = nodeObj[p.id]; if (!o || !o.flow) return;
      const net = p.served - p.pv;
      o.flow.set(Math.abs(net) / maxKW * 2.2, net < 0 ? 1 : -1);
      o.flow.setColor(net < 0 ? T.sun : T.s[0]);
      o.flow.visible(ctl.energy.checked && (p.on || !isla));
      o.data.set(ctl.digital.checked ? 0.6 : 0, 1); o.data.visible(ctl.digital.checked);
      const off = isla && (!p.on || p.served < 1e-3);
      o.g.traverse((m) => { if (m.isMesh && m.userData.baseMat) m.material = off ? dim : m.userData.baseMat; });
      o.lab.element.classList.toggle('off', off);
      o.lab.element.querySelector('.lv').textContent = off ? ' sin servicio' : ` ${net < 0 ? '+' : ''}${fmtN(-net, 0)} kW`;
    });
    gridFlow.set(isla ? 0 : Math.abs(s.grid) / 600 * 1.4, s.grid >= 0 ? 1 : -1);
    gridFlow.visible(!isla && ctl.energy.checked);
    brk.visible = isla; brk.element.hidden = !isla;
    bessObjs.forEach((o) => { const k = Math.max(0.02, s.soc); o.fill.scale.x = o.fw * k; o.fill.position.x = -o.fw * (1 - k) / 2; o.fill.material.color.set(s.soc < 0.25 ? T.bad : s.soc < 0.5 ? T.warn : T.good); o.fill.material.emissive.set(o.fill.material.color); });
    gen.children[0].material = s.gen > 0 ? genOn : mats.gen;
    st.updateShadows();
  }
  const dim = mat(0x555a60, { transparent: true, opacity: 0.45 });

  ctl.hour.addEventListener('input', () => { hour = +ctl.hour.value / 4; applyHour(); });
  ctl.play.addEventListener('click', () => { playing = !playing; ctl.play.textContent = playing ? 'Pausar' : 'Reproducir día'; ctl.play.setAttribute('aria-pressed', playing); });
  ctl.play.textContent = playing ? 'Pausar' : 'Reproducir día';
  [ctl.nub, ctl.isla, ctl.dr, ctl.dom].forEach((c) => c.addEventListener('input', () => { rerun(); applyHour(); }));
  [ctl.energy, ctl.digital].forEach((c) => c.addEventListener('input', applyHour));
  q('#mr-labels').addEventListener('input', (e) => { st.labels.domElement.hidden = !e.target.checked; });

  rerun(); applyHour();
  showNode(M.nodos.find((n) => n.id === 'hospital'));

  // Presupuesto, fases y mezcla de financiación
  const B = M.presupuesto;
  const directo = B.items.reduce((a, i) => a + i.cantidad * i.unitario, 0);
  const ind = B.indirectos.map((i) => ({ ...i, valor: directo * i.pct }));
  const total = directo + ind.reduce((a, i) => a + i.valor, 0);
  const anual = simulate(M, { nubosidad: 0.3 }).resumen.ahorro_cop_dia * 365;
  root.querySelector('[data-slot="microrred.budget"]').innerHTML = `<table>
    <thead><tr><th>Grupo</th><th>Componente</th><th class="n">Cantidad</th><th class="n">Unitario</th><th class="n">Subtotal</th></tr></thead>
    <tbody>${B.items.map((i) => `<tr><td>${i.grupo}</td><td>${i.componente}<br><span class="note">${i.fuente}</span></td><td class="n">${fmtN(i.cantidad)} ${i.unidad}</td><td class="n">${fmtCOP(i.unitario)}</td><td class="n">${fmtCOP(i.cantidad * i.unitario)}</td></tr>`).join('')}
    <tr><td colspan="4"><b>Costo directo</b></td><td class="n"><b>${fmtCOP(directo)}</b></td></tr>
    ${ind.map((i) => `<tr><td>Indirecto</td><td>${i.componente}</td><td class="n">${fmtN(i.pct * 100, 0)} %</td><td></td><td class="n">${fmtCOP(i.valor)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="4">Inversión total</td><td class="n">${fmtCOP(total)}</td></tr>
    <tr><td colspan="4">Ahorro anual estimado en facturas (día típico × 365)</td><td class="n">${fmtCOP(anual)}</td></tr>
    <tr><td colspan="4">Retorno simple</td><td class="n">${fmtN(total / anual, 1)} años</td></tr></tfoot></table>
    <div class="cols two" style="margin-top:14px">
      <div><h4>Fases</h4><table><tbody>${B.fases.map((f) => `<tr><td><b>${f.fase}</b><br><span class="note">${f.alcance}</span></td><td class="n">${fmtCOP(total * f.pct)}</td></tr>`).join('')}</tbody></table></div>
      <div><h4>Mezcla de financiación propuesta</h4><table><tbody>${B.financiacion.map((f) => `<tr><td>${f.fuente}</td><td class="n">${fmtN(f.pct * 100, 0)} %</td><td class="n">${fmtCOP(total * f.pct)}</td></tr>`).join('')}</tbody></table></div>
    </div>`;
  root.querySelector('[data-slot="microrred.cols"]').innerHTML = B.cols.map((c) => `<div class="card"><p class="eyebrow">${c.tag}</p><h3>${c.titulo}</h3>${c.html}</div>`).join('');

  let acc = 0;
  st.onFrame((dt) => {
    if (playing) {
      hour = (hour + dt * 0.8) % 24; acc += dt;
      if (acc > 0.1) { acc = 0; ctl.hour.value = Math.floor(hour * 4); applyHour(); }
    }
    let moving = playing;
    Object.values(nodeObj).forEach((o) => { if (o.flow?.update(dt)) moving = true; if (o.data?.update(dt)) moving = true; });
    if (gridFlow.update(dt)) moving = true;
    cced.scale.setScalar(1 + 0.15 * Math.sin(performance.now() / 300));
    return moving || ctl.digital.checked;
  });

  // ---- Modelos GLB: módulos solares reales instanciados, contenedores de baterías y hospital (LOD bajo)
  (async () => {
    try {
      const [pv, bessM, hospM] = await Promise.all(['models/modulo_fv.glb', 'models/contenedor_bess.glb', 'models/hospital_lod1.glb'].map((u) => loadModel(u)));
      // hospital: modelo de bajo detalle a escala del esquema
      const ho = nodeObj.hospital;
      ho.g.children.forEach((c) => { if (c.isMesh || c.isGroup) c.visible = false; });
      const hm = instantiate(hospM.gltf); hm.scale.setScalar(0.42); hm.position.set(0.6, 0, -0.8);
      hm.traverse((m) => { if (m.isMesh) m.userData.baseMat = m.material; });
      ho.g.add(hm);
      // baterías: contenedor de 20 pies escalado a cada capacidad
      bessObjs.forEach((o) => {
        o.c.children[0].visible = false;
        const cm = instantiate(bessM.gltf); cm.scale.set(o.len / 6.06, o.hgt / 2.59, o.hgt / 2.44); o.c.add(cm);
      });
      // solar: cada InstancedMesh provisional se reemplaza por el módulo GLB con las mismas matrices
      S.updateMatrixWorld(true);
      const placeholders = [];
      S.traverse((m) => { if (m.isInstancedMesh && m.userData.solar && m.visible) { let v = true; m.traverseAncestors((a) => { if (!a.visible) v = false; }); if (v) placeholders.push(m); } });
      const mats4 = [], tmp = new THREE.Matrix4();
      placeholders.forEach((m) => { for (let i = 0; i < m.count; i++) { m.getMatrixAt(i, tmp); mats4.push(m.matrixWorld.clone().multiply(tmp)); } m.visible = false; });
      S.add(instancedFromModel(pv.gltf, mats4, PANEL.scale));
      st.updateShadows();
    } catch (e) { console.warn('Modelos GLB no disponibles; se mantiene la geometría simple', e); }
  })();
  st.freeze(ground); st.freeze(river); st.freeze(crowns); st.freeze(trunks); st.freeze(poles); st.freeze(heads); st.freeze(church);

  onTheme((t) => {
    Object.assign(T, t);
    mats.ground.color.copy(t.ground); mats.road.color.copy(t.line); mats.water.color.copy(t.water); mats.wall.color.copy(t.wall); mats.roof.color.copy(t.roof); mats.dark.color.copy(t.ink);
    cced.material.color.copy(t.data); gridFlow.setColor(t.s[0]);
    Object.values(nodeObj).forEach((o) => o.data?.setColor(t.data));
    applyHour();
  });
  return st;
}
