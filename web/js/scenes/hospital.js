// Escena 3D: la E.S.E. Hospital Héctor Abad Gómez como nodo energético y financiero de 2028.
// Las fuentes de recursos son pilares cuya altura es el monto; sus corrientes entran al hospital.
import { THREE, Stage, tokens, onTheme, mat, box, solarArray, Flow, arc, fmtCOP, fmtN } from '../core.js';
import { HOSPITAL as Hs, MICRORRED } from '../data.js';

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [8, 44, 58], target: [0, 4, -12], maxDist: 130 });
  const T = tokens();
  const S = st.scene;
  const M = {
    ground: mat(T.ground), wall: mat(T.wall), roof: mat(T.roof), pv: mat(0x1d3557, { roughness: 0.35, metalness: 0.35 }), frame: mat(0x9aa5ad),
    bess: mat(T.s[3]), gen: mat(T.s[1]), dark: mat(T.ink), glass: mat(0x7fa6bd, { roughness: 0.2, metalness: 0.3 }), green: mat(0x6f9e6a), road: mat(T.line),
  };
  const ground = new THREE.Mesh(new THREE.CircleGeometry(48, 64), M.ground); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; S.add(ground);

  // Edificio: bloque de hospitalización (2 pisos), urgencias, consulta externa y servicios
  const H = new THREE.Group(); S.add(H);
  H.add(box(18, 6, 10, M.wall, 0, 0, 0));
  H.add(box(18.2, 0.5, 10.2, M.roof, 0, 6, 0));
  for (let i = 0; i < 8; i++) { H.add(box(1.4, 1.2, 0.1, M.glass, -7.7 + i * 2.2, 1.2, 5.02)); H.add(box(1.4, 1.2, 0.1, M.glass, -7.7 + i * 2.2, 4, 5.02)); }
  H.add(box(8, 3.6, 7, M.wall, 13, 0, 1.5));
  H.add(box(6, 0.3, 3, M.roof, 13, 3.6, 6.5));
  st.label('Urgencias', 'lbl-small', [13, 5, 6.5], H);
  H.add(box(9, 3.6, 7, M.wall, -13.5, 0, -1));
  st.label('Consulta externa · telesalud', 'lbl-small', [-13.5, 5, -1], H);
  H.add(box(6, 3, 5, M.wall, 4, 0, -9));
  st.label('Servicios: cadena de frío, lavandería, esterilización', 'lbl-small', [4, 4.2, -9], H);
  st.label('<b>E.S.E. Hospital Héctor Abad Gómez</b>', 'lbl-node', [0, 9.4, 0], H);
  st.label('H', 'lbl-h', [0, 7.4, 4], H);
  // Energía: cubierta solar, marquesina, baterías, planta, antena de conectividad
  const roofPV = solarArray(15, 4, M.pv, null); roofPV.position.set(0, 6.3, 0); H.add(roofPV);
  const cp = solarArray(16, 2, M.pv, M.frame); cp.position.set(0, 2.8, 13); H.add(cp);
  [-7, 0, 7].forEach((x) => H.add(box(0.25, 2.8, 0.25, M.frame, x, 0, 13)));
  st.label('Marquesina solar del parqueadero', 'lbl-small', [0, 4.4, 13], H);
  const bess = new THREE.Group(); bess.add(box(8, 2.6, 2.6, M.bess)); bess.position.set(-12, 0, 9); H.add(bess);
  const socBar = box(7.4, 0.35, 2.65, mat(T.good, { emissive: T.good, emissiveIntensity: 0.4 }), 0, 1.1, 0); bess.add(socBar);
  st.label(`BESS ${fmtN(MICRORRED.bess.find((b) => b.nodo === 'hospital').kwh)} kWh`, 'lbl-small', [0, 3.3, 0], bess);
  const gen = new THREE.Group(); gen.add(box(3.4, 2.1, 1.9, M.gen)); gen.add(box(0.3, 1.3, 0.3, M.dark, 1.2, 2.1, 0)); gen.position.set(-12, 0, -8); H.add(gen);
  st.label('Planta de respaldo', 'lbl-small', [0, 3, 0], gen);
  const mast = new THREE.Group(); mast.add(box(0.2, 10, 0.2, M.dark)); const dish = new THREE.Mesh(new THREE.SphereGeometry(0.9, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2.4), M.frame);
  dish.rotation.x = -Math.PI / 2.4; dish.position.y = 9; mast.add(dish); mast.position.set(8.5, 6.5, -3.5); H.add(mast);
  st.label('Nodo de conectividad MinTIC', 'lbl-data', [0, 11, 0], mast);
  [[-22, 2], [22, -6], [-4, 20], [16, 16], [-20, -14]].forEach(([x, z]) => {
    const t = new THREE.Group(); t.add(box(0.3, 1.4, 0.3, mat(0x6b4f3a)));
    const c = new THREE.Mesh(new THREE.SphereGeometry(1.4, 10, 8), M.green); c.position.y = 2.4; c.castShadow = true; t.add(c); t.position.set(x, 0, z); S.add(t);
  });

  // Fuentes de financiación: pilares en arco al norte
  const F = Hs.fuentes;
  const pillMats = F.map((f) => mat(T.s[f.slot - 1], { roughness: 0.5 }));
  const geo = new THREE.CylinderGeometry(1.25, 1.25, 1, 28); geo.translate(0, 0.5, 0);
  const items = F.map((f, i) => {
    const a = Math.PI * (0.12 + (0.76 * i) / Math.max(1, F.length - 1));
    const x = Math.cos(a) * -30, z = -Math.sin(a) * 24 - 6;
    const p = new THREE.Mesh(geo, pillMats[i]); p.position.set(x, 0, z); p.castShadow = true; S.add(p);
    const lab = st.label('', 'lbl-money', [x, 0, z]);
    const flow = new Flow(S, arc([x, 1, z], [0, 6.5, -1], 8), T.s[f.slot - 1], { max: 30, size: 0.22 });
    st.pickable(p, { onPick: () => pick(f) });
    return { f, p, lab, flow, h: 0.1, target: 0.1 };
  });

  let esc = 'med';
  const tiles = root.querySelector('[data-slot="hospital.tiles"]');
  function layout() {
    const max = Math.max(...F.map((f) => f.max));
    items.forEach((it) => {
      const v = it.f[esc];
      it.target = 0.3 + (v / max) * 16;
      it.lab.element.innerHTML = `${fmtCOP(v * 1e6)}<small>${it.f.corto}</small>`;
      it.flow.set((v / max) * 1.1, 1);
      // la corriente nace en la cima del pilar
      it.flow.curve.v0.y = it.target; it.flow.curve.updateArcLengths();
      it.flow.tube.geometry.dispose(); it.flow.tube.geometry = new THREE.TubeGeometry(it.flow.curve, 48, 0.05, 6, false);
    });
    const tot = F.reduce((a, f) => a + f[esc], 0);
    const ctr = Hs.contrapartida_esc[esc];
    tiles.innerHTML = `<div class="tile"><b>${fmtCOP(tot * 1e6)}</b><span>Recursos gestionables 2027–2029</span></div>
      <div class="tile"><b>${fmtN(F.filter((f) => f[esc] > 0).length)}</b><span>Fuentes activas</span></div>
      <div class="tile"><b>${fmtCOP(ctr * 1e6)}</b><span>Contrapartida municipal y de la E.S.E.</span></div>
      <div class="tile"><b>${fmtN((100 * ctr) / tot, 0)} %</b><span>Apalancamiento propio</span></div>`;
  }
  const pickEl = root.querySelector('[data-slot="hospital.pick"]');
  function pick(f) {
    pickEl.innerHTML = `<h4>${f.nombre}</h4><dl class="kv"><dt>Conservador</dt><dd>${fmtCOP(f.min * 1e6)}</dd><dt>Probable</dt><dd>${fmtCOP(f.med * 1e6)}</dd><dt>Ambicioso</dt><dd>${fmtCOP(f.max * 1e6)}</dd></dl>
      <p style="margin-top:8px"><b>Para qué:</b> ${f.uso}</p><p><b>Requisito:</b> ${f.requisito}</p><p><b>Calendario:</b> ${f.calendario}</p><p class="note">${f.base}</p>`;
  }
  root.querySelectorAll('[data-esc]').forEach((b) => b.addEventListener('click', () => {
    esc = b.dataset.esc; root.querySelectorAll('[data-esc]').forEach((x) => x.setAttribute('aria-pressed', x === b)); layout();
  }));
  root.querySelector('[data-slot="hospital.table"]').innerHTML = `<table><thead><tr><th>Fuente</th><th>Para qué</th><th>Calendario</th><th class="n">Conservador</th><th class="n">Probable</th><th class="n">Ambicioso</th></tr></thead>
    <tbody>${F.map((f) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--s${f.slot})"></i> ${f.nombre}</td><td>${f.uso}</td><td>${f.calendario}</td><td class="n">${fmtCOP(f.min * 1e6)}</td><td class="n">${fmtCOP(f.med * 1e6)}</td><td class="n">${fmtCOP(f.max * 1e6)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="3">Total</td>${['min', 'med', 'max'].map((k) => `<td class="n">${fmtCOP(F.reduce((a, f) => a + f[k], 0) * 1e6)}</td>`).join('')}</tr></tfoot></table>`;
  root.querySelector('[data-slot="hospital.cols"]').innerHTML = Hs.bloques.map((b) => `<div class="card"><p class="eyebrow">${b.tag}</p><h3>${b.titulo}</h3>${b.html}</div>`).join('');
  const fi = Hs.ficha;
  root.querySelector('[data-slot="hospital.ficha"]').innerHTML = `<dl class="kv" style="grid-template-columns:auto minmax(0,1fr)">
    <dt>NIT</dt><dd>${fi.nit}</dd><dt>Nivel y sede</dt><dd style="text-align:left;font-family:inherit">${fi.nivel}</dd>
    <dt>Capacidad</dt><dd style="text-align:left;font-family:inherit">${fi.capacidad}</dd><dt>Riesgo fiscal</dt><dd style="text-align:left;font-family:inherit">${fi.riesgo}</dd>
    <dt>Aseguramiento</dt><dd style="text-align:left;font-family:inherit">${fi.aseguramiento}</dd><dt>Población 2028</dt><dd>${fmtN(fi.poblacion_2028)} habitantes (DANE)</dd></dl>`;
  const pc = Hs.proyecto.componentes;
  root.querySelector('[data-slot="hospital.proyecto"]').innerHTML = `<table><thead><tr><th>Componente</th><th class="n">Valor</th></tr></thead><tbody>${pc.map((c) => `<tr><td>${c.componente} <span class="tag ${c.certeza === 'V' ? 'ver' : 'sup'}">${c.certeza === 'V' ? 'verificado' : 'supuesto'}</span><br><span class="note">${c.fuente}</span></td><td class="n">${fmtCOP(c.valor * 1e6)}</td></tr>`).join('')}</tbody><tfoot><tr><td>Total</td><td class="n">${fmtCOP(pc.reduce((a, c) => a + c.valor, 0) * 1e6)}</td></tr></tfoot></table>`;
  layout();
  pick(F[0]);

  st.onFrame((dt, t) => {
    items.forEach((it) => {
      it.h += (it.target - it.h) * Math.min(1, dt * 4);
      it.p.scale.y = it.h; it.lab.position.set(it.p.position.x, it.h + 1.3, it.p.position.z);
      it.flow.update(dt);
    });
    socBar.scale.x = 0.55 + 0.4 * Math.sin(t * 0.3) ** 2;
  });
  onTheme((t) => {
    M.ground.color.copy(t.ground); M.wall.color.copy(t.wall); M.roof.color.copy(t.roof); M.dark.color.copy(t.ink); M.road.color.copy(t.line);
    items.forEach((it, i) => { pillMats[i].color.copy(t.s[it.f.slot - 1]); it.flow.setColor(t.s[it.f.slot - 1]); });
  });
  return st;
}
