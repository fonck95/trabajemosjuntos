// Financiación: sobre el sitio de cada módulo se levanta una columna con la inversión, partida por fuentes con sus
// colores (regalías, Nación, obras por impuestos, Findeter…). La altura es proporcional a la plata: se compara de un
// vistazo qué pesa más y quién la pone.
import { THREE, gsap } from '../../core.js';
import { V } from '../geo3d.js';
import { pinesDe } from './comun.js';
import { fmtM } from '../main.js';

const M_POR_MILLON = 0.0042;   // metros de columna por millón de pesos (77.000 M ≈ 320 m)

export function crear(esc, datos) {
  const capa = esc.capa('financiacion.columnas'), F = datos.financiacion?.fuentes || [];
  const geo = new THREE.CylinderGeometry(1, 1, 1, 28).translate(0, 0.5, 0), mats = new Map();
  const matDe = (f) => mats.get(f.id) || mats.set(f.id, new THREE.MeshStandardMaterial({ color: new THREE.Color(f.color || '#888'), roughness: 0.45, metalness: 0.1, emissive: new THREE.Color(f.color || '#888'), emissiveIntensity: 0.15 })).get(f.id);
  const columnas = pinesDe(datos).map(({ m, x, y }) => {
    const g = new THREE.Group(); g.position.copy(V(x, y)); capa.add(g);
    const radio = 26;
    let h = 0;
    (m.financiacion || []).slice().sort((a, b) => b.monto - a.monto).forEach((f) => {
      const fu = F.find((k) => k.id === f.fuente) || { id: f.fuente, color: '#999' }, alto = (f.monto || 0) * M_POR_MILLON;
      if (alto <= 0) return;
      const o = new THREE.Mesh(geo, matDe(fu)); o.scale.set(radio, alto, radio); o.position.y = h; o.castShadow = true; g.add(o);
      h += alto;
    });
    esc.etiqueta(`<b>${m.corto || m.nombre}</b><small>${fmtM(m.inversion?.central)}</small>`, { pos: [0, 0, h + 18], padre: g, color: `var(--m-${m.id})` });
    return { g, h };
  });
  const todo = pinesDe(datos).map(({ x, y }) => [x, y, 0]).concat(pinesDe(datos).map(({ x, y }) => [x, y, 330]));
  const animar = () => {
    if (!gsap) return;
    columnas.forEach(({ g }, i) => gsap.fromTo(g.scale, { y: 0.001 }, { y: 1, duration: 1.4, delay: 0.5 + i * 0.12, ease: 'power3.out', onUpdate: () => esc.st.invalidate(), onComplete: () => esc.st.updateShadows() }));
  };
  const vista = () => esc.encuadrar(todo, { rumbo: 210, elev: 34, margen: 0.94, duracion: 2.2 });
  return { completo: [], pasos: { '*': { capas: ['financiacion.columnas'], vista, animar } } };
}
