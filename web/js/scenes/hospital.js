// Escena 3D: la E.S.E. Hospital Héctor Abad Gómez como nodo energético y financiero de 2028.
// Las fuentes de recursos son pilares cuya altura es el monto; sus corrientes entran al hospital.
import { THREE, Stage, tokens, onTheme, mat, box, solarArray, Flow, arc, fmtCOP, fmtN, gsap } from '../core.js';
import { progressiveLOD } from '../assets.js';
import { HOSPITAL as Hs, MICRORRED, EDIFICIOS } from '../data.js';

// quita las referencias a archivos internos del proyecto ("(docs/05)", "Ver docs/06.") que el ciudadano no puede abrir
const limpia = (s) => String(s ?? '').replace(/\s*\(?\bVer (?:docs\/\d+(?:,\s*|\s+y\s+)?)+\)?\.?/g, '').replace(/\s*\((?:docs\/\d+|[\w./-]+\.json)[^()]*\)/g, '');

export function mount(root) {
  const el = root.querySelector('.stage');
  // Réplica real del hospital (levantada con satélite y Street View) si existe; si no, el modelo esquemático
  const REAL = EDIFICIOS.find((e) => e.id === 'hospital' && e.archivo);
  const half = REAL ? Math.max(REAL.tamano[0], REAL.tamano[2]) / 2 : 23, HY = REAL ? REAL.tamano[1] : 8;
  const RAD = Math.max(30, half * 1.25 + 10), K = RAD / 30;
  // las etiquetas de plata y la del hospital se apartan solas para no encimarse
  const st = new Stage(el, { cam: [8 * K, 44 * K, 58 * K], target: [0, 4, -12 * K], maxDist: 130 * K, tone: 'aces', exposure: 1.05, dynamicShadows: true, declutter: ['lbl-money', 'lbl-node'] });
  { const c = st.sunLight.shadow.camera; Object.assign(c, { left: -RAD - 12, right: RAD + 12, top: RAD + 12, bottom: -RAD - 12, far: 260 * K }); st.sunLight.position.multiplyScalar(K); }
  const T = tokens();
  const S = st.scene;
  const M = {
    ground: mat(T.ground), wall: mat(T.wall), roof: mat(T.roof), pv: mat(0x1d3557, { roughness: 0.35, metalness: 0.35 }), frame: mat(0x9aa5ad),
    bess: mat(T.s[3]), gen: mat(T.s[1]), dark: mat(T.ink), glass: mat(0x7fa6bd, { roughness: 0.2, metalness: 0.3 }), green: mat(0x6f9e6a), road: mat(T.line),
  };
  const ground = new THREE.Mesh(new THREE.CircleGeometry(Math.max(48, RAD + 26), 64), M.ground); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; S.add(ground);

  // Marcador de posición liviano mientras llega el modelo GLB (se ve al instante y luego se reemplaza)
  const proc = new THREE.Group(); S.add(proc);
  proc.add(box(18, 6, 10, M.wall, 0, 0, 0), box(18.2, 0.5, 10.2, M.roof, 0, 6, 0));
  for (let i = 0; i < 8; i++) { proc.add(box(1.4, 1.2, 0.1, M.glass, -7.7 + i * 2.2, 1.2, 5.02)); proc.add(box(1.4, 1.2, 0.1, M.glass, -7.7 + i * 2.2, 4, 5.02)); }
  proc.add(box(8, 3.6, 7, M.wall, 13, 0, 1.5), box(9, 3.6, 7, M.wall, -13.5, 0, -1), box(6, 3, 5, M.wall, 4, 0, -9));
  const roofPV = solarArray(14, 4, M.pv, null); roofPV.position.set(0, 6.3, 0); proc.add(roofPV);
  const cp = solarArray(16, 2, M.pv, M.frame); cp.position.set(0, 2.8, 14.5); proc.add(cp);
  proc.add(box(7.6, 2.6, 2.4, M.bess, -12, 0, 9), box(3.4, 2.1, 1.9, M.gen, -12, 0, -8), box(0.2, 10, 0.2, M.dark, 8.5, 6.5, -3.5));

  // Modelo GLB comprimido con Draco, con dos niveles de detalle (se cambia por distancia de cámara)
  const status = st.label('Cargando modelo 3D…', 'lbl-small', [0, 1, 18]);
  const levels = REAL ? [{ url: REAL.archivo, distance: 0 }, { url: REAL.archivo_lod1, distance: 110 * K }] : [{ url: 'models/hospital_lod0.glb', distance: 0 }, { url: 'models/hospital_lod1.glb', distance: 85 }];
  const lod = progressiveLOD(levels, (o, lv) => {
    proc.visible = false;
    status.element.textContent = lv.distance === 0 ? '' : 'Nivel de detalle bajo · cargando el detallado…';
    st.updateShadows();
  });
  S.add(lod);
  st.onFrame(() => { lod.update(st.camera); return false; });

  // Etiquetas y piezas animadas sobre el modelo
  const tags = new THREE.Group(); S.add(tags);
  if (REAL) {
    // las etiquetas del modelo esquemático no corresponden a la réplica (CSS2D no hereda la visibilidad del grupo)
    queueMicrotask(() => tags.children.forEach((o) => { o.visible = false; }));
    st.label('<b>E.S.E. Hospital Héctor Abad Gómez</b><br><small>edificio actual · pasa a administración y bodega</small>', 'lbl-node lbl-hosp', [0, HY + 4, 0]);
    // baterías y marquesina solo si los datos del edificio las traen (el nodo solar del hospital pasó a la torre)
    (REAL.puntos || []).filter((q) => q.tipo !== 'bess' || REAL.bess?.kwh).forEach((q) => st.label(q.tipo === 'bess' ? `Baterías ${fmtN(REAL.bess.kwh)} kWh` : 'Marquesina solar', 'lbl-node lbl-hosp', [q.x, 4.5, -q.y]));
  }
  st.label('Urgencias', 'lbl-small', [13, 5, 6.5], tags);
  st.label('Consulta externa · telesalud', 'lbl-small', [-13.5, 5, -1], tags);
  st.label('Servicios: cadena de frío, lavandería, esterilización', 'lbl-small', [4, 4.2, -9], tags);
  st.label('<b>E.S.E. Hospital Héctor Abad Gómez</b>', 'lbl-node', [0, 9.6, 0], tags);
  st.label('Marquesina solar del parqueadero', 'lbl-small', [0, 4.6, 14.5], tags);
  const bessH = MICRORRED.bess.find((b) => b.nodo === 'hospital');
  if (bessH) st.label(`BESS ${fmtN(bessH.kwh)} kWh`, 'lbl-small', [-12, 3.6, 9], tags);
  st.label('Planta de respaldo', 'lbl-small', [-12, 3, -8], tags);
  st.label('Nodo de conectividad MinTIC', 'lbl-data', [8.5, 17.5, -3.5], tags);
  // barra de carga sobre el techo del contenedor de baterías
  const socW = 7;
  const socBar = box(socW, 0.12, 0.5, mat(T.good, { emissive: T.good, emissiveIntensity: 0.6 }), -12, 2.78, 9.9); if (!REAL) S.add(socBar);
  const trees = new THREE.InstancedMesh(new THREE.SphereGeometry(1.4, 10, 8), M.green, 5);
  const trunks = new THREE.InstancedMesh(new THREE.BoxGeometry(0.3, 1.4, 0.3), mat(0x6b4f3a), 5);
  [[-22, 2], [22, -6], [-4, 22], [18, 18], [-22, -14]].forEach(([x, z], i) => {
    trees.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 2.4, z)); trunks.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x, 0.7, z));
  });
  trees.castShadow = trunks.castShadow = true; if (!REAL) S.add(trees, trunks);
  st.freeze(ground); st.freeze(proc);

  // Fuentes de financiación: pilares en arco al norte, abierto casi a media vuelta para que las etiquetas se separen
  const F = Hs.fuentes;
  const pillMats = F.map((f) => mat(T.s[f.slot - 1], { roughness: 0.5 }));
  const geo = new THREE.CylinderGeometry(1.25, 1.25, 1, 28); geo.translate(0, 0.5, 0);
  // nombre corto de la fuente para el teléfono: "PMIDS + Gobernación" → "PMIDS", "MinSalud (PGN)" → "MinSalud"
  const mini = (s) => s.split(/\s[+(/]/)[0].replace(/ por Impuestos$/, ' por imp.');
  const items = F.map((f, i) => {
    const a = Math.PI * (0.03 + (0.94 * i) / Math.max(1, F.length - 1));
    const x = Math.cos(a) * -RAD, z = -Math.sin(a) * RAD * 0.85 - 6 * K;
    const p = new THREE.Mesh(geo, pillMats[i]); p.position.set(x, 0, z); p.castShadow = true; S.add(p);
    p.scale.y = 0.1;
    const lab = st.label('', 'lbl-money', [x, 1.4, z]);
    const flow = new Flow(S, arc([x, 1, z], [0, HY * 0.8, -1], 8 * K), T.s[f.slot - 1], { max: 30, size: 0.22 * Math.sqrt(K), tube: 0.05 * K });
    st.pickable(p, { onPick: () => pick(f) });
    return { f, p, lab, flow, target: 0.1 };
  });
  // en el teléfono (recuadro vertical) la cámara sube y encuadra el edificio con el arco de pilares a su altura máxima
  if (el.clientWidth < 560) {
    const bx = new THREE.Box3(new THREE.Vector3(-half, 0, -half), new THREE.Vector3(half, HY, half));
    items.forEach((it) => bx.expandByPoint(it.p.position.clone().setY(16 * Math.sqrt(K))));
    st.frameBox(bx, new THREE.Vector3(0.1, 1.6, 1), { margin: 0.68 });
  }

  let esc = 'med';
  const tiles = root.querySelector('[data-slot="hospital.tiles"]');
  function layout() {
    const max = Math.max(...F.map((f) => f.max));
    items.forEach((it) => {
      const v = it.f[esc];
      it.target = 0.3 + (v / max) * 16 * Math.sqrt(K);
      it.lab.element.innerHTML = `${fmtCOP(v * 1e6)}<small><span class="fl">${it.f.corto}</span><span class="fc">${mini(it.f.corto)}</span></small>`;
      // una fuente sin aporte en este escenario no se dibuja (un pilar de "$0" distrae)
      it.p.visible = it.lab.visible = v > 0; it.flow.visible(v > 0);
      it.flow.set((v / max) * 1.1, 1);
      // la corriente nace en la cima del pilar
      it.flow.curve.v0.y = it.target; it.flow.curve.updateArcLengths();
      it.flow.tube.geometry.dispose(); it.flow.tube.geometry = new THREE.TubeGeometry(it.flow.curve, 48, 0.05 * K, 6, false);
      const placeP = () => { it.lab.position.set(it.p.position.x, it.p.scale.y + 1.3, it.p.position.z); st.invalidate(); };
      if (gsap) gsap.to(it.p.scale, { y: it.target, duration: 1, ease: 'power3.out', delay: items.indexOf(it) * 0.06, overwrite: true, onUpdate: placeP });
      else { it.p.scale.y = it.target; placeP(); }
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
      <p style="margin-top:8px"><b>Para qué:</b> ${limpia(f.uso)}</p><p><b>Requisito:</b> ${limpia(f.requisito)}</p><p><b>Calendario:</b> ${limpia(f.calendario)}</p><p class="note">${limpia(f.base)}</p>`;
  }
  root.querySelectorAll('[data-esc]').forEach((b) => b.addEventListener('click', () => {
    esc = b.dataset.esc; root.querySelectorAll('[data-esc]').forEach((x) => x.setAttribute('aria-pressed', x === b)); layout();
  }));
  root.querySelector('[data-slot="hospital.table"]').innerHTML = `<table><thead><tr><th>Fuente</th><th>Para qué</th><th>Calendario</th><th class="n">Conservador</th><th class="n">Probable</th><th class="n">Ambicioso</th></tr></thead>
    <tbody>${F.map((f) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--s${f.slot})"></i> ${f.nombre}</td><td>${limpia(f.uso)}</td><td>${limpia(f.calendario)}</td><td class="n">${fmtCOP(f.min * 1e6)}</td><td class="n">${fmtCOP(f.med * 1e6)}</td><td class="n">${fmtCOP(f.max * 1e6)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="3">Total</td>${['min', 'med', 'max'].map((k) => `<td class="n">${fmtCOP(F.reduce((a, f) => a + f[k], 0) * 1e6)}</td>`).join('')}</tr></tfoot></table>`;
  root.querySelector('[data-slot="hospital.cols"]').innerHTML = Hs.bloques.map((b) => `<div class="card"><p class="eyebrow">${b.tag}</p><h3>${b.titulo}</h3>${limpia(b.html)}</div>`).join('');
  const fi = Hs.ficha;
  root.querySelector('[data-slot="hospital.ficha"]').innerHTML = `<dl class="kv" style="grid-template-columns:auto minmax(0,1fr)">
    <dt>NIT</dt><dd>${fi.nit}</dd><dt>Nivel y sede</dt><dd style="text-align:left;font-family:inherit">${fi.nivel}</dd>
    <dt>Capacidad</dt><dd style="text-align:left;font-family:inherit">${fi.capacidad}</dd><dt>Riesgo fiscal</dt><dd style="text-align:left;font-family:inherit">${fi.riesgo}</dd>
    <dt>Aseguramiento</dt><dd style="text-align:left;font-family:inherit">${fi.aseguramiento}</dd><dt>Población 2028</dt><dd>${fmtN(fi.poblacion_2028)} habitantes (DANE)</dd></dl>`;
  const pc = Hs.proyecto.componentes;
  // si la tabla todavía es la del refuerzo del edificio, se aclara que la torre la reemplazó
  const antes = pc.some((c) => /reforz/i.test(c.componente)) ? '<p class="note">Propuesta anterior a la torre: el reforzamiento se reemplaza por la <a href="#torre">torre de servicios de primer nivel</a> y por la adecuación del edificio actual para oficinas y bodega; la solar y las baterías ahora van en la torre.</p>' : '';
  root.querySelector('[data-slot="hospital.proyecto"]').innerHTML = `${antes}<table><thead><tr><th>Componente</th><th class="n">Valor</th></tr></thead><tbody>${pc.map((c) => `<tr><td>${limpia(c.componente)} <span class="tag ${c.certeza === 'V' ? 'ver' : 'sup'}">${c.certeza === 'V' ? 'verificado' : 'supuesto'}</span><br><span class="note">${limpia(c.fuente)}</span></td><td class="n">${fmtCOP(c.valor * 1e6)}</td></tr>`).join('')}</tbody><tfoot><tr><td>Total</td><td class="n">${fmtCOP(pc.reduce((a, c) => a + c.valor, 0) * 1e6)}</td></tr></tfoot></table>`;
  layout();
  pick(F[0]);

  st.onFrame((dt, t) => {
    let moving = false;
    items.forEach((it) => { if (it.flow.update(dt) !== false) moving = true; });
    const k = 0.55 + 0.4 * Math.sin(t * 0.3) ** 2;
    socBar.scale.x = socW * k; socBar.position.x = -12 - (socW * (1 - k)) / 2;
    return moving;
  });
  onTheme((t) => {
    M.ground.color.copy(t.ground); M.wall.color.copy(t.wall); M.roof.color.copy(t.roof); M.dark.color.copy(t.ink); M.road.color.copy(t.line);
    items.forEach((it, i) => { pillMats[i].color.copy(t.s[it.f.slot - 1]); it.flow.setColor(t.s[it.f.slot - 1]); });
  });
  return st;
}
