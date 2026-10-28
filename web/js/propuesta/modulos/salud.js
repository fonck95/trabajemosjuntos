// Salud: la torre de servicios de primer nivel junto al hospital Héctor Abad Gómez (el modelo BIM del atlas, ahora sin
// paneles propios: su energía viene de la granja solar centralizada), la red de telesalud por la fibra municipal hacia el
// centro de control y los puestos rurales, y las rutas de los equipos básicos de salud (EBS).
import { THREE, gsap } from '../../core.js';
import { sitios, caja } from './comun.js';

export function crear(esc, datos) {
  const color = '--m-salud';
  const torre = esc.edificios.get('torre_hospital'), hosp = esc.edificios.get('hospital');
  const pT = torre ? [torre.e.x, torre.e.y] : [-342, -137], pH = hosp ? [hosp.e.x, hosp.e.y] : [-326, -121];
  // capa de rótulos y enlaces de telesalud: arcos de datos del hospital al CCED (alcaldía) y hacia las veredas
  const cRed = esc.capa('salud.red'), cTorre = esc.capa('salud.torre');
  const alc = esc.edificios.get('alcaldia'), pA = alc ? [alc.e.x, alc.e.y] : [104, -199];
  const arco = (a, b, alto) => { const pts = []; for (let i = 0; i <= 40; i++) { const t = i / 40; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 12 + alto * 4 * t * (1 - t)]); } return pts; };
  esc.linea(arco(pH, pA, 60), { color: '--data', ancho: 3, punteada: true, guion: 10, padre: cRed });
  // puestos rurales: si geo.json trae sus sitios se usan; si no, rutas hacia el norte (Casabe), el occidente y el sur
  const puestos = sitios(datos, 'salud', 'puesto');
  const destinos = puestos.length ? puestos.map((s) => ({ p: [s.x, s.y], n: s.nombre })) : [
    { p: [-900, 2600], n: 'Veredas del norte (Casabe)' }, { p: [-2600, 400], n: 'Veredas del occidente' }, { p: [-1500, -2600], n: 'San Miguel del Tigre y el sur' },
  ];
  destinos.forEach(({ p, n }) => {
    esc.linea(arco(pH, p, 220), { color: '--data', ancho: 2.5, punteada: true, guion: 14, opacidad: 0.9, padre: cRed });
    esc.etiqueta(`<b>${n}</b><small>telesalud · EBS</small>`, { pos: [p[0], p[1], 30], padre: cRed, color: 'var(--data)', cls: 'lbl-p mini' });
  });
  esc.etiqueta('<b>Centro de control (CCED)</b><small>alcaldía</small>', { pos: [pA[0], pA[1], 22], padre: cRed, color: 'var(--data)', cls: 'lbl-p mini' });
  esc.etiqueta('<b>Torre de servicios de primer nivel</b><small>urgencias · partos · hospitalización · laboratorio 24 h</small>', { pos: [pT[0], pT[1], 36], padre: cTorre, color: `var(${color})` });
  esc.etiqueta('<b>Hospital Héctor Abad Gómez</b><small>sede actual: administración y apoyo</small>', { pos: [pH[0] + 30, pH[1] + 25, 14], padre: cTorre, color: `var(${color})`, cls: 'lbl-p mini' });
  esc.sincronizarEtiquetas();

  // la torre es la réplica del atlas en modo «proyecto», sin sus paneles ni la conexión de la microrred de sedes
  const verTorre = (v) => esc.modoEdificio('torre_hospital', v ? 'proyecto' : 'hoy', ['solar', 'conexion']);
  const crecerTorre = () => {
    if (!gsap || !torre?.lod) return;
    torre.lod.traverse((o) => { if (o.name === 'obra_nueva') gsap.fromTo(o.scale, { y: 0.02 }, { y: 1, duration: 1.6, delay: 0.7, ease: 'power3.out', onUpdate: () => esc.st.invalidate(), onComplete: () => esc.st.updateShadows() }); });
  };
  const cajaHosp = () => { const b = esc.cajaEdificio('torre_hospital'); const c = esc.cajaEdificio('hospital'); if (b && c) b.union(c); return b || caja([pT, pH], 60); };
  const vistaTorre = () => esc.encuadrar(cajaHosp(), { rumbo: 150, elev: 30, margen: 0.8 });
  const vistaRed = () => esc.encuadrar([...destinos.map((d) => d.p), pH, pA], { rumbo: 200, elev: 52, margen: 0.92 });
  return {
    completo: ['salud.torre'],
    pasos: {
      portadilla: { capas: [], antes: () => verTorre(false), vista: () => esc.encuadrar(caja([pH, pT], 140), { rumbo: 165, elev: 38, margen: 0.9 }) },
      componentes: { capas: ['salud.torre', 'salud.red'], antes: () => verTorre(true), vista: vistaRed },
      torre: { capas: ['salud.torre'], antes: () => verTorre(true), vista: vistaTorre, animar: crecerTorre },
      telesalud: { capas: ['salud.red', 'salud.torre'], antes: () => verTorre(true), vista: vistaRed },
      '*': { capas: ['salud.torre'], antes: () => verTorre(true), vista: vistaTorre },
    },
    salir: () => verTorre(false),
    alCompleto: () => verTorre(true),
  };
}
