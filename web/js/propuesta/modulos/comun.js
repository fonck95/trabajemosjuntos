// Utilidades que comparten los módulos 3D de la propuesta: dónde va el pin de cada módulo y cómo leer los sitios y
// trazados que vienen de data/propuesta/geo.json (en metros del modelo: x al oriente, y al norte).

// pin de cada módulo si geo.json no trae uno: el sitio principal de su propuesta
const PINES = {
  vivienda: [-490, 360], urbanismo: [-57, 125], agroindustria: [1300, 7750], salud: [-334, -128],
  aguas: [-2265, 300], saneamiento: [1000, 900], tic: [104, -199],
};
export function pinesDe(datos) {
  return datos.modulos.map((m, i) => {
    const [x, y] = datos.geo?.pines?.[m.id] || PINES[m.id] || [0, 0];
    return { m, i, x, y };
  });
}
// sitio o trazado de un módulo por su id (null si no está)
export const sitio = (datos, modulo, id) => (datos.geo?.[modulo]?.sitios || []).find((s) => s.id === id) || null;
export const trazado = (datos, modulo, id) => (datos.geo?.[modulo]?.trazados || []).find((t) => t.id === id) || null;
export const sitios = (datos, modulo, rol) => (datos.geo?.[modulo]?.sitios || []).filter((s) => !rol || s.rol === rol);
export const trazados = (datos, modulo, tipo) => (datos.geo?.[modulo]?.trazados || []).filter((t) => !tipo || t.tipo === tipo);
// caja de puntos [x, y] con un margen en metros (para encuadrar)
export function caja(pts, m = 0) {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs) - m, Math.max(...xs) + m, Math.min(...ys) - m, Math.max(...ys) + m];
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}
