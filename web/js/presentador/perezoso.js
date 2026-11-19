// El presentador sin cargarlo antes de tiempo: mando.js le avisa todo a este objeto y el módulo de verdad
// (presentador.js, con su personaje y su contexto WebGL) se importa recién con el primer aviso que lo necesita. Así la
// presentación pública, que nadie narra, no lo descarga nunca. Lo que llega mientras carga se guarda y se le pasa
// después (lo último, si son muchos); si no se pudo crear (sin WebGL), lo que llega se ignora.
// `mostrar(false)` antes de cargarlo no lo carga: queda anotado para cuando haga falta.
// Los avisos de lo que pasa en la escena (AVISOS: dónde queda la obra, el modelo del atlas que cargó, la simulación, la
// luz de la maqueta) tampoco lo despiertan: sin cargar se descartan (los vuelve a mandar la escena siguiente) y, mientras
// carga, de cada uno se guarda el último. `alturaMano()` pregunta en el acto (main.js, al resaltar): null si no está listo.
const METODOS = ['narrar', 'frase', 'habla', 'pausa', 'cierre', 'preparando', 'explicar', 'quitar', 'mostrar',
  'encuadre', 'atlas', 'simulacion', 'ambiente'];
const AVISOS = new Set(['encuadre', 'atlas', 'simulacion', 'ambiente']);
const COLA = 12;

export function presentadorPerezoso(cargar) {
  let real = null, estado = 'sin_cargar', permitido = true;
  const cola = [];
  function pedir(metodo, args) {
    if (metodo === 'mostrar') permitido = args[0] !== false;
    if (estado === 'listo') { try { real[metodo]?.(...args); } catch { /* nada */ } return; }
    if (estado === 'fallo') return;
    // sin cargar: un «quitar», un «mostrar» o un aviso de la escena no lo despiertan; tampoco nada si el panel lo apagó
    if (estado === 'sin_cargar' && (metodo === 'quitar' || metodo === 'mostrar' || AVISOS.has(metodo) || !permitido)) return;
    // de un aviso vale el último (así no empujan fuera de la cola a la escena que los trae)
    if (AVISOS.has(metodo)) { const i = cola.findIndex(([m]) => m === metodo); if (i >= 0) cola.splice(i, 1); }
    cola.push([metodo, args]);
    while (cola.length > COLA) cola.shift();
    if (estado === 'cargando') return;
    estado = 'cargando';
    Promise.resolve().then(cargar).then((p) => {
      if (!p) { estado = 'fallo'; cola.length = 0; return; }
      real = p;
      estado = 'listo';
      if (!permitido) { try { real.mostrar?.(false); } catch { /* nada */ } }
      for (const [m, a] of cola.splice(0)) { try { real[m]?.(...a); } catch { /* nada */ } }
    }).catch(() => { estado = 'fallo'; cola.length = 0; });
  }
  const api = Object.fromEntries(METODOS.map((m) => [m, (...args) => pedir(m, args)]));
  api.estado = () => estado;
  // {lado: 'panel' | 'ficha', y} mientras señala hacia ese lado en pantalla grande (main.js lleva lo resaltado a esa
  // altura); null si no está listo, si no señala o si el de verdad no lo sabe
  api.alturaMano = () => {
    if (estado !== 'listo') return null;
    try { return real.alturaMano?.() ?? null; } catch { return null; }
  };
  return api;
}
