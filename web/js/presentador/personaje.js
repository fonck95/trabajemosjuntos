// El presentador: una caricatura en 3D del candidato que explica las presentaciones del asistente (docs/presentador.md).
// Se arma entero con geometrías de three (sin modelos ni fotos): la cara llena y ancha en los pómulos, las mejillas que
// sube la sonrisa, los pliegues de la nariz a la boca, los ojos almendrados entrecerrados con sus patas de gallo, las
// cejas oscuras casi rectas, la nariz ancha de punta redonda, la sonrisa amplia con el labio de arriba fino y los
// dientes muy blancos; el pelo negro corto en cepillo, parado y peinado hacia arriba, con la línea de la frente recta y
// los lados cortos (degradé); la polo roja carmesí con su cuello, la tapeta de dos botones y el jinete bordado, el jean
// desteñido adelante, el reloj negro grande en la muñeca izquierda y la manilla roja con cuentas doradas en la derecha.
// Dibujo de caricatura: sombreado por tonos (MeshToonMaterial) y un contorno oscuro de grosor fijo en píxeles.
//
// El esqueleto son pivotes (Object3D), no un SkinnedMesh: cada pieza cuelga de su hueso y se mueve con él. El lado
// derecho del cuerpo (brazo, pierna, ojo, ceja, oreja) es una copia del izquierdo dentro de un grupo espejo
// (scale.x = -1): así la misma rotación local hace el mismo gesto en los dos lados (animador.js).
//
// La cara: la cabeza es una esfera esculpida (`deformarCabeza`: el óvalo, la mandíbula y el relieve de pómulos,
// mejillas, cuencas, hocico, mentón y pliegues). Lo que va dibujado sobre la piel (ojos, cejas, boca, pliegues, sombras)
// son tiras planas pegadas a la superficie con una grilla de alturas que se mide una vez rasterizando la cara
// (`alturas`), y que se rehacen en cada cuadro según la expresión (parpadear, mirar, alzar las cejas, hablar).
//
// Ejes: el personaje mira hacia +z y su izquierda queda en +x (la derecha de quien lo mira, como en la foto: el logo y
// el reloj de ese lado). Unidades: mide unos 2,35 de alto, con los pies en y = 0.
//
// Sin DOM obligatorio: sin `document` (Node, las pruebas) solo faltan las texturas de canvas (el logo, los dientes y
// las sombras suaves de la cara).
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export const COLORES = {
  piel: 0xc78b74, pielSombra: 0x9a5c4a, pielLinea: 0x7d4636, oreja: 0xc47b6a, labio: 0xb26a5c, labioSup: 0x8f4d42,
  pelo: 0x19141a, peloDegrade: 0x5e4b46, ceja: 0x1d1514,
  polo: 0xbe2537, poloOscuro: 0x951a2b, jeanClaro: 0x7d98c0, jean: 0x4b6798, jeanOscuro: 0x2c3f68,
  zapato: 0x3a2a22, suela: 0x2a201b,
  dientes: 0xfdfcf8, boca: 0x4a1416, lengua: 0xc0545a, ojo: 0xfbfaf6, iris: 0x2b1810, pupila: 0x080504,
  reloj: 0x18181b, bisel: 0x3c3f45, esfera: 0x111215, agujas: 0xe9e9e9, pulsera: 0xc0182b, cuenta: 0xdcab48,
  boton: 0xf6f2ea, contorno: 0x1e130e,
};

const R = 0.32;          // el radio de la cabeza (antes de esculpirla)

// ── Materiales ───────────────────────────────────────────────────────────────────────────────────────────────────
function rampaDeTonos(tonos, suaveRampa = false) {
  const datos = new Uint8Array(tonos.length * 4);
  tonos.forEach((t, i) => { const v = Math.round(Math.min(1, t) * 255); datos.set([v, v, v, 255], i * 4); });
  const tex = new THREE.DataTexture(datos, tonos.length, 1, THREE.RGBAFormat);
  tex.minFilter = tex.magFilter = suaveRampa ? THREE.LinearFilter : THREE.NearestFilter;
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

const raiz = (x) => Math.sqrt(Math.max(0, x));
const suave = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// ── La cabeza esculpida ──────────────────────────────────────────────────────────────────────────────────────────
// El relieve de la cara: [u, v, ancho, alto, cuánto, par] sobre la esfera de radio 1 (u = x, v = y; par: también del
// otro lado). Positivo sale, negativo se hunde; se suma solo adelante
const RELIEVE = [
  [0.37, -0.27, 0.16, 0.13, 0.055, true],   // las mejillas que sube la sonrisa
  [0.58, -0.05, 0.15, 0.15, 0.045, true],   // los pómulos
  [0.31, 0.33, 0.2, 0.075, 0.035, true],    // el arco de las cejas
  [0.33, 0.07, 0.12, 0.08, -0.012, true],   // las cuencas de los ojos
  [0, -0.5, 0.3, 0.19, 0.055, false],       // el hocico, alrededor de la boca
  [0, -0.9, 0.24, 0.1, 0.05, false],        // el mentón, ancho y redondo
  [0, -0.71, 0.19, 0.05, -0.025, false],    // el surco bajo el labio
  [0.2, -0.26, 0.045, 0.05, -0.03, true],   // el pliegue de la sonrisa: junto a la nariz
  [0.32, -0.4, 0.05, 0.06, -0.034, true],   //   al medio
  [0.46, -0.55, 0.05, 0.06, -0.026, true],  //   junto a la comisura
  [0.8, 0.3, 0.2, 0.2, -0.03, true],        // las sienes
  [0, 0.06, 0.07, 0.12, 0.02, false],       // el entrecejo y el puente de la nariz
];
function relieve(u, v, w) {
  if (w <= 0) return 0;
  let d = 0;
  for (const [cu, cv, su, sv, a, par] of RELIEVE) {
    for (const s of par ? [1, -1] : [1]) {
      const du = (u - s * cu) / su, dv = (v - cv) / sv;
      d += a * Math.exp(-0.5 * (du * du + dv * dv));
    }
  }
  return d * suave(0.05, 0.45, w);
}

/** La forma de la cabeza: el óvalo lleno, ancho en los pómulos, la mandíbula que se angosta sin hacer punta, la nuca
 * que baja al cuello y el relieve de la cara. Recibe un punto (Vector3) relativo al centro (en la esfera de radio R, o
 * de otro radio para el pelo) y lo devuelve esculpido. */
function deformarCabeza(v) {
  const r = v.length() || 1;
  const u = v.x / r, yn = v.y / r, w = v.z / r;
  v.multiplyScalar(1 + relieve(u, yn, w));
  let sx = 0.89, sz = 0.95, sy = 1.02;
  if (yn < 0) {
    const s = suave(0, 1, -yn);
    sx *= 1 - 0.02 * s - 0.09 * s * s;
    sz *= 1 - 0.05 * s;
    sy = 1.0;
  }
  sx *= 1 + 0.035 * Math.exp(-((yn + 0.08) ** 2) / 0.05);   // lo ancho de los pómulos
  if (v.z < 0) sz *= 1 - 0.28 * suave(0.1, 0.9, -yn) * suave(0, 0.6, -w);   // la nuca baja hacia el cuello
  v.set(v.x * sx, v.y * sy, v.z * sz);
  return v;
}

function suavizarNormales(geo) {
  geo.deleteAttribute('normal');
  geo.deleteAttribute('uv');
  const g = mergeVertices(geo, 1e-5);
  g.computeVertexNormals();
  return g;
}

/** Colorea los vértices de una geometría: f(posición, normal) → Color (el material multiplica por él) */
function tenir(geo, f) {
  const p = geo.attributes.position, n = geo.attributes.normal, col = new Float32Array(p.count * 3);
  const v = new THREE.Vector3(), m = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    const c = f(v.fromBufferAttribute(p, i), m.fromBufferAttribute(n, i));
    col.set([c.r, c.g, c.b], i * 3);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return geo;
}

/**
 * Arma el personaje. Devuelve {grupo, cuerpo, huesos, manos, cara, contorno, medidas, liberar()}:
 * - `huesos`: los pivotes que mueve animador.js (cadera, columna, pecho, cuello, cabeza, hombro/codo/muneca y
 *   muslo/rodilla/tobillo de cada lado: …I es el izquierdo, …D el derecho, que vive en un grupo espejo).
 * - `manos.I` / `manos.D`: {dedos: [[base, punta] × 4], pulgar, ponerPulgar(p)}: índice, medio, anular y meñique.
 * - `cara`: {boca: {poner({abrir, ancho, sonrisa})}, ojos: [{poner({abierto, sonrisa, mira})}],
 *   cejas: [{poner({alza, ceno})}]}.
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
  // la ropa en tonos (caricatura); la piel con una transición suave entre ellos: el relieve de la cara se lee sin
  // manchas
  const rampa = rampaDeTonos([0.52, 0.68, 0.82, 0.93, 1]);
  const rampaPiel = rampaDeTonos([0.66, 0.75, 0.84, 0.92, 0.97, 1], true);
  texs.add(rampa);
  texs.add(rampaPiel);
  const toon = (color, extra = {}) => {
    const m = new THREE.MeshToonMaterial({ color, gradientMap: rampa, ...extra });
    mats.add(m);
    return m;
  };
  const plano = (color, extra = {}) => { const m = new THREE.MeshBasicMaterial({ color, ...extra }); mats.add(m); return m; };
  const M = {
    piel: toon(COLORES.piel, { gradientMap: rampaPiel }), oreja: toon(COLORES.oreja, { gradientMap: rampaPiel }),
    pelo: toon(COLORES.pelo), peloDegrade: toon(0xffffff, { vertexColors: true }),
    polo: toon(COLORES.polo), poloDoble: toon(COLORES.polo, { side: THREE.DoubleSide }), poloOscuro: toon(COLORES.poloOscuro),
    jean: toon(0xffffff, { vertexColors: true }), jeanOscuro: toon(COLORES.jeanOscuro, { side: THREE.DoubleSide }),
    zapato: toon(COLORES.zapato), suela: toon(COLORES.suela), reloj: toon(COLORES.reloj), bisel: toon(COLORES.bisel),
    pulsera: toon(COLORES.pulsera), cuenta: toon(COLORES.cuenta), boton: toon(COLORES.boton),
    esfera: plano(COLORES.esfera), agujas: plano(COLORES.agujas), fosa: plano(0x4a2219),
  };

  // Una malla con su contorno (un hijo con la misma geometría y el material del contorno)
  function malla(geo, mat, { borde = true } = {}) {
    const m = new THREE.Mesh(g(geo), mat);
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
  const color = (hex) => new THREE.Color(hex);

  // ── El esqueleto ──────────────────────────────────────────────────────────────────────────────────────────────
  const grupo = new THREE.Group();
  grupo.name = 'presentador';
  const cuerpo = new THREE.Group();   // el salto, el estirón y la entrada (animador.js) mueven esto, no la raíz
  grupo.add(cuerpo);
  const huesos = {
    cadera: hueso('cadera', 'YXZ'), columna: hueso('columna', 'YXZ'), pecho: hueso('pecho', 'YXZ'),
    cuello: hueso('cuello', 'YXZ'), cabeza: hueso('cabeza', 'YXZ'),
  };
  huesos.cadera.position.y = 0.9;   // se corrige al final: las suelas en y = 0
  huesos.columna.position.y = 0.05;
  huesos.pecho.position.y = 0.28;
  huesos.cuello.position.set(0, 0.285, 0.008);
  huesos.cabeza.position.y = 0.105;
  cuerpo.add(huesos.cadera);
  huesos.cadera.add(huesos.columna);
  huesos.columna.add(huesos.pecho);
  huesos.pecho.add(huesos.cuello);
  huesos.cuello.add(huesos.cabeza);

  // Dónde queda la superficie de una malla vista de frente (o de lado): para pegarle el cuello, la tapeta, el logo y
  // las orejas
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

  // ── El torso: la polo carmesí ─────────────────────────────────────────────────────────────────────────────────
  const perfil = [[0.214, -0.21], [0.22, -0.18], [0.216, -0.12], [0.21, -0.03], [0.205, 0.08], [0.213, 0.2], [0.226, 0.31],
    [0.228, 0.39], [0.212, 0.455], [0.17, 0.5], [0.112, 0.527], [0.084, 0.537]].map(([r, y]) => new THREE.Vector2(r, y));
  let torsoGeo = new THREE.LatheGeometry(perfil, 56, Math.PI, Math.PI * 2);
  {
    const p = torsoGeo.attributes.position, v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      // los hombros anchos y la cintura más angosta (de nadador); el pecho algo adelante
      const ancho = 1.05 + 0.27 * suave(0.05, 0.42, v.y) - 0.07 * suave(0.43, 0.54, v.y);
      const fondo = 0.64 + 0.05 * suave(0.12, 0.34, v.y) * (v.z > 0 ? 1 : 0.4);
      p.setXYZ(i, v.x * ancho, v.y, v.z * fondo);
    }
  }
  torsoGeo = suavizarNormales(torsoGeo);
  const torso = malla(torsoGeo, M.polo);
  huesos.columna.add(torso);
  // el borde de abajo de la polo, un poco más ancho (la camiseta va por fuera del jean)
  const ruedo = malla(new THREE.TorusGeometry(0.22, 0.011, 8, 48).rotateX(Math.PI / 2).scale(1.05, 1, 0.645), M.polo, { borde: false });
  ruedo.position.y = -0.205;
  huesos.columna.add(ruedo);

  // El cuello de la polo: la tira alrededor del cuello, abierta adelante, y las dos puntas que caen sobre el pecho
  const tiraCuello = malla(new THREE.CylinderGeometry(0.118, 0.106, 0.052, 36, 1, true, Math.PI + 0.55, Math.PI * 2 - 1.1)
    .scale(1.06, 1, 0.9), M.poloDoble);
  tiraCuello.position.set(0, 0.553, -0.008);
  tiraCuello.rotation.x = -0.16;
  huesos.columna.add(tiraCuello);
  const forma = new THREE.Shape();
  forma.moveTo(0, 0.012);
  forma.lineTo(0.104, 0.032);
  forma.quadraticCurveTo(0.112, 0.004, 0.097, -0.024);
  forma.lineTo(0.03, -0.1);
  forma.quadraticCurveTo(0.004, -0.064, 0, 0.012);
  const solapaGeo = new THREE.ExtrudeGeometry(forma, { depth: 0.008, bevelEnabled: true, bevelThickness: 0.004,
    bevelSize: 0.004, bevelSegments: 2, curveSegments: 8 });
  for (const lado of [1, -1]) {
    const t = tocar(torso, 0.03 * lado, 0.515) || { p: new THREE.Vector3(0.03 * lado, 0.515, 0.11), n: new THREE.Vector3(0, 0.5, 1) };
    const s = malla(solapaGeo, M.polo);
    const pivote = new THREE.Group();
    pivote.position.copy(t.p).addScaledVector(t.n, 0.004);
    alinear(pivote, t.n);
    pivote.scale.x = lado;
    s.rotation.z = -0.12;
    pivote.add(s);
    huesos.columna.add(pivote);
  }
  // La tapeta con dos botones blancos (con su costura en cruz)
  const enPecho = tocar(torso, 0, 0.42) || { p: new THREE.Vector3(0, 0.42, 0.14), n: new THREE.Vector3(0, 0.2, 1) };
  const tapeta = malla(new THREE.BoxGeometry(0.048, 0.14, 0.01), M.polo);
  tapeta.position.copy(enPecho.p).add(new THREE.Vector3(0, 0.0, 0.002));
  alinear(tapeta, enPecho.n);
  huesos.columna.add(tapeta);
  for (const [i, y] of [[0, 0.032], [1, -0.028]]) {
    const b = malla(new THREE.CylinderGeometry(0.011, 0.011, 0.006, 18).rotateX(Math.PI / 2), M.boton, { borde: false });
    b.position.set(0, y, 0.008);
    b.name = `boton${i}`;
    tapeta.add(b);
    for (const a of [Math.PI / 4, -Math.PI / 4]) {
      const hilo = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0026, 0.012)), M.poloOscuro);
      hilo.position.set(0, y, 0.0115);
      hilo.rotation.z = a;
      tapeta.add(hilo);
    }
  }
  // El logo bordado (el jinete) en el pecho izquierdo
  if (documento?.createElement) {
    const tex = logoDelJinete(documento);
    if (tex) {
      texs.add(tex);
      const enLogo = tocar(torso, 0.11, 0.315);
      if (enLogo) {
        const logo = new THREE.Mesh(g(new THREE.PlaneGeometry(0.066, 0.066)), plano(0xffffff, { map: tex, transparent: true, depthWrite: false }));
        logo.position.copy(enLogo.p).addScaledVector(enLogo.n, 0.002);
        alinear(logo, enLogo.n);
        logo.renderOrder = 2;
        huesos.columna.add(logo);
      }
    }
  }

  // ── La cadera: el jean, más oscuro arriba ─────────────────────────────────────────────────────────────────────
  const jeanEn = (claro) => color(COLORES.jeanOscuro).lerp(color(COLORES.jean), Math.min(1, claro * 1.6))
    .lerp(color(COLORES.jeanClaro), Math.max(0, claro - 0.55) * 1.6);
  const pelvisGeo = elipsoide(0.206, 0.155, 0.128, 32, 20);
  tenir(pelvisGeo, (p, n) => jeanEn(0.35 * Math.max(0, n.z)));
  const pelvis = malla(pelvisGeo, M.jean);
  pelvis.position.y = -0.065;
  huesos.cadera.add(pelvis);

  // ── Los brazos ────────────────────────────────────────────────────────────────────────────────────────────────
  const manos = {};
  function brazo(lado) {
    const raiz = lado === 'D' ? espejo() : new THREE.Group();
    huesos.pecho.add(raiz);
    const bola = malla(new THREE.SphereGeometry(0.09, 24, 16), M.polo);
    bola.position.set(0.262, 0.185, 0);
    bola.scale.set(1, 1, 0.92);
    raiz.add(bola);
    const hombro = hueso(`hombro${lado}`, 'XZY'), codo = hueso(`codo${lado}`, 'XYZ'), muneca = hueso(`muneca${lado}`, 'XYZ');
    hombro.position.copy(bola.position);
    raiz.add(hombro);
    // la manga corta, ajustada al brazo, con su puño acanalado
    const manga = malla(new THREE.CylinderGeometry(0.09, 0.083, 0.18, 24, 1, true), M.poloDoble);
    manga.position.y = -0.08;
    hombro.add(manga);
    const puno = malla(new THREE.TorusGeometry(0.081, 0.011, 8, 28).rotateX(Math.PI / 2), M.poloOscuro, { borde: false });
    puno.position.y = -0.168;
    hombro.add(puno);
    // el brazo: el bíceps algo marcado
    const brazoGeo = new THREE.LatheGeometry([[0.0, -0.13], [0.04, -0.125], [0.053, -0.1], [0.06, -0.04], [0.062, 0.02],
      [0.058, 0.08], [0.05, 0.12], [0.0, 0.13]].map(([r, y]) => new THREE.Vector2(r, y)), 20);
    const sup = malla(suavizarNormales(brazoGeo), M.piel);
    sup.position.y = -0.17;
    sup.scale.z = 0.95;
    hombro.add(sup);
    codo.position.y = -0.305;
    hombro.add(codo);
    const codoBola = malla(new THREE.SphereGeometry(0.05, 16, 12), M.piel);
    hombro.add(codoBola);
    codoBola.position.y = -0.305;
    // el antebrazo: ancho cerca del codo, angosto en la muñeca
    const anteGeo = new THREE.LatheGeometry([[0.0, -0.272], [0.037, -0.26], [0.04, -0.22], [0.048, -0.15], [0.055, -0.08],
      [0.054, -0.03], [0.045, 0.02], [0.0, 0.03]].map(([r, y]) => new THREE.Vector2(r, y)), 20);
    const ante = malla(suavizarNormales(anteGeo).scale(1, 1, 0.9), M.piel);
    codo.add(ante);
    muneca.position.y = -0.27;
    codo.add(muneca);
    if (lado === 'I') reloj(codo); else manilla(codo);
    manos[lado] = mano(muneca);
    Object.assign(huesos, { [`hombro${lado}`]: hombro, [`codo${lado}`]: codo, [`muneca${lado}`]: muneca });
  }

  // El reloj negro y grande (muñeca izquierda): correa, caja con bisel y esfera negra hacia afuera (+x: el dorso, con la
  // palma hacia el cuerpo)
  function reloj(codo) {
    const r = new THREE.Group();
    r.position.y = -0.236;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.044, 0.012, 10, 28).rotateX(Math.PI / 2).scale(1, 1.6, 0.95), M.reloj));
    const caja = malla(new THREE.CylinderGeometry(0.037, 0.037, 0.02, 32).rotateZ(Math.PI / 2), M.reloj);
    caja.position.x = 0.05;
    r.add(caja);
    const bisel = new THREE.Mesh(g(new THREE.TorusGeometry(0.031, 0.0045, 8, 32).rotateY(Math.PI / 2)), M.bisel);
    bisel.position.x = 0.061;
    r.add(bisel);
    const esfera = new THREE.Mesh(g(new THREE.CircleGeometry(0.029, 32).rotateY(Math.PI / 2)), M.esfera);
    esfera.position.x = 0.0605;
    r.add(esfera);
    for (let i = 0; i < 12; i += 3) {
      const marca = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0022, 0.006).translate(0, 0.022, 0).rotateY(Math.PI / 2)), M.agujas);
      marca.position.x = 0.0612;
      marca.rotation.x = (i / 12) * Math.PI * 2;
      r.add(marca);
    }
    for (const [largo, ang] of [[0.02, 0.6], [0.014, 2.2]]) {
      const a = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0028, largo).translate(0, largo / 2, 0).rotateY(Math.PI / 2)), M.agujas);
      a.position.x = 0.0615;
      a.rotation.x = ang;
      r.add(a);
    }
  }
  // La manilla roja de hilo con cuentas doradas (muñeca derecha)
  function manilla(codo) {
    const r = new THREE.Group();
    r.position.y = -0.24;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.043, 0.0055, 6, 32).rotateX(Math.PI / 2), M.pulsera, { borde: false }));
    for (let i = 0; i < 9; i++) {
      const a = -1.5 + (3 * i) / 8;
      const c = new THREE.Mesh(g(new THREE.SphereGeometry(0.0095, 10, 8)), M.cuenta);
      c.position.set(Math.cos(a) * 0.046, 0, Math.sin(a) * 0.046);
      r.add(c);
    }
    // el nudo y los dos cabos que cuelgan
    const cabo = new THREE.Mesh(g(new THREE.CylinderGeometry(0.003, 0.003, 0.04, 6)), M.pulsera);
    cabo.position.set(-0.044, -0.02, 0.008);
    cabo.rotation.z = 0.2;
    r.add(cabo);
  }

  // La mano: la palma hacia el cuerpo (−x), los dedos hacia abajo (−y) y el pulgar adelante (+z)
  function mano(muneca) {
    const m = new THREE.Group();
    muneca.add(m);
    const palma = malla(new RoundedBoxGeometry(0.054, 0.1, 0.092, 3, 0.022), M.piel);
    palma.position.y = -0.055;
    m.add(palma);
    const dedos = [];
    const filas = [[0.031, 1.0], [0.0105, 1.08], [-0.0095, 1.02], [-0.029, 0.85]];
    for (const [z, largo] of filas) {
      const base = hueso('dedo', 'XYZ');
      base.position.set(0, -0.1, z);
      m.add(base);
      const f1 = malla(capsula(0.0152, 0.025 * largo, 8), M.piel);
      f1.position.y = -0.021 * largo;
      base.add(f1);
      const punta = hueso('punta', 'XYZ');
      punta.position.y = -0.043 * largo;
      base.add(punta);
      const f2 = malla(capsula(0.0142, 0.019 * largo, 8), M.piel);
      f2.position.y = -0.017 * largo;
      punta.add(f2);
      dedos.push([base, punta]);
    }
    const pulgar = hueso('pulgar', 'XYZ');
    pulgar.position.set(-0.008, -0.03, 0.044);
    m.add(pulgar);
    const p1 = malla(capsula(0.0175, 0.04, 8), M.piel);
    p1.position.y = -0.032;
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

  // ── Las piernas: el jean desteñido adelante, en los muslos y las rodillas ─────────────────────────────────────
  function pierna(lado) {
    const raiz = lado === 'D' ? espejo() : new THREE.Group();
    huesos.cadera.add(raiz);
    const muslo = hueso(`muslo${lado}`, 'XZY'), rodilla = hueso(`rodilla${lado}`, 'XYZ'), tobillo = hueso(`tobillo${lado}`, 'XYZ');
    muslo.position.set(0.108, -0.04, 0);
    raiz.add(muslo);
    const musloGeo = capsula(0.09, 0.27, 18);
    tenir(musloGeo, (p, n) => jeanEn(Math.max(0, n.z) ** 1.3 * (0.55 + 0.45 * Math.exp(-((p.y + 0.02) ** 2) / 0.012)) + 0.05));
    const mm = malla(musloGeo, M.jean);
    mm.position.y = -0.19;
    muslo.add(mm);
    rodilla.position.y = -0.4;
    muslo.add(rodilla);
    const pantGeo = new THREE.CapsuleGeometry(0.08, 0.27, 6, 18);
    tenir(pantGeo, (p, n) => jeanEn(Math.max(0, n.z) ** 1.3 * (0.35 + 0.5 * Math.exp(-((p.y - 0.12) ** 2) / 0.006))));
    const c = malla(pantGeo, M.jean);
    c.position.y = -0.17;
    rodilla.add(c);
    // el bota del jean, recto, que cae sobre el zapato
    const bota = malla(new THREE.CylinderGeometry(0.082, 0.088, 0.07, 24, 1, true), M.jeanOscuro);
    bota.position.y = -0.345;
    rodilla.add(bota);
    tobillo.position.y = -0.395;
    rodilla.add(tobillo);
    const zapato = malla(elipsoide(0.07, 0.05, 0.13, 24, 14), M.zapato);
    zapato.position.set(0, -0.012, 0.045);
    tobillo.add(zapato);
    const suela = malla(new THREE.CylinderGeometry(1, 1, 1, 24).scale(0.073, 0.022, 0.136), M.suela, { borde: false });
    suela.position.set(0, -0.045, 0.045);
    tobillo.add(suela);
    Object.assign(huesos, { [`muslo${lado}`]: muslo, [`rodilla${lado}`]: rodilla, [`tobillo${lado}`]: tobillo });
  }
  pierna('I');
  pierna('D');

  // ── El cuello y la cabeza ─────────────────────────────────────────────────────────────────────────────────────
  const cuello = malla(new THREE.CylinderGeometry(0.088, 0.098, 0.2, 20), M.piel);
  cuello.position.y = 0.045;
  huesos.cuello.add(cuello);
  const craneo = new THREE.Group();
  craneo.position.set(0, 0.305, 0.012);
  huesos.cabeza.add(craneo);
  let cabezaGeo = new THREE.SphereGeometry(R, 96, 72);
  {
    const p = cabezaGeo.attributes.position, v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) { deformarCabeza(v.fromBufferAttribute(p, i)); p.setXYZ(i, v.x, v.y, v.z); }
  }
  cabezaGeo = suavizarNormales(cabezaGeo);
  const cabeza = malla(cabezaGeo, M.piel);
  craneo.add(cabeza);
  const alto = alturas(cabezaGeo);
  const cara = construirCara(craneo, cabeza);
  pelo(craneo);

  /** La altura (z) de la cara vista de frente en cada (x, y): la superficie rasterizada una vez en una grilla fina
   * (lo de adelante de cada triángulo), para pegar lo que va dibujado sin lanzar un rayo por punto. */
  function alturas(geo) {
    const X0 = -0.32, Y0 = -0.42, P = 0.0035, NX = Math.ceil(0.64 / P) + 1, NY = Math.ceil(0.78 / P) + 1;
    const zb = new Float32Array(NX * NY).fill(-1);
    const pos = geo.attributes.position.array, idx = geo.index.array;
    for (let t = 0; t < idx.length; t += 3) {
      const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
      const ax = pos[a], ay = pos[a + 1], az = pos[a + 2], bx = pos[b], by = pos[b + 1], bz = pos[b + 2];
      const cx = pos[c], cy = pos[c + 1], cz = pos[c + 2];
      if (az < 0 && bz < 0 && cz < 0) continue;
      const den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (Math.abs(den) < 1e-12) continue;
      const i0 = Math.max(0, Math.floor((Math.min(ax, bx, cx) - X0) / P)), i1 = Math.min(NX - 1, Math.ceil((Math.max(ax, bx, cx) - X0) / P));
      const j0 = Math.max(0, Math.floor((Math.min(ay, by, cy) - Y0) / P)), j1 = Math.min(NY - 1, Math.ceil((Math.max(ay, by, cy) - Y0) / P));
      for (let j = j0; j <= j1; j++) {
        const y = Y0 + j * P;
        for (let i = i0; i <= i1; i++) {
          const x = X0 + i * P;
          const l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den;
          const l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den;
          const l3 = 1 - l1 - l2;
          if (l1 < -1e-6 || l2 < -1e-6 || l3 < -1e-6) continue;
          const z = l1 * az + l2 * bz + l3 * cz;
          const k = j * NX + i;
          if (z > zb[k]) zb[k] = z;
        }
      }
    }
    const zEn = (x, y) => {
      const fx = Math.max(0, Math.min(NX - 1.001, (x - X0) / P)), fy = Math.max(0, Math.min(NY - 1.001, (y - Y0) / P));
      const i = Math.floor(fx), j = Math.floor(fy), u = fx - i, w = fy - j;
      const a = zb[j * NX + i], b = zb[j * NX + i + 1], c = zb[(j + 1) * NX + i], d = zb[(j + 1) * NX + i + 1];
      // fuera de la cara (una celda sin superficie): la altura de las vecinas que sí tienen, y nunca hacia atrás
      if (a < 0 || b < 0 || c < 0 || d < 0) return Math.max(0, a, b, c, d);
      return (a * (1 - u) + b * u) * (1 - w) + (c * (1 - u) + d * u) * w;
    };
    const normal = (x, y) => {
      const h = 0.004;
      return new THREE.Vector3(-(zEn(x + h, y) - zEn(x - h, y)) / (2 * h), -(zEn(x, y + h) - zEn(x, y - h)) / (2 * h), 1).normalize();
    };
    return { zEn, normal, punto: (x, y) => new THREE.Vector3(x, y, zEn(x, y)) };
  }

  // El pelo: corto en cepillo, parado y peinado hacia arriba y un poco adelante; la línea de la frente recta, las
  // entradas apenas marcadas, los lados y la nuca cortos (en degradé hacia la piel) y la patilla corta
  function pelo(padre) {
    // el límite (grados desde la coronilla) según el rumbo: 0 al frente, π atrás
    const limite = [[0, 49], [0.4, 50], [0.68, 47], [0.95, 64], [1.15, 96], [1.27, 98], [1.4, 78], [1.85, 82], [2.3, 106], [Math.PI, 118]];
    const enLimite = (az) => {
      for (let i = 1; i < limite.length; i++) {
        const [a1, l1] = limite[i - 1], [a2, l2] = limite[i];
        if (az <= a2) return l1 + (l2 - l1) * (az - a1) / (a2 - a1);
      }
      return limite[limite.length - 1][1];
    };
    // el grueso del pelo: arriba el cepillo, adelante un frente parado, a los lados casi al ras
    const grueso = (t, az) => {
      const frente = suave(0.35, 0.85, Math.cos(az));
      return 0.008 + 0.06 * (1 - suave(0.45, 0.85, t)) * (0.7 + 0.3 * frente) + frente * 0.045 * suave(0.55, 1, t) - 0.012 * (1 - suave(0, 0.35, t));
    };
    const NA = 120, NT = 30, pos = [], col = [], idx = [];
    const v = new THREE.Vector3(), n = new THREE.Vector3();
    const negro = color(COLORES.pelo), degrade = color(COLORES.peloDegrade);
    const punto = (az, th, extra) => {
      n.set(Math.sin(th) * Math.sin(az), Math.cos(th), Math.sin(th) * Math.cos(az));
      v.copy(n).multiplyScalar(R);
      deformarCabeza(v);
      return v.addScaledVector(n, extra);
    };
    for (let i = 0; i <= NA; i++) {
      const az = -Math.PI + (2 * Math.PI * i) / NA, tope = (enLimite(Math.abs(az)) * Math.PI) / 180;
      const lado = 1 - suave(0.35, 0.85, Math.cos(az));
      for (let j = 0; j <= NT + 1; j++) {
        // la última fila baja del borde a la piel: el frente del cepillo (a los lados casi no se nota)
        const t = Math.min(1, j / NT);
        const p = punto(az, tope * t, j > NT ? 0.001 : grueso(t, az));
        pos.push(p.x, p.y, p.z);
        const c = negro.clone().lerp(degrade, lado * suave(0.72, 1, t) * 0.85);
        col.push(c.r, c.g, c.b);
      }
    }
    const F = NT + 2;
    for (let i = 0; i < NA; i++) {
      for (let j = 0; j < F - 1; j++) {
        const a = i * F + j, b = a + 1, c = a + F, d = c + 1;
        idx.push(a, b, c, b, d, c);
      }
    }
    let s = new THREE.BufferGeometry();
    s.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    s.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    s.setIndex(idx);
    s = mergeVertices(s, 1e-5);
    s.computeVertexNormals();
    padre.add(malla(s, M.peloDegrade));
    // la textura del cepillo: mechones cortos y finos, más largos y parados en el frente
    const r = azar(1896);
    const conos = [];
    const dir = new THREE.Vector3(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
    const doblar = (geo, hacia, k) => {   // el mechón se curva hacia `hacia` (más en la punta)
      const p = geo.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const t = (p.getY(i) + 0.5 * geo.parameters.height) / geo.parameters.height;
        p.setXYZ(i, p.getX(i) + hacia.x * k * t * t, p.getY(i), p.getZ(i) + hacia.z * k * t * t);
      }
      return geo;
    };
    for (let i = 0; i < 700; i++) {
      const delFrente = i < 90;
      const az = delFrente ? (r() * 2 - 1) * 0.7 : (r() * 2 - 1) * Math.PI;
      const tope = (enLimite(Math.abs(az)) * Math.PI) / 180;
      const t = delFrente ? 0.86 + 0.12 * r() : Math.min(0.9, Math.pow(r(), 0.85) * 0.92);
      const frente = suave(0.35, 0.85, Math.cos(az));
      if (!delFrente && t > 0.5 && frente < 0.3 && r() < 0.85) continue;   // los lados, cortos: pocos mechones
      const base = punto(az, tope * t, grueso(t, az) - 0.012).clone();
      const nn = n.clone();
      dir.copy(nn).multiplyScalar(0.55).add(new THREE.Vector3(0, 0.75, 0.18 + 0.32 * frente))
        .add(new THREE.Vector3(r() - 0.5, (r() - 0.5) * 0.4, r() - 0.5).multiplyScalar(0.35)).normalize();
      const largo = (0.018 + 0.02 * r()) * (delFrente ? 1.6 : 1) * (1 - 0.6 * suave(0.5, 0.88, t) * (1 - frente));
      const cono = doblar(new THREE.ConeGeometry(0.011 + 0.01 * r(), largo, 4, 2), { x: (r() - 0.5) * 0.4, z: 0.5 }, 0.012);
      q.setFromUnitVectors(Y, dir);
      cono.applyQuaternion(q);
      cono.translate(base.x + dir.x * (largo * 0.5 - 0.004), base.y + dir.y * (largo * 0.5 - 0.004), base.z + dir.z * (largo * 0.5 - 0.004));
      cono.deleteAttribute('uv');
      conos.push(cono.toNonIndexed());
    }
    const puntas = mergeGeometries(conos);
    for (const c of conos) c.dispose();
    puntas.computeVertexNormals();
    padre.add(new THREE.Mesh(g(puntas), M.pelo));
  }

  // Lo que va dibujado sobre la piel: tiras planas que se pegan a la cara con la grilla de alturas; en cada cuadro se
  // rehacen según la forma pedida. `dz` las separa un poco de la piel (y el polygonOffset, del resto)
  function capa(padre, colorHex, orden, extra = {}) {
    return plano(colorHex, { side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2 - orden,
      polygonOffsetUnits: -4 - 2 * orden, ...extra });
  }
  function montar(padre, geo, mat, orden) {
    const m = new THREE.Mesh(g(geo), mat);
    m.renderOrder = 3 + orden;
    m.frustumCulled = false;
    padre.add(m);
    return m;
  }
  /** Una tira entre dos curvas: devuelve poner(cx, a, arriba(u), abajo(u), dz), con u de −1 a 1 a lo ancho
   * (x = cx + u·a). `y(u)` puede inclinarla: así sirven para trazos cortos en diagonal */
  function tira(padre, colorHex, orden, extra = {}, N = 28, F = 4) {
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
    const m = montar(padre, geo, capa(padre, colorHex, orden, extra), orden);
    const poner = (cx, a, arriba, abajo, dz) => {
      for (let i = 0; i <= N; i++) {
        const u = -1 + (2 * i) / N, x = cx + u * a, y1 = arriba(u), yb = Math.min(y1, abajo(u));
        for (let j = 0; j <= F; j++) {
          const y = y1 + ((yb - y1) * j) / F, k = (i * (F + 1) + j) * 3;
          pos[k] = x; pos[k + 1] = y; pos[k + 2] = alto.zEn(x, y) + dz;
        }
      }
      geo.attributes.position.needsUpdate = true;
      geo.computeBoundingSphere();
    };
    poner.malla = m;
    return poner;
  }
  /** Un disco (con uv de 0 a 1, para las sombras suaves): devuelve poner(cx, cy, rx, ry, dz) */
  function disco(padre, colorHex, orden, extra = {}, N = 24) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array((N + 1) * 3), uv = new Float32Array((N + 1) * 2), idx = [];
    for (let i = 0; i < N; i++) idx.push(0, 1 + i, 1 + ((i + 1) % N));
    uv.set([0.5, 0.5], 0);
    for (let i = 0; i < N; i++) { const a = (i / N) * Math.PI * 2; uv.set([0.5 + Math.cos(a) / 2, 0.5 + Math.sin(a) / 2], (1 + i) * 2); }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    geo.setIndex(idx);
    const m = montar(padre, geo, capa(padre, colorHex, orden, extra), orden);
    const poner = (cx, cy, rx, ry = rx, dz = 0.002) => {
      pos[0] = cx; pos[1] = cy; pos[2] = alto.zEn(cx, cy) + dz;
      for (let i = 0; i < N; i++) {
        const a = (i / N) * Math.PI * 2, x = cx + Math.cos(a) * rx, y = cy + Math.sin(a) * ry;
        pos.set([x, y, alto.zEn(x, y) + dz], (1 + i) * 3);
      }
      geo.attributes.position.needsUpdate = true;
      geo.computeBoundingSphere();
    };
    poner.malla = m;
    return poner;
  }

  // La cara
  function construirCara(padre, cabeza) {
    const ojos = [], cejas = [];
    // Las sombras suaves: el calor de las mejillas y la nariz, la sombra bajo los pómulos y bajo el labio
    const nube = documento?.createElement ? degradado(documento) : null;
    if (nube) {
      texs.add(nube);
      const suaves = { map: nube, transparent: true, depthWrite: false };
      for (const s of [1, -1]) {
        disco(padre, 0xd9756a, 0, { ...suaves, opacity: 0.32 })(0.112 * s, -0.082, 0.062, 0.05, 0.0015);
        disco(padre, 0x6e3a2c, 0, { ...suaves, opacity: 0.12 })(0.18 * s, -0.16, 0.05, 0.07, 0.0015);
      }
      disco(padre, 0xd9756a, 0, { ...suaves, opacity: 0.24 })(0, -0.07, 0.04, 0.032, 0.0015);
      disco(padre, 0x6e3a2c, 0, { ...suaves, opacity: 0.22 })(0, -0.245, 0.05, 0.016, 0.0015);
      // la sombra bajo la nariz y a los lados del puente
      disco(padre, 0x5a2d22, 0, { ...suaves, opacity: 0.35 })(0, -0.108, 0.05, 0.016, 0.0015);
      for (const s of [1, -1]) disco(padre, 0x6e3a2c, 0, { ...suaves, opacity: 0.16 })(0.034 * s, -0.025, 0.016, 0.045, 0.0015);
    }
    // El blanco del ojo marca el stencil y el iris solo se pinta donde lo marcó: así el iris nunca se sale del ojo
    const marca = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp };
    const dentro = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc, stencilZPass: THREE.KeepStencilOp };
    const linea = (o = 0.75) => ({ transparent: true, opacity: o, depthWrite: false });
    for (const lado of ['I', 'D']) {
      const raizLado = lado === 'D' ? espejo() : new THREE.Group();
      padre.add(raizLado);
      // ── el ojo: almendrado, el párpado de abajo subido por la sonrisa; u = −1 es el lagrimal, 1 la cola ──
      const OX = 0.1, OY = 0.02, A = 0.046;
      const pliegueSup = tira(raizLado, COLORES.pielLinea, 2, linea(0.55), 20, 2);
      const blanco = tira(raizLado, COLORES.ojo, 2, marca, 24, 4);
      const pestanas = tira(raizLado, COLORES.contorno, 5, {}, 24, 2);
      const parpadoBajo = tira(raizLado, COLORES.pielLinea, 5, linea(0.7), 24, 2);
      const bolsa = tira(raizLado, COLORES.pielLinea, 2, linea(0.45), 20, 2);
      const patas = [0, 1, 2].map(() => tira(raizLado, COLORES.pielLinea, 2, linea(0.5), 6, 1));
      const iris = disco(raizLado, COLORES.iris, 3, dentro);
      const anillo = disco(raizLado, 0x4a2c1c, 3, dentro);
      const pupila = disco(raizLado, COLORES.pupila, 4, dentro, 20);
      const brillo = disco(raizLado, 0xffffff, 5, dentro, 12);
      let ultimo = '';
      /** abierto 0..1 (0: cerrado), sonrisa 0..1 (el párpado de abajo sube y aparecen las patas de gallo), mira [x, y]
       * de −1 a 1 */
      const poner = ({ abierto = 1, sonrisa = 1, mira = [0, 0] } = {}) => {
        const clave = `${abierto.toFixed(3)}|${sonrisa.toFixed(3)}|${mira[0].toFixed(3)}|${mira[1].toFixed(3)}`;
        if (clave === ultimo) return;
        ultimo = clave;
        const hb = 0.016 - 0.008 * sonrisa;
        const abajo = (u) => OY - hb * Math.pow(Math.max(0, 1 - u * u), 0.8) + 0.004 * sonrisa * (u + 1) * 0.5 - 0.002 * u;
        const ht = 0.023 - 0.004 * sonrisa;
        const arribaAbierto = (u) => OY + ht * Math.pow(Math.max(0, 1 - u * u), 0.5) * (1 - 0.14 * u) - 0.002 * u;
        const arriba = (u) => { const b = abajo(u); return b + (arribaAbierto(u) - b) * abierto; };
        blanco(OX, A, arriba, abajo, 0.0015);
        pestanas(OX + 0.002, A * 1.07, (u) => arriba(u / 1.03) + 0.0055 * Math.pow(Math.max(0, 1 - u * u), 0.3) + 0.0008,
          (u) => arriba(u / 1.03) - 0.0006, 0.0024);
        parpadoBajo(OX, A * 0.92, (u) => abajo(u / 0.92) + 0.0006, (u) => abajo(u / 0.92) - 0.0022 * raiz(1 - u * u), 0.0022);
        // el pliegue del párpado de arriba, que sigue al ojo abierto
        pliegueSup(OX + 0.004, A * 0.92, (u) => arribaAbierto(u / 0.95) + 0.011 + 0.002 * raiz(1 - u * u),
          (u) => arribaAbierto(u / 0.95) + 0.0085, 0.0018);
        // la bolsa de la sonrisa bajo el ojo y las patas de gallo en la cola
        bolsa(OX + 0.008, A * 0.85, (u) => OY - 0.026 - 0.008 * raiz(1 - u * u) + 0.006 * u, (u) => OY - 0.0285 - 0.008 * raiz(1 - u * u)
          + 0.006 * u, 0.0016);
        const cola = OX + A + 0.006;
        const trazos = [[0.012, 0.007], [0.014, -0.001], [0.011, -0.012]];
        trazos.forEach(([largo, sube], k) => {
          const y0 = OY + 0.004 - k * 0.009;
          patas[k](cola + largo / 2, largo / 2, (u) => y0 + sube * (u + 1) / 2 + 0.0011, (u) => y0 + sube * (u + 1) / 2 - 0.0011, 0.0016);
          patas[k].malla.visible = sonrisa > 0.4;
        });
        const mx = OX + mira[0] * 0.015, my = OY + 0.004 + mira[1] * 0.007;
        iris(mx, my, 0.0215, 0.0215, 0.0025);
        anillo(mx, my, 0.0215, 0.0215, 0.00245);
        iris(mx, my, 0.019, 0.019, 0.0026);
        pupila(mx, my, 0.0105, 0.0105, 0.0032);
        brillo(mx + 0.0065, my + 0.008, 0.005, 0.005, 0.0038);
      };
      poner();
      ojos.push({ poner });
      // ── la ceja: oscura, de grosor medio, casi recta con un arco leve hacia la cola ──
      const ceja = tira(raizLado, COLORES.ceja, 1, {}, 26, 3);
      let ultimaCeja = '';
      const ponerCeja = ({ alza = 0, ceno = 0 } = {}) => {
        const clave = `${alza.toFixed(3)}|${ceno.toFixed(3)}`;
        if (clave === ultimaCeja) return;
        ultimaCeja = clave;
        const CX = 0.098, CA = 0.064;
        const base = (u) => 0.088 + 0.01 * (1 - ((u - 0.3) / 1.3) ** 2) + 0.004 * u + 0.016 * alza * (1 - 0.3 * u)
          - 0.008 * ceno * (1 - u) / 2;
        const grosorCeja = (u) => 0.0135 - 0.006 * (u + 1) / 2;
        ceja(CX, CA, (u) => base(u) + grosorCeja(u) * 0.55 * raiz(1 - (u * 0.98) ** 8),
          (u) => base(u) - grosorCeja(u) * 0.45 * raiz(1 - (u * 0.98) ** 8), 0.003);
      };
      ponerCeja();
      cejas.push({ poner: ponerCeja });
      // ── la oreja: algo despegada, con el borde (hélix), la concha y el lóbulo ──
      const o = tocar(cabeza, 3, -0.015, -0.025, [-1, 0, 0]) || { p: new THREE.Vector3(0.25, -0.015, -0.025) };
      const oreja = new THREE.Group();
      oreja.position.copy(o.p).add(new THREE.Vector3(0.002, 0, -0.008));
      oreja.rotation.set(0, 0.5, 0.06);
      raizLado.add(oreja);
      oreja.scale.setScalar(1.15);
      oreja.add(malla(elipsoide(0.03, 0.072, 0.05, 20, 14), M.oreja));
      const helix = malla(new THREE.TorusGeometry(0.045, 0.011, 8, 22, Math.PI * 1.25).rotateY(Math.PI / 2).rotateX(-Math.PI * 0.42)
        .scale(1, 1.45, 1), M.oreja);
      helix.position.set(0.012, 0.004, -0.004);
      oreja.add(helix);
      const concha = new THREE.Mesh(g(elipsoide(0.012, 0.038, 0.024, 14, 10)), plano(0x8a4a3b));
      concha.position.set(0.025, 0.004, 0.006);
      oreja.add(concha);
      const lobulo = malla(elipsoide(0.022, 0.02, 0.022, 14, 10), M.oreja);
      lobulo.position.set(0.006, -0.06, 0.008);
      oreja.add(lobulo);
      // ── el pliegue de la sonrisa: de la aleta de la nariz a la comisura y un poco más ──
      const pliegue = tira(raizLado, COLORES.pielLinea, 1, linea(0.5), 22, 2);
      const yP = (x) => -0.086 - 1.05 * (x - 0.052) - 5 * (x - 0.052) ** 2;
      pliegue(0.087, 0.034, (u) => yP(0.087 + u * 0.034) + 0.002 * raiz(1 - u * u), (u) => yP(0.087 + u * 0.034)
        - 0.002 * raiz(1 - u * u), 0.0016);
    }
    // ── la nariz: ancha, de punta redonda, con las aletas marcadas y las fosas ──
    const np = alto.punto(0, -0.064);
    const partes = [
      elipsoide(0.046, 0.036, 0.036, 22, 16).translate(0, -0.008, 0.012),
      elipsoide(0.029, 0.024, 0.024, 16, 10).translate(0.038, -0.018, -0.006),
      elipsoide(0.029, 0.024, 0.024, 16, 10).translate(-0.038, -0.018, -0.006),
      capsula(0.017, 0.04, 10).rotateX(0.3).translate(0, 0.026, -0.014),
    ];
    for (const x of partes) x.deleteAttribute('uv');
    const narizGeo = suavizarNormales(mergeGeometries(partes.map((x) => x.toNonIndexed())));
    for (const x of partes) x.dispose();
    const nariz = malla(narizGeo, M.piel);
    nariz.position.copy(np).add(new THREE.Vector3(0, 0, -0.02));
    padre.add(nariz);
    for (const s of [1, -1]) {
      const fosa = new THREE.Mesh(g(elipsoide(0.0115, 0.0065, 0.01, 12, 8)), M.fosa);
      fosa.position.set(0.017 * s, -0.033, 0.006);
      fosa.rotation.z = 0.35 * s;
      nariz.add(fosa);
    }
    const boca = crearBoca(padre);
    return { ojos, cejas, boca, nariz };
  }

  // La boca: los labios (el de arriba fino, el de abajo lleno), el fondo oscuro, la lengua y las dos filas de dientes,
  // que se rehacen en cada cuadro según qué tan abierta, ancha y sonriente está
  function crearBoca(padre) {
    const Y0 = -0.172;
    const texDientes = documento?.createElement ? dibujoDeDientes(documento) : null;
    if (texDientes) texs.add(texDientes);
    const labioInf = tira(padre, COLORES.labio, 0);
    const labioSup = tira(padre, COLORES.labioSup, 0);
    const fondo = tira(padre, COLORES.boca, 1);
    const lengua = tira(padre, COLORES.lengua, 2);
    const dientesSup = tira(padre, COLORES.dientes, 3, texDientes ? { map: texDientes, color: 0xffffff } : {});
    const dientesInf = tira(padre, 0xf1ede4, 3);
    let ultimo = '';
    /** abrir 0..1 (0: la sonrisa de la foto, con los dientes de arriba a la vista), ancho 0.7..1.15 (menos: una «o»),
     * sonrisa 0..1 (las comisuras arriba) */
    function poner({ abrir = 0, ancho = 1, sonrisa = 1 } = {}) {
      const clave = `${abrir.toFixed(3)}|${ancho.toFixed(3)}|${sonrisa.toFixed(3)}`;
      if (clave === ultimo) return;
      ultimo = clave;
      const w = 0.1 * (0.88 + 0.12 * sonrisa) * ancho;
      const arriba = (u) => Y0 + 0.002 + 0.014 * sonrisa * u ** 4 + 0.008 * sonrisa * u * u - 0.004 * (1 - sonrisa) * (1 - u * u);
      const hondo = (u) => (0.036 + 0.064 * abrir - 0.01 * (1 - ancho)) * Math.pow(Math.max(0, 1 - u * u), 0.62);
      const abajo = (u) => arriba(u) - hondo(u);
      labioSup(0, w * 1.02, (u) => arriba(u) + 0.0042 * raiz(1 - u * u) + 0.0006, (u) => arriba(u) - 0.0004, 0.0015);
      labioInf(0, w * 1.0, (u) => abajo(u) + 0.0008, (u) => abajo(u) - (0.016 + 0.004 * abrir) * Math.pow(Math.max(0, 1 - u * u), 0.5), 0.0015);
      fondo(0, w, arriba, abajo, 0.002);
      lengua(0, w * 0.6, (u) => abajo(u * 0.6) + 0.4 * hondo(u * 0.6) * Math.min(1, abrir * 1.6) * (1 - u * u),
        (u) => abajo(u * 0.6), 0.0025);
      dientesSup(0, w * 0.96, (u) => arriba(u * 0.96), (u) => arriba(u * 0.96) - Math.min(0.026 * Math.pow(Math.max(0, 1 - u * u), 0.28),
        0.72 * hondo(u * 0.96)), 0.003);
      dientesInf(0, w * 0.8, (u) => abajo(u * 0.8) + Math.min(0.012 * Math.pow(Math.max(0, 1 - u * u), 0.4),
        0.26 * hondo(u * 0.8)), (u) => abajo(u * 0.8), 0.003);
    }
    poner();
    return { poner };
  }

  // Las suelas en el piso (y = 0) y las medidas para encuadrar: la altura de los hombros y de la coronilla
  grupo.updateMatrixWorld(true);
  const pies = new THREE.Box3();
  for (const l of ['I', 'D']) pies.expandByObject(huesos[`tobillo${l}`]);
  huesos.cadera.position.y -= pies.min.y;
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

// Una mancha redonda que se desvanece hacia el borde (las sombras suaves de la cara)
function degradado(doc) {
  const c = doc.createElement('canvas');
  c.width = c.height = 64;
  const x = c.getContext?.('2d');
  if (!x) return null;
  const gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.5, 'rgba(255,255,255,0.55)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = gr;
  x.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

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
