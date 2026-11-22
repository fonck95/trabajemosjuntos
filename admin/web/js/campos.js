// Campos que se usan igual en cualquier celular, tableta o computador, con cualquier sistema operativo:
//
// 1. Fechas y horas que se ESCRIBEN. El `<input type="date">` de cada navegador tiene su formato (mm/dd/aaaa en un
//    teléfono en inglés, ruedas en el iPhone, un calendario en Android que obliga a pasar mes por mes hasta 1960 para
//    una fecha de nacimiento). Aquí la fecha se escribe como dd/mm/aaaa con el teclado numérico (las barras se ponen
//    solas) y la hora como hh:mm de 24 horas; el calendario o el reloj del sistema siguen a un toque, en el botón de
//    al lado. El campo de siempre queda dentro, con su nombre y su valor ISO (aaaa-mm-dd, hh:mm): lo que lee,
//    escribe y envía cada vista no cambia.
// 2. Listas cortas como opciones para tocar. En el celular (y en pantallas táctiles) una lista desplegable de 2 a 15
//    opciones tapa media pantalla y pide dos toques; se cambia por chips a la vista, que se eligen con uno. La lista
//    sigue en el formulario, escondida, y es la que manda: sus oyentes, su valor y su envío son los mismos. En el
//    computador con ratón se ve la lista de siempre.
//
// Se aplica solo a lo que se pinta (un MutationObserver), sin tocar las vistas. Para dejar un campo como estaba:
// `data-nativo` en una fecha u hora, `data-lista` en una lista (los menús de acción, como «Usar vereda…»). En una lista:
// - `data-vacio="Texto"` muestra la opción vacía como un chip más (cuando significa algo, como «Vigentes»). Sin él, una
//   opción vacía como «—», «Seleccione» o el nombre del filtro es el «sin elegir»: no lleva chip y se vuelve a ella
//   tocando otra vez la opción elegida. Así un filtro de una sola opción («Sin dirección») es un chip que se prende y
//   se apaga.
// - `data-chip-corto` pone en cada chip el valor de la opción y no su texto (CC, TI, CE… con el nombre completo al
//   pasar el dedo o el lector de pantalla), para listas de nombres largos que todos conocen por su sigla.
import { fechaMalEscrita, html, icono } from './ui.js';

/** Celular o pantalla táctil: la misma frontera de 900 px de app.css, o un dedo como puntero. */
export const MEDIA_CHIPS = '(max-width: 900px), (pointer: coarse)';
/** Las listas que pasan a chips: ni una sola opción ni más de quince. */
export const MIN_CHIPS = 2;
export const MAX_CHIPS = 15;

const DOS = (n) => String(n).padStart(2, '0');
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
let serie = 0;
const nuevoId = (prefijo) => `${prefijo}-${++serie}`;

// ───────────────────────────── Fechas ─────────────────────────────

/** ¿Existe el día? (29 de febrero solo en bisiesto) */
const existe = (a, m, d) => m >= 1 && m <= 12 && d >= 1 && d <= new Date(Date.UTC(a, m, 0)).getUTCDate();
const isoDe = (a, m, d) => `${String(a).padStart(4, '0')}-${DOS(m)}-${DOS(d)}`;
const esIso = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v || '') && existe(+v.slice(0, 4), +v.slice(5, 7), +v.slice(8, 10));

/** «1985-03-07» → «07/03/1985»; '' si no es una fecha ISO válida. */
export function fechaEscrita(iso) {
  return esIso(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
}

function hoyIso() {
  const d = new Date();
  return isoDe(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

/** Año de dos cifras: si solo un siglo deja la fecha dentro de [min, max], ese («85» en una fecha de nacimiento, que
 * no puede ser futura, es 1985); si no, este siglo mientras no pase de dentro de diez años («27» es 2027). */
function siglo(aa, m, d, min, max) {
  const dentro = [1900 + aa, 2000 + aa].filter((a) => {
    const iso = isoDe(a, m, d);
    return (!min || iso >= min) && (!max || iso <= max);
  });
  if (dentro.length === 1) return dentro[0];
  return 2000 + aa <= new Date().getFullYear() + 10 ? 2000 + aa : 1900 + aa;
}

/**
 * Lee lo escrito en un campo de fecha: «7/3/1985», «07031985», «7-3-85», «07.03.1985» o «1985-03-07» (pegado).
 * Devuelve {iso} si es una fecha válida dentro de [min, max] (aaaa-mm-dd), {error} si no, o {} si está vacío.
 */
export function leerFecha(texto, { min = '', max = '' } = {}) {
  const t = String(texto ?? '').trim();
  if (!t) return {};
  let a, m, d, x;
  if ((x = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(t))) [a, m, d] = [+x[1], +x[2], +x[3]];
  else if ((x = /^(\d{1,2})[\s/.-]+(\d{1,2})[\s/.-]+(\d{4}|\d{2})$/.exec(t)) || (x = /^(\d{2})(\d{2})(\d{4}|\d{2})$/.exec(t))) {
    [d, m] = [+x[1], +x[2]];
    a = x[3].length === 2 ? siglo(+x[3], m, d, min, max) : +x[3];
  } else {
    return { error: 'Escriba la fecha como dd/mm/aaaa, por ejemplo 07/03/1985.' };
  }
  if (m < 1 || m > 12) return { error: `El mes va de 01 a 12 (escribió ${DOS(m)}).` };
  if (!existe(a, m, d)) return { error: d < 1 ? 'El día va desde 01.' : `El ${d} de ${MESES[m - 1]} de ${a} no existe.` };
  if (a < 1900) return { error: 'Revise el año: es anterior a 1900.' };
  if (a > new Date().getFullYear() + 100) return { error: 'Revise el año (dd/mm/aaaa).' };
  const iso = isoDe(a, m, d);
  const hoy = hoyIso();
  if (min && iso < min) return { error: min === hoy ? 'La fecha no puede ser antes de hoy.' : `La fecha debe ser desde el ${fechaEscrita(min) || min}.` };
  if (max && iso > max) return { error: max === hoy ? 'La fecha no puede ser después de hoy.' : `La fecha debe ser hasta el ${fechaEscrita(max) || max}.` };
  return { iso };
}

/**
 * Lo que se va escribiendo en una fecha, con las barras puestas: «0» «7» → «07/», «7» → «07/» (ningún día empieza
 * por 4 o más), «07/3» → «07/03/». Respeta las barras, guiones, puntos o espacios que escriba la persona («7/3/» →
 * «07/03/»). Una fecha pegada con el año primero («1985-03-07», «1985/03/07») pasa a «07/03/1985».
 */
export function enmascararFecha(texto) {
  const t = String(texto ?? '');
  const pegado = /^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s*$/.exec(t);
  if (pegado) return `${DOS(pegado[3])}/${DOS(pegado[2])}/${pegado[1]}`;
  // El año primero, a medio pegar o escribir («1985/03»): no se le ponen barras de día y mes; se lee al salir del campo
  if (/^\s*\d{3,}[-/.]/.test(t)) return t;
  const partes = [];
  let actual = '';
  for (const c of t) {
    if (c >= '0' && c <= '9') {
      if (partes.length === 2) {
        if (actual.length < 4) actual += c;
        continue;
      }
      actual += c;
      // Un día que empieza por 4 o más y un mes que empieza por 2 o más ya están completos
      if (actual.length === 1 && +c > (partes.length === 0 ? 3 : 1)) actual = '0' + c;
      if (actual.length === 2) { partes.push(actual); actual = ''; }
    } else if ('/-. '.includes(c) && actual && partes.length < 2) {
      partes.push(actual.padStart(2, '0'));
      actual = '';
    }
  }
  if (partes.length === 2) return `${partes[0]}/${partes[1]}/${actual}`;
  return partes.length ? `${partes[0]}/${actual}` : actual;
}

/** ¿Ya está escrita la fecha entera, mientras se escribe? Solo dd/mm/aaaa con todas sus cifras (u ocho cifras): «07/03/19»
 * todavía puede ser 1985 y «1/10/2026» puede ser el comienzo de 13/10/2026. Lo demás se lee al salir del campo. */
const fechaCompleta = (t) => /^\s*(\d{2}\/\d{2}\/\d{4}|\d{8}|\d{4}-\d{2}-\d{2})\s*$/.test(t);

// ───────────────────────────── Horas ─────────────────────────────

/** ¿Es una hora hh:mm de 24 horas? */
const esHora = (v) => /^([01]\d|2[0-3]):[0-5]\d$/.test(v || '');

/**
 * Lee una hora escrita: «15:30», «1530», «9:30», «930», «9», «3:30 pm», «3.30 p. m.», «12 am».
 * Devuelve {valor: 'hh:mm'} (24 horas), {error} o {} si está vacía.
 */
export function leerHora(texto, { min = '', max = '' } = {}) {
  // «09:» (lo que deja la máscara al escribir «9») es 09:00, y «03:pm» (al escribir «3pm») es 3 p. m.
  const t = String(texto ?? '').trim().toLowerCase().replace(/\s*[:.h]$/, '').replace(/(\d)\s*[:.h]\s*(?=[ap])/, '$1');
  if (!t) return {};
  const x = /^(\d{1,2})(?:\s*[:.h]\s*(\d{2})|(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?)?$/.exec(t);
  if (!x) return { error: 'Escriba la hora como hh:mm, por ejemplo 15:30.' };
  let h = +x[1];
  const mi = +(x[2] ?? x[3] ?? 0);
  const sufijo = x[4]?.[0];
  if (sufijo) {
    if (h < 1 || h > 12) return { error: 'Con a. m. o p. m. la hora va de 1 a 12.' };
    h = (h % 12) + (sufijo === 'p' ? 12 : 0);
  }
  if (h > 23 || mi > 59) return { error: 'Revise la hora: va de 00:00 a 23:59.' };
  const valor = `${DOS(h)}:${DOS(mi)}`;
  if (min && valor < min) return { error: `La hora debe ser desde las ${min}.` };
  if (max && valor > max) return { error: `La hora debe ser hasta las ${max}.` };
  return { valor };
}

/** Lo que se va escribiendo en una hora, con los dos puntos: «9» → «09:», «15» → «15:», «153» → «15:3». */
export function enmascararHora(texto) {
  const t = String(texto ?? '');
  // Con letras (a. m., p. m.) se respeta lo escrito y se lee al salir del campo
  if (/[a-z]/i.test(t)) return t;
  let h = '', m = '', enMinutos = false;
  for (const c of t) {
    if (c >= '0' && c <= '9') {
      if (!enMinutos) {
        h += c;
        if (h.length === 1 && +c > 2) h = '0' + c;
        if (h.length === 2) enMinutos = true;
      } else if (m.length < 2) m += c;
    } else if (':.h'.includes(c) && h && !enMinutos) {
      h = h.padStart(2, '0');
      enMinutos = true;
    }
  }
  return enMinutos ? `${h}:${m}` : h;
}

/** ¿Ya está escrita la hora entera, mientras se escribe? («15:30», «1530»; «9», «9:30» o «15:3» se leen al salir) */
const horaCompleta = (t) => /^\s*(\d{2}:\d{2}|\d{4})\s*$/.test(t);

// ───────────────────────────── El campo escrito ─────────────────────────────

/** El texto de un título de campo sin lo que lo decora: la insignia de la fuente («T», «B»), «por cruce», un asterisco
 * escondido. Para nombrar lo que se crea al lado (el calendario, los chips). */
function textoTitulo(el) {
  if (!el) return '';
  const copia = el.cloneNode(true);
  for (const x of copia.querySelectorAll('.fuente, .fuentes, [role="img"], [aria-hidden="true"], .marca-cruce, .sr')) x.remove();
  return copia.textContent.replace(/\s+/g, ' ').trim();
}

const TIPOS = {
  date: {
    clase: 'fecha', marcador: 'dd/mm/aaaa', ayuda: 'día, mes y año', largo: 14, icono: 'reuniones', abrir: 'Elegir en el calendario',
    mostrar: fechaEscrita, enmascarar: enmascararFecha, completa: fechaCompleta,
    leer: (t, x) => { const r = leerFecha(t, x); return r.iso != null ? { valor: r.iso } : r; },
  },
  time: {
    clase: 'hora', marcador: 'hh:mm', ayuda: 'hora y minutos, de 00:00 a 23:59', largo: 11, icono: 'reloj', abrir: 'Elegir en el reloj',
    mostrar: (v) => (esHora(v) ? v : ''), enmascarar: enmascararHora, completa: horaCompleta, leer: leerHora,
  },
};
const VALOR = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

/**
 * Convierte un `<input type="date">` o `type="time"` en el campo escrito. El original queda dentro, encima del ícono
 * del calendario y transparente: un toque en el ícono es un toque en él, que abre el selector del sistema en cualquier
 * celular; en el computador, `showPicker()` lo abre igual. Su valor, sus oyentes y su nombre no cambian.
 */
export function mejorarFecha(original) {
  const tipo = TIPOS[original.type];
  if (!tipo || original.dataset.escrita != null || original.dataset.nativo != null) return;
  original.dataset.escrita = '';
  // Un div y no un span: `.campo > span` es el título del campo (letra chica y gris)
  const caja = document.createElement('div');
  caja.className = `campo-escrito campo-${tipo.clase}`;
  // El estilo en línea del campo (un ancho) es de la caja: el original pasa a ser el botón del calendario
  if (original.getAttribute('style')) { caja.setAttribute('style', original.getAttribute('style')); original.removeAttribute('style'); }
  const texto = document.createElement('input');
  texto.type = 'text';
  texto.inputMode = 'numeric';
  texto.autocomplete = 'off';
  texto.placeholder = tipo.marcador;
  texto.maxLength = tipo.largo;
  // Ancho natural para lo que cabe (dd/mm/aaaa, hh:mm): en una fila con `width:auto` no ocupa media pantalla
  texto.size = tipo.clase === 'fecha' ? 11 : 6;
  texto.spellcheck = false;
  texto.className = original.className;
  // Su nombre es el del campo (el título de la etiqueta o su aria-label), sin el formato, el calendario ni el error, que
  // van en aria-describedby: la etiqueta envuelve todo y, sin esto, el lector los leería como parte del nombre
  const etiqueta = original.closest('label');
  const tituloEl = etiqueta?.querySelector(':scope > span, :scope > .titulo-campo');
  const nombre = original.getAttribute('aria-label') || textoTitulo(tituloEl);
  if (original.getAttribute('aria-label')) texto.setAttribute('aria-label', original.getAttribute('aria-label'));
  else if (tituloEl) {
    tituloEl.id ||= nuevoId('titulo');
    texto.setAttribute('aria-labelledby', tituloEl.id);
  }
  const formato = document.createElement('span');
  formato.className = 'sr';
  formato.id = nuevoId('formato');
  formato.textContent = `Formato ${tipo.marcador}: ${tipo.ayuda}.`;
  const icon = document.createElement('span');
  icon.className = 'campo-escrito-icono';
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = String(html`${icono(tipo.icono)}`);
  const error = document.createElement('small');
  error.className = 'campo-escrito-error';
  error.id = nuevoId('error');
  error.setAttribute('aria-live', 'polite');
  error.hidden = true;

  original.replaceWith(caja);
  caja.append(texto, formato, icon, original, error);
  original.classList.add('campo-escrito-sistema');
  original.tabIndex = -1;
  original.setAttribute('aria-label', nombre ? `${nombre}: ${tipo.abrir.toLowerCase()}` : tipo.abrir);
  original.title = tipo.abrir;
  texto.setAttribute('aria-describedby', formato.id);

  // El valor que trae: un dato guardado que no es una fecha (1985-02-30) se ve vacío, como en el campo del navegador
  texto.value = texto.defaultValue = tipo.mostrar(VALOR.get.call(original));

  let propio = false; // los eventos que manda este campo no lo vuelven a pintar
  let confirmado = VALOR.get.call(original);
  const avisar = (tipoEvento) => {
    propio = true;
    try { original.dispatchEvent(new Event(tipoEvento, { bubbles: true })); } finally { propio = false; }
  };
  /** Fija el valor del original y avisa como lo haría el navegador: `input` en cada cambio, `change` al confirmarlo. */
  const fijar = (valor, confirmar) => {
    if (VALOR.get.call(original) !== valor) { VALOR.set.call(original, valor); avisar('input'); }
    if (confirmar && confirmado !== valor) { confirmado = valor; avisar('change'); }
  };
  const mostrarError = (msg) => {
    caja.classList.toggle('invalido', !!msg);
    if (msg) texto.setAttribute('aria-invalid', 'true'); else texto.removeAttribute('aria-invalid');
    error.textContent = msg || '';
    error.hidden = !msg;
    texto.setAttribute('aria-describedby', msg ? `${error.id} ${formato.id}` : formato.id);
  };
  /**
   * Lee el texto. `salir` es el final (perder el foco, Enter): ahí lo incompleto es un error y el texto se ordena.
   * Mientras se escribe, solo una fecha entera con el cursor al final es un cambio (corregir el día en medio no lo es).
   */
  const revisar = (salir = false, alFinal = true) => {
    const t = texto.value;
    if (!t.trim()) {
      texto.setCustomValidity('');
      mostrarError('');
      fijar('', salir);
      return;
    }
    const r = salir || (alFinal && tipo.completa(t)) ? tipo.leer(t, { min: original.min || '', max: original.max || '' }) : null;
    if (r?.valor != null) {
      texto.setCustomValidity('');
      mostrarError('');
      if (salir) texto.value = tipo.mostrar(r.valor);
      // Completa y válida es un cambio confirmado: los filtros y la edad responden sin esperar a salir del campo
      fijar(r.valor, true);
      return;
    }
    // A medio escribir no se muestra error todavía, pero el formulario no se envía así
    const msg = r?.error || `Complete la ${tipo.clase === 'fecha' ? 'fecha' : 'hora'} (${tipo.marcador}).`;
    texto.setCustomValidity(msg);
    mostrarError(r ? msg : '');
    fijar('', salir);
  };
  const pintar = () => {
    const v = VALOR.get.call(original);
    confirmado = v;
    texto.value = tipo.mostrar(v);
    texto.setCustomValidity('');
    mostrarError('');
  };

  texto.addEventListener('input', (e) => {
    // Al borrar no se reacomoda nada (la persona borra lo que quiere, también una barra); en medio del texto tampoco
    const alFinal = texto.selectionStart === texto.value.length;
    if (alFinal && !String(e.inputType || '').startsWith('delete')) {
      const nuevo = tipo.enmascarar(texto.value);
      if (nuevo !== texto.value) texto.value = nuevo;
    }
    revisar(false, alFinal);
  });
  texto.addEventListener('blur', () => revisar(true));
  texto.addEventListener('keydown', (e) => { if (e.key === 'Enter') revisar(true); });
  // Su propio 'change' (al salir con el texto cambiado) no sale: el del campo de siempre ya avisó, y dos harían dos
  // recargas en los filtros que oyen el formulario entero
  texto.addEventListener('change', (e) => e.stopPropagation());
  // El selector del sistema, o un cambio en el campo original que no hizo este
  const delSistema = () => { if (!propio) pintar(); };
  original.addEventListener('input', delSistema);
  original.addEventListener('change', delSistema);
  original.addEventListener('click', () => {
    if (original.disabled || original.readOnly) return;
    try { original.showPicker?.(); } catch { /* el navegador ya lo abrió por su cuenta o no lo permite aquí */ }
  });
  // Tras tocar el ícono el foco queda en el campo del sistema, que no se ve y ordena las cifras a su manera (mm/dd/aaaa
  // en un navegador en inglés): lo que se escriba va al campo escrito, al final
  original.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || !(e.key.length === 1 || e.key === 'Backspace')) return;
    e.preventDefault();
    texto.focus();
    const fin = texto.value.length;
    if (e.key === 'Backspace') texto.setRangeText('', Math.max(0, fin - 1), fin, 'end');
    else texto.setRangeText(e.key, fin, fin, 'end');
    texto.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: e.key === 'Backspace' ? 'deleteContentBackward' : 'insertText', data: e.key }));
  });
  // Quien fije el valor desde el código (volver a pintar lo no guardado, limpiar filtros) lo ve escrito
  Object.defineProperty(original, 'value', {
    configurable: true,
    get() { return VALOR.get.call(this); },
    set(v) { VALOR.set.call(this, v); pintar(); },
  });
  // Quien le pida el foco (el primer campo de un formulario, un error) lo recibe en el campo que se escribe
  original.focus = (op) => texto.focus(op);
  // Lo que se le cambie al original (deshabilitarlo, hacerlo obligatorio, esconderlo) vale también para el escrito
  const reflejar = () => {
    texto.disabled = original.disabled;
    texto.readOnly = original.readOnly;
    texto.required = original.required;
    caja.hidden = original.hidden;
  };
  reflejar();
  new MutationObserver(reflejar).observe(original, { attributes: true, attributeFilter: ['disabled', 'readonly', 'required', 'hidden'] });
  const form = original.form;
  form?.addEventListener('reset', () => setTimeout(pintar));
  vigilarEnvio(form);
}

/**
 * Un formulario que se envía con una fecha mal escrita la perdería en silencio (el campo original queda vacío). Con
 * `novalidate` el navegador no lo detiene: se detiene aquí, antes de que lo atienda la vista, y se dice qué falta. Las
 * vistas que guardan con un clic, sin submit (Completar, el acercamiento), llaman a `fechaMalEscrita` de ui.js.
 */
const vigilados = new WeakSet();
function vigilarEnvio(form) {
  if (!form || vigilados.has(form)) return;
  vigilados.add(form);
  form.addEventListener('submit', (e) => {
    if (!fechaMalEscrita(form)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
  }, true);
}

// ───────────────────────────── Listas como chips ─────────────────────────────

const OPCION_VACIA = /^[\s—–\-·.…]*$|^(selecci|elij|elig|eleg|escoj|sin cambio$)/i;
const VALOR_LISTA = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
const INDICE_LISTA = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
const plano = (t) => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();

/** El nombre de una lista: su `aria-label`, o el título de la etiqueta que la envuelve. */
function nombreLista(sel) {
  const propio = sel.getAttribute('aria-label') || sel.title;
  if (propio) return propio;
  const etiqueta = sel.closest('label') || sel.labels?.[0];
  return textoTitulo(etiqueta?.querySelector(':scope > span, :scope > .titulo-campo'));
}

/** ¿La opción vacía es un chip («Lo tiene», «Automática») o solo el «sin elegir» («—», «Seleccione», el nombre del
 * filtro)? En una barra de filtros es el nombre del filtro: no lleva chip salvo con `data-vacio`. */
function vaciaEsChip(sel, op) {
  if (sel.dataset.vacio != null) return true;
  if (sel.closest('.filtros')) return false;
  const texto = op.textContent.trim();
  return !OPCION_VACIA.test(texto) && plano(texto) !== plano(nombreLista(sel));
}

/** ¿Tiene una opción vacía que es el «sin elegir»? (se vuelve a ella tocando otra vez la elegida) */
const conSinElegir = (sel) => !sel.required && [...sel.options].some((o) => o.value === '' && !vaciaEsChip(sel, o));

/** Las opciones que serían chips, o null si la lista se queda como lista. Con un «sin elegir», una sola opción basta:
 * es un chip que se prende y se apaga («Sin dirección»). */
function opcionesChips(sel) {
  if (sel.multiple || sel.size > 1 || sel.dataset.lista != null || sel.querySelector('optgroup')) return null;
  const chips = [...sel.options].filter((o) => !o.hidden && (o.value !== '' || vaciaEsChip(sel, o)));
  const minimo = conSinElegir(sel) ? 1 : MIN_CHIPS;
  return chips.length >= minimo && chips.length <= MAX_CHIPS ? chips : null;
}

const enModoChips = () => document.documentElement.classList.contains('modo-chips');

/** Lo de cada lista vigilada: su grupo de chips (solo en el modo de chips) y la firma de lo que se pintó. */
const LISTAS = new WeakMap();

/**
 * Vigila una lista para mostrarla, en el modo de chips (celular o pantalla táctil) y mientras tenga de 1 a 15
 * opciones, como chips (radios, o botones que se prenden y se apagan si la lista tiene un «sin elegir») puestos detrás de ella. La lista no se toca: los chips fijan su valor y le
 * mandan `input` y `change`, como si la persona la hubiera usado, y la siguen si cambia (también desde el código). En
 * el computador con ratón no se crea nada: la página es la de siempre.
 */
export function mejorarLista(sel) {
  if (sel.dataset.lista != null || LISTAS.has(sel)) return;
  LISTAS.set(sel, { grupo: null, caja: null, titulo: null, firma: null });
  const pintar = () => pintarLista(sel);
  // La lista sigue siendo la fuente: lo que le cambien la vista o la persona se ve en los chips
  sel.addEventListener('change', pintar);
  sel.addEventListener('input', pintar);
  for (const [prop, d] of [['value', VALOR_LISTA], ['selectedIndex', INDICE_LISTA]]) {
    Object.defineProperty(sel, prop, {
      configurable: true,
      get() { return d.get.call(this); },
      set(v) { d.set.call(this, v); pintar(); },
    });
  }
  // Opciones que llegan después (las necesidades y las listas del mapa), que se van o que cambian de texto
  new MutationObserver(pintar).observe(sel, { childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ['disabled', 'hidden', 'required', 'selected', 'label', 'value', 'aria-label', 'data-vacio', 'data-chip-corto'] });
  sel.form?.addEventListener('reset', () => setTimeout(pintar));
  // Escondida, una lista obligatoria sin elegir no puede mostrar su aviso: lo muestran los chips
  sel.addEventListener('invalid', () => {
    const { caja } = LISTAS.get(sel);
    if (!caja || !sel.classList.contains('con-chips')) return;
    sel.closest('label, .campo')?.classList.add('invalido');
    caja.querySelector('button:not(:disabled)')?.focus();
  });
  // Tocar el título de la etiqueta no abre la lista escondida (en el iPhone abriría su rueda)
  sel.closest('label')?.addEventListener('click', (e) => {
    if (sel.classList.contains('con-chips') && !e.target.closest('.opciones-lista')) e.preventDefault();
  });
  pintar();
}

/** Crea el grupo de chips de una lista, detrás de ella (no antes: la etiqueta que la envuelve sigue siendo suya). */
function crearGrupo(sel, est) {
  const grupo = document.createElement('div');
  grupo.className = 'opciones-lista';
  // Sin un título a la vista (una barra de filtros, donde lo hace la opción vacía), los chips llevan el suyo
  if (!(sel.closest('label') && !sel.getAttribute('aria-label')) || sel.closest('.filtros')) {
    est.titulo = document.createElement('span');
    est.titulo.className = 'opciones-titulo';
    est.titulo.setAttribute('aria-hidden', 'true');
    grupo.append(est.titulo);
  }
  const caja = document.createElement('div');
  caja.className = 'opciones-chips';
  grupo.append(caja);
  const elegir = (valor) => {
    if (VALOR_LISTA.get.call(sel) === valor) return;
    VALOR_LISTA.set.call(sel, valor);
    pintarLista(sel);
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const enfocar = (valor) => [...caja.children].find((b) => b.dataset.opcion === valor)?.focus();
  caja.addEventListener('click', (e) => {
    const b = e.target.closest('button.opcion-lista');
    if (!b || b.disabled) return;
    const v = b.dataset.opcion;
    // Tocar otra vez la elegida la quita (vuelve al «sin elegir») si la lista lo permite
    elegir(v === VALOR_LISTA.get.call(sel) && conSinElegir(sel) ? '' : v);
    sel.closest('label, .campo')?.classList.remove('invalido');
    enfocar(v);
  });
  caja.addEventListener('keydown', (e) => {
    const paso = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!paso) return;
    const botones = [...caja.querySelectorAll('button:not(:disabled)')];
    const i = botones.indexOf(document.activeElement);
    if (i < 0 || botones.length < 2) return;
    e.preventDefault();
    const otro = botones[(i + paso + botones.length) % botones.length];
    if (conSinElegir(sel)) {
      // Botones que se prenden y se apagan: la flecha lleva el foco; Enter o espacio eligen
      for (const b of botones) b.tabIndex = b === otro ? 0 : -1;
      otro.focus();
      return;
    }
    elegir(otro.dataset.opcion);
    enfocar(otro.dataset.opcion);
  });
  sel.after(grupo);
  Object.assign(est, { grupo, caja, firma: null });
}

/** Pinta los chips de una lista según su estado, o los quita si no van (computador, más de quince opciones…). */
function pintarLista(sel) {
  const est = LISTAS.get(sel);
  if (!est) return;
  const ops = enModoChips() && sel.isConnected ? opcionesChips(sel) : null;
  sel.classList.toggle('con-chips', !!ops);
  if (!ops) {
    est.grupo?.remove();
    Object.assign(est, { grupo: null, caja: null, titulo: null, firma: null });
    return;
  }
  if (!est.grupo || !est.grupo.isConnected) crearGrupo(sel, est);
  est.grupo.hidden = sel.hidden;
  const nombre = nombreLista(sel);
  est.grupo.setAttribute('aria-label', nombre);
  if (est.titulo) est.titulo.textContent = nombre;
  const vacio = sel.dataset.vacio;
  const corto = sel.dataset.chipCorto != null;
  const largoDe = (o) => (o.value === '' && vacio ? vacio : (o.label || o.textContent).trim());
  const textoDe = (o) => (corto && o.value ? o.value : largoDe(o));
  const firma = JSON.stringify([sel.disabled, corto, ...ops.map((o) => [o.value, largoDe(o), o.disabled])]);
  if (firma !== est.firma) {
    est.firma = firma;
    est.caja.replaceChildren(...ops.map((o) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip opcion-lista';
      b.dataset.opcion = o.value;
      b.textContent = textoDe(o);
      // La sigla a la vista y, para el lector y el control por voz, la sigla seguida del nombre («CC, Cédula de…»)
      if (textoDe(o) !== largoDe(o)) { b.title = largoDe(o); b.setAttribute('aria-label', `${textoDe(o)}, ${largoDe(o)}`); }
      b.disabled = sel.disabled || o.disabled;
      return b;
    }));
  }
  const valor = VALOR_LISTA.get.call(sel);
  const botones = [...est.caja.children];
  // Con un «sin elegir», la elegida se apaga tocándola otra vez: son botones que se prenden y se apagan (aria-pressed),
  // como los de «Más datos». Sin él, son radios: siempre hay una y las flechas la cambian
  const alternar = conSinElegir(sel);
  est.grupo.setAttribute('role', alternar ? 'group' : 'radiogroup');
  for (const b of botones) {
    const si = String(b.dataset.opcion === valor);
    if (alternar) { b.removeAttribute('role'); b.removeAttribute('aria-checked'); b.setAttribute('aria-pressed', si); }
    else { b.setAttribute('role', 'radio'); b.removeAttribute('aria-pressed'); b.setAttribute('aria-checked', si); }
  }
  // Un solo chip en el tabulador: el elegido o el primero (las flechas recorren los demás)
  const elegido = (b) => b.getAttribute('aria-checked') === 'true' || b.getAttribute('aria-pressed') === 'true';
  const enFoco = botones.find((b) => elegido(b) && !b.disabled) || botones.find((b) => !b.disabled);
  for (const b of botones) b.tabIndex = b === enFoco ? 0 : -1;
}

// ───────────────────────────── Arranque ─────────────────────────────

const FECHAS = 'input[type="date"], input[type="time"]';

/** Mejora los campos de `raiz` (y la raíz misma si es uno). El asistente (`#agente`) tiene sus propios controles y
 * escribe sus respuestas en vivo: no se recorre. */
export function mejorarCampos(raiz) {
  if (!raiz || raiz.nodeType !== 1 || raiz.closest('#agente')) return;
  if (raiz.matches(FECHAS)) mejorarFecha(raiz);
  else if (raiz.matches('select')) mejorarLista(raiz);
  for (const x of raiz.querySelectorAll(FECHAS)) if (!x.closest('#agente')) mejorarFecha(x);
  for (const s of raiz.querySelectorAll('select')) if (!s.closest('#agente')) mejorarLista(s);
}

/** El modo de chips sigue a la pantalla: al girar la tableta o achicar la ventana se ve la lista o los chips. */
function seguirPantalla() {
  const mq = matchMedia(MEDIA_CHIPS);
  const aplicar = () => {
    document.documentElement.classList.toggle('modo-chips', mq.matches);
    // Las listas ya pintadas ponen o quitan sus chips
    for (const sel of document.querySelectorAll('select')) pintarLista(sel);
  };
  aplicar();
  mq.addEventListener?.('change', aplicar);
}

if (typeof document !== 'undefined' && typeof MutationObserver !== 'undefined') {
  seguirPantalla();
  mejorarCampos(document.body);
  new MutationObserver((cambios) => {
    for (const c of cambios) for (const n of c.addedNodes) mejorarCampos(n);
  }).observe(document.documentElement, { childList: true, subtree: true });
}
