// Infraestructura TIC y energía: el anillo de fibra óptica que une las sedes públicas con el centro de control (CCED) en
// la alcaldía, Zonas Digitales con wifi público en parques y en la ciudadela deportiva, telemetría de las estaciones de
// bombeo y de la PTAR, y la energía de todo eso desde una granja solar CENTRALIZADA (no paneles sobre cada sede): 1,2 MWp
// frente a la subestación de EPM, con un bloque de reserva, más la granja de 997 kWp sobre el relleno clausurado.
import { THREE, gsap } from '../../core.js';
import { RED } from '../../data.js';
import { brotar } from '../geo3d.js';
import { granjaSolar } from '../piezas/plantas.js';
import { sitio, sitios, trazado, trazados, caja } from './comun.js';

const GRANJA = [[-1340, -300], [-1150, -300], [-1150, -470], [-1340, -470]];   // respaldo: junto a la subestación probable de EPM
const ZONAS_DIGITALES = [
  { nombre: 'Parque principal', p: [209, 96] }, { nombre: 'Parque Educativo', p: [151, -41] }, { nombre: 'Ciudadela deportiva', p: [-60, 125] },
  { nombre: 'Plaza del concejo', p: [201, 329] }, { nombre: 'Parque lineal del caño', p: [-160, 160] }, { nombre: 'Mirador del Magdalena', p: [1470, 7940] },
];

export function crear(esc, datos) {
  const color = '--m-tic';
  const cFib = esc.capa('tic.fibra'), cZd = esc.capa('tic.zonas'), cZd2 = esc.capa('tic.zonas2'), cTel = esc.capa('tic.telemetria'), cSol = esc.capa('tic.granja'), cDet = esc.capa('tic.granja_det'), cViejo = esc.capa('tic.descartado'), cHoy = esc.capa('tic.hoy');
  // fibra: las rutas por las vías entre sedes (las mismas de la red de distribución del atlas) más lo que traiga geo.json
  const rutas = trazados(datos, 'tic', 'fibra').map((t) => t.puntos);
  const tramos = rutas.length ? rutas : (RED?.arbol?.tramos || []).map((t) => t.ruta);
  const fibras = tramos.map((r) => esc.linea(r.map(([x, y]) => [x, y, 2]), { color: '--data', ancho: 3.5, punteada: true, guion: 9, padre: cFib }));
  esc.st.onFrame((dt) => { if (!cFib.visible) return false; fibras.forEach((f) => { f.material.dashOffset -= dt * 22; }); return true; });
  const alc = esc.edificios.get('alcaldia'), pA = alc ? [alc.e.x, alc.e.y] : [104, -199];
  // CCED: haz de luz y anillo que late sobre la alcaldía
  const haz = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, 80, 24, 1, true).translate(0, 40, 0), new THREE.MeshBasicMaterial({ color: 0x6250d6, transparent: true, opacity: 0.18, depthWrite: false, side: THREE.DoubleSide }));
  haz.position.set(pA[0], 0, -pA[1]); cFib.add(haz); esc.tenir(haz.material, '--data');
  esc.etiqueta('<b>CCED · centro de control</b><small>en la alcaldía</small>', { pos: [pA[0], pA[1], 84], padre: cFib, color: 'var(--data)', ancla: [0.5, 1] });
  // Zonas Digitales: pines de wifi con ondas
  const zd = sitios(datos, 'tic', 'zona_digital'), lista = zd.length ? zd.map((s) => ({ nombre: s.nombre, p: [s.x, s.y] })) : ZONAS_DIGITALES;
  const ondas = [];
  sitios(datos, 'tic', 'zona_digital_f2').forEach((s) => esc.etiqueta('', { pos: [s.x, s.y, 3], padre: cZd2, color: 'var(--muted)', cls: 'lbl-dot', titulo: `${s.nombre}: Zona Digital de la segunda fase` }));
  const corto = (n) => n.split(' (')[0].replace(/ y parque lineal.*$/, '');
  lista.forEach(({ nombre, p }) => {
    esc.etiqueta(`<b>ZD · ${corto(nombre)}</b>`, { pos: [p[0], p[1], 14], padre: cZd, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1], titulo: `Zona Digital: ${nombre}` });
    for (let k = 0; k < 2; k++) { const o = new THREE.Mesh(new THREE.RingGeometry(10, 11.2, 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x6250d6, transparent: true, opacity: 0.6, depthWrite: false })); o.position.set(p[0], 1 + k * 0.1, -p[1]); o.userData.fase = k / 2; cZd.add(o); ondas.push(o); esc.tenir(o.material, color); }
  });
  esc.st.onFrame((dt, t) => { if (!cZd.visible) return false; ondas.forEach((o) => { const u = ((t * 0.45) + o.userData.fase) % 1; o.scale.setScalar(0.4 + u * 2.4); o.material.opacity = 0.65 * (1 - u); }); return true; });
  // telemetría: puntos del acueducto y del alcantarillado que reportan al CCED (arcos de datos)
  const tel = sitios(datos, 'tic', 'telemetria');
  const puntos = tel.length ? tel.map((s) => ({ nombre: s.nombre, p: [s.x, s.y] })) : ['ptap', 'tanque_elevado', 'captacion', 'hospital'].map((id) => { const it = esc.edificios.get(id); return it ? { nombre: it.e.corto, p: [it.e.x, it.e.y] } : null; }).filter(Boolean);
  const arco = (a, b, h) => { const pts = []; for (let i = 0; i <= 40; i++) { const t = i / 40; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 10 + h * 4 * t * (1 - t)]); } return pts; };
  const ptarS = sitio(datos, 'saneamiento', 'ptar'), centralS = sitio(datos, 'saneamiento', 'ebar_central');
  if (ptarS?.poligono) esc.linea([...ptarS.poligono, ptarS.poligono[0]].map(([x, y]) => [x, y, 1.4]), { color: '--m-saneamiento', ancho: 2.5, punteada: true, guion: 8, padre: cTel });
  if (centralS) { const b = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 4, 24).translate(0, 2, 0), new THREE.MeshStandardMaterial({ color: 0x0d8f96, transparent: true, opacity: 0.45, depthWrite: false })); b.position.set(centralS.x, 0, -centralS.y); cTel.add(b); }
  puntos.forEach(({ nombre, p }) => { esc.linea(arco(p, pA, Math.min(260, Math.hypot(p[0] - pA[0], p[1] - pA[1]) * 0.12 + 30)), { color: '--data', ancho: 2.5, punteada: true, guion: 12, opacidad: 0.9, padre: cTel }); esc.etiqueta(`<b>${nombre}</b><small>telemetría${/PTAR|central/i.test(nombre) ? ' · obra nueva' : ''}</small>`, { pos: [p[0], p[1], 12], padre: cTel, color: 'var(--data)', cls: 'lbl-p mini', ancla: [0.5, 1] }); });

  // granja solar centralizada + la del relleno (réplica del atlas en modo proyecto)
  const sg = sitio(datos, 'tic', 'granja_solar'), poly = sg?.poligono || GRANJA, kwpMeta = sg?.kwp || 1200;
  const con0 = trazado(datos, 'tic', 'conexion_granja')?.puntos;
  const granja = granjaSolar(poly, { kwp: kwpMeta, salida: con0?.[0] || null }); cSol.add(granja);
  const cx = poly.reduce((a, p) => a + p[0], 0) / poly.length, cy = poly.reduce((a, p) => a + p[1], 0) / poly.length;
  esc.etiqueta(`<b>Granja solar municipal · ${granja.userData.kwp.toLocaleString('es-CO')} kWp</b><small>1,0 MW CA · energía para sedes, acueducto y PTAR desde un solo punto</small>`, { pos: [cx, cy, 16], padre: cSol, color: 'var(--power)', ancla: [0.5, 1] });
  const res = sitio(datos, 'tic', 'granja_reserva'), se = sitio(datos, 'tic', 'subestacion');
  if (res?.poligono) {
    esc.linea([...res.poligono, res.poligono[0]].map(([x, y]) => [x, y, 1]), { color: '#f0a020', ancho: 2.5, punteada: true, guion: 6, padre: cSol });
    const [rx, ry] = [res.poligono.reduce((a, q) => a + q[0], 0) / res.poligono.length, res.poligono.reduce((a, q) => a + q[1], 0) / res.poligono.length];
    esc.etiqueta('<b>Bloque B · reserva</b><small>0,49 ha para ampliar</small>', { pos: [rx, ry, 6], padre: cDet, color: 'var(--power)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  }
  if (se) esc.etiqueta('<b>Subestación Yondó · EPM</b><small>34,5/13,2 kV · conexión de 40 m</small>', { pos: [se.x, se.y, 12], padre: cDet, color: 'var(--power)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  // línea de 13,2 kV: de la subestación elevadora de la granja a la subestación de EPM
  const con = con0 ? [granja.userData.subestacion, ...con0] : null;
  if (con) esc.flujo(con.map(([x, y]) => [x, y, 11]), { color: '#f0a020', potencia: 0.9, max: 30, tam: 1.8, tubo: 0.3, padre: cSol });
  const rel = esc.edificios.get('relleno_parque');
  if (rel) esc.etiqueta('<b>Granja del relleno · 997 kWp</b><small>comunidad energética de estratos 1 y 2</small>', { pos: [rel.e.x, rel.e.y, 36], padre: cSol, color: 'var(--power)', cls: 'lbl-p mini' });
  // modelo descartado: paneles en cada sede (se muestra un momento para compararlo)
  const sedes = [...esc.edificios.values()].filter((it) => it.e.kwp_factible > 0 && !['relleno_parque', 'torre_hospital'].includes(it.e.id));
  sedes.forEach((it) => esc.etiqueta('', { pos: [it.e.x, it.e.y, 14], padre: cViejo, color: 'var(--bad)', cls: 'lbl-dot', titulo: it.e.corto || it.e.nombre || '' }));
  esc.etiqueta(`<b>Modelo descartado</b><small>paneles sobre ${sedes.length} sedes: muchas cubiertas, muchos contratos, poca escala</small>`, { pos: [0, -470, 30], padre: cViejo, color: 'var(--bad)', cls: 'lbl-p alerta', ancla: [0.5, 1] });
  // portadilla: las mismas sedes hoy, en gris (energía a tarifa oficial plena)
  sedes.forEach((it) => esc.etiqueta('', { pos: [it.e.x, it.e.y, 14], padre: cHoy, color: 'var(--muted)', cls: 'lbl-dot', titulo: it.e.corto || it.e.nombre || '' }));
  esc.etiqueta(`<b>${sedes.length} sedes públicas</b><small>energía a tarifa oficial plena</small>`, { pos: [pA[0], pA[1], 30], padre: cHoy, color: 'var(--muted)', cls: 'lbl-p mini', ancla: [0.5, 1] });
  const panelesSedes = (v) => sedes.forEach((it) => esc.modoEdificio(it.e.id, v ? 'proyecto' : 'hoy', ['conexion', 'equipos', 'almacenamiento', 'cubierta_nueva']));
  const verRelleno = (v) => esc.modoEdificio('relleno_parque', v ? 'proyecto' : 'hoy', ['conexion']);
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const vistaCasco = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], [-650, 760]], { rumbo: 196, elev: 52, margen: 0.94 });
  const vistaRed = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], pA, ...puntos.map((x) => x.p)], { rumbo: 196, elev: 52, margen: 0.94 });
  const vistaGranjaLejos = () => esc.encuadrar([...poly, ...(res?.poligono || []), ...(rel ? [[rel.e.x, rel.e.y]] : []), [0, 0]], { rumbo: 200, elev: 46, margen: 0.9 });
  const vistaGranja = () => esc.encuadrar(caja([...poly, ...(res?.poligono || []), ...(se ? [[se.x, se.y]] : [])], 45), { rumbo: 200, elev: 36, margen: 0.86, alto: 6 });
  const vistaTodo = () => esc.encuadrar([[-650, -420], [700, -420], [700, 760], [-650, 760], ...poly, ...(se ? [[se.x, se.y]] : [])], { rumbo: 196, elev: 52, margen: 0.94 });
  return {
    completo: ['tic.fibra', 'tic.granja'],
    salir: () => { panelesSedes(false); verRelleno(false); },
    alCompleto: () => { panelesSedes(false); verRelleno(true); },
    pasos: {
      portadilla: { capas: ['tic.hoy'], antes: () => { panelesSedes(false); verRelleno(false); }, vista: vistaCasco },
      fibra: { capas: ['tic.fibra', 'tic.zonas', 'tic.zonas2'], antes: () => panelesSedes(false), vista: vistaCasco },
      telemetria: { capas: ['tic.fibra', 'tic.telemetria'], antes: () => panelesSedes(false), vista: vistaRed },
      descartado: { capas: ['tic.descartado'], antes: () => { panelesSedes(true); verRelleno(false); }, vista: vistaCasco },
      granja: { capas: ['tic.granja', 'tic.granja_det'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaGranja, animar: () => brotar(granja, { duracion: 2.2, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() }) },
      granja_cerca: { capas: ['tic.granja'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaGranjaLejos },
      '*': { capas: ['tic.fibra', 'tic.zonas', 'tic.granja'], antes: () => { panelesSedes(false); verRelleno(true); }, vista: vistaTodo, etiquetas: ['tic.granja'] },
    },
  };
}
