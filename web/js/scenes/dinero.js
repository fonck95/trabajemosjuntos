// Escena 3D: matriz periodo × categoría de la contratación registrada en SECOP (2007–2026).
// Tablero con canto redondeado, ranuras por celda y columnas biseladas cuyo bisel no se deforma al crecer.
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, fmtN, gsap } from '../core.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { SECOP, TEXTOS } from '../data.js';

// Columna de altura 1 con bisel fijo: el sombreador reubica los vértices del bisel superior según la escala y
// del objeto (la altura real), así el canto mide lo mismo en una columna baja que en una alta
const BEV = 0.14;
function bevelKeep(m) {
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\nobjectNormal.y *= length(modelMatrix[1].xyz);')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nfloat hh = max(length(modelMatrix[1].xyz), 1e-4);\ntransformed.y = (position.y < 0.5 ? min(position.y, 0.5 * hh) : max(hh - (1.0 - position.y), 0.5 * hh)) / hh;');
  };
  m.customProgramCacheKey = () => 'columna-bisel';
  return m;
}

export function mount(root) {
  const el = root.querySelector('.stage');
  // declutter: las cifras sobre las columnas y las etiquetas de cada pila suben lo justo para no taparse
  const st = new Stage(el, { cam: [26, 24, 34], target: [0, 3, 0], maxDist: 90, dynamicShadows: true, env: false, declutter: ['lbl-val', 'lbl-money'] });
  const T = tokens();
  const S = st.scene;
  const P = SECOP.periodos, C = SECOP.categorias;
  const GX = 4.2, GZ = 3.2, H = 14;
  const x0 = -((P.length - 1) * GX) / 2, z0 = -((C.length - 1) * GZ) / 2;

  // tablero: losa de 60 cm con canto redondeado (cara superior en y = 0)
  const floor = new THREE.Mesh(new RoundedBoxGeometry(P.length * GX + 7, 0.6, C.length * GZ + 7, 3, 0.28), mat(T.surface, { roughness: 0.9 }));
  floor.position.y = -0.3; floor.receiveShadow = true; S.add(floor);
  // retícula entre celdas: franjas de 4 cm, 5 mm sobre el tablero y con polygonOffset (no titilan)
  const gx = (i) => x0 + (i - 0.5) * GX, gz = (j) => z0 + (j - 0.5) * GZ, lines = [];
  for (let i = 0; i <= P.length; i++) lines.push(new THREE.BoxGeometry(0.04, 0.005, gz(C.length) - gz(0) + 1).translate(gx(i), 0.0025, (gz(0) + gz(C.length)) / 2));
  for (let j = 0; j <= C.length; j++) lines.push(new THREE.BoxGeometry(gx(P.length) - gx(0) + 1, 0.005, 0.04).translate((gx(0) + gx(P.length)) / 2, 0.0025, gz(j)));
  const grid = new THREE.Mesh(mergeGeometries(lines), new THREE.MeshBasicMaterial({ color: T.line, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
  S.add(grid);
  // ranuras: una placa biselada bajo cada celda (matriz) o bajo cada pila (instanciadas)
  const slotMat = mat(T.surface.clone().lerp(T.ink, 0.07), { roughness: 0.75 });
  const slotGeo = new RoundedBoxGeometry(2.7, 0.06, 2.4, 2, 0.03).translate(0, 0.01, 0);
  const slots = new THREE.InstancedMesh(slotGeo, slotMat, P.length * C.length), slotsPila = new THREE.InstancedMesh(slotGeo, slotMat, P.length);
  P.forEach((p, i) => { C.forEach((c, j) => slots.setMatrixAt(i * C.length + j, new THREE.Matrix4().makeTranslation(x0 + i * GX, 0, z0 + j * GZ))); slotsPila.setMatrixAt(i, new THREE.Matrix4().makeTranslation(x0 + i * GX, 0, 0.4)); });
  slots.receiveShadow = slotsPila.receiveShadow = true; slotsPila.visible = false;
  S.add(slots, slotsPila);

  // rótulo de periodo completo y corto («08–11», el que se ve en el teléfono)
  const perLabels = P.map((p, i) => st.label(`<span class="per-l">${p.replace('-', '–')}</span><span class="per-c">${p.slice(2, 4)}–${p.slice(7, 9)}</span>`, 'lbl-axis', [x0 + i * GX, 0.2, z0 + C.length * GZ + 0.4]));
  // nombre de cada categoría al final de su fila, alineado a la izquierda: con la cámara desde el frente a la
  // derecha, las columnas de las filas de adelante quedan a la izquierda y no lo cruzan
  const catLabels = C.map((c, j) => {
    const l = st.label(c.corto, 'lbl-axis lbl-cat', [x0 + (P.length - 0.5) * GX, 0.2, z0 + j * GZ]);
    l.center.set(0, 0.5);
    return l;
  });

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
  const geo = new RoundedBoxGeometry(2.2, 1, 1.9, 2, BEV); geo.translate(0, 0.5, 0);
  const mats = C.map((c, j) => bevelKeep(mat(T.s[c.slot - 1], { roughness: 0.5, metalness: 0.05 })));
  P.forEach((p, i) => C.forEach((c, j) => {
    const m = new THREE.Mesh(geo, mats[j]);
    m.position.set(x0 + i * GX, 0, z0 + j * GZ);
    m.scale.set(1, 0.001, 1);
    m.castShadow = true; m.receiveShadow = true;
    S.add(m);
    const lab = st.label('', 'lbl-val', [0, 0, 0]);
    const b = { m, lab, p, c, i, j, h: 0, target: 0 };
    st.pickable(m, { onPick: () => pick(b), onEnter: () => { m.material = hi; lab.element.hidden = !b.v; }, onLeave: () => { m.material = mats[j]; lab.element.hidden = !b.show; } });
    bars.push(b);
  }));
  const hi = bevelKeep(mat(T.ink, { roughness: 0.5 }));

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
        // cada bloque muestra su categoría al pasar el cursor; el total del periodo va en la etiqueta de la pila
        b.lab.element.textContent = b.v ? `${b.c.corto}: ${fmtV(b.v)}` : '';
        b.show = false; b.lab.element.hidden = true;
      });
      ghosts.forEach((g, i) => {
        g.target = (ing[i] / max) * H; g.stack = (tot[i] / max) * H; g.z = conIngresos ? -1.1 : 0.4;
        const info = conIngresos && SECOP.ingresos[g.p], salvedad = info && info.nota.match(/\(([^)]+)\)/)?.[1];
        // una sola etiqueta por periodo con lo que entró y lo contratado: así las dos cifras no se tapan; la nota
        // solo aparece cuando hay una salvedad (por ejemplo, «solo 2024» en el periodo en curso)
        g.lab.element.innerHTML = `${info ? `<span>Entró ${fmtCOP(info.valor)}</span>` : ''}<span class="ct">${med === 'valor' ? `Contratado ${fmtCOP(tot[i])}` : `${fmtN(tot[i])} contratos`}</span>${salvedad ? `<span class="nt">${salvedad}</span>` : ''}`;
        g.on = tot[i] > 0 || ing[i] > 0;
      });
    }
    ghosts.forEach((g) => { const on = modo === 'pila' && g.on; g.g.visible = conIngresos; g.lab.visible = on; g.lab.element.hidden = !on; if (!conIngresos) g.target = 0; });
    catLabels.forEach((l) => { l.visible = modo === 'matriz'; l.element.hidden = modo !== 'matriz'; });
    // los periodos van al pie de cada pila o al frente de la matriz
    perLabels.forEach((l) => { l.position.z = modo === 'matriz' ? z0 + C.length * GZ + 0.4 : 2.6; });
    slots.visible = modo === 'matriz'; slotsPila.visible = modo !== 'matriz';
    // GSAP anima cada columna hacia su nuevo estado; sin GSAP se coloca de inmediato
    bars.forEach((b) => {
      if (!gsap) { b.h = b.target; b.y = b.ty; b.z = b.tz; place(b); return; }
      gsap.to(b, { h: b.target, y: b.ty, z: b.tz, duration: 0.9, ease: 'power3.out', delay: b.i * 0.05 + b.j * 0.025, overwrite: true, onUpdate: () => place(b) });
    });
    ghosts.forEach((g) => {
      if (!gsap) { g.h = g.target; placeG(g); return; }
      gsap.to(g, { h: g.target, duration: 1.1, ease: 'power2.out', delay: 0.2, overwrite: true, onUpdate: () => placeG(g) });
    });
    st.invalidate();
    tilesFor();
  }
  const place = (b) => {
    b.m.scale.y = Math.max(0.001, b.h); b.m.position.y = b.y; b.m.position.z = b.z;
    b.lab.position.set(b.m.position.x, b.y + b.h + 0.7, b.z);
    st.invalidate();
  };
  const placeG = (g) => { g.g.scale.y = Math.max(0.001, g.h); g.lab.position.set(g.g.position.x - 0.1, Math.max(g.h, g.stack || 0) + 1.2, g.z ?? 0.4); st.invalidate(); };

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
    modo = bt.dataset.modo; root.querySelectorAll('[data-modo]').forEach((x) => x.setAttribute('aria-pressed', x === bt)); layout(); encuadre(false);
  }));
  // Encuadre: la matriz conserva en escritorio la cámara de siempre; en el teléfono (escenario angosto y alto) la
  // cámara sube para que el tablero ocupe el alto disponible. La fila de pilas se ve más de frente y con aire
  // arriba y a los lados para las etiquetas
  function encuadre(primera) {
    const tel = el.clientWidth < 560;
    if (modo === 'matriz' && !tel) { if (!primera) st.flyTo(st.fitPos([26, 24, 34], [0, 3, 0]), [0, 3, 0], 1.2); return; }
    st.resize();
    // la matriz casi de frente y desde arriba; la fila de pilas con margen a los lados para las etiquetas
    if (modo === 'matriz') st.frameBox(new THREE.Box3(new THREE.Vector3(x0 - 2.1, 0, z0 - 1.4), new THREE.Vector3(-x0 + 2.1, H * 0.85, -z0 + 2.9)), new THREE.Vector3(0.25, 0.75, 1), { margin: 0.95, duration: 1.2, ty: 0.3 });
    else if (tel) st.frameBox(new THREE.Box3(new THREE.Vector3(x0 - 4, 0, -3.6), new THREE.Vector3(-x0 + 4, H + 2, 3)), new THREE.Vector3(0.3, 0.45, 1), { margin: 0.94, duration: 1.2, ty: 0.4 });
    else st.frameBox(new THREE.Box3(new THREE.Vector3(x0 - 2.5, 0, -3.6), new THREE.Vector3(-x0 + 2.5, H + 4, 3)), new THREE.Vector3(0.35, 0.45, 1), { margin: 0.85, duration: 1.2, ty: 0.42 });
  }

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

  bars.forEach((b) => { b.h = 0.001; b.y = 0; b.z = z0 + b.j * GZ; place(b); });
  layout(); encuadre(true);
  st.freeze(floor); st.freeze(grid); st.freeze(slots); st.freeze(slotsPila);
  onTheme((t) => {
    floor.material.color.copy(t.surface);
    grid.material.color.copy(t.line); slotMat.color.copy(t.surface).lerp(t.ink, 0.07);
    mats.forEach((m, j) => m.color.copy(t.s[C[j].slot - 1]));
    hi.color.copy(t.ink); ghostMat.color.copy(t.ink); ghostFill.color.copy(t.sun);
  });
  return st;
}
