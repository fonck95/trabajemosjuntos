// Hoja de ruta: la visión completa, con las capas principales de las siete áreas a la vez y la cámara girando
// despacio sobre el territorio mientras el panel cuenta las fases 2026–2031.
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const pts = [...pinesDe(datos).map(({ x, y }) => [x, y]).filter(([x, y]) => Math.hypot(x, y) < 1500), [-650, -420], [700, -420], [700, 760], [-650, 760]];
  let girando = false;
  esc.st.onFrame(() => {
    const on = girando && !esc.st.flying && !esc.st.userMoved;
    esc.st.controls.autoRotate = on; esc.st.controls.autoRotateSpeed = 0.35;
    return on;
  });
  // el giro dura mientras se está en este capítulo: lo dice el aviso de cada cambio de paso de main.js (`propuesta:paso`).
  // Antes se apagaba con `hashchange`, pero main.js cambia la dirección con replaceState (que no lo dispara): tras pasar
  // por aquí con las flechas, el riel o el mando del panel, la cámara seguía girando en los capítulos siguientes
  // (el módulo se carga en paralelo con el primer paso: si ese aviso ya pasó, la dirección dice dónde se está)
  let aqui = location.hash.startsWith('#ruta');
  addEventListener('propuesta:paso', (e) => { aqui = e.detail?.capitulo === 'ruta'; if (!aqui) girando = false; });
  return {
    completo: [],
    pasos: {
      '*': {
        todos: true,
        vista: () => { esc.encuadrar(pts.length ? pts : [[-600, -400], [700, 800]], { rumbo: 160, elev: 38, margen: 0.9, duracion: 2.4 }); setTimeout(() => { girando = aqui; }, 2600); },
      },
    },
  };
}
