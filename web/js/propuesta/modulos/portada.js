// Portada: el casco urbano con un pin por módulo en el sitio real de cada propuesta; el segundo paso se aleja hasta
// abarcar el territorio completo (del acueducto, 2,3 km al occidente, al puente sobre el Magdalena, 7,9 km al norte).
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const capa = esc.capa('portada.pines');
  const pines = pinesDe(datos);
  pines.forEach(({ m, i, x, y }) => {
    esc.linea([[x, y, 0], [x, y, 34]], { color: `--m-${m.id}`, ancho: 2.5, padre: capa });
    esc.etiqueta(`<span>${i + 1}</span>`, { cls: 'lbl-pin', pos: [x, y, 36], padre: capa, color: `var(--m-${m.id})`, titulo: `${i + 1}. ${m.nombre}`, alClic: () => { location.hash = m.id; } });
  });
  const casco = [[-650, -420], [700, -420], [700, 760], [-650, 760]];
  const todo = pines.map(({ x, y }) => [x, y]).concat([[-2400, 300], [1700, 8300]]);
  return {
    completo: ['portada.pines'],
    pasos: {
      inicio: { capas: ['portada.pines'], vista: () => esc.encuadrar(casco, { rumbo: 196, elev: 44, margen: 0.92, duracion: 2.4 }) },
      territorio: { capas: ['portada.pines'], vista: () => esc.encuadrar(todo, { rumbo: 205, elev: 55, margen: 0.94, duracion: 2.6 }) },
      '*': { capas: ['portada.pines'], vista: () => esc.encuadrar(casco, { rumbo: 196, elev: 44, margen: 0.92 }) },
    },
  };
}
