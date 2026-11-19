// Lo que mueve al presentador (personaje.js): una pose por capas que se recalcula en cada cuadro y que las
// articulaciones siguen con suavidad (así ningún cambio da un salto).
//
//   1. el reposo: de pie, las manos juntas al frente (la casa);
//   2. lo que hace siempre: respira, se balancea un poco y parpadea;
//   3. caminar (cuando va a otra x) o el salto de entrada y de salida;
//   4. hablar: la boca por sílabas, la cabeza que acompaña y, si los brazos están libres, las manos que explican con
//      un golpe cada tanto;
//   5. un gesto (saludar, señalar, presentar, explicar, contar, pensar, celebrar, invitar, asentir, pulgar, escuchar,
//      despedirse), que entra y sale sobre lo anterior;
//   6. hacia dónde mira: la columna, el cuello, la cabeza y los ojos se reparten el giro.
//
// Las poses se escriben como ángulos de Euler en el orden de cada hueso (personaje.js) y se mezclan como cuaterniones.
// Brazos (el derecho es el espejo del izquierdo: los mismos números hacen el mismo gesto del otro lado):
//   hombro 'XZY' [x: adelante (−) o atrás (+), y: giro del brazo, z: hacia afuera (+)];
//   codo 'XYZ' [x: dobla (−), y: gira el antebrazo (+: la palma hacia arriba con el antebrazo adelante)];
// Piernas: muslo 'XZY' [x: adelante (−)], rodilla [x: dobla (+)]. Columna, cuello y cabeza 'YXZ' [x: inclina adelante
// (+), y: gira, z: ladea].
//
// Sin DOM y sin reloj propio: `actualizar(dt)` avanza (el presentador y el taller lo llaman en cada cuadro; las pruebas,
// con el dt que quieran).
import * as THREE from 'three';

export const ARTICULACIONES = ['cadera', 'columna', 'pecho', 'cuello', 'cabeza', 'hombroI', 'codoI', 'munecaI',
  'hombroD', 'codoD', 'munecaD', 'musloI', 'rodillaI', 'tobilloI', 'musloD', 'rodillaD', 'tobilloD'];
const BRAZOS = { I: ['hombroI', 'codoI', 'munecaI'], D: ['hombroD', 'codoD', 'munecaD'] };

// Las manos: [índice, medio, anular, meñique, pulgar]. Cada dedo de 0 (estirado) a 1 (cerrado); el pulgar de −1 (afuera)
// a 1 (doblado sobre la palma)
export const MANOS = {
  relajada: [0.22, 0.28, 0.34, 0.4, 0.1],
  abierta: [0.04, 0.03, 0.06, 0.1, -0.55],
  explica: [0.12, 0.16, 0.22, 0.28, -0.3],
  puno: [1, 1, 1, 1, 1],
  senala: [0, 1, 1, 1, 0.75],
  pulgar: [1, 1, 1, 1, -1],
  uno: [0, 1, 1, 1, 0.9],
  dos: [0, 0, 1, 1, 0.9],
  tres: [0, 0, 0, 1, 0.9],
  barbilla: [0.15, 0.85, 0.95, 1, 0.3],
  junta: [0.5, 0.55, 0.6, 0.65, 0.4],
  pinza: [0.5, 0.75, 0.85, 0.9, 0.7],
  plana: [0, 0, 0, 0, -0.2],
};
export const FORMAS_CONTAR = ['uno', 'dos', 'tres'];

// El reposo. Los brazos, en «la casa»: las manos juntas y sueltas al frente, a la altura del ombligo (las palmas a
// y ≈ 1.0), la izquierda un poco más alta, sobre la derecha, sin tocarse del todo ni tocar la polo. En la presentación
// el borde de arriba del subtítulo corta al presentador a la altura de la cadera (el plano americano, 0.37·alto ≈ 0.85):
// con los brazos colgando las manos quedaban debajo del corte; así quedan arriba (≈ 0.08 de margen)
const REPOSO = {
  cadera: [0, 0, 0], columna: [0.03, 0, 0], pecho: [0, 0, 0], cuello: [0.02, 0, 0], cabeza: [-0.02, 0, 0],
  hombroI: [-0.23, -0.55, -0.04], codoI: [-1.34, 0.2, 0], munecaI: [0.12, 0, 0],
  hombroD: [-0.19, -0.55, -0.04], codoD: [-1.27, 0.4, 0], munecaD: [0.15, 0, 0],
  musloI: [0, 0, 0.035], rodillaI: [0.03, 0, 0], tobilloI: [-0.03, 0, -0.035],
  musloD: [0, 0, 0.035], rodillaD: [0.03, 0, 0], tobilloD: [-0.03, 0, -0.035],
};
// Los brazos mientras habla sin un gesto: adelante, las palmas a medio abrir
const CONVERSA = { hombro: [-0.24, 0, 0.17], codo: [-1.08, 1.0, 0], muneca: [0.12, 0, 0] };

const otro = (lado) => (lado === 'I' ? 'D' : 'I');
const brazo = (lado, hombro, codo, muneca = [0, 0, 0]) => ({ [`hombro${lado}`]: hombro, [`codo${lado}`]: codo, [`muneca${lado}`]: muneca });
const dos = (hombro, codo, muneca) => ({ ...brazo('I', hombro, codo, muneca), ...brazo('D', hombro, codo, muneca) });
// Algunas poses que se repiten
const P = {
  palmasArriba: [[-0.45, 0, 0.34], [-1.22, 1.35, 0], [0.18, 0, 0]],      // las manos adelante, las palmas arriba
  ladoAbierto: [[-0.55, 0, 0.78], [-0.6, 1.45, 0], [-0.15, 0, 0]],        // un brazo afuera, la palma arriba
  dedoArriba: [[-0.6, 0, 0.3], [-2.2, -1.5, 0], [0, 0, 0.08]],            // el antebrazo arriba, la palma a la sala
  enJarra: [[0.15, -1.57, 0.75], [-1.6, 0, 0], [0, 0, 0.2]],              // la mano en la cintura
};

/**
 * Los gestos: cada uno arma su clip con las opciones del momento. Un clip es
 * {dur, pose | claves, manos, osc?, cara?, entra?, sale?, sostener?, mirar?, salto?}:
 * - `pose` (o `claves`: [[t, pose], …], que se encadenan) son las articulaciones que toma; las demás siguen con las
 *   otras capas.
 * - `manos`: {I, D} con el nombre de una forma de MANOS (o [[t, forma], …] para cambiarla en el tiempo).
 * - `osc`: [[articulación, eje, amplitud, frecuencia, desde, hasta]]: un vaivén encima (saludar, explicar).
 * - `cara`: {cejas, ceno, sonrisa, abrir, ojos}: lo que hace la cara mientras dura.
 * - `entra` / `sale`: lo que tarda en tomar la pose y en soltarla; `sostener`: se queda hasta otro gesto.
 * - `mirar`: un punto (Vector3, del mundo) al que mira mientras dura; `salto`: un saltito (celebrar).
 * `o.lado` elige el brazo cuando el gesto es de uno solo; `o.punto` es hacia dónde (señalar, presentar, mirar la
 * maqueta); `o.n`, cuántos dedos (contar, enumerar).
 */
export const GESTOS = {
  // ── Empezar y terminar ──
  saludar: (o) => {
    const l = o.lado || 'D';
    return { dur: o.dur || 2.6, pose: { ...brazo(l, [-0.22, 1.45, 1.3], [-1.75, 0, 0], [0, 0, 0.1]), cabeza: [0.02, 0, l === 'D' ? 0.07 : -0.07] },
      manos: { [l]: 'abierta' }, osc: [[`codo${l}`, 0, 0.34, 2.6, 0.45, (o.dur || 2.6) - 0.4]], cara: { cejas: 0.7, abrir: 0.18 } };
  },
  despedirse: (o) => ({ ...GESTOS.saludar({ ...o, dur: o.dur || 1.5 }) }),
  invitar: (o) => ({ dur: o.dur || 3.0, sostener: o.sostener === true,
    pose: { ...dos([-0.4, 0, 0.82], [-0.55, 1.45, 0], [-0.2, 0, 0]), cabeza: [-0.05, 0, 0.06], pecho: [-0.04, 0, 0] },
    manos: { I: 'abierta', D: 'abierta' }, cara: { cejas: 0.85, abrir: 0.12 } }),
  // ── Mostrar ──
  senalar: (o) => {
    const l = o.lado || 'D';
    return { dur: o.dur || 2.8, pose: brazo(l, o.apunta || [-1.2, 0, 0.5], [-0.12, 0, 0], [0.1, 0, 0]), manos: { [l]: 'senala' },
      mirar: o.punto || null, cara: { cejas: 0.35 } };
  },
  presentar: (o) => {
    const l = o.lado || 'D';
    const [x, y, z] = o.apunta || [-0.9, 0, 0.6];
    return { dur: o.dur || 2.8, pose: brazo(l, [x, y, z], [-0.35, 1.45, 0], [-0.25, 0, 0]),
      manos: { [l]: 'abierta' }, mirar: o.punto || null, cara: { cejas: 0.45, abrir: 0.1 } };
  },
  mirar_maqueta: (o) => ({ dur: o.dur || 3.2, pose: { ...dos(...P.enJarra), columna: [0.02, 0, 0], pecho: [-0.03, 0, 0] },
    manos: { I: 'plana', D: 'plana' }, mirar: o.punto || null, cara: { cejas: 0.4, sonrisa: 0.9 } }),
  // ── Explicar ──
  explicar: (o) => {
    const d = o.dur || 3.4;
    return { dur: d, pose: { ...dos(...P.palmasArriba), pecho: [0.04, 0, 0] }, manos: { I: 'explica', D: 'explica' },
      osc: [['hombroI', 0, 0.09, 1.5, 0.4, d - 0.4], ['hombroD', 0, -0.09, 1.5, 0.4, d - 0.4], ['cabeza', 0, 0.04, 1.5, 0.4, d - 0.4]],
      cara: { cejas: 0.4 } };
  },
  destacar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.6;
    return { dur: d, pose: { ...brazo(l, ...P.dedoArriba), cabeza: [0.06, 0, 0], pecho: [0.04, 0, 0] }, manos: { [l]: 'uno' },
      osc: [[`codo${l}`, 0, 0.08, 1.4, 0.45, d - 0.4]], cara: { cejas: 0.9, sonrisa: 0.85 } };
  },
  comparar: (o) => ({ dur: o.dur || 3.6,
    claves: [
      [0.45, { ...brazo('D', ...P.ladoAbierto), ...brazo('I', [-0.2, 0, 0.12], [-0.9, 0.9, 0]), cabeza: [0, -0.2, -0.05] }],
      [1.45, { ...brazo('D', ...P.ladoAbierto), ...brazo('I', [-0.2, 0, 0.12], [-0.9, 0.9, 0]), cabeza: [0, -0.2, -0.05] }],
      [2.05, { ...brazo('I', ...P.ladoAbierto), ...brazo('D', [-0.2, 0, 0.12], [-0.9, 0.9, 0]), cabeza: [0, 0.2, 0.05] }],
    ],
    manos: { I: [[0, 'relajada'], [1.6, 'abierta']], D: [[0, 'abierta'], [1.8, 'relajada']] }, cara: { cejas: 0.5 } }),
  enumerar: (o) => {
    const n = Math.max(1, Math.min(3, o.n || 1));
    return { dur: o.dur || 3.2, sostener: o.sostener === true, pose: { ...brazo('I', ...P.dedoArriba), cabeza: [0.02, 0.08, 0.04] },
      manos: { I: [[0, 'puno'], [0.3, FORMAS_CONTAR[n - 1]]] }, osc: [['codoI', 0, 0.06, 1.2, 0.45, 60]], cara: { cejas: 0.5 } };
  },
  contar: (o) => {
    const n = Math.max(1, Math.min(3, o.n || 3));
    const paso = 0.85, d = 0.6 + n * paso + 0.6;
    const formas = FORMAS_CONTAR.slice(0, n).map((f, i) => [0.45 + i * paso, f]);
    return { dur: d, pose: { ...brazo('I', [-0.2, 0, 0.42], [-2.45, -1.5, 0], [0, 0, 0.1]), cabeza: [0.02, 0.06, 0.04] },
      manos: { I: [[0, 'puno'], ...formas] }, osc: [['codoI', 0, 0.07, 1 / paso, 0.45, d - 0.5]], cara: { cejas: 0.5 } };
  },
  crecer: (o) => ({ dur: o.dur || 3.0,
    claves: [[0.45, { ...dos([-0.2, 0, 0.28], [-0.95, 1.4, 0], [0.2, 0, 0]) }], [2.2, { ...dos([-1.05, 0, 0.5], [-1.1, 1.4, 0], [0.1, 0, 0]),
      cabeza: [-0.1, 0, 0] }]],
    manos: { I: 'abierta', D: 'abierta' }, cara: { cejas: 0.85, abrir: 0.15 } }),
  grande: (o) => {
    const d = o.dur || 2.8;
    return { dur: d, pose: { ...dos([-0.55, 0, 0.98], [-0.5, 0, 0], [0, 0, 0]), pecho: [-0.04, 0, 0] }, manos: { I: 'abierta', D: 'abierta' },
      osc: [['hombroI', 2, 0.08, 1.1, 0.45, d - 0.4], ['hombroD', 2, 0.08, 1.1, 0.45, d - 0.4]], cara: { cejas: 0.8, abrir: 0.2 } };
  },
  detalle: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.6;
    return { dur: d, pose: { ...brazo(l, [-0.6, 0, 0.12], [-1.95, -0.3, 0], [0.25, 0, 0]), cabeza: [0.08, 0, 0.04] },
      manos: { [l]: 'pinza' }, osc: [[`muneca${l}`, 0, 0.1, 1.6, 0.45, d - 0.4]], cara: { cejas: 0.3, sonrisa: 0.8, ojos: [0.2, -0.2] } };
  },
  construir: (o) => {
    const d = o.dur || 2.8;
    return { dur: d, pose: { ...brazo('D', [-0.55, 0, 0.22], [-1.75, 0, 0], [0, 0, 0]), ...brazo('I', [-0.35, 0, 0.1], [-1.35, 1.45, 0], [0.1, 0, 0]),
      cabeza: [0.1, 0, 0] }, manos: { D: 'puno', I: 'plana' }, osc: [['codoD', 0, 0.42, 2.4, 0.45, d - 0.4]],
    cara: { cejas: 0.3, sonrisa: 0.95 } };
  },
  // ── Preguntar y responder ──
  pensar: (o) => ({ dur: o.dur || 3.2, sostener: o.sostener === true,
    pose: { ...brazo('D', [-0.78, 0, -0.42], [-2.3, -1.3, 0], [0.3, 0, 0.3]),
      ...brazo('I', [-0.3, -0.7, -0.05], [-1.55, 0.3, 0], [0, 0, 0]), cabeza: [-0.1, 0.12, 0.12], cuello: [-0.03, 0.05, 0] },
    manos: { D: 'barbilla', I: 'relajada' }, cara: { cejas: 0.55, sonrisa: 0.75, ojos: [0.5, 0.7] } }),
  preguntar: (o) => ({ dur: o.dur || 2.6, pose: { ...dos([-0.15, 0, 0.42], [-1.35, 1.55, 0], [-0.2, 0, 0]), cabeza: [-0.04, 0, 0.16],
    cuello: [-0.05, 0, 0] }, manos: { I: 'abierta', D: 'abierta' }, cara: { cejas: 1, sonrisa: 0.7, abrir: 0.1 } }),
  asentir: (o) => ({ dur: o.dur || 1.3, pose: {}, osc: [['cabeza', 0, 0.13, 2.3, 0.1, (o.dur || 1.3) - 0.15]], entra: 0.1, sale: 0.15,
    cara: { cejas: 0.3 } }),
  negar: (o) => {
    const d = o.dur || 2.2;
    return { dur: d, pose: { ...brazo('D', ...P.dedoArriba) }, manos: { D: 'uno' },
      osc: [['cabeza', 1, 0.24, 2.2, 0.3, d - 0.4], ['codoD', 1, 0.4, 2.2, 0.4, d - 0.4]], cara: { ceno: 0.7, sonrisa: 0.55 } };
  },
  calmar: (o) => {
    const d = o.dur || 2.8;
    return { dur: d, pose: dos([-0.42, 0, 0.32], [-1.15, -1.45, 0], [-0.25, 0, 0]), manos: { I: 'plana', D: 'plana' },
      osc: [['hombroI', 0, 0.07, 1.1, 0.45, d - 0.4], ['hombroD', 0, 0.07, 1.1, 0.45, d - 0.4], ['cabeza', 0, 0.04, 1.1, 0.45, d - 0.4]],
      cara: { cejas: 0.2, sonrisa: 0.9 } };
  },
  // ── Emoción ──
  aprobar: (o) => {
    const l = o.lado || 'D';
    return { dur: o.dur || 2.0, pose: { ...brazo(l, [-0.38, 0, 0.24], [-1.4, 0, 0], [0, 0, 0]), cabeza: [0.03, 0, 0.06] },
      manos: { [l]: 'pulgar' }, cara: { cejas: 0.5, abrir: 0.1 } };
  },
  celebrar: (o) => ({ dur: o.dur || 2.0, pose: { ...dos([-0.15, 0, 2.55], [-0.4, 0, 0]), cabeza: [-0.12, 0, 0] },
    manos: { I: 'puno', D: 'puno' }, salto: true, cara: { cejas: 0.9, abrir: 0.55 },
    osc: [['hombroI', 2, 0.12, 2.4, 0.4, 1.6], ['hombroD', 2, 0.12, 2.4, 0.4, 1.6]] }),
  aplaudir: (o) => {
    const d = o.dur || 2.2;
    return { dur: d, pose: dos([-0.55, 0, 0.12], [-1.25, 0.2, 0], [0, 0, 0]), manos: { I: 'plana', D: 'plana' },
      osc: [['hombroI', 2, 0.13, 3.2, 0.4, d - 0.35], ['hombroD', 2, 0.13, 3.2, 0.4, d - 0.35]], cara: { cejas: 0.7, abrir: 0.35 } };
  },
  juntos: (o) => {
    const d = o.dur || 2.8;
    return { dur: d, claves: [[0.45, dos([-0.5, -0.3, 0.45], [-1.5, 0.1, 0], [0, 0, 0])], [1.1, { ...dos([-0.55, -0.8, -0.05], [-1.6, 0.1, 0], [0, 0, 0]),
      cabeza: [0.04, 0, 0] }]], manos: { I: [[0, 'abierta'], [1.0, 'junta']], D: [[0, 'abierta'], [1.0, 'junta']] },
    osc: [['pecho', 0, 0.03, 2, 1.2, d - 0.4]], cara: { cejas: 0.6, abrir: 0.1 } };
  },
  corazon: (o) => ({ dur: o.dur || 2.8, pose: { ...brazo('D', [-0.5, -0.85, -0.38], [-1.75, 0.1, 0], [0, 0, 0.2]), cabeza: [0.05, 0, -0.1] },
    manos: { D: 'plana' }, cara: { cejas: 0.4, ojos: [0, -0.3] } }),
  // ── En pausa ──
  escuchar: (o) => ({ dur: o.dur || 3, sostener: o.sostener !== false,
    pose: { ...dos([-0.22, 0, -0.06], [-1.35, 0.95, 0], [0.1, 0, 0]), cabeza: [0.04, 0, 0.09] }, manos: { I: 'junta', D: 'junta' },
    cara: { cejas: 0.2 } }),
};
// Para el asistente: los gestos que puede pedir en cada paso del plan (`gesto`: app/recorrido.py y el puente tienen la
// misma lista; una prueba las compara). Los demás los hace el presentador solo: contar el resumen y escuchar en pausa.
// `senalar` señala lo resaltado (o, sin resaltado, la obra en la maqueta); `mostrar_panel`, el panel
export const GESTOS_AGENTE = ['saludar', 'senalar', 'presentar', 'mostrar_panel', 'mirar_maqueta', 'explicar', 'destacar',
  'comparar', 'enumerar', 'crecer', 'grande', 'detalle', 'construir', 'pensar', 'preguntar', 'asentir', 'negar', 'calmar',
  'aprobar', 'celebrar', 'aplaudir', 'juntos', 'corazon', 'invitar', 'despedirse'];
export const NOMBRES_GESTOS = Object.keys(GESTOS);

const suave = (t) => { const x = Math.min(1, Math.max(0, t)); return x * x * (3 - 2 * x); };
const acercar = (k, dt) => 1 - Math.exp(-k * dt);

/**
 * crearAnimador(personaje, {reducido}) → {actualizar(dt), gesto(nombre, opciones), detenerGesto(), hablar(seg|true),
 * callar(), mirarA(punto|null), caminarA(x), entrar(), salir(alTerminar), estado(), camara}.
 * `reducido` (prefers-reduced-motion): sin saltos ni vaivenes del cuerpo, entra y sale sin animación.
 */
export function crearAnimador(personaje, { reducido = false, azar = Math.random } = {}) {
  const { grupo, cuerpo, huesos, manos, cara } = personaje;
  const orden = Object.fromEntries(ARTICULACIONES.map((j) => [j, huesos[j].rotation.order]));
  const eul = new THREE.Euler();
  const qDe = (j, e, out = new THREE.Quaternion()) => out.setFromEuler(eul.set(e[0], e[1], e[2], orden[j]));
  const base = Object.fromEntries(ARTICULACIONES.map((j) => [j, qDe(j, REPOSO[j])]));
  const actual = Object.fromEntries(ARTICULACIONES.map((j) => [j, base[j].clone()]));
  const objetivo = Object.fromEntries(ARTICULACIONES.map((j) => [j, new THREE.Quaternion()]));
  const dedos = { I: [...MANOS.relajada], D: [...MANOS.relajada] };
  const dedosObj = { I: [...MANOS.relajada], D: [...MANOS.relajada] };
  const tmpQ = new THREE.Quaternion(), tmpQ2 = new THREE.Quaternion(), tmpV = new THREE.Vector3(), tmpM = new THREE.Matrix4();

  let t = 0;
  let clip = null, tClip = 0, nombreClip = null, alTerminarClip = null;
  let hablando = false, finHabla = 0;
  let silaba = 0, abrirObj = 0, anchoObj = 1, abrir = 0, ancho = 1;
  let wHabla = 0, golpe = null, proxGolpe = 1, ladoGolpe = 'D';
  let parpado = 1, proxParpadeo = 2 + azar() * 3, enParpadeo = -1, doble = false;
  let cejas = 0, cejasPico = 0, sonrisa = 1, ceno = 0;
  let mira = null;          // un punto del mundo; null: la cámara (la sala)
  let yaw = 0, pitch = 0, ojoX = 0, ojoY = 0;
  let destinoX = grupo.position.x, fase = 0, wCaminar = 0, rumbo = 0, rumboBase = 0;
  let entrada = null;       // {desde, hasta, dur, t, al}
  let salto = 0;
  const api = { camara: null };

  // ── Los gestos ──
  function gesto(nombre, o = {}) {
    const hacer = GESTOS[nombre];
    if (!hacer) return 0;
    const opciones = { ...o };
    // señalar y presentar: el brazo del lado del punto y el ángulo del hombro que lo apunta
    if ((nombre === 'senalar' || nombre === 'presentar') && o.punto) {
      const lado = o.lado || ladoDe(o.punto);
      opciones.lado = lado;
      opciones.apunta = apuntar(lado, o.punto, nombre === 'presentar' ? 0.38 : 0);
    }
    const nuevo = hacer(opciones);
    // el mismo gesto que sigue (enumerar: un dedo más con cada frase): cambia sus manos sin volver a empezar
    if (o.seguir && clip && nombreClip === nombre) {
      clip.manosEn = normalizarManos(nuevo.manos);
      for (const l of Object.keys(clip.manosEn)) clip.manosEn[l] = clip.manosEn[l].map(([, f]) => [0, f]).slice(-1);
      return clip.sostener ? Infinity : clip.dur;
    }
    clip = nuevo;
    clip.nombre = nombre;
    clip.manosEn = normalizarManos(clip.manos);
    clip.qPose = Object.fromEntries(Object.entries(clip.pose || {}).map(([j, e]) => [j, qDe(j, e)]));
    // las claves: cada una con todas las articulaciones que toca alguna (las que no nombra, en reposo)
    if (clip.claves) {
      const todas = [...new Set(clip.claves.flatMap(([, p]) => Object.keys(p)))];
      clip.qClaves = clip.claves.map(([tt, p]) => [tt, Object.fromEntries(todas.map((j) => [j, p[j] ? qDe(j, p[j]) : base[j].clone()]))]);
      for (const j of todas) clip.qPose[j] = clip.qClaves[0][1][j];
    }
    tClip = 0;
    nombreClip = nombre;
    alTerminarClip = typeof o.alTerminar === 'function' ? o.alTerminar : null;
    if (clip.cara?.cejas) cejasPico = Math.max(cejasPico, clip.cara.cejas);
    return clip.sostener ? Infinity : clip.dur;
  }
  function normalizarManos(m = {}) {
    const out = {};
    for (const l of ['I', 'D']) {
      const v = m[l];
      if (!v) continue;
      out[l] = Array.isArray(v) ? v.map(([tt, f]) => [tt, MANOS[f] || MANOS.relajada]) : [[0, MANOS[v] || MANOS.relajada]];
    }
    return out;
  }
  function detenerGesto() {
    if (!clip) return;
    if (clip.sostener) { clip.sostener = false; tClip = Math.max(tClip, clip.dur - (clip.sale ?? 0.45)); }
    else tClip = Math.max(tClip, clip.dur - (clip.sale ?? 0.45));
  }
  // El lado del brazo que apunta: el del lado del punto (visto desde el personaje)
  function ladoDe(punto) {
    grupo.updateMatrixWorld(true);
    tmpV.copy(punto);
    grupo.worldToLocal(tmpV);
    return tmpV.x >= 0 ? 'I' : 'D';
  }
  // El ángulo del hombro (Euler 'XZY') que deja el brazo apuntando a `punto`; `bajar` lo baja (presentar: la palma
  // abierta hacia lo que se muestra, no el dedo)
  function apuntar(lado, punto, bajar = 0) {
    const h = huesos[`hombro${lado}`];
    grupo.updateMatrixWorld(true);
    const desdeH = new THREE.Vector3().setFromMatrixPosition(h.matrixWorld);
    const d = new THREE.Vector3().copy(punto).sub(desdeH);
    if (d.lengthSq() < 1e-6) d.set(0, 0, 1);
    tmpM.copy(h.parent.matrixWorld).invert();
    d.transformDirection(tmpM);
    if (bajar) { d.y -= bajar * Math.hypot(d.x, d.z); d.normalize(); }
    // nunca hacia atrás del cuerpo ni cruzado por delante del pecho
    d.z = Math.max(d.z, 0.15);
    d.x = Math.max(d.x, 0.08);
    d.normalize();
    const a = Math.asin(Math.max(-1, Math.min(1, d.x)));
    const f = Math.atan2(-d.z, -d.y);
    return [f, 0, a];
  }

  // ── Hablar ──
  function hablar(seg = true) {
    hablando = true;
    finHabla = seg === true ? t + 30 : t + Math.max(0.2, Math.min(30, Number(seg) || 0));
    cejasPico = Math.max(cejasPico, 0.35);
    silaba = 0;
  }
  function callar() { hablando = false; }

  // ── Moverse ──
  function caminarA(x) { destinoX = Number.isFinite(x) ? x : destinoX; }
  function mirarA(p) { mira = p ? p.clone() : null; }
  function entrar(al) {
    grupo.visible = true;
    if (reducido) { cuerpo.position.y = 0; al?.(); return; }
    entrada = { desde: -2.6, hasta: 0, dur: 0.8, t: 0, al, tipo: 'entra' };
    cuerpo.position.y = -2.6;
  }
  function salir(al) {
    if (reducido) { grupo.visible = false; al?.(); return; }
    entrada = { desde: cuerpo.position.y, hasta: -2.6, dur: 0.6, t: 0, al: () => { grupo.visible = false; al?.(); }, tipo: 'sale' };
  }

  // ── Cada cuadro ──
  function actualizar(dtIn) {
    // (con pocos cuadros por segundo, un equipo lento que dibuja la maqueta, el tiempo no se estira; tras una pestaña
    // oculta, tampoco salta)
    const dt = Math.min(0.25, Math.max(0, dtIn || 0));
    t += dt;
    for (const j of ARTICULACIONES) objetivo[j].copy(base[j]);
    const sumar = (j, x, y, z) => { objetivo[j].multiply(qDe(j, [x, y, z], tmpQ)); };

    // respirar y balancearse
    if (!reducido) {
      const r = Math.sin((t * 2 * Math.PI) / 3.6), b = Math.sin((t * 2 * Math.PI) / 5.3);
      sumar('columna', 0.014 * r, 0, 0);
      sumar('pecho', 0.01 * r, 0, 0);
      sumar('hombroI', 0, 0, 0.018 * r);
      sumar('hombroD', 0, 0, 0.018 * r);
      sumar('cadera', 0, 0.02 * b, 0.012 * b);
      sumar('columna', 0, -0.012 * b, -0.01 * b);
      sumar('cabeza', 0.012 * Math.sin(t * 0.9), 0.02 * Math.sin(t * 0.37), 0);
    }

    // caminar
    const dx = destinoX - grupo.position.x;
    const anda = Math.abs(dx) > 0.01;
    wCaminar += ((anda ? 1 : 0) - wCaminar) * acercar(6, dt);
    if (anda) {
      const paso = Math.sign(dx) * Math.min(Math.abs(dx), 0.95 * dt * (0.4 + 0.6 * wCaminar));
      grupo.position.x += paso;
      fase += (Math.abs(paso) * Math.PI) / 0.3;
    }
    rumbo += ((anda ? Math.sign(dx) * 1.1 : rumboBase) - rumbo) * acercar(7, dt);
    grupo.rotation.y = rumbo;
    if (wCaminar > 0.01) {
      const s = Math.sin(fase), c = Math.cos(fase), w = wCaminar;
      sumar('musloI', -0.5 * s * w, 0, 0);
      sumar('musloD', 0.5 * s * w, 0, 0);
      sumar('rodillaI', (0.1 + 0.7 * Math.max(0, -c)) * w * (s > 0 ? 1 : 0.4), 0, 0);
      sumar('rodillaD', (0.1 + 0.7 * Math.max(0, c)) * w * (s < 0 ? 1 : 0.4), 0, 0);
      sumar('tobilloI', 0.18 * s * w, 0, 0);
      sumar('tobilloD', -0.18 * s * w, 0, 0);
      sumar('hombroI', 0.36 * s * w, 0, 0);
      sumar('hombroD', -0.36 * s * w, 0, 0);
      sumar('columna', 0.05 * w, 0.06 * s * w, 0);
    }

    // el clip del gesto (su peso: entra, se sostiene, sale)
    let wClip = 0, clipManos = null, clipCara = null;
    if (clip) {
      tClip += dt;
      const entra = clip.entra ?? 0.4, sale = clip.sale ?? 0.45;
      if (!clip.sostener && tClip >= clip.dur) {
        const al = alTerminarClip;
        clip = null; nombreClip = null; alTerminarClip = null;
        try { al?.(); } catch { /* nada */ }
      } else {
        wClip = suave(tClip / entra) * (clip.sostener ? 1 : 1 - suave((tClip - (clip.dur - sale)) / sale));
        clipManos = clip.manosEn;
        clipCara = clip.cara || null;
      }
    }
    const ocupados = { I: !!clip && wClip > 0 && BRAZOS.I.some((j) => clip.qPose[j]), D: !!clip && wClip > 0 && BRAZOS.D.some((j) => clip.qPose[j]) };

    // hablar: las manos que acompañan (si el gesto no usa los brazos) y un golpe cada tanto
    if (hablando && t > finHabla) hablando = false;
    const libres = !ocupados.I && !ocupados.D && wCaminar < 0.3;
    wHabla += ((hablando && libres ? 1 : 0) - wHabla) * acercar(2.4, dt);
    if (wHabla > 0.01) {
      for (const l of ['I', 'D']) {
        objetivo[`hombro${l}`].slerp(qDe(`hombro${l}`, CONVERSA.hombro, tmpQ2), wHabla * (l === 'D' ? 1 : 0.75));
        objetivo[`codo${l}`].slerp(qDe(`codo${l}`, CONVERSA.codo, tmpQ2), wHabla * (l === 'D' ? 1 : 0.75));
        objetivo[`muneca${l}`].slerp(qDe(`muneca${l}`, CONVERSA.muneca, tmpQ2), wHabla * 0.8);
      }
    }
    if (hablando) {
      proxGolpe -= dt;
      if (proxGolpe <= 0 && !golpe) {
        golpe = { t: 0, lado: ladoGolpe, fuerza: 0.6 + 0.4 * azar() };
        ladoGolpe = azar() < 0.65 ? otro(ladoGolpe) : ladoGolpe;
        proxGolpe = 0.9 + azar() * 1.1;
        cejasPico = Math.max(cejasPico, 0.25 + 0.3 * azar());
      }
    }
    if (golpe) {
      golpe.t += dt;
      const s = Math.sin(Math.PI * Math.min(1, golpe.t / 0.42)) * golpe.fuerza;
      if (!reducido) {
        if (wHabla > 0.05) {
          sumar(`codo${golpe.lado}`, -0.26 * s * wHabla, 0, 0);
          sumar(`hombro${golpe.lado}`, -0.08 * s * wHabla, 0, 0.03 * s * wHabla);
        }
        sumar('cabeza', 0.06 * s, 0, 0);
      }
      if (golpe.t >= 0.42) golpe = null;
    }

    // el gesto encima
    if (clip && wClip > 0) {
      if (clip.qClaves) {
        // entre la clave anterior y la siguiente
        const ks = clip.qClaves;
        let k = 0;
        while (k < ks.length - 1 && tClip >= ks[k + 1][0]) k++;
        const [t0, p0] = ks[k], [t1, p1] = ks[Math.min(k + 1, ks.length - 1)];
        const u = t1 > t0 ? suave((tClip - t0) / (t1 - t0)) : 1;
        for (const j of Object.keys(p0)) objetivo[j].slerp(tmpQ2.slerpQuaternions(p0[j], p1[j], tClip < t0 ? 0 : u), wClip);
      } else for (const [j, q] of Object.entries(clip.qPose)) objetivo[j].slerp(q, wClip);
      if (!reducido || clip.nombre !== 'celebrar') {
        for (const [j, eje, amp, frec, desde, hasta] of clip.osc || []) {
          if (tClip < desde || tClip > hasta) continue;
          const env = suave((tClip - desde) / 0.25) * (1 - suave((tClip - (hasta - 0.25)) / 0.25));
          const v = amp * env * Math.sin(2 * Math.PI * frec * (tClip - desde)) * wClip;
          sumar(j, eje === 0 ? v : 0, eje === 1 ? v : 0, eje === 2 ? v : 0);
        }
      }
    }

    // hacia dónde mira: el punto del gesto, el de mirarA o la cámara
    const objetivoMira = (clip && wClip > 0.3 && clip.mirar) || mira || api.camara?.position || null;
    let yawObj = 0, pitchObj = 0;
    if (objetivoMira) {
      grupo.updateMatrixWorld(true);
      tmpV.copy(objetivoMira);
      grupo.worldToLocal(tmpV);
      const ox = tmpV.x, oy = tmpV.y - 1.85, oz = tmpV.z;
      yawObj = Math.max(-0.62, Math.min(0.62, Math.atan2(ox, Math.max(0.05, oz))));
      pitchObj = Math.max(-0.5, Math.min(0.45, Math.atan2(oy, Math.hypot(ox, oz))));
    }
    yaw += (yawObj - yaw) * acercar(5, dt);
    pitch += (pitchObj - pitch) * acercar(5, dt);
    sumar('columna', 0, yaw * 0.15, 0);
    sumar('cuello', -pitch * 0.35, yaw * 0.3, 0);
    sumar('cabeza', -pitch * 0.55, yaw * 0.45, 0);

    // seguir la pose: las articulaciones se acercan a lo pedido
    const k = acercar(clip && clip.osc ? 16 : 11, dt);
    for (const j of ARTICULACIONES) {
      actual[j].slerp(objetivo[j], k);
      huesos[j].quaternion.copy(actual[j]);
    }

    // las manos: la forma del gesto, la de hablar o la relajada
    for (const l of ['I', 'D']) {
      let forma = MANOS.relajada;
      const m = clipManos?.[l];
      if (m && wClip > 0.15) { for (const [tt, f] of m) if (tClip >= tt) forma = f; }
      else if (wHabla > 0.3) forma = MANOS.explica;
      const kd = acercar(14, dt);
      for (let i = 0; i < 5; i++) { dedosObj[l][i] = forma[i]; dedos[l][i] += (dedosObj[l][i] - dedos[l][i]) * kd; }
      ponerMano(manos[l], dedos[l]);
    }

    // el cuerpo: la entrada y la salida, el saltito y el sube y baja del paso
    let y = 0;
    if (entrada) {
      entrada.t += dt;
      const u = Math.min(1, entrada.t / entrada.dur);
      const e = entrada.tipo === 'entra' ? 1 + 2.2 * (u - 1) ** 3 + 1.2 * (u - 1) ** 2 : u * u * (2.4 * u - 1.4);
      cuerpo.position.y = entrada.desde + (entrada.hasta - entrada.desde) * e;
      if (u >= 1) { const al = entrada.al; entrada = null; cuerpo.position.y = 0; if (al) al(); }
    } else {
      if (clip?.salto && !reducido) salto = Math.max(0, Math.sin(Math.min(1, (tClip - 0.35) / 0.5) * Math.PI)) * (tClip > 0.35 ? 0.12 : 0);
      else salto *= 1 - acercar(10, dt);
      y = salto + (wCaminar > 0.01 ? -0.02 * Math.abs(Math.cos(fase)) * wCaminar : 0);
      if (grupo.visible) cuerpo.position.y = y;
    }

    // la cara
    if (!reducido || true) {
      // parpadear (a veces dos veces)
      proxParpadeo -= dt;
      if (proxParpadeo <= 0 && enParpadeo < 0) { enParpadeo = 0; doble = azar() < 0.2; proxParpadeo = 2.2 + azar() * 3.4; }
      if (enParpadeo >= 0) {
        enParpadeo += dt;
        const d = 0.16;
        parpado = 1 - Math.sin(Math.PI * Math.min(1, enParpadeo / d));
        if (enParpadeo >= d) { if (doble) { doble = false; enParpadeo = -0.12; } else enParpadeo = -1; }
      } else if (enParpadeo < -0.5) parpado = 1;
      else { enParpadeo += dt; if (enParpadeo >= 0) enParpadeo = 0; parpado = 1; }
    }
    // la boca: por sílabas mientras habla; la sonrisa de la foto cuando calla
    if (hablando) {
      silaba -= dt;
      if (silaba <= 0) {
        silaba = 0.09 + azar() * 0.12;
        const r = azar();
        abrirObj = r < 0.16 ? 0.04 : 0.3 + azar() * 0.7;
        anchoObj = azar() < 0.22 ? 0.78 : 0.94 + azar() * 0.14;
      }
    } else { abrirObj = 0; anchoObj = 1; }
    const minAbrir = (clipCara?.abrir || 0) * wClip;
    abrir += (Math.max(abrirObj, minAbrir) - abrir) * acercar(26, dt);
    ancho += (anchoObj - ancho) * acercar(20, dt);
    const sonrisaObj = clipCara?.sonrisa !== undefined ? 1 + (clipCara.sonrisa - 1) * wClip : 1;
    sonrisa += (sonrisaObj - sonrisa) * acercar(6, dt);
    cara.boca.poner({ abrir, ancho, sonrisa: Math.max(0, Math.min(1, sonrisa - 0.12 * abrir)) });
    // las cejas: un pico que decae (al empezar a hablar, en un golpe, en un gesto)
    cejasPico *= 1 - acercar(2.2, dt);
    const cejasObj = Math.max(cejasPico, (clipCara?.cejas || 0) * wClip * 0.8);
    cejas += (cejasObj - cejas) * acercar(10, dt);
    const cenoObj = (clipCara?.ceno || 0) * wClip;
    ceno += (cenoObj - ceno) * acercar(8, dt);
    for (const c of cara.cejas) c.poner({ alza: cejas, ceno });
    // los ojos: hacia donde mira, más de lo que gira la cabeza
    const ojos = clipCara?.ojos && wClip > 0.4 ? clipCara.ojos : null;
    const ox = ojos ? ojos[0] : Math.max(-1, Math.min(1, (yawObj - yaw) * 2.5 + yawObj * 0.4));
    const oy = ojos ? ojos[1] : Math.max(-1, Math.min(1, (pitchObj - pitch) * 2.5 + pitchObj * 0.6));
    ojoX += (ox - ojoX) * acercar(18, dt);
    ojoY += (oy - ojoY) * acercar(18, dt);
    const entrecierra = 0.85 - 0.25 * abrir + 0.1 * (sonrisa - 1);
    for (const o of cara.ojos) o.poner({ abierto: parpado, sonrisa: Math.max(0, Math.min(1, entrecierra)), mira: [ojoX, ojoY] });
  }

  function ponerMano(m, v) {
    const abre = [-0.14, -0.04, 0.05, 0.14];
    m.dedos.forEach(([b, p], i) => {
      b.rotation.set(abre[i] * (1 - v[i]), 0, -1.5 * v[i]);
      p.rotation.set(0, 0, -1.3 * v[i]);
    });
    m.ponerPulgar(v[4]);
  }

  /** Lo que está haciendo (para el taller y las pruebas) */
  function estado() {
    return { gesto: nombreClip, hablando, caminando: Math.abs(destinoX - grupo.position.x) > 0.01, x: grupo.position.x,
      visible: grupo.visible, entrando: entrada?.tipo || null };
  }

  return Object.assign(api, { actualizar, gesto, detenerGesto, hablar, callar, mirarA, caminarA, entrar, salir, estado,
    girar(r) { rumboBase = Math.max(-1.2, Math.min(1.2, Number(r) || 0)); } });
}
