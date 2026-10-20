// Escena 3D: la hoja de ruta 2026–2031 como un camino con compuertas. Cada compuerta es una
// condición verificable; si no se cumple, el siguiente contrato no se firma.
import { THREE, Stage, tokens, onTheme, mat, box, fmtCOP, reducedMotion } from '../core.js';
import { RUTA } from '../data.js';

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [0, 64, 92], target: [0, 0, 0], maxDist: 170 });
  const T = tokens();
  const S = st.scene;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(700, 500), mat(T.ground)); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; S.add(ground);

  const H = RUTA.hitos;
  const pts = H.map((h, i) => new THREE.Vector3(-44 + (88 * i) / (H.length - 1), 0.05, Math.sin(i * 0.9) * 12));
  const curve = new THREE.CatmullRomCurve3(pts);
  const roadMat = mat(T.surface);
  const road = new THREE.Mesh(new THREE.TubeGeometry(curve, 300, 1.4, 8, false), roadMat);
  road.scale.y = 0.06; road.receiveShadow = true; S.add(road);
  const fases = RUTA.fases;
  const gMats = fases.map((f) => mat(T.s[f.slot - 1], { roughness: 0.5 }));
  const lintelMats = fases.map((f) => mat(T.s[f.slot - 1], { roughness: 0.5, emissive: T.s[f.slot - 1], emissiveIntensity: 0.15 }));
  const pickEl = root.querySelector('[data-slot="ruta.pick"]');
  const gates = H.map((h, i) => {
    const fi = fases.findIndex((f) => f.id === h.fase);
    const g = new THREE.Group();
    const tan = curve.getTangentAt(i / (H.length - 1));
    g.add(box(0.45, 4.2, 0.45, gMats[fi], 0, 0, -2.2));
    g.add(box(0.45, 4.2, 0.45, gMats[fi], 0, 0, 2.2));
    g.add(box(0.7, 0.6, 5.1, lintelMats[fi], 0, 4.2, 0));
    g.position.copy(pts[i]); g.rotation.y = -Math.atan2(tan.z, tan.x);
    S.add(g);
    st.label(`<b>${h.fecha}</b><br>${h.titulo}`, 'lbl-node', [pts[i].x, 6.4, pts[i].z]);
    st.pickable(g, { onPick: () => pick(h) });
    return g;
  });
  // marcas de año sobre el terreno
  RUTA.anios.forEach((a) => st.label(a.label, 'lbl-geo', [-44 + 88 * a.t, 0.2, 20]));
  const walker = new THREE.Mesh(new THREE.SphereGeometry(0.7, 20, 14), mat(T.sun, { emissive: T.sun, emissiveIntensity: 0.6 }));
  S.add(walker);
  let u = 0;
  st.onFrame((dt) => {
    u = (u + dt * (reducedMotion ? 0.01 : 0.025)) % 1;
    const p = curve.getPointAt(u); walker.position.set(p.x, 1, p.z);
  });

  function pick(h) {
    pickEl.innerHTML = `<p class="eyebrow">${fases.find((f) => f.id === h.fase).nombre}</p><h4>${h.fecha} · ${h.titulo}</h4><p>${h.detalle}</p><p><b>Compuerta:</b> ${h.compuerta}</p>${h.responsable ? `<p class="note">Responsable: ${h.responsable}</p>` : ''}`;
  }
  pick(H[0]);
  root.querySelector('[data-slot="ruta.gates"]').innerHTML = H.map((h) => `<div class="gate"><time>${h.fecha}</time><div><b>${h.titulo}</b>${h.detalle}<br><span class="note">Compuerta: ${h.compuerta}</span></div></div>`).join('');
  root.querySelector('[data-slot="ruta.reglas"]').innerHTML = `<ol class="tight">${RUTA.reglas.map((r) => `<li>${r}</li>`).join('')}</ol>`;
  const P = RUTA.portafolio;
  root.querySelector('[data-slot="ruta.portafolio"]').innerHTML = `<table><thead><tr><th>Proyecto</th><th>Ejecutor / vía</th><th>Fuentes</th><th>Fase</th><th class="n">Inversión</th></tr></thead><tbody>${P.map((p) => `<tr><td><b>${p.nombre}</b><br><span class="note">${p.alcance}</span></td><td>${p.ejecutor}</td><td>${p.fuentes}</td><td>${p.fase}</td><td class="n">${fmtCOP(p.valor * 1e6)}</td></tr>`).join('')}</tbody><tfoot><tr><td colspan="4">Total portafolio</td><td class="n">${fmtCOP(P.reduce((a, p) => a + p.valor, 0) * 1e6)}</td></tr></tfoot></table>`;

  onTheme((t) => {
    ground.material.color.copy(t.ground); roadMat.color.copy(t.surface);
    fases.forEach((f, i) => { gMats[i].color.copy(t.s[f.slot - 1]); lintelMats[i].color.copy(t.s[f.slot - 1]); lintelMats[i].emissive.copy(t.s[f.slot - 1]); });
    walker.material.color.copy(t.sun); walker.material.emissive.copy(t.sun);
  });
  return st;
}
