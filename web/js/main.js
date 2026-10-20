// Navegación entre vistas, textos y carga diferida de cada escena 3D.
import { TEXTOS } from './data.js';

const scenes = {
  dinero: () => import('./scenes/dinero.js'),
  periodos: () => import('./scenes/periodos.js'),
  embudo: () => import('./scenes/embudo.js'),
  microrred: () => import('./scenes/microrred.js'),
  hospital: () => import('./scenes/hospital.js'),
  ruta: () => import('./scenes/ruta.js'),
};
const stages = {};

document.querySelectorAll('[data-t]').forEach((el) => {
  const t = TEXTOS[el.dataset.t];
  if (t) el.innerHTML = t;
});

async function show(id) {
  if (!scenes[id]) id = 'dinero';
  document.querySelectorAll('section.view').forEach((s) => { s.hidden = s.dataset.view !== id; });
  document.querySelectorAll('nav.tabs a').forEach((a) => a.setAttribute('aria-current', a.dataset.view === id ? 'page' : 'false'));
  Object.entries(stages).forEach(([k, st]) => { if (k !== id) st.stop(); });
  const root = document.getElementById(`v-${id}`);
  if (!stages[id]) {
    try {
      const mod = await scenes[id]();
      stages[id] = mod.mount(root);
    } catch (err) {
      console.error(err);
      root.querySelector('.stage').insertAdjacentHTML('beforeend', `<p class="note" style="padding:16px">No se pudo cargar la escena 3D (${err.message}). Los datos y tablas de esta vista siguen disponibles abajo.</p>`);
      return;
    }
  }
  stages[id].resize();
  stages[id].start();
}

const fromHash = () => show(location.hash.replace('#', '') || 'dinero');
addEventListener('hashchange', fromHash);
document.querySelectorAll('nav.tabs a').forEach((a) => a.addEventListener('click', (e) => {
  e.preventDefault();
  history.replaceState(null, '', `#${a.dataset.view}`);
  show(a.dataset.view);
}));
document.addEventListener('visibilitychange', () => {
  const id = location.hash.replace('#', '') || 'dinero';
  if (document.hidden) Object.values(stages).forEach((s) => s.stop()); else stages[id]?.start();
});
fromHash();
