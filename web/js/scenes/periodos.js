// Escena 3D: matriz área × periodo de gobierno. Altura = desempeño normalizado 0–100.
import { THREE, Stage, tokens, onTheme, mat, fmtN } from '../core.js';
import { PERIODOS, AREAS } from '../data.js';

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [42, 28, 40], target: [0, 3, 0], maxDist: 110 });
  const T = tokens();
  const S = st.scene;
  const GX = 4, GZ = 3.1, H = 9;
  const x0 = -((PERIODOS.length - 1) * GX) / 2, z0 = -((AREAS.length - 1) * GZ) / 2;
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(PERIODOS.length * GX + 9, AREAS.length * GZ + 7), mat(T.surface));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; S.add(floor);
  // planos de referencia 50 y 100
  const refMat = new THREE.MeshBasicMaterial({ color: T.line, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false });
  [0.5, 1].forEach((f) => {
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(PERIODOS.length * GX, 0.02), refMat);
    const fr = new THREE.Mesh(new THREE.PlaneGeometry(0.02, AREAS.length * GZ), refMat);
    pl.position.set(0, f * H, z0 - 1.6); S.add(pl); fr.position.set(x0 - 2, f * H, 0); fr.rotation.y = Math.PI / 2; S.add(fr);
    st.label(f === 1 ? '100' : '50', 'lbl-axis', [x0 - 2.4, f * H, z0 - 1.6]);
  });

  const colLabels = PERIODOS.map((p, i) => {
    const l = st.label(`${p.id.replace('-', '–')}`, 'lbl-title', [x0 + i * GX, 0.2, z0 + AREAS.length * GZ - 0.8]);
    l.element.style.pointerEvents = 'auto'; l.element.style.cursor = 'pointer';
    l.element.addEventListener('click', () => select(i));
    return l;
  });
  AREAS.forEach((a, j) => st.label(a.corto, 'lbl-axis', [x0 - 3.4, 0.2, z0 + j * GZ]));

  const geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);
  const ghostGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(2, 1.2, 1.8));
  const mats = AREAS.map((a) => mat(T.s[a.slot - 1], { roughness: 0.55 }));
  const dimMats = AREAS.map((a) => mat(T.s[a.slot - 1], { roughness: 0.55, transparent: true, opacity: 0.22 }));
  const ghostMat = new THREE.LineBasicMaterial({ color: T.muted });
  const cells = [];
  PERIODOS.forEach((p, i) => AREAS.forEach((a, j) => {
    const v = a.valores[p.id];
    const x = x0 + i * GX, z = z0 + j * GZ;
    let obj;
    if (v == null) {
      obj = new THREE.LineSegments(ghostGeo, ghostMat); obj.position.set(x, 0.6, z);
    } else {
      obj = new THREE.Mesh(geo, mats[j]); obj.position.set(x, 0, z); obj.scale.set(2, Math.max(0.08, (v / 100) * H), 1.8); obj.castShadow = true;
      const l = st.label(fmtN(v, 0), 'lbl-val', [x, (v / 100) * H + 0.6, z]);
      cells.push({ obj, l, i, j });
    }
    S.add(obj);
    st.pickable(obj, { onPick: () => { select(i); detailCell(a, p, v); } });
    if (v == null) cells.push({ obj, i, j, ghost: true });
  }));

  // selector, detalle y tabla
  const seg = root.querySelector('[data-slot="periodos.seg"]');
  seg.innerHTML = PERIODOS.map((p, i) => `<button type="button" data-i="${i}" aria-pressed="false">${p.id.replace('-', '–')}</button>`).join('');
  seg.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => select(+b.dataset.i)));
  const det = root.querySelector('[data-slot="periodos.detail"]');
  const list = (arr) => `<ul class="tight">${arr.map((x) => `<li>${x}</li>`).join('')}</ul>`;
  function select(i) {
    const p = PERIODOS[i];
    seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', +b.dataset.i === i));
    cells.forEach((c) => { if (!c.ghost) { c.obj.material = c.i === i ? mats[c.j] : dimMats[c.j]; c.l.element.hidden = c.i !== i; } });
    colLabels.forEach((l, k) => { l.element.style.opacity = k === i ? 1 : 0.5; });
    det.innerHTML = `<h4>${p.id.replace('-', '–')} · ${p.alcalde}</h4>
      <p class="note">${p.plan || ''}</p>
      ${p.plata ? `<p class="tag" style="display:inline-block;margin-bottom:8px">${p.plata}</p>` : ''}
      <p><b>Lo que se hizo</b></p>${list(p.hizo)}
      <p><b>Lo que pudo hacerse y no se hizo</b></p>${list(p.falto)}
      ${p.alertas?.length ? `<p><b>Alertas de control</b></p>${list(p.alertas)}` : ''}
      ${p.contexto ? `<p class="note">${p.contexto}</p>` : ''}`;
  }
  function detailCell(a, p, v) {
    const extra = a.detalle?.[p.id];
    det.insertAdjacentHTML('afterbegin', `<div class="card" style="margin-bottom:10px;background:var(--raised)"><b>${a.nombre}</b> · ${p.id}<br>${v == null ? 'Sin dato verificable para este periodo.' : `Puntaje normalizado: <b>${fmtN(v, 0)}</b> / 100`}${extra ? `<br><span class="note">${extra}</span>` : ''}<br><span class="note">${a.metodo}</span></div>`);
  }
  root.querySelector('[data-slot="periodos.table"]').innerHTML = `<table><thead><tr><th>Área (fuente)</th>${PERIODOS.map((p) => `<th class="n">${p.id}</th>`).join('')}</tr></thead><tbody>${AREAS.map((a) => `<tr><td>${a.nombre}<br><span class="note">${a.fuente}</span></td>${PERIODOS.map((p) => `<td class="n">${a.crudo?.[p.id] ?? (a.valores[p.id] == null ? '—' : fmtN(a.valores[p.id], 0))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  select(PERIODOS.length - 1);

  onTheme((t) => {
    floor.material.color.copy(t.surface); refMat.color.copy(t.line); ghostMat.color.copy(t.muted);
    AREAS.forEach((a, j) => { mats[j].color.copy(t.s[a.slot - 1]); dimMats[j].color.copy(t.s[a.slot - 1]); });
  });
  return st;
}
