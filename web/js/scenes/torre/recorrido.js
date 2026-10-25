// Modo «Recorrer por dentro» de la torre (equipo C; especificación de integración, 6 y 16, que prevalece): se camina en
// primera persona por TODA la torre —exteriores, pisos 1 a 4, escaleras, ascensores, bloque técnico y cubierta— con un
// solo nivel armado a la vez, y se inspecciona todo lo que se ve: cada unidad de dotación, equipamiento fijo, laboratorio e
// infraestructura abre su ficha con su contenido, cada recinto la suya, y el inventario completo se busca y se filtra con
// «Ir a», que lleva al caminante frente a la unidad y la resalta.
//
// Cómo se mueve (6.4 y 6.8): el caminante vive en coordenadas de planta (x al este, y al norte; h = altura de sus pies
// sobre el piso terminado del nivel). Cada cuadro, una sola función registrada con st.onFrame lee las intenciones de
// controles_fp.js, mueve al caminante por la rejilla de colisión del nivel (planta3d.js, celdas de 0,10 m, muros y equipos
// grandes inflados 0,30 m, deslizamiento por ejes) y pone la cámara en los ojos (1,60 m) con controls.target medio metro
// adelante: OrbitControls.update() reproduce la misma posición y orientación y adaptDepth deja el plano cercano en 0,05 m.
// En las celdas de escalera el piso es la parte (tramo o descanso) de este nivel, del de abajo o del descanso del de
// arriba que queda más cerca de los pies: así se sube y se baja caminando, y el nivel cambia cuando los ojos pasan su losa.
// Las puertas que unen niveles (exteriores, bloque técnico, terraza) llevan al otro nivel al cruzarlas; el ascensor tiene
// botones de piso, y R/F (o RePág/AvPág) saltan al vestíbulo de ascensores del nivel de arriba o de abajo.
// Espacio salta (gravedad y techo del nivel): en el aire se pasa por encima de los equipos y obstáculos más bajos que los
// pies y se cae sobre ellos (la rejilla guarda su altura); muros, columnas, barandas y vacíos no se saltan. V pasa al modo
// espectador (como en Minecraft: vuela hacia donde mira, Espacio sube, Shift baja, la rueda cambia la velocidad y atraviesa
// muros y losas; el nivel armado es el que tiene los ojos) y P pone el recuadro en pantalla completa, con el puntero tomado
// y la ficha de lo tocado a un lado.
import { THREE, tokens, onTheme, engine } from '../../core.js';
import { crearCapaEquipos, unidadesDelPiso, geometria as geometriaEquipo, nominal as nominalEquipo, materiales as materialesEquipos } from '../../equipos3d.js';
import { construirPiso, rejillaColision, cotaPiso, cotaParte, enPoligono, puntoInterior, bordeAlto } from './planta3d.js';
import { crearControles } from './controles_fp.js';
import { crearMinimapa } from './minimapa.js';
import { crearInventario, montarBuscador, NOMBRE_NIVEL, ESTADOS_R } from './inventario.js';

const OJOS = 1.6, VEL = 1.4, VEL_RAPIDA = 3.0, GIRO = (120 * Math.PI) / 180, PITCH_MAX = (80 * Math.PI) / 180;
const RADIO = 0.2;                  // radio del caminante en la rejilla (una puerta de 0,90 m deja 0,40 m de paso)
const PASO_Z = 0.3;                 // desnivel máximo entre dos sub-pasos (escalones, rampas): más que eso es un borde
const SALTO = 1.2, GRAVEDAD = 20, V_SALTO = Math.sqrt(2 * GRAVEDAD * SALTO);   // los pies suben 1,20 m (como en Minecraft)
const CABEZA = 0.12;                // de los ojos a la coronilla: lo que no puede pasar del cielo raso
const TECHO_ESCALERA = 2.3;         // en la escalera, sobre el piso que se pisa: el tramo de arriba (NSR-10 K.3, 2,05 m libres)
const VEL_ESPECTADOR = 4, ESPECTADOR_MIN = 0.25, ESPECTADOR_MAX = 8;   // m/s y el multiplicador de la rueda
const SUBE = 1.65, BAJA = 1.85;     // en la escalera: cambia al nivel de arriba con los ojos a 0,05 m de su losa y vuelve con histéresis
const FOV_TORRE = 36, ORDEN = ['BT', 'EXT', 'P1', 'P2', 'P3', 'P4', 'CUB'];
const CIELO_ABIERTO = new Set(['EXT', 'CUB']);   // sin cielo raso: el salto no tiene techo
const ETIQUETAS = 12, DIST_ETIQUETAS = 6;
const rad = (g) => (g * Math.PI) / 180, grados = (r) => (r * 180) / Math.PI;
const normGrados = (g) => ((g % 360) + 360) % 360;
const movReducido = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const CLAVE_PISO = { P1: '1', P2: '2', P3: '3', P4: '4', CUB: 'cubierta' };
const SIGLA_NIVEL = { EXT: 'Ext.', P1: 'P1', P2: 'P2', P3: 'P3', P4: 'P4', BT: 'BT', CUB: 'Cub.' };
const CORTO_NIVEL = { EXT: 'Exteriores', P1: 'Piso 1', P2: 'Piso 2', P3: 'Piso 3', P4: 'Piso 4', BT: 'Bloque técnico', CUB: 'Cubierta' };
const DEL_NIVEL = { EXT: 'de los exteriores', P1: 'del piso 1', P2: 'del piso 2', P3: 'del piso 3', P4: 'del piso 4', BT: 'del bloque técnico', CUB: 'de la cubierta' };
const MODELOS_IMPLEMENTO = new Set(['reactivo_caja', 'frasco_reactivo', 'gradilla_tubos']);

// piso del contrato (1-4, 'BT', 'EXT', 'CUB', 'cubierta', 'exterior'…) → id del nivel de la planta
export function idNivel(p) {
  if (p == null || p === '') return null;
  const s = String(p);
  if (ORDEN.includes(s)) return s;
  if (/^[1-4]$/.test(s)) return `P${s}`;
  if (/cubierta|terraza/i.test(s)) return 'CUB';
  if (/exterior/i.test(s)) return 'EXT';
  if (/bloque|^bt$/i.test(s)) return 'BT';
  return null;
}

// ---------------------------------------------------------------- alcance: ningún recinto encerrado por equipos (16.1)
// Despeje de cada puerta: rectángulo del ancho del vano por 0,9 m a cada lado del muro (lo que está al lado del vano no lo
// estrecha más que el propio muro, que también se infla con el radio del caminante)
export function despejesPuertas(nivel, muros) {
  const out = [];
  for (const p of nivel.puertas || []) {
    const m = muros.get(p.muro);
    if (!m || !p.centro) continue;
    const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1, ux = (m.b[0] - m.a[0]) / L, uy = (m.b[1] - m.a[1]) / L;
    out.push({ x: p.centro[0], y: p.centro[1], ux, uy, hl: Math.max(0.2, (+p.ancho || 0.9) / 2 - 0.02), hw: 0.9 + (+m.espesor || 0.15) / 2, puerta: p.id });
  }
  return out;
}
// ¿se cruzan la huella girada de un equipo ({ x, y, w, d, rot }) y un despeje ({ x, y, ux, uy, hl, hw })? (ejes separadores)
export function cruzanOBB(o, q) {
  const c = Math.cos(o.rot || 0), s = Math.sin(o.rot || 0);
  const A = [[c, s, o.w / 2], [-s, c, o.d / 2]], B = [[q.ux, q.uy, q.hl], [-q.uy, q.ux, q.hw]];
  const dx = q.x - o.x, dy = q.y - o.y;
  for (const [ax, ay] of [...A, ...B]) {
    const ra = A.reduce((t, [bx, by, h]) => t + h * Math.abs(ax * bx + ay * by), 0);
    const rb = B.reduce((t, [bx, by, h]) => t + h * Math.abs(ax * bx + ay * by), 0);
    if (Math.abs(dx * ax + dy * ay) > ra + rb - 1e-6) return false;
  }
  return true;
}
// recintos de un nivel que el recorrido no ofrece como destino: cabinas de montacargas (se cargan, no se camina en ellas)
export function recintosNoDestino(nivel) {
  return new Set((nivel.nucleos || []).filter((n) => n.tipo === 'montacargas').flatMap((n) => n.recintos || [n.recinto]).filter(Boolean));
}
// semillas del alcance: entradas del recorrido, pasos a otros niveles y puntos de ascensores y escaleras del nivel
export function semillasAlcance(nivel, clave) {
  const s = [];
  for (const q of nivel.entradas_recorrido || []) if (q.punto) s.push(q.punto);
  for (const q of nivel.pasos_entre_niveles || []) if (q.punto) s.push(q.punto);
  for (const cx of nivel.conexiones_verticales || []) if ((cx.tipo === 'ascensor' || cx.tipo === 'escalera') && cx.puntos?.[clave]) s.push(cx.puntos[clave]);
  return s;
}
// Índices de las huellas que hay que quitar para que cada recinto transitable quede unido a una semilla. Camino de costo
// mínimo (0-1: celda tapada solo por equipos = 1) sobre la rejilla sin equipos; se quitan las huellas cuyas celdas
// infladas tocan ese camino. Devuelve un Set vacío si todo se alcanza.
export function huellasQueEncierran(nivel, base, llena, obstaculos, clave) {
  const quitar = new Set();
  if (!obstaculos.length) return quitar;
  const { nx, ny, x0, y0, celda } = base, N = nx * ny, B = base.datos, F = llena.datos;
  const idx = (x, y) => { const i = Math.floor((x - x0) / celda), j = Math.floor((y - y0) / celda); return i < 0 || j < 0 || i >= nx || j >= ny ? -1 : j * nx + i; };
  const D = new Int32Array(N).fill(0x3fffffff), P = new Int32Array(N).fill(-1);
  const cubos = [[]];
  const sembrar = ([x, y]) => {
    // la celda libre (sin equipos) más cercana a la semilla, a menos de 2 m
    const i0 = Math.floor((x - x0) / celda), j0 = Math.floor((y - y0) / celda);
    for (let r = 0; r <= 20; r++) for (let dj = -r; dj <= r; dj++) for (let di = -r; di <= r; di++) {
      if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
      const i = i0 + di, j = j0 + dj;
      if (i < 0 || j < 0 || i >= nx || j >= ny) continue;
      const k = j * nx + i;
      if (B[k] === 1) continue;
      const c = F[k] === 1 ? 1 : 0;
      if (c < D[k]) { D[k] = c; (cubos[c] ||= []).push(k); }
      return;
    }
  };
  for (const s of semillasAlcance(nivel, clave)) sembrar(s);
  for (let c = 0; c < cubos.length; c++) {
    const L = cubos[c] || [];
    for (let q = 0; q < L.length; q++) {
      const k = L[q];
      if (D[k] !== c) continue;
      const i = k % nx;
      for (const kk of [i > 0 ? k - 1 : -1, i < nx - 1 ? k + 1 : -1, k - nx, k + nx]) {
        if (kk < 0 || kk >= N || B[kk] === 1) continue;
        const nc = c + (F[kk] === 1 ? 1 : 0);
        if (nc < D[kk]) { D[kk] = nc; P[kk] = k; (cubos[nc] ||= []).push(kk); }
      }
    }
  }
  const fuera = recintosNoDestino(nivel), margen = (base.radio || 0.3) + 2 * celda;
  for (const r of nivel.recintos || []) {
    if (r.transitable === false || fuera.has(r.id) || !r.poligono?.length) continue;
    // la celda del recinto con el camino más barato
    let a0 = Infinity, b0 = Infinity, a1 = -Infinity, b1 = -Infinity;
    for (const [x, y] of r.poligono) { a0 = Math.min(a0, x); b0 = Math.min(b0, y); a1 = Math.max(a1, x); b1 = Math.max(b1, y); }
    let mejor = -1, dm = 0x3fffffff;
    for (let y = b0 + celda / 2; y < b1 && dm > 0; y += celda) for (let x = a0 + celda / 2; x < a1; x += celda) {
      const k = idx(x, y);
      if (k < 0 || B[k] === 1 || D[k] >= dm || !enPoligono(x, y, r.poligono)) continue;
      dm = D[k]; mejor = k;
      if (!dm) break;
    }
    if (mejor < 0 || dm === 0 || dm >= 0x3fffffff) continue;
    // las huellas que tapan las celdas del camino
    for (let k = mejor; k >= 0; k = P[k]) {
      if (F[k] !== 1) continue;
      const px = x0 + ((k % nx) + 0.5) * celda, py = y0 + (((k / nx) | 0) + 0.5) * celda;
      obstaculos.forEach((o, n) => {
        if (quitar.has(n)) return;
        const c = Math.cos(o.rot || 0), s = Math.sin(o.rot || 0), dx = px - o.x, dy = py - o.y;
        if (Math.abs(dx * c + dy * s) <= o.w / 2 + margen && Math.abs(-dx * s + dy * c) <= o.d / 2 + margen) quitar.add(n);
      });
    }
  }
  return quitar;
}

export async function montar(ctx) {
  const { st, hud, panel, ficha, datos = {}, textos } = ctx;
  const { esc, escH, limpio } = textos;
  const stage = st.el;
  const plantas = datos.plantas || null, inv = datos.inventario || null, hab = datos.habilitacion || null;
  const niveles = new Map((plantas?.niveles || []).map((n) => [n.id, n]));
  const grupos = plantas?.grupos_1633 || {};
  const modelo = inv ? crearInventario(inv, { plantas, habilitacion: hab, textos }) : null;
  const ordenNiveles = ORDEN.filter((id) => niveles.has(id));
  const qa = new URLSearchParams(location.search).has('qa');

  // ---------------------------------------------------------------- estado
  let camaraAntes = null;
  let activo = false, cur = null, guardado = null, luz = null, sueloOculto = null, quitarTema = null;
  // h: pies sobre el piso del nivel (encima de un equipo o en el aire, más arriba que el piso); hp: el piso que se pisa
  // (el del recinto o la parte de la escalera), referencia de las escaleras y los bordes; vz y aire: el salto
  const w = { x: 0, y: 0, h: 0, hp: 0, vz: 0, aire: false, yaw: 0, pitch: 0 };
  let espectador = false, velEspectador = 1, tEspectador = 0, enPantalla = false;
  let forzar = false, aspecto = 0, ultimoFundido = false, saltando = false, tiempoNivel = 0, tiempos = null;
  const capas = { faltantes: false, estado: false, contraste: false, infraestructura: true };
  let recintoActual = null, subActual = null, tRecinto = 0, resaltados = null, ultimoEsc = 0;
  let marcaEtiquetas = { x: Infinity, y: Infinity, rec: null }, marcaMapa = { x: Infinity, y: Infinity, yaw: Infinity, rec: null, t: 0 };
  let T = tokens();

  // ---------------------------------------------------------------- HUD sobre el recuadro (torre.hud.recorrido)
  hud.innerHTML = '';
  hud.classList.add('reco-hud');
  const el = (tag, cls, html = '', attrs = {}) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  const barra = el('div', 'nav3d reco-barra', `<span class="nav3d-name reco-b-nivel"><span class="reco-largo"></span><span class="reco-corto"></span></span>
    <button type="button" data-acc="subir" aria-label="Subir de nivel (R o RePág)" title="Subir de nivel (R o RePág)">▲</button>
    <button type="button" data-acc="bajar" aria-label="Bajar de nivel (F o AvPág)" title="Bajar de nivel (F o AvPág)">▼</button>
    <span class="sep"></span>
    <button type="button" data-acc="mapa" aria-pressed="true" title="Minimapa (M)">Mapa</button>
    <button type="button" data-acc="bt" class="reco-ancho" title="Ir al bloque técnico por su puerta exterior">Bloque técnico</button>
    <button type="button" data-acc="mirar" class="reco-raton" title="Mirar con el ratón (o doble clic); Esc lo suelta">Mirar con el ratón</button>
    <button type="button" data-acc="espectador" class="reco-ancho" aria-pressed="false" title="Modo espectador (V): vuela y atraviesa muros y losas; Espacio sube y Shift baja">Espectador</button>
    <button type="button" data-acc="pantalla" class="reco-ancho" aria-pressed="false" title="Pantalla completa (P)">Pantalla completa</button>
    <button type="button" data-acc="salir" title="Salir del recorrido (Esc)">Salir</button>`, { role: 'toolbar', 'aria-label': 'Recorrido por la torre' });
  const asc = el('div', 'reco-asc', '', { role: 'group', 'aria-label': 'Botones del ascensor' });
  asc.hidden = true;
  const salida = el('button', 'reco-salida', 'Salir del edificio', { type: 'button' });
  salida.hidden = true;
  const pista = el('p', 'reco-pista');
  pista.hidden = true;
  const aviso = el('p', 'reco-aviso', '', { role: 'status' });
  aviso.hidden = true;
  const mira = el('div', 'reco-mira', '', { 'aria-hidden': 'true' });
  mira.hidden = true;
  const fundido = el('div', 'reco-fundido', '', { 'aria-hidden': 'true' });
  // dónde se está, sobre el recuadro y en todos los anchos (en el teléfono el minimapa está oculto y el panel queda abajo);
  // el panel lo anuncia en su región viva, así que esta línea no se lee dos veces
  const donde = el('p', 'reco-donde', '', { 'aria-hidden': 'true' });
  // la ficha de lo tocado puede quedar fuera de la pantalla (en el teléfono, debajo del recuadro): este botón la trae
  const verFicha = el('button', 'reco-verficha', '', { type: 'button' });
  verFicha.hidden = true;
  // modo espectador: aviso fijo con sus teclas; pantalla completa: ayuda de los controles al entrar y, en un lateral bajo
  // la barra, la ficha de lo tocado (la tarjeta de la ficha queda fuera del recuadro, que es lo único que se ve)
  const insignia = el('p', 'reco-espectador', 'Espectador: vuela hacia donde miras · Espacio sube · Shift baja · rueda: velocidad · V vuelve a caminar', { 'aria-hidden': 'true' });
  insignia.hidden = true;
  const ayudaFs = el('div', 'reco-fs-ayuda', `<p><b>Pantalla completa</b></p>
    <ul><li><kbd>W A S D</kbd> caminar · <kbd>Shift</kbd> correr · <kbd>Espacio</kbd> saltar</li>
    <li>Ratón: mirar · clic: ficha de lo que está en la mira</li>
    <li><kbd>V</kbd> espectador: vuela y atraviesa muros (<kbd>Espacio</kbd> sube, <kbd>Shift</kbd> baja)</li>
    <li><kbd>R</kbd> <kbd>F</kbd> cambian de piso · <kbd>M</kbd> minimapa · <kbd>Esc</kbd> suelta el ratón · <kbd>P</kbd> sale de pantalla completa</li></ul>`, { 'aria-hidden': 'true' });
  ayudaFs.hidden = true;
  const lateral = el('aside', 'reco-fs-ficha', '<button type="button" class="reco-fs-cerrar" aria-label="Cerrar la ficha">×</button>', { 'aria-label': 'Ficha' });
  lateral.hidden = true;
  hud.append(barra, donde, asc, salida, verFicha, pista, aviso, mira, insignia, ayudaFs, lateral, fundido);
  const nombreBarra = barra.querySelector('.reco-b-nivel');
  const ponerNombreBarra = (id) => {
    nombreBarra.querySelector('.reco-largo').textContent = CORTO_NIVEL[id] || id;
    nombreBarra.querySelector('.reco-corto').textContent = SIGLA_NIVEL[id] || id;
    nombreBarra.title = CORTO_NIVEL[id] || id;
  };
  const btnMapa = barra.querySelector('[data-acc="mapa"]'), btnPuntero = barra.querySelector('[data-acc="mirar"]');
  const btnEspectador = barra.querySelector('[data-acc="espectador"]'), btnPantalla = barra.querySelector('[data-acc="pantalla"]');
  const mapa = crearMinimapa(hud, { alTocar: (x, y) => { const r = cur?.planta.recintoEn(x, y); if (r) irA({ nivel: cur.id, recinto: r, ficha: false }); } });
  let tAviso = 0;
  function avisar(txt, ms = 2600) { aviso.textContent = txt; aviso.hidden = false; clearTimeout(tAviso); tAviso = setTimeout(() => { aviso.hidden = true; }, ms); }

  // ---------------------------------------------------------------- panel (torre.panel.recorrido)
  const BOTONES_NIVEL = ordenNiveles.slice().sort((a, b) => ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'].indexOf(a) - ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'].indexOf(b));
  panel.innerHTML = `<div class="reco-panel">
      <p class="eyebrow reco-p-nivel"></p>
      <div class="reco-aqui" aria-live="polite" aria-atomic="true"><h3 class="reco-rec" tabindex="-1"></h3><p class="note reco-rec-sub"></p></div>
      <p class="reco-rec-acc"><button type="button" class="btn ghost reco-ficha-rec">Ficha del recinto</button></p>
      <div class="seg wrap-seg reco-capas" role="group" aria-label="Capas del recorrido">
        <button type="button" data-capa="faltantes" aria-pressed="false" title="Unidades del cierre de brechas en 3D y recintos con exigencias que faltan">Faltantes</button>
        <button type="button" data-capa="estado" aria-pressed="false" title="Color del piso según el cumplimiento en dotación e infraestructura de cada recinto">Cumplimiento en dotación e infraestructura</button>
        <button type="button" data-capa="contraste" aria-pressed="false" title="Color del piso según el contraste con el proyecto tipo">Comparar con el proyecto tipo</button>
        <button type="button" data-capa="infraestructura" aria-pressed="true" title="Lavamanos, tomas de gases, extintores, señalización y demás infraestructura que piden las normas">Infraestructura</button>
      </div>
      <div class="reco-leyenda note" hidden></div>
      <h4>En este recinto</h4>
      <div class="reco-lista-rec"></div>
      <details class="fold reco-ira" open><summary>Ir a otro lugar</summary>
        <div class="seg wrap-seg reco-niveles" role="group" aria-label="Niveles">
          ${BOTONES_NIVEL.map((id) => `<button type="button" data-nivel="${id}">${esc(CORTO_NIVEL[id])}</button>`).join('')}
          ${niveles.get('P2')?.entradas_recorrido?.some((e) => e.id === 'laboratorio') ? '<button type="button" data-entrada="P2:laboratorio">Laboratorio</button>' : ''}
        </div>
        <p class="note reco-ira-t"></p>
        <ul class="reco-recintos"></ul>
      </details>
      <details class="fold reco-inv"><summary>Inventario completo de la torre${modelo ? ` (${modelo.total.toLocaleString('es-CO')} unidades)` : ''}</summary><div class="reco-buscador"></div></details>
      <p class="note">Planta ilustrativa: el diseño real lo hace el arquitecto con matrícula. Teclado: W A S D o flechas para caminar, Shift para ir rápido, Espacio para saltar, ← → para girar, R y F suben y bajan, V el modo espectador (vuela y atraviesa muros: Espacio sube, Shift baja, la rueda cambia la velocidad), P la pantalla completa, M el minimapa, I lleva a este panel y Esc sale.</p>
    </div>`;
  const $ = (s) => panel.querySelector(s);
  const pNivel = $('.reco-p-nivel'), pRec = $('.reco-rec'), pSub = $('.reco-rec-sub'), pLista = $('.reco-lista-rec'), pRecintos = $('.reco-recintos'), pIraT = $('.reco-ira-t'), pLeyenda = $('.reco-leyenda');
  const btnContraste = $('[data-capa="contraste"]');
  if (!datos.coloresContraste?.size) { btnContraste.disabled = true; btnContraste.title = 'El contraste con el proyecto tipo todavía no se publicó'; }
  let buscador = null;
  $('.reco-inv').addEventListener('toggle', (ev) => {
    if (!ev.target.open || buscador || !modelo) return;
    buscador = montarBuscador($('.reco-buscador'), modelo, { irA: (id, o = {}) => irA({ unidad: id, implementos: !!o.implementos, alRecuadro: true }), textos });
  });

  // ---------------------------------------------------------------- etiquetas 3D (6.5: recinto actual, < 6 m, máximo 12)
  const etiquetas = [];
  const asegurarEtiquetas = () => { while (etiquetas.length < ETIQUETAS) { const o = st.label('', 'lbl-node reco-lbl', [0, -999, 0]); o.visible = false; etiquetas.push(o); } };

  // ---------------------------------------------------------------- controles
  const ctl = crearControles({
    stage,
    activo: () => activo && st.isActive() && st.inView && !ctx.raiz.hidden,
    // en pantalla completa, un clic en el lienzo sin el puntero tomado lo toma (como en un juego); con él, el clic elige
    // lo que está en la mira
    alSeleccionar: (e) => { if (enPantalla && !e.centro && ctl.puedeBloquear() && !ctl.tomado()) { ctl.tomarPuntero(); return; } seleccionar(e); },
    alAccion: accion,
    contenedorJoystick: hud,
  });

  // ---------------------------------------------------------------- luz, cámara y controles (6.7 y 6.8)
  function ajustarControles() {
    const c = st.controls;
    c.update();
    c.enableDamping = false;
    c.enableRotate = false; c.enableZoom = false; c.enablePan = false;
    c.minDistance = 0.01; c.maxDistance = 10;
    c.minPolarAngle = 0.01; c.maxPolarAngle = Math.PI - 0.01;
    st.userMoved = true;
    ajustarFov();
  }
  // fov vertical del 6.4 (≈ 75° horizontales, entre 60° y 90° verticales); en un recuadro muy vertical (teléfono) se abre
  // lo justo para no bajar de 70° horizontales (13.3), hasta 100°
  function fovRecorrido() {
    const a = st.camera.aspect || 1, f = THREE.MathUtils.clamp(grados(2 * Math.atan(Math.tan(rad(37.5)) / a)), 60, 90);
    return Math.max(f, Math.min(100, grados(2 * Math.atan(Math.tan(rad(35.05)) / a))));
  }
  function ajustarFov() {
    aspecto = st.camera.aspect;
    const f = fovRecorrido();
    if (Math.abs(st.camera.fov - f) > 1e-3) { st.camera.fov = f; st.camera.updateProjectionMatrix(); }
  }
  function guardarCamara() {
    const c = st.controls;
    guardado = {
      target: c.target.clone(), posicion: st.camera.position.clone(), minDistance: c.minDistance, maxDistance: c.maxDistance, minPolarAngle: c.minPolarAngle,
      maxPolarAngle: c.maxPolarAngle, enableDamping: c.enableDamping, enableRotate: c.enableRotate, enableZoom: c.enableZoom, enablePan: c.enablePan, fov: st.camera.fov,
    };
    if (qa) { const { target, posicion, ...num } = guardado; camaraAntes = num; }
  }
  function restaurarCamara() {
    if (!guardado) return;
    const c = st.controls, g = guardado;
    Object.assign(c, { minDistance: g.minDistance, maxDistance: g.maxDistance, minPolarAngle: g.minPolarAngle, maxPolarAngle: g.maxPolarAngle, enableDamping: g.enableDamping, enableRotate: g.enableRotate, enableZoom: g.enableZoom, enablePan: g.enablePan });
    c.target.copy(g.target);
    st.camera.position.copy(g.posicion);
    st.camera.fov = FOV_TORRE;
    st.camera.updateProjectionMatrix();
    c.update();
    guardado = null;
  }
  function encenderLuces(on) {
    // adentro no hay sombras: el sol baja y el hemisferio sube, con el suelo claro para que los cielos rasos y las caras
    // de los muros que no mira el sol no queden en penumbra
    if (on && !luz) {
      luz = { sombra: st.sunLight.castShadow, sol: st.sunLight.intensity, hemi: st.hemi.intensity, suelo: st.hemi.groundColor.clone(), amb: new THREE.AmbientLight(0xffffff, 0.3) };
      st.sunLight.castShadow = false;
      st.sunLight.intensity = luz.sol * 0.55;
      st.hemi.intensity = Math.max(0.9, luz.hemi * 3);
      st.hemi.groundColor.set(0xb4b1a8);
      st.scene.add(luz.amb);
    } else if (!on && luz) {
      st.sunLight.castShadow = luz.sombra;
      st.sunLight.intensity = luz.sol;
      st.hemi.intensity = luz.hemi;
      st.hemi.groundColor.copy(luz.suelo);
      luz.amb.removeFromParent();
      luz.amb.dispose?.();
      luz = null;
      st.updateShadows();
    }
  }
  // el suelo de la escena (a −0,06 m) y el terreno del modelo («entorno», a la cota 0) atraviesan los recintos del bloque
  // técnico, que está a −1,50: se ocultan solo allí y vuelven al salir de él
  function suelo(ocultar) {
    if (ocultar && !sueloOculto) {
      sueloOculto = st.scene.children.filter((o) => o.isMesh && o.geometry?.type === 'CircleGeometry' && o.visible);
      st.scene.traverse((o) => { if (o.name === 'entorno' && o.visible) sueloOculto.push(o); });
      sueloOculto.forEach((o) => { o.visible = false; });
    } else if (!ocultar && sueloOculto) { sueloOculto.forEach((o) => { o.visible = true; }); sueloOculto = null; }
  }

  // ---------------------------------------------------------------- un nivel armado: planta, equipos, rejilla y superficies
  const colorEstado = (e) => ({ cumple: T.good, parcial: T.warn, falta: T.bad, documento_pendiente: T.data }[e] || null);
  const tono = (c, k = 0.35) => (c ? c.clone().lerp(new THREE.Color(1, 1, 1), k) : null);
  const nivelVecino = (n, campo) => idNivel((n.escaleras || []).find((e) => e[campo])?.[campo]);

  function armarCapa(nv, unidades, calidad) {
    const lista = capas.infraestructura ? unidades : unidades.filter((u) => modelo?.unidad(u.id)?.capa !== 'infraestructura');
    return crearCapaEquipos(lista, inv?.catalogo, nv, { calidad });
  }
  const huellasQuitadas = new Map();   // nivel|infraestructura → ids de las huellas que encerraban recintos
  function armarNivel(id) {
    const t0 = performance.now();
    const nivel = niveles.get(id);
    const idAb = nivelVecino(nivel, 'baja_a'), idAr = nivelVecino(nivel, 'sube_a');
    const nAb = idAb && niveles.get(idAb), nAr = idAr && niveles.get(idAr);
    const calidad = engine.tier || 'media';
    // contexto que se ve por las puertas y ventanas: en los exteriores, el piso 1 entero (sin equipos); en el piso 1, los
    // exteriores. Así la puerta principal no da a una torre hueca ni la galería a un vacío
    const idCtx = id === 'EXT' ? 'P1' : id === 'P1' ? 'EXT' : null, nCtx = idCtx && niveles.get(idCtx);
    const planta = construirPiso(nivel, {
      tier: calidad, colorPor: 'grupo', grupos, cielo: true, envolvente: true, abajo: nAb || null, contexto: [...niveles.values()],
      omitirContexto: nCtx && id === 'EXT' ? ['P1'] : [], huella: !(nCtx && id === 'EXT'),
    });
    st.scene.add(planta.grupo);
    const t1 = performance.now();
    const plantaCtx = nCtx ? construirPiso(nCtx, { tier: calidad, colorPor: 'grupo', grupos, cielo: true, envolvente: false, contexto: [niveles.get('P1')], huella: false, senales: idCtx === 'P1' }) : null;
    if (plantaCtx) st.scene.add(plantaCtx.grupo);
    const t2 = performance.now();
    // unidades del nivel (las de zona sin recinto en los datos toman el del inventario, que sale de su posición)
    const unidades = inv ? unidadesDelPiso(inv, id) : [];
    for (const n of unidades) { const m = modelo?.unidad(n.id); if (m && n.recinto == null && m.recinto) n.recinto = m.recinto; }
    const capa = inv ? armarCapa(nivel, unidades, calidad) : null;
    if (capa) st.scene.add(capa.objeto);
    const dims = new Map((capa?.unidades() || []).map((u) => [String(u.id), u]));
    const t3 = performance.now();
    // huellas de los equipos grandes de piso (> 0,5 m²) para la colisión (los fantasmas y los elevados no). Una huella que
    // invade el despeje de una puerta (el vano por 0,9 m a cada lado) no es obstáculo: un equipo mal ubicado frente a la
    // puerta no puede dejar un recinto sin entrada (16.1, todo caminable); se camina a través de él
    const muros = new Map((nivel.muros || []).map((m) => [m.id, m]));
    const despejes = despejesPuertas(nivel, muros);
    const obstaculos = [];
    let enPuerta = 0;
    // la altura de cada unidad se mide desde el piso donde está (la terraza de la cubierta está 4,20 m abajo del nivel)
    const pisoBajo = (x, y) => cotaPiso(planta.recinto(planta.recintoEn(x, y)), x, y);
    for (const n of unidades) {
      const d = dims.get(String(n.id));
      if (!d || !d.dibujada || d.montaje !== 'piso' || n.estado === 'cierre_brechas_propuesto' || (+n.z || 0) - pisoBajo(n.x, n.y) > 0.5 || d.variante === 'elevada') continue;
      // las de más de 0,5 m² (6.4) y también las altas y angostas (neveras, estantes, lockers, carros): no se camina a través
      const area = d.dim[0] * d.dim[1];
      if (area < 0.5 && !(area >= 0.2 && d.dim[2] >= 0.85)) continue;
      // alto: lo que hay que saltar para pasar por encima o pararse en él
      const ob = { x: n.x, y: n.y, w: d.dim[0], d: d.dim[1], rot: n.rot || 0, id: n.id, alto: Math.max(0.01, (+n.z || 0) - pisoBajo(n.x, n.y)) + (+d.dim[2] || 1) };
      if (despejes.some((q) => cruzanOBB(ob, q))) { enPuerta++; continue; }
      obstaculos.push(ob);
    }
    // superficies de las escaleras: las partes de este nivel, las del de abajo y el descanso de piso del de arriba
    const superficies = [];
    for (const e of nivel.escaleras || []) for (const p of e.partes || []) superficies.push({ rect: p.rect, p, dz: 0 });
    if (nAb) for (const e of nAb.escaleras || []) for (const p of e.partes || []) superficies.push({ rect: p.rect, p, dz: nAb.z - nivel.z });
    if (nAr) for (const e of nAr.escaleras || []) for (const p of e.partes || []) if (p.tipo === 'descanso_piso') superficies.push({ rect: p.rect, p, dz: nAr.z - nivel.z });
    const llegadas = nAb ? (nAb.escaleras || []).flatMap((e) => (e.partes || []).filter((p) => p.tipo === 'tramo' && Math.abs(+p.z1 - (nivel.z - nAb.z)) < 0.05).map(bordeAlto)) : [];
    const opRejilla = { partes: superficies.map((s) => s.rect), llegadas, radio: RADIO };
    // ningún recinto transitable queda encerrado por equipos: con la rejilla sin equipos se busca, desde las entradas, el
    // camino que cruza menos celdas tapadas por huellas, y se quitan las huellas que lo tapan (en la QA, alcance por nivel).
    // Lo que se quita se guarda por nivel: al volver a él la rejilla se arma una sola vez
    const claveH = `${id}|${capas.infraestructura ? 1 : 0}`;
    let rejilla, quitar = huellasQuitadas.get(claveH);
    if (quitar) rejilla = rejillaColision(nivel, { ...opRejilla, obstaculos: obstaculos.filter((o) => !quitar.has(String(o.id))) });
    else {
      rejilla = rejillaColision(nivel, { ...opRejilla, obstaculos });
      const sinEquipos = rejillaColision(nivel, { ...opRejilla, obstaculos: [] });
      const k = huellasQueEncierran(nivel, sinEquipos, rejilla, obstaculos, CLAVE_PISO[id]);
      quitar = new Set([...k].map((i) => String(obstaculos[i].id)));
      huellasQuitadas.set(claveH, quitar);
      if (quitar.size) rejilla = rejillaColision(nivel, { ...opRejilla, obstaculos: obstaculos.filter((o) => !quitar.has(String(o.id))) });
    }
    const techos = techosBajos(nivel, muros, unidades, dims, rejilla, pisoBajo);
    const t4 = performance.now();
    // puertas por recinto, pasos a otros niveles y salidas al exterior sin paso
    const puertasDe = new Map();
    for (const p of nivel.puertas || []) for (const r of [p.desde, p.hacia]) { if (!r) continue; if (!puertasDe.has(r)) puertasDe.set(r, []); puertasDe.get(r).push(p); }
    const pasos = (nivel.pasos_entre_niveles || []).filter((p) => niveles.has(p.otro_nivel));
    const conPaso = new Set(pasos.map((p) => p.puerta).filter(Boolean));
    const salidas = (nivel.puertas || []).filter((p) => (p.desde === 'exterior' || p.hacia === 'exterior') && !conPaso.has(p.id));
    const clave = CLAVE_PISO[id];
    const ascensores = (nivel.conexiones_verticales || []).filter((c) => c.tipo === 'ascensor' && c.puntos?.[clave]);
    const cabinas = new Set((nivel.nucleos || []).filter((n) => n.tipo === 'ascensor').flatMap((n) => n.recintos || [n.recinto]));
    const escaleras = new Set((nivel.escaleras || []).map((e) => e.recinto));
    const celdaRec = new Array(rejilla.nx * rejilla.ny);
    const n = {
      id, nivel, planta, plantaCtx, capa, unidades, dims, rejilla, techos, superficies, puertasDe, muros, pasos, salidas, ascensores, cabinas, escaleras, celdaRec, calidad,
      abajo: nAb ? idAb : null, arriba: nAr ? idAr : null, dzArriba: nAr ? nAr.z - nivel.z : 0, impl: null, implementos: implementosDelNivel(unidades, dims),
      huellas: { obstaculos: obstaculos.length - quitar.size, enPuerta, quitadas: quitar.size },
    };
    tiempoNivel = performance.now() - t0;
    tiempos = { planta: t1 - t0, contexto: t2 - t1, equipos: t3 - t2, rejilla: t4 - t3, resto: performance.now() - t4 };
    return n;
  }
  // Lo que queda sobre la cabeza más abajo que el cielo raso, por celda de la rejilla (altura sobre el piso; Infinity si
  // nada): el dintel de cada puerta en su vano (y el radio del caminante a cada lado del muro) y las unidades colgadas del
  // cielo o de la pared desde 1,80 m (lámparas, televisores, señales), con su huella inflada por el radio. Quien salta no
  // pasa la cabeza a través de ellos: el salto se detiene y en el aire no se entra bajo uno más bajo que los ojos
  function techosBajos(nivel, muros, unidades, dims, R, pisoBajo) {
    const T = new Float32Array(R.nx * R.ny).fill(Infinity);
    const marcar = (cx, cy, ux, uy, hl, hw, z) => {
      const ext = Math.abs(ux) * hl + Math.abs(uy) * hw, eyt = Math.abs(uy) * hl + Math.abs(ux) * hw;
      const i0 = Math.max(0, Math.floor((cx - ext - R.x0) / R.celda)), i1 = Math.min(R.nx - 1, Math.floor((cx + ext - R.x0) / R.celda));
      const j0 = Math.max(0, Math.floor((cy - eyt - R.y0) / R.celda)), j1 = Math.min(R.ny - 1, Math.floor((cy + eyt - R.y0) / R.celda));
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
        const px = R.x0 + (i + 0.5) * R.celda - cx, py = R.y0 + (j + 0.5) * R.celda - cy, k = j * R.nx + i;
        if (Math.abs(px * ux + py * uy) <= hl && Math.abs(-px * uy + py * ux) <= hw && z < T[k]) T[k] = z;
      }
    };
    for (const p of nivel.puertas || []) {
      const m = muros.get(p.muro);
      if (!m || !p.centro) continue;
      const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1;
      marcar(p.centro[0], p.centro[1], (m.b[0] - m.a[0]) / L, (m.b[1] - m.a[1]) / L, (+p.ancho || 0.9) / 2, (+m.espesor || 0.2) / 2 + RADIO, +p.alto || 2.1);
    }
    for (const n of unidades) {
      const d = dims.get(String(n.id));
      if (!d || !d.dibujada || (d.montaje !== 'cielo' && d.montaje !== 'pared') || d.modelo === 'riel_cortina' || d.variante === 'elevada') continue;
      const z = (+n.z || 0) - pisoBajo(n.x, n.y);
      if (z < 1.8) continue;
      marcar(n.x, n.y, Math.cos(n.rot || 0), Math.sin(n.rot || 0), d.dim[0] / 2 + RADIO, d.dim[1] / 2 + RADIO, z);
    }
    return T;
  }
  function soltarNivel() {
    if (!cur) return;
    soltarImplementos();
    cur.capa?.dispose();
    cur.planta.dispose();
    cur.plantaCtx?.dispose();
    cur = null;
  }

  // ---------------------------------------------------------------- implementos a la vista (16.2 y 16.6): solo en el recinto actual
  // Cajas de reactivos, frascos y gradillas de cada analizador y de las neveras y estantes, en los entrepaños de donde se guardan
  // (alm.donde) o sobre el equipo que los usa; una InstancedMesh por modelo, pickable (abre la ficha del implemento).
  function implementosDelNivel(unidades, dims) {
    if (!modelo) return new Map();
    const porRec = new Map(), ocupados = new Map();
    const delNivel = new Map();
    for (const n of unidades) { const u = modelo.unidad(n.id); if (u) delNivel.set(String(n.id), { u, n }); }
    const porLinea = new Map();
    for (const { u, n } of delNivel.values()) { const k = u.linea?.id; if (!k) continue; if (!porLinea.has(k)) porLinea.set(k, []); porLinea.get(k).push({ u, n }); }
    for (const { u, n } of delNivel.values()) {
      const items = modelo.itemsDe(u);
      items.forEach((it, k) => {
        if (!MODELOS_IMPLEMENTO.has(it.m3d)) return;
        // dónde se guarda: la unidad de la línea alm.donde en el mismo recinto, o en el nivel; si no, sobre el equipo
        const cand = it.alm?.donde ? porLinea.get(it.alm.donde) || [] : [];
        const dest = cand.find((c) => c.u.recinto === u.recinto) || cand[0] || { u, n };
        const d = dims.get(String(dest.n.id));
        if (!d || !d.dibujada) return;
        const rec = dest.u.recinto || u.recinto;
        if (!rec) return;
        const sobre = dest.u === u && !/nevera|estant|refriger|vitrina|gabinete|mueble/i.test(dest.n.modelo || '');
        const clave = String(dest.n.id), c = ocupados.get(clave) || 0;
        ocupados.set(clave, c + 1);
        if (!porRec.has(rec)) porRec.set(rec, []);
        porRec.get(rec).push({ uid: u.id, k, m3d: it.m3d, dest: dest.n, dim: d.dim, i: c, sobre });
      });
    }
    return porRec;
  }
  function armarImplementos(rec) {
    soltarImplementos();
    const L = cur?.implementos.get(rec);
    if (!L?.length) return;
    const porModelo = new Map();
    for (const it of L) { if (!porModelo.has(it.m3d)) porModelo.set(it.m3d, []); porModelo.get(it.m3d).push(it); }
    const mat = materialesEquipos().opaco, grupo = new THREE.Group(), M = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), uno = new THREE.Vector3(1, 1, 1);
    grupo.name = 'recorrido:implementos';
    const mallas = [];
    for (const [m3d, items] of porModelo) {
      const dimI = inv?.catalogo?.[m3d]?.dim || nominalEquipo(m3d).dim;
      const geo = geometriaEquipo(m3d, dimI, 0);
      geo.userData.vidrio?.dispose();
      const im = new THREE.InstancedMesh(geo, mat, items.length);
      im.name = `implementos:${m3d}`;
      items.forEach((it, k) => {
        const [W, D, H] = it.dim, por = Math.max(1, Math.floor((W - 0.1) / Math.max(0.12, dimI[0] + 0.03)));
        // entrepaños: 4 en un estante o nevera (de 0,35 a 0,85 del alto); encima del equipo, una fila
        const nE = it.sobre ? 1 : 4, fila = Math.floor(it.i / por) % nE, col = it.i % por, capaZ = Math.floor(it.i / (por * nE));
        const lx = -W / 2 + 0.05 + (col + 0.5) * ((W - 0.1) / por), ly = it.sobre ? 0 : -D / 2 + 0.06 + dimI[1] / 2;
        const lz = it.sobre ? H + capaZ * dimI[2] : H * (0.2 + 0.18 * fila) + capaZ * dimI[2];
        const c = Math.cos(it.dest.rot), s = Math.sin(it.dest.rot);
        const px = it.dest.x + c * lx - s * ly, py = it.dest.y + s * lx + c * ly;
        e.set(0, it.dest.rot, 0); q.setFromEuler(e);
        M.compose(new THREE.Vector3(px, cur.nivel.z + it.dest.z + lz, -py), q, uno);
        im.setMatrixAt(k, M);
      });
      im.instanceMatrix.needsUpdate = true;
      im.computeBoundingSphere();
      im.userData.items = items;
      grupo.add(im);
      mallas.push(im);
    }
    st.scene.add(grupo);
    cur.impl = { grupo, mallas };
  }
  function soltarImplementos() {
    if (!cur?.impl) return;
    for (const m of cur.impl.mallas) { m.geometry.dispose(); m.dispose?.(); }
    cur.impl.grupo.removeFromParent();
    cur.impl = null;
  }

  // ---------------------------------------------------------------- piso bajo los pies
  function celda(x, y) {
    const R = cur.rejilla, i = Math.floor((x - R.x0) / R.celda), j = Math.floor((y - R.y0) / R.celda);
    return i < 0 || j < 0 || i >= R.nx || j >= R.ny ? -1 : j * R.nx + i;
  }
  function recintoCelda(k, x, y) {
    let r = cur.celdaRec[k];
    if (r === undefined) { const id = cur.planta.recintoEn(x, y); r = cur.celdaRec[k] = id ? cur.planta.recinto(id) : null; }
    return r;
  }
  // altura del piso en (x, y) para quien llega caminando con el piso a la altura h (null si no se puede pisar). Una celda
  // tapada solo por un equipo u obstáculo con altura tiene piso debajo: lo que la tapa lo mide encima()
  function superficie(x, y, h) {
    const k = celda(x, y);
    if (k < 0) return null;
    const R = cur.rejilla, c = R.datos[k];
    if (c === 1 && (R.duro[k] === 1 || !(R.alto[k] > 0))) return null;
    if (c !== 2) { const z = cotaPiso(recintoCelda(k, x, y), x, y); return Math.abs(z - h) <= PASO_Z ? z : null; }
    let mejor = null, dm = PASO_Z;
    for (const s of cur.superficies) {
      const r = s.rect;
      if (x < r[0] - 1e-3 || x > r[2] + 1e-3 || y < r[1] - 1e-3 || y > r[3] + 1e-3) continue;
      const z = s.dz + cotaParte(s.p, x, y), d = Math.abs(z - h);
      if (d <= dm) { dm = d; mejor = z; }
    }
    return mejor;
  }
  // altura del piso al llegar de un salto (sin continuidad): el piso del recinto o, en la escalera, la parte de este nivel
  function sueloEn(x, y) {
    const k = celda(x, y);
    if (k < 0) return 0;
    if (cur.rejilla.datos[k] !== 2) return cotaPiso(recintoCelda(k, x, y), x, y);
    let mejor = 0, dm = Infinity;
    for (const s of cur.superficies) {
      const r = s.rect;
      if (x < r[0] || x > r[2] || y < r[1] || y > r[3]) continue;
      const z = s.dz + cotaParte(s.p, x, y), d = Math.abs(z) + (s.dz ? 100 : 0);
      if (d < dm) { dm = d; mejor = z; }
    }
    return mejor;
  }
  const enEscalera = (x, y) => { const k = celda(x, y); return k >= 0 && cur.rejilla.datos[k] === 2; };
  // altura de lo que tapa la celda sobre su piso (0 si nada: piso libre o escalera)
  const encima = (x, y) => { const k = celda(x, y); return k >= 0 && cur.rejilla.datos[k] === 1 ? cur.rejilla.alto[k] : 0; };
  // cielo raso sobre el piso z en (x, y): la altura libre del nivel; en la escalera, el tramo de arriba; en los exteriores
  // y la cubierta, el cielo
  const techo = (x, y, z) => (enEscalera(x, y) ? z + TECHO_ESCALERA : CIELO_ABIERTO.has(cur.id) ? Infinity : z + (+cur.nivel.altura_libre_m || 3));
  // altura máxima de los pies en (x, y) con el piso en z: el cielo raso (o el tramo de arriba) y lo que cuelga más bajo
  // (dinteles, lámparas); en la escalera, los ojos no pasan la losa de arriba (allí cambia de nivel quien sube caminando)
  function techoPies(x, y, z) {
    let t = techo(x, y, z);
    const k = celda(x, y);
    if (k >= 0 && cur.techos[k] < Infinity) t = Math.min(t, z + cur.techos[k]);
    t -= OJOS + CABEZA;
    if (cur.arriba && enEscalera(x, y)) t = Math.min(t, Math.max(z, cur.dzArriba - SUBE - 0.02));
    return t;
  }
  // piso y tope (piso + lo que tapa la celda) adonde puede pasar el caminante: caminando sube hasta PASO_Z (un escalón o
  // un equipo bajo); en el aire, solo por encima de lo que queda bajo sus pies y por debajo de lo que tenga encima (un
  // dintel, una lámpara o el tramo de una escalera lo detienen como un muro)
  function paso(x, y) {
    const zf = superficie(x, y, w.hp);
    if (zf == null) return null;
    const tope = zf + encima(x, y);
    if (tope > w.h + (w.aire ? 0.02 : PASO_Z)) return null;
    // de pie no cabe (una lámpara sobre la cama) o, en el aire, la cabeza va más alta que lo que hay encima
    const t = techoPies(x, y, zf);
    if (t < tope - 0.01 || (w.aire && w.h > t + 0.01)) return null;
    return [zf, tope];
  }
  function pisar(zf, tope) {
    w.hp = zf;
    if (w.aire) return;
    // caminando: sigue los escalones y rampas; al salir del borde de un equipo, cae
    if (tope >= w.h - PASO_Z) w.h = tope; else { w.aire = true; w.vz = 0; }
  }
  function moverCaminante(dx, dy) {
    const n = Math.max(1, Math.ceil(Math.hypot(dx, dy) / 0.04)), sx = dx / n, sy = dy / n;
    let bloqueado = false, z;
    for (let k = 0; k < n; k++) {
      if ((z = paso(w.x + sx, w.y + sy))) { w.x += sx; w.y += sy; pisar(...z); continue; }
      bloqueado = true;
      if (sx && (z = paso(w.x + sx, w.y))) { w.x += sx; pisar(...z); continue; }
      if (sy && (z = paso(w.x, w.y + sy))) { w.y += sy; pisar(...z); continue; }
      break;
    }
    return bloqueado;
  }
  // en el suelo, sin velocidad vertical, sobre el piso z (o sobre lo que tape la celda, si se cae encima)
  function aterrizar(z) { w.h = w.hp = z; w.vz = 0; w.aire = false; }
  // salto y caída: gravedad, el cielo raso detiene la subida y se aterriza sobre el piso o sobre lo que tapa la celda
  function caer(dt) {
    // la parábola exacta del cuadro: el salto llega a la misma altura con 15 o con 60 cuadros por segundo
    w.h += w.vz * dt - 0.5 * GRAVEDAD * dt * dt;
    w.vz -= GRAVEDAD * dt;
    const zf = superficie(w.x, w.y, w.hp) ?? w.hp, tope = zf + encima(w.x, w.y), t = techoPies(w.x, w.y, w.hp);
    if (w.h > t) { w.h = Math.max(t, tope); if (w.vz > 0) w.vz = 0; }
    if (w.h <= tope) { w.h = tope; w.hp = zf; w.vz = 0; w.aire = false; }
  }

  // ---------------------------------------------------------------- cámara en los ojos del caminante
  const _ojo = new THREE.Vector3(), _ad = new THREE.Vector3();
  function colocarCamara() {
    if (!cur) return;
    _ojo.set(w.x, cur.nivel.z + w.h + OJOS, -w.y);
    const cp = Math.cos(w.pitch);
    _ad.set(cp * Math.cos(w.yaw), Math.sin(w.pitch), -cp * Math.sin(w.yaw));
    st.camera.position.copy(_ojo);
    st.controls.target.copy(_ojo).addScaledVector(_ad, 0.5);
    st.camera.lookAt(st.controls.target);
    st.camera.updateMatrixWorld();
  }

  // ---------------------------------------------------------------- cambio de nivel y saltos
  // Arma el nivel id (si no es el actual) y pone al caminante en (x, y); h: altura de los pies (o la del piso allí)
  function ponerEnNivel(id, x, y, { h = null, yaw = null, pitch = null } = {}) {
    if (!cur || cur.id !== id || cur.calidad !== (engine.tier || 'media')) {
      const enCapa = { faltantes: capas.faltantes, resaltados };
      soltarNivel();
      cur = armarNivel(id);
      recintoActual = null; subActual = null;
      aplicarCapas();
      if (enCapa.resaltados) cur.capa?.resaltar(enCapa.resaltados);
      suelo(id === 'BT');
      ponerNombreBarra(id);
      pNivel.textContent = limpio(cur.nivel.nombre || NOMBRE_NIVEL[id] || id);
      pintarRecintos();
      marcaMapa.rec = Symbol('nivel');
    }
    w.x = x; w.y = y;
    aterrizar(h == null ? sueloEn(x, y) : h);
    if (yaw != null) w.yaw = yaw;
    if (pitch != null) w.pitch = pitch;
    forzar = true;
    st.invalidate();
  }
  // el caminante pasa a otro nivel por la escalera: mismas (x, y), los pies a la misma cota absoluta (y, si va en el
  // aire, sigue en el aire)
  function cambiarPorEscalera(id) {
    const n = niveles.get(id), dz = cur.nivel.z - n.z, sobre = w.h - w.hp, { vz, aire } = w;
    ponerEnNivel(id, w.x, w.y, { h: w.hp + dz });
    w.h += sobre; w.vz = vz; w.aire = aire;
  }
  // salto con fundido de 250 ms (instantáneo con prefers-reduced-motion; 6.4)
  function saltar(fn) {
    if (!activo || movReducido()) { ultimoFundido = false; fn(); return; }
    ultimoFundido = true;
    saltando = true;
    fundido.classList.add('on');
    setTimeout(() => {
      // si la persona salió del recorrido durante el fundido, el salto ya no se hace
      try { if (activo) fn(); } finally {
        saltando = false;
        requestAnimationFrame(() => { fundido.classList.remove('on'); st.invalidate(); });
      }
    }, 130);
  }
  // celda libre cerca de (x, y), si se puede dentro del recinto pedido
  function libreCerca(x, y, rec = null, r = 2.5) {
    const filtro = rec ? (px, py) => { const id = cur.planta.recintoEn(px, py); return id === rec || cur.planta.subrecintoEn(px, py, rec) != null; } : null;
    return cur.rejilla.cercana(x, y, r, filtro) || cur.rejilla.cercana(x, y, r) || [x, y];
  }
  // entrada del nivel por omisión (R/F y los botones de nivel): el vestíbulo de ascensores en los pisos, la puerta principal
  // en los exteriores, el pasaje en el bloque técnico y la salida de la escalera norte en la cubierta
  function entradaDe(id, pref = null) {
    const n = niveles.get(id), E = n.entradas_recorrido || [];
    const quiere = pref || { EXT: 'puerta_principal', BT: 'pasaje', CUB: 'cubierta' }[id] || 'ascensores';
    let e = E.find((x) => x.id === quiere);
    if (!e && quiere === 'ascensores') {
      // el piso 1 no trae la entrada del vestíbulo: es el mismo punto de los pisos de arriba (núcleo igual)
      for (const otro of ['P2', 'P3', 'P4']) { const x = niveles.get(otro)?.entradas_recorrido?.find((q) => q.id === 'ascensores'); if (x) { e = { ...x, nombre: 'Vestíbulo de ascensores' }; break; } }
    }
    return e || E[0] || { punto: puntoInterior(n.contorno || n.recintos[0].poligono), mirando_deg: 90 };
  }
  function irANivel(id, pref = null) {
    const e = entradaDe(id, pref);
    ponerEnNivel(id, e.punto[0], e.punto[1], { yaw: rad(+e.mirando_deg || 0), pitch: 0 });
    const [x, y] = libreCerca(e.punto[0], e.punto[1]);
    w.x = x; w.y = y; aterrizar(sueloEn(x, y));
  }
  function subirBajar(dir) {
    if (!cur) return;
    const i = ordenNiveles.indexOf(cur.id), j = i + dir;
    if (j < 0 || j >= ordenNiveles.length) { avisar(dir > 0 ? 'No hay nivel más arriba.' : 'No hay nivel más abajo.'); return; }
    const id = ordenNiveles[j];
    saltar(() => { irANivel(id); avisar(`${CORTO_NIVEL[id]}: ${limpio(entradaDe(id).nombre || '')}`); });
  }

  // ---------------------------------------------------------------- «Ir a» (6.2 y 16.4)
  // Posición y mirada frente a una unidad (16.4: «Ir a» deja al caminante frente a ella). Se prueban puntos al frente (+y
  // local), a los lados, en diagonal y detrás, de lejos a cerca (de 1,6 a 0,45 m del borde de su huella), y se acepta el
  // primero que: está libre en la rejilla, queda en el mismo recinto y subrecinto que la unidad (no detrás del tabique de
  // un baño) y desde cuyos ojos un rayo al centro de la unidad la toca antes que a un muro, una hoja de puerta u otro
  // equipo (la misma prueba de la selección). La inclinación encuadra la unidad entera si cabe en el campo vertical.
  const _rv = new THREE.Raycaster(), _o = new THREE.Vector3(), _c = new THREE.Vector3();
  let ultimoObjetivo = null;
  function frenteA(n, d) {
    const fx = -Math.sin(n.rot || 0), fy = Math.cos(n.rot || 0), lx = -fy, ly = fx;   // frente (+y local) y ancho (+x local)
    const W = d?.dim?.[0] || 0.5, D = d?.dim?.[1] || 0.5, H = d?.dim?.[2] || 1;
    const recU = modelo?.unidad(n.id)?.recinto || null;
    const padre = (recU && (modelo?.recintos.get(recU)?.padre || (cur.planta.recinto(recU) ? recU : null))) || cur.planta.recintoEn(n.x, n.y) || null;
    const sub = padre ? cur.planta.subrecintoEn(n.x, n.y, padre) : null;
    const z0 = cur.nivel.z + (n.z || 0);
    // lo que va en un núcleo (cabinas de ascensor y montacargas) se mira desde afuera, desde el vestíbulo
    const enNucleo = modelo?.unidad(n.id)?.montaje === 'en_nucleo';
    // la sala del recinto (objetos pequeños y LOD0) y sus implementos deben estar armados para probar la vista. No la del
    // núcleo: quien mira queda afuera, en otro recinto, y la unidad se ve como en el resto del piso (LOD1); probada con el
    // LOD0 del núcleo, el punto de mira podía caer donde el LOD1 no tiene nada (el montacargas visto por su ventanilla)
    if (padre && padre !== recintoActual && !enNucleo) { cur.capa?.entrarRecinto(padre); armarImplementos(padre); recintoActual = padre; subActual = null; }
    // distancia de (px, py) al borde de la huella girada (0 dentro)
    const fueraHuella = (px, py) => { const dx = px - n.x, dy = py - n.y, a = Math.abs(dx * lx + dy * ly) - W / 2, b = Math.abs(dx * fx + dy * fy) - D / 2; return Math.hypot(Math.max(0, a), Math.max(0, b)); };
    const mismoLugar = enNucleo ? () => true : (px, py) => (!padre || cur.planta.recintoEn(px, py) === padre) && (cur.planta.subrecintoEn(px, py, padre) || null) === sub;
    // puntos de mira: el centro (como máximo a 1,2 m de la base) y, si no se ve, puntos de su cara de frente y del medio a
    // varias alturas (una barra de apoyo o una ducha no tienen nada en el centro de su caja)
    const centro = [n.x, n.y, z0 + Math.min(H / 2, 1.2)];
    const otros = [];
    for (const h of [0.5, 0.25, 0.8, 0.05, 0.97]) for (const [a, b] of [[0, 0.45], [-0.3, 0.45], [0.3, 0.45], [0, 0], [-0.4, 0], [0.4, 0], [-0.47, 0], [0.47, 0]]) otros.push([n.x + a * W * lx + b * D * fx, n.y + a * W * ly + b * D * fy, z0 + h * H]);
    const ve = (px, py, [tx, ty, tz]) => {
      _o.set(px, cur.nivel.z + sueloEn(px, py) + OJOS, -py);
      _c.set(tx, tz, -ty);
      const L = _o.distanceTo(_c);
      _rv.set(_o, _c.sub(_o).normalize());
      _rv.near = 0; _rv.far = L + 0.6;
      const h = elegido(_rv);
      return !!h && h.tipo === 'unidad' && String(h.id) === String(n.id);
    };
    const dirs = [[fx, fy], [lx, ly], [-lx, -ly], [Math.SQRT1_2 * (fx + lx), Math.SQRT1_2 * (fy + ly)], [Math.SQRT1_2 * (fx - lx), Math.SQRT1_2 * (fy - ly)], [-fx, -fy],
      [Math.SQRT1_2 * (-fx + lx), Math.SQRT1_2 * (-fy + ly)], [Math.SQRT1_2 * (-fx - lx), Math.SQRT1_2 * (-fy - ly)]];
    const semi = (ux, uy) => Math.abs(ux * lx + uy * ly) * W / 2 + Math.abs(ux * fx + uy * fy) * D / 2;   // semiancho de la huella en (ux, uy)
    const libres = [];
    // de 1,6 m hacia la unidad y, si nada sirve (una cama delante de su cabecera), más lejos
    for (const extra of [1.6, 1.3, 1.0, 0.8, 0.6, 0.45, 2.0, 2.5, 3.0]) for (const [ux, uy] of dirs) {
      const r = semi(ux, uy) + extra, px = n.x + ux * r, py = n.y + uy * r;
      if (!cur.rejilla.libre(px, py) || !mismoLugar(px, py) || fueraHuella(px, py) < 0.44) continue;
      libres.push([px, py]);
      if (ve(px, py, centro)) return { pos: [px, py], punto: centro, visto: true };
    }
    // segunda vuelta: los demás puntos de mira desde los primeros lugares libres
    for (const [px, py] of libres.slice(0, 12)) for (const t of otros) if (ve(px, py, t)) return { pos: [px, py], punto: t, visto: true };
    // tercera: cualquier celda libre del mismo lugar a menos de 4,5 m (cada 0,25 m), de la más cómoda (a 1 m del borde) a la
    // menos; en un baño pequeño o detrás de una cama los puntos de los ejes pueden caer todos en celdas tapadas
    // menos; en un baño pequeño o detrás de una cama los puntos de los ejes pueden caer todos en celdas tapadas. Si en el
    // mismo lugar no hay sitio (un lavamanos en un baño de 1,5 m), se mira desde afuera, por la puerta, si se ve
    const celdas = [], afuera = [];
    for (let dy = -4.5; dy <= 4.5; dy += 0.25) for (let dx = -4.5; dx <= 4.5; dx += 0.25) {
      const px = n.x + dx, py = n.y + dy, b = fueraHuella(px, py);
      if (b < 0.44 || b > 4.5 || !cur.rejilla.libre(px, py)) continue;
      if (mismoLugar(px, py)) celdas.push([Math.abs(b - 1), px, py]); else afuera.push([b, px, py]);
    }
    celdas.sort((a, b) => a[0] - b[0]);
    afuera.sort((a, b) => a[0] - b[0]);
    for (const L of [celdas, afuera]) {
      for (const [, px, py] of L.slice(0, 40)) if (ve(px, py, centro)) return { pos: [px, py], punto: centro, visto: true };
      for (const [, px, py] of L.slice(0, 10)) for (const t of otros) if (ve(px, py, t)) return { pos: [px, py], punto: t, visto: true };
    }
    if (!libres.length && celdas.length) libres.push([celdas[0][1], celdas[0][2]]);
    if (libres.length) return { pos: libres[0], punto: centro, visto: false };
    // sin un punto así, la celda libre más cercana del recinto que no quede encima de la unidad
    const filtro = (px, py) => mismoLugar(px, py) && fueraHuella(px, py) >= 0.44;
    return { pos: cur.rejilla.cercana(n.x, n.y, 5, filtro) || libreCerca(n.x, n.y, padre, 4), punto: centro, visto: false };
  }
  // inclinación para ver la unidad: la encuadra entera (de la base al tope) si cabe en el 80 % del campo vertical y el punto
  // de mira queda dentro; si no, mira el punto de mira. Entre −60° y +60°
  function inclinacionHacia(n, d, [px, py], [tx, ty, tz]) {
    const H = d?.dim?.[2] || 1, z0 = cur.nivel.z + (n.z || 0), ojo = cur.nivel.z + sueloEn(px, py) + OJOS, v = rad(st.camera.fov);
    const dist = Math.max(0.3, Math.hypot(n.x - px, n.y - py) - Math.min(d?.dim?.[0] || 0.5, d?.dim?.[1] || 0.5) / 2);
    const aTop = Math.atan2(z0 + H - ojo, dist), aBot = Math.atan2(z0 - ojo, dist), aMira = Math.atan2(tz - ojo, Math.max(0.3, Math.hypot(tx - px, ty - py)));
    const marco = (aTop + aBot) / 2;
    const p = aTop - aBot <= v * 0.8 && Math.abs(marco - aMira) < v * 0.4 ? marco : aMira;
    return THREE.MathUtils.clamp(p, rad(-60), rad(60));
  }
  // la unidad que se ve: el contenedor de lo que va dentro y la madre de un componente guardado
  function unidadVisible(u) {
    let v = u;
    for (let g = 0; g < 4 && v && v.montaje === 'dentro'; g++) v = v.dentro >= 0 ? modelo.unidades[v.dentro] : v.componente >= 0 ? modelo.unidades[v.componente] : null;
    return v || u;
  }
  function irAUnidad(id, { resaltar = null, abrirFicha = true } = {}) {
    const u = modelo?.unidad(id);
    if (!u) { avisar('No se encontró esa unidad en el inventario.'); return; }
    const v = unidadVisible(u);
    const nivelId = idNivel(v.nivel) || (u.nivel && idNivel(u.nivel));
    if (!nivelId || !niveles.has(nivelId)) {
      if (abrirFicha) mostrarFicha({ unidad: u.id });
      avisar('Esta unidad no está en la torre (queda fuera del recorrido).');
      return;
    }
    // un faltante del cierre de brechas solo se dibuja con la capa «Faltantes»: se enciende para que se vea y se pueda tocar
    const faltante = u.estado === 'cierre_brechas_propuesto' || v.estado === 'cierre_brechas_propuesto';
    ponerEnNivel(nivelId, v.x, v.y);
    if (faltante && !capas.faltantes) ponerCapa('faltantes', true);
    const n = cur.unidades.find((q) => String(q.id) === String(v.id)) || { id: v.id, x: v.x, y: v.y, z: v.z, rot: v.rot };
    const d = cur.dims.get(String(n.id));
    const f = frenteA(n, d), [px, py] = f.pos, [tx, ty] = f.punto;
    ponerEnNivel(nivelId, px, py, { yaw: Math.atan2(ty - py, tx - px), pitch: inclinacionHacia(n, d, f.pos, f.punto) });
    ultimoObjetivo = { unidad: String(v.id), punto: [tx, ty, f.punto[2] - cur.nivel.z], visto: f.visto };
    resaltados = resaltar || [String(v.id)];
    cur.capa?.resaltar(resaltados);
    if (abrirFicha) mostrarFicha({ unidad: u.id });
    if (faltante) avisar('Faltante propuesto por el cierre de brechas: se muestra en violeta translúcido.', 4000);
    else if (!f.visto) avisar('Desde aquí la tapa otro equipo o un muro: su recuadro rojo se ve a través.', 4000);
  }
  // dentro de un recinto, junto a su puerta y mirando hacia adentro
  function irARecinto(id, { abrirFicha = false } = {}) {
    const r = modelo?.recintos.get(id) || [...niveles.values()].flatMap((n) => (n.recintos || []).map((q) => ({ ...q, nivel: n.id }))).find((q) => q.id === id);
    if (!r) return;
    const padre = r.padre || id, nivelId = r.nivel;
    ponerEnNivel(nivelId, ...puntoInterior(r.poligono));
    const pol = r.poligono, ps = cur.puertasDe.get(id) || cur.puertasDe.get(padre) || [];
    let pos = null, yaw = 0;
    for (const p of ps) {
      const m = cur.muros.get(p.muro);
      if (!m) continue;
      const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1;
      let nx = -(m.b[1] - m.a[1]) / L, ny = (m.b[0] - m.a[0]) / L;
      if (!enPoligono(p.centro[0] + nx * 0.4, p.centro[1] + ny * 0.4, pol)) { nx = -nx; ny = -ny; }
      const [x, y] = libreCerca(p.centro[0] + nx * 0.8, p.centro[1] + ny * 0.8, padre, 1.5);
      if (enPoligono(x, y, cur.planta.recinto(padre)?.poligono || pol)) { pos = [x, y]; yaw = Math.atan2(ny, nx); break; }
    }
    if (!pos) { const c = puntoInterior(pol); pos = libreCerca(c[0], c[1], padre, 3); yaw = w.yaw; }
    ponerEnNivel(nivelId, pos[0], pos[1], { yaw, pitch: 0 });
    if (abrirFicha) mostrarFicha({ recinto: id });
  }
  function irA(destino = {}) {
    if (!cur && !destino) return;
    const d = destino || {};
    saltar(() => {
      if (d.faltantes) ponerCapa('faltantes', true);
      if (d.unidad) irAUnidad(d.unidad, { resaltar: d.resaltar || null, abrirFicha: d.ficha !== false });
      else if (d.recinto) irARecinto(d.recinto, { abrirFicha: d.ficha === true });
      else if (d.laboratorio) irANivel('P2', 'laboratorio');
      else if (d.posicion) {
        const id = idNivel(d.nivel ?? d.piso) || cur?.id || 'P1';
        ponerEnNivel(id, d.posicion[0], d.posicion[1], { yaw: d.rumbo_deg != null ? rad(+d.rumbo_deg) : null, pitch: d.pitch_deg != null ? rad(+d.pitch_deg) : 0 });
        // un punto pedido dentro de un muro o de un equipo pasa a la celda libre más cercana
        if (!cur.rejilla.libre(w.x, w.y)) { const [x, y] = libreCerca(w.x, w.y, null, 3); w.x = x; w.y = y; aterrizar(sueloEn(x, y)); }
      } else {
        const id = idNivel(d.nivel ?? d.piso) || (d.entrada ? 'P2' : 'EXT');
        irANivel(id, d.entrada || null);
      }
      if (d.resaltar && !d.unidad) { resaltados = d.resaltar.map(String); cur.capa?.resaltar(resaltados); }
      // desde el buscador, por un implemento que coincide: la ficha del contenedor con su contenido desplegado
      if (d.implementos) ficha.querySelectorAll('details.reco-impl').forEach((x) => { x.open = true; });
      despuesDeMover(true);
    });
    // pedido desde el panel, el buscador o la ficha (no desde los ganchos ni el minimapa): el recuadro pasa a la vista y
    // recibe el foco, para que la persona vea adónde la llevó (en el teléfono queda 2.000 px más arriba)
    if (d.alRecuadro) alRecuadro();
  }
  function alRecuadro() {
    if (!activo) return;
    const r = stage.getBoundingClientRect();
    if (r.top < 0 || r.bottom > innerHeight) stage.scrollIntoView({ block: 'center', behavior: movReducido() ? 'auto' : 'smooth' });
    stage.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- capas (6.5 y 16.3)
  function ponerCapa(nombre, on) {
    if (!(nombre in capas)) return;
    if (nombre === 'contraste' && !datos.coloresContraste?.size) on = false;
    capas[nombre] = !!on;
    if (on && nombre === 'estado') capas.contraste = false;
    if (on && nombre === 'contraste') capas.estado = false;
    panel.querySelectorAll('[data-capa]').forEach((b) => b.setAttribute('aria-pressed', String(!!capas[b.dataset.capa])));
    if (nombre === 'infraestructura' && cur && cur.capa) {
      cur.capa.dispose();
      cur.capa = armarCapa(cur.nivel, cur.unidades, cur.calidad);
      st.scene.add(cur.capa.objeto);
      if (resaltados) cur.capa.resaltar(resaltados);
      if (recintoActual) cur.capa.entrarRecinto(recintoActual);
    }
    aplicarCapas();
    st.invalidate();
  }
  function aplicarCapas() {
    if (!cur) return;
    cur.capa?.fantasma(capas.faltantes);
    const estadoDe = (id) => modelo?.estadoRecinto(id) || null;
    let mapa = null, leyenda = '';
    if (capas.estado) {
      mapa = new Map();
      for (const r of cur.nivel.recintos || []) mapa.set(r.id, tono(colorEstado(estadoDe(r.id))));
      leyenda = `Piso de cada recinto según su cumplimiento en dotación e infraestructura (hoy): ${['cumple', 'parcial', 'falta', 'documento_pendiente'].map((e) => `<i style="background:#${colorEstado(e).getHexString()}"></i>${esc(ESTADOS_R[e])}`).join(' ')}. Sin color: sin exigencias que evaluar.`;
    } else if (capas.contraste && datos.coloresContraste?.size) {
      mapa = new Map();
      for (const r of cur.nivel.recintos || []) mapa.set(r.id, datos.coloresContraste.get(r.id) ? tono(datos.coloresContraste.get(r.id), 0.25) : null);
      leyenda = 'Piso teñido en los recintos que tienen un ambiente comparable en el proyecto tipo (colores del contraste).';
    } else if (capas.faltantes) {
      mapa = new Map();
      for (const r of cur.nivel.recintos || []) { const e = estadoDe(r.id); if (e === 'falta' || e === 'parcial') mapa.set(r.id, tono(colorEstado(e))); }
    }
    if (capas.faltantes) leyenda += `${leyenda ? ' ' : ''}En violeta translúcido, lo que propone el cierre de brechas${capas.estado || capas.contraste ? '' : '; recintos con exigencias que faltan (rojo) o a medias (amarillo)'}.`;
    cur.planta.colorearRecintos(mapa);
    pLeyenda.innerHTML = leyenda;
    pLeyenda.hidden = !leyenda;
    marcaMapa.rec = Symbol('capa');
  }

  // ---------------------------------------------------------------- selección (6.4): rayo propio, la unidad solo si es el primer impacto
  const rayo = new THREE.Raycaster();
  function seleccionar({ clientX, clientY, centro }) {
    if (!cur || saltando) return;
    const r = (engine.renderer?.domElement || stage).getBoundingClientRect();
    const ndc = centro ? new THREE.Vector2(0, 0) : new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    colocarCamara();
    rayo.setFromCamera(ndc, st.camera);
    rayo.far = 80;
    const h = elegido(rayo);
    if (!h) return;
    if (h.tipo === 'unidad') { resaltados = [String(h.id)]; cur.capa?.resaltar(resaltados); mostrarFicha({ unidad: h.id }); }
    else if (h.tipo === 'implemento') { resaltados = [String(h.dest)]; cur.capa?.resaltar(resaltados); mostrarFicha({ implemento: [h.uid, h.k] }); }
    else if (h.tipo === 'recinto') mostrarFicha({ recinto: h.id });
    st.invalidate();
  }
  function elegido(ray) {
    const muros = [cur.planta.mallaMuros, cur.plantaCtx?.mallaMuros].filter(Boolean);
    const muro = ray.intersectObjects(muros, false)[0] || null;
    const dm = muro ? muro.distance : Infinity;
    const u = cur.capa?.pick(ray) || null;
    let mejor = u && u.distancia <= dm + 0.02 ? { tipo: 'unidad', id: u.unidad, d: u.distancia } : null;
    if (cur.impl) {
      const hi = ray.intersectObjects(cur.impl.mallas, false)[0];
      if (hi && hi.distance <= dm + 0.02 && (!mejor || hi.distance < mejor.d)) {
        const it = hi.object.userData.items[hi.instanceId];
        mejor = { tipo: 'implemento', uid: it.uid, k: it.k, dest: it.dest.id, d: hi.distance };
      }
    }
    if (mejor) return mejor;
    const piso = cur.planta.mallaPisos ? ray.intersectObject(cur.planta.mallaPisos, false)[0] : null;
    if (piso && piso.distance < dm) {
      const x = piso.point.x, y = -piso.point.z, id = cur.planta.subrecintoEn(x, y) || cur.planta.recintoEn(x, y);
      if (id) return { tipo: 'recinto', id, d: piso.distance };
    }
    return null;
  }

  // ---------------------------------------------------------------- ficha (torre.ficha.modo)
  let fichaActual = null;
  function mostrarFicha(q) {
    if (!modelo) return;
    fichaActual = q;
    let html = '';
    if (q.unidad) {
      const u = modelo.unidad(q.unidad), nivelU = u && idNivel(u.nivel);
      const ir = u && nivelU && niveles.has(nivelU) ? `<p class="reco-ficha-ir"><button type="button" class="reco-ir" data-ir="${escH(u.id)}">Ir a esta unidad</button></p>` : '';
      html = modelo.fichaUnidad(q.unidad) + ir;
    } else if (q.implemento) html = modelo.fichaImplemento(q.implemento[0], q.implemento[1]);
    else if (q.recinto) html = modelo.fichaRecinto(q.recinto);
    if (!html) return;
    ficha.innerHTML = `<div class="reco-ficha" tabindex="-1">${html}</div>`;
    ficha.hidden = false;
    const u = q.unidad || q.implemento ? modelo.unidad(q.unidad || q.implemento[0]) : null;
    const nombre = q.unidad ? u?.nombre : q.implemento ? (u && modelo.itemsDe(u)[q.implemento[1]]?.n) : nombreRec(q.recinto);
    verFicha.textContent = `Ver ficha: ${limpio(String(nombre || '')).split(' (')[0]}`;
    verFicha.setAttribute('aria-label', `Ver la ficha de ${limpio(String(nombre || ''))}, debajo del recuadro`);
    revisarFicha();
  }
  // el botón «Ver ficha» aparece solo mientras la ficha abierta está fuera de la pantalla
  let rafFicha = 0;
  function revisarFicha() {
    cancelAnimationFrame(rafFicha);
    rafFicha = requestAnimationFrame(() => {
      if (!activo || ficha.hidden || !ficha.firstElementChild) { verFicha.hidden = true; return; }
      const r = ficha.getBoundingClientRect();
      verFicha.hidden = r.top < innerHeight - 48 && r.bottom > 48;
    });
  }
  addEventListener('scroll', revisarFicha, { passive: true });
  addEventListener('resize', revisarFicha, { passive: true });
  verFicha.addEventListener('click', () => {
    const f = ficha.querySelector('.reco-ficha');
    if (!f) return;
    (ficha.closest('.card') || ficha).scrollIntoView({ block: 'start', behavior: movReducido() ? 'auto' : 'smooth' });
    f.focus({ preventScroll: true });
    verFicha.hidden = true;
  });
  ficha.addEventListener('click', (ev) => {
    if (!activo) return;
    const ir = ev.target.closest('[data-ir]');
    if (ir) { irA({ unidad: ir.dataset.ir, alRecuadro: true }); return; }
    const b = ev.target.closest('[data-unidad]');
    if (b) {
      const u = modelo?.unidad(b.dataset.unidad);
      if (u && cur && idNivel(u.nivel) === cur.id) { resaltados = [String(u.id)]; cur.capa?.resaltar(resaltados); st.invalidate(); }
      mostrarFicha({ unidad: b.dataset.unidad });
    }
  });

  // ---------------------------------------------------------------- panel: recinto actual, lista y «Ir a…»
  function nombreRec(id) { return modelo ? modelo.nombreRecinto(id) : limpio(cur?.planta.recinto(id)?.ambiente || id || ''); }
  function pintarRecinto() {
    const id = recintoActual;
    if (!cur) return;
    const r = id ? cur.planta.recinto(id) : null;
    if (!r) {
      pRec.textContent = CORTO_NIVEL[cur.id] || cur.id;
      pSub.textContent = 'Fuera de los recintos del nivel';
      pLista.innerHTML = '';
      donde.textContent = `${SIGLA_NIVEL[cur.id] || cur.id} · fuera de los recintos`;
      return;
    }
    const sub = subActual ? modelo?.recintos.get(subActual) : null;
    pRec.textContent = `${limpio(r.ambiente || r.nombre || id)}${sub ? ` · ${limpio(sub.ambiente || '')}` : ''}`;
    donde.textContent = `${SIGLA_NIVEL[cur.id] || cur.id} · ${pRec.textContent}`;
    const e = modelo?.estadoRecinto(id), pr = hab?.por_recinto?.[id] || inv?.recintos?.[id];
    const exig = pr ? (pr.exigencias || pr.exig || []).length : 0;
    const area = r.area_ejes_m2 ? `${(+r.area_ejes_m2).toLocaleString('es-CO', { maximumFractionDigits: 1 })} m² a ejes${r.area_libre_m2 ? ` (${(+r.area_libre_m2).toLocaleString('es-CO', { maximumFractionDigits: 1 })} libres)` : ''}` : '';
    pSub.innerHTML = [esc(CORTO_NIVEL[cur.id]), r.servicio_programa ? esc(r.servicio_programa) : '', area,
      e ? `cumplimiento en dotación e infraestructura: <b>${esc((ESTADOS_R[e] || e).toLowerCase())}</b> (${exig - (pr?.por_confirmar || 0)} exigibles${pr?.por_confirmar ? `, ${pr.por_confirmar} por confirmar` : ''})` : ''].filter(Boolean).join(' · ');
    pLista.innerHTML = modelo ? modelo.listaRecinto(id) : '';
  }
  pLista.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-unidad]');
    if (!b || !cur) return;
    resaltados = (b.dataset.unidades || b.dataset.unidad).split(' ');
    cur.capa?.resaltar(resaltados);
    mostrarFicha({ unidad: b.dataset.unidad });
    st.invalidate();
  });
  $('.reco-ficha-rec').addEventListener('click', () => { if (recintoActual) mostrarFicha({ recinto: subActual || recintoActual }); });
  function pintarRecintos() {
    if (!cur) return;
    // los recintos repetidos del programa (varios baños, consultorios o ambientes de aseo) llevan su número y su servicio
    const lista = (n) => {
      const fuera = recintosNoDestino(n);
      const L = (n.recintos || []).filter((r) => r.transitable !== false && !fuera.has(r.id)).map((r) => [r.id, limpio(r.ambiente || r.nombre || r.id), r]);
      const veces = new Map();
      for (const [, t] of L) veces.set(t, (veces.get(t) || 0) + 1);
      return L.map(([id, t, r]) => [id, veces.get(t) > 1 ? `${t} (${[r.de > 1 ? `${r.k} de ${r.de}` : '', limpio(r.servicio_programa || '')].filter(Boolean).join(', ')})` : t])
        .sort((a, b) => a[1].localeCompare(b[1], 'es', { numeric: true }));
    };
    const propios = lista(cur.nivel);
    const bt = cur.id !== 'BT' && niveles.has('BT') ? lista(niveles.get('BT')) : [];
    pIraT.textContent = `Recintos ${DEL_NIVEL[cur.id]} (${propios.length})${bt.length ? ' y del bloque técnico' : ''}:`;
    const li = ([id, t]) => `<li><button type="button" data-recinto="${escH(id)}">${esc(t)}</button></li>`;
    pRecintos.innerHTML = propios.map(li).join('') + (bt.length ? `<li class="reco-sep" aria-hidden="true">Bloque técnico</li>${bt.map(li).join('')}` : '');
  }
  panel.addEventListener('click', (ev) => {
    const c = ev.target.closest('[data-capa]');
    if (c && !c.disabled) { ponerCapa(c.dataset.capa, c.getAttribute('aria-pressed') !== 'true'); return; }
    const n = ev.target.closest('[data-nivel]');
    if (n) { irA({ nivel: n.dataset.nivel, alRecuadro: true }); return; }
    const e = ev.target.closest('[data-entrada]');
    if (e) { const [nv, en] = e.dataset.entrada.split(':'); irA({ nivel: nv, entrada: en, alRecuadro: true }); return; }
    const r = ev.target.closest('[data-recinto]');
    if (r) irA({ recinto: r.dataset.recinto, ficha: true, alRecuadro: true });
  });

  // ---------------------------------------------------------------- barra, ascensor y salida
  barra.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-acc]');
    if (!b) return;
    accion(b.dataset.acc);
    // el foco vuelve al recuadro: con él en el botón, Espacio (saltar o subir) lo volvería a pulsar
    if ((b.dataset.acc === 'espectador' || b.dataset.acc === 'pantalla') && activo) stage.focus({ preventScroll: true });
  });
  asc.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-piso]');
    if (!b || !cur) return;
    const id = b.dataset.piso, cx = cur.ascensores.find((c) => c.id === asc.dataset.asc) || cur.ascensores[0];
    if (id === cur.id) return;
    const p = cx?.puntos?.[CLAVE_PISO[id]];
    saltar(() => {
      if (p) ponerEnNivel(id, p[0], p[1], { yaw: 0, pitch: 0 }); else irANivel(id);
      despuesDeMover(true);
      avisar(`${CORTO_NIVEL[id]}`);
    });
  });
  salida.addEventListener('click', () => salir({ porUsuario: true }));
  function accion(a, extra) {
    switch (a) {
      case 'subir': subirBajar(1); return true;
      case 'bajar': subirBajar(-1); return true;
      case 'mapa': mostrarMapa(!mapa.visible()); return true;
      case 'bt': irA({ nivel: 'BT' }); return true;
      case 'mirar':
        if (ctl.tomado()) ctl.soltarPuntero();
        else if (!ctl.tomarPuntero()) avisar('Este navegador no deja tomar el puntero aquí: arrastra para mirar.');
        return true;
      // controles_fp avisa los cambios del Pointer Lock: retícula central y botón
      case 'puntero': mira.hidden = !extra; btnPuntero.setAttribute('aria-pressed', String(!!extra)); if (!extra) ultimoEsc = performance.now(); return true;
      case 'puntero_bloqueado': avisar('Este navegador no deja tomar el puntero aquí: arrastra para mirar.'); return true;
      case 'salir': salir({ porUsuario: true }); return true;
      case 'espectador': ponerEspectador(!espectador); return true;
      case 'pantalla': ponerPantalla(!enPantalla); return true;
      case 'panel':
        // el panel está fuera del recuadro: en pantalla completa, primero se sale de ella
        if (enPantalla) ponerPantalla(false);
        pRec.focus({ preventScroll: true }); pRec.scrollIntoView({ block: 'nearest' }); return true;
      case 'tab': { const f = panel.querySelector('button:not([disabled]), summary, input, select'); if (f) { f.focus(); return true; } return false; }
      case 'esc':
        // con el puntero tomado, el primer Esc lo suelta (el navegador) y el segundo sale del recorrido; en pantalla
        // completa, el siguiente sale de ella y solo después Esc sale del recorrido
        if (ctl.tomado()) { ctl.soltarPuntero(); return true; }
        if (enPantalla) { ponerPantalla(false); return true; }
        if (performance.now() - ultimoEsc < 80) return true;
        salir({ porUsuario: true });
        return true;
      default: return false;
    }
  }
  function mostrarMapa(on) { mapa.mostrar(on); btnMapa.setAttribute('aria-pressed', String(!!on)); if (on) dibujarMapa(true); }

  // ---------------------------------------------------------------- después de moverse: recinto, panel, etiquetas, mapa, ayudas
  let claveAsc = '';
  function despuesDeMover(todo = false) {
    if (!cur) return;
    const rec = cur.planta.recintoEn(w.x, w.y), sub = rec ? cur.planta.subrecintoEn(w.x, w.y, rec) : null;
    if (rec !== recintoActual || sub !== subActual || todo) {
      const cambio = rec !== recintoActual;
      recintoActual = rec; subActual = sub;
      if (cambio || todo) { cur.capa?.entrarRecinto(rec); armarImplementos(rec); }
      clearTimeout(tRecinto);
      tRecinto = setTimeout(pintarRecinto, todo ? 0 : 120);
    }
    // etiquetas y mapa
    if (todo || Math.hypot(w.x - marcaEtiquetas.x, w.y - marcaEtiquetas.y) > 0.4 || marcaEtiquetas.rec !== rec) actualizarEtiquetas();
    dibujarMapa(todo);
    // ascensor, salida y escalera
    const enCabina = rec && cur.cabinas.has(rec);
    // botones del ascensor: dentro de una cabina, en el vestíbulo de ascensores o a menos de 3,2 m de una cabina
    const distAsc = (c) => { const p = c.puntos[CLAVE_PISO[cur.id]]; return Math.hypot(p[0] - w.x, p[1] - w.y); };
    const enVestibulo = rec && /vest[ií]bulo de ascensores/i.test(cur.planta.recinto(rec)?.ambiente || '');
    const cerca = cur.ascensores.filter((c) => enVestibulo || distAsc(c) < 3.2).sort((a, b) => distAsc(a) - distAsc(b))[0];
    const cx = enCabina ? cur.ascensores.find((c) => { const p = c.puntos[CLAVE_PISO[cur.id]]; return enPoligono(p[0], p[1], cur.planta.recinto(rec).poligono); }) || cerca : cerca;
    if (cx) {
      if (claveAsc !== `${cx.id}|${cur.id}`) {
        claveAsc = `${cx.id}|${cur.id}`;
        asc.innerHTML = `<span>${esc(cx.nombre ? limpio(cx.nombre).replace(/\s*\(.*$/, '') : 'Ascensor')}</span>${cx.pisos.map((p) => { const id = idNivel(p); return id && niveles.has(id) ? `<button type="button" data-piso="${id}" aria-label="Ir al ${escH(CORTO_NIVEL[id].toLowerCase())} en el ascensor"${id === cur.id ? ' aria-current="true"' : ''}>${esc(String(p).replace('cubierta', 'C'))}</button>` : ''; }).join('')}`;
        asc.dataset.asc = cx.id;
      }
      asc.hidden = false;
    } else asc.hidden = true;
    const puerta = cur.salidas.find((p) => Math.hypot(p.centro[0] - w.x, p.centro[1] - w.y) < 1.1);
    salida.hidden = !puerta;
    const esc0 = rec && cur.escaleras.has(rec);
    pista.hidden = !esc0;
    if (esc0) pista.textContent = 'Escalera: camina por los tramos para subir o bajar de nivel.';
  }
  function actualizarEtiquetas() {
    asegurarEtiquetas();
    marcaEtiquetas = { x: w.x, y: w.y, rec: recintoActual };
    const lim = ctl.tactil() || cur?.calidad === 'baja' ? 6 : ETIQUETAS;
    const cands = [];
    if (cur && recintoActual) {
      const z0 = cur.nivel.z;
      // los nombres de los recintos vecinos sobre las puertas del actual (señalización)
      const vistas = new Set();
      for (const p of cur.puertasDe.get(recintoActual) || []) {
        const otro = p.desde === recintoActual ? p.hacia : p.desde;
        if (!otro || otro === 'exterior' || vistas.has(otro)) continue;
        const d = Math.hypot(p.centro[0] - w.x, p.centro[1] - w.y);
        if (d > DIST_ETIQUETAS) continue;
        vistas.add(otro);
        const r = cur.planta.recinto(otro);
        const t = r ? limpio(r.ambiente || r.nombre || '') : '';
        if (!t) continue;
        cands.push({ d, cls: 'lbl-room reco-senal', html: esc(corto(t, 34)), pos: [p.centro[0], z0 + cotaPiso(cur.planta.recinto(recintoActual), p.centro[0], p.centro[1]) + (+p.alto || 2.1) + 0.32, p.centro[1]] });
      }
      // las unidades del recinto (una por línea, la más cercana), sin la infraestructura menuda
      const porLinea = new Map();
      for (const n of cur.unidades) {
        if (String(n.recinto) !== String(recintoActual)) continue;
        const u = modelo?.unidad(n.id), dd = cur.dims.get(String(n.id));
        if (!u || !dd?.dibujada || u.capa === 'infraestructura' || u.componente >= 0) continue;
        if (u.estado === 'cierre_brechas_propuesto' && !capas.faltantes) continue;
        const d = Math.hypot(n.x - w.x, n.y - w.y);
        if (d > DIST_ETIQUETAS) continue;
        const k = u.li, prev = porLinea.get(k);
        if (!prev) porLinea.set(k, { d, n, u, dd, c: 1 }); else { prev.c++; if (d < prev.d) Object.assign(prev, { d, n, u, dd }); }
      }
      for (const { d, n, u, dd, c } of porLinea.values()) {
        cands.push({ d: d + 0.01, cls: 'lbl-node reco-lbl', html: `${c > 1 ? `${c} × ` : ''}${esc(corto(u.nombre.split(' (')[0], 30))}`, pos: [n.x, z0 + (n.z || 0) + dd.dim[2] + 0.18, n.y] });
      }
    }
    const puertas = cands.filter((c) => c.cls.includes('senal')).sort((a, b) => a.d - b.d).slice(0, Math.ceil(lim / 2));
    const resto = cands.filter((c) => !c.cls.includes('senal')).sort((a, b) => a.d - b.d).slice(0, lim - puertas.length);
    const elegidas = puertas.concat(resto);
    etiquetas.forEach((o, i) => {
      const c = elegidas[i];
      if (!c) { o.visible = false; o.element.style.display = 'none'; return; }
      o.element.className = `lbl ${c.cls}`;
      o.position.set(c.pos[0], c.pos[1], -c.pos[2]);
      o.visible = true;
      o.element.style.display = '';
      if (o.element.innerHTML !== c.html) { o.element.innerHTML = c.html; o.userData.wh = null; }
    });
    recortarEtiquetas();
  }
  // una etiqueta que se saldría del recuadro se esconde. El tamaño se mide una sola vez por texto, cuando el elemento ya
  // está en la capa de etiquetas (CSS2DRenderer lo agrega en su primer cuadro); mientras tanto queda escondida
  const _pe = new THREE.Vector3();
  let porMedir = false;
  function recortarEtiquetas() {
    const W = stage.clientWidth, H = stage.clientHeight;
    porMedir = false;
    // lo que está sobre el recuadro (barra, minimapa, botón «Rendimiento», ascensor, salida, joystick) no se tapa con etiquetas
    const r0 = stage.getBoundingClientRect(), bl = stage.clientLeft, bt = stage.clientTop;
    const tapas = [barra, donde, verFicha, mapa.el, asc, salida, stage.querySelector(':scope > .hud-btn'), hud.querySelector('.reco-joy')]
      .filter((e) => e && !e.hidden && e.offsetParent !== null)
      .map((e) => { const r = e.getBoundingClientRect(); return [r.left - r0.left - bl - 4, r.top - r0.top - bt - 4, r.right - r0.left - bl + 4, r.bottom - r0.top - bt + 4]; });
    for (const o of etiquetas) {
      if (!o.visible) continue;
      if (!o.userData.wh) {
        if (!o.element.isConnected || !o.element.offsetWidth) { o.element.style.visibility = 'hidden'; porMedir = true; continue; }
        o.userData.wh = [o.element.offsetWidth, o.element.offsetHeight];
      }
      _pe.copy(o.position).project(st.camera);
      const [ew, eh] = o.userData.wh, x = ((_pe.x + 1) / 2) * W, y = ((1 - _pe.y) / 2) * H;
      // de lado se corre hacia adentro (hasta el 60 % de su ancho); si no alcanza, o si se sale por arriba o por abajo, se esconde
      const corr = x - ew / 2 < 2 ? 2 - (x - ew / 2) : x + ew / 2 > W - 2 ? W - 2 - (x + ew / 2) : 0;
      const cx = x + corr, tapa = tapas.some(([a, b, c, d]) => cx + ew / 2 > a && cx - ew / 2 < c && y + eh / 2 > b && y - eh / 2 < d);
      const dentro = _pe.z < 1 && !tapa && Math.abs(corr) <= ew * 0.6 && ew <= W - 4 && y - eh / 2 >= 2 && y + eh / 2 <= H - 2;
      o.element.style.visibility = dentro ? '' : 'hidden';
      o.element.style.marginLeft = dentro && corr ? `${Math.round(corr)}px` : '';
    }
  }
  const corto = (s, n) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
  function dibujarMapa(todo) {
    if (!cur || !mapa.visible()) return;
    const ahora = performance.now();
    const m = marcaMapa;
    if (!todo && m.rec === recintoActual && Math.hypot(w.x - m.x, w.y - m.y) < 0.15 && Math.abs(w.yaw - m.yaw) < 0.04) return;
    if (!todo && ahora - m.t < 90) return;
    marcaMapa = { x: w.x, y: w.y, yaw: w.yaw, rec: recintoActual, t: ahora };
    let colores = null;
    if (capas.estado) colores = new Map((cur.nivel.recintos || []).map((r) => [r.id, colorEstado(modelo?.estadoRecinto(r.id))]).filter(([, c]) => c));
    else if (capas.contraste && datos.coloresContraste?.size) colores = datos.coloresContraste;
    mapa.dibujar({ nivel: cur.nivel, nombre: CORTO_NIVEL[cur.id], grupos, posicion: [w.x, w.y], rumbo_deg: grados(w.yaw), recinto: recintoActual, colores });
  }

  // ---------------------------------------------------------------- cuadro (6.8, paso 3): una sola función, false si no hay nada que dibujar
  // El caminante usa su propio reloj (el del motor se corta en 50 ms por cuadro): así camina a 1,4 m/s también en un
  // equipo lento; con un salto de más de 0,25 s (pestaña en segundo plano, vista detenida) el paso se corta allí
  const _dir = new THREE.Vector2();
  let tPrev = 0;
  function cuadro() {
    const ahora = performance.now(), dt = Math.min(0.25, Math.max(0, (ahora - (tPrev || ahora)) / 1000));
    tPrev = ahora;
    if (!activo || !cur) return false;
    if (enPantalla && !simulada && !enCompleta()) estadoPantalla(false);
    if (porMedir) recortarEtiquetas();
    let mover = forzar;
    forzar = false;
    if (st.camera.aspect !== aspecto) { ajustarFov(); mover = true; }
    if (cur.calidad !== (engine.tier || 'media') && !saltando) {
      const { h, hp, vz, aire } = w;
      ponerEnNivel(cur.id, w.x, w.y, { h: hp });
      Object.assign(w, { h, hp, vz, aire });
      mover = true;
    }
    const i = ctl.leer();
    if (i.dyaw || i.dpitch || i.giro) {
      w.yaw += i.dyaw + i.giro * GIRO * dt;
      w.pitch = THREE.MathUtils.clamp(w.pitch + i.dpitch, -PITCH_MAX, PITCH_MAX);
      mover = true;
    }
    if (espectador) {
      if (!saltando && volar(i, dt)) mover = true;
    } else {
      if ((i.adelante || i.lado) && !saltando) {
        const v = (i.rapido ? VEL_RAPIDA : VEL) * dt;
        const c = Math.cos(w.yaw), s = Math.sin(w.yaw);
        _dir.set(c * i.adelante + s * i.lado, s * i.adelante - c * i.lado);
        if (_dir.lengthSq() > 1) _dir.normalize();
        const dx = _dir.x * v, dy = _dir.y * v;
        const bloqueado = moverCaminante(dx, dy);
        if (bloqueado && !w.aire) cruzarPuerta(dx, dy);
        mover = true;
      }
      if (i.salto && !w.aire && !saltando) { w.vz = V_SALTO; w.aire = true; }
      // sin apoyo (se quitó de la rejilla lo que tenía bajo los pies), cae
      if (!w.aire && !saltando && w.h > (superficie(w.x, w.y, w.hp) ?? w.hp) + encima(w.x, w.y) + 0.02) { w.aire = true; w.vz = 0; }
      if (w.aire && !saltando) { caer(dt); mover = true; }
      // escaleras: el nivel cambia cuando los ojos de quien camina pasan la losa de arriba o bajan de la propia (con el
      // piso que pisa y ya en el suelo: un salto no cambia de nivel y el techo del otro nivel no lo corta en el aire)
      if (mover && !w.aire && enEscalera(w.x, w.y)) {
        if (cur.arriba && w.hp > cur.dzArriba - SUBE) cambiarPorEscalera(cur.arriba);
        else if (cur.abajo && w.hp < -BAJA) cambiarPorEscalera(cur.abajo);
      }
    }
    if (!mover) return false;
    colocarCamara();
    despuesDeMover();
    recortarEtiquetas();
    return true;
  }
  // puertas que llevan a otro nivel (exteriores ↔ piso 1, exteriores ↔ bloque técnico, piso 4 ↔ terraza): se cruzan caminando
  function cruzarPuerta(dx, dy) {
    const L = Math.hypot(dx, dy);
    if (!L) return false;
    for (const p of cur.pasos) {
      // dirección de cruce: la normal del muro de la puerta, hacia donde camina la persona
      let ux = dx / L, uy = dy / L;
      const pu = p.puerta && (cur.nivel.puertas || []).find((q) => q.id === p.puerta), m = pu && cur.muros.get(pu.muro);
      if (m) {
        // frente al vano: dentro de su ancho a lo largo del muro, a menos de 0,95 m de él y caminando hacia él. Así se cruza
        // también pegado al marco de una puerta ancha (con el ángulo al centro, desde un costado no cruzaba)
        const Lm = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1, ex = (m.b[0] - m.a[0]) / Lm, ey = (m.b[1] - m.a[1]) / Lm;
        let nx = -ey, ny = ex;
        if (nx * dx + ny * dy < 0) { nx = -nx; ny = -ny; }
        const rx = w.x - p.punto[0], ry = w.y - p.punto[1], s = rx * nx + ry * ny;
        if (Math.abs(rx * ex + ry * ey) > (+pu.ancho || 0.9) / 2 || s < -0.95 || s > 0.1 || (nx * dx + ny * dy) / L < 0.3) continue;
        ux = nx; uy = ny;
      } else {
        const vx = p.punto[0] - w.x, vy = p.punto[1] - w.y, d = Math.hypot(vx, vy);
        if (d > 0.95 || (d > 0.05 && (vx * dx + vy * dy) / (L * d) < 0.3)) continue;
      }
      const destino = niveles.get(p.otro_nivel);
      if (!destino) continue;
      const tx = p.punto[0] + ux * 0.7, ty = p.punto[1] + uy * 0.7;
      ponerEnNivel(p.otro_nivel, tx, ty, { yaw: w.yaw });
      const [x, y] = libreCerca(tx, ty, p.otro_recinto || null, 1.5);
      w.x = x; w.y = y; aterrizar(sueloEn(x, y));
      avisar(`${CORTO_NIVEL[p.otro_nivel]}: ${nombreRec(p.otro_recinto)}`);
      despuesDeMover(true);
      return true;
    }
    return false;
  }

  // ---------------------------------------------------------------- modo espectador (V): vuela y atraviesa todo
  // Adelante va hacia donde se mira (rumbo e inclinación), el paso lateral es horizontal, Espacio sube y Shift baja; la
  // rueda multiplica la velocidad. Sin rejilla ni gravedad: el nivel armado es el que tiene los ojos (cambia al pasar una
  // losa o la fachada) y al volver a caminar se cae al piso que quede debajo
  const _vuelo = new THREE.Vector3();
  const zonaVuelo = (() => {
    const pts = [...niveles.values()].flatMap((n) => n.contorno || []);
    if (!pts.length) return [-200, -200, 200, 200];
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
    return [Math.min(...xs) - 80, Math.min(...ys) - 80, Math.max(...xs) + 80, Math.max(...ys) + 80];
  })();
  function volar(i, dt) {
    const vert = (i.arriba ? 1 : 0) - (i.abajo ? 1 : 0);
    if (!i.adelante && !i.lado && !vert) return false;
    const v = VEL_ESPECTADOR * velEspectador * dt;
    const c = Math.cos(w.yaw), s = Math.sin(w.yaw), cp = Math.cos(w.pitch), sp = Math.sin(w.pitch);
    _vuelo.set(c * cp * i.adelante + s * i.lado, s * cp * i.adelante - c * i.lado, sp * i.adelante + vert);
    if (_vuelo.lengthSq() > 1) _vuelo.normalize();
    const [a0, b0, a1, b1] = zonaVuelo;
    w.x = THREE.MathUtils.clamp(w.x + _vuelo.x * v, a0, a1);
    w.y = THREE.MathUtils.clamp(w.y + _vuelo.y * v, b0, b1);
    w.h = THREE.MathUtils.clamp(w.h + _vuelo.z * v, -25 - cur.nivel.z, 90 - cur.nivel.z);
    revisarNivelVuelo();
    return true;
  }
  // nivel que contiene los ojos en (x, y, z absoluta): el de piso más alto bajo los ojos y techo encima, cuyo contorno
  // contiene el punto (la cubierta no tiene techo; su terraza está 4,20 m más abajo y cuenta desde allí); si ninguno, los
  // exteriores
  function pisoEn(n, x, y) {
    for (const r of n.recintos || []) if (r.poligono?.length && enPoligono(x, y, r.poligono)) return +r.z_piso_m || 0;
    return 0;
  }
  function contiene(id, x, y, z, tol = 0) {
    const n = niveles.get(id);
    if (!n || id === 'EXT' || !n.contorno?.length || !enPoligono(x, y, n.contorno)) return null;
    const base = n.z + pisoEn(n, x, y), arriba = id === 'CUB' ? Infinity : n.z + (+n.altura_entrepiso_m || 4.2);
    return z >= base - tol && z < arriba + tol ? base : null;
  }
  function nivelDeLosOjos(x, y, z) {
    let mejor = 'EXT', zm = -Infinity;
    for (const id of ordenNiveles) { const b = contiene(id, x, y, z); if (b != null && b > zm) { zm = b; mejor = id; } }
    return mejor;
  }
  function revisarNivelVuelo() {
    const ahora = performance.now();
    if (ahora - tEspectador < 350) return;
    const z = cur.nivel.z + w.h + OJOS;
    // con histéresis: el nivel actual sigue mientras lo contenga con 0,2 m de margen
    if (cur.id !== 'EXT' && contiene(cur.id, w.x, w.y, z, 0.2) != null) return;
    const id = nivelDeLosOjos(w.x, w.y, z);
    if (id === cur.id) return;
    tEspectador = ahora;
    const pies = z - OJOS;
    ponerEnNivel(id, w.x, w.y, { h: pies - niveles.get(id).z });
    despuesDeMover(true);
  }
  function ponerEspectador(on) {
    if (!cur || on === espectador) return;
    espectador = on;
    btnEspectador.setAttribute('aria-pressed', String(on));
    ctl.marcar({ espectador: on });
    insignia.hidden = !on;
    stage.classList.toggle('reco-volando', on);
    ctl.modoEspectador(on);
    if (on) { w.aire = false; w.vz = 0; avisar('Modo espectador: atraviesas muros y losas. V para volver a caminar.'); }
    else bajarDelVuelo();
    forzar = true;
    st.invalidate();
  }
  // de vuelta a caminar: dentro de un muro, de un equipo o fuera de la planta, a la celda libre más cercana; bajo el piso
  // o sobre el cielo raso, de pie en el piso; en el aire bajo el techo (o al aire libre), cae
  function bajarDelVuelo() {
    const z = cur.nivel.z + w.h + OJOS, id = nivelDeLosOjos(w.x, w.y, z);
    if (id !== cur.id) ponerEnNivel(id, w.x, w.y, { h: z - OJOS - niveles.get(id).z });
    let x = w.x, y = w.y;
    if (!cur.rejilla.libre(x, y)) {
      const c = cur.rejilla.cercana(x, y, 8);
      if (!c) { const h = w.h; irANivel(cur.id); avisar(`De vuelta a caminar en ${limpio(entradaDe(cur.id).nombre || CORTO_NIVEL[cur.id])}.`); if (CIELO_ABIERTO.has(cur.id) && h > w.h) { w.h = h; w.aire = true; } return; }
      [x, y] = c;
    }
    const h = w.h, zf = sueloEn(x, y);
    w.x = x; w.y = y;
    aterrizar(zf);
    if (h > zf + 0.02 && h <= techo(x, y, zf) - OJOS - CABEZA) { w.h = h; w.aire = true; }
    despuesDeMover(true);
  }
  function rueda(ev) {
    if (!activo || !espectador) return;
    ev.preventDefault();
    velEspectador = THREE.MathUtils.clamp(velEspectador * (ev.deltaY < 0 ? 1.25 : 0.8), ESPECTADOR_MIN, ESPECTADOR_MAX);
    avisar(`Velocidad de vuelo: ${(VEL_ESPECTADOR * velEspectador).toLocaleString('es-CO', { maximumFractionDigits: 1 })} m/s`, 1200);
  }
  stage.addEventListener('wheel', rueda, { passive: false });

  // ---------------------------------------------------------------- pantalla completa (P): el recuadro solo, como un juego
  // Con la API de pantalla completa del navegador o, si no la da (iOS, un iframe sin permiso), el recuadro fijo sobre la
  // página. En escritorio se toma el puntero (clic en el lienzo para volver a tomarlo) y la ficha de lo tocado pasa a un
  // lateral del recuadro; al salir vuelve a su tarjeta
  const enCompleta = () => (document.fullscreenElement || document.webkitFullscreenElement) === stage;
  let fichaEn = null, tAyuda = 0, simulada = false;
  function ponerPantalla(on) {
    if (on === enPantalla) return;
    if (!on) {
      if (enCompleta()) { try { const r = (document.exitFullscreen || document.webkitExitFullscreen)?.call(document); r?.catch?.(() => {}); } catch { /* */ } }
      else estadoPantalla(false);
      return;
    }
    const pedir = stage.requestFullscreen || stage.webkitRequestFullscreen;
    let r = null;
    try { r = pedir ? pedir.call(stage, { navigationUI: 'hide' }) : null; } catch { r = null; }
    if (!pedir) estadoPantalla(true, true);
    else if (r?.catch) r.catch(() => { if (!enPantalla) estadoPantalla(true, true); });
    // en el mismo gesto: el navegador puede dar el puntero junto con la pantalla completa
    ctl.tomarPuntero({ silencioso: true });
  }
  // la del navegador manda: si sale de ella sin avisar (o el aviso se pierde), el estado vuelve a cuadrar al primer cuadro,
  // al cambiar el tamaño de la ventana o con fullscreenchange
  function alCambiarPantalla() {
    if (enPantalla && simulada) return;
    const fs = enCompleta();
    if (fs !== enPantalla) estadoPantalla(fs);
  }
  function estadoPantalla(on, sim = false) {
    enPantalla = on;
    simulada = on && sim;
    stage.classList.toggle('reco-fs', on && simulada);
    document.documentElement.classList.toggle('reco-fs-doc', on && simulada);
    if (!on) stage.classList.remove('reco-fs');
    stage.classList.toggle('reco-pantalla', on);
    btnPantalla.setAttribute('aria-pressed', String(on));
    ctl.marcar({ pantalla: on });
    clearTimeout(tAyuda);
    if (on) {
      if (!fichaEn) { fichaEn = { padre: ficha.parentNode, sig: ficha.nextSibling }; lateral.append(ficha); }
      lateral.hidden = false;
      ayudaFs.hidden = false;
      tAyuda = setTimeout(() => { ayudaFs.hidden = true; }, 7000);
      ctl.tomarPuntero({ silencioso: true });
    } else {
      if (fichaEn) { fichaEn.padre.insertBefore(ficha, fichaEn.sig); fichaEn = null; }
      lateral.hidden = true; ayudaFs.hidden = true;
      // el Esc que sacó de la pantalla completa no saca del recorrido
      ultimoEsc = performance.now();
    }
    if (activo) stage.focus({ preventScroll: true });
    forzar = true;
    st.invalidate(true);
  }
  document.addEventListener('fullscreenchange', alCambiarPantalla);
  document.addEventListener('webkitfullscreenchange', alCambiarPantalla);
  addEventListener('resize', alCambiarPantalla);
  lateral.querySelector('.reco-fs-cerrar').addEventListener('click', () => { ficha.hidden = true; stage.focus({ preventScroll: true }); });

  st.onFrame(cuadro);
  quitarTema = onTheme((t) => { T = t; if (activo) { aplicarCapas(); dibujarMapa(true); } });

  // ---------------------------------------------------------------- entrar y salir (6.2 y 6.8)
  function entrar(op = {}) {
    if (!plantas || !niveles.size) {
      panel.innerHTML = '<p class="note">Las plantas de la torre todavía no se publicaron: el recorrido por dentro estará disponible cuando lleguen.</p>';
      panel.hidden = false;
      return;
    }
    if (!activo) {
      activo = true;
      guardarCamara();
      ajustarControles();
      encenderLuces(true);
      ctx.exterior.ocultar(true);
      hud.hidden = false; panel.hidden = false;
      stage.classList.add('reco-on');
      stage.setAttribute('tabindex', '-1');
      stage.setAttribute('role', 'application');
      stage.setAttribute('aria-label', 'Recorrido en primera persona por la torre. W A S D o flechas: caminar; Shift: rápido; Espacio: saltar; flechas izquierda y derecha: girar; arrastrar: mirar; R o RePág: subir; F o AvPág: bajar; V: modo espectador (vuela y atraviesa muros; Espacio sube y Shift baja); P: pantalla completa; M: minimapa; I: panel; Tab: pasa al panel; Esc: salir.');
      stage.focus({ preventScroll: true });
      ctl.mostrarJoystick(ctl.tactil());
      btnPuntero.hidden = !ctl.puedeBloquear();
      mostrarMapa(!ctl.tactil() && stage.clientWidth >= 560);
      asegurarEtiquetas();
    }
    const d = op || {};
    const conDestino = d.unidad || d.recinto || d.posicion || d.piso != null || d.nivel || d.entrada || d.laboratorio;
    // la primera entrada no lleva fundido (la vista acaba de cambiar de modo); las siguientes, sí. Sin destino se vuelve
    // a donde quedó la persona la última vez o, la primera vez, a la plaza frente a la puerta principal
    if (!cur) irASinFundido(conDestino ? d : ultimaPos || { nivel: 'EXT', entrada: 'puerta_principal' });
    else if (conDestino) irA(d);
    forzar = true;
    st.invalidate();
  }
  function irASinFundido(d) {
    activo = false;   // saltar() sin fundido
    try { irA(d); } finally { activo = true; }
    colocarCamara();
  }
  let ultimaPos = null;
  function salir({ porUsuario = false } = {}) {
    if (!activo) return;
    if (cur) ultimaPos = { nivel: cur.id, posicion: [w.x, w.y], rumbo_deg: grados(w.yaw), pitch_deg: 0 };
    if (enPantalla) ponerPantalla(false);
    if (espectador) {
      espectador = false;
      btnEspectador.setAttribute('aria-pressed', 'false'); ctl.marcar({ espectador: false }); insignia.hidden = true; stage.classList.remove('reco-volando'); ctl.modoEspectador(false);
    }
    activo = false;
    ctl.vaciar();
    ctl.soltarPuntero();
    clearTimeout(tRecinto);
    soltarNivel();
    recintoActual = null; subActual = null; resaltados = null;
    etiquetas.forEach((o) => { o.visible = false; o.element.style.display = 'none'; });
    suelo(false);
    encenderLuces(false);
    restaurarCamara();
    ctx.exterior.ocultar(false);
    hud.hidden = true; panel.hidden = true;
    ficha.innerHTML = ''; ficha.hidden = true; fichaActual = null; verFicha.hidden = true;
    stage.classList.remove('reco-on');
    stage.removeAttribute('tabindex'); stage.removeAttribute('role'); stage.removeAttribute('aria-label');
    mira.hidden = true; asc.hidden = true; salida.hidden = true; pista.hidden = true; aviso.hidden = true;
    fundido.classList.remove('on');
    st.invalidate(true);
    if (porUsuario) ctx.alSalir?.();
  }

  const api = {
    entrar,
    salir,
    irA: (d) => { if (!activo) entrar(d); else irA(d); },
    alReanudar() { if (activo) { ajustarControles(); forzar = true; st.invalidate(); } },
    alDetener() { ctl.vaciar(); },
    capa: (nombre, on) => ponerCapa(nombre, on),
    estado() {
      if (!cur) return null;
      const d = new THREE.Vector3();
      st.camera.getWorldDirection(d);
      const k = celda(w.x, w.y);
      return {
        piso: /^P[1-4]$/.test(cur.id) ? +cur.id.slice(1) : cur.id, nivel: cur.id, recinto: recintoActual, subrecinto: subActual,
        posicion: [+w.x.toFixed(3), +w.y.toFixed(3)], altura: +w.h.toFixed(3), rumbo_deg: +normGrados(grados(Math.atan2(-d.z, d.x))).toFixed(3),
        // en un muro: en lo duro (pararse sobre un equipo no es estar en un muro); libre: también parado encima de él
        en_muro: k < 0 || cur.rejilla.crudoDuro[k] === 1,
        libre: cur.rejilla.libre(w.x, w.y) || (k >= 0 && cur.rejilla.duro[k] !== 1 && encima(w.x, w.y) > 0 && w.h >= w.hp + encima(w.x, w.y) - 0.02),
        espectador, en_el_aire: w.aire, pantalla_completa: enPantalla,
      };
    },
    libre: (x, y) => (cur ? cur.rejilla.libre(x, y) : null),
    dispose() {
      salir({ porUsuario: false });
      const k = st.frameFns.indexOf(cuadro);
      if (k >= 0) st.frameFns.splice(k, 1);
      stage.removeEventListener('wheel', rueda);
      document.removeEventListener('fullscreenchange', alCambiarPantalla);
      document.removeEventListener('webkitfullscreenchange', alCambiarPantalla);
      removeEventListener('resize', alCambiarPantalla);
      ctl.dispose();
      mapa.dispose();
      removeEventListener('scroll', revisarFicha);
      removeEventListener('resize', revisarFicha);
      quitarTema?.();
      etiquetas.forEach((o) => { o.element.remove(); o.removeFromParent(); const i = st._labels.indexOf(o); if (i >= 0) st._labels.splice(i, 1); });
      etiquetas.length = 0;
      hud.innerHTML = ''; panel.innerHTML = '';
    },
  };
  // ganchos de QA (13.3): solo con «?qa» en la URL
  if (qa) {
    window.__recorridoQA = {
      api,
      camara: () => ({ near: st.camera.near, fov: st.camera.fov, aspect: st.camera.aspect, hfov: grados(2 * Math.atan(Math.tan(rad(st.camera.fov / 2)) * st.camera.aspect)), posicion: st.camera.position.toArray() }),
      antes: () => camaraAntes,
      controles: () => { const c = st.controls; return { minDistance: c.minDistance, maxDistance: c.maxDistance, minPolarAngle: c.minPolarAngle, maxPolarAngle: c.maxPolarAngle, enableDamping: c.enableDamping, enableRotate: c.enableRotate, enableZoom: c.enableZoom, enablePan: c.enablePan, fov: st.camera.fov }; },
      nivel: () => (cur ? { id: cur.id, calidad: cur.calidad, ms: tiempoNivel, tiempos, planta: cur.planta.stats(), contexto: cur.plantaCtx?.stats() || null, equipos: cur.capa?.stats() || null, implementos: cur.impl ? cur.impl.mallas.reduce((a, m) => a + m.count, 0) : 0, huellas: cur.huellas } : null),
      ficha: () => fichaActual,
      ultimoFundido: () => ultimoFundido,
      unidades: (filtro = {}) => (modelo ? modelo.buscar(filtro).unidades.map((u) => ({ id: u.id, nombre: u.nombre, nivel: u.nivel, recinto: u.recinto, capa: u.capa, modelo: u.modelo, items: modelo.itemsDe(u).length, montaje: u.montaje, estado: u.estado })) : []),
      // proyecta un punto de planta (x, y, z sobre el piso del nivel) a la pantalla, para los clics de la QA
      pantalla([x, y, z]) {
        if (!cur) return null;
        colocarCamara();
        const v = new THREE.Vector3(x, cur.nivel.z + z, -y).project(st.camera), r = (engine.renderer?.domElement || stage).getBoundingClientRect();
        return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height, delante: v.z < 1 };
      },
      unidadVista(id) { const n = cur?.unidades.find((q) => String(q.id) === String(id)), d = cur?.dims.get(String(id)); return n && d ? { x: n.x, y: n.y, z: n.z, rot: n.rot, dim: d.dim } : null; },
      seleccionarEn: (clientX, clientY) => seleccionar({ clientX, clientY, centro: false }),
      // punto de la unidad que «Ir a» dejó a la vista (x, y, z sobre el piso del nivel) y si el rayo de los ojos lo toca
      objetivo: () => ultimoObjetivo,
      // qué toca primero un rayo desde los ojos en (x, y) hacia el punto (x, y, z sobre el piso del nivel)
      rayo([px, py], [tx, ty, tz]) {
        if (!cur) return null;
        const o = new THREE.Vector3(px, cur.nivel.z + sueloEn(px, py) + OJOS, -py), c = new THREE.Vector3(tx, cur.nivel.z + tz, -ty), L = o.distanceTo(c);
        const r = new THREE.Raycaster(o, c.clone().sub(o).normalize(), 0, L + 0.6);
        const m = r.intersectObjects([cur.planta.mallaMuros], false)[0], u = cur.capa?.pick(r);
        return { L, muro: m ? [m.distance, m.point.toArray()] : null, unidad: u ? [u.unidad, u.distancia] : null, elegido: elegido(r) };
      },
      pasos: () => cur?.pasos || [],
      // celda de la rejilla en (x, y): código (0 libre, 1 bloqueada, 2 escalera), recinto y superficies que la cubren
      sondeo(x, y) {
        if (!cur) return null;
        const k = celda(x, y);
        return { codigo: k < 0 ? null : cur.rejilla.datos[k], crudo: k < 0 ? null : cur.rejilla.crudo[k], recinto: cur.planta.recintoEn(x, y), h: w.h,
          superficies: cur.superficies.filter((q) => x >= q.rect[0] && x <= q.rect[2] && y >= q.rect[1] && y <= q.rect[3]).map((q) => ({ tipo: q.p.tipo, dz: q.dz, z: +(q.dz + cotaParte(q.p, x, y)).toFixed(3) })) };
      },
      // gira la mirada sin moverse (para los guiones de QA)
      girar(rumbo, pitch = null) { w.yaw = rad(rumbo); if (pitch != null) w.pitch = rad(pitch); forzar = true; st.invalidate(); },
      etiquetas: () => etiquetas.filter((o) => o.visible).map((o) => o.element.textContent),
    };
  }
  return api;
}
