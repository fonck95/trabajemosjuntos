// Escena 3D: embudo de la inversión. Cada anillo es una etapa; los proyectos caen como monedas y se "fugan"
// donde el ciclo se rompe (estudios que no llegan a obra, obras que no llegan a operación).
// Anillos torneados con pernos, embudo de vidrio en una sola pieza, base con la huella de cada etapa y bandeja final.
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, fmtN, reducedMotion } from '../core.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { EMBUDO } from '../data.js';

// perfil redondeado (r, y) de un anillo torneado: ancho radial 2a, alto 2b, radio de canto c
function ringProfile(R, a, b, c) {
  const pts = [], arc = (cx, cy, f0) => { for (let i = 0; i <= 4; i++) { const f = f0 + (i / 4) * (Math.PI / 2); pts.push(new THREE.Vector2(cx + Math.cos(f) * c, cy + Math.sin(f) * c)); } };
  arc(R + a - c, -b + c, -Math.PI / 2); arc(R + a - c, b - c, 0); arc(R - a + c, b - c, Math.PI / 2); arc(R - a + c, -b + c, Math.PI);
  pts.push(pts[0].clone());
  return pts;
}
// moneda: canto oscuro y caras con un disco central en relieve (color por vértice, el tinte lo pone el material)
function coinGeo(r, h) {
  const tone = (g, sideK, capK) => { g = g.toNonIndexed(); const n = g.attributes.position.count, c = new Float32Array(n * 3); g.groups.forEach((gr) => { const k = gr.materialIndex === 0 ? sideK : capK; for (let i = gr.start; i < gr.start + gr.count; i++) c.set([k, k, k], i * 3); }); g.setAttribute('color', new THREE.BufferAttribute(c, 3)); g.deleteAttribute('uv'); return g; };
  return mergeGeometries([tone(new THREE.CylinderGeometry(r, r, h, 12), 0.62, 0.9), tone(new THREE.CylinderGeometry(r * 0.72, r * 0.72, h * 1.25, 10), 0.8, 1.08)]);
}

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [0, 14, 36], target: [0, 8, 0], maxDist: 80 });
  const T = tokens();
  const S = st.scene;
  const E = EMBUDO.etapas;
  const maxN = Math.max(...E.map((e) => e.n));
  const R = (n) => 1.2 + 9 * Math.sqrt(n / maxN);
  const gap = 4.2, top = (E.length - 1) * gap + 2;
  const ringMats = [];
  const bolts = [];
  const rings = E.map((e, i) => {
    const y = top - i * gap, r = R(e.n);
    const m = mat(T.s[e.slot - 1], { roughness: 0.32, metalness: 0.35 });
    ringMats.push(m);
    const ring = new THREE.Mesh(new THREE.LatheGeometry(ringProfile(r, 0.36, 0.17, 0.07), 72), m);
    ring.position.y = y; ring.castShadow = true; ring.receiveShadow = true;
    S.add(ring);
    // pernos sobre la cara superior del anillo
    const nb = Math.round(10 + r * 2.4);
    for (let k = 0; k < nb; k++) { const a = (k / nb) * Math.PI * 2; bolts.push(new THREE.CylinderGeometry(0.045, 0.05, 0.06, 6).translate(Math.cos(a) * r, y + 0.19, Math.sin(a) * r)); }
    const lab = st.label(`<b>${e.etapa}</b><br>${fmtN(e.n)} ${e.unidad}${e.valor ? ` · ${fmtCOP(e.valor)}` : ''}`, 'lbl-node', [r + 1.5, y, 0]);
    st.pickable(ring, { onPick: () => info(e) });
    return { ring, y, r, e, lab };
  });
  // en pantallas angostas la etiqueta del anillo mayor no cabe a su derecha: va centrada encima del anillo
  new ResizeObserver(() => { const c = el.clientWidth < 560, { lab, r, y } = rings[0]; lab.position.set(c ? 0 : r + 1.5, c ? y + 3.2 : y, 0); st.invalidate(); }).observe(el);
  const boltMat = mat(0x6c747b, { roughness: 0.35, metalness: 0.7 });
  const boltM = new THREE.Mesh(mergeGeometries(bolts), boltMat); S.add(boltM);
  // embudo de vidrio en una sola pieza: primero la cara interior y luego la exterior (sin parpadeo por orden)
  const prof = rings.map((r) => new THREE.Vector2(r.r - 0.3, r.y)).reverse();
  const glassGeo = new THREE.LatheGeometry(prof, 72);
  const wallMat = new THREE.MeshStandardMaterial({ color: T.muted, transparent: true, opacity: 0.1, roughness: 0.08, metalness: 0, depthWrite: false, side: THREE.BackSide });
  const wallMatF = wallMat.clone(); wallMatF.side = THREE.FrontSide; wallMatF.opacity = 0.14;
  const wallB = new THREE.Mesh(glassGeo, wallMat), wallF = new THREE.Mesh(glassGeo, wallMatF);
  wallB.renderOrder = 1; wallF.renderOrder = 2; S.add(wallB, wallF);
  // costillas del embudo: líneas que siguen el perfil
  const ribPts = [];
  for (let k = 0; k < 24; k++) { const a = (k / 24) * Math.PI * 2; for (let j = 0; j < prof.length - 1; j++) ribPts.push(prof[j].x * Math.cos(a), prof[j].y, prof[j].x * Math.sin(a), prof[j + 1].x * Math.cos(a), prof[j + 1].y, prof[j + 1].x * Math.sin(a)); }
  const ribGeo = new THREE.BufferGeometry(); ribGeo.setAttribute('position', new THREE.Float32BufferAttribute(ribPts, 3));
  const ribMat = new THREE.LineBasicMaterial({ color: T.muted, transparent: true, opacity: 0.3 });
  const ribs = new THREE.LineSegments(ribGeo, ribMat); ribs.renderOrder = 3; S.add(ribs);
  // base: plinto con canto, huella de cada etapa sobre el piso y bandeja donde caen las obras terminadas
  const baseMat = mat(T.surface, { roughness: 0.85, envMapIntensity: 0.45 });
  const base = new THREE.Mesh(new THREE.CylinderGeometry(16, 16.3, 0.45, 96), baseMat); base.position.y = -0.725; base.receiveShadow = true; S.add(base);
  const lip = new THREE.Mesh(new THREE.TorusGeometry(16.02, 0.06, 6, 96), baseMat); lip.rotation.x = Math.PI / 2; lip.position.y = -0.52; S.add(lip);
  const prints = rings.map((r) => {
    const m = new THREE.Mesh(new THREE.RingGeometry(r.r - 0.36, r.r + 0.36, 96).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: T.s[r.e.slot - 1], transparent: true, opacity: 0.22, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    m.position.y = -0.495; S.add(m); return m;
  });
  const last = rings[rings.length - 1].r;
  const trayMat = mat(T.s[E[E.length - 1].slot - 1], { roughness: 0.4, metalness: 0.3 });
  const tray = new THREE.Mesh(new THREE.LatheGeometry([new THREE.Vector2(0, -0.5), new THREE.Vector2(last - 0.2, -0.5), new THREE.Vector2(last + 0.1, -0.16), new THREE.Vector2(last + 0.28, -0.12), new THREE.Vector2(last + 0.36, -0.2), new THREE.Vector2(last + 0.2, -0.5)], 72), trayMat);
  tray.position.y = 0.02; tray.receiveShadow = true; tray.castShadow = true; S.add(tray);

  // monedas: proyectos que caen y giran; en cada etapa sobrevive la fracción n(i+1)/n(i)
  const N = 260;
  const survive = E.map((e, i) => (i === 0 ? 1 : e.n / E[i - 1].n));
  const pts = Array.from({ length: N }, () => spawn());
  function spawn(p = {}) {
    const a = Math.random() * Math.PI * 2, rr = Math.random() * rings[0].r * 0.9;
    return Object.assign(p, { x: Math.cos(a) * rr, z: Math.sin(a) * rr, y: top + 2 + Math.random() * 8, vy: 0, stage: 0, leak: false, vx: 0, vz: 0, life: 0, rx: Math.random() * 6, rz: Math.random() * 6, sx: 1 + Math.random() * 3, sz: 0.5 + Math.random() * 2 });
  }
  const cg = coinGeo(0.2, 0.05);
  const coinMat = mat(T.sun, { vertexColors: true, roughness: 0.3, metalness: 0.55 }), deadMat = mat(T.bad, { vertexColors: true, roughness: 0.35, metalness: 0.4 });
  const live = new THREE.InstancedMesh(cg, coinMat, N), dead = new THREE.InstancedMesh(cg, deadMat, N);
  live.frustumCulled = dead.frustumCulled = false; S.add(live); S.add(dead);
  const m4 = new THREE.Matrix4(), zero = new THREE.Matrix4().makeScale(0, 0, 0), q = new THREE.Quaternion(), eu = new THREE.Euler(), v3 = new THREE.Vector3(), one = new THREE.Vector3(1, 1, 1);
  pts.forEach((p) => { p.y = Math.random() * (top + 8); p.stage = Math.max(0, Math.min(E.length - 1, Math.floor((top - p.y) / gap) + 1)); });

  st.onFrame((dt) => {
    const sp = reducedMotion ? 0.35 : 1;
    pts.forEach((p, i) => {
      if (p.leak) {
        p.x += p.vx * dt * sp; p.z += p.vz * dt * sp; p.y -= 2 * dt * sp; p.life += dt;
        if (p.y < -0.4 || p.life > 4) spawn(p);
      } else {
        p.y -= 3.2 * dt * sp;
        const next = rings[p.stage + 1];
        if (next && p.y <= next.y) {
          p.stage++;
          if (Math.random() > survive[p.stage]) { p.leak = true; const a = Math.atan2(p.z, p.x); p.vx = Math.cos(a) * 4; p.vz = Math.sin(a) * 4; }
          else { const k = next.r / rings[p.stage - 1].r; p.x *= k; p.z *= k; }
        }
        if (p.y < -0.3) spawn(p);
      }
      p.rx += p.sx * dt * sp; p.rz += p.sz * dt * sp;
      m4.compose(v3.set(p.x, p.y, p.z), q.setFromEuler(eu.set(p.rx, 0, p.rz)), one);
      live.setMatrixAt(i, p.leak ? zero : m4);
      dead.setMatrixAt(i, p.leak ? m4 : zero);
    });
    live.instanceMatrix.needsUpdate = true; dead.instanceMatrix.needsUpdate = true;
  });
  [boltM, wallB, wallF, ribs, base, lip, tray, ...prints, ...rings.map((r) => r.ring)].forEach((o) => st.freeze(o));

  const stagesEl = root.querySelector('[data-slot="embudo.stages"]');
  stagesEl.innerHTML = `<table><tbody>${E.map((e, i) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--s${e.slot})"></i> ${e.etapa}</td><td class="n">${fmtN(e.n)}</td><td class="n">${i ? fmtN((100 * e.n) / E[0].n, 0) + ' %' : '100 %'}</td></tr>`).join('')}</tbody></table>`;
  root.querySelector('[data-slot="embudo.break"]').innerHTML = EMBUDO.rupturas.map((r) => `<p><b>${r.titulo}.</b> ${r.texto}</p>`).join('');
  const pickEl = root.querySelector('[data-slot="embudo.break"]');
  function info(e) { pickEl.insertAdjacentHTML('afterbegin', `<div class="card" style="background:var(--raised);margin-bottom:8px"><b>${e.etapa}</b><br>${fmtN(e.n)} ${e.unidad}${e.valor ? ` · ${fmtCOP(e.valor)}` : ''}<br><span class="note">${e.nota}</span></div>`); }
  // los objetos de SECOP llegan cortados a 180 caracteres (la obra, a 110), a veces a mitad de palabra: se corta en la
  // última palabra completa, sin conectores sueltos al final, y se marca con «…»
  const fin = (s, n) => {
    const t = s.replace(/\s+/g, ' ').trim();
    if (s.length !== n || /[.…)]$/.test(t)) return t;
    return (/\s$/.test(s) ? t : t.replace(/\s+\S*$/, '')).replace(/(\s+(a|al|con|de|del|e|el|en|la|las|lo|los|o|para|por|que|u|un|una|y))+$/i, '').replace(/[\s,;:-]+$/, '') + '…';
  };
  root.querySelector('[data-slot="embudo.table"]').innerHTML = `<table><thead><tr><th>Año</th><th class="n">Valor</th><th>Objeto (SECOP)</th><th>Obra posterior identificable</th></tr></thead><tbody>${EMBUDO.estudios.map((s) => `<tr><td>${s.anio}</td><td class="n">${fmtCOP(s.valor)}</td><td>${fin(s.objeto, 180)}</td><td>${s.obra ? `Sí (${s.anio_obra}) <span class="note">${fin(s.obra, 110)}</span>` : '<span class="tag est">no hallada</span>'}</td></tr>`).join('')}</tbody></table>`;

  onTheme((t) => {
    rings.forEach((r, i) => { ringMats[i].color.copy(t.s[r.e.slot - 1]); prints[i].material.color.copy(t.s[r.e.slot - 1]); });
    trayMat.color.copy(t.s[E[E.length - 1].slot - 1]);
    wallMat.color.copy(t.muted); wallMatF.color.copy(t.muted); ribMat.color.copy(t.muted); baseMat.color.copy(t.surface); coinMat.color.copy(t.sun); deadMat.color.copy(t.bad);
  });
  return st;
}
