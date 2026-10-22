// Escena 3D: la hoja de ruta 2026–2031 como un camino con compuertas. Cada compuerta es una
// condición verificable; si no se cumple, el siguiente contrato no se firma.
// Maqueta sobre un plinto: vía con berma y bordes del color de cada fase, talanqueras que se levantan al paso
// del caminante, regla de años y arboleda. Las piezas repetidas van instanciadas (pocas llamadas de dibujo).
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, reducedMotion } from '../core.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { RUTA } from '../data.js';

// quita las referencias a archivos internos del proyecto ("Ver docs/05.", "(docs/11)") que el ciudadano no puede abrir
const limpia = (s) => String(s ?? '').replace(/\s*\(?\bVer (?:docs\/\d+(?:,\s*|\s+y\s+)?)+\)?\.?/g, '').replace(/\s*\((?:docs\/\d+|[\w./-]+\.json)[^()]*\)/g, '');
// proyectos del portafolio que tienen su propia página en el atlas
const VISTA = [[/torre/i, 'torre'], [/parque/i, 'parque'], [/red de distribución/i, 'ciudad'], [/microrred/i, 'microrred']];
// los montos y rangos de plata del texto ("$2.075–4.447 M") no se parten entre renglones
const plata = (s) => s.replace(/\$[\d.,]+(?:\s*[–-]\s*[\d.,]+)?\s(?:mil\s)?M\b/g, '<span class="nw">$&</span>');

// cinta plana a lo largo de la curva entre los desplazamientos laterales a < b (cara hacia arriba)
function ribbon(curve, a, b, y, n, t0 = 0, t1 = 1, colorAt) {
  const pos = [], col = [], idx = [];
  for (let i = 0; i <= n; i++) {
    const t = t0 + ((t1 - t0) * i) / n, p = curve.getPointAt(t), tg = curve.getTangentAt(t), L = Math.hypot(tg.x, tg.z), nx = -tg.z / L, nz = tg.x / L;
    pos.push(p.x + nx * a, y, p.z + nz * a, p.x + nx * b, y, p.z + nz * b);
    if (colorAt) { const c = colorAt(t); col.push(c.r, c.g, c.b, c.r, c.g, c.b); }
    if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  if (colorAt) g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx); g.computeVertexNormals();
  return g;
}
// geometría con un color por vértice (para fusionar piezas de varios colores en una sola malla)
const tinted = (g, c) => { g = g.index ? g.toNonIndexed() : g; g.deleteAttribute('uv'); const n = g.attributes.position.count, a = new Float32Array(n * 3); for (let i = 0; i < n; i++) a.set([c.r, c.g, c.b], i * 3); g.setAttribute('color', new THREE.BufferAttribute(a, 3)); return g; };

export function mount(root) {
  const el = root.querySelector('.stage');
  // declutter: si dos rótulos de una franja se tocan, el de atrás sube lo justo
  const st = new Stage(el, { cam: [0, 64, 92], target: [0, 0, 0], maxDist: 170, env: false, declutter: true });
  // la sombra cubre todo el plinto (antes el borde del volumen de sombra se veía sobre un piso de 700 m)
  Object.assign(st.sunLight.shadow.camera, { left: -70, right: 70, top: 50, bottom: -50, far: 200 });
  st.sunLight.shadow.camera.updateProjectionMatrix();
  st.sunLight.shadow.normalBias = 0.04;
  const T = tokens();
  const S = st.scene;
  const capa = (m, k) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const asphalt = (t) => t.ground.clone().lerp(new THREE.Color(0x3c3f43), 0.85);

  // plinto de la maqueta con canto redondeado y lomas bajas en el fondo
  const ground = new THREE.Mesh(new RoundedBoxGeometry(128, 1.2, 68, 3, 0.5), mat(T.ground, { roughness: 1 }));
  ground.position.set(0, -0.6, 1); ground.receiveShadow = true; S.add(ground);
  const hill = (t) => t.ground.clone().lerp(new THREE.Color(0x8fae7f), 0.3);
  const hillMat = mat(hill(T), { roughness: 1 });
  const hills = new THREE.Mesh(mergeGeometries([[-46, -28, 11, 2.2, 6], [-18, -30, 14, 1.6, 5], [16, -29, 12, 2.6, 6], [44, -27, 12, 1.8, 7], [-55, 26, 7, 1.2, 6], [54, 28, 8, 1.5, 6]].map(([x, z, sx, sy, sz]) => new THREE.SphereGeometry(1, 24, 10, 0, Math.PI * 2, 0, Math.PI / 2).scale(sx, sy, sz).translate(x, -0.02, z))), hillMat);
  hills.receiveShadow = true; hills.castShadow = true; S.add(hills);

  const H = RUTA.hitos;
  const pts = H.map((h, i) => new THREE.Vector3(-44 + (88 * i) / (H.length - 1), 0.05, Math.sin(i * 0.9) * 12));
  const curve = new THREE.CatmullRomCurve3(pts);
  const fases = RUTA.fases;
  const fi = H.map((h) => fases.findIndex((f) => f.id === h.fase));
  // tramo de vía: berma de grava, calzada y bordes del color de la fase que viene (cada tramo lleva a su compuerta)
  const segFase = (t) => fi[Math.min(H.length - 1, Math.ceil(t * (H.length - 1) - 1e-6))];
  const bermMat = mat(T.ground.clone().lerp(T.roof, 0.45), { roughness: 1 });
  const berm = new THREE.Mesh(ribbon(curve, -2.6, 2.6, 0.02, 360), bermMat); berm.receiveShadow = true;
  const roadMat = mat(asphalt(T), { roughness: 0.92 });
  const road = new THREE.Mesh(ribbon(curve, -1.7, 1.7, 0.05, 360), roadMat); road.receiveShadow = true;
  const edgeMat = capa(new THREE.MeshBasicMaterial({ vertexColors: true }), 2);
  const edgeCol = (t) => T.s[fases[segFase(t)].slot - 1];
  const edgeGeo = () => mergeGeometries([ribbon(curve, -1.6, -1.42, 0.056, 360, 0, 1, edgeCol), ribbon(curve, 1.42, 1.6, 0.056, 360, 0, 1, edgeCol)]);
  const edges = new THREE.Mesh(edgeGeo(), edgeMat);
  const dashes = [];
  for (let t = 0.004; t < 0.995; t += 0.012) dashes.push(ribbon(curve, -0.06, 0.06, 0.056, 2, t, t + 0.006));
  const markMat = capa(new THREE.MeshBasicMaterial({ color: T.wall.clone().lerp(new THREE.Color(0xffffff), 0.5) }), 2);
  const center = new THREE.Mesh(mergeGeometries(dashes), markMat);
  S.add(berm, road, edges, center);

  // compuertas: postes, dintel, placas, gabinete y talanquera a franjas; todo instanciado
  const pickEl = root.querySelector('[data-slot="ruta.pick"]');
  const gateM = H.map((h, i) => {
    const tg = curve.getTangent(i / (H.length - 1));
    return new THREE.Matrix4().compose(pts[i].clone().setY(0.05), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -Math.atan2(tg.z, tg.x)), new THREE.Vector3(1, 1, 1));
  });
  const phaseMat = mat(0xffffff, { roughness: 0.45 });
  const inst = (geo, m, n, f, color) => {
    const o = new THREE.InstancedMesh(geo, m, n);
    for (let k = 0; k < n; k++) { o.setMatrixAt(k, f(k)); if (color) o.setColorAt(k, color(k)); }
    o.castShadow = o.receiveShadow = true; S.add(o); return o;
  };
  const local = (i, x, y, z) => gateM[i].clone().multiply(new THREE.Matrix4().makeTranslation(x, y, z));
  const posts = inst(new RoundedBoxGeometry(0.45, 4.2, 0.45, 2, 0.08).translate(0, 2.1, 0), phaseMat, H.length * 2, (k) => local(k >> 1, 0, 0, k & 1 ? 2.2 : -2.2), (k) => T.s[fases[fi[k >> 1]].slot - 1]);
  const lintels = inst(new RoundedBoxGeometry(0.7, 0.6, 5.1, 2, 0.1).translate(0, 0.3, 0), phaseMat, H.length, (k) => local(k, 0, 4.2, 0), (k) => T.s[fases[fi[k]].slot - 1]);
  const plateMat = mat(0xf4f4ef, { roughness: 0.6 });
  const plates = inst(new THREE.BoxGeometry(0.06, 0.4, 3.4), plateMat, H.length * 2, (k) => local(k >> 1, k & 1 ? 0.37 : -0.37, 4.5, 0));
  const housingMat = mat(0x3a3f45, { roughness: 0.5, metalness: 0.3 });
  const housings = inst(new RoundedBoxGeometry(0.55, 1.25, 0.45, 1, 0.06).translate(0, 0.625, 0), housingMat, H.length, (k) => local(k, 0.55, 0, -1.75));
  const red = new THREE.Color(0xd0342c), white = new THREE.Color(0xf4f4ef); // franjas de señalización vial
  const boomGeo = mergeGeometries(Array.from({ length: 8 }, (_, s) => tinted(new THREE.BoxGeometry(0.11, 0.11, 0.47).translate(0, 0, 0.24 + s * 0.47), s % 2 ? white : red)));
  const boomMat = mat(0xffffff, { vertexColors: true, roughness: 0.5 });
  const lift = H.map(() => 0);
  const boomAt = (i, a) => local(i, 0.55, 1.1, -1.7).multiply(new THREE.Matrix4().makeRotationX(-a * 1.35));
  const booms = inst(boomGeo, boomMat, H.length, (k) => boomAt(k, 0));
  // rótulos en dos franjas, como una línea de tiempo: los pares al fondo y los impares al frente, cada uno en un
  // poste unido a su compuerta por una guía en el piso del color de la fase (así no se enciman)
  const BAND = [-15.5, 15], sign = (i) => new THREE.Vector3(pts[i].x, 0, BAND[i % 2]);
  const masts = inst(new THREE.CylinderGeometry(0.05, 0.06, 1.3, 6).translate(0, 0.65, 0), housingMat, H.length, (k) => new THREE.Matrix4().makeTranslation(sign(k).x, 0, sign(k).z));
  const guideMat = capa(new THREE.MeshBasicMaterial({ vertexColors: true }), 1);
  const guideGeo = () => mergeGeometries(H.map((h, i) => { const z0 = pts[i].z + (i % 2 ? 2.8 : -2.8), z1 = sign(i).z; return tinted(new THREE.BoxGeometry(0.09, 0.006, Math.abs(z1 - z0)).translate(pts[i].x, 0.003, (z0 + z1) / 2), T.s[fases[fi[i]].slot - 1]); }));
  const guides = new THREE.Mesh(guideGeo(), guideMat); S.add(guides);
  // un volumen invisible por compuerta para tocarla (el rayo no mira la visibilidad)
  const proxyGeo = new THREE.BoxGeometry(1.2, 5, 5.4).translate(0, 2.5, 0), proxyMat = new THREE.MeshBasicMaterial();
  H.forEach((h, i) => {
    const px = new THREE.Mesh(proxyGeo, proxyMat); px.visible = false;
    gateM[i].decompose(px.position, px.quaternion, px.scale); S.add(px);
    st.pickable(px, { onPick: () => pick(h) });
    const lab = st.label(`<b>${h.fecha}</b><span data-t><br>${h.titulo}</span>`, 'lbl-node', [sign(i).x, 1.95, sign(i).z]);
    Object.assign(lab.element.style, { whiteSpace: 'normal', maxWidth: '104px' }); // el título largo se parte en renglones (la franja de atrás se ve más angosta)
  });

  // en pantallas angostas los rótulos muestran solo la fecha (el título queda en la ficha al tocar)
  new ResizeObserver(() => { const c = el.clientWidth < 560; st.labels.domElement.querySelectorAll('[data-t]').forEach((x) => { x.hidden = c; }); }).observe(el);
  // en el teléfono la cámara sube y encuadra solo la vía con sus rótulos (no el plinto entero), sin cortar los extremos
  if (el.clientWidth < 560) st.frameBox(new THREE.Box3(new THREE.Vector3(-46, 0, BAND[0]), new THREE.Vector3(46, 4.5, 22.5)), new THREE.Vector3(0, 1.9, 1), { margin: 0.82, ty: 0 });

  // regla de años junto a la vía con mojones en cada año
  const rulerMat = mat(T.ground.clone().lerp(T.ink, 0.35), { roughness: 0.8 });
  const ruler = new THREE.Mesh(new RoundedBoxGeometry(90, 0.08, 0.22, 2, 0.03).translate(0, 0.04, 20.8), rulerMat); ruler.receiveShadow = true; S.add(ruler);
  const markers = inst(new RoundedBoxGeometry(0.42, 0.85, 0.32, 1, 0.06).translate(0, 0.425, 0), rulerMat, RUTA.anios.length, (k) => new THREE.Matrix4().makeTranslation(-44 + 88 * RUTA.anios[k].t, 0, 20.8));
  RUTA.anios.forEach((a) => st.label(a.label, 'lbl-geo', [-44 + 88 * a.t, 0.2, 22.2]));

  // arboleda: copas de varios lóbulos fuera de la vía y de la regla (una sola malla instanciada)
  const treeGeo = mergeGeometries([
    tinted(new THREE.CylinderGeometry(0.14, 0.2, 1.8, 6).translate(0, 0.9, 0), new THREE.Color(0x6b4f3a)),
    ...[[0, 2.5, 0, 1.15], [0.65, 2.15, 0.3, 0.82], [-0.6, 2.2, -0.35, 0.86], [0.1, 3.05, -0.1, 0.7]].map(([x, y, z, r]) => tinted(new THREE.IcosahedronGeometry(r, 1).translate(x, y, z), new THREE.Color(0x3f7d4e))),
  ]);
  const roadPts = curve.getSpacedPoints(160);
  let seed = 5;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const trees = [];
  while (trees.length < 70) {
    const x = -60 + rnd() * 120, z = -32 + rnd() * 66;
    if (Math.abs(z - 21.4) < 2.8 || BAND.some((b) => Math.abs(z - b) < 2.6) || pts.some((p) => Math.abs(p.x - x) < 1.6) || roadPts.some((p) => Math.hypot(p.x - x, p.z - z) < 5.2)) continue;
    trees.push([x, z, 0.75 + rnd() * 0.6]);
  }
  const treeMat = mat(0xffffff, { vertexColors: true, roughness: 0.9 });
  const forest = inst(treeGeo, treeMat, trees.length, (k) => new THREE.Matrix4().compose(new THREE.Vector3(trees[k][0], 0, trees[k][1]), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * 6.3), new THREE.Vector3(trees[k][2], trees[k][2], trees[k][2])), () => new THREE.Color().setRGB(0.85 + rnd() * 0.25, 0.88 + rnd() * 0.2, 0.82 + rnd() * 0.2));

  // caminante: esfera luminosa con halo y sombra de contacto sobre la calzada
  const walker = new THREE.Mesh(new THREE.SphereGeometry(0.7, 24, 16), mat(T.sun, { emissive: T.sun, emissiveIntensity: 0.6 }));
  const haloMat = capa(new THREE.MeshBasicMaterial({ color: T.sun, transparent: true, opacity: 0.45, depthWrite: false }), 3);
  const halo = new THREE.Mesh(new THREE.RingGeometry(0.95, 1.25, 40).rotateX(-Math.PI / 2), haloMat);
  const contact = new THREE.Mesh(new THREE.CircleGeometry(0.75, 28).rotateX(-Math.PI / 2), capa(new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.22, depthWrite: false }), 3));
  S.add(walker, halo, contact);
  let u = 0;
  const gx = pts.map((p) => p.x), gz = pts.map((p) => p.z);
  st.onFrame((dt) => {
    u = (u + dt * (reducedMotion ? 0.01 : 0.025)) % 1;
    const p = curve.getPointAt(u); walker.position.set(p.x, 1, p.z);
    halo.position.set(p.x, 0.062, p.z); contact.position.set(p.x, 0.06, p.z);
    // la talanquera sube cuando el caminante se acerca y baja cuando ya pasó
    let moved = false;
    for (let i = 0; i < H.length; i++) {
      const near = Math.hypot(gx[i] - p.x, gz[i] - p.z) < 7 ? 1 : 0, a = lift[i] + Math.sign(near - lift[i]) * Math.min(Math.abs(near - lift[i]), dt * 1.6);
      if (a !== lift[i]) { lift[i] = a; booms.setMatrixAt(i, boomAt(i, a * a * (3 - 2 * a))); moved = true; }
    }
    if (moved) booms.instanceMatrix.needsUpdate = true;
  });
  [ground, hills, berm, road, edges, center, posts, lintels, plates, housings, masts, guides, ruler, markers, forest].forEach((o) => st.freeze(o));

  function pick(h) {
    pickEl.innerHTML = `<p class="eyebrow">${fases.find((f) => f.id === h.fase).nombre}</p><h4>${h.fecha} · ${h.titulo}</h4><p>${limpia(h.detalle)}</p><p><b>Compuerta:</b> ${limpia(h.compuerta)}</p>${h.responsable ? `<p class="note">Responsable: ${h.responsable}</p>` : ''}`;
  }
  pick(H[0]);
  root.querySelector('[data-slot="ruta.gates"]').innerHTML = H.map((h) => `<div class="gate"><time>${h.fecha}</time><div><b>${h.titulo}</b>${limpia(h.detalle)}<br><span class="note">Compuerta: ${limpia(h.compuerta)}</span></div></div>`).join('');
  root.querySelector('[data-slot="ruta.reglas"]').innerHTML = `<ol class="tight">${RUTA.reglas.map((r) => `<li>${limpia(r)}</li>`).join('')}</ol>`;
  const P = RUTA.portafolio;
  // el nombre lleva a la página del proyecto si la tiene; el refuerzo del hospital, si aparece, remite a la torre que lo reemplazó
  const nombre = (p) => { const v = VISTA.find(([re]) => re.test(p.nombre)); return v ? `<a href="#${v[1]}">${p.nombre}</a>` : p.nombre; };
  const torre = (p) => (/hospital/i.test(p.nombre) && !/torre/i.test(p.nombre) && /reforz/i.test(p.alcance) ? ' <b>Decisión actual:</b> en lugar de reforzar el edificio se construye la <a href="#torre">torre de servicios de primer nivel</a>; el edificio actual pasa a administración, archivo, bodega y central de distribución.' : '');
  // "Cuándo" y no "Fase": la columna trae años y no las fases 0 a 3 de la hoja de ruta; el rango de años no se parte
  root.querySelector('[data-slot="ruta.portafolio"]').innerHTML = `<table><thead><tr><th>Proyecto</th><th>Ejecutor / vía</th><th>Fuentes</th><th>Cuándo</th><th class="n">Inversión</th></tr></thead><tbody>${P.map((p) => `<tr><td><b>${nombre(p)}</b><br><span class="note">${plata(limpia(p.alcance))}${torre(p)}</span></td><td>${p.ejecutor}</td><td>${p.fuentes}</td><td>${String(p.fase).replace(/\d{4}\s*[–-]\s*\d{4}/g, '<span class="nw">$&</span>')}</td><td class="n">${fmtCOP(p.valor * 1e6)}</td></tr>`).join('')}</tbody><tfoot><tr><td colspan="4">Total portafolio</td><td class="n">${fmtCOP(P.reduce((a, p) => a + p.valor, 0) * 1e6)}</td></tr></tfoot></table>`;

  onTheme((t) => {
    Object.assign(T, t);
    ground.material.color.copy(t.ground); hillMat.color.copy(hill(t)); bermMat.color.copy(t.ground).lerp(t.roof, 0.45);
    roadMat.color.copy(asphalt(t)); markMat.color.copy(t.wall).lerp(white, 0.5); rulerMat.color.copy(t.ground).lerp(t.ink, 0.35);
    // colores de fase: postes, dinteles y bordes de la vía
    for (let k = 0; k < H.length * 2; k++) posts.setColorAt(k, t.s[fases[fi[k >> 1]].slot - 1]);
    H.forEach((h, k) => lintels.setColorAt(k, t.s[fases[fi[k]].slot - 1]));
    posts.instanceColor.needsUpdate = lintels.instanceColor.needsUpdate = true;
    edges.geometry.dispose(); edges.geometry = edgeGeo(); guides.geometry.dispose(); guides.geometry = guideGeo();
    walker.material.color.copy(t.sun); walker.material.emissive.copy(t.sun); haloMat.color.copy(t.sun);
  });
  return st;
}
