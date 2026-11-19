// Lo que mueve al presentador (personaje.js): una pose por capas que se recalcula en cada cuadro y que cada
// articulación sigue con su muelle (así salen solos el arrastre del codo y de la muñeca, el sobrepaso y el
// asentamiento, y ningún cambio da un salto).
//
//   1. el reposo vivo: la casa (las manos juntas al frente, que cada tanto cambia), el peso en una pierna, la
//      respiración, la cabeza que nunca está del todo quieta, los ojos que saltan de un punto a otro y el parpadeo;
//   2. caminar paso a paso (el pie que apoya no patina); agacharse y asomarse detrás del subtítulo (entrar, salir,
//      saltar a otro lugar);
//   3. hablar: la boca por las sílabas del texto (los labios se cierran en la p, la b y la m; las pausas, cerrada; nunca
//      grita), la casa de hablar asimétrica (la mano que manda más alta, con una forma que cambia cada tanto), un golpe
//      de esa mano, la cabeza y las cejas en la tónica de las palabras clave, y un asentimiento chico al terminar; con
//      voz, al ritmo que tuvo la voz;
//   4. un gesto (el clip): entra desde lo que hacía el anterior, sin pasar por el reposo, con el cuerpo un poco antes
//      que el brazo y la muñeca un poco después; sale a la casa (la de hablar si sigue hablando). Sostenido, sigue vivo
//      (se mueve apenas, asiente despacio, hace su acento y a los 6–7 s afloja). Cada uno elige una variante distinta
//      de las dos últimas, y con poco tamaño los de dedos se reemplazan por los que se leen por la silueta; en el rótulo
//      (la cara en un círculo), con la cara y la cabeza;
//   5. hacia dónde mira: los ojos saltan, la cabeza los sigue y la columna y la cadera después (hablando, la mirada
//      recorre la sala); la cara (cejas por lado, párpados que se entrecierran, ojos que sonríen, el guiño);
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
  // hablando: la mano de canto (corta) y el índice con el pulgar (precisa); los dedos que «llaman» (invitar)
  canto: [0.08, 0.1, 0.12, 0.15, -0.2],
  ok: [0.62, 0.05, 0.08, 0.12, 0.65],
  llama: [0.35, 0.38, 0.4, 0.42, -0.3],
  // pensar: el índice a medio estirar sobre la mejilla y el pulgar bajo el mentón; las manos que se toman con los dedos
  // entrelazados (escuchar, juntos)
  ele: [0.3, 0.8, 0.8, 0.8, 0.2],
  entrelazada: [0.5, 0.55, 0.6, 0.65, 0.4],
};
export const FORMAS_CONTAR = ['uno', 'dos', 'tres'];
// Lo que se abre cada dedo estirado hacia los costados, en el plano de la palma (rad: índice, medio, anular, meñique;
// doblado, nada). En abanico: con la mano ×1.3 los dedos son gruesos y, más juntos, la mano abierta se leía como una
// manopla y los dedos que cuentan como uno solo
const ABRE = [-0.25, -0.08, 0.09, 0.25];

// ── El habla desde el texto: las sílabas de cada palabra, su tónica y lo que hace la boca en cada una ──
// Lo que tarda en decirse un carácter sin voz (el de presentador.js `decirS`, a unos 17 por segundo)
export const DECIR_S = 0.058;
const VOCALES = 'aeiouáéíóúü';
const ABIERTAS = 'aeoáéó';
const SIN_TILDE = { á: 'a', é: 'e', í: 'i', ó: 'o', ú: 'u', ü: 'u', y: 'i' };
// los pares de consonantes que no se separan (van juntos con la vocal que sigue: «pla», «tra», «che»; «qu» y «gu»
// con la u muda)
const JUNTAS = new Set(['pl', 'pr', 'bl', 'br', 'cl', 'cr', 'dr', 'fl', 'fr', 'gl', 'gr', 'tr', 'kl', 'kr', 'll', 'rr', 'ch', 'qu', 'gu']);
// las palabras que se dicen sin acento (artículos, preposiciones, conjunciones, pronombres átonos)
const ATONAS = new Set(('el la los las lo le les un una unos unas de del al a en con por para sin sobre entre hasta y e o u '
  + 'ni que se me te nos os su sus mi mis tu tus si como cuando donde pero').split(' '));
// tras «aquí» o «esta es», los verbos que todavía no son lo que se muestra
const VERBOS = new Set(['es', 'son', 'está', 'están', 'esta', 'estan', 'vemos', 'ven', 'tenemos', 'tiene', 'hay', 'va', 'van', 'queda', 'quedan']);
// la boca en cada vocal: [abrir, ancho]. La tónica abre 1.3 veces más; nunca más de ABRIR_MAX (más parece gritar)
// (la o y la u, redondas: más angostas, y la sonrisa afloja un poco; con 0.8 no se distinguían de la a)
const VISEMAS = { a: [0.55, 1], e: [0.35, 1.05], i: [0.3, 1.05], o: [0.42, 0.66], u: [0.3, 0.6] };
const ABRIR_MAX = 0.75, ABRIR_GENERADOR = 0.65;
// la sílaba que empieza con los labios (p, b, m y la v, que se dice como b) los cierra el primer 42 %
const BILABIAL = 'pbmv';
// las pausas con la boca cerrada: la coma, el punto, el punto y coma, los dos puntos, los puntos suspensivos
const PAUSA_COMA = 0.16, PAUSA_PUNTO = 0.28, PAUSA_CORTA = 0.12;
// (la u de «que», «qui», «gue», «gui» no suena: es parte de la consonante; la y del final, «hoy», «muy», es vocal)
const esVocal = (w, i) => {
  const c = w[i];
  if (c === 'u' && i > 0 && (w[i - 1] === 'q' || (w[i - 1] === 'g' && 'eéií'.includes(w[i + 1] || '')))) return false;
  return VOCALES.includes(c) || (c === 'y' && i === w.length - 1 && (i === 0 || VOCALES.includes(w[i - 1])));
};
const hiato = (a, b) => (ABIERTAS.includes(a) && ABIERTAS.includes(b)) || 'íú'.includes(a) || 'íú'.includes(b);
const sinTildes = (s) => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

/** Las sílabas de una palabra (en minúsculas): un núcleo por grupo de vocales (dos abiertas seguidas o una cerrada con
 * tilde van en sílabas distintas); entre dos núcleos, una consonante va con la sílaba siguiente, dos se separan (salvo
 * «pl», «tr»…, que van juntas) y de tres o más, las dos últimas si no se separan (si no, la última) */
export function silabear(palabra) {
  const w = String(palabra || '').toLowerCase();
  const nucleos = [];
  for (let i = 0; i < w.length;) {
    if (!esVocal(w, i)) { i++; continue; }
    let j = i + 1;
    while (j < w.length && esVocal(w, j) && !hiato(w[j - 1], w[j])) j++;
    nucleos.push([i, j]);
    i = j;
  }
  if (nucleos.length < 2) return w ? [w] : [];
  const cortes = [0];
  for (let k = 1; k < nucleos.length; k++) {
    const a = nucleos[k - 1][1], b = nucleos[k][0];
    const n = b - a;
    cortes.push(n === 0 ? b : n === 1 ? a : JUNTAS.has(w.slice(b - 2, b)) ? b - 2 : b - 1);
  }
  return cortes.map((c, k) => w.slice(c, cortes[k + 1] ?? w.length));
}
/** Cuál de las sílabas lleva el acento: la de la tilde; si no hay, la penúltima si la palabra termina en vocal, n o s,
 * y la última si no. −1: una palabra que se dice sin acento */
export function tonicaDe(silabas, palabra) {
  const p = String(palabra || '').toLowerCase();
  if (ATONAS.has(p)) return -1;
  const k = silabas.findIndex((s) => /[áéíóú]/.test(s));
  if (k >= 0) return k;
  if (silabas.length < 2) return silabas.length - 1;
  return /[aeiouns]$/.test(p) ? silabas.length - 2 : silabas.length - 1;
}
// la vocal que manda en una sílaba: la abierta (a, e, o), si no la última
const vocalDe = (s) => {
  const v = [...s].filter((c, i) => esVocal(s, i));
  const f = v.find((c) => ABIERTAS.includes(c)) || v[v.length - 1] || 'e';
  return SIN_TILDE[f] || f;
};
/**
 * El plan de decir `texto`: las sílabas (y las pausas) con su tiempo, lo que hace la boca en cada una y los golpes del
 * habla. Puro (se prueba con Node). Cada carácter dura DECIR_S, repartido entre las sílabas de cada palabra; las pausas
 * (coma 0.16 s, punto 0.28 s) van con la boca cerrada. `dura`: lo que tiene que durar (sin voz: lo de `decirS`); las
 * sílabas se estiran o se encogen para que entre (las pausas quedan). `claves`: palabras que son lo resaltado.
 * → {segs: [{i, d, pausa?, a, w, B, C, tonica, vocal, palabra}], eventos: [{i, tipo: 'golpe'|'cejas', amp}], dur,
 *    pregunta, clave (s: la tónica de la palabra clave, o null), primera (s: la primera tónica)}
 * Las palabras clave (un golpe de la mano, con al menos 0.5 s entre uno y otro): las cifras, las de 8 letras o más, los
 * nombres (con mayúscula a mitad de la oración, o siglas), la que sigue a «esta es / este es / aquí» y las de `claves`.
 * `clave`: la tónica de la primera cifra, de la que sigue a «esta es», o de lo resaltado; si no hay, la primera palabra
 * clave (si cae en los primeros 2.2 s); si no, la primera tónica después de 0.25 s.
 */
export function planHabla(texto, { claves = [], dura = null } = {}) {
  const segs = [], eventos = [];
  const conClave = new Set((Array.isArray(claves) ? claves : [claves]).map(sinTildes).filter(Boolean));
  let i = 0, inicio = true, primeraT = null, ultimoGolpe = -9, fuerte = null, debil = null, libre = null;
  const previas = [];
  const pausa = (d) => {
    if (!segs.length) return;
    const u = segs[segs.length - 1];
    if (u.pausa) { const extra = Math.max(0, d - u.d); u.d += extra; i += extra; return; }
    segs.push({ i, d, pausa: true });
    i += d;
  };
  const RE = /(\p{N}+(?:[.,]\p{N}+)*)|(\p{L}+)|([,;:.…!?()—–]+)/gu;
  for (const m of String(texto || '').matchAll(RE)) {
    if (m[3]) {
      const p = m[3];
      pausa(/[.;:…!?]/.test(p) ? PAUSA_PUNTO : p.includes(',') ? PAUSA_COMA : PAUSA_CORTA);
      if (/[.:…!?]/.test(p)) inicio = true;
      continue;
    }
    const cifra = !!m[1], palabra = m[1] || m[2], baja = palabra.toLowerCase();
    // una cifra se dice con más sílabas que dígitos («dos mil veintisiete»): unas 1.4 por dígito
    const sil = cifra
      ? Array.from({ length: lim(Math.round(palabra.replace(/\D/g, '').length * 1.4), 2, 7) }, (_, k) => `d${'eoaei'[k % 5]}`)
      : silabear(baja);
    if (!sil.length) continue;
    const ton = cifra ? sil.length - 2 : tonicaDe(sil, baja);
    const nombre = !cifra && ((!inicio && /^\p{Lu}/u.test(palabra)) || /^\p{Lu}{2,}$/u.test(palabra));
    const tras = previas.length >= 1 && (['aqui', 'aca'].includes(sinTildes(previas[previas.length - 1]))
      || (previas.length >= 2 && ['es', 'son'].includes(previas[previas.length - 1])
        && ['esta', 'este', 'esto', 'estos', 'estas'].includes(sinTildes(previas[previas.length - 2]))));
    const presenta = tras && !VERBOS.has(baja) && !ATONAS.has(baja);
    const resaltado = conClave.has(sinTildes(palabra));
    const esClave = ton >= 0 && (cifra || [...baja].length >= 8 || nombre || presenta || resaltado);
    // (tras «aquí» o «esta es» la que se muestra puede venir después de un verbo o un artículo: se sigue buscando)
    if (!(tras && (VERBOS.has(baja) || ATONAS.has(baja)))) previas.push(baja);
    const largo = [...palabra].length + 1;
    const letras = sil.reduce((s, x) => s + [...x].length, 0) || 1;
    sil.forEach((s, k) => {
      const d = (largo * DECIR_S * [...s].length) / letras;
      const vocal = vocalDe(s);
      const B = BILABIAL.includes(s[0]), C = !esVocal(s, 0);
      const tonica = k === ton;
      const [a0, w] = VISEMAS[vocal] || VISEMAS.e;
      segs.push({ i, d, a: Math.min(ABRIR_MAX, a0 * (tonica ? 1.3 : 1)), w, B, C, tonica, vocal, palabra: k === 0 ? palabra : null });
      if (tonica) {
        // el golpe cae cuando suena la vocal (después de los labios cerrados o de la consonante)
        const tv = i + (B ? 0.45 : C ? 0.25 : 0.05) * d;
        if (primeraT === null) { primeraT = tv; eventos.push({ i: Math.max(0, tv - 0.05), tipo: 'cejas', amp: 0.5 }); }
        else if (cifra) eventos.push({ i: Math.max(0, tv - 0.05), tipo: 'cejas', amp: 0.5 });
        if (esClave && tv - ultimoGolpe >= 0.5) {
          ultimoGolpe = tv;
          eventos.push({ i: Math.max(0, tv - 0.12), tipo: 'golpe', amp: cifra || presenta || resaltado ? 1 : 0.8 });
        }
        if ((cifra || presenta || resaltado) && fuerte === null) fuerte = tv;
        if (esClave && debil === null) debil = tv;
        if (libre === null && tv >= 0.25) libre = tv;
      }
      i += d;
    });
    inicio = false;
  }
  // la pausa del final no es parte de lo que dice
  if (segs.length && segs[segs.length - 1].pausa) { i -= segs[segs.length - 1].d; segs.pop(); }
  // que dure lo pedido: las sílabas se estiran o se encogen (las pausas quedan)
  if (Number.isFinite(dura) && dura > 0 && i > 0) {
    const P = segs.reduce((s, x) => s + (x.pausa ? x.d : 0), 0), S = i - P;
    const k = S > 0 ? lim((dura - P) / S, 0.6, 1.6) : 1;
    if (Math.abs(k - 1) > 1e-3) {
      const mapa = (x) => { let acum = 0, prev = 0; for (const s of segs) { if (x <= s.i + 1e-9) break; const dd = s.pausa ? s.d : s.d * k; const u = Math.min(1, (x - s.i) / s.d); acum = prev + dd * u; prev += dd; } return acum; };
      const nuevos = eventos.map((e) => ({ ...e, i: mapa(e.i) }));
      const tt = [fuerte, debil, libre, primeraT].map((x) => (x === null ? null : mapa(x)));
      let j = 0;
      for (const s of segs) { s.i = j; if (!s.pausa) s.d *= k; j += s.d; }
      i = j;
      eventos.splice(0, eventos.length, ...nuevos);
      [fuerte, debil, libre, primeraT] = tt;
    }
  }
  eventos.sort((a, b) => a.i - b.i);
  return { segs, eventos, dur: i, pregunta: /[¿?]/.test(String(texto || '')),
    clave: fuerte ?? (debil !== null && debil <= 2.2 ? debil : null) ?? libre ?? primeraT, primera: primeraT };
}

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
// Con el plano medio (cerca, el busto del celular) el corte va más arriba: las manos de la casa suben un poco (el
// hombro y el codo algo más doblados: las palmas a ~1.1, la punta de los dedos 0.05 del alto sobre el corte) para no
// quedar cortadas por el atril (asomaban los pulgares y el dorso, dos muñones). No más: con los antebrazos más parados,
// las manos juntas al frente se leían como brazos cruzados. Los brazos sueltos no suben
const ALZAR_MEDIO = { hombro: -0.09, codo: -0.12 };
const casaMedio = (c) => Object.fromEntries(Object.entries(c).map(([j, e]) => [j, e.map((x, i) => (i ? x : x + (ALZAR_MEDIO[j.slice(0, -1)] || 0)))]));
// La casa de hablar (sin un gesto, lo que el gesto no usa): asimétrica, la mano que manda más alta y adelante (la
// derecha, salvo que el gesto la ocupe: habla con la otra) y la otra más baja, acompañando. `chica`: lo que sube cada
// una con el busto (el plano medio corta más arriba: las manos tienen que quedar a la vista)
const HABLA = {
  alta: { hombro: [-0.5, 0, 0.34], codo: [-1.4, 1.1, 0], muneca: [0.1, 0, 0] },
  baja: { hombro: [-0.3, 0, 0.24], codo: [-1.22, 0.9, 0], muneca: [0.14, 0, 0] },
  medio: { hombro: -0.22, codo: -0.25 },
};
// La forma de la mano que manda (cambia cada 3–4 golpes): la palma arriba (ofrece), de canto (corta) y el índice con el
// pulgar (precisa); `giro`: el del antebrazo (codo y) que la pone así
const FORMAS_HABLA = [{ mano: 'explica', giro: 1.35 }, { mano: 'canto', giro: 0.6 }, { mano: 'ok', giro: 0.95 }];

const otro = (lado) => (lado === 'I' ? 'D' : 'I');
const brazo = (lado, hombro, codo, muneca = [0, 0, 0]) => ({ [`hombro${lado}`]: hombro, [`codo${lado}`]: codo, [`muneca${lado}`]: muneca });
const dos = (hombro, codo, muneca) => ({ ...brazo('I', hombro, codo, muneca), ...brazo('D', hombro, codo, muneca) });
// Una forma de mano entre otras dos (los dedos que «llaman» despacio, de a poco)
const entreManos = (a, b, u) => MANOS[a].map((x, i) => x + (MANOS[b][i] - x) * u);
// Algunas poses que se repiten
const P = {
  palmasArriba: [[-0.45, 0, 0.34], [-1.22, 1.35, 0], [0.18, 0, 0]],      // las manos adelante, las palmas arriba
  ladoAbierto: [[-0.55, 0, 0.78], [-0.6, 1.45, 0], [-0.15, 0, 0]],        // un brazo afuera, la palma arriba
  dedoArriba: [[-0.6, 0, 0.3], [-2.2, -1.5, 0], [0, 0, 0.08]],            // el antebrazo arriba, la palma a la sala
  enJarra: [[0.15, -1.57, 0.75], [-1.6, 0, 0], [0, 0, 0.2]],              // la mano en la cintura
};
// Las poses de los gestos de mostrar y de explicar, [hombro, codo, muñeca] de un brazo (el otro, los mismos números):
// buscadas con el personaje para que las manos queden donde dice cada una, sin entrar en el cuerpo, y arriba del corte
// del americano (0.85)
const POSE = {
  // saludar: la mano abierta al costado de la cabeza (la palma a 1.9, la punta de los dedos a 2.07), la palma a la
  // sala; el antebrazo tiene lugar para ir y venir. De cerca, a la altura de la cara
  saludoAlto: [[0.42, 1.79, 2.43], [-0.6, 0, 0], [0.02, 0, 0.29]],
  saludoCara: [[0.76, 1.9, 2.39], [-0.9, 0, 0], [0.25, 0, 0.45]],
  // señalar: preparando, la mano frente al pecho; presentar: sale del centro del pecho
  senalaPrepara: [[-0.5, 0, 0.15], [-1.2, 0, 0], [0.4, 0, 0]],
  presentaCentro: [[-0.5, 0, 0.1], [-1.5, 1.4, 0], [0, 0, 0]],
  // destacar: el índice arriba y adelante (0.44 delante del hombro, a la altura de la boca), la palma a la sala; o la
  // mano de canto que corta; antes, la mano baja y va atrás
  destacaIndice: [[-0.8, 0, 0.2], [-1.9, -1.4, 0], [-0.15, 0, 0]],
  destacaCanto: [[-0.95, 0, 0.28], [-1.55, 0.45, 0], [0.1, 0, 0]],
  destacaAtras: [[0, 0, 0.12], [-1.38, 0.3, 0], [0.45, 0, 0]],
  // comparar: las dos manos al centro con las palmas enfrentadas (a 1.22); «hoy», la izquierda afuera y abajo (1.08) con
  // la palma abajo y adentro; «con el proyecto», la derecha al otro lado y más alta (1.33) con la palma arriba
  comparaCentroI: [[-0.45, -0.34, -0.25], [-1.34, -0.45, 0], [-0.6, 0, 0.45]],
  comparaCentroD: [[-0.45, -0.46, -0.27], [-1.49, -0.19, 0], [0.14, 0, 0.45]],
  comparaHoy: [[-0.36, 0, 0.3], [-1.24, -1.01, 0], [0.31, 0, -0.05]],
  comparaProyecto: [[-0.81, 0.07, 0.5], [-1.32, 1.6, 0], [-0.03, 0, 0.45]],
  // enumerar: la izquierda frente al pecho y arriba (la palma a 1.44, los dedos hasta 1.6), la palma a la sala y los dedos
  // arriba; la derecha la acompaña más abajo y a su lado (la palma arriba hacia ella, a 1.18), sin tocarla: el índice que
  // tocaba la base de la palma quedaba sobre el reloj («se acabó el tiempo») y tapaba los dedos que cuentan
  cuentaI: [[-0.8, 0.04, -0.2], [-1.76, -1.4, 0], [0.01, 0, 0.45]],
  cuentaAcompana: [[-0.41, -0.31, 0], [-1.63, 1.21, 0], [0.14, 0, 0.49]],
  // crecer: las dos manos adelante, bajas (las palmas a 1.04), con las palmas arriba; la que sube termina por delante
  // del hombro con el codo doblado (85°: el antebrazo casi vertical), la muñeca a la altura del hombro (+0.07) y la
  // palma arriba (a 1.46): «sube», sin el brazo estirado en alto (se leería como un saludo de brazo en alto)
  creceBase: [[-0.26, -0.09, 0.23], [-1.27, 1.61, 0], [0.15, 0, 0.01]],
  creceArriba: [[-1.06, -0.01, 0.31], [-1.48, 1.55, 0], [0.01, 0, 0.55]],
  // grande: las manos juntas frente al pecho (1.3), las palmas enfrentadas; abiertas, adelante y afuera, a 1.1 (unos
  // 25° bajo la horizontal), las palmas adentro y adelante
  grandeJuntaI: [[-0.59, -0.47, -0.24], [-1.51, -0.31, 0], [0.1, 0, 0.15]],
  grandeJuntaD: [[-0.58, -0.43, -0.36], [-1.43, -0.43, 0], [0.1, 0, 0.15]],
  grandeAbierta: [[-0.56, -0.09, 0.8], [-0.58, 0.79, 0], [-0.4, 0, 0.29]],
  // detalle: la mano en «ok» al costado del mentón (1.5, sin tapar la boca) y delante (0.43), la palma a la sala y un
  // poco hacia adentro (el aro del índice y el pulgar se ve al costado de los otros tres dedos)
  detalle: [[-1.08, 0.21, -0.15], [-1.52, -0.77, 0], [-0.22, 0, 0.32]],
  // construir: la palma izquierda arriba frente al ombligo (1.1); el puño derecho apoyado en ella y levantado
  construyePalma: [[-0.29, -0.4, -0.25], [-1.32, 1.45, 0], [0.01, 0, 0.08]],
  construyePuno: [[-0.5, -0.47, -0.57], [-1.02, -0.27, 0], [0.09, 0, 0.45]],
  // ── los de reaccionar, el lema, el cierre y la pausa (etapa 7b) ──
  // pensar: la palma hacia la cara, a 5 cm de la barbilla (el pulgar bajo el mentón, el índice a medio estirar sobre la
  // mejilla); el otro brazo cruzado por delante del vientre, la palma arriba bajo el codo (lo sostiene): el codo afuera
  // del costado y adelante (0.3 del centro, 0.18 delante), así el antebrazo pasa por fuera de la polo (con el codo junto
  // al cuerpo, el brazo entero quedaba dentro del torso y la piel asomaba por la polo)
  pensarD: [[-1.1, -0.33, -0.61], [-1.47, 0.59, 0], [-0.43, 0, -0.15]],
  pensarI: [[-0.62, -1.33, 0.08], [-1.68, 1.68, 0], [-0.04, 0, 0.14]],
  // preguntar: la mano abierta adelante, hacia la cámara (0.66 delante del hombro, a la altura del pecho: 1.33), la palma
  // arriba y los dedos hacia la sala (y un poco afuera: de frente se lee por la silueta)
  pregunta: [[-1.52, 0.63, -0.13], [-0.24, 0.68, 0], [-0.1, 0, 0.3]],
  // calmar: las manos delante del vientre (1.09), al ancho de los hombros, las palmas abajo y un poco hacia la sala
  calma: [[-0.29, -0.32, 0.19], [-1.36, -1.61, 0], [0.03, 0, 0.45]],
  // aprobar: el puño de canto con el pulgar arriba, a la altura del pecho (1.25) y hacia la sala
  aprueba: [[-0.62, -0.29, 0.25], [-1.66, 0.61, 0], [0.6, 0, 0.45]],
  // celebrar: los puños al pecho (antes de saltar) y arriba, por delante y abiertos en V (a 1.9, sobre los hombros)
  punosPecho: [[-0.24, -0.2, -0.6], [-1.78, -1.23, 0], [0.13, 0, 0.45]],
  punosArriba: [[-2.7, 0, 0.5], [-0.5, 0, 0], [0, 0, 0]],
  // aplaudir: las palmas enfrentadas frente al pecho (1.25), la izquierda un poco más alta y girada; a 0.18 una de la
  // otra (el golpe las junta)
  aplaudeD: [[-0.46, -0.42, -0.35], [-1.48, -0.35, 0], [0.18, 0, 0.45]],
  aplaudeI: [[-0.53, -0.44, -0.26], [-1.53, -0.4, 0], [-0.01, 0, 0.45]],
  // juntos: las dos palmas arriba hacia la sala (a 1.17, abiertas); después entrelazadas frente al pecho (1.31), un
  // palmo delante de la polo (las palmas a 0.085 una de la otra: al llegar, el muelle las junta un poco más)
  juntosAbre: [[-0.77, -0.05, 0.17], [-1.04, 1.6, 0], [-0.1, 0, 0.45]],
  juntasD: [[-0.53, -0.52, -0.48], [-1.58, -0.32, 0], [0.45, 0, 0.43]],
  juntasI: [[-0.55, -0.57, -0.32], [-1.68, -0.19, 0], [0.48, 0, 0.45]],
  // corazón: la mano derecha plana sobre el pectoral izquierdo (la palma a 3 cm de la polo), los dedos hacia el hombro
  corazon: [[-0.36, -1.1, -0.32], [-1.66, 0.32, 0], [0.06, 0, -0.33]],
  // invitar: los brazos bajos y adelante, las palmas arriba hacia la sala (a 1.12, delante: no en T)
  invita: [[-0.48, 0.09, 0.39], [-1.14, 1.6, 0], [-0.05, 0, 0.45]],
  // negar: el índice arriba frente al pecho (1.38), la palma a la sala; o la mano plana, la palma abajo, adentro (frente
  // al ombligo) y afuera (a 0.36 del centro: no más que la huella del cuerpo, que el panel no se tape)
  niegaIndice: [[-0.78, -0.5, -0.14], [-1.52, -1.6, 0], [0.6, 0, 0.45]],
  cortaAdentro: [[-0.53, -0.62, -0.28], [-1.19, -1.6, 0], [0.24, 0, -0.1]],
  cortaAfuera: [[-0.41, -0.13, 0.16], [-1.4, -1.42, 0], [0.57, 0, -0.09]],
  // escuchar: las manos entrelazadas al frente, a la altura de la cintura (las palmas a 0.99, 0.078 una de la otra)
  escuchaD: [[-0.1, -0.57, -0.28], [-1.24, 0.4, 0], [0.51, 0, 0.45]],
  escuchaI: [[-0.04, -0.49, -0.27], [-1.37, 0.35, 0], [0.6, 0, 0.45]],
};
// el puño de construir, levantado: lo que suben el hombro y el codo desde apoyado (cada golpe los devuelve)
const MARTILLO = { hombro: -0.32, codo: -0.5, muneca: -0.3 };
// un brazo con otra x del hombro y del codo
const alzar = ([h, c, m], dh, dc, dm = 0) => [[h[0] + dh, h[1], h[2]], [c[0] + dc, c[1], c[2]], [m[0] + dm, m[1], m[2]]];
// un brazo más arriba para el plano medio (invitar, escuchar, calmar: el gesto se ve entero sobre el corte, a la altura
// del pecho; ~0.15 más arriba)
const alzarMedio = (b) => alzar(b, -0.18, -0.22);
// la mezcla de dos poses de un brazo (los ángulos, en línea recta: para pasos intermedios cercanos)
const entre = (a, b, u) => a.map((e, i) => e.map((x, k) => x + (b[i][k] - x) * u));

/**
 * Los gestos: cada uno arma su clip con las opciones del momento. Un clip es
 * {dur, pose | claves, manos, cara?, entra?, sale?, curva?, sostener?, mirar?, mirada?, resto?, retraso?, cuerpo?,
 *  golpes?, golpesCallado?, batuta?, vaiven?, osc?, salto?, acento?, relajada?, alSeguir?, poseApunta?, manoApunta?,
 *  parpadeos?, deriva?, alSoltar?, cambiaMirada?}:
 * - `pose` (o `claves`: [[t, pose, curva?], …], que se encadenan) son las articulaciones que toma; las demás siguen con
 *   las otras capas. `curva` es cómo se llega a esa clave desde la anterior (a la primera, desde lo que hacía antes):
 *   'suave' (la de omisión), 'anticipa' (retrocede un poco y después va), 'golpe' (llega rápido), 'sosten' (llega
 *   despacio) o 'lineal'.
 * - `manos`: {I, D} con el nombre de una forma de MANOS (o [[t, forma], …] para cambiarla en el tiempo; una forma puede
 *   ser también los cinco números: `entreManos`, los dedos que llaman despacio).
 * - `cara`: {cejas, ceno, sonrisa, abrir, ojos, labios, cejasI, cejasD, entrecierra, guino, duchenne}: lo que hace
 *   la cara mientras dura (`labios` 1: la sonrisa cerrada; 0: con los dientes; `cejasI`/`cejasD`: cada ceja por su lado;
 *   `entrecierra` 0..1; `guino`: 'I' | 'D' | {lado, t}, un ojo se cierra 0.25 s (a los 0.35 s); `duchenne`: los ojos
 *   sonríen con la boca; por omisión, cuando sonríe con los dientes; `ancho`: lo ancho de la boca callado; `cierra`:
 *   los ojos que se cierran, 0..1: de sonrisa al celebrar, al apoyar la mano en el pecho). Cada valor
 *   puede ser una línea en el tiempo del clip, [[t, valor], …] (de una clave a la otra, suave).
 * - `curva`: la de la entrada de un gesto con `pose` (con `claves`, la de la primera).
 * - `entra` / `sale`: lo que tarda en tomar la pose y en soltarla (0.4 / 0.45 por omisión); `sostener`: se queda
 *   hasta otro gesto.
 * - `retraso`: {articulación o familia: segundos} sobre los de RETRASO (el cuerpo antes, la muñeca y los dedos
 *   después).
 * - `cuerpo`: {columna, pecho, cadera: [x, y, z], peso: −1 … 1 (la pierna I … la D), alto: dy}: lo que el cuerpo
 *   acompaña, sumado al reposo (cada uno, fijo o una línea [[t, valor], …]). Lo que gira el torso no se lleva la cara: la
 *   mirada lo descuenta.
 * - `golpes`: [{t, art, eje, amp, ida, sosten, vuelta}]: un impulso (llega en `ida`, cada vez más rápido, se queda
 *   `sosten` y vuelve en `vuelta`); `golpesCallado`: solo cuando no habla (hablando, el habla pone los suyos); `batuta`:
 *   'I' | 'D' | true, el brazo con el que el habla puede golpear aunque el gesto lo ocupe (explicar).
 * - `vaiven`: [{art, eje, amp, frec, desde, hasta, decae, azar, cadena}]: ciclos que decrecen (`decae` por ciclo, 0.7)
 *   con la frecuencia algo irregular (±`azar`, 0.1); `cadena`: la amplitud de la articulación siguiente (hombro →
 *   codo → muñeca, columna → pecho → cuello → cabeza), que va 85 ms atrás (o {art, amp, retraso}).
 * - `osc`: [[articulación, eje, amplitud, frecuencia, desde, hasta]]: el vaivén parejo de antes (solo por
 *   compatibilidad: los gestos nuevos usan `vaiven`).
 * - `mirar`: un punto (Vector3, del mundo); `mirada`: cómo lo mira: 'objetivo' (todo el gesto), 'sala', 'sigue' (el
 *   punto, con un vistazo a la sala cada 3 s) o {objetivo: s, cada: [a, b], dura} (el punto `s` segundos y después la
 *   sala, con otro vistazo cada a–b s) o 'recorre' (salta entre puntos de la obra, asiente a la mitad y a los 1.2 s
 *   vuelve a la sala 1.1 s, en ciclo); por omisión, {objetivo: 0.8}. `resto`: mirando a la sala, la cara se queda hasta esos
 *   radianes hacia el punto. `salto`: un saltito (true, o {t, dur, alto}: cuándo despega, lo que dura en el aire y lo
 *   que sube; celebrar). `parpadeos`: [t, …] los parpadeos del gesto (la espera de la pregunta, el primer asentimiento).
 * - `deriva`: {amp, cada: [a, b]}: aunque no hable, la mirada recorre la sala (invitar, sostenido: cada a–b s, de un lado
 *   al otro). `cambiaMirada`: con cada `seguir`, la mirada cambia de lado de la sala (contar).
 * - `alSoltar`: (o) → un clip corto que hace al soltarlo con detenerGesto() (con el mismo nombre: el «¡ya está!» de
 *   pensar, la inspiración de escuchar antes de volver a hablar).
 * - Sostenido: `acento` {cada: [a, b], golpes: [{t, art, eje, amp, ida, vuelta}], manos: {I, D: [[t, forma], …]}} lo
 *   que hace cada a–b s para seguir vivo (y con `acentuar()`); `relajada`: la pose a la que afloja a los 6–7 s (si no
 *   la trae, los brazos que no apuntan bajan un poco). `alSeguir`: los golpes del mismo gesto que sigue (enumerar: el
 *   número nuevo).
 * - `poseApunta` / `manoApunta`: el brazo y la mano con los que apunta (si cambian en las claves): con ellos se calcula
 *   el hombro que deja la recta a la punta del índice en el punto; las claves (o la pose) que llevan ese ángulo vuelven a
 *   apuntar en cada cuadro.
 * `o.lado` elige el brazo cuando el gesto es de uno solo; `o.reducido`, si es con movimiento reducido (celebrar no se agacha
 * ni salta); `o.saliendo` (despedirse), se superpone a la salida, que pone el «gracias»; `o.punto` es hacia dónde (señalar, presentar, indicar, mirar la
 * maqueta) y `o.hasta`, otro punto (presentar barre de uno al otro: `o.apuntaHasta`); `o.abajo` / `o.arriba` (0..1), cuánto
 * más abajo o más arriba que el hombro está el punto; `o.n`, cuántos dedos (contar, enumerar); `o.variante`, cuál de sus
 * variantes (VARIANTES); `o.plano`, lo que se ve de él; `o.azar`, el azar del animador; `o.dato` (mostrar_panel):
 * «fíjense en este dato».
 */
export const GESTOS = {
  // ── Empezar y terminar ──
  // la bienvenida: el brazo sube en arco por delante (antes, un amague hacia abajo, y las cejas ya suben) hasta la mano
  // al costado de la cabeza, y el antebrazo va y viene tres veces, cada vez menos (la muñeca un poco después, los dedos
  // que se abren en cada ida); «¡Hola!» con la boca en la primera, la sonrisa amplia con los ojos, la cabeza ladeada
  // hacia la mano y un asentimiento. El pecho gira un poco hacia la mano y el peso va a la otra pierna. Corto (1.2 s:
  // la primera escena ya trae un dato), una sola ida y vuelta. (variantes: la mano alta; a la altura de la cara)
  saludar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.6, s = l === 'D' ? 1 : -1;
    // (de cerca, el plano medio: a la altura de la cara)
    const arriba = brazo(l, ...(o.variante === 1 || o.plano === 'medio' ? POSE.saludoCara : POSE.saludoAlto));
    const llega = Math.min(0.5, d * 0.32);
    // tres vaivenes a 2.2 Hz (si hay tiempo), y baja
    const fin = Math.max(llega + 0.35, Math.min(d - 0.4, llega + 0.05 + 3 / 2.2));
    // (la mano se abre antes de subir, los dedos un poco antes que el brazo: si sube cerrada, se lee un puño en alto)
    const dedos = [[0, 'abierta']];
    // (en cada ida los dedos se aflojan apenas: a medio camino de la palma que explica, nunca un puño)
    const afloja = entreManos('abierta', 'explica', 0.5);
    for (let k = llega + 0.1; k < fin - 0.1; k += 1 / 2.2) dedos.push([k, afloja], [k + 0.2, 'abierta']);
    return { dur: d, entra: Math.min(0.45, llega), sale: 0.38, retraso: { dedos: -0.12, dedosSale: 0.3 },
      claves: [[llega, { ...arriba, cabeza: [0.02, 0, 0.12 * s] }, 'anticipa']],
      manos: { [l]: dedos },
      cuerpo: { pecho: [0, -0.08 * s, 0], peso: -0.7 * s },
      vaiven: [{ art: `codo${l}`, eje: 0, amp: 0.35, frec: 2.2, desde: llega, hasta: fin, decae: 0.76, azar: 0.06,
        cadena: { art: `muneca${l}`, amp: 0.25, retraso: 0.1 } }],
      golpes: [{ t: llega + 0.05, art: 'cabeza', eje: 0, amp: 0.06, ida: 0.14, vuelta: 0.3 }, { t: llega + 0.05, art: 'cuello', eje: 0, amp: 0.025, ida: 0.14, vuelta: 0.3 }],
      cara: { cejas: [[0, 0.5], [llega, 0.8], [llega + 0.8, 0.5]], abrir: [[llega - 0.1, 0], [llega + 0.05, 0.35], [llega + 0.3, 0.12], [llega + 0.5, 0]],
        sonrisa: 1, duchenne: true } };
  },
  // gracias y hasta pronto: la mano sube enseguida al costado de la cabeza (sin el amague del saludo) y va y viene dos
  // veces mientras la cabeza asiente su «gracias»; la sonrisa con los ojos. Corta: se superpone a la salida (la mano
  // sigue saludando mientras él se agacha detrás del subtítulo, con la cara a la sala hasta el final; `saliendo`: el
  // «gracias» lo pone la salida)
  despedirse: (o) => {
    const l = o.lado || 'D', d = o.dur || 1.5, s = l === 'D' ? 1 : -1;
    const arriba = brazo(l, ...(o.plano === 'medio' ? POSE.saludoCara : POSE.saludoAlto));
    const llega = Math.min(0.32, d * 0.25), fin = Math.max(llega + 0.35, d - 0.3);
    // dos idas y vueltas (o las que entren, a no más de 2.6 por segundo)
    const frec = lim(2 / (fin - llega), 2.2, 2.6);
    // (la mano ya abierta al subir: en la salida, lo que se ve antes de agacharse es la mano que saluda, no un puño)
    const dedos = [[0, 'abierta']];
    const afloja = entreManos('abierta', 'explica', 0.5);
    for (let k = llega + 0.08; k < fin - 0.1; k += 1 / frec) dedos.push([k, afloja], [k + 0.18, 'abierta']);
    return { dur: d, entra: Math.min(0.3, llega), sale: 0.3, curva: 'sosten', retraso: { dedos: -0.12, dedosSale: 0.3 },
      claves: [[llega, { ...arriba, cabeza: [0.02, 0, 0.08 * s] }, 'sosten']],
      manos: { [l]: dedos },
      cuerpo: { pecho: [0, -0.06 * s, 0], peso: -0.5 * s },
      vaiven: [{ art: `codo${l}`, eje: 0, amp: 0.3, frec, desde: llega, hasta: fin, decae: 0.8, azar: 0.05,
        cadena: { art: `muneca${l}`, amp: 0.22, retraso: 0.1 } }],
      golpes: o.saliendo ? [] : [{ t: 0.08, art: 'cabeza', eje: 0, amp: 0.07, ida: 0.15, vuelta: 0.35 }, { t: 0.08, art: 'cuello', eje: 0, amp: 0.03, ida: 0.15, vuelta: 0.35 }],
      cara: { cejas: [[0, 0.4], [llega, 0.7], [d - 0.3, 0.5]], sonrisa: 1, labios: 0, duchenne: true } };
  },
  // bienvenida o «¿preguntas?»: los brazos bajos y adelante, las palmas arriba hacia la sala (las manos a la altura de la
  // cintura y delante, nunca en T), el pecho abierto y el peso adelante, la cabeza ladeada y un asentimiento. Sostenido:
  // los dedos «llaman» despacio (cada 1.6 s), respira y la mirada recorre la sala
  invitar: (o) => {
    const d = o.dur || 3.0, sost = o.sostener === true;
    // (de cerca, el plano medio: las palmas a la altura del pecho, 0.15 más arriba, para que no queden en el corte)
    const pose = o.plano === 'medio' ? alzarMedio(POSE.invita) : POSE.invita;
    // (los dedos que llaman: de abiertos a un poco cerrados y de vuelta, despacio, mientras dure)
    const llamar = [[0, 'explica'], [0.4, 'abierta']];
    if (sost) for (let t = 1.6; t < 40; t += 1.6) for (let k = 1; k <= 4; k++) llamar.push([t + k * 0.2, entreManos('abierta', 'llama', k / 4)], [t + 0.8 + k * 0.2, entreManos('llama', 'abierta', k / 4)]);
    return { dur: d, sostener: sost, entra: 0.55, curva: 'sosten', sale: 0.5,
      claves: [[0.55, { ...dos(...pose), cabeza: [-0.02, 0, 0.08] }, 'sosten']],
      manos: { I: llamar, D: llamar },
      cuerpo: { columna: [0.04, 0, 0], pecho: [-0.05, 0, 0] },
      golpes: [{ t: 0.6, art: 'cabeza', eje: 0, amp: 0.06, ida: 0.15, vuelta: 0.35 }, { t: 0.6, art: 'cuello', eje: 0, amp: 0.025, ida: 0.15, vuelta: 0.35 }],
      deriva: sost ? { amp: 0.15, cada: [1.8, 2.4] } : null,
      cara: { cejas: [[0.2, 0.85], [1.4, 0.6]], abrir: [[0.3, 0], [0.5, 0.12], [0.9, 0]], sonrisa: 1, duchenne: true },
      relajada: dos(...alzar(pose, 0.1, -0.08)) };
  },
  // ── Mostrar ──
  // «esta es…»: mira lo resaltado y prepara (la mano frente al pecho), y en el golpe estira el brazo (nunca del todo)
  // hasta que la recta del hombro a la punta del índice cae en lo que señala; pasa un poco y asienta. A los 0.8 s la
  // cabeza vuelve a la sala sin bajar el brazo (y queda un poco hacia lo señalado). El torso abierto hacia ahí y el peso
  // en ese pie; hacia abajo (una cifra baja del panel), el codo más doblado y la columna adelante. Las cejas en el golpe
  // y la boca de «¡esta!». Sostenido, dos toques del índice cada tanto. `dato` (mostrar_panel): las cejas más arriba, la
  // boca de «fíjense» y dos toques en el golpe
  senalar: (o) => {
    const l = o.lado || 'D', s = l === 'D' ? 1 : -1, d = o.dur || 2.8;
    const ap = o.apunta || [-1.2, 0, 0.5];
    const abajo = o.abajo || 0;
    const final = brazo(l, ap, [-0.3 - 0.25 * abajo, 0, 0], [0.02 - 0.2 * abajo, 0, 0]);
    const toques = (t0) => [{ t: t0, art: `muneca${l}`, eje: 0, amp: 0.07, ida: 0.07, vuelta: 0.14 }, { t: t0 + 0.24, art: `muneca${l}`, eje: 0, amp: 0.06, ida: 0.07, vuelta: 0.16 }];
    return { dur: d, entra: 0.22, sale: 0.4,
      claves: [[0.22, brazo(l, ...POSE.senalaPrepara)], [0.45, final, 'golpe']],
      poseApunta: final, manoApunta: 'senala',
      manos: { [l]: 'senala' }, mirar: o.punto || null, resto: 0.15,
      cuerpo: { columna: [0.06 * abajo, -0.08 * s, 0], pecho: [0, -0.05 * s, 0], peso: 0.7 * s },
      golpes: o.dato ? toques(0.75) : [],
      cara: { cejas: [[0.25, 0.3], [0.45, o.dato ? 0.7 : 0.6], [1.3, 0.35]], abrir: [[0.33, 0], [0.47, o.dato ? 0.2 : 0.15], [0.75, 0]] },
      acento: { cada: [4, 6], golpes: toques(0) } };
  },
  // «les presento…»: la palma sale del centro del pecho y se abre en arco hacia lo que presenta (0.5 s, llegando
  // despacio), el brazo casi estirado, la muñeca hacia atrás y los dedos en abanico; mira la obra 0.7 s y vuelve a la
  // sala. El torso gira hacia ahí y se abre (el pecho atrás). `hasta` (otro punto): la palma barre de uno al otro en
  // 1.2 s (los pines de la portada, los años del cronograma). (variantes: el arco amplio; corto, la mano más cerca; un
  // barrido chico sobre lo que presenta)
  presentar: (o) => {
    const l = o.lado || 'D', s = l === 'D' ? 1 : -1, v = o.variante || 0;
    const ap = o.apunta || [-0.9, 0, 0.6];
    // (hacia arriba el antebrazo gira menos: la palma mira a lo que presenta y no al cielo)
    const giro = 1.45 - 0.85 * (o.arriba || 0);
    // (y el codo más doblado: el brazo no sube más de ~11°; lo de más arriba lo muestran el codo, la palma y la mirada)
    const codo = [(v === 1 ? -0.72 : -0.45) - 0.35 * (o.arriba || 0), giro, 0];
    const final = brazo(l, ap, codo, [-0.3, 0, 0]);
    const claves = [[0.2, brazo(l, ...POSE.presentaCentro), 'suave'], [0.72, final, 'sosten']];
    let d = o.dur || 2.8;
    if (o.apuntaHasta) {
      claves.push([0.95, final], [2.15, brazo(l, o.apuntaHasta, codo, [-0.3, 0, 0]), 'suave']);
      d = Math.max(d, 3.4);
    } else if (v === 2) {
      // el barrido chico: llega un poco más adentro y la palma pasa sobre lo que presenta
      claves.splice(1, 1, [0.62, brazo(l, [ap[0], ap[1], ap[2] - 0.22], codo, [-0.3, 0, 0]), 'sosten'], [1.5, final, 'suave']);
    }
    // (la palma corta, con el codo doblado, apunta con el brazo: la recta a la punta de los dedos queda lejos de él)
    return { dur: d, entra: 0.2, sale: 0.45, claves, poseApunta: final, manoApunta: 'abierta',
      manos: { [l]: [[0, 'explica'], [0.4, 'abierta']] }, mirar: o.punto || null, mirada: { objetivo: o.apuntaHasta ? 2.2 : 0.7 }, resto: 0.15,
      cuerpo: { columna: [0, -0.1 * s, 0], pecho: [-0.04, -0.06 * s, 0], peso: 0.5 * s },
      cara: { cejas: [[0.2, 0.3], [0.7, 0.5], [1.5, 0.3]], abrir: [[0.5, 0], [0.72, 0.12], [1, 0]], sonrisa: 1 },
      acento: { cada: [4, 6], golpes: [{ t: 0, art: `muneca${l}`, eje: 0, amp: 0.08, ida: 0.1, vuelta: 0.2 }] } };
  },
  // «miren esto conmigo»: mira la obra saltando entre puntos de ella, asiente a la mitad y al rato (1.2 s) vuelve a la
  // sala (en ciclo, si se sostiene), con el cuerpo en 3/4 hacia ahí y el peso en el pie de atrás; la mano del lado de la
  // obra, abierta y baja hacia ella (la palma a la sala), la otra en la casa. Sin un punto, las manos en la casa (las
  // manos tomadas atrás dejaban una silueta sin brazos). (variantes: la palma baja; la palma arriba, el codo más doblado,
  // «se los muestro»)
  mirar_maqueta: (o) => {
    const d = o.dur || 3.2, l = o.lado || 'D', s = o.punto ? (l === 'D' ? 1 : -1) : 0, v = o.variante === 1;
    const forma = o.apunta ? { pose: brazo(l, o.apunta, v ? [-0.85, 1.45, 0] : [-0.6, 1.3, 0], [-0.2, 0, 0]) } : { pose: {} };
    return { dur: d, entra: 0.5, sale: 0.5, ...forma, manos: o.apunta ? { [l]: v ? 'explica' : 'abierta' } : {},
      mirar: o.punto || null, mirada: 'recorre',
      cuerpo: { columna: [0.02, -0.12 * s, 0], cadera: [0, -0.06 * s, 0], pecho: [-0.03, 0, 0], peso: -0.6 * s },
      cara: { cejas: 0.4, sonrisa: 0.9, labios: LABIOS_REPOSO } };
  },
  // ── Explicar ──
  // (variantes: las dos manos; solo la que manda, la otra acompaña abajo; las palmas de canto, «ordenando»)
  // «les explico»: las dos manos abiertas adelante, la derecha más alta y adelante que la izquierda, que golpean en las
  // palabras que pesan (bajan en 0.12 s y vuelven en 0.25 s, los dedos se cierran un poco y la cabeza cabecea); hablando,
  // los golpes los pone el habla en sus tónicas (`batuta`); callado, a intervalos de 0.5–0.9 s. Cada tanto la palma gira
  // de arriba a de canto, «ordenando», y vuelve. Las cejas suben en el primero. (variantes: las dos manos; solo la que
  // manda, la otra abajo; las palmas de canto). Con el plano medio, las manos más arriba
  explicar: (o) => {
    const d = o.dur || 3.4, v = o.variante || 0, az = o.azar || Math.random, medio = o.plano === 'medio' ? 1 : 0;
    const subir = (e) => [[e[0][0] - 0.22 * medio, e[0][1], e[0][2]], [e[1][0] - 0.25 * medio, e[1][1], e[1][2]], e[2]];
    const alta = (giro) => subir([[-0.55, 0, 0.3], [-1.3, giro, 0], [0.1, 0, 0]]);
    const baja = (giro) => subir(v === 1 ? [HABLA.baja.hombro, HABLA.baja.codo, HABLA.baja.muneca] : [[-0.32, 0, 0.26], [-1.12, giro, 0], [0.12, 0, 0]]);
    const pose = (gD, gI) => ({ ...brazo('D', ...alta(gD)), ...brazo('I', ...baja(gI)) });
    const [arriba, canto] = v === 2 ? [0.6, 1.35] : [1.35, 0.6];
    const forma = (g) => (g > 1 ? 'explica' : 'canto');
    // cuándo gira la palma (después de 2–3 golpes) y cuándo vuelve
    const g1 = Math.min(d - 1.2, 1.5 + az() * 0.4), g2 = Math.min(d - 0.8, g1 + 1.0 + az() * 0.3);
    const claves = [[0.4, pose(arriba, arriba + (v === 1 ? 0 : -0.15))], [g1, pose(arriba, arriba - 0.15)],
      [g1 + 0.3, pose(canto, v === 1 ? arriba : canto)], [g2, pose(canto, v === 1 ? arriba : canto)], [g2 + 0.3, pose(arriba, arriba - 0.15)]];
    const golpes = [];
    for (let t = 0.55 + az() * 0.15, k = 0; t < d - 0.6; t += 0.5 + az() * 0.4, k++) {
      const f = k === 0 ? 1 : 0.7 + az() * 0.3;
      golpes.push({ t, art: 'codoD', eje: 0, amp: 0.12 * f, ida: 0.12, vuelta: 0.25 }, { t: t + 0.04, art: 'munecaD', eje: 0, amp: 0.06 * f, ida: 0.12, vuelta: 0.25 },
        { t, art: 'cabeza', eje: 0, amp: 0.05 * f, ida: 0.12, vuelta: 0.25 });
      if (v === 0) golpes.push({ t: t + 0.05, art: 'codoI', eje: 0, amp: 0.06 * f, ida: 0.12, vuelta: 0.25 });
    }
    // (hablando, la otra mano también golpea cada 2–3 golpes del habla: `batutaOtra`; con una sola mano, no)
    return { dur: d, entra: 0.4, sale: 0.42, claves, batuta: 'D', batutaOtra: v !== 1, golpes, golpesCallado: true,
      manos: { D: [[0, forma(arriba)], [g1 + 0.12, forma(canto)], [g2 + 0.12, forma(arriba)]], I: v === 1 ? 'relajada' : [[0, forma(arriba)], [g1 + 0.12, forma(canto)], [g2 + 0.12, forma(arriba)]] },
      cuerpo: { pecho: [0.03, 0, 0], columna: [0.02, 0, 0] },
      cara: { cejas: [[0.4, 0.3], [0.6, 0.5], [1.3, 0.3]] } };
  },
  // «esto es clave»: la mano baja y va atrás (0.15 s) y el índice sube adelante, hacia la cámara; en la palabra, un golpe
  // adelante y abajo con la cabeza y las cejas al máximo; el pecho adelante y la mirada a la sala; quieto un momento y
  // baja. (variantes: el índice; la mano de canto que corta)
  destacar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.4, canto = o.variante === 1;
    const arriba = brazo(l, ...(canto ? POSE.destacaCanto : POSE.destacaIndice));
    return { dur: d, entra: 0.15, sale: 0.4,
      claves: [[0.15, brazo(l, ...POSE.destacaAtras)], [0.4, { ...arriba, cabeza: [0.04, 0, 0] }, 'golpe']],
      // (el índice se forma cuando la mano ya sube por delante del pecho: formado antes, pasaba apuntando a la sala a la
      // altura de la cintura, un «¡tú!»)
      manos: { [l]: [[0, 'relajada'], [0.22, canto ? 'canto' : 'uno']] },
      golpes: [{ t: 0.58, art: `muneca${l}`, eje: 0, amp: canto ? 0.18 : 0.25, ida: 0.1, vuelta: 0.25 }, { t: 0.58, art: `codo${l}`, eje: 0, amp: canto ? 0.22 : 0.06, ida: 0.1, vuelta: 0.25 },
        { t: 0.58, art: 'cabeza', eje: 0, amp: 0.08, ida: 0.1, vuelta: 0.3 }, { t: 0.58, art: 'cuello', eje: 0, amp: 0.03, ida: 0.1, vuelta: 0.3 }],
      cuerpo: { pecho: [0.04, 0, 0], columna: [[0.4, [0, 0, 0]], [0.6, [0.03, 0, 0]], [1.0, [0.015, 0, 0]]] },
      cara: { cejas: [[0.25, 0.5], [0.6, 1], [1.2, 0.6]], sonrisa: 0.9, entrecierra: [[0.5, 0], [0.65, 0.15], [1.1, 0]] } };
  },
  // hoy frente a con el proyecto: las dos manos al centro con las palmas enfrentadas; «hoy», la izquierda afuera y abajo
  // con un toque, el torso y la cabeza hacia ella y la cara seria (los labios juntos); «con el proyecto», la derecha al
  // otro lado y más alta con la palma arriba (pasa un poco y asienta), el peso cambia de pierna y la sonrisa amplia. La
  // izquierda se queda abajo; las manos nunca se cruzan
  comparar: (o) => {
    const d = o.dur || 3.6;
    const bajaD = [HABLA.baja.hombro, HABLA.baja.codo, HABLA.baja.muneca];
    const hoy = { ...brazo('I', ...POSE.comparaHoy), ...brazo('D', ...bajaD), cabeza: [0.03, 0.12, 0.04] };
    return { dur: d, entra: 0.35, sale: 0.45,
      claves: [[0.35, { ...brazo('I', ...POSE.comparaCentroI), ...brazo('D', ...POSE.comparaCentroD), cabeza: [0.02, 0, 0] }],
        [0.62, hoy, 'golpe'], [1.5, hoy], [1.82, { ...brazo('I', ...alzar(POSE.comparaHoy, 0.06, 0.08)), ...brazo('D', ...POSE.comparaProyecto), cabeza: [-0.02, -0.12, -0.04] }, 'sosten']],
      manos: { I: [[0, 'abierta'], [0.45, 'plana']], D: [[0, 'abierta'], [0.5, 'relajada'], [1.55, 'abierta']] },
      golpes: [{ t: 0.66, art: 'codoI', eje: 0, amp: 0.1, ida: 0.08, vuelta: 0.2 }, { t: 0.66, art: 'cabeza', eje: 0, amp: 0.04, ida: 0.1, vuelta: 0.25 }],
      cuerpo: { columna: [[0.35, [0, 0, 0]], [0.62, [0, 0.12, 0]], [1.5, [0, 0.12, 0]], [1.82, [0, -0.12, 0]]], pecho: [[1.5, [0, 0, 0]], [1.82, [-0.03, 0, 0]]],
        peso: [[0.5, -0.6], [1.5, -0.6], [1.85, 0.6]] },
      cara: { labios: [[0.5, 1], [1.5, 1], [1.8, 0]], sonrisa: [[0.4, 0.55], [1.5, 0.55], [1.85, 1]], cejas: [[0.4, 0.2], [1.5, 0.2], [1.85, 0.8], [2.6, 0.5]] } };
  },
  // una lista, un dedo por frase: la izquierda frente al pecho (no junto a la oreja), la palma a la sala, y la derecha
  // la acompaña abajo, la palma arriba hacia ella (sin taparla: los dedos que cuentan se leen). Con cada frase (`seguir`)
  // la mano sube y baja mientras el dedo nuevo salta, la derecha la señala con un golpe de la palma y la cabeza se ladea
  // hacia ella; hablando, la derecha golpea con lo que dice (`batuta`)
  enumerar: (o) => {
    const n = Math.max(1, Math.min(3, o.n || 1));
    const beat = [{ art: 'hombroI', eje: 0, amp: -0.1, ida: 0.08, vuelta: 0.22 }, { art: 'codoD', eje: 0, amp: -0.1, ida: 0.08, vuelta: 0.2, t: 0.04 },
      { art: 'cabeza', eje: 2, amp: -0.06, ida: 0.15, vuelta: 0.4 }];
    return { dur: o.dur || 3.2, sostener: o.sostener === true, entra: 0.55, curva: 'sosten', batuta: 'D',
      pose: { ...brazo('I', ...POSE.cuentaI), ...brazo('D', ...POSE.cuentaAcompana), cabeza: [0.03, 0.06, -0.04] },
      manos: { I: [[0, 'puno'], [0.3, FORMAS_CONTAR[n - 1]]], D: 'explica' }, golpes: beat.map((g) => ({ ...g, t: 0.45 + (g.t || 0) })), alSeguir: beat,
      cuerpo: { pecho: [0.02, 0.04, 0] }, cara: { cejas: [[0.3, 0.5], [1, 0.3]] },
      relajada: { ...brazo('I', ...alzar(POSE.cuentaI, 0.1, 0.06)), ...brazo('D', ...alzar(POSE.cuentaAcompana, 0.06, 0.08)) } };
  },
  // el resumen del cierre, un dedo al empezar cada punto (`seguir`): como enumerar (la izquierda frente al pecho y arriba,
  // la palma a la sala, la derecha que la acompaña abajo), y entre punto y punto un cabeceo y la mirada que cambia de
  // lado de la sala. Sin `seguir` cuenta solo hasta `n` (el taller, las pruebas)
  contar: (o) => {
    const n = Math.max(1, Math.min(3, o.n || 3));
    const c = GESTOS.enumerar({ ...o, n: o.sostener || o.seguir ? n : 1 });
    if (!o.sostener && !o.seguir && n > 1) {
      // (solo: los números siguientes, cada 0.85 s, con su golpe)
      const paso = 0.85;
      c.dur = o.dur || 0.6 + n * paso + 0.6;
      c.manos = { ...c.manos, I: [[0, 'puno'], ...FORMAS_CONTAR.slice(0, n).map((f, i) => [0.3 + i * paso, f])] };
      for (let i = 1; i < n; i++) c.golpes.push(...c.alSeguir.map((g) => ({ ...g, t: 0.3 + i * paso + (g.t || 0) })));
    }
    c.alSeguir = [...c.alSeguir, { art: 'cuello', eje: 0, amp: 0.03, ida: 0.12, vuelta: 0.3 }];
    c.cambiaMirada = true;
    return c;
  },
  // crece, aumenta, mejora: las dos manos adelante y bajas, las palmas arriba (lo de hoy); una sube por delante y
  // afuera, acelerando (o en tres escalones, con un golpecito en cada uno), con el codo doblado y la palma arriba, hasta
  // la altura del hombro, y la otra se queda en el nivel de partida. El pecho se abre, sube en puntas, las cejas arriba y
  // la boca se abre en la cima. Nunca el brazo estirado en alto ni la palma abajo arriba del hombro. (variantes: en
  // curva; en escalones)
  crecer: (o) => {
    const d = o.dur || 2.9, l = o.lado || 'D', escalones = o.variante === 1;
    const base = dos(...POSE.creceBase);
    const en = (u) => ({ ...base, ...brazo(l, ...entre(POSE.creceBase, POSE.creceArriba, u)) });
    const claves = escalones
      ? [[0.45, base], [0.8, en(0.38), 'golpe'], [1.0, en(0.38)], [1.32, en(0.7), 'golpe'], [1.52, en(0.7)], [1.85, { ...en(1), cabeza: [-0.06, 0, 0] }, 'golpe']]
      : [[0.45, base], [0.65, base], [1.85, { ...en(1), cabeza: [-0.06, 0, 0] }, 'golpe']];
    // (el golpecito: la palma sube un poco y vuelve, como quien levanta algo)
    const tap = (t) => ({ t, art: `muneca${l}`, eje: 0, amp: -0.12, ida: 0.06, vuelta: 0.18 });
    return { dur: d, entra: 0.45, sale: 0.45, claves,
      manos: { [l]: [[0, 'explica'], [1.6, 'abierta']], [otro(l)]: 'explica' }, golpes: escalones ? [tap(0.8), tap(1.32), tap(1.85)] : [tap(1.85)],
      cuerpo: { pecho: [[0.6, [0, 0, 0]], [1.85, [-0.06, 0, 0]]], alto: [[0.7, 0], [1.85, 0.02], [d - 0.5, 0.02], [d, 0]] },
      cara: { cejas: [[0.4, 0.4], [1.85, 0.85]], abrir: [[1.6, 0], [1.9, 0.3], [2.3, 0.08]], sonrisa: 1 } };
  },
  // la escala de la obra: las manos juntas frente al pecho (y la cabeza baja un poco) y se abren en arco, adelante y
  // afuera, pasando un poco: los brazos bajo la horizontal y delante de los hombros (nunca en T), las palmas adentro y
  // los dedos en abanico; el pecho se abre, la cabeza atrás, las cejas arriba y la boca redonda («¡así de grande!»); un
  // pulso hacia afuera y baja por delante. (variantes: las dos manos; una sola, hacia la maqueta)
  grande: (o) => {
    const d = o.dur || 2.8, uno = o.variante === 1, l = o.lado || 'I';
    const junta = { ...brazo('I', ...POSE.grandeJuntaI), ...brazo('D', ...POSE.grandeJuntaD) };
    const abierta = uno ? { ...brazo(l, ...POSE.grandeAbierta), ...brazo(otro(l), HABLA.baja.hombro, HABLA.baja.codo, HABLA.baja.muneca) }
      : dos(...POSE.grandeAbierta);
    const cerrando = uno ? { ...abierta, ...brazo(l, ...alzar(POSE.grandeAbierta, 0.3, -0.5)) } : dos(...alzar(POSE.grandeAbierta, 0.3, -0.5));
    const lados = uno ? [l] : LADOS;
    return { dur: d, entra: 0.3, sale: 0.35,
      claves: [[0.3, { ...junta, cabeza: [0.04, 0, 0] }], [0.78, { ...abierta, cabeza: [-0.06, 0, 0] }, 'sosten'], [d - 0.75, { ...abierta, cabeza: [-0.04, 0, 0] }],
        [d - 0.35, cerrando]],
      manos: uno ? { [l]: [[0, 'abierta']] } : { I: 'abierta', D: 'abierta' },
      golpes: lados.map((x) => ({ t: 1.35, art: `hombro${x}`, eje: 2, amp: 0.08, ida: 0.15, vuelta: 0.35 })),
      cuerpo: { pecho: [[0.3, [0.02, 0, 0]], [0.78, [-0.06, 0, 0]]], columna: [-0.02, 0, 0] },
      cara: { cejas: [[0.3, 0.5], [0.75, 1], [1.8, 0.7]], abrir: [[0.55, 0], [0.8, 0.4], [1.3, 0.25], [1.8, 0.05]], ancho: 0.85, sonrisa: 1 } };
  },
  // «exactamente esto»: la mano en «ok» (el índice y el pulgar que se tocan) a la altura del mentón y delante, la palma
  // a la sala; dos toques cortos hacia adelante en la palabra; los ojos se entrecierran, la mirada a la sala, las cejas
  // un poco y la cabeza adelante
  detalle: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.5;
    const toque = (t) => [{ t, art: `muneca${l}`, eje: 0, amp: 0.12, ida: 0.1, vuelta: 0.2 }, { t, art: `codo${l}`, eje: 0, amp: 0.05, ida: 0.1, vuelta: 0.2 }];
    return { dur: d, entra: 0.42, sale: 0.4, pose: { ...brazo(l, ...POSE.detalle), cabeza: [0.06, 0, 0.03] },
      manos: { [l]: [[0, 'relajada'], [0.2, 'ok']] }, golpes: [...toque(0.5), ...toque(0.82), { t: 0.5, art: 'cabeza', eje: 0, amp: 0.03, ida: 0.1, vuelta: 0.2 }],
      cuerpo: { columna: [0.02, 0, 0] },
      cara: { cejas: 0.3, sonrisa: 0.85, entrecierra: [[0.3, 0], [0.5, 0.25], [d - 0.4, 0.2]], labios: 1 } };
  },
  // obra, trabajo, firmeza: la palma izquierda arriba frente al ombligo y el puño derecho que la golpea tres veces (a
  // 2 Hz, como un martillo: baja rápido, toca, rebota y sube); la palma cede un poco en cada golpe y la cabeza asiente.
  // La cara decidida
  construir: (o) => {
    const d = o.dur || 2.45;
    const arriba = alzar(POSE.construyePuno, MARTILLO.hombro, MARTILLO.codo, MARTILLO.muneca);
    // cada golpe: el hombro llega primero, el codo 0.05 s después y la muñeca al final (el látigo); en el contacto
    // (los tres juntos) el puño toca la palma, y rebotan juntos
    const golpes = [];
    for (const t of [0.5, 1.0, 1.5]) {
      golpes.push({ t, art: 'hombroD', eje: 0, amp: -MARTILLO.hombro, ida: 0.1, sosten: 0.1, vuelta: 0.3 },
        { t: t + 0.03, art: 'codoD', eje: 0, amp: -MARTILLO.codo, ida: 0.12, sosten: 0.05, vuelta: 0.3 },
        { t: t + 0.1, art: 'munecaD', eje: 0, amp: -MARTILLO.muneca, ida: 0.1, vuelta: 0.3 },
        { t: t + 0.19, art: 'codoI', eje: 0, amp: 0.12, ida: 0.04, vuelta: 0.2 }, { t: t + 0.18, art: 'cabeza', eje: 0, amp: 0.05, ida: 0.08, vuelta: 0.25 },
        { t: t + 0.18, art: 'columna', eje: 0, amp: 0.012, ida: 0.08, vuelta: 0.25 });
    }
    return { dur: d, entra: 0.38, sale: 0.4, pose: { ...brazo('D', ...arriba), ...brazo('I', ...POSE.construyePalma), cabeza: [0.06, 0, 0] },
      manos: { D: [[0, 'relajada'], [0.2, 'puno']], I: 'plana' }, golpes,
      cara: { cejas: 0.2, ceno: 0.2, sonrisa: 0.8, labios: 1 } };
  },
  // ── Preguntar y responder ──
  // «¿por qué?» y «estoy preparando»: la mano a la barbilla (la palma hacia la cara, el pulgar bajo el mentón y el índice
  // a medio estirar sobre la mejilla) y el otro brazo cruzado que sostiene el codo; la cabeza ladeada y un poco atrás, el
  // peso atrás, los ojos arriba y a un lado (saltan de un punto a otro), las cejas desparejas y la boca de lado, cerrada.
  // Sostenido: el índice da un toque en la mejilla cada 1.2–2 s y la cabeza se mece despacio. Al soltarlo, «¡ya está!»:
  // las cejas arriba y la mano que se abre hacia la sala
  pensar: (o) => {
    const d = o.dur || 3.2, sost = o.sostener === true, hasta = sost ? 40 : d;
    const puntos = [[0.5, 0.6], [0.3, 0.7], [0.6, 0.5]];
    const ojos = [[0.2, [0.2, 0.3]], [0.4, puntos[0]]];
    for (let t = 1.5, k = 1; t < hasta; t += 1.1 + 0.25 * (k % 3), k++) ojos.push([t - 0.04, puntos[(k - 1) % 3]], [t, puntos[k % 3]]);
    return { dur: d, sostener: sost, entra: 0.55, curva: 'sosten', sale: 0.45,
      pose: { ...brazo('D', ...POSE.pensarD), ...brazo('I', ...POSE.pensarI), cabeza: [-0.1, 0.12, 0.12], cuello: [-0.03, 0.05, 0] },
      manos: { D: [[0, 'relajada'], [0.3, 'ele']], I: 'relajada' },
      cuerpo: { columna: [-0.03, 0, 0], peso: 0.6 },
      vaiven: [{ art: 'cabeza', eje: 2, amp: 0.035, frec: 0.25, desde: 0.6, hasta, decae: 1, azar: 0.15 }],
      cara: { cejasI: 0.6, cejasD: 0.2, sonrisa: 0.5, ancho: 0.85, labios: 1, ojos },
      acento: { cada: [1.2, 2], golpes: [{ t: 0, art: 'munecaD', eje: 0, amp: -0.12, ida: 0.08, vuelta: 0.16 }] },
      relajada: { ...brazo('I', ...alzar(POSE.pensarI, 0.08, 0.12)), cabeza: [-0.07, 0.1, 0.16] },
      alSoltar: () => ({ dur: 0.75, entra: 0.25, sale: 0.4, pose: brazo('D', ...P.palmasArriba), manos: { D: 'abierta' },
        cara: { cejas: 0.9, sonrisa: 1, labios: 0, abrir: [[0.1, 0], [0.25, 0.15], [0.5, 0]] } }) };
  },
  // una pregunta a la sala: una mano abierta adelante, hacia la cámara, la palma arriba (la otra queda en la casa), el
  // torso adelante, la cabeza ladeada, las cejas desparejas y la sonrisa cerrada; espera quieto un segundo (con un
  // parpadeo) y asiente apenas
  preguntar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.6, s = l === 'D' ? 1 : -1;
    return { dur: d, entra: 0.45, curva: 'sosten', sale: 0.45,
      claves: [[0.45, { ...brazo(l, ...POSE.pregunta), cabeza: [-0.02, 0, 0.12 * s] }, 'sosten']],
      manos: { [l]: [[0, 'explica'], [0.3, 'abierta']] },
      cuerpo: { columna: [0.05, 0, 0], pecho: [0, -0.04 * s, 0], peso: 0.4 * s },
      golpes: [{ t: 1.6, art: 'cabeza', eje: 0, amp: 0.05, ida: 0.15, vuelta: 0.35 }, { t: 1.6, art: 'cuello', eje: 0, amp: 0.02, ida: 0.15, vuelta: 0.35 }],
      parpadeos: [1.1],
      cara: { cejasI: 1, cejasD: 0.6, sonrisa: 0.9, labios: 1 } };
  },
  // «sí, así es»: dos o tres asentimientos que decrecen (bajan rápido y suben más despacio; 40 % el cuello y 60 % la
  // cabeza, el torso apenas), los ojos que sonríen con un parpadeo en el primero y la sonrisa que crece. (variantes:
  // tres; dos, más hondos)
  asentir: (o) => {
    const amps = o.variante === 1 ? [0.18, 0.1] : [0.16, 0.1, 0.05];
    const d = o.dur || (o.variante === 1 ? 1.05 : 1.3);
    const golpes = amps.flatMap((a, k) => {
      const t = 0.1 + k * 0.36;
      return [{ t, art: 'cabeza', eje: 0, amp: 0.6 * a, ida: 0.12, vuelta: 0.2 }, { t, art: 'cuello', eje: 0, amp: 0.4 * a, ida: 0.12, vuelta: 0.2 },
        { t, art: 'columna', eje: 0, amp: 0.02 * (a / 0.16), ida: 0.12, vuelta: 0.2 }];
    });
    return { dur: d, pose: {}, entra: 0.1, sale: 0.15, golpes, parpadeos: [0.16],
      cara: { cejas: 0.3, sonrisa: [[0, 0.85], [d - 0.3, 1]], entrecierra: [[0, 0], [0.25, 0.25], [d - 0.2, 0.1]], duchenne: true, labios: LABIOS_REPOSO } };
  },
  // «eso no», sin agresividad: el índice arriba frente al pecho que se agita desde la muñeca (tres veces, cada vez menos)
  // y la cabeza que niega a la mitad de esa frecuencia; la boca cerrada con una sonrisa leve que crece al final (nunca el
  // ceño con los dientes) y las cejas un poco juntas. (variantes: el índice; la mano plana, la palma abajo, que corta de
  // adentro hacia afuera)
  negar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.4, corta = o.variante === 1;
    const cabeza = { art: 'cuello', eje: 1, amp: 0.08, frec: 1.5, desde: 0.35, hasta: 0.35 + 3 / 1.5, decae: 0.6, azar: 0.05,
      cadena: { art: 'cabeza', amp: 0.12, retraso: 0.06 } };
    const cara = { ceno: 0.4, cejas: 0.1, sonrisa: [[0, 0.4], [d - 0.7, 0.4], [d - 0.3, 0.75]], labios: 1 };
    if (corta) {
      return { dur: d, entra: 0.3, sale: 0.4,
        claves: [[0.3, brazo(l, ...POSE.cortaAdentro)], [0.55, brazo(l, ...POSE.cortaAfuera), 'golpe'], [d - 0.5, brazo(l, ...POSE.cortaAfuera)]],
        manos: { [l]: [[0, 'relajada'], [0.15, 'plana']] }, vaiven: [cabeza], cara };
    }
    return { dur: d, entra: 0.35, sale: 0.4, claves: [[0.35, brazo(l, ...POSE.niegaIndice), 'sosten']],
      manos: { [l]: [[0, 'relajada'], [0.2, 'uno']] },
      // (la muñeca en x: con el índice arriba y la palma a la sala, la punta va de un lado al otro)
      vaiven: [{ art: `muneca${l}`, eje: 0, amp: 0.3, frec: 3, desde: 0.45, hasta: 0.45 + 3 / 3, decae: 0.7, azar: 0.05 }, cabeza],
      cara };
  },
  // «tranquilos, está previsto»: las dos manos delante del vientre, al ancho de los hombros, las palmas abajo y un poco
  // hacia la sala; dos presiones hacia abajo (la segunda más chica), el pecho que exhala, un asentimiento lento, los ojos
  // suaves y la boca cerrada sonriendo
  calmar: (o) => {
    const d = o.dur || 2.6, pose = o.plano === 'medio' ? alzarMedio(POSE.calma) : POSE.calma;
    const presion = (t, a) => LADOS.flatMap((x) => [{ t, art: `codo${x}`, eje: 0, amp: 0.16 * a, ida: 0.35, vuelta: 0.3 },
      { t, art: `muneca${x}`, eje: 0, amp: -0.1 * a, ida: 0.35, vuelta: 0.3 }]);
    return { dur: d, entra: 0.45, curva: 'sosten', sale: 0.45, pose: dos(...pose),
      manos: { I: 'plana', D: 'plana' },
      golpes: [...presion(0.55, 1), ...presion(1.3, 0.6), { t: 0.6, art: 'cabeza', eje: 0, amp: 0.05, ida: 0.35, vuelta: 0.5 }],
      cuerpo: { pecho: [[0.5, [0, 0, 0]], [0.9, [0.03, 0, 0]], [1.7, [0.01, 0, 0]]] },
      cara: { cejas: 0.25, sonrisa: 0.9, labios: 1, entrecierra: 0.2 } };
  },
  // ── Emoción ──
  // listo, de acuerdo: el pulgar arriba a la altura del pecho, hacia la sala, que llega de golpe (pasa un poco y rebota);
  // la cabeza se ladea y asiente una vez, un guiño y la sonrisa más grande, con los dientes
  aprobar: (o) => {
    const l = o.lado || 'D', d = o.dur || 2.0, s = l === 'D' ? 1 : -1;
    return { dur: d, entra: 0.12, sale: 0.4,
      claves: [[0.12, brazo(l, ...alzar(POSE.aprueba, 0.35, -0.25, -0.3))], [0.3, { ...brazo(l, ...POSE.aprueba), cabeza: [0.02, 0, 0.08 * s] }, 'golpe']],
      manos: { [l]: [[0, 'relajada'], [0.1, 'pulgar']] },
      golpes: [{ t: 0.3, art: `muneca${l}`, eje: 0, amp: -0.15, ida: 0.06, vuelta: 0.2 }, { t: 0.45, art: 'cabeza', eje: 0, amp: 0.07, ida: 0.14, vuelta: 0.3 },
        { t: 0.45, art: 'cuello', eje: 0, amp: 0.03, ida: 0.14, vuelta: 0.3 }],
      cuerpo: { pecho: [0, -0.05 * s, 0], peso: 0.4 * s },
      cara: { cejas: [[0.2, 0.5], [0.4, 0.7], [1.2, 0.4]], sonrisa: 1, labios: 0, duchenne: true, guino: { lado: l, t: 0.4 } } };
  },
  // ¡un logro!: se agacha un poco con los puños al pecho, los puños suben por delante y salta (con el americano se ve
  // como un rebote del torso), aterriza con un rebote y bombea los puños dos veces; «¡sí!» con la boca y los ojos que se
  // cierran de sonrisa; baja los brazos por delante. Con movimiento reducido, sin agacharse ni saltar
  celebrar: (o) => {
    const d = o.dur || 2.2, r = o.reducido ? 0 : 1;
    const arriba = { ...dos(...POSE.punosArriba), cabeza: [-0.1, 0, 0] };
    const bombeo = (t) => LADOS.map((x) => ({ t, art: `codo${x}`, eje: 0, amp: -0.5, ida: 0.12, vuelta: 0.25 }));
    return { dur: d, entra: 0.2, sale: 0.5,
      claves: [[0.2, { ...dos(...POSE.punosPecho), cabeza: [0.05, 0, 0] }], [0.45, arriba, 'golpe'], [d - 0.6, arriba],
        [d - 0.25, dos(...POSE.punosPecho)]],
      manos: { I: 'puno', D: 'puno' },
      salto: r ? { t: 0.38, dur: 0.3, alto: 0.1 } : null,
      golpes: [...bombeo(1.0), ...bombeo(1.5)],
      cuerpo: { alto: [[0, 0], [0.2, -0.045 * r], [0.38, 0], [0.62, 0], [0.74, -0.025 * r], [0.9, 0]], pecho: [[0.2, [0.04, 0, 0]], [0.45, [-0.05, 0, 0]]],
        columna: [[0.2, [0.06 * r, 0, 0]], [0.45, [-0.03, 0, 0]]] },
      cara: { cejas: [[0.2, 0.6], [0.45, 1], [1.6, 0.8]], abrir: [[0.35, 0], [0.5, 0.6], [0.8, 0.3], [1.1, 0.4], [1.6, 0.1]], sonrisa: 1, labios: 0, duchenne: true,
        cierra: [[0.45, 0], [0.55, 0.85], [0.75, 0.85], [0.9, 0]] } };
  },
  // reconocimiento: las palmas enfrentadas frente al pecho (la izquierda un poco más alta y girada) que se juntan y se
  // separan, 3.5 por segundo, cinco o seis veces (se cierran rápido y se abren más despacio: se tocan de verdad), los
  // dedos que se abren un poco en cada choque, la cabeza que rebota apenas, la sonrisa con los dientes
  aplaudir: (o) => {
    const d = o.dur || 2.2;
    const golpes = [], dedos = [[0, 'plana']];
    for (let k = 0, t = 0.45; k < 6 && t < d - 0.5; k++, t += 1 / 3.5) {
      golpes.push({ t, art: 'hombroD', eje: 2, amp: -0.22, ida: 0.07, vuelta: 0.15 }, { t, art: 'hombroI', eje: 2, amp: -0.18, ida: 0.07, vuelta: 0.15 },
        { t: t + 0.06, art: 'cabeza', eje: 0, amp: 0.02, ida: 0.05, vuelta: 0.12 });
      dedos.push([t + 0.05, 'abierta'], [t + 0.15, 'plana']);
    }
    return { dur: d, entra: 0.4, curva: 'sosten', sale: 0.4, pose: { ...brazo('D', ...POSE.aplaudeD), ...brazo('I', ...POSE.aplaudeI) },
      manos: { I: dedos, D: dedos }, golpes,
      cara: { cejas: 0.7, sonrisa: 1, labios: 0, duchenne: true } };
  },
  // «trabajemos juntos», el lema: abre las dos manos hacia la sala con las palmas arriba (inclusivo, el torso adelante),
  // las trae y entrelaza los dedos frente al pecho, un palmo adelante; un apretón con dos sacudidas, asiente, la sonrisa
  // amplia con los dientes y los ojos que sonríen, mirando a la sala; lo sostiene un momento
  juntos: (o) => {
    const d = o.dur || 2.8;
    const juntas = { ...brazo('D', ...POSE.juntasD), ...brazo('I', ...POSE.juntasI) };
    // (las trae rápido y las junta despacio: si no, el muelle las pasa y una mano entra en la otra)
    const cerca = { ...brazo('D', ...entre(POSE.juntosAbre, POSE.juntasD, 0.75)), ...brazo('I', ...entre(POSE.juntosAbre, POSE.juntasI, 0.75)) };
    // (el apretón: los codos se doblan un poco y vuelven, las dos manos juntas)
    const sacude = (t) => LADOS.map((x) => ({ t, art: `codo${x}`, eje: 0, amp: -0.06, ida: 0.1, vuelta: 0.18 }));
    return { dur: d, entra: 0.45, curva: 'sosten', sale: 0.45,
      claves: [[0.45, { ...dos(...POSE.juntosAbre), cabeza: [-0.03, 0, 0] }, 'sosten'], [0.6, dos(...POSE.juntosAbre)], [0.78, cerca],
        [1.12, { ...juntas, cabeza: [0.03, 0, 0] }, 'sosten']],
      manos: { I: [[0, 'explica'], [0.25, 'abierta'], [0.72, 'entrelazada']], D: [[0, 'explica'], [0.25, 'abierta'], [0.72, 'entrelazada']] },
      golpes: [...sacude(1.3), ...sacude(1.7), { t: 1.3, art: 'cabeza', eje: 0, amp: 0.07, ida: 0.15, vuelta: 0.3 }, { t: 1.3, art: 'cuello', eje: 0, amp: 0.03, ida: 0.15, vuelta: 0.3 }],
      cuerpo: { columna: [[0, [0, 0, 0]], [0.45, [0.04, 0, 0]], [1.0, [0.02, 0, 0]]], pecho: [[0.3, [0, 0, 0]], [0.5, [-0.03, 0, 0]], [1.0, [0, 0, 0]]] },
      cara: { cejas: [[0.3, 0.6], [1.2, 0.5]], abrir: [[0.3, 0], [0.5, 0.15], [0.8, 0]], sonrisa: 1, labios: 0, duchenne: true } };
  },
  // un compromiso sincero: la mano derecha plana sobre el pectoral izquierdo (los dedos hacia el hombro), llega en medio
  // segundo y se apoya con una presión pequeña; la cabeza baja y se ladea, los ojos se cierran un momento y vuelven a la
  // sala, la sonrisa cerrada, una respiración marcada y el peso un poco adelante. Quieto
  corazon: (o) => {
    const d = o.dur || 2.8;
    return { dur: d, entra: 0.5, curva: 'sosten', sale: 0.5,
      claves: [[0.5, { ...brazo('D', ...POSE.corazon), cabeza: [0.08, 0, -0.08] }, 'sosten']],
      manos: { D: [[0, 'relajada'], [0.25, 'plana']] },
      golpes: [{ t: 0.62, art: 'codoD', eje: 0, amp: -0.04, ida: 0.12, sosten: 0.3, vuelta: 0.4 }],
      cuerpo: { columna: [0.05, 0, 0], pecho: [[0.6, [0, 0, 0]], [1.3, [-0.025, 0, 0]], [2.1, [0, 0, 0]]] },
      cara: { cejas: 0.35, sonrisa: 0.9, labios: 1, cierra: [[0.55, 0], [0.75, 0.9], [1.1, 0.9], [1.35, 0]] },
      relajada: { cabeza: [0.06, 0, -0.06] } };
  },
  // ── En pausa ──
  // escucha: las manos entrelazadas al frente, a la altura de la cintura (no los puños), el peso en una pierna, la
  // cabeza ladeada hacia la sala y la sonrisa cerrada. Sostenido: asiente despacio cada tanto y ladea la cabeza. Al
  // soltarlo (vuelve a hablar), inspira
  escuchar: (o) => {
    const [pD, pI] = o.plano === 'medio' ? [alzarMedio(POSE.escuchaD), alzarMedio(POSE.escuchaI)] : [POSE.escuchaD, POSE.escuchaI];
    return { dur: o.dur || 3, sostener: o.sostener !== false, entra: 0.55, curva: 'sosten',
    pose: { ...brazo('D', ...pD), ...brazo('I', ...pI), cabeza: [0.03, 0, 0.1] },
    manos: { I: 'entrelazada', D: 'entrelazada' },
    cuerpo: { peso: 0.8 },
    cara: { cejas: 0.2, sonrisa: 0.9, labios: 1 },
    // sostenido: ladea la cabeza hacia la sala, despacio
    acento: { cada: [4, 6], golpes: [{ t: 0, art: 'cabeza', eje: 2, amp: 0.07, ida: 0.45, vuelta: 0.9 }, { t: 0, art: 'cuello', eje: 2, amp: 0.03, ida: 0.45, vuelta: 0.9 }] },
    relajada: { ...brazo('D', ...alzar(pD, 0.04, 0.02)), ...brazo('I', ...alzar(pI, 0.04, 0.02)), cabeza: [0.04, 0, 0.13] },
    alSoltar: () => ({ dur: 0.6, entra: 0.15, sale: 0.3, pose: {}, cuerpo: { pecho: [[0, [0, 0, 0]], [0.3, [-0.03, 0, 0]], [0.6, [0, 0, 0]]] },
      cara: { cejas: 0.35 } }) };
  },
  // ── Lo hace solo el presentador ──
  // la mano abierta, baja, hacia lo que se explica (después del primer golpe de señalar o de presentar): el brazo
  // apunta al objetivo (`o.punto`) un poco más abajo, el codo a medio doblar y la palma hacia la sala. Se sostiene
  // la escena entera (`sostener`) mientras la otra mano acompaña lo que dice. `o.mirar`: mirarlo mientras dura
  indicar: (o) => {
    const l = o.lado || 'D', s = l === 'D' ? 1 : -1, arriba = o.arriba || 0;
    // (lo que está más arriba que el hombro: el brazo no sube más de ~11° y el codo se dobla más, la palma de costado)
    return { dur: o.dur || 2.4, entra: 0.5, sale: 0.42, pose: brazo(l, o.apunta || [-0.35, 0, 0.45], [-0.6 - 0.35 * arriba, 1.3 - 0.3 * arriba, 0], [-0.2, 0, 0]),
      manos: { [l]: arriba > 0.3 ? 'explica' : 'abierta' }, mirar: o.mirar ? o.punto || null : null, cara: { cejas: 0.2 }, resto: 0.12,
      // (el torso abierto hacia lo que indica y el peso en ese pie)
      cuerpo: { columna: [0, -0.06 * s, 0], peso: 0.5 * s },
      // dos toques hacia lo que indica (cada tanto y en cada frase que sigue hablando de eso: `acentuar`)
      acento: { cada: [4, 6], golpes: [{ t: 0, art: `muneca${l}`, eje: 0, amp: 0.1, ida: 0.09, vuelta: 0.17 },
        { t: 0.3, art: `muneca${l}`, eje: 0, amp: 0.08, ida: 0.09, vuelta: 0.2 }] } };
  },
};
// Cuántas variantes tiene cada gesto (la fábrica recibe `o.variante`, de 0 a n − 1): el animador elige una distinta de
// las dos últimas de ese gesto (o de la última, si hay dos)
export const VARIANTES = { explicar: 3, asentir: 2, presentar: 3, destacar: 2, mirar_maqueta: 2, crecer: 2, grande: 2, negar: 2 };
// Con poco tamaño (la cabeza de menos de 70 px: el busto del celular) los dedos no se leen: contar y enumerar van con la
// mano abierta en un lugar por número, a la altura del pecho (el 1 a la izquierda de la pantalla, con la derecha; el 2
// al centro; el 3 a la derecha, con la izquierda) y un golpe al llegar; el detalle es un golpe de explicar con la mano
// alta; aprobar, el pulgar más alto y un asentimiento. Las manos, arriba del corte del plano medio (≥ 1.2)
const POR_NUMERO = [
  ['D', [-1.05, 0, 0.62], [-0.95, 0.3, 0], [-0.2, 0, 0]],
  ['D', [-1.0, 0, 0.08], [-1.15, 0.3, 0], [-0.2, 0, 0]],
  ['I', [-1.05, 0, 0.62], [-0.95, 0.3, 0], [-0.2, 0, 0]],
];
const porNumero = (o) => {
  const n = Math.max(1, Math.min(3, o.n || 1)), [l, h, c, m] = POR_NUMERO[n - 1];
  return { dur: o.dur || 1.8, sostener: o.sostener === true, entra: 0.32, pose: { ...brazo(l, h, c, m), cabeza: [0.03, 0, 0] },
    manos: { [l]: 'abierta' }, cara: { cejas: 0.5 },
    golpes: [{ t: 0.34, art: `muneca${l}`, eje: 0, amp: 0.2, ida: 0.08, vuelta: 0.24 }, { t: 0.34, art: 'cabeza', eje: 0, amp: 0.05, ida: 0.1, vuelta: 0.25 }] };
};
export const CHICOS = {
  contar: porNumero,
  enumerar: porNumero,
  detalle: (o) => ({ dur: o.dur || 1.6, pose: { ...brazo('D', [-0.95, 0, 0.32], [-1.3, 1.35, 0], [0.1, 0, 0]), pecho: [0.04, 0, 0] },
    manos: { D: 'explica' }, cara: { cejas: 0.5, entrecierra: 0.2 },
    golpes: [{ t: 0.45, art: 'codoD', eje: 0, amp: 0.16, ida: 0.12, vuelta: 0.25 }, { t: 0.45, art: 'cabeza', eje: 0, amp: 0.05, ida: 0.12, vuelta: 0.25 }] }),
  aprobar: (o) => {
    const l = o.lado || 'D';
    return { dur: o.dur || 2.0, pose: { ...brazo(l, [-0.85, 0, 0.3], [-1.6, 0, 0], [0, 0, 0]), cabeza: [0.03, 0, 0.06] },
      manos: { [l]: 'pulgar' }, cara: { cejas: 0.6, abrir: 0.1, sonrisa: 1 },
      golpes: [{ t: 0.45, art: 'cabeza', eje: 0, amp: 0.09, ida: 0.14, vuelta: 0.3 }, { t: 0.45, art: 'cuello', eje: 0, amp: 0.04, ida: 0.14, vuelta: 0.3 }] };
  },
};
// En el rótulo (la cara en un círculo: el atlas a la vista, la ficha en el celular, el celular de lado) los brazos no se
// ven: los gestos se hacen con la cara y la cabeza, y los brazos quedan en la casa, fuera del círculo
// (`gesto(nombre, {soloCara: true})`; los que no están acá no hacen nada: señalar, presentar o mirar la maqueta son mirar
// el modelo, y eso lo pide el presentador)
const asiente = (amps, t0 = 0.1, cada = 0.36, lento = 1) => amps.flatMap((a, k) => {
  const t = t0 + k * cada * lento;
  return [{ t, art: 'cabeza', eje: 0, amp: 0.6 * a, ida: 0.12 * lento, vuelta: 0.2 * lento }, { t, art: 'cuello', eje: 0, amp: 0.4 * a, ida: 0.12 * lento, vuelta: 0.2 * lento }];
});
const niega = (desde, ciclos = 3) => ({ art: 'cuello', eje: 1, amp: 0.08, frec: 1.5, desde, hasta: desde + ciclos / 1.5, decae: 0.6, azar: 0.05,
  cadena: { art: 'cabeza', amp: 0.12, retraso: 0.06 } });
export const CARAS = {
  // aprobar: asiente con la sonrisa y un guiño; celebrar: las cejas arriba y la sonrisa grande («¡sí!»)
  aprobar: () => ({ dur: 1.5, pose: {}, entra: 0.1, sale: 0.3, golpes: asiente([0.14], 0.25), cara: { cejas: 0.5, sonrisa: 1, labios: 0, duchenne: true, guino: { lado: 'D', t: 0.3 } } }),
  celebrar: () => ({ dur: 1.7, pose: { cabeza: [-0.08, 0, 0] }, entra: 0.2, sale: 0.4, golpes: asiente([0.06], 0.7),
    cara: { cejas: 1, sonrisa: 1, labios: 0, duchenne: true, abrir: [[0.2, 0], [0.4, 0.45], [0.9, 0.1]], cierra: [[0.3, 0], [0.4, 0.8], [0.6, 0.8], [0.75, 0]] } }),
  // pensar: la cabeza ladeada y los ojos arriba, a un lado
  pensar: (o) => ({ dur: o.dur || 3.2, sostener: o.sostener === true, entra: 0.5, sale: 0.45, pose: { cabeza: [-0.1, 0.1, 0.14], cuello: [-0.03, 0.04, 0] },
    cara: { cejasI: 0.6, cejasD: 0.2, sonrisa: 0.5, ancho: 0.85, labios: 1, ojos: [0.5, 0.65] }, relajada: { cabeza: [-0.07, 0.08, 0.17] } }),
  // calmar: asiente despacio; negar: la cabeza niega cada vez menos (la boca cerrada, una sonrisa leve al final)
  calmar: () => ({ dur: 2.2, pose: {}, golpes: asiente([0.1, 0.06], 0.25, 0.36, 2), cara: { cejas: 0.25, sonrisa: 0.9, labios: 1, entrecierra: 0.2 } }),
  negar: () => ({ dur: 2.4, pose: {}, vaiven: [niega(0.25)], cara: { ceno: 0.35, cejas: 0.1, sonrisa: [[0, 0.4], [1.7, 0.4], [2.1, 0.75]], labios: 1 } }),
  // saludar y despedirse: las cejas arriba, la sonrisa y un ladeo
  saludar: (o) => ({ dur: o.dur || 1.6, pose: { cabeza: [0, 0, 0.1] }, entra: 0.25, golpes: asiente([0.07], 0.35),
    cara: { cejas: [[0, 0.3], [0.3, 0.9], [1.2, 0.5]], sonrisa: 1, labios: 0, duchenne: true } }),
  despedirse: (o) => ({ dur: o.dur || 1.3, pose: { cabeza: [0, 0, -0.1] }, entra: 0.2, golpes: asiente([0.1], 0.15),
    cara: { cejas: [[0, 0.3], [0.25, 0.8], [1, 0.5]], sonrisa: 1, labios: 0, duchenne: true } }),
  asentir: (o) => GESTOS.asentir(o),
  // preguntar: la cabeza ladeada, las cejas desparejas, espera (un parpadeo) y asiente apenas
  preguntar: () => ({ dur: 2.2, pose: { cabeza: [-0.02, 0, 0.12] }, entra: 0.35, parpadeos: [1.0], golpes: asiente([0.06], 1.4),
    cara: { cejasI: 1, cejasD: 0.6, sonrisa: 0.9, labios: 1 } }),
  // destacar: un cabeceo con las cejas al máximo; grande y crecer: las cejas arriba (y la boca redonda)
  destacar: () => ({ dur: 1.6, pose: {}, golpes: [{ t: 0.4, art: 'cabeza', eje: 0, amp: 0.08, ida: 0.1, vuelta: 0.3 }, { t: 0.4, art: 'cuello', eje: 0, amp: 0.03, ida: 0.1, vuelta: 0.3 }],
    cara: { cejas: [[0.2, 0.5], [0.4, 1], [1.1, 0.5]], entrecierra: [[0.4, 0], [0.5, 0.15], [1, 0]], sonrisa: 0.9 } }),
  grande: () => ({ dur: 1.8, pose: { cabeza: [-0.06, 0, 0] }, cara: { cejas: [[0.2, 0.5], [0.5, 1], [1.3, 0.7]], abrir: [[0.3, 0], [0.5, 0.35], [1.1, 0.05]], ancho: 0.85, sonrisa: 1 } }),
  crecer: () => ({ dur: 1.8, pose: { cabeza: [-0.05, 0, 0] }, cara: { cejas: [[0.2, 0.4], [0.9, 0.85]], abrir: [[0.8, 0], [1.0, 0.25], [1.4, 0.05]], sonrisa: 1 } }),
  // juntos y aplaudir: asiente con la sonrisa amplia; corazón: la cabeza baja y los ojos se cierran un momento
  juntos: () => ({ dur: 1.8, pose: {}, golpes: asiente([0.12, 0.07], 0.3), cara: { cejas: 0.6, sonrisa: 1, labios: 0, duchenne: true } }),
  aplaudir: () => ({ dur: 1.7, pose: {}, golpes: asiente([0.06, 0.05, 0.04], 0.3, 0.28), cara: { cejas: 0.7, sonrisa: 1, labios: 0, duchenne: true } }),
  corazon: () => ({ dur: 2.2, pose: { cabeza: [0.08, 0, -0.08] }, entra: 0.5, sale: 0.5, cara: { cejas: 0.35, sonrisa: 0.9, labios: 1, cierra: [[0.4, 0], [0.6, 0.9], [1.0, 0.9], [1.25, 0]] } }),
  // invitar: las cejas, la sonrisa y un ladeo (sostenido, la mirada recorre la sala); escuchar: ladeada, sonrisa cerrada
  invitar: (o) => ({ dur: o.dur || 2.4, sostener: o.sostener === true, entra: 0.4, pose: { cabeza: [-0.02, 0, 0.08] }, golpes: asiente([0.08], 0.5),
    deriva: o.sostener === true ? { amp: 0.15, cada: [1.8, 2.4] } : null, cara: { cejas: [[0.2, 0.85], [1.4, 0.6]], sonrisa: 1, duchenne: true } }),
  escuchar: (o) => ({ dur: o.dur || 3, sostener: o.sostener !== false, entra: 0.5, pose: { cabeza: [0.03, 0, 0.1] }, cara: { cejas: 0.2, sonrisa: 0.9, labios: 1 },
    acento: { cada: [4, 6], golpes: [{ t: 0, art: 'cabeza', eje: 2, amp: 0.07, ida: 0.45, vuelta: 0.9 }] } }),
  // el resumen del cierre: un cabeceo por punto y la mirada que cambia de lado
  contar: (o) => ({ dur: o.dur || 2.4, sostener: o.sostener === true, pose: {}, golpes: asiente([0.06], 0.15), alSeguir: asiente([0.06], 0),
    cambiaMirada: true, cara: { cejas: 0.4 } }),
};
// Para el asistente: los gestos que puede pedir en cada paso del plan (`gesto`: app/recorrido.py y el puente tienen la
// misma lista; una prueba las compara). Los demás los hace el presentador solo: contar el resumen y escuchar en pausa.
// `senalar` señala lo resaltado (o, sin resaltado, la obra en la maqueta); `mostrar_panel`, el panel
export const GESTOS_AGENTE = ['saludar', 'senalar', 'presentar', 'mostrar_panel', 'mirar_maqueta', 'explicar', 'destacar',
  'comparar', 'enumerar', 'crecer', 'grande', 'detalle', 'construir', 'pensar', 'preguntar', 'asentir', 'negar', 'calmar',
  'aprobar', 'celebrar', 'aplaudir', 'juntos', 'corazon', 'invitar', 'despedirse'];
export const NOMBRES_GESTOS = Object.keys(GESTOS);
// Lo que pide el asistente y se hace con otro gesto: mostrar_panel señala el dato del panel (con las cejas más arriba,
// la boca de «fíjense» y dos toques en el golpe); sin un punto, presenta
const ALIAS = { mostrar_panel: (o) => [o.punto && o.foco !== false ? 'senalar' : 'presentar', { dato: true }] };

const suave = (t) => { const x = Math.min(1, Math.max(0, t)); return x * x * (3 - 2 * x); };
const acercar = (k, dt) => 1 - Math.exp(-k * dt);
const lim = (v, a, b) => Math.min(b, Math.max(a, v));
// Un valor del clip que cambia con su tiempo (la cara, el cuerpo): fijo (un número o [x, y, z]) o una línea
// [[t, valor], …] que va de una clave a la siguiente, suave (antes de la primera, la primera; después, la última)
const esLinea = (v) => Array.isArray(v) && Array.isArray(v[0]) && v[0].length === 2 && typeof v[0][0] === 'number';
function enTiempo(v, tau) {
  if (!esLinea(v)) return v;
  if (tau <= v[0][0]) return v[0][1];
  for (let k = 1; k < v.length; k++) {
    if (tau >= v[k][0]) continue;
    const [t0, a] = v[k - 1], [t1, b] = v[k], u = suave((tau - t0) / Math.max(1e-3, t1 - t0));
    return typeof a === 'number' ? a + (b - a) * u : a.map((x, i) => x + (b[i] - x) * u);
  }
  return v[v.length - 1][1];
}
// lo más alto de un valor (fijo o en el tiempo)
const maximo = (v) => (esLinea(v) ? Math.max(...v.map((x) => x[1])) : v);
const LADOS = ['I', 'D'];
const BRAZOS = new Set(['hombroI', 'codoI', 'munecaI', 'hombroD', 'codoD', 'munecaD']);

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
// Lo más que la cabeza (con el cuello) se alza para mirar algo de arriba (rad de la mirada); el resto, los ojos
const CABEZA_ARRIBA = 0.13;
// El parpadeo: cierra en 60 ms y abre en 120 ms
const CIERRA_S = 0.06, ABRE_S = 0.12;
// La sonrisa callado: la de la foto, amplia; los labios entreabiertos, con la fila de los dientes de arriba a la vista
// (con los labios cerrados, y las cejas gruesas, la cara callada se leía seria o socarrona y no la del candidato). Los
// labios cerrados quedan para los gestos que los piden (pensar, el corazón, escuchar) y las p, b y m del habla
const SONRISA_REPOSO = 1, LABIOS_REPOSO = 0.38;

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
 * crearAnimador(personaje, {reducido, azar}) → {actualizar(dt), gesto(nombre, opciones), detenerGesto(),
 * hablar(seg|true, {texto, claves}), callar({dicha}), mirarA(punto|null), mirarSala(seg), caminarA(x, {velocidad, rumbo,
 * zancada}), reubicar(x), entrar(al, {hondo, instante, casi}), salir(al, {hondo, gracias}), agacharse(al, {hondo}),
 * asomarse(al, {hondo, desde}), estado(), girar(rumbo, {ya}), casa(nombre), tamano(pxAlto, {celular}), acentuar(),
 * alzarCejas(v), reaccionar(v), camara, apertura, plano, chica}.
 * `gesto(nombre, {soloCara: true})`: el gesto con la cara y la cabeza (CARAS: el rótulo); si no tiene, nada.
 * `detenerGesto()`: lo suelta hacia la casa (si tiene su manera de terminar, `alSoltar`, la hace); un sostenido sale suave
 * desde ese momento. `reaccionar(v)`: las cejas arriba y un asentimiento, sin dejar el gesto (la simulación terminó).
 * `gesto(nombre, {sostener: true})` sostiene cualquier gesto hasta otro o hasta detenerGesto(); `{mirada}` cambia cómo
 * mira su punto (el formato de los clips); `{entra}`, lo que tarda en entrar; `{variante}`, cuál (si no, una distinta de
 * las dos últimas). Un gesto nuevo entra desde lo que pedía el anterior (si el mismo brazo cambia de lado, por delante del
 * pecho) y lo que este no usa vuelve a la casa. Un gesto sostenido sigue vivo: se mueve apenas, respira más, asiente
 * despacio, hace su acento cada 4–6 s (`acentuar()` lo hace ya: los dos toques de la mano que indica) y a los 6–7 s
 * afloja (las manos un poco más bajas).
 * `hablar(seg | true, {texto})`: con el texto, la boca va por sus sílabas (los labios se cierran en la p, la b y la m;
 * las pausas, con la boca cerrada), la mano que manda da un golpe en la tónica de las palabras clave y la cabeza y las
 * cejas acompañan; con voz (`true`) al ritmo de la voz de las frases anteriores, hasta `callar` (y si la voz sigue, sin
 * texto). Sin texto, sílabas al azar.
 * `tamano(pxAlto)`: con la cabeza de menos de 70 px (o el celular) contar, enumerar, detalle y aprobar se reemplazan por
 * versiones que se leen por la silueta (CHICOS).
 * `plano`: lo que se ve de él ('entero', 'americano', 'medio'…; lo pone el presentador): con la figura entera, a veces
 * deja los brazos sueltos en reposo; con el plano medio, las manos que hablan van más arriba.
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
  const miraOfs = new THREE.Vector3();
  // la cara del gesto en este instante (sus valores pueden cambiar con el tiempo del clip: `enTiempo`)
  const caraAhora = {};
  function caraEn(cc, tau) {
    for (const k of Object.keys(caraAhora)) delete caraAhora[k];
    for (const k of Object.keys(cc)) caraAhora[k] = k === 'guino' ? cc[k] : enTiempo(cc[k], tau);
    return caraAhora;
  }
  const tmpV = new THREE.Vector3(), tmpV2 = new THREE.Vector3(), tmpM = new THREE.Matrix4(), tmpE = [0, 0, 0];
  const qArco = { hombro: {}, codo: {} };
  for (const l of LADOS) for (const f of ['hombro', 'codo']) qArco[f][l] = qDe(`${f}${l}`, ARCO[f]);
  const qAndar = {};
  for (const l of LADOS) for (const f of ['hombro', 'codo', 'muneca']) qAndar[`${f}${l}`] = qDe(`${f}${l}`, ANDAR[f]);

  let t = 0;
  let clip = null, tClip = 0, nombreClip = null, alTerminarClip = null;
  let desde = null, desdeManos = null;   // de dónde viene el gesto (lo que pedía el anterior), mientras entra
  let hablando = false, finHabla = 0;
  let abrir = 0, ancho = 1, labios = 1;
  // lo que dice: el plan de sílabas (planHabla) o el generador; el ritmo de la voz (lo que dura de verdad lo que se dice
  // respecto de lo estimado, de la frase anterior) y lo que va diciendo con voz, para medirlo
  let habla = null, ritmo = 1, vozPlan = null;
  const bocaP = [0, 1, 1], bocaQ = [0, 1, 1];
  // la casa de hablar: cuánto la mano derecha es la que manda (1) o la izquierda (0), la forma de la mano que manda y
  // los golpes (en la tónica de las palabras clave; cada 3–4 cambia la forma)
  let wHabla = 0, domD = 1, formaHabla = 0, golpesForma = 0, cadaForma = 3, ultimoGolpe = -9, golpesHabla = 0;
  let golpesOtra = 0, cadaOtra = 2;   // (la otra mano de explicar: cada cuántos golpes del habla golpea también)
  const dedosGolpe = { I: { t0: -9, f: 0 }, D: { t0: -9, f: 0 } };
  // la mirada que deriva por la sala mientras habla (se queda en una «persona» 2–4 s) y el ladeo de las preguntas
  let deriva = 0, derivaP = 0, proxDeriva = 0, ladeo = 0;
  let parpado = 1, proxParpadeo = 2 + azar() * 3, enParpadeo = -1, doble = false, ultimoParpadeo = -9;
  let cejasPico = 0, sonrisa = 1, ceno = 0, entrecierra = 0, entrePulso = 0, duchenne = 0, cierra = 0;
  const cejasL = [0, 0];      // cada ceja (la I y la D: cara.cejas[0] y [1])
  // los impulsos sueltos (los golpes del habla, el asentimiento al terminar una frase, los acentos): {t0, art, eje, amp,
  // ida, vuelta}
  const sueltos = [];
  // la variedad: las dos últimas variantes de cada gesto
  const usadas = {};
  let relajaEstado = 0, vivoAntes = 0;   // (el sostenido: cuánto aflojó y cuánto está vivo, del cuadro anterior)
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
  // `chica`: la cabeza mide menos de 70 px en la pantalla (o es el celular): los gestos de dedos van por la silueta
  const api = { camara: null, apertura: 0.55, plano: null, chica: false };

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
  const qCasasMedio = Object.fromEntries(Object.entries(CASAS).map(([n, c]) => [n, Object.fromEntries(Object.entries(n === 'sueltos' ? c : casaMedio(c)).map(([j, e]) => [j, qDe(j, e)]))]));
  let wMedio = 0;           // cuánto manda el plano medio (las manos de la casa más arriba), con 0.25 s de transición
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
  const BAJAR = { senalar: 0, presentar: 0.12, indicar: 0.05, mirar_maqueta: 0.05 };
  // lo más que sube la recta del hombro a la mano abierta sobre la horizontal (rad, ≈ 11°): lo que está más arriba lo
  // muestran el codo más doblado, la palma y la mirada (el brazo estirado en alto con la mano plana se lee como un saludo
  // de brazo en alto). El índice (señalar) sí apunta arriba
  const TOPE = { presentar: 0.2, indicar: 0.2, mirar_maqueta: 0.2 };
  function gesto(nombre, o = {}) {
    // (mostrar_panel: señalar el dato del panel, con las cejas y la boca de «fíjense»; sin un punto, presentar)
    if (!GESTOS[nombre] && ALIAS[nombre]) { const [g, extra] = ALIAS[nombre](o); return gesto(g, { ...o, ...extra }); }
    if (!GESTOS[nombre]) return 0;
    // en el rótulo, solo con la cara y la cabeza (CARAS; si no tiene, nada)
    if (o.soloCara && !CARAS[nombre]) return 0;
    // con poco tamaño, la versión que se lee por la silueta (CHICOS)
    const chico = api.chica && !o.soloCara ? CHICOS[nombre] || null : null;
    const hacer = o.soloCara ? CARAS[nombre] : chico || GESTOS[nombre];
    const opciones = { ...o, chica: !!api.chica, plano: api.plano, azar, reducido };
    // la variante: la pedida o una distinta de las dos últimas (el mismo gesto que sigue, la misma)
    if (!o.seguir || nombreClip !== nombre) opciones.variante = variante(nombre, o.variante);
    else opciones.variante = clip?.variante ?? 0;
    // señalar, presentar, indicar y mirar la maqueta: el brazo del lado del punto y el ángulo del hombro que lo apunta,
    // medidos con el rumbo al que va el cuerpo (si está girando, apunta a donde quedará). `hasta`: un segundo punto
    // (presentar barre la palma de uno al otro)
    let apuntaA = null;
    if (BAJAR[nombre] !== undefined && o.punto && !o.soloCara) {
      const r0 = grupo.rotation.y;
      grupo.rotation.y = rumboBase;
      const lado = o.lado || ladoDe(o.punto);
      opciones.lado = lado;
      const bajar = BAJAR[nombre];
      // cuánto más abajo que el hombro está lo que apunta (0 a la altura del hombro o más arriba; 1, 30° abajo o más)
      grupo.updateMatrixWorld(true);
      huesos[`hombro${lado}`].getWorldPosition(tmpV);
      tmpV2.copy(o.punto).sub(tmpV);
      opciones.abajo = lim(-Math.atan2(tmpV2.y, Math.hypot(tmpV2.x, tmpV2.z)) / 0.52, 0, 1);
      // y cuánto más arriba (0 a la altura del hombro; 1, 40° arriba o más)
      opciones.arriba = lim(Math.atan2(tmpV2.y, Math.hypot(tmpV2.x, tmpV2.z)) / 0.7, 0, 1);
      // primero el brazo apuntado; después, con el codo, la muñeca y la mano de ese gesto (la pose con la que apunta),
      // la punta del índice
      const tope = TOPE[nombre] ?? null;
      const borrador = hacer({ ...opciones, apunta: apuntar(lado, o.punto, bajar, null, null, tope), apuntaHasta: o.hasta ? apuntar(lado, o.hasta, bajar, null, null, tope) : null });
      const pose = borrador.poseApunta || borrador.pose || null;
      const forma = borrador.manoApunta || (typeof borrador.manos?.[lado] === 'string' ? borrador.manos[lado] : null);
      opciones.apunta = apuntar(lado, o.punto, bajar, pose, forma, tope);
      opciones.apuntaHasta = o.hasta ? apuntar(lado, o.hasta, bajar, pose, forma, tope) : null;
      grupo.rotation.y = r0;
      grupo.updateMatrixWorld(true);
      apuntaA = { lado, bajar, pose, forma, tope, puntos: [[o.punto.clone(), opciones.apunta]] };
      if (o.hasta) apuntaA.puntos.push([o.hasta.clone(), opciones.apuntaHasta]);
    }
    const nuevo = hacer(opciones);
    // (y en cada cuadro el hombro vuelve a apuntar: el pecho se mueve con la respiración, la mirada y el giro; en la
    // pose o en las claves que llevan ese ángulo)
    if (apuntaA) nuevo.apuntaA = apuntaA;
    // cualquier gesto se puede sostener hasta otro (o hasta detenerGesto); y entrar más rápido (la despedida que se agacha)
    if (o.sostener === true) nuevo.sostener = true;
    if (Number.isFinite(o.entra) && o.entra > 0) nuevo.entra = o.entra;
    // y mirar su punto de otra manera ('sigue': mientras la cámara viaja; 'sala'; {objetivo, cada, dura})
    if (o.mirada !== undefined) nuevo.mirada = o.mirada;
    // el mismo gesto que sigue (enumerar: un dedo más con cada frase): cambia sus manos sin volver a empezar (chico, el
    // número siguiente es otro lugar: un gesto nuevo que entra desde el de antes, sostenido como él)
    if (o.seguir && clip && nombreClip === nombre && chico) { if (clip.sostener) nuevo.sostener = true; }
    else if (o.seguir && clip && nombreClip === nombre) {
      clip.manosEn = normalizarManos(nuevo.manos);
      for (const l of Object.keys(clip.manosEn)) clip.manosEn[l] = clip.manosEn[l].map(([, f]) => [0, f]).slice(-1);
      // (el golpe del número nuevo: la mano sube y baja, la cabeza se ladea hacia ella, el índice de la otra la toca)
      for (const g of nuevo.alSeguir || []) golpe(g.art, g.eje ?? 0, g.amp, g.ida, g.vuelta, t + (g.t || 0));
      // (contar: la mirada cambia de lado de la sala con cada número)
      if (clip.cambiaMirada && !reducido) { deriva = (deriva > 0 ? -1 : 1) * (0.08 + 0.05 * azar()); derivaP = 0; proxDeriva = t + 2 + azar(); }
      return clip.sostener ? Infinity : clip.dur;
    }
    nuevo.variante = opciones.variante;
    nuevo.chico = !!chico;
    nuevo.soloCara = !!o.soloCara;
    ponerClip(nuevo, nombre, typeof o.alTerminar === 'function' ? o.alTerminar : null);
    return clip.sostener ? Infinity : clip.dur;
  }
  // El clip nuevo, que entra desde lo que pedía el gesto anterior en el último cuadro (sus articulaciones y sus manos)
  // y no desde el reposo
  function ponerClip(nuevo, nombre, alTerminar) {
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
    alTerminarClip = alTerminar;
    if (typeof clip.cara?.cejas === 'number') cejasPico = Math.max(cejasPico, clip.cara.cejas);
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
    // (`dedosSale`: el retraso de los dedos al soltar, si es otro: la mano que saluda sigue abierta hasta que bajó)
    c.retDedosSale = propio.dedosSale ?? c.retDedos;
    const mas = Math.max(0, c.retDedos, c.retDedosSale, ...c.articulaciones.map((j) => c.ret[j]));
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
    // la mirada: el plan (mira el punto un rato y vuelve a la sala, con otro vistazo cada tanto). 'recorre': mira la
    // obra saltando entre puntos de ella (cada 0.5–0.8 s), asiente a la mitad y a los 1.2 s vuelve a la sala (1.1 s), en
    // ciclo. `resto`: mirando a la sala, la cara se queda un poco (rad) hacia el punto (el torso sigue abierto a él)
    if (c.mirar) {
      const m = c.mirada ?? { objetivo: 0.8 };
      c.plan = typeof m === 'string' ? { modo: m } : { modo: 'vistazo', objetivo: m.objetivo ?? 0.8, cada: m.cada || [2, 3], dura: m.dura ?? 0.7 };
      if (c.plan.modo === 'vistazo') c.plan.prox = c.plan.objetivo + c.plan.cada[0] + azar() * (c.plan.cada[1] - c.plan.cada[0]);
      if (c.plan.modo === 'recorre') { c.plan.ofs = new THREE.Vector3(); c.plan.proxSalto = 0; c.plan.ciclo = -1; }
    }
    // el hombro que apunta: las poses (la de `pose` o las de las claves) que llevan el ángulo de cada punto, para volver
    // a apuntarlas en cada cuadro
    c.aim = [];
    if (c.apuntaA) {
      const h = `hombro${c.apuntaA.lado}`;
      c.aim = c.apuntaA.puntos.map(([, ref]) => {
        const qs = [];
        if (c.pose?.[h] === ref) qs.push(c.qPose[h]);
        if (c.qClaves) c.claves.forEach(([, p], k) => { if (p[h] === ref) qs.push(c.qClaves[k][1][h]); });
        return qs;
      });
    }
    // el mismo brazo a otro lado (más de 1.2 rad entre el hombro de antes y el de ahora): pasa por delante
    c.arco = {};
    if (desde) for (const l of LADOS) {
      const h = `hombro${l}`;
      if (desde[h] && c.qPose[h] && 2 * Math.acos(Math.min(1, Math.abs(desde[h].dot(c.qPose[h])))) > 1.2) c.arco[l] = true;
    }
    c.desdeSolo = desde ? Object.keys(desde).filter((j) => !c.qPose[j]) : [];
    // sostenido, sigue vivo: cuándo asiente despacio, cuándo hace su acento y cuándo afloja (y hacia qué pose: la que
    // trae o, si no, los brazos que no apuntan un poco más bajos)
    c.semilla = azar() * 100;
    c.proxAsiente = c.entra + 1.5 + azar() * 1.5;
    if (c.acento) { const [a0, a1] = c.acento.cada || [4, 6]; c.proxAcento = c.entra + a0 + azar() * (a1 - a0); }
    c.tRelaja = 5.8 + azar() * 0.8;
    c.kParpadeo = 0;
    c.qRelaja = Object.fromEntries(Object.entries(c.relajada || relajadaDe(c)).filter(([j]) => c.qPose[j]).map(([j, e]) => [j, qDe(j, e)]));
    return c;
  }
  // La pose aflojada de un sostenido que no trae la suya: los brazos que no apuntan, un poco más bajos y más cerca
  function relajadaDe(c) {
    const fuente = c.claves ? c.claves[c.claves.length - 1][1] : c.pose || {};
    const out = {};
    for (const l of LADOS) {
      if (c.apuntaA?.lado === l) continue;
      const h = fuente[`hombro${l}`], k = fuente[`codo${l}`];
      if (h) out[`hombro${l}`] = [h[0] + 0.07, h[1], h[2] * 0.85];
      if (k) out[`codo${l}`] = [k[0] * 0.95, k[1], k[2]];
    }
    return out;
  }
  // La variante de un gesto: la pedida, o una distinta de las dos últimas (de la última, si tiene dos)
  function variante(nombre, pedida) {
    const n = VARIANTES[nombre] || 1;
    if (n <= 1) return 0;
    let v = Number.isInteger(pedida) ? lim(pedida, 0, n - 1) : null;
    if (v === null) {
      const ult = (usadas[nombre] || []).slice(n >= 3 ? -2 : -1);
      const libres = [...Array(n).keys()].filter((x) => !ult.includes(x));
      v = libres[Math.floor(azar() * libres.length)] ?? 0;
    }
    usadas[nombre] = [...(usadas[nombre] || []), v].slice(-2);
    return v;
  }
  // El acento de un sostenido (sus golpes y sus manos, desde ahora) y cuándo el próximo
  function acentoDe(c) {
    const a = c.acento;
    if (!a) return;
    for (const g of a.golpes || []) golpe(g.art, g.eje ?? 0, g.amp, g.ida, g.vuelta, t + (g.t || 0));
    if (a.manos && !reducido) c.acentoManos = { t0: tClip, manos: normalizarManos(a.manos) };
    const [a0, a1] = a.cada || [4, 6];
    c.proxAcento = tClip + a0 + azar() * (a1 - a0);
  }
  /** Un impulso suelto (después del muelle: su forma es la que se ve) que empieza en `en`: llega a `amp` en `ida` y vuelve
   * en `vuelta`. Con movimiento reducido, nada */
  function golpe(art, eje, amp, ida = 0.12, vuelta = 0.25, en = t) {
    if (reducido || !extra[art] || !amp) return;
    sueltos.push({ t0: en, art, eje, amp, ida, vuelta });
    if (sueltos.length > 48) sueltos.shift();
  }
  function normalizarManos(m = {}) {
    const out = {};
    for (const l of LADOS) {
      const v = m[l];
      if (!v) continue;
      // (cada forma, por su nombre o como los cinco números)
      const forma = (f) => MANOS[f] || (Array.isArray(f) && f.length === 5 ? f : MANOS.relajada);
      out[l] = Array.isArray(v) ? v.map(([tt, f]) => [tt, forma(f)]) : [[0, forma(v)]];
    }
    return out;
  }
  // Cuánto pesa el clip en el instante `tau` (el de una articulación: el del clip menos su retraso): entra con su
  // curva y sale suave
  const entrando = (c, tau) => (tau <= 0 ? 0 : curva(c.curvaEntra, tau / c.entra, c.entra));
  const saliendo = (c, tau) => (c.sostener ? 1 : 1 - suave((tau - (c.dur - c.sale)) / c.sale));
  const pesoBase = (c, tau) => Math.max(0, entrando(c, tau)) * saliendo(c, tau);
  // lo que pesa el clip ahora en la articulación `j` (con su retraso)
  const pesoArt = (j) => (clip ? Math.max(0, entrando(clip, tClip - clip.ret[j])) * saliendo(clip, tClip - clip.ret[j]) : 0);
  /** Suelta el gesto (a la casa: la de hablar si habla). Si el gesto tiene su manera de terminar (`alSoltar`: el «¡ya
   * está!» de pensar, la inspiración de escuchar antes de volver a hablar), la hace: un clip corto con el mismo nombre */
  function detenerGesto() {
    if (!clip) return;
    if (typeof clip.alSoltar === 'function' && !clip.soltando && pesoBase(clip, tClip) > 0.3) {
      const al = alTerminarClip;
      let c = null;
      try { c = clip.alSoltar({ chica: !!api.chica, plano: api.plano, azar, reducido }); } catch { c = null; }
      if (c) { c.soltando = true; c.variante = clip.variante; ponerClip(c, nombreClip, al); return; }
    }
    // (un sostenido que ya pasó su duración sale desde ahora, en lo que tarda su salida: si no, terminaría en el cuadro
    // siguiente y la cara y los dedos saltarían)
    if (clip.sostener && tClip > clip.dur - clip.sale) { clip.dur = tClip + clip.sale; clip.vida = clip.dur + clip.retMax; }
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
  // (señalar con el brazo apuntado erraba unos 8°: 50 px a tamaño de presentación). `tope`: lo más que sube la recta
  // sobre la horizontal (rad; la mano abierta: lo de más arriba no se alcanza con el brazo en alto)
  function apuntar(lado, punto, bajar = 0, pose = null, forma = null, tope = null) {
    const h = huesos[`hombro${lado}`];
    grupo.updateMatrixWorld(true);
    const desdeH = new THREE.Vector3().setFromMatrixPosition(h.matrixWorld);
    const d = new THREE.Vector3().copy(punto).sub(desdeH);
    if (d.lengthSq() < 1e-6) d.set(0, 0, 1);
    tmpM.copy(h.parent.matrixWorld).invert();
    d.transformDirection(tmpM);
    if (bajar) { d.y -= bajar * Math.hypot(d.x, d.z); d.normalize(); }
    if (tope !== null && d.y > Math.sin(tope)) {
      const hz = Math.max(1e-6, Math.hypot(d.x, d.z)), k = Math.cos(tope) / hz;
      d.set(d.x * k, Math.sin(tope), d.z * k);
    }
    // nunca hacia atrás del cuerpo ni cruzado por delante del pecho
    d.z = Math.max(d.z, 0.15);
    d.x = Math.max(d.x, 0.08);
    d.normalize();
    const euler = (v) => [Math.atan2(-v.z, -v.y), 0, Math.asin(Math.max(-1, Math.min(1, v.x)))];
    const v = pose ? puntaEnHombro(lado, pose, forma) : null;
    if (!v) return euler(d);
    // la dirección a pedirle al hombro para que la punta caiga en la recta: unas vueltas de corrección. El brazo nunca
    // va detrás del cuerpo: si la recta lo pide (lo que apunta está muy al costado), queda al costado, lo más cerca que
    // se puede (una sola solución que cambia de a poco con el punto: antes saltaba al brazo apuntado y el brazo subía o
    // bajaba 30° de golpe en un sostén cuando la mirada movía el pecho)
    const pedido = d.clone(), w = new THREE.Vector3(), q = new THREE.Quaternion(), corr = new THREE.Quaternion();
    for (let i = 0; i < 8; i++) {
      qDe(`hombro${lado}`, euler(pedido), q);
      w.copy(v).applyQuaternion(q);
      corr.setFromUnitVectors(w, d);
      pedido.applyQuaternion(corr).normalize();
      if (pedido.z < 0.05) { const k = Math.sqrt((1 - 0.05 * 0.05) / Math.max(1e-9, pedido.x * pedido.x + pedido.y * pedido.y)); pedido.set(pedido.x * k, pedido.y * k, 0.05); }
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
    base.rotation.set(ABRE[0] * (1 - v0), 0, -1.5 * v0);
    punta.rotation.set(0, 0, -1.3 * v0);
    h.updateMatrixWorld(true);
    const v = h.worldToLocal(punta.localToWorld(new THREE.Vector3(0, -0.044, 0)));
    h.quaternion.copy(guardado[0]); c.quaternion.copy(guardado[1]); m.quaternion.copy(guardado[2]);
    base.rotation.copy(guardado[3]); punta.rotation.copy(guardado[4]);
    h.updateMatrixWorld(true);
    return v.lengthSq() > 1e-8 ? v.normalize() : null;
  }


  // ── Hablar ──
  /** Habla `seg` segundos (o hasta `callar`, con `true`: la voz). Con `texto`, la boca va por sus sílabas (planHabla) y
   * las manos y la cabeza golpean en sus palabras clave (`claves`: lo resaltado); con voz, al ritmo que tuvo la voz en la
   * frase anterior (si la voz sigue después del texto, sílabas al azar). Sin texto mientras ya dice uno (la voz que
   * avisa que empezó justo antes o después de la frase), sigue con el mismo */
  function hablar(seg = true, o = {}) {
    const voz = seg === true;
    const texto = typeof o?.texto === 'string' ? o.texto.trim() : '';
    const fin = voz ? t + 30 : t + Math.max(0.2, Math.min(30, Number(seg) || 0));
    if (!texto && hablando && habla?.texto && (t - habla.t0) / habla.f < habla.dur) {
      finHabla = Math.max(finHabla, fin);
      if (voz) habla.voz = true;
      return;
    }
    hablando = true;
    finHabla = fin;
    const antes = [abrir, ancho, labios];
    if (texto) {
      const p = planHabla(texto, { claves: o.claves || [], dura: voz ? null : fin - t });
      habla = { segs: p.segs, ev: p.eventos, k: 0, ke: 0, t0: t, f: voz ? ritmo : 1, texto: true, voz, dur: p.dur, fin: p.dur,
        pregunta: p.pregunta, antes, cuenta: 0, proxPausa: 6, golpeGen: -9 };
      vozPlan = voz ? { t0: t, est: p.dur } : null;
    } else {
      habla = { segs: [], ev: [], k: 0, ke: 0, t0: t, f: 1, texto: false, voz, dur: 0, fin: 0, pregunta: false, antes,
        cuenta: 0, proxPausa: 5 + Math.floor(azar() * 5), golpeGen: -9 };
      vozPlan = null;
      cejasPico = Math.max(cejasPico, 0.35);
    }
    // (una pregunta: la cabeza ladeada)
    ladeo = habla.pregunta && !reducido ? (azar() < 0.5 ? -1 : 1) * 0.05 : 0;
  }
  /** Calla. `dicha`: la voz terminó de decir la frase (no la cortaron): lo que tardó, frente a lo estimado, es el ritmo
   * de la frase siguiente (entre 0.7 y 1.4) */
  function callar(o = {}) {
    if (hablando && vozPlan && o?.dicha) {
      // (mucho menos de lo estimado: la cortaron, una pausa; no dice nada del ritmo)
      const real = t - vozPlan.t0, r = real / Math.max(1e-3, vozPlan.est);
      if (real > 0.6 && vozPlan.est > 0.6 && r >= 0.55) ritmo = lim(r, 0.7, 1.4);
    }
    vozPlan = null;
    if (hablando) terminarFrase();
    hablando = false;
  }
  // al terminar de decir algo: un asentimiento chico (y la sonrisa de reposo, que vuelve sola)
  function terminarFrase() {
    golpe('cabeza', 0, 0.04, 0.15, 0.3);
    golpe('cuello', 0, 0.015, 0.15, 0.3);
  }
  /** Cada cuadro, mientras habla: los golpes que tocan, la sílaba de ahora y lo que hace la boca (en `bocaP`: [abrir,
   * ancho, labios]). Entra desde cómo terminó la sílaba anterior (35 ms: no salta) */
  function avanzarHabla() {
    const h = habla;
    const tau = (t - h.t0) / h.f;
    if (!h.texto || (h.voz && tau > h.fin - 0.3)) generar(h, tau);
    while (h.ke < h.ev.length && tau >= h.ev[h.ke].i) disparar(h.ev[h.ke++]);
    const s = h.segs;
    while (h.k < s.length - 1 && tau >= s[h.k + 1].i) h.k++;
    // (lo ya dicho no hace falta: en una voz larga sin texto, la lista no crece)
    if (h.k > 64) { s.splice(0, 48); h.k -= 48; }
    if (h.ke > 64) { h.ev.splice(0, 48); h.ke -= 48; }
    const sg = s[h.k];
    if (!sg) { bocaP[0] = 0; bocaP[1] = 1; bocaP[2] = 1; return bocaP; }
    if (tau >= sg.i + sg.d) {
      // se terminó lo que tenía que decir: cierra la boca (60 ms)
      bocaSeg(sg, 1, bocaQ);
      const b = suave(((tau - sg.i - sg.d) * h.f) / 0.06);
      bocaP[0] = bocaQ[0] * (1 - b); bocaP[1] = bocaQ[1] + (1 - bocaQ[1]) * b; bocaP[2] = bocaQ[2] + (1 - bocaQ[2]) * b;
      return bocaP;
    }
    bocaSeg(sg, (tau - sg.i) / sg.d, bocaP);
    const prev = h.k > 0 ? bocaSeg(s[h.k - 1], 1, bocaQ) : h.antes;
    const b = suave(((tau - sg.i) * h.f) / 0.035);
    if (b < 1) for (let i = 0; i < 3; i++) bocaP[i] = prev[i] + (bocaP[i] - prev[i]) * b;
    bocaP[0] = Math.min(sg.cap ?? ABRIR_MAX, bocaP[0]);
    return bocaP;
  }
  // La boca en la sílaba `s` en `u` (0 a 1 de lo que dura): los labios cerrados el primer 42 % si empieza con p, b o m;
  // si empieza con otra consonante, desde algo cerrada; la vocal; y al final cae un poco hacia la siguiente
  function bocaSeg(s, u, out) {
    if (!s || s.pausa) { out[0] = 0; out[1] = 1; out[2] = 1; return out; }
    const cae = 1 - 0.18 * suave((u - 0.62) / 0.38);
    if (s.B) {
      if (u < 0.42) { out[0] = 0; out[1] = 0.95; out[2] = 1; return out; }
      const e = suave((u - 0.42) / 0.2);
      out[0] = s.a * e * cae; out[1] = 0.95 + (s.w - 0.95) * e; out[2] = 1 - e;
      return out;
    }
    out[0] = s.a * (s.C ? 0.35 + 0.65 * suave(u / 0.3) : 1) * cae; out[1] = s.w; out[2] = 0;
    return out;
  }
  // Sin texto (o la voz siguió después del texto): sílabas al azar un poco por delante de lo que dice, con una pausa de
  // 0.2 s cada 5–9 y un golpe cada tanto en alguna tónica; la boca abre a lo sumo 0.65
  function generar(h, tau) {
    let fin = Math.max(h.fin, tau);
    while (fin < tau + 0.3) {
      if (h.cuenta >= h.proxPausa) {
        h.segs.push({ i: fin, d: 0.2, pausa: true });
        fin += 0.2;
        h.cuenta = 0;
        h.proxPausa = 5 + Math.floor(azar() * 5);
        continue;
      }
      const r = azar(), v = r < 0.3 ? 'a' : r < 0.6 ? 'e' : r < 0.8 ? 'o' : r < 0.9 ? 'i' : 'u';
      const B = azar() < 0.18, C = B || azar() < 0.7, tonica = azar() < 0.33, d = 0.09 + azar() * 0.12;
      const [a0, w] = VISEMAS[v];
      h.segs.push({ i: fin, d, a: Math.min(ABRIR_GENERADOR, a0 * (tonica ? 1.3 : 1) * (0.85 + 0.3 * azar())), w, B, C, tonica, vocal: v, cap: ABRIR_GENERADOR });
      if (tonica && fin - h.golpeGen >= 0.9 + azar() * 1.1) {
        h.golpeGen = fin;
        h.ev.push({ i: fin + (B ? 0.45 : 0.25) * d - 0.12, tipo: 'golpe', amp: 0.6 + 0.4 * azar() });
      }
      h.cuenta++;
      fin += d;
    }
    h.fin = fin;
  }
  function disparar(e) {
    if (e.tipo === 'cejas') cejasPico = Math.max(cejasPico, e.amp);
    else if (e.tipo === 'golpe') golpeDeHabla(e.amp);
  }
  // ¿El brazo `l` está libre del gesto? (para hablar con él)
  const libre = (l) => !clip || !clip.qPose[`hombro${l}`] || pesoArt(`hombro${l}`) < 0.3;
  /** Un golpe del habla (en la tónica de una palabra clave; al menos 0.5 s entre uno y otro): la mano que manda (si el
   * gesto la ocupa, la otra) baja en 0.12 s con los dedos que se cierran un poco y vuelve en 0.25 s; la cabeza cabecea,
   * las cejas suben y los ojos se entrecierran un poco. Cada 3–4 golpes la mano cambia de forma */
  function golpeDeHabla(f = 1) {
    if (t - ultimoGolpe < 0.5) return;
    ultimoGolpe = t;
    golpesHabla++;
    cejasPico = Math.max(cejasPico, 0.3);
    entrePulso = Math.max(entrePulso, 0.1);
    golpe('cabeza', 0, 0.05 * f, 0.12, 0.25);
    const dom = domD > 0.5 ? 'D' : 'I';
    // (un gesto que acompaña lo que dice, explicar, deja que el habla golpee con su mano: `batuta`)
    const bat = (x) => clip?.batuta === true || clip?.batuta === x;
    const l = libre(dom) || bat(dom) ? dom : libre(otro(dom)) || bat(otro(dom)) ? otro(dom) : null;
    if (l && wHabla > 0.3 && !reducido) {
      golpe(`codo${l}`, 0, 0.13 * f, 0.12, 0.25);
      golpe(`muneca${l}`, 0, 0.07 * f, 0.12, 0.25);
      golpe(`hombro${l}`, 0, 0.03 * f, 0.12, 0.25);
      dedosGolpe[l].t0 = t;
      dedosGolpe[l].f = f;
      // (el gesto de las dos manos, explicar: cada 2–3 golpes la otra también, un poco después y más chico; si no, la
      // otra mano quedaba quieta toda la frase)
      if (clip?.batutaOtra && ++golpesOtra >= cadaOtra) {
        const o = otro(l);
        golpe(`codo${o}`, 0, 0.14 * f, 0.12, 0.25, t + 0.06);
        golpe(`muneca${o}`, 0, 0.07 * f, 0.12, 0.25, t + 0.06);
        golpesOtra = 0;
        cadaOtra = 2 + (azar() < 0.5 ? 1 : 0);
      }
    }
    if (++golpesForma >= cadaForma) {
      formaHabla = (formaHabla + 1) % FORMAS_HABLA.length;
      golpesForma = 0;
      cadaForma = 3 + (azar() < 0.5 ? 1 : 0);
    }
  }

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
    if (p.modo === 'recorre') {
      // (1.2 s la obra y 1.1 s la sala: más tiempo mirando la obra, la cara queda fuera de la sala; de lado y hacia abajo)
      const ciclo = Math.floor(tau / 2.3), fase = tau - 2.3 * ciclo;
      if (ciclo !== p.ciclo) { p.ciclo = ciclo; p.asintio = false; }
      if (fase >= 1.2) return false;
      // salta entre puntos de la obra (alrededor del suyo) y a la mitad asiente
      if (tau >= p.proxSalto) { p.ofs.set((azar() * 2 - 1) * 0.5, (azar() * 2 - 1) * 0.2, 0); p.proxSalto = tau + 0.5 + azar() * 0.3; }
      if (fase >= 0.6 && !p.asintio) { p.asintio = true; golpe('cabeza', 0, 0.05, 0.15, 0.3); golpe('cuello', 0, 0.02, 0.15, 0.3); }
      return true;
    }
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
  // un golpe del clip: llega en `ida` (cada vez más rápido), se queda `sosten` s y vuelve en `vuelta`
  function golpeEn(g, tau) {
    const d = tau - g.t, ida = g.ida ?? 0.12, vuelta = g.vuelta ?? 0.25, sosten = g.sosten ?? 0;
    if (d < 0 || d > ida + sosten + vuelta) return 0;
    return d < ida ? g.amp * (d / ida) ** 2 : d < ida + sosten ? g.amp : g.amp * (1 - (d - ida - sosten) / vuelta) ** 2;
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
        clipCara = clip.cara ? caraEn(clip.cara, tClip) : null;
        // (los parpadeos del gesto: la espera quieta de la pregunta, el primer asentimiento)
        const pp = clip.parpadeos;
        if (pp && clip.kParpadeo < pp.length && tClip >= pp[clip.kParpadeo]) { clip.kParpadeo++; if (enParpadeo < 0 && t - ultimoParpadeo > 0.3) parpadear(); }
      }
    }

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
      wMedio += ((api.plano === 'medio' ? 1 : 0) - wMedio) * acercar(8, dt);
      const de = qCasas[casaDe] || qCasas.junta, a = qCasas[casaA] || qCasas.junta;
      if (u < 1 || casaA !== 'junta' || wMedio > 0.001) {
        const deM = qCasasMedio[casaDe] || qCasasMedio.junta, aM = qCasasMedio[casaA] || qCasasMedio.junta;
        for (const j of Object.keys(a)) {
          objetivo[j].copy(de[j]).slerp(a[j], u);
          if (wMedio > 0.001) objetivo[j].slerp(tmpQ.copy(deM[j]).slerp(aM[j], u), wMedio);
        }
      }
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
      pesoEf = (pesoReposo() + (wCad ? (enTiempo(clip.cuerpo.peso, tClip) - pesoReposo()) * wCad : 0)) * (1 - wCaminar);
      // la pelvis cae del lado de la pierna libre y la columna lo compensa: la cabeza queda derecha
      sumar('cadera', 0, 0, -0.04 * pesoEf);
      sumar('columna', 0, 0, 0.026 * pesoEf);
      sumar('pecho', 0, 0, 0.012 * pesoEf);
      sumar('cuello', 0, 0, 0.006 * pesoEf);
      // la respiración (4 s: inspira en 1.6, espira en 2.4): el pecho sube y los hombros se abren (sosteniendo un gesto,
      // se nota más)
      const fr = t % 4, r = ((fr < 1.6 ? suave(fr / 1.6) : 1 - suave((fr - 1.6) / 2.4)) - 0.5) * (1 + 0.6 * vivoAntes);
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

    // ── hablar: lo que dice (la boca por sílabas y sus golpes) y la casa de hablar, debajo del gesto (lo que el gesto no
    // usa habla): asimétrica, la mano que manda (la derecha, o la que el gesto deja libre) más alta y con su forma, la
    // otra más baja; con el plano medio, las dos más arriba (el corte va más alto). Una pregunta: la cabeza ladeada ──
    if (hablando && t > finHabla) { hablando = false; vozPlan = null; terminarFrase(); }
    const boca = hablando && habla ? avanzarHabla() : null;
    wHabla += ((hablando && wCaminar < 0.3 ? 1 : 0) - wHabla) * acercar(2.4, dt);
    domD += ((!libre('D') && libre('I') ? 0 : 1) - domD) * acercar(4, dt);
    if (wHabla > 0.01) {
      const fh = FORMAS_HABLA[formaHabla], medio = api.plano === 'medio' ? 1 : 0;
      for (const l of LADOS) {
        const alto = l === 'D' ? domD : 1 - domD;
        for (const f of ['hombro', 'codo', 'muneca']) {
          const a = HABLA.alta[f], b = HABLA.baja[f];
          const e = tmpE;
          for (let i = 0; i < 3; i++) e[i] = b[i] + (a[i] - b[i]) * alto;
          if (f === 'codo') e[1] += (fh.giro - a[1]) * alto;
          if (medio && f !== 'muneca') e[0] += HABLA.medio[f];
          objetivo[`${f}${l}`].slerp(qDe(`${f}${l}`, e, tmpQ2), wHabla);
        }
      }
      if (ladeo) sumar('cabeza', 0, 0, ladeo * wHabla);
    }

    // ── el gesto encima: cada articulación con su retraso, desde lo que pedía el gesto anterior (o desde la casa) ──
    let altoCadera = 0, torsion = 0;   // (lo que el gesto gira el torso: la mirada lo descuenta)
    if (clip) {
      const c = clip;
      // el brazo que apunta sigue apuntando al punto con el pecho como esté ahora
      const ap = c.apuntaA;
      if (ap) ap.puntos.forEach(([pt], k) => {
        if (!c.aim[k]?.length) return;
        qDe(`hombro${ap.lado}`, apuntar(ap.lado, pt, ap.bajar, ap.pose, ap.forma, ap.tope), tmpQ3);
        for (const qq of c.aim[k]) qq.copy(tmpQ3);
      });
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
          if (!c.cuerpo[j]) continue;
          const v = enTiempo(c.cuerpo[j], tClip - c.ret[j]);
          const w = pesoArt(j);
          if (w > 0) { sumar(j, v[0] * w, v[1] * w, v[2] * w); torsion += v[1] * w; }
        }
        altoCadera = (enTiempo(c.cuerpo.alto, tClip) || 0) * pesoArt('cadera');
      }
      // sostenido, sigue vivo: a los 6–7 s afloja (las manos un poco más bajas), se mueve apenas (±0.03 rad, 0.2 Hz),
      // asiente despacio cada 2.5–4 s y hace su acento cada 4–6 s
      let vivo = 0;
      if (c.sostener && !reducido && tClip > c.entrado) {
        vivo = suave(tClip - c.entrado) * wClip;
        const wr = suave((tClip - c.tRelaja) / 1.2) * wClip;
        relajaEstado = wr;
        if (wr > 0) for (const j in c.qRelaja) objetivo[j].slerp(c.qRelaja[j], wr);
        c.articulaciones.forEach((j, k) => {
          const f0 = c.semilla + 13.7 * k;
          sumar(j, 0.03 * vivo * ruido(t * 0.2 + f0), 0, 0.03 * vivo * ruido(t * 0.2 + f0 + 41.3));
        });
        if (tClip >= c.proxAsiente) {
          golpe('cabeza', 0, 0.045, 0.3, 0.5);
          golpe('cuello', 0, 0.02, 0.3, 0.5);
          c.proxAsiente = tClip + 2.5 + azar() * 1.5;
        }
        if (c.acento && tClip >= c.proxAcento) acentoDe(c);
      } else relajaEstado = 0;
      vivoAntes = vivo;
      // el vaivén de antes (con movimiento reducido, solo la cabeza: asentir y negar)
      for (const [j, eje, amp, frec, d0, d1] of c.osc || []) {
        if (tClip < d0 || tClip > d1 || (reducido && j !== 'cabeza' && j !== 'cuello')) continue;
        const env = suave((tClip - d0) / 0.25) * (1 - suave((tClip - (d1 - 0.25)) / 0.25));
        const v = amp * env * Math.sin(2 * Math.PI * frec * (tClip - d0)) * wClip;
        sumar(j, eje === 0 ? v : 0, eje === 1 ? v : 0, eje === 2 ? v : 0);
      }
      // los vaivenes y los golpes nuevos, después del muelle (su forma es la que se ve)
      if (!reducido) for (const v of c.vaivenes) sumarExtra(v.art, v.eje, vaivenEn(v, tClip) * wClip);
      // (`golpesCallado`: los suyos solo callado; hablando, los golpes los pone el habla en sus palabras clave)
      if (!(c.golpesCallado && hablando)) for (const g of c.golpes || []) sumarExtra(g.art, g.eje, golpeEn(g, tClip) * wClip);
    } else {
      if (desde) { desde = null; desdeManos = null; }
      vivoAntes = 0;
      relajaEstado = 0;
    }
    for (const j of ARTICULACIONES) trasClip[j].copy(objetivo[j]);
    // los impulsos sueltos (los golpes del habla, el asentimiento al terminar una frase, los acentos), después del muelle
    for (let k = sueltos.length - 1; k >= 0; k--) {
      const g = sueltos[k], d = t - g.t0;
      if (d > g.ida + g.vuelta) { sueltos.splice(k, 1); continue; }
      if (d >= 0) sumarExtra(g.art, g.eje, d < g.ida ? g.amp * (d / g.ida) ** 2 : g.amp * (1 - (d - g.ida) / g.vuelta) ** 2);
    }

    // ── hacia dónde mira: la sala si se lo pidieron (mirarSala), el punto del gesto (según su plan), el de mirarA o
    // la cámara ──
    const aLaSala = t < salaHasta;
    let punto = null;
    if (!aLaSala && clip && wClip > 0.3 && clip.mirar && miraClip(clip, tClip)) {
      punto = clip.plan?.ofs ? miraOfs.copy(clip.mirar).add(clip.plan.ofs) : clip.mirar;
      miraModo = 'gesto';
    }
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
    // mirando a la sala mientras el gesto apunta a algo, la cara se queda un poco hacia eso (`resto`): el torso sigue
    // abierto a lo que muestra
    if (miraModo === 'sala' && clip?.mirar && clip.resto && wClip > 0.3) {
      tmpV.copy(clip.mirar);
      grupo.worldToLocal(tmpV);
      const yp = Math.atan2(tmpV.x, Math.max(0.05, tmpV.z));
      yawObj += lim(yp - yawObj, -clip.resto, clip.resto) * wClip;
    }
    // hablando a la sala, la mirada deriva por la sala: se queda 2–4 s en una «persona» y salta a otra (±0.12); un gesto
    // que espera a la sala (invitar, sostenido) la recorre aunque no hable (`deriva`: {amp, cada})
    const dg = clip?.deriva && wClip > 0.5 ? clip.deriva : null;
    if ((hablando || dg) && !reducido && miraModo === 'sala') {
      if (t >= proxDeriva) {
        const amp = dg?.amp ?? 0.12, [c0, c1] = dg?.cada || [2, 4];
        // (recorriendo la sala, cada vez del otro lado)
        deriva = dg ? (deriva > 0 ? -1 : 1) * amp * (0.6 + 0.4 * azar()) : (azar() * 2 - 1) * amp;
        derivaP = (azar() * 2 - 1) * 0.03; proxDeriva = t + c0 + azar() * (c1 - c0);
      }
      yawObj += deriva;
      pitchObj += derivaP;
    } else if (deriva || derivaP) { deriva = 0; derivaP = 0; proxDeriva = t + 0.5; }
    // un giro grande de la mirada lleva un parpadeo
    if (Math.abs(yawObj - yawAntes) > 0.5 && enParpadeo < 0 && t - ultimoParpadeo > 0.4) parpadear();
    yawAntes = yawObj;
    if (!reducido) yawObj += 0.04 * ruido(t * frecRuido[0] + 7.3);
    // la apertura: la cara nunca se aparta de la sala más que `apertura` (el rumbo del cuerpo más el giro de la mirada);
    // lo que falta lo hacen los ojos. En 3/4, nunca de perfil. Con el rumbo de ahora y con el que va (girando, la cabeza
    // no se adelanta a lo que el cuerpo todavía no giró: después tendría que desenroscarse tarde)
    {
      const ap = Math.max(0.1, Number(api.apertura) || 0.55);
      const lo = Math.max(-ap - rumbo, -ap - rumboBase), hi = Math.max(lo, Math.min(ap - rumbo, ap - rumboBase));
      const recortado = Math.max(lo, Math.min(hi, yawObj));
      yawOjos = Math.max(-1, Math.min(1, (yawObj - recortado) * 1.6));
      yawObj = recortado;
    }
    hT[hI] = t; hY[hI] = yawObj; hP[hI] = pitchObj; hI = (hI + 1) % HIST;
    // los ojos ya; la cabeza y el cuello 0.1 s después; la columna y la cadera, 0.2 s. Hacia arriba la cabeza sube a lo
    // sumo 0.13 rad y el resto lo hacen los ojos (la cabeza muy alzada, en 3/4, perdía la línea de la mandíbula: la cara
    // y el cuello en un solo bloque, un muñeco sobre un palo)
    const [yC, pC0] = miradaDe(0.1), pC = Math.min(pC0, CABEZA_ARRIBA);
    // (el torso que gira con el gesto no se lleva la cara: el cuello y la cabeza lo descuentan)
    sumar('cuello', -pC * 0.35, yC * 0.3 - 0.5 * torsion, 0);
    sumar('cabeza', -pC * 0.55, yC * 0.4 - 0.5 * torsion, 0);
    {
      const [yT, pT0] = miradaDe(0.2), pT = Math.min(pT0, CABEZA_ARRIBA);
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
      if (e[0] || e[1] || e[2]) {
        // (en los brazos, lo que dobla en x va antes del resto: es sumarlo al ángulo x del hueso, el de doblar)
        if (BRAZOS.has(j)) {
          if (e[0]) huesos[j].quaternion.premultiply(qDe(j, [e[0], 0, 0], tmpQ));
          if (e[1] || e[2]) huesos[j].quaternion.multiply(qDe(j, [0, e[1], e[2]], tmpQ));
        } else huesos[j].quaternion.multiply(qDe(j, e, tmpQ));
      }
    }
    // la apertura, de verdad: si el cuerpo gira (o camina) mientras mira a un costado, la cabeza (que lo sigue con su
    // muelle) quedaría un momento más girada de lo permitido: se la endereza lo justo, alrededor de la vertical
    {
      const ap = Math.max(0.1, Number(api.apertura) || 0.55) + 0.02;
      huesos.cabeza.updateWorldMatrix(true, false);
      tmpV.set(0, 0, 1).transformDirection(huesos.cabeza.matrixWorld);
      const yaw = Math.atan2(tmpV.x, tmpV.z);
      if (Math.abs(yaw) > ap) {
        tmpM.extractRotation(huesos.cabeza.parent.matrixWorld).invert();
        tmpV2.set(0, 1, 0).applyMatrix4(tmpM).normalize();
        huesos.cabeza.quaternion.premultiply(tmpQ.setFromAxisAngle(tmpV2, Math.sign(yaw) * ap - yaw));
      }
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
      // (el saltito de un gesto: `salto` true, o {t, dur, alto}: cuándo despega, lo que está en el aire y lo que sube)
      const sj = clip?.salto === true ? { t: 0.35, dur: 0.5, alto: 0.12 } : clip?.salto || null;
      if (sj && !reducido) salto = tClip > sj.t ? Math.max(0, Math.sin(Math.min(1, (tClip - sj.t) / sj.dur) * Math.PI)) * sj.alto : 0;
      else salto *= 1 - acercar(10, dt);
      if (grupo.visible) cuerpo.position.y = yQuieto + salto;
    }
    // la pelvis: hacia la pierna de apoyo, lo que sube o baja el gesto, un poco más baja caminando y el asentamiento
    // al frenar; las piernas alcanzan los pies (y si no llegan, la cadera baja lo justo)
    const wPies = 1 - wAg;
    huesos.cadera.position.set(cadera0.x - 0.02 * pesoEf, cadera0.y + altoCadera - 0.018 * wCaminar
      - 0.012 * Math.sin(Math.PI * Math.min(1, asiento / 0.4)), cadera0.z);
    apoyar(wPies);

    // ── las manos: la forma del gesto (los dedos un poco después que la muñeca; el acento del sostenido), la del gesto
    // anterior mientras este entra, la de hablar (la que manda con su forma, la otra relajada) o la de la casa; en un
    // golpe del habla, los dedos se cierran un poco ──
    const pesoDedos = clip ? Math.max(0, entrando(clip, tClip - clip.retDedos)) * saliendo(clip, tClip - clip.retDedosSale) : 0;
    const tDedos = clip ? tClip - clip.retDedos : 0;
    for (const l of LADOS) {
      let forma = MANOS.relajada;
      const m = clipManos?.[l];
      if (m && pesoDedos > 0.15) {
        for (const [tt, f] of m) if (tDedos >= tt) forma = f;
        const am = clip.acentoManos, sq = am?.manos[l];
        if (sq && tClip - am.t0 >= 0 && tClip - am.t0 <= sq[sq.length - 1][0] + 0.4) for (const [tt, f] of sq) if (tClip - am.t0 >= tt) forma = f;
      } else if (desdeManos?.[l] && (m || pesoDedos < 0.5)) forma = desdeManos[l];
      else if (wHabla > 0.3) forma = MANOS[(l === 'D') === (domD > 0.5) ? FORMAS_HABLA[formaHabla].mano : 'relajada'];
      else { const n = suave((t - tCasa) / 0.9) > 0.5 ? casaA : casaDe; if (CASAS_MANOS[n]?.[l]) forma = MANOS[CASAS_MANOS[n][l]]; }
      const gd = t - dedosGolpe[l].t0;
      if (gd >= 0 && gd < 0.37) {
        const g = dedosGolpe[l].f * (gd < 0.12 ? (gd / 0.12) ** 2 : (1 - (gd - 0.12) / 0.25) ** 2);
        forma = forma.map((x, i) => (i < 4 ? Math.min(1, x + 0.15 * g) : x));
      }
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
    // la boca: hablando, la de la sílaba de ahora (con los labios que se cierran en la p, la b y la m, y en las pausas);
    // callado, la sonrisa de la foto con los dientes de arriba (los labios entreabiertos: LABIOS_REPOSO), salvo lo que
    // pida o abra el gesto. La sonrisa en reposo, cálida
    const minAbrir = (clipCara?.abrir || 0) * wClip;
    if (boca) {
      abrir = Math.max(boca[0], minAbrir);
      ancho = boca[1];
      labios = clipCara?.labios !== undefined ? boca[2] + (clipCara.labios - boca[2]) * wClip : minAbrir > 0.02 ? Math.min(boca[2], 0.3) : boca[2];
    } else {
      abrir += (minAbrir - abrir) * acercar(26, dt);
      // (lo ancho de la boca que pida el gesto: «¡así de grande!», más redonda)
      ancho += ((clipCara?.ancho !== undefined ? 1 + (clipCara.ancho - 1) * wClip : 1) - ancho) * acercar(20, dt);
      const labiosLibre = minAbrir > 0.02 ? 0 : LABIOS_REPOSO;
      const labiosObj = clipCara?.labios !== undefined ? labiosLibre + (clipCara.labios - labiosLibre) * wClip : labiosLibre;
      labios += (labiosObj - labios) * acercar(12, dt);
    }
    const sonrisaLibre = hablando ? 1 : SONRISA_REPOSO;
    const sonrisaObj = clipCara?.sonrisa !== undefined ? sonrisaLibre + (clipCara.sonrisa - sonrisaLibre) * wClip : sonrisaLibre;
    sonrisa += (sonrisaObj - sonrisa) * acercar(6, dt);
    // (la boca redonda, la o y la u del habla o el «¡así de grande!», estira menos las comisuras)
    const redonda = Math.max(0, 1 - ancho);
    cara.boca.poner({ abrir, ancho, sonrisa: Math.max(0, Math.min(1, sonrisa - 0.12 * abrir - 0.6 * redonda)), labios: Math.max(0, Math.min(1, labios)) });
    // las cejas: un pico que decae (la primera tónica de la frase y las cifras, un golpe, un gesto) y lo del gesto, cada
    // una por su lado (`cejasI`, `cejasD`: una más alta que la otra al pensar o al preguntar)
    cejasPico *= 1 - acercar(2.2, dt);
    for (let i = 0; i < 2; i++) {
      const delClip = clipCara ? clipCara[i === 0 ? 'cejasI' : 'cejasD'] ?? clipCara.cejas ?? 0 : 0;
      cejasL[i] += (Math.max(cejasPico, delClip * wClip * 0.8) - cejasL[i]) * acercar(10, dt);
    }
    const cenoObj = (clipCara?.ceno || 0) * wClip;
    ceno += (cenoObj - ceno) * acercar(8, dt);
    cara.cejas.forEach((c, i) => c.poner({ alza: cejasL[i] ?? cejasL[0], ceno }));
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
    // los párpados: entrecerrados lo que pida el gesto (y un poco en cada golpe del habla), el de arriba más bajo mirando
    // abajo; el de abajo sube con la sonrisa (los ojos de Duchenne cuando sonríe de verdad: con los dientes); y el guiño
    entrePulso *= 1 - acercar(4, dt);
    entrecierra += (Math.min(1, (clipCara?.entrecierra || 0) * wClip + entrePulso) - entrecierra) * acercar(12, dt);
    const duch = clipCara && (clipCara.duchenne ?? ((clipCara.sonrisa ?? 1) >= 0.85 && (clipCara.labios === 0 || (clipCara.abrir || 0) > 0.05)));
    duchenne += ((duch ? wClip : 0) - duchenne) * acercar(6, dt);
    const ojoSonrisa = lim(0.85 - 0.25 * abrir + 0.1 * (sonrisa - 1) + 0.15 * duchenne, 0, 1);
    // (`cierra`: los ojos que se cierran un momento: de sonrisa al celebrar, al apoyar la mano en el pecho)
    cierra += ((clipCara?.cierra || 0) * wClip - cierra) * acercar(14, dt);
    const abre = parpado * (1 - 0.3 * entrecierra) * (1 - 0.25 * Math.max(0, -ojoY)) * (1 - lim(cierra, 0, 0.95));
    const g = clipCara?.guino, gLado = typeof g === 'object' && g ? g.lado : g;
    const cierraGuino = gLado ? 0.8 * formaGuino(tClip - (g?.t ?? 0.35)) * wClip : 0;
    cara.ojos.forEach((o, i) => o.poner({ abierto: abre * (gLado === (i === 0 ? 'I' : 'D') ? 1 - cierraGuino : 1), sonrisa: ojoSonrisa, mira: [ojoX, ojoY] }));
  }
  // el guiño: cierra en 60 ms, se queda y abre en 120 ms (0.25 s en total)
  const formaGuino = (u) => (u < 0 || u > 0.25 ? 0 : u < 0.06 ? suave(u / 0.06) : u < 0.13 ? 1 : 1 - suave((u - 0.13) / 0.12));
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
    m.dedos.forEach(([b, p], i) => {
      b.rotation.set(ABRE[i] * (1 - v[i]), 0, -1.5 * v[i]);
      p.rotation.set(0, 0, -1.3 * v[i]);
    });
    m.ponerPulgar(v[4]);
  }

  /** Lo que está haciendo (para el taller y las pruebas). `cara`: hacia dónde mira la cara respecto de la sala (el
   * rumbo del cuerpo más el giro de la cabeza, en radianes; nunca más que la apertura). `peso`: la pierna de apoyo (−1
   * la I … 1 la D); `pies`: cuál está dando un paso; `vivo`: cuántos cambios de peso, saltos de los ojos y parpadeos
   * lleva; `mirada`: qué mira ('sala', 'gesto' o 'punto'). `ritmo`: el de la voz (lo que tarda de verdad respecto de lo
   * estimado); `habla`: lo que dice (con texto o sin él, con voz, cuántos golpes, la forma de la mano que manda);
   * `relajada`: cuánto aflojó el sostenido (0 a 1); `variante`: la del gesto; `chica`: los gestos de dedos por la silueta */
  const fwd = new THREE.Vector3();
  const r3 = (v) => Math.round(v * 1000) / 1000;
  function estado() {
    return { gesto: nombreClip, sostenido: !!clip?.sostener, hablando, caminando: Math.abs(destinoX - grupo.position.x) > 0.01,
      x: grupo.position.x, visible: grupo.visible, entrando: entrada?.tipo || null,
      rumbo: r3(rumbo), rumboBase: r3(rumboBase), aLaSala: t < salaHasta,
      agachado: r3(Math.max(0, Math.min(1, -cuerpo.position.y / hondo))), hondo,
      peso: r3(pesoEf), casa: casaA, mirada: miraModo, pies: { I: !!pies.I.vuelo, D: !!pies.D.vuelo },
      vivo: { pesos: cambiosPeso, sacadicos, parpadeos },
      ritmo: r3(ritmo), relajada: r3(relajaEstado), variante: clip?.variante ?? null, chica: !!api.chica, chico: !!clip?.chico,
      soltando: !!clip?.soltando, soloCara: !!clip?.soloCara,
      habla: hablando && habla ? { texto: habla.texto, voz: habla.voz, golpes: golpesHabla, mano: FORMAS_HABLA[formaHabla].mano,
        manda: domD > 0.5 ? 'D' : 'I' } : null,
      boca: { abrir: r3(abrir), labios: r3(labios), sonrisa: r3(sonrisa) },
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

  /** Lo que mide en la pantalla (px del personaje entero) y si es el celular: con la cabeza de menos de 70 px, los gestos
   * de dedos se reemplazan por los que se leen por la silueta (lo llama el presentador al cambiar de vista) */
  function tamano(pxAlto, o = {}) {
    api.chica = !!o?.celular || (Number.isFinite(pxAlto) && pxAlto > 0 && 0.312 * pxAlto < 70);
    return api.chica;
  }
  /** El acento del gesto sostenido, ya (los dos toques de la mano que indica en cada frase que sigue hablando de eso) */
  function acentuar() {
    if (!clip?.acento || reducido) return false;
    acentoDe(clip);
    return true;
  }
  /** Las cejas arriba un momento (lo que cambió: el panel de otro capítulo) */
  function alzarCejas(v = 0.6) { cejasPico = Math.max(cejasPico, lim(Number(v) || 0, 0, 1)); }
  /** La reacción a lo que pasó en el modelo (la simulación terminó: «sigue en servicio»): las cejas arriba y un
   * asentimiento, sin dejar el gesto que hace */
  function reaccionar(v = 0.6) {
    alzarCejas(v);
    golpe('cabeza', 0, 0.06, 0.14, 0.3, t + 0.15);
    golpe('cuello', 0, 0.025, 0.14, 0.3, t + 0.15);
  }

  return Object.assign(api, { actualizar, gesto, detenerGesto, hablar, callar, mirarA, mirarSala, caminarA, reubicar, entrar,
    salir, agacharse, asomarse, estado, girar, casa, tamano, acentuar, alzarCejas, reaccionar });
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
