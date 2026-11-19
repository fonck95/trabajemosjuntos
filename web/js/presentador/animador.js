// Lo que mueve al presentador (personaje.js): una pose por capas que se recalcula en cada cuadro y que cada
// articulación sigue con su muelle (así salen solos el arrastre del codo y de la muñeca, el sobrepaso y el
// asentamiento, y ningún cambio da un salto).
//
//   1. el reposo vivo: la casa (las manos juntas al frente, que cada tanto cambia), el peso en una pierna, la
//      respiración, la cabeza que nunca está del todo quieta, los ojos que saltan de un punto a otro y el parpadeo;
//   2. caminar paso a paso (el pie que apoya no patina); agacharse y asomarse detrás del subtítulo (entrar, salir,
//      saltar a otro lugar);
//   3. hablar: la boca por sílabas, la cabeza que acompaña y, con un brazo libre, las manos que explican con un golpe
//      cada tanto;
//   4. un gesto (el clip): entra desde lo que hacía el anterior, sin pasar por el reposo, con el cuerpo un poco antes
//      que el brazo y la muñeca un poco después; sale a la casa (la de hablar si sigue hablando);
//   5. hacia dónde mira: los ojos saltan, la cabeza los sigue y la columna y la cadera después;
//   6. los pies: las piernas los alcanzan donde quedaron apoyados (dos huesos, de la cadera al tobillo).
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

const Y = new THREE.Vector3(0, 1, 0);

export const ARTICULACIONES = ['cadera', 'columna', 'pecho', 'cuello', 'cabeza', 'hombroI', 'codoI', 'munecaI',
  'hombroD', 'codoD', 'munecaD', 'musloI', 'rodillaI', 'tobilloI', 'musloD', 'rodillaD', 'tobilloD'];

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
// Otras casas, que alternan con la de las manos juntas (cada 10–20 s, un rato): la mano derecha toma la muñeca
// izquierda (la palma 4 cm sobre la muñeca, sin entrar en el cuerpo ni en el antebrazo, las manos 9 cm sobre el corte
// del americano) y, con la figura entera a la vista, los brazos sueltos. `CASAS_MANOS`: la forma de las manos de cada
// una
const brazosDe = (p) => Object.fromEntries(['hombroI', 'codoI', 'munecaI', 'hombroD', 'codoD', 'munecaD'].map((j) => [j, p[j]]));
const CASAS = {
  junta: brazosDe(REPOSO),
  muneca: brazosDe({ hombroI: [-0.2, -1.18, -0.03], codoI: [-1.27, 0.64, 0], munecaI: [-0.24, 0, 0],
    hombroD: [-0.04, -0.8, -0.22], codoD: [-1.39, 0.54, 0], munecaD: [0.12, 0, -0.48] }),
  sueltos: brazosDe({ hombroI: [0.02, 0, 0.11], codoI: [-0.3, 0.35, 0], munecaI: [0, 0, -0.06],
    hombroD: [0.02, 0, 0.11], codoD: [-0.3, 0.35, 0], munecaD: [0, 0, -0.06] }),
};
// Los brazos mientras habla sin un gesto: adelante, las palmas a medio abrir
const CASAS_MANOS = { muneca: { D: 'junta' } };
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
 * {dur, pose | claves, manos, cara?, entra?, sale?, sostener?, mirar?, mirada?, retraso?, cuerpo?, golpes?, vaiven?,
 *  osc?, salto?}:
 * - `pose` (o `claves`: [[t, pose, curva?], …], que se encadenan) son las articulaciones que toma; las demás siguen con
 *   las otras capas. `curva` es cómo se llega a esa clave desde la anterior (a la primera, desde lo que hacía antes):
 *   'suave' (la de omisión), 'anticipa' (retrocede un poco y después va), 'golpe' (llega rápido), 'sosten' (llega
 *   despacio) o 'lineal'.
 * - `manos`: {I, D} con el nombre de una forma de MANOS (o [[t, forma], …] para cambiarla en el tiempo).
 * - `cara`: {cejas, ceno, sonrisa, abrir, ojos, labios}: lo que hace la cara mientras dura (`labios` 1: la sonrisa
 *   cerrada; 0: con los dientes).
 * - `entra` / `sale`: lo que tarda en tomar la pose y en soltarla (0.4 / 0.45 por omisión); `sostener`: se queda
 *   hasta otro gesto.
 * - `retraso`: {articulación o familia: segundos} sobre los de RETRASO (el cuerpo antes, la muñeca y los dedos
 *   después).
 * - `cuerpo`: {columna, pecho, cadera: [x, y, z], peso: −1 … 1 (la pierna I … la D), alto: dy}: lo que el cuerpo
 *   acompaña, sumado al reposo.
 * - `golpes`: [{t, art, eje, amp, ida, vuelta}]: un impulso (llega en `ida` y vuelve en `vuelta`).
 * - `vaiven`: [{art, eje, amp, frec, desde, hasta, decae, azar, cadena}]: ciclos que decrecen (`decae` por ciclo, 0.7)
 *   con la frecuencia algo irregular (±`azar`, 0.1); `cadena`: la amplitud de la articulación siguiente (hombro →
 *   codo → muñeca, columna → pecho → cuello → cabeza), que va 85 ms atrás (o {art, amp, retraso}).
 * - `osc`: [[articulación, eje, amplitud, frecuencia, desde, hasta]]: el vaivén parejo de antes (solo por
 *   compatibilidad: los gestos nuevos usan `vaiven`).
 * - `mirar`: un punto (Vector3, del mundo); `mirada`: cómo lo mira: 'objetivo' (todo el gesto), 'sala', 'sigue' (el
 *   punto, con un vistazo a la sala cada 3 s) o {objetivo: s, cada: [a, b], dura} (el punto `s` segundos y después la
 *   sala, con otro vistazo cada a–b s); por omisión, {objetivo: 0.8}. `salto`: un saltito (celebrar).
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
  // ── Lo hace solo el presentador ──
  // la mano abierta, baja, hacia lo que se explica (después del primer golpe de señalar o de presentar): el brazo
  // apunta al objetivo (`o.punto`) un poco más abajo, el codo a medio doblar y la palma hacia la sala. Se sostiene
  // la escena entera (`sostener`) mientras la otra mano acompaña lo que dice. `o.mirar`: mirarlo mientras dura
  indicar: (o) => {
    const l = o.lado || 'D';
    return { dur: o.dur || 2.4, entra: 0.5, pose: brazo(l, o.apunta || [-0.35, 0, 0.45], [-0.6, 1.3, 0], [-0.2, 0, 0]),
      manos: { [l]: 'abierta' }, mirar: o.mirar ? o.punto || null : null, cara: { cejas: 0.2 } };
  },
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
const lim = (v, a, b) => Math.min(b, Math.max(a, v));
const LADOS = ['I', 'D'];

// ── Las curvas de las claves: `u` de 0 a 1 en el tramo; `d`, lo que dura (la anticipación retrocede ~0.16 s) ──
export const CURVAS = {
  suave,
  golpe: (u) => u * u * u,
  sosten: (u) => 1 - (1 - u) ** 3,
  lineal: (u) => u,
  anticipa: (u, d = 0.5) => {
    const ua = lim(0.16 / Math.max(0.05, d), 0.12, 0.4), a = 0.12;
    return u < ua ? -a * suave(u / ua) : -a + (1 + a) * suave((u - ua) / (1 - ua));
  },
};
const curva = (nombre, u, d) => (CURVAS[nombre] || suave)(lim(u, 0, 1), d);

// ── Los muelles: [ω (rad/s), ζ] de cada familia de articulaciones. Cuanto más lejos del centro, más rápido y más
// suelto (la muñeca pasa un poco y vuelve); el hombro pasa ~5 % al llegar a la pose de un gesto y asienta en ~0.2 s.
// Con movimiento reducido todos van con ζ = 1 (sin pasarse) ──
export const MUELLES = { cadera: [6, 1], columna: [8, 0.9], pecho: [8, 0.9], cuello: [9, 0.85], cabeza: [10, 0.8],
  hombro: [12, 0.6], codo: [14, 0.6], muneca: [18, 0.6], muslo: [14, 1], rodilla: [14, 1], tobillo: [14, 1],
  dedos: [22, 0.7], rumbo: [7, 1] };
const PASO_MUELLE = 1 / 120;   // los muelles avanzan en pasos de a lo sumo esto (estables aunque el cuadro tarde)
// Cuánto después (o antes, negativo) que el clip toma su pose cada familia: el gesto nace en el cuerpo y termina en
// la mano
export const RETRASO = { cadera: -0.08, columna: -0.06, pecho: -0.06, hombro: 0, codo: 0.08, muneca: 0.19, dedos: 0.2 };
const familia = (j) => j.replace(/[ID]$/, '');
// la articulación que sigue en cada cadena (el vaivén con `cadena`)
const SIGUIENTE = { hombroI: 'codoI', codoI: 'munecaI', hombroD: 'codoD', codoD: 'munecaD', cadera: 'columna',
  columna: 'pecho', pecho: 'cuello', cuello: 'cabeza' };
// Al cambiar de lado el mismo brazo (de un gesto a otro), pasa por delante: la mano frente al pecho
const ARCO = { hombro: [-0.5, 0, 0.15], codo: [-1.2, 0.6, 0] };
// Caminar: los brazos más sueltos, a los costados (sobre ellos va el vaivén)
const ANDAR = { hombro: [-0.06, 0, 0.12], codo: [-0.75, 0.35, 0], muneca: [0, 0, 0] };
// Agachado detrás del subtítulo: cuánto baja el cuerpo por omisión (el presentador le da el de cada plano: lo justo para
// que la cabeza quede bajo el corte) y lo que tardan la entrada (sube), la salida y agacharse o asomarse en un cambio de
// lugar
const HONDO = 1.6;
const ENTRAR_S = 0.8, SALIR_S = 0.45, AGACHARSE_S = 0.3, ASOMARSE_S = 0.45, GRACIAS_S = 0.15;
// El parpadeo: cierra en 60 ms y abre en 120 ms
const CIERRA_S = 0.06, ABRE_S = 0.12;

// Ruido suave de una dimensión (gradientes de Perlin) con la semilla de `azar`: de −1 a 1, sin repetirse a la vista
function crearRuido(azar) {
  const g = Float64Array.from({ length: 256 }, () => azar() * 2 - 1);
  return (x) => {
    const i = Math.floor(x), f = x - i, a = g[i & 255], b = g[(i + 1) & 255];
    const s = f * f * f * (f * (f * 6 - 15) + 10);
    return lim(4 * (a * f + (b * (f - 1) - a * f) * s), -1, 1);
  };
}

/**
 * crearAnimador(personaje, {reducido, azar}) → {actualizar(dt), gesto(nombre, opciones), detenerGesto(), hablar(seg|true),
 * callar(), mirarA(punto|null), mirarSala(seg), caminarA(x, {velocidad, rumbo, zancada}), reubicar(x),
 * entrar(al, {hondo, instante, casi}), salir(al, {hondo, gracias}), agacharse(al, {hondo}), asomarse(al, {hondo, desde}),
 * estado(), girar(rumbo, {ya}), casa(nombre), camara, apertura, plano}.
 * `gesto(nombre, {sostener: true})` sostiene cualquier gesto hasta otro o hasta detenerGesto(); `{mirada}` cambia cómo
 * mira su punto (el formato de los clips); `{entra}`, lo que tarda en entrar. Un gesto nuevo entra desde lo que pedía
 * el anterior (si el mismo brazo cambia de lado, por delante del pecho) y lo que este no usa vuelve a la casa.
 * `plano`: lo que se ve de él ('entero', 'americano', 'medio'…; lo pone el presentador): con la figura entera, a veces
 * deja los brazos sueltos en reposo.
 * `reducido` (prefers-reduced-motion): sin saltos, vaivenes ni sobrepasos; entra, sale, se agacha y se asoma sin
 * animación y el cuerpo gira en el acto.
 */
export function crearAnimador(personaje, { reducido = false, azar = Math.random } = {}) {
  const { grupo, cuerpo, huesos, manos, cara } = personaje;
  const orden = Object.fromEntries(ARTICULACIONES.map((j) => [j, huesos[j].rotation.order]));
  const eul = new THREE.Euler();
  const qDe = (j, e, out = new THREE.Quaternion()) => out.setFromEuler(eul.set(e[0], e[1], e[2], orden[j]));
  const base = Object.fromEntries(ARTICULACIONES.map((j) => [j, qDe(j, REPOSO[j])]));
  const actual = Object.fromEntries(ARTICULACIONES.map((j) => [j, base[j].clone()]));
  const vel = Object.fromEntries(ARTICULACIONES.map((j) => [j, new THREE.Vector3()]));   // velocidad angular de cada muelle
  const objetivo = Object.fromEntries(ARTICULACIONES.map((j) => [j, new THREE.Quaternion()]));
  const trasClip = Object.fromEntries(ARTICULACIONES.map((j) => [j, base[j].clone()]));   // lo pedido con el gesto (sin la mirada)
  const extra = Object.fromEntries(ARTICULACIONES.map((j) => [j, [0, 0, 0]]));            // lo que se suma después del muelle
  const muelle = Object.fromEntries(ARTICULACIONES.map((j) => {
    const [w, z] = MUELLES[familia(j)] || [12, 0.8];
    return [j, [w, reducido ? 1 : z]];
  }));
  const [wDedos, zDedos] = [MUELLES.dedos[0], reducido ? 1 : MUELLES.dedos[1]];
  const dedos = { I: [...MANOS.relajada], D: [...MANOS.relajada] };
  const vDedos = { I: [0, 0, 0, 0, 0], D: [0, 0, 0, 0, 0] };
  const tmpQ = new THREE.Quaternion(), tmpQ2 = new THREE.Quaternion(), tmpQ3 = new THREE.Quaternion();
  const tmpV = new THREE.Vector3(), tmpV2 = new THREE.Vector3(), tmpM = new THREE.Matrix4();
  const qArco = { hombro: {}, codo: {} };
  for (const l of LADOS) for (const f of ['hombro', 'codo']) qArco[f][l] = qDe(`${f}${l}`, ARCO[f]);
  const qAndar = {};
  for (const l of LADOS) for (const f of ['hombro', 'codo', 'muneca']) qAndar[`${f}${l}`] = qDe(`${f}${l}`, ANDAR[f]);

  let t = 0;
  let clip = null, tClip = 0, nombreClip = null, alTerminarClip = null;
  let desde = null, desdeManos = null;   // de dónde viene el gesto (lo que pedía el anterior), mientras entra
  let hablando = false, finHabla = 0;
  let silaba = 0, abrirObj = 0, anchoObj = 1, abrir = 0, ancho = 1, labios = 1;
  let wHabla = 0, batuta = null, proxBatuta = 1, ladoBatuta = 'D';
  let parpado = 1, proxParpadeo = 2 + azar() * 3, enParpadeo = -1, doble = false, ultimoParpadeo = -9;
  let cejas = 0, cejasPico = 0, sonrisa = 1, ceno = 0;
  let mira = null;          // un punto del mundo; null: la cámara (la sala)
  let salaHasta = 0;        // hasta cuándo mira a la sala pase lo que pase (mirarSala)
  let ojoX = 0, ojoY = 0, yawAntes = 0, miraModo = 'sala';
  const yawCab = { x: 0, v: 0 }, pitchCab = { x: 0, v: 0 };   // lo que la cabeza ya giró (para los ojos)
  let destinoX = grupo.position.x, wCaminar = 0, rumbo = grupo.rotation.y || 0, rumboBase = rumbo, andaba = false;
  const rumboM = { x: rumbo, v: 0 };
  // caminar: la velocidad (unidades por segundo), el rumbo mientras anda (1.1: casi de perfil; el presentador va en 3/4)
  // y lo que avanza cada paso
  let velocidad = 0.95, rumboCaminar = 1.1, zancada = 0.5;
  let entrada = null;       // subir o bajar detrás del subtítulo: {tipo, desde, hasta, dur, t, espera, al, casi, gracias}
  let hondo = HONDO;        // cuánto baja agachado
  let wBrazos = 0;          // lo agachado, con 80 ms de retraso: los brazos llegan después que el cuerpo
  let tAsentar = 9, asentar = 0;   // el asentamiento al terminar de subir (la columna pasa un poco y vuelve)
  let yQuieto = 0;          // dónde se queda el cuerpo sin moverse: 0 de pie, −hondo agachado
  let salto = 0;
  // `apertura`: lo más que la cara se aparta de la sala (el rumbo del cuerpo más el giro de la cabeza), en radianes
  const api = { camara: null, apertura: 0.55, plano: null };

  // ── El reposo vivo ──
  const ruido = crearRuido(azar);
  const frecRuido = [0.15 + azar() * 0.15, 0.15 + azar() * 0.15, 0.15 + azar() * 0.15];
  // el peso en una pierna (−1 la I … 1 la D): cambia cada 6–10 s en 0.8 s (con 0.1 s de anticipación)
  let pesoDe = azar() < 0.5 ? -0.8 : 0.8, pesoA = pesoDe, tPeso = -9, proxPeso = 1.5 + azar() * 2, pesoEf = pesoDe;
  let cambiosPeso = 0, sacadicos = 0, parpadeos = 0;
  let sacX = 0, sacY = 0, proxSac = 0.8 + azar() * 1.7;
  // la casa: las manos juntas al frente; cada 10–20 s cambia por un rato (a los brazos sueltos solo con la figura
  // entera); `casaDe` → `casaA` en 0.9 s
  let casaDe = 'junta', casaA = 'junta', tCasa = -9, proxCasa = 10 + azar() * 10;
  const qCasas = Object.fromEntries(Object.entries(CASAS).map(([n, c]) => [n, Object.fromEntries(Object.entries(c).map(([j, e]) => [j, qDe(j, e)]))]));
  let asiento = 9;          // el asentamiento del peso al terminar de caminar (s desde que frenó)

  // ── Los pies: dónde está apoyado cada uno (en el mundo), hacia dónde mira y, si da un paso, su vuelo ──
  const cadera0 = huesos.cadera.position.clone();
  const LARGO = { muslo: huesos.rodillaI.position.length(), pierna: huesos.tobilloI.position.length() };
  const pieLocal = {}, pieRot = {};
  let yTobillo = 0.06;
  {
    // la pose de reposo puesta un momento en los huesos: dónde quedan los tobillos (respecto del grupo) y cómo miran
    const guardado = ARTICULACIONES.map((j) => huesos[j].quaternion.clone());
    ARTICULACIONES.forEach((j) => huesos[j].quaternion.copy(base[j]));
    grupo.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(grupo.matrixWorld).invert();
    const sinGiro = new THREE.Matrix4().makeRotationY(-(grupo.rotation.y || 0));
    for (const l of LADOS) {
      const tb = huesos[`tobillo${l}`];
      const p = new THREE.Vector3().setFromMatrixPosition(tb.matrixWorld).applyMatrix4(inv);
      pieLocal[l] = new THREE.Vector3(p.x, 0, p.z);
      yTobillo = p.y - cuerpo.position.y;
      pieRot[l] = new THREE.Matrix4().extractRotation(tb.matrixWorld).premultiply(sinGiro);
    }
    ARTICULACIONES.forEach((j, i) => huesos[j].quaternion.copy(guardado[i]));
  }
  const plantaReposo = (l, x, r, out) => out.copy(pieLocal[l]).applyAxisAngle(Y, r).add(tmpV.set(x, 0, grupo.position.z));
  const pies = Object.fromEntries(LADOS.map((l) => [l, { p: plantaReposo(l, grupo.position.x, rumbo, new THREE.Vector3()), yaw: rumbo, vuelo: null }]));
  let tSinPaso = 9, ultimoPie = 'D', fase = 0;

  // ── Los gestos ──
  // cuánto baja la recta del hombro a la punta de los dedos respecto de la recta al punto: el índice apunta justo; la
  // palma (presentar) y la mano abierta (indicar), un poco por debajo, sin dejar de caer en lo que se muestra
  const BAJAR = { senalar: 0, presentar: 0.12, indicar: 0.05 };
  function gesto(nombre, o = {}) {
    const hacer = GESTOS[nombre];
    if (!hacer) return 0;
    const opciones = { ...o };
    // señalar, presentar e indicar: el brazo del lado del punto y el ángulo del hombro que lo apunta, medidos con el
    // rumbo al que va el cuerpo (si está girando, apunta a donde quedará)
    let apuntaA = null;
    if (BAJAR[nombre] !== undefined && o.punto) {
      const r0 = grupo.rotation.y;
      grupo.rotation.y = rumboBase;
      const lado = o.lado || ladoDe(o.punto);
      opciones.lado = lado;
      // primero el brazo apuntado; después, con el codo, la muñeca y la mano de ese gesto, la punta del índice
      const borrador = hacer({ ...opciones, apunta: apuntar(lado, o.punto, BAJAR[nombre]) });
      const forma = typeof borrador.manos?.[lado] === 'string' ? borrador.manos[lado] : null;
      opciones.apunta = apuntar(lado, o.punto, BAJAR[nombre], borrador.pose || null, forma);
      grupo.rotation.y = r0;
      grupo.updateMatrixWorld(true);
      apuntaA = { lado, punto: o.punto.clone(), bajar: BAJAR[nombre], pose: borrador.pose || null, forma };
    }
    const nuevo = hacer(opciones);
    // (y en cada cuadro el hombro vuelve a apuntar: el pecho se mueve con la respiración, la mirada y el giro)
    if (apuntaA && nuevo.pose?.[`hombro${apuntaA.lado}`]) nuevo.apuntaA = apuntaA;
    // cualquier gesto se puede sostener hasta otro (o hasta detenerGesto); y entrar más rápido (la despedida que se agacha)
    if (o.sostener === true) nuevo.sostener = true;
    if (Number.isFinite(o.entra) && o.entra > 0) nuevo.entra = o.entra;
    // y mirar su punto de otra manera ('sigue': mientras la cámara viaja; 'sala'; {objetivo, cada, dura})
    if (o.mirada !== undefined) nuevo.mirada = o.mirada;
    // el mismo gesto que sigue (enumerar: un dedo más con cada frase): cambia sus manos sin volver a empezar
    if (o.seguir && clip && nombreClip === nombre) {
      clip.manosEn = normalizarManos(nuevo.manos);
      for (const l of Object.keys(clip.manosEn)) clip.manosEn[l] = clip.manosEn[l].map(([, f]) => [0, f]).slice(-1);
      return clip.sostener ? Infinity : clip.dur;
    }
    // de dónde viene: lo que pedía el gesto anterior en el último cuadro (sus articulaciones y sus manos), para entrar
    // desde ahí y no desde el reposo
    const viejo = clip && pesoBase(clip, tClip) > 0.01 ? clip : null;
    if (viejo) {
      const nuevoDesde = {};
      for (const j of viejo.articulaciones) nuevoDesde[j] = trasClip[j].clone();
      if (desde) for (const j of Object.keys(desde)) if (!nuevoDesde[j]) nuevoDesde[j] = trasClip[j].clone();
      desde = nuevoDesde;
      desdeManos = {};
      for (const l of LADOS) if (viejo.manosEn?.[l]) desdeManos[l] = [...dedos[l]];
    } else { desde = null; desdeManos = null; }
    clip = preparar(nuevo, nombre);
    tClip = 0;
    nombreClip = nombre;
    alTerminarClip = typeof o.alTerminar === 'function' ? o.alTerminar : null;
    if (clip.cara?.cejas) cejasPico = Math.max(cejasPico, clip.cara.cejas);
    return clip.sostener ? Infinity : clip.dur;
  }
  // El clip listo para usar: sus poses en cuaterniones, el retraso de cada articulación, cuánto vive, los vaivenes y
  // si algún brazo cambia de lado (pasa por delante)
  function preparar(c, nombre) {
    c.nombre = nombre;
    c.entra = c.entra ?? 0.4;
    c.sale = c.sale ?? 0.45;
    c.manosEn = normalizarManos(c.manos);
    c.qPose = Object.fromEntries(Object.entries(c.pose || {}).map(([j, e]) => [j, qDe(j, e)]));
    // las claves: cada una con todas las articulaciones que toca alguna (las que no nombra, en reposo) y su curva
    if (c.claves) {
      const todas = [...new Set(c.claves.flatMap(([, p]) => Object.keys(p)))];
      c.qClaves = c.claves.map(([tt, p, cv]) => [tt, Object.fromEntries(todas.map((j) => [j, p[j] ? qDe(j, p[j]) : base[j].clone()])), cv || 'suave']);
      for (const j of todas) c.qPose[j] = c.qClaves[0][1][j];
    }
    c.curvaEntra = c.qClaves?.[0]?.[2] || c.curva || 'suave';
    c.articulaciones = Object.keys(c.qPose).filter((j) => ARTICULACIONES.includes(j));
    // el retraso de cada una (y el de los dedos)
    const propio = c.retraso || {};
    const ret = (j) => propio[j] ?? propio[familia(j)] ?? RETRASO[familia(j)] ?? 0;
    c.ret = Object.fromEntries(ARTICULACIONES.map((j) => [j, ret(j)]));
    c.retDedos = propio.dedos ?? RETRASO.dedos;
    const mas = Math.max(0, c.retDedos, ...c.articulaciones.map((j) => c.ret[j]));
    const menos = Math.min(0, ...c.articulaciones.map((j) => c.ret[j]));
    c.retMax = mas;
    c.vida = c.dur + mas;
    c.entrado = c.entra + mas - menos;
    // los vaivenes: los ciclos (con su período algo distinto cada uno) calculados de una vez
    c.vaivenes = (c.vaiven || []).flatMap((v) => {
      const ciclos = [];
      let tt = v.desde ?? 0;
      const hasta = Math.min(v.hasta ?? c.dur, 60);
      while (tt < hasta && ciclos.length < 400) {
        const p = 1 / (Math.max(0.05, v.frec) * (1 + (v.azar ?? 0.1) * (azar() * 2 - 1)));
        ciclos.push([tt, p]);
        tt += p;
      }
      const uno = { ...v, desde: v.desde ?? 0, hasta, ciclos, decae: v.decae ?? 0.7, atras: 0 };
      const sig = v.cadena && (typeof v.cadena === 'number' ? { art: SIGUIENTE[v.art], amp: v.cadena } : v.cadena);
      return sig?.art ? [uno, { ...uno, art: sig.art, amp: sig.amp, atras: sig.retraso ?? 0.085 }] : [uno];
    });
    // la mirada: el plan (mira el punto un rato y vuelve a la sala, con otro vistazo cada tanto)
    if (c.mirar) {
      const m = c.mirada ?? { objetivo: 0.8 };
      c.plan = typeof m === 'string' ? { modo: m } : { modo: 'vistazo', objetivo: m.objetivo ?? 0.8, cada: m.cada || [2, 3], dura: m.dura ?? 0.7 };
      if (c.plan.modo === 'vistazo') c.plan.prox = c.plan.objetivo + c.plan.cada[0] + azar() * (c.plan.cada[1] - c.plan.cada[0]);
    }
    // el mismo brazo a otro lado (más de 1.2 rad entre el hombro de antes y el de ahora): pasa por delante
    c.arco = {};
    if (desde) for (const l of LADOS) {
      const h = `hombro${l}`;
      if (desde[h] && c.qPose[h] && 2 * Math.acos(Math.min(1, Math.abs(desde[h].dot(c.qPose[h])))) > 1.2) c.arco[l] = true;
    }
    c.desdeSolo = desde ? Object.keys(desde).filter((j) => !c.qPose[j]) : [];
    return c;
  }
  function normalizarManos(m = {}) {
    const out = {};
    for (const l of LADOS) {
      const v = m[l];
      if (!v) continue;
      out[l] = Array.isArray(v) ? v.map(([tt, f]) => [tt, MANOS[f] || MANOS.relajada]) : [[0, MANOS[v] || MANOS.relajada]];
    }
    return out;
  }
  // Cuánto pesa el clip en el instante `tau` (el de una articulación: el del clip menos su retraso): entra con su
  // curva y sale suave
  const entrando = (c, tau) => (tau <= 0 ? 0 : curva(c.curvaEntra, tau / c.entra, c.entra));
  const saliendo = (c, tau) => (c.sostener ? 1 : 1 - suave((tau - (c.dur - c.sale)) / c.sale));
  const pesoBase = (c, tau) => Math.max(0, entrando(c, tau)) * saliendo(c, tau);
  function detenerGesto() {
    if (!clip) return;
    clip.sostener = false;
    tClip = Math.max(tClip, clip.dur - clip.sale);
  }
  // El lado del brazo que apunta: el del lado del punto (visto desde el personaje)
  function ladoDe(punto) {
    grupo.updateMatrixWorld(true);
    tmpV.copy(punto);
    grupo.worldToLocal(tmpV);
    return tmpV.x >= 0 ? 'I' : 'D';
  }
  // El ángulo del hombro (Euler 'XZY') que deja el brazo apuntando a `punto`; `bajar` lo baja (presentar: la palma
  // abierta hacia lo que se muestra, no el dedo). Con `pose` (el codo y la muñeca del gesto) y `forma` (la mano), lo
  // que apunta es la recta del hombro a la punta del índice, no el brazo: el codo, la muñeca y la mano la desvían
  // (señalar con el brazo apuntado erraba unos 8°: 50 px a tamaño de presentación)
  function apuntar(lado, punto, bajar = 0, pose = null, forma = null) {
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
    const euler = (v) => [Math.atan2(-v.z, -v.y), 0, Math.asin(Math.max(-1, Math.min(1, v.x)))];
    const v = pose ? puntaEnHombro(lado, pose, forma) : null;
    if (!v) return euler(d);
    // la dirección a pedirle al hombro para que la punta caiga en la recta: unas vueltas de corrección
    const pedido = d.clone(), w = new THREE.Vector3(), q = new THREE.Quaternion(), corr = new THREE.Quaternion();
    for (let i = 0; i < 5; i++) {
      qDe(`hombro${lado}`, euler(pedido), q);
      w.copy(v).applyQuaternion(q);
      corr.setFromUnitVectors(w, d);
      pedido.applyQuaternion(corr).normalize();
    }
    return euler(pedido);
  }
  // Hacia dónde queda la punta del índice desde el hombro (en el espacio del hombro, sin girar) con el codo y la muñeca
  // de `pose` y la mano `forma`: se ponen un momento y se restauran
  function puntaEnHombro(lado, pose, forma) {
    const h = huesos[`hombro${lado}`], c = huesos[`codo${lado}`], m = huesos[`muneca${lado}`];
    const [base, punta] = manos[lado].dedos[0];
    const guardado = [h.quaternion.clone(), c.quaternion.clone(), m.quaternion.clone(), base.rotation.clone(), punta.rotation.clone()];
    h.quaternion.identity();
    if (pose[`codo${lado}`]) qDe(`codo${lado}`, pose[`codo${lado}`], c.quaternion);
    if (pose[`muneca${lado}`]) qDe(`muneca${lado}`, pose[`muneca${lado}`], m.quaternion);
    const v0 = MANOS[forma]?.[0] ?? 0;
    base.rotation.set(-0.14 * (1 - v0), 0, -1.5 * v0);
    punta.rotation.set(0, 0, -1.3 * v0);
    h.updateMatrixWorld(true);
    const v = h.worldToLocal(punta.localToWorld(new THREE.Vector3(0, -0.044, 0)));
    h.quaternion.copy(guardado[0]); c.quaternion.copy(guardado[1]); m.quaternion.copy(guardado[2]);
    base.rotation.copy(guardado[3]); punta.rotation.copy(guardado[4]);
    h.updateMatrixWorld(true);
    return v.lengthSq() > 1e-8 ? v.normalize() : null;
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
  /** Caminar hasta `x` (del mundo). `velocidad` en unidades por segundo (0.95 por omisión), `rumbo` el giro del cuerpo
   * mientras anda (1.1 por omisión; 0.6 es en 3/4, de cara a la sala) y `zancada` lo que avanza cada paso (0.45; no
   * más de 0.5: con las piernas cortas de la caricatura, un paso más largo hace bajar la cadera, y la cabeza, más de
   * 5 cm entre paso y paso) */
  function caminarA(x, o = {}) {
    destinoX = Number.isFinite(x) ? x : destinoX;
    velocidad = Number.isFinite(o.velocidad) && o.velocidad > 0 ? o.velocidad : 0.95;
    rumboCaminar = Number.isFinite(o.rumbo) ? Math.min(1.2, Math.abs(o.rumbo)) : 1.1;
    zancada = Number.isFinite(o.zancada) && o.zancada > 0 ? lim(o.zancada, 0.2, 0.5) : 0.45;
  }
  /** Ponerlo en `x` sin caminar (el presentador mueve la cámara con él: no se nota); los pies van con él */
  function reubicar(x) {
    if (!Number.isFinite(x)) return;
    const d = x - grupo.position.x;
    grupo.position.x = x;
    destinoX = x;
    for (const l of LADOS) {
      pies[l].p.x += d;
      if (pies[l].vuelo) { pies[l].vuelo.desde.x += d; pies[l].vuelo.hasta.x += d; }
    }
  }
  function mirarA(p) { mira = p ? p.clone() : null; }
  /** Mirar a la sala (la cámara) `seg` segundos, aunque el gesto o mirarA pidan otra cosa (el comienzo de una frase) */
  function mirarSala(seg = 1) { salaHasta = t + Math.max(0, Number(seg) || 0); }
  // ── Detrás del subtítulo: subir y bajar agachado (las rodillas dobladas y la columna adelante; lo de abajo del corte
  // no se ve). `hondo`: cuánto baja (que la cabeza quede bajo el corte del plano) ──
  function mover(tipo, hasta, dur, al, o = {}) {
    entrada = { tipo, desde: cuerpo.position.y, hasta, dur, t: 0, espera: o.espera || 0, al: al || null,
      casi: Array.isArray(o.casi) ? o.casi : null, gracias: !!o.gracias };
  }
  const ponerHondo = (h) => { if (Number.isFinite(h) && h > 0.2) hondo = h; };
  /** Sube desde agachado detrás del subtítulo: el cuerpo de −hondo a 0 sin pasarse (los brazos 80 ms después y la
   * columna, que se endereza, pasa un poco y vuelve), 0.8 s. `casi: [s, f]` llama a f cuando faltan s segundos (el
   * saludo empieza antes de terminar de subir); `instante`: ya arriba */
  function entrar(al, o = {}) {
    grupo.visible = true;
    ponerHondo(o.hondo);
    if (reducido || o.instante) {
      entrada = null;
      cuerpo.position.y = yQuieto = 0;
      try { o.casi?.[1]?.(); } catch { /* nada */ }
      al?.();
      return;
    }
    cuerpo.position.y = -hondo;
    wBrazos = 1;
    mover('entra', 0, Number(o.dur) > 0 ? o.dur : ENTRAR_S, al, o);
  }
  /** Se asoma desde donde esté (a medio agacharse, o desde `desde` si está más abajo): lo mismo que entrar, más corto y
   * con menos rebote (0.45 s desde abajo del todo) */
  function asomarse(al, o = {}) {
    grupo.visible = true;
    ponerHondo(o.hondo);
    if (Number.isFinite(o.desde)) cuerpo.position.y = Math.min(cuerpo.position.y, o.desde);
    const falta = Math.min(1, Math.max(0, -cuerpo.position.y / hondo));
    if (reducido || falta < 0.002) { entrada = null; cuerpo.position.y = yQuieto = 0; al?.(); return; }
    mover('asoma', 0, Math.max(0.15, (Number(o.dur) > 0 ? o.dur : ASOMARSE_S) * Math.sqrt(falta)), al, o);
  }
  /** Se agacha detrás del subtítulo hasta que no se ve (0.3 s), sin subir antes; queda a la vista (agachado) */
  function agacharse(al, o = {}) {
    ponerHondo(o.hondo);
    if (reducido) { entrada = null; cuerpo.position.y = yQuieto = -hondo; al?.(); return; }
    mover('agacha', -hondo, Number(o.dur) > 0 ? o.dur : AGACHARSE_S, al, o);
  }
  /** Se va: se agacha sin subir antes (0.45 s) y desaparece. `gracias`: antes, un asentimiento de «gracias» (0.15 s
   * de más; la despedida del cierre) */
  function salir(al, o = {}) {
    const fin = () => { grupo.visible = false; cuerpo.position.y = yQuieto = -hondo; al?.(); };
    ponerHondo(o.hondo);
    if (reducido) { entrada = null; fin(); return; }
    mover('sale', -hondo, Number(o.dur) > 0 ? o.dur : SALIR_S, fin, { espera: o.gracias ? GRACIAS_S : 0, gracias: o.gracias });
  }

  // ── Los pies ──
  /** Un paso del pie `l`: de donde está a `hasta` (del mundo), girando a `yaw`, en `dur` s y levantándolo `alto` */
  function pisar(l, hasta, yaw, dur, alto) {
    const p = pies[l];
    p.vuelo = { desde: p.p.clone(), hasta: hasta.clone(), yaw0: p.yaw, yaw1: yaw, u: 0, dur, alto };
    ultimoPie = l;
  }
  // Cada cuadro: el pie que vuela sigue su arco; si ninguno vuela, caminando da el paso el que quedó más atrás (cae
  // media zancada más allá de donde estará el cuerpo, o junto al otro al final) y quieto acomoda el que quedó lejos de
  // donde va (al llegar, al girar el cuerpo). Agachado, oculto o con movimiento reducido, van con el cuerpo
  function moverPies(dt, anda, dx, wAg) {
    if (!grupo.visible || reducido || wAg > 0.5) {
      for (const l of LADOS) { plantaReposo(l, grupo.position.x, rumbo, pies[l].p); pies[l].yaw = rumbo; pies[l].vuelo = null; }
      return;
    }
    tSinPaso += dt;
    for (const l of LADOS) {
      const v = pies[l].vuelo;
      if (!v) continue;
      v.u = Math.min(1, v.u + dt / v.dur);
      fase = (l === 'I' ? 0 : Math.PI) + Math.PI * v.u;
      if (v.u >= 1) { pies[l].p.copy(v.hasta); pies[l].yaw = v.yaw1; pies[l].vuelo = null; tSinPaso = 0; }
    }
    if (pies.I.vuelo || pies.D.vuelo || tSinPaso < (anda ? 0.02 : 0.15)) return;
    if (anda) {
      const dir = Math.sign(dx), resta = Math.abs(dx);
      const aI = pies.I.p.x * dir, aD = pies.D.p.x * dir;
      const l = aI < aD - 0.01 ? 'I' : aD < aI - 0.01 ? 'D' : ultimoPie === 'I' ? 'D' : 'I';
      // el pie cae adelante la mitad de lo que el cuerpo avanza en un paso, así el de apoyo va de media zancada
      // adelante a media atrás; el vuelo dura lo que tarda el cuerpo en dejar al de apoyo media zancada atrás (el
      // primer paso, que sale con los pies juntos, la mitad)
      const vuelo = 0.85 * lim(zancada / velocidad, 0.25, 0.5), media = 0.5 * velocidad * (vuelo + 0.02);
      const o = otro(l);
      plantaReposo(o, grupo.position.x, pies[o].yaw, tmpV2);
      const apoyo = (pies[o].p.x - tmpV2.x) * dir;
      const dur = lim(tiempoPara(Math.min(resta, apoyo + media), vuelo), 0.16, vuelo);
      const avanza = Math.min(resta, recorrido(resta, dur));
      const queda = resta - avanza;
      const yaw = queda > 0.1 ? dir * rumboCaminar : rumboBase;
      plantaReposo(l, grupo.position.x + dir * (avanza + Math.min(queda, media)), yaw, tmpV2);
      pisar(l, tmpV2, yaw, dur, 0.06);
      return;
    }
    let peor = null, err = 0;
    for (const l of LADOS) {
      plantaReposo(l, grupo.position.x, rumboBase, tmpV2);
      const e = Math.hypot(pies[l].p.x - tmpV2.x, pies[l].p.z - tmpV2.z) + 0.12 * Math.abs(pies[l].yaw - rumboBase);
      if (e > err) { err = e; peor = l; }
    }
    if (peor && err > 0.035) { plantaReposo(peor, grupo.position.x, rumboBase, tmpV2); pisar(peor, tmpV2, rumboBase, 0.3, 0.035); }
  }
  // Lo que avanzará el cuerpo en `s` segundos (arranca despacio: lo mismo que hace actualizar), sin pasar de `resta`
  function recorrido(resta, s) {
    let x = 0, w = wCaminar;
    const h = s / 12;
    for (let i = 0; i < 12; i++) { w += (1 - w) * acercar(6, h); x += Math.min(resta - x, velocidad * h * (0.4 + 0.6 * w)); }
    return x;
  }
  // Cuánto tarda el cuerpo en avanzar `d` (a lo sumo `max` s)
  function tiempoPara(d, max) {
    let x = 0, w = wCaminar, s = 0;
    const h = 1 / 120;
    while (x < d && s < max) { w += (1 - w) * acercar(6, h); x += velocidad * h * (0.4 + 0.6 * w); s += h; }
    return s;
  }
  // Dónde va el tobillo del pie `l` (del mundo): sobre su apoyo, a la altura del piso del cuerpo (que baja y sube con
  // él: agachado, el saltito) más el arco del paso
  function tobilloEn(l, out) {
    const p = pies[l], v = p.vuelo;
    if (v) out.lerpVectors(v.desde, v.hasta, suave(v.u));
    else out.copy(p.p);
    out.y = grupo.position.y + cuerpo.position.y + yTobillo + (v ? v.alto * Math.sin(Math.PI * v.u) : 0);
    return out;
  }
  const yawPie = (l) => { const v = pies[l].vuelo; return v ? v.yaw0 + (v.yaw1 - v.yaw0) * suave(v.u) : pies[l].yaw; };
  // Las piernas alcanzan los pies (dos huesos: el muslo apunta para que la rodilla doble lo justo hacia adelante y el
  // tobillo deja el pie plano, mirando hacia donde quedó). Si no llegan, la cadera baja lo necesario. `w`: cuánto manda
  // esto sobre la pose de las piernas (nada agachado)
  const ikObj = { I: new THREE.Vector3(), D: new THREE.Vector3() }, ikCad = new THREE.Vector3();
  const ikInv = new THREE.Matrix4(), ikE = new THREE.Matrix4(), ikF = new THREE.Matrix4(), ikR = new THREE.Matrix4(), ikW = new THREE.Matrix4();
  const e1 = new THREE.Vector3(), e2 = new THREE.Vector3(), e3 = new THREE.Vector3(), f1 = new THREE.Vector3(), f2 = new THREE.Vector3(), f3 = new THREE.Vector3();
  const ikP = new THREE.Vector3(), ikQ = new THREE.Quaternion(), X = new THREE.Vector3(1, 0, 0);
  let bajaCadera = 0;
  function apoyar(w) {
    bajaCadera = 0;
    if (w < 0.001) return;
    huesos.cadera.updateWorldMatrix(true, false);
    const R = LARGO.muslo + LARGO.pierna - 0.0007;
    for (const l of LADOS) {
      const m = huesos[`muslo${l}`];
      m.parent.updateWorldMatrix(false, false);
      ikCad.copy(m.position).applyMatrix4(m.parent.matrixWorld);
      tobilloEn(l, ikObj[l]);
      const hd = Math.hypot(ikObj[l].x - ikCad.x, ikObj[l].z - ikCad.z), vd = ikCad.y - ikObj[l].y;
      if (hd < R) { const vMax = Math.sqrt(R * R - hd * hd); if (vd > vMax) bajaCadera = Math.max(bajaCadera, vd - vMax); }
    }
    if (bajaCadera > 0) {
      huesos.cadera.position.y -= bajaCadera * w;
      huesos.cadera.updateWorldMatrix(false, false);
      for (const l of LADOS) huesos[`muslo${l}`].parent.updateWorldMatrix(false, false);
    }
    for (const l of LADOS) pierna(l, ikObj[l], w);
  }
  function pierna(l, objetivoMundo, w) {
    const m = huesos[`muslo${l}`], r = huesos[`rodilla${l}`], tb = huesos[`tobillo${l}`];
    const A = LARGO.muslo, B = LARGO.pierna;
    ikInv.copy(m.parent.matrixWorld).invert();
    ikP.copy(objetivoMundo).applyMatrix4(ikInv).sub(m.position);   // de la cadera al tobillo, en la raíz de la pierna
    const d = lim(ikP.length(), Math.abs(A - B) + 0.02, A + B - 0.0002);
    const th = Math.max(0.02, Math.acos(lim((d * d - A * A - B * B) / (2 * A * B), -1, 1)));
    // en el muslo: hacia dónde queda el tobillo con esa rodilla (f1) y hacia dónde la rodilla (f2)
    f1.set(0, -A - B * Math.cos(th), -B * Math.sin(th)).normalize();
    f2.set(0, -A, 0).addScaledVector(f1, A * f1.y).normalize();
    f3.crossVectors(f1, f2);
    // en la raíz: hacia el tobillo (e1) y la rodilla hacia adelante del pie (e2)
    e1.copy(ikP).normalize();
    const yaw = yawPie(l);
    e2.set(Math.sin(yaw), 0, Math.cos(yaw)).transformDirection(ikInv);
    e2.addScaledVector(e1, -e2.dot(e1));
    if (e2.lengthSq() < 1e-6) e2.set(0, 0, 1);
    e2.normalize();
    e3.crossVectors(e1, e2);
    ikE.makeBasis(e1, e2, e3);
    ikF.makeBasis(f1, f2, f3).transpose();
    ikQ.setFromRotationMatrix(ikR.multiplyMatrices(ikE, ikF));
    m.quaternion.slerp(ikQ, w);
    r.quaternion.slerp(ikQ.setFromAxisAngle(X, th), w);
    // el tobillo: el pie como en reposo, girado a donde quedó apoyado
    m.updateWorldMatrix(false, false);
    r.updateWorldMatrix(false, false);
    ikW.makeRotationY(yaw).multiply(pieRot[l]);
    ikR.extractRotation(r.matrixWorld).transpose();
    ikQ.setFromRotationMatrix(ikR.multiply(ikW));
    tb.quaternion.slerp(ikQ, w);
  }

  // ── Cada cuadro ──
  const sumar = (j, x, y, z) => { objetivo[j].multiply(qDe(j, [x, y, z], tmpQ)); };
  const sumarExtra = (j, eje, v) => { if (extra[j]) extra[j][eje] += v; };
  // la mirada de hace `d` segundos (la cabeza la sigue 0.1 s después de los ojos; la columna y la cadera, 0.2 s)
  const HIST = 128, hT = new Float64Array(HIST).fill(-9), hY = new Float64Array(HIST), hP = new Float64Array(HIST);
  let hI = 0;
  const atras = [0, 0];
  function miradaDe(d) {
    const tt = t - d;
    for (let k = 1; k <= HIST; k++) {
      const i = (hI - k + HIST) % HIST;
      if (hT[i] <= tt + 1e-9) { atras[0] = hY[i]; atras[1] = hP[i]; return atras; }
    }
    return atras;
  }
  // El clip en la articulación `j` en el instante `tau` (su pose en las claves)
  function poseEn(c, j, tau, out) {
    const ks = c.qClaves;
    if (!ks) return out.copy(c.qPose[j]);
    let k = 0;
    while (k < ks.length - 1 && tau >= ks[k + 1][0]) k++;
    if (k >= ks.length - 1 || tau <= ks[0][0]) return out.copy(ks[k][1][j]);
    const [t0, p0] = ks[k], [t1, p1, cv] = ks[k + 1];
    return out.slerpQuaternions(p0[j], p1[j], curva(cv, (tau - t0) / Math.max(1e-3, t1 - t0), t1 - t0));
  }
  // ¿El clip mira su punto ahora? (el plan de su mirada)
  function miraClip(c, tau) {
    const p = c.plan;
    if (!p || p.modo === 'sala') return false;
    if (p.modo === 'objetivo') return true;
    if (p.modo === 'sigue') return tau % 3 < 2.4;
    if (tau < p.objetivo) return true;
    if (tau >= p.prox + p.dura) p.prox += p.dura + p.cada[0] + azar() * (p.cada[1] - p.cada[0]);
    return tau >= p.prox && tau < p.prox + p.dura;
  }
  function vaivenEn(v, tau) {
    const tt = tau - v.atras;
    if (tt < v.desde || tt > v.hasta) return 0;
    let k = 0;
    while (k < v.ciclos.length - 1 && tt >= v.ciclos[k + 1][0]) k++;
    const [t0, per] = v.ciclos[k];
    const fr = Math.min(1, (tt - t0) / per);
    const env = suave((tt - v.desde) / 0.1) * (1 - suave((tt - (v.hasta - 0.2)) / 0.2));
    return v.amp * env * v.decae ** (k + fr) * Math.sin(2 * Math.PI * fr);
  }
  function golpeEn(g, tau) {
    const d = tau - g.t, ida = g.ida ?? 0.12, vuelta = g.vuelta ?? 0.25;
    if (d < 0 || d > ida + vuelta) return 0;
    return d < ida ? g.amp * (d / ida) ** 2 : g.amp * (1 - (d - ida) / vuelta) ** 2;
  }

  function actualizar(dtIn) {
    // (con pocos cuadros por segundo, un equipo lento que dibuja la maqueta, el tiempo no se estira; tras una pestaña
    // oculta, tampoco salta)
    const dt = Math.min(0.25, Math.max(0, dtIn || 0));
    t += dt;
    const n = Math.max(1, Math.ceil(dt / PASO_MUELLE - 1e-6)), h = dt / n;

    // ── moverse: el cuerpo hacia su x (más lento al arrancar) y el rumbo con su muelle ──
    const dx = destinoX - grupo.position.x;
    const anda = Math.abs(dx) > 0.01;
    wCaminar += ((anda ? 1 : 0) - wCaminar) * acercar(6, dt);
    if (anda) grupo.position.x += Math.sign(dx) * Math.min(Math.abs(dx), velocidad * dt * (0.4 + 0.6 * wCaminar));
    else if (andaba) asiento = 0;   // frenó: se asienta el peso
    andaba = anda;
    if (reducido && !anda) { rumboM.x = rumboBase; rumboM.v = 0; }
    else {
      const obj = anda ? Math.sign(dx) * rumboCaminar : rumboBase, [w, z] = MUELLES.rumbo;
      for (let i = 0; i < n; i++) { rumboM.v += h * (w * w * (obj - rumboM.x) - 2 * z * w * rumboM.v); rumboM.x += rumboM.v * h; }
    }
    rumbo = rumboM.x;
    grupo.rotation.y = rumbo;
    const wAg = Math.max(0, Math.min(1, -cuerpo.position.y / hondo));
    moverPies(dt, anda, dx, wAg);

    // ── el gesto: cuánto pesa ahora ──
    let wClip = 0, clipManos = null, clipCara = null;
    if (clip) {
      tClip += dt;
      if (!clip.sostener && tClip >= clip.vida) {
        const al = alTerminarClip;
        clip = null; nombreClip = null; alTerminarClip = null; desde = null; desdeManos = null;
        try { al?.(); } catch { /* nada */ }
      } else {
        wClip = pesoBase(clip, tClip);
        clipManos = clip.manosEn;
        clipCara = clip.cara || null;
      }
    }
    const pesoArt = (j) => (clip ? Math.max(0, entrando(clip, tClip - clip.ret[j])) * saliendo(clip, tClip - clip.ret[j]) : 0);

    // ── el reposo: la casa (y cada tanto otra) ──
    for (const j of ARTICULACIONES) { objetivo[j].copy(base[j]); extra[j][0] = extra[j][1] = extra[j][2] = 0; }
    const ocupado = !!clip || hablando || anda;
    if (!reducido && ((!ocupado && t >= proxCasa) || (ocupado && casaA !== 'junta'))) {
      // (hablando, con un gesto o caminando vuelve a la de siempre: es la que queda al terminar)
      casaDe = casaA;
      casaA = casaA !== 'junta' || ocupado ? 'junta' : api.plano === 'entero' && azar() < 0.4 ? 'sueltos' : 'muneca';
      if (!qCasas[casaA]) casaA = 'junta';
      tCasa = t;
      proxCasa = t + (casaA === 'junta' ? 10 + azar() * 10 : 5 + azar() * 4);
    }
    {
      const u = suave((t - tCasa) / 0.9);
      const de = qCasas[casaDe], a = qCasas[casaA];
      if (u < 1 && de) for (const j of Object.keys(de)) objetivo[j].copy(de[j]).slerp(a[j], u);
      else if (casaA !== 'junta') for (const j of Object.keys(a)) objetivo[j].copy(a[j]);
    }

    // ── el reposo vivo: el peso en una pierna, la respiración y la cabeza (sin nada de eso con movimiento reducido) ──
    if (!reducido) {
      if (t >= proxPeso && !anda) {
        pesoDe = pesoReposo();
        pesoA = (pesoDe > 0 ? -1 : 1) * (0.7 + 0.3 * azar());
        tPeso = t;
        proxPeso = t + 6 + azar() * 4;
        cambiosPeso++;
      }
      // el gesto pone su peso; caminando, el paso manda
      const wCad = clip?.cuerpo?.peso !== undefined ? pesoArt('cadera') : 0;
      pesoEf = (pesoReposo() + (wCad ? (clip.cuerpo.peso - pesoReposo()) * wCad : 0)) * (1 - wCaminar);
      // la pelvis cae del lado de la pierna libre y la columna lo compensa: la cabeza queda derecha
      sumar('cadera', 0, 0, -0.04 * pesoEf);
      sumar('columna', 0, 0, 0.026 * pesoEf);
      sumar('pecho', 0, 0, 0.012 * pesoEf);
      sumar('cuello', 0, 0, 0.006 * pesoEf);
      // la respiración (4 s: inspira en 1.6, espira en 2.4): el pecho sube y los hombros se abren
      const fr = t % 4, r = (fr < 1.6 ? suave(fr / 1.6) : 1 - suave((fr - 1.6) / 2.4)) - 0.5;
      sumar('pecho', -0.03 * r, 0, 0);
      sumar('columna', -0.008 * r, 0, 0);
      sumar('hombroI', 0, 0, 0.03 * r);
      sumar('hombroD', 0, 0, 0.03 * r);
      // la cabeza nunca quieta del todo (el giro va con la mirada, que respeta la apertura)
      sumar('cabeza', 0.02 * ruido(t * frecRuido[1] + 31.7), 0, 0.02 * ruido(t * frecRuido[2] + 63.1));
    }

    // ── caminar: los brazos opuestos a las piernas (el codo más doblado al ir adelante), la pelvis que gira y cae del
    // lado del pie en el aire y el torso en contra; la cabeza, quieta hacia la sala ──
    if (wCaminar > 0.01) {
      const s = Math.sin(fase), w = wCaminar;
      for (const j of Object.keys(qAndar)) objetivo[j].slerp(qAndar[j], 0.8 * w);
      sumar('hombroI', 0.3 * s * w, 0, 0);
      sumar('hombroD', -0.3 * s * w, 0, 0);
      sumar('codoI', -0.35 * Math.max(0, -s) * w, 0, 0);
      sumar('codoD', -0.35 * Math.max(0, s) * w, 0, 0);
      sumar('cadera', 0, -0.08 * s * w, -0.04 * s * w);
      sumar('columna', 0.03 * w, 0.14 * s * w, 0.03 * s * w);
      sumar('cuello', 0, -0.06 * s * w, 0);
    }
    // al frenar, el peso se asienta (la cadera baja un poco y vuelve)
    asiento += dt;

    // ── agachado detrás del subtítulo: las rodillas, los muslos y la columna adelante; los brazos, con 80 ms de retraso
    // (subiendo se quedan un poco atrás y bajando se adelantan), y al terminar de subir la columna pasa un poco y vuelve ──
    wBrazos += (wAg - wBrazos) * acercar(12.5, dt);
    if (wAg > 0.001) {
      sumar('rodillaI', 0.7 * wAg, 0, 0);
      sumar('rodillaD', 0.7 * wAg, 0, 0);
      sumar('musloI', -0.4 * wAg, 0, 0);
      sumar('musloD', -0.4 * wAg, 0, 0);
      sumar('columna', 0.2 * wAg, 0, 0);
    }
    if (!reducido) {
      const atrasB = Math.max(-0.12, Math.min(0.12, wBrazos - wAg));
      if (Math.abs(atrasB) > 0.001) { sumar('hombroI', 0.9 * atrasB, 0, 0); sumar('hombroD', 0.9 * atrasB, 0, 0); }
      tAsentar += dt;
      if (tAsentar < 0.25) sumar('columna', -asentar * Math.sin((Math.PI * tAsentar) / 0.25), 0, 0);
      // el «gracias» de la despedida: la cabeza asiente antes de bajar
      if (entrada?.gracias) sumar('cabeza', 0.12 * Math.sin(Math.PI * Math.min(1, entrada.t / 0.35)), 0, 0);
    }

    // ── hablar: la casa de hablar (debajo del gesto: lo que el gesto no usa habla) y un golpe cada tanto con una mano
    // libre ──
    if (hablando && t > finHabla) hablando = false;
    wHabla += ((hablando && wCaminar < 0.3 ? 1 : 0) - wHabla) * acercar(2.4, dt);
    if (wHabla > 0.01) {
      for (const l of LADOS) {
        objetivo[`hombro${l}`].slerp(qDe(`hombro${l}`, CONVERSA.hombro, tmpQ2), wHabla * (l === 'D' ? 1 : 0.75));
        objetivo[`codo${l}`].slerp(qDe(`codo${l}`, CONVERSA.codo, tmpQ2), wHabla * (l === 'D' ? 1 : 0.75));
        objetivo[`muneca${l}`].slerp(qDe(`muneca${l}`, CONVERSA.muneca, tmpQ2), wHabla * 0.8);
      }
    }
    const libre = (l) => !clip || !clip.qPose[`hombro${l}`] || pesoArt(`hombro${l}`) < 0.3;
    if (hablando) {
      proxBatuta -= dt;
      if (proxBatuta <= 0 && !batuta) {
        const l = libre(ladoBatuta) ? ladoBatuta : libre(otro(ladoBatuta)) ? otro(ladoBatuta) : null;
        batuta = { t: 0, lado: l, fuerza: 0.6 + 0.4 * azar() };
        ladoBatuta = azar() < 0.65 ? otro(ladoBatuta) : ladoBatuta;
        proxBatuta = 0.9 + azar() * 1.1;
        cejasPico = Math.max(cejasPico, 0.25 + 0.3 * azar());
      }
    }
    if (batuta) {
      batuta.t += dt;
      const s = Math.sin(Math.PI * Math.min(1, batuta.t / 0.42)) * batuta.fuerza;
      if (!reducido) {
        if (wHabla > 0.05 && batuta.lado) {
          sumar(`codo${batuta.lado}`, -0.26 * s * wHabla, 0, 0);
          sumar(`hombro${batuta.lado}`, -0.08 * s * wHabla, 0, 0.03 * s * wHabla);
        }
        sumar('cabeza', 0.06 * s, 0, 0);
      }
      if (batuta.t >= 0.42) batuta = null;
    }

    // ── el gesto encima: cada articulación con su retraso, desde lo que pedía el gesto anterior (o desde la casa) ──
    let altoCadera = 0;
    if (clip) {
      const c = clip;
      // el brazo que apunta sigue apuntando al punto con el pecho como esté ahora
      const ap = c.apuntaA;
      if (ap && !c.qClaves) qDe(`hombro${ap.lado}`, apuntar(ap.lado, ap.punto, ap.bajar, ap.pose, ap.forma), c.qPose[`hombro${ap.lado}`]);
      for (const j of c.articulaciones) {
        const tau = tClip - c.ret[j];
        const e = entrando(c, tau), x = saliendo(c, tau);
        poseEn(c, j, tau, tmpQ);
        const src = desde?.[j] || objetivo[j];
        const f = familia(j), l = j.slice(-1);
        if (c.arco[l] && (f === 'hombro' || f === 'codo') && e < 1) {
          // por delante: hasta la mano frente al pecho (al 45 % de la entrada) y de ahí a la pose
          if (e < 0.45) tmpQ2.slerpQuaternions(src, qArco[f][l], e / 0.45);
          else tmpQ2.slerpQuaternions(qArco[f][l], tmpQ, (e - 0.45) / 0.55);
        } else tmpQ2.slerpQuaternions(src, tmpQ, e);
        objetivo[j].slerp(tmpQ2, x);
      }
      // lo que hacía el gesto anterior con articulaciones que este no usa: vuelve a la casa mientras este entra
      if (desde) for (const j of c.desdeSolo) objetivo[j].slerp(desde[j], 1 - suave((tClip - c.ret[j]) / c.entra));
      if (desde && tClip > c.entrado) { desde = null; desdeManos = null; }
      // el cuerpo acompaña (sumado al reposo)
      if (c.cuerpo) {
        for (const j of ['cadera', 'columna', 'pecho']) {
          const v = c.cuerpo[j];
          if (!v) continue;
          const w = pesoArt(j);
          if (w > 0) sumar(j, v[0] * w, v[1] * w, v[2] * w);
        }
        altoCadera = (c.cuerpo.alto || 0) * pesoArt('cadera');
      }
      // el vaivén de antes (con movimiento reducido, solo la cabeza: asentir y negar)
      for (const [j, eje, amp, frec, d0, d1] of c.osc || []) {
        if (tClip < d0 || tClip > d1 || (reducido && j !== 'cabeza' && j !== 'cuello')) continue;
        const env = suave((tClip - d0) / 0.25) * (1 - suave((tClip - (d1 - 0.25)) / 0.25));
        const v = amp * env * Math.sin(2 * Math.PI * frec * (tClip - d0)) * wClip;
        sumar(j, eje === 0 ? v : 0, eje === 1 ? v : 0, eje === 2 ? v : 0);
      }
      // los vaivenes y los golpes nuevos, después del muelle (su forma es la que se ve)
      if (!reducido) for (const v of c.vaivenes) sumarExtra(v.art, v.eje, vaivenEn(v, tClip) * wClip);
      for (const g of c.golpes || []) sumarExtra(g.art, g.eje, golpeEn(g, tClip) * wClip);
    } else if (desde) { desde = null; desdeManos = null; }
    for (const j of ARTICULACIONES) trasClip[j].copy(objetivo[j]);

    // ── hacia dónde mira: la sala si se lo pidieron (mirarSala), el punto del gesto (según su plan), el de mirarA o
    // la cámara ──
    const aLaSala = t < salaHasta;
    let punto = null;
    if (!aLaSala && clip && wClip > 0.3 && clip.mirar && miraClip(clip, tClip)) { punto = clip.mirar; miraModo = 'gesto'; }
    else if (!aLaSala && mira) { punto = mira; miraModo = 'punto'; }
    else miraModo = 'sala';
    const objetivoMira = punto || api.camara?.position || null;
    let yawObj = 0, pitchObj = 0, yawOjos = 0;
    if (objetivoMira) {
      grupo.updateWorldMatrix(true, false);
      tmpV.copy(objetivoMira);
      grupo.worldToLocal(tmpV);
      const ox = tmpV.x, oy = tmpV.y - 1.85, oz = tmpV.z;
      yawObj = Math.max(-0.62, Math.min(0.62, Math.atan2(ox, Math.max(0.05, oz))));
      pitchObj = Math.max(-0.5, Math.min(0.45, Math.atan2(oy, Math.hypot(ox, oz))));
    }
    // un giro grande de la mirada lleva un parpadeo
    if (Math.abs(yawObj - yawAntes) > 0.5 && enParpadeo < 0 && t - ultimoParpadeo > 0.4) parpadear();
    yawAntes = yawObj;
    if (!reducido) yawObj += 0.04 * ruido(t * frecRuido[0] + 7.3);
    // la apertura: la cara nunca se aparta de la sala más que `apertura` (el rumbo del cuerpo más el giro de la mirada);
    // lo que falta lo hacen los ojos. En 3/4, nunca de perfil
    {
      const ap = Math.max(0.1, Number(api.apertura) || 0.55);
      const recortado = Math.max(-ap - rumbo, Math.min(ap - rumbo, yawObj));
      yawOjos = Math.max(-1, Math.min(1, (yawObj - recortado) * 1.6));
      yawObj = recortado;
    }
    hT[hI] = t; hY[hI] = yawObj; hP[hI] = pitchObj; hI = (hI + 1) % HIST;
    // los ojos ya; la cabeza y el cuello 0.1 s después; la columna y la cadera, 0.2 s
    const [yC, pC] = miradaDe(0.1);
    sumar('cuello', -pC * 0.35, yC * 0.3, 0);
    sumar('cabeza', -pC * 0.55, yC * 0.4, 0);
    {
      const [yT, pT] = miradaDe(0.2);
      sumar('columna', -pT * 0.1, yT * 0.18, 0);
      sumar('cadera', 0, yT * 0.12, 0);
    }
    {
      const [w, z] = MUELLES.cabeza;
      for (let i = 0; i < n; i++) {
        yawCab.v += h * (w * w * (yC - yawCab.x) - 2 * z * w * yawCab.v); yawCab.x += yawCab.v * h;
        pitchCab.v += h * (w * w * (pC - pitchCab.x) - 2 * z * w * pitchCab.v); pitchCab.x += pitchCab.v * h;
      }
    }

    // ── los muelles: cada articulación va hacia lo pedido con su velocidad ──
    for (const j of ARTICULACIONES) {
      const [w, z] = muelle[j];
      for (let i = 0; i < n; i++) muelleQ(actual[j], vel[j], objetivo[j], w, z, h);
      huesos[j].quaternion.copy(actual[j]);
      const e = extra[j];
      if (e[0] || e[1] || e[2]) huesos[j].quaternion.multiply(qDe(j, e, tmpQ));
    }

    // ── el cuerpo: subir y bajar detrás del subtítulo y el saltito ──
    if (entrada) {
      const e = entrada;
      e.t += dt;
      const tt = Math.max(0, e.t - e.espera);
      const u = Math.min(1, tt / e.dur);
      // subiendo, sin pasarse (frena al llegar); bajando, sin subir antes
      const sube = e.hasta > e.desde;
      const k = sube ? 1 - (1 - u) ** 3 : u * u * (3 - 2 * u);
      cuerpo.position.y = e.desde + (e.hasta - e.desde) * k;
      if (e.casi && e.dur - tt <= e.casi[0]) { const f = e.casi[1]; e.casi = null; try { f?.(); } catch { /* nada */ } }
      if (u >= 1) {
        entrada = null;
        cuerpo.position.y = yQuieto = e.hasta;
        if (sube) { tAsentar = 0; asentar = e.tipo === 'entra' ? 0.02 : 0.012; }
        e.al?.();
      }
    } else {
      if (clip?.salto && !reducido) salto = Math.max(0, Math.sin(Math.min(1, (tClip - 0.35) / 0.5) * Math.PI)) * (tClip > 0.35 ? 0.12 : 0);
      else salto *= 1 - acercar(10, dt);
      if (grupo.visible) cuerpo.position.y = yQuieto + salto;
    }
    // la pelvis: hacia la pierna de apoyo, lo que sube o baja el gesto, un poco más baja caminando y el asentamiento
    // al frenar; las piernas alcanzan los pies (y si no llegan, la cadera baja lo justo)
    const wPies = 1 - wAg;
    huesos.cadera.position.set(cadera0.x - 0.02 * pesoEf, cadera0.y + altoCadera - 0.018 * wCaminar
      - 0.012 * Math.sin(Math.PI * Math.min(1, asiento / 0.4)), cadera0.z);
    apoyar(wPies);

    // ── las manos: la forma del gesto (los dedos un poco después que la muñeca), la del gesto anterior mientras este
    // entra, la de hablar o la relajada ──
    const pesoDedos = clip ? pesoBase(clip, tClip - clip.retDedos) : 0;
    const tDedos = clip ? tClip - clip.retDedos : 0;
    for (const l of LADOS) {
      let forma = MANOS.relajada;
      const m = clipManos?.[l];
      if (m && pesoDedos > 0.15) { for (const [tt, f] of m) if (tDedos >= tt) forma = f; }
      else if (desdeManos?.[l] && (m || pesoDedos < 0.5)) forma = desdeManos[l];
      else if (wHabla > 0.3) forma = MANOS.explica;
      else { const n = suave((t - tCasa) / 0.9) > 0.5 ? casaA : casaDe; if (CASAS_MANOS[n]?.[l]) forma = MANOS[CASAS_MANOS[n][l]]; }
      const d = dedos[l], v = vDedos[l];
      for (let i = 0; i < 5; i++) for (let k = 0; k < n; k++) { v[i] += h * (wDedos * wDedos * (forma[i] - d[i]) - 2 * zDedos * wDedos * v[i]); d[i] += v[i] * h; }
      ponerMano(manos[l], d);
    }

    // ── la cara ──
    // parpadear: cierra en 60 ms y abre en 120 ms, cada 2.2–5.6 s (a veces dos veces seguidas)
    proxParpadeo -= dt;
    if (proxParpadeo <= 0 && enParpadeo < 0) parpadear();
    if (enParpadeo >= 0) {
      enParpadeo += dt;
      parpado = enParpadeo < CIERRA_S ? 1 - suave(enParpadeo / CIERRA_S) : suave((enParpadeo - CIERRA_S) / ABRE_S);
      if (enParpadeo >= CIERRA_S + ABRE_S) {
        parpado = 1;
        if (doble) { doble = false; enParpadeo = -0.1; } else enParpadeo = -1;
      }
    } else if (enParpadeo > -0.5) { enParpadeo -= dt; if (enParpadeo <= -0.2) { enParpadeo = 0; parpadeos++; } }
    // la boca: por sílabas mientras habla; la sonrisa de la foto cuando calla (cerrada: los labios juntos)
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
    const labiosLibre = hablando || minAbrir > 0.02 ? 0 : 1;
    const labiosObj = clipCara?.labios !== undefined ? labiosLibre + (clipCara.labios - labiosLibre) * wClip : labiosLibre;
    labios += (labiosObj - labios) * acercar(12, dt);
    cara.boca.poner({ abrir, ancho, sonrisa: Math.max(0, Math.min(1, sonrisa - 0.12 * abrir)), labios: Math.max(0, Math.min(1, labios)) });
    // las cejas: un pico que decae (al empezar a hablar, en un golpe, en un gesto)
    cejasPico *= 1 - acercar(2.2, dt);
    const cejasObj = Math.max(cejasPico, (clipCara?.cejas || 0) * wClip * 0.8);
    cejas += (cejasObj - cejas) * acercar(10, dt);
    const cenoObj = (clipCara?.ceno || 0) * wClip;
    ceno += (cenoObj - ceno) * acercar(8, dt);
    for (const c of cara.cejas) c.poner({ alza: cejas, ceno });
    // los ojos: hacia donde mira, más de lo que giró la cabeza; y cada 0.8–2.5 s un salto chico a otro punto (con
    // movimiento reducido, sin saltos)
    if (!reducido && t >= proxSac) {
      sacX = (azar() * 2 - 1) * 0.15;
      sacY = (azar() * 2 - 1) * 0.08;
      proxSac = t + 0.8 + azar() * 1.7;
      sacadicos++;
    }
    const ojos = clipCara?.ojos && wClip > 0.4 ? clipCara.ojos : null;
    const ox = ojos ? ojos[0] : Math.max(-1, Math.min(1, (yawObj - yawCab.x) * 2.5 + yawObj * 0.4 + yawOjos + sacX));
    const oy = ojos ? ojos[1] : Math.max(-1, Math.min(1, (pitchObj - pitchCab.x) * 2.5 + pitchObj * 0.6 + sacY));
    ojoX += (ox - ojoX) * acercar(60, dt);
    ojoY += (oy - ojoY) * acercar(60, dt);
    const entrecierra = 0.85 - 0.25 * abrir + 0.1 * (sonrisa - 1);
    for (const o of cara.ojos) o.poner({ abierto: parpado, sonrisa: Math.max(0, Math.min(1, entrecierra)), mira: [ojoX, ojoY] });
  }
  /** Pone ya la casa `nombre` (para el taller y las pruebas); la siguiente vuelve a la de siempre */
  function casa(nombre) {
    if (!qCasas[nombre]) return;
    casaDe = casaA;
    casaA = nombre;
    tCasa = t;
    proxCasa = t + 6;
  }
  function parpadear() {
    enParpadeo = 0;
    ultimoParpadeo = t;
    doble = azar() < 0.2;
    proxParpadeo = 2.2 + azar() * 3.4;
    parpadeos++;
  }
  // el peso del reposo ahora: va de `pesoDe` a `pesoA` en 0.8 s, después de 0.1 s hacia el otro lado (el impulso)
  function pesoReposo() {
    const tau = t - tPeso, d = pesoA - pesoDe;
    if (tau >= 0.9) return pesoA;
    if (tau < 0.1) return pesoDe - 0.15 * d * suave(tau / 0.1);
    return pesoDe - 0.15 * d + 1.15 * d * suave((tau - 0.1) / 0.8);
  }

  function ponerMano(m, v) {
    const abre = [-0.14, -0.04, 0.05, 0.14];
    m.dedos.forEach(([b, p], i) => {
      b.rotation.set(abre[i] * (1 - v[i]), 0, -1.5 * v[i]);
      p.rotation.set(0, 0, -1.3 * v[i]);
    });
    m.ponerPulgar(v[4]);
  }

  /** Lo que está haciendo (para el taller y las pruebas). `cara`: hacia dónde mira la cara respecto de la sala (el
   * rumbo del cuerpo más el giro de la cabeza, en radianes; nunca más que la apertura). `peso`: la pierna de apoyo (−1
   * la I … 1 la D); `pies`: cuál está dando un paso; `vivo`: cuántos cambios de peso, saltos de los ojos y parpadeos
   * lleva; `mirada`: qué mira ('sala', 'gesto' o 'punto') */
  const fwd = new THREE.Vector3();
  const r3 = (v) => Math.round(v * 1000) / 1000;
  function estado() {
    return { gesto: nombreClip, sostenido: !!clip?.sostener, hablando, caminando: Math.abs(destinoX - grupo.position.x) > 0.01,
      x: grupo.position.x, visible: grupo.visible, entrando: entrada?.tipo || null,
      rumbo: r3(rumbo), rumboBase: r3(rumboBase), aLaSala: t < salaHasta,
      agachado: r3(Math.max(0, Math.min(1, -cuerpo.position.y / hondo))), hondo,
      peso: r3(pesoEf), casa: casaA, mirada: miraModo, pies: { I: !!pies.I.vuelo, D: !!pies.D.vuelo },
      vivo: { pesos: cambiosPeso, sacadicos, parpadeos },
      get cara() {
        huesos.cabeza.updateWorldMatrix(true, false);
        fwd.set(0, 0, 1).transformDirection(huesos.cabeza.matrixWorld);
        return r3(Math.atan2(fwd.x, fwd.z));
      } };
  }

  /** El rumbo del cuerpo (lo sigue con su muelle en ~0.5 s); `ya`: en el acto (agachado detrás del subtítulo, antes
   * de asomarse; los pies van con él) */
  function girar(r, o = {}) {
    rumboBase = Math.max(-1.2, Math.min(1.2, Number(r) || 0));
    if (o.ya) {
      rumbo = rumboM.x = rumboBase;
      rumboM.v = 0;
      grupo.rotation.y = rumbo;
      for (const l of LADOS) { plantaReposo(l, grupo.position.x, rumbo, pies[l].p); pies[l].yaw = rumbo; pies[l].vuelo = null; }
    }
  }

  return Object.assign(api, { actualizar, gesto, detenerGesto, hablar, callar, mirarA, mirarSala, caminarA, reubicar, entrar,
    salir, agacharse, asomarse, estado, girar, casa });
}

// Un paso del muelle de una articulación (cuaternión `q` con velocidad angular `w`, en el espacio del padre) hacia
// `obj`: w += h·(ω²·e − 2ζω·w), con e el giro de q a obj por el camino corto, y q = exp(w·h)·q
const _qe = new THREE.Quaternion(), _qd = new THREE.Quaternion();
function muelleQ(q, w, obj, om, ze, h) {
  _qe.copy(q).invert().premultiply(obj);
  if (_qe.w < 0) { _qe.x = -_qe.x; _qe.y = -_qe.y; _qe.z = -_qe.z; _qe.w = -_qe.w; }
  const s = Math.hypot(_qe.x, _qe.y, _qe.z);
  const f = s > 1e-9 ? (2 * Math.atan2(s, _qe.w)) / s : 2;
  const k = om * om, c = 2 * ze * om;
  w.x += h * (k * _qe.x * f - c * w.x);
  w.y += h * (k * _qe.y * f - c * w.y);
  w.z += h * (k * _qe.z * f - c * w.z);
  const wl = Math.hypot(w.x, w.y, w.z);
  if (wl * h < 1e-12) return;
  const sa = Math.sin((wl * h) / 2) / wl;
  _qd.set(w.x * sa, w.y * sa, w.z * sa, Math.cos((wl * h) / 2));
  q.premultiply(_qd).normalize();
}
