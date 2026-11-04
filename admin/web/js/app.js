// Arranque del panel: sesión, menú lateral según el rol y enrutado en el navegador.
import { api, borrarBorrador, configurar, ErrorApi, olvidarCatalogos, puede, sesion } from './api.js';
import { $, aviso, html, icono, montar } from './ui.js';
import { dialogoIngreso, vistaLogin } from './vistas/login.js';
import { sinBase, url } from './base.js';
import { olvidarLlamada, revisarLlamadasPendientes } from './llamadas.js';
import { NOMBRES_ROL } from './modelo.js';

// Cada ruta lleva el permiso que pide (la interfaz solo oculta: el servidor decide)
const RUTAS = [
  { re: /^\/$|^\/panel$/, nav: 'panel', permiso: 'tablero.ver', carga: () => import('./vistas/panel.js').then((m) => m.vistaPanel) },
  { re: /^\/mapa$/, nav: 'mapa', permiso: 'mapa.ver', lleno: true, carga: () => import('./vistas/mapa.js').then((m) => m.vistaMapa) },
  { re: /^\/personas$/, nav: 'personas', permiso: 'personas.listar', carga: () => import('./vistas/personas.js').then((m) => m.vistaPersonas) },
  { re: /^\/personas\/(\d+)$/, nav: 'personas', permiso: 'personas.ver', carga: () => import('./vistas/ficha.js').then((m) => m.vistaFicha) },
  { re: /^\/reuniones$/, nav: 'reuniones', permiso: 'reuniones.ver', carga: () => import('./vistas/reuniones.js').then((m) => m.vistaReuniones) },
  { re: /^\/reuniones\/(\d+)$/, nav: 'reuniones', permiso: 'reuniones.ver', carga: () => import('./vistas/reunion.js').then((m) => m.vistaReunion) },
  { re: /^\/calidad$/, nav: 'calidad', permiso: 'calidad.ver', carga: () => import('./vistas/calidad.js').then((m) => m.vistaCalidad) },
  { re: /^\/importar$/, nav: 'importar', permiso: 'importar', carga: () => import('./vistas/importar.js').then((m) => m.vistaImportar) },
  { re: /^\/ajustes$/, nav: 'ajustes', permiso: 'ajustes.gestionar', carga: () => import('./vistas/ajustes.js').then((m) => m.vistaAjustes) },
  { re: /^\/trabajo$/, nav: 'trabajo', permiso: 'trabajo.ver', carga: () => import('./vistas/trabajo.js').then((m) => m.vistaTrabajo) },
  { re: /^\/usuarios$/, nav: 'usuarios', permiso: 'usuarios.gestionar', carga: () => import('./vistas/usuarios.js').then((m) => m.vistaUsuarios) },
  { re: /^\/usuarios\/(\d+)$/, nav: 'usuarios', permiso: 'usuarios.gestionar', carga: () => import('./vistas/usuarios.js').then((m) => m.vistaUsuario) },
  { re: /^\/cuenta$/, nav: 'cuenta', permiso: 'cuenta', carga: () => import('./vistas/cuenta.js').then((m) => m.vistaCuenta) },
];
// [clave, texto, ruta, permiso]: el menú muestra solo lo que el rol puede abrir, en este orden
const NAV = [
  ['panel', 'Panel', '/', 'tablero.ver'], ['mapa', 'Mapa 3D', '/mapa', 'mapa.ver'],
  ['personas', 'Habitantes', '/personas', 'personas.listar'], ['trabajo', 'Mi trabajo', '/trabajo', 'trabajo.ver'],
  ['reuniones', 'Reuniones', '/reuniones', 'reuniones.ver'], ['calidad', 'Calidad de datos', '/calidad', 'calidad.ver'],
  ['importar', 'Importar y exportar', '/importar', 'importar'], ['usuarios', 'Usuarios', '/usuarios', 'usuarios.gestionar'],
  ['ajustes', 'Ajustes', '/ajustes', 'ajustes.gestionar'], ['cuenta', 'Mi cuenta', '/cuenta', 'cuenta'],
];
// Insignias del menú: { nav: clave de /api/insignias }
const INSIGNIAS = { calidad: 'calidad', trabajo: 'trabajo' };
const TITULOS_INSIGNIA = { calidad: 'Personas con coincidencias por revisar', trabajo: 'Pendientes de su trabajo' };

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

// Estilos de usuarios, cuenta e ingreso (web/css/acceso.css): se cargan aquí porque index.html no los enlaza
function cargarEstilos() {
  if (document.querySelector('link[data-acceso]')) return;
  const l = Object.assign(document.createElement('link'), { rel: 'stylesheet', href: url('/static/css/acceso.css') });
  l.dataset.acceso = '';
  document.head.append(l);
}

/** Inicio según el rol: el panel para el administrador, «Mi trabajo» para planilleros y consultores. */
const inicio = () => (puede('tablero.ver') ? '/' : '/trabajo');
const conPendientes = () => sesion.debeCambiarClave || sesion.compromisoPendiente;

export function ir(ruta, { reemplazar = false } = {}) {
  const destino = url(sinBase(ruta)); // acepta «/personas» o «/panel/personas»
  if (reemplazar) history.replaceState({}, '', destino);
  else history.pushState({}, '', destino);
  render();
}

function armarEstructura() {
  const nav = NAV.filter(([, , , p]) => puede(p));
  // Sin tablero, «Mi trabajo» es el inicio y va primero
  if (!puede('tablero.ver')) nav.sort((x, y) => (y[0] === 'trabajo') - (x[0] === 'trabajo'));
  montar($('#raiz'), html`
    <div class="app" id="app">
      <div class="barra-movil"><button id="abrir-menu" aria-label="Menú" aria-expanded="false" aria-controls="menu-lateral">${icono('menu')}</button><b>Yondó · Base única</b></div>
      <aside class="lateral" id="menu-lateral" aria-label="Navegación">
        <a class="marca" href="${inicio()}" data-ruta><span class="sello">Y</span><span><b>Yondó</b><small>Base única · Panel</small></span></a>
        <nav class="nav" id="nav">${nav.map(([k, t, href]) => html`<a href="${href}" data-ruta data-nav="${k}">${icono(k)}<span>${t}</span>${INSIGNIAS[k] ? html`<span class="insignia oculto" id="insignia-${k}" title="${TITULOS_INSIGNIA[k]}"></span>` : ''}</a>`)}</nav>
        <div class="pie">
          <span>Sesión: <b id="usuario"></b></span>
          <button id="cambiar-tema">${icono('luna')} Cambiar tema</button>
          <button id="salir">${icono('salir')} Cerrar sesión</button>
        </div>
      </aside>
      <div class="velo" id="velo"></div>
      <main class="contenido" id="vista" tabindex="-1"></main>
    </div>`);
  $('#usuario').textContent = `${sesion.nombre || sesion.usuario} · ${NOMBRES_ROL[sesion.rol] || sesion.rol}`;
  $('#salir').onclick = async () => {
    try { await api.post('/api/logout'); } catch { /* ya cerrada */ }
    olvidar();
    location.href = url('/');
  };
  $('#cambiar-tema').onclick = () => aplicarTema(temaOscuro() ? 'light' : 'dark');
  $('#abrir-menu').onclick = () => abrirMenu(!$('#app').classList.contains('menu-abierto'));
  // En el celular el menú abierto tapa su botón: se cierra tocando fuera o con Escape
  $('#velo').onclick = () => abrirMenu(false);
}

// Al cerrar sesión no queda nada de ella en el navegador
function olvidar() {
  olvidarCatalogos();
  borrarBorrador();
  try { olvidarLlamada(); } catch { /* nada */ }
}

function abrirMenu(abrir) {
  $('#app')?.classList.toggle('menu-abierto', abrir);
  $('#abrir-menu')?.setAttribute('aria-expanded', abrir);
}

function insignia(nav, n) {
  const b = $(`#insignia-${nav}`);
  if (b) { b.textContent = n || ''; b.classList.toggle('oculto', !n); }
}

export async function refrescarInsignias() {
  try {
    const i = await api.get('/api/insignias');
    for (const [nav, clave] of Object.entries(INSIGNIAS)) insignia(nav, i[clave]);
  } catch (e) {
    // Un servidor sin /api/insignias: el administrador ve las coincidencias como antes
    if (e instanceof ErrorApi && e.estado === 404 && puede('tablero.ver')) {
      try { insignia('calidad', (await api.get('/api/indicadores')).kpi.pendientes_revision); } catch { /* opcional */ }
    }
  }
}

/** Aviso de un error de la API según su código: permisos y límites sin recargar, cuenta pendiente a «Mi cuenta». */
export function avisarError(e) {
  if (!(e instanceof ErrorApi) || e.estado === 401) return false;
  if (e.codigo === 'cambiar_clave' || e.codigo === 'compromiso') { irACuenta(e.codigo); return true; }
  if (e.codigo === 'volumen' || e.codigo === 'frecuencia') { aviso(e.message, 'error', 8000); return true; }
  aviso(e.message, 'error', 6000);
  return true;
}

function irACuenta(codigo) {
  if (codigo === 'cambiar_clave') sesion.debeCambiarClave = true;
  if (codigo === 'compromiso') sesion.compromisoPendiente = true;
  if (sinBase(location.pathname).replace(/\/+$/, '') !== '/cuenta') ir('/cuenta', { reemplazar: true });
}

async function render() {
  const g = ++generacion;
  if (limpiarVista) { try { limpiarVista(); } catch { /* nada */ } limpiarVista = null; }
  let ruta = sinBase(location.pathname).replace(/\/+$/, '') || '/';
  // Con la clave temporal o el compromiso pendientes, solo «Mi cuenta»
  if (conPendientes() && ruta !== '/cuenta') {
    history.replaceState({}, '', url('/cuenta'));
    ruta = '/cuenta';
  } else if (ruta === '/' && !puede('tablero.ver')) {
    history.replaceState({}, '', url(inicio()));
    ruta = inicio();
  }
  const r = RUTAS.find((x) => x.re.test(ruta));
  const vista = $('#vista');
  abrirMenu(false);
  if (!r) { montar(vista, html`<div class="vacio"><b>No existe esta página</b><a href="${inicio()}" data-ruta>Volver al inicio</a></div>`); return; }
  for (const a of document.querySelectorAll('#nav a')) {
    if (a.dataset.nav === r.nav) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  vista.classList.toggle('lleno', !!r.lleno);
  if (!puede(r.permiso)) {
    vista.classList.remove('lleno');
    montar(vista, html`<div class="vacio sin-acceso"><b>Sin acceso</b>Su rol no permite abrir esta sección.<a href="${inicio()}" data-ruta>Volver al inicio</a></div>`);
    return;
  }
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
    if (e instanceof ErrorApi && (e.codigo === 'cambiar_clave' || e.codigo === 'compromiso')) return;
    console.error(e);
    const motivo = e instanceof ErrorApi && e.estado === 403 && e.codigo === 'permiso' ? 'Sin acceso' : 'No se pudo cargar';
    montar(vista, html`<div class="vacio"><b>${motivo}</b>${e.message}</div>`);
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
  if (avisarError(e.reason)) e.preventDefault();
});

// Lo que devuelven /api/yo y /api/login: usuario, csrf y, con usuarios, uid, rol, permisos, nombre y pendientes
const datosSesion = (d) => ({
  token: d.csrf, usuario: d.usuario, uid: d.uid, rol: d.rol, permisos: d.permisos, nombre: d.nombre,
  debe_cambiar_clave: d.debe_cambiar_clave, compromiso_pendiente: d.compromiso_pendiente,
});

// Con algo escrito, una sesión vencida no recarga: se ingresa de nuevo en un diálogo (el mismo usuario) y la
// petición se reintenta
async function reingresar() {
  const d = await dialogoIngreso({ usuario: sesion.usuario });
  if (!d) throw new ErrorApi(401, 'La sesión terminó');
  if (d.uid !== sesion.uid) { location.reload(); throw new ErrorApi(401, 'Otra cuenta'); }
  configurar(datosSesion(d));
  return d;
}

const ganchos = { expira: expiro, reingresar, pendiente: irACuenta };

function entrar(d) {
  configurar({ ...datosSesion(d), ...ganchos });
  armarEstructura();
  return render().then(() => refrescarInsignias());
}

async function iniciar() {
  aplicarTema(tema());
  cargarEstilos();
  let yo;
  try {
    yo = await api.get('/api/yo');
  } catch (e) {
    const configurado = e instanceof ErrorApi ? e.detalle?.configurado !== false : true;
    vistaLogin($('#raiz'), { configurado, alEntrar: entrar });
    return;
  }
  await entrar(yo);
}

function expiro() {
  olvidar();
  aviso('La sesión terminó. Ingrese de nuevo.', 'error');
  setTimeout(() => location.reload(), 1200);
}

iniciar();
