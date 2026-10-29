// Agroindustria: el parque agroindustrial junto a la salida del puente Guillermo Gaviria Correa, en el lote de 8,3 ha del
// levantamiento (al suroriente de la vía, de 200 a 700 m del estribo y a más de 300 m del río, que se socava). Seis
// componentes productivos que comparten frío, agua tratada y biodigestor, en tres zonas en fila (sucia al sur, limpia al
// centro y logística junto al cruce), con el muelle de carga 140 m aguas arriba del puente. Los flujos muestran el
// circuito: los granos y la yuca van a la fábrica, el alimento a los animales, los productos al frío y de ahí, por el
// puente, a Barrancabermeja.
import { THREE } from '../../core.js';
import { crecer, brotar } from '../geo3d.js';
import { parqueAgro } from '../piezas/plantas.js';
import { sitio, sitios, trazado } from './comun.js';

// distribución de respaldo en el marco local del lote (u a lo largo del lado mayor, v hacia la vía); la reemplaza geo.json
const LOTE = { centro: [1359.7, 7459.8], rumbo: 53.4, ancho: 340, fondo: 240 };
const COMPS = [
  { id: 'admin', tipo: 'admin', u: 144, v: 95, w: 40, d: 22, nombre: 'Administración, laboratorio y aulas SENA' },
  { id: 'maquinaria', tipo: 'maquinaria', u: 144, v: 39, w: 60, d: 58, nombre: 'Banco de maquinaria agrícola y amarilla' },
  { id: 'concentrados', tipo: 'concentrados', u: -8, v: 26, w: 40, d: 40, nombre: 'Fábrica de concentrados' },
  { id: 'trilladora', tipo: 'trilladora', u: -8, v: 82, w: 40, d: 48, nombre: 'Trilladora con secado y silos' },
  { id: 'leche', tipo: 'leche', u: 29, v: 97, w: 20, d: 18, nombre: 'Acopio de leche refrigerada' },
  { id: 'frio', tipo: 'frio', u: -53, v: 93, w: 30, d: 26, nombre: 'Central de frío' },
  { id: 'pescado', tipo: 'pescado', u: -66, v: 51, w: 50, d: 30, nombre: 'Planta de pescado y frío' },
  { id: 'matadero', tipo: 'matadero', u: -101, v: 91, w: 60, d: 30, nombre: 'Matadero y frigorífico' },
  { id: 'corrales', tipo: 'corrales', u: -146, v: 76, w: 24, d: 60, nombre: 'Corrales de reposo' },
  { id: 'biodigestor', tipo: 'biodigestor', u: -206, v: 72, w: 60, d: 68, nombre: 'Biodigestor y compostaje' },
  { id: 'ptar', tipo: 'ptar', u: -201, v: 3, w: 50, d: 55, nombre: 'PTAR industrial' },
];
const ZONAS = [
  { id: 'zona_logistica', nombre: 'Zona logística', color: '#6250d6', poligono: [[55, -10], [194, -10], [194, 123], [55, 123]] },
  { id: 'zona_limpia', nombre: 'Zona limpia', color: '#2a78d6', poligono: [[-70, -10], [55, -10], [55, 123], [-70, 123]] },
  { id: 'zona_sucia', nombre: 'Zona sucia', color: '#b85f00', poligono: [[-266, -102], [-70, -102], [-70, 123], [-266, 123]] },
];
const cen = (p) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length];

export function crear(esc, datos) {
  const color = '--m-agroindustria';
  const lote = sitio(datos, 'agroindustria', 'lote');
  // marco local: centro del lote y u a lo largo de su lado mayor (rumbo geográfico → ángulo desde el oriente, antihorario)
  const cfg = lote ? { centro: [lote.x, lote.y], rumbo: 90 - (lote.orientacion_grados ?? 36.6) } : LOTE;
  const th = THREE.MathUtils.degToRad(cfg.rumbo), c = Math.cos(th), s = Math.sin(th);
  const aLocal = ([x, y]) => [(x - cfg.centro[0]) * c + (y - cfg.centro[1]) * s, -(x - cfg.centro[0]) * s + (y - cfg.centro[1]) * c];
  const huella = (k) => {
    const P = k.poligono.map(aLocal), [u, v] = cen(P), e0 = [P[1][0] - P[0][0], P[1][1] - P[0][1]], e1 = [P[2][0] - P[1][0], P[2][1] - P[1][1]];
    return { id: k.id, tipo: k.tipo, nombre: k.nombre, u, v, w: Math.hypot(...e0), d: Math.hypot(...e1), rot: THREE.MathUtils.radToDeg(Math.atan2(e0[1], e0[0])) };
  };
  const gc = sitios(datos, 'agroindustria', 'componente').filter((k) => k.poligono);
  const comps = gc.length ? gc.map(huella) : COMPS;
  const gz = sitios(datos, 'agroindustria', 'zona');
  const zonas = gz.length ? gz.map((z) => ({ id: z.id, nombre: z.nombre, color: z.color || '#999', poligono: z.poligono.map(aLocal) })) : ZONAS;
  const lotePoly = lote?.poligono ? lote.poligono.map(aLocal) : null;
  // vías: carril interno junto a la vía del puente (de la portería a la puerta sur), la servidumbre de Ecopetrol y el
  // acceso al muelle de carga
  const serv = trazado(datos, 'agroindustria', 'servidumbre_ecopetrol')?.puntos, vMuelle = trazado(datos, 'agroindustria', 'via_muelle')?.puntos;
  const vias = lotePoly ? [{ puntos: [[188, 114], [-258, 114]], ancho: 9 }, ...(serv ? [{ puntos: serv.map(aLocal), ancho: 5 }] : []), ...(vMuelle ? [{ puntos: vMuelle.map(aLocal), ancho: 7 }] : [])] : null;
  const retiro = sitio(datos, 'agroindustria', 'retiro_pozos')?.poligono;
  const cP = esc.capa('agro.parque'), cF = esc.capa('agro.flujos');
  const parque = parqueAgro({ ...cfg, comps, zonas, lote: lotePoly, vias, restricciones: retiro ? [retiro.map(aLocal)] : [] }); cP.add(parque);
  const P = parque.userData.aModelo;
  // rótulo de cada nave con el nombre corto (sin lo que va después de «:» o «(»)
  const CORTO = { maquinaria: 'Banco de maquinaria', muelle: 'Muelle de carga' };
  const lbl = (id, html, h = 22) => { const k = comps.find((x) => x.id === id); if (!k) return; const [x, y] = P(k.u, k.v); esc.etiqueta(html || `<b>${CORTO[id] || k.nombre.split(/[:(]/)[0].trim()}</b>`, { pos: [x, y, h], padre: cP, color: `var(${color})`, cls: 'lbl-p mini' }); };
  ['matadero', 'pescado', 'concentrados', 'trilladora', 'leche', 'maquinaria', 'frio', 'muelle'].forEach((id) => lbl(id));
  if (retiro) { const [x, y] = cen(retiro); esc.etiqueta('<b>Retiro de pozos</b><small>Casabe 980 y 394: concepto de Ecopetrol</small>', { pos: [x, y, 6], padre: cP, color: 'var(--bad)', cls: 'lbl-p mini' }); }
  const [lx, ly] = lotePoly ? P(...cen(lotePoly)) : P(0, 0);
  esc.etiqueta('<b>Parque Agroindustrial de Yondó</b><small>8,3 ha · 6 componentes productivos · frío y residuos compartidos</small>', { pos: [lx, ly, 44], padre: cP, color: `var(${color})` });

  // portadilla: el lote como está hoy (contorno), junto a la vía del puente y lejos de la orilla que se socava
  const cSitio = esc.capa('agro.sitio');
  if (lote?.poligono) {
    esc.linea([...lote.poligono, lote.poligono[0]].map(([x, y]) => [x, y, 1.5]), { color, ancho: 3, punteada: true, guion: 10, padre: cSitio });
    // el rótulo, sobre el borde del lote más lejano a la cámara de la portadilla (rumbo 215: el nororiente), para no taparlo
    const [nx, ny] = lote.poligono.reduce((a, q) => (q[0] * 0.574 + q[1] * 0.819 > a[0] * 0.574 + a[1] * 0.819 ? q : a));
    esc.etiqueta('<b>Lote del parque</b><small>8,3 ha al suroriente de la vía del puente</small>', { pos: [nx, ny, 6], padre: cSitio, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  }
  const est = sitio(datos, 'urbanismo', 'estribo');
  if (est) {
    esc.etiqueta('', { cls: 'lbl-dot', pos: [est.x, est.y, 2], padre: cSitio, color: 'var(--bad)' });
    esc.etiqueta('<b>Estribo del puente</b><small>orilla socavada en 2026</small>', { pos: [est.x, est.y, 8], padre: cSitio, color: 'var(--bad)', cls: 'lbl-p mini alerta', ancla: [1, 1] });
  }

  // circuito: arcos de flujo entre componentes (colores de la cadena)
  const centroDe = (id) => { const k = comps.find((x) => x.id === id); return k ? P(k.u, k.v) : null; };
  const arco = (a, b, alto = 26) => { const pts = []; for (let i = 0; i <= 24; i++) { const t = i / 24; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 8 + alto * 4 * t * (1 - t)]); } return pts; };
  const tb = datos.territorio?.puente?.tablero, puente = tb ? [tb[1][0], tb[1][1]] : null;
  // ruta de exportación: del frío a la vía de servicio de Ecopetrol, por ella al carril interno y por este a la portería;
  // luego por la vía del puente hasta el estribo y por el puente (el tablero sube al 6 % hasta 14 m: el flujo va encima)
  const via = (datos.territorio?.vias || []).find((v) => /Barrancabermeja - Yond/.test(v.nombre || ''))?.puntos;
  const sv = serv ? serv.map(aLocal) : null;
  const uEn = (v) => { for (let i = 1; sv && i < sv.length; i++) { const [a, b] = [sv[i - 1], sv[i]]; if ((v - a[1]) * (v - b[1]) <= 0) return a[0] + (b[0] - a[0]) * ((v - a[1]) / (b[1] - a[1] || 1)); } return null; };
  function rutaExport() {
    const fr = comps.find((x) => x.id === 'frio');
    if (!fr || !via?.length || !tb || !lotePoly) return null;
    const u0 = uEn(fr.v), u1 = uEn(114);
    const local = u0 != null && u1 != null
      ? [[fr.u, fr.v], [u0, fr.v], ...sv.filter(([, v]) => v > fr.v && v < 114).sort((a, b) => a[1] - b[1]), [u1, 114], [188, 114]]
      : [[fr.u, fr.v], [fr.u, 114], [188, 114]];
    const interna = local.map(([u, v]) => P(u, v)), sal = interna[interna.length - 1];
    let m = { d: Infinity };
    for (let i = 1; i < via.length; i++) {
      const [a, b] = [via[i - 1], via[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((sal[0] - a[0]) * dx + (sal[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
      const q = [a[0] + t * dx, a[1] + t * dy], d = Math.hypot(q[0] - sal[0], q[1] - sal[1]);
      if (d < m.d) m = { d, q, i };
    }
    const [e0, e1] = [tb[0], tb[1]], le = Math.hypot(e1[0] - e0[0], e1[1] - e0[1]) || 1, k = Math.min(1, 250 / le);
    return [...interna.map(([x, y]) => [x, y, 4]), [...m.q, 4], ...via.slice(0, m.i).reverse().map(([x, y]) => [x, y, 4]),
      [e0[0] + (e1[0] - e0[0]) * k, e0[1] + (e1[1] - e0[1]) * k, 18], [e1[0], e1[1], 18]];
  }
  [['maquinaria', 'concentrados', '#c98a00'], ['trilladora', 'concentrados', '#e3b23c'], ['concentrados', 'corrales', '#8c6d3f'], ['corrales', 'matadero', '#b0533c'],
    ['matadero', 'frio', '#2a78d6'], ['pescado', 'frio', '#2a78d6'], ['leche', 'frio', '#7fb2e5'], ['matadero', 'biodigestor', '#6b8f3a'], ['muelle', 'pescado', '#2a78d6']]
    .forEach(([a, b, col]) => {
      const A = centroDe(a), Bp = centroDe(b); if (!A || !Bp) return;
      const pts = arco(A, Bp, Math.min(90, 26 + Math.hypot(Bp[0] - A[0], Bp[1] - A[1]) * 0.08));
      // el arco también como línea: las partículas solas no se leen cuando el parque se ve pequeño (en el celular)
      esc.linea(pts, { color: col, ancho: 2, opacidad: 0.75, padre: cF });
      esc.flujo(pts, { color: col, potencia: 0.6, max: 14, tam: 1.6, tubo: 0.25, padre: cF });
    });
  const rExp = rutaExport();
  if (rExp) esc.flujo(rExp, { color: '#2a78d6', potencia: 0.9, max: 60, tam: 2.4, tubo: 0.35, padre: cF });
  else if (puente && centroDe('frio')) esc.flujo(arco(centroDe('frio'), puente, 70), { color: '#2a78d6', potencia: 0.9, max: 30, tam: 2.2, tubo: 0.35, padre: cF });
  if (tb) esc.etiqueta('<b>A Barrancabermeja</b><small>en carros refrigerados por el puente</small>', { pos: [tb[0][0], tb[0][1], 20], padre: cF, color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 1] });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const muelle = centroDe('muelle');
  // el lote es largo (eje a 36,6°): se mira de través, desde el suroriente, para que no quede escorzado
  const vista = () => esc.encuadrar(parque.userData.contorno, { rumbo: 126, elev: 42, margen: 0.86, alto: 14 });
  const vistaLejos = () => esc.encuadrar([...parque.userData.contorno, ...(puente ? [puente] : []), ...(muelle ? [muelle] : []), [1511, 7885]], { rumbo: 215, elev: 44, margen: 0.94, obra: lote?.poligono || parque.userData.contorno });
  // en el celular, solo el parque (sin el muelle ni el estribo): con ellos las naves quedan diminutas y no se siguen los
  // flujos entre plantas
  const vistaCircuito = () => (innerWidth > 640
    ? esc.encuadrar([...parque.userData.contorno, ...(muelle ? [muelle] : []), ...(tb ? [tb[0]] : [])], { rumbo: 128, elev: 42, margen: 0.9 })
    : esc.encuadrar(parque.userData.contorno, { rumbo: 128, elev: 48, margen: 0.9, alto: 14 }));
  const animar = () => {
    const O = parque.userData.partes.obras;
    O.children.forEach((g, i) => crecer(g, { duracion: 0.9, retraso: 0.5 + i * 0.06, onUpdate: inv }));
    brotar(parque.userData.partes.verde.children[0], { duracion: 1.6, retraso: 0.8, onUpdate: inv });
    setTimeout(() => esc.st.updateShadows(), 2400);
  };
  return {
    completo: ['agro.parque'],
    pasos: {
      portadilla: { capas: ['agro.sitio'], vista: vistaLejos },
      componentes: { capas: ['agro.parque'], vista, animar },
      matadero: { capas: ['agro.parque'], vista: () => { const k = comps.find((x) => x.id === 'matadero'), co = comps.find((x) => x.id === 'corrales'), fr = comps.find((x) => x.id === 'frio'); if (!k) return vista(); esc.encuadrar([k, co, fr].filter(Boolean).flatMap((q) => [P(q.u - q.w / 2, q.v - q.d / 2), P(q.u + q.w / 2, q.v + q.d / 2)]), { rumbo: 215, elev: 34, margen: 0.9, alto: 12 }); } },
      circuito: { capas: ['agro.parque', 'agro.flujos'], vista: vistaCircuito, etiquetas: ['agro.flujos'] },
      '*': { capas: ['agro.parque'], vista },
    },
  };
}
