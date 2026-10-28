// Vivienda: la vivienda nueva urbana en los dos lotes reales del levantamiento, y los mejoramientos sobre casas reales.
//  · Lote 1, predio José Domingo Oliveros (1,71 ha, terraplén ya construido): 200 VIP en 10 bloques de 5 pisos con sus
//    vías internas y manzanas verdes.
//  · Lote 2, lote occidental (2,54 ha): casas en serie de 2 pisos en lotes de 6 × 12 m (100 en la primera etapa, de 138
//    posibles) y dos manzanas de cesión con parque y salón comunal.
//  · Mejoramientos: techos resaltados sobre casas pequeñas de la periferia del casco, a partir de las huellas reales.
import { THREE, gsap } from '../../core.js';
import { casas, losa, cinta, arboles, brotar, crecer, dentro, area, azar, unir } from '../geo3d.js';
import { sitio, sitios, trazados, caja } from './comun.js';

const LOTE1 = [[-603, -256], [-561, -256], [-531, -273], [-499, -297], [-496, -339], [-502, -380], [-537, -395], [-585, -398], [-632, -383], [-659, -365], [-653, -339], [-620, -297], [-608, -273]];
const LOTE2 = [[-1198, 2], [-1120, 4], [-1062, 8], [-1032, 20], [-1028, 80], [-1036, 150], [-1110, 158], [-1170, 160], [-1200, 140], [-1204, 60]];
const cen = (p) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length];

// lotes de 6 × 12 m en dos filas espalda con espalda a lo largo del lado mayor de una manzana (cada fila da a su calle)
function lotesManzana(poly, max = 99, frente = 6, fondo = 12) {
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]), [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const horizontal = x1 - x0 >= y1 - y0, out = [];
  const L0 = horizontal ? x0 : y0, L1 = horizontal ? x1 : y1, A0 = horizontal ? y0 : x0, A1 = horizontal ? y1 : x1;
  [[A0 + fondo / 2, 0], [A1 - fondo / 2, 1]].forEach(([a, fila]) => {
    for (let l = L0 + frente / 2; l + frente / 2 <= L1 + 0.01; l += frente) {
      const [x, y] = horizontal ? [l, a] : [a, l];
      const esq = horizontal ? [[x - 2.6, y - 5.4], [x + 2.6, y - 5.4], [x + 2.6, y + 5.4], [x - 2.6, y + 5.4]] : [[x - 5.4, y - 2.6], [x + 5.4, y - 2.6], [x + 5.4, y + 2.6], [x - 5.4, y + 2.6]];
      if (esq.every((p) => dentro(p, poly))) out.push({ x, y, rot: (horizontal ? Math.PI / 2 : 0) + (fila ? Math.PI : 0), pisos: 2 });
    }
  });
  return out.slice(0, max);
}
// bloques multifamiliares: caja de 5 pisos con franjas de entrepiso, cubierta y escalera exterior
function bloques(polys, pisos = 5) {
  const g = new THREE.Group(), M = { muro: new THREE.MeshStandardMaterial({ color: 0xf1e7d6, roughness: 0.85 }), franja: new THREE.MeshStandardMaterial({ color: 0xc8643c, roughness: 0.7 }), cubierta: new THREE.MeshStandardMaterial({ color: 0x8f9499, roughness: 0.6 }), vidrio: new THREE.MeshStandardMaterial({ color: 0x5d7f99, roughness: 0.25, metalness: 0.3 }) };
  polys.forEach((poly) => {
    const [cx, cy] = cen(poly), lados = [0, 1].map((i) => Math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1]));
    const largo = Math.max(...lados), ancho = Math.min(...lados), i0 = lados[0] >= lados[1] ? 0 : 1, ang = Math.atan2(poly[i0 + 1][1] - poly[i0][1], poly[i0 + 1][0] - poly[i0][0]);
    const b = new THREE.Group(), H = pisos * 2.9;
    b.add(new THREE.Mesh(new THREE.BoxGeometry(largo, H, ancho).translate(0, H / 2, 0), M.muro));
    const fr = [], vi = [];
    for (let k = 1; k <= pisos; k++) fr.push(new THREE.BoxGeometry(largo + 0.12, 0.22, ancho + 0.12).translate(0, k * 2.9 - 0.05, 0));
    for (let k = 0; k < pisos; k++) for (let j = -3; j <= 3; j++) [-1, 1].forEach((s) => vi.push(new THREE.BoxGeometry(1.5, 1.2, 0.06).translate(j * 3.1, k * 2.9 + 1.55, s * (ancho / 2 + 0.03))));
    b.add(new THREE.Mesh(unir(fr), M.franja), new THREE.Mesh(unir(vi), M.vidrio), new THREE.Mesh(new THREE.BoxGeometry(largo + 0.6, 0.35, ancho + 0.6).translate(0, H + 0.18, 0), M.cubierta));
    b.add(new THREE.Mesh(new THREE.BoxGeometry(3.2, H + 1.2, 3).translate(largo / 2 + 1.5, (H + 1.2) / 2, 0), M.muro));
    b.position.set(cx, 0, -cy); b.rotation.y = ang;
    b.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    g.add(b);
  });
  return g;
}

export async function crear(esc, datos, cap) {
  const color = '--m-vivienda';
  const S = (rol) => sitios(datos, 'vivienda', rol);
  const lote1 = sitio(datos, 'vivienda', 'lote_jdo')?.poligono || LOTE1, lote2 = sitio(datos, 'vivienda', 'lote_oeste')?.poligono || LOTE2;
  const cNueva = esc.capa('viv.nueva'), cMej = esc.capa('viv.mejoramiento'), cRural = esc.capa('viv.rural');
  const M = {
    terraplen: new THREE.MeshStandardMaterial({ color: 0xcbbf9f, roughness: 1 }), verde: new THREE.MeshStandardMaterial({ color: 0x7fae5a, roughness: 1, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }),
    via: new THREE.MeshStandardMaterial({ color: 0x5d6064, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }), lote: new THREE.MeshStandardMaterial({ color: 0xd9cfbd, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }),
    cesion: new THREE.MeshStandardMaterial({ color: 0x5f9e48, roughness: 1, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }), salon: new THREE.MeshStandardMaterial({ color: 0xe0612a, roughness: 0.7 }),
  };
  [lote1, lote2].forEach((p) => cNueva.add(new THREE.Mesh(losa(p, 0.06), M.terraplen)));
  trazados(datos, 'vivienda', 'via').forEach((t) => cNueva.add(new THREE.Mesh(cinta(t.puntos, t.ancho_m || 8, 0.1), M.via)));
  // Lote 1: manzanas verdes y 10 bloques de 5 pisos (20 apartamentos VIP cada uno)
  S('manzana').forEach((m) => cNueva.add(new THREE.Mesh(losa(m.poligono, 0.08), M.verde)));
  const polBloques = S('bloque').map((b) => b.poligono);
  const blq = bloques(polBloques.length ? polBloques : [], 5); cNueva.add(blq);
  const verde1 = arboles(S('manzana').flatMap((m) => { const [cx, cy] = cen(m.poligono), r = azar(Math.round(Math.abs(cx))); return Array.from({ length: 7 }, () => [cx + (r() - 0.5) * 34, cy + (r() - 0.5) * 30]); }).filter((p) => S('manzana').some((m) => dentro(p, m.poligono)) && polBloques.every((b) => !dentro(p, b) && Math.hypot(p[0] - cen(b)[0], p[1] - cen(b)[1]) > 13)), { alto: 8, semilla: 101 });
  cNueva.add(verde1);
  // Lote 2: casas en serie de 2 pisos en las manzanas de vivienda (primera etapa: 100) y cesiones con parque y salón
  const metaNuevas = cap.componentes?.find((c) => c.id === 'nuevas')?.unidades || 300, etapa2 = Math.max(0, metaNuevas - S('bloque').reduce((a, b) => a + (b.unidades || 20), 0)) || 100;
  const lotes = S('manzana_casas').flatMap((m) => { cNueva.add(new THREE.Mesh(losa(m.poligono, 0.08), M.lote)); return lotesManzana(m.poligono, m.lotes || 99); });
  const viv = casas(lotes.slice(0, etapa2), { frente: 6, fondo: 9.5, alto: 2.7 }); cNueva.add(viv);
  const libres = lotes.slice(etapa2);
  if (libres.length) cNueva.add(new THREE.Mesh(unir(libres.map((l) => { const h = l.rot % Math.PI ? [5.4, 2.6] : [2.6, 5.4]; return cinta([[l.x - h[0], l.y - h[1]], [l.x + h[0], l.y - h[1]], [l.x + h[0], l.y + h[1]], [l.x - h[0], l.y + h[1]], [l.x - h[0], l.y - h[1]]], 0.25, 0.12); })), new THREE.MeshBasicMaterial({ color: 0xe0612a })));
  const ces = S('cesion');
  ces.forEach((m) => { cNueva.add(new THREE.Mesh(losa(m.poligono, 0.09), M.cesion)); const [cx, cy] = cen(m.poligono); const s = new THREE.Mesh(new THREE.BoxGeometry(14, 4, 9).translate(cx + 18, 2, -cy), M.salon); s.castShadow = true; cNueva.add(s); });
  const verde2 = arboles(ces.flatMap((m) => { const [cx, cy] = cen(m.poligono), r = azar(Math.round(Math.abs(cy)) + 3); return Array.from({ length: 12 }, () => [cx - 8 + (r() - 0.5) * 50, cy + (r() - 0.5) * 18]); }).filter((p) => ces.some((m) => dentro(p, m.poligono))), { alto: 9, semilla: 103 });
  cNueva.add(verde2);
  [lote1, lote2].forEach((p) => esc.linea([...p, p[0]].map(([x, y]) => [x, y, 1.2]), { color, ancho: 3, punteada: true, padre: cNueva }));
  const [c1, c2] = [cen(lote1), cen(lote2)];
  esc.etiqueta(`<b>Lote 1 · ${polBloques.length * 20 || 200} VIP en ${polBloques.length || 10} bloques</b><small>predio José Domingo Oliveros · ${(area(lote1) / 10000).toLocaleString('es-CO', { maximumFractionDigits: 2 })} ha · terraplén ya construido</small>`, { pos: [c1[0], c1[1], 26], padre: cNueva, color: `var(${color})` });
  const cupo = S('manzana_casas').reduce((a, m) => a + (m.lotes || 0), 0) || lotes.length;
  esc.etiqueta(`<b>Lote 2 · ${Math.min(etapa2, lotes.length)} casas VIS</b><small>lote occidental · cupo para ${cupo} casas de 6 × 12 m · ${ces.length || 2} manzanas de cesión</small>`, { pos: [c2[0], c2[1], 18], padre: cNueva, color: `var(${color})` });

  // mejoramientos: techos naranja sobre casas reales de los barrios con más carencias (casas pequeñas en la periferia)
  const metaMej = cap.componentes?.find((c) => c.id === 'mejoramientos')?.unidades || 400;
  await esc.listoHuellas;
  const zonas = S('barrio_mejoramiento').map((s) => s.poligono), r = azar(7);
  const candidatas = esc.huellas.filter((h) => !h.zona && h.area < 140 && !dentro([h.cx, h.cy], lote1) && !dentro([h.cx, h.cy], lote2) && (zonas.length ? zonas.some((z) => dentro([h.cx, h.cy], z)) : Math.hypot(h.cx - 60, h.cy - 120) > 280));
  const elegidas = candidatas.map((h) => ({ h, k: r() })).sort((a, b) => a.k - b.k).slice(0, metaMej).map((x) => x.h);
  const rp = [];
  elegidas.forEach((h) => THREE.ShapeUtils.triangulateShape(h.pts.map(([x, y]) => new THREE.Vector2(x, y)), []).forEach((t) => t.forEach((j) => rp.push(h.pts[j][0], h.h + 0.18, -h.pts[j][1]))));
  const gm = new THREE.BufferGeometry(); gm.setAttribute('position', new THREE.Float32BufferAttribute(rp, 3)); gm.computeVertexNormals();
  const matMej = new THREE.MeshStandardMaterial({ color: 0xe0612a, roughness: 0.6, emissive: 0xe0612a, emissiveIntensity: 0.25, side: THREE.DoubleSide });
  esc.tenir(matMej, color, true);
  cMej.add(new THREE.Mesh(gm, matMej));
  esc.etiqueta(`<b>${elegidas.length} mejoramientos urbanos</b><small>cubiertas, pisos, baños y cocinas en casas reales de la periferia</small>`, { pos: [-300, 380, 24], padre: cMej, color: `var(${color})` });
  // vivienda rural: está dispersa en 60 veredas, fuera de la maqueta; se señala hacia el campo
  esc.etiqueta('<b>Vivienda rural</b><small>200 casas nuevas en sitio propio y 400 mejoramientos en las veredas</small>', { pos: [-1700, -900, 30], padre: cRural, color: `var(${color})` });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const vistaNueva = () => esc.encuadrar([...lote1, ...lote2], { rumbo: 196, elev: 44, margen: 0.7, alto: 30 });
  const vistaCasco = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], [-650, 760], ...lote2], { rumbo: 196, elev: 50, margen: 0.94 });
  const vistaRural = () => esc.encuadrar([[-2400, -1200], [900, -1200], [900, 900], [-2400, 900]], { rumbo: 200, elev: 52, margen: 0.94 });
  const animNueva = () => {
    blq.children.forEach((b, i) => crecer(b, { duracion: 1, retraso: 0.6 + i * 0.08, onUpdate: inv, alFinal: i === blq.children.length - 1 ? () => esc.st.updateShadows() : undefined }));
    brotar(viv, { duracion: 2.2, retraso: 0.9, onUpdate: inv });
    [verde1, verde2].forEach((v) => brotar(v, { duracion: 1.6, retraso: 1.4, onUpdate: inv }));
  };
  return {
    completo: ['viv.nueva', 'viv.mejoramiento'],
    pasos: {
      portadilla: { capas: [], vista: vistaCasco },
      componentes: { capas: ['viv.nueva', 'viv.mejoramiento'], vista: vistaCasco },
      nuevas: { capas: ['viv.nueva'], vista: vistaNueva, animar: animNueva },
      mejoramientos: { capas: ['viv.mejoramiento'], vista: vistaCasco, animar: () => { if (gsap) gsap.fromTo(matMej, { opacity: 0 }, { opacity: 1, duration: 1, delay: 0.6, onStart: () => { matMej.transparent = true; }, onUpdate: inv, onComplete: () => { matMej.transparent = false; } }); } },
      rural: { capas: ['viv.nueva', 'viv.mejoramiento', 'viv.rural'], vista: vistaRural },
      '*': { capas: ['viv.nueva', 'viv.mejoramiento'], vista: vistaCasco },
    },
  };
}
