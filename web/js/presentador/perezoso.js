// El presentador sin cargarlo antes de tiempo: mando.js le avisa todo a este objeto y el módulo de verdad
// (presentador.js, con su personaje y su contexto WebGL) se importa recién con el primer aviso que lo necesita. Así la
// presentación pública, que nadie narra, no lo descarga nunca. Lo que llega mientras carga se guarda y se le pasa
// después (lo último, si son muchos); si no se pudo crear (sin WebGL), lo que llega se ignora.
// `mostrar(false)` antes de cargarlo no lo carga: queda anotado para cuando haga falta.
const METODOS = ['narrar', 'frase', 'habla', 'pausa', 'cierre', 'preparando', 'explicar', 'quitar', 'mostrar'];
const COLA = 12;

export function presentadorPerezoso(cargar) {
  let real = null, estado = 'sin_cargar', permitido = true;
  const cola = [];
  function pedir(metodo, args) {
    if (metodo === 'mostrar') permitido = args[0] !== false;
    if (estado === 'listo') { try { real[metodo]?.(...args); } catch { /* nada */ } return; }
    if (estado === 'fallo') return;
    // sin cargar: un «quitar» o un «mostrar» no lo despiertan; tampoco nada si el panel lo apagó
    if (estado === 'sin_cargar' && (metodo === 'quitar' || metodo === 'mostrar' || !permitido)) return;
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
  return api;
}
