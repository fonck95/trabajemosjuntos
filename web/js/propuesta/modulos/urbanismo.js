// Urbanismo: la ciudadela deportiva ecológica que une el caño colector Shell (parque lineal renaturalizado), la Cancha de
// Sóftbol Casabe renovada, la alameda por las calles que ya existen, el coliseo Benito Arias, el Parque Educativo, el
// parque principal, la cancha y canchas cubiertas junto al CIC; y, junto al puente sobre el Magdalena, el Mirador Puerta
// del Magdalena con la protección de la orilla. Las posiciones salen de data/propuesta/geo.json (urbanismo); si falta
// algo, se usan las del levantamiento.
import { THREE } from '../../core.js';
import { CALLES } from '../../data.js';
import { cinta, losa, arboles, postes, aLoLargo, crecer, brotar, revelar, dentro, unir } from '../geo3d.js';
import { canchaSoftbol } from '../piezas/softbol.js';
import { miradorMagdalena } from '../piezas/mirador.js';
import { parqueLineal } from '../piezas/cano.js';
import { sitio, sitios, trazado, trazados, caja } from './comun.js';

// levantamiento (OpenStreetMap, huellas e imagen satelital de referencia): lo reemplaza geo.json
const BASE = {
  softbol: { home: [-47.7, 88.8], rumbo: 346.5 },
  alameda: [[-42.5, 55.2], [-30.7, 58.7], [18.2, 75], [63.6, 88.3], [71.7, 90.2], [86.6, 29.1], [101.1, -37.4], [151, -26.7], [182.4, -20], [168.7, 48.3], [209, 57.6], [209, 96.4]],
  mirador: { origen: [1536.4, 7915.9], angulo: 138.7 },
  ciudadela: [[-215, -45], [-120, -70], [60, -80], [285, -35], [300, 40], [225, 140], [40, 205], [-130, 190], [-215, 150]],
  explanada: [[-318, 62], [-243, 64], [-240, 116], [-318, 118]],
  hitos: { coliseo: [141, 0], parque_edu: [151, -41], parque_principal: [209, 96], cancha: [242, 3], cic: [-282, 140] },
};

// eje del caño colector Shell (OpenStreetMap) si geo.json no trae el de la fase 1
function ejeCano(y0 = -100, y1 = 410) {
  const tramos = CALLES.canos.filter((c) => c.nombre === 'Caño Colector Shell').map((c) => c.p);
  const pts = tramos.flat().filter(([, y]) => y >= y0 && y <= y1).sort((a, b) => a[1] - b[1]);
  return pts.filter((p, i) => !i || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1);
}
// distancia de un punto a un polígono (0 si está dentro)
function distPoligono(p, poly) {
  if (dentro(p, poly)) return 0;
  let d = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [a, b] = [poly[j], poly[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    d = Math.min(d, Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy));
  }
  return d;
}

// cubierta para dos canchas múltiples (arco rebajado sobre columnas) y skatepark, sobre la explanada al sur del CIC
function instalacionesCIC(poly) {
  const raiz = new THREE.Group(), [a, b] = [poly[0], poly[1]], ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]), cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const piso = capa('piso'), obras = capa('obras'), cubierta = capa('cubierta');
  const M = {
    losa: new THREE.MeshStandardMaterial({ color: 0xc9c3b6, roughness: 0.95 }), cancha: new THREE.MeshStandardMaterial({ color: 0x2f6fb3, roughness: 0.7 }), cancha2: new THREE.MeshStandardMaterial({ color: 0x2f8f6a, roughness: 0.7 }),
    cal: new THREE.MeshBasicMaterial({ color: 0xffffff }), columna: new THREE.MeshStandardMaterial({ color: 0x9aa3aa, roughness: 0.5, metalness: 0.5 }),
    techo: new THREE.MeshStandardMaterial({ color: 0xe9ecee, roughness: 0.45, metalness: 0.3, side: THREE.DoubleSide }), skate: new THREE.MeshStandardMaterial({ color: 0xb8b4ab, roughness: 0.8 }),
  };
  piso.add(new THREE.Mesh(losa(poly, 0.07), M.losa));
  const g = new THREE.Group(); g.position.set(cx - 11, 0, -cy); g.rotation.y = ang; raiz.add(g);
  // dos canchas de 28 × 15 m con sus líneas, bajo una cubierta de 45 × 32 m
  [[-8, M.cancha], [8, M.cancha2]].forEach(([v, m]) => {
    const c = [[-14, v - 7.5], [14, v - 7.5], [14, v + 7.5], [-14, v + 7.5]];
    const o = new THREE.Mesh(losa(c, 0.11), m); o.receiveShadow = true; g.add(o);
    g.add(new THREE.Mesh(unir([cinta([...c, c[0], c[1]], 0.08, 0.13), cinta([[0, v - 7.5], [0, v + 7.5]], 0.08, 0.13), cinta(Array.from({ length: 25 }, (_, i) => [1.8 * Math.cos((i / 24) * 2 * Math.PI), v + 1.8 * Math.sin((i / 24) * 2 * Math.PI)]), 0.08, 0.13)]), M.cal));
  });
  const cols = [];
  for (let u = -22.5; u <= 22.6; u += 7.5) [-16, 16].forEach((v) => cols.push(new THREE.BoxGeometry(0.45, 7, 0.45).translate(u, 3.5, -v)));
  const colsM = new THREE.Mesh(unir(cols), M.columna); colsM.castShadow = true; obras.add(colsM);
  const arco = new THREE.Shape(), n = 24;
  for (let i = 0; i <= n; i++) { const v = -16.4 + (32.8 * i) / n; arco[i ? 'lineTo' : 'moveTo'](v, 7 + 4 * (1 - (v / 16.4) ** 2)); }
  for (let i = n; i >= 0; i--) { const v = -16.4 + (32.8 * i) / n; arco.lineTo(v, 7.25 + 4 * (1 - (v / 16.4) ** 2)); }
  const techo = new THREE.Mesh(new THREE.ExtrudeGeometry(arco, { depth: 46, bevelEnabled: false }).rotateY(Math.PI / 2).translate(-23, 0, 0), M.techo);
  techo.castShadow = true; techo.receiveShadow = true; cubierta.add(techo);
  // skatepark de ≈1.000 m² al oriente de la cubierta: rampas y un cuarto de tubo
  const sk = new THREE.Group(); sk.position.set(36, 0, 0); g.add(sk);
  sk.add(new THREE.Mesh(losa([[-10.5, -20], [10.5, -20], [10.5, 20], [-10.5, 20]], 0.12), M.skate));
  const cuña = (w, l, h) => { const s = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(l, 0), new THREE.Vector2(l, h)]); return new THREE.ExtrudeGeometry(s, { depth: w, bevelEnabled: false }); };
  [[-6, -12, 0], [4, -2, Math.PI], [-5, 9, 0]].forEach(([u, v, r]) => { const m = new THREE.Mesh(cuña(5, 6, 1.4).translate(-3, 0, -2.5).rotateY(r), M.skate); m.position.set(u, 0.1, -v); m.castShadow = true; sk.add(m); });
  const qp = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, 9, 16, 1, true, Math.PI, Math.PI / 2).rotateZ(Math.PI / 2).translate(0, 3, 0), M.skate);
  qp.position.set(6, 0, -15); qp.castShadow = true; sk.add(qp);
  [obras, cubierta].forEach((o) => { o.position.copy(g.position); o.rotation.copy(g.rotation); });
  raiz.userData.partes = { piso, obras, cubierta };
  raiz.userData.centro = [cx, cy];
  return raiz;
}

export async function crear(esc, datos) {
  const G = datos.geo?.urbanismo || {}, color = '--m-urbanismo';
  const S = (id) => sitio(datos, 'urbanismo', id), Tz = (id) => trazado(datos, 'urbanismo', id);
  const sb = S('softbol_home'), mi = S('mirador_origen'), lt = S('letras_yondo');
  const cfgSoft = sb ? { home: [sb.x, sb.y], rumbo: sb.orientacion_grados ?? BASE.softbol.rumbo } : BASE.softbol;
  const cfgMir = {
    origen: mi ? [mi.x, mi.y] : BASE.mirador.origen, angulo: mi?.angulo_orilla ?? BASE.mirador.angulo,
    diseno: { zonaA: S('mirador_zona_a')?.poligono, plaza: S('mirador_zona_b')?.poligono, mirador: S('mirador_elevado')?.poligono, muelle: S('muelle_flotante')?.poligono, letras: lt ? [lt.x, lt.y] : null, deck: Tz('sendero_deck')?.puntos, pasarela: Tz('pasarela_muelle')?.puntos, acceso: Tz('acceso_plaza')?.puntos, orilla: Tz('orilla_2025')?.puntos },
  };
  const ala = Tz('alameda')?.puntos || BASE.alameda, conector = Tz('conector_cic')?.puntos;
  const eje = Tz('parque_lineal_f1')?.puntos || ejeCano();
  const tramos = trazados(datos, 'urbanismo', 'tramo').filter((t) => t.fase === 1 && t.y0 != null).map((t) => ({ y0: t.y0, y1: t.y1, occidente: t.occidente_m, oriente: t.oriente_m }));
  const humedales = sitios(datos, 'urbanismo', 'humedal').filter((s) => s.fase === 1).map((s) => s.poligono);
  const bosques = sitios(datos, 'urbanismo', 'bosque').map((s) => s.poligono);
  const puentes = sitios(datos, 'urbanismo', 'puente').filter((s) => s.fase === 1);
  const ciud = S('ciudadela')?.poligono || BASE.ciudadela, explanada = S('explanada_cic')?.poligono || BASE.explanada;

  // --- hoy (portadilla): el cerramiento del estadio y el caño canalizado, tal como están
  const cHoy = esc.capa('urb.hoy'), cerr = S('softbol_cerramiento')?.poligono;
  if (cerr) {
    esc.linea([...cerr, cerr[0]].map(([x, y]) => [x, y, 1.2]), { color: '--muted', ancho: 2.5, padre: cHoy });
    const [cx, cy] = [cerr.reduce((a, p) => a + p[0], 0) / cerr.length, cerr.reduce((a, p) => a + p[1], 0) / cerr.length];
    esc.etiqueta('<b>Estadio de sóftbol (hoy)</b><small>cerramiento de 1,2 ha</small>', { pos: [cx, cy, 8], padre: cHoy, color: 'var(--muted)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  }
  const ejeHoy = (Tz('cano_eje')?.puntos || ejeCano()).filter(([, y]) => y <= 430);
  if (ejeHoy.length > 1) {
    esc.linea(ejeHoy.map(([x, y]) => [x, y, 1.6]), { color: '--m-aguas', ancho: 3.5, padre: cHoy });
    const [x, y] = ejeHoy[Math.floor(ejeHoy.length * 0.4)];
    esc.etiqueta('<b>Caño Colector Shell (hoy)</b><small>canalizado, de espaldas al barrio</small>', { pos: [x - 12, y, 6], padre: cHoy, color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });
  }

  // --- ciudadela: contorno punteado, la cancha de fútbol y rótulos (encima de lo que nombran) de lo que integra
  const cCiud = esc.capa('urb.ciudadela');
  esc.linea([...ciud, ciud[0]].map(([x, y]) => [x, y, 1.5]), { color, ancho: 3, punteada: true, guion: 10, padre: cCiud });
  const rot = (txt, sub, [x, y], h = 16) => esc.etiqueta(`<b>${txt}</b>${sub ? `<small>${sub}</small>` : ''}`, { pos: [x, y, h], padre: cCiud, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  const futbol = S('cancha_futbol')?.poligono;
  if (futbol) {
    const [a, b, c, d] = futbol, mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2], m0 = mid(a, c);
    const cesped = new THREE.Mesh(losa(futbol, 0.14), new THREE.MeshStandardMaterial({ color: 0x4f9a3d, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }));
    cesped.receiveShadow = true; cCiud.add(cesped);
    const circulo = Array.from({ length: 33 }, (_, i) => [m0[0] + 9.15 * Math.cos((i / 32) * 2 * Math.PI), m0[1] + 9.15 * Math.sin((i / 32) * 2 * Math.PI)]);
    cCiud.add(new THREE.Mesh(unir([cinta([...futbol, a, b], 0.5, 0.2), cinta([mid(a, b), mid(c, d)], 0.5, 0.2), cinta(circulo, 0.45, 0.2)]), new THREE.MeshBasicMaterial({ color: 0xffffff })));
  }
  rot('Coliseo Benito Arias', 'se integra', BASE.hitos.coliseo, 20);
  rot('Parque Educativo', null, BASE.hitos.parque_edu, 12);
  rot('Parque principal', null, BASE.hitos.parque_principal, 10);
  rot('Cancha de fútbol', null, futbol ? [S('cancha_futbol').x, S('cancha_futbol').y] : BASE.hitos.cancha, 6);
  rot('CIC', null, BASE.hitos.cic, 12);

  // --- Cancha de Sóftbol Casabe
  const cSoft = esc.capa('urb.softbol'), soft = canchaSoftbol(cfgSoft);
  cSoft.add(soft);
  // el rótulo, detrás de la cerca del jardín central (no sobre el diamante)
  const [hx, hy] = soft.userData.aModelo(0, 88);
  esc.etiqueta('<b>Cancha de Sóftbol Casabe</b><small>109 × 102,9 m · luz LED · graderías cubiertas</small>', { pos: [hx, hy, 12], padre: cSoft, color: `var(${color})`, ancla: [0.5, 1] });

  // --- parque lineal del caño colector (fase 1: del bosque del sur a la Calle 55)
  const cCano = esc.capa('urb.cano'), pl = parqueLineal(eje, { tramos, humedales, bosques, puentes: puentes.length ? puentes.map((s) => [s.x, s.y]) : undefined });
  cCano.add(pl);
  // el rótulo, al oriente del eje (las sendas van por la orilla occidental); los de los puentes, en su propia capa
  const em = pl.userData.eje[Math.floor(pl.userData.eje.length * 0.62)];
  esc.etiqueta('<b>Parque lineal del caño colector</b><small>cauce vivo · sendero y ciclorruta · laguna y bosque inundable</small>', { pos: [em[0] + 22, em[1], 10], padre: cCano, color: `var(${color})`, ancla: [0, 0.5] });
  const cPP = esc.capa('urb.puentes');
  puentes.forEach((s) => esc.etiqueta(`<b>${s.id.toUpperCase()}</b>`, { pos: [s.x, s.y, 7], padre: cPP, color: '#a8703f', cls: 'lbl-p mini', titulo: s.nombre, ancla: [0.5, 1] }));

  // --- alameda: calle compartida a nivel por las calles existentes (Calle 50, Carrera 54, carriles del coliseo y Calle 49
  // peatonal), con árboles de sombra donde hay espacio (no sobre las casas) y luminarias LED; conector al CIC por el PP2
  await esc.listoHuellas;
  const huellas = esc.huellas.filter((h) => !h.zona);
  const libre = (p, d = 2.2) => huellas.every((h) => Math.abs(h.cx - p[0]) > 40 || Math.abs(h.cy - p[1]) > 40 || distPoligono(p, h.pts) > d);
  const cAla = esc.capa('urb.alameda');
  const pav = new THREE.MeshStandardMaterial({ color: 0xc49a6c, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 });
  const franja = new THREE.MeshStandardMaterial({ color: 0x14a06c, roughness: 0.8, polygonOffset: true, polygonOffsetFactor: -7, polygonOffsetUnits: -7 });
  const pisoAla = new THREE.Mesh(cinta(ala, 7.5, 0.1), pav), lineaAla = new THREE.Mesh(cinta(ala, 1.5, 0.12), franja);
  [pisoAla, lineaAla].forEach((o) => { o.receiveShadow = true; cAla.add(o); });
  esc.tenir(franja, color);
  if (conector) cAla.add(new THREE.Mesh(cinta(conector, 5, 0.1), pav));
  const candidatos = [...aLoLargo(ala, 11, 4.8, 3), ...aLoLargo(ala, 11, -4.8, 8.5), ...(conector ? aLoLargo(conector, 10, 3.6, 4) : [])].map(([x, y]) => [x, y]);
  const arbAla = arboles(candidatos.filter((p) => libre(p)), { alto: 8.5, semilla: 71 });
  cAla.add(arbAla, postes(aLoLargo(ala, 20, 3.9, 10).map(([x, y]) => [x, y]).filter((p) => libre(p, 1)), 4.4));
  const am = ala[Math.floor(ala.length * 0.4)];
  esc.etiqueta('<b>Alameda de la ciudadela</b><small>483 m por calles que ya existen</small>', { pos: [am[0], am[1] + 8, 14], padre: cAla, color: `var(${color})` });

  // --- canchas cubiertas y skatepark en la explanada al sur del CIC
  const cInst = esc.capa('urb.instalaciones'), inst = instalacionesCIC(explanada);
  cInst.add(inst);
  esc.etiqueta('<b>Canchas cubiertas y skatepark</b><small>explanada al sur del CIC · a un puente del estadio</small>', { pos: [...inst.userData.centro, 16], padre: cInst, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0, 1] });

  // --- Mirador Puerta del Magdalena: se arma aparte porque las letras usan una fuente que se descarga, y el capítulo no la
  // espera (el paso del mirador vuelve a encuadrar y anima cuando llega)
  const cMir = esc.capa('urb.mirador');
  const tb = datos.territorio?.puente?.tablero;
  if (tb?.length > 1) esc.etiqueta('<b>Puente Guillermo Gaviria Correa</b><small>a Barrancabermeja</small>', { pos: [(tb[0][0] + tb[1][0]) / 2, (tb[0][1] + tb[1][1]) / 2, 30], padre: cMir, cls: 'lbl-p mini' });
  let mir = null;
  const listoMir = miradorMagdalena(cfgMir).then((m) => {
    mir = m; cMir.add(m);
    const U = m.userData;
    // el mirador va primero: si en el celular no caben todos, es el último que se oculta
    esc.etiqueta('<b>Mirador elevado</b><small>10 × 10 m sobre pilotes</small>', { pos: [...U.mirador, 12], padre: cMir, color: '#a8703f', cls: 'lbl-p mini' });
    esc.etiqueta('<b>Zona A · protección hidráulica</b><small>283 m de orilla: enrocado y vegetación de ribera</small>', { pos: [...U.zonaA, 8], padre: cMir, color: 'var(--m-aguas)', cls: 'lbl-p mini' });
    esc.etiqueta('<b>Zona B · plaza mirador</b><small>letras YONDÓ · jardineras · parqueadero</small>', { pos: [...U.zonaB, 12], padre: cMir, color: `var(${color})`, cls: 'lbl-p mini' });
    esc.etiqueta('<b>Muelle flotante</b><small>lanchas Barrancabermeja–Casabe</small>', { pos: [...U.muelle, 6], padre: cMir, color: '#a8703f', cls: 'lbl-p mini' });
    esc.sincronizarEtiquetas(); esc.st.updateShadows(); esc.st.invalidate();
    return m;
  }).catch((e) => { console.warn('mirador', e); return null; });
  esc.sincronizarEtiquetas();

  // --- vistas y animaciones de cada paso
  const capasTodo = ['urb.ciudadela', 'urb.softbol', 'urb.cano', 'urb.alameda', 'urb.instalaciones'];
  const piezas = capasTodo.slice(1);   // en las vistas de conjunto, solo los rótulos de las cuatro piezas
  const inv = () => esc.st.invalidate();
  const vistaCiud = () => esc.encuadrar([...ciud, ...explanada], { rumbo: 200, elev: 48, margen: 0.8 });
  const vistaSoft = () => esc.encuadrar(soft.userData.contorno, { rumbo: 200, elev: 34, margen: 0.9, alto: 10 });
  const vistaCano = () => esc.encuadrar(caja(pl.userData.eje, 24), { rumbo: 118, elev: 40, margen: 0.94 });
  const vistaAla = () => esc.encuadrar(caja([...ala, ...(conector || [])], 30), { rumbo: 196, elev: 46, margen: 0.94 });
  // la explanada con el puente PP2, que la une con el estadio (con toda la cancha, en el celular la obra quedaba diminuta)
  const pp2 = puentes.find((s) => s.id === 'pp2');
  const vistaInst = () => esc.encuadrar([...explanada, ...(pp2 ? [[pp2.x, pp2.y]] : soft.userData.contorno)], { rumbo: 208, elev: 38, margen: 0.94, alto: 10 });
  // la plaza, el deck, el mirador y el muelle, más las dos puntas de la zona A (la protección de la orilla que abre el paso)
  const encuadrarMir = () => esc.encuadrar(mir ? [...mir.userData.contorno, ...mir.userData.contornoA] : caja([cfgMir.origen], 150), { rumbo: 221, elev: 30, margen: 0.92, alto: 12 });
  const vistaMir = () => { encuadrarMir(); if (!mir) listoMir.then((m) => { if (m && cMir.visible) encuadrarMir(); }); };
  const animSoft = () => {
    const P = soft.userData.partes;
    crecer(P.obras, { duracion: 1.1, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() });
    crecer(P.cubierta, { duracion: 1.0, retraso: 1.2, onUpdate: inv });
    crecer(P.luces, { duracion: 1.2, retraso: 1.4, onUpdate: inv });
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.6, retraso: 1 + i * 0.2, onUpdate: inv }));
  };
  const animCano = () => {
    const P = pl.userData.partes;
    P.cauce.children.forEach((m) => m.isMesh && revelar(m, { duracion: 1.8, retraso: 0.5, onUpdate: inv }));
    P.sendas.children.forEach((m) => m.isMesh && revelar(m, { duracion: 1.8, retraso: 0.9, onUpdate: inv }));
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.8, retraso: 1.2 + i * 0.15, onUpdate: inv }));
    crecer(P.puentes, { duracion: 0.9, retraso: 2, onUpdate: inv });
  };
  const animAla = () => { brotar(arbAla, { duracion: 2, retraso: 0.7, onUpdate: inv }); [pisoAla, lineaAla].forEach((m) => revelar(m, { duracion: 1.6, retraso: 0.5, onUpdate: inv })); };
  const animInst = () => { const P = inst.userData.partes; crecer(P.obras, { duracion: 1, retraso: 0.6, onUpdate: inv }); crecer(P.cubierta, { duracion: 1, retraso: 1.1, onUpdate: inv, alFinal: () => esc.st.updateShadows() }); };
  const animMir = () => {
    if (!mir) { listoMir.then((m) => { if (m && cMir.visible) animMir(); }); return; }
    const P = mir.userData.partes;
    crecer(P.zonaA, { duracion: 1, retraso: 0.8, onUpdate: inv });
    crecer(P.letras, { duracion: 1.1, retraso: 1.3, onUpdate: inv });
    crecer(P.deck, { duracion: 1.1, retraso: 1.6, onUpdate: inv });
    crecer(P.muelle, { duracion: 0.9, retraso: 1.9, onUpdate: inv });
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.4, retraso: 1.2 + i * 0.2, onUpdate: inv }));
  };
  const hoy = (v) => (G.zonas || []).forEach((z) => esc.verHoy(z, v));
  return {
    completo: [...capasTodo, 'urb.mirador'],
    alCompleto: () => hoy(false),
    salir: () => hoy(true),
    pasos: {
      portadilla: { capas: ['urb.ciudadela', 'urb.hoy'], antes: () => hoy(true), vista: vistaCiud },
      componentes: { capas: capasTodo, antes: () => hoy(false), vista: vistaCiud, animar: () => { animSoft(); animCano(); animAla(); animInst(); }, etiquetas: piezas },
      softbol: { capas: capasTodo, antes: () => hoy(false), vista: vistaSoft, animar: animSoft, etiquetas: ['urb.softbol'] },
      cano: { capas: [...capasTodo, 'urb.puentes'], antes: () => hoy(false), vista: vistaCano, animar: animCano, etiquetas: ['urb.cano', 'urb.puentes'] },
      alameda: { capas: capasTodo, antes: () => hoy(false), vista: vistaAla, animar: animAla, etiquetas: ['urb.alameda'] },
      instalaciones: { capas: capasTodo, antes: () => hoy(false), vista: vistaInst, animar: animInst, etiquetas: ['urb.instalaciones'] },
      mirador: { capas: ['urb.mirador'], vista: vistaMir, animar: animMir },
      '*': { capas: [...capasTodo], antes: () => hoy(false), vista: vistaCiud, etiquetas: piezas },
    },
  };
}
