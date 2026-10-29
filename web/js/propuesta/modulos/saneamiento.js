// Aseo y saneamiento: hoy cuatro estaciones de bombeo vierten ~55 L/s de aguas residuales sin tratar. La propuesta del
// Plan Maestro de alcantarillado: interceptores que siguen los dos caños hasta su unión, al norte del casco, y allí,
// aguas abajo, una PTAR para todo el casco que devuelve el agua tratada al mismo caño (con laguna de pulimento); además, clausurar el relleno Las Américas y convertirlo
// en parque ecotecnológico, y una estación de clasificación y aprovechamiento (ECA) de residuos.
import { THREE, gsap } from '../../core.js';
import { tubo, revelar, crecer, brotar, nave, largo, puntoEn, losa, cinta } from '../geo3d.js';
import { ptar } from '../piezas/plantas.js';
import { sitios, sitio, trazado, trazados, caja } from './comun.js';

// respaldo hasta tener el levantamiento: estaciones en el borde bajo del casco, PTAR aguas abajo hacia el río
const EBAR = [
  { id: 'ebar_progreso', nombre: 'EBAR El Progreso', x: 520, y: 640, ls: 13.52 },
  { id: 'ebar_paraiso', nombre: 'EBAR El Paraíso', x: -390, y: 430, ls: 16.51 },
  { id: 'ebar_prado', nombre: 'EBAR El Prado', x: 600, y: -160, ls: 10.62 },
  { id: 'ebar_victoria', nombre: 'EBAR La Victoria', x: -110, y: -380, ls: 14.69 },
];
const PTAR = { x: -70, y: 1652, rumbo: 90 };

export function crear(esc, datos) {
  const color = '--m-saneamiento';
  const eb = sitios(datos, 'saneamiento', 'ebar');
  const ebars = eb.length ? eb.map((s) => ({ id: s.id, nombre: s.nombre, x: s.x, y: s.y, ls: s.caudal_ls ?? EBAR.find((k) => k.id === s.id)?.ls })) : EBAR;
  const sp = sitio(datos, 'saneamiento', 'ptar'), central = sitio(datos, 'saneamiento', 'ebar_central');
  const cfg = sp ? { x: sp.x, y: sp.y, rumbo: sp.orientacion_grados ?? 0 } : PTAR;
  const cHoy = esc.capa('san.hoy'), cEbar = esc.capa('san.ebar'), cCol = esc.capa('san.colectores'), cPtar = esc.capa('san.ptar'), cRel = esc.capa('san.relleno'), cRes = esc.capa('san.residuos');

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
  esc.etiqueta('<b>Estación de bombeo de llegada</b><small>recibe los dos interceptores y sube el agua a la PTAR</small>', { pos: [pc[0], pc[1], 12], padre: cCol, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
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
  esc.etiqueta(`<b>PTAR central</b><small>aguas abajo de la unión de los caños · UASB + filtro percolador · 50 L/s${sp?.area_m2 ? ` · predio de ${(sp.area_m2 / 10000).toLocaleString('es-CO', { maximumFractionDigits: 1 })} ha` : ''}</small>`, { pos: [pm[0], pm[1], 14], padre: cPtar, color: `var(${color})`, ancla: [0.5, 1] });
  const [qx, qy] = puntoEn(emisario, 0.7);
  esc.etiqueta(`<b>Descarga al Caño Colector Shell</b><small>${Math.round(largo(emisario) / 5) * 5} m · el agua tratada vuelve al caño, aguas abajo</small>`, { pos: [qx, qy, 6], padre: cPtar, color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });
  // los otros sitios evaluados para la PTAR: A (alternativa), B (hacia el río) y C (cerca de viviendas), descartados
  const cSitios = esc.capa('san.sitios');
  [['ptar_a', '#8a8f94', 'Sitio A · alternativa', 'reserva del EOT, pegada al casco'], ['ptar_b', '#d9363e', 'Sitio B · descartado', 'hacia el río: 911 m de bombeo y emisario'], ['ptar_c', '#d9363e', 'Sitio C · descartado', 'cerca de viviendas de finca'], ['ptar', '#0d8f96', '', '']].forEach(([id, col, t, sub]) => {
    const st = sitio(datos, 'saneamiento', id); if (!st?.poligono) return;
    esc.linea([...st.poligono, st.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: col, ancho: 3, punteada: true, guion: 8, padre: cSitios });
    const [cx, cy] = [st.poligono.reduce((a, q) => a + q[0], 0) / st.poligono.length, st.poligono.reduce((a, q) => a + q[1], 0) / st.poligono.length];
    if (id !== 'ptar') esc.etiqueta(`<b>${t}</b><small>${sub}</small>`, { pos: [cx, cy, 12], padre: cSitios, color: col, cls: 'lbl-p mini' });
  });

  // relleno Las Américas: clausura y parque ecotecnológico (la réplica del atlas en modo proyecto)
  const rel = esc.edificios.get('relleno_parque'), pR = rel ? [rel.e.x, rel.e.y] : [-2508, 835];
  esc.etiqueta('<b>Relleno Las Américas</b><small>licencia vencida (2023) → clausura y parque ecotecnológico</small>', { pos: [pR[0], pR[1], 40], padre: cRel, color: `var(${color})`, ancla: [0.5, 1] });
  // ECA y compostaje en una ubicación indicativa (el predio de servicios está por definir; no va sobre las celdas del
  // relleno): nave de clasificación de 40 × 25 m y seis pilas de compostaje
  const pE = [pR[0] + 260, pR[1] - 160], eca = new THREE.Group();
  eca.add(nave(pE[0] - 18, pE[1], 40, 25, 8, 0));
  const matComp = new THREE.MeshStandardMaterial({ color: 0x6f5233, roughness: 1 });
  const pila = new THREE.ExtrudeGeometry(new THREE.Shape([new THREE.Vector2(-1.8, 0), new THREE.Vector2(1.8, 0), new THREE.Vector2(0, 1.6)]), { depth: 30, bevelEnabled: false }).translate(0, 0, -15);
  for (let k = 0; k < 6; k++) { const m = new THREE.Mesh(pila, matComp); m.position.set(pE[0] + 16 + k * 5.5, 0, -pE[1]); m.castShadow = true; m.receiveShadow = true; eca.add(m); }
  cRes.add(eca);
  const predioEca = caja([[pE[0] - 42, pE[1] - 25], [pE[0] + 50, pE[1] + 25]]);
  esc.linea([...predioEca, predioEca[0]].map(([x, y]) => [x, y, 1.2]), { color, ancho: 2.5, punteada: true, guion: 8, padre: cRes });
  esc.etiqueta('<b>ECA de 10 t/día y compostaje</b><small>ubicación indicativa · no sobre las celdas del relleno</small>', { pos: [pE[0], pE[1], 14], padre: cRes, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  const verRelleno = (v) => esc.modoEdificio('relleno_parque', v ? 'proyecto' : 'hoy', ['conexion']);
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const todo = [...ebars.map((e) => [e.x, e.y]), ...pP.userData.contorno];
  const vistaHoy = () => esc.encuadrar(ebars.map((e) => [e.x, e.y]).concat([[0, 0]]), { rumbo: 200, elev: 50, margen: 0.9 });
  const vistaPlan = () => esc.encuadrar(todo, { rumbo: 205, elev: 46, margen: 0.94 });
  const vistaPtar = () => esc.encuadrar([...caja(pP.userData.contorno, 90), puntoEn(emisario, 0.7).slice(0, 2), ...(union ? [[union.x, union.y]] : [])], { rumbo: 200, elev: 40, margen: 0.9, alto: 10 });
  const vistaRel = () => esc.encuadrar(rel ? esc.cajaEdificio('relleno_parque') : caja([pR], 200), { rumbo: 200, elev: 40, margen: 0.85 });
  const vistaRes = () => esc.encuadrar([...caja([pR], 160), ...predioEca], { rumbo: 200, elev: 44, margen: 0.9 });
  return {
    completo: ['san.ebar', 'san.colectores', 'san.ptar'],
    salir: () => verRelleno(false),
    alCompleto: () => verRelleno(true),
    pasos: {
      portadilla: { capas: ['san.hoy', 'san.ebar'], antes: () => verRelleno(false), vista: vistaHoy },
      colectores: { capas: ['san.hoy', 'san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan, animar: () => tubos.forEach((t, i) => revelar(t, { duracion: 1.6, retraso: 0.4 + i * 0.15, onUpdate: inv })) },
      ptar: { capas: ['san.ebar', 'san.colectores', 'san.ptar', 'san.sitios'], antes: () => verRelleno(false), vista: vistaPtar, animar: () => { crecer(pP.userData.partes.obras, { duracion: 1.2, retraso: 0.7, onUpdate: inv, alFinal: () => esc.st.updateShadows() }); brotar(pP.userData.partes.verde.children[0], { duracion: 1.6, retraso: 1, onUpdate: inv }); } },
      relleno: { capas: ['san.relleno'], antes: () => verRelleno(true), vista: vistaRel },
      residuos: { capas: ['san.relleno', 'san.residuos'], antes: () => verRelleno(true), vista: vistaRes, etiquetas: ['san.residuos'], animar: () => crecer(eca, { duracion: 1, retraso: 0.7, onUpdate: inv }) },
      '*': { capas: ['san.ebar', 'san.colectores', 'san.ptar'], antes: () => verRelleno(false), vista: vistaPlan },
    },
  };
}
