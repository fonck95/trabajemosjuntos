// Escena 3D: matriz periodo × categoría de la contratación registrada en SECOP (2007–2026).
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, fmtN, reducedMotion } from '../core.js';
import { SECOP, TEXTOS } from '../data.js';

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [26, 24, 34], target: [0, 3, 0], maxDist: 90 });
  const T = tokens();
  const S = st.scene;
  const P = SECOP.periodos, C = SECOP.categorias;
  const GX = 4.2, GZ = 3.2, H = 14;
  const x0 = -((P.length - 1) * GX) / 2, z0 = -((C.length - 1) * GZ) / 2;

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(P.length * GX + 8, C.length * GZ + 8), mat(T.surface));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; S.add(floor);
  const grid = new THREE.GridHelper(Math.max(P.length * GX, C.length * GZ) + 8, 24, T.line, T.line);
  grid.position.y = 0.01; S.add(grid);

  P.forEach((p, i) => st.label(p.replace('-', '–'), 'lbl-axis', [x0 + i * GX, 0.2, z0 + C.length * GZ + 0.4]));
  const catLabels = C.map((c, j) => st.label(c.corto, 'lbl-axis', [x0 - 4.6, 0.2, z0 + j * GZ]));

  // Columnas fantasma: ingresos en caja del municipio en cada periodo (OEC, DNP)
  const ghostMat = new THREE.LineBasicMaterial({ color: T.ink, transparent: true, opacity: 0.7 });
  const ghostFill = new THREE.MeshBasicMaterial({ color: T.sun, transparent: true, opacity: 0.12, depthWrite: false });
  const unit = new THREE.BoxGeometry(1, 1, 1); unit.translate(0, 0.5, 0);
  const ghosts = P.map((p, i) => {
    const g = new THREE.Group();
    g.add(new THREE.LineSegments(new THREE.EdgesGeometry(unit), ghostMat));
    g.add(new THREE.Mesh(unit, ghostFill));
    g.position.set(x0 + i * GX + 0.2, 0, -2.6); g.scale.set(2.6, 0.001, 1.9); g.visible = false; S.add(g);
    const lab = st.label('', 'lbl-money', [0, 0, 0]); lab.visible = false;
    return { g, lab, p, h: 0, target: 0 };
  });

  const bars = [];
  const geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0.5, 0);
  const mats = C.map((c, j) => mat(T.s[c.slot - 1], { roughness: 0.6 }));
  P.forEach((p, i) => C.forEach((c, j) => {
    const m = new THREE.Mesh(geo, mats[j]);
    m.position.set(x0 + i * GX, 0, z0 + j * GZ);
    m.scale.set(2.2, 0.001, 1.9);
    m.castShadow = true; m.receiveShadow = true;
    S.add(m);
    const lab = st.label('', 'lbl-val', [0, 0, 0]);
    const b = { m, lab, p, c, i, j, h: 0, target: 0 };
    st.pickable(m, { onPick: () => pick(b), onEnter: () => { m.material = hi; lab.element.hidden = !b.v; }, onLeave: () => { m.material = mats[j]; lab.element.hidden = !b.show; } });
    bars.push(b);
  }));
  const hi = mat(T.ink);

  let ent = 'ALCALDIA', med = 'valor', modo = 'matriz';
  const cell = (e, p, c) => SECOP.por_periodo[e]?.[p]?.[c.key] || { n: 0, valor: 0 };

  function layout() {
    const vals = bars.map((b) => cell(ent, b.p, b.c)[med]);
    const fmtV = (v) => (med === 'valor' ? fmtCOP(v) : fmtN(v));
    const conIngresos = modo === 'pila' && ent === 'ALCALDIA' && med === 'valor';
    if (modo === 'matriz') {
      const max = Math.max(...vals, 1);
      // solo se rotula la categoría mayor de cada periodo; el resto aparece al pasar el cursor
      const top = P.map((p, i) => Math.max(...bars.filter((b) => b.i === i).map((b) => vals[bars.indexOf(b)])));
      bars.forEach((b, k) => {
        b.target = (vals[k] / max) * H; b.ty = 0; b.tz = z0 + b.j * GZ;
        b.v = vals[k];
        b.lab.element.textContent = b.v ? fmtV(b.v) : '';
        b.show = b.v > 0 && b.v === top[b.i];
        b.lab.element.hidden = !b.show;
      });
    } else {
      // pila: lo contratado en cada periodo, apilado por categoría, frente a lo que entró a la caja
      const tot = P.map((p, i) => bars.filter((b) => b.i === i).reduce((a, b) => a + vals[bars.indexOf(b)], 0));
      const ing = P.map((p) => (conIngresos ? SECOP.ingresos[p]?.valor || 0 : 0));
      const max = Math.max(...tot, ...ing, 1);
      const cum = P.map(() => 0);
      bars.forEach((b, k) => {
        b.v = vals[k]; b.target = (b.v / max) * H; b.ty = (cum[b.i] / max) * H; b.tz = 0.4; cum[b.i] += b.v;
        b.lab.element.textContent = `Contratado ${fmtV(tot[b.i])}`;
        b.show = b.j === C.length - 1 && tot[b.i] > 0; b.lab.element.hidden = !b.show;
      });
      ghosts.forEach((g, i) => {
        g.target = (ing[i] / max) * H;
        const info = SECOP.ingresos[g.p];
        g.lab.element.innerHTML = info ? `${fmtCOP(info.valor)}<small>${info.nota}</small>` : '';
      });
    }
    ghosts.forEach((g) => { g.g.visible = conIngresos; g.lab.visible = conIngresos; g.lab.element.hidden = !conIngresos; if (!conIngresos) g.target = 0; });
    catLabels.forEach((l) => { l.visible = modo === 'matriz'; l.element.hidden = modo !== 'matriz'; });
    if (reducedMotion) { bars.forEach((b) => { b.h = b.target; b.y = b.ty; b.z = b.tz; place(b); }); ghosts.forEach((g) => { g.h = g.target; placeG(g); }); }
    tilesFor();
  }
  const place = (b) => {
    b.m.scale.y = Math.max(0.001, b.h); b.m.position.y = b.y; b.m.position.z = b.z;
    b.lab.position.set(b.m.position.x, b.y + b.h + 0.7, b.z);
  };
  const placeG = (g) => { g.g.scale.y = Math.max(0.001, g.h); g.lab.position.set(g.g.position.x, g.h + 1.2, g.g.position.z); };

  const pickEl = root.querySelector('[data-slot="dinero.pick"]');
  function pick(b) {
    const v = cell(ent, b.p, b.c);
    const tot = C.reduce((a, c) => a + cell(ent, b.p, c).valor, 0);
    const tops = SECOP.top_celdas.filter((t) => t.ent === ent && t.periodo === b.p && t.categoria === b.c.key);
    pickEl.innerHTML = `<h4>${b.c.label} · ${b.p.replace('-', '–')}</h4>
      <dl class="kv"><dt>Contratos</dt><dd>${fmtN(v.n)}</dd><dt>Valor</dt><dd>${fmtCOP(v.valor)}</dd><dt>Peso en el periodo</dt><dd>${tot ? fmtN((100 * v.valor) / tot, 1) : 0} %</dd></dl>
      ${tops.length ? `<p class="note" style="margin-top:8px">Contratos de mayor valor:</p><ul class="tight note">${tops.map((t) => `<li>${t.anio} · <b>${fmtCOP(t.valor)}</b> · ${t.contratista} — ${t.objeto.toLowerCase().slice(0, 150)}…</li>`).join('')}</ul>` : ''}`;
  }

  // controles
  root.querySelectorAll('[data-ent]').forEach((bt) => bt.addEventListener('click', () => {
    ent = bt.dataset.ent; root.querySelectorAll('[data-ent]').forEach((x) => x.setAttribute('aria-pressed', x === bt)); layout();
  }));
  root.querySelectorAll('[data-med]').forEach((bt) => bt.addEventListener('click', () => {
    med = bt.dataset.med; root.querySelectorAll('[data-med]').forEach((x) => x.setAttribute('aria-pressed', x === bt)); layout();
  }));
  root.querySelectorAll('[data-modo]').forEach((bt) => bt.addEventListener('click', () => {
    modo = bt.dataset.modo; root.querySelectorAll('[data-modo]').forEach((x) => x.setAttribute('aria-pressed', x === bt)); layout();
  }));

  // leyenda, tabla y fichas
  root.querySelector('[data-slot="dinero.legend"]').innerHTML = C.map((c) => `<span><i style="background:var(--s${c.slot})"></i>${c.label}</span>`).join('');
  const tbl = (e) => {
    const rows = C.map((c) => `<tr><td>${c.label}</td>${P.map((p) => `<td class="n">${fmtN(cell(e, p, c).valor / 1e6)}</td>`).join('')}</tr>`).join('');
    const tot = P.map((p) => C.reduce((a, c) => a + cell(e, p, c).valor, 0));
    return `<table><thead><tr><th>Alcaldía · categoría</th>${P.map((p) => `<th class="n">${p}</th>`).join('')}</tr></thead><tbody>${rows}</tbody>
      <tfoot><tr><td>Total</td>${tot.map((v) => `<td class="n">${fmtN(v / 1e6)}</td>`).join('')}</tr>
      <tr><td>% del valor por contratación directa</td>${P.map((p) => { const d = SECOP.directa.find((x) => x.periodo === p); return `<td class="n">${d ? fmtN(d.pct_valor_directa, 1) + ' %' : '—'}</td>`; }).join('')}</tr></tfoot></table>`;
  };
  root.querySelector('[data-slot="dinero.table"]').innerHTML = tbl('ALCALDIA');
  const tilesEl = root.querySelector('[data-slot="dinero.tiles"]');
  function tilesFor() {
    const k = SECOP.kpis[ent];
    tilesEl.innerHTML = k.map((t) => `<div class="tile"><b>${t.v}</b><span>${t.l}</span></div>`).join('');
  }
  root.querySelector('[data-slot="dinero.findings"]').innerHTML = SECOP.hallazgos.map((h) => `<div class="card"><p class="eyebrow">${h.tag}</p><h3>${h.titulo}</h3><p>${h.texto}</p>${h.fuente ? `<p class="note">${h.fuente}</p>` : ''}</div>`).join('');

  layout();
  bars.forEach((b) => { b.y = b.ty; b.z = b.tz; if (!reducedMotion) { b.h = b.target * 0.15; } place(b); });
  const ease = (a, b, k) => a + (b - a) * k;
  st.onFrame((dt) => {
    const k = Math.min(1, dt * 5);
    bars.forEach((b) => {
      if (Math.abs(b.h - b.target) + Math.abs(b.y - b.ty) + Math.abs(b.z - b.tz) > 0.01) { b.h = ease(b.h, b.target, k); b.y = ease(b.y, b.ty, k); b.z = ease(b.z, b.tz, k); place(b); }
    });
    ghosts.forEach((g) => { if (Math.abs(g.h - g.target) > 0.01) { g.h = ease(g.h, g.target, k); placeG(g); } });
  });
  onTheme((t) => {
    floor.material.color.copy(t.surface);
    grid.material.color = t.line;
    mats.forEach((m, j) => m.color.copy(t.s[C[j].slot - 1]));
    hi.color.copy(t.ink); ghostMat.color.copy(t.ink); ghostFill.color.copy(t.sun);
  });
  return st;
}
