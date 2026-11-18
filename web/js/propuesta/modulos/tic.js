// Infraestructura TIC y energía: el anillo de fibra óptica que une las sedes públicas con el centro de control (CCED) en
// la alcaldía, Zonas Digitales con wifi público en parques y en la ciudadela deportiva, telemetría de las estaciones de
// bombeo y de la PTAR, y la energía de todo eso desde una granja solar CENTRALIZADA (no paneles sobre cada sede): 1,2 MWp
// frente a la subestación de EPM, con un bloque de reserva, más la granja de 997 kWp sobre el relleno clausurado.
import { THREE, gsap, mat } from '../../core.js';
import { RED } from '../../data.js';
import { brotar, aLoLargo, bancas, gente, V } from '../geo3d.js';
import { matT } from '../texturas.js';
import { granjaSolar } from '../piezas/plantas.js';
import { acopio, caja as bloque, cil, ubicar } from '../piezas/relleno.js';
import { RTU } from './saneamiento.js';
import { sitio, sitios, trazado, trazados, caja } from './comun.js';

const GRANJA = [[-1340, -300], [-1150, -300], [-1150, -470], [-1340, -470]];   // respaldo: junto a la subestación probable de EPM
const ZONAS_DIGITALES = [
  { nombre: 'Parque principal', p: [209, 96] }, { nombre: 'Parque Educativo', p: [151, -41] }, { nombre: 'Ciudadela deportiva', p: [-60, 125] },
  { nombre: 'Plaza del concejo', p: [201, 329] }, { nombre: 'Parque lineal del caño', p: [-160, 160] }, { nombre: 'Mirador del Magdalena', p: [1470, 7940] },
];

// el mástil de comunicaciones del CCED, en el lote de la alcaldía (al oriente del edificio, entre sus árboles): metros al
// oriente y al norte del centro de la alcaldía, y su alto. Lo usa también salud.js (el enlace de telesalud llega a él)
export const MASTIL_CCED = { off: [29, -11], alto: 30 };
// de cerca (cámara a menos de CERCA m de lo que mira) la fibra va en postes con cable aéreo; de lejos, la línea animada
const CERCA = 900;
const barraY = new THREE.Vector3(0, 1, 0);
// barra cilíndrica de a a b (puntos de three)
function barra(a, b, r) {
  const d = new THREE.Vector3().subVectors(b, a), L = d.length();
  return new THREE.CylinderGeometry(r, r, L, 5).applyQuaternion(new THREE.Quaternion().setFromUnitVectors(barraY, d.normalize())).translate((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
}
/**
 * Mástil de comunicaciones autosoportado (plantilla local, base en el origen): tres patas que se angostan, anillos y
 * diagonales cada 3 m, tres antenas de panel y dos parabólicas arriba, pararrayos y baliza roja de obstrucción. Materiales:
 * acero, blanco, concreto, baliza. Para ubicarlo: acopio().poner(mastil(alto), x, y, rot).
 */
export function mastil(alto = 30) {
  const T = { acero: [], blanco: [], concreto: [bloque(3.4, 0.3, 3.4)], baliza: [] }, r0 = 1.3, r1 = 0.45;
  const pata = (k, h) => { const a = (k / 3) * Math.PI * 2 + Math.PI / 6, r = r0 + (r1 - r0) * (h / alto); return new THREE.Vector3(r * Math.cos(a), 0.3 + h, r * Math.sin(a)); };
  for (let k = 0; k < 3; k++) T.acero.push(barra(pata(k, 0), pata(k, alto), 0.07));
  for (let h = 0; h < alto; h += 3) for (let k = 0; k < 3; k++) { T.acero.push(barra(pata(k, h + 3 > alto ? alto : h + 3), pata((k + 1) % 3, h + 3 > alto ? alto : h + 3), 0.035)); T.acero.push(barra(pata(k, h), pata((k + 1) % 3, Math.min(alto, h + 3)), 0.03)); }
  for (let k = 0; k < 3; k++) { const a = (k / 3) * Math.PI * 2 + Math.PI / 2; T.blanco.push(new THREE.BoxGeometry(0.12, 1.7, 0.34).translate(0.75, 0, 0).rotateY(-a).translate(0, 0.3 + alto - 1.4, 0)); }
  [0.4, 2.4].forEach((a, k) => T.blanco.push(new THREE.CylinderGeometry(0.5, 0.42, 0.28, 16).rotateZ(Math.PI / 2).translate(0.85, 0, 0).rotateY(a).translate(0, 0.3 + alto - 4 - k * 2.2, 0)));
  T.acero.push(cil(0.03, 2.2, 0, 0.3 + alto, 0, 5));
  T.baliza.push(new THREE.SphereGeometry(0.2, 10, 8).translate(0, 0.3 + alto + 0.25, 0));
  return T;
}
const matMastil = () => ({ acero: mat(new THREE.Color('#b9c0c5'), { roughness: 0.35, metalness: 0.75 }), blanco: mat(new THREE.Color('#f2f2ee'), { roughness: 0.5 }), concreto: matT('concreto'), baliza: new THREE.MeshBasicMaterial({ color: 0xff3b30, toneMapped: false }) });
export { matMastil };

export function crear(esc, datos) {
  const color = '--m-tic';
  const cFib = esc.capa('tic.fibra'), cZd = esc.capa('tic.zonas'), cZd2 = esc.capa('tic.zonas2'), cTel = esc.capa('tic.telemetria'), cSol = esc.capa('tic.granja'), cDet = esc.capa('tic.granja_det'), cViejo = esc.capa('tic.descartado'), cHoy = esc.capa('tic.hoy');
  // fibra: las rutas por las vías entre sedes (las mismas de la red de distribución del atlas) más lo que traiga geo.json
  const rutas = trazados(datos, 'tic', 'fibra').map((t) => t.puntos);
  const tramos = rutas.length ? rutas : (RED?.arbol?.tramos || []).map((t) => t.ruta);
  const fibras = tramos.map((r) => esc.linea(r.map(([x, y]) => [x, y, 2]), { color: '--data', ancho: 3.5, punteada: true, guion: 9, padre: cFib }));
  esc.st.onFrame((dt) => { if (!cFib.visible) return false; fibras.forEach((f) => { f.material.dashOffset -= dt * 22; }); return true; });
  // de cerca, la fibra va como en la calle: postes de concreto cada 40 m al lado de la vía, cruceta, cable aéreo en
  // catenaria y cajas de empalme; de lejos (más de CERCA m) solo la línea animada, que se lee a cualquier distancia
  const postesF = tramos.flatMap((r) => r.length > 1 ? aLoLargo(r, 40, 4.8) : []);
  const fCerca = new THREE.Group(); fCerca.visible = false; cFib.add(fCerca);
  if (postesF.length) {
    const Mf = { poste: matT('concreto', { color: '#d9d5cc' }), herraje: mat(new THREE.Color('#5b6168'), { roughness: 0.5, metalness: 0.6 }) };
    const gp = new THREE.CylinderGeometry(0.1, 0.15, 9, 7).translate(0, 4.5, 0), gc = new THREE.BoxGeometry(1.3, 0.09, 0.09).translate(0, 8.2, 0);
    const P = new THREE.InstancedMesh(gp, Mf.poste, postesF.length), C = new THREE.InstancedMesh(gc, Mf.herraje, postesF.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
    postesF.forEach(([x, y, a], i) => { q.setFromAxisAngle(barraY, a + Math.PI / 2); m4.compose(V(x, y), q, new THREE.Vector3(1, 1, 1)); P.setMatrixAt(i, m4); C.setMatrixAt(i, m4); });
    [P, C].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); fCerca.add(o); });
    // el cable: tramos en catenaria (0,35 m de flecha) entre postes consecutivos de una misma ruta, y una caja de empalme cada ocho postes
    const cab = [], Ae = acopio();
    tramos.forEach((r) => { const ps = r.length > 1 ? aLoLargo(r, 40, 4.8) : []; for (let i = 1; i < ps.length; i++) { const [a, b] = [ps[i - 1], ps[i]]; for (let k = 0; k < 8; k++) { const t0 = k / 8, t1 = (k + 1) / 8, h = (t) => 7.9 - 0.35 * 4 * t * (1 - t); cab.push(a[0] + (b[0] - a[0]) * t0, h(t0), -(a[1] + (b[1] - a[1]) * t0), a[0] + (b[0] - a[0]) * t1, h(t1), -(a[1] + (b[1] - a[1]) * t1)); } if (i % 8 === 4) Ae.put('herraje', bloque(0.22, 0.45, 0.16, (a[0] + b[0]) / 2, 7.0, -(a[1] + b[1]) / 2)); } });
    const gl = new THREE.BufferGeometry(); gl.setAttribute('position', new THREE.Float32BufferAttribute(cab, 3));
    fCerca.add(new THREE.LineSegments(gl, new THREE.LineBasicMaterial({ color: 0x1e2226 })));
    Ae.volcar(fCerca, Mf);
  }
  esc.st.onFrame(() => {
    if (!cFib.visible) return false;
    const v = esc.st.camera.position.distanceTo(esc.st.controls.target) < CERCA;
    if (v === fCerca.visible) return false;
    fCerca.visible = v; return true;
  });
  const alc = esc.edificios.get('alcaldia'), pA = alc ? [alc.e.x, alc.e.y] : [104, -199];
  // CCED: mástil de comunicaciones en el lote de la alcaldía, con su caseta de equipos, y un halo que late en su base
  const pM = [pA[0] + MASTIL_CCED.off[0], pA[1] + MASTIL_CCED.off[1]], Am = acopio();
  Am.poner(mastil(MASTIL_CCED.alto), pM[0], pM[1], 0.3);
  Am.poner({ caseta: [bloque(2.6, 2.4, 2.2, 3.2, 0, 0)], acero: [bloque(2.9, 0.08, 2.5, 3.2, 2.4, 0)] }, pM[0], pM[1], 0.3);
  Am.volcar(cFib, { ...matMastil(), caseta: matT('estuco', { color: '#e9e6de' }) });
  const halos = [];
  const halo = (p, padre, k0 = 4, k1 = 30, tono = 0x6250d6) => { for (let k = 0; k < 2; k++) { const o = new THREE.Mesh(new THREE.RingGeometry(1, 1.12, 48).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: tono, transparent: true, opacity: 0.6, depthWrite: false })); o.position.copy(V(p[0], p[1], 0.5 + k * 0.05)); Object.assign(o.userData, { fase: k / 2, k0, k1 }); padre.add(o); halos.push(o); esc.tenir(o.material, '--data'); } };
  halo(pM, cFib, 4, 34);
  esc.etiqueta('<b>CCED · centro de control</b><small>en la alcaldía</small>', { pos: [pA[0], pA[1], 44], padre: cFib, color: 'var(--data)', ancla: [0.5, 1] });
  // Zonas Digitales: pines de wifi con ondas
  const zd = sitios(datos, 'tic', 'zona_digital'), lista = zd.length ? zd.map((s) => ({ nombre: s.nombre, p: [s.x, s.y] })) : ZONAS_DIGITALES;
  const ondas = [];
  sitios(datos, 'tic', 'zona_digital_f2').forEach((s) => esc.etiqueta('', { pos: [s.x, s.y, 3], padre: cZd2, color: 'var(--muted)', cls: 'lbl-dot', titulo: `${s.nombre}: Zona Digital de la segunda fase` }));
  const corto = (n) => n.split(' (')[0].replace(/ y parque lineal.*$/, '');
  // en cada Zona Digital: poste de 6 m con el punto de acceso y sus antenas, sombrilla de lona con una banca debajo y
  // gente conectada (dos sentados y uno de pie)
  const Az = acopio(), sentados = [], dePie = [], bz = [];
  lista.forEach(({ p }) => {
    Az.put('acero', cil(0.07, 6, p[0] + 2.6, 0, -p[1], 8), cil(0.02, 0.5, p[0] + 2.5, 6, -p[1], 4), cil(0.02, 0.5, p[0] + 2.7, 6, -p[1], 4));
    Az.put('blanco', bloque(0.32, 0.42, 0.16, p[0] + 2.6, 5.3, -p[1] + 0.12));
    Az.put('acero', cil(0.05, 2.6, p[0] - 1, 0, -(p[1] + 1.2), 6));
    Az.put('lona', new THREE.ConeGeometry(2.3, 0.55, 4, 1, true).rotateY(Math.PI / 4).translate(p[0] - 1, 2.85, -(p[1] + 1.2)));
    bz.push([p[0] - 1, p[1] + 1.2, 0]);
    [-0.45, 0.45].forEach((d) => sentados.push(Object.assign([p[0] - 1 + d, p[1] + 1.15, 0], { h: 0.06 })));
    dePie.push([p[0] + 1.4, p[1] - 0.6, 2.2]);
  });
  Az.volcar(cZd, { acero: mat(new THREE.Color('#a9b0b6'), { roughness: 0.35, metalness: 0.7 }), blanco: mat(new THREE.Color('#f4f4f0'), { roughness: 0.4 }), lona: matT('membrana', { color: '#cfc7f2', side: THREE.DoubleSide }) });
  if (bz.length) { cZd.add(bancas(bz)); cZd.add(gente(sentados, { sentado: true, semilla: 41 })); cZd.add(gente(dePie, { semilla: 42 })); }
  lista.forEach(({ nombre, p }) => {
    esc.etiqueta(`<b>ZD · ${corto(nombre)}</b>`, { pos: [p[0], p[1], 14], padre: cZd, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], titulo: `Zona Digital: ${nombre}` });
    for (let k = 0; k < 2; k++) { const o = new THREE.Mesh(new THREE.RingGeometry(10, 11.2, 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x6250d6, transparent: true, opacity: 0.6, depthWrite: false })); o.position.set(p[0], 1 + k * 0.1, -p[1]); o.userData.fase = k / 2; cZd.add(o); ondas.push(o); esc.tenir(o.material, color); }
  });
  esc.st.onFrame((dt, t) => { if (!cZd.visible) return false; ondas.forEach((o) => { const u = ((t * 0.45) + o.userData.fase) % 1; o.scale.setScalar(0.4 + u * 2.4); o.material.opacity = 0.65 * (1 - u); }); return true; });
  // telemetría: puntos del acueducto y del alcantarillado que reportan al CCED (arcos de datos)
  const tel = sitios(datos, 'tic', 'telemetria');
  const puntos = tel.length ? tel.map((s) => ({ nombre: s.nombre, p: [s.x, s.y] })) : ['ptap', 'tanque_elevado', 'captacion', 'hospital'].map((id) => { const it = esc.edificios.get(id); return it ? { nombre: it.e.corto, p: [it.e.x, it.e.y] } : null; }).filter(Boolean);
  const arco = (a, b, h, h0 = 10, h1 = 10) => { const pts = []; for (let i = 0; i <= 40; i++) { const t = i / 40; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, h0 + (h1 - h0) * t + h * 4 * t * (1 - t)]); } return pts; };
  const ptarS = sitio(datos, 'saneamiento', 'ptar');
  if (ptarS?.poligono) esc.linea([...ptarS.poligono, ptarS.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: '--m-saneamiento', ancho: 2.5, punteada: true, guion: 8, padre: cTel });
  // gabinete RTU de cada estación: en el rincón que le deja su lote (RTU de saneamiento.js); en la PTAR, junto al edificio de
  // operación. Losa, gabinete gris con panel solar, mástil con antena omnidireccional y yagui, y un LED verde que parpadea
  const rtuEn = (s) => {
    const id = String(s.id || '');
    if (id === 'tel_ptar' && ptarS) { const a = THREE.MathUtils.degToRad(ptarS.orientacion_grados ?? 0), [u, v] = [66, 8]; return [ptarS.x + u * Math.cos(a) - v * Math.sin(a), ptarS.y + u * Math.sin(a) + v * Math.cos(a)]; }
    const off = id === 'tel_ebar_central' ? RTU.central : /ebar/.test(id) ? RTU.ebar : [0, 0];
    return [s.x + off[0], s.y + off[1]];
  };
  const rtus = tel.length ? tel.map(rtuEn) : puntos.map((x) => x.p), Ar = acopio(), leds = [];
  rtus.forEach(([x, y]) => {
    Ar.put('concreto', bloque(1.4, 0.15, 1.0, x, 0.15, -y));
    Ar.put('gabinete', bloque(0.8, 1.5, 0.45, x, 0.3, -y));
    Ar.put('solar', new THREE.BoxGeometry(0.9, 0.04, 0.6).rotateX(-0.35).translate(x, 2.0, -y));
    Ar.put('acero', cil(0.03, 0.25, x, 1.8, -y, 4), cil(0.045, 6, x + 0.6, 0.3, -y, 6), cil(0.025, 1.3, x + 0.6, 6.3, -y, 5), bloque(1.0, 0.03, 0.03, x + 0.6, 5.4, -y));
    for (let k = 0; k < 4; k++) Ar.put('acero', bloque(0.02, 0.02, 0.36 - k * 0.05, x + 0.25 + k * 0.25, 5.4, -y));
    leds.push(V(x, y, 1.35).add(new THREE.Vector3(0, 0, 0.235)));
  });
  Ar.volcar(cTel, { concreto: matT('concreto'), gabinete: mat(new THREE.Color('#c3c8cc'), { roughness: 0.4, metalness: 0.5 }), solar: mat(new THREE.Color('#1b2944'), { roughness: 0.2, metalness: 0.6 }), acero: mat(new THREE.Color('#a9b0b6'), { roughness: 0.35, metalness: 0.7 }) });
  const matLed = new THREE.MeshBasicMaterial({ color: 0x39ff7a, toneMapped: false });
  const geoLed = new THREE.SphereGeometry(0.05, 8, 6), led = new THREE.InstancedMesh(geoLed, matLed, Math.max(1, leds.length)), m4l = new THREE.Matrix4();
  leds.forEach((p, i) => { m4l.makeTranslation(p.x, p.y, p.z); led.setMatrixAt(i, m4l); }); led.count = leds.length; led.computeBoundingSphere(); cTel.add(led);
  rtus.forEach((p) => halo(p, cTel, 2, 18));
  // el mástil del CCED también en el paso de la telemetría (las estaciones le reportan a él)
  const Am2 = acopio(); Am2.poner(mastil(MASTIL_CCED.alto), pM[0], pM[1], 0.3); Am2.volcar(cTel, matMastil());
  puntos.forEach(({ nombre, p }, i) => { esc.linea(arco(rtus[i] || p, pM, Math.min(260, Math.hypot(p[0] - pA[0], p[1] - pA[1]) * 0.12 + 30), 6.5, MASTIL_CCED.alto - 1), { color: '--data', ancho: 2.5, punteada: true, guion: 12, opacidad: 0.9, padre: cTel }); esc.etiqueta(`<b>${nombre}</b><small>telemetría${/PTAR|central/i.test(nombre) ? ' · obra nueva' : ''}</small>`, { pos: [p[0], p[1], 12], padre: cTel, color: 'var(--data)', cls: 'lbl-p mini', ancla: [0.5, 1] }); });
  // el LED parpadea (encendido 0,25 s de cada 1,2 s) y los halos se abren: solo con la capa a la vista
  let ledOn = true;
  esc.st.onFrame((dt, t) => {
    let n = false;
    if (cTel.visible) { const on = (t % 1.2) < 0.25; if (on !== ledOn) { ledOn = on; matLed.color.setHex(on ? 0x39ff7a : 0x0f3a1f); n = true; } }
    halos.forEach((o) => { let vis = true; for (let k = o.parent; k; k = k.parent) if (!k.visible) { vis = false; break; } if (!vis) return; const u = ((t * 0.45) + o.userData.fase) % 1; o.scale.setScalar(o.userData.k0 + u * (o.userData.k1 - o.userData.k0)); o.material.opacity = 0.6 * (1 - u); n = true; });
    return n;
  });

  // granja solar centralizada + la del relleno (réplica del atlas en modo proyecto)
  const sg = sitio(datos, 'tic', 'granja_solar'), poly = sg?.poligono || GRANJA, kwpMeta = sg?.kwp || 1200;
  const con0 = trazado(datos, 'tic', 'conexion_granja')?.puntos;
  const granja = granjaSolar(poly, { kwp: kwpMeta, salida: con0?.[0] || null }); cSol.add(granja);
  const cx = poly.reduce((a, p) => a + p[0], 0) / poly.length, cy = poly.reduce((a, p) => a + p[1], 0) / poly.length;
  esc.etiqueta(`<b>Granja solar municipal · ${granja.userData.kwp.toLocaleString('es-CO')} kWp</b><small>1,0 MW CA · energía para sedes, acueducto y PTAR desde un solo punto</small>`, { pos: [cx, cy, 16], padre: cSol, color: 'var(--power)', ancla: [0.5, 1] });
  const res = sitio(datos, 'tic', 'granja_reserva'), se = sitio(datos, 'tic', 'subestacion');
  if (res?.poligono) {
    esc.linea([...res.poligono, res.poligono[0]].map(([x, y]) => [x, y, 1]), { color: '#f0a020', ancho: 2.5, punteada: true, guion: 6, padre: cSol });
    const [rx, ry] = [res.poligono.reduce((a, q) => a + q[0], 0) / res.poligono.length, res.poligono.reduce((a, q) => a + q[1], 0) / res.poligono.length];
    esc.etiqueta('<b>Bloque B · reserva</b><small>0,49 ha para ampliar</small>', { pos: [rx, ry, 6], padre: cDet, color: 'var(--power)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  }
  if (se) esc.etiqueta('<b>Subestación Yondó · EPM</b><small>34,5/13,2 kV · conexión de 40 m</small>', { pos: [se.x, se.y, 12], padre: cDet, color: 'var(--power)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  // línea de 13,2 kV: de la subestación elevadora de la granja a la subestación de EPM
  const con = con0 ? [granja.userData.subestacion, ...con0] : null;
  if (con) esc.flujo(con.map(([x, y]) => [x, y, 11]), { color: '#f0a020', potencia: 0.9, max: 30, tam: 1.8, tubo: 0.3, padre: cSol });
  const rel = esc.edificios.get('relleno_parque');
  if (rel) esc.etiqueta('<b>Granja del relleno · 997 kWp</b><small>comunidad energética de estratos 1 y 2</small>', { pos: [rel.e.x, rel.e.y, 36], padre: cSol, color: 'var(--power)', cls: 'lbl-p mini' });
  // modelo descartado: paneles en cada sede (se muestra un momento para compararlo)
  const sedes = [...esc.edificios.values()].filter((it) => it.e.kwp_factible > 0 && !['relleno_parque', 'torre_hospital'].includes(it.e.id));
  sedes.forEach((it) => esc.etiqueta('', { pos: [it.e.x, it.e.y, 14], padre: cViejo, color: 'var(--bad)', cls: 'lbl-dot', titulo: it.e.corto || it.e.nombre || '' }));
  esc.etiqueta(`<b>Modelo descartado</b><small>paneles sobre ${sedes.length} sedes: muchas cubiertas, muchos contratos, poca escala</small>`, { pos: [0, -470, 30], padre: cViejo, color: 'var(--bad)', cls: 'lbl-p alerta', ancla: [0.5, 1] });
  // portadilla: las mismas sedes hoy, en gris (energía a tarifa oficial plena)
  sedes.forEach((it) => esc.etiqueta('', { pos: [it.e.x, it.e.y, 14], padre: cHoy, color: 'var(--muted)', cls: 'lbl-dot', titulo: it.e.corto || it.e.nombre || '' }));
  esc.etiqueta(`<b>${sedes.length} sedes públicas</b><small>energía a tarifa oficial plena</small>`, { pos: [pA[0], pA[1], 30], padre: cHoy, color: 'var(--muted)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  const panelesSedes = (v) => sedes.forEach((it) => esc.modoEdificio(it.e.id, v ? 'proyecto' : 'hoy', ['conexion', 'equipos', 'almacenamiento', 'cubierta_nueva']));
  const verRelleno = (v) => esc.modoEdificio('relleno_parque', v ? 'proyecto' : 'hoy', ['conexion']);
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const vistaCasco = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], [-650, 760]], { rumbo: 196, elev: 52, margen: 0.94 });
  const vistaRed = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], pA, ...puntos.map((x) => x.p)], { rumbo: 196, elev: 52, margen: 0.94 });
  const vistaGranjaLejos = () => esc.encuadrar([...poly, ...(res?.poligono || []), ...(rel ? [[rel.e.x, rel.e.y]] : []), [0, 0]], { rumbo: 200, elev: 46, margen: 0.9 });
  const vistaGranja = () => esc.encuadrar(caja([...poly, ...(res?.poligono || []), ...(se ? [[se.x, se.y]] : [])], 45), { rumbo: 200, elev: 36, margen: 0.86, alto: 6 });
  const vistaTodo = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], [-650, 760], ...poly, ...(se ? [[se.x, se.y]] : [])], { rumbo: 196, elev: 52, margen: 0.94 });
  return {
    completo: ['tic.fibra', 'tic.granja'],
    salir: () => { panelesSedes(false); verRelleno(false); },
    alCompleto: () => { panelesSedes(false); verRelleno(true); },
    // estados que una pieza del catálogo puede pedir (visual.js): el modelo descartado, con paneles en cada sede
    efectos: { paneles_por_sede: panelesSedes },
    pasos: {
      portadilla: { capas: ['tic.hoy'], antes: () => { panelesSedes(false); verRelleno(false); }, vista: vistaCasco },
      fibra: { capas: ['tic.fibra', 'tic.zonas', 'tic.zonas2'], antes: () => panelesSedes(false), vista: vistaCasco },
      telemetria: { capas: ['tic.fibra', 'tic.telemetria'], antes: () => panelesSedes(false), vista: vistaRed },
      descartado: { capas: ['tic.descartado'], antes: () => { panelesSedes(true); verRelleno(false); }, vista: vistaCasco },
      granja: { capas: ['tic.granja', 'tic.granja_det'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaGranja, animar: () => brotar(granja, { duracion: 2.2, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() }) },
      granja_cerca: { capas: ['tic.granja'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaGranjaLejos },
      '*': { capas: ['tic.fibra', 'tic.zonas', 'tic.granja'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaTodo, etiquetas: ['tic.granja'] },
    },
  };
}
