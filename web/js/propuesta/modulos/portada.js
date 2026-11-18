// Portada: el casco urbano con un pin por módulo en el sitio real de cada propuesta y las obras de los siete capítulos ya
// construidas (la visión completa, como en la hoja de ruta: el estadio, la vivienda, la torre, la PTAR…), para que la vista
// global muestre la propuesta y no solo el pueblo de hoy; el segundo paso se aleja hasta abarcar el territorio completo (del relleno nuevo de Kilómetro Cinco, a unos 5,5 km al suroccidente, y el acueducto, 2,3 km
// al occidente, al puente sobre el Magdalena, a unos 8 km al norte).
import { pinesDe, sitio } from './comun.js';
import { dentro } from '../geo3d.js';

// En el teléfono el territorio se encuadra sin Kilómetro Cinco (con él, el casco queda en una franja de unos 40 px y los
// pines se enciman) y su rótulo se oculta, y se mira desde el occidente y más bajo: el río queda arriba y la PTAR al lado
// del casco, fuera de la columna de pines, que así cabe aun con la hoja media en 360 × 640 (y con el teléfono acostado, al
// lado del panel). Es la misma vista con la hoja plegada o desplegada, para que el mapa no gire al tocar el asa. Se decide
// en cada encuadre: sigue al tamaño de la ventana
const telefono = matchMedia('(max-width: 640px), (max-height: 500px)');

// Las obras que se contornean en la vista global, por módulo (polígonos de geo.json): a 2–24 km una obra es una mancha
// que se confunde con el potrero, y un borde de 3 px en el color de su área se lee a cualquier distancia
const OBRAS = {
  urbanismo: ['softbol_lote'], vivienda: ['lote_jdo', 'lote_oeste'], saneamiento: ['ptar', 'relleno_nuevo'],
  tic: ['granja_solar'], agroindustria: ['lote'],
};
// desde dónde mira la portada (grados desde el norte): el pin de una obra se corre a su borde del fondo de la pantalla
const RUMBO = 196;

// punto donde el rayo que sale de p hacia d corta el borde del polígono (el más cercano), o null
function borde(p, d, poly) {
  let t = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ax, ay] = poly[j], ex = poly[i][0] - ax, ey = poly[i][1] - ay, den = d[0] * ey - d[1] * ex;
    if (Math.abs(den) < 1e-9) continue;
    const s = ((ax - p[0]) * ey - (ay - p[1]) * ex) / den, u = ((ax - p[0]) * d[1] - (ay - p[1]) * d[0]) / den;
    if (s > 0 && u >= 0 && u <= 1) t = Math.min(t, s);
  }
  return Number.isFinite(t) ? t : null;
}

export function crear(esc, datos) {
  const capa = esc.capa('portada.pines');
  const pines = pinesDe(datos);
  // contornos de las obras (bajo los pines: van primero en la capa)
  const obras = [];
  Object.entries(OBRAS).forEach(([m, ids]) => ids.forEach((id) => {
    const poly = sitio(datos, m, id)?.poligono;
    if (!poly || poly.length < 3) return;
    obras.push({ m, poly });
    esc.linea([...poly, poly[0]].map(([x, y]) => [x, y, 1.4]), { color: `--m-${m}`, ancho: 3, opacidad: 0.95, padre: capa });
  }));
  // el pin que cae dentro de una obra (el estadio, el lote 1, la PTAR, la granja solar, el parque agroindustrial) ya no
  // va encima de ella con un tallo de 34 m que la atravesaba: se apoya en su borde del fondo, sin tallo, y su punta lo
  // señala; el contorno dice cuál es la obra. Los demás (la torre del hospital, la PTAP) conservan el tallo
  const az = (RUMBO + 180) * (Math.PI / 180), dir = [Math.sin(az), Math.cos(az)];
  const lejos = [];   // los pines fuera de la caja del inicio (granja solar, PTAR, acueducto, parque agroindustrial)
  pines.forEach(({ m, x, y }) => {
    const obra = obras.find((o) => o.m === m.id && dentro([x, y], o.poly)), t = obra && borde([x, y], dir, obra.poly);
    const [px, py, h] = t != null ? [x + dir[0] * (t + 3), y + dir[1] * (t + 3), 2] : [x, y, 34];
    if (h > 2) esc.linea([[x, y, 0], [x, y, h]], { color: `--m-${m.id}`, ancho: 2.5, padre: capa });
    const l = esc.etiqueta(`<span>${m.corto || m.nombre}</span>`, { cls: 'lbl-pin', pos: [px, py, h], padre: capa, color: `var(--m-${m.id})`, titulo: m.nombre, alClic: () => { location.hash = m.id; }, ancla: [0.5, 1.2] });
    if (px < -700 || px > 340 || py < -440 || py > 240) lejos.push(l);
  });
  // territorio: los nombres que cita el texto (río, puente, Barrancabermeja y el relleno nuevo), solo en el segundo paso
  const geo = esc.capa('portada.geo'), tb = datos.territorio?.puente?.tablero;
  const km5 = sitio(datos, 'saneamiento', 'relleno_nuevo'), pKm5 = km5 ? [km5.x, km5.y] : [-3764, -3955];
  const lKm5 = esc.etiqueta('Relleno nuevo · Kilómetro Cinco', { cls: 'lbl-geo', pos: [pKm5[0], pKm5[1], 4], padre: geo });
  esc.etiqueta('Río Magdalena', { cls: 'lbl-geo', pos: [2600, 6800, 4], padre: geo });   // dentro del cauce, 1,5 km aguas arriba del puente
  let lBarranca = null;
  if (tb?.length > 1) {
    const [m, f] = [tb[1], tb[tb.length - 1]];
    esc.etiqueta('Puente Guillermo Gaviria Correa', { cls: 'lbl-geo', pos: [m[0], m[1], 24], padre: geo, ancla: [0.5, 1] });
    lBarranca = esc.etiqueta('Barrancabermeja →', { cls: 'lbl-geo', pos: [f[0] + 90, f[1], 4], padre: geo, ancla: [0, 0.5] });
  }
  esc.sincronizarEtiquetas();
  // el inicio, sobre las obras del casco (del lote 1 de vivienda a la cancha de fútbol de la ciudadela) y no sobre la caja
  // que sumaba la granja solar (1,3 km al suroccidente) y la PTAR (1,5 km al norte): con ellas la cámara quedaba a 4 km y
  // el estadio medía 44 × 29 px; así, unos 80 × 55 px a 1280 × 720 con el panel. Sus pines vuelven en el territorio
  const casco = [[-660, -400], [300, -400], [300, 200], [-660, 200]];
  // en el inicio esos pines quedan fuera del cuadro (o asomaban bajo el panel): se ocultan, y vuelven en el territorio y
  // en las otras vistas de conjunto (alCompleto corre en todas, antes que el `antes` del paso)
  const verLejos = (v) => { lejos.forEach((l) => { l.userData.ver = v; }); esc.sincronizarEtiquetas(); };
  const todo = pines.map(({ x, y }) => [x, y]).concat([[-2400, 300], [1700, 8300], [2700, 6800]], tb?.length ? [[tb[tb.length - 1][0] + 260, tb[tb.length - 1][1]]] : []);
  // los rótulos esquivan las obras del casco (ningún recuadro tapa el punto de otro pin) y sus guías no se cruzan
  const sobreObras = obras.flatMap((o) => o.poly).filter(([x, y]) => x > -700 && x < 340 && y > -440 && y < 240);
  const vistaCasco = (duracion) => esc.encuadrar(casco, { rumbo: RUMBO, elev: 54, margen: 0.96, duracion, obra: sobreObras, apartar: true, sinCruces: true });
  const territorio = () => {
    const tel = telefono.matches;
    lKm5.userData.ver = !tel;
    if (lBarranca) lBarranca.userData.ver = !tel;   // mirando desde el occidente, Barrancabermeja queda arriba y la flecha engañaría
    esc.sincronizarEtiquetas();
    return esc.encuadrar(tel ? todo : [...todo, pKm5], { rumbo: tel ? 250 : 205, elev: tel ? 40 : 55, margen: 0.94, duracion: 2.6 });
  };
  return {
    completo: ['portada.pines'],
    alCompleto: () => verLejos(true),
    pasos: {
      inicio: { todos: true, capas: ['portada.pines'], antes: () => verLejos(false), vista: () => vistaCasco(2.4) },
      territorio: { todos: true, capas: ['portada.pines', 'portada.geo'], antes: () => verLejos(true), vista: territorio },
      '*': { todos: true, capas: ['portada.pines'], antes: () => verLejos(false), vista: () => vistaCasco() },
    },
  };
}
