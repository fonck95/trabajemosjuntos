// Importación de los Excel (se procesan y se descartan; solo quedan los datos), exportación de la base única y las
// planillas físicas por foto (docs/agente.md, «Planillas físicas por foto»).
//
// Planillas por foto: la bandeja del panel (app/api/planillas.py), la misma que usa el asistente del chat. Quien tiene
// el papel toma o elige la foto de cada hoja; el navegador la reduce y la vuelve a codificar (sin EXIF ni GPS) y la
// sube cruda a POST /api/planillas/fotos, donde se lee de fondo (la bandeja se consulta cada pocos segundos mientras
// haya alguna «leyendo»). A y K abren una: la foto al lado de la grilla con los valores completos, lo dudoso y lo
// ilegible marcado (con un signo, no solo con color), las celdas se corrigen (PATCH), «Cotejar» da la vista previa
// fiel del importador por fila, y las filas elegidas se cargan con el folio del papel y el planillero; el resultado
// enlaza a la confirmación de las autorizaciones «declaradas en planilla», que sigue siendo de una persona con el
// papel. P ve sus fotos con su estado y sus filas enmascaradas (como las sirve el servidor), sin corregir ni cargar.
//
// Privacidad: la foto se pide con la sesión y se dibuja en un canvas (nunca en una URL ni en el almacenamiento del
// navegador) y se suelta al cerrar la planilla o salir de la vista; los valores viven solo en la memoria de la vista.
import { api, descargar, ErrorApi, nuevaClave, puede, registrarPendiente, sesion } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { url } from '../base.js';
import { ETIQUETAS_CAMPOS } from '../modelo.js';
import { $, $$, aviso, avisoError, confirmar, dialogo, fecha, hayEscrito, html, icono, montar, num } from '../ui.js';

const MAX_ARCHIVOS = 6; // el servidor procesa como máximo 6 archivos por importación
const TIPOS = { tramites: 'trámites', cedulas: 'base con cédula', general: 'base general de la campaña', planilla: 'planilla de campo' };
const TIPOS_PERSONA_PLURAL = { concejal: 'concejales', lider: 'líderes', votante: 'votantes' };

const tablaHistorial = (historial) => (historial.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th>Usuario</th><th>Archivos</th><th class="num">Personas nuevas</th><th class="num">Trámites nuevos</th><th class="num">Cédulas cruzadas</th><th class="num">Por revisar</th><th>Autorizaciones</th></tr></thead>
  <tbody>${historial.map((h) => html`<tr style="cursor:default"><td>${fecha(h.ts, true)}</td><td>${h.usuario}</td><td>${h.archivo}</td>
    <td class="num">${num(h.resumen.personas_nuevas)}</td><td class="num">${num(h.resumen.tramites_nuevos)}</td><td class="num">${num(h.resumen.cedulas_unidas_auto)}</td>
    <td class="num">${num((h.resumen.cedulas_en_revision || 0) + (h.resumen.conflictos_cedula || 0))}</td>
    <td>${h.resumen.autorizaciones_por_confirmar ? html`<button class="btn chico" data-confirmar="${h.id}" data-n="${h.resumen.autorizaciones_por_confirmar}">Confirmar ${num(h.resumen.autorizaciones_por_confirmar)}</button>` : ''}</td></tr>`)}</tbody></table></div>`
  : html`<p class="sec">Aún no se ha importado nada.</p>`);

const kpi = (t, v, d = '') => html`<div class="kpi"><div class="t">${t}</div><div class="v">${num(v)}</div>${d ? html`<div class="d">${d}</div>` : ''}</div>`;

function resumen(r) {
  const geo = r.geo?.por_precision || {};
  const ubicadas = Object.entries(geo).filter(([k]) => k !== 'sin_ubicar').reduce((a, [, v]) => a + v, 0);
  const porFuente = Object.entries(r.registros_por_fuente || {}).map(([k, n]) => `${TIPOS[k] || k}: ${num(n)} filas`).join(' · ');
  return html`<div class="kpis" style="margin:0">
      ${kpi('Personas nuevas', r.personas_nuevas, `${num(r.personas_actualizadas)} actualizadas${r.suprimidas_omitidas ? ` · ${num(r.suprimidas_omitidas)} omitidas por supresión` : ''}`)}
      ${kpi('Trámites nuevos', r.tramites_nuevos)}
      ${kpi('Cédulas cruzadas', r.cedulas_unidas_auto, `${num(r.cedulas_en_revision)} por revisar · ${num(r.cedulas_sin_coincidencia)} sin par`)}
      ${kpi('Filas sin cédula unidas', r.registros_unidos_auto, `${num(r.registros_en_revision || 0)} por revisar`)}
      ${kpi('Teléfonos agregados', r.telefonos_agregados, `${num(r.alternos_agregados)} datos alternos guardados`)}
      ${kpi('Conflictos de cédula', r.conflictos_cedula, 'Nada se mezcló: revíselos en Calidad')}
      ${kpi('Ubicadas', ubicadas, `${num(geo.direccion || 0)} con dirección exacta`)}
    </div>
    <p class="sec">Archivos procesados: ${(r.archivos || []).map((a) => `${a.archivo} (${TIPOS[a.tipo] || a.tipo}, ${num(a.filas)} filas)`).join(' · ')}${porFuente ? ` — ${porFuente}` : ''}</p>
    ${Object.keys(r.tipos_marcados || {}).length || r.lideres_asignados || r.lideres_sin_resolver ? html`<p class="sec">Base general: ${[
      ...Object.entries(r.tipos_marcados || {}).map(([k, n]) => `${num(n)} ${TIPOS_PERSONA_PLURAL[k] || k} marcados`),
      `${num(r.lideres_asignados || 0)} personas enlazadas con su líder o concejal`,
      ...(r.lideres_sin_resolver ? [`${num(r.lideres_sin_resolver)} «Liderado por» sin resolver (sin cédula, con otro nombre o sin autorización)`] : []),
    ].join(' · ')}.</p>` : ''}
    ${r.omitidas_sin_autorizacion ? html`<p class="sec">${num(r.omitidas_sin_autorizacion)} filas de personas que no autorizaron: no se les agregó ningún dato.</p>` : ''}
    ${r.votacion_por_confirmar ? html`<p class="sec">${num(r.votacion_por_confirmar)} puestos o mesas quedaron «por confirmar» (puesto ambiguo, mesa fuera de rango o dato de otra base).</p>` : ''}
    ${r.autorizaciones_por_confirmar ? html`<div class="aviso-legal">${num(r.autorizaciones_por_confirmar)} autorizaciones «declaradas en planilla» no habilitan llamadas hasta que usted las confirme con la evidencia física (en el historial).</div>` : ''}
    ${(r.planilleros_desconocidos || []).length ? html`<div class="aviso-legal">Planilleros que no existen o no están activos: ${r.planilleros_desconocidos.join(', ')}. Sus filas quedaron con el «Capturado por» del formulario.</div>` : ''}
    ${r.no_guardadas ? html`<div class="aviso-legal">${num(r.no_guardadas)} fichas no se guardaron porque cambiaron al mismo tiempo en el panel. Vuelva a importar el archivo para completarlas.</div>` : ''}
    ${r.cedulas_en_revision || r.conflictos_cedula ? html`<p><a class="btn" href="/calidad" data-ruta>Revisar en Calidad de datos</a></p>` : ''}`;
}

/** Las autorizaciones «declaradas en planilla» de una importación: el administrador las confirma con la evidencia
 * física (el papel archivado). Lo usan el historial y el resultado de cargar una planilla por foto. */
function confirmarAutorizaciones(iid, n, alTerminar) {
  const { el: d, cerrar } = dialogo({ titulo: 'Confirmar autorizaciones de esta planilla',
    cuerpo: html`<p class="sec" style="margin-top:0">${num(n)} personas declararon en la planilla que autorizan. Al confirmarlas, se podrán contactar por los canales que eligieron. Solo se confirman las que siguen vigentes (no las revocadas después). Hágalo con el papel a la vista.</p>
      <label class="campo"><span>Evidencia física</span><textarea id="evidencia" maxlength="500" placeholder="Por ejemplo: planillas firmadas archivadas en la sede, carpeta 3"></textarea></label>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Confirmar</button>`, sucio: hayEscrito });
  $('#g', d).onclick = async () => {
    const evidencia = $('#evidencia', d).value.trim();
    if (evidencia.length < 5) { aviso('Describa dónde está la evidencia', 'error'); return; }
    $('#g', d).disabled = true;
    try {
      const r = await api.post(`/api/importaciones/${iid}/confirmar-autorizaciones`, { evidencia });
      cerrar(); aviso(`${num(r.confirmadas)} autorizaciones confirmadas`); alTerminar?.();
    } catch (err) { avisoError(err); $('#g', d).disabled = false; }
  };
}

// ───────────────────────────── Planillas por foto: lo que se calcula sin el navegador ─────────────────────────────

const RUTA_FOTOS = '/api/planillas/fotos';
const ID_PLANILLA = /^[0-9a-f]{32}$/;          // los ids de la bandeja (token_hex(16)): nada más va en la ruta
const CONSULTA_MS = 3000;                     // cada cuánto se consulta la bandeja mientras hay una «leyendo»
const MAX_FOTOS_VEZ = 10;                     // fotos por selección (se preparan y suben de a una: memoria del celular)
const LADO_MIN = 200;                         // el servidor no acepta un lado mayor más chico
const LADO_SERVIDOR = 2600;                   // ni uno más grande
const LADO_AVISO = 1600;                      // más chica, la letra de una planilla de 20 columnas no se distingue
const LADO_BRILLO = 96;                       // la copia chica donde se mide la luz
const BRILLO_MIN = 70;                        // brillo medio (0–255) por debajo del cual la foto está oscura
const CALIDAD_MIN = 0.5;                      // la calidad JPEG más baja antes de achicar la foto
const MAX_BYTES = 1500000;                    // lo que acepta el servidor
// Sin `adjuntos` en el estado del asistente (un rol que no usa el chat), los topes salen del proveedor: Claude lee
// hasta 2576 px de forma nativa; Mnemo, 2000
const LADO_DIRECTO = 2576, LADO_MNEMO = 2000;
const POR_DEFECTO = { ladoMax: LADO_MNEMO, calidad: 0.8, maxBytes: MAX_BYTES };
const SUBIDA_MS = 90000, SIMULAR_MS = 120000, CARGAR_MS = 180000;
const NOTA_MAX = 300, FOLIO_MAX = 120, FOLIO_MIN = 2;
const LECTURAS_MAX = 2;
const ZOOMS = [1, 1.5, 2, 3, 4];               // sobre «ajustada al ancho»
const AVISO_FOTOS = 'Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o '
  + 'políticas. Borre la foto del teléfono.';
const AVISOS_FOTO = {
  pequena: 'Foto pequeña: puede que la letra no se lea. Acérquese o use la cámara con más resolución.',
  oscura: 'Foto oscura: tómela con más luz.',
};
// Las columnas de la planilla de campo (las de la plantilla del panel, en su orden) y el largo máximo de cada valor
// (los mismos del servidor: `lector_planillas.LARGOS`)
const COLUMNAS = {
  cedula: 'Cédula', cedula_repetida: 'Repita la cédula', tipo_documento: 'Tipo de documento', nombre: 'Nombre completo',
  celular: 'Celular', otro_telefono: 'Otro teléfono', sexo: 'Sexo', fecha_nacimiento: 'Fecha de nacimiento',
  edad: 'Edad', direccion: 'Dirección', barrio: 'Barrio o vereda', puesto: 'Puesto de votación', mesa: 'Mesa',
  autorizacion: 'Autorización', medio: 'Medio de la autorización', canales: 'Canales', mayor_18: 'Mayor de 18',
  planillero: 'Planillero (usuario)', fecha: 'Fecha', observaciones: 'Observaciones',
};
const LARGOS = {
  cedula: 20, cedula_repetida: 20, tipo_documento: 10, nombre: 160, celular: 60, otro_telefono: 60, sexo: 20,
  fecha_nacimiento: 20, edad: 10, direccion: 240, barrio: 160, puesto: 160, mesa: 40, autorizacion: 20, medio: 40,
  canales: 120, mayor_18: 10, planillero: 60, fecha: 20, observaciones: 1000,
};
const FORMATOS = { planilla_campo: 'Planilla de campo del panel', asistencia: 'Lista de asistencia', otro: 'Otro formato' };
const FILTROS = [['todas', 'Todas'], ['revisar', 'Por revisar'], ['leyendo', 'Leyendo'], ['error', 'Con error'],
  ['cargada', 'Cargadas']];
const FIRMAS = { presente: 'firmada', ausente: 'sin firma', dudosa: 'firma dudosa' };
// El estado de cada fila de la planilla (`planillas._estado_fila`)
const ESTADOS_FILA = {
  pendiente: ['azul', 'Por cargar'], no_autoriza: ['rojo', 'No autoriza'], no_se_carga: ['borde', 'No se carga'],
  descartada: ['borde', 'Descartada'], cargada: ['verde', 'Cargada'],
};
// La vista previa del importador por fila (POST …/simular) y lo que pasó al cargar (POST …/cargar)
const COTEJO = {
  nueva: ['verde', 'Ficha nueva'], nueva_sin_autorizacion: ['azul', 'Ficha nueva sin autorización'],
  completaria: ['azul', 'Completa una ficha'], igual: ['borde', 'Ya está igual en la base'],
  revocaria: ['rojo', 'Revoca su autorización'], conflicto_cedula: ['rojo', 'Conflicto de cédula'],
  revision: ['ambar', 'Queda por revisar'], no_autorizo: ['rojo', 'No autorizó: solo se anota el «no»'],
  no_se_carga: ['borde', 'No se carga'], sin_nombre: ['ambar', 'Sin nombre: corríjalo para cargarla'],
  ya_cargada: ['verde', 'Ya cargada'], otra_eleccion: ['ambar', 'Puesto de otra elección'],
  descartada: ['borde', 'Descartada'],
};
const CARGADO = {
  nueva: 'Ficha nueva', nueva_sin_autorizacion: 'Ficha nueva sin autorización', completada: 'Completó la ficha',
  igual: 'Ya estaba igual', revocada: 'Revocó su autorización', conflicto_cedula: 'Conflicto de cédula: en Calidad',
  revision: 'Por revisar en Calidad', no_autorizo: 'Se anotó el «no»', no_se_carga: 'No se carga',
  sin_nombre: 'Sin nombre: no se cargó', ya_cargada: 'Ya estaba cargada', descartada: 'Descartada',
  no_guardada: 'No se guardó (la ficha cambió a la vez): cárguela de nuevo',
};
const MOTIVOS = {
  nombre_distinto: 'la cédula es de una ficha con otro nombre', cedula_anterior: 'la ficha tenía otra cédula',
  posible_duplicado: 'posible duplicado', posible_digitacion: 'posible error al escribir la cédula',
  puesto_de_otra_eleccion: 'el puesto guardado es de otra elección', cruce_automatico: 'se unió por cruce automático',
};

/** Los topes para preparar las fotos: los de `adjuntos` del estado del asistente si llegan bien formados; si no, por
 * el proveedor del modelo. null si el panel no tiene modelo para leerlas (`configurado` falso). Sin estado (no se
 * pudo pedir), los más prudentes. */
export function limitesSubida(estado) {
  if (!estado || typeof estado !== 'object') return { ...POR_DEFECTO };
  if (estado.configurado === false || estado.proveedor === null) return null;
  const a = estado.adjuntos;
  const entero = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
  if (a && typeof a === 'object' && entero(a.lado_max, LADO_MIN, LADO_SERVIDOR) && entero(a.max_bytes, 50000, MAX_BYTES)
      && typeof a.calidad === 'number' && a.calidad >= 0.3 && a.calidad <= 1) {
    return { ladoMax: a.lado_max, calidad: a.calidad, maxBytes: a.max_bytes };
  }
  return { ...POR_DEFECTO, ladoMax: estado.proveedor === 'anthropic' ? LADO_DIRECTO : LADO_MNEMO };
}

/** El tamaño al que se reduce una foto de `ancho` × `alto` para que su lado mayor no pase de `ladoMax` (nunca se
 * agranda). */
export function medidasFoto(ancho, alto, ladoMax) {
  const escala = Math.min(1, ladoMax / Math.max(ancho, alto, 1));
  return { ancho: Math.max(1, Math.round(ancho * escala)), alto: Math.max(1, Math.round(alto * escala)) };
}

/** Las calidades JPEG que se prueban, de la pedida hacia abajo de a 0,1 hasta CALIDAD_MIN. */
export function pasosCalidad(calidad) {
  const pasos = [];
  for (let q = calidad; q >= CALIDAD_MIN - 1e-9; q -= 0.1) pasos.push(Math.round(q * 100) / 100);
  return pasos.length ? pasos : [calidad];
}

/** Qué avisar de una foto ya preparada (se sube igual): `pequena` y `oscura`. */
export function avisosFoto({ ladoOriginal, brillo }) {
  return [...(ladoOriginal < LADO_AVISO ? ['pequena'] : []), ...(brillo < BRILLO_MIN ? ['oscura'] : [])];
}

/** Las planillas de la bandeja que muestra un filtro. */
export function filtrarBandeja(planillas, filtro) {
  const es = {
    revisar: (p) => p.estado === 'leida', leyendo: (p) => p.estado === 'leyendo',
    error: (p) => p.estado === 'fallida' || p.estado === 'rechazada', cargada: (p) => p.estado === 'cargada',
  }[filtro];
  return es ? planillas.filter(es) : planillas;
}

/** ¿Se puede elegir la fila para cargarla? Las que faltan, también las «No autoriza» (se anota su «no»). */
export const seleccionable = (f) => f.estado === 'pendiente' || f.estado === 'no_autoriza';
/** ¿Tiene algo que revisar contra la foto? */
export const conDudas = (f) => !!(f.dudosos?.length || f.ilegibles?.length);
/** Las filas que se eligen al abrir: las limpias (sin nada dudoso ni ilegible) y las «No autoriza». Las dudosas se
 * revisan con la foto primero (al corregirlas dejan de serlo). */
export function filasPorDefecto(filas) {
  return new Set(filas.filter((f) => seleccionable(f) && (f.estado === 'no_autoriza' || !conDudas(f))).map((f) => f.n));
}

/** El estado de una planilla para la bandeja: {clase, texto}. */
export function estadoPlanilla(p) {
  switch (p.estado) {
    case 'leyendo': return { clase: 'azul', texto: p.progreso ? `Leyendo… ${num(p.progreso)} filas` : 'Leyendo…' };
    case 'leida':
      if (!p.pendientes) return { clase: 'borde', texto: 'Sin filas por cargar' };
      return { clase: 'ambar', texto: p.cargadas ? 'Carga parcial' : 'Por revisar' };
    case 'fallida': return { clase: 'rojo', texto: 'Falló la lectura' };
    case 'rechazada': return { clase: 'rojo', texto: 'Rechazada' };
    case 'cargada': return { clase: 'verde', texto: p.importacion_id ? `Cargada · importación #${p.importacion_id}` : 'Cargada' };
    default: return { clase: 'borde', texto: p.estado || '—' };
  }
}

/** Lleva `el` a la vista, sin animación si la persona pidió menos movimiento. */
const desplazarA = (el, block = 'start') => el?.scrollIntoView({
  behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block });

/** «1 fila», «3 filas». */
const cuantas = (n, uno, varios) => `${num(n)} ${n === 1 ? uno : varios}`;

const etiquetaCampo = (k) => ETIQUETAS_CAMPOS?.[k] || COLUMNAS[k] || k;
const chip = ([clase, texto], titulo = '') => html`<span class="chip ${clase}"${titulo ? html` title="${titulo}"` : ''}>${texto}</span>`;
const cancelada = (e) => e instanceof ErrorApi && e.codigo === 'cancelada';

// ───────────────────────────── Planillas por foto: preparar la foto en el navegador ─────────────────────────────
// Todo pasa por un canvas: la foto se abre derecha (EXIF), se dibuja al tamaño de subida y se vuelve a codificar como
// JPEG, así que no sale nada de lo que traía el archivo (EXIF, GPS, el modelo del teléfono). Una foto a la vez, con
// los lienzos soltados en cuanto dejan de servir.

const errorFoto = (mensaje) => Object.assign(new Error(mensaje), { mensajeFoto: mensaje });

async function abrirImagen(fuente) {
  try {
    return await createImageBitmap(fuente, { imageOrientation: 'from-image' });
  } catch {
    return createImageBitmap(fuente);
  }
}

function lienzo(ancho, alto) {
  const c = document.createElement('canvas');
  c.width = ancho;
  c.height = alto;
  return c;
}

/** Dibuja `fuente` en todo `destino`, sobre blanco (un PNG transparente no queda negro en el JPEG). */
function pintarEn(destino, fuente) {
  const ctx = destino.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, destino.width, destino.height);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(fuente, 0, 0, destino.width, destino.height);
  return ctx;
}

/** El brillo medio (0–255) de una copia chica; si el navegador no deja leer los píxeles, no se avisa. */
function medirBrillo(fuente) {
  const m = medidasFoto(fuente.width, fuente.height, LADO_BRILLO);
  const c = lienzo(m.ancho, m.alto);
  try {
    const d = pintarEn(c, fuente).getImageData(0, 0, m.ancho, m.alto).data;
    let suma = 0;
    for (let i = 0; i < d.length; i += 4) suma += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    return suma / (d.length / 4 || 1);
  } catch {
    return 255;
  } finally {
    c.width = c.height = 0;
  }
}

const aBlob = (c, calidad) => new Promise((listo) => c.toBlob(listo, 'image/jpeg', calidad));

/** El JPEG de `c` que cabe en `lim.maxBytes`: con la calidad pedida y, si pesa más, más baja; si ni así cabe, más
 * chica (un 80 % por vuelta). {blob, ancho, alto}. */
async function codificar(c, lim) {
  let actual = c;
  try {
    for (;;) {
      for (const q of pasosCalidad(lim.calidad)) {
        const b = await aBlob(actual, q);
        if (b && b.type === 'image/jpeg' && b.size <= lim.maxBytes) return { blob: b, ancho: actual.width, alto: actual.height };
      }
      const m = medidasFoto(actual.width, actual.height, Math.floor(Math.max(actual.width, actual.height) * 0.8));
      if (Math.max(m.ancho, m.alto) < LADO_MIN) throw errorFoto('La foto pesa demasiado aun reducida: tómela de nuevo.');
      const chico = lienzo(m.ancho, m.alto);
      pintarEn(chico, actual);
      if (actual !== c) actual.width = actual.height = 0;
      actual = chico;
    }
  } finally {
    if (actual !== c) actual.width = actual.height = 0;
  }
}

/** Prepara para subir la foto `archivo` con los topes `lim`: {blob, ancho, alto, avisos}. */
async function prepararFoto(archivo, lim) {
  let bmp;
  try {
    bmp = await abrirImagen(archivo);
  } catch {
    throw errorFoto('No se pudo abrir esa imagen: elija una foto (JPEG o PNG).');
  }
  let c = null;
  try {
    const ladoOriginal = Math.max(bmp.width, bmp.height);
    if (ladoOriginal < LADO_MIN) throw errorFoto('La imagen es demasiado pequeña para leer una planilla.');
    const brillo = medirBrillo(bmp);
    const m = medidasFoto(bmp.width, bmp.height, lim.ladoMax);
    c = lienzo(m.ancho, m.alto);
    pintarEn(c, bmp);
    bmp.close(); // la imagen entera ya no hace falta
    const r = await codificar(c, lim);
    return { ...r, avisos: avisosFoto({ ladoOriginal, brillo }) };
  } finally {
    bmp.close();
    if (c) c.width = c.height = 0;
  }
}

// ───────────────────────────── Planillas por foto: la sección de la vista ─────────────────────────────

/**
 * Monta «Planillas por foto» en `caja` (la bandeja) y `cajaAbierta` (la planilla abierta). `planilleros` son los de
 * «Capturado por»; `ajustes`, los del panel si la persona los puede leer (A y K: retención, roles y otros formatos);
 * `inicial`, el id de `?planilla=` para abrirla al entrar; `alCargar`, lo que se refresca tras una carga (historial e
 * insignias). Devuelve la limpieza de la vista: corta las consultas y suelta la foto.
 */
function planillasPorFoto(caja, cajaAbierta, { planilleros, ajustes, inicial, alCargar }) {
  const revisa = puede('importar');          // A y K: valores completos, corregir, cotejar y cargar
  const control = new AbortController();     // al salir de la vista se cortan las peticiones en curso
  const op = { signal: control.signal };
  const ap = ajustes?.agente_planillas || null;
  let vivo = true;
  let lista = [];                            // la bandeja
  let filtro = 'todas';
  let reloj = null, consultando = null;
  let limites;                               // los topes de la foto (promesa, se piden una vez)
  let subiendo = false, sinSubida = ap && !ap.roles?.includes(sesion.rol) ? 'rol' : null;
  // La planilla abierta
  let abierta = null;                        // el detalle de GET /api/planillas/{id}
  let ediciones = new Map();                 // `${n}|${campo}` → valor escrito (sin guardar)
  let elegidas = new Set(), tocadas = new Set(); // filas elegidas para cargar y las que la persona marcó o desmarcó
  let cotejo = null;                         // {n: fila} de la última vista previa (null: sin cotejar o vieja)
  let cotejoViejo = false;
  let resultado = null;                      // la respuesta de la última carga
  let claveCarga = null;                     // {clave, cuerpo}: la Idempotency-Key de la carga en curso y lo que carga
  let folio = '', capturado = '';
  let foto = null, pedidoFoto = null, zoom = 0, giro = 0;
  let ocupado = false;
  let turno = 0;                             // cada respuesta que cambia la planilla abierta: gana la última pedida
  const quitarPendiente = registrarPendiente(() => ediciones.size > 0);

  // ── La sección: subir y bandeja ──
  const retencion = ap?.retencion_horas;
  montar(caja, html`
    <header><h2 id="pf-titulo">Planillas por foto</h2><span class="nota" id="pf-cuenta"></span></header>
    <p class="sec pf-intro">Tome o elija la foto de cada hoja de la planilla de campo: el panel la lee de fondo mientras usted sigue con la siguiente.${revisa ? ' Luego ábrala para revisar lo leído al lado de la foto, corregir, cotejar con la base y cargar.' : ' Un coordinador la revisa y la carga.'}</p>
    <div class="pf-subir" id="pf-subir">
      <div class="pf-botones">
        <button type="button" class="btn primario" id="pf-camara">${icono('camara')}<span>Tomar foto</span></button>
        <button type="button" class="btn" id="pf-galeria">${icono('galeria')}<span>Elegir fotos</span></button>
        <input type="file" id="pf-camara-in" accept="image/*" capture="environment" tabindex="-1" hidden>
        <input type="file" id="pf-galeria-in" accept="image/jpeg,image/png,image/*" multiple tabindex="-1" hidden>
        <span class="sec pf-soltar">o arrástrelas aquí (hasta ${MAX_FOTOS_VEZ} a la vez)</span>
      </div>
      <div class="form pf-opciones">
        <label class="campo"><span>Nota para estas fotos (opcional)</span><input id="pf-nota" maxlength="${NOTA_MAX}" placeholder="Vereda o reunión, sin datos de personas" autocomplete="off"></label>
        ${ap?.otros_formatos ? html`<label class="campo"><span>Formato</span><select id="pf-formato">${Object.entries(FORMATOS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>` : ''}
      </div>
      <p class="aviso-legal pf-aviso">${AVISO_FOTOS}</p>
      <p class="sec pf-privacidad">La foto va al modelo de lenguaje solo para leerla. Se guarda cifrada y se borra al cargar la hoja o ${retencion ? `a las ${num(retencion)} horas` : 'al vencer el plazo de Ajustes'}. Las autorizaciones leídas quedan «declaradas en planilla» hasta que alguien las confirme con el papel.</p>
    </div>
    <p class="aviso-legal pf-sin-subida" id="pf-sin-subida" hidden></p>
    <ul class="pf-subidas" id="pf-subidas" aria-live="polite"></ul>
    <div class="segmentado pf-filtros" role="group" aria-label="Mostrar planillas">${FILTROS.map(([k, t]) => html`<button type="button" data-filtro="${k}" aria-pressed="${k === filtro}">${t}</button>`)}</div>
    <div id="pf-bandeja" class="pf-bandeja"><div class="pf-cargando"><div class="giro"></div><span>Cargando la bandeja…</span></div></div>`);

  const sinSubidaTexto = {
    rol: puede('ajustes.gestionar') && sesion.rol === 'admin'
      ? 'Su rol no sube fotos de planillas: actívelo en Ajustes → Planillas físicas por foto.'
      : 'Su rol no sube fotos de planillas: el administrador lo habilita en Ajustes.',
    modelo: 'El panel no tiene un modelo conectado para leer las fotos: el administrador lo conecta en Ajustes → Asistente.',
  };
  function pintarSubida() {
    $('#pf-subir', caja).hidden = !!sinSubida;
    const aviso_ = $('#pf-sin-subida', caja);
    aviso_.hidden = !sinSubida;
    aviso_.textContent = sinSubida ? (sinSubidaTexto[sinSubida] || sinSubida) : '';
  }
  pintarSubida();

  const pedirLimites = () => (limites ||= api.get('/api/agente/estado', null, op).then(limitesSubida, (e) => {
    if (cancelada(e)) throw e;
    return { ...POR_DEFECTO };
  }));
  if (!sinSubida) {
    pedirLimites().then((l) => { if (vivo && l === null) { sinSubida = 'modelo'; pintarSubida(); } }).catch(() => {});
  }

  // ── Subir ──
  const elegirFotos = (archivos) => {
    const todas = [...(archivos || [])];
    if (!todas.length || subiendo || sinSubida) return;
    if (todas.length > MAX_FOTOS_VEZ) {
      aviso(`Elija como máximo ${MAX_FOTOS_VEZ} fotos a la vez`, 'error', 6000);
      return;
    }
    subirFotos(todas);
  };
  $('#pf-camara', caja).addEventListener('click', () => $('#pf-camara-in', caja).click());
  $('#pf-galeria', caja).addEventListener('click', () => $('#pf-galeria-in', caja).click());
  for (const id of ['#pf-camara-in', '#pf-galeria-in']) {
    $(id, caja).addEventListener('change', (e) => { const fs = [...e.target.files]; e.target.value = ''; elegirFotos(fs); });
  }
  const zona = $('#pf-subir', caja);
  zona.addEventListener('dragover', (e) => { if (e.dataTransfer?.types?.includes('Files')) { e.preventDefault(); zona.classList.add('encima'); } });
  zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
  zona.addEventListener('drop', (e) => {
    e.preventDefault();
    zona.classList.remove('encima');
    elegirFotos([...(e.dataTransfer?.files || [])].filter((f) => f.type.startsWith('image/')));
  });

  function itemSubida(i, total) {
    const li = document.createElement('li');
    li.className = 'pf-subida';
    $('#pf-subidas', caja).append(li);
    const pintar = (estado, texto, avisos = []) => montar(li, html`<span class="pf-subida-icono" data-estado="${estado}">${icono(estado === 'ok' ? 'hecho' : estado === 'error' ? 'alerta' : 'reloj')}</span>
      <span><b>Foto ${num(i)} de ${num(total)}:</b> ${texto}${avisos.length ? html`<span class="pf-subida-avisos">${avisos.map((a) => html`<span class="chip ambar">${AVISOS_FOTO[a] || a}</span>`)}</span>` : ''}</span>`);
    return pintar;
  }

  async function subirFotos(archivos) {
    subiendo = true;
    for (const b of ['#pf-camara', '#pf-galeria']) $(b, caja).disabled = true;
    montar($('#pf-subidas', caja), html``);
    const nota = ($('#pf-nota', caja).value || '').trim().slice(0, NOTA_MAX);
    const formato = $('#pf-formato', caja)?.value || 'planilla_campo';
    let parar = false;
    try {
      const lim = await pedirLimites();
      if (lim === null) { sinSubida = 'modelo'; pintarSubida(); return; }
      for (let i = 0; i < archivos.length && vivo; i++) {
        const pintar = itemSubida(i + 1, archivos.length);
        if (parar) { pintar('error', 'no se subió.'); continue; }
        pintar('espera', 'preparando…');
        let prep;
        try {
          prep = await prepararFoto(archivos[i], lim);
        } catch (e) {
          pintar('error', e.mensajeFoto || 'No se pudo preparar la foto.');
          continue;
        }
        pintar('espera', 'subiendo…', prep.avisos);
        const consulta = new URLSearchParams();
        if (nota) consulta.set('nota', nota);
        if (formato !== 'planilla_campo') consulta.set('formato', formato);
        try {
          const q = consulta.toString();
          const ruta = RUTA_FOTOS + (q ? `?${q}` : '');
          const r = await api.subir(ruta, prep.blob, { timeout: SUBIDA_MS, signal: control.signal });
          pintar('ok', r.repetida ? 'ya estaba en la bandeja.' : 'en la bandeja, leyéndose.', prep.avisos);
          consultar(); // aparece «leyendo» en la bandeja
        } catch (e) {
          if (cancelada(e)) return;
          pintar('error', e.message || 'No se pudo subir.', prep.avisos);
          if (e instanceof ErrorApi && ['planillas_apagado', 'sin_configurar'].includes(e.codigo)) {
            sinSubida = e.codigo === 'sin_configurar' ? 'modelo' : 'rol';
            parar = true;
          } else if (e instanceof ErrorApi && ['frecuencia', 'pendientes'].includes(e.codigo)) {
            parar = true;
          }
        } finally {
          prep.blob = null;
        }
      }
    } catch (e) {
      if (!cancelada(e)) avisoError(e);
    } finally {
      subiendo = false;
      if (vivo) {
        for (const b of ['#pf-camara', '#pf-galeria']) $(b, caja).disabled = false;
        pintarSubida();
        consultar();
      }
    }
  }

  // ── La bandeja ──
  function pintarBandeja() {
    const vistas = filtrarBandeja(lista, filtro);
    const porRevisar = lista.filter((p) => p.estado === 'leida' && p.pendientes).length;
    $('#pf-cuenta', caja).textContent = lista.length ? `${num(lista.length)} en la bandeja${porRevisar ? ` · ${num(porRevisar)} por revisar` : ''}` : '';
    for (const b of $$('[data-filtro]', caja)) b.setAttribute('aria-pressed', String(b.dataset.filtro === filtro));
    if (!vistas.length) {
      montar($('#pf-bandeja', caja), html`<p class="sec pf-vacia">${lista.length ? 'Ninguna planilla con ese estado.' : 'Aún no hay fotos de planillas.'}</p>`);
      return;
    }
    montar($('#pf-bandeja', caja), html`<ul class="pf-lista">${vistas.map((p) => {
      const e = estadoPlanilla(p);
      const datos = [
        p.filas != null && p.estado !== 'leyendo' ? cuantas(p.filas, 'fila', 'filas') : '',
        p.dudosas ? `${num(p.dudosas)} con dudas` : '',
        p.cargadas ? cuantas(p.cargadas, 'cargada', 'cargadas') : '',
        p.estado === 'leida' && p.pendientes ? `${num(p.pendientes)} por cargar` : '',
        p.incompleta ? 'lectura incompleta' : '',
        p.estado !== 'cargada' && p.expira ? `vence ${fecha(p.expira, true)}` : '',
      ].filter(Boolean).join(' · ');
      const quien = p.subida_por?.nombre || p.subida_por?.usuario || '';
      const releer = p.estado === 'fallida' && p.con_foto && (p.lecturas || 0) < LECTURAS_MAX;
      return html`<li class="pf-item${abierta?.id === p.id ? ' abierta' : ''}" data-id="${p.id}">
        <div class="pf-item-cab">${chip([e.clase, e.texto])}<b>Foto del ${fecha(p.ts, true)}</b>${revisa && quien ? html`<span class="sec">· ${quien}</span>` : ''}</div>
        ${datos ? html`<div class="sec pf-item-datos">${datos}</div>` : ''}
        ${p.nota ? html`<div class="pf-item-nota">Nota: ${p.nota}</div>` : ''}
        ${p.error?.mensaje && (p.estado === 'fallida' || p.estado === 'rechazada') ? html`<div class="pf-item-error">${p.error.mensaje}</div>` : ''}
        <div class="pf-item-acciones">
          <button type="button" class="btn chico${revisa && p.estado === 'leida' && p.pendientes ? ' oscuro' : ''}" data-abrir="${p.id}">${revisa && p.estado === 'leida' ? 'Revisar' : 'Ver'}</button>
          ${releer ? html`<button type="button" class="btn chico" data-releer="${p.id}">${icono('repetir')} Volver a leer</button>` : ''}
          <button type="button" class="btn chico fantasma peligro" data-borrar="${p.id}" aria-label="Borrar la foto del ${fecha(p.ts, true)}">${icono('basura')}</button>
        </div></li>`;
    })}</ul>`);
  }

  /** Pide la bandeja (una consulta a la vez) y, mientras alguna se lee, vuelve a pedirla en CONSULTA_MS. Con la
   * pestaña oculta no consulta: lo hace al volver. */
  function consultar() {
    clearTimeout(reloj);
    if (!vivo) return Promise.resolve();
    consultando ||= (async () => {
      try {
        const r = await api.get('/api/planillas', null, op);
        if (!vivo) return;
        lista = Array.isArray(r?.planillas) ? r.planillas : [];
        pintarBandeja();
        await seguirAbierta();
      } catch (e) {
        if (cancelada(e) || !vivo) return;
        if (!lista.length) montar($('#pf-bandeja', caja), html`<p class="aviso-legal">${e.message || 'No se pudo cargar la bandeja.'}</p>`);
      } finally {
        consultando = null;
        if (vivo && (lista.some((p) => p.estado === 'leyendo') || abierta?.estado === 'leyendo')) {
          reloj = setTimeout(() => { if (!document.hidden) consultar(); }, CONSULTA_MS);
        }
      }
    })();
    return consultando;
  }
  const alVolver = () => { if (!document.hidden && vivo) consultar(); };
  document.addEventListener('visibilitychange', alVolver);

  /** La planilla abierta sigue a la bandeja: si cambió de estado (terminó de leerse, la cargó otra persona) o se está
   * leyendo, se vuelve a pedir; si ya no está, se cierra. */
  async function seguirAbierta() {
    if (!abierta) return;
    const b = lista.find((p) => p.id === abierta.id);
    const igual = b && b.estado === abierta.estado && b.progreso === abierta.progreso;
    if ((abierta.estado === 'leyendo' && !igual) || (b && b.estado !== abierta.estado)) {
      await abrir(abierta.id, { desplazar: false, silencio: true });
    } else if (!b && lista.length < 100) {
      cerrarPlanilla();
      aviso('La planilla abierta ya no está en la bandeja (se borró o venció).', 'error');
    }
  }

  caja.addEventListener('click', async (e) => {
    const f = e.target.closest('[data-filtro]');
    if (f) { filtro = f.dataset.filtro; pintarBandeja(); return; }
    const a = e.target.closest('[data-abrir]');
    if (a) { abrir(a.dataset.abrir); return; }
    const r = e.target.closest('[data-releer]');
    if (r) { releer(r.dataset.releer, null, r); return; }
    const b = e.target.closest('[data-borrar]');
    if (b) borrar(b.dataset.borrar);
  });

  async function releer(id, desdeFila, boton) {
    if (!ID_PLANILLA.test(id)) return;
    if (boton) boton.disabled = true;
    try {
      await api.post(`/api/planillas/${id}/leer`, desdeFila ? { desde_fila: desdeFila } : {}, op);
      aviso(desdeFila ? `Leyendo desde la fila ${desdeFila}…` : 'Leyendo de nuevo…');
      if (abierta?.id === id) { ediciones = new Map(); cotejo = null; resultado = null; }
      await consultar();
      if (abierta?.id === id) await abrir(id, { desplazar: false, silencio: true });
    } catch (err) {
      if (!cancelada(err)) avisoError(err);
    } finally {
      if (boton?.isConnected) boton.disabled = false;
    }
  }

  async function borrar(id) {
    if (!ID_PLANILLA.test(id)) return;
    const p = lista.find((x) => x.id === id) || (abierta?.id === id ? abierta : null);
    const cargadas = p?.cargadas ? ' Las filas que ya se cargaron siguen en la base.' : '';
    if (!(await confirmar(`¿Borrar esta planilla? Se borran la foto y lo leído.${cargadas}`, { si: 'Borrar', peligro: true }))) return;
    try {
      await api.del(`/api/planillas/${id}`, op);
      aviso('Planilla borrada');
      if (abierta?.id === id) cerrarPlanilla();
      consultar();
    } catch (err) { if (!cancelada(err)) avisoError(err); }
  }

  // ── La planilla abierta ──
  const quitarDeUrl = () => {
    const u = new URL(location.href);
    if (u.searchParams.has('planilla')) { u.searchParams.delete('planilla'); history.replaceState(history.state ?? {}, '', u); }
  };
  const ponerEnUrl = (id) => {
    const u = new URL(location.href);
    if (u.searchParams.get('planilla') !== id) { u.searchParams.set('planilla', id); history.replaceState(history.state ?? {}, '', u); }
  };

  /** El planillero que se propone en «Capturado por»: quien subió la foto si es planillero; si no, el que nombra el
   * encabezado de la hoja por su usuario. */
  function capturadoPorDefecto(d) {
    const uid = d.subida_por?.uid;
    if (planilleros.some((u) => u.id === uid)) return String(uid);
    const escrito = String(d.encabezado?.planillero || '').trim().toLowerCase();
    const p = escrito && planilleros.find((u) => String(u.usuario || '').toLowerCase() === escrito);
    return p ? String(p.id) : '';
  }

  async function abrir(id, { desplazar = true, silencio = false } = {}) {
    if (!ID_PLANILLA.test(id)) return;
    const otra = abierta && abierta.id !== id;
    if (otra && ediciones.size && !(await confirmar('Tiene correcciones sin guardar en la planilla abierta. ¿Descartarlas y abrir otra?', { si: 'Descartar', peligro: true }))) return;
    // Si mientras llega se pide otra (la persona abre otra planilla, o guarda una corrección), esta respuesta sobra:
    // la consulta periódica no devuelve a la planilla de antes ni pisa lo recién guardado
    const mio = ++turno;
    let d;
    try {
      d = await api.get(`/api/planillas/${id}`, null, op);
    } catch (e) {
      if (cancelada(e) || !vivo || mio !== turno) return;
      if (e instanceof ErrorApi && e.estado === 404) {
        if (abierta?.id === id || !abierta) cerrarPlanilla();
        if (!silencio || !abierta) aviso(e.message || 'No existe esa planilla (o ya venció).', 'error');
      } else if (!silencio) avisoError(e);
      return;
    }
    if (!vivo || mio !== turno) return;
    const nueva = !abierta || abierta.id !== d.id;
    if (nueva) {
      soltarFoto();
      ediciones = new Map(); cotejo = null; cotejoViejo = false; resultado = null; claveCarga = null;
      elegidas = filasPorDefecto(d.filas || []); tocadas = new Set();
      folio = ''; capturado = capturadoPorDefecto(d); zoom = 0; giro = 0;
    } else {
      seguirEleccion(d);
    }
    const estabaLeyendo = abierta?.estado === 'leyendo';
    abierta = d;
    if (!d.con_foto) soltarFoto(); // se cargó entera o se rechazó: la foto ya no existe
    ponerEnUrl(d.id);
    pintarAbierta();
    if (d.con_foto && !foto && !pedidoFoto) cargarFoto(d.id);
    if (nueva || (estabaLeyendo && d.estado !== 'leyendo')) pintarBandeja();
    if (desplazar) desplazarA(cajaAbierta);
    if (d.estado === 'leyendo') consultar();
  }

  /** La misma planilla, vuelta a pedir o corregida: lo elegido sigue, lo que dejó de poder cargarse sale y una fila
   * que quedó limpia (se corrigió lo dudoso) se elige si nadie la marcó o desmarcó a mano. */
  function seguirEleccion(d) {
    const por = new Map((d.filas || []).map((f) => [f.n, f]));
    elegidas = new Set([...elegidas].filter((n) => por.has(n) && seleccionable(por.get(n))));
    for (const n of filasPorDefecto(d.filas || [])) if (!tocadas.has(n)) elegidas.add(n);
    if (d.estado !== 'leida') ediciones = new Map();
  }

  function cerrarPlanilla() {
    abierta = null;
    ediciones = new Map(); cotejo = null; resultado = null; claveCarga = null;
    soltarFoto();
    cajaAbierta.hidden = true;
    montar(cajaAbierta, html``);
    quitarDeUrl();
    pintarBandeja();
  }

  // La foto: se pide con la sesión y se dibuja en un canvas a su tamaño; el zoom es el ancho con que se muestra
  function soltarFoto() {
    pedidoFoto?.abort();
    pedidoFoto = null;
    try { foto?.close(); } catch { /* ya cerrada */ }
    foto = null;
    const c = $('#pf-lienzo', cajaAbierta);
    if (c) c.width = c.height = 0;
  }

  async function cargarFoto(id) {
    const marco = () => $('#pf-marco', cajaAbierta);
    const mensaje = (t) => { const m = marco(); if (m) montar(m, html`<p class="sec pf-foto-mensaje">${t}</p>`); };
    pedidoFoto = new AbortController();
    const senal = AbortSignal.any ? AbortSignal.any([pedidoFoto.signal, control.signal]) : pedidoFoto.signal;
    let bmp = null;
    try {
      const r = await fetch(url(`/api/planillas/${id}/foto`), { credentials: 'same-origin', cache: 'no-store', signal: senal });
      if (!r.ok) {
        let detalle = null;
        try { detalle = (await r.json())?.detail; } catch { /* no era JSON */ }
        mensaje(detalle?.mensaje || (r.status === 401 ? 'La sesión terminó: ingrese de nuevo para ver la foto.' : 'No se pudo abrir la foto.'));
        return;
      }
      bmp = await createImageBitmap(await r.blob());
      if (!vivo || abierta?.id !== id) return;
      foto = bmp;
      bmp = null;
      dibujarFoto();
    } catch (e) {
      if (e?.name !== 'AbortError' && vivo && abierta?.id === id) mensaje('No se pudo abrir la foto.');
    } finally {
      try { bmp?.close(); } catch { /* nada */ }
      if (abierta?.id === id || !abierta) pedidoFoto = null;
    }
  }

  function dibujarFoto() {
    const marco = $('#pf-marco', cajaAbierta);
    if (!marco || !foto) return;
    let c = $('#pf-lienzo', marco);
    if (!c) {
      montar(marco, html`<canvas id="pf-lienzo" role="img" aria-label="Foto de la planilla"></canvas>`);
      c = $('#pf-lienzo', marco);
    }
    const lado = giro % 180 ? [foto.height, foto.width] : [foto.width, foto.height];
    [c.width, c.height] = lado;
    const ctx = c.getContext('2d');
    ctx.save();
    ctx.translate(c.width / 2, c.height / 2);
    ctx.rotate((giro * Math.PI) / 180);
    ctx.drawImage(foto, -foto.width / 2, -foto.height / 2);
    ctx.restore();
    aplicarZoom();
  }

  function aplicarZoom() {
    const marco = $('#pf-marco', cajaAbierta), c = $('#pf-lienzo', cajaAbierta);
    if (!marco || !c || !c.width) return;
    const ajustado = Math.min(c.width, Math.max(120, marco.clientWidth - 2));
    c.style.width = `${Math.round(ajustado * ZOOMS[zoom])}px`;
    const t = $('#pf-zoom-valor', cajaAbierta);
    if (t) t.textContent = zoom ? `×${String(ZOOMS[zoom]).replace('.', ',')}` : 'Ajustada';
    const menos = $('[data-zoom="-1"]', cajaAbierta), mas = $('[data-zoom="1"]', cajaAbierta);
    if (menos) menos.disabled = zoom === 0;
    if (mas) mas.disabled = zoom === ZOOMS.length - 1;
  }
  const alCambiarTamano = () => aplicarZoom();
  addEventListener('resize', alCambiarTamano);

  const valorOriginal = (f, campo) => String(f.valores?.[campo] ?? '');

  function filaRevisable(f, columnas) {
    const editable = abierta.estado === 'leida' && (f.estado === 'pendiente' || f.estado === 'no_autoriza');
    const descartada = f.estado === 'descartada';
    const elegir = seleccionable(f) && abierta.estado === 'leida';
    const c = cotejo?.[f.n];
    const firma = f.firma && FIRMAS[f.firma];
    const detalles = c ? [
      ...(c.motivo && MOTIVOS[c.motivo] ? [MOTIVOS[c.motivo]] : []),
      ...(c.llenaria?.length ? [`llenaría: ${c.llenaria.map(etiquetaCampo).join(', ')}`] : []),
      ...(c.distintos || []).map((x) => `${etiquetaCampo(x.campo)}: ${x.base ?? '—'} en la base, ${x.planilla ?? '—'} en la planilla (${x.queda === 'planilla' ? 'queda el de la planilla' : 'el de la planilla queda como dato alterno'})`),
    ] : [];
    return html`<tr class="pf-fila" data-n="${f.n}" data-estado="${f.estado}">
      <td class="pf-sel">${elegir ? html`<input type="checkbox" data-elegir="${f.n}" aria-label="Cargar la fila ${f.n}"${elegidas.has(f.n) ? html` checked` : ''}>` : ''}</td>
      <th scope="row" class="pf-n">${f.n}</th>
      <td class="pf-estado-celda">
        ${f.estado === 'pendiente' ? '' : chip(ESTADOS_FILA[f.estado] || ['borde', f.estado], f.estado === 'no_autoriza' ? 'Solo se guardan nombre, cédula y barrio; al cargarla se anota el «no». Si la casilla se leyó mal, corrija «Autorización» y escriba el resto desde el papel.' : '')}
        ${firma ? html`<span class="pf-firma" data-firma="${f.firma}">${firma}</span>` : ''}
        ${c ? (detalles.length
          ? html`<details class="pf-cotejo"><summary>${chip(COTEJO[c.estado] || ['borde', c.estado])}</summary><ul>${detalles.map((t) => html`<li>${t}</li>`)}</ul></details>`
          : chip(COTEJO[c.estado] || ['borde', c.estado])) : ''}
        ${c?.persona_id > 0 ? html`<a class="pf-ficha" href="/personas/${c.persona_id}" target="_blank" rel="noopener">Ficha #${c.persona_id}</a>` : ''}
        ${abierta.estado === 'leida' && revisa && (editable || descartada) ? html`<button type="button" class="btn chico fantasma" data-${descartada ? 'restaurar' : 'descartar'}="${f.n}">${descartada ? 'Recuperar' : 'Descartar'}</button>` : ''}
      </td>
      ${columnas.map((k) => {
        const dudoso = f.dudosos?.includes(k), ilegible = f.ilegibles?.includes(k), corregido = f.corregidos?.includes(k);
        const clave = `${f.n}|${k}`;
        const valor = ediciones.has(clave) ? ediciones.get(clave) : valorOriginal(f, k);
        const marca = ilegible ? 'ilegible' : dudoso ? 'dudoso' : corregido ? 'corregido' : '';
        const nombre = `Fila ${f.n}, ${COLUMNAS[k] || k}${marca ? ` (${marca})` : ''}`;
        return html`<td class="pf-celda${ediciones.has(clave) ? ' cambiada' : ''}" data-marca="${marca}" data-campo="${k}"><input class="pf-entrada" data-n="${f.n}" data-campo="${k}" value="${valor}" maxlength="${LARGOS[k] || 200}" aria-label="${nombre}" title="${marca ? `${marca[0].toUpperCase()}${marca.slice(1)}: revíselo en la foto` : ''}" autocomplete="off" spellcheck="false"${editable ? '' : html` disabled`}></td>`;
      })}
    </tr>`;
  }

  // Una fila sin nada que corregir (cargada o que no se carga): su estado y su texto en una sola celda, que se queda a
  // la vista aunque la grilla esté desplazada hacia las últimas columnas
  function filaFija(f, columnas, texto) {
    return html`<tr class="pf-fila" data-n="${f.n}" data-estado="${f.estado}">
      <td class="pf-sel"></td><th scope="row" class="pf-n">${f.n}</th>
      <td class="pf-fija" colspan="${columnas.length + 1}"><div class="pf-fija-texto">${chip(ESTADOS_FILA[f.estado] || ['borde', f.estado])} ${texto}</div></td></tr>`;
  }

  function filaCargada(f, columnas) {
    return filaFija(f, columnas, html`${CARGADO[f.resultado] || 'Cargada'}${f.persona_id > 0 ? html` · <a href="/personas/${f.persona_id}" target="_blank" rel="noopener">Ficha #${f.persona_id}</a>` : ''}`);
  }

  // P: las filas enmascaradas como las sirve el servidor (sin corregir ni cargar)
  function tablaEnmascarada(filas) {
    return html`<div class="envoltura-tabla pf-tabla-env"><table class="tabla pf-tabla pf-enmascarada"><thead><tr><th>Fila</th><th>Estado</th><th>Nombre</th><th>Cédula</th><th>Celular</th><th>Barrio o vereda</th><th>Autorización</th><th>Para revisar</th></tr></thead>
      <tbody>${filas.map((f) => html`<tr class="sin-clic" data-n="${f.n}"><th scope="row" class="pf-n">${f.n}</th>
        <td>${chip(ESTADOS_FILA[f.estado] || ['borde', f.estado])}</td>
        <td>${f.nombre || ''}</td>
        <td>${f.cedula || ''}${f.cedula_coincide === false ? html` <span class="chip ambar">no coincide con su repetición</span>` : ''}</td>
        <td>${f.celular || ''}${f.menor ? html` <span class="chip borde">menor de edad</span>` : ''}</td>
        <td>${f.barrio || f.lugar || ''}</td>
        <td>${f.consentimiento === 'no' ? 'No autoriza' : f.autorizacion || ''}</td>
        <td>${[...(f.dudosos || []).map((k) => `${COLUMNAS[k] || k} dudosa`), ...(f.ilegibles || []).map((k) => `${COLUMNAS[k] || k} ilegible`)].join(', ')}</td></tr>`)}</tbody></table></div>`;
  }

  function avisosLectura(d) {
    const avisos = [];
    const n = (d.filas || []).length;
    if (d.estado === 'leyendo') {
      avisos.push(html`<div class="pf-leyendo" role="status"><div class="giro"></div><span>${d.progreso ? `Leyendo la foto… van ${num(d.progreso)} filas.` : 'La foto está en cola o leyéndose. Esta página se actualiza sola.'}</span></div>`);
    }
    if ((d.estado === 'fallida' || d.estado === 'rechazada') && d.error?.mensaje) {
      avisos.push(html`<div class="aviso-legal">${d.error.mensaje}</div>`);
    }
    if (d.estado === 'leida' && d.incompleta) {
      const desde = (d.ultima_fila || Math.max(0, ...(d.filas || []).map((f) => f.n))) + 1;
      avisos.push(html`<div class="aviso-legal">La lectura quedó incompleta: llegó hasta la fila ${num(desde - 1)}${d.filas_visibles ? ` de ${num(d.filas_visibles)}` : ''}. ${d.puede_releer ? html`<button type="button" class="btn chico" data-releer-desde="${desde}">Leer desde la fila ${desde}</button>` : 'Tome otra foto de las filas que faltan.'}</div>`);
    } else if (d.estado === 'leida' && d.filas_visibles && d.filas_visibles > n) {
      avisos.push(html`<div class="aviso-legal">En la hoja se ven ${num(d.filas_visibles)} filas y se leyeron ${num(n)}: revise la foto.</div>`);
    }
    if (d.estado === 'cargada') {
      avisos.push(html`<p class="sec">Todas sus filas se cargaron o descartaron${(d.importaciones || []).length ? ` (importaciones ${d.importaciones.map((i) => `#${i}`).join(', ')})` : ''}: la foto y lo leído ya se borraron.</p>`);
    }
    return avisos;
  }

  function pintarAbierta() {
    const d = abierta;
    if (!d) return;
    // Lo que se repinta no mueve a la persona: la grilla y la foto quedan donde estaban y la celda (o el botón) que
    // tenía el foco lo recupera con su cursor
    const envoltura = $('.pf-tabla-env', cajaAbierta), marcoAntes = $('#pf-marco', cajaAbierta);
    const scroll = envoltura ? [envoltura.scrollLeft, envoltura.scrollTop] : null;
    const scrollFoto = marcoAntes ? [marcoAntes.scrollLeft, marcoAntes.scrollTop] : null;
    const activo = cajaAbierta.contains(document.activeElement) ? document.activeElement : null;
    const enfocado = activo?.id || null;
    const celda = activo?.classList.contains('pf-entrada')
      ? { n: activo.dataset.n, campo: activo.dataset.campo, ini: activo.selectionStart, fin: activo.selectionEnd } : null;
    const columnas = (Array.isArray(d.columnas) && d.columnas.length ? d.columnas : Object.keys(COLUMNAS)).filter((k) => COLUMNAS[k]);
    const filas = d.filas || [];
    const enc = d.encabezado || {};
    const encabezado = [['Planillero', enc.planillero], ['Fecha', enc.fecha], ['Lugar', enc.lugar]].filter(([, v]) => v);
    const quien = d.subida_por?.nombre || d.subida_por?.usuario || '';
    const puedeCargar = revisa && d.estado === 'leida';
    const releerTodo = d.puede_releer && (d.estado === 'leida' || d.estado === 'fallida');
    cajaAbierta.hidden = false;
    montar(cajaAbierta, html`
      <header class="pf-abierta-cab">
        <div><h2 id="pf-abierta-titulo">Planilla del ${fecha(d.ts, true)}</h2>
          <div class="sec">${[revisa && quien ? `Subida por ${quien}` : '', d.formato && d.formato !== 'planilla_campo' ? FORMATOS[d.formato] || d.formato : '',
            d.estado !== 'cargada' && d.expira ? `vence ${fecha(d.expira, true)}` : '', d.nota ? `Nota: ${d.nota}` : ''].filter(Boolean).join(' · ')}</div></div>
        <div class="acciones">${chip([estadoPlanilla(d).clase, estadoPlanilla(d).texto])}
          ${releerTodo ? html`<button type="button" class="btn chico" id="pf-releer">${icono('repetir')} Volver a leer</button>` : ''}
          <button type="button" class="btn chico fantasma peligro" id="pf-borrar">${icono('basura')} Borrar</button>
          <button type="button" class="btn chico fantasma" id="pf-cerrar" aria-label="Cerrar la planilla">${icono('cerrar')}</button></div>
      </header>
      ${avisosLectura(d)}
      ${encabezado.length ? html`<p class="pf-encabezado">${encabezado.map(([k, v]) => html`<span><b>${k}:</b> ${v}</span>`)}</p>` : ''}
      <div class="pf-revision${d.con_foto ? '' : ' sin-foto'}">
        ${d.con_foto ? html`<div class="pf-foto">
          <div class="pf-foto-barra" role="group" aria-label="Ver la foto">
            <button type="button" class="btn chico" data-zoom="-1" aria-label="Alejar">−</button>
            <span id="pf-zoom-valor" class="pf-zoom-valor" aria-live="polite">Ajustada</span>
            <button type="button" class="btn chico" data-zoom="1" aria-label="Acercar">${icono('mas')}</button>
            <button type="button" class="btn chico" data-zoom="0">Ajustar</button>
            <button type="button" class="btn chico" id="pf-girar" aria-label="Girar la foto a la derecha">${icono('girar')}</button>
          </div>
          <div class="pf-foto-marco" id="pf-marco" tabindex="0" aria-label="Foto de la planilla: arrástrela o use las barras para moverse"><p class="sec pf-foto-mensaje">Abriendo la foto…</p></div>
        </div>` : ''}
        <div class="pf-grilla">
          ${!filas.length ? html`<p class="sec">${d.estado === 'leyendo' ? 'Las filas aparecen cuando termine la lectura.' : 'No hay filas leídas.'}</p>`
            : revisa ? html`
            ${d.estado === 'leida' ? html`<div class="pf-grilla-barra">
              <span class="pf-leyenda"><span class="pf-marca" data-marca="dudoso">?</span> dudoso <span class="pf-marca" data-marca="ilegible">✕</span> ilegible <span class="pf-marca" data-marca="corregido">✓</span> corregido: compárelo con la foto</span>
              <span class="pf-elegir" role="group" aria-label="Elegir filas para cargar">Elegir: <button type="button" class="btn chico fantasma" data-elegir-grupo="limpias">limpias</button><button type="button" class="btn chico fantasma" data-elegir-grupo="todas">todas</button><button type="button" class="btn chico fantasma" data-elegir-grupo="ninguna">ninguna</button></span>
            </div>` : ''}
            <div class="envoltura-tabla pf-tabla-env"><table class="tabla pf-tabla"><thead><tr><th class="pf-sel"><span class="sr">Cargar</span></th><th class="pf-n">Fila</th><th class="pf-estado-celda">Estado</th>${columnas.map((k) => html`<th data-campo="${k}">${COLUMNAS[k]}</th>`)}</tr></thead>
              <tbody>${filas.map((f) => (f.estado === 'cargada' ? filaCargada(f, columnas)
                : f.estado === 'no_se_carga' ? filaFija(f, columnas, 'Esta fila no se carga.')
                  : filaRevisable(f, columnas)))}</tbody></table></div>`
            : tablaEnmascarada(filas)}
          ${puedeCargar ? html`<div class="pf-acciones" id="pf-acciones">
            <div class="form pf-carga">
              <label class="campo"><span>Folio o ubicación del papel</span><input id="pf-folio" maxlength="${FOLIO_MAX}" value="${folio}" placeholder="Por ejemplo: carpeta 3, hoja 12" autocomplete="off"></label>
              <label class="campo"><span>Capturado por</span><select id="pf-capturado"><option value="">— Nadie / varios —</option>${planilleros.map((u) => html`<option value="${u.id}"${String(u.id) === capturado ? html` selected` : ''}>${u.nombre || u.usuario} (${u.usuario})</option>`)}</select></label>
            </div>
            <p class="sec pf-carga-nota">El folio queda en la evidencia de cada fila: es lo que permite encontrar el papel cuando la foto ya se borró. La columna «Planillero (usuario)» de cada fila manda sobre «Capturado por».</p>
            <div class="pf-botones-carga">
              <button type="button" class="btn" id="pf-guardar" disabled>Guardar correcciones</button>
              <button type="button" class="btn" id="pf-cotejar">Cotejar con la base</button>
              <button type="button" class="btn primario" id="pf-cargar">Cargar filas</button>
            </div>
            <div id="pf-cotejo-resumen" class="pf-cotejo-resumen" aria-live="polite"></div>
          </div>` : ''}
          <div id="pf-resultado" class="pf-resultado"></div>
        </div>
      </div>`);
    if (foto) dibujarFoto();
    else if (d.con_foto && !pedidoFoto) cargarFoto(d.id);
    const nuevaEnvoltura = $('.pf-tabla-env', cajaAbierta), marco = $('#pf-marco', cajaAbierta);
    if (scroll && nuevaEnvoltura) [nuevaEnvoltura.scrollLeft, nuevaEnvoltura.scrollTop] = scroll;
    if (scrollFoto && marco) [marco.scrollLeft, marco.scrollTop] = scrollFoto;
    actualizarAcciones();
    pintarCotejo();
    pintarResultado();
    if (celda) {
      const x = $(`.pf-entrada[data-n="${celda.n}"][data-campo="${celda.campo}"]`, cajaAbierta);
      if (x && !x.disabled) {
        x.focus({ preventScroll: true });
        try { x.setSelectionRange(celda.ini, celda.fin); } catch { /* sin cursor */ }
      }
    } else if (enfocado) {
      const x = document.getElementById(enfocado);
      if (x && !x.disabled) x.focus({ preventScroll: true });
    }
  }

  // Lo que dicen los botones según lo escrito y lo elegido
  function actualizarAcciones() {
    const g = $('#pf-guardar', cajaAbierta), c = $('#pf-cargar', cajaAbierta), co = $('#pf-cotejar', cajaAbierta);
    if (g) {
      g.disabled = ocupado || !ediciones.size;
      g.textContent = ediciones.size ? `Guardar correcciones (${num(ediciones.size)})` : 'Guardar correcciones';
    }
    if (co) co.disabled = ocupado;
    if (c) {
      c.disabled = ocupado || !elegidas.size;
      c.textContent = !elegidas.size ? 'Cargar filas' : elegidas.size === 1 ? 'Cargar 1 fila' : `Cargar ${num(elegidas.size)} filas`;
    }
  }

  function pintarCotejo() {
    const caja_ = $('#pf-cotejo-resumen', cajaAbierta);
    if (!caja_) return;
    if (!cotejo) {
      montar(caja_, cotejoViejo ? html`<p class="sec">Corrigió la planilla después de cotejarla: vuelva a cotejar para ver qué pasará con cada fila.</p>` : html``);
      return;
    }
    const conteo = {};
    for (const f of Object.values(cotejo)) conteo[f.estado] = (conteo[f.estado] || 0) + 1;
    montar(caja_, html`<div class="chips"><b class="pf-cotejo-titulo">Cotejo con la base:</b>${Object.entries(conteo).map(([k, n]) => chip([(COTEJO[k] || ['borde'])[0], `${(COTEJO[k] || [0, k])[1]}: ${num(n)}`]))}</div>
      <p class="sec">No se escribió nada. Revise los conflictos y lo que queda por revisar antes de cargar; esas filas se cargan igual y quedan en Calidad de datos.</p>`);
  }

  function pintarResultado() {
    const caja_ = $('#pf-resultado', cajaAbierta);
    if (!caja_ || !resultado) { if (caja_) montar(caja_, html``); return; }
    const r = resultado.resumen || {};
    const filas = Object.entries(resultado.filas || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
    const porRevisar = (r.cedulas_en_revision || 0) + (r.registros_en_revision || 0) + (r.conflictos_cedula || 0);
    montar(caja_, html`<section class="pf-resultado-caja" aria-labelledby="pf-resultado-titulo">
      <h3 id="pf-resultado-titulo">Carga terminada: importación #${resultado.importacion_id}</h3>
      <div class="kpis">
        ${kpi('Personas nuevas', r.personas_nuevas)}
        ${kpi('Fichas completadas', r.personas_actualizadas)}
        ${kpi('Por revisar en Calidad', porRevisar)}
        ${kpi('Autorizaciones por confirmar', r.autorizaciones_por_confirmar || 0)}
      </div>
      <ul class="pf-resultado-filas">${filas.map(([n, f]) => html`<li><b>Fila ${n}:</b> ${CARGADO[f.estado] || f.estado}${f.motivo && MOTIVOS[f.motivo] ? ` (${MOTIVOS[f.motivo]})` : ''}${f.persona_id > 0 ? html` · <a href="/personas/${f.persona_id}" target="_blank" rel="noopener">Ficha #${f.persona_id}</a>` : ''}</li>`)}</ul>
      ${r.omitidas_sin_autorizacion ? html`<p class="sec">${num(r.omitidas_sin_autorizacion)} filas de personas que no autorizaron: no se les agregó ningún dato.</p>` : ''}
      ${r.no_guardadas ? html`<div class="aviso-legal">${num(r.no_guardadas)} fichas no se guardaron porque cambiaron al mismo tiempo en el panel: esas filas siguen por cargar.</div>` : ''}
      ${r.autorizaciones_por_confirmar ? html`<div class="aviso-legal pf-confirmar">${num(r.autorizaciones_por_confirmar)} autorizaciones quedaron «declaradas en planilla»: no habilitan llamadas hasta que usted las confirme con el papel a la vista.
        <button type="button" class="btn chico oscuro" data-confirmar-carga="${resultado.importacion_id}" data-n="${r.autorizaciones_por_confirmar}">Confirmar ${num(r.autorizaciones_por_confirmar)} con el papel</button></div>` : ''}
      ${porRevisar ? html`<p><a class="btn chico" href="/calidad" data-ruta>Revisar en Calidad de datos</a></p>` : ''}
    </section>`);
  }

  // ── Editar celdas ──
  cajaAbierta.addEventListener('input', (e) => {
    const x = e.target.closest('.pf-entrada');
    if (x) {
      const f = abierta?.filas?.find((y) => y.n === Number(x.dataset.n));
      if (!f) return;
      const clave = `${f.n}|${x.dataset.campo}`;
      if (x.value.trim() === valorOriginal(f, x.dataset.campo).trim()) ediciones.delete(clave);
      else ediciones.set(clave, x.value);
      x.closest('td')?.classList.toggle('cambiada', ediciones.has(clave));
      if (cotejo && ediciones.size) { cotejo = null; cotejoViejo = true; pintarCotejo(); }
      actualizarAcciones();
      return;
    }
    if (e.target.id === 'pf-folio') folio = e.target.value;
  });
  cajaAbierta.addEventListener('change', (e) => {
    if (e.target.id === 'pf-capturado') { capturado = e.target.value; return; }
    const sel = e.target.closest('[data-elegir]');
    if (sel) {
      const n = Number(sel.dataset.elegir);
      tocadas.add(n);
      if (sel.checked) elegidas.add(n); else elegidas.delete(n);
      actualizarAcciones();
    }
  });
  // Enter baja a la misma columna de la fila siguiente (Mayús+Enter sube) y Escape devuelve el valor leído
  cajaAbierta.addEventListener('keydown', (e) => {
    const x = e.target.closest?.('.pf-entrada');
    if (!x) return;
    if (e.key === 'Escape') {
      const f = abierta?.filas?.find((y) => y.n === Number(x.dataset.n));
      if (!f) return;
      x.value = valorOriginal(f, x.dataset.campo);
      x.dispatchEvent(new Event('input', { bubbles: true }));
      e.stopPropagation();
      return;
    }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const todas = $$(`.pf-entrada[data-campo="${x.dataset.campo}"]:not(:disabled)`, cajaAbierta);
    const i = todas.indexOf(x) + (e.shiftKey ? -1 : 1);
    todas[i]?.focus();
    todas[i]?.select();
  });

  async function guardar() {
    if (!abierta || !ediciones.size) return true;
    const enviadas = new Map(ediciones);
    const filas = [...enviadas].map(([clave, valor]) => {
      const [n, campo] = clave.split('|');
      return { n: Number(n), campo, valor: valor.trim() || null };
    });
    const id = abierta.id;
    ocupado = true; actualizarAcciones();
    try {
      const d = await api.patch(`/api/planillas/${id}`, { filas }, op);
      turno++;
      // Sale lo guardado; lo que se escribió mientras viajaba sigue pendiente (salvo que ya sea igual a lo guardado)
      for (const [k, v] of enviadas) if (ediciones.get(k) === v) ediciones.delete(k);
      const por = new Map((d.filas || []).map((f) => [f.n, f]));
      for (const [k, v] of [...ediciones]) {
        const [n, campo] = k.split('|');
        const f = por.get(Number(n));
        if (!f || v.trim() === valorOriginal(f, campo).trim()) ediciones.delete(k);
      }
      cotejoViejo ||= !!cotejo;
      cotejo = null;
      seguirEleccion(d);
      abierta = d;
      pintarAbierta();
      aviso(filas.length === 1 ? 'Corrección guardada' : `${num(filas.length)} correcciones guardadas`);
      return true;
    } catch (e) {
      if (cancelada(e)) return false;
      if (e instanceof ErrorApi && e.codigo === 'cambiada') {
        // Otra persona la tocó a la vez: se trae como quedó, con lo escrito encima, para revisarlo y guardarlo de nuevo
        await abrir(id, { desplazar: false, silencio: true });
        aviso('La planilla cambió mientras guardaba: revise y vuelva a guardar (sus correcciones siguen escritas).', 'error', 8000);
      } else {
        avisoError(e);
      }
      return false;
    } finally {
      ocupado = false; actualizarAcciones();
    }
  }

  async function marcar(n, descartar) {
    if (!abierta || !(await guardar())) return;
    ocupado = true; actualizarAcciones();
    try {
      const d = await api.patch(`/api/planillas/${abierta.id}`, descartar ? { descartar: [n] } : { restaurar: [n] }, op);
      turno++;
      tocadas.add(n); // descartar o recuperar es una decisión: la fila recuperada no se elige sola
      seguirEleccion(d);
      abierta = d;
      if (cotejo) { cotejo = null; cotejoViejo = true; }
      pintarAbierta();
    } catch (e) { if (!cancelada(e)) avisoError(e); } finally { ocupado = false; actualizarAcciones(); }
  }

  async function cotejar() {
    if (!abierta || !(await guardar())) return;
    ocupado = true; actualizarAcciones();
    const boton = $('#pf-cotejar', cajaAbierta);
    if (boton) boton.textContent = 'Cotejando…';
    try {
      const cuerpo = capturado ? { capturado_por: Number(capturado) } : {};
      const r = await api.post(`/api/planillas/${abierta.id}/simular`, cuerpo, { ...op, timeout: SIMULAR_MS });
      cotejo = Object.fromEntries((r.filas || []).map((f) => [f.n, f]));
      cotejoViejo = false;
      // Lo que no se podrá cargar (sin nombre) sale de lo elegido si nadie lo eligió a mano
      for (const f of r.filas || []) if (f.estado === 'sin_nombre' && !tocadas.has(f.n)) elegidas.delete(f.n);
      pintarAbierta();
    } catch (e) {
      if (!cancelada(e)) avisoError(e);
    } finally {
      ocupado = false;
      const b = $('#pf-cotejar', cajaAbierta);
      if (b) b.textContent = 'Cotejar con la base';
      actualizarAcciones();
    }
  }

  async function pedirCarga() {
    if (!abierta || !elegidas.size) return;
    folio = ($('#pf-folio', cajaAbierta)?.value || '').trim();
    if (folio.length < FOLIO_MIN) {
      aviso('Escriba el folio o dónde queda archivado el papel', 'error');
      $('#pf-folio', cajaAbierta)?.focus();
      return;
    }
    if (!(await guardar())) return;
    const filas = (abierta.filas || []).filter((f) => elegidas.has(f.n) && seleccionable(f));
    if (!filas.length) { aviso('Elija las filas que va a cargar', 'error'); return; }
    const dudosas = filas.filter(conDudas).length;
    const noes = filas.filter((f) => f.estado === 'no_autoriza' || ['no_autorizo', 'revocaria'].includes(cotejo?.[f.n]?.estado)).length;
    const conteo = {};
    if (cotejo) for (const f of filas) { const k = cotejo[f.n]?.estado; if (k) conteo[k] = (conteo[k] || 0) + 1; }
    const planillero = planilleros.find((u) => String(u.id) === capturado);
    const { el: d, cerrar } = dialogo({
      titulo: filas.length === 1 ? 'Cargar 1 fila de esta planilla' : `Cargar ${num(filas.length)} filas de esta planilla`,
      cuerpo: html`<p style="margin-top:0">Se cargan como «Planilla de campo» con el folio <b>${folio}</b>${planillero ? html`, capturadas por <b>${planillero.nombre || planillero.usuario}</b>` : ''}. La foto queda como evidencia por su huella (SHA-256).</p>
        ${Object.keys(conteo).length ? html`<div class="chips">${Object.entries(conteo).map(([k, n]) => chip([(COTEJO[k] || ['borde'])[0], `${(COTEJO[k] || [0, k])[1]}: ${num(n)}`]))}</div>`
          : html`<p class="sec">Aún no la cotejó con la base: «Cotejar con la base» muestra antes qué pasará con cada fila.</p>`}
        ${dudosas ? html`<p class="aviso-legal">${num(dudosas)} ${dudosas === 1 ? 'fila elegida tiene' : 'filas elegidas tienen'} datos dudosos o ilegibles sin corregir.</p>` : ''}
        ${noes ? html`<p class="sec">${num(noes)} ${noes === 1 ? 'persona dice' : 'personas dicen'} «No autoriza»: se anota su «no» y no se guarda ningún otro dato suyo.</p>` : ''}
        <p class="aviso-legal">Las autorizaciones leídas en una foto quedan «declaradas en planilla»: no habilitan llamadas hasta que usted las confirme con el papel.</p>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="pf-si-cargar">${filas.length === 1 ? 'Cargar 1 fila' : `Cargar ${num(filas.length)} filas`}</button>`,
      ocupado: () => ocupado,
    });
    $('#pf-si-cargar', d).addEventListener('click', async (ev) => {
      const b = ev.currentTarget, texto = b.textContent;
      b.disabled = true;
      b.textContent = 'Cargando…';
      const r = await cargar(filas.map((f) => f.n));
      if (r) {
        cerrar();
        aviso(`Importación #${r.importacion_id} terminada`);
        desplazarA($('#pf-resultado', cajaAbierta), 'nearest');
      } else if (b.isConnected) {
        // El error se ve dentro del diálogo, que sigue abierto para reintentar (con la misma clave si no fue un 4xx)
        b.disabled = false;
        b.textContent = texto;
      }
    });
  }

  async function cargar(ns) {
    const id = abierta.id;
    const cuerpo = { filas: ns, folio };
    if (capturado) cuerpo.capturado_por = Number(capturado);
    // La misma clave solo para reintentar la misma carga: con otras filas, otro folio u otro planillero es otra (con
    // la clave de una que se cortó, el servidor devolvería la respuesta de aquella y estas filas no se cargarían)
    const firma = JSON.stringify(cuerpo);
    if (claveCarga?.cuerpo !== firma) claveCarga = { clave: nuevaClave(), cuerpo: firma };
    ocupado = true; actualizarAcciones();
    try {
      const r = await api.post(`/api/planillas/${id}/cargar`, cuerpo, { ...op, clave: claveCarga.clave,
        timeout: CARGAR_MS });
      claveCarga = null;
      resultado = r;
      cotejo = null; cotejoViejo = false;
      for (const n of ns) { elegidas.delete(n); tocadas.delete(n); }
      try { alCargar?.(); } catch (e) { console.error(e); }
      ocupado = false;
      await abrir(id, { desplazar: false, silencio: true });
      if (abierta?.id === id) pintarResultado();
      consultar();
      return r;
    } catch (e) {
      if (cancelada(e)) return null;
      if (e instanceof ErrorApi && e.estado >= 400 && e.estado < 500 && e.codigo !== 'en_proceso') claveCarga = null;
      avisoError(e, 8000);
      return null;
    } finally {
      ocupado = false; actualizarAcciones();
    }
  }

  // Arrastrar la foto con el ratón para moverse (con el dedo ya se desplaza sola)
  let arrastre = null;
  cajaAbierta.addEventListener('pointerdown', (e) => {
    const m = e.target.closest('#pf-marco');
    if (!m || e.pointerType !== 'mouse' || e.button !== 0) return;
    arrastre = { x: e.clientX, y: e.clientY, l: m.scrollLeft, t: m.scrollTop, m };
    m.classList.add('arrastrando');
  });
  const moverArrastre = (e) => {
    if (!arrastre) return;
    arrastre.m.scrollLeft = arrastre.l - (e.clientX - arrastre.x);
    arrastre.m.scrollTop = arrastre.t - (e.clientY - arrastre.y);
  };
  const soltarArrastre = () => { arrastre?.m.classList.remove('arrastrando'); arrastre = null; };
  addEventListener('pointermove', moverArrastre);
  addEventListener('pointerup', soltarArrastre);

  cajaAbierta.addEventListener('click', async (e) => {
    const t = e.target;
    if (t.closest('#pf-cerrar')) {
      if (ediciones.size && !(await confirmar('Tiene correcciones sin guardar. ¿Descartarlas?', { si: 'Descartar', peligro: true }))) return;
      cerrarPlanilla();
      desplazarA(caja);
      return;
    }
    if (t.closest('#pf-borrar')) { borrar(abierta?.id); return; }
    if (t.closest('#pf-releer')) {
      const quedan = LECTURAS_MAX - (abierta?.lecturas || 0);
      const texto = abierta?.estado === 'leida'
        ? `¿Volver a leer toda la foto? Se pierde lo leído y sus correcciones (las filas cargadas siguen cargadas). Le ${quedan === 1 ? 'queda 1 lectura' : `quedan ${quedan} lecturas`} de esta foto.`
        : `¿Volver a leer la foto? Le ${quedan === 1 ? 'queda 1 lectura' : `quedan ${quedan} lecturas`} de esta foto.`;
      if (await confirmar(texto, { si: 'Volver a leer' })) releer(abierta.id, null, t.closest('button'));
      return;
    }
    const desde = t.closest('[data-releer-desde]');
    if (desde) { releer(abierta.id, Number(desde.dataset.releerDesde), desde); return; }
    const z = t.closest('[data-zoom]');
    if (z) {
      const paso = Number(z.dataset.zoom);
      zoom = paso === 0 ? 0 : Math.min(ZOOMS.length - 1, Math.max(0, zoom + paso));
      aplicarZoom();
      return;
    }
    if (t.closest('#pf-girar')) { giro = (giro + 90) % 360; dibujarFoto(); return; }
    const grupo = t.closest('[data-elegir-grupo]');
    if (grupo && abierta) {
      const k = grupo.dataset.elegirGrupo;
      const filas = (abierta.filas || []).filter(seleccionable);
      elegidas = k === 'todas' ? new Set(filas.map((f) => f.n)) : k === 'limpias' ? filasPorDefecto(filas) : new Set();
      for (const f of filas) tocadas.add(f.n);
      for (const x of $$('[data-elegir]', cajaAbierta)) x.checked = elegidas.has(Number(x.dataset.elegir));
      actualizarAcciones();
      return;
    }
    const des = t.closest('[data-descartar]'), res = t.closest('[data-restaurar]');
    if (des) { marcar(Number(des.dataset.descartar), true); return; }
    if (res) { marcar(Number(res.dataset.restaurar), false); return; }
    if (t.closest('#pf-guardar')) { guardar(); return; }
    if (t.closest('#pf-cotejar')) { cotejar(); return; }
    if (t.closest('#pf-cargar')) { pedirCarga(); return; }
    const conf = t.closest('[data-confirmar-carga]');
    if (conf) confirmarAutorizaciones(Number(conf.dataset.confirmarCarga), Number(conf.dataset.n), () => { try { alCargar?.(); } catch { /* nada */ } });
  });

  consultar().then(() => { if (vivo && inicial && ID_PLANILLA.test(inicial)) abrir(inicial); });

  return () => {
    vivo = false;
    clearTimeout(reloj);
    control.abort();
    soltarFoto();
    quitarPendiente();
    document.removeEventListener('visibilitychange', alVolver);
    removeEventListener('resize', alCambiarTamano);
    removeEventListener('pointermove', moverArrastre);
    removeEventListener('pointerup', soltarArrastre);
  };
}

export async function vistaImportar(el, { q } = {}) {
  const conImportar = puede('importar'), conFotos = puede('plantillas');
  const [historial, catalogos, ajustes] = await Promise.all([
    conImportar ? api.get('/api/importaciones') : [],
    conImportar ? api.get('/api/catalogos').catch(() => ({})) : {},
    conFotos && puede('ajustes.gestionar') ? api.get('/api/ajustes').catch(() => null) : null,
  ]);
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const planilleros = (catalogos.usuarios || []).filter((u) => u.rol === 'planillero' && u.activo !== false);
  const titulo = puede('exportar') ? 'Importar y exportar' : conImportar ? 'Importar' : 'Planillas por foto';
  montar(el, html`
    <div class="cabecera"><div><h1>${titulo}</h1><div class="sub">${conImportar ? 'Suba versiones nuevas cuando quiera: nada se duplica, lo editado en el panel no se pisa y lo distinto queda como dato alterno.' : 'Suba las fotos de sus planillas de campo: el panel las lee y un coordinador las revisa y las carga.'}</div></div></div>
    <div class="rejilla r-12">
      ${conImportar ? html`<section class="tarjeta c-7">
        <h2>Importar archivos de Excel</h2>
        <label class="zona-subida" id="zona" style="display:block"><input type="file" id="archivos" accept=".xlsx" multiple class="sr">
          <b>Arrastre aquí los archivos .xlsx o haga clic</b>
          <span class="sec">Base de trámites por vereda, base unificada con cédula, base general de la campaña (CC, nombre, líder, grupo…) y planillas de campo. Se reconocen por sus columnas.</span></label>
        <div id="elegidos" class="chips" style="margin:12px 0"></div>
        <div class="form" style="margin-bottom:12px">
          <label class="campo"><span>Capturado por (planillas)</span><select id="capturado">
            <option value="">— Nadie / varios —</option>${planilleros.map((u) => html`<option value="${u.id}">${u.nombre || u.usuario} (${u.usuario})</option>`)}</select></label>
          <div class="campo"><span>Plantilla</span><button type="button" class="btn" id="plantilla">${icono('descargar')} Planilla de campo (.xlsx)</button></div>
        </div>
        <p class="sec" style="margin-top:0">La columna «Planillero (usuario)» de cada fila manda sobre «Capturado por».</p>
        <button class="btn primario" id="subir" disabled>Importar y cruzar</button>
        <div id="resultado" style="margin-top:16px"></div>
      </section>` : ''}
      ${puede('exportar') ? html`<section class="tarjeta c-5">
        <h2>Exportar</h2>
        <p class="sec">La base única completa en Excel: datos de contacto, dirección normalizada, coordenadas, precisión, necesidades, listas, reuniones y campos propios. Para exportar un grupo, aplique filtros en <a href="/personas" data-ruta>Habitantes</a> y exporte desde allí. Las exportaciones omiten a quien marcó «No autorizó» el tratamiento de sus datos.</p>
        <button class="btn oscuro" id="exportar">${icono('descargar')} Descargar base única (.xlsx)</button>
        <div class="aviso-legal" style="margin-top:16px">Cada exportación queda en la auditoría. Comparta el archivo solo por canales seguros y bórrelo cuando ya no lo necesite.</div>
      </section>` : ''}
      ${conFotos ? html`<section class="tarjeta c-12 planillas-foto" id="planillas-foto" aria-labelledby="pf-titulo"></section>
      <section class="tarjeta c-12 planilla-abierta" id="planilla-abierta" aria-labelledby="pf-abierta-titulo" hidden></section>` : ''}
      ${conImportar ? html`<section class="tarjeta c-12">
        <h2>Historial de importaciones</h2>
        <div id="historial">${tablaHistorial(historial)}</div>
      </section>` : ''}
    </div>`);

  const recargarHistorial = async () => {
    if (!conImportar) return;
    try { montar($('#historial', el), tablaHistorial(await api.get('/api/importaciones'))); } catch { /* se ve al volver a la vista */ }
  };
  const limpiarFotos = conFotos ? planillasPorFoto($('#planillas-foto', el), $('#planilla-abierta', el), {
    planilleros, ajustes, inicial: q?.get?.('planilla') || null,
    alCargar: () => { refrescarInsignias(); recargarHistorial(); },
  }) : null;
  if (!conImportar) return limpiarFotos;

  let archivos = [];
  const elegir = (lista) => {
    archivos = [...lista].filter((f) => f.name.toLowerCase().endsWith('.xlsx'));
    // Más de 6 no se envían: el servidor ignoraría los demás sin avisar
    const demasiados = archivos.length > MAX_ARCHIVOS;
    montar($('#elegidos', el), html`${archivos.map((f) => html`<span class="chip azul">${f.name} · ${(f.size / 1048576).toFixed(1)} MB</span>`)}
      ${demasiados ? html`<span class="chip rojo">Eligió ${num(archivos.length)} archivos: importe como máximo ${MAX_ARCHIVOS} a la vez</span>` : ''}`);
    $('#subir', el).disabled = !archivos.length || demasiados;
    if (demasiados) aviso(`Importe como máximo ${MAX_ARCHIVOS} archivos a la vez; el resto, en otra importación`, 'error', 6000);
  };
  const zona = $('#zona', el);
  $('#archivos', el).addEventListener('change', (e) => elegir(e.target.files));
  zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('encima'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
  zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('encima'); elegir(e.dataTransfer.files); });
  $('#plantilla', el).addEventListener('click', async () => {
    try { await descargar('/api/plantillas/planilla.xlsx'); } catch (e) { avisoError(e); }
  });
  $('#subir', el).addEventListener('click', async () => {
    if (!archivos.length || archivos.length > MAX_ARCHIVOS) return;
    const fd = new FormData();
    archivos.forEach((f) => fd.append('archivos', f));
    const capturado = $('#capturado', el).value;
    if (capturado) fd.append('capturado_por', capturado);
    $('#subir', el).disabled = true;
    montar($('#resultado', el), html`<div style="display:flex;gap:10px;align-items:center"><div class="giro"></div><span>Leyendo, cruzando por cédula y nombre y georreferenciando…</span></div>`);
    try {
      const r = await api.subir('/api/importar', fd);
      montar($('#resultado', el), resumen(r));
      aviso('Importación terminada');
      refrescarInsignias();
      recargarHistorial(); // muestra esta importación
    } catch (e) {
      montar($('#resultado', el), html`<div class="aviso-legal">${e.message}</div>`);
    } finally {
      $('#subir', el).disabled = false;
    }
  });
  // Autorizaciones «declaradas en planilla»: el administrador las confirma con la evidencia física
  $('#historial', el).addEventListener('click', (e) => {
    const b = e.target.closest('[data-confirmar]');
    if (b) confirmarAutorizaciones(b.dataset.confirmar, Number(b.dataset.n), recargarHistorial);
  });
  $('#exportar', el)?.addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx'); aviso('Exportación lista'); } catch (e) { aviso(e.message, 'error'); }
  });
  return limpiarFotos;
}
