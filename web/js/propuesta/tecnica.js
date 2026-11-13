// La presentación técnica (propuesta.html?modo=tecnica): la que muestran el asistente del panel y los agentes por MCP.
// Lo que se construye, dónde, cómo funciona y cómo se mide, sin costos ni financiación (esos quedan en la propuesta para
// la gestión, propuesta.html sin `modo`). Aquí van las piezas puras, sin DOM ni 3D, para que una prueba con Node las
// compare con las de admin/app/agente/guion.py, que arma con las mismas reglas lo que sabe el asistente:
// * `sinPlata`, `cifraTecnica` y `especificacionTecnica`: quitan lo que tiene plata (un paréntesis con «$», el tramo de
//   una especificación entre «·» o «;», la frase que la lleve y la cifra en pesos o en millones).
// * `pasosTecnicos` y `capsTecnica`: los capítulos (portada, siete módulos y cronograma de obra) y sus pasos (los del
//   módulo sin el de financiación, las inmersiones de general.json detrás del paso que dicen y el de metas).
// * `anios`: los años de un plazo («Diseño 2029; obra 2030–2032» → [2029, 2032]) para el cronograma.

// Lo que delata plata en un texto: el signo de pesos o «millones de pesos» (`PLATA` de guion.py)
export const PLATA = /\$|millones de pesos/;
const PARENTESIS = /\s*\([^()]*\$[^()]*\)/g;
// Dónde termina una frase: punto, cierre de pregunta o de exclamación, espacio y una mayúscula, un signo de apertura, un
// paréntesis o una etiqueta (no un número: «Res. 3100» no parte)
const FRASE = /(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«(<])/;
const TRAMO = /\s+·\s+|;\s+/;
const ANTES_DE_SIGNO = /\s+([,.;:])/g;
// la especificación cuyo nombre es de plata («Costo anual», «Tope del subsidio») no va, diga lo que diga
const CLAVE_PLATA = /costo|valor|precio|subsidio|tope|presupuest|financ|cr[eé]dito|aporte|tarifa/i;
export const TITULO_METAS = 'Lo que cambia y cómo se mide';
export const TITULO_CRONOGRAMA = 'Cronograma de obra';

function sinParentesis(t) {
  let antes = null;
  while (antes !== t) { antes = t; t = t.replace(PARENTESIS, ''); }
  return t;
}

/** El texto sin lo que tiene plata: los paréntesis con «$», los tramos entre «·» o «;» que la lleven (con `tramos`, las
 * especificaciones) y las frases que la lleven. Lo demás queda igual, con su HTML. */
export function sinPlata(t, tramos = false) {
  if (typeof t !== 'string') return '';
  if (!PLATA.test(t)) return t;
  t = sinParentesis(t);
  if (tramos) t = t.split(TRAMO).filter((x) => x.trim() && !PLATA.test(x)).join(' · ');
  t = t.split(FRASE).filter((f) => f.trim() && !PLATA.test(f)).join(' ');
  return t.replace(ANTES_DE_SIGNO, '$1').trim();
}

/** Una cifra grande sin plata: no va (null) si su valor o su rótulo hablan de pesos o de millones; el rótulo pierde los
 * paréntesis con «$». */
export function cifraTecnica(c) {
  if (!c || typeof c !== 'object' || typeof c.v !== 'string' || !c.v.trim()) return null;
  const rotulo = typeof c.l === 'string' ? sinParentesis(c.l) : '';
  if (PLATA.test(c.v) || PLATA.test(rotulo) || rotulo.toLowerCase().includes('millones')) return null;
  return { ...c, l: rotulo.replace(ANTES_DE_SIGNO, '$1').trim() };
}

/** [nombre, valor] de una especificación sin plata, o null si no queda nada. */
export function especificacionTecnica(e) {
  if (!Array.isArray(e) || e.length !== 2 || !e.every((x) => typeof x === 'string')) return null;
  if (CLAVE_PLATA.test(e[0]) || PLATA.test(e[0])) return null;
  const v = sinPlata(e[1], true);
  return v ? [e[0], v] : null;
}

/** Los pasos de un módulo en la presentación técnica: los suyos sin el de financiación, cada inmersión de `tec.pasos`
 * detrás del paso que dice `despues_de` (o al final) y, si el módulo tiene metas, el paso de metas. */
export function pasosTecnicos(m, tec = {}) {
  const pasos = (m.pasos || []).filter((p) => p && typeof p === 'object' && p.tipo !== 'financiacion');
  const extra = tec.pasos && typeof tec.pasos === 'object' ? tec.pasos[m.id] : null;
  for (const e of Array.isArray(extra) ? extra : []) {
    if (!e || typeof e !== 'object') continue;
    const k = pasos.findIndex((p) => p.id === e.despues_de);
    pasos.splice(k < 0 ? pasos.length : k + 1, 0, e);
  }
  if (m.metas?.length) {
    const metas = tec.metas && typeof tec.metas === 'object' ? tec.metas : {};
    pasos.push({ id: 'metas', tipo: 'metas', titulo: metas.titulo || TITULO_METAS, texto: metas.texto || '' });
  }
  return pasos;
}

/** Los capítulos de la presentación técnica (los de `capitulos_tecnicos` de guion.py, con los mismos nombres fijos). */
export function capsTecnica(datos) {
  const tec = datos.tecnica && typeof datos.tecnica === 'object' ? datos.tecnica : {};
  const tp = tec.portada || {}, portada = datos.portada || {}, cr = tec.cronograma || {};
  return [
    { ...portada, ...tp, id: 'portada', nombre: 'Portada', corto: 'Portada', pasos: [
      { id: 'inicio', tipo: 'portada', titulo: tp.titulo || portada.titulo, texto: tp.texto || '', nota: tp.nota || '' },
      ...(portada.pasos || []).filter((p) => p && typeof p === 'object' && p.tipo !== 'portada')] },
    ...datos.modulos.map((m) => ({ ...m, modulo: true, pasos: pasosTecnicos(m, tec) })),
    { id: 'ruta', nombre: 'Cronograma de obra', corto: 'Cronograma', pasos: [
      { id: 'cronograma', tipo: 'cronograma', titulo: cr.titulo || TITULO_CRONOGRAMA, texto: cr.texto || '', nota: cr.nota || '' }] },
  ];
}

/** [desde, hasta] de un plazo («2028–2031», «Diseño 2029; obra 2030–2032»), o null si no trae años. */
export function anios(plazo) {
  const a = String(plazo ?? '').match(/20\d\d/g);
  if (!a) return null;
  const n = a.map(Number);
  return [Math.min(...n), Math.max(...n)];
}
