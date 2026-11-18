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
// * Los controles de adentro de cada modo (los deslizadores, las opciones y los botones del simulador sísmico, los
//   niveles y las capas del recorrido, las herramientas del modelo BIM…) se accionan con simular(control, valor), también
//   como los acciona una persona (ver «Simulaciones» abajo).
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

// ---------------------------------------------------------------- Simulaciones
// Qué se puede accionar lo dice el catálogo (data/propuesta/simulaciones.json: por inmersión, cada control con su id, su
// nombre, su tipo —accion, numero, opcion o si_no— y sus rangos u opciones), que scripts/build_propuesta.py revisa y copia
// como `controles` a cada inmersión de `tecnica.inmersiones` en data/propuesta.json. Dónde está cada control en la página
// y cómo lo acciona una persona lo dice ACCIONADORES, por vista y modo del atlas («torre:sismo»): el escenario busca el
// control dentro de los contenedores del modo (`en`), así un modo que no está a la vista no tiene controles (los modos
// nuevos vacían o esconden los suyos al salir). Cómo se acciona cada uno (`como`):
//   rango        <input type=range|number>: pone el valor y avisa «input» y «change», como al soltar el deslizador;
//                con `fraccion`, el valor va de 0 a 100 % del recorrido del deslizador (el de los pasos calculados)
//   lista        <select>: elige la opción y avisa «input» y «change»
//   radio        grupo de radios por su name: pulsa el radio de la opción
//   botones      botones excluyentes (`sel`, con la opción en data-`dato`): pulsa el de la opción si no está elegido
//   boton        pulsa el botón; con `antes`, si el botón no está pero `antes` sí (Calcular mientras otro cálculo
//                corre), pulsa primero `antes` (Cancelar), como haría la persona
//   alternar     botón que se prende y se apaga (aria-pressed o `activo(el)`): lo pulsa si no está como se pide
//   casilla      <input type=checkbox>: lo pulsa si no está como se pide
//   desplegable  <details>: lo abre o lo cierra
//   propio       lo que la escena registró con registrarControl (un piso de «Pisos por servicio» se elige tocándolo en
//                el 3D: no hay un control en la página que pulsar)
// `valores` traduce el id de la opción del catálogo al valor de la página; `pestana`, un botón que la persona pulsa antes
// (la pestaña del panel BIM donde está el control); `espera: false`, un control que no se espera si no está (Cancelar
// sin un cálculo en curso); `libre`, un elemento que mientras está a la vista el control se espera (Reproducir y el instante
// esperan a que termine el cálculo en curso: con el resultado anterior todavía en pantalla, accionarlos no dejaría nada
// del nuevo, que al llegar arranca solo desde el comienzo). Por modo, `listo`: un elemento que marca que el modo ya se
// puede manejar (el modelo BIM cargado; antes sus botones están pero no hacen nada). Un control que no está todavía (el
// modo carga) o que está deshabilitado se espera hasta ESPERA_CONTROL_MS; si mientras tanto llega otra orden ir(), se
// abandona. Salvo `sinResultado`: un control que necesita un cálculo terminado (Reproducir y el instante, deshabilitados
// hasta el primero) no espera en silencio si no hay ningún cálculo en curso y el botón que calcula (`calcula` del modo)
// está a la vista: con 'calcular' (Reproducir), sí lo pulsa antes y el resultado se reproduce solo al llegar (no lo pausa:
// no hay nada que se mueva); con 'error' (el instante), responde enseguida que hace falta calcular.
// build_propuesta.py lee esta tabla (las claves «'vista:modo': {» y las de sus controles) para revisar el catálogo.
const ESPERA_CONTROL_MS = 25000;
const panel = (m) => [`#v-torre [data-slot="torre.panel.${m}"]`, `#v-torre [data-slot="torre.hud.${m}"]`];
const RECORRIDO = {
  en: panel('recorrido'),
  controles: {
    nivel: { como: 'botones', sel: '[data-nivel]', dato: 'nivel', valores: { ext: 'EXT', p1: 'P1', p2: 'P2', p3: 'P3', p4: 'P4', bt: 'BT', cub: 'CUB' } },
    laboratorio: { como: 'boton', sel: '[data-entrada="P2:laboratorio"]' },
    subir: { como: 'boton', sel: '[data-acc="subir"]' },
    bajar: { como: 'boton', sel: '[data-acc="bajar"]' },
    mapa: { como: 'alternar', sel: '[data-acc="mapa"]' },
    espectador: { como: 'alternar', sel: '[data-acc="espectador"]' },
    faltantes: { como: 'alternar', sel: '[data-capa="faltantes"]' },
    cumplimiento: { como: 'alternar', sel: '[data-capa="estado"]' },
    contraste: { como: 'alternar', sel: '[data-capa="contraste"]', espera: false },
    infraestructura: { como: 'alternar', sel: '[data-capa="infraestructura"]' },
  },
};
const conClase = (k) => (el) => el.classList.contains(k);
const MODO_DISC = { ver: 'normal', ocultar: 'oculta' };
const ACCIONADORES = {
  'torre:torre': {
    en: ['#v-torre [data-slot="torre.capas"]'],
    controles: {
      proyecto_tipo: { como: 'alternar', sel: '[data-capa-torre="tipo"]' },
    },
  },
  'torre:pisos': {
    en: ['#v-torre'],
    controles: {
      piso: { como: 'propio' },
    },
  },
  'torre:recorrido': RECORRIDO,
  'torre:laboratorio': RECORRIDO,
  'torre:sismo': {
    en: [...panel('sismo')],
    calcula: { sel: '[data-s="calcular"]', control: 'calcular' },
    controles: {
      calcular: { como: 'boton', sel: '[data-s="calcular"]', antes: '[data-s="cancelar"]' },
      cancelar: { como: 'boton', sel: '[data-s="cancelar"]', espera: false },
      reproducir: { como: 'alternar', sel: '[data-s="play"]', libre: '[data-s="cancelar"]', sinResultado: 'calcular' },
      magnitud: { como: 'rango', sel: '[data-c="Mw"]' },
      escenario: { como: 'lista', sel: '[data-c="escenario"]' },
      profundidad: { como: 'rango', sel: '[data-c="h"]' },
      distancia: { como: 'rango', sel: '[data-c="d"]' },
      tipo_sismo: { como: 'lista', sel: '[data-c="regimen"]' },
      suelo: { como: 'rango', sel: '[data-c="vs30"]' },
      escala: { como: 'radio', nombre: 'sismo-escala', valores: { fisica: '1' } },
      instante: { como: 'rango', sel: '[data-c="t"]', fraccion: true, libre: '[data-s="cancelar"]', sinResultado: 'error' },
      velocidad: { como: 'botones', sel: '[data-vel]', dato: 'vel', valores: { lenta: '0.25', real: '1' } },
      exageracion: { como: 'lista', sel: '[data-c="exag"]' },
      colorear: { como: 'botones', sel: '[data-campo]', dato: 'campo' },
      leyenda: { como: 'desplegable', sel: '.sismo-ley' },
      equipos: { como: 'lista', sel: '[data-c="piso-eq"]', valores: { ninguno: '', bt: 'BT', cub: 'CUB' } },
      muros: { como: 'radio', nombre: 'sismo-muros' },
      histeresis: { como: 'radio', nombre: 'sismo-histeresis' },
      direccion: { como: 'rango', sel: '[data-c="ang"]' },
      semilla: { como: 'rango', sel: '[data-c="semilla"]' },
      calidad: { como: 'radio', nombre: 'sismo-calidad' },
    },
  },
  'torre:bim': {
    en: [...panel('bim')],
    // el panel y sus pestañas aparecen antes que el modelo 3D, y sin él sus botones no hacen nada: bim.js lo marca al
    // terminar de cargar el modelo
    listo: '[data-bim-listo]',
    controles: {
      herramienta: { como: 'botones', sel: '.bim-pestanas button', dato: 'p' },
      vista: { como: 'botones', sel: '.bim-vistas button', dato: 'v', pestana: 'modelo' },
      arquitectura: { como: 'botones', sel: 'li[data-d="ARQ"] .bim-modo button', dato: 'm', valores: MODO_DISC, pestana: 'modelo' },
      estructura: { como: 'botones', sel: 'li[data-d="EST"] .bim-modo button', dato: 'm', valores: MODO_DISC, pestana: 'modelo' },
      cimentacion: { como: 'botones', sel: 'li[data-d="CIM"] .bim-modo button', dato: 'm', valores: MODO_DISC, pestana: 'modelo' },
      equipamiento_fijo: { como: 'botones', sel: 'li[data-d="FIJO"] .bim-modo button', dato: 'm', valores: MODO_DISC, pestana: 'modelo' },
      dotacion: { como: 'botones', sel: 'li[data-d="DOT"] .bim-modo button', dato: 'm', valores: MODO_DISC, pestana: 'modelo' },
      espacios: { como: 'casilla', sel: '[data-b="espacios"]', pestana: 'modelo' },
      mostrar_todo: { como: 'boton', sel: '[data-b="todo"]', pestana: 'modelo' },
      corte: { como: 'botones', sel: '[data-cn]', dato: 'cn', valores: { cim: 'CIM', p1: 'P1', p2: 'P2', p3: 'P3', p4: 'P4', cub: 'CUB' }, pestana: 'cortes' },
      quitar_corte: { como: 'boton', sel: '[data-b="sincorte"]', pestana: 'cortes', espera: false },
      ver_cimentacion: { como: 'alternar', sel: '[data-b="cim"]', activo: conClase('ghost'), pestana: 'cimentacion' },
      terreno: { como: 'botones', sel: '[data-t]', dato: 't', pestana: 'cimentacion' },
      construir: { como: 'alternar', sel: '[data-b="play4d"]', activo: (el) => el.textContent.trim() === 'Pausa', pestana: '4d' },
      fecha_obra: { como: 'rango', sel: '[data-b="r4d"]', fraccion: true, pestana: '4d' },
      colorear_sismo: { como: 'botones', sel: '[data-pest="comportamiento"] [data-c]', dato: 'c', pestana: 'comportamiento', espera: false },
      leyenda: { como: 'desplegable', sel: '[data-b="ley"]', espera: false },
    },
  },
};

// controles que una escena acciona por su cuenta (como: 'propio'): «vista:modo:control» → { listo(), hacer(valor) }
const propios = new Map();
/** Una escena registra un control sin botón en la página (p. ej. tocar un piso en el 3D). Fuera del escenario no hace nada.
 * listo() dice si ya se puede accionar (si no, se espera); hacer(valor) devuelve true o el texto del error. */
export function registrarControl(vista, modo, control, { listo, hacer }) {
  if (ESCENARIO) propios.set(`${vista}:${modo}:${control}`, { listo, hacer });
}

// el catálogo llega con data/propuesta.json (la presentación que enmarca el atlas ya lo leyó: viene de la caché)
let catalogo = null;   // [{ id, vista, modo, nombre, controles }]
let pedidoCatalogo = null;
const leerCatalogo = () => (pedidoCatalogo ??= fetch(new URL('../data/propuesta.json', import.meta.url))
  .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
  .then((d) => { catalogo = (d?.tecnica?.inmersiones || []).filter((i) => i && i.vista && i.modo); return catalogo; })
  .catch((e) => { console.warn('escenario: no se pudo leer el catálogo de controles', e); pedidoCatalogo = null; return null; }));

// la vista y el modo a la vista: la sección que se ve y el botón de modo que está oprimido
function aLaVista() {
  const sec = document.querySelector('section.view:not([hidden])');
  const vista = sec?.id?.replace(/^v-/, '');
  if (!vista || !(vista in BOTON)) return null;
  const b = sec.querySelector(`button[data-${BOTON[vista].replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}][aria-pressed="true"]`);
  const modo = b?.dataset[BOTON[vista]];
  return modo ? { vista, modo, clave: `${vista}:${modo}` } : null;
}
const inmersionDe = (v) => (v && catalogo ? catalogo.find((i) => i.vista === v.vista && i.modo === v.modo) || null : null);
const nombreModo = (v, inm) => (inm?.nombre ? `«${inm.nombre}»` : v ? `el modo «${v.modo}» de la vista «${v.vista}»` : 'el atlas');

// los contenedores del modo que están a la vista: un modo nuevo los muestra al entrar (con sus controles ya armados y el
// modo en su sitio, p. ej. el recorrido en la puerta del laboratorio), así que antes no se acciona nada
const raices = (ac) => [...document.querySelectorAll(ac.en.join(','))].filter((r) => !r.hidden);
// el elemento de la página de un control, dentro de los contenedores de su modo
function buscar(ac, sel) {
  for (const raiz of raices(ac)) {
    const el = raiz.matches(sel) ? raiz : raiz.querySelector(sel);
    if (el) return el;
  }
  return null;
}
const usable = (el) => !!el && el.isConnected && !el.disabled && !el.hidden;
const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
const plano = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
const fmt = (v) => String(v).replace('.', ',');

// valida el valor contra el tipo y el rango del catálogo; devuelve { v } (el valor ya normalizado) o { error }. La
// maqueta de la presentación (js/propuesta/simulacion.js) usa esta misma regla para sus controles
export function validar(c, valor) {
  const nombre = `«${c.nombre || c.id}»`;
  if (c.tipo === 'accion') return valor == null ? { v: null } : { error: `${nombre} es una acción: va sin valor` };
  if (c.tipo === 'si_no') return typeof valor === 'boolean' ? { v: valor } : { error: `${nombre} pide sí o no (true o false)` };
  if (c.tipo === 'numero') {
    const v = typeof valor === 'number' ? valor : typeof valor === 'string' && valor.trim() !== '' ? Number(valor.replace(',', '.')) : NaN;
    const unidad = c.unidad ? ` ${c.unidad}` : '';
    if (!Number.isFinite(v)) return { error: `${nombre} pide un número entre ${fmt(c.min)} y ${fmt(c.max)}${unidad}` };
    if ((c.min != null && v < c.min) || (c.max != null && v > c.max)) return { error: `${nombre} va de ${fmt(c.min)} a ${fmt(c.max)}${unidad}; ${fmt(v)} queda fuera` };
    if (!(c.paso > 0)) return { v };
    // al paso del control, como lo deja el deslizador (sin el ruido de la coma flotante)
    const dec = (String(c.paso).split('.')[1] || '').length, base = c.min ?? 0;
    return { v: Number((base + Math.round((v - base) / c.paso) * c.paso).toFixed(dec)) };
  }
  if (c.tipo === 'opcion') {
    const k = plano(valor), o = (c.opciones || []).find((x) => plano(x.id) === k) || (c.opciones || []).find((x) => plano(x.nombre) === k);
    return o ? { v: o.id } : { error: `${nombre} no tiene la opción «${valor}»; tiene ${(c.opciones || []).map((x) => x.id).join(', ')}` };
  }
  return { error: `${nombre} tiene un tipo que el atlas no conoce (${c.tipo})` };
}

// el elemento que hay que tocar para el valor pedido (null si todavía no está o no se puede usar)
function objetivo(ac, a, v, clave, id) {
  if (a.libre && usable(buscar(ac, a.libre))) return null;   // un cálculo en curso: se espera su resultado
  const dom = a.valores?.[v] ?? v;
  switch (a.como) {
    case 'radio': {
      const r = buscar(ac, `input[type="radio"][name="${a.nombre}"][value="${CSS.escape(String(dom))}"]`);
      return usable(r) ? r : null;
    }
    case 'botones': {
      const b = raices(ac).flatMap((raiz) => [...raiz.querySelectorAll(a.sel)]).find((x) => x.dataset[a.dato] === String(dom));
      return usable(b) ? b : null;
    }
    case 'propio': {
      const p = propios.get(`${clave}:${id}`);
      return p && p.listo() ? p : null;
    }
    default: {
      const el = buscar(ac, a.sel);
      if (a.como === 'boton' && !usable(el) && a.antes && usable(buscar(ac, a.antes))) return buscar(ac, a.antes);
      return usable(el) ? el : null;
    }
  }
}
const avisar = (el, ...tipos) => tipos.forEach((t) => el.dispatchEvent(new Event(t, { bubbles: true })));
// Sin un resultado calculado (`sinResultado`): el control está pero deshabilitado, no hay un cálculo en curso (`libre` no
// está a la vista) y el botón que calcula sí. Entonces no hay nada que esperar: antes se esperaba ESPERA_CONTROL_MS en
// silencio y la presentación lo daba por hecho
const SIN_RESULTADO = Symbol('sin resultado');
function faltaResultado(ac, a) {
  if (!a.sinResultado || !ac.calcula) return null;
  const el = buscar(ac, a.sel);
  if (!el || !el.isConnected || el.hidden || !el.disabled) return null;
  return !(a.libre && usable(buscar(ac, a.libre))) && usable(buscar(ac, ac.calcula.sel)) ? SIN_RESULTADO : null;
}
async function sinResultado(ac, a, c, v, inm, mio) {
  const calc = (inm?.controles || []).find((x) => x.id === ac.calcula.control);
  const nombreCalc = `«${calc?.nombre || ac.calcula.control}»`;
  if (a.sinResultado !== 'calcular') return `«${c.nombre}» necesita un cálculo terminado: accione antes ${nombreCalc}`;
  if (v === false) return true;   // pausar: no hay nada que se mueva
  const b = buscar(ac, ac.calcula.sel);
  if (!usable(b)) return `«${c.nombre}» necesita un cálculo terminado y ${nombreCalc} no está disponible`;
  b.click();
  // arrancó (el cálculo en curso a la vista) o ya terminó (el control quedó habilitado): el resultado se reproduce solo
  if (await hasta(() => usable(buscar(ac, a.libre)) || usable(buscar(ac, a.sel)), 1500, mio)) return true;
  if (mio !== turno) return `Se cambió de modelo antes de accionar «${c.nombre}»`;
  return `«${c.nombre}» necesita un cálculo terminado y ${nombreCalc} no arrancó`;
}

// acciona el control como la persona; devuelve true o el texto del error
async function accionar(ac, a, c, v, el, clave) {
  const dom = a.valores?.[v] ?? v;
  switch (a.como) {
    case 'rango': {
      let x = v;
      if (a.fraccion) x = Math.round(+el.min + (v / 100) * (+el.max - +el.min));
      else if ((el.min !== '' && x < +el.min) || (el.max !== '' && x > +el.max)) return `«${c.nombre}» va de ${fmt(el.min)} a ${fmt(el.max)} en la página; ${fmt(x)} queda fuera`;
      el.value = String(x);
      avisar(el, 'input', 'change');
      return true;
    }
    case 'lista': {
      if (![...el.options].some((o) => o.value === String(dom))) return `«${c.nombre}» no ofrece ahora la opción «${v}»`;
      if (el.value !== String(dom)) { el.value = String(dom); avisar(el, 'input', 'change'); }
      return true;
    }
    case 'radio': if (!el.checked) el.click(); return true;
    case 'botones': if (el.getAttribute('aria-pressed') !== 'true') el.click(); return true;
    case 'boton':
      el.click();
      // «antes» (Cancelar) acaba de pulsarse: ahora sí aparece el botón pedido
      if (el.matches(a.antes || ':not(*)')) {
        const b = await hasta(() => { const x = buscar(ac, a.sel); return usable(x) ? x : null; }, 3000);
        if (!b) return `«${c.nombre}» no volvió a estar disponible`;
        b.click();
      }
      return true;
    case 'alternar': {
      const on = a.activo ? a.activo(el) : el.getAttribute('aria-pressed') === 'true';
      if (on !== v) el.click();
      return true;
    }
    case 'casilla': if (el.checked !== v) el.click(); return true;
    case 'desplegable': el.open = v; return true;
    case 'propio': {
      const r = await el.hacer(dom);
      return r === true || r === undefined ? true : String(r);
    }
    default: return `el atlas no sabe accionar «${c.nombre}»`;
  }
}

// sube con cada ir() que cambia de vista o de modo: un control que se está esperando se abandona (la presentación repite
// ir() con el mismo modelo en cada paso, y eso no debe cortar una espera)
let turno = 0, pedido = '';
// espera a que f() devuelva algo (cada 120 ms, hasta ms), o null si se acaba el tiempo o llegó otra orden ir()
async function hasta(f, ms, mio = turno) {
  const t0 = performance.now();
  for (;;) {
    const r = f();
    if (r) return r;
    if (mio !== turno || performance.now() - t0 > ms) return null;
    await espera(120);
  }
}

// `mio`: el turno cuando se pidió (una orden ir() a otro modelo pedida después la deja sin efecto si todavía espera)
async function simularUno(control, valor, mio) {
  if (!(await leerCatalogo())) return 'El atlas no pudo leer el catálogo de controles (data/propuesta.json)';
  const v0 = aLaVista(), inm = inmersionDe(v0);
  const c = (inm?.controles || []).find((x) => x.id === control);
  if (!c) {
    const hay = (inm?.controles || []).map((x) => x.id);
    return `${nombreModo(v0, inm)} no tiene el control «${control}»${hay.length ? `; tiene ${hay.join(', ')}` : ' (no tiene controles)'}`;
  }
  const ac = ACCIONADORES[v0.clave], a = ac?.controles?.[control];
  if (!a) return `El atlas no sabe accionar «${c.nombre}» en ${nombreModo(v0, inm)}`;
  // sigue a la vista el mismo modo (el laboratorio pasa por el recorrido mientras carga: es la misma tabla)
  const mismo = () => ACCIONADORES[aLaVista()?.clave] === ac;
  const val = validar(c, valor);
  if (val.error) return val.error;
  // el modo, ya manejable (el modelo BIM cargado): antes ni la pestaña ni el control harían nada
  if (ac.listo && !(await hasta(() => mismo() && buscar(ac, ac.listo), ESPERA_CONTROL_MS, mio))) {
    if (mio !== turno || !mismo()) return `Se cambió de modelo antes de accionar «${c.nombre}»`;
    return `«${c.nombre}» no está disponible: ${nombreModo(v0, inm)} no terminó de cargar`;
  }
  // la pestaña del panel donde está el control, como la abre la persona
  if (a.pestana) {
    const p = await hasta(() => { const x = buscar(ac, `.bim-pestanas button[data-p="${a.pestana}"]`); return usable(x) ? x : null; }, ESPERA_CONTROL_MS, mio);
    if (!p) return mio !== turno ? `Se cambió de modelo antes de accionar «${c.nombre}»` : `«${c.nombre}» no está disponible: el panel no tiene la pestaña «${a.pestana}»`;
    if (p.getAttribute('aria-selected') !== 'true') { p.click(); await espera(0); }
  }
  const el = await hasta(() => (mismo() ? objetivo(ac, a, val.v, v0.clave, control) || faltaResultado(ac, a) : null), a.espera === false ? 0 : ESPERA_CONTROL_MS, mio);
  if (el === SIN_RESULTADO) return sinResultado(ac, a, c, val.v, inm, mio);
  if (!el) {
    if (mio !== turno || !mismo()) return `Se cambió de modelo antes de accionar «${c.nombre}»`;
    if (a.libre && usable(buscar(ac, a.libre))) return `«${c.nombre}» esperó a que terminara el cálculo en curso, y no terminó a tiempo`;
    return `«${c.nombre}» no está disponible ahora en ${nombreModo(v0, inm)}${a.espera === false ? '' : ' (no apareció o siguió deshabilitado)'}`;
  }
  return accionar(ac, a, c, val.v, el, v0.clave);
}

if (ESCENARIO) {
  document.documentElement.dataset.escenario = '';
  leerCatalogo();
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
      if (vista && `${vista}:${modo || ''}` !== pedido) { turno++; pedido = `${vista}:${modo || ''}`; }
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
    /** Acciona un control del modo a la vista como lo haría la persona (`valor` según su tipo; sin valor una acción).
     * Se encadena detrás de las órdenes anteriores. Nunca lanza: devuelve true o el texto de lo que no se pudo. */
    simular(control, valor) {
      const mio = turno;
      const paso = cadena.then(() => simularUno(String(control ?? ''), valor, mio)).catch((e) => `El atlas no pudo accionar «${control}»: ${e?.message || e}`);
      cadena = paso.then(() => {}, () => {});
      return paso;
    },
    /** Los controles del catálogo para la vista y el modo a la vista ([] si no tiene, o mientras llega el catálogo). */
    controles() {
      const inm = inmersionDe(aLaVista());
      return inm?.controles ? JSON.parse(JSON.stringify(inm.controles)) : [];
    },
    tema(t) { if (t === 'claro' || t === 'oscuro') document.documentElement.dataset.theme = t === 'claro' ? 'light' : 'dark'; },
    listo: () => true,
  });
}
