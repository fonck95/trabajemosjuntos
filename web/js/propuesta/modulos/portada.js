// Portada: el casco urbano con un pin por módulo en el sitio real de cada propuesta; el segundo paso se aleja hasta
// abarcar el territorio completo (del acueducto, 2,3 km al occidente, al puente sobre el Magdalena, a unos 8 km al norte).
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const capa = esc.capa('portada.pines');
  const pines = pinesDe(datos);
  pines.forEach(({ m, i, x, y }) => {
    esc.linea([[x, y, 0], [x, y, 34]], { color: `--m-${m.id}`, ancho: 2.5, padre: capa });
    esc.etiqueta(`<span>${m.corto || m.nombre}</span>`, { cls: 'lbl-pin', pos: [x, y, 34], padre: capa, color: `var(--m-${m.id})`, titulo: m.nombre, alClic: () => { location.hash = m.id; }, ancla: [0.5, 1.2] });
  });
  // territorio: los nombres que cita el texto (río, puente y Barrancabermeja), solo en el segundo paso
  const geo = esc.capa('portada.geo'), tb = datos.territorio?.puente?.tablero;
  esc.etiqueta('Río Magdalena', { cls: 'lbl-geo', pos: [2600, 6800, 4], padre: geo });   // dentro del cauce, 1,5 km aguas arriba del puente
  if (tb?.length > 1) {
    const [m, f] = [tb[1], tb[tb.length - 1]];
    esc.etiqueta('Puente Guillermo Gaviria Correa', { cls: 'lbl-geo', pos: [m[0], m[1], 24], padre: geo, ancla: [0.5, 1] });
    esc.etiqueta('Barrancabermeja →', { cls: 'lbl-geo', pos: [f[0] + 90, f[1], 4], padre: geo, ancla: [0, 0.5] });
  }
  esc.sincronizarEtiquetas();
  // el casco con los pines de la granja solar (1,3 km al suroccidente) y de la PTAR (al norte, aguas abajo de la unión de
  // los caños); el del acueducto y el del parque agroindustrial aparecen en el paso del territorio
  const tic = pines.find(({ m }) => m.id === 'tic'), san = pines.find(({ m }) => m.id === 'saneamiento');
  const casco = [[-650, -420], [880, -420], [880, 760], [-650, 760], ...[tic, san].filter(Boolean).map(({ x, y }) => [x, y])];
  const todo = pines.map(({ x, y }) => [x, y]).concat([[-2400, 300], [1700, 8300], [2700, 6800]], tb?.length ? [[tb[tb.length - 1][0] + 260, tb[tb.length - 1][1]]] : []);
  return {
    completo: ['portada.pines'],
    pasos: {
      inicio: { capas: ['portada.pines'], vista: () => esc.encuadrar(casco, { rumbo: 196, elev: 44, margen: 0.92, duracion: 2.4 }) },
      territorio: { capas: ['portada.pines', 'portada.geo'], vista: () => esc.encuadrar(todo, { rumbo: 205, elev: 55, margen: 0.94, duracion: 2.6 }) },
      '*': { capas: ['portada.pines'], vista: () => esc.encuadrar(casco, { rumbo: 196, elev: 44, margen: 0.92 }) },
    },
  };
}
