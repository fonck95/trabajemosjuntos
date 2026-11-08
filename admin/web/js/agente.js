// El asistente del panel (docs/agente.md): un botón flotante que abre una conversación con el modelo. Las respuestas
// llegan en flujo (NDJSON, `flujo` de api.js) y se pintan por partes; lo que escribe en la base espera la aprobación de
// la persona en una tarjeta; las acciones que pide el servidor (navegar, recargar, insignias, mapa) se validan aquí
// antes de hacerse. Vive en document.body, fuera de #raiz y de #vista: sobrevive a cada cambio de vista.
//
// Seguridad: nada de lo que escribe el modelo se pinta como HTML. Entra con textContent o como nodos de texto, y el
// Markdown se convierte a nodos con una lista cerrada de elementos (lo demás, también «<img …>», queda como texto). Los
// enlaces solo van a rutas del panel (las de RUTAS en app.js que el rol puede abrir) o, en otra pestaña, al origen https
// de Mnemo que da /api/agente/estado. Las plantillas `html` de este archivo solo llevan íconos de la tabla fija de ui.js.
import { api, ErrorApi, FLUJO_CORTADO, flujo, hayCambiosSinGuardar, registrarPendiente, sesion } from './api.js';
import { accionesMapa, estadoMapa, mapaListo } from './agente-mapa.js';
import { sinBase, url } from './base.js';
import { confirmar as preguntar, esMovil, fecha, html, icono, montar, num } from './ui.js';

const GUARDADO = 'yj_agente';             // sessionStorage: {abierto, conversacion, uid}; se borra en olvidar() de app.js
const MAX_TEXTO = 4000;                   // el tope de MensajeIn.texto en la API
const VIGENCIA_ESTADO_MS = 5 * 60 * 1000; // el estado (disponible, tope de mensajes) se vuelve a pedir al cambiar de vista
const REINTENTO_ESTADO_MS = 30 * 1000;    // si no se pudo leer, no se insiste en cada vista
const ESTADOS = new Set(['inicio', 'ok', 'error', 'pendiente', 'aprobada', 'rechazada']);
// Errores del turno que no se arreglan repitiendo el mismo mensaje. Los de Mnemo como modelo: la conexión se cayó, el
// plan no incluye el chat, no quedan créditos o la cuenta no tiene un modelo que sirva; `llm_peticion`, el proveedor
// rechazó la petición; `proveedor`, la conversación es de un proveedor del modelo que ya no está
const SIN_REINTENTO = new Set(['volumen', 'borrada', 'sin_pendientes', 'permiso', 'larga', 'agente_apagado', 'sin_configurar',
  'no_existe', 'proveedor', 'mnemo_conexion', 'mnemo_plan', 'mnemo_creditos', 'mnemo_sin_modelo', 'llm_peticion']);
// Errores tras los que esta conversación ya no sirve: se ofrece «Nueva conversación»
const CON_NUEVA = new Set(['larga', 'no_existe', 'borrada', 'proveedor', 'llm_peticion']);
// Errores tras los que cambió el estado del asistente (el rol apagado, sin proveedor del modelo, la conexión con Mnemo
// caída): se vuelve a leer, y al administrador se le explica qué hacer
const RELEER_ESTADO = new Set(['agente_apagado', 'sin_configurar', 'mnemo_conexion']);
// Las claves de la dirección que viajan al modelo como filtros de la vista: las de Habitantes y el mapa (`Filtros` de
// api/filtros.py) y el estado de algunas vistas (orden y página del directorio, pestaña de Calidad, la persona de «Mi
// trabajo», el periodo de Usuarios). Ninguna otra: la vuelta de Mnemo a Ajustes trae en la dirección `code`, `state`
// e `iss` (o `error`), y una clave desconocida tampoco es asunto del modelo
const CLAVES_CONTEXTO = new Set(['q', 'zona', 'lugar_id', 'fuente', 'lista', 'etiqueta', 'con_cedula', 'con_telefono',
  'precision', 'reunion_id', 'asistio', 'consentimiento', 'lider', 'sexo', 'completitud_max', 'ids', 'edad_min', 'edad_max',
  'tipo_documento', 'cedula_verificada', 'puesto_id', 'con_puesto', 'con_mesa', 'votacion_estado', 'donde', 'abordado',
  'contactado', 'abordaje_estado', 'ultimo_resultado', 'sin_acercamiento_dias', 'proximo_vencido', 'canal_autorizado',
  'situacion', 'creado_por', 'actualizado_por', 'menor', 'requiere_actualizacion', 'varios_telefonos', 'telefono_estado',
  'estado_civil', 'nivel_educativo', 'situacion_laboral', 'estrato', 'tenencia_vivienda', 'regimen_salud', 'tratables',
  'mios', 'poligono', 'area_id',
  ...['cedula', 'telefono', 'sexo', 'edad', 'lugar', 'puesto', 'mesa', 'direccion', 'puesto_mesa'].map((c) => `sin_${c}`),
  'ids_total', 'orden', 'pagina', 'p', 'uid', 'desde', 'hasta', 'por', 'agrupar']);
const MAX_FILTROS = 30;
const MAX_TEXTO_RONDA = 100000;           // `texto_ronda`: el texto final de una ronda (como en una conversación guardada)
// Por qué se cayó la conexión con Mnemo (`mnemo.conexion.motivo` del estado)
const CAIDA_MNEMO = {
  revocada: 'Mnemo ya no la acepta: se revocó en Mnemo, venció por no usarse o la cuenta se desactivó.',
  clave: 'Cambió la clave del administrador del panel y la conexión guardada ya no se puede leer.',
  error: 'Mnemo respondió algo inesperado al renovarla.',
};

// ───────── Utilidades ─────────

/** Un texto de una fuente externa (el servidor, el modelo): solo cadenas, recortadas a `max`. */
const texto = (v, max = 4000) => (typeof v === 'string' ? v.slice(0, max) : '');
const entero = (v) => (Number.isInteger(v) && v >= 0 ? v : null);
const rutaActual = () => sinBase(location.pathname).replace(/\/+$/, '') || '/';

function el(etiqueta, clase, contenido) {
  const e = document.createElement(etiqueta);
  if (clase) e.className = clase;
  if (contenido != null) e.textContent = contenido;
  return e;
}

// Los íconos salen de la tabla fija de ui.js: se arman una vez y se clonan
const plantillas = new Map();
function ico(nombre) {
  let t = plantillas.get(nombre);
  if (!t) {
    t = document.createElement('template');
    t.innerHTML = String(html`${icono(nombre)}`);
    plantillas.set(nombre, t);
  }
  return t.content.firstElementChild.cloneNode(true);
}

let estilos = null;
// Como zona.js: la hoja se pide al montar y el botón aparece cuando cargó (sin un destello sin estilos)
function cargarEstilos() {
  estilos ||= new Promise((listo) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = new URL('../css/agente.css', import.meta.url).href;
    l.dataset.agente = '';
    l.onload = l.onerror = () => listo();
    document.head.append(l);
  });
  return estilos;
}

// ───────── Enlaces permitidos ─────────

/** Adónde puede llevar un enlace del asistente: `{tipo: 'interno', ruta}` (una ruta del panel que el rol abre, con su
 * consulta), `{tipo: 'mnemo', href}` (https del origen de Mnemo) o null (queda como texto). `rutaPanel(ruta)` es la
 * de app.js: `{nav, permitida}` o null. */
export function destinoEnlace(destino, { origenMnemo = null, rutaPanel = () => null,
  origen = globalThis.location?.origin } = {}) {
  if (typeof destino !== 'string' || !origen) return null;
  const d = destino.trim();
  // Sin espacios, controles ni barras invertidas: los navegadores «arreglan» esas direcciones de formas distintas
  if (!d || d.length > 2048 || /[\u0000- \u007f\\]/.test(d)) return null;
  let u;
  try { u = new URL(d, origen); } catch { return null; }
  if (u.username || u.password) return null;
  const interna = (d.startsWith('/') && !d.startsWith('//')) || /^https?:\/\//i.test(d);
  if (interna && u.origin === origen) {
    const ruta = sinBase(u.pathname).replace(/\/+$/, '') || '/';
    if (!rutaPanel(ruta)?.permitida || u.search.length > 600) return null;
    return { tipo: 'interno', ruta: ruta + u.search };
  }
  if (origenMnemo && u.protocol === 'https:' && u.origin === origenMnemo) return { tipo: 'mnemo', href: u.href };
  return null;
}

/** Los filtros de la vista que van en el contexto de cada mensaje: de `consulta` (un `location.search`), solo las
 * claves conocidas (CLAVES_CONTEXTO), la primera vez que aparece cada una, con el valor recortado a 200 caracteres y
 * como mucho 30. Nunca lo que trae la vuelta de Mnemo (`code`, `state`, `iss`, `error`, `error_description`). */
export function filtrosDe(consulta) {
  const filtros = {};
  let n = 0;
  for (const [k, v] of new URLSearchParams(typeof consulta === 'string' ? consulta : '')) {
    if (n >= MAX_FILTROS) break;
    if (CLAVES_CONTEXTO.has(k) && !Object.hasOwn(filtros, k)) { filtros[k] = v.slice(0, 200); n++; }
  }
  return filtros;
}

/** El origen de Mnemo que da el estado, solo si es `https://host[:puerto]` (si no, ningún enlace sale del panel). */
function origenSeguro(o) {
  if (typeof o !== 'string') return null;
  try {
    const u = new URL(o);
    return u.protocol === 'https:' && u.origin === o.replace(/\/+$/, '') ? u.origin : null;
  } catch { return null; }
}

function crearEnlace(d) {
  const a = document.createElement('a');
  if (d.tipo === 'interno') {
    a.href = url(d.ruta);
    a.dataset.ruta = ''; // lo atiende el escucha de clics de app.js: navega sin recargar
  } else {
    a.href = d.href;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.referrerPolicy = 'no-referrer';
    a.title = 'Se abre en Mnemo, en otra pestaña';
  }
  return a;
}

// ───────── Markdown mínimo a nodos ─────────
// Bloques: párrafos, títulos, listas (con un nivel de anidación), citas, código, tablas simples y reglas. En línea:
// negrita, cursiva, tachado, código y enlaces. Lo que no es esto queda como texto.

const RE_VALLA = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const RE_TITULO = /^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/;
const RE_REGLA = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const RE_ITEM = /^([ \t]*)([-*+]|\d{1,3}[.)])[ \t]+(.*)$/;
const RE_CITA = /^ {0,3}>[ \t]?(.*)$/;
const RE_SEPARADOR = /^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;
const MAX_FILAS = 300;
const MAX_COLUMNAS = 12;

const sangria = (s) => s.replace(/\t/g, '    ').match(/^ */)[0].length;
const esSeparador = (l) => l.includes('|') && l.includes('-') && RE_SEPARADOR.test(l);
const empiezaTabla = (lineas, i) => lineas[i].includes('|') && i + 1 < lineas.length && esSeparador(lineas[i + 1]);

function iniciaBloque(lineas, i) {
  const l = lineas[i];
  const item = RE_ITEM.exec(l);
  return RE_VALLA.test(l) || RE_TITULO.test(l) || RE_REGLA.test(l) || RE_CITA.test(l)
    || (item && sangria(item[1]) <= 3) || empiezaTabla(lineas, i);
}

/** Las celdas de una fila de tabla («| a | b |» → ['a', 'b']); «\|» es una barra dentro de la celda. */
function celdas(linea) {
  let s = linea.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
  const out = [];
  let actual = '';
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '\\' && s[i + 1] === '|') { actual += '|'; i++; continue; }
    if (s[i] === '|') { out.push(actual.trim()); actual = ''; continue; }
    actual += s[i];
  }
  out.push(actual.trim());
  return out;
}
const alineacion = (c) => (/^:-+:$/.test(c) ? 'centro' : /^-+:$/.test(c) ? 'der' : '');

function lista(lineas, i) {
  const m0 = RE_ITEM.exec(lineas[i]);
  const ordenada = /\d/.test(m0[2]);
  const base = sangria(m0[1]);
  const items = [];
  const anexar = (t) => {
    const ult = items[items.length - 1];
    if (ult.sub) ult.sub.items[ult.sub.items.length - 1] += '\n' + t;
    else ult.texto += '\n' + t;
  };
  while (i < lineas.length) {
    const l = lineas[i];
    if (!l.trim()) {
      // Una línea en blanco sigue la lista si lo que viene después es de ella (otro ítem, o texto con sangría)
      let j = i + 1;
      while (j < lineas.length && !lineas[j].trim()) j++;
      const mj = j < lineas.length ? RE_ITEM.exec(lineas[j]) : null;
      if (mj && sangria(mj[1]) <= base + 1 && /\d/.test(mj[2]) === ordenada) { i = j; continue; }
      if (j < lineas.length && items.length && sangria(lineas[j]) >= base + 2) { i = j; continue; }
      break;
    }
    const m = RE_ITEM.exec(l);
    if (m && sangria(m[1]) <= base + 1) {
      if (/\d/.test(m[2]) !== ordenada) break;
      items.push({ texto: m[3], sub: null });
      i++;
      continue;
    }
    if (m && items.length) {
      const ult = items[items.length - 1];
      ult.sub ||= { ordenada: /\d/.test(m[2]), items: [] };
      ult.sub.items.push(m[3]);
      i++;
      continue;
    }
    if (!items.length) break;
    // Texto con sangría, o una línea suelta justo después de un ítem: es parte de ese ítem
    if (sangria(l) >= base + 2 || !iniciaBloque(lineas, i)) { anexar(l.trim()); i++; continue; }
    break;
  }
  return { bloque: { tipo: 'lista', ordenada, inicio: ordenada ? parseInt(m0[2], 10) : 1, items }, i };
}

/** El texto en bloques de Markdown ([{tipo, …}]), sin tocar el DOM. Al pintar por partes, los bloques que no cambiaron
 * (todos menos el último, casi siempre) conservan sus nodos. */
export function partirBloques(entrada) {
  const lineas = String(entrada ?? '').replace(/\r\n?/g, '\n').split('\n');
  const bloques = [];
  let i = 0;
  while (i < lineas.length) {
    const l = lineas[i];
    let m;
    if (!l.trim()) { i++; continue; }
    if ((m = RE_VALLA.exec(l))) {
      const valla = m[1];
      const fin = new RegExp(`^ {0,3}${valla[0] === '`' ? '`' : '~'}{${valla.length},}[ \\t]*$`);
      const cuerpo = [];
      i++;
      while (i < lineas.length && !fin.test(lineas[i])) cuerpo.push(lineas[i++]);
      const cerrado = i < lineas.length;
      if (cerrado) i++;
      bloques.push({ tipo: 'codigo', texto: cuerpo.join('\n'), cerrado });
      continue;
    }
    if ((m = RE_TITULO.exec(l))) { bloques.push({ tipo: 'titulo', nivel: m[1].length, texto: m[2] }); i++; continue; }
    if (RE_REGLA.test(l)) { bloques.push({ tipo: 'regla' }); i++; continue; }
    if (empiezaTabla(lineas, i)) {
      const cab = celdas(l).slice(0, MAX_COLUMNAS);
      const alin = celdas(lineas[i + 1]).map(alineacion);
      const filas = [];
      i += 2;
      while (i < lineas.length && lineas[i].trim() && lineas[i].includes('|')) {
        if (filas.length < MAX_FILAS) filas.push(celdas(lineas[i]));
        i++;
      }
      bloques.push({ tipo: 'tabla', cab, alin, filas });
      continue;
    }
    if (RE_CITA.test(l)) {
      const cuerpo = [];
      while (i < lineas.length && (m = RE_CITA.exec(lineas[i]))) { cuerpo.push(m[1]); i++; }
      bloques.push({ tipo: 'cita', texto: cuerpo.join('\n') });
      continue;
    }
    if ((m = RE_ITEM.exec(l)) && sangria(m[1]) <= 3) {
      const r = lista(lineas, i);
      bloques.push(r.bloque);
      i = r.i;
      continue;
    }
    const cuerpo = [l.trim()];
    i++;
    while (i < lineas.length && lineas[i].trim() && !iniciaBloque(lineas, i)) cuerpo.push(lineas[i++].trim());
    bloques.push({ tipo: 'parrafo', texto: cuerpo.join('\n') });
  }
  return bloques;
}

const RE_CODIGO = /(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/y;
// La dirección admite un nivel de paréntesis, como CommonMark: «…/Yondó_(Antioquia)» (y «javascript:x(1)» se reconoce
// como enlace para descartarlo, en vez de quedar el Markdown a medias)
const RE_ENLACE = /\[((?:[^[\]\\\n]|\\.){1,400})\]\(\s*<?((?:[^\s<>()]|\([^\s<>()]*\)){1,2048})>?(?:\s+(?:"[^"\n]{0,300}"|'[^'\n]{0,300}'))?\s*\)/y;
const RE_AUTOENLACE = /<(https?:\/\/[^\s<>]{1,2048})>/y;
const RE_URL = /https?:\/\/[^\s<>()[\]{}"'`]{1,2048}/y;
const RE_ESCAPABLE = /[!-/:-@[-`{-~]/;
const LETRA = /[\p{L}\p{N}]/u;
const MAX_ANIDADO = 4;
const ALCANCE_ENFASIS = 4000; // un énfasis no se busca más allá: un texto con muchos «*» sueltos no se vuelve lento

/** Dónde cierra el énfasis que abre `marca` en `desde` (o -1): el cierre no va pegado a un espacio y, con «_», no está
 * dentro de una palabra (nombres_con_guiones no son cursiva). */
function cierre(t, marca, desde) {
  const tope = Math.min(t.length, desde + ALCANCE_ENFASIS);
  let j = desde + 1;
  for (;;) {
    j = t.indexOf(marca, j);
    if (j < 0 || j >= tope) return -1;
    const antes = t[j - 1];
    const despues = t[j + marca.length];
    const sencilla = marca.length === 1;
    const valido = antes && !/\s/.test(antes) && antes !== '\\'
      && (!sencilla || (antes !== marca && despues !== marca))
      && (marca[0] !== '_' || !despues || !LETRA.test(despues));
    if (valido) return j;
    j += 1;
  }
}

function enfasis(t, i, op, nivel) {
  const c = t[i];
  const doble = t[i + 1] === c;
  if (c === '~' && !doble) return null;
  const marca = doble ? c + c : c;
  const desde = i + marca.length;
  const sig = t[desde];
  if (!sig || /\s/.test(sig) || sig === c) return null;
  if (c === '_' && i > 0 && LETRA.test(t[i - 1])) return null;
  const j = cierre(t, marca, desde);
  if (j < 0) return null;
  const nodo = el(c === '~' ? 's' : doble ? 'strong' : 'em');
  enLinea(t.slice(desde, j), nodo, op, nivel + 1);
  return { nodo, fin: j + marca.length };
}

/** Pinta en `padre` el texto en línea: los nodos se crean uno por uno (nunca se interpreta HTML). */
function enLinea(t, padre, op, nivel = 0) {
  let suelto = '';
  const soltar = () => { if (suelto) { padre.append(suelto); suelto = ''; } };
  let i = 0;
  while (i < t.length) {
    const c = t[i];
    if (c === '\\' && i + 1 < t.length && RE_ESCAPABLE.test(t[i + 1])) { suelto += t[i + 1]; i += 2; continue; }
    if (c === '\n') { soltar(); padre.append(document.createElement('br')); i++; continue; }
    if (c === '`') {
      RE_CODIGO.lastIndex = i;
      const m = RE_CODIGO.exec(t);
      if (m) {
        soltar();
        padre.append(el('code', null, m[2].length > 2 && m[2].startsWith(' ') && m[2].endsWith(' ') ? m[2].slice(1, -1) : m[2]));
        i = RE_CODIGO.lastIndex;
        continue;
      }
      // Un `código` abierto (todavía llega): las comillas quedan como texto
      while (t[i] === '`') suelto += t[i++];
      continue;
    }
    if ((c === '*' || c === '_' || c === '~') && nivel < MAX_ANIDADO) {
      const r = enfasis(t, i, op, nivel);
      if (r) { soltar(); padre.append(r.nodo); i = r.fin; continue; }
    }
    if (c === '[' && !op.sinEnlaces) {
      RE_ENLACE.lastIndex = i;
      const m = RE_ENLACE.exec(t);
      if (m) {
        soltar();
        const etiqueta = m[1].replace(/\\([[\]\\])/g, '$1');
        const d = destinoEnlace(m[2], op);
        // Un enlace que no es del panel ni de Mnemo queda como su texto, sin la dirección
        const destino = d ? crearEnlace(d) : padre;
        enLinea(etiqueta, destino, { ...op, sinEnlaces: true }, nivel + 1);
        if (d) padre.append(destino);
        i = RE_ENLACE.lastIndex;
        continue;
      }
    }
    if (c === '<' && !op.sinEnlaces) {
      RE_AUTOENLACE.lastIndex = i;
      const m = RE_AUTOENLACE.exec(t);
      if (m) {
        soltar();
        const d = destinoEnlace(m[1], op);
        if (d) padre.append(Object.assign(crearEnlace(d), { textContent: m[1] }));
        else padre.append(m[1]);
        i = RE_AUTOENLACE.lastIndex;
        continue;
      }
    }
    if ((c === 'h' || c === 'H') && !op.sinEnlaces && (i === 0 || !LETRA.test(t[i - 1]))) {
      RE_URL.lastIndex = i;
      const m = RE_URL.exec(t);
      if (m) {
        const dir = m[0].replace(/[.,;:!?»]+$/, '');
        const d = destinoEnlace(dir, op);
        if (d) {
          soltar();
          padre.append(Object.assign(crearEnlace(d), { textContent: dir }));
          i += dir.length;
          continue;
        }
      }
    }
    suelto += c;
    i++;
  }
  soltar();
}

function pintarBloque(b, op, nivel = 0) {
  switch (b.tipo) {
    case 'titulo': {
      const h = el(b.nivel <= 2 ? 'h3' : 'h4');
      enLinea(b.texto, h, op);
      return h;
    }
    case 'regla': return el('hr');
    case 'codigo': {
      const pre = el('pre');
      pre.append(el('code', null, b.texto));
      return pre;
    }
    case 'cita': {
      const q = el('blockquote');
      const internos = nivel < 2 ? partirBloques(b.texto) : [{ tipo: 'parrafo', texto: b.texto }];
      for (const x of internos) q.append(pintarBloque(x, op, nivel + 1));
      return q;
    }
    case 'lista': {
      const l = el(b.ordenada ? 'ol' : 'ul');
      if (b.ordenada && b.inicio > 1) l.start = b.inicio;
      for (const it of b.items.slice(0, MAX_FILAS)) {
        const li = el('li');
        enLinea(it.texto, li, op);
        if (it.sub) {
          const s = el(it.sub.ordenada ? 'ol' : 'ul');
          for (const x of it.sub.items.slice(0, MAX_FILAS)) {
            const sli = el('li');
            enLinea(x, sli, op);
            s.append(sli);
          }
          li.append(s);
        }
        l.append(li);
      }
      return l;
    }
    case 'tabla': {
      // La tabla se desplaza dentro de su caja: nunca ensancha el panel
      const caja = el('div', 'md-tabla');
      caja.tabIndex = 0;
      caja.setAttribute('role', 'region');
      caja.setAttribute('aria-label', 'Tabla');
      const tabla = el('table');
      const cabeza = el('thead');
      const fila = el('tr');
      const n = b.cab.length;
      b.cab.forEach((c, k) => {
        const th = el('th', b.alin[k] || null);
        th.scope = 'col';
        enLinea(c, th, op);
        fila.append(th);
      });
      cabeza.append(fila);
      const cuerpo = el('tbody');
      for (const f of b.filas) {
        const tr = el('tr');
        for (let k = 0; k < n; k++) {
          const td = el('td', b.alin[k] || null);
          enLinea(f[k] ?? '', td, op);
          tr.append(td);
        }
        cuerpo.append(tr);
      }
      tabla.append(cabeza, cuerpo);
      caja.append(tabla);
      return caja;
    }
    default: {
      const p = el('p');
      enLinea(b.texto, p, op);
      return p;
    }
  }
}

/** Repinta una parte de texto: solo los bloques que cambiaron (al llegar por partes, el último). */
function pintarTexto(parte, op) {
  const bloques = partirBloques(parte.fuente);
  const previos = parte.bloques;
  for (let k = 0; k < bloques.length; k++) {
    const clave = JSON.stringify(bloques[k]);
    if (previos[k]?.clave === clave) continue;
    const nodo = pintarBloque(bloques[k], op);
    if (previos[k]) { previos[k].nodo.replaceWith(nodo); previos[k] = { clave, nodo }; }
    else { parte.el.append(nodo); previos.push({ clave, nodo }); }
  }
  while (previos.length > bloques.length) previos.pop().nodo.remove();
}

// ───────── El asistente ─────────

let montado = null;

/** Monta el asistente una sola vez (app.js lo llama en cada vista): `ir` es el enrutador del panel, `rutaPanel(ruta)`
 * dice si una ruta es de RUTAS y si el rol la abre, e `insignias()` refresca las del menú. Devuelve {mostrar, ocultar}:
 * `mostrar` lo enseña si el estado lo permite (pide /api/agente/estado), `ocultar` lo esconde y corta lo que esté en
 * curso (la cuenta quedó pendiente). */
export function montarAgente({ ir, rutaPanel = () => null, insignias = () => {} } = {}) {
  if (montado) return montado;
  const listos = cargarEstilos();
  const caja = el('div', 'agente');
  caja.id = 'agente';
  montar(caja, html`
    <button type="button" id="agente-boton" class="agente-boton" aria-controls="agente-panel" aria-expanded="false" aria-label="Abrir el asistente" title="Asistente" hidden>${icono('agente')}<span class="agente-senal" hidden></span></button>
    <section id="agente-panel" class="agente-panel" role="dialog" aria-modal="false" aria-labelledby="agente-titulo" data-estado="listo" hidden>
      <header class="agente-cab">
        <span class="agente-sello" aria-hidden="true">${icono('agente')}</span>
        <div class="agente-titulos"><h2 id="agente-titulo">Asistente</h2><small id="agente-sub">Nueva conversación</small></div>
        <button type="button" class="btn fantasma chico agente-icono" id="agente-nueva" aria-label="Nueva conversación" title="Nueva conversación">${icono('nueva')}</button>
        <button type="button" class="btn fantasma chico agente-icono" id="agente-ver-historial" aria-label="Conversaciones anteriores" title="Conversaciones" aria-expanded="false" aria-controls="agente-historial">${icono('historial')}</button>
        <button type="button" class="btn fantasma chico agente-icono" id="agente-cerrar" aria-label="Cerrar el asistente" title="Cerrar">${icono('cerrar')}</button>
      </header>
      <section id="agente-historial" class="agente-historial" aria-labelledby="agente-historial-t" hidden>
        <div class="agente-historial-cab"><h3 id="agente-historial-t">Conversaciones</h3><button type="button" class="btn chico" id="agente-volver">Volver</button></div>
        <ul id="agente-lista" class="agente-lista"></ul>
        <p class="agente-historial-pie">Solo usted ve sus conversaciones. Se borran solas pasado el tiempo que fija el administrador.</p>
      </section>
      <div class="agente-cuerpo" id="agente-cuerpo">
        <div id="agente-mensajes" class="agente-mensajes" role="log" aria-live="polite" aria-label="Conversación con el asistente" tabindex="0"></div>
        <button type="button" class="agente-bajar" id="agente-bajar" aria-label="Ir al final de la conversación" title="Ir al final" hidden>${icono('abajo')}</button>
      </div>
      <form id="agente-form" class="agente-compositor" novalidate>
        <p class="agente-nota-pendiente" id="agente-nota-pendiente" hidden>Hay acciones esperando su aprobación. Si escribe otro mensaje, quedan sin aprobar.</p>
        <div class="agente-fila">
          <label class="sr" for="agente-texto">Mensaje para el asistente</label>
          <textarea id="agente-texto" rows="1" maxlength="4000" placeholder="Escriba su pregunta…" enterkeyhint="send" autocomplete="off" spellcheck="true"></textarea>
          <button type="submit" class="btn primario agente-enviar" id="agente-enviar" aria-label="Enviar" title="Enviar">${icono('enviar')}</button>
          <button type="button" class="btn agente-detener" id="agente-detener" hidden>${icono('detener')}<span>Detener</span></button>
        </div>
        <p class="agente-pie"><span id="agente-restantes"></span><span class="agente-ayuda">Enter envía · Mayús+Enter, otra línea</span></p>
      </form>
    </section>`);
  document.body.append(caja);

  const $ = (sel) => caja.querySelector(sel);
  const boton = $('#agente-boton'), senalEl = $('.agente-senal'), panel = $('#agente-panel'), sub = $('#agente-sub');
  const nuevaBtn = $('#agente-nueva'), verHistBtn = $('#agente-ver-historial'), cerrarBtn = $('#agente-cerrar');
  const historial = $('#agente-historial'), listaHist = $('#agente-lista'), volverBtn = $('#agente-volver');
  const cuerpo = $('#agente-cuerpo'), log = $('#agente-mensajes'), bajarBtn = $('#agente-bajar'), form = $('#agente-form');
  const entrada = $('#agente-texto'), enviarBtn = $('#agente-enviar'), detenerBtn = $('#agente-detener');
  const notaPendiente = $('#agente-nota-pendiente'), restantes = $('#agente-restantes');

  // ── Estado ──
  let info = null;            // GET /api/agente/estado, normalizado
  let infoT = 0;              // cuándo se leyó
  let leyendo = null;         // la lectura en curso (una sola)
  let visible = false;        // app.js lo quiere a la vista (rol con permiso y sin cuenta pendiente)
  let abierto = false;
  let iniciado = false;       // ya se pintó la conversación guardada o la bienvenida
  let historialAbierto = false;
  let conv = null;            // id de la conversación actual
  let titulo = '';
  let actual = null;          // el mensaje del asistente donde van las partes nuevas: {el}
  let ultima = null;          // la última parte (texto o nota de progreso) que sigue recibiendo trozos
  let ronda = { partes: [], recortes: new Map() }; // lo pintado en la ronda en curso (para `descartar`)
  let turno = null;           // el turno en curso: {control, tipo, inicio, fin, error, …}
  let novedad = false;        // llegó algo con el panel cerrado
  let devolverFoco = false;   // tras una navegación pedida por el asistente, el foco vuelve al cuadro de texto
  let ultimaRuta = rutaActual();
  let seguir = true;          // el desplazamiento sigue el final (salvo que la persona haya subido)
  let numTarjeta = 0;
  let restaurado = false;     // ya se leyó lo guardado en la pestaña (abierto, conversación)
  let detenidoEn = 0;         // cuándo detuvo la persona el último turno
  let cargando = false;       // se está trayendo una conversación: no se envía nada a la anterior
  let vez = 0;                // cambia con cada conversación que se pinta: una respuesta tardía no pisa la nueva
  const chips = new Map();    // id del tool_use → chip
  const tarjetas = new Map(); // id del tool_use → tarjeta de aprobación
  const sucias = new Set();   // partes de texto por repintar en el próximo cuadro
  let cuadro = 0;
  const op = { rutaPanel, origenMnemo: null };

  // Con algo escrito o un turno en curso, una sesión vencida abre el ingreso en un diálogo en vez de recargar
  const conAlgo = () => !!entrada.value.trim() || !!turno;
  registrarPendiente(conAlgo);

  // ── Guardado en la pestaña (nada de la conversación: solo su id) ──
  function guardar() {
    try {
      sessionStorage.setItem(GUARDADO, JSON.stringify({ abierto, conversacion: conv, uid: sesion.uid }));
    } catch { /* bloqueado */ }
  }
  function leerGuardado() {
    try {
      const g = JSON.parse(sessionStorage.getItem(GUARDADO) || 'null');
      if (g && typeof g === 'object' && g.uid === sesion.uid) {
        const id = Number.isInteger(g.conversacion) && g.conversacion > 0 ? g.conversacion : null;
        return { abierto: g.abierto === true, conversacion: id };
      }
    } catch { /* bloqueado o dañado */ }
    return { abierto: false, conversacion: null };
  }

  // ── Estado del asistente para esta persona ──
  // `proveedor`: de dónde sale el modelo de las conversaciones nuevas (`mnemo`, `anthropic` o null si no hay ninguno).
  // `conexion`: la conexión con Mnemo (solo llega al administrador y al coordinador): {estado, motivo, modelo} o null
  function normalizar(d) {
    const o = d && typeof d === 'object' ? d : {};
    const limite = o.limite && typeof o.limite === 'object' ? o.limite : {};
    const c = o.mnemo?.conexion && typeof o.mnemo.conexion === 'object' ? o.mnemo.conexion : null;
    return {
      disponible: o.disponible === true,
      motivo: texto(o.motivo, 40) || null,
      proveedor: ['mnemo', 'anthropic'].includes(o.proveedor) ? o.proveedor : null,
      esAdmin: o.es_admin === true,
      escritura: o.escritura !== false,
      limite: { usados: entero(limite.usados), maximo: entero(limite.maximo) },
      mnemo: { activo: o.mnemo?.activo === true, origen: origenSeguro(o.mnemo?.origen) },
      conexion: c && ['sin_conectar', 'conectada', 'caida'].includes(c.estado)
        ? { estado: c.estado, motivo: texto(c.motivo, 40) || null, modelo: c.modelo === true } : null,
      sugerencias: (Array.isArray(o.sugerencias) ? o.sugerencias : []).map((s) => texto(s, 200).trim()).filter(Boolean)
        .slice(0, 6),
    };
  }

  function leerEstado() {
    leyendo ||= (async () => {
      try {
        info = normalizar(await api.get('/api/agente/estado'));
        infoT = Date.now();
      } catch {
        infoT = Date.now() - VIGENCIA_ESTADO_MS + REINTENTO_ESTADO_MS; // se vuelve a intentar en un rato
      } finally {
        leyendo = null;
      }
    })();
    return leyendo;
  }

  // El administrador ve el botón aunque no haya modelo (Mnemo sin conectar) o su rol esté apagado: adentro se explica qué
  // hacer
  const usable = () => !!info && (info.disponible || (info.esAdmin && info.motivo !== 'cuenta'));

  function aplicarEstado() {
    op.origenMnemo = info?.mnemo.origen || null;
    pintarRestantes();
    const util = visible && usable();
    caja.toggleAttribute('data-usable', util); // la barra del celular le hace lugar al botón (agente.css)
    boton.hidden = !util || abierto;
    if (!util) { if (abierto) cerrar(); return; }
    if (!info.disponible) pintarExplicacion();
    else if (iniciado && log.dataset.explicacion) {
      // Ya está disponible (se conectó Mnemo o se encendió para su rol): la explicación da paso a la conversación
      iniciado = false;
      delete log.dataset.explicacion;
      if (abierto) iniciar();
    }
    form.hidden = !info.disponible || historialAbierto;
    nuevaBtn.hidden = verHistBtn.hidden = !info.disponible;
  }

  async function mostrar() {
    visible = true;
    await listos;
    const viejo = Date.now() - infoT > VIGENCIA_ESTADO_MS;
    if (!info || (viejo && !turno)) await leerEstado();
    if (!visible) return;
    aplicarEstado();
    if (!usable() || restaurado) return;
    restaurado = true;
    const g = leerGuardado();
    conv = info.disponible ? g.conversacion : null;
    if (g.abierto) abrir({ foco: false });
  }

  function ocultar() {
    visible = false;
    turno?.control.abort();
    caja.removeAttribute('data-usable');
    boton.hidden = true;
    if (abierto) cerrar();
  }

  // ── Abrir y cerrar ──
  function abrir({ foco = true } = {}) {
    if (!usable()) return;
    abierto = true;
    novedad = false;
    panel.hidden = false;
    boton.hidden = true;
    boton.setAttribute('aria-expanded', 'true');
    guardar();
    senal();
    ajustarTeclado();
    if (!iniciado) iniciar();
    alFinal(true);
    if (foco) (form.hidden ? cerrarBtn : entrada).focus({ preventScroll: true });
  }

  function cerrar({ foco = false } = {}) {
    abierto = false;
    panel.hidden = true;
    boton.hidden = !(visible && usable());
    boton.setAttribute('aria-expanded', 'false');
    guardar();
    senal();
    if (foco && !boton.hidden) boton.focus({ preventScroll: true });
  }

  /** En el celular el panel tapa la vista: se pliega para que se vea lo que hizo el asistente (o la vista que se abrió). */
  function plegar() {
    if (abierto && esMovil()) cerrar();
  }

  function iniciar() {
    iniciado = true;
    if (!info?.disponible) { pintarExplicacion(); return; }
    if (conv) abrirConversacion(conv, { silencioso: true });
    else pintarBienvenida();
  }

  // ── La señal del botón: algo espera con el panel cerrado ──
  function senal() {
    const pendientes = pendientesSinEnviar().length > 0;
    const s = abierto ? '' : pendientes ? 'pendiente' : turno ? 'trabajando' : novedad ? 'nuevo' : '';
    boton.dataset.senal = s;
    senalEl.hidden = !s;
    boton.setAttribute('aria-label', {
      pendiente: 'Abrir el asistente: hay una acción esperando su aprobación',
      trabajando: 'Abrir el asistente: está respondiendo',
      nuevo: 'Abrir el asistente: hay una respuesta nueva',
    }[s] || 'Abrir el asistente');
  }

  // ── Desplazamiento: sigue el final mientras la persona no suba a leer ──
  const pegado = () => log.scrollHeight - log.scrollTop - log.clientHeight < 48;
  log.addEventListener('scroll', () => {
    seguir = pegado();
    if (seguir) bajarBtn.hidden = true;
  }, { passive: true });
  function alFinal(forzar = false) {
    if (forzar || seguir) {
      log.scrollTop = log.scrollHeight;
      seguir = true;
      bajarBtn.hidden = true;
    } else if (!historialAbierto) {
      bajarBtn.hidden = false;
    }
  }
  bajarBtn.addEventListener('click', () => { alFinal(true); entrada.focus({ preventScroll: true }); });

  // Los trozos de texto se juntan y se pintan una vez por cuadro: el último bloque se rehace, los demás se quedan
  function programar() {
    if (!cuadro) cuadro = requestAnimationFrame(pintarSucias);
  }
  function pintarSucias() {
    cuadro = 0;
    for (const p of sucias) pintarTexto(p, op);
    sucias.clear();
    alFinal();
  }
  function vaciar() {
    if (cuadro) cancelAnimationFrame(cuadro);
    pintarSucias();
  }

  // ── La conversación en el DOM ──
  function limpiarConversacion() {
    vez++;
    cargando = false;
    if (cuadro) cancelAnimationFrame(cuadro);
    cuadro = 0;
    sucias.clear();
    chips.clear();
    tarjetas.clear();
    actual = ultima = null;
    nuevaRonda();
    log.replaceChildren();
    delete log.dataset.explicacion;
    seguir = true;
    actualizarPendientes();
  }

  function fijarConversacion(id, t) {
    if (Number.isInteger(id) && id > 0) conv = id;
    titulo = texto(t, 120) || titulo;
    sub.textContent = conv ? titulo || 'Conversación' : 'Nueva conversación';
    sub.title = sub.textContent;
    guardar();
  }

  function nuevaRonda() {
    ronda = { partes: [], recortes: new Map() };
    ultima = null;
  }

  // Para los lectores de pantalla: quién dice cada mensaje
  function quien(clase, t) {
    const s = el('span', 'sr', t);
    s.dataset.quien = clase;
    return s;
  }

  function agregarUsuario(t) {
    const m = el('div', 'agente-msj agente-persona');
    m.append(quien('usuario', 'Usted: '), el('p', null, t));
    log.append(m);
    actual = ultima = null;
    return m;
  }

  function nuevoAsistente() {
    const m = el('div', 'agente-msj agente-respuesta');
    m.append(quien('asistente', 'Asistente: '));
    log.append(m);
    actual = { el: m };
    ultima = null;
    return actual;
  }
  const enAsistente = () => (actual || nuevoAsistente()).el;

  function aviseNovedad() {
    if (!abierto) { novedad = true; senal(); }
  }

  /** La parte que recibe los trozos de un tipo: la última si es de ese tipo, si no una nueva (de esta ronda). */
  function parte(tipo) {
    if (ultima?.tipo === tipo) {
      if (!ronda.partes.includes(ultima) && !ronda.recortes.has(ultima)) {
        ronda.recortes.set(ultima, tipo === 'texto' ? ultima.fuente.length : ultima.nodo.length);
      }
      return ultima;
    }
    let p;
    if (tipo === 'texto') {
      p = { tipo, el: el('div', 'agente-md'), fuente: '', bloques: [] };
    } else {
      p = { tipo, el: el('p', 'agente-progreso'), nodo: document.createTextNode('') };
      p.el.append(p.nodo);
    }
    enAsistente().append(p.el);
    ronda.partes.push(p);
    ultima = p;
    return p;
  }

  function agregarTexto(delta) {
    const p = parte('texto');
    p.fuente += delta;
    sucias.add(p);
    programar();
    aviseNovedad();
  }

  function agregarProgreso(delta) {
    parte('progreso').nodo.appendData(delta);
    programar();
  }

  /** Una nota (aviso del servidor, resultado de una acción): gris si es informativa, ámbar si es una alerta. */
  function nota(t, nivel = 'info', { enRonda = false, dentro = null } = {}) {
    if (!t) return null;
    const n = el('p', `agente-nota ${nivel === 'alerta' ? 'alerta' : 'info'}`);
    n.append(ico(nivel === 'alerta' ? 'alerta' : 'info'), el('span', null, t));
    (dentro || enAsistente()).append(n);
    if (enRonda) ronda.partes.push({ tipo: 'nota', el: n });
    ultima = null;
    programar();
    return n;
  }

  /** Quita lo que pintó la ronda en curso: el servidor la repite (un error pasajero) o el modelo no siguió. */
  function descartar() {
    vaciar();
    for (const p of ronda.partes) {
      p.el.remove();
      if (p.tipo === 'chip') chips.delete(p.id);
      sucias.delete(p);
    }
    for (const [p, largo] of ronda.recortes) {
      if (p.tipo === 'texto') { p.fuente = p.fuente.slice(0, largo); pintarTexto(p, op); }
      else p.nodo.deleteData(largo, p.nodo.length - largo);
    }
    nuevaRonda();
  }

  /** `texto_ronda`: el texto final de la ronda en curso, cuando no coincide con lo que llegó por partes (con Mnemo los
   * trozos son un adelanto: vale el resultado). Reemplaza el texto de la ronda, sin tocar lo de rondas anteriores: va
   * en su primera parte de texto (o en una nueva) y las demás se quitan; vacío, la ronda queda sin texto. */
  function textoRonda(t) {
    vaciar();
    const quitar = (p) => {
      p.el.remove();
      sucias.delete(p);
      ronda.partes.splice(ronda.partes.indexOf(p), 1);
      if (ultima === p) ultima = null;
    };
    const propias = ronda.partes.filter((p) => p.tipo === 'texto');
    const heredadas = [...ronda.recortes].filter(([p]) => p.tipo === 'texto');
    for (const [p, largo] of heredadas) { p.fuente = p.fuente.slice(0, largo); sucias.add(p); }
    for (const p of propias.slice(1)) quitar(p);
    let destino = propias[0] || heredadas[0]?.[0] || null;
    if (destino && destino === propias[0]) destino.fuente = '';
    if (!destino && t) {
      // Una parte nueva, antes de las herramientas de la ronda (el modelo escribe y después las pide)
      destino = { tipo: 'texto', el: el('div', 'agente-md'), fuente: '', bloques: [] };
      const chip = ronda.partes.find((p) => p.tipo === 'chip' && p.el.isConnected);
      if (chip) chip.el.before(destino.el);
      else enAsistente().append(destino.el);
      ronda.partes.push(destino);
    }
    if (destino) {
      destino.fuente += t;
      if (!destino.fuente && ronda.partes.includes(destino)) quitar(destino);
      else sucias.add(destino);
    }
    programar();
    if (t) aviseNovedad();
  }

  // ── Herramientas: un chip por tool_use, con su estado ──
  const ICONOS_ESTADO = { ok: 'hecho', error: 'alerta', pendiente: 'reloj', rechazada: 'cerrar' };
  const TEXTO_ESTADO = { inicio: 'en curso', ok: 'listo', error: 'falló', pendiente: 'espera su aprobación',
    aprobada: 'aprobada, en curso', rechazada: 'rechazada' };

  function crearChip(id, nombre) {
    const c = { tipo: 'chip', id, el: el('div', 'agente-herr'), marca: el('span', 'agente-estado'), et: el('span', 'et'),
      res: el('span', 'res'), sr: el('span', 'sr'), estado: null, etiqueta: '' };
    c.el.title = nombre || '';
    const t = el('span', 'agente-herr-texto');
    t.append(c.et, c.res, c.sr);
    c.el.append(c.marca, t);
    return c;
  }

  function pintarChip(c, etiqueta, estado, resumen) {
    c.etiqueta = etiqueta || c.etiqueta;
    if (c.estado !== estado) {
      c.estado = estado;
      c.el.dataset.estado = estado;
      const enCurso = estado === 'inicio' || estado === 'aprobada';
      c.marca.replaceChildren(enCurso ? el('span', 'agente-giro') : ico(ICONOS_ESTADO[estado]));
    }
    c.et.textContent = c.etiqueta;
    c.res.textContent = resumen ? ` · ${resumen}` : '';
    c.sr.textContent = ` (${TEXTO_ESTADO[estado]})`;
  }

  function alHerramienta(ev) {
    const id = texto(ev.id, 100);
    const estado = ESTADOS.has(ev.estado) ? ev.estado : null;
    if (!id || !estado) return;
    const etiqueta = texto(ev.etiqueta, 120) || texto(ev.nombre, 64) || 'Herramienta';
    const resumen = texto(ev.resumen, 200);
    let c = chips.get(id);
    if (!c) {
      c = crearChip(id, texto(ev.nombre, 64));
      chips.set(id, c);
      enAsistente().append(c.el);
      ultima = null;
      if (estado === 'inicio') ronda.partes.push(c);
    }
    pintarChip(c, etiqueta, estado, resumen);
    const t = tarjetas.get(id);
    if (t) estadoTarjeta(t, estado, resumen);
    // Los resultados llegan al cerrar una ronda: lo que venga después es de la ronda siguiente
    if (estado !== 'inicio') nuevaRonda();
    programar();
  }

  // ── Tarjetas de aprobación ──
  const pendientesSinEnviar = () => [...tarjetas.values()].filter((t) => !t.final && !t.enviada);

  function pares(detalle) {
    return (Array.isArray(detalle) ? detalle : []).slice(0, 30)
      .filter((p) => Array.isArray(p) && p.length >= 2)
      .map(([k, v]) => [texto(k, 80), texto(typeof v === 'string' ? v : v == null ? '' : String(v), 500)])
      .filter(([k]) => k);
  }

  function crearTarjeta({ id, titulo: t, detalle, aviso }) {
    const n = ++numTarjeta;
    const art = el('article', 'agente-tarjeta');
    art.dataset.estado = 'pendiente';
    art.setAttribute('aria-labelledby', `agente-tarjeta-${n}`);
    const h = el('h3', null, t);
    h.id = `agente-tarjeta-${n}`;
    art.append(el('p', 'agente-tarjeta-et', 'Necesita su aprobación'), h);
    if (detalle.length) {
      const dl = el('dl');
      for (const [k, v] of detalle) {
        const fila = el('div');
        fila.append(el('dt', null, k), el('dd', null, v || '—'));
        dl.append(fila);
      }
      art.append(dl);
    }
    if (aviso) {
      const a = el('p', 'agente-tarjeta-aviso');
      a.append(ico('alerta'), el('span', null, aviso));
      art.append(a);
    }
    const botones = el('div', 'agente-tarjeta-botones');
    const si = el('button', 'btn primario', 'Aprobar');
    const no = el('button', 'btn', 'Rechazar');
    si.type = no.type = 'button';
    si.setAttribute('aria-pressed', 'false');
    no.setAttribute('aria-pressed', 'false');
    botones.append(si, no);
    const linea = el('p', 'agente-tarjeta-estado');
    linea.setAttribute('aria-live', 'polite');
    art.append(botones, linea);
    const tarjeta = { id, el: art, si, no, botones, linea, decision: null, enviada: false, final: false };
    si.addEventListener('click', () => decidir(tarjeta, true));
    no.addEventListener('click', () => decidir(tarjeta, false));
    return tarjeta;
  }

  function alConfirmar(ev, { dentro = null } = {}) {
    const id = texto(ev.id, 100);
    if (!id || tarjetas.has(id)) return;
    const t = crearTarjeta({ id, titulo: texto(ev.titulo, 200) || 'Confirmar acción', detalle: pares(ev.detalle),
      aviso: texto(ev.aviso, 500) });
    tarjetas.set(id, t);
    (dentro || enAsistente()).append(t.el);
    nuevaRonda();
    actualizarPendientes();
    aviseNovedad();
    programar();
  }

  function actualizarPendientes() {
    const hay = pendientesSinEnviar().length > 0;
    notaPendiente.hidden = !hay || !!turno;
    for (const t of tarjetas.values()) {
      if (t.final) continue;
      t.si.disabled = t.no.disabled = t.enviada || !!turno;
    }
    senal();
  }

  function decidir(t, aprobar) {
    if (t.final || t.enviada || turno) return;
    t.decision = aprobar;
    t.si.setAttribute('aria-pressed', String(aprobar));
    t.no.setAttribute('aria-pressed', String(!aprobar));
    const lote = pendientesSinEnviar();
    const faltan = lote.filter((x) => x.decision === null).length;
    if (faltan) {
      const cuantas = faltan === 1 ? 'otra acción' : `${faltan} acciones`;
      t.linea.textContent = `${aprobar ? 'Aprobada' : 'Rechazada'}. Falta decidir ${cuantas}: se envían juntas.`;
      return;
    }
    enviarDecisiones(lote);
  }

  function estadoTarjeta(t, estado, resumen) {
    if (estado === 'pendiente' || t.final) return;
    t.el.dataset.estado = estado;
    t.botones.hidden = true;
    const textos = {
      aprobada: 'Aprobada. Guardando…',
      ok: `Hecho${resumen ? ` · ${resumen}` : ''}`,
      error: `No se pudo${resumen ? `: ${resumen}` : ''}`,
      rechazada: resumen === 'No aprobada' ? 'Sin aprobar: escribió otro mensaje.' : 'Rechazada. No se hizo nada.',
      inicio: 'En curso…',
    };
    t.linea.textContent = textos[estado] || '';
    if (estado !== 'aprobada' && estado !== 'inicio') t.final = true;
    actualizarPendientes();
  }

  function enviarDecisiones(lote) {
    if (!lote.length || turno || !conv) return;
    for (const t of lote) {
      t.enviada = true;
      t.linea.textContent = t.decision ? 'Aprobada. Enviando…' : 'Rechazada. Enviando…';
    }
    actualizarPendientes();
    // Lo que el asistente diga después va en el mismo mensaje que las tarjetas
    const msj = lote[lote.length - 1].el.closest('.agente-msj');
    if (msj) { actual = { el: msj }; ultima = null; }
    const decisiones = lote.map((t) => ({ id: t.id, aprobar: t.decision }));
    correr('/api/agente/confirmaciones', { conversacion: conv, decisiones }, { tipo: 'confirmacion', lote, msj: enAsistente() });
  }

  // ── Acciones que pide el servidor ──
  function accion(a) {
    if (!a || typeof a !== 'object') return;
    if (a.tipo === 'navegar') navegar(a);
    else if (a.tipo === 'recargar') recargar();
    else if (a.tipo === 'insignias') { try { insignias(); } catch (e) { console.error(e); } }
    else if (a.tipo === 'mapa') mapa(a);
  }

  function navegar(a) {
    const ruta = texto(a.ruta, 700);
    const d = ruta.startsWith('/') ? destinoEnlace(ruta, op) : null;
    if (d?.tipo !== 'interno') {
      nota('El asistente pidió abrir una dirección que no es una vista del panel (o que su rol no abre): no la abrí.',
        'alerta');
      return;
    }
    // Con el mapa ya abierto y listo, ir() lo destruiría y lo volvería a crear (unos 8 s, perdiendo lo resaltado): sus
    // filtros se aplican sobre el mismo mapa. Una zona (área o polígono en la URL) sí necesita la navegación.
    const [camino, consulta = ''] = d.ruta.split('?');
    const params = new URLSearchParams(consulta);
    if (camino === '/mapa' && rutaActual() === '/mapa' && mapaListo() && !params.has('area_id') && !params.has('poligono')) {
      mapa({ acciones: [{ tipo: 'filtros', valores: Object.fromEntries(params), reemplazar: true }] });
      return;
    }
    if (esMovil()) plegar();
    else devolverFoco = panel.contains(document.activeElement);
    ir(d.ruta, { reemplazar: d.ruta === rutaActual() + location.search });
  }

  function recargar() {
    // El mapa no se rehace: perdería lo que el asistente acaba de poner en él (vuelos, resaltados)
    if (rutaActual() === '/mapa') return;
    if (hayCambiosSinGuardar(conAlgo)) {
      nota('La vista tiene cambios sin guardar: no la recargué. Guárdelos o descártelos para ver lo nuevo.');
      return;
    }
    devolverFoco = panel.contains(document.activeElement);
    ir(rutaActual() + location.search, { reemplazar: true });
  }

  function mapa(a) {
    const acciones = (Array.isArray(a.acciones) ? a.acciones : [])
      .filter((x) => x && typeof x === 'object' && !Array.isArray(x) && typeof x.tipo === 'string').slice(0, 20);
    if (!acciones.length) return;
    const dentro = enAsistente();
    if (esMovil()) plegar();
    else if (rutaActual() !== '/mapa') devolverFoco = panel.contains(document.activeElement);
    accionesMapa(acciones, { navegar: ir }).then((res) => {
      const malas = (Array.isArray(res) ? res : []).filter((r) => r && r.ok === false);
      if (!malas.length) return;
      const motivos = malas.map((r) => texto(r.error, 120) || texto(r.tipo, 30)).filter(Boolean).join('; ');
      const cuantos = malas.length === 1 ? 'Un cambio no se pudo aplicar' : `${malas.length} cambios no se pudieron aplicar`;
      nota(`${cuantos} en el mapa${motivos ? `: ${motivos}` : ''}.`, 'alerta', { dentro });
    }, (e) => {
      nota(`El mapa no aplicó los cambios: ${texto(e?.message, 160) || 'no terminó de cargar'}.`, 'alerta', { dentro });
    });
  }

  // ── El turno: un mensaje o una aprobación, en flujo ──
  function alEvento(ev, t) {
    switch (ev.tipo) {
      case 'inicio':
        t.inicio = true;
        fijarConversacion(ev.conversacion, ev.titulo);
        nuevaRonda();
        break;
      case 'progreso': if (texto(ev.texto)) agregarProgreso(texto(ev.texto)); break;
      case 'texto': if (texto(ev.texto)) agregarTexto(texto(ev.texto)); break;
      case 'texto_ronda': if (typeof ev.texto === 'string') textoRonda(texto(ev.texto, MAX_TEXTO_RONDA)); break;
      case 'herramienta': alHerramienta(ev); break;
      case 'accion':
        accion(ev.accion);
        nuevaRonda();
        break;
      case 'confirmar': alConfirmar(ev); break;
      case 'descartar': descartar(); break;
      case 'aviso': nota(texto(ev.texto, 600), ev.nivel === 'alerta' ? 'alerta' : 'info', { enRonda: true }); break;
      case 'error':
        t.error = { mensaje: texto(ev.mensaje, 400) || 'El asistente falló al responder.', codigo: texto(ev.codigo, 40) };
        break;
      case 'fin':
        t.fin = { motivo: texto(ev.motivo, 20) };
        if (ev.limite && typeof ev.limite === 'object' && info) {
          info.limite = { usados: entero(ev.limite.usados), maximo: entero(ev.limite.maximo) };
          pintarRestantes();
        }
        break;
      default: break; // `latido` y lo que todavía no se conoce
    }
  }

  function ponerEstado() {
    const ocupado = !!turno;
    panel.dataset.estado = ocupado ? 'respondiendo' : 'listo';
    if (!ocupado && document.activeElement === detenerBtn) entrada.focus({ preventScroll: true });
    enviarBtn.hidden = ocupado;
    detenerBtn.hidden = !ocupado;
    nuevaBtn.disabled = verHistBtn.disabled = ocupado;
    for (const b of log.querySelectorAll('.agente-reintentar, .agente-sugerencia')) b.disabled = ocupado;
    if (ocupado) log.setAttribute('aria-busy', 'true');
    else log.removeAttribute('aria-busy');
    actualizarPendientes();
  }

  async function correr(ruta, cuerpo, datos) {
    const t = { control: new AbortController(), inicio: false, fin: null, error: null, excepcion: null, ...datos };
    turno = t;
    nuevaRonda();
    ponerEstado();
    t.msj?.classList.add('trabajando'); // tres puntos al final mientras responde
    let terminado = false;
    const pedir = () => flujo(ruta, cuerpo, {
      signal: t.control.signal,
      alEvento: (ev) => { try { alEvento(ev, t); } catch (e) { console.error(e); } },
    });
    try {
      terminado = await pedir();
    } catch (e) {
      t.excepcion = e;
      // Recién detenido el turno anterior, el servidor tarda un momento en soltarlo: se intenta una vez más
      if (e instanceof ErrorApi && e.codigo === 'ocupada' && !t.inicio && Date.now() - detenidoEn < 6000) {
        await new Promise((listo) => setTimeout(listo, 1200));
        t.excepcion = null; // detenido durante la espera: termina como «Detuvo la respuesta»
        if (!t.control.signal.aborted) {
          try { terminado = await pedir(); } catch (e2) { t.excepcion = e2; }
        }
      }
    }
    vaciar();
    turno = null;
    t.msj?.classList.remove('trabajando');
    ponerEstado();
    cerrarTurno(t, terminado);
    nuevaRonda();
    alFinal();
  }

  async function enviar(t, { reusar = null } = {}) {
    if (turno || cargando || !info?.disponible) return;
    t = t.trim();
    if (!t) return;
    if (t.length > MAX_TEXTO) {
      nota(`El mensaje es demasiado largo: el máximo es ${num(MAX_TEXTO)} caracteres.`, 'alerta');
      return;
    }
    if (historialAbierto) verHistorial(false);
    if (log.querySelector('.agente-bienvenida')) log.replaceChildren();
    let burbuja = reusar?.burbuja;
    if (burbuja?.isConnected) {
      burbuja.classList.remove('sin-enviar');
      burbuja.querySelector('.agente-sin-enviar')?.remove();
      reusar.msj.replaceChildren(quien('asistente', 'Asistente: '));
      actual = { el: reusar.msj };
      log.append(burbuja, reusar.msj); // al final, aunque después se hayan escrito otras cosas
    } else {
      burbuja = agregarUsuario(t);
      nuevoAsistente();
    }
    // Lo pendiente que no se decidió queda sin aprobar: el servidor lo rechaza al recibir el mensaje (y lo avisa)
    const sinAprobar = pendientesSinEnviar();
    for (const x of sinAprobar) x.enviada = true;
    alFinal(true);
    await correr('/api/agente/mensajes', { conversacion: conv, texto: t, contexto: contexto() },
      { tipo: 'mensaje', texto: t, burbuja, msj: actual.el, sinAprobar });
  }

  // ── Cómo terminó el turno ──
  function marcarInterrumpidas() {
    for (const c of chips.values()) {
      if (c.estado === 'inicio' || c.estado === 'aprobada') pintarChip(c, c.etiqueta, 'error', 'Interrumpida');
    }
  }

  function explicar(e) {
    if (!(e instanceof ErrorApi)) return 'El asistente falló en el navegador. Intente de nuevo.';
    if (e.estado === 401) return 'La sesión terminó. Ingrese de nuevo para seguir con el asistente.';
    if (e.estado === 413) return 'El mensaje es demasiado largo.';
    if (e.estado === 422) return `El mensaje no es válido: no puede ir vacío ni pasar de ${num(MAX_TEXTO)} caracteres.`;
    if (e.estado === 0) return e.message;
    if (e.message && e.message !== 'Error inesperado') return e.message;
    return `El panel no pudo atender al asistente (error ${e.estado}). Intente de nuevo en un momento.`;
  }

  /** Un error del turno con lo que se puede hacer: [[texto del botón, función]]. */
  function mostrarError(mensaje, acciones = [], dentro = null) {
    const caja = el('div', 'agente-error');
    caja.setAttribute('role', 'alert');
    const linea = el('p');
    linea.append(ico('alerta'), el('span', null, mensaje));
    caja.append(linea);
    if (acciones.length) {
      const fila = el('div', 'agente-error-acciones');
      for (const [etiqueta, fn] of acciones) {
        const b = el('button', 'btn chico agente-reintentar', etiqueta);
        b.type = 'button';
        b.addEventListener('click', () => { caja.remove(); fn(); });
        fila.append(b);
      }
      caja.append(fila);
    }
    (dentro || enAsistente()).append(caja);
    aviseNovedad();
    return caja;
  }

  function cerrarTurno(t, terminado) {
    const dentro = t.msj || actual?.el || null;
    const reintento = (reusar) => ['Reintentar', () => {
      entrada.focus({ preventScroll: true });
      enviar(t.texto, { reusar });
    }];
    // Si el mensaje no llegó a la conversación (un error antes del flujo), la nueva lo trae escrito para enviarlo ahí
    const otra = ['Nueva conversación', () => {
      nuevaConversacion();
      if (t.tipo === 'mensaje' && !t.inicio && !entrada.value.trim()) { entrada.value = t.texto; autoAltura(); }
    }];
    const releer = (codigo) => { if (RELEER_ESTADO.has(codigo)) leerEstado().then(aplicarEstado); };
    const acciones = [];
    let mensaje = null;
    let duda = 'se cortó antes de confirmar el resultado; revise la vista'; // tarjeta aprobada sin respuesta final
    if (t.excepcion) {
      const e = t.excepcion;
      const codigo = e instanceof ErrorApi ? e.codigo : null;
      const reintentable = !SIN_REINTENTO.has(codigo) && ![404, 413, 422, 429].includes(e?.estado);
      mensaje = explicar(e);
      if (CON_NUEVA.has(codigo) || e?.estado === 404) acciones.push(otra);
      releer(codigo);
      if (t.tipo === 'mensaje' && !t.inicio) {
        // El servidor no recibió el mensaje: la burbuja queda marcada, «Reintentar» la reusa y lo pendiente sigue
        for (const x of t.sinAprobar) if (!x.final) x.enviada = false;
        t.burbuja.classList.add('sin-enviar');
        t.burbuja.append(el('small', 'agente-sin-enviar', 'No se envió'));
        if (reintentable) acciones.unshift(reintento({ burbuja: t.burbuja, msj: t.msj }));
      } else if (t.tipo === 'mensaje' && reintentable) {
        acciones.unshift(reintento(null));
      } else if (t.tipo === 'confirmacion' && !t.inicio && codigo !== 'sin_pendientes') {
        // Las decisiones no llegaron: las tarjetas quedan listas otra vez, con la misma decisión marcada
        for (const x of t.lote) { x.enviada = false; x.linea.textContent = ''; }
        if (reintentable) acciones.unshift(['Reintentar', () => enviarDecisiones(t.lote.filter((x) => !x.final))]);
      } else if (codigo === 'sin_pendientes') {
        duda = 'ya no estaba pendiente';
      }
    } else if (!terminado) {
      nota('Detuvo la respuesta.', 'info', { dentro });
      duda = 'se detuvo antes de confirmar el resultado; revise la vista';
    } else if (t.error) {
      mensaje = t.error.mensaje;
      if (CON_NUEVA.has(t.error.codigo)) acciones.push(otra);
      else if (t.tipo === 'mensaje' && !SIN_REINTENTO.has(t.error.codigo)) acciones.push(reintento(null));
      releer(t.error.codigo);
    } else if (!t.fin) {
      mensaje = FLUJO_CORTADO;
      if (t.tipo === 'mensaje') acciones.push(reintento(null));
    } else if (t.fin.motivo === 'pasos') {
      const caja = nota('El asistente llegó al tope de pasos de un turno.', 'info', { dentro });
      const b = el('button', 'btn chico agente-reintentar', 'Continuar');
      b.type = 'button';
      b.addEventListener('click', () => { b.remove(); enviar('Continúa donde quedaste.'); });
      caja?.append(b);
    }
    marcarInterrumpidas();
    // Una tarjeta enviada que no recibió su resultado no queda «guardando…» para siempre
    if (t.tipo === 'confirmacion') for (const x of t.lote) if (x.enviada && !x.final) estadoTarjeta(x, 'error', duda);
    actualizarPendientes();
    if (mensaje) mostrarError(mensaje, acciones, dentro);
  }

  // ── Contexto de la vista: se toma al enviar (las vistas cambian su URL con replaceState, sin avisar) ──
  function camara() {
    let s = null;
    try { s = estadoMapa(); } catch { s = null; }
    const c = s && typeof s === 'object' ? (s.camara && typeof s.camara === 'object' ? s.camara : s) : null;
    let centro = c?.centro ?? c?.center;
    let zoom = c?.zoom;
    if (centro == null && rutaActual() === '/mapa' && window.__mapa) {
      try { centro = window.__mapa.getCenter().toArray(); zoom = window.__mapa.getZoom(); } catch { centro = null; }
    }
    let lon = null, lat = null;
    if (Array.isArray(centro) && centro.length === 2) [lon, lat] = centro;
    else if (centro && typeof centro === 'object') { lat = centro.lat; lon = centro.lon ?? centro.lng; }
    const ok = (v, lim) => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= lim;
    if (!ok(lon, 180) || !ok(lat, 90)) return null;
    const r = (v, d) => Math.round(v * 10 ** d) / 10 ** d;
    return { centro: [r(lon, 6), r(lat, 6)], zoom: ok(zoom, 24) ? r(zoom, 2) : null };
  }

  function contexto() {
    const ruta = rutaActual();
    const m = /^\/(personas|reuniones)\/(\d{1,12})$/.exec(ruta);
    return {
      ruta: ruta.slice(0, 300),
      vista: document.querySelector('#nav a[aria-current="page"]')?.dataset.nav || null,
      persona_id: m?.[1] === 'personas' ? Number(m[2]) : null,
      reunion_id: m?.[1] === 'reuniones' ? Number(m[2]) : null,
      filtros: filtrosDe(location.search),
      mapa: camara(),
    };
  }

  // ── Bienvenida, explicación y tope de mensajes ──
  function pintarBienvenida() {
    limpiarConversacion();
    conv = null;
    titulo = '';
    fijarConversacion(null, '');
    const b = el('div', 'agente-bienvenida');
    const sello = el('span', 'agente-sello grande');
    sello.setAttribute('aria-hidden', 'true');
    sello.append(ico('agente'));
    const nombre = texto(sesion.nombre || '', 80).trim().split(/\s+/)[0];
    b.append(sello, el('p', 'agente-hola', nombre ? `Hola, ${nombre}.` : 'Hola.'));
    const partes = ['Pregúnteme por la base, el mapa, las reuniones o su trabajo.'];
    partes.push(info?.escritura ? 'Antes de guardar algo le muestro exactamente qué voy a cambiar, para que lo apruebe.'
      : 'En este panel solo consulto: no escribo en la base.');
    if (info?.mnemo.activo) partes.push('También tengo a mano su espacio de Mnemo.');
    b.append(el('p', 'agente-intro', partes.join(' ')));
    if (info?.sugerencias.length) {
      const ss = el('div', 'agente-sugerencias');
      ss.setAttribute('role', 'group');
      ss.setAttribute('aria-label', 'Sugerencias');
      for (const s of info.sugerencias) {
        const btn = el('button', 'agente-sugerencia', s);
        btn.type = 'button';
        btn.addEventListener('click', () => enviar(s));
        ss.append(btn);
      }
      b.append(ss);
    }
    log.append(b);
  }

  /** Por qué no hay modelo, según la conexión con Mnemo: `caida`, `sin_modelo` (conectada sin permiso para usar sus
   * modelos) o `sin_conectar` (también si no se sabe). */
  function faltaDeModelo() {
    const c = info?.conexion;
    if (c?.estado === 'caida') return 'caida';
    return c?.estado === 'conectada' && !c.modelo ? 'sin_modelo' : 'sin_conectar';
  }

  function pintarExplicacion() {
    const sinModelo = info?.motivo === 'sin_configurar';
    const falta = sinModelo ? faltaDeModelo() : null;
    const clave = sinModelo ? `sin_configurar:${falta}:${info?.conexion?.motivo || ''}` : info?.motivo || 'otro';
    if (log.dataset.explicacion === clave) return;
    limpiarConversacion();
    log.dataset.explicacion = clave;
    sub.textContent = sub.title = !sinModelo ? 'Apagado para su rol'
      : { caida: 'Conexión caída', sin_modelo: 'Sin permiso para usar los modelos' }[falta] || 'Sin conectar';
    const b = el('div', 'agente-explicacion');
    // «Ajustes → Asistente» enlaza a Ajustes para el administrador (quien conecta); para los demás es solo texto
    const ajustes = () => {
      const d = info?.esAdmin ? destinoEnlace('/ajustes', op) : null;
      return d ? Object.assign(crearEnlace(d), { textContent: 'Ajustes → Asistente' }) : 'Ajustes → Asistente';
    };
    if (sinModelo && falta === 'caida') {
      b.append(el('h3', null, 'Se cortó la conexión con Mnemo'));
      const motivo = CAIDA_MNEMO[info.conexion.motivo];
      b.append(el('p', null, 'El asistente usa los modelos de la cuenta de Mnemo conectada al panel, y esa conexión dejó '
        + `de valer.${motivo ? ` ${motivo}` : ''}`));
      const p = el('p');
      p.append('El administrador la vuelve a conectar en ', ajustes(),
        ': inicia sesión en Mnemo y da permiso; no hay que copiar claves.');
      b.append(p);
    } else if (sinModelo && falta === 'sin_modelo') {
      b.append(el('h3', null, 'Mnemo está conectado sin permiso para usar sus modelos'));
      const p = el('p');
      p.append('Vuelva a conectar en ', ajustes(), ' y, en la página de permisos de Mnemo, marque la casilla «Usar tus '
        + 'modelos de IA y tus créditos».');
      b.append(p);
    } else if (sinModelo) {
      b.append(el('h3', null, 'El asistente no está conectado'));
      const p = el('p');
      p.append('El asistente usa los modelos de su cuenta de Mnemo. El administrador lo conecta en ', ajustes(),
        ': inicia sesión en Mnemo y da permiso; no hay que copiar claves.');
      b.append(p);
    } else {
      b.append(el('h3', null, 'El asistente está apagado para su rol'));
      const p = el('p');
      const enlace = destinoEnlace('/ajustes', op);
      p.append('Puede encenderlo para cada rol en ');
      if (enlace) p.append(Object.assign(crearEnlace(enlace), { textContent: 'Ajustes' }));
      else p.append('Ajustes');
      p.append(', en la sección del asistente.');
      b.append(p);
    }
    log.append(b);
    form.hidden = true;
  }

  function pintarRestantes() {
    const { usados, maximo } = info?.limite || {};
    if (!info?.disponible || usados == null || !maximo) { restantes.textContent = ''; return; }
    const quedan = Math.max(0, maximo - usados);
    restantes.textContent = quedan === 0 ? 'Llegó al tope de mensajes de hoy'
      : quedan === 1 ? 'Le queda 1 mensaje hoy' : `Le quedan ${num(quedan)} mensajes hoy`;
    restantes.classList.toggle('poco', quedan <= Math.max(3, Math.round(maximo * 0.1)));
  }

  // ── Conversaciones anteriores ──
  function nuevaConversacion() {
    if (turno) return;
    if (historialAbierto) verHistorial(false);
    pintarBienvenida();
    entrada.focus({ preventScroll: true });
  }

  async function verHistorial(si) {
    historialAbierto = si;
    historial.hidden = !si;
    cuerpo.hidden = si;
    form.hidden = si || !info?.disponible;
    bajarBtn.hidden = true;
    verHistBtn.setAttribute('aria-expanded', String(si));
    if (!si) { alFinal(true); return; }
    listaHist.replaceChildren(el('li', 'agente-cargando', 'Cargando…'));
    let d;
    try {
      d = await api.get('/api/agente/conversaciones');
    } catch (e) {
      if (!historialAbierto) return;
      const li = el('li', 'agente-vacio');
      li.append(el('span', null, explicar(e)));
      const b = el('button', 'btn chico', 'Reintentar');
      b.type = 'button';
      b.addEventListener('click', () => verHistorial(true));
      li.append(b);
      listaHist.replaceChildren(li);
      return;
    }
    if (!historialAbierto) return;
    const filas = (Array.isArray(d?.conversaciones) ? d.conversaciones : [])
      .filter((c) => c && Number.isInteger(c.id) && c.id > 0).slice(0, 50);
    listaHist.replaceChildren(...(filas.length ? filas.map(filaHistorial) : [sinConversaciones()]));
    (listaHist.querySelector('button') || volverBtn).focus({ preventScroll: true });
  }

  const sinConversaciones = () => el('li', 'agente-vacio', 'Todavía no tiene conversaciones con el asistente.');

  function filaHistorial(c) {
    const li = el('li', 'agente-item');
    if (c.id === conv) li.dataset.actual = '';
    const abrirB = el('button', 'agente-abrir');
    abrirB.type = 'button';
    const t = texto(c.titulo, 120) || 'Conversación';
    abrirB.append(el('b', null, t));
    const meta = el('small', null, c.actualizada ? fecha(texto(c.actualizada, 40), true) : '');
    if (c.pendiente) meta.append(el('span', 'chip ambar', 'Espera aprobación'));
    abrirB.append(meta);
    abrirB.addEventListener('click', () => abrirConversacion(c.id));
    const borrar = el('button', 'btn fantasma chico agente-icono agente-borrar');
    borrar.type = 'button';
    borrar.setAttribute('aria-label', `Borrar la conversación «${t}»`);
    borrar.title = 'Borrar';
    borrar.append(ico('basura'));
    borrar.addEventListener('click', () => borrarConversacion(c.id, li));
    li.append(abrirB, borrar);
    return li;
  }

  async function borrarConversacion(id, li) {
    const si = await preguntar('¿Borrar esta conversación? Se borra con sus mensajes y no se puede deshacer.',
      { si: 'Borrar', peligro: true });
    if (!si) return;
    try {
      await api.del(`/api/agente/conversaciones/${id}`);
    } catch (e) {
      if (!(e instanceof ErrorApi && e.estado === 404)) {
        li.querySelector('.agente-error-fila')?.remove();
        li.append(el('small', 'agente-error-fila', explicar(e)));
        return;
      }
    }
    li.remove();
    if (!listaHist.children.length) listaHist.append(sinConversaciones());
    if (id === conv) { pintarBienvenida(); guardar(); }
    (listaHist.querySelector('button') || volverBtn).focus({ preventScroll: true });
  }

  async function abrirConversacion(id, { silencioso = false } = {}) {
    if (turno || cargando) return;
    if (historialAbierto) verHistorial(false);
    limpiarConversacion();
    log.append(el('p', 'agente-cargando', 'Cargando la conversación…'));
    const esta = vez;
    let d;
    cargando = true;
    try {
      d = await api.get(`/api/agente/conversaciones/${id}`);
    } catch (e) {
      if (esta !== vez) return; // mientras tanto se pidió otra (o una nueva)
      cargando = false;
      if (e instanceof ErrorApi && e.estado === 404) {
        pintarBienvenida();
        if (!silencioso) nota('Esa conversación ya no existe: se borró o venció.', 'info', { dentro: log });
        return;
      }
      limpiarConversacion();
      conv = id;
      const acciones = [['Reintentar', () => abrirConversacion(id)], ['Nueva conversación', () => nuevaConversacion()]];
      mostrarError(explicar(e), acciones, log);
      return;
    }
    if (esta !== vez) return;
    cargando = false;
    pintarConversacion(d);
    if (!silencioso) entrada.focus({ preventScroll: true });
  }

  function pintarConversacion(d) {
    limpiarConversacion();
    fijarConversacion(Number.isInteger(d?.id) ? d.id : null, d?.titulo);
    for (const m of Array.isArray(d?.mensajes) ? d.mensajes : []) {
      if (m?.rol === 'usuario' && texto(m.texto)) { agregarUsuario(texto(m.texto)); continue; }
      if (m?.rol !== 'asistente' || !Array.isArray(m.partes)) continue;
      nuevoAsistente();
      for (const p of m.partes) {
        if (!p || typeof p !== 'object') continue;
        if (p.tipo === 'texto' && texto(p.texto, 100000)) {
          const pt = parte('texto');
          pt.fuente += texto(p.texto, 100000);
          sucias.add(pt);
        } else if (p.tipo === 'progreso' && texto(p.texto)) {
          parte('progreso').nodo.appendData(texto(p.texto));
        } else if (p.tipo === 'herramienta') {
          alHerramienta({ ...p, estado: ESTADOS.has(p.estado) && p.estado !== 'inicio' ? p.estado : 'error' });
        } else if (p.tipo === 'aviso') {
          nota(texto(p.texto, 600), p.nivel === 'alerta' ? 'alerta' : 'info');
        }
      }
    }
    for (const p of Array.isArray(d?.pendientes) ? d.pendientes : []) if (p && typeof p === 'object') alConfirmar(p);
    nuevaRonda();
    vaciar();
    alFinal(true);
    if (!log.children.length) pintarBienvenida();
  }

  // ── Eventos ──
  boton.addEventListener('click', () => abrir());
  cerrarBtn.addEventListener('click', () => cerrar({ foco: true }));
  nuevaBtn.addEventListener('click', () => nuevaConversacion());
  verHistBtn.addEventListener('click', () => verHistorial(!historialAbierto));
  volverBtn.addEventListener('click', () => { verHistorial(false); entrada.focus({ preventScroll: true }); });
  detenerBtn.addEventListener('click', () => {
    if (!turno) return;
    detenidoEn = Date.now();
    turno.control.abort();
  });

  function enviarDelCompositor() {
    const t = entrada.value;
    if (!t.trim() || turno) return;
    entrada.value = '';
    autoAltura();
    enviar(t);
  }
  form.addEventListener('submit', (e) => { e.preventDefault(); enviarDelCompositor(); });
  entrada.addEventListener('keydown', (e) => {
    // Enter envía; Mayús+Enter es otra línea. Mientras se compone un carácter (teclados con acentos o IME), no
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      enviarDelCompositor();
    }
  });
  function autoAltura() {
    entrada.style.height = 'auto';
    entrada.style.height = `${Math.min(entrada.scrollHeight + 2, 160)}px`;
  }
  entrada.addEventListener('input', autoAltura);

  panel.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || e.isComposing || document.querySelector('dialog[open]')) return;
    e.preventDefault();
    if (historialAbierto) { verHistorial(false); verHistBtn.focus({ preventScroll: true }); } else cerrar({ foco: true });
  });

  // Un enlace del panel dentro de la conversación: en el celular se pliega para que se vea la vista que abre
  log.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-ruta]');
    if (a && !e.metaKey && !e.ctrlKey && !e.shiftKey) plegar();
  });

  // Al terminar de pintar una vista (app.js): el foco vuelve al cuadro si la abrió el asistente; en el celular, una
  // vista nueva pliega el panel (la persona eligió otra cosa en el menú)
  window.addEventListener('vista', (e) => {
    const ruta = typeof e.detail?.ruta === 'string' ? e.detail.ruta : rutaActual();
    if (devolverFoco && abierto && !esMovil()) entrada.focus({ preventScroll: true });
    devolverFoco = false;
    if (ruta !== ultimaRuta) plegar();
    ultimaRuta = ruta;
  });

  // El teclado del celular achica la ventana visible: el panel sube con él para que el cuadro de texto se vea
  const vv = window.visualViewport;
  function ajustarTeclado() {
    if (!vv || !abierto || !esMovil()) { panel.style.removeProperty('--teclado'); return; }
    const teclado = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
    panel.style.setProperty('--teclado', `${teclado}px`);
  }
  vv?.addEventListener('resize', ajustarTeclado);
  vv?.addEventListener('scroll', ajustarTeclado);

  montado = { mostrar, ocultar };
  return montado;
}
