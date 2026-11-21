// Aseo y saneamiento: hoy cuatro estaciones de bombeo vierten ~55 L/s de aguas residuales sin tratar. La propuesta del
// Plan Maestro de alcantarillado: interceptores que siguen los dos caños hasta su unión, al norte del casco, y allí,
// aguas abajo, una PTAR para todo el casco que devuelve el agua tratada al mismo caño (con laguna de pulimento). En aseo,
// un relleno sanitario nuevo en Yondó (vereda Kilómetro Cinco, en el predio que reserva el EOT), con la estación de
// clasificación y aprovechamiento (ECA) y el compostaje en el mismo predio, y el cierre del relleno Las Américas, que se
// vuelve parque ecotecnológico con granja solar.
import { THREE, gsap, mat } from '../../core.js';
import { tubo, revelar, crecer, brotar, largo, puntoEn, losa, cinta, centro, aLoLargo, matas, palmas, gente, bancas, postes, azar, area, V } from '../geo3d.js';
import { matT, matAgua } from '../texturas.js';
import { ptar } from '../piezas/plantas.js';
import { rellenoNuevo, adentro, acopio, cerco, letrero, caja as bloque, cil, ubicar as aLugar } from '../piezas/relleno.js';
import { sitios, sitio, trazado, trazados, caja } from './comun.js';

// respaldo hasta tener el levantamiento: estaciones en el borde bajo del casco, PTAR aguas abajo de la unión de los caños
const EBAR = [
  { id: 'ebar_progreso', nombre: 'Estación de bombeo El Progreso', x: 520, y: 640, ls: 13.52 },
  { id: 'ebar_paraiso', nombre: 'Estación de bombeo El Paraíso', x: -390, y: 430, ls: 16.51 },
  { id: 'ebar_prado', nombre: 'Estación de bombeo El Prado', x: 600, y: -160, ls: 10.62 },
  { id: 'ebar_victoria', nombre: 'Estación de bombeo La Victoria', x: -110, y: -380, ls: 14.69 },
];
const PTAR = { x: -70, y: 1652, rumbo: 90 };
const KM5 = [-3764, -3955];   // centro del predio del relleno nuevo, si geo.json no lo trae
const ARP = [11524, 1926];    // punto de referencia del aeropuerto Yariguíes (AIP), en metros del modelo
// desde dónde miran las vistas que rotulan de lado (grados desde el norte): el plano y los sitios
const R_PLAN = 205, R_SITIOS = 200;
// pantalla chica: la misma consulta de escena.js, donde el reparto aparta los rótulos que caen sobre la obra
const chico = matchMedia('(max-width: 1080px)');
/** Dónde va el gabinete de telemetría (tic.js) en cada estación: metros al oriente y al norte de su centro. */
export const RTU = { ebar: [5.2, -3.0], central: [9, 6] };
// de lejos (más de LEJOS m entre la cámara y lo que mira) los interceptores van también como línea de ancho fijo
const LEJOS = 700;
// los nombres y rótulos que vienen de geo.json se muestran sin siglas: cada sigla, con su nombre completo
const SIGLAS = [[/\bEBAR\b/g, 'estación de bombeo'], [/\bPTAR\b/g, 'planta de tratamiento'], [/\bECA\b/g, 'estación de reciclaje'], [/\bEOT\b/g, 'Esquema de Ordenamiento Territorial']];
const sinSiglas = (s) => { const o = String(s ?? ''), t = SIGLAS.reduce((a, [re, n]) => a.replace(re, n), o); return /^[A-ZÁÉÍÓÚ]/.test(o) ? t.charAt(0).toUpperCase() + t.slice(1) : t; };

// ---------------------------------------------------------------- piezas propias (geometría unida por material)
const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -k });
function materiales() {
  return {
    concreto: matT('concreto'), muro: matT('estuco', { color: '#eee9de' }), zinc: matT('zinc', { color: '#c9cfd3' }), madera: matT('madera', { color: '#9a7a5c' }),
    malla: matT('malla', { color: '#b7bec2' }), poste: matT('concreto', { color: '#d7d3cb' }), roca: matT('roca', { color: '#9c968a' }),
    oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.45 }), acero: mat(new THREE.Color('#7d868d'), { roughness: 0.4, metalness: 0.6 }),
    tablero: mat(new THREE.Color('#c9cdd1'), { roughness: 0.45, metalness: 0.5 }), planta: mat(new THREE.Color('#3f6e4a'), { roughness: 0.55, metalness: 0.2 }),
    vidrio: mat(new THREE.Color('#33434e'), { roughness: 0.08, metalness: 0.7 }), blanco: mat(new THREE.Color('#ecebe5'), { roughness: 0.5 }),
    pasto: matT('cesped', { color: '#c9d79f' }), berma: matT('tierra', { color: '#e0d6bd' }), servidumbre: matT('tierra', { color: '#d6c8a8', ...po(5) }),
    turbia: matAgua('#6d6a3b', { roughness: 0.3, ...po(6) }), espuma: new THREE.MeshBasicMaterial({ color: 0xf4f2ea, transparent: true, opacity: 0.82, depthWrite: false, ...po(8) }),
    pulimento: matAgua('#4d8a7c'), adoquin: matT('adoquin', { color: '#e9e2d6', ...po(6) }), cuneta: matT('concreto', { color: '#bdb9b0', ...po(7) }),
  };
}
// instancia una plantilla ({ material: geometría }) en varios puntos [x, y] del modelo
function instanciar(T, M, puntos, padre) {
  const m4 = new THREE.Matrix4();
  Object.entries(T).forEach(([k, g]) => {
    const im = new THREE.InstancedMesh(g, M[k], puntos.length);
    puntos.forEach(([x, y], i) => { m4.makeTranslation(x, 0, -y); im.setMatrixAt(i, m4); });
    im.castShadow = !M[k].transparent; im.receiveShadow = true; im.computeBoundingSphere(); padre.add(im);
  });
}
// EBAR de barrio: lote de 14 × 10 m con losa, caseta de bombas de pañete y zinc, pozo húmedo circular con tapa de hierro,
// cámara de válvulas, tablero eléctrico con techito, planta de emergencia y cerco de malla con portón al sur. Marco del
// modelo centrado en la estación (x al oriente, y al norte; en three z = −y). El rincón RTU.ebar queda libre
const POZO_EBAR = [3, 1.5];
function plantillaEbar() {
  const A = acopio(), [wx, wy] = POZO_EBAR;
  A.put('concreto', bloque(14, 0.15, 10));
  A.put('muro', bloque(5, 3, 4, -3, 0.15, -1.5));
  A.put('zinc', new THREE.BoxGeometry(5.8, 0.08, 4.8).rotateX(0.1).translate(-3, 3.35, -1.5));
  A.put('madera', bloque(1.0, 2.1, 0.06, -3.4, 0.15, 0.53));
  A.put('oscuro', bloque(0.9, 0.35, 0.05, -1.6, 2.3, 0.53), bloque(0.05, 0.35, 0.9, -5.53, 2.3, -1.5));
  A.put('concreto', cil(1.8, 0.6, wx, 0.15, -wy, 24));
  A.put('oscuro', cil(0.62, 0.05, wx, 0.75, -wy, 16), bloque(0.9, 0.05, 0.7, wx + 0.8, 0.75, -wy + 0.6));
  A.put('concreto', bloque(1.6, 0.3, 1.2, 5.6, 0.15, -wy));
  A.put('oscuro', bloque(1.2, 0.04, 0.9, 5.6, 0.45, -wy));
  A.put('acero', new THREE.CylinderGeometry(0.12, 0.12, 1.2, 8).rotateZ(Math.PI / 2).translate(wx + 2.1, 0.5, -wy));
  A.put('tablero', bloque(1.2, 1.9, 0.5, 1.2, 0.15, 3.0));
  A.put('zinc', bloque(1.5, 0.06, 0.9, 1.2, 2.1, 3.05));
  A.put('oscuro', bloque(0.03, 1.6, 0.03, 1.2, 0.3, 3.26));
  A.put('planta', bloque(2.8, 1.5, 1.2, -3.6, 0.15, 3.0));
  A.put('oscuro', cil(0.06, 0.7, -4.7, 1.65, 3.0, 6), bloque(0.05, 0.8, 0.9, -2.18, 0.5, 3.0));
  cerco(A, [[-7, -5], [7, -5], [7, 5], [-7, 5], [-7, -5]], { alto: 2.2, paso: 2.5, puertas: [[-1, -5]], hueco: 2.2 });
  return A.unidas();
}
// estación de bombeo de llegada: lote de 28 × 20 m con losa, canal de rejillas al sur (por donde entran los
// interceptores), pozo húmedo de 8 m con tapas, casa de bombas, tablero, planta de emergencia y cerco con portón al oriente
const POZO_LLEGADA = [1, 0];
function plantillaLlegada() {
  const A = acopio(), [wx, wy] = POZO_LLEGADA;
  A.put('concreto', bloque(28, 0.15, 20));
  A.put('concreto', bloque(10, 1.1, 0.3, -5, 0.15, 6 - 1.3), bloque(10, 1.1, 0.3, -5, 0.15, 6 + 1.3), bloque(0.3, 1.1, 2.9, -10, 0.15, 6));
  for (let k = 0; k < 13; k++) A.put('oscuro', bloque(0.07, 0.05, 2.4, -9.4 + k * 0.7, 1.22, 6));
  A.put('concreto', cil(4, 1.0, wx, 0.15, -wy, 32));
  A.put('oscuro', cil(1.0, 0.06, wx, 1.15, -wy, 16), bloque(1.2, 0.06, 1.0, wx + 2.0, 1.15, -wy - 1.2), bloque(1.2, 0.06, 1.0, wx - 1.9, 1.15, -wy + 1.4));
  A.put('muro', bloque(9, 4, 6, -7, 0.15, -5));
  A.put('zinc', new THREE.BoxGeometry(9.8, 0.1, 6.8).rotateX(0.1).translate(-7, 4.45, -5));
  A.put('madera', bloque(1.8, 2.6, 0.06, -6, 0.15, -1.97));
  A.put('vidrio', bloque(1.6, 0.9, 0.05, -9.6, 2.0, -1.97), bloque(0.05, 0.9, 1.6, -11.53, 2.0, -5));
  A.put('tablero', bloque(1.8, 2.0, 0.6, 4, 0.15, -7.5));
  A.put('zinc', bloque(2.2, 0.06, 1.1, 4, 2.2, -7.45));
  A.put('planta', bloque(3.4, 1.7, 1.4, 8, 0.15, 6.5));
  A.put('oscuro', cil(0.08, 0.8, 6.6, 1.85, 6.5, 6));
  A.put('acero', new THREE.CylinderGeometry(0.25, 0.25, 7, 10).rotateZ(Math.PI / 2).translate(-2.5, 0.6, -wy));
  cerco(A, [[-14, -10], [14, -10], [14, 10], [-14, 10], [-14, -10]], { alto: 2.4, paso: 3, puertas: [[14, 1.5]], hueco: 2.5 });
  return A.unidas();
}
// la mancha del vertimiento donde la tubería de la estación llega al caño: agua turbia que baja por el cauce (70 m),
// la boca de la tubería en un cabezal de concreto y espuma en anillos y parches sobre la mancha
function vertimiento(A, v, r) {
  const k = v.length > 2 ? 1 : v.length - 1, [x, y] = v[k], [ax, ay] = v[k - 1];
  const llega = Math.atan2(y - ay, x - ax), cauce = v.slice(k);
  let L = 0; const tramo = [cauce[0]];
  for (let i = 1; i < cauce.length && L < 70; i++) { const d = Math.hypot(cauce[i][0] - cauce[i - 1][0], cauce[i][1] - cauce[i - 1][1]), t = Math.min(1, (70 - L) / d); tramo.push([cauce[i - 1][0] + (cauce[i][0] - cauce[i - 1][0]) * t, cauce[i - 1][1] + (cauce[i][1] - cauce[i - 1][1]) * t]); L += d; }
  if (tramo.length > 1) A.put('turbia', cinta(tramo, 4.4, 0.12));
  A.put('turbia', new THREE.CircleGeometry(3.6, 20).rotateX(-Math.PI / 2).translate(x, 0.13, -y));
  [1.4, 2.6, 3.4].forEach((rr) => A.put('espuma', new THREE.RingGeometry(rr - 0.12, rr + 0.12, 28).rotateX(-Math.PI / 2).translate(x, 0.16, -y)));
  for (let i = 0; i < 30; i++) {
    const [px, py] = puntoEn(tramo, r() * 0.9), s = 0.25 + r() * 0.8;
    A.put('espuma', new THREE.CircleGeometry(s, 8).scale(1, 0.6 + r() * 0.5, 1).rotateZ(r() * 3).rotateX(-Math.PI / 2).translate(px + (r() - 0.5) * 2.6, 0.16, -(py + (r() - 0.5) * 2.6)));
  }
  const bx = x - Math.cos(llega) * 3.2, by = y - Math.sin(llega) * 3.2;
  A.put('concreto', aLugar(bloque(0.5, 1.4, 2.4, 0, -0.4, 0), bx, by, llega));
  A.put('oscuro', aLugar(new THREE.CylinderGeometry(0.3, 0.3, 0.9, 12).rotateZ(Math.PI / 2).translate(0.5, 0.25, 0), bx, by, llega));
}

// Rótulos de lado. Con la cámara mirando desde «rumbo», cada lado de la pantalla es una dirección sobre el piso: 'der' e
// 'izq' en horizontal, 'lejos' (arriba en la pantalla) y 'cerca' (abajo). masAlla da el punto de la recta que pasa por p
// en esa dirección, «m» metros más allá del borde del polígono: un rótulo anclado ahí queda junto a la obra sin taparla
const LADO = { der: -90, izq: 90, lejos: 180, cerca: 0 };
function masAlla(p, poly, rumbo, lado, m) {
  const a = ((rumbo + LADO[lado]) * Math.PI) / 180, dx = Math.sin(a), dy = Math.cos(a);
  const s = Math.max(...poly.map((q) => q[0] * dx + q[1] * dy)) - (p[0] * dx + p[1] * dy) + m;
  return [p[0] + dx * s, p[1] + dy * s];
}
// mueve un rótulo ya creado: posición [x, y, h], ancla y punto de su guía (sin punto, la guía va al pie del ancla)
function ubicar(o, [x, y, h = 0], ancla = [0.5, 0.5], punto = null) {
  o.position.copy(V(x, y, h)); o.center.set(ancla[0], ancla[1]);
  if (punto) o.userData.punto = V(punto[0], punto[1], punto[2] || 0); else delete o.userData.punto;
}

export function crear(esc, datos) {
  const color = '--m-saneamiento';
  const eb = sitios(datos, 'saneamiento', 'ebar');
  const ebars = eb.length ? eb.map((s) => ({ id: s.id, nombre: s.nombre, x: s.x, y: s.y, ls: s.caudal_ls ?? EBAR.find((k) => k.id === s.id)?.ls })) : EBAR;
  const sp = sitio(datos, 'saneamiento', 'ptar'), central = sitio(datos, 'saneamiento', 'ebar_central');
  const cfg = sp ? { x: sp.x, y: sp.y, rumbo: sp.orientacion_grados ?? 0 } : PTAR;
  const cHoy = esc.capa('san.hoy'), cEbar = esc.capa('san.ebar'), cCol = esc.capa('san.colectores'), cPtar = esc.capa('san.ptar'), cRel = esc.capa('san.relleno');

  const M = materiales(), r = azar(17);
  // hoy: cada estación vierte sin tratar (flujo café hacia el caño o la ciénaga más cercana) y deja una mancha turbia con
  // espuma donde su tubería llega al cauce
  const vertidos = trazados(datos, 'saneamiento', 'vertimiento'), Av = acopio();
  ebars.forEach((e) => {
    const v = vertidos.find((t) => t.id === `vert_${e.id}`)?.puntos || [[e.x, e.y], [e.x + (e.x > 0 ? 160 : -160), e.y + (e.y > 0 ? 120 : -120)]];
    esc.linea(v.map(([x, y]) => [x, y, 1.2]), { color: '#8a5a2b', ancho: 3, opacidad: 0.85, padre: cHoy });
    esc.flujo(v.map(([x, y]) => [x, y, 1.5]), { color: '#8a5a2b', potencia: Math.min(1, (e.ls || 12) / 16), max: 26, tam: 2.4, tubo: 0.5, padre: cHoy });
    vertimiento(Av, v, r);
    esc.etiqueta(`<b>${sinSiglas(e.nombre)}</b><small>${e.ls ? `${String(e.ls).replace('.', ',')} litros por segundo sin tratar` : 'sin tratamiento'}</small>`, { pos: [e.x, e.y, 14], padre: cHoy, color: 'var(--bad)', cls: 'lbl-p mini alerta' });
  });
  Av.volcar(cHoy, M, { sombra: false });
  // las estaciones: la misma plantilla instanciada en las cuatro (una llamada de dibujo por material)
  instanciar(plantillaEbar(), M, ebars.map((e) => [e.x, e.y]), cEbar);

  // propuesta: interceptores (de cada estación a la estación de bombeo central) e impulsión a la PTAR
  const pP = ptar(cfg.x, cfg.y, cfg.rumbo); cPtar.add(pP);
  const [ex, ey] = pP.userData.entrada, [sx, sy] = pP.userData.salida;
  const pc = central ? [central.x, central.y] : [ex - 140, ey - 60];
  const cols = trazados(datos, 'saneamiento', 'interceptor');
  const lineas = cols.length ? cols.map((t) => t.puntos) : ebars.map((e) => [[e.x, e.y], [(e.x + pc[0]) / 2, (e.y + pc[1]) / 2 + 40], pc]);
  const impulsion = trazado(datos, 'saneamiento', 'impulsion')?.puntos || [pc, [ex, ey]];
  const emisario = trazado(datos, 'saneamiento', 'emisario')?.puntos || [[sx, sy], [sx + 260, sy + 120]];
  const matCol = new THREE.MeshStandardMaterial({ color: 0x0d8f96, roughness: 0.4, metalness: 0.2, emissive: 0x0d8f96, emissiveIntensity: 0.15 });
  esc.tenir(matCol, color, true);
  // los interceptores salen del pozo húmedo de cada estación y van semienterrados (el eje a ras del piso: asoma medio tubo
  // de 1,4 m) sobre una franja de servidumbre de 8 m en tierra removida, con pozos de inspección cada 90 m. La impulsión de
  // la estación de llegada a la PTAR va a la vista, sobre silletas de concreto
  const alPozo = (pts) => { const e = ebars.find((k) => Math.hypot(k.x - pts[0][0], k.y - pts[0][1]) < 3); return e ? [[e.x + POZO_EBAR[0], e.y + POZO_EBAR[1]], ...pts.slice(1)] : pts; };
  const ejes = lineas.map(alPozo), imp = [[pc[0] + POZO_LLEGADA[0], pc[1] + POZO_LLEGADA[1]], ...impulsion.slice(1)];
  const tubos = ejes.map((pts) => { const m = new THREE.Mesh(tubo(pts, 0.7, 0), matCol); m.castShadow = true; m.receiveShadow = true; cCol.add(m); return m; });
  const timp = new THREE.Mesh(tubo(imp, 0.35, 0.95), matCol); timp.castShadow = true; cCol.add(timp); tubos.push(timp);
  const franjas = ejes.map((pts) => { const m = new THREE.Mesh(cinta(pts, 8, 0.06), M.servidumbre); m.receiveShadow = true; cCol.add(m); return m; });
  const Ai = acopio();
  ejes.forEach((pts) => aLoLargo(pts, 90, 0, 45).forEach(([x, y]) => { if (largo(pts) < 60) return; Ai.put('concreto', cil(0.75, 0.9, x, 0, -y, 16)); Ai.put('oscuro', cil(0.42, 0.05, x, 0.9, -y, 14)); }));
  aLoLargo(imp, 6, 0, 3).forEach(([x, y, a]) => Ai.put('concreto', aLugar(bloque(0.5, 0.6, 1.0, 0, 0, 0), x, y, a)));
  Ai.volcar(cCol, M);
  // de lejos el tubo y la franja quedan por debajo de un píxel: los interceptores van además como línea de ancho fijo,
  // que se apaga de cerca (donde ya se ven el tubo y los pozos)
  const lejos = new THREE.Group(); cCol.add(lejos);
  const lineasLejos = ejes.map((pts) => esc.linea(pts.map(([x, y]) => [x, y, 1.0]), { color, ancho: 3.5, padre: lejos }));
  esc.st.onFrame(() => {
    if (!cCol.visible) return false;
    const v = esc.st.camera.position.distanceTo(esc.st.controls.target) > LEJOS;
    if (v === lejos.visible) return false;
    lejos.visible = v; return true;
  });
  ejes.forEach((pts) => esc.flujo(pts.map(([x, y]) => [x, y, 1.2]), { color: '#7a5a3a', potencia: 0.5, max: 18, tam: 1.3, tubo: 0.01, padre: cCol }));
  esc.flujo(imp.map(([x, y]) => [x, y, 1.6]), { color: '#7a5a3a', potencia: 0.9, max: 24, tam: 1.3, tubo: 0.01, padre: cCol });
  esc.linea(imp.map(([x, y]) => [x, y, 1.7]), { color, ancho: 4, punteada: true, guion: 10, padre: cCol });
  esc.flujo(emisario.map(([x, y]) => [x, y, 2]), { color: '#3aa6d9', potencia: 0.9, max: 30, tam: 2, tubo: 0.5, padre: cPtar });
  instanciar(plantillaLlegada(), M, [pc], cCol);
  const lEst = esc.etiqueta('<b>Estación de bombeo de llegada</b><small>recibe los dos interceptores y sube el agua a la planta</small>', { pos: [pc[0], pc[1], 12], padre: cCol, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  // laguna de pulimento al norte de la planta: el caño lleva poco caudal para diluir, así que el agua se pule antes de volver
  const lag = sitio(datos, 'saneamiento', 'ptar_laguna')?.poligono;
  if (lag) {
    // dique con talud exterior empradizado y corona de afirmado; talud interior en enrocado hasta la lámina de agua y
    // matas de juncos en las orillas de los extremos
    const Al = acopio();
    Al.put('pasto', anilloDique(lag, 0.08, adentro(lag, 2), 1.4));
    Al.put('berma', anilloDique(adentro(lag, 2), 1.4, adentro(lag, 3.2), 1.4));
    Al.put('roca', anilloDique(adentro(lag, 3.2), 1.4, adentro(lag, 5.2), 0.4));
    Al.put('pulimento', losa(adentro(lag, 4.0), 0.9));
    Al.volcar(cPtar, M);
    const borde = adentro(lag, 3.9), piedras = aLoLargo([...borde, borde[0]], 1.1), roc = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), M.roca, piedras.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eu = new THREE.Euler();
    piedras.forEach(([x, y], i) => { const s = 0.35 + r() * 0.4; q.setFromEuler(eu.set(r() * 3, r() * 3, r() * 3)); m4.compose(V(x + (r() - 0.5) * 0.8, y + (r() - 0.5) * 0.8, 1.0), q, new THREE.Vector3(s, s * 0.7, s)); roc.setMatrixAt(i, m4); });
    roc.castShadow = true; roc.receiveShadow = true; roc.computeBoundingSphere(); cPtar.add(roc);
    const f = adentro(lag, 5.6), juncos = [];
    f.forEach((p, i) => { const q2 = f[(i + 1) % f.length], L = Math.hypot(q2[0] - p[0], q2[1] - p[1]); if (L > 40) return; for (let t = 0.1; t < 0.95; t += 0.12) juncos.push([p[0] + (q2[0] - p[0]) * t + (r() - 0.5), p[1] + (q2[1] - p[1]) * t + (r() - 0.5)]); });
    if (juncos.length) cPtar.add(matas(juncos, { tipo: 'heliconia', alto: 2.3, semilla: 21 }));
  }
  // la unión de los dos caños: la PTAR va aguas abajo de ella y la descarga vuelve al mismo caño, más abajo
  const union = sitio(datos, 'saneamiento', 'union_canos');
  if (union) esc.etiqueta('<b>Unión de los caños</b><small>Caño Colector Shell y canal oriental</small>', { pos: [union.x, union.y, 4], padre: esc.capa('san.sitios'), color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });   // solo en el paso de la PTAR
  // rótulos fuera de la planta (del lado oriental, lejos del caño) y a lo largo de la descarga, que vuelve al caño
  const pm = pP.userData.aModelo(0, -80);
  const lPtar = esc.etiqueta(`<b>Planta de tratamiento de aguas residuales</b><small>aguas abajo de la unión de los caños · 50 litros por segundo<br>reactor anaerobio y filtro percolador${sp?.area_m2 ? ` · predio de ${(sp.area_m2 / 10000).toLocaleString('es-CO', { maximumFractionDigits: 1 })} ha` : ''}</small>`, { pos: [pm[0], pm[1], 14], padre: cPtar, color: `var(${color})`, ancla: [0.5, 1] });
  const [qx, qy] = puntoEn(emisario, 0.7);
  const lDesc = esc.etiqueta(`<b>Descarga al Caño Colector Shell</b><small>${Math.round(largo(emisario) / 5) * 5} m · el agua tratada vuelve al caño, aguas abajo</small>`, { pos: [qx, qy, 6], padre: cPtar, color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });
  // en el plano del casco (colectores y financiación) la planta queda en el borde de arriba: en escritorio el rótulo de
  // la PTAR va encima de ella (con la laguna y la descarga), el de la estación a su derecha, con una guía, y el de la
  // descarga no va, porque no cabe junto a la planta; de cerca y en el celular, como se crearon
  const cPlanta = centro(pP.userData.contorno), planta = [...pP.userData.contorno, ...(lag || []), ...emisario];
  const rotularPlanta = (plano) => {
    const lado = plano && !chico.matches;
    if (lado) {
      ubicar(lPtar, [...masAlla(cPlanta, planta, R_PLAN, 'lejos', 30), 0], [0.5, 1]);
      ubicar(lEst, [...masAlla(cPlanta, pP.userData.contorno, R_PLAN, 'der', 25), 0], [0, 0.5], [pc[0], pc[1], 4]);
    } else {
      ubicar(lPtar, [pm[0], pm[1], 14], [0.5, 1]);
      ubicar(lEst, [pc[0], pc[1], 12], [0.5, 1]);
    }
    lDesc.userData.ver = !lado; esc.sincronizarEtiquetas();
  };
  // los otros sitios evaluados para la PTAR: A (alternativa), B (hacia el río) y C (cerca de viviendas), descartados
  const cSitios = esc.capa('san.sitios');
  [['ptar_a', '#8a8f94', 'Sitio A · alternativa', 'pegada al casco, en la reserva del<br>Esquema de Ordenamiento Territorial'], ['ptar_b', '#d9363e', 'Sitio B · descartado', 'hacia el río: 911 m de bombeo y emisario'], ['ptar_c', '#d9363e', 'Sitio C · descartado', 'cerca de viviendas de finca'], ['ptar', '#0d8f96', '', '']].forEach(([id, col, t, sub]) => {
    const st = sitio(datos, 'saneamiento', id); if (!st?.poligono) return;
    esc.linea([...st.poligono, st.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: col, ancho: 3, punteada: true, guion: 8, padre: cSitios });
    const [cx, cy] = [st.poligono.reduce((a, q) => a + q[0], 0) / st.poligono.length, st.poligono.reduce((a, q) => a + q[1], 0) / st.poligono.length];
    if (id !== 'ptar') esc.etiqueta(`<b>${t}</b><small>${sub}</small>`, { pos: [cx, cy, 12], padre: cSitios, color: col, cls: 'lbl-p mini' });
  });

  // relleno Las Américas: cierre por partes desde 2028 (las celdas viejas primero) y del frente activo cuando abra el relleno
  // nuevo, en 2030; luego, parque ecotecnológico y granja solar (la réplica del atlas en modo proyecto)
  const rel = esc.edificios.get('relleno_parque'), pR = rel ? [rel.e.x, rel.e.y] : [-2508, 835];
  esc.etiqueta('<b>Relleno Las Américas</b><small>licencia vencida (2023) → cierre desde 2028 y parque ecotecnológico</small>', { pos: [pR[0], pR[1], 40], padre: cRel, color: `var(${color})`, ancla: [0.5, 1] });
  // el piso de la réplica en modo proyecto: las celdas clausuradas quedan en grama (la losa gris del modelo parece obra sin
  // terminar); se devuelve el material original al salir. Encima, en la capa del paso, el parque: cerco, portería y
  // letrero, el circuito con gente a pie y en bicicleta, bancas, luminarias y palmas, chimeneas de venteo y cunetas
  let relVerde = false;
  const grama = matT('cesped', { color: '#cfd9a8' });
  const cubrir = () => rel?.lod?.traverse((o) => {
    if (!o.isMesh) return;
    if (o.material?.name === 'predio' && !o.userData.predio) o.userData.predio = o.material;
    if (o.userData.predio) o.material = relVerde ? grama : o.userData.predio;
  });
  // (la grama solo en el paso del cierre: en las vistas de conjunto y en los otros capítulos la réplica queda como viene)
  const verRelleno = (v, verde = false) => { esc.modoEdificio('relleno_parque', v ? 'proyecto' : 'hoy', ['conexion']); relVerde = !!(v && verde); cubrir(); };
  esc.alCargarEdificio?.('relleno_parque', (it) => { try { cRel.add(parqueAmericas(it.lod, M, r)); } catch (e) { console.warn('parque Las Américas', e); } cubrir(); esc.st.updateShadows(); esc.st.invalidate(); });

  // relleno nuevo en la vereda Kilómetro Cinco, en el predio que reserva el EOT (Tabla 35): celdas por fases, lagunas de
  // lixiviados, ECA y compostaje, portería con báscula y la vía de acceso desde el casco. Los polígonos vienen de geo.json
  const cRN = esc.capa('san.relleno_nuevo'), cSit = esc.capa('san.relleno_sitios'), cVia = esc.capa('san.relleno_via');
  const rn = sitio(datos, 'saneamiento', 'relleno_nuevo');
  const pol = (id) => sitio(datos, 'saneamiento', id)?.poligono || null;
  const serie = (pre) => sitios(datos, 'saneamiento').filter((s) => s.id.startsWith(pre) && s.poligono).map((s) => s.poligono);
  const via = trazado(datos, 'saneamiento', 'via_relleno')?.puntos || null, port = sitio(datos, 'saneamiento', 'relleno_porteria');
  let rnP = null;
  if (rn?.poligono) {
    rnP = rellenoNuevo({
      predio: rn.poligono, celdas: pol('relleno_celda_f1'), futuras: serie('relleno_celdas_futuras'), lixiviados: serie('relleno_lixiviados'), eca: pol('relleno_eca'), compostaje: pol('relleno_compostaje'),
      porteria: port ? [port.x, port.y] : null, entrada: via ? via.slice(-2) : null,
      vias: trazados(datos, 'saneamiento', 'via_interna').map((t) => t.puntos), franja: trazados(datos, 'saneamiento', 'franja_arboles')[0]?.puntos || null,
      monitoreo: sitios(datos, 'saneamiento', 'relleno_monitoreo').map((s) => [s.x, s.y]),
    });
    cRN.add(rnP);
    const U = rnP.userData;
    // rótulos del predio, en el orden en que sus obras quedan de izquierda a derecha en la pantalla: el reparto los aparta
    // arriba o abajo del predio en ese orden, también en escritorio (la vista pide apartar), sin que una guía cruce otra
    // (sinCruces), y oculta los que no caben, primero los últimos. h: altura del rótulo sobre la obra
    const rot = (html, p, h, color) => esc.etiqueta(html, { pos: [...p, h], padre: cRN, color, cls: 'lbl-p mini' });
    if (U.compostaje) rot('<b>Compostaje</b><small>orgánicos separados en la fuente</small>', U.compostaje, 4, '#6f5233');
    if (U.celda) rot('<b>Celda de la fase 1</b><small>tres terrazas de 3 m · geomembrana en la cara activa</small>', U.celda, 14, '#5d6b45');
    if (U.eca) rot('<b>Estación de reciclaje</b><small>clasificación y aprovechamiento</small>', U.eca, 10, `var(${color})`);
    if (U.lixiviados) rot('<b>Lagunas de lixiviados</b>', U.lixiviados, 4, '#55603f');
    if (port) rot('<b>Portería y báscula</b>', [port.x, port.y], 6, '#3f464c');
    // la reserva del EOT (se compra completa: lo que queda fuera del predio sirve de aislamiento y de retiro de la vía) y la
    // planta de tratamiento y disposición de lodos del EOT, vecina por el occidente
    const res = pol('relleno_reserva_eot');
    if (res) esc.linea([...res, res[0]].map(([x, y]) => [x, y, 1.2]), { color, ancho: 2, punteada: true, guion: 6, opacidad: 0.7, padre: cRN });
    const lodos = sitio(datos, 'saneamiento', 'relleno_vecino_lodos');
    if (lodos?.poligono) {
      esc.linea([...lodos.poligono, lodos.poligono[0]].map(([x, y]) => [x, y, 1.2]), { color: '#8a8f94', ancho: 2.5, punteada: true, guion: 8, padre: cRN });
      const [lx, ly] = centro(lodos.poligono);
      esc.etiqueta(`<b>Planta de lodos vecina</b><small>${sinSiglas(lodos.rotulo || 'por el occidente')}</small>`, { pos: [lx, ly, 6], padre: cRN, color: '#8a8f94', cls: 'lbl-p mini' });
    }
    // el contorno y el nombre del predio van con los sitios evaluados: se ven también en la vista de conjunto. El contorno
    // va a 4 m, por encima de la losa del predio aun con la cámara a 30 km; el rótulo, a la derecha del predio
    esc.linea([...rn.poligono, rn.poligono[0]].map(([x, y]) => [x, y, 4]), { color, ancho: 3.5, padre: cSit });
    esc.etiqueta(`<b>Relleno nuevo · Kilómetro Cinco</b><small>predio que reserva el Esquema de Ordenamiento Territorial${rn.area_m2 ? ` · ${(rn.area_m2 / 10000).toLocaleString('es-CO', { maximumFractionDigits: 1 })} ha` : ''}</small>`, { pos: [...masAlla(U.centro, rn.poligono, R_SITIOS, 'der', 200), 0], padre: cSit, color: `var(${color})`, ancla: [0, 0.5] });
  }
  // Las Américas en la vista de los sitios, con su propio rótulo, chico como los de los otros sitios evaluados y debajo
  // del relleno: arriba queda el sitio descartado que lo ampliaba, y el rótulo del paso del cierre lo taparía
  const [hx, hy] = rel?.e?.tamano ? [rel.e.tamano[0] / 2, rel.e.tamano[2] / 2] : [150, 150];
  esc.etiqueta('<b>Relleno Las Américas</b><small>licencia vencida desde 2023</small>', { pos: [...masAlla(pR, caja([[pR[0] - hx, pR[1] - hy], [pR[0] + hx, pR[1] + hy]]), R_SITIOS, 'cerca', 25), 0], padre: cSit, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 0] });
  // los otros sitios evaluados (alternativas en gris, descartado en rojo), con el rótulo al lado para que se vea el
  // contorno: las alternativas a la izquierda (el detalle en dos renglones) y el descartado encima
  [['relleno_alternativa', '#8a8f94', 'izq'], ['relleno_descartado', '#d9363e', 'lejos']].forEach(([rol, col, lado]) => sitios(datos, 'saneamiento', rol).forEach((s) => {
    if (!s.poligono) return;
    esc.linea([...s.poligono, s.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: col, ancho: 3, punteada: true, guion: 10, padre: cSit });
    esc.etiqueta(`<b>${sinSiglas(s.nombre)}</b>${s.rotulo ? `<small>${sinSiglas(s.rotulo).replace(/ · /g, '<br>')}</small>` : ''}`, { pos: [...masAlla(centro(s.poligono), s.poligono, R_SITIOS, lado, 40), 0], padre: cSit, color: col, cls: 'lbl-p mini', ancla: lado === 'izq' ? [1, 0.5] : [0.5, 1] });
  }));
  // la basura viaja por la vía al relleno nuevo (camión de la ruta: flujo café)
  if (via) {
    const m = new THREE.MeshStandardMaterial({ color: 0xa8997f, roughness: 1, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
    const cinta6 = new THREE.Mesh(cinta(via, 6, 0.16), m); cinta6.receiveShadow = true; cVia.add(cinta6);
    // de lejos la cinta de 6 m queda por debajo de un píxel: la vía va también como línea de ancho fijo, dibujada encima
    // de todo, porque las vías del territorio, casi a ras del piso, se adelantan en profundidad y la tapaban. Llega hasta
    // el empalme con la entrada, fuera del predio, para no pasar por encima de los árboles; su color (--basura, el mismo de
    // la leyenda) es más claro en el tema oscuro
    const lVia = esc.linea(via.slice(0, -1).map(([x, y]) => [x, y, 2]), { color: '--basura', ancho: 3, padre: cVia });
    lVia.material.depthTest = false; lVia.renderOrder = -1;   // los contornos de los sitios van encima de ella
    esc.flujo(via.map(([x, y]) => [x, y, 3]), { color: '#6f5233', potencia: 0.6, max: 30, tam: 5, tubo: 0.01, padre: cVia });
    // el rótulo, a la izquierda de la vía (a la derecha pasa el radio del aeropuerto), en el último tramo en que baja
    // derecho en la pantalla, lejos de los rótulos de las alternativas: en las curvas de más arriba el rótulo la taparía
    const pv = puntoEn(via, 0.8), [vx, vy] = masAlla(pv, [pv], R_SITIOS, 'izq', 200);
    esc.etiqueta(`<b>Vía al relleno</b><small>${(Math.round(largo(via) / 100) / 10).toLocaleString('es-CO')} km desde el borde del casco</small>`, { pos: [vx, vy, 0], padre: cVia, color: '#6f5233', cls: 'lbl-p mini', ancla: [1, 0.5] });
  }
  // radio de 13 km del aeropuerto Yariguíes (RAC 14 de la Aerocivil): adentro, un relleno, una planta de tratamiento o una
  // laguna necesitan su autorización previa, que se niega si atraen aves. El casco y la PTAR quedan adentro; Las Américas y
  // Kilómetro Cinco, afuera
  const arco = [];
  for (let a = 140; a <= 225; a += 2) arco.push([ARP[0] + 13000 * Math.cos((a * Math.PI) / 180), ARP[1] + 13000 * Math.sin((a * Math.PI) / 180), 2]);
  esc.linea(arco, { color: '#8e44ad', ancho: 2.5, punteada: true, guion: 30, opacidad: 0.85, padre: cSit });
  // el rótulo va sobre el tramo del arco que cruza el río (a 202°), lejos de la vía y de los sitios, y el detalle en
  // dos renglones para que no sea tan ancho
  esc.etiqueta('<b>13 km del aeropuerto Yariguíes</b><small>adentro, un relleno, una planta de tratamiento<br>o una laguna necesitan autorización de la Aerocivil</small>', { pos: [arco[31][0], arco[31][1], 4], padre: cSit, color: '#8e44ad', cls: 'lbl-p mini' });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const todo = [...ebars.map((e) => [e.x, e.y]), ...pP.userData.contorno];
  const vistaHoy = () => esc.encuadrar(ebars.map((e) => [e.x, e.y]).concat([[0, 0]]), { rumbo: 200, elev: 50, margen: 0.9 });
  // en escritorio el encuadre del plano deja aire encima de la planta, que queda en el borde de arriba, para su rótulo
  const vistaPlan = () => {
    rotularPlanta(true);
    const aire = chico.matches ? [] : [[...masAlla(cPlanta, planta, R_PLAN, 'lejos', 30), 150]];
    return esc.encuadrar([...todo, ...aire], { rumbo: R_PLAN, elev: 46, margen: 0.94 });
  };
  const vistaPtar = () => { rotularPlanta(false); return esc.encuadrar([...caja(pP.userData.contorno, 90), puntoEn(emisario, 0.7).slice(0, 2), ...(union ? [[union.x, union.y]] : [])], { rumbo: 200, elev: 40, margen: 0.9, alto: 10 }); };
  const vistaRel = () => esc.encuadrar(rel ? esc.cajaEdificio('relleno_parque') : caja([pR], 200), { rumbo: 200, elev: 40, margen: 0.85 });
  // los sitios: el casco, Las Américas, el predio del EOT en Kilómetro Cinco y las alternativas
  const ptsSitios = () => [[-650, -420], [700, 760], pR, ...(rn?.poligono || [KM5]), ...sitios(datos, 'saneamiento').filter((s) => /^relleno_(alternativa|descartado)$/.test(s.rol) && s.poligono).flatMap((s) => s.poligono)];
  const vistaSitios = () => esc.encuadrar(ptsSitios(), { rumbo: R_SITIOS, elev: 52, margen: 0.92, sinCruces: true });
  const vistaNuevo = () => esc.encuadrar(rn?.poligono || caja([KM5], 260), { rumbo: 210, elev: 36, margen: 0.9, alto: 12, sinCruces: true, apartar: true });
  const animNuevo = () => {
    if (!rnP) return;
    const P = rnP.userData.partes;
    crecer(P.celdas, { duracion: 1.2, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() });
    P.obras.children.forEach((g, i) => crecer(g, { duracion: 0.8, retraso: 0.9 + i * 0.05, onUpdate: inv }));
    if (P.verde.children[0]) brotar(P.verde.children[0], { duracion: 1.4, retraso: 1, onUpdate: inv });
  };
  return {
    completo: ['san.ebar', 'san.colectores', 'san.ptar', 'san.relleno_nuevo'],
    salir: () => verRelleno(false),
    alCompleto: () => verRelleno(true),
    pasos: {
      portadilla: { capas: ['san.hoy', 'san.ebar'], antes: () => verRelleno(false), vista: vistaHoy },
      colectores: { capas: ['san.hoy', 'san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan, animar: () => { [...tubos, ...franjas].forEach((t, i) => revelar(t, { duracion: 1.6, retraso: 0.4 + (i % tubos.length) * 0.15, onUpdate: inv })); lineasLejos.forEach((l, i) => revelarLinea(l, { duracion: 1.6, retraso: 0.4 + i * 0.15, onUpdate: inv })); } },
      ptar: { capas: ['san.ebar', 'san.colectores', 'san.ptar', 'san.sitios'], antes: () => verRelleno(false), vista: vistaPtar, animar: () => { crecer(pP.userData.partes.obras, { duracion: 1.2, retraso: 0.7, onUpdate: inv, alFinal: () => esc.st.updateShadows() }); brotar(pP.userData.partes.verde.children[0], { duracion: 1.6, retraso: 1, onUpdate: inv }); } },
      relleno_nuevo: { capas: ['san.relleno_sitios', 'san.relleno_via', 'san.relleno_nuevo'], antes: () => verRelleno(false), vista: vistaSitios, etiquetas: ['san.relleno_sitios', 'san.relleno_via'] },
      residuos: { capas: ['san.relleno_nuevo', 'san.relleno_via'], antes: () => verRelleno(false), vista: vistaNuevo, animar: animNuevo, etiquetas: ['san.relleno_nuevo'] },
      relleno: { capas: ['san.relleno'], antes: () => verRelleno(true, true), vista: vistaRel },
      '*': { capas: ['san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan },
    },
  };
}

// anillo de caras entre dos polígonos con los mismos vértices (taludes del dique), con la normal hacia arriba
function anilloDique(a, ha, b, hb) {
  const pos = [], n = a.length, e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, q = [V(a[i][0], a[i][1], ha), V(a[j][0], a[j][1], ha), V(b[j][0], b[j][1], hb), V(b[i][0], b[i][1], hb)];
    e1.subVectors(q[1], q[0]); e2.subVectors(q[2], q[0]);
    (e1.cross(e2).y >= 0 ? [0, 1, 2, 0, 2, 3] : [0, 2, 1, 0, 3, 2]).forEach((k) => pos.push(q[k].x, q[k].y, q[k].z));
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals();
  return g;
}
// dibuja de a poco una línea de ancho fijo (Line2): cuántos segmentos se dibujan
function revelarLinea(l, { duracion = 1.4, retraso = 0, onUpdate } = {}) {
  const g = l.geometry, total = g.attributes.instanceStart?.count || 0;
  if (!gsap || !total) return;
  const o = { u: 0 };
  g.instanceCount = 0;
  gsap.to(o, { u: 1, duration: duracion, ease: 'power2.inOut', delay: retraso, onUpdate: () => { g.instanceCount = Math.floor(total * o.u); onUpdate?.(); }, onComplete: () => { g.instanceCount = Infinity; onUpdate?.(); } });
}

// ---------------------------------------------------------------- parque ecotecnológico Las Américas
// Se arma sobre la réplica del atlas con lo que trae su modelo (en coordenadas del modelo de la maqueta): el contorno del
// predio (cerco, portería y letrero en el lado más cercano al parqueadero), el circuito (los caminos de la obra nueva
// cerca del borde: gente, ciclistas, bancas afuera, luminarias adentro y palmas) y las celdas clausuradas (las zonas de
// grama de la obra nueva: chimeneas de venteo lejos de los paneles y cunetas en su borde)
function parqueAmericas(lod, M, r) {
  const g = new THREE.Group(); g.name = 'parque';
  if (!lod) return g;
  lod.updateMatrixWorld(true);
  const nivel = lod.levels?.[0]?.object || lod, v = new THREE.Vector3(), m4 = new THREE.Matrix4();
  let entorno = null;
  nivel.traverse((o) => { if (o.name === 'obra_nueva_entorno') entorno = o; });
  const dentroDe = (o, p) => { for (let k = o; k; k = k.parent) if (k === p) return true; return false; };
  const T = { predio: [], camino: [], pasto: [], asfalto: [] }, modulos = [];
  nivel.traverse((o) => {
    if (o.isInstancedMesh) {
      if (/modulo/.test(`${o.parent?.name}${o.name}`)) for (let i = 0; i < o.count; i++) { o.getMatrixAt(i, m4); m4.premultiply(o.matrixWorld); v.setFromMatrixPosition(m4); modulos.push([v.x, -v.z]); }
      return;
    }
    if (!o.isMesh) return;
    const n = o.userData.predio ? 'predio' : o.material?.name, de = entorno && dentroDe(o, entorno);
    const k = n === 'predio' ? 'predio' : !de ? null : n === 'piso' ? 'camino' : n === 'pasto' ? 'pasto' : n === 'asfalto' ? 'asfalto' : null;
    if (!k) return;
    const pos = o.geometry.attributes.position, idx = o.geometry.index, cnt = idx ? idx.count : pos.count;
    const P = (i) => { v.fromBufferAttribute(pos, idx ? idx.getX(i) : i).applyMatrix4(o.matrixWorld); return [v.x, -v.z]; };
    for (let t = 0; t < cnt; t += 3) T[k].push([P(t), P(t + 1), P(t + 2)]);
  });
  const pts = T.predio.flat();
  if (pts.length < 3) return g;
  const borde = envolvente(pts), [cx, cy] = centro(borde), Lb = [...borde, borde[0]];
  const alBorde = (p) => { let d = Infinity; for (let i = 1; i < Lb.length; i++) d = Math.min(d, distSeg(p, Lb[i - 1], Lb[i])); return d; };
  // el circuito: puntos al azar sobre los caminos que corren cerca del borde, con el rumbo del lado más largo de su triángulo
  const circuito = [];
  T.camino.forEach((t) => {
    const c = [(t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3];
    if (alBorde(c) > 34) return;
    const a = area(t), lados = [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]].sort((p, q) => Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) - Math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]));
    const dir = Math.atan2(lados[0][1][1] - lados[0][0][1], lados[0][1][0] - lados[0][0][0]);
    for (let k = 0; k < Math.max(a > 2 ? 1 : 0, Math.round(a / 10)); k++) {
      let u = r(), w = r(); if (u + w > 1) { u = 1 - u; w = 1 - w; }
      circuito.push([t[0][0] + (t[1][0] - t[0][0]) * u + (t[2][0] - t[0][0]) * w, t[0][1] + (t[1][1] - t[0][1]) * u + (t[2][1] - t[0][1]) * w, dir]);
    }
  });
  const ralo = (lista, sep) => { const out = []; lista.forEach((p) => { if (out.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) >= sep)) out.push(p); }); return out; };
  const afuera = ([x, y, a]) => { const nx = -Math.sin(a), ny = Math.cos(a), s = nx * (x - cx) + ny * (y - cy) > 0 ? 1 : -1; return [nx * s, ny * s]; };
  const A = acopio();
  if (circuito.length) {
    const caminantes = ralo(circuito, 13).map(([x, y, a], i) => Object.assign([x, y, a + (i % 2 ? Math.PI : 0)], { h: 0.14 }));
    g.add(gente(caminantes, { semilla: 31 }));
    const bicis = ralo(circuito, 75).slice(0, 8);
    g.add(gente(bicis.map(([x, y, a]) => Object.assign([x, y, a - Math.PI / 2], { h: 0.62 })), { sentado: true, semilla: 32 }));
    bicis.forEach(([x, y, a]) => {
      [-0.55, 0.55].forEach((d) => A.put('oscuro', aLugar(new THREE.TorusGeometry(0.33, 0.035, 6, 16).translate(d, 0.33, 0), x, y, a, 0.14)));
      A.put('rojo', aLugar(bloque(1.1, 0.05, 0.05, 0, 0.62, 0), x, y, a, 0.14), aLugar(new THREE.BoxGeometry(0.05, 0.6, 0.05).rotateZ(0.3).translate(-0.1, 0.62, 0), x, y, a, 0.14));
    });
    bancasDe(g, ralo(circuito, 46).map((p) => { const [ox, oy] = afuera(p); return [p[0] + ox * 3.4, p[1] + oy * 3.4, Math.atan2(-oy, -ox) + Math.PI / 2]; }));
    g.add(postes(ralo(circuito, 34).map((p) => { const [ox, oy] = afuera(p); return [p[0] - ox * 2.8, p[1] - oy * 2.8]; }), 4.5));
    g.add(palmas(ralo(circuito, 27).map((p) => { const [ox, oy] = afuera(p); return [p[0] + ox * 6.5, p[1] + oy * 6.5]; }), { alto: 8, semilla: 33 }));
  }
  // celdas clausuradas: chimeneas de venteo (lejos de los paneles) y cunetas de concreto en el borde de la grama
  const cerca = new Map(), celda = (x, y) => `${Math.floor(x / 10)}|${Math.floor(y / 10)}`;
  modulos.forEach(([x, y]) => { const k = celda(x, y); if (!cerca.has(k)) cerca.set(k, []); cerca.get(k).push([x, y]); });
  const libre = ([x, y]) => { for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const [mx, my] of cerca.get(`${Math.floor(x / 10) + i}|${Math.floor(y / 10) + j}`) || []) if (Math.hypot(mx - x, my - y) < 6) return false; return true; };
  const enGrama = [];
  T.pasto.forEach((t) => { for (let k = 0; k < Math.round(area(t) / 120); k++) { let u = r(), w = r(); if (u + w > 1) { u = 1 - u; w = 1 - w; } enGrama.push([t[0][0] + (t[1][0] - t[0][0]) * u + (t[2][0] - t[0][0]) * w, t[0][1] + (t[1][1] - t[0][1]) * u + (t[2][1] - t[0][1]) * w]); } });
  ralo(enGrama.filter(libre), 24).forEach(([x, y]) => { A.put('concreto', cil(0.55, 0.3, x, 0.05, -y, 10)); A.put('blanco', cil(0.11, 2.1, x, 0.05, -y, 8), new THREE.TorusGeometry(0.22, 0.09, 6, 10, Math.PI).translate(x - 0.22, 2.15, -y)); });
  const aristas = new Map(), clave = (p) => `${p[0].toFixed(1)}|${p[1].toFixed(1)}`;
  T.pasto.forEach((t) => [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]].forEach(([a, b]) => { const k = [clave(a), clave(b)].sort().join('/'); aristas.set(k, aristas.has(k) ? null : [a, b]); }));
  aristas.forEach((e) => { if (e && Math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]) > 0.5) A.put('cuneta', cinta(e, 0.5, 0.1)); });
  // cerco con el portón en el lado más cercano al parqueadero, la portería adentro y el letrero afuera, de frente a quien llega
  const pq = T.asfalto.length ? centro(T.asfalto.flat()) : [cx - 1e4, cy];
  let gate = null, mejor = Infinity, lado = 0;
  for (let i = 1; i < Lb.length; i++) { const p = proySeg(pq, Lb[i - 1], Lb[i]), d = Math.hypot(p[0] - pq[0], p[1] - pq[1]); if (d < mejor) { mejor = d; gate = p; lado = i; } }
  cerco(A, Lb, { alto: 2.0, paso: 3, puertas: [gate], hueco: 4 });
  const [ax, ay] = Lb[lado - 1], [bx, by] = Lb[lado], tl = Math.hypot(bx - ax, by - ay) || 1, tx = (bx - ax) / tl, ty = (by - ay) / tl;
  let nx = -ty, ny = tx; if (nx * (gate[0] - cx) + ny * (gate[1] - cy) < 0) { nx = -nx; ny = -ny; }
  A.put('concreto', bloque(0.4, 2.6, 0.4, gate[0] + tx * 4, 0, -(gate[1] + ty * 4)), bloque(0.4, 2.6, 0.4, gate[0] - tx * 4, 0, -(gate[1] + -ty * 4)));
  const casetaP = [gate[0] - nx * 7 + tx * 7, gate[1] - ny * 7 + ty * 7], rotN = Math.atan2(ny, nx);
  A.put('muro', aLugar(bloque(3.2, 2.6, 3.2, 0, 0, 0), ...casetaP, rotN));
  A.put('zinc', aLugar(new THREE.BoxGeometry(4.0, 0.08, 4.0).rotateZ(0.08), ...casetaP, rotN, 2.75));
  A.put('vidrio', aLugar(bloque(0.05, 0.9, 1.6, 1.61, 1.1, 0), ...casetaP, rotN));
  A.put('adoquin', cinta([[gate[0] + nx * 8, gate[1] + ny * 8], gate, [gate[0] - nx * 14, gate[1] - ny * 14]], 4, 0.12));
  const cartel = letrero([['PARQUE ECOTECNOLÓGICO', 1], ['Las Américas · Yondó', 0.85], ['granja solar · coworking · circuito', 0.6]], { w: 6, h: 2.2, fondo: '#1d5a4a' });
  cartel.position.copy(V(gate[0] + nx * 5 - tx * 8, gate[1] + ny * 5 - ty * 8)); cartel.rotation.y = rotN; g.add(cartel);
  A.volcar(g, { ...M, rojo: mat(new THREE.Color('#c8322b'), { roughness: 0.5 }) });
  return g;
}
// bancas de concreto y madera en [x, y, rot] (rot: el frente de la banca mira hacia rot − 90°)
function bancasDe(g, lista) { if (lista.length) g.add(bancas(lista)); }
// envolvente convexa (cadena monótona) de puntos [x, y]
function envolvente(pts) {
  const p = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], hi = [];
  p.forEach((q) => { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); });
  [...p].reverse().forEach((q) => { while (hi.length > 1 && cr(hi[hi.length - 2], hi[hi.length - 1], q) <= 0) hi.pop(); hi.push(q); });
  return [...lo.slice(0, -1), ...hi.slice(0, -1)];
}
function proySeg(p, a, b) { const dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1))); return [a[0] + t * dx, a[1] + t * dy]; }
function distSeg(p, a, b) { const q = proySeg(p, a, b); return Math.hypot(p[0] - q[0], p[1] - q[1]); }
