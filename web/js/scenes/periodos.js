// Comparativa entre gobiernos (2004–2027).
// Modo "La plata": una pila de billetes por gobierno. Cada fajo vale lo mismo; la pila sólida es lo que entró
// (pesos constantes de 2026), los fajos rojos lo que no se convirtió en obra (registros verificables), los
// naranjas lo estimado y los fajos huecos de arriba lo que pudo gestionarse o ahorrarse y no se hizo.
// Modo "Indicadores": la matriz área × periodo con el desempeño normalizado 0–100.
// Debajo: la cuenta de cada gobierno en barras, equivalencias en obras y el panel anual con ~50 indicadores.
import { THREE, Stage, tokens, onTheme, mat, fmtN, gsap } from '../core.js';
import { PERIODOS, AREAS, DINERO, PANEL } from '../data.js';

const fmtM = (v) => (v == null || Number.isNaN(v) ? '—' : Math.abs(v) >= 1e6 ? `$${fmtN(v / 1e6, 2)} billones` : Math.abs(v) >= 1000 ? `$${fmtN(v / 1000, 1)} mil M` : `$${fmtN(v, 0)} M`);
const short = (s) => (s || '').split(/[(;]/)[0].trim();

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [6, 16, 50], target: [0, 7, 0], maxDist: 130, dynamicShadows: true, env: false });
  const T = tokens();
  const S = st.scene;
  const D = DINERO?.periodos?.length ? DINERO : null;
  const n = PERIODOS.length;
  const GX = 7.2, x0 = -((n - 1) * GX) / 2;
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(n * GX + 10, 30), mat(T.surface)); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; S.add(floor);
  st.freeze(floor);

  // ---------------------------------------------------------------- modo "La plata"
  const plata = new THREE.Group(); S.add(plata);
  const perD = (id) => D?.periodos.find((p) => p.id === id);
  const sum = (arr, f) => (arr || []).reduce((a, x) => a + (+f(x) || 0), 0);
  const cuentas = PERIODOS.map((p) => {
    const d = perD(p.id) || {};
    const ingresos = +d.ingresos || 0;
    const tot = (k, tipo) => d[k] ?? sum((d.fugas || []).filter((f) => f.tipo === tipo), (f) => f.valor);
    const hecho = Math.min(tot('total_hecho', 'hecho'), ingresos);
    const estimado = Math.min(tot('total_estimado', 'estimado'), Math.max(0, ingresos - hecho));
    const indicio = Math.min(tot('total_indicio', 'indicio'), Math.max(0, ingresos - hecho - estimado));
    const quieta = tot('total_plata_quieta', 'plata quieta');
    const contra = tot('total_contrafactual', 'contrafactual');
    return { p, d, ingresos, hecho, estimado, indicio, quieta, contra, sinObra: d.sin_obra ?? hecho + estimado };
  });
  const maxTot = Math.max(1, ...cuentas.map((c) => c.ingresos + c.quieta + c.contra));
  // un fajo = valor redondo que deja la pila más alta en ~70 fajos
  const steps = [1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000];
  const UNIT = steps.find((u) => maxTot / u <= 75) || 100000;
  const SLAB = { w: 3.2, h: 0.2, d: 1.7, gap: 0.045 };
  // lo que entró va en gris para que el rojo y el naranja (lo que no se hizo) salten a la vista
  const baseCol = (t) => t.ink.clone().lerp(t.surface, 0.55);
  const slabGeo = new THREE.BoxGeometry(SLAB.w, SLAB.h, SLAB.d); slabGeo.translate(0, SLAB.h / 2, 0);
  // orden de la pila: lo que entró (con sus fugas encima) y, por fuera de la caja, la plata quieta y lo no gestionado
  const kinds = [
    { key: 'base', css: 'color-mix(in srgb, var(--ink) 45%, var(--surface))', mat: mat(baseCol(T), { roughness: 0.6 }), label: 'Entró y se gastó sin fuga identificada' },
    { key: 'hecho', css: 'var(--bad)', mat: mat(T.bad, { roughness: 0.5 }), label: 'No se convirtió en obra (registros)' },
    { key: 'estimado', css: 'var(--warn)', mat: mat(T.warn, { roughness: 0.5 }), label: 'Sobrecosto y pérdidas estimadas' },
    { key: 'indicio', css: 'color-mix(in srgb, var(--warn) 45%, transparent)', mat: mat(T.warn, { transparent: true, opacity: 0.45, roughness: 0.5 }), label: 'Indicio por verificar (OPS por encima de lo usual)' },
    { key: 'quieta', css: 'color-mix(in srgb, var(--data) 55%, transparent)', mat: mat(T.data, { transparent: true, opacity: 0.55, roughness: 0.4 }), label: 'Plata quieta: regalías sin aprobar o sin comprometer' },
    { key: 'contra', css: 'transparent', hollow: true, mat: mat(T.accent, { transparent: true, opacity: 0.18, roughness: 0.4, depthWrite: false }), label: 'Pudo gestionarse o ahorrarse y no se hizo' },
  ];
  const K = Object.fromEntries(kinds.map((k) => [k.key, k]));
  const plan = [];   // [{kind, i, k(index en pila)}]
  cuentas.forEach((c, i) => {
    const cnt = (v) => Math.round(v / UNIT) || (v > 0 ? 1 : 0);
    const counts = { hecho: cnt(c.hecho), estimado: cnt(c.estimado), indicio: cnt(c.indicio), quieta: cnt(c.quieta), contra: Math.round(c.contra / UNIT) };
    counts.base = Math.max(0, Math.round(c.ingresos / UNIT) - counts.hecho - counts.estimado - counts.indicio);
    let k = 0;
    for (const kind of ['base', 'hecho', 'estimado', 'indicio', 'quieta', 'contra']) for (let j = 0; j < counts[kind]; j++, k++) plan.push({ kind, i, k });
    c.counts = counts; c.height = k * (SLAB.h + SLAB.gap);
  });
  const meshes = {};
  kinds.forEach((kd) => {
    const cnt = plan.filter((q) => q.kind === kd.key).length;
    const m = new THREE.InstancedMesh(slabGeo, kd.mat, Math.max(1, cnt)); m.count = cnt; m.castShadow = !kd.hollow && kd.key !== 'quieta'; m.receiveShadow = true;
    meshes[kd.key] = m; plata.add(m);
    if (kd.hollow) {
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(slabGeo), new THREE.LineBasicMaterial({ color: T.accent, transparent: true, opacity: 0.85 }));
      kd.edges = []; plan.filter((q) => q.kind === kd.key).forEach(() => { const e = edges.clone(); kd.edges.push(e); plata.add(e); });
    }
  });
  const m4 = new THREE.Matrix4(), jitter = (i, k) => (((i * 31 + k * 17) % 7) - 3) * 0.035;
  let progress = gsap ? 0 : 1;
  function layoutSlabs() {
    const idx = Object.fromEntries(kinds.map((k) => [k.key, 0]));
    plan.forEach((q) => {
      const t = Math.min(1, Math.max(0, progress * (plan.length / 40 + 1) - (q.k / 70) - q.i * 0.05));
      const y = q.k * (SLAB.h + SLAB.gap), drop = (1 - t) * (1 - t) * 18;
      const x = x0 + q.i * GX + jitter(q.i, q.k), z = jitter(q.k, q.i);
      m4.makeRotationY(jitter(q.k + 3, q.i) * 0.4).setPosition(x, y + drop, z);
      if (t <= 0) m4.makeScale(0, 0, 0);
      meshes[q.kind].setMatrixAt(idx[q.kind], m4);
      if (K[q.kind].hollow) { const e = K[q.kind].edges[idx[q.kind]]; e.matrixAutoUpdate = false; e.matrix.copy(m4); e.visible = t > 0; }
      idx[q.kind]++;
    });
    Object.values(meshes).forEach((m) => { m.instanceMatrix.needsUpdate = true; m.computeBoundingSphere(); });
    st.updateShadows();
  }
  layoutSlabs();
  const playDrop = () => { if (!gsap) return; progress = 0; gsap.to({ v: 0 }, { v: 1, duration: 2.2, ease: 'power2.out', onUpdate() { progress = this.targets()[0].v; layoutSlabs(); st.invalidate(true); } }); };

  // etiquetas por pila
  const pileLabels = cuentas.map((c, i) => {
    const x = x0 + i * GX, lv = SLAB.h + SLAB.gap;
    const base = st.label(`<b>${c.p.id.replace('-', '–')}</b><br><small>${short(c.p.alcalde).split(' ').slice(0, 2).join(' ')}</small>`, 'lbl-title lbl-pila', [x, 0.2, 4.4], plata);
    base.element.style.pointerEvents = 'auto'; base.element.style.cursor = 'pointer'; base.element.addEventListener('click', () => select(i));
    const top = st.label(`${fmtM(c.ingresos)}<small>entró</small>`, 'lbl-money', [x, c.height + 1.2, 0], plata);
    const red = c.sinObra > 0 ? st.label(`${fmtM(c.sinObra)} <small>sin obra</small>`, 'lbl-val', [x + 2.9, (c.counts.base + (c.counts.hecho + c.counts.estimado) / 2) * lv, 0], plata) : null;
    if (red) red.element.style.color = 'var(--bad)';
    return { base, top, red };
  });
  st.label(`1 fajo =<br>${fmtM(UNIT)}<br>de 2026`, 'lbl-axis lbl-val', [x0 - 4.6, 3, 0], plata);
  // zona de selección (invisible) por pila
  const hit = new THREE.MeshBasicMaterial({ visible: false });
  cuentas.forEach((c, i) => { const h = new THREE.Mesh(new THREE.BoxGeometry(SLAB.w + 0.8, Math.max(1, c.height) + 1, SLAB.d + 1), hit); h.position.set(x0 + i * GX, (Math.max(1, c.height) + 1) / 2, 0); plata.add(h); st.pickable(h, { onPick: () => select(i) }); });

  // ---------------------------------------------------------------- modo "Indicadores" (matriz 0–100)
  const ind = new THREE.Group(); ind.visible = false; S.add(ind);
  const GZ = 3.1, H = 9, z0 = -((AREAS.length - 1) * GZ) / 2, IX = 4, ix0 = -((n - 1) * IX) / 2;
  const geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);
  const ghostGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(2, 1.2, 1.8));
  const amats = AREAS.map((a) => mat(T.s[a.slot - 1], { roughness: 0.55 }));
  const dimMats = AREAS.map((a) => mat(T.s[a.slot - 1], { roughness: 0.55, transparent: true, opacity: 0.22 }));
  const ghostMat = new THREE.LineBasicMaterial({ color: T.muted });
  const cells = [];
  PERIODOS.forEach((p, i) => AREAS.forEach((a, j) => {
    const v = a.valores[p.id], x = ix0 + i * IX, z = z0 + j * GZ;
    let obj;
    if (v == null) { obj = new THREE.LineSegments(ghostGeo, ghostMat); obj.position.set(x, 0.6, z); cells.push({ obj, i, j, ghost: true }); }
    else {
      obj = new THREE.Mesh(geo, amats[j]); obj.position.set(x, 0, z); obj.userData.h = Math.max(0.08, (v / 100) * H); obj.scale.set(2, obj.userData.h, 1.8); obj.castShadow = true;
      cells.push({ obj, i, j, l: st.label(fmtN(v, 0), 'lbl-val', [x, (v / 100) * H + 0.6, z], ind) });
    }
    ind.add(obj);
    st.pickable(obj, { onPick: () => { select(i); detailCell(a, p, v); } });
  }));
  PERIODOS.forEach((p, i) => st.label(p.id.replace('-', '–'), 'lbl-title', [ix0 + i * IX, 0.2, z0 + AREAS.length * GZ - 0.8], ind));
  AREAS.forEach((a, j) => st.label(a.corto, 'lbl-axis', [ix0 - 3.4, 0.2, z0 + j * GZ], ind));
  // CSS2DRenderer no mira la visibilidad del grupo padre: se apaga cada etiqueta
  const hideLabels = (g, v) => g.traverse((o) => { if (o.isCSS2DObject) o.visible = v; });
  hideLabels(ind, false);

  let mode = D ? 'plata' : 'indicadores';
  const modeBtns = root.querySelectorAll('[data-modo-periodos]');
  if (!D) modeBtns.forEach((b) => { if (b.dataset.modoPeriodos === 'plata') b.disabled = true; });
  function setMode(m) {
    mode = m;
    modeBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modoPeriodos === m)));
    plata.visible = m === 'plata'; ind.visible = m === 'indicadores';
    hideLabels(plata, m === 'plata'); hideLabels(ind, m === 'indicadores');
    if (m === 'indicadores') { st.flyTo([42, 28, 40], [0, 3, 0], 1.2); select(sel); }
    else { st.flyTo([6, 16, 50], [0, 7, 0], 1.2); playDrop(); }
    root.querySelector('[data-t="periodos.stamp"]')?.replaceChildren(document.createTextNode(m === 'plata' ? `Cada fajo = ${fmtM(UNIT)} de 2026 · rojo = no se convirtió en obra (registros) · naranja = estimado · hueco = pudo gestionarse y no se hizo` : 'Altura = desempeño normalizado 0–100 · columna hueca = sin dato verificable'));
    st.updateShadows();
  }
  modeBtns.forEach((b) => b.addEventListener('click', () => setMode(b.dataset.modoPeriodos)));

  // ---------------------------------------------------------------- selector y detalle
  const seg = root.querySelector('[data-slot="periodos.seg"]');
  seg.innerHTML = PERIODOS.map((p, i) => `<button type="button" data-i="${i}" aria-pressed="false">${p.id.replace('-', '–')}</button>`).join('');
  seg.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => select(+b.dataset.i)));
  const det = root.querySelector('[data-slot="periodos.detail"]');
  const list = (arr) => `<ul class="tight">${(arr || []).map((x) => `<li>${x}</li>`).join('')}</ul>`;
  let sel = n - 1;
  function select(i) {
    sel = i;
    const p = PERIODOS[i], c = cuentas[i], d = c.d;
    seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.i === i)));
    cells.forEach((cl) => { if (!cl.ghost) { cl.obj.material = cl.i === i ? amats[cl.j] : dimMats[cl.j]; if (cl.l) cl.l.element.hidden = cl.i !== i; } });
    if (mode === 'indicadores' && gsap) cells.filter((cl) => !cl.ghost && cl.i === i).forEach((cl, k) => gsap.fromTo(cl.obj.scale, { y: 0.05 }, { y: cl.obj.userData.h, duration: 0.8, delay: k * 0.06, ease: 'power3.out', overwrite: true, onUpdate: () => st.invalidate() }));
    pileLabels.forEach((l, k) => { l.base.element.style.opacity = k === i ? 1 : 0.55; });
    const noObra = c.sinObra;
    det.innerHTML = `<h4>${p.id.replace('-', '–')} · ${p.alcalde}</h4>
      ${D ? `<div class="money-big"><div><b>${fmtM(c.ingresos)}</b><span>entraron${d?.en_curso ? ' (solo años con dato; periodo en curso)' : ''} · pesos de 2026</span></div>
        <div class="bad"><b>${fmtM(noObra)}</b><span>no se convirtieron en obra${c.estimado ? ` (${fmtM(c.hecho)} en registros + ${fmtM(c.estimado)} estimado)` : ''}${d?.sin_obra_rango ? ` · rango ${fmtM(d.sin_obra_rango[0])}–${fmtM(d.sin_obra_rango[1])}` : ''}</span></div>
        ${c.indicio ? `<div class="ind"><b>${fmtM(c.indicio)}</b><span>indicio por verificar (no suma en "sin obra")</span></div>` : ''}
        ${c.quieta ? `<div class="quieta"><b>${fmtM(c.quieta)}</b><span>plata quieta: regalías sin aprobar o sin comprometer al cierre (no es plata perdida)</span></div>` : ''}
        <div class="ghost"><b>${fmtM(c.contra)}</b><span>pudieron gestionarse o ahorrarse y no se hizo</span></div></div>` : ''}
      ${d?.lectura ? `<p>${d.lectura}</p>` : ''}
      <p class="note">${p.plan || ''}</p>
      <details${D ? '' : ' open'}><summary>Lo que se hizo y lo que faltó</summary>
      <p><b>Lo que se hizo</b></p>${list(p.hizo)}
      <p><b>Lo que pudo hacerse y no se hizo</b></p>${list(p.falto)}
      ${p.alertas?.length ? `<p><b>Alertas de control</b></p>${list(p.alertas)}` : ''}
      ${p.contexto ? `<p class="note">${p.contexto}</p>` : ''}</details>`;
    if (gsap) gsap.from(det, { opacity: 0, y: 8, duration: 0.35, ease: 'power2.out' });
    renderBars(); renderPudo(); renderPanel();
    st.invalidate();
  }
  function detailCell(a, p, v) {
    const extra = a.detalle?.[p.id];
    det.insertAdjacentHTML('afterbegin', `<div class="card" style="margin-bottom:10px;background:var(--raised)"><b>${a.nombre}</b> · ${p.id}<br>${v == null ? 'Sin dato verificable para este periodo.' : `Puntaje normalizado: <b>${fmtN(v, 0)}</b> / 100`}${extra ? `<br><span class="note">${extra}</span>` : ''}<br><span class="note">${a.metodo}</span></div>`);
  }

  // ---------------------------------------------------------------- la cuenta de cada gobierno (barras SVG)
  const barsEl = root.querySelector('[data-slot="periodos.cuenta"]');
  const legendEl = root.querySelector('[data-slot="periodos.leyenda"]');
  if (legendEl) legendEl.innerHTML = kinds.map((k) => `<span><i class="${k.hollow ? 'hollow' : ''}" style="background:${k.css}"></i>${k.label}</span>`).join('');
  function renderBars() {
    if (!barsEl) return;
    if (!D) { barsEl.innerHTML = '<p class="note">La cuenta por gobierno se está consolidando.</p>'; return; }
    const W = 880, rowH = 46, lab = 150, maxW = W - lab - 300, sc = maxW / maxTot;
    const rows = cuentas.map((c, i) => {
      const y = 10 + i * rowH, on = i === sel ? ' on' : '';
      // dentro de la caja: base, registros, estimado, indicio; por fuera: plata quieta y lo no gestionado
      const segs = [['b0', c.ingresos - c.hecho - c.estimado - c.indicio], ['b1', c.hecho], ['b2', c.estimado], ['b2i', c.indicio], ['b4', c.quieta], ['b3', c.contra]];
      let x = lab;
      const rects = segs.map(([cls, v]) => { const w = Math.max(0, v * sc); const r = w > 0 ? `<rect x="${x + (cls === 'b4' || cls === 'b3' ? 2 : 0)}" y="${cls === 'b3' ? 6 : 4}" width="${Math.max(0, w - (cls === 'b4' || cls === 'b3' ? 2 : 0))}" height="${cls === 'b3' ? 24 : 28}" class="${cls}"><title>${fmtM(v)}</title></rect>` : ''; x += w; return r; }).join('');
      return `<g class="row${on}" data-i="${i}" transform="translate(0,${y})">
        <text x="0" y="16" class="per">${c.p.id.replace('-', '–')}</text><text x="0" y="31" class="who">${short(c.p.alcalde).split(' ').slice(0, 3).join(' ')}</text>
        ${rects}
        <text x="${x + 8}" y="17" class="v">${fmtM(c.sinObra)} sin obra${c.d?.sin_obra_pct_ingresos != null ? ` (${fmtN(c.d.sin_obra_pct_ingresos, 1)} %)` : ''}</text>
        <text x="${x + 8}" y="31" class="v2">${fmtM(c.contra)} sin gestionar${c.quieta ? ` · ${fmtM(c.quieta)} quieta` : ''}</text>
      </g>`;
    }).join('');
    barsEl.innerHTML = `<svg viewBox="0 0 ${W} ${cuentas.length * rowH + 20}" class="cuenta" role="img" aria-label="Por gobierno: lo que entró, lo que no se convirtió en obra y lo que pudo gestionarse">${rows}</svg>`;
    barsEl.querySelectorAll('g.row').forEach((g) => g.addEventListener('click', () => select(+g.dataset.i)));
    if (gsap) gsap.from(barsEl.querySelectorAll('g.row rect'), { attr: { width: 0 }, duration: 0.7, stagger: 0.015, ease: 'power2.out' });
  }

  // ---------------------------------------------------------------- lo que se pudo hacer (equivalencias y lista)
  const pudoEl = root.querySelector('[data-slot="periodos.pudo"]');
  // textos largos: primera frase visible y el resto plegado
  const plegar = (t) => {
    t = String(t || ''); if (t.length <= 200) return `<span class="note">${t}</span>`;
    const cut = t.slice(0, 200).lastIndexOf('. ') > 60 ? t.slice(0, 200).lastIndexOf('. ') + 1 : 180;
    return `<details class="fold"><summary class="note">${t.slice(0, cut)} <span>Ver más</span></summary><span class="note">${t.slice(cut)}</span></details>`;
  };
  const ICON = {
    aulas: '<path d="M3 10 12 4l9 6v10H3z"/><path d="M9 20v-6h6v6"/>', vivienda: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/>',
    km: '<path d="M4 20 10 4h4l6 16"/><path d="M12 7v2M12 12v2M12 17v2"/>', ptar: '<circle cx="12" cy="13" r="7"/><path d="M12 3c2 3 3 4.5 3 6a3 3 0 0 1-6 0c0-1.5 1-3 3-6z"/>',
    kwp: '<rect x="3" y="7" width="18" height="11" rx="1"/><path d="M3 12h18M9 7v11M15 7v11"/>', ambulancia: '<rect x="2" y="8" width="13" height="9" rx="1"/><path d="M15 11h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 10v5M5.5 12.5h5"/>',
    beca: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>', default: '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M9 10.5c0-1.4 6-1.4 6 0s-6 1.6-6 3 6 1.4 6 0"/>',
  };
  const iconFor = (u) => { const s = (u || '').toLowerCase(); return ICON[Object.keys(ICON).find((k) => s.includes(k.slice(0, 4))) || (s.includes('placa') || s.includes('pav') ? 'km' : s.includes('agua') || s.includes('tratamiento') ? 'ptar' : s.includes('solar') ? 'kwp' : 'default')]; };
  function renderPudo() {
    if (!pudoEl) return;
    const d = cuentas[sel].d;
    if (!D || !d) { pudoEl.innerHTML = '<p class="note">Las equivalencias se están consolidando.</p>'; return; }
    const eq = (d.equivalencias || []).slice(0, 4).map((e) => {
      const nIcons = Math.min(60, Math.max(1, Math.round(e.n)));
      return `<div class="eq"><b>${fmtN(e.n, e.n < 10 ? 1 : 0)}</b><span>${e.unidad}</span><div class="icons">${Array.from({ length: nIcons }, () => `<svg viewBox="0 0 24 24" aria-hidden="true">${iconFor(e.unidad)}</svg>`).join('')}${e.n > 60 ? '<em>…</em>' : ''}</div></div>`;
    }).join('');
    const pudo = (d.pudo_hacerse || []).map((x) => `<tr><td><b>${x.que}</b>${x.por_que_no ? `<br>${plegar(x.por_que_no)}` : ''}</td><td class="n">${fmtM(x.costo)}</td><td>${x.equivalencia || ''}</td></tr>`).join('');
    const fondos = (d.fondos_no_gestionados || []).map((f) => `<li><b>${f.fondo}</b>${f.desde ? ` (desde ${f.desde})` : ''}: ${typeof f.monto_referencia === 'number' ? fmtM(f.monto_referencia) : f.monto_referencia || ''}${f.comparable ? ` · <span class="note">${f.comparable}</span>` : ''}</li>`).join('');
    const fugas = (d.fugas || []).filter((f) => f.valor).sort((a, b) => b.valor - a.valor).map((f) => {
      const cat = DINERO.categorias?.find((c) => c.id === f.categoria);
      return `<tr><td>${cat?.nombre || f.categoria}<br>${plegar(f.detalle)}</td><td><span class="tag ${f.tipo === 'hecho' ? 'ver' : f.tipo === 'estimado' || f.tipo === 'indicio' ? 'est' : 'sup'}">${f.tipo}</span></td><td class="n">${fmtM(f.valor)}${f.min != null && f.max != null ? `<br><span class="note">${fmtM(f.min)}–${fmtM(f.max)}</span>` : ''}</td></tr>`;
    }).join('');
    pudoEl.innerHTML = `<h3>${PERIODOS[sel].id.replace('-', '–')}: con la plata que no se volvió obra se habría podido…</h3>
      <div class="eqs">${eq || '<p class="note">Sin equivalencias calculadas.</p>'}</div>
      <div class="cols2">
        <div><h4>Obras que Yondó necesitaba en ese momento</h4><div class="tbl-wrap"><table><thead><tr><th>Qué</th><th class="n">Costo</th><th>Equivale a</th></tr></thead><tbody>${pudo || '<tr><td colspan="3" class="note">—</td></tr>'}</tbody></table></div></div>
        <div><h4>Dónde se fue o dejó de entrar la plata</h4><div class="tbl-wrap"><table><thead><tr><th>Categoría</th><th>Tipo</th><th class="n">Valor</th></tr></thead><tbody>${fugas || '<tr><td colspan="3" class="note">—</td></tr>'}</tbody></table></div>
        ${fondos ? `<h4>Fondos que no se gestionaron</h4><ul class="tight">${fondos}</ul>` : ''}</div>
      </div>`;
    if (gsap) gsap.from(pudoEl.querySelectorAll('.eq .icons svg'), { scale: 0, transformOrigin: '50% 50%', duration: 0.3, stagger: { each: 0.008, from: 'start' }, ease: 'back.out(2)' });
  }

  // ---------------------------------------------------------------- panel anual (pequeños múltiplos)
  const panelEl = root.querySelector('[data-slot="periodos.panel"]');
  const areaSeg = root.querySelector('[data-slot="periodos.areas"]');
  const P = PANEL?.indicadores?.length ? PANEL : null;
  const areas = P ? [...new Set(P.indicadores.map((x) => x.area))] : [];
  let area = areas[0];
  if (areaSeg) {
    areaSeg.innerHTML = areas.map((a) => `<button type="button" data-a="${a}" aria-pressed="${a === area}">${a}</button>`).join('');
    areaSeg.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { area = b.dataset.a; areaSeg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); renderPanel(); }));
  }
  const Y0 = 2004, Y1 = 2026;
  // fuente abreviada: la entidad y el conjunto de datos, sin URLs ni rutas (el texto completo queda en el título)
  const srcShort = (f) => { const t = String(f || '').replace(/\(?https?:\/\/[^\s);]+\)?/g, '').replace(/data\/fuentes\/[^\s;,)]+/g, '').split(';')[0].replace(/[\s,(]+$/, '').trim(); return t.length > 90 ? `${t.slice(0, 88)}…` : t; };
  function spark(ind) {
    const W = 220, Hh = 64, padL = 4, padR = 4, padT = 8, padB = 14;
    const pts = Object.entries(ind.serie || {}).map(([y, v]) => [+y, +v]).filter(([y, v]) => y >= Y0 && y <= Y1 && Number.isFinite(v)).sort((a, b) => a[0] - b[0]);
    if (pts.length < 2) return null;
    const vs = pts.map((p) => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || Math.abs(hi) || 1;
    const X = (y) => padL + ((y - Y0) / (Y1 - Y0)) * (W - padL - padR), Yv = (v) => padT + (1 - (v - lo) / span) * (Hh - padT - padB);
    const bands = PERIODOS.map((p, i) => { const a = +p.id.slice(0, 4), b = Math.min(Y1, +p.id.slice(5)); return `<rect x="${X(a)}" y="0" width="${X(b + 1) - X(a)}" height="${Hh - padB + 2}" class="band${i === sel ? ' on' : ''}${i % 2 ? ' alt' : ''}"/>`; }).join('');
    const path = pts.map(([y, v], k) => `${k ? 'L' : 'M'}${X(y).toFixed(1)},${Yv(v).toFixed(1)}`).join('');
    const dots = pts.map(([y, v]) => `<circle cx="${X(y).toFixed(1)}" cy="${Yv(v).toFixed(1)}" r="1.8"><title>${y}: ${fmtN(v, Math.abs(v) < 10 ? 2 : 0)} ${ind.unidad || ''}</title></circle>`).join('');
    const a = +PERIODOS[sel].id.slice(0, 4), b = +PERIODOS[sel].id.slice(5);
    const inP = pts.filter(([y]) => y >= a - 1 && y <= b);
    let delta = '';
    if (inP.length >= 2) {
      const d0 = inP[0][1], d1 = inP[inP.length - 1][1], up = d1 > d0, good = ind.mejor ? (ind.mejor === 'alto') === up : null;
      delta = `<span class="delta ${good == null ? '' : good ? 'good' : 'bad'}">${up ? '▲' : d1 < d0 ? '▼' : '='} ${fmtN(d0, Math.abs(d0) < 10 ? 2 : 0)} → ${fmtN(d1, Math.abs(d1) < 10 ? 2 : 0)}</span>`;
    } else delta = '<span class="delta">sin dato en el periodo</span>';
    return `<div class="spark"><p><b>${ind.nombre}</b> <span class="note">${ind.unidad || ''}</span></p>
      <svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${ind.nombre}, ${pts[0][0]}–${pts[pts.length - 1][0]}">${bands}<path d="${path}"/>${dots}<text x="${padL}" y="${Hh - 2}">${Y0}</text><text x="${W - padR}" y="${Hh - 2}" text-anchor="end">${Y1}</text></svg>
      ${delta}<p class="src" title="${(ind.fuente || '').replace(/"/g, '&quot;')}">${srcShort(ind.fuente)}</p></div>`;
  }
  function renderPanel() {
    if (!panelEl) return;
    if (!P) { panelEl.innerHTML = '<p class="note">El panel anual se está consolidando.</p>'; return; }
    panelEl.innerHTML = P.indicadores.filter((x) => x.area === area).map(spark).filter(Boolean).join('') || '<p class="note">Sin series para esta área.</p>';
  }

  // ---------------------------------------------------------------- matriz (tabla)
  root.querySelector('[data-slot="periodos.table"]').innerHTML = `<table><thead><tr><th>Área (fuente)</th>${PERIODOS.map((p) => `<th class="n">${p.id}</th>`).join('')}</tr></thead><tbody>${AREAS.map((a) => `<tr><td>${a.nombre}<br><span class="note">${a.fuente}</span></td>${PERIODOS.map((p) => `<td class="n">${a.crudo?.[p.id] ?? (a.valores[p.id] == null ? '—' : fmtN(a.valores[p.id], 0))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;

  setMode(mode);
  select(n - 1);
  onTheme((t) => {
    floor.material.color.copy(t.surface); ghostMat.color.copy(t.muted);
    K.base.mat.color.copy(baseCol(t)); K.hecho.mat.color.copy(t.bad); K.estimado.mat.color.copy(t.warn); K.indicio.mat.color.copy(t.warn); K.quieta.mat.color.copy(t.data); K.contra.mat.color.copy(t.accent);
    K.contra.edges?.forEach((e) => e.material.color.copy(t.accent));
    AREAS.forEach((a, j) => { amats[j].color.copy(t.s[a.slot - 1]); dimMats[j].color.copy(t.s[a.slot - 1]); });
  });
  return st;
}
