// Hoja de ruta: la visión completa, con las capas principales de los siete módulos a la vez y la cámara girando
// despacio sobre el territorio mientras el panel cuenta las fases 2026–2031.
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const pts = pinesDe(datos).map(({ x, y }) => [x, y]).filter(([x, y]) => Math.hypot(x, y) < 1500);
  let girando = false;
  esc.st.onFrame(() => {
    const on = girando && !esc.st.flying && !esc.st.userMoved;
    esc.st.controls.autoRotate = on; esc.st.controls.autoRotateSpeed = 0.35;
    return on;
  });
  const parar = () => { girando = false; };
  addEventListener('hashchange', parar);
  return {
    completo: [],
    pasos: {
      '*': {
        todos: true,
        vista: () => { esc.encuadrar(pts.length ? pts : [[-600, -400], [700, 800]], { rumbo: 160, elev: 38, margen: 0.9, duracion: 2.4 }); setTimeout(() => { girando = location.hash.startsWith('#ruta'); }, 2600); },
      },
    },
  };
}
