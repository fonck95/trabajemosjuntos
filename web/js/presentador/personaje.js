// El presentador: una caricatura en 3D del candidato que explica las presentaciones del asistente (docs/presentador.md).
// Se arma entero con geometrías de three (sin modelos ni texturas de afuera): la cabeza grande con el pelo corto y
// parado, las cejas gruesas, la sonrisa ancha que deja ver los dientes, la camiseta polo roja con su cuello, la tapeta
// de dos botones y el logo bordado del jinete, el jean, el reloj negro en la muñeca izquierda y la manilla roja con
// cuentas doradas en la derecha. Dibujo de caricatura: sombreado por tonos (MeshToonMaterial) y un contorno oscuro de
// grosor fijo en píxeles (casco invertido).
//
// El esqueleto son pivotes (Object3D), no un SkinnedMesh: cada pieza cuelga de su hueso y se mueve con él. El lado
// derecho del cuerpo (brazo, pierna, ojo, ceja, oreja) es una copia del izquierdo dentro de un grupo espejo
// (scale.x = -1): así la misma rotación local hace el mismo gesto en los dos lados (animador.js).
//
// Ejes: el personaje mira hacia +z y su izquierda queda en +x (la derecha de quien lo mira, como en la foto: el logo y
// el reloj de ese lado). Unidades: mide unos 2,2 de alto, con los pies en y = 0.
//
// Sin DOM obligatorio: sin `document` (Node, las pruebas) solo faltan el logo y el dibujo de los dientes, que son
// texturas de canvas.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

export const COLORES = {
  piel: 0xc68b62, pielSombra: 0x9a6243, labio: 0x9b5444, pelo: 0x17110d, ceja: 0x1a120e,
  polo: 0xc1222c, poloOscuro: 0x9a1a22, jean: 0x47689a, jeanOscuro: 0x37547f, zapato: 0x2c221d, suela: 0x4a3c33,
  dientes: 0xfbfaf3, boca: 0x4a1215, lengua: 0xc0545a, ojo: 0xfdfdfb, iris: 0x3a2316, pupila: 0x0b0705,
  reloj: 0x1b1b1e, esfera: 0x34383e, agujas: 0xe8e8e8, pulsera: 0xc2202b, cuenta: 0xd8a33f, boton: 0xf3eee4,
  contorno: 0x1e130e,
};

const R = 0.32;          // el radio de la cabeza (antes de deformarla)
const Y_CADERA = 0.835;  // la altura de la cadera: con ella las suelas quedan en y = 0

// ── Materiales ───────────────────────────────────────────────────────────────────────────────────────────────────
function rampaDeTonos() {
  const tonos = [0.46, 0.7, 0.88, 1];
  const datos = new Uint8Array(tonos.length * 4);
  tonos.forEach((t, i) => datos.set([t * 255, t * 255, t * 255, 255], i * 4));
  const tex = new THREE.DataTexture(datos, tonos.length, 1, THREE.RGBAFormat);
  tex.minFilter = tex.magFilter = THREE.NearestFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/** El contorno de caricatura: el casco invertido (las caras de atrás) empujado hacia afuera `grosor` píxeles en la
 * pantalla, a lo largo de la normal. `uniformes` se comparte entre todos: el presentador fija la resolución. */
function materialContorno(uniformes) {
  return new THREE.ShaderMaterial({
    uniforms: uniformes,
    side: THREE.BackSide,
    vertexShader: `
      uniform float grosor;
      uniform vec2 resolucion;
      void main() {
        vec4 vista = modelViewMatrix * vec4(position, 1.0);
        vec3 n = normalize(normalMatrix * normal);
        vec4 clip = projectionMatrix * vista;
        vec2 d = (projectionMatrix * vec4(n, 0.0)).xy;
        float l = length(d);
        if (l > 1e-5) clip.xy += (d / l) * grosor * 2.0 / resolucion * clip.w;
        gl_Position = clip;
      }`,
    fragmentShader: `
      uniform vec3 color;
      void main() { gl_FragColor = vec4(color, 1.0); }`,
  });
}

// Un generador de números al azar con semilla: el pelo sale igual cada vez
function azar(semilla) {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const suave = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

/** La forma de la cabeza: una esfera de radio R que se hace óvalo, con los pómulos marcados, la mandíbula más angosta
 * y larga y el mentón un poco adelante. Recibe y devuelve un punto (Vector3) relativo al centro de la cabeza. */
function deformarCabeza(v) {
  const yn = v.y / R;
  let sx = 0.83, sz = 0.94, sy = 1.03;
  if (yn < 0) {
    const s = suave(0, 1, -yn);
    sx *= 1 - 0.08 * s - 0.1 * s * s;
    sz *= 1 - 0.06 * s;
    sy = 1.06;
  }
  sx *= 1 + 0.035 * Math.exp(-((yn + 0.1) ** 2) / 0.04);   // los pómulos
  if (v.z < 0) sz *= 1 - 0.28 * suave(0.1, 0.9, -yn) * suave(0, 0.6, -v.z / R);   // la nuca baja hacia el cuello
  v.set(v.x * sx, v.y * sy, v.z * sz);
  if (yn < -0.5 && v.z > 0) v.z += 0.04 * R * ((-yn - 0.5) / 0.5) * (v.z / R);   // el mentón
  return v;
}

function suavizarNormales(geo) {
  geo.deleteAttribute('normal');
  geo.deleteAttribute('uv');
  const g = mergeVertices(geo, 1e-5);
  g.computeVertexNormals();
  return g;
}

/**
 * Arma el personaje. Devuelve {grupo, cuerpo, huesos, manos, cara, contorno, medidas, liberar()}:
 * - `huesos`: los pivotes que mueve animador.js (cadera, columna, pecho, cuello, cabeza, hombro/codo/muneca y
 *   muslo/rodilla/tobillo de cada lado: …I es el izquierdo, …D el derecho, que vive en un grupo espejo).
 * - `manos.I` / `manos.D`: {dedos: [[base, punta] × 4], pulgar, ponerPulgar(p)}: índice, medio, anular y meñique.
 * - `cara`: {boca: {poner({abrir, ancho, sonrisa})}, ojos: [{iris, parpadoSup, parpadoInf}], cejas: [Object3D]}.
 * - `contorno`: los uniformes del contorno ({grosor, resolucion, color}).
 */
export function crearPersonaje({ documento = globalThis.document } = {}) {
  const geos = new Set(), mats = new Set(), texs = new Set();
  const g = (x) => { geos.add(x); return x; };
  const contorno = {
    grosor: { value: 2 },
    resolucion: { value: new THREE.Vector2(800, 800) },
    color: { value: new THREE.Color(COLORES.contorno) },
  };
  const matContorno = materialContorno(contorno);
  mats.add(matContorno);
  const rampa = rampaDeTonos();
  texs.add(rampa);
  const toon = (color) => { const m = new THREE.MeshToonMaterial({ color, gradientMap: rampa }); mats.add(m); return m; };
  const plano = (color, extra = {}) => { const m = new THREE.MeshBasicMaterial({ color, ...extra }); mats.add(m); return m; };
  const M = {
    piel: toon(COLORES.piel), pelo: toon(COLORES.pelo), ceja: toon(COLORES.ceja), polo: toon(COLORES.polo),
    poloOscuro: toon(COLORES.poloOscuro), jean: toon(COLORES.jean), jeanOscuro: toon(COLORES.jeanOscuro),
    zapato: toon(COLORES.zapato), suela: toon(COLORES.suela), reloj: toon(COLORES.reloj), pulsera: toon(COLORES.pulsera),
    cuenta: toon(COLORES.cuenta), boton: toon(COLORES.boton), ojo: plano(COLORES.ojo), iris: plano(COLORES.iris),
    pupila: plano(COLORES.pupila), brillo: plano(0xffffff), esfera: plano(COLORES.esfera), agujas: plano(COLORES.agujas),
    pliegue: plano(COLORES.pielSombra),
  };

  // Una malla con su contorno (un hijo con la misma geometría y el material del contorno)
  function malla(geo, mat, { borde = true, sombra = false } = {}) {
    const m = new THREE.Mesh(g(geo), mat);
    m.castShadow = sombra;
    if (borde) {
      const c = new THREE.Mesh(geo, matContorno);
      c.raycast = () => {};
      m.add(c);
    }
    return m;
  }
  const hueso = (nombre, orden = 'XYZ') => { const o = new THREE.Object3D(); o.name = nombre; o.rotation.order = orden; return o; };
  const espejo = () => { const e = new THREE.Group(); e.scale.x = -1; return e; };
  const capsula = (r, largo, seg = 12) => new THREE.CapsuleGeometry(r, largo, 6, seg);
  const elipsoide = (rx, ry, rz, a = 24, b = 16) => new THREE.SphereGeometry(1, a, b).scale(rx, ry, rz);

  // ── El esqueleto ──────────────────────────────────────────────────────────────────────────────────────────────
  const grupo = new THREE.Group();
  grupo.name = 'presentador';
  const cuerpo = new THREE.Group();   // el salto, el estirón y la entrada (animador.js) mueven esto, no la raíz
  grupo.add(cuerpo);
  const huesos = {
    cadera: hueso('cadera', 'YXZ'), columna: hueso('columna', 'YXZ'), pecho: hueso('pecho', 'YXZ'),
    cuello: hueso('cuello', 'YXZ'), cabeza: hueso('cabeza', 'YXZ'),
  };
  huesos.cadera.position.y = Y_CADERA;
  huesos.columna.position.y = 0.05;
  huesos.pecho.position.y = 0.26;
  huesos.cuello.position.set(0, 0.27, 0.005);
  huesos.cabeza.position.y = 0.1;
  cuerpo.add(huesos.cadera);
  huesos.cadera.add(huesos.columna);
  huesos.columna.add(huesos.pecho);
  huesos.pecho.add(huesos.cuello);
  huesos.cuello.add(huesos.cabeza);

  // ── El torso: la polo ─────────────────────────────────────────────────────────────────────────────────────────
  const perfil = [[0.212, -0.2], [0.218, -0.17], [0.214, -0.12], [0.212, -0.04], [0.206, 0.08], [0.212, 0.2], [0.222, 0.3],
    [0.222, 0.38], [0.205, 0.44], [0.165, 0.485], [0.11, 0.51], [0.082, 0.52]].map(([r, y]) => new THREE.Vector2(r, y));
  let torsoGeo = new THREE.LatheGeometry(perfil, 48, Math.PI, Math.PI * 2);
  {
    const p = torsoGeo.attributes.position, v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      const ancho = 1.06 + 0.2 * suave(0.05, 0.4, v.y) - 0.05 * suave(0.42, 0.52, v.y);
      const fondo = 0.66 + 0.04 * suave(0.1, 0.32, v.y);
      p.setXYZ(i, v.x * ancho, v.y, v.z * fondo);
    }
  }
  torsoGeo = suavizarNormales(torsoGeo);
  const torso = malla(torsoGeo, M.polo);
  huesos.columna.add(torso);
  // el borde de abajo de la polo, un poco más ancho (la camiseta va por fuera del jean)
  const ruedo = malla(new THREE.TorusGeometry(0.218, 0.012, 8, 40).rotateX(Math.PI / 2).scale(1.06, 1, 0.66), M.polo, { borde: false });
  ruedo.position.y = -0.195;
  huesos.columna.add(ruedo);

  // Dónde queda la superficie de una malla vista de frente (o de lado): para pegarle el cuello, la tapeta, el logo y las
  // facciones de la cara
  const rayo = new THREE.Raycaster();
  const desde = new THREE.Vector3(), hacia = new THREE.Vector3();
  function tocar(objeto, x, y, z = 3, dir = [0, 0, -1]) {
    desde.set(x, y, z);
    hacia.set(...dir).normalize();
    rayo.set(desde, hacia);
    objeto.updateMatrixWorld(true);
    const h = rayo.intersectObject(objeto, false)[0];
    return h ? { p: h.point.clone(), n: h.face.normal.clone() } : null;
  }
  // Orienta un objeto para que su +z siga la normal `n`
  const alinear = (o, n) => { o.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n.clone().normalize()); return o; };

  // El cuello de la polo: la tira alrededor del cuello y las dos solapas sobre el pecho
  M.poloDoble = toon(COLORES.polo);
  M.poloDoble.side = THREE.DoubleSide;
  // la tira que se para alrededor del cuello, abierta adelante
  const tiraCuello = malla(new THREE.CylinderGeometry(0.112, 0.104, 0.05, 32, 1, true, Math.PI + 0.55, Math.PI * 2 - 1.1)
    .scale(1.06, 1, 0.9), M.poloDoble);
  tiraCuello.position.set(0, 0.538, -0.008);
  tiraCuello.rotation.x = -0.16;
  huesos.columna.add(tiraCuello);
  // y las dos puntas que caen sobre el pecho
  const forma = new THREE.Shape();
  forma.moveTo(0, 0.012);
  forma.lineTo(0.098, 0.03);
  forma.quadraticCurveTo(0.104, 0.004, 0.09, -0.022);
  forma.lineTo(0.026, -0.094);
  forma.quadraticCurveTo(0.004, -0.06, 0, 0.012);
  const solapaGeo = new THREE.ExtrudeGeometry(forma, { depth: 0.008, bevelEnabled: true, bevelThickness: 0.004,
    bevelSize: 0.004, bevelSegments: 2, curveSegments: 8 });
  for (const lado of [1, -1]) {
    const t = tocar(torso, 0.03 * lado, 0.5) || { p: new THREE.Vector3(0.03 * lado, 0.5, 0.11), n: new THREE.Vector3(0, 0.5, 1) };
    const s = malla(solapaGeo, M.polo);
    const pivote = new THREE.Group();
    pivote.position.copy(t.p).addScaledVector(t.n, 0.004);
    alinear(pivote, t.n);
    pivote.scale.x = lado;
    s.rotation.z = -0.12;
    pivote.add(s);
    huesos.columna.add(pivote);
  }
  // La tapeta con dos botones blancos
  const enPecho = tocar(torso, 0, 0.405) || { p: new THREE.Vector3(0, 0.405, 0.14), n: new THREE.Vector3(0, 0.2, 1) };
  const tapeta = malla(new THREE.BoxGeometry(0.046, 0.13, 0.01), M.polo);
  tapeta.position.copy(enPecho.p).add(new THREE.Vector3(0, 0.0, 0.002));
  alinear(tapeta, enPecho.n);
  huesos.columna.add(tapeta);
  for (const [i, y] of [[0, 0.03], [1, -0.025]]) {
    const b = malla(new THREE.CylinderGeometry(0.0105, 0.0105, 0.006, 16).rotateX(Math.PI / 2), M.boton, { borde: false });
    b.position.set(0, y, 0.008);
    b.name = `boton${i}`;
    tapeta.add(b);
  }
  // El logo bordado (el jinete) en el pecho izquierdo
  if (documento?.createElement) {
    const tex = logoDelJinete(documento);
    if (tex) {
      texs.add(tex);
      const enLogo = tocar(torso, 0.105, 0.3);
      if (enLogo) {
        const logo = new THREE.Mesh(g(new THREE.PlaneGeometry(0.06, 0.06)), plano(0xffffff, { map: tex, transparent: true, depthWrite: false }));
        logo.position.copy(enLogo.p).addScaledVector(enLogo.n, 0.002);
        alinear(logo, enLogo.n);
        logo.renderOrder = 2;
        huesos.columna.add(logo);
      }
    }
  }

  // ── La cadera: el jean ────────────────────────────────────────────────────────────────────────────────────────
  const pelvis = malla(elipsoide(0.2, 0.15, 0.125, 32, 20), M.jean);
  pelvis.position.y = -0.06;
  huesos.cadera.add(pelvis);

  // ── Los brazos ────────────────────────────────────────────────────────────────────────────────────────────────
  const manos = {};
  function brazo(lado) {
    const raiz = lado === 'D' ? espejo() : new THREE.Group();
    huesos.pecho.add(raiz);
    const bola = malla(new THREE.SphereGeometry(0.084, 24, 16), M.polo);
    bola.position.set(0.248, 0.19, 0);
    bola.scale.set(1, 1, 0.92);
    raiz.add(bola);
    const hombro = hueso(`hombro${lado}`, 'XZY'), codo = hueso(`codo${lado}`, 'XYZ'), muneca = hueso(`muneca${lado}`, 'XYZ');
    hombro.position.copy(bola.position);
    raiz.add(hombro);
    // la manga corta, abierta, con su puño acanalado
    const manga = malla(new THREE.CylinderGeometry(0.084, 0.08, 0.17, 24, 1, true), M.poloDoble);
    manga.position.y = -0.075;
    hombro.add(manga);
    const puno = malla(new THREE.TorusGeometry(0.078, 0.011, 8, 28).rotateX(Math.PI / 2), M.poloOscuro, { borde: false });
    puno.position.y = -0.158;
    hombro.add(puno);
    const brazoGeo = capsula(0.054, 0.2);
    const sup = malla(brazoGeo, M.piel);
    sup.position.y = -0.17;
    hombro.add(sup);
    codo.position.y = -0.292;
    hombro.add(codo);
    const ante = malla(new THREE.CapsuleGeometry(0.049, 0.2, 6, 12).scale(1, 1, 0.92), M.piel);
    ante.position.y = -0.125;
    codo.add(ante);
    muneca.position.y = -0.262;
    codo.add(muneca);
    if (lado === 'I') reloj(codo); else manilla(codo);
    manos[lado] = mano(muneca);
    Object.assign(huesos, { [`hombro${lado}`]: hombro, [`codo${lado}`]: codo, [`muneca${lado}`]: muneca });
  }

  // El reloj negro (muñeca izquierda): correa, caja y esfera hacia afuera (+x: el dorso, con la palma hacia el cuerpo)
  function reloj(codo) {
    const r = new THREE.Group();
    r.position.y = -0.232;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.05, 0.0125, 10, 28).rotateX(Math.PI / 2).scale(1, 1.25, 0.95), M.reloj));
    const caja = malla(new THREE.CylinderGeometry(0.032, 0.032, 0.018, 28).rotateZ(Math.PI / 2), M.reloj);
    caja.position.x = 0.052;
    r.add(caja);
    const esfera = new THREE.Mesh(g(new THREE.CircleGeometry(0.025, 28).rotateY(Math.PI / 2)), M.esfera);
    esfera.position.x = 0.0615;
    r.add(esfera);
    for (const [largo, ang] of [[0.016, 0.6], [0.011, 2.2]]) {
      const a = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0028, largo).translate(0, largo / 2, 0).rotateY(Math.PI / 2)), M.agujas);
      a.position.x = 0.062;
      a.rotation.x = ang;
      r.add(a);
    }
  }
  // La manilla roja de hilo con cuentas doradas (muñeca derecha)
  function manilla(codo) {
    const r = new THREE.Group();
    r.position.y = -0.236;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.05, 0.005, 6, 32).rotateX(Math.PI / 2), M.pulsera, { borde: false }));
    for (let i = 0; i < 7; i++) {
      const a = -1.2 + (2.4 * i) / 6;
      const c = new THREE.Mesh(g(new THREE.SphereGeometry(0.0085, 10, 8)), M.cuenta);
      c.position.set(Math.cos(a) * 0.052, 0, Math.sin(a) * 0.052);
      r.add(c);
    }
  }

  // La mano: la palma hacia el cuerpo (−x), los dedos hacia abajo (−y) y el pulgar adelante (+z)
  function mano(muneca) {
    const m = new THREE.Group();
    muneca.add(m);
    const palma = malla(elipsoide(0.031, 0.057, 0.05), M.piel);
    palma.position.y = -0.055;
    m.add(palma);
    const dedos = [];
    const filas = [[0.033, 1.0], [0.011, 1.08], [-0.011, 1.0], [-0.031, 0.84]];
    for (const [z, largo] of filas) {
      const base = hueso('dedo', 'XYZ');
      base.position.set(0, -0.098, z);
      m.add(base);
      const f1 = malla(capsula(0.0165, 0.022 * largo, 8), M.piel);
      f1.position.y = -0.02 * largo;
      base.add(f1);
      const punta = hueso('punta', 'XYZ');
      punta.position.y = -0.041 * largo;
      base.add(punta);
      const f2 = malla(capsula(0.0155, 0.016 * largo, 8), M.piel);
      f2.position.y = -0.016 * largo;
      punta.add(f2);
      dedos.push([base, punta]);
    }
    const pulgar = hueso('pulgar', 'XYZ');
    pulgar.position.set(-0.008, -0.032, 0.042);
    m.add(pulgar);
    const p1 = malla(capsula(0.018, 0.034, 8), M.piel);
    p1.position.y = -0.03;
    pulgar.add(p1);
    // Hacia dónde apunta el pulgar: −1 afuera (mano abierta, pulgar arriba), 0 en reposo, 1 doblado sobre la palma
    const abajo = new THREE.Vector3(0, -1, 0);
    const dirs = [[-0.05, -0.12, 1], [-0.4, -0.75, 0.55], [-0.8, -0.55, -0.15]].map((d) => new THREE.Vector3(...d).normalize());
    const qs = dirs.map((d) => new THREE.Quaternion().setFromUnitVectors(abajo, d));
    const ponerPulgar = (p) => {
      const t = Math.max(-1, Math.min(1, p));
      if (t < 0) pulgar.quaternion.slerpQuaternions(qs[1], qs[0], -t);
      else pulgar.quaternion.slerpQuaternions(qs[1], qs[2], t);
    };
    ponerPulgar(0);
    return { grupo: m, dedos, pulgar, ponerPulgar };
  }
  brazo('I');
  brazo('D');

  // ── Las piernas ───────────────────────────────────────────────────────────────────────────────────────────────
  function pierna(lado) {
    const raiz = lado === 'D' ? espejo() : new THREE.Group();
    huesos.cadera.add(raiz);
    const muslo = hueso(`muslo${lado}`, 'XZY'), rodilla = hueso(`rodilla${lado}`, 'XYZ'), tobillo = hueso(`tobillo${lado}`, 'XYZ');
    muslo.position.set(0.105, -0.035, 0);
    raiz.add(muslo);
    const m = malla(capsula(0.088, 0.25, 16), M.jean);
    m.position.y = -0.18;
    muslo.add(m);
    rodilla.position.y = -0.38;
    muslo.add(rodilla);
    const c = malla(new THREE.CapsuleGeometry(0.078, 0.24, 6, 16), M.jean);
    c.position.y = -0.16;
    rodilla.add(c);
    // el bota del jean, recto, que cae sobre el zapato
    const bota = malla(new THREE.CylinderGeometry(0.08, 0.086, 0.07, 24, 1, true), M.jeanOscuro);
    bota.material = toon(COLORES.jeanOscuro);
    bota.material.side = THREE.DoubleSide;
    bota.position.y = -0.322;
    rodilla.add(bota);
    tobillo.position.y = -0.37;
    rodilla.add(tobillo);
    const zapato = malla(elipsoide(0.07, 0.05, 0.13, 24, 14), M.zapato);
    zapato.position.set(0, -0.012, 0.045);
    tobillo.add(zapato);
    const suela = malla(new THREE.CylinderGeometry(1, 1, 1, 24).scale(0.072, 0.022, 0.135), M.suela, { borde: false });
    suela.position.set(0, -0.045, 0.045);
    tobillo.add(suela);
    Object.assign(huesos, { [`muslo${lado}`]: muslo, [`rodilla${lado}`]: rodilla, [`tobillo${lado}`]: tobillo });
  }
  pierna('I');
  pierna('D');

  // ── El cuello y la cabeza ─────────────────────────────────────────────────────────────────────────────────────
  const cuello = malla(new THREE.CylinderGeometry(0.072, 0.082, 0.2, 20), M.piel);
  cuello.position.y = 0.045;
  huesos.cuello.add(cuello);
  const craneo = new THREE.Group();
  craneo.position.set(0, 0.3, 0.012);
  huesos.cabeza.add(craneo);
  let cabezaGeo = new THREE.SphereGeometry(R, 72, 54);
  {
    const p = cabezaGeo.attributes.position, v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) { deformarCabeza(v.fromBufferAttribute(p, i)); p.setXYZ(i, v.x, v.y, v.z); }
  }
  cabezaGeo = suavizarNormales(cabezaGeo);
  const cabeza = malla(cabezaGeo, M.piel);
  craneo.add(cabeza);
  const cara = construirCara(craneo, cabeza);
  pelo(craneo);

  // El pelo: un casco algo más grande que la cabeza, recortado por la línea del pelo (la frente, las entradas, las
  // patillas cortas, sobre las orejas y la nuca), y encima puntas cortas, paradas y peinadas hacia adelante
  function pelo(padre) {
    // el límite (grados desde la coronilla) según el rumbo: 0 al frente, π atrás
    const limite = [[0, 47], [0.42, 48], [0.72, 44], [1.0, 62], [1.18, 90], [1.3, 92], [1.42, 76], [1.85, 80], [2.3, 104], [Math.PI, 116]];
    const enLimite = (az) => {
      for (let i = 1; i < limite.length; i++) {
        const [a1, l1] = limite[i - 1], [a2, l2] = limite[i];
        if (az <= a2) return l1 + (l2 - l1) * (az - a1) / (a2 - a1);
      }
      return limite[limite.length - 1][1];
    };
    // el casco: una grilla (rumbo × altura) cuyo borde de abajo sigue la línea del pelo
    const NA = 96, NT = 26, pos = [], idx = [];
    const v = new THREE.Vector3();
    for (let i = 0; i <= NA; i++) {
      const az = -Math.PI + (2 * Math.PI * i) / NA, tope = (enLimite(Math.abs(az)) * Math.PI) / 180;
      for (let j = 0; j <= NT; j++) {
        const th = (tope * j) / NT;
        v.set(Math.sin(th) * Math.sin(az), Math.cos(th), Math.sin(th) * Math.cos(az)).multiplyScalar(R * 1.05);
        deformarCabeza(v);
        v.y += 0.012 + 0.02 * Math.max(0, v.y / R);   // algo de volumen arriba
        pos.push(v.x, v.y, v.z);
      }
    }
    for (let i = 0; i < NA; i++) {
      for (let j = 0; j < NT; j++) {
        const a = i * (NT + 1) + j, b = a + 1, c = a + NT + 1, d = c + 1;
        idx.push(a, b, c, b, d, c);
      }
    }
    const s = new THREE.BufferGeometry();
    s.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    s.setAttribute('normal', new THREE.Float32BufferAttribute(pos.map(() => 0), 3));
    s.setAttribute('uv', new THREE.Float32BufferAttribute(new Array((pos.length / 3) * 2).fill(0), 2));
    s.setIndex(idx);
    const casco = malla(suavizarNormales(s), M.pelo);
    padre.add(casco);
    // las puntas
    const r = azar(1896);
    const conos = [];
    const arriba = new THREE.Vector3(), dir = new THREE.Vector3(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
    for (let i = 0; i < 230; i++) {
      // un punto de la coronilla y del frente de arriba, más denso adelante
      const az = (r() * 2 - 1) * Math.PI;
      const tope = enLimite(Math.abs(az)) - 6;
      const th = Math.min(tope, Math.pow(r(), 0.75) * Math.min(tope, 70)) * Math.PI / 180;
      arriba.set(Math.sin(th) * Math.sin(az), Math.cos(th), Math.sin(th) * Math.cos(az));
      const base = deformarCabeza(arriba.clone().multiplyScalar(R * 1.05));
      base.y += 0.012 + 0.02 * Math.max(0, base.y / R);
      const frente = Math.max(0, Math.cos(az)) * Math.min(1, Math.sin(th) * 1.6);   // cuánto está hacia la frente
      // paradas, peinadas hacia arriba y un poco adelante; más cortas hacia los lados y la nuca
      dir.copy(arriba).multiplyScalar(0.8).add(new THREE.Vector3(0, 0.6, 0.22 + 0.3 * frente))
        .add(new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).multiplyScalar(0.28)).normalize();
      const alto = (0.035 + 0.035 * r()) * (1 + 0.7 * frente) * (1 - 0.45 * Math.min(1, th / 1.15));
      const cono = new THREE.ConeGeometry(0.024 + 0.014 * r(), alto, 5, 1);
      q.setFromUnitVectors(Y, dir);
      cono.applyQuaternion(q);
      cono.translate(base.x + dir.x * (alto * 0.5 - 0.016), base.y + dir.y * (alto * 0.5 - 0.016), base.z + dir.z * (alto * 0.5 - 0.016));
      conos.push(cono.toNonIndexed());
    }
    const puntas = mergeGeometries(conos.map((c) => { c.deleteAttribute('uv'); return c; }));
    for (const c of conos) c.dispose();
    puntas.computeVertexNormals();
    padre.add(malla(puntas, M.pelo));
  }

  // Lo que va dibujado sobre la piel (los ojos, la boca, el pliegue de la nariz): tiras planas que se pegan a la cara.
  // Al armarlas se mide la altura de la superficie en una grilla de la región (`zEn`, con rayos); en cada cuadro se
  // rehacen sus vértices según la forma pedida (ojos que parpadean, boca que habla), sin volver a medir
  function pegatinas(padre, cabeza, { x0, x1, y0, y1, nx = 31, ny = 19 }) {
    const alturas = new Float32Array(nx * ny);
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const x = x0 + ((x1 - x0) * i) / (nx - 1), y = y0 + ((y1 - y0) * j) / (ny - 1);
        alturas[j * nx + i] = tocar(cabeza, x, y)?.p.z ?? R * 0.75;
      }
    }
    const zEn = (x, y) => {
      const fx = Math.max(0, Math.min(nx - 1.001, ((x - x0) / (x1 - x0)) * (nx - 1)));
      const fy = Math.max(0, Math.min(ny - 1.001, ((y - y0) / (y1 - y0)) * (ny - 1)));
      const i = Math.floor(fx), j = Math.floor(fy), u = fx - i, w = fy - j;
      const a = alturas[j * nx + i], b = alturas[j * nx + i + 1], c = alturas[(j + 1) * nx + i], d = alturas[(j + 1) * nx + i + 1];
      return (a * (1 - u) + b * u) * (1 - w) + (c * (1 - u) + d * u) * w;
    };
    const material = (color, orden, extra = {}) => plano(color, { side: THREE.DoubleSide, polygonOffset: true,
      polygonOffsetFactor: -2 - orden, polygonOffsetUnits: -4 - 2 * orden, ...extra });
    const montar = (geo, mat, orden) => {
      const m = new THREE.Mesh(g(geo), mat);
      m.renderOrder = 3 + orden;
      m.frustumCulled = false;
      padre.add(m);
      return m;
    };
    /** Una tira entre dos curvas: devuelve poner(cx, a, arriba(u), abajo(u), dz), con u de −1 a 1 a lo ancho (x = cx + u·a) */
    function tira(color, orden, extra = {}, N = 28, F = 4) {
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array((N + 1) * (F + 1) * 3), uv = new Float32Array((N + 1) * (F + 1) * 2), idx = [];
      for (let i = 0; i < N; i++) {
        for (let j = 0; j < F; j++) {
          const a = i * (F + 1) + j, b = a + 1, c = a + F + 1, d = c + 1;
          idx.push(a, c, b, b, c, d);
        }
      }
      for (let i = 0; i <= N; i++) for (let j = 0; j <= F; j++) uv.set([i / N, 1 - j / F], (i * (F + 1) + j) * 2);
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      geo.setIndex(idx);
      const m = montar(geo, material(color, orden, extra), orden);
      const poner = (cx, a, arriba, abajo, dz) => {
        for (let i = 0; i <= N; i++) {
          const u = -1 + (2 * i) / N, x = cx + u * a, y1 = arriba(u), yb = Math.min(y1, abajo(u));
          for (let j = 0; j <= F; j++) {
            const y = y1 + ((yb - y1) * j) / F, k = (i * (F + 1) + j) * 3;
            pos[k] = x; pos[k + 1] = y; pos[k + 2] = zEn(x, y) + dz;
          }
        }
        geo.attributes.position.needsUpdate = true;
        geo.computeBoundingSphere();
      };
      poner.malla = m;
      return poner;
    }
    /** Un disco: devuelve poner(cx, cy, r, dz) */
    function disco(color, orden, extra = {}, N = 24) {
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array((N + 1) * 3), idx = [];
      for (let i = 0; i < N; i++) idx.push(0, 1 + i, 1 + ((i + 1) % N));
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setIndex(idx);
      const m = montar(geo, material(color, orden, extra), orden);
      const poner = (cx, cy, r, dz) => {
        pos[0] = cx; pos[1] = cy; pos[2] = zEn(cx, cy) + dz;
        for (let i = 0; i < N; i++) {
          const a = (i / N) * Math.PI * 2, x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
          pos.set([x, y, zEn(x, y) + dz], (1 + i) * 3);
        }
        geo.attributes.position.needsUpdate = true;
        geo.computeBoundingSphere();
      };
      poner.malla = m;
      return poner;
    }
    return { zEn, tira, disco };
  }

  // La cara: los ojos (dibujados sobre la piel, entrecerrados por la sonrisa, que parpadean y miran), las cejas gruesas,
  // la nariz ancha, las orejas, los pliegues de la sonrisa y la boca
  function construirCara(padre, cabeza) {
    const sup = (x, y) => tocar(cabeza, x, y) || { p: new THREE.Vector3(x, y, R * 0.8), n: new THREE.Vector3(0, 0, 1) };
    const ojos = [], cejas = [];
    // El blanco del ojo marca el stencil y el iris solo se pinta donde lo marcó: así el iris nunca se sale del ojo
    const marca = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp };
    const dentro = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc, stencilZPass: THREE.KeepStencilOp };
    for (const lado of ['I', 'D']) {
      const raiz = lado === 'D' ? espejo() : new THREE.Group();
      padre.add(raiz);
      const P = pegatinas(raiz, cabeza, { x0: 0.02, x1: 0.19, y0: -0.05, y1: 0.08, nx: 25, ny: 15 });
      const OX = 0.098, OY = 0.016, A = 0.052;
      const blanco = P.tira(COLORES.ojo, 2, marca, 24, 4);
      const pestanas = P.tira(COLORES.contorno, 5, {}, 24, 2);
      const bajo = P.tira(COLORES.pielSombra, 5, {}, 24, 2);
      const iris = P.disco(COLORES.iris, 3, dentro);
      const pupila = P.disco(COLORES.pupila, 4, dentro, 20);
      const brillo = P.disco(0xffffff, 5, dentro, 12);
      /** abierto 0..1 (0: cerrado), sonrisa 0..1 (el párpado de abajo sube), mira [x, y] de −1 a 1 */
      let ultimo = '';
      const poner = ({ abierto = 1, sonrisa = 1, mira = [0, 0] } = {}) => {
        const clave = `${abierto.toFixed(3)}|${sonrisa.toFixed(3)}|${mira[0].toFixed(3)}|${mira[1].toFixed(3)}`;
        if (clave === ultimo) return;
        ultimo = clave;
        const hb = 0.02 - 0.009 * sonrisa;                     // lo que baja el borde de abajo
        const abajo = (u) => OY - hb * Math.pow(Math.max(0, 1 - u * u), 0.75) + 0.006 * sonrisa * u * u;
        const ht = 0.031 - 0.005 * sonrisa;                     // lo que sube el de arriba, abierto
        const arribaAbierto = (u) => OY + ht * Math.pow(Math.max(0, 1 - u * u), 0.55) + 0.004 * u;
        const arriba = (u) => { const b = abajo(u); return b + (arribaAbierto(u) - b) * abierto; };
        blanco(OX, A, arriba, abajo, 0.0015);
        pestanas(OX - 0.002, A * 1.08, (u) => arriba(u / 1.04) + 0.0085 * Math.pow(Math.max(0, 1 - u * u), 0.35) + 0.001,
          (u) => arriba(u / 1.04) - 0.0005, 0.0024);
        bajo(OX, A * 0.8, (u) => abajo(u / 0.8 * 0.8) - 0.006 - 0.002 * sonrisa, (u) => abajo(u / 0.8 * 0.8) - 0.0095 - 0.003 * sonrisa
          * (1 - u * u), 0.0012);
        const mx = OX + mira[0] * 0.016, my = OY + 0.004 + mira[1] * 0.008;
        iris(mx, my, 0.024, 0.0025);
        pupila(mx, my, 0.0125, 0.0032);
        brillo(mx + 0.007, my + 0.009, 0.0055, 0.0038);
      };
      poner();
      ojos.push({ poner });
      // la ceja: gruesa, recta con un arco leve, más fina hacia afuera
      const c = sup(0.104, 0.104);
      let cejaGeo = new THREE.CapsuleGeometry(0.0175, 0.085, 6, 12).rotateZ(Math.PI / 2);
      {
        const p = cejaGeo.attributes.position, v = new THREE.Vector3();
        for (let i = 0; i < p.count; i++) {
          v.fromBufferAttribute(p, i);
          const t = (v.x + 0.06) / 0.12;
          v.y *= 1.08 - 0.4 * Math.max(0, Math.min(1, t));
          v.y += 0.011 * (1 - ((v.x + 0.005) / 0.065) ** 2);
          v.z *= 0.5;
          p.setXYZ(i, v.x, v.y, v.z);
        }
        cejaGeo.computeVertexNormals();
      }
      const ceja = new THREE.Group();
      ceja.position.copy(c.p).addScaledVector(c.n, 0.002);
      alinear(ceja, c.n.clone().lerp(new THREE.Vector3(0, 0, 1), 0.3));
      raiz.add(ceja);
      const cejaM = malla(cejaGeo, M.ceja);
      cejaM.rotation.z = -0.05;
      ceja.add(cejaM);
      cejas.push(ceja);
      // la oreja, un poco despegada
      const o = tocar(cabeza, 3, -0.01, -0.02, [-1, 0, 0]) || { p: new THREE.Vector3(0.24, -0.01, -0.02) };
      const oreja = malla(elipsoide(0.034, 0.07, 0.05, 20, 14), M.piel);
      oreja.position.copy(o.p).add(new THREE.Vector3(0.004, 0, -0.01));
      oreja.rotation.set(0, 0.35, 0.08);
      raiz.add(oreja);
      const adentro = new THREE.Mesh(g(elipsoide(0.012, 0.044, 0.03, 14, 10)), M.pliegue);
      adentro.position.set(0.024, 0, 0.008);
      oreja.add(adentro);
      // el pliegue de la sonrisa, de la aleta de la nariz hacia la comisura
      const puntos = [[0.05, -0.085], [0.075, -0.12], [0.092, -0.158], [0.095, -0.18]].map(([x, y]) => {
        const h = sup(x, y);
        return h.p.addScaledVector(h.n, 0.0012);
      });
      raiz.add(new THREE.Mesh(g(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(puntos), 16, 0.003, 6)), M.pliegue));
    }
    // la nariz: el puente, la punta ancha y las aletas, de una pieza (sin contorno: lo dibujan el tono y la línea de
    // las fosas)
    const np = sup(0, -0.058);
    const partes = [
      elipsoide(0.038, 0.032, 0.034, 20, 14).translate(0, -0.006, 0.016),
      elipsoide(0.026, 0.021, 0.022, 16, 10).translate(0.03, -0.016, 0.0),
      elipsoide(0.026, 0.021, 0.022, 16, 10).translate(-0.03, -0.016, 0.0),
      capsula(0.018, 0.04, 10).rotateX(0.3).translate(0, 0.03, -0.006),
    ];
    for (const x of partes) x.deleteAttribute('uv');
    const nariz = new THREE.Mesh(g(suavizarNormales(mergeGeometries(partes.map((x) => x.toNonIndexed())))), M.piel);
    for (const x of partes) x.dispose();
    nariz.position.copy(np.p).add(new THREE.Vector3(0, 0, -0.012));
    padre.add(nariz);
    // las fosas: una «w» suave bajo la punta
    const PN = pegatinas(padre, cabeza, { x0: -0.08, x1: 0.08, y0: -0.12, y1: -0.04, nx: 21, ny: 11 });
    const fosas = PN.tira(COLORES.pielSombra, 1, {}, 24, 2);
    const yN = np.p.y - 0.034;
    fosas(0, 0.05, (u) => yN + 0.012 * u * u - 0.004 * Math.cos(u * Math.PI * 2) * (1 - u * u),
      (u) => yN + 0.012 * u * u - 0.004 * Math.cos(u * Math.PI * 2) * (1 - u * u) - 0.0055 * Math.pow(1 - u * u, 0.5), 0.004);
    const boca = crearBoca(padre, cabeza);
    return { ojos, cejas, boca, nariz };
  }

  // La boca: los labios, el fondo oscuro, la lengua y las dos filas de dientes, que se rehacen en cada cuadro según qué
  // tan abierta, ancha y sonriente está
  function crearBoca(padre, cabeza) {
    const Y0 = -0.165;
    const P = pegatinas(padre, cabeza, { x0: -0.15, x1: 0.15, y0: Y0 - 0.12, y1: Y0 + 0.06 });
    const texDientes = documento?.createElement ? dibujoDeDientes(documento) : null;
    if (texDientes) texs.add(texDientes);
    const labios = P.tira(COLORES.labio, 0);
    const fondo = P.tira(COLORES.boca, 1);
    const lengua = P.tira(COLORES.lengua, 2);
    const dientesSup = P.tira(COLORES.dientes, 3, texDientes ? { map: texDientes, color: 0xffffff } : {});
    const dientesInf = P.tira(0xeeeae0, 3);
    let ultimo = '';
    /** abrir 0..1 (0: la sonrisa cerrada de la foto, con los dientes de arriba a la vista), ancho 0.7..1.15 (menos: una
     * «o»), sonrisa 0..1 (las comisuras arriba) */
    function poner({ abrir = 0, ancho = 1, sonrisa = 1 } = {}) {
      const clave = `${abrir.toFixed(3)}|${ancho.toFixed(3)}|${sonrisa.toFixed(3)}`;
      if (clave === ultimo) return;
      ultimo = clave;
      const w = 0.098 * ancho;
      const arriba = (u) => Y0 + 0.004 + 0.026 * sonrisa * u * u - 0.004 * (1 - sonrisa) * (1 - u * u);
      const hondo = (u) => (0.05 + 0.06 * abrir - 0.012 * (1 - ancho)) * Math.pow(Math.max(0, 1 - u * u), 0.72);
      const abajo = (u) => arriba(u) - hondo(u);
      labios(0, w * 1.07, (u) => arriba(u) + 0.0055 * Math.sqrt(Math.max(0, 1 - u * u)) + 0.001,
        (u) => abajo(u) - 0.013 * Math.pow(Math.max(0, 1 - u * u), 0.6) - 0.0015, 0.0015);
      fondo(0, w, arriba, abajo, 0.002);
      lengua(0, w * 0.62, (u) => abajo(u * 0.62) + 0.4 * hondo(u * 0.62) * Math.min(1, abrir * 1.6) * (1 - u * u),
        (u) => abajo(u * 0.62), 0.0025);
      dientesSup(0, w * 0.97, (u) => arriba(u * 0.97), (u) => arriba(u * 0.97) - Math.min(0.032 * Math.pow(Math.max(0, 1 - u * u), 0.3),
        0.64 * hondo(u * 0.97)), 0.003);
      dientesInf(0, w * 0.82, (u) => abajo(u * 0.82) + Math.min(0.013 * Math.pow(Math.max(0, 1 - u * u), 0.4),
        0.27 * hondo(u * 0.82)), (u) => abajo(u * 0.82), 0.003);
    }
    poner();
    return { poner };
  }

  // Las medidas para encuadrar: la altura de los hombros y de la coronilla, con el cuerpo en reposo
  grupo.updateMatrixWorld(true);
  const caja = new THREE.Box3().setFromObject(grupo);
  const hombro = new THREE.Vector3();
  huesos.hombroI.getWorldPosition(hombro);
  const medidas = { alto: caja.max.y, ancho: caja.max.x - caja.min.x, piso: caja.min.y, hombro: hombro.y };

  function liberar() {
    for (const x of geos) x.dispose();
    for (const x of mats) x.dispose();
    for (const x of texs) x.dispose();
    grupo.traverse((o) => { if (o.geometry && !geos.has(o.geometry)) o.geometry.dispose(); });
  }

  return { grupo, cuerpo, huesos, manos, cara, contorno, medidas, liberar };
}

// El logo bordado de la polo: un jinete de polo dorado con la camiseta azul, en un canvas de 128 px
function logoDelJinete(doc) {
  const c = doc.createElement('canvas');
  c.width = c.height = 128;
  const x = c.getContext?.('2d');
  if (!x) return null;
  x.lineCap = x.lineJoin = 'round';
  // el caballo
  x.fillStyle = '#c99440';
  x.strokeStyle = '#8a5a22';
  x.lineWidth = 3;
  x.beginPath();
  x.ellipse(62, 74, 30, 14, -0.08, 0, Math.PI * 2);
  x.fill();
  x.stroke();
  x.beginPath();   // el cuello y la cabeza
  x.moveTo(84, 68); x.lineTo(98, 44); x.lineTo(110, 48); x.lineTo(104, 56); x.lineTo(92, 76); x.closePath();
  x.fill();
  x.stroke();
  x.lineWidth = 6;
  x.strokeStyle = '#b07a30';
  for (const [a, b, c2, d] of [[42, 82, 30, 112], [52, 84, 50, 114], [76, 84, 86, 112], [84, 82, 98, 108]]) {
    x.beginPath(); x.moveTo(a, b); x.lineTo(c2, d); x.stroke();
  }
  x.lineWidth = 4;   // la cola
  x.beginPath(); x.moveTo(33, 70); x.quadraticCurveTo(18, 74, 20, 92); x.stroke();
  // el jinete
  x.fillStyle = '#26386a';
  x.beginPath(); x.ellipse(64, 50, 9, 15, 0.15, 0, Math.PI * 2); x.fill();
  x.fillStyle = '#e9d9b0';
  x.beginPath(); x.arc(66, 31, 7, 0, Math.PI * 2); x.fill();
  x.strokeStyle = '#26386a';
  x.lineWidth = 5;
  x.beginPath(); x.moveTo(60, 60); x.lineTo(54, 78); x.stroke();
  // el taco
  x.strokeStyle = '#8a5a22';
  x.lineWidth = 3;
  x.beginPath(); x.moveTo(72, 46); x.lineTo(100, 18); x.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// Los dientes de arriba: blancos, con las separaciones apenas marcadas (la sonrisa amplia de la foto)
function dibujoDeDientes(doc) {
  const c = doc.createElement('canvas');
  c.width = 256;
  c.height = 32;
  const x = c.getContext?.('2d');
  if (!x) return null;
  x.fillStyle = '#fbfaf3';
  x.fillRect(0, 0, 256, 32);
  const g = x.createLinearGradient(0, 0, 0, 32);
  g.addColorStop(0, 'rgba(160,150,140,0.35)');
  g.addColorStop(0.25, 'rgba(160,150,140,0)');
  x.fillStyle = g;
  x.fillRect(0, 0, 256, 32);
  x.strokeStyle = 'rgba(150,140,130,0.55)';
  x.lineWidth = 2;
  const cortes = [0.16, 0.27, 0.36, 0.43, 0.5, 0.57, 0.64, 0.73, 0.84];
  for (const t of cortes) { x.beginPath(); x.moveTo(t * 256, 6); x.lineTo(t * 256, 32); x.stroke(); }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
