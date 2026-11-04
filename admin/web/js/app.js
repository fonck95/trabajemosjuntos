// Arranque del panel: sesión, menú lateral y enrutado en el navegador.
import { api, configurar, ErrorApi, sesion } from './api.js';
import { $, aviso, html, icono, montar } from './ui.js';
import { vistaLogin } from './vistas/login.js';
import { sinBase, url } from './base.js';
import { revisarLlamadasPendientes } from './llamadas.js';

const RUTAS = [
  { re: /^\/$|^\/panel$/, nav: 'panel', carga: () => import('./vistas/panel.js').then((m) => m.vistaPanel) },
  { re: /^\/mapa$/, nav: 'mapa', lleno: true, carga: () => import('./vistas/mapa.js').then((m) => m.vistaMapa) },
  { re: /^\/personas$/, nav: 'personas', carga: () => import('./vistas/personas.js').then((m) => m.vistaPersonas) },
  { re: /^\/personas\/(\d+)$/, nav: 'personas', carga: () => import('./vistas/ficha.js').then((m) => m.vistaFicha) },
  { re: /^\/reuniones$/, nav: 'reuniones', carga: () => import('./vistas/reuniones.js').then((m) => m.vistaReuniones) },
  { re: /^\/reuniones\/(\d+)$/, nav: 'reuniones', carga: () => import('./vistas/reunion.js').then((m) => m.vistaReunion) },
  { re: /^\/calidad$/, nav: 'calidad', carga: () => import('./vistas/calidad.js').then((m) => m.vistaCalidad) },
  { re: /^\/importar$/, nav: 'importar', carga: () => import('./vistas/importar.js').then((m) => m.vistaImportar) },
  { re: /^\/ajustes$/, nav: 'ajustes', carga: () => import('./vistas/ajustes.js').then((m) => m.vistaAjustes) },
  { re: /^\/trabajo$/, nav: 'trabajo', carga: () => import('./vistas/trabajo.js').then((m) => m.vistaTrabajo) },
  { re: /^\/usuarios$/, nav: 'usuarios', carga: () => import('./vistas/usuarios.js').then((m) => m.vistaUsuarios) },
  { re: /^\/usuarios\/(\d+)$/, nav: 'usuarios', carga: () => import('./vistas/usuarios.js').then((m) => m.vistaUsuario) },
  { re: /^\/cuenta$/, nav: 'cuenta', carga: () => import('./vistas/cuenta.js').then((m) => m.vistaCuenta) },
];
const NAV = [
  ['panel', 'Panel', '/'], ['mapa', 'Mapa 3D', '/mapa'], ['personas', 'Habitantes', '/personas'],
  ['reuniones', 'Reuniones', '/reuniones'], ['calidad', 'Calidad de datos', '/calidad'], ['importar', 'Importar y exportar', '/importar'],
  ['ajustes', 'Ajustes', '/ajustes'],
];

let limpiarVista = null;
let generacion = 0;

function tema() {
  try { return localStorage.getItem('tema'); } catch { return null; }
}
function aplicarTema(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  try { t ? localStorage.setItem('tema', t) : localStorage.removeItem('tema'); } catch { /* sin almacenamiento */ }
  window.dispatchEvent(new CustomEvent('tema'));
}
export const temaOscuro = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';

export function ir(ruta, { reemplazar = false } = {}) {
  const destino = url(sinBase(ruta)); // acepta «/personas» o «/panel/personas»
  if (reemplazar) history.replaceState({}, '', destino);
  else history.pushState({}, '', destino);
  render();
}

function armarEstructura() {
  montar($('#raiz'), html`
    <div class="app" id="app">
      <div class="barra-movil"><button id="abrir-menu" aria-label="Menú" aria-expanded="false" aria-controls="menu-lateral">${icono('menu')}</button><b>Yondó · Base única</b></div>
      <aside class="lateral" id="menu-lateral" aria-label="Navegación">
        <a class="marca" href="/" data-ruta><span class="sello">Y</span><span><b>Yondó</b><small>Base única · Panel</small></span></a>
        <nav class="nav" id="nav">${NAV.map(([k, t, href]) => html`<a href="${href}" data-ruta data-nav="${k}">${icono(k)}<span>${t}</span>${k === 'calidad' ? html`<span class="insignia oculto" id="insignia-calidad" title="Personas con coincidencias por revisar"></span>` : ''}</a>`)}</nav>
        <div class="pie">
          <span>Sesión: <b id="usuario"></b></span>
          <button id="cambiar-tema">${icono('luna')} Cambiar tema</button>
          <button id="salir">${icono('salir')} Cerrar sesión</button>
        </div>
      </aside>
      <div class="velo" id="velo"></div>
      <main class="contenido" id="vista" tabindex="-1"></main>
    </div>`);
  $('#usuario').textContent = sesion.usuario;
  $('#salir').onclick = async () => {
    try { await api.post('/api/logout'); } catch { /* ya cerrada */ }
    location.href = url('/');
  };
  $('#cambiar-tema').onclick = () => aplicarTema(temaOscuro() ? 'light' : 'dark');
  $('#abrir-menu').onclick = () => abrirMenu(!$('#app').classList.contains('menu-abierto'));
  // En el celular el menú abierto tapa su botón: se cierra tocando fuera o con Escape
  $('#velo').onclick = () => abrirMenu(false);
}

function abrirMenu(abrir) {
  $('#app')?.classList.toggle('menu-abierto', abrir);
  $('#abrir-menu')?.setAttribute('aria-expanded', abrir);
}

export async function refrescarInsignias() {
  try {
    const k = (await api.get('/api/indicadores')).kpi;
    const b = $('#insignia-calidad');
    if (b) { b.textContent = k.pendientes_revision; b.classList.toggle('oculto', !k.pendientes_revision); }
  } catch { /* opcional */ }
}

async function render() {
  const g = ++generacion;
  if (limpiarVista) { try { limpiarVista(); } catch { /* nada */ } limpiarVista = null; }
  const ruta = sinBase(location.pathname).replace(/\/+$/, '') || '/';
  const r = RUTAS.find((x) => x.re.test(ruta));
  const vista = $('#vista');
  abrirMenu(false);
  if (!r) { montar(vista, html`<div class="vacio"><b>No existe esta página</b><a href="/" data-ruta>Volver al panel</a></div>`); return; }
  for (const a of document.querySelectorAll('#nav a')) {
    if (a.dataset.nav === r.nav) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  vista.classList.toggle('lleno', !!r.lleno);
  montar(vista, html`<div class="cargando"><div class="giro"></div></div>`);
  try {
    const fn = await r.carga();
    if (g !== generacion) return;
    const params = ruta.match(r.re).slice(1);
    const q = new URLSearchParams(location.search);
    // Cada vista recibe un contenedor nuevo: sus escuchas de eventos mueren con ella
    const cont = document.createElement('div');
    cont.className = r.lleno ? 'vista lleno' : 'vista';
    vista.replaceChildren(cont);
    const limpiar = await fn(cont, { params, q, ir });
    // Si mientras cargaba se pidió otra vista, esta ya sobra: se limpia en el acto (mapas, temporizadores…)
    if (g !== generacion) { try { limpiar?.(); } catch { /* nada */ } return; }
    limpiarVista = limpiar || null;
    // Una llamada que quedó sin registrar se recuerda al cargar cualquier vista
    try { revisarLlamadasPendientes(); } catch (err) { console.error(err); }
  } catch (e) {
    if (g !== generacion) return;
    if (e instanceof ErrorApi && e.estado === 401) return;
    console.error(e);
    montar(vista, html`<div class="vacio"><b>No se pudo cargar</b>${e.message}</div>`);
  }
  // El foco va al campo con autofocus de la vista (buscador de la reunión) o, si no hay, a la vista
  (vista.querySelector('[autofocus]') || vista).focus({ preventScroll: true });
}

document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-ruta]');
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || a.target) return;
  e.preventDefault();
  ir(a.getAttribute('href'));
});
window.addEventListener('popstate', render);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && $('#app')?.classList.contains('menu-abierto')) { abrirMenu(false); $('#abrir-menu').focus(); }
});
// Red de seguridad: un error de la API que ninguna acción atrapó se muestra en vez de perderse en la consola
window.addEventListener('unhandledrejection', (e) => {
  if (e.reason instanceof ErrorApi && e.reason.estado !== 401) aviso(e.reason.message, 'error', 6000);
});

// Lo que devuelven /api/yo y /api/login: usuario, csrf y, con usuarios, uid, rol, permisos y nombre
const datosSesion = (d) => ({ token: d.csrf, usuario: d.usuario, uid: d.uid, rol: d.rol, permisos: d.permisos, nombre: d.nombre });

async function iniciar() {
  aplicarTema(tema());
  try {
    const yo = await api.get('/api/yo');
    configurar({ ...datosSesion(yo), expira: expiro });
    armarEstructura();
    await render();
    refrescarInsignias();
  } catch (e) {
    const configurado = e instanceof ErrorApi ? e.detalle?.configurado !== false : true;
    vistaLogin($('#raiz'), { configurado, alEntrar: (d) => {
      configurar({ ...datosSesion(d), expira: expiro });
      armarEstructura();
      render();
      refrescarInsignias();
    } });
  }
}

function expiro() {
  aviso('La sesión terminó. Ingrese de nuevo.', 'error');
  setTimeout(() => location.reload(), 1200);
}

iniciar();
