// Aguas: el acueducto del casco de punta a punta. Pozos y PTAP (40 L/s las 24 horas), impulsión de 12" al tanque elevado
// de 2.135 m³ y bajada por gravedad al pueblo, donde la red solo recibe agua 9 horas al día (4:00 a 13:00). La propuesta:
// sectorizar la red con válvulas y macromedidores para pasar a 24 horas, micromedir, bajar pérdidas, telemetría y un
// módulo de ampliación de la PTAP hacia ~60 L/s. El flujo de partículas muestra el agua; en el diagnóstico la red parpadea
// (9 de 24 horas) y con la propuesta queda encendida.
import { THREE, gsap } from '../../core.js';
import { CALLES, RED } from '../../data.js';
import { cinta } from '../geo3d.js';
import { moduloPTAP } from '../piezas/plantas.js';
import { sitios, trazado, caja } from './comun.js';

const SECTORES = [   // sectores hidráulicos de respaldo (los reemplazan los de geo.json)
  { id: 's1', nombre: 'Sector 1 · occidente', poligono: [[-640, -300], [-195, -300], [-195, 640], [-640, 640]] },
  { id: 's2', nombre: 'Sector 2 · centro sur', poligono: [[-195, -460], [330, -460], [330, 60], [-195, 60]] },
  { id: 's3', nombre: 'Sector 3 · centro norte', poligono: [[-195, 60], [330, 60], [330, 470], [-195, 470]] },
  { id: 's4', nombre: 'Sector 4 · oriente', poligono: [[330, -320], [760, -320], [760, 320], [330, 320]] },
  { id: 's5', nombre: 'Sector 5 · nororiente', poligono: [[330, 320], [760, 320], [760, 760], [330, 760]] },
];
const TONOS = ['#2a78d6', '#3fa7e0', '#1f5fb8', '#5cc1d6', '#2e8fc9', '#1d4f9a'];

export function crear(esc, datos) {
  const color = '--m-aguas';
  const pos = (id, def) => { const it = esc.edificios.get(id); return it ? [it.e.x, it.e.y] : def; };
  const ptap = pos('ptap', [-2265, 300]), tanque = pos('tanque_elevado', [-2356, 518]), capt = pos('captacion', [-2322, 249]);
  const ruta = (de, a) => { const t = RED?.arbol?.tramos?.find((x) => (x.de === de && x.a === a) || (x.de === a && x.a === de)); if (!t) return null; return t.de === de ? t.ruta : [...t.ruta].reverse(); };
  // impulsión PTAP → tanque (directa, indicativa: la ruta de la red del atlas da la vuelta por el casco) y bajada tanque →
  // casco (por la vía, hasta la entrada occidental junto al hospital)
  const imp = trazado(datos, 'aguas', 'impulsion')?.puntos || [ptap, tanque];
  const baja = trazado(datos, 'aguas', 'conduccion')?.puntos || [...(ruta('tanque_elevado', 'ptap') || [tanque, ptap]), ...(ruta('ptap', 'hospital') || [ptap, [-326, -121]]).slice(1)];

  const cSis = esc.capa('aguas.sistema'), cRed = esc.capa('aguas.red'), cSec = esc.capa('aguas.sectores'), cAmp = esc.capa('aguas.ampliacion');
  esc.flujo(imp.map(([x, y]) => [x, y, 3]), { color: '#3a8fe0', potencia: 0.75, max: 26, tam: 2.2, tubo: 0.6, padre: cSis });
  const fBaja = esc.flujo(baja.map(([x, y]) => [x, y, 3]), { color: '#3a8fe0', potencia: 0.9, max: 90, tam: 2.4, tubo: 0.7, padre: cSis });
  const lbl = (html, p, h = 30, cls = 'lbl-p') => esc.etiqueta(html, { pos: [p[0], p[1], h], padre: cSis, color: `var(${color})`, cls });
  lbl('<b>Pozos profundos</b><small>captación</small>', capt, 16, 'lbl-p mini');
  lbl('<b>PTAP · 40 L/s</b><small>opera las 24 horas</small>', ptap, 24);
  lbl('<b>Tanque elevado</b><small>2.135 m³ · impulsión de 12"</small>', tanque, 46);
  const mid = baja[Math.floor(baja.length * 0.55)];
  lbl('<b>Conducción al casco</b><small>por gravedad</small>', mid, 18, 'lbl-p mini');

  // red de distribución del casco (las calles residenciales) para mostrar las horas de servicio
  const calles = CALLES.calles.filter((c) => ['residential', 'tertiary', 'secondary', 'unclassified'].includes(c.tipo) && c.p.some(([x, y]) => Math.hypot(x, y) < 1000));
  const matRed = new THREE.MeshBasicMaterial({ color: new THREE.Color('#3a8fe0'), transparent: true, opacity: 0.85, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -9, polygonOffsetUnits: -9 });
  calles.forEach((c) => cRed.add(new THREE.Mesh(cinta(c.p, 4.5, 0.14), matRed)));
  esc.tenir(matRed, color);
  // parpadeo: encendida 9 de cada 24 «horas» (el ciclo dura 6 s) durante el diagnóstico
  let parpadeo = false, reloj = 0;
  esc.st.onFrame((dt) => {
    if (!parpadeo || !cRed.visible) return false;
    reloj = (reloj + dt / 6) % 1;
    const on = reloj < 9 / 24;
    matRed.opacity = on ? 0.9 : 0.08; fBaja.set(on ? 0.9 : 0.05, 1);
    return true;
  });

  // sectores hidráulicos con su entrada (válvula + macromedidor)
  const sec = sitios(datos, 'aguas', 'sector');
  const lista = sec.length ? sec.map((s) => ({ id: s.id, nombre: s.nombre, poligono: s.poligono })) : SECTORES;
  lista.forEach((s, i) => {
    const m = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(s.poligono.map(([x, y]) => new THREE.Vector2(x, y)))).rotateX(-Math.PI / 2).translate(0, 0.3, 0), new THREE.MeshBasicMaterial({ color: new THREE.Color(TONOS[i % TONOS.length]), transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -10, polygonOffsetUnits: -10 }));
    cSec.add(m);
    esc.linea([...s.poligono, s.poligono[0]].map(([x, y]) => [x, y, 1.2]), { color: TONOS[i % TONOS.length], ancho: 2.5, padre: cSec });
    const cx = s.poligono.reduce((a, p) => a + p[0], 0) / s.poligono.length, cy = s.poligono.reduce((a, p) => a + p[1], 0) / s.poligono.length;
    esc.etiqueta(`<b>${s.nombre}</b>`, { pos: [cx, cy, 14], padre: cSec, color: TONOS[i % TONOS.length], cls: 'lbl-p mini' });
  });
  const valvulas = sitios(datos, 'aguas', 'valvula');
  (valvulas.length ? valvulas.map((v) => [v.x, v.y]) : [[-200, -120], [-90, 60], [330, 60], [330, 330], [120, -300]]).forEach((p) => {
    const g = new THREE.Group(); g.position.set(p[0], 0, -p[1]);
    g.add(new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.2, 1.6, 16).translate(0, 0.8, 0), new THREE.MeshStandardMaterial({ color: 0x1f5fb8, roughness: 0.4, metalness: 0.4 })));
    g.add(new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 4, 8).translate(0, 2.4, 0), new THREE.MeshStandardMaterial({ color: 0xeeeeee })));
    cSec.add(g);
    esc.etiqueta('', { pos: [p[0], p[1], 3], padre: cSec, cls: 'lbl-dot', color: '#1f5fb8' });
  });
  esc.etiqueta('<b>Válvula + macromedidor</b><small>entrada de cada sector</small>', { pos: [...(valvulas[0] ? [valvulas[0].x, valvulas[0].y] : [-90, 60]), 40], padre: cSec, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });

  // módulo de ampliación de la PTAP, al lado de la planta actual
  const amp = sitio0(datos) || [ptap[0] + 62, ptap[1] - 18];
  const mod = moduloPTAP(amp[0], amp[1], 0); cAmp.add(mod);
  esc.etiqueta('<b>Ampliación de la PTAP</b><small>de 40 a ~60 L/s (horizonte 2044)</small>', { pos: [amp[0], amp[1], 20], padre: cAmp, color: `var(${color})` });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const entrada = baja[baja.length - 1];
  const vistaSistema = (duracion) => esc.encuadrar([capt, tanque, ptap, entrada, [capt[0] - 120, capt[1]]], { rumbo: 192, elev: 42, margen: 0.9, duracion });
  let tSis = 0;
  const parar = () => clearTimeout(tSis);
  const recorrido = () => { parar(); tSis = setTimeout(() => { if (!esc.st.userMoved && cSis.visible && !cRed.visible && !cAmp.visible) vistaSistema(3.5); }, 3000); };
  const vistaPlanta = () => esc.encuadrar(caja([ptap, tanque, capt, amp], 70), { rumbo: 160, elev: 34, margen: 0.86 });
  const vistaCasco = () => esc.encuadrar(lista.flatMap((s) => s.poligono), { rumbo: 196, elev: 50, margen: 0.94 });
  return {
    completo: ['aguas.sistema'],
    salir: () => { parpadeo = false; parar(); },
    alCompleto: parar,
    pasos: {
      portadilla: { capas: ['aguas.sistema', 'aguas.red'], antes: () => { parar(); parpadeo = true; }, vista: vistaCasco },
      sistema: { capas: ['aguas.sistema'], antes: () => { parpadeo = false; fBaja.set(0.9, 1); }, vista: vistaPlanta, animar: recorrido, alFinal: () => vistaSistema() },
      sectores: { capas: ['aguas.sistema', 'aguas.red', 'aguas.sectores'], antes: () => { parar(); parpadeo = false; matRed.opacity = 0.85; fBaja.set(0.9, 1); }, vista: vistaCasco, animar: () => { if (gsap) cSec.children.forEach((o, i) => { if (o.material?.opacity !== undefined && o.isMesh) gsap.fromTo(o.material, { opacity: 0 }, { opacity: o.material.opacity || 0.2, duration: 0.6, delay: 0.5 + i * 0.12, onUpdate: inv }); }); } },
      ampliacion: { capas: ['aguas.sistema', 'aguas.ampliacion'], antes: () => { parar(); parpadeo = false; }, vista: vistaPlanta, animar: () => { if (gsap) gsap.fromTo(mod.scale, { y: 0.01 }, { y: 1, duration: 1.1, delay: 0.8, ease: 'back.out(1.4)', onUpdate: inv }); } },
      '*': { capas: ['aguas.sistema', 'aguas.red', 'aguas.sectores'], antes: () => { parar(); parpadeo = false; matRed.opacity = 0.85; }, vista: vistaCasco },
    },
  };
}
function sitio0(datos) { const s = (datos.geo?.aguas?.sitios || []).find((x) => x.id === 'ptap_ampliacion'); return s ? [s.x, s.y] : null; }
