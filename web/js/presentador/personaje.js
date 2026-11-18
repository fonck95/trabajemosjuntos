// El presentador: una caricatura en 3D del candidato que explica las presentaciones del asistente (docs/presentador.md).
// Se arma entero con geometrías de three (sin modelos ni fotos): la cara llena y ancha en los pómulos, las mejillas que
// sube la sonrisa, los pliegues de la nariz a la boca, los ojos almendrados entrecerrados con sus patas de gallo, las
// cejas castañas casi rectas, la nariz ancha y trapezoidal (la punta redonda fundida con las aletas), la sonrisa ancha y
// plana, de medialuna, con el labio de abajo lleno y rosado y los dientes muy blancos; las orejas grandes y despegadas,
// abiertas hacia adelante; el pelo gris muy oscuro, corto en cepillo, parado y peinado hacia arriba y hacia su izquierda,
// en mechones con brillos de gel, la línea de la frente recta y los lados cortos (degradé gris). El cuerpo de un
// adulto robusto (hombros anchos en pendiente, brazos fuertes, manos grandes) con la polo roja carmesí: el cuello
// grande abierto en V hasta el botón de arriba, la tapeta larga de dos botones y el jinete bordado; el jean
// stonewash, el reloj negro grande en la muñeca izquierda y la manilla roja con cuentas doradas en la derecha.
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
// el reloj de ese lado). Unidades: mide unos 2,3 de alto, con los pies en y = 0.
//
// Sin DOM obligatorio: sin `document` (Node, las pruebas) solo faltan las texturas de canvas (el logo, los dientes y
// las sombras suaves de la cara).
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export const COLORES = {
  piel: 0xdca291, pielBrazo: 0xcf9480, pielSombra: 0x9e5e50, pielLinea: 0x8a4f45, oreja: 0xeca292, labio: 0xd68c92, labioSup: 0xc6827e,
  labioBrillo: 0xe6a9ab,
  pelo: 0x29252e, peloDegrade: 0x928684, ceja: 0x5d4138,
  polo: 0xbe2537, poloOscuro: 0x951a2b, jeanClaro: 0x97a8c5, jean: 0x445d8a, jeanOscuro: 0x283a5f,
  zapato: 0x3a2a22, suela: 0x2a201b,
  dientes: 0xfdfcf8, boca: 0x4a1416, lengua: 0xc0545a, ojo: 0xe0d3ca, iris: 0x2e1d17, pupila: 0x080504,
  reloj: 0x1b1b20, bisel: 0x4a4d57, esfera: 0x3a3b45, agujas: 0xf2f2f2, pulsera: 0xc8303a, cuenta: 0xe4c47e,
  boton: 0xf2e6e6, contorno: 0x1e130e, contornoPiel: 0x6e3b2e,
};

const R = 0.32;          // el radio de la cabeza (antes de esculpirla)

// ── Materiales ───────────────────────────────────────────────────────────────────────────────────────────────────
// La rampa de tonos del sombreado (MeshToonMaterial la lee según cuánto mira cada punto a cada luz). `tinte`: el
// exponente de cada canal (r, g, b); con g y b mayores que 1 los tonos oscuros salen más rojizos que los claros
function rampaDeTonos(tonos, suaveRampa = false, tinte = [1, 1, 1]) {
  const datos = new Uint8Array(tonos.length * 4);
  tonos.forEach((t, i) => datos.set([...tinte.map((e) => Math.round(Math.min(1, t) ** e * 255)), 255], i * 4));
  const tex = new THREE.DataTexture(datos, tonos.length, 1, THREE.RGBAFormat);
  tex.minFilter = tex.magFilter = suaveRampa ? THREE.LinearFilter : THREE.NearestFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/** El contorno de caricatura: el casco invertido (las caras de atrás) empujado hacia afuera `grosor` píxeles en la
 * pantalla, a lo largo de la normal. `uniformes` se comparte entre todos: el presentador fija la resolución. El casco
 * se corre además un poco hacia atrás, a lo largo del rayo de la cámara (no cambia dónde cae en la pantalla): así no
 * asoma en motas por delante de la piel en las zonas cóncavas o de canto (las cuencas, los costados del puente, los
 * lados de la polo), y la silueta y los bordes que están más adelante que eso (la nariz, las orejas, el pelo) siguen igual */
function materialContorno(uniformes) {
  return new THREE.ShaderMaterial({
    uniforms: uniformes,
    side: THREE.BackSide,
    vertexShader: `
      uniform float grosor;
      uniform vec2 resolucion;
      void main() {
        vec4 vista = modelViewMatrix * vec4(position, 1.0);
        vista.xyz += normalize(vista.xyz) * 0.006;
        vec3 n = normalize(normalMatrix * normal);
        vec4 clip = projectionMatrix * vista;
        vec2 d = (projectionMatrix * vec4(n, 0.0)).xy;
        float l = length(d);
        if (l > 1e-5) clip.xy += (d / l) * grosor * 2.0 / resolucion * clip.w;
        gl_Position = clip;
      }`,
    fragmentShader: `
      uniform vec3 color;
      void main() {
        gl_FragColor = vec4(color, 1.0);
        #include <colorspace_fragment>
      }`,   // el color pasa al espacio de la pantalla (sRGB), como el de los demás materiales: si no, sale casi negro
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
  [0.44, -0.24, 0.2, 0.13, 0.068, true],    // las mejillas que sube la sonrisa (las «manzanas», algo exageradas)
  [0.72, -0.05, 0.19, 0.15, 0.045, true],   // los pómulos
  [0.37, 0.2, 0.24, 0.075, 0.035, true],    // el arco de las cejas
  [0.41, 0.07, 0.15, 0.08, -0.012, true],   // las cuencas de los ojos
  [0, -0.47, 0.32, 0.18, 0.055, false],     // el hocico, alrededor de la boca
  [0, -0.9, 0.24, 0.1, 0.05, false],        // el mentón, ancho y redondo
  [0, -0.74, 0.26, 0.12, 0.045, false],     // la punta del mentón, adelante
  [0, -0.69, 0.2, 0.05, -0.025, false],     // el surco bajo el labio
  [0.24, -0.245, 0.053, 0.047, -0.03, true],  // el pliegue de la sonrisa: junto a la nariz
  [0.36, -0.375, 0.056, 0.056, -0.034, true], //   al medio
  [0.475, -0.515, 0.052, 0.056, -0.026, true], //   junto a la comisura
  [0.8, 0.3, 0.2, 0.2, -0.03, true],        // las sienes
  [0, 0.07, 0.085, 0.13, 0.03, false],      // el entrecejo y el puente de la nariz, ancho y recto
  [0, 0.5, 0.42, 0.2, 0.022, false],        // la frente, más derecha
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

/** La forma de la cabeza: un óvalo ancho de lados casi rectos (de la sien a la mejilla), la mandíbula llena que remata
 * en un mentón ancho y redondo (en U, no en V), la nuca que baja al cuello y el relieve de la cara. Recibe un punto
 * (Vector3) relativo al centro (en la esfera de radio R, o de otro radio para el pelo) y lo devuelve esculpido. */
function deformarCabeza(v) {
  const r = v.length() || 1;
  const u = v.x / r, yn = v.y / r, w = v.z / r;
  v.multiplyScalar(1 + relieve(u, yn, w));
  // de frente no es un círculo sino una superelipse (|x|^p + |y|^p = 1, con p = 3): los lados casi rectos de la sien a
  // la mejilla, la frente ancha y la mandíbula llena, como en la foto. `ancho` es cuánto más ancha que la esfera es a
  // esa altura. Arriba p baja un poco (a 2,7) para que la coronilla quede en cúpula y no en caja; abajo sube (a 3,2)
  // para que el mentón sea ancho, sin llegar a ser cuadrado
  const a = Math.abs(yn);
  const pe = 3 - 0.3 * suave(0.4, 0.95, yn) + 0.2 * suave(0.6, 0.95, -yn);
  const ancho = Math.min(2.2, Math.pow(Math.max(0, 1 - a ** pe), 1 / pe) / Math.sqrt(Math.max(1e-4, 1 - a * a)));
  let sx = 0.735 * ancho, sz = 0.95, sy = 1.02;
  if (yn < 0) {
    sz *= 1 - 0.05 * suave(0, 1, -yn);
    sy = 1.02 + 0.05 * suave(0, 0.35, -yn);   // la cara de abajo más larga: el mentón baja
  }
  sx *= 1 + 0.04 * Math.exp(-((yn - 0.42) ** 2) / 0.05);   // las sienes llenas
  if (v.z < 0) sz *= 1 - 0.28 * suave(0.1, 0.9, -yn) * suave(0, 0.6, -w);   // la nuca baja hacia el cuello
  // el mentón adelante: de perfil, la cara no se va para atrás desde el labio de abajo (queda el surco entre los dos)
  if (w > 0) sz *= 1 + 0.2 * Math.exp(-((yn + 0.84) ** 2) / 0.018) * Math.exp(-(u * u) / 0.12) * suave(0.2, 0.6, w);
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
 * Arma el personaje. Devuelve {grupo, cuerpo, huesos, manos, cara, craneo, contorno, medidas, liberar()}:
 * - `huesos`: los pivotes que mueve animador.js (cadera, columna, pecho, cuello, cabeza, hombro/codo/muneca y
 *   muslo/rodilla/tobillo de cada lado: …I es el izquierdo, …D el derecho, que vive en un grupo espejo).
 * - `manos.I` / `manos.D`: {dedos: [[base, punta] × 4], pulgar, ponerPulgar(p)}: índice, medio, anular y meñique.
 * - `cara`: {boca: {poner({abrir, ancho, sonrisa})}, ojos: [{poner({abierto, sonrisa, mira})}],
 *   cejas: [{poner({alza, ceno})}]}.
 * - `craneo`: el grupo de la cabeza (la cara, el pelo, las orejas), para medirla o encuadrarla.
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
  // la piel con una línea más cálida (un café rojizo): la cara no queda recortada en negro. Comparte el grosor y la
  // resolución (los mismos objetos), así el presentador los sigue controlando
  const matContornoPiel = materialContorno({ ...contorno, color: { value: new THREE.Color(COLORES.contornoPiel) } });
  mats.add(matContorno);
  mats.add(matContornoPiel);
  // la ropa en tonos (caricatura); la piel con una transición suave entre ellos: el relieve de la cara se lee sin
  // manchas. La de la piel cae parejo en los tonos de lo que mira de frente (la cara tiene volumen: la frente, los
  // pómulos y la nariz más claros que la mandíbula y los costados, como en la foto; con la de antes, todo lo que miraba
  // a la cámara quedaba en el mismo tono) y sus sombras son más rojizas, como las de la piel de verdad
  const rampa = rampaDeTonos([0.52, 0.68, 0.82, 0.93, 1]);
  const rampaPiel = rampaDeTonos([0.37, 0.41, 0.45, 0.49, 0.53, 0.58, 0.65, 0.73, 0.82, 0.9, 0.97, 1], true,
    [1, 1.14, 1.07]);
  texs.add(rampa);
  texs.add(rampaPiel);
  const toon = (color, extra = {}) => {
    const m = new THREE.MeshToonMaterial({ color, gradientMap: rampa, ...extra });
    mats.add(m);
    return m;
  };
  const plano = (color, extra = {}) => { const m = new THREE.MeshBasicMaterial({ color, ...extra }); mats.add(m); return m; };
  const M = {
    piel: toon(COLORES.piel, { gradientMap: rampaPiel }),
    pielBrazo: toon(COLORES.pielBrazo, { gradientMap: rampaPiel }),   // los brazos y las manos, más tostados que la cara
    cuello: toon(0xffffff, { gradientMap: rampaPiel, vertexColors: true }),   // la piel, con su sombra por vértice
    oreja: toon(COLORES.oreja, { gradientMap: rampaPiel, vertexColors: true }),
    pelo: toon(COLORES.pelo), peloDegrade: toon(0xffffff, { vertexColors: true }),
    polo: toon(COLORES.polo), poloDoble: toon(COLORES.polo, { side: THREE.DoubleSide }), poloOscuro: toon(COLORES.poloOscuro),
    jean: toon(0xffffff, { vertexColors: true }), jeanOscuro: toon(COLORES.jeanOscuro, { side: THREE.DoubleSide }),
    zapato: toon(COLORES.zapato), suela: toon(COLORES.suela), reloj: toon(COLORES.reloj), bisel: toon(COLORES.bisel),
    pulsera: toon(COLORES.pulsera), cuenta: toon(COLORES.cuenta), boton: toon(COLORES.boton),
    esfera: plano(COLORES.esfera), agujas: plano(COLORES.agujas), fosa: plano(0x6e3a2e),
    nariz: toon(COLORES.piel, { gradientMap: rampaPiel, vertexColors: true }),
    orejaLinea: plano(COLORES.pielLinea, { transparent: true, opacity: 0.5, depthWrite: false, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 }),
  };

  // Una malla con su contorno (un hijo con la misma geometría y el material del contorno: el café rojizo en la piel)
  const deLaPiel = new Set([M.piel, M.pielBrazo, M.oreja, M.cuello, M.nariz]);
  function malla(geo, mat, { borde = true } = {}) {
    const m = new THREE.Mesh(g(geo), mat);
    if (borde) {
      const c = new THREE.Mesh(geo, deLaPiel.has(mat) ? matContornoPiel : matContorno);
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

  // La oreja: una sola pieza cerrada (una lenteja gruesa), armada por anillos desde el centro hasta la silueta, en
  // coordenadas de la oreja vista de lado (u hacia adelante = z, v hacia arriba = y; el origen donde se pega a la
  // cabeza; +x es la cara que mira afuera). La silueta es ancha y redonda arriba y se angosta hacia el lóbulo, redondo
  // y pegado. La cara de afuera tiene relieve: el borde enrollado (el hélix) arriba y atrás, el surco que lo sigue por
  // dentro y la concha abajo y adelante, más oscura (color por vértice); encima, dos líneas finas como las de la cara:
  // el pliegue del hélix y el borde de atrás de la concha. La de adentro es lisa. La comparten las dos orejas
  const ORE = (() => {
    const S = [[0.012, 0.058], [-0.01, 0.086], [-0.04, 0.096], [-0.066, 0.082], [-0.08, 0.048], [-0.079, 0.01],
      [-0.07, -0.025], [-0.056, -0.052], [-0.042, -0.072], [-0.03, -0.086], [-0.014, -0.09], [-0.002, -0.08],
      [0.004, -0.062], [0.01, -0.035], [0.014, 0], [0.014, 0.035]];
    const forma = new THREE.Shape();
    forma.moveTo(...S[0]);
    forma.splineThru([...S.slice(1), S[0]].map(([u, v]) => new THREE.Vector2(u, v)));
    const NK = 72, borde = forma.getSpacedPoints(NK).slice(0, NK);
    const C = new THREE.Vector2(-0.034, 0.002);
    const anillos = [0.2, 0.38, 0.52, 0.62, 0.7, 0.76, 0.81, 0.85, 0.89, 0.93, 0.96, 0.985, 1];
    const redondo = (s) => (s < 0.72 ? 1 : raiz(1 - ((s - 0.72) / 0.28) ** 2));
    // el hélix va arriba y atrás: ni en el borde de adelante (pegado a la cara) ni en el lóbulo
    const libre = (k) => suave(0.006, -0.014, borde[k % NK].x) * suave(-0.078, -0.045, borde[k % NK].y);
    // la concha: un óvalo apenas hundido, de borde marcado (no una mancha difusa)
    const CO = { u: -0.02, v: -0.014, a: 0.02, b: 0.034, hondo: 0.004 };
    const concha = (u, v) => suave(1.05, 0.6, Math.hypot((u - CO.u) / CO.a, (v - CO.v) / CO.b));
    // la cara de afuera en (s, k): s de 0 (el centro) a 1 (la silueta), k el punto de la silueta
    const afuera = (s, k) => {
      const b = borde[k % NK], u = C.x + s * (b.x - C.x), v = C.y + s * (b.y - C.y);
      if (s >= 1) return { u, v, x: 0, c: 1 };
      const l = libre(k), co = concha(u, v);
      const helix = Math.exp(-(((s - 0.865) / 0.055) ** 2)), surco = Math.exp(-(((s - 0.75) / 0.035) ** 2));
      const x = Math.max(-0.0035 * redondo(s),
        0.006 * redondo(s) + l * (0.007 * helix - 0.002 * surco) - CO.hondo * co);
      return { u, v, x, c: 1 - 0.28 * co - 0.25 * l * surco + 0.04 * l * helix };
    };
    const pos = [], col = [], idx = [];
    const vertice = (s, k, deAfuera) => {
      let p;
      if (deAfuera) p = afuera(s, k);
      else {
        const b = borde[k % NK];
        p = { u: C.x + s * (b.x - C.x), v: C.y + s * (b.y - C.y), x: -0.005 * redondo(s), c: 0.94 };
      }
      pos.push(p.x, p.v, p.u);
      col.push(p.c, p.c, p.c);
      return pos.length / 3 - 1;
    };
    const unaCara = (deAfuera) => {
      const centro = vertice(0, 0, deAfuera), filas = [];
      for (const s of anillos) {
        // la silueta (s = 1) es la misma para las dos caras: la de adentro reusa la de afuera
        if (s >= 1 && !deAfuera) { filas.push(null); continue; }
        filas.push(Array.from({ length: NK }, (_, k) => vertice(s, k, deAfuera)));
      }
      return { centro, filas };
    };
    const A = unaCara(true), D = unaCara(false);
    D.filas[D.filas.length - 1] = A.filas[A.filas.length - 1];
    for (const [L, signo] of [[A, -1], [D, 1]]) {
      const tri = (a, b, c) => (signo > 0 ? idx.push(a, b, c) : idx.push(a, c, b));
      for (let k = 0; k < NK; k++) tri(L.centro, L.filas[0][k], L.filas[0][(k + 1) % NK]);
      for (let j = 0; j + 1 < L.filas.length; j++) {
        for (let k = 0; k < NK; k++) {
          const a = L.filas[j][k], b = L.filas[j][(k + 1) % NK];
          const c = L.filas[j + 1][k], d = L.filas[j + 1][(k + 1) % NK];
          tri(a, c, d);
          tri(a, d, b);
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    // las líneas: tiras finas sobre la cara de afuera, [u, v, x] por punto y el grosor que se afina en las puntas
    const tiras = [];
    const linea = (puntos, grosor) => {
      const lp = [], li = [];
      puntos.forEach(([u, v, x], i) => {
        const [ua, va] = puntos[Math.max(0, i - 1)], [ub, vb] = puntos[Math.min(puntos.length - 1, i + 1)];
        const l = Math.hypot(ub - ua, vb - va) || 1;
        const h = (grosor * Math.pow(Math.sin((Math.PI * (i + 0.5)) / puntos.length), 0.6)) / 2;
        const nu = (-(vb - va) / l) * h, nv = ((ub - ua) / l) * h;
        lp.push(x + 0.0008, v + nv, u + nu, x + 0.0008, v - nv, u - nu);
        if (i) li.push(2 * i - 2, 2 * i - 1, 2 * i, 2 * i - 1, 2 * i + 1, 2 * i);
      });
      const t = new THREE.BufferGeometry();
      t.setAttribute('position', new THREE.Float32BufferAttribute(lp, 3));
      t.setIndex(li);
      tiras.push(t);
    };
    // el pliegue del hélix: por dentro del borde, de la raíz (arriba, adelante) hasta antes del lóbulo
    const pliegue = [];
    for (let k = 0; k < NK; k++) if (libre(k) > 0.25) { const p = afuera(0.77, k); pliegue.push([p.u, p.v, p.x]); }
    linea(pliegue, 0.0032);
    // el borde de atrás de la concha (el antehélix), de arriba hacia abajo por atrás
    const borde2 = [];
    for (let i = 0; i <= 20; i++) {
      const f = 1.75 + (i / 20) * 2.6, u = CO.u + 0.9 * CO.a * Math.cos(f), v = CO.v + 0.9 * CO.b * Math.sin(f);
      borde2.push([u, v, 0.006 - CO.hondo * concha(u, v)]);
    }
    linea(borde2, 0.0026);
    const lineas = mergeGeometries(tiras);
    for (const t of tiras) t.dispose();
    return { geo, lineas };
  })();

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
  // Un torno (radio, altura) que después se ensancha de lado y se aplana de adelante hacia atrás. Es el de un hombre
  // adulto y robusto: de hombro a hombro mide más que la cabeza y los hombros bajan en pendiente suave desde el cuello,
  // sin bultos; la polo cae suelta y tapa la pretina del jean
  const perfil = [[0.224, -0.24], [0.226, -0.2], [0.22, -0.12], [0.214, -0.03], [0.212, 0.08], [0.218, 0.2], [0.228, 0.31],
    [0.231, 0.38], [0.224, 0.43], [0.2, 0.475], [0.16, 0.51], [0.124, 0.533], [0.1, 0.545]].map(([r, y]) => new THREE.Vector2(r, y));
  // los hombros anchos y la cintura más angosta; el pecho algo adelante
  const anchoTorso = (y) => 1.1 + 0.32 * suave(0.05, 0.42, y) - 0.12 * suave(0.43, 0.545, y);
  const fondoTorso = (y, adelante) => 0.64 + 0.05 * suave(0.12, 0.34, y) * (adelante ? 1 : 0.4);
  // el radio del torno a cada altura (0 por encima del hombro: ahí está abierto y lo tapa el cuello)
  function radioTorso(y) {
    if (y <= perfil[0].y) return perfil[0].x;
    for (let i = 1; i < perfil.length; i++) {
      const a = perfil[i - 1], b = perfil[i];
      if (y <= b.y) return a.x + ((b.x - a.x) * (y - a.y)) / (b.y - a.y);
    }
    return 0;
  }
  // La superficie de la polo sin lanzar rayos (en coordenadas de la columna): el punto del torso en el ángulo `fi`
  // (0 adelante, π/2 a su izquierda) a la altura `y`, y empujar un punto afuera hasta quedar `margen` por fuera
  const enTorso = (fi, y, margen = 0) => fueraDelTorso(new THREE.Vector3(Math.sin(fi) * anchoTorso(y) * 1e-3, y,
    Math.cos(fi) * fondoTorso(y, Math.cos(fi) > 0) * 1e-3), margen);
  // la altura (z) de la polo vista de frente en (x, y)
  const zTorso = (x, y) => {
    const r = radioTorso(y), a = anchoTorso(y);
    return fondoTorso(y, true) * Math.sqrt(Math.max(0, r * r - (x / a) ** 2));
  };
  function fueraDelTorso(v, margen) {
    const r = radioTorso(v.y);
    if (r <= 0) return v;
    const a = anchoTorso(v.y), f = fondoTorso(v.y, v.z > 0);
    const q = Math.hypot(v.x / a, v.z / f) || 1e-6;
    // el margen está en unidades del modelo: en esa dirección, una unidad del torno mide hypot(a·seno, f·coseno)
    const meta = r + margen / Math.hypot((v.x / q), (v.z / q));
    if (q < meta) { v.x *= meta / q; v.z *= meta / q; }
    return v;
  }
  let torsoGeo = new THREE.LatheGeometry(perfil, 56, Math.PI, Math.PI * 2);
  {
    const p = torsoGeo.attributes.position, v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      p.setXYZ(i, v.x * anchoTorso(v.y), v.y, v.z * fondoTorso(v.y, v.z > 0));
    }
  }
  torsoGeo = suavizarNormales(torsoGeo);
  const torso = malla(torsoGeo, M.polo);
  huesos.columna.add(torso);
  // el borde de abajo de la polo, un poco más ancho (la camiseta va por fuera del jean)
  const ruedo = malla(new THREE.TorusGeometry(0.226, 0.011, 8, 48).rotateX(Math.PI / 2).scale(1.1, 1, 0.645), M.polo, { borde: false });
  ruedo.position.y = -0.235;
  huesos.columna.add(ruedo);

  // La tapeta, larga y ancha, con dos botones blanco rosado (con su costura roja en cruz): empieza en la V del cuello
  // (ABRE_CUELLO, la altura donde se juntan las puntas, que tapan a medias el botón de arriba) y abajo tiene el pespunte
  // en cuadro. El cuello de la polo se arma más abajo, con el cuello
  const ABRE_CUELLO = 0.452;
  const enPecho = tocar(torso, 0, ABRE_CUELLO - 0.095) || { p: new THREE.Vector3(0, ABRE_CUELLO - 0.095, 0.15), n: new THREE.Vector3(0, 0.2, 1) };
  const tapeta = malla(new THREE.BoxGeometry(0.056, 0.19, 0.01), M.polo);
  tapeta.position.copy(enPecho.p).add(new THREE.Vector3(0, 0.0, 0.002));
  alinear(tapeta, enPecho.n);
  huesos.columna.add(tapeta);
  for (const [i, y] of [[0, 0.085], [1, 0.016]]) {
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
  // el pespunte: en cuadro abajo y a los dos lados, así la tapeta se lee como un rectángulo cosido
  const pespunte = new THREE.Mesh(g(new THREE.PlaneGeometry(0.046, 0.0022)), M.poloOscuro);
  pespunte.position.set(0, -0.08, 0.0052);
  tapeta.add(pespunte);
  for (const x of [-0.023, 0.023]) {
    const costura = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0022, 0.174)), M.poloOscuro);
    costura.position.set(x, 0.0059, 0.0052);
    tapeta.add(costura);
  }
  // El logo bordado (el jinete) en el pecho izquierdo
  if (documento?.createElement) {
    const tex = logoDelJinete(documento);
    if (tex) {
      texs.add(tex);
      const enLogo = tocar(torso, 0.13, 0.3);
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
    .lerp(color(COLORES.jeanClaro), Math.min(1, Math.max(0, claro - 0.55) * 1.6));
  const pelvisGeo = elipsoide(0.208, 0.158, 0.124, 32, 20);   // dentro de la polo, sin que su contorno asome por ella
  tenir(pelvisGeo, (p, n) => jeanEn(0.35 * Math.max(0, n.z)));
  const pelvis = malla(pelvisGeo, M.jean);
  pelvis.position.y = -0.065;
  huesos.cadera.add(pelvis);

  // ── Los brazos ────────────────────────────────────────────────────────────────────────────────────────────────
  const manos = {};
  function brazo(lado) {
    const raiz = lado === 'D' ? espejo() : new THREE.Group();
    huesos.pecho.add(raiz);
    // el hombro: una bola aplastada que llena la unión de la manga con la polo, sin asomar por encima de la línea del
    // hombro (antes abullonaba las mangas)
    const bola = malla(new THREE.SphereGeometry(0.086, 24, 16), M.polo);
    bola.position.set(0.29, 0.135, 0);
    bola.scale.set(1, 0.62, 0.95);
    raiz.add(bola);
    const hombro = hueso(`hombro${lado}`, 'XZY'), codo = hueso(`codo${lado}`, 'XYZ'), muneca = hueso(`muneca${lado}`, 'XYZ');
    hombro.position.copy(bola.position);
    raiz.add(hombro);
    // la manga corta, recta y algo suelta, hasta dos tercios del brazo; el puño es una banda acanalada del mismo rojo,
    // con una costura arriba
    const manga = malla(new THREE.CylinderGeometry(0.088, 0.09, 0.19, 24, 1, true), M.poloDoble);
    manga.position.y = -0.085;
    hombro.add(manga);
    const puno = malla(new THREE.CylinderGeometry(0.087, 0.084, 0.036, 24, 1, true), M.poloDoble);
    puno.position.y = -0.196;
    hombro.add(puno);
    const costuraPuno = new THREE.Mesh(g(new THREE.TorusGeometry(0.0885, 0.0022, 4, 28).rotateX(Math.PI / 2)), M.poloOscuro);
    costuraPuno.position.y = -0.184;
    hombro.add(costuraPuno);
    // el brazo: fuerte, el bíceps algo marcado. Abajo se angosta hasta meterse entero en la bola del codo, y el
    // antebrazo nace de adentro de ella: el codo no se ve cortado, como el de un muñeco
    const brazoGeo = new THREE.LatheGeometry([[0.0, -0.135], [0.05, -0.13], [0.061, -0.1], [0.071, -0.04], [0.073, 0.02],
      [0.068, 0.08], [0.056, 0.12], [0.0, 0.13]].map(([r, y]) => new THREE.Vector2(r, y)), 20);
    const sup = malla(suavizarNormales(brazoGeo), M.pielBrazo);
    sup.position.y = -0.17;
    sup.scale.z = 0.95;
    hombro.add(sup);
    codo.position.y = -0.305;
    hombro.add(codo);
    const codoBola = malla(new THREE.SphereGeometry(0.058, 16, 12), M.pielBrazo);
    hombro.add(codoBola);
    codoBola.position.y = -0.305;
    // el antebrazo: fuerte y ancho cerca del codo, angosto en la muñeca
    const anteGeo = new THREE.LatheGeometry([[0.0, -0.272], [0.04, -0.26], [0.043, -0.22], [0.055, -0.15], [0.065, -0.08],
      [0.066, -0.03], [0.054, 0.012], [0.0, 0.026]].map(([r, y]) => new THREE.Vector2(r, y)), 20);
    const ante = malla(suavizarNormales(anteGeo).scale(1, 1, 0.9), M.pielBrazo);
    codo.add(ante);
    muneca.position.y = -0.27;
    codo.add(muneca);
    if (lado === 'I') reloj(codo); else manilla(codo);
    manos[lado] = mano(muneca);
    Object.assign(huesos, { [`hombro${lado}`]: hombro, [`codo${lado}`]: codo, [`muneca${lado}`]: muneca });
  }

  // El reloj negro y grande (muñeca izquierda): la correa negra, plana y ancha; la caja redonda con el bisel gris
  // metálico, y la esfera gris carbón hacia afuera (+x: el dorso, con la palma hacia el cuerpo), con 12 marcas blancas en
  // barra, la ventanita de la fecha cerca de las 3 y la corona al costado
  function reloj(codo) {
    const r = new THREE.Group();
    r.position.y = -0.236;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.045, 0.0085, 8, 28).rotateX(Math.PI / 2).scale(1, 2.2, 0.95), M.reloj));
    const caja = malla(new THREE.CylinderGeometry(0.04, 0.04, 0.022, 32).rotateZ(Math.PI / 2), M.reloj);
    caja.position.x = 0.05;
    r.add(caja);
    const bisel = new THREE.Mesh(g(new THREE.TorusGeometry(0.0345, 0.005, 8, 32).rotateY(Math.PI / 2)), M.bisel);
    bisel.position.x = 0.062;
    r.add(bisel);
    const esfera = new THREE.Mesh(g(new THREE.CircleGeometry(0.031, 32).rotateY(Math.PI / 2)), M.esfera);
    esfera.position.x = 0.0615;
    r.add(esfera);
    for (let i = 0; i < 12; i++) {
      const largo = i % 3 === 0 ? 0.008 : 0.0055;
      const marca = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0024, largo).translate(0, 0.026 - largo / 2, 0).rotateY(Math.PI / 2)), M.agujas);
      marca.position.x = 0.0622;
      marca.rotation.x = (i / 12) * Math.PI * 2;
      r.add(marca);
    }
    const fecha = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0055, 0.0045).rotateY(Math.PI / 2)), M.agujas);
    fecha.position.set(0.0622, -0.009, 0.015);
    r.add(fecha);
    const corona = malla(new THREE.CylinderGeometry(0.0055, 0.0055, 0.009, 12).rotateX(Math.PI / 2), M.reloj);
    corona.position.set(0.05, 0, 0.044);
    r.add(corona);
    for (const [largo, ang] of [[0.02, 0.6], [0.014, 2.2]]) {
      const a = new THREE.Mesh(g(new THREE.PlaneGeometry(0.0028, largo).translate(0, largo / 2, 0).rotateY(Math.PI / 2)), M.agujas);
      a.position.x = 0.0625;
      a.rotation.x = ang;
      r.add(a);
    }
  }
  // La manilla roja de hilo, fina y trenzada, con cuentas chicas color oro champaña apretadas sobre el dorso, el nudo y
  // los dos cabos largos que cuelgan (muñeca derecha). Las cuentas son algo más grandes que en la foto: se leen de lejos
  function manilla(codo) {
    const r = new THREE.Group();
    r.position.y = -0.24;
    codo.add(r);
    r.add(malla(new THREE.TorusGeometry(0.044, 0.0042, 6, 32).rotateX(Math.PI / 2), M.pulsera, { borde: false }));
    for (let i = 0; i < 11; i++) {
      const a = -1.35 + (2.7 * i) / 10;
      const c = new THREE.Mesh(g(new THREE.SphereGeometry(0.0072, 10, 8)), M.cuenta);
      c.position.set(Math.cos(a) * 0.047, 0, Math.sin(a) * 0.047);
      r.add(c);
    }
    const nudo = new THREE.Mesh(g(new THREE.SphereGeometry(0.0065, 8, 6)), M.pulsera);
    nudo.position.set(-0.044, -0.002, 0.012);
    r.add(nudo);
    for (const [dz, rz] of [[0.008, 0.12], [0.016, -0.1]]) {
      const cabo = new THREE.Mesh(g(new THREE.CylinderGeometry(0.0026, 0.0022, 0.075, 6).translate(0, -0.0375, 0)), M.pulsera);
      cabo.position.set(-0.045, -0.004, dz);
      cabo.rotation.z = rz;
      r.add(cabo);
    }
  }

  // La mano: la palma hacia el cuerpo (−x), los dedos hacia abajo (−y) y el pulgar adelante (+z)
  function mano(muneca) {
    const m = new THREE.Group();
    muneca.add(m);
    const palma = malla(new RoundedBoxGeometry(0.058, 0.108, 0.1, 3, 0.024), M.pielBrazo);
    palma.position.y = -0.059;
    m.add(palma);
    const dedos = [];
    const filas = [[0.0335, 1.05], [0.0113, 1.13], [-0.0103, 1.07], [-0.0313, 0.9]];
    for (const [z, largo] of filas) {
      const base = hueso('dedo', 'XYZ');
      base.position.set(0, -0.108, z);
      m.add(base);
      const f1 = malla(capsula(0.0165, 0.025 * largo, 8), M.pielBrazo);
      f1.position.y = -0.021 * largo;
      base.add(f1);
      const punta = hueso('punta', 'XYZ');
      punta.position.y = -0.043 * largo;
      base.add(punta);
      const f2 = malla(capsula(0.0154, 0.019 * largo, 8), M.pielBrazo);
      f2.position.y = -0.017 * largo;
      punta.add(f2);
      dedos.push([base, punta]);
    }
    const pulgar = hueso('pulgar', 'XYZ');
    pulgar.position.set(-0.008, -0.032, 0.048);
    m.add(pulgar);
    const p1 = malla(capsula(0.019, 0.043, 8), M.pielBrazo);
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
    muslo.position.set(0.114, -0.04, 0);
    raiz.add(muslo);
    // el muslo y la pierna, tornos que se angostan hacia la rodilla hasta casi el mismo ancho: la pierna nace de
    // adentro del muslo y la rodilla no se ve cortada
    const musloGeo = suavizarNormales(new THREE.LatheGeometry([[0, -0.232], [0.045, -0.23], [0.076, -0.214], [0.089, -0.18],
      [0.094, -0.12], [0.097, 0.0], [0.097, 0.15], [0.09, 0.2], [0.06, 0.225], [0, 0.232]]
      .map(([r, y]) => new THREE.Vector2(r, y)), 18));
    tenir(musloGeo, (p, n) => jeanEn(Math.max(0, n.z) ** 1.1 * (0.62 + 0.45 * Math.exp(-((p.y + 0.02) ** 2) / 0.016)) + 0.06));
    const mm = malla(musloGeo, M.jean);
    mm.position.y = -0.19;
    muslo.add(mm);
    rodilla.position.y = -0.4;
    muslo.add(rodilla);
    const pantGeo = suavizarNormales(new THREE.LatheGeometry([[0, -0.219], [0.066, -0.21], [0.081, -0.18], [0.084, -0.1],
      [0.087, 0.05], [0.088, 0.15], [0.078, 0.188], [0.05, 0.21], [0, 0.219]].map(([r, y]) => new THREE.Vector2(r, y)), 18));
    tenir(pantGeo, (p, n) => jeanEn(Math.max(0, n.z) ** 1.3 * (0.35 + 0.5 * Math.exp(-((p.y - 0.12) ** 2) / 0.006))));
    const c = malla(pantGeo, M.jean);
    c.position.y = -0.17;
    rodilla.add(c);
    // el bota del jean, recto, que cae sobre el zapato
    const bota = malla(new THREE.CylinderGeometry(0.086, 0.092, 0.07, 24, 1, true), M.jeanOscuro);
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
  // el cuello es grueso, como en la foto (con la mandíbula llena, uno fino hace de la cabeza un chupete): casi tan ancho
  // como la mandíbula, más ancho que hondo y algo inclinado hacia adelante. Más oscuro que la cara: arriba, a la sombra
  // de la mandíbula, y abajo, a la del cuello de la polo
  const PERFIL_CUELLO = [[0.148, -0.075], [0.146, -0.04], [0.138, 0.01], [0.13, 0.06], [0.126, 0.11], [0.12, 0.16]];
  const FONDO_CUELLO = 0.8;   // más ancho que hondo
  let cuelloGeo = new THREE.LatheGeometry([[0, -0.075], ...PERFIL_CUELLO, [0, 0.16]].map(([r, y]) => new THREE.Vector2(r, y)), 36)
    .scale(1, 1, FONDO_CUELLO);
  cuelloGeo = suavizarNormales(cuelloGeo);
  const sombraCuello = 0.68;   // lo oscuro del cuello abajo, a la sombra de la polo (también el escote)
  {
    const claro = color(COLORES.piel), oscuro = color(COLORES.pielSombra), c = new THREE.Color();
    tenir(cuelloGeo, (p, n) => c.copy(claro).lerp(oscuro, Math.min(0.85, 0.28
      + 0.6 * suave(0, 0.1, p.y) * (0.55 + 0.45 * Math.max(0, n.z)) + (sombraCuello - 0.28) * (1 - suave(-0.05, 0.01, p.y)))));
  }
  const cuello = malla(cuelloGeo, M.cuello);
  cuello.position.set(0, 0, -0.012);
  cuello.rotation.x = 0.22;
  huesos.cuello.add(cuello);
  cuelloDeLaPolo();

  /** El cuello de la polo, grande, como en la foto: rodea el cuello por detrás y por los lados casi hasta la mandíbula y
   * adelante se abre en una V honda, cuyos bordes bajan hasta juntarse sobre el botón de arriba; las puntas, largas,
   * quedan apoyadas en el pecho. Es una sola pieza con grosor (un casco cerrado: el contorno la dibuja entera). Una
   * mitad se arma por columnas, desde la nuca (u = 0) hasta el borde de adelante (u = 1), y la otra es su espejo,
   * soldada en la nuca. Cada columna va del doblez de arriba, alrededor del cuello, al borde de abajo, que se apoya en
   * los hombros y adelante pasa por la punta y sube a la V. Se arma en coordenadas de la columna: el cuello (que cuelga de otro hueso) se pasa a ellas con su matriz, y
   * cada punto se empuja afuera del cuello y de la polo con un margen, así nada los atraviesa al mover la cabeza. */
  function cuelloDeLaPolo() {
    // del cuello (su malla) a la columna, y de vuelta
    for (const o of [huesos.pecho, huesos.cuello, cuello]) o.updateMatrix();
    const aColumna = new THREE.Matrix4().multiplyMatrices(huesos.pecho.matrix, huesos.cuello.matrix).multiply(cuello.matrix);
    const aCuello = aColumna.clone().invert();
    const radioCuello = (y) => {
      const P = PERFIL_CUELLO;
      if (y <= P[0][1]) return P[0][0];
      for (let i = 1; i < P.length; i++) if (y <= P[i][1]) return P[i - 1][0] + ((P[i][0] - P[i - 1][0]) * (y - P[i - 1][1])) / (P[i][1] - P[i - 1][1]);
      return P[P.length - 1][0];
    };
    const q = new THREE.Vector3();
    const fueraDelCuello = (v, margen) => {
      q.copy(v).applyMatrix4(aCuello);
      const r = radioCuello(q.y), d = Math.hypot(q.x, q.z / FONDO_CUELLO) || 1e-6;
      const meta = r + margen / Math.hypot(q.x / d, q.z / d / FONDO_CUELLO);
      if (d < meta) { q.x *= meta / d; q.z *= meta / d; v.copy(q.applyMatrix4(aColumna)); }
      return v;
    };
    const ESPESOR = 0.0055, HOLGURA = 0.013;   // la mitad del grosor de la tela; lo que se despega del cuello
    // el doblez de arriba: alrededor del cuello, desde la nuca hasta la esquina de adelante (a TF del frente)
    const TF = 0.6;
    const arriba = (u) => {
      const t = Math.PI - u * (Math.PI - TF), y = 0.066 - 0.012 * u, r = radioCuello(y) + HOLGURA;
      return new THREE.Vector3(Math.sin(t) * r, y, Math.cos(t) * (FONDO_CUELLO * radioCuello(y) + HOLGURA)).applyMatrix4(aColumna);
    };
    // el borde de abajo, sobre la polo: [u, ángulo en el torso, altura]. Atrás y a los lados se apoya en los hombros;
    // adelante baja a la punta y de ahí sube, casi recto, a la V
    const BORDE = [[0, Math.PI, 0.5], [0.4, Math.PI / 2, 0.523], [0.7, 0.75, 0.498], [0.85, 0.33, 0.402],
      [1, 0.012, ABRE_CUELLO - 0.02]];
    const abajo = (u) => {
      let i = 1;
      while (i < BORDE.length - 1 && u > BORDE[i][0]) i++;
      const [u0, f0, y0] = BORDE[i - 1], [u1, f1, y1] = BORDE[i], k = (u - u0) / (u1 - u0);
      return enTorso(f0 + (f1 - f0) * k, y0 + (y1 - y0) * k, ESPESOR + 0.004);
    };
    // las puntas pasan por encima de la tapeta (que es plana y arriba se despega del pecho): tapan a medias el botón
    const centroTapeta = tapeta.position.clone(), normalTapeta = enPecho.n.clone().normalize(), w = new THREE.Vector3();
    const sobreTapeta = (v) => {
      const d = w.subVectors(v, centroTapeta).dot(normalTapeta), meta = 0.012 + ESPESOR;
      const k = (1 - suave(0.02, 0.085, Math.abs(v.x))) * (1 - suave(0.46, 0.52, v.y));
      if (k > 0 && d < meta) v.addScaledVector(normalTapeta, (meta - d) * k);
    };
    const K = 40, J = 9;   // columnas (la punta cae justo en una: u = 0.85) y filas
    const P = [];
    for (let k = 0; k <= K; k++) {
      const u = k / K, a = arriba(u), b = abajo(u), col = [];
      for (let j = 0; j <= J; j++) {
        const t = j / J, v = a.clone().lerp(b, t);
        // el doblez redondo: la tela se abomba un poco hacia afuera entre el borde de arriba y el de abajo
        const afuera = new THREE.Vector3(v.x, 0, v.z + 0.01).normalize();
        v.addScaledVector(afuera, 0.008 * Math.sin(Math.PI * t) * (1 - 0.6 * u));
        fueraDelCuello(v, HOLGURA);
        fueraDelTorso(v, ESPESOR + 0.004);
        sobreTapeta(v);
        col.push(v);
      }
      P.push(col);
    }
    // las normales de la tela (hacia afuera, lejos del cuello) y el casco: la cara de afuera, la de adentro y los bordes
    const N = (K + 1) * (J + 1), pos = new Float32Array(N * 6), idx = [];
    const du = new THREE.Vector3(), dt = new THREE.Vector3(), n = new THREE.Vector3(), normales = [];
    for (let k = 0; k <= K; k++) {
      for (let j = 0; j <= J; j++) {
        du.subVectors(P[Math.min(K, k + 1)][j], P[Math.max(0, k - 1)][j]);
        dt.subVectors(P[k][Math.min(J, j + 1)], P[k][Math.max(0, j - 1)]);
        n.crossVectors(du, dt).normalize();
        const v = P[k][j];
        if (k === 0) { v.x = 0; n.x = 0; n.normalize(); }   // la nuca, en el plano del medio: ahí se suelda la otra mitad
        if (n.x * v.x + n.z * (v.z + 0.01) < 0) n.negate();
        normales.push(n.clone());
        const i = k * (J + 1) + j;
        pos.set([v.x + n.x * ESPESOR, v.y + n.y * ESPESOR, v.z + n.z * ESPESOR], i * 3);
        pos.set([v.x - n.x * ESPESOR, v.y - n.y * ESPESOR, v.z - n.z * ESPESOR], (N + i) * 3);
      }
    }
    const A = new THREE.Vector3(), B = new THREE.Vector3(), C = new THREE.Vector3();
    const tri = (a, b, c, hacia) => {   // un triángulo con la cara hacia `hacia`
      A.fromArray(pos, a * 3); B.fromArray(pos, b * 3).sub(A); C.fromArray(pos, c * 3).sub(A);
      if (B.cross(C).dot(hacia) < 0) idx.push(a, c, b); else idx.push(a, b, c);
    };
    const id = (k, j, adentro = 0) => adentro * N + k * (J + 1) + j;
    for (let k = 0; k < K; k++) {
      for (let j = 0; j < J; j++) {
        const m = normales[k * (J + 1) + j], mi = m.clone().negate();
        tri(id(k, j), id(k + 1, j), id(k + 1, j + 1), m);
        tri(id(k, j), id(k + 1, j + 1), id(k, j + 1), m);
        tri(id(k, j, 1), id(k + 1, j, 1), id(k + 1, j + 1, 1), mi);
        tri(id(k, j, 1), id(k + 1, j + 1, 1), id(k, j + 1, 1), mi);
      }
    }
    // los bordes: el doblez (j = 0), el de abajo (j = J) y el de adelante (k = K). En la nuca (k = 0) no hay: ahí se
    // suelda con la otra mitad
    const borde = (pares, hacia) => {
      for (let i = 0; i + 1 < pares.length; i++) {
        const [k0, j0] = pares[i], [k1, j1] = pares[i + 1];
        const h = hacia(k0, j0);
        tri(id(k0, j0), id(k1, j1), id(k1, j1, 1), h);
        tri(id(k0, j0), id(k1, j1, 1), id(k0, j0, 1), h);
      }
    };
    const fila = (j) => Array.from({ length: K + 1 }, (_, k) => [k, j]);
    const columna = (k) => Array.from({ length: J + 1 }, (_, j) => [k, j]);
    const resta = (a, b) => new THREE.Vector3().subVectors(a, b);
    borde(fila(0), (k) => resta(P[k][0], P[k][1]));
    borde(fila(J), (k) => resta(P[k][J], P[k][J - 1]));
    borde(columna(K), (k, j) => resta(P[K][j], P[K - 1][j]));
    // la otra mitad, en espejo (x → −x, con las caras dadas vuelta), y las dos soldadas en una sola pieza: sin costura
    const todo = new Float32Array(pos.length * 2);
    todo.set(pos);
    for (let i = 0; i < pos.length; i += 3) todo.set([-pos[i], pos[i + 1], pos[i + 2]], pos.length + i);
    const idx2 = idx.slice();
    for (let i = 0; i < idx.length; i += 3) idx2.push(idx[i] + 2 * N, idx[i + 2] + 2 * N, idx[i + 1] + 2 * N);
    let geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(todo, 3));
    geo.setIndex(idx2);
    geo = suavizarNormales(geo);
    huesos.columna.add(malla(geo, M.polo));
    // el escote: la piel que se ve en la V, entre los bordes del cuello, hasta la tapeta (pegada a la polo; arriba se
    // mete detrás del cuello). Del color de la base del cuello, a la sombra
    const filas = 8, cols = 6, ep = [], ei = [];
    for (let i = 0; i <= filas; i++) {
      const y = ABRE_CUELLO - 0.012 + (i / filas) * 0.09, w = 0.004 + 0.07 * (i / filas);
      for (let c = 0; c <= cols; c++) {
        const x = -w + (2 * w * c) / cols;
        ep.push(x, y, zTorso(x, y) + 0.0015);
        if (i < filas && c < cols) {
          const a = i * (cols + 1) + c, b = a + 1, d = a + cols + 1, e = d + 1;
          ei.push(a, b, e, a, e, d);
        }
      }
    }
    const escoteGeo = new THREE.BufferGeometry();
    escoteGeo.setAttribute('position', new THREE.Float32BufferAttribute(ep, 3));
    escoteGeo.setIndex(ei);
    escoteGeo.computeVertexNormals();
    const pielEscote = toon(color(COLORES.piel).lerp(color(COLORES.pielSombra), sombraCuello), { gradientMap: rampaPiel });
    huesos.columna.add(malla(escoteGeo, pielEscote, { borde: false }));
  }
  const craneo = new THREE.Group();
  craneo.position.set(0, 0.29, 0.012);
  craneo.scale.setScalar(0.94);
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

  // El pelo: corto en cepillo, parado y peinado hacia arriba y hacia su izquierda (+x), con gel: los pelos se juntan en
  // mechones. La línea de la frente recta, las entradas apenas marcadas, los lados y la nuca cortos, en un degradé gris
  // (las canas) que se funde con la piel, y la patilla corta que se afina y se aclara
  function pelo(padre) {
    // el límite (grados desde la coronilla) según el rumbo: 0 al frente, π atrás. Adelante es recto y alto (la frente
    // ancha de la foto), con un piquito redondo en el medio, las esquinas casi en ángulo recto y la sien que baja casi
    // vertical (cubierta, sin entradas); la patilla pasa apenas el borde de arriba de la oreja; atrás, la nuca recta
    const limite = [[0, 45.5], [0.07, 44.5], [0.16, 42], [0.26, 41], [0.5, 41], [0.85, 42], [1.0, 54], [1.1, 75],
      [1.17, 88], [1.24, 91], [1.32, 85], [1.42, 78], [1.85, 82], [2.3, 108], [2.75, 113], [Math.PI, 114]];
    const enLimite = (az) => {
      for (let i = 1; i < limite.length; i++) {
        const [a1, l1] = limite[i - 1], [a2, l2] = limite[i];
        if (az <= a2) return l1 + (l2 - l1) * (az - a1) / (a2 - a1);
      }
      return limite[limite.length - 1][1];
    };
    // el grueso del pelo: arriba el cepillo (más alto hacia su izquierda, donde sube el copete), adelante un frente
    // parado que crece de a poco desde la coronilla (sin escalón ni visera), y los lados que se afinan hasta quedar al
    // ras de la piel en el borde: el degradé, sin una pared que el contorno dibuje
    const grueso = (t, az) => {
      const c = Math.cos(az), frente = suave(0.7, 0.95, c), lado = 1 - suave(0.35, 0.85, c);
      return 0.011 + 0.056 * (1 - suave(0.4, 0.95, t)) * (0.7 + 0.3 * frente) + frente * 0.016 * suave(0.3, 1, t)
        - 0.012 * (1 - suave(0, 0.35, t))
        - 0.009 * (1 - frente) * Math.exp(-(((t - 0.55) / 0.18) ** 2))
        + 0.01 * Math.max(0, Math.sin(az)) * (1 - suave(0.3, 0.75, t))
        - 0.0085 * lado * suave(0.72, 1, t);
    };
    // el frente parado sube derecho desde la línea del pelo (no hacia adelante, a lo largo de la normal, que de perfil
    // hacía una visera): esto lo alza
    const alzar = (t, az) => suave(0.7, 0.95, Math.cos(az)) * 0.03 * suave(0.45, 1, t);
    const NA = 120, NT = 30, pos = [], col = [], idx = [];
    const v = new THREE.Vector3(), n = new THREE.Vector3();
    const negro = color(COLORES.pelo), degrade = color(COLORES.peloDegrade), brilloCol = color(0x55505c);
    const piel = color(COLORES.piel);
    const punto = (az, th, extra) => {
      n.set(Math.sin(th) * Math.sin(az), Math.cos(th), Math.sin(th) * Math.cos(az));
      v.copy(n).multiplyScalar(R);
      deformarCabeza(v);
      return v.addScaledVector(n, extra);
    };
    // el color del pelo: negro arriba; a los lados, el gris de las canas desde la mitad hasta el borde
    const ladoDe = (az) => 1 - suave(0.35, 0.85, Math.cos(az));
    const tinte = (az, t) => negro.clone().lerp(degrade, ladoDe(az) * suave(0.55, 0.97, t));
    for (let i = 0; i <= NA; i++) {
      const az = -Math.PI + (2 * Math.PI * i) / NA, tope = (enLimite(Math.abs(az)) * Math.PI) / 180;
      const lado = ladoDe(az);
      for (let j = 0; j <= NT + 1; j++) {
        // la última fila se mete bajo la piel (un poco más allá del borde a los lados): el borde queda pegado a la piel,
        // sin que asome la frente entre una columna y otra
        const t = Math.min(1, j / NT);
        const p = punto(az, tope * t + (j > NT ? 0.012 * lado : 0), j > NT ? -0.003 : grueso(t, az));
        if (j <= NT) p.y += alzar(t, az);
        pos.push(p.x, p.y, p.z);
        const c = tinte(az, t);
        // la pared del frente: apenas gris arriba, donde da la luz (si no, una banda negra lisa; más, una vincha)
        if (j <= NT) c.lerp(brilloCol, 0.12 * (1 - lado) * suave(0.8, 1, t));
        // a los lados el borde se funde con la piel
        if (j >= NT) c.lerp(piel, lado * (j > NT ? 0.6 : 0.3));
        col.push(c.r, c.g, c.b);
      }
    }
    // el contorno del pelo no baja por el degradé de los lados: ahí el borde es la piel (y su línea, la café de la piel);
    // si no, la patilla remataba en una punta negra sobre la oreja
    const F = NT + 2, idxCasco = [];
    for (let i = 0; i < NA; i++) {
      const enDegrade = ladoDe(-Math.PI + (2 * Math.PI * (i + 0.5)) / NA) > 0.6;
      for (let j = 0; j < F - 1; j++) {
        const a = i * F + j, b = a + 1, c = a + F, d = c + 1;
        idx.push(a, b, c, b, d, c);
        if (!enDegrade || j < NT * 0.7) idxCasco.push(a, b, c, b, d, c);
      }
    }
    const armar = (indices) => {
      let s = new THREE.BufferGeometry();
      s.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      s.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      s.setIndex(indices);
      s = mergeVertices(s, 1e-5);
      s.computeVertexNormals();
      return s;
    };
    const casco = malla(armar(idx), M.peloDegrade, { borde: false });
    const linea = new THREE.Mesh(g(armar(idxCasco)), matContorno);
    linea.raycast = () => {};
    casco.add(linea);
    padre.add(casco);
    // la textura del cepillo: mechones de pelos juntos (el gel), cada uno de varios conos anchos que nacen cerca y salen
    // casi paralelos, peinados hacia arriba, atrás y hacia su izquierda, con las puntas que se curvan hacia ese lado
    const r = azar(1896);
    const conos = [];
    const dir = new THREE.Vector3(), dirM = new THREE.Vector3(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
    const doblar = (geo, hacia, k) => {   // el mechón se curva hacia `hacia` (más en la punta)
      const p = geo.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const t = (p.getY(i) + 0.5 * geo.parameters.height) / geo.parameters.height;
        p.setXYZ(i, p.getX(i) + hacia.x * k * t * t, p.getY(i), p.getZ(i) + hacia.z * k * t * t);
      }
      return geo;
    };
    const tenirCono = (geo, alto, base, punta) => {   // de `base` en la raíz a `punta` en la punta
      const p = geo.attributes.position, col = new Float32Array(p.count * 3), c = new THREE.Color();
      for (let i = 0; i < p.count; i++) {
        c.copy(base).lerp(punta, Math.max(0, (p.getY(i) + alto / 2) / alto) ** 1.5);
        col.set([c.r, c.g, c.b], i * 3);
      }
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    };
    const ponerCono = (cono, base, alto, adentro) => {
      q.setFromUnitVectors(Y, dir);
      cono.applyQuaternion(q);
      cono.translate(base.x + dir.x * (alto * 0.5 - adentro), base.y + dir.y * (alto * 0.5 - adentro), base.z + dir.z * (alto * 0.5 - adentro));
      cono.deleteAttribute('uv');
      conos.push(cono.toNonIndexed());
    };
    const luzDir = new THREE.Vector3(-0.35, 0.75, 0.55).normalize();
    for (let m = 0; m < 165; m++) {
      const delFrente = m < 20;
      const az0 = delFrente ? (r() * 2 - 1) * 0.65 : (r() * 2 - 1) * Math.PI;
      const t0 = delFrente ? 0.84 + 0.1 * r() : Math.min(0.88, Math.pow(r(), 0.85) * 0.92);
      const frente0 = suave(0.35, 0.85, Math.cos(az0));
      if (!delFrente && t0 > 0.7 && frente0 < 0.3 && r() < 0.75) continue;   // los lados, cortos: pocos mechones
      const tope0 = (enLimite(Math.abs(az0)) * Math.PI) / 180;
      punto(az0, tope0 * t0, 0);
      // hacia dónde va el mechón: hacia afuera, arriba, atrás y hacia su izquierda (+x)
      // (a los lados, menos hacia afuera y hacia +x: no salen púas de costado; adelante, menos hacia adelante: no hay visera)
      const ax = Math.abs(n.x);
      dirM.copy(n).multiplyScalar(0.55 - 0.2 * ax - 0.15 * Math.max(0, n.z))
        .add(new THREE.Vector3(0.22 * (1 - 0.7 * ax), 0.7, 0.05 + 0.1 * frente0))
        .add(new THREE.Vector3(r() - 0.5, (r() - 0.5) * 0.4, r() - 0.5).multiplyScalar(0.22)).normalize();
      const hacia = { x: 0.6 + 0.3 * r(), z: -0.35 };
      const cuantos = 5 + Math.floor(r() * 2), abre = 0.09 / Math.max(0.3, Math.sin(tope0 * t0));
      for (let k = 0; k < cuantos; k++) {
        const az = az0 + (r() - 0.5) * abre, t = Math.min(0.92, Math.max(0.02, t0 + (r() - 0.5) * 0.08));
        const tope = (enLimite(Math.abs(az)) * Math.PI) / 180, frente = suave(0.35, 0.85, Math.cos(az));
        const base = punto(az, tope * t, grueso(t, az) - 0.006).clone();
        base.y += alzar(t, az);
        const nn = n.clone();
        // el brillo del gel: las puntas se aclaran hacia el gris, más arriba y adelante (donde da la luz); pocos,
        // más finos, brillan casi enteros
        const luz = Math.max(0, nn.dot(luzDir)), brilla = r() < 0.02 + 0.06 * luz;
        const brillo = brilla ? 0.65 : luz * (0.2 + 0.8 * r()) * 0.6;
        dir.copy(dirM).add(new THREE.Vector3(r() - 0.5, (r() - 0.5) * 0.4, r() - 0.5).multiplyScalar(0.12)).normalize();
        // más largos adelante y en el copete (a su izquierda, arriba); cortos a los lados
        const largo = (0.02 + 0.022 * r()) * (delFrente ? 1.35 : 1 - 0.12 * (1 - frente))
          * (1 - 0.6 * suave(0.5, 0.88, t) * (1 - frente))
          * (1 + 0.25 * suave(-0.2, 0.7, Math.sin(az)) * (1 - suave(0.3, 0.7, t)));
        const alto = largo * (brilla ? 1.1 : 1);
        const cono = doblar(new THREE.ConeGeometry((brilla ? 0.6 : 1) * (0.0095 + 0.0075 * r()), alto, 4, 2), hacia, 0.016);
        const cb = tinte(az, t), cp = cb.clone().lerp(brilloCol, brillo);
        tenirCono(cono, alto, cb, cp);
        ponerCono(cono, base, alto, 0.003);
      }
    }
    // el frente parado, peinado hacia arriba y atrás: mechones que nacen en la línea del pelo y suben pegados a la pared
    // del frente, más altos que ella (así no se ve su borde, como una vincha); oscuros en la raíz y algo grises en la punta
    for (let i = 0; i < 110; i++) {
      const az = (r() * 2 - 1) * 0.72, tope = (enLimite(Math.abs(az)) * Math.PI) / 180;
      // nacen apenas por delante de la pared (sobre la piel, en la raíz) y suben pegados a ella
      const base = punto(az, tope + 0.004, 0.004).clone(), nn = n.clone();
      dir.copy(nn).multiplyScalar(0.6).add(new THREE.Vector3((r() - 0.5) * 0.4 + 0.1, 0.6, -0.15)).normalize();
      const alto = (0.034 + 0.05 * r() ** 1.5) * (0.6 + 0.4 * suave(0.7, 0.95, Math.cos(az)));
      const cono = doblar(new THREE.ConeGeometry(0.008 + 0.006 * r(), alto, 4, 2), { x: 0.5, z: -0.5 }, 0.012);
      tenirCono(cono, alto, negro, negro.clone().lerp(brilloCol, 0.3 + 0.5 * r()));
      ponerCono(cono, base, alto, 0);
    }
    const puntas = mergeGeometries(conos);
    for (const c of conos) c.dispose();
    puntas.computeVertexNormals();
    padre.add(new THREE.Mesh(g(puntas), M.peloDegrade));
  }

  // Lo que va dibujado sobre la piel: tiras planas que se pegan a la cara con la grilla de alturas; en cada cuadro se
  // rehacen según la forma pedida. `dz` las separa un poco de la piel (y el polygonOffset, del resto). Lo que queda de
  // canto a la cámara no se pinta: con la cabeza de perfil, la ceja y el ojo del otro lado (que están un pelo por
  // encima de la piel) asomaban por el borde de la frente
  function capa(padre, colorHex, orden, extra = {}) {
    const m = plano(colorHex, { side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2 - orden,
      polygonOffsetUnits: -4 - 2 * orden, ...extra });
    m.onBeforeCompile = deCanto;
    return m;
  }
  function deCanto(sh) {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vVista;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvVista = mvPosition.xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vVista;')
      .replace('void main() {', `void main() {
        vec3 caraTira = normalize(cross(dFdx(vVista), dFdy(vVista)));
        if (abs(dot(caraTira, normalize(vVista))) < 0.28) discard;`);
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
  /** Un disco (con uv de 0 a 1, para las sombras suaves): devuelve poner(cx, cy, rx, ry, dz, giro) (`giro` inclina la
   * elipse, en radianes: para las sombras que siguen un pliegue en diagonal). `A` anillos: los discos
   * grandes (las sombras suaves) se pegan a la curva de la piel; con uno solo, el abanico de triángulos planos queda por
   * debajo de la piel y se ve a rayas y a manchas */
  function disco(padre, colorHex, orden, extra = {}, N = 24, A = 1) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array((1 + N * A) * 3), uv = new Float32Array((1 + N * A) * 2), idx = [];
    const k = (a, i) => 1 + (a - 1) * N + (i % N);   // el vértice i del anillo a (1..A); el 0 es el centro
    for (let i = 0; i < N; i++) {
      idx.push(0, k(1, i), k(1, i + 1));
      for (let a = 1; a < A; a++) idx.push(k(a, i), k(a + 1, i), k(a + 1, i + 1), k(a, i), k(a + 1, i + 1), k(a, i + 1));
    }
    uv.set([0.5, 0.5], 0);
    for (let a = 1; a <= A; a++) {
      for (let i = 0; i < N; i++) {
        const t = (i / N) * Math.PI * 2, f = a / A;
        uv.set([0.5 + (f * Math.cos(t)) / 2, 0.5 + (f * Math.sin(t)) / 2], k(a, i) * 2);
      }
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    geo.setIndex(idx);
    const m = montar(padre, geo, capa(padre, colorHex, orden, extra), orden);
    const poner = (cx, cy, rx, ry = rx, dz = 0.002, giro = 0) => {
      pos[0] = cx; pos[1] = cy; pos[2] = alto.zEn(cx, cy) + dz;
      const cg = Math.cos(giro), sg = Math.sin(giro);
      for (let a = 1; a <= A; a++) {
        for (let i = 0; i < N; i++) {
          const t = (i / N) * Math.PI * 2, f = a / A, u = Math.cos(t) * rx * f, w = Math.sin(t) * ry * f;
          const x = cx + u * cg - w * sg, y = cy + u * sg + w * cg;
          pos.set([x, y, alto.zEn(x, y) + dz], k(a, i) * 3);
        }
      }
      geo.attributes.position.needsUpdate = true;
      geo.computeBoundingSphere();
    };
    poner.malla = m;
    return poner;
  }

  /** Un trazo a lo largo de una curva: devuelve poner(punto(t) → [x, y], grosor(t), dz), con t de 0 a 1. Para las
   * líneas curvas o empinadas: la tira mide el grosor en vertical y se afina donde la línea se para */
  function trazo(padre, colorHex, orden, extra = {}, N = 24) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array((N + 1) * 2 * 3), idx = [];
    for (let i = 0; i < N; i++) { const a = 2 * i; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setIndex(idx);
    const m = montar(padre, geo, capa(padre, colorHex, orden, extra), orden);
    const poner = (punto, grosor, dz) => {
      for (let i = 0; i <= N; i++) {
        const t = i / N, [x, y] = punto(t);
        const [xa, ya] = punto(Math.max(0, t - 0.01)), [xb, yb] = punto(Math.min(1, t + 0.01));
        const l = Math.hypot(xb - xa, yb - ya) || 1, nx = -(yb - ya) / l, ny = (xb - xa) / l, h = grosor(t) / 2;
        for (let k = 0; k < 2; k++) {
          const px = x + nx * h * (k ? -1 : 1), py = y + ny * h * (k ? -1 : 1);
          pos.set([px, py, alto.zEn(px, py) + dz], (2 * i + k) * 3);
        }
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
    // el pliegue de la sonrisa (del lado izquierdo, +x): una curva de Bézier de la aleta de la nariz a la comisura.
    // Devuelve el punto en t (0..1) y hacia dónde va la curva (en radianes)
    const PLIEGUE = [[0.07, -0.078], [0.124, -0.088], [0.134, -0.166]];
    const enPliegue = (t) => {
      const [a, b, c] = PLIEGUE, k = (i) => (1 - t) ** 2 * a[i] + 2 * t * (1 - t) * b[i] + t * t * c[i];
      const d = (i) => 2 * (1 - t) * (b[i] - a[i]) + 2 * t * (c[i] - b[i]);
      return [k(0), k(1), Math.atan2(d(1), d(0))];
    };
    // Las sombras suaves: el calor de las mejillas y la nariz, la sombra bajo los pómulos y bajo el labio
    const nube = documento?.createElement ? degradado(documento) : null;
    if (nube) {
      texs.add(nube);
      const suaves = { map: nube, transparent: true, depthWrite: false };
      // en anillos, pegadas a la piel, y apenas separadas (0,0008): quedan por debajo de los labios y los pliegues
      const sombra = (colorHex, o, N = 24, A = 5) => disco(padre, colorHex, 0, { ...suaves, opacity: o }, N, A);
      for (const s of [1, -1]) {
        // el calor de las mejillas: ancho y suave, sin manchas
        sombra(0xdc7f74, 0.22)(0.125 * s, -0.078, 0.078, 0.058, 0.0008);
        // la sombra bajo el pómulo, hacia la mandíbula. Llega al costado de la cara, donde la piel se curva rápido:
        // con más anillos no se hunde bajo la piel (de perfil se veía agujereada)
        sombra(0x8a4a3c, 0.14, 32, 9)(0.18 * s, -0.15, 0.052, 0.085, 0.0008);
        // las cuencas de los ojos, más oscuras que la frente y los pómulos
        sombra(0x7a4234, 0.26)(0.098 * s, -0.004, 0.062, 0.032, 0.0008);
        // el párpado de arriba, entre el ojo y la ceja: en la foto es mucho más oscuro que la frente (el ojo hundido)
        sombra(0x6a372c, 0.28)(0.099 * s, 0.042, 0.054, 0.012, 0.0008);
        // la sombra ancha del pliegue de la sonrisa (bajo la línea): en la foto es una banda oscura que separa la
        // mejilla, alta y clara, de la boca. Tres elipses encadenadas que siguen la curva, de la aleta a la comisura
        for (const t of [0.15, 0.5, 0.85]) {
          const [x, y, giro] = enPliegue(t);
          sombra(0x7a4234, 0.28)(x * s, y, 0.03, 0.017, 0.0008, giro * s);
        }
      }
      sombra(0xd9756a, 0.24)(0, -0.07, 0.04, 0.032, 0.0008);
      sombra(0x6e3a2c, 0.13)(0, -0.229, 0.052, 0.012, 0.0008);   // bajo el labio de abajo
      // la sombra bajo la nariz, la del bigote rasurado (la piel sobre el labio es más oscura que las mejillas) y las
      // de los lados del puente
      sombra(0x5a2d22, 0.27)(0, -0.117, 0.056, 0.014, 0.0008);
      sombra(0x6e3a2c, 0.07)(0, -0.137, 0.062, 0.02, 0.0008);
      for (const s of [1, -1]) sombra(0x6e3a2c, 0.16)(0.034 * s, -0.025, 0.016, 0.045, 0.0008);
    }
    // El blanco del ojo marca el stencil y el iris solo se pinta donde lo marcó: así el iris nunca se sale del ojo
    const marca = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp };
    const dentro = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc, stencilZPass: THREE.KeepStencilOp };
    const linea = (o = 0.75) => ({ transparent: true, opacity: o, depthWrite: false });
    for (const lado of ['I', 'D']) {
      const raizLado = lado === 'D' ? espejo() : new THREE.Group();
      padre.add(raizLado);
      // ── el ojo: almendrado, con las esquinas abajo: el párpado de abajo, subido por la sonrisa, es casi recto y lo
      // abierto queda sobre la línea de las esquinas, como en la foto; u = −1 es el lagrimal, 1 la cola ──
      const OX = 0.097, OY = 0.012, A = 0.043;
      const pliegueSup = tira(raizLado, COLORES.pielLinea, 2, linea(0.55), 20, 2);
      const blanco = tira(raizLado, COLORES.ojo, 2, marca, 24, 4);
      const pestanas = tira(raizLado, COLORES.contorno, 5, {}, 24, 2);
      const parpadoBajo = tira(raizLado, COLORES.pielLinea, 5, linea(0.7), 24, 2);
      const bolsa = tira(raizLado, COLORES.pielLinea, 2, linea(0.45), 20, 2);
      const patas = [0, 1, 2].map(() => tira(raizLado, COLORES.pielLinea, 2, linea(0.32), 6, 1));
      const iris = disco(raizLado, COLORES.iris, 3, dentro);
      // la sombra del párpado sobre el tercio de arriba del ojo (también sobre el iris: usa el stencil del blanco)
      const sombraOjo = tira(raizLado, 0x7a4a3c, 4, { ...dentro, ...linea(0.3) }, 24, 2);
      // el borde del iris (el limbo), más oscuro que el iris: el ojo se lee café oscuro, casi negro, como en la foto
      const anillo = disco(raizLado, 0x1c110d, 3, dentro);
      const pupila = disco(raizLado, COLORES.pupila, 4, dentro, 20);
      const brillo = disco(raizLado, 0xffffff, 5, dentro, 12);
      let ultimo = '';
      /** abierto 0..1 (0: cerrado), sonrisa 0..1 (el párpado de abajo sube y aparecen las patas de gallo), mira [x, y]
       * de −1 a 1 */
      const poner = ({ abierto = 1, sonrisa = 1, mira = [0, 0] } = {}) => {
        const clave = `${abierto.toFixed(3)}|${sonrisa.toFixed(3)}|${mira[0].toFixed(3)}|${mira[1].toFixed(3)}`;
        if (clave === ultimo) return;
        ultimo = clave;
        const hb = 0.0135 - 0.0085 * sonrisa;
        const abajo = (u) => OY - hb * Math.pow(Math.max(0, 1 - u * u), 0.8) + 0.004 * sonrisa * (u + 1) * 0.5 - 0.0005 * u;
        const ht = 0.023 - 0.004 * sonrisa;
        const arribaAbierto = (u) => OY + ht * Math.pow(Math.max(0, 1 - u * u), 0.5) * (1 - 0.14 * u) - 0.0005 * u;
        const arriba = (u) => { const b = abajo(u); return b + (arribaAbierto(u) - b) * abierto; };
        blanco(OX, A, arriba, abajo, 0.0015);
        sombraOjo(OX, A, (u) => arriba(u) + 0.001, (u) => arriba(u) - 0.0055 * raiz(1 - u * u), 0.0034);
        // las pestañas de arriba: finas junto al lagrimal, más gruesas hacia la cola
        pestanas(OX + 0.001, A * 1.03,
          (u) => arriba(u / 1.015) + 0.0034 * Math.pow(Math.max(0, 1 - u * u), 0.3) * (1 + 0.2 * u) + 0.0008,
          (u) => arriba(u / 1.015) - 0.0006, 0.0024);
        parpadoBajo(OX, A * 0.92, (u) => abajo(u / 0.92) + 0.0006, (u) => abajo(u / 0.92) - 0.0022 * raiz(1 - u * u), 0.0022);
        // el pliegue del párpado de arriba, que sigue al ojo abierto: una línea fina que pasa la cola y baja (la
        // capucha del párpado)
        const capucha = (u) => 0.005 * Math.max(0, u) ** 3;
        pliegueSup(OX + 0.006, A * 1.02, (u) => arribaAbierto(u) + 0.0116 + 0.0008 * raiz(1 - u * u) - capucha(u),
          (u) => arribaAbierto(u) + 0.0094 - capucha(u), 0.0018);
        // la bolsa de la sonrisa bajo el ojo, casi recta y de todo el ancho, y las patas de gallo en la cola, abiertas
        // hacia afuera y abajo
        bolsa(OX + 0.006, A * 0.95, (u) => OY - 0.0205 - 0.0075 * raiz(1 - u * u) + 0.003 * u,
          (u) => OY - 0.0228 - 0.0075 * raiz(1 - u * u) + 0.003 * u, 0.0016);
        const cola = OX + A + 0.005;
        const trazos = [[0.009, 0.002], [0.011, -0.003], [0.008, -0.008]];
        trazos.forEach(([largo, sube], k) => {
          const y0 = OY + 0.004 - k * 0.009;
          patas[k](cola + largo / 2, largo / 2, (u) => y0 + sube * (u + 1) / 2 + 0.0011, (u) => y0 + sube * (u + 1) / 2 - 0.0011, 0.0016);
          patas[k].malla.visible = sonrisa > 0.4;
        });
        // el iris: algo más de un tercio del ancho del ojo, con blanco a los dos lados. Del lado espejo (D) «hacia su
        // izquierda» es −x: así los dos ojos miran, y brillan, hacia el mismo lado
        const sx = lado === 'D' ? -1 : 1;
        const mx = OX + sx * mira[0] * 0.015, my = OY + 0.005 + mira[1] * 0.007;
        anillo(mx, my, 0.0185, 0.0185, 0.00245);
        iris(mx, my, 0.0158, 0.0158, 0.0026);
        pupila(mx, my, 0.0082, 0.0082, 0.0032);
        brillo(mx + sx * 0.0055, my + 0.004, 0.0033, 0.0033, 0.0038);
      };
      poner();
      ojos.push({ poner });
      // ── la ceja: castaña (más clara que el pelo), de borde ralo, casi recta: sube apenas desde la cabeza hasta un
      // arco suave en el tercio de afuera y cae en la cola. Baja, cerca del ojo (a un tercio de lo que va del ojo a la
      // línea del pelo: la frente queda alta), y sin la cuña hacia la nariz, que daba cara de enojado ──
      const ceja = tira(raizLado, COLORES.ceja, 1, {}, 26, 3);
      const cejaRala = tira(raizLado, COLORES.ceja, 0, linea(0.4), 26, 2);   // el borde ralo, más claro
      const arco = lado === 'I' ? 1 : 0;   // su ceja izquierda arquea un poco más y cae más en la cola
      let ultimaCeja = '';
      const ponerCeja = ({ alza = 0, ceno = 0 } = {}) => {
        const clave = `${alza.toFixed(3)}|${ceno.toFixed(3)}`;
        if (clave === ultimaCeja) return;
        ultimaCeja = clave;
        const CX = 0.102, CA = 0.066;
        // la línea media (u = −1 la cabeza, junto a la nariz; 1 la cola): ≈0,046 sobre las esquinas del ojo en el
        // centro, la cabeza algo más baja y la cola que cae. La derecha casi no cae en la cola; la izquierda va un poco
        // más alta, con el arco más marcado y la cola más caída, como en la foto
        const base = (u) => 0.0602 + 0.0078 * u - 0.0073 * u * u - 0.0093 * u ** 3
          + (1 - arco) * 0.006 * Math.max(0, u) ** 3
          + arco * (0.002 + 0.004 * Math.exp(-(((u - 0.4) / 0.45) ** 2)) - 0.016 * Math.max(0, u - 0.55) ** 2)
          + 0.016 * alza * (1 - 0.3 * u) - 0.008 * ceno * (1 - u) / 2;
        // fina en la cabeza, más gruesa en el cuerpo; la cabeza roma (^10) y la cola que se afina en punta (^4)
        const grosorCeja = (u) => 0.012 + 0.0012 * u - 0.003 * u * u;
        const punta = (u) => raiz(1 - Math.abs(u * 0.98) ** (u < 0 ? 10 : 4));
        ceja(CX, CA, (u) => base(u) + grosorCeja(u) * 0.5 * punta(u), (u) => base(u) - grosorCeja(u) * 0.5 * punta(u), 0.0016);
        cejaRala(CX, CA * 1.03, (u) => base(u) + (grosorCeja(u) * 0.5 + 0.0034) * punta(u),
          (u) => base(u) - (grosorCeja(u) * 0.5 + 0.0026) * punta(u), 0.0013);
      };
      ponerCeja();
      cejas.push({ poner: ponerCeja });
      // ── la oreja: grande y despegada; abre hacia adelante (de frente se le ve la concha) y arriba se separa más de
      // la cabeza que en el lóbulo. Va de entre la ceja y el ojo a entre la nariz y la boca ──
      const o = tocar(cabeza, 3, -0.066, -0.02, [-1, 0, 0]) || { p: new THREE.Vector3(0.24, -0.066, -0.02) };
      const oreja = malla(ORE.geo, M.oreja);
      oreja.add(new THREE.Mesh(g(ORE.lineas), M.orejaLinea));
      oreja.position.copy(o.p).add(new THREE.Vector3(0.002, 0, 0));
      // la derecha (la de la izquierda en la foto) se despega algo menos que la izquierda, como en la foto
      oreja.rotation.set(0, lado === 'D' ? -0.52 : -0.7, -0.04);
      raizLado.add(oreja);
      // ── el pliegue de la sonrisa: un paréntesis que nace junto a la aleta de la nariz, se abre hacia la mejilla y
      // baja casi vertical hasta pasar por fuera de la comisura, como en la foto (una curva de Bézier) ──
      const pliegue = trazo(raizLado, COLORES.pielLinea, 1, linea(0.46), 24);
      pliegue((t) => enPliegue(t).slice(0, 2), (t) => 0.0046 * Math.pow(Math.sin(Math.PI * t), 0.6), 0.0016);
    }
    // ── la nariz: ancha y trapezoidal, con la punta redonda y grande fundida con las aletas, el puente ancho y las fosas
    // que asoman abajo. De ala a ala mide casi un tercio del ancho de la cara (±0,074) ──
    const np = alto.punto(0, -0.064);
    // Una sola superficie suave, no bolas sueltas: la unión suave (log-suma-exp) de seis elipsoides, [x, y, z, rx, ry,
    // rz]: la punta, las dos aletas y el puente, ancho y recto, en tres tramos que suben hasta el entrecejo, cada vez más
    // hundidos en la cara. La superficie se halla con un rayo por cada vértice de una esfera (el borde de más afuera).
    // Los rayos no salen de un punto sino de un eje vertical, detrás de la nariz (el de cada vértice, más arriba cuanto
    // más arriba apunta): así lo de adelante es una sola capa, sin pliegues (desde un punto, en el puente largo los rayos
    // vecinos caían en lóbulos distintos y quedaban triángulos dados vuelta, que el contorno pintaba en motas)
    const lobulos = [[0, -0.01, 0.012, 0.046, 0.036, 0.038], [0.042, -0.014, -0.002, 0.032, 0.022, 0.026],
      [-0.042, -0.014, -0.002, 0.032, 0.022, 0.026], [0, 0.024, 0.004, 0.033, 0.034, 0.024],
      [0, 0.06, -0.008, 0.029, 0.034, 0.02], [0, 0.092, -0.024, 0.024, 0.032, 0.016]];
    const K = 9;   // cuánto se funden: más alto, más se notan los lóbulos
    const campo = (x, y, z) => {
      let sum = 0;
      for (const [cx, cy, cz, rx, ry, rz] of lobulos) {
        const a = (x - cx) / rx, b = (y - cy) / ry, c = (z - cz) / rz;
        sum += Math.exp(-K * Math.sqrt(a * a + b * b + c * c));
      }
      return -Math.log(sum) / K;   // menos de 1: adentro
    };
    const narizGeo0 = new THREE.SphereGeometry(1, 48, 36);
    const pn = narizGeo0.attributes.position, LEJOS = 0.14;
    for (let i = 0; i < pn.count; i++) {
      const dx = pn.getX(i), dy = pn.getY(i), dz = pn.getZ(i);
      const ox = 0, oy = 0.03 + 0.055 * dy, oz = -0.03;
      const dentro = (m) => campo(ox + dx * m, oy + dy * m, oz + dz * m) < 1;
      let a = LEJOS;
      while (a > 0 && !dentro(a)) a -= 0.004;   // desde afuera hacia adentro
      a = Math.max(0, a);
      let b = Math.min(LEJOS, a + 0.004);
      for (let k = 0; k < 9; k++) { const m = (a + b) / 2; if (dentro(m)) a = m; else b = m; }
      pn.setXYZ(i, ox + dx * a, oy + dy * a, oz + dz * a);
    }
    const narizGeo = suavizarNormales(narizGeo0);
    narizGeo0.dispose();
    // el surco de las aletas: más oscuro donde la aleta y la punta pesan parecido (la línea curva que separa la aleta
    // de la punta), solo abajo y adelante. Los costados del puente y de la punta, algo más oscuros: la nariz tiene
    // volumen y no se lee como una bola
    const tono = new THREE.Color();
    tenir(narizGeo, (q) => {
      const peso = lobulos.slice(0, 3).map(([cx, cy, cz, rx, ry, rz]) => Math.exp(-K * Math.hypot((q.x - cx) / rx, (q.y - cy) / ry, (q.z - cz) / rz)));
      const aleta = Math.max(peso[1], peso[2]), r = aleta / (peso[0] + aleta + 1e-9);
      return tono.setScalar((1 - 0.22 * Math.exp(-(((r - 0.5) / 0.13) ** 2)) * suave(0.003, -0.022, q.y) * suave(-0.01, 0.01, q.z))
        * (1 - 0.08 * suave(0.018, 0.04, Math.abs(q.x)) * suave(-0.005, 0.02, q.y)) * (1 - 0.06 * suave(0.01, 0.06, q.y)));
    });
    // la nariz no lleva el casco del contorno: está metida en la cara y su borde roza la piel, y el casco salía
    // punteado (y en motas sueltas donde un rayo pasa de un lóbulo a otro). Su borde se oscurece en el sombreado, donde
    // la superficie se pone de canto a la cámara: una línea suave y entera alrededor de las aletas y bajo la punta, que
    // sigue a la nariz desde cualquier lado
    M.nariz.onBeforeCompile = (sh) => {
      sh.fragmentShader = sh.fragmentShader.replace('#include <opaque_fragment>', `
        float canto = abs(dot(normal, normalize(vViewPosition)));
        outgoingLight *= mix(vec3(1.0), vec3(0.55, 0.4, 0.34), 0.85 * (1.0 - smoothstep(0.1, 0.4, canto)));
        #include <opaque_fragment>`);
    };
    const nariz = malla(narizGeo, M.nariz, { borde: false });
    // metida en la cara: el puente se funde con el entrecejo y las aletas con las mejillas
    nariz.position.copy(np).add(new THREE.Vector3(0, 0, -0.017));
    padre.add(nariz);
    // las fosas: dos medialunas oscuras abajo, entre la punta y cada aleta, que asoman de frente. Cada una es un
    // elipsoide medio hundido en la superficie (la z de adelante de la nariz en ese punto)
    const frenteNariz = (x, y) => {
      let z = 0.09;
      while (z > -0.03 && campo(x, y, z) >= 1) z -= 0.001;
      return z;
    };
    for (const s of [1, -1]) {
      const fosa = new THREE.Mesh(g(elipsoide(0.0095, 0.0036, 0.006, 12, 8)), M.fosa);
      fosa.position.set(0.03 * s, -0.0355, frenteNariz(0.03 * s, -0.0355) - 0.0034);
      fosa.rotation.z = 0.25 * s;
      nariz.add(fosa);
    }
    const boca = crearBoca(padre);
    return { ojos, cejas, boca, nariz };
  }

  // La boca: los labios (el de arriba con su arco de cupido, el de abajo lleno y rosado, con su brillo), el fondo oscuro,
  // la lengua y las dos filas de dientes, que se rehacen en cada cuadro según qué tan abierta, ancha y sonriente está
  function crearBoca(padre) {
    const Y0 = -0.172;
    const texDientes = documento?.createElement ? dibujoDeDientes(documento) : null;
    if (texDientes) texs.add(texDientes);
    const labioInf = tira(padre, COLORES.labio, 0);
    const labioSup = tira(padre, COLORES.labioSup, 0);
    // el brillo del labio de abajo, a la derecha del centro (la luz de la foto viene de ese lado)
    const brilloInf = tira(padre, COLORES.labioBrillo, 1, { transparent: true, opacity: 0.35, depthWrite: false }, 14, 2);
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
      const w = 0.103 * (0.9 + 0.1 * sonrisa) * ancho;
      const c = (u) => Math.max(0, 1 - u * u);
      // la sonrisa de la foto es una medialuna ancha y plana: el borde de arriba casi recto, con las comisuras apenas
      // por encima del centro, y la curva la hace el borde de abajo
      const arriba = (u) => Y0 + 0.009 + 0.003 * sonrisa * u ** 4 + 0.002 * sonrisa * u * u - 0.006 * (1 - sonrisa) * c(u);
      const hondo = (u) => (0.024 + 0.066 * abrir - 0.008 * (1 - ancho)) * Math.pow(c(u), 0.5);
      const abajo = (u) => arriba(u) - hondo(u);
      // el labio de arriba: más grueso al medio, con el arco de cupido, y fino hacia las comisuras
      labioSup(0, w * 1.02, (u) => arriba(u) + (0.006 + 0.015 * c(u) - 0.0035 * Math.exp(-((u / 0.08) ** 2))) * c(u) ** 0.25 + 0.0006,
        (u) => arriba(u) - 0.0004, 0.0015);
      // el de abajo: lleno y redondo
      labioInf(0, w * 0.97, (u) => abajo(u * 0.97) + 0.0008, (u) => abajo(u * 0.97) - (0.032 + 0.004 * abrir) * c(u) ** 0.75, 0.0015);
      brilloInf(0.2 * w, w * 0.28, (u) => abajo(0.2 + u * 0.28) - 0.009 * (1 - 0.3 * u * u),
        (u) => abajo(0.2 + u * 0.28) - (0.009 + 0.011 * c(u) ** 0.7), 0.0019);
      fondo(0, w, arriba, abajo, 0.002);
      lengua(0, w * 0.6, (u) => abajo(u * 0.6) + 0.4 * hondo(u * 0.6) * Math.min(1, abrir * 1.6) * (1 - u * u),
        (u) => abajo(u * 0.6), 0.0025);
      // los dientes de arriba no llegan a las comisuras: a los lados queda el rincón oscuro de la boca
      dientesSup(0, w * 0.86, (u) => arriba(u * 0.86), (u) => arriba(u * 0.86) - Math.min(0.026 * Math.pow(c(u), 0.3),
        0.8 * hondo(u * 0.86)), 0.003);
      dientesInf(0, w * 0.7, (u) => abajo(u * 0.7) + Math.min(0.012 * Math.pow(c(u), 0.4),
        0.2 * hondo(u * 0.7)), (u) => abajo(u * 0.7), 0.003);
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

  return { grupo, cuerpo, huesos, manos, cara, craneo, contorno, medidas, liberar };
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
  // el caballo parado, mirando a la derecha, la cabeza en alto
  x.fillStyle = '#c08a4a';
  x.strokeStyle = '#7a4e22';
  x.lineWidth = 2.5;
  x.beginPath();
  x.ellipse(58, 72, 27, 13, -0.05, 0, Math.PI * 2);
  x.fill();
  x.stroke();
  x.beginPath();   // el cuello alto y la cabeza
  x.moveTo(74, 66); x.lineTo(86, 40); x.lineTo(96, 38); x.lineTo(108, 52); x.lineTo(103, 57); x.lineTo(92, 52); x.lineTo(86, 74);
  x.closePath();
  x.fill();
  x.stroke();
  // las cuatro patas rectas, con las vendas azul oscuro abajo y el casco claro
  for (const xp of [36, 45, 73, 82]) {
    x.strokeStyle = '#a8743a'; x.lineWidth = 6;
    x.beginPath(); x.moveTo(xp, 80); x.lineTo(xp, 108); x.stroke();
    x.strokeStyle = '#1f2c5c'; x.lineWidth = 7;
    x.beginPath(); x.moveTo(xp, 100); x.lineTo(xp, 108); x.stroke();
    x.strokeStyle = '#f0e6d0'; x.lineWidth = 6;
    x.beginPath(); x.moveTo(xp, 112); x.lineTo(xp, 113); x.stroke();
  }
  x.strokeStyle = '#7a4e22';   // la cola
  x.lineWidth = 4;
  x.beginPath(); x.moveTo(32, 66); x.quadraticCurveTo(22, 74, 26, 96); x.stroke();
  // el jinete derecho: casco y camisa azul oscuro, pantalón blanco y la bota
  x.fillStyle = '#1f2c5c';
  x.beginPath(); x.ellipse(60, 44, 8, 13, 0.05, 0, Math.PI * 2); x.fill();
  x.fillStyle = '#e8c9a8';
  x.beginPath(); x.arc(61, 25, 6, 0, Math.PI * 2); x.fill();
  x.fillStyle = '#1f2c5c';
  x.beginPath(); x.arc(61, 21, 6.5, Math.PI, 0); x.fill();
  x.strokeStyle = '#f2ead8'; x.lineWidth = 7;
  x.beginPath(); x.moveTo(58, 56); x.lineTo(66, 66); x.lineTo(64, 78); x.stroke();
  x.strokeStyle = '#1f2c5c'; x.lineWidth = 5;
  x.beginPath(); x.moveTo(64, 78); x.lineTo(63, 86); x.stroke();
  x.lineWidth = 4;   // el brazo a las riendas
  x.beginPath(); x.moveTo(62, 40); x.lineTo(74, 50); x.stroke();
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
  // las separaciones, apenas marcadas: los incisivos del medio anchos y los de los lados angostos (la arcada se curva)
  const cortes = [0.105, 0.175, 0.265, 0.372, 0.5, 0.628, 0.735, 0.825, 0.895];
  x.strokeStyle = 'rgba(165,155,150,0.4)';
  x.lineWidth = 1.5;
  for (const t of cortes) { x.beginPath(); x.moveTo(t * 256, 9); x.lineTo(t * 256, 32); x.stroke(); }
  // las muescas oscuras entre diente y diente, en el borde de abajo
  x.fillStyle = 'rgba(95,55,55,0.6)';
  for (const t of cortes) { x.beginPath(); x.moveTo(t * 256 - 3.5, 32); x.lineTo(t * 256, 25); x.lineTo(t * 256 + 3.5, 32); x.fill(); }
  // los costados en sombra: la boca se curva hacia adentro
  const lados = x.createLinearGradient(0, 0, 256, 0);
  lados.addColorStop(0, 'rgba(110,90,85,0.5)');
  lados.addColorStop(0.16, 'rgba(110,90,85,0)');
  lados.addColorStop(0.84, 'rgba(110,90,85,0)');
  lados.addColorStop(1, 'rgba(110,90,85,0.5)');
  x.fillStyle = lados;
  x.fillRect(0, 0, 256, 32);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
