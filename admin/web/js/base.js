// Prefijo con que está montado el panel: «» si se sirve solo, «/panel» dentro del sitio público. El servidor lo
// escribe en <meta name="panel-base">. Las vistas siguen usando rutas como «/personas/12» o «/api/personas»: este
// módulo les pone el prefijo al pedir a la API, al navegar y en los enlaces que aparecen en la página.
export const BASE = (document.querySelector('meta[name="panel-base"]')?.content || '').replace(/\/+$/, '');

const conBase = (ruta) => BASE && (ruta === BASE || ruta.startsWith(BASE + '/'));

/** «/personas/12» → «/panel/personas/12» (deja igual lo que ya lo trae o no es una ruta absoluta del panel). */
export const url = (ruta) => (BASE && ruta.startsWith('/') && !ruta.startsWith('//') && !conBase(ruta) ? BASE + ruta : ruta);

/** «/panel/personas/12» → «/personas/12». */
export const sinBase = (ruta) => (conBase(ruta) ? ruta.slice(BASE.length) || '/' : ruta);

if (BASE) {
  // Enlaces internos con su prefijo, también los que arman los diálogos y los globos del mapa: así abrirlos en otra
  // pestaña o copiarlos lleva a la ficha correcta
  const fijar = (n) => {
    if (n.nodeType !== 1) return;
    const enlaces = n.matches('a[href^="/"]') ? [n] : [];
    for (const a of [...enlaces, ...n.querySelectorAll('a[href^="/"]')]) {
      const h = a.getAttribute('href');
      if (url(h) !== h) a.setAttribute('href', url(h));
    }
  };
  new MutationObserver((cambios) => { for (const c of cambios) c.addedNodes.forEach(fijar); })
    .observe(document.documentElement, { childList: true, subtree: true });
}
