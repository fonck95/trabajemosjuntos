// Arranque del panel: sesión, menú lateral según el rol y enrutado en el navegador.
import { api, borrarBorrador, configurar, ErrorApi, nombreRol, olvidarCatalogos, puede, sesion } from './api.js';
import { $, aviso, esMovil, html, icono, montar } from './ui.js';
import { dialogoIngreso, vistaLogin } from './vistas/login.js';
import { sinBase, url } from './base.js';
import { olvidarLlamada, revisarLlamadasPendientes } from './llamadas.js';

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
  { re: /^\/presentacion$/, nav: 'presentacion', permiso: 'presentacion.ver', lleno: true, carga: () => import('./vistas/presentacion.js').then((m) => m.vistaPresentacion) },
];
// [clave, texto, ruta, permiso]: el menú muestra solo lo que el rol puede abrir, en este orden. El coordinador ve el
// mismo menú que el administrador; lo que no puede (coordinadores, roles, ajustes de permisos) se oculta en cada vista
const NAV = [
  ['panel', 'Panel', '/', 'tablero.ver'], ['mapa', 'Mapa 3D', '/mapa', 'mapa.ver'],
  ['personas', 'Habitantes', '/personas', 'personas.listar'], ['trabajo', 'Mi trabajo', '/trabajo', 'trabajo.ver'],
  ['reuniones', 'Reuniones', '/reuniones', 'reuniones.ver'], ['calidad', 'Calidad de datos', '/calidad', 'calidad.ver'],
  ['presentacion', 'Presentación', '/presentacion', 'presentacion.ver'],
  ['importar', 'Importar y exportar', '/importar', 'importar'], ['usuarios', 'Usuarios', '/usuarios', 'usuarios.gestionar'],
  ['ajustes', 'Ajustes', '/ajustes', 'ajustes.gestionar'], ['cuenta', 'Mi cuenta', '/cuenta', 'cuenta'],
];
// Insignias del menú: { nav: clave de /api/insignias }
const INSIGNIAS = { calidad: 'calidad', trabajo: 'trabajo' };
const TITULOS_INSIGNIA = { calidad: 'Personas con coincidencias por revisar', trabajo: 'Pendientes de su trabajo' };

let limpiarVista = null;
let generacion = 0;

// Tema: «Sistema» (sin elección guardada: sigue al del dispositivo, también si cambia con la hora), «Claro» u «Oscuro»
const TEMAS = ['light', 'dark'];
function tema() {
  try { const t = localStorage.getItem('tema'); return TEMAS.includes(t) ? t : null; } catch { return null; }
}
function aplicarTema(t) {
  if (!TEMAS.includes(t)) t = null;
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  try { t ? localStorage.setItem('tema', t) : localStorage.removeItem('tema'); } catch { /* sin almacenamiento */ }
  marcarTema(t);
  window.dispatchEvent(new CustomEvent('tema'));
}
// El selector del menú muestra la elección vigente (si ya está pintado)
function marcarTema(t = tema()) {
  for (const b of document.querySelectorAll('#cambiar-tema [data-tema]')) b.setAttribute('aria-pressed', String((b.dataset.tema || null) === t));
}
export const temaOscuro = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
// Siguiendo al sistema, el mapa y los gráficos se enteran cuando el dispositivo cambia de tema
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => { if (!tema()) window.dispatchEvent(new CustomEvent('tema')); });

// Estilos de usuarios, cuenta e ingreso (web/css/acceso.css): se cargan aquí porque index.html no los enlaza
function cargarEstilos() {
  if (document.querySelector('link[data-acceso]')) return;
  const l = Object.assign(document.createElement('link'), { rel: 'stylesheet', href: url('/static/css/acceso.css') });
  l.dataset.acceso = '';
  document.head.append(l);
}

/** Inicio según el rol: el panel para el administrador y el coordinador, «Mi trabajo» para planilleros y consultores. */
const inicio = () => (puede('tablero.ver') ? '/' : '/trabajo');
const conPendientes = () => sesion.debeCambiarClave || sesion.compromisoPendiente;

export function ir(ruta, { reemplazar = false } = {}) {
  const destino = url(sinBase(ruta)); // acepta «/personas» o «/panel/personas»
  if (reemplazar) history.replaceState({}, '', destino);
  else history.pushState({}, '', destino);
  render();
}

function armarEstructura() {
  // Descargar es solo del administrador (adenda 2): para el coordinador la entrada es «Importar»
  const nav = NAV.filter(([, , , p]) => puede(p))
    .map((x) => (x[0] === 'importar' && !puede('exportar') ? [x[0], 'Importar', ...x.slice(2)] : x));
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
          <div class="tema" id="cambiar-tema" role="group" aria-label="Tema de la pantalla"><span>${icono('luna')} Tema</span>
            <div class="segmentado">${[['', 'Sistema'], ['light', 'Claro'], ['dark', 'Oscuro']].map(([k, t]) => html`<button type="button" data-tema="${k}" aria-pressed="false">${t}</button>`)}</div></div>
          <button id="salir">${icono('salir')} Cerrar sesión</button>
        </div>
      </aside>
      <div class="velo" id="velo"></div>
      <main class="contenido" id="vista" tabindex="-1"></main>
    </div>`);
  $('#usuario').textContent = `${sesion.nombre || sesion.usuario} · ${nombreRol(sesion.rol)}`;
  $('#salir').onclick = async () => {
    try { await api.post('/api/logout'); } catch { /* ya cerrada */ }
    olvidar();
    location.href = url('/');
  };
  $('#cambiar-tema').onclick = (e) => { const b = e.target.closest('[data-tema]'); if (b) aplicarTema(b.dataset.tema || null); };
  marcarTema();
  $('#abrir-menu').onclick = () => abrirMenu(!$('#app').classList.contains('menu-abierto'));
  // En el celular el menú abierto tapa su botón: se cierra tocando fuera o con Escape
  $('#velo').onclick = () => abrirMenu(false);
}

// Al cerrar sesión no queda nada de ella en el navegador
function olvidar() {
  olvidarCatalogos();
  borrarBorrador();
  try { olvidarLlamada(); } catch { /* nada */ }
  try { sessionStorage.removeItem('yj_agente'); } catch { /* bloqueado */ }
}

/** La ruta del panel que abre `ruta` («/personas/12»): {nav, permitida} o null si no es de RUTAS. El asistente valida
 * con esto lo que pide abrir y los enlaces de sus respuestas. */
function rutaPanel(ruta) {
  const r = RUTAS.find((x) => x.re.test(ruta));
  return r ? { nav: r.nav, permitida: puede(r.permiso) } : null;
}

// El asistente (web/js/agente.js) se carga la primera vez que el rol lo puede usar y vive en document.body, fuera de
// #raiz: sobrevive a los cambios de vista. Con la cuenta pendiente se oculta (el servidor también lo rechaza); si su
// rol no está entre los que lo usan, el propio asistente no se muestra (lo dice /api/agente/estado)
let agente = null;
function asegurarAgente() {
  if (conPendientes() || !puede('agente.usar')) {
    agente?.then((a) => a.ocultar()).catch(() => {});
    return;
  }
  agente ||= import('./agente.js').then((m) => m.montarAgente)
    .then((montar) => montar({ ir, rutaPanel, insignias: refrescarInsignias }));
  agente.then((a) => a.mostrar()).catch((e) => { console.error(e); agente = null; });
}

// Cada vista que termina de pintarse se anuncia (como 'tema'): el asistente devuelve el foco a su cuadro si la abrió él
// y, en el celular, se pliega si la persona eligió otra vista
function avisarVista(ruta, r, ok) {
  window.dispatchEvent(new CustomEvent('vista', { detail: { ruta, nav: r?.nav ?? null, ok } }));
}

/**
 * Abre o cierra el menú lateral. En el celular el menú cerrado solo se corre fuera de la pantalla: queda inerte para
 * que el tabulador y el lector de pantalla no entren en él; abierto, la vista de atrás es la inerte (el velo la tapa) y
 * el foco entra al primer enlace. Si el foco quedó en el menú que se cierra, vuelve al botón que lo abre.
 */
function abrirMenu(abrir) {
  const app = $('#app'), menu = $('#menu-lateral'), vista = $('#vista');
  if (!app || !menu || !vista) return;
  const estaba = app.classList.contains('menu-abierto');
  app.classList.toggle('menu-abierto', abrir);
  $('#abrir-menu')?.setAttribute('aria-expanded', abrir);
  const movil = esMovil();
  menu.inert = movil && !abrir;
  vista.inert = movil && abrir;
  if (movil && abrir && !estaba) {
    (menu.querySelector('#nav a[aria-current="page"]') || menu.querySelector('#nav a') || menu.querySelector('a, button'))?.focus({ preventScroll: true });
  }
  if (menu.inert && menu.contains(document.activeElement)) $('#abrir-menu')?.focus({ preventScroll: true });
}
// Al pasar de celular a escritorio (o al revés: girar la tableta, ensanchar la ventana) el menú vuelve a su estado
matchMedia('(max-width: 900px)').addEventListener?.('change', () => abrirMenu(false));

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
  asegurarAgente();
  if (!r) {
    montar(vista, html`<div class="vacio"><b>No existe esta página</b><a href="${inicio()}" data-ruta>Volver al inicio</a></div>`);
    avisarVista(ruta, null, false);
    return;
  }
  for (const a of document.querySelectorAll('#nav a')) {
    if (a.dataset.nav === r.nav) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  vista.classList.toggle('lleno', !!r.lleno);
  if (!puede(r.permiso)) {
    vista.classList.remove('lleno');
    montar(vista, html`<div class="vacio sin-acceso"><b>Sin acceso</b>Su rol no permite abrir esta sección.<a href="${inicio()}" data-ruta>Volver al inicio</a></div>`);
    avisarVista(ruta, r, false);
    return;
  }
  montar(vista, html`<div class="cargando"><div class="giro"></div></div>`);
  let ok = false;
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
    ok = true;
  } catch (e) {
    if (g !== generacion) return;
    if (e instanceof ErrorApi && e.estado === 401) return;
    if (e instanceof ErrorApi && (e.codigo === 'cambiar_clave' || e.codigo === 'compromiso')) return;
    console.error(e);
    const motivo = e instanceof ErrorApi && e.estado === 403 && e.codigo === 'permiso' ? 'Sin acceso' : 'No se pudo cargar';
    montar(vista, html`<div class="vacio"><b>${motivo}</b>${e.message}</div>`);
  }
  // El foco va al campo con autofocus de la vista (buscador de la reunión) o, si no hay, a la vista. Salvo que esté en
  // algo que vive fuera de #raiz y sobrevive a la vista (el asistente, un diálogo): la persona escribía ahí mientras
  // la vista cargaba, y lo que siguiera escribiendo se perdería
  const activo = document.activeElement;
  if (!activo || activo === document.body || $('#raiz').contains(activo)) {
    (vista.querySelector('[autofocus]') || vista).focus({ preventScroll: true });
  }
  avisarVista(ruta, r, ok);
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

// Lo que devuelven /api/yo y /api/login: usuario, csrf y, con usuarios, uid, rol, permisos (y sus excepciones),
// nombre y pendientes
const datosSesion = (d) => ({
  token: d.csrf, usuario: d.usuario, uid: d.uid, rol: d.rol, permisos: d.permisos, excepto: d.excepto, nombre: d.nombre,
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
  // Con la clave temporal o el compromiso pendiente, el servidor responde 403 a todo lo demás: sin insignias
  return render().then(() => { if (!conPendientes()) refrescarInsignias(); });
}

// Sin MongoDB (503) o sin red, el arranque no pide la clave: la sesión sigue en la cookie. Se muestra el aviso y se
// pregunta de nuevo cada ~5 s (o al tocar «Reintentar»); cuando la base vuelve, se entra con la misma sesión
const REINTENTO_MS = 5000;
let reloj = null;
let preguntando = false;

async function preguntarSesion() {
  if (preguntando) return;
  preguntando = true;
  clearTimeout(reloj);
  let yo;
  try {
    yo = await api.get('/api/yo');
  } catch (e) {
    preguntando = false;
    if (e instanceof ErrorApi && e.estado === 401) {
      vistaLogin($('#raiz'), { configurado: e.detalle?.configurado !== false, alEntrar: entrar });
    } else {
      sinConexion();
    }
    return;
  }
  preguntando = false;
  await entrar(yo);
}

function sinConexion() {
  const raiz = $('#raiz');
  if (!$('#reintentar', raiz)) {
    montar(raiz, html`
      <div class="login sin-conexion">
        <section class="caja">
          <div class="estado-conexion" role="alert">
            <h2>Sin conexión con la base de datos</h2>
            <p class="sec">El panel vuelve a intentarlo solo cada 5 segundos. Su sesión no se pierde: no hace falta ingresar de nuevo.</p>
            <button class="btn primario" id="reintentar" type="button">Reintentar</button>
            <p class="sec" id="intento" aria-live="polite"></p>
          </div>
        </section>
      </div>`);
    $('#reintentar', raiz).addEventListener('click', () => preguntarSesion());
  }
  const hora = new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  $('#intento', raiz).textContent = `Último intento: ${hora}`;
  reloj = setTimeout(preguntarSesion, REINTENTO_MS);
}

async function iniciar() {
  aplicarTema(tema());
  cargarEstilos();
  await preguntarSesion();
}

function expiro() {
  olvidar();
  aviso('La sesión terminó. Ingrese de nuevo.', 'error');
  setTimeout(() => location.reload(), 1200);
}

iniciar();
