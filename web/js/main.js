// Navegación entre vistas con transiciones GSAP, textos y carga diferida de cada escena 3D.
import { TEXTOS } from './data.js';
import { gsap, countUp } from './core.js';

const scenes = {
  dinero: () => import('./scenes/dinero.js'),
  periodos: () => import('./scenes/periodos.js'),
  embudo: () => import('./scenes/embudo.js'),
  microrred: () => import('./scenes/microrred.js'),
  ciudad: () => import('./scenes/ciudad.js'),
  hospital: () => import('./scenes/hospital.js'),
  torre: () => import('./scenes/torre.js'),
  parque: () => import('./scenes/parque.js'),
  ruta: () => import('./scenes/ruta.js'),
  modelos: () => import('./scenes/modelos.js'),
};
const stages = {};
let current = null;
let busy = Promise.resolve();

document.querySelectorAll('[data-t]').forEach((el) => {
  const t = TEXTOS[el.dataset.t];
  if (t) el.innerHTML = t;
});

// Globo de diálogo: cola (como el logo) y titular partido en palabras para animarlo
const TAIL = '<svg class="tail" viewBox="0 0 54 36" aria-hidden="true"><rect class="gap" x="3" y="-8" width="44" height="10"/><path class="edge" d="M4 0 L14 33 L46 0"/></svg>';
document.querySelectorAll('.bubble').forEach((b) => { if (!b.querySelector('.tail')) b.insertAdjacentHTML('beforeend', TAIL); });
document.querySelectorAll('.view .bubble h2').forEach((h) => {
  h.innerHTML = h.textContent.trim().split(/\s+/).map((w) => `<span class="w" style="display:inline-block">${w}</span>`).join(' ');
});

function enter(view) {
  if (!gsap) return;
  const bubble = view.querySelector('.bubble');
  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
  if (bubble) {
    tl.fromTo(bubble, { clipPath: 'inset(-30px 100% -50px -3em)' }, { clipPath: 'inset(-30px -30px -50px -3em)', duration: 0.7, ease: 'power2.inOut' }, 0);
    tl.from(bubble.querySelectorAll('.w'), { y: 26, opacity: 0, duration: 0.55, stagger: 0.045 }, 0.15);
    tl.from(bubble.querySelector('.eyebrow'), { opacity: 0, x: -10, duration: 0.4 }, 0.1);
    tl.from(bubble.querySelector('.tail'), { scale: 0, transformOrigin: '30% 0%', duration: 0.35, ease: 'back.out(2.5)' }, 0.55);
  }
  tl.from(view.querySelectorAll('.lede, .stamp'), { opacity: 0, y: 10, duration: 0.5, stagger: 0.08 }, 0.3);
  const stage = view.querySelector('.stage');
  if (stage) tl.from(stage, { opacity: 0, scale: 0.985, duration: 0.6 }, 0.25);
  tl.from(view.querySelectorAll('.folder > .card'), { opacity: 0, x: 18, duration: 0.5, stagger: 0.07 }, 0.35);
  view.querySelectorAll('.tile b').forEach((b) => countUp(b));
  tl.add(() => gsap.set(view.querySelectorAll('.bubble'), { clearProps: 'clipPath' }));
}

async function show(id) {
  if (!scenes[id]) id = 'dinero';
  const next = document.getElementById(`v-${id}`);
  if (current === next) return;
  document.querySelectorAll('nav.tabs a').forEach((a) => a.setAttribute('aria-current', a.dataset.view === id ? 'page' : 'false'));
  if (current && gsap) await gsap.to(current, { opacity: 0, y: -12, duration: 0.22, ease: 'power2.in' });
  Object.entries(stages).forEach(([k, st]) => { if (k !== id) st.stop(); });
  document.querySelectorAll('section.view').forEach((s) => { s.hidden = s !== next; });
  if (current && gsap) gsap.set(current, { clearProps: 'opacity,transform' });
  current = next;
  if (scrollY > 120) scrollTo({ top: 0, behavior: gsap ? 'smooth' : 'auto' });
  enter(next);
  if (!stages[id]) {
    try {
      const mod = await scenes[id]();
      stages[id] = mod.mount(next);
    } catch (err) {
      console.error(err);
      next.querySelector('.stage').insertAdjacentHTML('beforeend', `<p class="note" style="padding:16px;position:relative;z-index:2">No se pudo cargar la escena 3D (${err.message}). Los datos y tablas de esta vista siguen disponibles abajo.</p>`);
      return;
    }
  }
  stages[id].start();
  stages[id].intro();
}

// Las transiciones se encadenan para que dos clics rápidos no se crucen
const go = (id) => { busy = busy.then(() => show(id)).catch((e) => console.error(e)); };
addEventListener('hashchange', () => go(location.hash.replace('#', '')));
document.querySelectorAll('nav.tabs a').forEach((a) => a.addEventListener('click', (e) => {
  e.preventDefault();
  history.replaceState(null, '', `#${a.dataset.view}`);
  go(a.dataset.view);
}));
go(location.hash.replace('#', '') || 'dinero');
