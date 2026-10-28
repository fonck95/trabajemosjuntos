// Salud: la torre de servicios de primer nivel junto al hospital Héctor Abad Gómez (el modelo BIM del atlas, ahora sin
// paneles propios: su energía viene de la granja solar centralizada), la red de telesalud por la fibra municipal hacia el
// centro de control y los puestos rurales, y las rutas de los equipos básicos de salud (EBS). Los puestos van en sus
// centros poblados (OpenStreetMap); los que quedan más allá de la maqueta se señalan en su dirección con la distancia.
import { THREE, gsap } from '../../core.js';
import { sitios, caja } from './comun.js';

const ALCANCE = 11500;   // radio en el que se dibujan los puestos (el terreno de la maqueta llega a 16 km)

export function crear(esc, datos) {
  const color = '--m-salud';
  const torre = esc.edificios.get('torre_hospital'), hosp = esc.edificios.get('hospital');
  const pT = torre ? [torre.e.x, torre.e.y] : [-342, -137], pH = hosp ? [hosp.e.x, hosp.e.y] : [-326, -121];
  const cRed = esc.capa('salud.red'), cTorre = esc.capa('salud.torre'), cPuestos = esc.capa('salud.puestos'), cHoy = esc.capa('salud.hoy');
  const alc = esc.edificios.get('alcaldia'), pA = alc ? [alc.e.x, alc.e.y] : [104, -199];
  const arco = (a, b, alto) => { const pts = []; for (let i = 0; i <= 40; i++) { const t = i / 40; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 12 + alto * 4 * t * (1 - t)]); } return pts; };
  // enlace hospital → centro de control (alcaldía) con datos en movimiento
  esc.linea(arco(pH, pA, 60), { color: '--data', ancho: 3, punteada: true, guion: 10, padre: cRed });
  esc.flujo(arco(pH, pA, 60), { color: '#6250d6', potencia: 0.8, max: 16, tam: 2.4, tubo: 0.01, padre: cRed });
  esc.etiqueta('<b>Centro de control (CCED)</b><small>alcaldía</small>', { pos: [pA[0], pA[1], 22], padre: cRed, color: 'var(--data)', cls: 'lbl-p mini', ancla: [0, 0.5] });
  // puestos rurales: los de geo.json (OpenStreetMap); si no hay, tres direcciones genéricas
  const gp = sitios(datos, 'salud', 'puesto');
  const puestos = (gp.length ? gp : [{ nombre: 'Veredas del norte', x: -900, y: 2600 }, { nombre: 'Veredas del occidente', x: -2600, y: 400 }, { nombre: 'Veredas del sur', x: -1500, y: -2600 }])
    .map((s) => { const d = Math.hypot(s.x, s.y), lejos = d > ALCANCE, k = lejos ? ALCANCE / d : 1; return { ...s, p: [s.x * k, s.y * k], lejos, km: s.distancia_km ?? Math.round(d / 100) / 10 }; });
  const matPin = new THREE.MeshStandardMaterial({ color: 0xd9363e, roughness: 0.5, emissive: 0xd9363e, emissiveIntensity: 0.35 });
  esc.tenir(matPin, color, true);
  puestos.forEach((s) => {
    esc.linea(arco(pH, s.p, Math.min(900, 180 + Math.hypot(s.p[0] - pH[0], s.p[1] - pH[1]) * 0.06)), { color: '--data', ancho: 2.5, punteada: true, guion: 14, opacidad: 0.9, padre: cRed });
    const pin = new THREE.Mesh(new THREE.CylinderGeometry(40, 40, 120, 20).translate(0, 60, 0), matPin);
    pin.position.set(s.p[0], 0, -s.p[1]); cPuestos.add(pin);
    const uso = s.uso || 'telesalud · EBS';
    esc.etiqueta(`<b>${s.nombre}</b><small>${s.lejos ? `a ${String(s.km).replace('.', ',')} km → · ` : ''}${uso}</small>`, { pos: [s.p[0], s.p[1], 140], padre: cPuestos, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  });
  // huella de la torre en el color del módulo (la réplica BIM es blanca: así se lee la muestra de la leyenda)
  esc.alCargarEdificio?.('torre_hospital', () => {
    const b = esc.cajaEdificio('torre_hospital'); if (!b) return;
    const r = [[b.min.x - 2, -b.max.z - 2], [b.max.x + 2, -b.max.z - 2], [b.max.x + 2, -b.min.z + 2], [b.min.x - 2, -b.min.z + 2]];
    const m = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
    esc.tenir(m, color);
    const area = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(r.map(([x, y]) => new THREE.Vector2(x, y)))).rotateX(-Math.PI / 2).translate(0, 0.25, 0), m);
    cTorre.add(area);
    esc.linea([...r, r[0]].map(([x, y]) => [x, y, 0.4]), { color, ancho: 3, padre: cTorre });
    esc.st.invalidate();
  });
  esc.etiqueta('<b>Torre de servicios de primer nivel</b><small>urgencias · partos · hospitalización · laboratorio 24 h</small>', { pos: [pT[0], pT[1], 36], padre: cTorre, color: `var(${color})`, ancla: [0.5, 1] });
  esc.etiqueta('<b>Hospital Héctor Abad Gómez</b><small>sede actual: administración y apoyo</small>', { pos: [pH[0] + 30, pH[1] + 25, 14], padre: cTorre, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0, 0.5] });
  // portadilla: el hospital de hoy, la única sede pública habilitada
  esc.etiqueta('<b>E.S.E. Hospital Héctor Abad Gómez</b><small>única sede pública habilitada · edificio de 1989</small>', { pos: [pH[0], pH[1], 16], padre: cHoy, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  esc.sincronizarEtiquetas();

  // la torre es la réplica del atlas en modo «proyecto», sin sus paneles ni la conexión de la microrred de sedes
  const verTorre = (v) => esc.modoEdificio('torre_hospital', v ? 'proyecto' : 'hoy', ['solar', 'conexion']);
  const crecerTorre = () => {
    if (!gsap || !torre?.lod) return;
    torre.lod.traverse((o) => { if (o.name === 'obra_nueva') gsap.fromTo(o.scale, { y: 0.02 }, { y: 1, duration: 1.6, delay: 0.7, ease: 'power3.out', onUpdate: () => esc.st.invalidate(), onComplete: () => esc.st.updateShadows() }); });
  };
  const cajaHosp = () => { const b = esc.cajaEdificio('torre_hospital'); const c = esc.cajaEdificio('hospital'); if (b && c) b.union(c); return b || caja([pT, pH], 60); };
  const vistaTorre = () => esc.encuadrar(cajaHosp(), { rumbo: 150, elev: 30, margen: 0.8 });
  // telesalud: el casco con el enlace al centro de control; los arcos a las veredas salen del cuadro
  const vistaTele = () => esc.encuadrar(caja([pH, pA, pT], 170), { rumbo: 200, elev: 48, margen: 0.85 });
  const vistaRural = () => esc.encuadrar([...puestos.map((s) => s.p), pH], { rumbo: 200, elev: 56, margen: 0.86 });
  return {
    completo: ['salud.torre'],
    pasos: {
      portadilla: { capas: ['salud.hoy'], antes: () => verTorre(false), vista: () => esc.encuadrar(caja([pH, pT], 140), { rumbo: 165, elev: 38, margen: 0.9 }) },
      componentes: { capas: ['salud.torre', 'salud.red', 'salud.puestos'], antes: () => verTorre(true), vista: vistaRural, etiquetas: ['salud.puestos'] },
      torre: { capas: ['salud.torre'], antes: () => verTorre(true), vista: vistaTorre, animar: crecerTorre },
      telesalud: { capas: ['salud.red', 'salud.torre'], antes: () => verTorre(true), vista: vistaTele, etiquetas: ['salud.red', 'salud.torre'] },
      rural: { capas: ['salud.puestos', 'salud.red'], antes: () => verTorre(true), vista: vistaRural, etiquetas: ['salud.puestos'] },
      '*': { capas: ['salud.torre'], antes: () => verTorre(true), vista: vistaTorre },
    },
    salir: () => verTorre(false),
    alCompleto: () => verTorre(true),
  };
}
