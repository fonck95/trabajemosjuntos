// Vivienda: el barrio nuevo de vivienda de interés social, los mejoramientos sobre casas reales y la vivienda rural.
//  · Barrio nuevo (documento del proyecto de vivienda, 2026): 300 apartamentos en 25 bloques de 3 pisos sobre un lote de
//    unas 5 ha cuya ubicación está por definir; en la maqueta va en un lote indicativo al occidente del casco (geo.json).
//    Bloques de 21 × 12 m con la escalera central acristalada al frente y dos apartamentos de 9 × 6 m a cada lado por piso,
//    franjas de color arena junto a la escalera y terracota en las esquinas sobre fachada clara, balcones con baranda
//    oscura y cubierta plana con pretil. Vía interna en anillo con parqueaderos en bahía, andenes, árboles y alumbrado;
//    parque central con juegos infantiles, cancha múltiple, kiosco, gimnasio al aire libre y senderos; entrada con el
//    letrero de bienvenida (el nombre del barrio está por decidir: el de la imagen conceptual es ilustrativo). En el paso
//    del apartamento tipo, uno de los bloques se ve cortado en el piso 3 con sus cuatro apartamentos.
//  · Mejoramientos: techos resaltados sobre casas pequeñas de la periferia del casco, a partir de las huellas reales.
//  · Vivienda rural: el prototipo de la Empresa de Vivienda de Antioquia en cinco fincas de muestra junto a la vía que va
//    al acueducto. Las ventanas se encienden al atardecer (tema oscuro).
import { THREE, gsap, mat } from '../../core.js';
import { losa, cinta, arboles, palmas, jardin, bancas, gente, carros, postes, aLoLargo, brotar, dentro, area, azar, unir, distLinea, sembrar } from '../geo3d.js';
import { matT } from '../texturas.js';
import { sitios, trazado, trazados, caja } from './comun.js';

// el lote indicativo si geo.json no lo trae (216 × 234 m, unas 5 ha)
const LOTE = [[-1248, -112], [-1032, -112], [-1032, 122], [-1248, 122]];
const cen = (p) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length];
const V3 = (x, y, h = 0) => new THREE.Vector3(x, h, -y);
const PISO = 2.9;
// punto del modelo [x, y] de un punto local de una pieza girada rot (lx a lo largo, lz hacia su frente: el +z local)
const aMundo = (o, lx, lz) => [o.x + lx * Math.cos(o.rot) + lz * Math.sin(o.rot), o.y + lx * Math.sin(o.rot) - lz * Math.cos(o.rot)];
// el rumbo (grados desde el norte, en el sentido del reloj) hacia donde mira el frente de una pieza girada rot
const rumboFrente = (rot) => (THREE.MathUtils.radToDeg(Math.atan2(Math.sin(rot), -Math.cos(rot))) + 360) % 360;
const sentido = (poly) => { let a = 0; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) a += (poly[j][0] - poly[i][0]) * (poly[j][1] + poly[i][1]); return a < 0 ? -1 : 1; };   // 1: antihorario
// polígono cerrado con las esquinas redondeadas (radio r): empieza y termina a mitad del último lado, para que la cinta
// del anillo no quede con una esquina viva
function lazo(poly, r = 10, n = 6) {
  const m = poly.length, arcos = [];
  for (let i = 0; i < m; i++) {
    const p = poly[i], a = poly[(i + m - 1) % m], b = poly[(i + 1) % m];
    const la = Math.hypot(a[0] - p[0], a[1] - p[1]), lb = Math.hypot(b[0] - p[0], b[1] - p[1]), ra = Math.min(r, la / 2), rb = Math.min(r, lb / 2);
    const q0 = [p[0] + ((a[0] - p[0]) / la) * ra, p[1] + ((a[1] - p[1]) / la) * ra], q2 = [p[0] + ((b[0] - p[0]) / lb) * rb, p[1] + ((b[1] - p[1]) / lb) * rb];
    for (let k = 0; k <= n; k++) { const t = k / n, u = 1 - t; arcos.push([u * u * q0[0] + 2 * u * t * p[0] + t * t * q2[0], u * u * q0[1] + 2 * u * t * p[1] + t * t * q2[1]]); }
  }
  const z = arcos[arcos.length - 1], medio = [(z[0] + poly[0][0]) / 2, (z[1] + poly[0][1]) / 2];
  return [medio, ...arcos, medio];
}

// ---------------------------------------------------------------- bloque de 3 pisos (plantilla instanciada)
// Coordenadas locales: x a lo largo (21 m), +z hacia el frente (la vía), y hacia arriba. Escalera central de 3,2 m que sale
// 0,7 m al frente, acristalada en cada piso, con puerta, marquesina y gradas; a cada lado, un apartamento adelante y otro
// atrás (cuatro por piso). Con `corte`, el bloque llega solo hasta el piso 2 (sin pretil): encima va el piso 3 cortado.
// Devuelve una geometría por material.
function plantillaBloque({ largo = 21, ancho = 12, pisos = 3, corte = false } = {}) {
  const H = pisos * PISO, zf = ancho / 2, xl = largo / 2, alto = corte ? H : H + 0.7;
  const P = { estuco: [], arena: [], terracota: [], escalera: [], concreto: [], cubierta: [], vidrio: [], luz: [], marco: [], oscuro: [] };
  const put = (k, w, h, d, x, y, z) => P[k].push(new THREE.BoxGeometry(w, h, d).translate(x, y + h / 2, z));
  // ventana con marco claro y alféizar en una fachada larga (s = 1 al frente, −1 atrás) o en una culata (huecoLado)
  const hueco = (k, w, h, x, y, s) => {
    const z = s * (zf + 0.03);
    put(k, w, h, 0.05, x, y, z);
    put('marco', w + 0.18, 0.09, 0.1, x, y + h, z); put('marco', 0.09, h, 0.1, x - w / 2 - 0.045, y, z); put('marco', 0.09, h, 0.1, x + w / 2 + 0.045, y, z);
    if (w > 1.1) put('marco', 0.06, h, 0.08, x, y, z);
    put('marco', w + 0.3, 0.07, 0.22, x, y - 0.07, s * (zf + 0.09));
  };
  const huecoLado = (k, w, h, z, y, s) => {
    const x = s * (xl + 0.03);
    put(k, 0.05, h, w, x, y, z);
    put('marco', 0.1, 0.09, w + 0.18, x, y + h, z); put('marco', 0.1, h, 0.09, x, y, z - w / 2 - 0.045); put('marco', 0.1, h, 0.09, x, y, z + w / 2 + 0.045);
    put('marco', 0.22, 0.07, w + 0.3, s * (xl + 0.09), y - 0.07, z);
  };
  put('estuco', largo, H, ancho, 0, 0, 0);
  put('concreto', largo + 0.1, 0.45, ancho + 0.1, 0, 0, 0);                    // zócalo
  put('concreto', largo + 2.4, 0.08, ancho + 2.4, 0, 0, 0);                     // andén perimetral
  if (!corte) {
    [-1, 1].forEach((s) => { put('estuco', largo, 0.7, 0.2, 0, H, s * (zf - 0.1)); put('estuco', 0.2, 0.7, ancho - 0.4, s * (xl - 0.1), H, 0); });
    [-1, 1].forEach((s) => { put('marco', largo + 0.1, 0.06, 0.3, 0, H + 0.7, s * (zf - 0.1)); put('marco', 0.3, 0.06, ancho, s * (xl - 0.1), H + 0.7, 0); });
    put('cubierta', largo - 0.4, 0.05, ancho - 0.4, 0, H, 0);
    put('escalera', 3.2, 1.6, ancho - 0.4, 0, H, 0);                               // la escalera sale sobre la cubierta
    P.oscuro.push(new THREE.CylinderGeometry(0.6, 0.6, 1.1, 14).translate(0, H + 1.6 + 0.55, -2.6));   // tanque
  }
  // escalera central acristalada
  const hc = corte ? H : H + 1.6;
  put('escalera', 3.2, hc, 0.7, 0, 0, zf + 0.35);
  put('escalera', 3.2, hc, 0.3, 0, 0, -(zf + 0.15));
  for (let f = 0; f < pisos; f++) {
    const y0 = f * PISO;
    if (f === 0) { put('vidrio', 1.9, 2.3, 0.06, 0, 0.45, zf + 0.72); put('oscuro', 0.06, 2.3, 0.08, 0, 0.45, zf + 0.73); }
    else { put(f % 2 ? 'luz' : 'vidrio', 2.4, 2.3, 0.06, 0, y0 + 0.25, zf + 0.72); put('marco', 0.06, 2.3, 0.08, 0, y0 + 0.25, zf + 0.74); put('marco', 2.4, 0.06, 0.08, 0, y0 + 1.4, zf + 0.74); put('marco', 2.52, 0.08, 0.1, 0, y0 + 2.55, zf + 0.74); put('marco', 2.52, 0.08, 0.1, 0, y0 + 0.17, zf + 0.74); }
    put('vidrio', 1.0, 1.9, 0.05, 0, y0 + 0.6, -(zf + 0.31));
  }
  put('concreto', 3.8, 0.14, 1.5, 0, 2.75, zf + 1.4);                                                       // marquesina
  put('concreto', 3.2, 0.15, 1.3, 0, 0, zf + 1.35); put('concreto', 3.2, 0.3, 0.7, 0, 0, zf + 1.05);      // gradas
  // franjas: arena junto a la escalera y terracota en las esquinas, en las fachadas largas y en las culatas
  for (const s of [1, -1]) for (const w of [-1, 1]) {
    put('arena', 1.8, alto - 0.45, 0.12, w * 2.5, 0.45, s * (zf + 0.06));
    put('terracota', 1.5, alto - 0.45, 0.12, w * (xl - 0.75), 0.45, s * (zf + 0.06));
    put('terracota', 0.12, alto - 0.45, 1.5, w * (xl + 0.06), 0.45, s * (zf - 0.75));
  }
  // por piso y por apartamento: sala con balcón (desde el piso 2), baño y alcoba principal en la fachada larga y la
  // alcoba 2 en la culata
  let n = 0;
  const enc = () => ((((n++) * 2654435761) >>> 0) % 100 < 45 ? 'luz' : 'vidrio');
  for (const s of [1, -1]) for (let f = 0; f < pisos; f++) for (const w of [-1, 1]) {
    const y0 = f * PISO, xb = w * 4.9;
    if (f === 0) hueco(enc(), 1.6, 1.25, xb, y0 + 1.0, s);
    else {
      hueco(enc(), 1.5, 2.15, xb, y0 + 0.1, s);
      put('concreto', 1.9, 0.12, 1.15, xb, y0 - 0.02, s * (zf + 0.575));
      put('oscuro', 1.9, 0.05, 0.05, xb, y0 + 1.0, s * (zf + 1.12));
      [-1, 1].forEach((k) => put('oscuro', 0.04, 0.05, 1.1, xb + k * 0.93, y0 + 1.0, s * (zf + 0.57)));
      for (let b = 0; b < 9; b++) put('oscuro', 0.025, 0.9, 0.025, xb - 0.88 + b * 0.22, y0 + 0.1, s * (zf + 1.12));
    }
    hueco('vidrio', 0.6, 0.5, w * 6.65, y0 + 1.75, s);
    hueco(enc(), 1.3, 1.25, w * 7.95, y0 + 1.0, s);
  }
  for (const w of [-1, 1]) for (let f = 0; f < pisos; f++) for (const s of [-1, 1]) huecoLado(enc(), 1.0, 1.2, s * 1.65, f * PISO + 1.0, w);
  const out = {};
  for (const [k, gs] of Object.entries(P)) if (gs.length) out[k] = unir(gs);
  return out;
}
const matsBloque = () => matsBloque.M || (matsBloque.M = {
  estuco: matT('estuco', { color: '#f5f2eb' }), arena: matT('estuco', { color: '#d2b08a' }), terracota: matT('estuco', { color: '#b8693f' }),
  escalera: matT('estuco', { color: '#8a7d6e' }), concreto: matT('concreto', { color: '#e4e1da' }), cubierta: matT('concreto', { color: '#cfcfc9' }),
  vidrio: mat(new THREE.Color('#4f6878'), { roughness: 0.12, metalness: 0.6 }),
  luz: mat(new THREE.Color('#4f6878'), { roughness: 0.12, metalness: 0.6, emissive: new THREE.Color('#ffc27a'), emissiveIntensity: 0 }),
  marco: matT('estuco', { color: '#fbfaf6' }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.45, metalness: 0.5 }),
});
// los 25 bloques instanciados: una malla por material. lista: [{ x, y, rot }]. ocultar(i, si): saca un bloque (el que se
// muestra cortado) o lo devuelve a su sitio
function bloques(lista) {
  const g = new THREE.Group();
  if (!lista.length) return g;
  const M = matsBloque(), T = plantillaBloque(), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0), uno = new THREE.Vector3(1, 1, 1);
  const ims = Object.entries(T).map(([k, geo]) => { const im = new THREE.InstancedMesh(geo, M[k], lista.length); im.name = k; return im; });
  const matriz = (b) => { q.setFromAxisAngle(eje, b.rot); return m4.compose(V3(b.x, b.y), q, uno); };
  lista.forEach((b, i) => { matriz(b); ims.forEach((im) => im.setMatrixAt(i, m4)); });
  const estuco = ims.find((im) => im.name === 'estuco');
  [estuco, ...ims.filter((im) => im !== estuco)].forEach((im) => { im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); g.add(im); });
  g.userData.instancias = g.children.slice(); g.userData.crecerY = true; g.userData.ventanas = M.luz;
  g.userData.ocultar = (i, si) => {
    if (si) m4.makeScale(0, 0, 0); else matriz(lista[i]);
    ims.forEach((im) => { im.setMatrixAt(i, m4); im.instanceMatrix.needsUpdate = true; });
  };
  return g;
}
// el piso 3 cortado a 1,3 m: los cuatro apartamentos tipo de 9 × 6 m (sala-comedor, cocina, zona de ropas, baño, alcoba
// principal, alcoba 2 y balcón, con muebles sencillos) y la escalera central entre ellos. Mismas coordenadas locales del
// bloque; va encima del bloque de dos pisos de la plantilla con `corte`
function pisoEnCorte() {
  const H = 2 * PISO, hw = 1.1, y = H + 0.1;
  const P = { madera: [], alcoba: [], baldosa: [], bano: [], balcon: [], estuco: [], arena: [], terracota: [], escalera: [], concreto: [], oscuro: [], vidrio: [], cama: [], tela: [], mueble: [] };
  const put = (k, w, h, d, x, yy, z) => P[k].push(new THREE.BoxGeometry(w, h, d).translate(x, yy + h / 2, z));
  put('concreto', 21, 0.1, 12, 0, H, 0);
  // a: de la escalera hacia la culata (0 a 9); b: de la mitad del bloque hacia la fachada (0 a 6)
  const apto = (sx, sz) => {
    const X = (a) => sx * (1.5 + a), Z = (b) => sz * b;
    const cajon = (k, a0, a1, b0, b1, h, y0) => put(k, Math.abs(X(a1) - X(a0)), h, Math.abs(Z(b1) - Z(b0)), (X(a0) + X(a1)) / 2, y0, (Z(b0) + Z(b1)) / 2);
    const suelo = (k, a0, a1, b0, b1, e = 0.006) => cajon(k, a0, a1, b0, b1, 0.03, y + e);
    const muro = (a0, a1, b0, b1, e = 0.1) => (a0 === a1 ? cajon('estuco', a0 - e / 2, a0 + e / 2, b0, b1, hw, y) : cajon('estuco', a0, a1, b0 - e / 2, b0 + e / 2, hw, y));
    suelo('madera', 0, 9, 0, 6, 0);
    suelo('baldosa', 0, 2.1, 0, 3.0); suelo('baldosa', 2.1, 3.4, 1.4, 3.0); suelo('bano', 4.3, 5.7, 3.75, 6);
    suelo('alcoba', 5.7, 9, 2.9, 6); suelo('alcoba', 6.3, 9, 0, 2.9);
    // balcón de la sala
    cajon('concreto', 2.5, 4.3, 6, 7.15, 0.12, H - 0.02); suelo('balcon', 2.55, 4.25, 6.0, 7.1, 0.012);
    cajon('oscuro', 2.5, 4.3, 7.1, 7.15, 0.05, y + 0.95);
    for (let a = 2.55; a < 4.3; a += 0.22) cajon('oscuro', a, a + 0.025, 7.1, 7.125, 0.95, y);
    // muros: fachada (con el vano del balcón), culata, el de la escalera (con la puerta) y la medianera; luego los interiores
    muro(0, 2.5, 5.91, 5.91, 0.18); muro(4.3, 9, 5.91, 5.91, 0.18); muro(8.91, 8.91, 0, 6, 0.18);
    muro(0.075, 0.075, 0, 3.0, 0.15); muro(0.075, 0.075, 4.0, 6, 0.15);
    if (sz > 0) muro(0, 9, 0, 0, 0.15);
    muro(5.7, 9, 2.9, 2.9); muro(6.3, 6.3, 0, 1.9); muro(5.7, 5.7, 3.75, 6); muro(4.3, 4.3, 3.75, 6);
    muro(4.3, 4.6, 3.75, 3.75); muro(5.4, 5.7, 3.75, 3.75); muro(3.4, 3.4, 1.4, 3.0); muro(2.1, 3.4, 1.4, 1.4);
    // muebles: camas, sofá, comedor, cocina en L y lavadora
    cajon('cama', 6.7, 8.75, 3.5, 5.1, 0.45, y); cajon('tela', 7.2, 8.75, 3.5, 5.1, 0.07, y + 0.45);
    cajon('cama', 6.9, 8.85, 0.25, 1.3, 0.45, y); cajon('tela', 7.4, 8.85, 0.25, 1.3, 0.07, y + 0.45);
    cajon('tela', 0.25, 1.05, 3.5, 5.5, 0.75, y); cajon('mueble', 2.3, 3.5, 3.6, 4.4, 0.75, y);
    cajon('mueble', 0.2, 0.8, 0.15, 2.7, 0.9, y); cajon('mueble', 0.8, 2.05, 0.15, 0.75, 0.9, y); cajon('mueble', 2.55, 3.15, 2.3, 2.9, 0.85, y);
  };
  [1, -1].forEach((sx) => [1, -1].forEach((sz) => apto(sx, sz)));
  // escalera central: descanso que da a las cuatro puertas, tramo que sube junto al vidrio del frente y el vacío del que baja
  put('concreto', 3.0, 0.1, 10.4, 0, H, -0.8);
  for (let k = 0; k < 8; k++) put('concreto', 1.4, 0.17 * (k + 1), 0.27, -0.75, H, 4.55 + k * 0.27);
  put('oscuro', 1.4, 0.02, 2.2, 0.75, H + 0.02, 5.5); put('oscuro', 0.05, 1.0, 2.2, 0, H + 0.1, 5.5);
  [-1, 1].forEach((s) => put('escalera', 0.2, hw, 0.7, s * 1.5, H, 6.35));
  put('vidrio', 2.8, hw, 0.05, 0, H, 6.68);
  // las franjas de la fachada siguen hasta el corte
  for (const s of [1, -1]) for (const w of [-1, 1]) {
    put('arena', 1.8, hw, 0.12, w * 2.5, H, s * 6.06); put('terracota', 1.5, hw, 0.12, w * 9.75, H, s * 6.06); put('terracota', 0.12, hw, 1.5, w * 10.56, H, s * 5.25);
  }
  const out = {};
  for (const [k, gs] of Object.entries(P)) if (gs.length) out[k] = unir(gs);
  return out;
}
function bloqueCortado(b) {
  const g = new THREE.Group(), MB = matsBloque();
  const M = {
    ...MB, madera: mat(new THREE.Color('#d9b48a'), { roughness: 0.6 }), alcoba: mat(new THREE.Color('#ead3ae'), { roughness: 0.6 }), baldosa: mat(new THREE.Color('#ebe7de'), { roughness: 0.5 }),
    bano: mat(new THREE.Color('#b9d7e1'), { roughness: 0.4 }), balcon: mat(new THREE.Color('#c47a55'), { roughness: 0.7 }), cama: mat(new THREE.Color('#f3f1ec'), { roughness: 0.9 }),
    tela: mat(new THREE.Color('#5a7ea8'), { roughness: 0.95 }), mueble: mat(new THREE.Color('#d8d2c7'), { roughness: 0.6 }),
  };
  [plantillaBloque({ pisos: 2, corte: true }), pisoEnCorte()].forEach((T) => Object.entries(T).forEach(([k, geo]) => { const o = new THREE.Mesh(geo, M[k]); o.castShadow = true; o.receiveShadow = true; g.add(o); }));
  g.position.copy(V3(b.x, b.y)); g.rotation.y = b.rot;
  return g;
}

// ---------------------------------------------------------------- parque central
// cilindro de radio r entre dos puntos locales [x, y, z] (tubos de los juegos y del gimnasio)
function tuboEntre(a, b, r = 0.06) {
  const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b), L = va.distanceTo(vb);
  const geo = new THREE.CylinderGeometry(r, r, L, 8).translate(0, L / 2, 0);
  geo.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), vb.clone().sub(va).normalize()));
  return geo.translate(va.x, va.y, va.z);
}
// kiosco (la pieza del antiguo salón comunal, abierta): piso de concreto, cuatro columnas de madera y cubierta de teja oscura
// a cuatro aguas, con mesa y bancas
function kiosco(x, y, rot) {
  const g = new THREE.Group(), w = 9, h = 2.8;
  const M = { concreto: matT('concreto'), madera: matT('madera', { color: '#8d6a4b' }), teja: matT('teja', { color: '#8e5f42' }), mesa: matT('madera', { color: '#b58a64' }) };
  const add = (geo, m) => { const o = new THREE.Mesh(geo, m); o.castShadow = true; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.BoxGeometry(w + 1, 0.2, w + 1).translate(0, 0.1, 0), M.concreto);
  add(unir([[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([a, b]) => new THREE.BoxGeometry(0.28, h, 0.28).translate(a * (w / 2 - 0.3), 0.2 + h / 2, b * (w / 2 - 0.3)))), M.madera);
  add(unir([new THREE.BoxGeometry(w, 0.25, 0.3).translate(0, 0.2 + h, w / 2 - 0.3), new THREE.BoxGeometry(w, 0.25, 0.3).translate(0, 0.2 + h, -(w / 2 - 0.3)), new THREE.BoxGeometry(0.3, 0.25, w).translate(w / 2 - 0.3, 0.2 + h, 0), new THREE.BoxGeometry(0.3, 0.25, w).translate(-(w / 2 - 0.3), 0.2 + h, 0)]), M.madera);
  add(new THREE.ConeGeometry(w * 0.8, 2.8, 4, 1).rotateY(Math.PI / 4).translate(0, 0.2 + h + 0.2 + 1.4, 0), M.teja);
  add(unir([new THREE.BoxGeometry(2.4, 0.08, 1.0).translate(0, 0.95, 0), new THREE.BoxGeometry(0.2, 0.75, 0.2).translate(0, 0.575, 0)]), M.mesa);
  g.add(bancas([[0, 1.1, 0], [0, -1.1, Math.PI]]).translateY(0.2));
  g.position.copy(V3(x, y)); g.rotation.y = rot;
  return g;
}
// parque infantil: piso de caucho circular de dos colores, torre con cubierta roja, rodadero, torre baja con puente,
// columpios y hongos para trepar
function juegos(x, y, r = 12) {
  const g = new THREE.Group();
  const cau = (c) => Object.assign(matT('caucho', { color: c }), { polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 });
  const M = { rojo: mat(new THREE.Color('#d8483a'), { roughness: 0.55 }), amarillo: mat(new THREE.Color('#f2c230'), { roughness: 0.5 }), azul: mat(new THREE.Color('#2f7fc0'), { roughness: 0.5 }), verde: mat(new THREE.Color('#3fa45b'), { roughness: 0.5 }), metal: mat(new THREE.Color('#d8dde0'), { roughness: 0.3, metalness: 0.7 }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.6 }) };
  const add = (geo, m, sombra = true) => { const o = new THREE.Mesh(geo, m); o.castShadow = sombra; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.CircleGeometry(r, 48).rotateX(-Math.PI / 2).translate(0, 0.12, 0), cau('#2f7fc0'), false);
  add(new THREE.RingGeometry(r - 2.2, r, 48).rotateX(-Math.PI / 2).translate(0, 0.14, 0), cau('#d8553a'), false);
  add(new THREE.RingGeometry(3.2, 4.6, 40).rotateX(-Math.PI / 2).translate(0, 0.14, 0), cau('#f2b630'), false);
  // torre: plataforma a 1,6 m, barandas, techo rojo en punta
  const torre = (cx, cz, lado, hp, techo) => {
    add(unir([[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([a, b]) => new THREE.BoxGeometry(0.16, hp + 1.9, 0.16).translate(cx + a * lado / 2, (hp + 1.9) / 2, cz + b * lado / 2))), M.amarillo);
    add(new THREE.BoxGeometry(lado, 0.12, lado).translate(cx, hp, cz), M.azul);
    add(unir([new THREE.BoxGeometry(lado, 0.7, 0.06).translate(cx, hp + 0.47, cz - lado / 2), new THREE.BoxGeometry(0.06, 0.7, lado).translate(cx - lado / 2, hp + 0.47, cz)]), M.verde);
    add(new THREE.ConeGeometry(lado * 0.82, 1.3, 4, 1).rotateY(Math.PI / 4).translate(cx, hp + 1.9 + 0.65, cz), techo);
  };
  torre(0.6, -0.4, 2.6, 1.6, M.rojo);
  torre(-4.2, 2.6, 1.9, 1.1, M.azul);
  add(new THREE.BoxGeometry(3.2, 0.1, 0.9).rotateY(0.5).translate(-2.0, 1.35, 1.2), M.amarillo);                         // puente entre las torres
  const rod = add(new THREE.BoxGeometry(0.8, 0.08, 4.0), M.amarillo); rod.position.set(2.1 + 1.6, 0.95, -0.4); rod.rotation.set(0, Math.PI / 2, 0); rod.rotateX(0.37);   // rodadero
  // columpios: dos marcos en A con su travesaño y dos sillas colgadas
  const cx = 4.4, cz = 5.4;
  add(unir([-1.8, 1.8].flatMap((e) => [tuboEntre([cx + e, 0, cz - 0.95], [cx + e, 2.75, cz]), tuboEntre([cx + e, 0, cz + 0.95], [cx + e, 2.75, cz])]).concat([tuboEntre([cx - 1.85, 2.75, cz], [cx + 1.85, 2.75, cz], 0.07)])), M.rojo);
  add(unir([-0.7, 0.7].flatMap((dx) => [new THREE.BoxGeometry(0.5, 0.05, 0.3).translate(cx + dx, 0.55, cz), new THREE.BoxGeometry(0.02, 2.2, 0.02).translate(cx + dx - 0.22, 1.65, cz), new THREE.BoxGeometry(0.02, 2.2, 0.02).translate(cx + dx + 0.22, 1.65, cz)])), M.oscuro);
  // hongos para trepar
  [[-6.5, -3.5, M.verde], [-5.2, -5.6, M.amarillo], [-3.0, -6.4, M.rojo]].forEach(([a, b, m]) => add(new THREE.CylinderGeometry(0.55, 0.35, 0.5, 14).translate(a, 0.25, b), m));
  g.position.copy(V3(x, y));
  return g;
}
// cancha múltiple de 30 × 17 m: piso azul con la cancha naranja, líneas, tableros de baloncesto y malla en las cabeceras;
// el lado largo va a lo largo del eje local z
function canchaMultiple(x, y, rot) {
  const g = new THREE.Group(), L = 30, W = 17, l = 26, w = 14;
  const piso = (c, k) => Object.assign(matT('caucho', { color: c, relieve: 0 }), { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const M = { azul: piso('#2f6fb8', 4), naranja: piso('#e07a3a', 5), cal: Object.assign(mat(new THREE.Color('#fbfbf7'), { roughness: 0.9 }), { polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.4 }), tablero: mat(new THREE.Color('#f4f4f0'), { roughness: 0.5 }), aro: mat(new THREE.Color('#e0612a'), { roughness: 0.4 }), malla: matT('malla', { color: '#3c4a3f' }) };
  const add = (geo, m, sombra = false) => { const o = new THREE.Mesh(geo, m); o.castShadow = sombra; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.BoxGeometry(W, 0.12, L).translate(0, 0.06, 0), M.azul);
  add(new THREE.PlaneGeometry(w, l).rotateX(-Math.PI / 2).translate(0, 0.125, 0), M.naranja);
  const linea = (a, b) => { const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz); return new THREE.BoxGeometry(0.08, 0.01, len).rotateY(Math.atan2(dx, dz)).translate((a[0] + b[0]) / 2, 0.135, (a[1] + b[1]) / 2); };
  const arco = (cz, r, desde, hasta, n = 20) => Array.from({ length: n }, (_, k) => { const t0 = desde + ((hasta - desde) * k) / n, t1 = desde + ((hasta - desde) * (k + 1)) / n; return linea([r * Math.sin(t0), cz + r * Math.cos(t0)], [r * Math.sin(t1), cz + r * Math.cos(t1)]); });
  const ls = [linea([-w / 2, -l / 2], [w / 2, -l / 2]), linea([w / 2, -l / 2], [w / 2, l / 2]), linea([w / 2, l / 2], [-w / 2, l / 2]), linea([-w / 2, l / 2], [-w / 2, -l / 2]), linea([-w / 2, 0], [w / 2, 0]), ...arco(0, 1.8, 0, Math.PI * 2, 24)];
  [-1, 1].forEach((s) => {
    const z0 = s * l / 2;
    ls.push(linea([-2.45, z0], [-2.45, z0 - s * 5.8]), linea([2.45, z0], [2.45, z0 - s * 5.8]), linea([-2.45, z0 - s * 5.8], [2.45, z0 - s * 5.8]), ...arco(z0, 6.75, s > 0 ? Math.PI / 2 + 0.3 : -Math.PI / 2 + 0.3, s > 0 ? Math.PI * 1.5 - 0.3 : Math.PI / 2 - 0.3, 18));
    // tablero: poste, brazo, tablero y aro
    add(unir([new THREE.CylinderGeometry(0.1, 0.12, 3.4, 10).translate(0, 1.7, s * (l / 2 + 1.0)), new THREE.BoxGeometry(0.1, 0.1, 1.0).translate(0, 3.3, s * (l / 2 + 0.5))]), M.oscuro, true);
    add(new THREE.BoxGeometry(1.8, 1.05, 0.05).translate(0, 3.05, s * l / 2), M.tablero, true);
    add(new THREE.TorusGeometry(0.23, 0.02, 6, 16).rotateX(Math.PI / 2).translate(0, 3.05, s * (l / 2 - 0.3)), M.aro);
    // malla de 3,5 m en la cabecera y baja (1,2 m) a los lados
    add(new THREE.PlaneGeometry(W, 3.5).translate(0, 1.75 + 0.12, s * L / 2), M.malla);
    add(unir([-W / 2, -W / 4, 0, W / 4, W / 2].map((xx) => new THREE.CylinderGeometry(0.04, 0.04, 3.6, 6).translate(xx, 1.8, s * L / 2))), M.oscuro, true);
  });
  [-1, 1].forEach((s) => add(new THREE.PlaneGeometry(L, 1.2).rotateY(Math.PI / 2).translate(s * W / 2, 0.72, 0), M.malla));
  add(unir(ls), M.cal);
  g.position.copy(V3(x, y)); g.rotation.y = rot;
  return g;
}
// gimnasio al aire libre: piso de caucho verde y cinco aparatos de tubo (barras, elíptica, prensa, abdominales y paralelas)
function gimnasio(x, y, rot) {
  const g = new THREE.Group(), w = 13, d = 8;
  const M = { piso: Object.assign(matT('caucho', { color: '#3e8e57' }), { polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }), amarillo: mat(new THREE.Color('#f0c419'), { roughness: 0.4, metalness: 0.3 }), verde: mat(new THREE.Color('#2f7a4a'), { roughness: 0.4, metalness: 0.3 }) };
  const pisoG = new THREE.Mesh(new THREE.PlaneGeometry(w, d).rotateX(-Math.PI / 2).translate(0, 0.11, 0), M.piso); pisoG.receiveShadow = true; g.add(pisoG);
  const tubo = tuboEntre;
  const A = [], B = [];
  [-4.8, -2.4, 0, 2.4, 4.8].forEach((cx, i) => {
    const cz = i % 2 ? 1.2 : -1.2, t = i % 2 ? A : B;
    t.push(tubo([cx - 0.6, 0, cz], [cx - 0.6, 2.0, cz]), tubo([cx + 0.6, 0, cz], [cx + 0.6, 2.0, cz]), tubo([cx - 0.6, 2.0, cz], [cx + 0.6, 2.0, cz]));
    (i % 2 ? B : A).push(new THREE.BoxGeometry(0.9, 0.08, 0.5).translate(cx, 0.6, cz + 0.4), tubo([cx, 0, cz + 0.4], [cx, 0.6, cz + 0.4], 0.05));
  });
  [[A, M.amarillo], [B, M.verde]].forEach(([gs, m]) => { const o = new THREE.Mesh(unir(gs), m); o.castShadow = true; g.add(o); });
  g.position.copy(V3(x, y)); g.rotation.y = rot;
  return g;
}
// letrero de la entrada: muro claro sobre una jardinera, con «Bienvenidos al barrio» y el nombre de la imagen conceptual
// (ilustrativo: el nombre se escoge entre seis alternativas). La cara con el texto es el +z local
function letrero(x, y, rot) {
  const g = new THREE.Group(), cv = document.createElement('canvas');
  cv.width = 1024; cv.height = 256;
  const c = cv.getContext('2d');
  c.fillStyle = '#ece7dc'; c.fillRect(0, 0, 1024, 256);
  c.fillStyle = '#c9bfae'; c.fillRect(0, 238, 1024, 18);
  c.fillStyle = '#34483b'; c.textAlign = 'center'; c.textBaseline = 'middle';
  c.font = 'bold 82px "Trebuchet MS", "Segoe UI", Arial, sans-serif'; c.fillText('BIENVENIDOS AL BARRIO', 512, 78);
  c.fillText('ALMA DEL MAGDALENA', 512, 172);
  const tx = new THREE.CanvasTexture(cv); tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 8;
  const muro = matT('estuco', { color: '#e7e2d7' }), cara = new THREE.MeshStandardMaterial({ map: tx, roughness: 0.75 }), base = matT('concreto', { color: '#cfc8bb' });
  const add = (geo, m) => { const o = new THREE.Mesh(geo, m); o.castShadow = true; o.receiveShadow = true; g.add(o); return o; };
  add(new THREE.BoxGeometry(12.6, 0.6, 2.6).translate(0, 0.3, 0), base);
  add(new THREE.BoxGeometry(10, 2.5, 0.5).translate(0, 0.6 + 1.25, 0), [muro, muro, muro, muro, cara, muro]);
  add(new THREE.BoxGeometry(10.2, 0.12, 0.62).translate(0, 0.6 + 2.5, 0), base);
  g.position.copy(V3(x, y)); g.rotation.y = rot;
  return g;
}
// casa rural del prototipo de la Empresa de Vivienda de Antioquia: un piso, corredor de madera al frente, zinc a dos aguas,
// zócalo de color, tanque elevado, panel solar y huerta con cerca de madera
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
  const lote = S('lote')[0]?.poligono || LOTE, [lx, ly] = cen(lote);
  const cNueva = esc.capa('viv.nueva'), cBloque = esc.capa('viv.bloque'), cParque = esc.capa('viv.parque'), cMej = esc.capa('viv.mejoramiento'), cRural = esc.capa('viv.rural');
  const capaPiso = (m, k) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const M = {
    lote: capaPiso(matT('cesped', { color: '#d3e1c2' }), 2), parque: capaPiso(matT('cesped', { color: '#bcd7a2' }), 3), materas: capaPiso(matT('cesped', { color: '#a9c98c' }), 7),
    via: capaPiso(matT('asfalto'), 5), anden: capaPiso(matT('concreto', { modo: 'xz', color: '#e8e4dc' }), 4), bahia: capaPiso(matT('asfalto', { color: '#a3a6a8' }), 6),
    sendero: capaPiso(matT('adoquin', { color: '#e3cdb0' }), 4), cal: capaPiso(mat(new THREE.Color('#fbfbf7'), { roughness: 0.9 }), 8),
  };
  const piso = (geo, m) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; cNueva.add(o); return o; };
  piso(losa(lote, 0.06), M.lote);
  // vías: andén de concreto en todo el ancho y calzada de asfalto 3 m más angosta; el anillo, con las esquinas redondeadas
  const vias = trazados(datos, 'vivienda', 'via').map((t) => {
    const p = t.puntos, cerrada = p.length > 3 && p[0][0] === p[p.length - 1][0] && p[0][1] === p[p.length - 1][1];
    return { ...t, cerrada, esquinas: cerrada ? p.slice(0, -1) : null, linea: cerrada ? lazo(p.slice(0, -1), 11) : p, ancho: t.ancho_m || 10 };
  });
  piso(unir(vias.map((t) => cinta(t.linea, t.ancho, 0.09))), M.anden);
  piso(unir(vias.map((t) => cinta(t.linea, t.ancho - 3, 0.1))), M.via);
  const anillo = vias.find((t) => t.cerrada), acceso = vias.filter((t) => !t.cerrada);
  const enLote = (p) => dentro(p, lote), enAnillo = (p) => !!anillo && dentro(p, anillo.esquinas);
  const cercaDeAcceso = (p, d) => acceso.some((t) => distLinea(p, t.linea) < d);
  const sA = anillo ? sentido(anillo.esquinas) : 1;   // 1: el anillo va en sentido antihorario (la izquierda es adentro)
  // ---- los 25 bloques: cada uno mira con la escalera a la vía más cercana
  const polBloques = S('bloque').map((b) => b.poligono);
  const med = polBloques.map((poly) => {
    const [cx, cy] = cen(poly), lados = [0, 1].map((i) => Math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1]));
    const i0 = lados[0] >= lados[1] ? 0 : 1, ang = Math.atan2(poly[i0 + 1][1] - poly[i0][1], poly[i0 + 1][0] - poly[i0][0]);
    const dv = (sgn) => Math.min(...vias.map((t) => distLinea([cx + Math.sin(ang) * 9 * sgn, cy - Math.cos(ang) * 9 * sgn], t.linea)));
    return { x: cx, y: cy, rot: dv(1) <= dv(-1) ? ang : ang + Math.PI };
  });
  const blq = bloques(med); cNueva.add(blq);
  // ¿el punto queda fuera de todos los bloques, con un margen?
  const fuera = (p, m = 2) => med.every((b) => { const dx = p[0] - b.x, dy = p[1] - b.y, u = dx * Math.cos(b.rot) + dy * Math.sin(b.rot), v = dx * Math.sin(b.rot) - dy * Math.cos(b.rot); return Math.abs(u) > 10.5 + m || Math.abs(v) > 6.7 + m; });
  // caminito de la puerta de cada bloque hasta el andén: el de detrás de las bahías (afuera del anillo) o el de la vía
  const caminos = med.map((b) => { const d = anillo ? distLinea([b.x, b.y], anillo.linea) : 18, hasta = d - (enAnillo([b.x, b.y]) ? 5.2 : 9.3); return hasta > 7.5 ? cinta([aMundo(b, 0, 6.9), aMundo(b, 0, hasta)], 1.6, 0.1) : null; }).filter(Boolean);
  if (caminos.length) piso(unir(caminos), M.anden);
  // ---- entrada: el letrero de bienvenida junto a la vía de acceso, mirando a quien llega, con jardín y palmas
  const ent = S('entrada')[0] || { x: -1040, y: -7 }, acc0 = acceso[0]?.linea;
  const fLet = { x: ent.x, y: ent.y, rot: (acc0 ? Math.atan2(acc0[1][1] - acc0[0][1], acc0[1][0] - acc0[0][0]) : 0) + 0.45 + Math.PI / 2 };
  cNueva.add(letrero(fLet.x, fLet.y, fLet.rot));
  cNueva.add(jardin([aMundo(fLet, -7, 1.6), aMundo(fLet, 7, 1.6), aMundo(fLet, 7, 4.0), aMundo(fLet, -7, 4.0)], { densidad: 0.9, semilla: 71, tipos: ['heliconia', 'cordyline', 'arbusto'] }));
  cNueva.add(palmas([aMundo(fLet, 6, -3), aMundo(fLet, -8, -2), aMundo(fLet, -10, 3)], { alto: 10, semilla: 73 }));
  const lejosDelLetrero = (p, d = 10) => Math.hypot(p[0] - fLet.x, p[1] - fLet.y) > d;
  // ---- parque central: prado, sendero perimetral, conexiones con los andenes, juegos, cancha, kiosco, gimnasio y árboles
  const pq = S('parque')[0]?.poligono, piezasParque = [], senderos = [];
  let verdeParque = [], pc = [lx, ly];
  if (pq) {
    pc = cen(pq);
    const xs = pq.map((p) => p[0]), ys = pq.map((p) => p[1]), [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    piso(losa(pq, 0.08), M.parque);
    const circuito = lazo([[x0 + 4, y0 + 4], [x1 - 4, y0 + 4], [x1 - 4, y1 - 4], [x0 + 4, y1 - 4]], 9);
    const ramales = [[[x0 + 4, pc[1]], [pc[0] - 13.5, pc[1]]]];
    if (anillo) {
      const E = anillo.esquinas, [aO, aE, aS, aN] = [Math.min(...E.map((p) => p[0])), Math.max(...E.map((p) => p[0])), Math.min(...E.map((p) => p[1])), Math.max(...E.map((p) => p[1]))];
      ramales.push([[aO + 5, pc[1]], [x0 + 4, pc[1]]], [[aE - 5, pc[1]], [x1 - 4, pc[1]]]);
      // por entre los bloques de las hileras interiores, hasta el andén del anillo
      [[(b) => b.y > pc[1], y1 - 4, aN - 5], [(b) => b.y < pc[1], y0 + 4, aS + 5]].forEach(([lado, ya, yb]) => {
        const xsH = med.filter((b) => enAnillo([b.x, b.y]) && lado(b)).map((b) => b.x).sort((a, b) => a - b);
        xsH.slice(1).forEach((x, i) => { const hx = (x + xsH[i]) / 2; ramales.push([[hx, ya], [hx, yb]]); });
      });
    }
    const anilloJuegos = lazo(Array.from({ length: 12 }, (_, k) => [pc[0] + 13.6 * Math.cos((k / 12) * Math.PI * 2), pc[1] + 2 + 13.6 * Math.sin((k / 12) * Math.PI * 2)]), 3, 3);
    piso(unir([cinta(circuito, 2.6, 0.11), cinta(anilloJuegos, 2.2, 0.11), ...ramales.map((q) => cinta(q, 2.4, 0.11))]), M.sendero);
    senderos.push(circuito, anilloJuegos, ...ramales);
    // las piezas: juegos al centro, cancha al oriente, kiosco y gimnasio al occidente
    const fJ = { x: pc[0], y: pc[1] + 2, r: 12 }, fC = { x: x1 - 24, y: pc[1] + 4, rot: 0 }, fK = { x: x0 + 22, y: pc[1] + 15, rot: 0.2 }, fG = { x: x0 + 22, y: pc[1] - 15, rot: 0 };
    cNueva.add(juegos(fJ.x, fJ.y, fJ.r), canchaMultiple(fC.x, fC.y, fC.rot), kiosco(fK.x, fK.y, fK.rot), gimnasio(fG.x, fG.y, fG.rot));
    const libre = (p) => Math.hypot(p[0] - fJ.x, p[1] - fJ.y) > fJ.r + 4 && (Math.abs(p[0] - fC.x) > 11 || Math.abs(p[1] - fC.y) > 18) && Math.hypot(p[0] - fK.x, p[1] - fK.y) > 9.5 && (Math.abs(p[0] - fG.x) > 9.5 || Math.abs(p[1] - fG.y) > 7) && senderos.every((l) => distLinea(p, l) > 3);
    const rP = azar(5), palm = [], somb = [];
    sembrar(pq, 55, 9.5, 61).filter(libre).forEach((p) => (rP() < 0.4 ? palm : somb).push(p));
    verdeParque = [arboles(somb, { alto: 7, semilla: 109, especie: 'mixto' }), palmas(palm, { alto: 9, semilla: 113 })];
    cNueva.add(...verdeParque);
    cNueva.add(postes(aLoLargo(circuito, 20, 1.9, 6).map(([x, y]) => [x, y]), 4.5));
    cNueva.add(bancas([...aLoLargo(anilloJuegos, 9, 1.6, 2).map(([x, y, a]) => [x, y, a + Math.PI]), ...aLoLargo(circuito, 26, -1.7, 12).map(([x, y, a]) => [x, y, a])]));
    cNueva.add(gente([[fJ.x + 3, fJ.y + 4, 0.4], [fJ.x - 2, fJ.y - 5, 2.2], [fJ.x + 6, fJ.y - 2, -1], [fJ.x - 7, fJ.y + 1, 1.2], [fJ.x + 1, fJ.y + 8, 2.9], [fC.x - 3, fC.y + 6, 0.2], [fC.x + 2, fC.y - 4, 3.1], [fC.x + 4, fC.y + 2, 1.6], [fC.x - 2, fC.y - 9, -0.5], [fK.x + 1, fK.y + 0.5, 0], [fK.x - 1.5, fK.y - 0.5, 3], [fG.x - 2, fG.y + 1, 1.2], [fG.x + 3, fG.y - 1, 0], ...aLoLargo(circuito, 31, 0.6, 9).map(([x, y, a], k) => [x, y, a + (k % 2 ? 0 : Math.PI)])], { semilla: 31 }));
    piezasParque.push(['<b>Parque infantil</b>', [fJ.x, fJ.y, 6]], ['<b>Cancha múltiple</b>', [fC.x, fC.y, 5]], ['<b>Kiosco</b>', [fK.x, fK.y, 6]], ['<b>Gimnasio al aire libre</b>', [fG.x, fG.y, 3.5]]);
  }
  const lejosDeSenderos = (p, d = 2.5) => senderos.every((l) => distLinea(p, l) > d);
  // ---- parqueaderos en bahía por fuera del anillo (de 3,5 a 9 m del eje, con el andén detrás) y un árbol cada cinco
  // cupos; no van en las curvas ni frente a la entrada
  const arbVia = [], luzVia = [], parqueados = [], bahias = [], rayas = [], materas = [], andenExt = [];
  const ra = azar(19);
  if (anillo) {
    const E = anillo.esquinas;
    E.forEach((a, i) => {
      const b = E[(i + 1) % E.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / L, uy = (b[1] - a[1]) / L, nx = uy * sA, ny = -ux * sA;   // normal hacia afuera
      const P = (t, o) => [a[0] + ux * t + nx * o, a[1] + uy * t + ny * o];
      andenExt.push(cinta([P(12, 10.2), P(L - 12, 10.2)], 2.2, 0.095));
      let k = 0, tramo = null;
      const cerrar = () => { if (tramo) { bahias.push(losa([P(tramo[0], 3.4), P(tramo[1], 3.4), P(tramo[1], 9.0), P(tramo[0], 9.0)], 0.105)); tramo = null; } };
      for (let t = 14; t + 2.5 <= L - 14; t += 2.5, k++) {
        const c = P(t + 1.25, 6.2);
        if (cercaDeAcceso(c, 10)) { cerrar(); continue; }
        if (k % 6 === 5) { cerrar(); materas.push(losa([P(t + 0.2, 3.6), P(t + 2.3, 3.6), P(t + 2.3, 8.8), P(t + 0.2, 8.8)], 0.13)); arbVia.push(c); continue; }
        tramo = tramo ? [tramo[0], t + 2.5] : [t, t + 2.5];
        rayas.push(cinta([P(t, 3.6), P(t, 8.8)], 0.1, 0.12), cinta([P(t + 2.5, 3.6), P(t + 2.5, 8.8)], 0.1, 0.12));
        if (ra() < 0.62) parqueados.push([...c, Math.atan2(ny, nx) + (ra() < 0.5 ? 0 : Math.PI)]);
      }
      cerrar();
    });
    [[bahias, M.bahia], [rayas, M.cal], [materas, M.materas], [andenExt, M.anden]].forEach(([gs, m]) => { if (gs.length) piso(unir(gs), m); });
    // árboles del lado de adentro del anillo, alumbrado a los dos lados y algunos carros andando por la vía (por la derecha)
    aLoLargo(anillo.linea, 13, sA * 7.2, 4).forEach(([x, y]) => { if (fuera([x, y], 1.5) && lejosDeSenderos([x, y], 3)) arbVia.push([x, y]); });
    aLoLargo(anillo.linea, 24, sA * 5.6, 10).forEach(([x, y]) => luzVia.push([x, y]));
    aLoLargo(anillo.linea, 24, -sA * 10.6, 22).forEach(([x, y]) => { if (!cercaDeAcceso([x, y], 6)) luzVia.push([x, y]); });
    aLoLargo(anillo.linea, 150, -sA * 1.8, 30).forEach(([x, y, a]) => parqueados.push([x, y, a]));
  }
  acceso.forEach((t) => {
    aLoLargo(t.linea, 22, t.ancho / 2 - 0.4, 6).forEach(([x, y]) => luzVia.push([x, y]));
    aLoLargo(t.linea, 11, -(t.ancho / 2 - 0.8), 5).forEach(([x, y]) => { if (!enLote([x, y])) arbVia.push([x, y]); });
    aLoLargo(t.linea, 60, -1.8, 25).forEach(([x, y, a]) => parqueados.push([x, y, a]));
    // sin árboles del contexto sobre la vía de acceso (por fuera del lote)
    esc.despejar?.(aLoLargo(t.linea, 6).map(([x, y]) => [x, y]), 8);
  });
  // ---- arborización: franja perimetral del lote y patios de atrás de los bloques
  const lazoLote = [...lote, lote[0]];
  const arbBorde = aLoLargo(lazoLote, 9, sentido(lote) * 4.5, 3).map(([x, y]) => [x, y]).filter((p) => fuera(p, 2) && !cercaDeAcceso(p, 12) && lejosDelLetrero(p));
  const arbPatio = med.flatMap((b) => [[-6.5, -12.5], [6.5, -12.5]].map(([u, v]) => aMundo(b, u, v))).filter((p) => enLote(p) && fuera(p, 1.5) && lejosDeSenderos(p, 3) && (!anillo || distLinea(p, anillo.linea) > 9));
  const verdeVia = arboles(arbVia, { alto: 6, semilla: 107, especie: 'mixto' }), verdeBorde = arboles(arbBorde, { alto: 8, semilla: 117, especie: 'mixto' }), verdePatio = arboles(arbPatio, { alto: 6.5, semilla: 127, especie: 'mixto' });
  cNueva.add(verdeVia, verdeBorde, verdePatio, palmas(arbBorde.filter((_, i) => i % 4 === 1).map(([x, y]) => [x + 3, y + 2]).filter((p) => fuera(p, 2) && enLote(p)), { alto: 10, semilla: 131 }));
  cNueva.add(postes(luzVia, 6), carros(parqueados, { semilla: 17 }));
  const paseantes = [];
  if (anillo) aLoLargo(anillo.linea, 17, -sA * 10.2, 7).forEach(([x, y, a], k) => { if (k % 2 === 0) paseantes.push([x, y, a + (k % 4 ? 0 : Math.PI)]); });
  cNueva.add(gente(paseantes, { semilla: 37 }));
  esc.linea([...lote, lote[0]].map(([x, y]) => [x, y, 1.2]), { color, ancho: 3, punteada: true, padre: cNueva });
  const nViv = cap.componentes?.find((c) => c.id === 'nuevas')?.unidades || 300, ha = area(lote) / 10000;
  esc.etiqueta(`<b>Barrio nuevo · ${nViv.toLocaleString('es-CO')} apartamentos en ${med.length || 25} bloques</b><small>lote indicativo de ${ha.toLocaleString('es-CO', { maximumFractionDigits: 0 })} ha · ubicación por definir</small>`, { pos: [lx, Math.max(...lote.map((q) => q[1])) + 8, 34], padre: cNueva, color: `var(${color})`, ancla: [0.5, 1], punto: [lx, ly, 10] });
  // ---- el bloque cortado (paso del apartamento tipo): el de la hilera interior más cercano al sur del parque
  const iCorte = med.length ? med.map((b, i) => ({ i, d: Math.hypot(b.x - pc[0], b.y - (pc[1] - 54)) })).sort((a, b) => a.d - b.d)[0].i : -1;
  const bC = med[iCorte];
  if (bC) {
    cBloque.add(bloqueCortado(bC));
    const H3 = 2 * PISO + 1.2, apto = aMundo(bC, 6.4, 3.2), esca = aMundo(bC, 0, 6.6), otro = aMundo(bC, -6.4, -3.2);
    esc.etiqueta('<b>Apartamento tipo · 54,04 m²</b><small>2 alcobas · baño · sala-comedor · cocina · ropas · balcón</small>', { pos: [apto[0], apto[1], 15], padre: cBloque, color: `var(${color})`, ancla: [0.5, 1], punto: [apto[0], apto[1], H3] });
    esc.etiqueta('<b>Escalera central acristalada</b><small>da a los 4 apartamentos de cada piso</small>', { pos: [esca[0], esca[1], 12.5], padre: cBloque, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], punto: [esca[0], esca[1], H3] });
    esc.etiqueta('<b>3 pisos · 12 apartamentos</b><small>piso 3 en corte: 4 apartamentos por piso</small>', { pos: [otro[0], otro[1], 14], padre: cBloque, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], punto: [otro[0], otro[1], H3] });
  }
  // ---- rótulos del urbanismo del barrio (paso «barrio»)
  piezasParque.forEach(([html, [x, y, h]]) => esc.etiqueta(html, { pos: [x, y, h + 6], padre: cParque, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], punto: [x, y, h] }));
  esc.etiqueta('<b>Letrero de bienvenida</b><small>nombre ilustrativo: se escoge entre seis</small>', { pos: [fLet.x, fLet.y, 9], padre: cParque, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], punto: [fLet.x, fLet.y, 3] });
  if (anillo) {
    const este = Math.max(...anillo.esquinas.map((p) => p[0])), pB = [este + 6.2, pc[1] + 42];   // una bahía del costado de la entrada
    esc.etiqueta('<b>Parqueaderos en bahía</b><small>sobre la vía interna, con árboles y alumbrado</small>', { pos: [pB[0], pB[1], 7], padre: cParque, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], punto: [pB[0], pB[1], 1] });
  }
  // las ventanas de los bloques se encienden al atardecer
  esc.alHora?.((Hh) => { const m = blq.userData.ventanas; if (m) m.emissiveIntensity = 0.85 * Hh.encendido; esc.st.invalidate(); });
  // el bloque del paso del apartamento tipo se ve cortado: se saca su instancia (y se cierra cualquier animación de los
  // bloques, que la devolvería a su sitio). `cortado` lo recuerda para que una animación que empiece después (`animar`
  // con la pieza «bloque» a la vista) no vuelva a poner el bloque entero encima del cortado
  let animados = [], cortado = false;
  const verCorte = (v) => {
    if (iCorte < 0) return;
    cortado = !!v;
    if (v) { animados.forEach((a) => a?.progress(1).kill()); animados = []; }
    blq.userData.ocultar(iCorte, cortado); esc.st.updateShadows(); esc.st.invalidate();
  };
  const sinCortado = () => { if (cortado) blq.userData.ocultar(iCorte, true); };

  // mejoramientos: techos naranja sobre casas reales de los barrios con más carencias (casas pequeñas en la periferia)
  const metaMej = cap.componentes?.find((c) => c.id === 'mejoramientos')?.unidades || 400;
  await esc.listoHuellas;
  const zonas = S('barrio_mejoramiento').map((s) => s.poligono), r = azar(7);
  const candidatas = esc.huellas.filter((h) => !h.zona && h.area < 140 && !dentro([h.cx, h.cy], lote) && (zonas.length ? zonas.some((z) => dentro([h.cx, h.cy], z)) : Math.hypot(h.cx - 60, h.cy - 120) > 280));
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
  // vivienda rural: está dispersa en 60 veredas; se muestra el prototipo de la Empresa de Vivienda de Antioquia (50–60 m²,
  // un piso, saneamiento propio y solar) en cinco fincas junto a la vía que va al acueducto, como muestra
  const via = trazado(datos, 'aguas', 'conduccion')?.puntos || [[-2356, 518], [-1500, 200], [-280, -4]];
  const enVia = (f) => { let L = 0; const seg = via.slice(1).map((b, i) => { const a = via[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]); L += l; return { a, b, l }; }); let t = f * L; for (const q of seg) { if (t <= q.l) { const k = t / q.l, ang = Math.atan2(q.b[1] - q.a[1], q.b[0] - q.a[0]); return { x: q.a[0] + (q.b[0] - q.a[0]) * k, y: q.a[1] + (q.b[1] - q.a[1]) * k, ang }; } t -= q.l; } const u = seg[seg.length - 1]; return { x: u.b[0], y: u.b[1], ang: 0 }; };
  const fincas = [0.44, 0.4475, 0.455, 0.4625, 0.47].map((f, i) => { const q = enVia(f), lado = i % 2 ? 1 : -1; return { x: q.x - Math.sin(q.ang) * 20 * lado, y: q.y + Math.cos(q.ang) * 20 * lado, ang: q.ang, lado }; });
  // sin árboles del contexto encima de las fincas de muestra; cada casa con el corredor (frente, +z local) hacia la vía
  esc.despejar?.(fincas.map((f) => [f.x, f.y]), 16);
  fincas.forEach((f, i) => { const g = casaRural(201 + i * 17); g.position.copy(V3(f.x, f.y)); g.rotation.y = f.ang + (f.lado > 0 ? 0 : Math.PI); cRural.add(g); });
  cRural.add(gente(fincas.slice(0, 4).map((f, i) => [f.x + Math.cos(f.ang) * 3 - Math.sin(f.ang) * 5 * -f.lado, f.y + Math.sin(f.ang) * 3 + Math.cos(f.ang) * 5 * -f.lado, f.ang + i]), { semilla: 41 }));
  // el rótulo, encima de la casa más al norte (detrás de las demás en la vista), para no tapar ninguna
  const f0 = fincas.reduce((a, f) => (f.y > a.y ? f : a), fincas[0]);
  esc.etiqueta('<b>Casa rural tipo · 50–60 m²</b><small>prototipo de la Empresa de Vivienda de Antioquia · un piso · solar</small>', { pos: [f0.x, f0.y, 22], padre: cRural, color: `var(${color})`, ancla: [0.5, 1], punto: [f0.x, f0.y, 4] });
  esc.etiqueta('<b>200 casas rurales nuevas</b><small>en el lote de cada familia, en 60 veredas (muestra)</small>', { pos: [fincas[4].x, fincas[4].y, 10], padre: cRural, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0, 0.5] });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const vistaNueva = () => esc.encuadrar(lote, { rumbo: 118, elev: 34, margen: 1.0, alto: 12 });
  const cajaCorte = bC ? [[-11.5, -7.5], [11.5, -7.5], [11.5, 8.5], [-11.5, 8.5]].map(([u, v]) => aMundo(bC, u, v)) : caja([pc], 30);
  const vistaBloque = () => esc.encuadrar(cajaCorte.map(([x, y]) => [x, y, 0]), { rumbo: bC ? rumboFrente(bC.rot) + 28 : 200, elev: 56, margen: 0.86, alto: 9, minDist: 30 });
  const vistaBarrio = () => esc.encuadrar(pq ? [...caja(pq, 8), [fLet.x, fLet.y]] : lote, { rumbo: 100, elev: 40, margen: 0.92, alto: 8 });
  const vistaCasco = () => esc.encuadrar([[-650, -420], [880, -420], [880, 760], [-650, 760], ...lote, [-1450, 80]], { rumbo: 196, elev: 50, margen: 0.94 });
  const vistaRural = () => esc.encuadrar(caja(fincas.map((f) => [f.x, f.y]), 15), { rumbo: 200, elev: 34, margen: 0.9, alto: 8 });
  const vistaMej = () => esc.encuadrar(foco.length ? caja(foco, 40) : caja([cf], 200), { rumbo: 196, elev: 52, margen: 0.9 });
  const gris = (v) => esc.contextoGris?.(v);
  const animNueva = () => {
    // brotar toma la primera vez la posición de cada bloque como base: el cortado va entero a ese momento y se vuelve a
    // sacar en cada cuadro (sinCortado)
    if (cortado) blq.userData.ocultar(iCorte, false);
    animados = [brotar(blq, { duracion: 1.8, retraso: 0.6, onUpdate: () => { sinCortado(); inv(); }, alFinal: () => { sinCortado(); esc.st.updateShadows(); } }),
      ...[verdeVia, verdeBorde, verdePatio, ...(verdeParque || [])].map((v) => brotar(v, { duracion: 1.6, retraso: 1.4, onUpdate: inv }))];
    sinCortado();
  };
  const antes = (enGris, corte = false) => () => { gris(enGris); verCorte(corte); };
  return {
    completo: ['viv.nueva', 'viv.mejoramiento'],
    salir: antes(false),
    alCompleto: antes(false),
    // estados que una pieza del catálogo puede pedir (visual.js): las cubiertas del pueblo en gris, para que se lean los
    // techos a mejorar, y el bloque del apartamento tipo cortado en el piso 3 (con la capa viv.bloque)
    efectos: { gris, corte: verCorte },
    pasos: {
      portadilla: { capas: [], antes: antes(false), vista: vistaCasco },
      componentes: { capas: ['viv.nueva', 'viv.mejoramiento'], antes: antes(true), vista: vistaCasco },
      nuevas: { capas: ['viv.nueva'], antes: antes(false), vista: vistaNueva, animar: animNueva, etiquetas: ['viv.nueva'] },
      apartamento: { capas: ['viv.nueva', 'viv.bloque'], antes: antes(false, true), vista: vistaBloque, etiquetas: ['viv.bloque'] },
      barrio: { capas: ['viv.nueva', 'viv.parque'], antes: antes(false), vista: vistaBarrio, etiquetas: ['viv.parque'] },
      mejoramientos: { capas: ['viv.mejoramiento'], antes: antes(true), vista: vistaMej, animar: () => { if (gsap) gsap.fromTo(matMej, { opacity: 0 }, { opacity: 1, duration: 1, delay: 0.6, onUpdate: inv }); } },
      rural: { capas: ['viv.rural'], antes: antes(false), vista: vistaRural, etiquetas: ['viv.rural'] },
      '*': { capas: ['viv.nueva', 'viv.mejoramiento'], antes: antes(true), vista: vistaCasco },
    },
  };
}
