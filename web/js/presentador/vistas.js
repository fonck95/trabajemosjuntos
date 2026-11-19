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
// * lugares / elegirLugar: dónde se para a lo largo del subtítulo, con un puntaje que castiga tapar la obra, sus rótulos
//   (el título y la caja entera), lo resaltado, el HUD y la leyenda (medido con la silueta: la cabeza y el torso), y
//   descarta tapar el panel, la ficha o el marco del atlas; señalando, el dedo tiene que llegar (o quedar lo más cerca
//   que se pueda); si desde ningún lugar que deje leer los rótulos llega, desde lejos: la mano abierta hacia el borde de
//   lo que explica, sin taparlos ni caer sobre uno; con histéresis (no va y viene, ni se mueve por poco) y a lo sumo un
//   cambio por escena.
// * comoSenala, abierta, manoAbierta: si el dedo llega, está muy arriba o lejos, y adónde va la mano abierta.
// * objetivoDe, alcance: el punto al que apunta y hasta dónde llega la punta del índice.
// * rotuloDe / posRotulo: el rótulo (la cara en un círculo), bajo el panel o acoplado al subtítulo.
// * transicion: cómo pasa de una vista a otra (girar, acercarse, caminar, saltar, el rótulo, fundirse).
// * tiemposCierre: cuándo empieza cada punto del resumen (un dedo por punto).

/** Los planos: [yb, ya] la ventana del personaje que se ve, yc el corte (el borde de arriba del subtítulo) y `ancho`
 * el del lienzo, todo en fracciones del alto del personaje (pxAlto). Lo que queda bajo el corte no se ve */
export const PLANOS = {
  entero: { yb: 0, ya: 1.1, yc: 0.05, ancho: 1.05 },        // los pies apenas detrás del subtítulo
  americano: { yb: 0.26, ya: 1.1, yc: 0.37, ancho: 1.1 },   // de la cadera para arriba: el subtítulo es el atril
  // de la cadera para arriba (medio largo): el corte bajo las manos de la casa, que se ven enteras (con el corte en la
  // cintura asomaban dos muñones) y con ellas lo que hacen a la altura del pecho (invitar, calmar, escuchar)
  medio: { yb: 0.34, ya: 1.08, yc: 0.4, ancho: 1.2 },
  primer: { yb: 0.52, ya: 1.06, yc: null, ancho: 1 },       // la cabeza y los hombros, en un círculo (el rótulo)
};

/** Medio ancho del cuerpo en el corte (·pxAlto, con el contorno): tiene que quedar sobre el subtítulo. Y la huella, lo
 * que tapa arriba del corte (medio ancho y alto) */
const CORTE = { entero: 0.1, americano: 0.12, medio: 0.15, primer: 0.15 };
// (el alto, hasta lo más alto del pelo: medido, 0.633·pxAlto sobre el corte del americano)
const HUELLA = { entero: [0.2, 0.95], americano: [0.22, 0.64], medio: [0.3, 0.6], primer: [0.3, 0.62] };
/** La silueta, más fina que la huella: la cabeza (medio ancho 0.14·pxAlto, de lo más alto del pelo a 0.66 de su alto)
 * y, debajo, el torso con los brazos (el medio ancho de la huella) hasta el corte. Lo que tapa de un rótulo o de lo
 * resaltado se mide con ella: al costado de la cabeza un rótulo se lee */
const CABEZA = { ancho: 0.14, desde: 0.66, hasta: 1.0 };
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
  // la cara en un círculo (rotuloDe): bajo el panel (k, min, max: el diámetro) o acoplado al subtítulo (84 en la
  // pantalla grande, 64 en la chica; de lado, lo que da el alto del subtítulo)
  rotulo: { plano: 'primer', k: 0.125, min: 88, max: 128, acoplado: 84, chica: 64, rumbo: 0.3, margen: 0, apertura: 0.45 },
  busto: { plano: 'medio', k: 0.26, min: 150, max: 240, rumbo: 0.25, margen: 0.26, apertura: 0.5 },
};
// El busto en una pantalla alta: 0.16 del alto, hasta 360 px
const BUSTO_ALTO = { k: 0.16, max: 360 };
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
 *   anterior: {capitulo, paso, visual, vista, lado}, domManda (la ficha, el panel y el atlas: los de la página, no los
 *   de la escena)}.
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
  // la ficha abierta, el panel oculto y el atlas: lo que pide la escena (lo visual de una escena es entero) o lo que
  // hay; con `ctx.domManda` (lo que se ve cambió a mitad de la escena: «Solo 3D», la ficha o el atlas que abre una orden
  // `visual`), lo que hay
  const domManda = !!ctx.domManda;
  const conFicha = escena && d.visual && !domManda ? !!v.detalle : !!dom.conDetalle;
  const sinPanel = escena && d.panel !== undefined && !domManda ? d.panel === false : !!dom.sinPanel;
  const atlas = domManda ? !!dom.conInmersion : atlasVisible(d, ctx);

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
export function medidas(vista, ctx = {}, { cierre = false, subAlto = 0, rotulo = null } = {}) {
  const V = VISTAS[vista] || VISTAS.anfitrion;
  const VW = ctx.VW || 800, VH = ctx.VH || 600;
  const chica = ctx.chica ?? VW <= CHICA_PX;
  const P = PLANOS[V.plano];
  let p;
  if (vista === 'rotulo') {
    // el círculo: un lienzo cuadrado del diámetro, con la cabeza y los hombros (el plano primer, sin corte)
    const r = rotulo || rotuloDe(ctx, { sub: subAlto ? { x0: 0, y0: 0, x1: 1, y1: subAlto } : null });
    return { vista, plano: 'primer', p: Math.round((r.lado / (P.ya - P.yb)) * 10) / 10, Wc: r.lado, Hc: r.lado, bajo: 0,
      alto: r.lado, yc: null, margen: 0, cadera: 0, huella: [r.lado / 2, r.lado], apertura: V.apertura,
      modo: r.modo, borde: r.borde, lado: r.lado };
  }
  if (chica && V.chica) p = acotar(V.chica[0] * VH, V.chica[1], V.chica[2]);
  else p = acotar(V.k * VH, V.min, V.max);
  // (en una pantalla alta, la tableta parada: el busto crece con el alto hasta 360 px; con el tope de 240 quedaba chico
  // en la esquina, la cabeza en el 3.6 % del alto. En el celular, 0.16·alto no pasa de 240: no cambia)
  if (vista === 'busto') p = Math.max(p, acotar(BUSTO_ALTO.k * VH, V.min, BUSTO_ALTO.max));
  if (vista === 'busto' && cierre) p *= 1.15;
  p = Math.round(p * 10) / 10;
  const Wc = Math.round(vista === 'busto' || vista === 'rotulo' ? Math.min(P.ancho * p, 0.7 * VW) : P.ancho * p);
  return {
    vista, plano: V.plano, p, Wc, Hc: Math.round((P.ya - P.yb) * p), bajo: Math.round((P.yc - P.yb) * p),
    alto: (P.ya - P.yc) * p, yc: P.yc, margen: V.margen * p, cadera: CORTE[V.plano] * p,
    huella: [HUELLA[V.plano][0] * p, HUELLA[V.plano][1] * p], apertura: V.apertura,
  };
}

/**
 * Dónde va el rótulo (la cara en un círculo) con las cajas `c` de la página (sub, panel): en la pantalla grande, bajo el
 * panel si entre su borde de abajo y el del subtítulo cabe el círculo (en la esquina de abajo a la derecha de la columna
 * del panel: no tapa el modelo del atlas ni su barra de tiempo); si no, acoplado al subtítulo, en su extremo izquierdo
 * (el subtítulo le hace lugar: propuesta.html, .pres.rotulo-acoplado). En la pantalla chica, acoplado a la derecha;
 * de lado, del alto del subtítulo. `c.antes` ({modo, lado}): el rótulo que ya está (una seguidilla: no cambia con cada
 * panel). → {modo: 'panel' | 'acoplado', lado (el diámetro, px), borde: 'izq' | 'der'}
 */
export function rotuloDe(ctx = {}, c = {}) {
  const V = VISTAS.rotulo;
  const VW = ctx.VW || 800, VH = ctx.VH || 600;
  const chica = ctx.chica ?? VW <= CHICA_PX;
  const horizontal = ctx.horizontal ?? (chica && VH < HORIZONTAL_PX);
  const sub = c.sub || null;
  const alto = sub ? sub.y1 - sub.y0 : 0;
  if (horizontal) return { modo: 'acoplado', lado: Math.round(acotar((alto || 56) - 6, 44, V.chica)), borde: 'der' };
  if (chica) return { modo: 'acoplado', lado: V.chica, borde: 'der' };
  // (bajo el panel, si no cabe entero se achica hasta el mínimo)
  const lado = Math.round(acotar(V.k * VH, V.min, V.max));
  const cabe = c.panel && sub ? Math.floor(sub.y1 - (c.panel.y1 + 8)) : 0;
  // en una seguidilla de escenas con el rótulo (`c.antes`: el que está), el círculo no cambia con cada panel: acoplado
  // sigue acoplado; bajo el panel conserva su tamaño mientras quepa (si no, se achica lo justo o se acopla)
  const a = c.antes;
  if (a?.modo === 'acoplado') return { modo: 'acoplado', lado: V.acoplado, borde: 'izq' };
  if (a?.modo === 'panel' && cabe >= V.min) return { modo: 'panel', lado: Math.min(a.lado, cabe), borde: 'izq' };
  if (cabe >= V.min) return { modo: 'panel', lado: Math.min(lado, cabe), borde: 'izq' };
  return { modo: 'acoplado', lado: V.acoplado, borde: 'izq' };
}
/**
 * La caja del círculo en la ventana (px) con el subtítulo de ahora: bajo el panel, su borde derecho a 4 px del de la
 * columna del panel (`panelX1`) y el de abajo con el del subtítulo; acoplado, a 10 px del extremo del subtítulo (8 a la
 * derecha), centrado en su alto y nunca más alto que él (si el subtítulo es bajo, el círculo se achica: no lo pasa ni
 * tapa lo de arriba, la barra de tiempo del simulador). → {x0, y0, L}
 */
export function posRotulo(r, sub, panelX1 = null, { techo = null } = {}) {
  if (!r || !sub) return null;
  if (r.modo === 'panel' && Number.isFinite(panelX1)) return { x0: panelX1 - 4 - r.lado, y0: sub.y1 - r.lado, L: r.lado };
  const alto = sub.y1 - sub.y0;
  let L = Math.max(36, Math.min(r.lado, alto - 6));
  let y0 = (sub.y0 + sub.y1) / 2 - L / 2;
  // (`techo`: lo de arriba que el círculo no pisa —la ficha abierta en el celular de lado, que el subtítulo ya monta—:
  // baja hasta 4 px debajo y, si no entra, se achica, apoyado en el pie del subtítulo)
  if (Number.isFinite(techo) && y0 < techo + 4) {
    y0 = techo + 4;
    L = Math.max(36, Math.min(L, sub.y1 - 3 - y0));
    y0 = Math.min(y0, sub.y1 - 3 - L);
  }
  const x0 = r.borde === 'der' ? sub.x1 - 8 - L : sub.x0 + 10;
  return { x0, y0, L };
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

// los pesos del puntaje: cuánto cuesta tapar cada cosa (el panel, la ficha y el marco no se tapan nunca). De un rótulo
// de la maqueta, su título (el nombre: «La Soledad») y su caja entera (la línea de abajo: «a 27,6 km → · sede…»)
const PESOS = { obra: 1, rotulo: 2, caja: 1, foco: 3, hud: 3, leyenda: 3 };
const CON_BRAZO = ['senala', 'presenta', 'general'];
/** Señalando: el dedo «llega» si la punta queda a no más de LLEGA_PX de lo que señala. Si algún lugar llega, los que no
 * llegan no están; si ninguno llega, solo los que quedan a no más de 30 px de lo más cerca que se puede (pararse junto
 * al panel se lee como «esto del panel»), hasta LEJOS_PX; más lejos, desde lejos (a 200 px el índice cae sobre la
 * maqueta y se lee «esto de la maqueta»: la mano abierta hacia el panel) */
export const LLEGA_PX = 90;
const BANDA_PX = 30;
/** Lo más que se tapa de un rótulo de la maqueta y se sigue leyendo: el título (30 %) y la caja entera (30 %) */
export const TITULO_TAPADO = 0.3;
export const CAJA_TAPADA = 0.3;
export const CAJA_LEJOS = 0.1;
/** Más lejos que esto (la punta del índice estirado a lo que señala) el dedo no llega: desde ningún lugar que deje leer
 * los rótulos, «desde lejos» (abierta) */
export const LEJOS_PX = 120;
/** Lo señalado más de ALTO_PX arriba del hombro, al alcance, se señala con el índice (la palma alzada, sostenida, se
 * leería como una mano levantada) */
export const ALTO_PX = 150;
/** La distancia (px) de la punta del índice parado en `x` a `punto` (alcance) */
export const distPunta = (x, punto, o) => { const a = alcance(x, punto, o).punta; return punto ? Math.hypot(a.x - punto.x, a.y - punto.y) : 0; };
/**
 * Cómo señala `punto` parado en `x` (presentador.js): 'llega' (el índice y después la mano abierta), 'alto' (al alcance
 * pero más de ALTO_PX arriba del hombro: el índice sostenido) o 'lejos' (la punta del índice estirado a más de LEJOS_PX:
 * el índice en alto se leería como un dedo levantado o, sobre la maqueta, como «esto del mapa»; la mano abierta hacia
 * el borde de lo que explica, a la altura del hombro, `abierta`)
 */
export function comoSenala(x, punto, o) {
  if (!punto || !Number.isFinite(x)) return 'llega';
  if (distPunta(x, punto, o) > LEJOS_PX) return 'lejos';
  return yHombro(o.subTop, o) - punto.y > ALTO_PX ? 'alto' : 'llega';
}
/** Desde lejos, la mano abierta llega a MANO_ABIERTA·pxAlto del hombro (medido en indicar y presentar: la palma a 0.24,
 * la punta de los dedos a 0.29) y la recta del hombro a la mano no sube más de TOPE_ABIERTA (rad, ≈ 11°: el TOPE de
 * animador.js) */
export const MANO_ABIERTA = 0.27;
export const TOPE_ABIERTA = 0.2;
/** Lo que explica (`lado`), para la mano abierta: el panel, la ficha o la leyenda (o lo resaltado) */
const regionDe = (lado, c) => (lado === 'panel' ? c.panel || c.foco : lado === 'ficha' ? c.ficha || c.foco : lado === 'leyenda' ? c.leyenda || c.foco : c.foco) || null;
/**
 * Hacia dónde va la mano abierta desde lejos (px de la ventana): el borde de lo que explica que da al cuerpo parado en
 * `x`, a la altura del hombro `yH` (dentro de su alto, a 20 px de sus bordes). Se lee «allá, en el panel» y no apunta a
 * nada del mapa. null: sin eso
 */
export function abierta(lado, c, x, yH) {
  const b = regionDe(lado, c);
  if (!b || !Number.isFinite(x)) return null;
  const m = Math.min(20, (b.y1 - b.y0) / 2);
  return { x: x >= (b.x0 + b.x1) / 2 ? b.x1 : b.x0, y: acotar(Number.isFinite(yH) ? yH : (b.y0 + b.y1) / 2, b.y0 + m, b.y1 - m) };
}
/** La mano abierta parada en `x` hacia `destino` (abierta): {hombro, punta (la mano)}; nunca baja del corte */
export function manoAbierta(x, destino, { p, subTop, rumbo = 0, yc = PLANOS.americano.yc }) {
  const s = destino && destino.x < x ? -1 : 1;
  const hombro = { x: x + s * HOMBRO.lado * p * Math.cos(rumbo), y: yHombro(subTop, { p, yc }) };
  if (!destino) return { hombro, punta: hombro };
  const ang = Math.min(TOPE_ABIERTA, Math.atan2(hombro.y - destino.y, Math.abs(destino.x - hombro.x) || 1));
  const L = Math.min(MANO_ABIERTA * p, Math.hypot(destino.x - hombro.x, destino.y - hombro.y));
  return { hombro, punta: { x: hombro.x + s * L * Math.cos(ang), y: Math.min(subTop - 30, hombro.y - L * Math.sin(ang)) } };
}
/** Desde lejos, la mano abierta a menos de CERCA_PX de un rótulo de la maqueta se leería «esto de acá» (el puesto bajo el
 * rótulo, su anillo) */
const CERCA_PX = 60;
const distCaja = (q, b) => Math.hypot(Math.max(b.x0 - q.x, 0, q.x - b.x1), Math.max(b.y0 - q.y, 0, q.y - b.y1));
// la banda del alcance desde lejos: la mano abierta, a no más de esto más lejos del borde que desde el mejor lugar limpio
const BANDA_LEJOS = 0.45;

/** La huella del cuerpo parado en `x` (lo que tapa arriba del corte) */
export function huella(x, m, subTop) {
  return { x0: x - m.huella[0], y0: subTop - m.huella[1], x1: x + m.huella[0], y1: subTop };
}
/** La silueta del cuerpo parado en `x`: [torso, cabeza] (sin el plano, la huella entera) */
export function silueta(x, m, subTop) {
  const h = huella(x, m, subTop);
  if (!Number.isFinite(m.yc) || !m.p) return [h];
  const cuello = subTop - Math.max(0, CABEZA.desde - m.yc) * m.p;
  return [{ ...h, y0: Math.min(cuello, h.y1) },
    { x0: x - CABEZA.ancho * m.p, y0: subTop - (CABEZA.hasta - m.yc) * m.p, x1: x + CABEZA.ancho * m.p, y1: Math.min(cuello, h.y1) }];
}
const areaEn = (cs, b) => cs.reduce((a, k) => a + area(corte(k, b)), 0);

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
  // (de cada rótulo, el título y la caja entera: 'titulo' y 'caja')
  for (const r of c.rotulos || []) blandos.push([r, PESOS.rotulo, true, true, 'titulo']);
  for (const r of c.cajasRotulos || []) blandos.push([r, PESOS.caja, true, true, 'caja']);
  if (c.foco) blandos.push([c.foco, PESOS.foco, false, true]);
  if (c.hud) blandos.push([c.hud, PESOS.hud, true]);
  if (c.leyenda && e.lado !== 'leyenda') blandos.push([c.leyenda, PESOS.leyenda, true]);
  const senala = e.vista === 'senala' && !!punto;
  // señalando, hasta el extremo del subtítulo que deje la cadera sobre él (junto al panel, si queda lugar libre)
  const lo = senala ? sub.x0 + 9 + m.cadera : sub.x0 + m.margen, hi = senala ? sub.x1 - 9 - m.cadera : sub.x1 - m.margen;
  // lo que señala: la punta del índice no entra ahí (el vidrio del panel, la ficha o la leyenda)
  const senalado = e.lado === 'panel' ? c.panel : e.lado === 'ficha' ? c.ficha || c.foco : e.lado === 'leyenda' ? c.leyenda || c.foco : null;
  const abre = Math.max(m.huella[0], m.p * Math.max(ENVERGADURA[e.gesto] || 0, e.saludoPrimero ? ENVERGADURA.saludar : 0));
  // los rótulos de la maqueta, para la mano abierta desde lejos (que no caiga sobre uno)
  const marcas = (c.cajasRotulos?.length ? c.cajasRotulos : c.rotulos || []).filter(Boolean);
  return { e, m, VW, sub, punto, blandos, duros: [c.panel, c.ficha, c.marco].filter(Boolean), lo, hi, abre,
    pref: preferido(e.vista, m, ctx, sub, punto), conBrazo: CON_BRAZO.includes(e.vista) && !!punto,
    senala, senalado, c, marcas, lejos: false, banda: Infinity, hayLimpios: false };
}
/** ¿Deja leer los rótulos de la maqueta? (ningún título ni caja tapados más de lo que se lee; desde lejos, la caja no
 * más de CAJA_LEJOS: si el dedo no llega igual, no hay por qué tapar la línea de abajo) */
const limpio = (l, lejos = false) => l.titulo <= TITULO_TAPADO && l.caja <= (lejos ? CAJA_LEJOS : CAJA_TAPADA);
// El costo de pararse en `x` y lo que no cumple (razon: [] si cumple todo)
function puntuar(P, x) {
  const { e, m, sub, punto } = P;
  const h = huella(x, m, sub.y0), sil = silueta(x, m, sub.y0);
  const razon = [];
  if (h.x0 < 6 || h.x1 > P.VW - 6) razon.push('pantalla');
  if (x - m.cadera < sub.x0 + 8 || x + m.cadera > sub.x1 - 8) razon.push('cadera');
  // (con los brazos abiertos del gesto: tampoco)
  if (P.duros.some((b) => cruza({ ...h, x0: x - P.abre - 6, x1: x + P.abre + 6 }, b))) razon.push('tapa');
  let a = null;
  if (P.conBrazo) {
    const o = { p: m.p, subTop: sub.y0, rumbo: rumboDe(e.vista, punto.x - x), yc: m.yc };
    // (desde lejos, la mano abierta hacia el borde de lo que explica; si no, el índice hacia lo que señala)
    a = P.lejos ? manoAbierta(x, abierta(e.lado, P.c, x, yHombro(sub.y0, m)), o) : alcance(x, punto, o);
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
  let costo = 0, titulo = 0, cajaR = 0;
  for (const [b, w, conBrazo, propia, deRotulo] of P.blandos) {
    if (!propia) {
      costo += (w * areaEn(sil, b)) / ah;
      // el brazo, con la mitad del peso (no sobre lo que señala)
      if (brazo && conBrazo) costo += (0.5 * w * area(corte(brazo, b))) / ah;
      continue;
    }
    // un rótulo o lo resaltado: poco si se tapa un poco; mucho pasado el 25 % (lo que ya no se lee)
    const f = Math.min(1, (areaEn(sil, b) + (brazo && conBrazo ? 0.5 * area(corte(brazo, b)) : 0)) / (area(b) || 1));
    costo += w * (0.5 * f + 4 * Math.max(0, f - 0.25));
    if (deRotulo === 'titulo') titulo = Math.max(titulo, f);
    if (deRotulo === 'caja') cajaR = Math.max(cajaR, f);
  }
  // lejos del preferido cuesta poco (señalando, más: lo más cerca que deje el alcance; desde lejos, menos: la mano
  // abierta se lee «allá, en el panel» desde cualquier lado, y pesa más no tapar)
  const kLejos = P.lejos ? 0.3 : 1;
  costo += ((P.senala ? kLejos : 0.15) * Math.abs(x - P.pref)) / (Math.max(40, P.hi - P.lo) + 1);
  // señalando: la punta del dedo, a no más de 60 px (después, cuanto más lejos, peor; más allá de la banda, no está).
  // Desde lejos, la mano abierta: lo cerca que queda del borde de lo que explica, y lejos de los rótulos de la maqueta
  // (a menos de 60 px de uno se leería «esto de acá»: el puesto bajo el rótulo, su anillo)
  let dp = null;
  if (P.senala && a) {
    const destino = P.lejos ? abierta(e.lado, P.c, x, a.hombro.y) : punto;
    dp = destino ? Math.hypot(a.punta.x - destino.x, a.punta.y - destino.y) : null;
    if (dp !== null) costo += (kLejos * Math.max(0, dp - 60)) / 100;
    if (P.lejos) for (const b of P.marcas) costo += Math.max(0, 1 - distCaja(a.punta, b) / CERCA_PX);
  }
  return { x, costo: Math.round(costo * 1e4) / 1e4, razon, punta: a ? { x: Math.round(a.punta.x), y: Math.round(a.punta.y) } : null,
    dp: dp === null ? null : Math.round(dp), titulo: Math.round(titulo * 100) / 100, caja: Math.round(cajaR * 100) / 100 };
}
// Señalando, lo que no cumple de la banda: la punta (o la mano abierta) más lejos que la banda ('lejos'); desde lejos, el
// lugar que tapa un rótulo si hay otro que no ('rotulo': si el dedo no llega igual, no hay por qué taparlo)
function marcar(P, l) {
  if (l.dp !== null && l.dp > P.banda) l.razon.push('lejos');
  if (P.lejos && P.hayLimpios && !limpio(l, true)) l.razon.push('rotulo');
  return l;
}
// Los candidatos puntuados y, señalando, la banda del alcance (los que no llegan llevan la razón 'lejos'). Si desde
// ningún lugar limpio llega el dedo, «desde lejos»: se vuelven a puntuar con la mano abierta
function candidatos(P, c, chica) {
  const xs = new Set();
  if (chica) { xs.add(Math.round(c.sub.x1 - P.m.margen)); xs.add(Math.round(c.sub.x0 + P.m.margen)); }
  else {
    // cada 40 px (señalando, cada 8: lo más cerca que deje el alcance)
    for (let x = P.lo; x <= P.hi; x += P.senala ? 8 : 40) xs.add(Math.round(x));
    for (const x of [P.lo, (c.sub.x0 + c.sub.x1) / 2, P.hi, P.pref]) xs.add(Math.round(x));
  }
  let lista = [...xs].map((x) => puntuar(P, x));
  if (P.senala) {
    const b = bandaDe(lista);
    if (b.lejos && !chica) {
      P.lejos = true;
      lista = [...xs].map((x) => puntuar(P, x));
      const bl = bandaDe(lista, true, P.m.p);
      P.banda = bl.banda; P.hayLimpios = bl.hayLimpios;
    } else { P.banda = b.banda; P.hayLimpios = b.hayLimpios; }
  }
  for (const l of lista) marcar(P, l);
  return { lista, banda: P.banda };
}
// Señalando: hasta dónde puede quedar la punta. Cuentan los lugares que dejan leer los rótulos de la maqueta (limpio);
// si todos tapan alguno, todos. Si alguno de ellos llega (a no más de LEJOS_PX), LLEGA_PX o lo más cerca que se puede
// + 30 (llegar a lo que señala pesa más que la histéresis); si ninguno, «desde lejos» (`lejos`). Desde lejos
// (`abiertas`), la mano a no más de 0.45·pxAlto más lejos del borde que desde el mejor
function bandaDe(lista, abiertas = false, p = 0) {
  const validos = lista.filter((l) => !l.razon.length && l.dp !== null);
  const limpios = validos.filter((l) => limpio(l, abiertas));
  const ds = (limpios.length ? limpios : validos).map((l) => l.dp);
  const hayLimpios = limpios.length > 0;
  if (!ds.length) return { banda: Infinity, lejos: false, hayLimpios };
  const min = Math.min(...ds);
  if (abiertas) return { banda: min + BANDA_LEJOS * p, lejos: true, hayLimpios };
  if (min > LEJOS_PX) return { banda: Infinity, lejos: true, hayLimpios };
  return { banda: Math.min(LEJOS_PX, Math.max(LLEGA_PX, min + BANDA_PX)), lejos: false, hayLimpios };
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
  const { lista } = candidatos(P, c, chica);
  const orden = (a, b) => a.costo - b.costo || Math.abs(a.x - P.pref) - Math.abs(b.x - P.pref);
  return (todos ? lista : lista.filter((l) => !l.razon.length)).sort(orden);
}

/**
 * El lugar de la escena: el mejor de `lugares`, salvo que el de ahora (`actual.x`) siga cumpliendo todo y no sea mucho
 * peor (histéresis: costo ≤ 1.25·mejor + 0.02, con lo que señala del mismo lado y la punta del dedo a no más de 40 px
 * de lo que llega desde el mejor), o que moverse sea poco (menos de 0.25·pxAlto, o menos de 60 px hacia el lado
 * contrario de lo que explica: gira en el lugar). A lo sumo un cambio por escena (`actual.cambios`) y ninguno en una
 * escena corta (`actual.ms` < 3500: solo gira), salvo que el de ahora ya no cumpla (la cadera en el aire, tapa el
 * panel, la punta del dedo entraría en lo que señala o no llega). Sin ninguno que cumpla todo, el que menos falla.
 * → {x, cambia, costo, razon, lejos (señalando: desde lejos)}
 */
export function elegirLugar(e, m, ctx, c, actual = {}, { punto = null } = {}) {   // actual: {x, cambios, ms, ciego}
  if (!c.sub) return null;
  const chica = ctx.chica ?? (ctx.VW || 800) <= CHICA_PX;
  const P = preparar(e, m, ctx, c, punto);
  const { lista: todos } = candidatos(P, c, chica);
  const r = elegirEntre(P, m, todos, actual, punto);
  // (`lejos`: el dedo no llega desde ningún lugar que deje leer los rótulos: se señala desde lejos, con la mano abierta)
  return r && P.senala ? { ...r, lejos: P.lejos } : r;
}
function elegirEntre(P, m, todos, actual, punto) {
  const grave = (l) => l.razon.reduce((a, r) => a + ({ tapa: 100, cadera: 50, pantalla: 50, alcance: 10, lejos: 8, rotulo: 6, corte: 5 }[r] || 1), 0);
  const orden = (a, b) => a.costo - b.costo || Math.abs(a.x - P.pref) - Math.abs(b.x - P.pref);
  const mejor = todos.filter((l) => !l.razon.length).sort(orden)[0] || [...todos].sort((a, b) => grave(a) - grave(b) || a.costo - b.costo)[0] || null;
  const x = actual.x;
  if (!Number.isFinite(x)) return mejor ? { x: mejor.x, cambia: true, costo: mejor.costo, razon: 'primero' } : null;
  if (!mejor) return { x, cambia: false, costo: null, razon: 'sin_lugar' };
  const ahora = marcar(P, puntuar(P, x));
  // (el de ahora que ya no cumple: la cadera en el aire, tapa el panel, la punta del dedo entraría en lo que señala o
  // no llega; desde lejos, tapa un rótulo que otro lugar deja leer)
  const valeAhora = !ahora.razon.length;
  // (`ciego`: el lugar de ahora se eligió sin saber dónde quedarían la obra y sus rótulos: lo que llegó manda, aunque
  // ya haya cambiado o la escena sea corta)
  if (valeAhora && !actual.ciego && (actual.cambios || 0) >= 1) return { x, cambia: false, costo: ahora.costo, razon: 'ya_cambio' };
  if (valeAhora && !actual.ciego && Number.isFinite(actual.ms) && actual.ms < 3500) return { x, cambia: false, costo: ahora.costo, razon: 'corta' };
  const mismoLado = !punto || Math.sign(punto.x - x) === Math.sign(punto.x - mejor.x);
  // (señalando: desde aquí la punta queda a no más de 40 px de lo que llega desde el mejor)
  const llegaIgual = ahora.dp === null || mejor.dp === null || ahora.dp <= mejor.dp + 40;
  if (valeAhora && mismoLado && llegaIgual && ahora.costo <= 1.25 * mejor.costo + 0.02) return { x, cambia: false, costo: ahora.costo, razon: 'se_queda' };
  // moverse poco no vale la pena (la histéresis lo absorbe): menos de un cuarto de su alto, o menos de 60 px en contra de
  // lo que explica (caminar a la derecha para presentar a la izquierda se lee como ir y volver: gira en el lugar); salvo
  // que desde aquí tape bastante más (un título de la maqueta pasado el 30 % ya cuesta más que eso)
  const dx = mejor.x - x;
  const enContra = !!punto && Math.abs(dx) < 60 && Math.sign(dx) !== Math.sign(punto.x - x);
  if (valeAhora && llegaIgual && ahora.costo <= mejor.costo + 0.5 && (Math.abs(dx) < 0.25 * m.p || enContra)) return { x, cambia: false, costo: ahora.costo, razon: 'se_queda' };
  if (Math.abs(dx) < 3) return { x, cambia: false, costo: mejor.costo, razon: 'mismo' };
  return { x: mejor.x, cambia: true, costo: mejor.costo, razon: valeAhora ? 'mejor' : 'no_sirve' };
}

/**
 * Cómo pasa de una vista a otra. desde/hasta: {vista, plano, p, x, modo?}. → 'giro' (mismo lugar y plano: solo gira) |
 * 'acercar' (otro plano o tamaño en el mismo lugar, o a menos de 0.2·pxAlto: la cámara se acerca y se corre) |
 * 'caminar' (otro lugar a no más de 0.8·pxAlto, mismo plano) | 'saltar' (más lejos, u otro plano y otro lugar: se
 * agacha, el lienzo salta y se asoma) | 'rotulo' (de figura a rótulo o al revés) | 'fundido' (de un rótulo a otro, y con
 * movimiento reducido todo lo que no es girar)
 */
export function transicion(desde, hasta, { reducido = false, p = null } = {}) {
  if (!desde || !hasta) return 'giro';
  const dx = Number.isFinite(desde.x) && Number.isFinite(hasta.x) ? Math.abs(hasta.x - desde.x) : 0;
  const otroLugar = dx >= 3;
  const otroPlano = desde.plano !== hasta.plano || Math.abs((desde.p || 0) - (hasta.p || 0)) > 0.5
    || (desde.modo || null) !== (hasta.modo || null);
  if (!otroLugar && !otroPlano) return 'giro';
  if (reducido) return 'fundido';
  if ((desde.vista === 'rotulo') !== (hasta.vista === 'rotulo')) return 'rotulo';
  if (desde.vista === 'rotulo') return 'fundido';
  const ref = p || Math.min(hasta.p || Infinity, desde.p || Infinity);
  const P = Number.isFinite(ref) ? ref : 300;
  if (otroPlano) return dx <= 0.2 * P ? 'acercar' : 'saltar';
  return dx <= 0.8 * P ? 'caminar' : 'saltar';
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
