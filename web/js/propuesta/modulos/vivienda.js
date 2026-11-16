// Vivienda: la vivienda nueva urbana en los dos lotes reales del levantamiento, y los mejoramientos sobre casas reales.
//  · Lote 1, predio José Domingo Oliveros (1,71 ha, terraplén ya construido): 200 VIP en 10 bloques de 5 pisos con sus
//    vías internas y manzanas verdes.
//  · Lote 2, lote occidental (2,54 ha): casas en serie de 2 pisos en lotes de 6 × 12 m (100 en la primera etapa, de 138
//    posibles) y dos manzanas de cesión con parque y salón comunal.
//  · Mejoramientos: techos resaltados sobre casas pequeñas de la periferia del casco, a partir de las huellas reales.
// Diseño de la maqueta: bloques de 22 × 10 m con punto fijo al frente (escalera con fachada de bloque calado y tanques
// encima), culatas y zócalo de ladrillo a la vista, balcones con antepecho de color, ventanas con marco y entrepisos
// marcados; casas en serie con cubierta de teja continua, antejardín y balcón (geo3d.casas); vías con andenes, arborización y
// alumbrado; cesiones con cancha múltiple, juegos y salón comunal; casa rural con corredor de madera, tanque elevado y panel
// solar. Las ventanas se encienden al atardecer (tema oscuro).
import { THREE, gsap, mat } from '../../core.js';
import { casas, losa, cinta, arboles, palmas, jardin, bancas, gente, carros, postes, aLoLargo, brotar, dentro, area, azar, unir, distLinea, membrana } from '../geo3d.js';
import { matT } from '../texturas.js';
import { sitio, sitios, trazado, trazados, caja } from './comun.js';

const LOTE1 = [[-603, -256], [-561, -256], [-531, -273], [-499, -297], [-496, -339], [-502, -380], [-537, -395], [-585, -398], [-632, -383], [-659, -365], [-653, -339], [-620, -297], [-608, -273]];
const LOTE2 = [[-1198, 2], [-1120, 4], [-1062, 8], [-1032, 20], [-1028, 80], [-1036, 150], [-1110, 158], [-1170, 160], [-1200, 140], [-1204, 60]];
const cen = (p) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length];
const V3 = (x, y, h = 0) => new THREE.Vector3(x, h, -y);

// lotes de 6 × 12 m en dos filas espalda con espalda a lo largo del lado mayor de una manzana (cada fila da a su calle)
function lotesManzana(poly, max = 99, frente = 6, fondo = 12) {
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]), [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const horizontal = x1 - x0 >= y1 - y0, out = [];
  const L0 = horizontal ? x0 : y0, L1 = horizontal ? x1 : y1, A0 = horizontal ? y0 : x0, A1 = horizontal ? y1 : x1;
  [[A0 + fondo / 2, 0], [A1 - fondo / 2, 1]].forEach(([a, fila]) => {
    for (let l = L0 + frente / 2; l + frente / 2 <= L1 + 0.01; l += frente) {
      const [x, y] = horizontal ? [l, a] : [a, l];
      const esq = horizontal ? [[x - 2.6, y - 5.4], [x + 2.6, y - 5.4], [x + 2.6, y + 5.4], [x - 2.6, y + 5.4]] : [[x - 5.4, y - 2.6], [x + 5.4, y - 2.6], [x + 5.4, y + 2.6], [x - 5.4, y + 2.6]];
      if (esq.every((p) => dentro(p, poly))) out.push({ x, y, rot: (horizontal ? 0 : Math.PI / 2) + (fila ? Math.PI : 0), pisos: 2 });
    }
  });
  return out.slice(0, max);
}

// ---------------------------------------------------------------- bloque multifamiliar VIP (plantilla instanciada)
// Coordenadas locales: x a lo largo (22 m), +z hacia la vía (fachada con el punto fijo). Dos alas de un apartamento por
// piso y fachada (cuatro por piso, veinte por bloque), escalera central. Devuelve una geometría por material
const PISO = 2.9;
function plantillaBloque(largo = 22, ancho = 10, pisos = 5) {
  const H = pisos * PISO, zf = ancho / 2, P = { estuco: [], ladrillo: [], concreto: [], vidrio: [], luz: [], marco: [], acento: [], oscuro: [], calado: [] };
  const put = (k, w, h, d, x, y, z) => P[k].push(new THREE.BoxGeometry(w, h, d).translate(x, y + h / 2, z));
  const hueco = (k, w, h, x, y, s) => {   // vidrio con marco blanco y alféizar en la fachada s (+1 frente, −1 atrás)
    const z = s * (zf + 0.03);
    put(k, w, h, 0.05, x, y, z);
    put('marco', w + 0.14, 0.07, 0.1, x, y + h, z); put('marco', 0.07, h, 0.1, x - w / 2 - 0.035, y, z); put('marco', 0.07, h, 0.1, x + w / 2 + 0.035, y, z);
    put('marco', w + 0.3, 0.06, 0.22, x, y - 0.06, s * (zf + 0.1));
  };
  put('estuco', largo, H, ancho, 0, 0, 0);
  // culatas y zócalo de ladrillo a la vista, pretil de la cubierta y losa
  [-1, 1].forEach((s) => put('ladrillo', 0.12, H + 0.9, ancho + 0.12, s * (largo / 2 + 0.06), 0, 0));
  put('ladrillo', largo + 0.14, 0.95, ancho + 0.14, 0, 0, 0);
  [-1, 1].forEach((s) => { put('estuco', largo, 0.9, 0.2, 0, H, s * (zf - 0.1)); put('estuco', 0.2, 0.9, ancho - 0.4, s * (largo / 2 - 0.1), H, 0); });
  put('concreto', largo - 0.4, 0.06, ancho - 0.4, 0, H, 0);
  for (let k = 1; k < pisos; k++) put('concreto', largo + 0.18, 0.2, ancho + 0.18, 0, k * PISO - 0.1, 0);   // entrepisos
  put('concreto', largo + 4, 0.1, ancho + 4, 0, 0, 0.6);                                                   // andén perimetral
  // punto fijo: torre de escaleras al frente con fachada de bloque calado, puerta, marquesina y cuarto de tanques arriba
  put('estuco', 3.6, H + 2.6, 2.6, 0, 0, zf + 1.1);
  put('calado', 2.6, H - 1.6, 0.08, 0, 2.9, zf + 2.44);
  put('vidrio', 1.6, 2.3, 0.08, 0, 0.1, zf + 2.44); put('marco', 1.8, 0.1, 0.12, 0, 2.4, zf + 2.44);
  put('concreto', 4.4, 0.16, 1.8, 0, 2.7, zf + 3.2);
  [-0.85, 0.85].forEach((x) => P.oscuro.push(new THREE.CylinderGeometry(0.62, 0.62, 1.3, 14).translate(x, H + 2.6 + 0.65, zf + 1.1)));
  // ventanas y balcones de las dos fachadas largas; el ala de cada lado del punto fijo es un apartamento por piso
  let n = 0;
  for (const s of [1, -1]) for (let f = 0; f < pisos; f++) for (const w of [-1, 1]) {
    const y0 = f * PISO, xc = w * 6.4, enc = ((n++ * 2654435761) >>> 0) % 100 < 45 ? 'luz' : 'vidrio';
    if (f === 0) hueco(enc, 2.0, 1.25, xc - 0.6, y0 + 1.0, s);
    else {
      hueco(enc, 2.0, 2.15, xc - 0.6, y0 + 0.08, s);
      put('concreto', 3.0, 0.14, 1.15, xc - 0.6, y0 - 0.04, s * (zf + 0.575));
      put('acento', 3.0, 0.95, 0.1, xc - 0.6, y0 + 0.1, s * (zf + 1.1));
      [-1, 1].forEach((k) => put('acento', 0.1, 0.95, 1.1, xc - 0.6 + k * 1.45, y0 + 0.1, s * (zf + 0.55)));
      put('oscuro', 3.0, 0.05, 0.06, xc - 0.6, y0 + 1.08, s * (zf + 1.1));
    }
    hueco(f % 2 ? 'vidrio' : enc, 1.2, 1.2, xc + 2.7, y0 + 1.0, s);
    hueco('vidrio', 0.8, 0.8, xc - w * 3.4, y0 + 1.5, s);   // baño o cocina, junto al punto fijo
  }
  const out = {};
  for (const [k, gs] of Object.entries(P)) if (gs.length) out[k] = unir(gs);
  return out;
}
// bloques instanciados: una malla por material para los diez; cada bloque mira con el punto fijo a la vía más cercana
function bloques(polys, vias, pisos = 5) {
  const g = new THREE.Group();
  if (!polys.length) return g;
  const med = polys.map((poly) => {
    const [cx, cy] = cen(poly), lados = [0, 1].map((i) => Math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1]));
    const i0 = lados[0] >= lados[1] ? 0 : 1, ang = Math.atan2(poly[i0 + 1][1] - poly[i0][1], poly[i0 + 1][0] - poly[i0][0]);
    const dv = (sgn) => Math.min(...vias.map((t) => distLinea([cx + Math.sin(ang) * 9 * sgn, cy - Math.cos(ang) * 9 * sgn], t.puntos)));
    return { cx, cy, largo: Math.max(...lados), ancho: Math.min(...lados), rot: dv(1) <= dv(-1) ? ang : ang + Math.PI };
  });
  const M = {
    estuco: matT('estuco', { color: '#f6f2ea' }), ladrillo: matT('ladrillo'), concreto: matT('concreto', { color: '#ebe8e1' }),
    vidrio: mat(new THREE.Color('#3e5361'), { roughness: 0.05, metalness: 0.75 }),
    luz: mat(new THREE.Color('#3e5361'), { roughness: 0.05, metalness: 0.75, emissive: new THREE.Color('#ffc27a'), emissiveIntensity: 0 }),
    marco: matT('estuco', { color: '#fbfaf6' }), acento: matT('estuco', { color: '#c8643c' }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.45, metalness: 0.5 }), calado: matT('calado'),
  };
  const T = plantillaBloque(Math.round(med[0].largo), Math.round(med[0].ancho), pisos), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0), uno = new THREE.Vector3(1, 1, 1);
  const ims = Object.entries(T).map(([k, geo]) => { const im = new THREE.InstancedMesh(geo, M[k], med.length); im.name = k; return im; });
  med.forEach((b, i) => { q.setFromAxisAngle(eje, b.rot); m4.compose(V3(b.cx, b.cy), q, uno); ims.forEach((im) => im.setMatrixAt(i, m4)); });
  const estuco = ims.find((im) => im.name === 'estuco');
  [estuco, ...ims.filter((im) => im !== estuco)].forEach((im) => { im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); g.add(im); });
  g.userData.instancias = g.children.slice(); g.userData.crecerY = true; g.userData.ventanas = M.luz;
  return g;
}

// salón comunal: muros de pañete con zócalo de ladrillo, cubierta de teja a dos aguas, corredor con columnas y ventanales
function salonComunal(x, y, rot, colorFranja) {
  const g = new THREE.Group(), w = 14, d = 9, h = 4;
  const M = { estuco: matT('estuco', { color: '#f3ede1' }), ladrillo: matT('ladrillo'), teja: matT('teja', { color: '#f2e8de' }), concreto: matT('concreto'), vidrio: mat(new THREE.Color('#3e5361'), { roughness: 0.05, metalness: 0.7 }), madera: matT('madera'), franja: mat(new THREE.Color(colorFranja), { roughness: 0.6 }) };
  const add = (geo, m) => { const o = new THREE.Mesh(geo, m); o.castShadow = true; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.BoxGeometry(w, h, d).translate(0, h / 2, 0), M.estuco);
  add(new THREE.BoxGeometry(w + 0.12, 0.9, d + 0.12).translate(0, 0.45, 0), M.ladrillo);
  const perfil = new THREE.Shape([[-d / 2 - 0.8, 0], [d / 2 + 3.6, 0], [1.4, 2.2]].map(([a, b]) => new THREE.Vector2(a, b)));   // el alero largo cubre el corredor (+z)
  add(new THREE.ExtrudeGeometry(perfil, { depth: w + 1.2, bevelEnabled: false }).translate(0, 0, -(w + 1.2) / 2).rotateY(-Math.PI / 2).translate(0, h - 0.05, 0), M.teja);
  add(new THREE.BoxGeometry(w + 0.6, 0.2, 3.6).translate(0, 0.1, d / 2 + 1.8), M.concreto);
  add(unir([-6, -2, 2, 6].map((cx) => new THREE.BoxGeometry(0.28, h - 0.1, 0.28).translate(cx, (h - 0.1) / 2, d / 2 + 3.2))), M.madera);
  add(unir([[-4.2, 1.9], [0, 2.6], [4.2, 1.9]].map(([cx, ww]) => new THREE.BoxGeometry(ww, 2.4, 0.06).translate(cx, 1.5, d / 2 + 0.03))), M.vidrio);
  add(new THREE.BoxGeometry(w + 0.04, 0.5, 0.06).translate(0, h - 0.5, d / 2 + 0.04), M.franja);
  g.position.copy(V3(x, y)); g.rotation.y = rot;
  return g;
}
// casa rural del prototipo VIVA: un piso, corredor de madera al frente, zinc a dos aguas, zócalo de color, tanque elevado,
// panel solar y huerta con cerca de madera
function casaRural(semilla) {
  const g = new THREE.Group(), r = azar(semilla), zocalos = ['#2f6d8c', '#3c7a4a', '#a8402f', '#c98a1d'];
  const M = casaRural.mats || (casaRural.mats = {
    muro: matT('estuco', { color: '#f6f1e4' }), zinc: matT('zinc', { color: '#b7bec2' }), madera: matT('madera', { color: '#c49a6c' }), concreto: matT('concreto'),
    panel: mat(new THREE.Color('#1b2944'), { roughness: 0.18, metalness: 0.65 }), tanque: mat(new THREE.Color('#1f2326'), { roughness: 0.5 }), metal: mat(new THREE.Color('#8f979c'), { roughness: 0.4, metalness: 0.7 }),
    patio: matT('arcilla', { color: '#e8d9c0', modo: 'xz' }), pasto: matT('cesped'), vidrio: mat(new THREE.Color('#33424c'), { roughness: 0.1, metalness: 0.6 }),
  });
  const zoc = mat(new THREE.Color(zocalos[Math.floor(r() * zocalos.length)]), { roughness: 0.8 });
  const add = (geo, m, sombra = true) => { const o = new THREE.Mesh(geo, m); o.castShadow = sombra; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.CircleGeometry(14, 32).rotateX(-Math.PI / 2).translate(0, 0.04, 0), M.pasto, false);
  add(new THREE.CircleGeometry(6.5, 24).rotateX(-Math.PI / 2).translate(0, 0.06, 2.5), M.patio, false);
  add(new THREE.BoxGeometry(8, 0.3, 9.6).translate(0, 0.15, 1.2), M.concreto);
  add(new THREE.BoxGeometry(7.4, 2.8, 7.2).translate(0, 1.7, 0), M.muro);
  add(new THREE.BoxGeometry(7.46, 0.75, 7.26).translate(0, 0.67, 0), zoc);
  const perfil = new THREE.Shape([[-4.4, 0], [6.4, 0], [1.0, 1.9]].map(([a, b]) => new THREE.Vector2(a, b)));
  add(new THREE.ExtrudeGeometry(perfil, { depth: 8.4, bevelEnabled: false }).translate(0, 0, -4.2).rotateY(-Math.PI / 2).translate(0, 3.05, 0).scale(1, 1, 1), M.zinc);
  add(unir([-3.5, -1.2, 1.2, 3.5].map((x) => new THREE.BoxGeometry(0.16, 2.75, 0.16).translate(x, 1.67, 5.6))), M.madera);
  add(unir([new THREE.BoxGeometry(7.4, 0.16, 0.16).translate(0, 3.0, 5.6), new THREE.BoxGeometry(1.0, 2.1, 0.06).translate(-1.4, 1.35, 3.62), new THREE.BoxGeometry(1.1, 1.0, 0.07).translate(1.8, 1.7, 3.62), new THREE.BoxGeometry(0.07, 1.0, 1.1).translate(-3.73, 1.7, 0.6)]), M.madera);
  add(new THREE.BoxGeometry(0.9, 0.85, 0.05).translate(1.8, 1.7, 3.66), M.vidrio);
  const pv = add(new THREE.BoxGeometry(2.1, 0.06, 1.6), M.panel); pv.position.set(-1.9, 4.05, -1.3); pv.rotation.x = -0.42;
  add(unir([[-0.6, -0.6], [0.6, -0.6], [-0.6, 0.6], [0.6, 0.6]].map(([a, b]) => new THREE.BoxGeometry(0.1, 3, 0.1).translate(5.6 + a, 1.5, -2.6 + b)).concat([new THREE.BoxGeometry(1.5, 0.1, 1.5).translate(5.6, 3.0, -2.6)])), M.metal);
  add(new THREE.CylinderGeometry(0.7, 0.7, 1.3, 16).translate(5.6, 3.7, -2.6), M.tanque);
  const cerca = [];
  for (let k = 0; k <= 8; k++) cerca.push(new THREE.BoxGeometry(0.1, 1.1, 0.1).translate(-9 + k * 1.2, 0.55, -6));
  [0.4, 0.9].forEach((yy) => cerca.push(new THREE.BoxGeometry(9.7, 0.06, 0.05).translate(-4.2, yy, -6)));
  add(unir(cerca), M.madera);
  g.add(arboles([[-7.5, -7.5], [8.5, -7]], { alto: 7, semilla: semilla + 3, especie: 'mixto' }), palmas([[9.5, 2]], { alto: 8, semilla: semilla + 5 }));   // detrás y al lado: el corredor queda a la vista
  g.add(jardin([[-8.6, -7], [-1.4, -7], [-1.4, -10.6], [-8.6, -10.6]], { densidad: 1.2, semilla: semilla + 9, tipos: ['heliconia', 'arbusto', 'helecho'] }));
  return g;
}

export async function crear(esc, datos, cap) {
  const color = '--m-vivienda';
  const S = (rol) => sitios(datos, 'vivienda', rol);
  const lote1 = sitio(datos, 'vivienda', 'lote_jdo')?.poligono || LOTE1, lote2 = sitio(datos, 'vivienda', 'lote_oeste')?.poligono || LOTE2;
  const cNueva = esc.capa('viv.nueva'), cMej = esc.capa('viv.mejoramiento'), cRural = esc.capa('viv.rural');
  const capaPiso = (m, k) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const M = {
    terraplen: matT('cesped', { color: '#dde6cf' }), verde: capaPiso(matT('cesped', { color: '#cfe0bd' }), 3),
    via: capaPiso(matT('asfalto'), 5), anden: capaPiso(matT('concreto', { modo: 'xz', color: '#e8e4dc' }), 4), lote: capaPiso(matT('cesped', { color: '#e6ecd8' }), 3),
    cesion: capaPiso(matT('cesped', { color: '#c6dbb0' }), 3), sendero: capaPiso(matT('adoquin'), 4), cancha: capaPiso(matT('caucho', { color: '#2f6fb8', relieve: 0 }), 4), caucho: capaPiso(matT('caucho', { color: '#1f9e8f' }), 4),
    cal: capaPiso(mat(new THREE.Color('#fbfbf7'), { roughness: 0.9 }), 6),
  };
  [lote1, lote2].forEach((p) => { const o = new THREE.Mesh(losa(p, 0.06), M.terraplen); o.receiveShadow = true; cNueva.add(o); });
  const vias = trazados(datos, 'vivienda', 'via');
  // vías: andén de concreto en todo el ancho y calzada de asfalto 3 m más angosta
  const piso = (geo, m) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; cNueva.add(o); return o; };
  piso(unir(vias.map((t) => cinta(t.puntos, t.ancho_m || 8, 0.09))), M.anden);
  piso(unir(vias.map((t) => cinta(t.puntos, (t.ancho_m || 8) - 3, 0.1))), M.via);
  // ¿el punto está en el andén de alguna vía y no en la calzada de ninguna?
  const enAnden = (p) => vias.some((t) => { const d = distLinea(p, t.puntos), w = (t.ancho_m || 8) / 2; return d < w && d > w - 1.5; }) && vias.every((t) => distLinea(p, t.puntos) > (t.ancho_m || 8) / 2 - 1.5);
  // Lote 1: manzanas verdes y 10 bloques de 5 pisos (20 apartamentos VIP cada uno)
  S('manzana').forEach((m) => piso(losa(m.poligono, 0.08), M.verde));
  const polBloques = S('bloque').map((b) => b.poligono);
  const blq = bloques(polBloques, vias, 5); cNueva.add(blq);
  const lejosDeBloques = (p, d = 13) => polBloques.every((b) => !dentro(p, b) && Math.hypot(p[0] - cen(b)[0], p[1] - cen(b)[1]) > d);
  const verde1 = arboles(S('manzana').flatMap((m) => { const [cx, cy] = cen(m.poligono), r = azar(Math.round(Math.abs(cx))); return Array.from({ length: 8 }, () => [cx + (r() - 0.5) * 36, cy + (r() - 0.5) * 32]); }).filter((p) => S('manzana').some((m) => dentro(p, m.poligono)) && lejosDeBloques(p)), { alto: 8, semilla: 101, especie: 'mixto' });
  cNueva.add(verde1);
  // Lote 2: casas en serie de 2 pisos en las manzanas de vivienda (primera etapa: 100) y cesiones con parque y salón
  const metaNuevas = cap.componentes?.find((c) => c.id === 'nuevas')?.unidades || 300, etapa2 = Math.max(0, metaNuevas - S('bloque').reduce((a, b) => a + (b.unidades || 20), 0)) || 100;
  const lotes = S('manzana_casas').flatMap((m) => { piso(losa(m.poligono, 0.08), M.lote); return lotesManzana(m.poligono, m.lotes || 99); });
  const viv = casas(lotes.slice(0, etapa2), { frente: 6, fondo: 9.5, alto: 2.7 }); cNueva.add(viv);
  const libres = lotes.slice(etapa2);
  if (libres.length) cNueva.add(new THREE.Mesh(unir(libres.map((l) => { const h = l.rot % Math.PI ? [5.4, 2.6] : [2.6, 5.4]; return cinta([[l.x - h[0], l.y - h[1]], [l.x + h[0], l.y - h[1]], [l.x + h[0], l.y + h[1]], [l.x - h[0], l.y + h[1]], [l.x - h[0], l.y - h[1]]], 0.25, 0.12); })), new THREE.MeshBasicMaterial({ color: 0xe0612a })));
  // cesiones: césped, senderos, cancha múltiple, juegos con velaria, salón comunal mirando a la vía y árboles
  const ces = S('cesion'), colorFranja = esc.css(color).getStyle(), ptsVerde2 = [];
  ces.forEach((m, i) => {
    const poly = m.poligono, [cx, cy] = cen(poly), vNorte = Math.min(...vias.map((t) => distLinea([cx, cy + 20], t.puntos))), vSur = Math.min(...vias.map((t) => distLinea([cx, cy - 20], t.puntos)));
    const frente = vSur < vNorte ? -1 : 1;   // hacia dónde queda la vía
    piso(losa(poly, 0.09), M.cesion);
    piso(unir([cinta([[cx - 38, cy], [cx + 38, cy]], 2.4, 0.11), cinta([[cx + 22, cy], [cx + 22, cy + frente * 13]], 2.4, 0.11)]), M.sendero);
    const cancha = [[cx - 34, cy - 7], [cx - 10, cy - 7], [cx - 10, cy + 7], [cx - 34, cy + 7]];
    if (cancha.every((p) => dentro(p, poly))) {
      piso(losa(cancha, 0.12), M.cancha);
      piso(unir([cinta([...cancha, cancha[0], cancha[1]], 0.08, 0.13), cinta([[cx - 22, cy - 7], [cx - 22, cy + 7]], 0.08, 0.13), cinta(Array.from({ length: 25 }, (_, k) => [cx - 22 + 1.8 * Math.cos((k / 24) * Math.PI * 2), cy + 1.8 * Math.sin((k / 24) * Math.PI * 2)]), 0.08, 0.13)]), M.cal);
    }
    const juegos = [[cx - 5, cy - 6], [cx + 6, cy - 6], [cx + 6, cy + 6], [cx - 5, cy + 6]];
    if (juegos.every((p) => dentro(p, poly))) { piso(losa(juegos, 0.12), M.caucho); cNueva.add(membrana(cx + 0.5, cy, 9, 9.5, 4.2, 0.3, { flecha: 1.0 })); }
    cNueva.add(salonComunal(cx + 22, cy - frente * 3, frente > 0 ? Math.PI : 0, colorFranja));
    const r = azar(Math.round(Math.abs(cy)) + 3);
    for (let k = 0; k < 16; k++) { const p = [cx + (r() - 0.5) * 76, cy + (r() < 0.5 ? -1 : 1) * (9.5 + r() * 3)]; if (dentro(p, poly)) ptsVerde2.push(p); }
    cNueva.add(bancas([[cx - 5, cy + frente * -8.4, frente > 0 ? 0 : Math.PI], [cx + 6, cy + frente * -8.4, frente > 0 ? 0 : Math.PI], [cx - 38 + 2, cy + 1.8, Math.PI]]));
    cNueva.add(gente([[cx - 30, cy + 2, 0.4], [cx - 18, cy - 3, 2.2], [cx - 25, cy + 4, -1], [cx + 1, cy + 2, 1.2], [cx + 3, cy - 2, 2.9], [cx + 14, cy + 0.6, 0.2], [cx + 20, cy + frente * 7, 0]], { semilla: 31 + i }));
  });
  const verde2 = arboles(ptsVerde2, { alto: 9, semilla: 103, especie: 'mixto' });
  cNueva.add(verde2);
  // arborización y alumbrado de las vías (en el andén, sin quedar en la calzada de otra) y carros parqueados
  const lotes12 = [lote1, lote2], enLote = (p) => lotes12.some((l) => dentro(p, l));
  const arbVia = [], luzVia = [], parqueados = [];
  vias.forEach((t, i) => {
    const w = (t.ancho_m || 8) / 2;
    [1, -1].forEach((s) => {
      aLoLargo(t.puntos, 13, s * (w - 0.75), 5 + i).forEach(([x, y]) => { if (enAnden([x, y]) && enLote([x, y]) && lejosDeBloques([x, y], 8)) arbVia.push([x, y]); });
      aLoLargo(t.puntos, 26, s * (w - 0.35), 11 + i * 3).forEach(([x, y]) => { if (enAnden([x, y]) && enLote([x, y])) luzVia.push([x, y]); });
      aLoLargo(t.puntos, 7.5, s * (w - 2.6), 3 + i * 2).forEach(([x, y, a], k) => { if ((k * 7 + i * 3) % 5 < 2 && enLote([x, y]) && vias.every((o) => o === t || distLinea([x, y], o.puntos) > (o.ancho_m || 8) / 2 + 1)) parqueados.push([x, y, a]); });
    });
  });
  const verde3 = arboles(arbVia, { alto: 7, semilla: 107, especie: 'mixto' });
  cNueva.add(verde3, postes(luzVia, 6), carros(parqueados, { semilla: 17 }));
  const paseantes = [];
  vias.forEach((t, i) => aLoLargo(t.puntos, 23, (i % 2 ? 1 : -1) * ((t.ancho_m || 8) / 2 - 0.8), 9).forEach(([x, y, a], k) => { if (k % 2 === 0 && enLote([x, y])) paseantes.push([x, y, a + (k % 4 ? 0 : Math.PI)]); }));
  cNueva.add(gente(paseantes, { semilla: 37 }));
  // las ventanas de los bloques y de las casas se encienden al atardecer
  esc.alHora?.((H) => { [blq.userData.ventanas, viv.userData.ventanas].forEach((m) => { if (m) m.emissiveIntensity = 0.85 * H.encendido; }); esc.st.invalidate(); });
  [lote1, lote2].forEach((p) => esc.linea([...p, p[0]].map(([x, y]) => [x, y, 1.2]), { color, ancho: 3, punteada: true, padre: cNueva }));
  const [c1, c2] = [cen(lote1), cen(lote2)];
  esc.etiqueta(`<b>Lote 1 · ${polBloques.length * 20 || 200} VIP en ${polBloques.length || 10} bloques</b><small>predio José Domingo Oliveros · ${(area(lote1) / 10000).toLocaleString('es-CO', { maximumFractionDigits: 2 })} ha · terraplén ya construido</small>`, { pos: [c1[0], Math.max(...lote1.map((q) => q[1])) + 10, 30], padre: cNueva, color: `var(${color})`, ancla: [0.5, 1], punto: [c1[0], c1[1], 8] });
  const cupo = lotes.length;   // los lotes de 6 × 12 m que caben de verdad en las manzanas (algunas tienen esquinas cortadas)
  esc.etiqueta(`<b>Lote 2 · ${Math.min(etapa2, lotes.length)} casas VIS</b><small>cupo para ${cupo} casas · ${ces.length || 2} manzanas de cesión</small>`, { pos: [c2[0], Math.max(...lote2.map((q) => q[1])) + 10, 24], padre: cNueva, color: `var(${color})`, ancla: [0.5, 1], punto: [c2[0], c2[1], 3] });

  // mejoramientos: techos naranja sobre casas reales de los barrios con más carencias (casas pequeñas en la periferia)
  const metaMej = cap.componentes?.find((c) => c.id === 'mejoramientos')?.unidades || 400;
  await esc.listoHuellas;
  const zonas = S('barrio_mejoramiento').map((s) => s.poligono), r = azar(7);
  const candidatas = esc.huellas.filter((h) => !h.zona && h.area < 140 && !dentro([h.cx, h.cy], lote1) && !dentro([h.cx, h.cy], lote2) && (zonas.length ? zonas.some((z) => dentro([h.cx, h.cy], z)) : Math.hypot(h.cx - 60, h.cy - 120) > 280));
  const elegidas = candidatas.map((h) => ({ h, k: r() })).sort((a, b) => a.k - b.k).slice(0, metaMej).map((x) => x.h);
  const rp = [];
  // el resaltado sigue la cubierta de cada casa (a dos aguas o losa: contexto.js la deja en h.techo), un poco por encima
  elegidas.forEach((h) => {
    if (h.techo?.length) { for (let i = 0; i < h.techo.length; i++) rp.push(h.techo[i] + (i % 3 === 1 ? 0.06 : 0)); return; }
    THREE.ShapeUtils.triangulateShape(h.pts.map(([x, y]) => new THREE.Vector2(x, y)), []).forEach((t) => t.forEach((j) => rp.push(h.pts[j][0], h.h + 0.18, -h.pts[j][1])));
  });
  const gm = new THREE.BufferGeometry(); gm.setAttribute('position', new THREE.Float32BufferAttribute(rp, 3)); gm.computeVertexNormals();
  const matMej = new THREE.MeshStandardMaterial({ color: 0xe0612a, roughness: 0.6, emissive: 0xe0612a, emissiveIntensity: 0.55, side: THREE.DoubleSide, transparent: true });
  esc.tenir(matMej, color, true);
  cMej.add(new THREE.Mesh(gm, matMej));
  // grupo que se muestra de cerca: las casas resaltadas más cercanas a un barrio de la periferia noroccidental
  const foco = elegidas.map((h) => ({ h, d: Math.hypot(h.cx + 360, h.cy - 330) })).sort((a, b) => a.d - b.d).slice(0, 70).map((x) => [x.h.cx, x.h.cy]);
  const cf = foco.length ? [foco.reduce((a, q) => a + q[0], 0) / foco.length, foco.reduce((a, q) => a + q[1], 0) / foco.length] : [-300, 380];
  esc.etiqueta(`<b>${metaMej.toLocaleString('es-CO')} mejoramientos urbanos</b><small>muestra: cubiertas, pisos, baños y cocinas en casas reales</small>`, { pos: [cf[0], cf[1], 40], padre: cMej, color: `var(${color})`, ancla: [0.5, 1] });
  // vivienda rural: está dispersa en 60 veredas; se muestra el prototipo de VIVA (50–60 m², un piso, saneamiento
  // propio y solar) en cinco fincas junto a la vía que va al acueducto, como muestra
  const via = trazado(datos, 'aguas', 'conduccion')?.puntos || [[-2356, 518], [-1500, 200], [-280, -4]];
  const enVia = (f) => { let L = 0; const seg = via.slice(1).map((b, i) => { const a = via[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]); L += l; return { a, b, l }; }); let t = f * L; for (const q of seg) { if (t <= q.l) { const k = t / q.l, ang = Math.atan2(q.b[1] - q.a[1], q.b[0] - q.a[0]); return { x: q.a[0] + (q.b[0] - q.a[0]) * k, y: q.a[1] + (q.b[1] - q.a[1]) * k, ang }; } t -= q.l; } const u = seg[seg.length - 1]; return { x: u.b[0], y: u.b[1], ang: 0 }; };
  const fincas = [0.44, 0.4475, 0.455, 0.4625, 0.47].map((f, i) => { const q = enVia(f), lado = i % 2 ? 1 : -1; return { x: q.x - Math.sin(q.ang) * 20 * lado, y: q.y + Math.cos(q.ang) * 20 * lado, ang: q.ang, lado }; });
  // sin árboles del contexto encima de las fincas de muestra; cada casa con el corredor (frente, +z local) hacia la vía
  esc.despejar?.(fincas.map((f) => [f.x, f.y]), 16);
  fincas.forEach((f, i) => { const g = casaRural(201 + i * 17); g.position.copy(V3(f.x, f.y)); g.rotation.y = f.ang + (f.lado > 0 ? 0 : Math.PI); cRural.add(g); });
  cRural.add(gente(fincas.slice(0, 4).map((f, i) => [f.x + Math.cos(f.ang) * 3 - Math.sin(f.ang) * 5 * -f.lado, f.y + Math.sin(f.ang) * 3 + Math.cos(f.ang) * 5 * -f.lado, f.ang + i]), { semilla: 41 }));
  // el rótulo, encima de la casa más al norte (detrás de las demás en la vista), para no tapar ninguna
  const f0 = fincas.reduce((a, f) => (f.y > a.y ? f : a), fincas[0]);
  esc.etiqueta('<b>Prototipo VIVA · 50–60 m²</b><small>un piso · saneamiento propio · solar donde no llega la red</small>', { pos: [f0.x, f0.y, 22], padre: cRural, color: `var(${color})`, ancla: [0.5, 1], punto: [f0.x, f0.y, 4] });
  esc.etiqueta('<b>200 casas rurales nuevas</b><small>en el lote de cada familia, en 60 veredas (muestra)</small>', { pos: [fincas[4].x, fincas[4].y, 10], padre: cRural, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0, 0.5] });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const vistaNueva = () => esc.encuadrar([...lote1, ...lote2], { rumbo: 196, elev: 44, margen: 0.7, alto: 30 });
  const vistaCasco = () => esc.encuadrar([[-650, -420], [880, -420], [880, 760], [-650, 760], ...lote2, [-1450, 80]], { rumbo: 196, elev: 50, margen: 0.94 });
  const vistaRural = () => esc.encuadrar(caja(fincas.map((f) => [f.x, f.y]), 15), { rumbo: 200, elev: 34, margen: 0.9, alto: 8 });
  const vistaMej = () => esc.encuadrar(foco.length ? caja(foco, 40) : caja([cf], 200), { rumbo: 196, elev: 52, margen: 0.9 });
  const gris = (v) => esc.contextoGris?.(v);
  const animNueva = () => {
    brotar(blq, { duracion: 1.8, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() });
    brotar(viv, { duracion: 2.2, retraso: 0.9, onUpdate: inv });
    [verde1, verde2, verde3].forEach((v) => brotar(v, { duracion: 1.6, retraso: 1.4, onUpdate: inv }));
  };
  return {
    completo: ['viv.nueva', 'viv.mejoramiento'],
    salir: () => gris(false),
    alCompleto: () => gris(false),
    // estados que una pieza del catálogo puede pedir (visual.js): las cubiertas del pueblo en gris, para que se lean los techos a mejorar
    efectos: { gris },
    pasos: {
      portadilla: { capas: [], antes: () => gris(false), vista: vistaCasco },
      componentes: { capas: ['viv.nueva', 'viv.mejoramiento'], antes: () => gris(true), vista: vistaCasco },
      nuevas: { capas: ['viv.nueva'], antes: () => gris(false), vista: vistaNueva, animar: animNueva },
      mejoramientos: { capas: ['viv.mejoramiento'], antes: () => gris(true), vista: vistaMej, animar: () => { if (gsap) gsap.fromTo(matMej, { opacity: 0 }, { opacity: 1, duration: 1, delay: 0.6, onUpdate: inv }); } },
      rural: { capas: ['viv.rural'], antes: () => gris(false), vista: vistaRural, etiquetas: ['viv.rural'] },
      '*': { capas: ['viv.nueva', 'viv.mejoramiento'], antes: () => gris(true), vista: vistaCasco },
    },
  };
}
