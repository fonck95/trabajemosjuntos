// Escena 3D: embudo de la inversión. Cada anillo es una etapa; los proyectos caen y se "fugan"
// donde el ciclo se rompe (estudios que no llegan a obra, obras que no llegan a operación).
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, fmtN, reducedMotion } from '../core.js';
import { EMBUDO } from '../data.js';

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
  const rings = E.map((e, i) => {
    const y = top - i * gap;
    const m = mat(T.s[e.slot - 1], { transparent: true, opacity: 0.85, roughness: 0.5 });
    ringMats.push(m);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(R(e.n), 0.28, 12, 72), m);
    ring.rotation.x = Math.PI / 2; ring.position.y = y; ring.castShadow = true;
    S.add(ring);
    st.label(`<b>${e.etapa}</b><br>${fmtN(e.n)} ${e.unidad}${e.valor ? ` · ${fmtCOP(e.valor)}` : ''}`, 'lbl-node', [R(e.n) + 1.5, y, 0]);
    st.pickable(ring, { onPick: () => info(e) });
    return { ring, y, r: R(e.n), e };
  });
  // paredes del embudo
  const wallMat = new THREE.MeshBasicMaterial({ color: T.muted, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false });
  for (let i = 0; i < rings.length - 1; i++) {
    const a = rings[i], b = rings[i + 1];
    const w = new THREE.Mesh(new THREE.CylinderGeometry(a.r, b.r, gap, 64, 1, true), wallMat);
    w.position.y = (a.y + b.y) / 2; S.add(w);
  }
  const base = new THREE.Mesh(new THREE.CircleGeometry(16, 64), mat(T.surface)); base.rotation.x = -Math.PI / 2; base.position.y = -0.5; base.receiveShadow = true; S.add(base);

  // partículas: proyectos que caen; en cada etapa sobrevive la fracción n(i+1)/n(i)
  const N = 260;
  const survive = E.map((e, i) => (i === 0 ? 1 : e.n / E[i - 1].n));
  const pts = Array.from({ length: N }, () => spawn());
  function spawn(p = {}) {
    const a = Math.random() * Math.PI * 2, rr = Math.random() * rings[0].r * 0.9;
    return Object.assign(p, { x: Math.cos(a) * rr, z: Math.sin(a) * rr, y: top + 2 + Math.random() * 8, vy: 0, stage: 0, leak: false, vx: 0, vz: 0, life: 0 });
  }
  const live = new THREE.InstancedMesh(new THREE.SphereGeometry(0.16, 8, 6), new THREE.MeshBasicMaterial({ color: T.sun }), N);
  const dead = new THREE.InstancedMesh(new THREE.SphereGeometry(0.14, 8, 6), new THREE.MeshBasicMaterial({ color: T.bad, transparent: true, opacity: 0.8 }), N);
  live.frustumCulled = dead.frustumCulled = false; S.add(live); S.add(dead);
  const m4 = new THREE.Matrix4(), zero = new THREE.Matrix4().makeScale(0, 0, 0);
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
      m4.makeTranslation(p.x, p.y, p.z);
      live.setMatrixAt(i, p.leak ? zero : m4);
      dead.setMatrixAt(i, p.leak ? m4 : zero);
    });
    live.instanceMatrix.needsUpdate = true; dead.instanceMatrix.needsUpdate = true;
  });

  const stagesEl = root.querySelector('[data-slot="embudo.stages"]');
  stagesEl.innerHTML = `<table><tbody>${E.map((e, i) => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--s${e.slot})"></i> ${e.etapa}</td><td class="n">${fmtN(e.n)}</td><td class="n">${i ? fmtN((100 * e.n) / E[0].n, 0) + ' %' : '100 %'}</td></tr>`).join('')}</tbody></table>`;
  root.querySelector('[data-slot="embudo.break"]').innerHTML = EMBUDO.rupturas.map((r) => `<p><b>${r.titulo}.</b> ${r.texto}</p>`).join('');
  const pickEl = root.querySelector('[data-slot="embudo.break"]');
  function info(e) { pickEl.insertAdjacentHTML('afterbegin', `<div class="card" style="background:var(--raised);margin-bottom:8px"><b>${e.etapa}</b><br>${fmtN(e.n)} ${e.unidad}${e.valor ? ` · ${fmtCOP(e.valor)}` : ''}<br><span class="note">${e.nota}</span></div>`); }
  root.querySelector('[data-slot="embudo.table"]').innerHTML = `<table><thead><tr><th>Año</th><th class="n">Valor</th><th>Objeto (SECOP)</th><th>Obra posterior identificable</th></tr></thead><tbody>${EMBUDO.estudios.map((s) => `<tr><td>${s.anio}</td><td class="n">${fmtCOP(s.valor)}</td><td>${s.objeto}</td><td>${s.obra ? `Sí (${s.anio_obra}) <span class="note">${s.obra}</span>` : '<span class="tag est">no hallada</span>'}</td></tr>`).join('')}</tbody></table>`;

  onTheme((t) => {
    rings.forEach((r, i) => ringMats[i].color.copy(t.s[r.e.slot - 1]));
    wallMat.color.copy(t.muted); base.material.color.copy(t.surface); live.material.color.copy(t.sun); dead.material.color.copy(t.bad);
  });
  return st;
}
