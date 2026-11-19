// Las vistas del presentador (docs/presentador.md): qué plano toma, dónde se para y hacia dónde se orienta según lo que
// se está explicando. Módulo puro, sin THREE ni DOM: presentador.js le pasa lo que sabe de la escena (lo que trae
// `narrar`) y las cajas que leyó de la página, y las pruebas lo usan con Node.
//
// * PLANOS: la ventana vertical del personaje que se ve y la altura a la que lo corta el borde de arriba del
//   subtítulo («el atril»), en fracciones de su alto.
// * VISTAS: siete maneras de estar (anfitrión, señala, presenta, general, cerca, rótulo y busto), cada una con su plano,
//   su tamaño, su rumbo y su lugar preferido.
// * elegirVista(d, ctx): las reglas, en orden (la primera que se cumple decide): lo resaltado manda (señala), después
//   la obra pedida (presenta), después el tipo de paso; con superposiciones (la bienvenida, el gesto de cara a la sala,
//   el cambio de capítulo).
// * lugares / elegirLugar: dónde se para a lo largo del subtítulo, con un puntaje que castiga tapar la obra, sus
//   rótulos, lo resaltado, el HUD y la leyenda, y descarta tapar el panel, la ficha o el marco del atlas; con
//   histéresis (no va y viene) y a lo sumo un cambio por escena.
// * objetivoDe, alcance: el punto al que apunta y hasta dónde llega la punta del índice.
// * transicion: cómo pasa de una vista a otra (girar, acercarse, caminar, saltar, el rótulo, fundirse).
// * tiemposCierre: cuándo empieza cada punto del resumen (un dedo por punto).

/** Los planos: [yb, ya] la ventana del personaje que se ve, yc el corte (el borde de arriba del subtítulo) y `ancho`
 * el del lienzo, todo en fracciones del alto del personaje (pxAlto). Lo que queda bajo el corte no se ve */
export const PLANOS = {
  entero: { yb: 0, ya: 1.1, yc: 0.05, ancho: 1.05 },        // los pies apenas detrás del subtítulo
  americano: { yb: 0.26, ya: 1.1, yc: 0.37, ancho: 1.1 },   // de la cadera para arriba: el subtítulo es el atril
  medio: { yb: 0.4, ya: 1.08, yc: 0.46, ancho: 1.2 },       // de la cintura para arriba
  primer: { yb: 0.52, ya: 1.06, yc: null, ancho: 1 },       // la cabeza y los hombros, en un círculo (el rótulo)
};

/** Medio ancho del cuerpo en el corte (·pxAlto, con el contorno): tiene que quedar sobre el subtítulo. Y la huella, lo
 * que tapa arriba del corte (medio ancho y alto) */
const CORTE = { entero: 0.1, americano: 0.12, medio: 0.15, primer: 0.15 };
const HUELLA = { entero: [0.2, 0.95], americano: [0.22, 0.74], medio: [0.3, 0.62], primer: [0.3, 0.62] };
/** Los gestos que abren los brazos a los costados: hasta dónde llega la figura desde el centro del cuerpo (·pxAlto,
 * medido con el personaje en el americano). El panel, la ficha y el atlas tampoco se tapan con ellos */
export const ENVERGADURA = { grande: 0.42, celebrar: 0.4, invitar: 0.39, comparar: 0.38, saludar: 0.35, despedirse: 0.33,
  crecer: 0.27, preguntar: 0.25, explicar: 0.24 };

/**
 * Las vistas. `k`, `min`, `max`: el tamaño (pxAlto = clamp(k·alto de la ventana, min, max)); `chica`: el de la pantalla
 * chica si cambia; `rumbo`: cuánto gira el cuerpo hacia lo que explica; `margen`: del extremo del subtítulo al cuerpo;
 * `apertura`: lo más que la cara se aparta de la sala.
 */
export const VISTAS = {
  anfitrion: { plano: 'americano', k: 0.36, min: 220, max: 400, rumbo: 0, margen: 0.2, apertura: 0.55 },
  senala: { plano: 'americano', k: 0.36, min: 220, max: 400, rumbo: 0.35, margen: 0.2, apertura: 0.55 },
  presenta: { plano: 'americano', k: 0.36, min: 220, max: 400, rumbo: 0.3, margen: 0.2, apertura: 0.55 },
  general: { plano: 'entero', k: 0.42, min: 250, max: 460, chica: [0.28, 160, 280], rumbo: 0.3, margen: 0.25, apertura: 0.55 },
  cerca: { plano: 'medio', k: 0.5, min: 280, max: 520, rumbo: 0, margen: 0.2, apertura: 0.55 },
  // (por ahora, un busto chico detrás del subtítulo: el círculo es de la etapa de las transiciones)
  rotulo: { plano: 'medio', k: 0.125, min: 88, max: 128, rumbo: 0.3, margen: 0.26, apertura: 0.45 },
  busto: { plano: 'medio', k: 0.26, min: 150, max: 240, rumbo: 0.25, margen: 0.26, apertura: 0.5 },
};
/** La pantalla chica (el celular, la tableta vertical): el busto en lugar del anfitrión, señala, presenta y cerca */
export const CHICA_PX = 1080;
export const HORIZONTAL_PX = 520;
/** El largo del brazo, del hombro a la punta del índice estirado (·pxAlto; medido con el personaje: 0.361·alto) */
export const BRAZO = 0.36;
/** El hombro: a qué altura del personaje y a qué distancia del centro del cuerpo (·pxAlto; sobre el corte del
 * americano queda a 0.221) */
export const HOMBRO = { y: 0.591, lado: 0.126 };

const acotar = (v, a, b) => Math.min(b, Math.max(a, v));

/** Los giros del movimiento suave del recorrido (= recorrido.GIROS_SUAVES de app/recorrido.py: una prueba los compara) */
export const GIROS_SUAVES = [10, 12, 14];
/** ¿Es el movimiento suave que el recorrido pone solo (girar unos grados, sin elevación)? Ese no es «obra pedida» */
export const esSuave = (m) => !!m && Number.isInteger(m.giro) && GIROS_SUAVES.includes(Math.abs(m.giro)) && m.elevacion == null;
/** ¿Queda un modelo del atlas a la vista (o cargando)? */
export const atlasVisible = (d, ctx) => !!d.atlas || d.simular?.modelo === 'atlas' || ((d.evento || 'narrar') !== 'narrar' && !!ctx?.dom?.conInmersion);
/** ¿La escena pide la obra (la cámara a algo, partes, hoy/proyecto, una simulación en la maqueta, un movimiento que no es
 * el suave, un gesto hacia la maqueta)? `animar` no cuenta: la automática lo manda en todas */
export function obraExplicita(d, anterior) {
  const v = d.visual || {};
  const mismoPaso = !!anterior && anterior.capitulo === d.capitulo && anterior.paso === d.paso;
  const comparoAntes = mismoPaso ? anterior.visual?.comparar ?? 'proyecto' : 'proyecto';
  return !!(v.enfoque || v.mirar || (v.camara && v.camara !== 'paso') || v.rumbo != null || v.elevacion != null
    || v.zoom != null || v.aislar || v.sin?.length || v.mostrar?.length || v.ocultar?.length || v.girar
    || (v.comparar && v.comparar !== comparoAntes) || d.simular?.modelo === 'maqueta'
    || (d.mover && !esSuave(d.mover))
    || ['presentar', 'mirar_maqueta', 'grande', 'construir', 'detalle'].includes(d.gesto));
}

/** Los gestos que se hacen de cara a la sala: la vista no cambia, pero el cuerpo mira de frente mientras duran */
export const DE_FRENTE = ['saludar', 'invitar', 'celebrar', 'aplaudir', 'juntos', 'corazon', 'preguntar', 'asentir',
  'negar', 'calmar', 'aprobar', 'pensar', 'explicar', 'destacar', 'crecer'];
// lo resaltado que vive en el panel
const DEL_PANEL = ['cifra', 'punto', 'componente'];
// la primera frase pregunta o niega («¿por qué…?», «hoy no hay…»): la portadilla empieza pensando
const PREGUNTA_O_NIEGA = /[¿?]|\b(hoy no|no hay|no tiene|no existe|nunca|ningun[oa]?|ningún)\b/i;
// las metas que crecen: «→», «meta», «de 120 a 300»
const CRECE = /→|\bmetas?\b|\bde\s+\S+(?:\s+\S+){0,3}\s+a\s+\d/i;

/**
 * elegirVista(d, ctx) → {vista, lado, objetivo, gesto, frente, transicionCapitulo, saludoPrimero, saludoCorto, regla}.
 * - d: lo que trae `narrar` (docs/presentador.md) más `d.evento` ('narrar' | 'cierre' | 'preguntas' | 'preparando' |
 *   'explicar' | 'pausa').
 * - ctx: {chica, VW, VH, horizontal, nuevo (recién sube), reducido, dom: {conInmersion, conDetalle, sinPanel},
 *   anterior: {capitulo, paso, visual, vista, lado}}.
 * `lado`: dónde está lo que explica ('panel' | 'ficha' | 'leyenda' | 'obra' | 'marco' | 'hoja' | 'arriba' | 'sala');
 * `objetivo`: a qué apunta ('foco' | 'bloque' | 'obra' | 'marco' | 'ficha' | 'sala'); `gesto`: el que pidió el asistente
 * o el de la vista; `frente`: el gesto va de cara a la sala; `regla`: la que decidió.
 */
export function elegirVista(d = {}, ctx = {}) {
  d = d || {};
  const dom = ctx.dom || {};
  const ev = d.evento || 'narrar';
  const escena = ev === 'narrar';
  const chica = ctx.chica ?? (ctx.VW ? ctx.VW <= CHICA_PX : false);
  const horizontal = ctx.horizontal ?? (chica && ctx.VH ? ctx.VH < HORIZONTAL_PX : false);
  const r = escena ? d.resaltar || null : null;
  const v = d.visual || {};
  const pedido = escena ? d.gesto || null : null;
  // la ficha abierta y el panel oculto: lo que pide la escena (lo visual de una escena es entero) o lo que hay
  const conFicha = escena && d.visual ? !!v.detalle : !!dom.conDetalle;
  const sinPanel = escena && d.panel !== undefined ? d.panel === false : !!dom.sinPanel;
  const atlas = atlasVisible(d, ctx);

  const base = (() => {
    const de = (vista, lado, objetivo, gesto, regla, extra = {}) => ({ vista, lado, objetivo, gesto, regla, ...extra });
    if (horizontal) return de('rotulo', atlas ? 'marco' : 'sala', atlas ? 'marco' : 'sala', null, 'R1');
    if (atlas) return de('rotulo', 'marco', 'marco', null, 'R2');
    if (chica && conFicha) return de('rotulo', 'ficha', 'ficha', null, 'R3');
    if (ev === 'cierre' || ev === 'preguntas') return de(chica ? 'busto' : 'cerca', 'sala', 'sala', ev === 'cierre' ? 'contar' : 'invitar', 'cierre', { cierre: true });
    if (ev === 'preparando') return de('anfitrion', 'sala', 'sala', 'pensar', 'preparando');
    if (ev === 'explicar') return de('anfitrion', 'sala', 'sala', 'explicar', 'explicar');
    if (ev === 'pausa') {
      const a = ctx.anterior || {};
      return de(a.vista || 'anfitrion', a.lado || 'sala', a.objetivo || 'sala', 'escuchar', 'pausa', { frente: true });
    }
    const enPanel = r && (DEL_PANEL.includes(r.tipo) || (r.tipo === 'especificacion' && (r.en ?? 'panel') === 'panel'));
    if (!chica && r && (r.en === 'ficha' || r.tipo === 'leyenda')) return de('senala', r.tipo === 'leyenda' ? 'leyenda' : 'ficha', 'foco', pedido, 'R4');
    if (!chica && enPanel && !sinPanel) return de('senala', 'panel', 'foco', pedido, 'R5');
    if (chica && enPanel && !sinPanel) return de('busto', 'hoja', 'foco', pedido || 'destacar', 'R5c');
    if (chica && r?.tipo === 'leyenda') return de('busto', 'arriba', 'foco', pedido || 'senalar', 'R4c');
    if (!chica && conFicha && !r) return de('senala', 'ficha', 'ficha', pedido || 'presentar', 'R6');
    if (sinPanel) return de('general', 'obra', 'obra', pedido || 'presentar', 'R7');
    if (obraExplicita(d, ctx.anterior)) {
      const mismoPaso = ctx.anterior && ctx.anterior.capitulo === d.capitulo && ctx.anterior.paso === d.paso;
      const comparo = v.comparar && v.comparar !== (mismoPaso ? ctx.anterior.visual?.comparar ?? 'proyecto' : 'proyecto');
      const g = pedido || (comparo ? 'comparar' : v.aislar || v.sin?.length ? 'detalle' : 'presentar');
      return de('presenta', 'obra', 'obra', g, 'R8');
    }
    if ((pedido === 'senalar' || pedido === 'mostrar_panel') && !r) return de('senala', 'panel', 'bloque', pedido, 'R9');
    // por el tipo de paso (la presentación automática y los planes sin lo visual)
    const t = d.tipo;
    const primera = String(d.textos?.[0] ?? '');
    if (t === 'portada') return d.n === 1 ? de('anfitrion', 'sala', 'obra', pedido || 'presentar', 'R10') : de('anfitrion', 'sala', 'sala', pedido || 'explicar', 'R10');
    if (t === 'portadilla') {
      if (d.cambio) return de('anfitrion', 'sala', 'sala', pedido || (PREGUNTA_O_NIEGA.test(primera) ? 'pensar' : 'explicar'), 'R10');
      return de('presenta', 'obra', 'obra', pedido || 'mirar_maqueta', 'R10');
    }
    if (t === 'componentes' || t === 'componente' || t === 'inmersion') return de('presenta', 'obra', 'obra', pedido || 'presentar', 'R10');
    if (t === 'comparacion') return de('senala', 'panel', 'bloque', pedido || 'comparar', 'R10');
    if (t === 'metas') return de('senala', 'panel', 'bloque', pedido || ((d.textos || []).some((x) => CRECE.test(x)) ? 'crecer' : 'mostrar_panel'), 'R10');
    if (t === 'cronograma') return de('senala', 'panel', 'bloque', pedido || 'presentar', 'R10');
    if (t === 'texto' && d.lista > 0) return de('senala', 'panel', 'bloque', pedido || 'enumerar', 'R10');
    if (t === 'texto') return de('anfitrion', 'sala', 'sala', pedido || 'explicar', 'R10');
    return de('anfitrion', 'sala', 'sala', pedido || 'explicar', 'R11');
  })();

  // en la pantalla chica, el anfitrión, señala, presenta y cerca son el busto
  if (chica && ['anfitrion', 'senala', 'presenta', 'cerca'].includes(base.vista)) {
    base.vista = 'busto';
    if (base.lado === 'panel') base.lado = 'hoja';
  }
  // O2: el gesto de cara a la sala
  base.frente = base.frente || DE_FRENTE.includes(base.gesto);
  // O3: el cambio de capítulo (el panel cambió de color y de contenido): lo mira antes del gesto
  base.transicionCapitulo = escena && d.cambio === 'capitulo' && base.vista !== 'rotulo';
  // O1: la bienvenida (recién sube en la primera escena): saluda y después pasa a la vista; si la escena ya trae un
  // dato resaltado, un saludo corto para no demorar el señalar
  base.saludoPrimero = escena && !!ctx.nuevo && d.n === 1 && base.vista !== 'rotulo';
  base.saludoCorto = base.saludoPrimero && !!r;
  if (base.saludoPrimero && base.gesto === 'saludar') base.gesto = null;   // es el mismo saludo
  base.gesto = base.gesto || null;
  return base;
}

/** El tamaño de la vista para la ventana: {plano, p (pxAlto), Wc, Hc, bajo (lo del lienzo detrás del subtítulo), alto
 * (lo que se ve arriba del corte), margen, cadera, huella: [medio ancho, alto]}. `cierre`: el busto del cierre ×1.15 */
export function medidas(vista, ctx = {}, { cierre = false, subAlto = 0 } = {}) {
  const V = VISTAS[vista] || VISTAS.anfitrion;
  const VW = ctx.VW || 800, VH = ctx.VH || 600;
  const chica = ctx.chica ?? VW <= CHICA_PX;
  const P = PLANOS[V.plano];
  let p;
  if (vista === 'rotulo') {
    // el tamaño del círculo (lo que se ve: 0.62 de pxAlto en el plano medio)
    const horizontal = ctx.horizontal ?? (chica && VH < HORIZONTAL_PX);
    const lado = horizontal ? acotar((subAlto || 56) - 6, 44, 64) : chica ? 64 : acotar(V.k * VH, V.min, V.max);
    p = lado / (P.ya - P.yc);
  } else if (chica && V.chica) p = acotar(V.chica[0] * VH, V.chica[1], V.chica[2]);
  else p = acotar(V.k * VH, V.min, V.max);
  if (vista === 'busto' && cierre) p *= 1.15;
  p = Math.round(p * 10) / 10;
  const Wc = Math.round(vista === 'busto' || vista === 'rotulo' ? Math.min(P.ancho * p, 0.7 * VW) : P.ancho * p);
  return {
    vista, plano: V.plano, p, Wc, Hc: Math.round((P.ya - P.yb) * p), bajo: Math.round((P.yc - P.yb) * p),
    alto: (P.ya - P.yc) * p, yc: P.yc, margen: V.margen * p, cadera: CORTE[V.plano] * p,
    huella: [HUELLA[V.plano][0] * p, HUELLA[V.plano][1] * p], apertura: V.apertura,
  };
}

/** El rumbo de la vista hacia un punto que está en `dx` (px, + a la derecha de la pantalla) del cuerpo */
export function rumboDe(vista, dx, frente = false) {
  const V = VISTAS[vista] || VISTAS.anfitrion;
  if (frente || !V.rumbo || !Number.isFinite(dx) || Math.abs(dx) < 4) return 0;
  return Math.sign(dx) * V.rumbo;
}
/** Dónde va el cuerpo en el ancho del lienzo: al centro de frente; corrido al lado contrario del brazo que se extiende */
export const cxDe = (rumbo) => (rumbo > 0.01 ? 0.38 : rumbo < -0.01 ? 0.62 : 0.5);

// ── Cajas ──
const area = (b) => (b ? Math.max(0, b.x1 - b.x0) * Math.max(0, b.y1 - b.y0) : 0);
const corte = (a, b) => (a && b ? { x0: Math.max(a.x0, b.x0), y0: Math.max(a.y0, b.y0), x1: Math.min(a.x1, b.x1), y1: Math.min(a.y1, b.y1) } : null);
const cruza = (a, b, tol = 0) => !!a && !!b && a.x0 < b.x1 - tol && a.x1 > b.x0 + tol && a.y0 < b.y1 - tol && a.y1 > b.y0 + tol;
/** Una caja {x0, y0, x1, y1} de un DOMRect ({left, top, right, bottom}) o de lo que ya lo sea; null si no tiene área */
export function caja(r) {
  if (!r) return null;
  const b = 'x0' in r ? { x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1 } : { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom };
  return [b.x0, b.y0, b.x1, b.y1].every(Number.isFinite) && b.x1 > b.x0 && b.y1 > b.y0 ? b : null;
}
export const union = (cs) => cs.filter(Boolean).reduce((a, b) => (a ? { x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) } : { ...b }), null);

/** La zona libre donde se encuadra la obra (la cuenta de zonaPx de escena.js, con las cajas de la página) */
export function zonaLibre(c, VW, VH) {
  let x0 = 0, x1 = VW, y0 = 0, y1 = VH;
  if (c.leyenda) { if (c.leyenda.y0 > VH / 2) y1 = Math.min(y1, c.leyenda.y0 - 8); else y0 = Math.max(y0, c.leyenda.y1 + 6); }
  if (c.barra) y0 = Math.max(y0, c.barra.y1 + 6);
  if (c.control) y1 = Math.min(y1, c.control.y0 - 6);
  if (c.panel) { if (c.panel.x1 - c.panel.x0 < VW * 0.7) x0 = Math.max(x0, c.panel.x1 + 16); else y1 = Math.min(y1, c.panel.y0 - 8); }
  if (c.sub) y1 = Math.min(y1, c.sub.y0 - 8);
  if (c.ficha && c.ficha.x1 - c.ficha.x0 < VW * 0.6) x1 = Math.min(x1, c.ficha.x0 - 16);
  if (x1 - x0 < VW * 0.25) { x0 = 0; x1 = VW; }
  if (y1 - y0 < 90) y1 = Math.min(VH, y0 + 90);
  return { x0, y0, x1, y1 };
}

/**
 * El punto (px de la ventana) al que apunta la vista: `objetivo` y `lado` de elegirVista; `c`, las cajas (foco: la del
 * .foco, o su unión; panel, ficha, leyenda, marco, obra, sub…); `yHombro`, la altura del hombro. null: la sala
 */
export function objetivoDe(objetivo, lado, c, { yHombro, VW, VH } = {}) {
  const y = (b, a = 6) => acotar(Number.isFinite(yHombro) ? yHombro : (b.y0 + b.y1) / 2, b.y0 + Math.min(a, (b.y1 - b.y0) / 2), b.y1 - Math.min(a, (b.y1 - b.y0) / 2));
  const centro = (b) => (b ? { x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2 } : null);
  if (objetivo === 'foco' && c.foco) {
    if (lado === 'panel') return { x: c.foco.x1, y: y(c.foco) };
    if (lado === 'ficha' || lado === 'leyenda') return { x: c.foco.x0, y: y(c.foco) };
    return centro(c.foco);
  }
  if (objetivo === 'bloque' && c.panel) {
    const b = c.panel;
    return { x: b.x1 - 40, y: acotar(Number.isFinite(yHombro) ? yHombro : (b.y0 + b.y1) / 2, b.y0 + Math.min(80, (b.y1 - b.y0) / 2), b.y1 - Math.min(40, (b.y1 - b.y0) / 2)) };
  }
  if (objetivo === 'obra') {
    const z = zonaLibre(c, VW || 800, VH || 600);
    const o = c.obra ? corte(c.obra, z) : null;
    return centro(o && area(o) > 0 ? o : z);
  }
  if (objetivo === 'marco') return centro(c.marco);
  if (objetivo === 'ficha') return centro(c.ficha);
  if (objetivo === 'foco' && c.leyenda && lado === 'leyenda') return { x: c.leyenda.x0, y: y(c.leyenda) };
  return null;
}

/** La altura del hombro en la pantalla (px) con el corte en `subTop` */
export const yHombro = (subTop, { p, yc = PLANOS.americano.yc }) => subTop - (HOMBRO.y - yc) * p;

/**
 * Hasta dónde llega la punta del índice si se para en `x` y apunta a `punto` (px de la ventana): el hombro del lado
 * del punto y el brazo de largo `BRAZO` hacia el punto (a lo sumo hasta el punto). → {hombro, punta, u}
 */
export function alcance(x, punto, { p, subTop, rumbo = 0, yc = PLANOS.americano.yc }) {
  const s = punto && punto.x < x ? -1 : 1;
  const hombro = { x: x + s * HOMBRO.lado * p * Math.cos(rumbo), y: yHombro(subTop, { p, yc }) };
  if (!punto) return { hombro, punta: hombro, u: { x: 0, y: 0 } };
  const dx = punto.x - hombro.x, dy = punto.y - hombro.y, n = Math.hypot(dx, dy) || 1;
  const u = { x: dx / n, y: dy / n };
  const largo = Math.min(BRAZO * p, n);
  return { hombro, punta: { x: hombro.x + u.x * largo, y: hombro.y + u.y * largo }, u };
}
/** Lo que se extiende el brazo en x desde el cuerpo (px), hacia `punto` */
export const alcanceX = (x, punto, o) => Math.abs(alcance(x, punto, o).punta.x - x);
/**
 * El punto al que conviene apuntar para señalar `punto` sin que la punta del dedo baje del corte (lo de abajo no se ve):
 * si la recta del hombro al punto la dejaría a menos de `margen` (8) px del borde de arriba del subtítulo, se levanta
 * lo justo
 */
export function apuntable(x, punto, o) {
  const a = alcance(x, punto, o);
  const margen = o.margen ?? 8;
  if (!punto || a.punta.y <= o.subTop - margen) return punto;
  const L = BRAZO * o.p;
  const uy = Math.max(-1, Math.min(1, (o.subTop - margen - a.hombro.y) / L));
  const ux = Math.sign(a.u.x || 1) * Math.sqrt(1 - uy * uy);
  const d = Math.hypot(punto.x - a.hombro.x, punto.y - a.hombro.y);
  return { x: a.hombro.x + ux * d, y: a.hombro.y + uy * d };
}

// los pesos del puntaje: cuánto cuesta tapar cada cosa (el panel, la ficha y el marco no se tapan nunca)
const PESOS = { obra: 1, rotulo: 2, foco: 3, hud: 3, leyenda: 3 };
const CON_BRAZO = ['senala', 'presenta', 'general'];

/** La huella del cuerpo parado en `x` (lo que tapa arriba del corte) */
export function huella(x, m, subTop) {
  return { x0: x - m.huella[0], y0: subTop - m.huella[1], x1: x + m.huella[0], y1: subTop };
}

/** El lugar preferido de la vista (px de la ventana) con el subtítulo `sub`: el anfitrión al centro, el cierre en el
 * primer tercio, el busto (y todo en la pantalla chica) a la derecha; señala, del lado de lo que señala (el alcance lo
 * corre lo justo); presenta, el general y el rótulo, a la izquierda (el tercio que deja el panel) */
export function preferido(vista, m, ctx, sub, punto = null) {
  const chica = ctx.chica ?? (ctx.VW || 800) <= CHICA_PX;
  const centro = (sub.x0 + sub.x1) / 2;
  if (vista === 'anfitrion' && !chica) return centro;
  if (vista === 'cerca' && !chica) return sub.x0 + 0.33 * (sub.x1 - sub.x0);
  if (vista === 'busto' || chica) return sub.x1 - m.margen;
  if (vista === 'senala' && punto && punto.x > centro) return sub.x1 - m.margen;
  return sub.x0 + m.margen;
}

// Lo que el puntaje necesita una vez por elección: las cajas que no se tapan, las que cuestan y el preferido
function preparar(e, m, ctx, c, punto) {
  const VW = ctx.VW || 800;
  const sub = c.sub;
  const blandos = [];
  // con la obra que se desborda (la cámara «cerca»), cuenta lo que queda en la zona libre
  const zona = zonaLibre(c, VW, ctx.VH || 600);
  const obra = c.obra ? corte(c.obra, zona) : null;
  // [caja, peso, cuenta el brazo, por su propia área]: la obra cuesta por lo que tapa de la huella; un rótulo o lo
  // resaltado, por lo que se tapa de ellos (chicos: medidos sobre la huella no costarían nada)
  if (obra && area(obra) > 0) blandos.push([obra, PESOS.obra, true]);
  for (const r of c.rotulos || []) blandos.push([r, PESOS.rotulo, true, true]);
  if (c.foco) blandos.push([c.foco, PESOS.foco, false, true]);
  if (c.hud) blandos.push([c.hud, PESOS.hud, true]);
  if (c.leyenda && e.lado !== 'leyenda') blandos.push([c.leyenda, PESOS.leyenda, true]);
  const lo = sub.x0 + m.margen, hi = sub.x1 - m.margen;
  // lo que señala: la punta del índice no entra ahí (el vidrio del panel, la ficha o la leyenda)
  const senalado = e.lado === 'panel' ? c.panel : e.lado === 'ficha' ? c.ficha || c.foco : e.lado === 'leyenda' ? c.leyenda || c.foco : null;
  const abre = Math.max(m.huella[0], m.p * Math.max(ENVERGADURA[e.gesto] || 0, e.saludoPrimero ? ENVERGADURA.saludar : 0));
  return { e, m, VW, sub, punto, blandos, duros: [c.panel, c.ficha, c.marco].filter(Boolean), lo, hi, abre,
    pref: preferido(e.vista, m, ctx, sub, punto), conBrazo: CON_BRAZO.includes(e.vista) && !!punto,
    senala: e.vista === 'senala' && !!punto, senalado };
}
// El costo de pararse en `x` y lo que no cumple (razon: [] si cumple todo)
function puntuar(P, x) {
  const { e, m, sub, punto } = P;
  const h = huella(x, m, sub.y0);
  const razon = [];
  if (h.x0 < 6 || h.x1 > P.VW - 6) razon.push('pantalla');
  if (x - m.cadera < sub.x0 + 8 || x + m.cadera > sub.x1 - 8) razon.push('cadera');
  // (con los brazos abiertos del gesto: tampoco)
  if (P.duros.some((b) => cruza({ ...h, x0: x - P.abre - 6, x1: x + P.abre + 6 }, b))) razon.push('tapa');
  let a = null;
  if (P.conBrazo) {
    a = alcance(x, punto, { p: m.p, subTop: sub.y0, rumbo: rumboDe(e.vista, punto.x - x), yc: m.yc });
    if (P.senala) {
      const t = a.punta, b = P.senalado;
      if (b && punto.x < x && t.x < b.x1 + 6) razon.push('alcance');
      if (b && punto.x > x && t.x > b.x0 - 12) razon.push('alcance');
      if (t.y > sub.y0 - 8) razon.push('corte');   // lo de abajo del corte no se ve
    }
  }
  const ah = area(h) || 1;
  const g = 0.04 * m.p;
  const brazo = a ? { x0: Math.min(a.hombro.x, a.punta.x) - g, y0: Math.min(a.hombro.y, a.punta.y) - g, x1: Math.max(a.hombro.x, a.punta.x) + g, y1: Math.max(a.hombro.y, a.punta.y) + g } : null;
  let costo = 0;
  for (const [b, w, conBrazo, propia] of P.blandos) {
    if (!propia) {
      costo += (w * area(corte(h, b))) / ah;
      // el brazo, con la mitad del peso (no sobre lo que señala)
      if (brazo && conBrazo) costo += (0.5 * w * area(corte(brazo, b))) / ah;
      continue;
    }
    // un rótulo o lo resaltado: poco si se tapa un poco; mucho pasado el 30 % (lo que ya no se lee)
    const f = Math.min(1, (area(corte(h, b)) + (brazo && conBrazo ? 0.5 * area(corte(brazo, b)) : 0)) / (area(b) || 1));
    costo += w * (0.5 * f + 4 * Math.max(0, f - 0.25));
  }
  // lejos del preferido cuesta poco (señalando, más: lo más cerca que deje el alcance)
  costo += ((P.senala ? 1 : 0.15) * Math.abs(x - P.pref)) / (Math.max(40, P.hi - P.lo) + 1);
  // señalando algo a la altura de la mano: la punta del dedo, a no más de 60 px (después, cuanto más lejos, peor)
  if (P.senala && a && Math.abs(punto.y - a.hombro.y) <= 120) costo += Math.max(0, Math.hypot(a.punta.x - punto.x, a.punta.y - punto.y) - 60) / 100;
  return { x, costo: Math.round(costo * 1e4) / 1e4, razon, punta: a ? { x: Math.round(a.punta.x), y: Math.round(a.punta.y) } : null };
}

/**
 * Los lugares posibles para la vista `e` (de elegirVista; `m` = sus medidas) y su costo (menor es mejor), con las cajas
 * `c` de la página (sub, panel, ficha, marco, leyenda, hud, obra, rotulos, foco…) y `punto` (a lo que apunta, si apunta).
 * Candidatos: cada 40 px a lo largo del subtítulo (señalando, cada 8) y los tres de siempre (en la pantalla chica, solo
 * los extremos). Los que no cumplen lo duro (dentro de la pantalla, la cadera sobre el subtítulo, sin tapar el panel,
 * la ficha ni el marco; señalando, la punta del dedo fuera de lo que señala y arriba del corte) no están (con `todos`,
 * sí, con su `razon`). → [{x, costo, razon, punta}], el mejor primero
 */
export function lugares(e, m, ctx, c, { punto = null, todos = false } = {}) {
  if (!c.sub) return [];
  const chica = ctx.chica ?? (ctx.VW || 800) <= CHICA_PX;
  const P = preparar(e, m, ctx, c, punto);
  const xs = new Set();
  if (chica) { xs.add(Math.round(c.sub.x1 - m.margen)); xs.add(Math.round(c.sub.x0 + m.margen)); }
  else {
    // cada 40 px (señalando, cada 8: lo más cerca que deje el alcance)
    for (let x = P.lo; x <= P.hi; x += P.senala ? 8 : 40) xs.add(Math.round(x));
    for (const x of [P.lo, (c.sub.x0 + c.sub.x1) / 2, P.hi, P.pref]) xs.add(Math.round(x));
  }
  const lista = [...xs].map((x) => puntuar(P, x));
  const orden = (a, b) => a.costo - b.costo || Math.abs(a.x - P.pref) - Math.abs(b.x - P.pref);
  return (todos ? lista : lista.filter((l) => !l.razon.length)).sort(orden);
}

/**
 * El lugar de la escena: el mejor de `lugares`, salvo que el de ahora (`actual.x`) siga cumpliendo todo y no sea mucho
 * peor (histéresis: costo ≤ 1.25·mejor + 0.02, con lo que señala del mismo lado). A lo sumo un cambio por escena
 * (`actual.cambios`) y ninguno en una escena corta (`actual.ms` < 3500: solo gira), salvo que el de ahora ya no cumpla
 * (la cadera en el aire, tapa el panel, la punta del dedo entraría en lo que señala). Sin ninguno que cumpla todo, el
 * que menos falla. → {x, cambia, costo, razon}
 */
export function elegirLugar(e, m, ctx, c, actual = {}, { punto = null } = {}) {
  if (!c.sub) return null;
  const todos = lugares(e, m, ctx, c, { punto, todos: true });
  const grave = (l) => l.razon.reduce((a, r) => a + ({ tapa: 100, cadera: 50, pantalla: 50, alcance: 10, corte: 5 }[r] || 1), 0);
  const mejor = todos.find((l) => !l.razon.length) || [...todos].sort((a, b) => grave(a) - grave(b) || a.costo - b.costo)[0] || null;
  const x = actual.x;
  if (!Number.isFinite(x)) return mejor ? { x: mejor.x, cambia: true, costo: mejor.costo, razon: 'primero' } : null;
  if (!mejor) return { x, cambia: false, costo: null, razon: 'sin_lugar' };
  const ahora = puntuar(preparar(e, m, ctx, c, punto), x);
  // (el de ahora que ya no cumple: la cadera en el aire, tapa el panel, la punta del dedo entraría en lo que señala)
  const valeAhora = !ahora.razon.length;
  if (valeAhora && (actual.cambios || 0) >= 1) return { x, cambia: false, costo: ahora.costo, razon: 'ya_cambio' };
  if (valeAhora && Number.isFinite(actual.ms) && actual.ms < 3500) return { x, cambia: false, costo: ahora.costo, razon: 'corta' };
  const mismoLado = !punto || Math.sign(punto.x - x) === Math.sign(punto.x - mejor.x);
  if (valeAhora && mismoLado && ahora.costo <= 1.25 * mejor.costo + 0.02) return { x, cambia: false, costo: ahora.costo, razon: 'se_queda' };
  if (Math.abs(mejor.x - x) < 3) return { x, cambia: false, costo: mejor.costo, razon: 'mismo' };
  return { x: mejor.x, cambia: true, costo: mejor.costo, razon: valeAhora ? 'mejor' : 'no_sirve' };
}

/**
 * Cómo pasa de una vista a otra. desde/hasta: {vista, plano, p, x}. → 'giro' (mismo lugar y plano: solo gira) |
 * 'acercar' (mismo lugar, otro plano o tamaño) | 'caminar' (otro lugar cerca, mismo plano) | 'saltar' (más lejos, u otro
 * plano y otro lugar) | 'rotulo' (de figura a rótulo o al revés) | 'fundido' (con movimiento reducido, todo lo que no es
 * girar)
 */
export function transicion(desde, hasta, { reducido = false, p = null } = {}) {
  if (!desde || !hasta) return 'giro';
  const otroLugar = Number.isFinite(desde.x) && Number.isFinite(hasta.x) && Math.abs(hasta.x - desde.x) >= 3;
  const otroPlano = desde.plano !== hasta.plano || Math.abs((desde.p || 0) - (hasta.p || 0)) > 0.5;
  if (!otroLugar && !otroPlano) return 'giro';
  if (reducido) return 'fundido';
  if ((desde.vista === 'rotulo') !== (hasta.vista === 'rotulo')) return 'rotulo';
  if (!otroLugar) return 'acercar';
  const lejos = Math.abs(hasta.x - desde.x) > 0.8 * (p || hasta.p || desde.p || 300);
  return !otroPlano && !lejos ? 'caminar' : 'saltar';
}

/** Lo que tarda en decirse un carácter sin voz (a unos 17 por segundo; el de presentador.js) */
export const DECIR_S = 0.058;
/**
 * Cuándo empieza cada punto del resumen («En resumen. p1. p2. p3»), en segundos desde que empieza a hablar, y lo que
 * dura todo (el tope y el mínimo de decirS reparten en proporción). → {inicios: [s], total}
 */
export function tiemposCierre(puntos = []) {
  const largo = (t) => [...String(t)].length;
  const inicios = [];
  let t = largo('En resumen. ');
  for (const p of puntos) { inicios.push(t); t += largo(`${p}. `); }
  const crudo = Math.max(1, t - 2);   // (el último punto no lleva «. »)
  const total = Math.min(16, Math.max(1.2, crudo * DECIR_S));
  const k = total / (crudo * DECIR_S);
  return { inicios: inicios.map((x) => Math.round(x * DECIR_S * k * 1000) / 1000), total: Math.round(total * 1000) / 1000 };
}
