// Aseo y saneamiento: hoy cuatro estaciones de bombeo vierten ~55 L/s de aguas residuales sin tratar. La propuesta del
// Plan Maestro de alcantarillado: interceptores que siguen los dos caños hasta su unión, al norte del casco, y allí,
// aguas abajo, una PTAR para todo el casco que devuelve el agua tratada al mismo caño (con laguna de pulimento). En aseo,
// un relleno sanitario nuevo en Yondó (vereda Kilómetro Cinco, en el predio que reserva el EOT), con la estación de
// clasificación y aprovechamiento (ECA) y el compostaje en el mismo predio, y el cierre del relleno Las Américas, que se
// vuelve parque ecotecnológico con granja solar.
import { THREE, gsap } from '../../core.js';
import { tubo, revelar, crecer, brotar, largo, puntoEn, losa, cinta, centro, V } from '../geo3d.js';
import { ptar } from '../piezas/plantas.js';
import { rellenoNuevo } from '../piezas/relleno.js';
import { sitios, sitio, trazado, trazados, caja } from './comun.js';

// respaldo hasta tener el levantamiento: estaciones en el borde bajo del casco, PTAR aguas abajo de la unión de los caños
const EBAR = [
  { id: 'ebar_progreso', nombre: 'EBAR El Progreso', x: 520, y: 640, ls: 13.52 },
  { id: 'ebar_paraiso', nombre: 'EBAR El Paraíso', x: -390, y: 430, ls: 16.51 },
  { id: 'ebar_prado', nombre: 'EBAR El Prado', x: 600, y: -160, ls: 10.62 },
  { id: 'ebar_victoria', nombre: 'EBAR La Victoria', x: -110, y: -380, ls: 14.69 },
];
const PTAR = { x: -70, y: 1652, rumbo: 90 };
const KM5 = [-3764, -3955];   // centro del predio del relleno nuevo, si geo.json no lo trae
const ARP = [11524, 1926];    // punto de referencia del aeropuerto Yariguíes (AIP), en metros del modelo
// desde dónde miran las vistas que rotulan de lado (grados desde el norte): el plano y los sitios
const R_PLAN = 205, R_SITIOS = 200;
// pantalla chica: la misma consulta de escena.js, donde el reparto aparta los rótulos que caen sobre la obra
const chico = matchMedia('(max-width: 1080px)');

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

  // hoy: cada estación vierte sin tratar (flujo rojo hacia el caño o la ciénaga más cercana)
  const vertidos = trazados(datos, 'saneamiento', 'vertimiento');
  ebars.forEach((e, i) => {
    const v = vertidos.find((t) => t.id === `vert_${e.id}`)?.puntos || [[e.x, e.y], [e.x + (e.x > 0 ? 160 : -160), e.y + (e.y > 0 ? 120 : -120)]];
    esc.linea(v.map(([x, y]) => [x, y, 1.2]), { color: '#8a5a2b', ancho: 3, opacidad: 0.85, padre: cHoy });
    esc.flujo(v.map(([x, y]) => [x, y, 1.5]), { color: '#8a5a2b', potencia: Math.min(1, (e.ls || 12) / 16), max: 26, tam: 3.5, tubo: 0.5, padre: cHoy });
    const g = new THREE.Group(); g.position.set(e.x, 0, -e.y);
    g.add(new THREE.Mesh(new THREE.BoxGeometry(7, 3.2, 5).translate(0, 1.6, 0), new THREE.MeshStandardMaterial({ color: 0xd8d2c4, roughness: 0.8 })), new THREE.Mesh(new THREE.BoxGeometry(7.6, 0.3, 5.6).translate(0, 3.35, 0), new THREE.MeshStandardMaterial({ color: 0x3f464c, roughness: 0.5, metalness: 0.4 })));
    g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    cEbar.add(g);
    esc.etiqueta(`<b>${e.nombre}</b><small>${e.ls ? `${String(e.ls).replace('.', ',')} L/s sin tratar` : 'sin tratamiento'}</small>`, { pos: [e.x, e.y, 14], padre: cHoy, color: 'var(--bad)', cls: 'lbl-p mini alerta' });
  });

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
  const tubos = [...lineas, impulsion].map((pts) => { const m = new THREE.Mesh(tubo(pts, 1.6, 1.8), matCol); m.castShadow = true; cCol.add(m); return m; });
  lineas.forEach((pts) => esc.flujo(pts.map(([x, y]) => [x, y, 3.6]), { color: '#7a5a3a', potencia: 0.5, max: 18, tam: 1.6, tubo: 0.01, padre: cCol }));
  esc.flujo(impulsion.map(([x, y]) => [x, y, 3.6]), { color: '#7a5a3a', potencia: 0.9, max: 24, tam: 1.8, tubo: 0.01, padre: cCol });
  esc.linea(impulsion.map(([x, y]) => [x, y, 4]), { color, ancho: 4, punteada: true, guion: 10, padre: cCol });
  esc.flujo(emisario.map(([x, y]) => [x, y, 2]), { color: '#3aa6d9', potencia: 0.9, max: 30, tam: 2, tubo: 0.5, padre: cPtar });
  const est = new THREE.Group(); est.position.set(pc[0], 0, -pc[1]);
  est.add(new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 4, 24).translate(0, 2, 0), new THREE.MeshStandardMaterial({ color: 0xd2cec4, roughness: 0.85 })), new THREE.Mesh(new THREE.BoxGeometry(8, 3, 6).translate(9, 1.5, 0), new THREE.MeshStandardMaterial({ color: 0xe8e4dc })));
  est.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } }); cCol.add(est);
  const lEst = esc.etiqueta('<b>Estación de bombeo de llegada</b><small>recibe los dos interceptores y sube el agua a la PTAR</small>', { pos: [pc[0], pc[1], 12], padre: cCol, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  // laguna de pulimento al norte de la planta: el caño lleva poco caudal para diluir, así que el agua se pule antes de volver
  const lag = sitio(datos, 'saneamiento', 'ptar_laguna')?.poligono;
  if (lag) {
    cPtar.add(new THREE.Mesh(losa(lag, 0.35), new THREE.MeshStandardMaterial({ color: 0x4f8f8a, roughness: 0.15, metalness: 0.1 })));
    cPtar.add(new THREE.Mesh(cinta([...lag, lag[0], lag[1]], 1.6, 0.6), new THREE.MeshStandardMaterial({ color: 0xbdb8ad, roughness: 0.9 })));
  }
  // la unión de los dos caños: la PTAR va aguas abajo de ella y la descarga vuelve al mismo caño, más abajo
  const union = sitio(datos, 'saneamiento', 'union_canos');
  if (union) esc.etiqueta('<b>Unión de los caños</b><small>Caño Colector Shell y canal oriental</small>', { pos: [union.x, union.y, 4], padre: esc.capa('san.sitios'), color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });   // solo en el paso de la PTAR
  // rótulos fuera de la planta (del lado oriental, lejos del caño) y a lo largo de la descarga, que vuelve al caño
  const pm = pP.userData.aModelo(0, -80);
  const lPtar = esc.etiqueta(`<b>PTAR central</b><small>aguas abajo de la unión de los caños · UASB + filtro percolador · 50 L/s${sp?.area_m2 ? ` · predio de ${(sp.area_m2 / 10000).toLocaleString('es-CO', { maximumFractionDigits: 1 })} ha` : ''}</small>`, { pos: [pm[0], pm[1], 14], padre: cPtar, color: `var(${color})`, ancla: [0.5, 1] });
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
  [['ptar_a', '#8a8f94', 'Sitio A · alternativa', 'reserva del EOT, pegada al casco'], ['ptar_b', '#d9363e', 'Sitio B · descartado', 'hacia el río: 911 m de bombeo y emisario'], ['ptar_c', '#d9363e', 'Sitio C · descartado', 'cerca de viviendas de finca'], ['ptar', '#0d8f96', '', '']].forEach(([id, col, t, sub]) => {
    const st = sitio(datos, 'saneamiento', id); if (!st?.poligono) return;
    esc.linea([...st.poligono, st.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: col, ancho: 3, punteada: true, guion: 8, padre: cSitios });
    const [cx, cy] = [st.poligono.reduce((a, q) => a + q[0], 0) / st.poligono.length, st.poligono.reduce((a, q) => a + q[1], 0) / st.poligono.length];
    if (id !== 'ptar') esc.etiqueta(`<b>${t}</b><small>${sub}</small>`, { pos: [cx, cy, 12], padre: cSitios, color: col, cls: 'lbl-p mini' });
  });

  // relleno Las Américas: cierre por partes desde 2028 (las celdas viejas primero) y del frente activo cuando abra el relleno
  // nuevo, en 2030; luego, parque ecotecnológico y granja solar (la réplica del atlas en modo proyecto)
  const rel = esc.edificios.get('relleno_parque'), pR = rel ? [rel.e.x, rel.e.y] : [-2508, 835];
  esc.etiqueta('<b>Relleno Las Américas</b><small>licencia vencida (2023) → cierre desde 2028 y parque ecotecnológico</small>', { pos: [pR[0], pR[1], 40], padre: cRel, color: `var(${color})`, ancla: [0.5, 1] });
  const verRelleno = (v) => esc.modoEdificio('relleno_parque', v ? 'proyecto' : 'hoy', ['conexion']);

  // relleno nuevo en la vereda Kilómetro Cinco, en el predio que reserva el EOT (Tabla 35): celdas por fases, lagunas de
  // lixiviados, ECA y compostaje, portería con báscula y la vía de acceso desde el casco. Los polígonos vienen de geo.json
  const cRN = esc.capa('san.relleno_nuevo'), cSit = esc.capa('san.relleno_sitios'), cVia = esc.capa('san.relleno_via');
  const rn = sitio(datos, 'saneamiento', 'relleno_nuevo');
  const pol = (id) => sitio(datos, 'saneamiento', id)?.poligono || null;
  const serie = (pre) => sitios(datos, 'saneamiento').filter((s) => s.id.startsWith(pre) && s.poligono).map((s) => s.poligono);
  const via = trazado(datos, 'saneamiento', 'via_relleno')?.puntos || null, port = sitio(datos, 'saneamiento', 'relleno_porteria');
  let rnP = null;
  if (rn?.poligono) {
    rnP = rellenoNuevo({ predio: rn.poligono, celdas: pol('relleno_celda_f1'), futuras: serie('relleno_celdas_futuras'), lixiviados: serie('relleno_lixiviados'), eca: pol('relleno_eca'), compostaje: pol('relleno_compostaje'), porteria: port ? [port.x, port.y] : null, entrada: via ? via.slice(-2) : null });
    cRN.add(rnP);
    const U = rnP.userData;
    // rótulos del predio, en el orden en que sus obras quedan de izquierda a derecha en la pantalla: el reparto los aparta
    // arriba o abajo del predio en ese orden, también en escritorio (la vista pide apartar), sin que una guía cruce otra
    // (sinCruces), y oculta los que no caben, primero los últimos. h: altura del rótulo sobre la obra
    const rot = (html, p, h, color) => esc.etiqueta(html, { pos: [...p, h], padre: cRN, color, cls: 'lbl-p mini' });
    if (U.compostaje) rot('<b>Compostaje</b><small>orgánicos separados en la fuente</small>', U.compostaje, 4, '#6f5233');
    if (U.celda) rot('<b>Celda de la fase 1</b><small>tres terrazas de 3 m · geomembrana en la cara activa</small>', U.celda, 14, '#5d6b45');
    if (U.eca) rot('<b>ECA</b><small>clasificación de reciclables</small>', U.eca, 10, `var(${color})`);
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
      esc.etiqueta(`<b>Planta de lodos del EOT</b><small>${lodos.rotulo || 'vecina por el occidente'}</small>`, { pos: [lx, ly, 6], padre: cRN, color: '#8a8f94', cls: 'lbl-p mini' });
    }
    // el contorno y el nombre del predio van con los sitios evaluados: se ven también en la vista de conjunto. El contorno
    // va a 4 m, por encima de la losa del predio aun con la cámara a 30 km; el rótulo, a la derecha del predio
    esc.linea([...rn.poligono, rn.poligono[0]].map(([x, y]) => [x, y, 4]), { color, ancho: 3.5, padre: cSit });
    esc.etiqueta(`<b>Relleno nuevo · Kilómetro Cinco</b><small>predio que reserva el EOT${rn.area_m2 ? ` · ${(rn.area_m2 / 10000).toLocaleString('es-CO', { maximumFractionDigits: 1 })} ha` : ''}</small>`, { pos: [...masAlla(U.centro, rn.poligono, R_SITIOS, 'der', 200), 0], padre: cSit, color: `var(${color})`, ancla: [0, 0.5] });
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
    esc.etiqueta(`<b>${s.nombre}</b>${s.rotulo ? `<small>${s.rotulo.replace(/ · /g, '<br>')}</small>` : ''}`, { pos: [...masAlla(centro(s.poligono), s.poligono, R_SITIOS, lado, 40), 0], padre: cSit, color: col, cls: 'lbl-p mini', ancla: lado === 'izq' ? [1, 0.5] : [0.5, 1] });
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
  esc.etiqueta('<b>13 km del aeropuerto Yariguíes</b><small>adentro, un relleno, una PTAR o una laguna<br>necesitan autorización de la Aerocivil</small>', { pos: [arco[31][0], arco[31][1], 4], padre: cSit, color: '#8e44ad', cls: 'lbl-p mini' });
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
      colectores: { capas: ['san.hoy', 'san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan, animar: () => tubos.forEach((t, i) => revelar(t, { duracion: 1.6, retraso: 0.4 + i * 0.15, onUpdate: inv })) },
      ptar: { capas: ['san.ebar', 'san.colectores', 'san.ptar', 'san.sitios'], antes: () => verRelleno(false), vista: vistaPtar, animar: () => { crecer(pP.userData.partes.obras, { duracion: 1.2, retraso: 0.7, onUpdate: inv, alFinal: () => esc.st.updateShadows() }); brotar(pP.userData.partes.verde.children[0], { duracion: 1.6, retraso: 1, onUpdate: inv }); } },
      relleno_nuevo: { capas: ['san.relleno_sitios', 'san.relleno_via', 'san.relleno_nuevo'], antes: () => verRelleno(false), vista: vistaSitios, etiquetas: ['san.relleno_sitios', 'san.relleno_via'] },
      residuos: { capas: ['san.relleno_nuevo', 'san.relleno_via'], antes: () => verRelleno(false), vista: vistaNuevo, animar: animNuevo, etiquetas: ['san.relleno_nuevo'] },
      relleno: { capas: ['san.relleno'], antes: () => verRelleno(true), vista: vistaRel },
      '*': { capas: ['san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan },
    },
  };
}
