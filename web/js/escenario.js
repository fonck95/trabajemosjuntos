// El atlas como escenario de la presentación técnica (propuesta.html?modo=tecnica, js/propuesta/visual.js): con
// «?escenario=1» en la dirección, atlas.html muestra solo la escena 3D de una vista a pantalla completa, sin la
// cabecera, las pestañas, los textos ni las tarjetas (atlas.html, html[data-escenario]), y la presentación que lo enmarca
// le dice qué mostrar: la torre del hospital («Con la torre», los pisos por servicio, el recorrido por dentro, el
// laboratorio, el simulador sísmico o el modelo BIM) o el parque del relleno («Hoy» o «Con el parque»).
// * Se habla con window.__escenario, que solo alcanza una página del mismo origen (la presentación del sitio): a otro
//   origen el navegador no le deja tocar esta ventana, así que no hace falta otro filtro. Fuera de un marco o sin
//   «?escenario=1», no se instala nada y el atlas es el de siempre.
// * Cada vista sabe pasar a sus modos con sus botones (data-modo-torre, data-modo-parque): el escenario los pulsa, así
//   la escena hace exactamente lo mismo que cuando lo pide una persona.
// * Se importa primero en js/main.js: la marca data-escenario queda puesta antes de que cargue cualquier escena (torre.js
//   la lee para mostrar la torre como la propone la presentación, sin paneles ni conexión propios).
const consulta = new URLSearchParams(location.search);
let enMarco = false;
try { enMarco = window.parent !== window; } catch { enMarco = true; }
export const ESCENARIO = consulta.get('escenario') === '1' && enMarco;

// los botones de modo de cada vista que se puede pedir, y los modos que tiene cada una
const BOTON = { torre: 'modoTorre', parque: 'modoParque' };
export const MODOS = { torre: ['hoy', 'torre', 'pisos', 'recorrido', 'laboratorio', 'sismo', 'bim'], parque: ['hoy', 'parque'] };
const ESPERA_MS = 30000;

if (ESCENARIO) {
  document.documentElement.dataset.escenario = '';
  const montadas = new Set();
  const esperando = new Map();   // vista → resolver
  addEventListener('atlas:vista', (e) => {
    const id = e.detail?.id;
    montadas.add(id);
    esperando.get(id)?.();
    esperando.delete(id);
  });
  const montada = (vista) => (montadas.has(vista) ? Promise.resolve() : new Promise((ok, mal) => {
    const t = setTimeout(() => { esperando.delete(vista); mal(new Error('La vista del atlas no cargó')); }, ESPERA_MS);
    esperando.set(vista, () => { clearTimeout(t); ok(); });
  }));
  let cadena = Promise.resolve();
  window.__escenario = Object.freeze({
    /** Muestra `vista` con su `modo` (y el tema, si viene). Las órdenes se encadenan: dos seguidas no se cruzan. */
    ir({ vista, modo, tema } = {}) {
      const paso = cadena.then(async () => {
        if (tema === 'claro' || tema === 'oscuro') document.documentElement.dataset.theme = tema === 'claro' ? 'light' : 'dark';
        if (!vista) return true;
        if (!(vista in BOTON) || (modo && !MODOS[vista].includes(modo))) throw new Error('El atlas no tiene esa vista o ese modo');
        if (location.hash !== `#${vista}`) location.hash = vista;
        await montada(vista);
        if (modo) {
          const b = [...document.querySelectorAll(`#v-${vista} button`)].find((x) => x.dataset[BOTON[vista]] === modo);
          if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
        }
        return true;
      });
      cadena = paso.catch(() => {});
      return paso;
    },
    tema(t) { if (t === 'claro' || t === 'oscuro') document.documentElement.dataset.theme = t === 'claro' ? 'light' : 'dark'; },
    listo: () => true,
  });
}
